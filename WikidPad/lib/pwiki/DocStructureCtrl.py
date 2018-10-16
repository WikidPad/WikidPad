

# import hotshot
# _prof = hotshot.Profile("hotshot.prf")

import os, traceback, codecs, bisect
import threading
from time import sleep

import wx

from . import Utilities
from .Utilities import DUMBTHREADSTOP
# from MiscEvent import KeyFunctionSinkAR
from .WikiExceptions import NotCurrentThreadException

from .wxHelper import EnhancedListControl, wxKeyFunctionSink, WindowUpdateLocker


class DocStructureCtrl(EnhancedListControl):
    def __init__(self, parent, ID, mainControl):
        EnhancedListControl.__init__(self, parent, ID,
                style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.LC_NO_HEADER)

        self.mainControl = mainControl

        self.InsertColumn(0, "", width=3000)

        self.updatingThreadHolder = Utilities.ThreadHolder()
        self.tocList = [] # List of tuples (char. start in text, headLevel, heading text)
        self.tocListStarts = []   # List of the char. start items of self.tocList
        self.mainControl.getMiscEvent().addListener(self)
        self.sizeVisible = True   # False if this window has a size
                # that it can't be read (one dim. less than 5 pixels)
        self.ignoreOnChange = False

        self.docPagePresenterSink = wxKeyFunctionSink((
                ("loaded current doc page", self.onUpdateNeeded),
                ("changed live text", self.onUpdateNeeded)
#                 ("options changed", self.onUpdateNeeded)
        ))

        self.__sinkApp = wxKeyFunctionSink((
                ("options changed", self.onUpdateNeeded),
        ), wx.GetApp().getMiscEvent(), self)

#         if not self.mainControl.isMainWindowConstructed():
#             # Install event handler to wait for construction
#             self.__sinkMainFrame = wxKeyFunctionSink((
#                     ("constructed main window", self.onConstructedMainWindow),
#             ), self.mainControl.getMiscEvent(), self)
#         else:
#             self.onConstructedMainWindow(None)

        self.__sinkMainFrame = wxKeyFunctionSink((
                ("idle visible", self.onIdleVisible),
        ), self.mainControl.getMiscEvent(), self)

        currPres = self.mainControl.getCurrentDocPagePresenter()
        if currPres is not None:
            self.docPagePresenterSink.setEventSource(currPres.getMiscEvent())
        
        self.lastSelection = (-1, -1)

        self.updateList()

        self.Bind(wx.EVT_WINDOW_DESTROY, self.OnDestroy)
        self.Bind(wx.EVT_LIST_ITEM_SELECTED, self.OnItemSelected, id=self.GetId())
        self.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self.OnItemActivated, id=self.GetId())
        self.Bind(wx.EVT_SIZE, self.OnSize)
        
        self.Bind(wx.EVT_KILL_FOCUS, self.OnKillFocus)
#         self.Bind(wx.EVT_LEFT_UP, self.OnLeftUp)


    def close(self):
        """
        """
        self.updatingThreadHolder.setThread(None)
        self.docPagePresenterSink.disconnect()
        self.__sinkApp.disconnect()


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
        self.__sinkMainFrame.enable(self.isVisibleEffect())

        if self.isVisibleEffect():
            presenter = self.mainControl.getCurrentDocPagePresenter()
            if presenter is not None:
                self.docPagePresenterSink.setEventSource(presenter.getMiscEvent())
            else:
                self.docPagePresenterSink.setEventSource(None)
            self.updateList()
        else:
            self.docPagePresenterSink.disconnect()
            if wx.Window.FindFocus() is self:
                self.mainControl.getMainAreaPanel().SetFocus()


    def OnDestroy(self, evt):
        if not self is evt.GetEventObject():
            evt.Skip()
            return

        self.close()
        evt.Skip()


    def OnSize(self, evt):
        evt.Skip()
        oldVisible = self.isVisibleEffect()
        size = evt.GetSize()
        self.sizeVisible = size.GetHeight() >= 5 and size.GetWidth() >= 5
        
        if oldVisible != self.isVisibleEffect():
            self.handleVisibilityChange()


