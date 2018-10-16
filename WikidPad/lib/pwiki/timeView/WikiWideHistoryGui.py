import traceback

import wx, wx.xrc

from .. import Utilities
from ..wxHelper import EnhancedListControl, wxKeyFunctionSink, \
        WindowUpdateLocker, GUI_ID, appendToMenuByMenuDesc

from ..Configuration import MIDDLE_MOUSE_CONFIG_TO_TABMODE


class WikiWideHistoryPanel(EnhancedListControl):
    
    def __init__(self, parent, ID, mainControl):
        EnhancedListControl.__init__(self, parent, ID,
                style=wx.LC_REPORT | wx.LC_SINGLE_SEL)

        self.mainControl = mainControl

        self.InsertColumn(0, _("Page Name"), width=100)
        self.InsertColumn(1, _("Visited"), width=100)
        
        colConfig = self.mainControl.getConfig().get("main",
                "wikiWideHistory_columnWidths", "100,100")

        self.setColWidthsByConfigString(colConfig)

#         self.updatingThreadHolder = Utilities.ThreadHolder()
        
        self.mainControl.getMiscEvent().addListener(self)

        self.layerVisible = True
        self.sizeVisible = True   # False if this window has a size
                # that it can't be read (one dim. less than 5 pixels)
        self.ignoreOnChange = False

        self.historyOverviewSink = wxKeyFunctionSink((
                ("changed wiki wide history", self.onUpdateNeeded),
        ))

        self.__sinkApp = wxKeyFunctionSink((
                ("options changed", self.onUpdateNeeded),
        ), wx.GetApp().getMiscEvent(), self)

        if not self.mainControl.isMainWindowConstructed():
            # Install event handler to wait for construction
            self.__sinkMainFrame = wxKeyFunctionSink((
                    ("constructed main window", self.onConstructedMainWindow),
            ), self.mainControl.getMiscEvent(), self)
        else:
            self.onConstructedMainWindow(None)

        self.Bind(wx.EVT_CONTEXT_MENU, self.OnContextMenu)

        self.Bind(wx.EVT_WINDOW_DESTROY, self.OnDestroy)
#         self.Bind(wx.EVT_LIST_ITEM_SELECTED, self.OnItemSelected, id=self.GetId())
        self.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self.OnItemActivated, id=self.GetId())
        self.Bind(wx.EVT_SIZE, self.OnSize)
#         self.Bind(wx.EVT_KEY_DOWN, self.OnKeyDown)
        self.Bind(wx.EVT_MIDDLE_DOWN, self.OnMiddleButtonDown)
        
        self.Bind(wx.EVT_MENU, self.OnCmdDeleteAll, id=GUI_ID.CMD_WIKI_WIDE_HISTORY_DELETE_ALL)

        self.onWikiStateChanged(None)

#         wx.EVT_UPDATE_UI(self, GUI_ID.CMD_CHECKBOX_TIMELINE_DATE_ASCENDING,
#                 self.OnCmdCheckUpdateDateAscending)


    def close(self):
        """
        """
        self.historyOverviewSink.disconnect()
        self.__sinkApp.disconnect()
        
        colConfig = self.getConfigStringForColWidths()

        self.mainControl.getConfig().set("main",
                "wikiWideHistory_columnWidths", colConfig)


    def isVisibleEffect(self):
        """
        Is this control effectively visible?
        """
        return self.layerVisible and self.sizeVisible


    def handleVisibilityChange(self):
        """
        Only call after isVisibleEffect() really changed its value.
        The new value is taken from isVisibleEffect(), the old is assumed
        to be the opposite.
        """
        if self.isVisibleEffect():
            # Trick to make switching look faster
            wx.CallLater(1, self.updateList)


    def OnContextMenu(self, evt):
        self.showContextMenuOnTab()

