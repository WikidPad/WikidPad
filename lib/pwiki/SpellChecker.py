import traceback

import wx, wx.xrc

from .WikiExceptions import *

# from wxHelper import *

from . import MiscEvent

from .Utilities import DUMBTHREADSTOP

from .wxHelper import GUI_ID, XrcControls, autosizeColumn, wxKeyFunctionSink

from .WikiPyparsing import buildSyntaxNode


try:
    from .EnchantDriver import Dict
    from . import EnchantDriver
except (AttributeError, ImportError, WindowsError):
    import ExceptionLogger
    ExceptionLogger.logOptionalComponentException(
            "Initialize enchant driver (spell checking)")
    Dict = None

    # traceback.print_exc()
    
    # WindowsError may happen if an incomplete enchant installation is found
    # in the system


from .DocPages import AliasWikiPage, WikiPage

from .StringOps import uniToGui, guiToUni

from collections import defaultdict


class enchantDictionaries:
    """
    For efficiency we create a single enchant dictionary for each language
    that is used (as and when they are needed).

    All interfacing with said dictionaries should be done though this class
    """
    def __init__(self):

        self.dicts = {}

        self.addedGlobalWords = defaultdict(set)
        self.addedLocalWords = defaultdict(set)

        self.current_lang = None

        self.block = False

    def getDictByLanguage(self, lang):
        """
        Helper to get the required dictionary.

        Will create it if required
        """

        if lang in self.dicts:
            return self.dicts[lang]
        else:
            try:
                self.dicts[lang] = Dict(lang)
                return self.dicts[lang]

            except EnchantDriver.DictNotFoundError:
                self.dicts[lang] = None
                # Error message?
                ExceptionLogger.logOptionalComponentException(
                        "Dictionary not found: {0} (spell checking)".format(lang))


    def addPersonalWordListsToEnchantDict(self, lang, globalWords, localWords):
        """
        Adds words from spellChkAddedGlobal and spellChkAddedLocal to
        the enchant Dict.
        """
        print("ADD PERS", self.block)
        if lang is None:
            return True# Should this ever happen? (it does during startup)

        # HACK (which seems to work)
        # If 2 instances try to access the aspell library at the same time
        # we can end up with a segfault (on linux at least)
        if self.block:
            return False

        print("ADD PERS2")
        self.block = True

        toAddGlobal = globalWords.difference(self.addedGlobalWords[lang])
        toAddLocal = localWords.difference(self.addedLocalWords[lang])

        toAddGlobal.discard("")
        toAddLocal.discard("")

        # We add the words to each of the currently active languages
        # It may be worth creating an option to add words directly to the
        # dictionary (as opposed to each time that it is loaded).
        if self.dicts[lang] is not None:
            add_word = self.dicts[lang].add_to_session
            check = self.dicts[lang].check

            [add_word(word) for word in toAddGlobal if not check(word)]
            [add_word(word) for word in toAddLocal if not check(word)]

            self.addedGlobalWords[lang] = globalWords
            self.addedLocalWords[lang] = localWords
        print("ADD PERS2")

        self.block = False

        return True




class SpellCheckerDialog(wx.Dialog):
    def __init__(self, parent, ID, mainControl, title=None,
                 pos=wx.DefaultPosition, size=wx.DefaultSize,
                 style=wx.NO_3D):
        wx.Dialog.__init__(self)

        self.mainControl = mainControl
        res = wx.xrc.XmlResource.Get()
        res.LoadDialog(self, parent, "SpellCheckDialog")

        if title is not None:
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

        self.session = SpellCheckerSession(self.mainControl.getWikiDocument(), 
                self.mainControl.getWikiDocument().enchantDictionaries)

        self.currentCheckedWord = None
        self.currentStart = -1
        self.currentEnd = -1
        
        self.session.setCurrentDocPage(
                self.mainControl.getActiveEditor().getLoadedDocPage())


        # Fixes focus bug under Linux
        self.SetFocus()

        self.Bind(wx.EVT_BUTTON, self.OnIgnore, id=GUI_ID.btnIgnore)
        self.Bind(wx.EVT_BUTTON, self.OnIgnoreAll, id=GUI_ID.btnIgnoreAll)
        self.Bind(wx.EVT_BUTTON, self.OnReplace, id=GUI_ID.btnReplace)
        self.Bind(wx.EVT_BUTTON, self.OnReplaceAll, id=GUI_ID.btnReplaceAll)
        self.Bind(wx.EVT_BUTTON, self.OnAddWordGlobal, id=GUI_ID.btnAddWordGlobal)
        self.Bind(wx.EVT_BUTTON, self.OnAddWordLocal, id=GUI_ID.btnAddWordLocal)
        self.Bind(wx.EVT_BUTTON, self.OnClose, id=wx.ID_CANCEL)        
        self.Bind(wx.EVT_CLOSE, self.OnClose)

                
