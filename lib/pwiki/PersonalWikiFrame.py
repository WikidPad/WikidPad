## import hotshot
## _prof = hotshot.Profile("hotshot.prf")

import os, sys, gc, traceback, sets, string, re
from os.path import *
from time import localtime, time, strftime, sleep

import cPickle

import urllib

import wx  #, wx.stc, wx.html
# from wxPython.wx import *
# from wxPython.stc import *
# from wxPython.html import *

from wxHelper import GUI_ID, cloneImageList, getAccelPairFromKeyDown, \
        getAccelPairFromString

from MiscEvent import MiscEventSourceMixin   # , DebugSimple

from WikiExceptions import *

import Configuration
from WindowLayout import WindowLayouter, setWindowPos, setWindowSize
from wikidata import DbBackendUtils, WikiDataManager

import OsAbstract

import DocPages, WikiFormatting

from CmdLineAction import CmdLineAction
from WikiTxtCtrl import WikiTxtCtrl
from WikiTreeCtrl import WikiTreeCtrl
from WikiHtmlView import createWikiHtmlView
from LogWindow import LogWindow
from DocPagePresenter import DocPagePresenter

from Ipc import EVT_REMOTE_COMMAND

import PropertyHandling, SpellChecker

from PageHistory import PageHistory
from SearchAndReplace import SearchReplaceOperation
from Printing import Printer, PrintMainDialog

from AdditionalDialogs import *
from OptionsDialog import OptionsDialog
from SearchAndReplaceDialogs import *



import Exporters
from StringOps import uniToGui, guiToUni, mbcsDec, mbcsEnc, strToBool, \
        wikiWordToLabel, BOM_UTF8, fileContentToUnicode, splitIndent, \
        unescapeWithRe, pathEnc

import DocPages
import WikiFormatting


import PageAst   # For experiments only

from PluginManager import *

# TODO More abstract/platform independent
try:
    import WindowsHacks
except:
    WindowsHacks = None



class wxGuiProgressHandler:
    """
    Implementation of a GuiProgressListener to
    show a wx.ProgressDialog
    """
    def __init__(self, title, msg, addsteps, parent, flags=wx.PD_APP_MODAL):
        self.title = title
        self.msg = msg
        self.addsteps = addsteps
        self.parent = parent
        self.flags = flags

    def open(self, sum):
        """
        Start progress handler, set the number of steps, the operation will
        take in sum. Will be called once before update()
        is called several times
        """
        self.progDlg = wx.ProgressDialog(self.title, self.msg,
                sum + self.addsteps, self.parent, self.flags)
        
    def update(self, step, msg):
        """
        Called after a step is finished to trigger update
        of GUI.
        step -- Number of done steps
        msg -- Human readable descripion what is currently done
        returns: True to continue, False to stop operation
        """
        self.progDlg.Update(step, uniToGui(msg))
        return True

    def close(self):
        """
        Called after finishing operation or after abort to 
        do clean-up if necessary
        """
        self.progDlg.Destroy()
        self.progDlg = None


class KeyBindingsCache:
    def __init__(self, kbModule):
        self.kbModule = kbModule
        self.accelPairCache = {}
        
    def __getattr__(self, attr):
        return getattr(self.kbModule, attr)
        
    def getAccelPair(self, attr):
        try:
            return self.accelPairCache[attr]
        except KeyError:
            ap = getAccelPairFromString("\t" + getattr(self, attr))
            self.accelPairCache[attr] = ap
            return ap

    def matchesAccelPair(self, attr, accP):
        return self.getAccelPair(attr) == accP


class LossyWikiCloseDeniedException(Exception):
    """
    Special exception thrown from PersonalWikiFrame.closeWiki() if user denied
    to close the wiki because it might lead to data loss
    """
    pass


class PersonalWikiFrame(wx.Frame, MiscEventSourceMixin):
    def __init__(self, parent, id, title, wikiAppDir, globalConfigDir,
            globalConfigSubDir, cmdLineAction):
        wx.Frame.__init__(self, parent, -1, title, size = (700, 550),
                         style=wx.DEFAULT_FRAME_STYLE|wx.NO_FULL_REPAINT_ON_RESIZE)
        MiscEventSourceMixin.__init__(self)

        if cmdLineAction.cmdLineError:
            cmdLineAction.showCmdLineUsage(self,
                    u"Bad formatted command line.\n\n")
            self.Close()
            self.Destroy()
            return

        self.sleepMode = False  # Is program in low resource sleep mode?

#         if not globalConfigDir or not exists(globalConfigDir):
#             self.displayErrorMessage(
#                     u"Error initializing environment, couldn't locate "+
#                     u"global config directory", u"Shutting Down")
#             self.Close()


        # initialize some variables
        self.globalConfigDir = globalConfigDir
        self.wikiAppDir = wikiAppDir
        
        self.globalConfigSubDir = globalConfigSubDir
        
        # Create the "[TextBlocks].wiki" file in the global config subdirectory
        # if the file doesn't exist yet.
        tbLoc = join(self.globalConfigSubDir, "[TextBlocks].wiki")
        if not exists(tbLoc):
            tbFile = open(pathEnc(tbLoc), "w")
            tbFile.write(BOM_UTF8)
            tbFile.write(
"""importance: high;a=[importance: high]\\n
importance: low;a=[importance: low]\\n
tree_position: 0;a=[tree_position: 0]\\n
wrap: 80;a=[wrap: 80]\\n
camelCaseWordsEnabled: false;a=[camelCaseWordsEnabled: false]\\n
""")
            tbFile.close()
        self.globalConfigLoc = join(globalConfigDir, "WikidPad.config")
        self.configuration = wx.GetApp().createCombinedConfiguration()

        self.wikiPadHelp = join(self.wikiAppDir, 'WikidPadHelp',
                'WikidPadHelp.wiki')
        self.windowLayouter = None  # will be set by initializeGui()

        # defaults
        self.wikiData = None
        self.wikiDataManager = None
#         self.currentWikiWord = None
#         self.currentWikiPage = None
        self.lastCursorPositionInPage = {}
        self.wikiHistory = []
        self.findDlg = None  # Stores find&replace or wiki search dialog, if present
        self.spellChkDlg = None  # Stores spell check dialog, if present
        self.mainmenu = None
        self.editorMenu = None  # "Editor" menu
        self.fastSearchField = None   # Text field in toolbar
        self.editors = [] # List of all editors (WikiTxtCtrl objects)
        
        self.textBlocksActivation = {} # See self.buildTextBlocksMenu()
        # Position of the root menu of the text blocks within "Editor" menu
        self.textBlocksMenuPosition = None  
        self.cmdIdToIconName = None # Maps command id (=menu id) to icon name
                                    # needed for "Editor"->"Add icon property"
        self.cmdIdToColorName = None # Same for color names
        
        self.eventRoundtrip = 0
        
        self.currentDocPagePresenter = None

        # setup plugin manager and hooks API
        self.pluginManager = PluginManager()
        self.hooks = self.pluginManager.registerPluginAPI(("hooks",1),
            ["startup", "newWiki", "createdWiki", "openWiki", "openedWiki", 
             "openWikiWord", "newWikiWord", "openedWikiWord", "savingWikiWord",
             "savedWikiWord", "renamedWikiWord", "deletedWikiWord", "exit"] )
        # interfaces for menu and toolbar plugins
        self.menuFunctions = self.pluginManager.registerPluginAPI(("MenuFunctions",1), 
                                ("describeMenuItems",))
        self.toolbarFunctions = self.pluginManager.registerPluginAPI(("ToolbarFunctions",1), 
                                ("describeToolbarItems",))
                                
        # load extensions
        self.loadExtensions()

        # initialize the wiki syntax
        WikiFormatting.initialize(self.wikiSyntax)
        
#         # Initialize new component
#         self.formatting = WikiFormatting.WikiFormatting(self, self.wikiSyntax)

        # Connect page history
        self.pageHistory = PageHistory(self)

        self.propertyChecker = PropertyHandling.PropertyChecker(self)

        self.configuration.setGlobalConfig(wx.GetApp().getGlobalConfig())
        
        # trigger hook
        self.hooks.startup(self)

#         # if it already exists read it in
#         if exists(self.globalConfigLoc):
#             try:
#                 self.configuration.loadGlobalConfig(self.globalConfigLoc)
#             except Configuration.Error:
#                 self.createDefaultGlobalConfig()
#         else:
#             self.createDefaultGlobalConfig()

        # Initialize printing
        self.printer = Printer(self)

        # wiki history
        history = self.configuration.get("main", "wiki_history")
        if history:
            self.wikiHistory = history.split(u";")
          
        # clipboard catcher  
        if WindowsHacks is None:
            self.win32Interceptor = None
        else:
            self.win32Interceptor = WindowsHacks.WikidPadWin32WPInterceptor(self)
            self.win32Interceptor.intercept(self.GetHandle())

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

        # Should reduce resources usage (less icons)
        # Do not set self.lowResources after initialization here!
        self.lowResources = wx.GetApp().getLowResources()
#         self.lowResources = self.configuration.getboolean("main", "lowresources")

#         # get the wrap mode setting
#         self.wrapMode = self.configuration.getboolean("main", "wrap_mode")

        # get the position of the splitter
        self.lastSplitterPos = self.configuration.getint("main", "splitter_pos")

        # get the default font for the editor
#         self.defaultEditorFont = self.configuration.get("main", "font",
#                 self.presentationExt.faces["mono"])
                
        self.layoutMainTreePosition = self.configuration.getint("main",
                "mainTree_position", 0)
        self.layoutViewsTreePosition = self.configuration.getint("main",
                "viewsTree_position", 0)

        # this will keep track of the last font used in the editor
        self.lastEditorFont = None

        # should WikiWords be enabled or not for the current wiki
        self.wikiWordsEnabled = True

        # if a wiki to open wasn't passed in use the last_wiki from the global config
        wikiToOpen = cmdLineAction.wikiToOpen
        wikiWordToOpen = cmdLineAction.wikiWordToOpen

        if not wikiToOpen:
            wikiToOpen = self.configuration.get("main", "last_wiki")

        # initialize the GUI
        self.initializeGui()

        # Minimize on tray?
        ## self.showOnTray = self.globalConfig.getboolean("main", "showontray")

        self.tbIcon = None
        self.setShowOnTray()

        # windowmode:  0=normal, 1=maximized, 2=iconized, 3=maximized iconized(doesn't work)
        windowmode = self.configuration.getint("main", "windowmode")

        if windowmode & 1:
            self.Maximize(True)
        if windowmode & 2:
            self.Iconize(True)

        # if a wiki to open is set, open it
        if wikiToOpen:
            if exists(pathEnc(wikiToOpen)):
                self.openWiki(wikiToOpen, wikiWordToOpen)
            else:
                self.statusBar.SetStatusText(
                        uniToGui(u"Last wiki doesn't exist: %s" % wikiToOpen), 0)

        # set the focus to the editor
#         if self.vertSplitter.GetSashPosition() < 2:
#             self.activeEditor.SetFocus()

        # display the window
        ## if not (self.showOnTray and self.IsIconized()):
            
        cmdLineAction.actionBeforeShow(self)

        if cmdLineAction.exitFinally:
            self.exitWiki()
#             self.Close()
#             self.Destroy()
            return

        self.Show(True)
        
        if self.lowResources and self.IsIconized():
            self.resourceSleep()
            
        EVT_REMOTE_COMMAND(self, self.OnRemoteCommand)


    def loadExtensions(self):
        self.wikidPadHooks = self.getExtension('WikidPadHooks', u'WikidPadHooks.py')
        self.keyBindings = KeyBindingsCache(
                self.getExtension('KeyBindings', u'KeyBindings.py'))
        self.evalLib = self.getExtension('EvalLibrary', u'EvalLibrary.py')
        self.wikiSyntax = self.getExtension('SyntaxLibrary', u'WikiSyntax.py')
        self.presentationExt = self.getExtension('Presentation', u'Presentation.py')
        dirs = [ join(self.wikiAppDir, u'user_extensions'),
                join(self.wikiAppDir, u'extensions') ]
        self.pluginManager.loadPlugins( dirs, [ u'KeyBindings.py',
                u'EvalLibrary.py', u'WikiSyntax.py' ] )

    def getExtension(self, extensionName, fileName):
        extensionFileName = join(self.wikiAppDir, 'user_extensions', fileName)
        if exists(pathEnc(extensionFileName)):
            extFile = open(pathEnc(extensionFileName), "rU")
            userExtension = extFile.read()
            extFile.close()
        else:
            userExtension = None
            
        extensionFileName = join(self.wikiAppDir, 'extensions', fileName)
        extFile = open(pathEnc(extensionFileName), "rU")
        systemExtension = extFile.read()
        extFile.close()
        
        return importCode(systemExtension, userExtension, extensionName)

#     def createDefaultGlobalConfig(self):
#         self.configuration.createEmptyGlobalConfig(self.globalConfigLoc)
#         self.configuration.fillGlobalWithDefaults()
# 
#         self.configuration.set("main", "wiki_history", self.wikiPadHelp)
#         self.configuration.set("main", "last_wiki", self.wikiPadHelp)
#         curSize = self.GetSize()
#         self.configuration.set("main", "size_x", str(curSize.x))
#         self.configuration.set("main", "size_y", str(curSize.y))
#         curPos = self.GetPosition()
#         self.configuration.set("main", "pos_x", str(curPos.x))
#         self.configuration.set("main", "pos_y", str(curPos.y))
#         self.configuration.set("main", "last_active_dir", os.getcwd())


    def getCurrentWikiWord(self):
        docPage = self.getCurrentDocPage()
        if docPage is None or not isinstance(docPage,
                (DocPages.WikiPage, DocPages.AliasWikiPage)):
            return None
        return docPage.getWikiWord()

    def getCurrentDocPage(self):
        if self.currentDocPagePresenter is None:
            return None
        return self.currentDocPagePresenter.getDocPage()

    def getActiveEditor(self):
        return self.currentDocPagePresenter.getSubControl("textedit")

    def getCurrentDocPagePresenter(self):
        return self.currentDocPagePresenter

    # TODO What about WikidPadHooks?
    def setCurrentDocPagePresenter(self, currentPresenter):
        if self.currentDocPagePresenter != currentPresenter:
            self.currentDocPagePresenter = currentPresenter
            self.refreshPageStatus()
            self.fireMiscEventKeys(("changed current docpage presenter",))
            
#     def setActiveEditor(self, activeEditor):
#         if self.activeEditor != activeEditor:
#             self.activeEditor = activeEditor
#             self.refreshPageStatus()
#             self.fireMiscEventKeys(("changed active editor",))

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

    def getWikiConfigPath(self):
        if self.wikiDataManager is None:
            return None

        return self.wikiDataManager.getWikiConfigPath()

    def getConfig(self):
        return self.configuration
        
    def getFormatting(self):
        if self.wikiDataManager is None:
            return None

        return self.wikiDataManager.getFormatting()

    def getCollator(self):
        return wx.GetApp().getCollator()

    def getLogWindow(self):
        return self.logWindow


    def lookupIcon(self, iconname):
        """
        Returns the bitmap object for the given iconname.
        If the bitmap wasn't cached already, it is loaded and created.
        If icon is unknown, None is returned.
        """
        return wx.GetApp().getIconCache().lookupIcon(iconname)


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
        # Check for infinite loop
        if self.eventRoundtrip > 0:
            return

        self.eventRoundtrip += 1
        try:
            focus = wx.Window.FindFocus()
            if focus is not None:
                focus.ProcessEvent(evt)
        finally:
            self.eventRoundtrip -= 1


    def addMenuItem(self, menu, label, text, evtfct=None, icondesc=None,
            menuID=None):
        if menuID is None:
            menuID = wx.NewId()

        menuitem = wx.MenuItem(menu, menuID, label, text)
        # if icondesc:  # (not self.lowResources) and
        bitmap = self.resolveIconDescriptor(icondesc)
        if bitmap:
            menuitem.SetBitmap(bitmap)

        menu.AppendItem(menuitem)
        if evtfct is not None:
            wx.EVT_MENU(self, menuID, evtfct)

        return menuitem


    def buildWikiMenu(self):
        """
        Builds the first, the "Wiki" menu and returns it
        """
        wikiData = self.getWikiData()
        wikiMenu = wx.Menu()

        self.addMenuItem(wikiMenu, '&New\t' + self.keyBindings.NewWiki,
                'New Wiki', self.OnWikiNew)

        self.addMenuItem(wikiMenu, '&Open\t' + self.keyBindings.OpenWiki,
                'Open Wiki', self.OnWikiOpen)

## TODO
        self.addMenuItem(wikiMenu, '&Open in New Window\t' +
                self.keyBindings.OpenWikiNewWindow,
                'Open Wiki in a new window', self.OnWikiOpenNewWindow)

        self.addMenuItem(wikiMenu, 'Open as &Type',
                'Open Wiki with a specified wiki database type',
                self.OnWikiOpenAsType)

        self.recentWikisMenu = wx.Menu()
        wikiMenu.AppendMenu(wx.NewId(), '&Recent', self.recentWikisMenu)

        # init the list of items
        for wiki in self.wikiHistory:
            menuID=wx.NewId()
            self.recentWikisMenu.Append(menuID, wiki)
            wx.EVT_MENU(self, menuID, self.OnSelectRecentWiki)

        wikiMenu.AppendSeparator()

        if wikiData is not None:
