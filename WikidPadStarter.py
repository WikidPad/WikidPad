#!/bin/python

import sys, os, traceback, os.path, glob, shutil, imp, warnings
os.stat_float_times(True)

if not hasattr(sys, 'frozen'):
    sys.path.append("lib")
#     sys.path.append(r"C:\Daten\Projekte\Wikidpad\Next20\lib")

from Consts import CONFIG_FILENAME, CONFIG_GLOBALS_DIRNAME


# Switch off warnings about my special import management
warnings.simplefilter('ignore', RuntimeWarning)


_realImport = __builtins__["__import__"]

def _retrieveModule(nameComps, path):
    """
    Returns <module>, <subPath (if package)>
    """
    if sys.modules.has_key(".".join(nameComps)):
        foundModule = sys.modules[".".join(nameComps)]  # ???
    else:
        foundModule = None

    
    if len(nameComps) == 0:
        f, impPath, desc = imp.find_module("__init__", [path])
    else:
#         print "--_retrieveModule13", repr((nameComps, path))
        try:
            f, impPath, desc = imp.find_module(nameComps[-1], [path])
#             print "--_retrieveModule15", repr((f, impPath, desc))
        finally:
            pass

    if desc[2] == imp.SEARCH_ERROR:
#         print "--_retrieveModule27"
        raise ImportError

    if desc[2] != imp.PKG_DIRECTORY:
        if foundModule is not None:
            f.close()
            return foundModule, None

        try:
#             print "--_retrieveModule32"
            module = imp.load_module(".".join(nameComps), f, impPath,
                    desc)
#             print "--_retrieveModule34"
            sys.modules[".".join(nameComps)] = module
#             print "--_retrieveModule36"
            return module, None
        finally:
            if f is not None:
                f.close()
    else:
        path = impPath
        if foundModule is not None:
            return foundModule, path

        f, impPath, desc = imp.find_module("__init__", [path])
        try:
            module = imp.load_module(".".join(nameComps), f, impPath,
                    desc)
            sys.modules[".".join(nameComps)] = module
            return module, path
        finally:
            if f is not None:
                f.close()



def _retrieveFinalModule(modComps, path, importComps):
    if importComps == [""]:
        importComps = []

#     print "--_retrieveFinalModule2", repr((modComps, importComps))

    if sys.modules.has_key(".".join(modComps + importComps)):
#         print "--_retrieveFinalModule5"
        module = sys.modules[".".join(modComps + importComps)]
        return module, os.path.dirname(module.__file__)  # ???

    if sys.modules.has_key(".".join(modComps)):
        module = sys.modules[".".join(modComps)]  # ???
    else:
        f, impPath, desc = imp.find_module("__init__", [path])
        try:
            module = imp.load_module(".".join(modComps), f, impPath,
                    desc)
            sys.modules[".".join(modComps)] = module
        finally:
            if f is not None:
                f.close()

#     print "--_retrieveFinalModule14", repr((modComps, importComps, path))

    if len(importComps) == 0:
        return module, path

    while len(importComps) > 0:
        parentModule = module

#         print "--_retrieveFinalModule33", repr((modComps + importComps[:1], path))
        module, nextPath = _retrieveModule(modComps + importComps[:1], path)
#         print "--_retrieveFinalModule35", repr((module, nextPath))
        if module is None:
            raise ImportError()  # TODO Own error message

        if not parentModule.__dict__.has_key(importComps[0]):
            parentModule.__dict__[importComps[0]] = module

        path = nextPath
        modComps.append(importComps[0])
        del importComps[0]

        if nextPath is None:
            if len(importComps) != 0:
                raise ImportError()  # TODO Own error message

            return module, path


    return module, path



def _newImport(name, globals=None, locals=None, fromlist=None, level=-1):
    """
    Replaces the internal __import__ function to allow relaxed checks for
    relative imports in plugins.
    """
    if level <= 0:
        return _realImport(name, globals, locals, fromlist, level)
    
#         print "--import", repr((name, globals.get("__name__") if globals is not None else None,
#                 globals.get("__file__") if globals is not None else None, fromlist, level))

#     except ImportError, ie:

    modComps = globals["__name__"].split(".")
    if not modComps[0].startswith("cruelimport"): # a tag to recognize
        return _realImport(name, globals, locals, fromlist, level)
    
    imp.acquire_lock()
    try:
#         print "--_newImport4", repr((name, globals.get("__name__") if globals is not None else None,
#                 globals.get("__file__") if globals is not None else None, fromlist, level))

        ilevel = level
        path = globals["__file__"]

        while ilevel > 0 and len(modComps) > 0:
            path = os.path.dirname(path)
            del modComps[-1]
            ilevel -= 1

        if ilevel > 0:
            raise
        
        if not fromlist:   # is this possible?
            raise ie

        # if len(modComps) == 0:
            # do ?
        importComps = name.split(".")
        if importComps == [""]:
            importComps = []
            
#         print "--_newImport27", repr((modComps, path, importComps))

        module, path = _retrieveFinalModule(modComps, path, importComps)
        
#         print "--_newImport29", repr((module, path))

        for frm in fromlist:
            if frm == "*":
                continue
            if not module.__dict__.has_key(frm):
                try:
#                     print "--_newImport34", repr((modComps, frm, path))
                    submod = _retrieveModule(modComps + [frm], path)
#                     print "--_newImport37", repr(submod)
                    module.__dict__[frm] = submod
                except ImportError:
#                     print "--_newImport42"
                    pass

#         print "--_newImport49", repr((module, path))

        return module
    except:
        traceback.print_exc()
        raise
    finally:
        imp.release_lock()



__builtins__["__import__"] = _newImport

from Consts import VERSION_STRING, VERSION_TUPLE

# Dummies for localization
def N_(s):
    return s
__builtins__["N_"] = N_
del N_


__builtins__["_"] = N_



# create a Trace object
import trace
__builtins__["tracer"] = trace.Trace(
    ignoredirs=[sys.prefix, sys.exec_prefix],
    trace=1,
    count=0)



import ExceptionLogger
ExceptionLogger.startLogger(VERSION_STRING)


# ## import hotshot
# ## _prof = hotshot.Profile("hotshot.prf")

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])),
        "gadfly.zip"))
# sys.path.append(r"C:\Daten\Projekte\Wikidpad\Current\gadfly.zip")
# print "sys.path + ", os.path.join(os.path.abspath(sys.argv[0]), "gadfly.zip")


import wx

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

# 
# try:
#     import psyco
#     psyco.full()
# except ImportError:
#     traceback.print_exc()




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

