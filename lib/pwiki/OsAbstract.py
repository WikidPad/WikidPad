"""
OS abstraction
"""

import os, shutil, os.path, traceback
import wx

import Configuration
from StringOps import mbcsEnc, urlQuote, pathnameFromUrl, URL_RESERVED, pathEnc


# import WindowsHacks

try:
    import WindowsHacks
except:
    if Configuration.isWindows():
        traceback.print_exc()
    WindowsHacks = None


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


# Define samefile
if Configuration.isWindows():
    if WindowsHacks:
        def samefile(path1, path2):
            # Not fully reliable. Does anybody know something better?
            return WindowsHacks.getLongPath(path1) == WindowsHacks.getLongPath(path2)
    else:
        def samefile(path1, path2):
            return os.path.abspath(path1) == os.path.abspath(path2)
else:
    samefile = os.path.samefile





