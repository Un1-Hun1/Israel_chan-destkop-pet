"""PixelPet — a tiny pixel anime girl who lives on your Windows desktop.

Run with pythonw.exe. A small widget on the desktop toggles her on/off;
launching the script again while it is running toggles her too.
"""
import ctypes
import ctypes.wintypes as wt
import json
import math
import os
import random
import re
import socket
import subprocess
import sys
import threading
import tkinter as tk

from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageTk

import sprites

FROZEN = getattr(sys, "frozen", False)  # running as a PyInstaller .exe
# user files (config, phrases, log) live next to the script / the .exe
APP_DIR = os.path.dirname(sys.executable if FROZEN else os.path.abspath(__file__))
BUNDLE_DIR = getattr(sys, "_MEIPASS", APP_DIR)  # read-only files packed into the .exe
CONFIG_PATH = os.path.join(APP_DIR, "config.json")
ICON_PATH = os.path.join(APP_DIR, "icon.ico")
IPC_PORT = 47823
PET_NAME = "Момо"
TICK_MS = 33

# ---------------------------------------------------------------- Win32 ---

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    ctypes.windll.user32.SetProcessDPIAware()

user32 = ctypes.windll.user32
dwmapi = ctypes.windll.dwmapi

WNDENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
MONITORENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HMONITOR, wt.HDC,
                                     ctypes.POINTER(wt.RECT), wt.LPARAM)


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("rcMonitor", wt.RECT),
                ("rcWork", wt.RECT), ("dwFlags", wt.DWORD)]


user32.EnumWindows.argtypes = [WNDENUMPROC, wt.LPARAM]
user32.EnumDisplayMonitors.argtypes = [wt.HDC, ctypes.c_void_p, MONITORENUMPROC, wt.LPARAM]
user32.GetMonitorInfoW.argtypes = [wt.HMONITOR, ctypes.POINTER(MONITORINFO)]
user32.IsWindowVisible.argtypes = [wt.HWND]
user32.IsIconic.argtypes = [wt.HWND]
user32.GetWindowTextLengthW.argtypes = [wt.HWND]
user32.GetClassNameW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
user32.GetWindowLongW.argtypes = [wt.HWND, ctypes.c_int]
user32.GetWindowLongW.restype = ctypes.c_long
user32.SetWindowLongW.argtypes = [wt.HWND, ctypes.c_int, ctypes.c_long]
user32.GetWindowRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
user32.GetForegroundWindow.restype = wt.HWND
user32.GetParent.argtypes = [wt.HWND]
user32.GetParent.restype = wt.HWND
user32.SetWindowPos.argtypes = [wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int, wt.UINT]
user32.ShowWindow.argtypes = [wt.HWND, ctypes.c_int]
dwmapi.DwmGetWindowAttribute.argtypes = [wt.HWND, wt.DWORD, ctypes.c_void_p, wt.DWORD]

GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x80
WS_EX_APPWINDOW = 0x40000
WS_EX_TRANSPARENT = 0x20
WS_EX_NOACTIVATE = 0x08000000
DWMWA_EXTENDED_FRAME_BOUNDS = 9
DWMWA_CLOAKED = 14
HWND_BOTTOM = 1
SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE = 0x1, 0x2, 0x10
SW_SHOWNOACTIVATE = 4

SKIP_CLASSES = {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd",
                "Windows.UI.Core.CoreWindow", "ApplicationFrameWindow_Hidden",
                "TopLevelWindowForOverflowXamlIsland", "XamlExplorerHostIslandWindow"}
DESKTOP_CLASSES = {"Progman", "WorkerW"}
OWN_PID = os.getpid()


def class_name(hwnd):
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def window_rect(hwnd):
    r = wt.RECT()
    if dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_EXTENDED_FRAME_BOUNDS,
                                    ctypes.byref(r), ctypes.sizeof(r)) != 0:
        user32.GetWindowRect(hwnd, ctypes.byref(r))
    return r.left, r.top, r.right, r.bottom


def monitors():
    """List of (monitor_rect, work_rect) tuples."""
    out = []

    def cb(hmon, hdc, rect, lp):
        mi = MONITORINFO()
        mi.cbSize = ctypes.sizeof(mi)
        user32.GetMonitorInfoW(hmon, ctypes.byref(mi))
        m, w = mi.rcMonitor, mi.rcWork
        out.append(((m.left, m.top, m.right, m.bottom),
                    (w.left, w.top, w.right, w.bottom)))
        return True

    user32.EnumDisplayMonitors(None, None, MONITORENUMPROC(cb), 0)
    return out


def top_level_windows():
    """Visible app windows, topmost first: [(hwnd, (l, t, r, b))]."""
    wins = []

    def cb(hwnd, lp):
        if not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
            return True
        if user32.GetWindowTextLengthW(hwnd) == 0:
            return True
        ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        if ex & (WS_EX_TRANSPARENT | WS_EX_NOACTIVATE):
            return True
        if ex & WS_EX_TOOLWINDOW and not ex & WS_EX_APPWINDOW:
            return True
        cloaked = wt.DWORD()
        dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(cloaked), 4)
        if cloaked.value:
            return True
        pid = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == OWN_PID:
            return True
        if class_name(hwnd) in SKIP_CLASSES:
            return True
        rect = window_rect(hwnd)
        if rect[2] - rect[0] < 120 or rect[3] - rect[1] < 60:
            return True
        wins.append((hwnd, rect))
        return True

    user32.EnumWindows(WNDENUMPROC(cb), 0)
    return wins


def subtract(segs, a, b):
    out = []
    for x1, x2 in segs:
        if b <= x1 or a >= x2:
            out.append((x1, x2))
            continue
        if a > x1:
            out.append((x1, a))
        if b < x2:
            out.append((b, x2))
    return out


