import sys, traceback, re

from wxPython.wx import *
from wxPython.html import *
import wxPython.xrc as xrc

from MiscEvent import MiscEventSourceMixin, KeyFunctionSink
from wxHelper import *

from StringOps import uniToGui, guiToUni, escapeHtml

from WindowLayout import setWindowPos, setWindowSize

import WikiFormatting
import PageAst

from SearchAndReplace import SearchReplaceOperation, ListWikiPagesOperation


class SearchWikiOptionsDialog(wxDialog):
    def __init__(self, parent, pWiki, ID=-1, title="Search Wiki",
                 pos=wxDefaultPosition, size=wxDefaultSize,
                 style=wxNO_3D|wxDEFAULT_DIALOG_STYLE|wxRESIZE_BORDER):
        d = wxPreDialog()
        self.PostCreate(d)

        self.pWiki = pWiki

        res = xrc.wxXmlResource.Get()
        res.LoadOnDialog(self, parent, "SearchWikiOptionsDialog")

        self.ctrls = XrcControls(self)
        
        before = unicode(self.pWiki.configuration.getint("main",
                "search_wiki_context_before"))
        after = unicode(self.pWiki.configuration.getint("main",
                "search_wiki_context_after"))
                
        self.ctrls.tfContextBefore.SetValue(uniToGui(before))
        self.ctrls.tfContextAfter.SetValue(uniToGui(after))
        self.ctrls.cbCountOccurrences.SetValue(
                self.pWiki.configuration.getboolean("main",
                "search_wiki_count_occurrences"))

        self.ctrls.btnOk.SetId(wxID_OK)
        self.ctrls.btnCancel.SetId(wxID_CANCEL)

        EVT_BUTTON(self, wxID_OK, self.OnOk)


    def OnOk(self, evt):
        # If a text field contains an invalid value, its background becomes red
        try:
            self.ctrls.tfContextBefore.SetBackgroundColour(wxRED)
            before = int(self.ctrls.tfContextBefore.GetValue())
            if before < 0: raise Exception
            self.ctrls.tfContextBefore.SetBackgroundColour(wxWHITE)

            self.ctrls.tfContextAfter.SetBackgroundColour(wxRED)
            after = int(self.ctrls.tfContextAfter.GetValue())
            if after < 0: raise Exception
            self.ctrls.tfContextAfter.SetBackgroundColour(wxWHITE)

            self.pWiki.configuration.set("main",
                "search_wiki_context_before", before)
            self.pWiki.configuration.set("main",
                "search_wiki_context_after", after)
            self.pWiki.configuration.set("main",
                "search_wiki_count_occurrences",
                self.ctrls.cbCountOccurrences.GetValue())
        except:
            self.Refresh()
            return

        self.EndModal(wxID_OK)



class _SearchResultItemInfo(object):
    __slots__ = ("__weakref__", "wikiWord", "occCount", "occNumber", "occHtml",
            "occPos", "html")
    
    def __init__(self, wikiWord, occPos = (-1, -1), occCount = -1):
        self.wikiWord = wikiWord
        if occPos[0] != -1:
            self.occNumber = 1
        else:
            self.occNumber = -1  # -1: No specific occurrence

        self.occHtml = u""  # HTML presentation of the occurrence
        self.occPos = occPos  # Tuple (start, end) with position of occurrence in characters
        self.occCount = occCount # -1: Undefined
        self.html = None
        
        
    def buildOccurrence(self, text, before, after, pos, occNumber):
        self.html = None
        basum = before + after
        self.occNumber = -1
        self.occPos = pos
        if basum == 0:
            # No context
            self.occHtml = u""
            return self
            
        if pos[0] == -1:
            # No position -> use beginning of text
            self.occHtml = escapeHtml(text[0:basum])
            return self
        
        s = max(0, pos[0] - before)
        e = min(len(text), pos[1] + after)
        self.occHtml = u"".join([escapeHtml(text[s:pos[0]]), 
            "<b>", escapeHtml(text[pos[0]:pos[1]]), "</b>",
            escapeHtml(text[pos[1]:e])])
            
        self.occNumber = occNumber
        return self


    def getHtml(self):
        if self.html is None:
            result = [u'<table><tr><td bgcolor="#0000ff" width="6"></td>'
                    u'<td><font color="BLUE"><b>%s</b></font>' % \
                    escapeHtml(self.wikiWord)]
            
            if self.occNumber != -1:
                stroc = [unicode(self.occNumber), u"/"]
            else:
                stroc = []
                
            if self.occCount != -1:
                stroc.append(unicode(self.occCount))
            elif len(stroc) > 0:
                stroc.append(u"?")
                
            stroc = u"".join(stroc)
            
            if stroc != u"":
                result.append(u' <b>(%s)</b>' % stroc)
                
#             if self.occCount != -1:
#                 result.append(u' <b>(%i/%i)</b>' % (self.occNumber, self.occCount))
#             elif self.occNumber != -1:
#                 # We have no count of occurrences but at least a occNumber
#                 # (this means it isn't a boolean search op.)
#                 result.append(u' <b>(%i/?)</b>' % self.occNumber)                
                
            if self.occHtml != u"":
                result.append(u'<br>\n')
                result.append(self.occHtml)
                
            result.append('</td></tr></table>')
            self.html = u"".join(result)
            
        return self.html

#                         self.htmlfound.append('<table><tr><td bgcolor="#0000ff" width="6"></td><td>' + u"".join(bluew) + "</td></tr></table>")



