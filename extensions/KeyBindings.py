from wxPython.wx import *
from wxPython.stc import *

NewWiki="Ctrl-N"
OpenWiki="Ctrl-Alt-O"
OpenWikiNewWindow=""
SearchWiki="Ctrl-Alt-F"
ViewBookmarks="Ctrl-Shift-B"
ShowTreeControl="Ctrl-T"
ShowToolbar="Ctrl-Shift-T"
StayOnTop=""
OpenWikiWord="Ctrl-O"
Save="Ctrl-S"
Print="Ctrl-P"
Rename="Ctrl-Alt-R"
Delete="Ctrl-D"
AddBookmark="Ctrl-Alt-B"
CatchClipboardAtPage=""
CatchClipboardAtCursor=""
CatchClipboardOff=""
ActivateLink="Ctrl-L"
ViewParents="Ctrl-Up"
ViewParentless="Ctrl-Shift-Up"
ViewChildren="Ctrl-Down"
ViewHistory="Ctrl-H"
SetAsRoot="Ctrl-Shift-Q"
UpHistory="Ctrl-Alt-Up"
DownHistory="Ctrl-Alt-Down"
GoBack="Alt-Left"
GoForward="Alt-Right"
GoHome="Ctrl-Q"
Bold="Ctrl-B"
Italic="Ctrl-I"
Heading="Ctrl-Alt-H"
SpellCheck=""
Cut="Ctrl-X"
Copy="Ctrl-C"
CopyToScratchPad="Ctrl-Alt-C"
Paste="Ctrl-V"
Undo="Ctrl-Z"
Redo="Ctrl-Y"
AddFileUrl=""
FindAndReplace="Ctrl-R"
ReplaceTextByWikiword="Ctrl-Shift-R"
RewrapText="Ctrl-W"
Eval="Ctrl-E"
InsertDate="Ctrl-Alt-D"
MakeWikiWord="Ctrl-J"
ZoomIn=""
ZoomOut=""
CloneWindow=""

ContinueSearch="F3"
BackwardSearch="Shift-F3"
AutoComplete="Ctrl-Space"
ActivateLink2="Ctrl-Return"
SwitchFocus="F6"
StartIncrementalSearch="Ctrl-F"

# IncrementalSearchCtrl="F"   # Hack, changing not recommended


def makeBold(editor):
    editor.styleSelection(u'*')

def makeItalic(editor):
    editor.styleSelection(u'_')

def addHeading(editor):
    bytePos = editor.PositionAfter(editor.GetCurrentPos())
    editor.CmdKeyExecute(wxSTC_CMD_HOME)
    editor.AddText(u'+')
    editor.GotoPos(bytePos)

def makeWikiWord(editor):
    text = editor.GetSelectedText()
    text = text.replace(u"'", u"")
    text = text[0:1].upper() + text[1:]
    text = u"[" + text + u"]"
    editor.ReplaceSelection(text)
