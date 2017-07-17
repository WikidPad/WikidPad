# -*- coding: iso8859-1 -*-
import sys, traceback
# from time import strftime
import re

from os.path import exists, isdir, isfile

from .rtlibRepl import minidom

import wx, wx.html, wx.xrc


from .wxHelper import *

try:
    from . import sqlite3api as sqlite
except:
    sqlite = None


from Consts import VERSION_STRING, DATABLOCK_STOREHINT_INTERN, ModifyText

from .StringOps import mbcsEnc, mbcsDec, \
        escapeForIni, unescapeForIni, escapeHtml, strftimeUB, pathEnc
from .wikidata import DbBackendUtils

from .WikiExceptions import *

from . import Serialization, PluginManager, SystemInfo





class SelectWikiWordDialog(wx.Dialog, ModalDialogMixin):
    """
    Called for "Append/Prepend wiki word" in tree node context menu
    """
    def __init__(self, pWiki, parent, ID, title=None,
                 pos=wx.DefaultPosition, size=wx.DefaultSize,
                 style=wx.NO_3D):

        wx.Dialog.__init__(self)

        self.pWiki = pWiki
        self.wikiWord = None
        self.listContent = []
        self.ignoreTextChange = 0
        
        res = wx.xrc.XmlResource.Get()
        res.LoadDialog(self, parent, "SelectWikiWordDialog")

        if title is not None:
            self.SetTitle(title)

        self.ctrls = XrcControls(self)

        self.ctrls.btnOk.SetId(wx.ID_OK)
        self.ctrls.btnCancel.SetId(wx.ID_CANCEL)
        
        # Fixes focus bug under Linux
        self.SetFocus()

        self.Bind(wx.EVT_BUTTON, self.OnOk, id=wx.ID_OK)

        self.Bind(wx.EVT_TEXT, self.OnText, id=ID)
        self.ctrls.text.Bind(wx.EVT_CHAR, self.OnCharText)
        self.ctrls.lb.Bind(wx.EVT_CHAR, self.OnCharListBox)
        self.Bind(wx.EVT_LISTBOX, self.OnListBox, id=ID)
        self.Bind(wx.EVT_LISTBOX_DCLICK, self.OnOk, id=GUI_ID.lb)


    def _fillListContent(self, searchTxt):
        if len(searchTxt) == 0:
            self.listContent = []
            return

        if searchTxt == "%":
            self.listContent = self.pWiki.getWikiData()\
                    .getWikiWordMatchTermsWith("")
            return
        
        # Filter out anything else than real words and explicit aliases
        self.listContent = self.pWiki.getWikiData().getWikiWordMatchTermsWith(
                searchTxt)


    def OnOk(self, evt):
        sel = self.ctrls.lb.GetSelection()
        if sel != wx.NOT_FOUND:
            term = self.listContent[sel]
            self.wikiWord = term[2]
        else:
            self.wikiWord = self.ctrls.text.GetValue()
    
            if not self.pWiki.getWikiDocument().isDefinedWikiLinkTerm(
                    self.wikiWord):
                self._fillListContent(self.wikiWord)
                if len(self.listContent) > 0:
                    self.wikiWord = self.listContent[0][2]
                else:
                    langHelper = wx.GetApp().createWikiLanguageHelper(
                            self.pWiki.getWikiDefaultWikiLanguage())
                    wikiWord = langHelper.extractWikiWordFromLink(self.wikiWord,
                            self.pWiki.getWikiDocument())
    
                    if wikiWord is None:
                        # Entered text is not a valid wiki word
                        # TODO Error message?
                        self.ctrls.text.SetFocus()
                        return

                    self.wikiWord = wikiWord

        self.EndModal(wx.ID_OK)
        
                
    def GetValue(self):
        return self.wikiWord

    def OnText(self, evt):
        if self.ignoreTextChange:
            self.ignoreTextChange -= 1
            return

        text = evt.GetString()

        self.ctrls.lb.Freeze()
        try:
            self.ctrls.lb.Clear()
            self._fillListContent(text)

            for term in self.listContent:
                self.ctrls.lb.Append(term[0])
        finally:
            self.ctrls.lb.Thaw()


    def OnListBox(self, evt):
        sel = self.ctrls.lb.GetSelection()
        if sel != wx.NOT_FOUND:
            if self.listContent[sel][0] != self.listContent[sel][2]:
                self.ctrls.stLinkTo.SetLabel(_("Links to:") + " " +
                        self.listContent[sel][2])
            else:
                self.ctrls.stLinkTo.SetLabel("")
            self.ignoreTextChange += 1
            self.ctrls.text.SetValue(self.listContent[sel][0])
        else:
            self.ctrls.stLinkTo.SetLabel("")



    def OnCharText(self, evt):
        if (evt.GetKeyCode() == wx.WXK_DOWN) and not self.ctrls.lb.IsEmpty():
            self.ctrls.lb.SetFocus()
            self.ctrls.lb.SetSelection(0)
            self.OnListBox(None)  # TODO Check if works for non-Windows
        elif (evt.GetKeyCode() == wx.WXK_UP):
            pass
        else:
            evt.Skip()


    def OnCharListBox(self, evt):
        if (evt.GetKeyCode() == wx.WXK_UP) and (self.ctrls.lb.GetSelection() == 0):
            self.ctrls.text.SetFocus()
            self.ctrls.lb.Deselect(0)
            self.ctrls.text.SetSelection(-1, -1)
        else:
            evt.Skip()

     

class OpenWikiWordDialog(wx.Dialog, ModalDialogMixin):
    def __init__(self, pWiki, parent, ID, title=None,
                 pos=wx.DefaultPosition, size=wx.DefaultSize,
                 style=wx.NO_3D):

        wx.Dialog.__init__(self)

        self.pWiki = pWiki
        self.value = None
        self.listContent = []
        self.ignoreTextChange = 0

        res = wx.xrc.XmlResource.Get()
        res.LoadDialog(self, parent, "OpenWikiWordDialog")

        if title is not None:
            self.SetTitle(title)

        self.ctrls = XrcControls(self)
        
        self.ctrls.chSort.SetSelection(self.pWiki.getConfig().getint("main",
                "openWikiWordDialog_sortOrder", 0))

        self.ctrls.btnOk.SetId(wx.ID_OK)
        self.ctrls.btnCancel.SetId(wx.ID_CANCEL)
        
        # Fixes focus bug under Linux
        self.SetFocus()

        self.Bind(wx.EVT_TEXT, self.OnText, id=ID)
        self.ctrls.text.Bind(wx.EVT_CHAR, self.OnCharText)
        self.ctrls.lb.Bind(wx.EVT_CHAR, self.OnCharListBox)
        self.ctrls.lb.Bind(wx.EVT_KEY_DOWN, self.OnKeyDownListBox)
        self.Bind(wx.EVT_LISTBOX, self.OnListBox, id=ID)
        self.Bind(wx.EVT_LISTBOX_DCLICK, self.OnOk, id=GUI_ID.lb)
        self.Bind(wx.EVT_BUTTON, self.OnOk, id=wx.ID_OK)
        self.Bind(wx.EVT_BUTTON, self.OnCreate, id=GUI_ID.btnCreate)
        self.Bind(wx.EVT_CHOICE, self.OnChoiceSort, id=GUI_ID.chSort)
        self.Bind(wx.EVT_BUTTON, self.OnDelete, id=GUI_ID.btnDelete)
        self.Bind(wx.EVT_BUTTON, self.OnNewTab, id=GUI_ID.btnNewTab)
        self.Bind(wx.EVT_BUTTON, self.OnNewTabBackground, id=GUI_ID.btnNewTabBackground)

    def OnOk(self, evt):
        if self.activateSelectedWikiWords(0):
            self.EndModal(wx.ID_OK)


    def _fillListContent(self, searchTxt):
        if len(searchTxt) == 0:
            self.listContent = []
            return
        
        orderChoice = self.ctrls.chSort.GetSelection()
        
        if orderChoice == 1:
            # Newest visited
            orderBy = "visited"
            descend = True
        elif orderChoice == 2:
            # Oldest visited
            orderBy = "visited"
            descend = False
        elif orderChoice == 3:
            # Alphabetically reverse
            orderBy = "word"
            descend = True
        else:   # orderChoice == 0:
            # Alphabetically
            orderBy = "word"
            descend = False

        if searchTxt == "%":
            self.listContent = self.pWiki.getWikiData()\
                    .getWikiWordMatchTermsWith("", orderBy=orderBy,
                    descend=descend)
            return

        self.listContent = self.pWiki.getWikiData().getWikiWordMatchTermsWith(
                searchTxt, orderBy=orderBy, descend=descend)


    def activateSelectedWikiWords(self, tabMode):
        sel = self.ctrls.lb.GetSelections()
        if len(sel) > 0:
            self.value = tuple(self.listContent[s] for s in sel)
        else:
            entered = self.ctrls.text.GetValue()

            if len(entered) == 0:
                # Nothing entered probably means the user doesn't want to
                # continue, so return True
                return True

            if not self.pWiki.getWikiDocument().isDefinedWikiLinkTerm(entered):
                langHelper = wx.GetApp().createWikiLanguageHelper(
                        self.pWiki.getWikiDefaultWikiLanguage())
                wikiWord = langHelper.extractWikiWordFromLink(entered,
                        self.pWiki.getWikiDocument())

                if wikiWord is not None and \
                        self.pWiki.getWikiDocument().isDefinedWikiLinkTerm(
                                wikiWord):
                    self.value = ((wikiWord, 0,
                            self.pWiki.getWikiDocument()\
                            .getWikiPageNameForLinkTerm(wikiWord), -1),)
                else:
                    self._fillListContent(entered)
                    if len(self.listContent) > 0:
                        self.value = (self.listContent[0],)
                    else:
                        if wikiWord is None:
                            self.pWiki.displayErrorMessage(
                                    _("'%s' is an invalid WikiWord") % entered)
                            # Entered text is not a valid wiki word
                            self.ctrls.text.SetFocus()
                            return False

                        if self.pWiki.getConfig().getboolean("main",
                                "openWordDialog_askForCreateWhenNonexistingWord",
                                True):
                            # wikiWord is valid but nonexisting, so maybe create it?
                            answer = wx.MessageBox(
                                    _("'%s' is not an existing wikiword. Create?") %
                                    wikiWord, _("Create"),
                                    wx.YES_NO | wx.YES_DEFAULT | wx.ICON_QUESTION, self)

                            if answer != wx.YES:
                                self.ctrls.text.SetFocus()
                                return False

                        self.value = ((wikiWord, 0, wikiWord, -1, -1),)
            else:
                self.value = ((entered, 0, entered, -1, -1),)

        if self.pWiki.activatePageByUnifiedName("wikipage/" + self.value[0][2],
                tabMode=tabMode, firstcharpos=self.value[0][3],
                charlength=self.value[0][4]) is None:   # TODO: Go to charPos
            return True   # False instead ?

        for term in self.value[1:]:
            if self.pWiki.activatePageByUnifiedName("wikipage/" + term[2],
                    tabMode=3, firstcharpos=term[3],
                    charlength=term[4]) is None:   # TODO: Go to charPos
                break

        return True


    def GetValue(self):
        return self.value

    def OnText(self, evt):
        if self.ignoreTextChange:
            self.ignoreTextChange -= 1
            return

        text = self.ctrls.text.GetValue()  # evt.GetString())
        
        listBox = self.ctrls.lb

        listBox.Freeze()
        try:
            listBox.Clear()
            self._fillListContent(text)

            listBox.AppendItems([term[0] for term in self.listContent])

