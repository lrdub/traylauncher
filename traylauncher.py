"""Tray Launcher: a menu of your apps, opened from one click.

Default mode: pin TrayLauncher.exe to the taskbar. Clicking it pops the menu up
above the button. Pick an entry to launch it; the program then closes.

Tray mode (run with --tray): sits in the system tray (by the clock) instead.

Edit apps.json (next to this program) to change the entries. Changes show up
the next time the menu opens.
"""

import base64
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys

__version__ = "1.0.0"

APP_NAME = "TrayLauncher"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"

DEFAULT_CONFIG = {
    "apps": [
        {"name": "Notepad", "path": "notepad.exe"},
        {"name": "Calculator", "path": "calc.exe"},
        {"name": "File Explorer", "path": "explorer.exe"},
        {"separator": True},
        {
            "name": "Web",
            "items": [
                {"name": "GitHub", "path": "https://github.com"},
                {"name": "Wikipedia", "path": "https://www.wikipedia.org"},
            ],
        },
    ]
}


def base_dir():
    """Folder holding the exe (when built) or this script."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def config_path():
    return os.path.join(base_dir(), "apps.json")


def load_config():
    """Read apps.json. Create it if missing. Never raise: return an error entry instead."""
    path = config_path()
    if not os.path.exists(path):
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_CONFIG, f, indent=2)
        except OSError:
            return DEFAULT_CONFIG, None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict) or not isinstance(data.get("apps"), list):
            return {"apps": []}, 'apps.json must contain {"apps": [ ... ]}'
        return data, None
    except (OSError, json.JSONDecodeError) as e:
        return {"apps": []}, f"apps.json problem: {e}"


def launch(entry):
    """Start one app, file, folder or URL."""
    target = os.path.expandvars(str(entry.get("path", "")))
    args = [os.path.expandvars(str(a)) for a in entry.get("args", [])]
    if not target:
        return
    try:
        if args:
            subprocess.Popen([target, *args], cwd=entry.get("start_in") or None)
        else:
            os.startfile(target)  # Windows only: opens exes, files, folders, URLs
    except Exception as e:  # noqa: BLE001 - show any failure to the user
        message_box(f"Could not start '{entry.get('name', target)}'.\n\n{e}")


def message_box(text):
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(0, text, APP_NAME, 0x10)
    except Exception:  # noqa: BLE001
        print(text)


def make_action(entry):
    """pystray only accepts actions with exactly 0, 1 or 2 arguments, so bind the entry here."""

    def action(icon, item):
        launch(entry)

    return action


def build_items(entries, Item, Menu):
    """Turn config entries into pystray menu items. Handles nested groups."""
    items = []
    for entry in entries:
        if entry.get("separator"):
            items.append(Menu.SEPARATOR)
        elif isinstance(entry.get("items"), list):
            sub = build_items(entry["items"], Item, Menu)
            items.append(Item(entry.get("name", "Group"), Menu(*sub)))
        elif entry.get("path"):
            items.append(Item(entry.get("name", entry["path"]), make_action(entry)))
    return items


# Start with Windows ---------------------------------------------------------

def _run_command():
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    exe = pyw if os.path.exists(pyw) else sys.executable
    return f'"{exe}" "{os.path.abspath(__file__)}"'


def autostart_enabled():
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, APP_NAME)
            return True
    except Exception:  # noqa: BLE001
        return False


def set_autostart(enable):
    import winreg

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if enable:
            winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, _run_command())
        else:
            try:
                winreg.DeleteValue(k, APP_NAME)
            except FileNotFoundError:
                pass


# Icon -----------------------------------------------------------------------

def make_icon_image(size=64):
    """A simple 2x2 grid of squares, drawn in code so no image file is needed."""
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pad, gap = size // 8, size // 12
    cell = (size - 2 * pad - gap) // 2
    colours = [(0, 120, 215), (16, 163, 127), (232, 145, 30), (200, 60, 80)]
    for i, colour in enumerate(colours):
        x = pad + (i % 2) * (cell + gap)
        y = pad + (i // 2) * (cell + gap)
        d.rounded_rectangle([x, y, x + cell, y + cell], radius=size // 12, fill=colour)
    return img


def write_ico(path="icon.ico"):
    img = make_icon_image(256)
    img.save(path, format="ICO", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (256, 256)])
    print(f"Wrote {path}")


# Taskbar popup mode ----------------------------------------------------------

def build_tk_menu(parent, entries, tk, on_pick):
    """Fill a tkinter Menu from config entries. Handles separators and nested groups."""
    menu = tk.Menu(parent, tearoff=0)
    for entry in entries:
        if entry.get("separator"):
            menu.add_separator()
        elif isinstance(entry.get("items"), list):
            menu.add_cascade(label=entry.get("name", "Group"), menu=build_tk_menu(menu, entry["items"], tk, on_pick))
        elif entry.get("path"):
            menu.add_command(label=entry.get("name", entry["path"]), command=lambda e=entry: on_pick(e))
    return menu


def popup_classic():
    """Show the menu at the mouse position (which is on the taskbar button), then exit."""
    import tkinter as tk

    try:  # sharp text on high-DPI screens
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:  # noqa: BLE001
        pass

    config, error = load_config()
    root = tk.Tk()
    x, y = root.winfo_pointerx(), root.winfo_pointery()

    # A tiny invisible window at the mouse. Windows only closes a popup menu when
    # you click elsewhere if the menu belongs to a window that has focus.
    root.overrideredirect(True)  # no border, no taskbar button of its own
    root.geometry(f"1x1+{x}+{y}")
    root.attributes("-topmost", True)
    root.attributes("-alpha", 0.0)
    root.update()
    root.focus_force()

    chosen = []

    def on_pick(entry):
        chosen.append(entry)

    menu = build_tk_menu(root, config["apps"], tk, on_pick)
    if error:
        menu.insert_command(0, label=error, state="disabled")
        menu.insert_separator(1)
    menu.add_separator()
    menu.add_command(label="Edit apps list", command=lambda: on_pick({"name": "apps.json", "path": config_path()}))

    try:
        menu.tk_popup(x, y)
    finally:
        menu.grab_release()
    # The click is delivered just after tk_popup returns. Let it run, then close.
    root.after(200, root.quit)
    root.mainloop()
    root.destroy()

    for entry in chosen:
        launch(entry)


# Modern popup (Windows 11 style) ---------------------------------------------

def log_error(text):
    """Append to %LOCALAPPDATA%\\TrayLauncher\\error.log so problems can be diagnosed."""
    try:
        import time
        import traceback

        folder = os.path.join(os.environ.get("LOCALAPPDATA", base_dir()), "TrayLauncher")
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, "error.log"), "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + text + "\n" + traceback.format_exc() + "\n")
    except Exception:  # noqa: BLE001
        pass


def theme():
    """Colours that follow the Windows light/dark app setting."""
    light = True
    try:
        import winreg

        key = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as k:
            light = winreg.QueryValueEx(k, "AppsUseLightTheme")[0] == 1
    except Exception:  # noqa: BLE001
        pass
    if light:
        return dict(bg="#F3F3F3", border="#D6D6D6", hover="#E4E4E4", fg="#1B1B1B", dim="#6B6B6B", sep="#DADADA", dark=False)
    return dict(bg="#2C2C2C", border="#484848", hover="#3C3C3C", fg="#FFFFFF", dim="#A6A6A6", sep="#434343", dark=True)


def dpi_aware():
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:  # noqa: BLE001
        pass


def dpi_scale():
    try:
        import ctypes

        return max(1.0, ctypes.windll.user32.GetDpiForSystem() / 96.0)
    except Exception:  # noqa: BLE001
        return 1.0


def work_area():
    """Screen area not covered by the taskbar: (left, top, right, bottom)."""
    import ctypes
    from ctypes import wintypes

    rect = wintypes.RECT()
    ctypes.windll.user32.SystemParametersInfoW(0x30, 0, ctypes.byref(rect), 0)  # SPI_GETWORKAREA
    return rect.left, rect.top, rect.right, rect.bottom


def cursor_pos():
    import ctypes
    from ctypes import wintypes

    pt = wintypes.POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def style_window(hwnd, colors):
    """Windows 11 rounded corners, matching border colour and dark title/border mode."""
    try:
        import ctypes

        dwm = ctypes.windll.dwmapi

        def set_attr(attr, value):
            v = ctypes.c_int(value)
            dwm.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(v), 4)

        set_attr(33, 2)  # DWMWA_WINDOW_CORNER_PREFERENCE = round
        set_attr(20, 1 if colors["dark"] else 0)  # immersive dark mode
        h = colors["border"].lstrip("#")
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        set_attr(34, r | (g << 8) | (b << 16))  # DWMWA_BORDER_COLOR (COLORREF is BGR)
    except Exception:  # noqa: BLE001
        pass


# Icons ----------------------------------------------------------------------

def icon_cache_dir():
    folder = os.path.join(os.environ.get("LOCALAPPDATA", base_dir()), "TrayLauncher", "icons")
    os.makedirs(folder, exist_ok=True)
    return folder


def letter_tile(name, px):
    """Fallback icon: coloured rounded square with the first letter."""
    from PIL import Image, ImageDraw, ImageFont

    palette = [(0, 120, 212), (16, 137, 62), (202, 80, 16), (136, 23, 152), (0, 153, 188), (196, 43, 28)]
    colour = palette[sum(map(ord, name)) % len(palette)]
    img = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, px - 1, px - 1], radius=max(2, px // 4), fill=colour + (255,))
    letter = (name.strip() or "?")[0].upper()
    try:
        font = ImageFont.load_default(size=int(px * 0.55))
    except TypeError:
        font = ImageFont.load_default()
    try:
        d.text((px / 2, px / 2), letter, fill=(255, 255, 255, 255), font=font, anchor="mm")
    except Exception:  # noqa: BLE001
        d.text((px // 3, px // 4), letter, fill=(255, 255, 255, 255), font=font)
    return img


def shell_icon(path, px):
    """Ask Windows for an item's icon (works for exes, shortcuts and Store apps). Returns a PIL image or None."""
    try:
        import ctypes
        import uuid
        from ctypes import wintypes

        from PIL import Image

        class GUID(ctypes.Structure):
            _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]

        class SIZE(ctypes.Structure):
            _fields_ = [("cx", wintypes.LONG), ("cy", wintypes.LONG)]

        class BITMAP(ctypes.Structure):
            _fields_ = [("bmType", wintypes.LONG), ("bmWidth", wintypes.LONG), ("bmHeight", wintypes.LONG),
                        ("bmWidthBytes", wintypes.LONG), ("bmPlanes", wintypes.WORD), ("bmBitsPixel", wintypes.WORD),
                        ("bmBits", ctypes.c_void_p)]

        class BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                        ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                        ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                        ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]

        ole32, shell32, gdi32, user32 = ctypes.windll.ole32, ctypes.windll.shell32, ctypes.windll.gdi32, ctypes.windll.user32
        ole32.CoInitialize(None)

        iid = GUID.from_buffer_copy(uuid.UUID("{bcc18b79-ba16-442f-80c4-8a59c30c463b}").bytes_le)  # IShellItemImageFactory
        create = shell32.SHCreateItemFromParsingName
        create.argtypes = [wintypes.LPCWSTR, ctypes.c_void_p, ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p)]
        create.restype = ctypes.c_long
        item = ctypes.c_void_p()
        if create(path, None, ctypes.byref(iid), ctypes.byref(item)) != 0 or not item.value:
            return None

        vtable = ctypes.cast(item.value, ctypes.POINTER(ctypes.c_void_p)).contents.value
        fns = ctypes.cast(vtable, ctypes.POINTER(ctypes.c_void_p))
        release = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(fns[2])
        get_image = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, SIZE, ctypes.c_uint, ctypes.POINTER(ctypes.c_void_p))(fns[3])
        hbm = ctypes.c_void_p()
        hr = get_image(item.value, SIZE(px, px), 0x1 | 0x4, ctypes.byref(hbm))  # BIGGERSIZEOK | ICONONLY
        release(item.value)
        if hr != 0 or not hbm.value:
            return None

        gdi32.GetObjectW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
        gdi32.GetDIBits.argtypes = [ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT, wintypes.UINT,
                                    ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT]
        gdi32.DeleteObject.argtypes = [ctypes.c_void_p]
        user32.GetDC.restype = ctypes.c_void_p
        user32.ReleaseDC.argtypes = [ctypes.c_void_p, ctypes.c_void_p]

        bm = BITMAP()
        gdi32.GetObjectW(hbm.value, ctypes.sizeof(bm), ctypes.byref(bm))
        w, h = bm.bmWidth, bm.bmHeight
        bih = BITMAPINFOHEADER(biSize=ctypes.sizeof(BITMAPINFOHEADER), biWidth=w, biHeight=-h, biPlanes=1, biBitCount=32, biCompression=0)
        buf = ctypes.create_string_buffer(w * h * 4)
        hdc = user32.GetDC(None)
        gdi32.GetDIBits(hdc, hbm.value, 0, h, buf, ctypes.byref(bih), 0)
        user32.ReleaseDC(None, hdc)
        gdi32.DeleteObject(hbm.value)

        img = Image.frombuffer("RGBA", (w, h), buf.raw, "raw", "BGRA", 0, 1)
        if img.getchannel("A").getextrema() == (0, 0):  # bitmap had no alpha: make it opaque
            img.putalpha(255)
        return img
    except Exception:  # noqa: BLE001
        log_error(f"shell_icon failed for {path}")
        return None


