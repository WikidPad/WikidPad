# import hotshot
# _prof = hotshot.Profile("hotshot.prf")

import os, traceback
import threading
import time

import wx

import Utilities
from Utilities import DUMBTHREADHOLDER
# from MiscEvent import KeyFunctionSinkAR
from wxHelper import GUI_ID, EnhancedListControl, wxKeyFunctionSink

from WindowLayout import setWindowPos, setWindowClientSize
from Configuration import MIDDLE_MOUSE_CONFIG_TO_TABMODE, isWindows

from StringOps import mbcsEnc, mbcsDec



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
        # This looks bad under Windows
        FRAME_BORDER = wx.NO_BORDER
        LIST_BORDER = wx.SIMPLE_BORDER


    def __init__(self, parent, mainControl, ID, parentItem, wikiWords, pos=wx.DefaultPosition):
        if ID == -1:
            ID = GUI_ID.TIMESHOW_WIKIWORDLIST_POPUP

        wx.Frame.__init__(self, parent, ID, "WikiWordList", pos=pos,
                style=wx.FRAME_FLOAT_ON_PARENT | self.FRAME_BORDER |     
                wx.FRAME_NO_TASKBAR)     # wx.RESIZE_BORDER | 

        self.mainControl = mainControl
        self.wikiWords = wikiWords
        # Item id of item in parent list
        self.parentItem = parentItem

        self.resultBox = EnhancedListControl(self, GUI_ID.TIMESHOW_WIKIWORDLIST,
                style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.LC_NO_HEADER |
                self.LIST_BORDER)

        self.resultBox.InsertColumn(0, u"", width=10)
        self.listContent = wikiWords

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
        
        wx.EVT_MIDDLE_DOWN(self.resultBox, self.OnListMiddleButtonDown)
        wx.EVT_MOTION(self.resultBox, self.OnListMouseMotion)
        wx.EVT_LEFT_DOWN(self.resultBox, self.OnListLeftButtonDown)
        

#         wx.EVT_KILL_FOCUS(self.resultBox, self.OnKillFocus)
#         wx.EVT_CLOSE(self, self.OnClose)


    def updateList(self):
        self.Freeze()
        try:
            self.resultBox.DeleteAllItems()

            for i, w in enumerate(self.listContent):
                self.resultBox.InsertStringItem(i, w)
                
            self.resultBox.SetColumnWidth(0, wx.LIST_AUTOSIZE)
        finally:
            self.Thaw()


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
        self.mainControl.activateWikiWord(wikiWord, 0)
        
        if self.mainControl.getConfig().getboolean("main",
                "timeView_autohide", False):
            # Auto-hide tree
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

        presenter = self.mainControl.activateWikiWord(wikiWord, tabMode)

        if not (tabMode & 1):
            # If not tab opened in background -> hide time view if option
            # is set and focus editor
            
            if self.mainControl.getConfig().getboolean("main",
                    "timeView_autohide", False):
                # Auto-hide time view if option selected
                self.mainControl.setShowTimeView(False)
            
            self.mainControl.getActiveEditor().SetFocus()
            self.Close()




class TimelinePanel(wx.ListCtrl):
    def __init__(self, parent, ID, mainControl):
        wx.ListCtrl.__init__(self, parent, ID,
                style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.LC_NO_HEADER |
                wx.LC_EDIT_LABELS)

        self.mainControl = mainControl

        self.InsertColumn(0, u"", width=1)  # date
        self.InsertColumn(1, u"", width=1)  # number of wiki words

        # Now gather some information
        self.InsertStringItem(0, u"1")
        rect = self.GetItemRect(0)
        self.itemHeight = rect.GetHeight()
        self.stdFont = self.GetFont()
        
        # Clone font
        self.boldFont = wx.Font(self.stdFont.GetPointSize(),
                self.stdFont.GetFamily(), self.stdFont.GetStyle(),
                self.stdFont.GetWeight(), self.stdFont.GetUnderlined(), 
                self.stdFont.GetFaceName(), self.stdFont.GetDefaultEncoding())

        self.boldFont.SetWeight(wx.FONTWEIGHT_BOLD)

        self.stepDays = 1
        
        self.DeleteAllItems()
        self.clientHeight = self.GetClientSizeTuple()[1]
        
        self.visibleItemCount = (self.clientHeight - 4) // self.itemHeight
        self.readablySized = True
        
        self.contextMenuWikiWords = {}  # {menuid: wiki word to go to}
        self.listContent = [] # Tuples (wxDateTime day, <number of wikiwords for day>)
        self.listMaxWordCount = 0  # max number of wikiwords over entries in listContent
        self.wikiWordListPopup = None
        self.labelEdit = False  # Is currently a label edit running?

        self.firstResize = True  # Hack

        currTime = wx.DateTime.Now()
        currTime.ResetTime()

        self.topDay = None  # currTime - wx.TimeSpan_Days(self.visibleItemCount - 1)

        wx.EVT_SIZE(self, self.OnSize)
