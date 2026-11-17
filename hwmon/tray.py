"""Tray icon with a live numeric face, and its context menu."""

from __future__ import annotations

import threading
import time
from typing import Callable, Optional

import pystray
from PIL import Image, ImageDraw

from .sampler import Snapshot

# icon face choices, in menu order
FIELD_CPU_LOAD = "cpu_load"
FIELD_GPU_LOAD = "gpu_load"
FIELD_CPU_TEMP = "cpu_temp"
FIELD_GPU_TEMP = "gpu_temp"
FIELD_BOARD_TEMP = "board_temp"
FIELD_RAM_LOAD = "ram_load"
FIELD_SCORE = "score"

FIELD_LABELS = [
    (FIELD_CPU_LOAD, "CPU 占用"),
    (FIELD_GPU_LOAD, "GPU 占用"),
    (FIELD_CPU_TEMP, "CPU 温度"),
    (FIELD_GPU_TEMP, "GPU 温度"),
    (FIELD_BOARD_TEMP, "主板温度"),
    (FIELD_RAM_LOAD, "内存占用"),
    (FIELD_SCORE, "健康评分"),
]


def _color_for(value: Optional[float], is_temp: bool) -> tuple[int, int, int]:
    if value is None:
        return (110, 118, 136)
    if is_temp:
        if value < 55:
            return (48, 209, 88)
        if value < 70:
            return (255, 214, 10)
        if value < 82:
            return (255, 159, 10)
        return (255, 69, 58)
    if value < 55:
        return (48, 209, 88)
    if value < 78:
        return (255, 214, 10)
    if value < 92:
        return (255, 159, 10)
    return (255, 69, 58)


class TrayIcon:
    def __init__(self, on_toggle: Callable, on_settings: Callable,
                 on_details: Callable, on_exit: Callable,
                 on_field: Callable[[str], None]):
        self.field = FIELD_CPU_LOAD
        self._on_toggle = on_toggle
        self._on_settings = on_settings
        self._on_details = on_details
        self._on_exit = on_exit
        self._on_field = on_field
        self._snap: Optional[Snapshot] = None
        self._icon: Optional[pystray.Icon] = None
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    # -- icon artwork -----------------------------------------------------
    def _render_icon(self) -> Image.Image:
        size = 64
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)

        value, is_temp = self._current_value()
        if value is None:
            text, color = "--", (110, 118, 136)
        else:
            if self.field == FIELD_SCORE:
                text = str(int(value))
            else:
                text = str(int(round(value)))
            color = _color_for(value, is_temp)

        font_size = 40 if len(text) >= 3 else 46 if len(text) == 2 else 52
        font = None
        for path in (r"C:\Windows\Fonts\msyhbd.ttc", r"C:\Windows\Fonts\segoeuib.ttf"):
            try:
                from PIL import ImageFont
                font = ImageFont.truetype(path, font_size)
                break
            except Exception:
                continue

        if font is None:
            from PIL import ImageFont
            font = ImageFont.load_default()

        box = d.textbbox((0, 0), text, font=font)
        tw, th = box[2] - box[0], box[3] - box[1]
        d.text(((size - tw) / 2 - box[0], (size - th) / 2 - box[1]), text,
               font=font, fill=color + (255,))
        return img

    def _current_value(self) -> tuple[Optional[float], bool]:
        s = self._snap
        if s is None:
            return (None, False)
        mapping = {
            FIELD_CPU_LOAD: (s.cpu_load, False),
            FIELD_GPU_LOAD: (s.gpu_load, False),
            FIELD_CPU_TEMP: (s.cpu_temp, True),
            FIELD_GPU_TEMP: (s.gpu_temp, True),
            FIELD_BOARD_TEMP: (s.board_temp, True),
            FIELD_RAM_LOAD: (s.ram_load, False),
            FIELD_SCORE: (float(s.score), False),
        }
        return mapping.get(self.field, (None, False))

    # -- menu -------------------------------------------------------------
    def _build_menu(self):
        items = [
            pystray.MenuItem("显示面板", lambda: self._on_toggle(), default=True),
            pystray.Menu.SEPARATOR,
        ]

        field_items = []
        for key, label in FIELD_LABELS:
            field_items.append(pystray.MenuItem(
                label,
                (lambda k: (lambda: self._set_field(k)))(key),
                checked=(lambda k: (lambda item: self.field == k))(key),
                radio=True))
        items.append(pystray.MenuItem("托盘图标显示", pystray.Menu(*field_items)))

        items += [
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("硬件详情", lambda: self._on_details()),
            pystray.MenuItem("设置", lambda: self._on_settings()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("退出", lambda: self._on_exit()),
        ]
        return pystray.Menu(*items)

    def _set_field(self, key: str):
        self.field = key
        self.refresh()
        self._on_field(key)

    # -- public -----------------------------------------------------------
    def start(self):
        """Runs the tray icon on its own thread.

        ``run_detached`` needs a Tk/message pump that this process does not
        have, so the icon is created and run explicitly on a worker thread.
        pystray marks the icon visible itself once run() starts, so no extra
        visibility handling is needed here.
        """
        if self._icon is not None:
            return

        self._icon = pystray.Icon(
            "hwmon",
            self._render_icon(),
            "硬件监控",
            menu=self._build_menu(),
        )

        self._thread = threading.Thread(target=self._run_icon, name="tray", daemon=True)
        self._thread.start()

        # Give the worker a moment so the icon exists before the first update.
        for _ in range(40):
            if getattr(self._icon, "visible", False):
                break
            time.sleep(0.05)

    def _run_icon(self):
        try:
            self._icon.run()
        except Exception:
            self._icon = None

    def refresh(self):
        if self._icon is None:
            return
        try:
            self._icon.icon = self._render_icon()
        except Exception:
            pass

    def update(self, snap: Snapshot):
        with self._lock:
            self._snap = snap
        self.refresh()
        if self._icon is not None:
            try:
                self._icon.title = (
                    f"CPU {snap.cpu_load:.0f}% " if snap.cpu_load is not None else "CPU --"
                ) + (f" · GPU {snap.gpu_load:.0f}%" if snap.gpu_load is not None else "") \
                  + f" · 评分 {snap.score}"
            except Exception:
                pass

    def stop(self):
        if self._icon is not None:
            try:
                self._icon.stop()
            except Exception:
                pass
            self._icon = None
