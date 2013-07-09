# -*- coding: iso8859-1 -*-
from __future__ import with_statement

## import profilehooks
## profile = profilehooks.profile(filename="profile.prf", immediate=False)


import os, os.path, sys, gc, traceback, string, re, collections
from os.path import *
import time

import cPickle  # to create dependency?

import wx, wx.html

# import urllib_red as urllib
# import urllib

from .wxHelper import GUI_ID, clearMenu, ProgressHandler, TopLevelLocker, \
        WindowUpdateLocker
from . import wxHelper

from . import TextTree

from .MiscEvent import MiscEventSourceMixin, ProxyMiscEvent  # , DebugSimple

from WikiExceptions import *
from Consts import HOMEPAGE

from . import Utilities
from . import SystemInfo
from .WindowLayout import WindowSashLayouter, setWindowPos, setWindowSize
from . import WindowLayout

from .wikidata import DbBackendUtils, WikiDataManager

# To generate py2exe dependency
from . import WikiDocument

from . import OsAbstract

from . import DocPages

from .PWikiNonCore import PWikiNonCore

from .CmdLineAction import CmdLineAction
from .WikiTxtCtrl import WikiTxtCtrl, FOLD_MENU
from .WikiTreeCtrl import WikiTreeCtrl
from .WikiHtmlView import createWikiHtmlView

from .MainAreaPanel import MainAreaPanel
from .UserActionCoord import UserActionCoord
from .DocPagePresenter import DocPagePresenter

from .Ipc import EVT_REMOTE_COMMAND

from . import AttributeHandling, SpellChecker


from . import AdditionalDialogs


import StringOps
from StringOps import uniToGui, guiToUni, mbcsDec, mbcsEnc, \
        unescapeForIni, urlFromPathname, \
        strftimeUB, pathEnc, loadEntireFile, writeEntireFile, \
        pathWordAndAnchorToWikiUrl, relativeFilePath, pathnameFromUrl


from PluginManager import PluginAPIAggregation
import PluginManager


# TODO More abstract/platform independent
try:
    import WindowsHacks
except:
    if SystemInfo.isWindows():
        traceback.print_exc()
    WindowsHacks = None



class KeyBindingsCache:
    def __init__(self, kbModule):
        self.kbModule = kbModule
        self.accelPairCache = {}
        
    def __getattr__(self, attr):
        return getattr(self.kbModule, attr, u"")
    
    def get(self, attr, default=None):
        return getattr(self.kbModule, attr, None)

    def getAccelPair(self, attr):
        try:
            return self.accelPairCache[attr]
        except KeyError:
            ap = wxHelper.getAccelPairFromString("\t" + getattr(self, attr))
            self.accelPairCache[attr] = ap
            return ap

    def matchesAccelPair(self, attr, accP):
        return self.getAccelPair(attr) == accP


class LossyWikiCloseDeniedException(Exception):
    """
    Special exception thrown by PersonalWikiFrame.closeWiki() if user denied
    to close the wiki because it might lead to data loss
    """
    pass



def _buildChainedUpdateEventFct(chain):
    def evtFct(evt):
        evt.Enable(True)
        for fct in chain:
            fct(evt)
        
    return evtFct


# def _buildUpdateEventFctByEnableExpress(expr):
#     def evtFct(evt):
#         
#         
#         evt.Enable(True)
#         for fct in chain:
#             fct(evt)
#         
#     return evtFct


_StatusBarStackEntry = collections.namedtuple("_StatusBarStackEntry",
        ("msg, duration, key"))


class PersonalWikiFrame(wx.Frame, MiscEventSourceMixin):
    HOTKEY_ID_HIDESHOW_BYAPP = 1
    HOTKEY_ID_HIDESHOW_BYWIKI = 2

##     @profile
    def __init__(self, parent, id, title, wikiAppDir, globalConfigDir,
            globalConfigSubDir, cmdLineAction):
        # Do not use member variables starting with "externalPlugin_"! They
        # are reserved for external plugins.
        wx.Frame.__init__(self, parent, -1, title, size = (700, 550),
                         style=wx.DEFAULT_FRAME_STYLE|wx.NO_FULL_REPAINT_ON_RESIZE)
        MiscEventSourceMixin.__init__(self)

        if cmdLineAction.cmdLineError:
            cmdLineAction.showCmdLineUsage(self,
                    _(u"Bad formatted command line.") + u"\n\n")
            self.Close()
            self.Destroy()
            return

        self.mainWindowConstructed = False

#         if not globalConfigDir or not exists(globalConfigDir):
#             self.displayErrorMessage(
#                     u"Error initializing environment, couldn't locate "+
#                     u"global config directory", u"Shutting Down")
#             self.Close()


        # initialize some variables
        self.globalConfigDir = globalConfigDir
        self.wikiAppDir = wikiAppDir

        self.globalConfigSubDir = globalConfigSubDir

        # TODO: Move to MainApp
        # Create the "[TextBlocks].wiki" file in the global config subdirectory
        # if the file doesn't exist yet.
        tbLoc = os.path.join(self.globalConfigSubDir, "[TextBlocks].wiki")
        if not os.path.exists(pathEnc(tbLoc)):
            writeEntireFile(tbLoc, 
"""importance: high;a=[importance: high]\\n
importance: low;a=[importance: low]\\n
tree_position: 0;a=[tree_position: 0]\\n
wrap: 80;a=[wrap: 80]\\n
camelCaseWordsEnabled: false;a=[camelCaseWordsEnabled: false]\\n
""", True)
        self.configuration = wx.GetApp().createCombinedConfiguration()

        # Listen to application events
        wx.GetApp().getMiscEvent().addListener(self)
        
        self.wikiPadHelp = os.path.join(self.wikiAppDir, 'WikidPadHelp',
                'WikidPadHelp.wiki')
        self.windowLayouter = None  # will be set by initializeGui()

        # defaults
        self.wikiData = None
        self.wikiDataManager = None
        self.lastCursorPositionInPage = {}
        self.wikiHistory = []
        self.nonModalFindDlg = None  # Stores find&replace dialog, if present
        self.nonModalMainWwSearchDlg = None
        self.nonModalWwSearchDlgs = []   # Stores wiki wide search dialogs and detached fast search frames
        self.nonModalFileCleanupDlg = None  # Stores file dialog FileCleanup.FileCleanupDialog
        self.spellChkDlg = None  # Stores spell check dialog, if present
        self.printer = None  # Stores Printer object (initialized on demand)
        self.continuousExporter = None   # Exporter-derived object if continuous export is in effect
        self.statusBarStack = []  # Internal stack with statusbar information
        
        self.mainAreaPanel = None
        self.mainmenu = None

        self.recentWikisMenu = None
        self.recentWikisActivation = wxHelper.IdRecycler()

        self.textBlocksMenu = None
        self.textBlocksActivation = wxHelper.IdRecycler() # See self.fillTextBlocksMenu()

        self.favoriteWikisMenu = None
        self.favoriteWikisActivation = wxHelper.IdRecycler() 

        self.pluginsMenu = None
        self.fastSearchField = None   # Text field in toolbar
        
        self.cmdIdToIconNameForAttribute = None # Maps command id (=menu id) to icon name
                                    # needed for "Editor"->"Add icon attribute"
        self.cmdIdToColorNameForAttribute = None # Same for color names
        
        self.cmdIdToInsertString = None

        self.sleepMode = True
        self.eventRoundtrip = 0

        self.currentWikiDocumentProxyEvent = ProxyMiscEvent(self)
        self.currentWikiDocumentProxyEvent.addListener(self)

        self.configuration.setGlobalConfig(wx.GetApp().getGlobalConfig())

        # State here: Global configuration available

        self.loadFixedExtensions()
        
        self.nonCoreMenuItems = PWikiNonCore(self, self)

        # setup plugin manager and hooks API
#         dirs = ( os.path.join(self.globalConfigSubDir, u'user_extensions'),
#                 os.path.join(self.wikiAppDir, u'user_extensions'),
#                 os.path.join(self.wikiAppDir, u'extensions') )
        dirs = ( os.path.join(self.wikiAppDir, u'extensions'),
                os.path.join(self.wikiAppDir, u'user_extensions'),
                os.path.join(self.globalConfigSubDir, u'user_extensions') )
        self.pluginManager = PluginManager.PluginManager(dirs, systemDirIdx=0)

#         wx.GetApp().pauseBackgroundThreads()

        plm = self.pluginManager # Make it shorter

        pluginDummyFct = lambda module, *args, **kwargs: None

        self.hooks = PluginManager.PluginAPIAggregation(
                plm.registerSimplePluginAPI(("hooks", 2),
                    ["startup", "newWiki", "createdWiki", "openWiki",
                    "openedWiki", "openWikiWord", "newWikiWord",
                    "openedWikiWord", "savingWikiWord", "savedWikiWord",
                    "renamedWikiWord", "deletedWikiWord", "exit",
                    "closingWiki", "droppingWiki", "closedWiki"
                    ] ),

                plm.registerWrappedPluginAPI(("hooks", 1),
                    startup=None, newWiki=None, createdWiki=None,
                    openWiki=None, openedWiki=None, openWikiWord=None,
                    newWikiWord=None, openedWikiWord=None, savingWikiWor=None,
                    savedWikiWord=None, renamedWikiWord=None,
                    deletedWikiWord=None, exit=None,
                    closingWiki=pluginDummyFct, droppingWiki=pluginDummyFct,
                    closedWiki=pluginDummyFct
                    )
                )

        self.viPluginFunctions = plm.registerSimplePluginAPI(("ViFunctions",1), 
                                ("describeViFunctions",))

        # interfaces for menu and toolbar plugins
        self.menuFunctions = plm.registerSimplePluginAPI(("MenuFunctions",1), 
                                ("describeMenuItems",))
        
        self.toolbarFunctions = PluginManager.PluginAPIAggregation(
                plm.registerWrappedPluginAPI(("ToolbarFunctions",2),
                                describeToolbarItems="describeToolbarItemsV02"),
                plm.registerSimplePluginAPI(("ToolbarFunctions",1), 
                                ("describeToolbarItems",))
                )

        del plm

        self.pluginManager.loadPlugins([ u'KeyBindings.py',
                u'EvalLibrary.py' ] )


        self.attributeChecker = AttributeHandling.AttributeChecker(self)

#         self.configuration.setGlobalConfig(wx.GetApp().getGlobalConfig())

        # State here: Plugins loaded

        # trigger hook
        self.hooks.startup(self)

        # wiki history
        history = self.configuration.get("main", "wiki_history")
        if history:
            self.wikiHistory = history.split(u";")

        # clipboard catcher  
        if WindowsHacks is not None:
            self.clipboardInterceptor = WindowsHacks.ClipboardCatchIceptor(self)
            self.browserMoveInterceptor = WindowsHacks.BrowserMoveIceptor(self)

            self._interceptCollection = WindowsHacks.WinProcInterceptCollection(
                    (self.clipboardInterceptor, self.browserMoveInterceptor))
        else:
            self.browserMoveInterceptor = None
            self.clipboardInterceptor = OsAbstract.createClipboardInterceptor(self)
            self._interceptCollection = OsAbstract.createInterceptCollection(
                    (self.clipboardInterceptor,))

        if self._interceptCollection is not None:
            self._interceptCollection.start(self) # .GetHandle())

        # resize the window to the last position/size
        setWindowSize(self, (self.configuration.getint("main", "size_x", 200),
                self.configuration.getint("main", "size_y", 200)))
        setWindowPos(self, (self.configuration.getint("main", "pos_x", 10),
                self.configuration.getint("main", "pos_y", 10)))

        # Set the auto save timing
        self.autoSaveDelayAfterKeyPressed = self.configuration.getint(
                "main", "auto_save_delay_key_pressed")
        self.autoSaveDelayAfterDirty = self.configuration.getint(
                "main", "auto_save_delay_dirty")

        # get the position of the splitter
        self.lastSplitterPos = self.configuration.getint("main", "splitter_pos")
                
        # if a wiki to open wasn't passed in use the last_wiki from the global config
        self.cmdLineAction = cmdLineAction
        wikiToOpen = cmdLineAction.wikiToOpen
        wikiWordsToOpen = cmdLineAction.wikiWordsToOpen
        anchorToOpen = cmdLineAction.anchorToOpen

        if not wikiToOpen:
            wikiToOpen = self.configuration.get("main", "last_wiki")

        # Prepare accelerator translation before initializing GUI
        if self.configuration.getboolean("main", "menu_accels_kbdTranslate", False):
            self.translateMenuAccelerator = OsAbstract.translateAcceleratorByKbLayout
        else:
            self.translateMenuAccelerator = lambda x: x

        # initialize the GUI
        self.initializeGui()
        
        # Minimize on tray?
        self.tbIcon = None
        self.setShowOnTray()

        # windowmode:  0=normal, 1=maximized, 2=iconized, 3=maximized iconized(doesn't work)
        windowmode = self.configuration.getint("main", "windowmode")

        if windowmode & 1:
            self.Maximize(True)
        if windowmode & 2:
            self.Iconize(True)

        # Set app-bound hot key
        self.hotKeyDummyWindow = None
        self._refreshHotKeys()

        self.windowLayouter.layout()

        # State here: GUI construction finished, but frame is hidden yet

        # if a wiki to open is set, open it
        if wikiToOpen:
            if os.path.exists(pathEnc(wikiToOpen)):
#                tracer.runctx('self.openWiki(wikiToOpen, wikiWordsToOpen, anchorToOpen=anchorToOpen)', globals(), locals())
                self.openWiki(wikiToOpen, wikiWordsToOpen,
                        anchorToOpen=anchorToOpen,
                        lastTabsSubCtrls=cmdLineAction.lastTabsSubCtrls,
                        activeTabNo=cmdLineAction.activeTabNo)
#                 wx.GetApp().pauseBackgroundThreads()
            else:
                if cmdLineAction.wikiToOpen:
                    cmdLineAction.showCmdLineUsage(self,
                            _(u"Wiki doesn't exist: %s") % wikiToOpen + u"\n\n")
                    self.Close()
                    self.Destroy()
                    return

#                 self.statusBar.SetStatusText(
#                         uniToGui(_(u"Last wiki doesn't exist: %s") % wikiToOpen), 0)
                self.displayErrorMessage(
                        _(u"Wiki doesn't exist: %s") % wikiToOpen)

        # State here: Wiki opened (if possible), additional command line actions
        # not done yet.
        
        if cmdLineAction.rebuild == cmdLineAction.NOT_SET and \
                self.isWikiLoaded():
            cmdLineAction.rebuild = self.getConfig().getint("main",
                    "wiki_onOpen_rebuild", 0)

        cmdLineAction.actionBeforeShow(self)

        if cmdLineAction.exitFinally:
            self.exitWiki()
            return

        self.userActionCoord = UserActionCoord(self)
        self.userActionCoord.applyConfiguration()

        self.Show(True)

        EVT_REMOTE_COMMAND(self, self.OnRemoteCommand)

        # Inform that idle handlers and window-specific threads can now be started
        self.mainWindowConstructed = True
        self.fireMiscEventKeys(("constructed main window",))

#         finally:
#             wx.GetApp().resumeBackgroundThreads()


    def loadFixedExtensions(self):
#         self.wikidPadHooks = self.getExtension('WikidPadHooks', u'WikidPadHooks.py')
        self.keyBindings = KeyBindingsCache(
                self.getExtension('KeyBindings', u'KeyBindings.py'))
        self.evalLib = self.getExtension('EvalLibrary', u'EvalLibrary.py')
        self.presentationExt = self.getExtension('Presentation', u'Presentation.py')


    def getExtension(self, extensionName, fileName):
        extensionFileName = os.path.join(self.globalConfigSubDir,
                u'user_extensions', fileName)
        if os.path.exists(pathEnc(extensionFileName)):
            userUserExtension = loadEntireFile(extensionFileName, True)
        else:
            userUserExtension = None

        extensionFileName = os.path.join(self.wikiAppDir, 'user_extensions',
                fileName)
        if os.path.exists(pathEnc(extensionFileName)):
            userExtension = loadEntireFile(extensionFileName, True)
        else:
            userExtension = None

        extensionFileName = os.path.join(self.wikiAppDir, 'extensions', fileName)
        systemExtension = loadEntireFile(extensionFileName, True)

        return importCode(systemExtension, userExtension, userUserExtension,
                extensionName)


    def getCurrentWikiWord(self):
        docPage = self.getCurrentDocPage()
        if docPage is None or not isinstance(docPage,
                (DocPages.WikiPage, DocPages.AliasWikiPage)):
            return None
        return docPage.getWikiWord()

    def getCurrentDocPage(self):
        if self.getCurrentDocPagePresenter() is None:
            return None
        return self.getCurrentDocPagePresenter().getDocPage()

    def getActiveEditor(self):
        if self.getCurrentDocPagePresenter() is None:
            return None
        return self.getCurrentDocPagePresenter().getSubControl("textedit")

    def getMainAreaPanel(self):
        return self.mainAreaPanel
        
    def isMainWindowConstructed(self):
        return self.mainWindowConstructed

    def getCurrentDocPagePresenter(self):
        """
        Convenience function. If main area's current presenter is not a
        doc page presenter, None is returned.
        """
        if self.mainAreaPanel is None:
            return None

        presenter = self.mainAreaPanel.getCurrentPresenter()

        if not isinstance(presenter, DocPagePresenter):
            return None

        return presenter

    def getCurrentPresenterProxyEvent(self):
        """
        This ProxyMiscEvent resends any messsages from the currently
        active DocPagePresenter
        """
        return self.mainAreaPanel.getCurrentPresenterProxyEvent()

    def getCurrentWikiDocumentProxyEvent(self):
        """
        This ProxyMiscEvent resends any messsages from the currently
        active WikiDocument
        """
        return self.currentWikiDocumentProxyEvent

    def getWikiData(self):
        if self.wikiDataManager is None:
            return None

        return self.wikiDataManager.getWikiData()

    def getWikiDataManager(self):
        """
        Deprecated, use getWikiDocument() instead
        """
        return self.wikiDataManager

    def getWikiDocument(self):
        return self.wikiDataManager

    def isWikiLoaded(self):
        return self.getWikiDocument() is not None

    def getWikiConfigPath(self):
        if self.wikiDataManager is None:
            return None

        return self.wikiDataManager.getWikiConfigPath()
        
    def getWikiDefaultWikiLanguage(self):
        if self.wikiDataManager is None:
            # No wiki loaded, so take users default
            return wx.GetApp().getUserDefaultWikiLanguage()

        return self.wikiDataManager.getWikiDefaultWikiLanguage()

    def getCmdLineAction(self):
        return self.cmdLineAction

#     def getUserDefaultWikiLanguage(self):
#         """
#         Returns the internal name of the default wiki language of the user.
#         """
#         return wx.GetApp().getUserDefaultWikiLanguage()

    def getConfig(self):
        return self.configuration

    def getPresentationExt(self):
        return self.presentationExt

    def getCollator(self):
        return wx.GetApp().getCollator()

    def getLogWindow(self):
        return self.logWindow

    def getKeyBindings(self):
        return self.keyBindings
        
    def getClipboardInterceptor(self):
        return self.clipboardInterceptor

    def getUserActionCoord(self):
        return self.userActionCoord

    def lookupIcon(self, iconname):
        """
        Returns the bitmap object for the given iconname.
        If the bitmap wasn't cached already, it is loaded and created.
        If icon is unknown, None is returned.
        """
        return wx.GetApp().getIconCache().lookupIcon(iconname)

    def lookupSystemIcon(self, iconname):
        """
        Returns the bitmap object for the given iconname.
        If the bitmap wasn't cached already, it is loaded and created.
        If icon is unknown, an error message is shown and an empty
        black bitmap is returned.
        """
        icon = wx.GetApp().getIconCache().lookupIcon(iconname)
        if icon is None:
            icon = wx.EmptyBitmap(16, 16)
            self.displayErrorMessage(_(u'Error, icon "%s" missing.' % iconname))

        return icon


    def lookupIconIndex(self, iconname):
        """
        Returns the id number into self.iconImageList of the requested icon.
        If icon is unknown, -1 is returned.
        """
        return wx.GetApp().getIconCache().lookupIconIndex(iconname)


    def resolveIconDescriptor(self, desc, default=None):
        """
        Used for plugins of type "MenuFunctions" or "ToolbarFunctions".
        Tries to find and return an appropriate wx.Bitmap object.
        
        An icon descriptor can be one of the following:
            - None
            - a wx.Bitmap object
            - the filename of a bitmap
            - a tuple of filenames, first existing file is used
        
        If no bitmap can be found, default is returned instead.
        """
        return wx.GetApp().getIconCache().resolveIconDescriptor(desc, default)


    def _OnRoundtripEvent(self, evt):
        """
        Special event handler for events which must be handled by the
        window which has currently the focus (e.g. "copy to clipboard" which
        must be done by either editor or HTML preview).
        
        These events are sent further to the currently focused window.
        If they are not consumed they go up to the parent window until
        they are here again (make a "roundtrip").
        This function also avoids an infinite loop of such events.
        """
        target = None

        if self.eventRoundtrip < 1:
            # First try: Focused window
            target = wx.Window.FindFocus()

        if target is None and self.eventRoundtrip < 2:
            # Second try: Active DocPagePresenter
            presenter = self.getCurrentDocPagePresenter()
            if presenter is not None:
                subCtl = presenter.getCurrentSubControl()
                if subCtl is not None:
                    target = subCtl
                else:
                    target = presenter

                if target is wx.Window.FindFocus():
                    # No double-check if first try is equal second try
                    target = None

        if target is None:
            return

        self.eventRoundtrip += 1
        try:
            target.ProcessEvent(evt)
        finally:
            self.eventRoundtrip -= 1


    def getPageHistoryDeepness(self):
        """
        Convenience method to call PageHistory.getDeepness() for current
        presenter.
        Returns tuple (back, forth) where  back  is the maximum number of steps
        to go backward in history,  forth  the max. number to go forward
        """
        dpp = self.getCurrentDocPagePresenter()
        if dpp is None:
            return (0, 0)
        
        return dpp.getPageHistory().getDeepness()


    def _OnEventToCurrentDocPPresenter(self, evt):
        """
        wx events which should be sent to current doc page presenter
        """
        # Check for infinite loop
        if self.eventRoundtrip > 0:
            return

        dpp = self.getCurrentDocPagePresenter()
        if dpp is None:
            return

        self.eventRoundtrip += 1
        try:
            dpp.ProcessEvent(evt)
        finally:
            self.eventRoundtrip -= 1


    def addMenuItem(self, menu, label, hint, evtfct=None, icondesc=None,
            menuID=None, updatefct=None, kind=wx.ITEM_NORMAL):
        if menuID is None:
            menuID = wx.NewId()
            
        if kind is None:
            kind = wx.ITEM_NORMAL

        lcut = label.split(u"\t", 1)
        if len(lcut) > 1:
            lcut[1] = self.translateMenuAccelerator(lcut[1])
            label = lcut[0] + u" \t" + lcut[1]


        menuitem = wx.MenuItem(menu, menuID, label + u" ", hint, kind)
        bitmap = self.resolveIconDescriptor(icondesc)
        if bitmap:
            menuitem.SetBitmap(bitmap)

        menu.AppendItem(menuitem)
        if evtfct is not None:
            wx.EVT_MENU(self, menuID, evtfct)

        if updatefct is not None:
            if isinstance(updatefct, tuple):
                updatefct = _buildChainedUpdateEventFct(updatefct)
            wx.EVT_UPDATE_UI(self, menuID, updatefct)

        return menuitem


    def addMenuItemByInternalDescriptor(self, menu, desc):
        if desc is None:
            return
        
        def internalAddMenuItem(function, label, statustext, shortcut=None,
                icondesc=None, menuID=None, updateFunction=None, kind=None,
                *dummy):
            """
            Compared to fillPluginsMenu() this variant supports tuples as
            update function but no auto-created submenus
            (by using '|' in item name).
            It expects an optional  shortcut  string before icon description
            instead of appending the shortcut with '\t' to label

            Furthermore it doesn't send self as additional parameter when
            menu item is called or updated.
            """
            if shortcut is not None:
                label += '\t' + shortcut

            self.addMenuItem(menu, label, statustext,
                    function, icondesc, menuID, updateFunction, kind)

        internalAddMenuItem(*desc)


    def addMenuItemByUnifNameTable(self, menu, unifNameTable):
        for unifName in unifNameTable.split("\n"):
            unifName = unifName.strip()
            if unifName == "":
                continue

            self.addMenuItemByInternalDescriptor(menu,
                    self.nonCoreMenuItems.getDescriptorFor(unifName))



    def buildWikiMenu(self):
        """
        Builds the first, the "Wiki" menu and returns it
        """
        wikiData = self.getWikiData()
        wikiMenu = wx.Menu()

        self.addMenuItem(wikiMenu, _(u'&New') + u'\t' + self.keyBindings.NewWiki,
                _(u'Create new wiki'), self.OnWikiNew)

        openWikiMenu = wx.Menu()
        wikiMenu.AppendMenu(wx.NewId(), _(u'&Open'), openWikiMenu)

        self.addMenuItem(openWikiMenu, _(u'In &This Window...') + u'\t' +
                self.keyBindings.OpenWiki,
                _(u'Open wiki in this window'), self.OnWikiOpen)

        self.addMenuItem(openWikiMenu, _(u'In &New Window...') + u'\t' +
                self.keyBindings.OpenWikiNewWindow,
                _(u'Open wiki in a new window'), self.OnWikiOpenNewWindow)

        self.addMenuItem(openWikiMenu, _(u'&Current in New Window') + u'\t' +
                self.keyBindings.CloneWindow,
                _(u'Create new window for same wiki'), self.OnCmdCloneWindow)

        wikiMenu.AppendSeparator()

        self.recentWikisMenu = wx.Menu()
        wikiMenu.AppendMenu(wx.NewId(), _(u'&Recent'), self.recentWikisMenu)

        self.rereadRecentWikis()


        self.favoriteWikisMenu = wx.Menu()  # TODO: Try to avoid rebuilding it each time wiki menu is recreated
        self.fillFavoriteWikisMenu(self.favoriteWikisMenu)
        wikiMenu.AppendMenu(wx.NewId(), _(u"F&avorites"), self.favoriteWikisMenu)


        if wikiData is not None:
            wikiMenu.AppendSeparator()

            self.addMenuItem(wikiMenu, _(u'&Search Wiki...') + u'\t' +
                    self.keyBindings.SearchWiki, _(u'Search whole wiki'),
                    lambda evt: self.showSearchDialog(), "tb_lens")


        wikiMenu.AppendSeparator()

        if wikiData is not None:
            exportWikisMenu = wx.Menu()
            wikiMenu.AppendMenu(wx.NewId(), _(u'Publish as HTML'), exportWikisMenu)

            self.addMenuItem(exportWikisMenu,
                    _(u'Wiki as Single HTML Page'),
                    _(u'Publish Wiki as Single HTML Page'), self.OnExportWiki,
                    menuID=GUI_ID.MENU_EXPORT_WHOLE_AS_PAGE)

            self.addMenuItem(exportWikisMenu,
                    _(u'Wiki as Set of HTML Pages'),
                    _(u'Publish Wiki as Set of HTML Pages'), self.OnExportWiki,
                    menuID=GUI_ID.MENU_EXPORT_WHOLE_AS_PAGES)

            self.addMenuItem(exportWikisMenu,
                    _(u'Current Wiki Word as HTML Page'),
                    _(u'Publish Current Wiki Word as HTML Page'), self.OnExportWiki,
                    menuID=GUI_ID.MENU_EXPORT_WORD_AS_PAGE)
    
            self.addMenuItem(exportWikisMenu,
                    _(u'Sub-Tree as Single HTML Page'),
                    _(u'Publish Sub-Tree as Single HTML Page'), self.OnExportWiki,
                    menuID=GUI_ID.MENU_EXPORT_SUB_AS_PAGE)
    
            self.addMenuItem(exportWikisMenu,
                    _(u'Sub-Tree as Set of HTML Pages'),
                    _(u'Publish Sub-Tree as Set of HTML Pages'), self.OnExportWiki,
                    menuID=GUI_ID.MENU_EXPORT_SUB_AS_PAGES)
    
