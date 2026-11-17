; Inno Setup script for WiFi Fortress (Windows build)
;
; Build the payload first:
;   python -m PyInstaller packaging/windows/wifi-fortress.spec --noconfirm ^
;          --distpath build/win/dist --workpath build/win/work
;
; Then compile this script with Inno Setup 6:
;   iscc packaging\windows\wifi-fortress.iss
;
; Output: packaging\windows\output\WiFi-Fortress-1.1.0-Windows-Setup.exe

#define AppName "WiFi Fortress"
#define AppVersion "1.1.0"
#define AppPublisher "WiFi Fortress Project"
#define AppURL "https://github.com/unupunct/WIFI-Fortress"
#define AppExe "WiFi Fortress.exe"
#define SourceDir "..\..\build\win\dist\WiFi Fortress"

[Setup]
AppId={{9B21C6B4-7E4A-4B7E-9C1D-3A5F2D8E6C10}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
AppUpdatesURL={#AppURL}/releases
VersionInfoVersion={#AppVersion}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
LicenseFile=LICENSE.txt
OutputDir=output
OutputBaseFilename=WiFi-Fortress-{#AppVersion}-Windows-Setup
SetupIconFile=wifi-fortress.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
MinVersion=10.0

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"; Comment: "Wireless security audit and diagnostics"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
Filename: "{app}\{#AppExe}"; Parameters: "--selftest"; Description: "Run the installation self-test"; Flags: nowait postinstall unchecked

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
