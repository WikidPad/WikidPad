

## import hotshot
## _prof = hotshot.Profile("hotshot.prf")

import os, sys, traceback, re

import wx
import aui
# import wx.xrc as xrc

from .wxHelper import GUI_ID, copyTextToClipboard, getAccelPairFromKeyDown, \
        WindowUpdateLocker, isAllModKeysReleased

from .MiscEvent import MiscEventSourceMixin, ProxyMiscEvent

from .WikiExceptions import *

from . import SystemInfo
from .StringOps import escapeForIni, unescapeForIni, pathWordAndAnchorToWikiUrl
from . import Utilities
from .WindowLayout import StorablePerspective


from .SearchAndReplace import stripSearchString

from .DocPagePresenter import BasicDocPagePresenter

from . import DocPages


class MainAreaPanel(aui.AuiNotebook, MiscEventSourceMixin, StorablePerspective):
    """
    The main area panel is embedded in the PersonalWikiFrame and holds and
    controls the doc page presenters.
    """

    def __init__(self, mainControl, parent, id):
        # TODO: test some of the style flags
        #       * Floating tabs produces issues as the tabs are not longer
        #         associated with this notebook (so SetSelection order fails)
        #       * Check how day order is affected when splitting the page
        #
        #aui.AuiNotebook.__init__(self, parent, id, agwStyle=aui.AUI_NB_TAB_MOVE|aui.AUI_NB_TAB_SPLIT|aui.AUI_NB_TAB_FLOAT|aui.AUI_NB_ORDER_BY_ACCESS)
        aui.AuiNotebook.__init__(self, parent, id, agwStyle=aui.AUI_NB_DEFAULT_STYLE & ~aui.AUI_NB_MIDDLE_CLICK_CLOSE)

#         nb = wx.PreNotebook()
#         self.PostCreate(nb)
        MiscEventSourceMixin.__init__(self)

#         flags = aui.AUI_NB_TAB_SPLIT |\
#                 aui.AUI_NB_TAB_MOVE |\
#                 aui.AUI_NB_TAB_EXTERNAL_MOVE |\
#                 aui.AUI_NB_TAB_FLOAT
# 
#         # Playing around (testing different style flags)
#         self.SetAGWWindowStyleFlag(flags)

        self.mainControl = mainControl
        self.mainControl.getMiscEvent().addListener(self)

        self.preparingPresenter = False
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
#         self.Bind(aui.EVT_AUINOTEBOOK_PAGE_CHANGING, self.OnNotebookPageChanging)
        self.Bind(aui.EVT_AUINOTEBOOK_TAB_RIGHT_DOWN, self.OnTabContextMenu, self)
        self.Bind(aui.EVT_AUINOTEBOOK_TAB_MIDDLE_DOWN, self.OnTabMiddleDown, self)
        self.Bind(aui.EVT_AUINOTEBOOK_TAB_DCLICK, self.OnTabDoubleClick, self)
        self.Bind(aui.EVT_AUINOTEBOOK_PAGE_VISIBILITY_CHANGED,
                self.OnNotebookPageVisibilityChanged)
        self.Bind(aui.EVT_AUINOTEBOOK_SET_FOCUS,
                self.OnNotebookPageSetFocus)
        
        # self.Bind(wx.EVT_CONTEXT_MENU, self.OnTabContextMenu)

        self.Bind(wx.EVT_KEY_UP, self.OnKeyUp)

        # self.Bind(wx.EVT_MIDDLE_DOWN, self.OnMiddleDown)


