"""Locate and run the external command-line tools (libimobiledevice, adb)."""

from __future__ import annotations

import os
import shutil
import subprocess
from typing import Dict, List, Optional

# Places the tools commonly live but that are often missing from a GUI-launched PATH.
_EXTRA_DIRS = [
    "/opt/homebrew/bin",
    "/usr/local/bin",
    "/usr/bin",
    os.path.expanduser("~/Library/Android/sdk/platform-tools"),
    os.path.expanduser("~/Android/Sdk/platform-tools"),
]


class ToolMissing(Exception):
    def __init__(self, tool: str):
        super().__init__(f"{tool} not found")
        self.tool = tool


class ToolError(Exception):
    def __init__(self, tool: str, code: int, output: str):
        super().__init__(f"{tool} exited with {code}: {output}")
        self.tool = tool
        self.code = code
        self.output = output


def find_tool(name: str) -> Optional[str]:
    found = shutil.which(name)
    if found:
        return found
    dirs = list(_EXTRA_DIRS)
    for env in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        if os.environ.get(env):
            dirs.append(os.path.join(os.environ[env], "platform-tools"))
    for d in dirs:
        candidate = os.path.join(d, name)
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


def run(tool: str, args: List[str], timeout: float = 20.0) -> bytes:
    """Run a tool and return stdout. Raises ToolMissing / ToolError."""
    path = find_tool(tool)
    if path is None:
        raise ToolMissing(tool)
    try:
        cp = subprocess.run([path] + args, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise ToolError(tool, -1, "timed out")
    if cp.returncode != 0:
        text = (cp.stderr or b"") + (cp.stdout or b"")
        raise ToolError(tool, cp.returncode, text.decode("utf-8", "replace").strip())
    return cp.stdout


def status() -> Dict[str, Optional[str]]:
    names = ["idevice_id", "ideviceinfo", "idevicediagnostics", "idevicepair", "adb"]
    return {n: find_tool(n) for n in names}
