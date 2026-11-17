"""Liquid-glass panel rendered into a 32-bit ARGB bitmap.

The window is per-pixel transparent, so this module owns the whole look:
blurred backdrop, frosted cards, specular rims, shadows and the metric
layout. Nothing is drawn by a child control; every pixel comes from here.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
from typing import Optional

from PIL import Image, ImageDraw, ImageFilter, ImageFont


# ----------------------------------------------------------------------------
#  Geometry (design pixels; everything scales by DPI)
# ----------------------------------------------------------------------------

DESIGN_WIDTH = 404
PAD = 14
GAP = 9
CARD_H = 124
INFO_STRIP_H = 58
HEADER_H = 52
PROC_ROW_H = 23
PROC_HEADER_H = 30
PROC_PAD_H = 8
SHADOW_MARGIN = 26

RADIUS_OUTER = 30
RADIUS_CARD = 20


# ----------------------------------------------------------------------------
#  Palette
# ----------------------------------------------------------------------------

ACCENT_BLUE = (10, 132, 255)
ACCENT_CYAN = (100, 210, 255)
ACCENT_GREEN = (48, 209, 88)
ACCENT_YELLOW = (255, 214, 10)
ACCENT_ORANGE = (255, 159, 10)
ACCENT_PURPLE = (191, 90, 242)
ACCENT_TEAL = (64, 200, 224)
ACCENT_RED = (255, 69, 58)

TEXT_PRIMARY = (255, 255, 255, 255)
TEXT_SECONDARY = (212, 255, 255, 255)
TEXT_MUTED = (150, 255, 255, 255)
TEXT_FAINT = (96, 255, 255, 255)
TEXT_SHADOW = (120, 0, 0, 0)


def temp_color(celsius: Optional[float]) -> tuple[int, int, int]:
    if celsius is None:
        return tuple(TEXT_FAINT[:3])
    if celsius < 55:
        return ACCENT_GREEN
    if celsius < 70:
        return ACCENT_YELLOW
    if celsius < 82:
        return ACCENT_ORANGE
    return ACCENT_RED


# ----------------------------------------------------------------------------
#  Fonts
# ----------------------------------------------------------------------------

_FONT_CACHE: dict[tuple[str, int, bool], ImageFont.FreeTypeFont] = {}


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Loads a font that actually covers CJK.

    Segoe UI has no Chinese glyphs, so it renders every label as a tofu box;
    Microsoft YaHei (msyh) is the one to reach for, with the bold face for
    numeric emphasis.
    """
    key = ("ui", size, bold)
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]

    if bold:
        candidates = [
            r"C:\Windows\Fonts\msyhbd.ttc",
            r"C:\Windows\Fonts\msyhbd.ttf",
            r"C:\Windows\Fonts\DengBold.ttf",
            r"C:\Windows\Fonts\simhei.ttf",
            r"C:\Windows\Fonts\segoeuib.ttf",
        ]
    else:
        candidates = [
            r"C:\Windows\Fonts\msyh.ttc",
            r"C:\Windows\Fonts\msyh.ttf",
            r"C:\Windows\Fonts\Deng.ttf",
            r"C:\Windows\Fonts\simsun.ttc",
            r"C:\Windows\Fonts\segoeui.ttf",
        ]

    font = None
    for path in candidates:
        try:
            font = ImageFont.truetype(path, size)
            break
        except Exception:
            continue
    if font is None:
        font = ImageFont.load_default()
    _FONT_CACHE[key] = font
    return font


# ----------------------------------------------------------------------------
#  History ring
# ----------------------------------------------------------------------------

class History:
    """Rolling window of nullable samples."""

    def __init__(self, capacity: int = 72):
        self.capacity = capacity
        self._buf: list[Optional[float]] = [None] * capacity
        self._head = 0
        self._count = 0

    def push(self, value: Optional[float]):
        self._buf[self._head] = value
        self._head = (self._head + 1) % self.capacity
        if self._count < self.capacity:
            self._count += 1

    def values(self) -> list[Optional[float]]:
        start = (self._head - self._count) % self.capacity
        return [self._buf[(start + i) % self.capacity] for i in range(self._count)]


# ----------------------------------------------------------------------------
#  Backdrop capture
# ----------------------------------------------------------------------------

