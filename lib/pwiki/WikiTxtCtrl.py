## import hotshot
## _prof = hotshot.Profile("hotshot.prf")

import os, traceback, codecs, array
from cStringIO import StringIO
import urllib_red as urllib
import string
import srePersistent as re
import threading

from os.path import exists, dirname

from time import time, strftime, sleep
from textwrap import fill

import wx, wx.stc

from Utilities import *

from wxHelper import GUI_ID, getTextFromClipboard, copyTextToClipboard, \
        wxKeyFunctionSink, getAccelPairFromKeyDown, appendToMenuByMenuDesc, \
        getBitmapFromClipboard
from MiscEvent import KeyFunctionSinkAR

from Configuration import MIDDLE_MOUSE_CONFIG_TO_TABMODE
from AdditionalDialogs import ImagePasteSaver, ImagePasteDialog
import WikiFormatting
import PageAst, DocPages
from WikiExceptions import WikiWordNotFoundException, WikiFileNotFoundException

from SearchAndReplace import SearchReplaceOperation
from StringOps import *
# utf8Enc, utf8Dec, mbcsEnc, mbcsDec, uniToGui, guiToUni, \
#        Tokenizer, wikiWordToLabel, revStr, lineendToInternal, lineendToOs

from Configuration import isUnicode, isWin9x, isLinux


try:
    import WindowsHacks
except:
    WindowsHacks = None


# Python compiler flag for float division
CO_FUTURE_DIVISION = 0x2000



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


class IncrementalSearchDialog(wx.Frame):
    
    COLOR_YELLOW = wx.Colour(255, 255, 0);
    COLOR_GREEN = wx.Colour(0, 255, 0);
    
    def __init__(self, parent, id, txtCtrl, rect, font, presenter, searchInit=None):
        wx.Frame.__init__(self, parent, id, u"", rect.GetPosition(),
                rect.GetSize(), wx.NO_BORDER)

        self.txtCtrl = txtCtrl
        self.presenter = presenter
        self.tfInput = wx.TextCtrl(self, GUI_ID.INC_SEARCH_TEXT_FIELD,
                u"Incremental search (ENTER/ESC to finish)",
                style=wx.TE_PROCESS_ENTER | wx.TE_RICH)

        self.tfInput.SetFont(font)
        self.tfInput.SetBackgroundColour(IncrementalSearchDialog.COLOR_YELLOW)
        mainsizer = wx.BoxSizer(wx.HORIZONTAL)
        mainsizer.Add(self.tfInput, 1, wx.ALL | wx.EXPAND, 0)

        self.SetSizer(mainsizer)
        self.Layout()
        self.tfInput.SetFocus()

        config = self.txtCtrl.presenter.getConfig()

        self.closeDelay = 1000 * config.getint("main", "incSearch_autoOffDelay",
                0)  # Milliseconds to close or 0 to deactivate

        wx.EVT_TEXT(self, GUI_ID.INC_SEARCH_TEXT_FIELD, self.OnText)
        wx.EVT_KEY_DOWN(self.tfInput, self.OnKeyDownInput)
        wx.EVT_KILL_FOCUS(self.tfInput, self.OnKillFocus)
        wx.EVT_TIMER(self, GUI_ID.TIMER_INC_SEARCH_CLOSE,
                self.OnTimerIncSearchClose)
        wx.EVT_MOUSE_EVENTS(self.tfInput, self.OnMouseAnyInput)

        if searchInit:
            self.tfInput.SetValue(searchInit)
            self.tfInput.SetSelection(-1, -1)

        if self.closeDelay:
            self.closeTimer = wx.Timer(self, GUI_ID.TIMER_INC_SEARCH_CLOSE)
            self.closeTimer.Start(self.closeDelay, True)

    def OnKillFocus(self, evt):
        self.Close()

    def OnText(self, evt):
        self.txtCtrl.searchStr = self.tfInput.GetValue()
        foundPos = self.txtCtrl.executeIncrementalSearch()

        if foundPos == -1:
            # Nothing found
            self.tfInput.SetBackgroundColour(IncrementalSearchDialog.COLOR_YELLOW)
        else:
            # Found
            self.tfInput.SetBackgroundColour(IncrementalSearchDialog.COLOR_GREEN)

    def OnMouseAnyInput(self, evt):
        if evt.Button(wx.MOUSE_BTN_ANY) and self.closeDelay:
            # If a mouse button was pressed/released, restart timer
            self.closeTimer.Start(self.closeDelay, True)

        evt.Skip()


    def OnKeyDownInput(self, evt):
        if self.closeDelay:
            self.closeTimer.Start(self.closeDelay, True)

        key = evt.GetKeyCode()
        accP = getAccelPairFromKeyDown(evt)
        matchesAccelPair = self.presenter.getMainControl().keyBindings.\
                matchesAccelPair

        foundPos = -2
        if key in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
            # Return pressed
            self.Close()
        elif key == wx.WXK_ESCAPE:
            # Esc -> Abort inc. search, go back to start
            self.txtCtrl.resetIncrementalSearch()
            self.Close()
        elif matchesAccelPair("ContinueSearch", accP):
            foundPos = self.txtCtrl.executeIncrementalSearch(next=True)
        # do the next search on another ctrl-f
        elif matchesAccelPair("StartIncrementalSearch", accP):
            foundPos = self.txtCtrl.executeIncrementalSearch(next=True)
        elif accP in ((wx.ACCEL_NORMAL, wx.WXK_DOWN),
                (wx.ACCEL_NORMAL, wx.WXK_PAGEDOWN),
                (wx.ACCEL_NORMAL, wx.WXK_NUMPAD_DOWN),
                (wx.ACCEL_NORMAL, wx.WXK_NUMPAD_PAGEDOWN),
                (wx.ACCEL_NORMAL, wx.WXK_NEXT)):
            foundPos = self.txtCtrl.executeIncrementalSearch(next=True)
        elif matchesAccelPair("BackwardSearch", accP):
            foundPos = self.txtCtrl.executeIncrementalSearchBackward()
        elif accP in ((wx.ACCEL_NORMAL, wx.WXK_UP),
                (wx.ACCEL_NORMAL, wx.WXK_PAGEUP),
                (wx.ACCEL_NORMAL, wx.WXK_NUMPAD_UP),
                (wx.ACCEL_NORMAL, wx.WXK_NUMPAD_PAGEUP),
                (wx.ACCEL_NORMAL, wx.WXK_PRIOR)):
            foundPos = self.txtCtrl.executeIncrementalSearchBackward()
        elif matchesAccelPair("ActivateLink", accP):
            # ActivateLink is normally Ctrl-L
            self.Close()
            self.txtCtrl.activateLink()
        elif matchesAccelPair("ActivateLinkNewTab", accP):
            # ActivateLinkNewTab is normally Ctrl-Alt-L
            self.Close()
            self.txtCtrl.activateLink(tabMode=2)        
        elif matchesAccelPair("ActivateLink2", accP):
            # ActivateLink2 is normally Ctrl-Return
            self.Close()
            self.txtCtrl.activateLink()
        # handle the other keys
        else:
            evt.Skip()

        if foundPos == -1:
            # Nothing found
            self.tfInput.SetBackgroundColour(IncrementalSearchDialog.COLOR_YELLOW)
        elif foundPos >= 0:
            # Found
            self.tfInput.SetBackgroundColour(IncrementalSearchDialog.COLOR_GREEN)

        # Else don't change


    def OnTimerIncSearchClose(self, evt):
        self.Close()



etEVT_STYLE_DONE_COMMAND = wx.NewEventType()
EVT_STYLE_DONE_COMMAND = wx.PyEventBinder(etEVT_STYLE_DONE_COMMAND, 0)

class StyleDoneEvent(wx.PyCommandEvent):
    """
    This wx Event is fired when style and folding calculations are finished.
    It is needed to savely transfer data from the style thread to the main thread.
    """
    def __init__(self, stylebytes, foldingseq):
        wx.PyCommandEvent.__init__(self, etEVT_STYLE_DONE_COMMAND, -1)
        self.stylebytes = stylebytes
#         self.pageAst = pageAst
        self.foldingseq = foldingseq



class WikiTxtCtrl(wx.stc.StyledTextCtrl):
    NUMBER_MARGIN = 0
    FOLD_MARGIN = 2
    SELECT_MARGIN = 1

    def __init__(self, presenter, parent, ID):
        wx.stc.StyledTextCtrl.__init__(self, parent, ID, style=wx.WANTS_CHARS | wx.TE_PROCESS_ENTER)
        self.presenter = presenter
        self.evalScope = None
        self.stylingThreadHolder = ThreadHolder()
        self.clearStylingCache()
        self.pageType = "normal"   # The pagetype controls some special editor behaviour
