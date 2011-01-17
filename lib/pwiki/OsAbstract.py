"""
OS abstraction
"""

import os, shutil, os.path, re, traceback
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
            if WindowsHacks.getLongPath(path1).lower() == \
                    WindowsHacks.getLongPath(path2).lower():
                return True
            
            return WindowsHacks.getLongPath(os.path.abspath(path1)).lower() == \
                    WindowsHacks.getLongPath(os.path.abspath(path2)).lower()
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
        

if WindowsHacks:
    _ACCEL_KEY_MAPPING = None
    
    def translateAcceleratorByKbLayout(accStr):
        global _ACCEL_KEY_MAPPING

        cm = re.match(ur"(.+?[\+\-])(.) *$", accStr)
        if not cm:
            return accStr
        
        if not _ACCEL_KEY_MAPPING:
            # Build mapping
            
            result = {}
            
            # The order to scan for matches is important:
            # 1. Uppercase letters
            # 2. Digits
            # 3. Remaining ASCII codes
            
            for char in range(0x41, 0x5b) + range(0x30, 0x3a) + \
                    range(0x20, 0x30) + range(0x3a, 0x41) + range(0x5b, 0x7f):
                ks = WindowsHacks.VkKeyScan(unichr(char))
                vkCode = ks & 0xff
                if vkCode == 0:
                    continue
                
                targetChar = WindowsHacks.MapVirtualKey(vkCode, 2) & 0xffff
                
                if targetChar == 0:
                    continue
                
                targetChar = unichr(targetChar).upper()
                
                if targetChar in result:
                    continue

                result[targetChar] = unichr(char)

            _ACCEL_KEY_MAPPING = result

        return cm.group(1) + _ACCEL_KEY_MAPPING.get(cm.group(2), cm.group(2))



else:
    def translateAcceleratorByKbLayout(accStr):
        return accStr
