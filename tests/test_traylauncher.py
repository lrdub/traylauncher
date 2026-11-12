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

    def make(x=500, y=300, screen_w=1920, screen_h=1040):
        tk = SimpleNamespace(Canvas=FakeCanvas, Toplevel=lambda root: FakeWin(clock))
        ctx = SimpleNamespace(
            tk=tk, root=FakeWin(clock), colors=T.theme(), S=S, W=300, PAD=8, ICON=26,
            icon_for=lambda e: None, font=None, glyph_font=None, chevron_font=None,
            work=(0, 0, screen_w, screen_h), panels=[], chosen=None, closed=False,
        )
        ctx.close = lambda: setattr(ctx, "closed", True)
        main = T.MenuPanel(ctx, ctx.root, APPS, footer=True)
        main.show(x, y)
        return ctx, main, clock

    return make


def hover(panel, name):
    row = next(r for r in panel.rows if (r.get("entry") or {}).get("name") == name)
    panel.on_motion(SimpleNamespace(y=row["y"] + row["h"] // 2))


def click(panel, name):
    row = next(r for r in panel.rows if (r.get("entry") or {}).get("name") == name)
    panel.on_click(SimpleNamespace(y=row["y"] + row["h"] // 2))


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
