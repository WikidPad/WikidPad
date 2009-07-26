import sys, traceback
# from time import strftime
import re

from os.path import exists, isdir, isfile

from xml.dom import minidom

import wx, wx.html, wx.xrc


from wxHelper import *

try:
    import sqlite3api as sqlite
except:
    sqlite = None


from StringOps import uniToGui, guiToUni, mbcsEnc, mbcsDec, \
        escapeForIni, unescapeForIni, escapeHtml, strftimeUB, pathEnc, \
        writeEntireFile
from wikidata import DbBackendUtils

from WikiExceptions import *
import Exporters, Importers
import Serialization
import Configuration

from Consts import VERSION_STRING, DATABLOCK_STOREHINT_INTERN

from SearchAndReplaceDialogs import SearchWikiDialog   # WikiPageListConstructionDialog
from SearchAndReplace import SearchReplaceOperation, ListWikiPagesOperation


try:
    import WindowsHacks
except:
    if Configuration.isWindows():
        traceback.print_exc()
    WindowsHacks = None




class SelectWikiWordDialog(wx.Dialog):
    """
    Called for "Append/Prepend wiki word" in tree node context menu
    """
    def __init__(self, pWiki, parent, ID, title=None,
                 pos=wx.DefaultPosition, size=wx.DefaultSize,
                 style=wx.NO_3D):

        d = wx.PreDialog()
        self.PostCreate(d)

        self.pWiki = pWiki
        self.wikiWord = None
        self.listContent = []
        self.ignoreTextChange = 0
        
        res = wx.xrc.XmlResource.Get()
        res.LoadOnDialog(self, parent, "SelectWikiWordDialog")

        if title is not None:
            self.SetTitle(title)

        self.ctrls = XrcControls(self)

        self.ctrls.btnOk.SetId(wx.ID_OK)
        self.ctrls.btnCancel.SetId(wx.ID_CANCEL)
        
        # Fixes focus bug under Linux
        self.SetFocus()

        wx.EVT_BUTTON(self, wx.ID_OK, self.OnOk)

        wx.EVT_TEXT(self, ID, self.OnText)
        wx.EVT_CHAR(self.ctrls.text, self.OnCharText)
        wx.EVT_CHAR(self.ctrls.lb, self.OnCharListBox)
        wx.EVT_LISTBOX(self, ID, self.OnListBox)
        wx.EVT_LISTBOX_DCLICK(self, GUI_ID.lb, self.OnOk)


    def _fillListContent(self, searchTxt):
        if len(searchTxt) == 0:
            self.listContent = []
            return

        if searchTxt == u"%":
            self.listContent = self.pWiki.getWikiData()\
                    .getWikiWordMatchTermsWith(u"")
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
            self.wikiWord = guiToUni(self.ctrls.text.GetValue())
    
            if not self.pWiki.getWikiDocument().isDefinedWikiLink(self.wikiWord):
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

        text = guiToUni(evt.GetString())

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
                self.ctrls.stLinkTo.SetLabel(uniToGui(_(u"Links to:") + u" " +
                        self.listContent[sel][2]))
            else:
                self.ctrls.stLinkTo.SetLabel(u"")
            self.ignoreTextChange += 1
            self.ctrls.text.SetValue(self.listContent[sel][0])
        else:
            self.ctrls.stLinkTo.SetLabel(u"")



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
            

SelectWikiWordDialog.runModal = staticmethod(runDialogModalFactory(SelectWikiWordDialog))

     

class OpenWikiWordDialog(wx.Dialog):
    def __init__(self, pWiki, parent, ID, title=None,
                 pos=wx.DefaultPosition, size=wx.DefaultSize,
                 style=wx.NO_3D):

        d = wx.PreDialog()
        self.PostCreate(d)

        self.pWiki = pWiki
        self.value = None
        self.listContent = []
        self.ignoreTextChange = 0

        res = wx.xrc.XmlResource.Get()
        res.LoadOnDialog(self, parent, "OpenWikiWordDialog")

        if title is not None:
            self.SetTitle(title)

        self.ctrls = XrcControls(self)

        self.ctrls.btnOk.SetId(wx.ID_OK)
        self.ctrls.btnCancel.SetId(wx.ID_CANCEL)
        
        # Fixes focus bug under Linux
        self.SetFocus()

        wx.EVT_BUTTON(self, wx.ID_OK, self.OnOk)

        wx.EVT_TEXT(self, ID, self.OnText)
        wx.EVT_CHAR(self.ctrls.text, self.OnCharText)
        wx.EVT_CHAR(self.ctrls.lb, self.OnCharListBox)
        wx.EVT_LISTBOX(self, ID, self.OnListBox)
        wx.EVT_LISTBOX_DCLICK(self, GUI_ID.lb, self.OnOk)
        wx.EVT_BUTTON(self, wx.ID_OK, self.OnOk)
        wx.EVT_BUTTON(self, GUI_ID.btnCreate, self.OnCreate)
        wx.EVT_BUTTON(self, GUI_ID.btnDelete, self.OnDelete)
        wx.EVT_BUTTON(self, GUI_ID.btnNewTab, self.OnNewTab)
        wx.EVT_BUTTON(self, GUI_ID.btnNewTabBackground, self.OnNewTabBackground)

    def OnOk(self, evt):
        if self.activateSelectedWikiWords(0):
            self.EndModal(wx.ID_OK)


    def _fillListContent(self, searchTxt):
        if len(searchTxt) == 0:
            self.listContent = []
            return

        if searchTxt == u"%":
            self.listContent = self.pWiki.getWikiData()\
                    .getWikiWordMatchTermsWith(u"")
            return
        
        self.listContent = self.pWiki.getWikiData().getWikiWordMatchTermsWith(
                searchTxt)


    def activateSelectedWikiWords(self, tabMode):
        sel = self.ctrls.lb.GetSelections()
        if len(sel) > 0:
            self.value = tuple(self.listContent[s] for s in sel)
        else:
            entered = guiToUni(self.ctrls.text.GetValue())

            if len(entered) == 0:
                # Nothing entered probably means the user doesn't want to
                # continue, so return True
                return True

            if not self.pWiki.getWikiDocument().isDefinedWikiLink(entered):
                langHelper = wx.GetApp().createWikiLanguageHelper(
                        self.pWiki.getWikiDefaultWikiLanguage())
                wikiWord = langHelper.extractWikiWordFromLink(entered,
                        self.pWiki.getWikiDocument())

                if wikiWord is not None and \
                        self.pWiki.getWikiDocument().isDefinedWikiLink(wikiWord):
                    self.value = ((wikiWord, 0,
                            self.pWiki.getWikiDocument()\
                            .getUnAliasedWikiWord(wikiWord), -1),)
                else:
                    self._fillListContent(entered)
