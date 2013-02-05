from __future__ import with_statement

## import hotshot
## _prof = hotshot.Profile("hotshot.prf")

import os, sys, traceback, re

import wx
# import wx.xrc as xrc

from .wxHelper import GUI_ID, copyTextToClipboard, getAccelPairFromKeyDown, \
        WindowUpdateLocker

from .MiscEvent import MiscEventSourceMixin, ProxyMiscEvent

from WikiExceptions import *

from . import SystemInfo
from .StringOps import escapeForIni, pathWordAndAnchorToWikiUrl

from .SearchAndReplace import stripSearchString

from .DocPagePresenter import BasicDocPagePresenter

import DocPages


class MainAreaPanel(wx.Notebook, MiscEventSourceMixin):
    """
    The main area panel is embedded in the PersonalWikiFrame and holds and
    controls the doc page presenters.
    """

    def __init__(self, mainControl, parent, id):
        wx.Notebook.__init__(self, parent, id)

#         nb = wx.PreNotebook()
#         self.PostCreate(nb)
        MiscEventSourceMixin.__init__(self)

        self.mainControl = mainControl
        self.mainControl.getMiscEvent().addListener(self)

        self.currentPresenter = None
        self.presenters = []
        self.mruTabIndex = []
        self.tabSwitchByKey = 0  # 2: Key hit, notebook change not processed;
                # 1: Key hit, nb. change processed
                # 0: Processing done
        self.currentPresenterProxyEvent = ProxyMiscEvent(self)

        # Last presenter for which a context menu was shown
        self.lastContextMenuPresenter = None

        self.runningPageChangedEvent = False

#         res = xrc.XmlResource.Get()
#         self.docPagePresContextMenu = res.LoadMenu("MenuDocPagePresenterTabPopup")

        self.tabDragCursor = wx.StockCursor(wx.CURSOR_HAND)
        self.tabDragging = wx.NOT_FOUND

