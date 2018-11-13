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
    Return if GUI is in unicode mode. Legacy function, TODO 2.5: Remove
    """
    return True

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
    Returns True if OS is Windows 95/98/ME. Legacy function, TODO 2.5: Remove
    """
    return False

def isWinNT():
    """
    Returns True if OS is Windows NT/2000/XP... Legacy function, TODO 2.5: Remove
    """
    return _ISWINNT

def isWindows():
    return _ISWINNT


