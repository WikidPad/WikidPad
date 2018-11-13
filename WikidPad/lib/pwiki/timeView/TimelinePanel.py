

# import hotshot
# _prof = hotshot.Profile("hotshot.prf")

import os, traceback

import wx

# from MiscEvent import KeyFunctionSinkAR
from ..wxHelper import GUI_ID, EnhancedListControl, wxKeyFunctionSink, cloneFont, \
        getAccelPairFromKeyDown, appendToMenuByMenuDesc, IdRecycler

from ..StringOps import formatWxDate

from ..SystemInfo import isWindows

from .TimePresentationBase import TimePresentationBase


class TimelinePanel(EnhancedListControl, TimePresentationBase):
    def __init__(self, parent, ID, mainControl, wikiWordFilter):
        EnhancedListControl.__init__(self, parent, ID,
                style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.LC_NO_HEADER |
                wx.LC_EDIT_LABELS)

        TimePresentationBase.__init__(self, mainControl, wikiWordFilter)

        self.InsertColumn(0, "", width=1)  # date
        self.InsertColumn(1, "", width=1)  # number of wiki words

        # Now gather some information
        self.InsertItem(0, "1")
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
        self.clientHeight = self.GetClientSize()[1]
        
        self.visibleItemCount = (self.clientHeight - 6) // self.itemHeight
        
        self.contextMenuWikiWords = IdRecycler()  # {menuid: wiki word to go to}
        self.listContent = [] # Tuples (wx.DateTime day, <number of wikiwords for day>)
        self.listMaxWordCount = 0  # max number of wikiwords over entries in listContent
        self.wikiWordListPopup = None

        self.firstResize = True  # Hack

#         self.topDay = None  # currTime - wx.TimeSpan.Days(self.visibleItemCount - 1)

        # Sets which day should be shown at which index
        self.fixedItemDay = None
        self.fixedItemIndex = 0

        self.minMaxDayCache = None

        self.Bind(wx.EVT_KEY_DOWN, self.OnKeyDown)

#         self.Bind(wx.EVT_SIZE, self.OnSize)
#         self.Bind(wx.EVT_ERASE_BACKGROUND, self.OnEraseBg)
        self.Bind(wx.EVT_CONTEXT_MENU, self.OnContextMenu)
#         self.Bind(wx.EVT_MOTION, self.OnMouseMotion)
        self.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self.OnItemActivated, id=self.GetId())
        self.Bind(wx.EVT_LIST_ITEM_SELECTED, self.OnItemSelected, id=self.GetId())

        self.Bind(wx.EVT_LIST_BEGIN_LABEL_EDIT, self.OnBeginLabelEdit, id=self.GetId())
        self.Bind(wx.EVT_LIST_END_LABEL_EDIT, self.OnEndLabelEdit, id=self.GetId())
        
        self.Bind(wx.EVT_MENU, self.OnCmdCheckShowEmptyDays, id=GUI_ID.CMD_CHECKBOX_TIMELINE_SHOW_EMPTY_DAYS)
        self.Bind(wx.EVT_UPDATE_UI, self.OnCmdCheckUpdateEmptyDays, id=GUI_ID.CMD_CHECKBOX_TIMELINE_SHOW_EMPTY_DAYS)

        self.Bind(wx.EVT_MENU, self.OnCmdCheckDateAscending, id=GUI_ID.CMD_CHECKBOX_TIMELINE_DATE_ASCENDING)
        self.Bind(wx.EVT_UPDATE_UI, self.OnCmdCheckUpdateDateAscending, id=GUI_ID.CMD_CHECKBOX_TIMELINE_DATE_ASCENDING)




