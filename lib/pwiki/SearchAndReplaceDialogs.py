# import profilehooks
# profile = profilehooks.profile(filename="profile.prf", immediate=False)

import sys, traceback, re, time

import wx, wx.html, wx.xrc

from .rtlibRepl import minidom

import Consts
from .MiscEvent import MiscEventSourceMixin, KeyFunctionSink
from .WikiExceptions import *
from .Utilities import DUMBTHREADSTOP, callInMainThread, callInMainThreadAsync, \
        ThreadHolder, FunctionThreadStop

from .SystemInfo import isLinux

from . import wxHelper
from .wxHelper import *

from .StringOps import escapeHtml

from .WikiPyparsing import ParseException

from .WindowLayout import setWindowPos, setWindowSize, \
        getRelativePositionTupleToAncestor, LayeredControlPanel

from .Configuration import MIDDLE_MOUSE_CONFIG_TO_TABMODE

from .SearchAndReplace import SearchReplaceOperation, ListWikiPagesOperation, \
        stripSearchString




class _SearchResultItemInfo:
    __slots__ = ("__weakref__", "wikiWord", "occCount", "occNumber", "occHtml",
            "occPos", "html", "maxCountOccurrences")

    def __init__(self, wikiWord, occPos = (-1, -1), occCount = -1,
            maxOccCount=100):
        self.wikiWord = wikiWord
        if occPos[0] != -1:
            self.occNumber = 1
        else:
            self.occNumber = -1  # -1: No specific occurrence

        self.occHtml = ""  # HTML presentation of the occurrence
        self.occPos = occPos  # Tuple (start, end) with position of occurrence in characters
        self.occCount = occCount # -1: Undefined; -2: More than maxCountOccurrences
        self.maxCountOccurrences = maxOccCount
        self.html = None


    def buildOccurrence(self, text, before, after, pos, occNumber, maxOccCount):
        self.html = None
        basum = before + after
        self.occNumber = -1
        self.occPos = pos
        self.maxCountOccurrences = maxOccCount

        if basum == 0:
            # No context
            self.occHtml = ""
            return self
        
        if pos[0] is None:
            # All occurences where deleted meanwhile dialog was open
            self.occHtml = ""
            self.occNumber = 0
            self.occCount = 0
            return self
        
        if pos[0] == -1:
            # No position -> use beginning of text
            self.occHtml = escapeHtml(text[0:basum])
            return self
        
        s = max(0, pos[0] - before)
        e = min(len(text), pos[1] + after)
        self.occHtml = "".join([escapeHtml(text[s:pos[0]]), 
            "<b>", escapeHtml(text[pos[0]:pos[1]]), "</b>",
            escapeHtml(text[pos[1]:e])])
            
        self.occNumber = occNumber
        return self


    def setHtmlDirectly(self, occHtml):
        self.occNumber = -1
        self.occCount = -1
        self.occHtml = occHtml



    def getHtml(self):
        if self.html is None:
            result = ['<table><tr><td bgcolor="#0000ff" width="6"></td>'
                    '<td><font color="BLUE"><b>%s</b></font>' % \
                    escapeHtml(self.wikiWord)]
            
            if self.occNumber != -1:
                stroc = [str(self.occNumber), "/"]
            else:
                stroc = []
                
            if self.occCount > -1:
                stroc.append(str(self.occCount))
            elif len(stroc) > 0:
                if self.occCount == -1:
                    stroc.append("?")
                elif self.occCount == -2:
                    stroc.append(">%s" % self.maxCountOccurrences)

            stroc = "".join(stroc)
            
            if stroc != "":
                result.append(' <b>(%s)</b>' % stroc)
                
            if self.occHtml != "":
                result.append('<br>\n')
                result.append(self.occHtml)
                
            result.append('</td></tr></table>')
            self.html = "".join(result)
            
        return self.html