#         self.Bind(wx.EVT_SET_FOCUS, self.OnFocused)
        self.Bind(wx.EVT_KILL_FOCUS, self.OnKillFocus)

        self.Bind(wx.EVT_MENU, self.OnCloseThisTab,
                id=GUI_ID.CMD_CLOSE_THIS_TAB)
        self.Bind(wx.EVT_MENU, self.OnCloseCurrentTab,
                id=GUI_ID.CMD_CLOSE_CURRENT_TAB)
        self.Bind(wx.EVT_MENU, self.OnCmdSwitchThisEditorPreview,
                id=GUI_ID.CMD_THIS_TAB_SHOW_SWITCH_EDITOR_PREVIEW)
        self.Bind(wx.EVT_MENU, self.OnGoTab,
                id=GUI_ID.CMD_GO_NEXT_TAB)
        self.Bind(wx.EVT_MENU, self.OnGoTab,
                id=GUI_ID.CMD_GO_PREVIOUS_TAB)
        self.Bind(wx.EVT_MENU, self.OnCmdClipboardCopyUrlToThisWikiWord,
                id=GUI_ID.CMD_CLIPBOARD_COPY_URL_TO_THIS_WIKIWORD)

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
            return ""

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


    def getTabCtrlsAndTheirPositions(self):
        panePosDict = {}
        for pane in self.GetAuiManager().GetAllPanes():
            if pane.name == "dummy":
                continue

            tabCtrl = pane.window._tabs
            panePosDict[tabCtrl] = (tabCtrl.GetPosition())

        return panePosDict


    def getTabCtrlByPresenter(self, presenter):
        """
        Returns the TabCtrl which contains a giver presenter
        """
        tabFrame = self.GetTabFrameFromWindow(presenter)

        if tabFrame is not None:
            return self.GetTabFrameFromWindow(presenter)._tabs

        return None


    def getTabCtrlTo(self, direction, presenter=None):
        """
        Returns the TabCtrl *direction* (of) the currently active one.

        @param direction: the direction to search, can be u"right", u"left"
                u"above", u"below"
        @param presenter: the presenter around which to search. If None the
                current presenter is used

        """

        tabCtrlPos = self.getTabCtrlsAndTheirPositions()

        if presenter is None:
            searchTabCtrl = self.GetActiveTabCtrl()
        else:
            searchTabCtrl = self.getTabCtrlByPresenter(presenter)

        curPos = tabCtrlPos.pop(searchTabCtrl)

        x, y = curPos

        # Hey I can't think of a better way to do this at the moment
        x_coord = None
        y_coord = None
        try:
            if direction == "right":
                x_coord = min([i[0] for i in list(tabCtrlPos.values()) if i[0]-x > 0])
                y_coord = min([i[1] for i in list(tabCtrlPos.values()) if i[0] == x_coord and i[1]-y >= 0])
            elif direction == "left":
                x_coord = max([i[0] for i in list(tabCtrlPos.values()) if x-i[0] > 0])
                y_coord = min([i[1] for i in list(tabCtrlPos.values()) if i[0] == x_coord and i[1]-y >= 0])
            elif direction == "above":
                y_coord = max([i[1] for i in list(tabCtrlPos.values()) if y-i[1] > 0])
                x_coord = min([i[0] for i in list(tabCtrlPos.values()) if i[1] == y_coord and i[0]-x >= 0])
            elif direction == "below":
                y_coord = min([i[1] for i in list(tabCtrlPos.values()) if i[1] - y > 0])
                x_coord = min([i[0] for i in list(tabCtrlPos.values()) if i[1] == y_coord and i[0]-x >= 0])
            else:
                return None
        except ValueError:
            # ValueError is raised if max() or min() is run on an empty list
            # i.e. if no valid x or y coord can be found
            pass


        new_ctrl = None
        for ctrl, pos in tabCtrlPos.items():
            if x_coord is None:
                if pos[1] == y_coord:
                    new_ctrl = ctrl
                    break
                continue
            elif y_coord is None:
                if pos[0] == x_coord:
                    new_ctrl = ctrl
                    break
                continue
            if pos == (x_coord, y_coord):
                new_ctrl = ctrl
                break

        return new_ctrl


    def switchPresenterByPosition(self, direction):
        """
        Activate the TabCtrl to the *direction* of the active one.

        see getTabCtrlTo for available directions
        """
        if direction is None:
            return

        newTabCtrl = self.getTabCtrlTo(direction)

        if newTabCtrl is not None:
            for page in newTabCtrl.GetPages():
                if page.window.IsShown():
                    self.SetSelectionToPage(page)
                    return

    def getActivePresenterInTabCtrl(self, tabCtrl):
        """
        Return the active (visible) presenter for a given TabCtrl

        """
        if tabCtrl is None:
            return None

        for page in tabCtrl.GetPages():
            if page.window.IsShown():
                return page.window

    def getActivePresenterTo(self, direction, presenter=None):
        """
        Returns the active (visible) presenter to the *direction* of the
        given presenter

        """
        return self.getActivePresenterInTabCtrl(
                self.getTabCtrlTo(direction, presenter))
        

    def getPossibleTabCtrlDirections(self, presenter=None):
        """
        Returns a dict of the TabCtrls surrounding a given presenter.

        If not presenter specified active presenter is used.

        """
        possible_directions = {}
        for direction in ["left", "right", "above", "below"]:
            possible_directions[direction] = self.getTabCtrlTo(direction, presenter)

        return possible_directions
        

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
            config.set("main", "further_wiki_words", "")
        else:
            fwws = ";".join([escapeForIni(w, " ;") for w in openWikiWords[1:]])
            config.set("main", "further_wiki_words", fwws)

        if len(openWikiWords) > 0:
            config.set("main", "last_wiki_word", openWikiWords[0])

            ltsc = ";".join([escapeForIni(w, " ;") for w in subCtrls])
            config.set("main", "wiki_lastTabsSubCtrls", ltsc)

            config.set("main", "wiki_lastActiveTabNo", activeNo)

        # Above settings are only stored for compatibility with earlier
        # versions (before 2.3beta10)

        config.set("main", "wiki_mainArea_auiPerspective",
                self.getStoredPerspective())

        config.save()


    #    # TODO What about WikidPadHooks?
    def prepareCurrentPresenter(self, currentPresenter):
        """
        Mainly called by OnNotebookPageChanged to inform presenters
        about change
        """
        if self.preparingPresenter:
            return

        if currentPresenter is not self.currentPresenter:
            self.currentPresenter = currentPresenter
            self.preparingPresenter = currentPresenter

            proxyEvent = self.getCurrentPresenterProxyEvent()
            proxyEvent.setWatchedEvents(
                    (self.currentPresenter.getMiscEvent(),))
            self.mainControl.refreshPageStatus()
            self.fireMiscEventKeys(("changed current presenter",))

            # Make the current notebook tab active
            pres_id = self.getIndexForPresenter(currentPresenter)
            if self.GetSelection() != pres_id:
                self.SetSelection(pres_id)

        # The currently active tab should always be visible (and enabled)
        #currentPresenter.setLayerVisible(True) # Causes the page to gain focus

            wx.CallAfter(self.presenterPrepared)


    def presenterPrepared(self):
        self.preparingPresenter = False


    def showPresenter(self, currentPresenter):
        """
        Sets current presenter by changing the active tab in the
        main area notebook which in turn calls prepareCurrentPresenter()
        """
        i = self.getIndexForPresenter(currentPresenter)
        if i != wx.NOT_FOUND:
            self.SetSelection(i, changeFocus=False)


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

        # Is not needed with AuiNotebook (and breaks new background tab 
        # compatability)
        #if SystemInfo.isLinux():
        #    presenter.Show(True)

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
        self.RemovePageByIdx(idx)
        self.updateConfig()


