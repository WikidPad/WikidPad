from __future__ import with_statement

## import hotshot
## _prof = hotshot.Profile("hotshot.prf")

import os, sys, traceback, re

import wx
import aui
# import wx.xrc as xrc

from .wxHelper import GUI_ID, copyTextToClipboard, getAccelPairFromKeyDown, \
        WindowUpdateLocker

from .MiscEvent import MiscEventSourceMixin, ProxyMiscEvent

from WikiExceptions import *

from . import SystemInfo
from .StringOps import escapeForIni, pathWordAndAnchorToWikiUrl
from . import Utilities


from .SearchAndReplace import stripSearchString

from .DocPagePresenter import BasicDocPagePresenter

import DocPages


class MainAreaPanel(aui.AuiNotebook, MiscEventSourceMixin):
    """
    The main area panel is embedded in the PersonalWikiFrame and holds and
    controls the doc page presenters.
    """

    def __init__(self, mainControl, parent, id):
        aui.AuiNotebook.__init__(self, parent, id)

#         nb = wx.PreNotebook()
#         self.PostCreate(nb)
        MiscEventSourceMixin.__init__(self)

        self.mainControl = mainControl
        self.mainControl.getMiscEvent().addListener(self)

        self.currentPresenter = None
        # References to all tab windows
        self._mruTabSequence = Utilities.IdentityList()
        self.tabSwitchByKey = 0  # 2: Key hit, notebook change not processed;
                # 1: Key hit, nb. change processed
                # 0: Processing done
        self.currentPresenterProxyEvent = ProxyMiscEvent(self)

        # Last presenter for which a context menu was shown
        self.lastContextMenuPresenter = None

        self.runningPageChangedEvent = False

#         res = xrc.XmlResource.Get()
#         self.docPagePresContextMenu = res.LoadMenu("MenuDocPagePresenterTabPopup")

        self.Bind(aui.EVT_AUINOTEBOOK_PAGE_CLOSE, self.OnCloseAuiTab)
        self.Bind(aui.EVT_AUINOTEBOOK_PAGE_CHANGED, self.OnNotebookPageChanged)
        self.Bind(aui.EVT_AUINOTEBOOK_PAGE_CHANGING, self.OnNotebookPageChanging)
        self.Bind(aui.EVT_AUINOTEBOOK_TAB_RIGHT_DOWN, self.OnTabContextMenu, self)
        self.Bind(aui.EVT_AUINOTEBOOK_PAGE_VISIBILITY_CHANGED,
                self.OnNotebookPageVisibilityChanged)
        
        #wx.EVT_CONTEXT_MENU(self, self.OnTabContextMenu)

        wx.EVT_KEY_UP(self, self.OnKeyUp)

        wx.EVT_MIDDLE_DOWN(self, self.OnMiddleDown)


        #wx.EVT_SET_FOCUS(self, self.OnFocused)
        wx.EVT_KILL_FOCUS(self, self.OnKillFocus)

        wx.EVT_MENU(self, GUI_ID.CMD_CLOSE_THIS_TAB, self.OnCloseThisTab)
        wx.EVT_MENU(self, GUI_ID.CMD_CLOSE_CURRENT_TAB, self.OnCloseCurrentTab)
        wx.EVT_MENU(self, GUI_ID.CMD_THIS_TAB_SHOW_SWITCH_EDITOR_PREVIEW,
                self.OnCmdSwitchThisEditorPreview)
        wx.EVT_MENU(self, GUI_ID.CMD_GO_NEXT_TAB, self.OnGoTab)
        wx.EVT_MENU(self, GUI_ID.CMD_GO_PREVIOUS_TAB, self.OnGoTab)
        wx.EVT_MENU(self, GUI_ID.CMD_CLIPBOARD_COPY_URL_TO_THIS_WIKIWORD,
                self.OnCmdClipboardCopyUrlToThisWikiWord)

    def close(self):
        for p in self.getPresenters():
            p.close()


    def getCurrentPresenter(self):
        # TODO: Some of the code arround this needs to be rewritten as
        #       focus events are not successfully followed
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
        return self.GetAllPages()


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
        return self.GetPageIndex(presenter)


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


    #    # TODO What about WikidPadHooks?
    def prepareCurrentPresenter(self, currentPresenter):
        """
        Mainly called by OnNotebookPageChanged to inform presenters
        about change
        """
        if currentPresenter is not self.currentPresenter:
#             # As multiple pages can now be shown on screen we check if its
#             # shown on screen, making sure the sub ctrl is visable if so.
#             for i in range(self.GetPageCount()):
#                 self.presenters[i].setLayerVisible(self.GetPage(i).IsShown())

    #        #if not (self.currentPresenter is currentPresenter):
        
            # TODO: Either keep currentPresenter up to date when switching pages
            #       (which I don't seem to be able to do) or rewrite the
            #       editor/preview switching so that currentPresenter is not
            #       required
            self.currentPresenter = currentPresenter
    #        #    #for p in self.presenters:
    #        #    #    p.setLayerVisible(p is currentPresenter)
            proxyEvent = self.getCurrentPresenterProxyEvent()
            proxyEvent.setWatchedEvents(
                    (self.currentPresenter.getMiscEvent(),))
            self.mainControl.refreshPageStatus()
            self.fireMiscEventKeys(("changed current presenter",))

            pres_id = self.getIndexForPresenter(currentPresenter)
            if self.GetSelection() != pres_id:
                self.SetSelection(pres_id)


    def showPresenter(self, currentPresenter):
        """
        Sets current presenter by changing the active tab in the
        main area notebook which in turn calls prepareCurrentPresenter()
        """
        i = self.getIndexForPresenter(currentPresenter)
        if i != wx.NOT_FOUND:
            self.SetSelection(i)


    def getCurrentPresenterProxyEvent(self):
        """
        This ProxyMiscEvent resends any messsages from the currently
        active DocPagePresenter
        """
        return self.currentPresenterProxyEvent


    def appendPresenterTab(self, presenter):
        self._mruTabWindowAppend(presenter)
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
        if idx == wx.NOT_FOUND:
            return False
            
        newIdx = -1
        if idx == self.GetSelection():
            switchMru = self.mainControl.getConfig().getboolean("main",
                    "mainTabs_switchMruOrder", True)
    
            if switchMru:
                # We are closing current active presenter and use MRU order
                # to switch -> select previous presenter in MRU order
                newWnd = self._mruTabWindowGetNext(presenter)
                if newWnd is not presenter:
                    self.SetSelectionToWindow(newWnd)

#                 elif newIdx > idx:
#                     # Adapt for after deletion of idx
#                     newIdx -= 1

        # Prepare presenter for closing
        presenter.close()

        # Actual deletion
        self._mruTabWindowDelete(presenter)

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
        if idx == wx.NOT_FOUND:
            return
            
        # Actual remove
        self._mruTabWindowDelete(presenter)
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
        for presenter in self.getPresenters():
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
        if self.GetPageIndex(presenter) == wx.NOT_FOUND:
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

    def OnNotebookPageChanging(self, evt):
        evt.Skip()

    def OnNotebookPageChanged(self, evt):
        presenter = self.GetPage(evt.GetSelection())
        self.prepareCurrentPresenter(presenter)
        if self.tabSwitchByKey < 2:
            self._mruTabWindowPushToTop(presenter)
            presenter.SetFocus()

        
    def OnNotebookPageVisibilityChanged(self, evt):
        evt.GetPageWindow().setLayerVisible(evt.IsVisible())


    def OnTabContextMenu(self, evt):
        pres = self.GetPage(evt.GetSelection())

        ctxMenu = pres.getTabContextMenu()
        if ctxMenu is not None:
            self.lastContextMenuPresenter = pres
#             sc = self.lastContextMenuPresenter
            self.PopupMenu(ctxMenu)



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
        self._mruTabWindowPushToTop(self.GetCurrentPage())

    def OnCloseAuiTab(self, evt):
        """
        AuiNotebook has a number of different ways of closing tabs
        """
        evt.Veto()
        self.closePresenterTab(self.GetPage(evt.GetSelection()))


    def OnCloseThisTab(self, evt):
        if self.lastContextMenuPresenter is not None:
            self.closePresenterTab(self.lastContextMenuPresenter)

    def OnCloseCurrentTab(self, evt):
        self.closePresenterTab(self.getCurrentPresenter())



    def _mruTabWindowPushToTop(self, wnd):
        """
        Push idx to top in mru list.
        """
        if wnd is None:
            return

        try:
            self._mruTabSequence.remove(wnd)
        except ValueError:
            pass

        self._mruTabSequence.insert(0, wnd)


    def _mruTabWindowAppend(self, wnd):
        self._mruTabSequence.append(wnd)


    def _mruTabWindowDelete(self, wnd):
        """
        Delete wnd.
        """
        self._mruTabSequence.remove(wnd)

    def _mruTabWindowGetNext(self, wnd):
        """
        Get next index after idx
        """
        try:
            return self._mruTabSequence[self._mruTabSequence.index(wnd) + 1]
        except (ValueError, IndexError):
            return self._mruTabSequence[0]

    def _mruTabWindowGetPrevious(self, wnd):
        """
        Get next index after idx
        """
        try:
            return self._mruTabSequence[self._mruTabSequence.index(wnd) - 1]
        except ValueError:
            return self._mruTabSequence[-1]




