import sys, traceback

from wxPython.wx import *
from wxPython.html import *
import wxPython.xrc as xrc

from wxHelper import *

from StringOps import uniToGui, guiToUni, escapeHtml
from SearchAndReplace import SearchReplaceOperation


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
        except:
            self.Refresh()
            return

        self.EndModal(wxID_OK)



class SearchResultListBox(wxHtmlListBox):
    def __init__(self, parent, pWiki, ID):
        wxHtmlListBox.__init__(self, parent, ID, style = wxSUNKEN_BORDER)
        
        self.pWiki = pWiki
        self.searchWikiDialog = parent
        self.found = []
        self.htmlfound = []
        self.SetItemCount(0)

    def OnGetItem(self, i):
        try:
            return self.htmlfound[i]
        except IndexError:
            return u""

    def showFound(self, sarOp, found, wikiData):
        if found is None:
            self.found = []
            self.htmlfound = []
            self.SetItemCount(0)
        else:
            self.found = found
            self.htmlfound = []
            
            # Load context settings
            before = self.pWiki.configuration.getint("main",
                    "search_wiki_context_before")
            after = self.pWiki.configuration.getint("main",
                    "search_wiki_context_after")
                    
            if before + after == 0:
                # No context
                self.htmlfound = [
                        '<font color="BLUE"><b>%s</b></font>' % \
                        escapeHtml(w) for w in found]
            elif sarOp.booleanOp:
                # No specific position to show, so show beginning of page
                context = before + after
                for w in found:
                    bluew = '<font color="BLUE"><b>%s</b></font><br>' % \
                            escapeHtml(w)
                    part = wikiData.getContent(w)[0:context]
                    self.htmlfound.append(bluew + escapeHtml(part))
            else:
                for w in found:
                    bluew = '<font color="BLUE"><b>%s</b></font><br>' % \
                            escapeHtml(w)
                    text = wikiData.getContent(w)
                    pos = sarOp.searchText(text)
                    s = max(0, pos[0] - before)
                    e = min(len(text), pos[1] + after)
                    self.htmlfound.append(bluew + escapeHtml(text[s:pos[0]]) +
                            "<b>" + escapeHtml(text[pos[0]:pos[1]]) + "</b>" +
                            escapeHtml(text[pos[1]:e]))

        self.SetItemCount(len(self.htmlfound))
        self.Refresh()
        
        # self.SetSelection(0)  #?
        
    def GetSelectedWord(self):
        sel = self.GetSelection()
        if sel == -1:
            return None
        else:
            return self.found[sel]
            
    def GetCount(self):
        return len(self.found)
        
    def IsEmpty(self):
        return self.GetCount() == 0



class SearchWikiDialog(wxDialog):   # TODO
    def __init__(self, pWiki, ID, title="Search Wiki",
                 pos=wxDefaultPosition, size=wxDefaultSize,
                 style=wxNO_3D|wxDEFAULT_DIALOG_STYLE|wxRESIZE_BORDER):
        d = wxPreDialog()
        self.PostCreate(d)
        
        self.pWiki = pWiki

        res = xrc.wxXmlResource.Get()
        res.LoadOnDialog(self, self.pWiki, "SearchWikiDialog")
        lbox = SearchResultListBox(self, self.pWiki, -1)
        res.AttachUnknownControl("htmllbPages", lbox, self)
        
        self.ctrls = XrcControls(self)
        
        self.ctrls.btnClose.SetId(wxID_CANCEL)
        
        self.listNeedsRefresh = True  # Reflects listbox content current
                                      # search criteria?
                                      
        self.savedSearches = None
        self.foundPages = []
        self._refreshSavedSearchesList()

        EVT_BUTTON(self, GUI_ID.btnFindPages, self.OnSearchWiki)
        EVT_BUTTON(self, GUI_ID.btnFindNext, self.OnFindNext)        
        EVT_BUTTON(self, GUI_ID.btnReplace, self.OnReplace)
        EVT_BUTTON(self, GUI_ID.btnReplaceAll, self.OnReplaceAll)
        EVT_BUTTON(self, GUI_ID.btnSaveSearch, self.OnSaveSearch)
        EVT_BUTTON(self, GUI_ID.btnDeleteSearches, self.OnDeleteSearches)
        EVT_BUTTON(self, GUI_ID.btnLoadSearch, self.OnLoadSearch)
        EVT_BUTTON(self, GUI_ID.btnLoadAndRunSearch, self.OnLoadAndRunSearch)
        EVT_BUTTON(self, GUI_ID.btnOptions, self.OnOptions)
        EVT_CHAR(self.ctrls.txtSearch, self.OnCharToFind)