class SearchResultListBox(wxHtmlListBox):
    def __init__(self, parent, pWiki, ID):
        wxHtmlListBox.__init__(self, parent, ID, style = wxSUNKEN_BORDER)
        
        self.pWiki = pWiki
        self.searchWikiDialog = parent
        self.found = []
        self.foundinfo = []
        self.searchOp = None # last search operation set by showFound
        self.SetItemCount(0)

        EVT_LEFT_DOWN(self, self.OnLeftDown)
        EVT_LEFT_DCLICK(self, self.OnLeftDown)
        EVT_KEY_DOWN(self, self.OnKeyDown)
        EVT_LISTBOX_DCLICK(self, ID, self.OnDClick)

    
#     def _buildContainerCell(self, i):
#         parser = wxHtmlWinParser()
#         
#         dc = wxClientDC(self)
#         font = dc.GetFont()
#         
#         # parser.SetDC(None)
#         parser.SetDC(dc)
# 
#         # set FS
#         # parser.SetStandardFonts()
#         
#         cell = parser.Parse("")  # self.OnGetItem(i))
#         f2 = dc.GetFont()
#         dc.SetFont(font)
#         
#         return None
#         cell.Layout(self.GetClientSize().x - 2*self.GetMargins().x)
#         parser.SetDC(None)
#         
#         print "_buildContainerCell2", repr(dc.thisown)
#         
#         return cell
#     
#     
#     def OnDrawItem(self, dc, rect, i):
#         # if selected
#         return
#         
#         cell = self._buildContainerCell(i)
#         
#         rendinfo = wxHtmlRenderingInfo()
#         cell.Draw(dc, rect.x+2, rect.y+2, 0, 2000000000, rendinfo)
# 
# 
#     def OnMeasureItem(self, i):
#         cell = self._buildContainerCell(i)
#         return 30
#         
#         return cell.GetHeight() + cell.GetDescent() + 4

    def OnGetItem(self, i):
        try:
            return self.foundinfo[i].getHtml()
        except IndexError:
            return u""

    def showFound(self, sarOp, found, wikiData):
        if found is None:
            self.found = []
            self.foundinfo = []
            self.SetItemCount(0)
            self.searchOp = None
        else:
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
                    
            countOccurrences = self.pWiki.configuration.getboolean("main",
                    "search_wiki_count_occurrences")
                    
            if sarOp.booleanOp:
                # No specific position to show, so show beginning of page
                context = before + after
                if context == 0:
                    self.foundinfo = [_SearchResultItemInfo(w) for w in found]
                else:                    
                    for w in found:
                        text = wikiData.getContent(w)
                        self.foundinfo.append(
                                _SearchResultItemInfo(w).buildOccurrence(
                                text, before, after, (-1, -1), -1))
            else:
                if before + after == 0 and not countOccurrences:
                    # No context, no occurrence counting
                    self.foundinfo = [_SearchResultItemInfo(w) for w in found]
                else:
                    for w in found:
                        text = wikiData.getContent(w)
                        pos = sarOp.searchText(text)
                        firstpos = pos
                        
                        info = _SearchResultItemInfo(w, occPos=pos)
                        
                        if countOccurrences:
                            occ = 1
                            while True:
                                pos = sarOp.searchText(text, pos[1])
                                if pos[0] is None:
                                    break
                                occ += 1

                            info.occCount = occ

                        self.foundinfo.append(info.buildOccurrence(
                                text, before, after, firstpos, 1))
                            
        self.SetItemCount(len(self.foundinfo))
        self.Refresh()
        

    def GetSelectedWord(self):
        sel = self.GetSelection()
        if sel == -1:
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
        if info.occPos[0] == -1:
            return
        if info.occNumber == -1:
            return
            
        before = self.pWiki.configuration.getint("main",
                "search_wiki_context_before")
        after = self.pWiki.configuration.getint("main",
                "search_wiki_context_after")
        
        wikiData = self.pWiki.wikiData
        text = wikiData.getContent(info.wikiWord)
#         searchOp = self.searchWikiDialog.buildSearchReplaceOperation()
#         searchOp.replaceOp = False
#         searchOp.cycleToStart = True

        pos = self.searchOp.searchText(text, info.occPos[1])
        if pos[0] == -1:
            # Page was changed after last search and contains no more any occurrence 
            info.occCount = 0
            info.buildOccurrence(text, 0, 0, pos, -1)
        elif pos[0] < info.occPos[1]:
            # Search went back to beginning, number of last occ. ist also occ.count
            info.occCount = info.occNumber
            info.buildOccurrence(text, before, after, pos, 1)
        else:
            info.buildOccurrence(text, before, after, pos, info.occNumber + 1)

        # TODO nicer refresh
        self.SetSelection(-1)
        self.SetSelection(sel)
        self.Refresh()
        

    def OnDClick(self, evt):
        sel = self.GetSelection()
        if sel == -1:
            return

        info = self.foundinfo[sel]

#         if self.pWiki.getCurrentWikiWord() == info.wikiWord:
#             # Search next
#             searchOp = self.searchWikiDialog.buildSearchReplaceOperation()
#             searchOp.replaceOp = False
#             searchOp.cycleToStart = True
#             self.pWiki.editor.executeSearch(searchOp,
#                     -1, next=True)[1]
#         else:
        self.pWiki.openWikiPage(info.wikiWord)
        # self.pagePosNext = 0
        if info.occPos[0] != -1:
            self.pWiki.getActiveEditor().SetSelectionByCharPos(info.occPos[0],
                    info.occPos[1])

