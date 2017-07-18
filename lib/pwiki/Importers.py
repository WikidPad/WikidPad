# from Enum import Enumeration
import sys, os, re, traceback, time, sqlite3
from codecs import BOM_UTF8
from os.path import join, exists, splitext
from calendar import timegm
from io import BytesIO, TextIOWrapper
from . import urllib_red as urllib

import wx, wx.xrc

from .wxHelper import XrcControls


import Consts
from .StringOps import *
from .StringOps import MBCS_ENCODING

from .ConnectWrapPysqlite import ConnectWrapSyncCommit

from .WikiExceptions import *

from . import DocPages

from .MptImporterGui import MultiPageTextImporterDialog

from .timeView import Versioning



class MultiPageTextImporter:
    def __init__(self, mainControl):
        """
        mainControl -- Currently PersonalWikiFrame object
        """
        self.mainControl = mainControl


    def getImportTypes(self, guiparent):
        """
        Return sequence of tuples with the description of import types provided
        by this object. A tuple has the form (<imp. type>,
            <human readable description>, <panel for add. options or None>)
        If panels for additional options must be created, they should use
        guiparent as parent
        """
        if guiparent:
            res = wx.xrc.XmlResource.Get()
            mptPanel = res.LoadPanel(guiparent, "ImportSubMultipageText")
#             ctrls = XrcControls(htmlPanel)
#             config = self.mainControl.getConfig()
# 
#             ctrls.cbPicsAsLinks.SetValue(config.getboolean("main",
#                     "html_export_pics_as_links"))
#             ctrls.chTableOfContents.SetSelection(config.getint("main",
#                     "export_table_of_contents"))
#             ctrls.tfHtmlTocTitle.SetValue(config.get("main",
#                     "html_toc_title"))

        else:
            mptPanel = None

        return (
                ("multipage_text", _("Multipage text"), mptPanel),
                )


    def getImportSourceWildcards(self, importType):
        """
        If an export type is intended to go to a file, this function
        returns a (possibly empty) sequence of tuples
        (wildcard description, wildcard filepattern).
        
        If an export type goes to a directory, None is returned
        """
        if importType == "multipage_text":
            return ((_("Multipage files (*.mpt)"), "*.mpt"),
                    (_("Text file (*.txt)"), "*.txt")) 

        return None


    def getAddOptVersion(self):
        """
        Returns the version of the additional options information returned
        by getAddOpt(). If the return value is -1, the version info can't
        be stored between application sessions.
        
        Otherwise, the addopt information can be stored between sessions
        and can later handled back to the doImport method of the object
        without previously showing the import dialog.
        """
        return 0


    def getAddOpt(self, addoptpanel):
        """
        Reads additional options from panel addoptpanel.
        If getAddOptVersion() > -1, the return value must be a sequence
        of simple string, unicode and/or numeric objects. Otherwise, any object
        can be returned (normally the addoptpanel itself)
        """
        if addoptpanel is None:
            return (0,)
        else:
            ctrls = XrcControls(addoptpanel)
            showImportTableAlways = boolToInt(ctrls.cbShowImportTableAlways.GetValue())

            return (showImportTableAlways,)


    def _collectContent(self):
        """
        Collect lines from current position of importFile up to separator
        or file end collect all lines and return them as list of lines.
        """
        content = []                    
        while True:
            # Read lines of wikiword
            line = self.importFile.readline()
            if line == "":
                # The last page in mpt file without separator
                # ends as the real wiki page
#                 content = u"".join(content)
                break
            
            if line == self.separator:
                if len(content) > 0:
                    # Iff last line of mpt page is empty, the original
                    # page ended with a newline, so remove last
                    # character (=newline)

                    content[-1] = content[-1][:-1]