#             self.addMenuItem(exportWikisMenu,
#                     _(u'Export Wiki to .wiki files'),
#                     _(u'Export Wiki to .wiki files in UTF-8'), self.OnExportWiki,
#                     menuID=GUI_ID.MENU_EXPORT_WHOLE_AS_RAW)
    
            self.addMenuItem(exportWikisMenu, _(u'Other Export...'),
                    _(u'Open general export dialog'), self.OnCmdExportDialog)


#         if wikiData is not None:
            self.addMenuItem(wikiMenu, _(u'Print...') + u'\t' + self.keyBindings.Print,
                    _(u'Show the print dialog'), self.OnShowPrintMainDialog)

            self.addMenuItemByUnifNameTable(wikiMenu,
                    """
                    menuItem/mainControl/builtin/openTrashcan
                    """
                    )

            wikiMenu.AppendSeparator()

            self.addMenuItem(wikiMenu, _(u'&Properties...'),
                    _(u'Show general information about current wiki'),
                    self.OnShowWikiPropertiesDialog)

        maintenanceMenu = wx.Menu()
        wikiMenu.AppendMenu(wx.NewId(), _(u'Maintenance'), maintenanceMenu)

        if wikiData is not None:
            if wikiData.checkCapability("rebuild") == 1:
                if wikiData.checkCapability("filePerPage") == 1:
                    self.addMenuItem(maintenanceMenu,
                            _(u'Update ext. modif. wiki files'),
                            _(u'Check for externally modified files and '
                            u'update cache in background'),
                            self.OnCmdUpdateExternallyModFiles,
                            menuID=GUI_ID.CMD_UPDATE_EXTERNALLY_MOD_FILES_WIKI,
                            updatefct=(self.OnUpdateDisReadOnlyWiki,))

                self.addMenuItem(maintenanceMenu, _(u'&Rebuild Wiki...'),
                        _(u'Rebuild this wiki and its cache completely'),
                        lambda evt: self.rebuildWiki(onlyDirty=False),
                        menuID=GUI_ID.MENU_REBUILD_WIKI,
                        updatefct=(self.OnUpdateDisReadOnlyWiki,))
                
                self.addMenuItem(maintenanceMenu, _(u'&Update cache...'),
                        _(u'Update cache where marked as not up to date'),
                        lambda evt: self.rebuildWiki(onlyDirty=True),
                        menuID=GUI_ID.MENU_UPDATE_WIKI_CACHE,
                        updatefct=(self.OnUpdateDisReadOnlyWiki,))

                self.addMenuItem(maintenanceMenu, _(u'&Initiate update...'),
                        _(u'Initiate full cache update which is done mainly '
                        u'in background'),
                        lambda evt: self.initiateFullUpdate(),
                        menuID=GUI_ID.MENU_INITATE_UPDATE_WIKI_CACHE,
                        updatefct=(self.OnUpdateDisReadOnlyWiki,))

                self.addMenuItemByUnifNameTable(maintenanceMenu,
                        """
                        menuItem/mainControl/builtin/showFileCleanupDialog
                        """
                        )

            # TODO: Test for wikiDocument.isSearchIndexEnabled()
#             self.addMenuItem(maintenanceMenu, _(u'Re&index Wiki...'),
#                     _(u'Rebuild the reverse index for fulltext search'),
#                     lambda evt: self.rebuildSearchIndex(onlyDirty=False),
#                     menuID=GUI_ID.MENU_REINDEX_REV_SEARCH,
#                     updatefct=self.OnUpdateDisReadOnlyWiki)


            self.addMenuItem(maintenanceMenu, _(u'Show job count...'),
                    _(u'Show how many update jobs are waiting in background'),
                    self.OnCmdShowWikiJobDialog)
                    
            maintenanceMenu.AppendSeparator()


        self.addMenuItem(maintenanceMenu, _(u'Open as &Type...'),
                _(u'Open wiki with a specified wiki database type'),
                self.OnWikiOpenAsType)

        if wikiData is not None:
            self.addMenuItem(maintenanceMenu, _(u'Reconnect...'),
                    _(u'Reconnect to database after connection failure'),
                    self.OnCmdReconnectDatabase)
                    
            maintenanceMenu.AppendSeparator()
    
            if wikiData.checkCapability("compactify") == 1:
                self.addMenuItem(maintenanceMenu, _(u'&Optimise Database'),
                        _(u'Free unused space in database'),
                        lambda evt: self.vacuumWiki(),
                        menuID=GUI_ID.MENU_VACUUM_WIKI,
                        updatefct=(self.OnUpdateDisReadOnlyWiki,))


            if wikiData.checkCapability("plain text import") == 1:
                self.addMenuItem(maintenanceMenu, _(u'&Copy .wiki files to database'),
                        _(u'Copy .wiki files to database'),
                        self.OnImportFromPagefiles,
                        updatefct=(self.OnUpdateDisReadOnlyWiki,))


        self.addMenuItemByUnifNameTable(maintenanceMenu,
                """
                menuItem/mainControl/builtin/recoverWikiDatabase
                """
                )


        wikiMenu.AppendSeparator()  # TODO May have two separators without anything between

#         self.addMenuItem(wikiMenu, '&Test', 'Test', lambda evt: self.testIt())

        menuID=wx.NewId()
        wikiMenu.Append(menuID, _(u'E&xit'), _(u'Exit'))
        wx.EVT_MENU(self, menuID, lambda evt: self.exitWiki())
        wx.App.SetMacExitMenuItemId(menuID)

        return wikiMenu

#         if wikiData is not None and wikiData.checkCapability("versioning") == 1:
#             wikiMenu.AppendSeparator()
#     
# #             menuID=wx.NewId()
# #             wikiMenu.Append(menuID, '&Store version', 'Store new version')
# #             wx.EVT_MENU(self, menuID, lambda evt: self.showStoreVersionDialog())
#     
#             menuID=wx.NewId()
#             wikiMenu.Append(menuID, _(u'&Retrieve version'),
#                     _(u'Retrieve previous version'))
#             wx.EVT_MENU(self, menuID, lambda evt: self.showSavedVersionsDialog())
#     
#             menuID=wx.NewId()
#             wikiMenu.Append(menuID, _(u'Delete &All Versions'),
#                     _(u'Delete all stored versions'))
#             wx.EVT_MENU(self, menuID, lambda evt: self.showDeleteAllVersionsDialog())



    def fillPluginsMenu(self, pluginMenu):
        """
        Builds or rebuilds the plugin menu. This function does no id reuse
        so it shouldn't be called too often (mainly on start and when
        rebuilding menu during development of plugins)

        pluginMenu -- An empty wx.Menu to add items to
        """
#         pluginMenu = None
        # get info for any plugin menu items and create them as necessary
        menuItems = reduce(lambda a, b: a+list(b),
                self.menuFunctions.describeMenuItems(self), [])
        
        subStructure = {}

        if len(menuItems) > 0:
            def addPluginMenuItem(function, label, statustext, icondesc=None,
                    menuID=None, updateFunction=None, kind=None, *dummy):
                
                labelComponents = label.split(u"|")
                
                sub = subStructure
                menu = pluginMenu

                for comp in labelComponents[:-1]:
                    newMenu, newSub = sub.get(comp, (None, None))
                    if newMenu is None:
                        newMenu = wx.Menu()
                        menu.AppendMenu(-1, comp, newMenu)
                        newSub = {}
                        sub[comp] = newMenu, newSub
                    
                    menu = newMenu
                    sub = newSub

                if updateFunction is not None:
                    updateFct = lambda evt: updateFunction(self, evt)
                else:
                    updateFct = None

                self.addMenuItem(menu, labelComponents[-1], statustext,
                        lambda evt: function(self, evt), icondesc, menuID,
                        updateFct, kind)

            for item in menuItems:
                addPluginMenuItem(*item)


    def fillRecentWikisMenu(self, menu):
        """
        Refreshes the list of recent wiki menus from self.wikiHistory
        """
        idRecycler = self.recentWikisActivation
        idRecycler.clearAssoc()

        # Add new items
        for wiki in self.wikiHistory:
            menuID, reused = idRecycler.assocGetIdAndReused(wiki)

            if not reused:
                # For a new id, an event must be set
                wx.EVT_MENU(self, menuID, self.OnRecentWikiUsed)

            menu.Append(menuID, uniToGui(wiki))


    def OnRecentWikiUsed(self, evt):
        entry = self.recentWikisActivation.get(evt.GetId())

        if entry is None:
            return

        self.openWiki(entry)


    def rereadRecentWikis(self):
        """
        Starts rereading and rebuilding of the recent wikis submenu
        """
        if self.recentWikisMenu is None:
            return

        history = self.configuration.get("main", "wiki_history")
        if not history:
            return

        self.wikiHistory = history.split(u";")

        maxLen = self.configuration.getint(
                "main", "recentWikisList_length", 5)
        if len(self.wikiHistory) > maxLen:
            self.wikiHistory = self.wikiHistory[:maxLen]

        clearMenu(self.recentWikisMenu)
        self.fillRecentWikisMenu(self.recentWikisMenu)


    def informRecentWikisChanged(self):
        if self.getCmdLineAction().noRecent:
            return

        self.configuration.set("main", "wiki_history",
                ";".join(self.wikiHistory))
        wx.GetApp().fireMiscEventKeys(
                ("reread recent wikis needed",))

    def fillTextBlocksMenu(self, menu):
        """
        Constructs the text blocks menu submenu and necessary subsubmenus.
        If this is called more than once, previously used menu ids are reused
        for the new menu.
        
        menu -- An empty wx.Menu to add items and submenus to
        """
        # Clear IdRecycler
        self.textBlocksActivation.clearAssoc()


        wikiDoc = self.getWikiDocument()
        if wikiDoc is not None and self.requireReadAccess():
            try:
                page = wikiDoc.getFuncPage(u"wiki/TextBlocks")
                treeData = TextTree.buildTreeFromText(page.getContent(),
                        TextTree.TextBlocksEntry.factory)
                TextTree.addTreeToMenu(treeData,
                        menu, self.textBlocksActivation, self,
                        self.OnTextBlockUsed)
                menu.AppendSeparator()

            except DbReadAccessError, e:
                self.lostReadAccess(e)
                traceback.print_exc()


        page = WikiDataManager.getGlobalFuncPage(u"global/TextBlocks")
        treeData = TextTree.buildTreeFromText(page.getContent(),
                TextTree.TextBlocksEntry.factory)
        TextTree.addTreeToMenu(treeData,
                menu, self.textBlocksActivation, self,
                self.OnTextBlockUsed)

        menu.AppendSeparator()
        menu.Append(GUI_ID.CMD_REREAD_TEXT_BLOCKS,
                _(u"Reread text blocks"),
                _(u"Reread the text block file(s) and recreate menu"))
        wx.EVT_MENU(self, GUI_ID.CMD_REREAD_TEXT_BLOCKS, self.OnRereadTextBlocks)


    def OnTextBlockUsed(self, evt):
        if self.isReadOnlyPage():
            return

        entry = self.textBlocksActivation.get(evt.GetId())

        if entry is None:
            return

        if u"a" in entry.flags:
            self.appendText(entry.value)
        else:
            self.addText(entry.value, replaceSel=True)


    
    def OnRereadTextBlocks(self, evt):
        self.rereadTextBlocks()
        
        
    def rereadTextBlocks(self):
        """
        Starts rereading and rebuilding of the text blocks submenu
        """
        if self.textBlocksMenu is None:
            return

        clearMenu(self.textBlocksMenu)
        self.fillTextBlocksMenu(self.textBlocksMenu)


    def fillFavoriteWikisMenu(self, menu):
        """
        Constructs the favorite wikis menu and necessary submenus.
        If this is called more than once, previously used menu ids are reused
        for the new menu.
        
        menu -- An empty wx.Menu to add items and submenus to
        """
        self.favoriteWikisActivation.clearAssoc()

        page = WikiDataManager.getGlobalFuncPage(u"global/FavoriteWikis")
        treeData = TextTree.buildTreeFromText(page.getContent(),
                TextTree.FavoriteWikisEntry.factory)
        TextTree.addTreeToMenu(treeData,
                menu, self.favoriteWikisActivation, self,
                self.OnFavoriteWikiUsed)

        menu.AppendSeparator()
        menu.Append(GUI_ID.CMD_ADD_CURRENT_WIKI_TO_FAVORITES,
                _(u"Add wiki"),
                _(u"Add a wiki to the favorites"))
        wx.EVT_MENU(self, GUI_ID.CMD_ADD_CURRENT_WIKI_TO_FAVORITES,
                self.OnAddToFavoriteWikis)

        menu.Append(GUI_ID.CMD_MANAGE_FAVORITE_WIKIS,
                _(u"Manage favorites"),
                _(u"Manage favorites"))
        wx.EVT_MENU(self, GUI_ID.CMD_MANAGE_FAVORITE_WIKIS,
                self.OnManageFavoriteWikis)


    def OnFavoriteWikiUsed(self, evt):
        try:
            entry = self.favoriteWikisActivation.get(evt.GetId())

            if entry is None:
                return

            if u"f" in entry.flags:
                # Try to focus already open frame
                frame = wx.GetApp().findFrameByWikiConfigPath(entry.value)
                if frame:
                    if frame.IsIconized():
                        frame.Iconize(False)
                    frame.Raise()
                    frame.SetFocus()
                    return

            if u"n" in entry.flags:
                # Open in new frame
                try:
                    clAction = CmdLineAction([])
                    clAction.inheritFrom(self.getCmdLineAction())
                    clAction.setWikiToOpen(entry.value)
                    clAction.frameToOpen = 1  # Open in new frame
                    wx.GetApp().startPersonalWikiFrame(clAction)
                except Exception, e:
                    traceback.print_exc()
                    self.displayErrorMessage(_(u'Error while starting new '
                            u'WikidPad instance'), e)
                    return
            else:
                # Open in same frame
                if entry.value.startswith(u"wiki:"):
                    # Handle an URL
                    filePath, wikiWordToOpen, anchorToOpen = \
                            StringOps.wikiUrlToPathWordAndAnchor(entry.value)
                    if os.path.exists(pathEnc(filePath)):
                        self.openWiki(filePath, wikiWordsToOpen=(wikiWordToOpen,),
                                anchorToOpen=anchorToOpen)
                    else:
                        self.displayErrorMessage(
                                _(u"Wiki doesn't exist: %s") % filePath)
                else:
                    self.openWiki(os.path.abspath(entry.value))

        except KeyError:
            pass


    def rereadFavoriteWikis(self):
        if self.favoriteWikisMenu is None:
            return

        clearMenu(self.favoriteWikisMenu)
        self.fillFavoriteWikisMenu(self.favoriteWikisMenu)
        
        # Update also toolbar by recreating
        if self.getShowToolbar():
            self.Freeze()
            try:
                self.setShowToolbar(False)
                self.setShowToolbar(True)
            finally:
                self.Thaw()


    def OnAddToFavoriteWikis(self,evt):
        document = self.getWikiDocument()
        if document is None:
            path = u""
            title = u""
        else:
            path = document.getWikiConfigPath()
            title = document.getWikiName()

        entry = TextTree.FavoriteWikisEntry(title, u"", u"",
                self._getStorableWikiPath(path))
        entry = TextTree.AddWikiToFavoriteWikisDialog.runModal(self, -1, entry)
        
        if entry is not None:
            page = WikiDataManager.getGlobalFuncPage(u"global/FavoriteWikis")
            text = page.getLiveText()
            if len(text) == 0 or text[-1] == u"\n":
                page.appendLiveText(entry.getTextLine() + u"\n")
            else:
                page.appendLiveText(u"\n" + entry.getTextLine() + u"\n")

            self.saveDocPage(page)


    def OnManageFavoriteWikis(self, evt):
        self.activatePageByUnifiedName(u"global/FavoriteWikis", tabMode=2)


    def OnInsertStringFromDict(self, evt):
        if self.isReadOnlyPage():
            return

        self.getActiveEditor().AddText(self.cmdIdToInsertString[evt.GetId()])


    def OnInsertIconAttribute(self, evt):
        if self.isReadOnlyPage():
            return

        self.insertAttribute("icon", self.cmdIdToIconNameForAttribute[evt.GetId()])


    def OnInsertColorAttribute(self, evt):
        if self.isReadOnlyPage():
            return

        self.insertAttribute("color", self.cmdIdToColorNameForAttribute[evt.GetId()])


    def resetCommanding(self):
        """
        Reset the "commanding" (meaning menus, toolbar(s), shortcuts)
        """
        self.buildMainMenu()

        # Update toolbar by recreating
        if self.getShowToolbar():
            with WindowUpdateLocker(self):
                self.setShowToolbar(False)
                self.setShowToolbar(True)


    def buildMainMenu(self):
        # ------------------------------------------------------------------------------------
        # Set up menu bar for the program.
        # ------------------------------------------------------------------------------------
        if self.mainmenu is not None:
            # This is a rebuild of an existing menu (after loading a new wikiData)
            self.mainmenu.Replace(0, self.buildWikiMenu(), _(u'W&iki'))
            return


        self.mainmenu = wx.MenuBar()   # Create menu bar.

        wikiMenu = self.buildWikiMenu()

        
        editMenu = wx.Menu()
        
        self.addMenuItem(editMenu, _(u'&Undo') + u'\t' + self.keyBindings.Undo,
                _(u'Undo'), self._OnRoundtripEvent, menuID=GUI_ID.CMD_UNDO,
                updatefct=(self.OnUpdateDisReadOnlyPage, self.OnUpdateDisNotTextedit))

        self.addMenuItem(editMenu, _(u'&Redo') + u'\t' + self.keyBindings.Redo,
                _(u'Redo'), self._OnRoundtripEvent, menuID=GUI_ID.CMD_REDO,
                updatefct=(self.OnUpdateDisReadOnlyPage, self.OnUpdateDisNotTextedit))
 
        editMenu.AppendSeparator()

        # TODO: Incremental search
        
        self.addMenuItem(editMenu, _(u'&Search and Replace...') + u'\t' + 
                self.keyBindings.FindAndReplace,
                _(u'Search and replace inside current page'),
                lambda evt: self.showSearchReplaceDialog(),
                updatefct=(self.OnUpdateDisNotTextedit,))

        editMenu.AppendSeparator()

        self.addMenuItem(editMenu, _(u'Cu&t') + u'\t' + self.keyBindings.Cut,
                _(u'Cut'), self._OnRoundtripEvent,
                "tb_cut", menuID=GUI_ID.CMD_CLIPBOARD_CUT,
                updatefct=(self.OnUpdateDisReadOnlyPage, self.OnUpdateDisNotTextedit))

        self.addMenuItem(editMenu, _(u'&Copy') + u'\t' + self.keyBindings.Copy,
                _(u'Copy'), self._OnRoundtripEvent,
                "tb_copy", menuID=GUI_ID.CMD_CLIPBOARD_COPY)

        self.addMenuItem(editMenu, _(u'&Paste') + u'\t' + self.keyBindings.Paste,
                _(u'Paste'), self._OnRoundtripEvent,
                "tb_paste", menuID=GUI_ID.CMD_CLIPBOARD_PASTE,
                updatefct=(self.OnUpdateDisReadOnlyPage, self.OnUpdateDisNotTextedit))

        self.addMenuItem(editMenu, _(u'&Paste Raw HTML') + u'\t' +
                self.keyBindings.PasteRawHtml,
                _(u'Paste HTML data as is if available'), self._OnRoundtripEvent,
                "tb_paste", menuID=GUI_ID.CMD_CLIPBOARD_PASTE_RAW_HTML,
                updatefct=(self.OnUpdateDisReadOnlyPage,
                    self.OnUpdateDisNotTextedit,self.OnUpdateDisNotHtmlOnClipboard))

        self.addMenuItem(editMenu, _(u'Select &All') + u'\t' + self.keyBindings.SelectAll,
                _(u'Select All'), self._OnRoundtripEvent,
                 menuID=GUI_ID.CMD_SELECT_ALL)

        editMenu.AppendSeparator()

        self.addMenuItem(editMenu, _(u'Copy to Sc&ratchPad') + u'\t' + \
                self.keyBindings.CopyToScratchPad,
                _(u'Copy selected text to ScratchPad'), lambda evt: self.getActiveEditor().snip(),
                "tb_copy", updatefct=(self.OnUpdateDisReadOnlyWiki,))

        self.textBlocksMenu = wx.Menu()
        self.fillTextBlocksMenu(self.textBlocksMenu)

        editMenu.AppendMenu(GUI_ID.MENU_TEXT_BLOCKS, _(u'Paste T&extblock'),
                self.textBlocksMenu)
        wx.EVT_UPDATE_UI(self, GUI_ID.MENU_TEXT_BLOCKS,
                _buildChainedUpdateEventFct((self.OnUpdateDisReadOnlyPage,)))
        

        if self.clipboardInterceptor is not None:
            clipCatchMenu = wx.Menu()
            editMenu.AppendMenu(wx.NewId(), _(u'C&lipboard Catcher'),
                    clipCatchMenu)

            self.addMenuItem(clipCatchMenu, _(u'Set at Page') + u'\t' +
                    self.keyBindings.CatchClipboardAtPage, 
                    _(u"Text copied to clipboard is also appended to this page"),
                    self.OnClipboardCatcherAtPage, 
                    menuID=GUI_ID.CMD_CLIPBOARD_CATCHER_AT_PAGE,
                    updatefct=self.OnUpdateClipboardCatcher,
                    kind=wx.ITEM_RADIO)

            self.addMenuItem(clipCatchMenu, _(u'Set at Cursor') + u'\t' +
                    self.keyBindings.CatchClipboardAtCursor, 
                    _(u"Text copied to clipboard is also added to cursor position"),
                    self.OnClipboardCatcherAtCursor, 
                    menuID=GUI_ID.CMD_CLIPBOARD_CATCHER_AT_CURSOR,
                    updatefct=self.OnUpdateClipboardCatcher,
                    kind=wx.ITEM_RADIO)

            self.addMenuItem(clipCatchMenu, _(u'Set Off') + u'\t' +
                    self.keyBindings.CatchClipboardOff, 
                    _(u"Switch off clipboard catcher"),
                    self.OnClipboardCatcherOff, 
                    menuID=GUI_ID.CMD_CLIPBOARD_CATCHER_OFF,
                    updatefct=self.OnUpdateClipboardCatcher,
                    kind=wx.ITEM_RADIO)


        if SpellChecker.isSpellCheckSupported():
            editMenu.AppendSeparator()

            self.addMenuItem(editMenu, _(u'Spell Check...') + u'\t' +
                    self.keyBindings.SpellCheck,
                    _(u'Spell check current and possibly further pages'),
                    lambda evt: self.showSpellCheckerDialog(),
                    updatefct=(self.OnUpdateDisReadOnlyPage, self.OnUpdateDisNotTextedit))

            self.addMenuItem(editMenu, _(u"Spell Check While Type"),
                    _(u"Set if editor should do spell checking during typing"),
                    self.OnCmdCheckSpellCheckWhileType, 
                    updatefct=(self.OnUpdateDisNotTextedit, self.OnUpdateSpellCheckWhileType),
                    kind=wx.ITEM_CHECK)

            self.addMenuItem(editMenu, _(u'Clear Ignore List') + u'\t' +
                    self.keyBindings.SpellCheck,
                    _(u'Clear the list of words to ignore for spell check while type'),
                    lambda evt: self.resetSpellCheckWhileTypeIgnoreList(),
                    updatefct=(self.OnUpdateDisNotTextedit,))


        editMenu.AppendSeparator()


        insertMenu = wx.Menu()
        editMenu.AppendMenu(wx.NewId(), _(u'&Insert'), insertMenu)


        self.addMenuItemByUnifNameTable(insertMenu,
                """
                menuItem/mainControl/builtin/showInsertFileUrlDialog
                menuItem/mainControl/builtin/insertCurrentDate
                """)

#         self.addMenuItem(insertMenu, _(u'&File URL...') + '\t' + 
#                 self.keyBindings.AddFileUrl, _(u'Use file dialog to add URL'),
#                 self.nonCore.OnShowAddFileUrlDialog,
#                 updatefct=(self.OnUpdateDisReadOnlyPage, self.OnUpdateDisNotTextedit))

#         self.addMenuItem(insertMenu, _(u'Current &Date') + u'\t' + 
#                 self.keyBindings.InsertDate, _(u'Insert current date'),
#                 lambda evt: self.insertDate(), "date",
#                 updatefct=(self.OnUpdateDisReadOnlyPage, self.OnUpdateDisNotTextedit,
#                     self.OnUpdateDisNotWikiPage))

        # TODO: Insert colorname, color value, icon name


        settingsMenu = wx.Menu()
        editMenu.AppendMenu(wx.NewId(), _(u'&Settings'), settingsMenu)


        self.addMenuItem(settingsMenu, _(u'&Date Format...'),
                _(u'Set date format for inserting current date'),
                lambda evt: self.showDateformatDialog())


        self.addMenuItem(settingsMenu, _(u"Auto-&Wrap"),
                _(u"Set if editor should wrap long lines"),
                self.OnCmdCheckWrapMode, 
                updatefct=self.OnUpdateWrapMode,
                kind=wx.ITEM_CHECK)