class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG),
        ("biPlanes", wt.WORD), ("biBitCount", wt.WORD), ("biCompression", wt.DWORD),
        ("biSizeImage", wt.DWORD), ("biXPelsPerMeter", wt.LONG),
        ("biYPelsPerMeter", wt.LONG), ("biClrUsed", wt.DWORD), ("biClrImportant", wt.DWORD),
    ]


_gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
_user32 = ctypes.WinDLL("user32", use_last_error=True)


def capture_screen_region(x: int, y: int, w: int, h: int) -> Optional[Image.Image]:
    """Grabs a screen rectangle. Must not be called while the panel covers it."""
    if w <= 0 or h <= 0:
        return None
    screen_dc = None
    mem_dc = None
    bmp = None
    old = None
    try:
        screen_dc = _user32.GetDC(None)
        mem_dc = _gdi32.CreateCompatibleDC(screen_dc)
        bmp = _gdi32.CreateCompatibleBitmap(screen_dc, w, h)
        old = _gdi32.SelectObject(mem_dc, bmp)

        SRCCOPY = 0x00CC0020
        CAPTUREBLT = 0x40000000
        if not _gdi32.BitBlt(mem_dc, 0, 0, w, h, screen_dc, x, y, SRCCOPY | CAPTUREBLT):
            _gdi32.BitBlt(mem_dc, 0, 0, w, h, screen_dc, x, y, SRCCOPY)

        bi = _BITMAPINFOHEADER()
        bi.biSize = ctypes.sizeof(_BITMAPINFOHEADER)
        bi.biWidth = w
        bi.biHeight = -h  # top-down
        bi.biPlanes = 1
        bi.biBitCount = 32
        bi.biCompression = 0  # BI_RGB

        buf = ctypes.create_string_buffer(w * h * 4)
        lines = _gdi32.GetDIBits(mem_dc, bmp, 0, h, buf, ctypes.byref(bi), 0)
        if lines == 0:
            return None
        return Image.frombuffer("RGBA", (w, h), buf, "raw", "BGRA", 0, 1).copy()
    except Exception:
        return None
    finally:
        try:
            if mem_dc and old:
                _gdi32.SelectObject(mem_dc, old)
            if bmp:
                _gdi32.DeleteObject(bmp)
            if mem_dc:
                _gdi32.DeleteDC(mem_dc)
            if screen_dc:
                _user32.ReleaseDC(None, screen_dc)
        except Exception:
            pass


# ----------------------------------------------------------------------------
#  Glass primitives
# ----------------------------------------------------------------------------

def _rounded_mask(size: tuple[int, int], radius: int) -> Image.Image:
    mask = Image.new("L", size, 0)
    d = ImageDraw.Draw(mask)
    d.rounded_rectangle([0, 0, size[0] - 1, size[1] - 1], radius=radius, fill=255)
    return mask


def make_glass_body(backdrop: Optional[Image.Image], size: tuple[int, int],
                    radius: int, tint=(12, 18, 34), tint_strength=0.46,
                    opacity: float = 0.82) -> Image.Image:
    """The glass body, as a genuinely translucent surface.

    The window is per-pixel-alpha, so keeping alpha below 255 is what makes the
    desktop show through live - a captured backdrop would be a stale snapshot
    of whatever was behind us when we painted.
    """
    w, h = size
    if backdrop is not None:
        img = backdrop.convert("RGB").resize((w, h), Image.LANCZOS)
        img = img.filter(ImageFilter.GaussianBlur(radius=22))
        img = Image.eval(img, lambda v: int(v * 0.62))
        base = img.convert("RGBA")
    else:
        base = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(base)
        for yy in range(h):
            t = yy / max(1, h - 1)
            col = (
                int(44 * (1 - t) + 16 * t),
                int(58 * (1 - t) + 20 * t),
                int(92 * (1 - t) + 30 * t),
                255,
            )
            d.line([(0, yy), (w, yy)], fill=col)

    # tint wash deepens the colour of the glass
    wash = Image.new("RGBA", (w, h), (tint[0], tint[1], tint[2], int(tint_strength * 255)))
    base = Image.alpha_composite(base, wash)

    # scale the whole surface's alpha: this is the actual see-through amount
    a = base.split()[3]
    a = a.point(lambda v: int(v * max(0.0, min(1.0, opacity))))
    base.putalpha(a)

    mask = _rounded_mask((w, h), radius)
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    out.paste(base, (0, 0), mask)
    return out


