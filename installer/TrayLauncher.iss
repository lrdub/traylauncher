; Inno Setup script. Build with:  iscc /DAppVersion=1.0.0 installer\TrayLauncher.iss
; Expects dist\TrayLauncher (PyInstaller output) and icon.ico in the repo root.

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

[Setup]
AppId={{7C40C288-DDF4-4B0C-8ECE-F2A673817130}
AppName=TrayLauncher
AppVersion={#AppVersion}
AppPublisher=TrayLauncher contributors
DefaultDirName={localappdata}\Programs\TrayLauncher
DisableProgramGroupPage=yes
DisableDirPage=yes
PrivilegesRequired=lowest
OutputDir=..\release
OutputBaseFilename=TrayLauncher-Setup-{#AppVersion}
SetupIconFile=..\icon.ico
UninstallDisplayIcon={app}\TrayLauncher.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
InfoAfterFile=after-install.txt

[Files]
; The program itself. Updates overwrite these files.
Source: "..\dist\TrayLauncher\*"; DestDir: "{app}"; Excludes: "apps.json"; Flags: ignoreversion recursesubdirs createallsubdirs
; The app list: written once, never overwritten on update, never removed on uninstall.
Source: "..\apps.example.json"; DestDir: "{app}"; DestName: "apps.json"; Flags: onlyifdoesntexist uninsneveruninstall

[Icons]
Name: "{userprograms}\TrayLauncher"; Filename: "{app}\TrayLauncher.exe"

[UninstallDelete]
; Icon cache and error log
Type: filesandordirs; Name: "{localappdata}\TrayLauncher"

[Code]
// "Start with Windows" (tray mode) saves a value under the Run key. Remove it on uninstall,
// or Windows would try to start the deleted program at every sign-in.
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then
    RegDeleteValue(HKEY_CURRENT_USER, 'Software\Microsoft\Windows\CurrentVersion\Run', 'TrayLauncher');
end;
