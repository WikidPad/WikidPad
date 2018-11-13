# import hotshot
# _prof = hotshot.Profile("hotshot.prf")

import os, traceback

import wx

# from MiscEvent import KeyFunctionSinkAR
from ..wxHelper import GUI_ID, EnhancedListControl, wxKeyFunctionSink, cloneFont, \
        drawTextRight, drawTextCenter, getAccelPairFromKeyDown, \
        appendToMenuByMenuDesc

from ..SystemInfo import isWindows, isOSX

from ..WindowLayout import setWindowPos, setWindowClientSize
from ..Configuration import MIDDLE_MOUSE_CONFIG_TO_TABMODE



# if isOSX():
#     _POPUP_PARENT = wx.Frame
# else:
#     _POPUP_PARENT = wx.PopupWindow


class WikiWordListPopup(wx.Frame):
    """
    Popup window which appears when hovering over a particular date
    Using frame because wx.PopupWindow is not available on Mac OS
    """
    if isWindows():
        # This does not work for Linux/GTK (no border at all)
        FRAME_BORDER = wx.SIMPLE_BORDER
        LIST_BORDER = wx.NO_BORDER
    else:
        # This looks badly under Windows
        FRAME_BORDER = wx.NO_BORDER
        LIST_BORDER = wx.SIMPLE_BORDER


    def __init__(self, parent, mainControl, ID, date, wikiWords, pos=wx.DefaultPosition):
        if ID == -1:
            ID = GUI_ID.TIMESHOW_WIKIWORDLIST_POPUP

#         if _POPUP_PARENT is wx.Frame:
        wx.Frame.__init__(self, parent, ID, "WikiWordList", pos=pos,
                style=wx.FRAME_FLOAT_ON_PARENT | self.FRAME_BORDER |     
                wx.FRAME_NO_TASKBAR)     # wx.RESIZE_BORDER | 
#         else:
#             wx.PopupWindow.__init__(self, parent, flags=self.FRAME_BORDER)

        self.mainControl = mainControl
        self.wikiWords = wikiWords
        # Item id of item in parent list
        self.date = date

        self.resultBox = EnhancedListControl(self, GUI_ID.TIMESHOW_WIKIWORDLIST,
                style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.LC_NO_HEADER |
                self.LIST_BORDER)

        self.resultBox.InsertColumn(0, "", width=10)
        self.listContent = wikiWords
        
        # Calculate minimal width of list
        dc = wx.ClientDC(self)
        try:
            dc.SetFont(self.resultBox.GetFont())
            self._listMinWidth = dc.GetTextExtent("MMMMMMMM")[0]
            dc.SetFont(wx.NullFont)
        finally:
            dc = None

#         self._listMinWidth = 60

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.resultBox, 1, wx.EXPAND)

        self.SetSizer(sizer)
        
        self.updateList()
        self.Layout()
        
        # Calculate size
        rect = self.resultBox.GetItemRect(0)
        setWindowClientSize(self, (rect.x + rect.width,
                rect.y + 2 + rect.height * len(self.listContent)))
        # self.SetClientSizeWH(rect.x + rect.width, rect.y + 2 + rect.height * len(self.listContent))

        # self.Layout()
        setWindowPos(self, fullVisible=True)
        
        self.resultBox.Bind(wx.EVT_MIDDLE_DOWN, self.OnListMiddleButtonDown)
        self.resultBox.Bind(wx.EVT_MOTION, self.OnListMouseMotion)
        self.resultBox.Bind(wx.EVT_LEFT_DOWN, self.OnListLeftButtonDown)
        self.resultBox.Bind(wx.EVT_LEAVE_WINDOW, self.OnListMouseLeave)
        

#         self.resultBox.Bind(wx.EVT_KILL_FOCUS, self.OnKillFocus)
#         self.Bind(wx.EVT_CLOSE, self.OnClose)


    def updateList(self):
        self.Freeze()
        try:
            self.resultBox.DeleteAllItems()

            for i, w in enumerate(self.listContent):
                self.resultBox.InsertItem(i, w)
                
#             self.resultBox.SetColumnWidth(0, wx.LIST_AUTOSIZE)
            self.resultBox.autosizeColumn(0)
            if self.resultBox.GetColumnWidth(0) < self._listMinWidth:
                self.resultBox.SetColumnWidth(0, self._listMinWidth)

        finally:
            self.Thaw()
            
    def isInsideList(self, mousePos):
        """
        Test if mousePos (screen coords) is inside the resultBox
        """
        pos = self.ScreenToClient(mousePos)
        return self.resultBox.GetRect().Contains(pos)
        


    def OnKillFocus(self, evt):
        self.Close()

    def OnListMouseMotion(self, evt):
        if evt.Dragging():
            evt.Skip()
            return
        
        pos = evt.GetPosition()
        item = self.resultBox.HitTest(pos)[0]

        if item != wx.NOT_FOUND:
            self.resultBox.SelectSingle(item)
        else:
            self.resultBox.SelectSingle(-1)


    def OnListLeftButtonDown(self, evt):
        item = self.resultBox.GetFirstSelected()
        if item is None:
            evt.Skip()
            return
        
        wikiWord = self.wikiWords[item]
#         self.mainControl.activateWikiWord(wikiWord, 0)
        if self.mainControl.activatePageByUnifiedName(
                "wikipage/" + wikiWord, 0) is None:
            return
        
        if self.mainControl.getConfig().getboolean("main",
                "timeView_autohide", False):
            # Auto-hide timeview
            self.mainControl.setShowTimeView(False)
            
        self.mainControl.getActiveEditor().SetFocus()
        self.Close()

        

    def OnListMiddleButtonDown(self, evt):
        item = self.resultBox.GetFirstSelected()
        if item is None:
            evt.Skip()
            return
        
        wikiWord = self.wikiWords[item]
        if evt.ControlDown():
            configCode = self.mainControl.getConfig().getint("main",
                    "mouse_middleButton_withCtrl")
        else:
            configCode = self.mainControl.getConfig().getint("main",
                    "mouse_middleButton_withoutCtrl")
                    
        tabMode = MIDDLE_MOUSE_CONFIG_TO_TABMODE[configCode]

#         presenter = self.mainControl.activateWikiWord(wikiWord, tabMode)
        presenter = self.mainControl.activatePageByUnifiedName(
                "wikipage/" + wikiWord, tabMode)

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

    def OnListMouseLeave(self, evt):
        # Resend mouse leave to frame
        pos = self.ScreenToClient(self.resultBox.ClientToScreen(
                evt.GetPosition()))
        evt.m_x = pos.x
        evt.m_y = pos.y
        
        self.ProcessEvent(evt)
        evt.Skip()