#         menuID=wx.NewId()
#         wrapModeMenuItem = wx.MenuItem(settingsMenu, menuID, _(u"Auto-&Wrap"),
#                 _(u"Set if editor should wrap long lines"), wx.ITEM_CHECK)
#         settingsMenu.AppendItem(wrapModeMenuItem)
#         wx.EVT_MENU(self, menuID, self.OnCmdCheckWrapMode)
#         wx.EVT_UPDATE_UI(self, menuID, self.OnUpdateWrapMode)


        self.addMenuItem(settingsMenu, _(u"Auto-&Indent"),
                _(u"Auto indentation"),
                self.OnCmdCheckAutoIndent, 
                updatefct=self.OnUpdateAutoIndent,
                kind=wx.ITEM_CHECK)


        self.addMenuItem(settingsMenu, _(u"Auto-&Bullets"),
                _(u"Show bullet on next line if current has one"),
                self.OnCmdCheckAutoBullets, 
                updatefct=self.OnUpdateAutoBullets,
                kind=wx.ITEM_CHECK)


        self.addMenuItem(settingsMenu, _(u"Tabs to spaces"),
                _(u"Write spaces when hitting TAB key"),
                self.OnCmdCheckTabsToSpaces, 
                updatefct=self.OnUpdateTabsToSpaces,
                kind=wx.ITEM_CHECK)


        viewMenu = wx.Menu()
        
        self.addMenuItem(viewMenu, _(u'Show T&oolbar') + u'\t' +
                self.keyBindings.ShowToolbar, 
                _(u"Show toolbar"),
                lambda evt: self.setShowToolbar(
                not self.getConfig().getboolean("main", "toolbar_show", True)), 
                menuID=GUI_ID.CMD_SHOW_TOOLBAR,
                updatefct=self.OnUpdateToolbarMenuItem,
                kind=wx.ITEM_CHECK)

        self.addMenuItem(viewMenu, _(u'Show &Tree View') + u'\t' +
                self.keyBindings.ShowTreeControl, 
                _(u"Show Tree Control"),
                lambda evt: self.setShowTreeControl(
                self.windowLayouter.isWindowCollapsed("maintree")), 
                updatefct=self.OnUpdateTreeCtrlMenuItem,
                kind=wx.ITEM_CHECK)


        self.addMenuItem(viewMenu, _(u'Show &Chron. View') + u'\t' +
                self.keyBindings.ShowTimeView, 
                _(u"Show chronological view"),
                lambda evt: self.setShowTimeView(
                self.windowLayouter.isWindowCollapsed("time view")), 
                updatefct=self.OnUpdateTimeViewMenuItem,
                kind=wx.ITEM_CHECK)


        self.addMenuItem(viewMenu, _(u'Show &Page Structure') + u'\t' +
                self.keyBindings.ShowDocStructure, 
                _(u"Show structure (headings) of the page"),
                lambda evt: self.setShowDocStructure(
                self.windowLayouter.isWindowCollapsed("doc structure")), 
                updatefct=self.OnUpdateDocStructureMenuItem,
                kind=wx.ITEM_CHECK)


        # TODO: Show error log

        viewMenu.AppendSeparator()


        self.addMenuItem(viewMenu, _(u"Show &Indentation Guides"), 
                _(u"Show indentation guides in editor"),
                self.OnCmdCheckIndentationGuides, 
                updatefct=self.OnUpdateIndentationGuides,
                kind=wx.ITEM_CHECK)
 
        self.addMenuItem(viewMenu, _(u"Show Line &Numbers"), 
                _(u"Show line numbers in editor"),
                self.OnCmdCheckShowLineNumbers, 
                updatefct=self.OnUpdateShowLineNumbers,
                kind=wx.ITEM_CHECK)
        
        viewMenu.AppendSeparator()
        
        self.addMenuItem(viewMenu, _(u'Stay on Top') + u'\t' +
                self.keyBindings.StayOnTop, 
                _(u"Stay on Top of all other windows"),
                lambda evt: self.setStayOnTop(not self.getStayOnTop()), 
                menuID=GUI_ID.CMD_STAY_ON_TOP,
                updatefct=self.OnUpdateStayOnTopMenuItem,
                kind=wx.ITEM_CHECK)
        
        viewMenu.AppendSeparator()
       
        self.addMenuItem(viewMenu, _(u'&Zoom In') + u'\t' + self.keyBindings.ZoomIn,
                _(u'Zoom In'), self._OnRoundtripEvent, "tb_zoomin",
                menuID=GUI_ID.CMD_ZOOM_IN)

        self.addMenuItem(viewMenu, _(u'Zoo&m Out') + u'\t' + self.keyBindings.ZoomOut,
                _(u'Zoom Out'), self._OnRoundtripEvent, "tb_zoomout",
                menuID=GUI_ID.CMD_ZOOM_OUT)


#         menuItem = wx.MenuItem(viewMenu, GUI_ID.CMD_SHOW_TOOLBAR,
#                 _(u'Show Toolbar') + u'\t' + self.keyBindings.ShowToolbar, 
#                 _(u"Show Toolbar"), wx.ITEM_CHECK)
#         viewMenu.AppendItem(menuItem)
#         wx.EVT_MENU(self, GUI_ID.CMD_SHOW_TOOLBAR, lambda evt: self.setShowToolbar(
#                 not self.getConfig().getboolean("main", "toolbar_show", True)))
#         wx.EVT_UPDATE_UI(self, GUI_ID.CMD_SHOW_TOOLBAR,
#                 self.OnUpdateToolbarMenuItem)



        tabsMenu = wx.Menu()
        
        # TODO: open new tab              (now: no menuchoice; open with current item)
        # TODO: close current tab         (now: no menuchoice)

#         tabsMenu.AppendSeparator()

        self.addMenuItem(tabsMenu, _(u'Toggle Ed./Prev') + u'\t' +
                self.keyBindings.ShowSwitchEditorPreview,
                _(u'Switch between editor and preview'),
                lambda evt: self.setDocPagePresenterSubControl(None),  "tb_switch ed prev",
                    menuID=GUI_ID.CMD_TAB_SHOW_SWITCH_EDITOR_PREVIEW)

        self.addMenuItem(tabsMenu, _(u'Enter Edit Mode') + u'\t' + self.keyBindings.ShowEditor,
                _(u'Show editor in tab'),
                lambda evt: self.setDocPagePresenterSubControl("textedit"),  #  "tb_editor",
                    menuID=GUI_ID.CMD_TAB_SHOW_EDITOR)

        self.addMenuItem(tabsMenu, _(u'Enter Preview Mode') + u'\t' +
                self.keyBindings.ShowPreview,
                _(u'Show preview in tab'),
                lambda evt: self.setDocPagePresenterSubControl("preview"),  #   "tb_preview",
                    menuID=GUI_ID.CMD_TAB_SHOW_PREVIEW)

        tabsMenu.AppendSeparator()

        wxHelper.appendToMenuByMenuDesc(tabsMenu, FOLD_MENU, self.keyBindings)

        wx.EVT_MENU(self, GUI_ID.CMD_CHECKBOX_SHOW_FOLDING,
                self.OnCmdCheckShowFolding)
        wx.EVT_UPDATE_UI(self, GUI_ID.CMD_CHECKBOX_SHOW_FOLDING,
                self.OnUpdateShowFolding)

        wx.EVT_MENU(self, GUI_ID.CMD_TOGGLE_CURRENT_FOLDING,
                lambda evt: self.getActiveEditor().toggleCurrentFolding())
        wx.EVT_MENU(self, GUI_ID.CMD_UNFOLD_ALL_IN_CURRENT,
                lambda evt: self.getActiveEditor().unfoldAll())
        wx.EVT_MENU(self, GUI_ID.CMD_FOLD_ALL_IN_CURRENT,
                lambda evt: self.getActiveEditor().foldAll())
        


        wikiPageMenu = wx.Menu()

        self.addMenuItem(wikiPageMenu, _(u'&Save') + u'\t' + self.keyBindings.Save,
                _(u'Save all open pages'),
                lambda evt: (self.saveAllDocPages(),
                self.getWikiData().commit()), "tb_save",
                menuID=GUI_ID.CMD_SAVE_WIKI,
                updatefct=(self.OnUpdateDisReadOnlyWiki,))

        # TODO: More fine grained check for en-/disabling of rename and delete?
        self.addMenuItem(wikiPageMenu, _(u'&Rename') + u'\t' + self.keyBindings.Rename,
                _(u'Rename current wiki word'), lambda evt: self.showWikiWordRenameDialog(),
                "tb_rename",
                menuID=GUI_ID.CMD_RENAME_PAGE,
                updatefct=(self.OnUpdateDisReadOnlyWiki, self.OnUpdateDisNotWikiPage))

        self.addMenuItem(wikiPageMenu, _(u'&Delete') + u'\t' + self.keyBindings.Delete,
                _(u'Delete current wiki word'), lambda evt: self.showWikiWordDeleteDialog(),
                "tb_delete",
                menuID=GUI_ID.CMD_DELETE_PAGE,
                updatefct=(self.OnUpdateDisReadOnlyWiki, self.OnUpdateDisNotWikiPage))

        wikiPageMenu.AppendSeparator()

        self.addMenuItem(wikiPageMenu, _(u'Set as Roo&t') + u'\t' +
                self.keyBindings.SetAsRoot,
                _(u'Set current wiki word as tree root'),
                lambda evt: self.setCurrentWordAsRoot(),
                )

        self.addMenuItem(wikiPageMenu, _(u'R&eset Root') + u'\t' +
                self.keyBindings.ResetRoot, _(u'Set home wiki word as tree root'),
                lambda evt: self.setHomeWordAsRoot(),
                )

        self.addMenuItem(wikiPageMenu, _(u'S&ynchronise Tree'),
                _(u'Find the current wiki word in the tree'),
                lambda evt: self.findCurrentWordInTree(),
                "tb_cycle", updatefct=(self.OnUpdateDisNotWikiPage,))

        wikiPageMenu.AppendSeparator()

        self.addMenuItem(wikiPageMenu, _(u'&Follow Link') + u'\t' +
                self.keyBindings.ActivateLink, _(u'Activate link/word'),
                lambda evt: self.getActiveEditor().activateLink(),
                updatefct=(self.OnUpdateDisNotTextedit, self.OnUpdateDisNotWikiPage)
                )

        self.addMenuItem(wikiPageMenu, _(u'Follow Link in &New Tab') + u'\t' +
                self.keyBindings.ActivateLinkNewTab,
                _(u'Activate link/word in new tab'),
                lambda evt: self.getActiveEditor().activateLink(tabMode=2),
                updatefct=(self.OnUpdateDisNotTextedit, self.OnUpdateDisNotWikiPage)
                )

        self.addMenuItem(wikiPageMenu, _(u'Follow Link in New &Window') + u'\t' +
                self.keyBindings.ActivateLinkNewWindow,
                _(u'Activate link/word in new window'),
                lambda evt: self.getActiveEditor().activateLink(tabMode=6),
                updatefct=(self.OnUpdateDisNotTextedit, self.OnUpdateDisNotWikiPage)
                )

        self.addMenuItem(wikiPageMenu, _(u'Copy &URL to Clipboard') + u'\t' +
                self.keyBindings.ClipboardCopyUrlToCurrentWikiword,
                _(u'Copy full "wiki:" URL of the word to clipboard'),
                self.OnCmdClipboardCopyUrlToCurrentWikiWord,
                updatefct=(self.OnUpdateDisNotWikiPage,))

        wikiPageMenu.AppendSeparator()

        self.addMenuItem(wikiPageMenu, _(u'&Add version') + u'\t' +
                self.keyBindings.AddVersion, _(u'Add new version'),
                self.OnCmdVersionAdd, menuID=GUI_ID.CMD_VERSIONING_ADD_VERSION,
                updatefct=(self.OnUpdateDisNotTextedit, self.OnUpdateDisNotWikiPage)
                )

        self.addMenuItemByUnifNameTable(wikiPageMenu,
                """
                menuItem/mainControl/builtin/togglePageReadOnly
                """
                )


        formatMenu = wx.Menu()
        
        self.addMenuItem(formatMenu, _(u'&Bold') + u'\t' + self.keyBindings.Bold,
                _(u'Bold'), lambda evt: self.getActiveEditor().formatSelection("bold"),
                "tb_bold",
                menuID=GUI_ID.CMD_FORMAT_BOLD,
                updatefct=(self.OnUpdateDisReadOnlyPage, self.OnUpdateDisNotTextedit,
                    self.OnUpdateDisNotWikiPage))

        self.addMenuItem(formatMenu, _(u'&Italic') + u'\t' + self.keyBindings.Italic,
                _(u'Italic'), lambda evt: self.getActiveEditor().formatSelection("italics"),
                "tb_italic",
                menuID=GUI_ID.CMD_FORMAT_ITALIC,
                updatefct=(self.OnUpdateDisReadOnlyPage, self.OnUpdateDisNotTextedit,
                    self.OnUpdateDisNotWikiPage))

        self.addMenuItem(formatMenu, _(u'&Heading') + u'\t' + self.keyBindings.Heading,
                _(u'Add Heading'), lambda evt: self.getActiveEditor().formatSelection("plusHeading"),
                "tb_heading",
                menuID=GUI_ID.CMD_FORMAT_HEADING_PLUS,
                updatefct=(self.OnUpdateDisReadOnlyPage, self.OnUpdateDisNotTextedit,
                    self.OnUpdateDisNotWikiPage))

        formatMenu.AppendSeparator()

        self.addMenuItem(formatMenu, _(u'&Rewrap Text') + u'\t' + 
                self.keyBindings.RewrapText,
                _(u'Rewrap Text'),
                lambda evt: self.getActiveEditor().rewrapText(),
                updatefct=(self.OnUpdateDisReadOnlyPage,))

        convertMenu = wx.Menu()
        formatMenu.AppendMenu(wx.NewId(), _(u'&Convert'), convertMenu)
        
        self.addMenuItemByUnifNameTable(convertMenu,
        """
        menuItem/mainControl/builtin/selectionToLink
        """
        )

#         self.addMenuItem(convertMenu,
#                 _(u'Selection to &Link') + u'\t' + self.keyBindings.MakeWikiWord,
#                 _(u'Remove non-allowed characters and make sel. a wiki word link'),
#                 lambda evt: self.keyBindings.makeWikiWord(self.getActiveEditor()),
#                 "tb_wikize", menuID=GUI_ID.CMD_FORMAT_WIKIZE_SELECTED,
#                 updatefct=(self.OnUpdateDisReadOnlyPage, self.OnUpdateDisNotTextedit))
        
        self.addMenuItem(convertMenu, _(u'Selection to &Wiki Word') + u'\t' + 
                self.keyBindings.ReplaceTextByWikiword,
                _(u'Put selected text in a new or existing wiki word'),
                lambda evt: self.showReplaceTextByWikiwordDialog(),
                updatefct=(self.OnUpdateDisReadOnlyPage,))


        self.addMenuItem(convertMenu, _(u'Absolute/Relative &File URL') + u'\t' + 
                self.keyBindings.ConvertAbsoluteRelativeFileUrl,
                _(u'Convert file URL from absolute to relative and vice versa'),
                lambda evt: self.getActiveEditor().convertSelectedUrlAbsoluteRelative(),
                updatefct=(self.OnUpdateDisReadOnlyPage, self.OnUpdateDisNotTextedit,
                    self.OnUpdateDisNotWikiPage))

        formatMenu.AppendSeparator()


        iconsMenu, cmdIdToIconName = AttributeHandling.buildIconsSubmenu(
                wx.GetApp().getIconCache())
        for cmi in cmdIdToIconName.keys():
            wx.EVT_MENU(self, cmi, self.OnInsertStringFromDict)

        formatMenu.AppendMenu(GUI_ID.MENU_ADD_ICON_NAME,
                _(u'&Icon Name'), iconsMenu)
        wx.EVT_UPDATE_UI(self, GUI_ID.MENU_ADD_ICON_NAME,
                _buildChainedUpdateEventFct((self.OnUpdateDisReadOnlyPage,)))

        self.cmdIdToInsertString = cmdIdToIconName
        
        
        colorsMenu, cmdIdToColorName = AttributeHandling.buildColorsSubmenu()
        for cmi in cmdIdToColorName.keys():
            wx.EVT_MENU(self, cmi, self.OnInsertStringFromDict)

        formatMenu.AppendMenu(GUI_ID.MENU_ADD_STRING_NAME,
                _(u'&Color Name'), colorsMenu)
        wx.EVT_UPDATE_UI(self, GUI_ID.MENU_ADD_STRING_NAME,
                _buildChainedUpdateEventFct((self.OnUpdateDisReadOnlyPage,)))

        self.cmdIdToInsertString.update(cmdIdToColorName)


        addAttributeMenu = wx.Menu()
        formatMenu.AppendMenu(wx.NewId(), _(u'&Add Attribute'), addAttributeMenu)

        # Build full submenu for icon attributes
        iconsMenu, self.cmdIdToIconNameForAttribute = AttributeHandling.buildIconsSubmenu(
                wx.GetApp().getIconCache())
        for cmi in self.cmdIdToIconNameForAttribute.keys():
            wx.EVT_MENU(self, cmi, self.OnInsertIconAttribute)

        addAttributeMenu.AppendMenu(GUI_ID.MENU_ADD_ICON_ATTRIBUTE,
                _(u'&Icon Attribute'), iconsMenu)
        wx.EVT_UPDATE_UI(self, GUI_ID.MENU_ADD_ICON_ATTRIBUTE,
                _buildChainedUpdateEventFct((self.OnUpdateDisReadOnlyPage,)))

        # Build submenu for color attributes
        colorsMenu, self.cmdIdToColorNameForAttribute = AttributeHandling.buildColorsSubmenu()
        for cmi in self.cmdIdToColorNameForAttribute.keys():
            wx.EVT_MENU(self, cmi, self.OnInsertColorAttribute)

        addAttributeMenu.AppendMenu(GUI_ID.MENU_ADD_COLOR_ATTRIBUTE,
                _(u'&Color Attribute'), colorsMenu)
        wx.EVT_UPDATE_UI(self, GUI_ID.MENU_ADD_COLOR_ATTRIBUTE,
                _buildChainedUpdateEventFct((self.OnUpdateDisReadOnlyPage,)))

        # TODO: Bold attribute


        navigateMenu = wx.Menu()

        self.addMenuItem(navigateMenu, _(u'&Back') + u'\t' + self.keyBindings.GoBack,
                _(u'Go backward'), self._OnEventToCurrentDocPPresenter,
                "tb_back", updatefct=lambda evt: evt.Enable(
                self.getPageHistoryDeepness()[0] > 0),
                menuID=GUI_ID.CMD_PAGE_HISTORY_GO_BACK)

        self.addMenuItem(navigateMenu, _(u'&Forward') + u'\t' + self.keyBindings.GoForward,
                _(u'Go forward'), self._OnEventToCurrentDocPPresenter,
                "tb_forward", updatefct=lambda evt: evt.Enable(
                self.getPageHistoryDeepness()[1] > 0),
                menuID=GUI_ID.CMD_PAGE_HISTORY_GO_FORWARD)

        self.addMenuItem(navigateMenu, _(u'&Wiki Home') + u'\t' + self.keyBindings.GoHome,
                _(u'Go to wiki homepage'),
                lambda evt: self.openWikiPage(self.getWikiDocument().getWikiName(),
                    forceTreeSyncFromRoot=True),
                "tb_home", updatefct=(self.OnUpdateDisNoWiki,))

        self.addMenuItem(navigateMenu, _(u'Up&ward') + u'\t' + 
                self.keyBindings.GoUpwardFromSubpage,
                _(u'Go upward from a subpage'), self._OnEventToCurrentDocPPresenter,
                "tb_up", menuID=GUI_ID.CMD_PAGE_GO_UPWARD_FROM_SUBPAGE)

        navigateMenu.AppendSeparator()

        self.addMenuItem(navigateMenu, _(u'Go to &Page...') + u'\t' +
                self.keyBindings.OpenWikiWord, _(u'Open wiki word'),
                lambda evt: self.showWikiWordOpenDialog(),
                "tb_doc")


        self.addMenuItem(navigateMenu, _(u'Go to P&arent...') + u'\t' +
                self.keyBindings.ViewParents,
                _(u'List parents of current wiki word'),
                lambda evt: self.viewParents(self.getCurrentWikiWord()))

        self.addMenuItem(navigateMenu, _(u'List &Children...') + u'\t' +
                self.keyBindings.ViewChildren,
                _(u'List children of current wiki word'),
                lambda evt: self.viewChildren(self.getCurrentWikiWord()))

        self.addMenuItem(navigateMenu, _(u'List Pa&rentless Pages') + u'\t' +
                self.keyBindings.ViewParentless,
                _(u'List nodes with no parent relations'),
                lambda evt: self.viewParentLess())

        navigateMenu.AppendSeparator()

        self.addMenuItem(navigateMenu, _(u'Show &History...') + u'\t' + self.keyBindings.ViewHistory,
                _(u'View tab history'), self._OnEventToCurrentDocPPresenter,
                menuID=GUI_ID.CMD_PAGE_HISTORY_LIST)

        self.addMenuItem(navigateMenu, _(u'&Up History...') + u'\t' + self.keyBindings.UpHistory,
                _(u'Up in tab history'), self._OnEventToCurrentDocPPresenter,
                menuID=GUI_ID.CMD_PAGE_HISTORY_LIST_UP)

        self.addMenuItem(navigateMenu, _(u'&Down History...') + u'\t' + self.keyBindings.DownHistory,
                _(u'Down in tab history'), self._OnEventToCurrentDocPPresenter,
                menuID=GUI_ID.CMD_PAGE_HISTORY_LIST_DOWN)

        navigateMenu.AppendSeparator()

        self.addMenuItem(navigateMenu, _(u'Add B&ookmark') + u'\t' +
                self.keyBindings.AddBookmark, _(u'Add bookmark to page'),
                lambda evt: self.insertAttribute("bookmarked", "true"),
                "pin", updatefct=(self.OnUpdateDisReadOnlyWiki, self.OnUpdateDisNotWikiPage))

        self.addMenuItem(navigateMenu, _(u'Go to &Bookmark...') + u'\t' +
                self.keyBindings.ViewBookmarks, _(u'List bookmarks'),
                lambda evt: self.viewBookmarks())


        extraMenu = wx.Menu()

        self.addMenuItem(extraMenu, _(u'&Export...'),
                _(u'Open general export dialog'), self.OnCmdExportDialog,
                updatefct=(self.OnUpdateDisNoWiki,))

        self.addMenuItem(extraMenu, _(u'&Continuous Export...'),
                _(u'Open export dialog for continuous export of changes'),
                self.OnCmdContinuousExportDialog,
                updatefct=(self.OnUpdateDisNoWiki,
                self.OnUpdateContinuousExportDialog), kind=wx.ITEM_CHECK)


        self.addMenuItem(extraMenu, _(u'&Import...'),
                _(u'Import dialog'), self.OnCmdImportDialog,
                updatefct=(self.OnUpdateDisReadOnlyWiki,))

        extraMenu.AppendSeparator()

        evaluationMenu=wx.Menu()
        extraMenu.AppendMenu(wx.NewId(), _(u"Scripts"), evaluationMenu,
                _(u"Run scripts, evaluate expressions"))

        self.addMenuItem(evaluationMenu, _(u'&Eval') + u'\t' + self.keyBindings.Eval,
                _(u'Evaluate script blocks'),
                lambda evt: self.getActiveEditor().evalScriptBlocks())

        for i in range(1,7):
            self.addMenuItem(evaluationMenu,
                    _(u'Run Function &%i\tCtrl-%i') % (i, i),
                    _(u'Run script function %i') % i,
                    lambda evt, i=i: self.getActiveEditor().evalScriptBlocks(i))

        extraMenu.AppendSeparator()

        self.addMenuItem(extraMenu, _(u'Optional component &log...'),
                _(u'Show error while initializing optional components'),
                self.OnShowOptionalComponentErrorLog)

        extraMenu.AppendSeparator()

        self.addMenuItem(extraMenu, _(u'O&ptions...'),
                _(u'Set options'), lambda evt: self.showOptionsDialog(),
                menuID = wx.ID_PREFERENCES)


        helpMenu = wx.Menu()

        def openHelp(evt):
            try:
                clAction = CmdLineAction([])
                clAction.inheritFrom(self.getCmdLineAction())
                clAction.wikiToOpen = self.wikiPadHelp
                clAction.frameToOpen = 1  # Open in new frame

                wx.GetApp().startPersonalWikiFrame(clAction)
            except Exception, e:
                traceback.print_exc()
                self.displayErrorMessage(_(u'Error while starting new '
                        u'WikidPad instance'), e)
                return

        self.addMenuItem(helpMenu, _(u'&Open help wiki'),
                _(u'Open WikidPadHelp, the help wiki'), openHelp)


#         menuID=wx.NewId()
#         helpMenu.Append(menuID, _(u'&Open WikidPadHelp'), _(u'Open WikidPadHelp'))
#         wx.EVT_MENU(self, menuID, openHelp)

        helpMenu.AppendSeparator()

        self.addMenuItem(helpMenu, _(u'&Visit Homepage'),
                _(u'Visit wikidPad homepage'),
                lambda evt: OsAbstract.startFile(self, HOMEPAGE))

#         menuID=wx.NewId()
#         helpMenu.Append(menuID, _(u'&Visit wikidPad Homepage'), _(u'Visit Homepage'))
#         wx.EVT_MENU(self, menuID, lambda evt: OsAbstract.startFile(self, HOMEPAGE))

        helpMenu.AppendSeparator()

        self.addMenuItem(helpMenu,
                _(u'Show &License'),
                _(u'Show license of WikidPad and used components'),
                lambda evt: OsAbstract.startFile(self,
                os.path.join(self.wikiAppDir, u'license.txt')))

#         menuID = wx.NewId()
#         helpMenu.Append(menuID, _(u'View &License'), _(u'View License'))
#         wx.EVT_MENU(self, menuID, lambda evt: OsAbstract.startFile(self, 
#                 os.path.join(self.wikiAppDir, u'license.txt')))


        # Build menubar from all the menus

        if wx.Platform != "__WXMAC__":
            #don't need final separator if about item is going to app menu
            helpMenu.AppendSeparator()

        menuID = wx.ID_ABOUT
        helpMenu.Append(menuID, _(u'&About'), _(u'About WikidPad'))

        wx.EVT_MENU(self, menuID, lambda evt: self.showAboutDialog())

        self.mainmenu.Append(wikiMenu, _(u'&Wiki'))
        self.mainmenu.Append(editMenu, _(u'&Edit'))
        self.mainmenu.Append(viewMenu, _(u'&View'))
        self.mainmenu.Append(tabsMenu, _(u'&Tabs'))
        self.mainmenu.Append(wikiPageMenu, _(u'Wiki &Page'))
        self.mainmenu.Append(formatMenu, _(u'&Format'))
        self.mainmenu.Append(navigateMenu, _(u'&Navigate'))
        self.mainmenu.Append(extraMenu, _(u'E&xtra'))

        
#         self.mainmenu.AppendMenu(wx.NewId(), _(u'&Wiki'), wikiMenu)
#         self.mainmenu.AppendMenu(wx.NewId(), _(u'&Edit'), editMenu)
#         self.mainmenu.AppendMenu(wx.NewId(), _(u'&View'), viewMenu)
#         self.mainmenu.AppendMenu(wx.NewId(), _(u'&Tabs'), tabsMenu)
#         self.mainmenu.AppendMenu(wx.NewId(), _(u'Wiki &Page'), wikiPageMenu)
#         self.mainmenu.AppendMenu(wx.NewId(), _(u'&Format'), formatMenu)
#         self.mainmenu.AppendMenu(wx.NewId(), _(u'&Navigate'), navigateMenu)
#         self.mainmenu.AppendMenu(wx.NewId(), _(u'E&xtra'), extraMenu)



        self.pluginsMenu = wx.Menu()
        self.fillPluginsMenu(self.pluginsMenu)
        self.mainmenu.Append(self.pluginsMenu, _(u"Pl&ugins"))


        # Mac does not use menu accelerators anyway and wx special cases &Help 
        # to the in build Help menu this check stops 2 help menus on mac
        if wx.Platform == "__WXMAC__": 
            self.mainmenu.Append(helpMenu, _(u'&Help'))
        else:
            self.mainmenu.Append(helpMenu, _(u'He&lp'))


        self.SetMenuBar(self.mainmenu)

