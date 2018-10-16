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

from ... import StringOps

from ...StringOps import longPathEnc, \
        longPathDec, fileContentToUnicode, utf8Enc, utf8Dec
from ...StringOps import writeEntireFile, iterCompatibleFilename


import Consts

class WikiData:
    "Interface to wiki data."
    def __init__(self, wikiDocument, dataDir, tempDir):
        self.wikiDocument = wikiDocument
        self.dataDir = dataDir
        self.resolveCaseNormed = False
        self.cachedWikiPageLinkTermDict = None
        
        dbPath = self.wikiDocument.getWikiConfig().get("wiki_db", "db_filename",
                "").strip()
                
        if (dbPath == ""):
            dbPath = "wikiovw.sli"

        dbfile = join(dataDir, dbPath)   # means "wiki overview"
        
        try:
            if (not exists(longPathEnc(dbfile))):
                DbStructure.createWikiDB(None, dataDir,
                        wikiDocument=self.wikiDocument)
        except (IOError, OSError, sqlite.Error) as e:
            traceback.print_exc()
            raise DbWriteAccessError(e)

        dbfile = longPathDec(dbfile)

        try:
            self.connWrap = DbStructure.ConnectWrapSyncCommit(
                    sqlite.connect(dbfile))
        except (IOError, OSError, sqlite.Error) as e:
            traceback.print_exc()
            raise DbReadAccessError(e)

        # If true, forces the editor to write platform dependent files to disk
        # (line endings as CR/LF, LF or CR)
        # If false, LF is used always
        self.editorTextMode = False
        
        # Set temporary directory if this is first sqlite use after prog. start
        if not GetApp().sqliteInitFlag:
            globalConfig = GetApp().getGlobalConfig()
            if globalConfig.getboolean("main", "tempHandling_preferMemory",
                    False):
                tempMode = "memory"
            else:
                tempMode = globalConfig.get("main", "tempHandling_tempMode",
                        "system")

            if tempMode == "auto":
                if GetApp().isInPortableMode():
                    tempMode = "config"
                else:
                    tempMode = "system"
            
            if tempMode == "memory":
                self.connWrap.execSql("pragma temp_store = 2")
            elif tempMode == "given":
                tempDir = globalConfig.get("main", "tempHandling_tempDir", "")
                try:
                    self.connWrap.execSql("pragma temp_store_directory = '%s'" %
                            utf8Enc(tempDir)[0])
                except sqlite.Error:
                    self.connWrap.execSql("pragma temp_store_directory = ''")

                self.connWrap.execSql("pragma temp_store = 1")
            elif tempMode == "config":
                self.connWrap.execSql("pragma temp_store_directory = '%s'" %
                        utf8Enc(GetApp().getGlobalConfigSubDir())[0])
                self.connWrap.execSql("pragma temp_store = 1")
            else:   # tempMode == u"system"
                self.connWrap.execSql("pragma temp_store_directory = ''")
                self.connWrap.execSql("pragma temp_store = 1")

            GetApp().sqliteInitFlag = True

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


    def _reinit(self):
        """
        Actual initialization or reinitialization after rebuildWiki()
        """
        pass        


    def _createTempTables(self):
        # Temporary table for findBestPathFromWordToWord
        # TODO: Possible for read-only dbs?

        # These schema changes are only on a temporary table so they are not
        # in DbStructure.py
        self.connWrap.execSql("create temp table temppathfindparents "
                "(word text primary key, child text, steps integer)")

        self.connWrap.execSql("create index temppathfindparents_steps "
                "on temppathfindparents(steps)")


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

            content = StringOps.loadEntireTxtFile(filePath)

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


    def getTimestamps(self, word):
        """
        Returns a tuple with modification, creation and visit date of
        a word or (None, None, None) if word is not in the database.
        Aliases must be resolved beforehand.
        Function must work for read-only wiki.
        """
        try:
            dates = self.connWrap.execSqlQuery(
                    "select modified, created, visited from wikiwords where word = ?",
                    (word,))
    
            if len(dates) > 0:
                return (float(dates[0][0]), float(dates[0][1]), float(dates[0][2]))
            else:
                return (None, None, None)  # ?
        except (IOError, OSError, sqlite.Error) as e:
            traceback.print_exc()
            raise DbReadAccessError(e)


    def setTimestamps(self, word, timestamps):
        """
        Set timestamps for an existing wiki page.
        Aliases must be resolved beforehand.
        """
        moddate, creadate, visitdate = timestamps[:3]

        try:
            data = self.connWrap.execSqlQuery("select word from wikiwords "
                    "where word = ?", (word,))
        except (IOError, OSError, sqlite.Error) as e:
            traceback.print_exc()
            raise DbReadAccessError(e)

        try:
            if len(data) < 1:
                raise WikiFileNotFoundException
            else:
                self.connWrap.execSql("update wikiwords set modified = ?, "
                        "created = ?, visited = ? where word = ?",
                        (moddate, creadate, visitdate, word))
        except (IOError, OSError, sqlite.Error) as e:
            traceback.print_exc()
            raise DbWriteAccessError(e)


    def setWikiWordReadOnly(self, word, flag):
        """
        Set readonly flag of a wikiword. Warning: Methods in WikiData do not
        respect this flag.
        word -- wikiword to modify (must exist, aliases must be resolved
                beforehand)
        flag -- integer value. 0: Readwrite; &1: Readonly
        """
        try:
            data = self.connWrap.execSqlQuery("select word from wikiwords "
                    "where word = ?", (word,))
        except (IOError, OSError, sqlite.Error) as e:
            traceback.print_exc()
            raise DbReadAccessError(e)

        try:
            if len(data) < 1:
                raise WikiFileNotFoundException
            else:
                self.connWrap.execSql("update wikiwords set readonly = ? "
                        "where word = ?", (flag, word))
        except (IOError, OSError, sqlite.Error) as e:
            traceback.print_exc()
            raise DbWriteAccessError(e)
        

    def getWikiWordReadOnly(self, word):
        """
        Returns readonly flag of a wikiword. Warning: Methods in WikiData do not
        respect this flag.
        """
        try:
            return self.connWrap.execSqlQuerySingleItem(
                    "select readonly from wikiwords where word = ?",
                    (word,))
        except (IOError, OSError, sqlite.Error) as e:
            traceback.print_exc()
            raise DbReadAccessError(e)


    def getExistingWikiWordInfo(self, wikiWord, withFields=()):
        """
        Get information about an existing wiki word
        Aliases must be resolved beforehand.
        Function must work for read-only wiki.
        withFields -- Seq. of names of fields which should be included in
            the output. If this is not empty, a tuple is returned
            (relation, ...) with ... as further fields in the order mentioned
            in withfields.

            Possible field names:
                "modified": Modification date of page
                "created": Creation date of page
                "visited": Last visit date of page
                "readonly": Read only flag
                "firstcharpos": Dummy returning very high value
        """
        if withFields is None:
            withFields = ()

        addFields = ""
        converters = [lambda s: s]

        for field in withFields:
            if field == "modified":
                addFields += ", modified"
                converters.append(float)
            elif field == "created":
                addFields += ", created"
                converters.append(float)
            elif field == "visited":
                addFields += ", visited"
                converters.append(float)
            elif field == "readonly":
                addFields += ", readonly"
                converters.append(int)
            elif field == "firstcharpos":
                # Fake character position. TODO More elegantly
                addFields += ", 0"
                converters.append(lambda s: 2000000000)


        sql = "select word%s from wikiwords where word = ?" % addFields

        try:
            if len(withFields) > 0:
                dbresult = [tuple(c(item) for c, item in zip(converters, row))
                        for row in self.connWrap.execSqlQuery(sql, (wikiWord,))]
            else:
                dbresult = self.connWrap.execSqlQuerySingleColumn(sql, (wikiWord,))
            
            if len(dbresult) == 0:
                raise WikiWordNotFoundException(wikiWord)
            
            return dbresult[0]
        except (IOError, OSError, sqlite.Error) as e:
            traceback.print_exc()
            raise DbReadAccessError(e)



    # ---------- Renaming/deleting pages with cache update or invalidation ----------

    def renameWord(self, word, toWord):
        try:
            # commit anything pending so we can rollback on error
            self.connWrap.syncCommit()

            try:
                self.connWrap.execSql("update wikirelations set word = ? where word = ?", (toWord, word))
                self.connWrap.execSql("update wikiwordattrs set word = ? where word = ?", (toWord, word))
                self.connWrap.execSql("update todos set word = ? where word = ?", (toWord, word))
                self.connWrap.execSql("update wikiwordmatchterms set word = ? where word = ?", (toWord, word))
                self._renameContent(word, toWord)
                self.connWrap.commit()
            except:
                self.connWrap.rollback()
                raise
        except (IOError, OSError, sqlite.Error) as e:
            traceback.print_exc()
            raise DbWriteAccessError(e)


    def deleteWord(self, word, delContent=True):
        """
        delete everything about the wikiword passed in. an exception is raised
        if you try and delete the wiki root node.
        
        delContent -- Should actual content be deleted as well? (Parameter is
                not part of official API)
        """
        if word != self.wikiDocument.getWikiName():
            try:
                self.connWrap.syncCommit()
                try:
                    # don't delete the relations to the word since other
                    # pages still have valid outward links to this page.
                    # just delete the content
    
                    self.deleteChildRelationships(word)
                    self.deleteAttributes(word)
                    self.deleteTodos(word)
                    if delContent:
                        self._deleteContent(word)
                    self.deleteWikiWordMatchTerms(word, syncUpdate=False)
                    self.deleteWikiWordMatchTerms(word, syncUpdate=True)
                    self.connWrap.commit()
                except:
                    self.connWrap.rollback()
                    raise
            except (IOError, OSError, sqlite.Error) as e:
                traceback.print_exc()
                raise DbWriteAccessError(e)
        else:
            raise WikiDataException(_("You cannot delete the root wiki node"),
                    "delete rootPage")


    def setMetaDataState(self, word, state):
        """
        Set the state of meta-data processing for a particular word.
        See Consts.WIKIWORDMETADATA_STATE_*
        """
        try:
            self.connWrap.execSql("update wikiwords set metadataprocessed = ? "
                    "where word = ?", (state, word))
        except (IOError, OSError, sqlite.Error) as e:
            traceback.print_exc()
            raise DbWriteAccessError(e)


    def getMetaDataState(self, word):
        """
        Retrieve meta-data processing state of a particular wiki word.
        """
        try:
            return self.connWrap.execSqlQuerySingleItem("select metadataprocessed "
                    "from wikiwords where word = ?", (word,))
        except (IOError, OSError, sqlite.Error) as e:
            traceback.print_exc()
            raise DbReadAccessError(e)


    def fullyResetMetaDataState(self, state=0):
        """
        Reset state of all wikiwords.
        """
        self.connWrap.execSql("update wikiwords set metadataprocessed = ?",
                (state,))


    _METADATASTATE_NUMCOPARE_TO_SQL = {"==": "=", ">=": "<=", "<=": ">=",
            "!=": "!=", ">": "<", "<": ">"}

    def getWikiPageNamesForMetaDataState(self, state, compare="=="):
        """
        Retrieve a list of all words with a particular meta-data processing
        state.
        """
        sqlCompare = self._METADATASTATE_NUMCOPARE_TO_SQL.get(compare)
        if sqlCompare is None:
            raise InternalError("getWikiPageNamesForMetaDataState: Bad compare '%s'" %
                    compare)

        try:
            return self.connWrap.execSqlQuerySingleColumn("select word "
                    "from wikiwords where metadataprocessed " + sqlCompare +
                    " ?", (state,))
        except (IOError, OSError, sqlite.Error) as e:
            traceback.print_exc()
            raise DbReadAccessError(e)


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


    def getParentRelationships(self, wikiWord):
        """
        get the parent relations to this word
        Function must work for read-only wiki.
        """