#     def _closeAllButCurrentTab(self):
#         """
#         Close all tabs except the current one.
#         """
#         current = self.currentPresenter
#         if current is None:
#             return
# 
#         if not isinstance(current, BasicDocPagePresenter):
#             # Current presenter is not a doc page one, so take first doc page
#             # presenter instead
#             current = self.getDocPagePresenters()[0]
# 
#         # Loop over copy of the presenter list
#         for presenter in self.getPresenters():
# #             if isinstance(presenter, BasicDocPagePresenter) and \
# #                     len(self.getDocPagePresenters()) < 2:
# #                 # At least one DPP tab must stay
# #                 return
#             if presenter is current:
#                 continue
# 
#             self.closePresenterTab(presenter)

    def _closeAllTabs(self):
        """
        Close all tabs.
        """
        
        for idx in range(self.GetPageCount() - 1, -1, -1):
            presenter = self.GetPage(idx)
            presenter.close()
            self.DeletePage(idx)
            
        self._mruTabWindowClear()
        
        self.currentPresenter = None
        proxyEvent = self.getCurrentPresenterProxyEvent()
        proxyEvent.setWatchedEvent(None)


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

#     def OnNotebookPageChanging(self, evt):
#         if self.preparingPresenter:
#             evt.Veto()
#             return
# 
#         evt.Skip()

    def OnNotebookPageChanged(self, evt):
        presenter = self.GetPage(evt.GetSelection())
        self.prepareCurrentPresenter(presenter)
        if self.tabSwitchByKey < 2:
            self._mruTabWindowPushToTop(presenter)
            presenter.SetFocus()

        
    def OnNotebookPageVisibilityChanged(self, evt):
        evt.GetPageWindow().setLayerVisible(evt.IsVisible())


    def OnTabContextMenu(self, evt, pres=None):
        if pres is None:
            pres = self.GetPage(evt.GetSelection())

        ctxMenu = pres.getTabContextMenu()
        if ctxMenu is not None:
            self.lastContextMenuPresenter = pres