#         EVT_CHAR(self.ctrls.rboxSearchType, self.OnCharToFind)
#         EVT_CHAR(self.ctrls.cbCaseSensitive, self.OnCharToFind)
#         EVT_CHAR(self.ctrls.cbWholeWord, self.OnCharToFind)

        EVT_CHAR(self.ctrls.htmllbPages, self.OnCharPagesListBox)
        EVT_LISTBOX_DCLICK(self, GUI_ID.htmllbPages, self.OnPageListDClick)
        EVT_LISTBOX_DCLICK(self, GUI_ID.lbSavedSearches, self.OnLoadAndRunSearch)
        EVT_RADIOBOX(self, GUI_ID.rboxSearchType, self.OnRadioBox)
        EVT_BUTTON(self, wxID_CANCEL, self.OnClose)        
        EVT_CLOSE(self, self.OnClose)
        
        EVT_TEXT(self, GUI_ID.txtSearch, self.OnListRefreshNeeded)
        EVT_CHECKBOX(self, GUI_ID.cbCaseSensitive, self.OnListRefreshNeeded)
        EVT_CHECKBOX(self, GUI_ID.cbWholeWord, self.OnListRefreshNeeded)


    def _buildSearchReplaceOperation(self):
        sarOp = SearchReplaceOperation()
        sarOp.searchStr = guiToUni(self.ctrls.txtSearch.GetValue())
        sarOp.booleanOp = self.ctrls.rboxSearchType.GetSelection() == 1
        sarOp.caseSensitive = self.ctrls.cbCaseSensitive.GetValue()
        sarOp.wholeWord = self.ctrls.cbWholeWord.GetValue()
        sarOp.cycleToStart = False
        sarOp.wildCard = 'regex'
        sarOp.wikiWide = True

        if not sarOp.booleanOp:
            sarOp.replaceStr = guiToUni(self.ctrls.txtReplace.GetValue())
            
        return sarOp


    def _refreshPageList(self):
        sarOp = self._buildSearchReplaceOperation()
        self.pWiki.saveCurrentWikiPage()

        if len(sarOp.searchStr) > 0:
            self.foundPages = self.pWiki.wikiData.search(sarOp)
            self.foundPages.sort()
            self.ctrls.htmllbPages.showFound(sarOp, self.foundPages,
                    self.pWiki.wikiData)
        else:
            self.foundPages = []
            self.ctrls.htmllbPages.showFound(None, None, None)

#         self.ctrls.lb.Clear()
# 
#         if len(sarOp.searchStr) > 0:
#             found = self.pWiki.wikiData.search(sarOp)
#             found.sort()
#             for word in found:
#                 self.ctrls.lb.Append(word)

        self.listNeedsRefresh = False
        

    def OnSearchWiki(self, evt):
        self._refreshPageList()
        if not self.ctrls.htmllbPages.IsEmpty():
            self.ctrls.htmllbPages.SetFocus()
            self.ctrls.htmllbPages.SetSelection(0)

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

            searchOp = self._buildSearchReplaceOperation()
            searchOp.replaceOp = False
            pagePosNext = self.pWiki.editor.executeSearch(searchOp,
                    0, next=nextOnPage)[1]
                    
            if pagePosNext is not None:
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
        sarOp = self._buildSearchReplaceOperation()
        sarOp.replaceOp = True
        self.pWiki.editor.executeReplace(sarOp)
        
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
                
            self.pWiki.saveCurrentWikiPage()
            
            sarOp = self._buildSearchReplaceOperation()
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
        sarOp = self._buildSearchReplaceOperation()
        
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
            self.pWiki.displayErrorMessage(u"Invalid search string, can't save as view")


    def OnPageListDClick(self, evt):
        wikiWord = guiToUni(self.ctrls.htmllbPages.GetSelectedWord())
        if wikiWord:
            self.pWiki.openWikiPage(wikiWord)
            self.pagePosNext = 0
            searchOp = self._buildSearchReplaceOperation()
            searchOp.replaceOp = False
            self.pWiki.editor.executeSearch(searchOp, 0)

            self.pWiki.editor.SetFocus()


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
            
        self.OnRadioBox(None)  # Refresh settings
        
        return True


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

    def OnCharPagesListBox(self, evt):
#         if (evt.GetKeyCode() == WXK_UP) and (self.ctrls.lb.GetSelection() == 0):
#             self.ctrls.text.SetFocus()
#             self.ctrls.lb.Deselect(0)
        if (evt.GetKeyCode() in (WXK_RETURN, WXK_NUMPAD_ENTER)):
            self.OnPageListDClick(evt)
        else:
            evt.Skip()




