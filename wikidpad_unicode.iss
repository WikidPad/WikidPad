[Files]
Source: dist\WikidPad.exe; DestDir: {app}; Components: Program_files; Flags: replacesameversion ignoreversion
Source: dist\export\wikistyle.css; DestDir: {app}\export\; Components: Program_files; Flags: confirmoverwrite
Source: dist\extensions\*; DestDir: {app}\extensions\; Components: Program_files; Flags: recursesubdirs ignoreversion
Source: dist\icons\*.gif; DestDir: {app}\icons\; Components: Program_files; Flags: onlyifdoesntexist
Source: dist\icons\pwiki.ico; DestDir: {app}\icons\; Components: Program_files; Flags: onlyifdoesntexist
Source: dist\WikidPadHelp\*; DestDir: {app}\WikidPadHelp\; Components: Gadfly\Help; Flags: recursesubdirs ignoreversion
Source: dist\w9xpopen.exe; DestDir: {app}; Components: Program_files
Source: dist\license.txt; DestDir: {app}; Components: Program_files
Source: dist\readme_Wic.txt; DestDir: {app}; Components: Program_files
Source: dist\python24.dll; DestDir: {app}; Components: Program_files
Source: dist\MSVCR71.dll; DestDir: {app}; Components: Program_files
Source: dist\sqlite3.dll; DestDir: {app}; Components: Sqlite
Source: dist\wxmsw26uh_stc_vc.dll; DestDir: {app}; Components: Program_files
Source: dist\wxmsw26uh_vc.dll; DestDir: {app}; Components: Program_files
Source: dist\_activex.pyd; DestDir: {app}; Components: Program_files
Source: dist\_controls_.pyd; DestDir: {app}; Components: Program_files
Source: dist\_core_.pyd; DestDir: {app}; Components: Program_files
Source: dist\_ctypes.pyd; DestDir: {app}; Components: Program_files
Source: dist\_gdi_.pyd; DestDir: {app}; Components: Program_files
Source: dist\_html.pyd; DestDir: {app}; Components: Program_files
Source: dist\_misc_.pyd; DestDir: {app}; Components: Program_files
Source: dist\_socket.pyd; DestDir: {app}; Components: Program_files
Source: dist\_stc.pyd; DestDir: {app}; Components: Program_files
Source: dist\_windows_.pyd; DestDir: {app}; Components: Program_files
Source: dist\_xrc.pyd; DestDir: {app}; Components: Program_files
Source: dist\zlib.pyd; DestDir: {app}; Components: Program_files
Source: dist\WikidPad.xrc; DestDir: {app}; Components: Program_files
Source: dist\gadfly.zip; DestDir: {app}; Components: Gadfly
Source: dist\library.zip; DestDir: {app}; Components: Program_files
[Dirs]
Name: {app}\extensions; Components: Program_files
Name: {app}\icons; Components: Program_files
Name: {app}\WikidPadHelp; Components: Gadfly\Help
Name: {app}\WikidPadHelp\data; Components: Gadfly\Help
Name: {app}\WikidPadHelp\files
Name: {app}\export; Components: Program_files
[Setup]
SolidCompression=true
AppName=WikidPad
AppVerName=WikidPad 1.8rc17
DefaultDirName={pf}\WikidPad
DefaultGroupName=WikidPad
AppID={{22A83C29-58A8-4CAB-8EDC-918D74F8429E}
VersionInfoVersion=1.8.117.0
VersionInfoTextVersion=WikidPad 1.8rc17
LicenseFile=C:\DATEN\Projekte\Wikidpad\Current\license.txt
AllowNoIcons=true
ShowLanguageDialog=yes
Compression=lzma/ultra
OutputBaseFilename=WikidPad-1.8rc17
InternalCompressLevel=ultra
AppCopyright=© 2005-2008 Jason Horman, Michael Butscher, Gerhard Reitmayr
UsePreviousAppDir=true
[Components]
Name: Program_files; Description: Main program files; Flags: fixed; Types: custom compact full
Name: Gadfly; Description: Gadfly database; Types: custom compact full
Name: Gadfly\Help; Description: Help wiki; Types: custom compact full
Name: Sqlite; Description: Sqlite database; Types: full
[Icons]
Name: {code:IconDest|Dummy}\WikidPad; Filename: {app}\WikidPad.exe; IconFilename: {app}\icons\pwiki.ico; Components: Program_files Gadfly\Help; IconIndex: 0
Name: {code:IconDest|Dummy}\{cm:UninstallProgram, WikidPad}; Filename: {uninstallexe}
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

Root: HKCU; Subkey: Software\Classes\.wiki; ValueType: string; ValueData: wikidPadFile; Flags: uninsdeletekey; Check: not GlobalRegClasses
Root: HKCU; SubKey: Software\Classes\wikidPadFile; ValueType: string; ValueData: WikidPad File; Flags: uninsdeletekey; Tasks: assocWiki; Check: not GlobalRegClasses
Root: HKCU; SubKey: Software\Classes\wikidPadFile\Shell\Open\Command; ValueType: string; ValueData: """{app}\WikidPad.exe"" ""%1"""; Flags: uninsdeletevalue; Tasks: assocWiki; Check: not GlobalRegClasses
Root: HKCU; Subkey: Software\Classes\wikidPadFile\DefaultIcon; ValueType: string; ValueData: {app}\icons\pwiki.ico,0; Flags: uninsdeletevalue; Tasks: assocWiki; Check: not GlobalRegClasses
Root: HKCU; Subkey: Software\Classes\wiki; ValueType: string; ValueData: URL:WikidPad Protocol; Flags: uninsdeletekey; Tasks: assocWikiUrl; Check: not GlobalRegClasses
Root: HKCU; Subkey: Software\Classes\wiki; ValueType: string; ValueName: URL Protocol; Flags: uninsdeletevalue; Tasks: assocWikiUrl; Check: not GlobalRegClasses
Root: HKCU; Subkey: Software\Classes\wiki\shell; ValueType: string; ValueData: open; Flags: uninsdeletevalue; Tasks: assocWikiUrl; Check: not GlobalRegClasses
Root: HKCU; Subkey: Software\Classes\wiki\DefaultIcon; ValueType: string; ValueData: {app}\icons\pwiki.ico,0; Flags: uninsdeletevalue; Tasks: assocWikiUrl; Check: not GlobalRegClasses
Root: HKCU; Subkey: Software\Classes\wiki\shell\open\command; ValueType: string; ValueData: """{app}\WikidPad.exe"" ""%1"""; Flags: uninsdeletevalue; Tasks: assocWikiUrl; Check: not GlobalRegClasses

[Tasks]
Name: assocWiki; Description: Associate WikidPad with .wiki files
Name: assocWikiUrl; Description: "Handle URLs with ""wiki:"" by WikidPad"
[InstallDelete]
Name: {app}\regexpr.cache; Type: files
[UninstallDelete]
Name: {app}\regexpr.cache; Type: files
[Code]
var
  UserModeQuestion: TInputOptionWizardPage;
  NotAdminMessage: TOutputMsgWizardPage;


function ShouldAskForUsermode: Boolean;
begin
  result := UsingWinNT and IsAdminLoggedOn;
end;

procedure InitializeWizard;
begin
  if ShouldAskForUsermode then begin
    UserModeQuestion := CreateInputOptionPage(wpLicense,
      'Installation mode',
      'You install as admin, choose for whom you want to install',
      'Install WikidPad for',
      True, False);
    UserModeQuestion.Add('All Users');
    UserModeQuestion.Add('Current User');

    UserModeQuestion.SelectedValueIndex := 0;
  end
  else if UsingWinNT then begin
    NotAdminMessage := CreateOutputMsgPage(wpLicense,
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
// If false, they go to HK_CU\Software\Classes
begin
  if ShouldAskForUsermode() and (UserModeQuestion.SelectedValueIndex = 0) then
    Result := true
  else
    Result := not UsingWinNT;  // On Win 98/ME, it should always return true
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