#         if self.getWikiConfigPath():  # If a wiki is open
#             self.mainmenu.EnableTop(1, 1)
#             self.mainmenu.EnableTop(2, 1)
#             self.mainmenu.EnableTop(3, 1)
#         else:
#             self.mainmenu.EnableTop(1, 0)
#             self.mainmenu.EnableTop(2, 0)
#             self.mainmenu.EnableTop(3, 0)



    def buildToolbar(self):
        # ------------------------------------------------------------------------------------
        # Create the toolbar
        # ------------------------------------------------------------------------------------

        tb = self.CreateToolBar(wx.TB_HORIZONTAL | wx.NO_BORDER | wx.TB_FLAT | wx.TB_TEXT)
        seperator = self.lookupSystemIcon("tb_seperator")

        icon = self.lookupSystemIcon("tb_back")
        tbID = GUI_ID.CMD_PAGE_HISTORY_GO_BACK
        tb.AddSimpleTool(tbID, icon, _(u"Back") + " " + self.keyBindings.GoBack,
                _(u"Back"))
        wx.EVT_TOOL(self, tbID, self._OnEventToCurrentDocPPresenter)

        icon = self.lookupSystemIcon("tb_forward")
        tbID = GUI_ID.CMD_PAGE_HISTORY_GO_FORWARD
        tb.AddSimpleTool(tbID, icon, _(u"Forward") + " " + self.keyBindings.GoForward,
                _(u"Forward"))
        wx.EVT_TOOL(self, tbID, self._OnEventToCurrentDocPPresenter)

        icon = self.lookupSystemIcon("tb_home")
        tbID = wx.NewId()
        tb.AddSimpleTool(tbID, icon, _(u"Wiki Home") + " " + self.keyBindings.GoHome,
                _(u"Wiki Home"))
        wx.EVT_TOOL(self, tbID,
                lambda evt: self.openWikiPage(self.getWikiDocument().getWikiName(),
                forceTreeSyncFromRoot=True))

        icon = self.lookupSystemIcon("tb_doc")
        tbID = wx.NewId()
        tb.AddSimpleTool(tbID, icon,
                _(u"Open Wiki Word") + " " + self.keyBindings.OpenWikiWord,
                _(u"Open Wiki Word"))
        wx.EVT_TOOL(self, tbID, lambda evt: self.showWikiWordOpenDialog())

        icon = self.lookupSystemIcon("tb_lens")
        tbID = wx.NewId()
        tb.AddSimpleTool(tbID, icon, _(u"Search") + " " + self.keyBindings.SearchWiki,
                _(u"Search"))
        wx.EVT_TOOL(self, tbID, lambda evt: self.showSearchDialog())

        icon = self.lookupSystemIcon("tb_cycle")
        tbID = wx.NewId()
        tb.AddSimpleTool(tbID, icon, _(u"Find current word in tree"),
                _(u"Find current word in tree"))
        wx.EVT_TOOL(self, tbID, lambda evt: self.findCurrentWordInTree())

        icon = self.lookupSystemIcon("tb_up")
        tbID = GUI_ID.CMD_PAGE_GO_UPWARD_FROM_SUBPAGE
        tb.AddSimpleTool(tbID, icon, _(u"Go upward from a subpage"),
                _(u"Go upward from a subpage"))
        wx.EVT_TOOL(self, tbID, self._OnEventToCurrentDocPPresenter)

        tb.AddSimpleTool(wx.NewId(), seperator, _(u"Separator"), _(u"Separator"))

        icon = self.lookupSystemIcon("tb_save")
        tb.AddSimpleTool(GUI_ID.CMD_SAVE_WIKI, icon,
                _(u"Save Wiki Word") + " " + self.keyBindings.Save,
                _(u"Save Wiki Word"))

        icon = self.lookupSystemIcon("tb_rename")
        tb.AddSimpleTool(GUI_ID.CMD_RENAME_PAGE, icon,
                _(u"Rename Wiki Word") + " " + self.keyBindings.Rename,
                _(u"Rename Wiki Word"))
#         wx.EVT_TOOL(self, tbID, lambda evt: self.showWikiWordRenameDialog())

        icon = self.lookupSystemIcon("tb_delete")
        tb.AddSimpleTool(GUI_ID.CMD_DELETE_PAGE, icon,
                _(u"Delete Wiki Word") + " " + self.keyBindings.Delete,
                _(u"Delete Wiki Word"))
#         wx.EVT_TOOL(self, tbID, lambda evt: self.showWikiWordDeleteDialog())

        tb.AddSimpleTool(wx.NewId(), seperator, _(u"Separator"), _(u"Separator"))

        icon = self.lookupSystemIcon("tb_heading")
        tb.AddSimpleTool(GUI_ID.CMD_FORMAT_HEADING_PLUS, icon,
                _(u"Heading") + " " + self.keyBindings.Heading, _(u"Heading"))
#         wx.EVT_TOOL(self, tbID, lambda evt: self.keyBindings.addHeading(
#                 self.getActiveEditor()))

        icon = self.lookupSystemIcon("tb_bold")
        tb.AddSimpleTool(GUI_ID.CMD_FORMAT_BOLD, icon,
                _(u"Bold") + " " + self.keyBindings.Bold, _(u"Bold"))
#         wx.EVT_TOOL(self, tbID, lambda evt: self.keyBindings.makeBold(
#                 self.getActiveEditor()))

        icon = self.lookupSystemIcon("tb_italic")
        tb.AddSimpleTool(GUI_ID.CMD_FORMAT_ITALIC, icon,
                _(u"Italic") + " " + self.keyBindings.Italic, _(u"Italic"))
#         wx.EVT_TOOL(self, tbID, lambda evt: self.keyBindings.makeItalic(
#                 self.getActiveEditor()))

        tb.AddSimpleTool(wx.NewId(), seperator, _(u"Separator"), _(u"Separator"))

        icon = self.lookupSystemIcon("tb_switch ed prev")
        tbID = GUI_ID.CMD_TAB_SHOW_SWITCH_EDITOR_PREVIEW
        tb.AddSimpleTool(tbID, icon, _(u"Switch Editor/Preview"),
                _(u"Switch between editor and preview"))

        icon = self.lookupSystemIcon("tb_zoomin")
        tbID = GUI_ID.CMD_ZOOM_IN
        tb.AddSimpleTool(tbID, icon, _(u"Zoom In"), _(u"Zoom In"))
        wx.EVT_TOOL(self, tbID, self._OnRoundtripEvent)

        icon = self.lookupSystemIcon("tb_zoomout")
        tbID = GUI_ID.CMD_ZOOM_OUT
        tb.AddSimpleTool(tbID, icon, _(u"Zoom Out"), _(u"Zoom Out"))
        wx.EVT_TOOL(self, tbID, self._OnRoundtripEvent)


        self.fastSearchField = wx.TextCtrl(tb, GUI_ID.TF_FASTSEARCH,
                style=wx.TE_PROCESS_ENTER | wx.TE_RICH)
        tb.AddControl(self.fastSearchField)
        wx.EVT_KEY_DOWN(self.fastSearchField, self.OnFastSearchKeyDown)

        icon = self.lookupSystemIcon("tb_wikize")
        tb.AddSimpleTool(GUI_ID.CMD_FORMAT_WIKIZE_SELECTED, icon,
                _(u"Wikize Selected Word ") + self.keyBindings.MakeWikiWord,
                _(u"Wikize Selected Word"))
#         wx.EVT_TOOL(self, tbID, lambda evt: self.keyBindings.makeWikiWord(self.getActiveEditor()))

        # Build favorite wikis tool buttons
        toolEntries = [(None, None)] * 9

        # Filter entries from activation map with a digit (1 to 9) in the flags.
        # This digit defines the position in the toolbar.
        for menuID, entry in self.favoriteWikisActivation.iteritems():
            num = entry.getToolbarPosition()
            if num != -1:
                toolEntries[num - 1] = (menuID, entry)

        defIcon = self.lookupSystemIcon("tb_doc")

        # Now go through found entries to create tool buttons
        for menuID, entry in toolEntries:
            if entry is None:
                # No entry for this digit
                continue

            icon = self.resolveIconDescriptor(entry.iconDesc, defIcon)
            tbID = menuID
            tb.AddSimpleTool(tbID, icon, entry.title, entry.value)
#             wx.EVT_TOOL(self, tbID, self._OnRoundtripEvent)   # TODO Check if needed on Linux/GTK


        # get info for any plugin toolbar items and create them as necessary
        toolbarItems = reduce(lambda a, b: a+list(b),
                self.toolbarFunctions.describeToolbarItems(self), [])

        def addPluginTool(function, tooltip, statustext, icondesc, tbID=None,
                updateFunction=None, rightclickFunction=None, *dummy):
            if tbID is None:
                tbID = wx.NewId()

            icon = self.resolveIconDescriptor(icondesc, defIcon)
            # tb.AddLabelTool(tbID, label, icon, wxNullBitmap, 0, tooltip)
            tb.AddSimpleTool(tbID, icon, tooltip, statustext)
            wx.EVT_TOOL(self, tbID, lambda evt: function(self, evt))

            if updateFunction is not None:
                wx.EVT_UPDATE_UI(self, tbID, lambda evt: updateFunction(self, evt))
            
            if rightclickFunction is not None:
                wx.EVT_TOOL_RCLICKED(self, tbID, lambda evt: rightclickFunction(self, evt))


        for item in toolbarItems:
            addPluginTool(*item)

        tb.Realize()



    def initializeGui(self):
        "initializes the gui environment"

        # ------------------------------------------------------------------------------------
        # Create the status bar
        # ------------------------------------------------------------------------------------
        self.statusBar = wx.StatusBar(self, -1)
        self.statusBar.SetFieldsCount(3)
        
        self.statusBarTimer = wx.Timer(self)
        wx.EVT_TIMER(self, self.statusBarTimer.GetId(), self.OnStatusBarTimer)

        # Measure necessary widths of status fields
        dc = wx.ClientDC(self.statusBar)
        try:
            dc.SetFont(self.statusBar.GetFont())
            posWidth = dc.GetTextExtent(
                    _(u"Line: 9999 Col: 9999 Pos: 9999999988888"))[0]
            dc.SetFont(wx.NullFont)
        finally:
            del dc


        # Create main area panel first
        self.mainAreaPanel = MainAreaPanel(self, self, -1)
        self.mainAreaPanel.getMiscEvent().addListener(self)

#         p = self.createNewDocPagePresenterTab()
#         self.mainAreaPanel.prepareCurrentPresenter(p)
 
        # ------------------------------------------------------------------------------------
        # Create menu and toolbar
        # ------------------------------------------------------------------------------------

        self.buildMainMenu()
        if self.getConfig().getboolean("main", "toolbar_show", True):
            self.setShowToolbar(True)

        wx.EVT_MENU(self, GUI_ID.CMD_SWITCH_FOCUS, self.OnSwitchFocus)

        # Table with additional possible accelerators
        ADD_ACCS = (
                ("CloseCurrentTab", GUI_ID.CMD_CLOSE_CURRENT_TAB),
                ("SwitchFocus", GUI_ID.CMD_SWITCH_FOCUS),
                ("GoNextTab", GUI_ID.CMD_GO_NEXT_TAB),
                ("GoPreviousTab", GUI_ID.CMD_GO_PREVIOUS_TAB),
                ("FocusFastSearchField", GUI_ID.CMD_FOCUS_FAST_SEARCH_FIELD)
#                 ("ActivateLink2", GUI_ID.CMD_ACTIVATE_LINK)
                )


        # Add alternative accelerators for clipboard operations
        accs = [
                (wx.ACCEL_CTRL, wx.WXK_INSERT, GUI_ID.CMD_CLIPBOARD_COPY),
                (wx.ACCEL_SHIFT, wx.WXK_INSERT, GUI_ID.CMD_CLIPBOARD_PASTE),
                (wx.ACCEL_SHIFT, wx.WXK_DELETE, GUI_ID.CMD_CLIPBOARD_CUT)
                ]


        # Add additional accelerators
        for keyName, menuId in ADD_ACCS:
            accP = self.keyBindings.getAccelPair(keyName)
            if accP != (None, None):
                accs.append((accP[0], accP[1], menuId))

        if SystemInfo.isLinux():   # Actually if wxGTK
            accs += [(wx.ACCEL_NORMAL, fkey, GUI_ID.SPECIAL_EAT_KEY)
                    for fkey in range(wx.WXK_F1, wx.WXK_F24 + 1)] + \
                    [(wx.ACCEL_SHIFT, fkey, GUI_ID.SPECIAL_EAT_KEY)
                    for fkey in range(wx.WXK_F1, wx.WXK_F24 + 1)]
    
            wx.EVT_MENU(self, GUI_ID.SPECIAL_EAT_KEY, lambda evt: None)

        self.SetAcceleratorTable(wx.AcceleratorTable(accs))

        # Check if window should stay on top
        self.setStayOnTop(self.getConfig().getboolean("main", "frame_stayOnTop",
                False))

        self.statusBar.SetStatusWidths([-1, -1, posWidth])
        self.SetStatusBar(self.statusBar)


        # Build layout:

        self.windowLayouter = WindowSashLayouter(self, self.createWindow)

        cfstr = self.getConfig().get("main", "windowLayout")
        self.windowLayouter.setWinPropsByConfig(cfstr)
        self.windowLayouter.realize()

        self.tree = self.windowLayouter.getWindowByName("maintree")
        self.logWindow = self.windowLayouter.getWindowByName("log")

        # Hide the vi input window
        self.windowLayouter.collapseWindow("vi input")


        # Register the App IDLE handler
#         wx.EVT_IDLE(self, self.OnIdle)

        wx.EVT_ACTIVATE(self, self.OnActivate)

        # Register the App close handler
        wx.EVT_CLOSE(self, self.OnCloseButton)

#         # Check resizing to layout sash windows
        wx.EVT_SIZE(self, self.OnSize)

        self.Bind(wx.EVT_ICONIZE, self.OnIconize)
        wx.EVT_MAXIMIZE(self, self.OnMaximize)
        
        wx.EVT_MENU(self, GUI_ID.CMD_CLOSE_CURRENT_TAB, self._OnRoundtripEvent)
        wx.EVT_MENU(self, GUI_ID.CMD_GO_NEXT_TAB, self._OnRoundtripEvent)
        wx.EVT_MENU(self, GUI_ID.CMD_GO_PREVIOUS_TAB, self._OnRoundtripEvent)
        wx.EVT_MENU(self, GUI_ID.CMD_FOCUS_FAST_SEARCH_FIELD,
                self.OnCmdFocusFastSearchField)


    def OnUpdateTreeCtrlMenuItem(self, evt):
        evt.Check(not self.windowLayouter.isWindowCollapsed("maintree"))

    def OnUpdateToolbarMenuItem(self, evt):
        evt.Check(not self.GetToolBar() is None)

    def OnUpdateDocStructureMenuItem(self, evt):
        evt.Check(not self.windowLayouter.isWindowCollapsed("doc structure"))

    def OnUpdateTimeViewMenuItem(self, evt):
        evt.Check(not self.windowLayouter.isWindowCollapsed("time view"))

    def OnUpdateStayOnTopMenuItem(self, evt):
        evt.Check(self.getStayOnTop())


    def OnSwitchFocus(self, evt):
        switchList = Utilities.IdentityList([self.mainAreaPanel])
        if not self.windowLayouter.isWindowCollapsed("maintree"):
            switchList.append(self.tree)

        if not self.windowLayouter.isWindowCollapsed("doc structure"):
            wnd = self.windowLayouter.getWindowByName("doc structure")
            if wnd is not None:
                switchList.append(wnd)
        
        if not self.windowLayouter.isWindowCollapsed("time view"):
            wnd = self.windowLayouter.getWindowByName("time view")
            if wnd is not None:
                switchList.append(wnd)


        if len(switchList) == 1:
            # Nothing to switch
            switchList[0].SetFocus()
            return

        foc = wx.Window.FindFocus()
        while foc != None:
            i = switchList.find(foc)
            if i > -1:
                i += 1
                if i >= len(switchList):
                    i = 0
                switchList[i].SetFocus()
                return

            foc = foc.GetParent()

        # Nothing found -> focus on main area panel
        switchList[0].SetFocus()


    def OnFastSearchKeyDown(self, evt):
        """
        Process wx.EVT_KEY_DOWN in the fast search text field
        """
        acc = wxHelper.getAccelPairFromKeyDown(evt)
        if acc == (wx.ACCEL_NORMAL, wx.WXK_RETURN) or \
                acc == (wx.ACCEL_NORMAL, wx.WXK_NUMPAD_ENTER):
            from .SearchAndReplaceDialogs import FastSearchPopup

            text = guiToUni(self.fastSearchField.GetValue())
            tfHeight = self.fastSearchField.GetSize()[1]
            pos = self.fastSearchField.ClientToScreen((0, tfHeight))

            popup = FastSearchPopup(self, self, -1, pos=pos)
            popup.Show()
            try:
                popup.runSearchOnWiki(text)
            except re.error, e:
                popup.Show(False)
                self.displayErrorMessage(_(u'Regular expression error'), e)
        else:
            evt.Skip()

#     def OnFastSearchChar(self, evt):
#         print "OnFastSearchChar", repr(evt.GetUnicodeKey()), repr(evt.GetKeyCode())
#         evt.Skip()

    def OnCmdReconnectDatabase(self, evt):
        answer = wx.MessageBox(_(u"Are you sure you want to reconnect? "
                u"You may lose some data by this process."),
                _(u'Reconnect database'),
                wx.YES_NO | wx.YES_DEFAULT | wx.ICON_QUESTION, self)

        wd = self.getWikiDocument()
        if answer == wx.YES and wd is not None:
            wd.setReadAccessFailed(True)
            wd.setWriteAccessFailed(True)
            # Try reading
            while True:
                try:
                    wd.reconnect()
                    wd.setReadAccessFailed(False)
                    break   # Success
                except (IOError, OSError, DbAccessError), e:
                    sys.stderr.write(_(u"Error while trying to reconnect:\n"))
                    traceback.print_exc()
                    answer = wx.MessageBox(uniToGui(_(
                            u'There was an error while reconnecting the database\n\n'
                            u'Would you like to try it again?\n%s') %
                            e), _(u'Error reconnecting!'),
                            wx.YES_NO | wx.YES_DEFAULT | wx.ICON_QUESTION, self)
                    if answer != wx.YES:
                        return

            # Try writing
            while True:
                try:
                    # write out the current configuration
                    self.writeCurrentConfig()
                    self.getWikiData().testWrite()

                    wd.setNoAutoSaveFlag(False)
                    wd.setWriteAccessFailed(False)
                    break   # Success
                except (IOError, OSError, DbWriteAccessError), e:
                    sys.stderr.write(_(u"Error while trying to write:\n"))
                    traceback.print_exc()
                    answer = wx.MessageBox(uniToGui(_(
                            u'There was an error while writing to the database\n\n'
                            u'Would you like to try it again?\n%s') %
                            e), _(u'Error writing!'),
                            wx.YES_NO | wx.YES_DEFAULT | wx.ICON_QUESTION, self)
                    if answer != wx.YES:
                        break

                
    def OnRemoteCommand(self, evt):
        try:
            clAction = CmdLineAction(evt.getCmdLineAction())
            wx.GetApp().startPersonalWikiFrame(clAction)
        except Exception, e:
            traceback.print_exc()
            self.displayErrorMessage(_(u'Error while starting new '
                    u'WikidPad instance'), e)
            return


    def OnShowHideHotkey(self, evt):
        if self.IsActive():
            self.Iconize(True)
        else:
            if self.IsIconized():
                self.Iconize(False)
                self.Show(True)

            self.Raise()


    def OnCmdFocusFastSearchField(self, evt):
        if self.fastSearchField is not None:
            self.fastSearchField.SetFocus()


    def OnCmdClipboardCopyUrlToCurrentWikiWord(self, evt):
        wikiWord = self.getCurrentWikiWord()
        if wikiWord is None:
            return
        
        path = self.getWikiDocument().getWikiConfigPath()
        wxHelper.copyTextToClipboard(pathWordAndAnchorToWikiUrl(path,
                wikiWord, None))


    def OnCmdVersionAdd(self, evt):
        ## _prof.start()
        from .timeView import Versioning

        docPage = self.getCurrentDocPage()
        if docPage is None or \
                not docPage.getUnifiedPageName().startswith(u"wikipage/"):
            return

        versionOverview = docPage.getVersionOverview()
        content = self.getActiveEditor().GetText()

        # TODO Description
        entry = Versioning.VersionEntry(u"", u"",
                "revdiff")
        versionOverview.addVersion(content, entry)
        versionOverview.writeOverview()
        ## _prof.stop()



    def goBrowserBack(self):
        evt = wx.CommandEvent(wx.wxEVT_COMMAND_MENU_SELECTED,
                GUI_ID.CMD_PAGE_HISTORY_GO_BACK)
        self._OnEventToCurrentDocPPresenter(evt)

    def goBrowserForward(self):
        evt = wx.CommandEvent(wx.wxEVT_COMMAND_MENU_SELECTED,
                GUI_ID.CMD_PAGE_HISTORY_GO_FORWARD)
        self._OnEventToCurrentDocPPresenter(evt)


    def _refreshHotKeys(self):
        """
        Refresh the system-wide hotkey settings according to configuration
        """
        # A dummy window must be destroyed and recreated because
        # unregistering a hotkey doesn't work
        if self.hotKeyDummyWindow is not None:
            self.hotKeyDummyWindow.Destroy()

        self.hotKeyDummyWindow = wxHelper.DummyWindow(self,
                id=GUI_ID.WND_HOTKEY_DUMMY)
        if self.configuration.getboolean("main",
                "hotKey_showHide_byApp_isActive"):
            wxHelper.setHotKeyByString(self.hotKeyDummyWindow,
                    self.HOTKEY_ID_HIDESHOW_BYAPP,
                    self.configuration.get("main",
                    "hotKey_showHide_byApp", u""))

        if self.getWikiDocument() is not None:
            wxHelper.setHotKeyByString(self.hotKeyDummyWindow,
                    self.HOTKEY_ID_HIDESHOW_BYWIKI,
                    self.configuration.get("main",
                    "hotKey_showHide_byWiki", u""))
        wx.EVT_HOTKEY(self.hotKeyDummyWindow, self.HOTKEY_ID_HIDESHOW_BYAPP,
                self.OnShowHideHotkey)
        wx.EVT_HOTKEY(self.hotKeyDummyWindow, self.HOTKEY_ID_HIDESHOW_BYWIKI,
                self.OnShowHideHotkey)


    def createWindow(self, winProps, parent):
        """
        Creates tree, editor, splitter, ... according to the given window name
        in winProps
        """
        winName = winProps["name"]
        if winName == "maintree" or winName == "viewstree":
            tree = WikiTreeCtrl(self, parent, -1, winName[:-4])
            # assign the image list
            try:
                # For native wx tree:
                # tree.AssignImageList(wx.GetApp().getIconCache().getNewImageList())
                # For custom tree control:
                tree.SetImageListNoGrayedItems(
                        wx.GetApp().getIconCache().getImageList())
            except Exception, e:
                traceback.print_exc()
                self.displayErrorMessage(_(u'There was an error loading the icons '
                        'for the tree control.'), e)
            if self.getWikiConfigPath() is not None and winName == "viewstree":
                tree.setViewsAsRoot()
                tree.expandRoot()
            return tree
        elif winName.startswith("txteditor"):
            editor = WikiTxtCtrl(winProps["presenter"], parent, -1)
            editor.evalScope = { 'editor' : editor,
                    'pwiki' : self, 'lib': self.evalLib}

            # enable and zoom the editor
            editor.Enable(0)
            editor.SetZoom(self.configuration.getint("main", "zoom"))
            return editor
        elif winName == "log":
            from .LogWindow import LogWindow
            return LogWindow(parent, -1, self)
        elif winName == "doc structure":
            from .DocStructureCtrl import DocStructureCtrl
            return DocStructureCtrl(parent, -1, self)
        elif winName == "time view":
            from .timeView.TimeViewCtrl import TimeViewCtrl
            return TimeViewCtrl(parent, -1, self)
        elif winName == "main area panel":  # TODO remove this hack
            self.mainAreaPanel.Reparent(parent)

#             if not self._mainAreaPanelCreated:
#                 print "--Parent main area panel2", repr(parent)
#                 self.mainAreaPanel.Create(parent, -1)
#                 self._mainAreaPanelCreated = True

#             self.mainAreaPanel.Reparent(parent)
#             self.mainAreaPanel = MainAreaPanel(parent, self, -1)
#             self.mainAreaPanel.getMiscEvent().addListener(self)
# 
#             p = self.createNewDocPagePresenterTab()
#             self.mainAreaPanel.setCurrentDocPagePresenter(p)

            return self.mainAreaPanel

        elif winName == "vi input":
            from .ViHelper import ViInputDialog
            return ViInputDialog(parent, -1, self)
            

    def perspectiveTypeFactory(self, parent, perspectType, data, typeFactory):
        """
        Type factory function as needed by
        WindowLayout.StorablePerspective.setByStoredPerspective()
        """
        if perspectType == u"DocPagePresenter":
            return DocPagePresenter.createFromPerspective(self, parent,
                    perspectType, data, typeFactory)
                    
        return None


    def createNewDocPagePresenterTab(self):
        presenter = DocPagePresenter(self, self)
        presenter.fillDefaultSubControls()
        return self.mainAreaPanel.appendPresenterTab(presenter)


    def createNewDocPagePresenterTabInNewFrame(self):
        """
        Launches a new wikidpad instance, create a DocPagePresenter in it
        and return it. Works only if wiki is loaded already
        """
        wd = self.getWikiDocument()
        if wd is None:
            return None

        clAction = CmdLineAction([])
        clAction.inheritFrom(self.getCmdLineAction())
        clAction.wikiToOpen = wd.getWikiConfigPath()
        clAction.wikiWordsToOpen = ()

        newFrame = wx.GetApp().startPersonalWikiFrame(clAction)
        return newFrame.createNewDocPagePresenterTab()


#     def appendLogMessage(self, msg):
#         """
#         Add message to log window, make log window visible if necessary
#         """
#         if self.configuration.getboolean("main", "log_window_autoshow"):
#             self.windowLayouter.expandWindow("log")
#         self.logWindow.appendMessage(msg)

    def showLogWindow(self):
        self.windowLayouter.expandWindow("log")

    def hideLogWindow(self):
        self.windowLayouter.collapseWindow("log")

    def reloadMenuPlugins(self):
        wx.GetApp().reloadPlugins()

        if self.mainmenu is not None:
            self.menuFunctions = self.pluginManager.registerSimplePluginAPI((
                    "MenuFunctions",1), ("describeMenuItems",))

            # Will only take affect for new tabs
            self.viPluginFunctions = self.pluginManager.registerSimplePluginAPI(
                    ("ViFunctions",1), ("describeViFunctions",))

            self.loadFixedExtensions()
            self.pluginManager.loadPlugins([ u'KeyBindings.py',
                    u'EvalLibrary.py' ] )
                    
            # TODO: Support for plugin menu modifiers wx.GetApp().reloadPluginMenuModifiers()

            # This is a rebuild of an existing menu (after loading a new wikiData)
            clearMenu(self.pluginsMenu)
            self.fillPluginsMenu(self.pluginsMenu)

            return


