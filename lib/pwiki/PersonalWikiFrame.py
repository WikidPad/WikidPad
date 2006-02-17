
import os, gc, traceback, sets
from os.path import *
from time import localtime, time, strftime

from wxPython.wx import *
from wxPython.stc import *
from wxPython.html import *
from wxHelper import GUI_ID, setWindowPos, setWindowSize

from MiscEvent import MiscEventSourceMixin
import Configuration
from Configuration import createConfiguration
# from WikiData import *
from wikidata import DbBackendUtils
from wikidata.WikiDataManager import WikiDataManager

from WikiTxtCtrl import *
from WikiTreeCtrl import *
from WikiHtmlView import WikiHtmlView
from AboutDialog import AboutDialog

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
import WikiFormatting

from PluginManager import *
_COLORS = [
    "AQUAMARINE",
    "BLACK",
    "BLUE VIOLET",
    "BLUE",
    "BROWN",
    "CADET BLUE",
    "CORAL",
    "CORNFLOWER BLUE",
    "CYAN",
    "DARK GREEN",
    "DARK GREY",
    "DARK OLIVE GREEN",
    "DARK ORCHID",
    "DARK SLATE BLUE",
    "DARK SLATE GREY",
    "DARK TURQUOISE",
    "DIM GREY",
    "FIREBRICK",
    "FOREST GREEN",
    "GOLD",
    "GOLDENROD",
    "GREEN YELLOW",
    "GREEN",
    "GREY",
    "INDIAN RED",
    "KHAKI",
    "LIGHT BLUE",
    "LIGHT GREY",
    "LIGHT STEEL BLUE",
    "LIME GREEN",
    "MAGENTA",
    "MAROON",
    "MEDIUM AQUAMARINE",
    "MEDIUM BLUE",
    "MEDIUM FOREST GREEN",
    "MEDIUM GOLDENROD",
    "MEDIUM ORCHID",
    "MEDIUM SEA GREEN",
    "MEDIUM SLATE BLUE",
    "MEDIUM SPRING GREEN",
    "MEDIUM TURQUOISE",
    "MEDIUM VIOLET RED",
    "MIDNIGHT BLUE",
    "NAVY",
    "ORANGE RED",
    "ORANGE",
    "ORCHID",
    "PALE GREEN",
    "PINK",
    "PLUM",
    "PURPLE",
    "RED",
    "SALMON",
    "SEA GREEN",
    "SIENNA",
    "SKY BLUE",
    "SLATE BLUE",
    "SPRING GREEN",
    "STEEL BLUE",
    "TAN",
    "THISTLE",
    "TURQUOISE",
    "VIOLET RED",
    "VIOLET",
    "WHEAT",
    "WHITE",
    "YELLOW GREEN",
    "YELLOW"
]



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

        self.sleepMode = False  # Is program in low resource sleep mode?

        # Locate the global configuration directory containing the WikidPad.config file
#         self.wikiAppDir = None
# 
#         try:
#             self.wikiAppDir = dirname(abspath(sys.argv[0]))
#             if not self.wikiAppDir:
#                 self.wikiAppDir = r"C:\Program Files\WikidPad"
# 
#             homeDir = os.environ.get("HOME")
#             if homeDir and exists(homeDir):
#                 globalConfigDir = homeDir
#             else:
#                 user = os.environ.get("USERNAME")
#                 if user:
#                     homeDir = r"c:\Documents And Settings\%s" % user
#                     if homeDir and exists(homeDir):
#                         globalConfigDir = homeDir
#         except Exception, e:
#             self.displayErrorMessage(u"Error initializing environment", e)
# 
#         if not globalConfigDir:
#             globalConfigDir = self.wikiAppDir
# 
#         if not globalConfigDir or not exists(globalConfigDir):
#             globalConfigDir = "C:\Windows"


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
        self.configuration = createConfiguration()

        self.wikiPadHelp = join(self.wikiAppDir, 'WikidPadHelp',
                'WikidPadHelp.wiki')

        # defaults
        self.wikiData = None
        self.wikiDataManager = None
        self.wikiConfigFilename = None
#         self.currentWikiWord = None
#         self.currentWikiPage = None
        self.lastCursorPositionInPage = {}
        self.iconLookupCache = {}
        self.wikiHistory = []
        self.findDlg = None  # Stores find and find&replace dialog, if present
        self.mainmenu = None
        self.editorMenu = None  # "Editor" menu
        self.textBlocksActivation = {} # See self.buildTextBlocksMenu()
        # Position of the root menu of the text blocks within "Editor" menu
        self.textBlocksMenuPosition = None  

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

        # are indentationGuides enabled
        self.indentationGuides = self.configuration.getboolean("main", "indentation_guides")