#         return self.connWrap.execSqlQuerySingleColumn(
#                 "select word from wikirelations where relation = ?", (wikiWord,))

        # Parents of the real word
        realWord = self.getWikiPageNameForLinkTerm(wikiWord)
        if realWord is None:
            realWord = wikiWord
        try:
            return self.connWrap.execSqlQuerySingleColumn(
                    "select word from wikirelations where relation = ? or "
                    "relation in (select matchterm from wikiwordmatchterms "
                    "where word = ? and "
                    "(wikiwordmatchterms.type & 2) != 0)", (realWord, realWord))
            # Consts.WIKIWORDMATCHTERMS_TYPE_ASLINK == 2


#             # Plus parents of aliases
#             aliases = [v for k, v in self.getAttributesForWord(wikiWord)
#                     if k == u"alias"]
#     
#             for al in aliases:
#                 parents.update(self.connWrap.execSqlQuerySingleColumn(
#                     "select word from wikirelations where relation = ?", (al,)))
#     
#             return list(parents)
        except (IOError, OSError, sqlite.Error) as e:
            traceback.print_exc()
            raise DbReadAccessError(e)



    def getParentlessWikiWords(self):
        """
        get the words that have no parents.
        Function must work for read-only wiki.

        NO LONGER VALID: (((also returns nodes that have files but
        no entries in the wikiwords table.)))
        """
        try:
            # Also working but slower:
#             return self.connWrap.execSqlQuerySingleColumn(
#                     "select word from wikiwords except "
#                     "select wikiwordmatchterms.word "
#                     "from wikiwordmatchterms inner join wikirelations "
#                     "on matchterm == relation where "
#                     "wikirelations.word != wikiwordmatchterms.word and "
#                     "(type & 2) != 0")


            return self.connWrap.execSqlQuerySingleColumn(
                    "select word from wikiwords except "
                    "select wikiwordmatchterms.word from wikiwordmatchterms "
                    "where exists (select 1 from wikirelations where "
                    "wikiwordmatchterms.matchterm == wikirelations.relation and "
                    "wikirelations.word != wikiwordmatchterms.word) and "
                    "(type & 2) != 0")

        except (IOError, OSError, sqlite.Error) as e:
            traceback.print_exc()
            raise DbReadAccessError(e)



    def getUndefinedWords(self):
        """
        List words which are childs of a word but are not defined, neither
        directly nor as alias.
        Function must work for read-only wiki.
        """
        try:
#             return self.connWrap.execSqlQuerySingleColumn(
#                     "select relation from wikirelations "
#                     "except select word from wikiwords "
#                     "except select value from wikiwordattrs where key='alias'")
            return self.connWrap.execSqlQuerySingleColumn(
                    "select relation from wikirelations "
                    "except select word from wikiwords "
                    "except select matchterm from wikiwordmatchterms "
                    "where (type & 2) != 0")
            # Consts.WIKIWORDMATCHTERMS_TYPE_ASLINK == 2


        except (IOError, OSError, sqlite.Error) as e:
            traceback.print_exc()
            raise DbReadAccessError(e)


    def _addRelationship(self, word, rel):
        """
        Add a relationship from word to rel. rel is a tuple (toWord, pos).
        A relation from one word to another is unique and can't be added twice.
        """
        try:
            self.connWrap.execSql(
                    "insert or replace into wikirelations(word, relation, firstcharpos) "
                    "values (?, ?, ?)", (word, rel[0], rel[1]))
        except (IOError, OSError, sqlite.Error) as e:
            traceback.print_exc()
            raise DbWriteAccessError(e)

    def updateChildRelations(self, word, childRelations):
        self.deleteChildRelationships(word)
        self.getExistingWikiWordInfo(word)
        for r in childRelations:
            self._addRelationship(word, r)

    def deleteChildRelationships(self, fromWord):
        try:
            self.connWrap.execSql("delete from wikirelations where word = ?",
                    (fromWord,))
        except (IOError, OSError, sqlite.Error) as e:
            traceback.print_exc()
            raise DbWriteAccessError(e)


    # TODO Maybe optimize
    def getAllSubWords(self, words, level=-1):
        """
        Return all words which are children, grandchildren, etc.
        of words and the words itself. Used by the "export/print Sub-Tree"
        functions. All returned words are real existing words, no aliases.
        Function must work for read-only wiki.
        """
        checkList = [(w, 0)
                for w in (self.getWikiPageNameForLinkTerm(w) for w in words)
                if w is not None]
        checkList.reverse()
        
        resultSet = {}
        result = []

        while len(checkList) > 0:
            toCheck, chLevel = checkList.pop()
            if toCheck in resultSet:
                continue

            result.append(toCheck)
            resultSet[toCheck] = None
            
            if level > -1 and chLevel >= level:
                continue  # Don't go deeper
            
            children = self.getChildRelationships(toCheck, existingonly=True,
                    selfreference=False)
                    
            children = [(self.getWikiPageNameForLinkTerm(c), chLevel + 1)
                    for c in children]
            children.reverse()
            checkList += children

        return result


    def findBestPathFromWordToWord(self, word, toWord):
        """
        finds the shortest path from word to toWord going through the parents.
        word and toWord are included as first/last element. If word == toWord,
        it is included only once as the single element of the list.
        If there is no path from word to toWord, [] is returned
        Function must work for read-only wiki (should hold although function
        writes to temporary table.
        """
        # TODO Aliases supported?
        
        if word == toWord:
            return [word]
        try:
            # Clear temporary table
            self.connWrap.execSql("delete from temppathfindparents")
    
            self.connWrap.execSql("insert into temppathfindparents "+
                    "(word, child, steps) select word, relation, 1 from wikirelations "+
                    "where relation = ?", (word,))

            step = 1
            while True:
                changes = self.connWrap.rowcount
    
                if changes == 0:
                    # No more (grand-)parents
                    return []

                if self.connWrap.execSqlQuerySingleItem("select word from "+
                        "temppathfindparents where word=?", (toWord,)) is not None:
                    # Path found
                    result = [toWord]
                    crumb = toWord
    
                    while crumb != word:
                        crumb = self.connWrap.execSqlQuerySingleItem(
                                "select child from temppathfindparents where "+
                                "word=?", (crumb,))
                        result.append(crumb)

                    # print "findBestPathFromWordToWord result", word, toWord, repr(result)
    
                    # Clear temporary table
                    self.connWrap.execSql("delete from temppathfindparents")

                    return result
    
                self.connWrap.execSql("""
                    insert or ignore into temppathfindparents (word, child, steps)
                    select wikirelations.word, temppathfindparents.word, ? from
                        temppathfindparents inner join wikirelations on
                        temppathfindparents.word == wikirelations.relation where
                        temppathfindparents.steps == ?
                    """, (step+1, step))
    
                step += 1
        
        except (IOError, OSError, sqlite.Error) as e:
            traceback.print_exc()
            raise DbReadAccessError(e)


    def _findNewWordForFile(self, path):
        wikiWord = StringOps.guessBaseNameByFilename(path, self.pagefileSuffix)
        try:
            if self.connWrap.execSqlQuerySingleItem(
                    "select word from wikiwords where word = ?", (wikiWord,)):
                for i in range(20):    # "while True" is too dangerous
                    rand = StringOps.createRandomString(10)

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

    def getAllDefinedWikiPageNames(self):
        """
        Get the names of all wiki pages in the db, no aliases
        Function must work for read-only wiki.
        """
        try:
            return self.connWrap.execSqlQuerySingleColumn(
                    "select word from wikiwords")
        except (IOError, OSError, sqlite.Error) as e:
            traceback.print_exc()
            raise DbReadAccessError(e)


    def getDefinedWikiPageNamesStartingWith(self, thisStr):
        """
        Get the names of all wiki pages in the db starting with  thisStr
        Function must work for read-only wiki.
        """
        try:
            thisStr = sqlite.escapeForGlob(thisStr)

            return self.connWrap.execSqlQuerySingleColumn(
                    "select word from wikiwords where word glob (? || '*')", 
                    (thisStr,))

        except (IOError, OSError, sqlite.Error) as e:
            traceback.print_exc()
            raise DbReadAccessError(e)


    def isDefinedWikiPageName(self, word):
        try:
            return bool(self.connWrap.execSqlQuerySingleItem(
                    "select 1 from wikiwords where word = ?", (word,)))
        except (IOError, OSError, sqlite.Error) as e:
            traceback.print_exc()
            raise DbReadAccessError(e)


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


    def _getCachedWikiPageLinkTermDict(self):
        """
        Function works for read-only wiki.
        """
        class CachedWikiPageLinkTermDict:
            def __init__(self, outer):
                self.outer = outer
                self.cache = {}
                self.cacheNonExistent = set()
                self.cacheComplete = False
                self.resolveCaseNormed = self.outer.resolveCaseNormed
                    

            def get(self, key, default=None):
                if self.cacheComplete:
                    return self.cache.get(key, default)

                if key in self.cache:
                    return self.cache.get(key, default)
                    
                if key in self.cacheNonExistent:
                    return default
                
                value = self._lookup(key)
                
                if value is None and self.resolveCaseNormed:
                    value = self._lookupCaseNormed(key)
                
                if value is not None:
                    self.cache[key] = value
                    return value

                self.cacheNonExistent.add(key)
                return default


            def _lookup(self, key):
                if self.outer.isDefinedWikiPageName(key):
                    return key
                
                try:
                    return self.outer.connWrap.execSqlQuerySingleItem(
                            "select word from wikiwordmatchterms "
                            "where matchterm = ? and (type & 2) != 0 ", (key,))
                    # Consts.WIKIWORDMATCHTERMS_TYPE_ASLINK == 2
                except (IOError, OSError, sqlite.Error) as e:
                    traceback.print_exc()
                    raise DbReadAccessError(e)
                
            def _lookupCaseNormed(self, key):
                try:
                    return self.outer.connWrap.execSqlQuerySingleItem(
                            "select word from wikiwordmatchterms "
                            "where matchtermnormcase = utf8Normcase(?) "
                            "and (type & 2) != 0 ", (key,))
                    # Consts.WIKIWORDMATCHTERMS_TYPE_ASLINK == 2
                except (IOError, OSError, sqlite.Error) as e:
                    traceback.print_exc()
                    raise DbReadAccessError(e)


            def keys(self):
                # This function is not affected by self.resolveCaseNormed
                # because in theory it would have to return all possible
                # lowercase-uppercase-combinations of a word to be
                # accurate
                if not self.cacheComplete:
                    cacheDict = dict(self.outer.connWrap.execSqlQuery(
                            "select word, word from wikiwords union "
                            "select matchterm, word from wikiwordmatchterms "
                            "where (type & 2) != 0 and not matchterm in "
                            "(select word from wikiwords)"))
                    # Consts.WIKIWORDMATCHTERMS_TYPE_ASLINK == 2

                    if not self.resolveCaseNormed:
                        # Cache can't be complete with case normed resolving
                        # because above
                        self.cacheComplete = True
                        self.cache = cacheDict

                else:
                    cacheDict = self.cache

                return list(cacheDict)

        try:
            if self.cachedWikiPageLinkTermDict is None:
                self.cachedWikiPageLinkTermDict = CachedWikiPageLinkTermDict(self)

            return self.cachedWikiPageLinkTermDict
        except (IOError, OSError, sqlite.Error) as e:
            traceback.print_exc()
            raise DbReadAccessError(e)