#             for term in self.listContent:
#                 listBox.Append(term[0])
        finally:
            listBox.Thaw()


    def OnChoiceSort(self, evt):
        self.pWiki.getConfig().set("main", "openWikiWordDialog_sortOrder",
                self.ctrls.chSort.GetSelection())

        self.OnText(evt)


    def OnListBox(self, evt):
        sel = self.ctrls.lb.GetSelections()
        if len(sel) > 0:
            sel = sel[0]
            if self.listContent[sel][0] != self.listContent[sel][2]:
                self.ctrls.stLinkTo.SetLabel(_("Links to:") + " " +
                        self.listContent[sel][2])
            else:
                self.ctrls.stLinkTo.SetLabel("")
            self.ignoreTextChange += 1
            self.ctrls.text.SetValue(self.listContent[sel][0])
        else:
            self.ctrls.stLinkTo.SetLabel("")


    def OnCharText(self, evt):
        if (evt.GetKeyCode() == wx.WXK_DOWN) and not self.ctrls.lb.IsEmpty():
            self.ctrls.lb.SetFocus()
            self.ctrls.lb.SetSelection(0)
            self.OnListBox(None)  # TODO Check if it works for non-Windows
        elif (evt.GetKeyCode() == wx.WXK_UP):
            pass
        else:
            evt.Skip()


    def OnCharListBox(self, evt):
        if (evt.GetKeyCode() == wx.WXK_UP) and (self.ctrls.lb.GetSelections() == (0,)):
            self.ctrls.text.SetFocus()
            self.ctrls.lb.Deselect(0)
            self.OnListBox(None)  # TODO Check if it works for non-Windows
            self.ctrls.text.SetSelection(-1, -1)
        else:
            evt.Skip()
            
    def OnKeyDownListBox(self, evt):
        accP = getAccelPairFromKeyDown(evt)
        if accP in ((wx.ACCEL_NORMAL, wx.WXK_DELETE),
                (wx.ACCEL_NORMAL, wx.WXK_NUMPAD_DELETE)):
            self.OnDelete(evt)
        else:
            evt.Skip()

            
    def OnCreate(self, evt):
        """
        Create new WikiWord
        """
        langHelper = wx.GetApp().createWikiLanguageHelper(
                self.pWiki.getWikiDefaultWikiLanguage(),
                self.pWiki.getWikiDocument())
        entered = self.ctrls.text.GetValue()
        wikiWord = langHelper.extractWikiWordFromLink(entered)

        if wikiWord is None:
            self.pWiki.displayErrorMessage(_("'%s' is an invalid WikiWord") %
                    entered)
            self.ctrls.text.SetFocus()
            return
        
        if not self.pWiki.getWikiDocument().isCreatableWikiWord(wikiWord):
            self.pWiki.displayErrorMessage(_("'%s' exists already") % wikiWord)
            self.ctrls.text.SetFocus()
            return

        self.value = (wikiWord, 0, wikiWord, -1)
        self.pWiki.activatePageByUnifiedName("wikipage/" + wikiWord,
                tabMode=0)
        self.EndModal(wx.ID_OK)


    def OnDelete(self, evt):
        sellen = len(self.ctrls.lb.GetSelections())
        if sellen > 0:
            if self.pWiki.getConfig().getboolean("main", "trashcan_askOnDelete",
                    True):
                answer = wx.MessageBox(
                        _("Do you want to delete %i wiki page(s)?") % sellen,
                        ("Delete Wiki Page(s)"),
                        wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION, self)
                if answer != wx.YES:
                    return

            self.pWiki.saveAllDocPages()
            for s in self.ctrls.lb.GetSelections():
                delword = self.listContent[s][2]
                # Un-alias word
                delword = self.pWiki.getWikiDocument()\
                        .getWikiPageNameForLinkTerm(delword)

                if delword is not None:
                    page = self.pWiki.getWikiDocument().getWikiPage(delword)
                    page.deletePageToTrashcan()
                    
                    # self.pWiki.getWikiData().deleteWord(delword)
        
                    # trigger hooks
                    self.pWiki.hooks.deletedWikiWord(self.pWiki, delword)

#                     p2 = {}
#                     p2["deleted page"] = True
#                     p2["deleted wiki page"] = True
#                     p2["wikiWord"] = delword
#                     self.pWiki.fireMiscEventProps(p2)
            
#             self.pWiki.pageHistory.goAfterDeletion()

            self.EndModal(wx.ID_OK)

 
 
    def OnNewTab(self, evt):
        if self.activateSelectedWikiWords(2):
            self.EndModal(wx.ID_OK)

    def OnNewTabBackground(self, evt):
        self.activateSelectedWikiWords(3)



class ChooseWikiWordDialog(wx.Dialog, ModalDialogMixin):
    """
    Used to allow selection from list of parents, parentless words, children
    or bookmarked words.
    """
    def __init__(self, pWiki, ID, words, motionType, title=None, default=None,
                 pos=wx.DefaultPosition, size=wx.DefaultSize):
#         d = wx.PreDialog()
#         self.PostCreate(d)

        wx.Dialog.__init__(self)
        
        self.pWiki = pWiki
        res = wx.xrc.XmlResource.Get()
        res.LoadDialog(self, self.pWiki, "ChooseWikiWordDialog")
        
        self.ctrls = XrcControls(self)
        
        if title is not None:
            self.SetTitle(title)

        self.ctrls.staTitle.SetLabel(title)
        
        self.motionType = motionType
        self.unsortedWords = words

        self.ctrls.cbSortAlphabetically.SetValue(
                self.pWiki.getConfig().get("main",
                "chooseWikiWordDialog_sortOrder") == "AlphaAsc")

        self._sortAndFillWords()
        
        self.ctrls.btnOk.SetId(wx.ID_OK)
        self.ctrls.btnCancel.SetId(wx.ID_CANCEL)

        if len(words) > 0:
            # Set default selection (if it exists)
            # Set to first item otherwise
            if default is not None:
                selPos = self.ctrls.lb.FindString(default)
                if selPos == -1:
                    selPos = 0
            else:
                selPos = 0

            self.ctrls.lb.SetSelection(selPos)

        # Fixes focus bug under Linux
        self.SetFocus()

        self.Bind(wx.EVT_BUTTON, self.OnDelete, id=GUI_ID.btnDelete)
        self.Bind(wx.EVT_BUTTON, self.OnNewTab, id=GUI_ID.btnNewTab)
        self.Bind(wx.EVT_BUTTON, self.OnOk, id=wx.ID_OK)
        self.Bind(wx.EVT_LISTBOX_DCLICK, self.OnOk, id=GUI_ID.lb)
        self.Bind(wx.EVT_CHECKBOX, self.OnCbSortAlphabetically, id=GUI_ID.cbSortAlphabetically)


    def OnDelete(self, evt):
        sellen = len(self.ctrls.lb.GetSelections())
        if sellen > 0:
            if self.pWiki.getConfig().getboolean("main", "trashcan_askOnDelete",
                    True):
                answer = wx.MessageBox(
                        _("Do you want to delete %i wiki page(s)?") % sellen,
                        ("Delete Wiki Page(s)"),
                        wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION, self)
    
                if answer != wx.YES:
                    return

            self.pWiki.saveAllDocPages()
            for s in self.ctrls.lb.GetSelections():
                delword = self.words[s]
                # Un-alias word
                delword = self.pWiki.getWikiDocument()\
                        .getWikiPageNameForLinkTerm(delword)

                if delword is not None:
                    page = self.pWiki.getWikiDocument().getWikiPage(delword)
                    page.deletePageToTrashcan()
                    
                    # self.pWiki.getWikiData().deleteWord(delword)
        
                    # trigger hooks
                    self.pWiki.hooks.deletedWikiWord(self.pWiki, delword)
                    
