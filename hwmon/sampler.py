"""Sensor sampling for the hardware monitor panel.

Everything here is read-only and best-effort: any reading that the machine
cannot answer is simply absent (None) rather than zero, so the UI can show
"--" instead of inventing a value.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import os
import time
from dataclasses import dataclass, field
from typing import Optional

import psutil


# ----------------------------------------------------------------------------
#  Win32 helpers
# ----------------------------------------------------------------------------

class _MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [
        ("dwLength", wt.DWORD),
        ("dwMemoryLoad", wt.DWORD),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)


def memory_status() -> Optional[tuple[float, float]]:
    """(used_gb, total_gb) of physical memory, or None."""
    try:
        st = _MEMORYSTATUSEX()
        st.dwLength = ctypes.sizeof(st)
        if not _kernel32.GlobalMemoryStatusEx(ctypes.byref(st)):
            return None
        total = st.ullTotalPhys / (1024 ** 3)
        free = st.ullAvailPhys / (1024 ** 3)
        return (total - free, total)
    except Exception:
        return None


def uptime_hours() -> float:
    try:
        return (_kernel32.GetTickCount64() / 1000.0) / 3600.0
    except Exception:
        return 0.0


# ----------------------------------------------------------------------------
#  PDH performance counters (no cgo, no WMI)
# ----------------------------------------------------------------------------

class _PDH_ITEM(ctypes.Structure):
    _fields_ = [
        ("szName", wt.LPWSTR),
        ("FmtValue", ctypes.c_byte * 16),
    ]


class _FMT_COUNTERVALUE(ctypes.Structure):
    _fields_ = [
        ("CStatus", wt.DWORD),
        ("doubleValue", ctypes.c_double),
    ]


class _FMT_COUNTERVALUE_ITEM(ctypes.Structure):
    _fields_ = [
        ("szName", wt.LPWSTR),
        ("FmtValue", _FMT_COUNTERVALUE),
    ]


class _PDH:
    """Minimal pdh.dll wrapper.

    Performance counters are the only dependency-free way to read GPU load,
    VRAM usage, network byte rates and the real CPU clock on Windows.
    """

    PDH_FMT_DOUBLE = 0x00000200
    PDH_MORE_DATA = 0x800007D2
    PDH_NO_DATA = 0x800007D5

    _FMT_COUNTERVALUE = _FMT_COUNTERVALUE
    _FMT_COUNTERVALUE_ITEM = _FMT_COUNTERVALUE_ITEM

    def __init__(self):
        self.ok = False
        try:
            self._pdh = ctypes.WinDLL("pdh")

            self._open = self._pdh.PdhOpenQueryW
            self._open.argtypes = [wt.LPCWSTR, ctypes.c_size_t, ctypes.POINTER(wt.HANDLE)]
            self._open.restype = wt.LONG
            self._add = self._pdh.PdhAddEnglishCounterW
            self._add.argtypes = [wt.HANDLE, wt.LPCWSTR, ctypes.c_size_t, ctypes.POINTER(wt.HANDLE)]
            self._add.restype = wt.LONG

            self._add_local = self._pdh.PdhAddCounterW
            self._add_local.argtypes = [wt.HANDLE, wt.LPCWSTR, ctypes.c_size_t, ctypes.POINTER(wt.HANDLE)]
            self._add_local.restype = wt.LONG
            self._collect = self._pdh.PdhCollectQueryData
            self._collect.argtypes = [wt.HANDLE]
            self._collect.restype = wt.LONG

            self._close = self._pdh.PdhCloseQuery
            self._close.argtypes = [wt.HANDLE]
            self._close.restype = wt.LONG

            self._get = self._pdh.PdhGetFormattedCounterValue
            self._get.argtypes = [wt.HANDLE, wt.DWORD, ctypes.POINTER(wt.DWORD),
                                  ctypes.POINTER(_FMT_COUNTERVALUE)]
            self._get.restype = wt.LONG

            # LONG PdhGetFormattedCounterArrayW(PDH_HCOUNTER, DWORD dwFormat,
            #        LPDWORD lpdwBufferSize, LPDWORD lpdwBufferCount,
            #        PPDH_FMT_COUNTERVALUE_ITEM_W *ppBufferItems)
            # The last argument is a pointer to a pointer: PDH allocates the array.
            self._get_array = self._pdh.PdhGetFormattedCounterArrayW
            self._get_array.argtypes = [wt.HANDLE, wt.DWORD, ctypes.POINTER(wt.DWORD),
                                        ctypes.POINTER(wt.DWORD), ctypes.POINTER(ctypes.c_void_p)]
            self._get_array.restype = wt.LONG

            self.ok = True
        except Exception:
            self.ok = False

    def query(self, paths: list[str]):
        """Opens a query with the given counters; returns (query, [handles])."""
        if not self.ok:
            return None, []
        q = wt.HANDLE()
        if self._open(None, 0, ctypes.byref(q)) != 0:
            return None, []
        handles = []
        for p in paths:
            h = wt.HANDLE()
            rc = self._add(q, p, 0, ctypes.byref(h))
            if rc != 0:
                rc = self._add_local(q, p, 0, ctypes.byref(h))
            handles.append(h if rc == 0 else None)
        return q, handles

    def collect(self, q) -> bool:
        if not self.ok or not q:
            return False
        return self._collect(q) == 0

    def value(self, handle) -> Optional[float]:
        if not self.ok or not handle:
            return None
        val = self._FMT_COUNTERVALUE()
        try:
            rc = self._get(handle, self.PDH_FMT_DOUBLE, None, ctypes.byref(val))
            if rc != 0:
                return None
            return float(val.doubleValue)
        except Exception:
            return None

    def values(self, handle) -> list[tuple[str, float]]:
        """Reads a wildcard counter instance by instance.

        Two calls: the first asks how big the item array must be (PDH answers
        PDH_MORE_DATA and fills in the size), the second fills our buffer.
        """
        if not self.ok or not handle:
            return []
        try:
            size = wt.DWORD(0)
            count = wt.DWORD(0)
            buf = ctypes.c_void_p(0)

            rc = self._get_array(handle, self.PDH_FMT_DOUBLE, ctypes.byref(size),
                                 ctypes.byref(count), ctypes.byref(buf))
            if rc == self.PDH_MORE_DATA and size.value > 0:
                block = ctypes.create_string_buffer(size.value)
                count = wt.DWORD(0)
                rc = self._get_array(handle, self.PDH_FMT_DOUBLE, ctypes.byref(size),
                                     ctypes.byref(count), ctypes.cast(
                                         ctypes.byref(block), ctypes.POINTER(ctypes.c_void_p)))
                # The second call expects the array pointer value, not a buffer.
                if rc != 0:
                    # Retry with the pointer form PDH documents for the second pass.
                    arr = (ctypes.c_void_p * 1)(ctypes.addressof(block))
                    rc = self._get_array(handle, self.PDH_FMT_DOUBLE, ctypes.byref(size),
                                         ctypes.byref(count), arr)
                    if rc != 0:
                        return []
                    base = arr[0]
                else:
                    base = ctypes.addressof(block)
            elif rc == 0 and buf.value:
                base = buf.value
            else:
                return []

            out: list[tuple[str, float]] = []
            item_size = ctypes.sizeof(_FMT_COUNTERVALUE_ITEM)
            for i in range(count.value):
                item = _FMT_COUNTERVALUE_ITEM.from_address(base + i * item_size)
                if item.FmtValue.CStatus == 0:
                    out.append((item.szName or "", float(item.FmtValue.doubleValue)))
            return out
        except Exception:
            return []
        finally:
            try:
                if buf.value:
                    ctypes.windll.kernel32.LocalFree(ctypes.c_void_p(buf.value))
            except Exception:
                pass

    def close(self, q):
        if self.ok and q:
            try:
                self._close(q)
            except Exception:
                pass


_pdh = _PDH()


def _read_gpu_counter() -> Optional[tuple[float, float]]:
    """(load_percent, vram_bytes) summed over every GPU counter instance."""
    script = (
        r'$g=(Get-Counter "\GPU Engine(*)\Utilization Percentage" '
        r'-ErrorAction SilentlyContinue).CounterSamples;'
        r'$l=0.0; if($g){$l=($g|Measure-Object -Property CookedValue -Sum).Sum};'
        r'$m=(Get-Counter "\GPU Adapter Memory(*)\Dedicated Usage" '
        r'-ErrorAction SilentlyContinue).CounterSamples;'
        r'$v=0.0; if($m){$v=($m|Measure-Object -Property CookedValue -Sum).Sum};'
        r'"$l|$v"'
    )
    try:
        import subprocess
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True, text=True, timeout=15,
            creationflags=0x08000000)  # CREATE_NO_WINDOW
        txt = (out.stdout or "").strip()
        if "|" not in txt:
            return None
        left, right = txt.split("|", 1)
        return (float(left), float(right))
    except Exception:
        return None


# ----------------------------------------------------------------------------
#  Snapshot
# ----------------------------------------------------------------------------

@dataclass
class Snapshot:
    """One sampling tick. None means "this machine cannot answer"."""

    time: str = ""

    # CPU
    cpu_name: str = ""
    cpu_load: Optional[float] = None
    cpu_temp: Optional[float] = None
    cpu_clock_ghz: Optional[float] = None
    cpu_power: Optional[float] = None
    cpu_threads: int = 0
    cpu_cores: int = 0

    # GPU
    gpu_name: str = ""
    gpu_load: Optional[float] = None
    gpu_temp: Optional[float] = None
    gpu_hotspot: Optional[float] = None
    gpu_mem_used_mb: Optional[float] = None
    gpu_mem_total_mb: Optional[float] = None

    # Motherboard / system thermal
    board_name: str = ""
    board_temp: Optional[float] = None

    # Memory
    ram_load: Optional[float] = None
    ram_used_gb: Optional[float] = None
    ram_total_gb: Optional[float] = None
    ram_temp: Optional[float] = None

    # Storage
    disk_name: str = "C:"
    disk_free_gb: Optional[float] = None
    disk_total_gb: Optional[float] = None
    disk_temp: Optional[float] = None

    # Network
    net_name: str = ""
    net_down_bps: float = 0.0
    net_up_bps: float = 0.0

    # Battery
    battery_percent: Optional[float] = None
    battery_health: Optional[float] = None
    battery_charging: bool = False
    battery_minutes: Optional[int] = None

    # System
    os_name: str = ""
    uptime_hours: float = 0.0
    score: int = 100
    weather_temp: Optional[float] = None
    weather_kind: str = ""
    weather_city: str = ""

    processes: list = field(default_factory=list)


def _reg(path: str, name: str) -> str:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path) as k:
            v, _ = winreg.QueryValueEx(k, name)
            return str(v).strip()
    except Exception:
        return ""


class Sampler:
    """Samples the machine. Not thread-safe; call from one thread."""

    def __init__(self):
        self._net_last = None
        self._net_stamp = None
        self._proc_last: dict[int, float] = {}
        self._proc_stamp = None
        self._core_count = max(1, psutil.cpu_count(logical=True) or 1)

        # PDH queries opened once, refreshed on every tick.
        self._q_net, self._h_net = _pdh.query([
            r"\Network Interface(*)\Bytes Received/sec",
            r"\Network Interface(*)\Bytes Sent/sec",
        ])
        self._q_cpu, self._h_cpu = _pdh.query([
            r"\Processor Information(_Total)\% Processor Performance",
        ])
        # prime rate counters
        for q in (self._q_net, self._q_cpu):
            _pdh.collect(q)

        self._gpu_cache: Optional[tuple[float, float]] = None
        self._gpu_stamp = 0.0

        self._cpu_name = self._detect_cpu_name()
        self._board_name = self._detect_board_name()
        self._gpu_name = self._detect_gpu_name()
        self._base_clock = self._detect_base_clock()

        # LibreHardwareMonitor supplies what Windows counters cannot: GPU,
        # board, RAM and disk temperatures. Without it those stay None.
        from .lhm import LhmSensors
        self._lhm = LhmSensors()
        self._lhm_ok = self._lhm.start()

    # -- identity ---------------------------------------------------------
    @staticmethod
    def _detect_cpu_name() -> str:
        return _reg(r"HARDWARE\DESCRIPTION\System\CentralProcessor\0", "ProcessorNameString")

    @staticmethod
    def _detect_board_name() -> str:
        prod = _reg(r"HARDWARE\DESCRIPTION\System\BIOS", "BaseBoardProduct")
        mfg = _reg(r"HARDWARE\DESCRIPTION\System\BIOS", "BaseBoardManufacturer")
        if not prod:
            return ""
        brand = mfg
        low = mfg.lower()
        if "asustek" in low or "asus" in low:
            brand = "华硕"
        elif "gigabyte" in low:
            brand = "技嘉"
        elif "micro-star" in low or "msi" in low:
            brand = "微星"
        elif "asrock" in low:
            brand = "华擎"
        return f"{brand} {prod}".strip()

    @staticmethod
    def _detect_gpu_name() -> str:
        """Adapter name from the display-adapter class registry key."""
        try:
            import winreg
            base = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base) as k:
                for i in range(32):
                    try:
                        sub = winreg.EnumKey(k, i)
                    except OSError:
                        break
                    if len(sub) != 4 or not sub.isdigit():
                        continue
                    try:
                        with winreg.OpenKey(k, sub) as s:
                            desc = s.GetValue("DriverDesc")
                            if not desc:
                                continue
                            low = str(desc).lower()
                            if any(x in low for x in ("orayidd", "virtual", "basic display", "remote")):
                                continue
                            return str(desc).strip()
                    except OSError:
                        continue
        except Exception:
            pass
        return ""

    @staticmethod
    def _detect_base_clock() -> float:
        try:
            mhz = _reg(r"HARDWARE\DESCRIPTION\System\CentralProcessor\0", "~MHz")
            return float(int(mhz)) / 1000.0 if mhz else 0.0
        except Exception:
            return 0.0

    # -- sampling ---------------------------------------------------------
    def sample(self) -> Snapshot:
        s = Snapshot()
        s.time = time.strftime("%H:%M:%S")
        s.cpu_name = self._cpu_name
        s.board_name = self._board_name
        s.gpu_name = self._gpu_name
        s.cpu_threads = self._core_count
        s.cpu_cores = psutil.cpu_count(logical=False) or 0
        s.os_name = self._os_label()

        self._read_cpu(s)
        self._read_memory(s)
        self._read_disk(s)
        self._read_network(s)
        self._read_battery(s)
        self._read_gpu(s)
        self._read_lhm(s)
        self._read_system_temp(s)
        self._read_processes(s)

        s.uptime_hours = uptime_hours()
        s.score = compute_score(s)
        return s

    def _read_lhm(self, s: Snapshot):
        """Temperatures and clocks from LibreHardwareMonitor, when available."""
        if not self._lhm_ok:
            return
        try:
            v = self._lhm.read()
        except Exception:
            return

        if v.get("cpu_temp") is not None:
            s.cpu_temp = v["cpu_temp"]
        if v.get("cpu_clock_ghz"):
            s.cpu_clock_ghz = v["cpu_clock_ghz"]
        if v.get("cpu_power"):
            s.cpu_power = v["cpu_power"]

        if v.get("gpu_temp") is not None:
            s.gpu_temp = v["gpu_temp"]
        if v.get("gpu_hotspot") is not None:
            s.gpu_hotspot = v["gpu_hotspot"]
        if v.get("gpu_mem_used_mb") is not None:
            s.gpu_mem_used_mb = v["gpu_mem_used_mb"]
        if v.get("gpu_mem_total_mb") is not None:
            s.gpu_mem_total_mb = v["gpu_mem_total_mb"]
        if not s.gpu_name and v.get("gpu_name"):
            s.gpu_name = v["gpu_name"]

        if v.get("board_temp") is not None:
            s.board_temp = v["board_temp"]
        if v.get("ram_temp") is not None:
            s.ram_temp = v["ram_temp"]
        if v.get("disk_temp") is not None:
            s.disk_temp = v["disk_temp"]

    def _read_cpu(self, s: Snapshot):
        try:
            s.cpu_load = psutil.cpu_percent(interval=None)
        except Exception:
            s.cpu_load = None

        # Real current clock: performance ratio against the advertised base.
        clock = None
        if _pdh.collect(self._q_cpu) and self._h_cpu and self._h_cpu[0]:
            ratio = _pdh.value(self._h_cpu[0])
            if ratio and self._base_clock > 0:
                clock = self._base_clock * ratio / 100.0
        if clock is None:
            try:
                freq = psutil.cpu_freq()
                if freq and freq.current:
                    clock = freq.current / 1000.0
            except Exception:
                pass
        s.cpu_clock_ghz = clock

    def _read_memory(self, s: Snapshot):
        st = memory_status()
        if st:
            s.ram_used_gb, s.ram_total_gb = st
            if s.ram_total_gb > 0:
                s.ram_load = 100.0 * s.ram_used_gb / s.ram_total_gb

    def _read_disk(self, s: Snapshot):
        try:
            root = os.environ.get("SystemDrive", "C:") + "\\"
            u = psutil.disk_usage(root)
            s.disk_name = os.environ.get("SystemDrive", "C:")
            s.disk_total_gb = u.total / (1024 ** 3)
            s.disk_free_gb = u.free / (1024 ** 3)
        except Exception:
            pass

    def _read_network(self, s: Snapshot):
        down = up = 0.0
        if _pdh.collect(self._q_net) and len(self._h_net) >= 2:
            try:
                down = sum(v for v in (_pdh.value(self._h_net[0]),) if v) or 0.0
                up = sum(v for v in (_pdh.value(self._h_net[1]),) if v) or 0.0
            except Exception:
                pass

        if not down and not up:
            # Fallback: psutil totals, differenced.
            try:
                nic = self._pick_nic()
                if nic:
                    io = psutil.net_io_counters(pernic=True).get(nic)
                    now = time.monotonic()
                    if io and self._net_last and self._net_stamp:
                        dt = max(0.05, now - self._net_stamp)
                        down = max(0.0, (io.bytes_recv - self._net_last[0]) / dt)
                        up = max(0.0, (io.bytes_sent - self._net_last[1]) / dt)
                    if io:
                        self._net_last = (io.bytes_recv, io.bytes_sent)
                        self._net_stamp = now
                    s.net_name = nic
                    s.net_down_bps = down
                    s.net_up_bps = up
                    return
            except Exception:
                pass

        s.net_name = self._pick_nic() or ""
        s.net_down_bps = down
        s.net_up_bps = up

    @staticmethod
    def _pick_nic() -> str:
        try:
            stats = psutil.net_io_counters(pernic=True)
            best = ("", -1)
            for name, io in stats.items():
                low = name.lower()
                if any(k in low for k in ("vmware", "virtual", "loopback", "tap",
                                          "wsl", "hyper-v", "vethernet", "bluetooth")):
                    continue
                total = io.bytes_recv + io.bytes_sent
                if total > best[1]:
                    best = (name, total)
            return best[0]
        except Exception:
            return ""

    def _read_battery(self, s: Snapshot):
        try:
            bat = psutil.sensors_battery()
            if bat is None:
                return
            s.battery_percent = float(bat.percent)
            s.battery_charging = bool(bat.power_plugged)
            if bat.secsleft and bat.secsleft > 0:
                s.battery_minutes = int(bat.secsleft / 60)
        except Exception:
            pass

    def _read_gpu(self, s: Snapshot):
        r"""GPU load and VRAM.

        The wildcard counters (\GPU Engine(*)\Utilization Percentage and
        \GPU Adapter Memory(*)\Dedicated Usage) expose hundreds of instances,
        and PDH's array API is awkward from ctypes, so Get-Counter does the
        summation. The call is cached because it spawns a shell.
        """
        now = time.monotonic()
        if self._gpu_cache is None or (now - self._gpu_stamp) > 3.0:
            self._gpu_cache = _read_gpu_counter()
            self._gpu_stamp = now

        if not self._gpu_cache:
            return
        load, vram = self._gpu_cache
        s.gpu_load = load
        if vram and vram > 0:
            s.gpu_mem_used_mb = vram / (1024 * 1024)

    def _read_system_temp(self, s: Snapshot):
        """WMI thermal zones; absent on most desktops."""
        try:
            c = ctypes.windll.kernel32
            pass
        except Exception:
            pass
        try:
            import subprocess
            out = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "(Get-CimInstance -Namespace root/wmi -ClassName MSAcpi_ThermalZoneTemperature "
                 "-ErrorAction SilentlyContinue | Measure-Object -Property CurrentTemperature "
                 "-Average).Average"],
                capture_output=True, text=True, timeout=4,
                creationflags=0x08000000)
            txt = (out.stdout or "").strip()
            if txt:
                kelvin = float(txt) / 10.0
                celsius = kelvin - 273.15
                if 0 < celsius < 150:
                    s.cpu_temp = celsius
        except Exception:
            pass

    def _read_processes(self, s: Snapshot):
        now = time.monotonic()
        elapsed = 0.0 if self._proc_stamp is None else (now - self._proc_stamp)
        self._proc_stamp = now

        groups: dict[str, list] = {}
        current: dict[int, float] = {}
        try:
            for p in psutil.process_iter(["pid", "name", "memory_info", "cpu_times"]):
                try:
                    info = p.info
                    name = info.get("name") or "?"
                    mem = info.get("memory_info")
                    mb = (mem.rss / (1024 ** 2)) if mem else 0.0
                    cpu_times = info.get("cpu_times")
                    total = (cpu_times.user + cpu_times.system) if cpu_times else 0.0
                    pid = info.get("pid")

                    row = groups.setdefault(name, [0.0, 0.0])
                    row[0] += mb

                    if total > 0 and pid is not None:
                        current[pid] = total
                        prev = self._proc_last.get(pid)
                        if elapsed > 0.2 and prev is not None:
                            pct = (total - prev) / elapsed / self._core_count * 100.0
                            if pct > 0:
                                row[1] += pct
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue
        except Exception:
            pass

        self._proc_last = current
        rows = sorted(groups.items(), key=lambda kv: kv[1][0], reverse=True)[:5]
        s.processes = [{"name": n, "mem_mb": v[0], "cpu": v[1]} for n, v in rows]

    @staticmethod
    def _os_label() -> str:
        try:
            v = os.sys.getwindowsversion()
            if v.major >= 10 and v.build >= 22000:
                rel = "24H2" if v.build >= 26100 else "23H2" if v.build >= 22631 else "22H2"
                return f"Windows 11 {rel}"
            return "Windows 10"
        except Exception:
            return "Windows"


# ----------------------------------------------------------------------------
#  Health score
# ----------------------------------------------------------------------------

def compute_score(s: Snapshot) -> int:
    """100 down to 1; dimensions the machine cannot report cost nothing."""
    score = 100.0

    if s.cpu_load is not None:
        score -= max(0.0, s.cpu_load - 55) * 0.35
    if s.gpu_load is not None:
        score -= max(0.0, s.gpu_load - 60) * 0.18
    if s.ram_load is not None:
        score -= max(0.0, s.ram_load - 70) * 0.5
    if s.cpu_temp is not None:
        score -= max(0.0, s.cpu_temp - 62) * 0.55
    if s.gpu_temp is not None:
        score -= max(0.0, s.gpu_temp - 68) * 0.35
    if s.board_temp is not None:
        score -= max(0.0, s.board_temp - 50) * 0.12

    if s.disk_free_gb is not None and s.disk_total_gb:
        used_pct = 100.0 * (1 - s.disk_free_gb / s.disk_total_gb)
        if used_pct > 88:
            score -= (used_pct - 88) * 0.9

    return max(1, min(100, int(round(score))))
