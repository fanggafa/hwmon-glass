"""Requests elevation for the monitor.

CPU and board temperatures come from MSR registers and the SuperIO chip, and
PawnIO only hands out its device handle to administrators. Rather than ship a
half-working panel, the app relaunches itself elevated once and remembers that
it did so.
"""

from __future__ import annotations

import ctypes
import os
import sys

_MARKER = "PYHWMON_ELEVATED"


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def relaunch_elevated() -> bool:
    """Spawns an elevated copy of this script. Returns True if it was launched."""
    if is_admin():
        return False
    if os.environ.get(_MARKER) == "1":
        # Already tried and the user said no: don't loop.
        return False

    try:
        exe = sys.executable
        # Prefer pythonw so no console appears behind the panel.
        pythonw = os.path.join(os.path.dirname(exe), "pythonw.exe")
        if os.path.exists(pythonw):
            exe = pythonw

        script = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "main.py"))
        os.environ[_MARKER] = "1"

        rc = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", exe, f'"{script}"',
            os.path.dirname(script), 1)
        # > 32 means the shell started it (the UAC prompt appeared or was accepted)
        return rc > 32
    except Exception:
        return False
