"""LibreHardwareMonitor bridge via pythonnet.

This is the only way to read GPU/board/disk temperatures and per-core CPU
clocks without writing a driver ourselves. The assemblies ship inside the
internet-download-mark that .NET refuses to load by path, so every one is
loaded from bytes instead.
"""

from __future__ import annotations

import ctypes
import os

_LIBDIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib")

# Dependency order matters: each assembly must be resolvable before its
# dependents load.
_PRELOAD = [
    "System.Runtime.CompilerServices.Unsafe.dll",
    "System.Numerics.Vectors.dll",
    "System.Buffers.dll",
    "System.Memory.dll",
    "System.Threading.Tasks.Extensions.dll",
    "Microsoft.Bcl.AsyncInterfaces.dll",
    "Microsoft.Bcl.HashCode.dll",
    "System.Text.Encodings.Web.dll",
    "System.Text.Json.dll",
    "System.Security.AccessControl.dll",
    "System.Security.Principal.Windows.dll",
    "System.Threading.AccessControl.dll",
    "HidSharp.dll",
    "BlackSharp.Core.dll",
    "RAMSPDToolkit-NDD.dll",
    "DiskInfoToolkit.dll",
    "LibreHardwareMonitorLib.dll",
]


class LhmSensors:
    """Wraps a LibreHardwareMonitor Computer and exposes plain floats."""

    def __init__(self):
        self.ok = False
        self.admin = False
        self._computer = None
        self._types = {}

    @staticmethod
    def is_admin() -> bool:
        try:
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            return False

    def start(self) -> bool:
        self.admin = self.is_admin()
        try:
            import clr  # noqa: F401  (registers the CLR bridge)
            from System.Reflection import Assembly
        except Exception:
            return False

        if not os.path.isdir(_LIBDIR):
            return False

        for name in _PRELOAD:
            path = os.path.join(_LIBDIR, name)
            if not os.path.exists(path):
                continue
            try:
                with open(path, "rb") as f:
                    Assembly.Load(f.read())
            except Exception:
                # A failed optional dependency is not fatal as long as the main
                # assembly loaded; the sensor read will surface any real gap.
                pass

        try:
            from LibreHardwareMonitor.Hardware import Computer, HardwareType, SensorType
            self._types = {"HardwareType": HardwareType, "SensorType": SensorType}

            c = Computer()
            c.IsCpuEnabled = True
            c.IsGpuEnabled = True
            c.IsMemoryEnabled = True
            c.IsMotherboardEnabled = True
            c.IsStorageEnabled = True
            c.Open()
            self._computer = c
            self.ok = True
            return True
        except Exception:
            self._computer = None
            self.ok = False
            return False

    def stop(self):
        if self._computer is not None:
            try:
                self._computer.Close()
            except Exception:
                pass
            self._computer = None
        self.ok = False

    # -- reading ----------------------------------------------------------
    def read(self) -> dict:
        """Returns a flat dict of the sensor values we care about."""
        out: dict = {
            "cpu_temp": None,
            "cpu_clock_ghz": None,
            "cpu_power": None,
            "gpu_temp": None,
            "gpu_hotspot": None,
            "gpu_mem_used_mb": None,
            "gpu_mem_total_mb": None,
            "board_temp": None,
            "ram_temp": None,
            "disk_temp": None,
            "gpu_name": "",
        }
        if not self.ok or self._computer is None:
            return out

        SensorType = self._types["SensorType"]
        HardwareType = self._types["HardwareType"]

        try:
            for hw in self._computer.Hardware:
                self._read_hardware(hw, out, SensorType, HardwareType)
        except Exception:
            pass
        return out

    def _read_hardware(self, hw, out: dict, SensorType, HardwareType):
        try:
            hw.Update()
        except Exception:
            return

        htype = hw.HardwareType

        if htype == HardwareType.Cpu:
            clocks = []
            package = None
            core_max = None
            core_avg = None
            for s in hw.Sensors:
                if s.SensorType == SensorType.Temperature and s.Value is not None:
                    name = str(s.Name)
                    v = float(s.Value)
                    if "Package" in name:
                        package = v
                    elif "Core Max" in name:
                        core_max = v
                    elif "Core Average" in name:
                        core_avg = v
                elif s.SensorType == SensorType.Clock and s.Value is not None:
                    if "Bus" not in str(s.Name):
                        clocks.append(float(s.Value))
                elif s.SensorType == SensorType.Power and s.Value is not None:
                    if out["cpu_power"] is None and "Package" in str(s.Name):
                        out["cpu_power"] = float(s.Value)

            # Package is the number people mean by "CPU temperature"; the
            # per-core readings are supporting detail.
            out["cpu_temp"] = package if package is not None else (
                core_max if core_max is not None else core_avg)
            if core_max is not None:
                out["cpu_core_max"] = core_max

            if clocks and out["cpu_clock_ghz"] is None:
                out["cpu_clock_ghz"] = max(clocks) / 1000.0

        elif htype in (HardwareType.GpuNvidia, HardwareType.GpuAmd, HardwareType.GpuIntel):
            if not out["gpu_name"]:
                out["gpu_name"] = str(hw.Name)
            for s in hw.Sensors:
                if s.Value is None:
                    continue
                name = str(s.Name)
                if s.SensorType == SensorType.Temperature:
                    if "Hot" in name or "热点" in name:
                        out["gpu_hotspot"] = float(s.Value)
                    elif out["gpu_temp"] is None and ("Core" in name or "GPU" in name):
                        out["gpu_temp"] = float(s.Value)
                elif s.SensorType == SensorType.SmallData:
                    if "Memory Used" in name:
                        out["gpu_mem_used_mb"] = float(s.Value)
                    elif "Memory Total" in name:
                        out["gpu_mem_total_mb"] = float(s.Value)

        elif htype == HardwareType.Storage:
            # Prefer the drive's own composite reading; the per-sensor ones are
            # controller/NAND pairs and read hotter than the useful number.
            composite = None
            best = None
            for s in hw.Sensors:
                if s.SensorType != SensorType.Temperature or s.Value is None:
                    continue
                v = float(s.Value)
                name = str(s.Name)
                if v <= 0 or v > 120:
                    continue
                if "Composite" in name:
                    composite = v
                elif "Warning" not in name and "Critical" not in name:
                    best = v if best is None else max(best, v)
            val = composite if composite is not None else best
            if val is not None:
                if out["disk_temp"] is None or val > out["disk_temp"]:
                    out["disk_temp"] = val

        elif htype == HardwareType.Memory:
            for s in hw.Sensors:
                if s.SensorType == SensorType.Temperature and s.Value is not None:
                    v = float(s.Value)
                    if 0 < v < 120:
                        out["ram_temp"] = v

        # SuperIO lives on the motherboard's sub-hardware
        for sub in hw.SubHardware:
            try:
                sub.Update()
            except Exception:
                continue
            if htype == HardwareType.Motherboard or sub.HardwareType == HardwareType.Motherboard:
                self._read_superio(sub, out, SensorType)
            for subsub in sub.SubHardware:
                try:
                    subsub.Update()
                except Exception:
                    continue
                self._read_superio(subsub, out, SensorType)

    @staticmethod
    def _read_superio(hw, out: dict, SensorType):
        """Board / chipset temperature from the SuperIO chip (needs admin)."""
        for s in hw.Sensors:
            if s.SensorType != SensorType.Temperature or s.Value is None:
                continue
            v = float(s.Value)
            if v <= 0 or v > 120:
                continue
            name = str(s.Name)
            if any(k in name for k in ("Motherboard", "Mainboard", "System", "Chipset", "Main")):
                out["board_temp"] = v
            elif out["board_temp"] is None and "Temperature #1" in name:
                # On most boards the first temp channel is the board sensor;
                # "CPU Core" here is a diode that reads well below the real
                # package temperature, so it is deliberately not used.
                out["board_temp"] = v