#                     terms = self.pWiki.getWikiData().getWikiWordMatchTermsWith(
#                             entered)
                    if len(self.listContent) > 0:
                        self.value = (self.listContent[0],)
                    else:
                        if wikiWord is None:
                            self.pWiki.displayErrorMessage(
                                    _(u"'%s' is an invalid WikiWord") % entered)
                            # Entered text is not a valid wiki word
                            self.ctrls.text.SetFocus()
                            return False

                        # wikiWord is valid but nonexisting, so maybe create it?
                        result = wx.MessageBox(
                                uniToGui(_(u"'%s' is not an existing wikiword. Create?") %
                                wikiWord), uniToGui(_(u"Create")),
                                wx.YES_NO | wx.YES_DEFAULT | wx.ICON_QUESTION, self)
    
                        if result == wx.NO:
                            self.ctrls.text.SetFocus()
                            return False
    
                        self.value = ((wikiWord, 0, wikiWord, -1),)
            else:
                self.value = ((entered, 0, entered, -1),)

        if self.pWiki.activatePageByUnifiedName(u"wikipage/" + self.value[0][2],
                tabMode=tabMode) is None:   # TODO: Go to charPos
            return True   # False instead ?

        for term in self.value[1:]:
            if self.pWiki.activatePageByUnifiedName(u"wikipage/" + term[2],
                    tabMode=3) is None:   # TODO: Go to charPos
                break

        return True


    def GetValue(self):
        return self.value

    def OnText(self, evt):
        if self.ignoreTextChange:
            self.ignoreTextChange -= 1
            return

        text = guiToUni(evt.GetString())

        self.ctrls.lb.Freeze()
        try:
            self.ctrls.lb.Clear()
            self._fillListContent(text)

            for term in self.listContent:
                self.ctrls.lb.Append(term[0])
        finally:
            self.ctrls.lb.Thaw()


    def OnListBox(self, evt):
        sel = self.ctrls.lb.GetSelections()
        if len(sel) > 0:
            sel = sel[0]
            if self.listContent[sel][0] != self.listContent[sel][2]:
                self.ctrls.stLinkTo.SetLabel(uniToGui(_(u"Links to:") + u" " +
                        self.listContent[sel][2]))
            else:
                self.ctrls.stLinkTo.SetLabel(u"")
            self.ignoreTextChange += 1
            self.ctrls.text.SetValue(self.listContent[sel][0])
        else:
            self.ctrls.stLinkTo.SetLabel(u"")


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
            
            
    def OnCreate(self, evt):
        """
        Create new WikiWord
        """
        langHelper = wx.GetApp().createWikiLanguageHelper(
                self.pWiki.getWikiDefaultWikiLanguage(),
                self.pWiki.getWikiDocument())
        entered = guiToUni(self.ctrls.text.GetValue())
        wikiWord = langHelper.extractWikiWordFromLink(entered)

        if wikiWord is None:
            self.pWiki.displayErrorMessage(_(u"'%s' is an invalid WikiWord") %
                    entered)
            self.ctrls.text.SetFocus()
            return
        
        if not self.pWiki.getWikiDocument().isCreatableWikiWord(wikiWord):
            self.pWiki.displayErrorMessage(_(u"'%s' exists already") % wikiWord)
            self.ctrls.text.SetFocus()
            return

        self.value = (wikiWord, 0, wikiWord, -1)
        self.pWiki.activatePageByUnifiedName(u"wikipage/" + wikiWord,
                tabMode=0)
        self.EndModal(wx.ID_OK)


    def OnDelete(self, evt):
        sellen = len(self.ctrls.lb.GetSelections())
        if sellen > 0:
            answer = wx.MessageBox(
                    _(u"Do you want to delete %i wiki page(s)?") % sellen,
                    (u"Delete Wiki Page(s)"),
                    wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION, self)

            if answer != wx.YES:
                return

            self.pWiki.saveAllDocPages()
            for s in self.ctrls.lb.GetSelections():
                delword = self.listContent[s][2]
                # Un-alias word
                delword = self.pWiki.getWikiDocument().getUnAliasedWikiWord(delword)

                if delword is not None:
                    page = self.pWiki.getWikiDocument().getWikiPage(delword)
                    page.deletePage()
                    
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

OpenWikiWordDialog.runModal = staticmethod(runDialogModalFactory(OpenWikiWordDialog))



class ChooseWikiWordDialog(wx.Dialog):
    """
    Used to allow selection from list of parents, parentless words, children
    or bookmarked words.
    """
    def __init__(self, pWiki, ID, words, motionType, title=None,
                 pos=wx.DefaultPosition, size=wx.DefaultSize):
        d = wx.PreDialog()
        self.PostCreate(d)
        
        self.pWiki = pWiki
        res = wx.xrc.XmlResource.Get()
        res.LoadOnDialog(self, self.pWiki, "ChooseWikiWordDialog")
        
        self.ctrls = XrcControls(self)
        
        if title is not None:
            self.SetTitle(title)

        self.ctrls.staTitle.SetLabel(title)
        
        self.motionType = motionType
        self.unsortedWords = words

        self.ctrls.cbSortAlphabetically.SetValue(
                self.pWiki.getConfig().get("main",
                "chooseWikiWordDialog_sortOrder") == u"AlphaAsc")

        self._sortAndFillWords()
        
        self.ctrls.btnOk.SetId(wx.ID_OK)
        self.ctrls.btnCancel.SetId(wx.ID_CANCEL)
        
        # Fixes focus bug under Linux
        self.SetFocus()

        wx.EVT_BUTTON(self, GUI_ID.btnDelete, self.OnDelete)
        wx.EVT_BUTTON(self, GUI_ID.btnNewTab, self.OnNewTab)
        wx.EVT_BUTTON(self, wx.ID_OK, self.OnOk)
        wx.EVT_LISTBOX_DCLICK(self, GUI_ID.lb, self.OnOk)
        wx.EVT_CHECKBOX(self, GUI_ID.cbSortAlphabetically,
                self.OnCbSortAlphabetically)


    def OnDelete(self, evt):
        sellen = len(self.ctrls.lb.GetSelections())
        if sellen > 0:
            answer = wx.MessageBox(
                    _(u"Do you want to delete %i wiki page(s)?") % sellen,
                    (u"Delete Wiki Page(s)"),
                    wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION, self)

            if answer != wx.YES:
                return

            self.pWiki.saveAllDocPages()
            for s in self.ctrls.lb.GetSelections():
                delword = self.words[s]
                # Un-alias word
                delword = self.pWiki.getWikiDocument().getUnAliasedWikiWord(delword)

                if delword is not None:
                    page = self.pWiki.getWikiDocument().getWikiPage(delword)
                    page.deletePage()
                    
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
                if self.pWiki.activatePageByUnifiedName(u"wikipage/" + word,
                        2) is None:
                    break
        finally:
            self.EndModal(wx.ID_OK)

 
    def OnCbSortAlphabetically(self, evt):
        self.pWiki.getConfig().set("main",
                "chooseWikiWordDialog_sortOrder", (u"AlphaAsc" if
                self.ctrls.cbSortAlphabetically.GetValue() else u"None"))
        self._sortAndFillWords()

 
    def _sortAndFillWords(self):
        """
        Sort words according to settings in dialog.
        """
        self.words = self.unsortedWords[:]
        if self.ctrls.cbSortAlphabetically.GetValue():
            self.pWiki.getCollator().sort(self.words)
            
        wordsgui = map(uniToGui, self.words)
        
        self.ctrls.lb.Set(wordsgui)

 
 

