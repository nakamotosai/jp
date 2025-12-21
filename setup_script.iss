; 脚本生成向导
#define MyAppName "AI 日语输入法"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Cai Siyang"
#define MyAppURL "https://github.com/your-repo"
#define MyAppExeName "AI_JP_Input.exe"

[Setup]
; NOTE: 下面的 AppId 的值唯一标识该应用程序。
; 不要在这个安装程序中用于其他应用程序。
; (从 Inno Setup IDE 中的 "Tools" -> "Generate GUID" 生成一个新的 GUID 并替换此处)
AppId={{YOUR-GUID-HERE}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\AI_JP_Input
DisableProgramGroupPage=yes
DisableDirPage=no
OutputBaseFilename=AI_JP_Input_Setup_v{#MyAppVersion}
Compression=lzma
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "chinese"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; 主程序
Source: "dist\AI_JP_Input.exe"; DestDir: "{app}"; Flags: ignoreversion
; 包含 logo (如果有)
Source: "logo.png"; DestDir: "{app}"; Flags: ignoreversion; Tasks: desktopicon
; 如果有其他依赖资源（非 Python 库，例如 fonts），请在此添加
; Source: "fonts\*"; DestDir: "{app}\fonts"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent
