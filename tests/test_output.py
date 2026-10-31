import io
import json

from rich.console import Console

from isitcooked import jsonout, render
from isitcooked.models import Battery, DeviceReport, ScanResult
from isitcooked.redact import mask


def make_report() -> DeviceReport:
    d = DeviceReport(platform="ios", device_id="00008110-001828AE143A201E", name="Test iPhone", model="iPhone 14 Plus", os="iOS 18.0")
    d.battery = Battery(cycle_count=764, design_mah=4325, full_charge_mah=3577, rated_cycles=500, charge_percent=82, serial="ABCDEFGHIJKLMNOP")
    s = d.section("device", "Device")
    s.add("serial_number", "Serial number", "F2LXYZ123456", sensitive=True)
    s.add("name", "Name", "Test iPhone")
    st = d.section("storage", "Storage")
    st.add("data_capacity_bytes", "User data capacity", 119_583_199_232, "bytes")
    st.add("data_used_bytes", "Used", 100_000_000_000, "bytes")
    return d


def test_mask_keeps_format_and_ends():
    m = mask("00008110-001828AE143A201E")
    assert m[:2] == "00" and m[-3:] == "01E" and m[8] == "-"
    assert len(m) == len("00008110-001828AE143A201E")
    assert "1828" not in m
    assert mask("aa:bb:cc:dd:ee:ff").count(":") == 5
    assert mask("abc") == "a•c"


def test_json_masks_by_default_and_reveals_on_request():
    result = ScanResult(devices=[make_report()])
    masked = jsonout.to_dict(result)
    assert masked["identifiers_masked"] is True
    assert masked["devices"][0]["sections"]["device"]["serial_number"] != "F2LXYZ123456"
    assert masked["devices"][0]["battery"]["serial"] != "ABCDEFGHIJKLMNOP"
    assert "001828" not in json.dumps(masked)

    revealed = jsonout.to_dict(result, reveal=True)
    assert revealed["devices"][0]["sections"]["device"]["serial_number"] == "F2LXYZ123456"
    assert revealed["devices"][0]["id"] == "00008110-001828AE143A201E"
    assert revealed["devices"][0]["battery"]["health_percent"] == 82.7


def test_render_smoke_shows_key_numbers_and_hides_ids():
    buf = io.StringIO()
    console = Console(file=buf, width=120, force_terminal=False, color_system=None)
    render.render_scan(console, ScanResult(devices=[make_report()]))
    out = buf.getvalue()
    assert "764" in out and "500 rated" in out and "82.7%" in out and "Good" in out
    assert "F2LXYZ123456" not in out
    assert "119.6 GB" in out


def test_render_empty_and_blocked_states():
    buf = io.StringIO()
    console = Console(file=buf, width=100, force_terminal=False, color_system=None)
    blocked = DeviceReport(platform="ios", device_id="X" * 20, state="untrusted", message="Tap Trust.")
    render.render_scan(console, ScanResult(devices=[blocked]))
    assert "Tap Trust." in buf.getvalue()
    buf.truncate(0)
    render.render_scan(console, ScanResult())
    assert "No phone detected" in buf.getvalue()


def test_human_formatting():
    assert render.human_bytes(128_000_000_000) == "128.0 GB"
    assert render.human_bytes(512) == "512 B"
    assert render.human_duration(90_000) == "1d 1h"