#         self.idleCounter = 0       # Used to reduce idle load
#         self.loadedDocPage = None
        self.lastFont = None
        self.ignoreOnChange = False
        self.searchStr = u""

        # If autocompletion word was choosen, how many bytes to delete backward
        # before inserting word
        self.autoCompBackBytesMap = {} # Maps selected word to number of backbytes

        # configurable editor settings
        config = self.presenter.getConfig()
        self.setWrapMode(config.getboolean("main", "wrap_mode"))
        self.SetIndentationGuides(config.getboolean("main", "indentation_guides"))
        self.autoIndent = config.getboolean("main", "auto_indent")
        self.autoBullets = config.getboolean("main", "auto_bullets")
        self.setShowLineNumbers(config.getboolean("main", "show_lineNumbers"))
        self.foldingActive = config.getboolean("main", "editor_useFolding")
        self.tabsToSpaces = config.getboolean("main", "editor_tabsToSpaces")

        # editor settings
        self.applyBasicSciSettings()

        self.defaultFont = config.get("main", "font",
                self.presenter.getDefaultFontFaces()["mono"])

        self.CallTipSetForeground(wx.Colour(0, 0, 0))

        shorthintDelay = self.presenter.getConfig().getint("main",
                "editor_shortHint_delay", 500)
        self.SetMouseDwellTime(shorthintDelay)


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
        # for unicode build on Win 98/ME
        self.UsePopUp(0)

        self.SetMarginMask(self.FOLD_MARGIN, wx.stc.STC_MASK_FOLDERS)
        self.SetMarginMask(self.NUMBER_MARGIN, 0)
        self.SetMarginMask(self.SELECT_MARGIN, 0)

        if self.foldingActive:
            self.SetMarginWidth(self.FOLD_MARGIN, 16)
        else:
            self.SetMarginWidth(self.FOLD_MARGIN, 0)
        self.SetMarginWidth(self.SELECT_MARGIN, 16)
        self.SetMarginWidth(self.NUMBER_MARGIN, 0)
        
        self.SetMarginType(self.FOLD_MARGIN, wx.stc.STC_MARGIN_SYMBOL)
        self.SetMarginType(self.SELECT_MARGIN, wx.stc.STC_MARGIN_SYMBOL)
        self.SetMarginType(self.NUMBER_MARGIN, wx.stc.STC_MARGIN_NUMBER)

        # Optical details
        self.MarkerDefine(wx.stc.STC_MARKNUM_FOLDER, wx.stc.STC_MARK_PLUS)
        self.MarkerDefine(wx.stc.STC_MARKNUM_FOLDEROPEN, wx.stc.STC_MARK_MINUS)
        self.MarkerDefine(wx.stc.STC_MARKNUM_FOLDEREND, wx.stc.STC_MARK_EMPTY)
        self.MarkerDefine(wx.stc.STC_MARKNUM_FOLDERMIDTAIL, wx.stc.STC_MARK_EMPTY)
        self.MarkerDefine(wx.stc.STC_MARKNUM_FOLDEROPENMID, wx.stc.STC_MARK_EMPTY)
        self.MarkerDefine(wx.stc.STC_MARKNUM_FOLDERSUB, wx.stc.STC_MARK_EMPTY)
        self.MarkerDefine(wx.stc.STC_MARKNUM_FOLDERTAIL, wx.stc.STC_MARK_EMPTY)
        self.SetFoldFlags(16)

        self.SetMarginSensitive(self.FOLD_MARGIN, True)
        self.StyleSetSpec(wx.stc.STC_STYLE_DEFAULT, "face:%(mono)s,size:%(size)d" %
                self.presenter.getDefaultFontFaces())
                
#         self.setFoldingActive(self.foldingActive)

        for i in xrange(32):
            self.StyleSetEOLFilled(i, True)

        # i plan on lexing myself
        self.SetLexer(wx.stc.STC_LEX_CONTAINER)
        
        # make the text control a drop target for files and text
        self.SetDropTarget(WikiTxtCtrlDropTarget(self))
        
        # register some keyboard commands
        self.CmdKeyAssign(ord('+'), wx.stc.STC_SCMOD_CTRL, wx.stc.STC_CMD_ZOOMIN)
        self.CmdKeyAssign(ord('-'), wx.stc.STC_SCMOD_CTRL, wx.stc.STC_CMD_ZOOMOUT)
        self.CmdKeyAssign(wx.stc.STC_KEY_HOME, 0, wx.stc.STC_CMD_HOMEWRAP)
        self.CmdKeyAssign(wx.stc.STC_KEY_END, 0, wx.stc.STC_CMD_LINEENDWRAP)
        self.CmdKeyAssign(wx.stc.STC_KEY_HOME, wx.stc.STC_SCMOD_SHIFT,
                wx.stc.STC_CMD_HOMEWRAPEXTEND)
        self.CmdKeyAssign(wx.stc.STC_KEY_END, wx.stc.STC_SCMOD_SHIFT,
                wx.stc.STC_CMD_LINEENDWRAPEXTEND)


        # Clear all key mappings for clipboard operations
        # PersonalWikiFrame handles them and calls the special clipboard functions
        # instead of the normal ones
        self.CmdKeyClear(wx.stc.STC_KEY_INSERT, wx.stc.STC_SCMOD_CTRL)
        self.CmdKeyClear(wx.stc.STC_KEY_INSERT, wx.stc.STC_SCMOD_SHIFT)
        self.CmdKeyClear(wx.stc.STC_KEY_DELETE, wx.stc.STC_SCMOD_SHIFT)

        self.CmdKeyClear(ord('X'), wx.stc.STC_SCMOD_CTRL)
        self.CmdKeyClear(ord('C'), wx.stc.STC_SCMOD_CTRL)
        self.CmdKeyClear(ord('V'), wx.stc.STC_SCMOD_CTRL)
        
        self.SetModEventMask(
                wx.stc.STC_MOD_INSERTTEXT | wx.stc.STC_MOD_DELETETEXT)

        # set the autocomplete separator
        self.AutoCompSetSeparator(1)   # ord('~')

        # register some event handlers
        self.presenterListener = wxKeyFunctionSink((
#                 ("options changed", self.onOptionsChanged),  # fired by PersonalWikiFrame
                ("saving all pages", self.onSavingAllPages),
                ("closing current wiki", self.onClosingCurrentWiki),
                ("dropping current wiki", self.onDroppingCurrentWiki),
                ("reloaded current doc page", self.onReloadedCurrentPage)
        ), self.presenter.getMiscEvent())

        self.__sinkApp = wxKeyFunctionSink((
                ("options changed", self.onOptionsChanged),
        ), wx.GetApp().getMiscEvent(), self)

#         self.presenter.getMiscEvent().addListener(self.presenterListener)


        self.wikiPageSink = wxKeyFunctionSink((
                ("updated wiki page", self.onWikiPageUpdated),   # fired by a WikiPage
        ))


        wx.stc.EVT_STC_STYLENEEDED(self, ID, self.OnStyleNeeded)
        wx.stc.EVT_STC_CHARADDED(self, ID, self.OnCharAdded)
        wx.stc.EVT_STC_MODIFIED(self, ID, self.OnModified)
        wx.stc.EVT_STC_USERLISTSELECTION(self, ID, self.OnUserListSelection)
        wx.stc.EVT_STC_MARGINCLICK(self, ID, self.OnMarginClick)
        wx.stc.EVT_STC_DWELLSTART(self, ID, self.OnDwellStart)
        wx.stc.EVT_STC_DWELLEND(self, ID, self.OnDwellEnd)
        
        wx.EVT_LEFT_DOWN(self, self.OnClick)
        wx.EVT_MIDDLE_DOWN(self, self.OnMiddleDown)
        wx.EVT_LEFT_DCLICK(self, self.OnDoubleClick)
#         EVT_MOTION(self, self.OnMouseMove)
        # EVT_STC_DOUBLECLICK(self, ID, self.OnDoubleClick)
        wx.EVT_KEY_DOWN(self, self.OnKeyDown)
        wx.EVT_CHAR(self, self.OnChar)
        wx.EVT_SET_FOCUS(self, self.OnSetFocus)
        
        wx.EVT_IDLE(self, self.OnIdle)
        wx.EVT_CONTEXT_MENU(self, self.OnContextMenu)
        
        EVT_STYLE_DONE_COMMAND(self, self.OnStyleDone)

        # search related vars
#         self.inIncrementalSearch = False
#         self.anchorBytePosition = -1
#         self.anchorCharPosition = -1
        self.incSearchCharStartPos = 0

        self.onOptionsChanged(None)

        # when was a key pressed last. used to check idle time.
        self.lastKeyPressed = time()
        self.eolMode = self.GetEOLMode()

#         # Stock cursors. Created here because the App object must be created first
#         WikiTxtCtrl.CURSOR_IBEAM = wx.StockCursor(wx.CURSOR_IBEAM)
#         WikiTxtCtrl.CURSOR_HAND = wx.StockCursor(wx.CURSOR_HAND)

        self.contextMenuTokens = None
        
        # Connect context menu events to functions
        wx.EVT_MENU(self, GUI_ID.CMD_UNDO, lambda evt: self.Undo())
        wx.EVT_MENU(self, GUI_ID.CMD_REDO, lambda evt: self.Redo())

        wx.EVT_MENU(self, GUI_ID.CMD_CLIPBOARD_CUT, lambda evt: self.Cut())
        wx.EVT_MENU(self, GUI_ID.CMD_CLIPBOARD_COPY, lambda evt: self.Copy())
        wx.EVT_MENU(self, GUI_ID.CMD_CLIPBOARD_PASTE, lambda evt: self.Paste())
        wx.EVT_MENU(self, GUI_ID.CMD_TEXT_DELETE, lambda evt: self.ReplaceSelection(""))
        wx.EVT_MENU(self, GUI_ID.CMD_ZOOM_IN,
                lambda evt: self.CmdKeyExecute(wx.stc.STC_CMD_ZOOMIN))
        wx.EVT_MENU(self, GUI_ID.CMD_ZOOM_OUT,
                lambda evt: self.CmdKeyExecute(wx.stc.STC_CMD_ZOOMOUT))

        wx.EVT_MENU(self, GUI_ID.CMD_ACTIVATE_THIS, self.OnActivateThis)        
        wx.EVT_MENU(self, GUI_ID.CMD_ACTIVATE_NEW_TAB_THIS,
                self.OnActivateNewTabThis)        
        wx.EVT_MENU(self, GUI_ID.CMD_ACTIVATE_NEW_TAB_BACKGROUND_THIS,
                self.OnActivateNewTabBackgroundThis)        

        wx.EVT_MENU(self, GUI_ID.CMD_TEXT_SELECT_ALL, lambda evt: self.SelectAll())

#         wx.EVT_MENU(self, GUI_ID.CMD_UNFOLD_ALL_IN_CURRENT,
#                 lambda evt: self.unfoldAll())
#         wx.EVT_MENU(self, GUI_ID.CMD_FOLD_ALL_IN_CURRENT,
#                 lambda evt: self.foldAll())


    def getLoadedDocPage(self):
        return self.presenter.getDocPage()

    def close(self):
        """
        Close the editor (=prepare for destruction)
        """
        self.stylingThreadHolder.setThread(None)
        self.unloadCurrentDocPage({})   # ?
        self.presenterListener.disconnect()
#         self.presenter.getMiscEvent().removeListener(self.presenterListener)


    def Cut(self):
        self.Copy()
        self.ReplaceSelection("")

    def Copy(self):
        copyTextToClipboard(self.GetSelectedText())

    def Paste(self):
        text = getTextFromClipboard()
        if text:
            self.ReplaceSelection(text)
            return
        else:
            bmp = getBitmapFromClipboard()
            if bmp is not None:
                img = bmp.ConvertToImage()
                del bmp
                fs = self.presenter.getWikiDocument().getFileStorage()
                imgsav = ImagePasteSaver()
                imgsav.readOptionsFromConfig(self.presenter.getConfig())
                
                if self.presenter.getConfig().getboolean("main",
                        "editor_imagePaste_askOnEachPaste", True):
                    # Options say to present dialog on an image paste operation
                    dlg = ImagePasteDialog(self.presenter.getMainControl(), -1,
                            imgsav)
                    try:
                        dlg.ShowModal()
                        imgsav = dlg.getImagePasteSaver()
                    finally:
                        dlg.Destroy()

                destPath = imgsav.saveFile(fs, img)
                if destPath is None:
                    # Couldn't find unused filename or saving denied
                    return
                    
