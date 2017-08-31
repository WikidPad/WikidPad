"""

Used terms:
    
    wikiword -- a string matching one of the wiki word regexes
    wiki page -- real existing content stored and associated with a wikiword
            (which is the page name). Sometimes page is synonymous for page name
    alias -- wikiword without content but associated to a page name.
            For the user it looks as if the content of the alias is the content
            of the page for the associated page name
    defined wiki word -- either a page name or an alias
"""



from os.path import exists, join, basename
import os, os.path

from time import time, localtime
import datetime
import glob, traceback

from wx import GetApp

from pwiki.WikiExceptions import *   # TODO make normal import
from pwiki import SearchAndReplace

try:
    import pwiki.sqlite3api as sqlite
    from . import DbStructure
    from .DbStructure import createWikiDB, WikiDBExistsException
except:
    import ExceptionLogger
    ExceptionLogger.logOptionalComponentException(
            "Initialize external sqlite for original_sqlite/WikiData.py")
    sqlite = None
# finally:
#     pass

from pwiki.StringOps import getBinCompactForDiff, applyBinCompact, longPathEnc, \
        longPathDec, binCompactToCompact, fileContentToUnicode, utf8Enc, utf8Dec, \
        uniWithNone, loadEntireTxtFile, Conjunction, lineendToInternal
from pwiki.StringOps import loadEntireFile, writeEntireFile, \
        iterCompatibleFilename, getFileSignatureBlock, guessBaseNameByFilename, \
        createRandomString, pathDec

from ..BaseWikiData import BasicWikiData

import Consts

class WikiData(BasicWikiData):
    "Interface to wiki data."
    def __init__(self, wikiDocument, dataDir, tempDir):
        self.wikiDocument = wikiDocument
        self.dataDir = dataDir
        self.cachedWikiPageLinkTermDict = None

        self.dbFilename = "wikiovw.sli"   # means "wiki overview"
        
        
        self.CreateAndConnectToDb(DbStructure)

        # If true, forces the editor to write platform dependent files to disk
        # (line endings as CR/LF, LF or CR)
        # If false, LF is used always
        self.editorTextMode = False
        
        app = GetApp()

        if app is not None:
            self.initSqlite(app)
        
        DbStructure.registerSqliteFunctions(self.connWrap)

        try:
            self.pagefileSuffix = self.wikiDocument.getWikiConfig().get("main",
                    "db_pagefile_suffix", ".wiki")
        except (IOError, OSError) as e:
            traceback.print_exc()
            raise DbReadAccessError(e)


    def checkDatabaseFormat(self):
        return DbStructure.checkDatabaseFormat(self.connWrap)


    def connect(self):
        formatcheck, formatmsg = self.checkDatabaseFormat()

        if formatcheck == 2:
            # Unknown format
            raise WikiDataException(formatmsg)

        # Update database from previous versions if necessary
        if formatcheck == 1:
            try:
                DbStructure.updateDatabase(self.connWrap, self.dataDir,
                        self.pagefileSuffix)
            except Exception as e:
                traceback.print_exc()
                try:
                    self.connWrap.rollback()
                except Exception as e2:
                    traceback.print_exc()
                    raise DbWriteAccessError(e2)
                raise DbWriteAccessError(e)

        lastException = None
        try:
            # Further possible updates
            DbStructure.updateDatabase2(self.connWrap)
        except sqlite.Error as e:
            # Remember but continue
            lastException = DbWriteAccessError(e)

        # Activate UTF8 support for text in database (content is blob!)
        DbStructure.registerUtf8Support(self.connWrap)

        # Function to convert from content in database to
        # return value, used by getContent()
        self.contentDbToOutput = lambda c: utf8Dec(c, "replace")[0]

        try:
            # Set marker for database type
            self.wikiDocument.getWikiConfig().set("main", "wiki_database_type",
                    "original_sqlite")
        except (IOError, OSError, sqlite.Error) as e:
            # Remember but continue
            lastException = DbWriteAccessError(e)

        # Function to convert unicode strings from input to content in database
        # used by setContent

        def contentUniInputToDb(unidata):
            return utf8Enc(unidata, "replace")[0]

        self.contentUniInputToDb = contentUniInputToDb

        try:
            self._createTempTables()

            # reset cache
            self.cachedWikiPageLinkTermDict = None
            self.cachedGlobalAttrs = None
            self.getGlobalAttributes()
        except (IOError, OSError, sqlite.Error) as e:
            traceback.print_exc()
            try:
                self.connWrap.rollback()
            except (IOError, OSError, sqlite.Error) as e2:
                traceback.print_exc()
                raise DbReadAccessError(e2)
            raise DbReadAccessError(e)
            
        if lastException:
            raise lastException


    # ---------- Direct handling of page data ----------
    
    def getContent(self, word):
        """
        Function must work for read-only wiki.
        """
        try:
            try:
                filePath = self.getWikiWordFileName(word)
            except WikiFileNotFoundException:
                raise