#             wikiMenu.AppendSeparator()

            self.addMenuItem(wikiMenu, '&Search Wiki\t' +
                    self.keyBindings.SearchWiki, 'Search Wiki',
                    lambda evt: self.showSearchDialog(), "tb_lens")


        self.addMenuItem(wikiMenu, 'O&ptions...',
                'Set Options', lambda evt: self.showOptionsDialog())

        wikiMenu.AppendSeparator()

        if wikiData is not None:
            exportWikisMenu = wx.Menu()
            wikiMenu.AppendMenu(wx.NewId(), 'Export', exportWikisMenu)
    
            self.addMenuItem(exportWikisMenu, 'Export Wiki as Single HTML Page',
                    'Export Wiki as Single HTML Page', self.OnExportWiki,
                    menuID=GUI_ID.MENU_EXPORT_WHOLE_AS_PAGE)
    
            self.addMenuItem(exportWikisMenu, 'Export Wiki as Set of HTML Pages',
                    'Export Wiki as Set of HTML Pages', self.OnExportWiki,
                    menuID=GUI_ID.MENU_EXPORT_WHOLE_AS_PAGES)
    
            self.addMenuItem(exportWikisMenu, 'Export Current Wiki Word as HTML Page',
                    'Export Current Wiki Word as HTML Page', self.OnExportWiki,
                    menuID=GUI_ID.MENU_EXPORT_WORD_AS_PAGE)
    
            self.addMenuItem(exportWikisMenu, 'Export Sub-Tree as Single HTML Page',
                    'Export Sub-Tree as Single HTML Page', self.OnExportWiki,
                    menuID=GUI_ID.MENU_EXPORT_SUB_AS_PAGE)
    
            self.addMenuItem(exportWikisMenu, 'Export Sub-Tree as Set of HTML Pages',
                    'Export Sub-Tree as Set of HTML Pages', self.OnExportWiki,
                    menuID=GUI_ID.MENU_EXPORT_SUB_AS_PAGES)
    
            self.addMenuItem(exportWikisMenu, 'Export Wiki as XML',
                    'Export Wiki as XML in UTF-8', self.OnExportWiki,
                    menuID=GUI_ID.MENU_EXPORT_WHOLE_AS_XML)
    
            self.addMenuItem(exportWikisMenu, 'Export Wiki to .wiki files',
                    'Export Wiki to .wiki files in UTF-8', self.OnExportWiki,
                    menuID=GUI_ID.MENU_EXPORT_WHOLE_AS_RAW)
    
            self.addMenuItem(exportWikisMenu, 'Other Export...',
                    'Open export dialog', self.OnCmdExportDialog)

        if wikiData is not None:
            self.addMenuItem(wikiMenu, 'Import...',
                    'Import dialog', self.OnCmdImportDialog)


        if wikiData is not None:
            self.addMenuItem(wikiMenu, 'Print...\t' + self.keyBindings.Print,
                    'Show the print dialog',
                    lambda evt: self.printer.showPrintMainDialog())

        if wikiData is not None and wikiData.checkCapability("rebuild") == 1:
            menuID=wx.NewId()
            wikiMenu.Append(menuID, '&Rebuild Wiki', 'Rebuild this wiki')
            wx.EVT_MENU(self, menuID, lambda evt: self.rebuildWiki())

        if wikiData is not None:
            self.addMenuItem(wikiMenu, 'Reconnect',
                    'Reconnect to database after connection failure',
                    self.OnCmdReconnectDatabase)

        if wikiData is not None and wikiData.checkCapability("compactify") == 1:
            menuID=wx.NewId()
            wikiMenu.Append(menuID, '&Vacuum Wiki', 'Free unused space in database')
            wx.EVT_MENU(self, menuID, lambda evt: self.vacuumWiki())

        if wikiData is not None and \
                wikiData.checkCapability("plain text import") == 1:
            menuID=wx.NewId()
            wikiMenu.Append(menuID, '&Copy .wiki files to database', 'Copy .wiki files to database')
            wx.EVT_MENU(self, menuID, self.OnImportFromPagefiles)

        if wikiData is not None:
            wikiMenu.AppendSeparator()            
            self.addMenuItem(wikiMenu, 'Wiki &Info...',
                    'Show general information about current wiki',
                    self.OnShowWikiInfoDialog)

        if wikiData is not None and wikiData.checkCapability("versioning") == 1:
            wikiMenu.AppendSeparator()
    
            menuID=wx.NewId()
            wikiMenu.Append(menuID, '&Store version', 'Store new version')
            wx.EVT_MENU(self, menuID, lambda evt: self.showStoreVersionDialog())
    
            menuID=wx.NewId()
            wikiMenu.Append(menuID, '&Retrieve version', 'Retrieve previous version')
            wx.EVT_MENU(self, menuID, lambda evt: self.showSavedVersionsDialog())
    
            menuID=wx.NewId()
            wikiMenu.Append(menuID, 'Delete &All Versions', 'Delete all stored versions')
            wx.EVT_MENU(self, menuID, lambda evt: self.showDeleteAllVersionsDialog())

        wikiMenu.AppendSeparator()  # TODO May have two separators without anything between

#         self.addMenuItem(wikiMenu, '&Test', 'Test', lambda evt: self.testIt())

        menuID=wx.NewId()
        wikiMenu.Append(menuID, 'E&xit', 'Exit')
        wx.EVT_MENU(self, menuID, lambda evt: self.exitWiki())
        
        return wikiMenu


    def _addToTextBlocksMenu(self, tbContent, stack, reusableIds):
        """
        Helper for buildTextBlocksMenu() to build up menu
        """
        emptyLine = False    
        for line in tbContent.split(u"\n"):
            if line.strip() == u"":
                emptyLine = True
                continue

            # Parse line                
            text, deep = splitIndent(line)
            try:
                entryPrefix, entryContent = text.split(u"=", 1)
            except:
                continue
                
            entryPrefixes = entryPrefix.split(u";")
            entryTitle = entryPrefixes[0]
            if len(entryPrefixes) > 1:
                entryFlags = entryPrefixes[1]
            else:
                entryFlags = u""

            if entryTitle == u"":
                entryTitle = entryContent[:60]
                entryTitle = entryTitle.split("\\n", 1)[0]

            try:
                entryContent = unescapeWithRe(entryContent)
                entryTitle = unescapeWithRe(entryTitle)
            except:
                continue

            # Adjust the stack
            if deep > stack[-1][0]:
                stack.append([deep, None, wx.Menu()])
            elif stack[-1][0] > deep:
                while stack[-1][0] > deep:
                    title, menu = stack.pop()[1:3]
                    if title is None:
                        title = u"<No title>"
                    
                    stack[-1][2].AppendMenu(wx.NewId(), title, menu)
            else:
                if emptyLine:
                    title, menu = stack.pop()[1:3]
                    if title is None:
                        title = u"<No title>"

                    stack[-1][2].AppendMenu(wx.NewId(), title, menu)
                    stack.append([deep, None, wx.Menu()])
            
            emptyLine = False
            
            # Create new entry if necessary
            title, menu = stack[-1][1:3]
            if title is None:
                # Entry defines title
                stack[-1][1] = entryTitle
                
            if entryContent == u"":
                continue

            if len(reusableIds) > 0:
                menuID = reusableIds.pop()
                # No event binding, must have happened before because id is reused
            else:
                menuID = wx.NewId()
                wx.EVT_MENU(self, menuID, self.OnTextBlockUsed)

            menuItem = wx.MenuItem(menu, menuID, entryTitle)
            menu.AppendItem(menuItem)

            self.textBlocksActivation[menuID] = (entryFlags, entryContent)
            
        # Add the remaining ids so nothing gets lost
        for i in reusableIds:
            self.textBlocksActivation[i] = (None, None)

        # Finally empty stack
        while len(stack) > 1:
            title, menu = stack.pop()[1:3]
            if title is None:
                title = u"<No title>"
            
            stack[-1][2].AppendMenu(wx.NewId(), title, menu)


    def buildTextBlocksMenu(self):
        """
        Constructs the text blocks menu submenu and necessary subsubmenus.
        If this is called more than once, previously used menu ids are reused
        for the new menu.
        """
        reusableIds = sets.Set(self.textBlocksActivation.keys())
        
        # Dictionary with menu id of the text block item as key and tuple
        # (entryFlags, entryContent) as value, where entryFlags is a string
        # of flag characters for the text block (currently only "a" for append
        # instead of insert at cursor position), entryContent is the unescaped
        # content of the text block.
        # Tuple may be (None, None) if the id isn't used but stored for later
        # reuse
        self.textBlocksActivation = {}
        
        stack = [[0, u"Text blocks", wx.Menu()]]
                
        wikiData = self.getWikiData()
        if wikiData is not None and self.requireReadAccess():
            try:
                # We have current wiki with appropriate functional page,
                # so fill menu first with wiki specific text blocks
                tbContent = wikiData.getContent("[TextBlocks]")
                self._addToTextBlocksMenu(tbContent, stack, reusableIds)

                stack[-1][2].AppendSeparator()
            except WikiFileNotFoundException:
                pass
            except (IOError, OSError, DbReadAccessError), e:
                self.lostReadAccess(e)
                traceback.print_exc()

        # Fill menu with global text blocks
        tbLoc = join(self.globalConfigSubDir, "[TextBlocks].wiki")
        try:
            tbFile = open(pathEnc(tbLoc), "rU")
            tbContent = tbFile.read()
            tbFile.close()
            tbContent = fileContentToUnicode(tbContent)
        except:
            tbContent = u""

        self._addToTextBlocksMenu(tbContent, stack, reusableIds)

        stack[-1][2].AppendSeparator()
        stack[-1][2].Append(GUI_ID.CMD_REREAD_TEXT_BLOCKS, 'Reread text blocks',
                'Reread the text block file(s) and recreate menu')
        wx.EVT_MENU(self, GUI_ID.CMD_REREAD_TEXT_BLOCKS, self.OnRereadTextBlocks)

        return stack[-1][2]


    def OnTextBlockUsed(self, evt):
        try:
            entryFlags, entryContent = self.textBlocksActivation[evt.GetId()]
            if entryFlags is None:
                return

            if u"a" in entryFlags:
                self.appendText(entryContent)
            else:
                self.addText(entryContent, replaceSel=True)
            
        except KeyError:
            pass

    
    def OnRereadTextBlocks(self, evt):
        self.rereadTextBlocks()
        
        
    def rereadTextBlocks(self):
        """
        Starts rereading and rebuilding of the text blocks submenu
        """
        oldItem = self.editorMenu.FindItemByPosition(
                self.textBlocksMenuPosition)
        oldItemId = oldItem.GetId()
        
        self.editorMenu.DeleteItem(oldItem)

        tbmenu = self.buildTextBlocksMenu()
                
        self.editorMenu.InsertMenu(self.textBlocksMenuPosition, oldItemId,
                '&Text blocks', tbmenu)


    def OnInsertIconAttribute(self, evt):
        self.insertAttribute("icon", self.cmdIdToIconName[evt.GetId()])


    def OnInsertColorAttribute(self, evt):
        self.insertAttribute("color", self.cmdIdToColorName[evt.GetId()])


    def buildMainMenu(self):
        # ------------------------------------------------------------------------------------
        # Set up menu bar for the program.
        # ------------------------------------------------------------------------------------
        if self.mainmenu is not None:
            # This is a rebuild of an existing menu (after loading a new wikiData)
            self.mainmenu.Replace(0, self.buildWikiMenu(), 'W&iki')
            return


        self.mainmenu = wx.MenuBar()   # Create menu bar.

        wikiMenu = self.buildWikiMenu()

        wikiWordMenu=wx.Menu()

        self.addMenuItem(wikiWordMenu, '&Open\t' + self.keyBindings.OpenWikiWord,
                'Open Wiki Word', lambda evt: self.showWikiWordOpenDialog(),
                "tb_doc")

        self.addMenuItem(wikiWordMenu, '&Save\t' + self.keyBindings.Save,
                'Save all open pages',
                lambda evt: (self.saveAllDocPages(force=True),
                self.getWikiData().commit()), "tb_save")

        self.addMenuItem(wikiWordMenu, '&Rename\t' + self.keyBindings.Rename,
                'Rename Current Wiki Word', lambda evt: self.showWikiWordRenameDialog(),
                "tb_rename")

        self.addMenuItem(wikiWordMenu, '&Delete\t' + self.keyBindings.Delete,
                'Delete Wiki Word', lambda evt: self.showWikiWordDeleteDialog(),
                "tb_delete")

        self.addMenuItem(wikiWordMenu, 'Add Bookmark\t' + self.keyBindings.AddBookmark,
                'Add Bookmark to Page', lambda evt: self.insertAttribute("bookmarked", "true"),
                "pin")
                
        if self.win32Interceptor is not None:
            wikiWordMenu.AppendSeparator()

            menuItem = wx.MenuItem(wikiWordMenu, GUI_ID.CMD_CLIPBOARD_CATCHER_AT_PAGE,
                    "Clipboard Catcher at Page\t" + self.keyBindings.CatchClipboardAtPage, 
                    u"Text copied to clipboard is also appended to this page",
                    wx.ITEM_RADIO)
            wikiWordMenu.AppendItem(menuItem)
            wx.EVT_MENU(self, GUI_ID.CMD_CLIPBOARD_CATCHER_AT_PAGE,
                    self.OnClipboardCatcherAtPage)
            wx.EVT_UPDATE_UI(self, GUI_ID.CMD_CLIPBOARD_CATCHER_AT_PAGE,
                    self.OnUpdateClipboardCatcher)


            menuItem = wx.MenuItem(wikiWordMenu, GUI_ID.CMD_CLIPBOARD_CATCHER_AT_CURSOR,
                    "Clipboard Catcher at Cursor\t" + self.keyBindings.CatchClipboardAtCursor, 
                    u"Text copied to clipboard is also added to cursor position",
                    wx.ITEM_RADIO)
            wikiWordMenu.AppendItem(menuItem)
            wx.EVT_MENU(self, GUI_ID.CMD_CLIPBOARD_CATCHER_AT_CURSOR,
                    self.OnClipboardCatcherAtCursor)
            wx.EVT_UPDATE_UI(self, GUI_ID.CMD_CLIPBOARD_CATCHER_AT_CURSOR,
                    self.OnUpdateClipboardCatcher)


            menuItem = wx.MenuItem(wikiWordMenu, GUI_ID.CMD_CLIPBOARD_CATCHER_OFF,
                    "Clipboard Catcher off\t" + self.keyBindings.CatchClipboardOff, 
                    u"Switch off clipboard catcher",wx.ITEM_RADIO)
            wikiWordMenu.AppendItem(menuItem)
            wx.EVT_MENU(self, GUI_ID.CMD_CLIPBOARD_CATCHER_OFF,
                    self.OnClipboardCatcherOff)
            wx.EVT_UPDATE_UI(self, GUI_ID.CMD_CLIPBOARD_CATCHER_OFF,
                    self.OnUpdateClipboardCatcher)


        wikiWordMenu.AppendSeparator()

#         menuID=wxNewId()
#         wikiWordMenu.Append(menuID, '&Activate Link/Word\t' + self.keyBindings.ActivateLink, 'Activate Link/Word')
#         EVT_MENU(self, menuID, lambda evt: self.activeEditor.activateLink())
# 
#         menuID=wxNewId()
#         wikiWordMenu.Append(menuID, '&View Parents\t' + self.keyBindings.ViewParents, 'View Parents Of Current Wiki Word')
#         EVT_MENU(self, menuID, lambda evt: self.viewParents(self.getCurrentWikiWord()))
# 
#         menuID=wxNewId()
#         wikiWordMenu.Append(menuID, 'View &Parentless Nodes\t' + self.keyBindings.ViewParentless, 'View nodes with no parent relations')
#         EVT_MENU(self, menuID, lambda evt: self.viewParentLess())
# 
#         menuID=wxNewId()
#         wikiWordMenu.Append(menuID, 'View &Children\t' + self.keyBindings.ViewChildren, 'View Children Of Current Wiki Word')
#         EVT_MENU(self, menuID, lambda evt: self.viewChildren(self.getCurrentWikiWord()))

        self.addMenuItem(wikiWordMenu, '&Activate Link/Word\t' +
                self.keyBindings.ActivateLink, 'Activate link/word',
                lambda evt: self.getActiveEditor().activateLink())

        self.addMenuItem(wikiWordMenu, '&List Parents\t' +
                self.keyBindings.ViewParents,
                'View parents of current wiki word',
                lambda evt: self.viewParents(self.getCurrentWikiWord()))

        self.addMenuItem(wikiWordMenu, 'List &Parentless Nodes\t' +
                self.keyBindings.ViewParentless,
                'View nodes with no parent relations',
                lambda evt: self.viewParentLess())

        self.addMenuItem(wikiWordMenu, 'List &Children\t' +
                self.keyBindings.ViewChildren,
                'View children of current wiki word',
                lambda evt: self.viewChildren(self.getCurrentWikiWord()))

        self.addMenuItem(wikiWordMenu, 'List &Bookmarks\t' +
                self.keyBindings.ViewBookmarks, 'View bookmarks',
                lambda evt: self.viewBookmarks())


        wikiWordMenu.AppendSeparator()

        self.addMenuItem(wikiWordMenu, 'Set As &Root\t' + self.keyBindings.SetAsRoot,
                'Set current wiki word as tree root',
                lambda evt: self.setCurrentWordAsRoot())

        self.addMenuItem(wikiWordMenu, 'S&ynchronize with tree',
                'Find the current wiki word in the tree', lambda evt: self.findCurrentWordInTree(),
                "tb_cycle")


        historyMenu=wx.Menu()

        menuID=wx.NewId()
        historyMenu.Append(menuID, '&List History\t' +
                self.keyBindings.ViewHistory, 'View History')
        wx.EVT_MENU(self, menuID, lambda evt: self.viewHistory())

        menuID=wx.NewId()
        historyMenu.Append(menuID, '&Up History\t' +
                self.keyBindings.UpHistory, 'Up History')
        wx.EVT_MENU(self, menuID, lambda evt: self.viewHistory(-1))

        menuID=wx.NewId()
        historyMenu.Append(menuID, '&Down History\t' +
                self.keyBindings.DownHistory, 'Down History')
        wx.EVT_MENU(self, menuID, lambda evt: self.viewHistory(1))

        self.addMenuItem(historyMenu, '&Back\t' + self.keyBindings.GoBack,
                'Go Back', lambda evt: self.pageHistory.goInHistory(-1),
                "tb_back")

        self.addMenuItem(historyMenu, '&Forward\t' + self.keyBindings.GoForward,
                'Go Forward', lambda evt: self.pageHistory.goInHistory(1),
                "tb_forward")

        self.addMenuItem(historyMenu, '&Wiki Home\t' + self.keyBindings.GoHome,
                'Go to Wiki Home Page',
                lambda evt: self.openWikiPage(self.getWikiDocument().getWikiName(),
                    forceTreeSyncFromRoot=True),
                "tb_home")


        self.editorMenu=wx.Menu()

        self.addMenuItem(self.editorMenu, '&Bold\t' + self.keyBindings.Bold,
                'Bold', lambda evt: self.keyBindings.makeBold(self.getActiveEditor()),
                "tb_bold")

        self.addMenuItem(self.editorMenu, '&Italic\t' + self.keyBindings.Italic,
                'Italic', lambda evt: self.keyBindings.makeItalic(self.getActiveEditor()),
                "tb_italic")

        self.addMenuItem(self.editorMenu, '&Heading\t' + self.keyBindings.Heading,
                'Add Heading', lambda evt: self.keyBindings.addHeading(self.getActiveEditor()),
                "tb_heading")

        self.addMenuItem(self.editorMenu, 'Insert Date\t' + self.keyBindings.InsertDate,
                'Insert Date', lambda evt: self.insertDate(),
                "date")

        self.addMenuItem(self.editorMenu, 'Set Date Format',
                'Set Date Format', lambda evt: self.showDateformatDialog())

        if SpellChecker.isSpellCheckSupported():
            self.addMenuItem(self.editorMenu, 'Spell check\t' + self.keyBindings.SpellCheck,
                    'Spell check current page',
                    lambda evt: self.showSpellCheckerDialog())


        self.addMenuItem(self.editorMenu,
                'Wikize Selected Word\t' + self.keyBindings.MakeWikiWord,
                'Wikize Selected Word',
                lambda evt: self.keyBindings.makeWikiWord(self.getActiveEditor()),
                "pin")


        self.editorMenu.AppendSeparator()

        self.addMenuItem(self.editorMenu, 'Cu&t\t' + self.keyBindings.Cut,
                'Cut', self._OnRoundtripEvent,  # lambda evt: self.activeEditor.Cut(),
                "tb_cut", menuID=GUI_ID.CMD_CLIPBOARD_CUT)