#                 executeSearch(searchOp, 0)
        
        # Works in fast search popup only if called twice
        self.pWiki.getActiveEditor().SetFocus()
        self.pWiki.getActiveEditor().SetFocus()


    def OnLeftDown(self, evt):
        pos = evt.GetPosition()
        hitsel = self.HitTest(pos)
        
        if hitsel == wxNOT_FOUND:
            evt.Skip()
            return
        
        if pos.x < (5 + 6):
            # Click inside the blue bar
#             sel = self.GetSelection()
            self.SetSelection(hitsel)
            self._pageListFindNext()
#             self.SetSelection(sel)
            return
        
        evt.Skip()
        
    def OnKeyDown(self, evt):
        if evt.GetKeyCode() == WXK_F3 and not evt.ShiftDown() and \
                not evt.MetaDown() and not evt.ControlDown() and \
                not evt.CmdDown():
            self._pageListFindNext()
        elif evt.GetKeyCode() in (WXK_RETURN, WXK_NUMPAD_ENTER) and \
                not evt.ShiftDown() and not evt.MetaDown() and \
                not evt.ControlDown() and not evt.CmdDown():
            self.OnDClick(evt)
        else:
            evt.Skip()


class SearchWikiDialog(wxDialog):   # TODO
    def __init__(self, pWiki, ID, title="Search Wiki",
                 pos=wxDefaultPosition, size=wxDefaultSize,
                 style=wxNO_3D|wxDEFAULT_DIALOG_STYLE|wxRESIZE_BORDER):
        d = wxPreDialog()
        self.PostCreate(d)
        
        self.pWiki = pWiki

        res = xrc.wxXmlResource.Get()
        res.LoadOnDialog(self, self.pWiki, "SearchWikiDialog")
        lbox = SearchResultListBox(self, self.pWiki, GUI_ID.htmllbPages)
        res.AttachUnknownControl("htmllbPages", lbox, self)
        
        self.ctrls = XrcControls(self)
        
#         searchContentPage = res.LoadPanel(self.ctrls.nbFilters,
#                 "SearchWikiContentPage")
#         
#         self.ctrls.nbFilters.AddPage(searchContentPage, u"Content", True)
#         
#         self.Fit()
        
        self.ctrls.btnClose.SetId(wxID_CANCEL)
        
        self.listNeedsRefresh = True  # Reflects listbox content current
                                      # search criteria?
                                      
        self.savedSearches = None
        self.foundPages = []
        
        self.listPagesOperation = ListWikiPagesOperation()
        self._refreshSavedSearchesList()

        EVT_BUTTON(self, GUI_ID.btnFindPages, self.OnSearchWiki)
        EVT_BUTTON(self, GUI_ID.btnSetPageList, self.OnSetPageList)
        EVT_BUTTON(self, GUI_ID.btnFindNext, self.OnFindNext)        
        EVT_BUTTON(self, GUI_ID.btnReplace, self.OnReplace)
        EVT_BUTTON(self, GUI_ID.btnReplaceAll, self.OnReplaceAll)
        EVT_BUTTON(self, GUI_ID.btnSaveSearch, self.OnSaveSearch)
        EVT_BUTTON(self, GUI_ID.btnDeleteSearches, self.OnDeleteSearches)
        EVT_BUTTON(self, GUI_ID.btnLoadSearch, self.OnLoadSearch)
        EVT_BUTTON(self, GUI_ID.btnLoadAndRunSearch, self.OnLoadAndRunSearch)
        EVT_BUTTON(self, GUI_ID.btnOptions, self.OnOptions)
        EVT_BUTTON(self, GUI_ID.btnCopyPageNamesToClipboard,
                self.OnCopyPageNamesToClipboard)
        
        EVT_CHAR(self.ctrls.txtSearch, self.OnCharToFind)
#         EVT_CHAR(self.ctrls.rboxSearchType, self.OnCharToFind)
#         EVT_CHAR(self.ctrls.cbCaseSensitive, self.OnCharToFind)
#         EVT_CHAR(self.ctrls.cbWholeWord, self.OnCharToFind)

        EVT_LISTBOX_DCLICK(self, GUI_ID.lbSavedSearches, self.OnLoadAndRunSearch)
        EVT_RADIOBOX(self, GUI_ID.rboxSearchType, self.OnRadioBox)
        EVT_BUTTON(self, wxID_CANCEL, self.OnClose)        
        EVT_CLOSE(self, self.OnClose)
        
        EVT_TEXT(self, GUI_ID.txtSearch, self.OnListRefreshNeeded)
        EVT_CHECKBOX(self, GUI_ID.cbCaseSensitive, self.OnListRefreshNeeded)
        EVT_CHECKBOX(self, GUI_ID.cbWholeWord, self.OnListRefreshNeeded)


    def buildSearchReplaceOperation(self):
        sarOp = SearchReplaceOperation()
        sarOp.searchStr = guiToUni(self.ctrls.txtSearch.GetValue())
        sarOp.booleanOp = self.ctrls.rboxSearchType.GetSelection() == 1
        sarOp.caseSensitive = self.ctrls.cbCaseSensitive.GetValue()
        sarOp.wholeWord = self.ctrls.cbWholeWord.GetValue()
        sarOp.cycleToStart = False
        sarOp.wildCard = 'regex'
        sarOp.wikiWide = True
        sarOp.listWikiPagesOp = self.listPagesOperation

        if not sarOp.booleanOp:
            sarOp.replaceStr = guiToUni(self.ctrls.txtReplace.GetValue())
            
        return sarOp


    def _refreshPageList(self):
        self.SetCursor(wxHOURGLASS_CURSOR)
        self.Freeze()
        try:
            sarOp = self.buildSearchReplaceOperation()
            self.pWiki.saveCurrentDocPage()
    
            if len(sarOp.searchStr) > 0:
                self.foundPages = self.pWiki.getWikiData().search(sarOp)
                self.foundPages.sort()
                self.ctrls.htmllbPages.showFound(sarOp, self.foundPages,
                        self.pWiki.wikiData)
            else:
                self.foundPages = []
                self.ctrls.htmllbPages.showFound(None, None, None)
    
            self.listNeedsRefresh = False
        
        finally:
            self.Thaw()
            self.SetCursor(wxNullCursor)


    def OnSearchWiki(self, evt):
        self._refreshPageList()
        if not self.ctrls.htmllbPages.IsEmpty():
            self.ctrls.htmllbPages.SetFocus()
            self.ctrls.htmllbPages.SetSelection(0)
            
    def OnSetPageList(self, evt):
        """
        Show the Page List dialog
        """
        dlg = WikiPageListConstructionDialog(self, self.pWiki, -1,
                value=self.listPagesOperation, allowOrdering=False)

