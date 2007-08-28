# import hotshot
# _prof = hotshot.Profile("hotshot.prf")

import os, traceback, codecs
import threading
from time import sleep

import wx

import Utilities
from Utilities import DUMBTHREADHOLDER
from MiscEvent import KeyFunctionSinkAR

# from Configuration import isWindows
from wxHelper import EnhancedListControl

from WikiFormatting import HEADING_LEVEL_MAP, getHeadingLevel

# from WikiExceptions import WikiWordNotFoundException, WikiFileNotFoundException

# from StringOps import *
# utf8Enc, utf8Dec, mbcsEnc, mbcsDec, uniToGui, guiToUni, \
#        Tokenizer, wikiWordToLabel, revStr, lineendToInternal, lineendToOs


class DocStructureCtrl(EnhancedListControl):
    def __init__(self, parent, ID, mainControl):
        EnhancedListControl.__init__(self, parent, ID,
                style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.LC_NO_HEADER)

        self.mainControl = mainControl

        self.InsertColumn(0, u"", width=3000)

#         self.mainAreaPanel = self.mainControl.getMainAreaPanel()
#         self.mainAreaPanel.getMiscEvent().addListener(self)

        self.updatingThreadHolder = Utilities.ThreadHolder()
        self.tocList = [] # List of tuples (char. start in text, headLevel, heading text)
        self.mainControl.getMiscEvent().addListener(self)
        self.readablySized = True   # False if this window has a size
                # that it can't be read (one dim. less than 5 pixels)

        self.docPagePresenterSinkAR = KeyFunctionSinkAR((
                ("loaded current doc page", self.onUpdateNeeded),
                ("changed live text", self.onUpdateNeeded),
                ("options changed", self.onUpdateNeeded)
        ))

        self.docPagePresenterSinkAR.setEventSource(
                self.mainControl.getCurrentDocPagePresenter())

        self.updateList()

        wx.EVT_WINDOW_DESTROY(self, self.OnDestroy)
        wx.EVT_LIST_ITEM_SELECTED(self, self.GetId(), self.OnItemSelected)
        wx.EVT_LIST_ITEM_ACTIVATED(self, self.GetId(), self.OnItemActivated)
        wx.EVT_SIZE(self, self.OnSize)
        
        wx.EVT_KILL_FOCUS(self, self.OnKillFocus)
#         wx.EVT_LEFT_UP(self, self.OnLeftUp)


    def close(self):
        """
        """
        self.docPagePresenterSinkAR.disconnect()

    def OnDestroy(self, evt):
        self.close()


    def OnSize(self, evt):
        evt.Skip()
        oldReadablySized = self.readablySized
        size = evt.GetSize()
        self.readablySized = size.GetHeight() >= 5 and size.GetWidth() >= 5
        
        if oldReadablySized == self.readablySized:
            # No change
            return
        
        if oldReadablySized:
            self.docPagePresenterSinkAR.disconnect()
        else:
            self.docPagePresenterSinkAR.setEventSource(
                    self.mainControl.getCurrentDocPagePresenter())
            self.updateList()


    def miscEventHappened(self, miscevt):
        """
        Handle misc events
        """
        if self.readablySized and miscevt.getSource() is self.mainControl:
            if miscevt.has_key("changed current docpage presenter"):
                self.docPagePresenterSinkAR.setEventSource(
                        self.mainControl.getCurrentDocPagePresenter())
                self.updateList()


    def onUpdateNeeded(self, miscevt):
#         print "onUpdateNeeded"
        self.updateList()


#     def updateList(self):
#         _prof.start()
#         self._updateList()
#         _prof.stop()


    def updateList(self):
        presenter = self.docPagePresenterSinkAR.getEventSource()
        if presenter is None:
            return

#         print "updateList"
        text = presenter.getLiveText()
        docPage = presenter.getDocPage()

        # Asynchronous update
        uth = self.updatingThreadHolder

        delay = presenter.getConfig().getfloat(
                "main", "async_highlight_delay")
        depth = presenter.getConfig().getint(
                "main", "docStructure_depth")
        
        t = threading.Thread(None, self.buildTocList,
                args = (text, docPage, depth, uth))
        uth.setThread(t)
        t.start()


    def buildTocList(self, text, docPage, depth, threadholder=DUMBTHREADHOLDER):
        """
        Build toc list and put data in self.tocList. Finally call applyTocList()
        to show data.
        """
