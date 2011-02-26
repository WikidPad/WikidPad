"""
"""
import os, os.path, traceback, sqlite3

import wx, wx.xrc

# from .wxHelper import XrcControls
# 
# import Consts

from .OsAbstract import normalizePath
from . import StringOps, WindowLayout

from EnhancedGrid import EnhancedGrid

from .ConnectWrapPysqlite import ConnectWrapSyncCommit
from .DocPages import AliasWikiPage

from .wxHelper import XrcControls, GUI_ID, runDialogModalFactory


class InfoDatabase:
    def __init__(self, wikiDocument):
        self.tempDb = None
        self.wikiDocument = wikiDocument
        
    def _createDatabase(self):
        """
        Create empty database with needed scheme.
        """
    
        tempDb = ConnectWrapSyncCommit(sqlite3.connect(ur"C:\Daten\Projekte\Wikidpad\Current\fmtest.sli"))
        # Items (files and directories) found in file storage
        tempDb.execSql("create table fStorItems("
                "id integer primary key not null, "
                "fullpath text not null default '', " # absolute path to item (as user would expect it)
                "normpath text not null default '', " # absolute normalized path to item (also lower-cased for Windows)
                "relpath text not null default '', " # relative path from root of file storage (the "files" directory)
                "type integer not null default 0, " # 0: file, 1: directory
                "containerId integer not null default -1, " # id of containing directory or -1 if root
                "directref integer not null default 0," # !=0: referenced directly
                "downwardref integer not null default 0," # !=0: inferred reference downwards
                "upwardref integer not null default 0," # !=0: inferred reference upwards
                "action integer not null default 0," # action to do (set by user during dialog)
                "isdefaultaction integer not null default 0," # !=0:  action  is default and not set especially for this item
                "calcaction integer not null default 0, " # calculated action
                "errormsg text not null default '' " # error message (created during dialog)
                        # (inferred and indirectly set by user during dialog)
                ");")


        # Items (files and directories) referenced on wiki pages
        tempDb.execSql("create table refedItems("
                "id integer primary key not null, "
                "fullpath text not null default ''," # absolute path to item (as user would expect it)
                "normpath text not null default ''," # absolute normalized path to item (also lower-cased for Windows)
                "infstore integer not null default 0," # !=0: path lies in file store (but item doesn't need to exist)               
                "present integer not null default 0" # !=0: item exists
#                 "fstoreId integer not null default -1" # id of item in  fstoritem  or -1 if outside of f.store or not present at all
                ");")
        
        
        # Map from unifiedNames of the wiki pages to the  refeditems  they reference
        tempDb.execSql("create table unifNameToItem("
                "unifName text not null default '',"  # unified name
                "refeditemId integer not null default 0," # id in  refeditems
                "relative integer not null default 0," # !=0: "rel://" URL, ==0: "file:" URL
                "tokenPos integer not null default -1," # character position of the token containing the link
                "tokenLength integer not null default -1," # character length of the token
                "corePos integer not null default -1," # character position of the link core
                        # (actual URL without surrounding characters)
                "coreLength integer not null default -1" # character length of link core
                ");")


#                 "constraint depgraphpk primary key (unifName, refeditemId)"

        tempDb.commit()

        self.tempDb = tempDb
        
    def getSqlDb(self):
        return self.tempDb


    def _scanFileStore(self):
        assert self.tempDb
        
        fileStorDir = self.wikiDocument.getFileStorage().getStoragePath()
        
        if not os.path.isdir(fileStorDir):
            # No file storage present
            return

        self.tempDb.execSql("insert into fStorItems(fullpath, normpath, "
                "relpath, type, containerId) values(?, ?, '', 1, -1)",
                        (fileStorDir, normalizePath(fileStorDir)))

        # Using a stack instead of recursion to avoid hitting rec. limit
        dirStack = [(fileStorDir, self.tempDb.lastrowid, u"")]
        
        while dirStack:
            procDir, procDirId, relPath = dirStack.pop()
        
            items = os.listdir(procDir)