#         self.addMenuItem(self.editorMenu, '&Copy\t' + self.keyBindings.Copy,
#                 'Copy', lambda evt: self.fireMiscEventKeys(("command copy",)), # lambda evt: self.activeEditor.Copy()
#                 "tb_copy", menuID=GUI_ID.CMD_CLIPBOARD_COPY)

        self.addMenuItem(self.editorMenu, '&Copy\t' + self.keyBindings.Copy,
                'Copy', self._OnRoundtripEvent,  # lambda evt: self.activeEditor.Copy()
                "tb_copy", menuID=GUI_ID.CMD_CLIPBOARD_COPY)


        # TODO support copying from preview
        self.addMenuItem(self.editorMenu, 'Copy to &ScratchPad\t' + \
                self.keyBindings.CopyToScratchPad,
                'Copy Text to ScratchPad', lambda evt: self.getActiveEditor().snip(),
                "tb_copy")

#         self.addMenuItem(self.editorMenu, '&Paste\t' + self.keyBindings.Paste,
#                 'Paste', lambda evt: self.activeEditor.Paste(),
#                 "tb_paste", menuID=GUI_ID.CMD_CLIPBOARD_PASTE)

        self.addMenuItem(self.editorMenu, '&Paste\t' + self.keyBindings.Paste,
                'Paste', self._OnRoundtripEvent,  # lambda evt: self.activeEditor.Paste(),
                "tb_paste", menuID=GUI_ID.CMD_CLIPBOARD_PASTE)


        self.editorMenu.AppendSeparator()

        self.addMenuItem(self.editorMenu, '&Undo\t' + self.keyBindings.Undo,
                'Undo', self._OnRoundtripEvent, menuID=GUI_ID.CMD_UNDO)

        self.addMenuItem(self.editorMenu, '&Redo\t' + self.keyBindings.Redo,
                'Redo', self._OnRoundtripEvent, menuID=GUI_ID.CMD_REDO)

#         self.addMenuItem(self.editorMenu, '&Undo\t' + self.keyBindings.Undo,
#                 'Undo', lambda evt: self.activeEditor.CmdKeyExecute(wxSTC_CMD_UNDO))
# 
#         self.addMenuItem(self.editorMenu, '&Redo\t' + self.keyBindings.Redo,
#                 'Redo', lambda evt: self.activeEditor.CmdKeyExecute(wxSTC_CMD_REDO))


        self.editorMenu.AppendSeparator()
        
        self.textBlocksMenuPosition = self.editorMenu.GetMenuItemCount()

        self.editorMenu.AppendMenu(wx.NewId(), '&Text blocks',
                self.buildTextBlocksMenu())

        # Build icon menu
        if self.lowResources:
            # Add only menu item for icon select dialog
            self.addMenuItem(self.editorMenu, 'Add icon property',
                    'Open icon select dialog', lambda evt: self.showIconSelectDialog())
        else:
            # Build full submenu for icons
            iconsMenu, self.cmdIdToIconName = PropertyHandling.buildIconsSubmenu(
                    wx.GetApp().getIconCache())
            for cmi in self.cmdIdToIconName.keys():
                wx.EVT_MENU(self, cmi, self.OnInsertIconAttribute)

            self.editorMenu.AppendMenu(wx.NewId(), 'Add icon property', iconsMenu)

        # Build submenu for colors
        colorsMenu, self.cmdIdToColorName = PropertyHandling.buildColorsSubmenu()
        for cmi in self.cmdIdToColorName.keys():
            wx.EVT_MENU(self, cmi, self.OnInsertColorAttribute)

        self.editorMenu.AppendMenu(wx.NewId(), 'Add color property', colorsMenu)

        self.addMenuItem(self.editorMenu, 'Add &file URL' +
                self.keyBindings.AddFileUrl, 'Use file dialog to add URL',
                lambda evt: self.showAddFileUrlDialog())



        self.editorMenu.AppendSeparator()

#         menuID=wxNewId()
#         formattingMenu.Append(menuID, '&Find\t', 'Find')
#         EVT_MENU(self, menuID, lambda evt: self.showFindDialog())

        menuID=wx.NewId()
        self.editorMenu.Append(menuID, 'Find and &Replace\t' + self.keyBindings.FindAndReplace, 'Find and Replace')
        wx.EVT_MENU(self, menuID, lambda evt: self.showFindReplaceDialog())

        menuID=wx.NewId()
        self.editorMenu.Append(menuID, 'Rep&lace Text by WikiWord\t' + self.keyBindings.ReplaceTextByWikiword, 'Replace selected text by WikiWord')
        wx.EVT_MENU(self, menuID, lambda evt: self.showReplaceTextByWikiwordDialog())

        self.editorMenu.AppendSeparator()

        menuID=wx.NewId()
        self.editorMenu.Append(menuID, '&Rewrap Text\t' + self.keyBindings.RewrapText, 'Rewrap Text')
        wx.EVT_MENU(self, menuID, lambda evt: self.getActiveEditor().rewrapText())

        menuID=wx.NewId()
        wrapModeMenuItem = wx.MenuItem(self.editorMenu, menuID, "&Wrap Mode", "Set wrap mode", wx.ITEM_CHECK)
        self.editorMenu.AppendItem(wrapModeMenuItem)
        wx.EVT_MENU(self, menuID, self.OnCmdCheckWrapMode)

        wrapModeMenuItem.Check(self.getActiveEditor().getWrapMode())


        menuID=wx.NewId()
        autoIndentMenuItem = wx.MenuItem(self.editorMenu, menuID,
                "Auto-indent", "Auto indentation", wx.ITEM_CHECK)
        self.editorMenu.AppendItem(autoIndentMenuItem)
        wx.EVT_MENU(self, menuID, self.OnCmdCheckAutoIndent)

        autoIndentMenuItem.Check(self.getActiveEditor().getAutoIndent())


        menuID=wx.NewId()
        autoBulletsMenuItem = wx.MenuItem(self.editorMenu, menuID,
                "Auto-bullets", "Show bullet on next line if current has one",
                wx.ITEM_CHECK)
        self.editorMenu.AppendItem(autoBulletsMenuItem)
        wx.EVT_MENU(self, menuID, self.OnCmdCheckAutoBullets)

        autoBulletsMenuItem.Check(self.getActiveEditor().getAutoBullets())

        self.editorMenu.AppendSeparator()


        evaluationMenu=wx.Menu()

        self.addMenuItem(evaluationMenu, '&Eval\t' + self.keyBindings.Eval,
                'Eval Script Blocks',
                lambda evt: self.getActiveEditor().evalScriptBlocks())

        for i in xrange(1,7):
            self.addMenuItem(evaluationMenu, 'Eval Function &%i\tCtrl-%i' % (i, i),
                    'Eval Script Function %i' % i,
                    lambda evt, i=i: self.getActiveEditor().evalScriptBlocks(i))
                    
        self.editorMenu.AppendMenu(wx.NewId(), "Evaluation", evaluationMenu,
                "Evaluate scripts/expressions")



#         menuID=wxNewId()
#         self.editorMenu.Append(menuID, '&Eval\t' + self.keyBindings.Eval, 'Eval Script Blocks')
#         EVT_MENU(self, menuID, lambda evt: self.activeEditor.evalScriptBlocks())
# 
#         menuID=wxNewId()
#         self.editorMenu.Append(menuID, 'Eval Function &1\tCtrl-1', 'Eval Script Function 1')
#         EVT_MENU(self, menuID, lambda evt: self.activeEditor.evalScriptBlocks(1))
# 
#         menuID=wxNewId()
#         self.editorMenu.Append(menuID, 'Eval Function &2\tCtrl-2', 'Eval Script Function 2')
#         EVT_MENU(self, menuID, lambda evt: self.activeEditor.evalScriptBlocks(2))
# 
#         menuID=wxNewId()
#         self.editorMenu.Append(menuID, 'Eval Function &3\tCtrl-3', 'Eval Script Function 3')
#         EVT_MENU(self, menuID, lambda evt: self.activeEditor.evalScriptBlocks(3))
# 
#         menuID=wxNewId()
#         self.editorMenu.Append(menuID, 'Eval Function &4\tCtrl-4', 'Eval Script Function 4')
#         EVT_MENU(self, menuID, lambda evt: self.activeEditor.evalScriptBlocks(4))
# 
#         menuID=wxNewId()
#         self.editorMenu.Append(menuID, 'Eval Function &5\tCtrl-5', 'Eval Script Function 5')
#         EVT_MENU(self, menuID, lambda evt: self.activeEditor.evalScriptBlocks(5))
# 
#         menuID=wxNewId()
#         self.editorMenu.Append(menuID, 'Eval Function &6\tCtrl-6', 'Eval Script Function 6')
#         EVT_MENU(self, menuID, lambda evt: self.activeEditor.evalScriptBlocks(6))


        viewMenu = wx.Menu()
        
# self.addMenuItem(self.editorMenu, '&Redo\t' + self.keyBindings.Redo,
#         'Redo', self._OnRoundtripEvent, menuID=GUI_ID.CMD_REDO)


#         self.addMenuItem(viewMenu, '&Zoom In\t' + self.keyBindings.ZoomIn,
#                 'Zoom In', lambda evt: self.getActiveEditor().CmdKeyExecute(wxSTC_CMD_ZOOMIN),
#                 "tb_zoomin", menuID=GUI_ID.CMD_ZOOM_IN)
# 
#         self.addMenuItem(viewMenu, 'Zoo&m Out\t' + self.keyBindings.ZoomOut,
#                 'Zoom Out', lambda evt: self.getActiveEditor().CmdKeyExecute(wxSTC_CMD_ZOOMOUT),
#                 "tb_zoomout", menuID=GUI_ID.CMD_ZOOM_OUT)
        self.addMenuItem(viewMenu, '&Zoom In\t' + self.keyBindings.ZoomIn,
                'Zoom In', self._OnRoundtripEvent, "tb_zoomin",
                menuID=GUI_ID.CMD_ZOOM_IN)

        self.addMenuItem(viewMenu, 'Zoo&m Out\t' + self.keyBindings.ZoomOut,
                'Zoom Out', self._OnRoundtripEvent, "tb_zoomout",
                menuID=GUI_ID.CMD_ZOOM_OUT)

        viewMenu.AppendSeparator()


        menuID = wx.NewId()
        menuItem = wx.MenuItem(viewMenu, menuID,
                "&Show Tree Control\t" + self.keyBindings.ShowTreeControl,
                "Show Tree Control", wx.ITEM_CHECK)
        viewMenu.AppendItem(menuItem)
        wx.EVT_MENU(self, menuID, lambda evt: self.setShowTreeControl(
                self.windowLayouter.isWindowCollapsed("maintree")))
        wx.EVT_UPDATE_UI(self, menuID, self.OnUpdateTreeCtrlMenuItem)

        menuItem = wx.MenuItem(viewMenu, GUI_ID.CMD_SHOW_TOOLBAR,
                "Show Toolbar\t" + self.keyBindings.ShowToolbar, 
                "Show Toolbar", wx.ITEM_CHECK)
        viewMenu.AppendItem(menuItem)
        wx.EVT_MENU(self, GUI_ID.CMD_SHOW_TOOLBAR, lambda evt: self.setShowToolbar(
                not self.getConfig().getboolean("main", "toolbar_show", True)))
        wx.EVT_UPDATE_UI(self, GUI_ID.CMD_SHOW_TOOLBAR,
                self.OnUpdateToolbarMenuItem)

        menuItem = wx.MenuItem(viewMenu, GUI_ID.CMD_STAY_ON_TOP,
                "Stay on Top\t" + self.keyBindings.StayOnTop, 
                "Stay on Top", wx.ITEM_CHECK)
        viewMenu.AppendItem(menuItem)
        wx.EVT_MENU(self, GUI_ID.CMD_STAY_ON_TOP, lambda evt: self.setStayOnTop(
                not self.getStayOnTop()))
        wx.EVT_UPDATE_UI(self, GUI_ID.CMD_STAY_ON_TOP,
                self.OnUpdateStayOnTopMenuItem)


        menuID=wx.NewId()
        indentGuidesMenuItem = wx.MenuItem(viewMenu, menuID,
                "&View Indentation Guides", "View Indentation Guides", wx.ITEM_CHECK)
        viewMenu.AppendItem(indentGuidesMenuItem)
        wx.EVT_MENU(self, menuID, self.OnCmdCheckIndentationGuides)

        indentGuidesMenuItem.Check(self.getActiveEditor().GetIndentationGuides())

        menuID=wx.NewId()
        showLineNumbersMenuItem = wx.MenuItem(viewMenu, menuID,
                "Show line numbers", "Show line numbers",
                wx.ITEM_CHECK)
        viewMenu.AppendItem(showLineNumbersMenuItem)
        wx.EVT_MENU(self, menuID, self.OnCmdCheckShowLineNumbers)

        showLineNumbersMenuItem.Check(self.getActiveEditor().getShowLineNumbers())

        viewMenu.AppendSeparator()

        self.addMenuItem(viewMenu, 'Clone Window\t' + self.keyBindings.CloneWindow,
                'Create new window for same wiki', self.OnCmdCloneWindow)


        helpMenu = wx.Menu()

        def openHelp(evt):
            try:
                clAction = CmdLineAction([])
                clAction.wikiToOpen = self.wikiPadHelp
                wx.GetApp().startPersonalWikiFrame(clAction)
#                 PersonalWikiFrame(None, -1, "WikidPad", self.wikiAppDir,
#                         self.globalConfigDir, self.globalConfigSubDir, clAction)
                # os.startfile(self.wikiPadHelp)   # TODO!
            except Exception, e:
                traceback.print_exc()
                self.displayErrorMessage('Error while starting new '
                        'WikidPad instance', e)
                return


        menuID=wx.NewId()
        helpMenu.Append(menuID, '&Open WikidPadHelp', 'Open WikidPadHelp')
        wx.EVT_MENU(self, menuID, openHelp)

        helpMenu.AppendSeparator()

        menuID=wx.NewId()
        helpMenu.Append(menuID, '&Visit wikidPad Homepage', 'Visit Homepage')
        wx.EVT_MENU(self, menuID, lambda evt: OsAbstract.startFile(
                u"http://wikidpad.sourceforge.net"))

        helpMenu.AppendSeparator()

        menuID=wx.NewId()
        helpMenu.Append(menuID, 'View &License', 'View License')
        wx.EVT_MENU(self, menuID, lambda evt: OsAbstract.startFile(
                join(self.wikiAppDir, u'license.txt')))

        helpMenu.AppendSeparator()

        menuID=wx.NewId()
        helpMenu.Append(menuID, '&About', 'About WikidPad')
        wx.EVT_MENU(self, menuID, lambda evt: self.showAboutDialog())

        # get info for any plugin menu items and create them as necessary
        pluginMenu = None
        menuItems = reduce(lambda a, b: a+list(b),
                self.menuFunctions.describeMenuItems(self), [])
        if len(menuItems) > 0:
            pluginMenu = wx.Menu()
            subStructure = {}

            def addPluginMenuItem(function, label, statustext, icondesc=None,
                    menuID=None):
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

                self.addMenuItem(menu, labelComponents[-1], statustext,
                        lambda evt: function(self, evt), icondesc, menuID)

            for item in menuItems:
                addPluginMenuItem(*item)

        self.mainmenu.Append(wikiMenu, 'W&iki')
        self.mainmenu.Append(wikiWordMenu, '&Wiki Words')
        self.mainmenu.Append(historyMenu, '&History')
        self.mainmenu.Append(self.editorMenu, '&Editor')
        self.mainmenu.Append(viewMenu, '&View')
        if pluginMenu:
            self.mainmenu.Append(pluginMenu, "Pl&ugins")
        self.mainmenu.Append(helpMenu, 'He&lp')

        self.SetMenuBar(self.mainmenu)

        if self.getWikiConfigPath():  # If a wiki is open
            self.mainmenu.EnableTop(1, 1)
            self.mainmenu.EnableTop(2, 1)
            self.mainmenu.EnableTop(3, 1)
        else:
            self.mainmenu.EnableTop(1, 0)
            self.mainmenu.EnableTop(2, 0)
            self.mainmenu.EnableTop(3, 0)

        # turn on or off the wrap mode menu item. this must be done here,
        # after the menus are added to the menu bar
