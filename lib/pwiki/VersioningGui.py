import traceback

import wx, wx.xrc

import Consts
from WikiExceptions import *

from .wxHelper import GUI_ID, EnhancedListControl

from .WindowLayout import LayeredControlPanel

from .WikiTxtCtrl import WikiTxtCtrl



class VersionExplorerPresenterControl(wx.Panel):
    """
    Panel which can be added to presenter in main area panel as tab showing
    search results.
    """
    def __init__(self, presenter, mainControl, ID):
        super(VersionExplorerPresenterControl, self).__init__(presenter, ID)

        self.mainControl = mainControl
        self.presenter = presenter

        mainsizer = wx.BoxSizer(wx.VERTICAL)
        self.splitter = wx.SplitterWindow(self, -1)
        mainsizer.Add(self.splitter, 1, wx.ALL | wx.EXPAND, 0)        

        self.editCtrl = WikiTxtCtrl(self.presenter, self.splitter, -1)

        self.versionListCtrl = EnhancedListControl(self.splitter, -1,
                style=wx.LC_REPORT | wx.LC_SINGLE_SEL)


    def close(self):
        self.editCtrl.close()


