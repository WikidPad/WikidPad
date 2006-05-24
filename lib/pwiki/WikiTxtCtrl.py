import os, traceback, codecs, array
from cStringIO import StringIO
import urllib_red as urllib
import string
import srePersistent as re
import threading

from os.path import exists, dirname

from time import time, strftime, sleep
from textwrap import fill

from wxPython.wx import *
from wxPython.stc import *
import wxPython.xrc as xrc

from Utilities import *

from wxHelper import GUI_ID, getTextFromClipboard, copyTextToClipboard, \
        wxKeyFunctionSink
from MiscEvent import KeyFunctionSink

import WikiFormatting
import PageAst, DocPages
from WikiExceptions import WikiWordNotFoundException, WikiFileNotFoundException

from SearchAndReplace import SearchReplaceOperation
from StringOps import *
# utf8Enc, utf8Dec, mbcsEnc, mbcsDec, uniToGui, guiToUni, \
#        Tokenizer, wikiWordToLabel, revStr, lineendToInternal, lineendToOs

from Configuration import isUnicode




def bytelenSct_utf8(us):
    """
    us -- unicode string
    returns: Number of bytes us requires in Scintilla (with UTF-8 encoding=Unicode)
    """
    return len(utf8Enc(us)[0])


def bytelenSct_mbcs(us):
    """
    us -- unicode string
    returns: Number of bytes us requires in Scintilla (with mbcs encoding=Ansi)
    """
    return len(mbcsEnc(us)[0])



class WikiTxtCtrl(wxStyledTextCtrl):
    def __init__(self, pWiki, parent, ID):
        wxStyledTextCtrl.__init__(self, parent, ID)
        self.pWiki = pWiki
        self.evalScope = None
        self.stylebytes = None
        self.stylingThreadHolder = ThreadHolder()
        self.loadedDocPage = None
        self.lastCursorPositionInPage = {}   # TODO Clear caches when loading new wiki
        self.scrollPosCache = {}
        self.lastFont = None
        self.pageType = "normal"   # The pagetype controls some special editor behaviour
#         self.idleCounter = 0       # Used to reduce idle load
        
        # If autocompletion word was choosen, how many bytes to delete backward
        # before inserting word, if word ...
        self.autoCompBackBytesWithoutBracket = 0  # doesn't start with '['
        self.autoCompBackBytesWithBracket = 0     # starts with '['

        # editor settings
        self.SetIndent(4)
        self.SetTabIndents(True)
        self.SetBackSpaceUnIndents(True)
        self.SetTabWidth(4)
        self.SetUseTabs(0)  # TODO Configurable
        self.SetEOLMode(wxSTC_EOL_LF)
        self.AutoCompSetFillUps(u":=")  # TODO Add '.'?
#         self.SetYCaretPolicy(wxSTC_CARET_SLOP, 2)  
#         self.SetYCaretPolicy(wxSTC_CARET_JUMPS | wxSTC_CARET_EVEN, 4)  
        self.SetYCaretPolicy(wxSTC_CARET_SLOP | wxSTC_CARET_EVEN, 4)  

        
        # configurable editor settings
        config = self.pWiki.getConfig()
        self.setWrapMode(config.getboolean("main", "wrap_mode"))
        self.SetIndentationGuides(config.getboolean("main", "indentation_guides"))
        self.autoIndent = config.getboolean("main", "auto_indent")
        self.autoBullets = config.getboolean("main", "auto_bullets")


        # Self-modify to ansi/unicode version
        if isUnicode():
            self.bytelenSct = bytelenSct_utf8
        else:
            self.bytelenSct = bytelenSct_mbcs
            
            self.GetText = self.GetText_unicode
            self.GetTextRange = self.GetTextRange_unicode
            self.GetSelectedText = self.GetSelectedText_unicode
            self.GetLine = self.GetLine_unicode
            self.ReplaceSelection = self.ReplaceSelection_unicode
            self.AddText = self.AddText_unicode


        # Popup menu must be created by Python code to replace clipboard functions
        # for unicode build
        self.UsePopUp(0)

        self.StyleSetSpec(wxSTC_STYLE_DEFAULT, "face:%(mono)s,size:%(size)d" %
                self.pWiki.presentationExt.faces)

        for i in xrange(32):
            self.StyleSetEOLFilled(i, True)

        # i plan on lexing myself
        self.SetLexer(wxSTC_LEX_CONTAINER)
        
        # make the text control a drop target for files and text
        self.SetDropTarget(WikiTxtCtrlDropTarget(self))

        # register some keyboard commands
        self.CmdKeyAssign(ord('+'), wxSTC_SCMOD_CTRL, wxSTC_CMD_ZOOMIN)
        self.CmdKeyAssign(ord('-'), wxSTC_SCMOD_CTRL, wxSTC_CMD_ZOOMOUT)
        self.CmdKeyAssign(wxSTC_KEY_HOME, 0, wxSTC_CMD_HOMEWRAP)
        self.CmdKeyAssign(wxSTC_KEY_END, 0, wxSTC_CMD_LINEENDWRAP)
        self.CmdKeyAssign(wxSTC_KEY_HOME, wxSTC_SCMOD_SHIFT,
                wxSTC_CMD_HOMEWRAPEXTEND)
        self.CmdKeyAssign(wxSTC_KEY_END, wxSTC_SCMOD_SHIFT,
                wxSTC_CMD_LINEENDWRAPEXTEND)


        # Clear all key mappings for clipboard operations
        # PersonalWikiFrame handles them and calls the special clipboard functions
        # instead of the normal ones
        self.CmdKeyClear(wxSTC_KEY_INSERT, wxSTC_SCMOD_CTRL)
        self.CmdKeyClear(wxSTC_KEY_INSERT, wxSTC_SCMOD_SHIFT)
        self.CmdKeyClear(wxSTC_KEY_DELETE, wxSTC_SCMOD_SHIFT)

        self.CmdKeyClear(ord('X'), wxSTC_SCMOD_CTRL)
        self.CmdKeyClear(ord('C'), wxSTC_SCMOD_CTRL)
        self.CmdKeyClear(ord('V'), wxSTC_SCMOD_CTRL)

        # set the autocomplete separator
        self.AutoCompSetSeparator(ord('~'))

        # register some event handlers
        wxKeyFunctionSink(self.pWiki.getMiscEvent(), self, (
                ("options changed", self.onOptionsChanged),  # fired by PersonalWikiFrame
                ("command copy", self.onCmdCopy)
        ))

        self.wikiPageListener = KeyFunctionSink((
                ("wiki page updated", self.onWikiPageUpdated),   # fired by a WikiPage
        ))


        EVT_STC_STYLENEEDED(self, ID, self.OnStyleNeeded)
        EVT_STC_CHARADDED(self, ID, self.OnCharAdded)
        EVT_STC_CHANGE(self, ID, self.OnChange)
        EVT_STC_USERLISTSELECTION(self, ID, self.OnUserListSelection)
        
        EVT_LEFT_DOWN(self, self.OnClick)
        EVT_LEFT_DCLICK(self, self.OnDoubleClick)
        EVT_MOTION(self, self.OnMouseMove)
        # EVT_STC_DOUBLECLICK(self, ID, self.OnDoubleClick)
        EVT_KEY_DOWN(self, self.OnKeyDown)
        EVT_CHAR(self, self.OnChar)
        EVT_SET_FOCUS(self, self.OnSetFocus)
        
        EVT_IDLE(self, self.OnIdle)
        EVT_CONTEXT_MENU(self, self.OnContextMenu)

        # search related vars
        self.inIncrementalSearch = False
        self.anchorBytePosition = -1
        self.anchorCharPosition = -1
        self.searchCharStartPos = 0

