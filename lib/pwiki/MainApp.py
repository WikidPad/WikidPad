## import hotshot
## _prof = hotshot.Profile("hotshot.prf")

import sys, os, traceback, os.path, socket

# To generate dependency for py2exe
import subprocess

import ExceptionLogger

import wx, wx.xrc

# import srePersistent
# srePersistent.loadCodeCache()

from wxHelper import IconCache
from Consts import CONFIG_FILENAME, CONFIG_GLOBALS_DIRNAME
from MiscEvent import KeyFunctionSink, MiscEventSourceMixin

from WikiExceptions import *
from Utilities import SingleThreadExecutor
from PersonalWikiFrame import PersonalWikiFrame
from StringOps import mbcsDec, createRandomString, pathEnc
from CmdLineAction import CmdLineAction
from Serialization import SerializeStream
import Ipc
import Configuration
import OptionsDialog
import Localization
from PluginManager import PluginManager, InsertionPluginManager



# For wx.GetOsVersion()
wxWINDOWS_NT = Configuration.wxWINDOWS_NT
wxWIN95 = Configuration.wxWIN95



def findDirs():
    """
    Returns tuple (wikiAppDir, globalConfigDir)
    """
    wikiAppDir = None
    
    isWindows = (wx.GetOsVersion()[0] == wxWIN95) or \
            (wx.GetOsVersion()[0] == wxWINDOWS_NT)

#     try:
    wikiAppDir = os.path.dirname(os.path.abspath(sys.argv[0]))
    if not wikiAppDir:
        wikiAppDir = r"C:\Program Files\WikidPad"
        
    globalConfigDir = None

    # This allows to keep the program with config on an USB stick
    if os.path.exists(pathEnc(os.path.join(wikiAppDir, CONFIG_FILENAME))):
        globalConfigDir = wikiAppDir
    elif os.path.exists(pathEnc(os.path.join(wikiAppDir, "." + CONFIG_FILENAME))):
        globalConfigDir = wikiAppDir
    else:
        globalConfigDir = os.environ.get("HOME")
        if not (globalConfigDir and os.path.exists(pathEnc(globalConfigDir))):
            # Instead of checking USERNAME, the user config dir. is
            # now used
            globalConfigDir = wx.StandardPaths.Get().GetUserConfigDir()
            # For Windows the user config dir is "...\Application data"
            # therefore we go down to "...\Application data\WikidPad"
            if os.path.exists(pathEnc(globalConfigDir)) and isWindows:
                try:
                    realGlobalConfigDir = os.path.join(globalConfigDir,
                            "WikidPad")
                    if not os.path.exists(pathEnc(realGlobalConfigDir)):
                        # If it doesn't exist, create the directory
                        os.mkdir(pathEnc(realGlobalConfigDir))

                    globalConfigDir = realGlobalConfigDir
                except:
                    traceback.print_exc()

#     finally:
#         pass

    if not globalConfigDir:
        globalConfigDir = wikiAppDir

    # mbcs decoding
    if wikiAppDir is not None:
        wikiAppDir = mbcsDec(wikiAppDir, "replace")[0]

    if globalConfigDir is not None:
        globalConfigDir = mbcsDec(globalConfigDir, "replace")[0]
        
    ExceptionLogger._exceptionDestDir = globalConfigDir

    return (wikiAppDir, globalConfigDir)



class App(wx.App, MiscEventSourceMixin): 
    def __init__(self, *args, **kwargs):
        global app
        app = self

        MiscEventSourceMixin.__init__(self)
        wx.App.__init__(self, *args, **kwargs)
        self.SetAppName("WikidPad")
        # Do not initialize member variables here!


    def OnInit(self):
        ## _prof.start()
