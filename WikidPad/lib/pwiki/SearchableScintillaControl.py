

## import hotshot
## _prof = hotshot.Profile("hotshot.prf")

import traceback, re

import wx, wx.stc

from . import SystemInfo

from . import wxHelper

from .EnhancedScintillaControl import EnhancedScintillaControl


# from wxHelper import GUI_ID, getTextFromClipboard, WindowUpdateLocker
# 
# import StringOps
# 

from . import WikiTxtDialogs



class SearchableScintillaControl(EnhancedScintillaControl):
    def __init__(self, presenter, mainControl, parent, ID):
        EnhancedScintillaControl.__init__(self, parent, ID)
        self.presenter = presenter
        self.mainControl = mainControl

        self.incSearchCharStartPos = -1
        self.searchStr = ""


    def getPresenter(self):
        return self.presenter
        
    def getMainControl(self):
        return self.mainControl

    def setSelectionForIncSearchByCharPos(self, start, end):
        """
        Called during incremental search to select text. Will be called with
        start=-1 if nothing is found to select.
        """
        if start == -1:
            self.SetSelection(self.GetSelectionStart(), self.GetSelectionStart())
        else:
            self.SetSelectionByCharPos(start, end)


    def OnKeyDown(self, evt):
        """
        wx.Event handler for key down.
        """
        accP = wxHelper.getAccelPairFromKeyDown(evt)
        matchesAccelPair = self.mainControl.keyBindings.matchesAccelPair

        if matchesAccelPair("ContinueSearch", accP):
            # ContinueSearch is normally F3
            self.startIncrementalSearch(self.searchStr)
            evt.Skip()

        elif matchesAccelPair("StartIncrementalSearch", accP):
            # Start incremental search
            # First get selected text and prepare it as default value
            text = self.GetSelectedText()
            text = text.split("\n", 1)[0]
            text = re.escape(text[:30])
            self.startIncrementalSearch(text)
        else:
            evt.Skip()


    def startIncrementalSearch(self, initSearch=None):
        sb = self.mainControl.GetStatusBar()
        self.incSearchCharStartPos = self.GetSelectionCharPos()[1]

        rect = sb.GetFieldRect(0)
        if SystemInfo.isOSX():
            # needed on Mac OSX to avoid cropped text
            rect = wx._core.Rect(rect.x, rect.y - 2, rect.width, rect.height + 4)

        rect.SetPosition(sb.ClientToScreen(rect.GetPosition()))

        dlg = WikiTxtDialogs.IncrementalSearchDialog(self, -1, self, rect,
                sb.GetFont(), self.mainControl, initSearch)
        dlg.Show()

    
    def executeIncrementalSearch(self, next=False):
        """
        Run incremental search, called only by IncrementalSearchDialog
        """
        text = self.GetText()
        if len(self.searchStr) > 0:
            if next:
                charStartPos = self.GetSelectionCharPos()[1]
            else:
                charStartPos = self.incSearchCharStartPos

            regex = None
            try:
                regex = re.compile(self.searchStr, re.IGNORECASE | \
                        re.MULTILINE | re.UNICODE)
            except:
                # Regex error
                return charStartPos   # ?

            match = regex.search(text, charStartPos, len(text))
            if not match and charStartPos > 0:
                match = regex.search(text, 0, charStartPos)

            if match:
                self.setSelectionForIncSearchByCharPos(
                        match.start(), match.end())

                return match.end()

        self.setSelectionForIncSearchByCharPos(-1, -1)
        self.GotoPos(self.bytelenSct(text[:self.incSearchCharStartPos]))

        return -1


    def executeIncrementalSearchBackward(self):
        """
        Run incremental search backwards, called only by IncrementalSearchDialog
        """
        text = self.GetText()
        if len(self.searchStr) > 0:
            charStartPos = self.GetSelectionCharPos()[0]

            regex = None
            try:
                regex = re.compile(self.searchStr, re.IGNORECASE | \
                        re.MULTILINE | re.UNICODE)
            except:
                # Regex error
                return charStartPos   # ?

            match = regex.search(text, 0, len(text))
            if match:
                if match.end() > charStartPos:
                    # First match already reached -> find last
                    while True:
                        matchNext = regex.search(text, match.end(), len(text))
                        if not matchNext:
                            break
                        match = matchNext
                        
                else:
                    while True:
                        matchNext = regex.search(text, match.end(), len(text))
                        if matchNext.end() > charStartPos:
                            break
                        match = matchNext

                self.setSelectionForIncSearchByCharPos(match.start(), match.end())

                return match.start()

        self.setSelectionForIncSearchByCharPos(-1, -1)
        self.GotoPos(self.bytelenSct(text[:self.incSearchCharStartPos]))

        return -1


    def forgetIncrementalSearch(self):
        """
        Called by IncrementalSearchDialog if user just leaves the inc. search
        field.
        """
        self.incSearchCharStartPos = -1

    def resetIncrementalSearch(self):
        """
        Called by IncrementalSearchDialog before aborting an inc. search.
        Called when search was explicitly aborted by user (with escape key)
        """
        self.setSelectionForIncSearchByCharPos(-1, -1)
        self.GotoPos(self.bytelenSct(self.GetText()[:self.incSearchCharStartPos]))
        self.incSearchCharStartPos = -1


    def endIncrementalSearch(self):
        """
        Called if incremental search ended successfully.
        """
        byteStart = self.GetSelectionStart()
        byteEnd = self.GetSelectionEnd()

        self.setSelectionForIncSearchByCharPos(-1, -1)
        
        self.SetSelection(byteStart, byteEnd)
        self.incSearchCharStartPos = -1


    def getContinuePosForSearch(self, sarOp):
        """
        Return the character position where to continue the given
        search operation sarOp. It always continues at beginning
        or end of current selection.
        
        If sarOp uses a regular expression, this function may throw
        a re.error exception.
        """
        range = self.GetSelectionCharPos()
        