#         wx.EVT_NOTEBOOK_PAGE_CHANGED(self, self.GetId(),
#                 self.OnNotebookPageChanged)
        self.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGED, self.OnNotebookPageChanged)
        wx.EVT_KEY_UP(self, self.OnKeyUp)

        wx.EVT_LEFT_DOWN(self, self.OnLeftDown)
        wx.EVT_LEFT_UP(self, self.OnLeftUp)
        wx.EVT_MIDDLE_DOWN(self, self.OnMiddleDown)

        wx.EVT_MOTION(self, self.OnMotion)

        wx.EVT_CONTEXT_MENU(self, self.OnContextMenu)
        wx.EVT_SET_FOCUS(self, self.OnFocused)
        wx.EVT_KILL_FOCUS(self, self.OnKillFocus)
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
        for p in self.presenters:
            p.close()


    def getCurrentPresenter(self):
        return self.currentPresenter
        
    def getCurrentSubControlName(self):
        if self.currentPresenter is None:
            return None
        
        return self.currentPresenter.getCurrentSubControlName()


    def getCurrentSubControl(self):
        if self.currentPresenter is None:
            return None
        
        return self.currentPresenter.getCurrentSubControl()


    def getCurrentTabTitle(self):
        sel = self.GetSelection()
        if sel == -1:
            return u""

        return self.GetPageText(sel)


    def getPresenters(self):
        """
        Returns list of presenters in the MainAreaPanel (one per tab).
        Most are derived from DocPagePresenter.DocPagePresenter, but all
        are derived from WindowLayout.LayeredControlPresenter.
        """
        return self.presenters
        
    def getOpenWikiWordsSubCtrlsAndActiveNo(self):
        """
        Returns tuple (wikiwords, subCtrls, activeNo) where wikiwords is a list of
        the open wiki words, subCtrls is a corresponding list of names of the
        active subcontrol in the according presenter ("textedit" or "preview"
        normally) and activeNo is the index into wikiwords
        for the corresponding active tab or -1 if active tab doesn't show
        a wiki word or no wiki loaded
        """
        if not self.mainControl.isWikiLoaded():
            return None, -1, None

        wikiWords = []
        subCtrls = []
        activeNo = 0
        for pres in self.getPresenters():
            if isinstance(pres, BasicDocPagePresenter):
                docPage = pres.getDocPage()
                if isinstance(docPage, (DocPages.AliasWikiPage,
                        DocPages.WikiPage)):
                    if pres is self.getCurrentPresenter():
                        activeNo = len(wikiWords)

                    wikiWords.append(
                            docPage.getNonAliasPage().getWikiWord())
                    subCtrls.append(pres.getCurrentSubControlName())

        return wikiWords, subCtrls, activeNo


    def getDocPagePresenters(self):
        """
        Return a list of the real document page presenters in the presenter list.
        """
        return [pres for pres in self.getPresenters()
                if isinstance(pres, BasicDocPagePresenter)]


    def getIndexForPresenter(self, presenter):
        for i, p in enumerate(self.presenters):
            if p is presenter:
                return i
        
        return -1


    def updateConfig(self):
        """
        Update configuration info about open tabs
        """
        config = self.mainControl.getConfig()

        openWikiWords, subCtrls, activeNo = \
                self.getOpenWikiWordsSubCtrlsAndActiveNo()

        if openWikiWords is None:
            return

        if len(openWikiWords) < 2:
            config.set("main", "further_wiki_words", u"")
        else:
            fwws = u";".join([escapeForIni(w, u" ;") for w in openWikiWords[1:]])
            config.set("main", "further_wiki_words", fwws)

        if len(openWikiWords) > 0:
            config.set("main", "last_wiki_word", openWikiWords[0])

            ltsc = u";".join([escapeForIni(w, u" ;") for w in subCtrls])
            config.set("main", "wiki_lastTabsSubCtrls", ltsc)

            config.set("main", "wiki_lastActiveTabNo", activeNo)


    if SystemInfo.isLinux():
        # TODO What about WikidPadHooks?
        def prepareCurrentPresenter(self, currentPresenter):
            """
            Mainly called by OnNotebookPageChanged to inform presenters
            about change
            """
            if not (self.currentPresenter is currentPresenter):
                self.currentPresenter = currentPresenter
                for p in self.presenters:
                    p.setLayerVisible(p is currentPresenter)

                currentPresenter.SetFocus()
                proxyEvent = self.getCurrentPresenterProxyEvent()
                proxyEvent.setWatchedEvents(
                        (self.currentPresenter.getMiscEvent(),))
                self.mainControl.refreshPageStatus()

                # Only difference to non-Linux variant. To workaround
                # funny behavior with left/right arrows with many tabs
                wx.CallAfter(self.fireMiscEventKeys,
                        ("changed current presenter",))
    else:
        # TODO What about WikidPadHooks?
        def prepareCurrentPresenter(self, currentPresenter):
            """
            Mainly called by OnNotebookPageChanged to inform presenters
            about change
            """
            if not (self.currentPresenter is currentPresenter):
                self.currentPresenter = currentPresenter
                for p in self.presenters:
                    p.setLayerVisible(p is currentPresenter)
                proxyEvent = self.getCurrentPresenterProxyEvent()
                proxyEvent.setWatchedEvents(
                        (self.currentPresenter.getMiscEvent(),))
                self.mainControl.refreshPageStatus()
                self.fireMiscEventKeys(("changed current presenter",))


    def showPresenter(self, currentPresenter):
        """
        Sets current presenter by changing the active tab in the
        main area notebook which in turn calls prepareCurrentPresenter()
        """
        i = self.getIndexForPresenter(currentPresenter)
        if i > -1:
            self.SetSelection(i)


    def getCurrentPresenterProxyEvent(self):
        """
        This ProxyMiscEvent resends any messsages from the currently
        active DocPagePresenter
        """
        return self.currentPresenterProxyEvent


    def appendPresenterTab(self, presenter):
        self._mruTabIndexAppend(len(self.presenters))
        self.presenters.append(presenter)
        self.AddPage(presenter, "    ")
        presenter.getMiscEvent().addListener(self)

        if SystemInfo.isLinux():
            presenter.Show(True)

        if self.getCurrentPresenter() is None:
            self.prepareCurrentPresenter(presenter)
            
        self.updateConfig()

        return presenter


    def closePresenterTab(self, presenter):
        # If the close command came from a popup menu then directly deleting the
        # page while the menu wasn't closed yet leads to an error or
        # a crash depending on OS (thanks to Ross)
        wx.CallAfter(self.closePresenterTabDirectly, presenter)


    def closePresenterTabDirectly(self, presenter):
        if isinstance(presenter, BasicDocPagePresenter) and \
                len(self.getDocPagePresenters()) < 2:
            # At least one tab must stay
            return False

        idx = self.getIndexForPresenter(presenter)
        if idx == -1:
            return False
            
        newIdx = -1
        if idx == self.GetSelection():
            switchMru = self.mainControl.getConfig().getboolean("main",
                    "mainTabs_switchMruOrder", True)
    
            if switchMru:
                # We are closing current active presenter and use MRU order
                # to switch -> select previous presenter in MRU order
                newIdx = self._mruTabIndexGetNext(idx)
                if newIdx == idx:
                    # Don't switch at all
                    newIdx = -1
                else:
                    self.SetSelection(newIdx)

