import plistlib

from phonecheck import ios, ios_models
from phonecheck.models import EXCELLENT, GOOD, SERVICE, UNKNOWN, Battery

# Mirrors the structure a modern iPhone returns: capacities live under BatteryData and
# AppleRawMaxCapacity is absent. Values are synthetic.
MODERN_IOREG = {
    "IORegistry": {
        "CycleCount": 764,
        "CurrentCapacity": 82,
        "MaxCapacity": 100,  # a percentage on modern iOS, must NOT be read as mAh
        "Voltage": 4291,
        "AppleRawBatteryVoltage": 4291,
        "InstantAmperage": 1176,
        "ExternalConnected": True,
        "IsCharging": True,
        "Serial": "TESTSERIAL0000001",
        "AdapterDetails": {"Watts": 8, "Description": "pd charger"},
        "BatteryData": {
            "DesignCapacity": 4325,
            "NominalChargeCapacity": 3577,
            "FullChargeCapacity": 3631,
            "RemainingCapacity": 2962,
        },
    }
}


def test_modern_ioreg_uses_nominal_capacity_and_ignores_percentage_max_capacity():
    b = ios.parse_battery(MODERN_IOREG, {}, product_type="iPhone14,8")
    assert b.cycle_count == 764
    assert b.design_mah == 4325
    assert b.full_charge_mah == 3577
    assert b.capacity_source == "NominalChargeCapacity"
    assert b.health_percent == 82.7
    assert b.condition == GOOD
    assert b.current_mah == 2962
    assert b.voltage_mv == 4291
    assert b.adapter_watts == 8.0
    assert b.rated_cycles == 500
    assert b.charge_percent == 82.0


def test_legacy_raw_max_capacity_wins_when_present():
    root = {"CycleCount": 100, "DesignCapacity": 3000, "AppleRawMaxCapacity": 2850}
    b = ios.parse_battery(root, {})
    assert (b.design_mah, b.full_charge_mah) == (3000, 2850)
    assert b.condition == EXCELLENT


def test_missing_capacity_gives_unknown_health_not_a_fake_number():
    b = ios.parse_battery({"IORegistry": {"CycleCount": 5}}, {})
    assert b.health_percent is None
    assert b.condition == UNKNOWN


def test_gas_gauge_fallback_for_cycle_count():
    b = ios.parse_battery({}, {}, gas_gauge={"CycleCount": 321})
    assert b.cycle_count == 321


def test_discharging_amperage_wraparound_is_signed():
    root = {"CycleCount": 1, "InstantAmperage": (1 << 64) - 500}
    assert ios.parse_battery(root, {}).current_ma == -500


def test_domain_charge_state_takes_priority():
    domain = {"BatteryCurrentCapacity": 55, "BatteryIsCharging": False, "ExternalConnected": False}
    b = ios.parse_battery({"IORegistry": {"CycleCount": 1, "CurrentCapacity": 99}}, domain)
    assert b.charge_percent == 55.0
    assert b.is_charging is False
    assert b.external_connected is False


def test_service_band():
    b = Battery(design_mah=4000, full_charge_mah=2000)
    assert b.condition == SERVICE


def test_plist_roundtrip_through_parser():
    data = plistlib.dumps({"a": 1})
    assert ios._plist(data) == {"a": 1}
    assert ios._plist(b"not a plist") == {}


def test_trust_error_detection():
    assert ios.looks_like_trust_error("ERROR: Could not connect to lockdownd, error code -21")
    assert ios.looks_like_trust_error("Please accept the trust dialog on the screen")
    assert not ios.looks_like_trust_error("No such file")


def test_model_names_and_rated_cycles():
    assert ios_models.marketing_name("iPhone14,8") == "iPhone 14 Plus"
    assert ios_models.marketing_name("iPhone99,1") == "iPhone (iPhone99,1)"
    assert ios_models.rated_cycles("iPhone15,3") == 500  # 14 Pro Max
    assert ios_models.rated_cycles("iPhone15,4") == 1000  # 15
    assert ios_models.rated_cycles("iPhone17,1") == 1000
    assert ios_models.rated_cycles("Watch1,1") is None
