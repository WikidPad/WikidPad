"""
GUI support and error checking for handling attributes (=properties)
"""

import traceback

import wx, wx.xrc

from .wxHelper import *

from .WikiExceptions import *




class LogMessage:
    """
    Represents a message (hint, warning, error) presented in the log
    window and defines a reaction on double clicking on it
    """
    SEVERITY_HINT = 5
    SEVERITY_WARNING = 3
    SEVERITY_ERROR = 1
    
    def __init__(self, mainControl, severity, title, checkedWikiWord, gotoWikiWord,
            selection):
        """
        mainControl -- currently the PersonalWikiFrame instance
        severity -- one of the SEVERITY_* constants
        title -- message text
        checkedWikiWord -- Name of word whose page was checked as message
            occurred. Normally identical to wikiWord. Used to delete all related
            messages if word is checked again.
        wikiWord -- wiki word to jump to on activation
        selection -- tuple (<start char pos>, <after end char pos>) to select
            text in the wikiWord page or (-1, -1) to select nothing
        """
        self.mainControl = mainControl
        self.severity = severity
        self.title = title
        self.checkedWikiWord = checkedWikiWord

        # Where to go on activation?
        self.gotoWikiWord = gotoWikiWord
        self.selection = selection


    def getCheckedWikiWord(self):
        return self.checkedWikiWord
        
    def getGotoWikiWord(self):
        return self.gotoWikiWord

    def getTitle(self):
        return "%s: %s" % (self.gotoWikiWord, self.title)

    def onActivate(self):
        """
        React on activation (double-click)
        """
        if self.gotoWikiWord is not None:
            self.mainControl.openWikiPage(self.gotoWikiWord)
            if self.selection is not None and self.selection != (-1, -1):
                self.mainControl.getActiveEditor().showSelectionByCharPos(
                        *self.selection)
            
            self.mainControl.getActiveEditor().SetFocus()



class LogWindow(wx.Panel):
    def __init__(self, parent, id, mainControl):
        wx.Panel.__init__(self)
#         d = wx.PrePanel()
#         self.PostCreate(d)

        self.mainControl = mainControl
        res = wx.xrc.XmlResource.Get()
        res.LoadPanel(self, parent, "LogWindow")
        self.ctrls = XrcControls(self)
        self.ctrls.lcEntries.InsertColumn(0, _("Message"))

        self.messages = []
        self.sizeVisible = True
        
        self.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self.OnEntryActivated, id=GUI_ID.lcEntries) 
        self.Bind(wx.EVT_BUTTON, self.OnClearLog, id=GUI_ID.btnClearLog)
        self.Bind(wx.EVT_BUTTON, self.OnHideLogWindow, id=GUI_ID.btnHideLogWindow)
        self.Bind(wx.EVT_SIZE, self.OnSize)

    def close(self):
        pass

    def appendMessage(self, msg):
        l = self.ctrls.lcEntries.GetItemCount()
        self.ctrls.lcEntries.InsertItem(l, msg.getTitle())
        self.ctrls.lcEntries.EnsureVisible(l)

        self.messages.append(msg)
#         self.ctrls.lcEntries.SetColumnWidth(0, wx.LIST_AUTOSIZE)
        autosizeColumn(self.ctrls.lcEntries, 0)

    def removeWithCheckedWikiWord(self, checkedWikiWord):
        """
        Remove message for which checkedWikiWord is equal
        the checkedWikiWord of the message. Used to replace
        previous entries by new ones.
        
        It is recommended to call checkAutoShowHide() after possible adding
        or removing of new entries, so the window can show or hide if in fact
        no entries are present.
        """
        dellist = []
        newmsgs = []
        
        # Find msgs to delete and create new message list
        for i, m in enumerate(self.messages):
            if m.getCheckedWikiWord() == checkedWikiWord:
                dellist.append(i)
            else:
                newmsgs.append(m)
                
        dellist.reverse()
        
        # Remove entries from list control
        for i in dellist:
            self.ctrls.lcEntries.DeleteItem(i)
            
        self.messages = newmsgs


    def clear(self):
        self.ctrls.lcEntries.DeleteAllItems()
        self.messages = []
        self.checkAutoShowHide()


    def checkAutoShowHide(self):
        """
        Hides the log window if autohide is in effect and log is empty and
        shows it if not empty and autoshow is in effect.
        """
        if self.mainControl.getConfig().getboolean(
                "main", "log_window_autohide") and len(self.messages) == 0:
            self.mainControl.hideLogWindow()
        elif self.mainControl.getConfig().getboolean(
                "main", "log_window_autoshow") and len(self.messages) > 0:
            self.mainControl.showLogWindow()


    def updateForWikiWord(self, wikiWord, msgs):
        self.removeWithCheckedWikiWord(wikiWord)
        for msg in msgs:
            self.appendMessage(msg)
        
        self.checkAutoShowHide()


    def OnEntryActivated(self, evt):
        self.messages[evt.GetIndex()].onActivate()

    def OnClearLog(self, evt):
        self.clear()
#         self.ctrls.lcEntries.DeleteAllItems()
#         self.messages = []
#         self.checkAutoShowHide()

    def OnHideLogWindow(self, evt):
        self.mainControl.hideLogWindow()


    def isVisibleEffect(self):
        """
        Is this control effectively visible?
        """
        return self.sizeVisible


    def handleVisibilityChange(self):
        """
        Only call after isVisibleEffect() really changed its value.
        The new value is taken from isVisibleEffect(), the old is assumed
        to be the opposite.
        """
        if not self.isVisibleEffect():
            if wx.Window.FindFocus() is self:
                self.mainControl.getMainAreaPanel().SetFocus()


    def OnSize(self, evt):
        evt.Skip()
        oldVisible = self.isVisibleEffect()
        size = evt.GetSize()
        self.sizeVisible = size.GetHeight() >= 5 and size.GetWidth() >= 5
        
        if oldVisible != self.isVisibleEffect():
            self.handleVisibilityChange()