#     def testIt(self):
#         from .FileManagementGui import InfoDatabase
# 
#         progresshandler = ProgressHandler(
#                 _(u"     Scanning     "),
#                 _(u"     Scanning     "), 0, self)
# 
#         infoDb = InfoDatabase(self.getWikiDocument())
#         
#         infoDb.buildDatabaseBeforeDialog(progresshandler)
        


#     def testIt(self):
#         self.hhelp = wx.html.HtmlHelpController()
#         self.hhelp.AddBook(join(self.wikiAppDir, "helptest/helptest.hhp"))
#         self.hhelp.DisplayID(1)

#     def testIt(self):
#         rect = self.statusBar.GetFieldRect(0)
#         
#         dc = wx.WindowDC(self.statusBar)
#         dc.SetBrush(wx.RED_BRUSH)
#         dc.SetPen(wx.RED_PEN)
#         dc.DrawRectangle(rect.x, rect.y, rect.width, rect.height)
#         dc.SetPen(wx.WHITE_PEN)
#         dc.SetFont(self.statusBar.GetFont())
#         dc.DrawText(u"Saving page", rect.x + 2, rect.y + 2)
#         dc.SetFont(wx.NullFont)
#         dc.SetBrush(wx.NullBrush)
#         dc.SetPen(wx.NullPen)

        # self.statusBar.Refresh()


#     def resourceSleep(self):
#         """
#         Free unnecessary resources if program is iconized
#         """
#         if self.sleepMode:
#             return  # Already in sleep mode
#         self.sleepMode = True
#         
#         toolBar = self.GetToolBar()
#         if toolBar is not None:
#             toolBar.Destroy()
# 
#         self.SetMenuBar(None)
#         self.mainmenu.Destroy()
# 
#         # Set menu/menu items to None
#         self.mainmenu = None
#         self.recentWikisMenu = None
#         self.textBlocksMenu = None
#         self.favoriteWikisMenu = None
#         # self.showOnTrayMenuItem = None
# 
#         # TODO Clear cache only if exactly one window uses centralized iconLookupCache
#         #      Maybe weak references?
# #         for k in self.iconLookupCache.keys():
# #             self.iconLookupCache[k] = (self.iconLookupCache[k][0], None)
# ##      Even worse:  wxGetApp().getIconCache().clearIconBitmaps()
# 
#         gc.collect()
# 
# 
#     def resourceWakeup(self):
#         """
#         Aquire resources after program is restored
#         """
#         if not self.sleepMode:
#             return  # Already in wake mode
#         self.sleepMode = False
# 
#         self.buildMainMenu()
#         self.setShowToolbar(self.getConfig().getboolean("main", "toolbar_show",
#                 True))
#         self.setShowOnTray()


    def resourceSleep(self):
        """
        Free unnecessary resources if program is iconized
        """
        if self.sleepMode:
            return  # Already in sleep mode
        self.sleepMode = True
        self.saveAllDocPages()
        self.Unbind(wx.EVT_IDLE)


    def resourceWakeup(self):
        """
        Aquire resources after program is restored
        """
        if not self.sleepMode:
            return  # Already in wake mode
        self.sleepMode = False
        
        self.Bind(wx.EVT_IDLE, self.OnIdle)


    def Show(self, val=True):
        super(PersonalWikiFrame, self).Show(val)
        if val:
            self.resourceWakeup()
        else:
            self.resourceSleep()


    def OnIconize(self, evt):
        if self.configuration.getboolean("main", "showontray"):
            self.Show(not self.IsIconized())
        else:
            if self.IsIconized():
                self.resourceSleep()
            else:
                self.resourceWakeup()

        evt.Skip()


    def OnMaximize(self, evt):
        evt.Skip()


    # TODO Reset preview and other possible details
    def resetGui(self):
        # delete everything in the current tree
        self.tree.DeleteAllItems()
        
        viewsTree = self.windowLayouter.getWindowByName("viewstree")
        if viewsTree is not None:
            viewsTree.DeleteAllItems()

        
        # reset the editor
        if self.getActiveEditor():
            self.getActiveEditor().loadWikiPage(None)
            self.getActiveEditor().SetSelection(-1, -1)
            self.getActiveEditor().EmptyUndoBuffer()
            self.getActiveEditor().Disable()

        # reset tray
        self.setShowOnTray()


    def _getRelativeWikiPath(self, path):
        """
        Converts the absolute path to a relative path if possible. Otherwise
        the unmodified path is returned.
        """
        relPath = relativeFilePath(self.wikiAppDir, path)
        
        if relPath is None:
            return path
        else:
            return relPath


    def _getStorableWikiPath(self, path):
        """
        Converts the absolute path to a relative path if possible and if option
        is set to do this. Otherwise the unmodified path is returned.
        """
        if not self.getConfig().getboolean("main", "wikiPathes_relative", False):
            return path

        return self._getRelativeWikiPath(path)


    def newWiki(self, wikiName, wikiDir):
        "creates a new wiki"
        if len(DbBackendUtils.listHandlers()) == 0:
            self.displayErrorMessage(
                    _(u'No data handler available to create database.'))
            return

        wikiName = string.replace(wikiName, u" ", u"")
        wikiDir = os.path.join(wikiDir, wikiName)
        configFileLoc = os.path.join(wikiDir, u"%s.wiki" % wikiName)

#         self.statusBar.SetStatusText(uniToGui(u"Creating Wiki: %s" % wikiName), 0)

        createIt = True;
        if (os.path.exists(pathEnc(wikiDir))):
            dlg=wx.MessageDialog(self,
                    uniToGui(_(u"A wiki already exists in '%s', overwrite? "
                    u"(This deletes everything in and below this directory!)") %
                    wikiDir), _(u'Warning'), wx.YES_NO)
            answer = dlg.ShowModal()
            dlg.Destroy()
            if answer == wx.ID_YES:
                os.rmdir(wikiDir)  # TODO bug
                createIt = True
            elif answer == wx.ID_NO:
                createIt = False

        if createIt:
#             # Ask for the data handler to use
#             index = wx.GetSingleChoiceIndex(_(u"Choose database type"),
#                     _(u"Choose database type"), [wdh[1] for wdh in wdhandlers],
#                     self)
#             if index == -1:
#                 return
# 
#             wdhName = wdhandlers[index][0]

            wsett = AdditionalDialogs.NewWikiSettings.runModal(self, -1, self)
            if wsett is None:
                return

            wdhName, wlangName, asciiOnly = wsett[:3]
            if wdhName is None:
                return

            # create the new dir for the wiki
            os.mkdir(wikiDir)

            allIsWell = True

            dataDir = os.path.join(wikiDir, "data")
            dataDir = mbcsDec(os.path.abspath(dataDir), "replace")[0]

            # create the data directory for the data files
            try:
                WikiDataManager.createWikiDb(self, wdhName, wikiName, dataDir,
                        False)
            except WikiDBExistsException:
                # The DB exists, should it be overwritten
                dlg=wx.MessageDialog(self, _(u'A wiki database already exists '
                        u'in this location, overwrite?'),
                        _(u'Wiki DB Exists'), wx.YES_NO)
                answer = dlg.ShowModal()
                if answer == wx.ID_YES:
                    WikiDataManager.createWikiDb(self, wdhName, wikiName, dataDir,
                        True)
                else:
                    allIsWell = False

                dlg.Destroy()
            except Exception, e:
                self.displayErrorMessage(
                        _(u'There was an error creating the wiki database.'), e)
                traceback.print_exc()                
                allIsWell = False
            
            if (allIsWell):
                try:
                    self.hooks.newWiki(self, wikiName, wikiDir)
    
                    # everything is ok, write out the config file
                    # create a new config file for the new wiki
                    wikiConfig = wx.GetApp().createWikiConfiguration()
    #                 
                    wikiConfig.createEmptyConfig(configFileLoc)
                    wikiConfig.fillWithDefaults()
                    
                    wikiConfig.set("main", "wiki_name", wikiName)
                    wikiConfig.set("main", "last_wiki_word", wikiName)
                    wikiConfig.set("main", "wiki_database_type", wdhName)
                    wikiConfig.set("main", "wiki_wikiLanguage", wlangName)
                    wikiConfig.set("main", "wikiPageFiles_asciiOnly", asciiOnly)
                    wikiConfig.set("main", "editor_text_mode",
                            self.getConfig().getboolean("main",
                            "newWikiDefault_editor_text_mode", False))
                            
                    # Set here because of legacy support.
                    # See option description in "Configuration.py"
                    wikiConfig.set("main", "wikiPageTitle_headingLevel", "2")

                    wikiConfig.set("wiki_db", "data_dir", "data")
                    wikiConfig.save()

                    self.closeWiki()
                    
                    # open the new wiki
                    self.openWiki(configFileLoc)
                    p = self.wikiDataManager.createWikiPage(wikiName)
                    p.appendLiveText(u"\n\n\t* WikiSettings\n", False)

                    p = self.wikiDataManager.createWikiPage(u"WikiSettings")

                    langHelper = wx.GetApp().createWikiLanguageHelper(
                            self.getWikiDefaultWikiLanguage())

                    text = langHelper.getNewDefaultWikiSettingsPage(self)
                    p.replaceLiveText(text, False)
    
                    p = self.wikiDataManager.createWikiPage(u"ScratchPad")
                    text = u"++ Scratch Pad\n\n"
                    p.replaceLiveText(text, False)

#                     self.getActiveEditor().GotoPos(self.getActiveEditor().GetLength())
#                     self.getActiveEditor().AddText(u"\n\n\t* WikiSettings\n")
#                     self.saveAllDocPages()
                    
                    # trigger hook
                    self.hooks.createdWiki(self, wikiName, wikiDir)
    
                    # open the homepage
                    self.openWikiPage(self.wikiName, False, False)

                except (IOError, OSError, DbAccessError), e:
                    self.lostAccess(e)
                    raise


    def _askForDbType(self):
        """
        Show dialog to ask for the wiki data handler (= database type)
        for opening a wiki
        """
        wdhandlers = DbBackendUtils.listHandlers()
        if len(wdhandlers) == 0:
            self.displayErrorMessage(
                    'No data handler available to open database.')
            return None

        # Ask for the data handler to use
        index = wx.GetSingleChoiceIndex(_(u"Choose database type"),
                _(u"Choose database type"), [wdh[1] for wdh in wdhandlers],
                self)
        if index == -1:
            return None
            
        return wdhandlers[index][0]



    def openWiki(self, wikiCombinedFilename, wikiWordsToOpen=None,
            ignoreWdhName=False, lastTabsSubCtrls=None, anchorToOpen=None,
            activeTabNo=-1):
        """
        opens up a wiki
        wikiWordsToOpen -- List of wiki words to open or None for default
        ignoreWdhName -- Should the name of the wiki data handler in the
                wiki config file (if any) be ignored?
        lastTabsSubCtrls -- List of subcontrol names for each presenter
                of the corresponding wiki word to open
        """
        # Fix special case
        if wikiWordsToOpen == (None,):
            wikiWordsToOpen = None

        lastWordsOverridden = wikiWordsToOpen is not None

        # Save the state of the currently open wiki, if there was one open
        # if the new config is the same as the old, don't resave state since
        # this could be a wiki overwrite from newWiki. We don't want to overwrite
        # the new config with the old one.

        wikiCombinedFilename = os.path.abspath(os.path.join(self.wikiAppDir,
                wikiCombinedFilename))

        # make sure the config exists
        cfgPath, splittedWikiWord = WikiDataManager.splitConfigPathAndWord(
                wikiCombinedFilename)

        if cfgPath is None:
            self.displayErrorMessage(_(u"Inaccessible or missing file: %s")
                        % wikiCombinedFilename)

            # Try to remove combined filename from recent files if existing
            
            self.removeFromWikiHistory(wikiCombinedFilename)
#             try:
#                 self.wikiHistory.remove(
#                         self._getRelativeWikiPath(wikiCombinedFilename))
#                 self.informRecentWikisChanged()
#             except ValueError:
#                 pass


            return False

#        if self.wikiConfigFilename != wikiConfigFilename:
        self.closeWiki()

        # Remove path from recent file list if present (we will add it again
        # on top if everything went fine).
        
        self.removeFromWikiHistory(cfgPath)

        # trigger hooks
        self.hooks.openWiki(self, wikiCombinedFilename)

        if ignoreWdhName:
            # Explicitly ask for wiki data handler
            dbtype = self._askForDbType()
            if dbtype is None:
                return
        else:
            # Try to get handler name from wiki config file
            dbtype = None
        
        wikiLang = None
        
        ignoreLock = self.getConfig().getboolean("main", "wikiLockFile_ignore",
                False)
        createLock = self.getConfig().getboolean("main", "wikiLockFile_create",
                True)

        while True:
            try:
                wikiDataManager = WikiDataManager.openWikiDocument(
                        cfgPath, dbtype, wikiLang, ignoreLock, createLock)
                frmcode, frmtext = wikiDataManager.checkDatabaseFormat()
                if frmcode == 2:
                    # Unreadable db format
                    self.displayErrorMessage(
                            _(u"Error connecting to database in '%s'")
                            % cfgPath, frmtext)
                    return False
                elif frmcode == 1:
                    # Update needed -> ask
                    answer = wx.MessageBox(_(u"The wiki needs an update to work "
                            u"with this version of WikidPad. Older versions of "
                            u"WikidPad may be unable to read the wiki after "
                            u"an update."), _(u'Update database?'),
                            wx.OK | wx.CANCEL | wx.ICON_QUESTION, self)
                    if answer == wx.CANCEL:
                        return False

                wikiDataManager.connect()
                break
            except (UnknownDbHandlerException, DbHandlerNotAvailableException), e:
                # Could not get a handler name from wiki config file
                # (probably old database) or required handler not available,
                # so ask user
                self.displayErrorMessage(unicode(e))
                dbtype = AdditionalDialogs.NewWikiSettings.runModal(
                        self, -1, self, dbtype,
                        AdditionalDialogs.NewWikiSettings.DEFAULT_GREY)[0]
#                 dbtype = self._askForDbType()
                if dbtype is None:
                    return False

                continue # Try again
            except UnknownWikiLanguageException, e:
                # Could not get a handler name from wiki config file
                # (probably old database) or required handler not available,
                # so ask user
                self.displayErrorMessage(unicode(e))
                wikiLang = AdditionalDialogs.NewWikiSettings.runModal(
                        self, -1, self,
                        AdditionalDialogs.NewWikiSettings.DEFAULT_GREY, wikiLang)[1]
#                 dbtype = self._askForDbType()
                if wikiLang is None:
                    return False

                continue # Try again
            except LockedWikiException, e:
                # Database already in use by different instance
                answer = wx.MessageBox(_(u"Wiki '%s' is probably in use by different\n"
                        u"instance of WikidPad. Connect anyway (dangerous!)?") % cfgPath,
                        _(u"Wiki already in use"), wx.YES_NO, self)
                if answer != wx.YES:
                    return False
                else:
                    ignoreLock = True
                    continue # Try again

            except (BadConfigurationFileException,
                    MissingConfigurationFileException), e:
                answer = wx.MessageBox(_(u"Configuration file '%s' is corrupted "
                        u"or missing.\nYou may have to change some settings "
                        u'in configuration page "Current Wiki" and below which '
                        u"were lost.") % cfgPath, _(u'Continue?'),
                        wx.OK | wx.CANCEL | wx.ICON_QUESTION, self)
                if answer == wx.CANCEL:
                    return False

                wdhName = self._askForDbType()
                if wdhName is None:
                    return False

                wikiName = basename(cfgPath)[:-5] # Remove ".wiki"

                wikiConfig = wx.GetApp().createWikiConfiguration()

                wikiConfig.createEmptyConfig(cfgPath)
                wikiConfig.fillWithDefaults()

                wikiConfig.set("main", "wiki_name", wikiName)
                wikiConfig.set("main", "last_wiki_word", wikiName)
                wikiConfig.set("main", "wiki_database_type", wdhName)
                wikiConfig.set("wiki_db", "data_dir", "data")
                wikiConfig.save()
                
                continue # Try again

            except (IOError, OSError, DbReadAccessError,
                    BadConfigurationFileException,
                    MissingConfigurationFileException), e:
                # Something else went wrong
                self.displayErrorMessage(_(u"Error connecting to database in '%s'")
                        % cfgPath, e)
                if not isinstance(e, DbReadAccessError):
                    traceback.print_exc()
#                 self.lostAccess(e)
                return False
            except DbWriteAccessError, e:
                self.displayErrorMessage(_(u"Can't write to database '%s'")
                        % cfgPath, e)
                break   # ???

        # OK, things look good. Now set the member variables.

        self.wikiDataManager = wikiDataManager
        self.currentWikiDocumentProxyEvent.setWatchedEvent(
                self.wikiDataManager.getMiscEvent())
        self.wikiDataManager.getUpdateExecutor().getMiscEvent().addListener(self)

        if self.wikiDataManager.getUpdateExecutor().getJobCount() > 0:
            self.updateStatusMessage(
                    _("Performing background jobs..."),
                    key="jobInfo", duration=300000)
        else:
            self.dropStatusMessageByKey("jobInfo")

        self.wikiData = wikiDataManager.getWikiData()

        self.wikiName = self.wikiDataManager.getWikiName()
        self.dataDir = self.wikiDataManager.getDataDir()
        
        self.getConfig().setWikiConfig(self.wikiDataManager.getWikiConfig())
        
        # Open wiki pages which were previously opened (old method before
        # introducing AUI and perspectives)
        
        # Collect information
        
        mainAreaPerspective = self.getConfig().get("main",
                "wiki_mainArea_auiPerspective", u"");

        defLtsc = None
        
        if lastTabsSubCtrls is None:
            defLtsc = self.getConfig().get("main", "wiki_onOpen_tabsSubCtrl", u"")
            if defLtsc:
                # Actually multiple values aren't supported but just in case
                defLtsc = unescapeForIni(defLtsc.split(u";", 1)[0])
                lastTabsSubCtrls = [defLtsc]

        try:
            furtherWikiWords = []

            if wikiWordsToOpen is None:
                if splittedWikiWord:
                    # Take wiki word from combinedFilename
                    wikiWordsToOpen = (splittedWikiWord,)
                else:
                    # Try to find first wiki word
                    firstWikiWord = self.getConfig().get("main",
                        "first_wiki_word", u"")
                    if firstWikiWord != u"":
                        wikiWordsToOpen = (firstWikiWord,)
                        lastWordsOverridden = True
                    else:
                        # Nothing worked so take the last open wiki words
                        lastWikiWord = self.getConfig().get("main",
                                "last_wiki_word", u"")
                        fwws = self.getConfig().get("main",
                                "further_wiki_words", u"")
                        if fwws != u"":
                            furtherWikiWords = [unescapeForIni(w) for w in
                                    fwws.split(u";")]
                        else:
                            furtherWikiWords = ()
                        
                        wikiWordsToOpen = (lastWikiWord,) + \
                                tuple(furtherWikiWords)
                        
                        if lastTabsSubCtrls is None:
                            ltsc = self.getConfig().get("main",
                                    "wiki_lastTabsSubCtrls", u"")
                            if ltsc != u"":
                                lastTabsSubCtrls = [unescapeForIni(w) for w in
                                        ltsc.split(u";")]

                        if activeTabNo == -1:
                            activeTabNo = self.getConfig().getint("main",
                                    "wiki_lastActiveTabNo", -1)

            with WindowUpdateLocker(self):
                # reset the gui
                self.resetCommanding()

                # enable the top level menus
                if self.mainmenu:
                    self.mainmenu.EnableTop(1, 1)
                    self.mainmenu.EnableTop(2, 1)
                    self.mainmenu.EnableTop(3, 1)
                    
                self.fireMiscEventKeys(("opened wiki",))
                
                # open the home page    # TODO!
    #             self.openWikiPage(self.wikiName)
    
                self.tree.SetScrollPos(wx.VERTICAL, 0)
                
                lastRoot = self.getConfig().get("main", "tree_last_root_wiki_word",
                        None)
                if not (lastRoot and
                        self.getWikiDocument().isDefinedWikiLinkTerm(lastRoot)):
                    lastRoot = self.wikiName
                    
                self.tree.setRootByWord(lastRoot)
                self.tree.readExpandedNodesFromConfig()
                self.tree.expandRoot()
                self.getConfig().set("main", "tree_last_root_wiki_word", lastRoot)
    
                viewsTree = self.windowLayouter.getWindowByName("viewstree")
                if viewsTree is not None:
                    viewsTree.setViewsAsRoot()
                    viewsTree.readExpandedNodesFromConfig()
                    viewsTree.expandRoot()
    
                # Normalize lastTabsSubCtrls
                if not lastTabsSubCtrls:
                    lastTabsSubCtrls = ["textedit"]
                if len(lastTabsSubCtrls) < len(wikiWordsToOpen):
                    lastTabsSubCtrls += [lastTabsSubCtrls[-1]] * \
                            (len(wikiWordsToOpen) - len(lastTabsSubCtrls))
    
                # Remove/Replace undefined wiki words
                wwo = []
                for word, subCtrl in zip(wikiWordsToOpen, lastTabsSubCtrls):
                    if self.getWikiDocument().isDefinedWikiLinkTerm(word):
                        wwo.append((word, subCtrl))
                        continue
    
                    wordsStartingWith = self.getWikiData().getWikiPageLinkTermsStartingWith(
                            word)
                    if len(wordsStartingWith) > 0:
                        word = wordsStartingWith[0]
                        wwo.append((word, subCtrl))
                        continue
                    
                    # Omitting word, so adjust activeTabNo
                    activeTabNo -= 1



                if lastWordsOverridden or not mainAreaPerspective:
                    # now try and open the last wiki page as leftmost tab
                    if len(wwo) > 0: ## and wwo[0][0] != self.wikiName:
                        firstWikiWord = wwo[0][0]
    
                        self.openWikiPage(firstWikiWord, anchor=anchorToOpen)
                        self.findCurrentWordInTree()
                        targetPresenter = self.getMainAreaPanel().getPresenters()[0]
                        if targetPresenter.hasSubControl(wwo[0][1]):
                            targetPresenter.switchSubControl(wwo[0][1])
    #                 else:
    #                     self.openWikiPage(self.wikiName)
        
                    # If present, open further words in tabs on the right
                    for word, subCtrl in wwo[1:]:
                        targetPresenter = self.activatePageByUnifiedName(
                                u"wikipage/" + word, tabMode=3)
                        if targetPresenter is None:
                            break    # return instead?
    
                        if targetPresenter.hasSubControl(subCtrl):
                            targetPresenter.switchSubControl(subCtrl)
    
                    if activeTabNo > 0 and \
                            len(self.getMainAreaPanel().getPresenters()) > 0:
                        activeTabNo = min(activeTabNo,
                                len(self.getMainAreaPanel().getPresenters()) - 1)
    
                        targetPresenter = self.getMainAreaPanel().getPresenters()[
                                activeTabNo]
                        self.getMainAreaPanel().showPresenter(targetPresenter)
                        
                else:
                    self.getMainAreaPanel().setByStoredPerspective(
                            u"MainAreaPanel", mainAreaPerspective,
                            self.perspectiveTypeFactory)
                    
                    if self.getMainAreaPanel().GetPageCount() == 0:
                        self.openWikiPage(self.getWikiDocument().getWikiName())

                self.tree.SetScrollPos(wx.HORIZONTAL, 0)

                # enable the editor control whether or not the wiki root was found
#                 for dpp in self.getMainAreaPanel().getPresenters():
#                     if isinstance(dpp, DocPagePresenter):
#                         e = dpp.getSubControl("textedit")
#                         e.Enable(True)

            # update the last accessed wiki config var
            self.lastAccessedWiki(self.getWikiConfigPath())

            # Rebuild text blocks menu
            self.rereadTextBlocks()
            
            self._refreshHotKeys()
            
            # reset tray
            self.setShowOnTray()

            # trigger hook
            self.hooks.openedWiki(self, self.wikiName, wikiCombinedFilename)
    
            self.getMainAreaPanel().SetFocus()

            # return that the wiki was opened successfully
            return True
        except (IOError, OSError, DbAccessError, WikiFileNotFoundException), e:
            self.lostAccess(e)
            return False


    def setCurrentWordAsRoot(self):
        """
        Set current wiki word as root of the tree
        """
        self.setWikiWordAsRoot(self.getCurrentWikiWord())


    def setHomeWordAsRoot(self):
        self.setWikiWordAsRoot(self.getWikiDocument().getWikiName())


    def setWikiWordAsRoot(self, word):
        if not self.requireReadAccess():
            return
        try:
            if word is not None and \
                    self.getWikiDocument().isDefinedWikiLinkTerm(word):
                self.tree.setRootByWord(word)
                self.tree.expandRoot()
                self.getConfig().set("main", "tree_last_root_wiki_word", word)

        except (IOError, OSError, DbAccessError), e:
            self.lostAccess(e)
            raise


    def closeWiki(self, saveState=True):

        def errCloseAnywayMsg():
            return wx.MessageBox(_(u"There is no (write-)access to underlying wiki\n"
                    "Close anyway and loose possible changes?"),
                    _(u'Close anyway'),
                    wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION, self)


        wikiConfigPath = self.getWikiConfigPath()

        if wikiConfigPath:
            wd = self.getWikiDocument()
            # Do not require access here, otherwise the user will not be able to
            # close a disconnected wiki
            if not wd.getReadAccessFailed() and not wd.getWriteAccessFailed():
                try:
                    self.fireMiscEventKeys(("closing current wiki",))
                    self.hooks.closingWiki(self, wikiConfigPath)

                    if self.getWikiData() and saveState:
                        self.saveCurrentWikiState()
                except (IOError, OSError, DbAccessError), e:
                    self.lostAccess(e)
                    if errCloseAnywayMsg() != wx.YES:
                        raise
                    else:
                        traceback.print_exc()
                        self.fireMiscEventKeys(("dropping current wiki",))
                        self.hooks.droppingWiki(self, wikiConfigPath)

                if self.continuousExporter is not None:
                    self.continuousExporter.stopContinuousExport()
                    self.continuousExporter = None

                try:
                    self.lastAccessedWiki(self.getWikiConfigPath())
                    if self.getWikiData():
                        wd.release()
                except (IOError, OSError, DbAccessError), e:
                    # TODO: Option to show such errors
