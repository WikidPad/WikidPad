

## import hotshot
## _prof = hotshot.Profile("hotshot.prf")

import traceback, codecs

import wx, wx.stc

from .wxHelper import GUI_ID, getTextFromClipboard, WindowUpdateLocker

from . import StringOps

from .SystemInfo import isOSX


def bytelenSct(us):
    """
    us -- unicode string
    returns: Number of bytes us requires in Scintilla (with UTF-8 encoding=Unicode)
    """
    return len(StringOps.utf8Enc(us)[0])



class StyleCollector(StringOps.SnippetCollector):
    """
    Helps to collect the style bytes needed to set the syntax coloring in
    Scintilla editor component
    """
    def __init__(self, defaultStyleNo, text, bytelenSct, startCharPos=0):   
        super(StyleCollector, self).__init__(b"")
        self.defaultStyleNo = defaultStyleNo
        self.text = text
        self.bytelenSct = bytelenSct
        self.charPos = startCharPos


    def bindStyle(self, targetCharPos, targetLength, styleNo):
        if targetCharPos < 0:
            return
        
        if targetCharPos < self.charPos:
            # Due to some unknown reason we had overlapping styles and
            # must remove some bytes
            bytestylelen = self.bytelenSct(self.text[targetCharPos:self.charPos])
            self.drop(bytestylelen)
        else:
            # There is possibly a gap between end of last style and current one
            # -> fill it with default style
            bytestylelen = self.bytelenSct(self.text[self.charPos:targetCharPos])
            self.append(bytes((self.defaultStyleNo,)) * bytestylelen)

        self.charPos = targetCharPos + targetLength
            
        bytestylelen = self.bytelenSct(self.text[targetCharPos:self.charPos])
        self.append(bytes((styleNo,)) * bytestylelen)

    def value(self):
        if self.charPos < len(self.text):
            bytestylelen = self.bytelenSct(self.text[self.charPos:len(self.text)])
            self.append(bytes((self.defaultStyleNo,)) * bytestylelen)

        return super(StyleCollector, self).value()





