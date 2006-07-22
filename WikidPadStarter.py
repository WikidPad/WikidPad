#!/bin/python

import sys, os, traceback, os.path, glob, time
os.stat_float_times(True)

VERSION_STRING = "wikidPad 1.7beta8"

if not hasattr(sys, 'frozen'):
    sys.path.append("lib")

import ExceptionLogger
ExceptionLogger.startLogger(VERSION_STRING)


## import hotshot
## _prof = hotshot.Profile("hotshot.prf")

# To ensure unicode selection, works only for me (Michael)

# if not hasattr(sys, 'frozen'):
#     sys.path =  \
#             [r"C:\Programme\Python23\Lib\site-packages\wx-2.6-msw-unicode"] + sys.path


sys.path.append(os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "gadfly.zip"))
# print "sys.path + ", os.path.join(os.path.abspath(sys.argv[0]), "gadfly.zip")


from wxPython.wx import *
import wxPython.xrc as xrc



# openThisWiki = None
# openThisWikiWord = None
# if len(sys.argv) > 1:
#    openThisWiki = sys.argv[1]
#    if openThisWiki.startswith("wiki:"):
#       openThisWiki = urllib.url2pathname(openThisWiki)
#       openThisWiki = openThisWiki.replace("wiki:", "")
# 
#    if len(sys.argv) > 2:
#       openThisWikiWord = sys.argv[2]


# global exception control

# class StdErrReplacement:
#     def write(self, data):
#         global _exceptionDestDir, _exceptionSessionTimeStamp, _exceptionOccurred
#         global _previousExcepthook
# 
#         print "onWrite", repr(_exceptionDestDir)
# 
#         try:
#             f = open(os.path.join(_exceptionDestDir, "WikidPad_Error.log"), "a")
#             try:
#                 if not _exceptionOccurred:
#                     # (Only write for first exception in session) This isn't an exception
#                     f.write(_exceptionSessionTimeStamp)
#                     ## _exceptionOccurred = True
#                 sys.stdout.write(data)
#                 f.write(data)
#             finally:
#                 f.close()
#         except:
#             pass # TODO
# 
#     def writelines(self, it):
#         for l in it:
#             self.write(l)
#             
# #     def __getattr__(self, attr):
# #         print "__getattr__", repr(attr)
# #         return None
# 
# 
# class ExceptionHandler:
#     def __init__(self):
#         global _exceptionDestDir, _exceptionSessionTimeStamp, _exceptionOccurred
#         global _previousExcepthook
#         self._exceptionDestDir = _exceptionDestDir
#         self._exceptionSessionTimeStamp = _exceptionSessionTimeStamp
#         self._exceptionOccurred = _exceptionOccurred
#         self._previousExcepthook = _previousExcepthook
#         self.traceback = traceback
# 
# 
#     def __call__(self, typ, value, trace):
#     #     global _exceptionDestDir, _exceptionSessionTimeStamp, _exceptionOccurred
#     #     global _previousExcepthook
#     #     global _traceback2
#         import WikidPadStarter
#     
#         try:
#             print "onException", repr(WikidPadStarter.traceback), repr(WikidPadStarter._exceptionDestDir)
#     ##        traceback.print_exception(typ, value, trace, file=sys.stdout)
#             f = open(os.path.join(WikidPadStarter._exceptionDestDir, "WikidPad_Error.log"), "a")
#             try:
#                 if not WikidPadStarter._exceptionOccurred:
#                     # Only write for first exception in session
#                     f.write(WikidPadStarter._exceptionSessionTimeStamp) 
#                     WikidPadStarter._exceptionOccurred = True
#                 WikidPadStarter.traceback.print_exception(typ, value, trace, file=f)
#                 WikidPadStarter.traceback.print_exception(typ, value, trace, file=sys.stdout)
#             finally:
#                 f.close()
#         except:
#             print "Exception occurred during global exception handling:"
#             WikidPadStarter.traceback.print_exc(file=sys.stdout)
#             print "Original exception:"
#             WikidPadStarter.traceback.print_exception(typ, value, trace, file=sys.stdout)
#             WikidPadStarter._previousExcepthook(typ, value, trace)
# 
# 
# _exceptionDestDir = os.path.dirname(os.path.abspath(sys.argv[0]))
# _exceptionSessionTimeStamp = \
#         time.strftime("\n\nVersion: '" + VERSION_STRING +
#                 "' Session start: %Y-%m-%d %H:%M:%S\n")
# _exceptionOccurred = False
# 
# 
# _previousExcepthook = sys.excepthook
# # sys.excepthook = ExceptionHandler()   # onException
# 
# _previousStdErr = sys.stderr
# sys.stderr = StdErrReplacement()


