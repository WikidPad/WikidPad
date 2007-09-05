# import hotshot
# _prof = hotshot.Profile("hotshot.prf")

import os, traceback
import threading
import time

import wx

import Utilities
from Utilities import DUMBTHREADHOLDER
# from MiscEvent import KeyFunctionSinkAR
from wxHelper import GUI_ID, EnhancedListControl, wxKeyFunctionSink, cloneFont,\
        drawTextRight, drawTextCenter

from WindowLayout import setWindowPos, setWindowClientSize, LayeredControlPanel
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
        # This looks badly under Windows
        FRAME_BORDER = wx.NO_BORDER
        LIST_BORDER = wx.SIMPLE_BORDER


    def __init__(self, parent, mainControl, ID, date, wikiWords, pos=wx.DefaultPosition):
        if ID == -1:
            ID = GUI_ID.TIMESHOW_WIKIWORDLIST_POPUP

        wx.Frame.__init__(self, parent, ID, "WikiWordList", pos=pos,
                style=wx.FRAME_FLOAT_ON_PARENT | self.FRAME_BORDER |     
                wx.FRAME_NO_TASKBAR)     # wx.RESIZE_BORDER | 

        self.mainControl = mainControl
        self.wikiWords = wikiWords
        # Item id of item in parent list
        self.date = date

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
        wx.EVT_LEAVE_WINDOW(self.resultBox, self.OnListMouseLeave)
        

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
            
    def isInsideList(self, mousePos):
        """
        Test if mousePos (screen coords) is inside the resultBox
        """
        pos = self.ScreenToClient(mousePos)
        return self.resultBox.GetRect().Inside(pos)
        


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

    def OnListMouseLeave(self, evt):
        # Resend mouse leave to frame
        pos = self.ScreenToClient(self.resultBox.ClientToScreen(
                evt.GetPosition()))
        evt.m_x = pos.x
        evt.m_y = pos.y
        
        self.ProcessEvent(evt)
        evt.Skip()


class DatedWikiWordFilterBase:
    """
    Provides for a given date or list of dates a list of wiki words
    related to that date. Subclasses of this class define which
    "relation" is meant.
    """
    def __init__(self):
        self.wikiDocument = None
        self.dayResolution = 1

    def setWikiDocument(self, wikiDoc):
        self.wikiDocument = wikiDoc

    def getWikiDocument(self):
        return self.wikiDocument

    def setDayResolution(self, dr):
        self.dayResolution = dr

    def getDayResolution(self):
        return self.dayResolution

    def getDisplayName(self):
        """
        Return a short name describing what the date of the wiki word means.
        """
        assert 0  # Abstract
        
    def getWikiWordsForDay(self, day):
        """
        Get all wiki words related to a date beginning with day (a wx.DateTime)
        up to so many days as set in self.dayResolution
        """
        assert 0  # Abstract



class DatedWikiWordFilterModified(DatedWikiWordFilterBase):

    def getDisplayName(self):
        return _(u"Modified")
        
    def getWikiWordsForDay(self, day):
        wikiDoc = self.getWikiDocument()
        if wikiDoc is None:
            return []
        
        startTime = day.GetTicks()
        endTime = float(startTime + 86400 * self.getDayResolution())

        return wikiDoc.getWikiWordsModifiedWithin(startTime,
                endTime)



class TimePresentationBase:
    def __init__(self, mainControl, wikiWordFilter):
        
        self.mainControl = mainControl

        # Some object derived from DatedWikiWordFilterBase
        self.wikiWordFilter = wikiWordFilter
        
        self.wikiWordListPopup = None
        # Shift from upper left corner of selected cell/list item
        self.popupShiftX = 5
        self.popupShiftY = 5

        self.labelEdit = False  # Is currently a label edit running?

        wx.EVT_MOTION(self, self.OnMouseMotion)
        wx.EVT_LEAVE_WINDOW(self, self.OnMouseLeave)


    def setVisible(self, vis):
        pass
        
    def close(self):
        pass

    def getBgColorForCount(self, wordCount):
        """
        Return the appropriate background color for a date entry
        which has wordCount number of wiki words assigned to this day
        (modified/created ... on this day).
        """
        if wordCount == 0:
            return wx.WHITE
            
        greylevel = max(0, 256 - wordCount * 16)

        return wx.Colour(greylevel, greylevel, greylevel)


    def _isDarkColour(self, col):
        return col.Green() < 128


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
            self.wikiWordListPopup.Unbind(wx.EVT_LEAVE_WINDOW)
            self.wikiWordListPopup.Destroy()

        self.wikiWordListPopup = popup

        if self.wikiWordListPopup is not None:        
            self.wikiWordListPopup.Bind(wx.EVT_WINDOW_DESTROY,
                    self.OnWikiWordListPopupDestroyed)
            self.wikiWordListPopup.Bind(wx.EVT_LEAVE_WINDOW,
                    self.OnMouseLeave)



    def OnMouseMotion(self, evt):
        if evt.Dragging():
            evt.Skip()
            return

        pos = evt.GetPosition()
        
