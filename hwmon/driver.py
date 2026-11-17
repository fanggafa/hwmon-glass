"""PawnIO driver detection and guided installation.

CPU and motherboard temperatures are read from MSR registers and the SuperIO
chip. PawnIO is the kernel driver that exposes them, and it must be installed
with ``-unrestricted`` or the MSR pages stay closed.

Shipping the installer inside the app is what turns "install these five things"
into one click, so this module hides every step behind ``ensure_driver()``.
"""

from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import time
from typing import Optional

PAWNIO_SETUP = "PawnIO_setup.exe"
PAWNIO_DIR = r"C:\Program Files\PawnIO"
PAWNIO_LIB = os.path.join(PAWNIO_DIR, "PawnIOLib.dll")

# resources are unpacked next to the executable, or read from the source tree
def _asset_path(name: str) -> Optional[str]:
    candidates = []
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
        candidates.append(os.path.join(base, "assets", name))
        candidates.append(os.path.join(os.path.dirname(sys.executable), "assets", name))
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidates.append(os.path.join(root, "assets", name))
    for c in candidates:
        if os.path.exists(c):
            return c
    return None


def is_installed() -> bool:
    """True when the driver files exist and the service is present."""
    if not os.path.exists(PAWNIO_LIB):
        return False
    try:
        out = subprocess.run(["sc", "query", "PawnIO"], capture_output=True,
                             text=True, timeout=8, creationflags=0x08000000)
        return "RUNNING" in (out.stdout or "") or "STOPPED" in (out.stdout or "")
    except Exception:
        return False


def service_running() -> bool:
    try:
        out = subprocess.run(["sc", "query", "PawnIO"], capture_output=True,
                             text=True, timeout=8, creationflags=0x08000000)
        return "RUNNING" in (out.stdout or "")
    except Exception:
        return False


def install() -> tuple[bool, str]:
    """Runs the bundled installer elevated. Returns (ok, message)."""
    setup = _asset_path(PAWNIO_SETUP)
    if not setup:
        return False, "安装包缺失（assets/PawnIO_setup.exe）"

    # -unrestricted is the whole point: the default build refuses MSR reads.
    args = f'-install -unrestricted -silent'

    try:
        rc = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", setup, args, os.path.dirname(setup), 1)
    except Exception as exc:
        return False, f"无法启动安装程序：{exc}"

    if rc <= 32:
        # 5 = the user dismissed the UAC prompt
        if rc == 5:
            return False, "已取消授权"
        return False, f"启动失败（代码 {rc}）"

    # The installer is asynchronous; wait for the service to appear.
    for _ in range(60):
        time.sleep(1)
        if service_running():
            return True, "驱动已安装并启动"
    if is_installed():
        return True, "驱动已安装（请重启程序）"
    return False, "安装未完成，请手动运行 assets/PawnIO_setup.exe"


def uninstall() -> tuple[bool, str]:
    setup = _asset_path(PAWNIO_SETUP)
    if not setup:
        return False, "安装包缺失"
    try:
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", setup, "-uninstall -silent", None, 1)
        return True, "已请求卸载"
    except Exception as exc:
        return False, str(exc)