class SearchResultListBox(wx.html.HtmlListBox, MiscEventSourceMixin):
    def __init__(self, parent, pWiki, ID):
        wx.html.HtmlListBox.__init__(self, parent, ID, style = wx.SUNKEN_BORDER)

        self.pWiki = pWiki
        self.searchWikiDialog = parent
        self.found = []
        self.foundinfo = []
        self.searchOp = None # last search operation set by showFound
        self.SetItemCount(0)
        self.isShowingSearching = False  # Show a visual feedback only while searching
        self.contextMenuSelection = -2

        self.Bind(wx.EVT_LEFT_DOWN, self.OnLeftDown)
        self.Bind(wx.EVT_LEFT_DCLICK, self.OnLeftDown)
        self.Bind(wx.EVT_MIDDLE_DOWN, self.OnMiddleButtonDown)
        self.Bind(wx.EVT_KEY_DOWN, self.OnKeyDown)
        self.Bind(wx.EVT_LISTBOX_DCLICK, self.OnDClick, id=ID)
        self.Bind(wx.EVT_CONTEXT_MENU, self.OnContextMenu)


        self.Bind(wx.EVT_MENU, self.OnActivateThis, id=GUI_ID.CMD_ACTIVATE_THIS)
        self.Bind(wx.EVT_MENU, self.OnActivateNewTabThis, id=GUI_ID.CMD_ACTIVATE_NEW_TAB_THIS)
        self.Bind(wx.EVT_MENU, self.OnActivateNewTabBackgroundThis, id=GUI_ID.CMD_ACTIVATE_NEW_TAB_BACKGROUND_THIS)


    def OnGetItem(self, i):
        if self.isShowingSearching:
            return "<b>" + _("Searching... (click into field to abort)") + "</b>"
        elif self.GetCount() == 0:
            return "<b>" + _("Not found") + "</b>"

        try:
            return self.foundinfo[i].getHtml()
        except IndexError:
            return ""

    def showSearching(self):
        """
        Shows a "Searching..." as visual feedback while search runs
        """
        self.isShowingSearching = True
        self.SetItemCount(1)
        self.Refresh()
        self.Update()
        
    def ensureNotShowSearching(self):
        """
        This function is called after a search operation and a call to
        showFound may have happened. If it did not happen,
        the list is cleared.
        """
        if self.isShowingSearching:
            # This can only happen if showFound wasn't called
            self.showFound(None, None, None)


    def _displayFound(self, itemCount, threadstop):
        """
        Called by showFound(), must be called in main thread.
        """
        if threadstop.isValidThread():
            self.SetItemCount(itemCount)
            self.Refresh()


    def showFound(self, sarOp, found, wikiDocument,
            threadstop=DUMBTHREADSTOP):
        """
        Shows the results of search operation sarOp
        found -- list of matching wiki words
        wikiDocument -- WikiDocument object
        """
        if found is None or len(found) == 0:
            self.found = []
            self.foundinfo = []
            self.searchOp = None
            self.isShowingSearching = False
            callInMainThreadAsync(self._displayFound, 1, threadstop)   # For the "Not found" entry
        else:
            try:
                # Store and prepare clone of search operation
                self.searchOp = sarOp.clone()
                self.searchOp.replaceOp = False
                self.searchOp.cycleToStart = True
    
                self.found = found
                self.foundinfo = []
                # Load context settings
                before = self.pWiki.configuration.getint("main",
                        "search_wiki_context_before")
                after = self.pWiki.configuration.getint("main",
                        "search_wiki_context_after")
                        
                countOccurrences = self.pWiki.getConfig().getboolean("main",
                        "search_wiki_count_occurrences")
                maxCountOccurrences = self.pWiki.getConfig().getint("main",
                        "search_wiki_max_count_occurrences", 100)

                context = before + after

                if sarOp.hasParticularTextPosition():
                    if context == 0 and not countOccurrences:
                        # No context, no occurrence counting
                        # -> just a list of found pages
                        self.foundinfo = [_SearchResultItemInfo(w) for w in found]
                    else:
                        # "As is" or regex search
                        sarOp.beginWikiSearch(self.pWiki.getWikiDocument())
                        try:
                            for w in found:
                                threadstop.testValidThread()
                                docPage = wikiDocument.getWikiPageNoError(w)
                                text = docPage.getLiveTextNoTemplate()
                                if text is None:
                                    continue
    
    #                             pos = sarOp.searchText(text)
                                pos = sarOp.searchDocPageAndText(docPage, text)
                                if pos[0] is None:
                                    # This can happen e.g. for boolean searches like
                                    # 'foo or not bar' on a page which has neither 'foo'
                                    # nor 'bar'.
                                    
                                    # Similar as if no particular text position available
                                    if context == 0:
                                        self.foundinfo.append(
                                                _SearchResultItemInfo(w))
                                    else:
                                        self.foundinfo.append(
                                                _SearchResultItemInfo(w).buildOccurrence(
                                                text, before, after, (-1, -1), -1,
                                                100))
                                    continue
                                firstpos = pos
                                
                                info = _SearchResultItemInfo(w, occPos=pos,
                                        maxOccCount=maxCountOccurrences)
    
                                if countOccurrences:
                                    occ = 1
                                    while True:
                                        pos = sarOp.searchDocPageAndText(
                                                docPage, text, pos[1])
                                        if pos[0] is None or pos[0] == pos[1]:
                                            break
                                        occ += 1
                                        if occ > maxCountOccurrences:
                                            occ = -2
                                            break
    
                                    info.occCount = occ
    
                                self.foundinfo.append(info.buildOccurrence(
                                        text, before, after, firstpos, 1,
                                        maxCountOccurrences))
                        finally:
                            sarOp.endWikiSearch()
                elif sarOp.hasWhooshHighlighting():
                    # Index search
                    if context == 0:
                        # No context, occurrence counting doesn't matter
                        # -> just a list of found pages
                        self.foundinfo = [_SearchResultItemInfo(w) for w in found]
                    else:
                        sarOp.beginWikiSearch(self.pWiki.getWikiDocument())
                        try:
                            for w in found:
                                threadstop.testValidThread()
                                docPage = wikiDocument.getWikiPageNoError(w)
                                text = docPage.getLiveTextNoTemplate()
                                if text is None:
                                    continue
    
                                html, firstPos = sarOp.highlightWhooshIndexFound(
                                        text, docPage, context * 2 + 30,
                                        context // 2)
                                
                                info = _SearchResultItemInfo(w, occPos=(firstPos, firstPos))
                                info.setHtmlDirectly(html)
    
                                self.foundinfo.append(info)
                        finally:
                            sarOp.endWikiSearch()
                else:  # not sarOp.hasParticularTextPosition():
                    # No specific position to show as context, so show beginning of page
                    # Also, no occurrence counting possible
                    if context == 0:
                        self.foundinfo = [_SearchResultItemInfo(w) for w in found]
                    else:
                        for w in found:
                            text = wikiDocument.getWikiPageNoError(w).\
                                    getLiveTextNoTemplate()
                            if text is None:
                                continue
                            self.foundinfo.append(
                                    _SearchResultItemInfo(w).buildOccurrence(
                                    text, before, after, (-1, -1), -1, 100))
                    threadstop.testValidThread()
                
                threadstop.testValidThread()
                self.isShowingSearching = False
#                 callInMainThreadAsync(self.SetItemCount, len(self.foundinfo))
                callInMainThreadAsync(self._displayFound, len(self.foundinfo),
                        threadstop)

            except NotCurrentThreadException:
                self.found = []
                self.foundinfo = []
                self.isShowingSearching = False
                # For the "Not found" entry
                callInMainThreadAsync(self._displayFound, 1, threadstop)
                raise


    def GetSelectedWord(self):
        sel = self.GetSelection()
        if sel == -1 or self.GetCount() == 0:
            return None
        else:
            return self.foundinfo[sel].wikiWord
            
    def GetCount(self):
        return len(self.found)

    def IsEmpty(self):
        return self.GetCount() == 0


    def _pageListFindNext(self):
        """
        After pressing F3 or clicking blue bar of an entry, position of
        next found element should be shown
        """
        sel = self.GetSelection()
        if sel == -1:
            return
        
        info = self.foundinfo[sel]
        if info.occPos[0] == -1 or info.occPos[1] is None:
            return
        if info.occNumber == -1:
            return

        before = self.pWiki.configuration.getint("main",
                "search_wiki_context_before")
        after = self.pWiki.configuration.getint("main",
                "search_wiki_context_after")

        maxCountOccurrences = self.pWiki.getConfig().getint("main",
                "search_wiki_max_count_occurrences", 100)

        wikiDocument = self.pWiki.getWikiDocument()
        docPage = wikiDocument.getWikiPageNoError(info.wikiWord)
        text = docPage.getLiveTextNoTemplate()
        if text is not None:
            self.searchOp.beginWikiSearch(self.pWiki.getWikiDocument())
            try:
#                 pos = self.searchOp.searchText(text, info.occPos[1])
                pos = self.searchOp.searchDocPageAndText(docPage, text,
                        info.occPos[1])
            finally:
                self.searchOp.endWikiSearch()
        else:
            pos = (-1, -1)

        if pos[0] == -1:
            # Page was changed after last search and doesn't contain any occurrence anymore
            info.occCount = 0
            info.buildOccurrence(text, 0, 0, pos, -1, maxCountOccurrences)
        elif pos[0] < info.occPos[1]:
            # Search went back to beginning, number of last occ. is also occ.count
            info.occCount = info.occNumber
            info.buildOccurrence(text, before, after, pos, 1,
                    maxCountOccurrences)
        elif info.occPos[0] == info.occPos[1]:    # pos[0] == info.occPos[1]:
            # Match is empty
            info.occCount = info.occNumber
            info.buildOccurrence(text, before, after, pos, 1,
                    maxCountOccurrences)            
        else:
            info.buildOccurrence(text, before, after, pos, info.occNumber + 1,
                    maxCountOccurrences)

        # TODO nicer refresh
        self.SetSelection(-1)
        self.SetSelection(sel)
        self.Refresh()


    def OnDClick(self, evt):
        sel = self.GetSelection()
        if sel == -1 or self.GetCount() == 0:
            return

        info = self.foundinfo[sel]

        self.pWiki.openWikiPage(info.wikiWord)

        editor = self.pWiki.getActiveEditor()
        if editor is not None:
            if info.occPos[0] != -1:
                self.pWiki.getActiveEditor().showSelectionByCharPos(info.occPos[0],
                        info.occPos[1])
#                 self.pWiki.getActiveEditor().ensureSelectionExpanded()

            # Works in fast search popup only if called twice
            editor.SetFocus()
            editor.SetFocus()
            # Sometimes not even then
            self.fireMiscEventKeys(("opened in foreground",))


    def OnLeftDown(self, evt):
        if self.isShowingSearching:
            self.searchWikiDialog.stopSearching()

        if self.GetCount() == 0:
            return  # no evt.Skip()?

        pos = evt.GetPosition()
        hitsel = self.VirtualHitTest(pos.y)
        
        if hitsel == wx.NOT_FOUND:
            evt.Skip()
            return
        
        if pos.x < (5 + 6):
            # Click inside the blue bar
            self.SetSelection(hitsel)
            self._pageListFindNext()
            return
        
        evt.Skip()


    def OnMiddleButtonDown(self, evt):
        if self.GetCount() == 0:
            return  # no evt.Skip()?

        pos = evt.GetPosition()
        if pos == wx.DefaultPosition:
            hitsel = self.GetSelection()

        hitsel = self.VirtualHitTest(pos.y)

        if hitsel == wx.NOT_FOUND:
            evt.Skip()
            return

        if pos.x < (5 + 6):
            # Click inside the blue bar
            self.SetSelection(hitsel)
            self._pageListFindNext()
            return
        
        info = self.foundinfo[hitsel]

        if evt.ControlDown():
            configCode = self.pWiki.getConfig().getint("main",
                    "mouse_middleButton_withCtrl")
        else:
            configCode = self.pWiki.getConfig().getint("main",
                    "mouse_middleButton_withoutCtrl")
                    
        tabMode = MIDDLE_MOUSE_CONFIG_TO_TABMODE[configCode]

        presenter = self.pWiki.activatePageByUnifiedName(
                "wikipage/" + info.wikiWord, tabMode)
        
        if presenter is None:
            return

        if info.occPos[0] != -1:
            presenter.getSubControl("textedit").showSelectionByCharPos(
                    info.occPos[0], info.occPos[1])

        if configCode != 1:
            # If not new tab opened in background -> focus editor

            # Works in fast search popup only if called twice
            self.pWiki.getActiveEditor().SetFocus()
            self.pWiki.getActiveEditor().SetFocus()
            
            self.fireMiscEventKeys(("opened in foreground",))

        
    def OnKeyDown(self, evt):
        if self.GetCount() == 0:
            return  # no evt.Skip()?

        accP = getAccelPairFromKeyDown(evt)
        matchesAccelPair = self.pWiki.keyBindings.matchesAccelPair
        
        if matchesAccelPair("ContinueSearch", accP):
            # ContinueSearch is normally F3
            self._pageListFindNext()
        elif accP == (wx.ACCEL_NORMAL, wx.WXK_RETURN) or \
                accP == (wx.ACCEL_NORMAL, wx.WXK_NUMPAD_ENTER):
            self.OnDClick(evt)
        else:
            evt.Skip()


    def OnContextMenu(self, evt):
        if self.GetCount() == 0:
            return  # no evt.Skip()?

        pos = evt.GetPosition()
        if pos == wx.DefaultPosition:
            hitsel = self.GetSelection()
        else:
            hitsel = self.VirtualHitTest(self.ScreenToClient(pos).y)

        if hitsel == wx.NOT_FOUND:
            evt.Skip()
            return

        self.contextMenuSelection = hitsel
        try:
            menu = wx.Menu()
            appendToMenuByMenuDesc(menu, _CONTEXT_MENU_ACTIVATE)
            self.PopupMenu(menu)
            menu.Destroy()
        finally:
            self.contextMenuSelection = -2



    def OnActivateThis(self, evt):
        if self.contextMenuSelection > -1:
            info = self.foundinfo[self.contextMenuSelection]

#             presenter = self.pWiki.activateWikiWord(info.wikiWord, 0)
            presenter = self.pWiki.activatePageByUnifiedName(
                    "wikipage/" + info.wikiWord, 0)

            if presenter is None:
                return

            if info.occPos[0] != -1:
                presenter.getSubControl("textedit").showSelectionByCharPos(
                        info.occPos[0], info.occPos[1])
    
            # Works in fast search popup only if called twice
            self.pWiki.getActiveEditor().SetFocus()
            self.pWiki.getActiveEditor().SetFocus()
            
            # Context menu is open yet -> send later
            wx.CallAfter(self.fireMiscEventKeys, ("opened in foreground",))


    def OnActivateNewTabThis(self, evt):
        if self.contextMenuSelection > -1:
            info = self.foundinfo[self.contextMenuSelection]

#             presenter = self.pWiki.activateWikiWord(info.wikiWord, 2)
            presenter = self.pWiki.activatePageByUnifiedName(
                    "wikipage/" + info.wikiWord, 2)

            if presenter is None:
                return

            if info.occPos[0] != -1:
                presenter.getSubControl("textedit").showSelectionByCharPos(
                        info.occPos[0], info.occPos[1])
    
            # Works in fast search popup only if called twice
            self.pWiki.getActiveEditor().SetFocus()
            self.pWiki.getActiveEditor().SetFocus()
            
            # Context menu is open yet -> send later
            wx.CallAfter(self.fireMiscEventKeys, ("opened in foreground",))


    def OnActivateNewTabBackgroundThis(self, evt):
        if self.contextMenuSelection > -1:
            info = self.foundinfo[self.contextMenuSelection]

#             presenter = self.pWiki.activateWikiWord(info.wikiWord, 3)
            presenter = self.pWiki.activatePageByUnifiedName(
                    "wikipage/" + info.wikiWord, 3)
            
            if presenter is None:
                return

            if info.occPos[0] != -1:
                presenter.getSubControl("textedit").showSelectionByCharPos(
                        info.occPos[0], info.occPos[1])


class SearchPageDialog(wx.Dialog):
    def __init__(self, mainControl, ID, title="",
                 pos=wx.DefaultPosition, size=wx.DefaultSize,
                 style=wx.NO_3D|wx.DEFAULT_DIALOG_STYLE|wx.RESIZE_BORDER):
        
        wx.Dialog.__init__(self)

        self.mainControl = mainControl

        res = wx.xrc.XmlResource.Get()
        res.LoadDialog(self, self.mainControl, "SearchPageDialog")

        self.ctrls = XrcControls(self)

        self.ctrls.btnClose.SetId(wx.ID_CANCEL)
        
        self.showExtended = True
        self.mainSizer = self.GetSizer()
#         self.mainSizer.Detach(self.ctrls.lbSavedSearches)
        self.OnToggleExtended(None)
        
        self.firstFind = True
        self.savedSearches = None

        self._refreshSavedSearchesList()
        self._refreshSearchHistoryCombo()
        

        # Fixes focus bug under Linux
        self.SetFocus()

        self.Bind(wx.EVT_BUTTON, self.OnFindNext, id=GUI_ID.btnFindNext)        
        self.Bind(wx.EVT_BUTTON, self.OnReplace, id=GUI_ID.btnReplace)
        self.Bind(wx.EVT_BUTTON, self.OnReplaceAll, id=GUI_ID.btnReplaceAll)

        self.Bind(wx.EVT_BUTTON, self.OnToggleExtended, id=GUI_ID.btnToggleExtended)
        self.Bind(wx.EVT_BUTTON, self.OnSaveSearch, id=GUI_ID.btnSaveSearch)
        self.Bind(wx.EVT_BUTTON, self.OnDeleteSearches, id=GUI_ID.btnDeleteSearches)
        self.Bind(wx.EVT_BUTTON, self.OnLoadSearch, id=GUI_ID.btnLoadSearch)
#         self.Bind(wx.EVT_BUTTON, self.OnLoadAndRunSearch, id=GUI_ID.btnLoadAndRunSearch)

        self.Bind(wx.EVT_BUTTON, self.OnClose, id=wx.ID_CANCEL)
        self.Bind(wx.EVT_COMBOBOX, self.OnSearchComboSelected, id=GUI_ID.cbSearch) 
        self.Bind(wx.EVT_LISTBOX_DCLICK, self.OnLoadSearch, id=GUI_ID.lbSavedSearches)
        self.Bind(wx.EVT_CLOSE, self.OnClose)
        

    def OnClose(self, evt):
        self.mainControl.nonModalFindDlg = None
        self.Destroy()


    def OnToggleExtended(self, evt):
        self.showExtended = not self.showExtended
        winMin = self.GetMinSize()
        winCurr = self.GetSize()
        oldSizerMin = self.mainSizer.CalcMin()

#         print "--OnToggleExtended3", repr((self.showExtended, self.mainSizer.CalcMin()))
        
        if not self.showExtended:
            self.ctrls.panelSavedSearchButtons.Show(False)
            self.mainSizer.Detach(self.ctrls.panelSavedSearchButtons)
            self.ctrls.btnToggleExtended.SetLabel(_("More >>"))
        else:
            self.ctrls.panelSavedSearchButtons.Show(True)
            self.mainSizer.Add(self.ctrls.panelSavedSearchButtons, (1,0), (1,2),
                    flag=wx.ALL | wx.EXPAND | wx.ALIGN_CENTRE_VERTICAL,
                    border=5)
#             self.mainSizer.AddGrowableRow(1)
            self.ctrls.btnToggleExtended.SetLabel(_("<< Less"))

#         print "--OnToggleExtended13", repr(self.mainSizer.CalcMin())
        self.Layout()

        newSizerMin = self.mainSizer.CalcMin()

        self.SetMinSize((winMin.GetWidth() - oldSizerMin.GetWidth() +
                newSizerMin.GetWidth(),
                winMin.GetHeight() - oldSizerMin.GetHeight() +
                newSizerMin.GetHeight()))
        
        self.SetSize((winCurr.GetWidth() - oldSizerMin.GetWidth() +
                newSizerMin.GetWidth(),
                winCurr.GetHeight() - oldSizerMin.GetHeight() +
                newSizerMin.GetHeight()))


    def _buildSearchReplaceOperation(self):
        sarOp = SearchReplaceOperation()
        sarOp.searchStr = stripSearchString(self.ctrls.cbSearch.GetValue())
        sarOp.replaceStr = self.ctrls.txtReplace.GetValue()
        sarOp.replaceOp = True
        sarOp.booleanOp = False
        sarOp.caseSensitive = self.ctrls.cbCaseSensitive.GetValue()
        sarOp.wholeWord = self.ctrls.cbWholeWord.GetValue()
        sarOp.cycleToStart = False
        
        if self.ctrls.cbRegEx.GetValue():
            sarOp.wildCard = 'regex'
        else:
            sarOp.wildCard = 'no'

        sarOp.wikiWide = False

        return sarOp


    def showSearchReplaceOperation(self, sarOp):
        """
        Load settings from search operation into controls
        """
        self.ctrls.cbSearch.SetValue(sarOp.searchStr)
        self.ctrls.txtReplace.SetValue(sarOp.replaceStr)
        self.ctrls.cbCaseSensitive.SetValue(sarOp.caseSensitive)
        self.ctrls.cbWholeWord.SetValue(sarOp.wholeWord)
        self.ctrls.cbRegEx.SetValue(sarOp.wildCard == 'regex')



    def buildHistoryTuple(self):
        """
        Build a tuple for the search history from current settings
        """
        return (
                self.ctrls.cbSearch.GetValue(),
                self.ctrls.txtReplace.GetValue(),
                bool(self.ctrls.cbCaseSensitive.GetValue()),
                bool(self.ctrls.cbWholeWord.GetValue()),
                bool(self.ctrls.cbRegEx.GetValue())
                )


    def showHistoryTuple(self, tpl):
        """
        Load settings from history tuple into controls
        """
        self.ctrls.cbSearch.SetValue(tpl[0])
        self.ctrls.txtReplace.SetValue(tpl[1])
        self.ctrls.cbCaseSensitive.SetValue(bool(tpl[2]))
        self.ctrls.cbWholeWord.SetValue(bool(tpl[3]))
        self.ctrls.cbRegEx.SetValue(bool(tpl[4]))


    def addCurrentToHistory(self):
        tpl = self.buildHistoryTuple()
        hist = wx.GetApp().getPageSearchHistory()
        try:
            pos = hist.index(tpl)
            del hist[pos]
            hist.insert(0, tpl)
        except ValueError:
            # tpl not in hist
            hist.insert(0, tpl)
            if len(hist) > 10:
                hist = hist[:10]
            
        wx.GetApp().setPageSearchHistory(hist)
#         self.ctrls.cbSearch.Clear()
#         self.ctrls.cbSearch.AppendItems([tpl[0] for tpl in hist])

        self.ctrls.cbSearch.Freeze()
        try:
            text = self.ctrls.cbSearch.GetValue()
            self._refreshSearchHistoryCombo()
            self.ctrls.cbSearch.SetValue(text)
        finally:
            self.ctrls.cbSearch.Thaw()


    def _refreshSavedSearchesList(self):
        wikiData = self.mainControl.getWikiData()
        unifNames = wikiData.getDataBlockUnifNamesStartingWith("savedpagesearch/")

        result = []
#         suppExTypes = PluginManager.getSupportedExportTypes(mainControl,
#                     None, continuousExport)

        for un in unifNames:
            name = un[16:]
            content = wikiData.retrieveDataBlock(un)
            xmlDoc = minidom.parseString(content)
            xmlNode = xmlDoc.firstChild
#             etype = Serialization.serFromXmlUnicode(xmlNode, u"exportTypeName")
#             if etype not in suppExTypes:
#                 # Export type of saved export not supported
#                 continue

            result.append((name, xmlNode))
    
        self.mainControl.getCollator().sortByFirst(result)
    
        self.savedSearches = result

        self.ctrls.lbSavedSearches.Clear()
        for search in self.savedSearches:
            self.ctrls.lbSavedSearches.Append(search[0])



    def _refreshSearchHistoryCombo(self):
        hist = wx.GetApp().getPageSearchHistory()
        self.ctrls.cbSearch.Clear()
        self.ctrls.cbSearch.AppendItems([tpl[0] for tpl in hist])


    def OnDeleteSearches(self, evt):
        sels = self.ctrls.lbSavedSearches.GetSelections()
        
        if len(sels) == 0:
            return
            
        answer = wx.MessageBox(
                _("Do you want to delete %i search(es)?") % len(sels),
                _("Delete search"),
                wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION, self)
        if answer != wx.YES:
            return

        for s in sels:
#             self.mainControl.getWikiData().deleteSavedSearch(self.savedSearches[s])
            self.mainControl.getWikiData().deleteDataBlock(
                    "savedpagesearch/" + self.savedSearches[s][0])
        self._refreshSavedSearchesList()


    def OnLoadSearch(self, evt):
        self._loadSearch()
        
#     def OnLoadAndRunSearch(self, evt):
#         if self._loadSearch():
#             try:
#                 self._refreshPageList()
#             except UserAbortException:
#                 return
#             except re.error, e:
#                 self.displayErrorMessage(_(u'Error in regular expression'),
#                         _(unicode(e)))
#             except ParseException, e:
#                 self.displayErrorMessage(_(u'Error in boolean expression'),
#                         _(unicode(e)))
#             except DbReadAccessError, e:
#                 self.displayErrorMessage(_(u'Error. Maybe wiki rebuild is needed'),
#                         _(unicode(e)))


    def _loadSearch(self):
        sels = self.ctrls.lbSavedSearches.GetSelections()
        
        if len(sels) != 1:
            return False
        
        xmlNode = self.savedSearches[sels[0]][1]

        sarOp = SearchReplaceOperation()
        sarOp.serializeFromXml(xmlNode)
        self.showSearchReplaceOperation(sarOp)
        
        return True


    # TODO Store search mode
    def OnSaveSearch(self, evt):
        sarOp = self._buildSearchReplaceOperation()
        try:
            sarOp.rebuildSearchOpTree()
        except re.error as e:
            self.mainControl.displayErrorMessage(_('Error in regular expression'),
                    _(str(e)))
            return
        except ParseException as e:
            self.mainControl.displayErrorMessage(_('Error in boolean expression'),
                    _(str(e)))
            return

        if len(sarOp.searchStr) > 0:
            title = sarOp.getTitle()
            while True:
                title = wx.GetTextFromUser(_("Title:"),
                        _("Choose search title"), title, self)
                if title == "":
                    return  # Cancel
                    
#                 if title in self.mainControl.getWikiData().getSavedSearchTitles():
                if ("savedpagesearch/" + title) in self.mainControl.getWikiData()\
                        .getDataBlockUnifNamesStartingWith(
                        "savedpagesearch/" + title):

                    answer = wx.MessageBox(
                            _("Do you want to overwrite existing search '%s'?") %
                            title, _("Overwrite search"),
                            wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION, self)
                    if answer != wx.YES:
                        continue

#                 self.mainControl.getWikiData().saveSearch(title,
#                         sarOp.getPackedSettings())

                xmlDoc = minidom.getDOMImplementation().createDocument(None,
                        None, None)
                xmlNode = xmlDoc.createElement("savedpagesearch")
                sarOp.serializeToXml(xmlNode, xmlDoc)
                
                xmlDoc.appendChild(xmlNode)
                content = xmlDoc.toxml("utf-8")
                xmlDoc.unlink()
                self.mainControl.getWikiData().storeDataBlock(
                        "savedpagesearch/" + title, content,
                        storeHint=Consts.DATABLOCK_STOREHINT_INTERN)

                self._refreshSavedSearchesList()
                break
        else:
            self.mainControl.displayErrorMessage(
                    _("Invalid search string, can't save as view"))


    def displayErrorMessage(self, errorStr, e=""):
        """
        Pops up an error dialog box
        """
        wx.MessageBox("%s. %s." % (errorStr, e), _("Error!"),
            wx.OK, self)


    def _nextSearch(self, sarOp):
        editor = self.mainControl.getActiveEditor()
        if self.ctrls.rbSearchFrom.GetSelection() == 0:
            # Search from cursor
            contPos = editor.getContinuePosForSearch(sarOp)
        else:
            # Search from beginning
            contPos = 0
            self.ctrls.rbSearchFrom.SetSelection(0)
            
        self.addCurrentToHistory()
        start, end = editor.executeSearch(sarOp,
                contPos)[:2]
        if start == -1:
            # No matches found
            if contPos != 0:
                # We started not at beginning, so ask if to wrap around
                result = wx.MessageBox(_("End of document reached. "
                        "Continue at beginning?"),
                        _("Continue at beginning?"),
                        wx.YES_NO | wx.YES_DEFAULT | wx.ICON_QUESTION, self)
                if result != wx.YES:
                    return

                start, end = editor.executeSearch(
                        sarOp, 0)[:2]
                if start != -1:
                    return

            # no more matches possible -> show dialog
            wx.MessageBox(_("No matches found"),
                    _("No matches found"), wx.OK, self)


    def OnFindNext(self, evt):
        if self.ctrls.cbSearch.GetValue() == "":
            return

        sarOp = self._buildSearchReplaceOperation()
        sarOp.replaceOp = False
        self.addCurrentToHistory()
        try:
            self._nextSearch(sarOp)
            self.firstFind = False
        except re.error as e:
            self.displayErrorMessage(_('Error in regular expression'),
                    _(str(e)))


    def OnReplace(self, evt):
        sarOp = self._buildSearchReplaceOperation()
#         sarOp.replaceStr = guiToUni(self.ctrls.txtReplace.GetValue())
#         sarOp.replaceOp = True
        self.addCurrentToHistory()
        try:
            self.mainControl.getActiveEditor().executeReplace(sarOp)
            self._nextSearch(sarOp)
        except re.error as e:
            self.displayErrorMessage(_('Error in regular expression'),
                    _(str(e)))


    def OnReplaceAll(self, evt):
        sarOp = self._buildSearchReplaceOperation()
#         sarOp.replaceStr = guiToUni(self.ctrls.txtReplace.GetValue())
#         sarOp.replaceOp = True
        sarOp.cycleToStart = False
        lastSearchPos = 0
        editor = self.mainControl.getActiveEditor()
        self.addCurrentToHistory()
        replaceCount = 0
        editor.BeginUndoAction()
        try:
            while True:
                nextReplacePos = editor.executeSearch(sarOp, lastSearchPos)[1]
                if nextReplacePos == -1:
                    break
                replaceCount += 1
                nextSearchPos = editor.executeReplace(sarOp)
                if lastSearchPos == nextReplacePos:
                    # Otherwise it would run infinitely
                    break
                lastSearchPos = nextSearchPos
        finally:
            editor.EndUndoAction()
            
        wx.MessageBox(_("%i replacements done") % replaceCount,
                _("Replace All"), wx.OK, self)


    def OnSearchComboSelected(self, evt):
        hist = wx.GetApp().getPageSearchHistory()
        self.showHistoryTuple(hist[evt.GetSelection()])



class SearchWikiDialog(wx.Dialog, MiscEventSourceMixin):
    def __init__(self, parent, mainControl, ID, srListBox=None,
            allowOrdering=True, allowOkCancel=True, value=None,
            title="Search Wiki", pos=wx.DefaultPosition, size=wx.DefaultSize,
            style=wx.NO_3D|wx.DEFAULT_DIALOG_STYLE|wx.RESIZE_BORDER):

#         _prof.start()
        wx.Dialog.__init__(self)

        self.mainControl = mainControl

        res = wx.xrc.XmlResource.Get()
        res.LoadDialog(self, parent, "SearchWikiDialog")
        if srListBox is None:
            srListBox = SearchResultListBox(self, self.mainControl,
                    GUI_ID.htmllbPages)
        else:
            srListBox.Reparent(self)

        res.AttachUnknownControl("htmllbPages", srListBox, self)
        # Necessary to workaround a bug in layout mechanism
        srListBox.GetGrandParent().Layout()
        self.ctrls = XrcControls(self)

        self.allowOkCancel = allowOkCancel
        self.allowOrdering = allowOrdering
        if allowOkCancel:
            self.ctrls.btnOk.SetId(wx.ID_OK)
            self.ctrls.btnCancel.SetId(wx.ID_CANCEL)
        else:
            self.ctrls.btnOk.SetLabel(_("Close"))
            self.ctrls.btnOk.SetId(wx.ID_CANCEL)
            self.ctrls.btnCancel.Show(False)

        currWord = self.mainControl.getCurrentWikiWord()
        if currWord is not None:
            self.ctrls.tfPageListToAdd.SetValue(currWord)

        self.ctrls.cbSearch.SetWindowStyle(self.ctrls.cbSearch.GetWindowStyle()
                | wx.TE_PROCESS_ENTER)

        self.listNeedsRefresh = True  # Reflects listbox content current
                                      # search criteria?

        self.searchingStartTime = None

        self.savedSearches = None
        self.foundPages = []
        self.pageListData = []

        if not self.allowOrdering:
            self.ctrls.chOrdering.SetSelection(self._ORDERNAME_TO_CHOICE["no"])
            self.ctrls.chOrdering.Enable(False)

        self.ctrls.rboxSearchType.EnableItem(Consts.SEARCHTYPE_INDEX,
                self.mainControl.getWikiDocument() is not None and \
                self.mainControl.getWikiDocument().isSearchIndexEnabled())

        self.pageListRadioButtons = (self.ctrls.rbPagesAll,
                self.ctrls.rbPagesMatchRe, self.ctrls.rbPagesInList)

        self.panelPageListLastFocused = None  


        self._refreshSavedSearchesList()
        self._refreshSearchHistoryCombo()

        if value is not None:
            self.showSearchReplaceOperation(value)
        else:
            config = self.mainControl.getConfig()
            self.ctrls.rboxSearchType.SetSelection(config.getint("main",
                    "search_wiki_searchType", 0))
            self.ctrls.cbCaseSensitive.SetValue(config.getboolean("main",
                    "search_wiki_caseSensitive", False))
            self.ctrls.cbWholeWord.SetValue(config.getboolean("main",
                    "search_wiki_wholeWord", False))

            self.listPagesOperation = ListWikiPagesOperation()
            self._showListPagesOperation(self.listPagesOperation)

            self.OnRadioBox(None)  # Refresh settings
            self._updateTabTitle()
            
            
        # Fixes focus bug under Linux
        self.SetFocus()
        self.ctrls.cbSearch.SetFocus()

        # Events from text search tab
        self.Bind(wx.EVT_BUTTON, self.OnSearchWiki, id=GUI_ID.btnFindPages)
        self.Bind(wx.EVT_BUTTON, self.OnFindNext, id=GUI_ID.btnFindNext)        
        self.Bind(wx.EVT_BUTTON, self.OnReplace, id=GUI_ID.btnReplace)
        self.Bind(wx.EVT_BUTTON, self.OnReplaceAll, id=GUI_ID.btnReplaceAll)
        self.Bind(wx.EVT_BUTTON, self.OnSaveSearch, id=GUI_ID.btnSaveSearch)
        self.Bind(wx.EVT_BUTTON, self.OnDeleteSearches, id=GUI_ID.btnDeleteSearches)
        self.Bind(wx.EVT_BUTTON, self.OnLoadSearch, id=GUI_ID.btnLoadSearch)
        self.Bind(wx.EVT_BUTTON, self.OnLoadAndRunSearch, id=GUI_ID.btnLoadAndRunSearch)
        self.Bind(wx.EVT_BUTTON, self.OnOptions, id=GUI_ID.btnOptions)
        self.Bind(wx.EVT_BUTTON, self.OnCopyPageNamesToClipboard, id=GUI_ID.btnCopyPageNamesToClipboard)
        self.Bind(wx.EVT_BUTTON, self.OnCmdAsResultlist, id=GUI_ID.btnAsResultlist)
        self.Bind(wx.EVT_BUTTON, self.OnCmdAsTab, id=GUI_ID.btnAsTab)

        self.ctrls.cbSearch.Bind(wx.EVT_CHAR, self.OnCharToFind)
        self.ctrls.rboxSearchType.Bind(wx.EVT_CHAR, self.OnCharToFind)
        self.ctrls.cbCaseSensitive.Bind(wx.EVT_CHAR, self.OnCharToFind)
        self.ctrls.cbWholeWord.Bind(wx.EVT_CHAR, self.OnCharToFind)

        self.Bind(wx.EVT_COMBOBOX, self.OnSearchComboSelected, id=GUI_ID.cbSearch) 
        self.Bind(wx.EVT_LISTBOX_DCLICK, self.OnLoadAndRunSearch, id=GUI_ID.lbSavedSearches)
        self.Bind(wx.EVT_RADIOBOX, self.OnRadioBox, id=GUI_ID.rboxSearchType)

        self.Bind(wx.EVT_TEXT, self.OnListRefreshNeeded, id=GUI_ID.cbSearch)
        self.Bind(wx.EVT_CHECKBOX, self.OnListRefreshNeeded, id=GUI_ID.cbCaseSensitive)
        self.Bind(wx.EVT_CHECKBOX, self.OnListRefreshNeeded, id=GUI_ID.cbWholeWord)


        # Events from page list construction tab

        self.Bind(wx.EVT_TEXT, self.OnTextSubtreeLevels, id=GUI_ID.tfSubtreeLevels)
        self.Bind(wx.EVT_TEXT, self.OnTextPageNameMatchRe, id=GUI_ID.tfMatchRe)

        self.Bind(wx.EVT_RADIOBUTTON, self.OnPageListRadioButtons, id=GUI_ID.rbPagesAll)
        self.Bind(wx.EVT_RADIOBUTTON, self.OnPageListRadioButtons, id=GUI_ID.rbPagesMatchRe)
        self.Bind(wx.EVT_RADIOBUTTON, self.OnPageListRadioButtons, id=GUI_ID.rbPagesInList)

        self.Bind(wx.EVT_TEXT_ENTER, self.OnPageListAdd, id=GUI_ID.tfPageListToAdd)
        self.Bind(wx.EVT_BUTTON, self.OnPageListUp, id=GUI_ID.btnPageListUp) 
        self.Bind(wx.EVT_BUTTON, self.OnPageListDown, id=GUI_ID.btnPageListDown) 
        self.Bind(wx.EVT_BUTTON, self.OnPageListSort, id=GUI_ID.btnPageListSort) 

        self.Bind(wx.EVT_BUTTON, self.OnPageListAdd, id=GUI_ID.btnPageListAdd) 
        self.Bind(wx.EVT_BUTTON, self.OnPageListDelete, id=GUI_ID.btnPageListDelete) 
        self.Bind(wx.EVT_BUTTON, self.OnPageListClearList, id=GUI_ID.btnPageListClearList) 

        self.Bind(wx.EVT_BUTTON, self.OnPageListCopyToClipboard, id=GUI_ID.btnPageListCopyToClipboard) 

        self.Bind(wx.EVT_BUTTON, self.OnPageListAddFromClipboard, id=GUI_ID.btnPageListAddFromClipboard) 
        self.Bind(wx.EVT_BUTTON, self.OnPageListOverwriteFromClipboard, id=GUI_ID.btnPageListOverwriteFromClipboard)
        self.Bind(wx.EVT_BUTTON, self.OnPageListIntersectWithClipboard, id=GUI_ID.btnPageListIntersectWithClipboard) 

        self.Bind(wx.EVT_BUTTON, self.OnResultListPreview, id=GUI_ID.btnResultListPreview) 
        self.Bind(wx.EVT_BUTTON, self.OnResultCopyToClipboard, id=GUI_ID.btnResultCopyToClipboard) 


#         self.Bind(wx.EVT_BUTTON, self.OnClose, id=wx.ID_CANCEL)        
#         self.Bind(wx.EVT_CLOSE, self.OnClose)

        # Common events on OK, Close, Cancel
        self.Bind(wx.EVT_BUTTON, self.OnClose, id=wx.ID_CANCEL)        
        self.Bind(wx.EVT_CLOSE, self.OnClose)
        self.Bind(wx.EVT_BUTTON, self.OnOk, id=wx.ID_OK)
        
        
        self.ctrls.panelPageList.Bind(wx.EVT_CHILD_FOCUS, self.OnPageListChildFocus)
        
        
#         _prof.stop()
        



    _ORDERCHOICE_TO_NAME = {
            0: "natural",
            1: "ascending",
            2: "asroottree",
            3: "no"
    }

    _ORDERNAME_TO_CHOICE = {
            "natural": 0,
            "ascending": 1,
            "asroottree": 2,
            "no": 3
    }


    def setValue(self, value):
        self.value = value

    def getValue(self):
        return self.value


    def displayErrorMessage(self, errorStr, e=""):
        """
        Pops up an error dialog box
        """
        wx.MessageBox("%s. %s." % (errorStr, e), _("Error!"),
            wx.OK, self)


    def _buildListPagesOperation(self):
        """
        Construct a ListWikiPagesOperation according to current content of the
        second tab of the dialog
        """
        from . import SearchAndReplace as Sar
        
        lpOp = Sar.ListWikiPagesOperation()
        
        if self.ctrls.rbPagesAll.GetValue():
            item = Sar.AllWikiPagesNode(lpOp)
        elif self.ctrls.rbPagesMatchRe.GetValue():
            pattern = self.ctrls.tfMatchRe.GetValue()
            try:
                re.compile(pattern, re.DOTALL | re.UNICODE | re.MULTILINE)
            except re.error as e:
                wx.MessageBox(_("Bad regular expression '%s':\n%s") %
                        (pattern, _(str(e))), _("Error in regular expression"),
                        wx.OK, self)
                return None
                
            item = Sar.RegexWikiPageNode(lpOp, pattern)
        elif self.ctrls.rbPagesInList.GetValue():
            try:
                level = int(self.ctrls.tfSubtreeLevels.GetValue())
                if level < 0:
                    raise ValueError
            except ValueError:
                level = -1

            item = Sar.ListItemWithSubtreeWikiPagesNode(lpOp,
                    self.pageListData[:], level)
        else:
            return None

        lpOp.setSearchOpTree(item)
        lpOp.ordering = self._ORDERCHOICE_TO_NAME[
                self.ctrls.chOrdering.GetSelection()]

        return lpOp


    def OnPageListChildFocus(self, evt):
        self.panelPageListLastFocused = evt.GetEventObject()
        evt.Skip()


    def _buildSearchReplaceOperation(self):
        searchType = self.ctrls.rboxSearchType.GetSelection()
        
        sarOp = SearchReplaceOperation()
        sarOp.searchStr = stripSearchString(self.ctrls.cbSearch.GetValue())
        sarOp.booleanOp = searchType == Consts.SEARCHTYPE_BOOLEANREGEX
        
        sarOp.indexSearch = 'no' if searchType != Consts.SEARCHTYPE_INDEX \
                else 'default'
        sarOp.caseSensitive = self.ctrls.cbCaseSensitive.GetValue()
        sarOp.wholeWord = self.ctrls.cbWholeWord.GetValue()
        sarOp.cycleToStart = False
        sarOp.wildCard = 'regex' if searchType != Consts.SEARCHTYPE_ASIS else 'no'
        sarOp.wikiWide = True
        self.listPagesOperation = self._buildListPagesOperation()
        sarOp.listWikiPagesOp = self.listPagesOperation

        if not sarOp.booleanOp:
            sarOp.replaceStr = self.ctrls.txtReplace.GetValue()

        return sarOp


    def _showListPagesOperation(self, lpOp):
        if lpOp is not None:
            item = self.listPagesOperation.searchOpTree
            
            if item.CLASS_PERSID == "AllPages":
                self._setPageListRadioButton(self.ctrls.rbPagesAll)
            elif item.CLASS_PERSID == "RegexPage":
                self._setPageListRadioButton(self.ctrls.rbPagesMatchRe)
                self.ctrls.tfMatchRe.SetValue(item.getPattern())
            elif item.CLASS_PERSID == "ListItemWithSubtreePages":
                self._setPageListRadioButton(self.ctrls.rbPagesInList)
                self.pageListData = item.rootWords[:]
                self.ctrls.lbPageList.AppendItems(self.pageListData)
                if item.level == -1:
                    self.ctrls.tfSubtreeLevels.SetValue("")
                else:
                    self.ctrls.tfSubtreeLevels.SetValue("%i" % item.level)
                    
            self.ctrls.chOrdering.SetSelection(
                    self._ORDERNAME_TO_CHOICE[self.listPagesOperation.ordering])
            
            self._updateTabTitle()


    def showSearchReplaceOperation(self, sarOp):
        self.ctrls.cbSearch.SetValue(sarOp.searchStr)
        if sarOp.booleanOp:
            self.ctrls.rboxSearchType.SetSelection(Consts.SEARCHTYPE_BOOLEANREGEX)
        elif sarOp.indexSearch == 'default':
            if self.mainControl.getWikiDocument() is not None and \
                    self.mainControl.getWikiDocument().isSearchIndexEnabled():
                self.ctrls.rboxSearchType.SetSelection(Consts.SEARCHTYPE_INDEX)
            else:
                self.ctrls.rboxSearchType.SetSelection(Consts.SEARCHTYPE_BOOLEANREGEX)
        else:
            if sarOp.wildCard == 'regex':
                self.ctrls.rboxSearchType.SetSelection(Consts.SEARCHTYPE_REGEX)
            else:
                self.ctrls.rboxSearchType.SetSelection(Consts.SEARCHTYPE_ASIS)

        self.ctrls.cbCaseSensitive.SetValue(sarOp.caseSensitive)
        self.ctrls.cbWholeWord.SetValue(sarOp.wholeWord)

        if not sarOp.booleanOp and sarOp.replaceOp:
            self.ctrls.txtReplace.SetValue(sarOp.replaceStr)

        self.listPagesOperation = sarOp.listWikiPagesOp
        self._showListPagesOperation(self.listPagesOperation)

        self.OnRadioBox(None)  # Refresh settings
        self._updateTabTitle()


#     @profile
    def _refreshPageList(self):
        sarOp = self._buildSearchReplaceOperation()

        # If allowOkCancel is True, the dialog is used to create a set of pages
        # so process even for an empty search string
        if len(sarOp.searchStr) == 0 and not self.allowOkCancel:
            self.foundPages = []
            self.ctrls.htmllbPages.showFound(None, None, None)

            self.listNeedsRefresh = False
            return

        disableSet = wxHelper.getAllChildWindows(self)
        disableSet.difference_update(wxHelper.getWindowParentsUpTo(
                self.ctrls.htmllbPages, self))
        disableSet = set(win for win in disableSet if win.IsEnabled())

        self.ctrls.htmllbPages.showSearching()
        self.SetCursor(wx.HOURGLASS_CURSOR)
#         self.Freeze()

        self.searchingStartTime = time.time()

        if self.mainControl.configuration.getboolean("main",
                        "search_dontAllowCancel"):
            threadstop = DUMBTHREADSTOP
        else:
            threadstop = FunctionThreadStop(self._searchPoll)

        for win in disableSet:
            win.Disable()
        try:
            self.foundPages = self.mainControl.getWikiDocument().searchWiki(
                    sarOp, self.allowOrdering, threadstop=threadstop)
            if not self.allowOrdering:
                # Use default alphabetical ordering
                self.mainControl.getCollator().sort(self.foundPages)

            self.ctrls.htmllbPages.showFound(sarOp, self.foundPages,
                    self.mainControl.getWikiDocument(),
                    threadstop=threadstop)

            self.listNeedsRefresh = False

        except NotCurrentThreadException:
            raise UserAbortException()
        finally:
            self.searchingStartTime = None
            for win in disableSet:
                win.Enable()

            # "index" option in search type was enabled by the above operation
            # so disable again if necessary
            self.ctrls.rboxSearchType.EnableItem(Consts.SEARCHTYPE_INDEX,
                    self.mainControl.getWikiDocument() is not None and \
                    self.mainControl.getWikiDocument().isSearchIndexEnabled())

    #         self.Thaw()
            self.SetCursor(wx.NullCursor)
            self.ctrls.htmllbPages.ensureNotShowSearching()


    def _searchPoll(self):
        return wx.SafeYield(self, True) and self.searchingStartTime is not None

    def stopSearching(self):
        self.searchingStartTime = None


    def OnOk(self, evt):
        self.stopSearching()
        val = self._buildSearchReplaceOperation()
        self.value = val 
        if val is None:
            return

        try:
            self.mainControl.nonModalWwSearchDlgs.remove(self)
        except ValueError:
            if self is self.mainControl.nonModalMainWwSearchDlg:
                self.mainControl.nonModalMainWwSearchDlg = None

        if self.IsModal():
            self.EndModal(wx.ID_OK)
        else:
            self.Destroy()
#             self.fireMiscEventProps({"nonmodal closed": wx.ID_OK,
#                     "listWikiPagesOp": self.value})


    def OnClose(self, evt):
        self.stopSearching()

        self.value = None
        try:
            self.mainControl.nonModalWwSearchDlgs.remove(self)
        except ValueError:
            if self is self.mainControl.nonModalMainWwSearchDlg:
                self.mainControl.nonModalMainWwSearchDlg = None

        if self.IsModal():
            self.EndModal(wx.ID_CANCEL)
        else:
            self.Destroy()
#             self.fireMiscEventProps({"nonmodal closed": wx.ID_CANCEL,
#                     "listWikiPagesOp": None})

    def OnSearchWiki(self, evt):
        try:
            self._refreshPageList()
            self.addCurrentToHistory()
            if not self.ctrls.htmllbPages.IsEmpty():
                self.ctrls.htmllbPages.SetFocus()
                self.ctrls.htmllbPages.SetSelection(0)
        except UserAbortException:
            return
        except re.error as e:
            self.displayErrorMessage(_('Error in regular expression'),
                    _(str(e)))
        except ParseException as e:
            self.displayErrorMessage(_('Error in boolean expression'),
                    _(str(e)))
        except DbReadAccessError as e:
            self.displayErrorMessage(_('Error. Maybe wiki rebuild is needed'),
                    _(str(e)))
            return


    def OnListRefreshNeeded(self, evt):
        self.listNeedsRefresh = True
        self._updateTabTitle()

    def OnFindNext(self, evt):
        self._findNext()

    def _findNext(self):
        if self.listNeedsRefresh:
            try:
                # Refresh list and start from beginning
                self._refreshPageList()
            except UserAbortException:
                return
            except re.error as e:
                self.displayErrorMessage(_('Error in regular expression'),
                        _(str(e)))
                return
            except ParseException as e:
                self.displayErrorMessage(_('Error in boolean expression'),
                        _(str(e)))
                return
            except DbReadAccessError as e:
                self.displayErrorMessage(_('Error. Maybe wiki rebuild is needed'),
                        _(str(e)))
                return


        self.addCurrentToHistory()
        if self.ctrls.htmllbPages.GetCount() == 0:
            return
        
        try:
            while True:            
                    
                #########self.ctrls.lb.SetSelection(self.listPosNext)
                
                wikiWord = self.ctrls.htmllbPages.GetSelectedWord()
                
                if not wikiWord:
                    self.ctrls.htmllbPages.SetSelection(0)
                    wikiWord = self.ctrls.htmllbPages.GetSelectedWord()
    
                if self.mainControl.getCurrentWikiWord() != wikiWord:
                    self.mainControl.openWikiPage(wikiWord)
                    nextOnPage = False
                else:
                    nextOnPage = True
    
                searchOp = self._buildSearchReplaceOperation()
                searchOp.replaceOp = False
                if nextOnPage:
                    pagePosNext = self.mainControl.getActiveEditor().executeSearch(searchOp,
                            -2)[1]
                else:
                    pagePosNext = self.mainControl.getActiveEditor().executeSearch(searchOp,
                            0)[1]
                    
                if pagePosNext != -1:
                    return  # Found
                    
                if self.ctrls.htmllbPages.GetSelection() == \
                        self.ctrls.htmllbPages.GetCount() - 1:
                    # Nothing more found on the last page in list, so back to
                    # begin of list and stop
                    self.ctrls.htmllbPages.SetSelection(0)
                    return
                    
                # Otherwise: Go to next page in list            
                self.ctrls.htmllbPages.SetSelection(
                        self.ctrls.htmllbPages.GetSelection() + 1)
        except re.error as e:
            self.displayErrorMessage(_('Error in regular expression'),
                    _(str(e)))
        except ParseException as e:
            self.displayErrorMessage(_('Error in boolean expression'),
                    _(str(e)))



    def OnReplace(self, evt):
        sarOp = self._buildSearchReplaceOperation()
        sarOp.replaceOp = True
        try:
            self.mainControl.getActiveEditor().executeReplace(sarOp)
        except re.error as e:
            self.displayErrorMessage(_('Error in regular expression'),
                    _(str(e)))
            return
        except ParseException as e:  # Probably this can't happen
            self.displayErrorMessage(_('Error in boolean expression'),
                    _(str(e)))
            return


        self._findNext()


    def OnReplaceAll(self, evt):
        answer = wx.MessageBox(_("Replace all occurrences?"), _("Replace All"),
                wx.YES_NO | wx.NO_DEFAULT, self)

        if answer != wx.YES:
            return

        try:
            self._refreshPageList()

            if self.ctrls.htmllbPages.GetCount() == 0:
                return

            # self.pWiki.saveCurrentDocPage()

            sarOp = self._buildSearchReplaceOperation()
            sarOp.replaceOp = True
            
            # wikiData = self.pWiki.getWikiData()
            wikiDocument = self.mainControl.getWikiDocument()
            self.addCurrentToHistory()
            
            replaceCount = 0
    
            for i in range(self.ctrls.htmllbPages.GetCount()):
                self.ctrls.htmllbPages.SetSelection(i)
                wikiWord = self.ctrls.htmllbPages.GetSelectedWord()
                wikiPage = wikiDocument.getWikiPageNoError(wikiWord)
                text = wikiPage.getLiveTextNoTemplate()
                if text is None:
                    continue
    
                charStartPos = 0
    
                sarOp.beginWikiSearch(self.mainControl.getWikiDocument())
                try:
                    while True:
                        try:
                            found = sarOp.searchDocPageAndText(wikiPage, text,
                                    charStartPos)
                            start, end = found[:2]
                        except:
                            # Regex error -> Stop searching
                            return
                            
                        if start is None: break
                        
                        repl = sarOp.replace(text, found)
                        text = text[:start] + repl + text[end:]  # TODO Faster?
                        charStartPos = start + len(repl)
                        replaceCount += 1
                        if start == end:
                            # Otherwise replacing would go infinitely
                            break
                finally:
                    sarOp.endWikiSearch()

                wikiPage.replaceLiveText(text)
                    
            self._refreshPageList()
            
            wx.MessageBox(_("%i replacements done") % replaceCount,
                    _("Replace All"),
                wx.OK, self)        
        except UserAbortException:
            return
        except re.error as e:
            self.displayErrorMessage(_('Error in regular expression'),
                    _(str(e)))
        except ParseException as e:
            self.displayErrorMessage(_('Error in boolean expression'),
                    _(str(e)))
        except DbReadAccessError as e:
            self.displayErrorMessage(_('Error. Maybe wiki rebuild is needed'),
                    _(str(e)))


    def addCurrentToHistory(self):
        sarOp = self._buildSearchReplaceOperation()
        try:
            sarOp.rebuildSearchOpTree()
        except re.error:
            # Ignore silently
            return
        except ParseException as e:
            # This too
            return

        data = sarOp.getPackedSettings()
        tpl = (sarOp.searchStr, sarOp.getPackedSettings())
        hist = wx.GetApp().getWikiSearchHistory()
        try:
            pos = hist.index(tpl)
            del hist[pos]
            hist.insert(0, tpl)
        except ValueError:
            # tpl not in hist
            hist.insert(0, tpl)
            if len(hist) > 10:
                hist = hist[:10]
            
        wx.GetApp().setWikiSearchHistory(hist)
        text = self.ctrls.cbSearch.GetValue()
        self._refreshSearchHistoryCombo()
#         self.ctrls.cbSearch.Clear()
#         self.ctrls.cbSearch.AppendItems([tpl[0] for tpl in hist])
        self.ctrls.cbSearch.SetValue(text)



    # TODO Store search mode
    def OnSaveSearch(self, evt):
        sarOp = self._buildSearchReplaceOperation()
        try:
            sarOp.rebuildSearchOpTree()
        except re.error as e:
            self.mainControl.displayErrorMessage(_('Error in regular expression'),
                    _(str(e)))
            return
        except ParseException as e:
            self.mainControl.displayErrorMessage(_('Error in boolean expression'),
                    _(str(e)))
            return

        if len(sarOp.searchStr) > 0:
            title = sarOp.getTitle()
            while True:
                title = wx.GetTextFromUser(_("Title:"),
                        _("Choose search title"), title, self)
                if title == "":
                    return  # Cancel
                    
#                 if title in self.pWiki.getWikiData().getSavedSearchTitles():
                if ("savedsearch/" + title) in self.mainControl.getWikiData()\
                        .getDataBlockUnifNamesStartingWith(
                        "savedsearch/" + title):

                    answer = wx.MessageBox(
                            _("Do you want to overwrite existing search '%s'?") %
                            title, _("Overwrite search"),
                            wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION, self)
                    if answer != wx.YES:
                        continue

#                 self.pWiki.getWikiData().saveSearch(title,
#                         sarOp.getPackedSettings())
                self.mainControl.getWikiData().storeDataBlock(
                        "savedsearch/" + title, sarOp.getPackedSettings(),
                        storeHint=Consts.DATABLOCK_STOREHINT_INTERN)

                self._refreshSavedSearchesList()
                break
        else:
            self.mainControl.displayErrorMessage(
                    _("Invalid search string, can't save as view"))


    def OnRadioBox(self, evt):
        self.listNeedsRefresh = True
        booleanSearch = self.ctrls.rboxSearchType.GetSelection() in (1, 3)

        self.ctrls.txtReplace.Enable(not booleanSearch)
        self.ctrls.btnFindNext.Enable(not booleanSearch)
        self.ctrls.btnReplace.Enable(not booleanSearch)
        self.ctrls.btnReplaceAll.Enable(not booleanSearch)


    def OnOptions(self, evt):
        self.mainControl.showOptionsDialog("OptionsPageSearching")
#         dlg = SearchWikiOptionsDialog(self, self.GetParent(), -1)
#         dlg.CenterOnParent(wx.BOTH)
# 
#         dlg.ShowModal()
#         dlg.Destroy()


    def getResultListPositionTuple(self):
        return getRelativePositionTupleToAncestor(self.ctrls.htmllbPages, self)


    def OnCmdAsResultlist(self, evt):
        self.Hide()
        
        ownPos = self.GetPosition()
        oldRelBoxPos = self.getResultListPositionTuple()
        
        frame = FastSearchPopup(self.GetParent(), self.mainControl, -1,
                srListBox=self.ctrls.htmllbPages)
        frame.setSearchOp(self._buildSearchReplaceOperation())
        
        newRelBoxPos = frame.getResultListPositionTuple()

        # A bit math to ensure that result list in both windows is placed
        # at same position (looks more cool)
        otherPos = (ownPos[0] + oldRelBoxPos[0] - newRelBoxPos[0],
                ownPos[1] + oldRelBoxPos[1] - newRelBoxPos[1])
        
        setWindowPos(frame, pos=otherPos, fullVisible=True)
        self.mainControl.nonModalWwSearchDlgs.append(frame)
        frame.Show()
        self.Close()


    def OnCmdAsTab(self, evt):
        self.Hide()

        maPanel = self.mainControl.getMainAreaPanel()
        presenter = LayeredControlPanel(maPanel)
        subCtl = SearchResultPresenterControl(presenter, self.mainControl,
                self.GetParent(), -1, srListBox=self.ctrls.htmllbPages)
        presenter.setSubControl("search result list", subCtl)
        presenter.switchSubControl("search result list")
        maPanel.appendPresenterTab(presenter)
        subCtl.setSearchOp(self._buildSearchReplaceOperation())

        maPanel.showPresenter(presenter)
        self.Close()


#     def OnClose(self, evt):
#         try:
#             self.mainControl.nonModalWwSearchDlgs.remove(self)
#         except ValueError:
#             if self is self.mainControl.nonModalMainWwSearchDlg:
#                 self.mainControl.nonModalMainWwSearchDlg = None
# 
#         self.Destroy()


    def _refreshSavedSearchesList(self):
        unifNames = self.mainControl.getWikiData()\
                .getDataBlockUnifNamesStartingWith("savedsearch/")

        self.savedSearches = [name[12:] for name in unifNames]
        self.mainControl.getCollator().sort(self.savedSearches)

        self.ctrls.lbSavedSearches.Clear()
        for search in self.savedSearches:
            self.ctrls.lbSavedSearches.Append(search)


    def _refreshSearchHistoryCombo(self):
        hist = wx.GetApp().getWikiSearchHistory()
        self.ctrls.cbSearch.Clear()
        self.ctrls.cbSearch.AppendItems([tpl[0] for tpl in hist])


    def OnDeleteSearches(self, evt):
        sels = self.ctrls.lbSavedSearches.GetSelections()
        
        if len(sels) == 0:
            return
            
        answer = wx.MessageBox(
                _("Do you want to delete %i search(es)?") % len(sels),
                _("Delete search"),
                wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION, self)
        if answer != wx.YES:
            return

        for s in sels:
#             self.pWiki.getWikiData().deleteSavedSearch(self.savedSearches[s])
            self.mainControl.getWikiData().deleteDataBlock(
                    "savedsearch/" + self.savedSearches[s])
        self._refreshSavedSearchesList()


    def OnLoadSearch(self, evt):
        self._loadSearch()
        
    def OnLoadAndRunSearch(self, evt):
        if self._loadSearch():
            try:
                self._refreshPageList()
            except UserAbortException:
                return
            except re.error as e:
                self.displayErrorMessage(_('Error in regular expression'),
                        _(str(e)))
            except ParseException as e:
                self.displayErrorMessage(_('Error in boolean expression'),
                        _(str(e)))
            except DbReadAccessError as e:
                self.displayErrorMessage(_('Error. Maybe wiki rebuild is needed'),
                        _(str(e)))


    def _loadSearch(self):
        sels = self.ctrls.lbSavedSearches.GetSelections()
        
        if len(sels) != 1:
            return False
        
        datablock = self.mainControl.getWikiData().retrieveDataBlock(
                "savedsearch/" + self.savedSearches[sels[0]])

        sarOp = SearchReplaceOperation()
        sarOp.setPackedSettings(datablock)
        
        self.showSearchReplaceOperation(sarOp)
        
        return True


    def OnSearchComboSelected(self, evt):
        hist = wx.GetApp().getWikiSearchHistory()
        sarOp = SearchReplaceOperation()
        sarOp.setPackedSettings(hist[evt.GetSelection()][1])
        
        self.showSearchReplaceOperation(sarOp)
        self.ctrls.txtReplace.SetValue(sarOp.replaceStr)


    def OnCopyPageNamesToClipboard(self, evt):
        langHelper = wx.GetApp().createWikiLanguageHelper(
                self.mainControl.getWikiDefaultWikiLanguage())

        wordsText = "".join([
                langHelper.createAbsoluteLinksFromWikiWords((w,)) + "\n"
                for w in self.foundPages])

        copyTextToClipboard(wordsText)


    def OnTextSubtreeLevels(self, evt):
        self._setPageListRadioButton(self.ctrls.rbPagesInList)
        self._updateTabTitle()
        self.listNeedsRefresh = True

    def OnTextPageNameMatchRe(self, evt):
        self._setPageListRadioButton(self.ctrls.rbPagesMatchRe)
        self._updateTabTitle()
        self.listNeedsRefresh = True


    def OnCharToFind(self, evt):
        if (evt.GetKeyCode() in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER)):
            self.OnSearchWiki(evt)
        elif evt.GetKeyCode() == wx.WXK_TAB:
            if evt.ShiftDown():
                self.ctrls.cbSearch.Navigate(wx.NavigationKeyEvent.IsBackward | 
                        wx.NavigationKeyEvent.FromTab)
            else:
                self.ctrls.cbSearch.Navigate(wx.NavigationKeyEvent.IsForward | 
                        wx.NavigationKeyEvent.FromTab)
        else:
            evt.Skip()


    # Processing of events on second tab
    
    def _updateTabTitle(self):
        if self.ctrls.rbPagesAll.GetValue():
            self.ctrls.nbSearchWiki.SetPageText(1, _("Set page list"))
        else:
            self.ctrls.nbSearchWiki.SetPageText(1, _("*Set page list*"))            


    def _setPageListRadioButton(self, selectedBtn):
        refocus = False
        focused = self.panelPageListLastFocused
        
        for btn in self.pageListRadioButtons:
            if btn is selectedBtn:
                btn.SetValue(True)
            else:
                if btn is focused:
                    refocus = True

                btn.SetValue(False)
                
        if refocus:
            self.ctrls.panelPageList.ProcessEvent(wx.ChildFocusEvent(selectedBtn))



    def OnPageListRadioButtons(self, evt):
        self._setPageListRadioButton(evt.GetEventObject())
        
        self.OnListRefreshNeeded(evt)


    def OnPageListUp(self, evt):
        sel = self.ctrls.lbPageList.GetSelection()
        if sel == wx.NOT_FOUND or sel == 0:
            return
            
        self.listNeedsRefresh = True
            
        dispWord = self.ctrls.lbPageList.GetString(sel)
        word = self.pageListData[sel]
        
        self.ctrls.lbPageList.Delete(sel)
        del self.pageListData[sel]
        
        self.ctrls.lbPageList.Insert(dispWord, sel - 1)
        self.pageListData.insert(sel - 1, word)
        self.ctrls.lbPageList.SetSelection(sel - 1)
        
        
    def OnPageListDown(self, evt):
        sel = self.ctrls.lbPageList.GetSelection()
        if sel == wx.NOT_FOUND or sel == len(self.pageListData) - 1:
            return
            
        self.listNeedsRefresh = True

        dispWord = self.ctrls.lbPageList.GetString(sel)
        word = self.pageListData[sel]
        
        self.ctrls.lbPageList.Delete(sel)
        del self.pageListData[sel]
        
        self.ctrls.lbPageList.Insert(dispWord, sel + 1)
        self.pageListData.insert(sel + 1, word)
        self.ctrls.lbPageList.SetSelection(sel + 1)


    def OnPageListSort(self, evt):
        self._setPageListRadioButton(self.ctrls.rbPagesInList)
        self._updateTabTitle()
        self.listNeedsRefresh = True

        self.mainControl.getCollator().sort(self.pageListData)
        
        self.ctrls.lbPageList.Clear()
        self.ctrls.lbPageList.AppendItems(self.pageListData)


    def OnPageListAdd(self, evt):
        self._setPageListRadioButton(self.ctrls.rbPagesInList)
        self._updateTabTitle()

        word = self.ctrls.tfPageListToAdd.GetValue()

        langHelper = wx.GetApp().createWikiLanguageHelper(
                self.mainControl.getWikiDefaultWikiLanguage())
        word = langHelper.extractWikiWordFromLink(word,
                self.mainControl.getWikiDocument())
        if word is None:
            return

        if word in self.pageListData:
            return  # Already in list
        
        self.listNeedsRefresh = True

        sel = self.ctrls.lbPageList.GetSelection()
        if sel == wx.NOT_FOUND:
            self.ctrls.lbPageList.Append(word)
            self.pageListData.append(word)
            self.ctrls.lbPageList.SetSelection(len(self.pageListData) - 1)
        else:
            self.ctrls.lbPageList.Insert(word, sel + 1)
            self.pageListData.insert(sel + 1, word)
            self.ctrls.lbPageList.SetSelection(sel + 1)
            
        self.ctrls.tfPageListToAdd.SetValue("")


    def OnPageListDelete(self, evt):
        self._setPageListRadioButton(self.ctrls.rbPagesInList)
        self._updateTabTitle()

        sel = self.ctrls.lbPageList.GetSelection()
        if sel == wx.NOT_FOUND:
            return

        self.ctrls.lbPageList.Delete(sel)
        del self.pageListData[sel]
        
        count = len(self.pageListData)
        if count == 0:
            return
            
        self.listNeedsRefresh = True
        
        if sel >= count:
            sel = count - 1
        self.ctrls.lbPageList.SetSelection(sel)


    def OnPageListClearList(self, evt):
        self._setPageListRadioButton(self.ctrls.rbPagesInList)
        self._updateTabTitle()

        self.ctrls.lbPageList.Clear()
        self.pageListData = []
        self.listNeedsRefresh = True
        

    def OnPageListAddFromClipboard(self, evt):
        """
        Take wiki words from clipboard and enter them into the list
        """
        self._setPageListRadioButton(self.ctrls.rbPagesInList)
        self._updateTabTitle()

        text = getTextFromClipboard()
        if text:
            self.listNeedsRefresh = True
            pageAst = self.mainControl.getCurrentDocPage().parseTextInContext(text)
            wwNodes = pageAst.iterDeepByName("wikiWord")
            found = {}
            # First fill found with already existing entries
            for w in self.pageListData:
                found[w] = None

            for node in wwNodes:
                w = node.wikiWord
                if w not in found:
                    self.ctrls.lbPageList.Append(w)
                    self.pageListData.append(w)
                    found[w] = None


    def OnPageListOverwriteFromClipboard(self, evt):
        self.ctrls.lbPageList.Clear()
        self.listNeedsRefresh = True
        self.pageListData = []
        
        self.OnPageListAddFromClipboard(evt)


    def OnPageListIntersectWithClipboard(self, evt):
        """
        Take wiki words from clipboard and intersect with the list
        """
        self._setPageListRadioButton(self.ctrls.rbPagesInList)
        self._updateTabTitle()

        text = getTextFromClipboard()
        
        if text:
            self.listNeedsRefresh = True
            pageAst = self.mainControl.getCurrentDocPage().parseTextInContext(text)
            wwNodes = pageAst.iterDeepByName("wikiWord")
            found = {}

            for node in wwNodes:
                w = node.wikiWord
                found[w] = None

            pageList = self.pageListData
            self.pageListData = []
            self.ctrls.lbPageList.Clear()

            # Now fill all with already existing entries
            for w in pageList:
                if w in found:
                    self.ctrls.lbPageList.Append(w)
                    self.pageListData.append(w)
                    del found[w]


    def OnPageListCopyToClipboard(self, evt):
        langHelper = wx.GetApp().createWikiLanguageHelper(
                self.mainControl.getWikiDefaultWikiLanguage())

        wordsText = "".join([
                langHelper.createAbsoluteLinksFromWikiWords((w,)) + "\n"
                for w in self.pageListData])

        copyTextToClipboard(wordsText)


    def OnResultCopyToClipboard(self, evt):
        langHelper = wx.GetApp().createWikiLanguageHelper(
                self.mainControl.getWikiDefaultWikiLanguage())

        wordsText = "".join([
                langHelper.createAbsoluteLinksFromWikiWords((w,)) + "\n"
                for w in self.resultListData])

        copyTextToClipboard(wordsText)


    def OnResultListPreview(self, evt):
        lpOp = self._buildListPagesOperation()

        if lpOp is None:
            return

        sarOp = SearchReplaceOperation()
        sarOp.listWikiPagesOp = lpOp

        self.SetCursor(wx.HOURGLASS_CURSOR)
        self.Freeze()
        try:
            words = self.mainControl.getWikiDocument().searchWiki(sarOp)
            
            self.ctrls.lbResultPreview.Clear()
            self.ctrls.lbResultPreview.AppendItems(words)
                
            self.resultListData = words
        finally:
            self.Thaw()
            self.SetCursor(wx.NullCursor)