#                     content = u"".join(content)
                break

            content.append(line)
            
        return "".join(content)


    def _skipContent(self):
        """
        Skip content until reaching next separator or end of file
        """
        while True:
            # Read lines of wikiword
            line = self.importFile.readline()
            if line == "":
                # The last page in mpt file without separator
                # ends as the real wiki page
                break
            
            if line == self.separator:
                break



    def doImport(self, wikiDocument, importType, importSrc,
            compatFilenames, addOpt, importData=None):
        """
        Run import operation.
        
        wikiDocument -- WikiDocument object
        importType -- string tag to identify how to import
        importSrc -- Path to source directory or file to import from
        compatFilenames -- Should the filenames be decoded from the lowest
                           level compatible?
        addOpt -- additional options returned by getAddOpt()
        importData -- if not None contains data to import as bytestring.
                importSrc is ignored in this case. Needed for trashcan.
        returns True if import was done (needed for trashcan)
        """
        if importData is not None:
            self.rawImportFile = BytesIO(importData)  # TODO bytes or string???
        else:
            try:
                self.rawImportFile = open(pathEnc(importSrc), "rb")
            except IOError:
                raise ImportException(_("Opening import file failed"))

        self.wikiDocument = wikiDocument
        self.tempDb = None
        
        showImportTableAlways = addOpt[0]
#         wikiData = self.wikiDocument.getWikiData()

        
        # TODO Do not stop on each import error, instead create error list and
        #   continue

        try:
            try:
                # Wrap input file to convert format
                bom = self.rawImportFile.read(len(BOM_UTF8))
                if bom != BOM_UTF8:
                    self.rawImportFile.seek(0)
                    self.importFile = TextIOWrapper(self.rawImportFile,
                            MBCS_ENCODING, "replace")
                else:
                    self.importFile = TextIOWrapper(self.rawImportFile,
                            "utf-8", "replace")

                line = self.importFile.readline()
                if line.startswith("#!"):
                    # Skip initial line with #! to allow execution as shell script
                    line = self.importFile.readline()

                if not line.startswith("Multipage text format "):
                    raise ImportException(
                            _("Bad file format, header not detected"))

                # Following in the format identifier line is a version number
                # of the file format
                self.formatVer = int(line[22:-1])
                
                if self.formatVer > 1:
                    raise ImportException(
                            _("File format number %i is not supported") %
                            self.formatVer)

                # Next is the separator line
                line = self.importFile.readline()
                if not line.startswith("Separator: "):
                    raise ImportException(
                            _("Bad file format, header not detected"))

                self.separator = line[11:]
                
                startPos = self.importFile.tell()

                if self.formatVer == 0:
                    self._doImportVer0()
                elif self.formatVer == 1:
                    # Create temporary database. It is mainly filled during
                    # pass 1 to check for validity and other things before
                    # actual importing in pass 2
                    
                    # TODO Respect settings for general temp location!!!
                    self.tempDb = ConnectWrapSyncCommit(sqlite3.connect(""))
                    try:            # TODO: Remove column "collisionWithPresent", seems to be unused
                        self.tempDb.execSql("create table entries("
                                "unifName text primary key not null, "   # Unified name in import file
                                "seen integer not null default 0, "   # data really exists
                                "dontImport integer not null default 0, "   # don't import this (set between pass 1 and 2)
                                "missingDep integer not null default 0, "  # missing dependency(ies)
                                "importVersionData integer not null default 0, "  # versioning data present
    #                             "neededBy text default '',"
    #                             "versionContentDifferencing text default '',"

                                "collisionWithPresent text not null default '',"  # Unif. name of present entry which collides with imported one (if any)
                                "renameImportTo text not null default ''," # Rename imported element to (if at all)
                                "renamePresentTo text not null default ''"  # Rename present element in  database to (if at all)
                                ");"
                                )
    
                        # Dependencies. If unifName isn't imported (or faulty), neededBy shouldn't be either
                        self.tempDb.execSql("create table depgraph("
                                "unifName text not null default '',"
                                "neededBy text not null default '',"
                                "constraint depgraphpk primary key (unifName, neededBy)"
                                ");"
                                )

                        # Recursive processing is not supported for this table
                        self.tempDb.execSql("create table renamegraph("
                                "unifName text not null default '',"
                                "dependent text not null default '',"
                                "constraint renamegraphpk primary key (unifName, dependent),"
                                "constraint renamegraphsingledep unique (dependent)"
                                ");"
                                )


                        # Collect some initial information into the temporary database
                        self._doImportVer1Pass1()
    
                        # Draw some logical conclusions on the temp db
                        self._markMissingDependencies()
                        self._markHasVersionData()
                        self._markCollision()

                        # Now ask user if necessary
                        if showImportTableAlways or self._isUserNeeded():
                            if not self._doUserDecision():
                                # Canceled by user
                                return False

                        # Further logical processing after possible user editing
                        self._markNonImportedVersionsData()
                        self._markNonImportedDependencies()
                        self._propagateRenames()
                        # TODO: Remove version data without ver. overview or main data

                        # Back to start of import file and import according to settings 
                        # in temp db
                        self.importFile.seek(startPos)
                        self._doImportVer1Pass2()
                        
                        return True
                    finally:
                        self.tempDb.close()
                        self.tempDb = None

            except ImportException:
                raise
            except Exception as e:
                traceback.print_exc()
                raise ImportException(str(e))

        finally:
            self.importFile.close()


    def _markMissingDependencies(self):
        """
        If a datablock wasn't present, all dependent data blocks are marked as
        not to import
        """
        while True:
            self.tempDb.execSql("""
                update entries set missingDep=1, dontImport=1 where (not missingDep) and 
                    unifName in (select depgraph.neededBy from depgraph inner join 
                    entries on depgraph.unifName = entries.unifName where
                    (not entries.seen) or entries.missingDep);
                """)

            if self.tempDb.rowcount == 0:
                break


    def _markHasVersionData(self):
        """
        Mark if version data present
        """
        self.tempDb.execSql("""
            update entries set importVersionData=1 where (not importVersionData) and 
                unifName in (select substr(unifName, 21) from entries where 
                unifName glob 'versioning/overview/*' and not dontImport)
            """)  # TODO Take missing deps into account here?