#                 elif newIdx > idx:
#                     # Adapt for after deletion of idx
#                     newIdx -= 1

        # Prepare presenter for closing
        presenter.close()

        # Actual deletion
        del self.presenters[idx]
        self._mruTabIndexDelete(idx)

        self.updateConfig()

        self.DeletePage(idx)

        return True


    def detachPresenterTab(self, presenter):
        """
        Removes the presenter from the tabs, but does not close or destroy it.
        """
        if isinstance(presenter, BasicDocPagePresenter) and \
                len(self.getDocPagePresenters()) < 2:
            # At least one tab must stay
            return

        idx = self.getIndexForPresenter(presenter)
        if idx == -1:
            return
            
        # Actual remove
        del self.presenters[idx]
        self._mruTabIndexDelete(idx)
        self.RemovePage(idx)
        self.updateConfig()


    def _closeAllButCurrentTab(self):
        """
        Close all tabs except the current one.
        """
        current = self.currentPresenter
        if current is None:
            return

        if not isinstance(current, BasicDocPagePresenter):
            # Current presenter is not a doc page one, so take first doc page
            # presenter instead
            current = self.getDocPagePresenters()[0]

        # Loop over copy of the presenter list
        for presenter in self.presenters[:]:
#             if isinstance(presenter, BasicDocPagePresenter) and \
#                     len(self.getDocPagePresenters()) < 2:
#                 # At least one DPP tab must stay
#                 return
            if presenter is current:
                continue

            self.closePresenterTab(presenter)


    def switchDocPagePresenterTabEditorPreview(self, presenter):
        """
        Switch between editor and preview in the given doc page presenter
        (if presenter is owned by the MainAreaPanel).
        """
        if not presenter in self.presenters:
            return
            
        if not isinstance(presenter, BasicDocPagePresenter):
            return

        scName = presenter.getCurrentSubControlName()
        if scName != "textedit":
            if self.mainControl.getConfig().getboolean("main",
                    "editor_sync_byPreviewSelection", False) and \
                    presenter.getCurrentSubControlName() == "preview":
                selText = presenter.getCurrentSubControl().GetSelectedText()

                presenter.switchSubControl("textedit", gainFocus=True)

                if selText:
                    editCtrl = presenter.getSubControl("textedit")
                    editCtrl.incSearchCharStartPos = 0
                    editCtrl.searchStr = re.escape(stripSearchString(selText))
                    editCtrl.executeIncrementalSearch()
            else:
                presenter.switchSubControl("textedit", gainFocus=True)
        else:
            presenter.switchSubControl("preview", gainFocus=True)


