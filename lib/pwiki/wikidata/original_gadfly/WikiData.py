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



from os import mkdir, unlink, rename, stat    # listdir
from os.path import exists, join, basename
from time import time, localtime
import datetime
import re, string, glob, sets, traceback

try:
    import gadfly
except ImportError:
    gadfly = None
# finally:
#     pass

if gadfly is not None:
    import DbStructure
    from DbStructure import createWikiDB


from pwiki.WikiExceptions import *   # TODO make normal import?
from pwiki import SearchAndReplace

from pwiki.StringOps import pathEnc, pathDec, utf8Enc, utf8Dec, BOM_UTF8, \
        fileContentToUnicode

from pwiki import WikiFormatting
from pwiki import PageAst

# from pwiki.DocPages import WikiPage


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
                DbStructure.updateDatabase(self.connWrap, self.dataDir)
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
        except (IOError, OSError), e:
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
            if (not exists(self.getWikiWordFileName(word))):
                raise WikiFileNotFoundException, \
                        u"wiki page not found for word: %s" % word
    
            fp = open(self.getWikiWordFileName(word), "rU")
            content = fp.read()
            fp.close()
    
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
            data = self.execSqlQuery("select word from wikiwords where word = ?",
                    (word,))
        except (IOError, OSError, ValueError), e:
            traceback.print_exc()
            raise DbReadAccessError(e)

        try:
            if len(data) < 1:
                if creadate is None:
                    creadate = ti
                    
                self.connWrap.execSqlInsert("wikiwords", ("word", "created", 
                        "modified", "presentationdatablock", "wordnormcase"),
                        (word, creadate, moddate, "", ""))

#                 self.execSql("insert into wikiwords(word, created, modified, "
#                         "presentationdatablock, wordnormcase) "
#                         "values (?, ?, ?, '', '')", (word, creadate, moddate))
            else:
                self.execSql("update wikiwords set modified = ? where word = ?",
                        (moddate, word))
                self.commitNeeded = True
        except (IOError, OSError, ValueError), e:
            traceback.print_exc()
            raise DbWriteAccessError(e)
                    
        self._getCachedContentNames()[word] = 1


    def setContent(self, word, content, moddate = None, creadate = None):
        """
        Store unicode text for wikiword word, regardless if previous
        content exists or not. creadate will be used for new content
        only.
        
        moddate -- Modification date to store or None for current
        creadate -- Creation date to store or None for current        
        """
        try:
            output = open(self.getWikiWordFileName(word), 'w')
            output.write(BOM_UTF8)
            output.write(utf8Enc(content)[0])
            output.close()
        except (IOError, OSError, ValueError), e:
            traceback.print_exc()
            raise DbWriteAccessError(e)
        
        self._updatePageEntry(word, moddate, creadate)


    def renameContent(self, oldWord, newWord):
        """
        The content which was stored under oldWord is stored
        after the call under newWord. The self.cachedContentNames
        dictionary is updated, other caches won't be updated.
        """
        try:
            self.execSql("update wikiwords set word = ? where word = ?",
                    (newWord, oldWord))
            self.commitNeeded = True
    
            rename(self.getWikiWordFileName(oldWord),
                    self.getWikiWordFileName(newWord))
            del self._getCachedContentNames()[oldWord]
            self._getCachedContentNames()[newWord] = 1
        except (IOError, OSError, ValueError), e:
            traceback.print_exc()
            raise DbWriteAccessError(e)



    def deleteContent(self, word):
        try:
            self.execSql("delete from wikiwords where word = ?", (word,))
            self.commitNeeded = True
            if exists(self.getWikiWordFileName(word)):
                unlink(self.getWikiWordFileName(word))
            del self._getCachedContentNames()[word]
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
        except (IOError, OSError, ValueError), e:
            traceback.print_exc()
            raise DbWriteAccessError(e)



    # ---------- Renaming/deleting pages with cache update ----------

    def renameWord(self, word, toWord):
        if not self.wikiDocument.getFormatting().isNakedWikiWord(toWord):
            raise WikiDataException, u"'%s' is an invalid wiki word" % toWord

        if self.isDefinedWikiWord(toWord):
            raise WikiDataException, u"Cannot rename '%s' to '%s', '%s' already exists" % (word, toWord, toWord)

        # commit anything pending so we can rollback on error
        self.commit()
        try:
            try:
                self.connWrap.execSql("update wikirelations set word = ? where word = ?", (toWord, word))
    #             self.connWrap.execSql("update wikirelations set relation = ? where relation = ?", (toWord, word))
                self.connWrap.execSql("update wikiwordprops set word = ? where word = ?", (toWord, word))
                self.connWrap.execSql("update todos set word = ? where word = ?", (toWord, word))
                self.renameContent(word, toWord)
                self.commit()
            except:
                self.connWrap.rollback()
                raise
        except (IOError, OSError, ValueError), e:
            traceback.print_exc()
            raise DbWriteAccessError(e)

