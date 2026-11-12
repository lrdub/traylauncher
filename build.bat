@echo off
rem Local build for development. Makes dist\TrayLauncher\TrayLauncher.exe.
rem Needs Python 3.11 or newer. Releases are built by GitHub Actions instead.
cd /d "%~dp0"

rem Use the "py" launcher that real Python installs. On a fresh Windows PC the plain
rem "python" command can be a Microsoft Store shortcut that does nothing.
set PY=
py -3 --version >nul 2>&1 && set PY=py -3
if not defined PY (
    python --version >nul 2>&1 && set PY=python
)
if not defined PY (
    echo Python is not installed.
    echo Install it with:  winget install -e --id Python.Python.3.12
    echo Then open a new window and run build.bat again.
    goto :fail
)

%PY% -m pip install --require-hashes -r requirements-lock.txt || goto :fail
%PY% traylauncher.py --make-icon || goto :fail
%PY% -m PyInstaller --noconsole --onedir --noconfirm --name TrayLauncher --icon icon.ico traylauncher.py || goto :fail
copy /y apps.example.json dist\TrayLauncher\apps.json >nul

rem If TrayLauncher is already installed, update it in place and keep its apps.json.
set "DST=%LOCALAPPDATA%\Programs\TrayLauncher"
if exist "%DST%\TrayLauncher.exe" (
    robocopy "dist\TrayLauncher" "%DST%" /E /XF apps.json >nul
    echo.
    echo Updated the installed copy in %DST%. Your apps.json was kept.
)

echo.
echo Done. Built: dist\TrayLauncher\TrayLauncher.exe
pause
exit /b 0

:fail
echo.
echo Build failed. See the messages above.
pause
exit /b 1
