from __future__ import absolute_import, with_statement

# import hotshot
# _prof = hotshot.Profile("hotshot.prf")

import os, traceback

import wx


from .wxHelper import EnhancedListControl, XrcControls, ModalDialogMixin, \
        GUI_ID, WindowUpdateLocker, appendToMenuByMenuDesc, \
        getAccelPairFromKeyDown

from .Importers import MultiPageTextImporter



class TrashBagList(EnhancedListControl):
    def __init__(self, mainControl, dialog, parent, ID):
        EnhancedListControl.__init__(self, parent, ID,
                style=wx.LC_REPORT | wx.LC_NO_HEADER)

        self.bagList = []
        self.mainControl = mainControl
        self.dialog = dialog
        self.contextMenuItem = -1

        self.InsertColumn(0, u"", width=1)  # wiki word
        self.InsertColumn(1, u"", width=1)  # trash date

#         wx.EVT_CONTEXT_MENU(self, self.OnContextMenu)
        wx.EVT_LIST_ITEM_ACTIVATED(self, self.GetId(),
                self.dialog.OnCmdRestoreSelected)
        wx.EVT_KEY_DOWN(self, self.OnKeyDown)
#         wx.EVT_MENU(self, GUI_ID.CMD_TRASHBAG_RESTORE,
#                 self.OnCmdTrashBagRestore)

        self.updateContent()


    def updateContent(self):
        self.bagList = []

        wikiDoc = self.mainControl.getWikiDocument()
        if wikiDoc is None:
            self._updatePresentation()
            return

        trashcan = wikiDoc.getTrashcan()
        if trashcan is None:
            self._updatePresentation()
            return

        # In trashcan the bags are listed from oldest to newest, we need
        # it the other way
        self.bagList = [bag for bag in reversed(trashcan.getTrashBags())
                if bag.originalUnifiedName.startswith(u"wikipage/")]

        self._updatePresentation()


    def _updatePresentation(self):
        with WindowUpdateLocker(self):
            self.DeleteAllItems()

            formatStr = self.mainControl.getConfig().get("main",
                    "pagestatus_timeformat", u"%Y %m %d")
            # timeView_dateFormat

            for i, bag in enumerate(self.bagList):
                self.InsertStringItem(i, bag.originalUnifiedName[9:])
                self.SetStringItem(i, 1, bag.getFormattedTrashDate(formatStr))
            
            self.autosizeColumn(0)
            self.autosizeColumn(1)
        
    def getSelectedBags(self):
        return [self.bagList[idx] for idx in self.GetAllSelected()]


    def OnKeyDown(self, evt):
        accP = getAccelPairFromKeyDown(evt)
        if accP in ((wx.ACCEL_NORMAL, wx.WXK_DELETE),
                (wx.ACCEL_NORMAL, wx.WXK_NUMPAD_DELETE)):
            self.dialog.OnCmdDeleteSelected(evt)
        else:
            evt.Skip()


#     def OnCmdTrashBagRestore(self, evt):
#         wikiDoc = self.mainControl.getWikiDocument()
#         if wikiDoc is None:
#             return
# 
#         bag = self.bagList[self.contextMenuItem]
#         data = bag.getPacketData()
#         if data is None:
#             return
# 
#         importer = TrashBagMptImporter(self, self.mainControl)
#         # TODO: Catch ImportError
#         success = importer.doImport(wikiDoc, u"multipage_text", None,
#                 False, importer.getAddOpt(None), importData=data)
# 
#         if success:
#             bag.getTrashcan().deleteBag(bag)
#             self.updateContent()
# 
# 
#     def OnContextMenu(self, evt):
#         mousePos = evt.GetPosition()
#         if mousePos == wx.DefaultPosition:
#             # E.g. context menu key was pressed on Windows keyboard
#             item = self.GetFirstSelected()
#         else:
#             item = self.HitTest(self.ScreenToClient(mousePos))[0]
# 
#         self.showContextMenuForItem(item)


#     def showContextMenuForItem(self, item):
#         if item == wx.NOT_FOUND:
#             return
# 
#         menu = wx.Menu()
#         appendToMenuByMenuDesc(menu, _CONTEXT_MENU_TRASHBAG)
#         self.contextMenuItem = item
#         self.PopupMenu(menu)
#         self.contextMenuItem = -1
        



class TrashcanDialog(wx.Dialog, ModalDialogMixin):
    """
    """
    def __init__(self, mainControl, parent):
        d = wx.PreDialog()
        self.PostCreate(d)

        self.mainControl = mainControl

        res = wx.xrc.XmlResource.Get()
        res.LoadOnDialog(self, parent, "TrashcanDialog")

        self.ctrls = XrcControls(self)
        self.ctrls.btnClose.SetId(wx.ID_CANCEL)

        listCtrl = TrashBagList(self.mainControl, self, self, GUI_ID.listDetails)
        res.AttachUnknownControl("listDetails", listCtrl, self)

        wx.EVT_BUTTON(self, GUI_ID.btnRestoreSelected, self.OnCmdRestoreSelected)
        wx.EVT_BUTTON(self, GUI_ID.btnDeleteSelected, self.OnCmdDeleteSelected)
        wx.EVT_BUTTON(self, GUI_ID.btnDeleteAll, self.OnCmdDeleteAll)


    def GetValue(self):
        return None


    def OnCmdRestoreSelected(self, evt):
        wikiDoc = self.mainControl.getWikiDocument()
        if wikiDoc is None:
            return

        bags = self.ctrls.listDetails.getSelectedBags()
        if len(bags) == 0:
            return

        initialRbChoice = None
        for i, bag in enumerate(bags):
            data = bag.getPacketData()
            if data is None:
                continue

            importer = TrashBagMptImporter(self, self.mainControl,
                    i < len(bags) - 1, initialRbChoice)
            # TODO: Catch ImportError
            importer.doImport(wikiDoc, u"multipage_text", None,
                    False, importer.getAddOpt(None), importData=data)
            
            initialRbChoice = importer.initialRbChoice

            if initialRbChoice == TrashBagRenameDialog.RET_CANCEL:
                break
            elif initialRbChoice == TrashBagRenameDialog.RET_SKIP:
                continue

            bag.getTrashcan().deleteBag(bag)

        self.ctrls.listDetails.updateContent()


    def OnCmdDeleteSelected(self, evt):
        bags = self.ctrls.listDetails.getSelectedBags()
        if len(bags) == 0:
            return
        
        answer = wx.MessageBox(
                _(u"Delete %i elements from trashcan?") %
                len(bags), _(u"Delete from trashcan"),
                wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION, self)

        if answer != wx.YES:
            return
        
        for bag in bags:
            bag.getTrashcan().deleteBag(bag)

        self.ctrls.listDetails.updateContent()


    def OnCmdDeleteAll(self, evt):
        wikiDoc = self.mainControl.getWikiDocument()
        if wikiDoc is None:
            return

        if self.ctrls.listDetails.GetItemCount() == 0:
            return

        trashcan = wikiDoc.getTrashcan()
        if trashcan is None:
            return

        answer = wx.MessageBox(
                _(u"Delete all elements from trashcan?"),
                _(u"Delete from trashcan"),
                wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION, self)

        if answer != wx.YES:
            return
        
        trashcan.clear()
#         self.ctrls.listDetails.updateContent()
        
        # If all items are deleted the dialog is useless for the moment
        self.Close()




