import sys, os, traceback   # , sqlite3

import wx, wx.grid, wx.xrc

import Consts

from .WikiExceptions import *

from .wxHelper import ModalDialogMixin, XrcControls, GUI_ID

from . import Utilities

from . import WindowLayout

from . import EnhancedGrid

# from EnhancedGrid import EnhancedGrid, ScrollPanel
from . import DocPages

# from timeView import Versioning




# def unifNameToHumanReadable(unifName):
#     """
#     Return human readable description for a unified name
#     """
#     # TODO Move to more central place
#     if unifName.startswith(u"wikipage/"):
#         return _(u"wiki page '%s'") % unifName[9:]
#     elif unifName.startswith(u"funcpage/"):
#         return _(u"functional page '%s'") % DocPages.getHrNameForFuncTag(
#                 unifName[9:])
#     elif unifName.startswith(u"versioning/overview/"):
#         return _(u"version overview for %s") % unifNameToHumanReadable(
#                 unifName[20:])
#     elif unifName.startswith(u"versioning/packet/versionNo/"):
#         versionNo, subUnifName = unifName[28:].split("/", 1)
#         return _(u"version packet (single version no. %s) for %s") % \
#                 (versionNo, unifNameToHumanReadable(subUnifName))
#     elif unifName.startswith(u"savedsearch/"):
#         return _(u"saved search '%s'") % unifName[12:]
#     else:
#         return None
# 
# 
# 
# def _buildErrorMessageList(db):
#     """
#     Build human readable list of uncorrectable errors for dialog.
#     """
#     result = []
#     
#     # List missing dependencies
#     for unifName in db.execSqlQuerySingleColumn(
#             "select unifName from entries where missingDep"):
#         if unifName.startswith(u"versioning/packet/versionNo/"):
#             continue
#         
#         hrName = unifNameToHumanReadable(unifName)
#         if hrName is None:
#             continue
#         
#         result.append((unifName, _(u"Missing data. Can't import %s") % hrName))
#     
#     return result



class RequestGridRow:
    __slots__ = ("doImport", "importVersion", "collisionWithPresent", "renamable",
            "unifNamePrefix", "itemName", "renameImportTo", "renamePresentTo",
            "errorMessage")

    IMPORT_DEFAULT = 0
    IMPORT_YES = 1
    IMPORT_NO = 2
    IMPORT_OVERWRITE = 3

    IMPVERSION_DEFAULT = 0
    IMPVERSION_YES = 1
    IMPVERSION_NO = 2
    IMPVERSION_NOTAVAIL = 3


    def __init__(self, unifName):
        self.doImport = RequestGridRow.IMPORT_NO  # Must be explicitly enabled
        self.importVersion = RequestGridRow.IMPVERSION_NOTAVAIL
        self.collisionWithPresent = None
        # If this is True, unifNamePrefix and itemName must be also filled
        # appropriately 
        self.renamable = False 
        self.unifNamePrefix = None
        self.itemName = None
        self.renameImportTo = ""
        self.renamePresentTo = ""
        self.errorMessage = None
        
        self.setByUnifName(unifName)


    @staticmethod
    def _splitOnMatch(unifName, match):
        if unifName.startswith(match):
            return match, unifName[len(match):]
        
        return None, None
    
    @staticmethod
    def _splitOnMatchSeq(unifName, matchSeq):
        for match in matchSeq:
            if unifName.startswith(match):
                return match, unifName[len(match):]

        return None, None



    def setByUnifName(self, unifName):
        # Check for renamable parts
        m, r = self._splitOnMatchSeq(unifName, ("wikipage/", "savedsearch/",
                "savedpagesearch/"))

        if m is not None:
            self.renamable = True
            self.unifNamePrefix = m
            self.itemName = r
            return
        
        m, r = self._splitOnMatch(unifName, "funcpage/")
        if m is not None:
            self.unifNamePrefix = m
            self.itemName = "<%s>" % DocPages.getHrNameForFuncTag(r)



#     @staticmethod
#     def getCreateFromDict(dct, unifName):
#       
#         obj = dct.get(unifName)
#         if obj is None:
#             obj = RequestGridRow()
#             dct[unifName] = obj
# 
#         return obj



