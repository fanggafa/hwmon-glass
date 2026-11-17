"""Static inventory for the details sheet."""

from __future__ import annotations

import ctypes
import subprocess
from dataclasses import dataclass, field


def _ps(script: str, timeout: int = 12) -> str:
    """Runs PowerShell hidden and returns stdout."""
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True, text=True, timeout=timeout,
            creationflags=0x08000000)
        return (out.stdout or "").strip()
    except Exception:
        return ""


def _cim(cls: str, props: list[str], namespace: str = "root/cimv2") -> list[dict]:
    """Queries one CIM class, returns rows as dicts. Empty on any failure."""
    cols = ",".join(props)
    script = (
        f"$ErrorActionPreference='SilentlyContinue';"
        f"Get-CimInstance -Namespace {namespace} -ClassName {cls} | "
        f"Select-Object {cols} | ConvertTo-Json -Compress"
    )
    raw = _ps(script)
    if not raw:
        return []
    try:
        import json
        data = json.loads(raw)
        if isinstance(data, dict):
            data = [data]
        return [d for d in data if isinstance(d, dict)]
    except Exception:
        return []


def _reg(path: str, name: str) -> str:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path) as k:
            v, _ = winreg.QueryValueEx(k, name)
            return str(v).strip()
    except Exception:
        return ""


_CN = "零一二三四五六七八九"