def resolve_target(target):
    """Turn 'notepad.exe' into a full path so Windows can find its icon."""
    if target.lower().startswith(("http://", "https://", "shell:")):
        return target
    return shutil.which(target) or target


def get_icon_image(entry, px):
    """Icon for one menu entry: custom 'icon' file, else Windows' icon (cached), else a letter tile."""
    from PIL import Image

    name = entry.get("name") or entry.get("path") or "?"
    custom = entry.get("icon")
    if custom:
        custom = os.path.expandvars(custom)
        try:
            if custom.lower().endswith((".png", ".jpg", ".jpeg", ".ico", ".bmp")) and os.path.exists(custom):
                return Image.open(custom).convert("RGBA").resize((px, px), Image.LANCZOS)
            img = shell_icon(custom, px)
            if img:
                return img.resize((px, px), Image.LANCZOS)
        except Exception:  # noqa: BLE001
            log_error(f"custom icon failed for {name}")
    target = entry.get("path")
    if target:
        target = resolve_target(os.path.expandvars(target))
        key = hashlib.sha1(f"{target}|{px}".encode("utf-8")).hexdigest()[:16]
        cached = os.path.join(icon_cache_dir(), key + ".png")
        try:
            if os.path.exists(cached):
                return Image.open(cached).convert("RGBA")
        except Exception:  # noqa: BLE001
            pass
        img = shell_icon(target, px)
        if img:
            img = img.resize((px, px), Image.LANCZOS)
            try:
                img.save(cached)
            except Exception:  # noqa: BLE001
                pass
            return img
    return letter_tile(name, px)


