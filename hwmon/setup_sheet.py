"""First-run setup sheet: offers to install the temperature driver."""

from __future__ import annotations

from typing import Optional

from PIL import Image, ImageDraw

from . import render as R
from .window import LayeredWindow


class SetupSheet:
    """A small glass dialog with one primary action."""

    WIDTH = 420
    SHADOW = 24

    def __init__(self, scale: float = 1.0):
        self.scale = max(1.0, min(3.0, scale))
        self.hits: dict[str, tuple[int, int, int, int]] = {}
        self.status = ""

    def s(self, v: float) -> int:
        return int(round(v * self.scale))

    def body_size(self) -> tuple[int, int]:
        return (self.s(self.WIDTH), self.s(214))

    def hit_at(self, wx: int, wy: int) -> str:
        x, y = wx - self.SHADOW, wy - self.SHADOW
        for name, (hx, hy, hw, hh) in self.hits.items():
            if hx <= x <= hx + hw and hy <= y <= hy + hh:
                return name
        return ""

    def render(self) -> Image.Image:
        bw, bh = self.body_size()
        m = self.SHADOW
        img = Image.new("RGBA", (bw + m * 2, bh + m * 2), (0, 0, 0, 0))
        radius = self.s(24)

        R.draw_outer_shadow(img, (m, m, m + bw, m + bh), radius, int(m * 0.8), 0.8)
        glass = R.make_glass_body(None, (bw, bh), radius,
                                  tint=(10, 16, 30), tint_strength=0.34, opacity=0.88)
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
        f_body = R._load_font(self.s(12))
        f_small = R._load_font(self.s(10.5))
        f_btn = R._load_font(self.s(12), bold=True)

        y = pad
        R.draw_text(img, d, "安装温度传感器驱动", f_title, R.TEXT_PRIMARY, (pad, y))
        y += self.s(28)

        lines = [
            "CPU 与主板温度需要 PawnIO 内核驱动（开源，",
            "LibreHardwareMonitor 官方方案）。",
            "",
            "安装需要一次 UAC 管理员授权，约 10 秒。",
        ]
        for line in lines:
            R.draw_text(img, d, line, f_body, R.TEXT_SECONDARY, (pad, y))
            y += self.s(19)

        if self.status:
            y += self.s(4)
            R.draw_text(img, d, self.status, f_small, R.ACCENT_YELLOW + (255,), (pad, y))

        # buttons
        by = img.height - pad - self.s(34)
        bh = self.s(32)

        skip_w = self.s(78)
        skip_x = img.width - pad - skip_w
        self.hits["skip"] = (skip_x, by, skip_w, bh)
        d.rounded_rectangle([skip_x, by, skip_x + skip_w, by + bh],
                            radius=self.s(8), fill=(255, 255, 255, 26),
                            outline=(255, 255, 255, 60), width=1)
        R.draw_text(img, d, "稍后", f_btn, R.TEXT_SECONDARY,
                    (skip_x + skip_w // 2, by + self.s(8)), align="center")

        go_w = self.s(112)
        go_x = skip_x - self.s(10) - go_w
        self.hits["install"] = (go_x, by, go_w, bh)
        d.rounded_rectangle([go_x, by, go_x + go_w, by + bh],
                            radius=self.s(8),
                            fill=R.ACCENT_BLUE + (220,),
                            outline=(255, 255, 255, 90), width=1)
        R.draw_text(img, d, "立即安装", f_btn, R.TEXT_PRIMARY,
                    (go_x + go_w // 2, by + self.s(8)), align="center", shadow=False)
