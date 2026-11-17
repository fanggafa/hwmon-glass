"""Single-instance guard.

The app relaunches itself elevated, so without a lock the original process and
its elevated copy both run: two tray icons, two panels, and menus that appear to
do nothing because clicks land on the invisible one.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt

ERROR_ALREADY_EXISTS = 183
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

_kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wt.BOOL, wt.LPCWSTR]
_kernel32.CreateMutexW.restype = wt.HANDLE

_handle = None


def acquire(name: str = "Global\\LiquidGlassMon") -> bool:
    """True when this process is the only instance; False if one exists."""
    global _handle
    ctypes.set_last_error(0)
    h = _kernel32.CreateMutexW(None, True, name)
    if not h:
        return True  # cannot check; better to run than to refuse
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        return False
    _handle = h
    return True


def release():
    global _handle
    if _handle:
        try:
            _kernel32.CloseHandle(_handle)
        except Exception:
            pass
        _handle = None