class _RequestGrid(EnhancedGrid.EnhancedGrid):
    # Because these contain localized strings, creation must be delayed
    IMPORTCHOICELIST = None
    VERSIONCHOICELIST = None

    _UNIFPREFIX_TO_HR_NAME_MAP = None

    COLOR_GRAY = wx.Colour(200, 200, 200)

    COL_TYPE = 0
    COL_NAME = 1
    COL_DOIMPORT = 2
    COL_VERSIONS = 3
    COL_REN_IMPORTED = 4
    COL_REN_PRESENT = 5
    COL_ERROR = 6
    
    COL_COUNT = 7

    def __init__(self, parent, db, wikiDocument, collator, id=-1):
        EnhancedGrid.EnhancedGrid.__init__(self, parent, id)

        if _RequestGrid.IMPORTCHOICELIST is None:
            _RequestGrid.IMPORTCHOICELIST = [_("Default"), _("Yes"),
                    _("No"), _("Overwrite")]
            _RequestGrid.VERSIONCHOICELIST = [_("Default"), _("Yes"), _("No")]
            _RequestGrid._UNIFPREFIX_TO_HR_NAME_MAP = {
                    "wikipage/": _("Wiki page"),
                    "funcpage/": _("Func. page"),
                    "savedsearch/": _("Saved search"),
                    "savedpagesearch/": _("Saved page search")
            }

        self.inputPanel = parent
        self.db = db
        self.wikiDocument = wikiDocument
        self.collator = collator
        
        self.requestGridData = list(self._buildInitialData().items())

        # TODO: Group by type of item
        self.collator.sortByFirst(self.requestGridData)
        
#         self.requestGridData.sort(key=lambda item: item[0])

        self.CreateGrid(len(self.requestGridData), self.COL_COUNT)
        
        self.SetColLabelValue(self.COL_TYPE, _("Type"))
        self.SetColLabelValue(self.COL_NAME, _("Name"))
        self.SetColLabelValue(self.COL_DOIMPORT, _("Import"))
        self.SetColLabelValue(self.COL_VERSIONS, _("Version\nImport"))
        self.SetColLabelValue(self.COL_REN_IMPORTED, _("Rename\nimported"))
        self.SetColLabelValue(self.COL_REN_PRESENT, _("Rename\npresent"))
        self.SetColLabelValue(self.COL_ERROR, _("Error"))

#         self.SetColLabelSize(30)

        colWidthSum = sum(self.GetColSize(i) for i in range(self.COL_COUNT))
        self.SetMinSize((min(colWidthSum + 40, 600), -1))
