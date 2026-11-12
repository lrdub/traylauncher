# Changelog

## Unreleased

- "Start with Windows" now starts the tray icon. Before, it opened the popup menu at sign-in. A setting saved by 1.0.0 is repaired the next time TrayLauncher runs.
- Uninstalling now turns off "Start with Windows".
- apps.json saved as UTF-8 with BOM or UTF-16 now loads.
- A mistake in one apps.json entry no longer closes the program. The entry is left out and the menu shows an error line.
- `args` written as text instead of a list counts as one argument, instead of being split into letters.
- `start_in` now expands environment variables such as `%USERPROFILE%`.
- A program that fails to start no longer makes the menu open a second time.
- `--version` shows a message box, because the program has no console window.
- "Edit apps list" falls back to Notepad when no program is set for `.json` files.
- The menu opens on the monitor that was clicked.
- A menu taller than the screen scrolls with the mouse wheel.
- The menu closes after 10 seconds if Windows never gave it focus and the mouse is not over it.
- Icons are refreshed when a program is updated, and at least once a week.
- Icon edges no longer show dark fringes.
- Build tools and libraries are pinned to exact versions and download hashes.
- Building from source needs Python 3.11 or newer.

## 1.0.0

- First release.
- Taskbar popup menu with app icons, light and dark theme, rounded Windows 11 style.
- Folders open as flyout panels, including folders inside folders.
- Launches desktop apps, Microsoft Store apps, files, folders and web addresses.
- Optional system tray mode with "Start with Windows".
