## import hotshot
## _prof = hotshot.Profile("hotshot.prf")

import sys, os, traceback, os.path, socket
from functools import reduce

# To generate dependency for py2exe
if False:
    import subprocess, CustomListBox

import ExceptionLogger

import wx, wx.adv, wx.xrc

# import srePersistent
# srePersistent.loadCodeCache()

from Consts import CONFIG_FILENAME, CONFIG_GLOBALS_DIRNAME

from .MiscEvent import KeyFunctionSink, MiscEventSourceMixin

from .WikiExceptions import *
from . import Configuration
from .StringOps import mbcsDec, createRandomString, pathEnc, \
        writeEntireFile, loadEntireFile

from . import SystemInfo
from . import WindowLayout
from .CmdLineAction import CmdLineAction



# For wx.GetOsVersion()
wxWINDOWS_NT = SystemInfo.wxWINDOWS_NT
wxWIN95 = SystemInfo.wxWIN95



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
        
    ExceptionLogger.setLogDestDir(globalConfigDir)
    
    return (wikiAppDir, globalConfigDir)


_defRedirect = (wx.Platform == '__WXMSW__' or wx.Platform == '__WXMAC__')


class App(wx.App, MiscEventSourceMixin): 
    def __init__(self, *args, **kwargs):
        global app
        app = self
        
        # Hack for Windows to allow installation in non-ascii path
        sys.prefix = mbcsDec(sys.prefix)[0]

        MiscEventSourceMixin.__init__(self)

        wx.App.__init__(self, *args, **kwargs)
        self.SetAppName("WikidPad")
        # Do not initialize member variables here!


    def OnInit(self):
        ## _prof.start()
#         global PREVIEW_CSS

        self.SetAppName("WikidPad")

