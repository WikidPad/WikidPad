#!/bin/python

import sys, os, traceback, os.path, socket

# To generate dependency for py2exe
import subprocess

import ExceptionLogger

import wx, wx.xrc
# from wxPython.wx import *
# import wxPython.xrc as xrc

import srePersistent
srePersistent.loadCodeCache()

from wxHelper import IconCache
from MiscEvent import KeyFunctionSink
from PersonalWikiFrame import PersonalWikiFrame
from StringOps import mbcsDec, createRandomString, pathEnc
from CmdLineAction import CmdLineAction
from Serialization import SerializeStream
import Ipc
import Configuration
import OptionsDialog
from Localization import getCollatorByString, CASEMODE_UPPER_INSIDE, \
        CASEMODE_UPPER_FIRST
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
    if os.path.exists(pathEnc(os.path.join(wikiAppDir, "WikidPad.config"))):
        globalConfigDir = wikiAppDir
    else:
        globalConfigDir = os.environ.get("HOME")
        if not (globalConfigDir and os.path.exists(pathEnc(globalConfigDir))):
            # Instead of checking USERNAME, the user config dir. is
            # now used
            globalConfigDir = wx.StandardPaths.Get().GetUserConfigDir()
            if os.path.exists(pathEnc(globalConfigDir)) and isWindows:
                try:
                    realGlobalConfigDir = os.path.join(globalConfigDir,
                            "WikidPad")
                    if not os.path.exists(pathEnc(realGlobalConfigDir)):
                        # If it doesn't exist, create the directory
                        os.mkdir(realGlobalConfigDir)
                        
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