#         if self.wrapMode:
#             wrapModeMenuItem.Check(1)

        # turn on or off auto-save
#         if self.autoSave:
#             autoSaveMenuItem.Check(1)

        # turn on or off indentation guides
#         if self.indentationGuides:
#             indentGuidesMenuItem.Check(1)


    def buildToolbar(self):
        # ------------------------------------------------------------------------------------
        # Create the toolbar
        # ------------------------------------------------------------------------------------

        tb = self.CreateToolBar(wx.TB_HORIZONTAL | wx.NO_BORDER | wx.TB_FLAT | wx.TB_TEXT)
        seperator = self.lookupIcon("tb_seperator")

        icon = self.lookupIcon("tb_back")
        tbID = wx.NewId()
        tb.AddSimpleTool(tbID, icon, "Back", "Back")
        wx.EVT_TOOL(self, tbID, lambda evt: self.pageHistory.goInHistory(-1))

        icon = self.lookupIcon("tb_forward")
        tbID = wx.NewId()
        tb.AddSimpleTool(tbID, icon, "Forward", "Forward")
        wx.EVT_TOOL(self, tbID, lambda evt: self.pageHistory.goInHistory(1))

        icon = self.lookupIcon("tb_home")
        tbID = wx.NewId()
        tb.AddSimpleTool(tbID, icon, "Wiki Home", "Wiki Home")
        wx.EVT_TOOL(self, tbID,
                lambda evt: self.openWikiPage(self.getWikiDocument().getWikiName(),
                forceTreeSyncFromRoot=True))

        icon = self.lookupIcon("tb_doc")
        tbID = wx.NewId()
        tb.AddSimpleTool(tbID, icon, "Open Wiki Word", "Open Wiki Word")
        wx.EVT_TOOL(self, tbID, lambda evt: self.showWikiWordOpenDialog())

        icon = self.lookupIcon("tb_lens")
        tbID = wx.NewId()
        tb.AddSimpleTool(tbID, icon, "Search", "Search")
        wx.EVT_TOOL(self, tbID, lambda evt: self.showSearchDialog())

        icon = self.lookupIcon("tb_cycle")
        tbID = wx.NewId()
        tb.AddSimpleTool(tbID, icon, "Find current word in tree", "Find current word in tree")
        wx.EVT_TOOL(self, tbID, lambda evt: self.findCurrentWordInTree())

        tb.AddSimpleTool(wx.NewId(), seperator, "Separator", "Separator")

        icon = self.lookupIcon("tb_save")
        tb.AddSimpleTool(GUI_ID.CMD_SAVE_WIKI, icon, "Save Wiki Word",
                "Save Wiki Word")
        wx.EVT_TOOL(self, GUI_ID.CMD_SAVE_WIKI,
                lambda evt: (self.saveAllDocPages(force=True),
                self.getWikiData().commit()))

        icon = self.lookupIcon("tb_rename")
        tbID = wx.NewId()
        tb.AddSimpleTool(tbID, icon, "Rename Wiki Word", "Rename Wiki Word")
        wx.EVT_TOOL(self, tbID, lambda evt: self.showWikiWordRenameDialog())

        icon = self.lookupIcon("tb_delete")
        tbID = wx.NewId()
        tb.AddSimpleTool(tbID, icon, "Delete", "Delete Wiki Word")
        wx.EVT_TOOL(self, tbID, lambda evt: self.showWikiWordDeleteDialog())

        tb.AddSimpleTool(wx.NewId(), seperator, "Separator", "Separator")

        icon = self.lookupIcon("tb_heading")
        tbID = wx.NewId()
        tb.AddSimpleTool(tbID, icon, "Heading", "Heading")
        wx.EVT_TOOL(self, tbID, lambda evt: self.keyBindings.addHeading(self.getActiveEditor()))

        icon = self.lookupIcon("tb_bold")
        tbID = wx.NewId()
        tb.AddSimpleTool(tbID, icon, "Bold", "Bold")
        wx.EVT_TOOL(self, tbID, lambda evt: self.keyBindings.makeBold(self.getActiveEditor()))

        icon = self.lookupIcon("tb_italic")
        tbID = wx.NewId()
        tb.AddSimpleTool(tbID, icon, "Italic)", "Italic")
        wx.EVT_TOOL(self, tbID, lambda evt: self.keyBindings.makeItalic(self.getActiveEditor()))

        tb.AddSimpleTool(wx.NewId(), seperator, "Separator", "Separator")

#         icon = self.lookupIcon("tb_zoomin")
#         tbID = wxNewId()
#         tb.AddSimpleTool(tbID, icon, "Zoom In", "Zoom In")
#         EVT_TOOL(self, tbID, lambda evt: self.getActiveEditor().CmdKeyExecute(wxSTC_CMD_ZOOMIN))
# 
#         icon = self.lookupIcon("tb_zoomout")
#         tbID = wxNewId()
#         tb.AddSimpleTool(tbID, icon, "Zoom Out", "Zoom Out")
#         EVT_TOOL(self, tbID, lambda evt: self.getActiveEditor().CmdKeyExecute(wxSTC_CMD_ZOOMOUT))
        icon = self.lookupIcon("tb_zoomin")
        tbID = GUI_ID.CMD_ZOOM_IN
        tb.AddSimpleTool(tbID, icon, "Zoom In", "Zoom In")
        wx.EVT_TOOL(self, tbID, self._OnRoundtripEvent)

        icon = self.lookupIcon("tb_zoomout")
        tbID = GUI_ID.CMD_ZOOM_OUT
        tb.AddSimpleTool(tbID, icon, "Zoom Out", "Zoom Out")
        wx.EVT_TOOL(self, tbID, self._OnRoundtripEvent)


        self.fastSearchField = wx.TextCtrl(tb, GUI_ID.TF_FASTSEARCH,
                style=wx.TE_PROCESS_ENTER | wx.TE_RICH)
        tb.AddControl(self.fastSearchField)
#         EVT_TEXT_ENTER(self, GUI_ID.TF_FASTSEARCH, self.OnFastSearchEnter)
#         EVT_CHAR(self.fastSearchField, self.OnFastSearchChar)
        wx.EVT_KEY_DOWN(self.fastSearchField, self.OnFastSearchKeyDown)
#         EVT_KEY_UP(self.fastSearchField, self.OnFastSearchChar)

        icon = self.lookupIcon("pin")
        tbID = wx.NewId()
        tb.AddSimpleTool(tbID, icon, "Wikize Selected Word", "Wikize Selected Word")
        wx.EVT_TOOL(self, tbID, lambda evt: self.keyBindings.makeWikiWord(self.getActiveEditor()))



        # get info for any plugin toolbar items and create them as necessary
        toolbarItems = reduce(lambda a, b: a+list(b),
                self.toolbarFunctions.describeToolbarItems(self), [])
        
        def addPluginTool(function, tooltip, statustext, icondesc, tbID=None):
            if tbID is None:
                tbID = wx.NewId()
                
            icon = self.resolveIconDescriptor(icondesc, self.lookupIcon(u"tb_doc"))
            # tb.AddLabelTool(tbID, label, icon, wxNullBitmap, 0, tooltip)
            tb.AddSimpleTool(tbID, icon, tooltip, statustext)
            wx.EVT_TOOL(self, tbID, lambda evt: function(self, evt))
            
        for item in toolbarItems:
            addPluginTool(*item)


        tb.Realize()



#     _LAYOUT_DEFINITION = (
#         {
#             "name": "main area panel"
#         },
#         {
#             "name": "maintree",
#             "layout relative to": "main area panel",
#             "layout relation": "left"
#         },
#         {
#             "name": "viewstree",
#             "layout relative to": "maintree",
#             "layout relation": "below"
#         },
#         {
#             "name": "log",
#             "layout relative to": "main area panel",
#             "layout relation": "below"
#         }
#     )


    def initializeGui(self):
        "initializes the gui environment"

#         # ------------------------------------------------------------------------------------
#         # load the icons the program will use
#         # ------------------------------------------------------------------------------------
# 
#         # add the gif handler for gif icon support
#         wxImage_AddHandler(wxGIFHandler())
#         ## create the image icon list
#         # iconList = wxImageList(16, 16)
#         # default icon is page.gif
#         icons = ['page.gif']
#         # add the rest of the icons
#         icons.extend([file for file in os.listdir(join(self.wikiAppDir, "icons"))
#                       if file.endswith('.gif') and file != 'page.gif'])
# 
#         self.iconFileList = icons
# 
# #         # Create iconImageList
# #         self.fillIconLookupCache(True)


        # Build layout:

        self.windowLayouter = WindowLayouter(self, self.createWindow)

        cfstr = self.getConfig().get("main", "windowLayout")
        self.windowLayouter.setWinPropsByConfig(cfstr)
       

        self.windowLayouter.realize()

        self.tree = self.windowLayouter.getWindowForName("maintree")
        self.logWindow = self.windowLayouter.getWindowForName("log")
        

        wx.EVT_NOTEBOOK_PAGE_CHANGED(self, self.mainAreaPanel.GetId(),
                self.OnNotebookPageChanged)
        wx.EVT_SET_FOCUS(self.mainAreaPanel, self.OnNotebookFocused)


        # ------------------------------------------------------------------------------------
        # Create menu and toolbar
        # ------------------------------------------------------------------------------------
        
        self.buildMainMenu()
        if self.getConfig().getboolean("main", "toolbar_show", True):
            self.setShowToolbar(True)

        wx.EVT_MENU(self, GUI_ID.CMD_SWITCH_FOCUS, self.OnSwitchFocus)

        # Add alternative accelerators for clipboard operations
        accs = [
            (wx.ACCEL_CTRL, wx.WXK_INSERT, GUI_ID.CMD_CLIPBOARD_COPY),
            (wx.ACCEL_SHIFT, wx.WXK_INSERT, GUI_ID.CMD_CLIPBOARD_PASTE),
            (wx.ACCEL_SHIFT, wx.WXK_DELETE, GUI_ID.CMD_CLIPBOARD_CUT),
            ]
            
        accP = self.keyBindings.getAccelPair("SwitchFocus")
        if accP != (None, None):
            accs.append((accP[0], accP[1], GUI_ID.CMD_SWITCH_FOCUS))

        if Configuration.isLinux():   # Actually if wxGTK
            accs += [(wx.ACCEL_NORMAL, fkey, GUI_ID.SPECIAL_EAT_KEY)
                    for fkey in range(wx.WXK_F1, wx.WXK_F24 + 1)] + \
                    [(wx.ACCEL_SHIFT, fkey, GUI_ID.SPECIAL_EAT_KEY)
                    for fkey in range(wx.WXK_F1, wx.WXK_F24 + 1)]
    
            wx.EVT_MENU(self, GUI_ID.SPECIAL_EAT_KEY, lambda evt: None)

        self.SetAcceleratorTable(wx.AcceleratorTable(accs))

        # ------------------------------------------------------------------------------------
        # Create the status bar
        # ------------------------------------------------------------------------------------
        self.statusBar = wx.StatusBar(self, -1)
        self.statusBar.SetFieldsCount(3)

        # Measure necessary widths of status fields
        dc = wx.ClientDC(self.statusBar)
        try:
            dc.SetFont(self.statusBar.GetFont())
            posWidth = dc.GetTextExtent(
                    u"Line: 9999 Col: 9999 Pos: 9999999988888")[0]
            dc.SetFont(wx.NullFont)
        finally:
            del dc
            
        
        # Check if window should stay on top
        self.setStayOnTop(self.getConfig().getboolean("main", "frame_stayOnTop",
                False))

        self.statusBar.SetStatusWidths([-1, -1, posWidth])
        self.SetStatusBar(self.statusBar)

        # Register the App IDLE handler
        wx.EVT_IDLE(self, self.OnIdle)

        # Register the App close handler
        wx.EVT_CLOSE(self, self.OnCloseButton)

        # Check resizing to layout sash windows
        wx.EVT_SIZE(self, self.OnSize)

        wx.EVT_ICONIZE(self, self.OnIconize)
        wx.EVT_MAXIMIZE(self, self.OnMaximize)


    def OnUpdateTreeCtrlMenuItem(self, evt):
#         evt.Check(not self.treeSashWindow.isCollapsed())
        evt.Check(not self.windowLayouter.isWindowCollapsed("maintree"))
        
    def OnUpdateToolbarMenuItem(self, evt):
        evt.Check(not self.GetToolBar() is None)

    def OnUpdateStayOnTopMenuItem(self, evt):
        evt.Check(self.getStayOnTop())


    def OnSwitchFocus(self, evt):
        foc = wx.Window.FindFocus()
        mainAreaPanel = self.mainAreaPanel
        while foc != None:
            if foc == mainAreaPanel:
                self.tree.SetFocus()
                return
            
            foc = foc.GetParent()
            
        mainAreaPanel.SetFocus()


    def OnFastSearchKeyDown(self, evt):
        """
        Process EVT_KEY_DOWN in the fast search text field
        """
        acc = getAccelPairFromKeyDown(evt)
        if acc == (wx.ACCEL_NORMAL, wx.WXK_RETURN) or \
                acc == (wx.ACCEL_NORMAL, wx.WXK_NUMPAD_ENTER):
            text = guiToUni(self.fastSearchField.GetValue())
            tfHeight = self.fastSearchField.GetSize()[1]
            pos = self.fastSearchField.ClientToScreen((0, tfHeight))

            popup = FastSearchPopup(self, self, -1, pos=pos)
            popup.Show()
            try:
                popup.runSearchOnWiki(text)
            except re.error, e:
                popup.Show(False)
                self.displayErrorMessage('Regular expression error', e)
        else:
            evt.Skip()

#     def OnFastSearchChar(self, evt):
#         print "OnFastSearchChar", repr(evt.GetUnicodeKey()), repr(evt.GetKeyCode())
#         evt.Skip()

    def OnCmdReconnectDatabase(self, evt):
        result = wx.MessageBox(u"Are you sure you want to reconnect? "
                u"You may lose some data by this process.",
                u'Reconnect database',
                wx.YES_NO | wx.YES_DEFAULT | wx.ICON_QUESTION, self)

        wd = self.getWikiDocument()
        if result == wx.YES and wd is not None:
            wd.setReadAccessFailed(True)
            wd.setWriteAccessFailed(True)
            # Try reading
            while True:
                try:
                    wd.reconnect()
                    wd.setReadAccessFailed(False)
                    break   # Success
                except (IOError, OSError, DbAccessError), e:
                    sys.stderr.write("Error while trying to reconnect:\n")
                    traceback.print_exc()
                    result = wx.MessageBox(uniToGui((
                            u'There was an error while reconnecting the database\n\n'
                            u'Would you like to try it again?\n%s') %
                            e), u'Error reconnecting!',
                            wx.YES_NO | wx.YES_DEFAULT | wx.ICON_QUESTION, self)
                    if result == wx.NO:
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
                    sys.stderr.write("Error while trying to write:\n")
                    traceback.print_exc()
                    result = wx.MessageBox(uniToGui((
                            u'There was an error while writing to the database\n\n'
                            u'Would you like to try it again?\n%s') %
                            e), u'Error writing!',
                            wx.YES_NO | wx.YES_DEFAULT | wx.ICON_QUESTION, self)
                    if result == wx.NO:
                        break

                

    def OnRemoteCommand(self, evt):
        try:
            clAction = CmdLineAction(evt.getCmdLine())
            wx.GetApp().startPersonalWikiFrame(clAction)
        except Exception, e:
            traceback.print_exc()
            self.displayErrorMessage('Error while starting new '
                    'WikidPad instance', e)
            return


    def createWindow(self, winProps, parent):
        """
        Creates tree, editor, splitter, ... according to the given window name
        in winProps
        """
        winName = winProps["name"]
        if winName == "maintree" or winName == "viewstree":
            tree = WikiTreeCtrl(self, parent, -1)
            # assign the image list
            try:
                tree.AssignImageList(wx.GetApp().getIconCache().getNewImageList())
            except Exception, e:
                traceback.print_exc()
                self.displayErrorMessage('There was an error loading the icons '
                        'for the tree control.', e)
            if self.getWikiConfigPath() is not None and winName == "viewstree":
                tree.setViewsAsRoot()
            return tree
        elif winName.startswith("txteditor"):
            editor = WikiTxtCtrl(winProps["presenter"], parent, -1)
            editor.evalScope = { 'editor' : editor,
                    'pwiki' : self, 'lib': self.evalLib}
    
            # enable and zoom the editor
            editor.Enable(0)
            editor.SetZoom(self.configuration.getint("main", "zoom"))
            self.editors.append(editor)
            return editor
        elif winName == "log":
            return LogWindow(parent, -1, self)
        elif winName == "main area panel":  # TODO remove this hack
            self.mainAreaPanel = wx.Notebook(parent, -1)
            
            presenter = DocPagePresenter(self)
                    
#             self.activeEditor = self.createWindow({"name": "txteditor1"},
#                     self.mainAreaPanel)
            editor = self.createWindow({"name": "txteditor1",
                    "presenter": presenter}, self.mainAreaPanel)
            self.mainAreaPanel.AddPage(editor, u"Edit")
            presenter.setSubControl("textedit", editor)
            
            self.htmlView = createWikiHtmlView(presenter, self.mainAreaPanel, -1)
            self.mainAreaPanel.AddPage(self.htmlView, u"Preview")
            presenter.setSubControl("preview", self.htmlView)
            
            self.currentDocPagePresenter = presenter
            self.currentDocPagePresenter.setVisible(True)
            