#         item = self.HitTest(pos)[0]

        day, rect = self._getDateAndRectForMousePosition(pos)
        if self.wikiWordListPopup is not None:
            if self.wikiWordListPopup.date == day:
                # On same item yet, nothing to do
                evt.Skip()
                return

            self.setWikiWordListPopup(None)


        if not self.labelEdit and day is not None:
            wikiWords = self.wikiWordFilter.getWikiWordsForDay(day)
            
            if len(wikiWords) == 0:
                evt.Skip()
                return

            self.mainControl.getCollator().sort(wikiWords)
#             rect = self.GetItemRect(item)

            # Position relative to self
            pos = wx.Point(rect.x + self.popupShiftX, rect.y + self.popupShiftY)
            
            # Screen position
            pos = self.ClientToScreen(pos)
            
            focus = wx.Window.FindFocus()
            self.setWikiWordListPopup(WikiWordListPopup(self, self.mainControl,
                    -1, day, wikiWords, pos=pos))
            
            self.wikiWordListPopup.Show()
            if focus is not None:
                focus.SetFocus()


    def OnMouseLeave(self, evt):
        """
        Called if either the timeline or the wiki words popup window is left.
        """
        mousePos = wx.GetMousePosition()
        pos = self.ScreenToClient(mousePos)
#         print "OnMouseLeave1", repr((self.GetRect(), self.GetParent().GetRect(), mousePos, pos, evt.GetEventObject()))

        tlRect = self._getInsideTestRectangle()

        if tlRect.Inside(pos):
            evt.Skip()
            return

        if self.wikiWordListPopup is not None:
            if self.wikiWordListPopup.isInsideList(mousePos):
                evt.Skip()
                return
            self.setWikiWordListPopup(None)
        evt.Skip()




class TimelinePanel(wx.ListCtrl, TimePresentationBase):
    def __init__(self, parent, ID, mainControl, wikiWordFilter):
        wx.ListCtrl.__init__(self, parent, ID,
                style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.LC_NO_HEADER |
                wx.LC_EDIT_LABELS)

        TimePresentationBase.__init__(self, mainControl, wikiWordFilter)

        self.InsertColumn(0, u"", width=1)  # date
        self.InsertColumn(1, u"", width=1)  # number of wiki words

        # Now gather some information
        self.InsertStringItem(0, u"1")
        self.itemHeight = self.GetItemRect(0).GetHeight()
        
        self.popupShiftX = 20
        self.popupShiftY = self.itemHeight - 2

        self.stdFont = self.GetFont()

        self.boldFont = cloneFont(self.stdFont)
        
#         # Clone font
#         self.boldFont = wx.Font(self.stdFont.GetPointSize(),
#                 self.stdFont.GetFamily(), self.stdFont.GetStyle(),
#                 self.stdFont.GetWeight(), self.stdFont.GetUnderlined(), 
#                 self.stdFont.GetFaceName(), self.stdFont.GetDefaultEncoding())

        self.boldFont.SetWeight(wx.FONTWEIGHT_BOLD)

        self.stepDays = 1
        
        self.DeleteAllItems()
        self.clientHeight = self.GetClientSizeTuple()[1]
        
        self.visibleItemCount = (self.clientHeight - 4) // self.itemHeight
        self.readablySized = True
        
        self.contextMenuWikiWords = {}  # {menuid: wiki word to go to}
        self.listContent = [] # Tuples (wx.DateTime day, <number of wikiwords for day>)
        self.listMaxWordCount = 0  # max number of wikiwords over entries in listContent
        self.wikiWordListPopup = None

        self.firstResize = True  # Hack

        self.topDay = None  # currTime - wx.TimeSpan_Days(self.visibleItemCount - 1)