class SearchResultPresenterControl(wx.Panel):
    """
    Panel which can be added to presenter in main area panel as tab showing
    search results.
    """
    def __init__(self, presenter, mainControl, searchDialogParent, ID,
            srListBox=None):
        super(SearchResultPresenterControl, self).__init__(presenter, ID)

        self.mainControl = mainControl
        self.presenter = presenter
        self.searchDialogParent = searchDialogParent
        self.sarOp = None

        if srListBox is None:
            self.resultBox = SearchResultListBox(self, self.mainControl,
                    GUI_ID.htmllbPages)
        else:
            srListBox.Reparent(self)
            self.resultBox = srListBox

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.resultBox, 1, wx.EXPAND)


        buttonSizer = wx.BoxSizer(wx.HORIZONTAL)

        self.btnAsResultlist = wx.Button(self,
                GUI_ID.CMD_SEARCH_AS_RESULTLIST, label=_("As Resultlist"))
                # TODO Allow hotkey for button
        buttonSizer.Add(self.btnAsResultlist, 0, wx.EXPAND)

        self.btnAsWwSearch = wx.Button(self, GUI_ID.CMD_SEARCH_AS_WWSEARCH,
                label=_("As Full Search"))    # TODO Allow hotkey for button
        buttonSizer.Add(self.btnAsWwSearch, 0, wx.EXPAND)

