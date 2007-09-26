"""
OS abstraction
"""

import os
import wx

import Configuration
from StringOps import mbcsEnc

try:
    import WindowsHacks
except:
    WindowsHacks = None


# Define startFile
if Configuration.isWindows():
    if Configuration.isWinNT() and Configuration.isUnicode() and WindowsHacks:
        startFile = WindowsHacks.startFile
    else:
        def startFile(link):
            os.startfile(mbcsEnc(link, "replace")[0])
else:
    def startFile(link):
        wx.LaunchDefaultBrowser(link)