#         wx.EVT_SIZE(self, self.OnSize)
##         wx.EVT_CONTEXT_MENU(self, self.OnContextMenu)
#         wx.EVT_MOTION(self, self.OnMouseMotion)
        wx.EVT_LIST_ITEM_ACTIVATED(self, self.GetId(), self.OnItemActivated)

        wx.EVT_LIST_BEGIN_LABEL_EDIT(self, self.GetId(), self.OnBeginLabelEdit)
        wx.EVT_LIST_END_LABEL_EDIT(self, self.GetId(), self.OnEndLabelEdit)


    def currentDateToBottom(self):
        currTime = wx.DateTime.Now()
        currTime.ResetTime()
        
        self.topDay = currTime - wx.TimeSpan_Days(self.visibleItemCount - 1)
        self.updateContent()



    def adjustToSize(self):
        size = self.GetSize()

        self.clientHeight = size.GetHeight()

        self.visibleItemCount = (self.clientHeight - 6) // self.itemHeight

        # print "adjustToSize", repr(self.clientHeight), self.visibleItemCount, self.visibleItemCount * self.itemHeight
        
        if self.firstResize:
            currTime = wx.DateTime.Now()
            currTime.ResetTime()
            
            self.topDay = currTime - wx.TimeSpan_Days(self.visibleItemCount - 1)

            # Register for pWiki events
            self.sink = wxKeyFunctionSink((
                    ("opened wiki", self.onUpdateNeeded),
                    ("closed current wiki", self.onUpdateNeeded),
                    ("updated wiki page", self.onUpdateNeeded),
                    ("deleted wiki page", self.onUpdateNeeded),
                    ("options changed", self.onUpdateNeeded)
            ), self.mainControl.getMiscEvent(), self)

            self.firstResize = False
            
#         size = evt.GetSize()
        self.readablySized = size.GetHeight() >= 5 and size.GetWidth() >= 5

        if len(self.listContent) > self.visibleItemCount:
            self.updateContent()
            # Cut list
            self.listContent = self.listContent[:self.visibleItemCount]
            
            # Recalc maxWordCount
            maxWordCount = 0
            for d, wc in self.listContent:
                maxWordCount = max(maxWordCount, wc)
            self.updatePresentation()

        elif len(self.listContent) < self.visibleItemCount:
            self.updateContent()


    def SetSize(self, size):
        wx.ListCtrl.SetSize(self, size)
        self.adjustToSize()

    def SetDimensions(self, x, y, width, height, flags=wx.SIZE_AUTO):
        wx.ListCtrl.SetDimensions(self, x, y, width, height, flags)
        self.adjustToSize()


#     def getBgColorForCount(self, wordCount):
#         """
#         Return the appropriate background color for a date entry
#         which has wordCount number of wiki words assigned to this day
#         (modified/created ... on this day).
#         """
#         if wordCount == 0:
#             return wx.WHITE
#             
#         greylevel = max(0, 256 - (wordCount) * 16)
# 
# #         if self.listMaxWordCount < 16:
# #             greylevel = 256 - (wordCount) * 16
# #         else:
# #             greylevel = \
# #                     240 - ((wordCount - 1) * 240) // (self.listMaxWordCount - 1)
#                     
#         return wx.Colour(greylevel, greylevel, greylevel)
# 
# 
#     def _isDarkColour(self, col):
#         return col.Green() < 128


#     def getWikiWordsForDay(self, day):
#         """
#         Returns unsorted list of wiki words which are "related" to the day where
#         "related" may mean e.g. created or modified at this day.
# 
#         This implementation returns words modified at this day.
#         day -- wx.DateTime object
#         """
#         wikiDoc = self.mainControl.getWikiDocument()
# 
#         startTime = day.GetTicks()
#         endTime = float(startTime + 86400 * self.stepDays)
# 
#         return wikiDoc.getWikiWordsModifiedWithin(startTime, endTime)


    def onUpdateNeeded(self, miscevt):
        self.updateContent()


    def updateContent(self):
        # First update the filter
        self.wikiWordFilter.setWikiDocument(self.mainControl.getWikiDocument())
        self.wikiWordFilter.setDayResolution(self.stepDays)
        
        stepDateSpan = wx.TimeSpan_Days(self.stepDays)

        if not self.readablySized or not self.mainControl.isWikiLoaded():
            self.listMaxWordCount = 0
            self.listContent = []
            self.updatePresentation()
            return
            
        # Collect data
        currTime = self.topDay
        content = []
        maxWordCount = 0
        for i in xrange(self.visibleItemCount):
            wikiWords = self.wikiWordFilter.getWikiWordsForDay(currTime)
            content.append((currTime, len(wikiWords)))
            maxWordCount = max(maxWordCount, len(wikiWords))
            currTime = currTime + stepDateSpan  # To ensure copying
           
        self.listMaxWordCount = maxWordCount
        self.listContent = content
                
        self.updatePresentation()
        

    def updatePresentation(self):
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

            # Does otherwise not work correctly if bold entry is contained
            self.SetColumnWidth(0, maxWidth0 + 12)
            self.SetColumnWidth(1, maxWidth1 + 12)
        finally:
            self.Thaw()
            dc.SetFont(wx.NullFont)
            del dc