class EnhancedScintillaControl(wx.stc.StyledTextCtrl):
    def __init__(self, parent, ID):
        wx.stc.StyledTextCtrl.__init__(self, parent, ID, style=wx.WANTS_CHARS | wx.TE_PROCESS_ENTER)

        self._resetKeyBindings()

    bytelenSct = staticmethod(bytelenSct)

    def Cut(self):
        self.Copy()
        self.ReplaceSelection("")

    def Copy(self):
        raise NotImplementedError

    def Paste(self):
        # Text pasted?
        text = getTextFromClipboard()
        if text:
            self.ReplaceSelection(text)
            return True
        
        return False


    def _resetKeyBindings(self):
        
        self.CmdKeyClearAll()
        
        # Register general keyboard commands (minus some which may lead to problems
        for key, mod, action in _DEFAULT_STC_KEYS:
            self.CmdKeyAssign(key, mod, action)
            
        self.allowRectExtend(True)
        
        if isOSX():
            for key, mod, action in _MACOS_ADD_STC_KEYS:
                self.CmdKeyAssign(key, mod, action)

        # register some special keyboard commands
        self.CmdKeyAssign(ord('+'), wx.stc.STC_SCMOD_CTRL, wx.stc.STC_CMD_ZOOMIN)
        self.CmdKeyAssign(ord('-'), wx.stc.STC_SCMOD_CTRL, wx.stc.STC_CMD_ZOOMOUT)
        self.CmdKeyAssign(wx.stc.STC_KEY_HOME, wx.stc.STC_SCMOD_NORM,
                wx.stc.STC_CMD_HOMEWRAP)
        self.CmdKeyAssign(wx.stc.STC_KEY_END, wx.stc.STC_SCMOD_NORM,
                wx.stc.STC_CMD_LINEENDWRAP)
        self.CmdKeyAssign(wx.stc.STC_KEY_HOME, wx.stc.STC_SCMOD_SHIFT,
                wx.stc.STC_CMD_HOMEWRAPEXTEND)
        self.CmdKeyAssign(wx.stc.STC_KEY_END, wx.stc.STC_SCMOD_SHIFT,
                wx.stc.STC_CMD_LINEENDWRAPEXTEND)


    def allowRectExtend(self, allow=True):
        if allow:
            for key, mod, action in _RECT_EXTEND_STC_KEYS:
                self.CmdKeyAssign(key, mod, action)
        else:
            for key, mod, action in _RECT_EXTEND_STC_KEYS:
                self.CmdKeyClear(key, mod)


    def SetSelectionByCharPos(self, start, end):
        """
        Same as SetSelection(), but start and end are character positions
        not byte positions
        """
        text = self.GetText()
        bs = bytelenSct(text[:start])
        be = bs + bytelenSct(text[start:end])
        self.SetSelection(bs, be)


    def showSelectionByCharPos(self, start, end):
        """
        Same as SetSelectionByCharPos(), but scrolls to position correctly 
        """
        text = self.GetText()
        bs = bytelenSct(text[:start])
        be = bs + bytelenSct(text[start:end])

        with WindowUpdateLocker(self):
            self.SetSelection(-1, -1)
            self.GotoPos(self.GetLength())
            self.GotoPos(be)
            self.GotoPos(bs)
            self.SetSelection(bs, be)


    def getCharPosBySciPos(self, sciPos):
        """
        Get character position by the byte position returned by Scintilla's
        own methods
        """
        return len(self.GetTextRange(0, sciPos))


    def getSciPosByCharPos(self, charPos):
        """
        Get byte position returned by Scintilla's own methods by
        the character position
        """
        text = self.GetText()
        return bytelenSct(text[:charPos])
                

    def GetSelectionCharPos(self):
        """
        Same as GetSelection(), but returned (start, end) are character positions
        not byte positions
        """
        start, end = self.GetSelection()
        cs = len(self.GetTextRange(0, start))
        ce = cs + len(self.GetTextRange(start, end))
        return (cs, ce)


    def gotoCharPos(self, pos, scroll=True):
        # Go to the end and back again, so the anchor is
        # near the top
        sctPos = bytelenSct(self.GetText()[:pos])
        if scroll:
            self.SetSelection(-1, -1)
            self.GotoPos(self.GetLength())
            self.GotoPos(sctPos)
        else:
            self.SetSelectionStart(sctPos)
            self.SetSelectionEnd(sctPos)

        # self.SetSelectionByCharPos(pos, pos)


    def scrollXY(self, scrollPosX, scrollPosY):
        """
        Set scroll bars according to given pixel positions
        """
        
        # Bad hack: First scroll to position to avoid a visible jump
        #   if scrolling works, then update display,
        #   then scroll again because it may have failed the first time
        
        self.SetScrollPos(wx.HORIZONTAL, scrollPosX, False)
        screvt = wx.ScrollWinEvent(wx.wxEVT_SCROLLWIN_THUMBTRACK,
                scrollPosX, wx.HORIZONTAL)
        self.ProcessEvent(screvt)
        screvt = wx.ScrollWinEvent(wx.wxEVT_SCROLLWIN_THUMBRELEASE,
                scrollPosX, wx.HORIZONTAL)
        self.ProcessEvent(screvt)
        
        self.SetScrollPos(wx.VERTICAL, scrollPosY, True)
        screvt = wx.ScrollWinEvent(wx.wxEVT_SCROLLWIN_THUMBTRACK,
                scrollPosY, wx.VERTICAL)
        self.ProcessEvent(screvt)
        screvt = wx.ScrollWinEvent(wx.wxEVT_SCROLLWIN_THUMBRELEASE,
                scrollPosY, wx.VERTICAL)
        self.ProcessEvent(screvt)

        self.Update()

        self.SetScrollPos(wx.HORIZONTAL, scrollPosX, False)
        screvt = wx.ScrollWinEvent(wx.wxEVT_SCROLLWIN_THUMBTRACK,
                scrollPosX, wx.HORIZONTAL)
        self.ProcessEvent(screvt)
        screvt = wx.ScrollWinEvent(wx.wxEVT_SCROLLWIN_THUMBRELEASE,
                scrollPosX, wx.HORIZONTAL)
        self.ProcessEvent(screvt)
        
        self.SetScrollPos(wx.VERTICAL, scrollPosY, True)
        screvt = wx.ScrollWinEvent(wx.wxEVT_SCROLLWIN_THUMBTRACK,
                scrollPosY, wx.VERTICAL)
        self.ProcessEvent(screvt)
        screvt = wx.ScrollWinEvent(wx.wxEVT_SCROLLWIN_THUMBRELEASE,
                scrollPosY, wx.VERTICAL)
        self.ProcessEvent(screvt)








