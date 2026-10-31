"""Read iPhones / iPads over USB using libimobiledevice (idevice_id, ideviceinfo, ...)."""

from __future__ import annotations

import plistlib
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional

from . import ios_models
from .models import (
    Battery,
    DeviceReport,
    ERROR,
    UNTRUSTED,
)
from .tools import ToolError, run

_TRUST_HINTS = ("trust", "pair", "passcode", "password", "-21", "lockdownd")


# --------------------------------------------------------------------------- helpers


def _plist(data: bytes) -> Dict[str, Any]:
    try:
        parsed = plistlib.loads(data)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _find_dict_with(obj: Any, key: str) -> Optional[Dict[str, Any]]:
    """Depth-first search for the first dict containing `key` (IORegistry nesting varies)."""
    if isinstance(obj, dict):
        if key in obj:
            return obj
        for v in obj.values():
            hit = _find_dict_with(v, key)
            if hit is not None:
                return hit
    elif isinstance(obj, list):
        for v in obj:
            hit = _find_dict_with(v, key)
            if hit is not None:
                return hit
    return None


def _mah(value: Any) -> Optional[int]:
    """A plausible capacity in mAh. Values <= 100 are percentages on some keys, so reject them."""
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if value > 100 else None


def _signed(value: Any) -> Optional[int]:
    """IORegistry amperage is a signed value that can arrive as an unsigned 64-bit wraparound."""
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value - (1 << 64) if value >= (1 << 63) else value


def looks_like_trust_error(text: str) -> bool:
    t = text.lower()
    return any(h in t for h in _TRUST_HINTS)


# --------------------------------------------------------------------------- pure parsers


def parse_battery(
    ioreg: Dict[str, Any],
    domain: Dict[str, Any],
    gas_gauge: Optional[Dict[str, Any]] = None,
    product_type: Optional[str] = None,
) -> Battery:
    """Build a Battery from the three data sources the phone exposes.

    Newer iOS versions no longer publish AppleRawMaxCapacity; the maximum capacity Apple shows in
    Settings lives in BatteryData.NominalChargeCapacity. Older versions use AppleRawMaxCapacity.
    """
    b = Battery(rated_cycles=ios_models.rated_cycles(product_type))
    entry = _find_dict_with(ioreg, "CycleCount") or _find_dict_with(ioreg, "DesignCapacity") or {}
    data = entry.get("BatteryData") if isinstance(entry.get("BatteryData"), dict) else {}

    cycles = entry.get("CycleCount")
    if not isinstance(cycles, int) and gas_gauge:
        cycles = gas_gauge.get("CycleCount")
    b.cycle_count = cycles if isinstance(cycles, int) and not isinstance(cycles, bool) else None

    b.design_mah = _mah(data.get("DesignCapacity")) or _mah(entry.get("DesignCapacity"))

    for source, value in (
        ("AppleRawMaxCapacity", entry.get("AppleRawMaxCapacity")),
        ("NominalChargeCapacity", data.get("NominalChargeCapacity") or entry.get("NominalChargeCapacity")),
        ("FullChargeCapacity", data.get("FullChargeCapacity")),
    ):
        mah = _mah(value)
        if mah:
            b.full_charge_mah, b.capacity_source = mah, source
            break

    b.current_mah = (
        _mah(entry.get("AppleRawCurrentCapacity"))
        or _mah(data.get("RemainingCapacity"))
        or _mah(data.get("TrueRemainingCapacity"))
    )

    pct = domain.get("BatteryCurrentCapacity")
    if not isinstance(pct, int):
        pct = entry.get("CurrentCapacity")
    if isinstance(pct, int) and 0 <= pct <= 100:
        b.charge_percent = float(pct)

    temp = entry.get("Temperature") or entry.get("VirtualTemperature")
    if isinstance(temp, int) and 0 < temp < 10000:  # reported in hundredths of a degree C
        b.temperature_c = round(temp / 100.0, 1)

    volt = entry.get("AppleRawBatteryVoltage") or entry.get("Voltage")
    if isinstance(volt, int) and volt > 0:
        b.voltage_mv = volt

    b.current_ma = _signed(entry.get("InstantAmperage") if "InstantAmperage" in entry else entry.get("Amperage"))

    b.is_charging = _first_bool(domain.get("BatteryIsCharging"), entry.get("IsCharging"))
    b.external_connected = _first_bool(domain.get("ExternalConnected"), entry.get("ExternalConnected"))
    b.fully_charged = _first_bool(domain.get("FullyCharged"), entry.get("FullyCharged"))

    adapter = entry.get("AdapterDetails")
    if b.external_connected and isinstance(adapter, dict):
        watts = adapter.get("Watts")
        if isinstance(watts, (int, float)) and watts > 0:
            b.adapter_watts = float(watts)
        desc = adapter.get("Description")
        b.adapter_description = desc if isinstance(desc, str) and desc else None

    tte = entry.get("AvgTimeToEmpty")
    if b.is_charging is False and isinstance(tte, int) and 0 < tte < 65535:
        b.time_to_empty_min = tte

    serial = entry.get("Serial")
    b.serial = serial if isinstance(serial, str) and serial else None
    return b


def _first_bool(*values: Any) -> Optional[bool]:
    for v in values:
        if isinstance(v, bool):
            return v
    return None


# --------------------------------------------------------------------------- device access


def list_udids() -> List[str]:
    out = run("idevice_id", ["-l"]).decode("utf-8", "replace")
    return [line.strip() for line in out.splitlines() if line.strip()]


def is_paired(udid: str) -> bool:
    try:
        run("idevicepair", ["-u", udid, "validate"], timeout=10)
        return True
    except ToolError:
        return False