#     # Problem with mouse capture on Linux  (MacOS?)
#     if SystemInfo.isWindows():
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


#     def OnKeyDown(self, evt):
#         key = evt.GetKeyCode()
# 
#         self.lastKeyPressed = time()
#         accP = getAccelPairFromKeyDown(evt)
#         matchesAccelPair = self.mainControl.keyBindings.\
#                 matchesAccelPair
#         
#         if accP == (wx.ACCEL_CTRL, wx.WXK_TAB):
#             print "--Forward"
#             return
#         
#         evt.Skip()


    if SystemInfo.isLinux():
        def SetSelection(self, i):
            """
            SetSelection is overwritten on Linux because Linux/GTK sets
            the focus automatically to the content of the selected
            notebook tab which is not desired.
            """
            foc = wx.Window.FindFocus()
            wx.Notebook.SetSelection(self, i)
            if foc is not None:
                foc.SetFocus()


#     if SystemInfo.isLinux():
#         def OnNotebookPageChanged(self, evt):
#             try:
#                 # Flag the event to ignore and resend it.
#                 # It is then processed by wx.Notebook code
#                 # where the focus is set to the notebook itself
#     
#                 presenter = self.presenters[evt.GetSelection()]
#                 self.prepareCurrentPresenter(presenter)
#     
#                 # Now we can set the focus back to the presenter
#                 # which in turn sets it to the active subcontrol
# 
#                 if self.tabSwitchByKey < 2:
#                     self._mruTabIndexPushToTop(evt.GetSelection())
#                     presenter.SetFocus()
#             except (IOError, OSError, DbAccessError), e:
#                 self.runningPageChangedEvent = False
#                 self.mainControl.lostAccess(e)
#                 raise #???
# 
#     else:


    def OnNotebookPageChanged(self, evt):
        # Tricky hack to set focus to the notebook page
        if self.runningPageChangedEvent:
            evt.Skip()
            self.runningPageChangedEvent = True
            return

        try:
            # Flag the event to ignore and resend it.
            # It is then processed by wx.Notebook code
            # where the focus is set to the notebook itself

            presenter = self.presenters[evt.GetSelection()]
            self.prepareCurrentPresenter(presenter)

            self.runningPageChangedEvent = True
            try:
                self.ProcessEvent(evt.Clone())
            finally:
                self.runningPageChangedEvent = False

            # Now we can set the focus back to the presenter
            # which in turn sets it to the active subcontrol
            
            if self.tabSwitchByKey < 2:
                self._mruTabIndexPushToTop(evt.GetSelection())
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

        # Show menu
        ctxMenu = self.presenters[tab].getTabContextMenu()
        if ctxMenu is not None:
            self.lastContextMenuPresenter = self.presenters[tab]