#         result = dlg.ShowModal()
#         dlg.Destroy()
#         if result == wxID_OK:
#             self.listPagesOperation = dlg.getValue()
#             pass

        dlg.getMiscEvent().addListener(KeyFunctionSink((
                ("nonmodal closed", self.onNonmodalClosedPageList),
        )))

        self.Show(False)
        dlg.Show(True)

    def onNonmodalClosedPageList(self, miscevt):
        plop = miscevt.get("listWikiPagesOp")
        if plop is not None:
            self.listPagesOperation = plop

        self.Show(True)


    def OnListRefreshNeeded(self, evt):
        self.listNeedsRefresh = True

    def OnFindNext(self, evt):
        self._findNext()

    def _findNext(self):
        if self.listNeedsRefresh:
            # Refresh list and start from beginning
            self._refreshPageList()
            
        if self.ctrls.htmllbPages.GetCount() == 0:
            return
            
        while True:            
                
            #########self.ctrls.lb.SetSelection(self.listPosNext)
            
            wikiWord = guiToUni(self.ctrls.htmllbPages.GetSelectedWord())
            
            if not wikiWord:
                self.ctrls.htmllbPages.SetSelection(0)
                wikiWord = guiToUni(self.ctrls.htmllbPages.GetSelectedWord())

            if self.pWiki.getCurrentWikiWord() != wikiWord:
                self.pWiki.openWikiPage(wikiWord)
                nextOnPage = False
            else:
                nextOnPage = True

            searchOp = self.buildSearchReplaceOperation()
            searchOp.replaceOp = False
            pagePosNext = self.pWiki.getActiveEditor().executeSearch(searchOp,
                    0, next=nextOnPage)[1]
                    
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


    def OnReplace(self, evt):
        sarOp = self.buildSearchReplaceOperation()
        sarOp.replaceOp = True
        self.pWiki.getActiveEditor().executeReplace(sarOp)
        
        self._findNext()


    def OnReplaceAll(self, evt):
        answer = wxMessageBox(u"Replace all occurrences?", u"Replace All",
                wxYES_NO | wxNO_DEFAULT, self)
        
        if answer == wxNO:
            return
        else:
            self._refreshPageList()
            
            if self.ctrls.htmllbPages.GetCount() == 0:
                return
                
            self.pWiki.saveCurrentDocPage()
            
            sarOp = self.buildSearchReplaceOperation()
            sarOp.replaceOp = True
            
            wikiData = self.pWiki.wikiData

            for i in xrange(self.ctrls.htmllbPages.GetCount()):
                self.ctrls.htmllbPages.SetSelection(i)
                wikiWord = guiToUni(self.ctrls.htmllbPages.GetSelectedWord())
                text = wikiData.getContent(wikiWord)
                
                charStartPos = 0

                while True:
                    try:
                        found = sarOp.searchText(text, charStartPos)
                        start, end = found[:2]
                    except:
                        # Regex error -> Stop searching
                        return
                        
                    if start is None: break
                    
                    repl = sarOp.replace(text, found)
                    text = text[:start] + repl + text[end:]  # TODO Faster?
                    charStartPos = start + len(repl)

                wikiData.setContent(wikiWord, text)
                
            # Reopen current word because its content could have been overwritten before
            self.pWiki.openWikiPage(self.pWiki.getCurrentWikiWord(),
                    addToHistory=False, forceReopen=True)
                    
            self._refreshPageList()



    # TODO Store search mode
    def OnSaveSearch(self, evt):
        sarOp = self.buildSearchReplaceOperation()
        
        if len(sarOp.searchStr) > 0:
            title = sarOp.getTitle()
            while True:
                title = guiToUni(wxGetTextFromUser("Title:",
                        "Choose search title", title, self))
                if title == u"":
                    return  # Cancel
                    
                if title in self.pWiki.wikiData.getSavedSearchTitles():
                    answer = wxMessageBox(
                            u"Do you want to overwrite existing search '%s'?" %
                            title, u"Overwrite search",
                            wxYES_NO | wxNO_DEFAULT | wxICON_QUESTION, self)
                    if answer == wxNO:
                        continue

                self.pWiki.wikiData.saveSearch(title,
                        sarOp.getPackedSettings())
                self._refreshSavedSearchesList()
                break
        else:
            self.pWiki.displayErrorMessage(
                    u"Invalid search string, can't save as view")


    def OnRadioBox(self, evt):
        self.listNeedsRefresh = True
        booleanSearch = self.ctrls.rboxSearchType.GetSelection() == 1
        
        self.ctrls.txtReplace.Enable(not booleanSearch)
        self.ctrls.btnFindNext.Enable(not booleanSearch)
        self.ctrls.btnReplace.Enable(not booleanSearch)
        self.ctrls.btnReplaceAll.Enable(not booleanSearch)


    def OnOptions(self, evt):
        dlg = SearchWikiOptionsDialog(self, self.pWiki, -1)
        dlg.CenterOnParent(wxBOTH)

        dlg.ShowModal()
        dlg.Destroy()


    def OnClose(self, evt):
        self.pWiki.findDlg = None
        self.Destroy()


    def _refreshSavedSearchesList(self):
        self.savedSearches = self.pWiki.wikiData.getSavedSearchTitles()
        self.savedSearches.sort()
        
        self.ctrls.lbSavedSearches.Clear()
        for search in self.savedSearches:
            self.ctrls.lbSavedSearches.Append(uniToGui(search))


    def OnDeleteSearches(self, evt):
        sels = self.ctrls.lbSavedSearches.GetSelections()
        
        if len(sels) == 0:
            return
            
        answer = wxMessageBox(
                u"Do you want to delete %i search(es)?" % len(sels),
                u"Delete search",
                wxYES_NO | wxNO_DEFAULT | wxICON_QUESTION, self)
        if answer == wxNO:
            return

        for s in sels:
            self.pWiki.wikiData.deleteSavedSearch(self.savedSearches[s])
        self._refreshSavedSearchesList()


    def OnLoadSearch(self, evt):
        self._loadSearch()
        
    def OnLoadAndRunSearch(self, evt):
        if self._loadSearch():
            self._refreshPageList()

    def _loadSearch(self):
        sels = self.ctrls.lbSavedSearches.GetSelections()
        
        if len(sels) != 1:
            return False
        
        datablock = self.pWiki.wikiData.getSearchDatablock(
                self.savedSearches[sels[0]])
        sarOp = SearchReplaceOperation()
        sarOp.setPackedSettings(datablock)
        
        self.ctrls.txtSearch.SetValue(uniToGui(sarOp.searchStr))
        if sarOp.booleanOp:
            self.ctrls.rboxSearchType.SetSelection(1)
        else:
            self.ctrls.rboxSearchType.SetSelection(0)
        
        self.ctrls.cbCaseSensitive.SetValue(sarOp.caseSensitive)
        self.ctrls.cbWholeWord.SetValue(sarOp.wholeWord)

        if not sarOp.booleanOp and sarOp.replaceOp:
            self.ctrls.txtReplace.SetValue(uniToGui(sarOp.replaceStr))
            
        self.listPagesOperation = sarOp.listWikiPagesOp
            
        self.OnRadioBox(None)  # Refresh settings
        
        return True


    def OnCopyPageNamesToClipboard(self, evt):
        formatting = self.pWiki.getFormatting()
        wordsText = u"".join([u"%s%s%s\n" % (formatting.wikiWordStart, w,
                formatting.wikiWordEnd) for w in self.foundPages])

        copyTextToClipboard(wordsText)


    def OnCharToFind(self, evt):