#             self.tempDb.execSql("insert or replace into entries(unifName, importVersionData) "
#                 "values (?, 1)", (depunifName,))


    def _markCollision(self):
        """
        Mark collisions between existing and data blocks and such to import
        """
        # First find collisions with wiki words
        for wikipageUnifName in self.tempDb.execSqlQuerySingleColumn(
                "select unifName from entries where unifName glob 'wikipage/*' "
                "and not dontImport"):
            wpName = wikipageUnifName[9:]
        
            if not self.wikiDocument.isDefinedWikiPageName(wpName):
                continue

            self.tempDb.execSql("update entries set collisionWithPresent = ? "
                    "where unifName = ?",
                    (wikipageUnifName, wikipageUnifName))
#                     (u"wikipage/" + collisionWithPresent, wikipageUnifName))

        # Then find other collisions (saved searches etc.)
        for unifName in self.tempDb.execSqlQuerySingleColumn(
                "select unifName from entries where (unifName glob 'savedsearch/*' "
                "or unifName glob 'savedpagesearch/*') and not dontImport"):
            if self.wikiDocument.hasDataBlock(unifName):
                self.tempDb.execSql("update entries set collisionWithPresent = ? "
                        "where unifName = ?", (unifName, unifName))


    def _markNonImportedVersionsData(self):
        """
        After user dialog: If importVersionData is false for some entries
        the depending version data shouldn't be imported.
        Only the versioning overview is marked for not importing. The next step
        propagates this to the other data blocks
        """
        self.tempDb.execSql("""
                update entries set dontImport = 1 where 
                unifName in (select 'versioning/overview/' || unifName from 
                entries where not importVersionData)
                """)

