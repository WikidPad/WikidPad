import wx, wx.stc

NewWiki="Ctrl-N"
OpenWiki="Ctrl-Alt-O"
OpenWikiNewWindow=""
SearchWiki="Ctrl-Alt-F"
ViewBookmarks="Ctrl-Shift-B"
ShowTreeControl="Ctrl-T"
ShowToolbar="Ctrl-Shift-T"
ShowDocStructure=""
ShowTimeView=""
StayOnTop=""
OpenWikiWord="Ctrl-O"
Save="Ctrl-S"
Print="Ctrl-P"
OpenTrashcan=""
Rename="Ctrl-Alt-R"
Delete="Ctrl-D"
AddBookmark="Ctrl-Alt-B"
CatchClipboardAtPage=""
CatchClipboardAtCursor=""
CatchClipboardOff=""
ActivateLink="Ctrl-L"
ActivateLinkNewWindow=""
if wx.Platform == "__WXMSW__":
    ActivateLinkNewTab="Ctrl-Alt-L"
    ActivateLinkBackground="Ctrl-Shift-L"
else:
#elif wx.Platform == "__WXGTK__":
    # On Linux (at least with KDE) the above Windows' key bindings doesn't work
    #    "Ctrl-Alt-L"     creates character 0xFF (and is in KDE command interface)
    #    "Ctrl-Shift-L"   simply does nothing
    ActivateLinkNewTab="Alt-Shift-L"
    ActivateLinkBackground="Alt-Shift-Ctrl-L"
    # to test: What about Mac OSX?   wx.Platform == "__WXMAC__"

ViewParents="Ctrl-Up"
ViewParentless="Ctrl-Shift-Up"
ViewChildren="Ctrl-Down"
ViewHistory="Ctrl-H"
ClipboardCopyUrlToCurrentWikiword=""
AddVersion=""
TogglePageReadOnly=""
SetAsRoot="Ctrl-Shift-Q"
ResetRoot=""
UpHistory="Ctrl-Alt-Up"
DownHistory="Ctrl-Alt-Down"
GoBack="Alt-Left"
GoForward="Alt-Right"
GoUpwardFromSubpage=""
if wx.Platform == "__WXMAC__":
    GoHome="Ctrl-Shift-H"
    StartIncrementalSearch="Alt-Shift-F"
    FocusFastSearchField="Alt-Shift-S"
else:
    GoHome="Ctrl-Q"
    StartIncrementalSearch="Ctrl-F"
    FocusFastSearchField="Ctrl-Shift-F"
Bold="Ctrl-B"
Italic="Ctrl-I"
Heading="Ctrl-Alt-H"
SpellCheck=""
Cut="Ctrl-X"
Copy="Ctrl-C"
CopyToScratchPad="Ctrl-Alt-C"
Paste="Ctrl-V"
PasteRawHtml=""
SelectAll="Ctrl-A"
Undo="Ctrl-Z"
Redo="Ctrl-Y"
AddFileUrl=""
FindAndReplace="Ctrl-R"
ReplaceTextByWikiword="Ctrl-Shift-R"
ConvertAbsoluteRelativeFileUrl=""
RewrapText="Ctrl-W"
Eval="Ctrl-E"
InsertDate="Ctrl-Alt-D"
MakeWikiWord="Ctrl-J"

ShowFolding=""
ToggleCurrentFolding=""
UnfoldAll=""
FoldAll=""

ShowEditor="Ctrl-Shift-A"
ShowPreview="Ctrl-Shift-S"
ShowSwitchEditorPreview="Ctrl-Shift-Space"
#if wx.Platform == "__WXMAC__":
    # no good keybinding found that works on Mac
    # ShowSwitchEditorPreview="??????"

ZoomIn=""
ZoomOut=""
CloneWindow=""

ContinueSearch="F3"
BackwardSearch="Shift-F3"
if wx.Platform == "__WXMAC__":
    AutoComplete="Alt-Space"
else:
    AutoComplete="Ctrl-Space"
ActivateLink2="Ctrl-Return"
SwitchFocus="F6"
CloseCurrentTab="Ctrl-F4"
GoNextTab="Ctrl-Tab"
GoPreviousTab="Ctrl-Shift-Tab"

# Move selected logical line(s) one line up or down. "WithIndent" means that
# all lines below selection which are deeper indented than the last selected one
# are also selected and moved
LogLineUp=""
LogLineUpWithIndented=""
LogLineDown=""
LogLineDownWithIndented=""


Plugin_AutoNew_Numbered = "Ctrl-Shift-N"

Plugin_GraphVizStructure_ShowRelationGraph = ""
Plugin_GraphVizStructure_ShowRelationGraphSource = ""
Plugin_GraphVizStructure_ShowChildGraph = ""
Plugin_GraphVizStructure_ShowChildGraphSource = ""