#     def _getCachedWikiPageLinkTermDict(self):
#         """
#         Function works for read-only wiki.
#         """
#         try:
#             if self.cachedWikiPageLinkTermDict is None:
#                 self.cachedWikiPageLinkTermDict = dict(self.connWrap.execSqlQuery(
#                         "select word, word from wikiwords union "
#                         "select matchterm, word from wikiwordmatchterms "
#                         "where (type & 2) != 0 and not matchterm in "
#                         "(select word from wikiwords)"))
#                 # Consts.WIKIWORDMATCHTERMS_TYPE_ASLINK == 2
# 
#             return self.cachedWikiPageLinkTermDict
#         except (IOError, OSError, sqlite.Error), e:
#             traceback.print_exc()
#             raise DbReadAccessError(e)


    def _getAllWikiFileNamesFromDisk(self):   # Used for rebuilding wiki
        try:
            files = glob.glob(join(self.dataDir, '*' + self.pagefileSuffix))

            return [StringOps.pathDec(basename(fn)) for fn in files]

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


    def isDefinedWikiLinkTerm(self, word):
        "check if a word is a valid wikiword (page name or alias)"
        return bool(self.getWikiPageNameForLinkTerm(word))


#     # TODO More reliably esp. for aliases
#     def isDefinedWikiWord(self, word):
#         "check if a word is a valid wikiword (page name or alias)"
#         return self._getCachedWikiPageLinkTermDict().has_key(word)


    def getAllProducedWikiLinks(self):
        """
        Return all links stored by production (in contrast to resolution)
        Function must work for read-only wiki.
        """
        return list(self._getCachedWikiPageLinkTermDict().keys())


    def getWikiPageLinkTermsStartingWith(self, thisStr, caseNormed=None):
        """
        Get the list of wiki page link terms (page names or aliases)
        starting with thisStr. Used for autocompletion.
        caseNormed -- Iff True also terms with different case than given thisStr
                are taken into account. If None (default) the parameter value
                is taken from self.resolveCaseNormed
        """
        if caseNormed is None:
            caseNormed = self.resolveCaseNormed
        
        if caseNormed:
            thisStr = sqlite.escapeForGlob(thisStr.lower())   # TODO More general normcase function

            try:
                return self.connWrap.execSqlQuerySingleColumn(
                        "select matchterm from wikiwordmatchterms "
                        "where matchtermnormcase glob (? || '*') and "
                        "(type & 2) != 0", 
                        (thisStr,))
                # Consts.WIKIWORDMATCHTERMS_TYPE_ASLINK == 2

            except (IOError, OSError, sqlite.Error) as e:
                traceback.print_exc()
                raise DbReadAccessError(e)

        else:
            try:
                thisStr = sqlite.escapeForGlob(thisStr)

                return self.connWrap.execSqlQuerySingleColumn(
                        "select matchterm from wikiwordmatchterms "
                        "where matchterm glob (? || '*') and "
                        "(type & 2) != 0 union "
                        "select word from wikiwords where word glob (? || '*')", 
                        (thisStr,thisStr))
                # Consts.WIKIWORDMATCHTERMS_TYPE_ASLINK == 2
                
                # To ensure that at least all real wikiwords are found,
                # the wikiwords table is also read
                
            except (IOError, OSError, sqlite.Error) as e:
                traceback.print_exc()
                raise DbReadAccessError(e)


    def getWikiPageNamesModifiedWithin(self, startTime, endTime):
        """
        Function must work for read-only wiki.
        startTime and endTime are floating values as returned by time.time()
        startTime is inclusive, endTime is exclusive
        """
        try:
            return self.connWrap.execSqlQuerySingleColumn(
                    "select word from wikiwords where modified >= ? and "
                    "modified < ?",
                    (startTime, endTime))
        except (IOError, OSError, sqlite.Error) as e:
            traceback.print_exc()
            raise DbReadAccessError(e)


    _STAMP_TYPE_TO_FIELD = {
            0: "modified",
            1: "created"
        }

    def getTimeMinMax(self, stampType):
        """
        Return the minimal and maximal timestamp values over all wiki words
        as tuple (minT, maxT) of float time values.
        A time value of 0.0 is not taken into account.
        If there are no wikiwords with time value != 0.0, (None, None) is
        returned.
        
        stampType -- 0: Modification time, 1: Creation, 2: Last visit
        """
        field = self._STAMP_TYPE_TO_FIELD.get(stampType)
        if field is None:
            # Visited not supported yet
            return (None, None)

        try:
            result = self.connWrap.execSqlQuery(
                    ("select min(%s), max(%s) from wikiwords where %s > 0") %
                    (field, field, field))
        except (IOError, OSError, sqlite.Error) as e:
            traceback.print_exc()
            raise DbReadAccessError(e)

        if len(result) == 0:
            # No matching wiki words found
            return (None, None)
        else:
            return tuple(result[0])


    def getWikiPageNamesBefore(self, stampType, stamp, limit=None):
        """
        Get a list of tuples of wiki words and dates related to a particular
        time before stamp.
        
        stampType -- 0: Modification time, 1: Creation, 2: Last visit
        limit -- How much words to return or None for all
        """
        field = self._STAMP_TYPE_TO_FIELD.get(stampType)
        if field is None:
            # Visited not supported yet
            return []
            
        if limit is None:
            limit = -1
            
        try:
            return self.connWrap.execSqlQuery(
                    ("select word, %s from wikiwords where %s > 0 and %s < ? "
                    "order by %s desc limit ?") %
                    (field, field, field, field), (stamp, limit))
        except (IOError, OSError, sqlite.Error) as e:
            traceback.print_exc()
            raise DbReadAccessError(e)


    def getWikiPageNamesAfter(self, stampType, stamp, limit=None):
        """
        Get a list of of tuples of wiki words and dates related to a particular
        time after OR AT stamp.
        
        stampType -- 0: Modification time, 1: Creation, 2: Last visit
        limit -- How much words to return or None for all
        """
        field = self._STAMP_TYPE_TO_FIELD.get(stampType)
        if field is None:
            # Visited not supported yet
            return []
            
        if limit is None:
            limit = -1

        try:
            return self.connWrap.execSqlQuery(
                    ("select word, %s from wikiwords where %s > ? "
                    "order by %s asc limit ?") %
                    (field, field, field), (stamp, limit))
        except (IOError, OSError, sqlite.Error) as e:
            traceback.print_exc()
            raise DbReadAccessError(e)


    def getFirstWikiPageName(self):
        """
        Returns the name of the "first" wiki word. See getNextWikiPageName()
        for details. Returns either an existing wiki word or None if no
        wiki words in database.
        Function must work for read-only wiki.
        """
        try:
            return self.connWrap.execSqlQuerySingleItem(
                    "select word from wikiwords "
                    "order by word limit 1")
        except (IOError, OSError, sqlite.Error) as e:
            traceback.print_exc()
            raise DbReadAccessError(e)


    def getNextWikiPageName(self, currWord):
        """
        Returns the "next" wiki word after currWord or None if no
        next word exists. If you begin with the first word returned
        by getFirstWikiPageName() and then use getNextWikiPageName() to
        go to the next word until no more words are available
        and if the list of existing wiki words is not modified during
        iteration, it is guaranteed that you have visited all real
        wiki words (no aliases) then.
        currWord  doesn't have to be an existing word itself.
        Function must work for read-only wiki.
        """
        try:
            return self.connWrap.execSqlQuerySingleItem(
                    "select word from wikiwords where "
                    "word > ? order by word limit 1", (currWord,))
        except (IOError, OSError, sqlite.Error) as e:
            traceback.print_exc()
            raise DbReadAccessError(e)


    # ---------- Attribute cache handling ----------

    def getAttributeNames(self):
        """
        Return all attribute names not beginning with "global."
        Function must work for read-only wiki.
        """
        try:
            return self.connWrap.execSqlQuerySingleColumn(
                    "select distinct(key) from wikiwordattrs "
                    "where key not glob 'global.*'")
        except (IOError, OSError, sqlite.Error) as e:
            traceback.print_exc()
            raise DbReadAccessError(e)


    # TODO More efficient? (used by autocompletion)
    def getAttributeNamesStartingWith(self, startingWith):
        """
        Function must work for read-only wiki.
        """
        try:
            return self.connWrap.execSqlQuerySingleColumn(
                    "select distinct(key) from wikiwordattrs "
                    "where key glob (? || '*')",
                    (sqlite.escapeForGlob(startingWith),))   #  order by key")
