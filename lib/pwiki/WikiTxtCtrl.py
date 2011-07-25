from __future__ import with_statement
## import hotshot
## _prof = hotshot.Profile("hotshot.prf")

import traceback, codecs
from cStringIO import StringIO
import string, itertools, contextlib
import re # import pwiki.srePersistent as re
import threading

import subprocess

from os.path import exists, dirname, isfile, join, basename
from os import rename, unlink

from time import time, sleep

import wx, wx.stc

from Consts import FormatTypes

#from Utilities import *  # TODO Remove this
from .Utilities import DUMBTHREADSTOP, callInMainThread, ThreadHolder, \
        calcResizeArIntoBoundingBox

from .wxHelper import GUI_ID, getTextFromClipboard, copyTextToClipboard, \
        wxKeyFunctionSink, getAccelPairFromKeyDown, appendToMenuByMenuDesc
from . import wxHelper

from . import OsAbstract

from .WikiExceptions import *

from .SystemInfo import isUnicode, isOSX, isLinux, isWindows

from .ParseUtilities import getFootnoteAnchorDict

from .EnhancedScintillaControl import StyleCollector

from .SearchableScintillaControl import SearchableScintillaControl



from . import Configuration
from . import AdditionalDialogs
from . import WikiTxtDialogs

# image stuff
import imghdr


# import WikiFormatting
from . import DocPages
from . import UserActionCoord, WindowLayout

from .SearchAndReplace import SearchReplaceOperation
from . import StringOps
from . import SpellChecker

# from StringOps import *  # TODO Remove this
# mbcsDec, uniToGui, guiToUni, \
#        wikiWordToLabel, revStr, lineendToInternal, lineendToOs


from ViHelper import ViHintDialog, ViHelper
from collections import defaultdict

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
    return len(StringOps.utf8Enc(us)[0])


def bytelenSct_mbcs(us):
    """
    us -- unicode string
    returns: Number of bytes us requires in Scintilla (with mbcs encoding=Ansi)
    """
    return len(StringOps.mbcsEnc(us)[0])



# etEVT_STYLE_DONE_COMMAND = wx.NewEventType()
# EVT_STYLE_DONE_COMMAND = wx.PyEventBinder(etEVT_STYLE_DONE_COMMAND, 0)
#
# class StyleDoneEvent(wx.PyCommandEvent):
#     """
#     This wx Event is fired when style and folding calculations are finished.
#     It is needed to savely transfer data from the style thread to the main thread.
#     """
#     def __init__(self, stylebytes, foldingseq):
#         wx.PyCommandEvent.__init__(self, etEVT_STYLE_DONE_COMMAND, -1)
#         self.stylebytes = stylebytes
# #         self.pageAst = pageAst
#         self.foldingseq = foldingseq



class WikiTxtCtrl(SearchableScintillaControl):
    NUMBER_MARGIN = 0
    FOLD_MARGIN = 2
    SELECT_MARGIN = 1

    # Not the best of all possible solutions
    SUGGESTION_CMD_IDS = [GUI_ID.CMD_REPLACE_THIS_SPELLING_WITH_SUGGESTION_0,
            GUI_ID.CMD_REPLACE_THIS_SPELLING_WITH_SUGGESTION_1,
            GUI_ID.CMD_REPLACE_THIS_SPELLING_WITH_SUGGESTION_2,
            GUI_ID.CMD_REPLACE_THIS_SPELLING_WITH_SUGGESTION_3,
            GUI_ID.CMD_REPLACE_THIS_SPELLING_WITH_SUGGESTION_4,
            GUI_ID.CMD_REPLACE_THIS_SPELLING_WITH_SUGGESTION_5,
            GUI_ID.CMD_REPLACE_THIS_SPELLING_WITH_SUGGESTION_6,
            GUI_ID.CMD_REPLACE_THIS_SPELLING_WITH_SUGGESTION_7,
            GUI_ID.CMD_REPLACE_THIS_SPELLING_WITH_SUGGESTION_8,
            GUI_ID.CMD_REPLACE_THIS_SPELLING_WITH_SUGGESTION_9]

    def __init__(self, presenter, parent, ID):
        SearchableScintillaControl.__init__(self, presenter,
                presenter.getMainControl(), parent, ID)
        self.evalScope = None
        self.stylingThreadHolder = ThreadHolder()
        self.calltipThreadHolder = ThreadHolder()
        self.clearStylingCache()
        self.pageType = "normal"   # The pagetype controls some special editor behaviour
#         self.idleCounter = 0       # Used to reduce idle load
#         self.loadedDocPage = None
        self.lastFont = None
        self.ignoreOnChange = False
        self.dwellLockCounter = 0  # Don't process dwell start messages if >0
        self.wikiLanguageHelper = None
        self.templateIdRecycler = wxHelper.IdRecycler()
        self.vi = None  # Contains ViHandler instance if vi key handling enabled

        # If autocompletion word was choosen, how many bytes to delete backward
        # before inserting word
        self.autoCompBackBytesMap = {} # Maps selected word to number of backbytes

        # Inline image
        self.tooltip_image = None

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

        self.__sinkGlobalConfig = wxKeyFunctionSink((
                ("changed configuration", self.onChangedConfiguration),
        ), wx.GetApp().getGlobalConfig().getMiscEvent(), self)

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
                ("modified spell checker session", self.OnStyleNeeded),  # ???
                ("changed read only flag", self.onPageChangedReadOnlyFlag)
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

        if config.getboolean("main", "editor_useImeWorkaround", False):
            wx.EVT_CHAR(self, self.OnChar_ImeWorkaround)

        wx.EVT_SET_FOCUS(self, self.OnSetFocus)

        wx.EVT_CONTEXT_MENU(self, self.OnContextMenu)

#         self.incSearchCharStartPos = 0
        self.incSearchPreviousHiddenLines = None
        self.incSearchPreviousHiddenStartLine = -1

        self.onlineSpellCheckerActive = SpellChecker.isSpellCheckSupported() and \
                self.presenter.getConfig().getboolean(
                "main", "editor_onlineSpellChecker_active", False)

        self.optionColorizeSearchFragments = self.presenter.getConfig()\
                .getboolean("main", "editor_colorizeSearchFragments", False)

        self.onOptionsChanged(None)

        # when was a key pressed last. used to check idle time.
        self.lastKeyPressed = time()
        self.eolMode = self.GetEOLMode()

        self.contextMenuTokens = None
        self.contextMenuSpellCheckSuggestions = None

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


        for sps in self.SUGGESTION_CMD_IDS:
            wx.EVT_MENU(self, sps, self.OnReplaceThisSpellingWithSuggestion)

        wx.EVT_MENU(self, GUI_ID.CMD_ADD_THIS_SPELLING_SESSION,
                self.OnAddThisSpellingToIgnoreSession)
        wx.EVT_MENU(self, GUI_ID.CMD_ADD_THIS_SPELLING_GLOBAL,
                self.OnAddThisSpellingToIgnoreGlobal)
        wx.EVT_MENU(self, GUI_ID.CMD_ADD_THIS_SPELLING_LOCAL,
                self.OnAddThisSpellingToIgnoreLocal)

        wx.EVT_MENU(self, GUI_ID.CMD_ACTIVATE_THIS, self.OnActivateThis)
        wx.EVT_MENU(self, GUI_ID.CMD_ACTIVATE_NEW_TAB_THIS,
                self.OnActivateNewTabThis)
        wx.EVT_MENU(self, GUI_ID.CMD_ACTIVATE_NEW_TAB_BACKGROUND_THIS,
                self.OnActivateNewTabBackgroundThis)
        wx.EVT_MENU(self, GUI_ID.CMD_ACTIVATE_NEW_WINDOW_THIS,
                self.OnActivateNewWindowThis)

        wx.EVT_MENU(self, GUI_ID.CMD_CONVERT_URL_ABSOLUTE_RELATIVE_THIS,
                self.OnConvertUrlAbsoluteRelativeThis)

        wx.EVT_MENU(self, GUI_ID.CMD_OPEN_CONTAINING_FOLDER_THIS,
                self.OnOpenContainingFolderThis)

        wx.EVT_MENU(self, GUI_ID.CMD_DELETE_FILE,
                self.OnDeleteFile)

        wx.EVT_MENU(self, GUI_ID.CMD_RENAME_FILE,
                self.OnRenameFile)

        wx.EVT_MENU(self, GUI_ID.CMD_CLIPBOARD_COPY_URL_TO_THIS_ANCHOR,
                self.OnClipboardCopyUrlToThisAnchor)

        wx.EVT_MENU(self, GUI_ID.CMD_SELECT_TEMPLATE, self.OnSelectTemplate)



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


    def Copy(self, text=None):
        if text is None:
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
        # Text pasted?
        text = getTextFromClipboard()
        if text:
            self.ReplaceSelection(text)
            return True

        # File(name)s pasted?
        filenames = wxHelper.getFilesFromClipboard()
        if filenames is not None:
            mc = self.presenter.getMainControl()

            paramDict = {"editor": self, "filenames": filenames,
                    "x": -1, "y": -1, "main control": mc,
                    "processDirectly": True}

            mc.getUserActionCoord().runAction(
                    u"action/editor/this/paste/files/insert/url/ask", paramDict)

            return True

        fs = self.presenter.getWikiDocument().getFileStorage()
        imgsav = WikiTxtDialogs.ImagePasteSaver()
        imgsav.readOptionsFromConfig(self.presenter.getConfig())

        # Bitmap pasted?
        bmp = wxHelper.getBitmapFromClipboard()
        if bmp is not None:
            img = bmp.ConvertToImage()
            del bmp

            if self.presenter.getConfig().getboolean("main",
                    "editor_imagePaste_askOnEachPaste", True):
                # Options say to present dialog on an image paste operation
                # Send image so it can be used for preview
                dlg = WikiTxtDialogs.ImagePasteDialog(
                        self.presenter.getMainControl(), -1, imgsav, img)
                try:
                    dlg.ShowModal()
                    imgsav = dlg.getImagePasteSaver()
                finally:
                    dlg.Destroy()

            destPath = imgsav.saveFile(fs, img)
            if destPath is None:
                # Couldn't find unused filename or saving denied
                return True

#                 destPath = fs.findDestPathNoSource(u".png", u"")
#
#                 print "Paste6", repr(destPath)
#                 if destPath is None:
#                     # Couldn't find unused filename
#                     return
#
#                 img.SaveFile(destPath, wx.BITMAP_TYPE_PNG)

            url = self.presenter.getWikiDocument().makeAbsPathRelUrl(destPath)

            if url is None:
                url = u"file:" + StringOps.urlFromPathname(destPath)

            self.ReplaceSelection(url)

#             locPath = self.presenter.getMainControl().getWikiConfigPath()
#
#             if locPath is not None:
#                 locPath = dirname(locPath)
#                 relPath = relativeFilePath(locPath, destPath)
#                 url = None
#                 if relPath is None:
#                     # Absolute path needed
#                     url = "file:%s" % urlFromPathname(destPath)
#                 else:
#                     url = "rel://%s" % urlFromPathname(relPath)
#
#             if url:
#                 self.ReplaceSelection(url)

            return True

        if not WindowsHacks:
            return False

        # Windows Meta File pasted?
        destPath = imgsav.saveWmfFromClipboardToFileStorage(fs)
        if destPath is not None:
            url = self.presenter.getWikiDocument().makeAbsPathRelUrl(destPath)

            if url is None:
                url = u"file:" + StringOps.urlFromPathname(destPath)

            self.ReplaceSelection(url)
            return True


#         if destPath is not None:
#             locPath = self.presenter.getMainControl().getWikiConfigPath()
#
#             if locPath is not None:
#                 locPath = dirname(locPath)
#                 relPath = relativeFilePath(locPath, destPath)
#                 url = None
#                 if relPath is None:
#                     # Absolute path needed
#                     url = "file:%s>i" % urlFromPathname(destPath)
#                 else:
#                     url = "rel://%s>i" % urlFromPathname(relPath)
#
#                 if url:
#                     self.ReplaceSelection(url)

        return False


    def onCmdCopy(self, miscevt):
        if wx.Window.FindFocus() != self:
            return
        self.Copy()



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
        self.SetStyleBits(5)

        # create the styles
        if styleFaces is None:
            styleFaces = self.presenter.getDefaultFontFaces()

        config = self.presenter.getConfig()
        styles = self.presenter.getMainControl().getPresentationExt()\
                .getStyles(styleFaces, config)

        for type, style in styles:
            self.StyleSetSpec(type, style)

            if type == wx.stc.STC_STYLE_CALLTIP:
                self.CallTipUseStyle(10)

        self.IndicatorSetStyle(2, wx.stc.STC_INDIC_SQUIGGLE)
        self.IndicatorSetForeground(2, wx.Colour(255, 0, 0))


    def SetText(self, text, emptyUndo=True):
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
            wx.stc.StyledTextCtrl.SetText(self,
                    StringOps.mbcsEnc(text, "replace")[0])
        self.ignoreOnChange = False

        if emptyUndo:
            self.EmptyUndoBuffer()
        # self.applyBasicSciSettings()


    def replaceText(self, text):
        if isUnicode():
            wx.stc.StyledTextCtrl.SetText(self, text)
        else:
            wx.stc.StyledTextCtrl.SetText(self,
                    StringOps.mbcsEnc(text, "replace")[0])


    def replaceTextAreaByCharPos(self, newText, start, end):
        text = self.GetText()
        bs = self.bytelenSct(text[:start])
        be = bs + self.bytelenSct(text[start:end])
        self.SetTargetStart(bs)
        self.SetTargetEnd(be)

        if isUnicode():
            self.ReplaceTarget(newText)
        else:
            self.ReplaceTarget(StringOps.mbcsEnc(newText, "replace")[0])

