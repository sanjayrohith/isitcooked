"""Machine-readable output. Identifiers are masked unless `reveal` is set."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from . import __version__
from .models import DeviceReport, ScanResult
from .redact import mask


def device_to_dict(d: DeviceReport, reveal: bool = False) -> Dict[str, Any]:
    battery = d.battery.to_dict()
    if not reveal and battery.get("serial"):
        battery["serial"] = mask(battery["serial"])
    sections: Dict[str, Dict[str, Any]] = {}
    for s in d.sections:
        sections[s.key] = {
            r.key: (mask(str(r.value)) if r.sensitive and not reveal else r.value) for r in s.rows
        }
    return {
        "platform": d.platform,
        "id": d.device_id if reveal else mask(d.device_id),
        "name": d.name,
        "model": d.model,
        "os": d.os,
        "state": d.state,
        "message": d.message,
        "battery": battery,
        "sections": sections,
        "warnings": d.warnings,
    }


def to_dict(result: ScanResult, reveal: bool = False) -> Dict[str, Any]:
    return {
        "tool": "phonecheck",
        "version": __version__,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "identifiers_masked": not reveal,
        "devices": [device_to_dict(d, reveal) for d in result.devices],
        "notes": result.notes,
    }