#         # are WikiWords enabled
#         self.wikiWordsEnabled = True
        
        self.onOptionsChanged(None)

        # when was a key pressed last. used to check idle time.
        self.lastKeyPressed = time()
        self.eolMode = self.GetEOLMode()

        # Stock cursors. Created here because the App object must be created first
        WikiTxtCtrl.CURSOR_IBEAM = wxStockCursor(wxCURSOR_IBEAM)
        WikiTxtCtrl.CURSOR_HAND = wxStockCursor(wxCURSOR_HAND)

        res = xrc.wxXmlResource.Get()
        self.contextMenu = res.LoadMenu("MenuTextctrlPopup")
        
        # Connect context menu events to functions
        EVT_MENU(self, GUI_ID.CMD_UNDO, lambda evt: self.Undo())
        EVT_MENU(self, GUI_ID.CMD_REDO, lambda evt: self.Redo())

        EVT_MENU(self, GUI_ID.CMD_CLIPBOARD_CUT, lambda evt: self.Cut())
        EVT_MENU(self, GUI_ID.CMD_CLIPBOARD_COPY, lambda evt: self.Copy())
        EVT_MENU(self, GUI_ID.CMD_CLIPBOARD_PASTE, lambda evt: self.Paste())
        EVT_MENU(self, GUI_ID.CMD_TEXT_DELETE, lambda evt: self.ReplaceSelection(""))

        EVT_MENU(self, GUI_ID.CMD_TEXT_SELECT_ALL, lambda evt: self.SelectAll())

    def getLoadedDocPage(self):
        return self.loadedDocPage

    def Cut(self):
        self.Copy()
        self.ReplaceSelection("")

    def Copy(self):
        copyTextToClipboard(self.GetSelectedText())

    def Paste(self):
        text = getTextFromClipboard()
        if text is None:
            return

        self.ReplaceSelection(text)

    def onCmdCopy(self, miscevt):
        if wxWindow.FindFocus() != self:
            return
        self.Copy()


    def setWrapMode(self, onOrOff):
        if onOrOff:
            self.SetWrapMode(wxSTC_WRAP_WORD)
        else:
            self.SetWrapMode(wxSTC_WRAP_NONE)

    def getWrapMode(self):
        return self.GetWrapMode() == wxSTC_WRAP_WORD

    def setAutoIndent(self, onOff):
        self.autoIndent = onOff
        
    def getAutoIndent(self):
        return self.autoIndent

    def setAutoBullets(self, onOff):
        self.autoBullets = onOff
        
    def getAutoBullets(self):
        return self.autoBullets


    def SetStyles(self, styleFaces = None):
        # create the styles
        if styleFaces is None:
            styleFaces = self.pWiki.presentationExt.faces
            
        config = self.pWiki.getConfig()
        for type, style in WikiFormatting.getStyles(styleFaces, config):
            self.StyleSetSpec(type, style)

    def SetText(self, text):
        """
        Overrides the wxStyledTextCtrl method.
        text -- Unicode text content to set
        """
        self.inIncrementalSearch = False
        self.anchorBytePosition = -1
        self.anchorCharPosition = -1
        self.searchCharStartPos = 0
        self.stylebytes = None
        self.pageAst = None
        self.pageType = "normal"

        self.SetSelection(-1, -1)
        self.ignoreOnChange = True
        if isUnicode():
            wxStyledTextCtrl.SetText(self, text)
        else:
            wxStyledTextCtrl.SetText(self, mbcsEnc(text, "replace")[0])
        self.ignoreOnChange = False
        self.EmptyUndoBuffer()


    def replaceText(self, text):
        if isUnicode():
            wxStyledTextCtrl.SetText(self, text)
        else:
            wxStyledTextCtrl.SetText(self, mbcsEnc(text, "replace")[0])


    def GetText_unicode(self):
        """
        Overrides the wxStyledTextCtrl.GetText method in ansi mode
        to return unicode.
        """
        return mbcsDec(wxStyledTextCtrl.GetText(self), "replace")[0]

    
    def GetTextRange_unicode(self, startPos, endPos):
        """
        Overrides the wxStyledTextCtrl.GetTextRange method in ansi mode
        to return unicode.
        startPos and endPos are byte(!) positions into the editor buffer
        """
        return mbcsDec(wxStyledTextCtrl.GetTextRange(self, startPos, endPos),
                "replace")[0]


    def GetSelectedText_unicode(self):
        """
        Overrides the wxStyledTextCtrl.GetSelectedText method in ansi mode
        to return unicode.
        """
        return mbcsDec(wxStyledTextCtrl.GetSelectedText(self), "replace")[0]


    def GetLine_unicode(self, line):
        return mbcsDec(wxStyledTextCtrl.GetLine(self, line), "replace")[0]


    def ReplaceSelection_unicode(self, txt):
        return wxStyledTextCtrl.ReplaceSelection(self, mbcsEnc(txt, "replace")[0])


    def AddText_unicode(self, txt):
        return wxStyledTextCtrl.AddText(self, mbcsEnc(txt, "replace")[0])


    def SetSelectionByCharPos(self, start, end):
        """
        Same as SetSelection(), but start and end are character positions
        not byte positions
        """
        text = self.GetText()
        bs = self.bytelenSct(text[:start])
        be = bs + self.bytelenSct(text[start:end])
        self.SetSelection(bs, be)


    def GetSelectionCharPos(self):
        """
        Same as GetSelection(), but returned (start, end) are character positions
        not byte positions
        """
        start, end = self.GetSelection()
        cs = len(self.GetTextRange(0, start))
        ce = cs + len(self.GetTextRange(start, end))
        return (cs, ce)


    def saveLoadedDocPage(self):
        """
        Save loaded wiki page into database. Does not check if dirty
        """
        if self.loadedDocPage is None:
            return

        page = self.loadedDocPage
#         wikiWord = page.getWikiWord()
#         if wikiWord is not None:
#             self.lastCursorPositionInPage[wikiWord] = self.GetCurrentPos()

#         if not self.loadedDocPage.getDirty()[0]:
#             return

        text = self.GetText()
        if self.pWiki.saveDocPage(page, text):
            self.SetSavePoint()

        
        
    def _unloadCurrentDocPage(self, evtprops):
        # Unload current page
        if self.loadedDocPage is not None:
            if self.loadedDocPage.getDirty()[0]:
                self.saveLoadedDocPage()

            wikiWord = self.loadedDocPage.getWikiWord()
            if wikiWord is not None:
                self.lastCursorPositionInPage[wikiWord] = self.GetCurrentPos()
                self.scrollPosCache[wikiWord] = (self.GetScrollPos(wxHORIZONTAL),
                        self.GetScrollPos(wxVERTICAL))


            miscevt = self.loadedDocPage.getMiscEvent()
            miscevt.removeListener(self.wikiPageListener)
            
            self.loadedDocPage.removeTxtEditor(self)
            self.loadedDocPage = None
            self.pageType = "normal"


    def loadFuncPage(self, funcPage, evtprops=None):
        self._unloadCurrentDocPage(evtprops)
        # set the editor text
        content = None
        wikiDataManager = self.pWiki.getWikiDataManager()
        
        self.loadedDocPage = funcPage
        if self.loadedDocPage is None:
            self.SetText(u"")
            return  # TODO How to handle?

        miscevt = self.loadedDocPage.getMiscEvent()
        miscevt.addListener(self.wikiPageListener)
        self.loadedDocPage.addTxtEditor(self)

        try:
            content = self.loadedDocPage.getContent()
        except WikiFileNotFoundException, e:
            assert 0   # TODO

        globalProps = wikiDataManager.getWikiData().getGlobalProperties()
        # get the font that should be used in the editor
        font = globalProps.get("global.font", self.pWiki.defaultEditorFont)

        # set the styles in the editor to the font
        if self.lastFont != font:
            faces = self.pWiki.presentationExt.faces.copy()
            faces["mono"] = font
            self.SetStyles(faces)
            self.lastEditorFont = font