#         if sarOp.matchesPart(self.GetSelectedText()) is not None:
        if sarOp.matchesPart(self.GetText(), range) is not None:
            # currently selected text matches search operation
            # -> continue searching at the end of selection
            return range[1]
        else:
            # currently selected text does not match search
            # -> continue searching at the beginning of selection
            return range[0]


    def executeSearch(self, sarOp, searchCharStartPos=-1, next=False):
        """
        Returns a tuple with a least two elements (<start>, <after end>)
        containing start and after end char positions of the found occurrence
        or (-1, -1) if not found.
        """
        if sarOp.booleanOp:
            return (-1, -1)  # Not possible

        if searchCharStartPos == -2:
            searchCharStartPos = self.getContinuePosForSearch(sarOp)

        text = self.GetText()
        if len(sarOp.searchStr) > 0:
            charStartPos = searchCharStartPos
            if next:
                charStartPos = len(self.GetTextRange(0, self.GetSelectionEnd()))
            try:
                found = sarOp.searchText(text, charStartPos)
                start, end = found[:2]
            except:
                # Regex error
                return (-1, -1)  # (self.anchorCharPosition, self.anchorCharPosition)
                
            if start is not None:
                self.showSelectionByCharPos(start, end)

                return found    # self.anchorCharPosition

        self.SetSelection(-1, -1)
        self.GotoPos(self.bytelenSct(text[:searchCharStartPos]))

        return (-1, -1)
        
        
    def executeReplace(self, sarOp):
        """
        Returns char position after replacement or -1 if replacement wasn't
        possible
        """
#         seltext = self.GetSelectedText()
        text = self.GetText()
#         found = sarOp.matchesPart(seltext)
        range = self.GetSelectionCharPos()
        
#         if sarOp.matchesPart(self.GetSelectedText()) is not None:
        found = sarOp.matchesPart(text, range)

        if found is None:
            return -1

        replacement = sarOp.replace(text, found)                    
        bytestart = self.GetSelectionStart()
        self.ReplaceSelection(replacement)
        selByteEnd = bytestart + self.bytelenSct(replacement)
        selCharEnd = len(self.GetTextRange(0, selByteEnd))

        return selCharEnd