#             editor = self.createWindow({"name": "txteditor2"},
#                     self.mainAreaPanel)
#             self.mainAreaPanel.AddPage(editor, u"Edit2")
            
            return self.mainAreaPanel
            
    def getPagePresenterControlNames(self):
        return ["textedit", "preview"]


    def appendLogMessage(self, msg):
        """
        Add message to log window, make log window visible if necessary
        """
        if self.configuration.getboolean("main", "log_window_autoshow"):
            self.windowLayouter.uncollapseWindow("log")
        self.logWindow.appendMessage(msg)

    def hideLogWindow(self):
        self.windowLayouter.collapseWindow("log")


    def resourceSleep(self):
        """
        Free unnecessary resources if program is iconized
        """
        if self.sleepMode:
            return  # Already in sleep mode
        self.sleepMode = True
        
        toolBar = self.GetToolBar()
        if toolBar is not None:
            toolBar.Destroy()

        self.SetMenuBar(None)
        self.mainmenu.Destroy()

        # Set menu/menu items to None
        self.mainmenu = None
        self.recentWikisMenu = None
        # self.showOnTrayMenuItem = None

        # TODO Clear cache only if exactly one window uses centralized iconLookupCache
        #      Maybe weak references?
#         for k in self.iconLookupCache.keys():
#             self.iconLookupCache[k] = (self.iconLookupCache[k][0], None)
##      Even worse:  wxGetApp().getIconCache().clearIconBitmaps()

        gc.collect()


    def resourceWakeup(self):
        """
        Aquire resources after program is restored
        """
        if not self.sleepMode:
            return  # Already in wake mode
        self.sleepMode = False

        self.buildMainMenu()
        self.setShowToolbar(self.getConfig().getboolean("main", "toolbar_show",
                True))
        self.setShowOnTray()


#     _TEST_LAYOUT_DEFINITION = (
#         {
#             "name": "main area panel"
#         },
#         {
#             "name": "maintree",
#             "layout relative to": "main area panel",
#             "layout relation": "left"
#         },
#         {
#             "name": "viewstree",
#             "layout relative to": "maintree",
#             "layout relation": "above"
#         },
#         {
#             "name": "log",
#             "layout relative to": "main area panel",
#             "layout relation": "below"
#         }
#     )

    def testIt(self):
        rect = self.statusBar.GetFieldRect(0)
        
        dc = wx.WindowDC(self.statusBar)
        dc.SetBrush(wx.RED_BRUSH)
        dc.SetPen(wx.RED_PEN)
        dc.DrawRectangle(rect.x, rect.y, rect.width, rect.height)
        dc.SetPen(wx.WHITE_PEN)
        dc.SetFont(self.statusBar.GetFont())
        dc.DrawText(u"Saving page", rect.x + 2, rect.y + 2)
        dc.SetFont(wx.NullFont)
        dc.SetBrush(wx.NullBrush)
        dc.SetPen(wx.NullPen)

        # self.statusBar.Refresh()



    def OnNotebookPageChanged(self, evt):
        try:
            if evt.GetSelection() == 0:
                subControl = "textedit"
            elif evt.GetSelection() == 1:
                subControl = "preview"
                
            self.getCurrentDocPagePresenter().switchSubControl(subControl)
            self.mainAreaPanel.GetPage(evt.GetSelection()).SetFocus()
        except (IOError, OSError, DbAccessError), e:
            self.lostAccess(e)
            raise


    def OnNotebookFocused(self, evt):
        self.mainAreaPanel.GetCurrentPage().SetFocus()

    def OnIconize(self, evt):
        if self.lowResources:
            if self.IsIconized():
                self.resourceSleep()
            else:
                self.resourceWakeup()

        if self.configuration.getboolean("main", "showontray"):
            self.Show(not self.IsIconized())

        evt.Skip()


    def OnMaximize(self, evt):
        if self.lowResources:
            self.resourceWakeup()

        evt.Skip()


    def resetGui(self):
        # delete everything in the current tree
        self.tree.DeleteAllItems()

        # reset the editor
        self.getActiveEditor().loadWikiPage(None)
        self.getActiveEditor().SetSelection(-1, -1)
        self.getActiveEditor().EmptyUndoBuffer()
        self.getActiveEditor().Disable()

        # reset tray
        self.setShowOnTray()

#     def getCurrentText(self):
#         """
#         Return the raw input text of current wiki word
#         """
#         return self.getActiveEditor().GetText()


    def newWiki(self, wikiName, wikiDir):
        "creates a new wiki"
        wdhandlers = DbBackendUtils.listHandlers()
        if len(wdhandlers) == 0:
            self.displayErrorMessage(
                    'No data handler available to create database.')
            return

        wikiName = string.replace(wikiName, u" ", u"")
        wikiDir = join(wikiDir, wikiName)
        configFileLoc = join(wikiDir, u"%s.wiki" % wikiName)

#         self.statusBar.SetStatusText(uniToGui(u"Creating Wiki: %s" % wikiName), 0)

        createIt = True;
        if (exists(pathEnc(wikiDir))):
            dlg=wx.MessageDialog(self,
                    uniToGui((u"A wiki already exists in '%s', overwrite? "
                    u"(This deletes everything in and below this directory!)") %
                    wikiDir), u'Warning', wx.YES_NO)
            result = dlg.ShowModal()
            dlg.Destroy()
            if result == wx.ID_YES:
                os.rmdir(wikiDir)  # TODO BUG!!!
                createIt = True
            elif result == wx.ID_NO:
                createIt = False

        if createIt:
            # Ask for the data handler to use
            index = wx.GetSingleChoiceIndex(u"Choose database type",
                    u"Choose database type", [wdh[1] for wdh in wdhandlers],
                    self)
            if index == -1:
                return

            wdhName = wdhandlers[index][0]
                
#             wikiDataFactory, createWikiDbFunc = DbBackendUtils.getHandler(self, 
#                     wdhName)
#                     
#             if wikiDataFactory is None:
#                 self.displayErrorMessage(
#                         'Data handler %s not available' % wdh[0])
#                 return
            

            # create the new dir for the wiki
            os.mkdir(wikiDir)

            allIsWell = True

            dataDir = join(wikiDir, "data")
            dataDir = mbcsDec(abspath(dataDir), "replace")[0]

            # create the data directory for the data files
            try:
                WikiDataManager.createWikiDb(self, wdhName, wikiName, dataDir,
                        False)
  #               createWikiDbFunc(wikiName, dataDir, False)
            except WikiDBExistsException:
                # The DB exists, should it be overwritten
                dlg=wx.MessageDialog(self, u'A wiki database already exists '+
                        u'in this location, overwrite?',
                        u'Wiki DB Exists', wx.YES_NO)
                result = dlg.ShowModal()
                if result == wx.ID_YES:
  #                   createWikiDbFunc(wikiName, dataDir, True)
                    WikiDataManager.createWikiDb(self, wdhName, wikiName, dataDir,
                        True)
                else:
                    allIsWell = False

                dlg.Destroy()
            except Exception, e:
                self.displayErrorMessage('There was an error creating the wiki database.', e)
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
                    wikiConfig.set("wiki_db", "data_dir", "data")
                    wikiConfig.save()

                    self.closeWiki()
                    
                    # open the new wiki
                    self.openWiki(configFileLoc)
                    p = self.wikiDataManager.createWikiPage(u"WikiSettings")
                    text = u"""++ Wiki Settings


These are your default global settings.

[global.importance.low.color: grey]
[global.importance.high.bold: true]
[global.contact.icon: contact]
[global.todo.bold: true]
[global.todo.icon: pin]
[global.wrap: 70]

[icon: cog]
"""
                    p.save(text, False)
                    p.update(text, False)
    
                    p = self.wikiDataManager.createWikiPage(u"ScratchPad")
                    text = u"++ Scratch Pad\n\n"
                    p.save(text, False)
                    p.update(text, False)
                    
                    self.getActiveEditor().GotoPos(self.getActiveEditor().GetLength())
                    self.getActiveEditor().AddText(u"\n\n\t* WikiSettings\n")
                    self.saveAllDocPages(force=True)
                    
                    # trigger hook
                    self.hooks.createdWiki(self, wikiName, wikiDir)
    
                    # reopen the root
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
        index = wx.GetSingleChoiceIndex(u"Choose database type",
                u"Choose database type", [wdh[1] for wdh in wdhandlers],
                self)
        if index == -1:
            return None
            
        return wdhandlers[index][0]



    def openWiki(self, wikiCombinedFilename, wikiWordToOpen=None,
            ignoreWdhName=False):
        """
        opens up a wiki
        ignoreWdhName -- Should the name of the wiki data handler in the
                wiki config file (if any) be ignored?
        """
        
        # Save the state of the currently open wiki, if there was one open
        # if the new config is the same as the old, don't resave state since
        # this could be a wiki overwrite from newWiki. We don't want to overwrite
        # the new config with the old one.

        wikiCombinedFilename = abspath(wikiCombinedFilename)

        # make sure the config exists
        cfgPath, splittedWikiWord = WikiDataManager.splitConfigPathAndWord(
                wikiCombinedFilename)
                
        if cfgPath is None:
            return False

#        if self.wikiConfigFilename != wikiConfigFilename:
        self.closeWiki()

        # trigger hooks
        self.hooks.openWiki(self, wikiCombinedFilename)

#         self.buildMainMenu()   # ???

        if ignoreWdhName:
            # Explicitly ask for wiki data handler
            dbtype = self._askForDbType()
            if dbtype is None:
                return
        else:
            # Try to get handler name from wiki config file
            dbtype = None
#                     

        while True:
            try:
                wikiDataManager = WikiDataManager.openWikiDocument(
                        cfgPath, self.wikiSyntax, dbtype)
                frmcode, frmtext = wikiDataManager.checkDatabaseFormat()
                if frmcode == 2:
                    # Unreadable db format
                    self.displayErrorMessage("Error connecting to database in '%s'"
                        % cfgPath, frmtext)
                    return False
                elif frmcode == 1:
                    # Update needed -> ask
                    answer = wx.MessageBox(u"The wiki needs an update to work "
                            u"with this version of WikidPad. Older versions of "
                            u"WikidPad may be unable to read the wiki after "
                            u"an update.", u'Update database?',
                            wx.OK | wx.CANCEL | wx.ICON_QUESTION, self)
                    if answer == wx.CANCEL:
                        return False

                wikiDataManager.connect()
                break
            except (UnknownDbHandlerException, DbHandlerNotAvailableException), e:
                # Could not get handler name from wiki config file
                # (probably old database) or required handler not available,
                # so ask user
                self.displayErrorMessage(str(e))
                dbtype = self._askForDbType()
                if dbtype is None:
                    return False
                    
                continue # Try again
            except (IOError, OSError, DbReadAccessError,
                    BadConfigurationFileException), e:
                # Something else went wrong
                self.displayErrorMessage("Error connecting to database in '%s'"
                        % cfgPath, e)
                if not isinstance(e, DbReadAccessError):
                    traceback.print_exc()
#                 self.lostAccess(e)
                return False
            except DbWriteAccessError, e:
                self.displayErrorMessage("Can't write to database '%s'"
                        % cfgPath, e)
                break


        # OK, things look good

        # set the member variables.

        self.wikiDataManager = wikiDataManager
        self.wikiDataManager.getMiscEvent().addListener(self)
        self.wikiData = wikiDataManager.getWikiData()

        self.wikiName = self.wikiDataManager.getWikiName()
        self.dataDir = self.wikiDataManager.getDataDir()
        
        self.getConfig().setWikiConfig(self.wikiDataManager.getWikiConfig())

        try:
            # what was the last wiki word opened
            lastWikiWord = wikiWordToOpen
            if not lastWikiWord:
                lastWikiWord = splittedWikiWord
            if not lastWikiWord:
                lastWikiWord = self.configuration.get("main", "first_wiki_word", u"")
                if lastWikiWord == u"":
                    lastWikiWord = self.configuration.get("main", "last_wiki_word")
    
            # reset the gui
            self.resetGui()
            self.buildMainMenu()
    
            # enable the top level menus
            if self.mainmenu:
                self.mainmenu.EnableTop(1, 1)
                self.mainmenu.EnableTop(2, 1)
                self.mainmenu.EnableTop(3, 1)
                
            self.fireMiscEventKeys(("opened wiki",))
    
            # open the root
            self.openWikiPage(self.wikiName)
            self.setCurrentWordAsRoot()
            
            viewsTree = self.windowLayouter.getWindowForName("viewstree")
            if viewsTree is not None:
                viewsTree.setViewsAsRoot()
    
    
            # set status
    #         self.statusBar.SetStatusText(
    #                 uniToGui(u"Opened wiki '%s'" % self.wikiName), 0)
    
            # now try and open the last wiki page
            if lastWikiWord and lastWikiWord != self.wikiName:
                # if the word is not a wiki word see if a word that starts with the word can be found
                if not self.getWikiData().isDefinedWikiWord(lastWikiWord):
                    wordsStartingWith = self.getWikiData().getWikiWordsStartingWith(
                            lastWikiWord, True)
                    if wordsStartingWith:
                        lastWikiWord = wordsStartingWith[0]
                self.openWikiPage(lastWikiWord)
                self.findCurrentWordInTree()
    
            self.tree.SetScrollPos(wx.HORIZONTAL, 0)
    
            # enable the editor control whether or not the wiki root was found
            for e in self.editors: e.Enable(1)
    
            # update the last accessed wiki config var
            self.lastAccessedWiki(self.getWikiConfigPath())
    
            # Rebuild text blocks menu
            self.rereadTextBlocks()
    
            # trigger hook
            self.hooks.openedWiki(self, self.wikiName, wikiCombinedFilename)
    
            # return that the wiki was opened successfully
            return True
        except (IOError, OSError, DbAccessError), e:
            self.lostAccess(e)
            return False


    def setCurrentWordAsRoot(self):
        """
        Set current wiki word as root of the tree
        """
        # make sure the root has a relationship to the ScratchPad
        # self.currentWikiPage.addChildRelationship("ScratchPad")
        if not self.requireReadAccess():
            return
        try:
            if self.getCurrentWikiWord() is not None:
                self.tree.setRootByWord(self.getCurrentWikiWord())
        except (IOError, OSError, DbAccessError), e:
            self.lostAccess(e)
            raise


    def closeWiki(self, saveState=True):
        def errCloseAnywayMsg():
            return wx.MessageBox(u"There is no (write-)access to underlying wiki\n"
                    "Close anyway and loose possible changes?",
                    u'Close anyway',
                    wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION, self)


        if self.getWikiConfigPath():
            wd = self.getWikiDocument()
            # Do not require access here, otherwise the user will not be able to
            # close a disconnected wiki
            if not wd.getReadAccessFailed() and not wd.getWriteAccessFailed():
                try:
                    self.fireMiscEventKeys(("closing current wiki",))
        #             for editor in self.editors:
        #                 editor.unloadCurrentDocPage()
                    if self.getWikiData() and saveState:
                        self.saveCurrentWikiState()
                except (IOError, OSError, DbAccessError), e:
                    self.lostAccess(e)
                    if errCloseAnywayMsg() == wx.NO:
                        raise
                    else:
                        traceback.print_exc()
                        self.fireMiscEventKeys(("dropping current wiki",))

                try:
                    if self.getWikiData():
                        wd.release()
                except (IOError, OSError, DbAccessError), e:
                    pass                
#                 self.getWikiData().close()
                self.wikiData = None
                if self.wikiDataManager is not None:
                    self.wikiDataManager.getMiscEvent().removeListener(self)
                self.wikiDataManager = None
            else:
                # We had already a problem, so ask what to do
                if errCloseAnywayMsg() == wx.NO:
                    raise LossyWikiCloseDeniedException
                
                self.fireMiscEventKeys(("dropping current wiki",))
                # else go ahead

            self.getConfig().setWikiConfig(None)
            if self.win32Interceptor is not None:
                self.win32Interceptor.stop()

            self.setShowOnTray()
            self.fireMiscEventKeys(("closed current wiki",))


    def saveCurrentWikiState(self):
        try:
            # write out the current config
            self.writeCurrentConfig()
    
            # save the current wiki page if it is dirty
            if self.getCurrentDocPage():
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
            wx.MessageBox(u"This operation requires an open database",
                    u'No open database', wx.OK, self)
            return False

        if not wd.getReadAccessFailed():
            return True

        while True:
            wd = self.getWikiDocument()
            if wd is None:
                return False

            self.SetFocus()
            result = wx.MessageBox(u"No connection to database. "
                    u"Try to reconnect?", u'Reconnect database?',
                    wx.YES_NO | wx.YES_DEFAULT | wx.ICON_QUESTION, self)

            if result == wx.NO:
                return False

            self.statusBar.PushStatusText(
                    "Trying to reconnect database...", 0)
            try:
                try:
                    wd.reconnect()
                    wd.setNoAutoSaveFlag(False)
                    wd.setReadAccessFailed(False)
                    self.requireWriteAccess()  # Just to test it  # TODO ?
                    return True  # Success
                except DbReadAccessError, e:
                    sys.stderr.write("Error while trying to reconnect:\n")
                    traceback.print_exc()
                    self.SetFocus()
                    self.displayErrorMessage('Error while reconnecting '
                            'database', e)
            finally:
                self.statusBar.PopStatusText(0)


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
            result = wx.MessageBox(u"This operation needs write access to database\n"
                    u"Try to write?", u'Try writing?',
                    wx.YES_NO | wx.YES_DEFAULT | wx.ICON_QUESTION, self)

            if result == wx.NO:
                return False

            self.statusBar.PushStatusText(
                    "Trying to write to database...", 0)
            try:
                try:
                    # write out the current configuration
                    self.writeCurrentConfig()
                    self.getWikiData().testWrite()

                    wd.setNoAutoSaveFlag(False)
                    wd.setWriteAccessFailed(False)
                    return True  # Success
                except (IOError, OSError, DbWriteAccessError), e:
                    sys.stderr.write("Error while trying to write:\n")
                    traceback.print_exc()
                    self.SetFocus()
                    self.displayErrorMessage('Error while writing to '
                            'database', e)
            finally:
                self.statusBar.PopStatusText(0)


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
        wx.MessageBox((u"Database connection error: %s.\n"
                u"Try to re-establish, then run \"Wiki\"->\"Reconnect\"") % str(exc),
                u'Connection lost', wx.OK, self)