#     def currentDateToBottom(self):
#         currTime = wx.DateTime.Now()
#         currTime.ResetTime()
#         
#         self.topDay = currTime - wx.TimeSpan.Days(self.visibleItemCount - 1)
#         self.updateContent()



    def adjustToSize(self):
        size = self.GetSize()

        self.clientHeight = size.GetHeight()

        if self.clientHeight - 6 < self.itemHeight:
            # Doesn't make sense to calculate further
            # This may especially happen for the initial call on Linux
            return

        self.visibleItemCount = (self.clientHeight - 6) // self.itemHeight

        # print "adjustToSize", repr(self.clientHeight), self.visibleItemCount, self.visibleItemCount * self.itemHeight
        
        if self.firstResize:
            currTime = wx.DateTime.Now()
            currTime.ResetTime()
            
#             self.topDay = currTime - wx.TimeSpan.Days(self.visibleItemCount - 1)

            self.fixedItemDay = currTime

            if self.mainControl.getConfig().getboolean("main",
                    "timeline_sortDateAscending", True):
                self.fixedItemIndex = self.visibleItemCount - 1
            else:
                self.fixedItemIndex = 0

            # Register for pWiki events
            self.__sinkMc = wxKeyFunctionSink((
                    ("opened wiki", self.onUpdateNeeded),
                    ("closed current wiki", self.onUpdateNeeded)
#                     ("changed options", self.onUpdateNeeded)
            ), self.mainControl.getMiscEvent(), self)

            self.__sinkWikiDoc = wxKeyFunctionSink((
                    ("updated wiki page", self.onUpdateNeeded),
                    ("deleted wiki page", self.onUpdateNeeded)
            ), self.mainControl.getCurrentWikiDocumentProxyEvent(), self)

            self.__sinkApp = wxKeyFunctionSink((
                    ("options changed", self.onUpdateNeeded),
            ), wx.GetApp().getMiscEvent(), self)

            self.firstResize = False
            
