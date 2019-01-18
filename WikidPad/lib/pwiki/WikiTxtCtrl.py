
## import hotshot
## _prof = hotshot.Profile("hotshot.prf")

import traceback, codecs
from io import StringIO
import string, itertools, contextlib
import re # import pwiki.srePersistent as re
import threading

import subprocess
import textwrap

from os.path import exists, dirname, isfile, isdir, join, basename
from os import rename, unlink, listdir

from time import time, sleep

import wx, wx.stc

from Consts import FormatTypes

from .Utilities import DUMBTHREADSTOP, callInMainThread, ThreadHolder, \
        calcResizeArIntoBoundingBox, DictFromFields, seqEnforceContained

from .wxHelper import GUI_ID, getTextFromClipboard, copyTextToClipboard, \
        wxKeyFunctionSink, getAccelPairFromKeyDown, appendToMenuByMenuDesc
from . import wxHelper

from . import OsAbstract

from .WikiExceptions import *

from .SystemInfo import isOSX, isLinux, isWindows

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

# NOTE: TEMPORARY
import inspect


from .ViHelper import ViHintDialog, ViHelper
from collections import defaultdict
from functools import reduce

try:
    from . import WindowsHacks
except:
    if isWindows():
        traceback.print_exc()
    WindowsHacks = None


# Python compiler flag for float division
CO_FUTURE_DIVISION = 0x2000


# Disable setting of wx.MouseEvent.m_wheelRotation in OnMouseWheel in case
# of AttributeError
disableMouseWheelSetting = False



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

        # TODO: set wrap indent mode (for wx >= 2.9)
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
        # self.SetMarginWidth(self.SELECT_MARGIN, 16)
        # self.SetMarginWidth(self.NUMBER_MARGIN, 0)

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

        for i in range(32):
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


        self.Bind(wx.stc.EVT_STC_STYLENEEDED, self.OnStyleNeeded, id=ID)
        self.Bind(wx.stc.EVT_STC_CHARADDED, self.OnCharAdded, id=ID)
        self.Bind(wx.stc.EVT_STC_MODIFIED, self.OnModified, id=ID)
        self.Bind(wx.stc.EVT_STC_USERLISTSELECTION, self.OnUserListSelection, id=ID)
        self.Bind(wx.stc.EVT_STC_MARGINCLICK, self.OnMarginClick, id=ID)
        self.Bind(wx.stc.EVT_STC_DWELLSTART, self.OnDwellStart, id=ID)
        self.Bind(wx.stc.EVT_STC_DWELLEND, self.OnDwellEnd, id=ID)

#         self.Bind(wx.EVT_LEFT_DOWN, self.OnClick)
        self.Bind(wx.EVT_MIDDLE_DOWN, self.OnMiddleDown)
        self.Bind(wx.EVT_LEFT_DCLICK, self.OnDoubleClick)

#         if config.getboolean("main", "editor_useImeWorkaround", False):
#             self.Bind(wx.EVT_CHAR, self.OnChar_ImeWorkaround)

        self.Bind(wx.EVT_SET_FOCUS, self.OnSetFocus)

        self.Bind(wx.EVT_CONTEXT_MENU, self.OnContextMenu)

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

        # Check if modifiers where pressed since last extended logical line move
        # See self.moveSelectedLinesOneUp() for the reason of this
        self.modifiersPressedSinceExtLogLineMove = False

        self.contextMenuTokens = None
        self.contextMenuSpellCheckSuggestions = None

        # Connect context menu events to functions
        self.Bind(wx.EVT_MENU, lambda evt: self.Undo(), id=GUI_ID.CMD_UNDO)
        self.Bind(wx.EVT_MENU, lambda evt: self.Redo(), id=GUI_ID.CMD_REDO)

        self.Bind(wx.EVT_MENU, lambda evt: self.Cut(), id=GUI_ID.CMD_CLIPBOARD_CUT)
        self.Bind(wx.EVT_MENU, lambda evt: self.Copy(), id=GUI_ID.CMD_CLIPBOARD_COPY)
        self.Bind(wx.EVT_MENU, lambda evt: self.Paste(), id=GUI_ID.CMD_CLIPBOARD_PASTE)
        self.Bind(wx.EVT_MENU, lambda evt: self.pasteRawHtml(), id=GUI_ID.CMD_CLIPBOARD_PASTE_RAW_HTML)
        self.Bind(wx.EVT_MENU, lambda evt: self.SelectAll(), id=GUI_ID.CMD_SELECT_ALL)

        self.Bind(wx.EVT_MENU, lambda evt: self.ReplaceSelection(""), id=GUI_ID.CMD_TEXT_DELETE)
        self.Bind(wx.EVT_MENU, lambda evt: self.CmdKeyExecute(wx.stc.STC_CMD_ZOOMIN), id=GUI_ID.CMD_ZOOM_IN)
        self.Bind(wx.EVT_MENU, lambda evt: self.CmdKeyExecute(wx.stc.STC_CMD_ZOOMOUT), id=GUI_ID.CMD_ZOOM_OUT)


        for sps in self.SUGGESTION_CMD_IDS:
            self.Bind(wx.EVT_MENU, self.OnReplaceThisSpellingWithSuggestion, id=sps)

        self.Bind(wx.EVT_MENU, self.OnAddThisSpellingToIgnoreSession, id=GUI_ID.CMD_ADD_THIS_SPELLING_SESSION)
        self.Bind(wx.EVT_MENU, self.OnAddThisSpellingToIgnoreGlobal, id=GUI_ID.CMD_ADD_THIS_SPELLING_GLOBAL)
        self.Bind(wx.EVT_MENU, self.OnAddThisSpellingToIgnoreLocal, id=GUI_ID.CMD_ADD_THIS_SPELLING_LOCAL)

        self.Bind(wx.EVT_MENU, self.OnLogicalLineMove, id=GUI_ID.CMD_LOGICAL_LINE_UP)
        self.Bind(wx.EVT_MENU, self.OnLogicalLineMove, id=GUI_ID.CMD_LOGICAL_LINE_UP_WITH_INDENT)
        self.Bind(wx.EVT_MENU, self.OnLogicalLineMove, id=GUI_ID.CMD_LOGICAL_LINE_DOWN)
        self.Bind(wx.EVT_MENU, self.OnLogicalLineMove, id=GUI_ID.CMD_LOGICAL_LINE_DOWN_WITH_INDENT)

        self.Bind(wx.EVT_MENU, self.OnActivateThis, id=GUI_ID.CMD_ACTIVATE_THIS)
        self.Bind(wx.EVT_MENU, self.OnActivateNewTabThis, id=GUI_ID.CMD_ACTIVATE_NEW_TAB_THIS)
        self.Bind(wx.EVT_MENU, self.OnActivateNewTabBackgroundThis, id=GUI_ID.CMD_ACTIVATE_NEW_TAB_BACKGROUND_THIS)
        self.Bind(wx.EVT_MENU, self.OnActivateNewWindowThis, id=GUI_ID.CMD_ACTIVATE_NEW_WINDOW_THIS)

        # Passing the evt here is not strictly necessary, but it may be
        # used in the future
        self.Bind(wx.EVT_MENU, lambda evt: self.OnActivateThis(evt, "left"),
                id=GUI_ID.CMD_ACTIVATE_THIS_LEFT)
        self.Bind(wx.EVT_MENU, lambda evt: self.OnActivateNewTabThis(evt, "left"),
                id=GUI_ID.CMD_ACTIVATE_NEW_TAB_THIS_LEFT)
        self.Bind(wx.EVT_MENU, lambda evt: self.OnActivateNewTabBackgroundThis(
                evt, "left"), id=GUI_ID.CMD_ACTIVATE_NEW_TAB_BACKGROUND_THIS_LEFT)

        self.Bind(wx.EVT_MENU, lambda evt: self.OnActivateThis(evt, "right"),
                id=GUI_ID.CMD_ACTIVATE_THIS_RIGHT)
        self.Bind(wx.EVT_MENU, lambda evt: self.OnActivateNewTabThis(evt, "right"),
                id=GUI_ID.CMD_ACTIVATE_NEW_TAB_THIS_RIGHT)
        self.Bind(wx.EVT_MENU, lambda evt: self.OnActivateNewTabBackgroundThis(
                evt, "right"), id=GUI_ID.CMD_ACTIVATE_NEW_TAB_BACKGROUND_THIS_RIGHT)

        self.Bind(wx.EVT_MENU, lambda evt: self.OnActivateThis(evt, "above"),
                id=GUI_ID.CMD_ACTIVATE_THIS_ABOVE)
        self.Bind(wx.EVT_MENU, lambda evt: self.OnActivateNewTabThis(evt, "above"),
                id=GUI_ID.CMD_ACTIVATE_NEW_TAB_THIS_ABOVE)
        self.Bind(wx.EVT_MENU, lambda evt: self.OnActivateNewTabBackgroundThis(
                evt, "above"), id=GUI_ID.CMD_ACTIVATE_NEW_TAB_BACKGROUND_THIS_ABOVE)

        self.Bind(wx.EVT_MENU, lambda evt: self.OnActivateThis(evt, "below"),
                id=GUI_ID.CMD_ACTIVATE_THIS_BELOW)
        self.Bind(wx.EVT_MENU, lambda evt: self.OnActivateNewTabThis(evt, "below"),
                id=GUI_ID.CMD_ACTIVATE_NEW_TAB_THIS_BELOW)
        self.Bind(wx.EVT_MENU, lambda evt: self.OnActivateNewTabBackgroundThis(
                evt, "below"), id=GUI_ID.CMD_ACTIVATE_NEW_TAB_BACKGROUND_THIS_BELOW)

        self.Bind(wx.EVT_MENU, lambda evt: self.OnActivateThis(evt, "above"), 
                id=GUI_ID.CMD_ACTIVATE_THIS_ABOVE)
        self.Bind(wx.EVT_MENU, lambda evt: self.OnActivateNewTabThis(evt, "above"), 
                id=GUI_ID.CMD_ACTIVATE_NEW_TAB_THIS_ABOVE)
        self.Bind(wx.EVT_MENU, lambda evt: self.OnActivateNewTabBackgroundThis(evt, "above"), 
                id=GUI_ID.CMD_ACTIVATE_NEW_TAB_BACKGROUND_THIS_ABOVE)

        self.Bind(wx.EVT_MENU, lambda evt: self.OnActivateThis(evt, "below"), 
                id=GUI_ID.CMD_ACTIVATE_THIS_BELOW)
        self.Bind(wx.EVT_MENU, lambda evt: self.OnActivateNewTabThis(evt, "below"), 
                id=GUI_ID.CMD_ACTIVATE_NEW_TAB_THIS_BELOW)
        self.Bind(wx.EVT_MENU, lambda evt: self.OnActivateNewTabBackgroundThis(evt, "below"), 
                id=GUI_ID.CMD_ACTIVATE_NEW_TAB_BACKGROUND_THIS_BELOW)


        self.Bind(wx.EVT_MENU, self.OnConvertUrlAbsoluteRelativeThis, 
                id=GUI_ID.CMD_CONVERT_URL_ABSOLUTE_RELATIVE_THIS)

        self.Bind(wx.EVT_MENU, self.OnOpenContainingFolderThis, 
                id=GUI_ID.CMD_OPEN_CONTAINING_FOLDER_THIS)

        self.Bind(wx.EVT_MENU, self.OnDeleteFile, id=GUI_ID.CMD_DELETE_FILE)

        self.Bind(wx.EVT_MENU, self.OnRenameFile, id=GUI_ID.CMD_RENAME_FILE)

        self.Bind(wx.EVT_MENU, self.OnClipboardCopyUrlToThisAnchor,
                id=GUI_ID.CMD_CLIPBOARD_COPY_URL_TO_THIS_ANCHOR)

        self.Bind(wx.EVT_MENU, self.OnSelectTemplate, id=GUI_ID.CMD_SELECT_TEMPLATE)

    # 2.8 does not support SetEditable - Define a dummy function for now
    if wx.version().startswith("2.8"):
        def SetEditable(self, state):
            pass

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
#         self.Bind(wx.EVT_IDLE, self.OnIdle)


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


    _PASTETYPE_TO_HR_NAME_MAP = {
            "files": N_("File(s)"),
            "bitmap": N_("Bitmap image"),
            "wmf": N_("Windows meta file"),
            "plainText": N_("Plain text"),
            "rawHtml": N_("HTML"),
            }


    @classmethod
    def getHrNameForPasteType(cls, pasteType):
        """
        Return the human readable name of a paste type.
        """
        return _(cls._PASTETYPE_TO_HR_NAME_MAP.get(pasteType, pasteType))


    def pasteFiles(self, testOnly=False):
        """
        Try to get file(name)s from clipboard and paste it at current
        cursor position as links.
        
        testOnly -- Don't paste, only check if clipboard provides appropriate data
        
        Returns True iff successful.
        """
        
        filenames = wxHelper.getFilesFromClipboard()
        if filenames is None:
            return False
            
        if testOnly:
            return True

        mc = self.presenter.getMainControl()

        paramDict = {"editor": self, "filenames": filenames,
                "x": -1, "y": -1, "main control": mc,
                "processDirectly": True}

        mc.getUserActionCoord().reactOnUserEvent(
                "event/paste/editor/files", paramDict)

        return True


    def pasteBitmap(self, testOnly=False):
        """
        Try to get image from clipboard and paste it at current
        cursor position as link.
        
        testOnly -- Don't paste, only check if clipboard provides appropriate data
        
        Returns True iff successful.
        """

        imgsav = WikiTxtDialogs.ImagePasteSaver()
        imgsav.readOptionsFromConfig(self.presenter.getConfig())

        # Bitmap pasted?
        bmp = wxHelper.getBitmapFromClipboard()
        if bmp is None:
            return False
        
        if testOnly:
            return True
            
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

        fs = self.presenter.getWikiDocument().getFileStorage()
        destPath = imgsav.saveFile(fs, img)
        if destPath is None:
            # Couldn't find unused filename or saving denied
            # TODO: Error message!
            return True

        url = self.presenter.getWikiDocument().makeAbsPathRelUrl(destPath)

        if url is None:
            url = "file:" + StringOps.urlFromPathname(destPath)

        self.ReplaceSelection(url)
        return True
        
    


    def pasteWmf(self, testOnly=False):
        """
        Try to get Windows meta file from clipboard and paste it at current
        cursor position as link.
        On non-Windows OSs it always returns False.
        
        testOnly -- Don't paste, only check if clipboard provides appropriate data
        
        Returns True iff successful.
        """

        if not WindowsHacks:
            return False
            
        if testOnly:
            return WikiTxtDialogs.ImagePasteSaver.isWmfAvailableOnClipboard()

        imgsav = WikiTxtDialogs.ImagePasteSaver()
        imgsav.readOptionsFromConfig(self.presenter.getConfig())

        fs = self.presenter.getWikiDocument().getFileStorage()

        # Windows Meta File pasted?
        destPath = imgsav.saveWmfFromClipboardToFileStorage(fs)
        if destPath is None:
            return False
            
        url = self.presenter.getWikiDocument().makeAbsPathRelUrl(destPath)

        if url is None:
            url = "file:" + StringOps.urlFromPathname(destPath)

        self.ReplaceSelection(url)
        return True


    def pastePlainText(self, testOnly=False):
        """
        Try to get text from clipboard and paste it at current
        cursor position.
        
        testOnly -- Don't paste, only check if clipboard provides appropriate data
        
        Returns True iff successful.
        """
    
        text = getTextFromClipboard()
        if not text:
            return False
        
        if testOnly:
            return True
            
        self.ReplaceSelection(text)
        return True



    def pasteRawHtml(self, testOnly=False):
        """
        Try to retrieve HTML text from clipboard and paste it at current
        cursor position.

        testOnly -- Don't paste, only check if clipboard provides appropriate data
        
        Returns True iff successful.
        """
        rawHtml, url = wxHelper.getHtmlFromClipboard()

        if not rawHtml:
            return False
            
        if testOnly:
            return True
            
        return self.wikiLanguageHelper.handlePasteRawHtml(self, rawHtml, {})



    def Paste(self):
        PASTETYPE_TO_FUNCTION = {
            "files": self.pasteFiles,
            "bitmap": self.pasteBitmap,
            "wmf": self.pasteWmf,
            "plainText": self.pastePlainText,
            "rawHtml": self.pasteRawHtml,
            }

        config = self.presenter.getConfig()

        # Retrieve default and configured paste order
        defPasteOrder = config.getDefault("main", "editor_paste_typeOrder").split(";")
        pasteOrder = config.get("main", "editor_paste_typeOrder", "").split(";")

        # Use default paste order to constrain which items are allowed and
        # necessary in configured paste order
        pasteOrder = seqEnforceContained(pasteOrder, defPasteOrder)

        pasteFctOrder = [PASTETYPE_TO_FUNCTION[pasteType] for pasteType in pasteOrder]

        for fct in pasteFctOrder:
            if fct():
                return True

        return False


