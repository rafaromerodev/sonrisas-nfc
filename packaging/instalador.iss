; Instalador de Windows (Inno Setup 6).  Requiere haber generado antes dist\SonrisasNFC con PyInstaller.
; Los datos NO se instalan ni se tocan: viven en %LOCALAPPDATA%\SonrisasCanarias\NFC,
; así que reinstalar o actualizar nunca sobrescribe la base de datos.

#define AppName "Sonrisas NFC"
#define AppVersion "2.0.0"
#define AppPublisher "ONG Sonrisas Canarias"
#define AppExe "SonrisasNFC.exe"

[Setup]
AppId={{8F1C7E52-5B7A-4E7B-9C0E-3D2A61B4F0A7}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=Output
OutputBaseFilename=SonrisasNFC-{#AppVersion}-instalador
SetupIconFile=..\src\sonrisas_nfc\assets\sonrisas.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\SonrisasNFC\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
