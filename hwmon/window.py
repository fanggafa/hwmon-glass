"""Layered, click-through-capable glass window for the panel.

The window has no frame and no background: every pixel comes from the Pillow
image, uploaded with UpdateLayeredWindow so the corners and the drop shadow
are genuinely transparent.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
from typing import Optional

from PIL import Image


# ----------------------------------------------------------------------------
#  Win32
# ----------------------------------------------------------------------------

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)


class _POINT(ctypes.Structure):
    _fields_ = [("x", wt.LONG), ("y", wt.LONG)]


class _SIZE(ctypes.Structure):
    _fields_ = [("cx", wt.LONG), ("cy", wt.LONG)]


class _BLENDFUNCTION(ctypes.Structure):
    _fields_ = [
        ("BlendOp", ctypes.c_byte),
        ("BlendFlags", ctypes.c_byte),
        ("SourceConstantAlpha", ctypes.c_byte),
        ("AlphaFormat", ctypes.c_byte),
    ]


class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG),
        ("biPlanes", wt.WORD), ("biBitCount", wt.WORD), ("biCompression", wt.DWORD),
        ("biSizeImage", wt.DWORD), ("biXPelsPerMeter", wt.LONG),
        ("biYPelsPerMeter", wt.LONG), ("biClrUsed", wt.DWORD), ("biClrImportant", wt.DWORD),
    ]


class _TRACKMOUSEEVENT(ctypes.Structure):
    _fields_ = [
        ("cbSize", wt.DWORD),
        ("dwFlags", wt.DWORD),
        ("hwndTrack", wt.HWND),
        ("dwHoverTime", wt.DWORD),
    ]


user32.TrackMouseEvent.argtypes = [ctypes.POINTER(_TRACKMOUSEEVENT)]
user32.TrackMouseEvent.restype = wt.BOOL
user32.SetCapture.argtypes = [wt.HWND]
user32.SetCapture.restype = wt.HWND
user32.ReleaseCapture.restype = wt.BOOL
user32.IsWindow.argtypes = [wt.HWND]
user32.IsWindow.restype = wt.BOOL


WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_long, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)


class _WNDCLASSEX(ctypes.Structure):
    _fields_ = [
        ("cbSize", wt.UINT), ("style", wt.UINT), ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
        ("hInstance", wt.HINSTANCE), ("hIcon", wt.HICON), ("hCursor", wt.HANDLE),
        ("hbrBackground", wt.HBRUSH), ("lpszMenuName", wt.LPCWSTR),
        ("lpszClassName", wt.LPCWSTR), ("hIconSm", wt.HICON),
    ]


user32.UpdateLayeredWindow.argtypes = [
    wt.HWND, wt.HDC, ctypes.POINTER(_POINT), ctypes.POINTER(_SIZE),
    wt.HDC, ctypes.POINTER(_POINT), wt.COLORREF,
    ctypes.POINTER(_BLENDFUNCTION), wt.DWORD]
user32.UpdateLayeredWindow.restype = wt.BOOL

user32.RegisterClassExW.argtypes = [ctypes.POINTER(_WNDCLASSEX)]
user32.RegisterClassExW.restype = wt.ATOM
user32.CreateWindowExW.argtypes = [
    wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD, ctypes.c_int, ctypes.c_int,
    ctypes.c_int, ctypes.c_int, wt.HWND, wt.HMENU, wt.HINSTANCE, wt.LPVOID]
user32.CreateWindowExW.restype = wt.HWND
user32.DefWindowProcW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.DefWindowProcW.restype = ctypes.c_long
user32.ShowWindow.argtypes = [wt.HWND, ctypes.c_int]
user32.DestroyWindow.argtypes = [wt.HWND]
user32.SetWindowPos.argtypes = [
    wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.UINT]
user32.GetMessageW.argtypes = [ctypes.POINTER(wt.MSG), wt.HWND, wt.UINT, wt.UINT]
user32.DispatchMessageW.argtypes = [ctypes.POINTER(wt.MSG)]
user32.TranslateMessage.argtypes = [ctypes.POINTER(wt.MSG)]
user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]

# style bits
WS_EX_LAYERED = 0x00080000
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOPMOST = 0x00000008
WS_POPUP = 0x80000000
SW_SHOW = 5
SW_HIDE = 0
ULW_ALPHA = 2
AC_SRC_OVER = 0
AC_SRC_ALPHA = 1

WM_DESTROY = 0x0002
WM_LBUTTONUP = 0x0202
WM_RBUTTONUP = 0x0205
WM_LBUTTONDOWN = 0x0201
WM_MOUSEMOVE = 0x0200
WM_NCHITTEST = 0x0084
WM_TIMER = 0x0113
WM_PAINT = 0x000F
WM_DISPLAYCHANGE = 0x007E
WM_MOUSELEAVE = 0x02A3
WM_CAPTURECHANGED = 0x0215
WM_ENTERSIZEMOVE = 0x0231
WM_EXITSIZEMOVE = 0x0232
TRACKMOUSEEVENT = 0x0020

HTCLIENT = 1

SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_NOREDRAW = 0x0008

HWND_TOPMOST = wt.HWND(-1)


class LayeredWindow:
    """A borderless per-pixel-alpha window.

    Callbacks (all optional, set as attributes):
        on_click(x, y)      left click inside the window, in image pixels
        on_move(x, y)       window moved by dragging
        on_close()          window asked to close
    """

    def __init__(self, title: str = "panel"):
        self._hwnd: Optional[wt.HWND] = None
        self._title = title
        self._cursor = None
        self._class_atom = None
        self._image: Optional[Image.Image] = None
        self._proc = WNDPROC(self._wndproc)  # keep a reference: ctypes GCs it

        self.on_click = None
        self.on_move = None
        self.on_leave = None
        self.on_drag_end = None
        self.on_close = None

        self._drag_origin = None
        self._drag_pos = (0, 0)
        self._dragging = False
        self._captured = False
        self._tracking_leave = False

        hinst = kernel32.GetModuleHandleW(None)
        cls_name = f"PyHwMon_{title}"

        wc = _WNDCLASSEX()
        wc.cbSize = ctypes.sizeof(_WNDCLASSEX)
        wc.style = 0
        wc.lpfnWndProc = self._proc
        wc.hInstance = hinst
        wc.hCursor = user32.LoadCursorW(None, ctypes.c_wchar_p(32512))  # IDC_ARROW
        wc.lpszClassName = cls_name
        self._class_atom = user32.RegisterClassExW(ctypes.byref(wc))
        self._hinst = hinst
        self._cls_name = cls_name

    def _wndproc(self, hwnd, msg, wparam, lparam):
        try:
            x = ctypes.c_short(lparam & 0xFFFF).value
            y = ctypes.c_short((lparam >> 16) & 0xFFFF).value

            if msg == WM_ENTERSIZEMOVE:
                self._in_sizemove = True
                return 0

            if msg == WM_EXITSIZEMOVE:
                self._in_sizemove = False
                return 0

            if msg == WM_LBUTTONDOWN:
                self._drag_origin = (x, y)
                self._drag_pos = self.get_position()
                self._dragging = False
                self._drag_moved = False
                self._captured = bool(user32.SetCapture(hwnd))
                return 0

            if msg == WM_MOUSEMOVE:
                # Ask for exactly one leave notification per entry, so the
                # hover highlight can be cleared reliably.
                if not self._tracking_leave:
                    tme = _TRACKMOUSEEVENT()
                    tme.cbSize = ctypes.sizeof(_TRACKMOUSEEVENT)
                    tme.dwFlags = 0x00000002  # TME_LEAVE
                    tme.hwndTrack = hwnd
                    tme.dwHoverTime = 0
                    if user32.TrackMouseEvent(ctypes.byref(tme)):
                        self._tracking_leave = True

                if self._drag_origin is not None:
                    ox, oy = self._drag_origin
                    if not self._dragging and (abs(x - ox) > 3 or abs(y - oy) > 3):
                        self._dragging = True
                    if self._dragging:
                        px, py = self._drag_pos
                        # Moving the window does not need a repaint: the layered
                        # surface travels with it. Re-uploading the bitmap here
                        # is what made dragging stutter.
                        user32.SetWindowPos(
                            hwnd, HWND_TOPMOST,
                            px + (x - ox), py + (y - oy), 0, 0,
                            SWP_NOSIZE | SWP_NOACTIVATE | SWP_NOREDRAW)
                        self._drag_moved = True
                        return 0
                if self.on_move:
                    self.on_move(x, y)
                return 0

            if msg == WM_LBUTTONUP:
                was_drag = self._dragging
                self._drag_origin = None
                self._dragging = False
                if self._captured:
                    try:
                        user32.ReleaseCapture()
                    except Exception:
                        pass
                    self._captured = False

                if was_drag:
                    if self.on_drag_end:
                        self.on_drag_end()
                elif self.on_click:
                    self.on_click(x, y)
                return 0

            if msg == WM_MOUSELEAVE:
                self._tracking_leave = False
                if self.on_leave:
                    self.on_leave()
                return 0

            if msg == WM_DESTROY:
                if self.on_close:
                    self.on_close()
                return 0

            if msg == WM_NCHITTEST:
                return HTCLIENT
        except Exception:
            pass
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    # -- lifecycle --------------------------------------------------------
    def create(self, x: int, y: int, w: int, h: int):
        # NOACTIVATE keeps the panel from stealing focus, but it does not stop
        # mouse messages; the hover/drag handling lives in _wndproc.
        ex_style = WS_EX_LAYERED | WS_EX_TOOLWINDOW | WS_EX_TOPMOST | WS_EX_NOACTIVATE
        self._hwnd = user32.CreateWindowExW(
            ex_style, self._cls_name, self._title, WS_POPUP,
            x, y, w, h, None, None, self._hinst, None)
        return self._hwnd

    def show(self):
        if self._hwnd:
            user32.ShowWindow(self._hwnd, SW_SHOW)

    def hide(self):
        if self._hwnd:
            user32.ShowWindow(self._hwnd, SW_HIDE)

    def move(self, x: int, y: int, w: int, h: int):
        if self._hwnd:
            user32.SetWindowPos(self._hwnd, HWND_TOPMOST, x, y, w, h,
                                SWP_NOACTIVATE)
            if self._image is not None:
                self.set_image(self._image)

    def destroy(self):
        if self._hwnd:
            try:
                user32.DestroyWindow(self._hwnd)
            except Exception:
                pass
            self._hwnd = None

    def alive(self) -> bool:
        """True when the window handle still exists."""
        return bool(self._hwnd and user32.IsWindow(self._hwnd))

    def get_position(self) -> tuple[int, int]:
        r = wt.RECT()
        if self._hwnd and user32.GetWindowRect(self._hwnd, ctypes.byref(r)):
            return (r.left, r.top)
        return (0, 0)

    # -- painting ---------------------------------------------------------
    def set_image(self, img: Image.Image):
        """Uploads an ARGB image to the window surface."""
        if not self._hwnd:
            return
        self._image = img

        w, h = img.size
        bgra = img.convert("RGBA").tobytes("raw", "BGRA")

        screen_dc = user32.GetDC(None)
        mem_dc = gdi32.CreateCompatibleDC(screen_dc)
        bmp = gdi32.CreateCompatibleBitmap(screen_dc, w, h)
        old = gdi32.SelectObject(mem_dc, bmp)

        bi = _BITMAPINFOHEADER()
        bi.biSize = ctypes.sizeof(_BITMAPINFOHEADER)
        bi.biWidth = w
        bi.biHeight = -h
        bi.biPlanes = 1
        bi.biBitCount = 32
        bi.biCompression = 0
        gdi32.SetDIBits(mem_dc, bmp, 0, h, bgra, ctypes.byref(bi), 0)

        pos = self.get_position()
        dst = _POINT(pos[0], pos[1])
        size = _SIZE(w, h)
        src = _POINT(0, 0)
        blend = _BLENDFUNCTION(AC_SRC_OVER, 0, 255, AC_SRC_ALPHA)

        user32.UpdateLayeredWindow(self._hwnd, screen_dc, ctypes.byref(dst),
                                   ctypes.byref(size), mem_dc, ctypes.byref(src),
                                   0, ctypes.byref(blend), ULW_ALPHA)

        gdi32.SelectObject(mem_dc, old)
        gdi32.DeleteObject(bmp)
        gdi32.DeleteDC(mem_dc)
        user32.ReleaseDC(None, screen_dc)
