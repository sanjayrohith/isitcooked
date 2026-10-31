"""Apple ProductType identifiers -> marketing names, and rated battery cycle life."""

from __future__ import annotations

import re
from typing import Optional

_NAMES = {
    "iPhone10,1": "iPhone 8", "iPhone10,4": "iPhone 8",
    "iPhone10,2": "iPhone 8 Plus", "iPhone10,5": "iPhone 8 Plus",
    "iPhone10,3": "iPhone X", "iPhone10,6": "iPhone X",
    "iPhone11,2": "iPhone XS", "iPhone11,4": "iPhone XS Max", "iPhone11,6": "iPhone XS Max",
    "iPhone11,8": "iPhone XR",
    "iPhone12,1": "iPhone 11", "iPhone12,3": "iPhone 11 Pro", "iPhone12,5": "iPhone 11 Pro Max",
    "iPhone12,8": "iPhone SE (2nd gen)",
    "iPhone13,1": "iPhone 12 mini", "iPhone13,2": "iPhone 12",
    "iPhone13,3": "iPhone 12 Pro", "iPhone13,4": "iPhone 12 Pro Max",
    "iPhone14,4": "iPhone 13 mini", "iPhone14,5": "iPhone 13",
    "iPhone14,2": "iPhone 13 Pro", "iPhone14,3": "iPhone 13 Pro Max",
    "iPhone14,6": "iPhone SE (3rd gen)",
    "iPhone14,7": "iPhone 14", "iPhone14,8": "iPhone 14 Plus",
    "iPhone15,2": "iPhone 14 Pro", "iPhone15,3": "iPhone 14 Pro Max",
    "iPhone15,4": "iPhone 15", "iPhone15,5": "iPhone 15 Plus",
    "iPhone16,1": "iPhone 15 Pro", "iPhone16,2": "iPhone 15 Pro Max",
    "iPhone17,1": "iPhone 16 Pro", "iPhone17,2": "iPhone 16 Pro Max",
    "iPhone17,3": "iPhone 16", "iPhone17,4": "iPhone 16 Plus", "iPhone17,5": "iPhone 16e",
    "iPad13,16": "iPad Air (5th gen)", "iPad13,18": "iPad (10th gen)",
    "iPad14,3": "iPad Pro 11\" (4th gen)", "iPad14,5": "iPad Pro 12.9\" (6th gen)",
    "iPad16,3": "iPad Pro 11\" (M4)", "iPad16,5": "iPad Pro 13\" (M4)",
}


def marketing_name(product_type: Optional[str]) -> str:
    if not product_type:
        return ""
    if product_type in _NAMES:
        return _NAMES[product_type]
    for prefix, family in (("iPhone", "iPhone"), ("iPad", "iPad"), ("iPod", "iPod touch")):
        if product_type.startswith(prefix):
            return f"{family} ({product_type})"
    return product_type


def rated_cycles(product_type: Optional[str]) -> Optional[int]:
    """Apple's published cycle life before ~80% capacity: 500 up to iPhone 14, 1000 from iPhone 15."""
    if not product_type:
        return None
    m = re.match(r"iPhone(\d+),(\d+)$", product_type)
    if m:
        major, minor = int(m.group(1)), int(m.group(2))
        if major >= 16 or (major == 15 and minor >= 4):
            return 1000
        return 500
    if product_type.startswith("iPad"):
        return 1000
    return None

