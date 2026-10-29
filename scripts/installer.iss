#define AppName "CodeDesk"
#ifndef AppVersion
#error Build through scripts/build_windows.py to provide AppVersion
#endif
#ifndef SourceRoot
#error Build through scripts/build_windows.py to provide SourceRoot
#endif
#ifndef OutputRoot
#error Build through scripts/build_windows.py to provide OutputRoot
#endif
#ifdef SignedBuild
#define BuildSuffix ""
#else
#ifndef UnsignedDevelopment
#error Choose a signed build or explicitly define UnsignedDevelopment
#endif
#define BuildSuffix "-unsigned"
#endif
[Setup]
AppId={{7F648483-55EC-49C4-9DFA-DC8447AD9DB7}
AppName={#AppName}{#BuildSuffix}
AppVersion={#AppVersion}
AppPublisher=CodeDesk Course Project
DefaultDirName={localappdata}\Programs\CodeDesk
DefaultGroupName=CodeDesk
PrivilegesRequired=lowest
OutputDir={#OutputRoot}
OutputBaseFilename=CodeDesk-Setup-{#AppVersion}{#BuildSuffix}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\CodeDesk.exe
CloseApplications=yes
SetupLogging=yes
#ifdef SignedBuild
SignTool=codedesk
SignedUninstaller=yes
SignedUninstallerDir={#SigningCache}
SignToolRetryCount=2
#else
SignedUninstaller=no
VersionInfoDescription=UNSIGNED DEVELOPMENT BUILD - NOT RELEASE APPROVED
#endif

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: checkedonce

[Files]
Source: "{#SourceRoot}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\CodeDesk"; Filename: "{app}\CodeDesk.exe"
Name: "{autodesktop}\CodeDesk"; Filename: "{app}\CodeDesk.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\CodeDesk.exe"; Description: "Launch CodeDesk"; Flags: nowait postinstall skipifsilent