#             self.pWiki.pageHistory.goAfterDeletion()

            self.EndModal(wx.ID_OK)


    def OnOk(self, evt):
        self.activateSelected(False)
#         sels = self.ctrls.lb.GetSelections()
#         if len(sels) != 1:
#             return # We can only go to exactly one wiki word
#             
#         wikiWord = self.words[sels[0]]
#         try:
#             self.pWiki.openWikiPage(wikiWord, forceTreeSyncFromRoot=True,
#                     motionType=self.motionType)
#         finally:
#             self.EndModal(GUI_ID.btnDelete)


    def OnNewTab(self, evt):
        self.activateSelected(True)

        
    def activateSelected(self, allNewTabs):
        """
        allNewTabs -- True: All selected words go to newly created tabs,
                False: The first selected word changes current tab
        """
        selIdxs = self.ctrls.lb.GetSelections()
        if len(selIdxs) == 0:
            return

        try:
            if not allNewTabs:
                self.pWiki.openWikiPage(self.words[selIdxs[0]],
                        forceTreeSyncFromRoot=True, motionType=self.motionType)

                selWords = [self.words[idx] for idx in selIdxs[1:]]
            else:
                selWords = [self.words[idx] for idx in selIdxs]

            for word in selWords:
                if self.pWiki.activatePageByUnifiedName("wikipage/" + word,
                        2) is None:
                    break
        finally:
            self.EndModal(wx.ID_OK)

 
    def OnCbSortAlphabetically(self, evt):
        self.pWiki.getConfig().set("main",
                "chooseWikiWordDialog_sortOrder", ("AlphaAsc" if
                self.ctrls.cbSortAlphabetically.GetValue() else "None"))
        self._sortAndFillWords()

 
    def _sortAndFillWords(self):
        """
        Sort words according to settings in dialog.
        """
        self.words = self.unsortedWords[:]
        if self.ctrls.cbSortAlphabetically.GetValue():
            self.pWiki.getCollator().sort(self.words)
        
        self.ctrls.lb.Set(self.words)




class RenameWikiWordDialog(wx.Dialog, ModalDialogMixin):
    def __init__(self, mainControl, fromWikiWord, parent, ID, title=None,
                 pos=wx.DefaultPosition, size=wx.DefaultSize,
                 style=wx.NO_3D):

        wx.Dialog.__init__(self)

        self.mainControl = mainControl
        self.fromWikiWord = fromWikiWord

        self.value = None

        res = wx.xrc.XmlResource.Get()
        res.LoadDialog(self, parent, "RenameWikiWordDialog")

        if title is not None:
            self.SetTitle(title)

        self.ctrls = XrcControls(self)

        self.ctrls.btnOk.SetId(wx.ID_OK)
        self.ctrls.btnOk = self.ctrls._byId(wx.ID_OK)
        self.ctrls.btnCancel.SetId(wx.ID_CANCEL)

        self.ctrls.stFromWikiWord.SetLabel(self.fromWikiWord)
        self.ctrls.tfToWikiWord.SetValue(self.fromWikiWord)
        self.ctrls.btnOk.Enable(False)
#         self.ctrls.cbModifyLinks.SetValue(self.mainControl.getConfig().getboolean(
#                 "main", "wikiWord_renameDefault_modifyWikiLinks", False))
        self.ctrls.chModifyLinks.SetSelection(
                {"off": 0, "false": 0, "advanced": 1, "true": 1, "simple":2}
                .get(self.mainControl.getConfig()
                    .get("main", "wikiWord_renameDefault_modifyWikiLinks", "off")
                    .lower(), 0))
        self.ctrls.cbRenameSubPages.SetValue(self.mainControl.getConfig().getboolean(
                "main", "wikiWord_renameDefault_renameSubPages", True))

        # Fixes focus bug under Linux
        self.SetFocus()

        self.Bind(wx.EVT_BUTTON, self.OnOk, id=wx.ID_OK)
        self.Bind(wx.EVT_TEXT, self.OnTextToWikiWord, id=GUI_ID.tfToWikiWord)



#         self.Bind(wx.EVT_BUTTON, self.OnOk, id=wx.ID_OK)
# 
#         self.ctrls.text.Bind(wx.EVT_CHAR, self.OnCharText)
#         self.ctrls.lb.Bind(wx.EVT_CHAR, self.OnCharListBox)
#         self.Bind(wx.EVT_LISTBOX, self.OnListBox, id=ID)
#         self.Bind(wx.EVT_LISTBOX_DCLICK, self.OnOk, id=GUI_ID.lb)
#         self.Bind(wx.EVT_BUTTON, self.OnCreate, id=GUI_ID.btnCreate)
#         self.Bind(wx.EVT_BUTTON, self.OnDelete, id=GUI_ID.btnDelete)
#         self.Bind(wx.EVT_BUTTON, self.OnNewTab, id=GUI_ID.btnNewTab)
#         self.Bind(wx.EVT_BUTTON, self.OnNewTabBackground, id=GUI_ID.btnNewTabBackground)



    def OnOk(self, evt):
        msg = self._checkValidToWikiWord()
        if msg is not None:
            return

        toWikiWord = self.ctrls.tfToWikiWord.GetValue()
        
        try:
            modifyText = (ModifyText.off, ModifyText.advanced, ModifyText.simple)[
                    self.ctrls.chModifyLinks.GetSelection()]
        except IndexError:
            modifyText = ModifyText.off
        
#         if self.ctrls.cbModifyLinks.GetValue():
#             modifyText = ModifyText.advanced
#         else:
#             modifyText = ModifyText.off


        try:
            self.mainControl.renameWikiWord(self.fromWikiWord, toWikiWord,
                    modifyText, self.ctrls.cbRenameSubPages.GetValue())
        except RenameWikiWordException as e:
            wx.MessageBox(_("Can't process renaming:\n%s") %
                    e.getFlowText(), _("Can't rename"),
                    wx.OK | wx.ICON_HAND, self)
            return
        except WikiDataException as e:
            traceback.print_exc()                
            self.displayErrorMessage(str(e))
        except (IOError, OSError, DbAccessError):
            pass

        self.EndModal(wx.ID_OK)


    def updateValidToWikiWord(self):
        msg = self._checkValidToWikiWord()
        if msg is None:
            self.ctrls.btnOk.Enable(True)
            self.ctrls.stErrorMessage.SetLabel("")
        else:
            self.ctrls.btnOk.Enable(False)
            self.ctrls.stErrorMessage.SetLabel(msg)


    def _checkValidToWikiWord(self):
        toWikiWord = self.ctrls.tfToWikiWord.GetValue()

        if not toWikiWord or len(toWikiWord) == 0:
            return "" # No error message, but disable OK
            
        langHelper = wx.GetApp().createWikiLanguageHelper(
                self.mainControl.getWikiDefaultWikiLanguage())

        errMsg = langHelper.checkForInvalidWikiWord(toWikiWord,
                self.mainControl.getWikiDocument())

        if errMsg:
            return errMsg   # _(u"Invalid wiki word. %s") % errMsg

        if self.fromWikiWord == toWikiWord:
            return _("Can't rename to itself")

        if not self.mainControl.getWikiDocument().isCreatableWikiWord(toWikiWord):
            return _("Word already exists")

        # Word is OK
        return None


    def OnTextToWikiWord(self, evt):
        evt.Skip()
        self.updateValidToWikiWord()


    def GetValue(self):
        return self.value



class SelectIconDialog(wx.Dialog, ModalDialogMixin):
    def __init__(self, parent, ID, iconCache, title="Select Icon",
                 pos=wx.DefaultPosition, size=wx.DefaultSize,
                 style=wx.NO_3D|wx.DEFAULT_DIALOG_STYLE|wx.RESIZE_BORDER):
        wx.Dialog.__init__(self, parent, ID, title, pos, size, style)

        self.iconCache = iconCache
        self.iconImageList = self.iconCache.iconImageList
        
        self.iconNames = [n for n in list(self.iconCache.iconLookupCache.keys())
                if not n.startswith("tb_")]
#         filter(lambda n: not n.startswith("tb_"),
#                 self.iconCache.iconLookupCache.keys())
        self.iconNames.sort()
        
        # Now continue with the normal construction of the dialog
        # contents
        sizer = wx.BoxSizer(wx.VERTICAL)

        label = wx.StaticText(self, -1, _("Select Icon"))
        sizer.Add(label, 0, wx.ALIGN_CENTRE|wx.ALL, 5)

        box = wx.BoxSizer(wx.VERTICAL)

        self.lc = wx.ListCtrl(self, -1, wx.DefaultPosition, wx.Size(145, 200), 
                style = wx.LC_REPORT | wx.LC_NO_HEADER)    ## | wx.BORDER_NONE
                
        self.lc.SetImageList(self.iconImageList, wx.IMAGE_LIST_SMALL)
        self.lc.InsertColumn(0, _("Icon"))

        for icn in self.iconNames:
            self.lc.InsertImageStringItem(sys.maxsize, icn,
                    self.iconCache.lookupIconIndex(icn))
