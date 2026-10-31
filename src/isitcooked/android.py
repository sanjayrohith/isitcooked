"""Read Android phones over USB using adb (USB debugging must be enabled on the phone)."""

from __future__ import annotations

import re
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from .models import (
    Battery,
    DeviceReport,
    ERROR,
    OFFLINE,
    OK,
    UNAUTHORIZED,
)
from .tools import ToolError, run

_MARK = "@@PC@@"

# One round-trip to the phone. Every command is optional: a failure just leaves its section empty.
_SHELL_SCRIPT = f"""
echo {_MARK}props; getprop
echo {_MARK}battery; dumpsys battery
echo {_MARK}sysfs
for s in battery bms; do for f in cycle_count charge_full charge_full_design capacity temp; do
  v=$(cat /sys/class/power_supply/$s/$f 2>/dev/null); [ -n "$v" ] && echo "$s.$f=$v"
done; done
echo {_MARK}stats; dumpsys batterystats 2>/dev/null | grep -iE "battery capacity|cycle count"
echo {_MARK}df; df -k /data
echo {_MARK}mem; head -n 3 /proc/meminfo
echo {_MARK}wm; wm size; wm density
echo {_MARK}uptime; cat /proc/uptime
"""

_STATUS = {1: "Unknown", 2: "Charging", 3: "Discharging", 4: "Not charging", 5: "Full"}
_HEALTH = {
    1: "Unknown", 2: "Good", 3: "Overheat", 4: "Dead",
    5: "Over voltage", 6: "Unspecified failure", 7: "Cold",
}


# --------------------------------------------------------------------------- pure parsers


def parse_devices(output: str) -> List[Tuple[str, str]]:
    """Parse `adb devices` into [(serial, state)]."""
    result = []
    for line in output.splitlines():
        line = line.strip()
        if not line or line.startswith("*") or line.startswith("List of devices"):
            continue
        parts = line.split()
        if len(parts) >= 2:
            result.append((parts[0], parts[1]))
    return result


def split_sections(output: str) -> Dict[str, str]:
    sections: Dict[str, List[str]] = {}
    current: Optional[str] = None
    for line in output.splitlines():
        line = line.rstrip("\r")
        if line.startswith(_MARK):
            current = line[len(_MARK):]
            sections[current] = []
        elif current is not None:
            sections[current].append(line)
    return {k: "\n".join(v) for k, v in sections.items()}


def parse_props(text: str) -> Dict[str, str]:
    props = {}
    for m in re.finditer(r"^\[(.+?)\]: \[(.*)\]$", text, re.MULTILINE):
        props[m.group(1)] = m.group(2)
    return props


def parse_keyvalue(text: str) -> Dict[str, str]:
    """Parse `  key: value` lines (dumpsys battery). Keys are lower-cased."""
    out = {}
    for line in text.splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            out[k.strip().lower()] = v.strip()
    return out


def _int(value: Optional[str]) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value.strip())
    except ValueError:
        return None


def _bool(value: Optional[str]) -> Optional[bool]:
    if value is None:
        return None
    v = value.strip().lower()
    return True if v == "true" else False if v == "false" else None


def _to_mah(raw: Optional[int]) -> Optional[int]:
    """sysfs capacities are normally microamp-hours; a few kernels already report milliamp-hours."""
    if raw is None or raw <= 0:
        return None
    return round(raw / 1000) if raw >= 100_000 else raw