#         global PREVIEW_CSS

        self.SetAppName("WikidPad")
        
        self._CallAfterId = wx.NewEventType()
        self.Connect(-1, -1, self._CallAfterId,
                    lambda event: event.callable(*event.args, **event.kw) )

        self.startupDummy = wx.Frame(None, -1, u"Dummy")
        self.dbExecutor = None  # SingleThreadExecutor()
        
        wx.CallAfter(self.OnInitDuringMain)

        return True



    def OnInitDuringMain(self):
        self.removeAppLockOnExit = False
        wx.EVT_END_SESSION(self, self.OnEndSession)
        appdir = os.path.dirname(os.path.abspath(sys.argv[0]))
        
        self.mainFrameSet = set()

        wikiAppDir, globalConfigDir = findDirs()

        if not globalConfigDir or not os.path.exists(globalConfigDir):
            raise Exception(_(u"Error initializing environment, couldn't locate "
                    u"global config directory"))
                    
        self.wikiAppDir = wikiAppDir
        self.globalConfigDir = globalConfigDir

        # Find/create global config subdirectory "WikidPadGlobals"
        if Configuration.isWindows():
            defaultGlobalConfigSubDir = os.path.join(self.globalConfigDir,
                    CONFIG_GLOBALS_DIRNAME)
        else:
            defaultGlobalConfigSubDir = os.path.join(self.globalConfigDir,
                    "." + CONFIG_GLOBALS_DIRNAME)

        self.globalConfigSubDir = os.path.join(self.globalConfigDir,
                CONFIG_GLOBALS_DIRNAME)
        if not os.path.exists(pathEnc(self.globalConfigSubDir)):
            self.globalConfigSubDir = os.path.join(self.globalConfigDir,
                    "." + CONFIG_GLOBALS_DIRNAME)
            if not os.path.exists(pathEnc(self.globalConfigSubDir)):
                self.globalConfigSubDir = defaultGlobalConfigSubDir
                os.mkdir(self.globalConfigSubDir)

