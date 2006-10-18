import sets, os.path

from wxPython.wx import *
from wxPython.html import *

import wxPython.xrc as xrc

from wxHelper import *


try:
    from EnchantDriver import Dict
    import EnchantDriver
except ImportError:
    Dict = None

from DocPages import AliasWikiPage, WikiPage

from StringOps import uniToGui, guiToUni, mbcsEnc

import WikiFormatting



class SpellCheckerDialog(wxDialog):
    def __init__(self, parent, ID, mainControl, title="Check spelling",
                 pos=wxDefaultPosition, size=wxDefaultSize,
                 style=wxNO_3D):
        d = wxPreDialog()
        self.PostCreate(d)
        
        self.mainControl = mainControl
        res = xrc.wxXmlResource.Get()
        res.LoadOnDialog(self, parent, "SpellCheckDialog")
        self.SetTitle(title)
        
        # Create styled explanation
        tfToCheck = wxTextCtrl(self, GUI_ID.tfToCheck, style=wxTE_MULTILINE|wxTE_RICH)
        res.AttachUnknownControl("tfToCheck", tfToCheck, self)
        tfReplaceWith = wxTextCtrl(self, GUI_ID.tfReplaceWith, style=wxTE_RICH)
        res.AttachUnknownControl("tfReplaceWith", tfReplaceWith, self)

        self.ctrls = XrcControls(self)
        self.ctrls.btnCancel.SetId(wxID_CANCEL)
        self.ctrls.lbReplaceSuggestions.InsertColumn(0, "Suggestion")
        
        self.wordRe = self.mainControl.getFormatting().TextWordRE
        
        self.enchantDict = None
        self.dictLanguage = None
        
        self.currentCheckedWord = None
        self.currentStart = -1
        self.currentEnd = -1

        # For current session
        self.autoReplaceWords = {}
        self.spellChkIgnore = sets.Set()  # set of words to ignore during spell checking

        # For currently open dict file (if any)
        self.spellChkAddedGlobal = None
        self.globalPwlPage = None
        self.spellChkAddedLocal = None
        self.localPwlPage = None

        self._refreshDictionary()

        EVT_BUTTON(self, GUI_ID.btnIgnore, self.OnIgnore)
        EVT_BUTTON(self, GUI_ID.btnIgnoreAll, self.OnIgnoreAll)
        EVT_BUTTON(self, GUI_ID.btnReplace, self.OnReplace)
        EVT_BUTTON(self, GUI_ID.btnReplaceAll, self.OnReplaceAll)
        EVT_BUTTON(self, GUI_ID.btnAddWordGlobal, self.OnAddWordGlobal)
        EVT_BUTTON(self, GUI_ID.btnAddWordLocal, self.OnAddWordLocal)
        EVT_BUTTON(self, wxID_CANCEL, self.OnClose)        
        EVT_CLOSE(self, self.OnClose)

                