#             fpItems = (os.path.join(procDir, n) for n in items)
            
            for fn in items:
                fpi = os.path.join(procDir, fn)
                relFpi = os.path.join(relPath, fn)
                
                if os.path.isfile(StringOps.longPathEnc(fpi)):
                    self.tempDb.execSql("insert into fStorItems(fullpath, "
                            "normpath, relpath, type, containerId) "
                            "values(?, ?, ?, 0, ?)",
                            (fpi, normalizePath(fpi), relFpi, procDirId))
                elif os.path.isdir(StringOps.longPathEnc(fpi)) \
                        and not os.path.islink(StringOps.longPathEnc(fpi)):
                    self.tempDb.execSql("insert into fStorItems(fullpath, "
                            "normpath, relpath, type, containerId) "
                            "values(?, ?, ?, 1, ?)",
                            (fpi, normalizePath(fpi), relFpi, procDirId))
                    dirStack.append((fpi, self.tempDb.lastrowid, relFpi))



    def _scanLinks(self, progresshandler):
        wikiWords = self.wikiDocument.getWikiData().getAllDefinedWikiPageNames()
        fileStorDir = normalizePath(self.wikiDocument.getFileStorage()
                .getStoragePath())

        progresshandler.open(len(wikiWords) + 1)
        try:
            step = 1

            for wikiWord in wikiWords:
                progresshandler.update(step, _(u"Scan links in %s") % wikiWord)

                wikiPage = self.wikiDocument._getWikiPageNoErrorNoCache(wikiWord)
                if isinstance(wikiPage, AliasWikiPage):
                    # This should never be an alias page
                    # This can only happen if there is a real page with
                    # the same name as an alias
                    continue  # TODO: Better solution

                pageAst = wikiPage.getLivePageAst()
                
                for urlNode in pageAst.iterDeepByName("urlLink"):
                    url = urlNode.url
                    
                    for actualNode in urlNode.iterDeepByName("url"):
                        if actualNode.getString() == url:
                            break # Inner for
                    else:
                        continue  # Outer for

                    urlPos = actualNode.pos
                    urlLength = len(url)
                    
                    if url.startswith(u"rel://"):
                        url = self.wikiDocument.makeRelUrlAbsolute(url)
                        isRel = 1
                    else:
                        isRel = 0
    
                    if url.startswith(u"file:"):
                        path = StringOps.pathnameFromUrl(url)
                        npath = normalizePath(path)
                        pathId = self.tempDb.execSqlQuerySingleItem(
                                "select id from refedItems where normpath=?",
                                (npath,))
                        if pathId is None:
                            # Create new item
                            lpe = StringOps.longPathEnc(path)
                            pathEx = os.path.isfile(lpe) \
                                    or (os.path.isdir(lpe)
                                    and not os.path.islink(lpe))
                            pathEx = 1 if pathEx else 0
                            
                            inFileStor = fileStorDir == npath or \
                                    StringOps.testContainedInDir(fileStorDir,
                                    npath)
                            inFileStor = 1 if inFileStor else 0
    
                            self.tempDb.execSql("insert into refedItems("
                                    "fullpath, normpath, infstore, present) "
                                    "values(?, ?, ?, ?)",
                                    (path, npath, inFileStor, pathEx))

                            pathId = self.tempDb.lastrowid

                        self.tempDb.execSql("insert or replace into unifNameToItem("
                                "unifName, refeditemId, relative,"
                                "tokenPos, tokenLength, corePos, coreLength) "
                                "values (?, ?, ?, ?, ?, ?, ?)",
                                (wikiPage.getUnifiedPageName(), pathId, isRel,
                                urlNode.pos, urlNode.strLength, urlPos, urlLength))

                step += 1

        finally:
            progresshandler.close()


    def _markDirectlyReferencedInFileStorage(self):
        """
        If a path is present in refedItems and fStorItems then
        fStorItems.directref should be set 1
        """
        
        self.tempDb.execSql("update fStorItems set directref = 1 where "
                "normpath in (select normpath from refedItems)")


    def _inferUpwardRefInFileStorage(self):
        """
        If an item has a direct or upward reference then its containing directory
        should also have an upward reference i.e. if a file is referenced its
        containing directory must be kept, too.
        """
        # This should actually be done recursively. Therefore statement
        # is repeated until no more rows are changed

        self.tempDb.execSqlUntilNoChange("update fStorItems set upwardref = 1 where "
                "upwardref == 0 and id in (select containerId from fStorItems "
                "where directref != 0 or upwardref != 0)")


    def _inferDownwardRefInFileStorage(self):
        """
        If a directory has a direct or downward reference then its contained
        items also get a downward reference. The idea is that if the user
        references a particular directory she probably also wants to keep
        the files and directories in it even if they aren't referenced.
        
        This is optional. Maybe there will be an option later to
        run this only to a given deepness.
        """
        # This should actually be done recursively. Therefore statement
        # is repeated until no more rows are changed

        self.tempDb.execSqlUntilNoChange("update fStorItems set downwardref = 1 where "
                "downwardref == 0 and containerId in "
                "(select id from fStorItems where "
                "type == 1 and (directref != 0 or downwardref != 0))")


    def _deleteUninteresting(self):
        """
        Remove all rows for items which exist and are referenced.
        """
        self.tempDb.execSql("delete from fStorItems where "
                "(directref or downwardref or upwardref)")
        self.tempDb.execSql("delete from refedItems where present")
        self.tempDb.execSql("delete from unifNameToItem where "
                "refeditemId not in (select id from refedItems)")


    def buildDatabaseBeforeDialog(self, progresshandler, options):
        self._createDatabase()
        self._scanFileStore()
        self._scanLinks(progresshandler)
        self._markDirectlyReferencedInFileStorage()
        self._inferUpwardRefInFileStorage()
        if options["downwardRef"]:
            self._inferDownwardRefInFileStorage()
        self._deleteUninteresting()

        self.tempDb.commit()


    def calcActionAndErrorsDuringDialog(self, orphanedActionDefault,
            orphanedDownwardRef):
        
        CALCACTION_KEEP = 1
        CALCACTION_DELETE = 2
        CALCACTION_COLLECT = 5  # 1|4
        

        MASK_KEEP = 1
        MASK_COLLECTOR = 4
