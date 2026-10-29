#define AppName "CodeDesk"
#define AppVersion "1.0.0"
[Setup]
AppId={{7F648483-55EC-49C4-9DFA-DC8447AD9DB7}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=CodeDesk Course Project
DefaultDirName={localappdata}\Programs\CodeDesk
DefaultGroupName=CodeDesk
PrivilegesRequired=lowest
OutputDir=..\release
OutputBaseFilename=CodeDesk-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\CodeDesk.exe
CloseApplications=yes
SetupLogging=yes

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: checkedonce

[Files]
Source: "..\dist\CodeDesk\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\CodeDesk"; Filename: "{app}\CodeDesk.exe"
Name: "{autodesktop}\CodeDesk"; Filename: "{app}\CodeDesk.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\CodeDesk.exe"; Description: "Launch CodeDesk"; Flags: nowait postinstall skipifsilent