#         # now we have to search the wiki files and replace the old word with the new
#         searchOp = SearchAndReplace.SearchReplaceOperation()
#         searchOp.wikiWide = True
#         searchOp.wildCard = 'no'
#         searchOp.caseSensitive = True
#         searchOp.searchStr = word
#         
#         results = self.search(searchOp)
#         for resultWord in results:
#             content = self.getContent(resultWord)
#             content = content.replace(word, toWord)
#             self.setContent(resultWord, content)


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
    
                    self.execSql("delete from wikirelations where word = ?", (word,))
                    self.execSql("delete from wikiwordprops where word = ?", (word,))
                    # self.execSql("delete from wikiwords where word = ?", (word,))
                    self.execSql("delete from todos where word = ?", (word,))
                    self.commitNeeded = True
                    self.deleteContent(word)
    #                 del self.cachedContentNames[word]
    #                 wikiFile = self.getWikiWordFileName(word)
    #                 if exists(wikiFile):
    #                     unlink(wikiFile)
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
            raise WikiDataException("You cannot delete the root wiki node")



    # ---------- Handling of relationships cache ----------

    def _getAllRelations(self):
        "get all of the relations in the db"
        relations = []
        try:
            data = self.execSqlQuery("select word, relation from wikirelations")
        except (IOError, OSError, ValueError), e:
            traceback.print_exc()
            raise DbReadAccessError(e)

        for row in data:
            relations.append((row[0], row[1]))
        return relations

    def getChildRelationships(self, wikiWord, existingonly=False,
            selfreference=True, withPosition=False):
        """
        get the child relations of this word
        existingonly -- List only existing wiki words
        selfreference -- List also wikiWord if it references itself
        withPositions -- Return tuples (relation, firstcharpos) with char.
            position of link in page (may be -1 to represent unknown).
            The Gadfly implementation always returns -1
        """
        sql = "select relation from wikirelations where word = ?"
        try:
            children = self.execSqlQuerySingleColumn(sql, (wikiWord,))
        except (IOError, OSError, ValueError), e:
            traceback.print_exc()
            raise DbReadAccessError(e)

        if not selfreference:
            try:
                children.remove(wikiWord)
            except ValueError:
                pass
        
        if existingonly:
            children = filter(lambda w:
                    self._getCachedContentNames().has_key(w), children)

        if withPosition:
            children = [(c, -1) for c in children]

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
        wikiWord = self.getAliasesWikiWord(wikiWord)
        try:
            parents = sets.Set(self.connWrap.execSqlQuerySingleColumn(
                    "select word from wikirelations where relation = ?", (wikiWord,)))
    
            # Plus parents of aliases
            aliases = [v for k, v in self.getPropertiesForWord(wikiWord)
                    if k == u"alias"]
    
            for al in aliases:
                parents.union_update(self.connWrap.execSqlQuerySingleColumn(
                    "select word from wikirelations where relation = ?", (al,)))
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
        wordSet = sets.Set(self.getAllDefinedWikiPageNames())

        # Remove all which have parents
        relations = self._getAllRelations()
        childWords = sets.Set([relation for word, relation in relations])
        
        # Remove directly mentioned words (not an alias of the word)
        wordSet -= childWords
        