#         if (evt.GetKeyCode() == WXK_DOWN):
#             if not self.ctrls.lb.IsEmpty():
#                 self.ctrls.lb.SetFocus()
#                 self.ctrls.lb.SetSelection(0)
#         elif (evt.GetKeyCode() == WXK_UP):
#             pass
        if (evt.GetKeyCode() in (WXK_RETURN, WXK_NUMPAD_ENTER)):
            self.OnSearchWiki(evt)
        else:
            evt.Skip()



class SearchPageDialog(wxDialog):   # TODO
    def __init__(self, pWiki, ID, title="Search Wiki",
                 pos=wxDefaultPosition, size=wxDefaultSize,
                 style=wxNO_3D|wxDEFAULT_DIALOG_STYLE|wxRESIZE_BORDER):
        d = wxPreDialog()
        self.PostCreate(d)
        
        self.pWiki = pWiki

        res = xrc.wxXmlResource.Get()
        res.LoadOnDialog(self, self.pWiki, "SearchPageDialog")
        
        self.ctrls = XrcControls(self)
        
        self.ctrls.btnClose.SetId(wxID_CANCEL)
        
        self.firstFind = True

        EVT_BUTTON(self, GUI_ID.btnFindNext, self.OnFindNext)        
        EVT_BUTTON(self, GUI_ID.btnReplace, self.OnReplace)
        EVT_BUTTON(self, GUI_ID.btnReplaceAll, self.OnReplaceAll)
        EVT_BUTTON(self, wxID_CANCEL, self.OnClose)        
        EVT_CLOSE(self, self.OnClose)


    def OnClose(self, evt):
        self.pWiki.findDlg = None
        self.Destroy()


    def _buildSearchOperation(self):
        sarOp = SearchReplaceOperation()
        sarOp.searchStr = guiToUni(self.ctrls.txtSearch.GetValue())
        sarOp.replaceOp = False
        sarOp.booleanOp = False
        sarOp.caseSensitive = self.ctrls.cbCaseSensitive.GetValue()
        sarOp.wholeWord = self.ctrls.cbWholeWord.GetValue()
        sarOp.cycleToStart = True #???
        
        if self.ctrls.cbRegEx.GetValue():
            sarOp.wildCard = 'regex'
        else:
            sarOp.wildCard = 'no'

        sarOp.wikiWide = False

        return sarOp


    def OnFindNext(self, evt):
        sarOp = self._buildSearchOperation()
        sarOp.replaceOp = False        
        self.pWiki.getActiveEditor().executeSearch(sarOp,
                next=not self.firstFind)
        self.firstFind = False

    def OnReplace(self, evt):
        sarOp = self._buildSearchOperation()
        sarOp.replaceStr = guiToUni(self.ctrls.txtReplace.GetValue())
        sarOp.replaceOp = True
        self.pWiki.getActiveEditor().executeReplace(sarOp)
        self.pWiki.getActiveEditor().executeSearch(sarOp, next=True)

    def OnReplaceAll(self, evt):
        sarOp = self._buildSearchOperation()
        sarOp.replaceStr = guiToUni(self.ctrls.txtReplace.GetValue())
        sarOp.replaceOp = True
        sarOp.cycleToStart = False
        lastReplacePos = 0
        while True:
            lastReplacePos = self.pWiki.getActiveEditor().executeSearch(sarOp,
                    lastReplacePos)[1]
            if lastReplacePos == -1:
                break
            lastReplacePos = self.pWiki.getActiveEditor().executeReplace(sarOp)



