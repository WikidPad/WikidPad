## import hotshot
## _prof = hotshot.Profile("hotshot.prf")

import os, traceback, codecs, array
from cStringIO import StringIO
import urllib_red as urllib
import string
import re # import pwiki.srePersistent as re
import threading

from os.path import exists, dirname

from time import time, sleep

import wx, wx.stc

from Utilities import *
from Utilities import DUMBTHREADSTOP, callInMainThread

from Consts import FormatTypes

from wxHelper import GUI_ID, getTextFromClipboard, copyTextToClipboard, \
        wxKeyFunctionSink, getAccelPairFromKeyDown, appendToMenuByMenuDesc, \
        getBitmapFromClipboard, getMetafileFromClipboard
from MiscEvent import KeyFunctionSinkAR
from WikiExceptions import WikiWordNotFoundException, WikiFileNotFoundException, \
        NotCurrentThreadException, NoPageAstException
from ParseUtilities import getFootnoteAnchorDict

from Configuration import MIDDLE_MOUSE_CONFIG_TO_TABMODE
from AdditionalDialogs import ImagePasteSaver, ImagePasteDialog
# import WikiFormatting
import DocPages
import UserActionCoord

from SearchAndReplace import SearchReplaceOperation
from StringOps import *
# utf8Enc, utf8Dec, mbcsEnc, mbcsDec, uniToGui, guiToUni, \
#        wikiWordToLabel, revStr, lineendToInternal, lineendToOs

from Configuration import isUnicode, isWin9x, isLinux, isWindows

try:
    import WindowsHacks
except:
    if isWindows():
        traceback.print_exc()
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



_RE_LINE_INDENT = re.compile(ur"^[ \t]*")



class IncrementalSearchDialog(wx.Frame):
    
    COLOR_YELLOW = wx.Colour(255, 255, 0);
    COLOR_GREEN = wx.Colour(0, 255, 0);
    
    def __init__(self, parent, id, txtCtrl, rect, font, presenter, searchInit=None):
        wx.Frame.__init__(self, parent, id, u"WikidPad i-search",
                rect.GetPosition(), rect.GetSize(),
                wx.NO_BORDER | wx.FRAME_FLOAT_ON_PARENT)

        self.txtCtrl = txtCtrl
        self.presenter = presenter
        self.tfInput = wx.TextCtrl(self, GUI_ID.INC_SEARCH_TEXT_FIELD,
                _(u"Incremental search (ENTER/ESC to finish)"),
                style=wx.TE_PROCESS_ENTER | wx.TE_RICH)

        self.tfInput.SetFont(font)
        self.tfInput.SetBackgroundColour(IncrementalSearchDialog.COLOR_YELLOW)
        mainsizer = wx.BoxSizer(wx.HORIZONTAL)
        mainsizer.Add(self.tfInput, 1, wx.ALL | wx.EXPAND, 0)

        self.SetSizer(mainsizer)
        self.Layout()
        self.tfInput.SelectAll()  #added for Mac compatibility
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
        self.txtCtrl.forgetIncrementalSearch()
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
#         if evt.Button(wx.MOUSE_BTN_ANY) and self.closeDelay:

        # Workaround for name clash in wx.MouseEvent.Button:
        if wx._core_.MouseEvent_Button(evt, wx.MOUSE_BTN_ANY) and self.closeDelay:
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
            self.txtCtrl.endIncrementalSearch()
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
            self.txtCtrl.endIncrementalSearch()
            self.Close()
            self.txtCtrl.activateLink()
        elif matchesAccelPair("ActivateLinkNewTab", accP):
            # ActivateLinkNewTab is normally Ctrl-Alt-L
            self.txtCtrl.endIncrementalSearch()
            self.Close()
            self.txtCtrl.activateLink(tabMode=2)        
        elif matchesAccelPair("ActivateLink2", accP):
            # ActivateLink2 is normally Ctrl-Return
            self.txtCtrl.endIncrementalSearch()
            self.Close()
            self.txtCtrl.activateLink()
        elif matchesAccelPair("ActivateLinkBackground", accP):
            # ActivateLinkNewTab is normally Ctrl-Alt-L
            self.txtCtrl.endIncrementalSearch()
            self.Close()
            self.txtCtrl.activateLink(tabMode=3)        
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


    if isOSX():
        # Fix focus handling after close
        def Close(self):
            wx.Frame.Close(self)
            wx.CallAfter(self.txtCtrl.SetFocus)


    def OnTimerIncSearchClose(self, evt):
        self.txtCtrl.endIncrementalSearch()  # TODO forgetIncrementalSearch() instead?
        self.Close()


class StyleCollector(SnippetCollector):
    """
    Helps to collect the style bytes needed to set the syntax coloring.
    """
    def __init__(self, defaultStyleNo, text, bytelenSct, startCharPos=0):   
        super(StyleCollector, self).__init__()
        self.defaultStyleNo = defaultStyleNo
        self.text = text
        self.bytelenSct = bytelenSct
        self.charPos = startCharPos


    def bindStyle(self, targetCharPos, targetLength, styleNo):
        bytestylelen = self.bytelenSct(self.text[self.charPos:targetCharPos])
        self.append(chr(self.defaultStyleNo) * bytestylelen)
       
        self.charPos = targetCharPos + targetLength
        
        bytestylelen = self.bytelenSct(self.text[targetCharPos:self.charPos])
        self.append(chr(styleNo) * bytestylelen)

#         bytestylelen = self.bytelenSct(self.text[self.charPos:targetCharPos])
#         self.append(chr(self.nextStyleNo) * bytestylelen)
#         
#         self.nextStyleNo = styleNo
#         self.charPos = targetCharPos

    def value(self):
        if self.charPos < len(self.text):
            bytestylelen = self.bytelenSct(self.text[self.charPos:len(self.text)])
            self.append(chr(self.defaultStyleNo) * bytestylelen)

        return super(StyleCollector, self).value()




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
        self.calltipThreadHolder = ThreadHolder()
        self.clearStylingCache()
        self.pageType = "normal"   # The pagetype controls some special editor behaviour
#         self.idleCounter = 0       # Used to reduce idle load
#         self.loadedDocPage = None
        self.lastFont = None
        self.ignoreOnChange = False
        self.searchStr = u""
        self.wikiLanguageHelper = None

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
        
        self._resetKeyBindings()
        
#         self.CmdKeyClearAll()
#         
#         # register some keyboard commands
#         self.CmdKeyAssign(ord('+'), wx.stc.STC_SCMOD_CTRL, wx.stc.STC_CMD_ZOOMIN)
#         self.CmdKeyAssign(ord('-'), wx.stc.STC_SCMOD_CTRL, wx.stc.STC_CMD_ZOOMOUT)
#         self.CmdKeyAssign(wx.stc.STC_KEY_HOME, 0, wx.stc.STC_CMD_HOMEWRAP)
#         self.CmdKeyAssign(wx.stc.STC_KEY_END, 0, wx.stc.STC_CMD_LINEENDWRAP)
#         self.CmdKeyAssign(wx.stc.STC_KEY_HOME, wx.stc.STC_SCMOD_SHIFT,
#                 wx.stc.STC_CMD_HOMEWRAPEXTEND)
#         self.CmdKeyAssign(wx.stc.STC_KEY_END, wx.stc.STC_SCMOD_SHIFT,
#                 wx.stc.STC_CMD_LINEENDWRAPEXTEND)
# 
# 
#         # Clear all key mappings for clipboard operations
#         # PersonalWikiFrame handles them and calls the special clipboard functions
#         # instead of the normal ones
#         self.CmdKeyClear(wx.stc.STC_KEY_INSERT, wx.stc.STC_SCMOD_CTRL)
#         self.CmdKeyClear(wx.stc.STC_KEY_INSERT, wx.stc.STC_SCMOD_SHIFT)
#         self.CmdKeyClear(wx.stc.STC_KEY_DELETE, wx.stc.STC_SCMOD_SHIFT)
# 
#         self.CmdKeyClear(ord('X'), wx.stc.STC_SCMOD_CTRL)
#         self.CmdKeyClear(ord('C'), wx.stc.STC_SCMOD_CTRL)
#         self.CmdKeyClear(ord('V'), wx.stc.STC_SCMOD_CTRL)

        self.SetModEventMask(
                wx.stc.STC_MOD_INSERTTEXT | wx.stc.STC_MOD_DELETETEXT)

        # set the autocomplete separator
        self.AutoCompSetSeparator(1)   # ord('~')

        # register some event handlers
        self.presenterListener = wxKeyFunctionSink((
                ("saving all pages", self.onSavingAllPages),
                ("closing current wiki", self.onClosingCurrentWiki),
                ("dropping current wiki", self.onDroppingCurrentWiki),
                ("reloaded current doc page", self.onReloadedCurrentPage)
        ), self.presenter.getMiscEvent())

        self.__sinkApp = wxKeyFunctionSink((
                ("options changed", self.onOptionsChanged),
        ), wx.GetApp().getMiscEvent(), self)

