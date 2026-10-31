"""Mask personal identifiers (serials, IMEI, MAC, phone numbers) so reports are safe to share."""

from __future__ import annotations


def mask(value: str, head: int = 2, tail: int = 3) -> str:
    """Replace the middle alphanumerics with bullets, keeping separators and both ends.

    "00008110-001828AE143A201E" -> "00••••••-•••••••••••••01E"
    Short values keep one character at each end.
    """
    positions = [i for i, c in enumerate(value) if c.isalnum()]
    if len(positions) < 8:
        head, tail = 1, 1
    if len(positions) <= head + tail:
        return "•" * len(value)
    hidden = set(positions[head: len(positions) - tail])
    return "".join("•" if i in hidden else c for i, c in enumerate(value))