#         self.lc.SetColumnWidth(0, wx.LIST_AUTOSIZE)
        autosizeColumn(self.lc, 0)
        
        
        box.Add(self.lc, 1, wx.ALIGN_CENTRE|wx.ALL|wx.EXPAND, 5)

        sizer.Add(box, 1, wx.GROW|wx.ALIGN_CENTER_VERTICAL|wx.ALL, 5)

        line = wx.StaticLine(self, -1, size=(20,-1), style=wx.LI_HORIZONTAL)
        sizer.Add(line, 0, wx.GROW|wx.ALIGN_CENTER_VERTICAL|wx.RIGHT|wx.TOP, 5)

        box = wx.BoxSizer(wx.HORIZONTAL)

        btn = wx.Button(self, wx.ID_OK, _(" OK "))
        btn.SetDefault()
        box.Add(btn, 0, wx.ALIGN_CENTRE|wx.ALL, 5)

        btn = wx.Button(self, wx.ID_CANCEL, _(" Cancel "))
        box.Add(btn, 0, wx.ALIGN_CENTRE|wx.ALL, 5)

        sizer.Add(box, 0, wx.ALIGN_CENTER_VERTICAL|wx.ALL, 5)

        self.SetSizer(sizer)
        self.SetAutoLayout(True)
        sizer.Fit(self)

        self.value = None
        
        # Fixes focus bug under Linux
        self.SetFocus()

        self.Bind(wx.EVT_BUTTON, self.OnOk, id=wx.ID_OK)
        self.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self.OnOk, id=self.lc.GetId())

    def GetValue(self):
        """
        Return name of selected icon or None
        """
        return self.value


    def OnOk(self, evt):
        no = self.lc.GetNextItem(-1, state = wx.LIST_STATE_SELECTED)
        if no > -1:
            self.value = self.iconNames[no]
        else:
            self.value = None
            
        self.EndModal(wx.ID_OK)



class DateformatDialog(wx.Dialog):

    # HTML explanation for strftime:
    FORMATHELP = N_(r"""<html>
<body bgcolor="#FFFFFF">

<table border="1" align="center" style="border-collapse: collapse">
    <tr><td align="center" valign="baseline"><b>Directive</b></td>
        <td align="left"><b>Meaning</b></td></tr>
    <tr><td align="center" valign="baseline"><code>%a</code></td>
        <td align="left">Locale's abbreviated weekday name.</td></tr>
    <tr><td align="center" valign="baseline"><code>%A</code></td>
        <td align="left">Locale's full weekday name.</td></tr>
    <tr><td align="center" valign="baseline"><code>%b</code></td>
        <td align="left">Locale's abbreviated month name.</td></tr>
    <tr><td align="center" valign="baseline"><code>%B</code></td>
        <td align="left">Locale's full month name.</td></tr>
    <tr><td align="center" valign="baseline"><code>%c</code></td>
        <td align="left">Locale's appropriate date and time representation.</td></tr>
    <tr><td align="center" valign="baseline"><code>%d</code></td>
        <td align="left">Day of the month as a decimal number [01,31].</td></tr>
    <tr><td align="center" valign="baseline"><code>%H</code></td>
        <td align="left">Hour (24-hour clock) as a decimal number [00,23].</td></tr>
    <tr><td align="center" valign="baseline"><code>%I</code></td>
        <td align="left">Hour (12-hour clock) as a decimal number [01,12].</td></tr>
    <tr><td align="center" valign="baseline"><code>%j</code></td>
        <td align="left">Day of the year as a decimal number [001,366].</td></tr>
    <tr><td align="center" valign="baseline"><code>%m</code></td>
        <td align="left">Month as a decimal number [01,12].</td></tr>
    <tr><td align="center" valign="baseline"><code>%M</code></td>
        <td align="left">Minute as a decimal number [00,59].</td></tr>
    <tr><td align="center" valign="baseline"><code>%p</code></td>
        <td align="left">Locale's equivalent of either AM or PM.</td></tr>
    <tr><td align="center" valign="baseline"><code>%S</code></td>
        <td align="left">Second as a decimal number [00,61].</td></tr>
    <tr><td align="center" valign="baseline"><code>%u</code></td>
        <td align="left">Weekday as a decimal number [1(Monday),7].</td></tr>
    <tr><td align="center" valign="baseline"><code>%U</code></td>
        <td align="left">Week number of the year (Sunday as the first day of the
                week) as a decimal number [00,53].  All days in a new year
                preceding the first Sunday are considered to be in week 0.</td></tr>
    <tr><td align="center" valign="baseline"><code>%w</code></td>
        <td align="left">Weekday as a decimal number [0(Sunday),6].</td></tr>
    <tr><td align="center" valign="baseline"><code>%W</code></td>
        <td align="left">Week number of the year (Monday as the first day of the
                week) as a decimal number [00,53].  All days in a new year
                preceding the first Monday are considered to be in week 0.</td></tr>
    <tr><td align="center" valign="baseline"><code>%x</code></td>
        <td align="left">Locale's appropriate date representation.</td></tr>
    <tr><td align="center" valign="baseline"><code>%X</code></td>
        <td align="left">Locale's appropriate time representation.</td></tr>
    <tr><td align="center" valign="baseline"><code>%y</code></td>
        <td align="left">Year without century as a decimal number [00,99].</td></tr>
    <tr><td align="center" valign="baseline"><code>%Y</code></td>
        <td align="left">Year with century as a decimal number.</td></tr>
    <tr><td align="center" valign="baseline"><code>%Z</code></td>
        <td align="left">Time zone name (no characters if no time zone exists).</td></tr>
    <tr><td align="center" valign="baseline"><code>%%</code></td>
        <td align="left">A literal "<tt class="character">%</tt>" character.</td></tr>
    <tr><td align="center" valign="baseline"><code>\n</code></td>
        <td align="left">A newline.</td></tr>
    <tr><td align="center" valign="baseline"><code>\\</code></td>
        <td align="left">A literal "<tt class="character">\</tt>" character.</td></tr>
    </tbody>
</table>
</body>
</html>
""")

    def __init__(self, parent, ID, mainControl, title=None,
                 pos=wx.DefaultPosition, size=wx.DefaultSize,
                 style=wx.NO_3D, deffmt=""):
        """
        deffmt -- Initial value for format string
        """
        wx.Dialog.__init__(self)
        
        self.mainControl = mainControl
        self.value = ""     
        res = wx.xrc.XmlResource.Get()
        res.LoadDialog(self, parent, "DateformatDialog")

        if title is not None:
            self.SetTitle(title)
        
        # Create HTML explanation
        html = wx.html.HtmlWindow(self, -1)
        html.SetPage(_(self.FORMATHELP))
        res.AttachUnknownControl("htmlExplain", html, self)
        
        self.ctrls = XrcControls(self)
        
        self.ctrls.btnOk.SetId(wx.ID_OK)
        self.ctrls.btnCancel.SetId(wx.ID_CANCEL)
        
        # Set dropdown list of recent time formats
        tfs = self.mainControl.getConfig().get("main", "recent_time_formats")
        self.recentFormats = [unescapeForIni(s) for s in tfs.split(";")]
        for f in self.recentFormats:
            self.ctrls.fieldFormat.Append(f)

        self.ctrls.fieldFormat.SetValue(deffmt)
        self.OnText(None)
        
        # Fixes focus bug under Linux
        self.SetFocus()
        
        self.Bind(wx.EVT_BUTTON, self.OnOk, id=wx.ID_OK)
        self.Bind(wx.EVT_TEXT, self.OnText, id=XRCID("fieldFormat")) 


    def OnText(self, evt):
        preview = _("<invalid>")
        text = self.ctrls.fieldFormat.GetValue()
        try:
            preview = strftimeUB(text)
            self.value = text
        except:
#             traceback.print_exc()
            pass

        self.ctrls.fieldPreview.SetLabel(preview)
        
        
    def GetValue(self):
        return self.value
        
    
    def OnOk(self, evt):
        if self.value != "":
            # Update recent time formats list
            
            try:
                self.recentFormats.remove(self.value)
            except ValueError:
                pass
                
            self.recentFormats.insert(0, self.value)
            if len(self.recentFormats) > 10:
                self.recentFormats = self.recentFormats[:10]

            # Escape to store it in configuration
            tfs = ";".join([escapeForIni(f, ";") for f in self.recentFormats])
            self.mainControl.getConfig().set("main", "recent_time_formats", tfs)

        self.EndModal(wx.ID_OK)



class FontFaceDialog(wx.Dialog):
    """
    Presents a list of available fonts (its face names) and renders a sample
    string with currently selected face.
    """
    def __init__(self, parent, ID, mainControl, value="",
                 pos=wx.DefaultPosition, size=wx.DefaultSize,
                 style=wx.NO_3D):
        """
        value -- Current value of a text field containing a face name (used to
                 choose default item in the shown list box)
        """
        wx.Dialog.__init__(self)

        self.parent = parent
        self.mainControl = mainControl
        self.value = value

        res = wx.xrc.XmlResource.Get()
        res.LoadDialog(self, self.parent, "FontFaceDialog")

        self.ctrls = XrcControls(self)

        self.ctrls.btnOk.SetId(wx.ID_OK)
        self.ctrls.btnCancel.SetId(wx.ID_CANCEL)

        # Fill font listbox
        fenum = wx.FontEnumerator()
        fenum.EnumerateFacenames()
        facelist = fenum.GetFacenames()
        self.mainControl.getCollator().sort(facelist)

        for f in facelist:
            self.ctrls.lbFacenames.Append(f)
            
        if len(facelist) > 0:
            try:
                # In wxPython, this can throw an exception if self.value
                # does not match an item
                if not self.ctrls.lbFacenames.SetStringSelection(self.value):
                    self.ctrls.lbFacenames.SetSelection(0)
            except:
                self.ctrls.lbFacenames.SetSelection(0)

            self.OnFaceSelected(None)
            
        # Fixes focus bug under Linux
        self.SetFocus()
            
        self.Bind(wx.EVT_BUTTON, self.OnOk, id=wx.ID_OK)
        self.Bind(wx.EVT_LISTBOX, self.OnFaceSelected, id=GUI_ID.lbFacenames)
        self.Bind(wx.EVT_LISTBOX_DCLICK, self.OnOk, id=GUI_ID.lbFacenames)


    def OnOk(self, evt):
        self.value = self.ctrls.lbFacenames.GetStringSelection()
        evt.Skip()

        
    def OnFaceSelected(self, evt):
        face = self.ctrls.lbFacenames.GetStringSelection()
        font = wx.Font(12, wx.DEFAULT, wx.NORMAL, wx.NORMAL, False, face)
        self.ctrls.stFacePreview.SetLabel(face)
        self.ctrls.stFacePreview.SetFont(font)

    def GetValue(self):
        return self.value