#         pCssLoc = os.path.join(self.globalConfigSubDir, "wikipreview.css")
#         if not os.path.exists(pathEnc(pCssLoc)):
#             tbFile = open(pathEnc(pCssLoc), "w")
#             tbFile.write(PREVIEW_CSS)
#             tbFile.close()

        # Create default config dicts
        self.defaultGlobalConfigDict = Configuration.GLOBALDEFAULTS.copy()
        self.defaultWikiConfigDict = Configuration.WIKIDEFAULTS.copy()
        self.wikiConfigFallthroughDict = Configuration.WIKIFALLTHROUGH.copy()
        self.pageSearchHistory = []
        self.wikiSearchHistory = []
        
        self.optionsDlgPanelList = list(
                OptionsDialog.OptionsDialog.DEFAULT_PANEL_LIST)

        # load or create global configuration
        self.globalConfig = self.createGlobalConfiguration()

        # Find/create global config file "WikidPad.config"
        if Configuration.isWindows():
            defaultGlobalConfigLoc = os.path.join(self.globalConfigDir,
                    CONFIG_FILENAME)
        else:
            defaultGlobalConfigLoc = os.path.join(self.globalConfigDir,
                    "." + CONFIG_FILENAME)

        globalConfigLoc = os.path.join(self.globalConfigDir, CONFIG_FILENAME)
        if os.path.exists(pathEnc(globalConfigLoc)):
            try:
                self.globalConfig.loadConfig(globalConfigLoc)
            except Configuration.Error, MissingConfigurationFileException:
                self.createDefaultGlobalConfig(globalConfigLoc)
        else:
            globalConfigLoc = os.path.join(self.globalConfigDir,
                    "." + CONFIG_FILENAME)
            if os.path.exists(pathEnc(globalConfigLoc)):
                try:
                    self.globalConfig.loadConfig(globalConfigLoc)
                except Configuration.Error, MissingConfigurationFileException:
                    self.createDefaultGlobalConfig(globalConfigLoc)
            else:
                self.createDefaultGlobalConfig(defaultGlobalConfigLoc)
            
        self.globalConfig.getMiscEvent().addListener(KeyFunctionSink((
                ("changed configuration", self.onGlobalConfigurationChanged),
        )), False)
        
        ## _prof.start()
        Localization.loadLangList(self.wikiAppDir)
        
        Localization.loadI18nDict(self.wikiAppDir, self.globalConfig.get(
                "main", "gui_language", u""))

        if self.globalConfig.getboolean("main", "single_process"):
            # Single process mode means to create a server, detect an already
            # running server and, if there, just send the commandline to
            # the running server and quit then.            

            # We create a "password" so that no other user can send commands to this
            # WikidPad instance.
            appCookie = createRandomString(30)

            port = Ipc.createCommandServer(appCookie)

            # True if this is the single existing instance which should write
            # a new "AppLock.lock" file which either didn't exist or was invalid

            singleInstance = True

            # TODO maybe more secure method to ensure atomic exist. check and
            #   writing of file
            if os.path.exists(pathEnc(os.path.join(
                    self.globalConfigSubDir, "AppLock.lock"))):
                singleInstance = False
                # There seems to be(!) another instance already
                # TODO Try to send commandline
                f = open(pathEnc(os.path.join(
                        self.globalConfigSubDir, "AppLock.lock")), "r")
                appLockContent = f.read()
                f.close()
                
                lines = appLockContent.split("\n")
                if len(lines) != 3:
                    sys.stderr.write(_(u"Invalid AppLock.lock file\n"))
                    return True # TODO Error handling!!!

                appCookie = lines[0]
                remotePort = int(lines[1])

                if port != remotePort:
                    # Everything ok so far
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(10.0)
                    try:
                        try:
                            sock.connect(("127.0.0.1", remotePort))
                            greet = self._readSocketLine(sock)
                            if greet == "WikidPad_command_server 1.0":
                                sock.send("cmdline\n" + appCookie + "\n")
                                
                                ack = self._readSocketLine(sock)
                                if ack[0] == "+":
                                    # app cookie ok
                                    sst = SerializeStream(stringBuf="", readMode=False)
                                    sst.serArrString(sys.argv[1:])
                                    sock.send(sst.getBytes())
                                
                                    return True
    
                            # Reaching this point means something went wrong
                            singleInstance = True  # TODO More fine grained reaction
                        except socket.timeout, e:
                            singleInstance = True
                        except socket.error, e:
                            if (e.args[0] == 10061 or e.args[0] == 111):
                                # Connection refused (port not bound to a server)
                                singleInstance = True
                            else:
                                raise
                    finally:
                        sock.close()
    
                else:
                    # Sure indicator that AppLock file is invalid if newly
                    # created server opened a port which is claimed to be used
                    # already by previously started instance.
                    singleInstance = True
    
            if not singleInstance:
                return False

            if port != -1:
                # Server is connected, start it
                Ipc.startCommandServer()
    
                appLockContent = appCookie + "\n" + str(port) + "\n"
    
                f = open(pathEnc(os.path.join(
                        self.globalConfigSubDir, "AppLock.lock")), "w")
                f.write(appLockContent)
                f.close()
    
                self.removeAppLockOnExit = True
        
        # Build icon cache
        iconDir = os.path.join(self.wikiAppDir, "icons")
        self.iconCache = IconCache(iconDir)

        # Create plugin manager for application-wide plugins
        dirs = ( os.path.join(self.globalConfigSubDir, u'user_extensions'),
                os.path.join(self.wikiAppDir, u'user_extensions'),
                os.path.join(self.wikiAppDir, u'extensions') )
        self.pluginManager = PluginManager(dirs)

        # Register app-wide plugin APIs
        describeInsertionApi = self.pluginManager.registerPluginAPI(
                ("InsertionByKey", 1), ("describeInsertionKeys",))

        registerOptionsApi = self.pluginManager.registerPluginAPI(
                ("Options", 1), ("registerOptions",))

        describeWikiLanguageApi = self.pluginManager.registerPluginAPI(
                ("WikiParser", 1), ("describeWikiLanguage",))

        # Load plugins