#                 if self.wikiDocument.getWikiConfig().getboolean("main",
#                         "wikiPageFiles_gracefulOutsideAddAndRemove", True):
#                     return u""

            content = loadEntireTxtFile(filePath)

            return fileContentToUnicode(content)
        except (IOError, OSError, sqlite.Error) as e:
            traceback.print_exc()
            raise DbReadAccessError(e)


        # TODO Remove method
    def _updatePageEntry(self, word, moddate = None, creadate = None):
        """
        Update/Create entry with additional information for a page
            (modif./creation date).
        Not part of public API!
        """
        ti = time()
        if moddate is None:
            moddate = ti
        
        try:
            data = self.connWrap.execSqlQuery("select word from wikiwords "
                    "where word = ?", (word,))
        except (IOError, OSError, sqlite.Error) as e:
            traceback.print_exc()
            raise DbReadAccessError(e)

        try:
            if len(data) < 1:
                if creadate is None:
                    creadate = ti

                fileName = self.createWikiWordFileName(word)
                self.connWrap.execSql("insert into wikiwords(word, created, "
                        "modified, filepath, filenamelowercase) "
                        "values (?, ?, ?, ?, ?)",
                        (word, creadate, moddate, fileName,
                        fileName.lower()))
            else:
                self.connWrap.execSql("update wikiwords set modified = ? "
                        "where word = ?", (moddate, word))

                if self.wikiDocument.getWikiConfig().getboolean("main",
                        "wikiPageFiles_gracefulOutsideAddAndRemove", True):
                    try:
                        self.getWikiWordFileName(word, mustExist=True)
                    except WikiFileNotFoundException:
                        fileName = self.createWikiWordFileName(word)

                        self.connWrap.execSql("update wikiwords set filepath = ?, "
                                "filenamelowercase = ? where word = ?",
                                (fileName, fileName.lower(), word))

            self.cachedWikiPageLinkTermDict = None
        except (IOError, OSError, sqlite.Error) as e:
            traceback.print_exc()
            raise DbWriteAccessError(e)



    def setContent(self, word, content, moddate = None, creadate = None):
        """
        Sets the content, does not modify the cache information
        except self.cachedWikiPageLinkTermDict
        """
        assert type(content) is str
        try:
            self._updatePageEntry(word, moddate, creadate)

            filePath = self.getWikiWordFileName(word, mustExist=False)
            writeEntireFile(filePath, content, self.editorTextMode,
                    self.wikiDocument.getWikiConfig().getint("main",
                        "wikiPageFiles_writeFileMode", 0))

            fileSig = self.wikiDocument.getFileSignatureBlock(filePath)
            self.connWrap.execSql("update wikiwords set filesignature = ?, "
                    "metadataprocessed = 0 where word = ?",
                    (sqlite.Binary(fileSig), word))
        except (IOError, OSError, sqlite.Error) as e:
            traceback.print_exc()
            raise DbWriteAccessError(e)


    def _renameContent(self, oldWord, newWord):
        """
        The content which was stored under oldWord is stored
        after the call under newWord. The self.cachedWikiPageLinkTermDict
        dictionary is updated, other caches won't be updated.
        """
        try:
            oldFilePath = self.getWikiWordFileNameRaw(oldWord)
            # To throw exception in case of error
            self.getWikiWordFileName(oldWord)

            head, oldFileName = os.path.split(oldFilePath)
#             head = pathDec(head)
#             oldFileName = pathDec(oldFileName)

            fileName = self.createWikiWordFileName(newWord)
            newFilePath = os.path.join(head, fileName)

            os.rename(longPathEnc(os.path.join(self.dataDir, oldFilePath)),
                    longPathEnc(os.path.join(self.dataDir, newFilePath)))

            self.cachedWikiPageLinkTermDict = None

            self.connWrap.execSql("update wikiwords set word = ?, filepath = ?, "
                    "filenamelowercase = ?, metadataprocessed = 0 where word = ?",
                    (newWord, newFilePath, fileName.lower(), oldWord))

        except (IOError, OSError, sqlite.Error) as e:
            traceback.print_exc()
            raise DbWriteAccessError(e)


    def _deleteContent(self, word):
        try:
            try:
                fileName = self.getWikiWordFileName(word)
            except WikiFileNotFoundException:
                if self.wikiDocument.getWikiConfig().getboolean("main",
                        "wikiPageFiles_gracefulOutsideAddAndRemove", True):
                    fileName = None
                else:
                    raise

            self.connWrap.execSql("delete from wikiwords where word = ?",
                    (word,))
            self.cachedWikiPageLinkTermDict = None
            if fileName is not None and os.path.exists(fileName):
                os.unlink(fileName)
        except (IOError, OSError, sqlite.Error) as e:
            traceback.print_exc()
            raise DbWriteAccessError(e)


    def validateFileSignatureForWikiPageName(self, word, setMetaDataDirty=False, 
            refresh=False):
        """
        Returns True if file signature stored in DB matches the file
        containing the content, False otherwise.
        """
        try:
            try:
                filePath = self.getWikiWordFileName(word)
            except WikiFileNotFoundException:
                if self.wikiDocument.getWikiConfig().getboolean("main",
                        "wikiPageFiles_gracefulOutsideAddAndRemove", True):
                    # File is missing and this should be handled gracefully
                    return True
                else:
                    raise