class ExportDialog(wx.Dialog, ModalDialogMixin):
    def __init__(self, mainControl, ID, continuousExport=False, title=None,
                 pos=wx.DefaultPosition, size=wx.DefaultSize):
        from . import Exporters
        from .SearchAndReplace import SearchReplaceOperation

#         d = wx.PreDialog()
#         self.PostCreate(d)

        wx.Dialog.__init__(self)
        
        self.mainControl = mainControl
        self.value = None
        
        self.listPagesOperation = SearchReplaceOperation()
        self.continuousExport = continuousExport
        self.savedExports = None
        
        res = wx.xrc.XmlResource.Get()
        res.LoadDialog(self, self.mainControl, "ExportDialog")

        self.ctrls = XrcControls(self)

        if continuousExport:
            self.SetTitle(_("Continuous Export"))

        # In addition to exporter list, this set will contain type tags of all
        # supported exports (used for saved exports list).
        self.supportedExportTypes = set()

        self.emptyPanel = None

        exporterList = [] # List of tuples (<exporter object>, <export tag>,
                          # <readable description>, <additional options panel>)

        addOptSizer = LayerSizer()

        # TODO Move to e.g. ExportOperation.py
        for obtp in list(PluginManager.getSupportedExportTypes(mainControl,
                self.ctrls.additOptions, continuousExport).values()):
            panel = obtp[3]
            if panel is None:
                if self.emptyPanel is None:
                    # Necessary to avoid a crash        
                    self.emptyPanel = wx.Panel(self.ctrls.additOptions)

                panel = self.emptyPanel
            else:
                pass
                # panel.Fit()

            # Add Tuple (Exporter object, export type tag,
            #     export type description, additional options panel)
            exporterList.append((obtp[0], obtp[1], obtp[2], panel))
            self.supportedExportTypes.add(obtp[1])
            addOptSizer.Add(panel)

        mainControl.getCollator().sortByItem(exporterList, 2)

        self.ctrls.additOptions.SetSizer(addOptSizer)
        self.ctrls.additOptions.SetMinSize(addOptSizer.GetMinSize())

        self.ctrls.additOptions.Fit()
        self.Fit()

#         self.ctrls.additOptions.Fit()
#         mins = self.ctrls.additOptions.GetMinSize()
# 
#         self.ctrls.additOptions.SetMinSize(wx.Size(mins.width+10, mins.height+10))
#         self.Fit()

        self.exporterList = exporterList

        self.ctrls.btnOk.SetId(wx.ID_OK)
        self.ctrls.btnCancel.SetId(wx.ID_CANCEL)
        
        defdir = self.mainControl.getConfig().get("main", "export_default_dir",
                "")
        if defdir == "":
            defdir = self.mainControl.getLastActiveDir()

        self.ctrls.tfDestination.SetValue(defdir)

        for e in self.exporterList:
            e[3].Show(False)
            e[3].Enable(False)
            self.ctrls.chExportTo.Append(e[2])
            