##         wx.EVT_CONTEXT_MENU(self, self.OnContextMenu)
        wx.EVT_MOTION(self, self.OnMouseMotion)
        wx.EVT_LIST_ITEM_ACTIVATED(self, self.GetId(), self.OnItemActivated)
        wx.EVT_LEAVE_WINDOW(self, self.OnMouseLeave)
#         wx.EVT_LIST_ITEM_SELECTED(self, self.GetId(), self.OnItemSelected)

        wx.EVT_LIST_BEGIN_LABEL_EDIT(self, self.GetId(), self.OnBeginLabelEdit)
        wx.EVT_LIST_END_LABEL_EDIT(self, self.GetId(), self.OnEndLabelEdit)


    def OnSize(self, evt):
        evt.Skip()
        self.clientHeight = self.GetClientSizeTuple()[1]
        self.visibleItemCount = (self.clientHeight - 4) // self.itemHeight
#         print "OnSize1", repr(self.clientHeight), self.visibleItemCount, self.visibleItemCount * self.itemHeight
        
        if self.firstResize:
            currTime = wx.DateTime.Now()
            currTime.ResetTime()
            
            self.topDay = currTime - wx.TimeSpan_Days(self.visibleItemCount - 1)

            # Register for pWiki events
            self.sink = wxKeyFunctionSink(self.mainControl.getMiscEvent(), self, (
                    ("opened wiki", self.onUpdateNeeded),
                    ("closed current wiki", self.onUpdateNeeded),
                    ("updated wiki page", self.onUpdateNeeded),
                    ("deleted wiki page", self.onUpdateNeeded),
                    ("options changed", self.onUpdateNeeded)
            ))

            self.firstResize = False
            
        size = evt.GetSize()
        self.readablySized = size.GetHeight() >= 5 and size.GetWidth() >= 5

        if len(self.listContent) > self.visibleItemCount:
            # Cut list
            self.listContent = self.listContent[:self.visibleItemCount]
            
            # Recalc maxWordCount
            maxWordCount = 0
            for d, wc in self.listContent:
                maxWordCount = max(maxWordCount, wc)
            self.updateList()

        elif len(self.listContent) < self.visibleItemCount:
            self.updateContent()


    def getBgColorForCount(self, wordCount):
        """
        Return the appropriate background color for a date entry
        which has wordCount number of wiki words assigned to this day
        (modified/created ... on this day).
        """
        if wordCount == 0:
            return wx.WHITE
            
        if self.listMaxWordCount < 16:
            greylevel = 256 - (wordCount) * 16
        else:
            greylevel = \
                    240 - ((wordCount - 1) * 240) // (self.listMaxWordCount - 1)
                    
        return wx.Colour(greylevel, greylevel, greylevel)


    def _isDarkColour(self, col):
        return col.Green() < 128


    def getWikiWordsForDay(self, day):
        """
        Returns unsorted list of wiki words which are "related" to the day where
        "related" may mean e.g. created or modified at this day.

        This implementation returns words modified at this day.
        day -- wxDateTime object
        """
        wikiDoc = self.mainControl.getWikiDocument()

        startTime = day.GetTicks()
        endTime = float(startTime + 86400 * self.stepDays)

        return wikiDoc.getWikiWordsModifiedWithin(startTime, endTime)


    def onUpdateNeeded(self, miscevt):
        self.updateContent()


    def updateContent(self):
        stepDateSpan = wx.TimeSpan_Days(self.stepDays)

        if not self.readablySized or not self.mainControl.isWikiLoaded():
            self.listMaxWordCount = 0
            self.listContent = []
            self.updateList()
            return
            
        # Collect data
        currTime = self.topDay
        content = []
        maxWordCount = 0
        for i in xrange(self.visibleItemCount):
            wikiWords = self.getWikiWordsForDay(currTime)
            content.append((currTime, len(wikiWords)))
            maxWordCount = max(maxWordCount, len(wikiWords))
            currTime = currTime + stepDateSpan  # To ensure copying
           
        self.listMaxWordCount = maxWordCount
        self.listContent = content
                
        self.updateList()
        

    def updateList(self):
        """
        Visual update of the list. self.listContent must be
        precalculated elsewhere.
        """
        formatStr = self.mainControl.getConfig().get("main",
                "timeView_dateFormat", u"%Y %m %d")
                
        today = wx.DateTime.Now()
        today.ResetTime()
        
        dc = wx.ClientDC(self)
        dc.SetFont(self.stdFont)

        self.Freeze()
        try:
            self.DeleteAllItems()
            if not self.mainControl.isWikiLoaded():
                return

            i = 0
            maxWidth0 = 0
            maxWidth1 = 0
            for t, c in self.listContent:
                
                bgCol = self.getBgColorForCount(c)

                if self._isDarkColour(bgCol):
                    txtCol = wx.WHITE
                else:
                    txtCol = wx.BLACK
                    
                # Date column
                col0txt = t.Format(formatStr)
                listItemD = wx.ListItem()
                listItemD.SetId(i)
                listItemD.SetBackgroundColour(bgCol)
                listItemD.SetTextColour(txtCol)
                listItemD.SetText(col0txt)
                
                # Number of wiki words column
                col1txt = "(%i)" % c
                listItemW = wx.ListItem()
                listItemW.SetColumn(1)
                listItemW.SetId(i)
                listItemW.SetBackgroundColour(bgCol)
                listItemW.SetTextColour(txtCol)
                listItemW.SetText(col1txt)
                
                if t == today:
                    # Make entry for today bold
                    listItemD.SetFont(self.boldFont)
                    listItemW.SetFont(self.boldFont)

                    dc.SetFont(self.boldFont)
                    maxWidth0 = max(maxWidth0, dc.GetTextExtent(col0txt)[0])
                    maxWidth1 = max(maxWidth1, dc.GetTextExtent(col1txt)[0])
                    dc.SetFont(self.stdFont)
                else:
                    maxWidth0 = max(maxWidth0, dc.GetTextExtent(col0txt)[0])
                    maxWidth1 = max(maxWidth1, dc.GetTextExtent(col1txt)[0])

                self.InsertItem(listItemD)
                self.SetItem(listItemW)

                i += 1

            # Does not work correctly if bold entry is contained
            self.SetColumnWidth(0, maxWidth0 + 12)
            self.SetColumnWidth(1, maxWidth1 + 12)