#                 destPath = fs.findDestPathNoSource(u".png", u"")
#                 
#                 print "Paste6", repr(destPath)
#                 if destPath is None:
#                     # Couldn't find unused filename
#                     return
# 
#                 img.SaveFile(destPath, wx.BITMAP_TYPE_PNG)

                locPath = self.presenter.getMainControl().getWikiConfigPath()

                if locPath is not None:
                    locPath = dirname(locPath)
                    relPath = relativeFilePath(locPath, destPath)
                    url = None
                    if relPath is None:
                        # Absolute path needed
                        url = "file:%s" % urlFromPathname(destPath)
                    else:
                        url = "rel://%s" % urlFromPathname(relPath)

                    if url:
                        self.ReplaceSelection(url)


    def onCmdCopy(self, miscevt):
        if wx.Window.FindFocus() != self:
            return
        self.Copy()
        
        
    def setLayerVisible(self, vis):
        """
        Informs the widget if it is really visible on the screen or not
        """
#         if vis:
#             self.Enable(True)
        self.Enable(vis)

    def setWrapMode(self, onOrOff):
        if onOrOff:
            self.SetWrapMode(wx.stc.STC_WRAP_WORD)
        else:
            self.SetWrapMode(wx.stc.STC_WRAP_NONE)

    def getWrapMode(self):
        return self.GetWrapMode() == wx.stc.STC_WRAP_WORD

    def setAutoIndent(self, onOff):
        self.autoIndent = onOff
        
    def getAutoIndent(self):
        return self.autoIndent

    def setAutoBullets(self, onOff):
        self.autoBullets = onOff
        
    def getAutoBullets(self):
        return self.autoBullets
        
    def setTabsToSpaces(self, onOff):
        self.tabsToSpaces = onOff
        self.SetUseTabs(not onOff)
        
    def getTabsToSpaces(self):
        return self.tabsToSpaces

    def setShowLineNumbers(self, onOrOff):
        if onOrOff:
            self.SetMarginWidth(self.NUMBER_MARGIN,
                    self.TextWidth(wx.stc.STC_STYLE_LINENUMBER, "_99999"))
            self.SetMarginWidth(self.SELECT_MARGIN, 0)
        else:
            self.SetMarginWidth(self.NUMBER_MARGIN, 0)
            self.SetMarginWidth(self.SELECT_MARGIN, 16)

    def getShowLineNumbers(self):
        return self.GetMarginWidth(self.NUMBER_MARGIN) != 0


    def setFoldingActive(self, onOrOff, forceSync=False):
        """
        forceSync -- when setting folding on, the folding is completed
            before function returns iff forceSync is True
        """ 
        if onOrOff:
            self.SetMarginWidth(self.FOLD_MARGIN, 16)
            self.foldingActive = True
            if forceSync:
                self.applyFolding(self.processFolding(
                        self.getPageAst().getTokens(), DUMBTHREADHOLDER))
            else:
                self.OnStyleNeeded(None)
        else:
            self.SetMarginWidth(self.FOLD_MARGIN, 0)
            self.unfoldAll()
            self.foldingActive = False
        
    def getFoldingActive(self):
        return self.foldingActive


    def SetStyles(self, styleFaces = None):
        # create the styles
        if styleFaces is None:
            styleFaces = self.presenter.getDefaultFontFaces()
            
        config = self.presenter.getConfig()
        for type, style in WikiFormatting.getStyles(styleFaces, config):
            self.StyleSetSpec(type, style)

    def SetText(self, text):
        """
        Overrides the wxStyledTextCtrl method.
        text -- Unicode text content to set
        """
        self.incSearchCharStartPos = 0
        self.clearStylingCache()
        self.pageType = "normal"

        self.SetSelection(-1, -1)
        self.ignoreOnChange = True
        if isUnicode():
            wx.stc.StyledTextCtrl.SetText(self, text)
        else:
            wx.stc.StyledTextCtrl.SetText(self, mbcsEnc(text, "replace")[0])
        self.ignoreOnChange = False
        self.EmptyUndoBuffer()
        # self.applyBasicSciSettings()


    def replaceText(self, text):
        if isUnicode():
            wx.stc.StyledTextCtrl.SetText(self, text)
        else:
            wx.stc.StyledTextCtrl.SetText(self, mbcsEnc(text, "replace")[0])


    def GetText_unicode(self):
        """
        Overrides the wxStyledTextCtrl.GetText method in ansi mode
        to return unicode.
        """
        return mbcsDec(wx.stc.StyledTextCtrl.GetText(self), "replace")[0]

    
    def GetTextRange_unicode(self, startPos, endPos):
        """
        Overrides the wxStyledTextCtrl.GetTextRange method in ansi mode
        to return unicode.
        startPos and endPos are byte(!) positions into the editor buffer
        """
        return mbcsDec(wx.stc.StyledTextCtrl.GetTextRange(self, startPos, endPos),
                "replace")[0]


    def GetSelectedText_unicode(self):
        """
        Overrides the wxStyledTextCtrl.GetSelectedText method in ansi mode
        to return unicode.
        """
        return mbcsDec(wx.stc.StyledTextCtrl.GetSelectedText(self), "replace")[0]


    def GetLine_unicode(self, line):
        return mbcsDec(wx.stc.StyledTextCtrl.GetLine(self, line), "replace")[0]


    def ReplaceSelection_unicode(self, txt):
        return wx.stc.StyledTextCtrl.ReplaceSelection(self, mbcsEnc(txt, "replace")[0])


    def AddText_unicode(self, txt):
        return wx.stc.StyledTextCtrl.AddText(self, mbcsEnc(txt, "replace")[0])


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


    def gotoCharPos(self, pos):
        # Go to the end and back again, so the anchor is
        # near the top
        self.SetSelection(-1, -1)
        self.GotoPos(self.GetLength())
        self.GotoPos(self.bytelenSct(self.GetText()[:pos]))

        # self.SetSelectionByCharPos(pos, pos)


    def applyBasicSciSettings(self):
        """
        Apply the basic Scintilla settings which are resetted to wrong
        default values by some operations
        """
        if isUnicode():
            self.SetCodePage(wx.stc.STC_CP_UTF8)
        self.SetIndent(4)
        self.SetTabIndents(True)
        self.SetBackSpaceUnIndents(True)
        self.SetTabWidth(4)
        self.SetUseTabs(not self.tabsToSpaces)
        self.SetEOLMode(wx.stc.STC_EOL_LF)
        self.AutoCompSetFillUps(u":=")  # TODO Add '.'?
#         self.SetYCaretPolicy(wxSTC_CARET_SLOP, 2)  
#         self.SetYCaretPolicy(wxSTC_CARET_JUMPS | wxSTC_CARET_EVEN, 4)  
        self.SetYCaretPolicy(wx.stc.STC_CARET_SLOP | wx.stc.STC_CARET_EVEN, 4) 



    def saveLoadedDocPage(self):
        """
        Save loaded wiki page into database. Does not check if dirty
        """
        if self.getLoadedDocPage() is None:
            return

        page = self.getLoadedDocPage()

#         if not self.loadedDocPage.getDirty()[0]:
#             return

        text = self.GetText()
        if self.presenter.getMainControl().\
                saveDocPage(page, text, self.getPageAst()):
            self.SetSavePoint()

        
    def unloadCurrentDocPage(self, evtprops=None):
        ## _prof.start()
        # Unload current page
        docPage = self.getLoadedDocPage()
        if docPage is not None:
            wikiWord = docPage.getWikiWord()
            if wikiWord is not None:
                docPage.setPresentation((self.GetCurrentPos(),
                        self.GetScrollPos(wx.HORIZONTAL),
                        self.GetScrollPos(wx.VERTICAL)), 0)
                docPage.setPresentation((self.getFoldInfo(),), 5)

            if docPage.getDirty()[0]:
                self.saveLoadedDocPage()

            self.wikiPageSink.disconnect()
            
            self.SetDocPointer(None)
            self.applyBasicSciSettings()

            docPage.removeTxtEditor(self)
            self.presenter.setDocPage(None)

            self.clearStylingCache()
#             self.stylebytes = None
#             self.foldingseq = None
#             self.pageAst = None
            self.pageType = "normal"
        
        ## _prof.stop()


    def loadFuncPage(self, funcPage, evtprops=None):
        self.unloadCurrentDocPage(evtprops)
        # set the editor text
        content = None
        wikiDataManager = self.presenter.getWikiDocument()
        
        self.presenter.setDocPage(funcPage)
        
        if self.getLoadedDocPage() is None:
            return  # TODO How to handle?

        globalProps = wikiDataManager.getWikiData().getGlobalProperties()
        # get the font that should be used in the editor
        font = globalProps.get("global.font", self.defaultFont)

        # set the styles in the editor to the font
        if self.lastFont != font:
            faces = self.presenter.getDefaultFontFaces().copy()
            faces["mono"] = font
            self.SetStyles(faces)
            self.lastEditorFont = font