#         # Enable first addit. options panel
#         self.exporterList[0][3].Enable(True)
#         self.exporterList[0][3].Show(True)

        exportTo = self.mainControl.getConfig().get("main",
                "export_lastDialogTag", "")

        selection = 0
        for i, e in enumerate(self.exporterList):
            if exportTo == e[1]:
                selection = i
                break

        self.ctrls.chExportTo.SetSelection(selection)
        self._refreshForEtype()
        self._refreshSavedExportsList()

        # Fixes focus bug under Linux
        self.SetFocus()

        self.Bind(wx.EVT_CHOICE, self.OnExportTo, id=GUI_ID.chExportTo)
        self.Bind(wx.EVT_CHOICE, self.OnChSelectedSet, id=GUI_ID.chSelectedSet)

        self.Bind(wx.EVT_LISTBOX_DCLICK, self.OnLoadAndRunExport, id=GUI_ID.lbSavedExports)

        self.Bind(wx.EVT_BUTTON, self.OnOk, id=wx.ID_OK)
        self.Bind(wx.EVT_BUTTON, self.OnSelectDest, id=GUI_ID.btnSelectDestination)
        self.Bind(wx.EVT_BUTTON, self.OnSaveExport, id=GUI_ID.btnSaveExport)
        self.Bind(wx.EVT_BUTTON, self.OnLoadExport, id=GUI_ID.btnLoadExport)
        self.Bind(wx.EVT_BUTTON, self.OnLoadAndRunExport, id=GUI_ID.btnLoadAndRunExport)
        self.Bind(wx.EVT_BUTTON, self.OnDeleteExports, id=GUI_ID.btnDeleteExports)


    def _refreshForEtype(self):
        for e in self.exporterList:
            e[3].Show(False)
            e[3].Enable(False)

        ob, etype, desc, panel = \
                self.exporterList[self.ctrls.chExportTo.GetSelection()][:4]

        # Enable appropriate addit. options panel
        panel.Enable(True)
        panel.Show(True)

        expDestWildcards = ob.getExportDestinationWildcards(etype)

        if expDestWildcards is None:
            # Directory destination
            self.ctrls.stDestination.SetLabel(_("Destination directory:"))
        else:
            # File destination
            self.ctrls.stDestination.SetLabel(_("Destination file:"))


    def OnExportTo(self, evt):
        self._refreshForEtype()
        self.mainControl.getConfig().set("main", "export_lastDialogTag",
                self.exporterList[self.ctrls.chExportTo.GetSelection()][1])
        evt.Skip()


    def OnChSelectedSet(self, evt):
        selset = self.ctrls.chSelectedSet.GetSelection()
        if selset == 3:  # Custom
            from .SearchAndReplaceDialogs import SearchWikiDialog

            dlg = SearchWikiDialog(self, self.mainControl, -1,
                    value=self.listPagesOperation)
            if dlg.ShowModal() == wx.ID_OK:
                self.listPagesOperation = dlg.getValue()
            dlg.Destroy()

    def OnOk(self, evt):
        self._runExporter()

        
    def _runExporter(self):
        # Run exporter
        ob, etype, desc, panel = \
                self.exporterList[self.ctrls.chExportTo.GetSelection()][:4]

        # If this returns None, export goes to a directory
        expDestWildcards = ob.getExportDestinationWildcards(etype)
        if expDestWildcards is None:
            # Export to a directory
            if not exists(pathEnc(self.ctrls.tfDestination.GetValue())):
                self.mainControl.displayErrorMessage(
                        _("Destination directory does not exist"))
                return
            
            if not isdir(pathEnc(self.ctrls.tfDestination.GetValue())):
                self.mainControl.displayErrorMessage(
                        _("Destination must be a directory"))
                return
        else:
            if exists(pathEnc(self.ctrls.tfDestination.GetValue())) and \
                    not isfile(pathEnc(self.ctrls.tfDestination.GetValue())):
                self.mainControl.displayErrorMessage(
                        _("Destination must be a file"))
                return

        sarOp = self._getEffectiveListWikiPagesOperation()
        if sarOp is None:
            return

        if panel is self.emptyPanel:
            panel = None

        pgh = ProgressHandler(_("Exporting"), "", 0, self)
        pgh.open(0)
        pgh.update(0, _("Preparing"))

        try:
            if self.continuousExport:
                ob.startContinuousExport(self.mainControl.getWikiDocument(),
                        sarOp, etype, self.ctrls.tfDestination.GetValue(),
                        self.ctrls.compatFilenames.GetValue(), ob.getAddOpt(panel),
                        pgh)
    
                self.value = ob
            else:
                wordList = self.mainControl.getWikiDocument().searchWiki(sarOp,
                        True)
        
                try:
                    ob.export(self.mainControl.getWikiDocument(), wordList, etype, 
                            self.ctrls.tfDestination.GetValue(), 
                            self.ctrls.compatFilenames.GetValue(), ob.getAddOpt(panel),
                            pgh)
                except ExportException as e:
                    self.mainControl.displayErrorMessage(_("Error while exporting"),
                    str(e))

        finally:
            pgh.close()
            self.EndModal(wx.ID_OK)

        
    def OnSelectDest(self, evt):
        ob, etype, desc, panel = \
                self.exporterList[self.ctrls.chExportTo.GetSelection()][:4]

        expDestWildcards = ob.getExportDestinationWildcards(etype)

        if expDestWildcards is None:
            # Only transfer between GUI elements, so no unicode conversion
            seldir = wx.DirSelector(_("Select Export Directory"),
                    self.ctrls.tfDestination.GetValue(),
                    style=wx.DD_DEFAULT_STYLE|wx.DD_NEW_DIR_BUTTON, parent=self)
                
            if seldir:
                self.ctrls.tfDestination.SetValue(seldir)

        else:
            # Build wildcard string
            wcs = []
            for wd, wp in expDestWildcards:
                wcs.append(wd)
                wcs.append(wp)
                
            wcs.append(_("All files (*.*)"))
            wcs.append("*")
            
            wcs = "|".join(wcs)
            
            selfile = wx.FileSelector(_("Select Export File"),
                    self.ctrls.tfDestination.GetValue(),
                    default_filename = "", default_extension = "",
                    wildcard = wcs, flags=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
                    parent=self)

            if selfile:
                self.ctrls.tfDestination.SetValue(selfile)


    def GetValue(self):
        return self.value


    def _getEffectiveListWikiPagesOperation(self):
        """
        Return the list operation appropriate for the current GUI settings.
        Shows message in case of an error and returns None
        """
        from . import SearchAndReplace as Sar

        # Create wordList (what to export)
        selset = self.ctrls.chSelectedSet.GetSelection()
        root = self.mainControl.getCurrentWikiWord()

        if root is None and selset in (0, 1):
            self.mainControl.displayErrorMessage(
                    _("No real wiki word selected as root"))
            return None

        if selset == 3:
            return self.listPagesOperation

        lpOp = Sar.ListWikiPagesOperation()

        if selset == 0:
            # single page
            item = Sar.ListItemWithSubtreeWikiPagesNode(lpOp, [root], 0)
            lpOp.setSearchOpTree(item)
            lpOp.ordering = "asroottree"  # Slow, but more intuitive
        elif selset == 1:
            # subtree
            item = Sar.ListItemWithSubtreeWikiPagesNode(lpOp, [root], -1)
            lpOp.setSearchOpTree(item)
            lpOp.ordering = "asroottree"
        elif selset == 2:
            # whole wiki
            item = Sar.AllWikiPagesNode(lpOp)
            lpOp.setSearchOpTree(item)
            lpOp.ordering = "asroottree"
        else:
            raise InternalError("Unknown selection for export set")

        result = Sar.SearchReplaceOperation()
        result.listWikiPagesOp = lpOp

        return result


    def _refreshSavedExportsList(self):
        from . import Exporters

        self.savedExports = Exporters.retrieveSavedExportsList(self.mainControl,
                self.mainControl.getWikiData(), self.continuousExport)

        self.ctrls.lbSavedExports.Clear()
        for exportName, xmlNode in self.savedExports:
            self.ctrls.lbSavedExports.Append(exportName)


    def OnSaveExport(self, evt):
        defValue = ""
        
        sels = self.ctrls.lbSavedExports.GetSelections()
        
        if len(sels) == 1:
            defValue = self.savedExports[sels[0]][0]

        while True:
            title = wx.GetTextFromUser(_("Title:"),
                    _("Choose export title"), defValue, self)
            if title == "":
                return  # Cancel
                
            if ("savedexport/" + title) in self.mainControl.getWikiData()\
                    .getDataBlockUnifNamesStartingWith(
                    "savedexport/" + title):

                answer = wx.MessageBox(
                        _("Do you want to overwrite existing export '%s'?") %
                        title, _("Overwrite export"),
                        wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION, self)
                if answer != wx.YES:
                    continue

            xmlDoc = minidom.getDOMImplementation().createDocument(None, None, None)
            xmlHead = xmlDoc.createElement("savedExport")

            xmlNode = self._buildSavedExport(xmlHead, xmlDoc)
            if xmlNode is None:
                return
            
            xmlDoc.appendChild(xmlNode)
            content = xmlDoc.toxml("utf-8")
            xmlDoc.unlink()
            self.mainControl.getWikiData().storeDataBlock(
                    "savedexport/" + title, content,
                    storeHint=DATABLOCK_STOREHINT_INTERN)
            
            self._refreshSavedExportsList()
            return


    def OnLoadExport(self, evt):
        self._loadExport()
        
        
    def OnLoadAndRunExport(self, evt):
        if self._loadExport():
            self._runExporter()


    def OnDeleteExports(self, evt):
        sels = self.ctrls.lbSavedExports.GetSelections()
        
        if len(sels) == 0:
            return

        answer = wx.MessageBox(
                _("Do you want to delete %i export(s)?") % len(sels),
                _("Delete export"),
                wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION, self)
        if answer != wx.YES:
            return

        for s in sels:
            self.mainControl.getWikiData().deleteDataBlock(
                    "savedexport/" + self.savedExports[s][0])
        self._refreshSavedExportsList()


    def _loadExport(self):
        sels = self.ctrls.lbSavedExports.GetSelections()
        
        if len(sels) != 1:
            return False

        xmlNode = self.savedExports[sels[0]][1]
        return self._showExportProfile(xmlNode)


    def _buildSavedExport(self, xmlHead, xmlDoc):
        """
        Builds the saved export as XML code from GUI settings.
        Returns the xmlHead (aka XML "savedExport") node or None in
        case of an error.
        """

        ob, etype, desc, panel = \
                self.exporterList[self.ctrls.chExportTo.GetSelection()][:4]
        
        addOptVer = ob.getAddOptVersion()
        
        if addOptVer == -1:
            # An addOpt version of -1 means that the addOpt value does not
            # have a defined format and therefore can't be stored
            self.mainControl.displayErrorMessage(
                    _("Selected export type does not support saving"))
            return None   # TODO Error message!!

        Serialization.serToXmlUnicode(xmlHead, xmlDoc, "exportTypeName", etype)

        Serialization.serToXmlUnicode(xmlHead, xmlDoc, "destinationPath",
                self.ctrls.tfDestination.GetValue())

        pageSetXml = xmlDoc.createElement("pageSet")
        xmlHead.appendChild(pageSetXml)

        sarOp = self._getEffectiveListWikiPagesOperation()
        if sarOp is None:
            return None

        sarOp.serializeToXml(pageSetXml, xmlDoc)

        addOptXml = xmlDoc.createElement("additionalOptions")
        xmlHead.appendChild(addOptXml)

        addOptXml.setAttribute("version", str(addOptVer))
        addOptXml.setAttribute("type", "simpleTuple")

        Serialization.convertTupleToXml(addOptXml, xmlDoc, ob.getAddOpt(panel))

        return xmlHead



    def _showExportProfile(self, xmlNode):
        from .SearchAndReplace import SearchReplaceOperation

        try:
            etypeProfile = Serialization.serFromXmlUnicode(xmlNode,
                    "exportTypeName")

            for sel, (ob, etype, desc, panel) in enumerate(self.exporterList):
                if etype == etypeProfile:
                    break
            else:
                self.mainControl.displayErrorMessage(
                        _("Export type '%s' of saved export is not supported") %
                        etypeProfile)
                return False

            addOptXml = Serialization.findXmlElementFlat(xmlNode,
                    "additionalOptions")

            addOptVersion = int(addOptXml.getAttribute("version"))

            if addOptVersion != ob.getAddOptVersion():
                self.mainControl.displayErrorMessage(
                        _("Saved export uses different version for additional "
                        "options than current export\nExport type: '%s'\n"
                        "Saved export version: %i\nCurrent export version: %i") %
                        (etypeProfile, addOptVersion, ob.getAddOptVersion()))
                return False 

            if addOptXml.getAttribute("type") != "simpleTuple":
                self.mainControl.displayErrorMessage(
                        _("Type of additional option storage ('%s') is unknown") %
                        addOptXml.getAttribute("type"))
                return False
    
            pageSetXml = Serialization.findXmlElementFlat(xmlNode, "pageSet")
            
            sarOp = SearchReplaceOperation()
    
            sarOp.serializeFromXml(pageSetXml)
    
            addOpt = Serialization.convertTupleFromXml(addOptXml)
    
            self.listPagesOperation = sarOp
            self.ctrls.chSelectedSet.SetSelection(3)
            self.ctrls.chExportTo.SetSelection(sel)
            ob.setAddOpt(addOpt, panel)
    
            self.ctrls.tfDestination.SetValue(
                    Serialization.serFromXmlUnicode(xmlNode, "destinationPath"))
                    
            self._refreshForEtype()
            
            return True
        except SerializationException as e:
            self.mainControl.displayErrorMessage(_("Error during retrieving "
                    "saved export: ") + e.message)



class ImportDialog(wx.Dialog):
    def __init__(self, parent, ID, mainControl, title="Import",
                 pos=wx.DefaultPosition, size=wx.DefaultSize):
                    
        wx.Dialog.__init__(self)

        from . import Importers

        self.parent = parent
        self.mainControl = mainControl
        
        res = wx.xrc.XmlResource.Get()
        res.LoadDialog(self, self.parent, "ImportDialog")

        self.ctrls = XrcControls(self)

        self.emptyPanel = None
        
        importerList = [] # List of tuples (<importer object>, <import tag=type>,
                          # <readable description>, <additional options panel>)
        
        addOptSizer = LayerSizer()

        for ob in Importers.describeImporters(self.mainControl):   # TODO search plugins
            for tp in ob.getImportTypes(self.ctrls.additOptions):
                panel = tp[2]
                if panel is None:
                    if self.emptyPanel is None:
                        # Necessary to avoid a crash        
                        self.emptyPanel = wx.Panel(self.ctrls.additOptions)
                        # self.emptyPanel.Fit()
                    panel = self.emptyPanel
                else:
                    pass
                    # panel.Fit()

                # Add Tuple (Importer object, import type tag,
                #     import type description, additional options panel)
                importerList.append((ob, tp[0], tp[1], panel))
                addOptSizer.Add(panel)

        self.ctrls.additOptions.SetSizer(addOptSizer)
        self.ctrls.additOptions.SetMinSize(addOptSizer.GetMinSize())

        self.ctrls.additOptions.Fit()
        self.Fit()

