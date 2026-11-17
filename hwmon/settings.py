"""User settings, persisted next to the executable as settings.json."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass


def _base_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


SETTINGS_PATH = os.path.join(_base_dir(), "settings.json")

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "LiquidGlassMon"


@dataclass
class Settings:
    # tray icon face
    tray_field: str = "cpu_load"
    # seconds between samples
    interval: float = 1.0
    # 0.4 .. 1.0; lower is more see-through
    opacity: float = 0.66
    # launch with Windows
    autostart: bool = False
    # weather city; empty means "locate by IP"
    city: str = ""

    @classmethod
    def load(cls) -> "Settings":
        try:
            with open(SETTINGS_PATH, encoding="utf-8") as f:
                data = json.load(f)
            known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
            return cls(**known)
        except Exception:
            return cls()

    def save(self):
        try:
            os.makedirs(os.path.dirname(SETTINGS_PATH), exist_ok=True)
            with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
                json.dump(asdict(self), f, ensure_ascii=False, indent=2)
        except Exception:
            pass


# -- autostart --------------------------------------------------------------

def autostart_enabled() -> bool:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, RUN_NAME)
            return True
    except Exception:
        return False


def set_autostart(enabled: bool) -> bool:
    """Registers or removes this app from the per-user Run key."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                            winreg.KEY_SET_VALUE) as k:
            if enabled:
                exe = sys.executable
                if getattr(sys, "frozen", False):
                    cmd = f'"{exe}"'
                else:
                    pythonw = os.path.join(os.path.dirname(exe), "pythonw.exe")
                    if os.path.exists(pythonw):
                        exe = pythonw
                    script = os.path.join(os.path.dirname(os.path.dirname(
                        os.path.abspath(__file__))), "main.py")
                    cmd = f'"{exe}" "{script}"'
                winreg.SetValueEx(k, RUN_NAME, 0, winreg.REG_SZ, cmd)
            else:
                try:
                    winreg.DeleteValue(k, RUN_NAME)
                except FileNotFoundError:
                    pass
        return True
    except Exception:
        return False
