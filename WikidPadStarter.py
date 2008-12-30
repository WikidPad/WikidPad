#!/bin/python

import sys, os, traceback, os.path, glob
os.stat_float_times(True)


# VERSION_TUPLE is structured (branch, major, minor, stateAndMicro, helper)
# where branch is normally string "wikidPad", but should be changed if somebody
# develops a derived version of WikidPad.
# 
# major and minor are the main versions,
# stateAndMicro is:
#     between 0 and 99 for "beta"
#     between 100 and 199 for "rc" (release candidate)
#     200 for "final"
#     
#     the unit and tenth place form the micro version.
# 
# helper is a sub-micro version, if needed, normally 0.
# 
# Examples:
# (1, 8, 107, 0) is 1.8rc7
# (1, 9, 4, 0) is 1.9beta4
# (1, 9, 4, 2) is something after 1.9beta4
# (2, 0, 200, 0) is 2.0final

VERSION_TUPLE = ("wikidPad", 1, 8, 119, 1)

VERSION_STRING = "wikidPad 1.8rc19_1"

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

import wx
# from wxPython.wx import wxApp, wxMessageDialog, wxDEFAULT_FRAME_STYLE, \
#         wxNO_FULL_REPAINT_ON_RESIZE, wxFrame, wxOK


from pwiki import srePersistent
srePersistent.loadCodeCache()

from pwiki.MainApp import App, findDirs



if len(sys.argv) == 2 and sys.argv[1] == "--deleteconfig":
    # Special option, called by deinstaller on request to delete personal
    # configuration files
    dummyApp = wx.App(0)
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


class ErrorFrame(wx.Frame):
   def __init__(self, parent, id, title):
      wx.Frame.__init__(self, parent, -1, title, size = (300, 200),
                       style=wx.DEFAULT_FRAME_STYLE|wx.NO_FULL_REPAINT_ON_RESIZE)
      dlg_m = wx.MessageDialog(self, "%s. %s." % ("Error starting wikidPad", e),
            'Error!', wx.OK)
      dlg_m.ShowModal()
      dlg_m.Destroy()
      self.Close()

class Error(wx.App):   
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