#         buttonSizer.AddStretchSpacer()
        buttonSizer.Add((0, 0), 1)

        res = wx.xrc.XmlResource.Get()
        self.tabContextMenu = res.LoadMenu("MenuSearchResultTabPopup")
        

        sizer.Add(buttonSizer, 0, wx.EXPAND)

        self.SetSizer(sizer)

        self.Bind(wx.EVT_BUTTON, self.OnCmdAsResultlist, id=GUI_ID.CMD_SEARCH_AS_RESULTLIST)
        self.Bind(wx.EVT_BUTTON, self.OnCmdAsWwSearch, id=GUI_ID.CMD_SEARCH_AS_WWSEARCH)

        self.tabContextMenu.Bind(wx.EVT_MENU, self.OnCmdAsResultlist, id=GUI_ID.CMD_SEARCH_AS_RESULTLIST)
        self.tabContextMenu.Bind(wx.EVT_MENU, self.OnCmdAsWwSearch, id=GUI_ID.CMD_SEARCH_AS_WWSEARCH)


    # Next two to fulfill presenter subcontrol protocol
    def close(self):
        pass

    def setLayerVisible(self, vis, scName):
        pass


    def setSearchOp(self, sarOp):
        """
        """
        self.sarOp = sarOp
        self.presenter.setTitle(_("<Search: %s>") % self.sarOp.searchStr)


    def getTabContextMenu(self):
        return self.tabContextMenu


    def OnCmdAsResultlist(self, evt):
        self.mainControl.getMainAreaPanel().detachPresenterTab(self.presenter)

        frame = FastSearchPopup(self.searchDialogParent, self.mainControl,
                -1, srListBox=self.resultBox)

        self.mainControl.nonModalWwSearchDlgs.append(frame)
        frame.setSearchOp(self.sarOp)
        frame.fixate()
        frame.Show()

        self.presenter.close()
        self.presenter.Destroy()


    def OnCmdAsWwSearch(self, evt):
        self.mainControl.getMainAreaPanel().detachPresenterTab(self.presenter)

        dlg = SearchWikiDialog(self.searchDialogParent, self.mainControl, -1,
                srListBox=self.resultBox, allowOkCancel=False,
                allowOrdering=False)
        dlg.showSearchReplaceOperation(self.sarOp)

        self.mainControl.nonModalWwSearchDlgs.append(dlg)
        dlg.Show()

        self.presenter.close()
        self.presenter.Destroy()

