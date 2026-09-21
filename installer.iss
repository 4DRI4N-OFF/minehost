; MineHost installer (Inno Setup 6)
#define AppVersion "1.0.0"

[Setup]
AppName=MineHost
AppVersion={#AppVersion}
AppPublisher=4DRI4N-OFF
AppPublisherURL=https://github.com/4DRI4N-OFF/minehost
DefaultDirName={localappdata}\MineHost
DefaultGroupName=MineHost
PrivilegesRequired=lowest
OutputDir=installer-output
OutputBaseFilename=MineHost-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Files]
Source: "dist\MineHost.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\MineHost"; Filename: "{app}\MineHost.exe"
Name: "{group}\Desinstalar MineHost"; Filename: "{uninstallexe}"
Name: "{autodesktop}\MineHost"; Filename: "{app}\MineHost.exe"; Tasks: desktopicon

[Tasks]
Name: desktopicon; Description: "Crear icono en el escritorio"; Flags: unchecked

[Run]
Filename: "{app}\MineHost.exe"; Description: "Abrir MineHost"; Flags: nowait postinstall skipifsilent