#         p2 = evtprops.copy()
#         p2.update({"loading current page": True})
#         self.pWiki.fireMiscEventProps(p2)  # TODO Remove this hack

        # now fill the text into the editor
        self.SetText(content)


    def loadWikiPage(self, wikiPage, evtprops=None):
        """
        Save loaded page, if necessary, then load wikiPage into editor
        """
        self._unloadCurrentDocPage(evtprops)        
        # set the editor text
        wikiDataManager = self.pWiki.getWikiDataManager()
        
        self.loadedDocPage = wikiPage

        if self.loadedDocPage is None:
            self.SetText(u"")
            return  # TODO How to handle?

        miscevt = self.loadedDocPage.getMiscEvent()
        miscevt.addListener(self.wikiPageListener)
        self.loadedDocPage.addTxtEditor(self)

        content = self.loadedDocPage.getContent()

        # get the font that should be used in the editor
        font = self.loadedDocPage.getPropertyOrGlobal("font",
                self.pWiki.defaultEditorFont)

        # set the styles in the editor to the font
        if self.lastFont != font:
            faces = self.pWiki.presentationExt.faces.copy()
            faces["mono"] = font
            self.SetStyles(faces)
            self.lastEditorFont = font
            
        if evtprops is None:
            evtprops = {}
        p2 = evtprops.copy()
        p2.update({"loading current page": True})
        self.pWiki.fireMiscEventProps(p2)  # TODO Remove this hack

        # now fill the text into the editor
        self.setTextAgaUpdated(content)

        self.pageType = self.loadedDocPage.getProperties().get(u"pagetype",
                [u"normal"])[-1]
                
        if self.pageType == u"normal":
            if not self.loadedDocPage.isDefined():
                # This is a new, not yet defined page, so go to the end of page
                self.GotoPos(self.GetLength())
            else:
                # see if there is a saved position for this page
                lastPos = self.lastCursorPositionInPage.get(
                        self.loadedDocPage.getWikiWord(), 0)
                self.GotoPos(lastPos)

                scrollPos = self.scrollPosCache.get(
                        self.loadedDocPage.getWikiWord())
                if scrollPos is not None:
                    # Bad hack: First scroll to position to avoid a visible jump
                    #   if scrolling works, then update display,
                    #   then scroll again because it may have failed the first time

                    self.SetScrollPos(wxHORIZONTAL, scrollPos[0], False)
                    screvt = wxScrollWinEvent(wxEVT_SCROLLWIN_THUMBTRACK, scrollPos[0], wxHORIZONTAL)
                    self.ProcessEvent(screvt)
                    screvt = wxScrollWinEvent(wxEVT_SCROLLWIN_THUMBRELEASE, scrollPos[0], wxHORIZONTAL)
                    self.ProcessEvent(screvt)
                    
                    self.SetScrollPos(wxVERTICAL, scrollPos[1], True)
                    screvt = wxScrollWinEvent(wxEVT_SCROLLWIN_THUMBTRACK, scrollPos[1], wxVERTICAL)
                    self.ProcessEvent(screvt)
                    screvt = wxScrollWinEvent(wxEVT_SCROLLWIN_THUMBRELEASE, scrollPos[1], wxVERTICAL)
                    self.ProcessEvent(screvt)

                    self.Update()

                    self.SetScrollPos(wxHORIZONTAL, scrollPos[0], False)
                    screvt = wxScrollWinEvent(wxEVT_SCROLLWIN_THUMBTRACK, scrollPos[0], wxHORIZONTAL)
                    self.ProcessEvent(screvt)
                    screvt = wxScrollWinEvent(wxEVT_SCROLLWIN_THUMBRELEASE, scrollPos[0], wxHORIZONTAL)
                    self.ProcessEvent(screvt)
                    
                    self.SetScrollPos(wxVERTICAL, scrollPos[1], True)
                    screvt = wxScrollWinEvent(wxEVT_SCROLLWIN_THUMBTRACK, scrollPos[1], wxVERTICAL)
                    self.ProcessEvent(screvt)
                    screvt = wxScrollWinEvent(wxEVT_SCROLLWIN_THUMBRELEASE, scrollPos[1], wxVERTICAL)
                    self.ProcessEvent(screvt)

        elif self.pageType == u"form":
            self.GotoPos(0)
            self._goToNextFormField()
        else:
            pass   # TODO Error message?


    def onOptionsChanged(self, miscevt):
        faces = self.pWiki.presentationExt.faces.copy()

        if isinstance(self.loadedDocPage, 
                (DocPages.WikiPage, DocPages.AliasWikiPage)):

            font = self.loadedDocPage.getPropertyOrGlobal("font",
                    self.pWiki.defaultEditorFont)
            faces["mono"] = font
            self.lastEditorFont = font    # ???

        self.SetStyles(faces)

        coltuple = htmlColorToRgbTuple(self.pWiki.getConfig().get(
                "main", "editor_bg_color"))

        if coltuple is None:
            coltuple = (255, 255, 255)
            
        color = wxColour(*coltuple)
        
        for i in xrange(32):
            self.StyleSetBackground(i, color)


    def onWikiPageUpdated(self, miscevt):
        if self.loadedDocPage is None or \
                not isinstance(self.loadedDocPage,
                (DocPages.WikiPage, DocPages.AliasWikiPage)):
            return

        # get the font that should be used in the editor
        font = self.loadedDocPage.getPropertyOrGlobal("font",
                self.pWiki.defaultEditorFont)

        # set the styles in the editor to the font
        if self.lastFont != font:
            faces = self.pWiki.presentationExt.faces.copy()
            faces["mono"] = font
            self.SetStyles(faces)
            self.lastEditorFont = font

        self.pageType = self.loadedDocPage.getProperties().get(u"pagetype",
                [u"normal"])[-1]


    def OnStyleNeeded(self, evt):
        "Styles the text of the editor"

        # get the text to regex against
        text = self.GetText()
        textlen = len(text)

#         self.tokenizer.setTokenThread(None)

        t = self.stylingThreadHolder.getThread()
        if t is not None:
#             t.cancel()
            self.stylingThreadHolder.setThread(None)
            self.stylebytes = None
            self.pageAst = None

        if textlen < self.pWiki.configuration.getint(
                "main", "sync_highlight_byte_limit"):
            # Synchronous styling
            self.stylingThreadHolder.setThread(None)
            self.buildStyling(text, 0, threadholder=DUMBTHREADHOLDER)
            self.applyStyling(self.stylebytes)
        else:
            # Asynchronous styling
            # This avoids further request from STC:
            self.StartStyling(self.GetLength(), 0xff)  # len(text) may be != self.GetLength()
            self.SetStyling(0, 0)

            sth = self.stylingThreadHolder
            
            delay = self.pWiki.configuration.getfloat(
                    "main", "async_highlight_delay")
            t = threading.Thread(None, self.buildStyling, args = (text, delay, sth))
