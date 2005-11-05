from wxPython.wx import *
from wxPython.stc import *

NewWiki="Ctrl-N"
OpenWiki="Ctrl-Alt-O"
SearchWiki="Ctrl-Alt-F"
ViewBookmarks="Ctrl-Shift-B"
ShowTreeControl="Ctrl-T"
OpenWikiWord="Ctrl-O"
Save="Ctrl-S"
Rename="Ctrl-Alt-R"
Delete="Ctrl-D"
AddBookmark="Ctrl-Alt-B"
ActivateLink="Ctrl-L"
ViewParents="Ctrl-Up"
ViewParentless="Ctrl-Shift-Up"
ViewChildren="Ctrl-Down"
ViewHistory="Ctrl-H"
UpHistory="Ctrl-Alt-Up"
DownHistory="Ctrl-Alt-Down"
GoBack="Ctrl-Alt-Left"
GoForward="Ctrl-Alt-Right"
Bold="Ctrl-B"
Italic="Ctrl-I"
Heading="Ctrl-Alt-H"
Cut="Ctrl-X"
Copy="Ctrl-C"
Paste="Ctrl-V"
CopyToScratchPad="Ctrl-Alt-C"
Undo="Ctrl-Z"
Redo="Ctrl-Y"
ZoomIn="Ctrl-+"
ZoomOut="Ctrl--"
FindAndReplace="Ctrl-R"
RewrapText="Ctrl-W"
Eval="Ctrl-E"
InsertDate="Ctrl-Alt-D"

def makeBold(editor):
    editor.styleSelection('*')

def makeItalic(editor):
    editor.styleSelection('_')

def addHeading(editor):
    pos = editor.GetCurrentPos()
    editor.CmdKeyExecute(wxSTC_CMD_HOME)
    editor.AddText('+')
    editor.GotoPos(pos)