#         p2 = evtprops.copy()
#         p2.update({"loading current page": True})
#         self.pWiki.fireMiscEventProps(p2)  # TODO Remove this hack

        self.wikiPageSink.setEventSource(self.getLoadedDocPage().getMiscEvent())

        otherEditor = self.getLoadedDocPage().getTxtEditor()
        if otherEditor is not None:
            # Another editor contains already this page, so share its
            # Scintilla document object for synchronized editing
            self.SetDocPointer(otherEditor.GetDocPointer())
            self.applyBasicSciSettings()
        else:
            # Load content
            try:
                content = self.getLoadedDocPage().getLiveText()
            except WikiFileNotFoundException, e:
                assert 0   # TODO

            # now fill the text into the editor
            self.SetText(content)

        self.getLoadedDocPage().addTxtEditor(self)
        self._checkForReadOnly()
        self.presenter.setTitle(self.getLoadedDocPage().getTitle())


    def loadWikiPage(self, wikiPage, evtprops=None):
        """
        Save loaded page, if necessary, then load wikiPage into editor
        """
        self.unloadCurrentDocPage(evtprops)        
        # set the editor text
        wikiDataManager = self.presenter.getWikiDocument()
        
        self.presenter.setDocPage(wikiPage)

        if self.getLoadedDocPage() is None:
            return  # TODO How to handle?

        # get the font that should be used in the editor
        font = self.getLoadedDocPage().getPropertyOrGlobal("font",
                self.defaultFont)
        
        # set the styles in the editor to the font
        if self.lastFont != font:
            faces = self.presenter.getDefaultFontFaces().copy()
            faces["mono"] = font
            self.SetStyles(faces)
            self.lastEditorFont = font

        self.wikiPageSink.setEventSource(self.getLoadedDocPage().getMiscEvent())

        otherEditor = self.getLoadedDocPage().getTxtEditor()
        if otherEditor is not None:
            # Another editor contains already this page, so share its
            # Scintilla document object for synchronized editing
            self.SetDocPointer(otherEditor.GetDocPointer())
            self.applyBasicSciSettings()
        else:
            # Load content
            try:
                content = self.getLoadedDocPage().getLiveText()
            except WikiFileNotFoundException, e:
                assert 0   # TODO

            # now fill the text into the editor
            self.setTextAgaUpdated(content)

        self.getLoadedDocPage().addTxtEditor(self)
        self._checkForReadOnly()

        if evtprops is None:
            evtprops = {}
        p2 = evtprops.copy()
        p2.update({"loading wiki page": True, "wikiPage": wikiPage})
        self.presenter.fireMiscEventProps(p2)  # TODO Remove this hack
        
        self.pageType = self.getLoadedDocPage().getProperties().get(u"pagetype",
                [u"normal"])[-1]

        if self.pageType == u"normal":
            if not self.getLoadedDocPage().isDefined():
                # This is a new, not yet defined page, so go to the end of page
                self.GotoPos(self.GetLength())
            else:
                anchor = evtprops.get("anchor")
                if anchor:
                    # Scroll page according to the anchor
                    pageAst = self.getPageAst()

                    anchorTokens = pageAst.findTypeFlat(WikiFormatting.FormatTypes.Anchor)
                    for t in anchorTokens:
                        if t.grpdict["anchorValue"] == anchor:
                            self.gotoCharPos(t.start + t.getRealLength())
#                             # Go to the end and back again, so the anchor is
#                             # near the top
#                             self.GotoPos(self.GetLength())
#                             self.SetSelectionByCharPos(
#                                     t.start + t.getRealLength(),
#                                     t.start + t.getRealLength())
                            break
                    else:
                        anchor = None # Not found

                if not anchor:
                    # see if there is a saved position for this page
                    prst = self.getLoadedDocPage().getPresentation()
                    lastPos, scrollPosX, scrollPosY = prst[0:3]
                    foldInfo = prst[5]
                    self.setFoldInfo(foldInfo)
                    self.GotoPos(lastPos)
                    
                    if True:  # scrollPosX != 0 or scrollPosY != 0:
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

        elif self.pageType == u"form":
            self.GotoPos(0)
            self._goToNextFormField()
        else:
            pass   # TODO Error message?

        self.presenter.setTitle(self.getLoadedDocPage().getTitle())


    def onReloadedCurrentPage(self, miscevt):
        """
        Called when already loaded page should be loaded again, mainly
        interesting if a link with anchor is activated
        """
        if not self.presenter.isCurrent():
            return

        anchor = miscevt.get("anchor")
        if not anchor:
            return

        if not self.getLoadedDocPage().isDefined():
            return

        if self.pageType == u"normal":
            # Scroll page according to the anchor
            pageAst = self.getPageAst()

            anchorTokens = pageAst.findTypeFlat(WikiFormatting.FormatTypes.Anchor)
            for t in anchorTokens:
                if t.grpdict["anchorValue"] == anchor:
                    # Go to the end and back again, so the anchor is
                    # near the top
                    self.GotoPos(self.GetLength())
                    self.SetSelectionByCharPos(
                            t.start + t.getRealLength(),
                            t.start + t.getRealLength())
                    break
            else:
                anchor = None # Not found
                
    def _checkForReadOnly(self):
        """
        Set/unset read-only mode of editor according to read-only state of page.
        """
        docPage = self.getLoadedDocPage()
        if docPage is None:
            self.SetReadOnly(True)
        else:
            self.SetReadOnly(docPage.isReadOnlyEffect())


    def _getColorFromOption(self, option, defColTuple):
        """
        Helper for onOptionsChanged() to read a color from an option
        and create a wx.Colour object from it.
        """
        coltuple = htmlColorToRgbTuple(self.presenter.getConfig().get(
                "main", option))

        if coltuple is None:
            coltuple = defColTuple

        return wx.Colour(*coltuple)



    def onOptionsChanged(self, miscevt):
        faces = self.presenter.getDefaultFontFaces().copy()

        if isinstance(self.getLoadedDocPage(), 
                (DocPages.WikiPage, DocPages.AliasWikiPage)):

            font = self.getLoadedDocPage().getPropertyOrGlobal("font",
                    self.defaultFont)
            faces["mono"] = font
            self.lastEditorFont = font    # ???

        self.SetStyles(faces)
        
        color = self._getColorFromOption("editor_bg_color", (255, 255, 255))

#         coltuple = htmlColorToRgbTuple(self.presenter.getConfig().get(
#                 "main", "editor_bg_color"))
# 
#         if coltuple is None:
#             coltuple = (255, 255, 255)
# 
#         color = wx.Colour(*coltuple)

        for i in xrange(32):
            self.StyleSetBackground(i, color)
        self.StyleSetBackground(wx.stc.STC_STYLE_DEFAULT, color)
            
        self.SetSelForeground(True, self._getColorFromOption(
                "editor_selection_fg_color", (0, 0, 0)))
        self.SetSelBackground(True, self._getColorFromOption(
                "editor_selection_bg_color", (192, 192, 192)))
        self.SetCaretForeground(self._getColorFromOption(
                "editor_caret_color", (0, 0, 0)))
        # Set default color (especially for folding lines)
        self.StyleSetForeground(wx.stc.STC_STYLE_DEFAULT, self._getColorFromOption(
                "editor_plaintext_color", (0, 0, 0)))

        shorthintDelay = self.presenter.getConfig().getint("main",
                "editor_shortHint_delay", 500)
        self.SetMouseDwellTime(shorthintDelay)


    def onWikiPageUpdated(self, miscevt):
        if self.getLoadedDocPage() is None or \
                not isinstance(self.getLoadedDocPage(),
                (DocPages.WikiPage, DocPages.AliasWikiPage)):
            return

        # get the font that should be used in the editor
        font = self.getLoadedDocPage().getPropertyOrGlobal("font",
                self.defaultFont)

        # set the styles in the editor to the font
        if self.lastFont != font:
            faces = self.presenter.getDefaultFontFaces().copy()
            faces["mono"] = font
            self.SetStyles(faces)
            self.lastEditorFont = font

        self.pageType = self.getLoadedDocPage().getProperties().get(u"pagetype",
                [u"normal"])[-1]


    def onSavingAllPages(self, miscevt):
        if self.getLoadedDocPage() is not None and (
                self.getLoadedDocPage().getDirty()[0] or miscevt.get("force", False)):
            self.saveLoadedDocPage()

    def onClosingCurrentWiki(self, miscevt):
        self.unloadCurrentDocPage()

    def onDroppingCurrentWiki(self, miscevt):
        """
        An access error occurred. Get rid of any data without trying to save
        it.
        """
        if self.getLoadedDocPage() is not None:
            self.wikiPageSink.disconnect()
            
            self.SetDocPointer(None)
            self.applyBasicSciSettings()

            self.getLoadedDocPage().removeTxtEditor(self)
            self.presenter.setDocPage(None)
#             self.loadedDocPage = None
            self.pageType = "normal"


    def OnStyleNeeded(self, evt):
        "Styles the text of the editor"

        docPage = self.getLoadedDocPage()
        if docPage is None:
            # This avoids further request from STC:
            self.stopStcStyler()
            return

        # get the text to regex against (use doc pages getLiveText because
        # it's cached
        text = docPage.getLiveText()  # self.GetText()
        textlen = len(text)

        t = self.stylingThreadHolder.getThread()
        if t is not None:
            self.stylingThreadHolder.setThread(None)
            self.clearStylingCache()
#             self.stylebytes = None
#             self.foldingseq = None
#             self.pageAst = None

        if textlen < self.presenter.getConfig().getint(
                "main", "sync_highlight_byte_limit"):
            # Synchronous styling
            self.stylingThreadHolder.setThread(None)
            self.buildStyling(text, 0, threadholder=DUMBTHREADHOLDER)

            self.applyStyling(self.stylebytes)   # TODO Necessary?
            # We can't call applyFolding directly because this in turn
            # calls repairFoldingVisibility which can't work while in
            # EVT_STC_STYLENEEDED event (at least for wxPython 2.6.2)
            # storeStylingAndAst() sends a StyleDoneEvent instead
            if self.getFoldingActive():
#                 self.applyFolding(self.foldingseq)
                self.storeStylingAndAst(None, self.foldingseq)
        else:
            # Asynchronous styling
            # This avoids further request from STC:
            self.stopStcStyler()