#         for word, relation in relations:
#             wordSet.discard(relation)

        # Remove words where an alias of the word is a child
        for word in tuple(wordSet):  # "tuple" to create a sequence copy of wordSet
            for k, alias in self.getPropertiesForWord(word):
                if k != u"alias":
                    continue

                if alias in childWords:
                    wordSet.discard(word)
                    break   # break inner for loop


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
        childWords = sets.Set([relation for word, relation in relations])
        
        return [word for word in childWords
                if not self._getCachedContentNames().has_key(word)]


    def addRelationship(self, word, rel):
        """
        Add a relationship from word to rel. rel is a tuple (toWord, pos).
        The Gadfly implementation ignores pos.
        Returns True if relation added.
        A relation from one word to another is unique and can't be added twice.
        """
        try:
            data = self.execSqlQuery("select relation from wikirelations where "
                    "word = ? and relation = ?", (word, rel[0]))
        except (IOError, OSError, ValueError), e:
            traceback.print_exc()
            raise DbReadAccessError(e)

        returnValue = False
        if len(data) < 1:
            try:
                self.connWrap.execSqlInsert("wikirelations", ("word", "relation",
                        "created"), (word, rel[0], time()))

#                 self.execSql("insert into wikirelations(word, relation, created) "
#                         "values (?, ?, ?)", (word, rel[0], time()))
            except (IOError, OSError, ValueError), e:
                traceback.print_exc()
                raise DbWriteAccessError(e)

            returnValue = True
        return returnValue

    def updateChildRelations(self, word, childRelations):
        self.deleteChildRelationships(word)
        for r in childRelations:
            self.addRelationship(word, r)

    def deleteChildRelationships(self, fromWord):
        try:
            self.execSql("delete from wikirelations where word = ?", (fromWord,))
            self.commitNeeded = True
        except (IOError, OSError, ValueError), e:
            traceback.print_exc()
            raise DbWriteAccessError(e)


    def getAllSubWords(self, words, level=-1):
        """
        Return all words which are children, grandchildren, etc.
        of words and the words itself. Used by the "export/print Sub-Tree"
        functions. All returned words are real existing words, no aliases.
        """
        checkList = [(self.getAliasesWikiWord(w), 0) for w in words]
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
                    
            children = [(self.getAliasesWikiWord(c), chLevel + 1)
                    for c in children]
            children.reverse()
            checkList += children

        return result


    def _assembleWordGraph(self, word, graph):
        """
        recursively builds a graph of each of words parent relations

        Not part of public API!
        """
        if not graph.has_key(word):
            parents = self.getParentRelationships(word)
            graph[word] = parents;
            for parent in parents:
                self._assembleWordGraph(parent, graph)
        return graph

    def findBestPathFromWordToWord(self, word, toWord):
        "finds the shortest path from word to toWord"
        bestPath = findShortestPath(self._assembleWordGraph(word, {}), word,
                toWord, [])
        if bestPath: bestPath.reverse()
        return bestPath


    # ---------- Listing/Searching wiki words (see also "alias handling", "searching pages")----------

    def getAllDefinedWikiPageNames(self):
        "get the names of all wiki pages in the db, no aliases"
        wikiWords = self.getAllDefinedContentNames()
        # Filter out functional 'words'
        wikiWords = [w for w in wikiWords if not w.startswith('[')]
        return wikiWords

    def getAllDefinedContentNames(self):
        """
        Get the names of all the content elements in the db, no aliases.
        Content elements are wiki pages plus functional pages and possible
        other data, their names begin with '['
        """
        try:
            return self.execSqlQuerySingleColumn("select word from wikiwords")
        except (IOError, OSError, ValueError), e:
            traceback.print_exc()
            raise DbReadAccessError(e)

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
        diskPages = sets.ImmutableSet(self._getAllPageNamesFromDisk())
        definedPages = sets.ImmutableSet(self.getAllDefinedContentNames())
        
        try:
            # Delete no-more-existing words
            for word in (definedPages - diskPages):
                self.execSql("delete from wikiwords where word = ?", (word,))
                self.commitNeeded = True
            
            # Add new words:
            ti = time()
            for word in (diskPages - definedPages):
                st = stat(self.getWikiWordFileName(word))
                self.connWrap.execSqlInsert("wikiwords", ("word", "created", 
                        "modified", "presentationdatablock", "wordnormcase"),
                        (word, ti, st.st_mtime, "", ""))