class TrashBagRenameDialog(wx.Dialog, ModalDialogMixin):
    """
    """
    RET_CANCEL = -1
    RET_OVERWRITE = 0
    RET_SKIP = 1
    RET_RENAME_TRASHBAG = 2
    RET_RENAME_WIKIELEMENT = 3


    def __init__(self, mainControl, parent, unifName, allowSkip=False,
            initialRbChoice=None):
        d = wx.PreDialog()
        self.PostCreate(d)

        self.mainControl = mainControl
        self.value = self.RET_CANCEL, None
        self.unifName = unifName

        res = wx.xrc.XmlResource.Get()
        res.LoadOnDialog(self, parent, "TrashBagRenameDialog")

        self.ctrls = XrcControls(self)
        self.ctrls.btnOk.SetId(wx.ID_OK)
        self.ctrls.btnOk = self.ctrls._byId(wx.ID_OK)
        self.ctrls.btnCancel.SetId(wx.ID_CANCEL)

        self.ctrls.rbSkip.Enable(allowSkip)
        
        if unifName.startswith(u"wikipage/"):
            nameCollision = unifName[9:]
        else:
            nameCollision = unifName  # Should not happen
        
        self.ctrls.stNameCollision.SetLabel(nameCollision)
        
        if allowSkip and initialRbChoice in (self.RET_CANCEL, self.RET_SKIP):
            self.ctrls.rbSkip.SetValue(True)
        elif initialRbChoice == self.RET_RENAME_TRASHBAG:
            self.ctrls.rbRenameTrashBag.SetValue(True)
        elif initialRbChoice == self.RET_RENAME_WIKIELEMENT:
            self.ctrls.rbRenameWikiElement.SetValue(True)

        self.updateValidToWikiWord()
        
        wx.EVT_BUTTON(self, wx.ID_OK, self.OnOk)
        wx.EVT_BUTTON(self, wx.ID_CANCEL, self.OnCancel)
        wx.EVT_TEXT(self, GUI_ID.tfTrashBagTo, self.OnTextTrashBagTo)
        wx.EVT_TEXT(self, GUI_ID.tfWikiElementTo, self.OnTextWikiElementTo)
        wx.EVT_RADIOBUTTON(self, GUI_ID.rbOverwrite, self.OnRadioButtonChanged)
        wx.EVT_RADIOBUTTON(self, GUI_ID.rbSkip, self.OnRadioButtonChanged)
        wx.EVT_RADIOBUTTON(self, GUI_ID.rbRenameTrashBag,
                self.OnRadioButtonChanged)
        wx.EVT_RADIOBUTTON(self, GUI_ID.rbRenameWikiElement,
                self.OnRadioButtonChanged)

        # Fixes focus bug under Linux
        self.SetFocus()


    def _getReturnValueForCurrentSettings(self):
        if self.ctrls.rbOverwrite.GetValue():
            return self.RET_OVERWRITE, None
        elif self.ctrls.rbSkip.GetValue():
            return self.RET_SKIP, None
        elif self.ctrls.rbRenameTrashBag.GetValue():
            return self.RET_RENAME_TRASHBAG, self.ctrls.tfTrashBagTo.GetValue()
        elif self.ctrls.rbRenameWikiElement.GetValue():
            return self.RET_RENAME_WIKIELEMENT, \
                    self.ctrls.tfWikiElementTo.GetValue()
        
    def OnOk(self, evt):
        self.value = self._getReturnValueForCurrentSettings() 
        self.EndModal(wx.ID_OK)

    # Without this, runModal would return None on cancel 
    def OnCancel(self, evt):
        self.EndModal(wx.ID_OK)


    def GetValue(self):
        return self.value


    def OnTextTrashBagTo(self, evt):
        self.ctrls.rbRenameTrashBag.SetValue(True)
        self.updateValidToWikiWord()

    def OnTextWikiElementTo(self, evt):
        self.ctrls.rbRenameWikiElement.SetValue(True)
        self.updateValidToWikiWord()

    # TODO: Check if called by  rb*.SetValue(True)
    def OnRadioButtonChanged(self, evt):
        self.updateValidToWikiWord()


    # Copied from AdditionalDialogs.RenameWikiWordDialog
    def updateValidToWikiWord(self):
        toWikiWord = self._getReturnValueForCurrentSettings()[1]

        if toWikiWord is None:
            msg = None
        else:
            msg = self._checkValidToWikiWord(toWikiWord)

        if msg is None:
            self.ctrls.btnOk.Enable(True)
            self.ctrls.stErrorMessage.SetLabel(u"")
        else:
            self.ctrls.btnOk.Enable(False)
            self.ctrls.stErrorMessage.SetLabel(msg)


    def _checkValidToWikiWord(self, toWikiWord):

        if not toWikiWord or len(toWikiWord) == 0:
            return u"" # No error message, but disable OK
            
        langHelper = wx.GetApp().createWikiLanguageHelper(
                self.mainControl.getWikiDefaultWikiLanguage())

        errMsg = langHelper.checkForInvalidWikiWord(toWikiWord,
                self.mainControl.getWikiDocument())

        if errMsg:
            return errMsg   # _(u"Invalid wiki word. %s") % errMsg

#         if self.fromWikiWord == toWikiWord:
#             return _(u"Can't rename to itself")

        if not self.mainControl.getWikiDocument().isCreatableWikiWord(toWikiWord):
            return _(u"Word already exists")

        # Word is OK
        return None




class TrashBagMptImporter(MultiPageTextImporter):
    """
    We need a modified MPT importer if a trash bag is imported back into
    the wiki
    """
    
    def __init__(self, guiParent, mainControl, allowSkip=False,
            initialRbChoice=None):
        MultiPageTextImporter.__init__(self, mainControl)
        self.guiParent = guiParent
        self.allowSkip = allowSkip
        self.initialRbChoice = initialRbChoice
    
    
    def _doUserDecision(self):
        """
        Called to present GUI to user for deciding what to do.
        This method is overwritten for trashcan GUI.
        Returns False if user canceled operation
        """
        unifName = self.tempDb.execSqlQuerySingleItem("select unifName "
                "from entries where seen and unifname glob 'wikipage/*' "
                "limit 1")
        if unifName is None:
            return False

        ret, element = TrashBagRenameDialog.runModal(self.mainControl,
                self.guiParent, unifName, allowSkip=self.allowSkip,
                initialRbChoice=self.initialRbChoice)

        self.initialRbChoice = ret
        if ret in (TrashBagRenameDialog.RET_CANCEL,
                TrashBagRenameDialog.RET_SKIP):
            return False
        elif ret == TrashBagRenameDialog.RET_OVERWRITE:
            return True
        elif ret == TrashBagRenameDialog.RET_RENAME_TRASHBAG:
            self.tempDb.execSql("""
                    update entries set renameImportTo = ?
                    where unifName = ?;
                    """, (u"wikipage/" + element, unifName))
            return True
        elif ret == TrashBagRenameDialog.RET_RENAME_WIKIELEMENT:
            self.tempDb.execSql("""
                    update entries set renamePresentTo = ?
                    where unifName = ?;
                    """, (u"wikipage/" + element, unifName))
            return True

        return False





# _CONTEXT_MENU_TRASHBAG = \
# u"""
# Restore;CMD_TRASHBAG_RESTORE;Restore from trashcan back to wiki
# """
# 
# # Entries to support i18n of context menus
# if False:
#     N_(u"Restore")
#     N_(u"Restore from trashcan back to wiki")