#         self._CallAfterId = wx.NewEventType()
#         self.Connect(-1, -1, self._CallAfterId,
#                     lambda event: event.callable(*event.args, **event.kw) )
# 
        self.sqliteInitFlag = False   # Read and modified only by WikiData classes
        
        WindowLayout.initiateAfterWxApp()
        self.removeAppLockOnExit = False
        self.Bind(wx.EVT_END_SESSION, self.OnEndSession)
        appdir = os.path.dirname(os.path.abspath(sys.argv[0]))
        
        self.mainFrameSet = set()

        wikiAppDir, globalConfigDir = findDirs()

        if not globalConfigDir or not os.path.exists(globalConfigDir):
            raise Exception(_("Error initializing environment, couldn't locate "
                    "global config directory"))
                    
        self.wikiAppDir = wikiAppDir
        self.globalConfigDir = globalConfigDir

        # Find/create global config subdirectory "WikidPadGlobals"
        if SystemInfo.isWindows():
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

        # load or create global configuration
        self.globalConfig = self.createGlobalConfiguration()

        # Find/create global config file "WikidPad.config"
        if SystemInfo.isWindows():
            defaultGlobalConfigLoc = os.path.join(self.globalConfigDir,
                    CONFIG_FILENAME)
        else:
            defaultGlobalConfigLoc = os.path.join(self.globalConfigDir,
                    "." + CONFIG_FILENAME)

        globalConfigLoc = os.path.join(self.globalConfigDir, CONFIG_FILENAME)
        if os.path.exists(pathEnc(globalConfigLoc)):
            try:
                self.globalConfig.loadConfig(globalConfigLoc)
            except Configuration.Error as MissingConfigurationFileException:
                self.createDefaultGlobalConfig(globalConfigLoc)
        else:
            globalConfigLoc = os.path.join(self.globalConfigDir,
                    "." + CONFIG_FILENAME)
            if os.path.exists(pathEnc(globalConfigLoc)):
                try:
                    self.globalConfig.loadConfig(globalConfigLoc)
                except Configuration.Error as MissingConfigurationFileException:
                    self.createDefaultGlobalConfig(globalConfigLoc)
            else:
                self.createDefaultGlobalConfig(defaultGlobalConfigLoc)

        splash = None
        
        cmdLine = CmdLineAction(sys.argv[1:])
        if not cmdLine.exitFinally and self.globalConfig.getboolean("main",
                "startup_splashScreen_show", True):
            bitmap = wx.Bitmap(os.path.join(appdir, "icons/pwiki.ico"))
            if bitmap:
                splash = wx.adv.SplashScreen(bitmap,
                      wx.adv.SPLASH_CENTRE_ON_SCREEN|wx.adv.SPLASH_TIMEOUT, 15000, None,
                      style=wx.BORDER_NONE|wx.FRAME_NO_TASKBAR)
                self.Yield()

        try:
            return self.initStep2(cmdLine)
        finally:
            if splash:
                splash.Destroy()


    def initStep2(self, cmdLine):
        # Block of modules to import while splash screen is shown
        from .wxHelper import IconCache, SimpleXmlSubclassFactory
        from .Serialization import SerializeStream
        from . import OsAbstract
        from . import Ipc
        from . import OptionsDialog, Localization

        self.optionsDlgPanelList = list(
                OptionsDialog.OptionsDialog.DEFAULT_PANEL_LIST)

        self.globalConfig.getMiscEvent().addListener(KeyFunctionSink((
                ("changed configuration", self.onChangedGlobalConfiguration),
        )), False)

        Localization.loadLangList(self.wikiAppDir)
        
        Localization.loadI18nDict(self.wikiAppDir, self.globalConfig.get(
                "main", "gui_language", ""))

        if self.globalConfig.getboolean("main", "single_process"):
            # Single process mode means to create a server, detect an already
            # running server and, if there, just send the commandline to
            # the running server and quit then.            

            # We create a "password" so that no other user can send commands to this
            # WikidPad instance.
            appCookie = createRandomString(30)
            
            try:
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
                    appLockContent = loadEntireFile(os.path.join(
                            self.globalConfigSubDir, "AppLock.lock")).decode("latin-1")
    #                 f = open(), "r")
    #                 f.read()
    #                 f.close()
                    
                    lines = appLockContent.split("\n")
                    if len(lines) != 3:
                        sys.stderr.write(_("Invalid AppLock.lock file.\n"
                                "Ensure that WikidPad is not running,\n"
                                "then delete file \"%s\" if present yet.\n") %
                                    (os.path.join(self.globalConfigSubDir,
                                    "AppLock.lock")))
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
                                    sock.send(("cmdline\n" + appCookie + "\n").encode("ascii"))
                                    
                                    ack = self._readSocketLine(sock)
                                    if ack[0] == "+":
                                        # app cookie ok
                                        sst = SerializeStream(byteBuf=b"", readMode=False)
                                        sst.serArrUniUtf8(sys.argv[1:])
                                        sock.send(sst.getBytes())
                                    
                                        return True
        
                                # Reaching this point means something went wrong
                                singleInstance = True  # TODO More fine grained reaction
                            except socket.timeout as e:
                                singleInstance = True
                            except socket.error as e:
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
    
                if self.globalConfig.getboolean("main", "zombieCheck", True):
                    otherProcIds = OsAbstract.checkForOtherInstances()
                    if len(otherProcIds) > 0:
                        procIdString = ", ".join([str(procId)
                                for procId in otherProcIds])
                        answer = wx.MessageBox(
                                _("Other WikidPad process(es) seem(s) to run already\n"
                                "Process identifier(s): %s\nContinue?") % procIdString,
                                _("Continue?"),
                                wx.YES_NO | wx.YES_DEFAULT | wx.ICON_QUESTION, None)
    
                        if answer != wx.YES:
                            return False

                if port != -1:
                    # Server is connected, start it
                    Ipc.startCommandServer()
                    
                    appLockContent = (appCookie + "\n" + str(port) + "\n") \
                            .encode("latin-1")
                    appLockPath = os.path.join(self.globalConfigSubDir,
                            "AppLock.lock")
    
                    writeEntireFile(appLockPath, appLockContent)
    
                    self.removeAppLockOnExit = True
    
                    Ipc.getCommandServer().setAppLockInfo(appLockPath, appLockContent)
                else:
                    answer = wx.MessageBox(
                            _("WikidPad couldn't detect if other processes are "
                            "already running.\nContinue anyway?"),
                            _("Continue?"),
                            wx.YES_NO | wx.YES_DEFAULT | wx.ICON_QUESTION, None)

                    if answer != wx.YES:
                        return False
                    
            except socket.error as e:
                answer = wx.MessageBox(
                        _("WikidPad couldn't detect if other processes are "
                        "already running.\nSocket error: %s\nContinue anyway?") %
                        str(e), _("Continue?"),
                        wx.YES_NO | wx.YES_DEFAULT | wx.ICON_QUESTION, None)

                if answer != wx.YES:
                    return False


        # Build icon cache
        iconDir = os.path.join(self.wikiAppDir, "icons")
        self.iconCache = IconCache(iconDir)

        # Create plugin manager for application-wide plugins