#         EVT_LISTBOX(self, GUI_ID.lbReplaceSuggestions,
#                 self.OnLbReplaceSuggestions)
        self.Bind(wx.EVT_LIST_ITEM_SELECTED, self.OnLbReplaceSuggestions,
                id=GUI_ID.lbReplaceSuggestions)

        self.ctrls.tfReplaceWith.Bind(wx.EVT_CHAR, self.OnCharReplaceWith)
        self.ctrls.lbReplaceSuggestions.Bind(wx.EVT_CHAR,
                self.OnCharReplaceSuggestions)


    def _showInfo(self, msg):
        """
        Set dialog controls to show an info/error message
        """
        
        self.ctrls.tfToCheck.SetValue("")
        # Show message in blue
        self.ctrls.tfToCheck.SetDefaultStyle(wx.TextAttr(wx.BLUE))
        self.ctrls.tfToCheck.AppendText(msg)
        self.ctrls.tfToCheck.SetDefaultStyle(wx.TextAttr(wx.BLACK))
        # To scroll text to beginning
        self.ctrls.tfToCheck.SetInsertionPoint(0)
        self.ctrls.tfReplaceWith.SetValue("")
        self.ctrls.lbReplaceSuggestions.DeleteAllItems()
        
        self.ctrls.tfReplaceWith.SetFocus()


    def checkNext(self, startPos=0):
        activeEditor = self.mainControl.getActiveEditor()
        startWikiWord = self.mainControl.getCurrentWikiWord()

        if startWikiWord is None:
            # No wiki loaded or no wiki word in editor
            self._showInfo(
                    _("No wiki open or current page is a functional page"))
            return False

        startWikiWord = self.mainControl.getWikiDocument()\
                .getWikiPageNameForLinkTermOrAsIs(startWikiWord)

        firstCheckedWikiWord = startWikiWord

        if not self.mainControl.getWikiDocument().isDefinedWikiPageName(
                firstCheckedWikiWord):

            # This can happen if startWikiWord is a newly created, not yet
            # saved page
            if not self.ctrls.cbGoToNextPage.GetValue():
                self._showInfo(_("Current page is not modified yet"))
                return False

            firstCheckedWikiWord = self.session.findAndLoadNextWikiPage(None,
                    firstCheckedWikiWord)
                    
            if firstCheckedWikiWord is None:
                self._showInfo(_("No (more) misspelled words found"))
                return False

        else:
            self.session.setCurrentDocPage(
                    self.mainControl.getWikiDocument().getWikiPage(
                    firstCheckedWikiWord))

            if not self.session.hasEnchantDict():
                if firstCheckedWikiWord == startWikiWord:
                    self._showInfo(_("No dictionary found for this page"))
                    return False  # No dictionary


        checkedWikiWord = firstCheckedWikiWord

        langHelper = wx.GetApp().createWikiLanguageHelper(
                self.session.getCurrentDocPage().getWikiLanguageName())

        text = activeEditor.GetText()

        self.ctrls.tfToCheck.SetValue("")

        while True:
            start, end, spWord = langHelper.findNextWordForSpellcheck(text,
                    startPos, self.session.getCurrentDocPage())

            if start is None:
                # End of page reached
                if self.ctrls.cbGoToNextPage.GetValue():
                    checkedWikiWord = self.session.findAndLoadNextWikiPage(
                            firstCheckedWikiWord, checkedWikiWord)
                    
                    if checkedWikiWord is None:
                        self._showInfo(_("No (more) misspelled words found"))
                        return False

                    text = self.mainControl.getWikiDocument()\
                            .getWikiPage(checkedWikiWord).getLiveText()
                    startPos = 0
                    continue
                else:
                    self._showInfo(_("No (more) misspelled words found"))
                    return False

            if self.session.checkWord(spWord):
                # Ignore if word is in the ignore lists or is seen as correct
                # by the spell checker

                startPos = end
                continue

            if spWord in self.session.getAutoReplaceWords():
                activeEditor.showSelectionByCharPos(start, end)
                activeEditor.ReplaceSelection(
                        self.session.getAutoReplaceWords()[spWord])
                startPos = activeEditor.GetSelectionCharPos()[1]
                continue

            break


        if startWikiWord != checkedWikiWord:
            # The search went on to another word, so load it into editor
            self.mainControl.openWikiPage(checkedWikiWord)

        self.currentCheckedWord = spWord
        self.currentStart = start
        self.currentEnd = end

        activeEditor.showSelectionByCharPos(start, end)

        conStart = max(0, start - 30)

        contextPre = text[conStart:start]
        contextPost = text[end:end+60]
        
        contextPre = contextPre.split("\n")[-1]
        contextPost = contextPost.split("\n", 1)[0]

        # Show misspelled word in context
        self.ctrls.tfToCheck.SetDefaultStyle(wx.TextAttr(wx.BLACK))
        self.ctrls.tfToCheck.AppendText(contextPre)
        self.ctrls.tfToCheck.SetDefaultStyle(wx.TextAttr(wx.RED))
        self.ctrls.tfToCheck.AppendText(spWord)
        self.ctrls.tfToCheck.SetDefaultStyle(wx.TextAttr(wx.BLACK))
        self.ctrls.tfToCheck.AppendText(contextPost)
        # To scroll text to beginning
        self.ctrls.tfToCheck.SetInsertionPoint(0)
        
        # List suggestions
        sugglist = self.session.suggest(spWord)
        
        self.ctrls.lbReplaceSuggestions.DeleteAllItems()
        for s in sugglist:
            self.ctrls.lbReplaceSuggestions.InsertItem(
                    self.ctrls.lbReplaceSuggestions.GetItemCount(), s)
