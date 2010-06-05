# from Enum import Enumeration
import sys, os, string, re, traceback, time, sqlite3
from os.path import join, exists, splitext
from calendar import timegm
import urllib_red as urllib

# import wx

import Consts
from StringOps import *

from ConnectWrapPysqlite import ConnectWrapSyncCommit

from WikiExceptions import *

import DocPages

# from MptImporterGui import MultiPageTextImporterDialog

from timeView import Versioning



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
        return (
                (u"multipage_text", _(u"Multipage text"), None),
                )


    def getImportSourceWildcards(self, importType):
        """
        If an export type is intended to go to a file, this function
        returns a (possibly empty) sequence of tuples
        (wildcard description, wildcard filepattern).
        
        If an export type goes to a directory, None is returned
        """
        if importType == u"multipage_text":
            return ((_(u"Multipage files (*.mpt)"), "*.mpt"),
                    (_(u"Text file (*.txt)"), "*.txt")) 

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
        return ()


    def _collectContent(self):
        """
        Collect lines from current position of importFile up to separator
        or file end collect all lines and return them as list of lines.
        """
        content = []                    
        while True:
            # Read lines of wikiword
            line = self.importFile.readline()
            if line == u"":
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
            
        return u"".join(content)


    def _skipContent(self):
        """
        Skip content until reaching next separator or end of file
        """
        while True:
            # Read lines of wikiword
            line = self.importFile.readline()
            if line == u"":
                # The last page in mpt file without separator
                # ends as the real wiki page
                break
            
            if line == self.separator:
                break



    def doImport(self, wikiDocument, importType, importSrc,
            compatFilenames, addOpt):
        """
        Run import operation.
        
        wikiDocument -- WikiDataManager object
        importType -- string tag to identify how to import
        importDest -- Path to source directory or file to import from
        compatFilenames -- Should the filenames be decoded from the lowest
                           level compatible?
        addOpt -- additional options returned by getAddOpt()
        """
        try:
            self.rawImportFile = open(pathEnc(importSrc), "rU")
        except IOError:
            raise ImportException(_(u"Opening import file failed"))
            
        self.wikiDocument = wikiDocument
        self.tempDb = None
#         wikiData = self.wikiDocument.getWikiData()

        
        # TODO Do not stop on each import error, instead create error list and
        #   continue

        try:
            try:
                # Wrap input file to convert format
                bom = self.rawImportFile.read(len(BOM_UTF8))
                if bom != BOM_UTF8:
                    self.rawImportFile.seek(0)
                    decodingReader = mbcsReader
                    decode = mbcsDec
                else:
                    decodingReader = utf8Reader
                    decode = utf8Dec

                line = decode(self.rawImportFile.readline())[0]
                if line.startswith("#!"):
                    # Skip initial line with #! to allow execution as shell script
                    line = decode(self.rawImportFile.readline())[0]

                if not line.startswith("Multipage text format "):
                    raise ImportException(
                            _(u"Bad file format, header not detected"))

                # Following in the format identifier line is a version number
                # of the file format
                self.formatVer = int(line[22:-1])
                
                if self.formatVer > 1:
                    raise ImportException(
                            _(u"File format number %i is not supported") %
                            self.formatVer)

                # Next is the separator line
                line = decode(self.rawImportFile.readline())[0]
                if not line.startswith("Separator: "):
                    raise ImportException(
                            _(u"Bad file format, header not detected"))

                self.separator = line[11:]
                
                if self.formatVer == 0:
                    self._doImportVer0()
                elif self.formatVer == 1:
                    startPos = self.rawImportFile.tell()
                    # Create temporary database. It is mainly filled during
                    # pass 1 to check for validity and other things before
                    # actual importing in pass 2
                    
                    # TODO Respect settings for general temp location!!!
                    self.tempDb = ConnectWrapSyncCommit(sqlite3.connect(""))
                    try:
                        self.tempDb.execSql("create table entries("
                                "unifName text primary key not null, "   # Unified name in import file
                                "seen integer not null default 0, "   # data really exists
                                "dontImport integer not null default 0, "   # don't import this (set between pass 1 and 2)
                                "missingDep integer not null default 0, "  # missing dependency(ies)
                                "hasVersionData integer not null default 0, "  # versioning data present
    #                             "neededBy text default '',"
    #                             "versionContentDifferencing text default '',"
                                "collisionWithPresent text not null default '',"  # Unif. name of present entry which collides with imported one (if any)
                                "renameImportTo text not null default ''," # Rename imported element to (if at all)
                                "renamePresentTo text not null default ''"  # Rename present element in  database to (if at all)
                                ");"
                                )
    
                        self.tempDb.execSql("create table depgraph("
                                "unifName text not null default '',"
                                "neededBy text not null default '',"
                                "constraint depgraphpk primary key (unifName, neededBy)"
                                ");"
                                )
    
    
                        self.importFile = decodingReader(self.rawImportFile, "replace")
                        
                        # Collect some initial information into the temporary database
                        self._doImportVer1Pass1()
    
                        # Draw some logical conclusions on the temp db
                        self._markMissingDependencies()
                        self._markHasVersionData()
                        self._markCollision()
                        
                        
                        # TODO Make work