#         wd.setWriteAccessFailed(True) ?
        self.getWikiDocument().setReadAccessFailed(True)


    def lostWriteAccess(self, exc):
        """
        Called if read access was lost during an operation
        """
        if self.getWikiDocument().getWriteAccessFailed():
            # Was already handled -> ignore
            return

        self.SetFocus()
        wx.MessageBox((u"No write access to database: %s.\n"
                u" Try to re-establish, then run \"Wiki\"->\"Reconnect\"") % str(exc),
                u'Connection lost', wx.OK, self)

        self.getWikiDocument().setWriteAccessFailed(True)


#     def checkDatabaseConnected(self):   # TODO: Make obsolete 
#         """
#         Check if database is connected (and return True),
#         show message window if not.
#         Returns true if database is connected after executing function.
#         """
#         if self.getWikiData() is not None:
#             return True
# 
#         while True:
#             wd = self.getWikiDocument()
#             if wd is None:
#                 return False
# 
#             result = wxMessageBox(u"No connection to database. "
#                     u"Try to reconnect?", u'Reconnect database?',
#                     wxYES_NO | wxYES_DEFAULT | wxICON_QUESTION, self)
# 
#             if result == wxNO:
#                 return False
# 
#             self.statusBar.PushStatusText(
#                     "Trying to reconnect database...", 0)
#             try:
#                 try:
#                     wd.reconnect()
#                     wd.setNoAutoSaveFlag(False)
#                     return True  # Success
#                 except (IOError, OSError), e:
#                     sys.stderr.write("Error while trying to reconnect:\n")
#                     traceback.print_exc()
#                     self.displayErrorMessage('Error while reconnecting '
#                             'database', e)
# 
#             finally:
#                 self.statusBar.PopStatusText(0)



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
            
        self.statusBar.PushStatusText("Trying to reconnect ...", 0)

        try:
            try:
                wd.setNoAutoSaveFlag(True)
                wd.reconnect()
                wd.setNoAutoSaveFlag(False)
                return True
            except:
                sys.stderr.write("Error while trying to reconnect:\n")
                traceback.print_exc()
        finally:
            self.statusBar.PopStatusText(0)
            
        return False



    def openFuncPage(self, funcTag, **evtprops):
        if not self.requireReadAccess():
            return

        try:
            page = self.wikiDataManager.getFuncPage(funcTag)
    
            self.getActiveEditor().loadFuncPage(page, evtprops)
        except (IOError, OSError, DbAccessError), e:
            self.lostAccess(e)
            raise

        p2 = evtprops.copy()
        p2.update({"loaded current functional page": True})
        # p2.update({"loaded current page": True})
        self.fireMiscEventProps(p2)        


    def openWikiPage(self, wikiWord, addToHistory=True,
            forceTreeSyncFromRoot=False, forceReopen=False, **evtprops):
        """
        Opens a wiki page in the active editor.
        """
        if not self.requireReadAccess():
            return

        evtprops["addToHistory"] = addToHistory
        evtprops["forceTreeSyncFromRoot"] = forceTreeSyncFromRoot

#         self.statusBar.SetStatusText(uniToGui(u"Opening wiki word '%s'" %
#                 wikiWord), 0)

        # make sure this is a valid wiki word
        if not self.getFormatting().isNakedWikiWord(wikiWord):
            self.displayErrorMessage(u"'%s' is an invalid wiki word." % wikiWord)
            return

        try:
            # don't reopen the currently open page, only send an event
            if (wikiWord == self.getCurrentWikiWord()) and not forceReopen:
                p2 = evtprops.copy()
                p2.update({"reloaded current page": True,
                        "reloaded current wiki page": True})
                self.fireMiscEventProps(p2)
    #             # self.tree.buildTreeForWord(self.currentWikiWord)  # TODO Needed?
    #             self.statusBar.SetStatusText(uniToGui(u"Wiki word '%s' already open" %
    #                     wikiWord), 0)
                return
    
            # trigger hook
            self.hooks.openWikiWord(self, wikiWord)
    
            # check if this is an alias
            if (self.getWikiData().isAlias(wikiWord)):
                wikiWord = self.getWikiData().getAliasesWikiWord(wikiWord)
    
            # fetch the page info from the database
            try:
                page = self.wikiDataManager.getWikiPage(wikiWord)
                self.statusBar.SetStatusText(uniToGui(u"Opened wiki word '%s'" %
                        wikiWord), 0)
                        
                self.refreshPageStatus(page)
    
            except (WikiWordNotFoundException, WikiFileNotFoundException), e:
                page = self.wikiDataManager.createWikiPage(wikiWord)
                # trigger hooks
                self.hooks.newWikiWord(self, wikiWord)
                self.statusBar.SetStatusText(uniToGui(u"Wiki page not found, a new "
                        u"page will be created"), 0)
                self.statusBar.SetStatusText(uniToGui(u""), 1)
    
            self.getActiveEditor().loadWikiPage(page, evtprops)
    
            p2 = evtprops.copy()
            p2.update({"loaded current page": True,
                    "loaded current wiki page": True})
            self.fireMiscEventProps(p2)
    
            # set the title and add the word to the history
            self.SetTitle(uniToGui(u"Wiki: %s - %s" %
                    (self.getWikiConfigPath(), self.getCurrentWikiWord())))
    
            self.configuration.set("main", "last_wiki_word", wikiWord)
    
            # sync the tree
            if forceTreeSyncFromRoot:
                self.findCurrentWordInTree()
        except (IOError, OSError, DbAccessError), e:
            self.lostAccess(e)
            raise

        # trigger hook
        self.hooks.openedWikiWord(self, wikiWord)


    # TODO 
    def saveCurrentDocPage(self, force = False):
        ## _prof.start()

        if (force or self.getCurrentDocPage().getDirty()[0]) and \
                self.requireWriteAccess():
            # Reset error flag here, it can be set true again by saveDocPage
#             self.getWikiDocument().setNoAutoSaveFlag(False)
            try:
                self.getActiveEditor().saveLoadedDocPage() # this calls in turn saveDocPage() below
            except (IOError, OSError, DbAccessError), e:
                self.lostAccess(e)
                raise

        self.refreshPageStatus()
        
        ## _prof.stop()

    def saveAllDocPages(self, force = False):
        if not self.requireWriteAccess():
            return

 #        self.getWikiDocument().setNoAutoSaveFlag(False)
        try:
            self.fireMiscEventProps({"saving all pages": None, "force": force})
            self.refreshPageStatus()
        except (IOError, OSError, DbAccessError), e:
            self.lostAccess(e)
            raise

#         self.saveCurrentDocPage(force)


#             self.GetToolBar().FindById(GUI_ID.CMD_SAVE_WIKI).Enable(False)

#             rect = self.statusBar.GetFieldRect(0)
# 
#             dc = wxWindowDC(self.statusBar)
#             try:
#                 dc.SetBrush(wxRED_BRUSH)
#                 dc.SetPen(wxRED_PEN)
#                 dc.DrawRectangle(rect.x, rect.y, rect.width, rect.height)
#                 dc.SetPen(wxWHITE_PEN)
#                 dc.SetFont(self.statusBar.GetFont())
#                 dc.DrawText(u"Saving page", rect.x + 2, rect.y + 2)
#                 self.activeEditor.saveLoadedDocPage()
#                 dc.SetFont(wxNullFont)
#                 dc.SetBrush(wxNullBrush)
#                 dc.SetPen(wxNullPen)
#             finally:
#                 del dc
# 
#             
#             self.statusBar.Refresh()



    def saveDocPage(self, page, text, pageAst):
        """
        Save page unconditionally
        """
        if page is None:
            return False

        if not self.requireWriteAccess():
            return

        self.statusBar.PushStatusText(u"Saving page", 0)
        try:
            word = page.getWikiWord()
            if word is not None:
                # trigger hooks
                self.hooks.savingWikiWord(self, word)

            reconnectTried = False  # Flag if reconnect was already tried after an error
            while True:
                try:
                    if word is not None:
                        # only for real wiki pages
                        page.save(self.getActiveEditor().cleanAutoGenAreas(text))
                        page.update(self.getActiveEditor().updateAutoGenAreas(text))   # ?
                        if pageAst is not None:
                            self.propertyChecker.checkPage(page, pageAst)

                        # trigger hooks
                        self.hooks.savedWikiWord(self, word)
                    else:
                        # for functional pages
                        page.save(text)
                        page.update(text)

                    self.getWikiData().commit()
                    return True
                except (IOError, OSError, DbAccessError), e:
                    self.lostAccess(e)
                    raise

#                 except (IOError, OSError), e:
#                     traceback.print_exc()
#                     if self.tryAutoReconnect():
#                         continue
# 
#                     if word is None:    # TODO !!!
#                         word = u"---"
#                     dlg = wxMessageDialog(self,
#                             uniToGui((u'There was an error saving the contents of '
#                             u'wiki page "%s".\n%s\n\nWould you like to try and '
#                             u'save this document again?') % (word, e)),
#                                         u'Error Saving!', wxYES_NO)
#                     result = dlg.ShowModal()
#                     dlg.Destroy()
#                     if result == wxID_NO:
#                         self.getWikiDocument().setNoAutoSaveFlag(True)
#                         return False
        finally:
            self.statusBar.PopStatusText(0)


    def deleteCurrentWikiPage(self):
        if self.getCurrentWikiWord() and self.requireWriteAccess():
            try:
                # self.saveCurrentDocPage()
                if self.getWikiData().isDefinedWikiWord(self.getCurrentWikiWord()):
                    page = self.getCurrentDocPage()
                    page.deletePage()
            except (IOError, OSError, DbAccessError), e:
                self.lostAccess(e)
                raise

#                 self.getWikiData().deleteWord(self.getCurrentWikiWord())
#                 # trigger hooks
#                 self.hooks.deletedWikiWord(self, self.getCurrentWikiWord())

#             self.pageHistory.goAfterDeletion()


    def renameCurrentWikiPage(self, toWikiWord, modifyText, **evtprops):
        """
        Renames current wiki word to toWikiWord.
        Returns True if renaming was done successful.
        
        modifyText -- Should the text of links to the renamed page be
                modified? This text replacement works unreliably
        """
        wikiWord = self.getCurrentWikiWord()
        if wikiWord is None or not self.requireWriteAccess():
            return False

        try:
            self.saveAllDocPages()

            if wikiWord == self.getWikiDocument().getWikiName():
                # Renaming of root word = renaming of wiki config file
                wikiConfigFilename = self.getWikiDocument().getWikiConfigPath()
                self.wikiHistory.remove(wikiConfigFilename)
                self.getWikiDocument().renameWikiWord(wikiWord, toWikiWord,
                        modifyText)
                # Store some additional information
                self.lastAccessedWiki(
                        self.getWikiDocument().getWikiConfigPath())

            else:
                self.getWikiDocument().renameWikiWord(wikiWord, toWikiWord,
                        modifyText)

            return True
        except (IOError, OSError, DbAccessError), e:
            self.lostAccess(e)
            raise
        except WikiDataException, e:
            traceback.print_exc()                
            self.displayErrorMessage(str(e))
            return False


    def findCurrentWordInTree(self):
        try:
            self.tree.buildTreeForWord(self.getCurrentWikiWord(), selectNode=True)
        except Exception, e:
            sys.stderr.write("%s\n" % e)


    def makeRelUrlAbsolute(self, relurl):
        """
        Return the absolute path for a rel: URL
        """
        relpath = urllib.url2pathname(relurl[6:])

        return u"file:" + urllib.pathname2url(
                abspath(join(dirname(self.getWikiConfigPath()), relpath)))

    def launchUrl(self, link):
#         match = self.getFormatting().UrlRE.match(link)
#         try:
#             link2 = match.group(1)

        link2 = link
        if self.configuration.getint(
                "main", "new_window_on_follow_wiki_url") == 1 or \
                not link2.startswith(u"wiki:"):
            if link2.startswith(u"rel://"):
                # This is a relative link
                link2 = self.makeRelUrlAbsolute(link2)
            try:
#                 if Configuration.isWindows():
                OsAbstract.startFile(link2)
#                 else:
#                     # Better solution?
#                     wx.LaunchDefaultBrowser(link2)    # TODO
            except Exception, e:
                traceback.print_exc()
                self.displayErrorMessage(u"Couldn't start file", e)
                return False

            return True
        elif self.configuration.getint(
                "main", "new_window_on_follow_wiki_url") == 0:
                    
            link2 = urllib.url2pathname(link2)
            link2 = link2.replace("wiki:", "")
            if exists(pathEnc(link2)):
                self.openWiki(link2, "")  # ?
                return True
            else:
                self.statusBar.SetStatusText(
                        uniToGui(u"Couldn't open wiki: %s" % link2), 0)
                return False
#         except:
#             pass
        return False


    def refreshPageStatus(self, page = None):
        """
        Read information from page and present it in the field 1 of the
        status bar.
        """
        fmt = mbcsEnc(self.getConfig().get("main", "pagestatus_timeformat"),
                "replace")[0]

        if page is None:
            page = self.getCurrentDocPage()

        if page is None or not isinstance(page,
                (DocPages.WikiPage, DocPages.AliasWikiPage)):
            self.statusBar.SetStatusText(uniToGui(u""), 1)
            return
            
        pageStatus = u""   # wikiWord

        modTime, creaTime = page.getTimestamps()
        if modTime is not None:
            pageStatus += u"Mod.: %s" % \
                    mbcsDec(strftime(fmt, localtime(modTime)), "replace")[0]
            pageStatus += u"; Crea.: %s" % \
                    mbcsDec(strftime(fmt, localtime(creaTime)), "replace")[0]

        self.statusBar.SetStatusText(uniToGui(pageStatus), 1)


    def viewWordSelection(self, title, words, motionType):
        """
        View a single choice to select a word to go to
        title -- Title of the dialog
        words -- Sequence of the words to choose from
        motionType -- motion type to set in openWikiPage if word was choosen
        """
        if not self.requireReadAccess():
            return
        try:
            dlg = ChooseWikiWordDialog(self, -1, words, motionType, title)
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
        self.viewWordSelection(u"Parent nodes of '%s'" % ofWord, parents,
                "parent")


    def viewParentLess(self):
        if not self.requireReadAccess():
            return
        try:
            parentLess = self.getWikiData().getParentlessWikiWords()
        except (IOError, OSError, DbAccessError), e:
            self.lostAccess(e)
            raise
        self.viewWordSelection(u"Parentless nodes", parentLess,
                "random")


    def viewChildren(self, ofWord):
        if not self.requireReadAccess():
            return
        try:
            children = self.getWikiData().getChildRelationships(ofWord)
        except (IOError, OSError, DbAccessError), e:
            self.lostAccess(e)
            raise
        self.viewWordSelection(u"Child nodes of '%s'" % ofWord, children,
                "child")

    def viewBookmarks(self):
        if not self.requireReadAccess():
            return
        try:
            bookmarked = self.getWikiData().getWordsWithPropertyValue(
                    "bookmarked", u"true")
        except (IOError, OSError, DbAccessError), e:
            self.lostAccess(e)
            raise
        self.viewWordSelection(u"Bookmarks", bookmarked,
                "random")


    def viewHistory(self, posDelta=0):
        if not self.requireReadAccess():
            return
        try:
            hist = self.pageHistory.getHistory()
            histpos = self.pageHistory.getPosition()
        except (IOError, OSError, DbAccessError), e:
            self.lostAccess(e)
            raise

        historyLen = len(hist)
        dlg = wx.SingleChoiceDialog(self,
                                   u"History",
                                   u"History",
                                   hist,
                                   wx.CHOICEDLG_STYLE|wx.OK|wx.CANCEL)
        
        if historyLen > 0:
            position = histpos + posDelta - 1
            if (position < 0):
                position = 0
            elif (position >= historyLen):
                position = historyLen-1
    
            dlg.SetSelection(position)

        if dlg.ShowModal() == wx.ID_OK and dlg.GetSelection() > -1:
            self.pageHistory.goInHistory(dlg.GetSelection() - (histpos - 1))

        dlg.Destroy()


    def lastAccessedWiki(self, wikiConfigFilename):
        """
        Writes to the global config the location of the last accessed wiki
        and updates file history.
        """
        # create a new config file for the new wiki
        self.configuration.set("main", "last_wiki", wikiConfigFilename)
        if wikiConfigFilename not in self.wikiHistory:
            self.wikiHistory.append(wikiConfigFilename)

            # only keep 5 items
            if len(self.wikiHistory) > 5:
                self.wikiHistory.pop(0)

            # add the item to the menu
            menuID = wx.NewId()
            self.recentWikisMenu.Append(menuID, wikiConfigFilename)
            wx.EVT_MENU(self, menuID, self.OnSelectRecentWiki)

        self.configuration.set("main", "last_active_dir", dirname(wikiConfigFilename))
        self.writeGlobalConfig()


    # Only needed for scripts
    def setAutoSave(self, onOrOff):
        self.autoSave = onOrOff
        self.configuration.set("main", "auto_save", self.autoSave)


    def setShowTreeControl(self, onOrOff):
        if onOrOff:
            self.windowLayouter.uncollapseWindow("maintree")
        else:
            self.windowLayouter.collapseWindow("maintree")


    def setShowToolbar(self, onOrOff):
        """
        Control, if toolbar should be shown or not
        """
        self.getConfig().set("main", "toolbar_show", bool(onOrOff))

        if bool(onOrOff) == (not self.GetToolBar() is None):
            # Desired state already reached
            return

        if onOrOff:
            self.buildToolbar()
        else:
            self.GetToolBar().Destroy()
            self.SetToolBar(None)

    def getStayOnTop(self):
        """
        Returns if this window is set to stay on top of all others
        """
        return not not self.GetWindowStyleFlag() & wx.STAY_ON_TOP 

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