class SelectIconDialog(wx.Dialog):
    def __init__(self, parent, ID, iconCache, title="Select Icon",
                 pos=wx.DefaultPosition, size=wx.DefaultSize,
                 style=wx.NO_3D|wx.DEFAULT_DIALOG_STYLE|wx.RESIZE_BORDER):
        wx.Dialog.__init__(self, parent, ID, title, pos, size, style)

        self.iconCache = iconCache
        self.iconImageList = self.iconCache.iconImageList
        
        self.iconNames = [n for n in self.iconCache.iconLookupCache.keys()
                if not n.startswith("tb_")]
#         filter(lambda n: not n.startswith("tb_"),
#                 self.iconCache.iconLookupCache.keys())
        self.iconNames.sort()
        
        # Now continue with the normal construction of the dialog
        # contents
        sizer = wx.BoxSizer(wx.VERTICAL)

        label = wx.StaticText(self, -1, _(u"Select Icon"))
        sizer.Add(label, 0, wx.ALIGN_CENTRE|wx.ALL, 5)

        box = wx.BoxSizer(wx.VERTICAL)

        self.lc = wx.ListCtrl(self, -1, wx.DefaultPosition, wx.Size(145, 200), 
                style = wx.LC_REPORT | wx.LC_NO_HEADER)    ## | wx.BORDER_NONE
                
        self.lc.SetImageList(self.iconImageList, wx.IMAGE_LIST_SMALL)
        self.lc.InsertColumn(0, _(u"Icon"))

        for icn in self.iconNames:
            self.lc.InsertImageStringItem(sys.maxint, icn,
                    self.iconCache.lookupIconIndex(icn))
        self.lc.SetColumnWidth(0, wx.LIST_AUTOSIZE)
        
        
        box.Add(self.lc, 1, wx.ALIGN_CENTRE|wx.ALL|wx.EXPAND, 5)

        sizer.Add(box, 1, wx.GROW|wx.ALIGN_CENTER_VERTICAL|wx.ALL, 5)

        line = wx.StaticLine(self, -1, size=(20,-1), style=wx.LI_HORIZONTAL)
        sizer.Add(line, 0, wx.GROW|wx.ALIGN_CENTER_VERTICAL|wx.RIGHT|wx.TOP, 5)

        box = wx.BoxSizer(wx.HORIZONTAL)

        btn = wx.Button(self, wx.ID_OK, _(u" OK "))
        btn.SetDefault()
        box.Add(btn, 0, wx.ALIGN_CENTRE|wx.ALL, 5)

        btn = wx.Button(self, wx.ID_CANCEL, _(u" Cancel "))
        box.Add(btn, 0, wx.ALIGN_CENTRE|wx.ALL, 5)

        sizer.Add(box, 0, wx.ALIGN_CENTER_VERTICAL|wx.ALL, 5)

        self.SetSizer(sizer)
        self.SetAutoLayout(True)
        sizer.Fit(self)

        self.value = None
        
        # Fixes focus bug under Linux
        self.SetFocus()

        wx.EVT_BUTTON(self, wx.ID_OK, self.OnOk)
        wx.EVT_LIST_ITEM_ACTIVATED(self, self.lc.GetId(), self.OnOk)

    def GetValue(self):
        """
        Return name of selected icon or None
        """
        return self.value


#     @staticmethod
#     def runModal(parent, ID, iconCache, title="Select Icon",
#             pos=wx.DefaultPosition, size=wx.DefaultSize,
#             style=wx.NO_3D|wx.DEFAULT_DIALOG_STYLE|wx.RESIZE_BORDER):
# 
#         dlg = SelectIconDialog(parent, ID, iconCache, title, pos, size, style)
#         try:
#             dlg.CenterOnParent(wx.BOTH)
#             if dlg.ShowModal() == wx.ID_OK:
#                 return dlg.GetValue()
#             else:
#                 return None
# 
#         finally:
#             dlg.Destroy()


    def OnOk(self, evt):
        no = self.lc.GetNextItem(-1, state = wx.LIST_STATE_SELECTED)
        if no > -1:
            self.value = self.iconNames[no]
        else:
            self.value = None
            
        self.EndModal(wx.ID_OK)