#         # set the locale  # TODO Why?
#         locale = wxLocale()
#         self.locale = locale.GetCanonicalName()

        # get the default font for the editor
        self.defaultEditorFont = self.configuration.get("main", "font",
                self.presentationExt.faces["mono"])

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
        if self.vertSplitter.GetSashPosition() < 2:
            self.activeEditor.SetFocus()

        # display the window
        ## if not (self.showOnTray and self.IsIconized()):
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
            extFile = open(extensionFileName, "ra")
            userExtension = extFile.read()
            extFile.close()
        else:
            userExtension = None
            
        extensionFileName = join(self.wikiAppDir, 'extensions', fileName)
        extFile = open(extensionFileName, "ra")
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
        wikiPage = self.getCurrentWikiPage()
        if wikiPage is None:
            return None
        return wikiPage.getWikiWord()

    def getCurrentWikiPage(self):
        if self.activeEditor is None:
            return None
        return self.activeEditor.getLoadedWikiPage()
        
    def getActiveEditor(self):
        return self.activeEditor

    def getWikiData(self):
        return self.wikiData

    def getWikiDataManager(self):
        return self.wikiDataManager

    def getConfig(self):
        return self.configuration
        
    def getFormatting(self):
        return self.formatting


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


    def addMenuItem(self, menu, label, text, evtfct, icondesc=None, menuID=None):
        if menuID is None:
            menuID = wxNewId()

        menuitem = wxMenuItem(menu, menuID, label, text)
        # if icondesc:  # (not self.lowResources) and
        bitmap = self.resolveIconDescriptor(icondesc)
        if bitmap:
            menuitem.SetBitmap(bitmap)

        menu.AppendItem(menuitem)
        EVT_MENU(self, menuID, evtfct)
        return menuitem


    def buildWikiMenu(self):
        """
        Builds the first, the "Wiki" menu and returns it
        """
        wikiData = self.wikiData
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

        menuID=wxNewId()
        self.showTreeCtrlMenuItem = wxMenuItem(wikiMenu, menuID, "&Show Tree Control\t" + self.keyBindings.ShowTreeControl, "Show Tree Control", wxITEM_CHECK)
        wikiMenu.AppendItem(self.showTreeCtrlMenuItem)
        EVT_MENU(self, menuID, lambda evt: self.setShowTreeControl(self.showTreeCtrlMenuItem.IsChecked()))


        self.addMenuItem(wikiMenu, 'O&ptions',
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
                    'Open export dialog',
                    lambda evt: self.showExportDialog())


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

        # self.addMenuItem(wikiMenu, '&Test',
        #         'Test', lambda evt: self.testIt())

        menuID=wxNewId()
        wikiMenu.Append(menuID, 'E&xit', 'Exit')
        EVT_MENU(self, menuID, lambda evt: self.Close())
        
        return wikiMenu


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

        tbLoc = join(self.globalConfigSubDir, "[TextBlocks].wiki")
        try:
            tbFile = open(tbLoc, "rU")
            tbContent = tbFile.read()
            tbFile.close()
            tbContent = fileContentToUnicode(tbContent)
        except:
            tbContent = u""
        
        stack = [[0, u"Text blocks", wxMenu()]]

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
#                 self.Bind(wx.EVT_MENU, lambda evt, content=entryContent:
#                         self.appendText(content), id=menuID)

            menuItem = wxMenuItem(menu, menuID, entryTitle)
            menu.AppendItem(menuItem)

            self.textBlocksActivation[menuID] = (entryFlags, entryContent)