# Default mapping based on Scintilla's "KeyMap.cxx" file
_DEFAULT_STC_KEYS = (
        (wx.stc.STC_KEY_DOWN,        wx.stc.STC_SCMOD_NORM,    wx.stc.STC_CMD_LINEDOWN),
        (wx.stc.STC_KEY_DOWN,        wx.stc.STC_SCMOD_SHIFT,    wx.stc.STC_CMD_LINEDOWNEXTEND),
        (wx.stc.STC_KEY_DOWN,        wx.stc.STC_SCMOD_CTRL,    wx.stc.STC_CMD_LINESCROLLDOWN),
        (wx.stc.STC_KEY_UP,        wx.stc.STC_SCMOD_NORM,    wx.stc.STC_CMD_LINEUP),
        (wx.stc.STC_KEY_UP,            wx.stc.STC_SCMOD_SHIFT,    wx.stc.STC_CMD_LINEUPEXTEND),
        (wx.stc.STC_KEY_UP,            wx.stc.STC_SCMOD_CTRL,    wx.stc.STC_CMD_LINESCROLLUP),
#         (ord('['),            wx.stc.STC_SCMOD_CTRL,        wx.stc.STC_CMD_PARAUP),
#         (ord('['),            wx.stc.STC_SCMOD_SHIFT | wx.stc.STC_SCMOD_CTRL,    wx.stc.STC_CMD_PARAUPEXTEND),
#         (ord(']'),            wx.stc.STC_SCMOD_CTRL,        wx.stc.STC_CMD_PARADOWN),
#         (ord(']'),            wx.stc.STC_SCMOD_SHIFT | wx.stc.STC_SCMOD_CTRL,    wx.stc.STC_CMD_PARADOWNEXTEND),
        (wx.stc.STC_KEY_LEFT,        wx.stc.STC_SCMOD_NORM,    wx.stc.STC_CMD_CHARLEFT),
        (wx.stc.STC_KEY_LEFT,        wx.stc.STC_SCMOD_SHIFT,    wx.stc.STC_CMD_CHARLEFTEXTEND),
        (wx.stc.STC_KEY_LEFT,        wx.stc.STC_SCMOD_CTRL,    wx.stc.STC_CMD_WORDLEFT),
        (wx.stc.STC_KEY_LEFT,        wx.stc.STC_SCMOD_SHIFT | wx.stc.STC_SCMOD_CTRL,    wx.stc.STC_CMD_WORDLEFTEXTEND),
        (wx.stc.STC_KEY_RIGHT,        wx.stc.STC_SCMOD_NORM,    wx.stc.STC_CMD_CHARRIGHT),
        (wx.stc.STC_KEY_RIGHT,        wx.stc.STC_SCMOD_SHIFT,    wx.stc.STC_CMD_CHARRIGHTEXTEND),
        (wx.stc.STC_KEY_RIGHT,        wx.stc.STC_SCMOD_CTRL,    wx.stc.STC_CMD_WORDRIGHT),
        (wx.stc.STC_KEY_RIGHT,        wx.stc.STC_SCMOD_SHIFT | wx.stc.STC_SCMOD_CTRL,    wx.stc.STC_CMD_WORDRIGHTEXTEND),
#         (ord('/'),        wx.stc.STC_SCMOD_CTRL,        wx.stc.STC_CMD_WORDPARTLEFT),
#         (ord('/'),        wx.stc.STC_SCMOD_SHIFT | wx.stc.STC_SCMOD_CTRL,    wx.stc.STC_CMD_WORDPARTLEFTEXTEND),
#         (ord('\\'),        wx.stc.STC_SCMOD_CTRL,        wx.stc.STC_CMD_WORDPARTRIGHT),
#         (ord('\\'),        wx.stc.STC_SCMOD_SHIFT | wx.stc.STC_SCMOD_CTRL,    wx.stc.STC_CMD_WORDPARTRIGHTEXTEND),
        (wx.stc.STC_KEY_HOME,        wx.stc.STC_SCMOD_NORM,    wx.stc.STC_CMD_VCHOME),
        (wx.stc.STC_KEY_HOME,         wx.stc.STC_SCMOD_SHIFT,     wx.stc.STC_CMD_VCHOMEEXTEND),
        (wx.stc.STC_KEY_HOME,         wx.stc.STC_SCMOD_CTRL,     wx.stc.STC_CMD_DOCUMENTSTART),
        (wx.stc.STC_KEY_HOME,         wx.stc.STC_SCMOD_SHIFT | wx.stc.STC_SCMOD_CTRL,     wx.stc.STC_CMD_DOCUMENTSTARTEXTEND),
        (wx.stc.STC_KEY_HOME,         wx.stc.STC_SCMOD_ALT,     wx.stc.STC_CMD_HOMEDISPLAY),
        (wx.stc.STC_KEY_END,         wx.stc.STC_SCMOD_NORM,    wx.stc.STC_CMD_LINEEND),
        (wx.stc.STC_KEY_END,         wx.stc.STC_SCMOD_SHIFT,     wx.stc.STC_CMD_LINEENDEXTEND),
        (wx.stc.STC_KEY_END,         wx.stc.STC_SCMOD_CTRL,     wx.stc.STC_CMD_DOCUMENTEND),
        (wx.stc.STC_KEY_END,         wx.stc.STC_SCMOD_SHIFT | wx.stc.STC_SCMOD_CTRL,     wx.stc.STC_CMD_DOCUMENTENDEXTEND),
        (wx.stc.STC_KEY_END,         wx.stc.STC_SCMOD_ALT,     wx.stc.STC_CMD_LINEENDDISPLAY),
        (wx.stc.STC_KEY_PRIOR,        wx.stc.STC_SCMOD_NORM,    wx.stc.STC_CMD_PAGEUP),
        (wx.stc.STC_KEY_PRIOR,        wx.stc.STC_SCMOD_SHIFT,     wx.stc.STC_CMD_PAGEUPEXTEND),
        (wx.stc.STC_KEY_NEXT,         wx.stc.STC_SCMOD_NORM,     wx.stc.STC_CMD_PAGEDOWN),
        (wx.stc.STC_KEY_NEXT,         wx.stc.STC_SCMOD_SHIFT,     wx.stc.STC_CMD_PAGEDOWNEXTEND),
        (wx.stc.STC_KEY_DELETE,     wx.stc.STC_SCMOD_NORM,    wx.stc.STC_CMD_CLEAR),
        (wx.stc.STC_KEY_DELETE,     wx.stc.STC_SCMOD_CTRL,    wx.stc.STC_CMD_DELWORDRIGHT),
        (wx.stc.STC_KEY_DELETE,    wx.stc.STC_SCMOD_SHIFT | wx.stc.STC_SCMOD_CTRL,    wx.stc.STC_CMD_DELLINERIGHT),
        (wx.stc.STC_KEY_INSERT,         wx.stc.STC_SCMOD_NORM,    wx.stc.STC_CMD_EDITTOGGLEOVERTYPE),
        (wx.stc.STC_KEY_ESCAPE,      wx.stc.STC_SCMOD_NORM,    wx.stc.STC_CMD_CANCEL),
        (wx.stc.STC_KEY_BACK,        wx.stc.STC_SCMOD_NORM,     wx.stc.STC_CMD_DELETEBACK),
        (wx.stc.STC_KEY_BACK,        wx.stc.STC_SCMOD_SHIFT,     wx.stc.STC_CMD_DELETEBACK),
        (wx.stc.STC_KEY_BACK,        wx.stc.STC_SCMOD_CTRL,     wx.stc.STC_CMD_DELWORDLEFT),
        (wx.stc.STC_KEY_BACK,         wx.stc.STC_SCMOD_ALT,    wx.stc.STC_CMD_UNDO),
        (wx.stc.STC_KEY_BACK,        wx.stc.STC_SCMOD_SHIFT | wx.stc.STC_SCMOD_CTRL,    wx.stc.STC_CMD_DELLINELEFT),
        (ord('Z'),             wx.stc.STC_SCMOD_CTRL,    wx.stc.STC_CMD_UNDO),
        (ord('Y'),             wx.stc.STC_SCMOD_CTRL,    wx.stc.STC_CMD_REDO),
        (ord('A'),             wx.stc.STC_SCMOD_CTRL,    wx.stc.STC_CMD_SELECTALL),
        (wx.stc.STC_KEY_TAB,        wx.stc.STC_SCMOD_NORM,    wx.stc.STC_CMD_TAB),
        (wx.stc.STC_KEY_TAB,        wx.stc.STC_SCMOD_SHIFT,    wx.stc.STC_CMD_BACKTAB),
        (wx.stc.STC_KEY_RETURN,     wx.stc.STC_SCMOD_NORM,    wx.stc.STC_CMD_NEWLINE),
        (wx.stc.STC_KEY_RETURN,     wx.stc.STC_SCMOD_SHIFT,    wx.stc.STC_CMD_NEWLINE),
        (wx.stc.STC_KEY_ADD,         wx.stc.STC_SCMOD_CTRL,    wx.stc.STC_CMD_ZOOMIN),
        (wx.stc.STC_KEY_SUBTRACT,    wx.stc.STC_SCMOD_CTRL,    wx.stc.STC_CMD_ZOOMOUT),
#         (wx.stc.STC_KEY_DIVIDE,    wx.stc.STC_SCMOD_CTRL,    wx.stc.STC_CMD_SETZOOM),
#         (ord('L'),             wx.stc.STC_SCMOD_CTRL,    wx.stc.STC_CMD_LINECUT),
#         (ord('L'),             wx.stc.STC_SCMOD_SHIFT | wx.stc.STC_SCMOD_CTRL,    wx.stc.STC_CMD_LINEDELETE),
#         (ord('T'),             wx.stc.STC_SCMOD_SHIFT | wx.stc.STC_SCMOD_CTRL,    wx.stc.STC_CMD_LINECOPY),
#         (ord('T'),             wx.stc.STC_SCMOD_CTRL,    wx.stc.STC_CMD_LINETRANSPOSE),
#         (ord('D'),             wx.stc.STC_SCMOD_CTRL,    wx.stc.STC_CMD_SELECTIONDUPLICATE),
#         (ord('U'),             wx.stc.STC_SCMOD_CTRL,    wx.stc.STC_CMD_LOWERCASE),
#         (ord('U'),             wx.stc.STC_SCMOD_SHIFT | wx.stc.STC_SCMOD_CTRL,    wx.stc.STC_CMD_UPPERCASE),
    )


