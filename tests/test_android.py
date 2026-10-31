from phonecheck import android

DEVICES = """* daemon not running; starting now at tcp:5037
* daemon started successfully
List of devices attached
R58M12ABCDE\tdevice usb:1-1 product:x model:SM_S911B device:dm1q transport_id:1
ZY22FFFF\tunauthorized usb:1-2 transport_id:2
emulator-5554\toffline

"""

BATTERY = """Current Battery Service state:
  AC powered: false
  USB powered: true
  Wireless powered: false
  Max charging current: 500000
  Max charging voltage: 5000000
  Charge counter: 2400000
  status: 2
  health: 2
  present: true
  level: 61
  scale: 100
  voltage: 4012
  temperature: 312
  technology: Li-ion
"""

SYSFS = """battery.cycle_count=212
battery.charge_full=4400000
battery.charge_full_design=5000000
"""


def test_parse_devices_skips_noise_and_reads_states():
    assert android.parse_devices(DEVICES) == [
        ("R58M12ABCDE", "device"),
        ("ZY22FFFF", "unauthorized"),
        ("emulator-5554", "offline"),
    ]


def test_parse_battery_from_dumpsys_and_sysfs():
    b = android.parse_battery(BATTERY, SYSFS, "")
    assert b.charge_percent == 61.0
    assert b.temperature_c == 31.2
    assert b.voltage_mv == 4012
    assert b.is_charging is True
    assert b.external_connected is True
    assert b.os_health == "Good"
    assert b.technology == "Li-ion"
    assert b.current_mah == 2400
    assert b.cycle_count == 212
    assert (b.design_mah, b.full_charge_mah) == (5000, 4400)
    assert b.health_percent == 88.0
    assert b.adapter_watts == 2.5


def test_cycle_count_from_dumpsys_battery_when_present():
    b = android.parse_battery(BATTERY + "  cycle count: 55\n", "battery.cycle_count=999\n", "")
    assert b.cycle_count == 55


def test_batterystats_fallback_for_capacity():
    stats = "  Estimated battery capacity: 5000 mAh\n  Last learned battery capacity: 4200 mAh\n"
    b = android.parse_battery(BATTERY, "", stats)
    assert (b.design_mah, b.full_charge_mah) == (5000, 4200)
    assert b.health_percent == 84.0


def test_missing_data_stays_none():
    b = android.parse_battery("", "", "")
    assert b.cycle_count is None
    assert b.health_percent is None


def test_milliamp_hour_sysfs_values_are_not_divided():
    b = android.parse_battery("", "battery.charge_full=4400\nbattery.charge_full_design=5000\n", "")
    assert (b.design_mah, b.full_charge_mah) == (5000, 4400)


def test_props_storage_and_meminfo():
    props = android.parse_props("[ro.product.model]: [Pixel 8]\n[ro.build.version.release]: [15]\n")
    assert props == {"ro.product.model": "Pixel 8", "ro.build.version.release": "15"}
    df = "Filesystem 1K-blocks Used Available Use% Mounted on\n/dev/block/dm-9 100000 40000 60000 40% /data\n"
    assert android.parse_storage(df) == (100000 * 1024, 40000 * 1024, 60000 * 1024)
    assert android.parse_meminfo("MemTotal:  8000000 kB\nMemAvailable: 3000000 kB\n")["MemAvailable"] == 3000000 * 1024


def test_split_sections():
    out = "@@PC@@props\n[a]: [b]\n@@PC@@df\nx\n"
    assert android.split_sections(out) == {"props": "[a]: [b]", "df": "x"}


def test_unauthorized_and_offline_states_do_not_touch_the_device():
    assert android.collect("S", "unauthorized").state == "unauthorized"
    assert android.collect("S", "offline").state == "offline"
