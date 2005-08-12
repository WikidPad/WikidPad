;NSIS Modern User Interface version 1.63
;Written by Jason Horman

!define MUI_PRODUCT "WikidPad"
!define MUI_VERSION "1.16"
!define DIST_DIR "..\dist\WikidPad"

!include "MUI.nsh"

;--------------------------------
;Configuration

  ;General
  OutFile "WikidPad.exe"

  ;Folder selection page
  InstallDir "$PROGRAMFILES\${MUI_PRODUCT}"
  
  ;Remember install folder
  InstallDirRegKey HKCU "Software\${MUI_PRODUCT}" ""

  ;Remember the Start Menu Folder
  !define MUI_STARTMENUPAGE_REGISTRY_ROOT "HKCU" 
  !define MUI_STARTMENUPAGE_REGISTRY_KEY "Software\${MUI_PRODUCT}" 
  !define MUI_STARTMENUPAGE_REGISTRY_VALUENAME "Start Menu Folder"
  !define TEMP $R0

;--------------------------------
;Modern UI Configuration

  !define MUI_LICENSEPAGE
  !define MUI_DIRECTORYPAGE  
  !define MUI_STARTMENUPAGE
  !define MUI_FINISHPAGE
    !define MUI_FINISHPAGE_RUN "$INSTDIR\WikidPad.exe"

  !define MUI_ABORTWARNING
  !define MUI_UNINSTALLER
  !define MUI_UNCONFIRMPAGE
  
;--------------------------------
;Languages
 
  !insertmacro MUI_LANGUAGE "English"

;--------------------------------
;Data
  
  LicenseData "..\license.txt"

;--------------------------------
;Installer Sections

Section "WikidPad.exe"

  SetOutPath "$INSTDIR"

	;Copy the files
  File /r "${DIST_DIR}\*.*"
  
  ;Store install folder
  WriteRegStr HKCU "Software\${MUI_PRODUCT}" "" $INSTDIR
  
  !insertmacro MUI_STARTMENU_WRITE_BEGIN
    
    ;Create shortcuts
    CreateDirectory "$SMPROGRAMS\${MUI_STARTMENUPAGE_VARIABLE}"
    CreateShortCut "$SMPROGRAMS\${MUI_STARTMENUPAGE_VARIABLE}\WikidPad.lnk" "$INSTDIR\WikidPad.exe"
    CreateShortCut "$SMPROGRAMS\${MUI_STARTMENUPAGE_VARIABLE}\Uninstall.lnk" "$INSTDIR\Uninstall.exe"

  !insertmacro MUI_STARTMENU_WRITE_END

  ;Associate .wiki with wikidPad
  WriteRegStr HKCR ".wiki" "" "wikidPadFile"
  ReadRegStr $0 HKCR "wikidPadFile" ""
  StrCmp $0 "" 0 skipOPTAssoc
	WriteRegStr HKCR "wikidPadFile" "" "wikidPad File"
	WriteRegStr HKCR "wikidPadFile\shell" "" "open"
	WriteRegStr HKCR "wikidPadFile\DefaultIcon" "" $INSTDIR\WikidPad.exe,0

  skipOPTAssoc:
  WriteRegStr HKCR "wikidPadFile\shell\open\command" "" \
    '"$INSTDIR\WikidPad.exe" "%1"'

  ReadRegStr $0 HKCR "wiki" ""
  StrCmp $0 "" 0 skipURLAssoc
	WriteRegStr HKCR "wiki" "" "URL:WikidPad Protocol"
	WriteRegStr HKCR "wiki" "URL Protocol" ""
	WriteRegStr HKCR "wiki\shell" "" "open"
	WriteRegStr HKCR "wiki\DefaultIcon" "" $INSTDIR\WikidPad.exe,0

  skipURLAssoc:
  WriteRegStr HKCR "wiki\shell\open\command" "" \
    '"$INSTDIR\WikidPad.exe" "%1"'


  ;Create uninstaller
  WriteUninstaller "$INSTDIR\Uninstall.exe"

SectionEnd

;Display the Finish header
;Insert this macro after the sections if you are not using a finish page
!insertmacro MUI_SECTIONS_FINISHHEADER

;--------------------------------
;Uninstaller Section

Section "Uninstall"

	Delete "$INSTDIR\license.txt"
	Delete "$INSTDIR\_socket.pyd"
	Delete "$INSTDIR\_sre.pyd"
	Delete "$INSTDIR\_winreg.pyd"
	Delete "$INSTDIR\stc_c.pyd"
	Delete "$INSTDIR\wxc.pyd"
	Delete "$INSTDIR\htmlc.pyd"
	Delete "$INSTDIR\_ssl.pyd"
	Delete "$INSTDIR\datetime.pyd"
	Delete "$INSTDIR\pyexpat.pyd"	

	Delete "$INSTDIR\_controls.pyd"	
	Delete "$INSTDIR\_core.pyd"	
	Delete "$INSTDIR\_gdi.pyd"	
	Delete "$INSTDIR\_html.pyd"	
	Delete "$INSTDIR\_misc.pyd"	
	Delete "$INSTDIR\_stc.pyd"	
	Delete "$INSTDIR\_windows.pyd"	
	Delete "$INSTDIR\wxbase251h_net_vc.dll"	
	Delete "$INSTDIR\wxbase251h_vc.dll"	
	Delete "$INSTDIR\wxmsw251h_adv_vc.dll"	
	Delete "$INSTDIR\wxmsw251h_core_vc.dll"	
	Delete "$INSTDIR\wxmsw251h_html_vc.dll"	
	Delete "$INSTDIR\wxmsw251h_stc_vc.dll"	

	Delete "$INSTDIR\export\wikistyle.css"
	Delete /REBOOTOK "$INSTDIR\python22.dll"
	Delete /REBOOTOK "$INSTDIR\python23.dll"
	Delete /REBOOTOK "$INSTDIR\wxmsw24h.dll"
	Delete /REBOOTOK "$INSTDIR\WikidPad.exe"

  RMDir /r "$INSTDIR\icons"
  RMDir /r "$INSTDIR\export"
  RMDir /r "$INSTDIR\lib"
  RMDir /r "$INSTDIR\extensions"
  RMDir /r "$INSTDIR\WikidPadHelp"

  ;Remove shortcut
  ReadRegStr ${TEMP} "${MUI_STARTMENUPAGE_REGISTRY_ROOT}" "${MUI_STARTMENUPAGE_REGISTRY_KEY}" "${MUI_STARTMENUPAGE_REGISTRY_VALUENAME}"
  
  StrCmp ${TEMP} "" noshortcuts
  
    Delete "$SMPROGRAMS\${TEMP}\WikidPad.lnk"
    Delete "$SMPROGRAMS\${TEMP}\Uninstall.lnk"
    RMDir "$SMPROGRAMS\${TEMP}" ;Only if empty, so it won't delete other shortcuts
    
  noshortcuts:

	Delete /REBOOTOK "$INSTDIR\Uninstall.exe"
  RMDir "$INSTDIR"

  DeleteRegKey HKCU "Software\${MUI_PRODUCT}"
  DeleteRegKey HKCR "wiki"
  DeleteRegKey HKCR ".wiki"
  DeleteRegKey HKCR "wikidPadFile"
  
  ;Display the Finish header
  !insertmacro MUI_UNFINISHHEADER

SectionEnd
