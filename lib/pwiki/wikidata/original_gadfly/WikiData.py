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

try:
#     tracer.runctx('import gadfly', globals(), locals())
    import gadfly
except ImportError:
#     traceback.print_exc()
    gadfly = None
# finally:
#     pass

if gadfly is not None:
    import DbStructure
    from DbStructure import createWikiDB


import Consts
from pwiki.WikiExceptions import *   # TODO make normal import?
from pwiki import SearchAndReplace

from pwiki.StringOps import longPathEnc, longPathDec, utf8Enc, utf8Dec, BOM_UTF8, \
        fileContentToUnicode, loadEntireTxtFile, loadEntireFile, \
        writeEntireFile, Conjunction, iterCompatibleFilename, \
        getFileSignatureBlock, lineendToInternal, guessBaseNameByFilename, \
        createRandomString


class WikiData:
    "Interface to wiki data."
    def __init__(self, wikiDocument, dataDir, tempDir):
        self.wikiDocument = wikiDocument
        self.dataDir = dataDir
        self.connWrap = None
        self.cachedContentNames = None
        # tempDir is ignored
        
        # Only if this is true, the database is called to commit.
        # This is necessary for read-only databases
        self.commitNeeded = False

        try:
            conn = gadfly.gadfly("wikidb", self.dataDir)
        except (IOError, OSError, ValueError), e:
            traceback.print_exc()
            raise DbReadAccessError(e)

        self.connWrap = DbStructure.ConnectWrap(conn)
        try:
            self.pagefileSuffix = self.wikiDocument.getWikiConfig().get("main",
                    "db_pagefile_suffix", u".wiki")
        except (IOError, OSError, ValueError), e:
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
            except:
                self.connWrap.rollback()
                raise

        lastException = None
        try:
            # Further possible updates   
            DbStructure.updateDatabase2(self.connWrap)
        except (IOError, OSError, ValueError), e:
            # Remember but continue
            lastException = DbWriteAccessError(e)

        try:
            # Set marker for database type
            self.wikiDocument.getWikiConfig().set("main", "wiki_database_type",
                    "original_gadfly")
        except (IOError, OSError, ValueError), e:
            # Remember but continue
            lastException = DbWriteAccessError(e)

        # create word caches
        self.cachedContentNames = None

        try:
#             # cache aliases
#             aliases = self.getAllAliases()
#             for alias in aliases:
#                 self.cachedContentNames[alias] = 2
#     
#             # Cache real words
#             for word in self.getAllDefinedContentNames():
#                 self.cachedContentNames[word] = 1
#     
            self.cachedGlobalProps = None
            self.getGlobalProperties()
        except (IOError, OSError, ValueError), e:
            traceback.print_exc()
            try:
                self.connWrap.rollback()
            except (IOError, OSError, ValueError), e2:
                traceback.print_exc()
                raise DbReadAccessError(e2)
            raise DbReadAccessError(e)

        if lastException:
            raise lastException


    # ---------- Direct handling of page data ----------

    def getContent(self, word):
        try:
#             if (not exists(self.getWikiWordFileName(word))):
#                 raise WikiFileNotFoundException(
#                         _(u"Wiki page not found for word: %s") % word)

            content = loadEntireTxtFile(self.getWikiWordFileName(word))

            return fileContentToUnicode(content)
        except (IOError, OSError, ValueError), e:
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
        except (IOError, OSError, ValueError), e:
            traceback.print_exc()
            raise DbReadAccessError(e)

        try:
            if len(data) < 1:
                if creadate is None:
                    creadate = ti

                fileName = self.createWikiWordFileName(word)
                self.connWrap.execSqlInsert("wikiwords", ("word", "created", 
                        "modified", "presentationdatablock", "filepath",
                        "filenamelowercase"),
                        (word, creadate, moddate, "", fileName,
                        fileName.lower()))
            else:
                self.connWrap.execSql("update wikiwords set modified = ? "
                        "where word = ?", (moddate, word))
                        
            self.cachedContentNames = None
            self.commitNeeded = True
        except (IOError, OSError, ValueError), e:
            traceback.print_exc()
            raise DbWriteAccessError(e)


    def setContent(self, word, content, moddate = None, creadate = None):
        """
        Store unicode text for wikiword word, regardless if previous
        content exists or not. creadate will be used for new content
        only.
        
        moddate -- Modification date to store or None for current
        creadate -- Creation date to store or None for current        
        """
        try:
            self._updatePageEntry(word, moddate, creadate)

            filePath = self.getWikiWordFileName(word)
            writeEntireFile(filePath, content, True)

            fileSig = getFileSignatureBlock(filePath)
            self.connWrap.execSql("update wikiwords set filesignature = ?, "
                    "metadataprocessed = ? where word = ?", (fileSig, 0, word))

        except (IOError, OSError, ValueError), e:
            traceback.print_exc()
            raise DbWriteAccessError(e)


    def renameContent(self, oldWord, newWord):
        """
        The content which was stored under oldWord is stored
        after the call under newWord. The self.cachedContentNames
        dictionary is invalidated, other caches are transferred.
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
                    "filenamelowercase = ?, metadataprocessed = ? where word = ?",
                    (newWord, newFilePath, fileName.lower(), 0, oldWord))
            self.commitNeeded = True

###            del self._getCachedContentNames()[oldWord]
###            self._getCachedContentNames()[newWord] = 1
        except (IOError, OSError, ValueError), e:
            traceback.print_exc()
            raise DbWriteAccessError(e)



    def deleteContent(self, word):
        try:
            fileName = self.getWikiWordFileName(word)
            self.connWrap.execSql("delete from wikiwords where word = ?",
                    (word,))
            self.commitNeeded = True
            self.cachedContentNames = None
            if exists(fileName):
                os.unlink(fileName)
        except (IOError, OSError, ValueError), e:
            traceback.print_exc()
            raise DbWriteAccessError(e)


    def getTimestamps(self, word):
        """
        Returns a tuple with modification, creation and visit date of
        a word or (None, None, None) if word is not in the database
        """
        try:
            dates = self.connWrap.execSqlQuery(
                    "select modified, created from wikiwords where word = ?",
                    (word,))
    
            if len(dates) > 0:
                return (float(dates[0][0]), float(dates[0][1]), 0.0)
            else:
                return (None, None, None)  # ?
        except (IOError, OSError, ValueError), e:
            traceback.print_exc()
            raise DbReadAccessError(e)


    def setTimestamps(self, word, timestamps):
        """
        Set timestamps for an existing wiki page.
        """
        moddate, creadate = timestamps[:2]

        try:
            data = self.connWrap.execSqlQuery("select word from wikiwords "
                    "where word = ?", (word,))
        except (IOError, OSError, ValueError), e:
            traceback.print_exc()
            raise DbReadAccessError(e)

        try:
            if len(data) < 1:
                raise WikiFileNotFoundException
            else:
                self.connWrap.execSql("update wikiwords set modified = ?, "
                        "created = ? where word = ?", (moddate, creadate, word))
                self.commitNeeded = True
        except (IOError, OSError, ValueError), e:
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
                converters.append(lambda s: 0.0)
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
        except (IOError, OSError, ValueError), e:
            traceback.print_exc()
            raise DbReadAccessError(e)




    # ---------- Renaming/deleting pages with cache update or invalidation ----------

    def renameWord(self, word, toWord):
        # commit anything pending so we can rollback on error
        self.commitNeeded = True
        self.commit()
        try:
            try:
                self.connWrap.execSql("update wikirelations set word = ? where word = ?", (toWord, word))
                self.connWrap.execSql("update wikiwordprops set word = ? where word = ?", (toWord, word))
                self.connWrap.execSql("update todos set word = ? where word = ?", (toWord, word))
                self.connWrap.execSql("update wikiwordmatchterms set word = ? where word = ?", (toWord, word))
                self.renameContent(word, toWord)
                self.commitNeeded = True
                self.commit()
            except:
                self.connWrap.rollback()
                raise
        except (IOError, OSError, ValueError), e:
            traceback.print_exc()
            raise DbWriteAccessError(e)


    def deleteWord(self, word):
        """
        delete everything about the wikiword passed in. an exception is raised
        if you try and delete the wiki root node.
        """
        if word != self.wikiDocument.getWikiName():
            try:
                try:
                    self.commit()
                    # don't delete the relations to the word since other
                    # pages still have valid outward links to this page.
                    # just delete the content
    
                    self.deleteChildRelationships(word)
                    self.deleteProperties(word)
                    self.deleteTodos(word)
                    self.deleteContent(word)
                    self.deleteWikiWordMatchTerms(word, syncUpdate=False)
                    self.deleteWikiWordMatchTerms(word, syncUpdate=True)
                    self.commit()
                except:
                    self.connWrap.rollback()
                    raise
            except (IOError, OSError, ValueError), e:
                traceback.print_exc()
                raise DbWriteAccessError(e)
                
            try:
                # due to some bug we have to close and reopen the db sometimes
                self.connWrap.close()
                conn = gadfly.gadfly("wikidb", self.dataDir)
                self.connWrap = DbStructure.ConnectWrap(conn)
            except (IOError, OSError, ValueError), e:
                traceback.print_exc()
                raise DbReadAccessError(e)
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
            self.commitNeeded = True
        except (IOError, OSError, ValueError), e:
            traceback.print_exc()
            raise DbWriteAccessError(e)


    def getMetaDataState(self, word):
        """
        Retrieve meta-data processing state of a particular wiki word.
        """
        try:
            return self.connWrap.execSqlQuerySingleItem("select metadataprocessed "
                    "from wikiwords where word = ?", (word,))
        except (IOError, OSError, ValueError), e:
            traceback.print_exc()
            raise DbReadAccessError(e)


    def fullyResetMetaDataState(self, state=0):
        """
        Reset state of all wikiwords.
        """
        self.connWrap.execSql("update wikiwords set metadataprocessed = ?",
                (state,))
        self.commitNeeded = True


    def getWikiWordsForMetaDataState(self, state):
        """
        Retrieve a list of all words with a particular meta-data processing
        state.
        """
        try:
            return self.connWrap.execSqlQuerySingleColumn("select word "
                    "from wikiwords where metadataprocessed = ?", (state,))
        except (IOError, OSError, ValueError), e:
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
                    (word,), strConv=False)
            
            return dbFileSig == fileSig
        except (IOError, OSError, ValueError), e:
            traceback.print_exc()
            raise DbReadAccessError(e)


    def refreshFileSignatureForWord(self, word):
        """
        Sets file signature to match current file.
        """
        try:
            filePath = self.getWikiWordFileName(word)
            fileSig = getFileSignatureBlock(filePath)
        except (IOError, OSError, ValueError), e:
            traceback.print_exc()
            raise DbReadAccessError(e)

        try:
            self.connWrap.execSql("update wikiwords set filesignature = ? "
                    "where word = ?", (fileSig, word))
        except (IOError, OSError, ValueError), e:
            traceback.print_exc()
            raise DbWriteAccessError(e)



#             self.execSql("update wikiwords set filesignature = ?, "
#                     "metadataprocessed = ? where word = ?", (fileSig, 0, word))
# 
#                     fileSig = getFileSignatureBlock(fullPath)

    

    # ---------- Handling of relationships cache ----------

    def _getAllRelations(self):
        "get all of the relations in the db"
        relations = []
        try:
            data = self.connWrap.execSqlQuery("select word, relation "
                    "from wikirelations")
        except (IOError, OSError, ValueError), e:
            traceback.print_exc()
            raise DbReadAccessError(e)

        for row in data:
            relations.append((row[0], row[1]))
        return relations

    def getChildRelationships(self, wikiWord, existingonly=False,
            selfreference=True, withFields=()):
        """
        get the child relations of this word
        existingonly -- List only existing wiki words
        selfreference -- List also wikiWord if it references itself
        withFields -- Seq. of names of fields which should be included in
            the output. If this is not empty, tuples are returned
            (relation, ...) with ... as further fields in the order mentioned
            in withfields.

            Possible field names:
                "firstcharpos": position of link in page (may be -1 to represent
                    unknown). The Gadfly implementation always returns -1
                "modified": Modification date

        """
        # TODO moddateLookup should also process aliases?
        def moddateLookup(rel):
            result = self.getTimestamps(rel)[0]
            if result is None:
                return 0

            return result

        if withFields is None:
            withFields = ()

        addFields = ""
        converters = [lambda s: s]
        for field in withFields:
            if field == "firstcharpos":
                addFields += ", relation" # Dummy field
                converters.append(lambda s: -1)
            elif field == "modified":
                addFields += ", relation"
                converters.append(moddateLookup)

        sql = "select relation%s from wikirelations where word = ?" % addFields

        if len(withFields) == 0:
            try:
                children = self.connWrap.execSqlQuerySingleColumn(sql,
                        (wikiWord,))
            except (IOError, OSError, ValueError), e:
                traceback.print_exc()
                raise DbReadAccessError(e)

            if not selfreference:
                try:
                    children.remove(wikiWord)
                except ValueError:
                    pass

            if existingonly:
                children = [c for c in children if self.getUnAliasedWikiWord(c)]
        else:
            try:
                children = self.connWrap.execSqlQuery(sql, (wikiWord,))
            except (IOError, OSError, ValueError), e:
                traceback.print_exc()
                raise DbReadAccessError(e)

            newChildren = []
            for c in children:
                newC = tuple((conv(item) for item, conv in zip(c, converters)))
                if not selfreference and newC[0] == wikiWord:
                    continue

                if existingonly and not self.getUnAliasedWikiWord(newC[0]):
                    continue

                newChildren.append(newC)

            children = newChildren

        return children


#     # TODO More efficient
#     def _hasChildren(self, wikiWord, existingonly=False,
#             selfreference=True):
#         return len(self.getChildRelationships(wikiWord, existingonly,
#                 selfreference)) > 0
#                 
#     # TODO More efficient                
#     def getChildRelationshipsAndHasChildren(self, wikiWord, existingonly=False,
#             selfreference=True):
#         """
#         get the child relations to this word as sequence of tuples
#             (<child word>, <has child children?>). Used when expanding
#             a node in the tree control.
#         existingonly -- List only existing wiki words
#         selfreference -- List also wikiWord if it references itself
#         """
#         children = self.getChildRelationships(wikiWord, existingonly,
#                 selfreference)
#                 
#         return map(lambda c: (c, self._hasChildren(c, existingonly,
#                 selfreference)), children)

    def getParentRelationships(self, wikiWord):
        "get the parent relations to this word"

        # Parents of the real word
        realWord = self.getUnAliasedWikiWord(wikiWord)
        if realWord is None:
            realWord = wikiWord
        try:
            parents = set(self.connWrap.execSqlQuerySingleColumn(
                    "select word from wikirelations where relation = ?", (realWord,)))
            
            otherTerms = self.connWrap.execSqlQuery(
                    "select matchterm, type from wikiwordmatchterms "
                    "where word = ?", (realWord,))

            for matchterm, typ in otherTerms:
                if not typ & Consts.WIKIWORDMATCHTERMS_TYPE_ASLINK:
                    continue

                parents.update(self.connWrap.execSqlQuerySingleColumn(
                    "select word from wikirelations where relation = ?",
                    (matchterm,)))

