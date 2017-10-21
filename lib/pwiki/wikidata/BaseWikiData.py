"""

Defines a number of base classes which contain code shared across
the different database backends.


To make this work the old "wikiwordcontent" table in the compact_sqlite
backend has been renamed to "wikiwords" to be consistent with the others


----

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
import wx

from time import time, localtime, strftime
import datetime
import string, glob, traceback
import shutil


import hashlib
import pickle

import Consts
from pwiki.WikiExceptions import *
from pwiki import SearchAndReplace


from pwiki.StringOps import getBinCompactForDiff, applyBinCompact, longPathEnc, \
        longPathDec, binCompactToCompact, fileContentToUnicode, utf8Enc, utf8Dec, \
        uniWithNone, loadEntireTxtFile, Conjunction, lineendToInternal
from pwiki.StringOps import loadEntireFile, writeEntireFile, \
        iterCompatibleFilename, getFileSignatureBlock, guessBaseNameByFilename, \
        createRandomString, pathDec


import pwiki.sqlite3api as sqlite
import traceback


class BasicWikiData:
    """
    Code shared across all db backends

    """

    # Cache for wikiterms, format: (len, dict(matchtermsnormcase -> word))
    definedWikiMatchTerms = (0, {})


    def checkDatabaseFormat(self):
        raise NotImplementedError


    def connect(self):
        raise NotImplementedError


    def getDbFilename(self):
        """Returns the current database filename"""
        dbFile = self.wikiDocument.getWikiConfig().get("wiki_db", 
                "db_filename", "").strip()
                
        if (dbFile == ""):
            dbFile = self.dbFilename

        return dbFile


    def CreateAndConnectToDb(self, DbStructure):
        dbfile = join(self.dataDir, self.getDbFilename())

        self.DbStructure = DbStructure

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

    def backupDatabase(self):
        # Create a db backup if requested
        dbBackupPath = join(self.dataDir, strftime("%Y-%m-%d_%h-%M"))

        answer = wx.MessageBox(_("WikidPad can make a backup of "
                "you current database. Press OK to continue or "
                "CANCEL to skip.\r\r"
                "Backup will be created at: \r\r{0}".format(dbBackupPath)), 
                _('Backup database?'),
                wx.OK | wx.CANCEL | wx.ICON_QUESTION)
        if answer == wx.OK:
            dbBackupPath = join(self.dataDir, strftime("%Y-%m-%d_%H-%M"))

            for name in self.getDbPaths():
                dbFile = join(self.dataDir, name)
                dbBackupFile = join(dbBackupPath, name)

            if not os.path.exists(dbBackupPath):
                os.mkdir(dbBackupPath)

            shutil.copyfile(dbFile, dbBackupFile)


    def initSqlite(self, app):
        sqliteInitFlag = app.sqliteInitFlag
        globalConfig = app.getGlobalConfig()
        portable = app.isInPortableMode()
        globalConfigSubDir = app.getGlobalConfigSubDir()

        # Set temporary directory if this is first sqlite use after prog. start
        if not sqliteInitFlag:
            if globalConfig.getboolean("main", "tempHandling_preferMemory",
                    False):
                tempMode = "memory"
            else:
                tempMode = globalConfig.get("main", "tempHandling_tempMode",
                        "system")

            if tempMode == "auto":
                if portable:
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
                        utf8Enc(globalConfigSubDir)[0])
                self.connWrap.execSql("pragma temp_store = 1")
            else:   # tempMode == u"system"
                self.connWrap.execSql("pragma temp_store_directory = ''")
                self.connWrap.execSql("pragma temp_store = 1")

            app.sqliteInitFlag = True


        self.caseInsensitiveWikiWords = self.wikiDocument.getWikiConfig().\
                getboolean("main", "caseInsensitiveWikiWords", False)



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
        raise NotImplementedError


    def setContent(self, word, content, moddate = None, creadate = None):
        raise NotImplementedError


    def _renameContent(self, oldWord, newWord):
        raise NotImplementedError


    def _deleteContent(self, word):
        raise NotImplementedError


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
        except (IOError, OSError, sqlite.Error, ValueError) as e:
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
        except (IOError, OSError, sqlite.Error, ValueError) as e:
            traceback.print_exc()
            raise DbReadAccessError(e)

        try:
            if len(data) < 1:
                raise WikiFileNotFoundException
            else:
                self.connWrap.execSql("update wikiwords set modified = ?, "
                        "created = ?, visited = ? where word = ?",
                        (moddate, creadate, visitdate, word))
        except (IOError, OSError, sqlite.Error, ValueError) as e:
            traceback.print_exc()
            raise DbWriteAccessError(e)


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
        except (IOError, OSError, sqlite.Error, ValueError) as e:
            traceback.print_exc()
            raise DbWriteAccessError(e)


    def deleteWord(self, word, delContent=True):
        """
        delete everything about the wikiword passed in. an exception is raised
        if you try and delete the wiki root node.
        
        delContent -- Should actual content be deleted as well? (Parameter is
                not part of official API)
        """
        raise NotImplementedError


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
            except (IOError, OSError, sqlite.Error, ValueError) as e:
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
        except (IOError, OSError, sqlite.Error, ValueError) as e:
            traceback.print_exc()
            raise DbWriteAccessError(e)


    def getMetaDataState(self, word):
        """
        Retrieve meta-data processing state of a particular wiki word.
        """
        try:
            return self.connWrap.execSqlQuerySingleItem("select metadataprocessed "
                    "from wikiwords where word = ?", (word,))
        except (IOError, OSError, sqlite.Error, ValueError) as e:
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


    def validateFileSignatureForWikiPageName(self, word, 
            setMetaDataDirty=False, refresh=False):
        """
        Returns True if file signature stored in DB matches the file
        containing the content, False otherwise.

        For compact_sqlite it always returns True.
        """
        return True


    def refreshFileSignatureForWikiPageName(self, word):
        """
        Sets file signature to match current file.
        """
        pass

    def setWikiWordReadOnly(self, word, flag):
        """
        Set readonly flag of a wikiword. Warning: Methods in WikiData do not
        respect this flag.
        word -- wikiword to modify (must exist, aliases must be resolved
                beforehand)
        flag -- integer value. 0: Readwrite; &1: Readonly
        """
        try:
            data = self.connWrap.execSqlQuery("select word from "
                    "wikiwords where word = ?", (word,))
        except (IOError, OSError, sqlite.Error, ValueError) as e:
            traceback.print_exc()
            raise DbReadAccessError(e)

        try:
            if len(data) < 1:
                raise WikiFileNotFoundException
            else:
                self.connWrap.execSql("update wikiwords set readonly = ? "
                        "where word = ?", (flag, word))
        except (IOError, OSError, sqlite.Error, ValueError) as e:
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
        except (IOError, OSError, sqlite.Error, ValueError) as e:
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


        sql = "select word{0} from wikiwords where word = ?".format(addFields)

        try:
            if len(withFields) > 0:
                dbresult = [tuple(c(item) for c, item in zip(converters, row))
                        for row in self.connWrap.execSqlQuery(sql, (wikiWord,))]
            else:
                dbresult = self.connWrap.execSqlQuerySingleColumn(sql, (wikiWord,))
            
            if len(dbresult) == 0:
                raise WikiWordNotFoundException(wikiWord)
            
            return dbresult[0]
        except (IOError, OSError, sqlite.Error, ValueError) as e:
            traceback.print_exc()
            raise DbReadAccessError(e)


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
                # "modified" isn't a field of wikirelations. We need
                # some SQL magic to retrieve the modification date
                addFields += (", ifnull((select modified from wikiwords "
                        "where wikiwords.word = relation or "
                        "wikiwords.word = (select word from wikiwordmatchterms "
                        "where wikiwordmatchterms.matchterm = relation and "
                        "(wikiwordmatchterms.type & 2) != 0 limit 1)), 0.0)")

                converters.append(float)


        sql = "select relation{0} from wikirelations where word = ?".format(
                addFields)

        if not selfreference:
            if self.caseInsensitiveWikiWords:
                sql += " and utf8Normcase(relation) != utf8Normcase(word)"
            else:
                sql += " and relation != word"

        if existingonly:
            # filter to only words in wikiwords or aliases
#             sql += " and (exists (select word from wikiwords "+\
#                     "where word = relation) or exists "+\
#                     "(select value from wikiwordattrs "+\
#                     "where value = relation and key = 'alias'))"
            if self.caseInsensitiveWikiWords:
                sql += (" and (exists (select 1 from wikiwords "
                        "where utf8Normcase(word) = utf8Normcase(relation)) or exists "
                        "(select 1 from wikiwordmatchterms "
                        "where wikiwordmatchterms.matchtermnormcase = utf8Normcase(relation) and "
                        "(wikiwordmatchterms.type & 2) != 0))")
            else:
                sql += (" and (exists (select 1 from wikiwords "
                        "where word = relation) or exists "
                        "(select 1 from wikiwordmatchterms "
                        "where wikiwordmatchterms.matchterm = relation and "
                        "(wikiwordmatchterms.type & 2) != 0))")
            # Consts.WIKIWORDMATCHTERMS_TYPE_ASLINK == 2


        try:
            if len(withFields) > 0:
                return self.connWrap.execSqlQuery(sql, (wikiWord,))
            else:
                return self.connWrap.execSqlQuerySingleColumn(sql, (wikiWord,))
        except (IOError, OSError, sqlite.Error, ValueError) as e:
            traceback.print_exc()
            raise DbReadAccessError(e)


    def getParentRelationships(self, wikiWord):
        """
        get the parent relations to this word
        Function must work for read-only wiki.
        """
        # Parents of the real word
        realWord = self.getWikiPageNameForLinkTerm(wikiWord)
        if realWord is None:
            realWord = wikiWord
        try:
            if self.caseInsensitiveWikiWords:
                return self.connWrap.execSqlQuerySingleColumn(
                        "select word from wikirelations where relation = ? or "
                        "relation in (select matchtermnormcase from wikiwordmatchterms "
                        "where utf8Normcase(word) = ? and "
                        "(wikiwordmatchterms.type & 2) != 0)", (realWord, realWord.lower()))
            else:
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


            if self.caseInsensitiveWikiWords:
                return self.connWrap.execSqlQuerySingleColumn(
                        "select word from wikiwords except "
                        "select wikiwordmatchterms.word from wikiwordmatchterms "
                        "where exists (select 1 from wikirelations where "
                        "wikiwordmatchterms.matchtermnormcase == utf8Normcase(wikirelations.relation) and "
                        "wikirelations.word != wikiwordmatchterms.word) and "
                        "(type & 2) != 0")
            else:
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

            if self.caseInsensitiveWikiWords:
                return self.connWrap.execSqlQuerySingleColumn(
                        # ? more efficient
                        "select relation from wikirelations where "
                        "lower(relation) not in (select lower(word) "
                        "from wikiwords) and lower(relation) not in "
                        "(select matchtermnormcase from wikiwordmatchterms "
                        "where (type & 2) != 0)")
            else:
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
        writes to temporary table).
        """
        # TODO Optimise? nocase support
        
        if word == toWord:
            return [word]
        try:
            # Clear temporary table
            self.connWrap.execSql("delete from temppathfindparents")
    
            self.connWrap.execSql("""insert or ignore into temppathfindparents 
                    (word, child, steps) select word, relation, 1 from 
                    wikirelations where relation in (select 
                    wikiwordmatchterms.matchterm from wikiwordmatchterms 
                    where word = ?)""", (word,))

            # temppathfindparents should now contain a list of all the
            # words/aliases that link to our desired word

            step = 1
            while True:
                changes = self.connWrap.rowcount
    
                if changes == 0:
                    # No more (grand-)parents
                    return []

                if self.connWrap.execSqlQuerySingleItem("select word from "
                        "temppathfindparents where word=?", (toWord,)
                        ) is not None:

                    # Path found
                    result = [toWord]
                    crumb = toWord
    
                    while crumb != word:

                        self.connWrap.execSqlQuerySingleItem(
                                "select child from temppathfindparents")

                        crumb = self.connWrap.execSqlQuerySingleItem(
                                "select child from temppathfindparents where "
                                "word in (select wikiwordmatchterms.matchterm "
                                "from wikiwordmatchterms where "
                                "wikiwordmatchterms.matchterm = ?)", (crumb,))

                        result.append(crumb)

                        if self.connWrap.execSqlQuerySingleItem(
                                """select matchterm from wikiwordmatchterms 
                                where word = ? and matchterm = ?""", 
                                (word, crumb)) is not None:
                            # result[-1] is not necessarily == word
                            # it could be an alias
                            break

                        if crumb is None:
                            # Somethings gone wrong (this shouldn't happen)
                            return []

                    # print "findBestPathFromWordToWord result", word, toWord, repr(result)
    
                    # Clear temporary table
                    self.connWrap.execSql("delete from temppathfindparents")

                    return result

                # To handle aliases we add all matchterms to the list to search
                self.connWrap.execSql("""
                    insert or ignore into temppathfindparents (word, child, 
                    steps) select wikiwordmatchterms.matchterm, 
                    temppathfindparents.child, temppathfindparents.steps 
                    from temppathfindparents inner join wikiwordmatchterms 
                    where (wikiwordmatchterms.word = temppathfindparents.word 
                    and wikiwordmatchterms.matchterm != 
                    temppathfindparents.word and (wikiwordmatchterms.type & 2) 
                    != 0)
                    """)
    
                self.connWrap.execSql("""
                    insert or ignore into temppathfindparents (word, child, steps)
                    select wikirelations.word, temppathfindparents.word, ? from
                        temppathfindparents inner join wikirelations on
                        temppathfindparents.word == wikirelations.relation where
                        temppathfindparents.steps == ?
                    """, (step+1, step))
    
                step += 1
        
        except (IOError, OSError, sqlite.Error, ValueError) as e:
            traceback.print_exc()
            raise DbReadAccessError(e)


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

        Gadfly does not support glob?
        """
        try:
            thisStr = sqlite.escapeForGlob(thisStr)

            return self.connWrap.execSqlQuerySingleColumn(
                    "select word from wikiwords where word glob (? || '*')", 
                    (thisStr,))

        except (IOError, OSError, sqlite.Error, ValueError) as e:
            traceback.print_exc()
            raise DbReadAccessError(e)


    def isDefinedWikiPageName(self, word):
        try:
            return bool(self.connWrap.execSqlQuerySingleItem(
                    "select 1 from wikiwords where word = ?", (word,)))
        except (IOError, OSError, sqlite.Error) as e:
            traceback.print_exc()
            raise DbReadAccessError(e)


    def refreshWikiPageLinkTerms(self):
        raise NotImplementedError


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
                
            def get(self, key, default=None):
                if self.cacheComplete:
                    return self.cache.get(key, default)
                
                if key in self.cache:
                    return self.cache.get(key, default)
                    
                if key in self.cacheNonExistent:
                    return default
                
                try:
                    value = self.lookup(key)
                    self.cache[key] = value
                    return value
                except KeyError:
                    self.cacheNonExistent.add(key)
                    return default
            
            def lookup(self, key):
                if self.outer.isDefinedWikiPageName(key):
                    return key
                
                try:
                    value = self.outer.connWrap.execSqlQuerySingleItem(
                            "select word from wikiwordmatchterms "
                            "where matchterm = ? and (type & 2) != 0 ", (key,))
                    # Consts.WIKIWORDMATCHTERMS_TYPE_ASLINK == 2
                except (IOError, OSError, sqlite.Error) as e:
                    traceback.print_exc()
                    raise DbReadAccessError(e)
                
                if value is None:
                    raise KeyError(key)
                
                return value

            def keys(self):
                if not self.cacheComplete:
                    self.cache = dict(self.outer.connWrap.execSqlQuery(
                            "select word, word from wikiwords union "
                            "select matchterm, word from wikiwordmatchterms "
                            "where (type & 2) != 0 and not matchterm in "
                            "(select word from wikiwords)"))
                    # Consts.WIKIWORDMATCHTERMS_TYPE_ASLINK == 2
                    self.cacheComplete = True
                    self.cacheNonExistent = set()

                return list(self.cache.keys())

        # A note about case insensitivity

        # The current implementation is not truly "insensitive". It allows
        # (for example) both wikiWord and WikiWord to exist side by side if
        # the pages are created by a method that doesn't use
        # Cachedwikipagelinktermdict. It would probably be simpler (code wise),
        # and perhaps make more sense to make it truly insensitive, which
        # would probably be best achieved by creating another column in the
        # wikiwords table - much like already exists in wikiwordmatchterms.
        class CachedWikiPageLinkTermDictNoCase(object):
            def __init__(self, outer):
                self.outer = outer
                self.cache = {}
                self.cacheLower = {}
                self.cacheNonExistent = set()
                self.cacheComplete = False
                
            def get(self, key, default=None):
                if self.cacheComplete:
                    retrievedKey = self.cache.get(key, default)

                    if retrievedKey is default:
                        return self.cacheLower.get(key, default)

                    return retrievedKey
                
                if key in self.cache:
                    return self.cache.get(key, default)
                elif key in self.cacheLower:
                    return self.cacheLower.get(key, default)
                    
                if key in self.cacheNonExistent:
                    return default
                
                try:
                    value = self.lookup(key)
                    self.cache[key] = value
                    return value
                except KeyError:
                    self.cacheNonExistent.add(key)
                    return default
            
            def lookup(self, key):
                if self.outer.isDefinedWikiPageName(key):
                    return key
                
                # First check for the word normally
                try:
                    value = self.outer.connWrap.execSqlQuerySingleItem(
                            "select word from wikiwordmatchterms "
                            "where matchterm = ? and (type & 2) != 0 ", (key,))
                    # Consts.WIKIWORDMATCHTERMS_TYPE_ASLINK == 2
                except (IOError, OSError, sqlite.Error, ValueError) as e:
                    traceback.print_exc()
                    raise DbReadAccessError(e)

                # If not found check the lowercase wikiwordmatchterms
                if value is None:
                    try:
                        value = self.outer.connWrap.execSqlQuerySingleItem(
                                "select word from wikiwordmatchterms "
                                "where matchtermnormcase = ? and "
                                "(type & 2) != 0 ", (key.lower(),))
                        # Consts.WIKIWORDMATCHTERMS_TYPE_ASLINK == 2
                    except (IOError, OSError, sqlite.Error, ValueError) as e:
                        traceback.print_exc()
                        raise DbReadAccessError(e)
                
                if value is None:
                    raise KeyError(key)
                
                return value

            def keys(self):
                if not self.cacheComplete:
                    # Normal cache
                    self.cache = dict(self.outer.connWrap.execSqlQuery(
                            "select word, word from wikiwords union "
                            "select matchterm, word from wikiwordmatchterms "
                            "where (type & 2) != 0 and not matchterm in "
                            "(select word from wikiwords)"))

                    # Is the best way to get the lowercase names?
                    self.cacheLower = dict(self.outer.connWrap.execSqlQuery(
                            "select utf8Normcase(word), word from wikiwords union "
                            "select matchtermnormcase, word from wikiwordmatchterms "
                            "where (type & 2) != 0 and not matchtermnormcase in "
                            "(select utf8Normcase(word) from wikiwords)"))


                    # Consts.WIKIWORDMATCHTERMS_TYPE_ASLINK == 2
                    self.cacheComplete = True
                    self.cacheNonExistent = set()

                return list(self.cache.keys())


        try:
            if self.cachedWikiPageLinkTermDict is None:
                if self.caseInsensitiveWikiWords:
                    self.cachedWikiPageLinkTermDict = \
                            CachedWikiPageLinkTermDictNoCase(self)
                else:
                    self.cachedWikiPageLinkTermDict = \
                            CachedWikiPageLinkTermDict(self)

            return self.cachedWikiPageLinkTermDict
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


    def getWikiPageLinkTermsStartingWith(self, thisStr, caseNormed=False):
        """
        Get the list of wiki page link terms (page names or aliases)
        starting with thisStr. Used for autocompletion.
        """
        if caseNormed:
            thisStr = sqlite.escapeForGlob(thisStr.lower())   # TODO More general normcase function

            try:
                return self.connWrap.execSqlQuerySingleColumn(
                        "select matchterm from wikiwordmatchterms "
                        "where matchtermnormcase glob (? || '*') and "
                        "(type & 2) != 0", 
                        (thisStr,))
                # Consts.WIKIWORDMATCHTERMS_TYPE_ASLINK == 2

            except (IOError, OSError, sqlite.Error, ValueError) as e:
                traceback.print_exc()
                raise DbReadAccessError(e)

        else:
            try:
                thisStr = sqlite.escapeForGlob(thisStr)

                # To ensure that at least all real wikiwords are found,
                # the wikiwords table is also read
                return self.connWrap.execSqlQuerySingleColumn(
                        "select matchterm from wikiwordmatchterms "
                        "where matchterm glob (? || '*') and "
                        "(type & 2) != 0 union "
                        "select word from wikiwords where word glob (? || '*')", 
                        (thisStr,thisStr))
                # Consts.WIKIWORDMATCHTERMS_TYPE_ASLINK == 2

            except (IOError, OSError, sqlite.Error, ValueError) as e:
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
        except (IOError, OSError, sqlite.Error, ValueError) as e:
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
                    ("select min({0}), max({0}) "
                    "from wikiwords where {0} > 0").format(field))
        except (IOError, OSError, sqlite.Error, ValueError) as e:
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
        except (IOError, OSError, sqlite.Error, ValueError) as e:
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
                    ("select word, {0] from wikiwords where {0] > ? "
                    "order by {0] asc limit ?").format(field), (stamp, limit))
        except (IOError, OSError, sqlite.Error, ValueError) as e:
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
        except (IOError, OSError, sqlite.Error, ValueError) as e:
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
        except (IOError, OSError, sqlite.Error, ValueError) as e:
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
        except (IOError, OSError, sqlite.Error, ValueError) as e:
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
        except (IOError, OSError, sqlite.Error, ValueError) as e:
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


    def getAllDefinedWikiMatchTermsNormcase(self):
        """
        Get the names of all defined matchterms in db
        Function must work for read-only wiki.

        Returns a dict(matchtermnormcase -> word)
        """

        # As this query can take a long time to execute we cache the output
        # Not failproof - fails if changes result in same length
        if self.definedWikiMatchTerms[0] == \
                self.connWrap.execSqlQuerySingleItem(
                        "select count(*) from wikiwordmatchterms where (type & 2) != 0"):
            return self.definedWikiMatchTerms[1]
         
        try:
            results = self.connWrap.execSqlQuery(
                    "select matchtermnormcase, word from wikiwordmatchterms where (type & 2) != 0")
            # To workaround non unique matchtermnormcase
            self.definedWikiMatchTerms = (len(results), dict(results))
        except (IOError, OSError, sqlite.Error, ValueError) as e:
            traceback.print_exc()
            raise DbReadAccessError(e)

        return self.definedWikiMatchTerms[1]


    def getWikiPageNamesModifiedWithin(self, startTime, endTime):
        """
        Function must work for read-only wiki.
        startTime and endTime are floating values as returned by time.time()
        startTime is inclusive, endTime is exclusive
        """
        raise NotImplementedError


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
        raise NotImplementedError


    def getWikiPageNamesBefore(self, stampType, stamp, limit=None):
        """
        Get a list of tuples of wiki words and dates related to a particular
        time before stamp.
        
        stampType -- 0: Modification time, 1: Creation, 2: Last visit
        limit -- How much count entries to return or None for all
        """
        raise NotImplementedError


    def getWikiPageNamesAfter(self, stampType, stamp, limit=None):
        """
        Get a list of of tuples of wiki words and dates related to a particular
        time after OR AT stamp.
        
        stampType -- 0: Modification time, 1: Creation, 2: Last visit
        limit -- How much words to return or None for all
        """
        raise NotImplementedError


    def getFirstWikiPageName(self):
        """
        Returns the name of the "first" wiki word. See getNextWikiPageName()
        for details. Returns either an existing wiki word or None if no
        wiki words in database.
        """
        raise NotImplementedError


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
        raise NotImplementedError


    def isDefinedWikiPageName(self, word):
        try:
            return bool(self.connWrap.execSqlQuerySingleItem(
                    "select 1 from wikiwords where word = ?", (word,)))
        except (IOError, OSError, sqlite.Error, ValueError) as e:
            traceback.print_exc()
            raise DbReadAccessError(e)


    # ---------- Attribute cache handling ----------

    def getDistinctAttributeValues(self, key):
        """
        Function must work for read-only wiki.
        """
        try:
            return self.connWrap.execSqlQuerySingleColumn(
                    "select distinct(value) from wikiwordattrs where key = ? ",
                    (key,))
        except (IOError, OSError, sqlite.Error, ValueError) as e:
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
        
        conjunction = Conjunction("where ", "and ")

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
        except (IOError, OSError, sqlite.Error, ValueError) as e:
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
        except (IOError, OSError, sqlite.Error, ValueError) as e:
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
        except (IOError, OSError, sqlite.Error, ValueError) as e:
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

        self.cachedGlobalAttrs = None   # reset global attributes cache


    def updateCachedGlobalAttrs(self):
        """
        TODO: Should become part of public API!
        Function must work for read-only wiki.
        """
        try:
            data = self.connWrap.execSqlQuery("select key, value from wikiwordattrs "
                    "where key glob 'global.*'")
        except (IOError, OSError, sqlite.Error, ValueError) as e:
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
        except (IOError, OSError, sqlite.Error, ValueError) as e:
            traceback.print_exc()
            raise DbWriteAccessError(e)

    
    # ---------- Alias handling ----------


    def getWikiPageNameForLinkTerm(self, alias):
        """
        Return real page name for wiki page link term which may be
        a real page name or an alias. Returns None if term not found.
        Function should only be called by WikiDocument as some methods
        of unaliasing must be performed in WikiDocument.
        Function must work for read-only wiki.
        """
        return self._getCachedWikiPageLinkTermDict().get(alias, None)


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

        except (IOError, OSError, sqlite.Error, ValueError) as e:
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
#         except (IOError, OSError, sqlite.Error, ValueError), e:
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
        except (IOError, OSError, sqlite.Error, ValueError) as e:
            traceback.print_exc()
            raise DbWriteAccessError(e)


    def deleteTodos(self, word):
        try:
            self.connWrap.execSql("delete from todos where word = ?", (word,))
        except (IOError, OSError, sqlite.Error, ValueError) as e:
            traceback.print_exc()
            raise DbWriteAccessError(e)


    # ---------- Wikiword matchterm cache handling ----------

    def getWikiWordMatchTermsWith(self, thisStr, orderBy=None, descend=False):
        "get the list of match terms with thisStr in them."
        thisStr = sqlite.escapeForGlob(thisStr.lower())   # TODO More general normcase function

#         orderBy = "visited"   # !!! Test
#         descend = True   # !!! Test

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
            except (IOError, OSError, sqlite.Error, ValueError) as e:
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
            except (IOError, OSError, sqlite.Error, ValueError) as e:
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
        except (IOError, OSError, sqlite.Error, ValueError) as e:
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
        except (IOError, OSError, sqlite.Error, ValueError) as e:
            traceback.print_exc()
            raise DbWriteAccessError(e)

    # ---------- Data block handling ----------

    def getDataBlockUnifNamesStartingWith(self, startingWith):
        """
        Return all unified names starting with startingWith (case sensitive)
        """
        raise NotImplementedError
    

    def retrieveDataBlock(self, unifName, default=""):
        """
        Retrieve data block as binary string.
        """
        raise NotImplementedError


    def iterAllDataBlocks(self):
        """
        Returns iterator over all data blocks. Each iteration returns a tuple
        (unified name, datablock content). The datablock content is returned
        as binary.

        This is only part of public API if "recovery mode" is supported.
        """
        return self.connWrap.execSqlQueryIter(
                "select unifiedname, data from datablocks")


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
        raise NotImplementedError


    def guessDataBlockStoreHint(self, unifName):
        """
        Return a guess of the store hint used to store the block last time.
        Returns one of the DATABLOCK_STOREHINT_* constants from Consts.py.
        The function is allowed to return the wrong value (therefore a guess)
        For compact_sqlite it always returns Consts.DATABLOCK_STOREHINT_INTERN.
        It returns None for non-existing data blocks.
        """
        raise NotImplementedError


    def deleteDataBlock(self, unifName):
        """
        Delete data block with the associated unified name. If the unified name
        is not in database, nothing happens.
        """
        raise NotImplementedError

    # ---------- Searching pages ----------

    def search(self, sarOp, exclusionSet):
        raise NotImplementedError

    # ---------- Miscellaneous ----------

    _CAPABILITIES = {} # Should be added by derived class

    def checkCapability(self, capkey):
        """
        Check the capabilities of this WikiData implementation.
        The capkey names the capability, the function returns normally
        a version number or None if not supported
        Function must work for read-only wiki.
        """
        return self._CAPABILITIES.get(capkey, None)


    def setEditorTextMode(self, mode):
        """
        If true, forces the editor to write platform dependent files to disk
        (line endings as CR/LF, LF or CR).
        If false, LF is used always.
        
        Must be implemented if checkCapability returns a version number
        for "filePerPage".
        """           
        raise NotImplementedError


    def clearCacheTables(self):
        # TODO: check if the differences in implementation are required
        raise NotImplementedError


    def setDbSettingsValue(self, key, value):
        assert isinstance(value, str)
        self.connWrap.execSql("insert or replace into settings(key, value) "
                "values (?, ?)", (key, value))


    def getDbSettingsValue(self, key, default=None):
        return self.DbStructure.getSettingsValue(self.connWrap, key, default)


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
        raise NotImplementedError


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
            if self.dbType == "original_gadfly":
                self.connWrap.commitNeeded = False
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



    # ---------- Other optional functionality ----------

    def cleanupAfterRebuild(self, progresshandler):
        raise NotImplementedError


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
                # "modified" isn't a field of wikirelations. We need
                # some SQL magic to retrieve the modification date
                addFields += (", ifnull((select modified from wikiwords "
                        "where wikiwords.word = relation or "
                        "wikiwords.word = (select word from wikiwordmatchterms "
                        "where wikiwordmatchterms.matchterm = relation and "
                        "(wikiwordmatchterms.type & 2) != 0 limit 1)), 0.0)")

                converters.append(float)


        sql = "select relation{0} from wikirelations where word = ?".format(
                addFields)

        if not selfreference:
            if self.caseInsensitiveWikiWords:
                sql += " and utf8Normcase(relation) != utf8Normcase(word)"
            else:
                sql += " and relation != word"

        if existingonly:
            # filter to only words in wikiwords or aliases
#             sql += " and (exists (select word from wikiwords "+\
#                     "where word = relation) or exists "+\
#                     "(select value from wikiwordattrs "+\
#                     "where value = relation and key = 'alias'))"
            if self.caseInsensitiveWikiWords:
                sql += (" and (exists (select 1 from wikiwords "
                        "where word = relation) or exists "
                        "(select 1 from wikiwordmatchterms "
                        "where wikiwordmatchterms.matchterm = relation and "
                        "(wikiwordmatchterms.type & 2) != 0))")
            else:
                sql += (" and (exists (select 1 from wikiwords "
                        "where utf8Normcase(word) = utf8Normcase(relation)) or exists "
                        "(select 1 from wikiwordmatchterms "
                        "where wikiwordmatchterms.matchtermnormcase = utf8Normcase(relation) and "
                        "(wikiwordmatchterms.type & 2) != 0))")
            # Consts.WIKIWORDMATCHTERMS_TYPE_ASLINK == 2


        try:
            if len(withFields) > 0:
                return self.connWrap.execSqlQuery(sql, (wikiWord,))
            else:
                return self.connWrap.execSqlQuerySingleColumn(sql, (wikiWord,))
        except (IOError, OSError, sqlite.Error, ValueError) as e:
            traceback.print_exc()
            raise DbReadAccessError(e)

