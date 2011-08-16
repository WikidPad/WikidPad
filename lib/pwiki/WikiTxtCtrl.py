from __future__ import with_statement
## import hotshot
## _prof = hotshot.Profile("hotshot.prf")

import traceback, codecs
from cStringIO import StringIO
import string, itertools, contextlib
import re # import pwiki.srePersistent as re
import threading

import subprocess
import string

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
        self.AutoCompSetTypeSeparator(2)   # ord('?')

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
        self.Unbind(wx.EVT_SCROLLWIN)
        self.Unbind(wx.EVT_MOUSEWHEEL)

        if use_vi_navigation:
            if self.vi is None:
                self.vi = ViHandler(self)

            
            #self.Bind(wx.EVT_CHAR, self.vi.OnViKeyDown)
            self.Bind(wx.EVT_KEY_DOWN, self.vi.OnViKeyDown)
            self.Bind(wx.EVT_LEFT_UP, self.vi.OnLeftMouseUp)
            self.Bind(wx.EVT_SCROLLWIN, self.vi.OnScroll)
            self.Bind(wx.EVT_MOUSEWHEEL, self.vi.OnMouseScroll)
            # Should probably store shortcut state in a global
            # variable otherwise this will be run each time
            # a new tab is opened
            wx.CallAfter(self.vi._enableMenuShortcuts, False)
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
            t.setDaemon(True)
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
        # TODO Handle form mode
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
                    if node.level < 5:
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
        thread.setDaemon(True)
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
        # TODO: Fix this for long lines
        fl = self.GetFirstVisibleLine()
        ll = self.GetLastVisibleLine()

        lines = ll - fl

        mid = fl + lines // 2

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
    #       autocompletion ctrl-n, ctrl-f
    
    def __init__(self, stc):
        ViHelper.__init__(self, stc)

        self._anchor = None

        wx.CallAfter(self.SetDefaultCaretColour)
        # Set default mode
        wx.CallAfter(self.SetMode, ViHelper.NORMAL)
        wx.CallAfter(self.Setup)

        self.text_object_map = {
                    "w" : (False, self.SelectInWord),
                    "W" : (False, self.SelectInWORD),
                    "s" : (False, self.SelectInSentence),
                    "p" : (False, self.SelectInParagraph),

                    "[" : (True, self.SelectInSquareBracket),
                    "]" : (True, self.SelectInSquareBracket),

                    "(" : (True, self.SelectInRoundBracket),
                    ")" : (True, self.SelectInRoundBracket),
                    "b" : (True, self.SelectInRoundBracket),

                    "<" : (True, self.SelectInInequalitySigns),
                    ">" : (True, self.SelectInInequalitySigns),

                    "t" : (True, self.SelectInTagBlock),

                    "{" : (True, self.SelectInBlock),
                    "}" : (True, self.SelectInBlock),
                    "B" : (True, self.SelectInBlock),

                    '"' : (True, self.SelectInDoubleQuote),
                    "'" : (True, self.SelectInSingleQuote),
                    "`" : (True, self.SelectInTilde),

                    # The commands below are not present in vim but may 
                    # be useful for quickly editing parser syntax
                    u"\xc2" : (True, self.SelectInPoundSigns),
                    u"$" : (True, self.SelectInDollarSigns),
                    u"^" : (True, self.SelectInHats),
                    u"%" : (True, self.SelectInPercentSigns),
                    u"&" : (True, self.SelectInAmpersands),
                    u"*" : (True, self.SelectInStars),
                    u"-" : (True, self.SelectInHyphens),
                    u"_" : (True, self.SelectInUnderscores),
                    u"=" : (True, self.SelectInEqualSigns),
                    u"+" : (True, self.SelectInPlusSigns),
                    u"!" : (True, self.SelectInExclamationMarks),
                    u"?" : (True, self.SelectInQuestionMarks),
                    u"@" : (True, self.SelectInAtSigns),
                    u"#" : (True, self.SelectInHashs),
                    u"~" : (True, self.SelectInApproxSigns),
                    u"|" : (True, self.SelectInVerticalBars),
                    u";" : (True, self.SelectInSemicolons),
                    u":" : (True, self.SelectInColons),
                    u"\\" : (True, self.SelectInBackslashes),
                    u"/" : (True, self.SelectInForwardslashes),
                }

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
    #               3 : Replace
    # Note:
    # The repeats provided by ; and , are managed within the FindChar function
        self.keys = {
            0 : {
            # Normal mode
        (60, "motion")  : (0, (self.DedentText, None), 1), # <motion
        (62, "motion")  : (0, (self.IndentText, None), 1), # >motion
        (99, "motion")  : (2, (self.EndDeleteInsert, None), 2), # cmotion
        (100, "motion") : (0, (self.EndDelete, None), 1), # dmotion
        (100, 115, "*") : (0, (self.DeleteSurrounding, None), 1), # ds
        (121, "motion") : (0, (self.Yank, None), 1), # ymotion
        (99, 115, "*", "*") : (0, (self.ChangeSurrounding, None), 1), # cs**
        # TODO: yS and ySS (indentation on new line)
        (121, 115, "motion", "*") : (0, (self.PreSurround, None), 1), # ysmotion*
        (121, 115, 115, "*") : (0, (self.PreSurroundLine, None), 1), # yss*
        (103, 117, "motion") : (0, (self.PreLowercase, None), 1), # gu
        (103, 85, "motion") : (0, (self.PreUppercase, None), 1), # gU
        (39, "*")  : (1, (self.GotoMark, None), 0), # '
        (96, "*")  : (1, (self.GotoMarkIndent, None), 0), # `
        (109, "*") : (0, (self.Mark, None), 0), # m
        (102, "*") : (1, (self.FindNextChar, None), 4), # f
        (70, "*")  : (1, (self.FindNextCharBackwards, None), 4), # F
        (116, "*") : (1, (self.FindUpToNextChar, None), 5), # t
        (84, "*")  : (1, (self.FindUpToNextCharBackwards, None), 5), # T
        (114, "*") : (0, (self.ReplaceChar, None), 0), # r

    (105,) : (0, (self.Insert, None), 2), # i
    (97,) : (0, (self.Append, None), 2), # a
    (73,) : (0, (self.InsertAtLineStart, None), 2), # I
    (65,) : (0, (self.AppendAtLineEnd, None), 2), # A
    (111,) : (0, (self.OpenNewLine, False), 2), # o
    (79,) : (0, (self.OpenNewLine, True), 2), # O
    (67,) : (0, (self.TruncateLineAndInsert, None), 2), # C
    (68,) : (0, (self.TruncateLine, None), 2), # D

    (120,) : (0, (self.DeleteRight, None), 1), # x
    (88,) : (0, (self.DeleteLeft, None), 1), # X

    (115,) : (0, (self.DeleteRightAndInsert, None), 2), # s
    (83,) : (0, (self.DeleteLinesAndIndentInsert, None), 2), # S

    (119,) : (1, (self.MoveCaretNextWord, None), 0), # w
    (87,) : (1, (self.MoveCaretNextWORD, None), 0), # W
    (103, 101) : (1, (self.MoveCaretPreviousWordEnd, None), 0), # ge
    # TODO: gE
    (101,) : (1, (self.MoveCaretWordEnd, None), 0), # e
    (69,) : (1, (self.MoveCaretWordEND, None), 0), # E
    (98,) : (1, (self.MoveCaretBackWord, None), 0), # b
    (66,) : (1, (self.MoveCaretBackWORD, None), 0), # B

    (123,) : (1, (self.MoveCaretParaUp, None), 0), # {
    (125,) : (1, (self.MoveCaretParaDown, None), 0), # }

    # TODO: complete search
    # Search should use a custom implementation of wikidpads incremental search
    (47,)  : (0, (self.StartSearch, None), 0), # /
    #47  : (0, (self.StartSearchReverse, None), 0), # /
    (110,) : (1, (self.Repeat, self.ContinueLastSearchSameDirection), 0), # n
    (78,) : (1, (self.Repeat, self.ContinueLastSearchReverseDirection), 0), # N

    (42,) : (1, (self.Repeat, self.SearchCaretWordForwards), 0), # *
    (35,) : (1, (self.Repeat, self.SearchCaretWordBackwards), 0), # #

    (103, 42)  : (1, (self.Repeat, self.SearchPartialCaretWordForwards), 0), # g*
    (103, 35)  : (1, (self.Repeat, self.SearchPartialCaretWordBackwards), 0), # g#

    # Basic movement
    # TODO: j and k should not act on screenlines
    (104,) : (1, (self.MoveCaretLeft, None), 0), # h
    (107,) : (1, (self.MoveCaretUp, None), 0), # k
    (108,) : (1, (self.MoveCaretRight, None), 0), # l
    (106,) : (1, (self.MoveCaretDown, None), 0), # j
    (103, 107) : (1, (self.MoveCaretUp, None), 0), # gk
    (103, 106) : (1, (self.MoveCaretDown, None), 0), # gj
    # Arrow keys
    (65361,) : (1, (self.MoveCaretLeft, None), 0), # left 
    (65362,) : (1, (self.MoveCaretUp, None), 0), # up
    (65363,) : (1, (self.MoveCaretRight, None), 0), # right
    (65364,) : (1, (self.MoveCaretDown, None), 0), # down

    (65293,) : (1, (self.MoveCaretDownAndIndent, None), 0), # enter
    (65293,) : (1, (self.MoveCaretDownAndIndent, None), ), # return

    # Line movement
    (36,)    : (1, (self.GotoLineEnd, False), 0), # $
    (65367,) : (1, (self.GotoLineEnd, False), 0), # home
    (48,)    : (1, (self.GotoLineStart, None), 0), # 0
    (65360,) : (1, (self.GotoLineStart, None), 0), # end 
    (45,)    : (1, (self.GotoLineIndentPreviousLine, None), 0), # -
    (43,)    : (1, (self.GotoLineIndentNextLine, None), 0), # +
    (94,)    : (1, (self.GotoLineIndent, None), 0), # ^
    (124,)   : (1, (self.GotoColumn, None), 0), # |

    (40,)   : (1, (self.GotoSentenceStart, None), 0), # (
    (41,)   : (1, (self.GotoNextSentence, None), 0), # )

    # Page scroll control
    (103, 103)  : (1, (self.DocumentNavigation, (103, 103)), 0), # gg
    (71,)        : (1, (self.DocumentNavigation, 71), 0), # G
    (37,)        : (1, (self.DocumentNavigation, 37), 0), # %

    (72,)        : (1, (self.GotoViewportTop, None), 0), # H
    (76,)        : (1, (self.GotoViewportBottom, None), 0), # L
    (77,)        : (1, (self.GotoViewportMiddle, None), 0), # M

    (122, 122)  : (0, (self.ScrollViewportMiddle, None), 0), # zz
    (122, 116)  : (0, (self.ScrollViewportTop, None), 0), # zt
    (122, 98)   : (0, (self.ScrollViewportBottom, None), 0), # zb

    (("Ctrl", 117),)    : (0, (self.ScrollViewportUpHalfScreen, 
                                                        None), 0), # <c-u>
    (("Ctrl", 100),)    : (0, (self.ScrollViewportDownHalfScreen, 
                                                        None), 0), # <c-d>
    (("Ctrl", 98),)     : (0, (self.ScrollViewportUpFullScreen, 
                                                        None), 0), # <c-b>
    (("Ctrl", 102),)    : (0, (self.ScrollViewportDownFullScreen, 
                                                        None), 0), # <c-f>

    (("Ctrl", 101),)    : (0, (self.ScrollViewportLineDown, 
                                                        None), 0), # <c-e>
    (("Ctrl", 121),)    : (0, (self.ScrollViewportLineUp, 
                                                        None), 0), # <c-y>

    (90, 90)    : (0, (self.ctrl.presenter.getMainControl().\
                                        exitWiki, None), 0), # ZZ

    (117,)              : (0, (self.Undo, None), 0), # u
    (("Ctrl", 114),)    : (0, (self.Redo, None), 0), # <c-r>

    (("Ctrl", 105),)    : (1, (self.GotoNextJump, None), 0), # <c-i>
    (65289,)            : (1, (self.GotoNextJump, None), 0), # Tab
    (("Ctrl", 111),)    : (1, (self.GotoPreviousJump, None), 0), # <c-o>

    # These two are motions
    (59,)   : (1, (self.RepeatLastFindCharCmd, None), 0), # ;
    (44,)   : (1, (self.RepeatLastFindCharCmdReverse, None), 0), # ,

    # Replace ?
    #(114)   : (1, (self.ReplaceChar, None)), # r
    # repeatable?
    (82,)   : (0, (self.StartReplaceMode, None), 0), # R

    (118,)   : (2, (self.EnterVisualMode, None), 0), # v
    (86,)   : (2, (self.EnterLineVisualMode, None), 0), # V

    (74,)   : (0, (self.JoinLines, None), 1), # J

    (126,)   : (0, (self.SwapCase, None), 0), # ~

    (121, 121)  : (0, (self.YankLine, None), 0), # yy
    (89,)        : (0, (self.YankLine, None), 0), # Y
    (112,)       : (0, (self.Put, False), 0), # p
    (80,)        : (0, (self.Put, True), 0), # P

    (100, 100)  : (0, (self.DeleteLine, None), 1), # dd

    (62, 62)    : (0, (self.Indent, True), 1), # >>
    (60, 60)    : (0, (self.Indent, False), 1), # <<

    (46,)    : (0, (self.RepeatCmd, None), 0), # .

    # Wikipage navigation
    # As some command (e.g. HL) are already being used in most cases
    # these navigation commands have been prefixed by "g".
    # TODO: different repeat command for these?
    (103, 102)  : (0, (self.ctrl.activateLink, { "tabMode" : 0 }), 0), # gf
    (("Ctrl", 119), 103, 102)  : (0, (self.ctrl.activateLink, { "tabMode" : 2 }), 0), # <c-w>gf
    (103, 70)   : (0, (self.ctrl.activateLink, { "tabMode" : 2 }), 0), # gF
    (103, 98)   : (0, (self.ctrl.activateLink, { "tabMode" : 3 }), 0), # gb
    # This might be going a bit overboard with history nagivaiton!
    (103, 72)   : (0, (self.GoBackwardInHistory, None), 0), # gH
    (103, 76)   : (0, (self.GoForwardInHistory, None), 0), # gL
    (103, 104)  : (0, (self.GoBackwardInHistory, None), 0), # gh
    (103, 108)  : (0, (self.GoForwardInHistory, None), 0), # gl
    (91,)        : (0, (self.GoBackwardInHistory, None), 0), # [
    (93,)        : (0, (self.GoForwardInHistory, None), 0), # ]
    (103, 116) : (0, (self.SwitchTabs, None), 0), # gt
    (103, 84)  : (0, (self.SwitchTabs, True), 0), # gT
    (103, 114) : (0, (self.OpenHomePage, False), 0), # gr
    (103, 82) : (0, (self.OpenHomePage, True), 0), # gR
    (103, 111) : (0, (self.ctrl.presenter.getMainControl()). \
                                    showWikiWordOpenDialog, None, 0), # go
    # TODO: rewrite open dialog so it can be opened with new tab as default
    (103, 79): (0, (self.ctrl.presenter.getMainControl()). \
                                    showWikiWordOpenDialog, None, 0), # gO

    (92, 117) : (0, (self.ViewParents, False), 0), # \u
    (92, 85) : (0, (self.ViewParents, True), 0), # \U

    (103, 115)  : (0, (self.SwitchEditorPreview, None), 0), # gs
    
    # TODO: think of suitable commands for the following
    #(103, 101)  : (0, (self.SwitchEditorPreview, "textedit"), 0), # ge
    (103, 112)  : (0, (self.SwitchEditorPreview, "preview"), 0), # gp
    (65470,)     : (0, (self.SwitchEditorPreview, "textedit"), 0), # F1
    (65471,)     : (0, (self.SwitchEditorPreview, "preview"), 0), # F2
            }
            }


        # Could be changed to use a wildcard
        for i in self.text_object_map:
            self.keys[0][(105, ord(i))] = (1, (self.SelectInTextObject, i), 0)
            self.keys[0][(97, ord(i))] = (1, (self.SelectATextObject, i), 0)

        # Shortcuts available in insert mode (need to be repeatable by ".",
        # i.e. must work with EmulateKeypresses)
        self.keys[1] = {
        (("Ctrl", 64),)  : (0, (self.InsertPreviousText, None), 0), # Ctrl-@
        (("Ctrl", 97),)  : (0, (self.InsertPreviousTextLeaveInsertMode, 
                                                            None), 0), # Ctrl-a
        (("Ctrl", 110),)  : (0, (self.Autocomplete, True), 0), # Ctrl-n
        (("Ctrl", 112),)  : (0, (self.Autocomplete, False), 0), # Ctrl-p
        }

        # Rather than rewrite all the keys for other modes it is easier just
        # to modify those that need to be changed

        # VISUAL MODE
        self.keys[2] = self.keys[0].copy()
        self.keys[2].update({

                (39, "*")  : (1, (self.GotoMark, None), 0), # '
                (96, "*")  : (1, (self.GotoMarkIndent, None), 0), # `
                (109, "*") : (0, (self.Mark, None), 0), # m
                (102, "*") : (1, (self.FindNextChar, None), 0), # f
                (70, "*")  : (1, (self.FindNextCharBackwards, None), 0), # F
                (116, "*") : (1, (self.FindUpToNextChar, None), 0), # t
                (84, "*")  : (1, (self.FindUpToNextCharBackwards, None), 0), # T
                (114, "*") : (0, (self.ReplaceChar, None), 2), # r
                (83, "*")  : (0, (self.SurroundSelection, None), 2), # S


                (99,)  : (0, (self.DeleteSelectionAndInsert, None), 2), # c
                (100,)  : (0, (self.DeleteSelection, None), 1), # d
                (120,)  : (0, (self.DeleteSelection, None), 1), # x
                (121,) : (0, (self.Yank, None), 0), # y
                (89,) : (0, (self.Yank, True), 0), # Y
                (60,) : (0, (self.Indent, {"forward":False, "visual":True}), 0), # <
                (62,) : (0, (self.Indent, {"forward":True, "visual":True}), 0), # >
                (117,) : (0, (self.LowerCase, None), 0), # u
                (85,) : (0, (self.UpperCase, None), 0), # U
                (103, 117) : (1, self.LowerCase, 0), # gu
                (103, 85) : (1, self.UpperCase, 0), # gU
            })
        # And delete a few so our key mods are correct
        # These are keys that who do not serve the same function in visual mode
        # as in normal mode (and it most cases are replaced by other function)
        del self.keys[2][(100, 100)] # dd
        del self.keys[2][(121, 121)] # yy
        del self.keys[2][(105,)] # i
        del self.keys[2][(97,)] # a
        del self.keys[2][(83,)] # S

        self.keys[3] = {}


        #self._motion_chains = self.GenerateMotionKeyChains(self.keys)
        self.key_mods = self.GenerateKeyModifiers(self.keys)
        self.motion_keys = self.GenerateMotionKeys(self.keys)
        self.motion_key_mods = self.GenerateKeyModifiers(self.motion_keys)

        # Used for rewriting menu shortcuts
        self.viKeyAccels = self.GenerateKeyAccelerators(self.keys)


        self.SINGLE_LINE_WHITESPACE = [9, 11, 12, 32]
        self.WORD_BREAK =   '!"#$%&\'()*+,-./:;<=>?@[\\]^`{|}~'
        self.WORD_BREAK_INCLUDING_WHITESPACE = \
                            '!"#$%&\'()*+,-./:;<=>?@[\\]^`{|}~ \n\r'
        self.SENTENCE_ENDINGS = '.!?'
        self.SENTENCE_ENDINGS_SUFFIXS = '\'")]'

        self.BRACES = {
                        "(" : ")",
                        "[" : "]",
                        "{" : "}",
                        "<" : ">",
                      }
        self.REVERSE_BRACES = dict((v,k) for k, v in self.BRACES.iteritems())

        self._undo_state = 0
        self._undo_pos = -1
        self._undo_start_position = None
        self._undo_positions = []

 
    def Setup(self):
        self.AddJumpPosition(self.ctrl.GetCurrentPos())

    def SetMode(self, mode):
        """
        It would be nice to set caret alpha but i don't think its
        possible at the moment
        """
        # If switching from insert mode vi does a few things
        if self.mode == ViHelper.INSERT:
            # Move back one pos if not at the start of a line
            # and not on the last line
            if self.ctrl.GetCurrentPos() != \
                    self.GetLineStartPos(self.ctrl.GetCurrentLine()) and \
                    self.ctrl.GetLineCount() != self.ctrl.GetCurrentLine() + 1:
                self.ctrl.CharLeft()
            self.EndUndo(force=True)

            if self.mode == ViHelper.INSERT:
                # If current line only contains whitespace remove it
                if self.ctrl.GetCurLine()[0].strip() == u"":
                    self.ctrl.LineDelete()
                    self.ctrl.AddText(self.ctrl.GetEOLChar())
                    self.ctrl.CharLeft()
        elif self.mode == ViHelper.REPLACE:
            # End undo action
            self.EndUndo()
        
        self.mode = mode

        # Save caret position
        self.ctrl.ChooseCaretX()

        if mode == ViHelper.NORMAL:
            # Set block caret (Not in wxpython < ?)
            #self.ctrl.SendMsg(2512, 2)
            self.ctrl.SetCaretPeriod(800)
            #self.ctrl.SetSelectionMode(0)
            self.RemoveSelection()
            self.ctrl.SetCaretForeground(wx.Colour(255, 0, 0))
            self.ctrl.SetCaretWidth(40)
            self.ctrl.SetOvertype(False)
            self.SetSelMode("NORMAL")
            # Vim never goes right to the end of the line
            self.CheckLineEnd()
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

    # Starting code to allow correct postitioning when undoing and redoing
    # actions

    # Need to overide Undo and Redo to goto positions
    def BeginUndo(self, use_start_pos=False):
        if self._undo_state == 0:
            self.ctrl.BeginUndoAction()
            #self._undo_start_positions = \
            #            self._undo_start_positions[:self._undo_pos + 1]
            self._undo_positions = \
                        self._undo_positions[:self._undo_pos + 1]

            if use_start_pos:
                if self.HasSelection:
                    self._undo_start_position = self.ctrl.GetSelectionStart()
                else:
                    self._undo_start_position = self.ctrl.GetCurrentPos()
        self._undo_state += 1


    def EndUndo(self, force=False):
        if force: self._undo_state = 1

        if self._undo_state == 1:
            self.ctrl.EndUndoAction()
            if self._undo_start_position is not None:
                self._undo_positions.append(self._undo_start_position)
                self._undo_start_position = None
                
            elif self.HasSelection:
                self._undo_positions.append(self.ctrl.GetSelectionStart())
            else:
                self._undo_positions.append(self.ctrl.GetCurrentPos())
            self._undo_pos += 1
        self._undo_state -= 1

    def _Undo(self):
        if self._undo_pos < 0:
            return False
        self.ctrl.Undo()
        self.ctrl.GotoPos(self._undo_positions[self._undo_pos])
        self._undo_pos -= 1

    def _Redo(self):
        # NOTE: the position may be off on some redo's
        if self._undo_pos > len(self._undo_positions):
            return False

        self.ctrl.Redo()
        self._undo_pos += 1


    # TODO: Remember caret position
    def GotoFirstVisibleLine(self):
        line = self.ctrl.GetFirstVisibleLine()
        if line < self.ctrl.GetCurrentLine():
            return
        self.ctrl.GotoLine(line)

    def GotoLastVisibleLine(self):
        line = self.ctrl.GetLastVisibleLine()
        if line > self.ctrl.GetCurrentLine():
            return
        self.ctrl.GotoLine(line)

    def OnMouseScroll(self, evt):
        current_line = self.ctrl.GetCurrentLine()
        top_line = self.ctrl.GetFirstVisibleLine() + 1
        bottom_line = self.ctrl.GetLastVisibleLine()

        if current_line < top_line:
            wx.CallAfter(self.GotoFirstVisibleLine)
        elif current_line > bottom_line:
            wx.CallAfter(self.GotoLastVisibleLine)
            #offset = evt.GetWheelRotation() / 40
            #print offset
            #if offset < 0:
            #        func = self.ctrl.LineDown
            #else:
            #        func = self.ctrl.LineUp
            #    
            #for i in range(abs(offset)):
            #    print "i", i
            #    func()

        evt.Skip()


    def OnScroll(self, evt):
        """
        Vim never lets the caret out of the viewport so track any
        viewport movements
        """
        # NOTE: may be inefficient?
        current_line = self.ctrl.GetCurrentLine()
        top_line = self.ctrl.GetFirstVisibleLine()+1
        bottom_line = self.ctrl.GetLastVisibleLine()-1

        if current_line < top_line:
            self.MoveCaretToLine(top_line)
        elif current_line > bottom_line:
            self.MoveCaretToLine(bottom_line)
        evt.Skip()

    def OnLeftMouseUp(self, evt):
        """Enter visual mode if text is selected by mouse"""
        if len(self.ctrl.GetSelectedText()) > 0:
            self.EnterVisualMode(True)
        else:
            self.LeaveVisualMode()
        # Prevent the end of line character from being selected as per vim
        # This will cause a slight delay, there may be a better solution
        # May be possible to override MOUSE_DOWN event.
        wx.CallAfter(self.CheckLineEnd)
        evt.Skip()

    def OnAutocompleteKeyDown(self, evt):
        if evt.GetKeyCode() in (wx.WXK_UP, wx.WXK_DOWN, wx.WXK_LEFT, wx.WXK_RIGHT, wx.WXK_RETURN, wx.WXK_ESCAPE):
            evt.Skip()
            return

        if evt.GetRawKeyCode() in (65505, 65507, 65513):
            return

        # Messy
        if evt.ControlDown():
            if evt.GetKeyCode() == 80:
                evt = wx.KeyEvent(wx.wxEVT_KEY_DOWN)
                evt.m_keyCode = wx.WXK_UP
                wx.PostEvent(self.ctrl, evt)
                return

            elif evt.GetKeyCode() == 78:
                evt = wx.KeyEvent(wx.wxEVT_KEY_DOWN)
                evt.m_keyCode = wx.WXK_DOWN
                wx.PostEvent(self.ctrl, evt)
                return

            elif evt.GetKeyCode() == 91:
                evt = wx.KeyEvent(wx.wxEVT_KEY_DOWN)
                evt.m_keyCode = wx.WXK_ESCAPE
                wx.PostEvent(self.ctrl, evt)
                return


        evt.Skip()
        self.ctrl.Bind(wx.EVT_KEY_DOWN, None)

    def OnViKeyDown(self, evt):
        """
        Handle keypresses when in Vi mode

        """


        # The following code is mostly duplicated from OnKeyDown (should be
        # rewritten to avoid duplication)
        key = evt.GetKeyCode()
        # TODO Check all modifiers
        if not evt.ControlDown() and not evt.ShiftDown():  
            if key == wx.WXK_TAB:
                if self.ctrl.pageType == u"form":
                    if not self.ctrl._goToNextFormField():
                        self.ctrl.presenter.getMainControl().showStatusMessage(
                                _(u"No more fields in this 'form' page"), -1)
                    return
                evt.Skip()
            elif key == wx.WXK_RETURN and not self.ctrl.AutoCompActive():
                text = self.ctrl.GetText()
                wikiDocument = self.ctrl.presenter.getWikiDocument()
                bytePos = self.ctrl.GetCurrentPos()
                lineStartBytePos = self.ctrl.PositionFromLine(
                                        self.ctrl.LineFromPosition(bytePos))

                lineStartCharPos = len(self.ctrl.GetTextRange(0, 
                                                        lineStartBytePos))
                charPos = lineStartCharPos + len(self.ctrl.GetTextRange(
                                                lineStartBytePos, bytePos))

                autoUnbullet = self.ctrl.presenter.getConfig().getboolean("main",
                        "editor_autoUnbullets", False)

                settings = {
                        "autoUnbullet": autoUnbullet,
                        "autoBullets": self.ctrl.autoBullets,
                        "autoIndent": self.ctrl.autoIndent
                        }

                if self.ctrl.wikiLanguageHelper.handleNewLineBeforeEditor(
                        self.ctrl, text, charPos, lineStartCharPos, 
                        wikiDocument, settings):
                    evt.Skip()
                    return
                # Hack to maintain consistency when pressing return
                # on an empty bullet
                elif bytePos != self.ctrl.GetCurrentPos():
                    return

        # NOTE: need to check cross platform compat

        key = evt.GetRawKeyCode()

        # Pass modifier keys on
        if key in (65505, 65507, 65513):
            return

        accP = getAccelPairFromKeyDown(evt)

        # TODO: Replace with override keys? break and run function
        # Escape, Ctrl-[, Ctrl-C
        # In VIM Ctrl-C triggers *InsertLeave*
        if key == 65307 or accP == (2, 91) or accP == (2, 99): 
            # TODO: Move into ViHandler?
            self.SetMode(ViHandler.NORMAL)
            self.FlushBuffers()
            return


        # There should be a better way to monitor for selection changed
        if self.HasSelection():
            self.EnterVisualMode()

        #control_mask = False
        try:
            if 2 in accP[0]: # Ctrl
            #    control_mask = True
                key = ("Ctrl", key)
        except TypeError:
            if accP[0] == 2:
                key = ("Ctrl", key)

        m = self.mode

        if m in [1, 3]: # Insert mode, replace mode, 
            # Store each keyevent
            # NOTE: this may be terribly inefficient (i'm not sure)
            #       !!may need to seperate insert and replace modes!!
            #       what about autocomplete?
            # It would be possbile to just store the text that is inserted
            # however then actions would be ignored
            self.insert_action.append(key)
            if key in [65362, 65362]: # Arrow up / arrow down
                self.insert_action = []
            if not self.RunKeyChain((key,), m):
                evt.Skip()
            return





        if self._acceptable_keys is None or \
                                "*" not in self._acceptable_keys:
            if 48 <= key <= 57: # Normal
                if self.SetNumber(key-48):
                    return
            elif 65456 <= key <= 65465: # Numpad
                if self.SetNumber(key-65456):
                    return

        self.SetCount()

        if self._motion and self._acceptable_keys is None:
            #self._acceptable_keys = None
            self._motion.append(key)

            temp = self._motion[:-1]
            temp.append("*")
            if tuple(self._motion) in self.motion_keys[m]:
                self.RunKeyChain(tuple(self.key_inputs), m)
                return
                #self._motion = []
            elif tuple(temp) in self.motion_keys[m]:
                self._motion[-1] = "*"
                self._motion_wildcard.append(key)
                self.RunKeyChain(tuple(self.key_inputs), m)
                #self._motion = []
                return
                
            elif tuple(self._motion) in self.motion_key_mods[m]:
                #self._acceptable_keys = self.motion_key_mods[m][tuple(self._motion)]
                return

            self.FlushBuffers()
            return


        if self._acceptable_keys is not None:
            if key in self._acceptable_keys:
                self._acceptable_keys = None
                pass
            elif "*" in self._acceptable_keys:
                self._wildcard.append(key)
                self.key_inputs.append("*")
                self._acceptable_keys = None
                self.RunKeyChain(tuple(self.key_inputs), m)

                return
            elif "motion" in self._acceptable_keys:
                self._acceptable_keys = None
                self._motion.append(key)
                if (key,) in self.motion_keys[m]:
                    self.key_inputs.append("motion")
                    self.RunKeyChain(tuple(self.key_inputs), m)
                    return
                if (key,) in self.motion_key_mods[m]:
                    self.key_inputs.append("motion")
                    return


        self.key_inputs.append(key)
        self.updateViStatus()

        key_chain = tuple(self.key_inputs)

        if self.RunKeyChain(key_chain, m):
            return

        self.FlushBuffers()
            
    def TurnOff(self):
        self._enableMenuShortcuts(True)
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
                # TODO: handle modifier keys, e.g. ctrl
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
        # TODO: clean this up, move to ViHelper
        if self.last_cmd is not None:
            self.visualBell("GREEN")
            self.BeginUndo()
            cmd_type, key, count, motion, motion_wildcards, wildcards = self.last_cmd

            self.count = count
            actions = self.insert_action
            # NOTE: Is "." only going to repeat editable commands as in vim?
            if cmd_type == 1:
                self.RunFunction(key, motion, motion_wildcards, wildcards)
            # If a command ends in insertion mode we also repeat any changes
            # made up until the next mode change.
            elif cmd_type == 2: # + insertion
                self.RunFunction(key, motion, motion_wildcards, wildcards)
                # Emulate keypresses
                # Return to normal mode
                self.EmulateKeypresses(actions)
                self.SetMode(ViHandler.NORMAL)
            elif cmd_type == 3:
                self.ReplaceChar(key)
            self.EndUndo()
            self.insert_action = actions
        else:
            self.visualBell("RED")