#         dirs = ( os.path.join(self.wikiAppDir, u'user_extensions'),
#                 os.path.join(self.wikiAppDir, u'extensions') )

        self.pluginManager.loadPlugins([ u'KeyBindings.py',
                u'EvalLibrary.py'] )

        # Register options
        registerOptionsApi.registerOptions(1, self)

        # Retrieve descriptions for InsertionByKey
        insertionDescriptions = reduce(lambda a, b: a+list(b),
                describeInsertionApi.describeInsertionKeys(1, self), [])

        self.insertionPluginManager = InsertionPluginManager(
                insertionDescriptions)

        # Retrieve descriptions for InsertionByKey
        insertionDescriptions = reduce(lambda a, b: a+list(b),
                describeInsertionApi.describeInsertionKeys(1, self), [])

        self.insertionPluginManager = InsertionPluginManager(
                insertionDescriptions)

        wikiLanguageDescriptions = reduce(lambda a, b: a+list(b),
                describeWikiLanguageApi.describeWikiLanguage(1, self), [])

        self.wikiLanguageDescDict = dict(( (item[0], item)
                for item in wikiLanguageDescriptions ))

        self.collator = None

        # Further configuration settings
        self._rereadGlobalConfig()

        rd = Localization.getI18nXrcData(self.wikiAppDir,
                self.globalConfigSubDir, "WikidPad")
        ## _prof.stop()

#         # Load wxPython XML resources
#         rf = open(os.path.join(appdir, "WikidPad.xrc"), "r")
#         rd = rf.read()
#         rf.close()

        res = wx.xrc.XmlResource.Get()
        res.SetFlags(0)
#         rd = rd.decode("utf-8")
#         sys.stderr.write(repr(type(rd)) + "\n")
        res.LoadFromString(rd)

        # print "Set standardIcon"
        self.standardIcon = wx.Icon(os.path.join(self.wikiAppDir, 'icons',
                    'pwiki.ico'), wx.BITMAP_TYPE_ICO)

        self.startPersonalWikiFrame(CmdLineAction(sys.argv[1:]))

        self.startupDummy.Close()

        return True


    def _readSocketLine(self, sock):
        result = []
        read = 0
        while read < 300:
            c = sock.recv(1)
            if c == "\n" or c == "":
                return "".join(result)
            result.append(c)
            read += 1
            
        return ""


    def getWikiLanguageDescription(self, intLanguageName):
        """
        Returns the parser description tuple as provided by a WikiParser plugin
        or None if intLanguageName not found.
        """
        return self.wikiLanguageDescDict.get(intLanguageName)

    def listWikiLanguageDescriptions(self):
        """
        Return list of internal names of all available wiki languages
        """
        if self.wikiLanguageDescDict.has_key("wikidpad_default_2_0"):
            return [self.getWikiLanguageDescription("wikidpad_default_2_0")] + \
                    [l for l in self.wikiLanguageDescDict.values()
                    if l[0] != "wikidpad_default_2_0"]
        else:
            return self.wikiLanguageDescDict.values()


    def createWikiParser(self, intLanguageName, debugMode=False):
        """
        Must be thread-safe!
        """
        desc = self.getWikiLanguageDescription(intLanguageName)
        if desc is None:
            return None
        # Call parser factory function
        return desc[2](intLanguageName, debugMode)

    def freeWikiParser(self, parser):
        """
        Must be thread-safe, must accept None as parser!
        """
        pass
        
    def getUserDefaultWikiLanguage(self):
        """
        Returns the internal name of the default wiki language of the user.
        """
        # TODO! Configurable
        return "wikidpad_default_2_0"



    def createWikiLanguageHelper(self, intLanguageName, debugMode=False):
        """
        Must be thread-safe
        """
        desc = self.getWikiLanguageDescription(intLanguageName)
        if desc is None:
            return None
        # Call language helper factory function
        return desc[4](intLanguageName, debugMode)

    def freeWikiLanguageHelper(self, helper):
        """
        Must be thread-safe, must accept None as helper!
        """
        pass
        
    def getDbExecutor(self):
        return self.dbExecutor


    def onGlobalConfigurationChanged(self, miscevt):
        self._rereadGlobalConfig()
        

    def _rereadGlobalConfig(self):
        """
        Make settings from global config which are changeable during session
        """
        collationOrder = self.globalConfig.get("main", "collation_order")
        collationUppercaseFirst = self.globalConfig.getboolean("main",
                "collation_uppercaseFirst")
                
        if collationUppercaseFirst:
            collationCaseMode = Localization.CASEMODE_UPPER_FIRST
        else:
            collationCaseMode = Localization.CASEMODE_UPPER_INSIDE

        try:
            self.collator = Localization.getCollatorByString(collationOrder,
                    collationCaseMode)
        except:
            try:
                self.collator = Localization.getCollatorByString(u"Default",
                        collationCaseMode)
            except:
                self.collator = Localization.getCollatorByString(u"C",
                        collationCaseMode)


    def OnEndSession(self, evt):
        # Loop over copy of set as original set is modified during loop
        for wikiFrame in frozenset(self.mainFrameSet):
            wikiFrame.exitWiki()


    def OnExit(self):
        self.getInsertionPluginManager().taskEnd()

        if self.removeAppLockOnExit:
            try:
                os.remove(os.path.join(self.globalConfigSubDir, "AppLock.lock"))
            except:  # OSError, ex:
                traceback.print_exc()
                # TODO Error message!

        try:
            Ipc.stopCommandServer()
        except:
            traceback.print_exc()

        if ExceptionLogger._exceptionOccurred and hasattr(sys, 'frozen'):
            wx.MessageBox(_(u"An error occurred during this session\nSee file %s") %
                    os.path.join(ExceptionLogger._exceptionDestDir, "WikidPad_Error.log"),
                    "Error", style = wx.OK)


    def startPersonalWikiFrame(self, clAction):
        wikiFrame = PersonalWikiFrame(None, -1, "WikidPad", self.wikiAppDir,
                self.globalConfigDir, self.globalConfigSubDir, clAction)

        self.SetTopWindow(wikiFrame)
        self.mainFrameSet.add(wikiFrame)
        ## _prof.stop()

        # set the icon of the app
        try:
            # Method lookupIcon returns a wx.Bitmap