#     def Paste(self):
#         # File(name)s pasted?
#         filenames = wxHelper.getFilesFromClipboard()
#         if filenames is not None:
#             mc = self.presenter.getMainControl()
# 
#             paramDict = {"editor": self, "filenames": filenames,
#                     "x": -1, "y": -1, "main control": mc,
#                     "processDirectly": True}
# 
# #             mc.getUserActionCoord().runAction(
# #                     u"action/editor/this/paste/files/insert/url/ask", paramDict)
# 
#             mc.getUserActionCoord().reactOnUserEvent(
#                     u"event/paste/editor/files", paramDict)
# 
#             return True
# 
#         fs = self.presenter.getWikiDocument().getFileStorage()
#         imgsav = WikiTxtDialogs.ImagePasteSaver()
#         imgsav.readOptionsFromConfig(self.presenter.getConfig())
# 
#         # Bitmap pasted?
#         bmp = wxHelper.getBitmapFromClipboard()
#         if bmp is not None:
#             img = bmp.ConvertToImage()
#             del bmp
# 
#             if self.presenter.getConfig().getboolean("main",
#                     "editor_imagePaste_askOnEachPaste", True):
#                 # Options say to present dialog on an image paste operation
#                 # Send image so it can be used for preview
#                 dlg = WikiTxtDialogs.ImagePasteDialog(
#                         self.presenter.getMainControl(), -1, imgsav, img)
#                 try:
#                     dlg.ShowModal()
#                     imgsav = dlg.getImagePasteSaver()
#                 finally:
#                     dlg.Destroy()
# 
#             destPath = imgsav.saveFile(fs, img)
#             if destPath is None:
#                 # Couldn't find unused filename or saving denied
#                 return True
# 
#             url = self.presenter.getWikiDocument().makeAbsPathRelUrl(destPath)
# 
#             if url is None:
#                 url = u"file:" + StringOps.urlFromPathname(destPath)
# 
#             self.ReplaceSelection(url)
#             return True
# 
#         if WindowsHacks:
# 
#             # Windows Meta File pasted?
#             destPath = imgsav.saveWmfFromClipboardToFileStorage(fs)
#             if destPath is not None:
#                 url = self.presenter.getWikiDocument().makeAbsPathRelUrl(destPath)
#     
#                 if url is None:
#                     url = u"file:" + StringOps.urlFromPathname(destPath)
#     
#                 self.ReplaceSelection(url)
#                 return True
# 
#         # Text pasted?
#         text = getTextFromClipboard()
#         if text:
#             self.ReplaceSelection(text)
#             return True
# 
# 
#         return False




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


    def isCharWrap(self):
        docPage = self.getLoadedDocPage()
        if docPage is not None:
            return docPage.getAttributeOrGlobal("wrap_type", "word").lower()\
                    .startswith("char")
        else:
            return False

    def setWrapMode(self, onOrOff, charWrap=None):
        if charWrap is None:
            charWrap = self.isCharWrap()

        if onOrOff:
            if charWrap:
                self.SetWrapMode(wx.stc.STC_WRAP_CHAR)
            else:
                self.SetWrapMode(wx.stc.STC_WRAP_WORD)
        else:
            self.SetWrapMode(wx.stc.STC_WRAP_NONE)

    def getWrapMode(self):
        return self.GetWrapMode() != wx.stc.STC_WRAP_NONE

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
        wx.stc.StyledTextCtrl.SetText(self, text)
        self.ignoreOnChange = False

        if emptyUndo:
            self.EmptyUndoBuffer()
        # self.applyBasicSciSettings()


    def replaceText(self, text):
        wx.stc.StyledTextCtrl.SetText(self, text)


    def replaceTextAreaByCharPos(self, newText, start, end):
        text = self.GetText()
        bs = self.bytelenSct(text[:start])
        be = bs + self.bytelenSct(text[start:end])
        self.SetTargetStart(bs)
        self.SetTargetEnd(be)

        self.ReplaceTarget(newText)

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
        self.SetCodePage(wx.stc.STC_CP_UTF8)
        self.SetTabIndents(True)
        self.SetBackSpaceUnIndents(True)
        self.SetUseTabs(not self.tabsToSpaces)
        self.SetEOLMode(wx.stc.STC_EOL_LF)

        tabWidth = self.presenter.getConfig().getint("main",
                "editor_tabWidth", 4)

        self.SetIndent(tabWidth)
        self.SetTabWidth(tabWidth)

        self.AutoCompSetFillUps(":=")  # TODO Add '.'?
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
        wikiDocument = self.presenter.getWikiDocument()

        self.presenter.setDocPage(funcPage)

        if self.getLoadedDocPage() is None:
            return  # TODO How to handle?

        globalAttrs = wikiDocument.getWikiData().getGlobalAttributes()
        # get the font that should be used in the editor
        font = globalAttrs.get("global.font", self.defaultFont)

        # set the styles in the editor to the font
        if self.lastFont != font:
            faces = self.presenter.getDefaultFontFaces().copy()
            faces["mono"] = font
            self.SetStyles(faces)
            self.lastEditorFont = font

        # this updates depending on attribute "wrap_type" (word or character)
        self.setWrapMode(self.getWrapMode())

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
            except WikiFileNotFoundException as e:
                assert 0   # TODO

            # now fill the text into the editor
            self.SetReadOnly(False)
            self.SetText(content)

        if self.wikiLanguageHelper is None or \
                self.wikiLanguageHelper.getWikiLanguageName() != \
                self.getLoadedDocPage().getWikiLanguageName():

            wx.GetApp().freeWikiLanguageHelper(self.wikiLanguageHelper)
            self.wikiLanguageHelper = self.getLoadedDocPage().createWikiLanguageHelper()

        self.getLoadedDocPage().addTxtEditor(self)
        self._checkForReadOnly()
        self.presenter.setTitle(self.getLoadedDocPage().getTitle())


    def loadWikiPage(self, wikiPage, evtprops=None):
        """
        Save loaded page, if necessary, then load wikiPage into editor
        """
        self.unloadCurrentDocPage(evtprops)
        # set the editor text
        wikiDocument = self.presenter.getWikiDocument()

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
            except WikiFileNotFoundException as e:
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

        # this updates depending on attribute "wrap_type" (word or character)
        self.setWrapMode(self.getWrapMode())

        self.pageType = docPage.getAttributes().get("pagetype",
                ["normal"])[-1]

        if self.pageType == "normal":
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

        if self.pageType == "form":
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
            if self.pageType == "normal":
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

        if self.pageType == "normal":
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

        for i in range(32):
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
        # this updates depending on attribute "wrap_type" (word or character)
        self.setWrapMode(self.getWrapMode())

        # To allow switching vi keys on and off without restart
        use_vi_navigation = self.presenter.getConfig().getboolean("main",
                "editor_compatibility_ViKeys", False)

        self.Unbind(wx.EVT_CHAR)
        self.Unbind(wx.EVT_KEY_DOWN)
        self.Unbind(wx.EVT_KEY_UP)
        self.Unbind(wx.EVT_LEFT_UP)
        #self.Unbind(wx.EVT_SCROLLWIN)
        self.Unbind(wx.EVT_MOUSEWHEEL)

        if use_vi_navigation:
            if self.vi is None:
                self.vi = ViHandler(self)


            if not isLinux():
                # Need to merge with OnChar_ImeWorkaround
                self.Bind(wx.EVT_CHAR, self.vi.OnChar)
            self.Bind(wx.EVT_KEY_DOWN, self.vi.OnViKeyDown)
            self.Bind(wx.EVT_LEFT_DOWN, self.vi.OnMouseClick)
            self.Bind(wx.EVT_LEFT_UP, self.vi.OnLeftMouseUp)
            # TODO: Replace with seperate scroll events
            #self.Bind(wx.EVT_SCROLLWIN, self.vi.OnScroll)

            if self.vi.settings["caret_scroll"]:
                self.Bind(wx.EVT_MOUSEWHEEL, self.vi.OnMouseScroll)

            # Should probably store shortcut state in a global
            # variable otherwise this will be run each time
            # a new tab is opened
            wx.CallAfter(self.vi._enableMenuShortcuts, False)

        else:
            if self.vi is not None:
                self.vi.TurnOff()
                self.vi = None

            if self.presenter.getConfig().getboolean("main",
                    "editor_useImeWorkaround", False):
                self.Bind(wx.EVT_CHAR, self.OnChar_ImeWorkaround)
            self.Bind(wx.EVT_KEY_DOWN, self.OnKeyDown)
            self.Bind(wx.EVT_KEY_UP, self.OnKeyUp)
            self.Bind(wx.EVT_LEFT_DOWN, self.OnClick)
            self.Bind(wx.EVT_MOUSEWHEEL, self.OnMouseWheel)
            if not isLinux():
                self.Bind(wx.EVT_CHAR, None)


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

        # this updates depending on attribute "wrap_type" (word or character)
        self.setWrapMode(self.getWrapMode())

        self.pageType = self.getLoadedDocPage().getAttributes().get("pagetype",
                ["normal"])[-1]


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

        templateRePat = config.get("main", "template_pageNamesRE",
                "^template/")

        try:
            templateRe = re.compile(templateRePat, re.DOTALL | re.UNICODE)
        except re.error:
            templateRe = re.compile("^template/", re.DOTALL | re.UNICODE)

        wikiDocument = self.presenter.getWikiDocument()
        templateNames = [n for n in wikiDocument.getAllDefinedWikiPageNames()
                if templateRe.search(n)]

        wikiDocument.getCollator().sort(templateNames)

        for tn in templateNames:
            menuID, reused = idRecycler.assocGetIdAndReused(tn)

            if not reused:
                # For a new id, an event must be set
                self.Bind(wx.EVT_MENU, self.OnTemplateUsed, id=menuID)

            menu.Append(menuID, tn)


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
        self.pageType = docPage.getAttributes().get("pagetype",
                ["normal"])[-1]
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
            title = _("Select Template")
        else:
            title = _("Select Template (deletes current content!)")

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
        self.pageType = docPage.getAttributes().get("pagetype",
                ["normal"])[-1]
        self.handleSpecialPageType()
        self.presenter.informEditorTextChanged(self)


    # TODO Wrong reaction on press of context menu button on keyboard
    def OnContextMenu(self, evt):
        mousePos = self.ScreenToClient(wx.GetMousePosition())

        leftFold = 0
        for i in range(self.FOLD_MARGIN):
            leftFold += self.GetMarginWidth(i)

        rightFold = leftFold + self.GetMarginWidth(self.FOLD_MARGIN)

        menu = wxHelper.EnhancedPlgSuppMenu(self)

        contextInfo = DictFromFields()
        contextInfo.mousePos = mousePos
        contextInfo.txtCtrl = self

        if mousePos.x >= leftFold and mousePos.x < rightFold:
            # Right click in fold margin
            contextName = "contextMenu/editor/foldMargin"
            appendToMenuByMenuDesc(menu, FOLD_MENU)
        else:
            contextName = "contextMenu/editor/textArea"
            nodes = self.getTokensForMousePos(mousePos)
            contextInfo.tokens = nodes

            self.contextMenuTokens = nodes
            addActivateItem = False
            addFileUrlItem = False
            addWikiUrlItem = False
            addUrlToClipboardItem = False
            unknownWord = None
            for node in nodes:
                if node.name == "wikiWord":
                    addActivateItem = True
                    contextInfo.inWikiWord = True
                elif node.name == "urlLink":
                    addActivateItem = True
                    if node.url.startswith("file:") or \
                            node.url.startswith("rel://"):
                        addFileUrlItem = True
                        contextInfo.inFileUrl = True
                    elif node.url.startswith("wiki:") or \
                            node.url.startswith("wikirel://"):
                        addWikiUrlItem = True
                        contextInfo.inWikiUrl = True
                elif node.name == "insertion" and node.key == "page":
                    addActivateItem = True
                    contextInfo.inPageInsertion = True
                elif node.name == "anchorDef":
                    addUrlToClipboardItem = True
                    contextInfo.inAnchorDef = True
                elif node.name == "unknownSpelling":
                    unknownWord = node.getText()
                    contextInfo.inUnknownSpelling = True

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

                            menu.Append(menuitem)

                        self.contextMenuSpellCheckSuggestions = suggestions
                    # Show other spelling menu items
                    appendToMenuByMenuDesc(menu, _CONTEXT_MENU_INTEXT_SPELLING)


            appendToMenuByMenuDesc(menu, _CONTEXT_MENU_INTEXT_BASE)

            if addActivateItem:
                appendToMenuByMenuDesc(menu, _CONTEXT_MENU_INTEXT_ACTIVATE)

                # Check if their are any surrounding viewports that we can use
                # TODO: we should be able to use (create) unused viewports
                viewports = self.presenter.getMainControl().\
                        getMainAreaPanel().getPossibleTabCtrlDirections(
                                self.presenter)
                for direction in viewports:
                    if viewports[direction] is not None:
                        appendToMenuByMenuDesc(menu,
                                    _CONTEXT_MENU_INTEXT_ACTIVATE_DIRECTION[
                                            direction])


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
                    menu.AppendSubMenu(templateSubmenu, _('Use Template'))
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

        contextInfo = contextInfo.getDict()

        menu.setContext(contextName, contextInfo)
        wx.GetApp().getModifyMenuDispatcher().dispatch(contextName,
                contextInfo, menu)
        # Dwell lock to avoid image popup while context menu is shown
        with self.dwellLock():
            # Show menu
            self.PopupMenu(menu)
            menu.close()

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
                threadstop.testValidThread()

            docPage = self.getLoadedDocPage()
            if docPage is None:
                return

            for i in range(20):   # "while True" is too dangerous
                formatDetails = docPage.getFormatDetails()
                pageAst = docPage.getLivePageAst(threadstop=threadstop)
                threadstop.testValidThread()
                if not formatDetails.isEquivTo(docPage.getFormatDetails()):
                    continue
                else:
                    break

            stylebytes = self.processTokens(text, pageAst, threadstop)

            threadstop.testValidThread()

            if self.getFoldingActive():
                foldingseq = self.processFolding(pageAst, threadstop)
            else:
                foldingseq = None

            threadstop.testValidThread()

            if self.onlineSpellCheckerActive and \
                    isinstance(docPage, DocPages.AbstractWikiPage):

                # Show intermediate syntax highlighting results before spell check
                # if we are in asynchronous mode
                if not threadstop is DUMBTHREADSTOP:
                    self.storeStylingAndAst(stylebytes, foldingseq, styleMask=0x1f)

                scTokens = docPage.getSpellCheckerUnknownWords(threadstop=threadstop)

                threadstop.testValidThread()

                if scTokens.getChildrenCount() > 0:
                    spellStyleBytes = self.processSpellCheckTokens(text, scTokens,
                            threadstop)

                    threadstop.testValidThread()

                    # TODO: Faster? How?
                    stylebytes = "".join([chr(a | b)
                            for a, b in zip(stylebytes, spellStyleBytes)]
                            ).encode("raw_unicode_escape")

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
        
        # Python 2.6, None and int were comparable, in Py 3.4 no more
        if found[0] is None:
            return found

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
                threadstop.testValidThread()

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

                elif node.name in \
                        self.wikiLanguageHelper.getRecursiveStylingNodeNames() or \
                        (getattr(node, "helperRecursive", False) and \
                        not node.isTerminal()):
                    process(node, stack[:])

        process(pageAst, [])
        return stylebytes.value()


    def processSpellCheckTokens(self, text, scTokens, threadstop):
        stylebytes = StyleCollector(0, text, self.bytelenSct)
        for node in scTokens:
            threadstop.testValidThread()
            stylebytes.bindStyle(node.pos, node.strLength,
                    wx.stc.STC_INDIC2_MASK)

        return stylebytes.value()


    def getFoldingNodeDict(self):
        """
        Retrieve the folding node dictionary from wiki language which tells
        which AST nodes (other than "heading") should be processed by
        folding.
        The folding node dictionary has the names of the AST node types as keys,
        each value is a tuple (fold, recursive) where
        fold -- True iff node should be folded
        recursive -- True iff node should be processed recursively

        The value tuples may contain more than these two items, processFolding()
        must be able to handle that.
        """
        # TODO: Add option to remove additional nodes from folding
        #   (or some of them)

        return self.wikiLanguageHelper.getFoldingNodeDict()


    def processFolding(self, pageAst, threadstop):
        # TODO: allow folding of tables / boxes / figures
        foldingseq = []
        #currLine = 0
        prevLevel = 0
        levelStack = []
        foldHeader = False

        foldNodeDict = self.getFoldingNodeDict()

        def searchAst(ast, foldingseq, prevLevel, levelStack, foldHeader):

            for node in ast:

                threadstop.testValidThread()

                recursive = False

                if node.name is None:
                    pass
                elif node.name == "heading":
                    while levelStack and (levelStack[-1][0] != "heading" or
                            levelStack[-1][1] > node.level) and \
                            levelStack[-1][0] != "recursive-node":
                        del levelStack[-1]
                    if not levelStack or \
                            levelStack[-1] != ("heading", node.level):
                        levelStack.append(("heading", node.level))
                    foldHeader = True
                elif node.name in foldNodeDict:
                    fndMode = foldNodeDict[node.name][:2]

                    if fndMode == (True, False):  # Fold, non recursive
                        # No point in folding single line items
                        if node.getString().count("\n") > 1:
                            levelStack.append(("node", 0))
                            foldHeader = True

                    elif fndMode == (True, True):  # Fold, recursive
                        levelStack.append(("recursive-node", 0))
                        foldHeader = True
                        foldingseq, prevLevel, levelStack, foldHeader = \
                                searchAst(node, foldingseq, prevLevel, levelStack,
                                foldHeader)
                        while levelStack[-1][0] == "heading":
                            del levelStack[-1]

                        del levelStack[-1]

                        recursive = True

                    elif fndMode == (False, True):  # No fold, but recursive
                        foldingseq, prevLevel, levelStack, foldHeader = \
                                searchAst(node, foldingseq, prevLevel, levelStack,
                                foldHeader)
                        recursive = True

                if not recursive:
                    lfc = node.getString().count("\n")

                    if len(levelStack) > prevLevel:
                        foldHeader = True

                    if foldHeader and lfc > 0:
                        foldingseq.append(len(levelStack) | wx.stc.STC_FOLDLEVELHEADERFLAG)
                        foldHeader = False
                        lfc -= 1

                    if lfc > 0:
                        foldingseq += [len(levelStack) + 1] * lfc

                    if levelStack and levelStack[-1][0] == "node":
                        del levelStack[-1]

                    prevLevel = len(levelStack) + 1


            return foldingseq, prevLevel, levelStack, foldHeader

        foldingseq, prevLevel, levelStack, foldHeader = searchAst(pageAst,
                foldingseq, prevLevel, levelStack, foldHeader)

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
            for ln in range(len(foldingseq)):
                self.SetFoldLevel(ln, foldingseq[ln])
            self.repairFoldingVisibility()


    def unfoldAll(self):
        """
        Unfold all folded lines
        """
        for i in range(self.GetLineCount()):
            self.SetFoldExpanded(i, True)

        self.ShowLines(0, self.GetLineCount()-1)


    def foldAll(self):
        """
        Fold all foldable lines
        """
        if not self.getFoldingActive():
            self.setFoldingActive(True, forceSync=True)

        for ln in range(self.GetLineCount()):
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
        for ln in range(self.GetLineCount()):
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

        for ln in range(1, lc):
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


    def formatSelection(self, formatType):
        start, afterEnd = self.GetSelectionCharPos()
        info = self.wikiLanguageHelper.formatSelectedText(self.GetText(),
                start, afterEnd, formatType, {})
        if info is None:
            return False

        replacement, repStart, repAfterEnd, selStart, selAfterEnd = info[:5]

        self.SetSelectionByCharPos(repStart, repAfterEnd)
        self.ReplaceSelection(replacement)
        self.SetSelectionByCharPos(selStart, selAfterEnd)
        return True


    def getPageAst(self):
        docPage = self.getLoadedDocPage()
        if docPage is None:
            raise NoPageAstException("Internal error: No docPage => no page AST")

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
                if node.key == "page":

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


    def findSimilarWords(self, mousePosition=None):
        """
        Finds similar words to an undefined link

        TODO: make an activateLink option?
        """
        nodeList = self.getTokensForMousePos(mousePosition)

        if len(nodeList) == 0:
            return False

        for node in nodeList:
            if node.name == "wikiWord":

                if self.presenter.getWikiDocument().isDefinedWikiLinkTerm(
                        node.wikiWord):
                    return False

                dlg = AdditionalDialogs.FindSimilarNamedWikiWordDialog(
                        self.presenter, -1, node.wikiWord, 0)
                dlg.CenterOnParent(wx.BOTH)
                dlg.ShowModal()
                dlg.Destroy()
                return
               




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


    def GetEditorToActivate(self, direction, makePresenterCurrent=False):
        """
        Helper for OnActive* functions.

        Returns the editor to activate the link on (based on the direction
        parameter)
        """
        if direction is not None:
            presenter = self.presenter.getMainControl().getMainAreaPanel().\
                            getActivePresenterTo(direction, self.presenter)
            ed = presenter.getSubControl("textedit")

            if makePresenterCurrent:
                presenter.makeCurrent()
        else:
            ed = self


        return ed

    def OnActivateThis(self, evt, direction=None):
        ed = self.GetEditorToActivate(direction, True)

        if self.contextMenuTokens:
            ed.activateTokens(self.contextMenuTokens, 0)

    def OnActivateNewTabThis(self, evt, direction=None):
        ed = self.GetEditorToActivate(direction, True)

        if self.contextMenuTokens:
            ed.activateTokens(self.contextMenuTokens, 2)

    def OnActivateNewTabBackgroundThis(self, evt, direction=None):
        # If we are opening a background tab assume we want the current
        # tabCtrl to remain active
        presenter = self.presenter
        ed = self.GetEditorToActivate(direction, True)

        if self.contextMenuTokens:
            ed.activateTokens(self.contextMenuTokens, 3)

        wx.CallAfter(presenter.makeCurrent)

    def OnActivateNewWindowThis(self, evt, direction=None):
        ed = self.GetEditorToActivate(direction, True)

        if self.contextMenuTokens:
            ed.activateTokens(self.contextMenuTokens, 6)

    def OnFindSimilarWikiWords(self, evt, direction=None):
        self.findSimilarWords()

    def OnOpenContainingFolderThis(self, evt):
        if self.contextMenuTokens:
            for node in self.contextMenuTokens:
                if node.name == "urlLink":
                    link = node.url

                    if link.startswith("rel://") or link.startswith("wikirel://"):
                        link = self.presenter.getWikiDocument()\
                                .makeRelUrlAbsolute(link)

                    if link.startswith("file:") or link.startswith("wiki:"):
                        # TODO: fix
                        try:
                            path = dirname(StringOps.pathnameFromUrl(link))
                            if not exists(StringOps.longPathEnc(path)):
                                self.presenter.displayErrorMessage(
                                        _("Folder does not exist"))
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
                                _("File does not exist"))
                        return

                    filename = basename(link)

                    choice = wx.MessageBox(
                            _("Are you sure you want to delete the file: %s") %
                            filename, _("Delete File"),
                            wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION, self)

                    if choice == wx.YES:
                        OsAbstract.deleteFile(link)
                        self.replaceTextAreaByCharPos("", node.pos,
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
            self.presenter.displayErrorMessage(_("File does not exist"))
            return

        path = dirname(link)
        filename = basename(link)

        newName = filename
        while True:
            dlg = WikiTxtDialogs.RenameFileDialog(self,
                    _("Enter new name for file: {0}").format(filename),
                    _("Rename File"), newName)

            if dlg.ShowModal() != wx.ID_OK:
                # User cancelled
                dlg.Destroy()
                return

            newName = dlg.GetValue()
            dlg.Destroy()

            newfile = join(path, newName)

            if exists(newfile):
                if not isfile(newfile):
                    self.presenter.displayErrorMessage(
                            _("Target is not a file"))
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

            if node.url.startswith("rel://"):
                # Relative URL/path
                newUrl = self.presenter.getWikiDocument().makeAbsPathRelUrl(
                        newfile)
            else:
                # Absolute URL/path
                newUrl = "file:" + StringOps.urlFromPathname(newfile)

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

                if link.startswith("rel://") or link.startswith("wikirel://"):
                    link = self.presenter.getWikiDocument()\
                            .makeRelUrlAbsolute(link, addSafe=addSafe)

                else:
                    link = self.presenter.getWikiDocument()\
                            .makeAbsUrlRelative(link, addSafe=addSafe)
                    if link is None:
                        continue # TODO Message?

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
                    _("This can only be done for the page of a wiki word"),
                    _('Not a wiki page'), wx.OK, self)
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
            wx.MessageBox(_("Set in menu \"Wiki\", item \"Options...\", "
                    "options page \"Security\", \n"
                    "item \"Script security\" an appropriate value "
                    "to execute a script."), _("Script execution disabled"),
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
                if "import_scripts" in self.getLoadedDocPage().getAttributes():
                    scriptNames = self.getLoadedDocPage().getAttributes()[
                            "import_scripts"]
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
                        getGlobalAttributes().get("global.import_scripts")

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
                script = re.sub(r"^[\r\n\s]+", "", script)
                script = re.sub(r"[\r\n\s]+$", "", script)
                try:
                    if index == -1:
                        script = re.sub(r"^\d:?\s?", "", script)
                        exec((script), self.evalScope)
                    elif index > -1 and script.startswith(str(index)):
                        script = re.sub(r"^\d:?\s?", "", script)
                        exec((script), self.evalScope)
                        break # Execute only the first found script

                except Exception as e:
                    s = StringIO()
                    traceback.print_exc(file=s)
                    self.AddText(_("\nException: %s") % s.getvalue())
        else:
            # Evaluate selected text
            text = self.GetSelectedText()
            try:
                compThunk = compile(re.sub(r"[\n\r]", "", text), "<string>",
                        "eval", CO_FUTURE_DIVISION)
                result = eval(compThunk, self.evalScope)
            except Exception as e:
                s = StringIO()
                traceback.print_exc(file=s)
                result = s.getvalue()

            pos = self.GetCurrentPos()
            self.GotoPos(endPos)
            self.AddText(" = %s" % str(result))
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
            result = str(eval(match.group(2), self.evalScope))
        except Exception as e:
            s = StringIO()
            traceback.print_exc(file=s)
            result = str(s.getvalue())

        if len(result) == 0 or result[-1] != "\n":
            result += "\n"

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
    AGACONTENTTABLERE = re.compile(r"^(\+{1,4})([^\n\+][^\n]*)", re.DOTALL | re.MULTILINE)

    def agaContentTable(self, omitfirst = False):
        """
        Can be called by an aga to present the content table of the current page.
        The text is assumed to be in self.agatext variable(see updateAutoGenAreas()).
        If omitfirst is true, the first entry (normally the title) is not shown.
        """
        allmatches = [m.group(0) for m in self.AGACONTENTTABLERE.finditer(self.agatext)]
        if omitfirst and len(allmatches) > 0:
            allmatches = allmatches[1:]

        return "\n".join(allmatches)


        # TODO Multi column support
    def agaFormatList(self, l):
        """
        Format a list l of strings in a nice way for an aga content
        """
        return "\n".join(l)


    def agaParentsTable(self):
        """
        Can be called by an aga to present all parents of the current page.
        """
        relations = self.getLoadedDocPage().getParentRelationships()[:]

        # Apply sort order
        relations.sort(key=lambda s: s.lower()) # sort alphabetically

        return self.agaFormatList(relations)


    def ensureTextRangeByBytePosExpanded(self, byteStart, byteEnd):
        self.repairFoldingVisibility()

        startLine = self.LineFromPosition(byteStart)
        endLine = self.LineFromPosition(byteEnd)

        # Just to be sure, shouldn't happen normally
        if endLine < startLine:
            startLine, endLine = endLine, startLine

        for checkLine in range(endLine, startLine - 1, -1):
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
        for i in range(startLine, endLine + 1):
            shownList.append(self.GetLineVisible(i))

        self.incSearchPreviousHiddenLines = shownList
        self.incSearchPreviousHiddenStartLine = startLine

        # Show lines
        self.ShowLines(startLine, endLine)
        self.SetSelection(byteStart, byteEnd)
        self.EnsureCaretVisible()



    def startIncrementalSearch(self, initSearch=None):
        self.incSearchPreviousHiddenLines = None
        self.incSearchPreviousHiddenStartLine = -1

        super(WikiTxtCtrl, self).startIncrementalSearch(initSearch)


    def endIncrementalSearch(self):
        super(WikiTxtCtrl, self).endIncrementalSearch()

        self.ensureSelectionExpanded()


    def rewrapText(self):
        wrapType = "word" if self.GetWrapMode() != wx.stc.STC_WRAP_CHAR else "char"
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

            self.UserListShow(1, "\x01".join(
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
        firstLine = self.LineFromPosition(selByteStart)
        lastLine = self.LineFromPosition(selByteEnd)
        selByteStart = self.PositionFromLine(self.LineFromPosition(selByteStart))
        selByteEnd = self.PositionFromLine(lastLine + 1)

        if extendOverChildren:
            # Extend over all lines which are more indented than the first line

            firstLineDeep = StringOps.splitIndentDeepness(self.GetLine(firstLine))[0]

            testLine = lastLine + 1
            while True:
                testLineContent = self.GetLine(testLine)
                if len(testLineContent) == 0:
                    # End of text reached
                    break

                if StringOps.splitIndentDeepness(testLineContent)[0] <= firstLineDeep:
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
            below the initial selection. It should only be set True for first move
            in a sequence of moves (until all modifier keys are released) otherwise:

            If you have e.g.
            A
                B
            C
                D

            and move up C with children two times then B would be moved above A
            as well which is not intended
        """

        self.BeginUndoAction()
        try:
            selByteStart, selByteEnd = self._getExpandedByteSelectionToLine(
                    extendOverChildren)

            firstLine = self.LineFromPosition(selByteStart)
            if firstLine > 0:
                content = self.GetSelectedText()
                if len(content) > 0:
                    if content[-1] == "\n":
                        selByteEnd -= 1
                    else:
                        content += "\n"
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

                    if content[-1] == "\n":  # Necessary for downward move?
                        selByteEnd -= 1
                    else:
                        content += "\n"

                    self.ReplaceSelection("")
                    if self.GetTextRange(target - 1,
                            target) != "\n":
                        self.InsertText(target, "\n")
                        target += 1

                    self.InsertText(target, content)
                    self.SetSelectionMode(0)
                    self.SetSelectionStart(target)
                    self.SetSelectionMode(0)
                    self.SetSelectionEnd(target + (selByteEnd - selByteStart))
        finally:
            self.EndUndoAction()



    def OnKeyUp(self, evt):
        evt.Skip()

        if not self.modifiersPressedSinceExtLogLineMove:
            return

        if wxHelper.isAllModKeysReleased(evt):
            self.modifiersPressedSinceExtLogLineMove = False


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

#         elif matchesAccelPair("LogLineUp", accP):
#             # LogLineUp is by default undefined
#             self.moveSelectedLinesOneUp(False)
#         elif matchesAccelPair("LogLineUpWithIndented", accP):
#             # LogLineUp is by default undefined
#             self.moveSelectedLinesOneUp(
#                     not self.modifiersPressedSinceExtLogLineMove)
#             self.modifiersPressedSinceExtLogLineMove = True
#         elif matchesAccelPair("LogLineDown", accP):
#             # LogLineUp is by default undefined
#             self.moveSelectedLinesOneDown(False)
#         elif matchesAccelPair("LogLineDownWithIndented", accP):
#             # LogLineUp is by default undefined
#             self.moveSelectedLinesOneDown(
#                     not self.modifiersPressedSinceExtLogLineMove)
#             self.modifiersPressedSinceExtLogLineMove = True

        elif not evt.ControlDown() and not evt.ShiftDown():  # TODO Check all modifiers
            if key == wx.WXK_TAB:
                if self.pageType == "form":
                    if not self._goToNextFormField():
                        self.presenter.getMainControl().showStatusMessage(
                                _("No more fields in this 'form' page"), -1)
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
                super(WikiTxtCtrl, self).OnKeyDown(evt)

        else:
            super(WikiTxtCtrl, self).OnKeyDown(evt)

            # CallAfter is used as otherwise we seem to lose a mouseup
            # evt. TODO: check what happens on windows
            wx.CallAfter(self.presenter.makeCurrent)


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

        if key >= wx.WXK_START and evt.GetUnicodeKey() != key:
            evt.Skip()
            return

        self.ReplaceSelection(chr(evt.GetUnicodeKey()))


    def OnMouseWheel(self, evt):
        # Scintilla's wheel zoom behavior is unusual (upward=zoom out)
        # So the sign of rotation value must be changed if wheel zoom is NOT
        # reversed by option

        global disableMouseWheelSetting

        if disableMouseWheelSetting:
            # Previously an error occurred.
            evt.Skip()
            return

        if evt.ControlDown() and not self.presenter.getConfig().getboolean(
                "main", "mouse_reverseWheelZoom", False):
            try:                                            # HACK changed here !
                evt.WheelRotation = -evt.WheelRotation
            except AttributeError:
                import ExceptionLogger
                ExceptionLogger.logOptionalComponentException(
                        "Error when setting mouse wheel rotation (WheelRotation). "
                        "You need wxPython version > 4.0.4")
                disableMouseWheelSetting = True

        evt.Skip()


    def OnLogicalLineMove(self, evt):
        evtId = evt.GetId()

        if evtId == GUI_ID.CMD_LOGICAL_LINE_UP:
            self.moveSelectedLinesOneUp(False)
        elif evtId == GUI_ID.CMD_LOGICAL_LINE_UP_WITH_INDENT:
            self.moveSelectedLinesOneUp(
                    not self.modifiersPressedSinceExtLogLineMove)
            self.modifiersPressedSinceExtLogLineMove = \
                    not wxHelper.isAllModKeysReleased(None)
        elif evtId == GUI_ID.CMD_LOGICAL_LINE_DOWN:
            self.moveSelectedLinesOneDown(False)
        elif evtId == GUI_ID.CMD_LOGICAL_LINE_DOWN_WITH_INDENT:
            self.moveSelectedLinesOneDown(
                    not self.modifiersPressedSinceExtLogLineMove)
            self.modifiersPressedSinceExtLogLineMove = \
                    not wxHelper.isAllModKeysReleased(None)


    if isLinux():
        def OnSetFocus(self, evt):
            #self.presenter.makeCurrent()

            # We need to make sure makeCurrent uses CallAfter overwise we
            # get a selection bug if the mouse is moved quickly after
            # clicking on the TxtCtrl (not sure if this is required for
            # windows)
            wx.CallAfter(self.presenter.makeCurrent)
            evt.Skip()

            wikiPage = self.getLoadedDocPage()
            if wikiPage is None:
                return
            if not isinstance(wikiPage,
                    (DocPages.DataCarryingPage, DocPages.AliasWikiPage)):
                return

            try:
                wikiPage.checkFileSignatureAndMarkDirty()
            except (IOError, OSError, DbAccessError) as e:
                self.presenter.getMainControl().lostAccess(e)

            evt.Skip()

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
            except (IOError, OSError, DbAccessError) as e:
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
        if (self.IsEnabled() and (wx.Window.FindFocus() is self)):
            if self.presenter.isCurrent():
                # fix the line, pos and col numbers
                currentLine = self.GetCurrentLine()+1
                currentPos = self.GetCurrentPos()
                currentCol = self.GetColumn(currentPos)
                self.presenter.SetStatusText(_("Line: %d Col: %d Pos: %d") %
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



    def _threadShowCalltip(self, wikiDocument, charPos, bytePos, mouseCoords,
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
                    threadstop.testValidThread()
                    wikiWord = wikiDocument.getWikiPageNameForLinkTerm(
                            astNode.wikiWord)

                    # Set status to wikipage
                    callInMainThread(
                            self.presenter.getMainControl().showStatusMessage,
                            _("Link to page: %s") % wikiWord, 0, "linkToPage")

                    if wikiWord is not None:
                        propList = wikiDocument.getAttributeTriples(
                                wikiWord, "short_hint", None)
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
                    if "l" in appendixDict:
                        urlAsImage = False
                    elif "i" in appendixDict:
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
                                threadstop.testValidThread()
                                callInMainThread(SetImageTooltip, path)
                            else:
                                callTip = _("Not a valid image")
                            break
                        else:
                            callTip = _("Image does not exist")

            if callTip:
                threadstop.testValidThread()

                # Position and format CallTip

                # try and display CallTip without reformating
                callTipLen = max([len(i) for i in callTip.split("\n")])
                colPos = self.GetColumn(bytePos)
                mouseX, mouseY = mouseCoords
                callTipWidth = self.TextWidth(0, callTip)
                x, y = self.GetClientSize()

                # first see if we can just reposition the calltip
                if x <= callTipWidth + mouseX:
                    # if this fails wrap the calltip to a more reasonable size
#                    if x < callTipWidth:
#                        # Split the CallTip
#                        ratio = x / float(callTipWidth)
#                        maxTextLen = int(ratio * callTipLen * 0.8)
#
#                        lines = callTip.split("\n")
#                        formatedLines = []
#
#                        # By default wrap ignores newlines so rewrap each line
#                        # seperately
#                        for line in lines:
#                            formatedLines.append("\n".join(textwrap.wrap(line, maxTextLen)))
#
#                        callTip = "\n".join(formatedLines)

                    bytePos = bytePos - self.GetColumn(bytePos)


                # TODO: FIX
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
        elif self.vi is not None and self.vi.KeyCommandInProgress():
            # Otherwise calltips (etc..) will break a command input
            return

        wikiDocument = self.presenter.getWikiDocument()
        if wikiDocument is None:
            return
        bytePos = evt.GetPosition()
        charPos = len(self.GetTextRange(0, bytePos))
        mouseCoords = evt.GetX(), evt.GetY()

        thread = threading.Thread(target=self._threadShowCalltip,
                args=(wikiDocument, charPos, bytePos, mouseCoords),
                kwargs={"threadstop": self.calltipThreadHolder})

        self.calltipThreadHolder.setThread(thread)
        thread.setDaemon(True)
        thread.start()


    def OnDwellEnd(self, evt):
        if self.dwellLockCounter > 0:
            return

        self.calltipThreadHolder.setThread(None)
        self.CallTipCancel()

        # Set status back to previous
        callInMainThread(self.presenter.getMainControl().dropStatusMessageByKey,
                "linkToPage")
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

        if unifActionName == "action/editor/this/paste/files/insert/url/ask":
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

        if unifActionName == "action/editor/this/paste/files/insert/url/absolute":
            modeToStorage = False
            modeRelativeUrl = False
        elif unifActionName == "action/editor/this/paste/files/insert/url/relative":
            modeToStorage = False
            modeRelativeUrl = True
        elif unifActionName == "action/editor/this/paste/files/insert/url/tostorage":
            modeToStorage = True
            modeRelativeUrl = False
        elif unifActionName == "action/editor/this/paste/files/insert/url/movetostorage":
            modeToStorage = True
            modeRelativeUrl = False
            moveToStorage = True
        else:
            return

        try:
            prefix = StringOps.strftimeUB(dlgParams.rawPrefix)
        except:
            traceback.print_exc()
            prefix = ""   # TODO Error message?

        try:
            middle = StringOps.strftimeUB(dlgParams.rawMiddle)
        except:
            traceback.print_exc()
            middle = " "   # TODO Error message?

        try:
            suffix = StringOps.strftimeUB(dlgParams.rawSuffix)
        except:
            traceback.print_exc()
            suffix = ""   # TODO Error message?


        urls = []

        for fn in filenames:
            protocol = None
            if fn.endswith(".wiki"):
                protocol = "wiki"

            toStorage = False
            if modeToStorage and protocol is None:
                # Copy file into file storage
                fs = editor.presenter.getWikiDocument().getFileStorage()
                try:
                    fn = fs.createDestPath(fn, move=moveToStorage)
                    toStorage = True
                except Exception as e:
                    traceback.print_exc()
                    editor.presenter.getMainControl().displayErrorMessage(
                            _("Couldn't copy file"), e)
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
            return '\r'
        elif m_id == wx.stc.STC_EOL_CRLF:
            return '\r\n'
        else:
            return '\n'

    def GetScrollAndCaretPosition(self):
        return self.GetCurrentPos(), self.GetScrollPos(wx.HORIZONTAL), self.GetScrollPos(wx.VERTICAL)

    def SetScrollAndCaretPosition(self, pos, x, y):
        self.GotoPos(pos)
        self.scrollXY(x, y)

    def GetViHandler(self):
        return self.vi


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


class WikiTxtCtrlDropTarget(wx.DropTarget):
    def __init__(self, editor):
        wx.DropTarget.__init__(self)

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
            suffix = "/modkeys/ctrl"
        elif shiftPressed:
            suffix = "/modkeys/shift"
        else:
            suffix = ""

        mc.getUserActionCoord().reactOnUserEvent(
                "mouse/leftdrop/editor/files" + suffix, paramDict)





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
            "action/editor/this/paste/files/insert/url/absolute",
            "action/editor/this/paste/files/insert/url/relative",
            "action/editor/this/paste/files/insert/url/tostorage",
            "action/editor/this/paste/files/insert/url/movetostorage",
            "action/editor/this/paste/files/insert/url/ask") )


UserActionCoord.registerActions(_ACTIONS)



_CONTEXT_MENU_INTEXT_SPELLING = \
"""
-
Ignore;CMD_ADD_THIS_SPELLING_SESSION
Add Globally;CMD_ADD_THIS_SPELLING_GLOBAL
Add Locally;CMD_ADD_THIS_SPELLING_LOCAL
"""


_CONTEXT_MENU_INTEXT_BASE = \
"""
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
"""
-
Follow Link;CMD_ACTIVATE_THIS
Follow Link New Tab;CMD_ACTIVATE_NEW_TAB_THIS
Follow Link New Tab Backgrd.;CMD_ACTIVATE_NEW_TAB_BACKGROUND_THIS
Follow Link New Window;CMD_ACTIVATE_NEW_WINDOW_THIS
"""

_CONTEXT_MENU_INTEXT_ACTIVATE_DIRECTION = {
    "left" : """
-
Follow Link in pane|Left;CMD_ACTIVATE_THIS_LEFT
Follow Link in pane|Left New Tab;CMD_ACTIVATE_NEW_TAB_THIS_LEFT
Follow Link in pane|Left New Tab Backgrd.;CMD_ACTIVATE_NEW_TAB_BACKGROUND_THIS_LEFT
""",
    "right" : """
-
Follow Link in pane|Right;CMD_ACTIVATE_THIS_RIGHT
Follow Link in pane|Right New Tab;CMD_ACTIVATE_NEW_TAB_THIS_RIGHT
Follow Link in pane|Right New Tab Backgrd.;CMD_ACTIVATE_NEW_TAB_BACKGROUND_THIS_RIGHT
""",
    "above" : """
-
Follow Link in pane|Above;CMD_ACTIVATE_THIS_ABOVE
Follow Link in pane|Above New Tab;CMD_ACTIVATE_NEW_TAB_THIS_ABOVE
Follow Link in pane|Above New Tab Backgrd.;CMD_ACTIVATE_NEW_TAB_BACKGROUND_THIS_ABOVE
""",
    "below" : """
-
Follow Link in pane|Below;CMD_ACTIVATE_THIS_BELOW
Follow Link in pane|Below New Tab;CMD_ACTIVATE_NEW_TAB_THIS_BELOW
Follow Link in pane|Below New Tab Backgrd.;CMD_ACTIVATE_NEW_TAB_BACKGROUND_THIS_BELOW
""",
    }

_CONTEXT_MENU_INTEXT_WIKI_URL = \
"""
-
Convert Absolute/Relative File URL;CMD_CONVERT_URL_ABSOLUTE_RELATIVE_THIS
Open Containing Folder;CMD_OPEN_CONTAINING_FOLDER_THIS
"""

_CONTEXT_MENU_INTEXT_FILE_URL = \
"""
-
Convert Absolute/Relative File URL;CMD_CONVERT_URL_ABSOLUTE_RELATIVE_THIS
Open Containing Folder;CMD_OPEN_CONTAINING_FOLDER_THIS
Rename file;CMD_RENAME_FILE
Delete file;CMD_DELETE_FILE
"""


_CONTEXT_MENU_INTEXT_URL_TO_CLIPBOARD = \
"""
-
Copy Anchor URL to Clipboard;CMD_CLIPBOARD_COPY_URL_TO_THIS_ANCHOR
"""

_CONTEXT_MENU_SELECT_TEMPLATE_IN_TEMPLATE_MENU = \
"""
-
Other...;CMD_SELECT_TEMPLATE
"""

_CONTEXT_MENU_SELECT_TEMPLATE = \
"""
-
Use Template...;CMD_SELECT_TEMPLATE
"""


_CONTEXT_MENU_INTEXT_BOTTOM = \
"""
-
Close Tab;CMD_CLOSE_CURRENT_TAB
"""



FOLD_MENU = \
"""
+Show folding;CMD_CHECKBOX_SHOW_FOLDING;Show folding marks and allow folding;*ShowFolding
&Toggle current folding;CMD_TOGGLE_CURRENT_FOLDING;Toggle folding of the current line;*ToggleCurrentFolding
&Unfold All;CMD_UNFOLD_ALL_IN_CURRENT;Unfold everything in current editor;*UnfoldAll
&Fold All;CMD_FOLD_ALL_IN_CURRENT;Fold everything in current editor;*FoldAll
"""


# Entries to support i18n of context menus
if not True:
    N_("Ignore")
    N_("Add Globally")
    N_("Add Locally")

    N_("Undo")
    N_("Redo")
    N_("Cut")
    N_("Copy")
    N_("Paste")
    N_("Delete")
    N_("Select All")

    N_("Follow Link")
    N_("Follow Link New Tab")
    N_("Follow Link New Tab Backgrd.")
    N_("Follow Link New Window")

    N_("Convert Absolute/Relative File URL")
    N_("Open Containing Folder")
    N_("Rename file")
    N_("Delete file")

    N_("Copy anchor URL to clipboard")

    N_("Other...")
    N_("Use Template...")

    N_("Close Tab")

    N_("Show folding")
    N_("Show folding marks and allow folding")
    N_("&Toggle current folding")
    N_("Toggle folding of the current line")
    N_("&Unfold All")
    N_("Unfold everything in current editor")
    N_("&Fold All")
    N_("Fold everything in current editor")


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

        self.bmp = wx.StaticBitmap(self, -1, img, (0, 0), (img.GetWidth(),
                img.GetHeight()))
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
    #       repeat visual actions
    #       scroll cursor on mousewheel at viewport top/bottom

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

                    "r" : (True, self.SelectInSquareBracketIgnoreStartingSlash),

                    "(" : (True, self.SelectInRoundBracket),
                    ")" : (True, self.SelectInRoundBracket),
                    "b" : (True, self.SelectInRoundBracket),

                    # < will select double blocks, << ... >> as these
                    # are commonly used in the default wikidpad parser
                    "<" : (True, self.SelectInDoubleInequalitySigns),
                    ">" : (True, self.SelectInInequalitySigns),

                    "t" : (True, self.SelectInTagBlock),
                    # T for table?

                    "{" : (True, self.SelectInBlock),
                    "}" : (True, self.SelectInBlock),
                    "B" : (True, self.SelectInBlock),

                    '"' : (True, self.SelectInDoubleQuote),
                    "'" : (True, self.SelectInSingleQuote),
                    "`" : (True, self.SelectInTilde),

                    # The commands below are not present in vim but may
                    # be useful for quickly editing parser syntax
                    "\xc2" : (True, self.SelectInPoundSigns),
                    "$" : (True, self.SelectInDollarSigns),
                    "^" : (True, self.SelectInHats),
                    "%" : (True, self.SelectInPercentSigns),
                    "&" : (True, self.SelectInAmpersands),
                    "*" : (True, self.SelectInStars),
                    "-" : (True, self.SelectInHyphens),
                    "_" : (True, self.SelectInUnderscores),
                    "=" : (True, self.SelectInEqualSigns),
                    "+" : (True, self.SelectInPlusSigns),
                    "!" : (True, self.SelectInExclamationMarks),
                    "?" : (True, self.SelectInQuestionMarks),
                    "@" : (True, self.SelectInAtSigns),
                    "#" : (True, self.SelectInHashs),
                    "~" : (True, self.SelectInApproxSigns),
                    "|" : (True, self.SelectInVerticalBars),
                    ";" : (True, self.SelectInSemicolons),
                    ":" : (True, self.SelectInColons),
                    "\\" : (True, self.SelectInBackslashes),
                    "/" : (True, self.SelectInForwardslashes),
                }

        self.LoadKeybindings()
        self.LoadPlugins("editor")
        self.GenerateKeyBindings()

        self.SINGLE_LINE_WHITESPACE = [9, 11, 12, 32]

        self.WORD_BREAK =   '!"#$%&\'()*+,-./:;<=>?@[\\]^`{|}~'
        self.WORD_BREAK_INCLUDING_WHITESPACE = \
                            '!"#$%&\'()*+,-./:;<=>?@[\\]^`{|}~ \n\r'
        self.SENTENCE_ENDINGS = (".", "!", "?", "\n\n")
        self.SENTENCE_ENDINGS_SUFFIXS = '\'")]'

        self.BRACES = {
                        "(" : ")",
                        "[" : "]",
                        "{" : "}",
                        "<" : ">",
                        "<<" : ">>",
                      }
        self.REVERSE_BRACES = dict((v,k) for k, v in self.BRACES.items())


        self.SURROUND_REPLACEMENTS = {
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
                        #"t" : ("<{0}>", "</{0}>"),
                        #"<" : ("<{0}>", "</{0}>"),

                        "'" : ("'", "'"),
                        '"' : ('"', '"'),
                        "`" : ("`", "`"),

                        }




        self._undo_state = 0
        self._undo_pos = -1
        self._undo_start_position = None
        self._undo_positions = []

        self._line_column_pos = 0

        self.ctrl.SendMsg(2472, 1)

        # Autoenlarge autcomplete box
        self.ctrl.AutoCompSetMaxWidth(200)

    def LoadKeybindings(self):
        """
        Function called to load keybindings.

        Must call GenerateKeyBindings after this.
        """
    # Format
    # key code : (command type, (function, arguments), repeatable, selection_type)

    # command type -
    #               0 : Normal
    #               1 : Motion (inclusive)
    #               2 : Motion (exclusive)
    #               3 : Command ends in visual mode
    #               4 : Command alters visual anchor pos

    # function : function to call on keypress

    # arguments : arguments can be None, a single argument or a dictionary

    # repeatable - repeat types
    #               0 : Not repeatable
    #               1 : Normal repeat
    #               2 : Repeat with insertion (i.e. i/a/etc)
    #               3 : Replace

    # selection_type : how does the cmd select text
    #               0 : Normal
    #               1 : Always selects full lines

    # Note:
    # The repeats provided by ; and , are managed within the FindChar function

    ######## TODO: some of these are duplicated in WikiHtmlView*, they should
    #               be moved to ViHelper.

        k = self.KEY_BINDINGS
        self.keys = {
            0 : {
            # Normal mode
    (k[":"],)  : (0, (self.StartCmdInput, None), 0, 0), # :
    (k["&"],)  : (0, (self.RepeatLastSubCmd, False), 0, 0), # &
    # TODO: convert from dialog so search can be used as a motion
    (k["/"],)  : (0, (self.StartForwardSearch, None), 0, 0), # /
    (k["?"],)  : (0, (self.StartReverseSearch, None), 0, 0), # ?


    (k["<"], "m")  : (0, (self.DedentText, None), 1, 0), # <motion
    (k[">"], "m")  : (0, (self.IndentText, None), 1, 0), # >motion
    (k["c"], "m")  : (0, (self.EndDeleteInsert, None), 2, 0), # cmotion
    (k["d"], "m") : (0, (self.EndDelete, None), 1, 0), # dmotion
    (k["d"], k["s"], "*") : (0, (self.DeleteSurrounding, None), 1, 0), # ds
    (k["y"], "m") : (0, (self.Yank, None), 1, 0), # ymotion
    (k["c"], k["s"], "*", "*") : (0, (self.ChangeSurrounding, None), 1, 0), # cs**
    #       cas**??ca**?? add surrounding
    (k["y"], k["s"], "m", "*") : (0, (self.PreSurround, None), 1, 0), # ysmotion*
    # TODO: yS and ySS (indentation on new line)
    # ? yss
    (k["y"], k["S"], "m", "*") : (0, (self.PreSurroundOnNewLine, None), 1, 0), # yS**
    (k["y"], k["s"], k["s"], "*") : (0, (self.PreSurroundLine, None), 1, 0), # yss*
    (k["g"], k["u"], "m") : (0, (self.PreLowercase, None), 1, 0), # gu
    (k["g"], k["U"], "m") : (0, (self.PreUppercase, None), 1, 0), # gU
    # TODO: gugu / guu and gUgU / gUU
    (k["g"], k["s"], "m") : (0, (self.SubscriptMotion, None), 1, 0), # gs
    (k["g"], k["S"], "m") : (0, (self.SuperscriptMotion, None), 1, 0), # gS
    (k["`"], "*")  : (1, (self.GotoMark, None), 0, 0), # `
    # TODO: ' is linewise
    (k["'"], "*")  : (1, (self.GotoMarkIndent, None), 0, 0), # '
    (k["m"], "*") : (0, (self.Mark, None), 0, 0), # m
    (k["f"], "*") : (1, (self.FindNextChar, None), 4, 0), # f*
    (k["F"], "*")  : (2, (self.FindNextCharBackwards, None), 4, 0), # F*
    (k["t"], "*") : (1, (self.FindUpToNextChar, None), 5, 0), # t*
    (k["T"], "*")  : (2, (self.FindUpToNextCharBackwards, None), 5, 0), # T*
    (k["r"], "*") : (0, (self.ReplaceChar, None), 0, 0), # r*

    (k["d"], k["c"], "m", "*") : (0, (self.DeleteCharMotion,
                                            False), 1, 0), # dcmotion*

    (k["i"],) : (0, (self.Insert, None), 2, 0), # i
    (k["a"],) : (0, (self.Append, None), 2, 0), # a
    (k["I"],) : (0, (self.InsertAtLineStart, None), 2, 0), # I
    (k["A"],) : (0, (self.AppendAtLineEnd, None), 2, 0), # A
    (k["o"],) : (0, (self.OpenNewLine, False), 2, 0), # o
    (k["O"],) : (0, (self.OpenNewLine, True), 2, 0), # O
    (k["C"],) : (0, (self.TruncateLineAndInsert, None), 2, 0), # C
    (k["D"],) : (0, (self.TruncateLine, None), 1, 0), # D

    (k["x"],) : (0, (self.DeleteRight, None), 1, 0), # x
    (k["X"],) : (0, (self.DeleteLeft, None), 1, 0), # X

    (k["s"],) : (0, (self.DeleteRightAndInsert, None), 2, 0), # s
    (k["S"],) : (0, (self.DeleteLinesAndIndentInsert, None), 2, 0), # S
    (k["c"], k["c"])  : (0, (self.DeleteLinesAndIndentInsert, None), 2, 1), # cc

    (k["w"],) : (2, (self.MoveCaretNextWord, None), 0, 0), # w
    (k["W"],) : (2, (self.MoveCaretNextWORD, None), 0, 0), # W
    (k["g"], k["e"]) : (1, (self.MoveCaretPreviousWordEnd, None), 0, 0), # ge
    # TODO: gE
    (k["e"],) : (1, (self.MoveCaretWordEnd, None), 0, 0), # e
    (k["E"],) : (1, (self.MoveCaretWordEND, None), 0, 0), # E
    (k["b"],) : (2, (self.MoveCaretBackWord, None), 0, 0), # b
    (k["B"],) : (2, (self.MoveCaretBackWORD, None), 0, 0), # B

    (k["{"],) : (2, (self.MoveCaretParaUp, None), 0, 0), # {
    (k["}"],) : (2, (self.MoveCaretParaDown, None), 0, 0), # }

    (k["n"],) : (1, (self.Repeat, self.ContinueLastSearchSameDirection), 0, 0), # n
    (k["N"],) : (1, (self.Repeat, self.ContinueLastSearchReverseDirection), 0, 0), # N

    (k["*"],) : (2, (self.Repeat, self.SearchCaretWordForwards), 0, 0), # *
    (k["#"],) : (2, (self.Repeat, self.SearchCaretWordBackwards), 0, 0), # #

    (k["g"], k["*"])  : (2, (self.Repeat, self.SearchPartialCaretWordForwards), 0, 0), # g*
    (k["g"], k["#"])  : (2, (self.Repeat, self.SearchPartialCaretWordBackwards), 0, 0), # g#

    # Basic movement
    (k["h"],) : (2, (self.MoveCaretLeft, None), 0, 0), # h
    (k["k"],) : (2, (self.MoveCaretUp, None), 0, 0), # k
    (k["l"],) : (2, (self.MoveCaretRight, False), 0, 0), # l
    (k["j"],) : (2, (self.MoveCaretDown, None), 0, 0), # j

    # TODO: ctrl-h / ctrl-l - goto headings?


    (k["g"], k["k"]) : (2, (self.MoveCaretUp, {"visual" : True}), 0, 0), # gk
    (k["g"], k["j"]) : (2, (self.MoveCaretDown, {"visual" : True}), 0, 0), # gj


    (k["g"], k["0"])  : (2, (self.GotoVisualLineStart, None), 1, 0), # g0
    (k["g"], k["$"])  : (2, (self.GotoVisualLineEnd, None), 1, 0), # g$

    # Arrow keys
    (wx.WXK_LEFT,) : (2, (self.MoveCaretLeft, None), 0, 0), # left
    (wx.WXK_UP,) : (2, (self.MoveCaretUp, None), 0, 0), # up
    (wx.WXK_RIGHT,) : (2, (self.MoveCaretRight, False), 0, 0), # right
    (wx.WXK_DOWN,) : (2, (self.MoveCaretDown, None), 0, 0), # down

    (wx.WXK_RETURN,) : (1, (self.MoveCaretDownAndIndent, None), 0, 0), # enter
    (wx.WXK_NUMPAD_ENTER,) : (1, (self.MoveCaretDownAndIndent, None), 0, 0), # return

    # Line movement
    (k["$"],)    : (1, (self.GotoLineEnd, False), 0, 0), # $
    (wx.WXK_END,) : (1, (self.GotoLineEnd, False), 0, 0), # end
    (k["0"],)    : (2, (self.GotoLineStart, None), 0, 0), # 0
    (wx.WXK_HOME,) : (2, (self.GotoLineStart, None), 0, 0), # home
    (k["-"],)    : (1, (self.GotoLineIndentPreviousLine, None), 0, 0), # -
    (k["+"],)    : (1, (self.GotoLineIndentNextLine, None), 0, 0), # +
    (k["^"],)    : (2, (self.GotoLineIndent, None), 0, 0), # ^
    (k["|"],)   : (2, (self.GotoColumn, None), 0, 0), # |

    (k["("],)   : (2, (self.GotoSentenceStart, True), 0, 0), # (
    (k[")"],)   : (1, (self.GotoNextSentence, True), 0, 0), # )

    # Page scroll control
    (k["g"], k["g"])  : (1, (self.DocumentNavigation, (k["g"], k["g"])), 0, 0), # gg
    (k["G"],)        : (1, (self.DocumentNavigation, k["G"]), 0, 0), # G
    (k["%"],)        : (1, (self.DocumentNavigation, k["%"]), 0, 0), # %

    (k["H"],)        : (1, (self.GotoViewportTop, None), 0, 0), # H
    (k["L"],)        : (1, (self.GotoViewportBottom, None), 0, 0), # L
    (k["M"],)        : (1, (self.GotoViewportMiddle, None), 0, 0), # M

    (k["z"], k["z"])  : (0, (self.ScrollViewportMiddle, None), 0, 0), # zz
    (k["z"], k["t"])  : (0, (self.ScrollViewportTop, None), 0, 0), # zt
    (k["z"], k["b"])   : (0, (self.ScrollViewportBottom, None), 0, 0), # zb

    (("Ctrl", k["u"]),)    : (0, (self.ScrollViewportUpHalfScreen,
                                                        None), 0, 0), # <c-u>
    (("Ctrl", k["d"]),)    : (0, (self.ScrollViewportDownHalfScreen,
                                                        None), 0, 0), # <c-d>
    (("Ctrl", k["b"]),)     : (0, (self.ScrollViewportUpFullScreen,
                                                        None), 0, 0), # <c-b>
    (("Ctrl", k["f"]),)    : (0, (self.ScrollViewportDownFullScreen,
                                                        None), 0, 0), # <c-f>

    (("Ctrl", k["e"]),)    : (0, (self.ctrl.LineScrollDown,
                                                        None), 0, 0), # <c-e>
    (("Ctrl", k["y"]),)    : (0, (self.ctrl.LineScrollUp,
                                                        None), 0, 0), # <c-y>
#    (("Ctrl", k["e"]),)    : (0, (self.ScrollViewportLineDown,
#                                                        None), 0, 0), # <c-e>
#    (("Ctrl", k["y"]),)    : (0, (self.ScrollViewportLineUp,
#                                                        None), 0, 0), # <c-y>

    (k["Z"], k["Z"])    : (0, (self.ctrl.presenter.getMainControl().\
                                        exitWiki, None), 0, 0), # ZZ

    (k["u"],)              : (0, (self.Undo, None), 0, 0), # u
    (("Ctrl", k["r"]),)    : (0, (self.Redo, None), 0, 0), # <c-r>

    (("Ctrl", k["i"]),)    : (0, (self.GotoNextJump, None), 0, 0), # <c-i>
    (wx.WXK_TAB,)            : (0, (self.GotoNextJump, None), 0, 0), # Tab
    (("Ctrl", k["o"]),)    : (0, (self.GotoPreviousJump, None), 0, 0), # <c-o>

    # These two are motions
    (k[";"],)   : (1, (self.RepeatLastFindCharCmd, None), 0, 0), # ;
    (k[","],)   : (1, (self.RepeatLastFindCharCmdReverse, None), 0, 0), # ,

    # Replace ?
    # repeatable?
    (k["R"],)   : (0, (self.StartReplaceMode, None), 0, 0), # R

    (k["v"],)   : (3, (self.EnterVisualMode, None), 0, 0), # v
    (k["V"],)   : (3, (self.EnterLineVisualMode, None), 0, 0), # V
    #(("Ctrl", k["v"]),)   : (3, (self.EnterBlockVisualMode, None), 0, 0), # <c-v>

    (k["J"],)   : (0, (self.JoinLines, None), 1, 1), # J

    (k["~"],)   : (0, (self.SwapCase, None), 0, 0), # ~

    (k["y"], k["y"])  : (0, (self.YankLine, None), 0, 0), # yy
    (k["Y"],)        : (0, (self.YankLine, None), 0, 0), # Y
    (k["p"],)       : (0, (self.Put, False), 0, 0), # p
    (k["P"],)        : (0, (self.Put, True), 0, 0), # P

    (("Ctrl", k["v"]),)       : (0, (self.PutClipboard, False), 0, 0), # <c-v>

    (k["d"], k["d"])  : (0, (self.DeleteLine, None), 1, 0), # dd

    (k[">"], k[">"])    : (0, (self.Indent, True), 1, 0), # >>
    (k["<"], k["<"])    : (0, (self.Indent, False), 1, 0), # <<

    (k["."],)    : (0, (self.RepeatCmd, None), 0, 0), # .

    # Wikipage navigation
    # As some command (e.g. HL) are already being used in most cases
    # these navigation commands have been prefixed by "g".
    # TODO: different repeat command for these?
    (k["g"], k["f"])  : (0, (self.ctrl.activateLink, { "tabMode" : 0 }), 0, 0), # gf
    (k["\\"], k["g"], k["f"])  : (0, (self.ctrl.findSimilarWords, None), 0, 0), # \gf
    (k["g"], k["c"])  : (0, (self.PseudoActivateLink, 0), 0, 0), # gc
    (k["g"], k["C"])  : (0, (self.PseudoActivateLink, 2), 0, 0), # gC

    (("Ctrl", k["w"]), k["g"], k["f"])  : (0, (self.ctrl.activateLink, { "tabMode" : 2 }), 0, 0), # <c-w>gf
    (k["g"], k["F"])   : (0, (self.ctrl.activateLink, { "tabMode" : 2 }), 0, 0), # gF
    (k["g"], k["b"])   : (0, (self.ctrl.activateLink, { "tabMode" : 3 }), 0, 0), # gb
    # This might be going a bit overboard with history nagivaiton!
    (k["g"], k["H"])   : (0, (self.GoBackwardInHistory, None), 0, 0), # gH
    (k["g"], k["L"])   : (0, (self.GoForwardInHistory, None), 0, 0), # gL
    (k["g"], k["h"])  : (0, (self.GoBackwardInHistory, None), 0, 0), # gh
    (k["g"], k["l"])  : (0, (self.GoForwardInHistory, None), 0, 0), # gl
    (k["["],)        : (0, (self.GoBackwardInHistory, None), 0, 0), # [
    (k["]"],)        : (0, (self.GoForwardInHistory, None), 0, 0), # ]
    (k["g"], k["t"]) : (0, (self.SwitchTabs, None), 0, 0), # gt
    (k["g"], k["T"])  : (0, (self.SwitchTabs, True), 0, 0), # gT
    (k["g"], k["r"]) : (0, (self.OpenHomePage, False), 0, 0), # gr
    (k["g"], k["R"]) : (0, (self.OpenHomePage, True), 0, 0), # gR
    (k["\\"], k["o"]) : (0, (self.StartCmdInput, "open "), 0, 0), # \o
    (k["\\"], k["t"]) : (0, (self.StartCmdInput, "tabopen "), 0, 0), # \t
    # TODO: rewrite open dialog so it can be opened with new tab as default
    (k["\\"], k["O"]): (0, (self.ctrl.presenter.getMainControl(). \
                                    showWikiWordOpenDialog, None), 0, 0), # \O
    #(k["g"], k["o"]) : (0, (self.ctrl.presenter.getMainControl(). \
    #                                showWikiWordOpenDialog, None), 0), # go
    (k["g"], k["o"]) : (0, (self.StartCmdInput, "open "), 0, 0), # go
    (k["g"], k["O"]): (0, (self.ctrl.presenter.getMainControl(). \
                                    showWikiWordOpenDialog, None), 0, 0), # gO

    (k["\\"], k["u"]) : (0, (self.ViewParents, False), 0, 0), # \u
    (k["\\"], k["U"]) : (0, (self.ViewParents, True), 0, 0), # \U

    (k["\\"], k["h"], "*") : (0, (self.SetHeading, None), 1, 0), # \h{level}

    (k["\\"], k["s"]) : (0, (self.CreateShortHint, None), 2, 0), # \s

    (("Alt", k["g"]),)    : (0, (self.GoogleSelection, None), 1, 0), # <a-g>
    (("Alt", k["e"]),)    : (0, (self.ctrl.evalScriptBlocks, None), 1, 0), # <a-e>

    (("Ctrl", k["w"]), k["l"])  : (0, (self.ctrl.presenter.getMainControl().getMainAreaPanel().switchPresenterByPosition, "right"), 0, 0), # <c-w>l
    (("Ctrl", k["w"]), k["h"])  : (0, (self.ctrl.presenter.getMainControl().getMainAreaPanel().switchPresenterByPosition, "left"), 0, 0), # <c-w>l
    (("Ctrl", k["w"]), k["j"])  : (0, (self.ctrl.presenter.getMainControl().getMainAreaPanel().switchPresenterByPosition, "below"), 0, 0), # <c-w>l
    (("Ctrl", k["w"]), k["k"])  : (0, (self.ctrl.presenter.getMainControl().getMainAreaPanel().switchPresenterByPosition, "above"), 0, 0), # <c-w>l

    #(k["g"], k["s"])  : (0, (self.SwitchEditorPreview, None), 0), # gs

    # TODO: think of suitable commands for the following
    (wx.WXK_F3,)     : (0, (self.SwitchEditorPreview, "textedit"), 0, 0), # F3
    (wx.WXK_F4,)     : (0, (self.SwitchEditorPreview, "preview"), 0, 0), # F4
            }
            }


        # Could be changed to use a wildcard
        for i in self.text_object_map:
            self.keys[0][(k["i"], ord(i))] = (4, (self.SelectInTextObject, i), 0, 0)
            self.keys[0][(k["a"], ord(i))] = (4, (self.SelectATextObject, i), 0, 0)

        # INSERT MODE
        # Shortcuts available in insert mode (need to be repeatable by ".",
        # i.e. must work with EmulateKeypresses)
        self.keys[1] = {
    # TODO:
    #(("Ctrl", 64),)  : (0, (self.InsertPreviousText, None), 0), # Ctrl-@
    #(("Ctrl", k["a"]),)  : (0, (self.InsertPreviousTextLeaveInsertMode,
    #                                                    None), 0), # Ctrl-a
    (("Ctrl", k["n"]),)  : (0, (self.Autocomplete, True), 0, 0), # Ctrl-n
    (("Ctrl", k["p"]),)  : (0, (self.Autocomplete, False), 0, 0), # Ctrl-p

    # Unlike vim we these are case sensitive
    (("Ctrl", k["w"]),)  : (0, (self.DeleteBackword, False), 0, 0), # Ctrl-w
    (("Ctrl", k["W"]),)  : (0, (self.DeleteBackword, True), 0, 0), # Ctrl-W
    (("Ctrl", k["v"]),)       : (0, (self.PutClipboard, True), 0, 0), # <c-v>

    # Ctrl-t and -d indent / deindent respectively
    (("Ctrl", k["t"]),)       : (0, (self.ctrl.Tab, None), 0, 0), # <c-t>
    (("Ctrl", k["d"]),)       : (0, (self.ctrl.BackTab, None), 0, 0), # <c-d>

    # F1 and F2 in insert mode will still switch between editor and preview
    # Should it revert back to normal mode?
    (wx.WXK_F1,)     : (0, (self.SwitchEditorPreview, "textedit"), 0, 0), # F1
    (wx.WXK_F2,)     : (0, (self.SwitchEditorPreview, "preview"), 0, 0), # F2
        }

        # Rather than rewrite all the keys for other modes it is easier just
        # to modify those that need to be changed

        # VISUAL MODE
        self.keys[2] = self.keys[0].copy()
        self.keys[2].update({

    # In visual mode the caret must be able to select the last char
    (k["l"],) : (2, (self.MoveCaretRight, True), 0, 0), # l
    (wx.WXK_RIGHT,) : (2, (self.MoveCaretRight, True), 0, 0), # right

    (k["'"], "*")  : (1, (self.GotoMark, None), 0, 0), # '
    (k["`"], "*")  : (1, (self.GotoMarkIndent, None), 0, 0), # `
    (k["m"], "*") : (0, (self.Mark, None), 0, 0), # m
    (k["f"], "*") : (1, (self.FindNextChar, None), 0, 0), # f
    (k["F"], "*")  : (2, (self.FindNextCharBackwards, None), 0, 0), # F
    (k["t"], "*") : (1, (self.FindUpToNextChar, None), 0, 0), # t
    (k["T"], "*")  : (2, (self.FindUpToNextCharBackwards, None), 0, 0), # T
    (k["r"], "*") : (0, (self.ReplaceChar, None), 0, 0), # r*
    (k["S"], "*")  : (0, (self.SurroundSelection, None), 1, 0), # S

    (k["o"],)  : (4, (self.SwitchSelection, None), 0, 0), # o

    (k["c"],)  : (0, (self.DeleteSelectionAndInsert, None), 2, 0), # c
    (k["d"],)  : (0, (self.DeleteSelection, None), 1, 0), # d
    (wx.WXK_DELETE,)  : (0, (self.DeleteSelection, None), 1, 0), # del key
    (k["D"],) : (0, (self.DeleteSelectionLines, None), 2, 0), # D
    (k["x"],)  : (0, (self.DeleteSelection, None), 1, 0), # x
    (k["y"],) : (0, (self.Yank, False), 0, 0), # y
    (k["Y"],) : (0, (self.Yank, True), 0, 0), # Y
    (k["<"],) : (0, (self.Indent, {"forward":False, "visual":True}), 1, 0), # <
    (k[">"],) : (0, (self.Indent, {"forward":True, "visual":True}), 1, 0), # >
    (k["u"],) : (0, (self.SelectionToLowerCase, None), 1, 0), # u
    (k["U"],) : (0, (self.SelectionToUpperCase, None), 1, 0), # U
    (k["g"], k["u"]) : (0, (self.SelectionToLowerCase, None), 1, 0), # gu
    (k["g"], k["U"]) : (0, (self.SelectionToUpperCase, None), 1, 0), # gU
    (k["g"], k["s"]) : (0, (self.SelectionToSubscript, None), 1, 0), # gs
    (k["g"], k["S"]) : (0, (self.SelectionToSuperscript, None), 1, 0), # gS

    (k["\\"], k["d"], k["c"], "*") : (0, (self.DeleteCharFromSelection,
                                                    None), 1), # \dc*

    # Use Ctrl-r in visual mode to start a replace
    (("Ctrl", k["r"]),)    : (0, (self.StartReplaceOnSelection, None), 1, 0), # <c-r>
    (("Alt", k["g"]),)    : (0, (self.GoogleSelection, None), 1, 0), # <a-g>
            })
        # And delete a few so our key mods are correct
        # These are keys that who do not serve the same function in visual mode
        # as in normal mode (in most cases they are replaced by other function)
        del self.keys[2][(k["d"], k["d"])] # dd
        del self.keys[2][(k["y"], k["y"])] # yy
        del self.keys[2][(k["i"],)] # i
        del self.keys[2][(k["a"],)] # a
        del self.keys[2][(k["S"],)] # S
        del self.keys[2][(k["<"], k["<"])] # <<
        del self.keys[2][(k[">"], k[">"])] # <<

        self.keys[3] = {}


    def GenerateKeyBindings(self):

        #self._motion_chains = self.GenerateMotionKeyChains(self.keys)
        self.key_mods = self.GenerateKeyModifiers(self.keys)
        self.motion_keys = self.GenerateMotionKeys(self.keys)
        self.motion_key_mods = self.GenerateKeyModifiers(self.motion_keys)

        # Used for rewriting menu shortcuts
        self.GenerateKeyAccelerators(self.keys)

    def ApplySettings(self):
        # Set wrap indent mode
        self.ctrl.SendMsg(2472, self.settings["set_wrap_indent_mode"])

        #self.ctrl.SendMsg(, self.settings["set_wrap_start_indent"])

    def Setup(self):
        self.AddJumpPosition(self.ctrl.GetCurrentPos())

    def EndInsertMode(self):
        # If switching from insert mode vi does a few things
        if self.mode == ViHelper.INSERT:
            # Move back one pos if not at the start of a line
            if self.ctrl.GetCurrentPos() != \
                    self.GetLineStartPos(self.ctrl.GetCurrentLine()):
                self.ctrl.CharLeft()

            # If current line only contains whitespace remove it
            current_line = self.ctrl.GetCurLine()[0]
            if len(current_line) > 1 and current_line.strip() == "":
                self.ctrl.LineDelete()
                self.ctrl.AddText(self.ctrl.GetEOLChar())
                self.ctrl.CharLeft()
            self.SetMode(ViHelper.NORMAL)
            self.EndUndo()

    def SetMode(self, mode):
        """
        It would be nice to set caret alpha but i don't think its
        possible at the moment
        """

        if mode is None:
            mode = self.mode
        else:
            self.mode = mode

        # ! there may be some situations in which we want to do this
        #   but it is probably better handled in the calling function
        ## Save caret position
        #self.SetLineColumnPos()

        if mode == ViHelper.NORMAL:
            # Set block caret (Not in wxpython < 2.9)
            self.SetCaretStyle("block")
            #self.ctrl.SetCaretWidth(40)

            self.ctrl.SetCaretPeriod(800)
            #self.ctrl.SetSelectionMode(0)
            self.RemoveSelection()
            self.SetCaretColour(self.settings['caret_colour_normal'])
            self.ctrl.SetOvertype(False)
            self.SetSelMode("NORMAL")
            # Vim never goes right to the end of the line
            self.CheckLineEnd()
        elif mode == ViHelper.VISUAL:
            self.SetCaretStyle("line")
            #self.ctrl.SetCaretWidth(1)
            self.SetCaretColour(self.settings['caret_colour_visual'])
            self.ctrl.SetOvertype(False)
        elif mode == ViHelper.INSERT:
            self.insert_action = []
            self.SetCaretStyle("line")
            #self.ctrl.SetCaretWidth(1)
            self.SetCaretColour(self.settings['caret_colour_insert'])
            self.ctrl.SetOvertype(False)
        elif mode == ViHelper.REPLACE:
            self.SetCaretStyle("block")
            #self.ctrl.SetCaretWidth(1)
            self.SetCaretColour(self.settings['caret_colour_replace'])
            self.ctrl.SetOvertype(True)

    def SetCaretStyle(self, style):
        """
        Helper to set the caret style

        @param style: Caret style
        """
        # default caret style is line
        sci_style = 1
        if style == "block":
            sci_style = 2
        elif style == "invisible":
            sci_style = 0

        self.ctrl.SendMsg(2512, sci_style)

    def SetCaretColour(self, colour):
        """
        Helper to set the caret colour

        @param colour: wx colour
        """
        self.ctrl.SetCaretForeground(colour)

    # Starting code to allow correct postitioning when undoing and redoing
    # actions

    # Need to overide Undo and Redo to goto positions
    # TODO: Tidy up
    def BeginUndo(self, use_start_pos=True, force=False):

        if self._undo_state == 0:
            self.ctrl.BeginUndoAction()
            print("START UNDO")
            self._undo_positions = \
                        self._undo_positions[:self._undo_pos + 1]

            if use_start_pos:
                if self.HasSelection():
                    self._undo_start_position = self._GetSelectionRange()[0]
                else:
                    self._undo_start_position = self.ctrl.GetCurrentPos()

        self._undo_state += 1
        print("BEGIN", self._undo_state, inspect.getframeinfo(inspect.currentframe().f_back)[2])

    def EndUndo(self, force=False):
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
            print("END UNDO")
        self._undo_state -= 1

        print(self._undo_state, inspect.getframeinfo(inspect.currentframe().f_back)[2])

    def EndBeginUndo(self):
        # TODO: shares code with EndUndo and BeginUndo
        self.ctrl.EndUndoAction()
        if self._undo_start_position is not None:
            self._undo_positions.append(self._undo_start_position)
            self._undo_start_position = None

        elif self.HasSelection:
            self._undo_positions.append(self.ctrl.GetSelectionStart())
        else:
            self._undo_positions.append(self.ctrl.GetCurrentPos())
        self._undo_pos += 1

        self.ctrl.BeginUndoAction()
        self._undo_positions = \
                    self._undo_positions[:self._undo_pos + 1]

        if self.HasSelection():
            self._undo_start_position = self._GetSelectionRange()[0]
        else:
            self._undo_start_position = self.ctrl.GetCurrentPos()

    def _Undo(self):
        if self._undo_pos < 0:
            return False
        self.ctrl.Undo()
        self.ctrl.GotoPos(self._undo_positions[self._undo_pos])
        self.SetLineColumnPos()
        self._undo_pos -= 1

    def _Redo(self):
        # NOTE: the position may be off on some redo's
        if self._undo_pos > len(self._undo_positions):
            return False

        self.ctrl.Redo()
        self._undo_pos += 1

    def SetLineColumnPos(self):
        currentPos = self.ctrl.GetCurrentPos()
        currentCol = self.ctrl.GetColumn(currentPos)
        self._line_column_pos = currentCol

        self.ctrl.ChooseCaretX()

    def GetLineColumnPos(self):
        return self._line_column_pos

    def GotoFirstVisibleLine(self):
        # GetFirstVisibleLine does not take into account word wrapping
        line = self.GetFirstVisibleLine()
        # Correct for word wrapping
        pos = self.ctrl.GetLineIndentPosition(line)
        text = self.ctrl.GetTextRange(0, pos)

        self.ctrl.GotoLine(line)

    def GotoLastVisibleLine(self):
        line = self.GetLastVisibleLine()
        if line > self.ctrl.GetCurrentLine():
            return
        self.ctrl.GotoLine(line)

    def FlushBuffersExtra(self):
        #self.SetCaretColour(self.settings['caret_colour_normal'])
        self.SetMode(None)
        self.register.SelectRegister(None)

    def OnMouseScroll(self, evt):
        # TODO: check if it would be better to move the caret once scrolling has
        #       finished (It would but there is no way to detect where to move
        #       it to...)

        # Not the best solution possible but until GetFirstVisibleLine
        # is fixed appears to be the best.
        current_line = self.ctrl.GetCurrentLine()
        if evt.GetWheelRotation() < 0:
            if current_line <= self.GetFirstVisibleLine():

                for i in range(evt.GetLinesPerAction()):
                    #self.ctrl.LineDown()
                    self.ctrl.LineScrollDown()
                return
        else:
            if current_line >= self.GetLastVisibleLine() - \
                    evt.GetLinesPerAction() - 1:

                for i in range(evt.GetLinesPerAction()):
                    #self.ctrl.LineUp()
                    self.ctrl.LineScrollUp()
                return
        #if self.ctrl.GetLineVisible(current_line):
        #    top_line = self.GetFirstVisibleLine() + 1
        #    bottom_line = self.GetLastVisibleLine()

        #    if current_line < top_line:
        #        wx.CallAfter(self.GotoFirstVisibleLine)
        #    elif current_line > bottom_line:
        #        wx.CallAfter(self.GotoLastVisibleLine)
        #    #offset = evt.GetWheelRotation() / 40
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


#    def OnScroll(self, evt):
#        """
#        Vim never lets the caret out of the viewport so track any
#        viewport movements
#        """
#        # NOTE: may be inefficient?
#        #       perhaps use EVT_SCROLLWIN_LINEUP
#        current_line = self.ctrl.GetCurrentLine()
#        top_line = self.GetFirstVisibleLine()+1
#        bottom_line = self.GetLastVisibleLine()-1
#
#        if current_line < top_line:
#            self.MoveCaretToLine(top_line)
#        elif current_line > bottom_line:
#            self.MoveCaretToLine(bottom_line)
#        evt.Skip()

    def OnMouseClick(self, evt):
        # Vim runs the command after changing the mouse position
        self.ctrl.OnClick(evt)
        wx.CallAfter(self.SetLineColumnPos)

        # TODO::
        # Get Mouse Pos and save it as motion cmd
        #if self.NextKeyCommandCanBeMotion:
        #    self.StartSelection()
        #    evt = wx.KeyEvent(wx.wxEVT_KEY_DOWN)
        #    evt.m_keyCode = -999 # Should this be done?
        #    wx.PostEvent(self.ctrl, evt)

    def OnLeftMouseUp(self, evt):
        """Enter visual mode if text is selected by mouse"""
        # Prevent the end of line character from being selected as per vim
        # This will cause a slight delay, there may be a better solution
        # May be possible to override MOUSE_DOWN event.

        # If we are in insert mode we clear our insert buffer and reset
        # and undo's
        if self.mode == ViHelper.INSERT:
            self.EndBeginUndo()
            self.insert_action = []
        wx.CallAfter(self.EnterVisualModeIfRequired)
        wx.CallAfter(self.CheckLineEnd)
        evt.Skip()

    def EnterVisualModeIfRequired(self):
        if len(self.ctrl.GetSelectedText()) > 0:
            self.EnterVisualMode(True)
        else:
            self.LeaveVisualMode()

    def OnAutocompleteKeyDown(self, evt):

        if evt.GetRawKeyCode() in (65505, 65507, 65513):
            return

        if evt.GetKeyCode() in (wx.WXK_UP, wx.WXK_DOWN, wx.WXK_RETURN):
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

        evt.Skip()




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
        # NOTE: wxstyledtextctrl supports macros which would probably be a
        #       better solution for much of this.
        if len(actions) > 0:

            eol = self.ctrl.GetEOLChar()

            for i in actions:
                # TODO: handle modifier keys, e.g. ctrl
                if i == wx.WXK_LEFT:
                    self.ctrl.CharLeft()
                elif i == wx.WXK_RIGHT:
                    self.ctrl.CharRight()
                elif i == wx.WXK_BACK:
                    self.ctrl.DeleteBackNotLine()
                elif i in [wx.WXK_DELETE]:# 65439????
                    self.ctrl.CharRight()
                    self.ctrl.DeleteBack()
                elif i in [wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER]: # enter, return
                    self.ctrl.InsertText(self.ctrl.GetCurrentPos(), eol)
                    self.ctrl.CharRight()
                elif i == wx.WXK_TAB: # tab
                    self.ctrl.InsertText(self.ctrl.GetCurrentPos(), "\t")
                    self.ctrl.CharRight()
                else:
                    self.ctrl.InsertText(self.ctrl.GetCurrentPos(), chr(i))
                    self.ctrl.CharRight()

    def _RepeatCmdHelper(self):
        self.visualBell("GREEN")
        #self.BeginUndo()
        cmd_type, key, count, motion, motion_wildcards, wildcards, \
                text_to_select = self.last_cmd

        # If no count has been specified use saved count
        if not self.true_count:
            self.count = count
        # overwise save the new count
        else:
            self.last_cmd[2] = self.count
        self._motion = motion
        actions = self.insert_action
        # NOTE: Is "." only going to repeat editable commands as in vim?
        if cmd_type == 1:
            self.RunFunction(key, motion, motion_wildcards, wildcards,
                                                text_to_select, repeat=True)
        # If a command ends in insertion mode we also repeat any changes
        # made up until the next mode change.
        elif cmd_type == 2: # + insertion
            self.RunFunction(key, motion, motion_wildcards, wildcards,
                                                text_to_select, repeat=True)
            # Emulate keypresses
            # Return to normal mode
            self.EmulateKeypresses(actions)
            self.EndInsertMode()
        elif cmd_type == 3:
            self.ReplaceChar(key)
        #self.EndUndo()
        self.insert_action = actions

    def RepeatCmd(self):
        # TODO: move to ViHelper?
        if self.last_cmd is not None:
            self.BeginUndo()
            # If a count is specified the count in the previous cmd is changed
            #self.Repeat(self._RepeatCmdHelper)
            self._RepeatCmdHelper()
            self.EndUndo()
        else:
            self.visualBell("RED")


#--------------------------------------------------------------------
# Misc stuff
#--------------------------------------------------------------------
    def PseudoActivateLink(self, tab_mode):
        """
        A custom way to follow links.

        Useful for a number of reasons
            # It works on the text (so does not need a parsed page)
            # It capitalises the first letter of the link
        """
        self.SelectInSquareBracket()

        self.SelectSelection(1)
        wikiword = self.ctrl.GetSelectedText()

        # Arbitrary limits are fun
        if len(wikiword) < 2:
            return

        if "|" in wikiword:
            wikiword = wikiword.split("|")[0]

        if wikiword.startswith("//"):
            wikiword = wikiword[2:]
        elif wikiword.startswith("/"):
            wikiword = self.ctrl.presenter.getWikiWord()+wikiword

        wikiword = wikiword[:1].upper() + wikiword[1:]

        self.ctrl.presenter.getMainControl().activatePageByUnifiedName(
            "wikipage/" + wikiword, tabMode=tab_mode)


    def Autocomplete(self, forwards):
        """
        Basic autocomplete

        Will search in current page for completions to basic words

        Also supports completing relative links (may not work on windows)
        """
        # TODO: fix for single length words.
        if not self.ctrl.AutoCompActive():
            pos = self.ctrl.GetCurrentPos()
            # First check if we are working with a link

            link = self.GetLinkAtCaret(link_type="rel://")

            if link is not None:
                word = None
            else:
                self.ctrl.GotoPos(pos)

                # NOTE: list order is not correct
                if pos - 1 > 0 and self.GetUnichrAt(pos-1) in \
                                    self.WORD_BREAK_INCLUDING_WHITESPACE:
                    word = "[a-zA-Z0-9_]"
                    completion_length = 0
                # Select in word fails if it is a single char, may be better
                # to fix it there
                elif pos - 2 > 0 and self.GetUnichrAt(pos-2) in \
                                    self.WORD_BREAK_INCLUDING_WHITESPACE:
                    self.ctrl.CharLeftExtend()
                    word = self.ctrl.GetSelectedText()
                    completion_length = 1
                else:
                    self.ctrl.CharLeft()
                    # Vim only selects backwards
                    # this will select the entire word
                    self.SelectInWord()
                    self.ctrl.CharRightExtend()
                    #self.ExtendSelectionIfRequired()
                    word = self.ctrl.GetSelectedText()
                    completion_length = len(word)

            # Remove duplicates
            completions = set()

            if word is None:
                abs_link = self.ctrl.presenter.getWikiDocument()\
                            .makeRelUrlAbsolute(link)

                # Check if link is a dir
                link_is_dir = False
                if isdir(abs_link[5:]):
                    link_is_dir = True

                link_dirname = dirname(abs_link)
                link_basename = basename(abs_link)

                # Search for matching files within the current directory
                files = listdir("{0}".format(link_dirname[5:]))
                completion_list = [self.ctrl.presenter.getWikiDocument()\
                            .makeAbsUrlRelative(join(link_dirname, i)) \
                            for i in files if link_basename == "" \
                            or i.startswith(link_basename)]

                # If the link is a directory we need to add all files from
                # that directory
                if link_is_dir:
                    completion_list.extend(
                            [self.ctrl.presenter.getWikiDocument()\
                                .makeAbsUrlRelative(join(abs_link, i)) \
                                for i in listdir(abs_link[5:])])

                completion_length = len(link)
            else:
                # Search for possible autocompletions
                # Bad ordering at the moment
                text = self.ctrl.GetTextRange(
                            self.ctrl.GetCurrentPos(), self.ctrl.GetLength())
                completion_list = re.findall(r"\b{0}.*?\b".format(re.escape(word)),
                        text, re.U)
                text = self.ctrl.GetTextRange(0, self.ctrl.GetCurrentPos())
                completion_list.extend(re.findall(r"\b{0}.*?\b".format(word),
                        text, re.U))
                completions.add(word)


            unique_completion_list = [i for i in completion_list if i not in completions \
                    and not completions.add(i)]

            # No completions found
            if len(unique_completion_list) < 1:
                if self.HasSelection():
                    self.ctrl.CharRight()
                self.visualBell("RED")
                return

            completion_list_prepped = "\x01".join(unique_completion_list)

            if self.HasSelection():
                self.ctrl.CharRight()
            self.ctrl.AutoCompShow(completion_length, completion_list_prepped)

    def GetFirstVisibleLine(self):
        return self.ctrl.GetFirstVisibleLine()
        #line = self.ctrl.GetFirstVisibleLine()
        #pos = self.ctrl.GetLineIdentPosition(line)
        #text = self.ctrl.GetTextRange(0, pos)
        #move = 0
        #print line, self.ctrl.GetLineVisible(line)
        #while self.ctrl.GetLineVisible(line - 1) and line - 1 > 0:
        #    line -= 1
        #
        #return line

    def GetLastVisibleLine(self):
        """
        Returns line number of the first visible line in viewport
        """
        return self.GetFirstVisibleLine() + self.ctrl.LinesOnScreen() - 1

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


#     def GotoSelectionStart(self):
#         self.ctrl.GotoPos(self.ctrl.GetSelectionStart())

    def InsertPreviousText(self):
        self.EmulateKeypresses(self.insert_action)

    def InsertPreviousTextLeaveInsertMode(self):
        self.InsertPreviousText()
        self.EndInsertMode()

    def ChangeSurrounding(self, keycodes):
        self.BeginUndo(force=True)
        r = self.DeleteSurrounding(keycodes[0])
        if r:
            self.StartSelection(r[0])
            self.ctrl.GotoPos(r[1])
            self.SelectSelection(2)
            self.SurroundSelection(keycodes[1])
        self.EndUndo(force=True)

        return
        # TODO: should work on the diff between selecting A and In text block
        char_to_change = self.GetCharFromCode(keycodes[0])
        if char_to_change in self.text_object_map:
            self.SelectATextObject(char_to_change)
            if self.HasSelection():
                #pos = self.ExtendSelectionIfRequired()
                pos = self.ctrl.GetSelectionStart()
                self.BeginUndo(force=True)
                self.ctrl.CharRightExtend()
                text = self.ctrl.GetSelectedText()[1:-1]
                self.ctrl.ReplaceSelection(text)
                #self.ctrl.CharLeft()
                self.ctrl.SetSelection(pos, pos + len(text))
                self.SurroundSelection(keycodes[1])
                self.ctrl.GotoPos(pos)
                self.EndUndo(force=True)
                self.visualBell("GREEN")
                return
        self.visualBell("RED")

    def PreSurround(self, code):
        self.BeginUndo(use_start_pos=True, force=True)
        self.SurroundSelection(code)
        self.EndUndo()

    def PreSurroundOnNewLine(self, code):
        self.BeginUndo(use_start_pos=True, force=True)
        self.SurroundSelection(code, new_line=True)
        self.EndUndo()

    def PreSurroundLine(self, code):
        self.SelectCurrentLine()
        self.BeginUndo(use_start_pos=True)
        self.SurroundSelection(code)
        self.EndUndo()

    def GetUnichrAt(self, pos, checkstart=False):
        """
        Returns the character under the caret. 
        """
        if checkstart:
            return self.ctrl.GetTextRange(
                    self.PositionBefore(self.PositionAfter(pos)), 
                    self.ctrl.PositionAfter(pos))
        else:
            return self.ctrl.GetTextRange(pos, self.ctrl.PositionAfter(pos))

        # Unfortunately we still can't use
        return self.ctrl.GetCharAt(pos)

        # Pre phoenix method
        return self.ctrl.GetTextRange(pos, self.ctrl.PositionAfter(pos))

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
            between, cmd = self.text_object_map[ob]

            if between:
                cmd(extra)
            else:
                self.SelectForwardStream(cmd, extra)
            #self.text_object_map[ob][1](extra)
            #self.ExtendSelectionIfRequired()
            #if extra:  # extra corresponds to a
            #    if self.text_object_map[ob][0]: # text block
            #        pass # Select surrouding chars
            #    else:
            #        self.SelectTrailingWhitespace(sel_start, sel_end)


            #if self.mode == ViHelper.VISUAL:
            #    self.ctrl.CharRightExtend()


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
                    in self.SINGLE_LINE_WHITESPACE:
                pos -= 1

                if pos == 0:
                    break

            self.ctrl.GotoPos(pos)
            self.StartSelection()
            self.ctrl.GotoPos(true_end)
        #self.SelectSelection()

    def SelectForwardStream(self, cmd, extra):
        start_anchor = False
        if self.HasSelection():
            start_anchor = self.ctrl.GetSelectionStart()

        cmd(extra)

        if start_anchor and self._anchor > start_anchor:
            self._anchor = start_anchor

        self.SelectSelection(2)


    def SelectInWord(self, extra=False):
        """
        Selects n words where n is the count. Whitespace between words
        is counted.
        """
        self._SelectInWords(False, extra=extra)

    def SelectInWORD(self, extra=False):
        self._SelectInWords(True, extra=extra)

    def _SelectInWords(self, WORD=False, extra=False):
        # NOTE: in VIM direction depends on selection stream direction
        #       there are still a number of difference between this
        #       and vims implementation

        # NOTE: Does not select single characters

        # TODO: Does not select the word if on final character
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
                elif ((self.GetUnichrAt(pos) in self.WORD_BREAK) is not \
                        (self.GetUnichrAt(pos-1) in self.WORD_BREAK)) \
                        and not WORD:
                    pass
                else:
                    back_word(1)
        sel_start = self.StartSelection(None)
        move_caret_word_end_count_whitespace(1)
        sel_end = self.ctrl.GetCurrentPos()
        if extra:
            self.SelectTrailingWhitespace(sel_start, sel_end)
        move_caret_word_end_count_whitespace(self.count-1)

        self.SelectSelection(2)

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
        elif pos > 0 and self.GetUnichrAt(pos-1) in self.SENTENCE_ENDINGS:
            pass
        else:
            self.GotoSentenceStart(1)
        sel_start = self.StartSelection()
        #self.GotoSentenceEnd(1)
        if extra:
            self.count += 1
        self.GotoSentenceEndCountWhitespace()

        self.SelectSelection(2)

    def SelectInParagraph(self, extra=False):
        """ Selects current paragraph. """
        # TODO: fix for multiple counts
        #       should track back to whitespace start
        self.MoveCaretParaDown(1)
        self.MoveCaretParaUp(1)
        self.StartSelection(None)
        self.MoveCaretParaDown()
        self.ctrl.CharLeft()
        self.ctrl.CharLeft()
        self.SelectSelection(2)

    def _SelectInBracket(self, bracket, extra=False, start_pos=None,
            count=None, linewise=False, ignore_forewardslashes=False):
        # TODO: config option to "delete preceeding whitespace"
        if start_pos is None: start_pos = self.ctrl.GetCurrentPos()
        if count is None: count = self.count

        if self.SearchBackwardsForChar(bracket, count):
            pos = self.ctrl.GetCurrentPos()

            pre_text = self.ctrl.GetTextRangeRaw(pos, start_pos)

            while pre_text.count(bracket.encode()) - \
                    pre_text.count(self.BRACES[bracket].encode()) != self.count:
                self.ctrl.CharLeft()
                if self.SearchBackwardsForChar(bracket, 1):
                    pos = self.ctrl.GetCurrentPos()
                    pre_text = self.ctrl.GetTextRangeRaw(pos, start_pos)
                else:
                    break

            if self.MatchBraceUnderCaret(brace=bracket):
                self.StartSelection(pos)
                self.SelectSelection(2)
                sel_start, sel_end = self._GetSelectionRange()
                if not sel_start <= start_pos <= sel_end:
                    self.ctrl.GotoPos(sel_start-len(bracket))
                    self._SelectInBracket(bracket, extra, start_pos, count)
                else:
                    # Only select the brackets if required
                    if not extra:
                        sel_start = self.StartSelection(sel_start+len(bracket))
                        if ignore_forewardslashes:
                            if self.GetUnichrAt(sel_start) == "/":
                                sel_start = self.StartSelection(sel_start+1)
                            if self.GetUnichrAt(sel_start) == "/":
                                sel_start = self.StartSelection(sel_start+1)

                        self.ctrl.GotoPos(sel_end - len(bracket))
                        #self.ctrl.SetSelection(sel_start+len(bracket), sel_end-len(bracket))
                        #self.ctrl.CharLeftExtend()
                    else:
                        sel_start = self.StartSelection(sel_start)
                        self.ctrl.GotoPos(sel_end - len(bracket) + 1)
                        if linewise:
                            self.ctrl.CharRightExtend()
            else:
                self.ctrl.GotoPos(start_pos)
        self.SelectSelection(2)

    def SelectInSquareBracket(self, extra=False):
        """ Selects text in [ ] block """
        self._SelectInBracket("[", extra)

    def SelectInSquareBracketIgnoreStartingSlash(self, extra=False):
        """ Selects text in [ ] block ignoring an starting /'s """
        self._SelectInBracket("[", extra, ignore_forewardslashes=True)

    def SelectInRoundBracket(self, extra=False):
        """ Selects text in ( ) block """
        self._SelectInBracket("(", extra)

    def SelectInInequalitySigns(self, extra=False):
        """ Selects text in < > block """
        self._SelectInBracket("<", extra)

    def SelectInDoubleInequalitySigns(self, extra=False):
        """ Selects text in < > block """
        self._SelectInBracket("<<", extra, linewise=True)

    # TODO: rewrite so input is handled more generally
    #       (and handled at the time of keypress)
    def SelectInTagBlock(self, extra=False):
        """ selects text in <aaa> </aaa> block """

        # Catch key inputs
        if not self.tag_input:
            try:
                dialog = wx.TextEntryDialog(self.ctrl.presenter.getMainControl(), "Enter tag")
                if dialog.ShowModal() == wx.ID_OK:
                    tag_content = dialog.GetValue()


                    self.tag_input = tag_content
                    r = self._SelectInChars("<{0}>".format(tag_content), forward_char="</{0}>".format(tag_content), extra=extra)
                    return r
                return False
            finally:
                dialog.Destroy()
        else:
            tag_content = self.tag_input
            return self._SelectInChars("<{0}>".format(tag_content), forward_char="</{0}>".format(tag_content), extra=extra)

    def SelectInBlock(self, extra=False):
        """ selects text in { } block """
        self._SelectInBracket("{", extra)

    def _SelectInChars(self, char, extra=False, forward_char=None):
        """
        Select in between "char" blocks.

        If "forward_char" is not None will select between "char" and
        "forward_char".

        Note:
            char / forward_char must not be unicode
        """
        if forward_char is None:
            forward_char = char

        pos = self.ctrl.GetCurrentPos()
        if self.SearchBackwardsForChar(char):
            start_pos = self.ctrl.GetCurrentPos()

            if self.SearchForwardsForChar(forward_char, start_offset=0):
                self.StartSelection(start_pos)
                self.SelectSelection(2)
                if not extra:
                    self.ctrl.CharLeftExtend()
                    self.StartSelection(start_pos+len(char))
                    self.SelectSelection(2)

                else:
                    for i in range(1, len(forward_char)):
                        self.ctrl.CharRightExtend()
                    self.SelectSelection(2)
                return True

        self.ctrl.GotoPos(pos)
        return False

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


    def SurroundSelection(self, keycode, new_line=False):
        #start = self.ExtendSelectionIfRequired()
        start = self.ctrl.GetSelectionStart()

        text = self.ctrl.GetSelectedText()

        if len(text) < 1:
            return # Should never happen

        self.BeginUndo()

        # Fix for EOL
        if text[-1] == self.ctrl.GetEOLChar():
            sel_start, sel_end = self._GetSelectionRange()
            self.ctrl.SetSelection(sel_start, sel_end-1)
            text = self.ctrl.GetSelectedText()

        replacements = self.SURROUND_REPLACEMENTS

        if new_line:
            text = "\n{0}\n".format(text)

        uni_chr = chr(keycode)
        if uni_chr in replacements:
            # Use .join([]) ?

            REWRITE_SUB_SUP_LINKS = True

            new_text = text

            # TODO: add option to rewrite links containing <sup> and <sub> tags
            tags = ["<sup>", "</sup>", "<sub>", "</sub>"]
            if uni_chr == "r" and REWRITE_SUB_SUP_LINKS and \
                    True in [tag in text for tag in tags]:
                stripped_text = text
                for tag in tags:
                    stripped_text = stripped_text.replace(tag, "")
                new_text = "{0}|{1}".format(stripped_text, text)

            # If r is used on a subpage we will add // for ease of use
            if uni_chr == "r" and "/" in self.ctrl.presenter.getWikiWord():
                new_text = "{0}//{1}{2}".format(replacements[uni_chr][0], new_text, replacements[uni_chr][1])
            else:
                new_text = "{0}{1}{2}".format(replacements[uni_chr][0], new_text, replacements[uni_chr][1])
        else:
            new_text = "{0}{1}{2}".format(uni_chr, text, uni_chr)

        self.ctrl.ReplaceSelection(new_text)
        self.LeaveVisualMode()
        self.ctrl.GotoPos(start)
        self.SetLineColumnPos()
        self.EndUndo()


    def CheckLineEnd(self):
        if self.mode not in [ViHelper.VISUAL, ViHelper.INSERT]:
            line_text, line_pos = self.ctrl.GetCurLineRaw()
            if len(line_text) > 1 and line_text != self.ctrl.GetEOLChar():
                if self.OnLastLine():
                    if line_pos >= len(line_text):
                        self.ctrl.CharLeft()
                else:
                    if line_pos >= len(line_text) - 1:
                        self.ctrl.CharLeft()

    def OnLastLine(self):
        return self.ctrl.GetCurrentLine() + 1 == self.ctrl.GetLineCount()

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
        #self.ctrl.SetSelection(end, start)
        self.ctrl.SetSelection(start, end)

    def SelectFullLines(self, include_eol=False):
        """
        Could probably be replaced by SetSectionMode,
        if it can be made to work. (retest with wx >= 2.9)
        """
        start_line, end_line = self._GetSelectedLines(exclusive=True)

        if self.ctrl.GetCurrentPos() >= self.GetSelectionAnchor():
            reverse = False

            # If selection is not on an empty line
            if self.ctrl.GetLine(start_line) != self.ctrl.GetEOLChar():
                end_line -= 1

            if self.GetUnichrAt(self.GetSelectionAnchor()) == \
                    self.ctrl.GetEOLChar():
                start_line += 1

            if self.ctrl.GetCurrentPos() > \
                    self.ctrl.GetLineEndPosition(end_line):
                end_line += 1

        else:
            reverse = True
            end_line -= 1

        self.SelectLines(start_line, end_line, reverse=reverse,
                include_eol=include_eol)


    def JoinLines(self):
        self.BeginUndo(use_start_pos=True)
        text = self.ctrl.GetSelectedText()
        start_line = self.ctrl.GetCurrentLine()
        eol_char = self.ctrl.GetEOLChar()
        if len(text) < 1:
            # We need at least 2 lines to be able to join
            count = self.count if self.count > 1 else 2
            self.SelectLines(start_line, start_line - 1 + count)
        else:
            self.SelectFullLines()

        text = self.ctrl.GetSelectedText()

        # Probably not the most efficient way to do this
        # We need to lstrip every line except the first
        lines = text.split(eol_char)
        new_text = []
        for i in range(len(lines)):
            line = lines[i]
            if line.strip() == "": # Leave out empty lines
                continue
            # Strip one space from line end (if it exists)
            elif line.endswith(" "):
                line = line[:-1]

            if i == 0:
                new_text.append(line)
            else:
                if ViHelper.STRIP_BULLETS_ON_LINE_JOIN:
                    # TODO: roman numerals
                    # It may be better to avoid using a regex here?
                    line = re.sub(r"^ *(\*|#|\d\.) ", r"", line)
                new_text.append(line.lstrip())

        self.ctrl.ReplaceSelection(" ".join(new_text))
        self.CheckLineEnd()
        self.EndUndo()

    #def DeleteCharMotion(self, key_code):
    #    if not self.HasSelection():
    #        self.visualBell("RED")
    #        return

    def DeleteCharMotion(self, key_code):
        self.DeleteCharFromSelection(key_code)

    def DeleteCharFromSelection(self, key_code):
        """
        Remove key_codes corresponding char from selection

        """
        if not self.HasSelection():
            self.visualBell("RED")
            return
        self.BeginUndo(use_start_pos=True)
        char = self.GetCharFromCode(key_code)
        text = self.ctrl.GetSelectedText()
        new_text = text.replace(char, "")
        self.ctrl.ReplaceSelection(new_text)
        self.SetLineColumnPos()
        self.EndUndo()


    def DeleteBackword(self, word=False):
        if word:
            move_word = self.MoveCaretBackWORD
        else:
            move_word = self.MoveCaretBackWord
        self.StartSelection()
        move_word()
        self.SelectSelection(2)
        self.DeleteSelection(yank=False)

    def DeleteSelectionAndInsert(self):
        self.DeleteSelection()
        self.Insert()

    def RemoveSelection(self, pos=None):
        """
        Removes the selection.

        """
        if pos is None:
            pos = self.ctrl.GetAnchor()
        self.ctrl.SetSelection(pos,pos)

    # TODO: Clean up selection names
    def GetSelectionAnchor(self):
        return self._anchor

    def SelectEOLCharIfRequired(self):
        """
        Select the end of line character if current selection spans multiple
        lines and selects and selects all the text. Will select the EOL char
        if required.

        @return: True if multiple lines are selected in their entirety.
        """
        sel_start, sel_end = self._GetSelectionRange()

        eol_char = self.ctrl.GetEOLChar()

        if self.GetUnichrAt(sel_start - 1) != eol_char or \
                self.ctrl.GetEOLChar() not in self.ctrl.GetSelectedText():
            return False

        if self.GetUnichrAt(sel_end - 1) == eol_char:
            return True
        elif self.GetUnichrAt(sel_end) == eol_char:
            self.ctrl.CharRightExtend()
            return True

        return False

    def GetSelectionDetails(self, selection_type):
        """
        Returns the type of selection

        """
        # Test if selection is lines
        if selection_type == 1 or self.GetSelMode() == "LINE" or \
        (self.GetLineStartPos(self.ctrl.LineFromPosition(
        self.ctrl.GetSelectionStart())) == self.ctrl.GetSelectionStart() and \
        self.ctrl.GetLineEndPosition(self.ctrl.LineFromPosition(
        self.ctrl.GetSelectionEnd())) == self.ctrl.GetSelectionEnd()):
            start, end = self._GetSelectedLines()
            return (True, end-start)
        else:
            return (False, len(self.ctrl.GetSelectedText()))

    def StartSelection(self, pos=None):
        """ Saves the current position to be used for selection start """
        if pos is None:
            pos = self.ctrl.GetCurrentPos()
        self._anchor = pos

        return pos

    def StartSelectionAtAnchor(self):
        """
        Saves the current position to be used for selection start using
        the anchor as the selection start.
        """
        if len(self.ctrl.GetSelectedText()) > 0:
            self._anchor = self.ctrl.GetAnchor()
        else:
            self._anchor = self.ctrl.GetCurrentPos()

    def SwitchSelection(self, com_type=0):
        """
        Goes to the other end of the selected text (switches the cursor and
        anchor positions)
        """
        anchor = self._anchor
        self._anchor = self.ctrl.GetCurrentPos()

        if self.SelectionIsForward():
            self._anchor = self._anchor - 1
            anchor = anchor - 1
        else:
            self._anchor = self._anchor + 1
            anchor = anchor - 1

        self.ctrl.GotoPos(anchor)
        self.SelectSelection(2)

    def SelectionIsForward(self):
        """
        Check what direction the selection is going in.

        @return True if anchor is behind current position

        """
        return self.ctrl.GetCurrentPos() > self.ctrl.GetSelectionStart()


    def SelectSelection(self, com_type=0):
        if com_type < 1:
            print("Select selection called incorrectly", inspect.getframeinfo(inspect.currentframe().f_back)[2])

            return

        current_pos = self.ctrl.GetCurrentPos()

        if current_pos > self._anchor:
            self.ctrl.SetSelectionStart(self._anchor)
            self.ctrl.SetSelectionEnd(current_pos)
        else:
            self.ctrl.SetAnchor(self._anchor)

        #self.SetSelMode(u"LINE")
        if self.GetSelMode() == "LINE":
            self.SelectFullLines()
        # Inclusive motion commands select the last character as well
        elif com_type != 2:
            self.ctrl.CharRightExtend()

    def SelectionOnSingleLine(self):
        """
        Assume that if an EOL char is present we have mutiple lines
        """
        if self.ctrl.GetEOLChar() in self.ctrl.GetSelectedText():
            return False
        else:
            return True

    #def ExtendSelectionIfRequired(self):
    #    """
    #    If selection is positive the last character is not actually
    #    selected and so a correction must be applied
    #    """
    #    start, end = self._GetSelectionRange()
    #    if self.ctrl.GetCurrentPos() == end:
    #        self.ctrl.CharRightExtend()
    #    return start

    def DeleteSelectionLines(self, yank=True):
        self.SelectFullLines(include_eol=True)
        self.DeleteSelection(yank)

    def DeleteSelection(self, yank=True):
        """Yank selection and delete it"""
        self.BeginUndo(use_start_pos=True)

        # Hack so that when deleting blocks that consit of entire lines
        # the eol char is copied as well (allows pasting of line block)
        self.SelectEOLCharIfRequired()

        if yank:
            self.YankSelection()

        self.ctrl.Clear()

        self.EndUndo()
        self.LeaveVisualMode()
        self.SetLineColumnPos()

    def _GetSelectionRange(self):
        """
        Get the range of selection such that the start is the visual start
        of the selection, not the logical start.

        """
        start, end = self.minmax(self.ctrl.GetSelectionStart(),
                            self.ctrl.GetSelectionEnd())
        return start, end

    #def _GetSelectedLines(self):
    #    # why exclusive?
    #    """Get the first and last line (exclusive) of selection"""
    #    start, end = self._GetSelectionRange()
    #    start_line, end_line = (self.ctrl.LineFromPosition(start),
    #                            self.ctrl.LineFromPosition(end - 1)+ 1)
    #    return start_line, end_line
    def _GetSelectedLines(self, exclusive=False):
        """Get the first and last line of selection"""
        start, end = self._GetSelectionRange()

        if exclusive:
            end -= 1

        start_line, end_line = (self.ctrl.LineFromPosition(start),
                                self.ctrl.LineFromPosition(end) + 1)
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

    def SelectLines(self, start, end, reverse=False, include_eol=False):
        """
        Selects lines

        @param start: start line
        @param end: end line
        @param reverse: if true selection is reversed
        """
        start = max(start, 0)
        max_line_count = self.ctrl.GetLineCount()
        end = min(end, max_line_count)

        start_pos = self.GetLineStartPos(start)
        end_pos = self.ctrl.GetLineEndPosition(end)

        if include_eol or end == max_line_count:
            end_pos += 1


        if reverse:
            self.ctrl.GotoPos(start_pos)
            self.ctrl.SetAnchor(end_pos)
        else:
            self.ctrl.SetSelection(start_pos, end_pos)


    def PreUppercase(self):
        """Convert selected text to uppercase"""
        start = self.ctrl.GetSelectionStart()
        self.BeginUndo(use_start_pos=True)
        self.ctrl.ReplaceSelection(self.ctrl.GetSelectedText().upper())
        self.ctrl.GotoPos(start)
        self.EndUndo()

    def PreLowercase(self):
        """Convert selected text to lowercase"""
        start = self.ctrl.GetSelectionStart()
        self.BeginUndo(use_start_pos=True)
        self.ctrl.ReplaceSelection(self.ctrl.GetSelectedText().lower())
        self.ctrl.GotoPos(start)
        self.EndUndo()

    def SubscriptMotion(self):
        start = self.ctrl.GetSelectionStart()
        self.BeginUndo(use_start_pos=True)
        self.ctrl.ReplaceSelection("<sub>{0}</sub>".format(self.ctrl.GetSelectedText()))
        self.ctrl.GotoPos(start)
        self.EndUndo()

    def SuperscriptMotion(self):
        start = self.ctrl.GetSelectionStart()
        self.BeginUndo(use_start_pos=True)
        self.ctrl.ReplaceSelection("<sup>{0}</sup>".format(self.ctrl.GetSelectedText()))
        self.ctrl.GotoPos(start)
        self.EndUndo()

    def CreateShortHint(self):
        """Add short hint template"""
        self.BeginUndo()
        self.ctrl.AddText('[short_hint:""]')
        self.ctrl.CharLeft()
        self.ctrl.CharLeft()
        self.EndUndo()

    def SetHeading(self, code):
        # TODO: make more vim-like (multiple line support)
        try:
            level = int(self.GetCharFromCode(code))
        except ValueError:
            self.visualBell("RED")
            return

        self.BeginUndo()
        self.SelectCurrentLine()

        # Check if heading needs line padding above
        # NOTE: fails if whitespace on line above
        extra = ""
        if self.settings["blank_line_above_headings"]:
            start = self.ctrl.GetSelectionStart()
            if self.GetUnichrAt(start-2) != self.ctrl.GetEOLChar():
                extra = self.ctrl.GetEOLChar()

        line = self.ctrl.GetSelectedText()

        if line.lstrip().startswith("* "):
            line = line.lstrip().lstrip("* ")

        # The heading still has its EOL character present
        if self.settings["strip_headings"]:
            if line[0] == "*" and line[-2] == "*":
                line = line[1:-2] + line[-1]
            if line[0] == "_" and line[-2] == "_":
                line = line[1:-2] + line[-1]


        new_line = "".join([extra, level * "+", self.ctrl.vi.settings["pad_headings"] * " ", line.lstrip("+")])
        self.ctrl.ReplaceSelection(new_line)


        self.EndUndo()
        self.MoveCaretUp(1)

    def SwapCase(self):
        """
        Swap case of selected text. If no text selected swap case of
        character under caret.
        """
        self.BeginUndo(force=True)
        text = self.ctrl.GetSelectedText()
        if len(text) < 1:
            self.StartSelection()
            self.MoveCaretRight(allow_last_char=True)
            self.SelectSelection(2)
            text = self.ctrl.GetSelectedText()
        self.ctrl.ReplaceSelection(text.swapcase())
        self.EndUndo()

    def SelectionToSubscript(self):
        """Surround selected text with <sub> </sub> tags"""
        self.BeginUndo(force=True)
        #self.ExtendSelectionIfRequired()
        self.ctrl.ReplaceSelection("<sub>{0}</sub>".format(
                self.ctrl.GetSelectedText()))
        self.RemoveSelection()
        self.EndUndo()

    def SelectionToSuperscript(self):
        """Surround selected text with <sup> </sup> tags"""
        self.BeginUndo(force=True)
        #self.ExtendSelectionIfRequired()
        self.ctrl.ReplaceSelection("<sup>{0}</sup>".format(
                self.ctrl.GetSelectedText()))
        self.RemoveSelection()
        self.EndUndo()

    def SelectionToUpperCase(self):
        self.BeginUndo(force=True)
        #self.ExtendSelectionIfRequired()
        self.ctrl.ReplaceSelection(self.ctrl.GetSelectedText().upper())
        self.RemoveSelection()
        self.EndUndo()

    def SelectionToLowerCase(self):
        self.BeginUndo(force=True)
        #self.ExtendSelectionIfRequired()
        self.ctrl.ReplaceSelection(self.ctrl.GetSelectedText().lower())
        self.RemoveSelection()
        self.EndUndo()

    def Indent(self, forward=True, repeat=1, visual=False):
        # TODO: fix - call SelectSelection?
        if visual == True:
            repeat = self.count

        self.BeginUndo(force=True)
        # If no selected text we work on lines as specified by count
        if not self.HasSelection():
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
        first_visible_line = self.GetFirstVisibleLine()

        n = current - first_visible_line

        return n / float(lines)

    def _ScrollViewportByLines(self, n):
        # TODO: should not always move cursor position
        first_visible_line = self.GetFirstVisibleLine()
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
    #def SetSelMode(self, mode):
    #    if mode == "LINE":
    #        self.ctrl.SetSelectionMode(wx.stc.STC_SEL_LINES)
    #    else:
    #        self.ctrl.SetSelectionMode(wx.stc.STC_SEL_STREAM)

    def EnterBlockVisualMode(self):
        pass

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
        if self.mode != ViHelper.VISUAL:
            self.SetMode(ViHelper.VISUAL)
            self.StartSelectionAtAnchor()

    def LeaveVisualMode(self):
        """Helper function to end visual mode"""
        if self.mode == ViHelper.VISUAL:
            self.ctrl.GotoPos(self.ctrl.GetSelectionStart())
            self.SetSelMode("NORMAL")
            self.SetMode(ViHelper.NORMAL)

    def EnterVisualMode(self, mouse=False):
        """
        Change to visual (selection) mode

        Will do nothing if already in visual mode

        @param mouse: Visual mode was started by mouse action

        """
        if self.mode == ViHelper.INSERT:
            self.EndInsertMode()
        if self.mode != ViHelper.VISUAL:
            self.SetMode(ViHelper.VISUAL)


            if not mouse:
                self.StartSelectionAtAnchor()

            else:
                pos = self.ctrl.GetSelectionStart() \
                        + self.ctrl.GetSelectionEnd() \
                        - self.ctrl.GetCurrentPos()
                self.StartSelection(pos)


    #--------------------------------------------------------------------
    # Searching
    #--------------------------------------------------------------------
    def SearchForwardsForChar(self, search_char, count=None,
                                    wrap_lines=True, start_offset=0):
        """
        Search for "char".

        Note:
        Position is incorrect if search_char is unicode (and there are unicode
        strings in the document text)

        """
        if count is None: count = self.count
        pos = start_pos = self.ctrl.GetCurrentPos() + start_offset

        text = self.ctrl.GetTextRaw()
        #text_to_search = text[pos:]

        n = 0
        for i in range(count):
            pos = text.find(search_char.encode(), pos + 1)
            
        if pos > -1:
            if not wrap_lines:

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

        Cursor is positioned at the start of the text if found

        @param search_char: Character to search for.
        @param count: Number of characeters to find.
        @param wrap_lines: Should search occur on multiple lines.
        @param start_offset: Start offset for searching. Should be
            zero if character under the caret should be included in
            the search, -1 if not.

        @rtype: bool
        @return: True if successful, False if not.

        Note:
        Position is incorrect if search_char is unicode (and there are unicode
        strings in the document text)

        """
        if count is None: count = self.count
        pos = start_pos = self.ctrl.GetCurrentPos() + start_offset

        text = self.ctrl.GetTextRaw()
        text_to_search = text[:pos+1]
        for i in range(count):
            pos = text_to_search.rfind(search_char.encode())
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
            return False

        start_pos = self.ctrl.GetCurrentPos()
        if forward:
            text = self.ctrl.GetTextRaw()[start_pos+1:]
        else:
            text = self.ctrl.GetTextRaw()[0:start_pos:][::-1]
        brace_count = 1
        pos = -1

        search_brace = b[brace]

        brace_length = len(search_brace)

        # It is probably unnecessary to convert to bytes, but it will
        # prevent any unicode warnings that may otherwise occur
        brace_bytes = brace.encode()
        search_brace_bytes = search_brace.encode()
        for j in range(len(text)-brace_length + 1):
            i = text[j:j+brace_length]
            if i == brace_bytes:
                brace_count += 1
            elif i == search_brace_bytes:
                brace_count -= 1

            # brace_count will be 0 when we have found our matching brace
            if brace_count < 1:
                if forward:
                    pos = start_pos + j + len(search_brace)
                else:
                    pos = start_pos - j - len(search_brace)
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
        char = self.GetCharFromCode(code)
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
            self.SetLineColumnPos()
            return True

        return False

    def FindNextChar(self, keycode):
        return self.FindChar(keycode, count=self.count)

    def FindNextCharBackwards(self, keycode):
        return self.FindChar(keycode, count=self.count, reverse=True)

    def FindUpToNextChar(self, keycode):
        return self.FindChar(keycode, count=self.count, offset=-1)

    def FindUpToNextCharBackwards(self, keycode):
        return self.FindChar(keycode, count=self.count, reverse=True, offset=-1)

    def GetLastFindCharCmd(self):
        return self.last_find_cmd

    def RepeatLastFindCharCmd(self):
        args = self.GetLastFindCharCmd()
        if args is not None:
            # Set the new count
            args["count"] = self.count
            return self.FindChar(**args)

    def RepeatLastFindCharCmdReverse(self):
        args = self.GetLastFindCharCmd()
        if args is not None:
            args["count"] = self.count
            args["reverse"] = not args["reverse"]
            self.FindChar(**args)
            args["reverse"] = not args["reverse"]

    def MatchBraceUnderCaret(self, brace=None):
        # TODO: << and >>
        if brace is None:
            return self.FindMatchingBrace(self.GetUnichrAt(
                                                self.ctrl.GetCurrentPos()))
        else:
            return self.FindMatchingBrace(brace)

    # TODO: vim like searching
    def _SearchText(self, text, forward=True, match_case=True, wrap=True,
            whole_word=True, regex=False, word_start=False, select_text=False,
                                            repeat_search=False):
        """
        Searches for next occurance of 'text'

        @param text: text to search for
        @param forward: if true searches forward in text, else
                        search in reverse
        @param match_case: should search be case sensitive?
        """

        if repeat_search:
            offset = 2 if forward else -1
            self.MoveCaretPos(offset)

        if not forward and self.HasSelection():
            self.ctrl.GotoPos(self.ctrl.GetSelectionEnd()+1)
        #elif forward:
        #    self.ctrl.CharRight()

        self.ctrl.SearchAnchor()
        self.AddJumpPosition(self.ctrl.GetCurrentPos() - len(text))

        search_cmd = self.ctrl.SearchNext if forward else self.ctrl.SearchPrev

        flags = 0

        if whole_word:
            flags = flags | wx.stc.STC_FIND_WHOLEWORD
        if match_case:
            flags = flags | wx.stc.STC_FIND_MATCHCASE
        if word_start:
            flags = flags | wx.stc.STC_FIND_WORDSTART

        if regex:
            flags = flags | wx.stc.STC_FIND_REGEXP

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
            if select_text:
                # Unicode conversion?
                self.ctrl.SetSelection(pos, pos + len(text))
            return True

        return False

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
        # this should probably be rewritten
        self.ctrl.CharRightExtend()
        #self.ExtendSelectionIfRequired()
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


    #--------------------------------------------------------------------
    # Replace
    #--------------------------------------------------------------------
    def StartReplaceOnSelection(self):
        """
        Starts a search and replace cmd using the currently selected text
        """
        if not self.HasSelection():
            return

        text = self.ctrl.GetSelectedText()

        # \V is used as we want a direct text replace
        self.StartCmdInput("%s/\V{0}/".format(text))

    def ReplaceChar(self, keycode):
        """
        Replaces character under caret

        Contains some custom code to allow repeating
        """
        # TODO: visual indication
        try:
            char = chr(keycode)
        except:
            return

        selected_text_len = None
        # If in visual mode use the seletion we have (not the count)
        if self.mode == ViHelper.VISUAL:
            sel_start, sel_end = self._GetSelectionRange()
            count = sel_end - sel_start
            self.ctrl.GotoPos(sel_start)
            selected_text_len = count
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

        self.last_cmd = \
                [3, keycode, count, None, None, None, selected_text_len]

        self.BeginUndo(use_start_pos=True, force=True)
        self.StartSelection()
        # Use movecaretright so it works correctly with unicode characters
        #self.ctrl.GotoPos(self.ctrl.GetCurrentPos()+count)
        #self.DeleteRight()
        #self.ctrl.CharRight()
        self.MoveCaretRight(allow_last_char=True)
        #self.EndDelete()
        self.SelectSelection(2)
        self.ctrl.ReplaceSelection(count * char)
        #self.Repeat(self.InsertText, arg=char)
        #if pos + count != line_length:
        #    self.MoveCaretPos(-1)

        self.ctrl.CharLeft()
        self.SetLineColumnPos()
        self.EndUndo()

    def StartReplaceMode(self):
        # TODO: visual indication
        self.BeginUndo(use_start_pos=True, force=True)
        self.SetMode(ViHelper.REPLACE)

    def EndReplaceMode(self):
        if self.mode == ViHelper.REPLACE:
            self.EndUndo()
            self.SetMode(ViHelper.NORMAL)

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

        self.ctrl.SetSelection(start, end + 1)

        self.YankSelection(yank_register=True)

        self.GotoSelectionStart()

    def YankSelection(self, lines=False, yank_register=False):
        """
        Copy the current selection to the clipboard

        Sets the currently selected register and either the yank ("0)
        or other number register depending on the value of yank_register
        """
        if lines:
            self.SelectFullLines()
            self.ctrl.CharRightExtend()
        elif self.GetSelMode() == "LINE":
            # Selection needs to be the correct way round
            start, end = self._GetSelectionRange()
            self.ctrl.SetSelection(start, end)

        self.SelectEOLCharIfRequired()

        #self.ctrl.Copy()
        text = self.ctrl.GetSelectedText()
        self.register.SetCurrentRegister(text, yank_register)

    def Yank(self, lines=False):
        self.YankSelection(lines, yank_register=True)
        self.GotoSelectionStart()

    def PutClipboard(self, before, count=None):
        self.register.SelectRegister("+")
        self.Put(before=False, count=count)

    def Put(self, before, count=None):
        count = count if count is not None else self.count
        #text = getTextFromClipboard()

        current_reg = self.register.GetSelectedRegister()
        text = self.register.GetCurrentRegister()

        #if text is None:
        #    self.visualBell("RED")
        #    return

        self.BeginUndo(True, force=True)

        # If its not text paste as normal for now
        if not text:
            self.ctrl.Paste()
            self.EndUndo()
            return

        # If the text to copy ends with an eol char we treat the text
        # as a line(s) (only for internal pastes)
        # TODO: fix for cross tab pasting
        is_line = False
        if current_reg != "+":
            eol = self.ctrl.GetEOLChar()
            eol_len = len(eol)
            if len(text) > eol_len:
                if text[-len(eol):] == eol:
                    is_line = True

        text_to_paste = count * text

        if self.HasSelection():
            if is_line:
                text_to_paste = "".join(["\n", text_to_paste])
            self.ctrl.ReplaceSelection(text_to_paste)
        else:
            if is_line:
                if not before:
                    # If pasting a line we have to goto the end before moving caret
                    # down to handle long lines correctly
                    #self.ctrl.LineEnd()
                    self.MoveCaretDown(1)
                self.GotoLineStart()
            else:
                if not before:
                    self.MoveCaretRight(allow_last_char=True)
                    #line_text, pos = self.ctrl.GetCurLine()
                    #if len(line_text) != pos + 1:
                    #    self.ctrl.CharRight()

            #self.Repeat(self.InsertText, arg=text)
            self.InsertText(text_to_paste)

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
        pos = self.ctrl.GetCurrentPos()
        if char in self.text_object_map:
            self.SelectInTextObject(char)
            self.ctrl.CharRightExtend()
            text = self.ctrl.GetSelectedText()
            self.ctrl.GotoPos(pos)
            self.SelectATextObject(char)
            self.ctrl.CharRightExtend()
            pos = self._GetSelectionRange()
            self.ctrl.ReplaceSelection(text)
            self.ctrl.GotoPos(pos[0])
            return ((pos[0], pos[0]+len(text)))
        return False

    def EndDelete(self):
        self.SelectSelection(2)
        self.DeleteSelection()
        self.CheckLineEnd()
        self.SetLineColumnPos()

    def EndDeleteInsert(self):
        self.BeginUndo(use_start_pos=True)
        self.SelectSelection(2)
        self.DeleteSelection()
        self.Insert()
        self.EndUndo()

    def DeleteRight(self):
        self.BeginUndo()
        self.StartSelection()
        self.MoveCaretRight(allow_last_char=True)
        self.SelectSelection(2)

        ## If the selection len is less than the count we need to select
        ## the last character on the line
        #if len(self.ctrl.GetSelectedText()) < self.count:
        #    self.ctrl.CharRightExtend()
        self.DeleteSelection()
        self.EndUndo()
        self.CheckLineEnd()

    def DeleteLeft(self):
        self.BeginUndo(force=True)
        self.StartSelection()
        self.MoveCaretLeft()
        self.SelectSelection(2)
        self.DeleteSelection()
        self.CheckLineEnd()
        self.EndUndo()

    def DeleteRightAndInsert(self):
        self.BeginUndo(use_start_pos=True)
        self.DeleteRight()
        self.Insert()
        self.EndUndo()

    def DeleteLinesAndIndentInsert(self):
        self.BeginUndo(force=True)
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
    def GotoSelectionStart(self):
        if not self.HasSelection():
            return False

        self.ctrl.GotoPos(self.ctrl.GetSelectionStart())


    def GetLineStartPos(self, line):
        return self.ctrl.PositionFromLine(line)

        #if line == 0:
        #    return 0
        #return self.ctrl.GetLineIndentPosition(line) - \
        #                            self.ctrl.GetLineIndentation(line)

    def GotoLineStart(self):
        self.ctrl.Home()
        self.SetLineColumnPos()

    def GotoLineEnd(self, true_end=True):
        line, pos = self.ctrl.GetCurLine()
        if line == self.ctrl.GetEOLChar():
            return

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
        self.SetLineColumnPos()

    def GotoColumn(self, pos=None, save_position=True):
        """
        Moves caret to "pos" on current line. If no pos specified use "count".

        @param pos: Column position to move caret to.
        """
        if pos is None: pos = self.count
        line = self.ctrl.GetCurrentLine()

        line_text = self.ctrl.GetLine(line)
        if len(line_text) < 2:
            return

        lstart = self.ctrl.PositionFromLine(line)

        # Use CharRight for correct handling of unicode chars
        self.MoveCaretPos(pos, allow_last_char=False, save_column_pos=False)
        #lend = self.ctrl.GetLineEndPosition(line)
        #line_len = lend - lstart
        #column = min(line_len, pos)
        #self.ctrl.GotoPos(lstart + column)

        if save_position:
            self.SetLineColumnPos()

    def GotoSentenceStart(self, count=None, save_jump_pos=False):
        if save_jump_pos:
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

        text = self.ctrl.GetTextRaw()[:pos]

        n = -1
        for i in self.SENTENCE_ENDINGS:
            index = text.rfind(i.encode())
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
                if pos == page_length:
                    break
        if forward_char in string.whitespace:
            while forward_char in string.whitespace:
                pos += 1
                forward_char = self.GetUnichrAt(pos)
                if pos == page_length:
                    break
        else:
            self._MoveCaretSentenceStart(pos-1, start_pos)
            return

        if start_pos >= pos:
            self.ctrl.GotoPos(pos)
        else:
            self._MoveCaretSentenceStart(sentence_end_pos-1, start_pos)

    def GotoNextSentence(self, count=None, save_jump_pos=False):
        if save_jump_pos:
            self.AddJumpPosition()
        self.Repeat(self._MoveCaretNextSentence, count)

    def GotoSentenceEnd(self, count=None, save_jump_pos=False):
        if save_jump_pos:
            self.AddJumpPosition()
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

        text = self.ctrl.GetTextRaw()[pos:]

        n = page_length
        for i in self.SENTENCE_ENDINGS:
            index = text.find(i.encode())
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
                if pos == page_length:
                    break
            sentence_end_pos = pos-1
        if forward_char in string.whitespace:
            while forward_char in string.whitespace:
                pos += 1
                forward_char = self.GetUnichrAt(pos)
                if pos == page_length:
                    break
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

    def MoveCaretRight(self, allow_last_char=True):
        self.MoveCaretPos(self.count, allow_last_char=allow_last_char)

    def MoveCaretVertically(self, count):
        line_no = self.ctrl.GetCurrentLine()

        self.ctrl.GotoPos(self.ctrl.PositionFromLine(line_no + count))
        self.GotoColumn(self.GetLineColumnPos(), save_position=False)

    def MoveCaretUp(self, count=None, visual=False):
        if count is None: count = self.count

        if visual:
            self.Repeat(self.ctrl.LineUp, count)
            self.CheckLineEnd()
            #self.SetLineColumnPos()
        else:
            self.MoveCaretVertically(-count)

    def MoveCaretDown(self, count=None, visual=False):
        """
        Moves caret down

        @param visual: If False ignore linewrap
        """
        if count is None: count = self.count

        if visual:
            self.Repeat(self.ctrl.LineDown, count)
            self.CheckLineEnd()
            #self.SetLineColumnPos()
        else:
            self.MoveCaretVertically(count)

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
        #self.Repeat(self.ctrl.LineDown, count)
        self.MoveCaretDown()
        self.GotoLineIndent()

    def MoveCaretLeft(self):
        self.MoveCaretPos(-self.count)

    def MoveCaretPos(self, offset, allow_last_char=False, save_column_pos=True):
        """
        Move caret by a given offset along the current line.

        """
        line, line_pos = self.ctrl.GetCurLine()
        line_no = self.ctrl.GetCurrentLine()

        rawline = line.encode()

        # Last line doesn't have an EOL char which the code below requires
        if self.OnLastLine():
            line = line + self.ctrl.GetEOLChar()

        end_offset = 1

        if not allow_last_char and len(line) > 2:
            end_offset = end_offset + len(line[-2].encode())

        if offset > 0:
            if line_pos + end_offset == len(rawline):
                return
            bytes_to_move = len(line.encode()[line_pos:-end_offset].decode()[:offset].encode())
        elif offset < 0:
            if line_pos == 0:
                return
            bytes_to_move = -len(line.encode()[:line_pos].decode()[offset:].encode())
        else:
            # Offset is 0, do nothing
            return

        self.ctrl.GotoPos(self.ctrl.GetCurrentPos() + bytes_to_move)

        if save_column_pos:
            self.SetLineColumnPos()

        return

# Code below is left as a reminder that trying to improve this function
# is probably more trouble than its worth.
#
#        pos = self.ctrl.GetCurrentPos()
#
#        if offset > 0:
#
#            end_offset = 0
#            if allow_last_char and len(line) > 2:
#                end_offset = len(bytes(line[-2]))
#
#            line_end = self.ctrl.GetLineEndPosition(line_no)
#
#            if pos + offset >= line_end + end_offset:
#                self.ctrl.GotoPos(line_end - 1)
#            else:
#                self.ctrl.GotoPos(pos + offset + end_offset)
#
#        else:
#            line_start = self.ctrl.PositionFromLine(line_no)
#
#            if pos + offset < line_start:
#                self.ctrl.GotoPos(line_start)
#            else:
#                self.ctrl.GotoPos(pos + offset)
#
#        if save_column_pos:
#            self.SetLineColumnPos()
#
#        return
#
#
#        # The code below works but is slower than the above implementation (i think)
#
#        # TODO: Speedup
#        line, line_pos = self.ctrl.GetCurLine()
#        line_no = self.ctrl.GetCurrentLine()
#
#        if self.mode == ViHelper.VISUAL:
#            if offset > 0:
#                move_right = True
#                move = self.ctrl.CharRightExtend
#                stop_pos = self.GetLineStartPos(line_no) + \
#                                self.ctrl.LineLength(line_no)-1
#            else:
#                move_right = False
#                move = self.ctrl.CharLeftExtend
#                stop_pos = self.GetLineStartPos(line_no)
#        else:
#            if offset > 0:
#                move_right = True
#                move = self.ctrl.CharRight
#                stop_pos = self.GetLineStartPos(line_no) + \
#                                self.ctrl.LineLength(line_no)-2
#
#                # Fix for last line (no EOL char present)
#                if line_no+1 == self.ctrl.GetLineCount():
#                    stop_pos += 1
#            else:
#                move_right = False
#                move = self.ctrl.CharLeft
#                stop_pos = self.GetLineStartPos(line_no)
#
#        if allow_last_char:
#            stop_pos += 1
#
#        for i in range(abs(offset)):
#            if (move_right and self.ctrl.GetCurrentPos() < stop_pos) or \
#               (not move_right and self.ctrl.GetCurrentPos() > stop_pos):
#                move()
#            else:
#                break
#
#        if save_column_pos:
#            self.SetLineColumnPos()
#
#        ## The code below is faster but does not handle
#        ## unicode charcters nicely
#        #line, line_pos = self.ctrl.GetCurLine()
#        #line_no = self.ctrl.GetCurrentLine()
#        #pos = max(line_pos + offset, 0)
#        #if self.mode == ViHelper.VISUAL:
#        #    pos = min(pos, self.ctrl.LineLength(line_no)-1)
#        #else:
#        #    pos = min(pos, self.ctrl.LineLength(line_no)-2)
#        #self.ctrl.GotoPos(self.GetLineStartPos(line_no) + pos)
#        #self.SetLineColumnPos()

    def MoveCaretLinePos(self, offset):
        """
        Move caret line position by a given offset

        Faster but does not maintain line position
        """
        self.SetLineColumnPos()
        line = max(self.ctrl.GetCurrentLine() + offset, 0)
        line = min(line, self.ctrl.GetLineCount())
        self.ctrl.GotoLine(line)
        line_start_pos = self.ctrl.GetCurrentPos()

        pos = max(index, 0)
        pos = min(pos, self.ctrl.GetLineEndPosition(line)-line_start_pos)
        self.ctrl.GotoPos(line_start_pos+pos)
        #self.SetLineColumnPos()

    def MoveCaretToLinePos(self, line, index):
        line = max(line, 0)
        line = min(line, self.ctrl.GetLineCount())
        self.ctrl.GotoLine(line)
        line_start_pos = self.ctrl.GetCurrentPos()
        pos = max(index, 0)
        pos = min(pos, self.ctrl.GetLineEndPosition(line)-line_start_pos)
        self.ctrl.GotoPos(line_start_pos+pos)

# word-motions
    def MoveCaretWordEndCountWhitespace(self, count=None):
        self.Repeat(self._MoveCaretWord, count,
                        { "recursion" : False, "count_whitespace" : True, \
                                    "only_whitespace" : False })

    def MoveCaretNextWord(self, count=None):
        # TODO: should probably use _MoveCaretWord
        self.Repeat(self.ctrl.WordRight, count)
        self.SetLineColumnPos()

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

        # At the end of the file
        # TODO: check what this does in p3
        if char is None:
            self.ctrl.CharLeft()
            self.SetLineColumnPos()
            return

        text_length = self.ctrl.GetTextLength() - 1


        if reverse:
            offset = -1
            move = self.ctrl.CharLeft
            move_extend = self.ctrl.CharLeftExtend
        else:
            if pos >= text_length:
                # Already at end of the text - nothing to do
                return
            offset = 1
            move = self.ctrl.CharRight
            move_extend = self.ctrl.CharRightExtend

        # If the current char is whitespace we either skip it or count
        # it depending on "count_whitespace"
        if char in string.whitespace:
            char = self.GetUnichrAt(pos + offset)
            if char is not None:
                while char is not None and char in string.whitespace \
                        and pos < text_length:
                    pos = pos + offset * len(char.encode())
                    char = self.GetUnichrAt(pos + offset)
            if not count_whitespace:
                self.GotoPosAndSave(pos)
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
                while char is not None and char in self.WORD_BREAK \
                        and pos < text_length:
                    pos = pos + offset * len(char.encode())
                    char = self.GetUnichrAt(pos + offset)
        # Else offset forwards to first punctuation or whitespace char
        # (or just whitespace char if only_whitespace = True)
        else:
            char = self.GetUnichrAt(pos + offset)
            if char is not None:
                while char is not None and \
                        (((only_whitespace or char not in self.WORD_BREAK) and \
                        char not in string.whitespace) \
                        or char in ("_")) \
                        and pos < text_length:
                    pos = pos + offset * len(char.encode())
                    char = self.GetUnichrAt(pos + offset)

        # We need to correct the position if using a unicode character
        if len(char) > 2:
            pos = self.ctrl.PositionAfter(pos)

        if pos != start_pos or recursion:
            self.GotoPosAndSave(pos)
        else:
            move_extend()
            self._MoveCaretWord(True, count_whitespace=count_whitespace,
                        only_whitespace=only_whitespace, reverse=reverse)
            return

        self.SetLineColumnPos()

    def MoveCaretToWhitespaceStart(self):
        start = self.ctrl.GetCurrentPos()
        while start > 0 and \
                self.ctrl.GetCharAt(start-1) in self.SINGLE_LINE_WHITESPACE:
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
            text_length = self.ctrl.GetLength()
            self.ctrl.WordRight()
            while self.GetChar(-1) and not self.GetChar(-1).isspace():
                if self.ctrl.GetCurrentPos() == text_length:
                    return
                self.ctrl.WordRight()
        self.Repeat(func, count)
        self.SetLineColumnPos()

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
        self.ctrl.CharLeft()

    def MoveCaretParaDown(self, count=None):
        # TODO: headings as paragraphs?
        self.AddJumpPosition()
        self.ctrl.CharRight()
        self.Repeat(self.ctrl.ParaDown, count)
        self.ctrl.CharLeft()

    def GotoPosAndSave(self, pos):
        """
        Helper for GotoPos. Saves current position.
        """
        self.ctrl.GotoPos(pos)
        self.SetLineColumnPos()

    def GotoVisualLineStart(self):
        """
        Move caret to start of the visual line
        """
        self.ctrl.HomeDisplay()

    def GotoVisualLineEnd(self):
        """
        Move caret to end of the visual line
        """
        self.ctrl.LineEndDisplay()

    def DocumentNavigation(self, key):
        """
        It may be better to seperate this into multiple functions
        """
        k = self.KEY_BINDINGS
        if key in [k["G"], (k["g"], k["g"]), k["%"]]:
            self.AddJumpPosition()

        # %, G or gg
        if self.true_count:
            if key in [k["G"], (k["g"], k["g"])]:
                # Correct for line 0
                self.MoveCaretToLinePos(
                        self.count-1, self.ctrl.GetCurLine()[1])
            elif key == k["%"]: # %
                max_lines = self.ctrl.GetLineCount()
                # Same as   int(self.count / 100 * max_lines)  but needs only
                #   integer arithmetic
                line_percentage = (self.count * max_lines) // 100
                self.MoveCaretToLinePos(
                                line_percentage, self.ctrl.GetCurLine()[1])

        elif key == k["%"]:
            # If key is % but no count it is used for brace matching
            self.MatchBraceUnderCaret()

        elif key == (k["g"], k["g"]):
            self.ctrl.GotoLine(0)

        elif key == (k["G"]):
            # As with vim "G" goes to the first nonwhitespace of the
            # character on the bottom line
            self.GotoLineIndent(self.ctrl.GetLineCount())

    def GotoViewportTop(self):
        self.GotoLineIndent(self.GetFirstVisibleLine())

    def GotoViewportMiddle(self):
        self.GotoLineIndent(self.GetMiddleVisibleLine())

    def GotoViewportBottom(self):
        self.GotoLineIndent(self.GetLastVisibleLine())

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

#    def ScrollViewportLineDown(self):
#        self._ScrollViewportByLines(1)
#
#    def ScrollViewportLineUp(self):
#        self._ScrollViewportByLines(-1)

    # TODO: FIX UNDO / REDO
    def CanUndo(self):
        return not self._undo_pos < 0

    def CanRedo(self):
        return not self._undo_pos > len(self._undo_positions)

    def Undo(self, count=None):
        if self.CanUndo():
            self.visualBell("GREEN")
            self.Repeat(self._Undo, count)
        else:
            self.visualBell("RED")

    def Redo(self, count=None):
        if self.CanRedo():
            self.visualBell("GREEN")
            self.Repeat(self._Redo, count)
        else:
            self.visualBell("RED")

# The following commands are basic ways to enter insert mode
    def Insert(self):
        self.BeginUndo(use_start_pos=True)
        self.SetMode(ViHelper.INSERT)

    def Append(self):
        if self.ctrl.GetCurrentPos() != self.ctrl.GetLineEndPosition(
                                                self.ctrl.GetCurrentLine()):
            self.ctrl.CharRight()
        self.Insert()

    def InsertAtLineStart(self):
        # Goto line places the caret at the start of the line
        self.GotoLineIndent(self.ctrl.GetCurrentLine())
        self.SetLineColumnPos()
        self.Insert()

    def AppendAtLineEnd(self):
        self.ctrl.GotoPos(self.ctrl.GetLineEndPosition(
                                    self.ctrl.GetCurrentLine()))
        self.Append()

    def OpenNewLine(self, above, indent=None):
        self.BeginUndo(True)

        # Set to True if opening a line above the first line.
        create_first_line = False

        if indent is None:
            indent = self.ctrl.GetLineIndentation(self.ctrl.GetCurrentLine())

        # This code is independent of the wikidpad syntax used
        line_prefix = False
        line_text = self.ctrl.GetCurLine()[0].strip()
        if line_text.startswith("* "):
            line_prefix = "* "

        if above:
            if self.ctrl.GetCurrentLine() == 0:
                create_first_line = True
            self.MoveCaretUp(1)
        if create_first_line:
            self.GotoLineStart()
        else:
            self.GotoLineEnd()
        self.ctrl.AddText(self.ctrl.GetEOLChar())
        if line_prefix:
            self.ctrl.AddText(line_prefix)

        if create_first_line:
            self.MoveCaretUp(1)
        self.ctrl.SetLineIndentation(self.ctrl.GetCurrentLine(), indent)
        self.AppendAtLineEnd()
        self.EndUndo()

    def TruncateLine(self, check_line_end=True):
        text, pos = self.ctrl.GetCurLine()

        # If line is empty do nothing (blank line has eol char)
        if len(text) < 2:
            return

        self.ctrl.LineEndExtend()
        self.ctrl.CharLeftExtend()
        self.ctrl.CharRightExtend()
        #self.ExtendSelectionIfRequired()
        self.DeleteSelection()
        ## replace with function
        #if self.mode == ViHelper.INSERT:
        if check_line_end:
            self.CheckLineEnd()

    def TruncateLineAndInsert(self):
        self.TruncateLine(check_line_end=False)
        self.Insert()


    def GetLinkAtCaret(self, link_type=("rel://", "abs://"), extensions=""):
        """
        Helper for checking if the caret is currently within a link
        """
        pos = self.ctrl.GetCurrentPos()
        # First check if we are working with a link

        self.SelectInWORD()
        self.ctrl.CharRightExtend()
        link = self.ctrl.GetSelectedText()

        self.RemoveSelection(pos)

        if link.startswith(link_type) and link.endswith(extensions):
            return link

        return None

class PositionDoesNotExist(Exception):
    """Raised when attempting to access an position out of range"""
