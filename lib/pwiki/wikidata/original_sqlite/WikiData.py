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
import string, glob, traceback

from pwiki.WikiExceptions import *   # TODO make normal import
from pwiki import SearchAndReplace

try:
    import pwiki.sqlite3api as sqlite
    import DbStructure
    from DbStructure import createWikiDB, WikiDBExistsException
except:
    traceback.print_exc()
    sqlite = None
# finally:
#     pass

from pwiki.StringOps import getBinCompactForDiff, applyBinCompact, longPathEnc, \
        longPathDec, binCompactToCompact, fileContentToUnicode, utf8Enc, utf8Dec, \
        BOM_UTF8, uniWithNone, loadEntireTxtFile, loadEntireFile, writeEntireFile, \
        Conjunction, iterCompatibleFilename, \
        getFileSignatureBlock, lineendToInternal, guessBaseNameByFilename, \
        createRandomString

import Consts

class WikiData:
    "Interface to wiki data."
    def __init__(self, wikiDocument, dataDir, tempDir):
        self.wikiDocument = wikiDocument
        self.dataDir = dataDir
        self.cachedContentNames = None

        dbfile = join(dataDir, "wikiovw.sli")   # means "wiki overview"
        
        try:
            if (not exists(longPathEnc(dbfile))):
                DbStructure.createWikiDB(None, dataDir)  # , True
        except (IOError, OSError, sqlite.Error), e:
            traceback.print_exc()
            raise DbWriteAccessError(e)

        dbfile = longPathDec(dbfile)
        try:
            self.connWrap = DbStructure.ConnectWrapSyncCommit(
                    sqlite.connect(dbfile))
        except (IOError, OSError, sqlite.Error), e:
            traceback.print_exc()
            raise DbReadAccessError(e)

        DbStructure.registerSqliteFunctions(self.connWrap)

        try:
            self.pagefileSuffix = self.wikiDocument.getWikiConfig().get("main",
                    "db_pagefile_suffix", u".wiki")
        except (IOError, OSError), e:
            traceback.print_exc()
            raise DbReadAccessError(e)


    def checkDatabaseFormat(self):
        return DbStructure.checkDatabaseFormat(self.connWrap)


    def connect(self):
        formatcheck, formatmsg = self.checkDatabaseFormat()

        if formatcheck == 2:
            # Unknown format
            raise WikiDataException, formatmsg

        # Update database from previous versions if necessary
        if formatcheck == 1:
            try:
                DbStructure.updateDatabase(self.connWrap, self.dataDir,
                        self.pagefileSuffix)
            except Exception, e:
                traceback.print_exc()
                try:
                    self.connWrap.rollback()
                except Exception, e2:
                    traceback.print_exc()
                    raise DbWriteAccessError(e2)
                raise DbWriteAccessError(e)

        lastException = None
        try:
            # Further possible updates
            DbStructure.updateDatabase2(self.connWrap)
        except sqlite.Error, e:
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
        except (IOError, OSError, sqlite.Error), e:
            # Remember but continue
            lastException = DbWriteAccessError(e)
    
        # Function to convert unicode strings from input to content in database
        # used by setContent
        def contentUniInputToDb(unidata):
            return utf8Enc(unidata, "replace")[0]

        self.contentUniInputToDb = contentUniInputToDb

        try:
            self._createTempTables()

            # create word caches
            self.cachedContentNames = None
            self.cachedGlobalProps = None
            self.getGlobalProperties()
        except (IOError, OSError, sqlite.Error), e:
            traceback.print_exc()
            try:
                self.connWrap.rollback()
            except (IOError, OSError, sqlite.Error), e2:
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
        self.connWrap.execSql("create temp table temppathfindparents "+
                "(word text primary key, child text, steps integer)")

        self.connWrap.execSql("create index temppathfindparents_steps "+
                "on temppathfindparents(steps)")


    # ---------- Direct handling of page data ----------
    
    def getContent(self, word):
        """
        Function must work for read-only wiki.
        """
        try:
#             if (not exists(self.getWikiWordFileName(word))):
#                 raise WikiFileNotFoundException(
#                         _(u"Wiki page not found for word: %s") % word)
    
            content = loadEntireTxtFile(self.getWikiWordFileName(word))
    
            return fileContentToUnicode(content)
        except (IOError, OSError, sqlite.Error), e:
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
        except (IOError, OSError, sqlite.Error), e:
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

            self.cachedContentNames = None
        except (IOError, OSError, sqlite.Error), e:
            traceback.print_exc()
            raise DbWriteAccessError(e)



    def setContent(self, word, content, moddate = None, creadate = None):
        """
        Sets the content, does not modify the cache information
        except self.cachedContentNames
        """
        assert type(content) is unicode
        try:
            self._updatePageEntry(word, moddate, creadate)

            filePath = self.getWikiWordFileName(word)
            writeEntireFile(filePath, content, True)

            fileSig = getFileSignatureBlock(filePath)
            self.connWrap.execSql("update wikiwords set filesignature = ?, "
                    "metadataprocessed = 0 where word = ?",
                    (sqlite.Binary(fileSig), word))
        except (IOError, OSError, sqlite.Error), e:
            traceback.print_exc()
            raise DbWriteAccessError(e)


    def renameContent(self, oldWord, newWord):
        """
        The content which was stored under oldWord is stored
        after the call under newWord. The self.cachedContentNames
        dictionary is updated, other caches won't be updated.
        """
        try:
            oldFilePath = self.getWikiWordFileNameRaw(oldWord)
            head, oldFileName = os.path.split(oldFilePath)
