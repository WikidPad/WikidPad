#!/bin/python

import sys, os, traceback, os.path, glob
os.stat_float_times(True)

if not hasattr(sys, 'frozen'):
    sys.path.append("lib")

from pwiki import srePersistent
srePersistent.loadCodeCache()

## import hotshot
## _prof = hotshot.Profile("hotshot.prf")

# To ensure unicode selection, works only for me (Michael)
# 
# if not hasattr(sys, 'frozen'):
#     sys.path =  \
#             [r"C:\Programme\Python23\Lib\site-packages\wx-2.6-msw-unicode"] + sys.path


sys.path.append(os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "gadfly.zip"))
# print "sys.path + ", os.path.join(os.path.abspath(sys.argv[0]), "gadfly.zip")


from wxPython.wx import *
import wxPython.xrc as xrc

from pwiki.PersonalWikiFrame import PersonalWikiFrame
from pwiki.StringOps import mbcsDec
from pwiki.CmdLineAction import CmdLineAction

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
        self.wikiFrame = PersonalWikiFrame(None, -1, "WikidPad", wikiAppDir,
                globalConfigDir, CmdLineAction(sys.argv[1:]))

        self.SetTopWindow(self.wikiFrame)
        ## _prof.stop()

        # set the icon of the app
        try:
            self.wikiFrame.SetIcon(wxIcon(os.path.join('icons', 'pwiki.ico'),
                    wxBITMAP_TYPE_ICO))
        except:
            pass


        return True

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