#         # Set focus to dialog (hackish)
#         wx.CallLater(100, dlg.SetFocus)




class FastSearchPopup(wx.Frame):
    """
    Popup window which appears when hitting Enter in the fast search text field
    in the main window.
    Using frame because wx.PopupWindow is not available on Mac OS
    """
    def __init__(self, parent, mainControl, ID, srListBox=None,
            pos=wx.DefaultPosition):
        wx.Frame.__init__(self, parent, ID, _("Fast Search"), pos=pos,
                style=wx.RESIZE_BORDER | wx.FRAME_FLOAT_ON_PARENT | wx.SYSTEM_MENU |
                wx.FRAME_TOOL_WINDOW | wx.CAPTION | wx.CLOSE_BOX ) # wx.FRAME_NO_TASKBAR)
                
        self.mainControl = mainControl
        self.sarOp = None
        self.fixed = False  # if window was moved, fix it to not close automatically 

        if srListBox is None:
            self.resultBox = SearchResultListBox(self, self.mainControl,
                    GUI_ID.htmllbPages)
        else:
            srListBox.Reparent(self)
            self.resultBox = srListBox

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.resultBox, 1, wx.EXPAND)


        buttonSizer = wx.BoxSizer(wx.HORIZONTAL)

        self.btnAsWwSearch = wx.Button(self, GUI_ID.CMD_SEARCH_AS_WWSEARCH,
                label=_("As Full Search"))    # TODO Allow hotkey for button
        buttonSizer.Add(self.btnAsWwSearch, 0, wx.EXPAND)

        self.btnAsTab = wx.Button(self, GUI_ID.CMD_SEARCH_AS_TAB,
                label=_("As Tab"))    # TODO Allow hotkey for button
        buttonSizer.Add(self.btnAsTab, 0, wx.EXPAND)
