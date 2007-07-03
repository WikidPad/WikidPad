#!/bin/python

import sys, os, traceback, os.path, glob
os.stat_float_times(True)

VERSION_STRING = "wikidPad 1.8rc6"

if not hasattr(sys, 'frozen'):
    sys.path.append("lib")

import ExceptionLogger
ExceptionLogger.startLogger(VERSION_STRING)


# ## import hotshot
# ## _prof = hotshot.Profile("hotshot.prf")
# 
# # To ensure unicode selection, works only for me (Michael)
# 
# # if not hasattr(sys, 'frozen'):
# #     sys.path =  \
# #             [r"C:\Programme\Python23\Lib\site-packages\wx-2.6-msw-unicode"] + sys.path
# 
# 
# 
# 
# from wxPython.wx import *

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "gadfly.zip"))
# print "sys.path + ", os.path.join(os.path.abspath(sys.argv[0]), "gadfly.zip")


from wxPython.wx import wxApp, wxMessageDialog, wxDEFAULT_FRAME_STYLE, \
        wxNO_FULL_REPAINT_ON_RESIZE, wxFrame, wxOK

# import wxPython.xrc as xrc
# 
# wxWINDOWS_NT = 18   # For wxGetOsVersion()
# wxWIN95 = 20   # For wxGetOsVersion(), this includes also Win 98 and ME
# 
# 
# 

from pwiki import srePersistent
srePersistent.loadCodeCache()

from pwiki.MainApp import App, findDirs

# 
# from pwiki.wxHelper import IconCache
# from pwiki.MiscEvent import KeyFunctionSink
# from pwiki.PersonalWikiFrame import PersonalWikiFrame
# from pwiki.StringOps import mbcsDec, createRandomString
# from pwiki.CmdLineAction import CmdLineAction
# from pwiki.Serialization import SerializeStream
# from pwiki import Ipc
# from pwiki.Configuration import createGlobalConfiguration
# from pwiki.Localization import getCollatorByString, CASEMODE_UPPER_INSIDE, \
#         CASEMODE_UPPER_FIRST
# 
# 
# 
# def findDirs():
#     """
#     Returns tuple (wikiAppDir, globalConfigDir)
#     """
#     wikiAppDir = None
#     
#     isWindows = (wxGetOsVersion()[0] == wxWIN95) or \
#             (wxGetOsVersion()[0] == wxWINDOWS_NT)
# 
#     try:
#         wikiAppDir = os.path.dirname(os.path.abspath(sys.argv[0]))
#         if not wikiAppDir:
#             wikiAppDir = r"C:\Program Files\WikidPad"
#             
#         globalConfigDir = None
# 
#         # This allows to keep the program with config on an USB stick
#         if os.path.exists(os.path.join(wikiAppDir, "WikidPad.config")):
#             globalConfigDir = wikiAppDir
#         else:
#             globalConfigDir = os.environ.get("HOME")
#             if not (globalConfigDir and os.path.exists(globalConfigDir)):
# #                 globalConfigDir = os.environ.get("USERPROFILE")
# #                 if not (globalConfigDir and os.path.exists(globalConfigDir)):
#                     # Instead of checking USERNAME, the user config dir. is
#                     # now used
#                 globalConfigDir = wxStandardPaths.Get().GetUserConfigDir()
#                 if os.path.exists(globalConfigDir) and isWindows:
#                     try:
#                         realGlobalConfigDir = os.path.join(globalConfigDir,
#                                 "WikidPad")
#                         if not os.path.exists(realGlobalConfigDir):
#                             # If it doesn't exist, create the directory
#                             os.mkdir(realGlobalConfigDir)
#                             
#                         globalConfigDir = realGlobalConfigDir
#                     except:
#                         traceback.print_exc()
# 
# #                     user = os.environ.get("USERNAME")
# #                     if user:
# #                         globalConfigDir = r"c:\Documents And Settings\%s" % user
# 
# #             if globalConfigDir and os.path.exists(globalConfigDir) and isWindows:
# #                 try:
# #                     realGlobalConfigDir = os.path.join(globalConfigDir, "WikidPad")
# #                     if not os.path.exists(realGlobalConfigDir):
# #                         # If it doesn't exist, create the directory
# #                         os.mkdir(realGlobalConfigDir)
# #                         # ... and try to move already created config files to it
# #                         oldCfgFile = os.path.join(globalConfigDir,
# #                                 "WikidPad.config")
# #                         oldGlobalsDir = os.path.join(globalConfigDir,
# #                                 ".WikidPadGlobals")
# #                         newCfgFile = os.path.join(realGlobalConfigDir,
# #                                 "WikidPad.config")
# #                         newGlobalsDir = os.path.join(realGlobalConfigDir,
# #                                 ".WikidPadGlobals")
# #                         if os.path.exists(oldCfgFile):
# #                             os.rename(oldCfgFile, newCfgFile)
# #                         if os.path.exists(oldGlobalsDir):
# #                             os.rename(oldGlobalsDir, newGlobalsDir)
# #                             
# #                     globalConfigDir = realGlobalConfigDir
# #                 except:
# #                     traceback.print_exc()
# 
#     finally:
#         pass
# 
#     if not globalConfigDir:
#         globalConfigDir = wikiAppDir
# 
#     # mbcs decoding
#     if wikiAppDir is not None:
#         wikiAppDir = mbcsDec(wikiAppDir, "replace")[0]
# 
#     if globalConfigDir is not None:
#         globalConfigDir = mbcsDec(globalConfigDir, "replace")[0]
#         
#     ExceptionLogger._exceptionDestDir = globalConfigDir
# 
#     return (wikiAppDir, globalConfigDir)
# 
# 
# 
# 