def png_b64(img):
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


# Layout and drawing ---------------------------------------------------------

CLICKABLE = ("item", "group", "edit")


def layout(entries, expanded, S, error=None, footer=True):
    """Work out each row's position. Returns (rows, total_height). Pure logic, no drawing."""
    ROW, SEP = S(44), S(9)
    rows = []
    y = S(8)

    def add(kind, h, **kw):
        nonlocal y
        rows.append(dict(kind=kind, y=y, h=h, **kw))
        y += h

    if error:
        add("note", ROW, label=error)
        add("sep", SEP)

    def walk(items, indent, prefix):
        for n, e in enumerate(items):
            key = f"{prefix}{n}"
            if e.get("separator"):
                add("sep", SEP)
            elif isinstance(e.get("items"), list):
                add("group", ROW, entry=e, key=key, indent=indent, open=key in expanded)
                if key in expanded:
                    walk(e["items"], indent + 1, key + ".")
            elif e.get("path"):
                add("item", ROW, entry=e, indent=indent)

    walk(entries, 0, "")
    if footer:
        add("sep", SEP)
        add("edit", ROW, entry={"name": "Edit apps list", "path": config_path()}, indent=0)
    return rows, y + S(8)


def rrect_points(x1, y1, x2, y2, r):
    return [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
            x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]