#         dirs = ( os.path.join(self.globalConfigSubDir, u'user_extensions'),
#                 os.path.join(self.wikiAppDir, u'user_extensions'),
#                 os.path.join(self.wikiAppDir, u'extensions') )

        self.reloadPlugins()

        self.collator = None

        # Further configuration settings
        self._rereadGlobalConfig()

        rd = Localization.getI18nXrcData(self.wikiAppDir,
                self.globalConfigSubDir, "WikidPad")
        ## _prof.stop()

        res = wx.xrc.XmlResource.Get()
        res.InitAllHandlers()
        res.SetFlags(0)
        res.AddSubclassFactory(SimpleXmlSubclassFactory())

        res.LoadFromBuffer(rd)

#         rd = loadEntireFile(r"C:\Daten\Projekte\Wikidpad\Current\wizards.xrc", True)
#         res.LoadFromString(rd)

        self.standardIcon = wx.Icon(os.path.join(self.wikiAppDir, 'icons',
                    'pwiki.ico'), wx.BITMAP_TYPE_ICO)

        self.startPersonalWikiFrame(cmdLine)

        return True


    def reloadPlugins(self):
        """
        Load or reload application-wide plugins. Normally called only once
        automatically at startup. Later calls only recommended during plugin
        development as they can have unwanted side effects!
        """
        from .PluginManager import PluginManager, InsertionPluginManager, \
                KeyInParamLearningDispatcher

        dirs = ( os.path.join(self.wikiAppDir, 'extensions'),
                os.path.join(self.wikiAppDir, 'user_extensions'),
                os.path.join(self.globalConfigSubDir, 'user_extensions') )

        self.pluginManager = PluginManager(dirs, systemDirIdx=0)

        # Register app-wide plugin APIs
        describeInsertionApi = self.pluginManager.registerSimplePluginAPI(
                ("InsertionByKey", 1), ("describeInsertionKeys",))

        registerOptionsApi = self.pluginManager.registerSimplePluginAPI(
                ("Options", 1), ("registerOptions",))

        describeWikiLanguageApi = self.pluginManager.registerSimplePluginAPI(
                ("WikiParser", 1), ("describeWikiLanguage",))

        self.describeExportersApi = self.pluginManager.registerSimplePluginAPI(
                ("Exporters", 1), ("describeExportersV01",))

        self.describePrintsApi = self.pluginManager.registerSimplePluginAPI(
                ("Prints", 1), ("describePrintsV01",))
                
        menuModifierApi = self.pluginManager.registerSimplePluginAPI(
                ("MenuModifier", 1), ("modifyMenuV01",))

        menuItemProviderApi = self.pluginManager.registerSimplePluginAPI(
                ("MenuItemProvider", 1), ("provideMenuItemV01",))

        # Load plugins
#         dirs = ( os.path.join(self.wikiAppDir, u'user_extensions'),
#                 os.path.join(self.wikiAppDir, u'extensions') )

        self.pluginManager.loadPlugins([ 'KeyBindings.py',
                'EvalLibrary.py'] )

        # Register options
        registerOptionsApi.registerOptions(1, self)

#         # Retrieve descriptions for InsertionByKey
#         insertionDescriptions = reduce(lambda a, b: a+list(b),
#                 describeInsertionApi.describeInsertionKeys(1, self), [])
# 
#         self.insertionPluginManager = InsertionPluginManager(
#                 insertionDescriptions)

        # Retrieve descriptions for InsertionByKey
        insertionDescriptions = reduce(lambda a, b: a+list(b),
                describeInsertionApi.describeInsertionKeys(1, self), [])

        self.insertionPluginManager = InsertionPluginManager(
                insertionDescriptions)

        wikiLanguageDescriptions = reduce(lambda a, b: a+list(b),
                describeWikiLanguageApi.describeWikiLanguage(1, self), [])

        self.wikiLanguageDescDict = dict(( (item[0], item)
                for item in wikiLanguageDescriptions ))

        # Parameters to .dispatch(): contextName, contextDict, menu;
        # contextName is key for LearningDispatcher
        self.modifyMenuDispatcher = KeyInParamLearningDispatcher(
                menuModifierApi.modifyMenuV01, 0)

        # Parameters to .dispatch(): menuItemUnifName, contextName, contextDict,
        # menu, insertIdx; menuItemUnifName is key for LearningDispatcher
        self.provideMenuItemDispatcher = KeyInParamLearningDispatcher(
                menuItemProviderApi.provideMenuItemV01, 0)



    def _readSocketLine(self, sock):
        result = []
        read = 0
        while read < 300:
            c = sock.recv(1)
            if c == b"\n" or c == b"":
                return (b"".join(result)).decode("latin-1")
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
        if "wikidpad_default_2_0" in self.wikiLanguageDescDict:
            return [self.getWikiLanguageDescription("wikidpad_default_2_0")] + \
                    [l for l in list(self.wikiLanguageDescDict.values())
                    if l[0] != "wikidpad_default_2_0"]
        else:
            return list(self.wikiLanguageDescDict.values())


    def getModifyMenuDispatcher(self):
        return self.modifyMenuDispatcher

    def getProvideMenuItemDispatcher(self):
        return self.provideMenuItemDispatcher


    def createWikiParser(self, intLanguageName, debugMode=False):   # ):True
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
        
        
    def FilterEvent(self, evt):
        if isinstance(evt, wx.MouseEvent) and \
                wx.wxEVT_MOUSEWHEEL == evt.GetEventType():
                    
            oldObj = evt.GetEventObject()

            scPos = evt.GetEventObject().ClientToScreen(evt.GetPosition())
            wnd = wx.FindWindowAtPoint(scPos)
            if wnd is not None and wnd is not oldObj:
#                 newPos = wnd.ScreenToClient(scPos)
                evt.m_x, evt.m_y = 0, 0 # newPos
                evt.SetEventObject(wnd)
                
                scrollUnits = (evt.GetWheelRotation() // evt.GetWheelDelta()) * evt.GetLinesPerAction()
                
                if isinstance(wnd, wx.ScrolledWindow):
                    x, y = wnd.GetViewStart()
                    wnd.Scroll(x, y - scrollUnits)
#                 elif isinstance(wnd, wx.ListCtrl):
#                     print "--FilterEvent31", repr(wnd.HasScrollbar(wx.VERTICAL))
                    
#                 elif wnd.HasScrollbar(wx.VERTICAL):
# #                     print "--FilterEvent31"
#                     y = wnd.GetScrollPos(wx.VERTICAL)
#                     wnd.SetScrollPos(wx.VERTICAL, y - scrollUnits)
                else:
#                     print "--FilterEvent45", repr(((evt.GetEventObject()), scrollUnits, wnd.HasScrollbar(wx.VERTICAL)))                    
                    wnd.ProcessEvent(evt)

                return 1
                
        result = wx.App.FilterEvent(self, evt)
        return result
        

    def pauseBackgroundThreads(self):
        self.fireMiscEventKeys(("pause background threads",))

    def resumeBackgroundThreads(self):
        self.fireMiscEventKeys(("resume background threads",))

    def onChangedGlobalConfiguration(self, miscevt):
        self._rereadGlobalConfig()
        

    def _rereadGlobalConfig(self):
        """
        Realize settings from global config which are changeable during session
        """
        from . import Localization
        from . import OsAbstract
        
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
                self.collator = Localization.getCollatorByString("Default",
                        collationCaseMode)
            except:
                self.collator = Localization.getCollatorByString("C",
                        collationCaseMode)
        try:
            self.SetCallFilterEvent(self.globalConfig.getboolean("main",
                    "mouse_scrollUnderPointer"))
        except AttributeError:
            pass  # Older wxPython versions didn't support this
            
        # Set CPU affinity
        
        if OsAbstract.getCpuCount() > 1:
            aff = self.globalConfig.getint("main", "cpu_affinity", -1)
            
            if aff == -1:
                OsAbstract.setCpuAffinity(OsAbstract.INITIAL_CPU_AFFINITY)
            else:
                OsAbstract.setCpuAffinity((aff,))



    def OnEndSession(self, evt):
        # Loop over copy of set as original set is modified during loop
        for wikiFrame in frozenset(self.mainFrameSet):
            wikiFrame.exitWiki()


    def OnExit(self):
        from . import Ipc

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
            wx.MessageBox(_("An error occurred during this session\nSee file %s") %
                    os.path.join(ExceptionLogger.getLogDestDir()),
                    "Error", style = wx.OK)
        
        return 0


    def getMainFrameSet(self):
        return self.mainFrameSet

    def startPersonalWikiFrame(self, clAction):
        from .PersonalWikiFrame import PersonalWikiFrame

        wikiFrame = PersonalWikiFrame(None, -1, "WikidPad", self.wikiAppDir,
                self.globalConfigDir, self.globalConfigSubDir, clAction)

        self.fireMiscEventProps({"adding wiki frame": True,
                "wiki frame": wikiFrame})
        self.SetTopWindow(wikiFrame)
        self.mainFrameSet.add(wikiFrame)
        self.fireMiscEventProps({"added wiki frame": True,
                "wiki frame": wikiFrame})

        ## _prof.stop()

        # set the icon of the app
        try:
            wikiFrame.SetIcon(self.standardIcon)
        except:
            pass
        
        return wikiFrame


    def unregisterMainFrame(self, wikiFrame):
        self.fireMiscEventProps({"removing wiki frame": True,
                "wiki frame": wikiFrame})
        self.mainFrameSet.discard(wikiFrame)
        self.fireMiscEventProps({"removed wiki frame": True,
                "wiki frame": wikiFrame})

    
    def findFrameByWikiConfigPath(self, wikiConfigPath):
        """
        Find and return a PersonalWikiFrame which currently displays the wiki
        determined by its  wikiConfigPath. If wiki isn't displayed None is
        returned. If multiple frames show the wiki one of them is chosen
        arbitrarily.
        """
        from .OsAbstract import samefile

        for frame in self.mainFrameSet:
            wikiDoc = frame.getWikiDocument()
            if wikiDoc is None:
                continue
            if samefile(wikiDoc.getWikiConfigPath(), wikiConfigPath):
                return frame
        
        return None


    def describeExporters(self, mainControl):
        return reduce(lambda a, b: a+list(b),
                self.describeExportersApi.describeExporters(mainControl), [])

    def describePrints(self, mainControl):
        return reduce(lambda a, b: a+list(b),
                self.describePrintsApi.describePrintsV01(mainControl), [])


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

    def getGlobalConfigDir(self):
        return self.globalConfigDir

    def getGlobalConfig(self):
        return self.globalConfig
        
    def getWikiAppDir(self):
        return self.wikiAppDir
    
    def isInPortableMode(self):
        return self.globalConfigDir == self.wikiAppDir

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

    def addGlobalPluginOptionsDlgPanel(self, factory, title):
        """
        Add option page to global plugin options 
        
        factory -- Factory function taking parameters
            (parent, optionsDlg, mainControl) where
                parent: GUI parent of panel
                optionsDlg: OptionsDialog object
                mainControl: PersonalWikiFrame object
        title -- unistring with title to show in the left list in options
            dialog
        """
        pl = self.getOptionsDlgPanelList()
        try:
            insPos = pl.index(("??insert mark/plugins global", ""))
        except ValueError:
            pl.append(("", _("Plugin options")))
            insPos = len(pl)
            pl.append(("??insert mark/plugins global", ""))

        pl.insert(insPos, (factory, 2 * " " + title))


    def addOptionsDlgPanel(self, factory, title):
        # Wrap factory function expecting old parameters with one for
        # the new parameters.
        def optionsPanelFactoryWrapper(parent, optionsDlg, mainControl):
            return factory(parent, optionsDlg, wx.GetApp())

        """
        Deprecated function, use addGlobalPluginOptionsDlgPanel() instead!

        Add option page to global plugin options.
        
        factory -- Factory function (or class taking parameters
            (parent, optionsDlg, app) where
                parent: GUI parent of panel
                optionsDlg: OptionsDialog object
                app: MainApp object
        title -- unistring with title to show in the left list in options
            dialog
        """
        if title[:2] == "  ":
            title = title[2:]

        self.addGlobalPluginOptionsDlgPanel(optionsPanelFactoryWrapper, title)


    def addWikiWikiLangOptionsDlgPanel(self, factory, title):
        """
        factory -- Factory function (or class taking parameters
            (parent, optionsDlg, mainControl) where
                parent: GUI parent of panel
                optionsDlg: OptionsDialog object
                mainControl: PersonalWikiFrame object
        title -- unistring with title to show in the left list in options
            dialog
        """
        pl = self.getOptionsDlgPanelList()

        try:
            insPos = pl.index(("??insert mark/current wiki/wiki lang", ""))
        except ValueError:
            insPos = pl.index(("??insert mark/current wiki", ""))
            pl.insert(insPos, ("??insert mark/current wiki/wiki lang", ""))
            pl.insert(insPos, ("", 2 * " " + _("Wiki language")))
            insPos += 1

        pl.insert(insPos, (factory, 4 * " " + title))


    def addWikiPluginOptionsDlgPanel(self, factory, title):
        """
        factory -- Factory function (or class taking parameters
            (parent, optionsDlg, mainControl) where
                parent: GUI parent of panel
                optionsDlg: OptionsDialog object
                mainControl: PersonalWikiFrame object
        title -- unistring with title to show in the left list in options
            dialog
        """
        pl = self.getOptionsDlgPanelList()

        try:
            insPos = pl.index(("??insert mark/current wiki/plugins", ""))
        except ValueError:
            insPos = pl.index(("??insert mark/current wiki", ""))
            pl.insert(insPos, ("??insert mark/current wiki/plugins", ""))
            pl.insert(insPos, ("", 2 * " " + _("Plugins")))
            insPos += 1

        pl.insert(insPos, (factory, 4 * " " + title))