#             icon = wx.IconFromBitmap(self.iconCache.lookupIcon("boy"))
#             wikiFrame.SetIcon(icon)
#             wikiFrame.SetIcon(wx.Icon(os.path.join(self.wikiAppDir, 'icons',
#                     'pwiki.ico'), wx.BITMAP_TYPE_ICO))
            wikiFrame.SetIcon(self.standardIcon)
        except:
            pass


    def unregisterMainFrame(self, wikiFrame):
        self.mainFrameSet.discard(wikiFrame)


    def createDefaultGlobalConfig(self, globalConfigLoc):
        self.globalConfig.createEmptyConfig(globalConfigLoc)
        self.globalConfig.fillWithDefaults()

        wikidPadHelp = os.path.join(self.wikiAppDir, 'WikidPadHelp',
                'WikidPadHelp.wiki')

        self.globalConfig.set("main", "wiki_history", wikidPadHelp)
        self.globalConfig.set("main", "last_wiki", wikidPadHelp)

        self.globalConfig.set("main", "last_active_dir", os.getcwd())


    def getGlobalConfigSubDir(self):
        return self.globalConfigSubDir

    def getGlobalConfig(self):
        return self.globalConfig
        
    def getWikiAppDir(self):
        return self.wikiAppDir

    def getIconCache(self):
        """
        Return the icon cache object
        """
        return self.iconCache

    def getCollator(self):
        return self.collator

    def getInsertionPluginManager(self):
        return self.insertionPluginManager
        
    def getPageSearchHistory(self):
        return self.pageSearchHistory
        
    def setPageSearchHistory(self, hist):
        self.pageSearchHistory = hist


    def getWikiSearchHistory(self):
        return self.wikiSearchHistory

    def setWikiSearchHistory(self, hist):
        self.wikiSearchHistory = hist

    def createGlobalConfiguration(self):
        return Configuration.SingleConfiguration(
                self.getDefaultGlobalConfigDict())

    def createWikiConfiguration(self):
        return Configuration.SingleConfiguration(
                self.getDefaultWikiConfigDict(), self.wikiConfigFallthroughDict)

    def createCombinedConfiguration(self):
        return Configuration.CombinedConfiguration(
                self.createGlobalConfiguration(), self.createWikiConfiguration())

    def getDefaultGlobalConfigDict(self):
        """
        Returns the dictionary of the global configuration defaults.
        It is a copy of Configuration.GLOBALDEFAULTS.
        The dictionary can be manipulated by plugins to add further
        configuration options.
        """
        return self.defaultGlobalConfigDict

    def getDefaultWikiConfigDict(self):
        """
        Returns the dictionary of the wiki configuration defaults.
        It is a copy of Configuration.WIKIDEFAULTS.
        The dictionary can be manipulated by plugins to add further
        configuration options.
        """
        return self.defaultWikiConfigDict

    def getWikiConfigFallthroughDict(self):
        """
        Returns the dictionary of the wiki fallthrough settings.
        The fallthrough dict must only contain keys which are present
        as options in wiki config. and global config.        
        If the key in wiki config. has the equal value as the same key
        in the fallthrough dict, the combined configuration takes the
        key value from global config. instead.

        This is intended for wiki-bound options which can be set to
        "use default" mode to use the app-bound setting instead.

        It is a copy of Configuration.WIKIFALLTHROUGH.
        The dictionary can be manipulated by plugins to add further
        configuration options.
        """
        return self.wikiConfigFallthroughDict
        

    def getOptionsDlgPanelList(self):        
        return self.optionsDlgPanelList

    def addOptionsDlgPanel(self, factory, title):
        """
        factory -- Factory function (or class taking parameters
            (parent, optionsDlg, app) where
                parent: GUI parent of panel
                optionsDlg: OptionsDialog object
                app: MainApp object
        title -- unistring with title to show in the left list in options
            dialog
        """
        pl = self.getOptionsDlgPanelList()
        try:
            pl.index(("", u"Plugin options"))
        except ValueError:
            pl.append(("", u"Plugin options"))

        pl.append((factory, title))