class WikiPageListConstructionDialog(wxDialog, MiscEventSourceMixin):   # TODO
    def __init__(self, parent, pWiki, ID, value=None, allowOrdering=True,
            title="Page List", pos=wxDefaultPosition, size=wxDefaultSize,
            style=wxNO_3D|wxDEFAULT_DIALOG_STYLE|wxRESIZE_BORDER):
        d = wxPreDialog()
        self.PostCreate(d)
        MiscEventSourceMixin.__init__(self)

        self.pWiki = pWiki
        self.value = value
        
        self.pageListData = []  # Wiki words in the left pagelist
        self.resultListData = []

        res = xrc.wxXmlResource.Get()
        res.LoadOnDialog(self, parent, "WikiPageListConstructionDialog")
        
        self.ctrls = XrcControls(self)
        
        self.ctrls.btnOk.SetId(wxID_OK)
        self.ctrls.btnCancel.SetId(wxID_CANCEL)
        
        self.ctrls.tfPageListToAdd.SetValue(uniToGui(
                self.pWiki.getCurrentWikiWord()))

        if self.value is not None:
            item = self.value.searchOpTree
            
            if item.CLASS_PERSID == "AllPages":
                self.ctrls.rbPagesAll.SetValue(True)
            elif item.CLASS_PERSID == "RegexPage":
                self.ctrls.rbPagesMatchRe.SetValue(True)
                self.ctrls.tfMatchRe.SetValue(item.getPattern)
            elif item.CLASS_PERSID == "ListItemWithSubtreePages":
                self.ctrls.rbPagesInList.SetValue(True)
                self.pageListData = item.rootWords[:]
                self.ctrls.lbPageList.AppendItems(self.pageListData)
                if item.level == -1:
                    self.ctrls.tfSubtreeLevels.SetValue(u"")
                else:
                    self.ctrls.tfSubtreeLevels.SetValue(u"%i" % item.level)
                    
            self.ctrls.chOrdering.SetSelection(
                    self._ORDERNAME_TO_CHOICE[self.value.ordering])

        if not allowOrdering:
            self.ctrls.chOrdering.SetSelection(self._ORDERNAME_TO_CHOICE["no"])
            self.ctrls.chOrdering.Enable(False)

        EVT_TEXT(self, GUI_ID.tfSubtreeLevels,
                lambda evt: self.ctrls.rbPagesInList.SetValue(True))
        EVT_TEXT(self, GUI_ID.tfMatchRe,
                lambda evt: self.ctrls.rbPagesMatchRe.SetValue(True))
        
        EVT_BUTTON(self, wxID_CANCEL, self.OnClose)        
        EVT_CLOSE(self, self.OnClose)
        EVT_BUTTON(self, wxID_OK, self.OnOk)

        EVT_TEXT_ENTER(self, GUI_ID.tfPageListToAdd, self.OnPageListAdd)
        EVT_BUTTON(self, GUI_ID.btnPageListUp, self.OnPageListUp) 
        EVT_BUTTON(self, GUI_ID.btnPageListDown, self.OnPageListDown) 
        EVT_BUTTON(self, GUI_ID.btnPageListSort, self.OnPageListSort) 

        EVT_BUTTON(self, GUI_ID.btnPageListAdd, self.OnPageListAdd) 
        EVT_BUTTON(self, GUI_ID.btnPageListDelete, self.OnPageListDelete) 
        EVT_BUTTON(self, GUI_ID.btnPageListClearList, self.OnPageListClearList) 

        EVT_BUTTON(self, GUI_ID.btnPageListCopyToClipboard,
                self.OnPageListCopyToClipboard) 

        EVT_BUTTON(self, GUI_ID.btnPageListAddFromClipboard,
                self.OnPageListAddFromClipboard) 
        EVT_BUTTON(self, GUI_ID.btnPageListOverwriteFromClipboard,
                self.OnPageListOverwriteFromClipboard) 
        EVT_BUTTON(self, GUI_ID.btnPageListIntersectWithClipboard,
                self.OnPageListIntersectWithClipboard) 

        EVT_BUTTON(self, GUI_ID.btnResultListPreview, self.OnResultListPreview) 
        EVT_BUTTON(self, GUI_ID.btnResultCopyToClipboard,
                self.OnResultCopyToClipboard) 


