# TrayLauncher

A one-click app menu for the Windows taskbar. Pin it, click it, and a menu pops up above the icon with your apps. Pick one to launch it.

It looks like a normal Windows 11 flyout: rounded corners, real app icons, light or dark to match your system. Folders open as side panels, and folders can sit inside folders.

Built and tested on Windows 11. Windows 10 should work too, but it has not been tested there.

## Install

1. Go to the [Releases](../../releases) page and download `TrayLauncher-Setup-<version>.exe`.
2. Run it. It installs for your user only, so it does not need administrator rights.
3. Open the Start menu, find TrayLauncher, and drag it onto the taskbar.
   If dragging does not work, right-click it, choose Open file location, right-click `TrayLauncher.exe`, choose Show more options, then Pin to taskbar.
4. Click the pinned icon.

Windows may show a "Windows protected your PC" screen the first time, because the installer is not code signed. Choose More info, then Run anyway.

There is also a portable zip on the Releases page. Unzip it anywhere and run `TrayLauncher.exe`.

## Choose your apps

Click "Edit apps list" at the bottom of the menu, or open `apps.json` in the install folder (`%LOCALAPPDATA%\Programs\TrayLauncher`). Save the file and open the menu again. No restart is needed.

```json
{
  "apps": [
    { "name": "Notepad", "path": "notepad.exe" },
    { "separator": true },
    {
      "name": "AI",
      "items": [
        { "name": "ChatGPT", "path": "shell:AppsFolder\\OpenAI.Codex_2p2nqsd0c76g0!App" },
        { "name": "Docs", "path": "https://example.com/docs" }
      ]
    }
  ]
}
```

Each entry can have:

| Field | Meaning |
| --- | --- |
| `name` | Text shown in the menu. |
| `path` | What to open: a program, file, folder, web address, or Store app (see below). Environment variables such as `%APPDATA%` work. |
| `args` | Optional list of arguments to pass to a program. |
| `start_in` | Optional folder to start the program in (used with `args`). |
| `icon` | Optional path to a `.png`, `.ico`, or program to take the icon from. |
| `items` | A list of entries. This makes the entry a folder. Folders can contain folders. |
| `separator` | `true` draws a divider line. |

In JSON, write each backslash twice (`\\`).

If the file has a mistake, the menu shows an error line at the top and your file is left alone.

### Store apps and other apps without a normal path

Run this in PowerShell to list the name and ID of an app. Change the words in the quotes to find yours.

```powershell
powershell.exe -NoProfile -Command 'Get-StartApps | Where-Object { $_.Name -match ''claude|chatgpt'' } | Format-List Name, AppID'
```

Then use the ID like this: `"path": "shell:AppsFolder\\<AppID>"`.

For classic apps that show up in the Start menu but have no useful ID, point `path` at their shortcut instead, for example `%APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs\\My App.lnk`.

## Options

Run `TrayLauncher.exe` with one of these:

| Option | What it does |
| --- | --- |
| (none) | Show the menu, then exit when you pick something. This is what the pinned taskbar icon does. |
| `--tray` | Stay running as an icon in the system tray (by the clock). The tray menu has a "Start with Windows" switch. |
| `--classic` | Use the plain Windows menu instead of the styled one. |
| `--version` | Print the version. |

## Troubleshooting

If the menu looks plain instead of styled, the styled menu hit an error and fell back. The reason is written to `%LOCALAPPDATA%\TrayLauncher\error.log`. Please include it if you open an issue.

If an app shows a coloured letter instead of its icon, Windows could not supply one. Set the `icon` field for that entry.

## Uninstall

Use Settings, Apps, Installed apps, then remove TrayLauncher. Your `apps.json` is kept in case you reinstall.

## Build from source

You need Python 3.9 or newer.

```
pip install -r requirements-dev.txt
python -m pytest
build.bat
```

`build.bat` makes `dist\TrayLauncher\TrayLauncher.exe`. If TrayLauncher is already installed, it also updates the installed copy and keeps your `apps.json`.

The tests run on any system. The menu itself only runs on Windows.

## Make a release

Releases are built by GitHub Actions. Update `CHANGELOG.md` and `__version__` in `traylauncher.py`, then push a tag:

```
git tag v1.0.1
git push origin v1.0.1
```

The workflow runs the tests, builds the program, checks it starts with all its libraries, builds the installer and a portable zip, and publishes them on the Releases page.

## Licence

MIT. See `LICENSE`.