#     def OnWikiWordListPopupDestroyed(self, evt):
#         if not self.wikiWordListPopup is evt.GetEventObject():
#             evt.Skip()
#             return
#             
#         self.wikiWordListPopup.Unbind(wx.EVT_WINDOW_DESTROY)
#         self.wikiWordListPopup = None
# 
#         evt.Skip()
# 
# 
#     def setWikiWordListPopup(self, popup):
#         if self.wikiWordListPopup is not None:
#             self.wikiWordListPopup.Unbind(wx.EVT_WINDOW_DESTROY)
#             self.wikiWordListPopup.Unbind(wx.EVT_LEAVE_WINDOW)
#             self.wikiWordListPopup.Destroy()
# 
#         self.wikiWordListPopup = popup
# 
#         if self.wikiWordListPopup is not None:        
#             self.wikiWordListPopup.Bind(wx.EVT_WINDOW_DESTROY,
#                     self.OnWikiWordListPopupDestroyed)
#             self.wikiWordListPopup.Bind(wx.EVT_LEAVE_WINDOW,
#                     self.OnMouseLeave)


    def showContextMenuForItem(self, item):
        if item == wx.NOT_FOUND:
            return
            
        day = self.listContent[item][0]
        wikiWords = self.wikiWordFilter.getWikiWordsForDay(day)
        
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


    def _getDateAndRectForMousePosition(self, pos):
        """
        pos is relative to self window.
        """
        item = self.HitTest(pos)[0]
        if item == wx.NOT_FOUND:
            return None, None

        rect = self.GetItemRect(item)

        return (self.listContent[item][0], rect)


#     def OnMouseMotion(self, evt):
#         if evt.Dragging():
#             evt.Skip()
#             return
# 
#         pos = evt.GetPosition()
#         
# #         item = self.HitTest(pos)[0]
# 
#         if self.wikiWordListPopup is not None:
#             if self.wikiWordListPopup.parentItem == item:
#                 # On same item yet, nothing to do
#                 evt.Skip()
#                 return
# 
#             self.setWikiWordListPopup(None)
# 
# 
#         if not self.labelEdit:
#             day = self._getDateForMousePosition(pos)
#             wikiWords = self.wikiWordFilter.getWikiWordsForDay(day)
#             
#             if len(wikiWords) == 0:
#                 evt.Skip()
#                 return
# 
#             self.mainControl.getCollator().sort(wikiWords)
#             rect = self.GetItemRect(item)
#             
#             # Position relative to self
#             pos = wx.Point(rect.x + 20, rect.y + rect.height - 2)
#             
#             # Screen position
#             pos = self.ClientToScreen(pos)
#             
#             focus = wx.Window.FindFocus()
#             self.setWikiWordListPopup(WikiWordListPopup(self, self.mainControl,
#                     -1, item, wikiWords, pos=pos))
#             
#             self.wikiWordListPopup.Show()
#             if focus is not None:
#                 focus.SetFocus()


    def _getInsideTestRectangle(self):
        tlRect = self.GetRect()
        # This is necessary, at least for Windows, no idea why
        tlRect = wx.Rect(tlRect.GetX(), tlRect.GetY(),
                max(0, tlRect.GetWidth() - 4), max(0, tlRect.GetHeight() - 4))

        return tlRect


#     def OnMouseLeave(self, evt):
#         """
#         Called if either the timeline or the wiki words popup window is left.
#         """
#         mousePos = wx.GetMousePosition()
#         pos = self.ScreenToClient(mousePos)
# #         print "OnMouseLeave1", repr((self.GetRect(), self.GetParent().GetRect(), mousePos, pos, evt.GetEventObject()))
# 
#         tlRect = self._getInsideTestRectangle()
# 
#         if tlRect.Inside(pos):
#             evt.Skip()
#             return
# 
#         if self.wikiWordListPopup is not None:
#             if self.wikiWordListPopup.isInsideList(mousePos):
#                 evt.Skip()
#                 return
#             self.setWikiWordListPopup(None)
#         evt.Skip()


    def OnBeginLabelEdit(self, evt):
        self.labelEdit = True
        if self.wikiWordListPopup is not None:
            self.setWikiWordListPopup(None)


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




class CalendarPanel(wx.Panel, TimePresentationBase):
    # Which day is first in week?
    Monday_First = wx.DateTime.Monday_First
    Sunday_First = wx.DateTime.Sunday_First
    
    def __init__(self, parent, ID, mainControl, wikiWordFilter):
        wx.Panel.__init__(self, parent, ID)
        TimePresentationBase.__init__(self, mainControl, wikiWordFilter)