#         size = evt.GetSize()
        self.sizeVisible = size.GetHeight() >= 5 and size.GetWidth() >= 5

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


    def SetSize(self, *size):
        wx.ListCtrl.SetSize(self, *size)

        oldVisible = self.isVisibleEffect()
        self.adjustToSize()
        if oldVisible != self.isVisibleEffect():
            self.handleVisibilityChange()


    def SetDimensions(self, x, y, width, height, flags=wx.SIZE_AUTO):
        wx.ListCtrl.SetDimensions(self, x, y, width, height, flags)

        oldVisible = self.isVisibleEffect()
        self.adjustToSize()
        if oldVisible != self.isVisibleEffect():
            self.handleVisibilityChange()


    def handleVisibilityChange(self):
        """
        Only call after isVisibleEffect() really changed its value.
        The new value is taken from isVisibleEffect(), the old is assumed
        to be the opposite.
        """
        if self.isVisibleEffect():
            self.clearCache()
            # Trick to make switching look faster
            wx.CallLater(1, self.updateContent)

        TimePresentationBase.handleVisibilityChange(self)


    def onUpdateNeeded(self, miscevt):
        self.clearCache()
        self.updateContent()


    def updateContent(self):
        # First update the filter
        self.wikiWordFilter.setWikiDocument(self.mainControl.getWikiDocument())
        self.wikiWordFilter.setDayResolution(self.stepDays)
        
        if not self.isVisibleEffect() or not self.mainControl.isWikiLoaded():
            self.listMaxWordCount = 0
            self.listContent = []
            self.updatePresentation()
            return

        timeAscend = self.mainControl.getConfig().getboolean("main",
                "timeline_sortDateAscending", True)

        if self.mainControl.getConfig().getboolean("main",
                "timeline_showEmptyDays", True):
            self._updateContentWithEmptyDays(timeAscend)
        else:
            self._updateContentWithoutEmptyDays(timeAscend)

        self.updatePresentation()


    def _updateContentWithEmptyDays(self, ascendTime):
        stepDateSpan = wx.TimeSpan.Days(self.stepDays)

        # Collect data
        if ascendTime:
            currTime = self.fixedItemDay - wx.TimeSpan.Days(
                    self.fixedItemIndex)
        else:
            currTime = self.fixedItemDay - wx.TimeSpan.Days(
                    self.visibleItemCount - self.fixedItemIndex - 1)

        content = []
        maxWordCount = 0
        massWordCounts = self.wikiWordFilter.getMassWikiWordCountForDays(
                currTime, self.visibleItemCount)
        
        for i in range(self.visibleItemCount):
            wordCount = massWordCounts[i]
            content.append((currTime, wordCount))
            maxWordCount = max(maxWordCount, wordCount)
            currTime = currTime + stepDateSpan  # To ensure copying
        
        if not ascendTime:
            content.reverse()
           
        self.listMaxWordCount = maxWordCount
        self.listContent = content


    def _getNeededDaysBefore(self, neededDays, minDay):
        wwf = self.wikiWordFilter

        beforeDayList = []
        beforeDay = self.fixedItemDay

        while neededDays > 0:
            if beforeDay <= minDay:
                # No more wiki words before this day
                break

            days = wwf.getDaysBefore(beforeDay, limit=40)  # TODO variable limit

            if len(days) == 0:
                # Second check: No more wiki words before this day                
                break

            if len(days) > neededDays:
                days = days[-neededDays:]

            beforeDayList = days + beforeDayList
            neededDays -= len(days)

            beforeDay = days[0]
            
        return beforeDayList
        
        
    def _getNeededDaysAfter(self, neededDays, maxDay):
        wwf = self.wikiWordFilter

        afterDayList = []
        afterDay = self.fixedItemDay

        while neededDays > 0:
            if afterDay >= maxDay:
                # No more wiki words after this day
                break

            days = wwf.getDaysAfter(afterDay, limit=40)  # TODO variable limit

            if len(days) == 0:
                # Second check: No more wiki words after this day                
                break

            if len(days) > neededDays:
                days = days[:neededDays]

            afterDayList += days
            neededDays -= len(days)

            afterDay = days[-1]
            
        return afterDayList

        

    def _updateContentWithoutEmptyDays(self, ascendTime):
        wwf = self.wikiWordFilter
        minDay, maxDay = wwf.getMinMaxDay()