def parse_battery(battery_txt: str, sysfs_txt: str, stats_txt: str) -> Battery:
    b = Battery()
    kv = parse_keyvalue(battery_txt)

    level, scale = _int(kv.get("level")), _int(kv.get("scale")) or 100
    if level is not None and scale > 0:
        b.charge_percent = round(level * 100.0 / scale, 1)

    temp = _int(kv.get("temperature"))
    if temp is not None:
        b.temperature_c = round(temp / 10.0, 1)  # tenths of a degree C

    volt = _int(kv.get("voltage"))
    if volt:
        b.voltage_mv = volt // 1000 if volt > 100_000 else volt  # a few devices report microvolts

    status, health = _int(kv.get("status")), _int(kv.get("health"))
    if status is not None:
        b.is_charging = status == 2
        b.fully_charged = status == 5
    b.os_health = _HEALTH.get(health) if health is not None else None
    b.technology = kv.get("technology") or None

    powered = [_bool(kv.get(k)) for k in ("ac powered", "usb powered", "wireless powered", "dock powered")]
    known = [p for p in powered if p is not None]
    b.external_connected = any(known) if known else None

    counter = _int(kv.get("charge counter"))  # microamp-hours of charge currently held
    if counter and counter > 0:
        b.current_mah = round(counter / 1000)

    amps, volts = _int(kv.get("max charging current")), _int(kv.get("max charging voltage"))
    if b.external_connected and amps and volts and amps > 0 and volts > 0:
        b.adapter_watts = round(amps * volts / 1e12, 1)

    sysfs = dict(line.split("=", 1) for line in sysfs_txt.splitlines() if "=" in line)

    def sys_val(name: str) -> Optional[int]:
        for supply in ("battery", "bms"):
            v = _int(sysfs.get(f"{supply}.{name}"))
            if v is not None:
                return v
        return None

    cycles = next((_int(v) for k, v in kv.items() if "cycle" in k and _int(v) is not None), None)
    if cycles is None:
        cycles = sys_val("cycle_count")
    if cycles is None:
        m = re.search(r"cycle count\D*(\d+)", stats_txt, re.IGNORECASE)
        cycles = int(m.group(1)) if m else None
    b.cycle_count = cycles

    design, full = _to_mah(sys_val("charge_full_design")), _to_mah(sys_val("charge_full"))
    if design and full:
        b.design_mah, b.full_charge_mah, b.capacity_source = design, full, "sysfs charge_full / charge_full_design"
    else:
        est = re.search(r"estimated battery capacity:\s*([\d.]+)", stats_txt, re.IGNORECASE)
        learned = re.search(r"last learned battery capacity:\s*([\d.]+)", stats_txt, re.IGNORECASE)
        if est and learned and float(learned.group(1)) > 0:
            b.design_mah = round(float(est.group(1)))
            b.full_charge_mah = round(float(learned.group(1)))
            b.capacity_source = "batterystats learned capacity"
        elif design:
            b.design_mah = design
    return b


def parse_storage(df_txt: str) -> Optional[Tuple[int, int, int]]:
    """Return (total, used, available) in bytes from `df -k /data`."""
    for line in df_txt.splitlines():
        parts = line.split()
        if len(parts) >= 6 and parts[-1] == "/data" and parts[-5].isdigit():
            total, used, avail = (int(parts[-5]) * 1024, int(parts[-4]) * 1024, int(parts[-3]) * 1024)
            return total, used, avail
    return None


def parse_meminfo(text: str) -> Dict[str, int]:
    out = {}
    for line in text.splitlines():
        m = re.match(r"(\w+):\s+(\d+) kB", line)
        if m:
            out[m.group(1)] = int(m.group(2)) * 1024
    return out


# --------------------------------------------------------------------------- device access


def adb(args: List[str], timeout: float = 20.0) -> str:
    return run("adb", args, timeout=timeout).decode("utf-8", "replace")


def list_devices() -> List[Tuple[str, str]]:
    adb(["start-server"], timeout=15)
    return parse_devices(adb(["devices"]))


def wait_for_authorization(
    serial: str,
    timeout: float = 45.0,
    on_tick: Optional[Callable[[float], None]] = None,
) -> bool:
    """Poll until the user taps 'Allow USB debugging' on the phone."""
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        state = dict(list_devices()).get(serial)
        if state == "device":
            return True
        if state is None:
            return False
        if on_tick:
            on_tick(timeout - (time.monotonic() - start))
        time.sleep(2.0)
    return False