#         self.ctrls.lbReplaceSuggestions.SetColumnWidth(0, wx.LIST_AUTOSIZE)
        autosizeColumn(self.ctrls.lbReplaceSuggestions, 0)

        if len(sugglist) > 0:
            self.ctrls.tfReplaceWith.SetValue(sugglist[0])
        else:
            self.ctrls.tfReplaceWith.SetValue(spWord)

        self.ctrls.tfReplaceWith.SetFocus()

        return True


    def OnClose(self, evt):
        self.mainControl.spellChkDlg = None
        self.session.close()
        self.session = None
        self.Destroy()

    def OnIgnore(self, evt):
        s, e = self.mainControl.getActiveEditor().GetSelectionCharPos()
        self.checkNext(e)


    def OnIgnoreAll(self, evt):
        self.session.addIgnoreWordSession(self.currentCheckedWord)
        self.OnIgnore(None)


    def OnReplace(self, evt):
        activeEditor = self.mainControl.getActiveEditor()

        repl = self.ctrls.tfReplaceWith.GetValue()
        if repl != self.currentCheckedWord:
            activeEditor.ReplaceSelection(repl)

        s, e = self.mainControl.getActiveEditor().GetSelectionCharPos()
        self.checkNext(e)


    def OnReplaceAll(self, evt):
        self.session.addAutoReplace(self.currentCheckedWord, 
                self.ctrls.tfReplaceWith.GetValue())
        self.OnReplace(None)


    def _getReplSuggSelect(self):
        return self.ctrls.lbReplaceSuggestions.GetNextItem(-1,
                state=wx.LIST_STATE_SELECTED)

    def OnLbReplaceSuggestions(self, evt):
        sel = self._getReplSuggSelect()
        if sel == -1:
            return
        sel = self.ctrls.lbReplaceSuggestions.GetItemText(sel)
        self.ctrls.tfReplaceWith.SetValue(sel)

    def OnAddWordGlobal(self, evt):
        """
        Add word globally (application-wide)
        """
        self.session.addIgnoreWordGlobal(self.currentCheckedWord)
        self.OnIgnore(None)


    def OnAddWordLocal(self, evt):
        """
        Add word locally (wiki-wide)
        """
        self.session.addIgnoreWordLocal(self.currentCheckedWord)
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
                (self._getReplSuggSelect() == 0):
            self.ctrls.tfReplaceWith.SetFocus()
            self.ctrls.lbReplaceSuggestions.SetItemState(0, 0,
                    wx.LIST_STATE_SELECTED)
        else:
            evt.Skip()