#             if self.wikiDocument.getWikiConfig().getboolean("main",
#                     "wikiPageFiles_gracefulOutsideAddAndRemove", True) and \
#                     not os.path.exists(filePath):
#                 # File is missing and this should be handled gracefully
#                 self.refreshWikiPageLinkTerms(deleteFully=True)
#                 return True

            fileSig = self.wikiDocument.getFileSignatureBlock(filePath)

            dbFileSig = self.connWrap.execSqlQuerySingleItem(
                    "select filesignature from wikiwords where word = ?",
                    (word,))

            return dbFileSig == fileSig
        except (IOError, OSError, sqlite.Error) as e:
            traceback.print_exc()
            raise DbReadAccessError(e)


    def refreshFileSignatureForWikiPageName(self, word):
        """
        Sets file signature to match current file.
        """
        try:
            filePath = self.getWikiWordFileName(word)
            fileSig = self.wikiDocument.getFileSignatureBlock(filePath)
        except (IOError, OSErro, sqlite.Error) as e:
            traceback.print_exc()
            raise DbReadAccessError(e)

        try:
            self.connWrap.execSql("update wikiwords set filesignature = ? "
                    "where word = ?", (sqlite.Binary(fileSig), word))
        except (IOError, OSError, sqlite.Error) as e:
            traceback.print_exc()
            raise DbWriteAccessError(e)



#             self.execSql("update wikiwords set filesignature = ?, "
#                     "metadataprocessed = ? where word = ?", (fileSig, 0, word))
# 
#                     fileSig = self.wikiDocument.getFileSignatureBlock(fullPath)

    

    # ---------- Handling of relationships cache ----------

    def getChildRelationships(self, wikiWord, existingonly=False,
            selfreference=True, withFields=()):
        """
        get the child relations of this word
        Function must work for read-only wiki.
        existingonly -- List only existing wiki words
        selfreference -- List also wikiWord if it references itself
        withFields -- Seq. of names of fields which should be included in
            the output. If this is not empty, tuples are returned
            (relation, ...) with ... as further fields in the order mentioned
            in withfields.

            Possible field names:
                "firstcharpos": position of link in page (may be -1 to represent
                    unknown)
                "modified": Modification date of child
        """
        if withFields is None:
            withFields = ()

        addFields = ""
        converters = [lambda s: s]
        for field in withFields:
            if field == "firstcharpos":
                addFields += ", firstcharpos"
                converters.append(lambda s: s)
            elif field == "modified":
#                 addFields += (", ifnull((select modified from wikiwords "
#                         "where wikiwords.word = relation), 0.0)")
#                 addFields += (", ifnull((select modified from wikiwords "
#                         "where wikiwords.word = relation or "
#                         "wikiwords.word = (select word from wikiwordattrs "
#                         "where key = 'alias' and value = relation)), 0.0)")

                # "modified" isn't a field of wikirelations. We need
                # some SQL magic to retrieve the modification date
                addFields += (", ifnull((select modified from wikiwords "
                        "where wikiwords.word = relation or "
                        "wikiwords.word = (select word from wikiwordmatchterms "
                        "where wikiwordmatchterms.matchterm = relation and "
                        "(wikiwordmatchterms.type & 2) != 0 limit 1)), 0.0)")
                # Consts.WIKIWORDMATCHTERMS_TYPE_ASLINK == 2

                converters.append(float)


        sql = "select relation%s from wikirelations where word = ?" % addFields

        if existingonly:
            # filter to only words in wikiwords or aliases
#             sql += " and (exists (select word from wikiwords "+\
#                     "where word = relation) or exists "+\
#                     "(select value from wikiwordattrs "+\
#                     "where value = relation and key = 'alias'))"
            sql += (" and (exists (select 1 from wikiwords "
                    "where word = relation) or exists "
                    "(select 1 from wikiwordmatchterms "
                    "where wikiwordmatchterms.matchterm = relation and "
                    "(wikiwordmatchterms.type & 2) != 0))")
            # Consts.WIKIWORDMATCHTERMS_TYPE_ASLINK == 2

        if not selfreference:
            sql += " and relation != word"

        try:
            if len(withFields) > 0:
                return [tuple(c(item) for c, item in zip(converters, row))
                        for row in self.connWrap.execSqlQuery(sql, (wikiWord,))]
            else:
                return self.connWrap.execSqlQuerySingleColumn(sql, (wikiWord,))
        except (IOError, OSError, sqlite.Error) as e:
            traceback.print_exc()
            raise DbReadAccessError(e)


