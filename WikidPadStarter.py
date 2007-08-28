#!/bin/python

import sys, os, traceback, os.path, glob, shutil   # , gettext
os.stat_float_times(True)

VERSION_STRING = "wikidPad 1.9beta9"

if not hasattr(sys, 'frozen'):
    sys.path.append("lib")

import ExceptionLogger
ExceptionLogger.startLogger(VERSION_STRING)


# ## import hotshot
# ## _prof = hotshot.Profile("hotshot.prf")

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])),
        "gadfly.zip"))
# print "sys.path + ", os.path.join(os.path.abspath(sys.argv[0]), "gadfly.zip")

import wx

from pwiki import srePersistent
srePersistent.loadCodeCache()

from pwiki.MainApp import App, findDirs



if len(sys.argv) == 2 and sys.argv[1] == "--deleteconfig":
    # Special option, called by deinstaller on request to delete personal
    # configuration files
    
    # We need a dummy app to call findDirs()
    dummyApp = wx.App(0)
    dummyApp.SetAppName("WikidPad")

    wikiAppDir, globalConfigDir = findDirs()

    if globalConfigDir is None:
        sys.exit(1)
        
    try:
        try:
            globalConfigSubDir = os.path.join(globalConfigDir, "WikidPadGlobals")
            shutil.rmtree(globalConfigSubDir, True)
        except:
            pass

        try:
            globalConfigSubDir = os.path.join(globalConfigDir, ".WikidPadGlobals")
            shutil.rmtree(globalConfigSubDir, True)
        except:
            pass

#         subfiles = glob.glob(os.path.join(globalConfigSubDir, "*"))
#         for f in subfiles:
#             try:
#                 os.remove(f)
#             except:
#                 pass
#         try:
#             os.rmdir(globalConfigSubDir)
#         except:
#             pass

        try:
            os.remove(os.path.join(globalConfigDir, "WikidPad.config"))
        except:
            pass

        try:
            os.remove(os.path.join(globalConfigDir, ".WikidPad.config"))
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
else:
    # Dummy localization function
    def N_(s):
        return s
    def _(s):
        return s

    __builtins__["N_"] = N_
    __builtins__["_"] = _

    del _
    del N_

#     # Start initial localization support before reading config
#     gettext.install("WikidPad", os.path.join(wikiAppDir, "Lang"), True)



class ErrorFrame(wx.Frame):
   def __init__(self, parent, id, title):
      wx.Frame.__init__(self, parent, -1, title, size = (300, 200),
                       style=wx.DEFAULT_FRAME_STYLE|wx.NO_FULL_REPAINT_ON_RESIZE)
      dlg_m = wx.MessageDialog(self, "%s. %s." % (_(u"Error starting WikidPad"), e),
            _(u'Error!'), wx.OK)
      dlg_m.ShowModal()
      dlg_m.Destroy()
      self.Close()

class Error(wx.App):   
   def OnInit(self):
      errorFrame = ErrorFrame(None, -1, _(u"Error"))
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