# PREVIEW_CSS = """
# BODY {
# 	font-family: Verdana; font-size: 90%;
# }
# 
# .wiki-name-ref {
# 	color: #888888; font-size: 75%;
# }
# 
# .parent-nodes {
# 	color: #888888; font-size: 75%;
# }
# 
# .property {
# 	color: #888888; font-size: 75%;
# }
# 
# .script {
# 	color: #888888; font-size: 75%;
# }
# 
# .todo {
# 	font-weight: bold;
# }
# 
# .url-link {
# }
# 
# .wiki-link {
# }
# 
# .page-toc {
# }
# 
# .page-toc-level1 {
# }
# 
# .page-toc-level2 {
#     margin-left: 4mm;
# }
# 
# .page-toc-level3 {
#     margin-left: 8mm;
# }
# 
# .page-toc-level4 {
#     margin-left: 12mm;
# }
# 
# .page-toc-level5 {
#     margin-left: 16mm;
# }
# 
# .page-toc-level6 {
#     margin-left: 20mm;
# }
# 
# .page-toc-level7 {
#     margin-left: 24mm;
# }
# 
# .page-toc-level8 {
#     margin-left: 28mm;
# }
# 
# .page-toc-level9 {
#     margin-left: 32mm;
# }
# 
# .page-toc-level10 {
#     margin-left: 36mm;
# }
# 
# .page-toc-level11 {
#     margin-left: 40mm;
# }
# 
# .page-toc-level12 {
#     margin-left: 44mm;
# }
# 
# .page-toc-level13 {
#     margin-left: 48mm;
# }
# 
# .page-toc-level14 {
#     margin-left: 52mm;
# }
# 
# .page-toc-level15 {
#     margin-left: 56mm;
# }
# 
# """