class SpellCheckerSession(MiscEvent.MiscEventSourceMixin):
    def __init__(self, wikiDocument, enchantDictionaries):
        MiscEvent.MiscEventSourceMixin.__init__(self)

        self.enchantDictionaries = enchantDictionaries

        self.wikiDocument = wikiDocument
        self.currentDocPage = None

        self.enchantDict = None
        self.dictLanguage = None
        
        # For current session
        self.autoReplaceWords = {}
        self.spellChkIgnore = set()  # set of words to ignore during spell checking

        # For currently open dict file (if any)
        self.spellChkAddedGlobal = None
        self.globalPwlPage = None
        self.spellChkAddedLocal = None
        self.localPwlPage = None
        
        self.__sinkWikiDocument = wxKeyFunctionSink((
                ("reread personal word list needed",
                    self.onRereadPersonalWordlistNeeded),
        ), self.wikiDocument.getMiscEvent())

        self.__sinkApp = wxKeyFunctionSink((
                ("reread personal word list needed",
                    self.onRereadPersonalWordlistNeeded),
        ), wx.GetApp().getMiscEvent())



#         self.currentDocPage = self.mainControl.getActiveEditor().getLoadedDocPage()
# 
#         self._refreshDictionary()

    def close(self):
        """
        Prepare for destruction
        """
        # We need to delete (all?) these references otherwise we get a small
        # (but noticable) memory leak when calling cloneForThread
        self.enchantDict = None
        self.dictLanguage = None
        self.globalPwlPage = None
        self.spellChkAddedGlobal = None
        self.spellChkAddedLocal = None
        self.localPwlPage = None
        self.enchantDictionaries = None
        self.wikiDocument = None
        self.__sinkWikiDocument.disconnect()
        self.__sinkApp.disconnect()

    def cloneForThread(self):
        """
        Generates a clone which can be run in a different thread independently
        of other clones.
        
        """
        result = SpellCheckerSession(self.wikiDocument, 
                self.enchantDictionaries)
        result.currentDocPage = self.currentDocPage
        
        # For current session
        result.autoReplaceWords = self.autoReplaceWords
        result.spellChkIgnore = self.spellChkIgnore

        result.dictLanguage = self.dictLanguage
        result.enchantDict = self.enchantDict  # Thread safety???  Dict(self.dictLanguage)

        # For currently open dict file (if any)
        result.spellChkAddedGlobal = self.spellChkAddedGlobal
        result.globalPwlPage = self.globalPwlPage
        result.spellChkAddedLocal = self.spellChkAddedLocal
        result.localPwlPage = self.localPwlPage

        return result



    def getCurrentDocPage(self):
        return self.currentDocPage

    def setCurrentDocPage(self, docPage):
        self.currentDocPage = docPage
        self._refreshDictionary()   # TODO Make faster?

    def hasEnchantDict(self):
        return not self.enchantDict is None


    def _refreshDictionary(self):
        """
        Creates the enchant spell checker object
        """
        docPage = self.currentDocPage  # self.mainControl.getActiveEditor().getLoadedDocPage()
        if not isinstance(docPage, (AliasWikiPage, WikiPage)):
            return  # No support for functional pages

        lang = docPage.getAttributeOrGlobal("language", self.dictLanguage)
        try:
            if lang == "" or lang == None:
                # TODO: should raise an ?error message that spellchecking
                #       won't work with no language defined
                raise EnchantDriver.DictNotFoundError()

            if lang != self.dictLanguage:
                self.enchantDict = self.enchantDictionaries.getDictByLanguage(
                        lang)
                self.dictLanguage = lang
                self.rereadPersonalWordLists()
        except (UnicodeEncodeError, EnchantDriver.DictNotFoundError):
            self.enchantDict = None
            self.dictLanguage = None
            self.globalPwlPage = None
            self.spellChkAddedGlobal = None
            self.spellChkAddedLocal = None
            self.localPwlPage = None


    def onRereadPersonalWordlistNeeded(self, miscevt):
        self.rereadPersonalWordLists()
        self.fireMiscEventKeys(("modified spell checker session",))

    def rereadPersonalWordLists(self):
        self.globalPwlPage = self.wikiDocument.getFuncPage("global/PWL")
        self.spellChkAddedGlobal = \
                set(self.globalPwlPage.getLiveText().split("\n"))

        self.localPwlPage = self.wikiDocument.getFuncPage("wiki/PWL")
        self.spellChkAddedLocal = \
                set(self.localPwlPage.getLiveText().split("\n"))


        #words_added = self.enchantDictionaries.addPersonalWordListsToEnchantDict(
        #        self.dictLanguage, self.spellChkAddedGlobal, 
        #        self.spellChkAddedLocal)

        if not self.addPersonalWordLists():
            wx.CallAfter(self.addPersonalWordLists)

    def addPersonalWordLists(self):
        if self.enchantDictionaries is None:
            return False

        return self.enchantDictionaries.addPersonalWordListsToEnchantDict(
                self.dictLanguage, self.spellChkAddedGlobal, 
                self.spellChkAddedLocal)

        # This is probably very bad practice
        #while not words_added:
        #    words_added = self.enchantDictionaries.addPersonalWordListsToEnchantDict(
        #        self.dictLanguage, self.spellChkAddedGlobal, 
        #        self.spellChkAddedLocal)



    def findAndLoadNextWikiPage(self, firstCheckedWikiWord, checkedWikiWord):
        while True:
            #Go to next page
            nw = self.wikiDocument.getWikiData().getNextWikiPageName(
                    checkedWikiWord)
            if nw is None:
                nw = self.wikiDocument.getWikiData().getFirstWikiPageName()

            if nw is None or nw == firstCheckedWikiWord:
                # Something went wrong or we are where we started
                return None

            checkedWikiWord = nw

            if firstCheckedWikiWord is None:
                # To avoid infinite loop
                firstCheckedWikiWord = checkedWikiWord

            self.setCurrentDocPage(self.wikiDocument.getWikiPage(checkedWikiWord))

            if self.enchantDict is None:
                # This page has no defined language or dictionary not available
                continue
            else:
                # Success
                return checkedWikiWord


    def checkWord(self, spWord):
        # If no enchantDict we just use locally defined words
        if self.enchantDict is None:
            return spWord in self.spellChkIgnore or \
                    spWord in self.spellChkAddedGlobal or \
                    spWord in self.spellChkAddedLocal
        # Otherwise we only care about the ignore list (the rest is
        # handled by adding the words to the enchantDict, see
        # addPersonalWordListsToEnchantDict)
        else:
            return spWord in self.spellChkIgnore or \
                    self.enchantDict.check(spWord)

    def suggest(self, spWord):
        if self.enchantDict is None:
            return []

        return self.enchantDict.suggest(spWord)

    def getAutoReplaceWords(self):
        return self.autoReplaceWords

    def addAutoReplace(self, fromWord, toWord):
        self.autoReplaceWords[fromWord] = toWord


    def resetIgnoreListSession(self):
        """
        Clear the list of words to ignore for this session.
        """
        self.spellChkIgnore.clear()
        self.fireMiscEventKeys(("modified spell checker session",))


    def addIgnoreWordSession(self, spWord):
        self.spellChkIgnore.add(spWord)
        # For global and local ignores the changed FuncPage automatically
        # issues an event which triggers a reread of the word lists
        # and sends another event that session was modified.
        # For the session ignore list this must be done here explicitly

        self.fireMiscEventKeys(("modified spell checker session",))


    def addIgnoreWordGlobal(self, spWord):
        """
        Add spWord globally (application-wide)
        """
        if self.spellChkAddedGlobal is None:
            return  # TODO When does this happen?
        self.spellChkAddedGlobal.add(spWord)
        words = list(self.spellChkAddedGlobal)
        self.wikiDocument.getCollator().sort(words)
        self.globalPwlPage.replaceLiveText("\n".join(words))
        self.enchantDict.add_to_session(spWord)


    def addIgnoreWordLocal(self, spWord):
        """
        Add spWord locally (wiki-wide)
        """
        if self.spellChkAddedLocal is None:
            return  # TODO When does this happen?
        self.spellChkAddedLocal.add(spWord)
        words = list(self.spellChkAddedLocal)
        self.wikiDocument.getCollator().sort(words)
        self.localPwlPage.replaceLiveText("\n".join(words))
        self.enchantDict.add_to_session(spWord)


    def buildUnknownWordList(self, text, threadstop=DUMBTHREADSTOP):
        if not self.hasEnchantDict():
            return buildSyntaxNode([], -1, "unknownSpellList")
        
        docPage = self.getCurrentDocPage()
        
        if docPage is None:
            return buildSyntaxNode([], -1, "unknownSpellList")
        
        result = []

        langHelper = wx.GetApp().createWikiLanguageHelper(
                docPage.getWikiLanguageName())

        startPos = 0

        while True:
            threadstop.testValidThread()

            start, end, spWord = langHelper.findNextWordForSpellcheck(text,
                    startPos, docPage)
            

            if start is None:
                # End of page reached
                return buildSyntaxNode(result, -1, "unknownSpellList")

            startPos = end

            if self.checkWord(spWord):
                # Ignore if word is in the ignore lists or is seen as correct
                # by the spell checker
                continue
            
            # Word is unknown -> add to result
            # It is added as a WikiPyparsing.TerminalNode
            
            result.append(buildSyntaxNode(spWord, start, "unknownSpelling"))
            


def isSpellCheckSupported():
    return Dict is not None
