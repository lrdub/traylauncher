"""Tests for the parts of TrayLauncher that do not need Windows."""

import base64
import json
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import traylauncher as T  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_dirs(tmp_path, monkeypatch):
    """Keep the icon cache and error log out of the real user folders."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.setattr(T, "config_path", lambda: str(tmp_path / "apps.json"))
    return tmp_path


# Config ---------------------------------------------------------------------

def test_missing_config_is_created_with_defaults(isolated_dirs):
    config, error = T.load_config()
    assert error is None
    assert config == T.DEFAULT_CONFIG
    assert (isolated_dirs / "apps.json").exists()


def test_broken_json_reports_an_error_instead_of_crashing(isolated_dirs):
    (isolated_dirs / "apps.json").write_text("{bad", encoding="utf-8")
    config, error = T.load_config()
    assert config == {"apps": []}
    assert "apps.json problem" in error


def test_wrong_shape_reports_an_error(isolated_dirs):
    (isolated_dirs / "apps.json").write_text('{"apps": "nope"}', encoding="utf-8")
    config, error = T.load_config()
    assert config == {"apps": []}
    assert error


def test_example_file_matches_built_in_default():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "apps.example.json"), encoding="utf-8") as f:
        assert json.load(f) == T.DEFAULT_CONFIG


def valid_entries(entries):
    for e in entries:
        if e.get("separator"):
            continue
        assert e.get("name"), e
        if "items" in e:
            valid_entries(e["items"])
        else:
            assert e.get("path"), e


def test_default_config_entries_are_valid():
    valid_entries(T.DEFAULT_CONFIG["apps"])


# Layout ---------------------------------------------------------------------

APPS = [
    {"name": "Notepad", "path": "notepad.exe"},
    {"separator": True},
    {"name": "AI", "items": [
        {"name": "ChatGPT", "path": "g"},
        {"name": "More", "items": [{"name": "Deep", "path": "d"}]},
    ]},
]


def S(v):
    return v


def test_layout_has_footer_only_when_asked():
    with_footer, _ = T.layout(APPS, set(), S, footer=True)
    without, _ = T.layout(APPS, set(), S, footer=False)
    assert with_footer[-1]["kind"] == "edit"
    assert all(r["kind"] != "edit" for r in without)


def test_layout_rows_do_not_overlap():
    rows, height = T.layout(APPS, set(), S)
    for a, b in zip(rows, rows[1:]):
        assert a["y"] + a["h"] == b["y"]
    assert rows[-1]["y"] + rows[-1]["h"] < height


def test_layout_shows_error_note_first():
    rows, _ = T.layout(APPS, set(), S, error="broken")
    assert rows[0]["kind"] == "note"


# Tray menu actions ------------------------------------------------------------

def test_tray_actions_take_exactly_two_arguments():
    # pystray raises ValueError for menu actions with more than two arguments.
    action = T.make_action({"name": "x", "path": "y"})
    assert action.__code__.co_argcount == 2


def test_build_items_handles_folders_and_separators():
    class Item:
        def __init__(self, text, action=None, **kw):
            self.text, self.action = text, action

    class Menu:
        SEPARATOR = "SEP"

        def __init__(self, *items):
            self.items = items

    items = T.build_items(APPS, Item, Menu)
    assert items[0].text == "Notepad"
    assert items[1] == "SEP"
    assert [i.text for i in items[2].action.items][0] == "ChatGPT"


# Icons ----------------------------------------------------------------------

def test_letter_tile_is_the_right_size():
    img = T.letter_tile("Claude", 40)
    assert img.size == (40, 40)


def test_png_b64_round_trips():
    data = base64.b64decode(T.png_b64(T.letter_tile("A", 16)))
    assert data.startswith(b"\x89PNG")


def test_icon_falls_back_to_a_tile_when_windows_cannot_supply_one():
    img = T.get_icon_image({"name": "Thing", "path": "https://example.com"}, 32)
    assert img.size == (32, 32)


def test_theme_always_returns_all_colours():
    needed = {"bg", "border", "hover", "fg", "dim", "sep", "dark"}
    assert needed <= set(T.theme())


# Flyout panels ----------------------------------------------------------------

class Clock:
    def __init__(self):
        self.t, self.jobs, self.n = 0, {}, 0

    def after(self, ms, fn):
        self.n += 1
        self.jobs[self.n] = (self.t + ms, fn)
        return self.n

    def cancel(self, i):
        self.jobs.pop(i, None)

    def advance(self, ms):
        self.t += ms
        for i, (due, fn) in sorted(self.jobs.items(), key=lambda kv: kv[1][0]):
            if due <= self.t and i in self.jobs:
                del self.jobs[i]
                fn()


class FakeWin:
    def __init__(self, clock):
        self.clock, self.alive = clock, True

    def after(self, ms, fn):
        return self.clock.after(ms, fn)

    def after_cancel(self, i):
        self.clock.cancel(i)

    def winfo_id(self):
        return id(self)

    def destroy(self):
        self.alive = False

    def __getattr__(self, name):
        return lambda *a, **k: None


class FakeCanvas:
    def __init__(self, *a, **k):
        self.n = 0

    def __getattr__(self, name):
        def f(*a, **k):
            self.n += 1
            return self.n
        return f


@pytest.fixture
def make_menu(monkeypatch):
    clock = Clock()
    monkeypatch.setattr(T, "get_hwnd", lambda w: id(w))
    monkeypatch.setattr(T, "style_window", lambda *a: None)

    def make(x=500, y=300, screen_w=1920, screen_h=1040, apps=APPS):
        tk = SimpleNamespace(Canvas=FakeCanvas, Toplevel=lambda root: FakeWin(clock))
        ctx = SimpleNamespace(
            tk=tk, root=FakeWin(clock), colors=T.theme(), S=S, W=300, PAD=8, ICON=26,
            icon_for=lambda e: None, font=None, glyph_font=None, chevron_font=None,
            work=(0, 0, screen_w, screen_h), panels=[], chosen=None, closed=False,
        )
        ctx.close = lambda: setattr(ctx, "closed", True)
        main = T.MenuPanel(ctx, ctx.root, apps, footer=True)
        main.show(x, y)
        return ctx, main, clock

    return make


def hover(panel, name):
    row = next(r for r in panel.rows if (r.get("entry") or {}).get("name") == name)
    panel.on_motion(SimpleNamespace(y=row["y"] + row["h"] // 2 - panel.offset))


def click(panel, name):
    row = next(r for r in panel.rows if (r.get("entry") or {}).get("name") == name)
    panel.on_click(SimpleNamespace(y=row["y"] + row["h"] // 2 - panel.offset))


def test_flyout_opens_after_a_short_hover(make_menu):
    ctx, main, clock = make_menu()
    hover(main, "AI")
    assert main.child is None
    clock.advance(200)
    assert main.child is not None
    assert main.child.rows[0]["entry"]["name"] == "ChatGPT"


def test_flyout_has_no_edit_footer(make_menu):
    ctx, main, clock = make_menu()
    click(main, "AI")
    assert all(r["kind"] != "edit" for r in main.child.rows)


def test_moving_into_the_flyout_keeps_it_open(make_menu):
    ctx, main, clock = make_menu()
    hover(main, "AI")
    clock.advance(200)
    flyout = main.child
    hover(main, "Notepad")   # mouse crosses another row on the way
    flyout.on_enter(None)    # and arrives in the flyout
    clock.advance(600)
    assert main.child is flyout


def test_flyout_closes_after_resting_on_a_plain_item(make_menu):
    ctx, main, clock = make_menu()
    hover(main, "AI")
    clock.advance(200)
    flyout = main.child
    hover(main, "Notepad")
    clock.advance(600)
    assert main.child is None and not flyout.win.alive


def test_nested_flyouts_and_picking_an_entry(make_menu):
    ctx, main, clock = make_menu()
    click(main, "AI")
    hover(main.child, "More")
    clock.advance(200)
    deep = main.child.child
    assert deep.rows[0]["entry"]["name"] == "Deep"
    click(deep, "Deep")
    assert ctx.chosen["name"] == "Deep" and ctx.closed


def test_flyout_opens_left_near_the_right_edge(make_menu):
    ctx, main, clock = make_menu(x=1700)
    click(main, "AI")
    assert main.child.x < main.x


def test_flyout_stays_on_screen_at_the_bottom(make_menu):
    ctx, main, clock = make_menu(y=1000)
    click(main, "AI")
    assert main.child.y + main.child.height <= 1040


def test_long_menu_is_cut_to_the_screen_and_scrolls(make_menu):
    apps = [{"name": f"App {n}", "path": "x"} for n in range(40)]
    ctx, main, clock = make_menu(screen_h=600, apps=apps)
    assert main.height == 600 - 16 < main.full_height
    first = main.row_at(30)
    assert main.scroll(200)
    assert main.row_at(30) is not first
    assert main.row_at(30)["y"] <= 230 < main.row_at(30)["y"] + main.row_at(30)["h"]
    main.scroll(10_000)  # cannot scroll past the end
    assert main.offset == main.full_height - main.height
    main.scroll(-10_000)
    assert main.offset == 0


def test_scrolling_closes_a_flyout_and_flyouts_follow_the_scroll(make_menu):
    apps = [{"name": f"App {n}", "path": "x"} for n in range(30)] + [APPS[2]]
    ctx, main, clock = make_menu(screen_h=600, apps=apps)
    main.scroll(10_000)
    click(main, "AI")
    flyout = main.child
    row = next(r for r in main.rows if (r.get("entry") or {}).get("name") == "AI")
    wanted = main.y + row["y"] - main.offset - 8
    assert flyout.y == max(min(wanted, 600 - flyout.height - 8), 8)
    assert flyout.y != main.y + row["y"] - 8  # without the scroll offset it would be off screen
    main.scroll(-50)
    assert main.child is None and not flyout.win.alive


# Config problems ----------------------------------------------------------------

def write_config(isolated_dirs, data, encoding="utf-8"):
    (isolated_dirs / "apps.json").write_text(json.dumps(data), encoding=encoding)


@pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig", "utf-16"])
def test_config_loads_in_common_windows_encodings(isolated_dirs, encoding):
    write_config(isolated_dirs, {"apps": [{"name": "Café", "path": "x"}]}, encoding)
    config, error = T.load_config()
    assert error is None
    assert config["apps"][0]["name"] == "Café"


def test_unreadable_bytes_report_an_error_instead_of_crashing(isolated_dirs):
    (isolated_dirs / "apps.json").write_bytes(b"\x80\x81{}")
    config, error = T.load_config()
    assert config == {"apps": []}
    assert "apps.json problem" in error


def test_bad_entries_are_skipped_and_reported(isolated_dirs):
    write_config(isolated_dirs, {"apps": [
        "oops",
        None,
        {"name": "Good", "path": "x"},
        {"name": "Folder", "items": [123, {"name": "Inner", "path": "y"}]},
        {"name": "Bad args", "path": "z", "args": 5},
        {"name": "Bad items", "items": "nope"},
    ]})
    config, error = T.load_config()
    names = [e.get("name") for e in config["apps"]]
    assert names == ["Good", "Folder"]
    assert [e["name"] for e in config["apps"][1]["items"]] == ["Inner"]
    assert error.startswith("apps.json problem: apps entry 1")
    assert "(and 4 more)" in error


def test_cleaned_config_works_in_every_menu(isolated_dirs):
    write_config(isolated_dirs, {"apps": ["oops", {"name": 5, "path": 7}, {"name": "F", "items": [None]}]})
    config, error = T.load_config()
    rows, _ = T.layout(config["apps"], set(), S)
    assert rows[0]["entry"]["name"] == "5" and rows[0]["entry"]["path"] == "7"
    T.letter_tile(config["apps"][0]["name"], 16)


def test_args_written_as_text_count_as_one_argument(isolated_dirs):
    write_config(isolated_dirs, {"apps": [{"name": "A", "path": "x", "args": "--new-window"}]})
    config, _ = T.load_config()
    assert config["apps"][0]["args"] == ["--new-window"]


def test_user_entries_cannot_pretend_to_be_the_edit_entry(isolated_dirs):
    write_config(isolated_dirs, {"apps": [{"name": "A", "path": "x", T.EDIT_KEY: True}]})
    config, _ = T.load_config()
    assert T.EDIT_KEY not in config["apps"][0]


# Launching ----------------------------------------------------------------------

@pytest.fixture
def popen(monkeypatch):
    calls = []
    monkeypatch.setattr(T.subprocess, "Popen", lambda cmd, **kw: calls.append((cmd, kw)))
    return calls


@pytest.fixture
def boxes(monkeypatch):
    shown = []
    monkeypatch.setattr(T, "message_box", lambda text, error=True: shown.append((text, error)))
    return shown


def test_launch_passes_text_args_as_one_argument(popen):
    T.launch({"path": "x.exe", "args": "--new-window"})
    assert popen[0][0] == ["x.exe", "--new-window"]


def test_launch_expands_variables_in_start_in(popen, monkeypatch):
    monkeypatch.setenv("TL_TEST_DIR", "/some/folder")
    T.launch({"path": "x.exe", "args": ["a"], "start_in": "%TL_TEST_DIR%" if os.name == "nt" else "$TL_TEST_DIR"})
    assert popen[0][1]["cwd"] == "/some/folder"


def test_launch_never_raises(monkeypatch, boxes):
    def fail(*a, **k):
        raise FileNotFoundError("no such program")

    monkeypatch.setattr(T.subprocess, "Popen", fail)
    T.launch({"name": "Broken", "path": "x.exe", "args": ["a"]})
    T.launch({"name": "Weird", "path": "x.exe", "args": 5})
    assert len(boxes) == 2 and "Broken" in boxes[0][0]


def test_edit_entry_opens_the_config(monkeypatch):
    opened = []
    monkeypatch.setattr(T, "open_config", lambda: opened.append(True))
    T.launch(T.edit_entry())
    assert opened


def test_edit_falls_back_to_notepad_when_json_has_no_program(monkeypatch, popen, isolated_dirs):
    def no_program(path):
        raise OSError("No application is associated with the specified file")

    monkeypatch.setattr(T.os, "startfile", no_program, raising=False)
    T.open_config()
    assert popen[0][0] == ["notepad.exe", str(isolated_dirs / "apps.json")]


def test_a_failed_pick_does_not_open_a_second_menu(monkeypatch):
    launched = []
    monkeypatch.setattr(T, "launch", lambda e: launched.append(e))

    def classic():
        raise AssertionError("classic menu must not open")

    T.popup(modern=lambda: {"name": "A", "path": "x"}, classic=classic)
    assert launched == [{"name": "A", "path": "x"}]


def test_classic_menu_is_used_when_the_modern_one_fails(monkeypatch):
    launched = []
    monkeypatch.setattr(T, "launch", lambda e: launched.append(e))

    def modern():
        raise RuntimeError("no styled menu")

    T.popup(modern=modern, classic=lambda: {"name": "B", "path": "y"})
    assert launched == [{"name": "B", "path": "y"}]


def test_version_shows_a_box_when_there_is_no_console(monkeypatch, boxes):
    monkeypatch.setattr(T.sys, "stdout", None)
    T.show_version()
    assert boxes == [(f"TrayLauncher {T.__version__}", False)]


# Start with Windows -------------------------------------------------------------

class FakeWinreg:
    HKEY_CURRENT_USER, KEY_SET_VALUE, REG_SZ = 1, 2, 3

    def __init__(self, saved=None):
        self.values = {} if saved is None else {T.APP_NAME: saved}

    def OpenKey(self, *a):
        reg = self

        class Key:
            def __enter__(self):
                return reg

            def __exit__(self, *exc):
                return False

        return Key()

    def QueryValueEx(self, key, name):
        if name not in self.values:
            raise FileNotFoundError(name)
        return self.values[name], self.REG_SZ

    def SetValueEx(self, key, name, reserved, kind, value):
        self.values[name] = value

    def DeleteValue(self, key, name):
        del self.values[name]


def test_start_with_windows_starts_tray_mode():
    assert T._run_command().endswith(" --tray")


def test_old_start_with_windows_setting_is_repaired(monkeypatch):
    reg = FakeWinreg(saved='"C:\\Apps\\TrayLauncher.exe"')
    monkeypatch.setitem(sys.modules, "winreg", reg)
    T.repair_autostart()
    assert reg.values[T.APP_NAME] == '"C:\\Apps\\TrayLauncher.exe" --tray'


def test_repair_keeps_a_correct_setting_from_another_copy(monkeypatch):
    reg = FakeWinreg(saved='"C:\\Other\\TrayLauncher.exe" --tray')
    monkeypatch.setitem(sys.modules, "winreg", reg)
    T.repair_autostart()
    assert reg.values[T.APP_NAME] == '"C:\\Other\\TrayLauncher.exe" --tray'


def test_repair_leaves_start_with_windows_off(monkeypatch):
    reg = FakeWinreg()
    monkeypatch.setitem(sys.modules, "winreg", reg)
    T.repair_autostart()
    assert reg.values == {}


# Icon pixels and cache ----------------------------------------------------------

def test_premultiplied_icon_pixels_keep_their_colour():
    # A half-transparent mid grey, as Windows stores it: colour already multiplied by alpha.
    img = T.bitmap_to_image(bytes([64, 64, 64, 128]), 1, 1)
    r, g, b, a = img.getpixel((0, 0))
    assert a == 128 and 126 <= r <= 129


def test_icon_with_no_alpha_is_opaque_not_black():
    img = T.bitmap_to_image(bytes([10, 20, 30, 0]), 1, 1)
    assert img.getpixel((0, 0)) == (30, 20, 10, 255)


def test_icon_cache_key_changes_when_the_program_changes(tmp_path):
    exe = tmp_path / "app.exe"
    exe.write_bytes(b"1")
    before = T.icon_cache_key(str(exe), 26)
    os.utime(exe, (1_000_000_000, 1_000_000_000))
    assert T.icon_cache_key(str(exe), 26) != before


def test_old_cached_icons_are_fetched_again(monkeypatch):
    from PIL import Image

    target = "https://example.com"
    cached = os.path.join(T.icon_cache_dir(), T.icon_cache_key(target, 8) + ".png")
    Image.new("RGBA", (8, 8), (0, 0, 255, 255)).save(cached)
    monkeypatch.setattr(T, "shell_icon", lambda path, px: Image.new("RGBA", (8, 8), (255, 0, 0, 255)))
    entry = {"name": "Site", "path": target}
    assert T.get_icon_image(entry, 8).getpixel((0, 0)) == (0, 0, 255, 255)  # fresh cache is used
    old = T.time.time() - (T.ICON_CACHE_DAYS + 1) * 86400
    os.utime(cached, (old, old))
    assert T.get_icon_image(entry, 8).getpixel((0, 0)) == (255, 0, 0, 255)  # stale cache is replaced