#         self.GetParent().SetMinSize((min(colWidthSum + 20, 600), -1))

        readOnlyAttr = wx.grid.GridCellAttr()
        readOnlyAttr.SetReadOnly()
        readOnlyAttr.SetBackgroundColour(self.COLOR_GRAY)
        
        self.SetColAttr(self.COL_TYPE, readOnlyAttr)
        self.SetColAttr(self.COL_NAME, readOnlyAttr)
        self.SetColAttr(self.COL_ERROR, readOnlyAttr)
        
        importChEditor = wx.grid.GridCellChoiceEditor(self.IMPORTCHOICELIST,
                False)
        importAttr = wx.grid.GridCellAttr()
        importAttr.SetEditor(importChEditor)
        
        self.SetColAttr(self.COL_DOIMPORT, importAttr)

        versionChEditor = wx.grid.GridCellChoiceEditor(self.VERSIONCHOICELIST,
                False)
        versionAttr = wx.grid.GridCellAttr()
        versionAttr.SetEditor(versionChEditor)
        
        self.SetColAttr(self.COL_VERSIONS, versionAttr)

        
        for rowNo, (unifName, obj) in enumerate(self.requestGridData):
            self._fillRowByData(rowNo, unifName, obj)


        self.SetRowLabelSize(20)

        if len(self.requestGridData) > 0:
            self.validateInput()
            self.updateErrorColumn()
            
            self.inputPanel.setGridErrorMessage(
                    self.requestGridData[0][1].errorMessage)
            
            self.Bind(wx.grid.EVT_GRID_SELECT_CELL, self.OnGridSelectCell)



    def _fillRowByData(self, rowNo, unifName, obj):
        if obj.unifNamePrefix is not None:
            unifNamePrefix = obj.unifNamePrefix
            typeHr = self._UNIFPREFIX_TO_HR_NAME_MAP[unifNamePrefix]
        else:
            print("--_fillRowByData9", repr(unifName))
            for k, v in self._UNIFPREFIX_TO_HR_NAME_MAP.items():
                if unifName.startswith(k):
                    typeHr = v
                    unifNamePrefix = k
                    break
            else:
                typeHr = ""  # TODO Error? Message?
                unifNamePrefix = None
            print("--_fillRowByData21", repr((unifName, typeHr, unifNamePrefix)))

        self.SetCellValue(rowNo, self.COL_TYPE, typeHr)
        
        if obj.itemName is not None:
            self.SetCellValue(rowNo, self.COL_NAME, obj.itemName)
        else:
            self.SetCellValue(rowNo, self.COL_NAME, "")  # TODO Error? Message?
        
        self.SetCellValue(rowNo, self.COL_DOIMPORT, self.IMPORTCHOICELIST[obj.doImport])

        if obj.importVersion == RequestGridRow.IMPVERSION_NOTAVAIL:
            self.SetReadOnly(rowNo, self.COL_VERSIONS)
            self.SetCellBackgroundColour(rowNo, self.COL_VERSIONS, self.COLOR_GRAY)
        else:
            self.SetCellValue(rowNo, self.COL_VERSIONS,
                    self.VERSIONCHOICELIST[obj.importVersion])
        
        if not obj.renamable:
            self.SetReadOnly(rowNo, self.COL_REN_IMPORTED)
            self.SetCellBackgroundColour(rowNo, self.COL_REN_IMPORTED, self.COLOR_GRAY)
            self.SetReadOnly(rowNo, self.COL_REN_PRESENT)
            self.SetCellBackgroundColour(rowNo, self.COL_REN_PRESENT, self.COLOR_GRAY)


    def _isDirectEdit(self, row, col):
        return True

    
    def OnGridSelectCell(self, evt):
        evt.Skip()
        self.inputPanel.setGridErrorMessage(
                self.requestGridData[evt.GetRow()][1].errorMessage)

    
    def _buildInitialData(self):
        result = Utilities.DefaultDictParam(RequestGridRow)
        db = self.db

        # Mark version data importable where present
        # Currently only version data for wikipages is supported
        for unifName in db.execSqlQuerySingleColumn(
                "select unifName from entries where importVersionData and "
                "unifName glob 'wikipage/*'"):
            result[unifName].importVersion = RequestGridRow.IMPVERSION_DEFAULT

        # Mark collisions
        for unifName, collisionWithPresent in db.execSqlQuery(
                "select unifName, collisionWithPresent from entries "
                "where collisionWithPresent != ''"):
            result[unifName].collisionWithPresent = collisionWithPresent

        # Mark all appropriate items which should be imported at all
        for unifName in db.execSqlQuerySingleColumn(
                "select unifName from entries where not dontImport and ("
                "unifName glob 'wikipage/*' or "
                "unifName glob 'savedsearch/*' or "
                "unifName glob 'savedpagesearch/*' or "
                "unifName glob 'funcpage/*')"):
            result[unifName].doImport = RequestGridRow.IMPORT_DEFAULT

        return result


    def _resolveImportValue(self, rowNo):
        if self.IsReadOnly(rowNo, self.COL_DOIMPORT):
            return RequestGridRow.IMPORT_NO  # This should not happen, TODO: InternalError?

        result = self.IMPORTCHOICELIST.index(self.GetCellValue(rowNo,
                self.COL_DOIMPORT))
        if result == RequestGridRow.IMPORT_DEFAULT:
            result = self.inputPanel.getDefaultImportValue()

        return result


    def _resolveVersionImportValue(self, rowNo):
        if self.IsReadOnly(rowNo, self.COL_VERSIONS):
            return RequestGridRow.IMPVERSION_NOTAVAIL

        result = self.IMPORTCHOICELIST.index(self.GetCellValue(rowNo,
                self.COL_VERSIONS))
        if result == RequestGridRow.IMPVERSION_DEFAULT:
            result = self.inputPanel.getDefaultVersionImportValue()

        return result


    def validateInput(self):
        """
        Returns iff contents of table are valid and updates the  errorMessage
        of each object to be either None or describe the problem
        """

        isValid = True

        # Set of unifnames which will be created by importing items
        importedUnifNames = set()

        # Dict of unifnames created by renaming existing items as {newName: (unifNamePrefix, oldItemName)}
        presentRenamedToFrom = {}

        langHelper = wx.GetApp().createWikiLanguageHelper(
                self.wikiDocument.getWikiDefaultWikiLanguage())

        for rowNo, (unifName, obj) in enumerate(self.requestGridData):
