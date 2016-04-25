[Files]
Source: dist\WikidPad.exe; DestDir: {app}; Flags: replacesameversion ignoreversion
Source: dist\appbase.css; DestDir: {app}
Source: extensions\*.py; DestDir: {app}\extensions\; Flags: recursesubdirs ignoreversion
Source: extensions\*.pyf; DestDir: {app}\extensions\; Flags: recursesubdirs ignoreversion
Source: extensions\*.zipf; DestDir: {app}\extensions\; Flags: recursesubdirs ignoreversion
Source: dist\icons\*.gif; DestDir: {app}\icons\; Flags: onlyifdoesntexist
Source: dist\icons\pwiki.ico; DestDir: {app}\icons\; Flags: onlyifdoesntexist
Source: dist\WikidPadHelp\*; DestDir: {app}\WikidPadHelp\; Flags: recursesubdirs ignoreversion
Source: dist\license.txt; DestDir: {app}
Source: dist\python26.dll; DestDir: {app}
Source: dist\sqlite3.dll; DestDir: {app}
Source: dist\wxbase28uh_net_vc.dll; DestDir: {app}; Check: ShouldInstallWxRuntime
Source: dist\wxbase28uh_vc.dll; DestDir: {app}; Check: ShouldInstallWxRuntime
Source: dist\wxbase28uh_xml_vc.dll; DestDir: {app}; Check: ShouldInstallWxRuntime
Source: dist\wxmsw28uh_adv_vc.dll; DestDir: {app}; Check: ShouldInstallWxRuntime
Source: dist\wxmsw28uh_core_vc.dll; DestDir: {app}; Check: ShouldInstallWxRuntime
Source: dist\wxmsw28uh_html_vc.dll; DestDir: {app}; Check: ShouldInstallWxRuntime
Source: dist\wxmsw28uh_stc_vc.dll; DestDir: {app}; Check: ShouldInstallWxRuntime
Source: dist\wxmsw28uh_xrc_vc.dll; DestDir: {app}; Check: ShouldInstallWxRuntime
Source: dist\_ctypes.pyd; DestDir: {app}; Flags: replacesameversion ignoreversion
Source: dist\_hashlib.pyd; DestDir: {app}; Flags: replacesameversion ignoreversion
Source: dist\_multiprocessing.pyd; DestDir: {app}; Flags: replacesameversion ignoreversion
Source: dist\pyexpat.pyd; DestDir: {app}; Flags: replacesameversion ignoreversion
Source: dist\_sqlite3.pyd; DestDir: {app}; Flags: replacesameversion ignoreversion
Source: dist\_socket.pyd; DestDir: {app}; Flags: replacesameversion ignoreversion
Source: dist\select.pyd; DestDir: {app}; Flags: replacesameversion ignoreversion
Source: dist\wx._controls_.pyd; DestDir: {app}; Flags: replacesameversion ignoreversion; Check: ShouldInstallWxRuntime
Source: dist\wx._core_.pyd; DestDir: {app}; Flags: replacesameversion ignoreversion; Check: ShouldInstallWxRuntime
Source: dist\wx._gdi_.pyd; DestDir: {app}; Flags: replacesameversion ignoreversion; Check: ShouldInstallWxRuntime
Source: dist\wx._grid.pyd; DestDir: {app}; Flags: replacesameversion ignoreversion; Check: ShouldInstallWxRuntime
Source: dist\wx._html.pyd; DestDir: {app}; Flags: replacesameversion ignoreversion; Check: ShouldInstallWxRuntime
Source: dist\wx._misc_.pyd; DestDir: {app}; Flags: replacesameversion ignoreversion; Check: ShouldInstallWxRuntime
Source: dist\wx._stc.pyd; DestDir: {app}; Flags: replacesameversion ignoreversion; Check: ShouldInstallWxRuntime
Source: dist\wx._windows_.pyd; DestDir: {app}; Flags: replacesameversion ignoreversion; Check: ShouldInstallWxRuntime
Source: dist\wx._xrc.pyd; DestDir: {app}; Flags: replacesameversion ignoreversion; Check: ShouldInstallWxRuntime
Source: dist\WikidPad.xrc; DestDir: {app}
Source: dist\WikidPad_*.po; DestDir: {app}; Flags: ignoreversion sortfilesbyextension
Source: dist\langlist.txt; DestDir: {app}; Flags: replacesameversion ignoreversion
Source: dist\gadfly.zip; DestDir: {app}; Flags: nocompression
Source: dist\library.zip; DestDir: {app}; Flags: nocompression
Source: docs\MenuHandling_contextInfo.txt; DestDir: {app}\docs\; Flags: recursesubdirs ignoreversion
Source: WikidPad-winport.config; DestDir: {app}; DestName: WikidPad.config; Flags: onlyifdoesntexist; Check: PortableInstall
Source: Microsoft.VC90.CRT.manifest; DestDir: {app}
Source: winBinAdditions\msvcp90.dll; DestDir: {app}
Source: winBinAdditions\msvcr90.dll; DestDir: {app}
Source: winBinAdditions\msvcm90.dll; DestDir: {app}
Source: winBinAdditions\gdiplus.dll; DestDir: {app}
[Dirs]
Name: {app}\extensions
Name: {app}\icons
Name: {app}\WikidPadHelp
Name: {app}\WikidPadHelp\data
Name: {app}\WikidPadHelp\files
Name: {app}\export
[Setup]
#define verStr "2.3beta15"
#define verNo "002.003.115.000"