_RECT_EXTEND_STC_KEYS = (
        (wx.stc.STC_KEY_DOWN,        wx.stc.STC_SCMOD_SHIFT | wx.stc.STC_SCMOD_ALT,    wx.stc.STC_CMD_LINEDOWNRECTEXTEND),
        (wx.stc.STC_KEY_UP,        wx.stc.STC_SCMOD_SHIFT | wx.stc.STC_SCMOD_ALT,    wx.stc.STC_CMD_LINEUPRECTEXTEND),
        (wx.stc.STC_KEY_LEFT,        wx.stc.STC_SCMOD_SHIFT | wx.stc.STC_SCMOD_ALT,    wx.stc.STC_CMD_CHARLEFTRECTEXTEND),
        (wx.stc.STC_KEY_RIGHT,        wx.stc.STC_SCMOD_SHIFT | wx.stc.STC_SCMOD_ALT,    wx.stc.STC_CMD_CHARRIGHTRECTEXTEND),
        (wx.stc.STC_KEY_HOME,        wx.stc.STC_SCMOD_SHIFT | wx.stc.STC_SCMOD_ALT,    wx.stc.STC_CMD_VCHOMERECTEXTEND),
        (wx.stc.STC_KEY_END,        wx.stc.STC_SCMOD_SHIFT | wx.stc.STC_SCMOD_ALT,    wx.stc.STC_CMD_LINEENDRECTEXTEND),
        (wx.stc.STC_KEY_PRIOR,        wx.stc.STC_SCMOD_SHIFT | wx.stc.STC_SCMOD_ALT,    wx.stc.STC_CMD_PAGEUPRECTEXTEND),
        (wx.stc.STC_KEY_NEXT,        wx.stc.STC_SCMOD_SHIFT | wx.stc.STC_SCMOD_ALT,    wx.stc.STC_CMD_PAGEDOWNRECTEXTEND),
    )