def cn_num(n: int) -> str:
    if n <= 0:
        return str(n)
    if n < 10:
        return _CN[n]
    if n == 10:
        return "十"
    if n < 20:
        return "十" + _CN[n % 10]
    if n % 10 == 0:
        return _CN[n // 10] + "十"
    return _CN[n // 10] + "十" + _CN[n % 10]


def friendly_cpu(raw: str, cores: int = 0) -> str:
    if not raw:
        return ""
    name = raw.replace("(R)", "").replace("(TM)", "").replace("  ", " ").strip()
    if "intel" in name.lower():
        name = name.replace("Intel Core ", "").replace("Intel ", "")
        gen = 0
        idx = name.lower().find("th gen")
        if idx > 0:
            try:
                gen = int(name[:idx].strip())
            except ValueError:
                gen = 0
            name = name[idx + 6:].strip()
        gen_text = f"{cn_num(gen)}代" if gen else ""
        core = f"{cn_num(cores)}核" if cores else ""
        return f"英特尔 {gen_text}酷睿 {name} {core}".strip()
    if "amd" in name.lower() or "ryzen" in name.lower():
        core = f"{cn_num(cores)}核" if cores else ""
        return f"AMD {name.replace('AMD ', '')} {core}".strip()
    return name


def brand_of(mfg: str) -> str:
    low = (mfg or "").lower()
    if "asustek" in low or "asus" in low:
        return "华硕"
    if "gigabyte" in low:
        return "技嘉"
    if "micro-star" in low or "msi" in low:
        return "微星"
    if "asrock" in low:
        return "华擎"
    return mfg or ""


@dataclass
class HardwareInfo:
    model: str = ""
    os_summary: str = ""
    cpu: str = ""
    board: str = ""
    memory: str = ""
    gpus: list[str] = field(default_factory=list)
    displays: list[str] = field(default_factory=list)
    disks: list[str] = field(default_factory=list)
    sound: list[str] = field(default_factory=list)
    net: list[str] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not any([self.cpu, self.board, self.memory,
                        self.gpus, self.disks, self.net])


def _dedupe(seq: list[str]) -> list[str]:
    seen = set()
    out = []
    for s in seq:
        key = s.lower()
        if not s or key in seen:
            continue
        seen.add(key)
        out.append(s)
    return out


def collect() -> HardwareInfo:
    info = HardwareInfo()

    # --- CPU -----------------------------------------------------------
    raw_cpu = _reg(r"HARDWARE\DESCRIPTION\System\CentralProcessor\0", "ProcessorNameString")
    cores = 0
    for row in _cim("Win32_Processor", ["Name", "NumberOfCores"]):
        if not raw_cpu:
            raw_cpu = row.get("Name") or ""
        try:
            cores = int(row.get("NumberOfCores") or 0)
        except (TypeError, ValueError):
            cores = 0
        break
    info.cpu = friendly_cpu(raw_cpu, cores)

    # --- board ---------------------------------------------------------
    board_prod = _reg(r"HARDWARE\DESCRIPTION\System\BIOS", "BaseBoardProduct")
    board_mfg = _reg(r"HARDWARE\DESCRIPTION\System\BIOS", "BaseBoardManufacturer")
    if board_prod:
        info.board = f"{brand_of(board_mfg)} {board_prod}".strip()

    # --- machine model -------------------------------------------------
    sys_prod = _reg(r"HARDWARE\DESCRIPTION\System\BIOS", "SystemProductName")
    sys_mfg = _reg(r"HARDWARE\DESCRIPTION\System\BIOS", "SystemManufacturer")
    kind = "台式电脑"
    for row in _cim("Win32_ComputerSystem", ["Model", "PCSystemType"]):
        try:
            if int(row.get("PCSystemType") or 1) == 2:
                kind = "笔记本"
        except (TypeError, ValueError):
            pass
        break
    if sys_prod:
        info.model = f"{brand_of(sys_mfg)} {sys_prod} {kind}".strip()

    # --- memory --------------------------------------------------------
    sizes, speeds = [], []
    for row in _cim("Win32_PhysicalMemory",
                    ["Capacity", "Speed", "ConfiguredClockSpeed", "SMBIOSMemoryType"]):
        try:
            cap = int(row.get("Capacity") or 0)
        except (TypeError, ValueError):
            cap = 0
        speed = 0
        for key in ("ConfiguredClockSpeed", "Speed"):
            try:
                speed = int(row.get(key) or 0)
            except (TypeError, ValueError):
                speed = 0
            if speed > 0:
                break
        if cap > 0:
            sizes.append(cap)
            speeds.append(speed)

    if sizes:
        total_gb = sum(sizes) / 1024 ** 3
        common = [s for s in speeds if s > 0]
        speed_txt = ""
        if common:
            speed_txt = f" {max(set(common), key=common.count)}MHz"
        detail = ""
        if len(sizes) > 1 and len(set(sizes)) == 1:
            detail = f"（{sizes[0] / 1024 ** 3:.0f}GB × {len(sizes)}）"
        else:
            detail = f"（{len(sizes)} 条）"
        info.memory = f"{total_gb:.0f}GB{speed_txt}{detail}"

    # --- GPU -----------------------------------------------------------
    for row in _cim("Win32_VideoController", ["Name"]):
        name = (row.get("Name") or "").strip()
        low = name.lower()
        if not name:
            continue
        if any(k in low for k in ("virtual", "orayidd", "basic", "remote")):
            continue
        info.gpus.append(name)
    if not info.gpus:
        for row in _cim("Win32_VideoController", ["Name"]):
            name = (row.get("Name") or "").strip()
            if name:
                info.gpus.append(name)

    # --- displays ------------------------------------------------------
    for row in _cim("Win32_DesktopMonitor", ["Name", "ScreenWidth", "ScreenHeight"]):
        name = (row.get("Name") or "").strip()
        if not name:
            continue
        if any(k in name for k in ("默认监视器", "Default", "通用即插即用")):
            continue
        try:
            w = int(row.get("ScreenWidth") or 0)
            h = int(row.get("ScreenHeight") or 0)
        except (TypeError, ValueError):
            w = h = 0
        size = f"（{w}×{h}）" if w and h else ""
        info.displays.append(name + size)

    # --- disks ---------------------------------------------------------
    for row in _cim("Win32_DiskDrive", ["Model", "Size"]):
        model = (row.get("Model") or "").strip()
        if not model or "virtual" in model.lower():
            continue
        try:
            size = int(row.get("Size") or 0)
        except (TypeError, ValueError):
            size = 0
        gb = f"（{size / 1024 ** 3:.0f}GB）" if size else ""
        info.disks.append(model + gb)

    # --- sound ---------------------------------------------------------
    for row in _cim("Win32_SoundDevice", ["Name"]):
        name = (row.get("Name") or "").strip()
        if name:
            info.sound.append(name)

    # --- network -------------------------------------------------------
    for row in _cim("Win32_NetworkAdapter", ["Name", "PNPDeviceID"]):
        name = (row.get("Name") or "").strip()
        pnp = (row.get("PNPDeviceID") or "")
        if not name:
            continue
        low = name.lower()
        if pnp.upper().startswith("ROOT\\"):
            continue
        if any(k in low for k in ("wan miniport", "virtual", "vmware", "bluetooth",
                                  "tap-", "loopback", "kernel debug", "wsl", "vethernet")):
            continue
        info.net.append(name)

    # --- OS ------------------------------------------------------------
    info.os_summary = _os_label()

    info.gpus = _dedupe(info.gpus)
    info.disks = _dedupe(info.disks)
    info.sound = _dedupe(info.sound)
    info.net = _dedupe(info.net)

    if not info.model:
        info.model = "本机"
    return info


def _os_label() -> str:
    try:
        v = __import__("os").sys.getwindowsversion()
        arch = "64位" if ctypes.sizeof(ctypes.c_void_p) == 8 else "32位"
        if v.major >= 10 and v.build >= 22000:
            rel = "24H2" if v.build >= 26100 else "23H2" if v.build >= 22631 else "22H2"
            return f"Windows 11 {rel} {arch}"
        return f"Windows 10 {arch}"
    except Exception:
        return "Windows"