#             t = threading.Timer(1, self.buildStyling, args = (text, sth))
            sth.setThread(t)
            t.start()

        # self.buildStyling(text, True)


    def OnContextMenu(self, evt):
        # Enable/Disable appropriate menu items
        self.contextMenu.FindItemById(GUI_ID.CMD_UNDO).Enable(self.CanUndo())
        self.contextMenu.FindItemById(GUI_ID.CMD_REDO).Enable(self.CanRedo())

        cancopy = self.GetSelectionStart() != self.GetSelectionEnd()
        self.contextMenu.FindItemById(GUI_ID.CMD_TEXT_DELETE).\
                Enable(cancopy and self.CanPaste())
        self.contextMenu.FindItemById(GUI_ID.CMD_CLIPBOARD_CUT).\
                Enable(cancopy and self.CanPaste())
        self.contextMenu.FindItemById(GUI_ID.CMD_CLIPBOARD_COPY).\
                Enable(cancopy)
        self.contextMenu.FindItemById(GUI_ID.CMD_CLIPBOARD_PASTE).\
                Enable(self.CanPaste())

        # Show menu
        self.PopupMenu(self.contextMenu)


    def _goToNextFormField(self):
        """
        If pagetype is "form" this is called when user presses TAB in
        text editor and after loading a form page
        """
        searchOp = SearchReplaceOperation()
        searchOp.wikiWide = False
        searchOp.wildCard = 'regex'
        searchOp.caseSensitive = True
        searchOp.searchStr = "&&[a-z]"
        
        text = self.GetText()
        charStartPos = len(self.GetTextRange(0, self.GetSelectionEnd()))
        while True:
            start, end = searchOp.searchText(text, charStartPos)[:2]
            if start is None: break
            
            fieldcode = text[start + 2]
            if fieldcode == "i":
                matchbytestart = self.bytelenSct(text[:start])
                matchbyteend = matchbytestart + \
                        self.bytelenSct(text[start:end])

                self.SetSelection(matchbytestart, matchbyteend)
                break
                
            charStartPos = end


    def storeStylingAndAst(self, stylebytes, page):
        self.stylebytes = stylebytes
        self.pageAst = page
        self.AddPendingEvent(wxIdleEvent())


    def buildStyling(self, text, delay, threadholder=DUMBTHREADHOLDER):
        if delay != 0:  # not threadholder is DUMBTHREADHOLDER:
            sleep(delay)
            if not threadholder.isCurrent():
                return

        page = PageAst.Page()
        page.buildAst(self.pWiki.getFormatting(), text,
                threadholder=threadholder)
        
#         print "buildStyling", repr(page.getTokens())
        
        stylebytes = self.processTokens(page.getTokens(), threadholder)
        
        if threadholder.isCurrent():
            self.storeStylingAndAst(stylebytes, page)


    def processTokens(self, tokens, threadholder):
        wikiData = self.pWiki.getWikiData()
        stylebytes = []
        
        for tok in tokens:
            if not threadholder.isCurrent():
                return ""

            styleno = tok.ttype
            bytestylelen = self.bytelenSct(tok.text)
            if styleno == WikiFormatting.FormatTypes.WikiWord:
                if wikiData.isDefinedWikiWord(tok.node.nakedWord):
                    styleno = WikiFormatting.FormatTypes.AvailWikiWord
                else:
                    styleno = WikiFormatting.FormatTypes.WikiWord
        
            elif styleno == WikiFormatting.FormatTypes.ToDo:
                styleno = -1
                node = tok.node
                stylebytes.append(chr(WikiFormatting.FormatTypes.Default) *
                        self.bytelenSct(node.indent))
                        
                stylebytes.append(chr(WikiFormatting.FormatTypes.ToDo) *
                        (self.bytelenSct(node.name) + self.bytelenSct(node.delimiter)))
                        
                stylebytes.append(self.processTokens(node.valuetokens, threadholder))

            elif styleno == WikiFormatting.FormatTypes.Table:
                styleno = -1
                node = tok.node

                stylebytes.append(chr(WikiFormatting.FormatTypes.Default) *
                        self.bytelenSct(node.begin))
                        
                stylebytes.append(self.processTokens(node.contenttokens, threadholder))

                stylebytes.append(chr(WikiFormatting.FormatTypes.Default) *
                        self.bytelenSct(node.end)) 

            elif styleno not in WikiFormatting.VALID_SCINTILLA_STYLES:
                # Style is not known to Scintilla, so use default instead
                styleno = WikiFormatting.FormatTypes.Default

            if styleno != -1:
                stylebytes.append(chr(styleno) * bytestylelen)
                

        return "".join(stylebytes)


    def applyStyling(self, stylebytes):
        if len(stylebytes) == self.GetLength():
            self.StartStyling(0, 0xff)
            self.SetStyleBytes(len(stylebytes), stylebytes)


    def snip(self):
        # get the selected text
        text = self.GetSelectedText()

        # copy it to the clipboard also
        self.Copy()

        # load the ScratchPad
#         try:
#             wikiPage = self.pWiki.getWikiDataManager().getWikiPage("ScratchPad")
#         except WikiWordNotFoundException, e:
#             wikiPage = self.pWiki.getWikiDataManager().createWikiPage("ScratchPad")
# 
#         content = ""
# 
#         # get the text from the scratch pad
#         try:
#             content = wikiPage.getContent()
#         except WikiFileNotFoundException, e:
#             content = u"++ Scratch Pad\n"

        wikiPage = self.pWiki.getWikiDataManager().getWikiPageNoError("ScratchPad")
        
        wikiPage.appendLiveText("\n%s\n---------------------------\n\n%s\n" %
                (mbcsDec(strftime("%x %I:%M %p"), "replace")[0], text))


        # TODO strftime
#         content = u"%s\n%s\n---------------------------\n\n%s\n" % \
#                 (content, mbcsDec(strftime("%x %I:%M %p"))[0], text)
#         wikiPage.save(content, False)
#         self.pWiki.statusBar.SetStatusText(uniToGui("Copied snippet to ScratchPad"), 0)

    def styleSelection(self, styleChars):
        """
        Currently len(styleChars) must be 1.
        """
        (startBytePos, endBytePos) = self.GetSelection()
        if startBytePos == endBytePos:
            (startBytePos, endBytePos) = self.getNearestWordPositions()

        for i in xrange(len(styleChars)):
            endBytePos = self.PositionAfter(endBytePos)

#         bytePos = self.PositionAfter(self.GetCurrentPos())

        bytePos = endBytePos
        for i in xrange(len(styleChars)):
            bytePos = self.PositionAfter(bytePos)
        self.GotoPos(startBytePos)
        self.AddText(styleChars)
        self.GotoPos(endBytePos)   # +len(styleChars)
        self.AddText(styleChars)
        self.GotoPos(bytePos)        


    def getPageAst(self):
        page = self.pageAst
        if page is None:
            t = self.stylingThreadHolder.getThread()
            if t is not None:
                t.join()
                page = self.pageAst
        
        if page is None:
            page = PageAst.Page()
            self.pageAst = page
            page.buildAst(self.pWiki.getFormatting(), self.GetText())
        
        return page


    def _activateTokens(self, tokens):
        """
        Helper for activateLink()
        """
        if len(tokens) == 0:
            return False

        for tok in tokens:
            if tok.ttype not in (WikiFormatting.FormatTypes.Url,
                    WikiFormatting.FormatTypes.WikiWord):
                continue
        
            if tok.ttype == WikiFormatting.FormatTypes.WikiWord:
                searchStr = None
    
                # open the wiki page
                self.pWiki.openWikiPage(tok.node.nakedWord, motionType="child")
    
                searchfrag = tok.node.searchFragment
                # Unescape search fragment
                if searchfrag is not None:
                    searchfrag = self.pWiki.getFormatting().\
                            SearchFragmentUnescapeRE.sub(ur"\1", searchfrag)
                    searchOp = SearchReplaceOperation()
                    searchOp.wildCard = "no"   # TODO Why not regex?
                    searchOp.searchStr = searchfrag
    
                    self.executeSearch(searchOp, 0)
    
                return True
    
            elif tok.ttype == WikiFormatting.FormatTypes.Url:
                self.pWiki.launchUrl(tok.node.url)
                return True
                
        return False


    def activateLink(self, mousePosition=None):
        "returns true if the link was activated"
        linkPos = self.GetCurrentPos()
        # mouse position overrides current pos
        if mousePosition:
            linkPos = self.PositionFromPoint(mousePosition)

        pageAst = self.getPageAst()
        linkCharPos = len(self.GetTextRange(0, linkPos))
        tokens = pageAst.getTokensForPos(linkCharPos)

        if not self._activateTokens(tokens):
            if linkCharPos > 0:
                # Maybe a token left to the cursor was meant, so check
                # one char to the left
                tokens = pageAst.getTokensForPos(linkCharPos - 1)

                return self._activateTokens(tokens)
        else:
            return True

        return False