#                         if self._isUserNeeded():
#                             if not MultiPageTextImporterDialog.runModal(
#                                     self.mainControl, self.tempDb,
#                                     self.mainControl):
#                                 # Canceled by user
#                                 return

                        # Back to start of import file and import according to settings 
                        # in temp db
                        self.rawImportFile.seek(startPos)
                        self.importFile = decodingReader(self.rawImportFile, "replace")
                        self._doImportVer1Pass2()

                    finally:
                        self.tempDb.close()
                        self.tempDb = None

            except ImportException:
                raise
            except Exception, e:
                traceback.print_exc()
                raise ImportException(unicode(e))

        finally:
            self.rawImportFile.close()


    def _markMissingDependencies(self):
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
        self.tempDb.execSql("""
            update entries set hasVersionData=1 where (not hasVersionData) and 
                unifName in (select substr(unifName, 21) from entries where 
                unifName glob 'versioning/overview/*' and not dontImport)
            """)  # TODO Take missing deps into account here?

#             self.tempDb.execSql("insert or replace into entries(unifName, hasVersionData) "
#                 "values (?, 1)", (depunifName,))


    def _markCollision(self):
        # First find collisions with wiki words
        for wikipageUnifName in self.tempDb.execSqlQuerySingleColumn(
                "select unifName from entries where unifName glob 'wikipage/*' "
                "and not dontImport"):
            wpName = wikipageUnifName[9:]
        
            collisionWithPresent = self.wikiDocument.getUnAliasedWikiWord(wpName)
            if collisionWithPresent is None:
                continue
            
            self.tempDb.execSql("update entries set collisionWithPresent = ? "
                    "where unifName = ?",
                    (u"wikipage/" + collisionWithPresent, wikipageUnifName))

        # Then find other collisions (saved searches etc.)
        for unifName in self.tempDb.execSqlQuerySingleColumn(
                "select unifName from entries where unifName glob 'savedsearch/*' "
                "and not dontImport"):
            if self.wikiDocument.hasDataBlock(unifName):
                self.tempDb.execSql("update entries set collisionWithPresent = ? "
                        "where unifName = ?", (unifName, unifName))


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
                default=u"")) > 0:
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
            if line == u"":
                break

            wikiWord = line[:-1]
            errMsg = langHelper.checkForInvalidWikiWord(wikiWord,
                    self.wikiDocument)
            if errMsg:
                raise ImportException(_(u"Bad wiki word: %s, %s") %
                        (wikiWord, errMsg))

            content = self._collectContent()
            page = self.wikiDocument.getWikiPageNoError(wikiWord)

            page.replaceLiveText(content)


    def _doImportVer1Pass1(self):
        while True:
            tag = self.importFile.readline()
            if tag == u"":
                # End of file
                break
            tag = tag[:-1]
            if tag.startswith(u"funcpage/"):
                self._skipContent()
            elif tag.startswith(u"savedsearch/"):
                self._skipContent()
            elif tag.startswith(u"wikipage/"):
                self._skipContent()
            elif tag.startswith(u"versioning/overview/"):
                self._doImportItemVersioningOverviewVer1Pass1(tag[20:])
            else:
                # Unknown tag -> Ignore until separator
                self._skipContent()
                continue
            
            self.tempDb.execSql("insert or replace into entries(unifName, seen) "
                    "values (?, 1)", (tag,))


    def _doImportVer1Pass2(self):
        while True:
            tag = self.importFile.readline()
            if tag == u"":
                # End of file
                break
            tag = tag[:-1]
            if tag.startswith(u"funcpage/"):
                self.importItemFuncPageVer1Pass2(tag[9:])
            elif tag.startswith(u"savedsearch/"):
                self.importItemSavedSearchVer1Pass2(tag)
            elif tag.startswith(u"wikipage/"):
                self.importItemWikiPageVer1Pass2(tag[9:])
            else:
                # Unknown tag -> Ignore until separator
                self._skipContent()


    def importItemFuncPageVer1Pass2(self, subtag):
        # The subtag is functional page tag
        try:
            # subtag is unicode but func tags are bytestrings
            subtag = str(subtag)
        except UnicodeEncodeError:
            return

        content = self._collectContent()
        try:
            page = self.wikiDocument.getFuncPage(subtag)
            page.replaceLiveText(content)
        except BadFuncPageTagException:
            # This function tag is bad or unknown -> ignore
            return  # TODO Report error


    def importItemSavedSearchVer1Pass2(self, unifName):
        # The subtag is the title of the search
        
        # Content is base64 encoded
        b64Content = self._collectContent()
        
        try:
            datablock = base64BlockDecode(b64Content)
            self.wikiDocument.getWikiData().storeDataBlock(unifName, datablock,
                    storeHint=Consts.DATABLOCK_STOREHINT_INTERN)

        except TypeError:
            # base64 decoding failed
            return  # TODO Report error


    def importItemWikiPageVer1Pass2(self, subtag):
        timeStampLine = self.importFile.readline()[:-1]
        timeStrings = timeStampLine.split(u"  ")
        if len(timeStrings) < 3:
            return  # TODO Report error

        timeStrings = timeStrings[:3]

        try:
            timeStrings = [str(ts) for ts in timeStrings]
        except UnicodeEncodeError:
            return  # TODO Report error

        try:
            timeStamps = [timegm(time.strptime(ts, "%Y-%m-%d/%H:%M:%S"))
                    for ts in timeStrings]

        except (ValueError, OverflowError):
            traceback.print_exc()
            return  # TODO Report error

        content = self._collectContent()
        page = self.wikiDocument.getWikiPageNoError(subtag)

        # TODO How to handle versions here?
        page.replaceLiveText(content)
        if page.getTxtEditor() is not None:
            page.writeToDatabase()

        page.setTimestamps(timeStamps)



    def _doImportItemVersioningOverviewVer1Pass1(self, subtag):
        # Always encode to UTF-8 no matter what the import file encoding is
        content = self._collectContent().encode("utf-8")

        try:
            ovw = Versioning.VersionOverview(self.wikiDocument,
                    unifiedBasePageName=subtag)
            
            ovw.readOverviewFromBytes(content)
            
            ovwUnifName = ovw.getUnifiedName()
            
            self.tempDb.execSql("insert or replace into depgraph(unifName, neededBy) "
                "values (?, 1)", (subtag, ovwUnifName))
                
            for depUnifName in ovw.getDependentDataBlocks(omitSelf=True):
                # Mutual dependency between version overview and each version packet
                self.tempDb.execSql("insert or replace into depgraph(unifName, neededBy) "
                    "values (?, 1)", (depUnifName, ovwUnifName))
                self.tempDb.execSql("insert or replace into depgraph(unifName, neededBy) "
                    "values (?, 1)", (ovwUnifName, depUnifName))
#                 self.tempDb.execSql("insert or replace into entries(unifName, needed) "
#                     "values (?, 1)", (depUnifName,))

        except VersioningException:
            return
            




def describeImporters(mainControl):
    return (MultiPageTextImporter(mainControl),)