#             self.SetColumnWidth(0, wx.LIST_AUTOSIZE)
#             self.SetColumnWidth(0, self.GetColumnWidth(0) + 8)
#             self.SetColumnWidth(1, wx.LIST_AUTOSIZE)
#             self.SetColumnWidth(1, self.GetColumnWidth(1) + 2)
        finally:
            self.Thaw()
            dc.SetFont(wx.NullFont)
            del dc


    def OnWikiWordListPopupDestroyed(self, evt):
        if not self.wikiWordListPopup is evt.GetEventObject():
            evt.Skip()
            return
            
        self.wikiWordListPopup.Unbind(wx.EVT_WINDOW_DESTROY)
        self.wikiWordListPopup = None

        evt.Skip()


    def setWikiWordListPopup(self, popup):
        if self.wikiWordListPopup is not None:
            self.wikiWordListPopup.Unbind(wx.EVT_WINDOW_DESTROY)
            self.wikiWordListPopup.Destroy()
        
        self.wikiWordListPopup = popup

        if self.wikiWordListPopup is not None:        
            self.wikiWordListPopup.Bind(wx.EVT_WINDOW_DESTROY,
                    self.OnWikiWordListPopupDestroyed)


    def showContextMenuForItem(self, item):
        if item == wx.NOT_FOUND:
            return
            
        day = self.listContent[item][0]
        wikiWords = self.getWikiWordsForDay(day)
        
        if len(wikiWords) == 0:
            return
        
        self.mainControl.getCollator().sort(wikiWords)

        reusableIds = set(self.contextMenuWikiWords.keys())
        menu = wx.Menu()
        
        cmc = {}
        
        for word in wikiWords:
            if len(reusableIds) > 0:
                menuId = reusableIds.pop()
            else:
                menuId = wx.NewId()
                wx.EVT_MENU(self, menuId, self.OnWikiWordInMenu)

            cmc[menuId] = word
            menuItem = wx.MenuItem(menu, menuId, word)
            menu.AppendItem(menuItem)
            
        # Add remaining ids to prevent them from getting lost
        for i in reusableIds:
            cmc[i] = None

        self.contextMenuWikiWords = cmc
        self.PopupMenu(menu)


    def OnContextMenu(self, evt):
        pos = self.ScreenToClient(wx.GetMousePosition())
        item = self.HitTest(pos)[0]
        
        self.showContextMenuForItem(item)


    def OnItemActivated(self, evt):
        self.showContextMenuForItem(evt.GetIndex())