#  DO NOT DELETE!
#     def launchUrl(self, link):   # TODO Works only for Windows
#         match = WikiFormatting.UrlRE.match(link)
#         try:
#             link2 = match.group(1)
#             
#             if link2.startswith("wiki:"):
#                 if self.pWiki.configuration.getint(
#                         "main", "new_window_on_follow_wiki_url") == 1:
#                     os.startfile(link2)
#                     return True
#                 else:
#                     link2 = urllib.url2pathname(link2)
#                     link2 = link2.replace(u"wiki:", u"")
#                     if exists(link2):
#                         self.openWiki(link2, u"")
#                         return True
#                     else:
#                         self.SetStatusText(
#                                 uniToGui(u"Couldn't find wiki: %s" % link2))
#                         return False
#             elif link2.startswith("file:"):
#                 link2 = link2.replace(u"file:", u"")
#                 if "|" in link2:
#                     # Link is absolute
#                     filepath = urllib.url2pathname(link2)
#                 else:
#                     # Link is relative, cut off leading '/'
#                     while link2.startswith("/"):
#                         link2 = link2[1:]
#                     filepath = urllib.url2pathname(link2)
#                     filepath = join(self.dataDir, filepath)
#                     
#                 if exists(filepath):
#                     os.startfile(filepath)
#                     return True
#                 else:
#                     self.SetStatusText(
#                             uniToGui(u"Couldn't find file: %s" % filepath))
#                     return False
#             else:
#                 os.startfile(link2)
#         except:
#             pass
#         return False


    def evalScriptBlocks(self, index=-1):
        """
        Evaluates scripts. Respects "script_security_level" option
        """
        securityLevel = self.pWiki.configuration.getint(
                "main", "script_security_level")
        if securityLevel == 0:
            # No scripts allowed
            # Print warning message
            wxMessageBox(u"Set in options, chapter \"Other\", \n"
                    "item \"Script security\" an appropriate value \n"
                    "to execute a script", u"Script execution disabled",
                    wxOK, self.pWiki)
            return

        # it is important to python to have consistent eol's
        self.ConvertEOLs(self.eolMode)
        (startPos, endPos) = self.GetSelection()

        # if no selection eval all scripts
        if startPos == endPos or index > -1:
            # get the text of the current page
            text = self.GetText()
            
            # process script imports
            if securityLevel > 1: # Local import_scripts properties allowed
                if self.loadedDocPage.getProperties().has_key(
                        "import_scripts"):
                    scripts = self.loadedDocPage.getProperties()[
                            "import_scripts"]
                    for script in scripts:
                        try:
                            importPage = self.pWiki.getWikiDataManager().\
                                    getWikiPage(script)
                            content = importPage.getContent()
                            text += "\n" + content
                        except:
                            pass

            if securityLevel > 2: # global.import_scripts property also allowed
                globscript = self.pWiki.getWikiData().getGlobalProperties().get(
                        "global.import_scripts")
    
                if globscript is not None:
                    try:
                        importPage = self.pWiki.getWikiDataManager().\
                                getWikiPage(globscript)
                        content = importPage.getContent()
                        text += "\n" + content
                    except:
                        pass

            match = WikiFormatting.ScriptRE.search(text)
            while(match):
                script = re.sub(u"^[\r\n\s]+", "", match.group(1))
                script = re.sub(u"[\r\n\s]+$", "", script)
                try:
                    if index == -1:
                        script = re.sub(u"^\d:?\s?", u"", script)
                        exec(script) in self.evalScope
                    elif index > -1 and script.startswith(str(index)):
                        script = re.sub(u"^\d:?\s?", u"", script)
                        exec(script) in self.evalScope
                        break # Execute only the first found script

                except Exception, e:
                    self.AddText(u"\nException: %s" % unicode(e))

                match = WikiFormatting.ScriptRE.search(text, match.end())
        else:
            text = self.GetSelectedText()
            try:
                result = eval(re.sub(u"[\n\r]", u"", text), self.evalScope)
            except Exception, e:
                s = StringIO()
                traceback.print_exc(file=s)
                result = s.getvalue()

            pos = self.GetCurrentPos()
            self.GotoPos(endPos)
            self.AddText(u" = %s" % unicode(result))
            self.GotoPos(pos)


    def cleanAutoGenAreas(self, text):
        """
        Remove any content from the autogenerated areas and return
        cleaned text. Call this before storing page in the database.
        The original text is returned if option
        "process_autogenerated_areas" is False.
        """
        if not self.pWiki.configuration.getboolean("main",
                "process_autogenerated_areas"):
            return text

        return WikiFormatting.AutoGenAreaRE.sub(ur"\1\2\4", text)


    def _agaReplace(self, match):
        try:
            result = unicode(eval(match.group(2), self.evalScope))
        except Exception, e:
            s = StringIO()
            traceback.print_exc(file=s)
            result = unicode(s.getvalue())

        if len(result) == 0 or result[-1] != u"\n":
            result += u"\n"

        return match.group(1) + match.group(2) + result + match.group(4)


    def updateAutoGenAreas(self, text):
        """
        Update content of the autogenerated areas and return
        updated text. Call this before loading the text in the editor
        and on user request. The original text is returned if
        option "process_autogenerated_areas" is False.
        """
        if not self.pWiki.configuration.getboolean("main",
                "process_autogenerated_areas"):
            return text

        # So the text can be referenced from an AGA function
        self.agatext = text

        return WikiFormatting.AutoGenAreaRE.sub(self._agaReplace, text)


    def getAgaCleanedText(self):
        """
        Get editor text after cleaning of autogenerated area content
        if configuration option is set appropriately, otherwise, the
        text is not modified
        """
        return self.cleanAutoGenAreas(self.GetText())


    def setTextAgaUpdated(self, text):
        """
        Set editor text after updating of autogenerated area content
        if configuration option is set appropriately, otherwise, the
        text is not modified
        """
        self.SetText(self.updateAutoGenAreas(text))


    # TODO  Reflect possible changes in WikiSyntax.py
    AGACONTENTTABLERE = re.compile(ur"^(\+{1,4})([^\n\+][^\n]*)", re.DOTALL | re.LOCALE | re.MULTILINE)

    def agaContentTable(self, omitfirst = False):
        """
        Can be called by an aga to present the content table of the current page.
        The text is assumed to be in self.agatext variable(see updateAutoGenAreas()).
        If omitfirst is true, the first entry (normally the title) is not shown.
        """
        allmatches = map(lambda m: m.group(0), self.AGACONTENTTABLERE.finditer(self.agatext))
        if omitfirst and len(allmatches) > 0:
            allmatches = allmatches[1:]

        return u"\n".join(allmatches)


        # TODO Multi column support
    def agaFormatList(self, l):
        """
        Format a list l of strings in a nice way for an aga content
        """
        return u"\n".join(l)


    def agaParentsTable(self):
        """
        Can be called by an aga to present all parents of the current page.
        """
        relations = self.loadedDocPage.getParentRelationships()[:]

        # Apply sort order
        relations.sort(_removeBracketsAndSort) # sort alphabetically

        return self.agaFormatList(relations)


    def startIncrementalSearch(self, searchStr=u''):
        self.SetFocus()
        self.searchStr = searchStr
        self.pWiki.statusBar.SetStatusText(uniToGui(u"Search (ESC to stop): "), 0)
        self.searchCharStartPos = len(self.GetTextRange(0, self.GetCurrentPos()))

        self.inIncrementalSearch = True
        self.anchorBytePosition = -1
        self.anchorCharPosition = -1


    def executeIncrementalSearch(self, next=False):
        """
        Run incremental search
        """
        self.pWiki.statusBar.SetStatusText(
                uniToGui(u"Search (ESC to stop): %s" % self.searchStr), 0)
        text = self.GetText()
        if len(self.searchStr) > 0:   # and not searchStr.endswith("\\"):
            charStartPos = self.searchCharStartPos
            if next and (self.anchorCharPosition != -1):
                charStartPos = self.anchorCharPosition

            regex = None
            try:
                regex = re.compile(self.searchStr, re.IGNORECASE | \
                        re.MULTILINE | re.UNICODE)
            except:
                # Regex error
                return self.anchorCharPosition

            match = regex.search(text, charStartPos, len(text))
            if not match and charStartPos > 0:
                match = regex.search(text, 0, charStartPos)

            if match:
                matchbytestart = self.bytelenSct(text[:match.start()])
                self.anchorBytePosition = matchbytestart + \
                        self.bytelenSct(text[match.start():match.end()])
                self.anchorCharPosition = match.end()

                self.SetSelection(matchbytestart, self.anchorBytePosition)

                return self.anchorCharPosition

        self.SetSelection(-1, -1)
        self.anchorBytePosition = -1
        self.anchorCharPosition = -1
        self.GotoPos(self.bytelenSct(text[:self.searchCharStartPos]))

        return -1


    def endIncrementalSearch(self):
        self.pWiki.statusBar.SetStatusText("", 0)
        self.inIncrementalSearch = False
        self.anchorBytePosition = -1
        self.anchorCharPosition = -1


    def executeSearch(self, sarOp, searchCharStartPos=-1, next=False):
        """
        Returns a tuple with a least two elements (<start>, <after end>)
        containing start and after end char positions of the found occurrence
        or (-1, -1) if not found.
        """
        if sarOp.booleanOp:
            return (-1, -1)  # Not possible

        if searchCharStartPos < 0:
            searchCharStartPos = self.searchCharStartPos

