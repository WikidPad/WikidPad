[Setup]
SolidCompression=true
AppName=WikidPadSpellAddon
AppVerName=WikidPad spell addon 2.0
DefaultDirName={reg:HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{{22A83C29-58A8-4CAB-8EDC-918D74F8429E%7d_is1,InstallLocation|{pf}\WikidPad}
DefaultGroupName=WikidPad
AppID={{8C751029-AC6E-43AC-B2CE-F13EB8D84DAD}
VersionInfoVersion=2.0
VersionInfoTextVersion=WikidPad spell addon 2.0
LicenseFile=C:\DATEN\Projekte\Wikidpad\Current\license-spelladdon.txt
AllowNoIcons=true
ShowLanguageDialog=auto
Compression=lzma/ultra
OutputBaseFilename=WP-SpellAddon-2.0
InternalCompressLevel=ultra
AppCopyright=
UsePreviousAppDir=true
EnableDirDoesntExistWarning=true
DisableProgramGroupPage=true
UsePreviousGroup=false
DirExistsWarning=no
[Icons]
Name: {group}\{cm:UninstallProgram, WikidPadSpellAddon}; Filename: {uninstallexe}
[Dirs]
Name: {app}\lib
Name: {app}\lib\enchant
Name: {app}\share
Name: {app}\share\enchant
Name: {app}\share\enchant\myspell
Name: {app}\share\enchant\ispell
[Files]
Source: ..\..\..\..\Programme\Python26\Lib\site-packages\enchant\lib\enchant\libenchant_ispell.dll; DestDir: {app}\lib\enchant
Source: ..\..\..\..\Programme\Python26\Lib\site-packages\enchant\lib\enchant\libenchant_myspell.dll; DestDir: {app}\lib\enchant
Source: ..\..\..\..\Programme\Python26\Lib\site-packages\enchant\share\enchant\myspell\en_GB.aff; DestDir: {app}\share\enchant\myspell
Source: ..\..\..\..\Programme\Python26\Lib\site-packages\enchant\share\enchant\myspell\en_GB.dic; DestDir: {app}\share\enchant\myspell
Source: ..\..\..\..\Programme\Python26\Lib\site-packages\enchant\share\enchant\myspell\en_US.aff; DestDir: {app}\share\enchant\myspell
Source: ..\..\..\..\Programme\Python26\Lib\site-packages\enchant\share\enchant\myspell\en_US.dic; DestDir: {app}\share\enchant\myspell
Source: ..\..\..\..\Programme\Python26\Lib\site-packages\enchant\share\enchant\myspell\de_DE.aff; DestDir: {app}\share\enchant\myspell
Source: ..\..\..\..\Programme\Python26\Lib\site-packages\enchant\share\enchant\myspell\de_DE.dic; DestDir: {app}\share\enchant\myspell
Source: ..\..\..\..\Programme\Python26\Lib\site-packages\enchant\share\enchant\myspell\fr_FR.aff; DestDir: {app}\share\enchant\myspell
Source: ..\..\..\..\Programme\Python26\Lib\site-packages\enchant\share\enchant\myspell\fr_FR.dic; DestDir: {app}\share\enchant\myspell
Source: ..\..\..\..\Programme\Python26\Lib\site-packages\enchant\share\enchant\ispell\README.txt; DestDir: {app}\share\enchant\ispell
Source: ..\..\..\..\Programme\Python26\Lib\site-packages\enchant\iconv.dll; DestDir: {app}
Source: ..\..\..\..\Programme\Python26\Lib\site-packages\enchant\intl.dll; DestDir: {app}
Source: ..\..\..\..\Programme\Python26\Lib\site-packages\enchant\libenchant.dll; DestDir: {app}
Source: ..\..\..\..\Programme\Python26\Lib\site-packages\enchant\libglib-2.0-0.dll; DestDir: {app}
Source: ..\..\..\..\Programme\Python26\Lib\site-packages\enchant\libgmodule-2.0-0.dll; DestDir: {app}

Source: license-spelladdon.txt; DestDir: {app}
