# import hotshot
# _prof = hotshot.Profile("hotshot.prf")

import os, traceback

import wx

# from MiscEvent import KeyFunctionSinkAR
from pwiki.wxHelper import appendToMenuByMenuDesc

from pwiki.WindowLayout import LayeredControlPanel
from pwiki.Configuration import isWindows

import DatedWikiWordFilters

from TimelinePanel import TimelinePanel
from CalendarPanel import CalendarPanel


class TimeViewCtrl(wx.Notebook):
    def __init__(self, parent, ID, mainControl):
        wx.Notebook.__init__(self, parent, ID)

        self.mainControl = mainControl
        
        wikiWordFilter = DatedWikiWordFilters.DatedWikiWordFilterModified()


        self.modifiedPanel = LayeredControlPanel(self, -1)
        tlp = TimelinePanel(self.modifiedPanel, -1, self.mainControl,
                wikiWordFilter)
#         tlp = CalendarPanel(self.modifiedPanel, -1, self.mainControl,
#                 wikiWordFilter)
        self.modifiedPanel.setSubControl("timeline", tlp)

        self.modifiedPanel.switchSubControl("timeline")

#         self.modifiedPanel = TimelinePanel(self, -1, self.mainControl, wikiWordFilter)
#         self.modifiedPanel = CalendarPanel(self, -1, self.mainControl, wikiWordFilter)
        self.AddPage(self.modifiedPanel, wikiWordFilter.getDisplayName())
        
        wx.EVT_CONTEXT_MENU(self, self.OnContextMenu)


    def close(self):
        """
        """
        pass

    def miscEventHappened(self, miscevt):
        """
        Handle misc events
        """
        pass


    def setLayerVisible(self, vis):
        pass


    def OnContextMenu(self, evt):
        pos = self.ScreenToClient(wx.GetMousePosition())
        tab = self.HitTest(pos)[0]
        if tab == wx.NOT_FOUND:
            return
        
        activeWindow = self.GetPage(tab).getCurrentSubControl()
        # Show menu
        activeWindow.showContextMenuOnTab()