#         self.pWiki.statusBar.SetStatusText(
#                 uniToGui(u"Search (ESC to stop): %s" % searchStr), 0)
        text = self.GetText()
        if len(sarOp.searchStr) > 0:
            charStartPos = searchCharStartPos
#             if next and (self.anchorCharPosition != -1):
#                 charStartPos = self.anchorCharPosition
            if next:
                charStartPos = len(self.GetTextRange(0, self.GetSelectionEnd()))
            try:
                found = sarOp.searchText(text, charStartPos)
                start, end = found[:2]
            except:
                # Regex error
                return (-1, -1)  # (self.anchorCharPosition, self.anchorCharPosition)
                
            if start is not None:
                matchbytestart = self.bytelenSct(text[:start])
                self.anchorBytePosition = matchbytestart + \
                        self.bytelenSct(text[start:end])
                self.anchorCharPosition = end

                self.SetSelection(matchbytestart, self.anchorBytePosition)

#                 if sarOp.replaceOp:
#                     replacement = sarOp.replace(text, found)                    
#                     self.ReplaceSelection(replacement)
#                     selByteEnd = matchbytestart + self.bytelenSct(replacement)
#                     selCharEnd = start + len(replacement)
#                     self.SetSelection(matchbytestart, selByteEnd)
#                     self.anchorBytePosition = selByteEnd
#                     self.anchorCharPosition = selCharEnd
# 
#                     return selCharEnd
#                 else:
#                     return self.anchorCharPosition
                return found    # self.anchorCharPosition

        self.SetSelection(-1, -1)
        self.anchorBytePosition = -1
        self.anchorCharPosition = -1
        self.GotoPos(self.bytelenSct(text[:searchCharStartPos]))

        return (-1, -1)
        
        
    def executeReplace(self, sarOp):
        """
        Returns char position after replacement or -1 if replacement wasn't
        possible
        """
        seltext = self.GetSelectedText()
        found = sarOp.matchesPart(seltext)
        
        if found is None:
            return -1

        replacement = sarOp.replace(seltext, found)                    
        bytestart = self.GetSelectionStart()
        self.ReplaceSelection(replacement)
        selByteEnd = bytestart + self.bytelenSct(replacement)
        selCharEnd = len(self.GetTextRange(0, selByteEnd))
#         self.SetSelection(matchbytestart, selByteEnd)
        self.anchorBytePosition = selByteEnd
        self.anchorCharPosition = selCharEnd

        return selCharEnd


    def rewrapText(self):
        curPos = self.GetCurrentPos()

        # search back for start of the para
        curLineNum = self.GetCurrentLine()
        curLine = self.GetLine(curLineNum)
        while curLineNum > 0:
            # don't wrap previous bullets with this bullet
            if (WikiFormatting.BulletRE.match(curLine) or WikiFormatting.NumericBulletRE.match(curLine)):
                break

            if WikiFormatting.EmptyLineRE.match(curLine):
                curLineNum = curLineNum + 1
                break

            curLineNum = curLineNum - 1
            curLine = self.GetLine(curLineNum)
        startLine = curLineNum

        # search forward for end of the para
        curLineNum = self.GetCurrentLine()
        curLine = self.GetLine(curLineNum)
        while curLineNum <= self.GetLineCount():
            # don't wrap the next bullet with this bullet
            if curLineNum > startLine:
                if (WikiFormatting.BulletRE.match(curLine) or WikiFormatting.NumericBulletRE.match(curLine)):
                    curLineNum = curLineNum - 1
                    break

            if WikiFormatting.EmptyLineRE.match(curLine):
                curLineNum = curLineNum - 1
                break

            curLineNum = curLineNum + 1
            curLine = self.GetLine(curLineNum)
        endLine = curLineNum

        if (startLine <= endLine):
            # get the start and end of the lines
            startPos = self.PositionFromLine(startLine)
            endPos = self.GetLineEndPosition(endLine)

            # get the indentation for rewrapping
            indent = self.GetLineIndentation(startLine)
            subIndent = indent

            # if the start of the para is a bullet the subIndent has to change
            if WikiFormatting.BulletRE.match(self.GetLine(startLine)):
                subIndent = indent + 2
            else:
                match = WikiFormatting.NumericBulletRE.match(self.GetLine(startLine))
                if match:
                    subIndent = indent + len(match.group(2)) + 2

            # get the text that will be wrapped
            text = self.GetTextRange(startPos, endPos)
            # remove spaces, newlines, etc
            text = re.sub("[\s\r\n]+", " ", text)

            # wrap the text
            wrapPosition = 70
            try:
                wrapPosition = int(
                        self.loadedDocPage.getPropertyOrGlobal(
                        "wrap", "70"))
            except:
                pass

            # make the min wrapPosition 5
            if wrapPosition < 5:
                wrapPosition = 5

            filledText = fill(text, width=wrapPosition,
                    initial_indent=u" " * indent, 
                    subsequent_indent=u" " * subIndent)
            # replace the text based on targetting
            self.SetTargetStart(startPos)
            self.SetTargetEnd(endPos)
            self.ReplaceTarget(filledText)
            self.GotoPos(curPos)

    def getWikiWordText(self, position):
        word = self.getTextInStyle(position, WikiFormatting.FormatTypes.WikiWord)
        if not word:
            word = self.getTextInStyle(position, WikiFormatting.FormatTypes.WikiWord2)
        if not word:
            word = self.getTextInStyle(position, WikiFormatting.FormatTypes.AvailWikiWord)
        return word

    def getWikiWordBeginEnd(self, position):
        (start, end) = self.getBeginEndOfStyle(position, WikiFormatting.FormatTypes.WikiWord)
        if start == -1 and end == -1:
            (start, end) = self.getBeginEndOfStyle(position, WikiFormatting.FormatTypes.WikiWord2)
        if start == -1 and end == -1:
            (start, end) = self.getBeginEndOfStyle(position, WikiFormatting.FormatTypes.AvailWikiWord)
        return (start, end)

    def isPositionInWikiWord(self, position):
        return self.isPositionInStyle(position, WikiFormatting.FormatTypes.WikiWord) \
               or self.isPositionInStyle(position, WikiFormatting.FormatTypes.WikiWord2) \
               or self.isPositionInStyle(position, WikiFormatting.FormatTypes.AvailWikiWord)

    def isPositionInLink(self, position):
        return self.isPositionInStyle(position, WikiFormatting.FormatTypes.Url)

    def isPositionInStyle(self, position, style):
        return self.GetStyleAt(position) == style

    def getTextInStyle(self, position, style):
        (start, end) = self.getBeginEndOfStyle(position, style)
        if start >= 0 and end >= 0:
            return self.GetTextRange(start, end+1)

    def getBeginEndOfStyle(self, position, style):
        currentStyle = self.GetStyleAt(position)
        if currentStyle != style:
            return (-1, -1)

        startPos = 0
        currentPos = position
        while currentPos >= 0:
            currentStyle = self.GetStyleAt(currentPos)
            if currentStyle == style:
                startPos = currentPos
                if currentPos > 0:
                    currentPos = currentPos - 1
                else:
                    break
            else:
                break

        endPos = 0
        currentPos = position
        while currentPos < self.GetLength():
            currentStyle = self.GetStyleAt(currentPos)
            if currentStyle == style:
                endPos = currentPos
                currentPos = currentPos + 1
            else:
                break

        if endPos > startPos:
            return (startPos, endPos)
        else:
            return (-1, -1)

    def getNearestWordPositions(self, bytepos=None):
        if not bytepos:
            bytepos = self.GetCurrentPos()
        return (self.WordStartPosition(bytepos, 1), self.WordEndPosition(bytepos, 1))

    def OnChange(self, evt):
        if not self.ignoreOnChange:
            self.loadedDocPage.setDirty(True)

    def OnCharAdded(self, evt):
        "When the user presses enter reindent to the previous level"