#         self.ctrls.additOptions.Fit()
#         mins = self.ctrls.additOptions.GetMinSize()
#         
#         self.ctrls.additOptions.SetMinSize(wx.Size(mins.width+10, mins.height+10))
#         self.Fit()

        
        self.importerList = importerList

        self.ctrls.btnOk.SetId(wx.ID_OK)
        self.ctrls.btnCancel.SetId(wx.ID_CANCEL)
        
        self.ctrls.tfSource.SetValue(self.mainControl.getLastActiveDir())
        
        for e in self.importerList:
            e[3].Show(False)
            e[3].Enable(False)
            self.ctrls.chImportFormat.Append(e[2])
            
#         # Enable first addit. options panel
#         self.importerList[0][3].Enable(True)
#         self.importerList[0][3].Show(True)
        self.ctrls.chImportFormat.SetSelection(0)
        self._refreshForItype()
        
        # Fixes focus bug under Linux
        self.SetFocus()

        self.Bind(wx.EVT_CHOICE, self.OnImportFormat, id=GUI_ID.chImportFormat)

        self.Bind(wx.EVT_BUTTON, self.OnOk, id=wx.ID_OK)
        self.Bind(wx.EVT_BUTTON, self.OnSelectSrc, id=GUI_ID.btnSelectSource)


    def _refreshForItype(self):
        """
        Refresh GUI depending on chosen import type
        """
        for e in self.importerList:
            e[3].Show(False)
            e[3].Enable(False)

        ob, itype, desc, panel = \
                self.importerList[self.ctrls.chImportFormat.GetSelection()][:4]

        # Enable appropriate addit. options panel
        panel.Enable(True)
        panel.Show(True)

        impSrcWildcards = ob.getImportSourceWildcards(itype)

        if impSrcWildcards is None:
            # Directory source
            self.ctrls.stSource.SetLabel(_("Source directory:"))
        else:
            # File source
            self.ctrls.stSource.SetLabel(_("Source file:"))


    def OnImportFormat(self, evt):
        self._refreshForItype()
        evt.Skip()



    def OnOk(self, evt):
        # Run importer
        ob, itype, desc, panel = \
                self.importerList[self.ctrls.chImportFormat.GetSelection()][:4]
                
        if not exists(self.ctrls.tfSource.GetValue()):
            self.mainControl.displayErrorMessage(
                    _("Source does not exist"))
            return

        # If this returns None, import goes to a directory
        impSrcWildcards = ob.getImportSourceWildcards(itype)
        if impSrcWildcards is None:
            # Import from a directory
            
            if not isdir(self.ctrls.tfSource.GetValue()):
                self.mainControl.displayErrorMessage(
                        _("Source must be a directory"))
                return
        else:
            if not isfile(self.ctrls.tfSource.GetValue()):
                self.mainControl.displayErrorMessage(
                        _("Source must be a file"))
                return

        if panel is self.emptyPanel:
            panel = None

        try:
            ob.doImport(self.mainControl.getWikiDocument(), itype, 
                    self.ctrls.tfSource.GetValue(), 
                    False, ob.getAddOpt(panel))
        except ImportException as e:
            self.mainControl.displayErrorMessage(_("Error while importing"),
                    str(e))

        self.EndModal(wx.ID_OK)

        
    def OnSelectSrc(self, evt):
        ob, itype, desc, panel = \
                self.importerList[self.ctrls.chImportFormat.GetSelection()][:4]

        impSrcWildcards = ob.getImportSourceWildcards(itype)

        if impSrcWildcards is None:
            # Only transfer between GUI elements, so no unicode conversion
            seldir = wx.DirSelector(_("Select Import Directory"),
                    self.ctrls.tfSource.GetValue(),
                    style=wx.DD_DEFAULT_STYLE, parent=self)

            if seldir:
                self.ctrls.tfSource.SetValue(seldir)

        else:
            # Build wildcard string
            wcs = []
            for wd, wp in impSrcWildcards:
                wcs.append(wd)
                wcs.append(wp)
                
            wcs.append(_("All files (*.*)"))
            wcs.append(_("*"))
            
            wcs = "|".join(wcs)
            
            selfile = wx.FileSelector(_("Select Import File"),
                    self.ctrls.tfSource.GetValue(),
                    default_filename = "", default_extension = "",
                    wildcard = wcs, flags=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST,
                    parent=self)

            if selfile:
                self.ctrls.tfSource.SetValue(selfile)



def _children(win, indent=0):
    print(" " * indent + repr(win), win.GetId())
    for c in win.GetChildren():
        _children(c, indent=indent+2)



class NewWikiSettings(wx.Dialog, ModalDialogMixin):
    """
    Dialog to choose options when creating a new wiki or when a wiki with
    damaged configuration file is opened.
    """
    DEFAULT_GREY = 1

    def __init__(self, parent, ID, mainControl, defDbHandler=None,
            defWikiLang=None, title="", pos=wx.DefaultPosition,
            size=wx.DefaultSize):
#         d = wx.PreDialog()
#         self.PostCreate(d)
        wx.Dialog.__init__(self)

        self.mainControl = mainControl
        self.value = None, None, None

        res = wx.xrc.XmlResource.Get()
        res.LoadDialog(self, parent, "NewWikiSettingsDialog")

        self.ctrls = XrcControls(self)

        # Retrieve lists of db backends and wiki languages
        self.dbHandlers = DbBackendUtils.listHandlers()
        self.wikiLanguages = wx.GetApp().listWikiLanguageDescriptions()

        errMsg = ""

        if len(self.dbHandlers) == 0:
            errMsg += 'No data handler available'
        if len(self.wikiLanguages) == 0:
            errMsg += 'No wiki language handler available'

        if errMsg:
            self.mainControl.displayErrorMessage(errMsg)
            self.EndModal(wx.ID_CANCEL)
            return

        if defDbHandler is not NewWikiSettings.DEFAULT_GREY:
            self.ctrls.lbDatabaseType.Set([h[1] for h in self.dbHandlers])
            for i, h in enumerate(self.dbHandlers):
                if h[0] == defDbHandler:
                    self.ctrls.lbDatabaseType.SetSelection(i)
                    break
            else:
                self.ctrls.lbDatabaseType.SetSelection(0)

            self.ctrls.cbWikiPageFilesAsciiOnly.SetValue(SystemInfo.isOSX())

        else:
            self.ctrls.lbDatabaseType.Enable(False)
            self.ctrls.cbWikiPageFilesAsciiOnly.Enable(False)
            self.ctrls.lbDatabaseType.SetBackgroundColour(wx.LIGHT_GREY)

        if defWikiLang is not NewWikiSettings.DEFAULT_GREY:
            self.ctrls.lbWikiLanguage.Set([l[1] for l in self.wikiLanguages])
            for i, l in enumerate(self.wikiLanguages):
                if l[0] == defWikiLang:
                    self.ctrls.lbWikiLanguage.SetSelection(i)
                    break
            else:
                self.ctrls.lbWikiLanguage.SetSelection(0)

        else:
            self.ctrls.lbWikiLanguage.Enable(False)
            self.ctrls.lbWikiLanguage.SetBackgroundColour(wx.LIGHT_GREY)

        self.ctrls.cbWikiPageFilesAsciiOnly.SetValue(
                self.mainControl.getConfig().getboolean(
                "main", "newWikiDefault_wikiPageFiles_asciiOnly", False))

        self.ctrls.btnOk.SetId(wx.ID_OK)
        self.ctrls.btnCancel.SetId(wx.ID_CANCEL)

        self.Bind(wx.EVT_BUTTON, self.OnOk, id=wx.ID_OK)


    def GetValue(self):
        return self.value

    def OnOk(self, evt):
        dbSel = self.ctrls.lbDatabaseType.GetSelection()
        langSel = self.ctrls.lbWikiLanguage.GetSelection()
        
        dbH = None
        wlH = None
        
        if dbSel != wx.NOT_FOUND:
            dbH = self.dbHandlers[dbSel][0]
        if langSel != wx.NOT_FOUND:
            wlH = self.wikiLanguages[langSel][0]
        
        self.value = (dbH, wlH, self.ctrls.cbWikiPageFilesAsciiOnly.GetValue())

        self.EndModal(wx.ID_OK)



class ShowStaticHtmlTextDialog(wx.Dialog, ModalDialogMixin):
    """ Show static content in an HTML window """

    def __init__(self, parent, title, htmlContent=None, textContent=None,
            size=(470, 330)):
        """
        In the constructor you can either give html source or plain text
        which is escaped to html
        """
        wx.Dialog.__init__(self, parent, -1, title, size=size)
        
        if htmlContent is None and textContent is not None:
            htmlContent = escapeHtml(textContent)
            
        html = wx.html.HtmlWindow(self, -1)
        
        if htmlContent is not None:
            html.SetPage(htmlContent)

        button = wx.Button(self, wx.ID_OK, _("Okay"))

        # constraints for the html window
        lc = wx.LayoutConstraints()
        lc.top.SameAs(self, wx.Top, 5)
        lc.left.SameAs(self, wx.Left, 5)
        lc.bottom.SameAs(button, wx.Top, 5)
        lc.right.SameAs(self, wx.Right, 5)
        html.SetConstraints(lc)

        # constraints for the button
        lc = wx.LayoutConstraints()
        lc.bottom.SameAs(self, wx.Bottom, 5)
        lc.centreX.SameAs(self, wx.CentreX)
        lc.width.AsIs()
        lc.height.AsIs()
        button.SetConstraints(lc)

        self.SetAutoLayout(True)
        self.Layout()
        self.CentreOnParent(wx.BOTH)
        
        # Fixes focus bug under Linux
        self.SetFocus()