#         MASK_DEFAULT = 8
        MASK_INFER_UPWARD = 16
        MASK_INFER_DOWNWARD = 32

        error = False
        
        self.tempDb.commit()

        # 1. Calculate for orphaned file storage items
#         self.tempDb.execSql("update fStorItems set calcaction=action, errormsg=''")

        # Reset
        # Rewriting ACTION_COLLECT (=3) to CALCACTION_COLLECT (=5), copying
        # otherwise
        self.tempDb.execSql("""
                update fStorItems set calcaction = case
                    when action == 3 then 5
                    else action
                end,
                errormsg=''""")


        if orphanedActionDefault == 3:
#             orphanedActionDefault = CALCACTION_COLLECT
#             collectorBit = MASK_COLLECTOR

            # Set collector bit for defaults
            self.tempDb.execSql("update fStorItems set calcaction=4 "
                    "where calcaction==0")

#         if orphanedActionDefault == CALCACTION_COLLECT:


        # First process explicit (non-default) settings

        # If something should be kept (with/without putting on collector)
        # all ancestor containers must be kept
        self.tempDb.execSqlUntilNoChange("update fStorItems set calcaction=calcaction|1|16 "
                "where (calcaction & 1) == 0 and id in (select containerId from fStorItems "
                "where (calcaction & 1) == 1)")

        if orphanedDownwardRef:
            # Only default settings are overwritten
            self.tempDb.execSqlUntilNoChange("update fStorItems "
                    "set calcaction=calcaction|1|32 "
                    "where (calcaction & 3) == 0 and containerId in "
                    "(select id from fStorItems where (calcaction & 1))")

        # If something (a directory) should be deleted, everything in it
        # must be deleted as well
        self.tempDb.execSqlUntilNoChange("update fStorItems "
                "set calcaction=calcaction|2|32 "
                "where (calcaction & 2) == 0 and containerId in "
                "(select id from fStorItems where (calcaction & 2) == 2)")

        # Enforce rule: keep wins over delete
        self.tempDb.execSql("update fStorItems set calcaction=calcaction & ~2 "
                "where (calcaction & 3) == 3")

#         # Fill in default for the rest
#         self.tempDb.execSql("update fStorItems set calcaction=? where "
#                 "calcaction==0", (orphanedActionDefault | MASK_DEFAULT,))


        self.tempDb.execSql("""
                update fStorItems set calcaction = case
                    when (calcaction & 2) == 2 then 2  /* Delete */
                    when (calcaction & 5) == 5 then 3  /* Collect */
                    when (calcaction & 1) == 1 then 1  /* Keep */
                    when (calcaction & 3) == 0 then ?  /* Default */
                    else 0 /* Internal error */
                end,
                errormsg=''""", (orphanedActionDefault,))


#         # Clear the higher bits of calcaction
#         self.tempDb.execSql("update fStorItems set calcaction=calcaction & 7")

