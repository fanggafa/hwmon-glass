"""The panel: a vertical column of glass cards, rendered to one ARGB image."""

from __future__ import annotations

from typing import Optional

from PIL import Image, ImageDraw, ImageFilter

from . import render as R
from .hardware import HardwareInfo
from .sampler import Snapshot


class Panel:
    """Owns the visual state (history buffers) and paints the panel."""

    def __init__(self, scale: float = 1.0):
        self.scale = max(1.0, min(3.0, scale))
        self.snap: Optional[Snapshot] = None
        self.info: Optional[HardwareInfo] = None
        self.backdrop: Optional[Image.Image] = None
        self.weather: Optional[dict] = None

        self.cpu_hist = R.History(72)
        self.gpu_hist = R.History(72)
        self.ram_hist = R.History(72)
        self.net_hist = R.History(72)
        self.temp_hist = R.History(72)
        self.board_hist = R.History(72)

        self._net_peak = 64.0
        self._gpu_peak = 100.0

        # hit rectangles, exported so the preview page can align overlay buttons
        self.hits: dict[str, tuple[int, int, int, int]] = {}
        # hover state: which button the cursor is over, and its tooltip
        self.hover: str = ""
        self.collapsed = False

    @property
    def hit_offset(self) -> int:
        """Window coords carry the shadow margin; hit boxes are content coords."""
        return R.SHADOW_MARGIN

    # -- geometry ---------------------------------------------------------
    def s(self, v: float) -> int:
        return int(round(v * self.scale))

    def body_size(self) -> tuple[int, int]:
        card_h = self.s(R.CARD_H)
        gap = self.s(R.GAP)
        pad = self.s(R.PAD)
        proc_h = self.s(R.PROC_HEADER_H) + 5 * self.s(R.PROC_ROW_H) + self.s(R.PROC_PAD_H)

        h = (pad + self.s(R.HEADER_H) + self.s(6)
             + self.s(R.INFO_STRIP_H) + self.s(10)
             + card_h + gap
             + card_h + gap
             + card_h + gap
             + self.s(72) + gap
             + proc_h
             + pad)
        return (self.s(R.DESIGN_WIDTH), h)

    def window_size(self) -> tuple[int, int]:
        w, h = self.body_size()
        margin = R.SHADOW_MARGIN * 2
        return (w + margin, h + margin)

    # -- data -------------------------------------------------------------
    def update(self, snap: Snapshot):
        self.snap = snap
        self.cpu_hist.push(snap.cpu_load)
        self.gpu_hist.push(snap.gpu_load)
        self.ram_hist.push(snap.ram_load)
        self.temp_hist.push(snap.cpu_temp)
        self.board_hist.push(snap.board_temp)
        kb = snap.net_down_bps / 1024.0
        self.net_hist.push(kb)
        self._net_peak = max(self._net_peak, kb)
        if snap.gpu_load is not None:
            self._gpu_peak = max(self._gpu_peak, snap.gpu_load)

    # -- painting ---------------------------------------------------------
    def render(self) -> Image.Image:
        win_w, win_h = self.window_size()
        body_w, body_h = self.body_size()
        margin = R.SHADOW_MARGIN

        img = Image.new("RGBA", (win_w, win_h), (0, 0, 0, 0))

        body_box = (margin, margin, margin + body_w, margin + body_h)
        radius = self.s(R.RADIUS_OUTER)

        R.draw_outer_shadow(img, body_box, radius, int(margin * 0.82), 0.85)

        # Translucent glass: the layered window's per-pixel alpha lets the real
        # desktop show through, so no screen capture is involved (a capture
        # would photograph this very panel and freeze a stale image).
        glass = R.make_glass_body(None, (body_w, body_h), radius,
                                  tint=(10, 16, 30), tint_strength=0.34, opacity=0.66)
        img.alpha_composite(glass, (margin, margin))

        # sheen over the top half
        sheen = Image.new("RGBA", (body_w, body_h), (0, 0, 0, 0))
        sd = ImageDraw.Draw(sheen)
        for i in range(60):
            alpha = int(50 * (1 - i / 60))
            sd.ellipse(
                [-body_w * 0.35, -body_h * 0.05 + i, body_w * 1.35, body_h * 0.55 + i],
                fill=(255, 255, 255, max(0, alpha // 12)))
        mask = R._rounded_mask((body_w, body_h), radius)
        sheen.putalpha(Image.composite(sheen.split()[3], Image.new("L", (body_w, body_h), 0), mask))
        img.alpha_composite(sheen, (margin, margin))

        # content
        content = Image.new("RGBA", (body_w, body_h), (0, 0, 0, 0))
        self._paint_content(content)
        img.alpha_composite(content, (margin, margin))

        # rim last
        R.draw_specular_rim(img, (margin, margin, margin + body_w, margin + body_h), radius)

        # tooltip drawn above everything, near the hovered control
        if self.hover:
            self._paint_tooltip(img, margin)

        return img

    def _paint_tooltip(self, img: Image.Image, margin: int):
        text = self.tooltip_for(self.hover)
        if not text:
            return
        box = self.hits.get(self.hover)
        if not box:
            return

        d = ImageDraw.Draw(img)
        f = R._load_font(self.s(11))
        tw = R.text_size(d, text, f)[0]
        pad_x = self.s(9)
        w = tw + pad_x * 2
        h = self.s(21)

        hx, hy, hw, hh = box
        x = margin + hx + hw // 2 - w // 2
        y = margin + hy + hh + self.s(6)

        # keep it inside the panel
        if x < margin + self.s(8):
            x = margin + self.s(8)
        if x + w > margin + img.width - margin - self.s(8):
            x = margin + img.width - margin - self.s(8) - w

        layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        ld.rounded_rectangle([x, y, x + w, y + h], radius=self.s(6),
                             fill=(14, 17, 26, 235), outline=(255, 255, 255, 60), width=1)
        img.alpha_composite(layer)
        R.draw_text(img, d, text, f, R.TEXT_PRIMARY,
                    (x + w // 2, y + self.s(3)), align="center", shadow=False)

    def _paint_content(self, img: Image.Image):
        d = ImageDraw.Draw(img)
        pad = self.s(R.PAD)
        gap = self.s(R.GAP)
        x = pad
        y = pad
        content_w = img.width - pad * 2

        y = self._paint_header(img, d, x, y, content_w)
        y = self._paint_info_strip(img, d, x, y, content_w)

        # Motherboard sits directly under the info strip, spanning the full width.
        y = self._paint_board_card(img, d, x, y, content_w)

        col_w = (content_w - gap) // 2
        right_x = x + col_w + gap
        card_h = self.s(R.CARD_H)

        self._paint_card(img, d, x, y, col_w, card_h, "CPU", "cpu", R.ACCENT_CYAN,
                         R.fmt_pct(self._cpu_load()),
                         self._sub_cpu(), self.cpu_hist, 0, 100, "line", self._clock_pill())
        self._paint_card(img, d, right_x, y, col_w, card_h, "GPU", "gpu", R.ACCENT_ORANGE,
                         R.fmt_pct(self._gpu_load()),
                         self._sub_gpu(), self.gpu_hist, 0, max(100, self._gpu_peak * 1.1),
                         "line", self._gpu_pill())
        y += card_h + gap

        self._paint_card(img, d, x, y, col_w, card_h, "内存", "ram", R.ACCENT_GREEN,
                         f"{self._ram_load() or 0:.0f}%", self._sub_ram(),
                         self.ram_hist, 0, 100, "bar", self._ram_pill())
        self._paint_card(img, d, right_x, y, col_w, card_h, "存储", "disk", R.ACCENT_BLUE,
                         self._disk_text(), self._sub_disk(),
                         None, 0, 1, "bar", ("C:", R.ACCENT_BLUE))
        y += card_h + gap

        self._paint_card(img, d, x, y, col_w, card_h, "网络", "net", R.ACCENT_TEAL,
                         R.fmt_rate(self.snap.net_down_bps if self.snap else 0),
                         self._sub_net(), self.net_hist, 0, max(64, self._net_peak * 1.35),
                         "line", (self._net_name(), R.ACCENT_TEAL))
        self._paint_temp_card(img, d, right_x, y, col_w, card_h)
        y += card_h + gap

        self._paint_processes(img, d, x, y, content_w)

    # -- header -----------------------------------------------------------
    def _paint_header(self, img, d, x, y, w) -> int:
        h = self.s(R.HEADER_H)
        score = self.snap.score if self.snap else 100
        color = R.ACCENT_GREEN if score >= 85 else R.ACCENT_YELLOW if score >= 65 else R.ACCENT_ORANGE

        # Big score with a small arc, instead of digits crammed into a ring:
        # "100" needs horizontal room that a 44px circle cannot give.
        ring = self.s(40)
        rx, ry = x, y + self.s(4)
        d.arc([rx, ry, rx + ring, ry + ring], -90, 270,
              fill=(255, 255, 255, 40), width=self.s(3))
        d.arc([rx, ry, rx + ring, ry + ring], -90, -90 + 360 * score / 100,
              fill=color + (255,), width=self.s(3))

        f_score = R._load_font(self.s(26), bold=True)
        f_word = R._load_font(self.s(12))

        # number sits right of the ring, freely sized
        sx = rx + ring + self.s(10)
        R.draw_text(img, d, str(score), f_score, R.TEXT_PRIMARY, (sx, y + self.s(2)))
        sw = R.text_size(d, str(score), f_score)[0]
        f_unit = R._load_font(self.s(11))
        R.draw_text(img, d, "分", f_unit, R.TEXT_MUTED, (sx + sw + self.s(2), y + self.s(17)))

        R.draw_text(img, d, R.score_word(score), f_word, color + (255,),
                    (sx + sw + self.s(18), y + self.s(15)))

        # buttons: collapse / close / pin / gear
        bs = self.s(30)
        by = ry + (ring - bs) // 2
        close_x = x + w - bs
        pin_x = close_x - bs - self.s(4)
        gear_x = pin_x - bs - self.s(4)
        min_x = gear_x - bs - self.s(8)
        self.hits["close"] = (close_x, by, bs, bs)
        self.hits["pin"] = (pin_x, by, bs, bs)
        self.hits["gear"] = (gear_x, by, bs, bs)
        self.hits["min"] = (min_x, by, bs, bs)

        for key, cx, glyph in (
            ("close", close_x, "close"),
            ("pin", pin_x, "pin"),
            ("gear", gear_x, "gear"),
            ("min", min_x, "min"),
        ):
            self._draw_button(d, cx, by, bs, glyph, hover=(self.hover == key))

        return y + h + self.s(6)

    def _draw_button(self, d, x, y, size, kind, hover=False):
        """Round glass button; highlights and shows nothing else when hovered."""
        if hover:
            d.ellipse([x, y, x + size, y + size],
                      fill=(255, 255, 255, 52), outline=(255, 255, 255, 150), width=1)
        self._draw_glyph(d, x, y, size, kind,
                         color=(255, 255, 255, 255) if hover else (212, 212, 212, 235))

    def hover_at(self, wx: int, wy: int) -> str:
        """Returns the button key under a window-space cursor position."""
        off = self.hit_offset
        x, y = wx - off, wy - off
        for key, (hx, hy, hw, hh) in self.hits.items():
            if hx <= x <= hx + hw and hy <= y <= hy + hh:
                return key
        return ""

    def tooltip_for(self, key: str) -> str:
        return {
            "min": "最小化到托盘",
            "close": "关闭面板",
            "pin": "固定在桌面",
            "gear": "设置",
            "info": "查看硬件详情",
        }.get(key, "")

    def _draw_glyph(self, d, x, y, size, kind, color=(212, 212, 212, 255)):
        cx, cy = x + size / 2, y + size / 2
        s = self.scale
        lw = max(1, int(1.6 * s))
        if kind == "close":
            d.line([cx - 4.5 * s, cy - 4.5 * s, cx + 4.5 * s, cy + 4.5 * s], fill=color, width=lw)
            d.line([cx + 4.5 * s, cy - 4.5 * s, cx - 4.5 * s, cy + 4.5 * s], fill=color, width=lw)
        elif kind == "pin":
            d.ellipse([cx - 3 * s, cy - 6.5 * s, cx + 3 * s, cy - 0.5 * s], fill=color)
            d.line([cx, cy - 0.5 * s, cx, cy + 6 * s], fill=color, width=lw)
            d.line([cx - 3 * s, cy + 6 * s, cx + 3 * s, cy + 6 * s], fill=color, width=lw)
        elif kind == "gear":
            d.ellipse([cx - 5.5 * s, cy - 5.5 * s, cx + 5.5 * s, cy + 5.5 * s],
                      outline=color, width=lw)
            d.ellipse([cx - 2 * s, cy - 2 * s, cx + 2 * s, cy + 2 * s], outline=color, width=lw)
        elif kind == "min":
            d.line([cx - 4.5 * s, cy, cx + 4.5 * s, cy], fill=color, width=lw)

    # -- info strip -------------------------------------------------------
    def _paint_info_strip(self, img, d, x, y, w) -> int:
        h = self.s(R.INFO_STRIP_H)
        self._glass_card(img, d, x, y, w, h, R.ACCENT_BLUE)
        self.hits["info"] = (x, y, w, h)

        padx = self.s(13)
        items = [
            ("型号信息", self._machine_name()),
            ("系统信息", self._os_text()),
            ("运行时间", ("已运行 " + R.fmt_uptime(self.snap.uptime_hours)) if self.snap else "--"),
        ]
        inner = w - padx * 2 - self.s(18)
        col = inner // 3

        f_lab = R._load_font(self.s(10))
        f_val = R._load_font(self.s(12))

        for i, (label, value) in enumerate(items):
            cx = x + padx + col * i
            R.draw_text(img, d, label, f_lab, R.TEXT_MUTED, (cx, y + self.s(8)))
            value = R.fit_text(d, value, f_val, col - self.s(10))
            R.draw_text(img, d, value, f_val, R.TEXT_PRIMARY, (cx, y + self.s(25)))

        # chevron
        chx = x + w - self.s(14)
        chy = y + h // 2
        s = self.scale
        col_c = R.TEXT_SECONDARY
        d.line([chx - 2 * s, chy - 4 * s, chx + 2 * s, chy], fill=col_c, width=max(1, int(1.5 * s)))
        d.line([chx + 2 * s, chy, chx - 2 * s, chy + 4 * s], fill=col_c, width=max(1, int(1.5 * s)))

        return y + h + self.s(10)

    # -- generic card -----------------------------------------------------
    def _glass_card(self, img, d, x, y, w, h, accent):
        """A frosted sub-card: translucent enough to let the glass show through."""
        card = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        cd = ImageDraw.Draw(card)
        radius = self.s(R.RADIUS_CARD)

        # Dark base for contrast, kept clearly translucent so the desktop
        # continues to read through the whole stack: glass -> card -> content.
        cd.rounded_rectangle([0, 0, w - 1, h - 1], radius=radius, fill=(10, 14, 26, 62))
        # light wash on top
        for i in range(h):
            t = i / max(1, h - 1)
            a = int(32 * (1 - t) + 4 * t)
            cd.line([(1, i), (w - 2, i)], fill=(255, 255, 255, a))
        # accent glow, top-left
        glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow)
        gd.ellipse([-w * 0.25, -h * 0.6, w * 0.7, h * 0.65],
                   fill=(accent[0], accent[1], accent[2], 34))
        glow = glow.filter(ImageFilter.GaussianBlur(self.s(10)))
        card.alpha_composite(glow)

        # rim
        cd.rounded_rectangle([0, 0, w - 1, h - 1], radius=radius,
                             outline=(255, 255, 255, 96), width=1)

        mask = R._rounded_mask((w, h), radius)
        card.putalpha(Image.composite(card.split()[3], Image.new("L", (w, h), 0), mask))

        img.alpha_composite(card, (x, y))

    def _paint_card(self, img, d, x, y, w, h, title, icon, accent,
                    value, sub, hist, hmin, hmax, style, pill):
        self._glass_card(img, d, x, y, w, h, accent)

        padx = self.s(13)
        f_lab = R._load_font(self.s(12))
        f_val = R._load_font(self.s(30), bold=True)
        f_tiny = R._load_font(self.s(10))

        # icon + title on one centre line
        row_cy = y + self.s(9) + self.s(9)
        icon_size = self.s(13)
        self._icon(d, x + padx, row_cy - icon_size // 2, icon_size, icon, accent)
        R.draw_text(img, d, title, f_lab, R.TEXT_SECONDARY,
                    (x + padx + self.s(21), row_cy - self.s(8)))

        if pill and pill[0]:
            self._pill(img, d, x, y, w, pill[0], pill[1])

        R.draw_text(img, d, value, f_val, R.TEXT_PRIMARY, (x + padx, y + self.s(28)))

        gx, gy = x + padx, y + self.s(68)
        gw = w - padx * 2
        if style == "bar":
            frac = pill[3] if len(pill) > 3 else 0.55
            self._bar(d, gx, gy + self.s(4), gw, frac, accent)
        elif hist is not None:
            self._sparkline(img, d, gx, gy, gw, self.s(16), hist, accent, hmin, hmax)

        R.draw_text(img, d, sub, f_tiny, R.TEXT_MUTED, (x + padx, y + self.s(92)))

    def _pill(self, img, d, x, y, w, text, tint):
        f = R._load_font(self.s(10))
        tw = R.text_size(d, text, f)[0]
        pw = min(tw + self.s(16), w - self.s(50))
        ph = self.s(18)
        px = x + w - self.s(11) - pw
        py = y + self.s(10)
        d.rounded_rectangle([px, py, px + pw, py + ph], radius=ph // 2,
                            fill=(tint[0], tint[1], tint[2], 76),
                            outline=(255, 255, 255, 70), width=1)
        R.draw_text(img, d, text, f, R.TEXT_PRIMARY + (255,),
                    (px + pw // 2, py + self.s(3)), align="center")

    def _bar(self, d, x, y, w, frac, accent, height=None):
        hgt = height or self.s(5)
        frac = max(0.0, min(1.0, frac))
        d.rounded_rectangle([x, y, x + w, y + hgt], radius=hgt // 2, fill=(255, 255, 255, 38))
        if frac > 0.001:
            fw = max(hgt, int(w * frac))
            d.rounded_rectangle([x, y, x + fw, y + hgt], radius=hgt // 2,
                                fill=(accent[0], accent[1], accent[2], 255))

    def _sparkline(self, img, d, x, y, w, h, hist, accent, vmin, vmax):
        vals = [v for v in hist.values() if v is not None]
        if len(vals) < 2:
            return
        span = max(1e-6, vmax - vmin)
        n = len(vals)
        pts = []
        for i, v in enumerate(vals):
            nx = x + (w - 1) * i / (n - 1)
            norm = max(0.0, min(1.0, (v - vmin) / span))
            ny = y + h - norm * h
            pts.append((nx, ny))

        # area under the line
        poly = pts + [(x + w - 1, y + h), (x, y + h)]
        fill_img = Image.new("RGBA", img.size, (0, 0, 0, 0))
        fd = ImageDraw.Draw(fill_img)
        fd.polygon(poly, fill=(accent[0], accent[1], accent[2], 46))
        img.alpha_composite(fill_img)

        d.line(pts, fill=(accent[0], accent[1], accent[2], 235), width=max(1, int(1.4 * self.scale)))
        lx, ly = pts[-1]
        r = self.s(2)
        d.ellipse([lx - r, ly - r, lx + r, ly + r], fill=(accent[0], accent[1], accent[2], 255))

    def _icon(self, d, x, y, size, kind, accent):
        col = (accent[0], accent[1], accent[2], 210)
        lw = max(1, int(1.35 * self.scale))
        if kind == "cpu":
            d.rounded_rectangle([x + 1, y + 1, x + size - 1, y + size - 1], radius=3, outline=col, width=lw)
            d.rectangle([x + 4.5, y + 4.5, x + size - 4.5, y + size - 4.5], outline=col, width=lw)
        elif kind == "gpu":
            d.rounded_rectangle([x, y + 2.5, x + size - 2, y + size - 3.5], radius=3, outline=col, width=lw)
            d.ellipse([x + size / 2 - 2.6, y + size / 2 - 2.6, x + size / 2 + 2.6, y + size / 2 + 2.6], outline=col, width=lw)
        elif kind == "ram":
            d.rounded_rectangle([x, y + 3, x + size, y + size - 3], radius=2, outline=col, width=lw)
            d.line([x + 3, y + 6, x + 3, y + size - 6], fill=col, width=lw)
            d.line([x + size - 3, y + 6, x + size - 3, y + size - 6], fill=col, width=lw)
        elif kind == "disk":
            d.rounded_rectangle([x, y, x + size, y + size], radius=3, outline=col, width=lw)
            d.line([x, y + size * 0.58, x + size, y + size * 0.58], fill=col, width=lw)
        elif kind == "net":
            d.ellipse([x, y, x + size, y + size], outline=col, width=lw)
            d.ellipse([x, y + 3, x + size, y + size - 3], outline=col, width=lw)
        elif kind == "temp":
            d.line([x + size / 2, y + 1.5, x + size / 2, y + size - 5], fill=col, width=lw)
            d.ellipse([x + size / 2 - 3.4, y + size - 8, x + size / 2 + 3.4, y + size - 1.4], outline=col, width=lw)
        elif kind == "board":
            d.rounded_rectangle([x, y, x + size, y + size], radius=3, outline=col, width=lw)
            d.rectangle([x + 3.5, y + 3.5, x + 8, y + 8], outline=col, width=lw)
            d.line([x + 9, y + 10, x + size - 2, y + 10], fill=col, width=lw)

    # -- temperature card -------------------------------------------------
    def _paint_temp_card(self, img, d, x, y, w, h):
        t = self.snap.cpu_temp if self.snap else None
        color = R.temp_color(t)
        self._glass_card(img, d, x, y, w, h, color)

        padx = self.s(13)
        f_lab = R._load_font(self.s(12))
        f_val = R._load_font(self.s(30), bold=True)
        f_tiny = R._load_font(self.s(10))

        row_cy = y + self.s(9) + self.s(9)
        icon_size = self.s(13)
        self._icon(d, x + padx, row_cy - icon_size // 2, icon_size, "temp", color)
        # Say whose temperature this is: the value alone is ambiguous.
        R.draw_text(img, d, "CPU 温度", f_lab, R.TEXT_SECONDARY,
                    (x + padx + self.s(21), row_cy - self.s(8)))

        state = "无数据" if t is None else ("凉爽" if t < 55 else "正常" if t < 70 else "偏高" if t < 82 else "过热")
        self._pill(img, d, x, y, w, state, color)

        big = "--" if t is None else f"{t:.0f}"
        R.draw_text(img, d, big, f_val, R.TEXT_PRIMARY, (x + padx, y + self.s(28)))
        bw = R.text_size(d, big, f_val)[0]
        R.draw_text(img, d, "°C", f_lab, R.TEXT_SECONDARY, (x + padx + bw, y + self.s(40)))

        frac = 0.0 if t is None else min(1.0, max(0.0, (t - 25) / 75))
        self._bar(d, x + padx, y + self.s(72), w - padx * 2, frac, color)

        # Two tidy lines instead of one that runs into the card edge.
        sub1 = ""
        sub2 = ""
        if self.snap:
            sub1 = f"主板 {R.fmt_temp(self.snap.board_temp)} · 显卡 {R.fmt_temp(self.snap.gpu_temp)}"
            disk = R.fmt_temp(self.snap.disk_temp)
            ram = "无传感器" if self.snap.ram_temp is None else R.fmt_temp(self.snap.ram_temp)
            sub2 = f"硬盘 {disk} · 内存 {ram}"

        sub1 = R.fit_text(d, sub1, f_tiny, w - padx * 2)
        R.draw_text(img, d, sub1, f_tiny, R.TEXT_MUTED, (x + padx, y + self.s(84)))
        sub2 = R.fit_text(d, sub2, f_tiny, w - padx * 2)
        R.draw_text(img, d, sub2, f_tiny, R.TEXT_MUTED, (x + padx, y + self.s(98)))

    # -- board (full width) -----------------------------------------------
    def _paint_board_card(self, img, d, x, y, w) -> int:
        h = self.s(72)
        t = self.snap.board_temp if self.snap else None
        color = R.temp_color(t)
        self._glass_card(img, d, x, y, w, h, color)

        padx = self.s(13)
        f_lab = R._load_font(self.s(12))
        f_val = R._load_font(self.s(22), bold=True)
        f_tiny = R._load_font(self.s(10))

        row_cy = y + self.s(9) + self.s(9)
        icon_size = self.s(13)
        self._icon(d, x + padx, row_cy - icon_size // 2, icon_size, "board", color)
        R.draw_text(img, d, "主板", f_lab, R.TEXT_SECONDARY,
                    (x + padx + self.s(21), row_cy - self.s(8)))

        # board model, right-aligned in the title row
        name = self.info.board if self.info and self.info.board else (
            self.snap.board_name if self.snap else "")
        if name:
            # leave room for the icon+title on the left
            avail = w - self.s(150)
            name = R.fit_text(d, name, f_tiny, max(self.s(60), avail))
            R.draw_text(img, d, name, f_tiny, R.TEXT_MUTED,
                        (x + w - padx, row_cy - self.s(7)), align="right")

        R.draw_text(img, d, "--" if t is None else f"{t:.0f}°C", f_val, R.TEXT_PRIMARY,
                    (x + padx, y + self.s(30)))

        gx = x + padx + self.s(88)
        self._sparkline(img, d, gx, y + self.s(36), x + w - padx - gx, self.s(14),
                        self.board_hist, color, 20, 90)

        sub = ""
        if self.snap:
            sub = f"热点 {R.fmt_temp(self.snap.gpu_hotspot)} · 硬盘 {R.fmt_temp(self.snap.disk_temp)}"
        R.draw_text(img, d, sub, f_tiny, R.TEXT_MUTED, (x + padx, y + self.s(52)))

        return y + h + self.s(R.GAP)

    # -- processes --------------------------------------------------------
    def _paint_processes(self, img, d, x, y, w):
        h = self.s(R.PROC_HEADER_H) + 5 * self.s(R.PROC_ROW_H) + self.s(R.PROC_PAD_H)
        self._glass_card(img, d, x, y, w, h, R.ACCENT_PURPLE)

        padx = self.s(13)
        f_lab = R._load_font(self.s(12))
        f_small = R._load_font(self.s(11))
        f_tiny = R._load_font(self.s(10))

        R.draw_text(img, d, "高占用进程", f_lab, R.TEXT_SECONDARY, (x + padx, y + self.s(7)))
        R.draw_text(img, d, "内存", f_tiny, R.TEXT_MUTED,
                    (x + w - self.s(150), y + self.s(9)), align="right")
        R.draw_text(img, d, "% CPU", f_tiny, R.TEXT_MUTED,
                    (x + w - self.s(70), y + self.s(9)), align="right")

        if not self.snap or not self.snap.processes:
            return

        row_y = y + self.s(R.PROC_HEADER_H)
        for p in self.snap.processes[:5]:
            mb = p["mem_mb"]
            mem = f"{mb / 1024:.1f} GB" if mb >= 1024 else f"{mb:.0f} MB"
            R.draw_text(img, d, p["name"], f_small, R.TEXT_PRIMARY,
                        (x + padx, row_y + self.s(3)))
            R.draw_text(img, d, mem, f_small, R.TEXT_SECONDARY,
                        (x + w - self.s(150), row_y + self.s(3)), align="right")
            R.draw_text(img, d, f"{p['cpu']:.1f}", f_small, R.TEXT_SECONDARY,
                        (x + w - self.s(70), row_y + self.s(3)), align="right")
            row_y += self.s(R.PROC_ROW_H)

    # -- value helpers ----------------------------------------------------
    def _cpu_load(self):
        return self.snap.cpu_load if self.snap else None

    def _gpu_load(self):
        return self.snap.gpu_load if self.snap else None

    def _ram_load(self):
        return self.snap.ram_load if self.snap else None

    def _clock_pill(self):
        c = self.snap.cpu_clock_ghz if self.snap else None
        return (f"{c:.2f} GHz" if c else "", R.ACCENT_CYAN)

    def _gpu_pill(self):
        """The GPU model: temperature already has its own card."""
        name = self._gpu_short()
        return (name, R.ACCENT_ORANGE) if name else ("", R.ACCENT_ORANGE)

    def _gpu_short(self) -> str:
        """'AMD Radeon RX 6650 XT' -> 'RX 6650 XT'."""
        name = ""
        if self.info and self.info.gpus:
            name = self.info.gpus[0]
        elif self.snap and self.snap.gpu_name:
            name = self.snap.gpu_name
        if not name:
            return ""
        for prefix in ("AMD Radeon ", "NVIDIA GeForce ", "Intel Arc ", "Intel "):
            if name.startswith(prefix):
                name = name[len(prefix):]
                break
        if len(name) > 13:
            name = name[:13]
        return name

    def _ram_pill(self):
        v = self.snap.ram_load if self.snap else None
        word, color = "正常", R.ACCENT_GREEN
        frac = (v / 100.0) if v else 0.55
        if v is not None:
            if v >= 92:
                word, color = "紧张", R.ACCENT_RED
            elif v >= 80:
                word, color = "较高", R.ACCENT_ORANGE
            elif v >= 60:
                word, color = "偏高", R.ACCENT_YELLOW
        return (word, color, "", frac)

    def _disk_text(self):
        free = self.snap.disk_free_gb if self.snap else None
        return "--" if free is None else f"{free:.1f} GB"

    def _net_name(self):
        return (self.snap.net_name or "网络")[:10] if self.snap else "网络"

    def _sub_cpu(self):
        if not self.snap:
            return ""
        parts = [R.load_word(self.snap.cpu_load), f"{self.snap.cpu_threads} 线程"]
        return " · ".join(parts)

    def _sub_gpu(self):
        if not self.snap:
            return ""
        used = self.snap.gpu_mem_used_mb
        if used:
            return f"{used / 1024:.1f} GB 显存 · {R.load_word(self.snap.gpu_load)}"
        return R.load_word(self.snap.gpu_load)

    def _sub_ram(self):
        if not self.snap or self.snap.ram_used_gb is None:
            return ""
        return f"{self.snap.ram_used_gb:.1f} / {self.snap.ram_total_gb:.1f} GB"

    def _sub_disk(self):
        if not self.snap or self.snap.disk_total_gb is None:
            return ""
        used = self.snap.disk_total_gb - self.snap.disk_free_gb
        pct = used / self.snap.disk_total_gb * 100
        return f"已用 {used:.0f} GB · {pct:.0f}%"

    def _sub_net(self):
        if not self.snap:
            return ""
        return f"↑ {R.fmt_rate(self.snap.net_up_bps)}   ↓ {R.fmt_rate(self.snap.net_down_bps)}"

    def _machine_name(self):
        if self.info and self.info.model:
            return self.info.model
        if self.snap and self.snap.board_name:
            return self.snap.board_name
        return "本机"

    def _os_text(self):
        return self.snap.os_name if self.snap else ""