#         text = self.GetText()
#         text = text[:pos] + newText + text[(pos + len):]
#
#         self.replaceText(text)


    def showSelectionByCharPos(self, start, end):
        """
        Same as SetSelectionByCharPos(), but scrolls to position correctly
        """
        text = self.GetText()
        bs = self.bytelenSct(text[:start])
        be = bs + self.bytelenSct(text[start:end])

        self.ensureTextRangeByBytePosExpanded(bs, be)
        super(WikiTxtCtrl, self).showSelectionByCharPos(start, end)


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

        globalAttrs = wikiDataManager.getWikiData().getGlobalAttributes()
        # get the font that should be used in the editor
        font = globalAttrs.get("global.font", self.defaultFont)

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

        # get the font that should be used in the editor
        font = docPage.getAttributeOrGlobal("font", self.defaultFont)

        # set the styles in the editor to the font
        if self.lastFont != font:
            faces = self.presenter.getDefaultFontFaces().copy()
            faces["mono"] = font
            self.SetStyles(faces)
            self.lastEditorFont = font

        self.pageType = docPage.getAttributes().get(u"pagetype",
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
                    # Is there a position given in the eventprops?
                    firstcharpos = evtprops.get("firstcharpos", -1)
                    if firstcharpos != -1:
                        charlength = max(0, evtprops.get("charlength", 0))
                        self.showSelectionByCharPos(firstcharpos,
                                firstcharpos + charlength)
                        anchor = True

                if not anchor:
                    # see if there is a saved position for this page
                    prst = docPage.getPresentation()
                    lastPos, scrollPosX, scrollPosY = prst[0:3]
                    foldInfo = prst[5]
                    self.setFoldInfo(foldInfo)
                    self.GotoPos(lastPos)

                    self.scrollXY(scrollPosX, scrollPosY)
        else:
            self.handleSpecialPageType()

        self.presenter.setTitle(docPage.getTitle())


    def handleSpecialPageType(self):
#         self.allowRectExtend(self.pageType != u"texttree")

        if self.pageType == u"form":
            self.GotoPos(0)
            self._goToNextFormField()
            return True

        return False


    def onReloadedCurrentPage(self, miscevt):
        """
        Called when already loaded page should be loaded again, mainly
        interesting if a link with anchor is activated
        """
        if not self.presenter.isCurrent():
            return

        anchor = miscevt.get("anchor")
        if not anchor:
            if self.pageType == u"normal":
                # Is there a position given in the eventprops?
                firstcharpos = miscevt.get("firstcharpos", -1)
                if firstcharpos != -1:
                    charlength = max(0, miscevt.get("charlength", 0))
                    self.showSelectionByCharPos(firstcharpos,
                            firstcharpos + charlength)

            return


#         if not anchor:
#             return

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
        coltuple = StringOps.colorDescToRgbTuple(self.presenter.getConfig().get(
                "main", option))

        if coltuple is None:
            coltuple = defColTuple

        return wx.Colour(*coltuple)


    def onPageChangedReadOnlyFlag(self, miscevt):
        self._checkForReadOnly()


    def onOptionsChanged(self, miscevt):
        faces = self.presenter.getDefaultFontFaces().copy()

        if isinstance(self.getLoadedDocPage(),
                (DocPages.WikiPage, DocPages.AliasWikiPage)):

            font = self.getLoadedDocPage().getAttributeOrGlobal("font",
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


        # To allow switching vi keys on and off without restart
        use_vi_navigation = self.presenter.getConfig().getboolean("main",
                "editor_compatibility_ViKeys", False)

        self.Unbind(wx.EVT_KEY_DOWN)
        self.Unbind(wx.EVT_LEFT_UP)

        if use_vi_navigation:
            if self.vi is None:
                self.vi = ViHandler(self)

            self.Bind(wx.EVT_KEY_DOWN, self.vi.OnViKeyDown)
            self.Bind(wx.EVT_LEFT_UP, self.vi.OnLeftMouseUp)
        else:
            if self.vi is not None:
                self.vi.TurnOff()
                self.vi = None
            self.Bind(wx.EVT_KEY_DOWN, self.OnKeyDown)


    def onChangedConfiguration(self, miscevt):
        """
        Called when global configuration was changed. Most things are processed
        by onOptionsChanged so only the online spell checker switch must be
        handled here.
        """
        restyle = False

        newSetting = SpellChecker.isSpellCheckSupported() and \
                self.presenter.getConfig().getboolean(
                "main", "editor_onlineSpellChecker_active", False)

        if newSetting != self.onlineSpellCheckerActive:
            self.onlineSpellCheckerActive = newSetting
            restyle = True

        newSetting = self.presenter.getConfig()\
                .getboolean("main", "editor_colorizeSearchFragments", False)

        if newSetting != self.optionColorizeSearchFragments:
            self.optionColorizeSearchFragments = newSetting
            restyle = True

        if restyle:
            self.OnStyleNeeded(None)



    def onWikiPageUpdated(self, miscevt):
        if self.getLoadedDocPage() is None or \
                not isinstance(self.getLoadedDocPage(),
                (DocPages.WikiPage, DocPages.AliasWikiPage)):
            return

        # get the font that should be used in the editor
        font = self.getLoadedDocPage().getAttributeOrGlobal("font",
                self.defaultFont)

        # set the styles in the editor to the font
        if self.lastFont != font:
            faces = self.presenter.getDefaultFontFaces().copy()
            faces["mono"] = font
            self.SetStyles(faces)
            self.lastEditorFont = font

        self.pageType = self.getLoadedDocPage().getAttributes().get(u"pagetype",
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


    def _fillTemplateMenu(self, menu):
        idRecycler = self.templateIdRecycler
        idRecycler.clearAssoc()

        config = self.presenter.getConfig()

        templateRePat = config.get(u"main", u"template_pageNamesRE",
                u"^template/")

        try:
            templateRe = re.compile(templateRePat, re.DOTALL | re.UNICODE)
        except re.error:
            templateRe = re.compile(u"^template/", re.DOTALL | re.UNICODE)

        wikiDocument = self.presenter.getWikiDocument()
        templateNames = [n for n in wikiDocument.getAllDefinedWikiPageNames()
                if templateRe.search(n)]

        wikiDocument.getCollator().sort(templateNames)

        for tn in templateNames:
            menuID, reused = idRecycler.assocGetIdAndReused(tn)

            if not reused:
                # For a new id, an event must be set
                wx.EVT_MENU(self, menuID, self.OnTemplateUsed)

            menu.Append(menuID, StringOps.uniToGui(tn))


    def OnTemplateUsed(self, evt):
        docPage = self.getLoadedDocPage()
        if docPage is None:
            return
        templateName = self.templateIdRecycler.get(evt.GetId())

        if templateName is None:
            return

        wikiDocument = self.presenter.getWikiDocument()
        templatePage = wikiDocument.getWikiPage(templateName)

        content = self.getLoadedDocPage().getContentOfTemplate(templatePage,
                templatePage)
        docPage.setMetaDataFromTemplate(templatePage)

        self.SetText(content, emptyUndo=False)
        self.pageType = docPage.getAttributes().get(u"pagetype",
                [u"normal"])[-1]
        self.handleSpecialPageType()
        # TODO Handle form mode!!
        self.presenter.informEditorTextChanged(self)


    def OnSelectTemplate(self, evt):
        docPage = self.getLoadedDocPage()
        if docPage is None:
            return

        if not isinstance(docPage, DocPages.WikiPage):
            return

        if not docPage.isDefined() and not docPage.getDirty()[0]:
            title = _(u"Select Template")
        else:
            title = _(u"Select Template (deletes current content!)")

        templateName = AdditionalDialogs.SelectWikiWordDialog.runModal(
                self.presenter.getMainControl(), self, -1,
                title=title)
        if templateName is None:
            return

        wikiDocument = self.presenter.getWikiDocument()
        templatePage = wikiDocument.getWikiPage(templateName)

        content = self.getLoadedDocPage().getContentOfTemplate(templatePage,
                templatePage)
        docPage.setMetaDataFromTemplate(templatePage)

        self.SetText(content, emptyUndo=False)
        self.pageType = docPage.getAttributes().get(u"pagetype",
                [u"normal"])[-1]
        self.handleSpecialPageType()
        self.presenter.informEditorTextChanged(self)


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
        else:

            nodes = self.getTokensForMousePos(mousePos)

            self.contextMenuTokens = nodes
            addActivateItem = False
            addFileUrlItem = False
            addWikiUrlItem = False
            addUrlToClipboardItem = False
            unknownWord = None
            for node in nodes:
                if node.name == "wikiWord":
                    addActivateItem = True
                elif node.name == "urlLink":
                    addActivateItem = True
                    if node.url.startswith(u"file:") or \
                            node.url.startswith(u"rel://"):
                        addFileUrlItem = True
                    elif node.url.startswith(u"wiki:") or \
                            node.url.startswith(u"wikirel://"):
                        addWikiUrlItem = True
                elif node.name == "insertion" and node.key == u"page":
                    addActivateItem = True
                elif node.name == "anchorDef":
                    addUrlToClipboardItem = True
                elif node.name == "unknownSpelling":
                    unknownWord = node.getText()

            if unknownWord:
                # Right click on a word not in spelling dictionary
                spellCheckerSession = self.presenter.getWikiDocument()\
                        .createOnlineSpellCheckerSessionClone()
                spellCheckerSession.setCurrentDocPage(self.getLoadedDocPage())
                if spellCheckerSession:
                    # Show suggestions if available (up to first 5)
                    suggestions = spellCheckerSession.suggest(unknownWord)[:5]
                    spellCheckerSession.close()

                    if len(suggestions) > 0:
                        for s, mid in zip(suggestions, self.SUGGESTION_CMD_IDS):
                            menuitem = wx.MenuItem(menu, mid, s)
                            font = menuitem.GetFont()
                            font.SetWeight(wx.FONTWEIGHT_BOLD)
                            menuitem.SetFont(font)

                            menu.AppendItem(menuitem)

                        self.contextMenuSpellCheckSuggestions = suggestions
                    # Show other spelling menu items
                    appendToMenuByMenuDesc(menu, _CONTEXT_MENU_INTEXT_SPELLING)


            appendToMenuByMenuDesc(menu, _CONTEXT_MENU_INTEXT_BASE)

            if addActivateItem:
                appendToMenuByMenuDesc(menu, _CONTEXT_MENU_INTEXT_ACTIVATE)

                if addFileUrlItem:
                    appendToMenuByMenuDesc(menu, _CONTEXT_MENU_INTEXT_FILE_URL)
                elif addWikiUrlItem:
                    appendToMenuByMenuDesc(menu, _CONTEXT_MENU_INTEXT_WIKI_URL)

            if addUrlToClipboardItem:
                appendToMenuByMenuDesc(menu,
                        _CONTEXT_MENU_INTEXT_URL_TO_CLIPBOARD)

            docPage = self.getLoadedDocPage()
            if isinstance(docPage, DocPages.WikiPage):
                if not docPage.isDefined() and not docPage.getDirty()[0]:
                    templateSubmenu = wx.Menu()
                    self._fillTemplateMenu(templateSubmenu)
                    appendToMenuByMenuDesc(templateSubmenu,
                            _CONTEXT_MENU_SELECT_TEMPLATE_IN_TEMPLATE_MENU)

                    menu.AppendSeparator()
                    menu.AppendMenu(wx.NewId(), _(u'Use Template'),
                            templateSubmenu)
                else:
                    appendToMenuByMenuDesc(menu,
                            _CONTEXT_MENU_SELECT_TEMPLATE)

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

        # Dwell lock to avoid image popup while context menu is shown
        with self.dwellLock():
            # Show menu
            self.PopupMenu(menu)

        self.contextMenuTokens = None
        self.contextMenuSpellCheckSuggestions = None
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
            if start is None:
                return False

            fieldcode = text[start + 2]
            if fieldcode == "i":
                self.showSelectionByCharPos(start, end)
                return True

            charStartPos = end


    def handleDropText(self, x, y, text):
        if x != -1:
            # Real drop
            self.DoDropText(x, y, text)
            self.gotoCharPos(self.GetSelectionCharPos()[1], scroll=False)
        else:
            self.ReplaceSelection(text)

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



    def storeStylingAndAst(self, stylebytes, foldingseq, styleMask=0xff):
        self.stylebytes = stylebytes
#         self.pageAst = pageAst
        self.foldingseq = foldingseq

        def putStyle():
            if stylebytes:
                self.applyStyling(stylebytes, styleMask)

            if foldingseq:
                self.applyFolding(foldingseq)

        wx.CallAfter(putStyle)

#         self.AddPendingEvent(StyleDoneEvent(stylebytes, foldingseq))



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

            if self.onlineSpellCheckerActive and \
                    isinstance(docPage, DocPages.AbstractWikiPage):

                # Show intermediate syntax highlighting results before spell check
                # if we are in asynchronous mode
                if not threadstop is DUMBTHREADSTOP:
                    self.storeStylingAndAst(stylebytes, foldingseq, styleMask=0x1f)

                scTokens = docPage.getSpellCheckerUnknownWords(threadstop=threadstop)

                threadstop.testRunning()

                if scTokens.getChildrenCount() > 0:
                    spellStyleBytes = self.processSpellCheckTokens(text, scTokens,
                            threadstop)

                    threadstop.testRunning()

                    # TODO: Faster? How?
                    stylebytes = "".join([chr(ord(a) | ord(b))
                            for a, b in itertools.izip(stylebytes, spellStyleBytes)])

                    self.storeStylingAndAst(stylebytes, None, styleMask=0xff)
                else:
                    self.storeStylingAndAst(stylebytes, None, styleMask=0xff)
            else:
                self.storeStylingAndAst(stylebytes, foldingseq, styleMask=0xff)

        except NotCurrentThreadException:
            return



    _TOKEN_TO_STYLENO = {
        "bold": FormatTypes.Bold,
        "italics": FormatTypes.Italic,
        "urlLink": FormatTypes.Url,
        "script": FormatTypes.Script,
        "property": FormatTypes.Attribute,             # TODO remove "property"-compatibility
        "attribute": FormatTypes.Attribute,
        "insertion": FormatTypes.Script,
        "anchorDef": FormatTypes.Bold,
        "plainText": FormatTypes.Default
        }


    def _findFragmentSearch(self, linkNode):
        """
        linkNode -- AST node of type "wikiWord"
        returns
            (<first char pos>, <after last char pos>) of targeted search
                fragment if present
            (None, None) if not present
            (-1, -1) if search is not applicable
        """
        unaliasedTarget = self.presenter.getWikiDocument()\
                .getWikiPageNameForLinkTermOrAsIs(linkNode.wikiWord)

        docPage = self.getLoadedDocPage()
        if docPage is None:
            return (-1, -1)

        wikiWord = docPage.getWikiWord()
        if wikiWord is None:
            return (-1, -1)

        if wikiWord == unaliasedTarget:
            forbiddenSearchfragHit = (linkNode.pos,
                    linkNode.pos + linkNode.strLength)
        else:
            forbiddenSearchfragHit = (0, 0)
        
        searchfrag = linkNode.searchFragment
        if searchfrag is None:
            return (-1, -1)

        searchOp = SearchReplaceOperation()
        searchOp.wildCard = "no"
        searchOp.searchStr = searchfrag
        
        targetPage = self.presenter.getWikiDocument().getWikiPage(
                linkNode.wikiWord)

        found = searchOp.searchDocPageAndText(targetPage,
                targetPage.getLiveText(), 0)

        if found[0] >= forbiddenSearchfragHit[0] and \
                found[0] < forbiddenSearchfragHit[1]:
            # Searchfrag found its own link -> search after link
            found = searchOp.searchDocPageAndText(targetPage,
                    targetPage.getLiveText(), forbiddenSearchfragHit[1])

        return found



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
                        if self.optionColorizeSearchFragments and \
                                node.searchFragment:
                            if self._findFragmentSearch(node)[0] == None:
#                             if targetTxt.find(node.searchFragment) == -1:
                                searchFragNode = node.fragmentNode

                                stylebytes.bindStyle(node.pos,
                                        searchFragNode.pos - node.pos,
                                        FormatTypes.AvailWikiWord)

                                stylebytes.bindStyle(searchFragNode.pos,
                                        searchFragNode.strLength,
                                        FormatTypes.WikiWord)

                                stylebytes.bindStyle(searchFragNode.pos +
                                        searchFragNode.strLength,
                                        node.strLength -
                                        (searchFragNode.pos - node.pos) -
                                        searchFragNode.strLength,
                                        FormatTypes.AvailWikiWord)
                                continue

                    stylebytes.bindStyle(node.pos, node.strLength, styleNo)

                elif node.name == "todoEntry":
                    process(node, stack + ["todoEntry"])
                elif node.name == "key" and "todoEntry" in stack:
                    stylebytes.bindStyle(node.pos, node.strLength,
                            FormatTypes.ToDo)
                elif node.name == "value" and "todoEntry" in stack:
                    process(node, stack[:])

                elif node.name == "heading":
                    if node.level < 6:   # TODO: Compatibility for Presentation.py without heading5
                        styleNo = FormatTypes.Heading1 + \
                                (node.level - 1)
                    else:
                        styleNo = FormatTypes.Bold

                    stylebytes.bindStyle(node.pos, node.strLength, styleNo)

                elif node.name in ("table", "tableRow", "tableCell",
                        "orderedList", "unorderedList", "indentedText",
                        "noExport"):
                    process(node, stack[:])

        process(pageAst, [])
        return stylebytes.value()


    def processSpellCheckTokens(self, text, scTokens, threadstop):
        stylebytes = StyleCollector(0, text, self.bytelenSct)
        for node in scTokens:
            threadstop.testRunning()
            stylebytes.bindStyle(node.pos, node.strLength,
                    wx.stc.STC_INDIC2_MASK)

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


    def applyStyling(self, stylebytes, styleMask=0xff):
        if len(stylebytes) == self.GetLength():
            self.StartStyling(0, styleMask)
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
                (StringOps.strftimeUB("%x %I:%M %p"), text))

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
                    if tabMode == 6:
                        # New Window
                        presenter = self.presenter.getMainControl().\
                                createNewDocPagePresenterTabInNewFrame()
                    else:
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

                unaliasedTarget = self.presenter.getWikiDocument()\
                        .getWikiPageNameForLinkTermOrAsIs(node.wikiWord)

                docPage = self.getLoadedDocPage()

                # Contains start and end character position where a search fragment
                # search should never match
                # If the target wikiword is the current one, the search fragment
                # search should not find the link itself

                forbiddenSearchfragHit = (0, 0)
                if docPage is not None:
                    wikiWord = docPage.getWikiWord()
                    if wikiWord is not None:
                        if wikiWord == unaliasedTarget:
                            forbiddenSearchfragHit = (node.pos, node.pos + node.strLength)

                presenter.openWikiPage(unaliasedTarget,
                        motionType="child", anchor=node.anchorLink,
                        suggNewPageTitle=suggNewPageTitle)

                searchfrag = node.searchFragment
                if searchfrag is not None:
                    searchOp = SearchReplaceOperation()
                    searchOp.wildCard = "no"
                    searchOp.searchStr = searchfrag

                    found = presenter.getSubControl("textedit").executeSearch(
                            searchOp, 0)

                    if found[0] >= forbiddenSearchfragHit[0] and \
                            found[0] < forbiddenSearchfragHit[1]:
                        # Searchfrag found its own link -> search after link
                        presenter.getSubControl("textedit").executeSearch(
                            searchOp, forbiddenSearchfragHit[1])

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
                        if tabMode == 6:
                            # New Window
                            presenter = self.presenter.getMainControl().\
                                    createNewDocPagePresenterTabInNewFrame()
                        else:
                            # New tab
                            presenter = self.presenter.getMainControl().\
                                    createNewDocPagePresenterTab()
                    else:
                        # Same tab
                        presenter = self.presenter

                    presenter.openWikiPage(node.value,
                            motionType="child")  # , anchor=node.value)

                    if not tabMode & 1:
                        # Show in foreground (if presenter is in other window,
                        # this does nothing)
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

        if self.onlineSpellCheckerActive:
            docPage = self.getLoadedDocPage()
            if isinstance(docPage, DocPages.AbstractWikiPage):
                allUnknownWords = docPage.getSpellCheckerUnknownWords()
                wantedUnknownWords = allUnknownWords.findNodesForCharPos(
                        linkCharPos)

                if linkCharPos > 0 and len(wantedUnknownWords) == 0:
                    # No unknown word found -> try left to cursor
                    wantedUnknownWords = allUnknownWords.findNodesForCharPos(
                            linkCharPos - 1)

                result += wantedUnknownWords

        return result



    def activateLink(self, mousePosition=None, tabMode=0):
        """
        Activates link (wiki word or URL)
        tabMode -- 0:Same tab; 2: new tab in foreground; 3: new tab in background
        """
        tokens = self.getTokensForMousePos(mousePosition)
        return self.activateTokens(tokens, tabMode)



    def OnReplaceThisSpellingWithSuggestion(self, evt):
        if self.contextMenuTokens and self.contextMenuSpellCheckSuggestions:
            for node in self.contextMenuTokens:
                if node.name == "unknownSpelling":
                    self.replaceTextAreaByCharPos(
                            self.contextMenuSpellCheckSuggestions[
                            self.SUGGESTION_CMD_IDS.index(evt.GetId())],
                            node.pos, node.pos + node.strLength)
                    break



    def OnAddThisSpellingToIgnoreSession(self, evt):
        if self.contextMenuTokens:
            for node in self.contextMenuTokens:
                if node.name == "unknownSpelling":
                    self.presenter.getWikiDocument()\
                            .getOnlineSpellCheckerSession().addIgnoreWordSession(
                            node.getText())
                    break


    def OnAddThisSpellingToIgnoreGlobal(self, evt):
        if self.contextMenuTokens:
            for node in self.contextMenuTokens:
                if node.name == "unknownSpelling":
                    self.presenter.getWikiDocument()\
                            .getOnlineSpellCheckerSession().addIgnoreWordGlobal(
                            node.getText())
                    break

    def OnAddThisSpellingToIgnoreLocal(self, evt):
        if self.contextMenuTokens:
            for node in self.contextMenuTokens:
                if node.name == "unknownSpelling":
                    self.presenter.getWikiDocument()\
                            .getOnlineSpellCheckerSession().addIgnoreWordLocal(
                            node.getText())
                    break



    def OnActivateThis(self, evt):
        if self.contextMenuTokens:
            self.activateTokens(self.contextMenuTokens, 0)

    def OnActivateNewTabThis(self, evt):
        if self.contextMenuTokens:
            self.activateTokens(self.contextMenuTokens, 2)

    def OnActivateNewTabBackgroundThis(self, evt):
        if self.contextMenuTokens:
            self.activateTokens(self.contextMenuTokens, 3)

    def OnActivateNewWindowThis(self, evt):
        if self.contextMenuTokens:
            self.activateTokens(self.contextMenuTokens, 6)


    def OnOpenContainingFolderThis(self, evt):
        if self.contextMenuTokens:
            for node in self.contextMenuTokens:
                if node.name == "urlLink":
                    link = node.url

                    if link.startswith(u"rel://") or link.startswith(u"wikirel://"):
                        link = self.presenter.getWikiDocument()\
                                .makeRelUrlAbsolute(link)

                    if link.startswith(u"file:") or link.startswith(u"wiki:"):
                        try:
                            path = dirname(StringOps.pathnameFromUrl(link))
                            if not exists(StringOps.longPathEnc(path)):
                                self.presenter.displayErrorMessage(
                                        _(u"Folder does not exist"))
                                return

                            OsAbstract.startFile(self.presenter.getMainControl(),
                                    path)
                        except IOError:
                            pass   # Error message?

                    break

    def OnDeleteFile(self, evt):
         if self.contextMenuTokens:
            for node in self.contextMenuTokens:
                if node.name == "urlLink":
                    link = self.presenter.getWikiDocument().makeFileUrlAbsPath(
                            node.url)
                    if link is None:
                        continue
                    
#                     link = node.url
# 
#                     if link.startswith(u"rel://"):
#                         link = StringOps.pathnameFromUrl(self.presenter.getMainControl().makeRelUrlAbsolute(link))
#                     else:
#                         break

#                     path = dirname(link)

                    if not isfile(link):
                        self.presenter.displayErrorMessage(
                                _(u"File does not exist"))
                        return

                    filename = basename(link)

                    choice = wx.MessageBox(
                            _("Are you sure you want to delete the file: %s") %
                            filename, _("Delete File"),
                            wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION, self)

                    if choice == wx.YES:
                        OsAbstract.deleteFile(link)
                        self.replaceTextAreaByCharPos(u"", node.pos,
                                node.pos + node.strLength)
                    return

        
    def OnRenameFile(self, evt):
        if not self.contextMenuTokens:
            return

        for node in self.contextMenuTokens:
            if node.name == "urlLink":
                link = self.presenter.getWikiDocument().makeFileUrlAbsPath(
                        node.url)
                if link is not None:
                    break
        else:
            return


#                 link = node.url
# 
#                 if link.startswith(u"rel://"):
#                     link = StringOps.pathnameFromUrl(self.presenter.getMainControl().makeRelUrlAbsolute(link))
#                 else:
#                     break

        if not isfile(link):
            self.presenter.displayErrorMessage(_(u"File does not exist"))
            return

        path = dirname(link)
        filename = basename(link)

        newName = filename
        while True:
            newName = wx.GetTextFromUser(_(u"Enter new name"),
                    _(u"Rename File"), newName, self)
            if not newName:
                # User cancelled
                return

            newfile = join(path, newName)
            
            if exists(newfile):
                if not isfile(newfile):
                    self.presenter.displayErrorMessage(
                            _(u"Target is not a file"))
                    continue

                choice = wx.MessageBox(
                        _("Target file exists already. Overwrite?"),
                        _("Overwrite File"),
                        wx.YES_NO | wx.CANCEL  | wx.NO_DEFAULT | wx.ICON_QUESTION,
                        self)
                if choice == wx.CANCEL:
                    return
                elif choice == wx.NO:
                    continue

            # Either file doesn't exist or user allowed overwrite
            
            OsAbstract.moveFile(link, newfile)
            
            if node.url.startswith(u"rel://"):
                # Relative URL/path
                newUrl = self.presenter.getWikiDocument().makeAbsPathRelUrl(
                        newfile)
            else:
                # Absolute URL/path
                newUrl = u"file:" + StringOps.urlFromPathname(newfile)

            self.replaceTextAreaByCharPos(newUrl, node.coreNode.pos,
                    node.coreNode.pos + node.coreNode.strLength)

            return



    def convertUrlAbsoluteRelative(self, tokenList):
        for node in tokenList:
            if node.name == "urlLink":
                link = node.url

                if ' ' in node.coreNode.getString():
                    addSafe = ' '
                else:
                    addSafe = ''

                if link.startswith(u"rel://") or link.startswith(u"wikirel://"):
                    link = self.presenter.getWikiDocument()\
                            .makeRelUrlAbsolute(link, addSafe=addSafe)

                elif link.startswith(u"file:"):
                    link = self.presenter.getWikiDocument()\
                            .makeAbsPathRelUrl(StringOps.pathnameFromUrl(
                            link), addSafe=addSafe)
                    if link is None:
                        continue # TODO Message?
                elif link.startswith(u"wiki:"):
                    link = self.presenter.getWikiDocument()\
                            .makeAbsPathRelUrl(StringOps.pathnameFromUrl(
                            link), addSafe=addSafe)
                    if link is None:
                        continue # TODO Message?
                    else:
                        link = u"wiki" + link  # Combines to "wikirel://"

                else:
                    continue

                self.replaceTextAreaByCharPos(link, node.coreNode.pos,
                        node.coreNode.pos + node.coreNode.strLength)

                break


    def convertSelectedUrlAbsoluteRelative(self):
        tokenList = self.getTokensForMousePos(None)
        self.convertUrlAbsoluteRelative(tokenList)


    def OnConvertUrlAbsoluteRelativeThis(self, evt):
        if self.contextMenuTokens:
            self.convertUrlAbsoluteRelative(self.contextMenuTokens)


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
                copyTextToClipboard(StringOps.pathWordAndAnchorToWikiUrl(path,
                        wikiWord, node.anchorLink))
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
            if securityLevel > 1: # Local import_scripts attributes allowed
                if self.getLoadedDocPage().getAttributes().has_key(
                        u"import_scripts"):
                    scriptNames = self.getLoadedDocPage().getAttributes()[
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

            if securityLevel > 2: # global.import_scripts attribute also allowed
                globScriptName = self.presenter.getWikiDocument().getWikiData().\
                        getGlobalAttributes().get(u"global.import_scripts")

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


    def ensureTextRangeByBytePosExpanded(self, byteStart, byteEnd):
        self.repairFoldingVisibility()

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



    def ensureSelectionExpanded(self):
        """
        Ensure that the selection is visible and not in a folded area
        """
        byteStart = self.GetSelectionStart()
        byteEnd = self.GetSelectionEnd()

        self.ensureTextRangeByBytePosExpanded(byteStart, byteEnd)

        self.SetSelection(byteStart, byteEnd)


    def setSelectionForIncSearchByCharPos(self, start, end):
        """
        Overwrites SearchableScintillaControl.setSelectionForIncSearchByCharPos
        Called during incremental search to select text. Will be called with
        start=-1 if nothing is found to select.
        This variant handles showing/hiding of folded lines
        """

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
        self.incSearchPreviousHiddenLines = None
        self.incSearchPreviousHiddenStartLine = -1

        super(WikiTxtCtrl, self).startIncrementalSearch(initSearch)


    def endIncrementalSearch(self):
        super(WikiTxtCtrl, self).endIncrementalSearch()

        self.ensureSelectionExpanded()


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
                charPos, lineStartCharPos, wikiDocument, self.getLoadedDocPage(),
                {"closingBracket": closingBracket, "builtinAttribs": True})

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

#                 docPage = self.getLoadedDocPage()




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


    def _getExpandedByteSelectionToLine(self, extendOverChildren):
        """
        Move the start of current selection to start of the line it's in and
        move end of selection to end of its line.
        """
        selByteStart = self.GetSelectionStart();
        selByteEnd = self.GetSelectionEnd();
        lastLine = self.LineFromPosition(selByteEnd)
        selByteStart = self.PositionFromLine(self.LineFromPosition(selByteStart))
        selByteEnd = self.PositionFromLine(lastLine + 1)

        if extendOverChildren:
            # Extend over all lines which are more indented than the last line

            lastLineDeep = StringOps.splitIndentDeepness(self.GetLine(lastLine))[0]

            testLine = lastLine + 1
            while True:
                testLineContent = self.GetLine(testLine)
                if len(testLineContent) == 0:
                    # End of text reached
                    break

                if StringOps.splitIndentDeepness(testLineContent)[0] <= lastLineDeep:
                    break

                testLine += 1

            selByteEnd = self.PositionFromLine(testLine)

        self.SetSelectionMode(0)
        self.SetSelectionStart(selByteStart)
        self.SetSelectionMode(0)
        self.SetSelectionEnd(selByteEnd)

        return selByteStart, selByteEnd



    def moveSelectedLinesOneUp(self, extendOverChildren):
        """
        Extend current selection to full logical lines and move selected lines
        upward one line.
        extendOverChildren -- iff true, extend selection over lines more indented
            below the initial selection
        """
        self.BeginUndoAction()
        try:
            selByteStart, selByteEnd = self._getExpandedByteSelectionToLine(
                    extendOverChildren)

            firstLine = self.LineFromPosition(selByteStart)
            if firstLine > 0:
                content = self.GetSelectedText()
                if len(content) > 0:
                    if content[-1] == u"\n":
                        selByteEnd -= 1
                    else:
                        content += u"\n"
                    # Now content ends with \n and selection end points
                    # before this newline
                    self.ReplaceSelection("")
                    target = self.PositionFromLine(firstLine - 1)
                    self.InsertText(target, content)
                    self.SetSelectionMode(0)
                    self.SetSelectionStart(target)
                    self.SetSelectionMode(0)
                    self.SetSelectionEnd(target + (selByteEnd - selByteStart))
        finally:
            self.EndUndoAction()



    def moveSelectedLinesOneDown(self, extendOverChildren):
        """
        Extend current selection to full logical lines and move selected lines
        upward one line.
        extendOverChildren -- iff true, extend selection over lines more indented
            below the initial selection
        """
        self.BeginUndoAction()
        try:
            selByteStart, selByteEnd = self._getExpandedByteSelectionToLine(
                    extendOverChildren)

            lastLine = self.LineFromPosition(selByteEnd)
            lineCount = self.GetLineCount() - 1
            if lastLine <= lineCount:
                content = self.GetSelectedText()
                if len(content) > 0:
                    # Now content ends with \n and selection end points
                    # before this newline
                    target = self.PositionFromLine(lastLine + 1)
                    target -= selByteEnd - selByteStart

                    if content[-1] == u"\n":  # Necessary for downward move?
                        selByteEnd -= 1
                    else:
                        content += u"\n"

                    self.ReplaceSelection("")
                    if self.GetTextRange(target - 1,
                            target) != u"\n":
                        self.InsertText(target, u"\n")
                        target += 1

                    self.InsertText(target, content)
                    self.SetSelectionMode(0)
                    self.SetSelectionStart(target)
                    self.SetSelectionMode(0)
                    self.SetSelectionEnd(target + (selByteEnd - selByteStart))
        finally:
            self.EndUndoAction()



    def OnKeyDown(self, evt):
        key = evt.GetKeyCode()

        self.lastKeyPressed = time()
        accP = getAccelPairFromKeyDown(evt)
        matchesAccelPair = self.presenter.getMainControl().keyBindings.\
                matchesAccelPair

#         if self.pageType == u"texttree":
#             if accP in ( (wx.ACCEL_ALT, wx.WXK_NUMPAD_UP),
#                     (wx.ACCEL_ALT, wx.WXK_UP),
#                     (wx.ACCEL_SHIFT | wx.ACCEL_ALT, wx.WXK_NUMPAD_UP),
#                     (wx.ACCEL_SHIFT | wx.ACCEL_ALT, wx.WXK_UP) ):
# 
#                 self.moveSelectedLinesOneUp(accP[0] & wx.ACCEL_SHIFT)
#                 return
#             elif accP in ( (wx.ACCEL_ALT, wx.WXK_NUMPAD_DOWN),
#                     (wx.ACCEL_ALT, wx.WXK_DOWN),
#                     (wx.ACCEL_SHIFT | wx.ACCEL_ALT, wx.WXK_NUMPAD_DOWN),
#                     (wx.ACCEL_SHIFT | wx.ACCEL_ALT, wx.WXK_DOWN) ):
#
#                 self.moveSelectedLinesOneDown(accP[0] & wx.ACCEL_SHIFT)
#                 return
# 
#             evt.Skip()


        if matchesAccelPair("AutoComplete", accP):
            # AutoComplete is normally Ctrl-Space
            # Handle autocompletion
            self.autoComplete()

        elif matchesAccelPair("ActivateLink2", accP):
            # ActivateLink2 is normally Ctrl-Return
            self.activateLink()

        elif matchesAccelPair("ActivateLinkBackground", accP):
            # ActivateLink2 is normally Ctrl-Return
            self.activateLink(tabMode=3)

        elif matchesAccelPair("ActivateLink", accP):
            # ActivateLink is normally Ctrl-L
            # There is also a shortcut for it. This can only happen
            # if OnKeyDown is called indirectly
            # from IncrementalSearchDialog.OnKeyDownInput
            self.activateLink()

        elif matchesAccelPair("ActivateLinkNewTab", accP):
            # ActivateLinkNewTab is normally Ctrl-Alt-L
            # There is also a shortcut for it. This can only happen
            # if OnKeyDown is called indirectly
            # from IncrementalSearchDialog.OnKeyDownInput
            self.activateLink(tabMode=2)

        elif matchesAccelPair("ActivateLinkNewWindow", accP):
            self.activateLink(tabMode=6)

        elif matchesAccelPair("LogLineUp", accP):
            # LogLineUp is by default undefined
            self.moveSelectedLinesOneUp(False)
        elif matchesAccelPair("LogLineUpWithIndented", accP):
            # LogLineUp is by default undefined
            self.moveSelectedLinesOneUp(True)
        elif matchesAccelPair("LogLineDown", accP):
            # LogLineUp is by default undefined
            self.moveSelectedLinesOneDown(False)
        elif matchesAccelPair("LogLineDownWithIndented", accP):
            # LogLineUp is by default undefined
            self.moveSelectedLinesOneDown(True)

        elif not evt.ControlDown() and not evt.ShiftDown():  # TODO Check all modifiers
            if key == wx.WXK_TAB:
                if self.pageType == u"form":
                    if not self._goToNextFormField():
                        self.presenter.getMainControl().showStatusMessage(
                                _(u"No more fields in this 'form' page"), -1)
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
            super(WikiTxtCtrl, self).OnKeyDown(evt)


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
            unichar = StringOps.mbcsDec(chr(key))[0]

        self.ReplaceSelection(unichar)


    if isLinux():
        def OnSetFocus(self, evt):
#             self.presenter.makeCurrent()
            evt.Skip()

            wikiPage = self.getLoadedDocPage()
            if wikiPage is None:
                return
            if not isinstance(wikiPage,
                    (DocPages.DataCarryingPage, DocPages.AliasWikiPage)):
                return

            try:
                wikiPage.checkFileSignatureAndMarkDirty()
            except (IOError, OSError, DbAccessError), e:
                self.presenter.getMainControl().lostAccess(e)


    else:
        def OnSetFocus(self, evt):
            self.presenter.makeCurrent()
            evt.Skip()

            wikiPage = self.getLoadedDocPage()
            if wikiPage is None:
                return
            if not isinstance(wikiPage,
                    (DocPages.DataCarryingPage, DocPages.AliasWikiPage)):
                return

            try:
                wikiPage.checkFileSignatureAndMarkDirty()
            except (IOError, OSError, DbAccessError), e:
                self.presenter.getMainControl().lostAccess(e)




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

        tabMode = Configuration.MIDDLE_MOUSE_CONFIG_TO_TABMODE[middleConfig]

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



#     def OnStyleDone(self, evt):
#         if evt.stylebytes:
#             self.applyStyling(evt.stylebytes)
#
#         if evt.foldingseq:
#             self.applyFolding(evt.foldingseq)
#


    def onIdleVisible(self, miscevt):
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

            astNodes = pageAst.findNodesForCharPos(charPos)

            if charPos > 0:
                # Maybe a token left to the cursor was meant, so check
                # one char to the left
                astNodes += pageAst.findNodesForCharPos(charPos - 1)

            callTip = None
            for astNode in astNodes:
                if astNode.name == "wikiWord":
                    threadstop.testRunning()
                    wikiWord = wikiDocument.getWikiPageNameForLinkTerm(
                            astNode.wikiWord)

                    # Set status to wikipage
                    callInMainThread(
                            self.presenter.getMainControl().showStatusMessage,
                            _(u"Link to page: %s") % wikiWord, 0)

                    if wikiWord is not None:
                        propList = wikiDocument.getAttributeTriples(
                                wikiWord, u"short_hint", None)
                        if len(propList) > 0:
                            callTip = propList[-1][2]
                            break
                elif astNode.name == "urlLink":
                    # Should we show image preview tooltips for local URLs?
                    if not self.presenter.getConfig().getboolean("main",
                            "editor_imageTooltips_localUrls", True):
                        continue

                    # Decision code taken from HtmlExporter.HtmlExporter._processUrlLink
                    if astNode.appendixNode is None:
                        appendixDict = {}
                    else:
                        appendixDict = dict(astNode.appendixNode.entries)
            
                    # Decide if this is an image link
                    if appendixDict.has_key("l"):
                        urlAsImage = False
                    elif appendixDict.has_key("i"):
                        urlAsImage = True
#                     elif self.asHtmlPreview and \
#                             self.mainControl.getConfig().getboolean(
#                             "main", "html_preview_pics_as_links"):
#                         urlAsImage = False
#                     elif not self.asHtmlPreview and self.addOpt[0]:
#                         urlAsImage = False
                    elif astNode.url.lower().split(".")[-1] in \
                            ("jpg", "jpeg", "gif", "png", "tif", "bmp"):
                        urlAsImage = True
                    else:
                        urlAsImage = False

                    # If link is a picture display it as a tooltip
                    if urlAsImage:
                        path = self.presenter.getWikiDocument()\
                                .makeFileUrlAbsPath(astNode.url)

                        if path is not None and isfile(path):
                            if imghdr.what(path):
                                config = self.presenter.getConfig()
                                maxWidth = config.getint("main",
                                        "editor_imageTooltips_maxWidth", 200)
                                maxHeight = config.getint("main",
                                        "editor_imageTooltips_maxHeight", 200)

                                def SetImageTooltip(path):
                                    self.tooltip_image = ImageTooltipPanel(self,
                                            path, maxWidth, maxHeight)
                                threadstop.testRunning()
                                callInMainThread(SetImageTooltip, path)
                            else:
                                callTip = _(u"Not a valid image")
                            break

            if callTip:
                threadstop.testRunning()
                callInMainThread(self.CallTipShow, bytePos, callTip)

        except NotCurrentThreadException:
            pass

    @contextlib.contextmanager
    def dwellLock(self):
        if self.dwellLockCounter == 0:
            self.OnDwellEnd(None)
        
        self.dwellLockCounter += 1
        yield
        self.dwellLockCounter -= 1


    def OnDwellStart(self, evt):
        if self.dwellLockCounter > 0:
            return

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


    def OnDwellEnd(self, evt):
        if self.dwellLockCounter > 0:
            return

        self.calltipThreadHolder.setThread(None)
        self.CallTipCancel()

        # Set status back to nothing
        callInMainThread(self.presenter.getMainControl().showStatusMessage, "",
                0)
        # And close any shown pic
        if self.tooltip_image:
            self.tooltip_image.Close()
            self.tooltip_image = None

    @staticmethod
    def userActionPasteFiles(unifActionName, paramDict):
        """
        User action to handle pasting or dropping of files into editor.
        """
        editor = paramDict.get("editor")
        if editor is None:
            return

        filenames = paramDict.get("filenames")
        x = paramDict.get("x")
        y = paramDict.get("y")

        dlgParams = WikiTxtDialogs.FilePasteParams()
#             config = editor.presenter.getMainControl().getConfig()
        dlgParams.readOptionsFromConfig(
                editor.presenter.getMainControl().getConfig())

        if unifActionName == u"action/editor/this/paste/files/insert/url/ask":
            # Ask user
            if not paramDict.get("processDirectly", False):
                # If files are drag&dropped, at least on Windows the dragging
                # source (e.g. Windows Explorer) is halted until the drop
                # event returns.
                # So do an idle call to open dialog later
                paramDict["processDirectly"] = True
                wx.CallAfter(WikiTxtCtrl.userActionPasteFiles, unifActionName,
                        paramDict)
                return

            dlgParams = WikiTxtDialogs.FilePasteDialog.runModal(
                    editor.presenter.getMainControl(), -1, dlgParams)
            if dlgParams is None:
                # User abort
                return

            unifActionName = dlgParams.unifActionName

        moveToStorage = False

        if unifActionName == u"action/editor/this/paste/files/insert/url/absolute":
            modeToStorage = False
            modeRelativeUrl = False
        elif unifActionName == u"action/editor/this/paste/files/insert/url/relative":
            modeToStorage = False
            modeRelativeUrl = True
        elif unifActionName == u"action/editor/this/paste/files/insert/url/tostorage":
            modeToStorage = True
            modeRelativeUrl = False
        elif unifActionName == u"action/editor/this/paste/files/insert/url/movetostorage":
            modeToStorage = True
            modeRelativeUrl = False
            moveToStorage = True
        else:
            return

        try:
            prefix = StringOps.strftimeUB(dlgParams.rawPrefix)
        except:
            traceback.print_exc()
            prefix = u""   # TODO Error message?

        try:
            middle = StringOps.strftimeUB(dlgParams.rawMiddle)
        except:
            traceback.print_exc()
            middle = u" "   # TODO Error message?

        try:
            suffix = StringOps.strftimeUB(dlgParams.rawSuffix)
        except:
            traceback.print_exc()
            suffix = u""   # TODO Error message?


        urls = []

        for fn in filenames:
            protocol = None
            if fn.endswith(u".wiki"):
                protocol = "wiki"

            toStorage = False
            if modeToStorage and protocol is None:
                # Copy file into file storage
                fs = editor.presenter.getWikiDocument().getFileStorage()
                try:
                    fn = fs.createDestPath(fn, move=moveToStorage)
                    toStorage = True
                except Exception, e:
                    traceback.print_exc()
                    editor.presenter.getMainControl().displayErrorMessage(
                            _(u"Couldn't copy file"), e)
                    return

            urls.append(editor.wikiLanguageHelper.createUrlLinkFromPath(
                    editor.presenter.getWikiDocument(), fn,
                    relative=modeRelativeUrl or toStorage,
                    bracketed=dlgParams.bracketedUrl, protocol=protocol))

        editor.handleDropText(x, y, prefix + middle.join(urls) + suffix)


    def GetEOLChar(self):
        """
        Gets the end of line char currently being used
        """
        m_id = self.GetEOLMode()
        if m_id == wx.stc.STC_EOL_CR:
            return u'\r'
        elif m_id == wx.stc.STC_EOL_CRLF:
            return u'\r\n'
        else:
            return u'\n'

    def GetLastVisibleLine(self):
        """
        Returns line number of the first visible line in viewport
        """
        return self.GetFirstVisibleLine() + self.LinesOnScreen() - 1

    def GetMiddleVisibleLine(self):
        """
        Returns line number of the middle visible line in viewport
        """
        fl = self.GetFirstVisibleLine()
        ll = self.GetLastVisibleLine()

        lines = ll - fl

        mid = fl + lines // 2
        print fl, ll
        # TODO: Fix this for long lines

        #if self.LinesOnScreen() < self.GetLineCount():
        #    # This may return a float with .5  Really wanted? (MB)
        #    mid = (fl + (self.LinesOnScreen() / 2))
        #else:
        #    mid = (fl + (self.GetLineCount() / 2))
        return mid

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
                    text = StringOps.lineendToInternal(text)
                    self.OnDropText(x, y, text)

            return defresult

        finally:
            self.resetDObject()


    def OnDropText(self, x, y, text):
        text = StringOps.lineendToInternal(text)
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
                filenames = [StringOps.utf8Dec(fn.encode("latin-1"))[0]
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
# _ACTION_EDITOR_PASTE_FILES_ABSOLUTE = UserActionCoord.SimpleAction("",
#         u"action/editor/this/paste/files/insert/url/absolute",
#         WikiTxtCtrl.userActionPasteFiles)
#
# _ACTION_EDITOR_PASTE_FILES_RELATIVE = UserActionCoord.SimpleAction("",
#         u"action/editor/this/paste/files/insert/url/relative",
#         WikiTxtCtrl.userActionPasteFiles)
#
# _ACTION_EDITOR_PASTE_FILES_TOSTORAGE = UserActionCoord.SimpleAction("",
#         u"action/editor/this/paste/files/insert/url/tostorage",
#         WikiTxtCtrl.userActionPasteFiles)
#
# _ACTION_EDITOR_PASTE_FILES_ASK = UserActionCoord.SimpleAction("",
#         u"action/editor/this/paste/files/insert/url/ask",
#         WikiTxtCtrl.userActionPasteFiles)
#
#
# _ACTIONS = (
#         _ACTION_EDITOR_PASTE_FILES_ABSOLUTE, _ACTION_EDITOR_PASTE_FILES_RELATIVE,
#         _ACTION_EDITOR_PASTE_FILES_TOSTORAGE, _ACTION_EDITOR_PASTE_FILES_ASK)


# Register paste actions
_ACTIONS = tuple( UserActionCoord.SimpleAction("", unifName,
        WikiTxtCtrl.userActionPasteFiles) for unifName in (
            u"action/editor/this/paste/files/insert/url/absolute",
            u"action/editor/this/paste/files/insert/url/relative",
            u"action/editor/this/paste/files/insert/url/tostorage",
            u"action/editor/this/paste/files/insert/url/movetostorage",
            u"action/editor/this/paste/files/insert/url/ask") )


UserActionCoord.registerActions(_ACTIONS)



_CONTEXT_MENU_INTEXT_SPELLING = \
u"""
-
Ignore;CMD_ADD_THIS_SPELLING_SESSION
Add Globally;CMD_ADD_THIS_SPELLING_GLOBAL
Add Locally;CMD_ADD_THIS_SPELLING_LOCAL
"""


_CONTEXT_MENU_INTEXT_BASE = \
u"""
-
Undo;CMD_UNDO
Redo;CMD_REDO
-
Cut;CMD_CLIPBOARD_CUT
Copy;CMD_CLIPBOARD_COPY
Paste;CMD_CLIPBOARD_PASTE
Delete;CMD_TEXT_DELETE
-
Select All;CMD_SELECT_ALL
"""


_CONTEXT_MENU_INTEXT_ACTIVATE = \
u"""
-
Follow Link;CMD_ACTIVATE_THIS
Follow Link New Tab;CMD_ACTIVATE_NEW_TAB_THIS
Follow Link New Tab Backgrd.;CMD_ACTIVATE_NEW_TAB_BACKGROUND_THIS
Follow Link New Window;CMD_ACTIVATE_NEW_WINDOW_THIS
"""

_CONTEXT_MENU_INTEXT_WIKI_URL = \
u"""
-
Convert Absolute/Relative File URL;CMD_CONVERT_URL_ABSOLUTE_RELATIVE_THIS
Open Containing Folder;CMD_OPEN_CONTAINING_FOLDER_THIS
"""

_CONTEXT_MENU_INTEXT_FILE_URL = \
u"""
-
Convert Absolute/Relative File URL;CMD_CONVERT_URL_ABSOLUTE_RELATIVE_THIS
Open Containing Folder;CMD_OPEN_CONTAINING_FOLDER_THIS
Rename file;CMD_RENAME_FILE
Delete file;CMD_DELETE_FILE
"""


_CONTEXT_MENU_INTEXT_URL_TO_CLIPBOARD = \
u"""
-
Copy Anchor URL to Clipboard;CMD_CLIPBOARD_COPY_URL_TO_THIS_ANCHOR
"""

_CONTEXT_MENU_SELECT_TEMPLATE_IN_TEMPLATE_MENU = \
u"""
-
Other...;CMD_SELECT_TEMPLATE
"""

_CONTEXT_MENU_SELECT_TEMPLATE = \
u"""
-
Use Template...;CMD_SELECT_TEMPLATE
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
if False:
    N_(u"Ignore")
    N_(u"Add Globally")
    N_(u"Add Locally")

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
    N_(u"Follow Link New Window")

    N_(u"Convert Absolute/Relative File URL")
    N_(u"Open Containing Folder")
    N_(u"Rename file")
    N_(u"Delete file")

    N_(u"Copy anchor URL to clipboard")

    N_(u"Other...")
    N_(u"Use Template...")

    N_(u"Close Tab")

    N_(u"Show folding")
    N_(u"Show folding marks and allow folding")
    N_(u"&Toggle current folding")
    N_(u"Toggle folding of the current line")
    N_(u"&Unfold All")
    N_(u"Unfold everything in current editor")
    N_(u"&Fold All")
    N_(u"Fold everything in current editor")


# I will move this to wxHelper later (MB)
try:
    class wxPopupOrFrame(wx.PopupWindow):
        def __init__(self, parent, id=-1, style=None):
            wx.PopupWindow.__init__(self, parent)

except AttributeError:
    class wxPopupOrFrame(wx.Frame):
        def __init__(self, parent, id=-1,
                style=wx.NO_BORDER|wx.FRAME_NO_TASKBAR|wx.FRAME_FLOAT_ON_PARENT):
            wx.Frame.__init__(self, parent, id, style=style)


class ImageTooltipPanel(wxPopupOrFrame):
    """Quick panel for image tooltips"""
    def __init__(self, pWiki, filePath, maxWidth=200, maxHeight=200):
        wxPopupOrFrame.__init__(self, pWiki, -1)

        self.url = filePath
        self.pWiki = pWiki
        self.firstMove = True
        
        img = wx.Image(filePath, wx.BITMAP_TYPE_ANY)

        origWidth = img.GetWidth()
        origHeight = img.GetHeight()

        # Set defaults for invalid values
        if maxWidth <= 0:
            maxWidth = 200
        if maxHeight <= 0:
            maxHeight = 200

        if origWidth > 0 and origHeight > 0:
            self.width, self.height = calcResizeArIntoBoundingBox(origWidth,
                    origHeight, maxWidth, maxHeight)
            
            img.Rescale(self.width, self.height, quality = wx.IMAGE_QUALITY_HIGH)
        else:
            self.width = origWidth
            self.height = origHeight

        img = img.ConvertToBitmap()

        self.SetSize((self.width, self.height))

        self.bmp = wx.StaticBitmap(self, -1, img, (0, 0), (img.GetWidth(), img.GetHeight()))
        self.bmp.Bind(wx.EVT_LEFT_DOWN, self.OnLeftClick)
        self.bmp.Bind(wx.EVT_RIGHT_DOWN, self.OnRightClick)
        self.bmp.Bind(wx.EVT_MOTION, self.OnMouseMotion)
        self.Bind(wx.EVT_KEY_DOWN, self.OnKeyDown)

        mousePos = wx.GetMousePosition()
        # If possible the frame shouldn't be exactly under mouse pointer
        # so doubleclicking on link works
        mousePos.x += 1
        mousePos.y += 1
        WindowLayout.setWindowPos(self, mousePos, fullVisible=True)

        self.Show()
        # Works for Windows (but not for GTK), maybe also for Mac (MB)
        self.GetParent().SetFocus()  

    def Close(self, event=None):
        self.Destroy()

    def OnLeftClick(self, event=None):
#         scrPos = self.ClientToScreen(evt.GetPosition())
        self.Close()
#         wnd = wx.FindWindowAtPoint(scrPos)
#         print "--OnLeftClick1", repr((self, wnd))
#         if wnd is not None:
#             cliPos = wnd.ScreenToClient(scrPos)
#             evt.m_x = cliPos.x
#             evt.m_y = cliPos.y
#             wnd.ProcessEvent(evt)

    def OnRightClick(self, event=None):
        self.Close()

    def OnMouseMotion(self, evt):
        if self.firstMove:
            self.firstMove = False
            evt.Skip()
            return

        self.Close()


    def OnKeyDown(self, event):
        kc = event.GetKeyCode()

        if kc == wx.WXK_ESCAPE:
            self.Close()


class ViHandler(ViHelper):
    # TODO: Add search commands
    #       Fix long line inconsistency?
    #       Brace matching - finish % cmd
    #       Find a way to monitor selection (to enter visual mode from mouse selecttion)
    
    def __init__(self, stc):
        ViHelper.__init__(self, stc)

        wx.CallAfter(self.SetDefaultCaretColour)
        # Set default mode
        wx.CallAfter(self.SetMode, ViHelper.NORMAL)

        """
        pre_keys holds all the keys that can be used as "power" modifiers
            i.e. they can be followed by other commands (or a range of
                 inputs)

        In general there are three types,
            1. those that can be followed by any motion commands
                e.g. dyc<>
            2. those that can be followed by a wide range of inputs
                e.g. mr
            3. same as 2 but can be prefixed by commands in 1 (they
               are motion commands themselves)
                e.g. '`ft
        """
        self.pre_keys = {
                        0 : {
                            60  : (1, self.DedentSingle, 1), # <
                            62  : (1, self.IndentSingle, 1), # >
                            99  : (1, self.EndDeleteInsert, 2), # c
                            100 : (1, self.EndDelete, 1), # d
                            121 : (1, self.Yank, 0), # y
                            39  : (3, self.GotoMark, 0), # '
                            96  : (3, self.GotoMarkIndent, 0), # `
                            109 : (2, self.Mark, 0), # m
                            102 : (3, self.FindNextChar, 0), # f
                            70  : (3, self.FindNextCharBackwards, 0), # F
                            116 : (3, self.FindUpToNextChar, 0), # t
                            84  : (3, self.FindUpToNextCharBackwards, 0), # T
                            114 : (2, self.ReplaceChar, 2), # r
                            },
                        2 : {
                            # In visual mode a number of keys no longer
                            # act as modifiers
                            39  : (3, self.GotoMark, 0), # '
                            96  : (3, self.GotoMarkIndent, 0), # `
                            109 : (2, self.Mark, 0), # m
                            102 : (3, self.FindNextChar, 0), # f
                            70  : (3, self.FindNextCharBackwards, 0), # F
                            116 : (3, self.FindUpToNextChar, 0), # t
                            84  : (3, self.FindUpToNextCharBackwards, 0), # T
                            114 : (2, self.ReplaceChar, 2), # r
                    }
                }

        self.pre_motion_keys = defaultdict(dict)
        for j in self.pre_keys:
            self.pre_motion_keys[j] = \
                    [i for i in self.pre_keys[j] if self.pre_keys[j][i][0] == 1]

    # Format
    # key code : (command type, (function, arguments), repeatable)

    # command type -
    #               0 : Normal
    #               1 : Motion
    #               2 : Mode change

    # function : function to call on keypress

    # arguments : arguments can be None, a single argument or a dictionary

    # repeatable - repeat types
    #               0 : Not repeatable
    #               1 : Normal repeat
    #               2 : Repeat with insertion (i.e. i/a/etc)
    #               3 : Replacet
    #               4 : Find reverse
    #               5 : Find forward
        self.keys = {
            0 : {
            # Normal mode
    (105) : (0, (self.Insert, None), 2), # i
    (97) : (0, (self.Append, None), 2), # a
    (73) : (0, (self.InsertAtLineStart, None), 2), # I
    (65) : (0, (self.AppendAtLineEnd, None), 2), # A
    (111) : (0, (self.OpenNewLine, False), 2), # o
    (79) : (0, (self.OpenNewLine, True), 2), # O
    (67) : (0, (self.TruncateLineAndInsert, None), 2), # C
    (68) : (0, (self.TruncateLine, None), 2), # D

    (120) : (0, (self.DeleteRight, None), 1), # x
    (88) : (0, (self.DeleteLeft, None), 1), # X

    (115) : (0, (self.DeleteRightAndInsert, None), 2), # s
    (83) : (0, (self.DeleteLinesAndIndentInsert, None), 2), # S

    (119) : (1, (self.MoveCaretNextWord, None), 0), # w
    (87) : (1, (self.MoveCaretNextWORD, None), 0), # W
    (101) : (1, (self.MoveCaretWordEnd, None), 0), # e
    (69) : (1, (self.MoveCaretWordEND, None), 0), # E
    (98) : (1, (self.MoveCaretBackWord, None), 0), # b
    (66) : (1, (self.MoveCaretBackWORD, None), 0), # B

    (105, 119) : (1, (self.SelectInWord, None), 0), # iw
    (105, 108) : (1, (self.SelectInLink, None), 0), # il
    (105, 91) : (1, (self.SelectInLink, None), 0), # i[
    (105, 93) : (1, (self.SelectInLink, None), 0), # i]

    (123) : (1, (self.Repeat, self.ctrl.ParaUp), 0), # {
    (125) : (1, (self.Repeat, self.ctrl.ParaDown), 0), # }

    # TODO: complete search
    # Search should use a custom implementation of wikidpads incremental search
    47  : (0, (self.StartSearch, None), 0), # /
    #47  : (0, (self.StartSearchReverse, None), 0), # /
    110 : (1, (self.Repeat, self.ContinueLastSearchSameDirection), 0), # n
    78 : (1, (self.Repeat, self.ContinueLastSearchReverseDirection), 0), # N

    42 : (1, (self.Repeat, self.SearchCaretWordForwards), 0), # *
    35 : (1, (self.Repeat, self.SearchCaretWordBackwards), 0), # #

    (103, 42)  : (1, (self.Repeat, self.SearchPartialCaretWordForwards), 0), # g*
    (103, 35)  : (1, (self.Repeat, self.SearchPartialCaretWordBackwards), 0), # g#

    # Basic movement
    (104) : (1, (self.MoveCaretLeft, None), 0), # h
    (107) : (1, (self.MoveCaretUp, None), 0), # k
    (108) : (1, (self.MoveCaretRight, None), 0), # l
    (106) : (1, (self.MoveCaretDown, None), 0), # j
    # Arrow keys
    (65361) : (1, (self.MoveCaretLeft, None), 0), # left 
    (65362) : (1, (self.MoveCaretUp, None), 0), # up
    (65363) : (1, (self.MoveCaretRight, None), 0), # right
    (65364) : (1, (self.MoveCaretDown, None), 0), # down

    (65293) : (1, (self.MoveCaretDownAndIndent, None), 0), # enter
    (65293) : (1, (self.MoveCaretDownAndIndent, None), 0), # return

    # Line movement
    (36)  : (1, (self.GotoLineEnd, None), 0), # 0
    (48)  : (1, (self.GotoLineStart, None), 0), # $
    (94)  : (1, (self.GotoLineIndent, None), 0), # ^
    (124) : (1, (self.GotoColumn, None), 0), # |

    # Page scroll control
    (103, 103)  : (1, (self.DocumentNavigation, (103, 103)), 0), # gg
    (71)        : (1, (self.DocumentNavigation, 71), 0), # G
    (37)        : (1, (self.DocumentNavigation, 37), 0), # %

    (72)        : (1, (self.GotoViewportTop, None), 0), # H
    (76)        : (1, (self.GotoViewportBottom, None), 0), # L
    (77)        : (1, (self.GotoViewportMiddle, None), 0), # M

    (122, 122)  : (0, (self.ScrollViewportMiddle, None), 0), # zz
    (122, 116)  : (0, (self.ScrollViewportTop, None), 0), # zt
    (122, 98)   : (0, (self.ScrollViewportBottom, None), 0), # zb

    (90, 90)    : (0, (self.ctrl.presenter.getMainControl().\
                                        exitWiki, None), 0), # ZZ

    (117)           : (0, (self.Undo, None), 0), # u
    ("ctrl", 114)   : (0, (self.Redo, None), 0), # ctrl-r (already bound)

    # These two are motions
    (59)   : (1, (self.RepeatLastForwardFindCharCmd, None), 0), # ;
    (44)   : (1, (self.RepeatLastBackwardFindCharCmd, None), 0), # ,

    # Replace ?
    #(114)   : (1, (self.ReplaceChar, None)), # r
    # repeatable?
    (82)   : (0, (self.StartReplaceMode, None), 0), # R

    (118)   : (2, (self.EnterVisualMode, None), 0), # v
    (86)   : (2, (self.EnterLineVisualMode, None), 0), # V

    (74)   : (0, (self.JoinLines, None), 1), # J

    (126)   : (0, (self.SwapCase, None), 0), # ~

    (121, 121)  : (0, (self.YankLine, None), 0), # yy
    (89)        : (0, (self.YankLine, None), 0), # Y
    (112)       : (0, (self.Put, False), 0), # p
    (80)        : (0, (self.Put, True), 0), # P

    (100, 100)  : (0, (self.DeleteLine, None), 1), # dd

    (62, 62)    : (0, (self.Indent, True), 1), # >>
    (60, 60)    : (0, (self.Indent, False), 1), # <<

    (46)    : (0, (self.RepeatCmd, None), 0), # .

    # Wikipage navigation
    # As some command (e.g. HL) are already being used in most cases
    # these navigation commands have been prefixed by "g".
    # TODO: different repeat command for these?
    (103, 102)  : (0, (self.ctrl.activateLink, { "tabMode" : 0 }), 0), # gf
    (103, 70)   : (0, (self.ctrl.activateLink, { "tabMode" : 2 }), 0), # gF
    (103, 98)   : (0, (self.ctrl.activateLink, { "tabMode" : 3 }), 0), # gb
    # This might be going a bit overboard with history nagivaiton!
    (103, 72)   : (0, (self.GoBackwardInHistory, None), 0), # gH
    (103, 76)   : (0, (self.GoForwardInHistory, None), 0), # gL
    (103, 104)  : (0, (self.GoBackwardInHistory, None), 0), # gh
    (103, 108)  : (0, (self.GoForwardInHistory, None), 0), # gl
    (91)        : (0, (self.GoBackwardInHistory, None), 0), # [
    (93)        : (0, (self.GoForwardInHistory, None), 0), # ]
    (103, 116) : (0, (self.SwitchTabs, None), 0), # gt
    (103, 84)  : (0, (self.SwitchTabs, True), 0), # gT
    (103, 114) : (0, (self.OpenHomePage, False), 0), # gr
    (103, 82) : (0, (self.OpenHomePage, True), 0), # gR
    (103, 117) : (0, (self.ViewParents, False), 0), # gu
    (103, 85) : (0, (self.ViewParents, True), 0), # gU
    (103, 111) : (0, (self.ctrl.presenter.getMainControl()). \
                                    showWikiWordOpenDialog, None, 0), # go
    # TODO: rewrite open dialog so it can be opened with new tab as default
    (103, 79): (0, (self.ctrl.presenter.getMainControl()). \
                                    showWikiWordOpenDialog, None, 0), # gO

    (103, 115)  : (0, (self.SwitchEditorPreview, None), 0), # gs
    (103, 101)  : (0, (self.SwitchEditorPreview, "textedit"), 0), # ge
    (103, 112)  : (0, (self.SwitchEditorPreview, "preview"), 0), # gp
    (65470)     : (0, (self.SwitchEditorPreview, "textedit"), 0), # F1
    (65471)     : (0, (self.SwitchEditorPreview, "preview"), 0), # F2
            }
            }

        # Rather than rewrite all the keys for other modes it is easier just
        # to modify those that need to be changed

        # VISUAL MODE
        self.keys[2] = self.keys[0].copy()
        self.keys[2].update({
                99  : (0, (self.DeleteSelectionAndInsert, None), 2), # c
                100  : (0, (self.DeleteSelection, None), 1), # d
                120  : (0, (self.DeleteSelection, None), 1), # x
                121 : (0, (self.YankSelection, None), 0), # y
                89 : (0, (self.YankSelection, True), 0), # Y
                60 : (0, (self.Indent, {"forward":False, "visual":True}), 0), # <
                62 : (0, (self.Indent, {"forward":True, "visual":True}), 0), # >
                (117) : (0, (self.LowerCase, None), 0), # u
                (85) : (0, (self.UpperCase, None), 0), # U
                #(105, 119) : (1, (self.SelectInWord, None), 0), # iw
            })
        # And delete a few so our key mods are correct
        # These are keys that who do not serve the same function in visual mode
        # as in normal mode (and it most cases are replaced by other function)
        del self.keys[2][(100, 100)] # dd
        del self.keys[2][(121, 121)] # yy
        del self.keys[2][(105)] # i


        self.key_mods = self.GenerateKeyModifiers(self.keys)

    def SetNumber(self, n):
        # If 0 is first modifier it is a command
        if len(self.key_number_modifier) < 1 and n == 0:
            return False
        self.key_number_modifier.append(n)
        self.key_modifier = []
        self.updateViStatus(True)
        return True


    def SetMode(self, mode):
        """
        It would be nice to set caret alpha but i don't think its
        possible at the moment
        """
        # If switching from insert mode vi does a few things
        if self.mode == ViHelper.INSERT:
            # Move back one pos if not at the start of a line
            if self.ctrl.GetCurrentPos() != \
                    self.GetLineStartPos(self.ctrl.GetCurrentLine()):
                self.ctrl.CharLeft()

            if self.mode == ViHelper.INSERT:
                # If current line only contains whitespace remove it
                if self.ctrl.GetCurLine()[0].strip() == u"":
                    self.ctrl.LineDelete()
                    self.ctrl.AddText(self.ctrl.GetEOLChar())
                    self.ctrl.CharLeft()
        
        self.mode = mode

        # Save caret position
        self.ctrl.ChooseCaretX()

        if mode == ViHelper.NORMAL:
            # Set block caret
            #self.ctrl.SendMsg(2512, 2)
            #self.ctrl.SetSelectionMode(0)
            self.RemoveSelection()
            self.ctrl.SetCaretForeground(wx.Colour(255, 0, 0))
            self.ctrl.SetCaretWidth(40)
            self.ctrl.SetOvertype(False)
            self.SetSelMode("NORMAL")
        elif mode == ViHelper.VISUAL:
            self.ctrl.SetCaretWidth(40)
            self.ctrl.SetCaretForeground(wx.Colour(250, 250, 210))
            self.ctrl.SetOvertype(False)
        elif mode == ViHelper.INSERT:
            self.insert_action = []
            self.ctrl.SetCaretWidth(1)
            self.ctrl.SetCaretForeground(self.default_caret_colour)
            self.ctrl.SetOvertype(False)
        elif mode == ViHelper.REPLACE:
            self.ctrl.SetCaretWidth(1)
            self.ctrl.SetCaretForeground(self.default_caret_colour)
            self.ctrl.SetOvertype(True)

    def OnLeftMouseUp(self, evt):
        """Enter visual mode if text is selected by mouse"""
        if len(self.ctrl.GetSelectedText()) > 0:
            self.EnterVisualMode(True)
        else:
            self.LeaveVisualMode()
        evt.Skip()

    def OnViKeyDown(self, evt):
        """
        Handle keypresses when in Vi mode
        """

        key = evt.GetRawKeyCode()

        print key, unichr(key)

        # Pass modifier keys on
        if key in (65505, 65507, 65513):
            return

        accP = getAccelPairFromKeyDown(evt)


#         if control_mask:
#             if key == 102: # f
#                 self.startIncrementalSearch()

        if key == 65307 or accP == (2, 91): # Escape
            # TODO: Move into ViHandler?
            self.SetMode(ViHandler.NORMAL)
            self.FlushBuffers()
            return

        # There might be a better way to monitor for selection changed
        if len(self.ctrl.GetSelectedText()) > 0:
            self.EnterVisualMode()

        if self.mode in [1, 3]: # Insert mode, replace mode, 
            # Store each keyevent
            # NOTE: this may be terribly inefficient (i'm not sure)
            # It would be possbile to just store the text that is inserted
            # however then actions would be ignored
            self.insert_action.append(key)
            if key in [65362, 65362]:
                self.insert_action = []
            evt.Skip()
            return

        m = self.mode

        # As soon as a non-motion pre command has been set the next
        # key must be valid or the input will be lost
        # As with self. counts have to be specified prior to this
        if self.pre_key is not None:
            # TODO: make these commands repeatable
            # If self.pre_motion_key is also set we need to prepare for the motion
            if self.pre_motion_key is not None and self.pre_keys[m][self.pre_key][0] == 3:
                self.StartSelection()
                # Run the motion
                self.pre_keys[m][self.pre_key][1](key)
                # Post pre_motion_key action
                self.pre_keys[m][self.pre_motion_key][1]()
                self.FlushBuffers()
                return

            # Otherwise we just run it normally
            else:
                self.pre_keys[m][self.pre_key][1](key)
                self.FlushBuffers()
                return

        control_mask = False
        if accP[0] == 2: # Ctrl
            control_mask = True

        if 48 <= key <= 57: # Normal
            if self.SetNumber(key-48):
                return
        elif 65456 <= key <= 65465: # Numpad
            if self.SetNumber(key-65456):
                return

        self.SetCount()

        # First check if key is one one that can prefix motion commands
        if not self.block_pre_keys:
            if self.pre_motion_key is None and key in self.pre_motion_keys[m]:
                self.pre_motion_key = key
                self.updateViStatus(True)
                return
            # If not is it one of the other pre keys?
            elif key in self.pre_keys[m] and key not in self.pre_motion_keys[m]:
                self.pre_key = key
                self.updateViStatus(True)
                return

        self.key_modifier.append(key)
        if len(self.key_modifier) > 1:
            key = tuple(self.key_modifier)

        self.updateViStatus()

        if key in self.keys[m]:
            self.RunFunction(key, self.pre_motion_key)
            return 
        elif key in self.key_mods[m]:
            self.block_pre_keys = True

            if self.pre_motion_key is not None:
                temp_key = (self.pre_motion_key, key)

                if temp_key in self.keys[m]:
                    self.RunFunction(temp_key, None)

            return

        # If we've reached this point key hasn't been recogised so
        # clear buffers
        self.FlushBuffers()

    def TurnOff(self):
        self.ctrl.SetCaretWidth(1)

    def GetChar(self, length=1):
        """
        Retrieves text from under caret
        @param length: the number of characters to get
        """
        pos = self.ctrl.GetCurrentPos()
        start, end = self.minmax(pos, pos + length)
        start = max(0, start)
        end = min(end, self.ctrl.GetLength())
        return self.ctrl.GetTextRange(start, end)

    def EmulateKeypresses(self, actions):
        if len(actions) > 0:

            eol = self.ctrl.GetEOLChar()
            
            for i in actions:
                if i == 65361:
                    self.ctrl.CharLeft()
                elif i == 65363:
                    self.ctrl.CharRight()
                elif i == 65288:
                    self.ctrl.DeleteBackNotLine()
                elif i in [65535, 65439]:
                    self.ctrl.CharRight()
                    self.ctrl.DeleteBack()
                elif i in [65293, 65421]: # enter, return
                    self.ctrl.InsertText(self.ctrl.GetCurrentPos(), eol)
                    self.ctrl.CharRight()
                elif i == 65289: # tab
                    self.ctrl.InsertText(self.ctrl.GetCurrentPos(), "\t")
                    self.ctrl.CharRight()
                else:
                    self.ctrl.InsertText(self.ctrl.GetCurrentPos(), unichr(i))
                    self.ctrl.CharRight()
        
    
    def RepeatCmd(self):
        # TODO: clean this up
        if self.last_cmd is not None:
            self.visualBell("GREEN")
            self.ctrl.BeginUndoAction()
            cmd_type, key, count, pre_motion_key = self.last_cmd

            self.count = count
            actions = self.insert_action
            # NOTE: Is "." only going to repeat editable commands as in vim?
            if cmd_type == 1:
                self.RunFunction(key, pre_motion_key)
            elif cmd_type == 2: # + insertion
                self.RunFunction(key, pre_motion_key)
                # Emulate keypresses
                # Return to normal mode
                self.EmulateKeypresses(actions)
                self.SetMode(ViHandler.NORMAL)
            elif cmd_type == 3:
                self.ReplaceChar(key)
            elif cmd_type == 4: # reverse repeat
                self.pre_motion_key = pre_motion_key
                self.StartSelection()
                self.RepeatLastBackwardFindCharCmd()
                pre_key_type = self.pre_keys[self.mode][pre_motion_key][2] 
                self.pre_keys[self.mode][pre_motion_key][1]()
                if pre_key_type == 2:
                    self.EmulateKeypresses(actions)
                    self.SetMode(ViHandler.NORMAL)
            elif cmd_type == 5: # forward repeat
                self.pre_motion_key = pre_motion_key
                self.StartSelection()
                self.RepeatLastForwardFindCharCmd()
                pre_key_type = self.pre_keys[self.mode][pre_motion_key][2] 
                self.pre_keys[self.mode][pre_motion_key][1]()
                if pre_key_type == 2:
                    self.EmulateKeypresses(actions)
                    self.SetMode(ViHandler.NORMAL)
            self.ctrl.EndUndoAction()
            self.insert_action = actions
        else:
            self.visualBell("RED")


#--------------------------------------------------------------------
# Misc stuff
#--------------------------------------------------------------------
    def SelectFullLines(self):
        """
        Could probably be replaced by SetSectionMode,
        if it can be made to work.
        """
        start_line, end_line = self._GetSelectedLines()
        print start_line, end_line
        if self.ctrl.GetCurrentPos() >= self.visual_line_start_pos:
            reverse = False

            # Hack needed if selection is started on empty line
            if len(self.ctrl.GetLine(start_line)) > 1:
                text, pos = self.ctrl.GetCurLine()
                if len(text) > 1:
                    end_line -= 1

        else:
            reverse = True
            end_line -= 1

        cur_line = self.ctrl.GetCurrentLine()
        self.SelectLines(start_line, end_line, reverse)


    def JoinLines(self):
        text = self.ctrl.GetSelectedText()
        start_line = self.ctrl.GetCurrentLine()
        if len(text) < 1:
            # We need at least 2 lines to be able to join
            count = self.count if self.count > 1 else 2
            self.SelectLines(start_line, min(self.ctrl.GetLineCount(), \
                                                    start_line - 1 + count))
        else:
            start_line, end_line = self._GetSelectedLines()
            self.SelectLines(start_line, end_line)

        text = self.ctrl.GetSelectedText()

        eol_char = self.ctrl.GetEOLChar()

        # Probably not the most efficient way to do this
        # We need to lstrip every line except the first
        lines = text.split(eol_char)
        new_text = []
        for i in range(len(lines)):
            if lines[i] == u"": # Leave out empty lines
                continue
            if i == 0:
                new_text.append(lines[i])
            else:   
                new_text.append(lines[i].lstrip())
            
        self.ctrl.ReplaceSelection(" ".join(new_text))

    def DeleteSelection(self):
        self.ctrl.Clear()

    def DeleteSelectionAndInsert(self):
        self.DeleteSelection()
        self.Insert()


    def RemoveSelection(self):
        """
        Removes the selection.

        TODO: don't goto selection start pos
        """
        pos = self.ctrl.GetAnchor()
        self.ctrl.SetSelection(pos,pos)

    def StartSelection(self):
        """ Saves the current position to be used for selection start """
        self._anchor = self.ctrl.GetCurrentPos()

    def StartSelectionAtAnchor(self):
        """
        Saves the current position to be used for selection start using
        the anchor as the selection start.
        """
        if len(self.ctrl.GetSelectedText()) > 0:
            self._anchor = self.ctrl.GetAnchor()
        else:
            self._anchor = self.ctrl.GetCurrentPos()

    def SelectInWord(self):
        pos = self.ctrl.GetCurrentPos()
        if pos > 0 and re.match("\W", unichr(self.ctrl.GetCharAt(pos-1))) is None:
            self.MoveCaretBackWord(1)
        self.StartSelection()
        self.MoveCaretWordEnd(1)
        self.SelectSelection()

    def SelectInLink(self):
        pos = self.ctrl.GetCurrentPos()
        start_pos = self.FindChar(91, True, 0, 1, False)
        self.StartSelection()
        end_pos = self.FindChar(93, False, -1, 1, False)

        if start_pos and end_pos:
            self.SelectSelection()

    def SelectSelection(self):
        self.ctrl.SetSelection(self._anchor, self.ctrl.GetCurrentPos())

    def SelectionOnSingleLine(self):
        """
        Assume that if an EOL char is present we have mutiple lines
        """
        if self.ctrl.GetEOLChar() in self.ctrl.GetSelectedText():
            return False
        else:
            return True

    def DeleteSelection(self):
        """Yank selection and delete it"""
        start, end = self._GetSelectionRange()
        self.ctrl.BeginUndoAction()
        self.YankSelection()
        self.ctrl.Clear()
        self.ctrl.GotoPos(start)
        self.ctrl.EndUndoAction()

    def _GetSelectionRange(self):
        """Get the range of selection such that the start is the visual start
        of the selection, not the logical start.

        """
        start, end = self.minmax(self.ctrl.GetSelectionStart(),
                            self.ctrl.GetSelectionEnd())
        return start, end

    def _GetSelectedLines(self):
        """Get the first and last line (exclusive) of selection"""
        start, end = self._GetSelectionRange()
        start_line, end_line = (self.ctrl.LineFromPosition(start),
                                self.ctrl.LineFromPosition(end - 1) + 1)
        return start_line, end_line

    def HasSelection(self):
        """
        Detects if there's anything selected
        @rtype: bool
        """
        return len(self.ctrl.GetSelectedText()) > 0

    def InsertText(self, text):
        self.ctrl.InsertText(self.ctrl.GetCurrentPos(), text)
        self.MoveCaretPos(len(text))

    def SelectLines(self, start, end, reverse=False):
        """
        Selects lines

        @param start: start line
        @param end: end line
        @param reverse: if true selection is reversed
        """
        start_pos = self.GetLineStartPos(start)
        end_pos = self.ctrl.GetLineEndPosition(end)

        if reverse:
            self.ctrl.SetSelection(end_pos, start_pos)
        else:
            self.ctrl.SetSelection(start_pos, end_pos)

    def SwapCase(self):
        self.ctrl.BeginUndoAction()
        text = self.ctrl.GetSelectedText()
        if len(text) == 0:
            self.StartSelection()
            self.MoveCaretRight()
            self.SelectSelection()
            text = self.ctrl.GetSelectedText()
        self.ctrl.ReplaceSelection(text.swapcase())
        self.ctrl.EndUndoAction()

    def UpperCase(self):
        self.ctrl.ReplaceSelection(self.ctrl.GetSelectedText().upper())

    def LowerCase(self):
        self.ctrl.ReplaceSelection(self.ctrl.GetSelectedText().lower())

    def Indent(self, forward=True, repeat=1, visual=False):
        if visual == True:
            repeat = self.count

        self.ctrl.BeginUndoAction()
        # If no selected text we work on lines as specified by count
        if len(self.ctrl.GetSelectedText()) < 1:
            start_line = self.ctrl.GetCurrentLine()
            if self.count > 1:
                self.SelectLines(start_line, min(self.ctrl.GetLineCount(), \
                                                start_line - 1 + self.count))
        else:
            start_line, end = self._GetSelectedLines()

        if self.SelectionOnSingleLine():
            self.GotoLineIndent()

        for i in range(repeat):
            if forward:
                self.ctrl.Tab()
            else:
                self.ctrl.BackTab()

        self.ctrl.GotoLine(start_line)
        self.GotoLineIndent()
        self.ctrl.EndUndoAction()

    def _PositionViewport(self, n):
        """
        Positions the viewport around caret position
        """
        lines = self.ctrl.LinesOnScreen() - 1
        current = self.ctrl.GetCurrentLine()
        diff = int(lines * n)
        self.ctrl.ScrollToLine(current - diff)


    def IndentSingle(self):
        self.SelectSelection()
        self.Indent(True)

    def DedentSingle(self):
        self.SelectSelection()
        self.Indent(False)

    #--------------------------------------------------------------------
    # Visual mode
    #--------------------------------------------------------------------

    def EnterLineVisualMode(self):
        self.SetSelMode("LINE")
        text, pos = self.ctrl.GetCurLine()
        if pos == 0:
            self.MoveCaretRight()
        self.visual_line_start_pos = self.ctrl.GetCurrentPos()
        if self.mode != ViHelper.VISUAL:
            self.SetMode(ViHelper.VISUAL)
            self.StartSelectionAtAnchor()

            #if self.ctrl.GetSelectedText() > 0:
            #    self.MoveCaretRight()

    def LeaveVisualMode(self):
        """Helper function to end visual mode"""
        self.SetSelMode("NORMAL")
        self.SetMode(ViHelper.NORMAL)

    def EnterVisualMode(self, mouse=False):
        """
        Change to visual (selection) mode
        
        Will do nothing if already in visual mode
        """
        if self.mode != ViHelper.VISUAL:
            self.SetMode(ViHelper.VISUAL)

            if not mouse:
                self.StartSelectionAtAnchor()

                if self.ctrl.GetSelectedText() > 0:
                    self.MoveCaretRight()

    #--------------------------------------------------------------------
    # Searching
    #--------------------------------------------------------------------

    def FindChar(self, code=None, reverse=False, offset=0, count=1, \
                                                            repeat=True):
        """
        Searches current line for specified character. Will move the
        caret to this place (+/- any offset supplied).
        """
        if code is None:
            return
        char = unichr(code)
        text, cur_pos = self.ctrl.GetCurLine()

        pos = cur_pos
        
        if reverse: # Search backwards
            if repeat:
                # First save cmd so it can be repeated later
                # Vim doesn't save the count so a new one can be used next time
                self.last_backward_find_cmd = \
                            {"code":code,"reverse":reverse,"offset":offset}
                # Also save it for the "." repeats
                if self.pre_motion_key is not None and \
                            self.pre_keys[self.mode][self.pre_motion_key][2] in (1,2):
                    self.last_cmd = 4, code, self.count, self.pre_motion_key
            for i in range(count):
                pos = text.rfind(char, 0, pos)
                # Vim won't move the caret if all occurences are not found
                if pos == -1:
                    return

        else: # Search forwards
            if repeat:
                self.last_forward_find_cmd = {"code":code,"reverse":reverse,"offset":offset,"count":count}
                if self.pre_motion_key is not None and \
                            self.pre_keys[self.mode][self.pre_motion_key][2] in (1,2):
                    self.last_cmd = 5, code, self.count, self.pre_motion_key
            for i in range(count):
                pos = text.find(char, pos+1)
                if pos == -1:
                    return
         
        new_pos = pos + offset

        # Hack to make deleting forward consistent with vim behavoir
        # same thing if in visual mode
        if self.pre_motion_key is not None and not reverse \
                                    or self.mode == ViHelper.VISUAL:
            new_pos += 1
        
        if -1 < new_pos < len(text):
            to_move = new_pos - cur_pos
            self.MoveCaretPos(to_move)

            # If in visual mode we need to select the text
            if self.mode == ViHelper.VISUAL:
                self.SelectSelection()

            return to_move
        return False

            
    def FindNextChar(self, keycode):
        self.FindChar(keycode, count=self.count)
        
    def FindNextCharBackwards(self, keycode):
        cmd = self.FindChar(keycode, count=self.count, reverse=True)

    def FindUpToNextChar(self, keycode):
        cmd = self.FindChar(keycode, count=self.count, offset=-1)
        
    def FindUpToNextCharBackwards(self, keycode):
        cmd = self.FindChar(keycode, count=self.count, reverse=True, offset=1)

    def GetLastForwardFindCharCmd(self):
        return self.last_forward_find_cmd

    def GetLastBackwardFindCharCmd(self):
        return self.last_backward_find_cmd

    def RepeatLastForwardFindCharCmd(self):
        args = self.GetLastForwardFindCharCmd()
        if args is not None: 
            # Set the new count
            args["count"] = self.count
            self.FindChar(**args)
        # If no previous command has been found break any other functions
        # that might be running
        else: self.pre_motion_key = None
        
    def RepeatLastBackwardFindCharCmd(self):
        args = self.GetLastBackwardFindCharCmd()
        if args is not None: 
            args["count"] = self.count
            self.FindChar(**args)
        else: self.pre_motion_key = None

    def MatchBraces(self):
        """
        Brace highlighting is possible though might be a bit
        excessive
        """
        pos = self.ctrl.GetCurrentPos()
        char = self.ctrl.GetCharAt(pos)
        
        if char in (40, 41):
            self.ctrl.GotoPos(self.ctrl.BraceMatch(pos))
        else:
            # Vim appears to only search forward for a closing brace
            self.FindChar(41, False, 0, 1, False)

    # TODO: vim like searching
    def _SearchText(self, text, forward=True, match_case=True, wrap=True, whole_word=True):
        """
        Searches for next occurance of 'text'

        @param text: text to search for
        @param forward: if true searches forward in text, else
                        search in reverse
        @param match_case: should search be case sensitive?  
        """
        self.AddSearchPosition(self.ctrl.GetCurrentPos())

        search_cmd = self.ctrl.SearchNext if forward else self.ctrl.SearchPrev
        
        # There must be a better way to do this
        if whole_word and match_case:
            flags = wx.stc.STC_FIND_WHOLEWORD|wx.stc.STC_FIND_MATCHCASE
        elif whole_word:
            flags = wx.stc.STC_FIND_WHOLEWORD
        elif match_case:
            flags = wx.stc.STC_FIND_MATCHCASE

        pos = search_cmd(flags, text)

        if pos == -1 and wrap:
            if forward:
                self.ctrl.GotoLine(0)
            else:
                self.ctrl.GotoLine(self.ctrl.GetLineCount())
            self.ctrl.SearchAnchor()
            pos = search_cmd(flags, text)
        if pos != -1:
            self.ctrl.GotoPos(pos)

    def _SearchCaretWord(self, forward=True, whole_word=True):
        """
        Searches for next occurance of word currently under
        the caret

        @param forward: if true searches forward in text, else
                        search in reverse
        @param match_case: should search be case sensitive?  
        """ 
        self.SelectInWord()
        text = self.ctrl.GetSelectedText()
        offset = 1 if forward else -1
        self.MoveCaretPos(offset)
        self.ctrl.SearchAnchor()
        self._SearchText(text, forward, wrap=True, whole_word=whole_word)

        self.last_search_args = {'text' : text, 'forward' : forward, 
                                 'match_case' : True, 
                                 'whole_word' : whole_word}

    def SearchCaretWordForwards(self):
        """Helper function to allow repeats"""
        self._SearchCaretWord(True, True)

    def SearchPartialCaretWordForwards(self):
        self._SearchCaretWord(True, False)

    def SearchCaretWordBackwards(self):
        """Helper function to allow repeats"""
        self._SearchCaretWord(False, True)

    def SearchPartialCaretWordBackwards(self):
        self._SearchCaretWord(False, False)

    def ContinueLastSearch(self, reverse):
        """
        Repeats last search command
        """
        args = self.last_search_args
        if args is not None:
            # If "N" we need to reverse the search direction
            if reverse:
                args['forward'] = not args['forward']

            offset = 1 if args['forward'] else -1
            self.MoveCaretPos(offset)
            self.ctrl.SearchAnchor()

            self._SearchText(**args)

            # Restore search direction (could use copy())
            if reverse:
                args['forward'] = not args['forward']

    def ContinueLastSearchSameDirection(self):
        """Helper function to allow repeats"""
        self.ContinueLastSearch(False)

    def ContinueLastSearchReverseDirection(self):
        """Helper function to allow repeats"""
        self.ContinueLastSearch(True)

    #--------------------------------------------------------------------
    # Replace
    #--------------------------------------------------------------------
    
    def ReplaceChar(self, keycode):
        """
        Replaces character under caret

        Contains some custom code to allow repeating
        """
        # TODO: visual indication
        char = unichr(keycode)

        # If in visual mode use the seletion we have (not the count)
        if self.mode == ViHelper.VISUAL:
            sel_start, sel_end = self._GetSelectionRange()
            count = sel_end - sel_start
            self.ctrl.GotoPos(self_start)
        else:
            count = self.count

        # Replace does not wrap lines and fails if you try and replace 
        # non existent chars
        line, pos = self.ctrl.GetCurLine()
        if pos + count > len(line)-1:
            return

        self.last_cmd = 3, keycode, count, None

        self.ctrl.BeginUndoAction()
        self.StartSelection()
        self.ctrl.GotoPos(self.ctrl.GetCurrentPos()+count)
        self.EndDelete()
        self.Repeat(self.InsertText, arg=char)
        self.ctrl.EndUndoAction()
        self.MoveCaretPos(-1)

    def StartReplaceMode(self):
        # TODO: visual indication
        self.SetMode(ViHelper.REPLACE)

    #--------------------------------------------------------------------
    # Marks
    #--------------------------------------------------------------------

    def _SetMark(self, code):
        """
        Not called directly (call self.Mark instead)
        """
        page = self.ctrl.presenter.getWikiWord()
        self.marks[page][code] = self.ctrl.GetCurrentPos()

    def GotoMark(self, char):
        page = self.ctrl.presenter.getWikiWord()
        if char in self.marks[page]:
            pos = self.marks[page][char]

            # If mark is set past the end of the document just
            # go to the end
            pos = min(self.ctrl.GetLength(), pos)

            self.ctrl.GotoPos(pos)
            self.visualBell("GREEN")
            return True

        self.visualBell("RED")
        return False

    def GotoMarkIndent(self, char):
        if self.GotoMark(char):
            self.GotoLineIndent()

    #--------------------------------------------------------------------
    # Copy and Paste commands
    #--------------------------------------------------------------------

    def YankLine(self):
        """Copy the current line text to the clipboard"""

        line_no = self.ctrl.GetCurrentLine()
        max_line = min(line_no+self.count-1, self.ctrl.GetLineCount())
        start = self.GetLineStartPos(line_no)
        end = self.ctrl.GetLineEndPosition(max_line)

        text = self.ctrl.GetTextRange(start, end) + self.ctrl.GetEOLChar()

        self.ctrl.Copy(text)

    def YankSelection(self, lines=False):
        """Copy the current selection to the clipboard"""
        if lines:
            self.SelectFullLines()
            self.ctrl.CharRightExtend()
        elif self.GetSelMode() == "LINE":
            # Selection needs to be the correct way round
            start, end = self._GetSelectionRange()
            self.ctrl.SetSelection(start, end)
            self.ctrl.CharRightExtend()

        self.ctrl.Copy()

    def Yank(self):
        self.SelectSelection()
        self.YankSelection()
        start, end = self._GetSelectionRange()
        self.ctrl.GotoPos(start)

    def Put(self, before, count=None):
        count = count if count is not None else self.count
        text = getTextFromClipboard()

        # If its not text paste as normal for now
        if not text:
            self.ctrl.Paste()

        # Test for line as they are handled differently
        eol = self.ctrl.GetEOLChar()
        eol_len = len(eol)
        if len(text) > eol_len:
            is_line = text[-len(eol):] == eol
        else:
            is_line = False

        self.ctrl.BeginUndoAction()

        if is_line:
            if not before:  
                # If pasting a line we have to goto the end before moving caret 
                # down to handle long lines correctly
                self.GotoLineEnd()
                self.MoveCaretDown(1)
            self.GotoLineStart()

        if self.HasSelection():
            self.ctrl.Clear()

        #self.Repeat(self.InsertText, arg=text)
        self.InsertText(count * text)

        if is_line:
            #if before:
            #    self.MoveCaretUp(1)
            self.GotoLineIndent()

        self.ctrl.EndUndoAction()
                
    #--------------------------------------------------------------------
    # Deletion commands
    #--------------------------------------------------------------------

    def EndDelete(self):
        self.SelectSelection()
        self.DeleteSelection()

    def EndDeleteInsert(self):
        self.SelectSelection()
        self.DeleteSelection()
        self.Insert()

    def DeleteRight(self):
        # TODO: make this less complicated
        self.ctrl.BeginUndoAction()
        self.StartSelection()
        self.MoveCaretRight()
        self.SelectSelection()
        self.DeleteSelection()
        self.ctrl.EndUndoAction()

    def DeleteLeft(self):
        self.ctrl.BeginUndoAction()
        self.StartSelection()
        self.MoveCaretLeft()
        self.SelectSelection()
        self.DeleteSelection()
        self.ctrl.EndUndoAction()

    def DeleteRightAndInsert(self):
        self.DeleteRight()
        self.Insert()

    def DeleteLinesAndIndentInsert(self):
        self.ctrl.BeginUndoAction()
        indent = self.ctrl.GetLineIndentation(self.ctrl.GetCurrentLine())
        self.DeleteLine()
        self.OpenNewLine(True, indent=indent)
        self.ctrl.EndUndoAction()

    def DeleteLine(self):
        line_no = self.ctrl.GetCurrentLine()
        max_line = min(line_no+self.count-1, self.ctrl.GetLineCount())
        start = self.GetLineStartPos(line_no)
        end = self.ctrl.GetLineEndPosition(max_line)+1
        self.ctrl.SetSelection(end, start)
        self.DeleteSelection()
        

    #--------------------------------------------------------------------
    # Movement commands
    #--------------------------------------------------------------------

    def GetLineStartPos(self, line):
        return self.ctrl.GetLineIndentPosition(line) - \
                                    self.ctrl.GetLineIndentation(line)

    def GotoLineStart(self):
        self.ctrl.Home()

    def GotoLineEnd(self):
        self.ctrl.LineEnd()

    def GotoLineIndent(self, line=None):
        if line is None: line = self.ctrl.GetCurrentLine()
        self.ctrl.GotoPos(self.ctrl.GetLineIndentPosition(line))
        self.ctrl.ChooseCaretX()

    def GotoColumn(self):
        line = self.ctrl.GetCurrentLine()
        lstart = self.ctrl.PositionFromLine(line)
        lend = self.ctrl.GetLineEndPosition(line)
        line_len = lend - lstart
        column = min(line_len, self.count)
        self.ctrl.GotoPos(lstart + column)

        self.ctrl.ChooseCaretX()

    def MoveCaretRight(self):
        self.MoveCaretPos(self.count)

    #def MoveCaretLineUp(self, count=None):
    #    """Make long lines behave as in vim"""
    #    count = count if count is not None else self.count
    #    new_line_number = max(0, self.ctrl.GetCurrentLine()-count)
    #    self.ctrl.GotoLine(new_line_number)

    #def MoveCaretLineDown(self, count=None):
    #    """Make long lines behave as in vim"""
    #    count = count if count is not None else self.count
    #    new_line_number = min(self.ctrl.GetLineCount(), self.ctrl.GetCurrentLine()+count)
    #    self.ctrl.GotoLine(new_line_number)

    def MoveCaretUp(self, count=None):
        #count = count if count is not None else self.count
        #self.MoveCaretToLinePos(-count)
        #self.MoveCaretLineUp(count)
        self.Repeat(self.ctrl.LineUp, count)

    def MoveCaretDown(self, count=None):
        #self.MoveCaretLineDown(count)
        self.Repeat(self.ctrl.LineDown, count)

    def MoveCaretDownAndIndent(self, count=None):
        self.Repeat(self.ctrl.LineDown, count)
        self.GotoLineIndent()

    def MoveCaretLeft(self):
        self.MoveCaretPos(-self.count)

    def MoveCaretPos(self, offset):
        """
        Move caret by a given offset
        """
        #pos = max(self.ctrl.GetCurrentPos() + offset, 0)
        #pos = min(pos, self.ctrl.GetLength())
        line, line_pos = self.ctrl.GetCurLine()
        line_no = self.ctrl.GetCurrentLine()
        pos = max(line_pos + offset, 0)
        pos = min(pos, self.ctrl.LineLength(line_no)-1)
        self.ctrl.GotoPos(self.GetLineStartPos(line_no) + pos)
        self.ctrl.ChooseCaretX()

    def MoveCaretLinePos(self, offset):
        """
        Move caret line position by a given offset

        Faster but does not maintain line position
        """
        self.ctrl.ChooseCaretX()
        line = max(self.ctrl.GetCurrentLine() + offset, 0)
        line = min(line, self.ctrl.GetLineCount())
        self.ctrl.GotoLine(line)
        line_start_pos = self.ctrl.GetCurrentPos()

        pos = max(index, 0)
        pos = min(pos, self.ctrl.GetLineEndPosition(line)-line_start_pos)
        self.ctrl.GotoPos(line_start_pos+pos)
        #self.ctrl.ChooseCaretX()

    def MoveCaretToLinePos(self, line, index):
        line = max(line, 0)
        line = min(line, self.ctrl.GetLineCount())
        self.ctrl.GotoLine(line)
        line_start_pos = self.ctrl.GetCurrentPos()
        pos = max(index, 0)
        pos = min(pos, self.ctrl.GetLineEndPosition(line)-line_start_pos)
        self.ctrl.GotoPos(line_start_pos+pos)

    def SaveCaretPos(self):
        page = self.ctrl.presenter.getWikiWord()
        self.previous_positions[page].append(self.ctrl.GetCurrentPos())
        self.future_positions[page] = []

# word-motions

    def MoveCaretNextWord(self, count=None):
        self.Repeat(self.ctrl.WordRight, count)

    def MoveCaretWordEnd(self, count=None):
        self.Repeat(self.ctrl.WordRightEnd, count)

    def MoveCaretBackWord(self, count=None):
        self.Repeat(self.ctrl.WordLeft, count)

    def MoveCaretNextWORD(self, count=None):
        """Wordbreaks are spaces"""
        def func():
            self.ctrl.WordRight()
            while self.GetChar(-1) and not self.GetChar(-1).isspace():
                self.ctrl.WordRight()
        self.Repeat(func, count)

    def MoveCaretWordEND(self, count=None):
        def func():
            self.ctrl.WordRightEnd()
            while self.GetChar(-1) and not self.GetChar(-1).isspace():
                self.ctrl.WordRightEnd()
        self.Repeat(func, count)

    def MoveCaretBackWORD(self, count=None):
        def func():
            self.ctrl.WordRightEnd()
            while self.GetChar(-1) and not self.GetChar(-1).isspace():
                self.ctrl.WordRightEnd()
        self.Repeat(func, count)

    def DocumentNavigation(self, key):
        
        # %, G or gg
        if self.true_count:
            if key in [71, (103, 103)]:
                # Correct for line 0
                self.MoveCaretToLinePos(self.count-1, self.ctrl.GetCurLine()[1])
            elif key == 37: # %
                max_lines = self.ctrl.GetLineCount()
                # Same as   int(self.count / 100 * max_lines)  but needs only
                #   integer arithmetic
                line_percentage = (self.count * max_lines) // 100
                self.MoveCaretToLinePos(line_percentage, self.ctrl.GetCurLine()[1])

        elif key == 37:
            # If key is % but no count it is used for brace matching
            self.MatchBraces()

        elif key == (103, 103):
            self.ctrl.GotoLine(0)

        elif key == (71):
            self.ctrl.GotoLine(self.ctrl.GetLineCount())

    def GotoViewportTop(self):
        self.GotoLineIndent(self.ctrl.GetFirstVisibleLine())
        
    def GotoViewportMiddle(self):
        self.GotoLineIndent(self.ctrl.GetMiddleVisibleLine())

    def GotoViewportBottom(self):
        self.GotoLineIndent(self.ctrl.GetLastVisibleLine())

    def ScrollViewportTop(self):
        self._PositionViewport(0)

    def ScrollViewportMiddle(self):
        self._PositionViewport(0.5)

    def ScrollViewportBottom(self):
        self._PositionViewport(1)

    def Undo(self, count=None):
        if self.ctrl.CanUndo():
            self.visualBell("GREEN")
            self.Repeat(self.ctrl.Undo, count)
        else:
            self.visualBell("RED")

    def Redo(self, count=None):
        if self.ctrl.CanRedo():
            self.visualBell("GREEN")
            self.Repeat(self.ctrl.Redo, count)
        else:
            self.visualBell("RED")

# The following commands are basic ways to enter insert mode
    def Insert(self):
        self.SetMode(ViHelper.INSERT)

    def Append(self):
        if self.ctrl.GetCurrentPos() != self.ctrl.GetLineEndPosition(self.ctrl.GetCurrentLine()):
            self.ctrl.CharRight()
        self.Insert()

    def InsertAtLineStart(self):
        # Goto line places the caret at the start of the line
        self.GotoLineIndent(self.ctrl.GetCurrentLine())
        self.ctrl.ChooseCaretX()
        self.Insert()

    def AppendAtLineEnd(self):
        self.ctrl.GotoPos(self.ctrl.GetLineEndPosition(
                                    self.ctrl.GetCurrentLine()))
        self.Append()

    def OpenNewLine(self, above, indent=None):
        self.ctrl.BeginUndoAction()

        if indent is None:
            indent = self.ctrl.GetLineIndentation(self.ctrl.GetCurrentLine())

        if above:
            self.MoveCaretUp(1)
        self.GotoLineEnd()
        self.ctrl.AddText(self.ctrl.GetEOLChar())
        self.ctrl.SetLineIndentation(self.ctrl.GetCurrentLine(), indent)
        self.ctrl.EndUndoAction()
        self.AppendAtLineEnd()

    def TruncateLine(self):
        self.ctrl.LineEndExtend()
        self.DeleteSelection()

    def TruncateLineAndInsert(self):
        self.TruncateLine()
        self.Insert()