#         if not self.presenter.getMainControl().isMainWindowConstructed():
#             # Install event handler to wait for construction
#             self.__sinkMainFrame = wxKeyFunctionSink((
#                     ("constructed main window", self.onConstructedMainWindow),
#             ), self.presenter.getMainControl().getMiscEvent(), self)
#         else:
#             self.onConstructedMainWindow(None)


        self.__sinkMainFrame = wxKeyFunctionSink((
                ("idle visible", self.onIdleVisible),
        ), self.presenter.getMainControl().getMiscEvent(), self)

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

        wx.EVT_KEY_DOWN(self, self.OnKeyDown)
        if config.getboolean("main", "editor_useImeWorkaround", False):
            wx.EVT_CHAR(self, self.OnChar_ImeWorkaround)

        wx.EVT_SET_FOCUS(self, self.OnSetFocus)

        wx.EVT_CONTEXT_MENU(self, self.OnContextMenu)
        
        EVT_STYLE_DONE_COMMAND(self, self.OnStyleDone)

        self.incSearchCharStartPos = 0
        self.incSearchPreviousHiddenLines = None
        self.incSearchPreviousHiddenStartLine = -1

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
        wx.EVT_MENU(self, GUI_ID.CMD_SELECT_ALL, lambda evt: self.SelectAll())

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

        wx.EVT_MENU(self, GUI_ID.CMD_CLIPBOARD_COPY_URL_TO_THIS_ANCHOR,
                self.OnClipboardCopyUrlToThisAnchor)

        wx.EVT_MENU(self, GUI_ID.CMD_TEXT_SELECT_ALL, lambda evt: self.SelectAll())



#     def __getattr__(self, attr):
#         return getattr(self.cnt, attr)

    def getLoadedDocPage(self):
        return self.presenter.getDocPage()

    def close(self):
        """
        Close the editor (=prepare for destruction)
        """
        self.stylingThreadHolder.setThread(None)
        self.calltipThreadHolder.setThread(None)

        self.unloadCurrentDocPage({})   # ?
        self.presenterListener.disconnect()
#         self.presenter.getMiscEvent().removeListener(self.presenterListener)


#     def onConstructedMainWindow(self, evt):
#         """
#         Now we can register idle handler.
#         """
#         wx.EVT_IDLE(self, self.OnIdle)


    def Cut(self):
        self.Copy()
        self.ReplaceSelection("")

    def Copy(self):
        text = self.GetSelectedText()
        if len(text) == 0:
            return

        cbIcept = self.presenter.getMainControl().getClipboardInterceptor()  
        if cbIcept is not None:
            cbIcept.informCopyInWikidPadStart(text=text)
            try:
                copyTextToClipboard(text)
            finally:
                cbIcept.informCopyInWikidPadStop()
        else:
            copyTextToClipboard(text)

    def Paste(self):
        text = getTextFromClipboard()
        if text:
            self.ReplaceSelection(text)
            return

        fs = self.presenter.getWikiDocument().getFileStorage()
        imgsav = ImagePasteSaver()
        imgsav.readOptionsFromConfig(self.presenter.getConfig())

        bmp = getBitmapFromClipboard()
        if bmp is not None:
            img = bmp.ConvertToImage()
            del bmp
            
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

            return
        
        if not WindowsHacks:
            return

        destPath = imgsav.saveWmfFromClipboardToFileStorage(fs)

        if destPath is not None:
            locPath = self.presenter.getMainControl().getWikiConfigPath()

            if locPath is not None:
                locPath = dirname(locPath)
                relPath = relativeFilePath(locPath, destPath)
                url = None
                if relPath is None:
                    # Absolute path needed
                    url = "file:%s>i" % urlFromPathname(destPath)
                else:
                    url = "rel://%s>i" % urlFromPathname(relPath)

                if url:
                    self.ReplaceSelection(url)


    def onCmdCopy(self, miscevt):
        if wx.Window.FindFocus() != self:
            return
        self.Copy()


    def _resetKeyBindings(self):
        
        self.CmdKeyClearAll()
        
        # Register general keyboard commands (minus some which may lead to problems
        for key, mod, action in _DEFAULT_STC_KEYS:
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



#         # Clear all key mappings for clipboard operations
#         # PersonalWikiFrame handles them and calls the special clipboard functions
#         # instead of the normal ones
#         self.CmdKeyClear(wx.stc.STC_KEY_INSERT, wx.stc.STC_SCMOD_CTRL)
#         self.CmdKeyClear(wx.stc.STC_KEY_INSERT, wx.stc.STC_SCMOD_SHIFT)
#         self.CmdKeyClear(wx.stc.STC_KEY_DELETE, wx.stc.STC_SCMOD_SHIFT)
# 
#         self.CmdKeyClear(ord('X'), wx.stc.STC_SCMOD_CTRL)
#         self.CmdKeyClear(ord('C'), wx.stc.STC_SCMOD_CTRL)
#         self.CmdKeyClear(ord('V'), wx.stc.STC_SCMOD_CTRL)

        
        
    def setLayerVisible(self, vis, scName=""):
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
                try:
                    self.applyFolding(self.processFolding(
                            self.getPageAst(), DUMBTHREADSTOP))
                except NoPageAstException:
                    return
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
        styles = self.presenter.getMainControl().getPresentationExt()\
                .getStyles(styleFaces, config)
        
        for type, style in styles:
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


    def gotoCharPos(self, pos, scroll=True):
        # Go to the end and back again, so the anchor is
        # near the top
        sctPos = self.bytelenSct(self.GetText()[:pos])
        if scroll:
            self.SetSelection(-1, -1)
            self.GotoPos(self.GetLength())
            self.GotoPos(sctPos)
        else:
            self.SetSelectionStart(sctPos)
            self.SetSelectionEnd(sctPos)

        # self.SetSelectionByCharPos(pos, pos)


    def applyBasicSciSettings(self):
        """
        Apply the basic Scintilla settings which are resetted to wrong
        default values by some operations
        """
        if isUnicode():
            self.SetCodePage(wx.stc.STC_CP_UTF8)
        self.SetTabIndents(True)
        self.SetBackSpaceUnIndents(True)
        self.SetUseTabs(not self.tabsToSpaces)
        self.SetEOLMode(wx.stc.STC_EOL_LF)

        tabWidth = self.presenter.getConfig().getint("main",
                "editor_tabWidth", 4)

        self.SetIndent(tabWidth)
        self.SetTabWidth(tabWidth)

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