#         mousePos = evt.GetPosition()
#         if mousePos == wx.DefaultPosition:
#             idx = self.GetFirstSelected()
#         else:
#             pos = self.ScreenToClient(wx.GetMousePosition())
#             idx = self.HitTest(pos)[0]
#             if not self.GetIsSelected(idx):
#                 self.SelectSingle(idx)
# 
#         if idx < 0 or idx > len(self.versionEntries):
#             # Use the tab context menu
#             self.showContextMenuOnTab()
#             return
# 
#         menu = wx.Menu()
# 
#         if self.activationMode == self._ACTIVATION_MODE_NORMAL:
#             appendToMenuByMenuDesc(menu, _CONTEXT_MENU_DIFF_ON_WIKI_PAGE)
#         else:
#             appendToMenuByMenuDesc(menu, _CONTEXT_MENU_DIFF_ON_DIFF_CTRL)
# 
#         if idx < len(self.versionEntries):
#             # Usable version entry selected
#             appendToMenuByMenuDesc(menu, _CONTEXT_MENU_VERSIONING_ITEM)
#         else:
#             # Entry "<Current>" selected, but at least one version present
#             appendToMenuByMenuDesc(menu, _CONTEXT_MENU_VERSIONING_CURRENT_ITEM)
# 
#         self.PopupMenu(menu)



    def showContextMenuOnTab(self):
        """
        Called by the TimeView to show a context menu if the tab was
        context-clicked.
        """
        menu = wx.Menu()
        appendToMenuByMenuDesc(menu, _CONTEXT_MENU_HISTORY_TAB)
        self.PopupMenu(menu)


    def OnCmdDeleteAll(self, evt):
        wikiDoc = self.mainControl.getWikiDocument()
        
        if wikiDoc is None:
            return
        
        wwh = wikiDoc.getWikiWideHistory()
        wwh.clearAll()



#     def OnKeyDown(self, evt):
#         accP = getAccelPairFromKeyDown(evt)
# 
#         if accP in ((wx.ACCEL_NORMAL, wx.WXK_DELETE),
#                 (wx.ACCEL_NORMAL, wx.WXK_NUMPAD_DELETE)):
#             self.OnCmdDeleteVersion(evt)
#         else:
#             evt.Skip()


    def setLayerVisible(self, vis, scName=""):
        oldVisible = self.isVisibleEffect()
        self.layerVisible = vis
        if oldVisible != self.isVisibleEffect():
            self.handleVisibilityChange()


    def OnDestroy(self, evt):
        self.close()


    def OnSize(self, evt):
        evt.Skip()
        oldVisible = self.isVisibleEffect()
        size = evt.GetSize()
        self.sizeVisible = size.GetHeight() >= 5 and size.GetWidth() >= 5
        
        if oldVisible != self.isVisibleEffect():
            self.handleVisibilityChange()


    def onConstructedMainWindow(self, evt):
        """
        Now we can register idle handler.
        """
        pass


    def miscEventHappened(self, miscevt):
        """
        Handle misc events
        """
        if self.isVisibleEffect() and miscevt.getSource() is self.mainControl:
            if "opened wiki" in miscevt:
                self.onWikiStateChanged(miscevt)
            elif "closed current wiki" in miscevt:
                self.onWikiStateChanged(miscevt)


    def onWikiStateChanged(self, miscevt):
        wikiDoc = self.mainControl.getWikiDocument()
        
        if wikiDoc is None:
            self.historyOverviewSink.setEventSource(None)
        else:
            self.historyOverviewSink.setEventSource(wikiDoc.getWikiWideHistory()
                    .getMiscEvent())

        self.onUpdateNeeded(miscevt)


    def onUpdateNeeded(self, miscevt):
        if self.isVisibleEffect():
            self.updateList()



    def updateList(self):
        wikiDoc = self.mainControl.getWikiDocument()
        
        if wikiDoc is None:
            return
        
        wwh = wikiDoc.getWikiWideHistory()
        
        # TODO: Own date/time format
        formatStr = self.mainControl.getConfig().get("main",
                "wikiWideHistory_dateFormat", "%x %I:%M %p")

        with WindowUpdateLocker(self):
            self.DeleteAllItems()

            # The list control shows newest entries at the top but in the internal
            # list they are at the end
            for entry in reversed(wwh.getHistoryEntries()):
                text = entry.getHrPageName()
                