#             names = self.connWrap.execSqlQuerySingleColumn(
#                     "select distinct(key) from wikiwordattrs")   #  order by key")
        except (IOError, OSError, sqlite.Error) as e:
            traceback.print_exc()
            raise DbReadAccessError(e)

#         return [name for name in names if name.startswith(startingWith)]



    def getGlobalAttributes(self):
        """
        Function must work for read-only wiki.
        """
        if not self.cachedGlobalAttrs:
            return self.updateCachedGlobalAttrs()

        return self.cachedGlobalAttrs


    def getDistinctAttributeValues(self, key):
        """
        Function must work for read-only wiki.
        """
        try:
            return self.connWrap.execSqlQuerySingleColumn(
                    "select distinct(value) from wikiwordattrs where key = ? ",
                    (key,))
        except (IOError, OSError, sqlite.Error) as e:
            traceback.print_exc()
            raise DbReadAccessError(e)
    
    
    def getAttributeTriples(self, word, key, value,
            withFields=("word", "key", "value")):
        """
        Function must work for read-only wiki.
        word, key and value can either be unistrings or None.
        """
        if withFields is None:
            withFields = ()

        cols = []
        for field in withFields:
            if field in ("word", "key", "value"):
                cols.append(field)
        
        if len(cols) == 0:
            return []
        
        colTxt = ", ".join(cols)
        
        conjunction = StringOps.Conjunction("where ", "and ")
        
        query = "select distinct " + colTxt + " from wikiwordattrs "
        parameters = []
        
        if word is not None:
            parameters.append(word)
            query += conjunction() + "word = ? "
        
        if key is not None:
            parameters.append(key)
            query += conjunction() + "key = ? "

        if value is not None:
            parameters.append(value)
            query += conjunction() + "value = ? "

        try:
            return self.connWrap.execSqlQuery(query, tuple(parameters))
        except (IOError, OSError, sqlite.Error) as e:
            traceback.print_exc()
            raise DbReadAccessError(e)


    def getWordsForAttributeName(self, key):
        """
        Function must work for read-only wiki.
        """
        try:
            return self.connWrap.execSqlQuerySingleColumn(
                    "select distinct(word) from wikiwordattrs where key = ? ",
                    (key,))
        except (IOError, OSError, sqlite.Error) as e:
            traceback.print_exc()
            raise DbReadAccessError(e)


    def getAttributesForWord(self, word):
        """
        Returns list of tuples (key, value) of key and value
        of all attributes for word.
        Function must work for read-only wiki.
        """
        try:
            return self.connWrap.execSqlQuery("select key, value "+
                        "from wikiwordattrs where word = ?", (word,))
        except (IOError, OSError, sqlite.Error) as e:
            traceback.print_exc()
            raise DbReadAccessError(e)

            
    def _setAttribute(self, word, key, value):
        try:
            self.connWrap.execSql(
                    "insert into wikiwordattrs(word, key, value) "
                    "values (?, ?, ?)", (word, key, value))
        except (IOError, OSError, sqlite.Error) as e:
            traceback.print_exc()
            raise DbWriteAccessError(e)


    def updateAttributes(self, word, attrs):
        self.deleteAttributes(word)
        self.getExistingWikiWordInfo(word)
        for k in list(attrs.keys()):
            values = attrs[k]
            for v in values:
                self._setAttribute(word, k, v)