#             # Plus parents of aliases
#             aliases = [v for k, v in self.getPropertiesForWord(wikiWord)
#                     if k == u"alias"]
#     
#             for al in aliases:
#                 parents.update(self.connWrap.execSqlQuerySingleColumn(
#                     "select word from wikirelations where relation = ?", (al,)))

        except (IOError, OSError, ValueError), e:
            traceback.print_exc()
            raise DbReadAccessError(e)

        return list(parents)


    def getParentlessWikiWords(self):
        """
        get the words that have no parents.
        
        NO LONGER VALID: (((also returns nodes that have files but
        no entries in the wikiwords table.)))
        """
        wordSet = set(self.getAllDefinedWikiPageNames())

        # Remove all which have parents
        for word, relation in self._getAllRelations():
            relation = self.getUnAliasedWikiWord(relation)
            if relation is None or word == relation:
                continue

            wordSet.discard(relation)

        # Create a list of them
        words = list(wordSet)
#         words.sort()
        
        return words


    def getUndefinedWords(self):
        """
        List words which are childs of a word but are not defined, neither
        directly nor as alias.
        """
        relations = self._getAllRelations()
        childWords = set([relation for word, relation in relations])
        
        return [word for word in childWords
                if not self.getUnAliasedWikiWord(word)]


    def _addRelationship(self, word, rel):
        """
        Add a relationship from word to rel. rel is a tuple (toWord, pos).
        The Gadfly implementation ignores pos.
        Returns True if relation added.
        A relation from one word to another is unique and can't be added twice.
        """
        try:
            data = self.connWrap.execSqlQuery("select relation "
                    "from wikirelations where word = ? and relation = ?",
                    (word, rel[0]))
        except (IOError, OSError, ValueError), e:
            traceback.print_exc()
            raise DbReadAccessError(e)

        returnValue = False
        if len(data) < 1:
            try:
                self.connWrap.execSqlInsert("wikirelations", ("word", "relation",
                        "created"), (word, rel[0], time()))
                self.commitNeeded = True
            except (IOError, OSError, ValueError), e:
                traceback.print_exc()
                raise DbWriteAccessError(e)

            returnValue = True
        return returnValue

    def updateChildRelations(self, word, childRelations):
        self.deleteChildRelationships(word)
        self.getExistingWikiWordInfo(word)
        for r in childRelations:
            self._addRelationship(word, r)

    def deleteChildRelationships(self, fromWord):
        try:
            self.connWrap.execSql("delete from wikirelations where word = ?",
                    (fromWord,))
            self.commitNeeded = True
        except (IOError, OSError, ValueError), e:
            traceback.print_exc()
            raise DbWriteAccessError(e)


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


    def findBestPathFromWordToWord( self, word, toWord ):
        """
        Do a breadth first search, which will find the shortest
        path between the nodes we are interested in
        This will only find a path if the words are
        linked by parent relationship
        you won't be able to find your cousins
        """
        queue = [word]
        previous = { word: word }
        while queue:
            node = queue.pop(0)
            if node == toWord: # If we've found our target word.
                # Work out how we got here.
                path = [node]
                while previous[node] != node:
                    node = previous[node]
                    path.append( node )
                return path

            # Continue on up the tree.
            for parent in self.getParentRelationships(node):
                # unless we've been to this parent before.
                if parent not in previous and parent not in queue:
                    previous[parent] = node
                    queue.append( parent )

        # We didn't find a path to our target word
        return None




    # ---------- Listing/Searching wiki words (see also "alias handling", "searching pages")----------