#             sc = self.lastContextMenuPresenter
            self.PopupMenu(ctxMenu)



    def OnNotebookPageSetFocus(self, evt):
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

        self._mruTabSequence.drop(wnd)
        self._mruTabSequence.insert(0, wnd)


    def _mruTabWindowAppend(self, wnd):
        self._mruTabSequence.append(wnd)


    def _mruTabWindowDelete(self, wnd):
        """
        Delete wnd.
        """
        self._mruTabSequence.drop(wnd)

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

    def _mruTabWindowClear(self):
        self._mruTabSequence.clear()
        


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
            self.SetFocus()
            # self.mainControl.tree.SetFocus()
            # wx.CallAfter(self.SetFocus)
        else:
            self.SetSelection(newIdx)

        if self.tabSwitchByKey > 0:
            self.tabSwitchByKey = 1


    def OnKeyUp(self, evt):
        if self.tabSwitchByKey == 0:
            evt.Skip()
            return

        if not isAllModKeysReleased(evt):
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
                    _("This can only be done for the page of a wiki word"),
                    _('Not a wiki page'), wx.OK, self)
            return

        path = self.mainControl.getWikiDocument().getWikiConfigPath()
        copyTextToClipboard(pathWordAndAnchorToWikiUrl(path, wikiWord, None))


    def OnTabMiddleDown(self, evt):
        #tab = evt.GetSelection()
        #if tab == wx.NOT_FOUND:
        #    return

        #pres = self.GetPage(tab)

        # GetSelection returns the tab from the current TabCtrl
        # instead we can just access the tab directly
        pres = evt.Page
        mc = self.mainControl

        paramDict = {"presenter": pres, "main control": mc}
        mc.getUserActionCoord().reactOnUserEvent(
                "mouse/middleclick/pagetab", paramDict)


    def OnTabDoubleClick(self, evt):
        pres = evt.Page
        mc = self.mainControl

        paramDict = {"presenter": pres, "main control": mc}
        mc.getUserActionCoord().reactOnUserEvent(
                u"mouse/leftdoubleclick/pagetab", paramDict)


    def miscEventHappened(self, miscevt):
        idx = self.GetPageIndex(miscevt.getSource())
        if idx != wx.NOT_FOUND:
            if "changed presenter title" in miscevt:
                presenter = miscevt.getSource()

                self.SetPageText(idx, miscevt.get("title"))

                if presenter is self.getCurrentPresenter():
                    self.mainControl.refreshPageStatus()

        elif miscevt.getSource() is self.mainControl:
            if "closed current wiki" in miscevt:
                # self._closeAllButCurrentTab()
                self._closeAllTabs()


