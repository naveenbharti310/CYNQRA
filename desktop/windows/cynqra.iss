; Cynqra for Windows: the installer. Built by desktop/build.py with Inno Setup 6:
;   iscc /DAppVersion=0.1.0 /DSourceDir=<staged app> /DOutputDir=<dist> /DIconFile=<cynqra.ico> cynqra.iss
; Installs for the current user (no administrator rights) under %LOCALAPPDATA%\Programs\Cynqra.
; Models and runs live in %LOCALAPPDATA%\Cynqra; uninstalling asks whether to delete them.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{6F4B7C1E-2A8D-4E5B-9C31-7D0E8A2F5B64}
AppName=Cynqra
AppVersion={#AppVersion}
AppVerName=Cynqra {#AppVersion}
AppPublisher=Cynqra
AppComments=The organization that builds with you, running on an open model on this computer.
DefaultDirName={localappdata}\Programs\Cynqra
DefaultGroupName=Cynqra
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
OutputDir={#OutputDir}
OutputBaseFilename=Cynqra-Setup-{#AppVersion}-windows-x64
SetupIconFile={#IconFile}
UninstallDisplayIcon={app}\cynqra.ico
UninstallDisplayName=Cynqra
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{autoprograms}\Cynqra"; Filename: "{app}\python\pythonw.exe"; Parameters: "-X utf8 ""{app}\app\desktop.py"""; WorkingDir: "{app}"; IconFilename: "{app}\cynqra.ico"; Comment: "Cynqra"
Name: "{autodesktop}\Cynqra"; Filename: "{app}\python\pythonw.exe"; Parameters: "-X utf8 ""{app}\app\desktop.py"""; WorkingDir: "{app}"; IconFilename: "{app}\cynqra.ico"; Comment: "Cynqra"; Tasks: desktopicon

[Run]
Filename: "{app}\python\pythonw.exe"; Parameters: "-X utf8 ""{app}\app\desktop.py"""; WorkingDir: "{app}"; Description: "Start Cynqra"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\app"
Type: filesandordirs; Name: "{app}\python"

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Data: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    Data := ExpandConstant('{localappdata}\Cynqra');
    if DirExists(Data) and not UninstallSilent() then
      if MsgBox('Also delete the downloaded models and every Cynqra run in ' + Data + '?' + #13#10#13#10 +
                'Choose No to keep them for the next install.', mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
        DelTree(Data, True, True, True);
  end;
end;
