[Files]
Source: dist\WikidPad.exe; DestDir: {app}; Components: Program_files; Flags: replacesameversion
Source: dist\export\wikistyle.css; DestDir: {app}\export\; Components: Program_files; Flags: confirmoverwrite
Source: dist\extensions\EvalLibrary.py; DestDir: {app}\extensions\; Components: Program_files
Source: dist\extensions\KeyBindings.py; DestDir: {app}\extensions\; Components: Program_files
Source: dist\extensions\WikidPadHooks.py; DestDir: {app}\extensions\; Components: Program_files
Source: dist\extensions\WikiSyntax.py; DestDir: {app}\extensions\; Components: Program_files
Source: dist\extensions\Presentation.py; DestDir: {app}\extensions\; Components: Program_files
Source: dist\extensions\referrals.py; DestDir: {app}\extensions\; Components: Program_files
Source: dist\extensions\autoNew.py; DestDir: {app}\extensions\; Components: Program_files
Source: dist\icons\*.gif; DestDir: {app}\icons\; Components: Program_files; Flags: onlyifdoesntexist
Source: dist\icons\pwiki.ico; DestDir: {app}\icons\; Components: Program_files; Flags: onlyifdoesntexist
Source: dist\WikidPadHelp\*; DestDir: {app}\WikidPadHelp\; Components: Gadfly\Help; Flags: recursesubdirs
Source: dist\w9xpopen.exe; DestDir: {app}; Components: Program_files
Source: dist\license.txt; DestDir: {app}; Components: Program_files
Source: dist\readme_Wic.txt; DestDir: {app}; Components: Program_files
Source: dist\python24.dll; DestDir: {app}; Components: Program_files
Source: dist\MSVCR71.dll; DestDir: {app}; Components: Program_files
Source: dist\sqlite3.dll; DestDir: {app}; Components: Sqlite
Source: dist\wxmsw26uh_stc_vc.dll; DestDir: {app}; Components: Program_files
Source: dist\wxmsw26uh_vc.dll; DestDir: {app}; Components: Program_files
Source: dist\_controls_.pyd; DestDir: {app}; Components: Program_files
Source: dist\_core_.pyd; DestDir: {app}; Components: Program_files
Source: dist\_ctypes.pyd; DestDir: {app}; Components: Sqlite
Source: dist\_gdi_.pyd; DestDir: {app}; Components: Program_files
Source: dist\_html.pyd; DestDir: {app}; Components: Program_files
Source: dist\_misc_.pyd; DestDir: {app}; Components: Program_files
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
Name: {app}\export; Components: Program_files
[Setup]
SolidCompression=true
AppName=WikidPad
AppVerName=WikidPad 1.6beta2
DefaultDirName={pf}\WikidPad
DefaultGroupName=WikidPad
AppID={{22A83C29-58A8-4CAB-8EDC-918D74F8429E}
VersionInfoVersion=1.6
VersionInfoTextVersion=WikidPad 1.6beta2
LicenseFile=C:\DATEN\Projekte\Wikidpad\Current\license.txt
AllowNoIcons=true
ShowLanguageDialog=yes
Compression=lzma/ultra
OutputBaseFilename=WikidPad-1.6beta2
InternalCompressLevel=ultra
AppCopyright=© 2005-2006 Jason Horman, Michael Butscher, Gerhard Reitmayr
[Components]
Name: Program_files; Description: Main program files; Flags: fixed; Types: custom compact full
Name: Gadfly; Description: Gadfly database; Types: custom compact full
Name: Gadfly\Help; Description: Help wiki; Types: custom compact full
Name: Sqlite; Description: Sqlite database; Types: full
[Icons]
Name: {group}\WikidPad; Filename: {app}\WikidPad.exe; IconFilename: {app}\icons\pwiki.ico; IconIndex: 0; Components: Program_files Gadfly\Help
Name: {group}\{cm:UninstallProgram, WikidPad}; Filename: {uninstallexe}
[Registry]
Root: HKCR; SubKey: .wiki; ValueType: string; ValueData: wikidPadFile; Flags: uninsdeletekey; Tasks: assocWiki
Root: HKCR; SubKey: wikidPadFile; ValueType: string; ValueData: WikidPad File; Flags: uninsdeletekey; Tasks: assocWiki
Root: HKCR; SubKey: wikidPadFile\Shell\Open\Command; ValueType: string; ValueData: """{app}\WikidPad.exe"" ""%1"""; Flags: uninsdeletevalue; Tasks: assocWiki
Root: HKCR; Subkey: wikidPadFile\DefaultIcon; ValueType: string; ValueData: {app}\icons\pwiki.ico,0; Flags: uninsdeletevalue; Tasks: assocWiki
Root: HKCR; Subkey: wiki; ValueType: string; ValueData: URL:WikidPad Protocol; Flags: uninsdeletekey; Tasks: assocWikiUrl
Root: HKCR; Subkey: wiki; ValueType: string; ValueName: URL Protocol; Flags: uninsdeletevalue; Tasks: assocWikiUrl
Root: HKCR; Subkey: wiki\shell; ValueType: string; ValueData: open; Flags: uninsdeletevalue; Tasks: assocWikiUrl
Root: HKCR; Subkey: wiki\DefaultIcon; ValueType: string; ValueData: {app}\icons\pwiki.ico,0; Flags: uninsdeletevalue; Tasks: assocWikiUrl
Root: HKCR; Subkey: wiki\shell\open\command; ValueType: string; ValueData: """{app}\WikidPad.exe"" ""%1"""; Flags: uninsdeletevalue; Tasks: assocWikiUrl
[Tasks]
Name: assocWiki; Description: Associate WikidPad with .wiki files
Name: assocWikiUrl; Description: "Handle URLs with ""wiki:"" by WikidPad"
[InstallDelete]
Name: {app}\regexpr.cache; Type: files
[UninstallDelete]
Name: {app}\regexpr.cache; Type: files