# class SavedVersionsDialog(wx.Dialog):
#     def __init__(self, pWiki, ID, title="Saved Versions",
#                  pos=wx.DefaultPosition, size=wx.DefaultSize,
#                  style=wx.NO_3D):
#         wx.Dialog.__init__(self, pWiki, ID, title, pos, size, style)
#         self.pWiki = pWiki
#         self.value = None        
#         
#         # Now continue with the normal construction of the dialog
#         # contents
#         sizer = wx.BoxSizer(wx.VERTICAL)
# 
#         label = wx.StaticText(self, -1, _(u"Saved Versions"))
#         sizer.Add(label, 0, wx.ALIGN_CENTRE|wx.ALL, 5)
# 
#         box = wx.BoxSizer(wx.VERTICAL)
# 
#         self.lb = wx.ListBox(self, -1, wx.DefaultPosition, wx.Size(165, 200),
#                 [], wx.LB_SINGLE)
# 
#         # fill in the listbox
#         self.versions = self.pWiki.getWikiData().getStoredVersions()
#             
#         for version in self.versions:
#             self.lb.Append(version[1])
# 
#         box.Add(self.lb, 1, wx.ALIGN_CENTRE|wx.ALL, 5)
# 
#         sizer.AddSizer(box, 0, wx.GROW|wx.ALIGN_CENTER_VERTICAL|wx.ALL, 5)
# 
#         line = wx.StaticLine(self, -1, size=(20,-1), style=wx.LI_HORIZONTAL)
#         sizer.Add(line, 0, wx.GROW|wx.ALIGN_CENTER_VERTICAL|wx.RIGHT|wx.TOP, 5)
# 
#         box = wx.BoxSizer(wx.HORIZONTAL)
# 
#         btn = wx.Button(self, wx.ID_OK, _(u" Retrieve "))
#         btn.SetDefault()
#         box.Add(btn, 0, wx.ALIGN_CENTRE|wx.ALL, 5)
# 
#         btn = wx.Button(self, wx.ID_CANCEL, _(u" Cancel "))
#         box.Add(btn, 0, wx.ALIGN_CENTRE|wx.ALL, 5)
# 
#         sizer.AddSizer(box, 0, wx.ALIGN_CENTER_VERTICAL|wx.ALL, 5)
# 
#         self.SetSizer(sizer)
#         self.SetAutoLayout(True)
#         sizer.Fit(self)
#         
#         # Fixes focus bug under Linux
#         self.SetFocus()
# 
#         ## wx.EVT_BUTTON(self, wxID_OK, self.OnRetrieve)
#         wx.EVT_LISTBOX(self, ID, self.OnListBox)
#         wx.EVT_LISTBOX_DCLICK(self, ID, lambda evt: self.EndModal(wx.ID_OK))
#         
# ##    def OnRetrieve(self, evt):
# ##        if self.value:
# ##            self.pWiki.getWikiData().deleteSavedSearch(self.value)
# ##            self.EndModal(wxID_CANCEL)
#         
#     def GetValue(self):
#         """ Returns None or tuple (<id>, <description>, <creation date>)
#         """
#         return self.value
# 
#     def OnListBox(self, evt):
#         self.value = self.versions[evt.GetSelection()]


SelectIconDialog.runModal = staticmethod(runDialogModalFactory(SelectIconDialog))




