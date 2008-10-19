[Setup]
SolidCompression=true
AppName=WikidPadHelpAnd1stSteps
AppVerName=WikidPad help and first steps
DefaultDirName={reg:HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{{22A83C29-58A8-4CAB-8EDC-918D74F8429E%7d_is1,InstallLocation|{pf}\WikidPad}\HelpAnd1stSteps
DefaultGroupName=WikidPad
AppID={{8C751029-AC6E-43AC-B2CE-F13EB8D84DAD}
VersionInfoVersion=0.3
VersionInfoTextVersion=WikidPad help and first steps 0.3
LicenseFile=
AllowNoIcons=true
ShowLanguageDialog=no
Compression=lzma/ultra
OutputBaseFilename=WP-HelpAnd1stSteps-0.3
InternalCompressLevel=ultra
AppCopyright=© 2008 Jan Stegehuis
UsePreviousAppDir=true
EnableDirDoesntExistWarning=false
DisableProgramGroupPage=false
UsePreviousGroup=true
DirExistsWarning=no
[Icons]
Name: {group}\{cm:UninstallProgram, WikidPadHelpAnd1stSteps}; Filename: {uninstallexe}
Name: {group}\HelpAnd1stSteps; Filename: {reg:HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{{22A83C29-58A8-4CAB-8EDC-918D74F8429E%7d_is1,InstallLocation|{pf}\WikidPad}\WikidPad.exe; Parameters: {app}\Help.wiki
[Files]
Source: HelpAnd1stSteps\*; DestDir: {app}\; Flags: recursesubdirs ignoreversion
[Dirs]
Name: {app}