#         EVT_BUTTON(self, GUI_ID.btnReplace, self.OnReplace)
#         EVT_BUTTON(self, GUI_ID.btnReplaceAll, self.OnReplaceAll)
#         EVT_BUTTON(self, wxID_CANCEL, self.OnClose)        
#         EVT_CLOSE(self, self.OnClose)

    _ORDERCHOICE_TO_NAME = {
            0: "natural",
            1: "ascending",
            2: "no"
    }

    _ORDERNAME_TO_CHOICE = {
            "natural": 0,
            "ascending": 1,
            "no": 2
    }


    def setValue(self, value):
        self.value = value
        
    def getValue(self):
        return self.value


    def _buildListPagesOperation(self):
        """
        Construct a ListWikiPagesOperation according to current content of the
        dialog
        """
        import SearchAndReplace as Sar
        
        lpOp = Sar.ListWikiPagesOperation()
        
        if self.ctrls.rbPagesAll.GetValue():
            item = Sar.AllWikiPagesNode(lpOp)
        elif self.ctrls.rbPagesMatchRe.GetValue():
            pattern = self.ctrls.tfMatchRe.GetValue()
            try:
                re.compile(pattern, re.DOTALL | re.UNICODE | re.MULTILINE)
            except re.error, e:
                wxMessageBox("Bad regular expression '%s':\n%s" %
                        (pattern, unicode(e)), u"Regular expression error",
                        wxOK, self)
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


    def OnOk(self, evt):
        val = self._buildListPagesOperation()
        if val is None:
            return
            
        self.value = val 
        if self.IsModal():
            self.EndModal(wxID_OK)
        else:
            self.Destroy()
            self.fireMiscEventProps({"nonmodal closed": wxID_OK,
                    "listWikiPagesOp": self.value})

    def OnClose(self, evt):
        self.value = None
        if self.IsModal():
            self.EndModal(wxID_CANCEL)
        else:
            self.Destroy()
            self.fireMiscEventProps({"nonmodal closed": wxID_CANCEL,
                    "listWikiPagesOp": None})


    def OnPageListUp(self, evt):
        sel = self.ctrls.lbPageList.GetSelection()
        if sel == wxNOT_FOUND or sel == 0:
            return
            
        dispWord = self.ctrls.lbPageList.GetString(sel)
        word = self.pageListData[sel]
        
        self.ctrls.lbPageList.Delete(sel)
        del self.pageListData[sel]
        
        self.ctrls.lbPageList.Insert(dispWord, sel - 1)
        self.pageListData.insert(sel - 1, word)
        self.ctrls.lbPageList.SetSelection(sel - 1)
        
        
    def OnPageListDown(self, evt):
        sel = self.ctrls.lbPageList.GetSelection()
        if sel == wxNOT_FOUND or sel == len(self.pageListData) - 1:
            return

        dispWord = self.ctrls.lbPageList.GetString(sel)
        word = self.pageListData[sel]
        
        self.ctrls.lbPageList.Delete(sel)
        del self.pageListData[sel]
        
        self.ctrls.lbPageList.Insert(dispWord, sel + 1)
        self.pageListData.insert(sel + 1, word)
        self.ctrls.lbPageList.SetSelection(sel + 1)


    def OnPageListSort(self, evt):
        self.ctrls.rbPagesInList.SetValue(True)

        self.pageListData.sort()
        
        self.ctrls.lbPageList.Clear()
        self.ctrls.lbPageList.AppendItems(self.pageListData)


    def OnPageListAdd(self, evt):
        self.ctrls.rbPagesInList.SetValue(True)

        word = guiToUni(self.ctrls.tfPageListToAdd.GetValue())
        formatting = self.pWiki.getFormatting()
        word = formatting.wikiWordToLabel(word)
        if not formatting.isNakedWikiWord(word):
            return
        if word in self.pageListData:
            return  # Already in list

        sel = self.ctrls.lbPageList.GetSelection()
        if sel == wxNOT_FOUND:
            self.ctrls.lbPageList.Append(uniToGui(word))
            self.pageListData.append(word)
            self.ctrls.lbPageList.SetSelection(len(self.pageListData) - 1)
        else:
            self.ctrls.lbPageList.Insert(uniToGui(word), sel + 1)
            self.pageListData.insert(sel + 1, word)
            self.ctrls.lbPageList.SetSelection(sel + 1)
            
        self.ctrls.tfPageListToAdd.SetValue(u"")


    def OnPageListDelete(self, evt):
        self.ctrls.rbPagesInList.SetValue(True)

        sel = self.ctrls.lbPageList.GetSelection()
        if sel == wxNOT_FOUND:
            return

        self.ctrls.lbPageList.Delete(sel)
        del self.pageListData[sel]
        
        count = len(self.pageListData)
        if count == 0:
            return
        
        if sel >= count:
            sel = count - 1
        self.ctrls.lbPageList.SetSelection(sel)


    def OnPageListClearList(self, evt):
        self.ctrls.rbPagesInList.SetValue(True)

        self.ctrls.lbPageList.Clear()
        self.pageListData = []
        

    def OnPageListAddFromClipboard(self, evt):
        """
        Take wiki words from clipboard and enter them into the list
        """
        self.ctrls.rbPagesInList.SetValue(True)

        page = PageAst.Page()
        
        text = getTextFromClipboard()
        if text:
            page.buildAst(self.pWiki.getFormatting(), text)
            wwTokens = page.findType(WikiFormatting.FormatTypes.WikiWord)

            found = {}
            # First fill found with already existing entries
            for w in self.pageListData:
                found[w] = None
            
            # Now fill all with new tokens
            for t in wwTokens:
                w = t.node.nakedWord
                if not found.has_key(w):
                    self.ctrls.lbPageList.Append(uniToGui(w))
                    self.pageListData.append(w)
                    found[w] = None


    def OnPageListOverwriteFromClipboard(self, evt):
        self.ctrls.lbPageList.Clear()
        self.pageListData = []
        
        self.OnPageListAddFromClipboard(evt)


    def OnPageListIntersectWithClipboard(self, evt):
        """
        Take wiki words from clipboard and intersect with the list
        """
        self.ctrls.rbPagesInList.SetValue(True)

        page = PageAst.Page()
        
        text = getTextFromClipboard()
        if text:
            page.buildAst(self.pWiki.getFormatting(), text)
            wwTokens = page.findType(WikiFormatting.FormatTypes.WikiWord)

            found = {}
            # First fill found with new tokens
            for t in wwTokens:
                w = t.node.nakedWord
                found[w] = None

            pageList = self.pageListData
            self.pageListData = []
            self.ctrls.lbPageList.Clear()

            # Now fill all with already existing entries
            for w in pageList:
                if found.has_key(w):
                    self.ctrls.lbPageList.Append(uniToGui(w))
                    self.pageListData.append(w)
                    del found[w]


    def OnPageListCopyToClipboard(self, evt):
        formatting = self.pWiki.getFormatting()
        wordsText = u"".join([u"%s%s%s\n" % (formatting.wikiWordStart, w,
                formatting.wikiWordEnd) for w in self.pageListData])

        copyTextToClipboard(wordsText)


    def OnResultCopyToClipboard(self, evt):
        formatting = self.pWiki.getFormatting()
        wordsText = u"".join([u"%s%s%s\n" % (formatting.wikiWordStart, w,
                formatting.wikiWordEnd) for w in self.resultListData])

        copyTextToClipboard(wordsText)


    def OnResultListPreview(self, evt):
        lpOp = self._buildListPagesOperation()
        
        if lpOp is None:
            return

        self.SetCursor(wxHOURGLASS_CURSOR)
        self.Freeze()
        try:
            words = self.pWiki.getWikiData().search(lpOp)
            
            self.ctrls.lbResultPreview.Clear()
            self.ctrls.lbResultPreview.AppendItems(words)