#     def onConstructedMainWindow(self, evt):
#         """
#         Now we can register idle handler.
#         """
#         self.Bind(wx.EVT_IDLE, self.OnIdle)


    def onIdleVisible(self, evt):
        self.checkSelectionChanged()
        
        
    def checkSelectionChanged(self, callAlways=False):
        if not self.isVisibleEffect():
            return

        presenter = self.mainControl.getCurrentDocPagePresenter()
        if presenter is None:
            return

        subCtrl = presenter.getSubControl("textedit")
        if subCtrl is None:
            return
        
        sel = subCtrl.LineFromPosition(subCtrl.GetCurrentPos())
        
        if sel != self.lastSelection or callAlways:
            self.lastSelection = sel
            self.onSelectionChanged(subCtrl.GetSelectionCharPos())


    def onSelectionChanged(self, sel):
        """
        This is not directly supported by Scintilla, but called by OnIdle().
        """
        if not self.mainControl.getConfig().getboolean("main",
                "docStructure_autofollow"):
            return
            
        idx = bisect.bisect_right(self.tocListStarts, sel[0]) - 1

        self.ignoreOnChange = True
        try:
            self.SelectSingle(idx, scrollVisible=True)
        finally:    
            self.ignoreOnChange = False



    def miscEventHappened(self, miscevt):
        """
        Handle misc events
        """
        if self.sizeVisible and miscevt.getSource() is self.mainControl:
            if "changed current presenter" in miscevt:
                presenter = self.mainControl.getCurrentDocPagePresenter()
                if presenter is not None:
                    self.docPagePresenterSink.setEventSource(presenter.getMiscEvent())
                else:
                    self.docPagePresenterSink.setEventSource(None)

                self.updateList()


    def onUpdateNeeded(self, miscevt):
        self.updateList()


    def updateList(self):
#         if self.mainControl.getConfig().getboolean("main",
#                 "docStructure_autofollow"):
#             self.tocListStarts = []
#             self.SelectSingle(-1)

        presenter = self.mainControl.getCurrentDocPagePresenter()

        if presenter is None:
            self.tocList = []
            self.tocListStarts = []
            self.applyTocList()
            return

#         print "updateList"
        text = presenter.getLiveText()
        docPage = presenter.getDocPage()

        # Asynchronous update
        uth = self.updatingThreadHolder

        depth = presenter.getConfig().getint(
                "main", "docStructure_depth")
        
        t = threading.Thread(None, self.buildTocList,
                args = (text, docPage, depth, uth))
        uth.setThread(t)
        t.setDaemon(True)
        t.start()


    def buildTocList(self, text, docPage, depth, threadstop=DUMBTHREADSTOP):
        """
        Build toc list and put data in self.tocList. Finally call applyTocList()
        to show data.
        """
        try:
            if docPage is None:
                self.tocList = []
                self.tocListStarts = []
                Utilities.callInMainThread(self.applyTocList)
                return

            sleep(0.3)   # Make configurable?
            threadstop.testValidThread()

            depth = min(depth, 15)
            depth = max(depth, 1)

            pageAst = docPage.getLivePageAst(threadstop=threadstop)

            result = []
            for node in pageAst.iterFlatByName("heading"):
                threadstop.testValidThread()
                if node.level > depth:
                    continue

                title = "  " * (node.level - 1) + node.contentNode.getString()
                while title.endswith("\n"):
                    title = title[:-1]
                result.append((node.pos, node.level, title))

            threadstop.testValidThread()

            self.tocList = result
            self.tocListStarts = [r[0] for r in result]

            threadstop.testValidThread()
            Utilities.callInMainThread(self.applyTocList)

        except NotCurrentThreadException:
            return


    def applyTocList(self):
        """
        Show the content of self.tocList in the ListCtrl
        """
        with WindowUpdateLocker(self):
            self.DeleteAllItems()
            for start, headLevel, text in self.tocList:
                self.InsertItem(self.GetItemCount(), text)
#             self.SetColumnWidth(0, wx.LIST_AUTOSIZE)
            self.autosizeColumn(0)
            self.checkSelectionChanged(callAlways=True)


    def OnKillFocus(self, evt):
#         self.SelectSingle(-1)
        evt.Skip()
        
        
#     def OnLeftUp(self, evt):
#         print "OnLeftUp"
#         if self.FindFocus() is self:
#             evt.Skip()
#         # Consume event otherwise


    def displayInSubcontrol(self, start):   # , focusToSubctrl
        """
        Display title in subcontrol of current presenter which
        starts at char position  start  in page text.

        focusToSubctrl -- True iff subcontrol should become focused after
                displaying is done
        """

        presenter = self.mainControl.getCurrentDocPagePresenter()
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
            subCtrl.gotoAnchor(".h%i" % start)

#         if focusToSubctrl:
#             subCtrl.SetFocus()
#             # wx.CallAfter(presenter.SetFocus)


    def OnItemSelected(self, evt):
        if self.ignoreOnChange:
            return

        start = self.tocListStarts[evt.GetIndex()]
        self.displayInSubcontrol(start)



    def OnItemActivated(self, evt):
        presenter = self.mainControl.getCurrentDocPagePresenter()
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

            
        

