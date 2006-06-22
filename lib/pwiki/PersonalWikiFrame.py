import os, gc, traceback, sets, string
from os.path import *
from time import localtime, time, strftime

import urllib_red as urllib

from wxPython.wx import *
from wxPython.stc import *
from wxPython.html import *
from wxHelper import GUI_ID, cloneImageList, keyDownToAccel

from MiscEvent import MiscEventSourceMixin

import Configuration
from WindowLayout import WindowLayouter, setWindowPos, setWindowSize
# from WikiData import *
from wikidata import DbBackendUtils
from wikidata.WikiDataManager import WikiDataManager
import DocPages

from CmdLineAction import CmdLineAction
from WikiTxtCtrl import WikiTxtCtrl
from WikiTreeCtrl import WikiTreeCtrl
from WikiHtmlView import WikiHtmlView
from AboutDialog import AboutDialog
from LogWindow import LogWindow

import PropertyHandling, SpellChecker

from PageHistory import PageHistory
from SearchAndReplace import SearchReplaceOperation
from Printing import Printer, PrintMainDialog

from AdditionalDialogs import *
from SearchAndReplaceDialogs import *

from WikiExceptions import *

import Exporters
from StringOps import uniToGui, guiToUni, mbcsDec, mbcsEnc, strToBool, \
        wikiWordToLabel, BOM_UTF8, fileContentToUnicode, splitIndent, \
        unescapeWithRe

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
    show a wxProgressDialog
    """
    def __init__(self, title, msg, addsteps, parent, flags=wxPD_APP_MODAL):
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
        self.progDlg = wxProgressDialog(self.title, self.msg,
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



class PersonalWikiFrame(wxFrame, MiscEventSourceMixin):
    def __init__(self, parent, id, title, wikiAppDir, globalConfigDir,
            cmdLineAction):
        wxFrame.__init__(self, parent, -1, title, size = (700, 550),
                         style=wxDEFAULT_FRAME_STYLE|wxNO_FULL_REPAINT_ON_RESIZE)
        MiscEventSourceMixin.__init__(self)

        if cmdLineAction.cmdLineError:
            cmdLineAction.showCmdLineUsage(self,
                    u"Bad formatted command line.\n\n")
            self.Close()
            self.Destroy()
            return

        self.sleepMode = False  # Is program in low resource sleep mode?

        if not globalConfigDir or not exists(globalConfigDir):
            self.displayErrorMessage(
                    u"Error initializing environment, couldn't locate "+
                    u"global config directory", u"Shutting Down")
            self.Close()


        # initialize some variables
        self.globalConfigDir = globalConfigDir
        self.wikiAppDir = wikiAppDir
        
        self.globalConfigSubDir = join(self.globalConfigDir, ".WikidPadGlobals")
        if not exists(self.globalConfigSubDir):
            os.mkdir(self.globalConfigSubDir)
        # Create the "[TextBlocks].wiki" file in the global config subdirectory
        # if the file doesn't exist yet.
        tbLoc = join(self.globalConfigSubDir, "[TextBlocks].wiki")
        if not exists(tbLoc):
            tbFile = open(tbLoc, "wa")
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
        self.configuration = Configuration.createConfiguration()

        self.wikiPadHelp = join(self.wikiAppDir, 'WikidPadHelp',
                'WikidPadHelp.wiki')
        self.windowLayouter = None  # will be set by initializeGui()

        # defaults
        self.wikiData = None
        self.wikiDataManager = None
        self.wikiConfigFilename = None
#         self.currentWikiWord = None
#         self.currentWikiPage = None
        self.lastCursorPositionInPage = {}
        self.iconLookupCache = {}
        self.wikiHistory = []
        self.findDlg = None  # Stores find&replace or wiki search dialog, if present
        self.spellChkDlg = None  # Stores spell check dialog, if present
        self.mainmenu = None
        self.editorMenu = None  # "Editor" menu
        self.fastSearchField = None   # Text field in toolbar
        self.textBlocksActivation = {} # See self.buildTextBlocksMenu()
        # Position of the root menu of the text blocks within "Editor" menu
        self.textBlocksMenuPosition = None  
        self.cmdIdToIconName = None # Maps command id (=menu id) to icon name
                                    # needed for "Editor"->"Add icon property"
        self.cmdIdToColorName = None # Same for color names
        
        # setup plugin manager and hooks API
        self.pluginManager = PluginManager()
        self.hooks = self.pluginManager.registerPluginAPI(("hooks",1),
            ["startup", "newWiki", "createdWiki", "openWiki", "openedWiki", 
             "openWikiWord", "newWikiWord", "openedWikiWord", "savingWikiWord",
             "savedWikiWord", "renamedWikiWord", "deletedWikiWord", "exit"] )
        # interfaces for menu and toolbar plugins
        self.menuFunctions = self.pluginManager.registerPluginAPI(("MenuFunctions",1), 
                                ["describeMenuItems"])
        self.toolbarFunctions = self.pluginManager.registerPluginAPI(("ToolbarFunctions",1), 
                                ["describeToolbarItems"])

        # load extensions
        self.loadExtensions()

        # initialize the wiki syntax
        WikiFormatting.initialize(self.wikiSyntax)
        
        # Initialize new component
        self.formatting = WikiFormatting.WikiFormatting(self, self.wikiSyntax)
        
        # Connect page history
        self.pageHistory = PageHistory(self)

        self.propertyChecker = PropertyHandling.PropertyChecker(self)

        # trigger hook
        self.hooks.startup(self)

        # if it already exists read it in
        if exists(self.globalConfigLoc):
            try:
                self.configuration.loadGlobalConfig(self.globalConfigLoc)
            except Configuration.Error:
                self.createDefaultGlobalConfig()
        else:
            self.createDefaultGlobalConfig()

        # Initialize printing
        self.printer = Printer(self)

        # wiki history
        history = self.configuration.get("main", "wiki_history")
        if history:
            self.wikiHistory = history.split(u";")
          
        # clipboard catcher  
        if WindowsHacks is None:
            self.clipboardCatcher = None
        else:
            self.clipboardCatcher = WindowsHacks.ClipboardCatcher(self)
            

        # resize the window to the last position/size
        setWindowSize(self, (self.configuration.getint("main", "size_x", 10),
                self.configuration.getint("main", "size_y", 10)))
        setWindowPos(self, (self.configuration.getint("main", "pos_x", 10),
                self.configuration.getint("main", "pos_y", 10)))

        # Set the auto save timing
        self.autoSaveDelayAfterKeyPressed = self.configuration.getint(
                "main", "auto_save_delay_key_pressed")
        self.autoSaveDelayAfterDirty = self.configuration.getint(
                "main", "auto_save_delay_dirty")

        # Should reduce resources usage (less icons)
        # Do not set self.lowResources after initialization here!
        self.lowResources = self.configuration.getboolean("main", "lowresources")

        # get the wrap mode setting
        self.wrapMode = self.configuration.getboolean("main", "wrap_mode")

        # get the position of the splitter
        self.lastSplitterPos = self.configuration.getint("main", "splitter_pos")

        # is autosave on
#         self.autoSave = True
#         if (self.globalConfig.has_option("main", "auto_save")):
#             self.autoSave = self.globalConfig.getboolean("main", "auto_save")

#         # are indentationGuides enabled
#         self.indentationGuides = self.configuration.getboolean("main",
#                 "indentation_guides")

#         # set the locale  # TODO Why?
#         locale = wxLocale()
#         self.locale = locale.GetCanonicalName()

        # get the default font for the editor
        self.defaultEditorFont = self.configuration.get("main", "font",
                self.presentationExt.faces["mono"])
                
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
            if exists(wikiToOpen):
                self.openWiki(wikiToOpen, wikiWordToOpen)
            else:
                self.statusBar.SetStatusText(
                        uniToGui(u"Couldn't open last wiki: %s" % wikiToOpen), 0)

        # set the focus to the editor
#         if self.vertSplitter.GetSashPosition() < 2:
#             self.activeEditor.SetFocus()

        # display the window
        ## if not (self.showOnTray and self.IsIconized()):
            
        cmdLineAction.actionBeforeShow(self)
        
        if cmdLineAction.exitFinally:
            self.Close()
            self.Destroy()
            return

        self.Show(True)
        
        if self.lowResources and self.IsIconized():
            self.resourceSleep()


    def loadExtensions(self):
        self.wikidPadHooks = self.getExtension('WikidPadHooks', u'WikidPadHooks.py')
        self.keyBindings = self.getExtension('KeyBindings', u'KeyBindings.py')
        self.evalLib = self.getExtension('EvalLibrary', u'EvalLibrary.py')
        self.wikiSyntax = self.getExtension('SyntaxLibrary', u'WikiSyntax.py')
        self.presentationExt = self.getExtension('Presentation', u'Presentation.py')
        dirs = [ join(self.wikiAppDir, u'user_extensions'),
                join(self.wikiAppDir, u'extensions') ]
        self.pluginManager.loadPlugins( dirs, [ u'KeyBindings.py',
                u'EvalLibrary.py', u'WikiSyntax.py' ] )

    def getExtension(self, extensionName, fileName):
        extensionFileName = join(self.wikiAppDir, 'user_extensions', fileName)
        if exists(extensionFileName):
            extFile = open(extensionFileName, "rU")
            userExtension = extFile.read()
            extFile.close()
        else:
            userExtension = None
            
        extensionFileName = join(self.wikiAppDir, 'extensions', fileName)
        extFile = open(extensionFileName, "rU")
        systemExtension = extFile.read()
        extFile.close()
        
        return importCode(systemExtension, userExtension, extensionName)

    def createDefaultGlobalConfig(self):
        self.configuration.createEmptyGlobalConfig(self.globalConfigLoc)
        self.configuration.fillGlobalWithDefaults()

        self.configuration.set("main", "wiki_history", self.wikiPadHelp)
        self.configuration.set("main", "last_wiki", self.wikiPadHelp)
        curSize = self.GetSize()
        self.configuration.set("main", "size_x", str(curSize.x))
        self.configuration.set("main", "size_y", str(curSize.y))
        curPos = self.GetPosition()
        self.configuration.set("main", "pos_x", str(curPos.x))
        self.configuration.set("main", "pos_y", str(curPos.y))
        self.configuration.set("main", "last_active_dir", os.getcwd())


    def getCurrentWikiWord(self):
        docPage = self.getCurrentDocPage()
        if docPage is None or not isinstance(docPage,
                (DocPages.WikiPage, DocPages.AliasWikiPage)):
            return None
        return docPage.getWikiWord()

    def getCurrentDocPage(self):
        if self.activeEditor is None:
            return None
        return self.activeEditor.getLoadedDocPage()
        
    def getActiveEditor(self):
        return self.activeEditor
        
    def setActiveEditor(self, activeEditor):
        self.activeEditor = activeEditor

    def getWikiData(self):
        if self.wikiDataManager is None:
            return None

        return self.wikiDataManager.getWikiData()

    def getWikiDataManager(self):
        return self.wikiDataManager
        
    def getWikiConfigPath(self):
        return self.wikiConfigFilename

    def getConfig(self):
        return self.configuration
        
    def getFormatting(self):
        return self.formatting
        
    def getLogWindow(self):
        return self.logWindow


    # TODO!
    def fillIconLookupCache(self, createIconImageList=False):
        """
        Fills or refills the self.iconLookupCache (if createIconImageList is
        false, self.iconImageList must exist already)
        If createIconImageList is true, self.iconImageList is also
        built
        """

        if createIconImageList:
            # create the image icon list
            self.iconImageList = wxImageList(16, 16)
            self.iconLookupCache = {}

        for icon in self.iconFileList:
            iconFile = join(self.wikiAppDir, "icons", icon)
            bitmap = wxBitmap(iconFile, wxBITMAP_TYPE_GIF)
            try:
                id = -1
                if createIconImageList:
                    id = self.iconImageList.Add(bitmap, wxNullBitmap)

                if self.lowResources:   # and not icon.startswith("tb_"):
                    bitmap = None

                iconname = icon.replace('.gif', '')
                if id == -1:
                    id = self.iconLookupCache[iconname][0]

                self.iconLookupCache[iconname] = (id, bitmap)
            except Exception, e:
                traceback.print_exc()
                sys.stderr.write("couldn't load icon %s\n" % iconFile)

    def lookupIcon(self, iconname):
        """
        Returns the bitmap object for the given iconname.
        If the bitmap wasn't cached already, it is loaded and created.
        If icon is unknown, None is returned.
        """
        try:
            bitmap = self.iconLookupCache[iconname][1]
            if bitmap is not None:
                return bitmap
                
            # Bitmap not yet available -> create it and store in the cache
            iconFile = join(self.wikiAppDir, "icons", iconname+".gif")
            bitmap = wxBitmap(iconFile, wxBITMAP_TYPE_GIF)
            
            self.iconLookupCache[iconname] = (self.iconLookupCache[iconname][0],
                    bitmap)
            return bitmap

        except KeyError:
            return None


    def lookupIconIndex(self, iconname):
        """
        Returns the id number into self.iconImageList of the requested icon.
        If icon is unknown, -1 is returned.
        """
        try:
            return self.iconLookupCache[iconname][0]
        except KeyError:
            return -1


    def resolveIconDescriptor(self, desc, default=None):
        """
        Used for plugins of type "MenuFunctions" or "ToolbarFunctions".
        Tries to find and return an appropriate wxBitmap object.
        
        An icon descriptor can be one of the following:
            - None
            - a wxBitmap object
            - the filename of a bitmap
            - a tuple of filenames, first existing file is used
        
        If no bitmap can be found, default is returned instead.
        """
        if desc is None:
            return default            
        elif isinstance(desc, wxBitmap):
            return desc
        elif isinstance(desc, basestring):
            result = self.lookupIcon(desc)
            if result is not None:
                return result
            
            return default
        else:    # A sequence of possible names
            for n in desc:
                result = self.lookupIcon(n)
                if result is not None:
                    return result

            return default


    def addMenuItem(self, menu, label, text, evtfct=None, icondesc=None,
            menuID=None):
        if menuID is None:
            menuID = wxNewId()

        menuitem = wxMenuItem(menu, menuID, label, text)
        # if icondesc:  # (not self.lowResources) and
        bitmap = self.resolveIconDescriptor(icondesc)
        if bitmap:
            menuitem.SetBitmap(bitmap)

        menu.AppendItem(menuitem)
        if evtfct is not None:
            EVT_MENU(self, menuID, evtfct)
        return menuitem


    def buildWikiMenu(self):
        """
        Builds the first, the "Wiki" menu and returns it
        """
        wikiData = self.getWikiData()
        wikiMenu=wxMenu()

        self.addMenuItem(wikiMenu, '&New\t' + self.keyBindings.NewWiki,
                'New Wiki', self.OnWikiNew)

        self.addMenuItem(wikiMenu, '&Open\t' + self.keyBindings.OpenWiki,
                'Open Wiki', self.OnWikiOpen)

        self.addMenuItem(wikiMenu, 'Open as &Type',
                'Open Wiki with a specified wiki database type',
                self.OnWikiOpenAsType)

        self.recentWikisMenu = wxMenu()
        wikiMenu.AppendMenu(wxNewId(), '&Recent', self.recentWikisMenu)

        # init the list of items
        for wiki in self.wikiHistory:
            menuID=wxNewId()
            self.recentWikisMenu.Append(menuID, wiki)
            EVT_MENU(self, menuID, self.OnSelectRecentWiki)

        if wikiData is not None:
            wikiMenu.AppendSeparator()

            self.addMenuItem(wikiMenu, '&Search Wiki\t' +
                    self.keyBindings.SearchWiki, 'Search Wiki',
                    lambda evt: self.showSearchDialog(), "tb_lens")

            self.addMenuItem(wikiMenu, '&View Bookmarks\t' +
                    self.keyBindings.ViewBookmarks, 'View Bookmarks',
                    lambda evt: self.viewBookmarks())

        wikiMenu.AppendSeparator()

        menuID = wxNewId()
        menuItem = wxMenuItem(wikiMenu, menuID,
                "&Show Tree Control\t" + self.keyBindings.ShowTreeControl,
                "Show Tree Control", wxITEM_CHECK)
        wikiMenu.AppendItem(menuItem)
        EVT_MENU(self, menuID, lambda evt: self.setShowTreeControl(
                self.windowLayouter.isWindowCollapsed("maintree")))
        EVT_UPDATE_UI(self, menuID, self.OnUpdateTreeCtrlMenuItem)

        menuItem = wxMenuItem(wikiMenu, GUI_ID.CMD_SHOW_TOOLBAR,
                "Show Toolbar\t" + self.keyBindings.ShowToolbar, 
                "Show Toolbar", wxITEM_CHECK)
        wikiMenu.AppendItem(menuItem)
        EVT_MENU(self, GUI_ID.CMD_SHOW_TOOLBAR, lambda evt: self.setShowToolbar(
                not self.getConfig().getboolean("main", "toolbar_show", True)))
        EVT_UPDATE_UI(self, GUI_ID.CMD_SHOW_TOOLBAR,
                self.OnUpdateToolbarMenuItem)

        menuItem = wxMenuItem(wikiMenu, GUI_ID.CMD_STAY_ON_TOP,
                "Stay on Top\t" + self.keyBindings.StayOnTop, 
                "Stay on Top", wxITEM_CHECK)
        wikiMenu.AppendItem(menuItem)
        EVT_MENU(self, GUI_ID.CMD_STAY_ON_TOP, lambda evt: self.setStayOnTop(
                not self.getStayOnTop()))
        EVT_UPDATE_UI(self, GUI_ID.CMD_STAY_ON_TOP,
                self.OnUpdateStayOnTopMenuItem)

        self.addMenuItem(wikiMenu, 'O&ptions...',
                'Set Options', lambda evt: self.showOptionsDialog())

        wikiMenu.AppendSeparator()
        
        if wikiData is not None:
            exportWikisMenu = wxMenu()
            wikiMenu.AppendMenu(wxNewId(), 'Export', exportWikisMenu)
    
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
            menuID=wxNewId()
            wikiMenu.Append(menuID, '&Rebuild Wiki', 'Rebuild this wiki')
            EVT_MENU(self, menuID, lambda evt: self.rebuildWiki())

        if wikiData is not None and wikiData.checkCapability("compactify") == 1:
            menuID=wxNewId()
            wikiMenu.Append(menuID, '&Vacuum Wiki', 'Free unused space in database')
            EVT_MENU(self, menuID, lambda evt: self.vacuumWiki())

        if wikiData is not None and \
                wikiData.checkCapability("plain text import") == 1:
            menuID=wxNewId()
            wikiMenu.Append(menuID, '&Copy .wiki files to database', 'Copy .wiki files to database')
            EVT_MENU(self, menuID, self.OnImportFromPagefiles)

        if wikiData is not None and wikiData.checkCapability("versioning") == 1:
            wikiMenu.AppendSeparator()
    
            menuID=wxNewId()
            wikiMenu.Append(menuID, '&Store version', 'Store new version')
            EVT_MENU(self, menuID, lambda evt: self.showStoreVersionDialog())
    
            menuID=wxNewId()
            wikiMenu.Append(menuID, '&Retrieve version', 'Retrieve previous version')
            EVT_MENU(self, menuID, lambda evt: self.showSavedVersionsDialog())
    
            menuID=wxNewId()
            wikiMenu.Append(menuID, 'Delete &All Versions', 'Delete all stored versions')
            EVT_MENU(self, menuID, lambda evt: self.showDeleteAllVersionsDialog())

        wikiMenu.AppendSeparator()  # TODO May have two separators without anything between

#         self.addMenuItem(wikiMenu, '&Test', 'Test', lambda evt: self.testIt())

        menuID=wxNewId()
        wikiMenu.Append(menuID, 'E&xit', 'Exit')
        EVT_MENU(self, menuID, lambda evt: self.Close())
        
        return wikiMenu


    def _addToTextBlocksMenu(self, tbContent, stack, reusableIds):
        """
        Helper for buildTextBlocksMenu() to build up menu
        """
        for line in tbContent.split(u"\n"):
            if line.strip() == u"":
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
                stack.append([deep, None, wxMenu()])
            else:
                while stack[-1][0] > deep:
                    title, menu = stack.pop()[1:3]
                    if title is None:
                        title = u"<No title>"
                    
                    stack[-1][2].AppendMenu(wxNewId(), title, menu)
            
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
                menuID = wxNewId()
                EVT_MENU(self, menuID, self.OnTextBlockUsed)

            menuItem = wxMenuItem(menu, menuID, entryTitle)
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
            
            stack[-1][2].AppendMenu(wxNewId(), title, menu)


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
        
        stack = [[0, u"Text blocks", wxMenu()]]
                
        wikiData = self.getWikiData()
        if wikiData is not None:
            if wikiData.isDefinedWikiWord("[TextBlocks]"):
                # We have current wiki with appropriate functional page,
                # so fill menu first with wiki specific text blocks
                tbContent = wikiData.getContent("[TextBlocks]")
                self._addToTextBlocksMenu(tbContent, stack, reusableIds)

                stack[-1][2].AppendSeparator()

        # Fill menu with global text blocks
        tbLoc = join(self.globalConfigSubDir, "[TextBlocks].wiki")
        try:
            tbFile = open(tbLoc, "rU")
            tbContent = tbFile.read()
            tbFile.close()
            tbContent = fileContentToUnicode(tbContent)
        except:
            tbContent = u""

        self._addToTextBlocksMenu(tbContent, stack, reusableIds)

        stack[-1][2].AppendSeparator()
        stack[-1][2].Append(GUI_ID.CMD_REREAD_TEXT_BLOCKS, 'Reread text blocks',
                'Reread the text block file(s) and recreate menu')
        EVT_MENU(self, GUI_ID.CMD_REREAD_TEXT_BLOCKS, self.OnRereadTextBlocks)

        return stack[-1][2]


    def OnTextBlockUsed(self, evt):
        try:
            entryFlags, entryContent = self.textBlocksActivation[evt.GetId()]
            if entryFlags is None:
                return

            if u"a" in entryFlags:
                self.appendText(entryContent)
            else:
                self.addText(entryContent)
            
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


        self.mainmenu = wxMenuBar()   # Create menu bar.

        wikiMenu = self.buildWikiMenu()

        wikiWordMenu=wxMenu()

        self.addMenuItem(wikiWordMenu, '&Open\t' + self.keyBindings.OpenWikiWord,
                'Open Wiki Word', lambda evt: self.showWikiWordOpenDialog(),
                "tb_doc")

        self.addMenuItem(wikiWordMenu, '&Save\t' + self.keyBindings.Save,
                'Save Current Wiki Word',
                lambda evt: (self.saveCurrentDocPage(force=True),
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
                
        if self.clipboardCatcher is not None:
            wikiWordMenu.AppendSeparator()

            menuItem = wxMenuItem(wikiWordMenu, GUI_ID.CMD_CLIPBOARD_CATCHER_AT_PAGE,
                    "Clipboard Catcher at Page\t" + self.keyBindings.CatchClipboardAtPage, 
                    u"Text copied to clipboard is also pasted to this page",
                    wxITEM_RADIO)
            wikiWordMenu.AppendItem(menuItem)
            EVT_MENU(self, GUI_ID.CMD_CLIPBOARD_CATCHER_AT_PAGE,
                    self.OnClipboardCatcherAtPage)
            EVT_UPDATE_UI(self, GUI_ID.CMD_CLIPBOARD_CATCHER_AT_PAGE,
                    self.OnUpdateClipboardCatcher)


            menuItem = wxMenuItem(wikiWordMenu, GUI_ID.CMD_CLIPBOARD_CATCHER_AT_CURSOR,
                    "Clipboard Catcher at Cursor\t" + self.keyBindings.CatchClipboardAtCursor, 
                    u"Text copied to clipboard is also added to cursor position",
                    wxITEM_RADIO)
            wikiWordMenu.AppendItem(menuItem)
            EVT_MENU(self, GUI_ID.CMD_CLIPBOARD_CATCHER_AT_CURSOR,
                    self.OnClipboardCatcherAtCursor)
            EVT_UPDATE_UI(self, GUI_ID.CMD_CLIPBOARD_CATCHER_AT_CURSOR,
                    self.OnUpdateClipboardCatcher)


            menuItem = wxMenuItem(wikiWordMenu, GUI_ID.CMD_CLIPBOARD_CATCHER_OFF,
                    "Clipboard Catcher off\t" + self.keyBindings.CatchClipboardOff, 
                    u"Switch off clipboard catcher",wxITEM_RADIO)
            wikiWordMenu.AppendItem(menuItem)
            EVT_MENU(self, GUI_ID.CMD_CLIPBOARD_CATCHER_OFF,
                    self.OnClipboardCatcherOff)
            EVT_UPDATE_UI(self, GUI_ID.CMD_CLIPBOARD_CATCHER_OFF,
                    self.OnUpdateClipboardCatcher)


        wikiWordMenu.AppendSeparator()

        menuID=wxNewId()
        wikiWordMenu.Append(menuID, '&Activate Link/Word\t' + self.keyBindings.ActivateLink, 'Activate Link/Word')
        EVT_MENU(self, menuID, lambda evt: self.activeEditor.activateLink())

        menuID=wxNewId()
        wikiWordMenu.Append(menuID, '&View Parents\t' + self.keyBindings.ViewParents, 'View Parents Of Current Wiki Word')
        EVT_MENU(self, menuID, lambda evt: self.viewParents(self.getCurrentWikiWord()))

        menuID=wxNewId()
        wikiWordMenu.Append(menuID, 'View &Parentless Nodes\t' + self.keyBindings.ViewParentless, 'View nodes with no parent relations')
        EVT_MENU(self, menuID, lambda evt: self.viewParentLess())

        menuID=wxNewId()
        wikiWordMenu.Append(menuID, 'View &Children\t' + self.keyBindings.ViewChildren, 'View Children Of Current Wiki Word')
        EVT_MENU(self, menuID, lambda evt: self.viewChildren(self.getCurrentWikiWord()))

        self.addMenuItem(wikiWordMenu, 'Set As &Root\t' + self.keyBindings.SetAsRoot,
                'Set current wiki word as tree root',
                lambda evt: self.setCurrentWordAsRoot())

        self.addMenuItem(wikiWordMenu, 'S&ynchronize with tree',
                'Find the current wiki word in the tree', lambda evt: self.findCurrentWordInTree(),
                "tb_cycle")


        historyMenu=wxMenu()

        menuID=wxNewId()
        historyMenu.Append(menuID, '&View History\t' + self.keyBindings.ViewHistory, 'View History')
        EVT_MENU(self, menuID, lambda evt: self.viewHistory())

        menuID=wxNewId()
        historyMenu.Append(menuID, '&Up History\t' + self.keyBindings.UpHistory, 'Up History')
        EVT_MENU(self, menuID, lambda evt: self.viewHistory(-1))

        menuID=wxNewId()
        historyMenu.Append(menuID, '&Down History\t' + self.keyBindings.DownHistory, 'Down History')
        EVT_MENU(self, menuID, lambda evt: self.viewHistory(1))

        self.addMenuItem(historyMenu, '&Back\t' + self.keyBindings.GoBack,
                'Go Back', lambda evt: self.pageHistory.goInHistory(-1),
                "tb_back")

        self.addMenuItem(historyMenu, '&Forward\t' + self.keyBindings.GoForward,
                'Go Forward', lambda evt: self.pageHistory.goInHistory(1),
                "tb_forward")

        self.addMenuItem(historyMenu, '&Wiki Home\t' + self.keyBindings.GoHome,
                'Go to Wiki Home Page',
                lambda evt: self.openWikiPage(self.wikiName, forceTreeSyncFromRoot=True),
                "tb_home")


        self.editorMenu=wxMenu()

        self.addMenuItem(self.editorMenu, '&Bold\t' + self.keyBindings.Bold,
                'Bold', lambda evt: self.keyBindings.makeBold(self.activeEditor),
                "tb_bold")

        self.addMenuItem(self.editorMenu, '&Italic\t' + self.keyBindings.Italic,
                'Italic', lambda evt: self.keyBindings.makeItalic(self.activeEditor),
                "tb_italic")

        self.addMenuItem(self.editorMenu, '&Heading\t' + self.keyBindings.Heading,
                'Add Heading', lambda evt: self.keyBindings.addHeading(self.activeEditor),
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
                lambda evt: self.keyBindings.makeWikiWord(self.activeEditor),
                "pin")


        self.editorMenu.AppendSeparator()

        self.addMenuItem(self.editorMenu, 'Cu&t\t' + self.keyBindings.Cut,
                'Cut', lambda evt: self.activeEditor.Cut(),
                "tb_cut", menuID=GUI_ID.CMD_CLIPBOARD_CUT)

        self.addMenuItem(self.editorMenu, '&Copy\t' + self.keyBindings.Copy,
                'Copy', lambda evt: self.fireMiscEventKeys(("command copy",)), # lambda evt: self.activeEditor.Copy()  # lambda evt: wxWindow.FindFocus().ProcessEvent(evt),
                "tb_copy", menuID=GUI_ID.CMD_CLIPBOARD_COPY)

        self.addMenuItem(self.editorMenu, 'Copy to &ScratchPad\t' + \
                self.keyBindings.CopyToScratchPad,
                'Copy Text to ScratchPad', lambda evt: self.activeEditor.snip(),
                "tb_copy")

        self.addMenuItem(self.editorMenu, '&Paste\t' + self.keyBindings.Paste,
                'Paste', lambda evt: self.activeEditor.Paste(),
                "tb_paste", menuID=GUI_ID.CMD_CLIPBOARD_PASTE)


        self.editorMenu.AppendSeparator()

        self.addMenuItem(self.editorMenu, '&Undo\t' + self.keyBindings.Undo,
                'Undo', lambda evt: self.activeEditor.CmdKeyExecute(wxSTC_CMD_UNDO))

        self.addMenuItem(self.editorMenu, '&Redo\t' + self.keyBindings.Redo,
                'Redo', lambda evt: self.activeEditor.CmdKeyExecute(wxSTC_CMD_REDO))


        self.editorMenu.AppendSeparator()
        
        self.textBlocksMenuPosition = self.editorMenu.GetMenuItemCount()

        self.editorMenu.AppendMenu(wxNewId(), '&Text blocks',
                self.buildTextBlocksMenu())

        # Build icon menu
        if self.lowResources:
            # Add only menu item for icon select dialog
            self.addMenuItem(self.editorMenu, 'Add icon property',
                    'Open icon select dialog', lambda evt: self.showIconSelectDialog())
        else:
            # Build full submenu for icons
            iconsMenu, self.cmdIdToIconName = PropertyHandling.buildIconsSubmenu(self)
            for cmi in self.cmdIdToIconName.keys():
                EVT_MENU(self, cmi, self.OnInsertIconAttribute)

            self.editorMenu.AppendMenu(wxNewId(), 'Add icon property', iconsMenu)

        # Build submenu for colors
        colorsMenu, self.cmdIdToColorName = PropertyHandling.buildColorsSubmenu()
        for cmi in self.cmdIdToColorName.keys():
            EVT_MENU(self, cmi, self.OnInsertColorAttribute)

        self.editorMenu.AppendMenu(wxNewId(), 'Add color property', colorsMenu)

        self.editorMenu.AppendSeparator()

        self.addMenuItem(self.editorMenu, '&Zoom In\t' + self.keyBindings.ZoomIn,
                'Zoom In', lambda evt: self.activeEditor.CmdKeyExecute(wxSTC_CMD_ZOOMIN),
                "tb_zoomin")

        self.addMenuItem(self.editorMenu, 'Zoo&m Out\t' + self.keyBindings.ZoomOut,
                'Zoom Out', lambda evt: self.activeEditor.CmdKeyExecute(wxSTC_CMD_ZOOMOUT),
                "tb_zoomout")


        self.editorMenu.AppendSeparator()

#         menuID=wxNewId()
#         formattingMenu.Append(menuID, '&Find\t', 'Find')
#         EVT_MENU(self, menuID, lambda evt: self.showFindDialog())

        menuID=wxNewId()
        self.editorMenu.Append(menuID, 'Find and &Replace\t' + self.keyBindings.FindAndReplace, 'Find and Replace')
        EVT_MENU(self, menuID, lambda evt: self.showFindReplaceDialog())

        menuID=wxNewId()
        self.editorMenu.Append(menuID, 'Rep&lace Text by WikiWord\t' + self.keyBindings.ReplaceTextByWikiword, 'Replace selected text by WikiWord')
        EVT_MENU(self, menuID, lambda evt: self.showReplaceTextByWikiwordDialog())

        self.editorMenu.AppendSeparator()

        menuID=wxNewId()
        self.editorMenu.Append(menuID, '&Rewrap Text\t' + self.keyBindings.RewrapText, 'Rewrap Text')
        EVT_MENU(self, menuID, lambda evt: self.activeEditor.rewrapText())

        menuID=wxNewId()
        wrapModeMenuItem = wxMenuItem(self.editorMenu, menuID, "&Wrap Mode", "Set wrap mode", wxITEM_CHECK)
        self.editorMenu.AppendItem(wrapModeMenuItem)
        EVT_MENU(self, menuID, self.OnCmdCheckWrapMode)

        wrapModeMenuItem.Check(self.getActiveEditor().getWrapMode())


        menuID=wxNewId()
        indentGuidesMenuItem = wxMenuItem(self.editorMenu, menuID,
                "&View Indentation Guides", "View Indentation Guides", wxITEM_CHECK)
        self.editorMenu.AppendItem(indentGuidesMenuItem)
        EVT_MENU(self, menuID, self.OnCmdCheckIndentationGuides)

        indentGuidesMenuItem.Check(self.getActiveEditor().GetIndentationGuides())


        menuID=wxNewId()
        autoIndentMenuItem = wxMenuItem(self.editorMenu, menuID,
                "Auto-indent", "Auto indentation", wxITEM_CHECK)
        self.editorMenu.AppendItem(autoIndentMenuItem)
        EVT_MENU(self, menuID, self.OnCmdCheckAutoIndent)

        autoIndentMenuItem.Check(self.getActiveEditor().getAutoIndent())


        menuID=wxNewId()
        autoBulletsMenuItem = wxMenuItem(self.editorMenu, menuID,
                "Auto-bullets", "Show bullet on next line if current has one",
                wxITEM_CHECK)
        self.editorMenu.AppendItem(autoBulletsMenuItem)
        EVT_MENU(self, menuID, self.OnCmdCheckAutoBullets)

        autoBulletsMenuItem.Check(self.getActiveEditor().getAutoBullets())


        menuID=wxNewId()
        showLineNumbersMenuItem = wxMenuItem(self.editorMenu, menuID,
                "Show line numbers", "Show line numbers",
                wxITEM_CHECK)
        self.editorMenu.AppendItem(showLineNumbersMenuItem)
        EVT_MENU(self, menuID, self.OnCmdCheckShowLineNumbers)

        showLineNumbersMenuItem.Check(self.getActiveEditor().getShowLineNumbers())

        self.editorMenu.AppendSeparator()


        evaluationMenu=wxMenu()

        self.addMenuItem(evaluationMenu, '&Eval\t' + self.keyBindings.Eval,
                'Eval Script Blocks',
                lambda evt: self.activeEditor.evalScriptBlocks())

        for i in xrange(1,7):
            self.addMenuItem(evaluationMenu, 'Eval Function &%i\tCtrl-%i' % (i, i),
                    'Eval Script Function %i' % i,
                    lambda evt, i=i: self.activeEditor.evalScriptBlocks(i))
                    
        self.editorMenu.AppendMenu(wxNewId(), "Evaluation", evaluationMenu,
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


        helpMenu=wxMenu()

        def openHelp(evt):
            try:
                clAction = CmdLineAction([])
                clAction.wikiToOpen = self.wikiPadHelp
                PersonalWikiFrame(None, -1, "WikidPad", self.wikiAppDir,
                        self.globalConfigDir, clAction)
                # os.startfile(self.wikiPadHelp)   # TODO!
            except Exception, e:
                traceback.print_exc()
                self.displayErrorMessage('Error while starting new '
                        'WikidPad instance', e)
                return

            # set the icon of the app
            try:
                self.wikiFrame.SetIcon(wxIcon(os.path.join(wikiAppDir, 'icons',
                        'pwiki.ico'), wxBITMAP_TYPE_ICO))
            except:
                pass


        menuID=wxNewId()
        helpMenu.Append(menuID, '&Open WikidPadHelp', 'Open WikidPadHelp')
        EVT_MENU(self, menuID, openHelp)

        helpMenu.AppendSeparator()

        menuID=wxNewId()
        helpMenu.Append(menuID, '&Visit wikidPad Homepage', 'Visit Homepage')
        EVT_MENU(self, menuID, lambda evt: os.startfile('http://www.jhorman.org/wikidPad/'))

        helpMenu.AppendSeparator()

        menuID=wxNewId()
        helpMenu.Append(menuID, 'View &License', 'View License')
        EVT_MENU(self, menuID, lambda evt: os.startfile(join(self.wikiAppDir, 'license.txt')))

        helpMenu.AppendSeparator()

        menuID=wxNewId()
        helpMenu.Append(menuID, '&About', 'About WikidPad')
        EVT_MENU(self, menuID, lambda evt: self.showAboutDialog())

        # get info for any plugin menu items and create them as necessary
        pluginMenu = None
        menuItems = reduce(lambda a, b: a+list(b),
                self.menuFunctions.describeMenuItems(self), [])
        if len(menuItems) > 0:
            pluginMenu = wxMenu()
                
            def addPluginMenuItem(function, label, statustext, icondesc=None,
                    menuID=None):
                self.addMenuItem(pluginMenu, label, statustext,
                        lambda evt: function(self, evt), icondesc, menuID)
            
            for item in menuItems:
                addPluginMenuItem(*item)


        self.mainmenu.Append(wikiMenu, 'W&iki')
        self.mainmenu.Append(wikiWordMenu, '&Wiki Words')
        self.mainmenu.Append(historyMenu, '&History')
        self.mainmenu.Append(self.editorMenu, '&Editor')
        if pluginMenu:
            self.mainmenu.Append(pluginMenu, "Pl&ugins")
        self.mainmenu.Append(helpMenu, 'He&lp')

        self.SetMenuBar(self.mainmenu)

        if self.wikiConfigFilename:  # If a wiki is open
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

        tb = self.CreateToolBar(wxTB_HORIZONTAL | wxNO_BORDER | wxTB_FLAT | wxTB_TEXT)
        seperator = self.lookupIcon("tb_seperator")

        icon = self.lookupIcon("tb_back")
        tbID = wxNewId()
        tb.AddSimpleTool(tbID, icon, "Back (Ctrl-Alt-Back)", "Back")
        EVT_TOOL(self, tbID, lambda evt: self.pageHistory.goInHistory(-1))

        icon = self.lookupIcon("tb_forward")
        tbID = wxNewId()
        tb.AddSimpleTool(tbID, icon, "Forward (Ctrl-Alt-Forward)", "Forward")
        EVT_TOOL(self, tbID, lambda evt: self.pageHistory.goInHistory(1))

        icon = self.lookupIcon("tb_home")
        tbID = wxNewId()
        tb.AddSimpleTool(tbID, icon, "Wiki Home", "Wiki Home")
        EVT_TOOL(self, tbID, lambda evt: self.openWikiPage(self.wikiName, forceTreeSyncFromRoot=True))

        icon = self.lookupIcon("tb_doc")
        tbID = wxNewId()
        tb.AddSimpleTool(tbID, icon, "Open Wiki Word  (Ctrl-O)", "Open Wiki Word")
        EVT_TOOL(self, tbID, lambda evt: self.showWikiWordOpenDialog())

        icon = self.lookupIcon("tb_lens")
        tbID = wxNewId()
        tb.AddSimpleTool(tbID, icon, "Search  (Ctrl-Alt-F)", "Search")
        EVT_TOOL(self, tbID, lambda evt: self.showSearchDialog())

        icon = self.lookupIcon("tb_cycle")
        tbID = wxNewId()
        tb.AddSimpleTool(tbID, icon, "Find current word in tree", "Find current word in tree")
        EVT_TOOL(self, tbID, lambda evt: self.findCurrentWordInTree())

        tb.AddSimpleTool(wxNewId(), seperator, "Separator", "Separator")

        icon = self.lookupIcon("tb_save")
        tb.AddSimpleTool(GUI_ID.CMD_SAVE_WIKI, icon, "Save Wiki Word (Ctrl-S)",
                "Save Wiki Word")
        EVT_TOOL(self, GUI_ID.CMD_SAVE_WIKI,
                lambda evt: (self.saveCurrentDocPage(force=True),
                self.getWikiData().commit()))

        icon = self.lookupIcon("tb_rename")
        tbID = wxNewId()
        tb.AddSimpleTool(tbID, icon, "Rename Wiki Word (Ctrl-Alt-R)", "Rename Wiki Word")
        EVT_TOOL(self, tbID, lambda evt: self.showWikiWordRenameDialog())

        icon = self.lookupIcon("tb_delete")
        tbID = wxNewId()
        tb.AddSimpleTool(tbID, icon, "Delete (Ctrl-D)", "Delete Wiki Word")
        EVT_TOOL(self, tbID, lambda evt: self.showWikiWordDeleteDialog())

        tb.AddSimpleTool(wxNewId(), seperator, "Separator", "Separator")

        icon = self.lookupIcon("tb_heading")
        tbID = wxNewId()
        tb.AddSimpleTool(tbID, icon, "Heading (Ctrl-Alt-H)", "Heading")
        EVT_TOOL(self, tbID, lambda evt: self.keyBindings.addHeading(self.activeEditor))

        icon = self.lookupIcon("tb_bold")
        tbID = wxNewId()
        tb.AddSimpleTool(tbID, icon, "Bold (Ctrl-B)", "Bold")
        EVT_TOOL(self, tbID, lambda evt: self.keyBindings.makeBold(self.activeEditor))

        icon = self.lookupIcon("tb_italic")
        tbID = wxNewId()
        tb.AddSimpleTool(tbID, icon, "Italic (Ctrl-I)", "Italic")
        EVT_TOOL(self, tbID, lambda evt: self.keyBindings.makeItalic(self.activeEditor))

        tb.AddSimpleTool(wxNewId(), seperator, "Separator", "Separator")

        icon = self.lookupIcon("tb_zoomin")
        tbID = wxNewId()
        tb.AddSimpleTool(tbID, icon, "Zoom In", "Zoom In")
        EVT_TOOL(self, tbID, lambda evt: self.activeEditor.CmdKeyExecute(wxSTC_CMD_ZOOMIN))

        icon = self.lookupIcon("tb_zoomout")
        tbID = wxNewId()
        tb.AddSimpleTool(tbID, icon, "Zoom Out", "Zoom Out")
        EVT_TOOL(self, tbID, lambda evt: self.activeEditor.CmdKeyExecute(wxSTC_CMD_ZOOMOUT))

        self.fastSearchField = wxTextCtrl(tb, GUI_ID.TF_FASTSEARCH,
                style=wxTE_PROCESS_ENTER | wxTE_RICH)
        tb.AddControl(self.fastSearchField)
#         EVT_TEXT_ENTER(self, GUI_ID.TF_FASTSEARCH, self.OnFastSearchEnter)
#         EVT_CHAR(self.fastSearchField, self.OnFastSearchChar)
        EVT_KEY_DOWN(self.fastSearchField, self.OnFastSearchKeyDown)
#         EVT_KEY_UP(self.fastSearchField, self.OnFastSearchChar)

        icon = self.lookupIcon("pin")
        tbID = wxNewId()
        tb.AddSimpleTool(tbID, icon, "Wikize Selected Word", "Wikize Selected Word")
        EVT_TOOL(self, tbID, lambda evt: self.keyBindings.makeWikiWord(self.activeEditor))



        # get info for any plugin toolbar items and create them as necessary
        toolbarItems = reduce(lambda a, b: a+list(b),
                self.toolbarFunctions.describeToolbarItems(self), [])
        
        def addPluginTool(function, tooltip, statustext, icondesc, tbID=None):
            if tbID is None:
                tbID = wxNewId()
                
            icon = self.resolveIconDescriptor(icondesc, self.lookupIcon(u"tb_doc"))
            # tb.AddLabelTool(tbID, label, icon, wxNullBitmap, 0, tooltip)
            tb.AddSimpleTool(tbID, icon, tooltip, statustext)
            EVT_TOOL(self, tbID, lambda evt: function(self, evt))
            
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

        # ------------------------------------------------------------------------------------
        # load the icons the program will use
        # ------------------------------------------------------------------------------------

        # add the gif handler for gif icon support
        wxImage_AddHandler(wxGIFHandler())
        ## create the image icon list
        # iconList = wxImageList(16, 16)
        # default icon is page.gif
        icons = ['page.gif']
        # add the rest of the icons
        icons.extend([file for file in os.listdir(join(self.wikiAppDir, "icons"))
                      if file.endswith('.gif') and file != 'page.gif'])

        self.iconFileList = icons

        # Create iconImageList
        self.fillIconLookupCache(True)


        # Build layout:

        self.windowLayouter = WindowLayouter(self, self.createWindow)
        
#         for pr in self._LAYOUT_DEFINITION:
#             self.windowLayouter.addWindowProps(pr)

        cfstr = self.getConfig().get("main", "windowLayout")
        self.windowLayouter.setWinPropsByConfig(cfstr)
       

#         print "initializeGui layout", repr(self.windowLayouter.getWinPropsForConfig())

        self.windowLayouter.realize()

#         self.viewsTree = self.windowLayouter.getWindowForName("viewstree")
        self.tree = self.windowLayouter.getWindowForName("maintree")
        self.logWindow = self.windowLayouter.getWindowForName("log")



#         # ------------------------------------------------------------------------------------
#         # Create the left-right splitter window.
#         # ------------------------------------------------------------------------------------
#         self.treeSashWindow = SmartSashLayoutWindow(self, GUI_ID.SASH_WINDOW_TREE,
#                 wxDefaultPosition, (200, 30), wxSW_3DSASH)
#         self.treeSashWindow.align(wxLAYOUT_LEFT)
#         self.treeSashWindow.setMinimalEffectiveSashPosition(10)
#         
#         pos = self.getConfig().getint("main", "splitter_pos", 170)
# 
#         self.treeSashWindow.setSashPosition(pos)
#         if pos < 50: pos = 170
#         self.treeSashWindow.setEffectiveSashPosition(pos)
# 
# 
#         self.viewsTreeSashWindow = SmartSashLayoutWindow(self.treeSashWindow, -1,
#                 wxDefaultPosition, (200, 30), wxSW_3DSASH)
#         self.viewsTreeSashWindow.align(wxLAYOUT_BOTTOM)
#         self.viewsTreeSashWindow.setMinimalEffectiveSashPosition(10)
#         self.viewsTreeSashWindow.setSashPosition(60)
#         
#         self.viewsTree = self.createWindow({"name": "viewstree"},
#                 self.viewsTreeSashWindow)
# 
# 
# #         self.vertSplitter = self.createWindow({"name":
# #                 "split(tree)(split(txteditor1)(log))"}, self)
# #         self.vertSplitter.SetMinimumPaneSize(1)
# 
#         # ------------------------------------------------------------------------------------
#         # Create the tree on the left.
#         # ------------------------------------------------------------------------------------
#         self.tree = self.createWindow({"name": "maintree"}, self.treeSashWindow)
# 
#         EVT_SIZE(self.treeSashWindow, lambda evt: wxLayoutAlgorithm().LayoutWindow(
#                 self.treeSashWindow, self.tree))
# 
# 
#         self.logSashWindow = SmartSashLayoutWindow(self, GUI_ID.SASH_WINDOW_LOG,
#                 wxDefaultPosition, (200, 30), wxSW_3DSASH)  # wxNO_BORDER|wxSW_3D
#         self.logSashWindow.align(wxLAYOUT_BOTTOM)
#         self.logSashWindow.setMinimalEffectiveSashPosition(10)
#         
#         self.logSashWindow.setEffectiveSashPosition(self.configuration.getint(
#                 "main", "log_window_effectiveSashPos", 120))
#         self.logSashWindow.setSashPosition(self.configuration.getint(
#                 "main", "log_window_sashPos", 1))
# #         self.logSashWindow.SetDefaultSize((1000, 120))
# #         self.logSashWindow.SetOrientation(wxLAYOUT_HORIZONTAL)
# #         self.logSashWindow.SetAlignment(wxLAYOUT_BOTTOM)
# #         self.logSashWindow.SetSashVisible(wxSASH_TOP, True)
# 
#         self.logWindow = self.createWindow({"name": "log"},
#                 self.logSashWindow)


        # ------------------------------------------------------------------------------------
        # Create the editor
        # ------------------------------------------------------------------------------------
        ## self.createEditor()

#         self.mainAreaPanel = wxNotebook(self, -1)
#                 
#         self.activeEditor = self.createWindow({"name": "txteditor1"},
#                 self.mainAreaPanel)
#         self.mainAreaPanel.AddPage(self.activeEditor, u"Edit")
#         
#         self.htmlView = WikiHtmlView(self, self.mainAreaPanel, -1)
#         self.mainAreaPanel.AddPage(self.htmlView, u"Preview")
        

        EVT_NOTEBOOK_PAGE_CHANGED(self, self.mainAreaPanel.GetId(),
                self.OnNotebookPageChanged)
        EVT_SET_FOCUS(self.mainAreaPanel, self.OnNotebookFocused)



        # ------------------------------------------------------------------------------------
        # Create menu and toolbar
        # ------------------------------------------------------------------------------------
        
        self.buildMainMenu()
        if self.getConfig().getboolean("main", "toolbar_show", True):
            self.setShowToolbar(True)

        EVT_MENU(self, GUI_ID.CMD_SWITCH_FOCUS, self.OnSwitchFocus)

        # Add alternative accelerators for clipboard operations
        ACCS = [
            (wxACCEL_CTRL, WXK_INSERT, GUI_ID.CMD_CLIPBOARD_COPY),
            (wxACCEL_SHIFT, WXK_INSERT, GUI_ID.CMD_CLIPBOARD_PASTE),
            (wxACCEL_SHIFT, WXK_DELETE, GUI_ID.CMD_CLIPBOARD_CUT),
            (wxACCEL_NORMAL, WXK_F6, GUI_ID.CMD_SWITCH_FOCUS)
            ]

        self.SetAcceleratorTable(wxAcceleratorTable(ACCS))

        # ------------------------------------------------------------------------------------
        # Create the status bar
        # ------------------------------------------------------------------------------------
        self.statusBar = wxStatusBar(self, -1)
        self.statusBar.SetFieldsCount(3)

        # Measure necessary widths of status fields
        dc = wxClientDC(self.statusBar)
        try:
            dc.SetFont(self.statusBar.GetFont())
            posWidth = dc.GetTextExtent(
                    u"Line: 9999 Col: 9999 Pos: 9999999988888")[0]
            dc.SetFont(wxNullFont)
        finally:
            del dc
            
        
        # Check if window should stay on top
        self.setStayOnTop(self.getConfig().getboolean("main", "frame_stayOnTop",
                False))

        self.statusBar.SetStatusWidths([-1, -1, posWidth])
        self.SetStatusBar(self.statusBar)

        # Register the App IDLE handler
        EVT_IDLE(self, self.OnIdle)

        # Register the App close handler
        EVT_CLOSE(self, self.OnWikiExit)

        # Check resizing to layout sash windows
        EVT_SIZE(self, self.OnSize)

        EVT_ICONIZE(self, self.OnIconize)
        EVT_MAXIMIZE(self, self.OnMaximize)


    def OnUpdateTreeCtrlMenuItem(self, evt):
#         evt.Check(not self.treeSashWindow.isCollapsed())
        evt.Check(not self.windowLayouter.isWindowCollapsed("maintree"))
        
    def OnUpdateToolbarMenuItem(self, evt):
        evt.Check(not self.GetToolBar() is None)

    def OnUpdateStayOnTopMenuItem(self, evt):
        evt.Check(self.getStayOnTop())


    def OnSwitchFocus(self, evt):
        foc = wxWindow.FindFocus()
        mainAreaPanel = self.mainAreaPanel
        while foc != None:
            if foc == mainAreaPanel:
                self.tree.SetFocus()
                return
            
            foc = foc.GetParent()
            
        mainAreaPanel.SetFocus()


    def OnFastSearchKeyDown(self, evt):
        acc = keyDownToAccel(evt)
        if acc == (wxACCEL_NORMAL, WXK_RETURN) or \
                acc == (wxACCEL_NORMAL, WXK_NUMPAD_ENTER):
            text = guiToUni(self.fastSearchField.GetValue())
            tfHeight = self.fastSearchField.GetSize()[1]
            pos = self.fastSearchField.ClientToScreen((0, tfHeight))

            popup = FastSearchPopup(self, self, -1, pos=pos)
            popup.Show()
            popup.runSearchOnWiki(text)
        else:
            evt.Skip()

#     def OnFastSearchChar(self, evt):
#         print "OnFastSearchChar", repr(evt.GetUnicodeKey()), repr(evt.GetKeyCode())
#         evt.Skip()


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
                tree.AssignImageList(cloneImageList(self.iconImageList))
            except Exception, e:
                traceback.print_exc()
                self.displayErrorMessage('There was an error loading the icons '
                        'for the tree control.', e)
            if self.wikiConfigFilename is not None and winName == "viewstree":
                tree.setViewsAsRoot()
            return tree
        elif winName.startswith("txteditor"):
            editor = WikiTxtCtrl(self, parent, -1)
            editor.evalScope = { 'editor' : editor,
                    'pwiki' : self, 'lib': self.evalLib}
    
            # enable and zoom the editor
            editor.Enable(0)
            editor.SetZoom(self.configuration.getint("main", "zoom"))
            return editor
        elif winName == "log":
            return LogWindow(parent, -1, self)
        elif winName == "main area panel":  # TODO remove this hack
            self.mainAreaPanel = wxNotebook(parent, -1)
                    
            self.activeEditor = self.createWindow({"name": "txteditor1"},
                    self.mainAreaPanel)
            self.mainAreaPanel.AddPage(self.activeEditor, u"Edit")
            
            self.htmlView = WikiHtmlView(self, self.mainAreaPanel, -1)
            self.mainAreaPanel.AddPage(self.htmlView, u"Preview")
            
            return self.mainAreaPanel


    def appendLogMessage(self, msg):   # TODO make log window visible if necessary
        """
        Add message to log window, make log window visible if necessary
        """
        if self.configuration.getboolean("main", "log_window_autoshow"):
#             self.logSashWindow.uncollapseWindow()
            self.windowLayouter.uncollapseWindow("log")
        self.logWindow.appendMessage(msg)

    def hideLogWindow(self):
#         self.logSashWindow.collapseWindow()
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


        for k in self.iconLookupCache.keys():
            self.iconLookupCache[k] = (self.iconLookupCache[k][0], None)

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

#     def testIt(self):

    def OnNotebookPageChanged(self, evt):
        if evt.GetSelection() == 0:
            self.activeEditor.SetFocus()
        elif evt.GetSelection() == 1:
            self.htmlView.SetFocus()

        self.htmlView.setVisible(evt.GetSelection() == 1)  # TODO

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


#     def createEditor(self):
#         self.activeEditor = WikiTxtCtrl(self, self.mainAreaPanel, -1)
#         self.mainAreaPanel.AddPage(self.activeEditor, u"Edit")
#         self.activeEditor.evalScope = { 'editor' : self.activeEditor,
#                 'pwiki' : self, 'lib': self.evalLib}
# 
#         # enable and zoom the editor
#         self.activeEditor.Enable(0)
#         self.activeEditor.SetZoom(self.configuration.getint("main", "zoom"))




    def resetGui(self):
        # delete everything in the current tree
        self.tree.DeleteAllItems()

        # reset the editor
        self.activeEditor.loadWikiPage(None)
        self.activeEditor.SetSelection(-1, -1)
        self.activeEditor.EmptyUndoBuffer()
        self.activeEditor.Disable()

        # reset tray
        self.setShowOnTray()

    def getCurrentText(self):
        """
        Return the raw input text of current wiki word
        """
        return self.activeEditor.GetText()


    def newWiki(self, wikiName, wikiDir):
        "creates a new wiki"
        wdhandlers = DbBackendUtils.listHandlers(self)
        if len(wdhandlers) == 0:
            self.displayErrorMessage(
                    'No data handler available to create database.')
            return

        self.hooks.newWiki(self, wikiName, wikiDir)

        wikiName = string.replace(wikiName, u" ", u"")
        wikiDir = join(wikiDir, wikiName)
        configFileLoc = join(wikiDir, u"%s.wiki" % wikiName)

#         self.statusBar.SetStatusText(uniToGui(u"Creating Wiki: %s" % wikiName), 0)

        createIt = True;
        if (exists(wikiDir)):
            dlg=wxMessageDialog(self,
                    uniToGui((u"A wiki already exists in '%s', overwrite? "
                    u"(This deletes everything in and below this directory!)") %
                    wikiDir), u'Warning', wxYES_NO)
            result = dlg.ShowModal()
            if result == wxID_YES:
                os.rmdir(wikiDir)  # TODO BUG!!!
                createIt = True
            elif result == wxID_NO:
                createIt = False
            dlg.Destroy()

        if createIt:
            # Ask for the data handler to use
            index = wxGetSingleChoiceIndex(u"Choose database type",
                    u"Choose database type", [wdh[1] for wdh in wdhandlers],
                    self)
            if index == -1:
                return

            wdhName = wdhandlers[index][0]
                
            wikiDataFactory, createWikiDbFunc = DbBackendUtils.getHandler(self, 
                    wdhName)
                    
            if wikiDataFactory is None:
                self.displayErrorMessage(
                        'Data handler %s not available' % wdh[0])
                return
            

            # create the new dir for the wiki
            os.mkdir(wikiDir)

            allIsWell = True

            dataDir = join(wikiDir, "data")

            # create the data directory for the data files
            try:
                createWikiDbFunc(wikiName, dataDir, False)
            except WikiDBExistsException:
                # The DB exists, should it be overwritten
                dlg=wxMessageDialog(self, u'A wiki database already exists '+
                        u'in this location, overwrite?',
                        u'Wiki DB Exists', wxYES_NO)
                result = dlg.ShowModal()
                if result == wxID_YES:
                    createWikiDbFunc(wikiName, dataDir, True)
                else:
                    allIsWell = False

                dlg.Destroy()
            except Exception, e:
                self.displayErrorMessage('There was an error creating the wiki database.', e)
                traceback.print_exc()                
                allIsWell = False

            if (allIsWell):
                # everything is ok, write out the config file
                # create a new config file for the new wiki
                self.configuration.createEmptyWikiConfig(configFileLoc)
                self.configuration.fillWikiWithDefaults()
                
                self.configuration.set("main", "wiki_name", wikiName)
                self.configuration.set("main", "last_wiki_word", wikiName)
                self.configuration.set("main", "wiki_database_type", wdhName)
                self.configuration.set("wiki_db", "data_dir", "data")
                self.configuration.save()

#                 configFile = open(configFileLoc, 'w')
#                 config.write(configFile)
#                 configFile.close()

#                 self.statusBar.SetStatusText(
#                         uniToGui(u"Created Wiki: %s" % wikiName), 0)

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
                
                self.activeEditor.GotoPos(self.activeEditor.GetLength())
                self.activeEditor.AddText(u"\n\n\t* WikiSettings\n")
                self.saveCurrentDocPage(force=True)
                
                # trigger hook
                self.hooks.createdWiki(self, wikiName, wikiDir)

                # reopen the root
                self.openWikiPage(self.wikiName, False, False)


    def openWiki(self, wikiConfigFilename, wikiWordToOpen=None,
            ignoreWdhName=False):
        """
        opens up a wiki
        ignoreWdhName -- Should the name of the wiki data handler in the
                wiki config file (if any) be ignored?
        """

        # trigger hooks
        self.hooks.openWiki(self, wikiConfigFilename)

        # Save the state of the currently open wiki, if there was one open
        # if the new config is the same as the old, don't resave state since
        # this could be a wiki overwrite from newWiki. We don't want to overwrite
        # the new config with the old one.

        # status
#         self.statusBar.SetStatusText(
#                 uniToGui(u"Opening Wiki: %s" % wikiConfigFilename), 0)

        # make sure the config exists
        if (not exists(wikiConfigFilename)):
            self.displayErrorMessage(u"Wiki configuration file '%s' not found" %
                    wikiConfigFilename)
            if wikiConfigFilename in self.wikiHistory:
                self.wikiHistory.remove(wikiConfigFilename)
            return False

#        if self.wikiConfigFilename != wikiConfigFilename:
        self.closeWiki()
#         self.buildMainMenu()   # ???

        # read in the config file
        # config = ConfigParser.ConfigParser()
        try:
            # config.read(wikiConfigFile)
            self.configuration.loadWikiConfig(wikiConfigFilename)
        except Exception, e:
            # try to recover by checking if the parent dir contains the real wiki file
            # if it does the current wiki file must be a wiki word file, so open the
            # real wiki to the wiki word.
            try:
                parentDir = dirname(dirname(wikiConfigFilename))
                if parentDir:
                    wikiFiles = [file for file in os.listdir(parentDir) \
                            if file.endswith(".wiki")]
                    if len(wikiFiles) > 0:
                        wikiWord = basename(wikiConfigFilename)
                        wikiWord = wikiWord[0:len(wikiWord)-5]

                        # if this is win95 or < the file name could be a 8.3 alias, file~1 for example
                        windows83Marker = wikiWord.find("~")
                        if windows83Marker != -1:
                            wikiWord = wikiWord[0:windows83Marker]
                            matchingFiles = [file for file in wikiFiles \
                                    if file.lower().startswith(wikiWord)]
                            if matchingFiles:
                                wikiWord = matchingFiles[0]
                        self.openWiki(join(parentDir, wikiFiles[0]), wikiWord)
                return
            except Exception, ne:
                traceback.print_exc()
                self.displayErrorMessage(u"Error reading config file '%s'" %
                        wikiConfigFilename, ne)
                return False

        # config variables
        wikiName = self.configuration.get("main", "wiki_name")
        dataDir = self.configuration.get("wiki_db", "data_dir")

        # except Exception, e:
        if wikiName is None or dataDir is None:
            self.displayErrorMessage("Wiki configuration file is corrupted", e)
            # traceback.print_exc()
            return False

        # absolutize the path to data dir if it's not already
        if not isabs(dataDir):
            dataDir = join(dirname(wikiConfigFilename), dataDir)

        # create the db interface to the wiki data
        wikiData = None
        try:
            if not ignoreWdhName:
                wikidhName = self.configuration.get("main",
                        "wiki_database_type", "")
            else:
                wikidhName = None
            if wikidhName:
                wikiDataFactory, createWikiDbFunc = DbBackendUtils.getHandler(self, 
                        wikidhName)
                if wikiDataFactory is None:
                    self.displayErrorMessage(
                            'Required data handler %s not available' % wikidhName)
                    wikidhName = None
            
            if not wikidhName:
                wdhandlers = DbBackendUtils.listHandlers(self)
                if len(wdhandlers) == 0:
                    self.displayErrorMessage(
                            'No data handler available to open database.')
                    return

                # Ask for the data handler to use
                index = wxGetSingleChoiceIndex(u"Choose database type",
                        u"Choose database type", [wdh[1] for wdh in wdhandlers],
                        self)
                if index == -1:
                    return
                    
                wikiDataFactory, createWikiDbFunc = DbBackendUtils.getHandler(self, 
                        wdhandlers[index][0])
                        
                if wikiDataFactory is None:
                    self.displayErrorMessage(
                            'Data handler %s not available' % wdh[0])
                    return

            wikiData = wikiDataFactory(self, dataDir)
        except Exception, e:
            self.displayErrorMessage("Error connecting to database in '%s'" % dataDir, e)
            traceback.print_exc()
            return False

        # what was the last wiki word opened
        lastWikiWord = wikiWordToOpen
        if not lastWikiWord:
            lastWikiWord = self.configuration.get("main", "first_wiki_word")
            if lastWikiWord == u"":
                lastWikiWord = self.configuration.get("main", "last_wiki_word")

        # OK, things look good

        # Reset some of the members
#         self.currentWikiWord = None
#         self.currentWikiPage = None

        # set the member variables.
        self.wikiConfigFilename = wikiConfigFilename
        ## self.wikiConfig = config
        self.wikiName = wikiName
        self.dataDir = dataDir
        self.wikiData = wikiData
        self.wikiDataManager = WikiDataManager(self, wikiData)

        # Set file storage according to configuration
        fs = self.getWikiDataManager().getFileStorage()
        
        fs.setModDateMustMatch(self.configuration.getboolean("main",
                "fileStorage_identity_modDateMustMatch", False))
        fs.setFilenameMustMatch(self.configuration.getboolean("main",
                "fileStorage_identity_filenameMustMatch", False))
        fs.setModDateIsEnough(self.configuration.getboolean("main",
                "fileStorage_identity_modDateIsEnough", False))

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

        self.tree.SetScrollPos(wxHORIZONTAL, 0)

        # enable the editor control whether or not the wiki root was found
        self.activeEditor.Enable(1)

        # update the last accessed wiki config var
        self.lastAccessedWiki(self.wikiConfigFilename)

        # Rebuild text blocks menu
        self.rereadTextBlocks()

        # trigger hook
        self.hooks.openedWiki(self, self.wikiName, wikiConfigFilename)

        # return that the wiki was opened successfully
        return True


    def setCurrentWordAsRoot(self):
        """
        Set current wiki word as root of the tree
        """
        # make sure the root has a relationship to the ScratchPad
        # self.currentWikiPage.addChildRelationship("ScratchPad")
        if self.getCurrentWikiWord() is not None:
            self.tree.setRootByWord(self.getCurrentWikiWord())


    def closeWiki(self, saveState=True):
        if self.wikiConfigFilename:
            if saveState:
                self.saveCurrentWikiState()
            if self.getWikiData():
                self.getWikiData().close()
                self.wikiData = None
                self.wikiDataManager = None
            self.wikiConfigFilename = None
            if self.clipboardCatcher is not None and \
                    self.clipboardCatcher.isActive():
                self.clipboardCatcher.stop()

            self.setShowOnTray()
            self.fireMiscEventKeys(("closed current wiki",))


    def saveCurrentWikiState(self):
        # write out the current config
        self.writeCurrentConfig()

        # save the current wiki page if it is dirty
        if self.getCurrentDocPage():
            self.saveCurrentDocPage()

        # database commits
        if self.getWikiData():
            self.getWikiData().commit()


    def openFuncPage(self, funcTag, **evtprops):
        page = self.wikiDataManager.getFuncPage(funcTag)

        self.activeEditor.loadFuncPage(page, evtprops)

        p2 = evtprops.copy()
        p2.update({"loaded current functional page": True})
        # p2.update({"loaded current page": True})
        self.fireMiscEventProps(p2)        


    def openWikiPage(self, wikiWord, addToHistory=True,
            forceTreeSyncFromRoot=False, forceReopen=False, **evtprops):
        """
        Opens a wiki page in the active editor.
        """
                
        evtprops["addToHistory"] = addToHistory
        evtprops["forceTreeSyncFromRoot"] = forceTreeSyncFromRoot

#         self.statusBar.SetStatusText(uniToGui(u"Opening wiki word '%s'" %
#                 wikiWord), 0)

        # make sure this is a valid wiki word
        if not self.getFormatting().isNakedWikiWord(wikiWord):
            self.displayErrorMessage(u"'%s' is an invalid wiki word." % wikiWord)
            return

        # don't reopen the currently open page
        if (wikiWord == self.getCurrentWikiWord()) and not forceReopen:
            # self.tree.buildTreeForWord(self.currentWikiWord)  # TODO Needed?
            self.statusBar.SetStatusText(uniToGui(u"Wiki word '%s' already open" %
                    wikiWord), 0)
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

        self.activeEditor.loadWikiPage(page, evtprops)

        p2 = evtprops.copy()
        p2.update({"loaded current page": True})
        p2.update({"loaded current wiki page": True})
        self.fireMiscEventProps(p2)        

        # set the title and add the word to the history
        self.SetTitle(uniToGui(u"Wiki: %s - %s" %
                (self.wikiConfigFilename, self.getCurrentWikiWord())))

        self.configuration.set("main", "last_wiki_word", wikiWord)

        # sync the tree
        if forceTreeSyncFromRoot:
            self.findCurrentWordInTree()

        # trigger hook
        self.hooks.openedWikiWord(self, wikiWord)


    def saveCurrentDocPage(self, force = False):
        if force or self.getCurrentDocPage().getDirty()[0]:
            self.activeEditor.saveLoadedDocPage() # this calls in turn saveDocPage() below

        self.refreshPageStatus()


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



    def saveDocPage(self, page, text):
        """
        Save page unconditionally
        """
        if page is None:
            return False
        self.statusBar.PushStatusText(u"Saving page", 0)
        word = page.getWikiWord()
        if word is not None:
            # trigger hooks
            self.hooks.savingWikiWord(self, word)
        try:
            while True:
                try:
                    if word is not None:
                        # only for real wiki pages
                        page.save(self.activeEditor.cleanAutoGenAreas(text))
                        page.update(self.activeEditor.updateAutoGenAreas(text))   # ?
                        self.propertyChecker.checkPage(page,
                                self.activeEditor.getPageAst())

                        # trigger hooks
                        self.hooks.savedWikiWord(self, word)
                    else:
                        page.save(text)
                        page.update(text)
                        
                    return True
                except Exception, e:
                    if word is None:    # TODO !!!
                        word = u"---"
                    dlg = wxMessageDialog(self,
                            uniToGui((u'There was an error saving the contents of '
                            u'wiki page "%s".\n%s\n\nWould you like to try and '
                            u'save this document again?') % (word, e)),
                                        u'Error Saving!', wxYES_NO)
                    result = dlg.ShowModal()
                    dlg.Destroy()
                    traceback.print_exc()
                    if result == wxID_NO:
                        return False
        finally:
            self.statusBar.PopStatusText(0)


    def deleteCurrentWikiPage(self, **evtprops):
        if self.getCurrentWikiWord():
            # self.saveCurrentDocPage()
            if self.getWikiData().isDefinedWikiWord(self.getCurrentWikiWord()):
                self.getWikiData().deleteWord(self.getCurrentWikiWord())

                # trigger hooks
                self.hooks.deletedWikiWord(self, self.getCurrentWikiWord())
                
                p2 = evtprops.copy()
                p2["deleted page"] = True
                p2["wikiWord"] = self.getCurrentWikiWord()
                self.fireMiscEventProps(p2)

            self.pageHistory.goAfterDeletion()


    def renameCurrentWikiPage(self, toWikiWord, modifyText, **evtprops):
        """
        Renames current wiki word to toWikiWord.
        Returns True if renaming was done successful.
        
        modifyText -- Should the text of links to the renamed page be
                modified? This text replacement works unreliably
        """
        wikiWord = self.getCurrentWikiWord()
        if wikiWord is None:
            return False

        try:
            self.saveCurrentDocPage()
            self.getWikiDataManager().renameWikiWord(wikiWord, toWikiWord,
                    modifyText)

            # if the root was renamed we have a little more to do
            if wikiWord == self.wikiName:
                self.configuration.set("main", "wiki_name", toWikiWord)
                self.configuration.set("main", "last_wiki_word", toWikiWord)
                self.saveCurrentWikiState()
                self.configuration.loadWikiConfig(None)

                self.wikiHistory.remove(self.wikiConfigFilename)
                renamedConfigFile = join(dirname(self.wikiConfigFilename),
                        u"%s.wiki" % toWikiWord)
                os.rename(self.wikiConfigFilename, renamedConfigFile)
                self.openWiki(renamedConfigFile)

            self.getActiveEditor().loadWikiPage(None)

            # trigger hooks
            self.hooks.renamedWikiWord(self, wikiWord, toWikiWord)                
            # self.tree.collapse()
            p2 = evtprops.copy()
            p2["renamed page"] = True
            p2["oldWord"] = wikiWord
            p2["newWord"] = toWikiWord
            self.fireMiscEventProps(p2)

            self.openWikiPage(toWikiWord, forceTreeSyncFromRoot=False)
            # self.findCurrentWordInTree()
            return True
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
                abspath(join(dirname(self.wikiConfigFilename), relpath)))

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
                os.startfile(mbcsEnc(link2, "replace")[0])
            except Exception, e:
                traceback.print_exc()
                self.displayErrorMessage(u"Couldn't start file", e)
                return False

            return True
        elif self.configuration.getint(
                "main", "new_window_on_follow_wiki_url") == 0:
                    
            link2 = urllib.url2pathname(link2)
            link2 = link2.replace("wiki:", "")
            if exists(link2):
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
        dlg = ChooseWikiWordDialog(self, -1, words, motionType, title)
        dlg.CenterOnParent(wxBOTH)
        dlg.ShowModal()
        dlg.Destroy()


    def viewParents(self, ofWord):
        parents = self.getWikiData().getParentRelationships(ofWord)
        self.viewWordSelection(u"Parent nodes of '%s'" % ofWord, parents,
                "parent")


    def viewParentLess(self):
        parentLess = self.getWikiData().getParentlessWikiWords()
        self.viewWordSelection(u"Parentless nodes", parentLess,
                "random")


    def viewChildren(self, ofWord):
        children = self.getWikiData().getChildRelationships(ofWord)
        self.viewWordSelection(u"Child nodes of '%s'" % ofWord, children,
                "child")

    def viewBookmarks(self):
        bookmarked = self.getWikiData().getWordsWithPropertyValue(
                "bookmarked", u"true")
        self.viewWordSelection(u"Bookmarks", bookmarked,
                "random")

    def viewHistory(self, posDelta=0):
        hist = self.pageHistory.getHistory()
        histpos = self.pageHistory.getPosition()

        dlg = wxSingleChoiceDialog(self,
                                   u"History",
                                   u"History",
                                   hist,
                                   wxCHOICEDLG_STYLE|wxOK|wxCANCEL)
        
        historyLen = len(hist)
        position = histpos + posDelta - 1
        if (position < 0):
            position = 0
        elif (position >= historyLen):
            position = historyLen-1

        dlg.SetSelection(position)
        if dlg.ShowModal() == wxID_OK:
            self.pageHistory.goInHistory(dlg.GetSelection() - (histpos - 1))

        dlg.Destroy()


    def lastAccessedWiki(self, wikiConfigFilename):
        "writes to the global config the location of the last accessed wiki"
        # create a new config file for the new wiki
        self.configuration.set("main", "last_wiki", wikiConfigFilename)
        if wikiConfigFilename not in self.wikiHistory:
            self.wikiHistory.append(wikiConfigFilename)

            # only keep 5 items
            if len(self.wikiHistory) > 5:
                self.wikiHistory.pop(0)

            # add the item to the menu
            menuID=wxNewId()
            self.recentWikisMenu.Append(menuID, wikiConfigFilename)
            EVT_MENU(self, menuID, self.OnSelectRecentWiki)

        self.configuration.set("main", "last_active_dir", dirname(wikiConfigFilename))
        self.writeGlobalConfig()


    # Only needed for scripts
    def setAutoSave(self, onOrOff):
        self.autoSave = onOrOff
        self.configuration.set("main", "auto_save", self.autoSave)


    def setShowTreeControl(self, onOrOff):
#         if onOrOff:
#             self.treeSashWindow.uncollapseWindow()
#         else:
#             self.treeSashWindow.collapseWindow()
        if onOrOff:
            self.windowLayouter.uncollapseWindow("maintree")
        else:
            self.windowLayouter.collapseWindow("maintree")


    def setShowToolbar(self, onOrOff):
        """
        Control, if toolbar should be shown or not
        """
        self.getConfig().set("main", "toolbar_show", onOrOff)

        if onOrOff == (not self.GetToolBar() is None):
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
        return not not self.GetWindowStyleFlag() & wxSTAY_ON_TOP 

    def setStayOnTop(self, onOrOff):
        style = self.GetWindowStyleFlag()
        
        if onOrOff:
            style |= wxSTAY_ON_TOP
        else:
            style &= ~wxSTAY_ON_TOP
            
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
            if self.wikiConfigFilename:  # If a wiki is open
                tooltip = u"Wiki: %s" % self.wikiConfigFilename  # self.wikiName
            else:
                tooltip = u"Wikidpad"

            self.tbIcon.SetIcon(wxIcon(os.path.join(self.wikiAppDir, 'icons', 'pwiki.ico'),
                    wxBITMAP_TYPE_ICO), uniToGui(tooltip))
        else:
            if self.tbIcon is not None:
                if self.tbIcon.IsIconInstalled():
                    self.tbIcon.RemoveIcon()

                self.tbIcon.Destroy()
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
            w.Reparent(None)

        self.windowLayouter.cleanMainWindow()
        
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
                return window
                
            window = self.createWindow(winProps, parent)
            if window is not None:
                cachedWindows[winName] = window

            return window
        
        self.windowLayouter = WindowLayouter(self, cachedCreateWindow)

#         for pr in self._TEST_LAYOUT_DEFINITION:
#             self.windowLayouter.addWindowProps(pr)

        self.windowLayouter.setWinPropsByConfig(layoutCfStr)
        # Handle no size events while realizing layout
        self.Unbind(EVT_SIZE)
        
        self.windowLayouter.realize()

        # Destroy windows which weren't reused (have parent None)
        for n, w in cachedWindows.iteritems():
            if w.GetParent() is None:
                w.Destroy()

        self.windowLayouter.layout()

        EVT_SIZE(self, self.OnSize)

        self.tree = self.windowLayouter.getWindowForName("maintree")
        self.logWindow = self.windowLayouter.getWindowForName("log")


#     def getClipboardCatcher(self):
#         return self.clipboardCatcher is not None and \
#                 self.clipboardCatcher.isActive()

    def OnClipboardCatcherOff(self, evt):
        if self.clipboardCatcher.isActive():
            self.clipboardCatcher.stop()

    def OnClipboardCatcherAtPage(self, evt):
        self.clipboardCatcher.startAtPage(self.GetHandle(),
                self.getCurrentDocPage())

    def OnClipboardCatcherAtCursor(self, evt):
        self.clipboardCatcher.startAtCursor(self.GetHandle())


    def OnUpdateClipboardCatcher(self, evt):
        cc = self.clipboardCatcher
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
                        (self.clipboardCatcher.getWikiWord(),
                        self.keyBindings.CatchClipboardAtPage))
            else:
                evt.Check(False)
                evt.SetText("Clipboard Catcher at Page\t" +
                        self.keyBindings.CatchClipboardAtPage)

    def writeGlobalConfig(self):
        "writes out the global config file"
        try:
            self.configuration.save()
        except Exception, e:
            self.displayErrorMessage("Error saving global configuration", e)


    def writeCurrentConfig(self):
        "writes out the current config file"
        try:
            self.configuration.save()
        except Exception, e:
            self.displayErrorMessage("Error saving current configuration", e)


    def showWikiWordOpenDialog(self):
        dlg = OpenWikiWordDialog(self, -1)
        dlg.CenterOnParent(wxBOTH)
        if dlg.ShowModal() == wxID_OK:
            wikiWord = dlg.GetValue()
            if wikiWord:
                dlg.Destroy()
                self.openWikiPage(wikiWord, forceTreeSyncFromRoot=True)
                self.activeEditor.SetFocus()
        dlg.Destroy()


    def showWikiWordRenameDialog(self, wikiWord=None, toWikiWord=None):
        if self.getCurrentWikiWord() is None:
            self.displayErrorMessage(u"No real wiki word selected to rename")
            return

        dlg = wxTextEntryDialog(self, uniToGui(u"Rename '%s' to:" %
                self.getCurrentWikiWord()), u"Rename Wiki Word",
                self.getCurrentWikiWord(), wxOK | wxCANCEL)

        try:
            while dlg.ShowModal() == wxID_OK and \
                    not self.showWikiWordRenameConfirmDialog(
                            guiToUni(dlg.GetValue())):
                pass

        finally:
            dlg.Destroy()

    # TODO Unicode
    def showStoreVersionDialog(self):
        dlg = wxTextEntryDialog (self, u"Description:",
                                 u"Store new version", u"",
                                 wxOK | wxCANCEL)

        description = None
        if dlg.ShowModal() == wxID_OK:
            description = dlg.GetValue()
        dlg.Destroy()

        if not description is None:
            self.saveCurrentDocPage()
            self.getWikiData().storeVersion(description)


    def showDeleteAllVersionsDialog(self):
        result = wxMessageBox(u"Do you want to delete all stored versions?",
                u"Delete All Versions", wxYES_NO | wxNO_DEFAULT | wxICON_QUESTION, self)

        if result == wxYES:
            self.getWikiData().deleteVersioningData()


    def showSavedVersionsDialog(self):
        if not self.getWikiData().hasVersioningData():
            dlg=wxMessageDialog(self, u"This wiki does not contain any version information",
                    u'Retrieve version', wxOK)
            dlg.ShowModal()
            dlg.Destroy()
            return

        dlg = SavedVersionsDialog(self, -1)
        dlg.CenterOnParent(wxBOTH)

        version = None
        if dlg.ShowModal() == wxID_OK:
            version = dlg.GetValue()
        dlg.Destroy()

        if version:
            dlg=wxMessageDialog(self, u"This will overwrite current content if not stored as version. Continue?",
                    u'Retrieve version', wxYES_NO)
            if dlg.ShowModal() == wxID_YES:
                dlg.Destroy()
                self.saveCurrentDocPage()
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

        if self.getWikiData().isDefinedWikiWord(toWikiWord):
            self.displayErrorMessage(u"Cannot rename to '%s', word already exists" %
                    toWikiWord)
            return False
            
        result = wxMessageBox(u"Do you want to modify all links to the wiki word "
                u"'%s' renamed to '%s'?" % (wikiWord, toWikiWord),
                u'Rename Wiki Word', wxYES_NO | wxCANCEL, self)

        if result == wxYES or result == wxNO:
            try:
                self.renameCurrentWikiPage(toWikiWord, result == wxYES)
                return True
            except WikiDataException, e:
                traceback.print_exc()                
                self.displayErrorMessage(str(e))

#         dlg.Destroy()
        return False

    def showSearchDialog(self):
        if self.findDlg != None:
            return

        self.findDlg = SearchWikiDialog(self, -1)
        self.findDlg.CenterOnParent(wxBOTH)
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

        dlg=wxMessageDialog(self,
                uniToGui(u"Are you sure you want to delete wiki word '%s'?" % wikiWord),
                'Delete Wiki Word', wxYES_NO)
        result = dlg.ShowModal()
        if result == wxID_YES:
            self.saveCurrentDocPage()
            try:
                self.deleteCurrentWikiPage()
            except WikiDataException, e:
                self.displayErrorMessage(str(e))

        dlg.Destroy()


    def showFindReplaceDialog(self):
        if self.findDlg != None:
            return

        self.findDlg = SearchPageDialog(self, -1)
        self.findDlg.CenterOnParent(wxBOTH)
        self.findDlg.Show()


    def showReplaceTextByWikiwordDialog(self):
        if self.getCurrentWikiWord() is None:
            self.displayErrorMessage(u"No real wiki word to modify")
            return

        wikiWord = guiToUni(wxGetTextFromUser(u"Replace text by WikiWord:",
                u"Replace by Wiki Word", self.getCurrentWikiWord(), self))

        if wikiWord:
            wikiWord = wikiWordToLabel(wikiWord)
            if not self.getFormatting().isNakedWikiWord(wikiWord):
                self.displayErrorMessage(u"'%s' is an invalid wiki word" % wikiWord)
                return False

            if self.getWikiData().isDefinedWikiWord(wikiWord):
                self.displayErrorMessage(u"'%s' exists already" % wikiWord)
                        # TODO Allow retry or append/replace
                return False

            text = self.activeEditor.GetSelectedText()
            page = self.wikiDataManager.createWikiPage(wikiWord)
            self.activeEditor.ReplaceSelection(
                    self.getFormatting().normalizeWikiWord(wikiWord))
            # TODO Respect template property?
            title = DocPages.WikiPage.getWikiPageTitle(wikiWord)
            self.saveDocPage(page, u"++ %s\n\n%s" % (title, text))


    def showIconSelectDialog(self):
        dlg = IconSelectDialog(self, -1)
        dlg.CenterOnParent(wxBOTH)
        iconname = None
        if dlg.ShowModal() == wxID_OK:
            iconname = dlg.GetValue()

        dlg.Destroy()

        if iconname:
            self.insertAttribute("icon", iconname)

    def showDateformatDialog(self):
        fmt = self.configuration.get("main", "strftime")

        dlg = DateformatDialog(self, -1, self, deffmt = fmt)
        dlg.CenterOnParent(wxBOTH)
        dateformat = None

        if dlg.ShowModal() == wxID_OK:
            dateformat = dlg.GetValue()
        dlg.Destroy()

        if not dateformat is None:
            self.configuration.set("main", "strftime", dateformat)


    def showOptionsDialog(self):
        dlg = OptionsDialog(self, -1)
        dlg.CenterOnParent(wxBOTH)

        result = dlg.ShowModal()
        dlg.Destroy()

        if result == wxID_OK:
            # Perform operations to reset GUI parts after option changes
            self.autoSaveDelayAfterKeyPressed = self.configuration.getint(
                    "main", "auto_save_delay_key_pressed")
            self.autoSaveDelayAfterDirty = self.configuration.getint(
                    "main", "auto_save_delay_dirty")
            self.setShowOnTray()
            self.setHideUndefined()
            self.refreshPageStatus()
            
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
                self.changeLayoutByCf(layoutCfStr)

            self.fireMiscEventKeys(("options changed",))


    def OnCmdExportDialog(self, evt):
        self.saveCurrentDocPage()
        self.getWikiData().commit()

        dlg = ExportDialog(self, -1)
        dlg.CenterOnParent(wxBOTH)

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
        typ = evt.GetId()
        
        if typ != GUI_ID.MENU_EXPORT_WHOLE_AS_XML:
            # Export to dir
            dest = wxDirSelector(u"Select Export Directory", self.getLastActiveDir(),
            wxDD_DEFAULT_STYLE|wxDD_NEW_DIR_BUTTON, parent=self)
        else:
            # Export to file
            dest = wxFileSelector(u"Select Export File",
                    self.getLastActiveDir(),
                    default_filename = "", default_extension = "",
                    wildcard = u"XML files (*.xml)|*.xml|All files (*.*)|*",
                    flags=wxSAVE | wxOVERWRITE_PROMPT, parent=self)

        if dest:
            if typ in (GUI_ID.MENU_EXPORT_WHOLE_AS_PAGE,
                    GUI_ID.MENU_EXPORT_WHOLE_AS_PAGES,
                    GUI_ID.MENU_EXPORT_WHOLE_AS_XML,
                    GUI_ID.MENU_EXPORT_WHOLE_AS_RAW):
                wordList = self.getWikiData().getAllDefinedWikiPageNames()
                
            elif typ in (GUI_ID.MENU_EXPORT_SUB_AS_PAGE,
                    GUI_ID.MENU_EXPORT_SUB_AS_PAGES):
                if self.getCurrentWikiWord() is None:
                    self.pWiki.displayErrorMessage(
                            u"No real wiki word selected as root")
                    return
                wordList = self.getWikiData().getAllSubWords(
                        [self.getCurrentWikiWord()])
            else:
                if self.getCurrentWikiWord() is None:
                    self.pWiki.displayErrorMessage(
                            u"No real wiki word selected as root")
                    return

                wordList = (self.getCurrentWikiWord(),)

            expclass, exptype, addopt = self.EXPORT_PARAMS[typ]
            
            
            self.saveCurrentDocPage(force=True)
            self.getWikiData().commit()
            
            ob = expclass(self)
            if addopt is None:
                # Additional options not given -> take default provided by exporter
                addopt = ob.getAddOpt(None)

            ob.export(self.getWikiDataManager(), wordList, exptype, dest,
                    False, addopt)

            self.configuration.set("main", "last_active_dir", dest)


    def OnCmdImportDialog(self, evt):
        self.saveCurrentDocPage()
        self.getWikiData().commit()

        dlg = ImportDialog(self, -1, self)
        dlg.CenterOnParent(wxBOTH)

        result = dlg.ShowModal()
        dlg.Destroy()
        

    def showSpellCheckerDialog(self):
        if self.spellChkDlg != None:
            return
            
        self.spellChkDlg = SpellChecker.SpellCheckerDialog(self, -1, self)
        self.spellChkDlg.CenterOnParent(wxBOTH)
        self.spellChkDlg.Show()
        self.spellChkDlg.checkNext(startPos=0)


    def rebuildWiki(self, skipConfirm = False):
        if not skipConfirm:
            result = wxMessageBox(u"Are you sure you want to rebuild this wiki? "+
                    u"You may want to backup your data first!",
                    u'Rebuild wiki', wxYES_NO | wxYES_DEFAULT | wxICON_QUESTION, self)

        if skipConfirm or result == wxYES :
            try:
                progresshandler = wxGuiProgressHandler(u"Rebuilding wiki",
                        u"Rebuilding wiki", 0, self)
                self.getWikiDataManager().rebuildWiki(progresshandler)

                self.tree.collapse()

                # TODO Adapt for functional pages
                if self.getCurrentWikiWord() is not None:
                    self.openWikiPage(self.getCurrentWikiWord(),
                            forceTreeSyncFromRoot=True)
            except Exception, e:
                self.displayErrorMessage(u"Error rebuilding wiki", e)
                traceback.print_exc()


    def vacuumWiki(self):
        self.getWikiData().vacuum()


    def OnImportFromPagefiles(self, evt):
        dlg=wxMessageDialog(self, u"This could overwrite pages in the database. Continue?",
                            u"Import pagefiles", wxYES_NO)

        result = dlg.ShowModal()
        if result == wxID_YES:
            self.getWikiData().copyWikiFilesToDatabase()


    def insertAttribute(self, name, value):
        self.activeEditor.AppendText(u"\n\n[%s=%s]" % (name, value))
#         self.saveCurrentDocPage()   # TODO Remove or activate this line?

    def addText(self, text):
        """
        Add text to current active editor view
        """
        self.activeEditor.AddText(text)


    def appendText(self, text):
        """
        Append text to current active editor view
        """
        self.activeEditor.AppendText(text)

    def insertDate(self):
        # strftime can't handle unicode correctly, so conversion is needed
        mstr = mbcsEnc(self.configuration.get("main", "strftime"), "replace")[0]
        self.activeEditor.AddText(mbcsDec(strftime(mstr), "replace")[0])

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
            return guiToUni(wxGetTextFromUser(uniToGui(message),
                    uniToGui(title), uniToGui(additional), self))
        else:
            style = None
            if dlgtype == "o":
                style = wxOK
            elif dlgtype == "oc":
                style = wxOK | wxCANCEL
            elif dlgtype == "yn":
                style = wxYES_NO
            elif dlgtype == "ync":
                style = wxYES_NO | wxCANCEL
            
            if style is None:
                raise RuntimeError, "Unknown dialog type"

            result = wxMessageBox(uniToGui(message), uniToGui(title), style, self)
            
            if result == wxOK:
                return "ok"
            elif result == wxCANCEL:
                return "cancel"
            elif result == wxYES:
                return "yes"
            elif result == wxNO:
                return "no"
                
            raise RuntimeError, "Internal Error"

    def displayMessage(self, title, str):
        """pops up a dialog box,
        used by scripts only
        """
        dlg_m = wxMessageDialog(self, uniToGui(u"%s" % str), title, wxOK)
        dlg_m.ShowModal()
        dlg_m.Destroy()


    def displayErrorMessage(self, errorStr, e=u""):
        "pops up a error dialog box"
        dlg_m = wxMessageDialog(self, uniToGui(u"%s. %s." % (errorStr, e)), 'Error!', wxOK)
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


    # ----------------------------------------------------------------------------------------
    # Event handlers from here on out.
    # ----------------------------------------------------------------------------------------

    def OnWikiOpen(self, event):
        dlg = wxFileDialog(self, u"Choose a Wiki to open",
                self.getLastActiveDir(), "", "*.wiki", wxOPEN)
        if dlg.ShowModal() == wxID_OK:
            self.openWiki(mbcsDec(abspath(dlg.GetPath()), "replace")[0])
        dlg.Destroy()
        
    def OnWikiOpenAsType(self, event):
        dlg = wxFileDialog(self, u"Choose a Wiki to open",
                self.getLastActiveDir(), "", "*.wiki", wxOPEN)
        if dlg.ShowModal() == wxID_OK:
            self.openWiki(mbcsDec(abspath(dlg.GetPath()), "replace")[0],
                    ignoreWdhName=True)
        dlg.Destroy()
        
    def OnWikiNew(self, event):
        dlg = wxTextEntryDialog (self,
                u"Name for new wiki (must be in the form of a WikiWord):",
                u"Create New Wiki", u"MyWiki", wxOK | wxCANCEL)

        if dlg.ShowModal() == wxID_OK:
            wikiName = guiToUni(dlg.GetValue())
            wikiName = wikiWordToLabel(wikiName)

            # make sure this is a valid wiki word
            if wikiName.find(u' ') == -1 and \
                    self.getFormatting().isNakedWikiWord(wikiName):
                startDir = self.wikiConfigFilename
                if startDir is None:
                    startDir = self.getLastActiveDir()
                else:
                    startDir = dirname(dirname(startDir))

                dlg = wxDirDialog(self, u"Directory to store new wiki",
#                         self.getLastActiveDir(),
                        startDir,
                        style=wxDD_DEFAULT_STYLE|wxDD_NEW_DIR_BUTTON)
                if dlg.ShowModal() == wxID_OK:
                    try:
                        self.newWiki(wikiName, dlg.GetPath())
                    except IOError, e:
                        self.displayErrorMessage(u'There was an error while '+
                                'creating your new Wiki.', e)
            else:
                self.displayErrorMessage((u"'%s' is an invalid wiki word. "+
                u"There must be no spaces and mixed caps") % wikiName)

        dlg.Destroy()


    def OnSelectRecentWiki(self, event):
        recentItem = self.recentWikisMenu.FindItemById(event.GetId())
        if not self.openWiki(recentItem.GetText()):
            self.recentWikisMenu.Remove(event.GetId())


    def informWikiPageUpdate(self, wikiPage):
        # self.tree.buildTreeForWord(wikiPage.wikiWord)    # self.currentWikiWord)
        self.fireMiscEventProps({"updated current page props": None,
                "wikiPage": wikiPage})


    def OnIdle(self, evt):
        if not self.configuration.getboolean("main", "auto_save"):  # self.autoSave:
            return
        # check if the current wiki page needs to be saved
        if self.getCurrentDocPage():
            (saveDirtySince, updateDirtySince) = \
                    self.getCurrentDocPage().getDirtySince()
            if saveDirtySince is not None:
                currentTime = time()
                # only try and save if the user stops typing
                if (currentTime - self.activeEditor.lastKeyPressed) > \
                        self.autoSaveDelayAfterKeyPressed:
#                     if saveDirty:
                    if (currentTime - saveDirtySince) > \
                            self.autoSaveDelayAfterDirty:
                        self.saveCurrentDocPage()
                        self.getWikiData().commit()
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


    def OnWikiExit(self, evt):
        # Stop clipboard catcher if running
        if self.clipboardCatcher is not None and self.clipboardCatcher.isActive():
            self.clipboardCatcher.stop()

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

#         splitterPos = self.treeSashWindow.getSashPosition()
# 
#         self.configuration.set("main", "splitter_pos", splitterPos)
# 
#         self.configuration.set("main", "log_window_effectiveSashPos",
#                 self.logSashWindow.getEffectiveSashPosition())
#         self.configuration.set("main", "log_window_sashPos",
#                 self.logSashWindow.getSashPosition())

        layoutCfStr = self.windowLayouter.getWinPropsForConfig()
        self.configuration.set("main", "windowLayout", layoutCfStr)

        self.configuration.set("main", "frame_stayOnTop", self.getStayOnTop())
        self.configuration.set("main", "zoom", self.activeEditor.GetZoom())
        self.configuration.set("main", "wiki_history", ";".join(self.wikiHistory))
        self.writeGlobalConfig()

        # save the current wiki state
        self.closeWiki()
#         self.saveCurrentWikiState()

        # trigger hook
        self.hooks.exit(self)

        wxTheClipboard.Flush()
        if self.getWikiData():
            self.getWikiData().close()
            self.wikiData = None
            self.wikiDataManager = None

        if self.tbIcon is not None:
            if self.tbIcon.IsIconInstalled():
                self.tbIcon.RemoveIcon()
                
            self.tbIcon.Destroy()
            self.tbIcon = None

        self.Destroy()


class TaskBarIcon(wxTaskBarIcon):
    def __init__(self, pwiki):
        wxTaskBarIcon.__init__(self)
        self.pwiki = pwiki

        # Register menu events
        EVT_MENU(self, GUI_ID.TBMENU_RESTORE, self.OnLeftUp)
        EVT_MENU(self, GUI_ID.TBMENU_SAVE, lambda evt: (self.pwiki.saveCurrentDocPage(force=True),
                self.pwiki.wikiData.commit()))
        EVT_MENU(self, GUI_ID.TBMENU_EXIT, lambda evt: self.pwiki.Close())

        EVT_TASKBAR_LEFT_UP(self, self.OnLeftUp)

    def OnLeftUp(self, evt):
        if self.pwiki.IsIconized():
            self.pwiki.Iconize(False)
            self.pwiki.Show(True)
            self.pwiki.Raise()

    def CreatePopupMenu(self):
        # Build menu
        tbMenu = wxMenu()
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