#         currPos = self.GetScrollPos(wxVERTICAL)
        
        key = evt.GetKey()

        if key == 10:
            currentLine = self.GetCurrentLine()
            if currentLine > 0:
                previousLine = self.GetLine(currentLine-1)

                # check if the prev level was a bullet level
                if self.autoBullets:
                    match = WikiFormatting.BulletRE.match(previousLine)
                    if match:
                        self.AddText(
                                (" " * self.GetLineIndentation(currentLine-1)) +
                                match.group("actualBullet"))
                        return

                    match = WikiFormatting.NumericBulletRE.search(previousLine)
                    if match:
                        prevNumStr = match.group(3)
                        prevNum = int(prevNumStr)
                        nextNum = prevNum+1
                        adjustment = len(str(nextNum)) - len(prevNumStr)

                        self.AddText(u"%s%s%d. " % (u" " * (self.GetLineIndentation(currentLine-1) - adjustment), match.group(2), int(prevNum)+1))
                        return

                if self.autoIndent:
                    self.AddText(u" " * self.GetLineIndentation(currentLine-1))


    def OnKeyDown(self, evt):
#         self.idleCounter = 0
        key = evt.GetKeyCode()
        self.lastKeyPressed = time()

        if key == WXK_F3 and not self.inIncrementalSearch:
            self.startIncrementalSearch()
            evt.Skip()
        else:

            # handle key presses while in incremental search here
            if self.inIncrementalSearch:
                if key < 256:
                    # escape ends the search
                    if key == WXK_ESCAPE:
                        self.endIncrementalSearch()
                    # do the next search on another ctrl-s, or f
                    elif evt.ControlDown() and (key == ord('S') or \
                            key == ord(self.pWiki.keyBindings.IncrementalSearchCtrl)):
                        self.executeIncrementalSearch(next=True)
                    # handle the delete key
                    elif key == WXK_BACK or key == WXK_DELETE:
                        self.searchStr = self.searchStr[:len(self.searchStr)-1]
                        self.executeIncrementalSearch();
                    # handle the other keys
                    else:
                        evt.Skip() # OnChar is responsible for that

                elif key == WXK_F3:
                    self.executeIncrementalSearch(next=True)
                else:
                    # TODO Should also work for mouse!
                    self.anchorBytePosition = self.GetCurrentPos()
                    self.anchorCharPosition = \
                            len(self.GetTextRange(0, self.GetCurrentPos()))

                    evt.Skip()

            elif evt.ControlDown():
                (selectStart, selectEnd) = self.GetSelection()

                # activate link
                if key == ord(self.pWiki.keyBindings.IncrementalSearchCtrl) and \
                        not evt.ShiftDown() and not evt.AltDown():
                    self.startIncrementalSearch()

                elif key == WXK_SPACE:
                    # Handle autocompletion
                    endBytePos = self.GetCurrentPos()
                    startBytePos = self.PositionFromLine(
                            self.LineFromPosition(endBytePos))
                    line = self.GetTextRange(startBytePos, endBytePos)
                    rline = revStr(line)
                    mat1 = WikiFormatting.RevWikiWordRE.match(rline)
                    mat2 = WikiFormatting.RevWikiWordRE2.match(rline)
                    mat3 = WikiFormatting.RevPropertyValue.match(rline)
                    acresult = []
                    self.autoCompBackBytesWithoutBracket = 0
                    self.autoCompBackBytesWithBracket = 0

                    if mat1:
                        # may be CamelCase word
                        tofind = line[-mat1.end():]
                        # print "mat1", repr(tofind)
                        self.autoCompBackBytesWithoutBracket = self.bytelenSct(tofind)
                        formatting = self.pWiki.getFormatting()
                        acresult += filter(formatting.isCcWikiWord, 
                                self.pWiki.wikiData.getWikiWordsStartingWith(
                                tofind, True))

                    if mat2:
                        # may be not-CamelCase word or in a property name
                        tofind = line[-mat2.end():]
                        # print "mat2", repr(tofind)
                        self.autoCompBackBytesWithBracket = self.bytelenSct(tofind)
                        acresult += map(lambda s: u"[" + s, self.pWiki.wikiData.\
                                getWikiWordsStartingWith(tofind[1:], True))
                        acresult += map(lambda s: u"[" + s, self.pWiki.wikiData.\
                                getPropertyNamesStartingWith(tofind[1:]))

                    elif mat3:
                        # In a property value
                        tofind = line[-mat3.end():]
                        propkey = revStr(mat3.group(3))
                        propfill = revStr(mat3.group(2))
                        propvalpart = revStr(mat3.group(1))
                        # print "mat3", repr(tofind)
                        self.autoCompBackBytesWithBracket = self.bytelenSct(tofind)
                        values = filter(lambda pv: pv.startswith(propvalpart),
                                self.pWiki.wikiData.getDistinctPropertyValues(propkey))
                        acresult += map(lambda v: u"[" + propkey + propfill + 
                                v +  u"]", values)

                    # print "line", repr(line)
                    
                    if len(acresult) > 0:
                        # print "acresult", repr(acresult), repr(endBytePos-startBytePos)
                        self.UserListShow(1, u"~".join(acresult))
                    
                elif key == WXK_RETURN:
                    self.activateLink()
                else:
                    evt.Skip()

            elif not evt.ControlDown() and not evt.ShiftDown():  # TODO Check all modifiers
                if key == WXK_TAB:
                    if self.pageType == u"form":
                        self._goToNextFormField()
                        return
                evt.Skip()
            else:
                evt.Skip()


    def OnSetFocus(self, evt):
        self.pWiki.setActiveEditor(self)
        evt.Skip()


    def OnUserListSelection(self, evt):
        text = evt.GetText()
        # print "OnUserListSelection", repr(evt.GetText())   # TODO: Non unicode version
        if text[0] == "[":
            toerase = self.autoCompBackBytesWithBracket
        else:
            toerase = self.autoCompBackBytesWithoutBracket
            
        self.SetSelection(self.GetCurrentPos() - toerase, self.GetCurrentPos())
        
        self.ReplaceSelection(text)
        

    def OnChar(self, evt):
        key = evt.GetKeyCode()
        # handle key presses while in incremental search here
        if self.inIncrementalSearch and key < WXK_START and key > 31 and \
                not evt.ControlDown():

            if isUnicode():
                self.searchStr += unichr(evt.GetUnicodeKey())
            else:
                self.searchStr += mbcsDec(chr(key))[0]

            self.executeIncrementalSearch();
        else:
            evt.Skip()


    def OnClick(self, evt):
        if evt.ControlDown():
            x = evt.GetX()
            y = evt.GetY()
            if not self.activateLink(wxPoint(x, y)):
                evt.Skip()
        else:
            evt.Skip()

    def OnDoubleClick(self, evt):
        x = evt.GetX()
        y = evt.GetY()
        if not self.activateLink(wxPoint(x, y)):
            evt.Skip()

    def OnMouseMove(self, evt):
        if (not evt.ControlDown()) or evt.Dragging():
            # self.SetCursor(WikiTxtCtrl.CURSOR_IBEAM)
            evt.Skip()
            return
        else:
            textPos = self.PositionFromPoint(evt.GetPosition())

            if (self.isPositionInWikiWord(textPos) or
                        self.isPositionInLink(textPos)):
                self.SetCursor(WikiTxtCtrl.CURSOR_HAND)
                return
            else:
                # self.SetCursor(WikiTxtCtrl.CURSOR_IBEAM)
                evt.Skip()
                return


    def OnIdle(self, evt):