#--------------------------------------------------------------------
# Misc stuff
#--------------------------------------------------------------------
    def Autocomplete(self, forwards):
        if not self.ctrl.AutoCompActive():
            # NOTE: list order is not correct
            if self.GetUnichrAt(self.ctrl.GetCurrentPos()-1) in \
                                self.WORD_BREAK_INCLUDING_WHITESPACE:
                word = u"[a-zA-Z0-9_]"
                word_length = 0

            else:
                # Vim only selects backwards
                self.SelectInWord()
                self.ExtendSelectionIfRequired()
                word = self.ctrl.GetSelectedText()
                word_length = len(word)


            # Search for possible autocompletions
            # Bad ordering at the moment
            text = self.ctrl.GetTextRange(
                        self.ctrl.GetCurrentPos(), self.ctrl.GetLength())
            word_list = re.findall(ur"\b{0}.*?\b".format(word), text, re.U)
            text = self.ctrl.GetTextRange(0, self.ctrl.GetCurrentPos())
            word_list.extend(re.findall(ur"\b{0}.*?\b".format(word), text, re.U))

            # No completions found
            if len(word_list) <= 1:
                if self.HasSelection():
                    self.ctrl.CharRight()
                self.visualBell("RED")
                return

            # Remove duplicates
            words = set()
            words.add(word)
            word_list_prepped = "\x01".join([i for i in word_list if i not in words and not words.add(i)])

            if self.HasSelection():
                self.ctrl.CharRight()
            self.ctrl.AutoCompShow(word_length, word_list_prepped)
            self.ctrl.Bind(wx.EVT_KEY_DOWN, self.OnAutocompleteKeyDown)

        
    def GotoSelectionStart(self):
        self.ctrl.GotoPos(self.ctrl.GetSelectionStart())

    def InsertPreviousText(self):
        self.EmulateKeypresses(self.insert_action)

    def InsertPreviousTextLeaveInsertMode(self):
        self.InsertPreviousText()
        self.SetMode(ViHelper.NORMAL)

    def ChangeSurrounding(self, keycodes):
        char_to_change = self.GetCharFromCode(keycodes[0])
        if char_to_change in self.text_object_map:
            self.SelectATextObject(char_to_change)
            if self.HasSelection():
                pos = self.ExtendSelectionIfRequired()
                self.BeginUndo()
                self.ctrl.ReplaceSelection(self.ctrl.GetSelectedText()[1:-1])
                self.ctrl.CharLeft()
                self.SelectSelection()
                self.SurroundSelection(keycodes[1])
                self.ctrl.GotoPos(pos)
                self.EndUndo()
                self.visualBell("GREEN")
                return
        self.visualBell("RED")

    def PreSurround(self, code):
        self.SelectSelection(False)
        self.SurroundSelection(code)

    def PreSurroundLine(self, code):
        self.SelectCurrentLine()
        self.SurroundSelection(code)

    def GetUnichrAt(self, pos):
        if -1 < pos < self.ctrl.GetLength():
            return self.ctrl.GetTextRaw()[pos]

    def SelectInTextObject(self, ob):
        self.SelectTextObject(ob, False)

    def SelectATextObject(self, ob):
        self.SelectTextObject(ob, True)

    def SelectTextObject(self, ob=None, extra=False):
        """
        Selects specified text object

        See vim help -> *text-objects*

        Two different selection methods are supported. They are given
        the names "In" and "A" corresponding to vim's "i(n)" and "a(n)"
        commands respectively.

        The differences between these is dependent on the type of text
        to be selected, it can be either a selection (e.g. words,
        sentences, etc...) or a block (e.g. text within [ ] or " " or
        ( ) etc...).
        """
        if ob in self.text_object_map:
            self.text_object_map[ob][1](extra)
            #if extra:  # extra corresponds to a
            #    if self.text_object_map[ob][0]: # text block
            #        pass # Select surrouding chars
            #    else:
            #        self.SelectTrailingWhitespace(sel_start, sel_end)

    def SelectTrailingWhitespace(self, sel_start, sel_end):
        self.StartSelection(sel_start)
        true_end = self.ctrl.GetCurrentPos()
        # Vim defaults to selecting trailing whitespace
        if self.ctrl.GetCharAt(sel_end+1) in \
                self.SINGLE_LINE_WHITESPACE or \
                self.ctrl.GetCharAt(sel_start) in \
                self.SINGLE_LINE_WHITESPACE:
            self.MoveCaretWordEndCountWhitespace(1)
        # or if not found it selects preceeding whitespace
        elif self.ctrl.GetCharAt(sel_start-1) \
                in self.SINGLE_LINE_WHITESPACE:
            pos = sel_start-1
            while self.ctrl.GetCharAt(pos-1) \
                    in  self.SINGLE_LINE_WHITESPACE:
                pos -= 1
            self.ctrl.GotoPos(pos)
            self.StartSelection()
            self.ctrl.GotoPos(true_end)
        self.SelectSelection()

    def SelectInWord(self, extra=False):
        """
        Selects n words where n is the count. Whitespace between words
        is counted.
        """
        self._SelectInWords(False, extra=extra)

    def SelectInWORD(self, extra=False):
        self._SelectInWords(True, extra=extra)
        
    def _SelectInWords(self, WORD=False, extra=False):
        # NOTE: Does not select single characters
        pos = self.ctrl.GetCurrentPos()

        if not WORD:
            back_word = self.MoveCaretBackWord
            move_caret_word_end_count_whitespace = \
                    self.MoveCaretWordEndCountWhitespace
        else:
            back_word = self.MoveCaretBackWORD
            move_caret_word_end_count_whitespace = \
                    self.MoveCaretWordENDCountWhitespace

        # If the caret is in whitespace the whitespace is selected
        if self.ctrl.GetCharAt(pos) in self.SINGLE_LINE_WHITESPACE:
            self.MoveCaretToWhitespaceStart()
        else:
            if pos > 0:
                if self.GetUnichrAt(pos-1) in string.whitespace:
                    pass
                elif ((self.GetUnichrAt(pos) in self.WORD_BREAK) is not (self.GetUnichrAt(pos-1) in self.WORD_BREAK)) and not WORD:
                    pass
                else:
                    back_word(1)
        self.StartSelection()
        move_caret_word_end_count_whitespace(1)
        self.SelectSelection()
        if extra:
            sel_start, sel_end = self._GetSelectionRange()
            self.SelectTrailingWhitespace(sel_start, sel_end)
        move_caret_word_end_count_whitespace(self.count-1)
        self.SelectSelection()

    def SelectInSentence(self, extra=False):
        """ Selects current sentence """
        # First check if we are at the start of a sentence already
        pos = start_pos = self.ctrl.GetCurrentPos()
        if pos > 0 and self.GetUnichrAt(pos-1) in string.whitespace:
            pos -= 1
            char = self.GetUnichrAt(pos-1)
            while pos > 0 and char in string.whitespace:
                pos -= 1
                char = self.GetUnichrAt(pos-1)
            if char in self.SENTENCE_ENDINGS_SUFFIXS:
                pos -= 1
                char = self.GetUnichrAt(pos-1)
                while pos > 0 and char in self.SENTENCE_ENDINGS_SUFFIXS:
                    pos -= 1
                    char = self.GetUnichrAt(pos-1)
            if char not in self.SENTENCE_ENDINGS:
                self.GotoSentenceStart(1)
        else:
            self.GotoSentenceStart(1)
        self.StartSelection()
        self.GotoSentenceEnd(1)
        self.SelectSelection()
        sel_start, sel_end = self._GetSelectionRange()
        self.ctrl.GotoPos(sel_start)
        if extra:
            self.count += 1
        self.GotoSentenceEndCountWhitespace()
        self.SelectSelection()

    def SelectInParagraph(self, extra=False):
        """ Selects current paragraph """
        # TODO: fix for multiple counts
        self.MoveCaretParaDown(1)
        self.MoveCaretParaUp(1)
        self.StartSelection()
        self.MoveCaretParaDown()
        self.ctrl.CharLeft()
        self.SelectSelection()

    def _SelectInBracket(self, bracket, extra=False, start_pos=None, count=None):
        if start_pos is None: start_pos = self.ctrl.GetCurrentPos()
        if count is None: count = self.count

        if self.SearchBackwardsForChar(bracket, count):
            pos = self.ctrl.GetCurrentPos()

            pre_text = self.ctrl.GetTextRange(pos, start_pos)

            while pre_text.count(bracket) - pre_text.count(self.BRACES[bracket]) \
                                                                != self.count:
                self.ctrl.CharLeft()
                if self.SearchBackwardsForChar(bracket, 1):
                    pos = self.ctrl.GetCurrentPos()
                    pre_text = self.ctrl.GetTextRange(pos, start_pos)
                else:
                    break

            if self.MatchBraceUnderCaret():
                self.StartSelection(pos)
                self.SelectSelection()
                sel_start, sel_end = self._GetSelectionRange()
                if not sel_start <= start_pos <= sel_end:
                    self.ctrl.GotoPos(sel_start-1)
                    self._SelectInBracket(bracket, extra, start_pos, count)
                else:
                    # Only select the brackets if required
                    if not extra:
                        self.StartSelection(pos+1)
                        # The sel_start below is ignored due to the
                        # StartSelection called above
                        self.ctrl.SetSelection(sel_start, sel_end-1)
            else:
                self.ctrl.GotoPos(start_pos)

    def SelectInSquareBracket(self, extra=False):
        """ Selects text in [ ] block """
        self._SelectInBracket("[", extra)

    def SelectInRoundBracket(self, extra=False):
        """ Selects text in ( ) block """
        self._SelectInBracket("(", extra)

    def SelectInInequalitySigns(self, extra=False):
        """ Selects text in < > block """
        self._SelectInBracket("<", extra)

    def SelectInTagBlock(self, extra=False):
        """ selects text in <aaa> </aaa> block """
        # TODO: requires method of textinput

    def SelectInBlock(self, extra=False):
        """ selects text in { } block """
        self._SelectInBracket("{", extra)

    def _SelectInChars(self, char, extra=False):
        pos = self.ctrl.GetCurrentPos()
        if self.SearchBackwardsForChar(char):
            start_pos = self.ctrl.GetCurrentPos()
            self.ctrl.GotoPos(pos)
            if self.SearchForwardsForChar(char):
                self.StartSelection(start_pos)
                self.SelectSelection()
                if not extra:
                    sel_start, sel_end = self._GetSelectionRange()
                    self.StartSelection(start_pos+1)
                    self.ctrl.SetSelection(sel_start, sel_end-1)

    def SelectInDoubleQuote(self, extra=False):
        """ selects text in " " block """
        self._SelectInChars('"', extra)

    def SelectInSingleQuote(self, extra=False):
        """ selects text in ' ' block """
        self._SelectInChars("'", extra)

    def SelectInTilde(self, extra=False):
        """ selects text in ` ` block """
        self._SelectInChars("`", extra)

    # ---------------------------------------

    def SelectInPoundSigns(self, extra=False):
        self._SelectInChars("\xc2", extra)

    def SelectInDollarSigns(self, extra=False):
        self._SelectInChars("$", extra)

    def SelectInHats(self, extra=False):
        self._SelectInChars("^", extra)

    def SelectInPercentSigns(self, extra=False):
        self._SelectInChars("%", extra)

    def SelectInAmpersands(self, extra=False):
        self._SelectInChars("&", extra)

    def SelectInStars(self, extra=False):
        self._SelectInChars("*", extra)

    def SelectInHyphens(self, extra=False):
        self._SelectInChars("-", extra)

    def SelectInUnderscores(self, extra=False):
        self._SelectInChars("_", extra)

    def SelectInEqualSigns(self, extra=False):
        self._SelectInChars("=", extra)

    def SelectInPlusSigns(self, extra=False):
        self._SelectInChars("+", extra)

    def SelectInExclamationMarks(self, extra=False):
        self._SelectInChars("!", extra)

    def SelectInQuestionMarks(self, extra=False):
        self._SelectInChars("?", extra)

    def SelectInAtSigns(self, extra=False):
        self._SelectInChars("@", extra)

    def SelectInHashs(self, extra=False):
        self._SelectInChars("#", extra)

    def SelectInApproxSigns(self, extra=False):
        self._SelectInChars("~", extra)

    def SelectInVerticalBars(self, extra=False):
        self._SelectInChars("|", extra)

    def SelectInSemicolons(self, extra=False):
        self._SelectInChars(";", extra)

    def SelectInColons(self, extra=False):
        self._SelectInChars(":", extra)

    def SelectInBackslashes(self, extra=False):
        self._SelectInChars("\\", extra)

    def SelectInForwardslashes(self, extra=False):
        self._SelectInChars("/", extra)


    def SurroundSelection(self, keycode):
        # TODO: expand to include cs, ds and ys
        start = self.ExtendSelectionIfRequired()

        text = self.ctrl.GetSelectedText()

        if len(text) < 1:
            return # Should never happen

        self.BeginUndo()

        # Fix for EOL
        if text[-1] == self.ctrl.GetEOLChar():
            sel_start, sel_end = self._GetSelectionRange()
            self.ctrl.SetSelection(sel_start, sel_end-1)
            text = self.ctrl.GetSelectedText()

        replacements = {
                        ")" : ("(", ")"),
                        "b" : ("(", ")"),
                        "}" : ("{", "}"),
                        "B" : ("{", "}"),
                        "]" : ("[", "]"),
                        "r" : ("[", "]"),
                        ">" : ("<", ">"),
                        "a" : ("<", ">"),

                        "(" : ("( ", " )"),
                        "{" : ("{ ", " }"),
                        "[" : ("[ ", " ]"),

                        # TODO
                        #"t" : ("<{0}>", "</{0}}"),
                        #"<" : ("<{0}>", "</{0}}"),

                        "'" : ("'", "'"),
                        '"' : ('"', '"'),
                        "`" : ("`", "`"),

                        }
        uni_chr = unichr(keycode)
        if uni_chr in replacements:
            new_text = "{0}{1}{2}".format(replacements[uni_chr][0], text, replacements[uni_chr][1])
        else:
            new_text = "{0}{1}{2}".format(uni_chr, text, uni_chr)

        self.ctrl.ReplaceSelection(new_text)
        self.LeaveVisualMode()
        self.ctrl.GotoPos(start)
        self.EndUndo()


    def CheckLineEnd(self):
        # TODO: fix
        line, line_pos = self.ctrl.GetCurLine()
        if self.mode not in [ViHelper.VISUAL, ViHelper.INSERT]:
            unicode_line = unicode(line)
            if len(line) > 1 and line_pos >= len(bytes(unicode_line))-1:
                # Necessary for unicode chars
                pos = self.ctrl.GetCurrentPos()-len(bytes(unicode_line[-1]))
                self.ctrl.GotoPos(pos)
                #self.ctrl.SetSelection(self.ctrl.GetCurrentPos(),self.ctrl.GetCurrentPos())
        #if self.ctrl.GetCurrentPos() == self.ctrl.GetLineEndPosition(self.ctrl.GetCurrentLine()):
        #    self.MoveCaretLeft()

    def SelectCurrentLine(self, include_eol=True):
        line_no = self.ctrl.GetCurrentLine()
        max_line = min(line_no+self.count-1, self.ctrl.GetLineCount())
        start = self.GetLineStartPos(line_no)
        end = self.ctrl.GetLineEndPosition(max_line)

        # If we are deleting the last line we also need to delete
        # the eol char at the end of the new last line.
        if max_line + 1 == self.ctrl.GetLineCount():
            start -= 1

        if include_eol:
            end += 1
        self.ctrl.SetSelection(end, start)

    def SelectFullLines(self):
        """
        Could probably be replaced by SetSectionMode,
        if it can be made to work.
        """
        start_line, end_line = self._GetSelectedLines()
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

    # TODO: Clean up selection names
    def GetSelectionAnchor(self):
        return self._anchor

    def StartSelection(self, pos=None):
        """ Saves the current position to be used for selection start """
        if pos is None:
            pos = self.ctrl.GetCurrentPos()
        self._anchor = pos

    def StartSelectionAtAnchor(self):
        """
        Saves the current position to be used for selection start using
        the anchor as the selection start.
        """
        if len(self.ctrl.GetSelectedText()) > 0:
            self._anchor = self.ctrl.GetAnchor()
        else:
            self._anchor = self.ctrl.GetCurrentPos()


    def SelectInLink(self):
        pos = self.ctrl.GetCurrentPos()
        start_pos = self.FindChar(91, True, 0, 1, False)
        self.StartSelection()
        end_pos = self.FindChar(93, False, -1, 1, False)

        if start_pos and end_pos:
            self.SelectSelection()

    def SelectSelection(self, offset_motion=True):
        # Fix for actions to end of word/WORD (deleting, yanking..)
        # These are cases in which vim will perform an action on
        # an extra character. (Would it be easier to go the other way?)
        if offset_motion and self._motion in (
                [101], [69], [36], [102, "*"], [70, "*"], [116, "*"], [84, "*"]):
            #self.ctrl.CharRight()
            self.ExtendSelectionIfRequired()

        self.ctrl.SetSelection(self._anchor, self.ctrl.GetCurrentPos())


    def SelectionOnSingleLine(self):
        """
        Assume that if an EOL char is present we have mutiple lines
        """
        if self.ctrl.GetEOLChar() in self.ctrl.GetSelectedText():
            return False
        else:
            return True

    def ExtendSelectionIfRequired(self):
        """
        If selection is positive the last character is not actually
        selected and so a correction must be applied
        """
        start, end = self._GetSelectionRange()
        if self.ctrl.GetCurrentPos() == end:
            self.ctrl.CharRightExtend()
        return start

    def DeleteSelection(self):
        """Yank selection and delete it"""
        #if self.mode == ViHelper.VISUAL:
        #    start = self.ExtendSelectionIfRequired()
        self.BeginUndo()
        self.YankSelection()
        self.ctrl.Clear()
        #self.ctrl.GotoPos(start)
        self.EndUndo()
        self.LeaveVisualMode()

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

    def PreUppercase(self):
        start = self.ExtendSelectionIfRequired()
        self.SelectSelection()
        self.ctrl.ReplaceSelection(self.ctrl.GetSelectedText().upper())
        self.ctrl.GotoPos(start)

    def PreLowercase(self):
        start = self.ExtendSelectionIfRequired()
        self.SelectSelection()
        self.ctrl.ReplaceSelection(self.ctrl.GetSelectedText().lower())
        self.ctrl.GotoPos(start)

    def SwapCase(self):
        self.BeginUndo()
        text = self.ctrl.GetSelectedText()
        if len(text) == 0:
            self.StartSelection()
            self.MoveCaretRight()
            self.SelectSelection()
            text = self.ctrl.GetSelectedText()
        self.ctrl.ReplaceSelection(text.swapcase())
        self.EndUndo()

    def UpperCase(self):
        self.ctrl.ReplaceSelection(self.ctrl.GetSelectedText().upper())

    def LowerCase(self):
        self.ctrl.ReplaceSelection(self.ctrl.GetSelectedText().lower())

    def Indent(self, forward=True, repeat=1, visual=False):
        if visual == True:
            repeat = self.count

        self.BeginUndo()
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
        self.EndUndo()

    def _PositionViewport(self, n):
        """
        Helper function for ScrollViewport* functions.

        Positions the viewport around caret position

        """
        lines = self.ctrl.LinesOnScreen() - 1
        current = self.ctrl.GetCurrentLine()
        diff = int(lines * n)
        self.ctrl.ScrollToLine(current - diff)

    def GetViewportPosition(self):
        lines = self.ctrl.LinesOnScreen() - 1
        current = self.ctrl.GetCurrentLine()
        first_visible_line = self.ctrl.GetFirstVisibleLine()

        n = current - first_visible_line

        return n / float(lines)

    def _ScrollViewportByLines(self, n):
        first_visible_line = self.ctrl.GetFirstVisibleLine()
        lines_on_screen = self.ctrl.LinesOnScreen()

        line = max(0, first_visible_line + n)
        line = min(line, self.ctrl.GetLineCount() - lines_on_screen)
        self.ctrl.ScrollToLine(line)
        if self.ctrl.GetCurrentLine() < line:
            self.ctrl.LineDown()
        elif self.ctrl.GetCurrentLine() > first_visible_line + lines_on_screen-2:
            self.ctrl.LineUp()

    def _ScrollViewport(self, n):
        view_pos = self.GetViewportPosition()
        lines = self.ctrl.LinesOnScreen()
        current_line = self.ctrl.GetCurrentLine()
        new_line = max(0, current_line + n * lines)
        new_line = min(new_line, self.ctrl.GetLineCount())
        self.GotoLineIndent(new_line)
        self._PositionViewport(view_pos)

    def IndentText(self):
        """
        Post motion function. Select text and indent it
        """
        self.SelectSelection()
        self.Indent(True)

    def DedentText(self):
        """
        Post motion function. Select text and deindent it
        """
        self.SelectSelection()
        self.Indent(False)

    #--------------------------------------------------------------------
    # Visual mode
    #--------------------------------------------------------------------

    def EnterLineVisualMode(self):
        """
        Enter line visual mode
        
        Sets a special type of visual mode in which only full lines can
        be selected.

        NOTE:
        Should be possible using StyledTextCtrl.SetSelectionType() but
        for some reason I can't get it to work so a SetSelMode() has
        been implemented.
        
        """
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
        self.ctrl.GotoPos(self.ctrl.GetSelectionStart())
        if self.mode == ViHelper.VISUAL:
            self.SetSelMode("NORMAL")
            self.SetMode(ViHelper.NORMAL)

    def EnterVisualMode(self, mouse=False):
        """
        Change to visual (selection) mode
        
        Will do nothing if already in visual mode

        @param mouse: Visual mode was started by mouse action

        """
        if self.mode != ViHelper.VISUAL:
            self.SetMode(ViHelper.VISUAL)

            if not mouse:
                self.StartSelectionAtAnchor()

                #if self.ctrl.GetSelectedText() > 0:
                #    self.MoveCaretRight()
            else:
                self.StartSelection(self.ctrl.GetSelectionEnd())

    #--------------------------------------------------------------------
    # Searching
    #--------------------------------------------------------------------

    def SearchForwardsForChar(self, search_char, count=None, 
                                    wrap_lines=True, start_offset=-1):
        if count is None: count = self.count
        pos = start_pos = self.ctrl.GetCurrentPos() + start_offset

        text = self.ctrl.GetTextRaw()
        #text_to_search = text[pos:]

        n = 0
        for i in range(count):
            pos = text.find(search_char, pos + 1)
            

            
        if pos > -1:
            if not wrap_lines:
                # TODO: fix eol searching
                text_to_check = self.ctrl.GetTextRange(start_pos, pos)
                if self.ctrl.GetEOLChar() in text_to_check:
                    return False
            self.ctrl.GotoPos(pos)
            return True

        self.visualBell("RED")
        return False

    def SearchBackwardsForChar(self, search_char, count=None, 
                                    wrap_lines=True, start_offset=0):
        """
        Searches backwards in text for character.

        @param search_char: Character to search for.
        @param count: Number of characeters to find.
        @param wrap_lines: Should search occur on multiple lines.
        @param start_offset: Start offset for searching. Should be
            zero if character under the caret should be included in
            the search, -1 if not.

        @rtype: bool
        @return: True if successful, False if not.

        """
        if count is None: count = self.count
        pos = start_pos = self.ctrl.GetCurrentPos() + start_offset

        text = self.ctrl.GetTextRaw()
        text_to_search = text[:pos+1]
        for i in range(count):
            pos = text_to_search.rfind(search_char)
            text_to_search = text[:pos]
            
        if pos > -1:
            if not wrap_lines:
                text_to_check = self.ctrl.GetTextRange(start_pos, pos)
                if self.ctrl.GetEOLChar() in text_to_check:
                    return False
            self.ctrl.GotoPos(pos)
            return True

        self.visualBell("RED")
        return False

    def FindMatchingBrace(self, brace):
        if brace in self.BRACES:
            forward = True
            b = self.BRACES
        elif brace in self.REVERSE_BRACES:
            forward = False
            b = self.REVERSE_BRACES
        else:
            return

        start_pos = self.ctrl.GetCurrentPos()
        if forward:
            text = self.ctrl.GetTextRaw()[start_pos+1:]
        else:
            text = self.ctrl.GetTextRaw()[0:start_pos:][::-1]
        brace_count = 1
        n = 0
        pos = -1
        for i in text:
            n += 1
            if i == brace:
                brace_count += 1
            elif i == b[brace]:
                brace_count -= 1

            if brace_count < 1:
                if forward:
                    pos = start_pos + n
                else:
                    pos = start_pos - n
                break

        if pos > -1:
            self.ctrl.GotoPos(pos)
            return True
        else:
            self.visualBell("RED")
            return False

    def FindChar(self, code=None, reverse=False, offset=0, count=1, \
                                                            repeat=True):
        """
        Searches current *line* for specified character. 
        
        Will move the caret to this place (+/- any offset supplied).

        @param code: keycode of character to search for.
        @param reverse: If True will search backwards.
        @param offset: Offset to move caret post search.
        @param count: Number of characters to find. If not all found,
            i.e. count is 3 but only 2 characters on current line, will 
            not move caret.
        @param repeat: Should the search be saved so it will be
            repeated (by "," and ";")

        @rtype: bool
        @return: True if successful, False if not.

        """
        if code is None:
            return False
        # Weird stuff happens when searching for a unicode string
        char = bytes(self.GetCharFromCode(code))
        pos = self.ctrl.GetCurrentPos()
        
        if repeat:
            # First save cmd so it can be repeated later
            # Vim doesn't save the count so a new one can be used next time
            self.last_find_cmd = {
                                            "code": code, 
                                            "reverse": reverse,
                                            "offset": offset,
                                            "repeat": False
                                            }

        if reverse: # Search backwards
            search_cmd = self.SearchBackwardsForChar
            start_offset = -1
            offset = - offset

        else: # Search forwards
            search_cmd = self.SearchForwardsForChar
            start_offset = 0
         
        if search_cmd(char, count, False, start_offset):
            self.MoveCaretPos(offset)
            self.ctrl.ChooseCaretX()
            return True

        return False

    def FindNextChar(self, keycode):
        self.FindChar(keycode, count=self.count)
        
    def FindNextCharBackwards(self, keycode):
        cmd = self.FindChar(keycode, count=self.count, reverse=True)

    def FindUpToNextChar(self, keycode):
        cmd = self.FindChar(keycode, count=self.count, offset=-1)
        
    def FindUpToNextCharBackwards(self, keycode):
        cmd = self.FindChar(keycode, count=self.count, reverse=True, offset=-1)

    def GetLastFindCharCmd(self):
        return self.last_find_cmd

    def RepeatLastFindCharCmd(self):
        args = self.GetLastFindCharCmd()
        if args is not None: 
            # Set the new count
            args["count"] = self.count
            self.FindChar(**args)
        
    def RepeatLastFindCharCmdReverse(self):
        args = self.GetLastFindCharCmd()
        if args is not None: 
            args["count"] = self.count
            args["reverse"] = not args["reverse"]
            self.FindChar(**args)
            args["reverse"] = not args["reverse"]

    def MatchBraceUnderCaret(self):
        return self.FindMatchingBrace(self.GetUnichrAt(
                                                self.ctrl.GetCurrentPos()))

    # TODO: vim like searching
    def _SearchText(self, text, forward=True, match_case=True, wrap=True, 
                                                            whole_word=True):
        """
        Searches for next occurance of 'text'

        @param text: text to search for
        @param forward: if true searches forward in text, else
                        search in reverse
        @param match_case: should search be case sensitive?  
        """
        self.AddJumpPosition(self.ctrl.GetCurrentPos() - len(text))

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

    def _SearchCaretWord(self, forward=True, match_case=True, whole_word=True):
        """
        Searches for next occurance of word currently under
        the caret

        @param forward: if true searches forward in text, else
                        search in reverse
        @param match_case: should search be case sensitive?  
        @param whole_word: must the entire string match as a word
        """ 
        self.SelectInWord()
        self.ExtendSelectionIfRequired()
        text = self.ctrl.GetSelectedText()
        #offset = 1 if forward else -1
        #self.MoveCaretPos(offset)
        if forward:
            self.ctrl.CharRight()
        else:
            self.ctrl.CharLeft()
        self.ctrl.SearchAnchor()
        self._SearchText(text, forward, match_case=match_case, wrap=True, whole_word=whole_word)
        
        self.last_search_args = {'text' : text, 'forward' : forward, 
                                 'match_case' : match_case, 
                                 'whole_word' : whole_word}

    def SearchCaretWordForwards(self):
        """Helper function to allow repeats"""
        self._SearchCaretWord(True, True, True)

    def SearchPartialCaretWordForwards(self):
        self._SearchCaretWord(True, True, False)

    def SearchCaretWordBackwards(self):
        """Helper function to allow repeats"""
        self._SearchCaretWord(False, True, True)

    def SearchPartialCaretWordBackwards(self):
        self._SearchCaretWord(False, True, False)

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
            self.ctrl.GotoPos(sel_start)
        else:
            count = self.count

        # Replace does not wrap lines and fails if you try and replace 
        # non existent chars
        line, pos = self.ctrl.GetCurLineRaw()
        line_length = len(line)

        # If we are on the last line we need to increase the line 
        # length by 1 (as the last line has no eol char)
        if self.ctrl.GetLineCount() == self.ctrl.GetCurrentLine() + 1:
            line_length += 1

        if pos + count > line_length:
            return

        self.last_cmd = 3, keycode, count, None

        self.BeginUndo()
        self.StartSelection()
        self.ctrl.GotoPos(self.ctrl.GetCurrentPos()+count)
        self.EndDelete()
        self.Repeat(self.InsertText, arg=char)
        if pos + count != line_length:
            self.MoveCaretPos(-1)
        self.EndUndo()

    def StartReplaceMode(self):
        # TODO: visual indication
        self.BeginUndo()
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
        # TODO '' and `` goto previous jump
        page = self.ctrl.presenter.getWikiWord()
        if char in self.marks[page]:
            self.AddJumpPosition()
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
        if self.mode == ViHelper.VISUAL:
            self.ExtendSelectionIfRequired()
        if lines:
            self.SelectFullLines()
            self.ctrl.CharRightExtend()
        elif self.GetSelMode() == "LINE":
            # Selection needs to be the correct way round
            start, end = self._GetSelectionRange()
            self.ctrl.SetSelection(start, end)
            self.ctrl.CharRightExtend()

        self.ctrl.Copy()

    def Yank(self, lines=False):
        self.SelectSelection()
        #if self.mode == ViHelper.VISUAL:
        #    start = self.ExtendSelectionIfRequired()
        self.YankSelection(lines)
        self.GotoSelectionStart()

    def Put(self, before, count=None):
        count = count if count is not None else self.count
        text = getTextFromClipboard()

        self.BeginUndo(True)

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


        if is_line:
            if not before:  
                # If pasting a line we have to goto the end before moving caret 
                # down to handle long lines correctly
                self.ctrl.LineEnd()
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

        self.EndUndo()
                
    #--------------------------------------------------------------------
    # Deletion commands
    #--------------------------------------------------------------------
    def DeleteSurrounding(self, code):
        char = self.GetCharFromCode(code)
        if char in self.text_object_map:
            self.SelectATextObject(char)
            pos = self.ExtendSelectionIfRequired()
            self.ctrl.ReplaceSelection(self.ctrl.GetSelectedText()[1:-1])
            self.ctrl.GotoPos(pos)

    def EndDelete(self):
        self.SelectSelection()
        self.DeleteSelection()

    def EndDeleteInsert(self):
        self.SelectSelection()
        self.DeleteSelection()
        self.Insert()

    def DeleteRight(self):
        self.ctrl.BeginUndoAction
        self.StartSelection()
        self.MoveCaretRight()
        self.SelectSelection()
        
        # If the selection len is less than the count we need to select
        # the last character on the line
        if len(self.ctrl.GetSelectedText()) < self.count:
            self.ctrl.CharRightExtend()
        self.DeleteSelection()
        self.EndUndo()
        self.CheckLineEnd()

    def DeleteLeft(self):
        self.BeginUndo()
        self.StartSelection()
        self.MoveCaretLeft()
        self.SelectSelection()
        self.DeleteSelection()
        self.EndUndo()

    def DeleteRightAndInsert(self):
        self.DeleteRight()
        self.Insert()

    def DeleteLinesAndIndentInsert(self):
        self.BeginUndo()
        indent = self.ctrl.GetLineIndentation(self.ctrl.GetCurrentLine())
        self.DeleteLine()
        self.OpenNewLine(True, indent=indent)
        self.EndUndo()

    def DeleteLine(self):
        self.BeginUndo()
        self.SelectCurrentLine()
        self.DeleteSelection()
        self.EndUndo()
        

    #--------------------------------------------------------------------
    # Movement commands
    #--------------------------------------------------------------------

    def GetLineStartPos(self, line):
        return self.ctrl.GetLineIndentPosition(line) - \
                                    self.ctrl.GetLineIndentation(line)

    def GotoLineStart(self):
        self.ctrl.Home()

    def GotoLineEnd(self, true_end=True):
        self.ctrl.LineEnd()
        if not true_end:
            self.ctrl.CharLeft()

    def GotoLineIndentPreviousLine(self):
        line = max(0, self.ctrl.GetCurrentLine()-1)
        self.GotoLineIndent(line)

    def GotoLineIndentNextLine(self):
        line = min(self.ctrl.GetLineCount(), self.ctrl.GetCurrentLine()+1)
        self.GotoLineIndent(line)

    def GotoLineIndent(self, line=None):
        """
        Moves caret to first non-whitespace character on "line".

        If "line" is None current line is used.

        @param line: Line number

        """
        if line is None: line = self.ctrl.GetCurrentLine()
        self.ctrl.GotoPos(self.ctrl.GetLineIndentPosition(line))
        self.ctrl.ChooseCaretX()

    def GotoColumn(self, pos=None):
        """
        Moves caret to "pos" on current line. If no pos specified use "count".

        @param pos: Column position to move caret to.
        """
        if pos is None: pos = self.count
        line = self.ctrl.GetCurrentLine()
        lstart = self.ctrl.PositionFromLine(line)
        lend = self.ctrl.GetLineEndPosition(line)
        line_len = lend - lstart
        column = min(line_len, pos)
        self.ctrl.GotoPos(lstart + column)

        self.ctrl.ChooseCaretX()

    def GotoSentenceStart(self, count=None):
        self.AddJumpPosition()
        self.Repeat(self._MoveCaretSentenceStart, count)

    def _MoveCaretSentenceStart(self, pos=None, start_pos=None):
        """
        Internal function to move caret to sentence start.

        Call GotoSentenceStart instead.
        """
        if pos is None:
            pos = self.ctrl.GetCurrentPos()-1
        if start_pos is None:
            start_pos = pos
        char = self.GetUnichrAt(pos)

        page_length = self.ctrl.GetLength()

        text = self.ctrl.GetText()[:pos] 

        n = -1
        for i in self.SENTENCE_ENDINGS:
            index = text.rfind(i)
            if index != -1 and index > n:
                n = index
        pos = n

        if pos < 1:
            self.ctrl.GotoPos(0)
            return

        sentence_end_pos =  pos
        forward_char = self.GetUnichrAt(pos+1)
        if forward_char in self.SENTENCE_ENDINGS_SUFFIXS:
            pos += 1
            while forward_char in self.SENTENCE_ENDINGS_SUFFIXS:
                pos += 1
                forward_char = self.GetUnichrAt(pos)
        if forward_char in string.whitespace:
            while forward_char in string.whitespace:
                pos += 1
                forward_char = self.GetUnichrAt(pos)
        else:
            self._MoveCaretSentenceStart(pos-1, start_pos)
            return

        if start_pos >= pos:
            self.ctrl.GotoPos(pos)
        else:
            self._MoveCaretSentenceStart(sentence_end_pos-1, start_pos)

    def GotoNextSentence(self, count=None):
        self.AddJumpPosition()
        self.Repeat(self._MoveCaretNextSentence, count)

    def GotoSentenceEnd(self, count=None):
        self.Repeat(self._MoveCaretNextSentence, count, False)

    def GotoSentenceEndCountWhitespace(self, count=None):
        if count is None: count = self.count

        if count % 2:
            include_whitespace = False
            count = count / 2 + 1
            move_left = False
        else:
            include_whitespace = True
            count = count / 2 
            move_left = True
        
        self.Repeat(self._MoveCaretNextSentence, count, include_whitespace)

        if move_left:
            self.ctrl.CharLeftExtend()

        #self.ctrl.CharLeftExtend()

    def _MoveCaretNextSentence(self, include_whitespace=True, 
                                        pos=None, start_pos=None):
        # Could be combined with _MoveCaretBySentence func
        if pos is None:
            pos = self.ctrl.GetCurrentPos()+1
        if start_pos is None:
            start_pos = pos
        char = self.GetUnichrAt(pos)

        page_length = self.ctrl.GetLength()

        text = self.ctrl.GetText()[pos:] 

        n = page_length
        for i in self.SENTENCE_ENDINGS:
            index = text.find(i)
            if index != -1 and index < n:
                n = index
        pos = pos + n

        if pos+1 >= page_length:
            self.ctrl.GotoPos(page_length)
            return

        sentence_end_pos = pos
        forward_char = self.GetUnichrAt(pos+1)
        if forward_char in self.SENTENCE_ENDINGS_SUFFIXS:
            pos += 1
            while forward_char in self.SENTENCE_ENDINGS_SUFFIXS:
                pos += 1
                forward_char = self.GetUnichrAt(pos)
            sentence_end_pos = pos-1
        if forward_char in string.whitespace:
            while forward_char in string.whitespace:
                pos += 1
                forward_char = self.GetUnichrAt(pos)
        else:
            self._MoveCaretNextSentence(include_whitespace, pos+1, start_pos)
            return

        if start_pos <= pos:
            if include_whitespace:
                self.ctrl.GotoPos(pos)
            else:
                self.ctrl.GotoPos(sentence_end_pos)
        else:
            self._MoveCaretNextSentence(include_whitespace, 
                                            sentence_end_pos, start_pos)

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
        self.Repeat(self.ctrl.LineUp, count)
        self.CheckLineEnd()

    def MoveCaretDown(self, count=None):
        self.Repeat(self.ctrl.LineDown, count)
        self.CheckLineEnd()

    def MoveCaretToLine(self, line):
        current_line = self.ctrl.GetCurrentLine()
        if line == current_line:
            return

        if line < current_line:
            scroll_func = self.ctrl.LineUp
        else:
            scroll_func = self.ctrl.LineDown

        to_move = abs(current_line - line)

        for i in range(to_move):
            scroll_func()


    def MoveCaretDownAndIndent(self, count=None):
        self.Repeat(self.ctrl.LineDown, count)
        self.GotoLineIndent()

    def MoveCaretLeft(self):
        self.MoveCaretPos(-self.count)

    def MoveCaretPos(self, offset):
        """
        Move caret by a given offset
        """
        line, line_pos = self.ctrl.GetCurLine()
        line_no = self.ctrl.GetCurrentLine()

        if self.mode == ViHelper.VISUAL:
            if offset > 0:
                move_right = True
                move = self.ctrl.CharRightExtend
                stop_pos = self.GetLineStartPos(line_no) + \
                                self.ctrl.LineLength(line_no)-1
            else:
                move_right = False
                move = self.ctrl.CharLeftExtend
                stop_pos = self.GetLineStartPos(line_no)
        else:
            if offset > 0:
                move_right = True
                move = self.ctrl.CharRight
                stop_pos = self.GetLineStartPos(line_no) + \
                                self.ctrl.LineLength(line_no)-2

                # Fix for last line (no EOL char present)
                if line_no+1 == self.ctrl.GetLineCount():
                    stop_pos += 1
            else:
                move_right = False
                move = self.ctrl.CharLeft
                stop_pos = self.GetLineStartPos(line_no)

        for i in range(abs(offset)):
            if (move_right and self.ctrl.GetCurrentPos() < stop_pos) or \
               (not move_right and self.ctrl.GetCurrentPos() > stop_pos):
                move()
            else:
                break

        ## The code below is faster but does not handle
        ## unicode charcters nicely
        #line, line_pos = self.ctrl.GetCurLine()
        #line_no = self.ctrl.GetCurrentLine()
        #pos = max(line_pos + offset, 0)
        #if self.mode == ViHelper.VISUAL:
        #    pos = min(pos, self.ctrl.LineLength(line_no)-1)
        #else:
        #    pos = min(pos, self.ctrl.LineLength(line_no)-2)
        #self.ctrl.GotoPos(self.GetLineStartPos(line_no) + pos)
        #self.ctrl.ChooseCaretX()

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
    def MoveCaretWordEndCountWhitespace(self, count=None):
        self.Repeat(self._MoveCaretWord, count, 
                        { "recursion" : False, "count_whitespace" : True, \
                                    "only_whitespace" : False })

    def MoveCaretNextWord(self, count=None):
        self.Repeat(self.ctrl.WordRight, count)

    def MoveCaretPreviousWordEnd(self, count=None):
        # TODO: complete
        self.Repeat(self._MoveCaretWord, count, { 
                                    "recursion" : False, 
                                    "count_whitespace" : False, 
                                    "only_whitespace" : False,
                                    "reverse" : True
                                    })

    def MoveCaretWordEnd(self, count=None):
        self.Repeat(self._MoveCaretWord, count)

    def _MoveCaretWord(self, recursion=False, count_whitespace=False, 
                                        only_whitespace=False, reverse=False):
        """
        wxStyledTextCtrl's WordEnd function behaves differently to
        vims so it need to be replaced to get equivalent function

        """
        pos = start_pos = self.ctrl.GetCurrentPos()
        char = self.GetUnichrAt(pos)

        if char is None:
            return

        text_length = self.ctrl.GetTextLength()

        if reverse:
            offset = -1
            move = self.ctrl.CharLeft
            move_extend = self.ctrl.CharLeftExtend
        else:
            offset = 1
            move = self.ctrl.CharRight
            move_extend = self.ctrl.CharRightExtend

        # If the current char is whitespace we either skip it or count
        # it depending on "count_whitespace"
        if char in string.whitespace:
            char = self.GetUnichrAt(pos + offset)
            if char is not None:
                while char is not None and char in string.whitespace:
                    pos = pos + offset
                    char = self.GetUnichrAt(pos + offset)
            if not count_whitespace:
                self._GotoPos(pos)
                move()
                self._MoveCaretWord(recursion=True, 
                                   count_whitespace=count_whitespace, 
                                   only_whitespace=only_whitespace, 
                                   reverse=reverse)
                return
        # If we want a minor word end and start in punctuation we goto
        # end of the punctuation
        elif not only_whitespace and char in self.WORD_BREAK:
            char = self.GetUnichrAt(pos + offset)
            if char is not None:
                while char is not None and char in self.WORD_BREAK:
                    pos = pos + offset
                    char = self.GetUnichrAt(pos + offset)
        # Else offset forwards to first punctuation or whitespace char
        # (or just whitespace char if only_whitespace = True)
        else:
            char = self.GetUnichrAt(pos + offset)
            if char is not None:
                while char is not None and \
                        ((only_whitespace or char not in self.WORD_BREAK) and \
                        char not in string.whitespace) or char in ("_"):
                    pos = pos + offset
                    char = self.GetUnichrAt(pos + offset)
 
        if pos != start_pos or recursion:
            self._GotoPos(pos)
        else:
            move_extend()
            self._MoveCaretWord(True, count_whitespace=count_whitespace, 
                        only_whitespace=only_whitespace, reverse=reverse)
            return

    def MoveCaretToWhitespaceStart(self):
        start = self.ctrl.GetCurrentPos()
        while self.ctrl.GetCharAt(start-1) in self.SINGLE_LINE_WHITESPACE:
            start -= 1
        self.ctrl.GotoPos(start)

    def MoveCaretBackWord(self, count=None):
        self.Repeat(self._MoveCaretWord, count, { 
                                    "recursion" : False, 
                                    "count_whitespace" : False, 
                                    "only_whitespace" : False,
                                    "reverse" : True
                                    })

    def MoveCaretBackWORD(self, count=None):
        self.Repeat(self._MoveCaretWord, count, { 
                                    "recursion" : False, 
                                    "count_whitespace" : False, 
                                    "only_whitespace" : True,
                                    "reverse" : True
                                    })

    def MoveCaretNextWORD(self, count=None):
        """Wordbreaks are spaces"""
        def func():
            self.ctrl.WordRight()
            while self.GetChar(-1) and not self.GetChar(-1).isspace():
                self.ctrl.WordRight()
        self.Repeat(func, count)

    def MoveCaretWordEND(self, count=None):
        self.Repeat(self._MoveCaretWord, count, { 
                                    "recursion" : False, 
                                    "count_whitespace" : False, 
                                    "only_whitespace" : True 
                                    })

    def MoveCaretWordENDCountWhitespace(self, count=None):
        self.Repeat(self._MoveCaretWord, count, { 
                                    "recursion" : False, 
                                    "count_whitespace" : True, 
                                    "only_whitespace" : True 
                                    })

    def MoveCaretParaUp(self, count=None):
        self.AddJumpPosition()
        self.Repeat(self.ctrl.ParaUp, count)

    def MoveCaretParaDown(self, count=None):
        self.AddJumpPosition()
        self.Repeat(self.ctrl.ParaDown, count)

    def _GotoPos(self, pos):
        """
        Save caret position
        """
        self.ctrl.GotoPos(pos)
        self.ctrl.ChooseCaretX()

    def DocumentNavigation(self, key):
        """
        It may be better to seperate this into multiple functions
        """
        if key in [71, (103, 103), 37]:
            self.AddJumpPosition()
        
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
            self.MatchBraceUnderCaret()

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

    def ScrollViewportUpHalfScreen(self):
        self._ScrollViewport(-0.5)

    def ScrollViewportUpFullScreen(self):
        # vim has a 2 line offset
        # see *03.7* 
        self._ScrollViewport(-1)

    def ScrollViewportDownHalfScreen(self):
        self._ScrollViewport(0.5)

    def ScrollViewportDownFullScreen(self):
        self._ScrollViewport(1)

    def ScrollViewportLineDown(self):
        self._ScrollViewportByLines(1)

    def ScrollViewportLineUp(self):
        self._ScrollViewportByLines(-1)

    def Undo(self, count=None):
        if self.ctrl.CanUndo():
            self.visualBell("GREEN")
            self.Repeat(self._Undo, count)
        else:
            self.visualBell("RED")

    def Redo(self, count=None):
        if self.ctrl.CanRedo():
            self.visualBell("GREEN")
            self.Repeat(self._Redo, count)
        else:
            self.visualBell("RED")

# The following commands are basic ways to enter insert mode
    def Insert(self):
        self.BeginUndo(True)
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
        self.BeginUndo(True)
        self.BeginUndo()

        if indent is None:
            indent = self.ctrl.GetLineIndentation(self.ctrl.GetCurrentLine())

        if above:
            self.MoveCaretUp(1)
        self.GotoLineEnd()
        self.ctrl.AddText(self.ctrl.GetEOLChar())
        self.ctrl.SetLineIndentation(self.ctrl.GetCurrentLine(), indent)
        self.EndUndo()
        self.AppendAtLineEnd()

    def TruncateLine(self):
        self.ctrl.LineEndExtend()
        self.ctrl.CharLeftExtend()
        self.ExtendSelectionIfRequired()
        self.DeleteSelection()

    def TruncateLineAndInsert(self):
        self.TruncateLine()
        self.Insert()