# 
#     # Handle self.mruTabIndex
#     def _mruTabIndexPushToTop(self, idx):
#         """
#         Push idx to top in mru list.
#         """
#         if idx == -1:
#             return
# 
#         try:
#             self.mruTabIndex.remove(idx)
#         except ValueError:
#             pass
#         
#         self.mruTabIndex.insert(0, idx)
# 
#     def _mruTabIndexAppend(self, idx):
#         self.mruTabIndex = [(i if i < idx else i + 1) for i in self.mruTabIndex]
#         self.mruTabIndex.append(idx)
# 
#     def _mruTabIndexDelete(self, idx):
#         """
#         Delete idx. Indices > idx must be decremented by one.
#         """
#         self.mruTabIndex = [(i if i < idx else i - 1) for i in self.mruTabIndex
#                 if i != idx]
# 
#     def _mruTabIndexGetNext(self, idx):
#         """
#         Get next index after idx
#         """
#         try:
#             return self.mruTabIndex[self.mruTabIndex.index(idx) + 1]
#         except (ValueError, IndexError):
#             return self.mruTabIndex[0]
# 
#     def _mruTabIndexGetPrevious(self, idx):
#         """
#         Get next index after idx
#         """
#         try:
#             return self.mruTabIndex[self.mruTabIndex.index(idx) - 1]
#         except ValueError:
#             return self.mruTabIndex[-1]


    def OnGoTab(self, evt):
        pageCount = self.GetPageCount()
        if pageCount < 2:
            return
            
        switchMru = self.mainControl.getConfig().getboolean("main",
                "mainTabs_switchMruOrder", True)
                
        newWnd = None
        newIdx = -1

        if evt.GetId() == GUI_ID.CMD_GO_NEXT_TAB:
            if switchMru:
                newWnd = self._mruTabWindowGetNext(self.GetCurrentPage())
                self.tabSwitchByKey = 2
            else:
                newIdx = self.GetSelection() + 1
                if newIdx >= pageCount:
                    newIdx = 0
        elif evt.GetId() == GUI_ID.CMD_GO_PREVIOUS_TAB:
            if switchMru:
                newWnd = self._mruTabWindowGetPrevious(self.GetCurrentPage())
                self.tabSwitchByKey = 2
            else:
                newIdx = self.GetSelection() - 1
                if newIdx < 0:
                    newIdx = pageCount - 1

        if newWnd is not None:
            self.SetSelectionToWindow(newWnd)
            # self.mainControl.tree.SetFocus()
            # wx.CallAfter(self.SetFocus)
        else:
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
            self._mruTabWindowPushToTop(self.GetCurrentPage())
            self.GetPage(self.GetSelection()).SetFocus()
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
            self._mruTabWindowPushToTop(self.GetCurrentPage())
            self.GetPage(self.GetSelection()).SetFocus()


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


    def OnMiddleDown(self, evt):
        tab = self.HitTest(evt.GetPosition())[0]
        if tab == wx.NOT_FOUND:
            return

        pres = self.GetPage(tab)
        mc = self.mainControl

        paramDict = {"presenter": pres, "main control": mc}
        mc.getUserActionCoord().reactOnUserEvent(
                u"mouse/middleclick/pagetab", paramDict)


    def miscEventHappened(self, miscevt):
        idx = self.GetPageIndex(miscevt.getSource())
        if idx != wx.NOT_FOUND:
            if miscevt.has_key("changed presenter title"):
                presenter = miscevt.getSource()

                self.SetPageText(idx, miscevt.get("title"))

                if presenter is self.getCurrentPresenter():
                    self.mainControl.refreshPageStatus()

        elif miscevt.getSource() is self.mainControl:
            if miscevt.has_key("closed current wiki"):
                self._closeAllButCurrentTab()



