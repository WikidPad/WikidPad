"""
OS abstraction
"""

import os, shutil, os.path, re, traceback
import wx

from . import SystemInfo
from .StringOps import mbcsEnc, urlQuote, pathnameFromUrl, pathEnc


# WindowsHacks for some OS specials

if SystemInfo.isWindows():
    try:
        from . import WindowsHacks
    except:
        if SystemInfo.isWindows():
            traceback.print_exc()
        WindowsHacks = None
else:
    WindowsHacks = None

# GtkHacks for the Clipboard Catcher


try:
    import LinuxHacks
except:
    if SystemInfo.isLinux():
        traceback.print_exc()
    LinuxHacks = None


try:
    from . import GtkHacks
except:
    import ExceptionLogger
    ExceptionLogger.logOptionalComponentException(
            "Initialize GTK hacks in OsAbstract.py")
    GtkHacks = None




# Define startFile
if SystemInfo.isWindows():
    if WindowsHacks:
        startFile = WindowsHacks.startFile
    else:
        def startFile(mainControl, link):
            os.startfile(mbcsEnc(link, "replace")[0])
else:
    def startFile(mainControl, link):
        # We need mainControl only for this version of startFile()

        startPath = mainControl.getConfig().get("main", "fileLauncher_path", "")
        if startPath == "":
            wx.LaunchDefaultBrowser(link)
            return

        if link.startswith("file:"):
            link = pathnameFromUrl(link)

        os.spawnlp(os.P_NOWAIT, startPath, startPath, link)


# Define copyFile
if SystemInfo.isWinNT() and WindowsHacks:
    copyFile = WindowsHacks.copyFile
    moveFile = WindowsHacks.moveFile
    deleteFile = WindowsHacks.deleteFile
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


    def deleteFile(path):
        """
        Delete file or directory  path.
        """
        # TODO: Check for directories
        # os.rmdir(path) ?
        if os.path.isfile(path) or os.path.islink(path):
            os.unlink(path)
        elif os.path.isdir(path):
            os.rmdir(path)


# Define samefile
if SystemInfo.isWindows():
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


if WindowsHacks:
    def normalizePath(path):
        return WindowsHacks.getLongPath(os.path.abspath(path)).lower()
else:
    def normalizePath(path):
        return os.path.normcase(os.path.abspath(path))



# Define checkForOtherInstances
# If defined properly it returns a list of process identifier of other WikidPad
# processes. This list should be empty if option "Single process per user"
# is selected. If it is not, there is an error.

if WindowsHacks:
    checkForOtherInstances = WindowsHacks.checkForOtherInstances
else:
    def checkForOtherInstances():
        return []


# Define setCpuAffinity, getCpuAffinity and getCpuCount

if WindowsHacks:
    setCpuAffinity = WindowsHacks.setCpuAffinity
    getCpuAffinity = WindowsHacks.getCpuAffinity
    getCpuCount = WindowsHacks.getCpuCount
elif LinuxHacks:
    setCpuAffinity = LinuxHacks.setCpuAffinity
    getCpuAffinity = LinuxHacks.getCpuAffinity
    getCpuCount = LinuxHacks.getCpuCount
else:
    def setCpuAffinity(cpuIndexSeq):
        return False
    
    def getCpuAffinity():
        return None

    def getCpuCount():
        return 0

INITIAL_CPU_AFFINITY = getCpuAffinity()



# Define createInterceptCollection, createClipboardInterceptor  (may return None)
# Define supportsClipboardInterceptor

# Fallback def.
def supportsClipboardInterceptor():
    return False
def createInterceptCollection(interceptors=None):
    return None
def createClipboardInterceptor(callingWindow):
    return None

if SystemInfo.isWindows():
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
    translateAcceleratorByKbLayout = WindowsHacks.translateAcceleratorByKbLayout
else:
    def translateAcceleratorByKbLayout(accStr):
        return accStr