class App(wx.App): 
    def __init__(self, *args, **kwargs):
        global app
        app = self

        wx.App.__init__(self, *args, **kwargs)
        self.SetAppName("WikidPad")
        # Do not initialize member variables here!


    def OnInit(self):
        ## _prof.start()
        global PREVIEW_CSS

        self.SetAppName("WikidPad")
        self.removeAppLockOnExit = False
        appdir = os.path.dirname(os.path.abspath(sys.argv[0]))
        
        wikiAppDir, globalConfigDir = findDirs()
        
        if not globalConfigDir or not os.path.exists(pathEnc(globalConfigDir)):
            raise Exception(u"Error initializing environment, couldn't locate "
                    u"global config directory")
                    
        self.wikiAppDir = wikiAppDir
        self.globalConfigDir = globalConfigDir

        self.globalConfigSubDir = os.path.join(self.globalConfigDir,
                ".WikidPadGlobals")
        if not os.path.exists(pathEnc(self.globalConfigSubDir)):
            os.mkdir(self.globalConfigSubDir)

        pCssLoc = os.path.join(self.globalConfigSubDir, "wikipreview.css")
        if not os.path.exists(pathEnc(pCssLoc)):
            tbFile = open(pathEnc(pCssLoc), "w")
            tbFile.write(PREVIEW_CSS)
            tbFile.close()

        # Create default config dicts
        self.defaultGlobalConfigDict = Configuration.GLOBALDEFAULTS.copy()
        self.defaultWikiConfigDict = Configuration.WIKIDEFAULTS.copy()
        self.optionsDlgPanelList = list(
                OptionsDialog.OptionsDialog.DEFAULT_PANEL_LIST)

        # load or create global configuration
        globalConfigLoc = os.path.join(self.globalConfigDir, "WikidPad.config")
        self.globalConfig = self.createGlobalConfiguration()
        if os.path.exists(pathEnc(globalConfigLoc)):
            try:
                self.globalConfig.loadConfig(globalConfigLoc)
            except Configuration.Error:
                self.createDefaultGlobalConfig(globalConfigLoc)
        else:
            self.createDefaultGlobalConfig(globalConfigLoc)
            
        self.globalConfig.getMiscEvent().addListener(KeyFunctionSink((
                ("configuration changed", self.onGlobalConfigurationChanged),
        )), False)


        self.lowResources = self.globalConfig.getboolean("main", "lowresources")

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
            if os.path.exists(pathEnc(os.path.join(self.globalConfigSubDir,
                    "AppLock.lock"))):
                singleInstance = False
                # There seems to be(!) another instance already
                # TODO Try to send commandline
                f = open(pathEnc(os.path.join(self.globalConfigSubDir,
                        "AppLock.lock")), "r")
                appLockContent = f.read()
                f.close()
                
                lines = appLockContent.split("\n")
                if len(lines) != 3:
                    sys.stderr.write("Invalid AppLock.lock file\n")
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
                            if e.args[0] == 10061:
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
    
                f = open(pathEnc(os.path.join(self.globalConfigSubDir,
                        "AppLock.lock")), "w")
                f.write(appLockContent)
                f.close()
    
                self.removeAppLockOnExit = True
        
        # Build icon cache
        iconDir = os.path.join(self.wikiAppDir, "icons")
        self.iconCache = IconCache(iconDir, self.lowResources)
        
        # Create plugin manager for application-wide plugins
        self.pluginManager = PluginManager()

        # Register app-wide plugin APIs
        describeInsertionApi = self.pluginManager.registerPluginAPI(
                ("InsertionByKey", 1), ("describeInsertionKeys",))

        registerOptionsApi = self.pluginManager.registerPluginAPI(
                ("Options", 1), ("registerOptions",))
        
        # Load plugins
        dirs = ( os.path.join(self.wikiAppDir, u'user_extensions'),
                os.path.join(self.wikiAppDir, u'extensions') )
        self.pluginManager.loadPlugins( dirs, [ u'KeyBindings.py',
                u'EvalLibrary.py', u'WikiSyntax.py' ] )

        # Register options
        registerOptionsApi.registerOptions(1, self)

        # Retrieve descriptions for InsertionByKey
        insertionDescriptions = reduce(lambda a, b: a+list(b),
                describeInsertionApi.describeInsertionKeys(1, self), [])

        self.insertionPluginManager = InsertionPluginManager(
                insertionDescriptions)

        self.collator = None

        # Further configuration settings
        self._rereadGlobalConfig()

        # Load wxPython XML resources
        rf = open(pathEnc(os.path.join(appdir, "WikidPad.xrc")), "r")
        rd = rf.read()
        rf.close()

        res = wx.xrc.XmlResource.Get()
        res.SetFlags(0)
        res.LoadFromString(rd)

        self.startPersonalWikiFrame(CmdLineAction(sys.argv[1:]))

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
            collationCaseMode = CASEMODE_UPPER_FIRST
        else:
            collationCaseMode = CASEMODE_UPPER_INSIDE

        self.collator = getCollatorByString(collationOrder, collationCaseMode)

        
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
            wx.MessageBox("An error occurred during this session\nSee file %s" %
                    os.path.join(ExceptionLogger._exceptionDestDir, "WikidPad_Error.log"),
                    "Error", style = wx.OK)


    def startPersonalWikiFrame(self, clAction):
        wikiFrame = PersonalWikiFrame(None, -1, "WikidPad", self.wikiAppDir,
                self.globalConfigDir, self.globalConfigSubDir, clAction)

        self.SetTopWindow(wikiFrame)
        ## _prof.stop()

        # set the icon of the app
        try:
            wikiFrame.SetIcon(wx.Icon(os.path.join(self.wikiAppDir, 'icons',
                    'pwiki.ico'), wx.BITMAP_TYPE_ICO))
        except:
            pass


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

    def getLowResources(self):
        """
        Return state of the low resources global setting
        """
        return self.lowResources

    def getIconCache(self):
        """
        Return the icon cache object
        """
        return self.iconCache

    def getCollator(self):
        return self.collator

    def getInsertionPluginManager(self):
        return self.insertionPluginManager


    def createGlobalConfiguration(self):
        return Configuration.SingleConfiguration(
                self.getDefaultGlobalConfigDict())

    def createWikiConfiguration(self):
        return Configuration.SingleConfiguration(
                self.getDefaultWikiConfigDict())

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
        Returns the dictionary of the global configuration defaults.
        It is a copy of Configuration.WIKIDEFAULTS.
        The dictionary can be manipulated by plugins to add further
        configuration options.
        """
        return self.defaultWikiConfigDict

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


PREVIEW_CSS = """
BODY {
	font-family: Verdana; font-size: 90%;
}

.wiki-name-ref {
	color: #888888; font-size: 75%;
}

.parent-nodes {
	color: #888888; font-size: 75%;
}

.property {
	color: #888888; font-size: 75%;
}

.script {
	color: #888888; font-size: 75%;
}

.todo {
	font-weight: bold;
}

.url-link {
}

.wiki-link {
}

.page-toc {
}

.page-toc-level1 {
}

.page-toc-level2 {
    margin-left: 4mm;
}

.page-toc-level3 {
    margin-left: 8mm;
}

.page-toc-level4 {
    margin-left: 12mm;
}
"""