#                     traceback.print_exc()
                    pass
                self.wikiData = None
                if self.wikiDataManager is not None:
                    self.wikiDataManager.getUpdateExecutor().getMiscEvent()\
                            .removeListener(self)
                    self.currentWikiDocumentProxyEvent.setWatchedEvent(None)
                    self.wikiDataManager = None
            else:
                # We had already a problem, so ask what to do
                if errCloseAnywayMsg() != wx.YES:
                    raise LossyWikiCloseDeniedException
                
                self.fireMiscEventKeys(("dropping current wiki",))
                self.hooks.droppingWiki(self, wikiConfigPath)

                self.wikiData = None
                if self.wikiDataManager is not None:
                    self.wikiDataManager.getUpdateExecutor().getMiscEvent()\
                            .removeListener(self)
                    self.currentWikiDocumentProxyEvent.setWatchedEvent(None)
                    self.wikiDataManager = None
                
            self._refreshHotKeys()
            self.statusBarTimer.Stop()

            self.getConfig().setWikiConfig(None)
            if self.clipboardInterceptor is not None:
                self.clipboardInterceptor.catchOff()

            self.fireMiscEventKeys(("closed current wiki",))
            self.hooks.closedWiki(self, wikiConfigPath)

            self.resetGui()


    def saveCurrentWikiState(self):
        try:
            # write out the current config
            self.writeCurrentConfig()
    
            # save the current wiki page if it is dirty
            if self.isWikiLoaded():
                self.saveAllDocPages()
    
            # database commits
            if self.getWikiData():
                self.getWikiData().commit()
        except (IOError, OSError, DbAccessError), e:
            self.lostAccess(e)
            raise


    def requireReadAccess(self):
        """
        Check flag in WikiDocument if database is readable. If not, take
        measures to re-establish it. If read access is probably possible,
        return True
        """
        wd = self.getWikiDocument()
        if wd is None:
            wx.MessageBox(_(u"This operation requires an open database"),
                    _(u'No open database'), wx.OK, self)
            return False

        if not wd.getReadAccessFailed():
            return True

        while True:
            wd = self.getWikiDocument()
            if wd is None:
                return False

            self.SetFocus()
            answer = wx.MessageBox(_(u"No connection to database. "
                    u"Try to reconnect?"), _(u'Reconnect database?'),
                    wx.YES_NO | wx.YES_DEFAULT | wx.ICON_QUESTION, self)

            if answer != wx.YES:
                return False

            self.showStatusMessage(_(u"Trying to reconnect database..."), 0,
                    "reconnect")
            try:
                try:
                    wd.reconnect()
                    wd.setNoAutoSaveFlag(False)
                    wd.setReadAccessFailed(False)
                    self.requireWriteAccess()  # Just to test it  # TODO ?
                    return True  # Success
                except DbReadAccessError, e:
                    sys.stderr.write(_(u"Error while trying to reconnect:\n"))
                    traceback.print_exc()
                    self.SetFocus()
                    self.displayErrorMessage(_(u'Error while reconnecting '
                            'database'), e)
            finally:
                self.dropStatusMessageByKey("reconnect")


    def requireWriteAccess(self):
        """
        Check flag in WikiDocument if database is writable. If not, take
        measures to re-establish it. If write access is probably possible,
        return True
        """
        if not self.requireReadAccess():
            return False
        
        if not self.getWikiDocument().getWriteAccessFailed():
            return True

        while True:
            wd = self.getWikiDocument()
            if wd is None:
                return False

            self.SetFocus()
            answer = wx.MessageBox(
                    _(u"This operation needs write access to database\n"
                    u"Try to write?"), _(u'Try writing?'),
                    wx.YES_NO | wx.YES_DEFAULT | wx.ICON_QUESTION, self)

            if answer != wx.YES:
                return False

            self.showStatusMessage(_(u"Trying to write to database..."), 0,
                    "reconnect")
            try:
                try:
                    # write out the current configuration
                    self.writeCurrentConfig()
                    self.getWikiData().testWrite()

                    wd.setNoAutoSaveFlag(False)
                    wd.setWriteAccessFailed(False)
                    return True  # Success
                except (IOError, OSError, DbWriteAccessError), e:
                    sys.stderr.write(_(u"Error while trying to write:\n"))
                    traceback.print_exc()
                    self.SetFocus()
                    self.displayErrorMessage(_(u'Error while writing to '
                            'database'), e)
            finally:
                self.dropStatusMessageByKey("reconnect")


    def lostAccess(self, exc):
        if isinstance(exc, DbReadAccessError):
            self.lostReadAccess(exc)
        elif isinstance(exc, DbWriteAccessError):
            self.lostWriteAccess(exc)
        else:
            self.lostReadAccess(exc)


    def lostReadAccess(self, exc):
        """
        Called if read access was lost during an operation
        """
        if self.getWikiDocument().getReadAccessFailed():
            # Was already handled -> ignore
            return
            
        self.SetFocus()
        wx.MessageBox(_(u"Database connection error: %s.\n"
                u"Try to re-establish, then run \"Wiki\"->\"Reconnect\"") % unicode(exc),
                _(u'Connection lost'), wx.OK, self)

#         wd.setWriteAccessFailed(True) ?
        self.getWikiDocument().setReadAccessFailed(True)


    def lostWriteAccess(self, exc):
        """
        Called if write access was lost during an operation
        """
        if self.getWikiDocument().getWriteAccessFailed():
            # Was already handled -> ignore
            return

        self.SetFocus()
        wx.MessageBox(_(u"No write access to database: %s.\n"
                u" Try to re-establish, then run \"Wiki\"->\"Reconnect\"") % unicode(exc),
                _(u'Connection lost'), wx.OK, self)

        self.getWikiDocument().setWriteAccessFailed(True)


    def tryAutoReconnect(self):   # TODO ???
        """
        Try reconnect after an error, if not already tried automatically
        """
        wd = self.getWikiDocument()
        if wd is None:
            return False

        if wd.getAutoReconnectTriedFlag():
            # Automatic reconnect was tried already, so don't try again
            return False

        self.showStatusMessage(_(u"Trying to reconnect ..."), 0,
                "reconnect")
        try:
            try:
                wd.setNoAutoSaveFlag(True)
                wd.reconnect()
                wd.setNoAutoSaveFlag(False)
                return True
            except:
                sys.stderr.write(_(u"Error while trying to reconnect:") + u"\n")
                traceback.print_exc()
        finally:
            self.dropStatusMessageByKey("reconnect")

        return False


    def openFuncPage(self, funcTag, **evtprops):
        dpp = self.getCurrentDocPagePresenter()
        if dpp is None:
            dpp = self.createNewDocPagePresenterTab()

        dpp.openFuncPage(funcTag, **evtprops)


    def openWikiPage(self, wikiWord, addToHistory=True,
            forceTreeSyncFromRoot=False, forceReopen=False, **evtprops):
        if not self.requireReadAccess():
            return

        try:
            ## _prof.start()

            dpp = self.getCurrentDocPagePresenter()

            if dpp is None:
                dpp = self.createNewDocPagePresenterTab()
    
            dpp.openWikiPage(wikiWord, addToHistory, forceTreeSyncFromRoot,
                    forceReopen, **evtprops)

            self.getMainAreaPanel().showPresenter(dpp)
            ## _prof.stop()
        except (WikiFileNotFoundException, IOError, OSError, DbAccessError), e:
            self.lostAccess(e)
            return None


    def saveCurrentDocPage(self, force=False):
        dpp = self.getCurrentDocPagePresenter()
        if dpp is None:
            return
            
        dpp.saveCurrentDocPage(force)


    def activatePageByUnifiedName(self, unifName, tabMode=0, firstcharpos=-1,
            charlength=-1):
        """
        tabMode -- 0:Same tab; 2: new tab in foreground; 3: new tab in background; 6: New Window
        """
        # open the wiki page
        if tabMode & 2:
            if tabMode == 6:
                # New Window
                presenter = self.presenter.getMainControl().\
                        createNewDocPagePresenterTabInNewFrame()
            else:
                # New tab
                presenter = self.createNewDocPagePresenterTab()
        else:
            # Same tab
            presenter = self.getCurrentDocPagePresenter()
            if presenter is None:
                presenter = self.createNewDocPagePresenterTab()

        try:
            if firstcharpos != -1:
                presenter.openDocPage(unifName, motionType="random",
                        firstcharpos=firstcharpos, charlength=charlength)
            else:
                presenter.openDocPage(unifName, motionType="random")
        except WikiFileNotFoundException, e:
            self.lostAccess(e)
            return None

        if not tabMode & 1:
            # Show in foreground (if presenter is in other window, this does nothing)
            self.getMainAreaPanel().showPresenter(presenter)

        return presenter


    def saveAllDocPages(self, force = False, async=False):
        if not self.requireWriteAccess():
            return

        try:
            self.fireMiscEventProps({"saving all pages": None, "force": force})
            self.refreshPageStatus()
        except (IOError, OSError, DbAccessError), e:
            self.lostAccess(e)
            raise


    def saveDocPage(self, page, text=None):
        """
        Save page unconditionally
        """
        if page is None:
            return False

        if page.isReadOnlyEffect():
            return True   # return False?

        if not self.requireWriteAccess():
            return

        self.showStatusMessage(_(u"Saving page"), 0, "saving")
        try:
            # Test if editor is active
            if page.getTxtEditor() is None:
                # No editor -> nothing to do
                return False

#             text = page.getLiveText()

            word = page.getWikiWord()
            if word is not None:
                # trigger hooks
                self.hooks.savingWikiWord(self, word)

            while True:
                try:
                    if word is not None:
                        # only for real wiki pages
                        # TODO Enable support for AGAs again
#                         page.save(self.getActiveEditor().cleanAutoGenAreas(text))
#                         page.update(self.getActiveEditor().updateAutoGenAreas(text))   # ?
                        page.writeToDatabase()
                        self.attributeChecker.initiateCheckPage(page)

                        # trigger hooks
                        self.hooks.savedWikiWord(self, word)
                    else:
                        page.writeToDatabase()

                    self.getWikiData().commit()
                    return True
                except (IOError, OSError, DbAccessError), e:
                    self.lostAccess(e)
                    raise
        finally:
            self.dropStatusMessageByKey("saving")


    def deleteWikiWord(self, wikiWord):
        wikiDoc = self.getWikiDocument()

        if wikiWord and self.requireWriteAccess():
            try:
                if wikiDoc.isDefinedWikiLinkTerm(wikiWord):
                    page = wikiDoc.getWikiPage(wikiWord)
                    page.deletePageToTrashcan()
            except (IOError, OSError, DbAccessError), e:
                self.lostAccess(e)
                raise


    def renameWikiWord(self, wikiWord, toWikiWord, modifyText, processSubpages):
        """
        Renames current wiki word to toWikiWord.
        Returns True if renaming was done successful.
        
        modifyText -- Should the text of links to the renamed page be
                modified? (This text replacement works unreliably)
        processSubpages -- Should subpages be renamed as well?
        """
        if wikiWord is None or not self.requireWriteAccess():
            return False

        wikiDoc = self.getWikiDocument()

        try:
            if processSubpages:
                renameSeq = wikiDoc.buildRenameSeqWithSubpages(wikiWord,
                        toWikiWord)
            else:
                renameSeq = [(wikiWord, toWikiWord)]

            self.saveAllDocPages()

            # TODO Don't recycle variable names!
            for wikiWord, toWikiWord in renameSeq:

                if wikiWord == wikiDoc.getWikiName():
                    # Renaming of root word = renaming of wiki config file
                    wikiConfigFilename = wikiDoc.getWikiConfigPath()
                    self.removeFromWikiHistory(wikiConfigFilename)
    #                 self.wikiHistory.remove(wikiConfigFilename)
                    wikiDoc.renameWikiWord(wikiWord, toWikiWord,
                            modifyText)
                    # Store some additional information
                    self.lastAccessedWiki(wikiDoc.getWikiConfigPath())
                else:
                    wikiDoc.renameWikiWord(wikiWord, toWikiWord,
                            modifyText)

            return True
        except (IOError, OSError, DbAccessError), e:
            self.lostAccess(e)
            raise
        except WikiDataException, e:
            traceback.print_exc()                
            self.displayErrorMessage(unicode(e))
            return False


    def findCurrentWordInTree(self):
        try:
            self.tree.buildTreeForWord(self.getCurrentWikiWord(), selectNode=True)
        except Exception:
            traceback.print_exc()


    def makeRelUrlAbsolute(self, relurl, addSafe=''):
        """
        Return the absolute file: URL for a rel: URL
        TODO: Remove
        """
        import warnings
        warnings.warn("PersonalWikiFrame.makeRelUrlAbsolute() deprecated, use "
                "WikiDocument.makeRelUrlAbsolute()", DeprecationWarning,
                stacklevel=2)

        return self.getWikiDocument().makeRelUrlAbsolute(relurl, addSafe=addSafe)


    def makeAbsPathRelUrl(self, absPath, addSafe=''):
        """
        Return the rel: URL for an absolute file path or None if
        a relative URL can't be created.
        TODO: Remove
        """
        import warnings
        warnings.warn("PersonalWikiFrame.makeAbsPathRelUrl() deprecated, use "
                "WikiDocument.makeAbsPathRelUrl()", DeprecationWarning)

        return self.getWikiDocument().makeAbsPathRelUrl(absPath, addSafe=addSafe)


    def launchUrl(self, link):
        if link.startswith(u"wikirel://"):
            # Relative wiki link
            link = self.getWikiDocument().makeRelUrlAbsolute(link)
        elif link.startswith(u"rel://"):
            # Relative link
            link = self.getWikiDocument().makeRelUrlAbsolute(link)
        
        if not link.startswith(u"wiki:"):
            try:
                OsAbstract.startFile(self, link)
                return True
            except Exception, e:
                traceback.print_exc()
                self.displayErrorMessage(_(u"Couldn't start file"), e)
                return False
        else:
            # Open wiki
            filePath, wikiWordToOpen, anchorToOpen = StringOps.wikiUrlToPathWordAndAnchor(
                    link)
            if not os.path.exists(filePath):
                self.showStatusMessage(
                        uniToGui(_(u"Couldn't open wiki: %s") % link), -2)
                return False

            if self.configuration.getint(
                    "main", "new_window_on_follow_wiki_url") != 1:
                # Same window
                self.openWiki(filePath, wikiWordsToOpen=(wikiWordToOpen,),
                        anchorToOpen=anchorToOpen)  # ?
                return True
            else:
                # New window
                try:
                    clAction = CmdLineAction([])
                    clAction.inheritFrom(self.getCmdLineAction())
                    clAction.setWikiToOpen(link)
                    clAction.frameToOpen = 1  # Open in new frame
                    wx.GetApp().startPersonalWikiFrame(clAction)
                    return True
                except Exception, e:
                    traceback.print_exc()
                    self.displayErrorMessage(_(u'Error while starting new '
                            u'WikidPad instance'), e)
                    return False

        return False


    def refreshPageStatus(self, docPage = None):
        """
        Read information from page and present it in the field 1 of the
        status bar and in the title bar.
        """
        fmt = mbcsEnc(self.getConfig().get("main", "pagestatus_timeformat"),
                "replace")[0]

        if docPage is None:
            docPage = self.getCurrentDocPage()

        if docPage is None or not isinstance(docPage,
                (DocPages.WikiPage, DocPages.AliasWikiPage)):
            self.statusBar.SetStatusText(uniToGui(u""), 1)
            return

        pageStatus = u""   # wikiWord

        modTime, creaTime = docPage.getTimestamps()[:2]
        if modTime is not None:
#             pageStatus += _(u"Mod.: %s") % \
#                     mbcsDec(strftime(fmt, localtime(modTime)), "replace")[0]
#             pageStatus += _(u"; Crea.: %s") % \
#                     mbcsDec(strftime(fmt, localtime(creaTime)), "replace")[0]
            pageStatus += _(u"Mod.: %s") % strftimeUB(fmt, modTime)
            pageStatus += _(u"; Crea.: %s") % strftimeUB(fmt, creaTime)

        self.statusBar.SetStatusText(uniToGui(pageStatus), 1)

        self.SetTitle(uniToGui(u"%s: %s - %s - WikidPad" %
                (self.getWikiDocument().getWikiName(), docPage.getWikiWord(),
                self.getWikiConfigPath(), )))


    def viewWordSelection(self, title, words, motionType, default=None):
        """
        View a single choice to select a word to go to
        title -- Title of the dialog
        words -- Sequence of the words to choose from
        motionType -- motion type to set in openWikiPage if word was choosen
        """
        if not self.requireReadAccess():
            return
        try:
            dlg = AdditionalDialogs.ChooseWikiWordDialog(self, -1, words,
                    motionType, title, default)
            dlg.CenterOnParent(wx.BOTH)
            dlg.ShowModal()
            dlg.Destroy()
        except (IOError, OSError, DbAccessError), e:
            self.lostAccess(e)
            raise


    def viewParents(self, ofWord):
        if not self.requireReadAccess():
            return
        try:
            parents = self.getWikiData().getParentRelationships(ofWord)
        except (IOError, OSError, DbAccessError), e:
            self.lostAccess(e)
            raise

        # Check for canonical parent to set as default selection
        default = None
        canonical_parent = self.getWikiDocument().getAttributeTriples(ofWord, "parent", None)
        if canonical_parent:
            default = canonical_parent[0][2]

            # Add the canonical parent to the list if it does not exist
            if default not in parents:
                parents.append(default)
        
            
        self.viewWordSelection(_(u"Parent nodes of '%s'") % ofWord, parents,
                "parent", default)


    def viewParentLess(self):
        if not self.requireReadAccess():
            return
        try:
            parentLess = self.getWikiData().getParentlessWikiWords()
        except (IOError, OSError, DbAccessError), e:
            self.lostAccess(e)
            raise
        self.viewWordSelection(_(u"Parentless nodes"), parentLess,
                "random")


    def viewChildren(self, ofWord):
        if not self.requireReadAccess():
            return
        try:
            children = self.getWikiData().getChildRelationships(ofWord)
        except (IOError, OSError, DbAccessError), e:
            self.lostAccess(e)
            raise
        self.viewWordSelection(_(u"Child nodes of '%s'") % ofWord, children,
                "child")


    def viewBookmarks(self):
        if not self.requireReadAccess():
            return
        try:
            bookmarked = [w for w,k,v in self.getWikiDocument()
                    .getAttributeTriples(None, "bookmarked", u"true")]
        except (IOError, OSError, DbAccessError), e:
            self.lostAccess(e)
            raise
        self.viewWordSelection(_(u"Bookmarks"), bookmarked,
                "random")


    def removeFromWikiHistory(self, path):
        """
        Remove path from wiki history (if present) and sends an event.
        """
        try:
            self.wikiHistory.remove(self._getRelativeWikiPath(path))
            self.informRecentWikisChanged()
        except ValueError:
            pass

        # Try absolute
        try:
            self.wikiHistory.remove(path)
            self.informRecentWikisChanged()
        except ValueError:
            pass


    def lastAccessedWiki(self, wikiConfigFilename):
        """
        Writes to the global config the location of the last accessed wiki
        and updates file history.
        """
        wikiConfigFilename = self._getStorableWikiPath(wikiConfigFilename)

        if wikiConfigFilename == self.wikiPadHelp:
            return

        # create a new config file for the new wiki
        self.configuration.set("main", "last_wiki", wikiConfigFilename)
        if wikiConfigFilename not in self.wikiHistory:
            self.wikiHistory = [wikiConfigFilename] + self.wikiHistory

            # only keep most recent items
            maxLen = self.configuration.getint(
                    "main", "recentWikisList_length", 5)
            if len(self.wikiHistory) > maxLen:
                self.wikiHistory = self.wikiHistory[:maxLen]

            self.informRecentWikisChanged()

        self.configuration.set("main", "last_active_dir", dirname(wikiConfigFilename))
        self.writeGlobalConfig()


    # Only needed for scripts
    def setAutoSave(self, onOrOff):
        self.autoSave = onOrOff
        self.configuration.set("main", "auto_save", self.autoSave)


    def setShowTreeControl(self, onOrOff):
        self.windowLayouter.expandWindow("maintree", onOrOff)
        if onOrOff:
            self.windowLayouter.focusWindow("maintree")


    def getShowToolbar(self):
        return not self.GetToolBar() is None

    def setShowToolbar(self, onOrOff):
        """
        Control, if toolbar should be shown or not
        """
        self.getConfig().set("main", "toolbar_show", bool(onOrOff))

        if bool(onOrOff) == self.getShowToolbar():
            # Desired state already reached
            return

        if onOrOff:
            self.buildToolbar()
        else:
            self.fastSearchField = None    
            self.GetToolBar().Destroy()
            self.SetToolBar(None)


    def setShowDocStructure(self, onOrOff):
        if self.windowLayouter.containsWindow("doc structure"):
            self.windowLayouter.expandWindow("doc structure", onOrOff)
            if onOrOff:
                self.windowLayouter.focusWindow("doc structure")
        else:
            if onOrOff:
                self.configuration.set("main", "docStructure_position", u"1")
                layoutCfStr = WindowLayout.calculateMainWindowLayoutCfString(
                        self.configuration)
                self.configuration.set("main", "windowLayout", layoutCfStr)
                # Call of changeLayoutByCf() may crash so save
                # data beforehand
                self.saveCurrentWikiState()
                self.changeLayoutByCf(layoutCfStr)


    def setShowTimeView(self, onOrOff):
        if self.windowLayouter.containsWindow("time view"):
            self.windowLayouter.expandWindow("time view", onOrOff)
            if onOrOff:
                self.windowLayouter.focusWindow("time view")
        else:
            if onOrOff:
                self.configuration.set("main", "timeView_position", u"2")
                layoutCfStr = WindowLayout.calculateMainWindowLayoutCfString(
                        self.configuration)
                self.configuration.set("main", "windowLayout", layoutCfStr)
                # Call of changeLayoutByCf() may crash so save
                # data beforehand
                self.saveCurrentWikiState()
                self.changeLayoutByCf(layoutCfStr)


    def getStayOnTop(self):
        """
        Returns if this window is set to stay on top of all others
        """
        return bool(self.GetWindowStyleFlag() & wx.STAY_ON_TOP)

    def setStayOnTop(self, onOrOff):
        style = self.GetWindowStyleFlag()
        
        if onOrOff:
            style |= wx.STAY_ON_TOP
        else:
            style &= ~wx.STAY_ON_TOP

        self.SetWindowStyleFlag(style)


    def setShowOnTray(self, onOrOff=None):
        """
        Update UI and config according to the settings of onOrOff.
        If onOrOff is omitted, UI is updated according to current
        setting of the global config
        """
        if not onOrOff is None:
            self.configuration.set("main", "showontray", onOrOff)
        else:
            onOrOff = self.configuration.getboolean("main", "showontray")


        tooltip = None
        if self.getWikiConfigPath():  # If a wiki is open
            tooltip = _(u"Wiki: %s") % self.getWikiConfigPath()  # self.wikiName
            iconName = self.getConfig().get("main", "wiki_icon", u"")
        else:
            tooltip = u"Wikidpad"
            iconName = u""

        bmp = None
        if iconName != u"":
            bmp = wx.GetApp().getIconCache().lookupIcon(iconName)


        if onOrOff:
            if self.tbIcon is None:
                self.tbIcon = TaskBarIcon(self)

            if SystemInfo.isLinux():
                # On Linux, the tray icon must be resized here, otherwise
                # it might be too large.
                if bmp is not None:
                    img = bmp.ConvertToImage()
                else:
                    img = wx.Image(os.path.join(self.wikiAppDir, 'icons',
                            'pwiki.ico'), wx.BITMAP_TYPE_ICO)

                img.Rescale(20, 20)
                bmp = wx.BitmapFromImage(img)
                icon = wx.IconFromBitmap(bmp)
                self.tbIcon.SetIcon(icon, uniToGui(tooltip))
            else:
                if bmp is not None:                
                    self.tbIcon.SetIcon(wx.IconFromBitmap(bmp),
                            uniToGui(tooltip))
                else:
                    self.tbIcon.SetIcon(wx.GetApp().standardIcon,
                            uniToGui(tooltip))

        else:
            if self.tbIcon is not None:
                if self.tbIcon.IsIconInstalled():
                    self.tbIcon.RemoveIcon()

                self.tbIcon.Destroy()
                self.tbIcon = None


#         # TODO  Move to better function
#         if bmp is not None:                
#             self.SetIcon(wx.IconFromBitmap(bmp))
#         else:
#             print "setShowOnTray25", repr(os.path.join(self.wikiAppDir,
#                     'icons', 'pwiki.ico')), repr(wx.Icon(os.path.join(self.wikiAppDir,
#                     'icons', 'pwiki.ico'), wx.BITMAP_TYPE_ICO))
# #             self.SetIcon(wx.Icon(os.path.join(self.wikiAppDir,
# #                     'icons', 'pwiki.ico'), wx.BITMAP_TYPE_ICO))
#             self.SetIcon(wx.GetApp().standardIcon)


    def setHideUndefined(self, onOrOff=None):
        """
        Set if undefined WikiWords should be hidden in the tree
        """

        if not onOrOff is None:
            self.configuration.set("main", "hideundefined", onOrOff)
        else:
            onOrOff = self.configuration.getboolean("main", "hideundefined")


#     _LAYOUT_WITHOUT_VIEWSTREE = "name:main area panel;"\
#         "layout relation:%s&layout relative to:main area panel&name:maintree&"\
#             "layout sash position:170&layout sash effective position:170;"\
#         "layout relation:below&layout relative to:main area panel&name:log&"\
#             "layout sash position:1&layout sash effective position:120"
# 
#     _LAYOUT_WITH_VIEWSTREE = "name:main area panel;"\
#             "layout relation:%s&layout relative to:main area panel&name:maintree&"\
#                 "layout sash position:170&layout sash effective position:170;"\
#             "layout relation:%s&layout relative to:maintree&name:viewstree;"\
#             "layout relation:below&layout relative to:main area panel&name:log&"\
#                 "layout sash position:1&layout sash effective position:120"

    def changeLayoutByCf(self, layoutCfStr):
        """
        Create a new window layouter according to the
        layout configuration string layoutCfStr. Try to reuse and reparent
        existing windows.
        BUG: Reparenting seems to disturb event handling for tree events and
            isn't available for all OS'
        """
        # Handle no size events while realizing layout
        self.Unbind(wx.EVT_SIZE)

        self.windowLayouter.realizeNewLayoutByCf(layoutCfStr)

#         self.windowLayouter.realize()
        self.windowLayouter.layout()

        wx.EVT_SIZE(self, self.OnSize)

        self.tree = self.windowLayouter.getWindowByName("maintree")
        self.logWindow = self.windowLayouter.getWindowByName("log")