#         # Rewrite for ACTION_COLLECT
#         self.tempDb.execSql("update fStorItems set calcaction=3 where "
#                 "calcaction == 5")

        self.tempDb.commit()



# class OrphanedGridRow(object):
#     """
#     One row in the grid of orphaned files (stored in file storage but
#     not referenced)
#     """
#     __slots__ = ("relPath", "typeStr", "action", "calcAction", "id",
#             "containerId", "errorMessage")
# 
# 
#     def __init__(self, relPath, typeStr, id, containerId):
#         self.relPath = relPath
#         self.typeStr = typeStr
#         self.id = id
#         self.containerId = containerId
#         self.action = self.ACTION_DEFAULT
#         self.calcAction = self.ACTION_DEFAULT
#         self.errorMessage = u""



class _OrphanedGrid(EnhancedGrid):
    # Because these contain localized strings, creation must be delayed
    ACTIONCHOICELIST = None
    CALCACTIONNAMES = None

    COLOR_GRAY = wx.Colour(200, 200, 200)

    ACTION_DEFAULT = 0
    ACTION_KEEP = 1
    ACTION_DELETE = 2
    ACTION_LINK_ON_COLLECTOR = 3

    COL_RELPATH = 0
    COL_TYPE = 1
    COL_ACTION = 2
    COL_CALCACTION = 3   # Calculated action (inferred from other actions and dependencies)

    COL_COUNT = 4


    def __init__(self, parent, db, wikiDocument, collator, id=-1):
        EnhancedGrid.__init__(self, parent, id)

        if _OrphanedGrid.ACTIONCHOICELIST is None:
            _OrphanedGrid.ACTIONCHOICELIST = [_(u"Default"), _(u"Keep"),
                    _(u"Delete"), _(u"Collect")]
            _OrphanedGrid.CALCACTIONNAMES = [_(u""), _(u"Keep"),
                    _(u"Delete"), _(u"Collect")]

        self.inputPanel = parent
        self.db = db
        self.wikiDocument = wikiDocument
        self.collator = collator
        
        self.gridToId = []

#         dbData = self.db.getSqlDb().execSqlQuery(
#                 "select relpath, type, id, containerId "
#                 "from fStorItems")
# 
#         self.collator.sortByFirst(dbData)
# 
#         actDef = _(u"Default")
#         typStr = [_(u"File"), _(u"Dir.")]
# 
#         self.gridData = [(relPath, typStr[typ], id, containerId)
#                 for relPath, typ, id, containerId in dbData]

        self.CreateGrid(0, self.COL_COUNT)

        self.SetColLabelValue(self.COL_RELPATH, _(u"Path"))
        self.SetColLabelValue(self.COL_TYPE, _(u"Type"))
        self.SetColLabelValue(self.COL_ACTION, _(u"Action"))
        self.SetColLabelValue(self.COL_CALCACTION, _(u"Calc. action"))
#         self.SetColLabelValue(self.COL_ERROR, _(u"Error"))

        colWidthSum = sum(self.GetColSize(i) for i in range(self.COL_COUNT))
        self.SetMinSize((min(colWidthSum + 40, 600), -1))
#         self.GetParent().SetMinSize((min(colWidthSum + 20, 600), -1))

        readOnlyAttr = wx.grid.GridCellAttr()
        readOnlyAttr.SetReadOnly()
        readOnlyAttr.SetBackgroundColour(self.COLOR_GRAY)

        self.SetColAttr(self.COL_RELPATH, readOnlyAttr)
        self.SetColAttr(self.COL_TYPE, readOnlyAttr)
        self.SetColAttr(self.COL_CALCACTION, readOnlyAttr)
#         self.SetColAttr(self.COL_ERROR, readOnlyAttr)

        actionChEditor = wx.grid.GridCellChoiceEditor(self.ACTIONCHOICELIST,
                False)
        actionAttr = wx.grid.GridCellAttr()
        actionAttr.SetEditor(actionChEditor)
        
        self.SetColAttr(self.COL_ACTION, actionAttr)
        
        self.updateGridBySql()


#     def updateErrorColumn(self):
#         """
#         Update error column of table according to the messages in the
#         grid data entries
#         """
#         
#         for rowNo, row in enumerate(self.gridData):
#             if obj.errorMessage:
#                 self.SetCellBackgroundColour(rowNo, self.COL_RELPATH, wx.RED)
#                 self.SetCellValue(rowNo, self.COL_ERROR, obj.errorMessage)
#             else:
#                 self.SetCellBackgroundColour(rowNo, self.COL_RELPATH,
#                         self.COLOR_GRAY)
#                 self.SetCellValue(rowNo, self.COL_ERROR, "")


    def _isDirectEdit(self, row, col):
        return True

    
    def OnGridSelectCell(self, evt):
        evt.Skip()