#     def getChildRelationshipsAndChildNumber(self, wikiWord, existingonly=False,
#             selfreference=False):
#         sql = ("select parent.relation, count(child.relation) "
#                 "from wikirelations as parent left join wikirelations as child "
#                 "on parent.relation=child.word where parent.word = ? "
#                 "group by parent.relation")
#         
# #         return self.connWrap.execSqlQuerySingleColumn(sql, (wikiWord,))
#         return self.connWrap.execSqlQuery(sql, (wikiWord,))
#         
# 
# 
#     def getChildRelationshipsAndHasChildren(self, wikiWord, existingonly=False,
#             selfreference=False):
#         """
#         get the child relations to this word as sequence of tuples
#             (<child word>, <has child children?>). Used when expanding
#             a node in the tree control. If cycles are forbidden in the
#             tree, a True in the "children" flag must be checked
#             for cycles, a False is always correct.
# 
#         existingonly -- List only existing wiki words
#         selfreference -- List also wikiWord if it references itself
#         """
#         innersql = "select relation from wikirelations as innerrel where "+\
#                 "word = wikirelations.relation"
#         if existingonly:
#             # filter to only words in wikiwords or aliases
#             innersql += " and (exists (select word from wikiwords "+\
#                     "where word = relation) or exists "+\
#                     "(select value from wikiwordattrs "+\
#                     "where value = relation and key = 'alias'))"
# 
#         if not selfreference:
#             innersql += " and relation != word"
# 
# 
#         outersql = "select relation, exists(%s) from wikirelations where word = ?"
#         if existingonly:
#             # filter to only words in wikiwords or aliases
#             outersql += " and (exists (select word from wikiwords "+\
#                     "where word = relation) or exists "+\
#                     "(select value from wikiwordattrs "+\
#                     "where value = relation and key = 'alias'))"
# 
#         if not selfreference:
#             outersql += " and relation != word"
# 
#         outersql = outersql % innersql
# 
# 
#         return self.connWrap.execSqlQuery(outersql, (wikiWord,))





    def _findNewWordForFile(self, path):
        wikiWord = guessBaseNameByFilename(path, self.pagefileSuffix)
        try:
            if self.connWrap.execSqlQuerySingleItem(
                    "select word from wikiwords where word = ?", (wikiWord,)):
                for i in range(20):    # "while True" is too dangerous
                    rand = createRandomString(10)

                    if self.connWrap.execSqlQuerySingleItem(
                            "select word from wikiwords where word = ?",
                            (wikiWord + "~" + rand,)):
                        continue
                    
                    return wikiWord + "~" + rand

                return None

            else:
                return wikiWord

        except (IOError, OSError, sqlite.Error) as e:
            traceback.print_exc()
            raise DbWriteAccessError(e)


    # ---------- Listing/Searching wiki words (see also "alias handling", "searching pages")----------

    def refreshWikiPageLinkTerms(self, deleteFully=False):
        """
        Refreshes the internal list of defined pages which
        may be different from the list of pages for which
        content is available (not possible for compact database)
        because there may be a DB entry without a file or vice versa.
        The function tries to conserve additional informations
        (creation/modif. date) if possible.
        
        It is mainly called during rebuilding of the wiki 
        so it must not rely on the presence of other cache
        information (e.g. relations).

        The self.cachedWikiPageLinkTermDict is invalidated.
        
        deleteFully -- if true, all cache information related to a no
            longer existing word is also deleted
        """
        diskFiles = frozenset(self._getAllWikiFileNamesFromDisk())
        dbFiles = frozenset(self._getAllWikiFileNamesFromDb())
        
        self.cachedWikiPageLinkTermDict = None
        try:
            # Delete words for which no file is present anymore
            for path in self.connWrap.execSqlQuerySingleColumn(
                    "select filepath from wikiwords"):

                testPath = longPathEnc(os.path.join(self.dataDir, path))
                if not os.path.exists(testPath) or not os.path.isfile(testPath):
                    if deleteFully:
                        words = self.connWrap.execSqlQuerySingleColumn(
                                "select word from wikiwords "
                                "where filepath = ?", (path,))
                        for word in words:
                            try:
                                self.deleteWord(word, delContent=False)
                            except WikiDataException as e:
                                if e.getTag() != "delete rootPage":
                                    raise

                    self.connWrap.execSql("delete from wikiwords "
                            "where filepath = ?", (path,))

            # Add new words:
            ti = time()
            
            for path in (diskFiles - dbFiles):
                fullPath = os.path.join(self.dataDir, path)
                st = os.stat(longPathEnc(fullPath))
                
                wikiWord = self._findNewWordForFile(path)
                
                if wikiWord is not None:
                    fileSig = self.wikiDocument.getFileSignatureBlock(fullPath)
                    
                    self.connWrap.execSql("insert into wikiwords(word, created, "
                            "modified, filepath, filenamelowercase, "
                            "filesignature, metadataprocessed) "
                            "values (?, ?, ?, ?, ?, ?, 0)",
                            (wikiWord, ti, st.st_mtime, path, path.lower(),
                                    sqlite.Binary(fileSig)))
                                    
                    page = self.wikiDocument.getWikiPage(wikiWord)
                    page.refreshSyncUpdateMatchTerms()
                    
        except (IOError, OSError, sqlite.Error) as e:
            traceback.print_exc()
            raise DbWriteAccessError(e)


    def _getAllWikiFileNamesFromDisk(self):   # Used for rebuilding wiki
        try:
            files = glob.glob(join(self.dataDir, '*' + self.pagefileSuffix))

            return [pathDec(basename(fn)) for fn in files]