#         buttonSizer.AddStretchSpacer()
        buttonSizer.Add((0, 0), 1)

        sizer.Add(buttonSizer, 0, wx.EXPAND)

        self.SetSizer(sizer)

        config = self.mainControl.getConfig()
        width = config.getint("main", "fastSearch_sizeX", 200)
        height = config.getint("main", "fastSearch_sizeY", 400)

        setWindowSize(self, (width, height))
        setWindowPos(self, fullVisible=True)

        # Fixes focus bug under Linux
        self.resultBox.SetFocus()
        
        self.resultBox.getMiscEvent().addListener(self)

#         self.Bind(wx.EVT_BUTTON, self.OnCloseMe, button)

        self.resultBox.Bind(wx.EVT_KILL_FOCUS, self.OnKillFocus)
        self.btnAsWwSearch.Bind(wx.EVT_KILL_FOCUS, self.OnKillFocus)
        self.btnAsTab.Bind(wx.EVT_KILL_FOCUS, self.OnKillFocus)
        self.Bind(wx.EVT_KILL_FOCUS, self.OnKillFocus)
#         self.resultBox.Bind(wx.EVT_KILL_FOCUS, self.OnKillFocus)
        self.Bind(wx.EVT_BUTTON, self.OnCmdAsWwSearch, id=GUI_ID.CMD_SEARCH_AS_WWSEARCH)
        self.Bind(wx.EVT_BUTTON, self.OnCmdAsTab, id=GUI_ID.CMD_SEARCH_AS_TAB)
        self.Bind(wx.EVT_CLOSE, self.OnClose)
        self.resultBox.Bind(wx.EVT_KEY_DOWN, self.OnKeyDown)