#                 if entry.versionNumber == currVn:
#                     selected = self.GetItemCount()

                self.InsertItem(self.GetItemCount(), text)
                
                text = entry.getFormattedVisitedDate(formatStr)
                self.SetItem(self.GetItemCount() - 1, 1, text)

#             if selected == -1 and currVn == 0:
#                 selected = self.GetItemCount()

#             self.autosizeColumn(0)
#             self.SelectSingle(selected, scrollVisible=True)
            
#             self.checkSelectionChanged(callAlways=True)


#     def OnItemSelected(self, evt):
#         if self.ignoreOnChange:
#             return

    def getCurrentVersionNumber(self):
        """
        Return version number shown in current presenter.
        """
        presenter = self.mainControl.getCurrentDocPagePresenter()
        if presenter is None:
            return 0
        
        docPage = presenter.getDocPage()
        
        if docPage is None:
            return 0
        
        if not isinstance(docPage, WikiPageSnapshot):
            return 0
        
        return docPage.getSnapshotVersionNumber()


    def getHistoryEntryByListIndex(self, idx):
        if idx == -1:
            return None
        
        wikiDoc = self.mainControl.getWikiDocument()
        
        if wikiDoc is None:
            return
        
        wwh = wikiDoc.getWikiWideHistory()
        
        histEntries = wwh.getHistoryEntries()
        
        if idx >= len(histEntries):
            return None
            
        # The list control shows newest entries at the top but in the internal
        # list they are at the end
        return histEntries[(len(histEntries) - 1) - idx]


    def OnItemActivated(self, evt):
        entry = self.getHistoryEntryByListIndex(evt.GetIndex())
        if entry is None:
            return
        
        if self.mainControl.activatePageByUnifiedName(
                entry.getUnifiedPageName(), 0) is None:
            return

        if self.mainControl.getConfig().getboolean("main",
                "timeView_autohide", False):
            # Auto-hide timeview
            self.mainControl.setShowTimeView(False)
            
        self.mainControl.getActiveEditor().SetFocus()
        self.Close()


    def OnMiddleButtonDown(self, evt):
        mousePos = evt.GetPosition()
        if mousePos == wx.DefaultPosition:
            idx = self.GetFirstSelected()
        else:
            pos = self.ScreenToClient(wx.GetMousePosition())
            idx = self.HitTest(pos)[0]
            if not self.GetIsSelected(idx):
                self.SelectSingle(idx)

        entry = self.getHistoryEntryByListIndex(idx)
        if entry is None:
            evt.Skip()
            return
        
        if evt.ControlDown():
            configCode = self.mainControl.getConfig().getint("main",
                    "mouse_middleButton_withCtrl")
        else:
            configCode = self.mainControl.getConfig().getint("main",
                    "mouse_middleButton_withoutCtrl")
                    
        tabMode = MIDDLE_MOUSE_CONFIG_TO_TABMODE[configCode]

#         presenter = self.mainControl.activateWikiWord(wikiWord, tabMode)
        presenter = self.mainControl.activatePageByUnifiedName(
                entry.getUnifiedPageName(), tabMode)

        if presenter is None:
            return

        if not (tabMode & 1):
            # If not tab opened in background -> hide time view if option
            # is set and focus editor
            
            if self.mainControl.getConfig().getboolean("main",
                    "timeView_autohide", False):
                # Auto-hide time view if option selected
                self.mainControl.setShowTimeView(False)
            
            self.mainControl.getActiveEditor().SetFocus()
            self.Close()




# Context menu on history tab
_CONTEXT_MENU_HISTORY_TAB = \
"""
Clear history;CMD_WIKI_WIDE_HISTORY_DELETE_ALL;Clear history
"""




# Entries to support i18n of context menus
if not True:
    N_("Clear history")