#             wikiWord = unifName[9:]
            obj.errorMessage = None

            if self._resolveImportValue(rowNo) == RequestGridRow.IMPORT_NO:
                continue

            renImportedItem = self.GetCellValue(rowNo, self.COL_REN_IMPORTED)
            renPresentItem = self.GetCellValue(rowNo, self.COL_REN_PRESENT)
            
            renImportedUnifName = obj.unifNamePrefix + renImportedItem
            renPresentUnifName = obj.unifNamePrefix + renPresentItem

            if renImportedItem != "" and renPresentItem != "":
                # This is forbidden to ensure that if item A is currently
                # present in the database it will also be present after the import
                # (either it was unchanged or replaced).
                # Otherwise if a item B should now be renamed to A we first would
                # have to check if A will be present in database after import even
                # if it was present before.
                obj.errorMessage = _(
                        "You can't rename imported and present item at the same time")
                isValid = False
                continue


            # Check for invalid wiki words if processed item is a wikipage
            if obj.unifNamePrefix == "wikipage/":
                if renImportedItem != "":
                    errMsg = langHelper.checkForInvalidWikiWord(renImportedItem,
                            self.wikiDocument)
    
                    if errMsg is not None:
                        obj.errorMessage = _("Rename imported") + ": " + errMsg
                        isValid = False
                        continue

                if renPresentItem != "":
                    errMsg = langHelper.checkForInvalidWikiWord(renPresentItem,
                            self.wikiDocument)
    
                    if errMsg is not None:
                        obj.errorMessage = _("Rename present") + ": " + errMsg
                        isValid = False
                        continue


            if renImportedItem == "":
                renImportedItem = obj.itemName
                renImportedUnifName = obj.unifNamePrefix + renImportedItem

            # Item was already imported in a previous entry
            if renImportedUnifName in importedUnifNames:
                obj.errorMessage = _("Name collision: Item '%s' will be imported already") % renImportedItem
                isValid = False
                continue

            if renImportedUnifName in presentRenamedToFrom:
                obj.errorMessage = \
                        _("Name collision: Item '%s' will already be created by renaming '%s'") % \
                        (renImportedItem, presentRenamedToFrom[renImportedUnifName][1])
                isValid = False
                continue


            if self._resolveImportValue(rowNo) != RequestGridRow.IMPORT_OVERWRITE and \
                    renPresentItem == "" and \
                    self.wikiDocument.hasDataBlock(renImportedUnifName):
                obj.errorMessage = _("Name collision: Item '%s' exists already in database") % renImportedItem
                isValid = False
                continue


            importedUnifNames.add(renImportedUnifName)

            if renPresentItem != "":
                if renPresentUnifName in importedUnifNames:
                    obj.errorMessage = _("Name collision: Item '%s' will be imported already") % renPresentItem
                    isValid = False
                    continue
                
                if self.wikiDocument.hasDataBlock(renPresentUnifName):
                    obj.errorMessage = _("Name collision: Item '%s' exists already in database") % renPresentItem
                    isValid = False
                    continue

                if renPresentUnifName in presentRenamedToFrom:
                    obj.errorMessage = \
                            _("Name collision: Item '%s' will already be created by renaming '%s'") % \
                            (renImportedItem, presentRenamedToFrom[renPresentUnifName][1])
                    isValid = False
                    continue
                
                presentRenamedToFrom[renPresentUnifName] = \
                        (obj.unifNamePrefix, obj.itemName)


        return isValid


    def updateErrorColumn(self):
        """
        Update error column of table according to the messages in the
        grid data entries
        """
        
        for rowNo, (unifName, obj) in enumerate(self.requestGridData):
            if obj.errorMessage:
                self.SetCellBackgroundColour(rowNo, self.COL_NAME, wx.RED)
                self.SetCellValue(rowNo, self.COL_ERROR, obj.errorMessage)
            else:
                self.SetCellBackgroundColour(rowNo, self.COL_NAME,
                        self.COLOR_GRAY)
                self.SetCellValue(rowNo, self.COL_ERROR, "")


    def writeGridToDb(self):
        """
        Write data from grid back to DB. Function assumes that _validateInput
        was previously run and returned True
        """
        for rowNo, (unifName, obj) in enumerate(self.requestGridData):
            if self._resolveImportValue(rowNo) == RequestGridRow.IMPORT_NO:
                self.db.execSql("""
                    update entries set dontImport=1 where unifName = ?;
                    """, (unifName,))
                continue

            renImportedUnifName = ""
            renPresentUnifName = ""

            if obj.renamable:
                renImportedItem = self.GetCellValue(rowNo, self.COL_REN_IMPORTED)
                renPresentItem = self.GetCellValue(rowNo, self.COL_REN_PRESENT)

                if renImportedItem != "":
                    renImportedUnifName = obj.unifNamePrefix + renImportedItem

                if renPresentItem != "":
                    renPresentUnifName = obj.unifNamePrefix + renPresentItem

            if self._resolveVersionImportValue(rowNo) == RequestGridRow.IMPVERSION_YES:
                importVersionData = 1
            else:
                importVersionData = 0

            self.db.execSql("""
                update entries set renameImportTo = ?, renamePresentTo = ?,
                importVersionData = ? where unifName = ?;
                """, (renImportedUnifName, renPresentUnifName, importVersionData,
                    unifName))