#         self.shortWeekDays = None
#         self._calcShortWeekDayNames()

        self.firstResize = True  # Hack

        # The following values can be customized to change the look 
        #     of the calendar
        # TODO Make customizable

        # Minimal distance from Margin of Panel to months
        self.minOuterMarginDistHor = 6
        self.minOuterMarginDistVert = 4
        
        # Minimal distance between neighboured cells
        self.minCellDistHor = 3
        self.minCellDistVert = 2
        
        # Minimal distance between months
        self.minMonthDistHor = 10
        self.minMonthDistVert = 10
        
        self.firstWeekDay = self.Monday_First
        
        # From here on things are calculated automatically
        
        self.topMonth = None # wx.DateTimeFromDMY(1, 4 - 1, 2007)   # TODO !!!

        # Dictionary which maps days to the count of wiki words
        # Days are tuples (day, month, year)
        self.dayToWordCountCache = {}
        
        # Some type of cache during repainting
        self.today = None

        self.stdFont = self.GetFont()

        self.boldFont = cloneFont(self.stdFont)
        self.boldFont.SetWeight(wx.FONTWEIGHT_BOLD)
        
        # Dimensions of a cell
        self.cellWidth = 0
        self.cellHeight = 0
        
        # Minimal month dimensions
        self.minMonthWidth = 0
        self.minMonthHeight = 0

        self.calcSizeIndepDimensions()


        # Initial values for layout
        self.monthCols = 1
        self.monthRows = 1

        self.outerMarginLeft = self.minOuterMarginDistHor
        self.outerMarginTop = self.minOuterMarginDistVert
        self.cellDistHor = self.minCellDistHor
        self.cellDistVert = self.minCellDistVert
        self.monthDistHor = self.minMonthDistHor
        self.monthDistVert = self.minMonthDistVert
        self.monthWidth = self.minMonthWidth
        self.monthHeight = self.minMonthHeight

        self.recalcLayout()


        self.SetBackgroundColour(wx.WHITE)

        wx.EVT_PAINT(self, self.OnPaint)
        wx.EVT_ERASE_BACKGROUND(self, self.OnEraseBackground)
        wx.EVT_SIZE(self, self.OnSize)
#         wx.EVT_MOTION(self, self.OnMotion)


    def adjustToSize(self):
        self.recalcLayout()

        if self.firstResize:
            currMonth = wx.DateTime.Now()
            currMonth.ResetTime()
            currMonth.SetDay(1)
            
            self.topMonth = currMonth - wx.DateSpan_Months(
                    self.monthCols * self.monthRows- 1)

            # Register for pWiki events
            self.sink = wxKeyFunctionSink((
                    ("opened wiki", self.onUpdateNeeded),
                    ("closed current wiki", self.onUpdateNeeded),
                    ("updated wiki page", self.onUpdateNeeded),
                    ("deleted wiki page", self.onUpdateNeeded),
                    ("options changed", self.onUpdateNeeded)
            ), self.mainControl.getMiscEvent(), self)

            self.firstResize = False
            self.updateContent()


    def OnSize(self, evt):
        evt.Skip()
        self.adjustToSize()
        

    def setVisible(self, vis):
        pass
        
    def close(self):
        pass


    def onUpdateNeeded(self, miscevt):
        self.updateContent()