#             self.StartStyling(self.GetLength(), 0xff)  # len(text) may be != self.GetLength()
#             self.SetStyling(0, 0)

            sth = self.stylingThreadHolder
            
            delay = self.presenter.getConfig().getfloat(
                    "main", "async_highlight_delay")
            t = threading.Thread(None, self.buildStyling, args = (text, delay, sth))
            sth.setThread(t)
            t.start()


    # TODO Wrong reaction on press of context menu button on keyboard
    def OnContextMenu(self, evt):
        mousePos = self.ScreenToClient(wx.GetMousePosition())
        
        leftFold = 0
        for i in range(self.FOLD_MARGIN):
            leftFold += self.GetMarginWidth(i)
            
        rightFold = leftFold + self.GetMarginWidth(self.FOLD_MARGIN)

        menu = wx.Menu()

        if mousePos.x >= leftFold and mousePos.x < rightFold:
            # Right click in fold margin

            appendToMenuByMenuDesc(menu, FOLD_MENU)

            # print "Right click in fold margin"
        else:
            appendToMenuByMenuDesc(menu, _CONTEXT_MENU_INTEXT_BASE)
            
            tokens = self.getTokensForMousePos(mousePos)
            
            self.contextMenuTokens = tokens
            addActivateItem = False
            for tok in tokens:
                if tok.ttype == WikiFormatting.FormatTypes.WikiWord:
                    addActivateItem = True
                elif tok.ttype == WikiFormatting.FormatTypes.Url:
                    addActivateItem = True
                elif tok.ttype == WikiFormatting.FormatTypes.Insertion and \
                        tok.node.key == u"page":
                    addActivateItem = True
                    
            if addActivateItem:
                appendToMenuByMenuDesc(menu, _CONTEXT_MENU_INTEXT_ACTIVATE)
    
            appendToMenuByMenuDesc(menu, _CONTEXT_MENU_INTEXT_BOTTOM)
    
            # Enable/Disable appropriate menu items
            item = menu.FindItemById(GUI_ID.CMD_UNDO)
            if item: item.Enable(self.CanUndo())
            item = menu.FindItemById(GUI_ID.CMD_REDO)
            if item: item.Enable(self.CanRedo())
    
            cancopy = self.GetSelectionStart() != self.GetSelectionEnd()
            
            item = menu.FindItemById(GUI_ID.CMD_TEXT_DELETE)
            if item: item.Enable(cancopy and not self.GetReadOnly())
            item = menu.FindItemById(GUI_ID.CMD_CLIPBOARD_CUT)
            if item: item.Enable(cancopy and not self.GetReadOnly())
            item = menu.FindItemById(GUI_ID.CMD_CLIPBOARD_COPY)
            if item: item.Enable(cancopy)
            item = menu.FindItemById(GUI_ID.CMD_CLIPBOARD_PASTE)
            if item: item.Enable(self.CanPaste())


        # Show menu
        self.PopupMenu(menu)
        self.contextMenuTokens = None
        menu.Destroy()


    def _goToNextFormField(self):
        """
        If pagetype is "form" this is called when user presses TAB in
        text editor and after loading a form page
        """
        searchOp = SearchReplaceOperation()
        searchOp.wikiWide = False
        searchOp.wildCard = 'regex'
        searchOp.caseSensitive = True
        searchOp.searchStr = "&&[a-zA-Z]"

        text = self.GetText()
        charStartPos = len(self.GetTextRange(0, self.GetSelectionEnd()))
        while True:
            start, end = searchOp.searchText(text, charStartPos)[:2]
            if start is None: break

            fieldcode = text[start + 2]
            if fieldcode == "i":
                self.SetSelectionByCharPos(start, end)
                break

            charStartPos = end


    def clearStylingCache(self):
        self.stylebytes = None
        self.foldingseq = None
#         self.pageAst = None


    def stopStcStyler(self):
        """
        Stops further styling requests from Scintilla until text is modified
        """
        self.StartStyling(self.GetLength(), 0xff)
        self.SetStyling(0, 0)



    def storeStylingAndAst(self, stylebytes, foldingseq):
        self.stylebytes = stylebytes
#         self.pageAst = pageAst
        self.foldingseq = foldingseq
        
        self.AddPendingEvent(StyleDoneEvent(stylebytes, foldingseq))


    def buildStyling(self, text, delay, threadholder=DUMBTHREADHOLDER):
        if delay != 0:  # not threadholder is DUMBTHREADHOLDER:
            sleep(delay)
            if not threadholder.isCurrent():
                return

#         page = PageAst.Page()
#         page.buildAst(self.presenter.getFormatting(), text,
#                 self.getLoadedDocPage().getFormatDetails(), threadholder=threadholder)
        docPage = self.getLoadedDocPage()
        if docPage is None:
            return

        pageAst = docPage.getLivePageAst(text, threadholder)
        if not threadholder.isCurrent():
            return

        stylebytes = self.processTokens(pageAst.getTokens(), threadholder)
        if not threadholder.isCurrent():
            return

        if self.getFoldingActive():
            foldingseq = self.processFolding(pageAst.getTokens(), threadholder)
        else:
            foldingseq = None

        if threadholder.isCurrent():
            self.storeStylingAndAst(stylebytes, foldingseq)


    def processTokens(self, tokens, threadholder):
        wikiData = self.presenter.getWikiDocument().getWikiData()
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

            elif styleno == WikiFormatting.FormatTypes.Insertion:
                styleno = WikiFormatting.FormatTypes.Script
            elif styleno == WikiFormatting.FormatTypes.Anchor:
                styleno = WikiFormatting.FormatTypes.Bold
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

            elif styleno in WikiFormatting.ADDITIONAL_HEADING_STYLES:
                styleno = WikiFormatting.FormatTypes.Heading4
            elif styleno not in WikiFormatting.VALID_SCINTILLA_STYLES:
                # Style is not known to Scintilla, so use default instead
                styleno = WikiFormatting.FormatTypes.Default

            if styleno != -1:
                stylebytes.append(chr(styleno) * bytestylelen)
                

        return "".join(stylebytes)


    def processFolding(self, tokens, threadholder):
#         wikiData = self.presenter.getWikiDocument().getWikiData()
        foldingseq = []
        currLine = 0
        prevLevel = 0
        levelStack = []
        foldHeader = False
        
        for tok in tokens:
            if not threadholder.isCurrent():
                return None
                
            styleno = tok.ttype
            headLevel = WikiFormatting.getHeadingLevel(styleno)
            if headLevel > 0:
                while levelStack and (levelStack[-1][0] != "heading" or
                        levelStack[-1][1] > headLevel):
                    del levelStack[-1]
                if not levelStack or levelStack[-1] != ("heading", headLevel):
                    levelStack.append(("heading", headLevel))
                foldHeader = True

            lfc = tok.text.count(u"\n")
            if len(levelStack) > prevLevel:
                foldHeader = True

            if foldHeader and lfc > 0:
                foldingseq.append(len(levelStack) | wx.stc.STC_FOLDLEVELHEADERFLAG)
                foldHeader = False
                lfc -= 1

            if lfc > 0:
                foldingseq += [len(levelStack) + 1] * lfc
                
            prevLevel = len(levelStack) + 1
                
        # final line
        foldingseq.append(len(levelStack) + 1)
        
        return foldingseq


    def applyStyling(self, stylebytes):
        if len(stylebytes) == self.GetLength():
            self.StartStyling(0, 0xff)
            self.SetStyleBytes(len(stylebytes), stylebytes)

    def applyFolding(self, foldingseq):
        if foldingseq and self.getFoldingActive() and \
                len(foldingseq) == self.GetLineCount():
            for ln in xrange(len(foldingseq)):
                self.SetFoldLevel(ln, foldingseq[ln])
            self.repairFoldingVisibility()


    def unfoldAll(self):
        """
        Unfold all folded lines
        """
        for i in xrange(self.GetLineCount()):
            self.SetFoldExpanded(i, True)
        
        self.ShowLines(0, self.GetLineCount()-1)


    def foldAll(self):
        """
        Fold all foldable lines
        """
        if not self.getFoldingActive():
            self.setFoldingActive(True, forceSync=True)

        for ln in xrange(self.GetLineCount()):
            if self.GetFoldLevel(ln) & wx.stc.STC_FOLDLEVELHEADERFLAG and \
                    self.GetFoldExpanded(ln):
                self.ToggleFold(ln)
#                 self.SetFoldExpanded(ln, False)
#             else:
#                 self.HideLines(ln, ln)

        self.Refresh()


    def toggleCurrentFolding(self):
        if not self.getFoldingActive():
            return

        self.ToggleFold(self.LineFromPosition(self.GetCurrentPos()))


    def getFoldInfo(self):
        if not self.getFoldingActive():
            return None

        result = [0] * self.GetLineCount()
        for ln in xrange(self.GetLineCount()):
            levComb = self.GetFoldLevel(ln)
            levOut = levComb & 4095
            if levComb & wx.stc.STC_FOLDLEVELHEADERFLAG:
                levOut |= 4096
            if self.GetFoldExpanded(ln):
                levOut |= 8192
            if self.GetLineVisible(ln):
                levOut |= 16384            
            result[ln] = levOut
            
        return result


    def setFoldInfo(self, fldInfo):
        if fldInfo is None or \
                not self.getFoldingActive() or \
                len(fldInfo) != self.GetLineCount():
            return

        for ln, levIn in enumerate(fldInfo):
            levComb = levIn & 4095
            if levIn & 4096:
                levComb |= wx.stc.STC_FOLDLEVELHEADERFLAG
                
            self.SetFoldLevel(ln, levComb)
            self.SetFoldExpanded(ln, bool(levIn & 8192))
            if levIn & 16384:
                self.ShowLines(ln, ln)
            else:
                self.HideLines(ln, ln)
        
        self.repairFoldingVisibility()



    def repairFoldingVisibility(self):
        if not self.getFoldingActive():
            return
            
        lc = self.GetLineCount()
        
        if lc == 0:
            return

        self.ShowLines(0, 0)
        if lc == 1:
            return
            
        combLevel = self.GetFoldLevel(0)
        prevLevel = combLevel & 4095
        prevIsHeader = combLevel & wx.stc.STC_FOLDLEVELHEADERFLAG
        prevIsExpanded = self.GetFoldExpanded(0)
        prevVisible = True  # First line must always be visible
        prevLn = 0
        
#         print "0", prevLevel, bool(prevIsHeader), bool(prevIsExpanded), bool(prevVisible)

        for ln in xrange(1, lc):
            combLevel = self.GetFoldLevel(ln)
            level = combLevel & 4095
            isHeader = combLevel & wx.stc.STC_FOLDLEVELHEADERFLAG
            isExpanded = self.GetFoldExpanded(ln)
            visible = self.GetLineVisible(ln)