class MultiPageTextImporterDialog(wx.Dialog, ModalDialogMixin):
    """
    """

    def __init__(self, mainControl, db, parent):
        wx.Dialog.__init__(self)

        self.mainControl = mainControl
        self.db = db
        self.value = False

        res = wx.xrc.XmlResource.Get()
        res.LoadDialog(self, parent, "MultiPageTextImporterDialog")

        self.ctrls = XrcControls(self)

        grid = _RequestGrid(self, db, mainControl.getWikiDocument(),
                mainControl.getCollator())

        EnhancedGrid.replaceStandIn(self, self.ctrls.gridDetails, grid)

        self.ctrls.btnOk.SetId(wx.ID_OK)
        self.ctrls.btnCancel.SetId(wx.ID_CANCEL)
        
        self.Fit()
        # If the table is too long, a resizing may become necessary
        WindowLayout.setWindowSize(self)
        WindowLayout.setWindowPos(self)
        
        # Fixes focus bug under Linux
        self.SetFocus()

        self.Bind(wx.EVT_BUTTON, self.OnOk, id=wx.ID_OK)
        self.Bind(wx.EVT_BUTTON, self.OnTest, id=GUI_ID.btnTest)


    def OnOk(self, evt):
        if not self.ctrls.gridDetails.validateInput():
            self.ctrls.gridDetails.updateErrorColumn()
            return

        self.ctrls.gridDetails.writeGridToDb()
        self.value = True

        self.EndModal(wx.ID_OK)


    def OnTest(self, evt):
        self.ctrls.gridDetails.validateInput()
        self.ctrls.gridDetails.updateErrorColumn()



    def GetValue(self):
        return self.value


    def setGridErrorMessage(self, errMsg):
        if errMsg is None:
            errMsg = ""
        
        self.ctrls.stGridErrors.SetLabel(errMsg)


    def getDefaultImportValue(self):
        return self.ctrls.chDefaultImport.GetSelection() + 1

    def getDefaultVersionImportValue(self):
        return self.ctrls.chDefaultVersionImport.GetSelection() + 1