#                 self.execSql("insert into wikiwords(word, created, modified, "
#                         "presentationdatablock, wordnormcase) "
#                         "values (?, ?, ?, '', '')", (word, ti, st.st_mtime))
        except (IOError, OSError, ValueError), e:
            traceback.print_exc()
            raise DbReadAccessError(e)


        self.cachedContentNames = None
#         # cache aliases
#         aliases = self.getAllAliases()
#         for alias in aliases:
#             self.cachedContentNames[alias] = 2
# 
#         # recreate word caches
#         for word in self.getAllDefinedContentNames():
#             self.cachedContentNames[word] = 1


    def _getCachedContentNames(self):
        try:
            if self.cachedContentNames is None:
                result = {}
        
                # cache aliases
                aliases = self.getAllAliases()
                for alias in aliases:
                    result[alias] = 2
        
                # Cache real words
                for word in self.getAllDefinedContentNames():
                    result[word] = 1
                    
                self.cachedContentNames = result

            return self.cachedContentNames
        except (IOError, OSError, ValueError), e:
            traceback.print_exc()
            raise DbReadAccessError(e)


    # TODO More general Wikiword to filename mapping
    def _getAllPageNamesFromDisk(self):   # Used for rebuilding wiki
        files = glob.glob(pathEnc(join(self.dataDir,
                u'*' + self.pagefileSuffix), "replace")[0])
        return [pathDec(basename(file), "replace")[0].replace(self.pagefileSuffix, '')
                for file in files]   # TODO: Unsafe. Suffix like e.g. '.wiki' may appear
                                    #  in the word. E.g. "The.great.wiki.for.all.wiki"


    # TODO More general Wikiword to filename mapping
    def getWikiWordFileName(self, wikiWord):
        """
        Not part of public API!
        """
        return join(self.dataDir, (u"%s" + self.pagefileSuffix) % wikiWord)

    # TODO More reliably esp. for aliases
    def isDefinedWikiWord(self, word):
        "check if a word is a valid wikiword (page name or alias)"
        return self._getCachedContentNames().has_key(word)

    def getWikiWordsStartingWith(self, thisStr, includeAliases=False, 
            caseNormed=False):
        "get the list of words starting with thisStr. used for autocompletion."
        words = self.getAllDefinedContentNames()
        if includeAliases:
            words.extend(self.getAllAliases())
        
        if caseNormed:
            thisStr = thisStr.lower()   # TODO More general normcase function
            startingWith = [word for word in words
                    if word.lower().startswith(thisStr)]
            return startingWith
        else:
            startingWith = [word for word in words if word.startswith(thisStr)]
            return startingWith


    def getWikiWordsWith(self, thisStr, includeAliases=False):
        "get the list of words with thisStr in them."
        thisStr = thisStr.lower()   # TODO More general normcase function


        result1 = [word for word in self.getAllDefinedWikiPageNames()
                if word.lower().startswith(thisStr)]

        if includeAliases:
            result1 += [word for word in self.getAllAliases()
                    if word.lower().startswith(thisStr)]


        result2 = [word for word in self.getAllDefinedWikiPageNames()
                if word.lower().find(thisStr) != -1 and
                not word.lower().startswith(thisStr)]

        if includeAliases:
            result2 += [word for word in self.getAllAliases()
                    if word.lower().find(thisStr) != -1 and
                    not word.lower().startswith(thisStr)]

#         result = [word for word in self.getAllDefinedWikiPageNames()
#                 if word.lower().find(thisStr) != -1]
# 
#         if includeAliases:
#             result += [word for word in self.getAllAliases()
#                     if word.lower().find(thisStr) != -1]

        coll = self.wikiDocument.getCollator()
        
        coll.sort(result1)
        coll.sort(result2)

        return result1 + result2


