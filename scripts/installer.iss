; ═══════════════════════════════════════════════════════════════════════════════
; INNO SETUP SCRIPT: NOVACUT - AI VIDEO & REVIEW EDITOR (INSTALLER WIZARD)
; ═══════════════════════════════════════════════════════════════════════════════

#define MyAppName "NovaCut"
#define MyAppVersion "1.0.7"
#define MyAppPublisher "NovaCut AI Studio"
#define MyAppURL "https://novacut.ai"
#define MyAppExeName "NovaCut.exe"

[Setup]
AppId={{D37E84B1-2A4F-4C9D-9F8A-9A2E1F6B7C8D}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} v{#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DisableProgramGroupPage=yes
LicenseFile=..\LICENSE_DISCLAIMER.txt
OutputDir=..\release
OutputBaseFilename=NovaCut_Setup_v{#MyAppVersion}
SetupIconFile=..\resources\icon.ico
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64
RestartIfNeededByRun=no
AlwaysRestart=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Tệp cài đặt Microsoft Edge WebView2 Runtime Bootstrapper (tự động xóa sau khi cài xong)
Source: "..\resources\MicrosoftEdgeWebview2Setup.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall; Check: NeedsWebView2Install

; Toàn bộ thư mục release của NovaCut với đầy đủ quyền ghi cho Users
Source: "..\release\NovaCut\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Permissions: users-modify

[Dirs]
Name: "{app}"; Permissions: users-modify
Name: "{app}\bin"; Permissions: users-modify
Name: "{app}\models"; Permissions: users-modify
Name: "{app}\downloads"; Permissions: users-modify
Name: "{app}\output"; Permissions: users-modify
Name: "{app}\temp"; Permissions: users-modify
Name: "{app}\projects"; Permissions: users-modify

[Registry]
; Bật hỗ trợ đường dẫn dài không giới hạn trên Windows
Root: HKLM; Subkey: "SYSTEM\CurrentControlSet\Control\FileSystem"; ValueType: dword; ValueName: "LongPathsEnabled"; ValueData: "1"; Flags: noerror

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\resources\icon.ico"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\resources\icon.ico"; Tasks: desktopicon

[Run]
; 1. Tự động cài đặt ngầm Microsoft Edge WebView2 Runtime nếu máy khách chưa có
Filename: "{tmp}\MicrosoftEdgeWebview2Setup.exe"; Parameters: "/silent /install"; StatusMsg: "Đang cài đặt Microsoft Edge WebView2 Runtime..."; Check: NeedsWebView2Install; Flags: runhidden waituntilterminated

; 2. Khởi chạy ứng dụng NovaCut sau khi cài đặt thành công
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Code]
// Hàm kiểm tra xem máy khách đã cài đặt Microsoft Edge WebView2 Runtime hay chưa
function IsWebView2Installed(): Boolean;
var
  Version: String;
begin
  Result := False;

  // 1. Kiểm tra Registry 64-bit WOW6432Node (Machine-wide)
  if RegQueryStringValue(HKLM, 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-9F4A-4475-A603-8F3D25E4C2D5}', 'pv', Version) then
  begin
    if (Version <> '') and (Version <> '0.0.0.0') then
    begin
      Result := True;
      Exit;
    end;
  end;

  // 2. Kiểm tra Registry Native 32/64-bit (Machine-wide)
  if RegQueryStringValue(HKLM, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-9F4A-4475-A603-8F3D25E4C2D5}', 'pv', Version) then
  begin
    if (Version <> '') and (Version <> '0.0.0.0') then
    begin
      Result := True;
      Exit;
    end;
  end;

  // 3. Kiểm tra Registry User-level (Per-user install)
  if RegQueryStringValue(HKCU, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-9F4A-4475-A603-8F3D25E4C2D5}', 'pv', Version) then
  begin
    if (Version <> '') and (Version <> '0.0.0.0') then
    begin
      Result := True;
      Exit;
    end;
  end;
end;

function NeedsWebView2Install(): Boolean;
begin
  Result := not IsWebView2Installed();
end;