#     def getAllDefinedWikiPageNames(self):
#         "get the names of all wiki pages in the db, no aliases"
#         wikiWords = self.getAllDefinedContentNames()
#         # Filter out functional 'words'
#         wikiWords = [w for w in wikiWords if not w.startswith('[')]
#         return wikiWords

    def getAllDefinedContentNames(self):
        """
        Get the names of all the content elements in the db, no aliases.
        Content elements are wiki pages plus functional pages and possible
        other data, their names begin with '['
        """
        try:
            return self.connWrap.execSqlQuerySingleColumn("select word "
                    "from wikiwords")
        except (IOError, OSError, ValueError), e:
            traceback.print_exc()
            raise DbReadAccessError(e)
            
    getAllDefinedWikiPageNames = getAllDefinedContentNames



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

        except (IOError, OSError, ValueError), e:
            traceback.print_exc()
            raise DbWriteAccessError(e)


    def refreshDefinedContentNames(self):
        """
        Refreshes the internal list of defined pages which
        may be different from the list of pages for which
        content is available (if .wiki files were added or removed).
        The function tries to conserve additional informations
        (creation/modif. date) if possible.
        
        It is mainly called during rebuilding of the wiki 
        so it must not rely on the presence of other cache
        information (e.g. relations)

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
                    self.commitNeeded = True

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
                    self.connWrap.execSqlInsert("wikiwords", ("word", "created", 
                            "modified", "filepath", "filenamelowercase",
                            "filesignature"),
                            (wikiWord, ti, st.st_mtime, path, path.lower(), fileSig))
                    self.commitNeeded = True

        except (IOError, OSError, ValueError), e:
            traceback.print_exc()
            raise DbWriteAccessError(e)


    def _getCachedContentNames(self):
        try:
            if self.cachedContentNames is None:
                result = {}
        
                for matchterm, typ, word in self.connWrap.execSqlQuery(
                        "select matchterm, type, word from wikiwordmatchterms"):
    
                    if not (typ & Consts.WIKIWORDMATCHTERMS_TYPE_ASLINK):
                        continue
                    result[matchterm] = word

                result.update((word, word)
                        for word in self.getAllDefinedWikiPageNames())

                self.cachedContentNames = result

            return self.cachedContentNames
        except (IOError, OSError, ValueError), e:
            traceback.print_exc()
            raise DbReadAccessError(e)


    # TODO More general Wikiword to filename mapping
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

        except (IOError, OSError, ValueError), e:
            traceback.print_exc()
            raise DbReadAccessError(e)


    def _getAllWikiFileNamesFromDb(self):   # Used for rebuilding wiki
        try:
            return self.connWrap.execSqlQuerySingleColumn("select filepath "
                    "from wikiwords")

        except (IOError, OSError, ValueError), e:
            traceback.print_exc()
            raise DbReadAccessError(e)


    def getWikiWordFileNameRaw(self, wikiWord):
        """
        Not part of public API!
        """
        try:
            path = self.connWrap.execSqlQuerySingleItem("select filepath "
                    "from wikiwords where word = ?", (wikiWord,))
        except (IOError, OSError, ValueError), e:
            traceback.print_exc()
            raise DbReadAccessError(e)

        if path is None:
            raise WikiFileNotFoundException(
                    _(u"Wiki page not found for word: %s") % wikiWord)
        
        return path


    def getWikiWordFileName(self, wikiWord):
        """
        Not part of public API!
        """
        path = self.getWikiWordFileNameRaw(wikiWord)
        
        return longPathEnc(join(self.dataDir, path))


    def createWikiWordFileName(self, wikiWord):
        """
        Create a filename for wikiWord which is not yet in the database or
        a file with that name in the data directory
        """
        icf = iterCompatibleFilename(wikiWord, self.pagefileSuffix)
        try:
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
        except (IOError, OSError, ValueError), e:
            traceback.print_exc()
            raise DbReadAccessError(e)




    def isDefinedWikiPage(self, word):
        try:
            return bool(self.connWrap.execSqlQuerySingleItem(
                    "select word from wikiwords where word = ?", (word,)))
        except (IOError, OSError, ValueError), e:
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

#         try:
#             otherTerms = self.connWrap.execSqlQuery("select matchterm, type "
#                     "from wikiwordmatchterms")
#         except (IOError, OSError, ValueError), e:
#             traceback.print_exc()
#             raise DbReadAccessError(e)
# 
#         result = [match for match, typ in otherTerms
#                 if typ & Consts.WIKIWORDMATCHTERMS_TYPE_ASLINK]
# 
#         return result


    def getWikiLinksStartingWith(self, thisStr, includeAliases=False, 
            caseNormed=False):
        "get the list of words starting with thisStr. used for autocompletion."
        if caseNormed:
            thisStr = thisStr.lower()   # TODO More general normcase function

            try:
                foundTerms = self.connWrap.execSqlQuery(
                        "select matchterm, type "
                        "from wikiwordmatchterms")

            except (IOError, OSError, ValueError), e:
                traceback.print_exc()
                raise DbReadAccessError(e)

            return [matchterm for matchterm, typ in foundTerms
                    if matchterm.lower().startswith(thisStr) and
                    (typ & Consts.WIKIWORDMATCHTERMS_TYPE_ASLINK)]

        else:
            try:
                foundTerms = self.connWrap.execSqlQuery(
                        "select matchterm, type "
                        "from wikiwordmatchterms")
                
                words = set(matchterm for matchterm, typ in foundTerms
                        if matchterm.startswith(thisStr) and
                        (typ & Consts.WIKIWORDMATCHTERMS_TYPE_ASLINK))

                # To ensure that at least all real wikiwords are found
                
                realWords = self.connWrap.execSqlQuerySingleColumn("select word "
                    "from wikiwords")
                
                words.update(word for word in realWords
                        if word.startswith(thisStr))
                        
                return list(words)

                
            except (IOError, OSError, ValueError), e:
                traceback.print_exc()
                raise DbReadAccessError(e)

        
        
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
#         "get the list of words with thisStr in them."
#         thisStr = thisStr.lower()   # TODO More general normcase function
# 
# 
#         result1 = [word for word in self.getAllDefinedWikiPageNames()
#                 if word.lower().startswith(thisStr)]
# 
#         if includeAliases:
#             result1 += [word for word in self.getAllAliases()
#                     if word.lower().startswith(thisStr)]
# 
# 
#         result2 = [word for word in self.getAllDefinedWikiPageNames()
#                 if word.lower().find(thisStr) != -1 and
#                 not word.lower().startswith(thisStr)]
# 
#         if includeAliases:
#             result2 += [word for word in self.getAllAliases()
#                     if word.lower().find(thisStr) != -1 and
#                     not word.lower().startswith(thisStr)]
# 
#         coll = self.wikiDocument.getCollator()
#         
#         coll.sort(result1)
#         coll.sort(result2)
# 
#         return result1 + result2


    def getWikiWordsModifiedWithin(self, startTime, endTime):
        """
        Function must work for read-only wiki.
        startTime and endTime are floating values as returned by time.time()
        startTime is inclusive, endTime is exclusive
        """
        try:
            rows = self.connWrap.execSqlQuery("select word, modified "
                    "from wikiwords")
        except (IOError, OSError, ValueError), e:
            traceback.print_exc()
            raise DbReadAccessError(e)
            
        return [row[0] for row in rows if float(row[1]) >= startTime and
                float(row[1]) < endTime and not row[0].startswith('[')]


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
            rows = self.connWrap.execSqlQuery("select word, %s from wikiwords" %
                    field)
        except (IOError, OSError, ValueError), e:
            traceback.print_exc()
            raise DbReadAccessError(e)

        minT = None
        maxT = None
        
        # Find initial record for setting min/max
        for i in xrange(len(rows)):
            row = rows[i]
            if row[0].startswith('[') or row[1] == 0.0:
                continue
            
            minT = row[1]
            maxT = row[1]
            break
        
        for i in xrange(i + 1, len(rows)):
            row = rows[i]
            if row[0].startswith('[') or row[1] == 0.0:
                continue

            minT = min(minT, row[1])
            maxT = max(maxT, row[1])
            
        return (minT, maxT)


    def getWikiWordsBefore(self, stampType, stamp, limit=None):
        """
        Get a list of tuples of wiki words and dates related to a particular
        time before stamp.
        
        stampType -- 0: Modification time, 1: Creation, 2: Last visit
        limit -- How much count entries to return or None for all
        """
        field = self._STAMP_TYPE_TO_FIELD.get(stampType)
        if field is None:
            # Visited not supported yet
            return []

        try:
            rows = self.connWrap.execSqlQuery("select word, %s from wikiwords" %
                    field)
        except (IOError, OSError, ValueError), e:
            traceback.print_exc()
            raise DbReadAccessError(e)

        rows = [row for row in rows if float(row[1]) < stamp and
                row[1] > 0]

        rows.sort(key=lambda row: row[1], reverse=True)

        if limit is not None:
            return rows[:limit]
        else:
            return rows


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

        try:
            rows = self.connWrap.execSqlQuery("select word, %s from wikiwords" %
                    field)
        except (IOError, OSError, ValueError), e:
            traceback.print_exc()
            raise DbReadAccessError(e)

        rows = [row for row in rows if float(row[1]) >= stamp]

        rows.sort(key=lambda row: row[1])

        if limit is not None:
            return rows[:limit]
        else:
            return rows


    def getFirstWikiWord(self):
        """
        Returns the name of the "first" wiki word. See getNextWikiWord()
        for details. Returns either an existing wiki word or None if no
        wiki words in database.
        """
        words = self.getAllDefinedWikiPageNames()
        words.sort()
        if len(words) == 0:
            return None
        return words[0]


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
        words = self.getAllDefinedWikiPageNames()
        words.sort()
        if len(words) == 0:
            return None
            
        try:
            i = words.index(currWord)
            i += 1
            if i == len(words):
                return None
            
            return words[i]
        except ValueError:
            None


    # ---------- Property cache handling ----------

    def getPropertyNames(self):
        """
        Return all property names not beginning with "global."
        """
        try:
            names = self.connWrap.execSqlQuerySingleColumn(
                    "select distinct(key) from wikiwordprops")
        except (IOError, OSError, ValueError), e:
            traceback.print_exc()
            raise DbReadAccessError(e)

        return [name for name in names if not name.startswith('global.')]

    def getPropertyNamesStartingWith(self, startingWith):
        try:
            names = self.connWrap.execSqlQuerySingleColumn(
                    "select distinct(key) from wikiwordprops")   #  order by key")
        except (IOError, OSError, ValueError), e:
            traceback.print_exc()
            raise DbReadAccessError(e)

        return [name for name in names if name.startswith(startingWith)]

    def getGlobalProperties(self):
        if self.cachedGlobalProps is None:
            try:
                data = self.connWrap.execSqlQuery(
                        "select key, value from wikiwordprops")  # order by key
            except (IOError, OSError, ValueError), e:
                traceback.print_exc()
                raise DbReadAccessError(e)
            globalMap = {}
            for (key, val) in data:
                if key.startswith('global.'):
                    globalMap[key] = val
            self.cachedGlobalProps = globalMap

        return self.cachedGlobalProps


    def getDistinctPropertyValues(self, key):
        try:
            return self.connWrap.execSqlQuerySingleColumn("select distinct(value) "
                    "from wikiwordprops where key = ?", (key,))  #  order by value
        except (IOError, OSError, ValueError), e:
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
        except (IOError, OSError, ValueError), e:
            traceback.print_exc()
            raise DbReadAccessError(e)


    def getWordsForPropertyName(self, key):
        try:
            return self.connWrap.execSqlQuerySingleColumn(
                    "select distinct(word) from wikiwordprops where key = ? ",
                    (key,))
        except (IOError, OSError, ValueError), e:
            traceback.print_exc()
            raise DbReadAccessError(e)


#     def getWordsWithPropertyValue(self, key, value):
#         words = []
#         try:
#             data = self.execSqlQuery("select word from wikiwordprops "
#                     "where key = ? and value = ?", (key, value))
#         except (IOError, OSError, ValueError), e:
#             traceback.print_exc()
#             raise DbReadAccessError(e)
# 
#         for row in data:
#             words.append(row[0])
#         return words


    def getPropertiesForWord(self, word):
        """
        Returns list of tuples (key, value) of key and value
        of all properties for word.
        """
        try:
            return self.connWrap.execSqlQuery("select key, value "+
                        "from wikiwordprops where word = ?", (word,))
        except (IOError, OSError, ValueError), e:
            traceback.print_exc()
            raise DbReadAccessError(e)


    def _setProperty(self, word, key, value):
        # make sure the value doesn't already exist for this property
        try:
            data = self.connWrap.execSqlQuery("select word from wikiwordprops "
                    "where word = ? and key = ? and value = ?",
                    (word, key, value))
        except (IOError, OSError, ValueError), e:
            traceback.print_exc()
            raise DbReadAccessError(e)
        # if it doesn't insert it
        returnValue = False
        if len(data) < 1:
            try:
                self.connWrap.execSqlInsert("wikiwordprops", ("word", "key",
                        "value"), (word, key, value))
                self.commitNeeded = True
            except (IOError, OSError, ValueError), e:
                traceback.print_exc()
                raise DbWriteAccessError(e)
            returnValue = True
        return returnValue

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


    def deleteProperties(self, word):
        try:
            self.connWrap.execSql("delete from wikiwordprops where word = ?",
                    (word,))
            self.commitNeeded = True
        except (IOError, OSError, ValueError), e:
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
        try:
            return self.connWrap.execSqlQuery("select word, todo from todos")
        except (IOError, OSError, ValueError), e:
            traceback.print_exc()
            raise DbReadAccessError(e)

    def getTodosForWord(self, word):
        """
        Returns list of all todo items of word
        """
        try:
            return self.connWrap.execSqlQuerySingleColumn("select todo from todos "
                    "where word = ?", (word,))
        except (IOError, OSError, ValueError), e:
            traceback.print_exc()
            raise DbReadAccessError(e)


    def updateTodos(self, word, todos):
        self.deleteTodos(word)
        self.getExistingWikiWordInfo(word)
        for t in todos:
            self._addTodo(word, t)


    def _addTodo(self, word, todo):
        try:
            self.connWrap.execSqlInsert("todos", ("word", "todo"), (word, todo))
            self.commitNeeded = True

#             self.execSql("insert into todos(word, todo) values (?, ?)", (word, todo))
        except (IOError, OSError, ValueError), e:
            traceback.print_exc()
            raise DbWriteAccessError(e)

    def deleteTodos(self, word):
        try:
            self.connWrap.execSql("delete from todos where word = ?", (word,))
            self.commitNeeded = True
        except (IOError, OSError, ValueError), e:
            traceback.print_exc()
            raise DbWriteAccessError(e)


    # ---------- Wikiword matchterm cache handling ----------

    def getWikiWordMatchTermsWith(self, thisStr):
        "get the list of match terms with thisStr in them."
        thisStr = thisStr.lower()   # TODO More general normcase function
        try:
            # TODO Check for name collisions
            foundTerms = self.connWrap.execSqlQuery(
                    "select matchterm, type, word, firstcharpos "
                    "from wikiwordmatchterms")
            
        except (IOError, OSError, ValueError), e:
            traceback.print_exc()
            raise DbReadAccessError(e)

        result1 = [term for term in foundTerms
            if term[0].lower().startswith(thisStr)]

        result2 = [term for term in foundTerms
                if term[0].lower().find(thisStr) > 0]

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
            self.connWrap.execSqlInsert("wikiwordmatchterms", ("matchterm",
                    "type", "word", "firstcharpos"),
                    (matchterm, typ, word, firstcharpos))
            self.commitNeeded = True
        except (IOError, OSError, ValueError), e:
            traceback.print_exc()
            raise DbWriteAccessError(e)

    def deleteWikiWordMatchTerms(self, word, syncUpdate=False):
        try:
            self.cachedContentNames = None
            foundTerms = self.connWrap.execSqlQuery(
                    "select matchterm, type, word, firstcharpos "
                    "from wikiwordmatchterms where word = ?", (word,))

            if not syncUpdate:
                for term in foundTerms:
                    if not term[1] & Consts.WIKIWORDMATCHTERMS_TYPE_SYNCUPDATE:
                        self.connWrap.execSql("delete from wikiwordmatchterms "
                                "where matchterm = ? and type = ? and word = ? and "
                                "firstcharpos = ?", term)

#                 self.connWrap.execSql("delete from wikiwordmatchterms "
#                         "where word = ?", (word,))
            else:
                for term in foundTerms:
                    if term[1] & Consts.WIKIWORDMATCHTERMS_TYPE_SYNCUPDATE:
                        self.connWrap.execSql("delete from wikiwordmatchterms "
                                "where matchterm = ? and type = ? and word = ? and "
                                "firstcharpos = ?", term)

            self.commitNeeded = True
        except (IOError, OSError, ValueError), e:
            traceback.print_exc()
            raise DbWriteAccessError(e)


    # ---------- Data block handling ----------

#     def getDataBlockUnifNames(self):
#         """
#         Return unified names of all stored data blocks.
#         """
        
    def getDataBlockUnifNamesStartingWith(self, startingWith):
        """
        Return all unified names starting with startingWith (case sensitive)
        """
        try:
            names1 = self.connWrap.execSqlQuerySingleColumn(
                    "select distinct(unifiedname) from datablocks")
                    
            names2 = self.connWrap.execSqlQuerySingleColumn(
                    "select distinct(unifiedname) from datablocksexternal")
        except (IOError, OSError, ValueError), e:
            traceback.print_exc()
            raise DbReadAccessError(e)

        return [name for name in names1 if name.startswith(startingWith)] + \
                [name for name in names2 if name.startswith(startingWith)]


    def retrieveDataBlock(self, unifName):
        """
        Retrieve data block as binary string.
        """
        try:
            datablock = self.connWrap.execSqlQuerySingleItem(
                    "select data from datablocks where unifiedname = ?",
                    (unifName,), strConv=False)
            if datablock is not None:
                return datablock
            
            filePath = self.connWrap.execSqlQuerySingleItem(
                    "select filepath from datablocksexternal where unifiedname = ?",
                    (unifName,))
            
            if filePath is None:
                return None  # TODO exception?
            
            datablock = loadEntireFile(join(self.dataDir, filePath))
            return datablock

        except (IOError, OSError, ValueError), e:
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
                        (unifName,), strConv=False)
            except (IOError, OSError, ValueError), e:
                traceback.print_exc()
                raise DbReadAccessError(e)

            try:
                if datablock is not None:
                    # It is in internal data blocks
                    self.connWrap.execSql("update datablocks set data = ? where "
                            "unifiedname = ?", (data, unifName))
                    return
                    
                # It may be in external data blocks
                self.deleteDataBlock(unifName)
                
                self.connWrap.execSqlInsert("datablocks", ("unifiedname",
                        "data"), (unifName, newdata))
                self.commitNeeded = True

            except (IOError, OSError, ValueError), e:
                traceback.print_exc()
                raise DbWriteAccessError(e)

        else:   # storeHint == Consts.DATABLOCK_STOREHINT_EXTERN
            try:
                filePath = self.connWrap.execSqlQuerySingleItem(
                        "select filepath from datablocksexternal "
                        "where unifiedname = ?", (unifName,))
            except (IOError, OSError, ValueError), e:
                traceback.print_exc()
                raise DbReadAccessError(e)

            try:
                if filePath is not None:
                    # The entry is already in an external file, so overwrite it
                    writeEntireFile(join(self.dataDir, filePath), newdata,
                            isinstance(newdata, unicode))

                    fileSig = getFileSignatureBlock(join(self.dataDir, filePath))
                    self.connWrap.execSql("update datablocksexternal "
                            "set filesignature = ?", (fileSig,))
                    self.commitNeeded = True
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

                self.connWrap.execSqlInsert("datablocksexternal",
                        ("unifiedname", "filepath", "filenamelowercase",
                        "filesignature"),
                        (unifName, fileName, fileName.lower(), fileSig))
                self.commitNeeded = True

            except (IOError, OSError, ValueError), e:
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
            self.commitNeeded = True
            
            filePath = self.connWrap.execSqlQuerySingleItem(
                    "select filepath from datablocksexternal "
                    "where unifiedname = ?", (unifName,))

            if filePath is not None:
                # The entry is in an external file, so delete it
                os.unlink(longPathEnc(join(self.dataDir, filePath)))
                self.connWrap.execSql(
                        "delete from datablocksexternal "
                        "where unifiedname = ?", (unifName,))

        except (IOError, OSError, ValueError), e:
            traceback.print_exc()
            raise DbWriteAccessError(e)




    # ---------- Searching pages ----------

    def search(self, sarOp, exclusionSet):
        """
        Search all wiki pages using the SearchAndReplaceOperation sarOp and
        return set of all page names that match the search criteria.
        sarOp.beginWikiSearch() must be called before calling this function,
        sarOp.endWikiSearch() must be called after calling this function.
        
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


#     def saveSearch(self, title, datablock):
#         try:
#             test = self.connWrap.execSqlQuerySingleItem(
#                     "select title from search_views where title = ?",
#                     (title,))
#         except (IOError, OSError, ValueError), e:
#             traceback.print_exc()
#             raise DbReadAccessError(e)
# 
#         try:
#             if test is not None:
#                 self.connWrap.execSql(
#                         "update search_views set datablock = ? where "+\
#                         "title = ?", (datablock, title))
#             else:
#                 self.connWrap.execSqlInsert("search_views", ("title", "datablock"),
#                         (title, datablock))
#             
#             self.commitNeeded = True
# 
#         except (IOError, OSError, ValueError), e:
#             traceback.print_exc()
#             raise DbWriteAccessError(e)


#     def getSavedSearchTitles(self):
#         """
#         Return the titles of all stored searches in alphabetical order
#         """
#         try:
#             return self.connWrap.execSqlQuerySingleColumn(
#                     "select title from search_views order by title")
#         except (IOError, OSError, ValueError), e:
#             traceback.print_exc()
#             raise DbReadAccessError(e)