#         self.Bind(wx.EVT_LEFT_DOWN, self.OnLeftDown)
        
        # To avoid unwanted move events (resulting in calls to fixate)      
        wx.CallAfter(self.Bind, wx.EVT_MOVE, self.OnMove)


    def fixate(self):
        if self.fixed:
            return
        
        self.resultBox.Unbind(wx.EVT_KILL_FOCUS)
        self.btnAsWwSearch.Unbind(wx.EVT_KILL_FOCUS)
        self.Unbind(wx.EVT_MOVE)
        self.SetTitle(_("Search: %s") % self.sarOp.searchStr)
        self.fixed = True
        

    def OnMove(self, evt):
        evt.Skip()
        self.fixate()


    def getResultListPositionTuple(self):
        return getRelativePositionTupleToAncestor(self.resultBox, self)


    def OnCmdAsWwSearch(self, evt):
        self.Hide()
        self.fixate()

        ownPos = self.GetPosition()
        oldRelBoxPos = self.getResultListPositionTuple()

        dlg = SearchWikiDialog(self.GetParent(), self.mainControl, -1,
                srListBox=self.resultBox, allowOkCancel=False,
                allowOrdering=False)
        dlg.showSearchReplaceOperation(self.sarOp)

        newRelBoxPos = dlg.getResultListPositionTuple()

        # A bit math to ensure that result list in both windows is placed
        # at same position (looks more cool)
        otherPos = (ownPos[0] + oldRelBoxPos[0] - newRelBoxPos[0],
                ownPos[1] + oldRelBoxPos[1] - newRelBoxPos[1])

        setWindowPos(dlg, pos=otherPos, fullVisible=True)
        self.mainControl.nonModalWwSearchDlgs.append(dlg)
        self.Close()
        dlg.Show()

        # Set focus to dialog (hackish)
        wx.CallLater(100, dlg.SetFocus)


    def OnCmdAsTab(self, evt):
        self.Hide()
        self.fixate()

        maPanel = self.mainControl.getMainAreaPanel()
        presenter = LayeredControlPanel(maPanel)
        subCtl = SearchResultPresenterControl(presenter, self.mainControl,
                self.GetParent(), -1, srListBox=self.resultBox)
        presenter.setSubControl("search result list", subCtl)
        presenter.switchSubControl("search result list")
        maPanel.appendPresenterTab(presenter)
        subCtl.setSearchOp(self.sarOp)

        maPanel.showPresenter(presenter)
        self.Close()
        
    
    def miscEventHappened(self, miscevt):
        if miscevt.getSource() is self.resultBox and "opened in foreground" in miscevt:

            if not self.fixed:
                self.Close()

        
    def displayErrorMessage(self, errorStr, e=""):
        """
        Pops up an error dialog box
        """
        wx.MessageBox("%s. %s." % (errorStr, e), "Error!",
            wx.OK, self)


    def OnKeyDown(self, evt):
        accP = getAccelPairFromKeyDown(evt)

        if accP == (wx.ACCEL_NORMAL, wx.WXK_ESCAPE):
            self.Close()
        else:
            evt.Skip()


    # def OnKillFocus(self, evt):

    # TODO What about Mac?
    if isLinux():
        def OnKillFocus(self, evt):
            evt.Skip()
            
            if self.resultBox.contextMenuSelection == -2 and \
                    not wx.Window.FindFocus() in \
                    (None, self.resultBox, self.btnAsWwSearch, self.btnAsTab):
                # Close only if context menu is not open
                # otherwise crashes on GTK
                self.Close()
    else:
        def OnKillFocus(self, evt):
            evt.Skip()
            if not wx.Window.FindFocus() in (self.resultBox, self.btnAsWwSearch,
                    self.btnAsTab):
                self.Close()


    def OnClose(self, evt):
        if not self.fixed:
            width, height = self.GetSize()
            config = self.mainControl.getConfig()
            config.set("main", "fastSearch_sizeX", str(width))
            config.set("main", "fastSearch_sizeY", str(height))
        
        try:
            self.mainControl.nonModalWwSearchDlgs.remove(self)
        except ValueError:
            pass

        evt.Skip()


    def _buildSearchReplaceOperation(self, searchText):
        config = self.mainControl.getConfig()
        
        searchType = config.getint("main", "fastSearch_searchType")

        # TODO Make configurable
        sarOp = SearchReplaceOperation()
        sarOp.searchStr = stripSearchString(searchText)
        sarOp.booleanOp = searchType == Consts.SEARCHTYPE_BOOLEANREGEX
        sarOp.caseSensitive = config.getboolean("main",
                "fastSearch_caseSensitive")
        sarOp.wholeWord = config.getboolean("main", "fastSearch_wholeWord")
        sarOp.cycleToStart = False
        sarOp.wildCard = 'regex' if searchType != Consts.SEARCHTYPE_ASIS else 'no'
        sarOp.wikiWide = True

        return sarOp


    def runSearchOnWiki(self, text):
        self.setSearchOp(self._buildSearchReplaceOperation(text))
        try:
            self._refreshPageList()
        except UserAbortException:
            return
        except re.error as e:
            self.displayErrorMessage(_('Error in regular expression'),
                    _(str(e)))
        except ParseException as e:
            self.displayErrorMessage(_('Error in boolean expression'),
                    _(str(e)))
        except DbReadAccessError as e:
            self.displayErrorMessage(_('Error. Maybe wiki rebuild is needed'),
                    _(str(e)))


    def setSearchOp(self, sarOp):
        """
        """
        self.sarOp = sarOp