#         self.idleCounter -= 1
#         if self.idleCounter < 0:
#             self.idleCounter = 0
        if (self.IsEnabled()):
            # fix the line, pos and col numbers
            currentLine = self.GetCurrentLine()+1
            currentPos = self.GetCurrentPos()
            currentCol = self.GetColumn(currentPos)
            self.pWiki.statusBar.SetStatusText(uniToGui(u"Line: %d Col: %d Pos: %d" %
                                            (currentLine, currentCol, currentPos)), 2)

            stylebytes = self.stylebytes
            self.stylebytes = None
    
            if stylebytes:
                self.applyStyling(stylebytes)


    def OnDestroy(self, evt):
        # This is how the clipboard contents can be preserved after
        # the app has exited.
        wxTheClipboard.Flush()
        evt.Skip()


    # TODO !!!!!!!!!!!!!
#     def setMouseCursor(self):
#         """
#         Set the right mouse cursor depending on some circumstances.
#         Returns True iff a special cursor was choosen.
#         """
#         mousePos = wxGetMousePosition()
#         mouseBtnPressed = wxGetKeyState(WXK_LBUTTON) or \
#                 wxGetKeyState(WXK_MBUTTON) or \
#                 wxGetKeyState(WXK_RBUTTON)
# 
#         ctrlPressed = wxGetKeyState(WXK_CONTROL)
# 
#         if (not ctrlPressed) or mouseBtnPressed:
#             self.SetCursor(WikiTxtCtrl.CURSOR_IBEAM)
#             return False
#         else:
#             linkPos = self.PositionFromPoint(wxPoint(*self.ScreenToClientXY(*mousePos)))
# 
#             if (self.isPositionInWikiWord(linkPos) or
#                         self.isPositionInLink(linkPos)):
#                 self.SetCursor(WikiTxtCtrl.CURSOR_HAND)
#                 return True
#             else:
#                 self.SetCursor(WikiTxtCtrl.CURSOR_IBEAM)
#                 return False


# # Already defined in WikiTreeCtrl
# def _getTextForNode(text):
#     if text.startswith("["):
#         return text[1:len(text)-1]
#     return text


# sorter for relations, removes brackets and sorts lower case
# Already defined in WikiTreeCtrl
def _removeBracketsAndSort(a, b):
#     a = wikiWordToLabel(a)
#     b = wikiWordToLabel(b)
    return cmp(a.lower(), b.lower())


class WikiTxtCtrlDropTarget(wxPyDropTarget):
    def __init__(self, editor):
        wxPyDropTarget.__init__(self)

        self.editor = editor
        self.resetDObject()

    def resetDObject(self):
        """
        (Re)sets the dataobject at init and after each drop
        """
        dataob = wxDataObjectComposite()
        self.tobj = wxTextDataObject()  # Char. size depends on wxPython build!
        dataob.Add(self.tobj)
        self.fobj = wxFileDataObject()
        
        dataob.Add(self.fobj)

        self.dataob = dataob
        self.SetDataObject(dataob)

##    def OnDrop(self, x, y):
##        return 1


    def OnDragOver(self, x, y, defresult):
        return self.editor.DoDragOver(x, y, defresult)


    def OnData(self, x, y, defresult):
        try:
            if self.GetData():
                # data = self.dataob
                # formats = data.GetAllFormats()

                fnames = self.fobj.GetFilenames()
                text = self.tobj.GetText()

                if fnames:
                    self.OnDropFiles(x, y, fnames)
                elif text:
                    text = lineendToInternal(text)
                    self.OnDropText(x, y, text)

            return defresult

        finally:
            self.resetDObject()


    def OnDropText(self, x, y, text):
        self.editor.DoDropText(x, y, text)

        # TODO works for Windows only
    def OnDropFiles(self, x, y, filenames):
        urls = []
        for fn in filenames:
            url = urllib.pathname2url(fn)
            if fn.endswith(".wiki"):
                urls.append("wiki:%s" % url)
            else:
                doCopy = False  # Necessary because key state may change between
                                # the two ifs
                if wxGetKeyState(WXK_CONTROL):
                    # Copy file into file storage
                    fs = self.editor.pWiki.getWikiDataManager().getFileStorage()
                    try:
                        fn = fs.createDestPath(fn)
                        doCopy = True
                    except Exception, e:
                        traceback.print_exc()
                        self.editor.pWiki.displayErrorMessage(
                                u"Couldn't copy file", e)
                        return

                if wxGetKeyState(WXK_SHIFT) or doCopy:
                    # Relative rel: URL
                    locPath = self.editor.pWiki.getWikiConfigPath()
                    if locPath is not None:
                        locPath = dirname(locPath)
                        relPath = relativeFilePath(locPath, fn)
                        if relPath is None:
                            # Absolute path needed
                            urls.append("file:%s" % url)
                        else:
                            urls.append("rel://%s" % urllib.pathname2url(relPath))
                else:
                    # Absolute file: URL
                    urls.append("file:%s" % url)
                
#             if f.endswith(".wiki"):
#                 url = urllib.pathname2url(f)
#                 urls.append("wiki:%s" % url)
#             else:
#                 if f.startswith(self.controller.dataDir + sep):
#                     f = "//" + f[len(self.controller.dataDir + sep):]
#                 
#                 url = urllib.pathname2url(f)
# 
#                 urls.append("file:%s" % url)


        self.editor.DoDropText(x, y, " ".join(urls))

