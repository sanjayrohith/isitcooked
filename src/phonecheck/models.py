"""Plain data containers shared by the iOS and Android readers and the renderers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# Battery condition bands (same thresholds as the Capax macOS app).
EXCELLENT, GOOD, FAIR, SERVICE, UNKNOWN = "excellent", "good", "fair", "service", "unknown"

CONDITION_LABELS = {
    EXCELLENT: "Excellent",
    GOOD: "Good",
    FAIR: "Fair",
    SERVICE: "Service recommended",
    UNKNOWN: "Unknown",
}


@dataclass
class Row:
    """One labelled value. `unit` drives formatting; `sensitive` values are masked by default."""

    key: str
    label: str
    value: Any
    unit: str = ""
    sensitive: bool = False


@dataclass
class Section:
    key: str
    title: str
    rows: List[Row] = field(default_factory=list)

    def add(
        self,
        key: str,
        label: str,
        value: Any,
        unit: str = "",
        sensitive: bool = False,
    ) -> None:
        """Append a row, silently skipping values the device did not provide."""
        if value is None or value == "":
            return
        self.rows.append(Row(key, label, value, unit, sensitive))


@dataclass
class Battery:
    """Battery snapshot. Health is always computed from raw capacities, never trusted from the OS."""

    cycle_count: Optional[int] = None
    design_mah: Optional[int] = None
    full_charge_mah: Optional[int] = None  # current maximum capacity, in mAh
    current_mah: Optional[int] = None
    charge_percent: Optional[float] = None
    temperature_c: Optional[float] = None
    voltage_mv: Optional[int] = None
    current_ma: Optional[int] = None  # positive = charging, negative = discharging
    is_charging: Optional[bool] = None
    external_connected: Optional[bool] = None
    fully_charged: Optional[bool] = None
    technology: Optional[str] = None
    os_health: Optional[str] = None  # e.g. Android "Good" / "Overheat"
    rated_cycles: Optional[int] = None  # manufacturer's rated cycle life, when known
    adapter_watts: Optional[float] = None
    adapter_description: Optional[str] = None
    time_to_empty_min: Optional[int] = None
    serial: Optional[str] = None
    capacity_source: Optional[str] = None  # which key the capacity came from

    @property
    def health_percent(self) -> Optional[float]:
        if not self.design_mah or not self.full_charge_mah or self.design_mah <= 0:
            return None
        return round(self.full_charge_mah / self.design_mah * 100.0, 1)

    @property
    def condition(self) -> str:
        h = self.health_percent
        if h is None:
            return UNKNOWN
        if h >= 90:
            return EXCELLENT
        if h >= 80:
            return GOOD
        if h >= 60:
            return FAIR
        return SERVICE

    @property
    def cycle_fraction(self) -> Optional[float]:
        if self.cycle_count is None or not self.rated_cycles:
            return None
        return self.cycle_count / self.rated_cycles

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cycle_count": self.cycle_count,
            "rated_cycles": self.rated_cycles,
            "health_percent": self.health_percent,
            "condition": self.condition,
            "design_capacity_mah": self.design_mah,
            "full_charge_capacity_mah": self.full_charge_mah,
            "current_capacity_mah": self.current_mah,
            "charge_percent": self.charge_percent,
            "temperature_c": self.temperature_c,
            "voltage_mv": self.voltage_mv,
            "current_ma": self.current_ma,
            "is_charging": self.is_charging,
            "external_power_connected": self.external_connected,
            "fully_charged": self.fully_charged,
            "technology": self.technology,
            "os_reported_health": self.os_health,
            "adapter_watts": self.adapter_watts,
            "adapter": self.adapter_description,
            "time_to_empty_min": self.time_to_empty_min,
            "serial": self.serial,
            "capacity_source": self.capacity_source,
        }


# Device states. Anything other than "ok" means we could see the phone but not read it.
OK, UNTRUSTED, UNAUTHORIZED, OFFLINE, ERROR = "ok", "untrusted", "unauthorized", "offline", "error"


@dataclass
class DeviceReport:
    platform: str  # "ios" | "android"
    device_id: str
    name: str = ""
    model: str = ""
    os: str = ""
    state: str = OK
    message: str = ""
    battery: Battery = field(default_factory=Battery)
    sections: List[Section] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def section(self, key: str, title: str) -> Section:
        s = Section(key, title)
        self.sections.append(s)
        return s


@dataclass
class ScanResult:
    devices: List[DeviceReport] = field(default_factory=list)
    # tool name -> resolved path (or None when missing)
    tools: Dict[str, Optional[str]] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)