#         print "buildTocList start"
#         try:
        if docPage is None:
            return
        
        sleep(0.3)   # Make configurable?
        if not threadholder.isCurrent():
            return

        depth = min(depth, 15)
        depth = max(depth, 1)

        pageAst = docPage.getLivePageAst(text, threadholder)

        result = []
        for headTType in HEADING_LEVEL_MAP.keys():
            if not threadholder.isCurrent():
                return

            headLevel = getHeadingLevel(headTType)
            if headLevel > depth:
                continue

            tokens = pageAst.findTypeFlat(headTType)

            for tok in tokens:
                title = tok.text
                if title.endswith(u"\n"):
                    title = title[-1]
                result.append((tok.start, headLevel, tok.text))

        result.sort()

        if not threadholder.isCurrent():
            return

        self.tocList = result

        if threadholder is DUMBTHREADHOLDER:
            self.applyTocList()
        else:
            wx.CallAfter(self.applyTocList)
#         finally:
#             print "buildTocList end"


    def applyTocList(self):
        """
        Show the content of self.tocList in the ListCtrl
        """
        self.Freeze()
        try:
            self.DeleteAllItems()
            for start, headLevel, text in self.tocList:
                self.InsertStringItem(self.GetItemCount(), text)
        finally:
            self.Thaw()


#     def getAllSelectedIndices(self):
#         result = []
#         sel = -1
#         while True:
#             sel = self.GetNextItem(sel, state=wx.LIST_STATE_SELECTED)
#             if sel == -1:
#                 break
#             result.append(sel)
# 
#         return result
# 
# 
#     if isWindows():
#         _SETSSI_ITEMMASK = wx.LIST_STATE_SELECTED | wx.LIST_STATE_FOCUSED
#     else:
#         # TODO Check for MacOS
#         _SETSSI_ITEMMASK = wx.LIST_STATE_SELECTED
# 
#     def setSingleSelectedIndex(self, pos):
#         # Unselect all selected
#         for prev in self.getAllSelectedIndices():
#             self.SetItemState(prev, 0, self._SETSSI_ITEMMASK)
# 
#         if pos > -1:
#             self.SetItemState(pos, self._SETSSI_ITEMMASK, self._SETSSI_ITEMMASK)


    def OnKillFocus(self, evt):
        self.SelectSingle(-1)
        evt.Skip()
        
        
#     def OnLeftUp(self, evt):
#         print "OnLeftUp"
#         if self.FindFocus() is self:
#             evt.Skip()
#         # Consume event otherwise


    def displayInSubcontrol(self, start):   # , focusToSubctrl
        """
        Display title in subcontrol of current presenter which
        starts at byte position start in page text.
        
        focusToSubctrl -- True iff subcontrol should become focused after
                displaying is done
        """

        presenter = self.docPagePresenterSinkAR.getEventSource()
        if presenter is None:
            return

        # Find out which subcontrol is currently active
        scName = presenter.getCurrentSubControlName()
        subCtrl = presenter.getSubControl(scName)
        
        if scName == "textedit":
            # Text editor is active
            subCtrl.gotoCharPos(start)
        elif scName == "preview": 
            # HTML preview
            subCtrl.gotoAnchor(u".h%i" % start)
            
#         if focusToSubctrl:
#             subCtrl.SetFocus()
#             # wx.CallAfter(presenter.SetFocus)
            

    def OnItemSelected(self, evt):
        start = self.tocList[evt.GetIndex()][0]
        self.displayInSubcontrol(start)



    def OnItemActivated(self, evt):
        presenter = self.docPagePresenterSinkAR.getEventSource()
        if presenter is None:
            return

        # Find out which subcontrol is currently active
        scName = presenter.getCurrentSubControlName()
        subCtrl = presenter.getSubControl(scName)

        if self.mainControl.getConfig().getboolean("main",
                "docStructure_autohide", False):
            # Auto-hide tree
            self.mainControl.setShowDocStructure(False)

        subCtrl.SetFocus()
        # wx.CallAfter(presenter.SetFocus)

            
        