#         self.inputPanel.setGridErrorMessage(
#                 self.gridData[evt.GetRow()][1].errorMessage)


    def updateGridBySql(self, orphanedActionDefault=0):
        dbData = self.db.getSqlDb().execSqlQuery(
                "select relpath, type, id, action, calcaction, errormsg "
                "from fStorItems")

        self.collator.sortByFirst(dbData)

        actDef = _(u"Default")
        typStr = [_(u"File"), _(u"Directory")]
        
        if self.GetNumberRows() > 0:
            self.DeleteRows(0, self.GetNumberRows())
        self.AppendRows(len(dbData))
        
        self.gridToId = []

        for rowNo, (relPath, typ, id, action, calcaction, errormsg) \
                in enumerate(dbData):
            self.gridToId.append(id)

            self.SetCellValue(rowNo, self.COL_RELPATH, relPath)
            self.SetCellValue(rowNo, self.COL_TYPE, typStr[typ])
            self.SetCellValue(rowNo, self.COL_ACTION,
                    self.ACTIONCHOICELIST[action])
            self.SetCellValue(rowNo, self.COL_CALCACTION,
                    self.CALCACTIONNAMES[calcaction])
            
            if calcaction != 0 and orphanedActionDefault != 0:
                if action == 0:
                    action = orphanedActionDefault
                if action != calcaction:
                    self.SetCellBackgroundColour(rowNo, self.COL_CALCACTION, wx.RED)
                else:
                    self.SetCellBackgroundColour(rowNo, self.COL_CALCACTION,
                            self.COLOR_GRAY)
            else:
                self.SetCellBackgroundColour(rowNo, self.COL_CALCACTION,
                        self.COLOR_GRAY)



    def storeGridToSql(self):
        sqlDb = self.db.getSqlDb()
        
        for rowNo, id in enumerate(self.gridToId):
            print "--storeGridToSql5", repr((rowNo, id, self.GetCellValue(rowNo,
                    self.COL_ACTION), self.ACTIONCHOICELIST.index(self.GetCellValue(rowNo,
                    self.COL_ACTION))))
            sqlDb.execSql("update fStorItems set action=? where id==?",
                    (self.ACTIONCHOICELIST.index(self.GetCellValue(rowNo,
                    self.COL_ACTION)), id))


#     def calcActionAndErrors(self):
#         # Reset first
#         sqlDb.execSql("update fStorItems set calcaction=action, errormsg=''")
#         
#         actionDefault   # TODO!!!
#         sqlDb.execSql("update fStorItems set calcaction=? where action=0",
#                 (actionDefault,))
#         
#         self.tempDb.execSqlUntilNoChange("update fStorItems set upwardref = 1 where "
#                 "upwardref == 0 and id in (select containerId from fStorItems "
#                 "where directref != 0 or upwardref != 0)")

        
        

#     def _fillRowByData(self, rowNo, obj):
#         self.SetCellValue(rowNo, self.COL_RELPATH, obj.relPath)
#         self.SetCellValue(rowNo, self.COL_TYPE, obj.typeStr)
#         self.SetCellValue(rowNo, self.COL_ACTION,
#                 self.ACTIONCHOICELIST[obj.action])
#         self.SetCellValue(rowNo, self.COL_CALCACTION,
#                 self.CALCACTIONNAMES[obj.calcAction])
#         self.SetCellValue(rowNo, self.COL_ERROR, obj.errorMessage)






# 
# 
# 
# class MissingGridRow(object):
#     """
#     One row in the grid of missing files (referenced but not present)
#     """
#     __slots__ = ("refedItemsId", "fullPath", "itemName", "action",
#             "changeLinkTo")
#     
#     ACTION_DEFAULT = 0
#     ACTION_NONE = 1
#     ACTION_REMOVE_LINKS = 2
#     ACTION_CHANGE_LINKS = 3
    