#             result = []
#             for file in files:
#                 word = pathDec(basename(file))
#                 if word.endswith(self.pagefileSuffix):
#                     word = word[:-len(self.pagefileSuffix)]
#                 
#                 result.append(word)
#             
#             return result

        except (IOError, OSError, sqlite.Error) as e:
            traceback.print_exc()
            raise DbReadAccessError(e)


    def _getAllWikiFileNamesFromDb(self):   # Used for rebuilding wiki
        try:
            return self.connWrap.execSqlQuerySingleColumn("select filepath "
                    "from wikiwords")

        except (IOError, OSError, sqlite.Error) as e:
            traceback.print_exc()
            raise DbReadAccessError(e)


    def getWikiWordFileNameRaw(self, wikiWord):
        """
        Not part of public API!
        Function must work for read-only wiki.
        """
        try:
            path = self.connWrap.execSqlQuerySingleItem("select filepath "
                    "from wikiwords where word = ?", (wikiWord,))
        except (IOError, OSError, sqlite.Error) as e:
            traceback.print_exc()
            raise DbReadAccessError(e)

        if path is None:
            raise WikiFileNotFoundException(
                    _("Wiki page not found (no path information) for word: %s") %
                    wikiWord)

        return path


    def getWikiWordFileName(self, wikiWord, mustExist=True):
        """
        Not part of public API!
        Function must work for read-only wiki.
        """
        try:
            path = longPathEnc(join(self.dataDir,
                    self.getWikiWordFileNameRaw(wikiWord)))
    
            if mustExist and \
                    (not os.path.exists(path) or not os.path.isfile(path)):
                 raise WikiFileNotFoundException(
                        _("Wiki page not found (bad path information) for word: %s") %
                        wikiWord)
        except WikiFileNotFoundException:
            if self.wikiDocument.getWikiConfig().getboolean("main",
                    "wikiPageFiles_gracefulOutsideAddAndRemove", True):
                # Refresh content names and try again
                self.refreshWikiPageLinkTerms(deleteFully=True)
            
                path = longPathEnc(join(self.dataDir,
                        self.getWikiWordFileNameRaw(wikiWord)))

                if mustExist and \
                        (not os.path.exists(path) or not os.path.isfile(path)):
                     raise WikiFileNotFoundException(
                            _("Wiki page not found (bad path information) for word: %s") %
                            wikiWord)
            else:
                raise

        return path


    def createWikiWordFileName(self, wikiWord):
        """
        Create a filename for wikiWord which is not yet in the database or
        a file with that name in the data directory
        """
        asciiOnly = self.wikiDocument.getWikiConfig().getboolean("main",
                "wikiPageFiles_asciiOnly", False)
                
        maxFnLength = self.wikiDocument.getWikiConfig().getint("main",
                "wikiPageFiles_maxNameLength", 120)

        icf = iterCompatibleFilename(wikiWord, self.pagefileSuffix,
                asciiOnly=asciiOnly, maxLength=maxFnLength)
        for i in range(30):   # "while True" would be too dangerous
            fileName = next(icf)
            existing = self.connWrap.execSqlQuerySingleColumn(
                    "select filenamelowercase from wikiwords "
                    "where filenamelowercase = ?", (fileName.lower(),))
            if len(existing) > 0:
                continue
            if exists(longPathEnc(join(self.dataDir, fileName))):
                continue

            return fileName

        return None


    def _guessWikiWordFileName(self, wikiWord):
        """
        Try to find an existing file in self.dataDir which COULD BE the page
        file for wikiWord.
        Called when external adding of files should be handled gracefully.
        Returns either the filename relative to self.dataDir or None.
        """
        try:
            asciiOnly = self.wikiDocument.getWikiConfig().getboolean("main",
                    "wikiPageFiles_asciiOnly", False)
                    
            maxFnLength = self.wikiDocument.getWikiConfig().getint("main",
                    "wikiPageFiles_maxNameLength", 120)

            # Try first with current ascii-only setting
            icf = iterCompatibleFilename(wikiWord, self.pagefileSuffix,
                    asciiOnly=asciiOnly, maxLength=maxFnLength)
    
            for i in range(2):
                fileName = next(icf)

                existing = self.connWrap.execSqlQuerySingleColumn(
                        "select filenamelowercase from wikiwords "
                        "where filenamelowercase = ?", (fileName.lower(),))
                if len(existing) > 0:
                    continue
                if not os.path.exists(longPathEnc(join(self.dataDir, fileName))):
                    continue

                return fileName

            # Then the same with opposite ascii-only setting
            icf = iterCompatibleFilename(wikiWord, self.pagefileSuffix,
                    asciiOnly=not asciiOnly, maxLength=maxFnLength)
    
            for i in range(2):
                fileName = next(icf)

                existing = self.connWrap.execSqlQuerySingleColumn(
                        "select filenamelowercase from wikiwords "
                        "where filenamelowercase = ?", (fileName.lower(),))
                if len(existing) > 0:
                    continue
                if not os.path.exists(longPathEnc(join(self.dataDir, fileName))):
                    continue

                return fileName
            
            return None
        except (IOError, OSError, sqlite.Error) as e:
            traceback.print_exc()
            raise DbReadAccessError(e)

    # ---------- Attribute cache handling ----------

    # ---------- Alias handling ----------

    # ---------- Todo cache handling ----------

    # ---------- Wikiword matchterm cache handling ----------

    # ---------- Data block handling ----------

    # TODO Optimize
    def getDataBlockUnifNamesStartingWith(self, startingWith):
        """
        Return all unified names starting with startingWith (case sensitive)
        """
        try:
            startingWith = sqlite.escapeForGlob(startingWith)
            
            return self.connWrap.execSqlQuerySingleColumn(
                    "select distinct(unifiedname) from datablocks where "
                    "unifiedname glob (? || '*') union "
                    "select distinct(unifiedname) from datablocksexternal where "
                    "unifiedname glob (? || '*')", 
                    (startingWith, startingWith))

        except (IOError, OSError, sqlite.Error) as e:
            traceback.print_exc()
            raise DbReadAccessError(e)


    def retrieveDataBlock(self, unifName, default=""):
        """
        Retrieve data block as binary string.
        If option "wikiPageFiles_gracefulOutsideAddAndRemove" is set and
        the file couldn't be retrieved, default is returned instead.
        """
        try:
            datablock = self.connWrap.execSqlQuerySingleItem(
                    "select data from datablocks where unifiedname = ?",
                    (unifName,))
            if datablock is not None:
                return datablock
            
            filePath = self.connWrap.execSqlQuerySingleItem(
                    "select filepath from datablocksexternal where unifiedname = ?",
                    (unifName,))
            
            if filePath is None:
                return None  # TODO exception?

        except (IOError, OSError, sqlite.Error) as e:
            traceback.print_exc()
            raise DbReadAccessError(e)

        try:
            datablock = loadEntireFile(join(self.dataDir, filePath))
            return datablock

        except (IOError, OSError, sqlite.Error) as e:
            if self.wikiDocument.getWikiConfig().getboolean("main",
                    "wikiPageFiles_gracefulOutsideAddAndRemove", True):
                return default
            else:
                traceback.print_exc()
                raise DbReadAccessError(e)


    def retrieveDataBlockAsText(self, unifName, default=""):
        """
        Retrieve data block as unicode string (assuming it was encoded properly)
        and with normalized line-ending (Un*x-style).
        If option "wikiPageFiles_gracefulOutsideAddAndRemove" is set and
        the file couldn't be retrieved, default is returned instead.
        """
        datablock = self.retrieveDataBlock(unifName, default=default)
        if datablock is None:
            return None

        return fileContentToUnicode(lineendToInternal(datablock))



    def storeDataBlock(self, unifName, newdata, storeHint=None):
        """
        Store newdata under unified name. If previously data was stored under the
        same name, it is deleted.
        
        unifName -- unistring. Unified name to store data under
        newdata -- Data to store, either bytestring or unistring. The latter one
            will be converted using utf-8 before storing and the file gets
            the appropriate line-ending of the OS for external data blocks .
        storeHint -- Hint if data should be stored intern in table or extern
            in a file (using DATABLOCK_STOREHINT_* constants from Consts.py).
            storeHint is ignored in compact_sqlite
        """
        
        if storeHint is None:
            storeHint = Consts.DATABLOCK_STOREHINT_INTERN
            
        if storeHint == Consts.DATABLOCK_STOREHINT_INTERN:
            try:
                datablock = self.connWrap.execSqlQuerySingleItem(
                        "select data from datablocks where unifiedname = ?",
                        (unifName,))
            except (IOError, OSError, sqlite.Error) as e:
                traceback.print_exc()
                raise DbReadAccessError(e)

            try:
                if datablock is not None:
                    # It is in internal data blocks
                    self.connWrap.execSql("update datablocks set data = ? where "
                            "unifiedname = ?", (sqlite.Binary(newdata), unifName))
                    return

                # It may be in external data blocks
                self.deleteDataBlock(unifName)
                
                self.connWrap.execSql("insert into datablocks(unifiedname, data) "
                        "values (?, ?)", (unifName, sqlite.Binary(newdata)))

            except (IOError, OSError, sqlite.Error) as e:
                traceback.print_exc()
                raise DbWriteAccessError(e)

        else:   # storeHint == Consts.DATABLOCK_STOREHINT_EXTERN
            try:
                filePath = self.connWrap.execSqlQuerySingleItem(
                        "select filepath from datablocksexternal "
                        "where unifiedname = ?", (unifName,))
            except (IOError, OSError, sqlite.Error) as e:
                traceback.print_exc()
                raise DbReadAccessError(e)

            try:
                if filePath is not None:
                    # The entry is already in an external file, so overwrite it
                    writeEntireFile(join(self.dataDir, filePath), newdata,
                            self.editorTextMode and isinstance(newdata, str),
                            self.wikiDocument.getWikiConfig().getint("main",
                                "wikiPageFiles_writeFileMode", 0))

                    fileSig = self.wikiDocument.getFileSignatureBlock(
                            join(self.dataDir, filePath))
                    self.connWrap.execSql("update datablocksexternal "
                            "set filesignature = ?", (sqlite.Binary(fileSig),))
                    return

                asciiOnly = self.wikiDocument.getWikiConfig().getboolean("main",
                        "wikiPageFiles_asciiOnly", False)

                maxFnLength = self.wikiDocument.getWikiConfig().getint("main",
                        "wikiPageFiles_maxNameLength", 120)

                # Find unused filename
                icf = iterCompatibleFilename(unifName, ".data",
                        asciiOnly=asciiOnly, maxLength=maxFnLength)

                for i in range(30):   # "while True" would be too dangerous
                    fileName = next(icf)
                    existing = self.connWrap.execSqlQuerySingleColumn(
                            "select filenamelowercase "
                            "from datablocksexternal where filenamelowercase = ?",
                            (fileName.lower(),))
                    if len(existing) > 0:
                        continue
                    if exists(longPathEnc(join(self.dataDir, fileName))):
                        continue

                    break
                else:
                    return None
                
                filePath = join(self.dataDir, fileName)
                writeEntireFile(filePath, newdata,
                        self.editorTextMode and isinstance(newdata, str),
                        self.wikiDocument.getWikiConfig().getint("main",
                            "wikiPageFiles_writeFileMode", 0))
                fileSig = self.wikiDocument.getFileSignatureBlock(filePath)

                # It may be in internal data blocks, so try to delete
                self.deleteDataBlock(unifName)

                self.connWrap.execSql("insert into datablocksexternal("
                        "unifiedname, filepath, filenamelowercase, "
                        "filesignature) values (?, ?, ?, ?)",
                        (unifName, fileName, fileName.lower(),
                        sqlite.Binary(fileSig)))

            except (IOError, OSError, sqlite.Error) as e:
                traceback.print_exc()
                raise DbWriteAccessError(e)


    def guessDataBlockStoreHint(self, unifName):
        """
        Return a guess of the store hint used to store the block last time.
        Returns one of the DATABLOCK_STOREHINT_* constants from Consts.py.
        The function is allowed to return the wrong value (therefore a guess).
        It returns None for non-existing data blocks.
        """
        try:
            datablock = self.connWrap.execSqlQuerySingleItem(
                    "select 1 from datablocks where unifiedname = ?",
                    (unifName,))
        except (IOError, OSError, sqlite.Error) as e:
            traceback.print_exc()
            raise DbReadAccessError(e)

        if datablock is not None:
            return Consts.DATABLOCK_STOREHINT_INTERN

        try:
            datablock = self.connWrap.execSqlQuerySingleItem(
                    "select 1 from datablocksexternal where unifiedname = ?",
                    (unifName,))
        except (IOError, OSError, sqlite.Error) as e:
            traceback.print_exc()
            raise DbWriteAccessError(e)

        if datablock is not None:
            return Consts.DATABLOCK_STOREHINT_EXTERN
        
        return None


    def deleteDataBlock(self, unifName):
        """
        Delete data block with the associated unified name. If the unified name
        is not in database, nothing happens.
        """
        try:
            self.connWrap.execSql(
                    "delete from datablocks where unifiedname = ?", (unifName,))
            
            filePath = self.connWrap.execSqlQuerySingleItem(
                    "select filepath from datablocksexternal "
                    "where unifiedname = ?", (unifName,))

            if filePath is not None:
                try:
                    # The entry is in an external file, so delete it
                    os.unlink(longPathEnc(join(self.dataDir, filePath)))
                except (IOError, OSError):
                    if not self.wikiDocument.getWikiConfig().getboolean("main",
                            "wikiPageFiles_gracefulOutsideAddAndRemove", True):
                        raise

                self.connWrap.execSql(
                        "delete from datablocksexternal where unifiedname = ?",
                        (unifName,))

        except (IOError, OSError, sqlite.Error) as e:
            traceback.print_exc()
            raise DbWriteAccessError(e)


    # ---------- Searching pages ----------

    def search(self, sarOp, exclusionSet):  # TODO Threadholder for all
        """
        Search all content using the SearchAndReplaceOperation sarOp and
        return set of all page names that match the search criteria.
        sarOp.beginWikiSearch() must be called before calling this function,
        sarOp.endWikiSearch() must be called after calling this function.
        Function must work for read-only wiki.
        
        exclusionSet -- set of wiki words for which their pages shouldn't be
        searched here and which must not be part of the result set
        """
        result = set()

        if sarOp.isTextNeededForTest():
            for word in self.getAllDefinedWikiPageNames():
                if word in exclusionSet:
                    continue
                try:
                    fileContents = self.getContent(word)
                except WikiFileNotFoundException:
                    # some error in cache (should not happen)
                    continue
    
                if sarOp.testWikiPage(word, fileContents) == True:
                    result.add(word)
        else:
            for word in self.getAllDefinedWikiPageNames():
                if word in exclusionSet:
                    continue

                if sarOp.testWikiPage(word, None) == True:
                    result.add(word)

        return result
        

    # ---------- Miscellaneous ----------

    _CAPABILITIES = {
        "rebuild": 1,
        "compactify": 1,     # = sqlite vacuum
        "filePerPage": 1,   # Uses a single file per page
#         "versioning": 1,     # (old versioning)
#         "plain text import":1   # Is already plain text      
        }


    def setEditorTextMode(self, mode):
        """
        If true, forces the editor to write platform dependent files to disk
        (line endings as CR/LF, LF or CR).
        If false, LF is used always.
        
        Must be implemented if checkCapability returns a version number
        for "filePerPage".
        """           
        self.editorTextMode = mode


        # TODO drop and recreate tables and indices!
    def clearCacheTables(self):
        """
        Clear all tables in the database which contain non-essential
        (cache) information as well as other cache information.
        Needed before rebuilding the whole wiki
        """
        try:
            self.connWrap.syncCommit()

            self.cachedWikiPageLinkTermDict = None
            self.cachedGlobalAttrs = None

            self.fullyResetMetaDataState()

            DbStructure.recreateCacheTables(self.connWrap)
            self.connWrap.syncCommit()
        except (IOError, OSError, sqlite.Error) as e:
            traceback.print_exc()
            raise DbWriteAccessError(e)


    def testWrite(self):
        """
        Test if writing to database is possible. Throws a DbWriteAccessError
        if writing failed.
        """
        try:
            self.connWrap.syncCommit()
            self.connWrap.execSql("insert or replace into settings(key, value) "
                    "values ('formatver', ?)", (DbStructure.getSettingsValue(
                    self.connWrap, "formatver"),))
            self.connWrap.commit()
        except (IOError, OSError, sqlite.Error) as e:
            traceback.print_exc()
            raise DbWriteAccessError(e)




    # ---------- Other optional functionality ----------

    def cleanupAfterRebuild(self, progresshandler):
        """
        Rebuild cached structures, try to repair database inconsistencies.

        Must be implemented if checkCapability returns a version number
        for "rebuild".
        
        progresshandler -- Object, fulfilling the GuiProgressHandler
            protocol
        """
        try:
            self.connWrap.execSql("update wikiwordmatchterms "
                    "set matchtermnormcase=utf8Normcase(matchterm)")
            DbStructure.rebuildIndices(self.connWrap)
        except (IOError, OSError, sqlite.Error) as e:
            traceback.print_exc()
            raise DbWriteAccessError(e)


        # TODO
        # Check the presence of important indexes