#             sc = self.lastContextMenuPresenter
            self.PopupMenu(ctxMenu)


    if SystemInfo.isLinux():
        # OnFocused() is not always called so a direct overwrite is necessary
        def SetFocus(self):
            if self.tabSwitchByKey == 0:
                p = self.GetCurrentPage()
                if p is not None:
                    p.SetFocus()
                    return

            wx.Notebook.SetFocus(self)


    def OnFocused(self, evt):
        if self.tabSwitchByKey == 0:
            p = self.GetCurrentPage()
            if p is not None:
                p.SetFocus()


    def OnKillFocus(self, evt):
        evt.Skip()

        if self.tabSwitchByKey == 0:
            return

        self.tabSwitchByKey = 0
        self._mruTabIndexPushToTop(self.GetSelection())



    def OnCloseThisTab(self, evt):
        if self.lastContextMenuPresenter is not None:
            self.closePresenterTab(self.lastContextMenuPresenter)

    def OnCloseCurrentTab(self, evt):
        self.closePresenterTab(self.getCurrentPresenter())


    # Handle self.mruTabIndex
    def _mruTabIndexPushToTop(self, idx):
        """
        Push idx to top in mru list.
        """
        if idx == -1:
            return

        try:
            self.mruTabIndex.remove(idx)
        except ValueError:
            pass
        
        self.mruTabIndex.insert(0, idx)

    def _mruTabIndexAppend(self, idx):
        self.mruTabIndex = [(i if i < idx else i + 1) for i in self.mruTabIndex]
        self.mruTabIndex.append(idx)

    def _mruTabIndexDelete(self, idx):
        """
        Delete idx. Indices > idx must be decremented by one.
        """
        self.mruTabIndex = [(i if i < idx else i - 1) for i in self.mruTabIndex
                if i != idx]

    def _mruTabIndexGetNext(self, idx):
        """
        Get next index after idx
        """
        try:
            return self.mruTabIndex[self.mruTabIndex.index(idx) + 1]
        except (ValueError, IndexError):
            return self.mruTabIndex[0]

    def _mruTabIndexGetPrevious(self, idx):
        """
        Get next index after idx
        """
        try:
            return self.mruTabIndex[self.mruTabIndex.index(idx) - 1]
        except ValueError:
            return self.mruTabIndex[-1]


    def OnGoTab(self, evt):
        pageCount = self.GetPageCount()
        if pageCount < 2:
            return
            
        switchMru = self.mainControl.getConfig().getboolean("main",
                "mainTabs_switchMruOrder", True)

        if evt.GetId() == GUI_ID.CMD_GO_NEXT_TAB:
            if switchMru:
                newIdx = self._mruTabIndexGetNext(self.GetSelection())
                self.tabSwitchByKey = 2
            else:
                newIdx = self.GetSelection() + 1
                if newIdx >= pageCount:
                    newIdx = 0
        elif evt.GetId() == GUI_ID.CMD_GO_PREVIOUS_TAB:
            if switchMru:
                newIdx = self._mruTabIndexGetPrevious(self.GetSelection())
                self.tabSwitchByKey = 2
            else:
                newIdx = self.GetSelection() - 1
                if newIdx < 0:
                    newIdx = pageCount - 1

        self.SetSelection(newIdx)
        if self.tabSwitchByKey > 0:
            self.tabSwitchByKey = 1


    if SystemInfo.isLinux():
        def OnKeyUp(self, evt):
            if self.tabSwitchByKey == 0:
                evt.Skip()
                return

            # For Linux the test must be done this way.
            # Meta is always reported as pressed (at least for PC), so ignore it
            mstate = wx.GetMouseState()
            if mstate.ControlDown() or mstate.ShiftDown() or mstate.AltDown() or \
                    mstate.CmdDown():
                # Some modifier keys are pressed yet
                evt.Skip()
                return

            self.tabSwitchByKey = 0
            self._mruTabIndexPushToTop(self.GetSelection())
            self.presenters[self.GetSelection()].SetFocus()
    else:
        def OnKeyUp(self, evt):
            if self.tabSwitchByKey == 0:
                evt.Skip()
                return

            if evt.GetModifiers() & \
                    (wx.MOD_ALT | wx.MOD_CONTROL | wx.MOD_ALTGR | wx.MOD_META | wx.MOD_CMD):
                # Some modifier keys are pressed yet
                evt.Skip()
                return

            self.tabSwitchByKey = 0
            self._mruTabIndexPushToTop(self.GetSelection())
            self.presenters[self.GetSelection()].SetFocus()


    def OnCmdSwitchThisEditorPreview(self, evt):
        """
        Switch between editor and preview in the presenter for which
        context menu was used.
        """
        if self.lastContextMenuPresenter is not None:
            self.switchDocPagePresenterTabEditorPreview(self.lastContextMenuPresenter)


    def OnCmdClipboardCopyUrlToThisWikiWord(self, evt):
        if not isinstance(self.lastContextMenuPresenter, BasicDocPagePresenter):
            return

        wikiWord = self.lastContextMenuPresenter.getWikiWord()
        if wikiWord is None:
            wx.MessageBox(
                    _(u"This can only be done for the page of a wiki word"),
                    _(u'Not a wiki page'), wx.OK, self)
            return

        path = self.mainControl.getWikiDocument().getWikiConfigPath()
        copyTextToClipboard(pathWordAndAnchorToWikiUrl(path, wikiWord, None))


    def OnLeftDown(self, evt):
        self.tabDragging = self.HitTest(evt.GetPosition())[0]  # tab != wx.NOT_FOUND