#             for w in words:
#                 self.ctrls.lbResultPreview.Append(uniToGui(w))
                
            self.resultListData = words
        finally:
            self.Thaw()
            self.SetCursor(wxNullCursor)


class FastSearchPopup(wxFrame):
    """
    Popup window which appears when hitting Enter in the fast search text field
    in the main window.
    Using frame because wxPopupWindow is not available on Mac OS
    """
    def __init__(self, parent, mainControl, ID, pos=wxDefaultPosition):
        wxFrame.__init__(self, parent, ID, "fast search", pos=pos,
                style=wxRESIZE_BORDER | wxFRAME_FLOAT_ON_PARENT |
                wxFRAME_NO_TASKBAR)

        self.mainControl = mainControl
        self.searchText = None
        
        self.resultBox = SearchResultListBox(self, self.mainControl, -1)
        
        sizer = wxBoxSizer(wxVERTICAL)
        sizer.Add(self.resultBox, 1, wxEXPAND)

        self.SetSizer(sizer)
        
        config = self.mainControl.getConfig()
        width = config.getint("main", "fastSearch_sizeX", 200)
        height = config.getint("main", "fastSearch_sizeY", 400)

        setWindowSize(self, (width, height))
        setWindowPos(self, fullVisible=True)

#         EVT_KILL_FOCUS(self, self.OnKillFocus)
        EVT_KILL_FOCUS(self.resultBox, self.OnKillFocus)
        EVT_CLOSE(self, self.OnClose)


    def OnKillFocus(self, evt):
        self.Close()
        
        
    def OnClose(self, evt):
        width, height = self.GetSizeTuple()
        config = self.mainControl.getConfig()
        config.set("main", "fastSearch_sizeX", str(width))
        config.set("main", "fastSearch_sizeY", str(height))

        evt.Skip()


    def buildSearchReplaceOperation(self):
        sarOp = SearchReplaceOperation()
        sarOp.searchStr = self.searchText
        sarOp.booleanOp = False # ?
        sarOp.caseSensitive = False
        sarOp.wholeWord = False
        sarOp.cycleToStart = False
        sarOp.wildCard = 'regex'
        sarOp.wikiWide = True
#         sarOp.listWikiPagesOp = self.listPagesOperation

#         if not sarOp.booleanOp:
#             sarOp.replaceStr = guiToUni(self.ctrls.txtReplace.GetValue())
  
        return sarOp

    def runSearchOnWiki(self, text):
        """
        lists all found pages which match search text
        """
        self.searchText = text
        self._refreshPageList()
#         if not self.ctrls.htmllbPages.IsEmpty():
#             self.ctrls.htmllbPages.SetFocus()
#             self.ctrls.htmllbPages.SetSelection(0)

    def _refreshPageList(self):
        self.SetCursor(wxHOURGLASS_CURSOR)
        self.Freeze()
        try:
            sarOp = self.buildSearchReplaceOperation()
            self.mainControl.saveCurrentDocPage()
    
            if len(sarOp.searchStr) > 0:
                self.foundPages = self.mainControl.getWikiData().search(sarOp)
                self.foundPages.sort()
                self.resultBox.showFound(sarOp, self.foundPages,
                        self.mainControl.getWikiData())
            else:
                self.foundPages = []
                self.resultBox.showFound(None, None, None)

            self.listNeedsRefresh = False

        finally:
            self.Thaw()
            self.SetCursor(wxNullCursor)
