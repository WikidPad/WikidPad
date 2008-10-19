[Setup]
SolidCompression=true
AppName=WikidPadFreeIcons
AppVerName=WikidPad free icons 1.0
DefaultDirName={reg:HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{{22A83C29-58A8-4CAB-8EDC-918D74F8429E%7d_is1,InstallLocation|{pf}\WikidPad}
DefaultGroupName=WikidPad
AppID={{8C751029-AC6E-43AC-B2CE-F13EB8D84DAD}
VersionInfoVersion=1.0
VersionInfoTextVersion=WikidPad free icons 1.0
LicenseFile=C:\Daten\Projekte\Wikidpad\Repos\branches\jstegehuis\FreeIcons\IconSet\FreeIcons-License.txt
AllowNoIcons=true
ShowLanguageDialog=auto
Compression=lzma/ultra
OutputBaseFilename=WP-FreeIcons-1.0
InternalCompressLevel=ultra
AppCopyright=
UsePreviousAppDir=true
EnableDirDoesntExistWarning=true
DisableProgramGroupPage=true
UsePreviousGroup=false
DirExistsWarning=no
[Icons]
Name: {group}\{cm:UninstallProgram, WikidPadFreeIcons}; Filename: {uninstallexe}
[Files]
Source: IconSet\*; DestDir: {app}\icons; Flags: onlyifdoesntexist
Source: IconSet\*; DestDir: {app}\icons; Flags: ignoreversion replacesameversion uninsneveruninstall onlyifdestfileexists; Tasks: OverwriteExisting
[Tasks]
Name: OverwriteExisting; Description: Overwrite existing icons (you won't be able to uninstall overwritten icons); Flags: unchecked
