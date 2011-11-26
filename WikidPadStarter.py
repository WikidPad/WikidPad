#!/bin/python


# try:
#     import psyco
#     psyco.full()
# except ImportError:
#     pass
#     traceback.print_exc()



import sys, os, traceback, os.path, glob, shutil, imp, warnings, ConfigParser
os.stat_float_times(True)

if not hasattr(sys, 'frozen'):
    sys.path.insert(0, "lib")
#     sys.path.append("lib")
#     sys.path.append(r"C:\Daten\Projekte\Wikidpad\Current\lib")

    os.environ["PATH"] = os.path.dirname(os.path.abspath(sys.argv[0])) + \
            os.pathsep + os.environ["PATH"]

from Consts import CONFIG_FILENAME, CONFIG_GLOBALS_DIRNAME

# imports VERSION_TUPLE for plugins which may expect it here
from Consts import VERSION_STRING, VERSION_TUPLE

import __builtin__

# Dummies for localization
def N_(s):
    return s
__builtin__.N_ = N_
del N_


__builtin__._ = N_


del __builtin__


# create a Trace object
# import trace
# __builtins__["tracer"] = trace.Trace(
#     ignoredirs=[sys.prefix, sys.exec_prefix],
#     trace=1,
#     count=0)



import ExceptionLogger
ExceptionLogger.startLogger(VERSION_STRING)


# ## import hotshot
# ## _prof = hotshot.Profile("hotshot.prf")

def _putPathPrepends():
    """
    Process file "binInst.ini" in installation directory, if present.
    The file is created by the Windows binary installer (Inno Setup)
    and contains adjustments to the installation, namely additional
    ZIP-files to add to sys.path.
    """
    parser = ConfigParser.RawConfigParser()
    try:
        f = open(os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])),
                "binInst.ini"), "rU")
        parser.readfp(f)
        f.close()

        try:
            for opt, val in parser.items("sysPathPrepend"):
                sys.path.insert(0, os.path.join(os.path.dirname(
                        os.path.abspath(sys.argv[0])), val))
        except ConfigParser.NoSectionError:
            pass

        try:
            for opt, val in parser.items("sysPathAppend"):
                sys.path.append(os.path.join(os.path.dirname(
                        os.path.abspath(sys.argv[0])), val))
        except ConfigParser.NoSectionError:
            pass

    except IOError:
        pass  # Probably file not present


_putPathPrepends()


sys.path.append(os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])),
        "gadfly.zip"))
# sys.path.append(r"C:\Daten\Projekte\Wikidpad\Current\gadfly.zip")
# print "sys.path + ", os.path.join(os.path.abspath(sys.argv[0]), "gadfly.zip")


import wx

# cmore addition
if (not hasattr(wx, "NO_3D")):
    wx.NO_3D=0


# from pwiki import srePersistent
# srePersistent.loadCodeCache()

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
            globalConfigSubDir = os.path.join(globalConfigDir,
                    CONFIG_GLOBALS_DIRNAME)
            shutil.rmtree(globalConfigSubDir, True)
        except:
            pass

        try:
            globalConfigSubDir = os.path.join(globalConfigDir,
                    "." + CONFIG_GLOBALS_DIRNAME)
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
            os.remove(os.path.join(globalConfigDir, CONFIG_FILENAME))
        except:
            pass

        try:
            os.remove(os.path.join(globalConfigDir, "." + CONFIG_FILENAME))
        except:
            pass
            
        if wikiAppDir != globalConfigDir:
            try:
                os.rmdir(globalConfigDir)
            except:
                pass

        sys.exit(0)
    
    except SystemExit:
        raise
    except:
        sys.exit(1)

elif len(sys.argv) >= 3 and sys.argv[1] == "--updtrans":
    try:
        # Update translation from .pot file
        args = sys.argv[2:]
    
        # We need a dummy app to call findDirs()
        dummyApp = wx.App(0)
        dummyApp.SetAppName("WikidPad")
    
        wikiAppDir, globalConfigDir = findDirs()
    
        if len(args) == 1:
            args.append(os.path.join(wikiAppDir, "WikidPad.pot"))
        
        from pwiki import I18nPoUpdater
        I18nPoUpdater.main(args)

        sys.exit(0)
    except SystemExit:
        raise
    except:
        traceback.print_exc()
        sys.exit(1)
   
    

#     # Start initial localization support before reading config
#     gettext.install("WikidPad", os.path.join(wikiAppDir, "Lang"), True)



class ErrorFrame(wx.Frame):
    def __init__(self, parent, id, title):
        wx.Frame.__init__(self, parent, -1, title, size = (300, 200),
                style=wx.DEFAULT_FRAME_STYLE|wx.NO_FULL_REPAINT_ON_RESIZE)
        dlg_m = wx.MessageDialog(self, _(u"Error starting WikidPad"),
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





def main():
    try:
        app = App(0)
        app.MainLoop()
    #     srePersistent.saveCodeCache()
        
    except Exception, e:
        traceback.print_exc()
        exception = e
        error = Error(0)
        error.MainLoop()
       
    sys.exit()