class Surface:
    __slots__ = ("hwnd", "y", "x1", "x2")

    def __init__(self, hwnd, y, x1, x2):
        self.hwnd, self.y, self.x1, self.x2 = hwnd, y, x1, x2

    def has(self, x, pad=0):
        return self.x1 + pad <= x <= self.x2 - pad


def scan_world(clearance):
    """Return (surfaces, rects_by_hwnd, monitors)."""
    mons = monitors()
    wins = top_level_windows()
    rects = {h: r for h, r in wins}
    surfaces = []
    for i, (hwnd, (l, t, r, b)) in enumerate(wins):
        mon = next((m for m, _ in mons if m[0] <= (l + r) // 2 < m[2] and m[1] <= t < m[3]), None)
        if mon is None or t - mon[1] < clearance:
            continue
        segs = [(l, r)]
        for _, (l2, t2, r2, b2) in wins[:i]:
            if t2 <= t + 1 and b2 > t:
                segs = subtract(segs, l2, r2)
        for x1, x2 in segs:
            if x2 - x1 >= 60:
                surfaces.append(Surface(hwnd, t, x1, x2))
    for _, (l, t, r, b) in mons:
        surfaces.append(Surface(None, b, l, r))
    return surfaces, rects, mons


def set_ex_style(hwnd, add):
    user32.SetWindowLongW(hwnd, GWL_EXSTYLE, user32.GetWindowLongW(hwnd, GWL_EXSTYLE) | add)


def foreground_is_fullscreen(mons):
    hwnd = user32.GetForegroundWindow()
    if not hwnd or class_name(hwnd) in DESKTOP_CLASSES:
        return False
    pid = wt.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if pid.value == OWN_PID:
        return False
    r = wt.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    return any((r.left, r.top, r.right, r.bottom) == m for m, _ in mons)


# --------------------------------------------------------------- config ---

DEFAULT_CONFIG = {"pet_on": True, "widget_x": None, "widget_y": None, "size": 2.4}


def load_config():
    cfg = dict(DEFAULT_CONFIG)
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            cfg.update(json.load(f))
    except Exception:
        pass
    return cfg


def save_config(cfg):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        pass


def log_error():
    import traceback
    try:
        with open(os.path.join(APP_DIR, "errors.log"), "a", encoding="utf-8") as f:
            traceback.print_exc(file=f)
    except Exception:
        pass


def dpi_factor():
    try:
        return user32.GetDpiForSystem() / 96
    except Exception:
        return 1.0


# ------------------------------------------------------------------ pet ---

KEY_HEX = "#%02x%02x%02x" % sprites.KEY

STATUS = {
    "idle": "стоит", "walk": "гуляет", "sit": "сидит", "sleep": "спит",
    "fall": "падает!", "jump": "прыгает", "drag": "в руках", "happy": "довольна ♥",
    "rocket": "летит на ракете!", "parachute": "на парашюте",
}


class FlyingRocket:
    """The empty rocket zooming off after she bails out."""

    def __init__(self, root):
        self.root = root
        self.win = tk.Toplevel(root)
        self.win.withdraw()
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.attributes("-transparentcolor", KEY_HEX)
        self.win.configure(bg=KEY_HEX)
        self.label = tk.Label(self.win, bd=0, highlightthickness=0, bg=KEY_HEX)
        self.label.pack()
        self.active = False
        self.styled = False

    def launch(self, x, y, direction, images, scale, bounds):
        self.x, self.y, self.dir = float(x), float(y), direction
        self.vx, self.vy = direction * 3.0 * scale, -0.5 * scale
        self.images, self.scale, self.bounds = images, scale, bounds
        self.t = 0
        self.active = True
        self.tick()
        self.win.deiconify()
        self.win.attributes("-topmost", True)
        if not self.styled:
            self.win.update_idletasks()
            set_ex_style(user32.GetParent(self.win.winfo_id()),
                         WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE | WS_EX_TRANSPARENT)
            self.styled = True

    def tick(self):
        if not self.active:
            return
        self.t += 1
        self.vx *= 1.06
        self.vy -= 0.12 * self.scale
        self.x += self.vx
        self.y += self.vy
        img = self.images[(f"rocket_only{1 + (self.t // 3) % 2}", self.dir)]
        left, top, right, bottom = self.bounds
        if self.t > 200 or self.x > right + 50 or self.x + img.width() < left - 50 \
                or self.y + img.height() < top - 50:
            self.active = False
            self.win.withdraw()
            return
        self.label.configure(image=img)
        self.win.geometry(f"{img.width()}x{img.height()}+{int(self.x)}+{int(self.y)}")


PHRASES_PATH = os.path.join(APP_DIR, "phrases.txt")
HEBREW = re.compile(r"[֐-׿]")


def load_phrases():
    groups, cur = {}, "random"
    path = PHRASES_PATH
    if not os.path.exists(path):
        path = os.path.join(BUNDLE_DIR, "phrases.txt")
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("[") and line.endswith("]"):
                    cur = line[1:-1].strip().lower()
                    continue
                groups.setdefault(cur, []).append(line)
    except Exception:
        log_error()
    return groups


def load_font(size):
    for name in ("segoeuib.ttf", "segoeui.ttf", "arial.ttf"):
        try:
            # BASIC layout: we do right-to-left ordering for Hebrew ourselves
            return ImageFont.truetype(name, size, layout_engine=ImageFont.Layout.BASIC)
        except OSError:
            continue
    return ImageFont.load_default()


def wrap(text, font, max_w):
    lines, cur = [], ""
    for word in text.split():
        cand = f"{cur} {word}".strip()
        if cur and font.getlength(cand) > max_w:
            lines.append(cur)
            cur = word
        else:
            cur = cand
    if cur:
        lines.append(cur)
    return lines


class Bubble:
    """Thought cloud above the pet's head: dot, dot, "...", then the phrase."""
    DOT1, DOT2, DOTS, TEXT = 8, 16, 34, 34

    def __init__(self, root):
        self.root = root
        self.win = tk.Toplevel(root)
        self.win.withdraw()
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.attributes("-transparentcolor", KEY_HEX)
        self.win.configure(bg=KEY_HEX)
        self.label = tk.Label(self.win, bd=0, highlightthickness=0, bg=KEY_HEX)
        self.label.pack()
        self.u = max(2, round(2 * dpi_factor()))
        self.font = load_font(round(12 * dpi_factor()))
        self.active = False
        self.styled = False
        self.shown = None

    def say(self, text, side):
        self.side = side
        self.images = self.make_images(text, side)
        self.t = 0
        self.duration = self.TEXT + 100 + 3 * len(text)
        self.active = True
        self.shown = None

    def close(self):
        self.active = False
        self.shown = None
        self.win.withdraw()

    def make_images(self, text, side):
        u, font = self.u, self.font
        lines = []
        for part in text.split("|"):
            lines += wrap(part.strip(), font, 190 * dpi_factor())
        lines = [l[::-1] if HEBREW.search(l) else l for l in lines]
        asc, desc = font.getmetrics()
        lh = asc + desc
        tw = max(font.getlength(l) for l in lines)
        th = lh * len(lines)

        R, P = 2, 3  # cloud corner radius and inner padding, in cloud pixels
        tw_u, th_u = -(-int(tw) // u), -(-th // u)
        ix1, iy1 = R + 1, R + 1
        ix2, iy2 = ix1 + tw_u + 2 * P, iy1 + th_u + 2 * P
        cw, ch = ix2 + R + 2, iy2 + R + 2
        dots_h = 10
        W, H = cw, ch + dots_h

        def draw_cloud(d):
            box = (ix1 - R, iy1 - R, ix2 + R, iy2 + R)
            d.rounded_rectangle(box, radius=R + 1, fill=outline)
            inner = (box[0] + 1, box[1] + 1, box[2] - 1, box[3] - 1)
            d.rounded_rectangle(inner, radius=R, fill=white)

        def dot_positions():
            big = (ix1 + 4, ch + 2, 2)
            small = (ix1 + 1, ch + 7, 1)
            if side < 0:
                big = (W - 1 - big[0], big[1], big[2])
                small = (W - 1 - small[0], small[1], small[2])
            return big, small

        outline = sprites.PALETTE["K"]
        white = (255, 255, 255)
        big, small = dot_positions()

        def stage(dots, cloud, txt):
            small_img = Image.new("RGB", (W, H), sprites.KEY)
            d = ImageDraw.Draw(small_img)
            if cloud:
                draw_cloud(d)
            for i, (x, y, r) in enumerate((small, big)[:dots]):
                d.ellipse((x - r - 1, y - r - 1, x + r + 1, y + r + 1), fill=outline)
                d.ellipse((x - r, y - r, x + r, y + r), fill=white)
            img = small_img.resize((W * u, H * u), Image.NEAREST)
            if txt:
                d = ImageDraw.Draw(img)
                tlines = txt
                block_h = lh * len(tlines)
                cy = ((iy1 + iy2) * u) // 2 - block_h // 2
                cx = ((ix1 + ix2) * u) // 2
                for i, l in enumerate(tlines):
                    lw = font.getlength(l)
                    d.text((cx - lw / 2, cy + i * lh), l, font=font, fill=outline)
            return ImageTk.PhotoImage(img)

        anchor = (small[0] * u, small[1] * u)
        return {
            "dot1": stage(1, False, None),
            "dot2": stage(2, False, None),
            "dots": stage(2, True, ["..."]),
            "text": stage(2, True, lines),
            "anchor": anchor,
            "size": (W * u, H * u),
        }

    def tick(self, anchor_x, anchor_y, bounds):
        if not self.active:
            return
        self.t += 1
        if self.t > self.duration:
            self.close()
            return
        if self.t < self.DOT1:
            key = "dot1"
        elif self.t < self.DOT2:
            key = "dot2"
        elif self.t < self.DOTS:
            key = "dots"
        else:
            key = "text"
        if key != self.shown:
            self.shown = key
            self.label.configure(image=self.images[key])
        ax, ay = self.images["anchor"]
        w, h = self.images["size"]
        x = int(anchor_x - ax)
        y = int(anchor_y - ay)
        left, top, right, bottom = bounds
        x = max(left, min(x, right - w))
        y = max(top, min(y, bottom - h))
        self.win.geometry(f"{w}x{h}+{x}+{y}")
        if self.win.state() == "withdrawn":
            self.win.deiconify()
            self.win.attributes("-topmost", True)
            if not self.styled:
                self.win.update_idletasks()
                set_ex_style(user32.GetParent(self.win.winfo_id()),
                             WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE | WS_EX_TRANSPARENT)
                self.styled = True


class Pet:
    def __init__(self, root, size):
        self.root = root
        self.win = tk.Toplevel(root)
        self.win.withdraw()
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.attributes("-transparentcolor", KEY_HEX)
        self.win.configure(bg=KEY_HEX)
        self.label = tk.Label(self.win, bd=0, highlightthickness=0, bg=KEY_HEX)
        self.label.pack()
        self.label.bind("<ButtonPress-1>", self.on_press)
        self.label.bind("<B1-Motion>", self.on_motion)
        self.label.bind("<ButtonRelease-1>", self.on_release)
        self.label.bind("<Button-3>", self.on_menu)

        self.menu = tk.Menu(self.win, tearoff=0)
        self.menu.add_command(label="Погладить ♥", command=self.pet_her)
        self.menu.add_command(label="Скажи что-нибудь", command=lambda: self.chatter())
        self.menu.add_command(label="Полетать на ракете", command=self.rocket_now)
        self.menu.add_command(label="Спрятать", command=lambda: self.on_hide_request())
        self.on_hide_request = lambda: None

        self.set_size(size)
        self.visible = False
        self.running = False
        self.hidden_for_fullscreen = False
        self.surfaces, self.rects, self.mons = [], {}, []
        self.state = "fall"
        self.surface = None
        self.surface_rect = None
        self.x = self.y = 0.0
        self.vx = self.vy = 0.0
        self.dir = 1
        self.timer = 0
        self.t = 0
        self.frame_key = None
        self.geom = None
        self.drag_off = (0, 0)
        self.drag_hist = []
        self.press_pos = None
        self.dragging = False
        self.bubble = Bubble(root)
        self.flyer = FlyingRocket(root)
        self.talk_timer = random.randint(90, 240)
        self.rocket_timer = random.randint(450, 700)
        self.waypoints = []
        self.air_t = 0

    # -- setup ------------------------------------------------------------
    def set_size(self, size):
        self.scale = max(1, round(size * dpi_factor()))
        imgs = sprites.frames(self.scale)
        self.images, self.sizes, self.feet = {}, {}, {}
        for name, img in imgs.items():
            self.images[(name, 1)] = ImageTk.PhotoImage(img)
            self.images[(name, -1)] = ImageTk.PhotoImage(ImageOps.mirror(img))
            self.sizes[name] = img.size
            self.feet[name] = sprites.FOOT_ROWS[name] * self.scale
        self.w = sprites.GRID_W * self.scale
        self.h = sprites.GRID_H * self.scale
        self.body_h = (sprites.GRID_H - sprites.TOP_MARGIN) * self.scale
        self.g = 0.35 * self.scale
        self.speed = 0.55 * self.scale
        self.frame_key = None
        self.geom = None

    def hwnd(self):
        return user32.GetParent(self.win.winfo_id())

    def show(self):
        if self.visible:
            return
        self.visible = True
        self.refresh_world()
        self.spawn()
        self.render()
        self.win.deiconify()
        self.win.attributes("-topmost", True)
        self.win.update_idletasks()
        set_ex_style(self.hwnd(), WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE)
        if not self.running:
            self.running = True
            self.loop()

    def hide(self):
        self.visible = False
        self.win.withdraw()
        self.bubble.close()
        self.flyer.active = False
        self.flyer.win.withdraw()

    def talk(self, group):
        # re-read every time so edits to phrases.txt apply without a restart
        options = load_phrases().get(group)
        if not options or not self.visible:
            return
        right = max((m[2] for m, _ in self.mons), default=1920)
        side = 1 if self.x + 260 * dpi_factor() < right else -1
        self.bubble.say(random.choice(options), side)
        self.talk_timer = random.randint(240, 600)  # next chatter in ~8-20 s

    def chatter(self):
        self.talk("hebrew" if random.random() < 0.65 else "random")

    def spawn(self, x=None):
        mon, work = next(((m, w) for m, w in self.mons if m[0] == 0 and m[1] == 0),
                         self.mons[0] if self.mons else ((0, 0, 1920, 1080),) * 2)
        self.x = float(x if x is not None else random.randint(work[0] + 150, work[2] - 150))
        self.y = float(mon[1] - 10)
        self.vx, self.vy = 0.0, 0.0
        self.state = "fall"
        self.surface = None

    # -- world ------------------------------------------------------------
    def refresh_world(self):
        self.surfaces, self.rects, self.mons = scan_world(self.body_h)

    def grounded_surface_update(self):
        """Keep standing on the current surface (follow moving windows)."""
        s = self.surface
        if s.hwnd is not None:
            rect = self.rects.get(s.hwnd)
            if rect is None:
                return False
            if self.surface_rect:  # ride along when the window is moved
                self.x += rect[0] - self.surface_rect[0]
            self.surface_rect = rect
            self.y = rect[1]
            for cand in self.surfaces:
                if cand.hwnd == s.hwnd and cand.has(self.x):
                    self.surface = cand
                    return True
            return False
        for cand in self.surfaces:
            if cand.hwnd is None and abs(cand.y - s.y) <= 2 and cand.has(self.x):
                self.surface = cand
                self.y = cand.y
                return True
        return False

    def land(self, s):
        if self.vy > 6 * self.scale and random.random() < 0.5:
            self.talk("land")
        self.surface = s
        self.surface_rect = self.rects.get(s.hwnd) if s.hwnd else None
        self.y = s.y
        self.vx = self.vy = 0.0
        self.set_state("idle", random.randint(20, 50))

    def fall(self, vx=0.0, vy=0.0):
        self.surface = None
        self.vx, self.vy = vx, vy
        self.state = "fall"

    # -- behaviour --------------------------------------------------------
    def set_state(self, state, ticks):
        self.state = state
        self.timer = ticks

    def choose_next(self):
        r = random.random()
        if r < 0.42:
            self.dir = random.choice((-1, 1))
            self.set_state("walk", random.randint(60, 240))
        elif r < 0.58:
            self.set_state("sit", random.randint(150, 450))
        elif r < 0.64:
            self.set_state("sleep", random.randint(300, 800))
        elif r < 0.80 and self.try_jump():
            pass
        else:
            self.set_state("idle", random.randint(40, 120))

    def try_jump(self):
        cur = self.surface
        options = []
        for s in self.surfaces:
            if s is cur or s.hwnd is None:
                continue
            dy = cur.y - s.y
            if 40 <= dy <= 650:
                tx = min(max(self.x, s.x1 + 40), s.x2 - 40)
                if abs(tx - self.x) <= 700:
                    options.append((s, tx))
        if not options:
            return False
        s, tx = random.choice(options)
        tx += random.uniform(-30, 30)
        tx = min(max(tx, s.x1 + 30), s.x2 - 30)
        dy = self.y - s.y + 30
        vy0 = -((2 * self.g * dy) ** 0.5)
        t_up = -vy0 / self.g
        t_down = (2 * 30 / self.g) ** 0.5
        self.vx = (tx - self.x) / (t_up + t_down)
        self.vy = vy0
        self.dir = 1 if self.vx >= 0 else -1
        self.surface = None
        self.state = "jump"
        return True

    def status(self):
        if self.state in ("sit", "idle") and self.surface is not None and self.surface.hwnd:
            return "сидит на окне" if self.state == "sit" else "на окне"
        return STATUS.get(self.state, "")

    def pet_her(self):
        if self.surface is None:
            return
        if self.state == "sleep":
            self.set_state("idle", 60)
            self.talk("wake")
            return
        self.set_state("happy", 50)
        if random.random() < 0.7:
            self.talk("click")

    def step(self):
        self.t += 1
        if self.t % 3 == 0 or self.surface is not None and self.surface.hwnd:
            self.refresh_world()

        if self.state == "drag":
            return

        if self.state == "rocket":
            self.rocket_step()
            return

        if self.state == "parachute":
            self.air_t += 1
            self.vy = min(self.vy + self.g * 0.25, 0.8 * self.scale)
            self.vx = math.sin(self.air_t / 25) * 0.6 * self.scale
            self.move_airborne()
            return

        if self.state in ("fall", "jump"):
            self.vy = min(self.vy + self.g, 12 * self.scale)
            self.move_airborne()
            return

        if not self.grounded_surface_update():
            self.fall(vx=self.dir * self.speed if self.state == "walk" else 0)
            return

        self.timer -= 1
        if self.state != "sleep" and not self.bubble.active:
            self.talk_timer -= 1
            if self.talk_timer <= 0:
                self.chatter()
        if self.state in ("idle", "walk", "sit", "happy"):
            self.rocket_timer -= 1
            if self.rocket_timer <= 0:
                self.start_rocket()
                return
        if self.state == "walk":
            self.walk()
        if self.timer <= 0:
            self.choose_next()

    def move_airborne(self):
        ny = self.y + self.vy
        nx = self.x + self.vx
        if self.vy > 0:
            hits = [s for s in self.surfaces if self.y <= s.y <= ny and s.has(nx)]
            if hits:
                self.x = nx
                self.land(min(hits, key=lambda s: s.y))
                return
        self.x, self.y = nx, ny
        self.keep_on_screen()
        if self.y > max((w[3] for _, w in self.mons), default=1080) + 400:
            self.spawn()

    def current_monitor(self):
        for m, work in self.mons:
            if m[0] <= self.x < m[2]:
                return work
        return self.mons[0][1] if self.mons else (0, 0, 1920, 1040)

    def start_rocket(self):
        left, top, right, bottom = self.current_monitor()
        h = bottom - top
        self.waypoints = [(random.randint(left + 150, right - 150),
                           random.randint(top + h // 5, top + h * 3 // 5))
                          for _ in range(random.randint(3, 5))]
        self.surface = None
        self.state = "rocket"
        self.air_t = 0
        self.vx, self.vy = 0.0, 0.0
        self.rocket_timer = random.randint(850, 1000)  # ~30 s on the ground
        if random.random() < 0.8:
            self.talk("rocket")

    def rocket_now(self):
        if self.surface is not None and self.state not in ("rocket", "parachute"):
            self.start_rocket()

    def rocket_step(self):
        self.air_t += 1
        if self.air_t < 25:  # ignition: rumble in place
            self.x += random.choice((-1, 1))
            return
        if not self.waypoints or self.air_t > 700:
            self.bail_out()
            return
        tx, ty = self.waypoints[0]
        dx, dy = tx - self.x, ty - self.y
        dist = math.hypot(dx, dy) or 1
        sp = 3.0 * self.scale
        self.vx += (dx / dist * sp - self.vx) * 0.05
        self.vy += (dy / dist * sp - self.vy) * 0.05
        self.x += self.vx
        self.y += self.vy + math.sin(self.air_t / 6) * 0.4 * self.scale
        if abs(self.vx) > 0.6:
            self.dir = 1 if self.vx > 0 else -1
        if dist < 50:
            self.waypoints.pop(0)

    def bail_out(self):
        w, h = self.sizes["rocket1"]
        rocket_h = len(sprites.ROCKET) * self.scale
        rx = self.x - w / 2
        ry = self.y - self.feet["rocket1"] + h - rocket_h
        self.flyer.launch(rx, ry, self.dir, self.images, self.scale, self.screen_bounds())
        self.state = "parachute"
        self.air_t = 0
        self.vx, self.vy = 0.0, -1.5 * self.scale
        if random.random() < 0.6:
            self.talk("parachute")

    def screen_bounds(self):
        return (min(m[0] for m, _ in self.mons), min(m[1] for m, _ in self.mons),
                max(m[2] for m, _ in self.mons), max(m[3] for m, _ in self.mons))

    def walk(self):
        self.x += self.dir * self.speed
        pad = 8 * self.scale
        s = self.surface
        if s.has(self.x, pad):
            return
        for cand in self.surfaces:
            if cand is not s and abs(cand.y - s.y) <= 3 and cand.has(self.x, pad):
                self.surface = cand
                self.surface_rect = self.rects.get(cand.hwnd) if cand.hwnd else None
                return
        if s.hwnd is not None and random.random() < 0.4:
            self.fall(vx=self.dir * self.speed)
            return
        self.dir = -self.dir
        self.x = min(max(self.x, s.x1 + pad), s.x2 - pad)

    def keep_on_screen(self):
        if not self.mons:
            return
        left = min(m[0] for m, _ in self.mons)
        right = max(m[2] for m, _ in self.mons)
        pad = 8 * self.scale
        if self.x < left + pad:
            self.x, self.vx = left + pad, abs(self.vx) * 0.5
        elif self.x > right - pad:
            self.x, self.vx = right - pad, -abs(self.vx) * 0.5

    # -- rendering --------------------------------------------------------
    def current_frame(self):
        t, st = self.t, self.state
        on_ground = self.surface is not None and self.surface.hwnd is None
        g = "g" if on_ground else ""
        blink = t % 110 < 4
        if st == "walk":
            return "walk1" if (t // 7) % 2 == 0 else "walk2"
        if st == "sit":
            if blink:
                return g + "sit_blink"
            if on_ground:
                return "gsit1"
            return "sit1" if (t // 20) % 2 == 0 else "sit2"
        if st == "sleep":
            return g + ("sleep1" if (t // 25) % 2 == 0 else "sleep2")
        if st == "fall":
            return "fall"
        if st == "jump":
            return "jump" if self.vy < 0 else "fall"
        if st == "drag":
            return "drag1" if (t // 6) % 2 == 0 else "drag2"
        if st == "happy":
            return "happy1" if (t // 8) % 2 == 0 else "happy2"
        if st == "rocket":
            return "rocket1" if (t // 3) % 2 == 0 else "rocket2"
        if st == "parachute":
            return "para1" if (t // 20) % 2 == 0 else "para2"
        return "blink" if blink else "idle"

    def render(self):
        frame = self.current_frame()
        key = (frame, self.dir)
        if key != self.frame_key:
            self.frame_key = key
            self.label.configure(image=self.images[key])
        w, h = self.sizes[frame]
        wx = int(self.x - w / 2)
        wy = int(self.y - self.feet[frame])
        geom = f"{w}x{h}+{wx}+{wy}"
        if geom != self.geom:
            self.geom = geom
            self.win.geometry(geom)
        if self.bubble.active and self.mons:
            bounds = self.screen_bounds()
            # above the parachute canopy, otherwise just above her head
            head_top = wy + (0 if frame.startswith("para") else sprites.TOP_MARGIN * self.scale)
            self.bubble.tick(self.x + self.bubble.side * 6 * self.scale, head_top, bounds)

    def loop(self):
        if not self.visible:
            self.running = False
            return
        try:
            if self.t % 30 == 0:
                fs = foreground_is_fullscreen(self.mons)
                if fs != self.hidden_for_fullscreen:
                    self.hidden_for_fullscreen = fs
                    if fs:
                        self.win.withdraw()
                        self.bubble.close()
                    else:
                        self.win.deiconify()
                        self.win.attributes("-topmost", True)
            self.step()
            self.render()
            self.flyer.tick()
        except Exception:
            log_error()
        self.root.after(TICK_MS, self.loop)

    # -- mouse ------------------------------------------------------------
    def on_press(self, e):
        self.press_pos = (e.x_root, e.y_root)
        self.dragging = False
        self.drag_off = (e.x_root - self.x, e.y_root - self.y)
        self.drag_hist = [(e.x_root, e.y_root)]

    def on_motion(self, e):
        if self.press_pos is None:
            return
        if not self.dragging:
            dx, dy = e.x_root - self.press_pos[0], e.y_root - self.press_pos[1]
            if dx * dx + dy * dy < 25:
                return
            self.dragging = True
            self.state = "drag"
            if random.random() < 0.6:
                self.talk("drag")
            self.surface = None
            # hold her by the head
            self.drag_off = (0, -(sprites.GRID_H - sprites.TOP_MARGIN - 3) * self.scale)
        self.x = e.x_root - self.drag_off[0]
        self.y = e.y_root - self.drag_off[1]
        self.drag_hist = (self.drag_hist + [(e.x_root, e.y_root)])[-4:]
        self.render()

    def on_release(self, e):
        if self.dragging:
            h = self.drag_hist
            vx = (h[-1][0] - h[0][0]) / max(1, len(h) - 1)
            vy = (h[-1][1] - h[0][1]) / max(1, len(h) - 1)
            cap = 10 * self.scale
            vx, vy = max(-cap, min(cap, vx)), max(-cap, min(cap, vy))
            if abs(vx) > 1:
                self.dir = 1 if vx > 0 else -1
            self.fall(vx=vx, vy=vy)
        else:
            self.pet_her()
        self.dragging = False
        self.press_pos = None

    def on_menu(self, e):
        self.menu.tk_popup(e.x_root, e.y_root)


# --------------------------------------------------------------- widget ---

class Widget:
    BG = "#2a1f3d"
    ON = "#f07cb5"
    OFF = "#6b6380"

    def __init__(self, root, app):
        self.root, self.app = root, app
        f = dpi_factor()
        self.u = max(2, round(2 * f))          # one "pixel" of the widget
        self.W, self.H = self.u * 106, self.u * 30
        root.overrideredirect(True)
        root.configure(bg=KEY_HEX)
        root.attributes("-transparentcolor", KEY_HEX)
        self.c = tk.Canvas(root, width=self.W, height=self.H, bg=KEY_HEX,
                           highlightthickness=0, bd=0)
        self.c.pack()

        head_scale = max(1, round(1.5 * f))
        self.faces = {}
        for key, frame in (("on", "idle"), ("off", "sleep1")):
            img = sprites.frames(head_scale)[frame]
            s = head_scale
            box = (sprites.SIDE_MARGIN * s - s, sprites.TOP_MARGIN * s - s,
                   (sprites.SIDE_MARGIN + sprites.W) * s + s,
                   (sprites.TOP_MARGIN + sprites.HEAD_ROWS) * s)
            face = img.crop(box).convert("RGB")
            bg = tuple(int(self.BG[i:i + 2], 16) for i in (1, 3, 5))
            face.putdata([bg if p == sprites.KEY else p for p in face.getdata()])
            self.faces[key] = ImageTk.PhotoImage(face)

        cfg = app.cfg
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        x = cfg["widget_x"] if cfg["widget_x"] is not None else sw - self.W - 40
        y = cfg["widget_y"] if cfg["widget_y"] is not None else 40
        root.geometry(f"{self.W}x{self.H}+{x}+{y}")

        self.c.bind("<ButtonPress-1>", self.on_press)
        self.c.bind("<B1-Motion>", self.on_motion)
        self.c.bind("<ButtonRelease-1>", self.on_release)
        self.c.bind("<Button-3>", self.on_menu)
        self.press = None
        self.moved = False

        self.autostart_var = tk.BooleanVar(value=autostart_enabled())
        self.size_var = tk.DoubleVar(value=cfg["size"])
        self.menu = tk.Menu(root, tearoff=0)
        self.menu.add_command(label="Позвать сюда", command=app.call_here)
        sizes = tk.Menu(self.menu, tearoff=0)
        for label, val in (("Маленькая", 1.6), ("Средняя", 2.4), ("Большая", 3.2)):
            sizes.add_radiobutton(label=label, value=val, variable=self.size_var,
                                  command=lambda: app.set_size(self.size_var.get()))
        self.menu.add_cascade(label="Размер", menu=sizes)
        self.menu.add_checkbutton(label="Запускать с Windows", variable=self.autostart_var,
                                  command=lambda: set_autostart(self.autostart_var.get()))
        self.menu.add_separator()
        self.menu.add_command(label="Выход", command=app.quit)

        root.update_idletasks()
        self.hwnd = user32.GetParent(root.winfo_id())
        set_ex_style(self.hwnd, WS_EX_TOOLWINDOW)
        self.send_to_bottom()
        self.draw()
        self.watch()

    def send_to_bottom(self):
        user32.SetWindowPos(self.hwnd, HWND_BOTTOM, 0, 0, 0, 0,
                            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)

    def watch(self):
        # Survive "Show desktop" (Win+D): bring ourselves back if minimised.
        if user32.IsIconic(self.hwnd) or not user32.IsWindowVisible(self.hwnd):
            user32.ShowWindow(self.hwnd, SW_SHOWNOACTIVATE)
            self.send_to_bottom()
        self.draw()
        self.root.after(500, self.watch)

    def pixel_box(self, x1, y1, x2, y2, fill):
        """Rectangle with 1-pixel stepped corners (pixel-art rounded)."""
        u = self.u
        self.c.create_rectangle(x1 + u, y1, x2 - u, y2, fill=fill, width=0)
        self.c.create_rectangle(x1, y1 + u, x2, y2 - u, fill=fill, width=0)

    def draw(self):
        on = self.app.cfg["pet_on"]
        u, W, H = self.u, self.W, self.H
        accent = self.ON if on else self.OFF
        self.c.delete("all")
        self.pixel_box(0, 0, W, H, accent)
        self.pixel_box(u, u, W - u, H - u, self.BG)
        self.c.create_image(u * 3, H // 2, image=self.faces["on" if on else "off"], anchor="w")
        tx = u * 42
        self.c.create_text(tx, u * 10, text=PET_NAME, anchor="w", fill="white",
                           font=("Segoe UI", 10, "bold"))
        status = self.app.pet.status() if on else "выключена"
        self.c.create_text(tx, u * 20, text=status, anchor="w", fill=accent,
                           font=("Segoe UI", 8))
        # toggle switch
        sx1, sy1, sx2, sy2 = W - u * 26, H // 2 - u * 6, W - u * 5, H // 2 + u * 6
        self.pixel_box(sx1, sy1, sx2, sy2, accent)
        k = u * 10
        kx = sx2 - u - k if on else sx1 + u
        self.pixel_box(kx, sy1 + u, kx + k, sy2 - u, "white")

    def on_press(self, e):
        self.press = (e.x_root, e.y_root, self.root.winfo_x(), self.root.winfo_y())
        self.moved = False

    def on_motion(self, e):
        if not self.press:
            return
        dx, dy = e.x_root - self.press[0], e.y_root - self.press[1]
        if not self.moved and dx * dx + dy * dy < 16:
            return
        self.moved = True
        self.root.geometry(f"+{self.press[2] + dx}+{self.press[3] + dy}")

    def on_release(self, e):
        if self.moved:
            self.app.cfg["widget_x"] = self.root.winfo_x()
            self.app.cfg["widget_y"] = self.root.winfo_y()
            save_config(self.app.cfg)
        else:
            self.app.toggle()
        self.press = None
        self.send_to_bottom()

    def on_menu(self, e):
        self.autostart_var.set(autostart_enabled())
        self.menu.tk_popup(e.x_root, e.y_root)


# ----------------------------------------------------- autostart / links ---

STARTUP_LNK = os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs\Startup\PixelPet.lnk")


def pythonw():
    exe = sys.executable
    cand = os.path.join(os.path.dirname(exe), "pythonw.exe")
    return cand if os.path.exists(cand) else exe


def make_shortcut(path, args=""):
    if FROZEN:
        exe, arguments, icon = sys.executable, args, sys.executable
    else:
        exe, arguments, icon = pythonw(), f'"{os.path.abspath(__file__)}" {args}', ICON_PATH
    ps = (
        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:PP_LNK);"
        "$s.TargetPath=$env:PP_EXE;"
        "$s.Arguments=$env:PP_ARGS;"
        "$s.WorkingDirectory=$env:PP_DIR;"
        "$s.IconLocation=$env:PP_ICON;"
        "$s.Save()"
    )
    env = dict(os.environ, PP_LNK=path, PP_EXE=exe, PP_ARGS=arguments,
               PP_DIR=APP_DIR, PP_ICON=icon)
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], env=env,
                   creationflags=0x08000000)


def autostart_enabled():
    return os.path.exists(STARTUP_LNK)


def set_autostart(on):
    if on:
        make_shortcut(STARTUP_LNK)
    elif os.path.exists(STARTUP_LNK):
        os.remove(STARTUP_LNK)


def ensure_phrases():
    """First run of the .exe: put an editable copy of phrases.txt next to it."""
    bundled = os.path.join(BUNDLE_DIR, "phrases.txt")
    if not os.path.exists(PHRASES_PATH) and os.path.exists(bundled):
        import shutil
        try:
            shutil.copyfile(bundled, PHRASES_PATH)
        except OSError:
            log_error()


def ensure_icon():
    if FROZEN or os.path.exists(ICON_PATH):  # the .exe carries its own icon
        return
    img = sprites.frames(4)["idle"]
    s = 4
    img = img.crop((sprites.SIDE_MARGIN * s - s, sprites.TOP_MARGIN * s - s,
                    (sprites.SIDE_MARGIN + sprites.W) * s + s,
                    (sprites.TOP_MARGIN + sprites.HEAD_ROWS) * s))
    side = max(img.size)
    from PIL import Image
    sq = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    rgba = img.convert("RGBA")
    px = rgba.load()
    for yy in range(rgba.size[1]):
        for xx in range(rgba.size[0]):
            if px[xx, yy][:3] == sprites.KEY:
                px[xx, yy] = (0, 0, 0, 0)
    sq.paste(rgba, ((side - rgba.size[0]) // 2, (side - rgba.size[1]) // 2))
    sq.save(ICON_PATH, sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128)])


# ------------------------------------------------------------------ app ---

class App:
    def __init__(self):
        self.cfg = load_config()
        self.root = tk.Tk()
        self.root.title("PixelPet")
        self.pet = Pet(self.root, self.cfg["size"])
        self.pet.on_hide_request = self.turn_off
        self.widget = Widget(self.root, self)
        if self.cfg["pet_on"]:
            self.pet.show()
        self.start_ipc()

    def toggle(self):
        (self.turn_off if self.cfg["pet_on"] else self.turn_on)()

    def turn_on(self):
        self.cfg["pet_on"] = True
        save_config(self.cfg)
        self.pet.show()
        self.widget.draw()

    def turn_off(self):
        self.cfg["pet_on"] = False
        save_config(self.cfg)
        self.pet.hide()
        self.widget.draw()

    def call_here(self):
        if not self.cfg["pet_on"]:
            self.turn_on()
        x = self.root.winfo_x() + self.widget.W // 2
        self.pet.spawn(x)

    def set_size(self, size):
        self.cfg["size"] = size
        save_config(self.cfg)
        self.pet.set_size(size)

    def quit(self):
        save_config(self.cfg)
        self.root.destroy()

    def start_ipc(self):
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.bind(("127.0.0.1", IPC_PORT))
        srv.listen(2)

        def serve():
            while True:
                try:
                    conn, _ = srv.accept()
                    msg = conn.recv(64).decode(errors="ignore").strip()
                    conn.close()
                    self.root.after(0, self.handle_ipc, msg)
                except Exception:
                    return

        threading.Thread(target=serve, daemon=True).start()

    def handle_ipc(self, msg):
        if msg == "toggle":
            self.toggle()
        elif msg == "quit":
            self.quit()
        elif msg == "say":
            self.pet.chatter()
        elif msg == "rocket":
            self.pet.rocket_now()
        elif msg.startswith("drop:"):  # drop the pet from the top at x
            if not self.cfg["pet_on"]:
                self.turn_on()
            self.pet.spawn(int(msg[5:]))

    def run(self):
        self.root.mainloop()


def send_to_running(msg):
    try:
        with socket.create_connection(("127.0.0.1", IPC_PORT), timeout=1) as s:
            s.sendall(msg.encode())
        return True
    except OSError:
        return False


def main():
    args = sys.argv[1:]
    if "--make-shortcuts" in args:
        ensure_icon()
        desktop = os.path.join(os.environ["USERPROFILE"], "Desktop")
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders") as k:
                desktop = os.path.expandvars(winreg.QueryValueEx(k, "Desktop")[0])
        except Exception:
            pass
        make_shortcut(os.path.join(desktop, f"{PET_NAME}.lnk"))
        return
    if "--autostart-on" in args:
        ensure_icon()
        set_autostart(True)
        return
    msg = "quit" if "--quit" in args else "toggle"
    if send_to_running(msg):
        return
    if msg == "quit":
        return
    ensure_icon()
    ensure_phrases()
    App().run()


if __name__ == "__main__":
    main()