#     def getSearchDatablock(self, title):
#         try:
#             return self.connWrap.execSqlQuerySingleItem(
#                     "select datablock from search_views where title = ?", (title,),
#                     strConv=False)
#         except (IOError, OSError, ValueError), e:
#             traceback.print_exc()
#             raise DbReadAccessError(e)

#     def deleteSavedSearch(self, title):
#         try:
#             self.connWrap.execSql(
#                     "delete from search_views where title = ?", (title,))
#             self.commitNeeded = True
#         except (IOError, OSError, ValueError), e:
#             traceback.print_exc()
#             raise DbWriteAccessError(e)



    # ---------- Miscellaneous ----------

    _CAPABILITIES = {
        "rebuild": 1
        }

    def checkCapability(self, capkey):
        """
        Check the capabilities of this WikiData implementation.
        The capkey names the capability, the function returns normally
        a version number or None if not supported
        """
        return WikiData._CAPABILITIES.get(capkey, None)

    def clearCacheTables(self):
        """
        Clear all tables in the database which contain non-essential
        (cache) information as well as other cache information.
        Needed before rebuilding the whole wiki
        """
        self.cachedContentNames = None
        self.cachedGlobalProps = None
        try:
            self.fullyResetMetaDataState()
            self.commit()

            DbStructure.recreateCacheTables(self.connWrap)
            self.commitNeeded = True
            self.commit()
        except (IOError, OSError, ValueError), e:
            traceback.print_exc()
            raise DbWriteAccessError(e)


    def setDbSettingsValue(self, key, value):
        assert isinstance(value, basestring)
        DbStructure.setSettingsValue(self.connWrap, key, value)
        self.commitNeeded = True


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
                    "word = ?", (datablock, word))
            self.commitNeeded = True
        except (IOError, OSError, ValueError), e:
            traceback.print_exc()
            raise DbWriteAccessError(e)


    def getPresentationBlock(self, word):
        """
        Returns the presentation datablock (a byte string).
        The function may return either an empty string or a valid datablock
        """
        try:
            return self.connWrap.execSqlQuerySingleItem(
                    "select presentationdatablock from wikiwords where word = ?",
                    (word,), strConv=False)
        except (IOError, OSError, ValueError), e:
            traceback.print_exc()
            raise DbReadAccessError(e)


    def testWrite(self):
        """
        Test if writing to database is possible. Throws a DbWriteAccessError
        if writing failed.
        TODO !
        """
        pass


    def close(self):
        self.commit()
        self.connWrap.close()


    # Not part of public API:

#     def execSql(self, sql, params=None):
#         "utility method, executes the sql, no return"
#         return self.connWrap.execSql(sql, params)
# 
#     def execSqlQuery(self, sql, params=None):
#         "utility method, executes the sql, returns query result"
#         return self.connWrap.execSqlQuery(sql, params)
# 
#     def execSqlQuerySingleColumn(self, sql, params=None):
#         "utility method, executes the sql, returns query result"
#         return self.connWrap.execSqlQuerySingleColumn(sql, params)

    def commit(self):
        if self.commitNeeded:
            self.connWrap.commit()
        
        self.commitNeeded = False
        
    def rollback(self):
        self.connWrap.rollback()
        self.commitNeeded = False
        

    # ---------- Other optional functionality ----------

    def cleanupAfterRebuild(self, progresshandler):
        """
        Rebuild cached structures, try to repair database inconsistencies.

        Must be implemented if checkCapability returns a version number
        for "rebuild".
        
        progresshandler -- Object, fulfilling the GuiProgressHandler
            protocol
        """
        DbStructure.rebuildIndices(self.connWrap)   # ?


####################################################
# module level functions
####################################################


# def findShortestPath(graph, start, end, path):   # path=[]
#     "finds the shortest path in the graph from start to end"
#     path = path + [start]
#     if start == end:
#         return path
#     if not graph.has_key(start):
#         return None
#     shortest = None
#     for node in graph[start]:
#         if node not in path:
#             newpath = findShortestPath(graph, node, end, path)
#             if newpath:
#                 if not shortest or len(newpath) < len(shortest):
#                     shortest = newpath
# 
#     return shortest



def listAvailableWikiDataHandlers():
    """
    Returns a list with the names of available handlers from this module.
    Each item is a tuple (<internal name>, <descriptive name>)
    """
    if gadfly is not None:
        return [("original_gadfly", "Original Gadfly")]
    else:
        return []


def getWikiDataHandler(name):
    """
    Returns a creation function (or class) for an appropriate
    WikiData object and a createWikiDB function or (None, None)
    if name is unknown
    """
    if name == "original_gadfly":
        return WikiData, createWikiDB
    
    return (None, None)
