"""Application entry point: tray icon, sampler thread and the glass panel."""

from __future__ import annotations

import ctypes
import os
import threading
import time

from . import hardware, render
from .panel import Panel
from .sampler import Sampler
from .tray import TrayIcon
from .window import LayeredWindow, user32, wt


def _dpi_scale() -> float:
    try:
        user32.SetProcessDPIAware()
        dc = user32.GetDC(None)
        dpi = ctypes.WinDLL("gdi32").GetDeviceCaps(dc, 88)  # LOGPIXELSX
        user32.ReleaseDC(None, dc)
        return max(1.0, min(3.0, dpi / 96.0))
    except Exception:
        return 1.0


class App:
    def __init__(self):
        self.scale = _dpi_scale()
        self.panel = Panel(scale=self.scale)
        self.sampler = Sampler()
        self.window = None          # created lazily in show_panel
        self.panel_window = None
        self.details_window = None
        self.visible = False
        self._running = True
        self._last_snap = None
        self.setup_window = None

        self.tray = TrayIcon(
            on_toggle=self.toggle_panel,
            on_settings=self.show_settings,
            on_details=self.show_details,
            on_exit=self.quit,
            on_field=lambda _k: self.render_and_push())

    # -- panel ------------------------------------------------------------
    def _panel_position(self) -> tuple[int, int]:
        """Bottom-right of the work area, tucked against the taskbar."""
        r = wt.RECT()
        user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(r), 0)  # SPI_GETWORKAREA
        w, h = self.panel.window_size()
        margin = render.SHADOW_MARGIN
        x = r.right - w + margin - 6
        y = r.bottom - h + margin - 6
        return (max(r.left, x), max(r.top, y))

    def toggle_panel(self):
        if self.visible:
            self.hide_panel()
        else:
            self.show_panel()

    def show_panel(self):
        # A click that closes the panel leaves the window destroyed; recreate on demand.
        if self.panel_window is not None and self.panel_window.alive():
            self.panel_window.show()
            self.render_and_push()
            self.visible = True
            return

        w, h = self.panel.window_size()
        x, y = self._panel_position()

        self.panel_window = LayeredWindow("panel")
        self.panel_window.on_click = self._on_panel_click
        self.panel_window.on_move = self._on_panel_hover
        self.panel_window.on_leave = self._on_panel_leave
        self.panel_window.on_drag_end = self._on_panel_drag_end
        self.panel_window.create(x, y, w, h)

        # Wait briefly for the first sample: painting an empty panel then
        # filling it in looks like a glitch.
        deadline = time.time() + 3.0
        while self._last_snap is None and time.time() < deadline:
            time.sleep(0.1)

        self.render_and_push()
        self.panel_window.show()
        self.visible = True

    def hide_panel(self):
        if self.panel_window:
            self.panel_window.hide()
        self.visible = False

    def render_and_push(self):
        if not self.visible or self.panel_window is None:
            return
        try:
            img = self.panel.render()
            self.panel_window.set_image(img)
        except Exception:
            pass

    def _on_panel_click(self, x, y):
        """Hit-test the exported rectangles (window coords, shadow margin included)."""
        key = self.panel.hover_at(x, y)
        if not key:
            box = self.panel.hits.get("info")
            if box:
                off = self.panel.hit_offset
                if (box[0] <= x - off <= box[0] + box[2]
                        and box[1] <= y - off <= box[1] + box[3]):
                    self.show_details()
            return

        if key == "close":
            self.hide_panel()
        elif key == "min":
            self.hide_panel()
        elif key == "gear":
            self.show_settings()
        elif key == "pin":
            self.panel.collapsed = not self.panel.collapsed

    def _on_panel_hover(self, x, y):
        key = self.panel.hover_at(x, y)
        if key != self.panel.hover:
            self.panel.hover = key
            self.render_and_push()

    def _on_panel_leave(self):
        if self.panel.hover:
            self.panel.hover = ""
            self.render_and_push()

    def _on_panel_drag_end(self):
        # The panel moved; nothing to do beyond keeping it on top.
        pass

    # -- inventory / details ---------------------------------------------
    def _load_inventory(self):
        try:
            self.panel.info = hardware.collect()
            self.render_and_push()
        except Exception:
            pass

    def show_details(self):
        """Opens the hardware inventory sheet as its own glass window."""
        from .details import DetailsPanel

        if self.details_window is not None and self.details_window.alive():
            self.details_window.destroy()
            self.details_window = None
            return

        sheet = DetailsPanel(self.panel.info, self.scale)
        w, h = sheet.render().size

        # centre it on the work area
        r = wt.RECT()
        user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(r), 0)
        x = r.left + (r.right - r.left - w) // 2
        y = r.top + (r.bottom - r.top - h) // 2

        win = LayeredWindow("details")
        win.on_click = lambda px, py: self._on_details_click(sheet, win, px, py)
        win.create(x, y, w, h)
        win.set_image(sheet.render())
        win.show()
        self.details_window = win

    # -- driver onboarding ------------------------------------------------
    def maybe_offer_driver(self):
        """Shows the install sheet the first time, when the driver is missing."""
        from . import driver

        if driver.is_installed():
            return
        if os.path.exists(self._driver_declined_flag()):
            return
        self.show_driver_sheet()

    def _driver_declined_flag(self) -> str:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(base, ".driver_declined")

    def show_driver_sheet(self):
        from .setup_sheet import SetupSheet

        if self.setup_window is not None and self.setup_window.alive():
            return

        sheet = SetupSheet(self.scale)
        w, h = sheet.render().size

        r = wt.RECT()
        user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(r), 0)
        x = r.left + (r.right - r.left - w) // 2
        y = r.top + (r.bottom - r.top - h) // 2

        win = LayeredWindow("setup")
        win.on_click = lambda px, py: self._on_setup_click(sheet, win, px, py)
        win.create(x, y, w, h)
        win.set_image(sheet.render())
        win.show()
        self.setup_window = win

    def _on_setup_click(self, sheet, win, px, py):
        from . import driver

        key = sheet.hit_at(px, py)
        if not key:
            return

        if key == "skip":
            try:
                with open(self._driver_declined_flag(), "w") as f:
                    f.write("1")
            except Exception:
                pass
            win.destroy()
            self.setup_window = None
            return

        if key == "install":
            sheet.status = "正在安装，请在弹出的窗口中确认…"
            win.set_image(sheet.render())
            ok, msg = driver.install()
            sheet.status = msg
            win.set_image(sheet.render())
            if ok:
                time.sleep(1.5)
                win.destroy()
                self.setup_window = None

    def _on_details_click(self, sheet, win, px, py):
        if sheet.hit_at(px, py) == "close":
            win.destroy()
            self.details_window = None

    def show_settings(self):
        pass

    # -- sampling ---------------------------------------------------------
    def _sample_loop(self):
        # Prime the rate counters; PDH needs two reads before it reports a rate,
        # and warm up the process CPU deltas the same way.
        try:
            self.sampler.sample()
        except Exception:
            pass
        time.sleep(1.0)

        tick = 0
        while self._running:
            try:
                snap = self.sampler.sample()
                self._last_snap = snap
                self.panel.update(snap)
                self.tray.update(snap)
                self.render_and_push()

                # A NOACTIVATE window can be pushed behind other apps; nudge it
                # back to the top every few ticks without stealing focus.
                tick += 1
                if tick % 3 == 0:
                    self._raise_panel()
            except Exception:
                pass
            time.sleep(1.0)

    def _raise_panel(self):
        win = self.panel_window
        if win is None or not win.alive() or not self.visible:
            return
        try:
            HWND_TOPMOST = wt.HWND(-1)
            SWP_NOMOVE = 0x0002
            SWP_NOSIZE = 0x0001
            SWP_NOACTIVATE = 0x0010
            x, y = win.get_position()
            user32.SetWindowPos(win._hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                                SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)
        except Exception:
            pass

    # -- lifecycle --------------------------------------------------------
    def run(self):
        # One sampling thread, no competing message loops: pystray runs on its
        # own thread and the Win32 loop below owns the panel window.
        threading.Thread(target=self._load_inventory, daemon=True).start()

        try:
            self._last_snap = self.sampler.sample()
            self.panel.update(self._last_snap)
        except Exception:
            pass

        threading.Thread(target=self._sample_loop, daemon=True).start()
        self.tray.start()
        self.show_panel()
        # After the panel is up, offer the driver if it is missing.
        threading.Thread(target=self._driver_prompt_later, daemon=True).start()

        msg = wt.MSG()
        while self._running:
            got = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if got == 0 or got == -1:
                break
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    def _driver_prompt_later(self):
        time.sleep(2.0)
        try:
            self.maybe_offer_driver()
        except Exception:
            pass

    def quit(self):
        self._running = False
        try:
            self.tray.stop()
        except Exception:
            pass
        try:
            if self.panel_window:
                self.panel_window.destroy()
        except Exception:
            pass


def main():
    app = App()
    try:
        app.run()
    except KeyboardInterrupt:
        app.quit()


if __name__ == "__main__":
    main()