#     def _calcShortWeekDayNames(self):
#             # Go over all short weekday names
#             # Begin with an arbitrary Sunday as wxPython uses Sunday
#             # as first weekday internally
#             swd = []
#             day = wx.DateTimeFromDMY(26, 8, 2007)
#             for i in xrange(7):
#                 swd.append(day.Format(u"%a"))
#                 day += wx.TimeSpan_Day()
#                 
#             self.shortWeekDays = swd


    def updateContent(self):
        self.wikiWordFilter.setWikiDocument(self.mainControl.getWikiDocument())
        self.wikiWordFilter.setDayResolution(1)

        # Clear cache and repaint
        self.dayToWordCountCache = {}
        self.Refresh()




    def calcSizeIndepDimensions(self):
        """
        Calculate the dimensions which are independent of the 
        panel size.
        Call this also after an options change.
        """
        # Calculate and set dimensions of a "cell" which is the day number
        # of a particular day or a weekday heading ("Mo", "Tu", ...).
        dc = wx.WindowDC(self)
        try:
            # Initialize dims
            dc.SetFont(self.boldFont)
            cdw, cdh = dc.GetTextExtent(u"00")
            dc.SetFont(self.stdFont)
            
            # Expand cell width if a short weekday is broader
            for i in xrange(7):
                wd = wx.DateTime.GetWeekDayName(i, wx.DateTime.Name_Abbr)
                cdw = max(cdw, dc.GetTextExtent(wd)[0])

            self.cellWidth = cdw
            self.cellHeight = cdh
            
            self.popupShiftX = self.cellWidth // 2
            self.popupShiftY = self.cellHeight - 2
        finally:
            dc.SetFont(wx.NullFont)
            del dc


        # Calc minimal month dimensions

        # 7 weekdays plus minimal distance between them
        self.minMonthWidth = 7 * self.cellWidth + 6 * self.minCellDistHor

        # A month spans over 4 to 6 weeks (at least partially) ignoring the
        # plus one line for month name plus one line for weekday names
        self.minMonthHeight = 8 * self.cellHeight + 7 * self.minCellDistVert


    def recalcLayout(self):
        """
        Recalculate layout after a size change.
        """
        pWidth, pHeight = self.GetSizeTuple()
        
        # How many months side by side
        self.monthCols = \
                (pWidth - 2 * self.minOuterMarginDistHor) // \
                    (self.minMonthWidth + self.minMonthDistHor)

        self.monthRows = \
                (pHeight - 2 * self.minOuterMarginDistVert) // \
                    (self.minMonthHeight + self.minMonthDistVert)

        tooSmall = False
        if self.monthCols < 1:
            self.monthCols = 1
            tooSmall = True
        
        if self.monthRows < 1:
            self.monthRows = 1
            tooSmall = True

        # Initial values for layout
        self.outerMarginLeft = self.minOuterMarginDistHor
        self.outerMarginTop = self.minOuterMarginDistVert
        self.cellDistHor = self.minCellDistHor
        self.cellDistVert = self.minCellDistVert
        self.monthDistHor = self.minMonthDistHor
        self.monthDistVert = self.minMonthDistVert
        self.monthWidth = self.minMonthWidth
        self.monthHeight = self.minMonthHeight


    def getColForWeekDay(self, weekDay):
        """
        Convert a weekDay number (0=Sun, 1=Mon) to the
        appropriate column in month (beginning with 0)
        """
        if self.firstWeekDay == self.Sunday_First:
            return weekDay
        else:
            # Monday first
            if weekDay == 0:
                return 6
            else:
                return weekDay - 1


    def paintDateCell(self, date, startX, startY, dc):
        bgCol = self.getBgColorForCount(self.getWordCountForDay(date))
        brush = wx.Brush(bgCol)
        dc.SetBrush(brush)
        if self._isDarkColour(bgCol):
            dc.SetTextForeground(wx.WHITE)
        else:
            dc.SetTextForeground(wx.BLACK)

        dc.DrawRectangle(startX, startY, self.cellWidth, self.cellHeight)
        
        if self.today == date:
            dc.SetFont(self.boldFont)
            drawTextRight(dc, u"%i" % date.GetDay(), startX, startY,
                    self.cellWidth)            
            dc.SetFont(self.stdFont)
        else:
            drawTextRight(dc, u"%i" % date.GetDay(), startX, startY,
                    self.cellWidth)

        dc.SetBrush(wx.NullBrush)


    def paintMonth(self, startX, startY, month, dc):
        """
        Paint the month on the device context dc
        """
        cellShiftX = self.cellWidth + self.cellDistHor
        cellShiftY = self.cellHeight + self.cellDistVert
        date = month

        # Write month name
        yPos = startY
        dc.SetFont(self.boldFont)
#         monthName = wx.DateTime.GetMonthName(month[0], wx.DateTime.Name_Abbr)
        monthName = date.Format(u"%b %Y")
        drawTextCenter(dc, monthName, startX, yPos, self.monthWidth)
        
#         dc.DrawText(monthName, startX, yPos)
#         drawTextRight(dc, "%i" % month[1], startX, yPos, self.monthWidth)

        # Write weekday shortnames
        dc.SetFont(self.stdFont)
        yPos += cellShiftY
        xPos = startX
        if self.firstWeekDay == self.Sunday_First:
            wdOrder = range(7)
        else:
            wdOrder = range(1, 7) + [0]

        for i in wdOrder:
            wd = wx.DateTime.GetWeekDayName(i, wx.DateTime.Name_Abbr)
            drawTextRight(dc, wd, xPos, yPos, self.cellWidth)
            xPos += cellShiftX

        # Actual day grid
        yPos += cellShiftY
        dateShift = wx.TimeSpan_Day()
        dayCount = wx.DateTime.GetNumberOfDaysInMonth(month.GetMonth(),
                month.GetYear())

        wdCol = self.getColForWeekDay(date.GetWeekDay())
        xPos = startX + wdCol * cellShiftX
        
        for d in xrange(dayCount):
            self.paintDateCell(date, xPos, yPos, dc)
