## import hotshot
## _prof = hotshot.Profile("hotshot.prf")

import os, sys, traceback, sets, string, re

import wx
import wx.xrc as xrc

from wxHelper import GUI_ID
from MiscEvent import MiscEventSourceMixin, ResendingMiscEvent

from WikiExceptions import *

import Configuration



# etEVT_AFTER_FOCUS = wx.NewEventType()
# EVT_AFTER_FOCUS = wx.PyEventBinder(etEVT_AFTER_FOCUS, 0)
# 
# class AfterFocusEvent(wx.PyCommandEvent):
#     """
#     This wx Event is fired when style and folding calculations are finished.
#     It is needed to savely transfer data from the style thread to the main thread.
#     """
#     def __init__(self, toFocus):
#         wx.PyCommandEvent.__init__(self, etEVT_AFTER_FOCUS, -1)
#         self.toFocus = toFocus



class MainAreaPanel(wx.Notebook, MiscEventSourceMixin):
    """
    The main area panel is embedded in the PersonalWikiFrame and holds and
    controls the doc page presenters.
    """

    def __init__(self, parent, mainControl, id=-1):
        wx.Notebook.__init__(self, parent, id)
        MiscEventSourceMixin.__init__(self)

        self.mainControl = mainControl
        self.mainControl.getMiscEvent().addListener(self)

        self.currentDocPagePresenter = None
        self.docPagePresenters = []
#         self.currentDocPagePresenterRMEvent = ResendingMiscEvent(self)

        res = xrc.XmlResource.Get()
        self.contextMenu = res.LoadMenu("MenuDocPagePresenterTabPopup")


        # Last presenter for which a context menu was shown
        self.lastContextMenuPresenter = None

        wx.EVT_NOTEBOOK_PAGE_CHANGED(self, self.GetId(),
                self.OnNotebookPageChanged)
        wx.EVT_CONTEXT_MENU(self, self.OnContextMenu)
        wx.EVT_SET_FOCUS(self, self.OnFocused)
#         EVT_AFTER_FOCUS(self, self.OnAfterFocus)

        wx.EVT_MENU(self, GUI_ID.CMD_CLOSE_THIS_TAB, self.OnCloseThisTab)
        wx.EVT_MENU(self, GUI_ID.CMD_CLOSE_CURRENT_TAB, self.OnCloseCurrentTab)


    def close(self):
        for p in self.docPagePresenters:
            p.close()


    def getCurrentDocPagePresenter(self):
        return self.currentDocPagePresenter


    def getDocPagePresenters(self):
        return self.docPagePresenters

    def getIndexForDocPagePresenter(self, presenter):
        for i, p in enumerate(self.docPagePresenters):
            if p is presenter:
                return i
        
        return -1


    # TODO What about WikidPadHooks?
    def setCurrentDocPagePresenter(self, currentPresenter):
        """
        Mainly called by OnNotebookPageChanged to inform presenters
        about change
        """
        if not (self.currentDocPagePresenter is currentPresenter):
            self.currentDocPagePresenter = currentPresenter
            for p in self.docPagePresenters:
                p.setVisible(p is currentPresenter)
            rMEvent = self.mainControl.getCurrentDocPagePresenterRMEvent()
            rMEvent.setWatchedEvents((self.currentDocPagePresenter.getMiscEvent(),))
            self.mainControl.refreshPageStatus()
            self.fireMiscEventKeys(("changed current docpage presenter",))


    def showDocPagePresenter(self, currentPresenter):
        """
        Sets current presenter by changing the active tab in the
        main area notebook which in turn calls setCurrentDocPagePresenter()
        """
        i = self.getIndexForDocPagePresenter(currentPresenter)
        if i > -1:
            self.SetSelection(i)


#     def getCurrentDocPagePresenterRMEvent(self):
#         """
#         This ResendingMiscEvent resends any messsages from the currently
#         active DocPagePresenter
#         """
#         return self.currentDocPagePresenterRMEvent


    def appendDocPagePresenterTab(self, presenter):
        self.docPagePresenters.append(presenter)
        self.AddPage(presenter, "    ")
        presenter.getMiscEvent().addListener(self)

        presenter.switchSubControl("textedit")

        if Configuration.isLinux():
            presenter.Show(True)

        if self.getCurrentDocPagePresenter() is None:
            self.setCurrentDocPagePresenter(presenter)
            
        return presenter


    def closeDocPagePresenterTab(self, presenter):
        if len(self.docPagePresenters) < 2:
            # At least one tab must stay
            return

        idx = self.getIndexForDocPagePresenter(presenter)
        if idx == -1:
            return
            
        # Prepare presenter for closing
        presenter.close()
        
        # Actual deletion
        del self.docPagePresenters[idx]
        self.DeletePage(idx)


    def closeAllButCurrentTab(self):
        """
        Close all tabs except the current one.
        """
        current = self.currentDocPagePresenter
        
        # Loop over copy of the presenter list
        for presenter in self.docPagePresenters[:]:
            if len(self.docPagePresenters) < 2:
                # At least one tab must stay
                return
            
            if presenter is current:
                continue
            
            self.closeDocPagePresenterTab(presenter)



    def OnNotebookPageChanged(self, evt):
        try:
            presenter = self.docPagePresenters[evt.GetSelection()]
#             presenter = self.GetCurrentPage()
#             print "OnNotebookPageChanged2", repr(presenter), repr(evt.GetSelection()), repr(presenter.GetChildren())
            self.setCurrentDocPagePresenter(presenter)
#             self.GetPage(evt.GetSelection()).SetFocus()
            presenter.SetFocus()
        except (IOError, OSError, DbAccessError), e:
            self.mainControl.lostAccess(e)
            raise #???
        
        evt.Skip()


    def OnContextMenu(self, evt):
        pos = self.ScreenToClient(wx.GetMousePosition())
        tab = self.HitTest(pos)[0]
        if tab == wx.NOT_FOUND:
            return
        
        self.lastContextMenuPresenter = self.docPagePresenters[tab]
        # Show menu
        self.PopupMenu(self.contextMenu)



    def OnFocused(self, evt):
        p = self.GetCurrentPage()
        if p is not None:
#             self.AddPendingEvent(AfterFocusEvent(p))
            p.SetFocus()


#     def OnAfterFocus(self, evt):
#         evt.toFocus.SetFocus()


    def OnCloseThisTab(self, evt):
        if self.lastContextMenuPresenter is not None:
            self.closeDocPagePresenterTab(self.lastContextMenuPresenter)

    def OnCloseCurrentTab(self, evt):
        self.closeDocPagePresenterTab(self.getCurrentDocPagePresenter())

    def miscEventHappened(self, miscevt):
        if miscevt.getSource() in self.docPagePresenters:
            if miscevt.has_key("changed presenter title"):
                presenter = miscevt.getSource()
                idx = self.getIndexForDocPagePresenter(presenter)
                if idx > -1:
                    self.SetPageText(idx,
                            presenter.getLongTitle())
                            
#                     # TODO (Re)move this
# #                     if presenter is self.getCurrentDocPagePresenter():
#                     title = (u"Wiki: %s - %s" %
#                             (self.mainControl.getWikiConfigPath(),
#                             presenter.getShortTitle()))
# #                     if self.mainControl.GetTitle() != title:
#                     self.mainControl.SetTitle(title)

                    if presenter is self.getCurrentDocPagePresenter():
                        self.mainControl.refreshPageStatus()

        elif miscevt.getSource() is self.mainControl:
            if miscevt.has_key("closed current wiki"):
                self.closeAllButCurrentTab()