class DateformatDialog(wx.Dialog):

    # HTML explanation for strftime:
    FORMATHELP = N_(ur"""<html>
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
                 style=wx.NO_3D, deffmt=u""):
        """
        deffmt -- Initial value for format string
        """
        d = wx.PreDialog()
        self.PostCreate(d)
        
        self.mainControl = mainControl
        self.value = u""     
        res = wx.xrc.XmlResource.Get()
        res.LoadOnDialog(self, parent, "DateformatDialog")

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
        self.recentFormats = [unescapeForIni(s) for s in tfs.split(u";")]
        for f in self.recentFormats:
            self.ctrls.fieldFormat.Append(f)

        self.ctrls.fieldFormat.SetValue(deffmt)
        self.OnText(None)
        
        # Fixes focus bug under Linux
        self.SetFocus()
        
        wx.EVT_BUTTON(self, wx.ID_OK, self.OnOk)
        wx.EVT_TEXT(self, XRCID("fieldFormat"), self.OnText) 


    def OnText(self, evt):
        preview = _(u"<invalid>")
        text = guiToUni(self.ctrls.fieldFormat.GetValue())
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
        if self.value != u"":
            # Update recent time formats list
            
            try:
                self.recentFormats.remove(self.value)
            except ValueError:
                pass
                
            self.recentFormats.insert(0, self.value)
            if len(self.recentFormats) > 10:
                self.recentFormats = self.recentFormats[:10]

            # Escape to store it in configuration
            tfs = u";".join([escapeForIni(f, u";") for f in self.recentFormats])
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
        d = wx.PreDialog()
        self.PostCreate(d)

        self.parent = parent
        self.mainControl = mainControl
        self.value = value

        res = wx.xrc.XmlResource.Get()
        res.LoadOnDialog(self, self.parent, "FontFaceDialog")

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
            
        wx.EVT_BUTTON(self, wx.ID_OK, self.OnOk)
        wx.EVT_LISTBOX(self, GUI_ID.lbFacenames, self.OnFaceSelected)
        wx.EVT_LISTBOX_DCLICK(self, GUI_ID.lbFacenames, self.OnOk)


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



class ExportDialog(wx.Dialog):
    def __init__(self, mainControl, ID, continuousExport=False, title=None,
                 pos=wx.DefaultPosition, size=wx.DefaultSize):
        d = wx.PreDialog()
        self.PostCreate(d)
        
        self.mainControl = mainControl
        self.value = None
        
        self.listPagesOperation = SearchReplaceOperation()  # ListWikiPagesOperation()
        self.continuousExport = continuousExport
        self.savedExports = None
        
        # In addition to exporter list, this set will contain type tags of all
        # supported exports (used for saved exports list).
        self.supportedExportTypes = set()
        res = wx.xrc.XmlResource.Get()
        res.LoadOnDialog(self, self.mainControl, "ExportDialog")

        self.ctrls = XrcControls(self)

        if continuousExport:
            self.SetTitle(_(u"Continuous Export"))

        self.emptyPanel = None

        exporterList = [] # List of tuples (<exporter object>, <export tag>,
                          # <readable description>, <additional options panel>)

        addOptSizer = LayerSizer()

        # TODO Move to ExportOperation.py
        for ob in Exporters.describeExporters(self.mainControl):   # TODO search plugins
            for tp in ob.getExportTypes(self.ctrls.additOptions, continuousExport):
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

                # Add Tuple (Exporter object, export type tag,
                #     export type description, additional options panel)
                exporterList.append((ob, tp[0], tp[1], panel))
                self.supportedExportTypes.add(tp[0])
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

        self.exporterList = exporterList

        self.ctrls.btnOk.SetId(wx.ID_OK)
        self.ctrls.btnCancel.SetId(wx.ID_CANCEL)
        
        defdir = self.mainControl.getConfig().get("main", "export_default_dir",
                u"")
        if defdir == u"":
            defdir = self.mainControl.getLastActiveDir()

        self.ctrls.tfDestination.SetValue(defdir)

        for e in self.exporterList:
            e[3].Show(False)
            e[3].Enable(False)
            self.ctrls.chExportTo.Append(e[2])
            
#         # Enable first addit. options panel
#         self.exporterList[0][3].Enable(True)
#         self.exporterList[0][3].Show(True)

        self.ctrls.chExportTo.SetSelection(0)  
        self._refreshForEtype()
        self._refreshSavedExportsList()

        # Fixes focus bug under Linux
        self.SetFocus()

        wx.EVT_CHOICE(self, GUI_ID.chExportTo, self.OnExportTo)
        wx.EVT_CHOICE(self, GUI_ID.chSelectedSet, self.OnChSelectedSet)

        wx.EVT_LISTBOX_DCLICK(self, GUI_ID.lbSavedExports, self.OnLoadAndRunExport)

        wx.EVT_BUTTON(self, wx.ID_OK, self.OnOk)
        wx.EVT_BUTTON(self, GUI_ID.btnSelectDestination, self.OnSelectDest)
        wx.EVT_BUTTON(self, GUI_ID.btnSaveExport, self.OnSaveExport)
        wx.EVT_BUTTON(self, GUI_ID.btnLoadExport, self.OnLoadExport)
        wx.EVT_BUTTON(self, GUI_ID.btnLoadAndRunExport, self.OnLoadAndRunExport)
        wx.EVT_BUTTON(self, GUI_ID.btnDeleteExports, self.OnDeleteExports)


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
            self.ctrls.stDestination.SetLabel(_(u"Destination directory:"))
        else:
            # File destination
            self.ctrls.stDestination.SetLabel(_(u"Destination file:"))


    def OnExportTo(self, evt):
        self._refreshForEtype()
        evt.Skip()


    def OnChSelectedSet(self, evt):
        selset = self.ctrls.chSelectedSet.GetSelection()
        if selset == 3:  # Custom
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
                        _(u"Destination directory does not exist"))
                return
            
            if not isdir(pathEnc(self.ctrls.tfDestination.GetValue())):
                self.mainControl.displayErrorMessage(
                        _(u"Destination must be a directory"))
                return
        else:
            if exists(pathEnc(self.ctrls.tfDestination.GetValue())) and \
                    not isfile(pathEnc(self.ctrls.tfDestination.GetValue())):
                self.mainControl.displayErrorMessage(
                        _(u"Destination must be a file"))
                return

        sarOp = self._getEffectiveListWikiPagesOperation()
        if sarOp is None:
            return

        if panel is self.emptyPanel:
            panel = None

        pgh = ProgressHandler(_(u"Exporting"), u"", 0, self)
        pgh.open(0)
        pgh.update(0, _(u"Preparing"))

        try:
            if self.continuousExport:
                ob.startContinuousExport(self.mainControl.getWikiDocument(),
                        sarOp, etype, guiToUni(self.ctrls.tfDestination.GetValue()),
                        self.ctrls.compatFilenames.GetValue(), ob.getAddOpt(panel),
                        pgh)
    
                self.value = ob
            else:
                wordList = self.mainControl.getWikiDocument().searchWiki(sarOp,
                        True)
        
                try:
                    ob.export(self.mainControl.getWikiDocument(), wordList, etype, 
                            guiToUni(self.ctrls.tfDestination.GetValue()), 
                            self.ctrls.compatFilenames.GetValue(), ob.getAddOpt(panel),
                            pgh)
                except ExportException, e:
                    self.mainControl.displayErrorMessage(_(u"Error while exporting"),
                    unicode(e))

        finally:
            pgh.close()
            self.EndModal(wx.ID_OK)

        
    def OnSelectDest(self, evt):
        ob, etype, desc, panel = \
                self.exporterList[self.ctrls.chExportTo.GetSelection()][:4]

        expDestWildcards = ob.getExportDestinationWildcards(etype)

        if expDestWildcards is None:
            # Only transfer between GUI elements, so no unicode conversion
            seldir = wx.DirSelector(_(u"Select Export Directory"),
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
                
            wcs.append(_(u"All files (*.*)"))
            wcs.append(u"*")
            
            wcs = u"|".join(wcs)
            
            selfile = wx.FileSelector(_(u"Select Export File"),
                    self.ctrls.tfDestination.GetValue(),
                    default_filename = "", default_extension = "",
                    wildcard = wcs, flags=wx.SAVE | wx.OVERWRITE_PROMPT,
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
        import SearchAndReplace as Sar

        # Create wordList (what to export)
        selset = self.ctrls.chSelectedSet.GetSelection()
        root = self.mainControl.getCurrentWikiWord()

        if root is None and selset in (0, 1):
            self.mainControl.displayErrorMessage(
                    _(u"No real wiki word selected as root"))
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
        wikiData = self.mainControl.getWikiData()
        unifNames = wikiData.getDataBlockUnifNamesStartingWith(u"savedexport/")

        result = []
        for un in unifNames:
            name = un[12:]
            content = wikiData.retrieveDataBlock(un)
            xmlDoc = minidom.parseString(content)
            xmlNode = xmlDoc.firstChild
            etype = Serialization.serFromXmlUnicode(xmlNode, u"exportTypeName")
            if etype not in self.supportedExportTypes:
                # Export type of saved export not supported
                continue

            result.append((name, xmlNode))

        self.mainControl.getCollator().sortByFirst(result)

        self.savedExports = result

        self.ctrls.lbSavedExports.Clear()
        for exportName, xmlNode in self.savedExports:
            self.ctrls.lbSavedExports.Append(uniToGui(exportName))



    def OnSaveExport(self, evt):
        defValue = u""
        
        sels = self.ctrls.lbSavedExports.GetSelections()
        
        if len(sels) == 1:
            defValue = self.savedExports[sels[0]][0]

        while True:
            title = guiToUni(wx.GetTextFromUser(_(u"Title:"),
                    _(u"Choose export title"), defValue, self))
            if title == u"":
                return  # Cancel
                
            if (u"savedexport/" + title) in self.mainControl.getWikiData()\
                    .getDataBlockUnifNamesStartingWith(
                    u"savedexport/" + title):

                answer = wx.MessageBox(
                        _(u"Do you want to overwrite existing export '%s'?") %
                        title, _(u"Overwrite export"),
                        wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION, self)
                if answer == wx.NO:
                    continue

            xmlDoc = minidom.getDOMImplementation().createDocument(None, None, None)
            xmlHead = xmlDoc.createElement(u"savedExport")

            xmlNode = self._buildSavedExport(xmlHead, xmlDoc)
            if xmlNode is None:
                return
            
            xmlDoc.appendChild(xmlNode)
            content = xmlDoc.toxml("utf-8")
            xmlDoc.unlink()
            self.mainControl.getWikiData().storeDataBlock(
                    u"savedexport/" + title, content,
                    storeHint=DATABLOCK_STOREHINT_INTERN)
            
            self._refreshSavedExportsList()
            return


    def OnLoadExport(self, evt):
        self._loadExport()
        
        
    def OnLoadAndRunExport(self, evt):
        if self._loadExport():
            self._runExporter()

#     def OnLoadAndRunSearch(self, evt):
#         if self._loadSearch():
#             try:
#                 self._refreshSavedExportsList()
#             except re.error, e:
#                 self.displayErrorMessage(_(u'Error in regular expression'),
#                         _(unicode(e)))


    def OnDeleteExports(self, evt):
        sels = self.ctrls.lbSavedExports.GetSelections()
        
        if len(sels) == 0:
            return

        answer = wx.MessageBox(
                _(u"Do you want to delete %i export(s)?") % len(sels),
                _(u"Delete export"),
                wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION, self)
        if answer == wx.NO:
            return

        for s in sels:
            self.mainControl.getWikiData().deleteDataBlock(
                    u"savedexport/" + self.savedExports[s][0])
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
                    _(u"Selected export type does not support saving"))
            return None   # TODO Error message!!

        Serialization.serToXmlUnicode(xmlHead, xmlDoc, u"exportTypeName", etype)

        Serialization.serToXmlUnicode(xmlHead, xmlDoc, u"destinationPath",
                guiToUni(self.ctrls.tfDestination.GetValue()))

        pageSetXml = xmlDoc.createElement(u"pageSet")
        xmlHead.appendChild(pageSetXml)

        sarOp = self._getEffectiveListWikiPagesOperation()
        if sarOp is None:
            return None

#         if isinstance(lpOp, SearchReplaceOperation):
#             pageSetXml.setAttribute(u"type", u"searchReplaceOperation")
#         elif isinstance(lpOp, ListWikiPagesOperation):
#             pageSetXml.setAttribute(u"type", u"listWikiPagesOperation")

        sarOp.serializeToXml(pageSetXml, xmlDoc)

        addOptXml = xmlDoc.createElement(u"additionalOptions")
        xmlHead.appendChild(addOptXml)

        addOptXml.setAttribute(u"version", unicode(addOptVer))
        addOptXml.setAttribute(u"type", u"simpleTuple")

        Serialization.convertTupleToXml(addOptXml, xmlDoc, ob.getAddOpt(panel))

        return xmlHead



    def _showExportProfile(self, xmlNode):
        try:
            etypeProfile = Serialization.serFromXmlUnicode(xmlNode,
                    u"exportTypeName")

            for sel, (ob, etype, desc, panel) in enumerate(self.exporterList):
                if etype == etypeProfile:
                    break
            else:
                self.mainControl.displayErrorMessage(
                        _(u"Export type '%s' of saved export is not supported") %
                        etypeProfile)
                return False

            addOptXml = Serialization.findXmlElementFlat(xmlNode,
                    u"additionalOptions")

            addOptVersion = int(addOptXml.getAttribute(u"version"))

            if addOptVersion != ob.getAddOptVersion():
                self.mainControl.displayErrorMessage(
                        _(u"Saved export uses different version for additional "
                        "options than current export\nExport type: '%s'\n"
                        "Saved export version: %i\nCurrent export version: %i") %
                        (etypeProfile, addOptVersion, ob.getAddOptVersion()))
                return False 

            if addOptXml.getAttribute(u"type") != u"simpleTuple":
                self.mainControl.displayErrorMessage(
                        _(u"Type of additional option storage ('%s') is unknown") %
                        addOptXml.getAttribute(u"type"))
                return False
    
            pageSetXml = Serialization.findXmlElementFlat(xmlNode, u"pageSet")
            
            sarOp = SearchReplaceOperation()
    
    #         if pageSetXml.getAttribute(u"type") == u"searchReplaceOperation":
    #             lpOp = SearchReplaceOperation()
    #         elif pageSetXml.getAttribute(u"type") == u"listWikiPagesOperation":
    #             lpOp = ListWikiPagesOperation()
    #         else:
    #             return # TODO Error message!
            
            sarOp.serializeFromXml(pageSetXml)
    
            addOpt = Serialization.convertTupleFromXml(addOptXml)
    
            self.listPagesOperation = sarOp
            self.ctrls.chSelectedSet.SetSelection(3)
            self.ctrls.chExportTo.SetSelection(sel)
            ob.setAddOpt(addOpt, panel)
    
            self.ctrls.tfDestination.SetValue(uniToGui(
                    Serialization.serFromXmlUnicode(xmlNode, u"destinationPath")))
                    
            self._refreshForEtype()
            
            return True
        except SerializationException, e:
            self.mainControl.displayErrorMessage(_(u"Error during retrieving "
                    "saved export: ") + e.message)


ExportDialog.runModal = staticmethod(runDialogModalFactory(ExportDialog))





class ImportDialog(wx.Dialog):
    def __init__(self, parent, ID, mainControl, title="Import",
                 pos=wx.DefaultPosition, size=wx.DefaultSize):
        d = wx.PreDialog()
        self.PostCreate(d)
        
        self.parent = parent
        self.mainControl = mainControl
        
        res = wx.xrc.XmlResource.Get()
        res.LoadOnDialog(self, self.parent, "ImportDialog")

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

        wx.EVT_CHOICE(self, GUI_ID.chImportFormat, self.OnImportFormat)

        wx.EVT_BUTTON(self, wx.ID_OK, self.OnOk)
        wx.EVT_BUTTON(self, GUI_ID.btnSelectSource, self.OnSelectSrc)


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
            self.ctrls.stSource.SetLabel(_(u"Source directory:"))
        else:
            # File source
            self.ctrls.stSource.SetLabel(_(u"Source file:"))


    def OnImportFormat(self, evt):
        self._refreshForItype()
        evt.Skip()



    def OnOk(self, evt):
        # Run importer
        ob, itype, desc, panel = \
                self.importerList[self.ctrls.chImportFormat.GetSelection()][:4]
                
        if not exists(guiToUni(self.ctrls.tfSource.GetValue())):
            self.mainControl.displayErrorMessage(
                    _(u"Source does not exist"))
            return

        # If this returns None, import goes to a directory
        impSrcWildcards = ob.getImportSourceWildcards(itype)
        if impSrcWildcards is None:
            # Import from a directory
            
            if not isdir(guiToUni(self.ctrls.tfSource.GetValue())):
                self.mainControl.displayErrorMessage(
                        _(u"Source must be a directory"))
                return
        else:
            if not isfile(guiToUni(self.ctrls.tfSource.GetValue())):
                self.mainControl.displayErrorMessage(
                        _(u"Source must be a file"))
                return

        if panel is self.emptyPanel:
            panel = None

        try:
            ob.doImport(self.mainControl.getWikiDataManager(), itype, 
                    guiToUni(self.ctrls.tfSource.GetValue()), 
                    False, ob.getAddOpt(panel))
        except ImportException, e:
            self.mainControl.displayErrorMessage(_(u"Error while importing"),
                    unicode(e))

        self.EndModal(wx.ID_OK)

        
    def OnSelectSrc(self, evt):
        ob, itype, desc, panel = \
                self.importerList[self.ctrls.chImportFormat.GetSelection()][:4]

        impSrcWildcards = ob.getImportSourceWildcards(itype)

        if impSrcWildcards is None:
            # Only transfer between GUI elements, so no unicode conversion
            seldir = wx.DirSelector(_(u"Select Import Directory"),
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
                
            wcs.append(_(u"All files (*.*)"))
            wcs.append(_(u"*"))
            
            wcs = u"|".join(wcs)
            
            selfile = wx.FileSelector(_(u"Select Import File"),
                    self.ctrls.tfSource.GetValue(),
                    default_filename = "", default_extension = "",
                    wildcard = wcs, flags=wx.OPEN | wx.FILE_MUST_EXIST,
                    parent=self)

            if selfile:
                self.ctrls.tfSource.SetValue(selfile)



def _children(win, indent=0):
    print " " * indent + repr(win), win.GetId()
    for c in win.GetChildren():
        _children(c, indent=indent+2)



class NewWikiSettings(wx.Dialog):
    """
    Dialog to choose options when creating a new wiki or when a wiki with
    damaged configuration file is opened.
    """
    DEFAULT_GREY = 1

    def __init__(self, parent, ID, mainControl, defDbHandler=None,
            defWikiLang=None, title="", pos=wx.DefaultPosition,
            size=wx.DefaultSize):
        d = wx.PreDialog()
        self.PostCreate(d)

        self.mainControl = mainControl
        self.value = None, None

        res = wx.xrc.XmlResource.Get()
        res.LoadOnDialog(self, parent, "NewWikiSettingsDialog")

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
        else:
            self.ctrls.lbDatabaseType.Enable(False)
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

        self.ctrls.btnOk.SetId(wx.ID_OK)
        self.ctrls.btnCancel.SetId(wx.ID_CANCEL)

        wx.EVT_BUTTON(self, wx.ID_OK, self.OnOk)


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
        
        self.value = dbH, wlH

        self.EndModal(wx.ID_OK)

NewWikiSettings.runModal = staticmethod(runDialogModalFactory(NewWikiSettings))



class AboutDialog(wx.Dialog):
    """ An about box that uses an HTML window """

    TEXT_TEMPLATE = N_(u'''
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
        wx.Dialog.__init__(self, pWiki, -1, _(u'About WikidPad'),
                          size=(470, 330) )
        
        if sqlite is None:
            sqliteVer = _(u"N/A")
        else:
            sqliteVer = sqlite.getLibVersion()

        text = _(self.TEXT_TEMPLATE) % (VERSION_STRING,
                escapeHtml(pWiki.globalConfigDir), escapeHtml(sqliteVer),
                escapeHtml(wx.__version__))

        html = wx.html.HtmlWindow(self, -1)
        html.SetPage(text)
        button = wx.Button(self, wx.ID_OK, _(u"Okay"))

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



class SimpleInfoDialog(wx.Dialog):
    def __init__(self, *args, **kwargs):
        wx.Dialog.__init__(self, *args, **kwargs)

        self.txtBgColor = self.GetBackgroundColour()

        button = wx.Button(self, wx.ID_OK)
        button.SetDefault()

        self.mainsizer = wx.BoxSizer(wx.VERTICAL)

        self.fillInfoLines()

        inputsizer = wx.BoxSizer(wx.HORIZONTAL)
        inputsizer.Add(button, 0, wx.ALL | wx.EXPAND, 5)
        inputsizer.Add((0, 0), 1)   # Stretchable spacer

        self.mainsizer.Add(inputsizer, 0, wx.ALL | wx.EXPAND, 5)
        
        wx.EVT_BUTTON(self, wx.ID_OK, self.OnOk)
        wx.EVT_CLOSE(self, self.OnOk)


        self.SetSizer(self.mainsizer)
        self.Fit()

        # Fixes focus bug under Linux
        self.SetFocus()


    def _addLine(self, label, value):
        inputsizer = wx.BoxSizer(wx.HORIZONTAL)
        inputsizer.Add(wx.StaticText(self, -1, label), 1,
                wx.ALL | wx.EXPAND, 5)
        ctl = wx.TextCtrl(self, -1, value, style = wx.TE_READONLY)
        ctl.SetBackgroundColour(self.txtBgColor)
        inputsizer.Add(ctl, 1, wx.ALL | wx.EXPAND, 5)
        
        self.mainsizer.Add(inputsizer, 0, wx.EXPAND)
        
        return ctl

        
    def fillInfoLines(self):
        raise NotImplementedError #abstract
        
    
    def OnOk(self, evt):
        evt.Skip()
        



class WikiPropertiesDialog(SimpleInfoDialog):
    """
    Show general information about currently open wiki
    """
    def __init__(self, parent, id, mainControl):
        self.mainControl = mainControl
        SimpleInfoDialog.__init__(self, parent, id, 'Wiki Info',
                          size=(470, 330) )

    def fillInfoLines(self):
        wd = self.mainControl.getWikiDocument()

        wikiData = wd.getWikiData()

        label = _(u"Wiki database backend:")
        if wd is None:
            value = _(u"N/A")
        else:
            value = wd.getDbtype()

        self._addLine(label, value)

        label = _(u"Number of wiki pages:")
        if wd is None:
            value = _(u"N/A")
        else:
            value = unicode(len(wikiData.getAllDefinedWikiPageNames()))

        self._addLine(label, value)



class WikiJobDialog(SimpleInfoDialog):
    """
    Show information about currently open wiki
    """
    def __init__(self, parent, id, mainControl):
        self.jobTxtCtrl = None
        self.mainControl = mainControl

        SimpleInfoDialog.__init__(self, parent, id, 'Jobs',
                          size=(470, 330) )

        # Start timer
        self.timer = wx.Timer(self, GUI_ID.TIMER_JOBDIALOG)
        self.OnTimer(None)
        self.timer.Start(500, False)

        wx.EVT_TIMER(self, GUI_ID.TIMER_JOBDIALOG, self.OnTimer)


    def OnOk(self, evt):
        evt.Skip()
        self.timer.Stop()
        

    def fillInfoLines(self):
        self.jobTxtCtrl = self._addLine(_(u"Number of Jobs:"), u"0")

    def OnTimer(self, evt):
        wd = self.mainControl.getWikiDocument()
        if wd is not None:
            exe = wd.getUpdateExecutor()
            if exe is not None:
                self.jobTxtCtrl.SetValue(unicode(exe.getJobCount()))



# TODO Move to better module
class ImagePasteSaver:
    """
    Helper class to store image settings (format, quality) and to 
    perform saving on request.
    """
    def __init__(self):
        self.prefix = u""  # Prefix before random numbers in filename
        self.formatNo = 0  # Currently either 0:None, 1:PNG or 2:JPG
        self.quality = 75   # Quality for JPG image


    def readOptionsFromConfig(self, config):
        """
        config -- SingleConfiguration or CombinedConfiguration to read default
                settings from into the object
        """
        self.prefix = config.get("main", "editor_imagePaste_filenamePrefix", u"")

        self.formatNo = config.getint("main", "editor_imagePaste_fileType", u"")

        quality = config.getint("main", "editor_imagePaste_quality", 75)
        quality = min(100, quality)
        quality = max(0, quality)

        self.quality = quality


    def setQualityByString(self, s):
        try:
            quality = int(s)
            quality = min(100, quality)
            quality = max(0, quality)
    
            self.quality = quality
        except ValueError:
            return


#     def setFormatByFormatNo(self, formatNo):
#         if formatNo == 1:
#             self.format = "png"
#         elif formatNo == 2:
#             self.format = "jpg"
#         else:  # formatNo == 0
#             self.format = "none"


    def saveFile(self, fs, img):
        """
        fs -- FileStorage to save into
        img -- wx.Image to save

        Returns absolute path of saved image or None if not saved
        """
        if self.formatNo < 1 or self.formatNo > 2:
            return None

        img.SetOptionInt(u"quality", self.quality)

        if self.formatNo == 1:   # PNG
            destPath = fs.findDestPathNoSource(u".png", self.prefix)
        elif self.formatNo == 2:   # JPG
            destPath = fs.findDestPathNoSource(u".jpg", self.prefix)

        if destPath is None:
            # Couldn't find unused filename
            return None

        if self.formatNo == 1:   # PNG
            img.SaveFile(destPath, wx.BITMAP_TYPE_PNG)
        elif self.formatNo == 2:   # JPG
            img.SaveFile(destPath, wx.BITMAP_TYPE_JPEG)

        return destPath


    def saveWmfFromClipboardToFileStorage(self, fs):
        if WindowsHacks is None:
            return None
        
        return WindowsHacks.saveWmfFromClipboardToFileStorage(fs, self.prefix)


    def saveMetaFile(self, fs, metaFile):
        """
        fs -- FileStorage to save into
        rawData -- raw bytestring to save

        Returns absolute path of saved image or None if not saved
        """
        destPath = fs.findDestPathNoSource(u".wmf", self.prefix)
        
        if destPath is None:
            # Couldn't find unused filename
            return None

        metaDC = wx.MetaFileDC(destPath)
        metaFile.Play(metaDC)
        metaDC.Close()

#         writeEntireFile(destPath, rawData)
        
        return destPath




class ImagePasteDialog(wx.Dialog):
    def __init__(self, pWiki, ID, imgpastesaver, title=None,
                 pos=wx.DefaultPosition, size=wx.DefaultSize):
        d = wx.PreDialog()
        self.PostCreate(d)

        self.pWiki = pWiki
        res = wx.xrc.XmlResource.Get()
        res.LoadOnDialog(self, self.pWiki, "ImagePasteDialog")

        self.ctrls = XrcControls(self)

        if title is not None:
            self.SetTitle(title)

        self.ctrls.tfEditorImagePasteFilenamePrefix.SetValue(imgpastesaver.prefix)
        self.ctrls.chEditorImagePasteFileType.SetSelection(imgpastesaver.formatNo)
        self.ctrls.tfEditorImagePasteQuality.SetValue(unicode(
                imgpastesaver.quality))

        self.imgpastesaver = ImagePasteSaver()

        self.ctrls.btnOk.SetId(wx.ID_OK)
        self.ctrls.btnCancel.SetId(wx.ID_CANCEL)
        
        self.OnFileTypeChoice(None)
        
        # Fixes focus bug under Linux
        self.SetFocus()

        wx.EVT_BUTTON(self, wx.ID_OK, self.OnOk)
        wx.EVT_CHOICE(self, GUI_ID.chEditorImagePasteFileType,
                self.OnFileTypeChoice)


    def getImagePasteSaver(self):
        return self.imgpastesaver
        
    def OnFileTypeChoice(self, evt):
        # Make quality field gray if not JPG format
        enabled = self.ctrls.chEditorImagePasteFileType.GetSelection() == 2
        self.ctrls.tfEditorImagePasteQuality.Enable(enabled)


    def OnOk(self, evt):
        try:
            imgpastesaver = ImagePasteSaver()
            imgpastesaver.prefix = \
                    self.ctrls.tfEditorImagePasteFilenamePrefix.GetValue()
            imgpastesaver.formatNo = \
                    self.ctrls.chEditorImagePasteFileType.GetSelection()
            imgpastesaver.setQualityByString(
                    self.ctrls.tfEditorImagePasteQuality.GetValue())

            self.imgpastesaver = imgpastesaver
        finally:
            self.EndModal(wx.ID_OK)





