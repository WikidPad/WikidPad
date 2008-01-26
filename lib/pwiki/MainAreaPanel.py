## import hotshot
## _prof = hotshot.Profile("hotshot.prf")

import os, sys, traceback, sets, string, re

import wx
import wx.xrc as xrc

from wxHelper import GUI_ID, copyTextToClipboard
from MiscEvent import MiscEventSourceMixin, ProxyMiscEvent

from WikiExceptions import *

import Configuration
from StringOps import escapeForIni, pathWordAndAnchorToWikiUrl

import DocPages


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
        self.currentDocPagePresenterProxyEvent = ProxyMiscEvent(self)

        res = xrc.XmlResource.Get()
        self.contextMenu = res.LoadMenu("MenuDocPagePresenterTabPopup")
        
        self.tabDragCursor = wx.StockCursor(wx.CURSOR_HAND)
        self.tabDragging = False


        # Last presenter for which a context menu was shown
        self.lastContextMenuPresenter = None

        self.runningPageChangedEvent = False

#         wx.EVT_NOTEBOOK_PAGE_CHANGED(self, self.GetId(),
#                 self.OnNotebookPageChanged)
        self.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGED, self.OnNotebookPageChanged)
        wx.EVT_LEFT_DOWN(self, self.OnLeftDown)
        wx.EVT_LEFT_UP(self, self.OnLeftUp)
        wx.EVT_MOTION(self, self.OnMotion)
        
        wx.EVT_CONTEXT_MENU(self, self.OnContextMenu)
        wx.EVT_SET_FOCUS(self, self.OnFocused)
#         EVT_AFTER_FOCUS(self, self.OnAfterFocus)

        wx.EVT_MENU(self, GUI_ID.CMD_CLOSE_THIS_TAB, self.OnCloseThisTab)
        wx.EVT_MENU(self, GUI_ID.CMD_CLOSE_CURRENT_TAB, self.OnCloseCurrentTab)
        wx.EVT_MENU(self, GUI_ID.CMD_THIS_TAB_SHOW_SWITCH_EDITOR_PREVIEW,
                self.OnCmdSwitchThisEditorPreview)
        wx.EVT_MENU(self, GUI_ID.CMD_GO_NEXT_TAB, self.OnGoTab)
        wx.EVT_MENU(self, GUI_ID.CMD_GO_PREVIOUS_TAB, self.OnGoTab)
        wx.EVT_MENU(self, GUI_ID.CMD_CLIPBOARD_COPY_URL_TO_THIS_WIKIWORD,
                self.OnCmdClipboardCopyUrlToThisWikiWord)


    def close(self):
        for p in self.docPagePresenters:
            p.close()


    def getCurrentDocPagePresenter(self):
        return self.currentDocPagePresenter
        
    def getCurrentTabTitle(self):
        sel = self.GetSelection()
        if sel == -1:
            return u""
        
        return self.GetPageText(sel)


    def getDocPagePresenters(self):
        return self.docPagePresenters
        
    def getOpenWikiWords(self):
        if not self.mainControl.isWikiLoaded():
            return None

        result = []
        for pres in self.getDocPagePresenters():
            docPage = pres.getDocPage()
            if isinstance(docPage, (DocPages.AliasWikiPage,
                    DocPages.WikiPage)):
                result.append(
                        docPage.getNonAliasPage().getWikiWord())
                        
        return result


    def getIndexForDocPagePresenter(self, presenter):
        for i, p in enumerate(self.docPagePresenters):
            if p is presenter:
                return i
        
        return -1


    def updateConfig(self):
        """
        Update configuration info about open tabs
        """
        
        openWikiWords = self.getOpenWikiWords()
        
        if openWikiWords is None:
            return
        
        if len(openWikiWords) < 2:
            self.mainControl.getConfig().set("main", "further_wiki_words", u"")
        else:
            fwws = u";".join([escapeForIni(w, u" ;")
                    for w in openWikiWords[1:]])
            self.mainControl.getConfig().set("main", "further_wiki_words", fwws)

        if len(openWikiWords) > 0:
            self.mainControl.getConfig().set("main", "last_wiki_word",
                    openWikiWords[0])


    # TODO What about WikidPadHooks?
    def setCurrentDocPagePresenter(self, currentPresenter):
        """
        Mainly called by OnNotebookPageChanged to inform presenters
        about change
        """
        if not (self.currentDocPagePresenter is currentPresenter):
            self.currentDocPagePresenter = currentPresenter
            for p in self.docPagePresenters:
                p.setLayerVisible(p is currentPresenter)
#             rMEvent = self.mainControl.getCurrentDocPagePresenterProxyEvent()
            proxyEvent = self.getCurrentDocPagePresenterProxyEvent()
            proxyEvent.setWatchedEvents(
                    (self.currentDocPagePresenter.getMiscEvent(),))
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


    def getCurrentDocPagePresenterProxyEvent(self):
        """
        This ProxyMiscEvent resends any messsages from the currently
        active DocPagePresenter
        """
        return self.currentDocPagePresenterProxyEvent


    def appendDocPagePresenterTab(self, presenter):
        self.docPagePresenters.append(presenter)
        self.AddPage(presenter, "    ")
        presenter.getMiscEvent().addListener(self)

        presenter.switchSubControl("textedit")

        if Configuration.isLinux():
            presenter.Show(True)

        if self.getCurrentDocPagePresenter() is None:
            self.setCurrentDocPagePresenter(presenter)
            
        self.updateConfig()

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
        self.updateConfig()


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


    def switchDocPagePresenterTabEditorPreview(self, presenter):
        """
        Switch between editor and preview in the given presenter
        (if presenter is owned by the MainAreaPanel).
        """
        if not presenter in self.docPagePresenters:
            return
        
        scName = presenter.getCurrentSubControlName()
        if scName != "textedit":
            presenter.switchSubControl("textedit", gainFocus=True)
        else:
            presenter.switchSubControl("preview", gainFocus=True)