#         if self.tabDragging:
#             self.CaptureMouseIfOk()
        
        evt.Skip()


    def OnLeftUp(self, evt):
        if self.tabDragging != wx.NOT_FOUND:
#             self.ReleaseMouseIfOk()
            oldTab = self.tabDragging
            self.tabDragging = wx.NOT_FOUND
            self.SetCursor(wx.NullCursor)
            tab = self.HitTest(evt.GetPosition())[0]
            if not self.runningPageChangedEvent and tab != wx.NOT_FOUND and \
                    tab != oldTab:

                # oldTab = self.GetSelection()
                title = self.GetPageText(oldTab)
                
                # window and presenter should be identical, but to be sure
                window = self.GetPage(oldTab)
                presenter = self.presenters[oldTab]
                
                self.Unbind(wx.EVT_NOTEBOOK_PAGE_CHANGED)
                self.Freeze()
                try:
                    self.RemovePage(oldTab)
                    del self.presenters[oldTab]
                    self._mruTabIndexDelete(oldTab)
        
                    self.presenters.insert(tab, presenter)
                    self._mruTabIndexAppend(tab)
                    self._mruTabIndexPushToTop(tab)
                    self.InsertPage(tab, window, title, select=True)
                finally:
                    self.Thaw()
                    self.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGED,
                            self.OnNotebookPageChanged)
        evt.Skip()


    def OnMiddleDown(self, evt):
        tab = self.HitTest(evt.GetPosition())[0]
        if tab == wx.NOT_FOUND:
            return

        pres = self.presenters[tab]
        mc = self.mainControl

        paramDict = {"presenter": pres, "main control": mc}
        mc.getUserActionCoord().reactOnUserEvent(
                u"mouse/middleclick/pagetab", paramDict)


    def OnMotion(self, evt):
#        if evt.Dragging() and evt.LeftIsDown():
        if self.tabDragging != wx.NOT_FOUND:
            # Just to be sure
            if not evt.Dragging():
#                 self.ReleaseMouseIfOk()
                self.tabDragging = wx.NOT_FOUND
                self.SetCursor(wx.NullCursor)
                evt.Skip()
                return

            tab = self.HitTest(evt.GetPosition())[0]
            if tab != wx.NOT_FOUND and tab != self.tabDragging:
                self.SetCursor(self.tabDragCursor)
            else:
                self.SetCursor(wx.NullCursor)


    def miscEventHappened(self, miscevt):
        if miscevt.getSource() in self.presenters:
            if miscevt.has_key("changed presenter title"):
                presenter = miscevt.getSource()
                idx = self.getIndexForPresenter(presenter)
                if idx > -1:
#                     self.SetPageText(idx,
#                             presenter.getLongTitle())
                    self.SetPageText(idx, miscevt.get("title"))

                    if presenter is self.getCurrentPresenter():
                        self.mainControl.refreshPageStatus()

        elif miscevt.getSource() is self.mainControl:
            if miscevt.has_key("closed current wiki"):
                self._closeAllButCurrentTab()



