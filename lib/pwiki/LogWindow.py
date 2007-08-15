"""
GUI support and error checking for handling properties (=attributes)
"""

import sets, traceback

import wx, wx.xrc

from wxHelper import *

from WikiExceptions import *




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
                self.mainControl.getActiveEditor().SetSelectionByCharPos(
                        *self.selection)
            
            self.mainControl.getActiveEditor().SetFocus()



class LogWindow(wx.Panel):
    def __init__(self, parent, id, mainControl):
        d = wx.PrePanel()
        self.PostCreate(d)

        self.mainControl = mainControl
        res = wx.xrc.XmlResource.Get()
        res.LoadOnPanel(self, parent, "LogWindow")
        self.ctrls = XrcControls(self)
        self.ctrls.lcEntries.InsertColumn(0, u"Message")

        self.messages = []
        
        wx.EVT_LIST_ITEM_ACTIVATED(self, GUI_ID.lcEntries, self.OnEntryActivated) 
        wx.EVT_BUTTON(self, GUI_ID.btnClearLog, self.OnClearLog)
        wx.EVT_BUTTON(self, GUI_ID.btnHideLogWindow, self.OnHideLogWindow)


    def close(self):
        pass

    def appendMessage(self, msg):
        l = self.ctrls.lcEntries.GetItemCount()
        self.ctrls.lcEntries.InsertStringItem(l, msg.getTitle())
        self.ctrls.lcEntries.EnsureVisible(l)

        self.messages.append(msg)
        self.ctrls.lcEntries.SetColumnWidth(0, wx.LIST_AUTOSIZE)


    def removeWithCheckedWikiWord(self, checkedWikiWord):
        """
        Remove message for which checkedWikiWord is equal
        the checkedWikiWord of the message. Used to replace
        previous entries by new ones.
        
        It is recommended to call checkAutoHide() after possible adding
        of new entries, so the window can hide if in fact no entries
        are present.
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


    def checkAutoHide(self):
        """
        Hides the log window if autohide is in effect and log is empty
        """
        if self.mainControl.getConfig().getboolean(
                "main", "log_window_autohide") and len(self.messages) == 0:
            self.mainControl.hideLogWindow()

    def OnEntryActivated(self, evt):
        self.messages[evt.GetIndex()].onActivate()

    def OnClearLog(self, evt):
        self.ctrls.lcEntries.DeleteAllItems()
        self.messages = []
        self.checkAutoHide()

    def OnHideLogWindow(self, evt):
        self.mainControl.hideLogWindow()