#     def getWikiWordsModifiedLastDays(self, days):
#         timeDiff = time()-(86400*days)
#         try:
#             rows = self.execSqlQuery("select word, modified from wikiwords")
#         except (IOError, OSError, ValueError), e:
#             traceback.print_exc()
#             raise DbReadAccessError(e)
#         return [row[0] for row in rows if float(row[1]) >= timeDiff and
#                 not row[0].startswith('[')]

    def getWikiWordsModifiedWithin(self, startTime, endTime):
        """
        Function must work for read-only wiki.
        startTime and endTime are floating values as returned by time.time()
        startTime is inclusive, endTime is exclusive
        """
        try:
            rows = self.execSqlQuery("select word, modified from wikiwords")            
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
            rows = self.execSqlQuery("select word, %s from wikiwords" % field)
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
            rows = self.execSqlQuery("select word, %s from wikiwords" % field)
        except (IOError, OSError, ValueError), e:
            traceback.print_exc()
            raise DbReadAccessError(e)

        rows = [row for row in rows if float(row[1]) < stamp and
                row[1] > 0 and not row[0].startswith('[')]

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
            rows = self.execSqlQuery("select word, %s from wikiwords" % field)
        except (IOError, OSError, ValueError), e:
            traceback.print_exc()
            raise DbReadAccessError(e)

        rows = [row for row in rows if float(row[1]) >= stamp and
                not row[0].startswith('[')]

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
            names = self.execSqlQuerySingleColumn(
                    "select distinct(key) from wikiwordprops")
        except (IOError, OSError, ValueError), e:
            traceback.print_exc()
            raise DbReadAccessError(e)

        return [name for name in names if not name.startswith('global.')]

    def getPropertyNamesStartingWith(self, startingWith):
        try:
            names = self.execSqlQuerySingleColumn(
                    "select distinct(key) from wikiwordprops")   #  order by key")
        except (IOError, OSError, ValueError), e:
            traceback.print_exc()
            raise DbReadAccessError(e)

        return [name for name in names if name.startswith(startingWith)]

    def getGlobalProperties(self):
        if not self.cachedGlobalProps:
            try:
                data = self.execSqlQuery(
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
            return self.execSqlQuerySingleColumn("select distinct(value) "
                    "from wikiwordprops where key = ?", (key,))  #  order by value
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


    def getWordsWithPropertyValue(self, key, value):
        words = []
        try:
            data = self.execSqlQuery("select word from wikiwordprops "
                    "where key = ? and value = ?", (key, value))
        except (IOError, OSError, ValueError), e:
            traceback.print_exc()
            raise DbReadAccessError(e)

        for row in data:
            words.append(row[0])
        return words


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


    def setProperty(self, word, key, value):
        # make sure the value doesn't already exist for this property
        try:
            data = self.execSqlQuery("select word from wikiwordprops where "+
                    "word = ? and key = ? and value = ?", (word, key, value))
        except (IOError, OSError, ValueError), e:
            traceback.print_exc()
            raise DbReadAccessError(e)
        # if it doesn't insert it
        returnValue = False
        if len(data) < 1:
            try:
                self.connWrap.execSqlInsert("wikiwordprops", ("word", "key",
                        "value"), (word, key, value))

#                 self.execSql("insert into wikiwordprops(word, key, value) "+
#                         "values (?, ?, ?)", (word, key, value))
            except (IOError, OSError, ValueError), e:
                traceback.print_exc()
                raise DbWriteAccessError(e)
            returnValue = True
        return returnValue

    def updateProperties(self, word, props):
        self.deleteProperties(word)
        for k in props.keys():
            values = props[k]
            for v in values:
                self.setProperty(word, k, v)
                if k == "alias":
                    self.setAsAlias(v)  # TODO
                    
        self.cachedGlobalProps = None   # reset global properties cache

    def deleteProperties(self, word):
        try:
            self.execSql("delete from wikiwordprops where word = ?", (word,))
            self.commitNeeded = True
        except (IOError, OSError, ValueError), e:
            traceback.print_exc()
            raise DbWriteAccessError(e)


    # ---------- Alias handling ----------

    def getAliasesWikiWord(self, alias):
        """
        If alias is an alias for another word, return that,
        otherwise return alias itself
        """
        if not self.isAlias(alias):
            return alias

        aliases = self.getWordsWithPropertyValue("alias", alias)
        if len(aliases) > 0:
            return aliases[0]
        return alias # None

    def isAlias(self, word):
        "check if a word is an alias for another"
        return self._getCachedContentNames().get(word) == 2

    def setAsAlias(self, word):
        """
        Sets this word in internal cache to be an alias
        """
        if self._getCachedContentNames().get(word, 2) == 2:
            self._getCachedContentNames()[word] = 2


    def getAllAliases(self):
        # get all of the aliases
        try:
            return self.execSqlQuerySingleColumn(
                    "select value from wikiwordprops where key = 'alias'")
        except (IOError, OSError, ValueError), e:
            traceback.print_exc()
            raise DbReadAccessError(e)


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
        for t in todos:
            self.addTodo(word, t)

    def addTodo(self, word, todo):
        try:
            self.connWrap.execSqlInsert("todos", ("word", "todo"), (word, todo))

#             self.execSql("insert into todos(word, todo) values (?, ?)", (word, todo))
        except (IOError, OSError, ValueError), e:
            traceback.print_exc()
            raise DbWriteAccessError(e)

    def deleteTodos(self, word):
        try:
            self.execSql("delete from todos where word = ?", (word,))
            self.commitNeeded = True
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
        result = sets.Set()
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


    def saveSearch(self, title, datablock):
        try:
            test = self.connWrap.execSqlQuerySingleItem(
                    "select title from search_views where title = ?",
                    (title,))
        except (IOError, OSError, ValueError), e:
            traceback.print_exc()
            raise DbReadAccessError(e)

        try:
            if test is not None:
                self.connWrap.execSql(
                        "update search_views set datablock = ? where "+\
                        "title = ?", (datablock, title))
            else:
                self.connWrap.execSqlInsert("search_views", ("title", "datablock"),
                        (title, datablock))

#                 self.connWrap.execSql(
#                         "insert into search_views(title, datablock) "+\
#                         "values (?, ?)", (title, datablock))
        except (IOError, OSError, ValueError), e:
            traceback.print_exc()
            raise DbWriteAccessError(e)


    def getSavedSearchTitles(self):
        """
        Return the titles of all stored searches in alphabetical order
        """
        try:
            return self.connWrap.execSqlQuerySingleColumn(
                    "select title from search_views order by title")
        except (IOError, OSError, ValueError), e:
            traceback.print_exc()
            raise DbReadAccessError(e)

    def getSearchDatablock(self, title):
        try:
            return self.connWrap.execSqlQuerySingleItem(
                    "select datablock from search_views where title = ?", (title,),
                    strConv=False)
        except (IOError, OSError, ValueError), e:
            traceback.print_exc()
            raise DbReadAccessError(e)

    def deleteSavedSearch(self, title):
        try:
            self.connWrap.execSql(
                    "delete from search_views where title = ?", (title,))
        except (IOError, OSError, ValueError), e:
            traceback.print_exc()
            raise DbWriteAccessError(e)



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
        DbStructure.recreateCacheTables(self.connWrap)
        self.commit()

        self.cachedContentNames = None
        self.cachedGlobalProps = None


    def setPresentationBlock(self, word, datablock):
        """
        Save the presentation datablock (a byte string) for a word to
        the database.
        """
        try:
            self.connWrap.execSql(
                    "update wikiwords set presentationdatablock = ? where "
                    "word = ?", (datablock, word))
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

    def execSql(self, sql, params=None):
        "utility method, executes the sql, no return"
        return self.connWrap.execSql(sql, params)

    def execSqlQuery(self, sql, params=None):
        "utility method, executes the sql, returns query result"
        return self.connWrap.execSqlQuery(sql, params)

    def execSqlQuerySingleColumn(self, sql, params=None):
        "utility method, executes the sql, returns query result"
        return self.connWrap.execSqlQuerySingleColumn(sql, params)

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
        pass


####################################################
# module level functions
####################################################


def findShortestPath(graph, start, end, path):   # path=[]
    "finds the shortest path in the graph from start to end"
    path = path + [start]
    if start == end:
        return path
    if not graph.has_key(start):
        return None
    shortest = None
    for node in graph[start]:
        if node not in path:
            newpath = findShortestPath(graph, node, end, path)
            if newpath:
                if not shortest or len(newpath) < len(shortest):
                    shortest = newpath

    return shortest



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