#         text = self.GetText()
#         page.replaceLiveText(text)
        if self.presenter.getMainControl().saveDocPage(page):
            self.SetSavePoint()


    def unloadCurrentDocPage(self, evtprops=None):
        ## _prof.start()
        # Stop threads
        self.stylingThreadHolder.setThread(None)
        self.calltipThreadHolder.setThread(None)

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

            docPage.removeTxtEditor(self)

            self.SetDocPointer(None)
            self.applyBasicSciSettings()

            self.wikiPageSink.disconnect()
            
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
            self.SetReadOnly(False)
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

        docPage = self.getLoadedDocPage()

        if docPage is None:
            return  # TODO How to handle?

        # get the font that should be used in the editor
        font = docPage.getPropertyOrGlobal("font", self.defaultFont)

        # set the styles in the editor to the font
        if self.lastFont != font:
            faces = self.presenter.getDefaultFontFaces().copy()
            faces["mono"] = font
            self.SetStyles(faces)
            self.lastEditorFont = font
        
        self.wikiPageSink.setEventSource(docPage.getMiscEvent())

        otherEditor = docPage.getTxtEditor()
        if otherEditor is not None:
            # Another editor contains already this page, so share its
            # Scintilla document object for synchronized editing
            self.SetDocPointer(otherEditor.GetDocPointer())
            self.applyBasicSciSettings()
        else:
            # Load content
            try:
                content = docPage.getLiveText()
            except WikiFileNotFoundException, e:
                assert 0   # TODO

            # now fill the text into the editor
            self.SetReadOnly(False)
            self.setTextAgaUpdated(content)
            
        if self.wikiLanguageHelper is None or \
                self.wikiLanguageHelper.getWikiLanguageName() != \
                docPage.getWikiLanguageName():

            wx.GetApp().freeWikiLanguageHelper(self.wikiLanguageHelper)
            self.wikiLanguageHelper = docPage.createWikiLanguageHelper()

        docPage.addTxtEditor(self)
        self._checkForReadOnly()

        if evtprops is None:
            evtprops = {}
        p2 = evtprops.copy()
        p2.update({"loading wiki page": True, "wikiPage": docPage})
        self.presenter.fireMiscEventProps(p2)  # TODO Remove this hack

        self.pageType = docPage.getProperties().get(u"pagetype",
                [u"normal"])[-1]

        if self.pageType == u"normal":
            if not docPage.isDefined():
                # This is a new, not yet defined page, so go to the end of page
                self.GotoPos(self.GetLength())
            else:
                anchor = evtprops.get("anchor")
                if anchor:
                    # Scroll page according to the anchor
                    pageAst = self.getPageAst()

                    anchorNodes = pageAst.iterDeepByName("anchorDef")
                    for node in anchorNodes:
                        if node.anchorLink == anchor:
                            self.gotoCharPos(node.pos + node.strLength)
                            break
                    else:
                        anchor = None # Not found

                if not anchor:
                    # see if there is a saved position for this page
                    prst = docPage.getPresentation()
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

        self.presenter.setTitle(docPage.getTitle())


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

        docPage = self.getLoadedDocPage()

        if not docPage.isDefined():
            return

        if self.wikiLanguageHelper is None or \
                self.wikiLanguageHelper.getWikiLanguageName() != \
                docPage.getWikiLanguageName():

            wx.GetApp().freeWikiLanguageHelper(self.wikiLanguageHelper)
            self.wikiLanguageHelper = docPage.createWikiLanguageHelper()
        
        if self.pageType == u"normal":
            # Scroll page according to the anchor
            try:
                anchorNodes = self.getPageAst().iterDeepByName("anchorDef")
                anchorNodes = self.getPageAst().iterDeepByName("anchorDef")
                for node in anchorNodes:
                    if node.anchorLink == anchor:
                        self.gotoCharPos(node.pos + node.strLength)
                        break
