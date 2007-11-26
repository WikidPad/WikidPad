import sets, os.path

import wx, wx.xrc

from wxHelper import *


try:
    from EnchantDriver import Dict
    import EnchantDriver
except ImportError:
    Dict = None

from DocPages import AliasWikiPage, WikiPage

from StringOps import uniToGui, guiToUni, mbcsEnc

import WikiFormatting



class SpellCheckerDialog(wx.Dialog):
    def __init__(self, parent, ID, mainControl, title="Check spelling",
                 pos=wx.DefaultPosition, size=wx.DefaultSize,
                 style=wx.NO_3D):
        d = wx.PreDialog()
        self.PostCreate(d)
        
        self.mainControl = mainControl
        res = wx.xrc.XmlResource.Get()
        res.LoadOnDialog(self, parent, "SpellCheckDialog")
        self.SetTitle(title)
        
        # Create styled explanation
        tfToCheck = wx.TextCtrl(self, GUI_ID.tfToCheck,
                style=wx.TE_MULTILINE|wx.TE_RICH)
        res.AttachUnknownControl("tfToCheck", tfToCheck, self)
        tfReplaceWith = wx.TextCtrl(self, GUI_ID.tfReplaceWith, style=wx.TE_RICH)
        res.AttachUnknownControl("tfReplaceWith", tfReplaceWith, self)

        self.ctrls = XrcControls(self)
        self.ctrls.btnCancel.SetId(wx.ID_CANCEL)
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
        
        # Fixes focus bug under Linux
        self.SetFocus()

        wx.EVT_BUTTON(self, GUI_ID.btnIgnore, self.OnIgnore)
        wx.EVT_BUTTON(self, GUI_ID.btnIgnoreAll, self.OnIgnoreAll)
        wx.EVT_BUTTON(self, GUI_ID.btnReplace, self.OnReplace)
        wx.EVT_BUTTON(self, GUI_ID.btnReplaceAll, self.OnReplaceAll)
        wx.EVT_BUTTON(self, GUI_ID.btnAddWordGlobal, self.OnAddWordGlobal)
        wx.EVT_BUTTON(self, GUI_ID.btnAddWordLocal, self.OnAddWordLocal)
        wx.EVT_BUTTON(self, wx.ID_CANCEL, self.OnClose)        
        wx.EVT_CLOSE(self, self.OnClose)

                
#         EVT_LISTBOX(self, GUI_ID.lbReplaceSuggestions,
#                 self.OnLbReplaceSuggestions)
        wx.EVT_LIST_ITEM_SELECTED(self, GUI_ID.lbReplaceSuggestions,
                self.OnLbReplaceSuggestions)

        wx.EVT_CHAR(self.ctrls.tfReplaceWith, self.OnCharReplaceWith)
        wx.EVT_CHAR(self.ctrls.lbReplaceSuggestions, self.OnCharReplaceSuggestions)


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
        # Show message in blue
        self.ctrls.tfToCheck.SetDefaultStyle(wx.TextAttr(wx.BLUE))
        self.ctrls.tfToCheck.AppendText(uniToGui(msg))
        self.ctrls.tfToCheck.SetDefaultStyle(wx.TextAttr(wx.BLACK))
        # To scroll text to beginning
        self.ctrls.tfToCheck.SetInsertionPoint(0)
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
            self._showInfo(_(u"No dictionary found for this page"))
            return False  # No dictionary  # TODO: Next page

        text = self.mainControl.getActiveEditor().GetText()
        activeEditor = self.mainControl.getActiveEditor()
        startWikiWord = self.mainControl.getCurrentWikiWord()

        if startWikiWord is None:
            # No wiki loaded or no wiki word in editor
            self._showInfo(
                    _(u"No wiki open or current page is a functional page"))
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
                        self._showInfo(_(u"No (more) misspelled words found"))
                        return False
                        
                    text = self.mainControl.getWikiDataManager().getWikiPage(nw).getLiveText()
                    checkedWikiWord = nw
                    startPos = 0
                    continue
                else:
                    self._showInfo(_(u"No (more) misspelled words found"))
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
        self.ctrls.tfToCheck.SetDefaultStyle(wx.TextAttr(wx.BLACK))
        self.ctrls.tfToCheck.AppendText(contextPre)
        self.ctrls.tfToCheck.SetDefaultStyle(wx.TextAttr(wx.RED))
        self.ctrls.tfToCheck.AppendText(mat.group(0))
        self.ctrls.tfToCheck.SetDefaultStyle(wx.TextAttr(wx.BLACK))
        self.ctrls.tfToCheck.AppendText(contextPost)
        # To scroll text to beginning
        self.ctrls.tfToCheck.SetInsertionPoint(0)
        
        # List suggestions
        sugglist = self.enchantDict.suggest(mat.group(0))
        
        self.ctrls.lbReplaceSuggestions.DeleteAllItems()
        for s in sugglist:
            self.ctrls.lbReplaceSuggestions.InsertStringItem(
                    self.ctrls.lbReplaceSuggestions.GetItemCount(), s)
        self.ctrls.lbReplaceSuggestions.SetColumnWidth(0, wx.LIST_AUTOSIZE)
        
        if len(sugglist) > 0:
            self.ctrls.tfReplaceWith.SetValue(uniToGui(sugglist[0]))
        else:
            self.ctrls.tfReplaceWith.SetValue(uniToGui(mat.group(0)))

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
                state=wx.LIST_STATE_SELECTED)

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
        if (evt.GetKeyCode() == wx.WXK_DOWN) and \
                not self.ctrls.lbReplaceSuggestions.GetItemCount() == 0:
            self.ctrls.lbReplaceSuggestions.SetFocus()
            self.ctrls.lbReplaceSuggestions.SetItemState(0,
                    wx.LIST_STATE_SELECTED|wx.LIST_STATE_FOCUSED,
                    wx.LIST_STATE_SELECTED|wx.LIST_STATE_FOCUSED)
            self.OnLbReplaceSuggestions(None)
        elif (evt.GetKeyCode() == wx.WXK_UP):
            pass
        else:
            evt.Skip()

    def OnCharReplaceSuggestions(self, evt):
        if (evt.GetKeyCode() == wx.WXK_UP) and \
                (self.getReplSuggSelect() == 0):
            self.ctrls.tfReplaceWith.SetFocus()
            self.ctrls.lbReplaceSuggestions.SetItemState(0, 0,
                    wx.LIST_STATE_SELECTED)
        else:
            evt.Skip()





def isSpellCheckSupported():
    return Dict is not None