_MACOS_ADD_STC_KEYS = (
        (ord('B'), wx.stc.STC_SCMOD_CTRL, wx.stc.STC_CMD_CHARLEFT),
        (ord('F'), wx.stc.STC_SCMOD_CTRL, wx.stc.STC_CMD_CHARRIGHT),
        (ord('P'), wx.stc.STC_SCMOD_CTRL, wx.stc.STC_CMD_LINEUP),
        (ord('N'), wx.stc.STC_SCMOD_CTRL, wx.stc.STC_CMD_LINEDOWN),
        (ord('A'), wx.stc.STC_SCMOD_CTRL, wx.stc.STC_CMD_HOMEDISPLAY),
        (ord('E'), wx.stc.STC_SCMOD_CTRL, wx.stc.STC_CMD_LINEENDDISPLAY),
        (ord('J'), wx.stc.STC_SCMOD_CTRL, wx.stc.STC_CMD_NEWLINE),
        (ord('H'), wx.stc.STC_SCMOD_CTRL, wx.stc.STC_CMD_DELETEBACK),
        (ord('U'), wx.stc.STC_SCMOD_CTRL, wx.stc.STC_CMD_DELLINELEFT),
        (ord('K'), wx.stc.STC_SCMOD_CTRL, wx.stc.STC_CMD_DELLINERIGHT),
        (ord('D'), wx.stc.STC_SCMOD_CTRL, wx.stc.STC_CMD_CLEAR),
    )