def request_pairing(udid: str) -> None:
    """Ask the phone to show its 'Trust This Computer?' prompt. Errors are expected until accepted."""
    try:
        run("idevicepair", ["-u", udid, "pair"], timeout=15)
    except ToolError:
        pass


def wait_for_trust(
    udid: str,
    timeout: float = 45.0,
    on_tick: Optional[Callable[[float], None]] = None,
) -> bool:
    """Trigger the trust prompt and poll until the user accepts it (or we time out)."""
    start = time.monotonic()
    request_pairing(udid)
    while time.monotonic() - start < timeout:
        if is_paired(udid):
            return True
        if on_tick:
            on_tick(timeout - (time.monotonic() - start))
        time.sleep(2.0)
    return False


def collect(udid: str) -> DeviceReport:
    report = DeviceReport(platform="ios", device_id=udid)

    try:
        info = _plist(run("ideviceinfo", ["-u", udid, "-x"]))
    except ToolError as e:
        if looks_like_trust_error(e.output):
            report.state = UNTRUSTED
            report.message = "Unlock the iPhone and tap 'Trust This Computer', then run isitcooked again."
        else:
            report.state = ERROR
            report.message = e.output or "Could not read device."
        return report

    def safe(what: str, args: List[str], timeout: float = 20.0) -> Dict[str, Any]:
        try:
            return _plist(run(args[0], args[1:], timeout=timeout))
        except ToolError as e:
            report.warnings.append(f"Could not read {what}: {e.output or 'failed'}")
            return {}

    with ThreadPoolExecutor(max_workers=4) as pool:
        f_domain = pool.submit(
            safe, "battery status", ["ideviceinfo", "-u", udid, "-q", "com.apple.mobile.battery", "-x"]
        )
        f_ioreg = pool.submit(
            safe, "battery registry", ["idevicediagnostics", "-u", udid, "ioregentry", "AppleSmartBattery"]
        )
        f_disk = pool.submit(
            safe, "storage", ["ideviceinfo", "-u", udid, "-q", "com.apple.disk_usage", "-x"]
        )
        domain, ioreg, disk = f_domain.result(), f_ioreg.result(), f_disk.result()

    product_type = info.get("ProductType")
    gas: Dict[str, Any] = {}
    entry = _find_dict_with(ioreg, "CycleCount")
    if entry is None:  # older devices expose the cycle count through the diagnostics GasGauge
        gas = safe("gas gauge", ["idevicediagnostics", "-u", udid, "diagnostics", "GasGauge"]).get("GasGauge", {})

    report.name = info.get("DeviceName", "")
    report.model = ios_models.marketing_name(product_type)
    report.os = f"iOS {info['ProductVersion']}" if info.get("ProductVersion") else ""
    report.battery = parse_battery(ioreg, domain, gas, product_type)
    _fill_sections(report, info, disk)
    return report


def _fill_sections(report: DeviceReport, info: Dict[str, Any], disk: Dict[str, Any]) -> None:
    dev = report.section("device", "Device")
    dev.add("name", "Name", info.get("DeviceName"))
    dev.add("model", "Model", report.model)
    dev.add("product_type", "Identifier", info.get("ProductType"))
    model_number = info.get("ModelNumber")
    if model_number:
        region = info.get("RegionInfo")
        dev.add("model_number", "Model number", f"{model_number}{region}" if region else model_number)
    dev.add("hardware_model", "Board", info.get("HardwareModel"))
    dev.add("cpu_architecture", "CPU architecture", info.get("CPUArchitecture"))
    dev.add("serial_number", "Serial number", info.get("SerialNumber"), sensitive=True)
    dev.add("udid", "UDID", info.get("UniqueDeviceID") or report.device_id, sensitive=True)

    sw = report.section("software", "Software")
    sw.add("ios_version", "iOS version", info.get("ProductVersion"))
    sw.add("build", "Build", info.get("BuildVersion"))
    sw.add("activation_state", "Activation", info.get("ActivationState"))
    pw = info.get("PasswordProtected")
    if isinstance(pw, bool):
        sw.add("passcode_set", "Passcode set", pw)
    sw.add("time_zone", "Time zone", info.get("TimeZone"))

    total = disk.get("TotalDataCapacity")
    avail = disk.get("AmountDataAvailable")
    st = report.section("storage", "Storage")
    st.add("disk_capacity_bytes", "Disk size", disk.get("TotalDiskCapacity"), "bytes")
    st.add("data_capacity_bytes", "User data capacity", total, "bytes")
    if isinstance(total, int) and isinstance(avail, int) and total > 0:
        st.add("data_available_bytes", "Available", avail, "bytes")
        st.add("data_used_bytes", "Used", max(total - avail, 0), "bytes")
    st.add("system_capacity_bytes", "System volume", disk.get("TotalSystemCapacity"), "bytes")

    net = report.section("network", "Network & telephony")
    net.add("wifi_mac", "Wi-Fi address", info.get("WiFiAddress"), sensitive=True)
    net.add("bluetooth_mac", "Bluetooth address", info.get("BluetoothAddress"), sensitive=True)
    net.add("imei", "IMEI", info.get("InternationalMobileEquipmentIdentity"), sensitive=True)
    net.add("imei2", "IMEI 2", info.get("InternationalMobileEquipmentIdentity2"), sensitive=True)
    net.add("phone_number", "Phone number", info.get("PhoneNumber"), sensitive=True)
    net.add("iccid", "SIM ICCID", info.get("IntegratedCircuitCardIdentity"), sensitive=True)
    net.add("sim_status", "SIM status", _tidy_sim(info.get("SIMStatus")))
    net.add("baseband_version", "Baseband", info.get("BasebandVersion"))


def _tidy_sim(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    return value.replace("kCTSIMSupportSIMStatus", "") or None