#             dc.DrawText("%i" % d, )

            date = date + dateShift
            xPos += cellShiftX
            wdCol += 1
            if wdCol > 6:
                # New row
                wdCol = 0
                xPos = startX
                yPos += cellShiftY



    def paintCalendar(self, dc):
        month = self.topMonth
        monthDateShift = wx.DateSpan_Month()
        self.today = wx.DateTime.Now()
        self.today.ResetTime()

        monthShiftX = self.monthWidth + self.monthDistHor
        monthShiftY = self.monthHeight + self.monthDistVert
        
        yPos = self.outerMarginTop
        
#         clipX, clipY, clipWidth, clipHeight = dc.GetClippingBox()
#         clipRect = wx.Rect(clipX, clipY, clipWidth, clipHeight)

        for mrow in xrange(self.monthRows):
            xPos = self.outerMarginLeft
            for mcol in xrange(self.monthCols):
#                 monthRect = wx.Rect(xPos, yPos, self.monthWidth,
#                         self.monthHeight)
#                 print "paintCalendar9", repr(monthRect)
# 
#                 if clipRect.Intersects(monthRect):
                self.paintMonth(xPos, yPos, month, dc)

                month = month + monthDateShift
                xPos += monthShiftX
            
            yPos += monthShiftY


    def getWordCountForDay(self, date):
        dateKey = (date.GetDay(), date.GetMonth(), date.GetYear())
        result = self.dayToWordCountCache.get(dateKey)
        if result is None:
            result = len(self.wikiWordFilter.getWikiWordsForDay(date))
            self.dayToWordCountCache[dateKey] = result

        return result

    def OnPaint(self, evt):
        ## _prof.start()
        dc = wx.BufferedPaintDC(self)
        dc.SetBackground(wx.WHITE_BRUSH)
        dc.Clear()
        dc.SetBackground(wx.NullBrush)
        dc.SetPen(wx.TRANSPARENT_PEN)
        self.paintCalendar(dc)
        dc.SetPen(wx.NullPen)
        ## _prof.stop()


    def OnEraseBackground(self, evt):
        pass


    def OnMotion(self, evt):
        if not evt.Moving():
            evt.Skip()
            return
        
        evt.Skip()
        pt = evt.GetPosition()
#         print "OnMotion5", repr(self.HitTest(pt))


    def _getInsideTestRectangle(self):
        return self.GetRect()


    def _getDateAndRectForMousePosition(self, pos):
        """
        pos is relative to self window.
        """
        
        date, flag, rect = self.HitTestAndRect(pos)
        if flag != self.HITTEST_DAY:
            return None, None
            
        return date, rect



    # Constants for HitTest
    # Outside of a month
    HITTEST_NOWHERE = 0
    # In a month, but not on particular date
    HITTEST_MONTH = 1
    # On the title of a month
    HITTEST_MONTH_TITLE = 2
    # On a particular day
    HITTEST_DAY = 3


    def _HitTestInMonth(self, month, posX, posY):
        """
        Called by HitTest

        month -- wx.DateTime object repesenting the first day of
                the month to look at
        posX, posY -- Upper left position of month calendar
        """
        cellShiftX = self.cellWidth + self.cellDistHor
        cellShiftY = self.cellHeight + self.cellDistVert

        cellCol = posX // cellShiftX
        if cellCol >= 7:
            return (month, self.HITTEST_MONTH, None)

        # If cellRow is out of range will be decided later
        cellRow = posY // cellShiftY

        if cellRow == 0:
            # In title
            return (month, self.HITTEST_MONTH_TITLE,
                    wx.Rect(0, 0, self.cellWidth * 7 + self.cellDistHor * 6,
                    self.cellHeight))

        if cellRow == 1:
            # In weekday names
            return (month, self.HITTEST_MONTH, None)

        inCellX = posX % cellShiftX
        inCellY = posY % cellShiftY

        if inCellX >= self.cellWidth or inCellY >= self.cellHeight:
            # Somewhere between cells or a bit too far right/down
            return (month, self.HITTEST_MONTH, None)

        cellNumber = (cellRow - 2) * 7 + cellCol
        
        dayShift = cellNumber - self.getColForWeekDay(month.GetWeekDay())
        
        if dayShift < 0:
            # In a cell to the left of day 1
            return (month, self.HITTEST_MONTH, None)

        dayCount = wx.DateTime.GetNumberOfDaysInMonth(month.GetMonth(),
                month.GetYear())
        
        if dayShift >= dayCount:
            # On an empty cell after the last day of month
            return (month, self.HITTEST_MONTH, None)
        
        date = month + wx.TimeSpan_Days(dayShift)
        
        return (date, self.HITTEST_DAY, wx.Rect(cellCol * cellShiftX,
                cellRow * cellShiftY, self.cellWidth, self.cellHeight))


    def HitTest(self, point):
        return self.HitTest(self, point)[:2]


    def HitTestAndRect(self, point):
        """
        Point must be relative to this control.
        Returns a tuple (date, flag, rect) where date and rect may be None.
        """
        posX = point.x
        posY = point.y
        
        # Find month
        if posX < self.outerMarginLeft or posY < self.outerMarginTop:
            # In the left or top margin -> nowhere
            return (None, self.HITTEST_NOWHERE, None)

        monthShiftX = self.monthWidth + self.monthDistHor
        monthShiftY = self.monthHeight + self.monthDistVert
        
        # Shift position
        posX -= self.outerMarginLeft
        posY -= self.outerMarginTop

        monthCol = posX // monthShiftX
        if monthCol >= self.monthCols:
            # Much too far right
            return (None, self.HITTEST_NOWHERE, None)
            
        monthRow = posY // monthShiftY
        if monthRow >= self.monthRows:
            # Much too far down
            return (None, self.HITTEST_NOWHERE, None)
            
        # Relative position inside month
        inMonthX = posX % monthShiftX
        inMonthY = posY % monthShiftY

        if inMonthX >= self.monthWidth or inMonthY >= self.monthHeight:
            # Somewhere between months or a bit too far right/down
            return (None, self.HITTEST_NOWHERE, None)

        month = self.topMonth + wx.DateSpan_Months(
                monthRow * self.monthCols + monthCol)
                
        date, flag, rect = self._HitTestInMonth(month, inMonthX, inMonthY)
        
        if rect is not None:
            # Make position relative to whole control
            rect.OffsetXY(monthCol * monthShiftX, monthRow * monthShiftY)

        return (date, flag, rect)