#     # Problem with mouse capture on Linux  (MacOS?)
#     if Configuration.isWindows():
#         def CaptureMouseIfOk(self):
#             return self.CaptureMouse()
#         
#         def ReleaseMouseIfOk(self):
#             return self.ReleaseMouse()
#     else:
#         def CaptureMouseIfOk(self):
#             pass
#         
#         def ReleaseMouseIfOk(self):
#             pass


    def OnNotebookPageChanged(self, evt):
        # Tricky hack to set focus to the notebook page
        if self.runningPageChangedEvent:
            evt.Skip()
            self.runningPageChangedEvent = False
            return

        try:
            # Flag the event to ignore and resend it.
            # It is then processed by wx.Notebook code
            # where the focus is set to the notebook itself
            self.runningPageChangedEvent = True

            presenter = self.docPagePresenters[evt.GetSelection()]
            self.setCurrentDocPagePresenter(presenter)

            self.ProcessEvent(evt)

            # Now we can set the focus back to the presenter
            # which in turn sets it to the active subcontrol
            presenter.SetFocus()
        except (IOError, OSError, DbAccessError), e:
            self.runningPageChangedEvent = False
            self.mainControl.lostAccess(e)
            raise #???


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
            p.SetFocus()


    def OnCloseThisTab(self, evt):
        if self.lastContextMenuPresenter is not None:
            self.closeDocPagePresenterTab(self.lastContextMenuPresenter)

    def OnCloseCurrentTab(self, evt):
        self.closeDocPagePresenterTab(self.getCurrentDocPagePresenter())


    def OnGoTab(self, evt):
        pageCount = self.GetPageCount()
        if pageCount < 2:
            return

        if evt.GetId() == GUI_ID.CMD_GO_NEXT_TAB:
            newIdx = self.GetSelection() + 1
            if newIdx >= pageCount:
                newIdx = 0
        elif evt.GetId() == GUI_ID.CMD_GO_PREVIOUS_TAB:
            newIdx = self.GetSelection() - 1
            if newIdx < 0:
                newIdx = pageCount - 1
        
        self.SetSelection(newIdx)


    def OnCmdSwitchThisEditorPreview(self, evt):
        """
        Switch between editor and preview in the presenter for which
        context menu was used.
        """
        if self.lastContextMenuPresenter is not None:
            self.switchDocPagePresenterTabEditorPreview(self.lastContextMenuPresenter)


    def OnCmdClipboardCopyUrlToThisWikiWord(self, evt):
        wikiWord = self.lastContextMenuPresenter.getWikiWord()
        if wikiWord is None:
            wx.MessageBox(
                    _(u"This can only be done for the page of a wiki word"),
                    _(u'Not a wiki page'), wx.OK, self)
            return

        path = self.mainControl.getWikiDocument().getWikiConfigPath()
        copyTextToClipboard(pathWordAndAnchorToWikiUrl(path, wikiWord, None))


    def OnLeftDown(self, evt):
        tab = self.HitTest(evt.GetPosition())[0]
        self.tabDragging = tab != wx.NOT_FOUND
#         if self.tabDragging:
#             self.CaptureMouseIfOk()
        
        evt.Skip()


    def OnLeftUp(self, evt):
        if self.tabDragging:
#             self.ReleaseMouseIfOk()
            self.tabDragging = False
            self.SetCursor(wx.NullCursor)
            tab = self.HitTest(evt.GetPosition())[0]
            if not self.runningPageChangedEvent and tab != wx.NOT_FOUND and \
                    tab != self.GetSelection():

                oldTab = self.GetSelection()
                title = self.GetPageText(oldTab)
                
                # window and presenter should be identical, but to be sure
                window = self.GetPage(oldTab)
                presenter = self.docPagePresenters[oldTab]
                
                self.Unbind(wx.EVT_NOTEBOOK_PAGE_CHANGED)
                self.Freeze()
                try:
                    self.RemovePage(oldTab)
                    del self.docPagePresenters[oldTab]
        
                    self.docPagePresenters.insert(tab, presenter)
                    self.InsertPage(tab, window, title, select=True)
                finally:
                    self.Thaw()
                    self.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGED,
                            self.OnNotebookPageChanged)
        evt.Skip()


    def OnMotion(self, evt):
#        if evt.Dragging() and evt.LeftIsDown():
        if self.tabDragging:
            # Just to be sure
            if not evt.Dragging():
#                 self.ReleaseMouseIfOk()
                self.tabDragging = False
                self.SetCursor(wx.NullCursor)
                evt.Skip()
                return

            tab = self.HitTest(evt.GetPosition())[0]
            if tab != wx.NOT_FOUND and tab != self.GetSelection():
                self.SetCursor(self.tabDragCursor)
            else:
                self.SetCursor(wx.NullCursor)


    def miscEventHappened(self, miscevt):
        if miscevt.getSource() in self.docPagePresenters:
            if miscevt.has_key("changed presenter title"):
                presenter = miscevt.getSource()
                idx = self.getIndexForDocPagePresenter(presenter)
                if idx > -1:
                    self.SetPageText(idx,
                            presenter.getLongTitle())

                    if presenter is self.getCurrentDocPagePresenter():
                        self.mainControl.refreshPageStatus()

        elif miscevt.getSource() is self.mainControl:
            if miscevt.has_key("closed current wiki"):
                self.closeAllButCurrentTab()