#     def getClipboardCatcher(self):
#         return self.clipboardCatcher is not None and \
#                 self.clipboardCatcher.isActive()

    def OnClipboardCatcherOff(self, evt):
        self.clipboardInterceptor.catchOff()

    def OnClipboardCatcherAtPage(self, evt):
        if self.isReadOnlyPage():
            return

        self.clipboardInterceptor.catchAtPage(self.getCurrentDocPage())

    def OnClipboardCatcherAtCursor(self, evt):
        if self.isReadOnlyPage():
            return

        self.clipboardInterceptor.catchAtCursor()


    def OnUpdateClipboardCatcher(self, evt):
        cc = self.clipboardInterceptor
        if cc is None:
            return  # Shouldn't be called anyway
            
        enableCatcher = not self.isReadOnlyPage()

        if evt.GetId() == GUI_ID.CMD_CLIPBOARD_CATCHER_OFF:
            evt.Check(cc.getMode() == cc.MODE_OFF)
        elif evt.GetId() == GUI_ID.CMD_CLIPBOARD_CATCHER_AT_CURSOR:
            evt.Enable(enableCatcher)
            evt.Check(cc.getMode() == cc.MODE_AT_CURSOR)
        elif evt.GetId() == GUI_ID.CMD_CLIPBOARD_CATCHER_AT_PAGE:
            evt.Enable(enableCatcher)
            if cc.getMode() == cc.MODE_AT_PAGE:
                evt.Check(True)
                evt.SetText(_(u"Set at Page: %s\t%s") % 
                        (self.clipboardInterceptor.getWikiWord(),
                        self.keyBindings.CatchClipboardAtPage))
            else:
                evt.Check(False)
                evt.SetText(_(u'Set at Page') + u'\t' +
                        self.keyBindings.CatchClipboardAtPage)

    def writeGlobalConfig(self):
        "writes out the global config file"
        try:
            self.configuration.save()
        except (IOError, OSError, DbAccessError), e:
            self.lostAccess(e)
            raise
        except Exception, e:
            self.displayErrorMessage(_(u"Error saving global configuration"), e)


    def writeCurrentConfig(self):
        "writes out the current config file"
        try:
            self.configuration.save()
        except (IOError, OSError, DbAccessError), e:
            self.lostAccess(e)
            raise
        except Exception, e:
            self.displayErrorMessage(_(u"Error saving current configuration"), e)


    def showWikiWordOpenDialog(self):
        AdditionalDialogs.OpenWikiWordDialog.runModal(self, self, -1)
#         dlg = OpenWikiWordDialog(self, -1)
#         try:
#             dlg.CenterOnParent(wx.BOTH)
#             dlg.ShowModal()
        self.getActiveEditor().SetFocus()
#         finally:
#             dlg.Destroy()


    def showWikiWordRenameDialog(self, wikiWord=None):
        if wikiWord is None:
            wikiWord = self.getCurrentWikiWord()

        if wikiWord is not None:
            wikiWord = self.getWikiDocument().getWikiPageNameForLinkTerm(wikiWord)

        if wikiWord is None:
            self.displayErrorMessage(_(u"No real wiki word selected to rename"))
            return

        if wikiWord == u"ScratchPad":
            self.displayErrorMessage(_(u"The scratch pad cannot be renamed."))
            return

        if self.isReadOnlyPage():
            return

        AdditionalDialogs.RenameWikiWordDialog.runModal(self, wikiWord, self, -1)
        return


#         dlg = wx.TextEntryDialog(self, uniToGui(_(u"Rename '%s' to:") %
#                 wikiWord), _(u"Rename Wiki Word"), wikiWord, wx.OK | wx.CANCEL)
# 
#         try:
#             while dlg.ShowModal() == wx.ID_OK and \
#                     not self.showWikiWordRenameConfirmDialog(wikiWord,
#                             guiToUni(dlg.GetValue())):
#                 pass
# 
#         finally:
#             dlg.Destroy()

    # TODO Unicode
    def showStoreVersionDialog(self):
        dlg = wx.TextEntryDialog (self, _(u"Description:"),
                                 _(u"Store new version"), u"",
                                 wx.OK | wx.CANCEL)

        description = None
        if dlg.ShowModal() == wx.ID_OK:
            description = dlg.GetValue()
        dlg.Destroy()

        if not description is None:
            self.saveAllDocPages()
            self.getWikiData().storeVersion(description)


    def showDeleteAllVersionsDialog(self):
        answer = wx.MessageBox(_(u"Do you want to delete all stored versions?"),
                _(u"Delete All Versions"),
                wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION, self)

        if answer == wx.YES:
            self.getWikiData().deleteVersioningData()


    def showSearchDialog(self):
        from .SearchAndReplaceDialogs import SearchWikiDialog

        if self.nonModalMainWwSearchDlg != None:
            if isinstance(self.nonModalMainWwSearchDlg, SearchWikiDialog):
                self.nonModalMainWwSearchDlg.SetFocus()
            return

        self.nonModalMainWwSearchDlg = SearchWikiDialog(self, self, -1,
                allowOkCancel=False, allowOrdering=False)
        self.nonModalMainWwSearchDlg.CenterOnParent(wx.BOTH)
        self.nonModalMainWwSearchDlg.Show()


    def showWikiWordDeleteDialog(self, wikiWord=None):
        if wikiWord is None:
            wikiWord = self.getCurrentWikiWord()

        if wikiWord is not None:
            actualWikiWord = self.getWikiDocument().getWikiPageNameForLinkTerm(
                    wikiWord)

            if actualWikiWord is None:
                # A not yet saved page is shown
                page = self.getWikiDocument().getWikiPageNoError(wikiWord)
                if page.getDirty()[0]:
                    # Page was changed already
                        self.saveAllDocPages()
                        actualWikiWord = self.getWikiDocument()\
                                .getWikiPageNameForLinkTerm(wikiWord)
                else:
                    # Unchanged unsaved page -> (pseudo-)delete without further request
                    page.pseudoDeletePage()
                    return

            wikiWord = actualWikiWord

        if wikiWord == u"ScratchPad":
            self.displayErrorMessage(_(u"The scratch pad cannot be deleted"))
            return

        if wikiWord is None:
            self.displayErrorMessage(_(u"No real wiki word to delete"))
            return
            
        if self.isReadOnlyPage():
            return   # TODO Error message

        if self.getConfig().getboolean("main", "trashcan_askOnDelete", True):
            answer = wx.MessageBox(
                    _(u"Are you sure you want to delete wiki word '%s'?") %
                    wikiWord, _(u'Delete Wiki Word'),
                    wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION, self)

            if answer != wx.YES:
                return

        try:
            self.saveAllDocPages()
            self.deleteWikiWord(wikiWord)
        except (IOError, OSError, DbAccessError), e:
            self.lostAccess(e)
            raise
        except WikiDataException, e:
            self.displayErrorMessage(unicode(e))


    def showSearchReplaceDialog(self):
        from .SearchAndReplaceDialogs import SearchPageDialog

        if self.nonModalFindDlg != None:
            if isinstance(self.nonModalFindDlg, SearchPageDialog):
                self.nonModalFindDlg.SetFocus()
            return

        self.nonModalFindDlg = SearchPageDialog(self, -1)
        self.nonModalFindDlg.CenterOnParent(wx.BOTH)
        self.nonModalFindDlg.Show()


    def showReplaceTextByWikiwordDialog(self):
        if self.getCurrentWikiWord() is None:
            self.displayErrorMessage(_(u"No real wiki word to modify"))
            return
        
        if self.isReadOnlyPage():
            return

        newWord = True
        try:
            langHelper = wx.GetApp().createWikiLanguageHelper(
                    self.getWikiDefaultWikiLanguage())
                
            absoluteLink = False
            
            text = self.getActiveEditor().GetSelectedText()

            wikiWord = langHelper.createWikiLinkFromText(
                    self.getActiveEditor().GetSelectedText().splitlines()[0],
                    bracketed=False)

            while True:
                wikiWord = guiToUni(wx.GetTextFromUser(
                        _(u"Replace text by WikiWord:"),
                        _(u"Replace by Wiki Word"), wikiWord, self))
                        
                if not wikiWord:
                    return False

                validWikiLinkCore = langHelper.extractWikiWordFromLink(wikiWord,
                        self.getWikiDocument())
        
                if validWikiLinkCore is None:
                    self.displayErrorMessage(_(u"'%s' is an invalid wiki word.") % wikiWord)
                    continue
                
                absoluteLink = langHelper.isAbsoluteLinkCore(validWikiLinkCore)

                validWikiWord = langHelper.resolveWikiWordLink(
                        validWikiLinkCore, self.getCurrentDocPage())

#                 print "--showReplaceTextByWikiwordDialog23", repr((validWikiLinkCore, langHelper.resolveWikiWordLink(validWikiLinkCore,
#                             self.getCurrentDocPage())))

                knownWikiWord = self.getWikiDocument()\
                        .getWikiPageNameForLinkTerm(validWikiWord)

                if knownWikiWord is not None:
                    answer = wx.MessageBox(uniToGui(_(
                            u'Wiki word %s exists already\n'
                            u'Would you like to append to the word?') %
                            knownWikiWord), _(u'Word exists'),
                            wx.YES_NO | wx.YES_DEFAULT | wx.ICON_QUESTION, self)
                    
                    if answer != wx.YES:
                        continue
                        
                    validWikiWord = knownWikiWord
                    newWord = False

                break

            if newWord:
                page = self.wikiDataManager.createWikiPage(validWikiWord)
                # TODO Respect template attribute?
                title = self.wikiDataManager.getWikiPageTitle(validWikiWord)
                if title is not None:
                    page.replaceLiveText(u"%s\n\n%s" % \
                            (self.wikiDataManager.formatPageTitle(title), text))
                    self.saveDocPage(page)
                else:
                    page.replaceLiveText(text)
                    self.saveDocPage(page)
            else:
                page = self.wikiDataManager.getWikiPage(validWikiWord)
                page.appendLiveText(u"\n\n" + text)


#             print "--showReplaceTextByWikiwordDialog34", repr((validWikiWord, langHelper.createLinkFromWikiWord(validWikiWord,
#                     self.getCurrentDocPage())))
            self.getActiveEditor().ReplaceSelection(
                    langHelper.createLinkFromWikiWord(validWikiWord,
                    self.getCurrentDocPage(), forceAbsolute=absoluteLink))

        except (IOError, OSError, DbAccessError), e:
            self.lostAccess(e)
            raise


    def showSelectIconDialog(self):
#         dlg = SelectIconDialog(self, -1, wx.GetApp().getIconCache())
#         dlg.CenterOnParent(wx.BOTH)
#         if dlg.ShowModal() == wx.ID_OK:
#             iconname = dlg.GetValue()
# 
#         dlg.Destroy()
# 
        iconname = AdditionalDialogs.SelectIconDialog.runModal(self, -1,
                wx.GetApp().getIconCache())

        if iconname:
            self.insertAttribute("icon", iconname)

    def showDateformatDialog(self):
        fmt = self.configuration.get("main", "strftime")

        dlg = AdditionalDialogs.DateformatDialog(self, -1, self, deffmt = fmt)
        dlg.CenterOnParent(wx.BOTH)
        dateformat = None

        if dlg.ShowModal() == wx.ID_OK:
            dateformat = dlg.GetValue()
        dlg.Destroy()

        if not dateformat is None:
            self.configuration.set("main", "strftime", dateformat)

    def showOptionsDialog(self, startPanelName=None):
        from .OptionsDialog import OptionsDialog

        dlg = OptionsDialog(self, -1, startPanelName=startPanelName)
        dlg.CenterOnParent(wx.BOTH)

        answer = dlg.ShowModal()
        oldSettings = dlg.getOldSettings()
        
        dlg.Destroy()

        if answer == wx.ID_OK:
            # Perform operations to reset GUI parts after option changes
            self.autoSaveDelayAfterKeyPressed = self.configuration.getint(
                    "main", "auto_save_delay_key_pressed")
            self.autoSaveDelayAfterDirty = self.configuration.getint(
                    "main", "auto_save_delay_dirty")
            maxLen = self.configuration.getint(
                    "main", "recentWikisList_length", 5)
            self.wikiHistory = self.wikiHistory[:maxLen]

            self.setShowOnTray()
            self.setHideUndefined()
            self.rereadRecentWikis()
            self.refreshPageStatus()
            
            # TODO Move this to WikiDataManager!
            # Set file storage according to configuration
            
            if self.getWikiDocument() is not None:
                fs = self.getWikiDocument().getFileStorage()
                
                fs.setModDateMustMatch(self.configuration.getboolean("main",
                        "fileStorage_identity_modDateMustMatch", False))
                fs.setFilenameMustMatch(self.configuration.getboolean("main",
                        "fileStorage_identity_filenameMustMatch", False))
                fs.setModDateIsEnough(self.configuration.getboolean("main",
                        "fileStorage_identity_modDateIsEnough", False))


            relayoutNeeded = False
            # Build new layout config string
            for setName in ("mainTree_position", "viewsTree_position",
                    "docStructure_position", "timeView_position"):
                if self.configuration.getint("main", setName, 0) != \
                        int(oldSettings.get(setName, u"0")):
                    relayoutNeeded = True
                    break
 
            if relayoutNeeded:
                layoutCfStr = WindowLayout.calculateMainWindowLayoutCfString(
                        self.configuration)
                self.configuration.set("main", "windowLayout", layoutCfStr)
                # Call of changeLayoutByCf() may crash so save
                # data beforehand
                self.saveCurrentWikiState()
                self.changeLayoutByCf(layoutCfStr)
            
            self.userActionCoord.applyConfiguration()
            self._refreshHotKeys()

            wx.GetApp().fireMiscEventProps({"options changed": True,
                    "old config settings": oldSettings})


    def OnCmdExportDialog(self, evt):
        self.saveAllDocPages()
        self.getWikiData().commit()

        dlg = AdditionalDialogs.ExportDialog(self, -1, continuousExport=False)
        dlg.CenterOnParent(wx.BOTH)

        dlg.ShowModal()
        dlg.Destroy()


    def OnCmdContinuousExportDialog(self, evt):
        if self.continuousExporter is not None:
            self.continuousExporter.stopContinuousExport()
            self.continuousExporter = None
            return

        self.saveAllDocPages()
        self.getWikiData().commit()

        dlg = AdditionalDialogs.ExportDialog(self, -1, continuousExport=True)
        try:
            dlg.CenterOnParent(wx.BOTH)
    
            dlg.ShowModal()
            exporter = dlg.GetValue()
            self.continuousExporter = exporter
        finally:
            dlg.Destroy()


    def OnUpdateContinuousExportDialog(self, evt):
        evt.Check(self.continuousExporter is not None)


    EXPORT_PARAMS = {
            GUI_ID.MENU_EXPORT_WHOLE_AS_PAGE:
                    (u"html_multi", None),
            GUI_ID.MENU_EXPORT_WHOLE_AS_PAGES:
                    (u"html_single", None),
            GUI_ID.MENU_EXPORT_WORD_AS_PAGE:
                    (u"html_multi", None),
            GUI_ID.MENU_EXPORT_SUB_AS_PAGE:
                    (u"html_multi", None),
            GUI_ID.MENU_EXPORT_SUB_AS_PAGES:
                    (u"html_single", None),
            GUI_ID.MENU_EXPORT_WHOLE_AS_RAW:
                    (u"raw_files", (1,))
            }


    def OnExportWiki(self, evt):
        import SearchAndReplace as Sar

        defdir = self.getConfig().get("main", "export_default_dir", u"")
        if defdir == u"":
            defdir = self.getLastActiveDir()
        
        typ = evt.GetId()
        # Export to dir
        with TopLevelLocker:
            dest = wx.DirSelector(_(u"Select Export Directory"), defdir,
                    wx.DD_DEFAULT_STYLE|wx.DD_NEW_DIR_BUTTON, parent=self)

        try:
            if dest:
                if typ in (GUI_ID.MENU_EXPORT_WHOLE_AS_PAGE,
                        GUI_ID.MENU_EXPORT_WHOLE_AS_PAGES,
                        GUI_ID.MENU_EXPORT_WHOLE_AS_RAW):
                    # Export whole wiki
    
                    lpOp = Sar.ListWikiPagesOperation()
                    item = Sar.AllWikiPagesNode(lpOp)
                    lpOp.setSearchOpTree(item)
                    lpOp.ordering = "asroottree"  # Slow, but more intuitive
                    sarOp = Sar.SearchReplaceOperation()
                    sarOp.listWikiPagesOp = lpOp
#                     wordList = self.getWikiDocument().searchWiki(lpOp)
                    wordList = self.getWikiDocument().searchWiki(sarOp)
    
                elif typ in (GUI_ID.MENU_EXPORT_SUB_AS_PAGE,
                        GUI_ID.MENU_EXPORT_SUB_AS_PAGES):
                    # Export a subtree of current word
                    if self.getCurrentWikiWord() is None:
                        self.displayErrorMessage(
                                _(u"No real wiki word selected as root"))
                        return
                    lpOp = Sar.ListWikiPagesOperation()
                    item = Sar.ListItemWithSubtreeWikiPagesNode(lpOp,
                            [self.getCurrentWikiWord()], -1)
                    lpOp.setSearchOpTree(item)
                    lpOp.ordering = "asroottree"  # Slow, but more intuitive

                    sarOp = Sar.SearchReplaceOperation()
                    sarOp.listWikiPagesOp = lpOp
#                     wordList = self.getWikiDocument().searchWiki(lpOp)
                    wordList = self.getWikiDocument().searchWiki(sarOp)
    
                else:
                    if self.getCurrentWikiWord() is None:
                        self.displayErrorMessage(
                                _(u"No real wiki word selected as root"))
                        return

                    wordList = (self.getCurrentWikiWord(),)

                exptype, addopt = self.EXPORT_PARAMS[typ]
                
                self.saveAllDocPages()
                self.getWikiData().commit()

                ob = PluginManager.getSupportedExportTypes(self, None, False)[exptype][0]
#                 ob = expclass(self)

                if addopt is None:
                    # Additional options not given -> take default provided by exporter
                    addopt = ob.getAddOpt(None)

                pgh = ProgressHandler(_(u"Exporting"), u"", 0, self)
                pgh.open(0)
                pgh.update(0, _(u"Preparing"))

                try:
                    ob.export(self.getWikiDocument(), wordList, exptype, dest,
                            False, addopt, pgh)
                except ExportException, e:
                    self.displayErrorMessage(_(u"Error on export"), e)
                finally:
                    pgh.close()

                self.configuration.set("main", "last_active_dir", dest)

        except (IOError, OSError, DbAccessError), e:
            self.lostAccess(e)
            raise


    def OnCmdImportDialog(self, evt):
        if self.isReadOnlyWiki():
            return

        self.saveAllDocPages()
        self.getWikiData().commit()

        dlg = AdditionalDialogs.ImportDialog(self, -1, self)
        dlg.CenterOnParent(wx.BOTH)

        dlg.ShowModal()
        dlg.Destroy()


    def showSpellCheckerDialog(self):
        if self.spellChkDlg != None:
            return
        try:
            self.spellChkDlg = SpellChecker.SpellCheckerDialog(self, -1, self)
        except (IOError, OSError, DbAccessError), e:
            self.lostAccess(e)
            raise

        self.spellChkDlg.CenterOnParent(wx.BOTH)
        self.spellChkDlg.Show()
        self.spellChkDlg.checkNext(startPos=0)


    def OnCmdCheckSpellCheckWhileType(self, evt):        
        self.configuration.set("main", "editor_onlineSpellChecker_active",
                evt.IsChecked())
        oldSettings = {"editor_onlineSpellChecker_active":
                not evt.IsChecked()}
                
        self.configuration.informChanged(oldSettings)

    def OnUpdateSpellCheckWhileType(self, evt):
        editor = self.getActiveEditor()
        
        evt.Check( editor is not None and self.configuration.getboolean("main",
                "editor_onlineSpellChecker_active", False) )
        evt.Enable(editor is not None)


    def resetSpellCheckWhileTypeIgnoreList(self):
        wikiDoc = self.getWikiDocument()
        if wikiDoc is None:
            return
        
        scs = wikiDoc.getOnlineSpellCheckerSession()
        if scs is None:
            return
        
        scs.resetIgnoreListSession()


    def initiateFullUpdate(self, skipConfirm=False):
        if self.isReadOnlyWiki():
            return

        if not skipConfirm:
            answer = wx.MessageBox(_(u"Are you sure you want to start a full "
                    u"rebuild of wiki in background?"),
                    _(u'Initiate update'),
                    wx.YES_NO | wx.YES_DEFAULT | wx.ICON_QUESTION, self)

        if skipConfirm or answer == wx.YES :
            try:
                self.saveAllDocPages()
                progresshandler = ProgressHandler(
                        _(u"     Initiating update     "),
                        _(u"     Initiating update     "), 0, self)
                self.getWikiDocument().initiateFullUpdate(progresshandler)
        
    #         self.tree.collapse()
    # 
    #         # TODO Adapt for functional pages
    #         if self.getCurrentWikiWord() is not None:
    #             self.openWikiPage(self.getCurrentWikiWord(),
    #                     forceTreeSyncFromRoot=True)
    #         self.tree.expandRoot()
            except (IOError, OSError, DbAccessError), e:
                self.lostAccess(e)
                raise
            except Exception, e:
                self.displayErrorMessage(_(u"Error initiating update"), e)
                traceback.print_exc()


    def rebuildWiki(self, skipConfirm=False, onlyDirty=False):
        if self.isReadOnlyWiki():
            return

        if not skipConfirm:
            answer = wx.MessageBox(_(u"Are you sure you want to rebuild this wiki? "
                    u"You may want to backup your data first!"),
                    _(u'Rebuild wiki'),
                    wx.YES_NO | wx.YES_DEFAULT | wx.ICON_QUESTION, self)

        if skipConfirm or answer == wx.YES :
            try:
                self.saveAllDocPages()
                progresshandler = ProgressHandler(
                        _(u"     Rebuilding wiki     "),
                        _(u"     Rebuilding wiki     "), 0, self)
                self.getWikiDocument().rebuildWiki(progresshandler,
                        onlyDirty=onlyDirty)

                self.tree.collapse()

                # TODO Adapt for functional pages
                if self.getCurrentWikiWord() is not None:
                    self.openWikiPage(self.getCurrentWikiWord(),
                            forceTreeSyncFromRoot=True)
                self.tree.expandRoot()
            except (IOError, OSError, DbAccessError), e:
                self.lostAccess(e)
                raise
            except Exception, e:
                self.displayErrorMessage(_(u"Error rebuilding wiki"), e)
                traceback.print_exc()



    def rebuildSearchIndex(self, skipConfirm=True, onlyDirty=False):
        if self.isReadOnlyWiki():
            return

# Removed from .pot

#         if not skipConfirm:
#             answer = wx.MessageBox(_(u"Are you sure you want to rebuild this wiki? "
#                     u"You may want to backup your data first!"),
#                     _(u'Rebuild wiki'),
#                     wx.YES_NO | wx.YES_DEFAULT | wx.ICON_QUESTION, self)
# 
#         if skipConfirm or answer == wx.YES :
#             try:
#                 self.saveAllDocPages()
#                 progresshandler = ProgressHandler(
#                         _(u"     Reindexing wiki     "),
#                         _(u"     Reindexing wiki     "), 0, self)
#                 self.getWikiDocument().rebuildSearchIndex(progresshandler,
#                         onlyDirty=onlyDirty)
#             except (IOError, OSError, DbAccessError), e:
#                 self.lostAccess(e)
#                 raise
#             except Exception, e:
#                 self.displayErrorMessage(_(u"Error reindexing wiki"), e)
#                 traceback.print_exc()



    def updateExternallyModFiles(self):
        if self.isReadOnlyWiki():
            return

        # TODO Progresshandler?
        self.getWikiDocument().initiateExtWikiFileUpdate()
        # self.checkFileSignatureForAllWikiPageNamesAndMarkDirty()
        # self.getWikiDocument().pushDirtyMetaDataUpdate()


    def OnCmdUpdateExternallyModFiles(self, evt):
        self.updateExternallyModFiles()


    def vacuumWiki(self):
        if self.isReadOnlyWiki():
            return

        try:
            self.getWikiData().vacuum()
        except (IOError, OSError, DbAccessError), e:
            self.lostAccess(e)
            raise


    def OnCmdCloneWindow(self, evt):
        wd = self.getWikiDocument()
        if wd is None:
            return

        try:
            clAction = CmdLineAction([])
            clAction.inheritFrom(self.getCmdLineAction())
            clAction.wikiToOpen = wd.getWikiConfigPath()
            clAction.frameToOpen = 1  # Open in new frame
            wws, subCtrls, activeNo = \
                    self.getMainAreaPanel().getOpenWikiWordsSubCtrlsAndActiveNo()

            if wws is not None:
                clAction.wikiWordsToOpen = wws
                clAction.lastTabsSubCtrls = subCtrls
                clAction.activeTabNo = activeNo

            wx.GetApp().startPersonalWikiFrame(clAction)
        except Exception, e:
            traceback.print_exc()
            self.displayErrorMessage(_(u'Error while starting new '
                    u'WikidPad instance'), e)
            return


    def OnImportFromPagefiles(self, evt):
        if self.isReadOnlyWiki():
            return

        dlg=wx.MessageDialog(self,
                _(u"This could overwrite pages in the database. Continue?"),
                _(u"Import pagefiles"), wx.YES_NO)

        answer = dlg.ShowModal()
        if answer == wx.ID_YES:
            self.getWikiData().copyWikiFilesToDatabase()


    def setDocPagePresenterSubControl(self, scName):
        presenter = self.getCurrentDocPagePresenter()
        if presenter is None:
            return
        
        if scName is None:
            self.getMainAreaPanel().switchDocPagePresenterTabEditorPreview(
                    presenter)
        else:
            presenter.switchSubControl(scName, gainFocus=True)

        