def draw_specular_rim(target: Image.Image, box: tuple[int, int, int, int], radius: int):
    """Bright inner edge at the top fading to nothing at the bottom."""
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    if w <= 2 or h <= 2:
        return

    rim = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(rim)
    d.rounded_rectangle([0, 0, w - 1, h - 1], radius=radius, outline=(255, 255, 255, 190), width=1)

    # vertical fade: opaque at top, transparent at bottom
    fade = Image.new("L", (1, h))
    for yy in range(h):
        fade.putpixel((0, yy), max(0, int(255 * (1 - yy / max(1, h - 1)) ** 1.3)))
    fade = fade.resize((w, h))

    alpha = rim.split()[3]
    rim.putalpha(Image.composite(alpha, Image.new("L", (w, h), 0), fade))
    target.alpha_composite(rim, (x0, y0))


def draw_outer_shadow(target: Image.Image, box: tuple[int, int, int, int],
                      radius: int, margin: int, opacity: float = 0.85):
    x0, y0, x1, y1 = box
    steps = 8
    layer = Image.new("RGBA", target.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for i in range(steps, 0, -1):
        grow = margin * i / steps
        alpha = int(255 * opacity * (1 - i / steps) * 0.55)
        if alpha <= 2:
            continue
        d.rounded_rectangle(
            [x0 - grow, y0 - grow + margin * 0.28, x1 + grow, y1 + grow],
            radius=int(radius + grow), fill=(0, 0, 0, alpha))
    layer = layer.filter(ImageFilter.GaussianBlur(3))
    target.alpha_composite(layer)


# ----------------------------------------------------------------------------
#  Text helpers
# ----------------------------------------------------------------------------

def text_size(draw: ImageDraw.ImageDraw, text: str, font) -> tuple[int, int]:
    if not text:
        return (0, 0)
    box = draw.textbbox((0, 0), text, font=font)
    return (box[2] - box[0], box[3] - box[1])


def _rgba(color) -> tuple[int, int, int, int]:
    """Normalises a colour to a 4-tuple so callers can pass RGB or RGBA."""
    if color is None:
        return (255, 255, 255, 255)
    t = tuple(color)
    if len(t) == 4:
        return t
    if len(t) == 3:
        return (t[0], t[1], t[2], 255)
    return (255, 255, 255, 255)


def draw_text(target: Image.Image, draw: ImageDraw.ImageDraw, text: str, font,
              color, xy: tuple[int, int], align: str = "left",
              shadow: bool = True):
    if not text:
        return
    tw, th = text_size(draw, text, font)
    x, y = xy
    if align == "right":
        x = x - tw
    elif align == "center":
        x = x - tw // 2

    if shadow:
        draw.text((x + 1, y + 1), text, font=font, fill=TEXT_SHADOW)
    draw.text((x, y), text, font=font, fill=_rgba(color))


def fit_text(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> str:
    if not text:
        return ""
    if text_size(draw, text, font)[0] <= max_width:
        return text
    for cut in range(len(text) - 1, 0, -1):
        candidate = text[:cut] + "…"
        if text_size(draw, candidate, font)[0] <= max_width:
            return candidate
    return "…"


# ----------------------------------------------------------------------------
#  Formatters
# ----------------------------------------------------------------------------

def fmt_pct(v: Optional[float]) -> str:
    return "--" if v is None else f"{v:.1f}%"


def fmt_temp(v: Optional[float]) -> str:
    return "--" if v is None else f"{v:.0f}°"


def fmt_rate(bps: float) -> str:
    kb = max(0.0, bps) / 1024.0
    if kb < 1024:
        return f"{kb:.1f} KB/s"
    mb = kb / 1024.0
    if mb < 1024:
        return f"{mb:.1f} MB/s"
    return f"{mb / 1024:.2f} GB/s"


def fmt_uptime(hours: float) -> str:
    h = int(max(0, hours))
    d = h // 24
    if d > 0:
        return f"{d}天{h % 24}小时"
    if h > 0:
        return f"{h}小时"
    return f"{max(1, int(hours * 60))}分钟"


def load_word(pct: Optional[float]) -> str:
    if pct is None:
        return "未知"
    if pct < 15:
        return "空闲"
    if pct < 45:
        return "轻载"
    if pct < 75:
        return "中载"
    return "重载"


def score_word(score: int) -> str:
    if score >= 90:
        return "运行良好"
    if score >= 75:
        return "状态正常"
    if score >= 60:
        return "略有压力"
    return "需要留意"