class AboutDialog(ShowStaticHtmlTextDialog):
    """ An about box that uses an HTML window """

    TEXT_TEMPLATE = N_('''
<html>
<body bgcolor="#FFFFFF">
    <center>
        <table bgcolor="#CCCCCC" width="100%%" cellspacing="0" cellpadding="0" border="1">
            <tr>
                <td align="center"><h2>%s</h2></td>
            </tr>
        </table>

        <p>
wikidPad is a Wiki-like notebook for storing your thoughts, ideas, todo lists, contacts, or anything else you can think of to write down.
What makes wikidPad different from other notepad applications is the ease with which you can cross-link your information.        </p>        
        <br><br>

        <table border=0 cellpadding=1 cellspacing=0>
            <tr><td width="30%%" align="right"><font size="3"><b>Author:</b></font></td><td nowrap><font size="3">Michael Butscher</font></td></tr>
            <tr><td width="30%%" align="right"><font size="3"><b>Email:</b></font></td><td nowrap><font size="3">mbutscher@gmx.de</font></td></tr>
            <tr><td width="30%%" align="right"><font size="3"><b>URL:</b></font></td><td nowrap><font size="3">http://www.mbutscher.de/software.html</font></td></tr>
            <tr><td width="30%%" align="right">&nbsp;</td></tr>
            <tr><td width="30%%" align="right"><font size="3"><b>Author:</b></font></td><td nowrap><font size="3">Jason Horman</font></td></tr>
            <tr><td width="30%%" align="right"><font size="3"><b>Email:</b></font></td><td nowrap><font size="3">wikidpad@jhorman.org</font></td></tr>
            <tr><td width="30%%" align="right"><font size="3"><b>URL:</b></font></td><td nowrap><font size="3">http://www.jhorman.org/wikidPad/</font></td></tr>
            <tr><td width="30%%" align="right">&nbsp;</td></tr>
            <tr><td width="30%%" align="right"><font size="3"><b>Author:</b></font></td><td nowrap><font size="3">Gerhard Reitmayr</font></td></tr>
            <tr><td width="30%%" align="right"><font size="3"><b>Email:</b></font></td><td nowrap><font size="3">gerhard.reitmayr@gmail.com</font></td></tr>
            <tr><td width="30%%" align="right">&nbsp;</td></tr>
            <tr><td width="30%%" align="right">&nbsp;</td></tr>
            <tr><td width="30%%" align="left" colspan="2" nowrap><font size="3"><b>Translations:</b></font></td></tr>
            <tr><td width="30%%" align="right"><font size="3"><b>Chinese:</b></font></td><td nowrap><font size="3">yuxiaoxu@msn.com</font></td></tr>
            <tr><td width="30%%" align="right"><font size="3"><b>Hungarian:</b></font></td><td nowrap><font size="3">Török Árpád</font></td></tr>
            <tr><td width="30%%" align="right"><font size="3"><b>Russian:</b></font></td><td nowrap><font size="3">Oleg Domanov</font></td></tr>
            <tr><td width="30%%" align="right"><font size="3"><b>Swedish:</b></font></td><td nowrap><font size="3">Stefan Berg</font></td></tr>
        </table>
    </center>
    
    

    
    <hr />
    
    <p>Your configuration directory is: <b>%s</b><br />
    Sqlite version: <b>%s</b><br />
    wxPython version: <b>%s</b>
    </p>
    
</body>
</html>
''')

    def __init__(self, pWiki):
#         wx.Dialog.__init__(self, pWiki, -1, _(u'About WikidPad'),
#                           size=(470, 330) )
        
        if sqlite is None:
            sqliteVer = _("N/A")
        else:
            sqliteVer = sqlite.getLibVersion()

        content = _(self.TEXT_TEMPLATE) % (VERSION_STRING,
                escapeHtml(pWiki.globalConfigDir), escapeHtml(sqliteVer),
                escapeHtml(wx.__version__))

        ShowStaticHtmlTextDialog.__init__(self, pWiki, _('About WikidPad'),
                htmlContent=content, size=(470, 330))



class SimpleInfoDialog(wx.Dialog):
    """
    Show a dialog with a static list of key-value pairs
    """
    def __init__(self, *args, **kwargs):
        wx.Dialog.__init__(self, *args, **kwargs)

        self.txtBgColor = self.GetBackgroundColour()

        button = wx.Button(self, wx.ID_OK)
        button.SetDefault()

        mainsizer = wx.BoxSizer(wx.VERTICAL)

        self.lineSizer = wx.FlexGridSizer(2)
        self.lineSizer.AddGrowableCol(1, 1)

        self.fillInfoLines()

        mainsizer.Add(self.lineSizer, 0, wx.ALL | wx.EXPAND, 0)

        inputsizer = wx.BoxSizer(wx.HORIZONTAL)
        inputsizer.Add(button, 0, wx.ALL | wx.EXPAND, 5)
        inputsizer.Add((0, 0), 1)   # Stretchable spacer

        mainsizer.Add(inputsizer, 0, wx.ALL | wx.EXPAND, 0)
        
        self.Bind(wx.EVT_BUTTON, self.OnOk, id=wx.ID_OK)
        self.Bind(wx.EVT_BUTTON, self.OnOk, id=wx.ID_CANCEL)

        self.SetSizer(mainsizer)
        self.Fit()

        # Fixes focus bug under Linux
        self.SetFocus()



    def _addTextLine(self, label, value, multiLine=False):

        if value is not None:
            self.lineSizer.Add(wx.StaticText(self, -1, label), 0,
                    wx.ALL | wx.EXPAND, 5)
        else:
            # If no value given, show no label (as static text)
            # but show label as value
            self.lineSizer.Add((0, 0), 1)
            value = label

        if multiLine:
            ctl = wx.TextCtrl(self, -1, value,
                    style = wx.TE_MULTILINE | wx.TE_READONLY)
        else:
            ctl = wx.TextCtrl(self, -1, value, style = wx.TE_READONLY)
        ctl.SetBackgroundColour(self.txtBgColor)
        self.lineSizer.Add(ctl, 1, wx.ALL | wx.EXPAND, 5)

        return ctl

    # Compatiblity.  TODO: 2.4: Remove
    _addLine = _addTextLine
        
    def fillInfoLines(self):
        raise NotImplementedError #abstract
        
        
    def close(self):
        pass
    
    def OnOk(self, evt):
        self.close()
        evt.Skip()
        



class WikiPropertiesDialog(SimpleInfoDialog):
    """
    Show general information about currently open wiki
    """
    def __init__(self, parent, id, mainControl):
        self.mainControl = mainControl
        SimpleInfoDialog.__init__(self, parent, id, _('Wiki Properties'),
                          size=(470, 330),
                          style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)

    def fillInfoLines(self):
        wd = self.mainControl.getWikiDocument()
        if wd is None:
            label = _("No wiki loaded")
            self._addTextLine(label, None)
            return

        label = _("Wiki config. path:")
        value = wd.getWikiConfigPath()
        self._addTextLine(label, value)

#         wikiData = wd.getWikiData()

        label = _("Wiki database backend:")
#         if wd is None:
#             value = _(u"N/A")
#         else:
        value = wd.getDbtype()

        self._addTextLine(label, value)

        label = _("Number of wiki pages:")
#         if wd is None:
#             value = _(u"N/A")
#         else:
        value = str(len(wd.getAllDefinedWikiPageNames()))

        self._addTextLine(label, value)

        if wd.isReadOnlyEffect():
            label = _("Wiki is read-only. Reason:")

            if wd.getWriteAccessFailed():
                value = _("Write access to database lost. Try \"Wiki\"->\"Reconnect\"")
            elif wd.getWriteAccessDeniedByConfig():
                value = _("Wiki was set read-only in options dialog")
            elif wd.getWriteAccessDenied():
                try:
                    f = open(pathEnc(wd.getWikiConfigPath()), "r+b")
                    f.close()
                    value = _("Can't write wiki config.:") + " " + _("Unknown reason")
                except IOError as e:
                    value = _("Can't write wiki config.:") + " " + str(e)
            else:
                value = _("Unknown reason")
            
            self._addTextLine(label, value, multiLine=True)


class WikiJobDialog(SimpleInfoDialog):
    """
    Show information about currently open wiki
    """
    def __init__(self, parent, id, mainControl):
        self.jobTxtCtrl = None
        self.mainControl = mainControl

        SimpleInfoDialog.__init__(self, parent, id, _('Jobs'),
                          size=(470, 330) )
                          
        wd = self.mainControl.getWikiDocument()
        if wd is not None:
            exe = wd.getUpdateExecutor()
            if exe is not None:
                exe.startDoneJobCount()
                exe.resetDoneJobCount()

        # Start timer
        self.timer = wx.Timer(self, GUI_ID.TIMER_JOBDIALOG)
        self.OnTimer(None)
        self.timer.Start(500, False)

        self.Bind(wx.EVT_TIMER, self.OnTimer, self.timer)


#     def OnOk(self, evt):
#         evt.Skip()
#         self.timer.Stop()
        

    def fillInfoLines(self):
        self.jobTxtCtrl = self._addTextLine(_("Number of Jobs:"), "0")
        self.jobDoneTxtCtrl = self._addTextLine(_("Number of Done Jobs:"), "0")

    def OnTimer(self, evt):
        wd = self.mainControl.getWikiDocument()
        if wd is not None:
            exe = wd.getUpdateExecutor()
            if exe is not None:
                self.jobTxtCtrl.SetValue(str(exe.getJobCount()))
                self.jobDoneTxtCtrl.SetValue(str(exe.getDoneJobCount()))

    def close(self):
        self.timer.Stop()
        wd = self.mainControl.getWikiDocument()
        if wd is not None:
            exe = wd.getUpdateExecutor()
            if exe is not None:
                exe.stopDoneJobCount()

        SimpleInfoDialog.close(self)
        
        