SolidCompression=true
AppName=WikidPad
AppVerName=WikidPad {#verStr}
DefaultDirName={pf}\WikidPad
DefaultGroupName=WikidPad
AppID={{22A83C29-58A8-4CAB-8EDC-918D74F8429E}
VersionInfoVersion={#verNo}
VersionInfoTextVersion=WikidPad {#verStr}
LicenseFile=license.txt
AllowNoIcons=true
ShowLanguageDialog=yes
Compression=lzma/ultra
OutputBaseFilename=WikidPad-{#verStr}
InternalCompressLevel=ultra
AppCopyright=© 2005-2016 Jason Horman, Michael Butscher, Gerhard Reitmayr
UsePreviousAppDir=true
PrivilegesRequired=none
CreateUninstallRegKey=not PortableInstall
Uninstallable=not PortableInstall
[INI]
Filename: {app}\binInst.ini; Section: Main; Key: CurrVersion; String: {#verNo}; Flags: createkeyifdoesntexist uninsdeleteentry uninsdeletesectionifempty
Filename: {app}\binInst.ini; Section: Main; Key: wxVersion; String: 002.008.010.001; Flags: createkeyifdoesntexist uninsdeleteentry uninsdeletesectionifempty; Check: ShouldInstallWxRuntime
Filename: {app}\binInst.ini; Section: Main; Key: portableInstall; String: 0; Flags: uninsdeleteentry uninsdeletesectionifempty; Check: not PortableInstall
Filename: {app}\binInst.ini; Section: Main; Key: portableInstall; String: 1; Flags: uninsdeleteentry uninsdeletesectionifempty; Check: PortableInstall
[Icons]
Name: {code:IconDest|Dummy}\WikidPad; Filename: {app}\WikidPad.exe; IconFilename: {app}\icons\pwiki.ico; IconIndex: 0; Check: not PortableInstall
Name: {code:IconDest|Dummy}\{cm:UninstallProgram, WikidPad}; Filename: {uninstallexe}; Check: not PortableInstall
[Registry]
Root: HKCR; SubKey: .wiki; ValueType: string; ValueData: wikidPadFile; Flags: uninsdeletekey; Tasks: assocWiki; Check: GlobalRegClasses
Root: HKCR; SubKey: wikidPadFile; ValueType: string; ValueData: WikidPad File; Flags: uninsdeletekey; Tasks: assocWiki; Check: GlobalRegClasses
Root: HKCR; SubKey: wikidPadFile\Shell\Open\Command; ValueType: string; ValueData: """{app}\WikidPad.exe"" ""%1"""; Flags: uninsdeletevalue; Tasks: assocWiki; Check: GlobalRegClasses
Root: HKCR; Subkey: wikidPadFile\DefaultIcon; ValueType: string; ValueData: {app}\icons\pwiki.ico,0; Flags: uninsdeletevalue; Tasks: assocWiki; Check: GlobalRegClasses
Root: HKCR; Subkey: wiki; ValueType: string; ValueData: URL:WikidPad Protocol; Flags: uninsdeletekey; Tasks: assocWikiUrl; Check: GlobalRegClasses
Root: HKCR; Subkey: wiki; ValueType: string; ValueName: URL Protocol; Flags: uninsdeletevalue; Tasks: assocWikiUrl; Check: GlobalRegClasses
Root: HKCR; Subkey: wiki\shell; ValueType: string; ValueData: open; Flags: uninsdeletevalue; Tasks: assocWikiUrl; Check: GlobalRegClasses
Root: HKCR; Subkey: wiki\DefaultIcon; ValueType: string; ValueData: {app}\icons\pwiki.ico,0; Flags: uninsdeletevalue; Tasks: assocWikiUrl; Check: GlobalRegClasses
Root: HKCR; Subkey: wiki\shell\open\command; ValueType: string; ValueData: """{app}\WikidPad.exe"" ""%1"""; Flags: uninsdeletevalue; Tasks: assocWikiUrl; Check: GlobalRegClasses

Root: HKCU; Subkey: Software\Classes\.wiki; ValueType: string; ValueData: wikidPadFile; Flags: uninsdeletekey; Check: UserRegClasses
Root: HKCU; SubKey: Software\Classes\wikidPadFile; ValueType: string; ValueData: WikidPad File; Flags: uninsdeletekey; Tasks: assocWiki; Check: UserRegClasses
Root: HKCU; SubKey: Software\Classes\wikidPadFile\Shell\Open\Command; ValueType: string; ValueData: """{app}\WikidPad.exe"" ""%1"""; Flags: uninsdeletevalue; Tasks: assocWiki; Check: UserRegClasses
Root: HKCU; Subkey: Software\Classes\wikidPadFile\DefaultIcon; ValueType: string; ValueData: {app}\icons\pwiki.ico,0; Flags: uninsdeletevalue; Tasks: assocWiki; Check: UserRegClasses
Root: HKCU; Subkey: Software\Classes\wiki; ValueType: string; ValueData: URL:WikidPad Protocol; Flags: uninsdeletekey; Tasks: assocWikiUrl; Check: UserRegClasses
Root: HKCU; Subkey: Software\Classes\wiki; ValueType: string; ValueName: URL Protocol; Flags: uninsdeletevalue; Tasks: assocWikiUrl; Check: UserRegClasses
Root: HKCU; Subkey: Software\Classes\wiki\shell; ValueType: string; ValueData: open; Flags: uninsdeletevalue; Tasks: assocWikiUrl; Check: UserRegClasses
Root: HKCU; Subkey: Software\Classes\wiki\DefaultIcon; ValueType: string; ValueData: {app}\icons\pwiki.ico,0; Flags: uninsdeletevalue; Tasks: assocWikiUrl; Check: UserRegClasses
Root: HKCU; Subkey: Software\Classes\wiki\shell\open\command; ValueType: string; ValueData: """{app}\WikidPad.exe"" ""%1"""; Flags: uninsdeletevalue; Tasks: assocWikiUrl; Check: UserRegClasses

[Tasks]
Name: assocWiki; Description: Associate WikidPad with .wiki files; Check: not PortableInstall
Name: assocWikiUrl; Description: "Handle URLs with ""wiki:"" by WikidPad"; Check: not PortableInstall
[InstallDelete]
Name: {app}\regexpr.cache; Type: files
Name: {app}\zlib.pyd; Type: files
Name: {app}\extensions\WikiSyntax.py; Type: files

[UninstallDelete]
Name: {app}\regexpr.cache; Type: files
Name: {app}\binInst.ini; Type: files
Name: {app}\WikidPad_*.xrc; Type: files
Name: {app}\extensions\*.pyc; Type: filesandordirs
Name: {app}\extensions\*.pyo; Type: filesandordirs
Name: {app}\extensions\wikidPadParser\*.pyc; Type: filesandordirs
Name: {app}\extensions\wikidPadParser\*.pyo; Type: filesandordirs
[Run]
Filename: {app}\WikidPad.exe; WorkingDir: {app}; Description: Start WikidPad; Flags: postinstall skipifsilent nowait
[LangOptions]
LanguageID=$0000
[Code]
var
  PortableModeQuestion: TInputOptionWizardPage;
  UserModeQuestion: TInputOptionWizardPage;
  NotAdminMessage: TOutputMsgWizardPage;


function PortableInstall: Boolean;
begin
  result := PortableModeQuestion.SelectedValueIndex = 1
end;


function ShouldAskForUsermode: Boolean;
begin
  result := UsingWinNT and IsAdminLoggedOn;
end;

procedure InitializeWizard;
begin
  PortableModeQuestion := CreateInputOptionPage(wpLicense,
    'Portable installation?',
    'Install in portable mode, e.g. on a USB stick (to uninstall, just delete the created folder)',
    '',
    True, False);
  PortableModeQuestion.Add('Standard installation');
  PortableModeQuestion.Add('Portable installation (no uninstaller, no file associations)');

  PortableModeQuestion.SelectedValueIndex := 0;


  if ShouldAskForUsermode then begin
    UserModeQuestion := CreateInputOptionPage(PortableModeQuestion.ID,
      'Installation mode',
      'You install as admin, choose for whom you want to install',
      'Install WikidPad for',
      True, False);
    UserModeQuestion.Add('All Users');
    UserModeQuestion.Add('Current User');

    UserModeQuestion.SelectedValueIndex := 0;
  end
  else if UsingWinNT then begin
    NotAdminMessage := CreateOutputMsgPage(PortableModeQuestion.ID,
      'Not in admin mode', 'You should install as admin',
      'This program can be installed for all users if you run it as administrator. ' +
      'You can now abort the setup and log in as administrator.'#13#13 +
      'If you cannot or don''t want to do that, you can just continue and install ' +
      'it for current user only.'#13#13 +
      'If you continue, be aware that the installer maybe can''t ' +
      'install in the suggested default directory. You may receive an ' +
      'error message if you try that.');
  end
end;

function IsUserModePage(PageID: Integer): Boolean;
begin
  if ShouldAskForUsermode then begin
    result := UserModeQuestion.ID = PageID;
  end
  else if UsingWinNT then
    result := NotAdminMessage.ID = PageID;
end;


function ShouldSkipPage(PageID: Integer): Boolean;
begin
  if PortableInstall then begin
    result := IsUserModePage(PageID) or (PageID = wpSelectProgramGroup);
  end
  else
    result := false;
end;


function IconDest(Param: String): String;
begin
  if ShouldAskForUsermode() and (UserModeQuestion.SelectedValueIndex = 0) then
    // All users
    Result := ExpandConstant('{commonprograms}\{groupname}')
  else
    // Current user
    Result := ExpandConstant('{userprograms}\{groupname}');
end;


function GlobalRegClasses: Boolean;
// Returns true iff registry entries should go to global HK_CR root.
// If false, they go to HK_CU\Software\Classes (or nowhere in portable mode)
begin
  if PortableInstall then begin
    Result := false;
    exit;
  end;

  if ShouldAskForUsermode() and (UserModeQuestion.SelectedValueIndex = 0) then
    Result := true
  else
    Result := not UsingWinNT;  // On Win 98/ME, it should always return true
end;


function UserRegClasses: Boolean;
// Returns true iff registry entries should go to HK_CU\Software\Classes
begin
  if PortableInstall then begin
    Result := false;
    exit;
  end;

  Result := not GlobalRegClasses;
end;


function ShouldInstallWxRuntime: Boolean;
// Returns true iff wxWidgets runtime should be installed.
begin
  Result := not GetIniBool('PreventInstall', 'wxPy2_8_10_1', false,
      ExpandConstant('{app}\binInst.ini'));
end;



function MemoAppend(Memo, NewContent, NewLine: String): String;
begin
  if NewContent <> '' then
    result := Memo + NewContent + NewLine + NewLine
  else
    result := Memo;
end;



function UpdateReadyMemo(Space, NewLine, MemoUserInfoInfo, MemoDirInfo, MemoTypeInfo,
    MemoComponentsInfo, MemoGroupInfo, MemoTasksInfo: String): String;
var
  Answer: String;

begin
  Answer := '';

  Answer := MemoAppend(Answer, MemoUserInfoInfo, NewLine);
  Answer := MemoAppend(Answer, MemoDirInfo, NewLine);
  Answer := MemoAppend(Answer, MemoTypeInfo, NewLine);
  Answer := MemoAppend(Answer, MemoComponentsInfo, NewLine);

  if not PortableInstall then
    Answer := MemoAppend(Answer, MemoGroupInfo, NewLine);

  Answer := MemoAppend(Answer, MemoTasksInfo, NewLine);

  Result := Answer;
end;


procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  resultCode: Integer;
begin
  // Call our function just before the actual uninstall process begins
  if CurUninstallStep = usUninstall then
  begin
    if MsgBox('Do you also want to remove your personal settings?',
        mbConfirmation, MB_YESNO) = idYes then
    begin
      Exec(ExpandConstant('{app}/WikidPad.exe'), '--deleteconfig',
          ExpandConstant('{app}'), SW_HIDE, ewWaitUntilTerminated, resultCode);
    end;
  end;
end;