#         if minDay is None:
#             self.listMaxWordCount = 0
#             self.listContent = []
#             return

        # Test if fixed item day is allowed (word count > 0)
        fixedCount = len(wwf.getWikiWordsForDay(self.fixedItemDay))

        if fixedCount == 0:
            # Not allowed -> adjust to next allowed day
            after = wwf.getDaysAfter(self.fixedItemDay, limit=1)
            if len(after) > 0:
                self.fixedItemDay = after[0]
            else:
                # No day after -> find day before
                before = wwf.getDaysBefore(self.fixedItemDay, limit=1)

                if len(before) > 0:
                    self.fixedItemDay = before[0]
                else:
                    # No days with wiki words at all
                    self.listMaxWordCount = 0
                    self.listContent = []
                    return

            fixedCount = len(wwf.getWikiWordsForDay(self.fixedItemDay))


        minDay, maxDay = wwf.getMinMaxDay()

        # Fill list with items before fixed item
        if ascendTime:
            neededDays = self.fixedItemIndex
            beforeDayList = self._getNeededDaysBefore(neededDays, minDay)

            self.fixedItemIndex = min(self.fixedItemIndex, len(beforeDayList))

            neededDays = self.visibleItemCount - self.fixedItemIndex - 1
            neededDays = max(0, neededDays)
            afterDayList = self._getNeededDaysAfter(neededDays, maxDay)
        else:
            neededDays = self.fixedItemIndex
            afterDayList = self._getNeededDaysAfter(neededDays, maxDay)

            self.fixedItemIndex = min(self.fixedItemIndex, len(afterDayList))

            neededDays = self.visibleItemCount - self.fixedItemIndex - 1
            neededDays = max(0, neededDays)
            beforeDayList = self._getNeededDaysBefore(neededDays, minDay)


        # Build content list
        content = []
        maxWordCount = 0
        
        if len(beforeDayList) > self.visibleItemCount:
            beforeDayList = beforeDayList[:self.visibleItemCount]
            
        for day in beforeDayList:
            wordCount = len(wwf.getWikiWordsForDay(day))
            maxWordCount = max(maxWordCount, wordCount)
            content.append((day, wordCount))
            
        if len(content) < self.visibleItemCount:
            maxWordCount = max(maxWordCount, fixedCount)
            content.append((self.fixedItemDay, fixedCount))
        
        for day in afterDayList:
            wordCount = len(wwf.getWikiWordsForDay(day))
            maxWordCount = max(maxWordCount, wordCount)
            content.append((day, wordCount))
            
        if not ascendTime:
            content.reverse()
            
        self.listMaxWordCount = maxWordCount
        self.listContent = content


    def updatePresentation(self):
        """
        Visual update of the list. self.listContent must be
        precalculated elsewhere.
        """
        formatStr = self.mainControl.getConfig().get("main",
                "timeView_dateFormat", "%Y %m %d")
                
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
                col0txt = formatWxDate(formatStr, t)
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


    def clearCache(self):
        self.minMaxDayCache = None


    def getMinMaxDay(self):
        if self.minMaxDayCache is None:
            self.minMaxDayCache = self.wikiWordFilter.getMinMaxDay()

        return self.minMaxDayCache


    def showContextMenuForItem(self, item):
        self.labelEdit = True
        try:
            self.setWikiWordListPopup(None)
    
            if item == wx.NOT_FOUND:
                menu = wx.Menu()
                appendToMenuByMenuDesc(menu, _CONTEXT_MENU_TIMELINE)
                self.PopupMenu(menu)
                return
                
            day = self.listContent[item][0]
            wikiWords = self.wikiWordFilter.getWikiWordsForDay(day)
            
            if len(wikiWords) == 0:
                menu = wx.Menu()
                appendToMenuByMenuDesc(menu, _CONTEXT_MENU_TIMELINE)
                self.PopupMenu(menu)
                return

            self.mainControl.getCollator().sort(wikiWords)

#             reusableIds = self.contextMenuWikiWords.keys()
            menu = wx.Menu()

#             cmc = {}

            for word in wikiWords:
                menuID, reused = self.contextMenuWikiWords.assocGetIdAndReused(
                        word)
                
                if not reused:
                    # For a new id, an event must be set
                    self.Bind(wx.EVT_MENU, self.OnWikiWordInMenu, id=menuID)

#                 if len(reusableIds) > 0:
#                     menuId = reusableIds.pop()
#                 else:
#                     menuId = wx.NewId()
#                     self.Bind(wx.EVT_MENU, self.OnWikiWordInMenu, id=menuId)
# 
#                 cmc[menuId] = word
                menuItem = wx.MenuItem(menu, menuID, word)
                menu.Append(menuItem)

#             # Add remaining ids to prevent them from getting lost
#             for i in reusableIds:
#                 cmc[i] = None
#     
#             self.contextMenuWikiWords = cmc


            appendToMenuByMenuDesc(menu, "-\n" + _CONTEXT_MENU_TIMELINE)
            
            self.PopupMenu(menu)
        finally:
            self.labelEdit = False
        
    
    def showContextMenuOnTab(self):
        """
        Called by the TimeView to show a context menu if the tab was
        context-clicked.
        """
        self.labelEdit = True
        try:
            self.setWikiWordListPopup(None)
    
            menu = wx.Menu()
            appendToMenuByMenuDesc(menu, _CONTEXT_MENU_TIMELINE)
            self.PopupMenu(menu)
        finally:
            self.labelEdit = False


    def OnContextMenu(self, evt):
        mousePos = evt.GetPosition()
        if mousePos == wx.DefaultPosition:
            # E.g. context menu key was pressed on Windows keyboard
            item = self.GetFirstSelected()
        else:
            item = self.HitTest(self.ScreenToClient(mousePos))[0]

