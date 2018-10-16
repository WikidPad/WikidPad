# import hotshot
# _prof = hotshot.Profile("hotshot.prf")

import os, traceback

import wx

# from MiscEvent import KeyFunctionSinkAR
from pwiki.wxHelper import GUI_ID, wxKeyFunctionSink, cloneFont, \
        drawTextRight, drawTextCenter, getAccelPairFromKeyDown, \
        appendToMenuByMenuDesc

from pwiki.StringOps import formatWxDate

from pwiki.WindowLayout import setWindowPos, setWindowClientSize, LayeredControlPanel
from pwiki.SystemInfo import isWindows

from .TimePresentationBase import TimePresentationBase



class CalendarPanel(wx.Window, TimePresentationBase):
    # Which day is first in week?
    Monday_First = wx.DateTime.Monday_First
    Sunday_First = wx.DateTime.Sunday_First
    
    def __init__(self, parent, ID, mainControl, wikiWordFilter):
        wx.Window.__init__(self, parent, ID)
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
        
        # wx.DateTime of first day of the month shown in the top left of
        # the panel
        self.topMonth = None
        
        # Day which is selected
        self.selectedDay = None

        # Dictionary which maps days to the count of wiki words
        # Days are tuples (day, month, year)
        self.dayToWordCountCache = {}
        # Are all days which are visible in current layout already in cache?
        self.layoutInDayToWordCountCache = False
        
        # Some type of cache during repainting
        self.today = None

        self.stdFont = self.GetFont()

        self.boldFont = cloneFont(self.stdFont)
        self.boldFont.SetWeight(wx.FONTWEIGHT_BOLD)
        
        # Text control for label (month name) editing, if used
        self.labelEditCtrl = None
        # Info about label which is edited, normally a tuple (date, flag)
        # where date is a wx.DateTime and flag is a HITTEST_ flag
        self.labelEditLabel = None 
        
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

        self.Bind(wx.EVT_PAINT, self.OnPaint)
        self.Bind(wx.EVT_ERASE_BACKGROUND, self.OnEraseBackground)
        self.Bind(wx.EVT_SIZE, self.OnSize)
        self.Bind(wx.EVT_LEFT_DOWN, self.OnLeftDown)

#         self.Bind(wx.EVT_SET_FOCUS, self.OnSetFocus)
#         self.Bind(wx.EVT_KILL_FOCUS, self.OnKillFocus)
        
