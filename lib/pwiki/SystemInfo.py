import os, traceback

import wx


# Bug workaround: In wxPython 2.6 these constants weren't defined
#    in 2.8 they are defined under a different name and with different values

try:
    wxWINDOWS_NT = wx.OS_WINDOWS_NT
except AttributeError:
    wxWINDOWS_NT = 18   # For wx.GetOsVersion()
    
try:
    wxWIN95 = wx.OS_WINDOWS_9X
except AttributeError:
    wxWIN95 = 20   # For wx.GetOsVersion(), this includes also Win 98 and ME


# Placed here to avoid circular dependency with StringOps
def isUnicode():
    """
    Return if GUI is in unicode mode
    """
    return wx.PlatformInfo[2] == "unicode"

def isOSX():
    """
    Return if running on Mac OSX
    """
    return '__WXMAC__' in wx.PlatformInfo
    
def isLinux():
    """
    Return if running on Linux system
    """
    try:
        return os.uname()[0] == "Linux"
    except AttributeError:
        return False


_ISWIN9x = wx.GetOsVersion()[0] == wxWIN95
_ISWINNT = wx.GetOsVersion()[0] == wxWINDOWS_NT

def isWin9x():
    """
    Returns True if OS is Windows 95/98/ME
    """
    return _ISWIN9x

def isWinNT():
    """
    Returns True if OS is Windows NT/2000/XP...
    """
    return _ISWINNT

def isWindows():
    return _ISWIN9x or _ISWINNT