def get_hwnd(win):
    import ctypes

    return ctypes.windll.user32.GetAncestor(win.winfo_id(), 2)  # GA_ROOT


class MenuPanel:
    """One menu window: the main menu, or a flyout that opens beside a folder row."""

    OPEN_DELAY = 150    # ms to hover a folder before its flyout opens
    CLOSE_DELAY = 350   # ms before a flyout closes after the mouse moves to another row

    def __init__(self, ctx, win, entries, parent=None, error=None, footer=False):
        self.ctx, self.win, self.parent = ctx, win, parent
        self.child = self.child_row = self.hover = self.timer = self.hwnd = None
        self.x = self.y = 0
        S = ctx.S
        self.rows, self.height = layout(entries, set(), S, error, footer)
        self.canvas = ctx.tk.Canvas(win, width=ctx.W, height=self.height, bg=ctx.colors["bg"], highlightthickness=0, bd=0)
        self.canvas.pack()
        self.hl = self.canvas.create_polygon(rrect_points(ctx.PAD, 0, ctx.W - ctx.PAD, 10, S(6)), smooth=True,
                                             fill=ctx.colors["hover"], outline="", state="hidden")
        self.draw()
        self.canvas.bind("<Motion>", self.on_motion)
        self.canvas.bind("<Button-1>", self.on_click)
        self.canvas.bind("<Enter>", self.on_enter)
        win.bind("<Escape>", lambda e: ctx.close())
        ctx.panels.append(self)

    def draw(self):
        c, canvas, S = self.ctx, self.canvas, self.ctx.S
        for r in self.rows:
            mid = r["y"] + r["h"] // 2
            kind = r["kind"]
            if kind == "sep":
                canvas.create_line(c.PAD * 2, mid, c.W - c.PAD * 2, mid, fill=c.colors["sep"])
            elif kind == "note":
                canvas.create_text(c.PAD * 2, mid, text=r["label"], anchor="w", fill=c.colors["dim"], font=c.font, width=c.W - c.PAD * 4)
            else:
                ix = c.PAD + S(12)
                if kind == "edit":
                    canvas.create_text(ix + c.ICON // 2, mid, text="", font=c.glyph_font, fill=c.colors["dim"])
                    label = r["entry"]["name"]
                else:
                    canvas.create_image(ix, mid, image=c.icon_for(r["entry"]), anchor="w")
                    label = r["entry"].get("name") or r["entry"].get("path", "")
                canvas.create_text(ix + c.ICON + S(12), mid, text=label, anchor="w", fill=c.colors["fg"], font=c.font)
                if kind == "group":
                    canvas.create_text(c.W - c.PAD - S(18), mid, text="", font=c.chevron_font, fill=c.colors["dim"])

    def show(self, x, y):
        c = self.ctx
        self.x, self.y = x, y
        self.win.overrideredirect(True)
        self.win.configure(bg=c.colors["bg"])
        self.win.geometry(f"{c.W}x{self.height}+{x}+{y}")
        self.win.attributes("-topmost", True)
        self.win.deiconify()
        self.win.update()
        self.hwnd = get_hwnd(self.win)
        style_window(self.hwnd, c.colors)

    def row_at(self, y):
        for r in self.rows:
            if r["kind"] in CLICKABLE and r["y"] <= y < r["y"] + r["h"]:
                return r
        return None

    def update_highlight(self):
        row = self.hover or self.child_row
        if row is None:
            self.canvas.itemconfigure(self.hl, state="hidden")
            return
        c, S = self.ctx, self.ctx.S
        self.canvas.coords(self.hl, *rrect_points(c.PAD, row["y"] + S(2), c.W - c.PAD, row["y"] + row["h"] - S(2), S(6)))
        self.canvas.itemconfigure(self.hl, state="normal")

    def cancel_timer(self):
        if self.timer is not None:
            try:
                self.win.after_cancel(self.timer)
            except Exception:  # noqa: BLE001
                pass
            self.timer = None

    def on_enter(self, ev):
        # Mouse arrived in this flyout: stop any parent from closing it.
        p = self.parent
        while p is not None:
            p.cancel_timer()
            p = p.parent

    def on_motion(self, ev):
        r = self.row_at(ev.y)
        if r is self.hover:
            return
        self.hover = r
        self.cancel_timer()
        self.update_highlight()
        if r is not None and r["kind"] == "group":
            if self.child_row is not r:
                self.timer = self.win.after(self.OPEN_DELAY, lambda row=r: self.open_child(row))
        elif self.child is not None:
            self.timer = self.win.after(self.CLOSE_DELAY, self.close_child)

    def on_click(self, ev):
        r = self.row_at(ev.y)
        if r is None:
            return
        if r["kind"] == "group":
            self.cancel_timer()
            if self.child_row is not r:
                self.open_child(r)
            return
        self.ctx.chosen = r["entry"]
        self.ctx.close()

    def open_child(self, row):
        self.timer = None
        self.close_child()
        c, S = self.ctx, self.ctx.S
        top = c.tk.Toplevel(c.root)
        top.withdraw()
        panel = MenuPanel(c, top, row["entry"]["items"], parent=self)
        x = self.x + c.W - S(4)
        if x + c.W > c.work[2] - S(8):  # no room on the right: open to the left
            x = self.x - c.W + S(4)
        y = self.y + row["y"] - S(8)
        y = max(min(y, c.work[3] - panel.height - S(8)), c.work[1] + S(8))
        panel.show(x, y)
        self.child, self.child_row = panel, row
        self.update_highlight()

    def close_child(self):
        if self.child is not None:
            self.child.destroy()
            self.child = self.child_row = None
            self.update_highlight()

    def destroy(self):
        self.cancel_timer()
        self.close_child()
        if self in self.ctx.panels:
            self.ctx.panels.remove(self)
        self.win.destroy()


def popup_modern():
    import ctypes
    import tkinter as tk
    from tkinter import font as tkfont
    from types import SimpleNamespace

    dpi_aware()
    root = tk.Tk()
    root.withdraw()
    user32 = ctypes.windll.user32
    scale = dpi_scale()

    def S(v):
        return max(1, int(round(v * scale)))

    colors = theme()
    config, error = load_config()
    W, PAD, ICON = S(300), S(8), S(26)
    images = {}

    def icon_for(entry):
        key = f"{entry.get('path', '')}|{entry.get('icon', '')}|{entry.get('name', '')}"
        if key not in images:
            try:
                images[key] = tk.PhotoImage(master=root, data=png_b64(get_icon_image(entry, ICON)))
            except Exception:  # noqa: BLE001
                log_error(f"icon failed for {entry.get('name')}")
                images[key] = tk.PhotoImage(master=root, data=png_b64(letter_tile(entry.get("name") or "?", ICON)))
        return images[key]

    # Windows 11 has Segoe Fluent Icons; Windows 10 has Segoe MDL2 Assets (same symbol codes).
    icon_family = "Segoe Fluent Icons" if "Segoe Fluent Icons" in tkfont.families(root) else "Segoe MDL2 Assets"

    ctx = SimpleNamespace(
        tk=tk, root=root, colors=colors, S=S, W=W, PAD=PAD, ICON=ICON, icon_for=icon_for,
        font=tkfont.Font(root=root, family="Segoe UI", size=-S(15)),
        glyph_font=tkfont.Font(root=root, family=icon_family, size=-S(16)),
        chevron_font=tkfont.Font(root=root, family=icon_family, size=-S(12)),
        work=work_area(), panels=[], chosen=None, close=root.quit,
    )

    main = MenuPanel(ctx, root, config["apps"], error=error, footer=True)
    cx, cy = cursor_pos()
    work = ctx.work
    opens_below = cy < (work[1] + work[3]) // 2  # taskbar at the top of the screen
    x = min(max(cx - W // 2, work[0] + S(8)), work[2] - W - S(8))
    y = work[1] + S(8) if opens_below else work[3] - main.height - S(8)
    main.show(x, y)

    root.focus_force()
    try:
        user32.SetForegroundWindow(main.hwnd)
    except Exception:  # noqa: BLE001
        pass

    seen = {"fg": False}

    def poll():
        # Close when the user clicks somewhere else (once one of our windows has had focus).
        try:
            fg = user32.GetForegroundWindow()
            if fg in {p.hwnd for p in ctx.panels}:
                seen["fg"] = True
            elif seen["fg"]:
                root.quit()
                return
        except Exception:  # noqa: BLE001
            pass
        root.after(100, poll)

    root.after(100, poll)
    root.mainloop()
    root.destroy()

    if ctx.chosen:
        launch(ctx.chosen)


def popup():
    """Taskbar click: try the modern menu, fall back to the plain one if anything goes wrong."""
    if "--classic" in sys.argv:
        popup_classic()
        return
    try:
        popup_modern()
    except Exception:  # noqa: BLE001
        log_error("popup_modern failed, using classic menu")
        popup_classic()


# Main -----------------------------------------------------------------------

def main():
    import pystray
    from pystray import Menu, MenuItem as Item

    def menu_items():
        # Called every time the menu opens, so apps.json edits apply immediately.
        config, error = load_config()
        items = []
        if error:
            items.append(Item(error, None, enabled=False))
            items.append(Menu.SEPARATOR)
        items.extend(build_items(config["apps"], Item, Menu))
        if items:
            items.append(Menu.SEPARATOR)
        items.append(Item("Edit apps list", lambda icon, item: os.startfile(config_path())))
        items.append(
            Item(
                "Start with Windows",
                lambda icon, item: set_autostart(not autostart_enabled()),
                checked=lambda item: autostart_enabled(),
            )
        )
        items.append(Item("Quit", lambda icon, item: icon.stop()))
        return items

    icon = pystray.Icon(APP_NAME, make_icon_image(), APP_NAME, Menu(menu_items))

    # By default pystray shows the menu on right-click only. Make left-click
    # show it too. This relies on a pystray internal, so fall back quietly if
    # a future version changes it (right-click will still work).
    try:
        from pystray._util import win32

        handlers = icon._message_handlers  # built when the icon is created
        original = handlers[win32.WM_NOTIFY]

        def on_notify(wparam, lparam):
            if lparam == win32.WM_LBUTTONUP:
                lparam = win32.WM_RBUTTONUP
            return original(wparam, lparam)

        handlers[win32.WM_NOTIFY] = on_notify
    except Exception:  # noqa: BLE001
        pass

    icon.run()


def selftest():
    """Used by the release build: check that every library is bundled. Returns an exit code."""
    try:
        import tkinter  # noqa: F401
        import pystray  # noqa: F401
        from PIL import Image  # noqa: F401

        letter_tile("A", 32)
        return 0
    except Exception:  # noqa: BLE001
        log_error("selftest failed")
        return 1


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    elif "--version" in sys.argv:
        print(f"{APP_NAME} {__version__}")
    elif "--make-icon" in sys.argv:
        write_ico()
    elif "--tray" in sys.argv:
        main()
    else:
        popup()