#             if u"a" in entryFlags:
#                 self.Bind(wx.EVT_MENU, lambda evt, content=entryContent:
#                         self.appendText(content), id=menuID)
#             else:
#                 self.Bind(wx.EVT_MENU, lambda evt, content=entryContent:
#                         self.addText(content), id=menuID)
#                 EVT_MENU(self, menuID, lambda evt, content=entryContent:
#                         self.addText(content))

        # Add the remaining ids so nothing gets lost
        for i in reusableIds:
            self.textBlocksActivation[i] = (None, None)

        # Finally empty stack
        while len(stack) > 1:
            title, menu = stack.pop()[1:3]
            if title is None:
                title = u"<No title>"
            
            stack[-1][2].AppendMenu(wxNewId(), title, menu)
            
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
                'Save Current Wiki Word', lambda evt: (self.saveCurrentWikiPage(force=True), self.wikiData.commit()),
                "tb_save")

        self.addMenuItem(wikiWordMenu, '&Rename\t' + self.keyBindings.Rename,
                'Rename Current Wiki Word', lambda evt: self.showWikiWordRenameDialog(),
                "tb_rename")

        self.addMenuItem(wikiWordMenu, '&Delete\t' + self.keyBindings.Delete,
                'Delete Wiki Word', lambda evt: self.showWikiWordDeleteDialog(),
                "tb_delete")

        self.addMenuItem(wikiWordMenu, 'Add Bookmark\t' + self.keyBindings.AddBookmark,
                'Add Bookmark to Page', lambda evt: self.insertAttribute("bookmarked", "true"),
                "pin")

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
                'Copy', lambda evt: self.activeEditor.Copy(),
                "tb_copy", menuID=GUI_ID.CMD_CLIPBOARD_COPY)

        self.addMenuItem(self.editorMenu, 'Copy to &ScratchPad\t' + self.keyBindings.CopyToScratchPad,
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

#         attributesMenu = wxMenu()
#         formattingMenu.AppendMenu(wxNewId(), 'Attributes', attributesMenu)
# 
#         menuID=wxNewId()
#         menuItem = wxMenuItem(attributesMenu, menuID, 'importance: high')
#         attributesMenu.AppendItem(menuItem)
#         EVT_MENU(self, menuID, lambda evt: self.insertAttribute('importance', 'high'))
# 
#         menuID=wxNewId()
#         menuItem = wxMenuItem(attributesMenu, menuID, 'importance: low')
#         attributesMenu.AppendItem(menuItem)
#         EVT_MENU(self, menuID, lambda evt: self.insertAttribute('importance', 'low'))
# 
#         menuID=wxNewId()
#         menuItem = wxMenuItem(attributesMenu, menuID, 'tree_position: 0')
#         attributesMenu.AppendItem(menuItem)
#         EVT_MENU(self, menuID, lambda evt: self.insertAttribute('tree_position', '0'))
# 
#         menuID=wxNewId()
#         menuItem = wxMenuItem(attributesMenu, menuID, 'wrap: 80')
#         attributesMenu.AppendItem(menuItem)
#         EVT_MENU(self, menuID, lambda evt: self.insertAttribute('wrap', '80'))
# 
#         self.addMenuItem(attributesMenu, 'camelCaseWordsEnabled: false', '',
#                 lambda evt: self.insertAttribute('camelCaseWordsEnabled', 'false'))


        # Build icon menu

        if self.lowResources:
            # Add only menu item for icon select dialog
            self.addMenuItem(self.editorMenu, 'Add icon property',
                    'Open icon select dialog', lambda evt: self.showIconSelectDialog())
        else:
            # Build full submenu for icons
            iconsMenu = wxMenu()
            self.editorMenu.AppendMenu(wxNewId(), 'Add icon property', iconsMenu)

            iconsMenu1 = wxMenu()
            iconsMenu.AppendMenu(wxNewId(), 'A-C', iconsMenu1)
            iconsMenu2 = wxMenu()
            iconsMenu.AppendMenu(wxNewId(), 'D-F', iconsMenu2)
            iconsMenu3 = wxMenu()
            iconsMenu.AppendMenu(wxNewId(), 'H-L', iconsMenu3)
            iconsMenu4 = wxMenu()
            iconsMenu.AppendMenu(wxNewId(), 'M-P', iconsMenu4)
            iconsMenu5 = wxMenu()
            iconsMenu.AppendMenu(wxNewId(), 'Q-S', iconsMenu5)
            iconsMenu6 = wxMenu()
            iconsMenu.AppendMenu(wxNewId(), 'T-Z', iconsMenu6)

            icons = self.iconLookupCache.keys();  # TODO: Create function?
            icons.sort()

            for id in icons:
                if id.startswith("tb_"):
                    continue
                iconsSubMenu = None
                if id[0] <= 'c':
                    iconsSubMenu = iconsMenu1
                elif id[0] <= 'f':
                    iconsSubMenu = iconsMenu2
                elif id[0] <= 'l':
                    iconsSubMenu = iconsMenu3
                elif id[0] <= 'p':
                    iconsSubMenu = iconsMenu4
                elif id[0] <= 's':
                    iconsSubMenu = iconsMenu5
                elif id[0] <= 'z':
                    iconsSubMenu = iconsMenu6

                menuID=wxNewId()
                menuItem = wxMenuItem(iconsSubMenu, menuID, id, id)
                bitmap = self.lookupIcon(id)
                menuItem.SetBitmap(bitmap)
                iconsSubMenu.AppendItem(menuItem)
                def insertIconAttribute(evt, iconId=id):
                    self.insertAttribute("icon", iconId)
                EVT_MENU(self, menuID, insertIconAttribute)

        colorsMenu = wxMenu()

        colorsMenu1 = wxMenu()
        colorsMenu.AppendMenu(wxNewId(), 'A-L', colorsMenu1)
        colorsMenu2 = wxMenu()
        colorsMenu.AppendMenu(wxNewId(), 'M-Z', colorsMenu2)

        for cn in _COLORS:    # ["BLACK"]:
            colorsSubMenu = None
            if cn[0] <= 'L':
                colorsSubMenu = colorsMenu1
            ## elif cn[0] <= 'Z':
            else:
                colorsSubMenu = colorsMenu2

            menuID=wxNewId()
            menuItem = wxMenuItem(colorsSubMenu, menuID, cn, cn)
            cl = wxNamedColour(cn)

            menuItem.SetBackgroundColour(cl)

            # if color is dark, text should be white (checking green component seems to be enough)
            ## light = (cl.Green() + cl.Red() + cl.Blue())/3
            if cl.Green() < 128:
                menuItem.SetTextColour(wxWHITE)

            colorsSubMenu.AppendItem(menuItem)
            def insertColorAttribute(evt, colorId=cn):
                self.insertAttribute("color", colorId)
            EVT_MENU(self, menuID, insertColorAttribute)

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
        EVT_MENU(self, menuID, lambda evt: self.setWrapMode(wrapModeMenuItem.IsChecked()))

        menuID=wxNewId()
        indentGuidesMenuItem = wxMenuItem(self.editorMenu, menuID, "&View Indentation Guides", "View Indentation Guides", wxITEM_CHECK)
        self.editorMenu.AppendItem(indentGuidesMenuItem)
        EVT_MENU(self, menuID, lambda evt: self.setIndentationGuides(indentGuidesMenuItem.IsChecked()))

        self.editorMenu.AppendSeparator()

        menuID=wxNewId()
        self.editorMenu.Append(menuID, '&Eval\t' + self.keyBindings.Eval, 'Eval Script Blocks')
        EVT_MENU(self, menuID, lambda evt: self.activeEditor.evalScriptBlocks())

        menuID=wxNewId()
        self.editorMenu.Append(menuID, 'Eval Function &1\tCtrl-1', 'Eval Script Function 1')
        EVT_MENU(self, menuID, lambda evt: self.activeEditor.evalScriptBlocks(1))

        menuID=wxNewId()
        self.editorMenu.Append(menuID, 'Eval Function &2\tCtrl-2', 'Eval Script Function 2')
        EVT_MENU(self, menuID, lambda evt: self.activeEditor.evalScriptBlocks(2))

        menuID=wxNewId()
        self.editorMenu.Append(menuID, 'Eval Function &3\tCtrl-3', 'Eval Script Function 3')
        EVT_MENU(self, menuID, lambda evt: self.activeEditor.evalScriptBlocks(3))

        menuID=wxNewId()
        self.editorMenu.Append(menuID, 'Eval Function &4\tCtrl-4', 'Eval Script Function 4')
        EVT_MENU(self, menuID, lambda evt: self.activeEditor.evalScriptBlocks(4))

        menuID=wxNewId()
        self.editorMenu.Append(menuID, 'Eval Function &5\tCtrl-5', 'Eval Script Function 5')
        EVT_MENU(self, menuID, lambda evt: self.activeEditor.evalScriptBlocks(5))

        menuID=wxNewId()
        self.editorMenu.Append(menuID, 'Eval Function &6\tCtrl-6', 'Eval Script Function 6')
        EVT_MENU(self, menuID, lambda evt: self.activeEditor.evalScriptBlocks(6))

        helpMenu=wxMenu()


        def openHelp(evt):
            os.startfile(self.wikiPadHelp)   # TODO!

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
        if self.wrapMode:
            wrapModeMenuItem.Check(1)

        # turn on or off auto-save
#         if self.autoSave:
#             autoSaveMenuItem.Check(1)

        # turn on or off indentation guides
        if self.indentationGuides:
            indentGuidesMenuItem.Check(1)


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
        tbID = wxNewId()
        tb.AddSimpleTool(tbID, icon, "Save Wiki Word (Ctrl-S)", "Save Wiki Word")
        EVT_TOOL(self, tbID, lambda evt: (self.saveCurrentWikiPage(force=True), self.wikiData.commit()))

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
        self.toolBar = tb


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

        self.buildMainMenu()
        self.buildToolbar()
        
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
        # Create the left-right splitter window.
        # ------------------------------------------------------------------------------------
        self.vertSplitter = wxSplitterWindow(self, -1, style=wxSP_NOBORDER)
        self.vertSplitter.SetMinimumPaneSize(1)

        # ------------------------------------------------------------------------------------
        # Create the tree on the left.
        # ------------------------------------------------------------------------------------
        self.tree = WikiTreeCtrl(self, self.vertSplitter, -1)

        # assign the image list
        try:
            self.tree.AssignImageList(self.iconImageList)
        except Exception, e:
            self.displayErrorMessage('There was an error loading the icons '+
                    'for the tree control.', e)
                    
                    
        self.mainAreaPanel = wxNotebook(self.vertSplitter, -1)# wxPanel(self.vertSplitter)
        # self.mainAreaPanelSizer = wxBoxSizer(wxVERTICAL)

        # ------------------------------------------------------------------------------------
        # Create the editor
        # ------------------------------------------------------------------------------------
        self.createEditor()
        
        self.htmlView = WikiHtmlView(self, self.mainAreaPanel, -1)
        
        self.mainAreaPanel.AddPage(self.htmlView, u"Preview")
        
        # self.mainAreaPanel.SetSizer(self.mainAreaPanelSizer)

        # ------------------------------------------------------------------------------------
        # Split the tree and the editor
        # ------------------------------------------------------------------------------------
        
        # self.vertSplitter.SplitVertically(self.tree, self.editor, self.lastSplitterPos)
        self.vertSplitter.SplitVertically(self.tree, self.mainAreaPanel, self.lastSplitterPos)

        EVT_NOTEBOOK_PAGE_CHANGED(self, self.mainAreaPanel.GetId(), self.OnNotebookPageChanged)
        EVT_SET_FOCUS(self.mainAreaPanel, self.OnNotebookFocused)

        # ------------------------------------------------------------------------------------
        # Create the status bar
        # ------------------------------------------------------------------------------------
        self.statusBar = wxStatusBar(self, -1)
        self.statusBar.SetFieldsCount(2)
        self.SetStatusBar(self.statusBar)

        # Register the App IDLE handler
        EVT_IDLE(self, self.OnIdle)

        # Register the App close handler
        EVT_CLOSE(self, self.OnWikiExit)

        EVT_ICONIZE(self, self.OnIconize)
        EVT_MAXIMIZE(self, self.OnMaximize)

        # turn on the tree control check box   # TODO: Doesn't work after restore from sleep mode
        ## if self.vertSplitter.GetSashPosition() > 1:
        if self.lastSplitterPos > 1:
            self.showTreeCtrlMenuItem.Check(1)
        else:
            self.tree.Hide()

    def OnSwitchFocus(self, evt):
        foc = wxWindow.FindFocus()
        mainAreaPanel = self.mainAreaPanel
        while foc != None:
            if foc == mainAreaPanel:
                self.tree.SetFocus()
                return
            
            foc = foc.GetParent()
            
        mainAreaPanel.SetFocus()


    def resourceSleep(self):
        """
        Free unnecessary resources if program is iconized
        """
        if self.sleepMode:
            return  # Already in sleep mode
        self.sleepMode = True

        self.toolBar.Destroy()

        self.SetMenuBar(None)
        self.showTreeCtrlMenuItem = None
        self.mainmenu.Destroy()

        # Set menu/menu items to None
        self.mainmenu = None
        self.recentWikisMenu = None
        self.showTreeCtrlMenuItem = None
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
        self.buildToolbar()
        self.setShowOnTray()


    def testIt(self):
        cb = wxTheClipboard
        cb.Open()
        # datob = wxTextDataObject()
        # datob = wxCustomDataObject(wxDataFormat(wxDF_TEXT))
        datob = wxCustomDataObject(wxDataFormat(wxDF_UNICODETEXT))


        print "Test getData", repr(cb.GetData(datob))
        print "Test text", repr(datob.GetData())       # GetDataHere())
        cb.Close()


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


    def createEditor(self):
        self.activeEditor = WikiTxtCtrl(self, self.mainAreaPanel, -1)
        self.mainAreaPanel.AddPage(self.activeEditor, u"Edit")
        self.activeEditor.evalScope = { 'editor' : self.activeEditor,
                'pwiki' : self, 'lib': self.evalLib}

        # enable and zoom the editor
        self.activeEditor.Enable(0)
        self.activeEditor.SetZoom(self.configuration.getint("main", "zoom"))

        # set the wrap mode of the editor
        self.setWrapMode(self.wrapMode)
        if self.indentationGuides:
            self.activeEditor.SetIndentationGuides(1)


    def resetGui(self):
        # delete everything in the current tree
        self.tree.DeleteAllItems()

        # reset the editor
        self.activeEditor.loadWikiPage(None, None)
        self.activeEditor.SetSelection(-1, -1)
        self.activeEditor.EmptyUndoBuffer()
        self.activeEditor.Disable()

        # reset tray
        self.setShowOnTray()
        
#         # reset menu and toolbar (capabilities of WikiData may have changed)
#         self.toolBar.Destroy()
#         
#         self.SetMenuBar(None)
# 
#         self.buildMainMenu()
#         self.buildToolbar()

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

        self.statusBar.SetStatusText(uniToGui(u"Creating Wiki: %s" % wikiName), 0)

        createIt = True;
        if (exists(wikiDir)):
            dlg=wxMessageDialog(self,
                    uniToGui((u"A wiki already exists in '%s', overwrite? "
                    u"(This deletes everything in and below this directory!)") %
                    wikiDir), u'Warning', wxYES_NO)
            result = dlg.ShowModal()
            if result == wxID_YES:
                os.rmdir(wikiDir)  # BUG!!!!!!!!!!!!!
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

                self.statusBar.SetStatusText(
                        uniToGui(u"Created Wiki: %s" % wikiName), 0)

                # open the new wiki
                self.openWiki(configFileLoc)
                p = self.wikiDataManager.createPage(u"WikiSettings")
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

                p = self.wikiDataManager.createPage(u"ScratchPad")
                text = u"++ Scratch Pad\n\n"
                p.save(text, False)
                p.update(text, False)
                
                self.activeEditor.GotoPos(self.activeEditor.GetLength())
                self.activeEditor.AddText(u"\n\n\t* WikiSettings\n")
                self.saveCurrentWikiPage(force=True)
                
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
        self.statusBar.SetStatusText(
                uniToGui(u"Opening Wiki: %s" % wikiConfigFilename), 0)

        # make sure the config exists
        if (not exists(wikiConfigFilename)):
            self.displayErrorMessage(u"Wiki configuration file '%s' not found" %
                    wikiConfigFilename)
            if wikiConfigFilename in self.wikiHistory:
                self.wikiHistory.remove(wikiConfigFilename)
            return False

#        if self.wikiConfigFilename != wikiConfigFilename:
        self.closeWiki()
        self.buildMainMenu()

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
                self.displayErrorMessage(u"Error reading config file '%s'" %
                        wikiConfigFilename, e)
                traceback.print_exc()
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

        # set status
        self.statusBar.SetStatusText(
                uniToGui(u"Opened wiki '%s'" % self.wikiName), 0)

        # now try and open the last wiki page
        if lastWikiWord and lastWikiWord != self.wikiName:
            # if the word is not a wiki word see if a word that starts with the word can be found
            if not self.wikiData.isDefinedWikiWord(lastWikiWord):
                wordsStartingWith = self.wikiData.getWikiWordsStartingWith(lastWikiWord, True)
                if wordsStartingWith:
                    lastWikiWord = wordsStartingWith[0]
            self.openWikiPage(lastWikiWord)
            self.findCurrentWordInTree()

        self.tree.SetScrollPos(wxHORIZONTAL, 0)

        # enable the editor control whether or not the wiki root was found
        self.activeEditor.Enable(1)

        # update the last accessed wiki config var
        self.lastAccessedWiki(self.wikiConfigFilename)

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
            if self.wikiData:
                self.wikiData.close()
                self.wikiData = None
                self.wikiDataManager = None
            self.wikiConfigFilename = None

            self.setShowOnTray()
            self.fireMiscEventKeys(("closed current wiki",))

    def saveCurrentWikiState(self):
        # write out the current config
        self.writeCurrentConfig()

        # save the current wiki page if it is dirty
        if self.getCurrentWikiPage():
            self.saveCurrentWikiPage()

        # database commits
        if self.getWikiData():
            self.getWikiData().commit()

    def openWikiPage(self, wikiWord, addToHistory=True,
            forceTreeSyncFromRoot=False, forceReopen=False, **evtprops):
                
        evtprops["addToHistory"] = addToHistory
        evtprops["forceTreeSyncFromRoot"] = forceTreeSyncFromRoot

        self.statusBar.SetStatusText(uniToGui(u"Opening wiki word '%s'" %
                wikiWord), 0)

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

        # save the current page if it is dirty
#         if self.getCurrentWikiPage():
#             self.saveCurrentWikiPage()
# 
#             # save the cursor position of the current page so that if
#             # the user comes back we can put the cursor in the right spot.
#             self.lastCursorPositionInPage[self.getCurrentWikiWord()] = \
#                     self.editor.GetCurrentPos()

        # trigger hook
        self.hooks.openWikiWord(self, wikiWord)

        # check if this is an alias
        if (self.wikiData.isAlias(wikiWord)):
            wikiWord = self.wikiData.getAliasesWikiWord(wikiWord)

#         # set the current wikiword
#         self.currentWikiWord = wikiWord

        # fetch the page info from the database
        try:
            page = self.wikiDataManager.getPage(wikiWord)
            self.statusBar.SetStatusText(uniToGui(u"Opened wiki word '%s'" %
                    self.getCurrentWikiWord()), 0)
        except (WikiWordNotFoundException, WikiFileNotFoundException), e:
            page = self.wikiDataManager.createPage(wikiWord)
            # trigger hooks
            self.hooks.newWikiWord(self, wikiWord)
            self.statusBar.SetStatusText(uniToGui(u"Wiki page not found, a new "
                    u"page will be created"), 0)


        self.activeEditor.loadWikiPage(page, evtprops)


#         # set the editor text
#         content = None
# 
#         try:
#             content = self.currentWikiPage.getContent()
#             self.statusBar.SetStatusText(uniToGui(u"Opened wiki word '%s'" %
#                     self.getCurrentWikiWord()), 0)
#         except WikiFileNotFoundException, e:
#             self.statusBar.SetStatusText(uniToGui(u"Wiki page not found, a new "
#                     u"page will be created"), 0)
# 
#             # Check if there is exactly one parent
#             parents = self.currentWikiPage.getParentRelationships()
#             if len(parents) == 1:
#                 # Check if there is a template page
#                 try:
#                     parentPage = self.wikiDataManager.getPage(parents[0])
#                     templateWord = parentPage.getPropertyOrGlobal("template")
#                     templatePage = self.wikiDataManager.getPage(templateWord)
#                     content = templatePage.getContent()
#                 except (WikiWordNotFoundException, WikiFileNotFoundException):
#                     pass
# 
#             if content is None:
#                 title = self.getWikiPageTitle(self.getCurrentWikiWord())
#                 content = u"++ %s\n\n" % title
# 
#             self.lastCursorPositionInPage[self.getCurrentWikiWord()] = len(content)
# 
#         # get the properties that need to be checked for options
#         pageProps = self.currentWikiPage.getProperties()
#         globalProps = self.wikiData.getGlobalProperties()
# 
#         # get the font that should be used in the editor
#         font = self.currentWikiPage.getPropertyOrGlobal("font",
#                 self.defaultEditorFont)
# 
#         # set the styles in the editor to the font
#         if self.lastEditorFont != font:         # TODO ??????
#             self.presentationExt.faces["mono"] = font
#             self.editor.SetStyles(self.presentationExt.faces)
#             self.lastEditorFont = font
#             
#         p2 = evtprops.copy()
#         p2.update({"loading current page": True})
#         self.fireMiscEventProps(p2)
# 
#         # now fill the text into the editor
#         self.editor.setTextAgaUpdated(content)
# 
#         # see if there is a saved position for this page
#         lastPos = self.lastCursorPositionInPage.get(wikiWord, 0)
#         self.editor.GotoPos(lastPos)
# 
#         # check if CamelCase should be used
#         # print "openWikiPage props", repr(pageProps), repr(globalProps)
#         wikiWordsEnabled = strToBool(self.currentWikiPage.getPropertyOrGlobal(
#                 "camelCaseWordsEnabled"), True)
# 
#         self.wikiWordsEnabled = wikiWordsEnabled
#         self.editor.wikiWordsEnabled = wikiWordsEnabled

        p2 = evtprops.copy()
        p2.update({"loaded current page": True})
        self.fireMiscEventProps(p2)        

        # set the title and add the word to the history
        self.SetTitle(uniToGui(u"Wiki: %s - %s" %
#                 (self.wikiName, self.getCurrentWikiWord())))
                (self.wikiConfigFilename, self.getCurrentWikiWord())))

        self.configuration.set("main", "last_wiki_word", wikiWord)

        # sync the tree
        if forceTreeSyncFromRoot:
            self.findCurrentWordInTree()

        # trigger hook
        self.hooks.openedWikiWord(self, wikiWord)


    def saveCurrentWikiPage(self, force = False):
        if force or self.getCurrentWikiPage().getDirty()[0]:
            self.activeEditor.saveLoadedWikiPage()
#             return self.saveWikiPage(self.getCurrentWikiWord(), self.currentWikiPage,
#                     self.activeEditor.GetText())
#         else:
#             return None

    def saveWikiPage(self, page, text):
        if page is None:
            return False
        self.statusBar.PushStatusText(u"Saving WikiPage", 0)
        word = page.getWikiWord()
        # trigger hooks
        self.hooks.savingWikiWord(self, word)
        try:
            while True:
                try:
                    page.save(self.activeEditor.cleanAutoGenAreas(text))
                    page.update(self.activeEditor.updateAutoGenAreas(text))   # ?
                    # trigger hooks
                    self.hooks.savedWikiWord(self, word)
                    return True
                except Exception, e:
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
            # self.saveCurrentWikiPage()
            self.wikiData.deleteWord(self.getCurrentWikiWord())

            # trigger hooks
            self.hooks.deletedWikiWord(self, self.getCurrentWikiWord())
            
            p2 = evtprops.copy()
            p2["deleted page"] = True
            p2["wikiWord"] = self.getCurrentWikiWord()
            self.fireMiscEventProps(p2)
            
            self.pageHistory.goAfterDeletion()
            
            
    def renameCurrentWikiPage(self, toWikiWord, **evtprops):
        """
        Renames current wiki word to toWikiWord.
        Returns True if renaming was done successful.
        """
        wikiWord = self.getCurrentWikiWord()
        if wikiWord is None:
            return False

        try:
            self.saveCurrentWikiPage()
            self.getWikiDataManager().renameWikiWord(wikiWord, toWikiWord)
#             self.getWikiData().renameWord(wikiWord, toWikiWord)
# 
#             # now we have to search the wiki files and replace the old word with the new
#             searchOp = SearchReplaceOperation()
#             searchOp.wikiWide = True
#             searchOp.wildCard = 'no'
#             searchOp.caseSensitive = True
#             searchOp.searchStr = wikiWord
#             
#             for resultWord in self.getWikiData().search(searchOp):
#                 page = self.getWikiDataManager().getPage(resultWord)
#                 content = page.getContent()
#                 content = content.replace(wikiWord, toWikiWord)
#                 page.save(content)
#                 page.update(content, False)  # TODO AGA processing
# 
# 
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

            self.currentWikiWord = toWikiWord
            self.currentWikiPage = None

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


    def launchUrl(self, link):
#         match = self.getFormatting().UrlRE.match(link)
#         try:
#             link2 = match.group(1)
            
        link2 = link
        if self.configuration.getint(
                "main", "new_window_on_follow_wiki_url") == 1 or \
                not link2.startswith("wiki:"):
            os.startfile(link2)
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
        parents = self.wikiData.getParentRelationships(ofWord)
        self.viewWordSelection(u"Parent nodes of '%s'" % ofWord, parents,
                "parent")


    def viewParentLess(self):
        parentLess = self.wikiData.getParentLessWords()
        self.viewWordSelection(u"Parentless nodes", parentLess,
                "random")


    def viewChildren(self, ofWord):
        children = self.wikiData.getChildRelationships(ofWord)
        self.viewWordSelection(u"Child nodes of '%s'" % ofWord, children,
                "child")

    def viewBookmarks(self):
        bookmarked = self.wikiData.getWordsWithPropertyValue(
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


#     def updateRelationships(self):
#         self.statusBar.SetStatusText(u"Updating relationships", 0)
#         self.currentWikiPage.update(self.activeEditor.GetText())
#         self.statusBar.SetStatusText(u"", 0)


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

    def setWrapMode(self, onOrOff):
        self.wrapMode = onOrOff
        self.configuration.set("main", "wrap_mode", self.wrapMode)
        self.activeEditor.setWrap(self.wrapMode)

    # Only needed for scripts
    def setAutoSave(self, onOrOff):
        self.autoSave = onOrOff
        self.configuration.set("main", "auto_save", self.autoSave)

    def setIndentationGuides(self, onOrOff):
        self.indentationGuides = onOrOff
        self.configuration.set("main", "indentation_guides", self.indentationGuides)
        if onOrOff:
            self.activeEditor.SetIndentationGuides(1)
        else:
            self.activeEditor.SetIndentationGuides(0)

    def setShowTreeControl(self, onOrOff):
        if onOrOff:
            if self.lastSplitterPos < 50:
                self.lastSplitterPos = 185
            self.vertSplitter.SetSashPosition(self.lastSplitterPos)
            self.tree.Show()
        else:
            self.lastSplitterPos = self.vertSplitter.GetSashPosition()
            self.vertSplitter.SetSashPosition(1)
            self.tree.Hide()


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


    # TODO: Rebuild tree
    def setHideUndefined(self, onOrOff=None):
        """
        Set if undefined WikiWords should be hidden in the tree
        """

        if not onOrOff is None:
            self.configuration.set("main", "hideundefined", onOrOff)
        else:
            onOrOff = self.configuration.getboolean("main", "hideundefined")


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
            self.pWiki.displayErrorMessage(u"No real wiki word selected to rename")
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
            self.saveCurrentWikiPage()
            self.wikiData.storeVersion(description)


    def showDeleteAllVersionsDialog(self):
        result = wxMessageBox(u"Do you want to delete all stored versions?",
                u"Delete All Versions", wxYES_NO | wxNO_DEFAULT | wxICON_QUESTION, self)

        if result == wxYES:
            self.wikiData.deleteVersioningData()


    def showSavedVersionsDialog(self):
        if not self.wikiData.hasVersioningData():
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
                self.saveCurrentWikiPage()
                word = self.getCurrentWikiWord()
                self.wikiData.applyStoredVersion(version[0])
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
            self.displayErrorMessage(u"'%s' is an invalid WikiWord" % toWikiWord)
            return False

        if wikiWord == toWikiWord:
            self.displayErrorMessage(u"Can't rename to itself")
            return False

        if wikiWord == "ScratchPad":
            self.displayErrorMessage(u"The scratch pad cannot be renamed.")
            return False

        if self.wikiData.isDefinedWikiWord(toWikiWord):
            self.displayErrorMessage(u"Cannot rename to '%s', word already exists" %
                    toWikiWord)
            return False

        dlg=wxMessageDialog(self, uniToGui((u"Are you sure you want to rename "+
                u"wiki word '%s' to '%s'?") % (wikiWord, toWikiWord)),
                u'Rename Wiki Word', wxYES_NO)
        renamed = False
        result = dlg.ShowModal()
        if result == wxID_YES:
            try:
                # self.saveCurrentWikiPage()
                renamed = self.renameCurrentWikiPage(toWikiWord)
#                 self.wikiData.renameWord(wikiWord, toWikiWord)
# 
#                 # if the root was renamed we have a little more to do
#                 if wikiWord == self.wikiName:
#                     self.configuration.set("main", "wiki_name", toWikiWord)
#                     self.configuration.set("main", "last_wiki_word", toWikiWord)
#                     self.saveCurrentWikiState()
#                     self.wikiHistory.remove(self.wikiConfigFilename)
#                     renamedConfigFile = join(dirname(self.wikiConfigFilename),
#                             u"%s.wiki" % toWikiWord)
#                     os.rename(self.wikiConfigFilename, renamedConfigFile)
#                     self.wikiConfigFilename = None
#                     self.openWiki(renamedConfigFile)
# 
#                 # trigger hooks
#                 self.hooks.renamedWikiWord(self, wikiWord, toWikiWord)                
#                 self.tree.collapse()
#                 self.openWikiPage(toWikiWord, forceTreeSyncFromRoot=True)
#                 self.findCurrentWordInTree()
#                 renamed = True
            except WikiDataException, e:
                traceback.print_exc()                
                self.displayErrorMessage(str(e))

        dlg.Destroy()
        return renamed

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
            self.saveCurrentWikiPage()
            try:
                self.deleteCurrentWikiPage()
#                 self.wikiData.deleteWord(wikiWord)
#                 # trigger hooks
#                 self.hooks.deletedWikiWord(self, wikiWord)
#                 if wikiWord == self.currentWikiWord:
#                     self.tree.collapse()
#                     if self.wikiWordHistory[self.historyPosition-1] != self.currentWikiWord:
#                         self.goInHistory(-1)
#                     else:
#                         self.openWikiPage(self.wikiName)
#                     self.findCurrentWordInTree()
            except WikiDataException, e:
                self.displayErrorMessage(str(e))

        dlg.Destroy()


#     def showFindDialog(self):
#         if self.findDlg is None:
#             data = wxFindReplaceData()
#         else:
#             return
# 
#         self.lastFindPos = -1
#         dlg = wxFindReplaceDialog(self, data, u"Find", wxFR_NOUPDOWN)
#         dlg.data = data
#         self.findDlg = dlg
#         dlg.Show(True)


    def showFindReplaceDialog(self):
        if self.findDlg != None:
            return

        self.findDlg = SearchPageDialog(self, -1)
        self.findDlg.CenterOnParent(wxBOTH)
        self.findDlg.Show()
        
    def showReplaceTextByWikiwordDialog(self):
        if self.getCurrentWikiWord() is None:
            self.pWiki.displayErrorMessage(u"No real wiki word to modify")
            return

        wikiWord = guiToUni(wxGetTextFromUser(u"Replace text by WikiWord:",
                u"Replace by Wiki Word", self.getCurrentWikiWord(), self))

        if wikiWord:
            wikiWord = wikiWordToLabel(wikiWord)
#             if not self.getFormatting().isWikiWord(wikiWord):
#                 wikiWord = u"[%s]" % wikiWord
            if not self.getFormatting().isNakedWikiWord(wikiWord):
                self.displayErrorMessage(u"'%s' is an invalid WikiWord" % wikiWord)
                return False

            if self.wikiData.isDefinedWikiWord(wikiWord):
                self.displayErrorMessage(u"'%s' exists already" % wikiWord)  # TODO Allow retry or append/replace
                return False

            text = self.activeEditor.GetSelectedText()
            page = self.wikiDataManager.createPage(wikiWord)
            self.activeEditor.ReplaceSelection(wikiWord)
            title = self.getWikiPageTitle(wikiWord)   # TODO Respect template property?
            self.saveWikiPage(page, u"++ %s\n\n%s" % (title, text))


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

        dlg = DateformatDialog(self, -1, deffmt = fmt)
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
            self.fireMiscEventKeys(("options changed",))


    def showExportDialog(self):
        self.saveCurrentWikiPage(force=True)
        self.wikiData.commit()

        dlg = ExportDialog(self, -1)
        dlg.CenterOnParent(wxBOTH)

        result = dlg.ShowModal()
        dlg.Destroy()

#         if result == wxID_OK:
#             pass


    EXPORT_PARAMS = {
            GUI_ID.MENU_EXPORT_WHOLE_AS_PAGE:
                    (Exporters.HtmlXmlExporter, u"html_single", ()),
            GUI_ID.MENU_EXPORT_WHOLE_AS_PAGES:
                    (Exporters.HtmlXmlExporter, u"html_multi", ()),
            GUI_ID.MENU_EXPORT_WORD_AS_PAGE:
                    (Exporters.HtmlXmlExporter, u"html_single", ()),
            GUI_ID.MENU_EXPORT_SUB_AS_PAGE:
                    (Exporters.HtmlXmlExporter, u"html_single", ()),
            GUI_ID.MENU_EXPORT_SUB_AS_PAGES:
                    (Exporters.HtmlXmlExporter, u"html_multi", ()),
            GUI_ID.MENU_EXPORT_WHOLE_AS_XML:
                    (Exporters.HtmlXmlExporter, u"xml", ()),
            GUI_ID.MENU_EXPORT_WHOLE_AS_RAW:
                    (Exporters.TextExporter, u"raw_files", (1,))
            }


    def OnExportWiki(self, evt):
        dest = wxDirSelector(u"Select Export Directory", self.getLastActiveDir(),
        wxDD_DEFAULT_STYLE|wxDD_NEW_DIR_BUTTON, parent=self)

        if dest:
            typ = evt.GetId()
            
            if typ in (GUI_ID.MENU_EXPORT_WHOLE_AS_PAGE,
                    GUI_ID.MENU_EXPORT_WHOLE_AS_PAGES,
                    GUI_ID.MENU_EXPORT_WHOLE_AS_XML,
                    GUI_ID.MENU_EXPORT_WHOLE_AS_RAW):
                wordList = self.wikiData.getAllDefinedPageNames()
                
            elif typ in (GUI_ID.MENU_EXPORT_SUB_AS_PAGE,
                    GUI_ID.MENU_EXPORT_SUB_AS_PAGES):
                if self.getCurrentWikiWord() is None:
                    self.pWiki.displayErrorMessage(
                            u"No real wiki word selected as root")
                    return
                wordList = self.wikiData.getAllSubWords([self.getCurrentWikiWord()])
            else:
                if self.getCurrentWikiWord() is None:
                    self.pWiki.displayErrorMessage(
                            u"No real wiki word selected as root")
                    return

                wordList = (self.getCurrentWikiWord(),)

            expclass, exptype, addopt = self.EXPORT_PARAMS[typ]
            
            self.saveCurrentWikiPage(force=True)
            self.wikiData.commit()
            
            expclass().export(self, self.getWikiDataManager(), wordList, exptype, dest,
                    False, addopt)

            self.configuration.set("main", "last_active_dir", dest)


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

#                 self.getWikiData().refreshDefinedPages()
# 
#                 # get all of the wikiWords
#                 wikiWords = self.getWikiData().getAllDefinedPageNames()
#                 
#                 progresshandler.open(len(wikiWords) + 1)
#                 try:
#                     step = 1
# 
#                     # re-save all of the pages
#                     self.getWikiData().clearCacheTables()
#                     for wikiWord in wikiWords:
#                         progresshandler.update(step, u"")   # , "Rebuilding %s" % wikiWord)
#                         wikiPage = self.getWikiDataManager().createPage(wikiWord)
#                         wikiPage.update(wikiPage.getContent(), False)  # TODO AGA processing
#                         step = step + 1
#     
#                 finally:            
#                     progresshandler.close()
#                     
# 
#                 # Give possibility to do further reorganisation
#                 # specific to database backend
#                 self.getWikiData().rebuildWiki(progresshandler)
                
#                 self.wikiData.rebuildWiki(
#                         wxGuiProgressHandler(u"Rebuilding wiki", u"Rebuilding wiki",
#                         0, self))

                self.tree.collapse()

                # TODO Adapt for functional pages
                if self.getCurrentWikiWord() is not None:
                    self.openWikiPage(self.getCurrentWikiWord(),
                            forceTreeSyncFromRoot=True)
            except Exception, e:
                self.displayErrorMessage(u"Error rebuilding wiki", e)
                traceback.print_exc()


    def vacuumWiki(self):
        self.wikiData.vacuum()


    def OnImportFromPagefiles(self, evt):
        dlg=wxMessageDialog(self, u"This could overwrite pages in the database. Continue?",
                            u"Import pagefiles", wxYES_NO)

        result = dlg.ShowModal()
        if result == wxID_YES:
            self.wikiData.copyWikiFilesToDatabase()


    def insertAttribute(self, name, value):
#         pos = self.editor.GetCurrentPos()
#         self.editor.GotoPos(self.editor.GetLength())
#         self.editor.AddText(u"\n\n[%s=%s]" % (name, value))
#         self.editor.GotoPos(pos)
        self.activeEditor.AppendText(u"\n\n[%s=%s]" % (name, value))
        self.saveCurrentWikiPage()

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

    def displayMessage(self, title, str):
        "pops up a dialog box"
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


    def getWikiPageTitle(self, wikiWord):
        title = re.sub(ur'([A-Z\xc0-\xde]{2,})([a-z\xdf-\xff])', r'\1 \2', wikiWord)
        title = re.sub(ur'([a-z\xdf-\xff])([A-Z\xc0-\xde])', r'\1 \2', title)
#         if title.startswith("["):
#             title = title[1:len(title)-1]
        return title


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
                dlg = wxDirDialog(self, u"Directory to store new wiki",
                        self.getLastActiveDir(),
                        style=wxDD_DEFAULT_STYLE|wxDD_NEW_DIR_BUTTON)
                if dlg.ShowModal() == wxID_OK:
                    try:
                        self.newWiki(wikiName, dlg.GetPath())
                    except IOError, e:
                        self.displayErrorMessage(u'There was an error while '+
                                'creating your new Wiki.', e)
            else:
                self.displayErrorMessage((u"'%s' is an invalid WikiWord. "+
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


    # TODO decouple save and update
    def OnIdle(self, evt):
        if not self.configuration.getboolean("main", "auto_save"):  # self.autoSave:
            return
        # check if the current wiki page needs to be saved
        if self.getCurrentWikiPage():
            (saveDirtySince, updateDirtySince) = \
                    self.getCurrentWikiPage().getDirtySince()
            if saveDirtySince is not None:
                currentTime = time()
                # only try and save if the user stops typing
                if (currentTime - self.activeEditor.lastKeyPressed) > \
                        self.autoSaveDelayAfterKeyPressed:
#                     if saveDirty:
                    if (currentTime - saveDirtySince) > \
                            self.autoSaveDelayAfterDirty:
                        self.saveCurrentWikiPage()
                        self.wikiData.commit()
#                     elif updateDirty:
#                         if (currentTime - self.currentWikiPage.lastUpdate) > 5:
#                             self.updateRelationships()


    def OnWikiExit(self, evt):
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

        splitterPos = self.vertSplitter.GetSashPosition()
        if splitterPos == 0:
            splitterPos = self.lastSplitterPos
        self.configuration.set("main", "splitter_pos", splitterPos)
        self.configuration.set("main", "zoom", self.activeEditor.GetZoom())
        self.configuration.set("main", "wiki_history", ";".join(self.wikiHistory))
        self.writeGlobalConfig()

        # save the current wiki state
        self.closeWiki()
#         self.saveCurrentWikiState()

        # trigger hook
        self.hooks.exit(self)

        wxTheClipboard.Flush()
        if self.wikiData:
            self.wikiData.close()

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
        EVT_MENU(self, GUI_ID.TBMENU_SAVE, lambda evt: (self.pwiki.saveCurrentWikiPage(force=True),
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