#         # Vice versa the importVersionData column must be updated if
#         self.tempDb.execSql("""
#                 update entries set importVersionData = 0 where importVersionData 
#                 and ('versioning/overview/' || unifName) in (select unifName 
#                 from entries where dontImport)
#                 """)
       


    def _markNonImportedDependencies(self):
        """
        After user dialog: If some data blocks where chosen not to import
        mark all dependent blocks to not import also (especially version data)
        """
        while True:
            self.tempDb.execSql("""
                    update entries set dontImport=1 where (not dontImport) and 
                    unifName in (select depgraph.neededBy from depgraph inner join 
                    entries on depgraph.unifName = entries.unifName where
                    entries.dontImport);
                """)

            if self.tempDb.rowcount == 0:
                break


        

    def _propagateRenames(self):
        """
        Write rename commands for imported items to all parts to import
        if some parts need renaming. Renaming of present items is not propagated.
        """
        for unifName, renImportTo in self.tempDb.execSqlQuery(
                "select unifName, renameImportTo from entries "
                "where renameImportTo != '' and not dontImport"):
            for depUnifName in self.tempDb.execSqlQuerySingleColumn(
                    "select dependent from renamegraph where unifName = ? and "
                    "dependent in (select unifName from entries where "
                    "not dontImport)", (unifName,)):
                if depUnifName.endswith(unifName):
                    newName = depUnifName[:-len(unifName)] + renImportTo

                    self.tempDb.execSql("""
                        update entries set renameImportTo=? where unifName = ?
                        """, (newName, depUnifName))


    def _doUserDecision(self):
        """
        Called to present GUI to user for deciding what to do.
        This method is overwritten for trashcan GUI.
        Returns False if user canceled operation
        """
        return MultiPageTextImporterDialog.runModal(
                self.mainControl, self.tempDb,
                self.mainControl)


    def _isUserNeeded(self):
        """
        Decide if a dialog must be shown to ask user how to proceed.
        Under some circumstances the dialog may be shown regardless of the result.
        """
        if self.tempDb.execSqlQuerySingleItem("select missingDep from entries "
                "where missingDep limit 1", default=False):
            # Missing dependency
            return True
        
        if len(self.tempDb.execSqlQuerySingleItem("select collisionWithPresent "
                "from entries where collisionWithPresent != '' limit 1",
                default="")) > 0:
            # Name collision
            return True

        # No problems found
        return False



    def _doImportVer0(self):
        """
        Import wikiwords if format version is 0.
        """
        langHelper = wx.GetApp().createWikiLanguageHelper(
                self.wikiDocument.getWikiDefaultWikiLanguage())

        while True:
            # Read next wikiword
            line = self.importFile.readline()
            if line == "":
                break

            wikiWord = line[:-1]
            errMsg = langHelper.checkForInvalidWikiWord(wikiWord,
                    self.wikiDocument)
            if errMsg:
                raise ImportException(_("Bad wiki word: %s, %s") %
                        (wikiWord, errMsg))

            content = self._collectContent()
            page = self.wikiDocument.getWikiPageNoError(wikiWord)

            page.replaceLiveText(content)


    def _doImportVer1Pass1(self):
        while True:
            tag = self.importFile.readline()
            if tag == "":
                # End of file
                break
            tag = tag[:-1]
            if tag.startswith("funcpage/"):
                self._skipContent()
            elif tag.startswith("savedsearch/"):
                self._skipContent()
            elif tag.startswith("savedpagesearch/"):
                self._skipContent()
            elif tag.startswith("wikipage/"):
                self._skipContent()
            elif tag.startswith("versioning/overview/"):
                self._doImportItemVersioningOverviewVer1Pass1(tag[20:])
            elif tag.startswith("versioning/packet/versionNo/"):
                self._skipContent()
            else:
                # Unknown tag -> Ignore until separator
                self._skipContent()
                continue

            self.tempDb.execSql("insert or replace into entries(unifName, seen) "
                    "values (?, 1)", (tag,))


    def _readHintedDatablockVer1(self):
        """
        Reads datablock and preprocesses encoding if necessary.
        Returns either (hintStrings, content) or (None, None) if either
        an unknown important hint was found or if encoding had an error.

        hintStrings is a list of hints (as unistrings) which were
        not processed by the function (therefore encoding hint is removed).
        content can be a bytestring or a unistring.
        
        If (None, None) is returned, the remaining content of the entry
        was skipped already by the function.
        """
        hintLine = self.importFile.readline()[:-1]
        hintStrings = hintLine.split("  ")
        
        resultHintStrings = []

        # Set default
        useB64 = False

        # Process hints
        for hint in hintStrings:
            if hint.startswith("important/encoding/"):
                if hint[19:] == "text":
                    useB64 = False
                elif hint[19:] == "base64":
                    useB64 = True
                else:
                    # Unknown encoding: don't read further
                    self._skipContent()
                    return None, None
            elif hint.startswith("important/"):
                # There is something important we do not understand
                self._skipContent()
                return None, None
            else:
                resultHintStrings.append(hint)

        content = self._collectContent()

        if useB64:
            try:
                content = base64BlockDecode(content)
            except TypeError:
                # base64 decoding failed
                self._skipContent()
                return None, None
        
        return (resultHintStrings, content)



    def _doImportItemVersioningOverviewVer1Pass1(self, subtag):
        hintStrings, content = self._readHintedDatablockVer1()
        if content is None:
            return

        # Always encode to UTF-8 no matter what the import file encoding is
        content = content.encode("utf-8")

        try:
            ovw = Versioning.VersionOverview(self.wikiDocument,
                    unifiedBasePageName=subtag)
            
            ovw.readOverviewFromBytes(content)
            
            ovwUnifName = ovw.getUnifiedName()
            
            self.tempDb.execSql("insert or replace into depgraph(unifName, neededBy) "
                "values (?, ?)", (subtag, ovwUnifName))

            self.tempDb.execSql("insert or replace into renamegraph(unifName, dependent) "
                "values (?, ?)", (subtag, ovwUnifName))

            for depUnifName in ovw.getDependentDataBlocks(omitSelf=True):
                # Mutual dependency between version overview and each version packet
                self.tempDb.execSql("insert or replace into depgraph(unifName, neededBy) "
                    "values (?, ?)", (depUnifName, ovwUnifName))
                self.tempDb.execSql("insert or replace into depgraph(unifName, neededBy) "
                    "values (?, ?)", (ovwUnifName, depUnifName))
                    
                self.tempDb.execSql("insert or replace into renamegraph(unifName, dependent) "
                    "values (?, ?)", (subtag, depUnifName))

