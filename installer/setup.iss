#ifndef Payload
  #error Payload directory required
#endif
#ifndef Output
  #error Output directory required
#endif
[Setup]
AppId={{DF93F785-7775-43B2-A639-683B60A08986}
AppName=업무보고 작업실
AppVersion=0.2.0
AppPublisher=secret5028
AppPublisherURL=https://github.com/secret5028/upmu-bogo
DefaultDirName={localappdata}\Programs\UpmuBogo
DefaultGroupName=업무보고 작업실
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#Output}
OutputBaseFilename=UpmuBogo-Setup-0.2.0-x64
SetupIconFile={#Payload}\app\static\report-icon.ico
UninstallDisplayIcon={app}\app\static\report-icon.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes
CloseApplications=yes
RestartApplications=no
UninstallDisplayName=업무보고 작업실

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"

[Files]
Source: "{#Payload}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{userdesktop}\업무보고 작업실"; Filename: "{app}\runtime\python\pythonw.exe"; Parameters: """{app}\bootstrap.py"""; WorkingDir: "{app}"; IconFilename: "{app}\app\static\report-icon.ico"
Name: "{userprograms}\업무보고 작업실"; Filename: "{app}\runtime\python\pythonw.exe"; Parameters: """{app}\bootstrap.py"""; WorkingDir: "{app}"; IconFilename: "{app}\app\static\report-icon.ico"

[Run]
Filename: "{app}\runtime\python\pythonw.exe"; Parameters: """{app}\bootstrap.py"""; Description: "업무보고 작업실 실행"; Flags: nowait postinstall skipifsilent

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
begin
  if CurStep = ssPostInstall then
  begin
    if not Exec(ExpandConstant('{app}\runtime\python\python.exe'),
      '"' + ExpandConstant('{app}\bootstrap.py') + '" --initialize',
      ExpandConstant('{app}'), SW_HIDE, ewWaitUntilTerminated, ResultCode) then
      RaiseException('초기 설정을 실행하지 못했습니다.');
    if ResultCode <> 0 then
      RaiseException('초기 설정에 실패했습니다. 설치를 다시 실행하세요.');
  end;
end;