from pwiki import srePersistent
srePersistent.loadCodeCache()

from pwiki.PersonalWikiFrame import PersonalWikiFrame
from pwiki.StringOps import mbcsDec
from pwiki.CmdLineAction import CmdLineAction


def findDirs():
    """
    Returns tuple (wikiAppDir, globalConfigDir)
    """
    wikiAppDir = None

    try:
        wikiAppDir = os.path.dirname(os.path.abspath(sys.argv[0]))
        if not wikiAppDir:
            wikiAppDir = r"C:\Program Files\WikidPad"
            
        # This allows to keep the program with config on an USB stick
        if os.path.exists(os.path.join(wikiAppDir, "WikidPad.config")):
            globalConfigDir = wikiAppDir
        else:
            globalConfigDir = os.environ.get("HOME")
            if not (globalConfigDir and os.path.exists(globalConfigDir)):
                globalConfigDir = os.environ.get("USERPROFILE")
                if not (globalConfigDir and os.path.exists(globalConfigDir)):
                    # Instead of checking USERNAME, the user config dir. is
                    # now used
                    globalConfigDir = wxStandardPaths.Get().GetUserConfigDir()
#                     user = os.environ.get("USERNAME")
#                     if user:
#                         globalConfigDir = r"c:\Documents And Settings\%s" % user
    finally:
        pass
#     except Exception, e:
#         return None, None

    if not globalConfigDir:
        globalConfigDir = wikiAppDir

#     if not globalConfigDir or not os.path.exists(globalConfigDir):
#         globalConfigDir = "C:\Windows"
        
    # mbcs decoding
    if wikiAppDir is not None:
        wikiAppDir = mbcsDec(wikiAppDir, "replace")[0]

    if globalConfigDir is not None:
        globalConfigDir = mbcsDec(globalConfigDir, "replace")[0]
        
    ExceptionLogger._exceptionDestDir = globalConfigDir

    return (wikiAppDir, globalConfigDir)




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

        sys.exit(0)
    
    except:
        sys.exit(1)


class App(wxApp): 
    def __init__(self, *args, **kwargs):
        wxApp.__init__(self, *args, **kwargs)
        self.SetAppName("WikidPad")

    def OnInit(self):
        ## _prof.start()
        appdir = os.path.dirname(os.path.abspath(sys.argv[0]))
        rf = open(os.path.join(appdir, "WikidPad.xrc"), "r")
        rd = rf.read()
        rf.close()

        res = xrc.wxXmlResource.Get()
        res.SetFlags(0)
        res.LoadFromString(rd)
        
        wikiAppDir, globalConfigDir = findDirs()
        
        if not globalConfigDir or not os.path.exists(globalConfigDir):
            raise Exception(u"Error initializing environment, couldn't locate "
                    u"global config directory")
                    
        self.globalConfigDir = globalConfigDir

        self.globalConfigSubDir = os.path.join(self.globalConfigDir,
                ".WikidPadGlobals")
        if not os.path.exists(self.globalConfigSubDir):
            os.mkdir(self.globalConfigSubDir)


        self.wikiFrame = PersonalWikiFrame(None, -1, "WikidPad", wikiAppDir,
                globalConfigDir, self.globalConfigSubDir,
                CmdLineAction(sys.argv[1:]))

        self.SetTopWindow(self.wikiFrame)
        ## _prof.stop()

        # set the icon of the app
        try:
            self.wikiFrame.SetIcon(wxIcon(os.path.join(wikiAppDir, 'icons',
                    'pwiki.ico'), wxBITMAP_TYPE_ICO))
        except:
            pass

        return True
        
        
    def OnExit(self):
#         global _exceptionDestDir, _exceptionOccurred
        if ExceptionLogger._exceptionOccurred and hasattr(sys, 'frozen'):
            wxMessageBox("An error occurred during this session\nSee file %s" %
                    os.path.join(ExceptionLogger._exceptionDestDir, "WikidPad_Error.log"),
                    "Error", style = wxOK)


    def getGlobalConfigSubDir(self):
        return self.globalConfigSubDir



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