# ----- Implementation of StorablePerspective methods -----

    def getPerspectiveType(self):
        return "MainAreaPanel"
        
    def getStoredPerspective(self):
        # Based on AuiNotebook.SavePerspective()
        
        # Build list of panes/tabs
        # Version code
        tabs = "v1/"
        all_panes = self._mgr.GetAllPanes()

        sel_wnd = self.GetCurrentPage()

        paneDescs = []
        
        for pane in all_panes:
            paneDesc = ""

            if pane.name == "dummy":
                continue

            tabframe = pane.window

#             if tabs:
#                 tabs += u"|"

            paneDesc += pane.name + "="

            # add tab id's
            page_count = tabframe._tabs.GetPageCount()

            tabDescs = []

            for p in range(page_count):
                tabDesc = ""

                page = tabframe._tabs.GetPage(p)
                if not isinstance(page.window, StorablePerspective):
                    continue
                    
                tabPerspect = page.window.getStoredPerspective()
                if tabPerspect is None:
                    continue

                # page_idx = self._tabs.GetIdxFromWindow(page.window)

                if sel_wnd is page.window:
                    tabDesc += "*"
                elif p == tabframe._tabs.GetActivePageIdx():
                    tabDesc += "+"
                else:
                    tabDesc += " "
                    
                tabDesc += escapeForIni(page.window.getPerspectiveType(), "|=,@") + "="
                tabDesc += escapeForIni(page.caption, "|=,@") + "="
                tabDesc += str(self._mruTabSequence.find(page.window)) + "="
                tabDesc += escapeForIni(tabPerspect, "|=,@")
                
                tabDescs.append(tabDesc)

            paneDesc += ",".join(tabDescs)
            
            paneDescs.append(paneDesc)


        tabs += "|".join(paneDescs) + "@"

        # Add frame perspective
        tabs += self._mgr.SavePerspective()

        return tabs
    
        
    def setByStoredPerspective(self, perspectType, data, typeFactory):
        """
        Unlike the default LoadPerspective() function the necessary tabs are
        created here on-demand instead of pre-creating them. This ensures
        that the perspective can be reconstructed even if one or more tabs
        can't be recreated. Each tab is built by the typeFactory which
        is normally the function PersonalWikiFrame.perspectiveTypeFactory()
        """
        # Based on AuiNotebook.LoadPerspective()

        if not data.startswith("v1/"):
            return False

        data = data[3:]

        # Delete all tab ctrls
        tab_count = self._tabs.GetPageCount()
        
        # Contains a list of windows which should be deleted finally
        # Deletion is postponed as typeFactory may be able to recycle
        # some of them (currently not)
        windowsToDel = []

        for i in range(tab_count):
            wnd = self._tabs.GetWindowFromIdx(i)

            # find out which onscreen tab ctrl owns this tab
            ctrl, ctrl_idx = self.FindTab(wnd)
            if not ctrl:
                return False
                
            # remove the tab from ctrl
            if not ctrl.RemovePage(wnd):
                return False
                
            windowsToDel.append(wnd)
            
        self.RemoveEmptyTabFrames()
        
        self._tabs.RemoveAllPages()

        mruList = []
        
        # Main area panel is empty at this point

        sel_wnd = None
        tabs = data[0:data.index("@")]
        to_break1 = False

        while 1:
            if "|" not in tabs:
                to_break1 = True
                tab_part = tabs
            else:
                tab_part = tabs[0:tabs.index('|')]

            if "=" not in tab_part or tab_part[-1] == "=":
                # No pages in this perspective...
                return False

            # Get pane name
            pane_name = tab_part[0:tab_part.index("=")]

            # create a new tab frame
            new_tabs = aui.TabFrame(self)
            self._tab_id_counter += 1
            new_tabs._tabs = aui.AuiTabCtrl(self, self._tab_id_counter)
            new_tabs._tabs.SetArtProvider(self._tabs.GetArtProvider().Clone())
            new_tabs.SetTabCtrlHeight(self._tab_ctrl_height)
            new_tabs._tabs.SetAGWFlags(self._agwFlags)
            dest_tabs = new_tabs._tabs

            # create a pane info structure with the information
            # about where the pane should be added
            pane_info = aui.framemanager.AuiPaneInfo().Name(pane_name).Bottom().CaptionVisible(False)
            self._mgr.AddPane(new_tabs, pane_info)

            # Get list of tab id's and move them to pane
            tab_list = tab_part[tab_part.index("=")+1:]
            to_break2, active_found = False, False

            for tab in tab_list.split(","):
                if tab.strip() == "":
                    continue