#     def OnItemSelected(self, evt):
#         print "OnItemSelected1", repr(evt.GetIndex())
#         
#         evt.Skip()


    def OnWikiWordInMenu(self, evt):
        word = self.contextMenuWikiWords[evt.GetId()]
        self.mainControl.activateWikiWord(word, 0)

    def OnMouseMotion(self, evt):
        if evt.Dragging():
            evt.Skip()
            return

        pos = evt.GetPosition()
        
        item = self.HitTest(pos)[0]

        if self.wikiWordListPopup is not None:
            if self.wikiWordListPopup.parentItem == item:
                # On same item yet, nothing to do
                evt.Skip()
                return

            self.setWikiWordListPopup(None)
#             self.wikiWordListPopup.Destroy()
#             self.wikiWordListPopup = None


        if item != wx.NOT_FOUND and not self.labelEdit:
            day = self.listContent[item][0]
            wikiWords = self.getWikiWordsForDay(day)
            
            if len(wikiWords) == 0:
                evt.Skip()
                return

            self.mainControl.getCollator().sort(wikiWords)
            rect = self.GetItemRect(item)
            
            # Position relative to self
            pos = wx.Point(rect.x + 20, rect.y + rect.height - 2)
            
            # Screen position
            pos = self.ClientToScreen(pos)
            
            focus = wx.Window.FindFocus()
            self.setWikiWordListPopup(WikiWordListPopup(self, self.mainControl,
                    -1, item, wikiWords, pos=pos))
            
            self.wikiWordListPopup.Show()
            if focus is not None:
                focus.SetFocus()


    def OnMouseLeave(self, evt):
        mousePos = wx.GetMousePosition()
        pos = self.ScreenToClient(mousePos)

        if self.GetRect().Inside(pos):
            evt.Skip()
            return

        if self.wikiWordListPopup is not None:
#             pos = self.wikiWordListPopup.ScreenToClient(mousePos)
            if self.wikiWordListPopup.GetRect().Inside(mousePos):
                evt.Skip()
                return
            self.setWikiWordListPopup(None)
#             self.wikiWordListPopup.Destroy()
#             self.wikiWordListPopup = None

        evt.Skip()


    def OnBeginLabelEdit(self, evt):
        self.labelEdit = True
        if self.wikiWordListPopup is not None:
            self.setWikiWordListPopup(None)
#             self.wikiWordListPopup.Destroy()
#             self.wikiWordListPopup = None


    def OnEndLabelEdit(self, evt):
        formatStr = self.mainControl.getConfig().get("main",
                "timeView_dateFormat", u"%Y %m %d")
                
        self.labelEdit = False
        
        if not evt.IsEditCancelled():
            evt.Veto()

            newDate = wx.DateTime()
            if newDate.ParseFormat(evt.GetText(), formatStr) == -1:
                return

            newDate.ResetTime()
            self.topDay = newDate - wx.TimeSpan_Days(evt.GetIndex())
            
            self.updateContent()

# class CalendarPanel
        

# class DatedWikiWordProviderBase
# class DatedWikiWordProviderModified



        
#         self.lastContextMenuPresenter = self.docPagePresenters[tab]
#         # Show menu
#         self.PopupMenu(self.contextMenu)

        
        






class TimeViewCtrl(wx.Notebook):
    def __init__(self, parent, ID, mainControl):
        wx.Notebook.__init__(self, parent, ID)

        self.mainControl = mainControl
        
        self.timelinePanel = TimelinePanel(self, -1, self.mainControl)
        self.AddPage(self.timelinePanel, _(u"Modified"))


    def close(self):
        """
        """
        pass

    def miscEventHappened(self, miscevt):
        """
        Handle misc events
        """
        pass
#         if self.readablySized and miscevt.getSource() is self.mainControl:
#             if miscevt.has_key("changed current docpage presenter"):
#                 self.docPagePresenterSinkAR.setEventSource(
#                         self.mainControl.getCurrentDocPagePresenter())
#                 self.updateList()


    def setVisible(self, vis):
        pass
            
        