class TimeViewCtrl(wx.Notebook):
    def __init__(self, parent, ID, mainControl):
        wx.Notebook.__init__(self, parent, ID)

        self.mainControl = mainControl
        
        wikiWordFilter = DatedWikiWordFilterModified()


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
#                 self.updatePresentation()


    def setVisible(self, vis):
        pass
            
        
        
        
        
        
# from class CalendarPanel
#     def recalcLayout(self):
#         """
#         Recalculate layout after a size change.
#         """
#         pWidth, pHeight = self.GetSizeTuple()
#         
#         # How many months side by side
#         self.monthCols = \
#                 (pWidth - 2 * self.minOuterMarginDistHor) // self.minMonthWidth
# 
#         self.monthRows = \
#                 (pHeight - 2 * self.minOuterMarginDistVert) // self.minMonthHeight
#                 
#         tooSmall = False
#         if self.monthCols < 1:
#             self.monthCols = 1
#             tooSmall = True
#         
#         if self.monthRows < 1:
#             self.monthRows = 1
#             tooSmall = True
# 
#         # Initial values for layout
#         self.outerMarginLeft = self.minOuterMarginDistHor
#         self.outerMarginTop = self.minOuterMarginDistVert
#         self.cellDistHor = self.minCellDistHor
#         self.cellDistVert = self.minCellDistVert
#         self.monthDistHor = self.minMonthDistHor
#         self.monthDistVert = self.minMonthDistVert
#         self.monthWidth = self.minMonthWidth
#         self.monthHeight = self.minMonthHeight
# 
#         if tooSmall:
#             # No remaining space: Nothing more to do
#             return
# 
#         # Now we distribute the remaining space among the possible distances
#         remainWidth = (pWidth - 2 * self.minOuterMarginDistHor) % self.minMonthWidth
#         remainHeight = (pHeight - 2 * self.minOuterMarginDistVert) % self.minMonthHeight
#         
#         distCount = 6 * self.monthCols + (self.monthCols + 1)
#         addValue = remainWidth // distCount
#         remainWidth = remainWidth % distCount
#         self.cellDistHor += addValue
#         self.monthDistHor += addValue
#         self.outerMarginLeft += addValue
#        
#         distCount = 6 * self.monthRows + (self.monthRows + 1)
#         addValue = remainHeight // distCount
#         remainHeight = remainHeight % distCount
#         self.cellDistVert += addValue
#         self.monthDistVert += addValue
#         self.outerMarginTop += addValue
#         
#         distCount = self.monthCols + 1
#         addValue = remainWidth // distCount
#         remainWidth = remainWidth % distCount
#         self.monthDistHor += addValue
#         self.outerMarginLeft += addValue
#        
#         distCount = self.monthRows + 1
#         addValue = remainHeight // distCount
#         remainHeight = remainHeight % distCount
#         self.monthDistVert += addValue
#         self.outerMarginTop += addValue
# 
#         self.outerMarginLeft += remainWidth
#         self.outerMarginTop += remainHeight
#         
#         # Recalculate month width and height
#         self.monthWidth = self.cellWidth * 7 + self.cellDistHor * 6
#         self.monthHeight = self.cellHeight * 7 + self.cellDistVert * 6