def collect(serial: str, state: str = "device") -> DeviceReport:
    report = DeviceReport(platform="android", device_id=serial)
    if state == "unauthorized":
        report.state = UNAUTHORIZED
        report.message = "Unlock the phone and tap 'Allow' on the USB debugging prompt, then run isitcooked again."
        return report
    if state == "offline":
        report.state = OFFLINE
        report.message = "adb reports the device offline. Unplug and replug the cable, then try again."
        return report
    if state != "device":
        report.state = ERROR
        report.message = f"Unexpected adb state: {state}"
        return report

    try:
        raw = adb(["-s", serial, "shell", _SHELL_SCRIPT], timeout=40)
    except ToolError as e:
        report.state = ERROR
        report.message = e.output or "adb shell failed."
        return report

    parts = split_sections(raw)
    props = parse_props(parts.get("props", ""))
    report.state = OK

    manufacturer = props.get("ro.product.manufacturer", "")
    model = props.get("ro.product.model", "")
    market = props.get("ro.product.marketname") or props.get("ro.config.marketing_name") or ""
    report.name = market or f"{manufacturer.title()} {model}".strip()
    report.model = model
    report.os = f"Android {props['ro.build.version.release']}" if props.get("ro.build.version.release") else ""

    report.battery = parse_battery(parts.get("battery", ""), parts.get("sysfs", ""), parts.get("stats", ""))
    if report.battery.cycle_count is None:
        report.warnings.append("This phone does not expose a battery cycle count to adb.")
    if report.battery.health_percent is None:
        report.warnings.append("This phone does not expose battery capacity values, so health % is unavailable.")

    _fill_sections(report, props, parts, manufacturer, model)
    return report


def _fill_sections(
    report: DeviceReport,
    props: Dict[str, str],
    parts: Dict[str, str],
    manufacturer: str,
    model: str,
) -> None:
    dev = report.section("device", "Device")
    dev.add("name", "Name", report.name)
    dev.add("manufacturer", "Manufacturer", manufacturer.title())
    dev.add("model", "Model", model)
    dev.add("device_codename", "Codename", props.get("ro.product.device"))
    dev.add("hardware", "Hardware", props.get("ro.hardware"))
    dev.add("platform", "SoC platform", props.get("ro.board.platform"))
    dev.add("cpu_abi", "CPU ABI", props.get("ro.product.cpu.abi"))
    dev.add("serial_number", "Serial number", props.get("ro.serialno") or report.device_id, sensitive=True)

    sw = report.section("software", "Software")
    sw.add("android_version", "Android version", props.get("ro.build.version.release"))
    sw.add("sdk_level", "API level", props.get("ro.build.version.sdk"))
    sw.add("security_patch", "Security patch", props.get("ro.build.version.security_patch"))
    sw.add("build_id", "Build", props.get("ro.build.display.id") or props.get("ro.build.id"))
    sw.add("build_type", "Build type", props.get("ro.build.type"))
    sw.add("baseband", "Baseband", props.get("gsm.version.baseband"))
    sw.add("time_zone", "Time zone", props.get("persist.sys.timezone"))

    st = report.section("storage", "Storage & memory")
    storage = parse_storage(parts.get("df", ""))
    if storage:
        total, used, avail = storage
        st.add("data_capacity_bytes", "User data capacity", total, "bytes")
        st.add("data_used_bytes", "Used", used, "bytes")
        st.add("data_available_bytes", "Available", avail, "bytes")
    mem = parse_meminfo(parts.get("mem", ""))
    st.add("ram_total_bytes", "RAM total", mem.get("MemTotal"), "bytes")
    st.add("ram_available_bytes", "RAM available", mem.get("MemAvailable"), "bytes")

    disp = report.section("display", "Display & uptime")
    size = re.search(r"Physical size:\s*(\S+)", parts.get("wm", ""))
    dens = re.search(r"Physical density:\s*(\d+)", parts.get("wm", ""))
    disp.add("resolution", "Resolution", size.group(1) if size else None)
    disp.add("density_dpi", "Density", int(dens.group(1)) if dens else None, "dpi")
    up = re.match(r"([\d.]+)", parts.get("uptime", "").strip())
    disp.add("uptime_s", "Uptime", int(float(up.group(1))) if up else None, "s")

    net = report.section("network", "Network & telephony")
    net.add("operator", "Carrier", props.get("gsm.operator.alpha") or props.get("gsm.sim.operator.alpha"))
    net.add("network_type", "Network type", props.get("gsm.network.type"))
    net.add("sim_state", "SIM state", props.get("gsm.sim.state"))

    sec = report.section("security", "Security")
    sec.add("verified_boot", "Verified boot", props.get("ro.boot.verifiedbootstate"))
    locked = props.get("ro.boot.flash.locked")
    if locked in ("0", "1"):
        sec.add("bootloader_locked", "Bootloader locked", locked == "1")
    sec.add("encryption", "Encryption", props.get("ro.crypto.state"))