#             print ln, level, bool(isHeader), bool(isExpanded), bool(visible)

            if prevVisible and not visible:
                # Previous line visible, current not -> check if we must show it
                if ((level <= prevLevel) and \
                            not (prevIsHeader and not prevIsExpanded)) or \
                        (prevIsHeader and prevIsExpanded):
                    # if current level is not larger than previous this indicates
                    # an error except that the previous line is a header line and 
                    # folded (not expanded).
                    # Other possibility of an error is if previous line is a
                    # header and IS expanded.
                    
                    # Show line in these cases
                    self.SetFoldExpanded(prevLn, True) # Needed?
                    self.ShowLines(ln, ln)
                    # self.EnsureVisible(ln)
                    visible = True

            prevLevel = level
            prevIsHeader = isHeader
            prevIsExpanded = isExpanded
            prevVisible = visible
            prevLn = ln




    def snip(self):
        # get the selected text
        text = self.GetSelectedText()

        # copy it to the clipboard also
        self.Copy()

        wikiPage = self.presenter.getWikiDocument().getWikiPageNoError("ScratchPad")
        
        wikiPage.appendLiveText("\n%s\n---------------------------\n\n%s\n" %
                (mbcsDec(strftime("%x %I:%M %p"), "replace")[0], text))

        # TODO strftime

    def styleSelection(self, styleChars):
        """
        Currently len(styleChars) must be 1.
        """
        (startBytePos, endBytePos) = self.GetSelection()
        if startBytePos == endBytePos:
            (startBytePos, endBytePos) = self.getNearestWordPositions()
            
        emptySelection = startBytePos == endBytePos  # is selection empty

        self.BeginUndoAction()
        try:
            self.GotoPos(startBytePos)
            self.AddText(styleChars)
    
            for i in xrange(len(styleChars)):
                endBytePos = self.PositionAfter(endBytePos)
    
            self.GotoPos(endBytePos)
            self.AddText(styleChars)
    
            bytePos = endBytePos
            
            if not emptySelection:
                # Cursor will in the end stand after styled word
                # if selection is empty, it will stand between the style characters
                for i in xrange(len(styleChars)):
                    bytePos = self.PositionAfter(bytePos)
    
            self.GotoPos(bytePos)
        finally:
            self.EndUndoAction()
            

#     def getCachedPageAst(self):
#         """
#         Returns cached page ast or None if currently not cached
#         """
#         return self.pageAst

    def getPageAst(self):
        docPage = self.getLoadedDocPage()
        if docPage is None:
            return None
        
        return docPage.getLivePageAst()

#         page = self.pageAst
#         if page is None:
#             t = self.stylingThreadHolder.getThread()
#             if t is not None:
#                 t.join()
#                 page = self.pageAst
#         
#         if page is None:
#             page = PageAst.Page()
#             self.pageAst = page
#             page.buildAst(self.presenter.getFormatting(), self.GetText(),
#                     self.getLoadedDocPage().getFormatDetails())
#         
#         return page


    def activateTokens(self, tokens, tabMode=0):
        """
        Helper for activateLink()
        tabMode -- 0:Same tab; 2: new tab in foreground; 3: new tab in background
        """
        if len(tokens) == 0:
            return False

        for tok in tokens:
            if tok.ttype == WikiFormatting.FormatTypes.WikiWord:
                searchStr = None
    
                # open the wiki page
                if tabMode & 2:
                    # New tab
                    presenter = self.presenter.getMainControl().\
                            createNewDocPagePresenterTab()
                else:
                    # Same tab
                    presenter = self.presenter
                    
                titleFromLink = self.presenter.getConfig().getboolean("main",
                        "wikiPageTitle_fromLinkTitle", False)
                
                if not titleFromLink or tok.node.titleTokens is None:
                    suggNewPageTitle = None
                else:
                    suggNewPageTitle = PageAst.getTextFromTokenList(
                            tok.node.titleTokens)

                presenter.openWikiPage(tok.node.nakedWord,   # .getMainControl()
                        motionType="child", anchor=tok.node.anchorFragment,
                        suggNewPageTitle=suggNewPageTitle)

                searchfrag = tok.node.searchFragment
                # Unescape search fragment
                if searchfrag is not None:
                    searchfrag = presenter.getFormatting().\
                            SearchFragmentUnescapeRE.sub(ur"\1", searchfrag)
                    searchOp = SearchReplaceOperation()
                    searchOp.wildCard = "no"   # TODO Why not regex?
                    searchOp.searchStr = searchfrag
    
                    presenter.getSubControl("textedit").executeSearch(
                            searchOp, 0)
                
                if not tabMode & 1:
                    # Show in foreground
                    presenter.getMainControl().getMainAreaPanel().\
                            showDocPagePresenter(presenter)

                return True

            elif tok.ttype == WikiFormatting.FormatTypes.Url:
                self.presenter.getMainControl().launchUrl(tok.node.url)
                return True

            elif tok.ttype == WikiFormatting.FormatTypes.Insertion and \
                    tok.node.key == u"page":
                        
                # open the wiki page
                if tabMode & 2:
                    # New tab
                    presenter = self.presenter.getMainControl().\
                            createNewDocPagePresenterTab()
                else:
                    # Same tab
                    presenter = self.presenter

                presenter.openWikiPage(tok.node.value,   # .getMainControl()
                        motionType="child", anchor=tok.node.value)

                if not tabMode & 1:
                    # Show in foreground
                    presenter.getMainControl().getMainAreaPanel().\
                            showDocPagePresenter(presenter)

                return True
            elif tok.ttype == WikiFormatting.FormatTypes.Footnote:
                pageAst = self.getPageAst()
                footnoteId = tok.grpdict["footnoteId"]

                anchorTok = pageAst.getFootnoteAnchorDict().get(footnoteId)
                if anchorTok is not None:
                    if anchorTok.start != tok.start:
                        # Activated footnote was not last -> go to last
                        self.gotoCharPos(anchorTok.start)
                    else:
                        # Activated footnote was last -> go to first
                        fnTokens = pageAst.findType(
                                WikiFormatting.FormatTypes.Footnote)

                        for ft in fnTokens:
                            if ft.grpdict["footnoteId"] == footnoteId:
                                self.gotoCharPos(ft.start)
                                break

                return True
            else:
                continue

        return False


    def getTokensForMousePos(self, mousePosition=None):
        # mouse position overrides current pos
        if mousePosition and mousePosition != wx.DefaultPosition:
            linkPos = self.PositionFromPoint(mousePosition)
        else:
            linkPos = self.GetCurrentPos()

        pageAst = self.getPageAst()
        linkCharPos = len(self.GetTextRange(0, linkPos))

        result = pageAst.getTokensForPos(linkCharPos)

        if linkCharPos > 0:
            # Maybe a token left to the cursor was meant, so check
            # one char to the left
            result += pageAst.getTokensForPos(linkCharPos - 1)
            
        return result


    def activateLink(self, mousePosition=None, tabMode=0):
        """
        Activates link (wiki word or URL)
        tabMode -- 0:Same tab; 2: new tab in foreground; 3: new tab in background
        """
        tokens = self.getTokensForMousePos(mousePosition)
        return self.activateTokens(tokens, tabMode)


    def OnActivateThis(self, evt):
        if self.contextMenuTokens:
            self.activateTokens(self.contextMenuTokens, 0)

    def OnActivateNewTabThis(self, evt):
        if self.contextMenuTokens:
            self.activateTokens(self.contextMenuTokens, 2)

    def OnActivateNewTabBackgroundThis(self, evt):
        if self.contextMenuTokens:
            self.activateTokens(self.contextMenuTokens, 3)


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


    # TODO More efficient
    def evalScriptBlocks(self, index=-1):
        """
        Evaluates scripts. Respects "script_security_level" option
        """
        securityLevel = self.presenter.getConfig().getint(
                "main", "script_security_level")
        if securityLevel == 0:
            # No scripts allowed
            # Print warning message
            wx.MessageBox(u"Set in options, page \"Security\", \n"
                    "item \"Script security\" an appropriate value \n"
                    "to execute a script", u"Script execution disabled",
                    wx.OK, self.presenter.getMainControl())
            return

        SCRIPTFORMAT = WikiFormatting.FormatTypes.Script
        # it is important to python to have consistent eol's
        self.ConvertEOLs(self.eolMode)
        (startPos, endPos) = self.GetSelection()

        # if no selection eval all scripts
        if startPos == endPos or index > -1:
            # Execute all or selected script blocks on the page (or other
            #   related pages)
            
            pageAst = self.getPageAst()
            scriptTokens = pageAst.findTypeFlat(SCRIPTFORMAT)

#             # get the text of the current page
#             text = self.GetText()
            
            # process script imports
            if securityLevel > 1: # Local import_scripts properties allowed
                if self.getLoadedDocPage().getProperties().has_key(
                        "import_scripts"):
                    scriptNames = self.getLoadedDocPage().getProperties()[
                            "import_scripts"]
                    for sn in scriptNames:
                        try:
                            importPage = self.presenter.getWikiDocument().\
                                    getWikiPage(sn)
                            pageAst = importPage.getLivePageAst()
                            scriptTokens += pageAst.findTypeFlat(SCRIPTFORMAT)
                            
#                             content = importPage.getLiveText()
#                             text += "\n" + content
                        except:
                            pass

            if securityLevel > 2: # global.import_scripts property also allowed
                globScriptName = self.presenter.getWikiDocument().getWikiData().\
                        getGlobalProperties().get("global.import_scripts")
    
                if globScriptName is not None:
                    try:
                        importPage = self.presenter.getWikiDocument().\
                                getWikiPage(globScriptName)
                        pageAst = importPage.getLivePageAst()
                        scriptTokens += pageAst.findTypeFlat(SCRIPTFORMAT)
#                         content = importPage.getLiveText()
#                         text += "\n" + content
                    except:
                        pass

            for st in scriptTokens:
                script = st.grpdict["scriptContent"]
                script = re.sub(u"^[\r\n\s]+", u"", script)
                script = re.sub(u"[\r\n\s]+$", u"", script)
                try:
                    if index == -1:
                        script = re.sub(u"^\d:?\s?", u"", script)
                        exec(script) in self.evalScope
                    elif index > -1 and script.startswith(str(index)):
                        script = re.sub(u"^\d:?\s?", u"", script)
                        exec(script) in self.evalScope
                        break # Execute only the first found script

                except Exception, e:
                    s = StringIO()
                    traceback.print_exc(file=s)
                    self.AddText(u"\nException: %s" % s.getvalue())
                