#                 self.tempDb.execSql("insert or replace into entries(unifName, needed) "
#                     "values (?, 1)", (depUnifName,))

        except VersioningException:
            return


    def _doImportVer1Pass2(self):
        wikiDoc = self.wikiDocument
        
        # We have to rename present items
        # First wikipages because this automatically renames depending version data
        for pageFrom, pageTo in self.tempDb.execSqlQuery(
                """
                select substr(unifName, 10), substr(renamePresentTo, 10) 
                from entries where unifName glob 'wikipage/*' and 
                renamePresentTo glob 'wikipage/*'
                """):
            if wikiDoc.isDefinedWikiPageName(pageFrom):
                wikiDoc.renameWikiWords({pageFrom: pageTo}, Consts.ModifyText.off)
                        # TODO How to handle rename of home page?

        # Then remaining data blocks
        for oldUnifName, newUnifName in self.tempDb.execSqlQuery(
                """
                select unifName, renamePresentTo
                from entries where unifName not glob 'wikipage/*' and 
                renamePresentTo != ''
                """):
            wikiDoc.renameDataBlock(oldUnifName, newUnifName)

        # For wiki pages with versions to import, existing versions must be
        # deleted

        for wikiWord in self.tempDb.execSqlQuerySingleColumn(
                """
                select substr(unifName, 10)
                from entries where unifName glob 'wikipage/*' and 
                renameImportTo == '' and not dontImport and importVersionData
                union
                select substr(renameImportTo, 10)
                from entries where unifName glob 'wikipage/*' and 
                renameImportTo glob 'wikipage/*' and not dontImport and 
                importVersionData
                """):
            if not wikiDoc.isDefinedWikiPageName(wikiWord):
                continue

            page = wikiDoc.getWikiPage(wikiWord)
            versionOverview = page.getExistingVersionOverview()
            if versionOverview is not None:
                versionOverview.delete()


        while True:
            tag = self.importFile.readline()
            if tag == "":
                # End of file
                break
            tag = tag[:-1]  # Remove line end
            
            try:
                dontImport, renameImportTo = \
                        self.tempDb.execSqlQuery(
                        "select dontImport, renameImportTo from "
                        "entries where unifName = ?", (tag,))[0]
            except IndexError:
                # Maybe dangerous
                traceback.print_exc()
                self._skipContent()
                continue

            if dontImport:
                self._skipContent()
                continue
            
            if renameImportTo == "":
                renameImportTo = tag

            if tag.startswith("wikipage/"):
                self._importItemWikiPageVer1Pass2(renameImportTo[9:])
            elif tag.startswith("funcpage/"):
                self._importItemFuncPageVer1Pass2(tag[9:])
            elif tag.startswith("savedsearch/"):
                self._importB64DatablockVer1Pass2(renameImportTo)
            elif tag.startswith("savedpagesearch/"):
                self._importHintedDatablockVer1Pass2(renameImportTo)
            elif tag.startswith("versioning/"):
                self._importHintedDatablockVer1Pass2(renameImportTo)
            else:
                # Unknown tag -> Ignore until separator
                self._skipContent()

        
        for wikiWord in self.tempDb.execSqlQuerySingleColumn(
                """
                select substr(unifName, 10)
                from entries where unifName glob 'wikipage/*' and 
                renamePresentTo == '' and importVersionData
                union
                select substr(renamePresentTo, 10)
                from entries where unifName glob 'wikipage/*' and 
                renamePresentTo glob 'wikipage/*' and importVersionData
                """):
            if not wikiDoc.isDefinedWikiPageName(wikiWord):
                continue

            page = wikiDoc.getWikiPage(wikiWord)
            versionOverview = page.getExistingVersionOverview()
            if versionOverview is not None:
                versionOverview.readOverview()





    def _importItemWikiPageVer1Pass2(self, wikiWord):
        timeStampLine = self.importFile.readline()[:-1]
        timeStrings = timeStampLine.split("  ")
        if len(timeStrings) < 3:
            traceback.print_exc()
            self._skipContent()
            return  # TODO Report error

        timeStrings = timeStrings[:3]

        try:
            timeStrings = [str(ts) for ts in timeStrings]
        except UnicodeEncodeError:
            traceback.print_exc()
            self._skipContent()
            return  # TODO Report error

        try:
            timeStamps = [timegm(time.strptime(ts, "%Y-%m-%d/%H:%M:%S"))
                    for ts in timeStrings]

        except (ValueError, OverflowError):
            traceback.print_exc()
            self._skipContent()
            return  # TODO Report error

        content = self._collectContent()
        page = self.wikiDocument.getWikiPageNoError(wikiWord)

        # TODO How to handle versions here?
        page.replaceLiveText(content)
        if page.getTxtEditor() is not None:
            page.writeToDatabase()

        page.setTimestamps(timeStamps)



    def _importItemFuncPageVer1Pass2(self, subtag):
        # The subtag is functional page tag
        try:
            # subtag is unicode but func tags are bytestrings
            subtag = str(subtag)
        except UnicodeEncodeError:
            self._skipContent()
            return

        content = self._collectContent()
        try:
            page = self.wikiDocument.getFuncPage(subtag)
            page.replaceLiveText(content)
        except BadFuncPageTagException:
            # This function tag is bad or unknown -> ignore
            return  # TODO Report error


    def _importB64DatablockVer1Pass2(self, unifName):
        # Content is base64 encoded
        b64Content = self._collectContent()
        
        try:
            datablock = base64BlockDecode(b64Content)
            self.wikiDocument.getWikiData().storeDataBlock(unifName, datablock,
                    storeHint=Consts.DATABLOCK_STOREHINT_INTERN)

        except TypeError:
            # base64 decoding failed
            return  # TODO Report error


    def _importTextDatablockVer1Pass2(self, unifName):
        content = self._collectContent()
        
        try:
            self.wikiDocument.getWikiData().storeDataBlock(unifName, content,
                    storeHint=Consts.DATABLOCK_STOREHINT_INTERN)

        except TypeError:
            return  # TODO Report error


    def _importHintedDatablockVer1Pass2(self, unifName):
        """
        A hinted datablock starts with an extra line defining encoding
        (text or B64) and storage hint. It was introduced later therefore
        only versioning packets use this while saved searches don't.
        """
        hintStrings, content = self._readHintedDatablockVer1()
        if hintStrings is None:
            return
        
        # Set defaults
        storeHint = Consts.DATABLOCK_STOREHINT_INTERN

        # Process hints
        for hint in hintStrings:
            if hint.startswith("storeHint/"):
                if hint[10:] == "extern":
                    storeHint = Consts.DATABLOCK_STOREHINT_EXTERN
                elif hint[10:] == "intern":
                    storeHint = Consts.DATABLOCK_STOREHINT_INTERN
                # No else. It is not vital to get the right storage hint

        try:
            if isinstance(content, str):
                content = BOM_UTF8 + content.encode("utf-8")

            self.wikiDocument.getWikiData().storeDataBlock(unifName, content,
                    storeHint=storeHint)

        except TypeError:
            traceback.print_exc()
            return  # TODO Report error




def describeImporters(mainControl):
    return (MultiPageTextImporter(mainControl),)