#         indexes = self.connWrap.execSqlQuerySingleColumn(
#                 "select name from sqlite_master where type='index'")
#         indexes = map(string.upper, indexes)
#         
#         if not "WIKIWORDCONTENT_PKEY" in indexes:
#             # Maybe we have multiple pages with the same name in the database
#             
#             # Copy valid creation date to all pages
#             self.connWrap.execSql("update wikiwordcontent set "
#                     "created=(select max(created) from wikiwordcontent as "
#                     "inner where inner.word=wikiwordcontent.word)")
#             
#             # Delete all but the newest page
#             self.connWrap.execSql("delete from wikiwordcontent where "
#                     "ROWID not in (select max(ROWID) from wikiwordcontent as "
#                     "outer where modified=(select max(modified) from "
#                     "wikiwordcontent as inner where inner.word=outer.word) "
#                     "group by outer.word)")
#                     
#             DbStructure.rebuildIndices(self.connWrap)

       # TODO: More repair operations


#         self.cachedWikiPageLinkTermDict = {}
# 
#         # cache aliases
#         aliases = self.getAllAliases()
#         for alias in aliases:
#             self.cachedWikiPageLinkTermDict[alias] = 2
# 
#         # recreate word caches
#         for word in self.getAllDefinedContentNames():
#             self.cachedWikiPageLinkTermDict[word] = 1



#         finally:            
#             progresshandler.close()




def listAvailableWikiDataHandlers():
    """
    Returns a list with the names of available handlers from this module.
    Each item is a tuple (<internal name>, <descriptive name>)
    """
    if sqlite is not None:
        return [("original_sqlite", "Original Sqlite")]
    else:
        return []


def getWikiDataHandler(name):
    """
    Returns a factory function (or class) for an appropriate
    WikiData object and a createWikiDB function or (None, None)
    if name is unknown
    """
    if name == "original_sqlite":
        return WikiData, createWikiDB
    
    return (None, None)