#             match = WikiFormatting.ScriptRE.search(text)
#             while(match):
#                 script = re.sub(u"^[\r\n\s]+", "", match.group(1))
#                 script = re.sub(u"[\r\n\s]+$", "", script)
#                 try:
#                     if index == -1:
#                         script = re.sub(u"^\d:?\s?", u"", script)
#                         exec(script) in self.evalScope
#                     elif index > -1 and script.startswith(str(index)):
#                         script = re.sub(u"^\d:?\s?", u"", script)
#                         exec(script) in self.evalScope
#                         break # Execute only the first found script
# 
#                 except Exception, e:
#                     s = StringIO()
#                     traceback.print_exc(file=s)
#                     self.AddText(u"\nException: %s" % s.getvalue())
# 
#                 match = WikiFormatting.ScriptRE.search(text, match.end())
        else:
            # Evaluate selected text
            text = self.GetSelectedText()
            try:
                compThunk = compile(re.sub(u"[\n\r]", u"", text), "<string>",
                        "eval", CO_FUTURE_DIVISION)
                result = eval(compThunk, self.evalScope)
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
        if not self.presenter.getConfig().getboolean("main",
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
        if not self.presenter.getConfig().getboolean("main",
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
        relations = self.getLoadedDocPage().getParentRelationships()[:]

        # Apply sort order
        relations.sort(_removeBracketsAndSort) # sort alphabetically

        return self.agaFormatList(relations)


    def startIncrementalSearch(self, initSearch=None):
        sb = self.presenter.getStatusBar()

        self.incSearchCharStartPos = self.GetSelectionCharPos()[1]

        rect = sb.GetFieldRect(0)
        rect.SetPosition(sb.ClientToScreen(rect.GetPosition()))

        dlg = IncrementalSearchDialog(self, -1, self, rect,
                sb.GetFont(), self.presenter, initSearch)
        dlg.Show()



    def executeIncrementalSearch(self, next=False):
        """
        Run incremental search, called only by IncrementalSearchDialog
        """
        text = self.GetText()
        if len(self.searchStr) > 0:   # and not searchStr.endswith("\\"):
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
                matchbytestart = self.bytelenSct(text[:match.start()])
                matchbyteend = matchbytestart + \
                        self.bytelenSct(text[match.start():match.end()])

                self.SetSelectionByCharPos(match.start(), match.end())

                return match.end()

        self.SetSelection(-1, -1)
        self.GotoPos(self.bytelenSct(text[:self.incSearchCharStartPos]))

        return -1


    def executeIncrementalSearchBackward(self):
        """
        Run incremental search, called only by IncrementalSearchDialog
        """
        text = self.GetText()
        if len(self.searchStr) > 0:   # and not searchStr.endswith("\\"):
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

                self.SetSelectionByCharPos(match.start(), match.end())

                return match.start()

        self.SetSelection(-1, -1)
        self.GotoPos(self.bytelenSct(text[:self.incSearchCharStartPos]))

        return -1


    def resetIncrementalSearch(self):
        """
        Called by IncrementalSearchDialog before aborting a inc. search
        """
        self.SetSelection(-1, -1)
        self.GotoPos(self.bytelenSct(self.GetText()[:self.incSearchCharStartPos]))


    def getContinuePosForSearch(self, sarOp):
        """
        Return the character position where to continue the given
        search operation sarOp. It always continues at beginning
        or end of current selection.
        
        If sarOp uses a regular expression, this function may throw
        a re.error exception.
        """
        if sarOp.matchesPart(self.GetSelectedText()) is not None:
            # currently selected text matches search operation
            # -> continue searching at the end of selection
            return self.GetSelectionCharPos()[1]
        else:
            # currently selected text does not match search
            # -> continue searching at the beginning of selection
            return self.GetSelectionCharPos()[0]


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
                self.SetSelectionByCharPos(start, end)

                return found    # self.anchorCharPosition

        self.SetSelection(-1, -1)
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
                        self.getLoadedDocPage().getPropertyOrGlobal(
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


    def getNearestWordPositions(self, bytepos=None):
        if not bytepos:
            bytepos = self.GetCurrentPos()
        return (self.WordStartPosition(bytepos, 1), self.WordEndPosition(bytepos, 1))


    def autoComplete(self):
        """
        Called when user wants autocompletion.
        """
        endBytePos = self.GetCurrentPos()
        startBytePos = self.PositionFromLine(
                self.LineFromPosition(endBytePos))
        line = self.GetTextRange(startBytePos, endBytePos)
        rline = revStr(line)
        backBytesMap = {}

        # TODO Sort entries appropriately (whatever this means)

        wikiDocument = self.presenter.getWikiDocument()
        wikiData = wikiDocument.getWikiData()
        
        formatting = self.presenter.getFormatting()

        mat1 = formatting.RevWikiWordRE.match(rline)
        if mat1:
            # may be CamelCase word
            tofind = line[-mat1.end():]
            bb = self.bytelenSct(tofind)
            for word in wikiData.getWikiWordsStartingWith(tofind, True, True):
                if not formatting.isCcWikiWord(word):
                    continue
                backBytesMap[word] = bb

        mat2 = formatting.RevWikiWordRE2.match(rline)
        mat3 = formatting.RevPropertyValue.match(rline)
        if mat2:
            # may be not-CamelCase word or in a property name
            tofind = line[-mat2.end():]
            bb = self.bytelenSct(tofind)
            
            # Should a closing bracket be appended to suggested words?
            if self.presenter.getConfig().getboolean("main",
                    "editor_autoComplete_closingBracket", False):
                wordBracketEnd = formatting.BracketEnd
            else:
                wordBracketEnd = u""

            for word in wikiData.getWikiWordsStartingWith(
                    tofind[len(formatting.BracketStart):], True, True):
                backBytesMap[formatting.BracketStart + word +
                        wordBracketEnd] = bb

            for prop in wikiData.getPropertyNamesStartingWith(tofind[
                    len(formatting.BracketStart):]):
                backBytesMap[formatting.BracketStart + prop] = bb
        elif mat3:
            # In a property value
            tofind = line[-mat3.end():]
            propkey = revStr(mat3.group(3))
            propfill = revStr(mat3.group(2))
            propvalpart = revStr(mat3.group(1))
            bb = self.bytelenSct(tofind)
            values = filter(lambda pv: pv.startswith(propvalpart),
                    wikiData.getDistinctPropertyValues(propkey))

            for v in values:
                backBytesMap[formatting.BracketStart + propkey +
                        propfill + v + formatting.BracketEnd] = bb

        mat = formatting.RevTodoKeyRE.match(rline)
        if mat:
            # Might be todo entry
            tofind = line[-mat.end():]
            bb = self.bytelenSct(tofind)
            for t in wikiData.getTodos():
                td = t[1]
                if not td.startswith(tofind):
                    continue

                tdmat = formatting.ToDoREWithCapturing.match(td)
                key = tdmat.group(1) + u":"
                backBytesMap[key] = bb

        mat = formatting.RevTodoValueRE.match(rline)
        if mat:
            # Might be todo entry
            tofind = line[-mat.end():]
            bb = self.bytelenSct(tofind)
            todos = [t[1] for t in wikiData.getTodos() if t[1].startswith(tofind)]
            for t in todos:
                backBytesMap[t] = bb

        mat = formatting.RevWikiWordAnchorRE2.match(rline)
        if mat:
            # In an anchor of a possible bracketed wiki word
            tofind = line[-mat.end():]
            bb = self.bytelenSct(tofind)
            wikiWord = revStr(mat.group("wikiWord"))
            anchorBegin = revStr(mat.group("anchorBegin"))

            try:
                page = wikiDocument.getWikiPage(wikiWord) # May throw exception
                anchors = [a for a in page.getAnchors()
                        if a.startswith(anchorBegin)]

                for a in anchors:
                    backBytesMap[formatting.BracketStart + wikiWord +
                            formatting.BracketEnd +
                            formatting.AnchorStart + a] = bb
            except WikiWordNotFoundException:
                # wikiWord isn't a wiki word
                pass

        mat = formatting.RevWikiWordAnchorRE.match(rline)
        if mat:
            # In an anchor of a possible camel case word
            tofind = line[-mat.end():]
            bb = self.bytelenSct(tofind)
            wikiWord = revStr(mat.group("wikiWord"))
            anchorBegin = revStr(mat.group("anchorBegin"))

            try:
                page = wikiDocument.getWikiPage(wikiWord) # May throw exception
                anchors = [a for a in page.getAnchors()
                        if a.startswith(anchorBegin)]
                        
                for a in anchors:
                    backBytesMap[wikiWord + formatting.AnchorStart +
                            a] = bb
            except WikiWordNotFoundException:
                # wikiWord isn't a wiki word
                pass

        self.autoCompBackBytesMap = backBytesMap
        acresult = backBytesMap.keys()
        
        if len(acresult) > 0:
            # formatting.BracketEnd
            acresultTuples = []
            for r in acresult:
                if r.endswith(formatting.BracketEnd):
                    rc = r[: -len(formatting.BracketEnd)]
                else:
                    rc = r
                acresultTuples.append((rc, r))
                
            self.presenter.getWikiDocument().getCollator().sortByKey(
                    acresultTuples)
            self.UserListShow(1, u"\x01".join(
                    [art[1] for art in acresultTuples]))

#             self.presenter.getWikiDocument().getCollator().sort(acresult)
#             self.UserListShow(1, u"\x01".join(acresult))


    def OnModified(self, evt):
        if not self.ignoreOnChange:
            if evt.GetModificationType() & \
                    (wx.stc.STC_MOD_INSERTTEXT | wx.stc.STC_MOD_DELETETEXT):
                self.getLoadedDocPage().setDirty(True)
                self.presenter.informLiveTextChanged(self)

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
        key = evt.GetKeyCode()

        self.lastKeyPressed = time()
        accP = getAccelPairFromKeyDown(evt)
        matchesAccelPair = self.presenter.getMainControl().keyBindings.\
                matchesAccelPair

        if matchesAccelPair("ContinueSearch", accP):
            # ContinueSearch is normally F3
            self.startIncrementalSearch(self.searchStr)
            evt.Skip()

        elif matchesAccelPair("StartIncrementalSearch", accP):
            # Start incremental search
            # First get selected text and prepare it as default value
            text = self.GetSelectedText()
            text = text.split("\n", 1)[0]
            text = text[:30]
            self.startIncrementalSearch(text)

        elif matchesAccelPair("AutoComplete", accP):
            # AutoComplete is normally Ctrl-Space
            # Handle autocompletion
            self.autoComplete()

        elif matchesAccelPair("ActivateLink2", accP):
            # ActivateLink2 is normally Ctrl-Return
            self.activateLink()

        elif not evt.ControlDown() and not evt.ShiftDown():  # TODO Check all modifiers
            if key == wx.WXK_TAB:
                if self.pageType == u"form":
                    self._goToNextFormField()
                    return
                evt.Skip()
            elif key == wx.WXK_RETURN:
                if self.presenter.getConfig().getboolean("main",
                        "editor_autoUnbullets"):
                    # Check for lonely bullet or number
                    endBytePos = self.GetCurrentPos()
                    startBytePos = self.PositionFromLine(
                            self.LineFromPosition(endBytePos))
                    
                    line = self.GetTextRange(startBytePos, endBytePos)
                    mat = WikiFormatting.BulletRE.match(line)
                    if mat and mat.end(0) == len(line):
                        self.SetSelection(startBytePos, endBytePos)
                        self.ReplaceSelection(mat.group("indentBullet"))
                        return

                    mat = WikiFormatting.NumericBulletRE.match(line)
                    if mat and mat.end(0) == len(line):
                        self.SetSelection(startBytePos, endBytePos)

                        replacement = mat.group("indentNumeric")
                        if mat.group("preLastNumeric") != u"":
                            replacement += mat.group("preLastNumeric") + u" "

                        self.ReplaceSelection(replacement)
                        return
                evt.Skip()
            else:
                evt.Skip()
            
        else:
            evt.Skip()


    def OnChar(self, evt):
        key = evt.GetKeyCode()

        # Return if this doesn't seem to be a real character input
        if evt.ControlDown() or key < 32:
            evt.Skip()
            return
            
        if key >= wx.WXK_START and (not isUnicode() or evt.GetUnicodeKey() != key):
            evt.Skip()
            return


        if isWin9x() and (WindowsHacks is not None):
            unichar = WindowsHacks.ansiInputToUnicodeChar(key)

#             if self.inIncrementalSearch:
#                 self.searchStr += unichar
#                 self.executeIncrementalSearch();
#             else:
            self.ReplaceSelection(unichar)

        else:

            if isUnicode():
                unichar = unichr(evt.GetUnicodeKey())
            else:
                unichar = mbcsDec(chr(key))[0]
                
#             # handle key presses while in incremental search here
#             if self.inIncrementalSearch:
#                 self.searchStr += unichar
#                 self.executeIncrementalSearch();
#             else:
            evt.Skip()


    def OnSetFocus(self, evt):
        self.presenter.makeCurrent()
        evt.Skip()


    def OnUserListSelection(self, evt):
        text = evt.GetText()
        toerase = self.autoCompBackBytesMap[text]
#         if text[0] == "[":
#             toerase = self.autoCompBackBytesWithBracket
#         else:
#             toerase = self.autoCompBackBytesWithoutBracket
            
        self.SetSelection(self.GetCurrentPos() - toerase, self.GetCurrentPos())
        
        self.ReplaceSelection(text)


    def OnClick(self, evt):
        if evt.ControlDown():
            x = evt.GetX()
            y = evt.GetY()
            if not self.activateLink(wx.Point(x, y)):
                evt.Skip()
        else:
            evt.Skip()

    def OnMiddleDown(self, evt):
        if not evt.ControlDown():
            middleConfig = self.presenter.getConfig().getint("main",
                    "mouse_middleButton_withoutCtrl", 2)
        else:
            middleConfig = self.presenter.getConfig().getint("main",
                    "mouse_middleButton_withCtrl", 3)

        tabMode = MIDDLE_MOUSE_CONFIG_TO_TABMODE[middleConfig]
        
        if not self.activateLink(evt.GetPosition(), tabMode=tabMode):
            evt.Skip()


    def OnDoubleClick(self, evt):
        x = evt.GetX()
        y = evt.GetY()
        if not self.activateLink(wx.Point(x, y)):
            evt.Skip()

#     def OnMouseMove(self, evt):
#         if (not evt.ControlDown()) or evt.Dragging():
#             self.SetCursor(WikiTxtCtrl.CURSOR_IBEAM)
#             evt.Skip()
#             return
#         else:
#             textPos = self.PositionFromPoint(evt.GetPosition())
# 
#             if (self.isPositionInWikiWord(textPos) or
#                         self.isPositionInLink(textPos)):
#                 self.SetCursor(WikiTxtCtrl.CURSOR_HAND)
#                 return
#             else:
#                 # self.SetCursor(WikiTxtCtrl.CURSOR_IBEAM)
#                 evt.Skip()
#                 return


    def OnStyleDone(self, evt):
        if evt.stylebytes:
            self.applyStyling(evt.stylebytes)
        
        if evt.foldingseq:
            self.applyFolding(evt.foldingseq)


    def OnIdle(self, evt):
#         self.idleCounter -= 1
#         if self.idleCounter < 0:
#             self.idleCounter = 0
        if (self.IsEnabled()):
            if self.presenter.isCurrent():
                # fix the line, pos and col numbers
                currentLine = self.GetCurrentLine()+1
                currentPos = self.GetCurrentPos()
                currentCol = self.GetColumn(currentPos)
                self.presenter.SetStatusText(u"Line: %d Col: %d Pos: %d" %
                        (currentLine, currentCol, currentPos), 2)


    def OnDestroy(self, evt):
        # This is how the clipboard contents can be preserved after
        # the app has exited.
        wx.TheClipboard.Flush()
        evt.Skip()


    def OnMarginClick(self, evt):
        if evt.GetMargin() == self.FOLD_MARGIN:
            pos = evt.GetPosition()
            line = self.LineFromPosition(pos)
            modifiers = evt.GetModifiers() #?

            self.ToggleFold(line)
            self.repairFoldingVisibility()
        
        evt.Skip()
        
        
    def OnDwellStart(self, evt):
        wikiDocument = self.presenter.getWikiDocument()
        if wikiDocument is None:
            return
        wikiData = wikiDocument.getWikiData()
        
        bytePos = evt.GetPosition()
        charPos = len(self.GetTextRange(0, bytePos))
        
        pageAst = self.getPageAst()

        tokens = pageAst.getTokensForPos(charPos)

        if charPos > 0:
            # Maybe a token left to the cursor was meant, so check
            # one char to the left
            tokens += pageAst.getTokensForPos(charPos - 1)
            
        callTip = None
        for tok in tokens:
            if tok.ttype == WikiFormatting.FormatTypes.WikiWord:
                wikiWord = tok.node.nakedWord
                if wikiData.isDefinedWikiWord(wikiWord):
                    wikiWord = wikiData.getAliasesWikiWord(wikiWord)
                    propList = wikiData.getPropertiesForWord(wikiWord)
                    for key, value in propList:
                        if key == u"short_hint":
                            callTip = value
                            break

                    if callTip:
                        break

        if callTip:
            self.CallTipShow(bytePos, callTip)


    def OnDwellEnd(self, evt):
        self.CallTipCancel()



    # TODO
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


# sorter for relations, removes brackets and sorts lower case
# Already defined in WikiTreeCtrl
def _removeBracketsAndSort(a, b):
#     a = wikiWordToLabel(a)
#     b = wikiWordToLabel(b)
    return cmp(a.lower(), b.lower())


class WikiTxtCtrlDropTarget(wx.PyDropTarget):
    def __init__(self, editor):
        wx.PyDropTarget.__init__(self)

        self.editor = editor
        self.resetDObject()

    def resetDObject(self):
        """
        (Re)sets the dataobject at init and after each drop
        """
        dataob = wx.DataObjectComposite()
        self.tobj = wx.TextDataObject()  # Char. size depends on wxPython build!

        dataob.Add(self.tobj)

        self.fobj = wx.FileDataObject()
        dataob.Add(self.fobj)
        
        self.dataob = dataob
        self.SetDataObject(dataob)


    def OnDragOver(self, x, y, defresult):
        return self.editor.DoDragOver(x, y, defresult)


    def OnData(self, x, y, defresult):
        try:
            if self.GetData():
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
        text = lineendToInternal(text)
        self.editor.DoDropText(x, y, text)


    def OnDropFiles(self, x, y, filenames):
        urls = []

        # Necessary because key state may change during the loop                                
        controlPressed = wx.GetKeyState(wx.WXK_CONTROL)
        shiftPressed = wx.GetKeyState(wx.WXK_SHIFT)

        for fn in filenames:
            if isLinux():
                # On Linux, at least Ubuntu, fn is a UTF-8 encoded unicode(!?)
                # string
                fn = utf8Dec(fn.encode("latin-1", "replace"))[0]

            url = urlFromPathname(fn)

            if fn.endswith(".wiki"):
                urls.append("wiki:%s" % url)
            else:
                doCopy = False
                if controlPressed:
                    # Copy file into file storage
                    fs = self.editor.presenter.getWikiDocument().getFileStorage()
                    try:
                        fn = fs.createDestPath(fn)
                        doCopy = True
                    except Exception, e:
                        traceback.print_exc()
                        self.editor.presenter.getMainControl().displayErrorMessage(
                                u"Couldn't copy file", e)
                        return

                if shiftPressed or doCopy:
                    # Relative rel: URL
                    locPath = self.editor.presenter.getMainControl().getWikiConfigPath()
                    if locPath is not None:
                        locPath = dirname(locPath)
                        relPath = relativeFilePath(locPath, fn)
                        if relPath is None:
                            # Absolute path needed
                            urls.append("file:%s" % url)
                        else:
                            urls.append("rel://%s" % urlFromPathname(relPath))
                else:
                    # Absolute file: URL
                    urls.append("file:%s" % url)

        self.editor.DoDropText(x, y, " ".join(urls))



_CONTEXT_MENU_INTEXT_BASE = \
u"""
Undo;CMD_UNDO
Redo;CMD_REDO
-
Cut;CMD_CLIPBOARD_CUT
Copy;CMD_CLIPBOARD_COPY
Paste;CMD_CLIPBOARD_PASTE
Delete;CMD_TEXT_DELETE
-
Select All;CMD_TEXT_SELECT_ALL
"""


_CONTEXT_MENU_INTEXT_ACTIVATE = \
u"""
-
Activate;CMD_ACTIVATE_THIS
Activate New Tab;CMD_ACTIVATE_NEW_TAB_THIS
Activate New Tab Backgrd.;CMD_ACTIVATE_NEW_TAB_BACKGROUND_THIS
"""


_CONTEXT_MENU_INTEXT_BOTTOM = \
u"""
-
Close Tab;CMD_CLOSE_CURRENT_TAB
"""



FOLD_MENU = \
u"""
+Show folding;CMD_CHECKBOX_SHOW_FOLDING;Show folding marks and allow folding;*ShowFolding
&Toggle current folding;CMD_TOGGLE_CURRENT_FOLDING;Toggle folding of the current line;*ToggleCurrentFolding
&Unfold All;CMD_UNFOLD_ALL_IN_CURRENT;Unfold everything in current editor;*UnfoldAll
&Fold All;CMD_FOLD_ALL_IN_CURRENT;Fold everything in current editor;*FoldAll
"""