#         self.Bind(wx.EVT_MOTION, self.OnMotion)


    def adjustToSize(self):
        self.recalcLayout()

        if self.firstResize:
            currMonth = wx.DateTime.Now()
            currMonth.ResetTime()
            currMonth.SetDay(1)
            
            self.topMonth = currMonth - wx.DateSpan.Months(
                    self.monthCols * self.monthRows - 1)
                    
            self.selectedDay = None

            # Register for pWiki events
            self.__sinkMc = wxKeyFunctionSink((
                    ("opened wiki", self.onUpdateNeeded),
                    ("closed current wiki", self.onUpdateNeeded),
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
            self.updateContent()


    def OnSize(self, evt):
        evt.Skip()

        oldVisible = self.isVisibleEffect()
        self.adjustToSize()
        if oldVisible != self.isVisibleEffect():
            self.handleVisibilityChange()


    def onUpdateNeeded(self, miscevt):
        self.updateContent()


    def updateContent(self):
        self.wikiWordFilter.setWikiDocument(self.mainControl.getWikiDocument())
        self.wikiWordFilter.setDayResolution(1)

        # Clear cache and repaint
        self.clearWordCountCache()
        self.Refresh()


    def clearWordCountCache(self):
        self.dayToWordCountCache = {}
        self.layoutInDayToWordCountCache = False

    def fillWordCountCache(self):
        """
        Fill cache with all data needed for the current layout (=visible months)
        """
        if self.layoutInDayToWordCountCache:
            # Already filled
            return

        self.wikiWordFilter.setWikiDocument(self.mainControl.getWikiDocument())
        self.wikiWordFilter.setDayResolution(1)

        date = self.topMonth
        afterLastMonth = date + wx.DateSpan.Months(
                self.monthCols * self.monthRows)
        
        count = (afterLastMonth - date).GetDays()
        
        massWordCounts = self.wikiWordFilter.getMassWikiWordCountForDays(date,
                count)

        step = wx.TimeSpan.Day()
        for i in range(count):
            dateKey = (date.GetDay(), date.GetMonth(), date.GetYear())
            self.dayToWordCountCache[dateKey] = massWordCounts[i]
            date = date + step

        self.layoutInDayToWordCountCache = True


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
            cdw, cdh = dc.GetTextExtent("00")
            dc.SetFont(self.stdFont)
            
            # Expand cell width if a short weekday is broader
            for i in range(7):
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
        pWidth, pHeight = self.GetSize()

        self.sizeVisible = pWidth >= 5 and pHeight >= 5

        oldMonthCount = self.monthCols * self.monthRows

        if self.isVisibleEffect():
            # How many months side by side
            self.monthCols = \
                    (pWidth - 2 * self.minOuterMarginDistHor) // \
                        (self.minMonthWidth + self.minMonthDistHor)
    
            self.monthRows = \
                    (pHeight - 2 * self.minOuterMarginDistVert) // \
                        (self.minMonthHeight + self.minMonthDistVert)
    
            if self.monthCols < 1:
                self.monthCols = 1
    
            if self.monthRows < 1:
                self.monthRows = 1
        else:
            self.monthCols = 0
            self.monthRows = 0

        # Initial values for layout
        self.outerMarginLeft = self.minOuterMarginDistHor
        self.outerMarginTop = self.minOuterMarginDistVert
        self.cellDistHor = self.minCellDistHor
        self.cellDistVert = self.minCellDistVert
        self.monthDistHor = self.minMonthDistHor
        self.monthDistVert = self.minMonthDistVert
        self.monthWidth = self.minMonthWidth
        self.monthHeight = self.minMonthHeight

        if oldMonthCount < (self.monthCols * self.monthRows):
            # The cache may not contain every day needed for current layout
            self.layoutInDayToWordCountCache = False


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
        # Choose cell background color
        bgCol = self.getBgColorForCount(self.getWordCountForDay(date))
        brush = wx.Brush(bgCol)
        dc.SetBrush(brush)
        if self._isDarkColour(bgCol):
            dc.SetTextForeground(wx.WHITE)
        else:
            dc.SetTextForeground(wx.BLACK)

        resetPen = False
        # If this cell is selected, draw it differently
        if self.selectedDay == date and wx.Window.FindFocus() is self:
            dc.SetPen(wx.RED_PEN)
            resetPen = True

        dc.DrawRectangle(startX, startY, self.cellWidth, self.cellHeight)

        if resetPen:
            dc.SetPen(wx.TRANSPARENT_PEN)

        resetFont = False
        if self.today == date:
            dc.SetFont(self.boldFont)
            resetFont = True
            
        drawTextRight(dc, "%i" % date.GetDay(), startX, startY,
                self.cellWidth)            
        
        if resetFont:
            dc.SetFont(self.stdFont)

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
        monthName = formatWxDate("%b %Y", date)
        drawTextCenter(dc, monthName, startX, yPos, self.monthWidth)
        
#         dc.DrawText(monthName, startX, yPos)
#         drawTextRight(dc, "%i" % month[1], startX, yPos, self.monthWidth)

        # Write weekday shortnames
        dc.SetFont(self.stdFont)
        yPos += cellShiftY
        xPos = startX
        if self.firstWeekDay == self.Sunday_First:
            wdOrder = list(range(7))
        else:
            wdOrder = list(range(1, 7)) + [0]

        for i in wdOrder:
            wd = wx.DateTime.GetWeekDayName(i, wx.DateTime.Name_Abbr)
            drawTextRight(dc, wd, xPos, yPos, self.cellWidth)
            xPos += cellShiftX

        # Actual day grid
        yPos += cellShiftY
        dateShift = wx.TimeSpan.Day()
        dayCount = wx.DateTime.GetNumberOfDaysInMonth(month.GetMonth(),
                month.GetYear())

        wdCol = self.getColForWeekDay(date.GetWeekDay())
        xPos = startX + wdCol * cellShiftX
        
        for d in range(dayCount):
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



    def paintCalendar(self, dc, updateRegion=None):
        dc.SetPen(wx.TRANSPARENT_PEN)
        try:
            self.fillWordCountCache()
            month = self.topMonth
            monthDateShift = wx.DateSpan.Month()
            self.today = wx.DateTime.Now()
            self.today.ResetTime()
    
            monthShiftX = self.monthWidth + self.monthDistHor
            monthShiftY = self.monthHeight + self.monthDistVert
            
            yPos = self.outerMarginTop
            
            for mrow in range(self.monthRows):
                xPos = self.outerMarginLeft
                for mcol in range(self.monthCols):
                    if updateRegion is None or \
                            updateRegion.ContainsRectDim(xPos, yPos,
                            self.monthWidth, self.monthHeight) != wx.OutRegion:
    
                        self.paintMonth(xPos, yPos, month, dc)
    
                    month = month + monthDateShift
                    xPos += monthShiftX
                
                yPos += monthShiftY

        finally:
            dc.SetPen(wx.NullPen)


    def getXYForMonth(self, searchedMonth):
        # TODO More elegantly
        month = self.topMonth
        monthDateShift = wx.DateSpan.Month()
        
        monthShiftX = self.monthWidth + self.monthDistHor
        monthShiftY = self.monthHeight + self.monthDistVert
        
        yPos = self.outerMarginTop
        
        for mrow in range(self.monthRows):
            xPos = self.outerMarginLeft
            for mcol in range(self.monthCols):
                if month == searchedMonth:
                    return (xPos, yPos)

                month = month + monthDateShift
                xPos += monthShiftX
            
            yPos += monthShiftY
        
        return (None, None)


    def refreshMonth(self, searchedMonth):
        xPos, yPos = self.getXYForMonth(searchedMonth)

        if xPos is None:
            return
            
        self.RefreshRect(wx.Rect(xPos, yPos, self.monthWidth, self.monthHeight))


    def getWordCountForDay(self, date):
        dateKey = (date.GetDay(), date.GetMonth(), date.GetYear())
        result = self.dayToWordCountCache.get(dateKey)
        if result is None:
            result = len(self.wikiWordFilter.getWikiWordsForDay(date))
            self.dayToWordCountCache[dateKey] = result

        return result

    def OnPaint(self, evt):
        ## _prof.start()
        dc = wx.AutoBufferedPaintDC(self)
        dc.SetBackground(wx.WHITE_BRUSH)
        dc.Clear()
        dc.SetBackground(wx.NullBrush)
        dc.SetPen(wx.TRANSPARENT_PEN)
        self.paintCalendar(dc, self.GetUpdateRegion())
        dc.SetPen(wx.NullPen)
        ## _prof.stop()


    def OnEraseBackground(self, evt):
        pass


#     def OnMotion(self, evt):
#         if not evt.Moving():
#             evt.Skip()
#             return
# 
#         evt.Skip()
#         pt = evt.GetPosition()
# #         print "OnMotion5", repr(self.HitTest(pt))


    def endLabelEdit(self, abort=False):
        if not self.labelEdit:
            return

        if not abort:
            date, flag = self.labelEditLabel
            text = self.labelEditCtrl.GetValue()
            


    def OnLeftDown(self, evt):
        evt.Skip()
        
        pos = evt.GetPosition()
        date, flag, rect = self.HitTestAndRect(pos)
        if flag == self.HITTEST_MONTH_TITLE:
            pass

        self.labelEditCtrl


    def OnSetFocus(self, evt):
        if selectedDay is not None:
            # Clone day
            sel = self.selectedDay + wx.TimeSpan.Days(0)
    
            sel.SetDay(1)
            self.refreshMonth(sel)
        evt.Skip()
        

    def OnKillFocus(self, evt):
        if selectedDay is not None:
            # Clone day
            sel = self.selectedDay + wx.TimeSpan.Days(0)
    
            sel.SetDay(1)
            self.refreshMonth(sel)
        evt.Skip()


#     def OnKeyDown(self, evt):
#         acc = getAccelPairFromKeyDown(evt)
#         newSelection = None
#         
#         if acc in ((wx.ACCEL_NORMAL, wx.WXK_RETURN),
#                 (wx.ACCEL_NORMAL, wx.WXK_NUMPAD_ENTER):
#         elif acc in ((wx.ACCEL_NORMAL, wx.WXK_RETURN),
#                 (wx.ACCEL_NORMAL, wx.WXK_NUMPAD_ENTER):
#         elif acc in ((wx.ACCEL_NORMAL, wx.WXK_RETURN),
#                 (wx.ACCEL_NORMAL, wx.WXK_NUMPAD_ENTER):
#         elif acc in ((wx.ACCEL_NORMAL, wx.WXK_RETURN),
#                 (wx.ACCEL_NORMAL, wx.WXK_NUMPAD_ENTER):
# 
#         if acc == in ((wx.ACCEL_NORMAL, wx.WXK_RETURN),
#                 (wx.ACCEL_NORMAL, wx.WXK_NUMPAD_ENTER):



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
        
        date = month + wx.TimeSpan.Days(dayShift)
        
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


       
        
        
# from class CalendarPanel
#     def recalcLayout(self):
#         """
#         Recalculate layout after a size change.
#         """
#         pWidth, pHeight = self.GetSize()
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
