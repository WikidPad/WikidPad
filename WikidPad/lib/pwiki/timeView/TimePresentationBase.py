# import hotshot
# _prof = hotshot.Profile("hotshot.prf")

import os, traceback

import wx

# from MiscEvent import KeyFunctionSinkAR
from pwiki.wxHelper import GUI_ID, wxKeyFunctionSink, cloneFont, \
        getAccelPairFromKeyDown, appendToMenuByMenuDesc, getWxAddress

from pwiki.SystemInfo import isWindows

from .WikiWordListPopup import WikiWordListPopup


class TimePresentationBase:
    """
    Basic functionality for a timeline or calendar panel.
    """
    def __init__(self, mainControl, wikiWordFilter):
        
        self.mainControl = mainControl

        # Some object derived from DatedWikiWordFilterBase
        self.wikiWordFilter = wikiWordFilter
        
        self.wikiWordListPopup = None
        # Shift from upper left corner of selected cell/list item
        self.popupShiftX = 5
        self.popupShiftY = 5

        self.labelEdit = False  # Is currently a label edit running?
        
        # Is control in the top layer?
        self.layerVisible = True
        self.sizeVisible = True

        self.Bind(wx.EVT_MOTION, self.OnMouseMotion)
        self.Bind(wx.EVT_LEAVE_WINDOW, self.OnMouseLeave)


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
        if not self.isVisibleEffect():
            if self.wikiWordListPopup is not None:
                self.setWikiWordListPopup(None)

            if wx.Window.FindFocus() is self:
                self.mainControl.getMainAreaPanel().SetFocus()

    def setLayerVisible(self, vis, scName=""):
        oldVisible = self.isVisibleEffect()
        self.layerVisible = vis
        if oldVisible != self.isVisibleEffect():
            self.handleVisibilityChange()
    
        
    def close(self):
        pass
        
    def showContextMenuOnTab(self):
        """
        Called by the TimeView to show a context menu if the tab was
        context-clicked.
        """
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
        if self.wikiWordListPopup.wxAddress != getWxAddress(evt.GetEventObject()):
            evt.Skip()
            return
            
        self.wikiWordListPopup = None

        evt.Skip()


    def setWikiWordListPopup(self, popup):
        if self.wikiWordListPopup is not None:
            self.wikiWordListPopup.Unbind(wx.EVT_WINDOW_DESTROY)
            self.wikiWordListPopup.Unbind(wx.EVT_LEAVE_WINDOW)
            self.wikiWordListPopup.Destroy()

        self.wikiWordListPopup = popup

        if self.wikiWordListPopup is not None:
            self.wikiWordListPopup.wxAddress = getWxAddress(
                    self.wikiWordListPopup)

            self.wikiWordListPopup.Bind(wx.EVT_WINDOW_DESTROY,
                    self.OnWikiWordListPopupDestroyed)
            self.wikiWordListPopup.Bind(wx.EVT_LEAVE_WINDOW,
                    self.OnMouseLeave)


    def showWikiWordListPopupForDay(self, day, rect):
        if self.wikiWordListPopup is not None:
            if self.wikiWordListPopup.date == day:
                # On same item yet, nothing to do
                return

            self.setWikiWordListPopup(None)


        if not self.labelEdit and day is not None:
            wikiWords = self.wikiWordFilter.getWikiWordsForDay(day)
            
            if len(wikiWords) == 0:
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
            
            # Note: Using Freeze/Thaw here makes things worse
            self.wikiWordListPopup.Show()
            if focus is not None:
                focus.SetFocus()



    def OnMouseMotion(self, evt):
        if evt.Dragging() or not self.mainControl.getConfig().getboolean("main",
                "timeView_showWordListOnHovering", True):
            evt.Skip()
            return

        pos = evt.GetPosition()
        
#         item = self.HitTest(pos)[0]

        day, rect = self._getDateAndRectForMousePosition(pos)
        self.showWikiWordListPopupForDay(day, rect)


    def OnMouseLeave(self, evt):
        """
        Called if either the timeline or the wiki words popup window is left.
        """
        mousePos = wx.GetMousePosition()
        pos = self.ScreenToClient(mousePos)
#         print "OnMouseLeave1", repr((self.GetRect(), self.GetParent().GetRect(), mousePos, pos, evt.GetEventObject()))

        tlRect = self._getInsideTestRectangle()

        if tlRect.Contains(pos):
            evt.Skip()
            return

        if self.wikiWordListPopup is not None:
            if self.wikiWordListPopup.isInsideList(mousePos):
                evt.Skip()
                return
            self.setWikiWordListPopup(None)
        evt.Skip()