#     def _refreshPageList(self):
#         self.resultBox.showSearching()
#         self.SetCursor(wx.HOURGLASS_CURSOR)
#         self.Freeze()
#         try:
#             # self.mainControl.saveCurrentDocPage()
#     
#             if len(self.sarOp.searchStr) > 0:
#                 self.foundPages = self.mainControl.getWikiDocument().searchWiki(self.sarOp)
#                 self.mainControl.getCollator().sort(self.foundPages)
#                 self.resultBox.showFound(self.sarOp, self.foundPages,
#                         self.mainControl.getWikiDocument())
#             else:
#                 self.foundPages = []
#                 self.resultBox.showFound(None, None, None)
# 
#             self.listNeedsRefresh = False
# 
#         finally:
#             self.Thaw()
#             self.SetCursor(wx.NullCursor)
#             self.resultBox.ensureNotShowSearching()


    def _refreshPageList(self):
        if len(self.sarOp.searchStr) == 0:
            self.foundPages = []
            self.resultBox.showFound(None, None, None)

            self.listNeedsRefresh = False
            return

        disableSet = wxHelper.getAllChildWindows(self)
        disableSet.difference_update(wxHelper.getWindowParentsUpTo(
                self.resultBox, self))
        disableSet = set(win for win in disableSet if win.IsEnabled())

        self.resultBox.showSearching()
        self.SetCursor(wx.HOURGLASS_CURSOR)
#         self.Freeze()

        if self.mainControl.configuration.getboolean("main",
                        "search_dontAllowCancel"):
            threadstop = DUMBTHREADSTOP
        else:
            threadstop = FunctionThreadStop(self._searchPoll)

        self.searchingStartTime = time.time()
        for win in disableSet:
            win.Disable()
        try:
            self.foundPages = self.mainControl.getWikiDocument().searchWiki(
                    self.sarOp, threadstop=threadstop)
            self.mainControl.getCollator().sort(self.foundPages)
            self.resultBox.showFound(self.sarOp, self.foundPages,
                    self.mainControl.getWikiDocument(),
                    threadstop=threadstop)

            self.listNeedsRefresh = False

        except NotCurrentThreadException:
            raise UserAbortException()
        finally:
            self.searchingStartTime = None
            for win in disableSet:
                win.Enable()
    
    #         self.Thaw()
            self.SetCursor(wx.NullCursor)
            self.resultBox.ensureNotShowSearching()


    def _searchPoll(self):
        return wx.SafeYield(self, True) and self.searchingStartTime is not None

    def stopSearching(self):
        self.searchingStartTime = None





_CONTEXT_MENU_ACTIVATE = \
"""
Activate;CMD_ACTIVATE_THIS
Activate New Tab;CMD_ACTIVATE_NEW_TAB_THIS
Activate New Tab Backgrd.;CMD_ACTIVATE_NEW_TAB_BACKGROUND_THIS
"""

# Entries to support i18n of context menus
if False:
    N_("Activate")
    N_("Activate New Tab")
    N_("Activate New Tab Backgrd.")
