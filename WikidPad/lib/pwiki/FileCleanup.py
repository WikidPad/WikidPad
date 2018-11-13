"""
"""
import os, os.path, traceback, sqlite3

import wx, wx.html, wx.xrc

from .wxHelper import GUI_ID, wxKeyFunctionSink, XrcControls, \
        ModalDialogMixin

# from .wxHelper import XrcControls
#
# import Consts

from .OsAbstract import normalizePath, deleteFile
from . import StringOps, WindowLayout

from . import EnhancedGrid

from .ConnectWrapPysqlite import ConnectWrapSyncCommit
from .DocPages import AliasWikiPage



class InfoDatabase:
    def __init__(self, mainControl):
        self.tempDb = None
        self.mainControl = mainControl
        self.wikiDocument = mainControl.getWikiDocument()

        self.fileStorDir = self.wikiDocument.getFileStorage().getStoragePath()
        self.normFileStorDir = normalizePath(self.fileStorDir)


    def _createDatabase(self):
        """
        Create empty database with needed scheme.
        """

#         tempDb = ConnectWrapSyncCommit(sqlite3.connect(ur"C:\Daten\Projekte\Wikidpad\Current\fmtest.sli"))
        tempDb = ConnectWrapSyncCommit(sqlite3.connect(r""))
        # Items (files and directories) found in file storage
        tempDb.execSql("create table fStorItems("
                "id integer primary key not null, "
                "procCounter integer not null, " # Just a counter to keep the order in which items where processed first
                "fullpath text not null default '', " # absolute path to item (as user would expect it)
                "normpath text not null default '', " # absolute normalized path to item (also lower-cased for Windows)
                "relpath text not null default '', " # relative path from root of file storage (the "files" directory)
                "type integer not null default 0, " # 0: file, 1: directory
                "deepness integer not null, " # root dir. has 0, everything else has <deepness of container>+1
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
                "present integer not null default 0," # !=0: item exists
                "action integer not null default 0" # action to do (set by user during dialog)
#                 "fstoreId integer not null default -1" # id of item in  fstoritem  or -1 if outside of f.store or not present at all
                ");")


        # Map from unifiedNames of the wiki pages to the  refeditems  they reference
        tempDb.execSql("create table unifNameToItem("
                "unifName text not null default '',"  # unified name of the wiki page
                "presentationUrl text not null default '',"  # URL as it is written on wiki page
                "refedItemId integer not null default 0," # id in  refeditems
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

        if not os.path.isdir(self.fileStorDir):
            # No file storage present
            return

        self.tempDb.execSql("insert into fStorItems(procCounter, fullpath, "
                "normpath, relpath, type, containerId, deepness) "
                "values(0, ?, ?, '', 1, -1, 0)",
                        (self.fileStorDir, self.normFileStorDir))
        procCounter = 1

        # Using a stack instead of recursion to avoid hitting rec. limit
        dirStack = [(self.fileStorDir, self.tempDb.lastrowid, "", 0)]

        while dirStack:
            procDir, procDirId, relPath, dirDeepness = dirStack.pop()

            items = os.listdir(procDir)
#             fpItems = (os.path.join(procDir, n) for n in items)

            for fn in items:
                fpi = os.path.join(procDir, fn)
                relFpi = os.path.join(relPath, fn)

                if os.path.isfile(StringOps.longPathEnc(fpi)):
                    self.tempDb.execSql("insert into fStorItems(procCounter, "
                            "fullpath, normpath, relpath, type, containerId, "
                            "deepness) values(?, ?, ?, ?, 0, ?, ?)",
                            (procCounter, fpi, normalizePath(fpi), relFpi,
                            procDirId, dirDeepness + 1))
                    procCounter += 1
                elif os.path.isdir(StringOps.longPathEnc(fpi)) \
                        and not os.path.islink(StringOps.longPathEnc(fpi)):
                    self.tempDb.execSql("insert into fStorItems(procCounter, "
                            "fullpath, normpath, relpath, type, containerId, "
                            "deepness) values(?, ?, ?, ?, 1, ?, ?)",
                            (procCounter, fpi, normalizePath(fpi), relFpi,
                            procDirId, dirDeepness + 1))
                    procCounter += 1
                    dirStack.append((fpi, self.tempDb.lastrowid, relFpi,
                            dirDeepness + 1))


    def updateWikiPage(self, wikiPage):
        pageAst = wikiPage.getLivePageAst()

        self.tempDb.execSql("delete from unifNameToItem where "
                "unifName == ?", (wikiPage.getUnifiedPageName(),))

        for urlNode in pageAst.iterDeepByName("urlLink"):
            url = urlNode.url

            if url.startswith("rel://"):
                url = self.wikiDocument.makeRelUrlAbsolute(url)
                isRel = 1
            else:
                isRel = 0

            if url.startswith("file:"):
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

                    inFileStor = self.normFileStorDir == npath or \
                            StringOps.testContainedInDir(self.normFileStorDir,
                            npath)
                    inFileStor = 1 if inFileStor else 0

                    self.tempDb.execSql("insert into refedItems("
                            "fullpath, normpath, infstore, present) "
                            "values(?, ?, ?, ?)",
                            (path, npath, inFileStor, pathEx))

                    pathId = self.tempDb.lastrowid

                self.tempDb.execSql("insert or replace into unifNameToItem("
                        "unifName, presentationUrl, refedItemId, relative,"
                        "tokenPos, tokenLength, corePos, coreLength) "
                        "values (?, ?, ?, ?, ?, ?, ?, ?)",
                        (wikiPage.getUnifiedPageName(),
                        urlNode.coreNode.getString(), pathId, isRel,
                        urlNode.pos, urlNode.strLength,
                        urlNode.coreNode.pos,
                        urlNode.coreNode.strLength))


    def _scanLinks(self, progresshandler):
        wikiWords = self.wikiDocument.getWikiData().getAllDefinedWikiPageNames()

        progresshandler.open(len(wikiWords) + 1)
        try:
            step = 1

            for wikiWord in wikiWords:
                progresshandler.update(step, _("Scan links in %s") % wikiWord)

                wikiPage = self.wikiDocument._getWikiPageNoErrorNoCache(wikiWord)
                if isinstance(wikiPage, AliasWikiPage):
                    # This should never be an alias page
                    # This can only happen if there is a real page with
                    # the same name as an alias
                    continue  # TODO: Better solution

                self.updateWikiPage(wikiPage)
#                 pageAst = wikiPage.getLivePageAst()
# 
#                 for urlNode in pageAst.iterDeepByName("urlLink"):
#                     url = urlNode.url
# 
#                     if url.startswith(u"rel://"):
#                         url = self.wikiDocument.makeRelUrlAbsolute(url)
#                         isRel = 1
#                     else:
#                         isRel = 0
# 
#                     if url.startswith(u"file:"):
#                         path = StringOps.pathnameFromUrl(url)
#                         npath = normalizePath(path)
#                         pathId = self.tempDb.execSqlQuerySingleItem(
#                                 "select id from refedItems where normpath=?",
#                                 (npath,))
#                         if pathId is None:
#                             # Create new item
#                             lpe = StringOps.longPathEnc(path)
#                             pathEx = os.path.isfile(lpe) \
#                                     or (os.path.isdir(lpe)
#                                     and not os.path.islink(lpe))
#                             pathEx = 1 if pathEx else 0
# 
#                             inFileStor = self.normFileStorDir == npath or \
#                                     StringOps.testContainedInDir(self.normFileStorDir,
#                                     npath)
#                             inFileStor = 1 if inFileStor else 0
# 
#                             self.tempDb.execSql("insert into refedItems("
#                                     "fullpath, normpath, infstore, present) "
#                                     "values(?, ?, ?, ?)",
#                                     (path, npath, inFileStor, pathEx))
# 
#                             pathId = self.tempDb.lastrowid
# 
#                         self.tempDb.execSql("insert or replace into unifNameToItem("
#                                 "unifName, presentationUrl, refedItemId, relative,"
#                                 "tokenPos, tokenLength, corePos, coreLength) "
#                                 "values (?, ?, ?, ?, ?, ?, ?, ?)",
#                                 (wikiPage.getUnifiedPageName(),
#                                 urlNode.coreNode.getString(), pathId, isRel,
#                                 urlNode.pos, urlNode.strLength,
#                                 urlNode.coreNode.pos,
#                                 urlNode.coreNode.strLength))

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


    def deleteUninteresting(self):
        """
        Remove all rows for items which exist and are referenced.
        """
        self.tempDb.execSql("delete from fStorItems where "
                "(directref or downwardref or upwardref)")
        self.tempDb.execSql("delete from refedItems where present")
        self.tempDb.execSql("delete from unifNameToItem where "
                "refedItemId not in (select id from refedItems)")


    def buildDatabaseBeforeDialog(self, progresshandler, options):
        self._createDatabase()
        self._scanFileStore()
        self._scanLinks(progresshandler)
        self._markDirectlyReferencedInFileStorage()
        self._inferUpwardRefInFileStorage()
        if options["downwardRef"]:
            self._inferDownwardRefInFileStorage()
        self.deleteUninteresting()

        self.tempDb.commit()


    def calcActionAndErrorsDuringDialog(self, orphanedActionDefault,
            orphanedDownwardRef):

        CALCACTION_KEEP = 1
        CALCACTION_DELETE = 2
        CALCACTION_COLLECT = 5  # 1|4


        MASK_KEEP = 1
        MASK_COLLECT = 4
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
#             collectorBit = MASK_COLLECT

            # Set collector bit for defaults if default action is "Collect"
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
            # If a directory is kept explicitly and not by the upward inference
            # above, everything in it with default setting is also kept
            self.tempDb.execSqlUntilNoChange("update fStorItems "
                    "set calcaction=calcaction|1|32 "
                    "where (calcaction & 3) == 0 and containerId in "
                    "(select id from fStorItems where (calcaction & 1) == 1 and "
                    "(calcaction & 16) == 0)")

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

        # Final cleanup
        self.tempDb.execSql("""
                update fStorItems set calcaction = case
                    when (calcaction & 2) == 2 then 2  /* Delete */
                    when (calcaction & 5) == 5 then 3  /* Collect */
                    when (calcaction & 1) == 1 then 1  /* Keep */
                    when (calcaction & 3) == 0 then ?  /* Default */
                    else 0 /* Internal error */
                end,
                errormsg=''""", (orphanedActionDefault,))


        self.tempDb.commit()


    def _deleteOrphanedItems(self):
        """
        Delete orphaned items which where selected for deletion. Items are
        deleted in the order of their deepness, meaning items with most path
        elements first. Not the most efficient but simplest and safest way.
        """
        for p in self.tempDb.execSqlQuerySingleColumn("select fullpath "
                "from fStorItems where calcaction == 2 order by deepness desc"):
            try:
                deleteFile(p)
            except:
                traceback.print_exc()


    def _pruneEmptyDirsFromFileStorage(self):
        pass # TODO
#         if not os.path.isdir(self.fileStorDir):
#             # No file storage present
#             return

    def _listOrphanedFilesOnCollector(self, collectorPageName):
        """
        Add links to collectorPageName of files which are set to be placed there
        """
        absPaths = self.tempDb.execSqlQuerySingleColumn("select fullpath "
                "from fStorItems where calcaction == 3 order by procCounter")

        if len(absPaths) == 0:
            # Nothing to do
            return

        config = self.mainControl.getConfig()

        try:
            prefix = StringOps.strftimeUB(StringOps.unescapeForIni(config.get(
                "main", "editor_filePaste_prefix", "")))
        except:
            traceback.print_exc()
            prefix = ""   # TODO Error message?

        try:
            middle = StringOps.strftimeUB(StringOps.unescapeForIni(config.get(
                "main", "editor_filePaste_middle", " ")))
        except:
            traceback.print_exc()
            middle = " "   # TODO Error message?

        try:
            suffix = StringOps.strftimeUB(StringOps.unescapeForIni(config.get(
                "main", "editor_filePaste_suffix", "")))
        except:
            traceback.print_exc()
            suffix = ""   # TODO Error message?

        bracketedUrl = config.getboolean("main",
                "editor_filePaste_bracketedUrl", True)

        langHelper = wx.GetApp().createWikiLanguageHelper(
                self.wikiDocument.getWikiDefaultWikiLanguage())

        urls = [langHelper.createUrlLinkFromPath(self.wikiDocument, ap,
                relative=True, bracketed=bracketedUrl) for ap in absPaths]

        page = self.wikiDocument.getWikiPageNoError(collectorPageName)
        page.appendLiveText(prefix + middle.join(urls) + suffix)


    def runAfterDialog(self, collectorPageName):
        """
        Apply actions after dialog was closed with "OK". IMPORTANT:
        calcActionAndErrorsDuringDialog() must have been run for the final
        db state before this function can be called.
        """
        self._deleteOrphanedItems()
#         self._pruneEmptyDirsFromFileStorage()  # as an option
        self._listOrphanedFilesOnCollector(collectorPageName)





class _OrphanedGrid(EnhancedGrid.EnhancedGrid):
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


    def __init__(self, parent, dialog, db, wikiDocument, collator, id=-1):
        EnhancedGrid.EnhancedGrid.__init__(self, parent, id)

        if _OrphanedGrid.ACTIONCHOICELIST is None:
            _OrphanedGrid.ACTIONCHOICELIST = [_("Default"), _("Keep"),
                    _("Delete"), _("Collect")]
            _OrphanedGrid.CALCACTIONNAMES = [_(""), _("Keep"),
                    _("Delete"), _("Collect")]

        self.fileCleanupDialog = dialog
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

        self.SetColLabelValue(self.COL_RELPATH, _("Path"))
        self.SetColLabelValue(self.COL_TYPE, _("Type"))
        self.SetColLabelValue(self.COL_ACTION, _("Action"))
        self.SetColLabelValue(self.COL_CALCACTION, _("Calc. action"))
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
#         self.fileCleanupDialog.setGridErrorMessage(
#                 self.gridData[evt.GetRow()][1].errorMessage)


    def updateGridBySql(self, orphanedActionDefault=0):
        dbData = self.db.getSqlDb().execSqlQuery(
                "select relpath, type, id, action, calcaction, errormsg "
                "from fStorItems")

        self.collator.sortByFirst(dbData)

        actDef = _("Default")
        typStr = [_("File"), _("Directory")]

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
#             print "--storeGridToSql5", repr((rowNo, id, self.GetCellValue(rowNo,
#                     self.COL_ACTION), self.ACTIONCHOICELIST.index(self.GetCellValue(rowNo,
#                     self.COL_ACTION))))
            sqlDb.execSql("update fStorItems set action=? where id==?",
                    (self.ACTIONCHOICELIST.index(self.GetCellValue(rowNo,
                    self.COL_ACTION)), id))






class _MissingGrid(EnhancedGrid.EnhancedGrid):
    # Because these contain localized strings, creation must be delayed
    ACTIONCHOICELIST = None

    COLOR_GRAY = wx.Colour(200, 200, 200)

    ACTION_DEFAULT = 0
    ACTION_KEEP = 1
    ACTION_DELETE = 2

    COL_FULLPATH = 0
#     COL_ACTION = 1

    COL_COUNT = 1


    def __init__(self, parent, dialog, db, wikiDocument, collator, id=-1):
        EnhancedGrid.EnhancedGrid.__init__(self, parent, id)

        if _MissingGrid.ACTIONCHOICELIST is None:
            _MissingGrid.ACTIONCHOICELIST = [_("Default"), _("Keep"),
                    _("Delete")]

        self.fileCleanupDialog = dialog
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

        self.SetColLabelValue(self.COL_FULLPATH, _("Path"))
#         self.SetColLabelValue(self.COL_ACTION, _(u"Action"))
#         self.SetColLabelValue(self.COL_ERROR, _(u"Error"))

        colWidthSum = sum(self.GetColSize(i) for i in range(self.COL_COUNT))
        self.SetMinSize((min(colWidthSum + 40, 600), -1))
#         self.GetParent().SetMinSize((min(colWidthSum + 20, 600), -1))

        readOnlyAttr = wx.grid.GridCellAttr()
        readOnlyAttr.SetReadOnly()
        readOnlyAttr.SetBackgroundColour(self.COLOR_GRAY)

        self.SetColAttr(self.COL_FULLPATH, readOnlyAttr)

#         actionChEditor = wx.grid.GridCellChoiceEditor(self.ACTIONCHOICELIST,
#                 False)
#         actionAttr = wx.grid.GridCellAttr()
#         actionAttr.SetEditor(actionChEditor)
# 
#         self.SetColAttr(self.COL_ACTION, actionAttr)

        self.updateGridBySql()

        self.Bind(wx.grid.EVT_GRID_SELECT_CELL, self.OnSelectCell)
        self.Bind(wx.grid.EVT_GRID_CMD_CELL_LEFT_DCLICK, self.OnCellDClick)

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


    def OnSelectCell(self, evt):
        self.fileCleanupDialog.updateMissingLinkingPagesListBoxByRefedItemId(
                self.gridToId[evt.GetRow()])
        evt.Skip()
#         self.fileCleanupDialog.setGridErrorMessage(
#                 self.gridData[evt.GetRow()][1].errorMessage)


    def OnCellDClick(self, evt):
        self.fileCleanupDialog.runFirstInMissingLinkingPagesListBox()


    def updateGridBySql(self):
        dbData = self.db.getSqlDb().execSqlQuery(
                "select fullpath, id, present, action "
                "from refedItems")

        self.collator.sortByFirst(dbData)

        actDef = _("Default")
        
        row = self.GetGridCursorRow()
        col = self.GetGridCursorCol()

        if self.GetNumberRows() > 0:
            self.DeleteRows(0, self.GetNumberRows())
        self.AppendRows(len(dbData))

        self.gridToId = []

        for rowNo, (fullPath, id, present, action) \
                in enumerate(dbData):
            self.gridToId.append(id)

            self.SetCellValue(rowNo, self.COL_FULLPATH, fullPath)
#             self.SetCellValue(rowNo, self.COL_ACTION,
#                     self.ACTIONCHOICELIST[action])

        self.SetGridCursor(row, col)


    def storeGridToSql(self):
        pass

#         sqlDb = self.db.getSqlDb()
# 
#         for rowNo, id in enumerate(self.gridToId):
# #             print "--storeGridToSql5", repr((rowNo, id, self.GetCellValue(rowNo,
# #                     self.COL_ACTION), self.ACTIONCHOICELIST.index(self.GetCellValue(rowNo,
# #                     self.COL_ACTION))))
#             sqlDb.execSql("update refedItems set action=? where id==?",
#                     (self.ACTIONCHOICELIST.index(self.GetCellValue(rowNo,
#                     self.COL_ACTION)), id))




class _MissingLinkingPagesItemInfo:
    __slots__ = ("__weakref__", "unifName", "wikiWord", "hitList",
            "fileCleanupDialog")

    def __init__(self, fileCleanupDialog, unifName, hitList):
        self.fileCleanupDialog = fileCleanupDialog
        
        self.unifName = unifName
        if unifName.startswith("wikipage/"):
            self.wikiWord = unifName[9:]
        else:
            self.wikiWord = unifName  # TODO: This should never happen
            
        hitList.sort()
        self.hitList = hitList


#     def buildOccurrence(self, text, before, after, pos, occNumber, maxOccCount):
#         self.html = None
#         basum = before + after
#         self.occNumber = -1
#         self.occPos = pos
#         self.maxCountOccurrences = maxOccCount
# 
#         if basum == 0:
#             # No context
#             self.occHtml = u""
#             return self
#         
#         if pos[0] is None:
#             # All occurences where deleted meanwhile dialog was open
#             self.occHtml = u""
#             self.occNumber = 0
#             self.occCount = 0
#             return self
#         
#         if pos[0] == -1:
#             # No position -> use beginning of text
#             self.occHtml = escapeHtml(text[0:basum])
#             return self
#         
#         s = max(0, pos[0] - before)
#         e = min(len(text), pos[1] + after)
#         self.occHtml = u"".join([escapeHtml(text[s:pos[0]]), 
#             "<b>", escapeHtml(text[pos[0]:pos[1]]), "</b>",
#             escapeHtml(text[pos[1]:e])])
#             
#         self.occNumber = occNumber
#         return self


    def getCharSelection(self):
        if len(self.hitList) == 0:
            return (-1, -1)
        
        return (self.hitList[0][0], self.hitList[0][1])


    def getHtml(self):
        modified = self.fileCleanupDialog.isModifiedPage(self.unifName)
        
        if modified:
            result = ['<font color="GRAY"><b>%s</b>' % \
                    StringOps.escapeHtml(self.wikiWord)]
        else:
            result = ['<font color="BLUE"><b>%s</b></font>' % \
                    StringOps.escapeHtml(self.wikiWord)]
        
        if len(self.hitList) > 4:
            for hit in self.hitList[:3]:
                result.append("<br />\n%s" % StringOps.escapeHtml(hit[2]))

            result.append("<br />\n...")
        else:
            for hit in self.hitList:
                result.append("<br />\n%s" % StringOps.escapeHtml(hit[2]))

        if modified:
            result.append("</font>")

        return "".join(result)




class _MissingLinkingPagesListBox(wx.html.HtmlListBox):
    def __init__(self, parent, db, mainControl, collator, ID):
        wx.html.HtmlListBox.__init__(self, parent, ID, style = wx.SUNKEN_BORDER)

        self.fileCleanupDialog = parent
        self.db = db
        self.mainControl = mainControl
        self.collator = collator
        self.lastRefedItemId = -1

        self.itemInfo = []
        self.SetItemCount(0)
        
        self.Bind(wx.EVT_KILL_FOCUS, self.OnKillFocus)
        self.Bind(wx.EVT_LISTBOX_DCLICK, self.OnDClick, id=ID)

#         self.contextMenuSelection = -2

#         self.Bind(wx.EVT_LEFT_DOWN, self.OnLeftDown)
#         self.Bind(wx.EVT_LEFT_DCLICK, self.OnLeftDown)
#         self.Bind(wx.EVT_MIDDLE_DOWN, self.OnMiddleButtonDown)
#         self.Bind(wx.EVT_KEY_DOWN, self.OnKeyDown)
#         self.Bind(wx.EVT_CONTEXT_MENU, self.OnContextMenu)
# 
# 
#         self.Bind(wx.EVT_MENU, self.OnActivateThis, id=GUI_ID.CMD_ACTIVATE_THIS)
#         wx.EVT_MENU(self, GUI_ID.CMD_ACTIVATE_NEW_TAB_THIS,
#                 self.OnActivateNewTabThis)
#         wx.EVT_MENU(self, GUI_ID.CMD_ACTIVATE_NEW_TAB_BACKGROUND_THIS,
#                 self.OnActivateNewTabBackgroundThis)


    def OnKillFocus(self, evt):
        self.SetSelection(-1)


    def OnGetItem(self, i):
#         if self.isShowingSearching:
#             return u"<b>" + _(u"Searching... (click into field to abort)") + u"</b>"
#         elif self.GetCount() == 0:
#             return u"<b>" + _(u"Not found") + u"</b>"

        try:
            return self.itemInfo[i].getHtml()
        except IndexError:
            return ""


    def updateByRefedItemId(self, refedItemId):
        self.lastRefedItemId = refedItemId
        dbData = self.db.getSqlDb().execSqlQuery("select unifName, "
                "corePos, coreLength, presentationUrl from unifNameToItem "
                "where refedItemId == ?", (refedItemId,))

        if len(dbData) == 0:
            self.itemInfo = []
            self.SetItemCount(0)
            self.Refresh()
            return

        # Group by unified name (wiki word)
        groupDict = {}
        for un, cp, cl, pu in dbData:
            groupDict.setdefault(un, []).append((cp, cl, pu))

        finalData = list(groupDict.items())

        self.collator.sortByFirst(finalData)

        self.itemInfo = [_MissingLinkingPagesItemInfo(self.fileCleanupDialog,
                un, hitList) for un, hitList in finalData]

        self.SetItemCount(len(self.itemInfo))
        self.Refresh()


    def update(self):
        if self.lastRefedItemId > -1:
            self.updateByRefedItemId(self.lastRefedItemId)


    def activateSelection(self, sel):
        if sel == -1 or self.GetItemCount() == 0:
            return

        info = self.itemInfo[sel]

        self.mainControl.openWikiPage(info.wikiWord)

        editor = self.mainControl.getActiveEditor()
        if editor is not None:
            csel = info.getCharSelection()
            if csel[0] != -1:
                self.mainControl.getActiveEditor().showSelectionByCharPos(
                        csel[0], csel[0] + csel[1])
#                 self.mainControl.getActiveEditor().ensureSelectionExpanded()

            # Works in fast search popup only if called twice
            # (keeping it here just in case)
            editor.SetFocus()
            editor.SetFocus()


    def OnDClick(self, evt):
        self.activateSelection(self.GetSelection())



# 
# 
#     def OnLeftDown(self, evt):
#         if self.isShowingSearching:
#             self.searchWikiDialog.stopSearching()
# 
#         if self.GetItemCount() == 0:
#             return  # no evt.Skip()?
# 
#         pos = evt.GetPosition()
#         hitsel = self.HitTest(pos)
#         
#         if hitsel == wx.NOT_FOUND:
#             evt.Skip()
#             return
#         
#         if pos.x < (5 + 6):
#             # Click inside the blue bar
#             self.SetSelection(hitsel)
#             self._pageListFindNext()
#             return
#         
#         evt.Skip()
# 
# 
#     def OnMiddleButtonDown(self, evt):
#         if self.GetItemCount() == 0:
#             return  # no evt.Skip()?
# 
#         pos = evt.GetPosition()
#         if pos == wx.DefaultPosition:
#             hitsel = self.GetSelection()
# 
#         hitsel = self.HitTest(pos)
# 
#         if hitsel == wx.NOT_FOUND:
#             evt.Skip()
#             return
# 
#         if pos.x < (5 + 6):
#             # Click inside the blue bar
#             self.SetSelection(hitsel)
#             self._pageListFindNext()
#             return
#         
#         info = self.itemInfo[hitsel]
# 
#         if evt.ControlDown():
#             configCode = self.mainControl.getConfig().getint("main",
#                     "mouse_middleButton_withCtrl")
#         else:
#             configCode = self.mainControl.getConfig().getint("main",
#                     "mouse_middleButton_withoutCtrl")
#                     
#         tabMode = MIDDLE_MOUSE_CONFIG_TO_TABMODE[configCode]
# 
#         presenter = self.mainControl.activatePageByUnifiedName(
#                 u"wikipage/" + info.wikiWord, tabMode)
#         
#         if presenter is None:
#             return
# 
#         if info.occPos[0] != -1:
#             presenter.getSubControl("textedit").showSelectionByCharPos(
#                     info.occPos[0], info.occPos[1])
# 
#         if configCode != 1:
#             # If not new tab opened in background -> focus editor
# 
#             # Works in fast search popup only if called twice
#             self.mainControl.getActiveEditor().SetFocus()
#             self.mainControl.getActiveEditor().SetFocus()
# 
#         
#     def OnKeyDown(self, evt):
#         if self.GetItemCount() == 0:
#             return  # no evt.Skip()?
# 
#         accP = getAccelPairFromKeyDown(evt)
#         matchesAccelPair = self.mainControl.keyBindings.matchesAccelPair
#         
#         if matchesAccelPair("ContinueSearch", accP):
#             # ContinueSearch is normally F3
#             self._pageListFindNext()
#         elif accP == (wx.ACCEL_NORMAL, wx.WXK_RETURN) or \
#                 accP == (wx.ACCEL_NORMAL, wx.WXK_NUMPAD_ENTER):
#             self.OnDClick(evt)
#         else:
#             evt.Skip()
# 
# 
#     def OnContextMenu(self, evt):
#         if self.GetItemCount() == 0:
#             return  # no evt.Skip()?
# 
#         pos = evt.GetPosition()
#         if pos == wx.DefaultPosition:
#             hitsel = self.GetSelection()
#         else:
#             hitsel = self.HitTest(self.ScreenToClient(pos))
# 
#         if hitsel == wx.NOT_FOUND:
#             evt.Skip()
#             return
# 
#         self.contextMenuSelection = hitsel
#         try:
#             menu = wx.Menu()
#             appendToMenuByMenuDesc(menu, _CONTEXT_MENU_ACTIVATE)
#             self.PopupMenu(menu)
#             menu.Destroy()
#         finally:
#             self.contextMenuSelection = -2
# 
# 
# 
#     def OnActivateThis(self, evt):
#         if self.contextMenuSelection > -1:
#             info = self.itemInfo[self.contextMenuSelection]
# 
# #             presenter = self.mainControl.activateWikiWord(info.wikiWord, 0)
#             presenter = self.mainControl.activatePageByUnifiedName(
#                     u"wikipage/" + info.wikiWord, 0)
# 
#             if presenter is None:
#                 return
# 
#             if info.occPos[0] != -1:
#                 presenter.getSubControl("textedit").showSelectionByCharPos(
#                         info.occPos[0], info.occPos[1])
#     
#             # Works in fast search popup only if called twice
#             self.mainControl.getActiveEditor().SetFocus()
#             self.mainControl.getActiveEditor().SetFocus()
# 
# 
#     def OnActivateNewTabThis(self, evt):
#         if self.contextMenuSelection > -1:
#             info = self.itemInfo[self.contextMenuSelection]
# 
# #             presenter = self.mainControl.activateWikiWord(info.wikiWord, 2)
#             presenter = self.mainControl.activatePageByUnifiedName(
#                     u"wikipage/" + info.wikiWord, 2)
# 
#             if presenter is None:
#                 return
# 
#             if info.occPos[0] != -1:
#                 presenter.getSubControl("textedit").showSelectionByCharPos(
#                         info.occPos[0], info.occPos[1])
#     
#             # Works in fast search popup only if called twice
#             self.mainControl.getActiveEditor().SetFocus()
#             self.mainControl.getActiveEditor().SetFocus()
# 
# 
#     def OnActivateNewTabBackgroundThis(self, evt):
#         if self.contextMenuSelection > -1:
#             info = self.itemInfo[self.contextMenuSelection]
# 
# #             presenter = self.mainControl.activateWikiWord(info.wikiWord, 3)
#             presenter = self.mainControl.activatePageByUnifiedName(
#                     u"wikipage/" + info.wikiWord, 3)
#             
#             if presenter is None:
#                 return
# 
#             if info.occPos[0] != -1:
#                 presenter.getSubControl("textedit").showSelectionByCharPos(
#                         info.occPos[0], info.occPos[1])













#
#
#
# class MissingGridRow:
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




class FileCleanupInitialDialog(wx.Dialog, ModalDialogMixin):
    """
    Dialog to ask for the options for the data to collect on file links
    and file storage
    """

    def __init__(self, mainControl, parent):
        wx.Dialog.__init__(self)

        self.mainControl = mainControl
        self.value = None

        res = wx.xrc.XmlResource.Get()
        res.LoadDialog(self, parent, "FileCleanupInitialDialog")

        self.ctrls = XrcControls(self)

        value = {"downwardRef": True}
        self.ctrls.cbDownwardRef.SetValue(value["downwardRef"])

        self.ctrls.btnOk.SetId(wx.ID_OK)
        self.ctrls.btnCancel.SetId(wx.ID_CANCEL)

        self.Fit()

        # Fixes focus bug under Linux
        self.SetFocus()

        self.Bind(wx.EVT_BUTTON, self.OnOk, id=wx.ID_OK)


    def GetValue(self):
        return self.value


    def OnOk(self, evt):
        self.value = {"downwardRef": self.ctrls.cbDownwardRef.GetValue()}

        self.EndModal(wx.ID_OK)




class FileCleanupDialog(wx.Dialog, ModalDialogMixin):
    """
    """

    # Because these contain localized strings, creation must be delayed
    ORPHANED_DEFAULTACTIONCHOICELIST = None

    def __init__(self, mainControl, db, parent):

        if FileCleanupDialog.ORPHANED_DEFAULTACTIONCHOICELIST is None:
            FileCleanupDialog.ORPHANED_DEFAULTACTIONCHOICELIST = [_("Keep"),
                    _("Delete"), _("Collect")]

        wx.Dialog.__init__(self)

        self.mainControl = mainControl
        self.db = db
        self.value = False

        self.modifiedSinceOpen = set() # Set of unified names of pages modified
            # since dialog was opened

        res = wx.xrc.XmlResource.Get()
        res.LoadDialog(self, parent, "FileCleanupDialog")

        self.ctrls = XrcControls(self)

        orphanedGrid = _OrphanedGrid(self.ctrls.panelOrphaned, self, self.db,
                mainControl.getWikiDocument(), mainControl.getCollator())

#         res.AttachUnknownControl("gridOrphaned", orphanedGrid, self)
        EnhancedGrid.replaceStandIn(self.ctrls.panelOrphaned,
                self.ctrls.gridOrphaned, orphanedGrid)
        
        missingGrid = _MissingGrid(self.ctrls.panelMissing, self, self.db,
                mainControl.getWikiDocument(), mainControl.getCollator())

#         res.AttachUnknownControl("gridMissing", missingGrid, self)
        EnhancedGrid.replaceStandIn(self.ctrls.panelMissing,
                self.ctrls.gridMissing, missingGrid)

        htmllbMissingLinkingPages = _MissingLinkingPagesListBox(self, self.db,
                mainControl, mainControl.getCollator(),
                GUI_ID.htmllbMissingLinkingPages)

        res.AttachUnknownControl("htmllbMissingLinkingPages",
                htmllbMissingLinkingPages, self)

        self.ctrls.btnOk.SetId(wx.ID_OK)
        self.ctrls.btnCancel.SetId(wx.ID_CANCEL)

        self.Fit()
        # If the table is too long, a resizing may become necessary
        WindowLayout.setWindowSize(self)
        WindowLayout.setWindowPos(self)

        # Fixes layout problem
        orphanedGrid.GetGrandParent().Layout()
        missingGrid.GetGrandParent().Layout()
        
        self.ctrls.nbCleanup.SetSelection(0)

        # Fixes focus bug under Linux
        self.SetFocus()

        self.Bind(wx.EVT_BUTTON, self.OnOk, id=wx.ID_OK)
        self.Bind(wx.EVT_BUTTON, self.OnTest, id=GUI_ID.btnTest)
        

        self.__sinkWikiDoc = wxKeyFunctionSink((
                ("renamed wiki page", self.onRemovedWikiPage),
                ("deleted wiki page", self.onRemovedWikiPage),
                ("updated wiki page", self.onModifiedWikiPage),
        ), self.mainControl.getWikiDocument().getMiscEvent(), self)
        
        
        

#         self.Bind(wx.EVT_TEXT, self.OnText, id=ID)
#         self.ctrls.text.Bind(wx.EVT_CHAR, self.OnCharText)
#         self.ctrls.lb.Bind(wx.EVT_CHAR, self.OnCharListBox)
#         self.Bind(wx.EVT_LISTBOX, self.OnListBox, id=ID)
#         self.Bind(wx.EVT_LISTBOX_DCLICK, self.OnOk, id=GUI_ID.lb)

    def GetValue(self):
        return self.value


    def OnOk(self, evt):
#         if not self.ctrls.gridDetails.validateInput():
#             self.ctrls.gridDetails.updateErrorColumn()
#             return
#
#         self.ctrls.gridDetails.writeGridToDb()
        self.ctrls.gridOrphaned.storeGridToSql()
        self.db.calcActionAndErrorsDuringDialog(
                self.ctrls.chOrphanedDefaultAction.GetSelection() + 1,
                self.ctrls.cbOrphanedDownwardRef.GetValue())

        self.db.getSqlDb().commit()

        absPaths = self.db.getSqlDb().execSqlQuerySingleColumn("select fullpath "
                "from fStorItems where calcaction == 3 limit 1")

        collectorPageName = self.ctrls.tfOrphanedCollectorPage.GetValue()

        if len(absPaths) > 0:
            # Some files are designated to be collected on collector page
            langHelper = wx.GetApp().createWikiLanguageHelper(
                    self.mainControl.getWikiDocument()\
                    .getWikiDefaultWikiLanguage())

            if langHelper.checkForInvalidWikiWord(collectorPageName,
                    self.mainControl.getWikiDocument()) is not None:
                # There are paths to collect but the name of the collector
                # page isn't a valid wiki word, so update UI and back to user
                self.OnTest(None)
                return

        self.value = True

        self.db.runAfterDialog(collectorPageName)

        if self is self.mainControl.nonModalFileCleanupDlg:
            self.mainControl.nonModalFileCleanupDlg = None

        self.__sinkWikiDoc.disconnect()

        if self.IsModal():
            self.EndModal(wx.ID_OK)
        else:
            self.Destroy()



    def OnClose(self, evt):
        self.value = None

        if self is self.mainControl.nonModalFileCleanupDlg:
            self.mainControl.nonModalFileCleanupDlg = None

        self.__sinkWikiDoc.disconnect()

        if self.IsModal():
            self.EndModal(wx.ID_CANCEL)
        else:
            self.Destroy()


    def OnTest(self, evt):
        self.ctrls.gridOrphaned.storeGridToSql()
        self.db.calcActionAndErrorsDuringDialog(
                self.ctrls.chOrphanedDefaultAction.GetSelection() + 1,
                self.ctrls.cbOrphanedDownwardRef.GetValue())

        self.db.getSqlDb().commit()

        absPaths = self.db.getSqlDb().execSqlQuerySingleColumn("select fullpath "
                "from fStorItems where calcaction == 3 limit 1")

        self.ctrls.tfOrphanedCollectorPage.SetBackgroundColour(wx.WHITE)

        collectorPageName = self.ctrls.tfOrphanedCollectorPage.GetValue()

        if len(absPaths) > 0:
            # Some files are designated to be collected on collector page
            langHelper = wx.GetApp().createWikiLanguageHelper(
                    self.mainControl.getWikiDocument()\
                    .getWikiDefaultWikiLanguage())

            if langHelper.checkForInvalidWikiWord(collectorPageName,
                    self.mainControl.getWikiDocument()) is not None:
                self.ctrls.tfOrphanedCollectorPage.SetBackgroundColour(wx.RED)

        self.ctrls.tfOrphanedCollectorPage.Refresh()

        self.ctrls.gridOrphaned.updateGridBySql(
                self.ctrls.chOrphanedDefaultAction.GetSelection() + 1)

        return


    def onModifiedWikiPage(self, miscevt):
        self.db.updateWikiPage(miscevt.get("wikiPage"))
        self.db.deleteUninteresting()
        self.db.getSqlDb().commit()

#         if miscevt.get("wikiPage").getUnifiedPageName() in self.modifiedSinceOpen:
#             return
# 
#         self.modifiedSinceOpen.add(miscevt.get("wikiPage").getUnifiedPageName())
        self.ctrls.gridMissing.updateGridBySql()
        self.ctrls.htmllbMissingLinkingPages.update()


    def onRemovedWikiPage(self, miscevt):
        if miscevt.get("wikiPage").getUnifiedPageName() in self.modifiedSinceOpen:
            return

        self.modifiedSinceOpen.add(miscevt.get("wikiPage").getUnifiedPageName())
        self.ctrls.htmllbMissingLinkingPages.update()


    def isModifiedPage(self, unifPageName):
        return unifPageName in self.modifiedSinceOpen

    def updateMissingLinkingPagesListBoxByRefedItemId(self, refedItemId):
        self.ctrls.htmllbMissingLinkingPages.updateByRefedItemId(refedItemId)

    def runFirstInMissingLinkingPagesListBox(self):
        """
        Simulate double click on first item in MissingLinkingPagesListBox
        Called after double click on a cell in missing items table
        """
        self.ctrls.htmllbMissingLinkingPages.activateSelection(0)




def runFileCleanup(mainControl, parent, progresshandler):
    if mainControl.nonModalFileCleanupDlg:
        # Dialog already open
        mainControl.nonModalFileCleanupDlg.SetFocus()
        return

    options = FileCleanupInitialDialog.runModal(mainControl, parent)
    if options is None:
        return

    db = InfoDatabase(mainControl)
    db.buildDatabaseBeforeDialog(progresshandler, options)

    dlg = FileCleanupDialog(mainControl, db, parent)
    mainControl.nonModalFileCleanupDlg = dlg

#     parent.Enable(False)
#     dlg.Enable(True)
    dlg.Show()

#     FileCleanupDialog.runModal(mainControl, db, parent)