if len(sys.argv) == 2 and sys.argv[1] == "--deleteconfig":
    # Special option, called by deinstaller on request to delete personal
    # configuration files
    dummyApp = wxApp(0)
    dummyApp.SetAppName("WikidPad")

    wikiAppDir, globalConfigDir = findDirs()
    if globalConfigDir is None:
        sys.exit(1)
        
    try:
        globalConfigSubDir = os.path.join(globalConfigDir, ".WikidPadGlobals")
        subfiles = glob.glob(os.path.join(globalConfigSubDir, "*"))
        for f in subfiles:
            try:
                os.remove(f)
            except:
                pass
        try:
            os.rmdir(globalConfigSubDir)
        except:
            pass

        try:
            os.remove(os.path.join(globalConfigDir, "WikidPad.config"))
        except:
            pass
            
        if wikiAppDir != globalConfigDir:
            try:
                os.rmdir(globalConfigDir)
            except:
                pass

        sys.exit(0)
    
    except:
        sys.exit(1)
# 
# 
# class App(wxApp): 
#     def __init__(self, *args, **kwargs):
#         global app
#         app = self
# 
#         wxApp.__init__(self, *args, **kwargs)
#         self.SetAppName("WikidPad")
#         # Do not initialize member variables here!
# 
# 
#     def OnInit(self):
#          # TODO Load global config here!!!
#         ## _prof.start()
# 
#         self.SetAppName("WikidPad")
#         self.removeAppLockOnExit = False
#         appdir = os.path.dirname(os.path.abspath(sys.argv[0]))
#         
#         wikiAppDir, globalConfigDir = findDirs()
#         
#         if not globalConfigDir or not os.path.exists(globalConfigDir):
#             raise Exception(u"Error initializing environment, couldn't locate "
#                     u"global config directory")
#                     
#         self.wikiAppDir = wikiAppDir
#         self.globalConfigDir = globalConfigDir
# 
#         self.globalConfigSubDir = os.path.join(self.globalConfigDir,
#                 ".WikidPadGlobals")
#         if not os.path.exists(self.globalConfigSubDir):
#             os.mkdir(self.globalConfigSubDir)
# 
#         # load or create global configuration
#         globalConfigLoc = os.path.join(self.globalConfigDir, "WikidPad.config")
#         self.globalConfig = createGlobalConfiguration()
#         if os.path.exists(globalConfigLoc):
#             try:
#                 self.globalConfig.loadConfig(globalConfigLoc)
#             except Configuration.Error:
#                 self.createDefaultGlobalConfig(globalConfigLoc)
#         else:
#             self.createDefaultGlobalConfig(globalConfigLoc)
#             
#         self.globalConfig.getMiscEvent().addListener(KeyFunctionSink((
#                 ("configuration changed", self.onGlobalConfigurationChanged),
#         )), False)
# 
# 
#         self.lowResources = self.globalConfig.getboolean("main", "lowresources")
# 
#         # Build icon cache
#         iconDir = os.path.join(self.wikiAppDir, "icons")
#         self.iconCache = IconCache(iconDir, self.lowResources)
#         
#         # self.collator = getCollatorByString("c")
#         # self.collator = getCollatorByString("Default")
#         # self.collator = getCollatorByString("", True)
# 
#         if self.globalConfig.getboolean("main", "single_process"):
#             # Single process mode means to create a server, detect an already
#             # running server and, if there, just send the commandline to
#             # the running server and quit then.            
# 
#             # We create a "password" so that no other user can send commands to this
#             # WikidPad instance.
#             appCookie = createRandomString(30)
#             
#             port = Ipc.createCommandServer(appCookie)
#             
#             # True if this is the single existing instance which should write
#             # a new "AppLock.lock" file which either didn't exist or was invalid
# 
#             singleInstance = True
#     
#             # TODO maybe more secure method to ensure atomic exist. check and
#             #   writing of file
#             if os.path.exists(os.path.join(self.globalConfigSubDir, "AppLock.lock")):
#                 singleInstance = False
#                 # There seems to be(!) another instance already
#                 # TODO Try to send commandline
#                 f = open(os.path.join(self.globalConfigSubDir, "AppLock.lock"), "ra")
#                 appLockContent = f.read()
#                 f.close()
#                 
#                 lines = appLockContent.split("\n")
#                 if len(lines) != 3:
#                     return True # TODO Error handling!!!
#                     
#                 appCookie = lines[0]
#                 remotePort = int(lines[1])
#                 
#                 if port != remotePort:
#                     # Everything ok so far
#                     sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
#                     sock.settimeout(10.0)
#                     try:
#                         try:
#                             sock.connect(("127.0.0.1", remotePort))
#                             greet = self._readSocketLine(sock)
#                             if greet == "WikidPad_command_server 1.0":
#                                 sock.send("cmdline\n" + appCookie + "\n")
#                                 
#                                 ack = self._readSocketLine(sock)
#                                 if ack[0] == "+":
#                                     # app cookie ok
#                                     sst = SerializeStream(stringBuf="", readMode=False)
#                                     sst.serArrString(sys.argv[1:])
#                                     sock.send(sst.getBytes())
#                                 
#                                     return True
#     
#                             # Reaching this point means something went wrong
#                             singleInstance = True  # TODO More fine grained reaction
#                         except socket.timeout, e:
#                             singleInstance = True
#                         except socket.error, e:
#                             if e.args[0] == 10061:
#                                 # Connection refused (port not bound to a server)
#                                 singleInstance = True
#                             else:
#                                 raise
#                     finally:
#                         sock.close()
#     
#                 else:
#                     # Sure indicator that AppLock file is invalid if newly
#                     # created server opened a port which is claimed to be used
#                     # already by previously started instance.
#                     singleInstance = True
#     
#             if not singleInstance:
#                 return False
# 
#             if port != -1:
#                 # Server is connected, start it
#                 Ipc.startCommandServer()
#     
#                 appLockContent = appCookie + "\n" + str(port) + "\n"
#     
#                 f = open(os.path.join(self.globalConfigSubDir, "AppLock.lock"), "wa")
#                 f.write(appLockContent)
#                 f.close()
#     
#                 self.removeAppLockOnExit = True
#         
#         self.collator = None
# 
#         # Further configuration settings
#         self._rereadGlobalConfig()
# 
#         # Load wxPython XML resources
#         rf = open(os.path.join(appdir, "WikidPad.xrc"), "r")
#         rd = rf.read()
#         rf.close()
# 
#         res = xrc.wxXmlResource.Get()
#         res.SetFlags(0)
#         res.LoadFromString(rd)
# 
#         self.startPersonalWikiFrame(CmdLineAction(sys.argv[1:]))
# 
#         return True
#         
#         
#     def _readSocketLine(self, sock):
#         result = []
#         read = 0
#         while read < 300:
#             c = sock.recv(1)
#             if c == "\n" or c == "":
#                 return "".join(result)
#             result.append(c)
#             read += 1
#             
#         return ""
# 
# 
#     def onGlobalConfigurationChanged(self, miscevt):
#         self._rereadGlobalConfig()
# 
# 
#     def _rereadGlobalConfig(self):
#         """
#         Make settings from global config which are changeable during session
#         """
#         collationOrder = self.globalConfig.get("main", "collation_order")
#         collationUppercaseFirst = self.globalConfig.getboolean("main",
#                 "collation_uppercaseFirst")
#                 
#         if collationUppercaseFirst:
#             collationCaseMode = CASEMODE_UPPER_FIRST
#         else:
#             collationCaseMode = CASEMODE_UPPER_INSIDE
# 
#         self.collator = getCollatorByString(collationOrder, collationCaseMode)
# 
#         
#     def OnExit(self):
#         if self.removeAppLockOnExit:
#             try:
#                 os.remove(os.path.join(self.globalConfigSubDir, "AppLock.lock"))
#             except:  # OSError, ex:
#                 traceback.print_exc()
#                 # TODO Error message!
# 
#         try:
#             Ipc.stopCommandServer()
#         except:
#             traceback.print_exc()
# 
#         if ExceptionLogger._exceptionOccurred and hasattr(sys, 'frozen'):
#             wxMessageBox("An error occurred during this session\nSee file %s" %
#                     os.path.join(ExceptionLogger._exceptionDestDir, "WikidPad_Error.log"),
#                     "Error", style = wxOK)
# 
# 
#     def startPersonalWikiFrame(self, clAction):
#         wikiFrame = PersonalWikiFrame(None, -1, "WikidPad", self.wikiAppDir,
#                 self.globalConfigDir, self.globalConfigSubDir, clAction)
# 
#         self.SetTopWindow(wikiFrame)
#         ## _prof.stop()
# 
#         # set the icon of the app
#         try:
#             wikiFrame.SetIcon(wxIcon(os.path.join(self.wikiAppDir, 'icons',
#                     'pwiki.ico'), wxBITMAP_TYPE_ICO))
#         except:
#             pass
# 
# 
#     def createDefaultGlobalConfig(self, globalConfigLoc):
#         self.globalConfig.createEmptyConfig(globalConfigLoc)
#         self.globalConfig.fillWithDefaults()
# 
#         wikidPadHelp = os.path.join(self.wikiAppDir, 'WikidPadHelp',
#                 'WikidPadHelp.wiki')
# 
#         self.globalConfig.set("main", "wiki_history", wikidPadHelp)
#         self.globalConfig.set("main", "last_wiki", wikidPadHelp)
# 
#         self.globalConfig.set("main", "last_active_dir", os.getcwd())
# 
# 
#     def getGlobalConfigSubDir(self):
#         return self.globalConfigSubDir
#     
#     def getGlobalConfig(self):
#         return self.globalConfig
#         
#     def getLowResources(self):
#         """
#         Return state of the low resources global setting
#         """
#         return self.lowResources
# 
#     def getIconCache(self):
#         """
#         Return the icon cache object
#         """
#         return self.iconCache
#         
#     def getCollator(self):
#         return self.collator
# 
# 
# 
class ErrorFrame(wxFrame):
   def __init__(self, parent, id, title):
      wxFrame.__init__(self, parent, -1, title, size = (300, 200),
                       style=wxDEFAULT_FRAME_STYLE|wxNO_FULL_REPAINT_ON_RESIZE)
      dlg_m = wxMessageDialog(self, "%s. %s." % ("Error starting wikidPad", e), 'Error!', wxOK)
      dlg_m.ShowModal()
      dlg_m.Destroy()
      self.Close()

class Error(wxApp):   
   def OnInit(self):
      errorFrame = ErrorFrame(None, -1, "Error")
      self.SetTopWindow(errorFrame)
      return False

app = None
exception = None



try:
    app = App(0)
    app.MainLoop()
    srePersistent.saveCodeCache()
    
except Exception, e:
   traceback.print_exc()
   exception = e
   error = Error(0)
   error.MainLoop()
   
sys.exit()