#                 if u"," not in tab_list:
#                     to_break2 = True
#                     tab = tab_list
#                 else:
#                     tab = tab_list[0:tab_list.index(u",")]
#                     tab_list = tab_list[tab_list.index(u",")+1:]

                # Store possible 'active' marker for later use
                c = tab[0]
                tab = tab[1:]

#                 tab_idx = int(tab)
#                 if tab_idx >= self.GetPageCount():
#                     to_break1 = True
#                     break

                # if more parts are available after an additional '=' they are ignored
                perspectType, caption, mruOrder, wndPerspective = tab.split("=", 4)[:4]
                perspectType = unescapeForIni(perspectType)
                caption = unescapeForIni(caption)
                wndPerspective = unescapeForIni(wndPerspective)

                page = aui.AuiNotebookPage()
                page.window = typeFactory(self, perspectType, wndPerspective,
                        typeFactory)

                if page.window is None:
                    continue

                page.caption = caption
                page.bitmap = wx.NullBitmap
                page.dis_bitmap = wx.NullBitmap
                page.active = False
                page.control = None
                
                self._tabs.AddPage(page.window, page)
                # Move tab to pane
                newpage_idx = dest_tabs.GetPageCount()
                dest_tabs.InsertPage(page.window, page, newpage_idx)
                
                # --- begin WikidPad specific ---
                page.window.getMiscEvent().addListener(self)
                try:
                    mruOrder = int(mruOrder)
                    if mruOrder >= 0:
                        while len(mruList) <= mruOrder:
                            mruList.append(None)
                        mruList[mruOrder] = page.window
                except ValueError:
                    traceback.print_exc()
                # --- end WikidPad specific ---
                    
                if c == '+':
                    dest_tabs.SetActivePage(newpage_idx)
                    active_found = True
                elif c == '*':
                    sel_wnd = page.window

#                 if to_break2:
#                     break

            if not active_found:
                dest_tabs.SetActivePage(0)
                
            # --- begin WikidPad specific ---
            self._mruTabSequence = Utilities.IdentityList(
                    wnd for wnd in mruList if wnd is not None)
            # --- end WikidPad specific ---

            new_tabs.DoSizing()
            dest_tabs.DoShowHide()
            dest_tabs.Refresh()

            if to_break1:
                break

            tabs = tabs[tabs.index('|')+1:]

        # Load the frame perspective
        frames = data[data.index('@')+1:]
        self._mgr.LoadPerspective(frames)

        self.RemoveEmptyTabFrames()

        # Force refresh of selection
        self._curpage = -1
        
        if sel_wnd is None:
            self.SetSelection(0)
        else:
            self.SetSelectionToWindow(sel_wnd)
            self._mruTabWindowPushToTop(sel_wnd)

        self.UpdateTabCtrlHeight()
        
        # Now delete all orphaned windows
        
        for wnd in windowsToDel:
            if self._tabs.GetIdxFromWindow(wnd) != wx.NOT_FOUND:
                # Window in again use
                continue
        
            if isinstance(wnd, StorablePerspective):
                wnd.deleteForNewPerspective()
            else:
                wnd.Destroy()

        return True


#     @staticmethod
#     def createFromStoredPerspective(parent, perspectType, data, typeFactory):
#         result = MainAreaPanel(parent, parent, -1)
#         result.setByStoredPerspective(perspectType, data, typeFactory)
#         return result