#         EVT_LISTBOX(self, GUI_ID.lbReplaceSuggestions,
#                 self.OnLbReplaceSuggestions)
        EVT_LIST_ITEM_SELECTED(self, GUI_ID.lbReplaceSuggestions,
                self.OnLbReplaceSuggestions)

        EVT_CHAR(self.ctrls.tfReplaceWith, self.OnCharReplaceWith)
        EVT_CHAR(self.ctrls.lbReplaceSuggestions, self.OnCharReplaceSuggestions)


    def _refreshDictionary(self):
        """
        Creates the enchant spell checker object
        """
        localDictPath = os.path.join(self.mainControl.globalConfigSubDir,
                "[PWL].wiki")

        docPage = self.mainControl.getActiveEditor().getLoadedDocPage()
        if not isinstance(docPage, (AliasWikiPage, WikiPage)):
            return  # No support for functional pages

        lang = docPage.getPropertyOrGlobal(u"language", self.dictLanguage)
        try:
            if lang != self.dictLanguage:
                self.enchantDict = Dict(str(lang))
                self.dictLanguage = lang
                self.rereadPersonalWordLists()
        except (UnicodeEncodeError, EnchantDriver.DictNotFoundError):
            self.enchantDict = None
            self.dictLanguage = None
            self.globalPwlPage = None
            self.spellChkAddedGlobal = None
            self.spellChkAddedLocal = None
            self.localPwlPage = None
            
            
    def _showInfo(self, msg):
        """
        Set dialog controls to show an info/error message
        """
        
        self.ctrls.tfToCheck.SetValue("")
        # Show misspelled word in context
        self.ctrls.tfToCheck.SetDefaultStyle(wxTextAttr(wxBLUE))
        self.ctrls.tfToCheck.AppendText(uniToGui(msg))
        self.ctrls.tfToCheck.SetDefaultStyle(wxTextAttr(wxBLACK))
        self.ctrls.tfReplaceWith.SetValue(u"")
        self.ctrls.lbReplaceSuggestions.DeleteAllItems()
        
        self.ctrls.tfReplaceWith.SetFocus()


    def rereadPersonalWordLists(self):
        wdm = self.mainControl.getWikiDataManager()
        self.globalPwlPage = wdm.getFuncPage("global/[PWL]")
        self.spellChkAddedGlobal = \
                sets.Set(self.globalPwlPage.getLiveText().split("\n"))

        self.localPwlPage = wdm.getFuncPage("wiki/[PWL]")
        self.spellChkAddedLocal = \
                sets.Set(self.localPwlPage.getLiveText().split("\n"))


    def checkNext(self, startPos=0):
        self._refreshDictionary()   # TODO Make faster?
        
        if self.enchantDict is None:
            self._showInfo(u"No dictionary found for this page")
            return False  # No dictionary  # TODO: Next page

        text = self.mainControl.getActiveEditor().GetText()
        activeEditor = self.mainControl.getActiveEditor()
        startWikiWord = self.mainControl.getCurrentWikiWord()

        if startWikiWord is None:
            # No wiki loaded or no wiki word in editor
            self._showInfo(u"No wiki open or current page is a functional page")
            return False

        startWikiWord = self.mainControl.getWikiData().getAliasesWikiWord(
                startWikiWord)
        checkedWikiWord = startWikiWord

        self.ctrls.tfToCheck.SetValue("")

        while True:
            mat = self.wordRe.search(text, startPos)
            if mat is None:
                # End of page reached
                if self.ctrls.cbGoToNextPage.GetValue():
                    #Automatically go to next page
                    nw = self.mainControl.getWikiData().getNextWikiWord(
                            checkedWikiWord)
                    if nw is None:
                        nw = self.mainControl.getWikiData().getFirstWikiWord()
                    
                    if nw is None or nw == startWikiWord:
                        # Something went wrong or we are where we started
                        self._showInfo(u"No (more) misspelled words found")
                        return False
                        
                    text = self.mainControl.getWikiDataManager().getWikiPage(nw).getLiveText()
                    checkedWikiWord = nw
                    startPos = 0
                    continue
                else:
                    self._showInfo(u"No (more) misspelled words found")
                    return False

            start, end = mat.span()
            word = mat.group()

            if mat.group("negative") is not None or \
                    word in self.spellChkIgnore or \
                    word in self.spellChkAddedGlobal or \
                    word in self.spellChkAddedLocal or \
                    self.enchantDict.check(word):
                # Ignore if word is in the negative regex pattern (like numbers,
                # URLs, ...) or in the ignore lists or is seen as correct
                # by the spell checker

                startPos = end
                continue

            if self.autoReplaceWords.has_key(word):
                activeEditor.SetSelectionByCharPos(start, end)
                activeEditor.ReplaceSelection(self.autoReplaceWords[word])
                startPos = activeEditor.GetSelectionCharPos()[1]
                continue  # ?

            break
            
            
        if startWikiWord != checkedWikiWord:
            # The search went on to another word, so load it into editor
            self.mainControl.openWikiPage(checkedWikiWord)

        self.currentCheckedWord = word
        self.currentStart = start
        self.currentEnd = end

        activeEditor.SetSelectionByCharPos(start, end)

        conStart = max(0, start - 30)

        contextPre = text[conStart:start]
        contextPost = text[end:end+60]
        
        contextPre = contextPre.split(u"\n")[-1]
        contextPost = contextPost.split(u"\n", 1)[0]

        # Show misspelled word in context
        self.ctrls.tfToCheck.SetDefaultStyle(wxTextAttr(wxBLACK))
        self.ctrls.tfToCheck.AppendText(contextPre)
        self.ctrls.tfToCheck.SetDefaultStyle(wxTextAttr(wxRED))
        self.ctrls.tfToCheck.AppendText(mat.group(0))
        self.ctrls.tfToCheck.SetDefaultStyle(wxTextAttr(wxBLACK))
        self.ctrls.tfToCheck.AppendText(contextPost)
        
        self.ctrls.tfReplaceWith.SetValue(uniToGui(mat.group(0)))
        
        # List suggestions
        sugglist = self.enchantDict.suggest(mat.group(0))
        
        self.ctrls.lbReplaceSuggestions.DeleteAllItems()
        for s in sugglist:
            self.ctrls.lbReplaceSuggestions.InsertStringItem(
                    self.ctrls.lbReplaceSuggestions.GetItemCount(), s)
        self.ctrls.lbReplaceSuggestions.SetColumnWidth(0, wxLIST_AUTOSIZE)

        self.ctrls.tfReplaceWith.SetFocus()

        return True

    def OnClose(self, evt):
        self.mainControl.spellChkDlg = None
        self.Destroy()

    def OnIgnore(self, evt):
        s, e = self.mainControl.getActiveEditor().GetSelectionCharPos()
        self.checkNext(e)


    def OnIgnoreAll(self, evt):
        self.spellChkIgnore.add(self.currentCheckedWord)
        self.OnIgnore(None)


    def OnReplace(self, evt):
        activeEditor = self.mainControl.getActiveEditor()

        repl = guiToUni(self.ctrls.tfReplaceWith.GetValue())
        if repl != self.currentCheckedWord:
            activeEditor.ReplaceSelection(repl)

        s, e = self.mainControl.getActiveEditor().GetSelectionCharPos()
        self.checkNext(e)


    def OnReplaceAll(self, evt):
        self.autoReplaceWords[self.currentCheckedWord] = \
                guiToUni(self.ctrls.tfReplaceWith.GetValue())
        self.OnReplace(None)


    def getReplSuggSelect(self):
        return self.ctrls.lbReplaceSuggestions.GetNextItem(-1,
                state=wxLIST_STATE_SELECTED)

    def OnLbReplaceSuggestions(self, evt):
        sel = self.getReplSuggSelect()
        if sel == -1:
            return
        sel = self.ctrls.lbReplaceSuggestions.GetItemText(sel)
        self.ctrls.tfReplaceWith.SetValue(sel)


    def OnAddWordGlobal(self, evt):
        """
        Add word globally (application-wide)
        """  
        self.spellChkAddedGlobal.add(self.currentCheckedWord)
        words = list(self.spellChkAddedGlobal)
        self.mainControl.getCollator().sort(words)
        self.globalPwlPage.replaceLiveText(u"\n".join(words))

        self.OnIgnore(None)


    def OnAddWordLocal(self, evt):
        """
        Add word locally (wiki-wide)
        """
        self.spellChkAddedLocal.add(self.currentCheckedWord)
        words = list(self.spellChkAddedLocal)
        self.mainControl.getCollator().sort(words)
        self.localPwlPage.replaceLiveText(u"\n".join(words))

        self.OnIgnore(None)


    def OnCharReplaceWith(self, evt):
        if (evt.GetKeyCode() == WXK_DOWN) and \
                not self.ctrls.lbReplaceSuggestions.GetItemCount() == 0:
            self.ctrls.lbReplaceSuggestions.SetFocus()
            self.ctrls.lbReplaceSuggestions.SetItemState(0,
                    wxLIST_STATE_SELECTED|wxLIST_STATE_FOCUSED,
                    wxLIST_STATE_SELECTED|wxLIST_STATE_FOCUSED)
            self.OnLbReplaceSuggestions(None)
        elif (evt.GetKeyCode() == WXK_UP):
            pass
        else:
            evt.Skip()

    def OnCharReplaceSuggestions(self, evt):
        if (evt.GetKeyCode() == WXK_UP) and \
                (self.getReplSuggSelect() == 0):
            self.ctrls.tfReplaceWith.SetFocus()
            self.ctrls.lbReplaceSuggestions.SetItemState(0, 0,
                    wxLIST_STATE_SELECTED)
        else:
            evt.Skip()





def isSpellCheckSupported():
    return Dict is not None
