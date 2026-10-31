"""Find every connected phone (iOS + Android) and read it."""

from __future__ import annotations

from typing import Callable, Optional

from . import android, ios, tools
from .models import ScanResult, UNAUTHORIZED, UNTRUSTED
from .tools import ToolError

Status = Callable[[str], None]

INSTALL_HINT = "Run the IsItCooked installer again, or: brew install libimobiledevice && brew install --cask android-platform-tools"


def scan(on_status: Optional[Status] = None, wait_for_prompts: bool = True) -> ScanResult:
    say = on_status or (lambda _msg: None)
    result = ScanResult(tools=tools.status())
    t = result.tools

    ios_ready = bool(t.get("idevice_id") and t.get("ideviceinfo") and t.get("idevicediagnostics"))
    if ios_ready:
        say("Looking for iPhones and iPads…")
        try:
            udids = ios.list_udids()
        except ToolError as e:
            udids = []
            result.notes.append(f"Could not list iOS devices: {e.output or 'unknown error'}")
        for udid in udids:
            say(f"Reading iOS device {udid[:8]}…")
            report = ios.collect(udid)
            if report.state == UNTRUSTED and wait_for_prompts:
                say("Waiting for you to tap “Trust” on the iPhone (enter your passcode if asked)…")
                if ios.wait_for_trust(udid):
                    report = ios.collect(udid)
            result.devices.append(report)
    else:
        result.notes.append("iPhone support is off: libimobiledevice is not installed. " + INSTALL_HINT)

    if t.get("adb"):
        say("Looking for Android phones…")
        try:
            found = android.list_devices()
        except ToolError as e:
            found = []
            result.notes.append(f"Could not list Android devices: {e.output or 'unknown error'}")
        for serial, state in found:
            say(f"Reading Android device {serial[:8]}…")
            report = android.collect(serial, state)
            if report.state == UNAUTHORIZED and wait_for_prompts:
                say("Waiting for you to tap “Allow” on the phone's USB debugging prompt…")
                if android.wait_for_authorization(serial):
                    report = android.collect(serial, "device")
            result.devices.append(report)
    else:
        result.notes.append("Android support is off: adb is not installed. " + INSTALL_HINT)

    return result