#     def OnCmdSwitchEditorPreview(self, evt):
#         presenter = self.getCurrentDocPagePresenter()
#         if presenter is None:
#             return
# 
#         self.getMainAreaPanel().switchDocPagePresenterTabEditorPreview(presenter)


    def insertAttribute(self, key, value, wikiWord=None):
        langHelper = wx.GetApp().createWikiLanguageHelper(
                self.getWikiDefaultWikiLanguage())

        if wikiWord is None:
            attr = langHelper.createAttributeFromComponents(key, value)
            self.getActiveEditor().AppendText(attr)
        else:
            try:
                # self.saveCurrentDocPage()
                if self.getWikiDocument().isDefinedWikiLinkTerm(wikiWord):
                    page = self.getWikiDocument().getWikiPage(wikiWord)
                    attr = langHelper.createAttributeFromComponents(key, value,
                            page)
                    page.appendLiveText(attr)
            except (IOError, OSError, DbAccessError), e:
                self.lostAccess(e)
                raise


    def addText(self, text, replaceSel=False):
        """
        Add text to current active editor view
        """
        ed = self.getActiveEditor()
        ed.BeginUndoAction()
        try:
            if replaceSel:
                ed.ReplaceSelection(text)
            else:
                ed.AddText(text)
        finally:
            ed.EndUndoAction()


    def appendText(self, text):
        """
        Append text to current active editor view
        """
        ed = self.getActiveEditor()
        ed.BeginUndoAction()
        try:
            self.getActiveEditor().AppendText(text)
        finally:
            ed.EndUndoAction()


    def getLastActiveDir(self):
        return self.configuration.get("main", "last_active_dir", os.getcwd())

    
    def stdDialog(self, dlgtype, title, message, additional=None):
        """
        Used to show a dialog, especially in scripts.
        Possible values for dlgtype:
        "text": input text to dialog, additional is the default text
            when showing dlg returns entered text on OK or empty string
        "listmcstr": List with multiple choices, additional is a sequence of
            strings to fill the UI list with, returns a Python list with the
            selected strings or None if dialog was aborted.
        "o": As displayMessage, shows only OK button
        "oc": Shows OK and Cancel buttons, returns either "ok" or "cancel"
        "yn": Yes and No buttons, returns either "yes" or "no"
        "ync": like "yn" but with additional cancel button, can also return
            "cancel"
        """
        if dlgtype == "text":
            if additional is None:
                additional = u""
            return guiToUni(wx.GetTextFromUser(uniToGui(message),
                    uniToGui(title), uniToGui(additional), self))
        elif dlgtype == "listmcstr":
            if additional is None:
                raise RuntimeError(
                        _(u'No list of strings passed to "listmcstr" dialog'))
            multidlg = wx.MultiChoiceDialog(self, uniToGui(message),
                    uniToGui(title), list(additional))
            try:
                if (multidlg.ShowModal() == wx.ID_OK):
                    selections = multidlg.GetSelections()
                    return [additional[x] for x in selections]
                else:
                    return None
            finally:
                multidlg.Destroy()
        else:
            style = None
            if dlgtype == "o":
                style = wx.OK
            elif dlgtype == "oc":
                style = wx.OK | wx.CANCEL
            elif dlgtype == "yn":
                style = wx.YES_NO
            elif dlgtype == "ync":
                style = wx.YES_NO | wx.CANCEL

            if style is None:
                raise RuntimeError(_(u"Unknown dialog type"))

            answer = wx.MessageBox(uniToGui(message), uniToGui(title), style, self)
            
            if answer == wx.OK:
                return "ok"
            elif answer == wx.CANCEL:
                if dlgtype == "yn":
                    return "no"
                else:
                    return "cancel"
            elif answer == wx.YES:
                return "yes"
            elif answer == wx.NO:
                return "no"
                
            raise InternalError(u"Unexpected result from MessageBox in stdDialog()")


    def showStatusMessage(self, msg, duration=0, key=None):
        """
        If duration > 0 the message is removed after  duration  milliseconds.
        If duration == 0 show forever (until new message overwrites)
        If duration == -1 show for a default length (ten seconds currently)
        If duration == -2 show for a long default length (45 seconds currently).
                Intended for error messages
        
        key -- if given you can remove message(s) with this key by using
                self.dropStatusMessage(key). Messages with other keys
                remain until overwritten (for duration == 0) or the end
                of their duration time.
        """
        self.statusBarTimer.Stop()
        
        if duration == 0 and key == None:
            self.statusBar.SetStatusText(msg, 0)
            return
        
        if duration == -1:
            duration = 10000
        elif duration == -2:
            duration = 45000
            
        self.statusBarStack.append(_StatusBarStackEntry(msg, duration, key))
        self._updateStatusBarByStack()


    def updateStatusMessage(self, msg, key, duration=0):
        """
        Delete all messages with key  key  and place this new one on the top.
        """
        self.statusBarTimer.Stop()

        self.statusBarStack = [e for e in self.statusBarStack if e.key != key]
        self.showStatusMessage(msg, duration, key)


    def dropStatusMessageByKey(self, key):
        """
        Delete all messages with given key from stack
        """
        if len(self.statusBarStack) == 0:
            return
        
        update = self.statusBarStack[-1].key == key
        
        self.statusBarStack = [e for e in self.statusBarStack if e.key != key]
        
        if update:
            self._updateStatusBarByStack()


    def _updateStatusBarByStack(self):
#         print "--_updateStatusBarByStack1", repr((wx.Thread_IsMain(), wx.GetApp().IsMainLoopRunning()))
        try:
            if not wx.GetApp().IsMainLoopRunning():
                return

            Utilities.callInMainThreadAsync(self.statusBarTimer.Stop)
    #         self.statusBarTimer.Stop()

            if len(self.statusBarStack) == 0:
                self.statusBar.SetStatusText(u"", 0)
                return
                
            # Just in case: Restrict stack size
            if len(self.statusBarStack) > 50:
                self.statusBarStack = self.statusBarStack[(len(self.statusBarStack) - 50):]
    
            msg, duration, key = self.statusBarStack[-1]
    
            self.statusBar.SetStatusText(msg, 0)
            if duration != 0:
                    Utilities.callInMainThreadAsync(self.statusBarTimer.Stop)
        #             self.statusBarTimer.Start(duration, True)
        except:
            print "----- Caught error start -----"
            traceback.print_exc()
            print "----- Caught error end -----"


    def OnStatusBarTimer(self, evt):
        if len(self.statusBarStack) == 0:
            self.statusBar.SetStatusText(u"", 0)
            return

        del self.statusBarStack[-1]
        self._updateStatusBarByStack()


    def displayMessage(self, title, str):
        """pops up a dialog box,
        used by scripts only
        """
        dlg_m = wx.MessageDialog(self, uniToGui(u"%s" % str), title, wx.OK)
        dlg_m.ShowModal()
        dlg_m.Destroy()


    def displayErrorMessage(self, errorStr, e=u""):
        "pops up a error dialog box"
        if errorStr != "":
            msg = errorStr + "."
        else:
            msg = ""
        
        if str(e) != "":
            msg += " %s." % e 
        
        dlg_m = wx.MessageDialog(self, uniToGui(msg),  # u"%s. %s." % (errorStr, e)
                _(u'Error!'), wx.OK)
        dlg_m.ShowModal()
        dlg_m.Destroy()
#         try:
#             self.showStatusMessage(uniToGui(errorStr), -2)
#         except:
#             pass


    def showAboutDialog(self):
        dlg = AdditionalDialogs.AboutDialog(self)
        dlg.ShowModal()
        dlg.Destroy()
    
    def OnShowOptionalComponentErrorLog(self, evt):
        import ExceptionLogger
        AdditionalDialogs.ShowStaticHtmlTextDialog.runModal(self,
                _(u"Optional component error log"),
                textContent=ExceptionLogger.getOptionalComponentErrorLog())


    def OnShowPrintMainDialog(self, evt=None, exportTo=-1):
        if self.printer is None:
            from .Printing import Printer
            self.printer = Printer(self)

        self.printer.showPrintMainDialog(exportTo=exportTo)


    def OnShowWikiPropertiesDialog(self, evt):
        dlg = AdditionalDialogs.WikiPropertiesDialog(self, -1, self)
        dlg.ShowModal()
        dlg.Destroy()

    def OnCmdShowWikiJobDialog(self, evt):
        dlg = AdditionalDialogs.WikiJobDialog(self, -1, self)
        dlg.ShowModal()
        dlg.Destroy()


    # ----------------------------------------------------------------------------------------
    # Event handlers from here on out.
    # ----------------------------------------------------------------------------------------


    def miscEventHappened(self, miscEvt):
        """
        Handle misc events
        """
        try:
            if miscEvt.getSource() is self.getWikiDocument():
                # Event from wiki document aka wiki data manager
                if miscEvt.has_key("deleted wiki page"):
                    wikiPage = miscEvt.get("wikiPage")
                    # trigger hooks
                    self.hooks.deletedWikiWord(self,
                            wikiPage.getWikiWord())
    
#                     self.fireMiscEventProps(miscEvt.getProps())
    
                elif miscEvt.has_key("renamed wiki page"):
                    oldWord = miscEvt.get("wikiPage").getWikiWord()
                    newWord = miscEvt.get("newWord")

                    # trigger hooks
                    self.hooks.renamedWikiWord(self, oldWord, newWord)

#                 elif miscEvt.has_key("updated wiki page"):
#                     # This was send from a WikiDocument(=WikiDataManager) object,
#                     # send it again to listening components
#                     self.fireMiscEventProps(miscEvt.getProps())
            elif miscEvt.getSource() is self.getMainAreaPanel():
                self.fireMiscEventProps(miscEvt.getProps())
#                 if miscEvt.has_key("changed current docpage presenter"):
#                     self.hooks.switchedToWikiWord(self, oldWord, newWord)

            elif self.isWikiLoaded() and miscEvt.getSource() is \
                    self.getWikiDocument().getUpdateExecutor():
                if miscEvt.has_key("changed state"):
                    # Update executor started/stopped/ran empty/was filled
                    if miscEvt.get("isRunning"):
                        jobCount = miscEvt.get("jobCount")
                    else:
                        jobCount = 0
                     
                    if jobCount > 0:
                        self.updateStatusMessage(
                                _("Performing background jobs..."),
                                key="jobInfo", duration=300000)
                    else:
                        self.dropStatusMessageByKey("jobInfo")


            # Depending on wiki-related or global func. page, the following
            # events come from document or application object

            if (miscEvt.getSource() is self.getWikiDocument()) or \
                   (miscEvt.getSource() is wx.GetApp()):
                if miscEvt.has_key("reread text blocks needed"):
                    self.rereadTextBlocks()
#                 elif miscEvt.has_key("reread personal word list needed"):
#                     if self.spellChkDlg is not None:
#                         self.spellChkDlg.rereadPersonalWordLists()
                elif miscEvt.has_key("reread favorite wikis needed"):
                    self.rereadFavoriteWikis()
                elif miscEvt.has_key("reread recent wikis needed"):
                    self.rereadRecentWikis()


        except (IOError, OSError, DbAccessError), e:
            self.lostAccess(e)
            raise


    def getDefDirForWikiOpenNew(self):
        """
        Return the appropriate default directory to start when user
        wants to create a new or open an existing wiki.
        """
        startDir = self.getConfig().get("main",
                "wikiOpenNew_defaultDir", u"")
        if startDir == u"":
            startDir = self.getWikiConfigPath()
            if startDir is None:
                startDir = self.getLastActiveDir()
            else:
                startDir = dirname(dirname(startDir))
        
        return startDir


    def OnWikiOpen(self, event):
        oldfocus = wx.Window.FindFocus()

        with TopLevelLocker:
            path = wx.FileSelector(_(u"Choose a Wiki to open"),
                    self.getDefDirForWikiOpenNew(), wildcard=u"*.wiki",
                    flags=wx.FD_OPEN, parent=self)

#         dlg = wx.FileDialog(self, _(u"Choose a Wiki to open"),
#                 self.getDefDirForWikiOpenNew(), "", "*.wiki", wx.OPEN)
        if path:
            self.openWiki(mbcsDec(os.path.abspath(path), "replace")[0])
        else:
            if oldfocus is not None:
                oldfocus.SetFocus()
#         dlg.Destroy()


    def OnWikiOpenNewWindow(self, event):
        oldfocus = wx.Window.FindFocus()

        with TopLevelLocker:
            path = wx.FileSelector(_(u"Choose a Wiki to open"),
                    self.getDefDirForWikiOpenNew(), wildcard=u"*.wiki",
                    flags=wx.FD_OPEN, parent=self)
#         dlg = wx.FileDialog(self, _(u"Choose a Wiki to open"),
#                 self.getDefDirForWikiOpenNew(), "", "*.wiki", wx.OPEN)
        if path:
            try:
                clAction = CmdLineAction([])
                clAction.inheritFrom(self.getCmdLineAction())
                clAction.wikiToOpen = mbcsDec(os.path.abspath(path), "replace")[0]
                clAction.frameToOpen = 1  # Open in new frame
                wx.GetApp().startPersonalWikiFrame(clAction)
            except Exception, e:
                traceback.print_exc()
                self.displayErrorMessage(_(u'Error while starting new '
                        u'WikidPad instance'), e)
                return
        else:
            oldfocus.SetFocus()

#         dlg.Destroy()


    def OnWikiOpenAsType(self, event):
        with TopLevelLocker:
            path = wx.FileSelector(_(u"Choose a Wiki to open"),
                    self.getDefDirForWikiOpenNew(), wildcard=u"*.wiki",
                    flags=wx.FD_OPEN, parent=self)

#         dlg = wx.FileDialog(self, _(u"Choose a Wiki to open"),
#                 self.getDefDirForWikiOpenNew(), "", "*.wiki", wx.OPEN)
        if path:
            self.openWiki(mbcsDec(os.path.abspath(path), "replace")[0],
                    ignoreWdhName=True)
#         dlg.Destroy()


    def OnWikiNew(self, event):
        dlg = wx.TextEntryDialog (self,
                _(u"Name for new wiki (must be in the form of a WikiWord):"),
                _(u"Create New Wiki"), u"MyWiki", wx.OK | wx.CANCEL)

        if dlg.ShowModal() == wx.ID_OK:
            wikiName = guiToUni(dlg.GetValue())
            userLangHelper = wx.GetApp().createWikiLanguageHelper(
                    wx.GetApp().getUserDefaultWikiLanguage())

            wikiName = userLangHelper.extractWikiWordFromLink(wikiName)
            # TODO: Further measures to exclude prohibited characters!!!

            # make sure this is a valid wiki word
            errMsg = userLangHelper.checkForInvalidWikiWord(wikiName)

            if errMsg is None:
                with TopLevelLocker:
                    dirPath = wx.DirSelector(_(u"Directory to store new wiki"),
                            self.getDefDirForWikiOpenNew(),
                            style=wx.DD_DEFAULT_STYLE|wx.DD_NEW_DIR_BUTTON,
                            parent=self)

#                 dlg = wx.DirDialog(self, _(u"Directory to store new wiki"),
#                         self.getDefDirForWikiOpenNew(),
#                         style=wx.DD_DEFAULT_STYLE|wx.DD_NEW_DIR_BUTTON)
                if dirPath:
                    self.newWiki(wikiName, dirPath)
            else:
                self.displayErrorMessage(_(u"'%s' is an invalid wiki word. %s")
                        % (wikiName, errMsg))

        dlg.Destroy()


    def OnIdle(self, evt):
        self.fireMiscEventKeys(("idle visible",))
        
        # TODO: Maybe called a bit too often for statusbar check?
        if self.statusBar.GetStatusText(0) == u"":
            self._updateStatusBarByStack()

        if not self.configuration.getboolean("main", "auto_save"):  # self.autoSave:
            return
        if self.getWikiDocument() is None or self.getWikiDocument().getWriteAccessFailed():
            # No automatic saving due to previous error
            return

        # check if the current wiki page needs to be saved
        if self.getCurrentDocPage():
            (saveDirtySince, updateDirtySince) = \
                    self.getCurrentDocPage().getDirtySince()
            if saveDirtySince is not None:
                currentTime = time.time()
                # only try and save if the user stops typing
                if (currentTime - self.getActiveEditor().lastKeyPressed) > \
                        self.autoSaveDelayAfterKeyPressed:
#                     if saveDirty:
                    if (currentTime - saveDirtySince) > \
                            self.autoSaveDelayAfterDirty:
                        self.saveAllDocPages()
#                     elif updateDirty:
#                         if (currentTime - self.currentWikiPage.lastUpdate) > 5:
#                             self.updateRelationships()

    def OnSize(self, evt):
        if self.windowLayouter is not None:
            self.windowLayouter.layout()


    def OnActivate(self, evt):
        evt.Skip()
        if evt.GetActive():
            wx.UpdateUIEvent.SetUpdateInterval(0)
#             wx.IdleEvent.SetMode(wx.IDLE_PROCESS_SPECIFIED)
        else:
            wx.UpdateUIEvent.SetUpdateInterval(-1)
#             wx.IdleEvent.SetMode(wx.IDLE_PROCESS_ALL)


    def isReadOnlyWiki(self):
        wikiDoc = self.getWikiDocument()
        return (wikiDoc is None) or wikiDoc.isReadOnlyEffect()


    def isReadOnlyPage(self):
        docPage = self.getCurrentDocPage()
        return (docPage is None) or docPage.isReadOnlyEffect()
                

    # All OnUpdateDis* methods only disable a menu/toolbar item, they
    # never enable. This allows to build chains of them where each
    # condition is checked which may disable the item (before running the
    # chain the item is enabled by _buildChainedUpdateEventFct()

    def OnUpdateDisNoWiki(self, evt):
        """
        Called for ui-update to disable menu item if no wiki loaded.
        """
        if not self.isWikiLoaded():
            evt.Enable(False)

    def OnUpdateDisReadOnlyWiki(self, evt):
        """
        Called for ui-update to disable menu item if wiki is read-only.
        """
        if self.isReadOnlyWiki():
            evt.Enable(False)


    def OnUpdateDisReadOnlyPage(self, evt):
        """
        Called for ui-update to disable menu item if page is read-only.
        """
        if self.isReadOnlyPage():
            evt.Enable(False)

    def OnUpdateDisNotTextedit(self, evt):
        """
        Disables item if current presenter doesn't show textedit subcontrol.
        """
        pres = self.getCurrentDocPagePresenter()
        if pres is None or pres.getCurrentSubControlName() != "textedit":
            evt.Enable(False)

    def OnUpdateDisNotWikiPage(self, evt):
        """
        Disables item if current presenter doesn't show a real wiki page.
        """
        if self.getCurrentWikiWord() is None:
            evt.Enable(False)            

    def OnUpdateDisNotHtmlOnClipboard(self, evt):
        """
        Disables item if HTML data is not available on clipboard
        """
        if not wxHelper.getHasHtmlOnClipboard()[0]:
            evt.Enable(False)            


    def OnCmdCheckWrapMode(self, evt):
        editor = self.getActiveEditor()
        if editor is None and \
                self.getMainAreaPanel().getCurrentSubControlName() == "inline diff":
            editor = self.getMainAreaPanel().getCurrentSubControl()

        editor.setWrapMode(evt.IsChecked())
        self.configuration.set("main", "wrap_mode", evt.IsChecked())

    def OnUpdateWrapMode(self, evt):
        editor = self.getActiveEditor()
        if editor is None and \
                self.getMainAreaPanel().getCurrentSubControlName() == "inline diff":
            editor = self.getMainAreaPanel().getCurrentSubControl()

        evt.Check(editor is not None and editor.getWrapMode())
        evt.Enable(editor is not None)


    def OnCmdCheckIndentationGuides(self, evt):        
        self.getActiveEditor().SetIndentationGuides(evt.IsChecked())
        self.configuration.set("main", "indentation_guides", evt.IsChecked())

    def OnUpdateIndentationGuides(self, evt):
        editor = self.getActiveEditor()
        evt.Check(editor is not None and editor.GetIndentationGuides())
        evt.Enable(editor is not None)


    def OnCmdCheckAutoIndent(self, evt):        
        self.getActiveEditor().setAutoIndent(evt.IsChecked())
        self.configuration.set("main", "auto_indent", evt.IsChecked())

    def OnUpdateAutoIndent(self, evt):
        editor = self.getActiveEditor()
        evt.Check(editor is not None and editor.getAutoIndent())
        evt.Enable(editor is not None)


    def OnCmdCheckAutoBullets(self, evt):        
        self.getActiveEditor().setAutoBullets(evt.IsChecked())
        self.configuration.set("main", "auto_bullets", evt.IsChecked())

    def OnUpdateAutoBullets(self, evt):
        editor = self.getActiveEditor()
        evt.Check(editor is not None and editor.getAutoBullets())
        evt.Enable(editor is not None)


    def OnCmdCheckTabsToSpaces(self, evt):        
        self.getActiveEditor().setTabsToSpaces(evt.IsChecked())
        self.configuration.set("main", "editor_tabsToSpaces", evt.IsChecked())

    def OnUpdateTabsToSpaces(self, evt):
        editor = self.getActiveEditor()
        evt.Check(editor is not None and editor.getTabsToSpaces())
        evt.Enable(editor is not None)


    def OnCmdCheckShowLineNumbers(self, evt):        
        self.getActiveEditor().setShowLineNumbers(evt.IsChecked())
        self.configuration.set("main", "show_lineNumbers", evt.IsChecked())

    def OnUpdateShowLineNumbers(self, evt):
        editor = self.getActiveEditor()
        evt.Check(editor is not None and editor.getShowLineNumbers())
        evt.Enable(editor is not None)


    def OnCmdCheckShowFolding(self, evt):        
        self.getActiveEditor().setFoldingActive(evt.IsChecked())
        self.configuration.set("main", "editor_useFolding", evt.IsChecked())

    def OnUpdateShowFolding(self, evt):
        editor = self.getActiveEditor()
        evt.Check(editor is not None and editor.getFoldingActive())
        evt.Enable(editor is not None)


    def OnCloseButton(self, evt):
        if self.configuration.getboolean("main", "minimize_on_closeButton"):
            self.Iconize(True)
        else:
            try:
#             tracer.runctx('self._prepareExitWiki()', globals(), locals())
                self._prepareExitWiki()
                self.Destroy()
                evt.Skip()
            except LossyWikiCloseDeniedException:
                pass


    def exitWiki(self):
        self._prepareExitWiki()
        wx.CallLater(1, self.Destroy)
#         self.Destroy()

    def _prepareExitWiki(self):
        self.getMainAreaPanel().updateConfig()
        self.closeWiki()

        self.Unbind(wx.EVT_ICONIZE)
        if self._interceptCollection is not None:
            self._interceptCollection.close()


        wx.GetApp().getMiscEvent().removeListener(self)

        # if the frame is not minimized
        # update the size/pos of the global config
        if not self.IsIconized():
            curSize = self.GetSize()
            self.configuration.set("main", "size_x", curSize.x)
            self.configuration.set("main", "size_y", curSize.y)
            curPos = self.GetPosition()
            self.configuration.set("main", "pos_x", curPos.x)
            self.configuration.set("main", "pos_y", curPos.y)

        # windowmode:  0=normal, 1=maximized, 2=iconized, 3=maximized iconized

        windowmode = 0
        if self.IsMaximized():
            windowmode |= 1
        if self.IsIconized():
            windowmode |= 2

        self.configuration.set("main", "windowmode", windowmode)

        layoutCfStr = self.windowLayouter.getWinPropsForConfig()
        self.configuration.set("main", "windowLayout", layoutCfStr)

        self.configuration.set("main", "frame_stayOnTop", self.getStayOnTop())
        if self.getActiveEditor():
            self.configuration.set("main", "zoom", self.getActiveEditor().GetZoom())
        if not self.getCmdLineAction().noRecent:
            self.configuration.set("main", "wiki_history",
                    ";".join(self.wikiHistory))

        self.windowLayouter.close()

        # trigger hook
        self.hooks.exit(self)
        self.writeGlobalConfig()

#         self.getMainAreaPanel().close()

        # save the current wiki state
#         self.saveCurrentWikiState()

        wx.TheClipboard.Flush()

        if self.tbIcon is not None:
            if self.tbIcon.IsIconInstalled():
                self.tbIcon.RemoveIcon()

            self.tbIcon.prepareExit()
            self.tbIcon.Destroy()
            # May mysteriously prevent crash when closing WikidPad minimized
            #   on tray:
            time.sleep(0.1)
            self.tbIcon = None

        wx.GetApp().unregisterMainFrame(self)



class TaskBarIcon(wx.TaskBarIcon):
    def __init__(self, pWiki):
        wx.TaskBarIcon.__init__(self)
        self.pWiki = pWiki

        # Register menu events
        wx.EVT_MENU(self, GUI_ID.TBMENU_RESTORE, self.OnLeftUp)
        wx.EVT_MENU(self, GUI_ID.TBMENU_SAVE,
                lambda evt: (self.pWiki.saveAllDocPages(),
                self.pWiki.getWikiData().commit()))
        wx.EVT_MENU(self, GUI_ID.TBMENU_EXIT, self.OnCmdExit)

        if self.pWiki.clipboardInterceptor is not None:
            wx.EVT_MENU(self, GUI_ID.CMD_CLIPBOARD_CATCHER_AT_CURSOR,
                    self.pWiki.OnClipboardCatcherAtCursor)
            wx.EVT_MENU(self, GUI_ID.CMD_CLIPBOARD_CATCHER_OFF,
                    self.pWiki.OnClipboardCatcherOff)

            wx.EVT_UPDATE_UI(self, GUI_ID.CMD_CLIPBOARD_CATCHER_AT_CURSOR,
                    self.pWiki.OnUpdateClipboardCatcher)
            wx.EVT_UPDATE_UI(self, GUI_ID.CMD_CLIPBOARD_CATCHER_OFF,
                    self.pWiki.OnUpdateClipboardCatcher)

        wx.EVT_TASKBAR_LEFT_UP(self, self.OnLeftUp)


    def prepareExit(self):
        # Another desperate try to prevent crashing
        self.Unbind(wx.EVT_TASKBAR_LEFT_UP)


    def OnCmdExit(self, evt):
        # Trying to prevent a crash with this, but didn't help much
        wx.CallLater(1, self.pWiki.exitWiki)

    def OnLeftUp(self, evt):
        if self.pWiki.IsIconized():
            self.pWiki.Iconize(False)
            self.pWiki.Show(True)

        self.pWiki.Raise()


    def CreatePopupMenu(self):
        tbMenu = wx.Menu()
        # Build menu
        if self.pWiki.clipboardInterceptor is not None:
            menuItem = wx.MenuItem(tbMenu,
                    GUI_ID.CMD_CLIPBOARD_CATCHER_AT_CURSOR,
                    _(u"Clipboard Catcher at Cursor"), u"", wx.ITEM_CHECK)
            tbMenu.AppendItem(menuItem)

            menuItem = wx.MenuItem(tbMenu, GUI_ID.CMD_CLIPBOARD_CATCHER_OFF,
                    _(u"Clipboard Catcher off"), u"", wx.ITEM_CHECK)
            tbMenu.AppendItem(menuItem)
            
            tbMenu.AppendSeparator()


        wxHelper.appendToMenuByMenuDesc(tbMenu, _SYSTRAY_CONTEXT_MENU_BASE)


        return tbMenu


def importCode(code, usercode, userUserCode, name, add_to_sys_modules=False):
    """
    Import dynamically generated code as a module. 
    usercode and code are the objects containing the code
    (a string, a file handle or an actual compiled code object,
    same types as accepted by an exec statement), usercode
    may be None. code is executed first, usercode thereafter
    and can overwrite settings in code. The name is the name to give to the module,
    and the final argument says wheter to add it to sys.modules
    or not. If it is added, a subsequent import statement using
    name will return this module. If it is not added to sys.modules
    import will try to load it in the normal fashion.

    import foo

    is equivalent to

    foofile = open("/path/to/foo.py")
    foo = importCode(foofile,"foo",1)

    Returns a newly generated module.
    """
    import sys,imp

    module = imp.new_module(name)

    exec code in module.__dict__
    if usercode is not None:
        exec usercode in module.__dict__
    if userUserCode is not None:
        exec userUserCode in module.__dict__
    if add_to_sys_modules:
        sys.modules[name] = module

    return module




_SYSTRAY_CONTEXT_MENU_BASE = \
u"""
Restore;TBMENU_RESTORE
Save;TBMENU_SAVE
Exit;TBMENU_EXIT
"""


# Entries to support i18n of context menus
if False:
    N_(u"Restore")
    N_(u"Save")
    N_(u"Exit")

# _TASKBAR_CONTEXT_MENU_CLIPCATCH = \
# u"""
# Clipboard Catcher at Cursor;CMD_CLIPBOARD_CATCHER_AT_CURSOR
# Clipboard Catcher off;CMD_CLIPBOARD_CATCHER_OFF
# -
# """




#         This function must FOLLOW the actual update eventhandler in the
#         updatefct tuple of self.addMenuItem.