#         pos = self.ScreenToClient(wx.GetMousePosition())
#         item = self.HitTest(pos)[0]

        self.showContextMenuForItem(item)


    def OnItemActivated(self, evt):
        self.showContextMenuForItem(evt.GetIndex())


#     def OnItemSelected(self, evt):
#         print "OnItemSelected1", repr(evt.GetIndex())
#         
#         evt.Skip()


    def OnItemSelected(self, evt):
        evt.Skip()

        if not self.mainControl.getConfig().getboolean("main",
                "timeView_showWordListOnSelect", False):
            return

        item = evt.GetIndex()
        if item == wx.NOT_FOUND:
            return

        self.showWikiWordListPopupForDay(self.listContent[item][0],
                self.GetItemRect(item))


    def OnWikiWordInMenu(self, evt):
        word = self.contextMenuWikiWords[evt.GetId()]
#         self.mainControl.activateWikiWord(word, 0)
        self.mainControl.activatePageByUnifiedName(
                "wikipage/" + word, 0)



    def OnCmdCheckShowEmptyDays(self, evt):
        self.mainControl.getConfig().set("main", "timeline_showEmptyDays",
                evt.IsChecked())
        self.updateContent()


    def OnCmdCheckUpdateEmptyDays(self, evt):
        evt.Check(self.mainControl.getConfig().getboolean("main",
                "timeline_showEmptyDays", True))


    def OnCmdCheckDateAscending(self, evt):
        oldVal = self.mainControl.getConfig().getboolean("main",
                "timeline_sortDateAscending", True)
        newVal = evt.IsChecked()
        if oldVal != newVal:
            # Turn position of fixed index
            self.fixedItemIndex = self.visibleItemCount - self.fixedItemIndex - 1
            self.fixedItemIndex = max(0, self.fixedItemIndex)

        self.mainControl.getConfig().set("main", "timeline_sortDateAscending",
                newVal)
        self.updateContent()

    def OnCmdCheckUpdateDateAscending(self, evt):
        evt.Check(self.mainControl.getConfig().getboolean("main",
                "timeline_sortDateAscending", True))


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
        self.setWikiWordListPopup(None)


    def OnEndLabelEdit(self, evt):
        formatStr = self.mainControl.getConfig().get("main",
                "timeView_dateFormat", "%Y %m %d")
                
        self.labelEdit = False
        
        if not evt.IsEditCancelled():
            evt.Veto()

            newDate = wx.DateTime()
            if newDate.ParseFormat(evt.GetText(), formatStr) == -1:
                return

            newDate.ResetTime()
#             self.topDay = newDate - wx.TimeSpan.Days(evt.GetIndex())
            self.fixedItemDay = newDate
            self.fixedItemIndex = evt.GetIndex()
            
            self.updateContent()


    def OnKeyDown(self, evt):
        accP = getAccelPairFromKeyDown(evt)

        if accP == (wx.ACCEL_NORMAL, wx.WXK_F2) and not self.labelEdit:
            sel = self.GetFirstSelected()
            if sel != -1:
                self.EditLabel(sel)
        else:
            evt.Skip()



_CONTEXT_MENU_TIMELINE = \
"""
+Show empty days;CMD_CHECKBOX_TIMELINE_SHOW_EMPTY_DAYS;Show dates without associated wiki words
+Sort dates ascending;CMD_CHECKBOX_TIMELINE_DATE_ASCENDING;List dates ascending or descending
"""

# Entries to support i18n of context menus
if not True:
    N_("Show empty days")
    N_("Show dates without associated wiki words")
    N_("Sort dates ascending")
    N_("List dates ascending or descending")