#             head = pathDec(head)
#             oldFileName = pathDec(oldFileName)

            fileName = self.createWikiWordFileName(newWord)
            newFilePath = os.path.join(head, fileName)

            os.rename(longPathEnc(os.path.join(self.dataDir, oldFilePath)),
                    longPathEnc(os.path.join(self.dataDir, newFilePath)))

            self.cachedContentNames = None

            self.connWrap.execSql("update wikiwords set word = ?, filepath = ?, "
                    "filenamelowercase = ?, metadataprocessed = 0 where word = ?",
                    (newWord, newFilePath, fileName.lower(), oldWord))

        except (IOError, OSError, sqlite.Error), e:
            traceback.print_exc()
            raise DbWriteAccessError(e)


    def deleteContent(self, word):
        try:
            fileName = self.getWikiWordFileName(word)
            self.connWrap.execSql("delete from wikiwords where word = ?",
                    (word,))
            self.cachedContentNames = None
            if exists(fileName):
                os.unlink(fileName)
        except (IOError, OSError, sqlite.Error), e:
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
                    "select modified, created from wikiwords where word = ?",
                    (word,))
    
            if len(dates) > 0:
                return (float(dates[0][0]), float(dates[0][1]), 0.0)
            else:
                return (None, None, None)  # ?
        except (IOError, OSError, sqlite.Error), e:
            traceback.print_exc()
            raise DbReadAccessError(e)


    def setTimestamps(self, word, timestamps):
        """
        Set timestamps for an existing wiki page.
        Aliases must be resolved beforehand.
        """
        moddate, creadate = timestamps[:2]

        try:
            data = self.connWrap.execSqlQuery("select word from wikiwords "
                    "where word = ?", (word,))
        except (IOError, OSError, sqlite.Error), e:
            traceback.print_exc()
            raise DbReadAccessError(e)

        try:
            if len(data) < 1:
                raise WikiFileNotFoundException
            else:
                self.connWrap.execSql("update wikiwords set modified = ?, "
                        "created = ? where word = ?", (moddate, creadate, word))
        except (IOError, OSError, sqlite.Error), e:
            traceback.print_exc()
            raise DbWriteAccessError(e)


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
                "visited": Last visit date of page (currently always returns 0)
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
                # Fake "visited" field
                addFields += ", visited"
#                 converters.append(lambda s: 0.0)
                converters.append(float)
            elif field == "firstcharpos":
                # Fake character position. TODO More elegantly
                addFields += ", 0"
                converters.append(lambda s: 2000000000L)


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
        except (IOError, OSError, sqlite.Error), e:
            traceback.print_exc()
            raise DbReadAccessError(e)



    # ---------- Renaming/deleting pages with cache update or invalidation ----------

    def renameWord(self, word, toWord):
        try:
            # commit anything pending so we can rollback on error
            self.connWrap.syncCommit()

            try:
                self.connWrap.execSql("update wikirelations set word = ? where word = ?", (toWord, word))
                self.connWrap.execSql("update wikiwordprops set word = ? where word = ?", (toWord, word))
                self.connWrap.execSql("update todos set word = ? where word = ?", (toWord, word))
                self.connWrap.execSql("update wikiwordmatchterms set word = ? where word = ?", (toWord, word))
                self.renameContent(word, toWord)
                self.connWrap.commit()
            except:
                self.connWrap.rollback()
                raise
        except (IOError, OSError, sqlite.Error), e:
            traceback.print_exc()
            raise DbWriteAccessError(e)


    def deleteWord(self, word):
        """
        delete everything about the wikiword passed in. an exception is raised
        if you try and delete the wiki root node.
        """
        if word != self.wikiDocument.getWikiName():
            try:
                self.connWrap.syncCommit()
                try:
                    # don't delete the relations to the word since other
                    # pages still have valid outward links to this page.
                    # just delete the content
    
                    self.deleteChildRelationships(word)
                    self.deleteProperties(word)
                    self.deleteTodos(word)
                    self.deleteContent(word)
                    self.deleteWikiWordMatchTerms(word, syncUpdate=False)
                    self.deleteWikiWordMatchTerms(word, syncUpdate=True)
                    self.connWrap.commit()
                except:
                    self.connWrap.rollback()
                    raise
            except (IOError, OSError, sqlite.Error), e:
                traceback.print_exc()
                raise DbWriteAccessError(e)
        else:
            raise WikiDataException(_(u"You cannot delete the root wiki node"))


    def setMetaDataState(self, word, state):
        """
        Set the state of meta-data processing for a particular word.
        See Consts.WIKIWORDMETADATA_STATE_*
        """
        try:
            self.connWrap.execSql("update wikiwords set metadataprocessed = ? "
                    "where word = ?", (state, word))
        except (IOError, OSError, sqlite.Error), e:
            traceback.print_exc()
            raise DbWriteAccessError(e)


    def getMetaDataState(self, word):
        """
        Retrieve meta-data processing state of a particular wiki word.
        """
        try:
            return self.connWrap.execSqlQuerySingleItem("select metadataprocessed "
                    "from wikiwords where word = ?", (word,))
        except (IOError, OSError, sqlite.Error), e:
            traceback.print_exc()
            raise DbReadAccessError(e)


    def fullyResetMetaDataState(self, state=0):
        """
        Reset state of all wikiwords.
        """
        self.connWrap.execSql("update wikiwords set metadataprocessed = ?",
                (state,))


    def getWikiWordsForMetaDataState(self, state):
        """
        Retrieve a list of all words with a particular meta-data processing
        state.
        """
        try:
            return self.connWrap.execSqlQuerySingleColumn("select word "
                    "from wikiwords where metadataprocessed = ?", (state,))
        except (IOError, OSError, sqlite.Error), e:
            traceback.print_exc()
            raise DbReadAccessError(e)


    def validateFileSignatureForWord(self, word, setMetaDataDirty=False, 
            refresh=False):
        """
        Returns True if file signature stored in DB matches the file
        containing the content, False otherwise.
        """
        try:
            filePath = self.getWikiWordFileName(word)
            fileSig = getFileSignatureBlock(filePath)

            dbFileSig = self.connWrap.execSqlQuerySingleItem(
                    "select filesignature from wikiwords where word = ?",
                    (word,))
            
            return dbFileSig == fileSig
        except (IOError, OSError, sqlite.Error), e:
            traceback.print_exc()
            raise DbReadAccessError(e)


    def refreshFileSignatureForWord(self, word):
        """
        Sets file signature to match current file.
        """
        try:
            filePath = self.getWikiWordFileName(word)
            fileSig = getFileSignatureBlock(filePath)
        except (IOError, OSErro, sqlite.Error), e:
            traceback.print_exc()
            raise DbReadAccessError(e)

        try:
            self.connWrap.execSql("update wikiwords set filesignature = ? "
                    "where word = ?", (sqlite.Binary(fileSig), word))
        except (IOError, OSError, sqlite.Error), e:
            traceback.print_exc()
            raise DbWriteAccessError(e)



