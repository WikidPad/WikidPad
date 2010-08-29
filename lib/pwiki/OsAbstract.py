"""
OS abstraction
"""

import os, shutil, os.path, traceback
import wx

from . import Configuration
from .StringOps import mbcsEnc, urlQuote, pathnameFromUrl, URL_RESERVED, pathEnc


# import WindowsHacks

try:
    import WindowsHacks
except:
    if Configuration.isWindows():
        traceback.print_exc()
    WindowsHacks = None

try:
    import GtkHacks
except:
#     traceback.print_exc()
    GtkHacks = None


# Define startFile
if Configuration.isWindows():
    if Configuration.isWinNT() and Configuration.isUnicode() and WindowsHacks:
        startFile = WindowsHacks.startFile
    else:
        def startFile(mainControl, link):
            os.startfile(mbcsEnc(link, "replace")[0])
else:
    def startFile(mainControl, link):
        # We need mainControl only for this version of startFile()
        
#         # The link was unquoted(???), so URL-quote it again
#         if link.startswith("http:") or link.startswith("https:") or \
#                 link.startswith("mailto:") or link.startswith("ftp:") or \
#                 link.startswith("file:"):
#             link = urlQuote(link, URL_RESERVED)

        startPath = mainControl.getConfig().get("main", "fileLauncher_path", u"")
        if startPath == u"":
            wx.LaunchDefaultBrowser(link)
            return

        if link.startswith("file:"):
            link = pathnameFromUrl(link)

        os.spawnlp(os.P_NOWAIT, startPath, startPath, link)


# Define copyFile
if Configuration.isWinNT() and WindowsHacks:
    copyFile = WindowsHacks.copyFile
    moveFile = WindowsHacks.moveFile
else:
    # TODO Mac version    
    def copyFile(srcPath, dstPath):
        """
        Copy file from srcPath to dstPath. dstPath may be overwritten if
        existing already. dstPath must point to a file, not a directory.
        If some directories in dstPath do not exist, they are created.

        This currently just calls shutil.copy2() TODO!
        """
        dstDir = os.path.dirname(dstPath)
            
        if not os.path.exists(pathEnc(dstDir)):
            os.makedirs(dstDir)
    
        shutil.copy2(srcPath, dstPath)

    def moveFile(srcPath, dstPath):
        """
        Move file from srcPath to dstPath. dstPath may be overwritten if
        existing already. dstPath must point to a file, not a directory.
        If some directories in dstPath do not exist, they are created.
        """
        dstDir = os.path.dirname(dstPath)        
    
        if not os.path.exists(pathEnc(dstDir)):
            os.makedirs(dstDir)
    
        shutil.move(srcPath, dstPath)  


# Define samefile
if Configuration.isWindows():
    if WindowsHacks:
        def samefile(path1, path2):
            # Not fully reliable. Does anybody know something better?
            return WindowsHacks.getLongPath(path1).lower() == \
                    WindowsHacks.getLongPath(path2).lower()
    else:
        def samefile(path1, path2):
            return os.path.abspath(path1) == os.path.abspath(path2)
else:
    samefile = os.path.samefile



# Define checkForOtherInstances
# If defined properly it returns a list of process identifier of other WikidPad
# processes. This list should be empty if option "Single process per user"
# is selected. If it is not, there is an error.

if WindowsHacks:
    checkForOtherInstances = WindowsHacks.checkForOtherInstances
else:
    def checkForOtherInstances():
        return []



# Define createInterceptCollection, createClipboardInterceptor  (may return None)
# Define supportsClipboardInterceptor

# Fallback def.
def supportsClipboardInterceptor():
    return False
def createInterceptCollection(interceptors=None):
    return None
def createClipboardInterceptor(callingWindow):
    return None

if Configuration.isWindows():
    if WindowsHacks:
        def supportsClipboardInterceptor():
            return True
        def createInterceptCollection(interceptors=None):
            return WindowsHacks.WinProcInterceptCollection(interceptors)
        def createClipboardInterceptor(callingWindow):
            return WindowsHacks.ClipboardCatchIceptor(callingWindow)
else:
    if GtkHacks:
        def supportsClipboardInterceptor():
            return True
        def createInterceptCollection(interceptors=None):
            return GtkHacks.FakeInterceptCollection(interceptors)
        def createClipboardInterceptor(callingWindow):
            return GtkHacks.ClipboardCatchFakeIceptor(callingWindow)
        