class FileCleanupInitialDialog(wx.Dialog):
    """
    Dialog to ask for the options for the data to collect on file links
    and file storage
    """

    def __init__(self, mainControl, parent):
        d = wx.PreDialog()
        self.PostCreate(d)

        self.mainControl = mainControl
        self.value = None

        res = wx.xrc.XmlResource.Get()
        res.LoadOnDialog(self, parent, "FileCleanupInitialDialog")

        self.ctrls = XrcControls(self)
        
        value = {"downwardRef": True}
        self.ctrls.cbDownwardRef.SetValue(value["downwardRef"])

        self.ctrls.btnOk.SetId(wx.ID_OK)
        self.ctrls.btnCancel.SetId(wx.ID_CANCEL)

        self.Fit()
        
        # Fixes focus bug under Linux
        self.SetFocus()

        wx.EVT_BUTTON(self, wx.ID_OK, self.OnOk)
    
    
    def GetValue(self):
        return self.value


    def OnOk(self, evt):
        self.value = {"downwardRef": self.ctrls.cbDownwardRef.GetValue()}

        self.EndModal(wx.ID_OK)

FileCleanupInitialDialog.runModal = staticmethod(runDialogModalFactory(
        FileCleanupInitialDialog))




class FileCleanupDialog(wx.Dialog):
    """
    """

    # Because these contain localized strings, creation must be delayed
    ORPHANED_DEFAULTACTIONCHOICELIST = None

    def __init__(self, mainControl, db, parent):
        
        if FileCleanupDialog.ORPHANED_DEFAULTACTIONCHOICELIST is None:
            FileCleanupDialog.ORPHANED_DEFAULTACTIONCHOICELIST = [_(u"Keep"),
                    _(u"Delete"), _(u"Collect")]

        d = wx.PreDialog()
        self.PostCreate(d)

        self.mainControl = mainControl
        self.db = db
        self.value = False

        res = wx.xrc.XmlResource.Get()
        res.LoadOnDialog(self, parent, "FileCleanupDialog")

        self.ctrls = XrcControls(self)

        orphanedGrid = _OrphanedGrid(self, self.db, mainControl.getWikiDocument(),
                mainControl.getCollator())

        res.AttachUnknownControl("gridOrphaned", orphanedGrid, self)

        self.ctrls.btnOk.SetId(wx.ID_OK)
        self.ctrls.btnCancel.SetId(wx.ID_CANCEL)
        
        self.Fit()
        # If the table is too long, a resizing may become necessary
        WindowLayout.setWindowSize(self)
        WindowLayout.setWindowPos(self)

        # Fixes layout problem
        orphanedGrid.GetGrandParent().Layout()
        
        # Fixes focus bug under Linux
        self.SetFocus()

        wx.EVT_BUTTON(self, wx.ID_OK, self.OnOk)
        wx.EVT_BUTTON(self, GUI_ID.btnTest, self.OnTest)

#         wx.EVT_TEXT(self, ID, self.OnText)
#         wx.EVT_CHAR(self.ctrls.text, self.OnCharText)
#         wx.EVT_CHAR(self.ctrls.lb, self.OnCharListBox)
#         wx.EVT_LISTBOX(self, ID, self.OnListBox)
#         wx.EVT_LISTBOX_DCLICK(self, GUI_ID.lb, self.OnOk)

    def GetValue(self):
        return self.value


    def OnOk(self, evt):
#         if not self.ctrls.gridDetails.validateInput():
#             self.ctrls.gridDetails.updateErrorColumn()
#             return
#         
#         self.ctrls.gridDetails.writeGridToDb()
        self.value = True

        self.EndModal(wx.ID_OK)
        
        
    def OnTest(self, evt):
        self.ctrls.gridOrphaned.storeGridToSql()
        self.db.calcActionAndErrorsDuringDialog(
                self.ctrls.chOrphanedDefaultAction.GetSelection() + 1,
                self.ctrls.cbOrphanedDownwardRef.GetValue())


        self.ctrls.gridOrphaned.updateGridBySql(
                self.ctrls.chOrphanedDefaultAction.GetSelection() + 1)

        self.db.getSqlDb().commit()
        return





FileCleanupDialog.runModal = staticmethod(runDialogModalFactory(
        FileCleanupDialog))




def runFileCleanup(mainControl, parent, progresshandler):
    options = FileCleanupInitialDialog.runModal(mainControl, parent)
    if options is None:
        return
        
    db = InfoDatabase(mainControl.getWikiDocument())
    db.buildDatabaseBeforeDialog(progresshandler, options)
    
    FileCleanupDialog.runModal(mainControl, db, parent)