#                 if k == "alias":
#                     self.setAsAlias(v)

        self.cachedGlobalAttrs = None   # reset global attributes cache


    def updateCachedGlobalAttrs(self):
        """
        TODO: Should become part of public API!
        Function must work for read-only wiki.
        """
        try:
            data = self.connWrap.execSqlQuery("select key, value from wikiwordattrs "
                    "where key glob 'global.*'")
        except (IOError, OSError, sqlite.Error) as e:
            traceback.print_exc()
            raise DbReadAccessError(e)

        globalMap = {}
        for (key, val) in data:
            globalMap[key] = val

        self.cachedGlobalAttrs = globalMap

        return globalMap


    def deleteAttributes(self, word):
        try:
            self.connWrap.execSql("delete from wikiwordattrs where word = ?",
                    (word,))
        except (IOError, OSError, sqlite.Error) as e:
            traceback.print_exc()
            raise DbWriteAccessError(e)

    # TODO: 2.3: remove "property"-compatibility
    getPropertyNames = getAttributeNames  
    getPropertyNamesStartingWith = getAttributeNamesStartingWith
    getGlobalProperties = getGlobalAttributes
    getDistinctPropertyValues = getDistinctAttributeValues
    getPropertyTriples = getAttributeTriples
    getWordsForPropertyName = getWordsForAttributeName
    getPropertiesForWord = getAttributesForWord
    updateProperties = updateAttributes
    updateCachedGlobalProps = updateCachedGlobalAttrs
    deleteProperties = deleteAttributes


    # ---------- Alias handling ----------

    def setResolveCaseNormed(self, cn):
        """
        Set if non-existing wiki words should be resolved to an existing
        word which only differs in case when calling getWikiPageNameForLinkTerm().
        
        Additionally the default setting of the "caseNormed" parameter
        is set to this value for the functions getWikiPageLinkTermsStartingWith()
        """
        if cn == self.resolveCaseNormed:
            return  # Nothing to change

        self.resolveCaseNormed = cn
        # Clear cache which must be rebuilt differently depending on the setting
        self.cachedWikiPageLinkTermDict = None


    def getWikiPageNameForLinkTerm(self, alias):
        """
        Return real page name for wiki page link term which may be
        a real page name or an alias. Returns None if term not found.
        Function should only be called by WikiDocument as some methods
        of unaliasing must be performed in WikiDocument.
        Function must work for read-only wiki.
        """
        return self._getCachedWikiPageLinkTermDict().get(alias, None)


    # TODO: 2.4: Remove compatibility definitions
    getAllDefinedContentNames = getAllDefinedWikiPageNames
    isDefinedWikiPage = isDefinedWikiPageName
    refreshDefinedContentNames = refreshWikiPageLinkTerms
    getUnAliasedWikiWord = getWikiPageNameForLinkTerm
    isDefinedWikiLink = isDefinedWikiLinkTerm
    getWikiWordsModifiedWithin = getWikiPageNamesModifiedWithin
    getWikiWordsBefore = getWikiPageNamesBefore
    getWikiWordsAfter = getWikiPageNamesAfter
    getFirstWikiWord = getFirstWikiPageName
    getNextWikiWord = getNextWikiPageName
    getWikiWordsForMetaDataState = getWikiPageNamesForMetaDataState
    validateFileSignatureForWord = validateFileSignatureForWikiPageName
    refreshFileSignatureForWord = refreshFileSignatureForWikiPageName
    def getWikiLinksStartingWith(self, thisStr, includeAliases=False,
            caseNormed=False):
        """
        For compatibility. Use getWikiPageLinkTermsStartingWith() instead.
        """
        return self.getWikiPageLinkTermsStartingWith(thisStr, caseNormed)


    # ---------- Todo cache handling ----------

    def getTodos(self):
        """
        Function must work for read-only wiki.
        Returns list of tuples (word, todoKey, todoValue).
        """
        try:
#             return self.connWrap.execSqlQuery("select word, todo from todos")
            return self.connWrap.execSqlQuery("select word, key, value from todos")

        except (IOError, OSError, sqlite.Error) as e:
            traceback.print_exc()
            raise DbReadAccessError(e)


#     def getTodosForWord(self, word):
#         """
#         Returns list of all todo items of word.
#         Function must work for read-only wiki.
#         """
#         try:
#             return self.connWrap.execSqlQuerySingleColumn("select todo from todos "
#                     "where word = ?", (word,))
#         except (IOError, OSError, sqlite.Error), e:
#             traceback.print_exc()
#             raise DbReadAccessError(e)


    def updateTodos(self, word, todos):
        self.deleteTodos(word)
        self.getExistingWikiWordInfo(word)
        for t in todos:
            self._addTodo(word, t)


    def _addTodo(self, word, todo):
        try:
            self.connWrap.execSql("insert into todos(word, key, value) values (?, ?, ?)",
                    (word, todo[0], todo[1]))
        except (IOError, OSError, sqlite.Error) as e:
            traceback.print_exc()
            raise DbWriteAccessError(e)


    def deleteTodos(self, word):
        try:
            self.connWrap.execSql("delete from todos where word = ?", (word,))
        except (IOError, OSError, sqlite.Error) as e:
            traceback.print_exc()
            raise DbWriteAccessError(e)


    # ---------- Wikiword matchterm cache handling ----------

    def getWikiWordMatchTermsWith(self, thisStr, orderBy=None, descend=False):
        "get the list of match terms with thisStr in them."
        thisStr = sqlite.escapeForGlob(thisStr.lower())   # TODO More general normcase function

        if orderBy == "visited":
            try:
                result1 = self.connWrap.execSqlQuery(
                        "select matchterm, type, wikiwordmatchterms.word, "
                        "firstcharpos, charlength, visited "
                        "from wikiwordmatchterms inner join wikiwords "
                        "on wikiwordmatchterms.word = wikiwords.word where "
                        "matchtermnormcase glob (? || '*')", (thisStr,))
    
                result2 = self.connWrap.execSqlQuery(
                        "select matchterm, type, wikiwordmatchterms.word, "
                        "firstcharpos, charlength, visited "
                        "from wikiwordmatchterms inner join wikiwords "
                        "on wikiwordmatchterms.word = wikiwords.word where "
                        "not matchtermnormcase glob (? || '*') "
                        "and matchtermnormcase glob ('*' || ? || '*')",
                        (thisStr, thisStr))
            except (IOError, OSError, sqlite.Error) as e:
                traceback.print_exc()
                raise DbReadAccessError(e)
        else:
            try:
                result1 = self.connWrap.execSqlQuery(
                        "select matchterm, type, word, firstcharpos, charlength "
                        "from wikiwordmatchterms where "
                        "matchtermnormcase glob (? || '*')", (thisStr,))
    
                result2 = self.connWrap.execSqlQuery(
                        "select matchterm, type, word, firstcharpos, charlength "
                        "from wikiwordmatchterms where "
                        "not matchtermnormcase glob (? || '*') "
                        "and matchtermnormcase glob ('*' || ? || '*')",
                        (thisStr, thisStr))
            except (IOError, OSError, sqlite.Error) as e:
                traceback.print_exc()
                raise DbReadAccessError(e)

        coll = self.wikiDocument.getCollator()

        coll.sortByFirst(result1)
        coll.sortByFirst(result2)
        
        if orderBy == "visited":
            result1.sort(key=lambda k: k[5], reverse=descend)
            result2.sort(key=lambda k: k[5], reverse=descend)
        else:
            if descend:
                result1.reverse()
                result2.reverse()

        return result1 + result2


    def updateWikiWordMatchTerms(self, word, wwmTerms, syncUpdate=False):
        self.deleteWikiWordMatchTerms(word, syncUpdate=syncUpdate)
        self.getExistingWikiWordInfo(word)
        for t in wwmTerms:
            assert t[2] == word
            self._addWikiWordMatchTerm(t)


    def _addWikiWordMatchTerm(self, wwmTerm):
        matchterm, typ, word, firstcharpos, charlength = wwmTerm
        try:
            # TODO Check for name collisions
            self.connWrap.execSql("insert into wikiwordmatchterms(matchterm, "
                    "type, word, firstcharpos, charlength, matchtermnormcase) "
                    "values (?, ?, ?, ?, ?, ?)",
                    (matchterm, typ, word, firstcharpos, charlength,
                    matchterm.lower()))
        except (IOError, OSError, sqlite.Error) as e:
            traceback.print_exc()
            raise DbWriteAccessError(e)


    def deleteWikiWordMatchTerms(self, word, syncUpdate=False):
        if syncUpdate:
            addSql = " and (type & 16) != 0"
        else:
            addSql = " and (type & 16) == 0"
            # Consts.WIKIWORDMATCHTERMS_TYPE_SYNCUPDATE == 16

        try:
            self.connWrap.execSql("delete from wikiwordmatchterms where "
                    "word = ?" + addSql, (word,))
            self.cachedWikiPageLinkTermDict = None
        except (IOError, OSError, sqlite.Error) as e:
            traceback.print_exc()
            raise DbWriteAccessError(e)


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
            datablock = StringOps.loadEntireFile(join(self.dataDir, filePath))
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

        return fileContentToUnicode(StringOps.lineendToInternal(datablock))



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


            if isinstance(newdata, str):
                newdata = StringOps.BOM_UTF8 + newdata.encode("utf-8",
                        "surrogateescape")

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


    def checkCapability(self, capkey):
        """
        Check the capabilities of this WikiData implementation.
        The capkey names the capability, the function returns normally
        a version number or None if not supported
        Function must work for read-only wiki.
        """
        return WikiData._CAPABILITIES.get(capkey, None)


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


    def setDbSettingsValue(self, key, value):
        assert isinstance(value, str)
        self.connWrap.execSql("insert or replace into settings(key, value) "
                "values (?, ?)", (key, value))

    def getDbSettingsValue(self, key, default=None):
        return DbStructure.getSettingsValue(self.connWrap, key, default)


    def setPresentationBlock(self, word, datablock):
        """
        Save the presentation datablock (a byte string) for a word to
        the database.
        """
        try:
            self.connWrap.execSql(
                    "update wikiwords set presentationdatablock = ? where "
                    "word = ?", (sqlite.Binary(datablock), word))
        except (IOError, OSError, sqlite.Error) as e:
            traceback.print_exc()
            raise DbWriteAccessError(e)


    def getPresentationBlock(self, word):
        """
        Returns the presentation datablock (a byte string).
        The function may return either an empty string or a valid datablock
        Function must work for read-only wiki.
        """
        try:
            return self.connWrap.execSqlQuerySingleItem(
                    "select presentationdatablock from wikiwords where word = ?",
                    (word,))
        except (IOError, OSError, sqlite.Error) as e:
            traceback.print_exc()
            raise DbReadAccessError(e)

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

        
    def close(self):
        """
        Function must work for read-only wiki.
        """
        try:
            self.connWrap.syncCommit()
            self.connWrap.close()
    
            self.connWrap = None
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


    def commit(self):
        """
        Do not call from this class, only from outside to handle errors.
        """
        try:
            self.connWrap.commit()
        except (IOError, OSError, sqlite.Error) as e:
            traceback.print_exc()
            raise DbWriteAccessError(e)


    def rollback(self):
        """
        Do not call from this class, only from outside to handle errors.
        """
        try:
            self.connWrap.rollback()
        except (IOError, OSError, sqlite.Error) as e:
            traceback.print_exc()
            raise DbWriteAccessError(e)


    def vacuum(self):
        """
        Reorganize the database, free unused space.
        
        Must be implemented if checkCapability returns a version number
        for "compactify".        
        """
        try:
            self.connWrap.syncCommit()
            self.connWrap.execSql("vacuum")
        except (IOError, OSError, sqlite.Error) as e:
            traceback.print_exc()
            raise DbWriteAccessError(e)


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
