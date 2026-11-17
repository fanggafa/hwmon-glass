"""The hardware details sheet, drawn with the same glass material."""

from __future__ import annotations

from typing import Optional

from PIL import Image, ImageDraw

from . import render as R
from .hardware import HardwareInfo
from .window import LayeredWindow


class DetailsPanel:
    """A taller glass sheet listing the full machine inventory."""

    WIDTH = 520
    PAD = 22
    ROW_H = 26
    SECTION_GAP = 18
    SHADOW = 26

    def __init__(self, info: Optional[HardwareInfo], scale: float = 1.0):
        self.info = info or HardwareInfo()
        self.scale = max(1.0, min(3.0, scale))
        self.hits: dict[str, tuple[int, int, int, int]] = {}

    def s(self, v: float) -> int:
        return int(round(v * self.scale))

    # -- layout -----------------------------------------------------------
    def hit_at(self, wx: int, wy: int) -> str:
        """Maps a window-space click to a control name (accounts for the shadow margin)."""
        x, y = wx - self.SHADOW, wy - self.SHADOW
        for name, (hx, hy, hw, hh) in self.hits.items():
            if hx <= x <= hx + hw and hy <= y <= hy + hh:
                return name
        return ""

    def _rows(self) -> list[tuple[str, list[str]]]:
        info = self.info
        out: list[tuple[str, list[str]]] = []
        out.append(("处理器", [info.cpu] if info.cpu else []))
        out.append(("主板", [info.board] if info.board else []))
        out.append(("内存", [info.memory] if info.memory else []))
        out.append(("显卡", info.gpus))
        out.append(("显示器", info.displays))
        out.append(("硬盘", info.disks))
        out.append(("声卡", info.sound))
        out.append(("网卡", info.net))
        return [(label, [v for v in values if v]) for label, values in out]

    def body_size(self) -> tuple[int, int]:
        rows = self._rows()
        h = self.s(self.PAD) + self.s(58) + self.s(34)
        for _label, values in rows:
            if not values:
                continue
            h += self.s(self.SECTION_GAP) + len(values) * self.s(self.ROW_H)
        h += self.s(self.PAD)
        return (self.s(self.WIDTH), h)

    # -- painting ---------------------------------------------------------
    def render(self) -> Image.Image:
        body_w, body_h = self.body_size()
        margin = self.SHADOW
        img = Image.new("RGBA", (body_w + margin * 2, body_h + margin * 2), (0, 0, 0, 0))

        body = (margin, margin, margin + body_w, margin + body_h)
        radius = self.s(26)

        R.draw_outer_shadow(img, body, radius, int(margin * 0.8), 0.8)

        glass = R.make_glass_body(None, (body_w, body_h), radius,
                                  tint=(10, 16, 30), tint_strength=0.34, opacity=0.80)
        img.alpha_composite(glass, (margin, margin))

        content = Image.new("RGBA", (body_w, body_h), (0, 0, 0, 0))
        self._paint(content)
        img.alpha_composite(content, (margin, margin))

        R.draw_specular_rim(img, (margin, margin, margin + body_w, margin + body_h), radius)
        return img

    def _paint(self, img: Image.Image):
        d = ImageDraw.Draw(img)
        x = self.s(self.PAD)
        w = img.width - self.s(self.PAD) * 2
        y = self.s(self.PAD)

        f_title = R._load_font(self.s(19), bold=True)
        f_model = R._load_font(self.s(12))
        f_label = R._load_font(self.s(12))
        f_value = R._load_font(self.s(13))

        R.draw_text(img, d, "硬件信息", f_title, R.TEXT_PRIMARY, (x, y))
        if self.info.model:
            R.draw_text(img, d, self.info.model, f_model, R.TEXT_SECONDARY,
                        (x, y + self.s(27)))

        # close button
        bs = self.s(28)
        bx = img.width - self.s(self.PAD) - bs
        self.hits["close"] = (bx, y - self.s(4), bs, bs)
        cx, cy = bx + bs / 2, y - self.s(4) + bs / 2
        col = R.TEXT_SECONDARY
        lw = max(1, int(1.6 * self.scale))
        d.line([cx - 5 * self.scale, cy - 5 * self.scale,
                cx + 5 * self.scale, cy + 5 * self.scale], fill=col, width=lw)
        d.line([cx + 5 * self.scale, cy - 5 * self.scale,
                cx - 5 * self.scale, cy + 5 * self.scale], fill=col, width=lw)

        y += self.s(58)

        # summary chips
        chips = []
        if self.info.os_summary:
            chips.append(self.info.os_summary)
        if self.info.memory:
            chips.append(self.info.memory.split("（")[0])
        if self.info.gpus:
            chips.append(self.info.gpus[0])

        chip_x = x
        f_chip = R._load_font(self.s(11))
        for text in chips:
            tw = R.text_size(d, text, f_chip)[0]
            cw = tw + self.s(18)
            if chip_x + cw > x + w:
                break
            d.rounded_rectangle([chip_x, y, chip_x + cw, y + self.s(24)],
                                radius=self.s(12), fill=(255, 255, 255, 34),
                                outline=(255, 255, 255, 70), width=1)
            R.draw_text(img, d, text, f_chip, R.TEXT_SECONDARY,
                        (chip_x + cw // 2, y + self.s(5)), align="center")
            chip_x += cw + self.s(8)

        y += self.s(34)

        # rows
        for label, values in self._rows():
            if not values:
                continue
            y += self.s(self.SECTION_GAP)

            # section rule
            d.line([x, y - self.s(8), x + w, y - self.s(8)], fill=(255, 255, 255, 34), width=1)

            for i, value in enumerate(values):
                if i == 0:
                    R.draw_text(img, d, label, f_label, (150, 170, 195, 255), (x, y))
                value = R.fit_text(d, value, f_value, w - self.s(76))
                R.draw_text(img, d, value, f_value, R.TEXT_PRIMARY, (x + self.s(76), y))
                y += self.s(self.ROW_H)
