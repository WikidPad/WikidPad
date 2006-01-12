from wxPython.wx import *
from wxPython.stc import *

NewWiki="Ctrl-N"
OpenWiki="Ctrl-Alt-O"
SearchWiki="Ctrl-Alt-F"
ViewBookmarks="Ctrl-Shift-B"
ShowTreeControl="Ctrl-T"
OpenWikiWord="Ctrl-O"
Save="Ctrl-S"
Print="Ctrl-P"
Rename="Ctrl-Alt-R"
Delete="Ctrl-D"
AddBookmark="Ctrl-Alt-B"
ActivateLink="Ctrl-L"
ViewParents="Ctrl-Up"
ViewParentless="Ctrl-Shift-Up"
ViewChildren="Ctrl-Down"
ViewHistory="Ctrl-H"
SetAsRoot="Ctrl-Shift-Q"
UpHistory="Ctrl-Alt-Up"
DownHistory="Ctrl-Alt-Down"
GoBack="Ctrl-Alt-Left"
GoForward="Ctrl-Alt-Right"
GoHome="Ctrl-Q"
Bold="Ctrl-B"
Italic="Ctrl-I"
Heading="Ctrl-Alt-H"
Cut="Ctrl-X"
Copy="Ctrl-C"
Paste="Ctrl-V"
CopyToScratchPad="Ctrl-Alt-C"
Undo="Ctrl-Z"
Redo="Ctrl-Y"
ZoomIn=""
ZoomOut=""
FindAndReplace="Ctrl-R"
ReplaceTextByWikiword="Ctrl-Shift-R"
RewrapText="Ctrl-W"
Eval="Ctrl-E"
InsertDate="Ctrl-Alt-D"
MakeWikiWord="Ctrl-J"

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