#         if self.showOnTrayMenuItem:
#             self.showOnTrayMenuItem.Check(self.showOnTray)   # TODO infinite loop?

        if onOrOff:
            if self.tbIcon is None:
                self.tbIcon = TaskBarIcon(self)

            tooltip = None
            if self.getWikiConfigPath():  # If a wiki is open
                tooltip = u"Wiki: %s" % self.getWikiConfigPath()  # self.wikiName
            else:
                tooltip = u"Wikidpad"

            self.tbIcon.SetIcon(wx.Icon(os.path.join(self.wikiAppDir, 'icons', 'pwiki.ico'),
                    wx.BITMAP_TYPE_ICO), uniToGui(tooltip))
        else:
            if self.tbIcon is not None:
                if self.tbIcon.IsIconInstalled():
                    self.tbIcon.RemoveIcon()

                self.tbIcon.Destroy()
                sleep(0.01)            
                self.tbIcon = None


    def setHideUndefined(self, onOrOff=None):
        """
        Set if undefined WikiWords should be hidden in the tree
        """

        if not onOrOff is None:
            self.configuration.set("main", "hideundefined", onOrOff)
        else:
            onOrOff = self.configuration.getboolean("main", "hideundefined")


    _LAYOUT_WITHOUT_VIEWSTREE = "name:main area panel;"\
        "layout relation:%s&layout relative to:main area panel&name:maintree&"\
            "layout sash position:170&layout sash effective position:170;"\
        "layout relation:below&layout relative to:main area panel&name:log&"\
            "layout sash position:1&layout sash effective position:120"

    _LAYOUT_WITH_VIEWSTREE = "name:main area panel;"\
            "layout relation:%s&layout relative to:main area panel&name:maintree&"\
                "layout sash position:170&layout sash effective position:170;"\
            "layout relation:%s&layout relative to:maintree&name:viewstree;"\
            "layout relation:below&layout relative to:main area panel&name:log&"\
                "layout sash position:1&layout sash effective position:120"

    def changeLayoutByCf(self, layoutCfStr):
        """
        Create a new window layouter according to the
        layout configuration string layoutCfStr. Try to reuse and reparent
        existing windows.
        BUG: Reparenting seems to disturb event handling for tree events and
            isn't available for all OS'
        """
        # Reparent reusable windows so they aren't destroyed when
        #   cleaning main window
        # TODO Reparent not available for all OS'
        cachedWindows = {}
        for n, w in self.windowLayouter.winNameToObject.iteritems():
            cachedWindows[n] = w
#             w.Reparent(None)
            w.Reparent(self)

        self.windowLayouter.cleanMainWindow(cachedWindows.values())

        # make own creator function which provides already existing windows
        def cachedCreateWindow(winProps, parent):
            """
            Wrapper around _actualCreateWindow to maintain a cache
            of already existing windows
            """
            winName = winProps["name"]

            # Try in cache:
            window = cachedWindows.get(winName)
            if window is not None:
                window.Reparent(parent)    # TODO Reparent not available for all OS'
                del cachedWindows[winName]
                return window

            window = self.createWindow(winProps, parent)
#             if window is not None:
#                 cachedWindows[winName] = window

            return window
        
        self.windowLayouter = WindowLayouter(self, cachedCreateWindow)

#         for pr in self._TEST_LAYOUT_DEFINITION:
#             self.windowLayouter.addWindowProps(pr)

        self.windowLayouter.setWinPropsByConfig(layoutCfStr)
        # Handle no size events while realizing layout
        self.Unbind(wx.EVT_SIZE)
        
        self.windowLayouter.realize()

        # Destroy windows which weren't reused
        for n, w in cachedWindows.iteritems():
#             if w.GetParent() is None:
            w.Destroy()

        self.windowLayouter.layout()

        wx.EVT_SIZE(self, self.OnSize)

        self.tree = self.windowLayouter.getWindowForName("maintree")
        self.logWindow = self.windowLayouter.getWindowForName("log")


#     def getClipboardCatcher(self):
#         return self.clipboardCatcher is not None and \
#                 self.clipboardCatcher.isActive()

    def OnClipboardCatcherOff(self, evt):
        self.win32Interceptor.stop()

    def OnClipboardCatcherAtPage(self, evt):
        self.win32Interceptor.startAtPage(self.GetHandle(),
                self.getCurrentDocPage())

    def OnClipboardCatcherAtCursor(self, evt):
        self.win32Interceptor.startAtCursor(self.GetHandle())


    def OnUpdateClipboardCatcher(self, evt):
        cc = self.win32Interceptor
        if cc is None:
            return  # Shouldn't be called anyway

        if evt.GetId() == GUI_ID.CMD_CLIPBOARD_CATCHER_OFF:
            evt.Check(cc.getMode() == cc.MODE_OFF)
        elif evt.GetId() == GUI_ID.CMD_CLIPBOARD_CATCHER_AT_CURSOR:
            evt.Check(cc.getMode() == cc.MODE_AT_CURSOR)
        elif evt.GetId() == GUI_ID.CMD_CLIPBOARD_CATCHER_AT_PAGE:
            if cc.getMode() == cc.MODE_AT_PAGE:
                evt.Check(True)
                evt.SetText("Clipboard Catcher at: %s\t%s" % 
                        (self.win32Interceptor.getWikiWord(),
                        self.keyBindings.CatchClipboardAtPage))
            else:
                evt.Check(False)
                evt.SetText("Clipboard Catcher at Page\t" +
                        self.keyBindings.CatchClipboardAtPage)

    def writeGlobalConfig(self):
        "writes out the global config file"
        try:
            self.configuration.save()
        except (IOError, OSError, DbAccessError), e:
            self.lostAccess(e)
            raise
        except Exception, e:
            self.displayErrorMessage("Error saving global configuration", e)


    def writeCurrentConfig(self):
        "writes out the current config file"
        try:
            self.configuration.save()
        except (IOError, OSError, DbAccessError), e:
            self.lostAccess(e)
            raise
        except Exception, e:
            self.displayErrorMessage("Error saving current configuration", e)


    def showWikiWordOpenDialog(self):
        dlg = OpenWikiWordDialog(self, -1)
        try:
            dlg.CenterOnParent(wx.BOTH)
            if dlg.ShowModal() == wx.ID_OK:
                wikiWord = dlg.GetValue()
                if wikiWord:
                    self.openWikiPage(wikiWord, forceTreeSyncFromRoot=True)
                    self.getActiveEditor().SetFocus()
        finally:
            dlg.Destroy()


    def showWikiWordRenameDialog(self, wikiWord=None, toWikiWord=None):
        if self.getCurrentWikiWord() is None:
            self.displayErrorMessage(u"No real wiki word selected to rename")
            return

        dlg = wx.TextEntryDialog(self, uniToGui(u"Rename '%s' to:" %
                self.getCurrentWikiWord()), u"Rename Wiki Word",
                self.getCurrentWikiWord(), wx.OK | wx.CANCEL)

        try:
            while dlg.ShowModal() == wx.ID_OK and \
                    not self.showWikiWordRenameConfirmDialog(
                            guiToUni(dlg.GetValue())):
                pass

        finally:
            dlg.Destroy()

    # TODO Unicode
    def showStoreVersionDialog(self):
        dlg = wx.TextEntryDialog (self, u"Description:",
                                 u"Store new version", u"",
                                 wx.OK | wx.CANCEL)

        description = None
        if dlg.ShowModal() == wx.ID_OK:
            description = dlg.GetValue()
        dlg.Destroy()

        if not description is None:
            self.saveAllDocPages()
            self.getWikiData().storeVersion(description)


    def showDeleteAllVersionsDialog(self):
        result = wx.MessageBox(u"Do you want to delete all stored versions?",
                u"Delete All Versions", wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION, self)

        if result == wx.YES:
            self.getWikiData().deleteVersioningData()


    def showSavedVersionsDialog(self):
        if not self.getWikiData().hasVersioningData():
            dlg=wx.MessageDialog(self, u"This wiki does not contain any version information",
                    u'Retrieve version', wx.OK)
            dlg.ShowModal()
            dlg.Destroy()
            return

        dlg = SavedVersionsDialog(self, -1)
        dlg.CenterOnParent(wx.BOTH)

        version = None
        if dlg.ShowModal() == wx.ID_OK:
            version = dlg.GetValue()
        dlg.Destroy()

        if version:
            dlg=wx.MessageDialog(self, u"This will overwrite current content if not stored as version. Continue?",
                    u'Retrieve version', wx.YES_NO)
            if dlg.ShowModal() == wx.ID_YES:
                dlg.Destroy()
                self.saveAllDocPages()
                word = self.getCurrentWikiWord()
                self.getWikiData().applyStoredVersion(version[0])
                self.rebuildWiki(skipConfirm=True)
                ## self.tree.collapse()
                self.openWikiPage(self.getCurrentWikiWord(), forceTreeSyncFromRoot=True, forceReopen=True)
                ## self.findCurrentWordInTree()
            else:
                dlg.Destroy()


    # TODO Check if new name already exists (?)
    def showWikiWordRenameConfirmDialog(self, toWikiWord):
        """
        Checks if renaming operation is valid, presents either an error
        message or a confirmation dialog.
        Returns -- True iff renaming was done successfully
        """
        wikiWord = self.getCurrentWikiWord()

        if not toWikiWord or len(toWikiWord) == 0:
            return False

        if not self.getFormatting().isNakedWikiWord(toWikiWord):
            self.displayErrorMessage(u"'%s' is an invalid wiki word" % toWikiWord)
            return False

        if wikiWord == toWikiWord:
            self.displayErrorMessage(u"Can't rename to itself")
            return False

        if wikiWord == "ScratchPad":
            self.displayErrorMessage(u"The scratch pad cannot be renamed.")
            return False

        try:
            if self.getWikiData().isDefinedWikiWord(toWikiWord):
                self.displayErrorMessage(u"Cannot rename to '%s', word already exists" %
                        toWikiWord)
                return False
                
            result = wx.MessageBox(u"Do you want to modify all links to the wiki word "
                    u"'%s' renamed to '%s'?" % (wikiWord, toWikiWord),
                    u'Rename Wiki Word',
                    wx.YES_NO | wx.CANCEL | wx.ICON_QUESTION, self)
    
            if result == wx.YES or result == wx.NO:
                try:
                    self.renameCurrentWikiPage(toWikiWord, result == wx.YES)
                    return True
                except WikiDataException, e:
                    traceback.print_exc()                
                    self.displayErrorMessage(str(e))
    
    #         dlg.Destroy()
            return False
        except (IOError, OSError, DbAccessError), e:
            self.lostAccess(e)
            raise


    def showSearchDialog(self):
        if self.findDlg != None:
            return

        self.findDlg = SearchWikiDialog(self, -1)
        self.findDlg.CenterOnParent(wx.BOTH)
        self.findDlg.Show()


    def showWikiWordDeleteDialog(self, wikiWord=None):
        if not wikiWord:
            wikiWord = self.getCurrentWikiWord()

        if wikiWord == u"ScratchPad":
            self.displayErrorMessage(u"The scratch pad cannot be deleted")
            return
            
        if wikiWord is None:
            self.displayErrorMessage(u"No real wiki word to delete")
            return

        dlg=wx.MessageDialog(self,
                uniToGui(u"Are you sure you want to delete wiki word '%s'?" % wikiWord),
                'Delete Wiki Word', wx.YES_NO | wx.NO_DEFAULT)
        result = dlg.ShowModal()
        if result == wx.ID_YES:
            try:
                self.saveAllDocPages()
                self.deleteCurrentWikiPage()
            except (IOError, OSError, DbAccessError), e:
                self.lostAccess(e)
                raise
            except WikiDataException, e:
                self.displayErrorMessage(str(e))

        dlg.Destroy()


    def showFindReplaceDialog(self):
        if self.findDlg != None:
            return

        self.findDlg = SearchPageDialog(self, -1)
        self.findDlg.CenterOnParent(wx.BOTH)
        self.findDlg.Show()


    def showReplaceTextByWikiwordDialog(self):
        if self.getCurrentWikiWord() is None:
            self.displayErrorMessage(u"No real wiki word to modify")
            return

        wikiWord = guiToUni(wx.GetTextFromUser(u"Replace text by WikiWord:",
                u"Replace by Wiki Word", self.getCurrentWikiWord(), self))

        if wikiWord:
            wikiWord = wikiWordToLabel(wikiWord)
            if not self.getFormatting().isNakedWikiWord(wikiWord):
                self.displayErrorMessage(u"'%s' is an invalid wiki word" % wikiWord)
                return False

            try:
                if self.getWikiData().isDefinedWikiWord(wikiWord):
                    self.displayErrorMessage(u"'%s' exists already" % wikiWord)
                            # TODO Allow retry or append/replace
                    return False
    
                text = self.getActiveEditor().GetSelectedText()
                page = self.wikiDataManager.createWikiPage(wikiWord)
                self.getActiveEditor().ReplaceSelection(
                        self.getFormatting().normalizeWikiWord(wikiWord))
                # TODO Respect template property?
                title = DocPages.WikiPage.getWikiPageTitle(wikiWord)
                self.saveDocPage(page, u"++ %s\n\n%s" % (title, text), None)
            except (IOError, OSError, DbAccessError), e:
                self.lostAccess(e)
                raise


    def showIconSelectDialog(self):
        dlg = IconSelectDialog(self, -1, wx.GetApp().getIconCache())
        dlg.CenterOnParent(wx.BOTH)
        iconname = None
        if dlg.ShowModal() == wx.ID_OK:
            iconname = dlg.GetValue()

        dlg.Destroy()

        if iconname:
            self.insertAttribute("icon", iconname)

    def showDateformatDialog(self):
        fmt = self.configuration.get("main", "strftime")

        dlg = DateformatDialog(self, -1, self, deffmt = fmt)
        dlg.CenterOnParent(wx.BOTH)
        dateformat = None

        if dlg.ShowModal() == wx.ID_OK:
            dateformat = dlg.GetValue()
        dlg.Destroy()

        if not dateformat is None:
            self.configuration.set("main", "strftime", dateformat)


    def showOptionsDialog(self):
        dlg = OptionsDialog(self, -1)
        dlg.CenterOnParent(wx.BOTH)

        result = dlg.ShowModal()
        dlg.Destroy()

        if result == wx.ID_OK:
            # Perform operations to reset GUI parts after option changes
            self.autoSaveDelayAfterKeyPressed = self.configuration.getint(
                    "main", "auto_save_delay_key_pressed")
            self.autoSaveDelayAfterDirty = self.configuration.getint(
                    "main", "auto_save_delay_dirty")
            self.setShowOnTray()
            self.setHideUndefined()
            self.refreshPageStatus()
            
            # TODO Move this to WikiDataManager!
            # Set file storage according to configuration
            fs = self.getWikiDataManager().getFileStorage()
            
            fs.setModDateMustMatch(self.configuration.getboolean("main",
                    "fileStorage_identity_modDateMustMatch", False))
            fs.setFilenameMustMatch(self.configuration.getboolean("main",
                    "fileStorage_identity_filenameMustMatch", False))
            fs.setModDateIsEnough(self.configuration.getboolean("main",
                    "fileStorage_identity_modDateIsEnough", False))

            newLayoutMainTreePosition = self.configuration.getint("main",
                "mainTree_position", 0)
            newLayoutViewsTreePosition = self.configuration.getint("main",
                "viewsTree_position", 0)
            if self.layoutViewsTreePosition != newLayoutViewsTreePosition or \
                self.layoutMainTreePosition != newLayoutMainTreePosition:
                self.layoutViewsTreePosition = newLayoutViewsTreePosition
                self.layoutMainTreePosition = newLayoutMainTreePosition
                
                mainPos = {0:"left", 1:"right", 2:"above", 3:"below"}\
                        [newLayoutMainTreePosition]

                if newLayoutViewsTreePosition == 0:
                    # Don't show "Views" tree
                    layoutCfStr = self._LAYOUT_WITHOUT_VIEWSTREE % mainPos
                else:
                    viewsPos = {1:"above", 2:"below", 3:"left", 4:"right"}\
                            [newLayoutViewsTreePosition]
                    layoutCfStr = self._LAYOUT_WITH_VIEWSTREE % \
                            (mainPos, viewsPos)
    
                self.configuration.set("main", "windowLayout", layoutCfStr)
                # Call of changeLayoutByCf() crashes on Linux/GTK so save
                # data beforehand
                self.saveCurrentWikiState()
                self.changeLayoutByCf(layoutCfStr)

            self.fireMiscEventKeys(("options changed",))


    def OnCmdExportDialog(self, evt):
        self.saveAllDocPages()
        self.getWikiData().commit()

        dlg = ExportDialog(self, -1)
        dlg.CenterOnParent(wx.BOTH)

        result = dlg.ShowModal()
        dlg.Destroy()


    EXPORT_PARAMS = {
            GUI_ID.MENU_EXPORT_WHOLE_AS_PAGE:
                    (Exporters.HtmlXmlExporter, u"html_single", None),
            GUI_ID.MENU_EXPORT_WHOLE_AS_PAGES:
                    (Exporters.HtmlXmlExporter, u"html_multi", None),
            GUI_ID.MENU_EXPORT_WORD_AS_PAGE:
                    (Exporters.HtmlXmlExporter, u"html_single", None),
            GUI_ID.MENU_EXPORT_SUB_AS_PAGE:
                    (Exporters.HtmlXmlExporter, u"html_single", None),
            GUI_ID.MENU_EXPORT_SUB_AS_PAGES:
                    (Exporters.HtmlXmlExporter, u"html_multi", None),
            GUI_ID.MENU_EXPORT_WHOLE_AS_XML:
                    (Exporters.HtmlXmlExporter, u"xml", None),
            GUI_ID.MENU_EXPORT_WHOLE_AS_RAW:
                    (Exporters.TextExporter, u"raw_files", (1,))
            }


    def OnExportWiki(self, evt):
        import SearchAndReplace as Sar
        
        typ = evt.GetId()
        
        if typ != GUI_ID.MENU_EXPORT_WHOLE_AS_XML:
            # Export to dir
            dest = wx.DirSelector(u"Select Export Directory", self.getLastActiveDir(),
            wx.DD_DEFAULT_STYLE|wx.DD_NEW_DIR_BUTTON, parent=self)
        else:
            # Export to file
            dest = wx.FileSelector(u"Select Export File",
                    self.getLastActiveDir(),
                    default_filename = "", default_extension = "",
                    wildcard = u"XML files (*.xml)|*.xml|All files (*.*)|*",
                    flags=wx.SAVE | wx.OVERWRITE_PROMPT, parent=self)
        
        try:
            if dest:
                if typ in (GUI_ID.MENU_EXPORT_WHOLE_AS_PAGE,
                        GUI_ID.MENU_EXPORT_WHOLE_AS_PAGES,
                        GUI_ID.MENU_EXPORT_WHOLE_AS_XML,
                        GUI_ID.MENU_EXPORT_WHOLE_AS_RAW):
                    # Export whole wiki
    
                    lpOp = Sar.ListWikiPagesOperation()
                    item = Sar.AllWikiPagesNode(lpOp)
                    lpOp.setSearchOpTree(item)
                    lpOp.ordering = "asroottree"  # Slow, but more intuitive
                    wordList = self.getWikiDocument().searchWiki(lpOp)
    
    #                 wordList = self.getWikiData().getAllDefinedWikiPageNames()
                    
                elif typ in (GUI_ID.MENU_EXPORT_SUB_AS_PAGE,
                        GUI_ID.MENU_EXPORT_SUB_AS_PAGES):
                    # Export a subtree of current word
                    if self.getCurrentWikiWord() is None:
                        self.pWiki.displayErrorMessage(
                                u"No real wiki word selected as root")
                        return
                    lpOp = Sar.ListWikiPagesOperation()
                    item = Sar.ListItemWithSubtreeWikiPagesNode(lpOp,
                            [self.getCurrentWikiWord()], -1)
                    lpOp.setSearchOpTree(item)
                    lpOp.ordering = "asroottree"  # Slow, but more intuitive
                    wordList = self.getWikiDocument().searchWiki(lpOp)
    
    #                 wordList = self.getWikiData().getAllSubWords(
    #                         [self.getCurrentWikiWord()])
                else:
                    if self.getCurrentWikiWord() is None:
                        self.pWiki.displayErrorMessage(
                                u"No real wiki word selected as root")
                        return
    
                    wordList = (self.getCurrentWikiWord(),)

                expclass, exptype, addopt = self.EXPORT_PARAMS[typ]
                
                self.saveAllDocPages(force=True)
                self.getWikiData().commit()
                
                ob = expclass(self)
                if addopt is None:
                    # Additional options not given -> take default provided by exporter
                    addopt = ob.getAddOpt(None)
    
                ob.export(self.getWikiDataManager(), wordList, exptype, dest,
                        False, addopt)
    
                self.configuration.set("main", "last_active_dir", dest)

        except (IOError, OSError, DbAccessError), e:
            self.lostAccess(e)
            raise


    def OnCmdImportDialog(self, evt):
        self.saveAllDocPages()
        self.getWikiData().commit()

        dlg = ImportDialog(self, -1, self)
        dlg.CenterOnParent(wx.BOTH)

        result = dlg.ShowModal()
        dlg.Destroy()


    def showAddFileUrlDialog(self):
        dlg = wx.FileDialog(self, u"Choose a file to create URL",
                self.getLastActiveDir(), "", "*.*", wx.OPEN)
        if dlg.ShowModal() == wx.ID_OK:
            url = urllib.pathname2url(dlg.GetPath())
            if dlg.GetPath().endswith(".wiki"):
                url = "wiki:" + url
            else:
#                 doCopy = False  # Necessary because key state may change between
#                                 # the two ifs
#                 if False:
#                     # Relative rel: URL
#                     locPath = self.editor.pWiki.getWikiConfigPath()
#                     if locPath is not None:
#                         locPath = dirname(locPath)
#                         relPath = relativeFilePath(locPath, fn)
#                         if relPath is None:
#                             # Absolute path needed
#                             urls.append("file:%s" % url)
#                         else:
#                             urls.append("rel://%s" % urllib.pathname2url(relPath))
#                 else:
    
                # Absolute file: URL
                url = "file:" + url
                
            self.getActiveEditor().AddText(url)
            
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


    def rebuildWiki(self, skipConfirm = False):
        if not skipConfirm:
            result = wx.MessageBox(u"Are you sure you want to rebuild this wiki? "+
                    u"You may want to backup your data first!",
                    u'Rebuild wiki',
                    wx.YES_NO | wx.YES_DEFAULT | wx.ICON_QUESTION, self)

        if skipConfirm or result == wx.YES :
            try:
                self.saveAllDocPages()
                progresshandler = wxGuiProgressHandler(u"Rebuilding wiki",
                        u"Rebuilding wiki", 0, self)
                self.getWikiDataManager().rebuildWiki(progresshandler)

                self.tree.collapse()

                # TODO Adapt for functional pages
                if self.getCurrentWikiWord() is not None:
                    self.openWikiPage(self.getCurrentWikiWord(),
                            forceTreeSyncFromRoot=True)
            except (IOError, OSError, DbAccessError), e:
                self.lostAccess(e)
                raise
            except Exception, e:
                self.displayErrorMessage(u"Error rebuilding wiki", e)
                traceback.print_exc()


    def vacuumWiki(self):
        try:
            self.getWikiData().vacuum()
        except (IOError, OSError, DbAccessError), e:
            self.lostAccess(e)
            raise


#     def OnCmdCloneWindow(self, evt):
#         _prof.start()
#         self._OnCmdCloneWindow(evt)
#         _prof.stop()


    def OnCmdCloneWindow(self, evt):
        wd = self.getWikiDocument()
        if wd is None:
            return

        try:
            clAction = CmdLineAction([])
            clAction.wikiToOpen = wd.getWikiConfigPath()
            ww = self.getCurrentWikiWord()
            if ww is not None:
                clAction.wikiWordToOpen = ww

            wx.GetApp().startPersonalWikiFrame(clAction)
        except Exception, e:
            traceback.print_exc()
            self.displayErrorMessage('Error while starting new '
                    'WikidPad instance', e)
            return


    def OnImportFromPagefiles(self, evt):
        dlg=wx.MessageDialog(self,
                u"This could overwrite pages in the database. Continue?",
                u"Import pagefiles", wx.YES_NO)

        result = dlg.ShowModal()
        if result == wx.ID_YES:
            self.getWikiData().copyWikiFilesToDatabase()


    def insertAttribute(self, name, value):
        self.getActiveEditor().AppendText(u"\n\n[%s=%s]" % (name, value))
#         self.saveCurrentDocPage()   # TODO Remove or activate this line?

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


    def insertDate(self):
        # strftime can't handle unicode correctly, so conversion is needed
        mstr = mbcsEnc(self.configuration.get("main", "strftime"), "replace")[0]
        self.getActiveEditor().AddText(mbcsDec(strftime(mstr), "replace")[0])

    def getLastActiveDir(self):
        return self.configuration.get("main", "last_active_dir", os.getcwd())

    
    def stdDialog(self, dlgtype, title, message, additional=None):
        """
        Used to show a dialog, especially in scripts.
        Possible values for dlgtype:
        "text": input text to dialog, additional is the default text
            when showing dlg returns entered text on OK or empty string
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
                raise RuntimeError, "Unknown dialog type"

            result = wx.MessageBox(uniToGui(message), uniToGui(title), style, self)
            
            if result == wx.OK:
                return "ok"
            elif result == wx.CANCEL:
                return "cancel"
            elif result == wx.YES:
                return "yes"
            elif result == wx.NO:
                return "no"
                
            raise RuntimeError, "Internal Error"

    def displayMessage(self, title, str):
        """pops up a dialog box,
        used by scripts only
        """
        dlg_m = wx.MessageDialog(self, uniToGui(u"%s" % str), title, wx.OK)
        dlg_m.ShowModal()
        dlg_m.Destroy()


    def displayErrorMessage(self, errorStr, e=u""):
        "pops up a error dialog box"
        dlg_m = wx.MessageDialog(self, uniToGui(u"%s. %s." % (errorStr, e)),
                'Error!', wx.OK)
        dlg_m.ShowModal()
        dlg_m.Destroy()
        try:
            self.statusBar.SetStatusText(uniToGui(errorStr), 0)
        except:
            pass


    def showAboutDialog(self):
        dlg = AboutDialog(self)
        dlg.ShowModal()
        dlg.Destroy()

    def OnShowWikiInfoDialog(self, evt):
        dlg = WikiInfoDialog(self, -1, self)
        dlg.ShowModal()
        dlg.Destroy()


    # ----------------------------------------------------------------------------------------
    # Event handlers from here on out.
    # ----------------------------------------------------------------------------------------


    def miscEventHappened(self, miscevt):
        """
        Handle misc events
        """
        try:
            if miscevt.getSource() is self.getWikiDocument():
                # Event from wiki document aka wiki data manager
                if miscevt.has_key("deleted wiki page"):
                    wikiPage = miscevt.get("wikiPage")
                    # trigger hooks
                    self.hooks.deletedWikiWord(self,
                            wikiPage.getWikiWord())
    
                    self.fireMiscEventProps(miscevt.getProps())
                    if wikiPage is self.getCurrentDocPage():
                        self.pageHistory.goAfterDeletion()
    
                elif miscevt.has_key("renamed wiki page"):
                    oldWord = miscevt.get("wikiPage").getWikiWord()
                    newWord = miscevt.get("newWord")
    
                    if miscevt.get("wikiPage") is self.getCurrentDocPage():
                        self.getActiveEditor().loadWikiPage(None)
    
                        # trigger hooks
                        self.hooks.renamedWikiWord(self, oldWord, newWord)
        
                        self.openWikiPage(newWord, forceTreeSyncFromRoot=False)
                        # self.findCurrentWordInTree()
                    else:
                        # trigger hooks
                        self.hooks.renamedWikiWord(self, oldWord, newWord)
    
                elif miscevt.has_key("updated wiki page"):
                    # This was send from a WikiDocument(=WikiDataManager) object,
                    # send it again to listening components
                    self.fireMiscEventProps(miscevt.getProps())
                elif miscevt.has_key("reread text blocks needed"):
                    self.rereadTextBlocks()
                elif miscevt.has_key("reread personal word list needed"):
                    if self.spellChkDlg is not None:
                        self.spellChkDlg.rereadPersonalWordLists()
        except (IOError, OSError, DbAccessError), e:
            self.lostAccess(e)
            raise


    def OnWikiOpen(self, event):
        dlg = wx.FileDialog(self, u"Choose a Wiki to open",
                self.getLastActiveDir(), "", "*.wiki", wx.OPEN)
        if dlg.ShowModal() == wx.ID_OK:
            self.openWiki(mbcsDec(abspath(dlg.GetPath()), "replace")[0])
        dlg.Destroy()


    def OnWikiOpenNewWindow(self, event):
        dlg = wx.FileDialog(self, u"Choose a Wiki to open",
                self.getLastActiveDir(), "", "*.wiki", wx.OPEN)
        if dlg.ShowModal() == wx.ID_OK:
            try:
                clAction = CmdLineAction([])
                clAction.wikiToOpen = mbcsDec(abspath(dlg.GetPath()), "replace")[0]
                wx.GetApp().startPersonalWikiFrame(clAction)
#                 PersonalWikiFrame(None, -1, "WikidPad", self.wikiAppDir,
#                         self.globalConfigDir, self.globalConfigSubDir, clAction)
                # os.startfile(self.wikiPadHelp)   # TODO!
            except Exception, e:
                traceback.print_exc()
                self.displayErrorMessage('Error while starting new '
                        'WikidPad instance', e)
                return

        dlg.Destroy()


    def OnWikiOpenAsType(self, event):
        dlg = wx.FileDialog(self, u"Choose a Wiki to open",
                self.getLastActiveDir(), "", "*.wiki", wx.OPEN)
        if dlg.ShowModal() == wx.ID_OK:
            self.openWiki(mbcsDec(abspath(dlg.GetPath()), "replace")[0],
                    ignoreWdhName=True)
        dlg.Destroy()
        
        
    def OnWikiNew(self, event):
        dlg = wx.TextEntryDialog (self,
                u"Name for new wiki (must be in the form of a WikiWord):",
                u"Create New Wiki", u"MyWiki", wx.OK | wx.CANCEL)

        if dlg.ShowModal() == wx.ID_OK:
            wikiName = guiToUni(dlg.GetValue())
            wikiName = wikiWordToLabel(wikiName)

            # make sure this is a valid wiki word
            if wikiName.find(u' ') == -1 and \
                    WikiFormatting.isNakedWikiWordForNewWiki(wikiName):
#                     self.getFormatting().isNakedWikiWord(wikiName):
                startDir = self.getWikiConfigPath()
                if startDir is None:
                    startDir = self.getLastActiveDir()
                else:
                    startDir = dirname(dirname(startDir))

                dlg = wx.DirDialog(self, u"Directory to store new wiki",
                        startDir,
                        style=wx.DD_DEFAULT_STYLE|wx.DD_NEW_DIR_BUTTON)
                if dlg.ShowModal() == wx.ID_OK:
#                     try:
                    self.newWiki(wikiName, dlg.GetPath())
#                     except IOError, e:
#                         self.displayErrorMessage(u'There was an error while '+
#                                 'creating your new Wiki.', e)
            else:
                self.displayErrorMessage((u"'%s' is an invalid wiki word. "+
                u"There must be no spaces and mixed caps") % wikiName)

        dlg.Destroy()


    def OnSelectRecentWiki(self, event):
        recentItem = self.recentWikisMenu.FindItemById(event.GetId())
        if not self.openWiki(recentItem.GetText()):
            self.recentWikisMenu.Remove(event.GetId())


#     def informWikiPageUpdate(self, wikiPage):
#         # self.tree.buildTreeForWord(wikiPage.wikiWord)    # self.currentWikiWord)
#         self.fireMiscEventProps({"updated page props": None,
#                 "wikiPage": wikiPage})
                
    def OnIdle(self, evt):
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
                currentTime = time()
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


    def OnCmdCheckWrapMode(self, evt):        
        self.getActiveEditor().setWrapMode(evt.IsChecked())
        self.configuration.set("main", "wrap_mode", evt.IsChecked())


    def OnCmdCheckIndentationGuides(self, evt):        
        self.getActiveEditor().SetIndentationGuides(evt.IsChecked())
        self.configuration.set("main", "indentation_guides", evt.IsChecked())

    def OnCmdCheckAutoIndent(self, evt):        
        self.getActiveEditor().setAutoIndent(evt.IsChecked())
        self.configuration.set("main", "auto_indent", evt.IsChecked())

    def OnCmdCheckAutoBullets(self, evt):        
        self.getActiveEditor().setAutoBullets(evt.IsChecked())
        self.configuration.set("main", "auto_bullets", evt.IsChecked())

    def OnCmdCheckShowLineNumbers(self, evt):        
        self.getActiveEditor().setShowLineNumbers(evt.IsChecked())
        self.configuration.set("main", "show_lineNumbers", evt.IsChecked())


    def OnCloseButton(self, evt):
        if self.configuration.getboolean("main", "minimize_on_closeButton"):
            self.Iconize(True)
        else:
            self.exitWiki()
#             self.Destroy()

    def exitWiki(self):
#         if not self.configuration.getboolean("main", "minimize_on_closeButton"):
#             self.Close()
#         else:
#             self.prepareExit()
#             self.Destroy()
# 
# 
#     def prepareExit(self):
        # Stop clipboard catcher if running
        if self.win32Interceptor is not None:
            self.win32Interceptor.unintercept()

        self.closeWiki()
        self.getCurrentDocPagePresenter().close()

        # trigger hook
        self.hooks.exit(self)

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
        self.configuration.set("main", "zoom", self.getActiveEditor().GetZoom())
        self.configuration.set("main", "wiki_history", ";".join(self.wikiHistory))
        self.writeGlobalConfig()

        # save the current wiki state
#         self.saveCurrentWikiState()

        wx.TheClipboard.Flush()

        if self.tbIcon is not None:
            if self.tbIcon.IsIconInstalled():
                self.tbIcon.RemoveIcon()

            self.tbIcon.Destroy()
            self.tbIcon = None

        self.Destroy()



class TaskBarIcon(wx.TaskBarIcon):
    def __init__(self, pwiki):
        wx.TaskBarIcon.__init__(self)
        self.pwiki = pwiki

        # Register menu events
        wx.EVT_MENU(self, GUI_ID.TBMENU_RESTORE, self.OnLeftUp)
        wx.EVT_MENU(self, GUI_ID.TBMENU_SAVE, lambda evt: (self.pwiki.saveAllDocPages(force=True),
                self.pwiki.getWikiData().commit()))
        wx.EVT_MENU(self, GUI_ID.TBMENU_EXIT, lambda evt: self.pwiki.exitWiki())

        wx.EVT_TASKBAR_LEFT_UP(self, self.OnLeftUp)

    def OnLeftUp(self, evt):
        if self.pwiki.IsIconized():
            self.pwiki.Iconize(False)
            self.pwiki.Show(True)
        
        self.pwiki.Raise()

    def CreatePopupMenu(self):
        # Build menu
        tbMenu = wx.Menu()
        tbMenu.Append(GUI_ID.TBMENU_RESTORE, '&Restore')
        tbMenu.Append(GUI_ID.TBMENU_SAVE, '&Save\t')
        tbMenu.Append(GUI_ID.TBMENU_EXIT, 'E&xit')

        return tbMenu


def importCode(code, usercode, name, add_to_sys_modules=False):
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
    if add_to_sys_modules:
        sys.modules[name] = module

    return module