#                 else:
#                     anchor = None # Not found

            except NoPageAstException:
                return


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
        coltuple = colorDescToRgbTuple(self.presenter.getConfig().get(
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

        self._checkForReadOnly()
        self.SetStyles(faces)

        color = self._getColorFromOption("editor_bg_color", (255, 255, 255))

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
        self.StyleSetBackground(wx.stc.STC_STYLE_LINENUMBER, self._getColorFromOption(
                "editor_margin_bg_color", (212, 208, 200)))

        shorthintDelay = self.presenter.getConfig().getint("main",
                "editor_shortHint_delay", 500)
        self.SetMouseDwellTime(shorthintDelay)

        tabWidth = self.presenter.getConfig().getint("main",
                "editor_tabWidth", 4)

        self.SetIndent(tabWidth)
        self.SetTabWidth(tabWidth)



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


    def handleInvalidFileSignature(self, docPage):
        """
        Called directly from a doc page to repair the editor state if an
        invalid file signature was detected.
        
        docPage -- calling docpage
        """
        if docPage is not self.getLoadedDocPage() or \
                not isinstance(docPage,
                        (DocPages.DataCarryingPage, DocPages.AliasWikiPage)):
            return
        
        sd, ud = docPage.getDirty()
        if sd:
            return   # TODO What to do on conflict?

        content = docPage.getContent()
        docPage.setEditorText(content, dirty=False)
        self.ignoreOnChange = True
        # TODO: Store/restore selection & scroll pos.
        self.setTextAgaUpdated(content)
        self.ignoreOnChange = False


    def onSavingAllPages(self, miscevt):
        if self.getLoadedDocPage() is not None and (
                self.getLoadedDocPage().getDirty()[0] or miscevt.get("force",
                False)):
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


        if textlen < self.presenter.getConfig().getint(
                "main", "sync_highlight_byte_limit"):
#         if True:
            # Synchronous styling
            self.stylingThreadHolder.setThread(None)
            self.buildStyling(text, 0, threadstop=DUMBTHREADSTOP)

            self.applyStyling(self.stylebytes)   # TODO Necessary?
            # We can't call applyFolding directly because this in turn
            # calls repairFoldingVisibility which can't work while in
            # EVT_STC_STYLENEEDED event (at least for wxPython 2.6.2)
            # storeStylingAndAst() sends a StyleDoneEvent instead
            if self.getFoldingActive():
                self.storeStylingAndAst(None, self.foldingseq)
        else:
            # Asynchronous styling
            # This avoids further request from STC:
            self.stopStcStyler()

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
            
            nodes = self.getTokensForMousePos(mousePos)
            
            self.contextMenuTokens = nodes
            addActivateItem = False
            addUrlToClipboardItem = False
            for node in nodes:
                if node.name == "wikiWord":
                    addActivateItem = True
                elif node.name == "urlLink":
                    addActivateItem = True
                elif node.name == "insertion" and node.key == u"page":
                    addActivateItem = True
                elif node.name == "anchorDef":
                    addUrlToClipboardItem = True

            if addActivateItem:
                appendToMenuByMenuDesc(menu, _CONTEXT_MENU_INTEXT_ACTIVATE)
            
            if addUrlToClipboardItem:
                appendToMenuByMenuDesc(menu,
                        _CONTEXT_MENU_INTEXT_URL_TO_CLIPBOARD)            
    
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
            
            
    def handleDropText(self, x, y, text):
        self.DoDropText(x, y, text)
        self.gotoCharPos(self.GetSelectionCharPos()[1], scroll=False)
        self.SetFocus()


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


    def buildStyling(self, text, delay, threadstop=DUMBTHREADSTOP):
        try:
            if delay != 0 and not threadstop is DUMBTHREADSTOP:
                sleep(delay)
                threadstop.testRunning()
            
            docPage = self.getLoadedDocPage()
            if docPage is None:
                return
            
            for i in range(20):   # "while True" is too dangerous
                formatDetails = docPage.getFormatDetails()
                pageAst = docPage.getLivePageAst(threadstop=threadstop)
                threadstop.testRunning()
                if not formatDetails.isEquivTo(docPage.getFormatDetails()):
                    continue
                else:
                    break

            stylebytes = self.processTokens(text, pageAst, threadstop)
            
            threadstop.testRunning()
    
            if self.getFoldingActive():
                foldingseq = self.processFolding(pageAst, threadstop)
            else:
                foldingseq = None
    
            threadstop.testRunning()
            
            self.storeStylingAndAst(stylebytes, foldingseq)

        except NotCurrentThreadException:
            return



    _TOKEN_TO_STYLENO = {
        "bold": FormatTypes.Bold,
        "italics": FormatTypes.Italic,
        "urlLink": FormatTypes.Url,
        "script": FormatTypes.Script,
        "property": FormatTypes.Property,
        "insertion": FormatTypes.Script,
        "anchorDef": FormatTypes.Bold,
        "plainText": FormatTypes.Default
        }
       

    def processTokens(self, text, pageAst, threadstop):
        wikiDoc = self.presenter.getWikiDocument()
        stylebytes = StyleCollector(FormatTypes.Default,
                text, self.bytelenSct)


        def process(pageAst, stack):
            for node in pageAst.iterFlatNamed():
                threadstop.testRunning()
                
                styleNo = WikiTxtCtrl._TOKEN_TO_STYLENO.get(node.name)
                
                if styleNo is not None:
                    stylebytes.bindStyle(node.pos, node.strLength, styleNo)
                elif node.name == "wikiWord":
                    if wikiDoc.isCreatableWikiWord(node.wikiWord):
                        styleNo = FormatTypes.WikiWord
                    else:
                        styleNo = FormatTypes.AvailWikiWord

                    stylebytes.bindStyle(node.pos, node.strLength, styleNo)

                elif node.name == "todoEntry":
                    process(node, stack + ["todoEntry"])
                elif node.name == "key" and "todoEntry" in stack:
                    stylebytes.bindStyle(node.pos, node.strLength,
                            FormatTypes.ToDo)
                elif node.name == "value" and "todoEntry" in stack:
                    process(node, stack[:])
                           
                elif node.name == "heading":
                    if node.level < 4:
                        styleNo = FormatTypes.Heading1 + \
                                (node.level - 1)
                    else:
                        styleNo = FormatTypes.Heading4

                    stylebytes.bindStyle(node.pos, node.strLength, styleNo)
                
                elif node.name in ("table", "tableRow", "tableCell",
                        "orderedList", "unorderedList", "indentedText",
                        "noExport"):
                    process(node, stack[:])

        process(pageAst, [])
        return stylebytes.value()
        


    def processFolding(self, pageAst, threadstop):
        foldingseq = []
        currLine = 0
        prevLevel = 0
        levelStack = []
        foldHeader = False
        
        for node in pageAst:
            threadstop.testRunning()
            
            if node.name == "heading":
                while levelStack and (levelStack[-1][0] != "heading" or
                        levelStack[-1][1] > node.level):
                    del levelStack[-1]
                if not levelStack or levelStack[-1] != ("heading", node.level):
                    levelStack.append(("heading", node.level))
                foldHeader = True

            lfc = node.getString().count(u"\n")
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
        
#         wikiPage.appendLiveText("\n%s\n---------------------------\n\n%s\n" %
#                 (mbcsDec(strftime("%x %I:%M %p"), "replace")[0], text))
        wikiPage.appendLiveText("\n%s\n---------------------------\n\n%s\n" %
                (strftimeUB("%x %I:%M %p"), text))

    def styleSelection(self, startChars, endChars=None):
        """
        """
        if endChars is None:
            endChars = startChars

        (startBytePos, endBytePos) = self.GetSelection()
        if startBytePos == endBytePos:
            (startBytePos, endBytePos) = self.getNearestWordPositions()

        emptySelection = startBytePos == endBytePos  # is selection empty

        startCharPos = len(self.GetTextRange(0, startBytePos))
        endCharPos = startCharPos + len(self.GetTextRange(startBytePos, endBytePos))

        self.BeginUndoAction()
        try:
            endCharPos += len(startChars)
            
            if emptySelection:
                # If selection is empty, cursor will in the end
                # stand between the style characters
                cursorCharPos = endCharPos
            else:
                # If not, it will stand after styled word
                cursorCharPos = endCharPos + len(endChars)

            self.gotoCharPos(startCharPos, scroll=False)
            self.AddText(startChars)
    
            self.gotoCharPos(endCharPos, scroll=False)
            self.AddText(endChars)

            self.gotoCharPos(cursorCharPos, scroll=False)
        finally:
            self.EndUndoAction()
            

    def getPageAst(self):
        docPage = self.getLoadedDocPage()
        if docPage is None:
            raise NoPageAstException(u"Internal error: No docPage => no page AST")

        return docPage.getLivePageAst()


    def activateTokens(self, nodeList, tabMode=0):
        """
        Helper for activateLink()
        tabMode -- 0:Same tab; 2: new tab in foreground; 3: new tab in background
        """
        if len(nodeList) == 0:
            return False

        for node in nodeList:
            if node.name == "wikiWord":
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
                
                if not titleFromLink or node.titleNode is None:
                    suggNewPageTitle = None
                else:
                    suggNewPageTitle = node.titleNode.getString()

                presenter.openWikiPage(node.wikiWord,
                        motionType="child", anchor=node.anchorLink,
                        suggNewPageTitle=suggNewPageTitle)

                searchfrag = node.searchFragment
                if searchfrag is not None:
                    searchOp = SearchReplaceOperation()
                    searchOp.wildCard = "no"   # TODO Why not regex?
                    searchOp.searchStr = searchfrag
    
                    presenter.getSubControl("textedit").executeSearch(
                            searchOp, 0)
                
                if not tabMode & 1:
                    # Show in foreground
                    presenter.getMainControl().getMainAreaPanel().\
                            showPresenter(presenter)

                return True

            elif node.name == "urlLink":
                self.presenter.getMainControl().launchUrl(node.url)
                return True

            elif node.name == "insertion":
                if node.key == u"page":
                        
                    # open the wiki page
                    if tabMode & 2:
                        # New tab
                        presenter = self.presenter.getMainControl().\
                                createNewDocPagePresenterTab()
                    else:
                        # Same tab
                        presenter = self.presenter
    
                    presenter.openWikiPage(node.value,
                            motionType="child")  # , anchor=node.value)

                    if not tabMode & 1:
                        # Show in foreground
                        presenter.getMainControl().getMainAreaPanel().\
                                showPresenter(presenter)
    
                    return True

                    # TODO: Make this work correctly
#                 elif tok.node.key == u"rel":
#                     if tok.node.value == u"back":
#                         # Go back in history
#                         self.presenter.getMainControl().goBrowserBack()

            elif node.name == "footnote":
                try:
                    pageAst = self.getPageAst()
                    footnoteId = node.footnoteId
    
                    anchorNode = getFootnoteAnchorDict(pageAst).get(footnoteId)
                    if anchorNode is not None:
                        if anchorNode.pos != node.pos:
                            # Activated footnote was not last -> go to last
                            self.gotoCharPos(anchorNode.pos)
                        else:
                            # Activated footnote was last -> go to first
                            for fnNode in pageAst.iterDeepByName("footnote"):
                                if fnNode.footnoteId == footnoteId:
                                    self.gotoCharPos(fnNode.pos)
                                    break
    
                    return True
                except NoPageAstException:
                    return False
            else:
                continue

        return False


    def getTokensForMousePos(self, mousePosition=None):
        # mouse position overrides current pos
        if mousePosition and mousePosition != wx.DefaultPosition:
            linkBytePos = self.PositionFromPoint(mousePosition)
        else:
            linkBytePos = self.GetCurrentPos()

        try:
            pageAst = self.getPageAst()
        except NoPageAstException:
            return []

        linkCharPos = len(self.GetTextRange(0, linkBytePos))

        result = pageAst.findNodesForCharPos(linkCharPos)

        if linkCharPos > 0:
            # Maybe a token left to the cursor was meant, so check
            # one char to the left
            result += pageAst.findNodesForCharPos(linkCharPos - 1)
            
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

    def OnClipboardCopyUrlToThisAnchor(self, evt):
        wikiWord = self.presenter.getWikiWord()
        if wikiWord is None:
            wx.MessageBox(
                    _(u"This can only be done for the page of a wiki word"),
                    _(u'Not a wiki page'), wx.OK, self)
            return

        path = self.presenter.getWikiDocument().getWikiConfigPath()
        for node in self.contextMenuTokens:
            if node.name == "anchorDef":
                copyTextToClipboard(pathWordAndAnchorToWikiUrl(path, wikiWord,
                        node.anchorLink))
                return


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
            wx.MessageBox(_(u"Set in menu \"Wiki\", item \"Options...\", "
                    "options page \"Security\", \n"
                    "item \"Script security\" an appropriate value "
                    "to execute a script."), _(u"Script execution disabled"),
                    wx.OK, self.presenter.getMainControl())
            return

        SCRIPTFORMAT = "script"
        # it is important to python to have consistent eol's
        self.ConvertEOLs(self.eolMode)
        (startPos, endPos) = self.GetSelection()

        # if no selection eval all scripts
        if startPos == endPos or index > -1:
            # Execute all or selected script blocks on the page (or other
            #   related pages)
            try:            
                pageAst = self.getPageAst()
            except NoPageAstException:
                return

            scriptNodeGroups = [list(pageAst.iterDeepByName(SCRIPTFORMAT))]
            
            # process script imports
            if securityLevel > 1: # Local import_scripts properties allowed
                if self.getLoadedDocPage().getProperties().has_key(
                        u"import_scripts"):
                    scriptNames = self.getLoadedDocPage().getProperties()[
                            u"import_scripts"]
                    for sn in scriptNames:
                        try:
                            importPage = self.presenter.getWikiDocument().\
                                    getWikiPage(sn)
                            pageAst = importPage.getLivePageAst()
                            scriptNodeGroups.append(list(
                                    pageAst.iterDeepByName(SCRIPTFORMAT)))
                        except:
                            pass

            if securityLevel > 2: # global.import_scripts property also allowed
                globScriptName = self.presenter.getWikiDocument().getWikiData().\
                        getGlobalProperties().get(u"global.import_scripts")

                if globScriptName is not None:
                    try:
                        importPage = self.presenter.getWikiDocument().\
                                getWikiPage(globScriptName)
                        pageAst = importPage.getLivePageAst()
                        scriptNodeGroups.append(list(
                                    pageAst.iterDeepByName(SCRIPTFORMAT)))
                    except:
                        pass
             
            if self.presenter.getConfig().getboolean("main",
                    "script_search_reverse", False):
                scriptNodeGroups.reverse()

            scriptNodes = reduce(lambda a, b: a + b, scriptNodeGroups)

            for node in scriptNodes:
                script = node.findFlatByName("code").getString()
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
                    self.AddText(_(u"\nException: %s") % s.getvalue())
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
        return text
        # TODO: Reactivate function
#         if not self.presenter.getConfig().getboolean("main",
#                 "process_autogenerated_areas"):
#             return text
# 
#         return WikiFormatting.AutoGenAreaRE.sub(ur"\1\2\4", text)


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
        return text
        # TODO: Reactivate function

#         if not self.presenter.getConfig().getboolean("main",
#                 "process_autogenerated_areas"):
#             return text
# 
#         # So the text can be referenced from an AGA function
#         self.agatext = text
# 
#         return WikiFormatting.AutoGenAreaRE.sub(self._agaReplace, text)


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


    # TODO  Reflect possible changes in WikidPadParser.py
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
        relations.sort(key=string.lower) # sort alphabetically

        return self.agaFormatList(relations)


    def ensureSelectionExpanded(self):
        """
        Ensure that the selection is visible and not in a folded area
        """
        self.repairFoldingVisibility()

        byteStart = self.GetSelectionStart()
        byteEnd = self.GetSelectionEnd()

        startLine = self.LineFromPosition(byteStart)
        endLine = self.LineFromPosition(byteEnd)
        
        # Just to be sure, shouldn't happen normally
        if endLine < startLine:
            startLine, endLine = endLine, startLine
        
        for checkLine in xrange(endLine, startLine - 1, -1):
            if not self.GetLineVisible(checkLine):
                line = checkLine

                while True:
                    line = self.GetFoldParent(line)
                    if line == -1:
                        break
                    if not self.GetFoldExpanded(line):
                        self.ToggleFold(line)

        self.SetSelection(byteStart, byteEnd)


    def setSelectionForIncSearchByCharPos(self, start, end):
        # Hide lines which were previously shown
        if self.incSearchPreviousHiddenLines is not None:
            line = self.incSearchPreviousHiddenStartLine
            for state in self.incSearchPreviousHiddenLines:
                if state:
                    self.ShowLines(line, line)
                else:
                    self.HideLines(line, line)
                
                line += 1
            
        self.incSearchPreviousHiddenLines = None
        self.incSearchPreviousHiddenStartLine = -1
        
        if start == -1:
#             self.SetSelection(-1, -1)
            self.SetSelection(self.GetSelectionStart(), self.GetSelectionStart())
            return
        text = self.GetText()

        byteStart = self.bytelenSct(text[:start])
        byteEnd = byteStart + self.bytelenSct(text[start:end])
        startLine = self.LineFromPosition(byteStart)
        endLine = self.LineFromPosition(byteEnd)
        
        # Store current show/hide state of lines to show
        shownList = []
        for i in xrange(startLine, endLine + 1):
            shownList.append(self.GetLineVisible(i))
            
        self.incSearchPreviousHiddenLines = shownList
        self.incSearchPreviousHiddenStartLine = startLine

        # Show lines
        self.ShowLines(startLine, endLine)
        self.SetSelection(byteStart, byteEnd)



    def startIncrementalSearch(self, initSearch=None):
        sb = self.presenter.getStatusBar()

        self.incSearchCharStartPos = self.GetSelectionCharPos()[1]
        self.incSearchPreviousHiddenLines = None
        self.incSearchPreviousHiddenStartLine = -1

        rect = sb.GetFieldRect(0)
        
        if isOSX():
            # needed on Mac OSX to avoid cropped text
            rect = wx._core.Rect(rect.x, rect.y - 2, rect.width, rect.height + 4)

        rect.SetPosition(sb.ClientToScreen(rect.GetPosition()))

        dlg = IncrementalSearchDialog(self, -1, self, rect,
                sb.GetFont(), self.presenter, initSearch)
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
#                 matchbytestart = self.bytelenSct(text[:match.start()])
#                 matchbyteend = matchbytestart + \
#                         self.bytelenSct(text[match.start():match.end()])

                self.setSelectionForIncSearchByCharPos(
                        match.start(), match.end())

                return match.end()

        self.setSelectionForIncSearchByCharPos(-1, -1)
        self.GotoPos(self.bytelenSct(text[:self.incSearchCharStartPos]))

        return -1


    def executeIncrementalSearchBackward(self):
        """
        Run incremental search, called only by IncrementalSearchDialog
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
        pass

    def resetIncrementalSearch(self):
        """
        Called by IncrementalSearchDialog before aborting an inc. search.
        Called when search was explicitly aborted by user (with escape key)
        """
        self.setSelectionForIncSearchByCharPos(-1, -1)
        self.GotoPos(self.bytelenSct(self.GetText()[:self.incSearchCharStartPos]))


    def endIncrementalSearch(self):
        """
        Called if incremental search ended successful.
        """
        byteStart = self.GetSelectionStart()
        byteEnd = self.GetSelectionEnd()

        self.setSelectionForIncSearchByCharPos(-1, -1)
        
        self.SetSelection(byteStart, byteEnd)
        self.ensureSelectionExpanded()


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



    def rewrapText(self):
        return self.wikiLanguageHelper.handleRewrapText(self, {})


    def getNearestWordPositions(self, bytepos=None):
        if not bytepos:
            bytepos = self.GetCurrentPos()
        return (self.WordStartPosition(bytepos, 1), self.WordEndPosition(bytepos, 1))


    def autoComplete(self):
        """
        Called when user wants autocompletion.
        """
        text = self.GetText()
        wikiDocument = self.presenter.getWikiDocument()
        closingBracket = self.presenter.getConfig().getboolean("main",
                "editor_autoComplete_closingBracket", False)

        bytePos = self.GetCurrentPos()
        lineStartBytePos = self.PositionFromLine(self.LineFromPosition(bytePos))
        
        lineStartCharPos = len(self.GetTextRange(0, lineStartBytePos))
        charPos = lineStartCharPos + len(self.GetTextRange(lineStartBytePos,
                bytePos))

        acResultTuples = self.wikiLanguageHelper.prepareAutoComplete(self, text,
                charPos, lineStartCharPos, wikiDocument,
                {"closingBracket": closingBracket})

        if len(acResultTuples) > 0:
            self.presenter.getWikiDocument().getCollator().sortByFirst(
                    acResultTuples)
            
            self.autoCompBackBytesMap = dict( (
                    (art[1], self.bytelenSct(text[charPos - art[2]:charPos]))
                    for art in acResultTuples) )

            self.UserListShow(1, u"\x01".join(
                    [art[1] for art in acResultTuples]))


    def OnModified(self, evt):
        if not self.ignoreOnChange:
            
            if evt.GetModificationType() & \
                    (wx.stc.STC_MOD_INSERTTEXT | wx.stc.STC_MOD_DELETETEXT):

                self.presenter.informEditorTextChanged(self)

                docPage = self.getLoadedDocPage()




    def OnCharAdded(self, evt):
        "When the user presses enter reindent to the previous level"

#         currPos = self.GetScrollPos(wxVERTICAL)
        
        evt.Skip()
        key = evt.GetKey()

        if key == 10:
            text = self.GetText()
            wikiDocument = self.presenter.getWikiDocument()
            bytePos = self.GetCurrentPos()
            lineStartBytePos = self.PositionFromLine(self.LineFromPosition(bytePos))

            lineStartCharPos = len(self.GetTextRange(0, lineStartBytePos))
            charPos = lineStartCharPos + len(self.GetTextRange(lineStartBytePos,
                    bytePos))

            autoUnbullet = self.presenter.getConfig().getboolean("main",
                    "editor_autoUnbullets", False)

            settings = {
                    "autoUnbullet": autoUnbullet,
                    "autoBullets": self.autoBullets,
                    "autoIndent": self.autoIndent
                    }

            self.wikiLanguageHelper.handleNewLineAfterEditor(self, text,
                    charPos, lineStartCharPos, wikiDocument, settings)



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
            text = re.escape(text[:30])
            self.startIncrementalSearch(text)

        elif matchesAccelPair("AutoComplete", accP):
            # AutoComplete is normally Ctrl-Space
            # Handle autocompletion
            self.autoComplete()

        elif matchesAccelPair("ActivateLink2", accP):
            # ActivateLink2 is normally Ctrl-Return
            self.activateLink()

        elif matchesAccelPair("ActivateLinkBackground", accP):
            # ActivateLink2 is normally Ctrl-Return
            self.activateLink(tabMode=3)

        elif not evt.ControlDown() and not evt.ShiftDown():  # TODO Check all modifiers
            if key == wx.WXK_TAB:
                if self.pageType == u"form":
                    self._goToNextFormField()
                    return
                evt.Skip()
            elif key == wx.WXK_RETURN and not self.AutoCompActive():
                text = self.GetText()
                wikiDocument = self.presenter.getWikiDocument()
                bytePos = self.GetCurrentPos()
                lineStartBytePos = self.PositionFromLine(self.LineFromPosition(bytePos))
                
                lineStartCharPos = len(self.GetTextRange(0, lineStartBytePos))
                charPos = lineStartCharPos + len(self.GetTextRange(lineStartBytePos,
                        bytePos))

                autoUnbullet = self.presenter.getConfig().getboolean("main",
                        "editor_autoUnbullets", False)
                
                settings = {
                        "autoUnbullet": autoUnbullet,
                        "autoBullets": self.autoBullets,
                        "autoIndent": self.autoIndent
                        }
                
                if self.wikiLanguageHelper.handleNewLineBeforeEditor(self, text,
                        charPos, lineStartCharPos, wikiDocument, settings):
                    evt.Skip()
                    return

            else:
                evt.Skip()
            
        else:
            evt.Skip()


    def OnChar_ImeWorkaround(self, evt):
        """
        Workaround for problem of Scintilla with some input method editors,
        e.g. UniKey vietnamese IME.
        """
        key = evt.GetKeyCode()

        # Return if this doesn't seem to be a real character input
        if evt.ControlDown() or (0 < key < 32):
            evt.Skip()
            return
            
        if key >= wx.WXK_START and (not isUnicode() or evt.GetUnicodeKey() != key):
            evt.Skip()
            return

        if isUnicode():
            unichar = unichr(evt.GetUnicodeKey())
        else:
            unichar = mbcsDec(chr(key))[0]

        self.ReplaceSelection(unichar)



    def OnSetFocus(self, evt):
        self.presenter.makeCurrent()
        evt.Skip()

        wikiPage = self.getLoadedDocPage()
        if wikiPage is None:
            return
        if not isinstance(wikiPage,
                (DocPages.DataCarryingPage, DocPages.AliasWikiPage)):
            return

        wikiPage.checkFileSignatureAndMarkDirty()


    def OnUserListSelection(self, evt):
        text = evt.GetText()
        toerase = self.autoCompBackBytesMap[text]

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


#     def OnIdle(self, evt):
    def onIdleVisible(self, miscevt):
#         evt.Skip()


#         self.idleCounter -= 1
#         if self.idleCounter < 0:
#             self.idleCounter = 0
        if (self.IsEnabled()):
            if self.presenter.isCurrent():
                # fix the line, pos and col numbers
                currentLine = self.GetCurrentLine()+1
                currentPos = self.GetCurrentPos()
                currentCol = self.GetColumn(currentPos)
                self.presenter.SetStatusText(_(u"Line: %d Col: %d Pos: %d") %
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
        
        

    def _threadShowCalltip(self, wikiDocument, charPos, bytePos,
            threadstop=DUMBTHREADSTOP):
        try:
            docPage = self.getLoadedDocPage()
            if docPage is None:
                return

            pageAst = docPage.getLivePageAst(threadstop=threadstop)

            nodes = pageAst.findNodesForCharPos(charPos)

            if charPos > 0:
                # Maybe a token left to the cursor was meant, so check
                # one char to the left
                nodes += pageAst.findNodesForCharPos(charPos - 1)

            callTip = None
            for node in nodes:
                if node.name == "wikiWord":
                    threadstop.testRunning()
                    wikiWord = wikiDocument.getUnAliasedWikiWord(node.wikiWord)
                    if wikiWord is not None:
                        propList = wikiDocument.getPropertyTriples(
                                wikiWord, u"short_hint", None)
                        if len(propList) > 0:
                            callTip = propList[-1][2]
                            break

            if callTip:
                threadstop.testRunning()
                callInMainThread(self.CallTipShow, bytePos, callTip)

        except NotCurrentThreadException:
            pass


    def OnDwellStart(self, evt):
        wikiDocument = self.presenter.getWikiDocument()
        if wikiDocument is None:
            return
        bytePos = evt.GetPosition()
        charPos = len(self.GetTextRange(0, bytePos))

        thread = threading.Thread(target=self._threadShowCalltip,
                args=(wikiDocument, charPos, bytePos),
                kwargs={"threadstop": self.calltipThreadHolder})
                
        self.calltipThreadHolder.setThread(thread)
        thread.start()

        
#         pageAst = self.getPageAst()
# 
#         nodes = pageAst.findNodesForCharPos(charPos)
# 
#         if charPos > 0:
#             # Maybe a token left to the cursor was meant, so check
#             # one char to the left
#             nodes += pageAst.findNodesForCharPos(charPos - 1)
# 
#         callTip = None
#         for node in nodes:
#             if node.name == "wikiWord":
#                 wikiWord = node.wikiWord
#                 if not wikiDocument.isCreatableWikiWord(wikiWord):
#                     wikiWord = wikiDocument.getAliasesWikiWord(wikiWord)
#                     propList = wikiDocument.getPropertyTriples(
#                             wikiWord, u"short_hint", None)
#                     if len(propList) > 0:
#                         callTip = propList[-1][2]
#                         break
# 
#         if callTip:
#             self.CallTipShow(bytePos, callTip)


    def OnDwellEnd(self, evt):
        self.calltipThreadHolder.setThread(None)
        self.CallTipCancel()


    @staticmethod
    def userActionPasteFiles(unifName, paramDict):
        """
        User action to handle pasting or dropping of files into editor.
        """
        editor = paramDict.get("editor")
        if editor is None:
            return

        filenames = paramDict.get("filenames")
        x = paramDict.get("x")
        y = paramDict.get("y")
        
        if unifName == u"action/editor/this/paste/files/insert/url/absolute":
            modeCopyToStorage = False
            modeRelativeUrl = False
        elif unifName == u"action/editor/this/paste/files/insert/url/relative":
            modeCopyToStorage = False
            modeRelativeUrl = True
        elif unifName == u"action/editor/this/paste/files/insert/url/tostorage":
            modeCopyToStorage = True
            modeRelativeUrl = False

        urls = []

        for fn in filenames:
            url = urlFromPathname(fn)
    
            if fn.endswith(".wiki"):
                urls.append("wiki:%s" % url)
            else:
                doCopy = False
                if modeCopyToStorage:
                    # Copy file into file storage
                    fs = editor.presenter.getWikiDocument().getFileStorage()
                    try:
                        fn = fs.createDestPath(fn)
                        doCopy = True
                    except Exception, e:
                        traceback.print_exc()
                        editor.presenter.getMainControl().displayErrorMessage(
                                _(u"Couldn't copy file"), e)
                        return
    
                if modeRelativeUrl or doCopy:
                    # Relative rel: URL
                    locPath = editor.presenter.getMainControl().getWikiConfigPath()
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
    
        editor.handleDropText(x, y, " ".join(urls))


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
        self.editor.handleDropText(x, y, text)


    def OnDropFiles(self, x, y, filenames):
        urls = []

        # Necessary because key state may change during the loop                                
        controlPressed = wx.GetKeyState(wx.WXK_CONTROL)
        shiftPressed = wx.GetKeyState(wx.WXK_SHIFT)
        
        if isLinux():
            # On Linux, at least Ubuntu, fn may be a UTF-8 encoded unicode(!?)
            # string
            try:
                filenames = [utf8Dec(fn.encode("latin-1"))[0]
                        for fn in filenames]
            except (UnicodeEncodeError, UnicodeDecodeError):
                pass


        mc = self.editor.presenter.getMainControl()

        paramDict = {"editor": self.editor, "filenames": filenames,
                "x": x, "y": y, "main control": mc}

        if controlPressed:
            suffix = u"/modkeys/ctrl"
        elif shiftPressed:
            suffix = u"/modkeys/shift"
        else:
            suffix = u""

        mc.getUserActionCoord().reactOnUserEvent(
                u"mouse/leftdrop/editor/files" + suffix, paramDict)




# User actions to register
_ACTION_EDITOR_PASTE_FILES_ABSOLUTE = UserActionCoord.SimpleAction("",
        u"action/editor/this/paste/files/insert/url/absolute",
        WikiTxtCtrl.userActionPasteFiles)

_ACTION_EDITOR_PASTE_FILES_RELATIVE = UserActionCoord.SimpleAction("",
        u"action/editor/this/paste/files/insert/url/relative",
        WikiTxtCtrl.userActionPasteFiles)

_ACTION_EDITOR_PASTE_FILES_TOSTORAGE = UserActionCoord.SimpleAction("",
        u"action/editor/this/paste/files/insert/url/tostorage",
        WikiTxtCtrl.userActionPasteFiles)


_ACTIONS = (
        _ACTION_EDITOR_PASTE_FILES_ABSOLUTE, _ACTION_EDITOR_PASTE_FILES_RELATIVE,
        _ACTION_EDITOR_PASTE_FILES_TOSTORAGE)


UserActionCoord.registerActions(_ACTIONS)



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
Follow Link;CMD_ACTIVATE_THIS
Follow Link New Tab;CMD_ACTIVATE_NEW_TAB_THIS
Follow Link New Tab Backgrd.;CMD_ACTIVATE_NEW_TAB_BACKGROUND_THIS
"""

_CONTEXT_MENU_INTEXT_URL_TO_CLIPBOARD = \
u"""
-
Copy Anchor URL to Clipboard;CMD_CLIPBOARD_COPY_URL_TO_THIS_ANCHOR
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


# Entries to support i18n of context menus

N_(u"Undo")
N_(u"Redo")
N_(u"Cut")
N_(u"Copy")
N_(u"Paste")
N_(u"Delete")
N_(u"Select All")

N_(u"Follow Link")
N_(u"Follow Link New Tab")
N_(u"Follow Link New Tab Backgrd.")

N_(u"Copy anchor URL to clipboard")

N_(u"Close Tab")

N_(u"Show folding")
N_(u"Show folding marks and allow folding")
N_(u"&Toggle current folding")
N_(u"Toggle folding of the current line")
N_(u"&Unfold All")
N_(u"Unfold everything in current editor")
N_(u"&Fold All")
N_(u"Fold everything in current editor")



# Default mapping based on Scintilla's "KeyMap.cxx" file
_DEFAULT_STC_KEYS = (
        (wx.stc.STC_KEY_DOWN,		wx.stc.STC_SCMOD_NORM,	wx.stc.STC_CMD_LINEDOWN),
        (wx.stc.STC_KEY_DOWN,		wx.stc.STC_SCMOD_SHIFT,	wx.stc.STC_CMD_LINEDOWNEXTEND),
        (wx.stc.STC_KEY_DOWN,		wx.stc.STC_SCMOD_CTRL,	wx.stc.STC_CMD_LINESCROLLDOWN),
        (wx.stc.STC_KEY_DOWN,		wx.stc.STC_SCMOD_SHIFT | wx.stc.STC_SCMOD_ALT,	wx.stc.STC_CMD_LINEDOWNRECTEXTEND),
        (wx.stc.STC_KEY_UP,		wx.stc.STC_SCMOD_NORM,	wx.stc.STC_CMD_LINEUP),
        (wx.stc.STC_KEY_UP,			wx.stc.STC_SCMOD_SHIFT,	wx.stc.STC_CMD_LINEUPEXTEND),
        (wx.stc.STC_KEY_UP,			wx.stc.STC_SCMOD_CTRL,	wx.stc.STC_CMD_LINESCROLLUP),
        (wx.stc.STC_KEY_UP,		wx.stc.STC_SCMOD_SHIFT | wx.stc.STC_SCMOD_ALT,	wx.stc.STC_CMD_LINEUPRECTEXTEND),
#         (ord('['),			wx.stc.STC_SCMOD_CTRL,		wx.stc.STC_CMD_PARAUP),
#         (ord('['),			wx.stc.STC_SCMOD_SHIFT | wx.stc.STC_SCMOD_CTRL,	wx.stc.STC_CMD_PARAUPEXTEND),
#         (ord(']'),			wx.stc.STC_SCMOD_CTRL,		wx.stc.STC_CMD_PARADOWN),
#         (ord(']'),			wx.stc.STC_SCMOD_SHIFT | wx.stc.STC_SCMOD_CTRL,	wx.stc.STC_CMD_PARADOWNEXTEND),
        (wx.stc.STC_KEY_LEFT,		wx.stc.STC_SCMOD_NORM,	wx.stc.STC_CMD_CHARLEFT),
        (wx.stc.STC_KEY_LEFT,		wx.stc.STC_SCMOD_SHIFT,	wx.stc.STC_CMD_CHARLEFTEXTEND),
        (wx.stc.STC_KEY_LEFT,		wx.stc.STC_SCMOD_CTRL,	wx.stc.STC_CMD_WORDLEFT),
        (wx.stc.STC_KEY_LEFT,		wx.stc.STC_SCMOD_SHIFT | wx.stc.STC_SCMOD_CTRL,	wx.stc.STC_CMD_WORDLEFTEXTEND),
        (wx.stc.STC_KEY_LEFT,		wx.stc.STC_SCMOD_SHIFT | wx.stc.STC_SCMOD_ALT,	wx.stc.STC_CMD_CHARLEFTRECTEXTEND),
        (wx.stc.STC_KEY_RIGHT,		wx.stc.STC_SCMOD_NORM,	wx.stc.STC_CMD_CHARRIGHT),
        (wx.stc.STC_KEY_RIGHT,		wx.stc.STC_SCMOD_SHIFT,	wx.stc.STC_CMD_CHARRIGHTEXTEND),
        (wx.stc.STC_KEY_RIGHT,		wx.stc.STC_SCMOD_CTRL,	wx.stc.STC_CMD_WORDRIGHT),
        (wx.stc.STC_KEY_RIGHT,		wx.stc.STC_SCMOD_SHIFT | wx.stc.STC_SCMOD_CTRL,	wx.stc.STC_CMD_WORDRIGHTEXTEND),
        (wx.stc.STC_KEY_RIGHT,		wx.stc.STC_SCMOD_SHIFT | wx.stc.STC_SCMOD_ALT,	wx.stc.STC_CMD_CHARRIGHTRECTEXTEND),
#         (ord('/'),		wx.stc.STC_SCMOD_CTRL,		wx.stc.STC_CMD_WORDPARTLEFT),
#         (ord('/'),		wx.stc.STC_SCMOD_SHIFT | wx.stc.STC_SCMOD_CTRL,	wx.stc.STC_CMD_WORDPARTLEFTEXTEND),
#         (ord('\\'),		wx.stc.STC_SCMOD_CTRL,		wx.stc.STC_CMD_WORDPARTRIGHT),
#         (ord('\\'),		wx.stc.STC_SCMOD_SHIFT | wx.stc.STC_SCMOD_CTRL,	wx.stc.STC_CMD_WORDPARTRIGHTEXTEND),
        (wx.stc.STC_KEY_HOME,		wx.stc.STC_SCMOD_NORM,	wx.stc.STC_CMD_VCHOME),
        (wx.stc.STC_KEY_HOME, 		wx.stc.STC_SCMOD_SHIFT, 	wx.stc.STC_CMD_VCHOMEEXTEND),
        (wx.stc.STC_KEY_HOME, 		wx.stc.STC_SCMOD_CTRL, 	wx.stc.STC_CMD_DOCUMENTSTART),
        (wx.stc.STC_KEY_HOME, 		wx.stc.STC_SCMOD_SHIFT | wx.stc.STC_SCMOD_CTRL, 	wx.stc.STC_CMD_DOCUMENTSTARTEXTEND),
        (wx.stc.STC_KEY_HOME, 		wx.stc.STC_SCMOD_ALT, 	wx.stc.STC_CMD_HOMEDISPLAY),
        (wx.stc.STC_KEY_HOME,		wx.stc.STC_SCMOD_SHIFT | wx.stc.STC_SCMOD_ALT,	wx.stc.STC_CMD_VCHOMERECTEXTEND),
        (wx.stc.STC_KEY_END,	 	wx.stc.STC_SCMOD_NORM,	wx.stc.STC_CMD_LINEEND),
        (wx.stc.STC_KEY_END,	 	wx.stc.STC_SCMOD_SHIFT, 	wx.stc.STC_CMD_LINEENDEXTEND),
        (wx.stc.STC_KEY_END, 		wx.stc.STC_SCMOD_CTRL, 	wx.stc.STC_CMD_DOCUMENTEND),
        (wx.stc.STC_KEY_END, 		wx.stc.STC_SCMOD_SHIFT | wx.stc.STC_SCMOD_CTRL, 	wx.stc.STC_CMD_DOCUMENTENDEXTEND),
        (wx.stc.STC_KEY_END, 		wx.stc.STC_SCMOD_ALT, 	wx.stc.STC_CMD_LINEENDDISPLAY),
        (wx.stc.STC_KEY_END,		wx.stc.STC_SCMOD_SHIFT | wx.stc.STC_SCMOD_ALT,	wx.stc.STC_CMD_LINEENDRECTEXTEND),
        (wx.stc.STC_KEY_PRIOR,		wx.stc.STC_SCMOD_NORM,	wx.stc.STC_CMD_PAGEUP),
        (wx.stc.STC_KEY_PRIOR,		wx.stc.STC_SCMOD_SHIFT, 	wx.stc.STC_CMD_PAGEUPEXTEND),
        (wx.stc.STC_KEY_PRIOR,		wx.stc.STC_SCMOD_SHIFT | wx.stc.STC_SCMOD_ALT,	wx.stc.STC_CMD_PAGEUPRECTEXTEND),
        (wx.stc.STC_KEY_NEXT, 		wx.stc.STC_SCMOD_NORM, 	wx.stc.STC_CMD_PAGEDOWN),
        (wx.stc.STC_KEY_NEXT, 		wx.stc.STC_SCMOD_SHIFT, 	wx.stc.STC_CMD_PAGEDOWNEXTEND),
        (wx.stc.STC_KEY_NEXT,		wx.stc.STC_SCMOD_SHIFT | wx.stc.STC_SCMOD_ALT,	wx.stc.STC_CMD_PAGEDOWNRECTEXTEND),
        (wx.stc.STC_KEY_DELETE, 	wx.stc.STC_SCMOD_NORM,	wx.stc.STC_CMD_CLEAR),
        (wx.stc.STC_KEY_DELETE, 	wx.stc.STC_SCMOD_CTRL,	wx.stc.STC_CMD_DELWORDRIGHT),
        (wx.stc.STC_KEY_DELETE,	wx.stc.STC_SCMOD_SHIFT | wx.stc.STC_SCMOD_CTRL,	wx.stc.STC_CMD_DELLINERIGHT),
        (wx.stc.STC_KEY_INSERT, 		wx.stc.STC_SCMOD_NORM,	wx.stc.STC_CMD_EDITTOGGLEOVERTYPE),
        (wx.stc.STC_KEY_ESCAPE,  	wx.stc.STC_SCMOD_NORM,	wx.stc.STC_CMD_CANCEL),
        (wx.stc.STC_KEY_BACK,		wx.stc.STC_SCMOD_NORM, 	wx.stc.STC_CMD_DELETEBACK),
        (wx.stc.STC_KEY_BACK,		wx.stc.STC_SCMOD_SHIFT, 	wx.stc.STC_CMD_DELETEBACK),
        (wx.stc.STC_KEY_BACK,		wx.stc.STC_SCMOD_CTRL, 	wx.stc.STC_CMD_DELWORDLEFT),
        (wx.stc.STC_KEY_BACK, 		wx.stc.STC_SCMOD_ALT,	wx.stc.STC_CMD_UNDO),
        (wx.stc.STC_KEY_BACK,		wx.stc.STC_SCMOD_SHIFT | wx.stc.STC_SCMOD_CTRL,	wx.stc.STC_CMD_DELLINELEFT),
        (ord('Z'), 			wx.stc.STC_SCMOD_CTRL,	wx.stc.STC_CMD_UNDO),
        (ord('Y'), 			wx.stc.STC_SCMOD_CTRL,	wx.stc.STC_CMD_REDO),
        (ord('A'), 			wx.stc.STC_SCMOD_CTRL,	wx.stc.STC_CMD_SELECTALL),
        (wx.stc.STC_KEY_TAB,		wx.stc.STC_SCMOD_NORM,	wx.stc.STC_CMD_TAB),
        (wx.stc.STC_KEY_TAB,		wx.stc.STC_SCMOD_SHIFT,	wx.stc.STC_CMD_BACKTAB),
        (wx.stc.STC_KEY_RETURN, 	wx.stc.STC_SCMOD_NORM,	wx.stc.STC_CMD_NEWLINE),
        (wx.stc.STC_KEY_RETURN, 	wx.stc.STC_SCMOD_SHIFT,	wx.stc.STC_CMD_NEWLINE),
        (wx.stc.STC_KEY_ADD, 		wx.stc.STC_SCMOD_CTRL,	wx.stc.STC_CMD_ZOOMIN),
        (wx.stc.STC_KEY_SUBTRACT,	wx.stc.STC_SCMOD_CTRL,	wx.stc.STC_CMD_ZOOMOUT),
#         (wx.stc.STC_KEY_DIVIDE,	wx.stc.STC_SCMOD_CTRL,	wx.stc.STC_CMD_SETZOOM),
#         (ord('L'), 			wx.stc.STC_SCMOD_CTRL,	wx.stc.STC_CMD_LINECUT),
#         (ord('L'), 			wx.stc.STC_SCMOD_SHIFT | wx.stc.STC_SCMOD_CTRL,	wx.stc.STC_CMD_LINEDELETE),
#         (ord('T'), 			wx.stc.STC_SCMOD_SHIFT | wx.stc.STC_SCMOD_CTRL,	wx.stc.STC_CMD_LINECOPY),
#         (ord('T'), 			wx.stc.STC_SCMOD_CTRL,	wx.stc.STC_CMD_LINETRANSPOSE),
#         (ord('D'), 			wx.stc.STC_SCMOD_CTRL,	wx.stc.STC_CMD_SELECTIONDUPLICATE),
#         (ord('U'), 			wx.stc.STC_SCMOD_CTRL,	wx.stc.STC_CMD_LOWERCASE),
#         (ord('U'), 			wx.stc.STC_SCMOD_SHIFT | wx.stc.STC_SCMOD_CTRL,	wx.stc.STC_CMD_UPPERCASE),
    )