#             self.execSql("update wikiwords set filesignature = ?, "
#                     "metadataprocessed = ? where word = ?", (fileSig, 0, word))
# 
#                     fileSig = getFileSignatureBlock(fullPath)

    

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
#                         "wikiwords.word = (select word from wikiwordprops "
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
#                     "(select value from wikiwordprops "+\
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
        except (IOError, OSError, sqlite.Error), e:
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
#                     "(select value from wikiwordprops "+\
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
#                     "(select value from wikiwordprops "+\
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
        wikiWord = self.getUnAliasedWikiWord(wikiWord)
        try:
            return self.connWrap.execSqlQuerySingleColumn(
                    "select word from wikirelations where relation = ? or "
                    "relation in (select matchterm from wikiwordmatchterms "
                    "where word = ? and "
                    "(wikiwordmatchterms.type & 2) != 0)", (wikiWord, wikiWord))
            # Consts.WIKIWORDMATCHTERMS_TYPE_ASLINK == 2


#             # Plus parents of aliases
#             aliases = [v for k, v in self.getPropertiesForWord(wikiWord)
#                     if k == u"alias"]
#     
#             for al in aliases:
#                 parents.update(self.connWrap.execSqlQuerySingleColumn(
#                     "select word from wikirelations where relation = ?", (al,)))
#     
#             return list(parents)
        except (IOError, OSError, sqlite.Error), e:
            traceback.print_exc()
            raise DbReadAccessError(e)



    # TODO Optimize!
    def getParentlessWikiWords(self):
        """
        get the words that have no parents.
        Function must work for read-only wiki.

        NO LONGER VALID: (((also returns nodes that have files but
        no entries in the wikiwords table.)))
        """
        try:
#             return self.connWrap.execSqlQuerySingleColumn(
#                     "select word from wikiwords where not word glob '[[]*' "
#                     "except select "
#                     "ifnull(wikiwordprops.word, wikirelations.relation) as unaliased "
#                     "from wikirelations left join wikiwordprops "
#                     "on wikirelations.relation = wikiwordprops.value and "
#                     "wikiwordprops.key = 'alias' where unaliased != wikirelations.word")

            return self.connWrap.execSqlQuerySingleColumn(
                    "select word from wikiwords except "
#                     "(select relation from wikirelations) and not in "
                    "select word as mtword from wikiwordmatchterms "
                    "where matchterm in (select relation from wikirelations "
                    "where wikirelations.word != mtword)")

        except (IOError, OSError, sqlite.Error), e:
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
#                     "except select value from wikiwordprops where key='alias'")
            return self.connWrap.execSqlQuerySingleColumn(
                    "select relation from wikirelations "
                    "except select word from wikiwords "
                    "except select matchterm from wikiwordmatchterms "
                    "where (type & 2) != 0")
            # Consts.WIKIWORDMATCHTERMS_TYPE_ASLINK == 2


        except (IOError, OSError, sqlite.Error), e:
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
        except (IOError, OSError, sqlite.Error), e:
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
        except (IOError, OSError, sqlite.Error), e:
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
                for w in (self.getUnAliasedWikiWord(w) for w in words)
                if w is not None]
        checkList.reverse()
        
        resultSet = {}
        result = []

        while len(checkList) > 0:
            toCheck, chLevel = checkList.pop()
            if resultSet.has_key(toCheck):
                continue

            result.append(toCheck)
            resultSet[toCheck] = None
            
            if level > -1 and chLevel >= level:
                continue  # Don't go deeper
            
            children = self.getChildRelationships(toCheck, existingonly=True,
                    selfreference=False)
                    
            children = [(self.getUnAliasedWikiWord(c), chLevel + 1)
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
        
        except (IOError, OSError, sqlite.Error), e:
            traceback.print_exc()
            raise DbReadAccessError(e)


    def _findNewWordForFile(self, path):
        wikiWord = guessBaseNameByFilename(path, self.pagefileSuffix)
        try:
            if self.connWrap.execSqlQuerySingleItem(
                    "select word from wikiwords where word = ?", (wikiWord,)):
                for i in range(20):    # "while True" is too dangerous
                    rand = createRandomString(10)

                    if self.connWrap.execSqlQuerySingleItem(
                            "select word from wikiwords where word = ?",
                            (wikiWord + u"~" + rand,)):
                        continue
                    
                    return wikiWord + u"~" + rand

                return None

            else:
                return wikiWord

        except (IOError, OSError, sqlite.Error), e:
            traceback.print_exc()
            raise DbWriteAccessError(e)


    # ---------- Listing/Searching wiki words (see also "alias handling", "searching pages")----------

#     def getAllDefinedWikiPageNames(self):
#         """
#         get the names of all wiki pages in the db, no aliases, no functional
#         pages.
#         Function must work for read-only wiki.
#         """
#         try:
#             return self.connWrap.execSqlQuerySingleColumn(
#                     "select word from wikiwords where not word glob '[[]*'")
#         except (IOError, OSError, sqlite.Error), e:
#             traceback.print_exc()
#             raise DbReadAccessError(e)


    def getAllDefinedContentNames(self):
        """
        get the names of all the content elements in the db, no aliases
        Function must work for read-only wiki.
        """
        try:
            return self.connWrap.execSqlQuerySingleColumn(
                    "select word from wikiwords")
        except (IOError, OSError, sqlite.Error), e:
            traceback.print_exc()
            raise DbReadAccessError(e)


    getAllDefinedWikiPageNames = getAllDefinedContentNames

    
    def refreshDefinedContentNames(self):
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

        The self.cachedContentNames is invalidated.
        """
        diskFiles = frozenset(self._getAllWikiFileNamesFromDisk())
        dbFiles = frozenset(self._getAllWikiFileNamesFromDb())

        self.cachedContentNames = None
        try:
            # Delete words for which no file is present anymore
            for path in self.connWrap.execSqlQuerySingleColumn(
                    "select filepath from wikiwords"):
                if not os.path.exists(longPathEnc(os.path.join(self.dataDir, path))):
                    self.connWrap.execSql("delete from wikiwords "
                            "where filepath = ?", (path,))

            # Add new words:
            ti = time()
            for path in (diskFiles - dbFiles):
                fullPath = os.path.join(self.dataDir, path)
                st = os.stat(longPathEnc(fullPath))
                
                wikiWord = self._findNewWordForFile(path)
                
#                 wikiWord = guessBaseNameByFilename(path, self.pagefileSuffix)
                
#                 if self.execSqlQuerySingleItem(
#                         "select word from wikiwords where word = ?", (wikiWord,)):
#                     for i in range(20):    # "while True" is too dangerous
#                         rand = createRandomString(10)
#                         
#                         if self.execSqlQuerySingleItem(
#                                 "select word from wikiwords where word = ?",
#                                 (wikiWord + u"~" + rand,)):
#                             continue
#                         
#                         wikiWord = wikiWord + u"~" + rand
#                         break
#                     else:

                if wikiWord is not None:
                    fileSig = getFileSignatureBlock(fullPath)
                    
                    self.connWrap.execSql("insert into wikiwords(word, created, "
                            "modified, filepath, filenamelowercase, "
                            "filesignature) "
                            "values (?, ?, ?, ?, ?, ?)",
                            (wikiWord, ti, st.st_mtime, path, path.lower(),
                                    sqlite.Binary(fileSig)))
        except (IOError, OSError, sqlite.Error), e:
            traceback.print_exc()
            raise DbWriteAccessError(e)


    def _getCachedContentNames(self):
        """
        Function works for read-only wiki.
        """
        try:
            if self.cachedContentNames is None:
                self.cachedContentNames = dict(self.connWrap.execSqlQuery(
                        "select word, word from wikiwords union "
                        "select matchterm, word from wikiwordmatchterms "
                        "where (type & 2) != 0 and not matchterm in "
                        "(select word from wikiwords)"))
                # Consts.WIKIWORDMATCHTERMS_TYPE_ASLINK == 2

            return self.cachedContentNames
        except (IOError, OSError, sqlite.Error), e:
            traceback.print_exc()
            raise DbReadAccessError(e)



    def _getAllWikiFileNamesFromDisk(self):   # Used for rebuilding wiki
        try:
            files = glob.glob(longPathEnc(join(self.dataDir,
                    u'*' + self.pagefileSuffix)))

            return [longPathDec(basename(fn)) for fn in files]
            
#             result = []
#             for file in files:
#                 word = pathDec(basename(file))
#                 if word.endswith(self.pagefileSuffix):
#                     word = word[:-len(self.pagefileSuffix)]
#                 
#                 result.append(word)
#             
#             return result

        except (IOError, OSError, sqlite.Error), e:
            traceback.print_exc()
            raise DbReadAccessError(e)


    def _getAllWikiFileNamesFromDb(self):   # Used for rebuilding wiki
        try:
            return self.connWrap.execSqlQuerySingleColumn("select filepath "
                    "from wikiwords")

        except (IOError, OSError, sqlite.Error), e:
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
        except (IOError, OSError, sqlite.Error), e:
            traceback.print_exc()
            raise DbReadAccessError(e)

        if path is None:
            raise WikiFileNotFoundException(
                    _(u"Wiki page not found for word: %s") % wikiWord)

        return path


    def getWikiWordFileName(self, wikiWord):
        """
        Not part of public API!
        Function must work for read-only wiki.
        """
        path = self.getWikiWordFileNameRaw(wikiWord)
        return longPathEnc(join(self.dataDir, path))


#     def isDefinedWikiWord(self, word):
#         """
#         check if a word is a valid wikiword (page name or alias)
#         Function must work for read-only wiki.
#         """
#         return self._getCachedContentNames().has_key(word)

#     def getWikiWordsStartingWith(self, thisStr, includeAliases=False,
#             caseNormed=False):
#         """
#         get the list of words starting with thisStr. used for autocompletion.
#         Function must work for read-only wiki.
#         """
#         # Escape some characters:   # TODO more elegant
#         thisStr = thisStr.replace("[", "[[").replace("]", "[]]").replace("[[", "[[]")
#         try:
#             if caseNormed:
#                 thisStr = thisStr.lower()   # TODO More general normcase function
#                 if includeAliases:
#                     return self.connWrap.execSqlQuerySingleColumn(
#                             "select word from wikiwords where wordnormcase glob (? || '*') union "
#                             "select value from wikiwordprops where key = 'alias' and "
#                             "utf8Normcase(value) glob (? || '*')", (thisStr, thisStr))
#                 else:
#                     return self.connWrap.execSqlQuerySingleColumn("select word "
#                             "from wikiwords where wordnormcase glob (? || '*')",
#                             (thisStr,))
#             else:
#                 if includeAliases:
#                     return self.connWrap.execSqlQuerySingleColumn(
#                             "select word from wikiwords where word glob (? || '*') union "
#                             "select value from wikiwordprops where key = 'alias' and "
#                             "value glob (? || '*')", (thisStr, thisStr))
#                 else:
#                     return self.connWrap.execSqlQuerySingleColumn("select word "
#                             "from wikiwords where word glob (? || '*')",
#                             (thisStr,))
# 
# 
#         except (IOError, OSError, sqlite.Error), e:
#             traceback.print_exc()
#             raise DbReadAccessError(e)
#         
#         return pathEnc(join(self.dataDir, path))


    def createWikiWordFileName(self, wikiWord):
        """
        Create a filename for wikiWord which is not yet in the database or
        a file with that name in the data directory
        """
        icf = iterCompatibleFilename(wikiWord, self.pagefileSuffix)
        for i in range(30):   # "while True" would be too dangerous
            fileName = icf.next()
            existing = self.connWrap.execSqlQuerySingleColumn(
                    "select filenamelowercase from wikiwords "
                    "where filenamelowercase = ?", (fileName.lower(),))
            if len(existing) > 0:
                continue
            if exists(longPathEnc(join(self.dataDir, fileName))):
                continue

            return fileName

        return None


    def isDefinedWikiPage(self, word):
        try:
            return bool(self.connWrap.execSqlQuerySingleItem(
                    "select 1 from wikiwords where word = ?", (word,)))
        except (IOError, OSError, sqlite.Error), e:
            traceback.print_exc()
            raise DbReadAccessError(e)


    def isDefinedWikiLink(self, word):
        "check if a word is a valid wikiword (page name or alias)"
        return bool(self.getUnAliasedWikiWord(word))


#     # TODO More reliably esp. for aliases
#     def isDefinedWikiWord(self, word):
#         "check if a word is a valid wikiword (page name or alias)"
#         return self._getCachedContentNames().has_key(word)


    def getAllProducedWikiLinks(self):
        """
        Return all links stored by production (in contrast to resolution)
        Function must work for read-only wiki.
        """
        return self._getCachedContentNames().keys()


    def getWikiLinksStartingWith(self, thisStr, includeAliases=False, 
            caseNormed=False):
        "get the list of words starting with thisStr. used for autocompletion."
        if caseNormed:
            thisStr = sqlite.escapeForGlob(thisStr.lower())   # TODO More general normcase function

            try:
                return self.connWrap.execSqlQuerySingleColumn(
                        "select matchterm from wikiwordmatchterms "
                        "where matchtermnormcase glob (? || '*') and "
                        "(type & 2) != 0", 
                        (thisStr,))
                # Consts.WIKIWORDMATCHTERMS_TYPE_ASLINK == 2

            except (IOError, OSError, sqlite.Error), e:
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
                
            except (IOError, OSError, sqlite.Error), e:
                traceback.print_exc()
                raise DbReadAccessError(e)


#     def getWikiLinksStartingWith(self, thisStr, includeAliases=False, 
#             caseNormed=False):
#         "get the list of words starting with thisStr. used for autocompletion."
#         words = self.getAllDefinedContentNames()
#         if includeAliases:
#             words.extend(self.getAllAliases())
#         
#         if caseNormed:
#             thisStr = thisStr.lower()   # TODO More general normcase function
#             startingWith = [word for word in words
#                     if word.lower().startswith(thisStr)]
#             return startingWith
#         else:
#             startingWith = [word for word in words if word.startswith(thisStr)]
#             return startingWith


#     def getWikiWordsWith(self, thisStr, includeAliases=False):
#         """
#         get the list of words with thisStr in them,
#         if possible first these which start with thisStr.
#         Function must work for read-only wiki.
#         """
#         thisStr = thisStr.lower()   # TODO More general normcase function
# 
#         try:
#             result1 = self.connWrap.execSqlQuerySingleColumn(
#                     "select word from wikiwords where wordnormcase like (? || '%')",
#                     (thisStr,))
# 
#             if includeAliases:
#                 result1 += self.connWrap.execSqlQuerySingleColumn(
#                         "select value from wikiwordprops where key = 'alias' and "
#                         "utf8Normcase(value) like (? || '%')", (thisStr,))
#     
#             result2 = self.connWrap.execSqlQuerySingleColumn(
#                     "select word from wikiwords "
#                     "where wordnormcase like ('%' || ? || '%') and "
#                     "wordnormcase not like (? || '%') and word not glob '[[]*'",
#                     (thisStr, thisStr))
#     
#             if includeAliases:
#                 result2 += self.connWrap.execSqlQuerySingleColumn(
#                         "select value from wikiwordprops where key = 'alias' and "
#                         "utf8Normcase(value) like ('%' || ? || '%') and "
#                         "utf8Normcase(value) not like (? || '%')",
#                         (thisStr, thisStr))
#                         
#             coll = self.wikiDocument.getCollator()
#             
#             coll.sort(result1)
#             coll.sort(result2)
# 
#             return result1 + result2
#         except (IOError, OSError, sqlite.Error), e:
#             traceback.print_exc()
#             raise DbReadAccessError(e)



    def getWikiWordsModifiedWithin(self, startTime, endTime):
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
        except (IOError, OSError, sqlite.Error), e:
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
        except (IOError, OSError, sqlite.Error), e:
            traceback.print_exc()
            raise DbReadAccessError(e)

        if len(result) == 0:
            # No matching wiki words found
            return (None, None)
        else:
            return tuple(result[0])


    def getWikiWordsBefore(self, stampType, stamp, limit=None):
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
        except (IOError, OSError, sqlite.Error), e:
            traceback.print_exc()
            raise DbReadAccessError(e)


    def getWikiWordsAfter(self, stampType, stamp, limit=None):
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
        except (IOError, OSError, sqlite.Error), e:
            traceback.print_exc()
            raise DbReadAccessError(e)


    def getFirstWikiWord(self):
        """
        Returns the name of the "first" wiki word. See getNextWikiWord()
        for details. Returns either an existing wiki word or None if no
        wiki words in database.
        Function must work for read-only wiki.
        """
        try:
            return self.connWrap.execSqlQuerySingleItem(
                    "select word from wikiwords "
                    "order by word limit 1")
        except (IOError, OSError, sqlite.Error), e:
            traceback.print_exc()
            raise DbReadAccessError(e)


    def getNextWikiWord(self, currWord):
        """
        Returns the "next" wiki word after currWord or None if no
        next word exists. If you begin with the first word returned
        by getFirstWikiWord() and then use getNextWikiWord() to
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
        except (IOError, OSError, sqlite.Error), e:
            traceback.print_exc()
            raise DbReadAccessError(e)


    # ---------- Property cache handling ----------

    def getPropertyNames(self):
        """
        Return all property names not beginning with "global."
        Function must work for read-only wiki.
        """
        try:
            return self.connWrap.execSqlQuerySingleColumn(
                    "select distinct(key) from wikiwordprops "
                    "where key not glob 'global.*'")
        except (IOError, OSError, sqlite.Error), e:
            traceback.print_exc()
            raise DbReadAccessError(e)


    # TODO More efficient? (used by autocompletion)
    def getPropertyNamesStartingWith(self, startingWith):
        """
        Function must work for read-only wiki.
        """
        try:
            return self.connWrap.execSqlQuerySingleColumn(
                    "select distinct(key) from wikiwordprops "
                    "where key glob (? || '*')",
                    (sqlite.escapeForGlob(startingWith),))   #  order by key")
#             names = self.connWrap.execSqlQuerySingleColumn(
#                     "select distinct(key) from wikiwordprops")   #  order by key")
        except (IOError, OSError, sqlite.Error), e:
            traceback.print_exc()
            raise DbReadAccessError(e)

#         return [name for name in names if name.startswith(startingWith)]




    def getGlobalProperties(self):
        """
        Function must work for read-only wiki.
        """
        if not self.cachedGlobalProps:
            return self.updateCachedGlobalProps()

        return self.cachedGlobalProps

    def getDistinctPropertyValues(self, key):
        """
        Function must work for read-only wiki.
        """
        try:
            return self.connWrap.execSqlQuerySingleColumn(
                    "select distinct(value) from wikiwordprops where key = ? ",
                    (key,))
        except (IOError, OSError, sqlite.Error), e:
            traceback.print_exc()
            raise DbReadAccessError(e)
    
    
    def getPropertyTriples(self, word, key, value):
        """
        Function must work for read-only wiki.
        word, key and value can either be unistrings or None.
        """
        conjunction = Conjunction("where ", "and ")
        
        query = "select distinct word, key, value from wikiwordprops "
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
        except (IOError, OSError, sqlite.Error), e:
            traceback.print_exc()
            raise DbReadAccessError(e)
                

                
    def getWordsForPropertyName(self, key):
        """
        Function must work for read-only wiki.
        """
        try:
            return self.connWrap.execSqlQuerySingleColumn(
                    "select distinct(word) from wikiwordprops where key = ? ",
                    (key,))
        except (IOError, OSError, sqlite.Error), e:
            traceback.print_exc()
            raise DbReadAccessError(e)


#     def getWordsWithPropertyValue(self, key, value):
#         """
#         Function must work for read-only wiki.
#         """
#         try:
#             return self.connWrap.execSqlQuerySingleColumn(
#                     "select word from wikiwordprops where key = ? and value = ?",
#                     (key, value))
#         except (IOError, OSError, sqlite.Error), e:
#             traceback.print_exc()
#             raise DbReadAccessError(e)


    def getPropertiesForWord(self, word):
        """
        Returns list of tuples (key, value) of key and value
        of all properties for word.
        Function must work for read-only wiki.
        """
        try:
            return self.connWrap.execSqlQuery("select key, value "+
                        "from wikiwordprops where word = ?", (word,))
        except (IOError, OSError, sqlite.Error), e:
            traceback.print_exc()
            raise DbReadAccessError(e)

            
    def _setProperty(self, word, key, value):
        try:
            self.connWrap.execSql(
                    "insert into wikiwordprops(word, key, value) "
                    "values (?, ?, ?)", (word, key, value))
        except (IOError, OSError, sqlite.Error), e:
            traceback.print_exc()
            raise DbWriteAccessError(e)


    def updateProperties(self, word, props):
        self.deleteProperties(word)
        self.getExistingWikiWordInfo(word)
        for k in props.keys():
            values = props[k]
            for v in values:
                self._setProperty(word, k, v)
#                 if k == "alias":
#                     self.setAsAlias(v)

        self.cachedGlobalProps = None   # reset global properties cache


    def updateCachedGlobalProps(self):
        """
        TODO: Should become part of public API!
        Function must work for read-only wiki.
        """
        try:
            data = self.connWrap.execSqlQuery("select key, value from wikiwordprops "
                    "where key glob 'global.*'")
        except (IOError, OSError, sqlite.Error), e:
            traceback.print_exc()
            raise DbReadAccessError(e)

        globalMap = {}
        for (key, val) in data:
            globalMap[key] = val

        self.cachedGlobalProps = globalMap

        return globalMap


    def deleteProperties(self, word):
        try:
            self.connWrap.execSql("delete from wikiwordprops where word = ?",
                    (word,))
        except (IOError, OSError, sqlite.Error), e:
            traceback.print_exc()
            raise DbWriteAccessError(e)



    # ---------- Alias handling ----------

    def getUnAliasedWikiWord(self, alias):
        """
        If alias is an alias for another word, return that,
        otherwise return None.
        Function should only be called by WikiDocument as some methods
        of unaliasing must be performed in WikiDocument.
        Function must work for read-only wiki.
        """
        return self._getCachedContentNames().get(alias, None)


    # ---------- Todo cache handling ----------

    def getTodos(self):
        """
        Function must work for read-only wiki.
        """
        try:
            return self.connWrap.execSqlQuery("select word, todo from todos")
        except (IOError, OSError, sqlite.Error), e:
            traceback.print_exc()
            raise DbReadAccessError(e)


    def getTodosForWord(self, word):
        """
        Returns list of all todo items of word.
        Function must work for read-only wiki.
        """
        try:
            return self.connWrap.execSqlQuerySingleColumn("select todo from todos "
                    "where word = ?", (word,))
        except (IOError, OSError, sqlite.Error), e:
            traceback.print_exc()
            raise DbReadAccessError(e)


    def updateTodos(self, word, todos):
        self.deleteTodos(word)
        self.getExistingWikiWordInfo(word)
        for t in todos:
            self._addTodo(word, t)


    def _addTodo(self, word, todo):
        try:
            self.connWrap.execSql("insert into todos(word, todo) values (?, ?)",
                    (word, todo))
        except (IOError, OSError, sqlite.Error), e:
            traceback.print_exc()
            raise DbWriteAccessError(e)


    def deleteTodos(self, word):
        try:
            self.connWrap.execSql("delete from todos where word = ?", (word,))
        except (IOError, OSError, sqlite.Error), e:
            traceback.print_exc()
            raise DbWriteAccessError(e)


    # ---------- Wikiword matchterm cache handling ----------

    def getWikiWordMatchTermsWith(self, thisStr):
        "get the list of match terms with thisStr in them."
        thisStr = sqlite.escapeForGlob(thisStr.lower())   # TODO More general normcase function

        try:
            # TODO Check for name collisions
            result1 = self.connWrap.execSqlQuery(
                    "select matchterm, type, word, firstcharpos "
                    "from wikiwordmatchterms where "
                    "matchtermnormcase glob (? || '*')", (thisStr,))

            result2 = self.connWrap.execSqlQuery(
                    "select matchterm, type, word, firstcharpos "
                    "from wikiwordmatchterms where "
                    "not matchtermnormcase glob (? || '*') "
                    "and matchtermnormcase glob ('*' || ? || '*')",
                    (thisStr, thisStr))
        except (IOError, OSError, sqlite.Error), e:
            traceback.print_exc()
            raise DbReadAccessError(e)

        coll = self.wikiDocument.getCollator()

        coll.sortByFirst(result1)
        coll.sortByFirst(result2)

        return result1 + result2


    def updateWikiWordMatchTerms(self, word, wwmTerms, syncUpdate=False):
        self.deleteWikiWordMatchTerms(word, syncUpdate=syncUpdate)
        self.getExistingWikiWordInfo(word)
        for t in wwmTerms:
            assert t[2] == word
            self._addWikiWordMatchTerm(t)


    def _addWikiWordMatchTerm(self, wwmTerm):
        matchterm, typ, word, firstcharpos = wwmTerm
        try:
            # TODO Check for name collisions
            self.connWrap.execSql("insert into wikiwordmatchterms(matchterm, "
                    "type, word, firstcharpos, matchtermnormcase) values "
                    "(?, ?, ?, ?, ?)",
                    (matchterm, typ, word, firstcharpos, matchterm.lower()))
        except (IOError, OSError, sqlite.Error), e:
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
            self.cachedContentNames = None
        except (IOError, OSError, sqlite.Error), e:
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

        except (IOError, OSError, sqlite.Error), e:
            traceback.print_exc()
            raise DbReadAccessError(e)


    def retrieveDataBlock(self, unifName):
        """
        Retrieve data block as binary string.
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
            

            datablock = loadEntireFile(join(self.dataDir, filePath))
            return datablock

        except (IOError, OSError, sqlite.Error), e:
            traceback.print_exc()
            raise DbReadAccessError(e)


    def retrieveDataBlockAsText(self, unifName):
        """
        Retrieve data block as unicode string (assuming it was encoded properly)
        and with normalized line-ending (Un*x-style).
        """
        datablock = self.retrieveDataBlock(unifName)
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
        """
        
        if storeHint is None:
            storeHint = Consts.DATABLOCK_STOREHINT_INTERN
            
        if storeHint == Consts.DATABLOCK_STOREHINT_INTERN:
            try:
                datablock = self.connWrap.execSqlQuerySingleItem(
                        "select data from datablocks where unifiedname = ?",
                        (unifName,))
            except (IOError, OSError, sqlite.Error), e:
                traceback.print_exc()
                raise DbReadAccessError(e)

            try:
                if datablock is not None:
                    # It is in internal data blocks
                    self.connWrap.execSql("update datablocks set data = ? where "
                            "unifiedname = ?", (sqlite.Binary(data), unifName))
                    return
                    
                # It may be in external data blocks
                self.deleteDataBlock(unifName)
                
                self.connWrap.execSql("insert into datablocks(unifiedname, data) "
                        "values (?, ?)", (unifName, sqlite.Binary(newdata)))

            except (IOError, OSError, sqlite.Error), e:
                traceback.print_exc()
                raise DbWriteAccessError(e)

        else:   # storeHint == Consts.DATABLOCK_STOREHINT_EXTERN
            try:
                filePath = self.connWrap.execSqlQuerySingleItem(
                        "select filepath from datablocksexternal "
                        "where unifiedname = ?", (unifName,))
            except (IOError, OSError, sqlite.Error), e:
                traceback.print_exc()
                raise DbReadAccessError(e)

            try:
                if filePath is not None:
                    # The entry is already in an external file, so overwrite it
                    writeEntireFile(join(self.dataDir, filePath), newdata,
                            isinstance(newdata, unicode))

                    fileSig = getFileSignatureBlock(join(self.dataDir, filePath))
                    self.connWrap.execSql("update datablocksexternal "
                            "set filesignature = ?", (sqlite.Binary(fileSig),))
                    return

                # Find unused filename
                icf = iterCompatibleFilename(unifName, u".data")

                for i in range(30):   # "while True" would be too dangerous
                    fileName = icf.next()
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
                        isinstance(newdata, unicode))
                fileSig = getFileSignatureBlock(filePath)

                # It may be in internal data blocks, so try to delete
                self.deleteDataBlock(unifName)

                self.connWrap.execSql("insert into datablocksexternal("
                        "unifiedname, filepath, filenamelowercase, "
                        "filesignature) values (?, ?, ?, ?)",
                        (unifName, filePath, fileName.lower(),
                        sqlite.Binary(fileSig)))

            except (IOError, OSError, sqlite.Error), e:
                traceback.print_exc()
                raise DbWriteAccessError(e)


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
                # The entry is in an external file, so delete it
                os.unlink(longPathEnc(join(self.dataDir, filePath)))
                self.connWrap.execSql(
                        "delete from datablocksexternal "
                        "where unifiedname = ?", (unifName,))

        except (IOError, OSError, sqlite.Error), e:
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
        for word in self.getAllDefinedWikiPageNames():  #glob.glob(join(self.dataDir, '*.wiki')):
            if word in exclusionSet:
                continue
            try:
                fileContents = self.getContent(word)
            except WikiFileNotFoundException:
                # some error in cache (should not happen)
                continue

            if sarOp.testWikiPage(word, fileContents) == True:
                result.add(word)

        return result


    # ---------- Miscellaneous ----------

    _CAPABILITIES = {
        "rebuild": 1,
        "compactify": 1,     # = sqlite vacuum
#         "versioning": 1,     # TODO (old versioning)
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


        # TODO drop and recreate tables and indices!
    def clearCacheTables(self):
        """
        Clear all tables in the database which contain non-essential
        (cache) information as well as other cache information.
        Needed before rebuilding the whole wiki
        """
        try:
            self.connWrap.syncCommit()

            self.cachedContentNames = None
            self.cachedGlobalProps = None

            self.fullyResetMetaDataState()

            DbStructure.recreateCacheTables(self.connWrap)
            self.connWrap.syncCommit()
        except (IOError, OSError, sqlite.Error), e:
            traceback.print_exc()
            raise DbWriteAccessError(e)


    def setDbSettingsValue(self, key, value):
        assert isinstance(value, basestring)
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
        except (IOError, OSError, sqlite.Error), e:
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
        except (IOError, OSError, sqlite.Error), e:
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
        except (IOError, OSError, sqlite.Error), e:
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
        except (IOError, OSError, sqlite.Error), e:
            traceback.print_exc()
            raise DbWriteAccessError(e)



#     # ---------- Versioning (optional) ----------
#     # Must be implemented if checkCapability returns a version number
#     #     for "versioning".
#         
#     def storeModification(self, word):
#         """ Store the modification for a single word (wikicontent and headversion for the word must exist)
#         between wikicontents and headversion in the changelog.
#         Does not modify headversion. It is recommended to not call this directly
# 
#         Values for the op-column in the changelog:
#         0 set content: set content as it is in content column
#         1 modify: content is a binary compact diff as defined in StringOps,
#             apply it to new revision to get the old one.
#         2 create page: content contains data of the page
#         3 delete page: content is undefined
#         """
# 
#         content, moddate = self.getContentAndInfo(word)[:2]
# 
#         headcontent, headmoddate = self.connWrap.execSqlQuery("select content, modified from headversion "+\
#                 "where word=?", (word,))[0]
# 
#         bindiff = getBinCompactForDiff(content, headcontent)
#         self.connWrap.execSql("insert into changelog (word, op, content, moddate) values (?, ?, ?, ?)",
#                 (word, 1, sqlite.Binary(bindiff), headmoddate))  # Modify  # TODO: Support overwrite
#         return self.connWrap.lastrowid
# 
# 
#     def hasVersioningData(self):
#         """
#         Returns true iff any version information is stored in the database
#         """
#         return DbStructure.hasVersioningData(self.connWrap)
# 
# 
#     def storeVersion(self, description):
#         """
#         Store the current version of a wiki in the changelog
# 
#         Values for the op-column in the changelog:
#         0 set content: set content as it is in content column
#         1 modify: content is a binary compact diff as defined in StringOps,
#             apply it to new revision to get the old one.
#         2 create page: content contains data of the page
#         3 delete page: content is undefined
# 
#         Renaming is not supported directly.
#         """
#         # Test if tables were created already
# 
#         if not DbStructure.hasVersioningData(self.connWrap):
#             # Create the tables
#             self.connWrap.commit()
#             try:
#                 DbStructure.createVersioningTables(self.connWrap)
#                 # self.connWrap.commit()
#             except:
#                 self.connWrap.rollback()
#                 raise
# 
#         self.connWrap.commit()
#         try:
#             # First move head version to normal versions
#             headversion = self.connWrap.execSqlQuery("select description, "+\
#                     "created from versions where id=0") # id 0 is the special head version
#             if len(headversion) == 1:
#                 firstchangeid = self.connWrap.execSqlQuerySingleItem("select id from changelog order by id desc limit 1 ",
#                         default = -1) + 1
# 
#                 # Find modified words
#                 modwords = self.connWrap.execSqlQuerySingleColumn("select headversion.word from headversion inner join "+\
#                         "wikiwordcontent on headversion.word = wikiwordcontent.word where "+\
#                         "headversion.modified != wikiwordcontent.modified")
# 
#                 for w in modwords:
#                     self.storeModification(w)
# 
# 
#                 # Store changes for deleted words
#                 self.connWrap.execSql("insert into changelog (word, op, content, moddate) "+\
#                         "select word, 2, content, modified from headversion where "+\
#                         "word not in (select word from wikiwordcontent)")
# 
#                 # Store changes for inserted words
#                 self.connWrap.execSql("insert into changelog (word, op, content, moddate) "+\
#                         "select word, 3, x'', modified from wikiwordcontent where "+\
#                         "word not in (select word from headversion)")
# 
#                 if firstchangeid == (self.connWrap.execSqlQuerySingleItem("select id from changelog order by id desc limit 1 ",
#                         default = -1) + 1):
# 
#                     firstchangeid = -1 # No changes recorded in changelog
# 
#                 headversion = headversion[0]
#                 self.connWrap.execSql("insert into versions(description, firstchangeid, created) "+\
#                         "values(?, ?, ?)", (headversion[0], firstchangeid, headversion[1]))
# 
#             self.connWrap.execSql("insert or replace into versions(id, description, firstchangeid, created) "+\
#                     "values(?, ?, ?, ?)", (0, description, -1, time()))
# 
#             # Copy from wikiwordcontent everything to headversion
#             self.connWrap.execSql("delete from headversion")
#             self.connWrap.execSql("insert into headversion select * from wikiwordcontent")
# 
#             self.connWrap.commit()
#         except:
#             self.connWrap.rollback()
#             raise
# 
# 
#     def getStoredVersions(self):
#         """
#         Return a list of tuples for each stored version with (<id>, <description>, <creation date>).
#         Newest versions at first
#         """
#         # Head version first
#         result = self.connWrap.execSqlQuery("select id, description, created "+\
#                     "from versions where id == 0")
# 
#         result += self.connWrap.execSqlQuery("select id, description, created "+\
#                     "from versions where id != 0 order by id desc")
#         return result
# 
# 
#     # TODO: Wrong moddate?
#     def applyChange(self, word, op, content, moddate):
#         """
#         Apply a single change to wikiwordcontent. word, op, content and modified have the
#         same meaning as in the changelog table
#         """
#         if op == 0:
#             self.setContentRaw(word, content, moddate)
#         elif op == 1:
#             self.setContentRaw(word, applyBinCompact(self.getContent(word), content), moddate)
#         elif op == 2:
#             self.setContentRaw(word, content, moddate)
#         elif op == 3:
#             self.deleteContent(word)
# 
# 
#     # TODO: Wrong date?, more efficient
#     def applyStoredVersion(self, id):
#         """
#         Set the content back to the version identified by id (retrieved by getStoredVersions).
#         Only wikiwordcontent is modified, the cache information must be updated separately
#         """
# 
#         self.connWrap.commit()
#         try:
#             # Start with head version
#             self.connWrap.execSql("delete from wikiwordcontent") #delete all rows
#             self.connWrap.execSql("insert into wikiwordcontent select * from headversion") # copy from headversion
# 
#             if id != 0:
#                 lowestchangeid = self.connWrap.execSqlQuerySingleColumn("select firstchangeid from versions where id == ?",
#                         (id,))
#                 if len(lowestchangeid) == 0:
#                     raise WikiFileNotFoundException()  # TODO: Better exception
# 
#                 lowestchangeid = lowestchangeid[0]
# 
#                 changes = self.connWrap.execSqlQuery("select word, op, content, moddate from changelog "+\
#                         "where id >= ? order by id desc", (lowestchangeid,))
# 
#                 for c in changes:
#                     self.applyChange(*c)
# 
# 
#             self.connWrap.commit()
#         except:
#             self.connWrap.rollback()
#             raise
# 
# 
#     def deleteVersioningData(self):
#         """
#         Completely delete all versioning information
#         """
#         DbStructure.deleteVersioningTables(self.connWrap)


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
        except (IOError, OSError, sqlite.Error), e:
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


#         self.cachedContentNames = {}
# 
#         # cache aliases
#         aliases = self.getAllAliases()
#         for alias in aliases:
#             self.cachedContentNames[alias] = 2
# 
#         # recreate word caches
#         for word in self.getAllDefinedContentNames():
#             self.cachedContentNames[word] = 1



#         finally:            
#             progresshandler.close()


    def commit(self):
        """
        Do not call from this class, only from outside to handle errors.
        """
        try:
            self.connWrap.commit()
        except (IOError, OSError, sqlite.Error), e:
            traceback.print_exc()
            raise DbWriteAccessError(e)


    def rollback(self):
        """
        Do not call from this class, only from outside to handle errors.
        """
        try:
            self.connWrap.rollback()
        except (IOError, OSError, sqlite.Error), e:
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
        except (IOError, OSError, sqlite.Error), e:
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
