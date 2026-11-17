"""Settings sheet: glass-styled, drawn with the same primitives as the panel."""

from __future__ import annotations


from PIL import Image, ImageDraw

from . import render as R
from .settings import Settings


class SettingsSheet:
    """A single-page settings panel with real interactive controls."""

    WIDTH = 420
    SHADOW = 24
    ROW_H = 72

    def __init__(self, settings: Settings, scale: float = 1.0):
        self.settings = settings
        self.scale = max(1.0, min(3.0, scale))
        self.hits: dict[str, tuple[int, int, int, int]] = {}
        # drag state for the opacity slider
        self._drag_slider = False

    def s(self, v: float) -> int:
        return int(round(v * self.scale))

    def body_size(self) -> tuple[int, int]:
        # title block + 4 setting rows + button row
        h = self.s(52) + self.s(self.ROW_H) * 4 + self.s(52)
        return (self.s(self.WIDTH), h)

    def hit_at(self, wx: int, wy: int) -> str:
        x, y = wx - self.SHADOW, wy - self.SHADOW
        for name, (hx, hy, hw, hh) in self.hits.items():
            if hx <= x <= hx + hw and hy <= y <= hy + hh:
                return name
        return ""

    # -- painting ---------------------------------------------------------
    def render(self) -> Image.Image:
        bw, bh = self.body_size()
        m = self.SHADOW
        img = Image.new("RGBA", (bw + m * 2, bh + m * 2), (0, 0, 0, 0))
        radius = self.s(24)

        R.draw_outer_shadow(img, (m, m, m + bw, m + bh), radius, int(m * 0.8), 0.8)
        glass = R.make_glass_body(None, (bw, bh), radius,
                                  tint=(10, 16, 30), tint_strength=0.34, opacity=0.92)
        img.alpha_composite(glass, (m, m))

        content = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
        self._paint(content)
        img.alpha_composite(content, (m, m))

        R.draw_specular_rim(img, (m, m, m + bw, m + bh), radius)
        return img

    def _paint(self, img: Image.Image):
        d = ImageDraw.Draw(img)
        pad = self.s(20)
        w = img.width - pad * 2

        f_title = R._load_font(self.s(16), bold=True)
        f_label = R._load_font(self.s(12))
        f_value = R._load_font(self.s(11))
        f_btn = R._load_font(self.s(12), bold=True)

        y = pad
        R.draw_text(img, d, "设置", f_title, R.TEXT_PRIMARY, (pad, y))

        # close
        bs = self.s(26)
        bx = img.width - pad - bs
        self.hits["close"] = (bx, y - self.s(2), bs, bs)
        cx, cy = bx + bs / 2, y - self.s(2) + bs / 2
        col = R.TEXT_SECONDARY
        lw = max(1, int(1.5 * self.scale))
        d.line([cx - 5 * self.scale, cy - 5 * self.scale,
                cx + 5 * self.scale, cy + 5 * self.scale], fill=col, width=lw)
        d.line([cx + 5 * self.scale, cy - 5 * self.scale,
                cx - 5 * self.scale, cy + 5 * self.scale], fill=col, width=lw)

        y += self.s(40)

        # Every row owns a fixed slice: label on the first line, the control
        # below it. Heights are fixed so nothing can overlap the next row.
        row = self.s(self.ROW_H)

        # 1. opacity slider
        self._row(img, d, pad, y, w, "面板透明度",
                  f"{int(self.settings.opacity * 100)}%", f_label, f_value)
        self._slider(img, d, pad, y + self.s(22), w, self.settings.opacity)
        self.hits["opacity"] = (pad, y + self.s(17), w, self.s(16))
        y += row

        # 2. sample interval
        self._row(img, d, pad, y, w, "刷新间隔", f"{self.settings.interval:.1f} 秒",
                  f_label, f_value)
        self._stepper(img, d, pad, y + self.s(21), w, "interval")
        y += row

        # 3. autostart toggle
        self._row(img, d, pad, y, w, "开机自动启动",
                  "已开启" if self.settings.autostart else "已关闭", f_label, f_value)
        self._toggle(img, d, img.width - pad - self.s(42), y + self.s(24),
                     self.s(42), self.settings.autostart)
        self.hits["autostart"] = (img.width - pad - self.s(50), y + self.s(16),
                                  self.s(56), self.s(34))
        y += row

        # 4. tray face (changed from the tray menu, shown read-only here)
        face = {
            "cpu_load": "CPU 占用", "gpu_load": "GPU 占用",
            "cpu_temp": "CPU 温度", "gpu_temp": "GPU 温度",
            "board_temp": "主板温度", "ram_load": "内存占用",
            "score": "健康评分",
        }.get(self.settings.tray_field, "CPU 占用")
        self._row(img, d, pad, y, w, "托盘图标显示", face, f_label, f_value)

        # save button, pinned to the bottom
        by = img.height - pad - self.s(32)
        bw_btn = self.s(104)
        bx_btn = img.width - pad - bw_btn
        self.hits["save"] = (bx_btn, by, bw_btn, self.s(32))
        d.rounded_rectangle([bx_btn, by, bx_btn + bw_btn, by + self.s(32)],
                            radius=self.s(8), fill=R.ACCENT_BLUE + (220,),
                            outline=(255, 255, 255, 90), width=1)
        R.draw_text(img, d, "保存并关闭", f_btn, R.TEXT_PRIMARY,
                    (bx_btn + bw_btn // 2, by + self.s(8)), align="center", shadow=False)

    def _row(self, img, d, x, y, w, label, value, f_label, f_value):
        R.draw_text(img, d, label, f_label, R.TEXT_PRIMARY, (x, y))
        R.draw_text(img, d, value, f_value, R.TEXT_SECONDARY,
                    (x + w, y + self.s(1)), align="right")

    def _slider(self, img, d, x, y, w, frac):
        h = self.s(5)
        d.rounded_rectangle([x, y, x + w, y + h], radius=h // 2, fill=(255, 255, 255, 40))
        fw = max(h, int(w * max(0.0, min(1.0, frac))))
        d.rounded_rectangle([x, y, x + fw, y + h], radius=h // 2,
                            fill=R.ACCENT_BLUE + (255,))
        knob = self.s(6)
        d.ellipse([x + fw - knob, y + h / 2 - knob, x + fw + knob, y + h / 2 + knob],
                  fill=(255, 255, 255, 255))

    def _stepper(self, img, d, x, y, w, key):
        bs = self.s(26)
        # minus on the left, plus on the right of a centred readout
        mx = x
        px = x + w - bs
        for bx, glyph, name in ((mx, "-", key + "_dec"), (px, "+", key + "_inc")):
            d.rounded_rectangle([bx, y, bx + bs, y + bs], radius=self.s(6),
                                fill=(255, 255, 255, 30),
                                outline=(255, 255, 255, 60), width=1)
            cx, cy = bx + bs / 2, y + bs / 2
            lw = max(1, int(1.6 * self.scale))
            d.line([cx - 5 * self.scale, cy, cx + 5 * self.scale, cy],
                   fill=R.TEXT_PRIMARY, width=lw)
            if glyph == "+":
                d.line([cx, cy - 5 * self.scale, cx, cy + 5 * self.scale],
                       fill=R.TEXT_PRIMARY, width=lw)
            self.hits[name] = (bx, y, bs, bs)

    def _toggle(self, img, d, x, y, w, on):
        h = self.s(22)
        track = R.ACCENT_GREEN + (230,) if on else (255, 255, 255, 40)
        d.rounded_rectangle([x, y, x + w, y + h], radius=h // 2, fill=track)
        r = h / 2 - self.s(2)
        cx = x + (w - h / 2 - self.s(2)) if on else x + (h / 2 + self.s(2))
        d.ellipse([cx - r, y + h / 2 - r, cx + r, y + h / 2 + r],
                  fill=(255, 255, 255, 255))
