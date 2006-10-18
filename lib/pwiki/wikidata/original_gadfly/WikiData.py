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



from os import mkdir, unlink, rename    # listdir
from os.path import exists, join, basename
from time import time, localtime
import datetime
import re, string, glob, sets

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

from pwiki.StringOps import mbcsEnc, mbcsDec, utf8Enc, utf8Dec, BOM_UTF8, \
        fileContentToUnicode, wikiWordToLabel

from pwiki import WikiFormatting
from pwiki import PageAst

# from pwiki.DocPages import WikiPage


class WikiData:
    "Interface to wiki data."
    def __init__(self, dataManager, dataDir):
        self.dataManager = dataManager
        self.dataDir = dataDir
        self.connWrap = None
        self.cachedContentNames = None

        conn = gadfly.gadfly("wikidb", self.dataDir)
        self.connWrap = DbStructure.ConnectWrap(conn)
        
        self.pagefileSuffix = self.dataManager.getWikiConfig().get("main",
                "db_pagefile_suffix", u".wiki")


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

        # Set marker for database type
        self.dataManager.getWikiConfig().set("main", "wiki_database_type",
                "original_gadfly")

        # create word caches
        self.cachedContentNames = {}

        # cache aliases
        aliases = self.getAllAliases()
        for alias in aliases:
            self.cachedContentNames[alias] = 2

        # Cache real words
        for word in self.getAllDefinedContentNames():
            self.cachedContentNames[word] = 1

        self.cachedGlobalProps = None
        self.getGlobalProperties()

    # ---------- Direct handling of page data ----------

    def getContent(self, word):
        if (not exists(self.getWikiWordFileName(word))):
            raise WikiFileNotFoundException, \
                    u"wiki page not found for word: %s" % word

        fp = open(self.getWikiWordFileName(word), "rU")
        content = fp.read()
        fp.close()

        return fileContentToUnicode(content)

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
            
        data = self.execSqlQuery("select word from wikiwords where word = ?",
                (word,))
        if len(data) < 1:
            if creadate is None:
                creadate = ti
                
            self.execSql("insert into wikiwords(word, created, modified, "
                    "presentationdatablock, wordnormcase) "
                    "values (?, ?, ?, '', '')", (word, creadate, moddate))
        else:
            self.execSql("update wikiwords set modified = ? where word = ?",
                    (moddate, word))
                    
        self.cachedContentNames[word] = 1


    def setContent(self, word, content, moddate = None, creadate = None):
        """
        Store unicode text for wikiword word, regardless if previous
        content exists or not. creadate will be used for new content
        only.
        
        moddate -- Modification date to store or None for current
        creadate -- Creation date to store or None for current        
        """
        
        output = open(self.getWikiWordFileName(word), 'w')
        output.write(BOM_UTF8)
        output.write(utf8Enc(content)[0])
        output.close()
        
        self._updatePageEntry(word, moddate, creadate)


    def renameContent(self, oldWord, newWord):
        """
        The content which was stored under oldWord is stored
        after the call under newWord. The self.cachedContentNames
        dictionary is updated, other caches won't be updated.
        """
        self.execSql("update wikiwords set word = ? where word = ?",
                (newWord, oldWord))

        rename(self.getWikiWordFileName(oldWord),
                self.getWikiWordFileName(newWord))
        del self.cachedContentNames[oldWord]
        self.cachedContentNames[newWord] = 1


    def deleteContent(self, word):
        self.execSql("delete from wikiwords where word = ?", (word,))
        if exists(self.getWikiWordFileName(word)):
            unlink(self.getWikiWordFileName(word))
        del self.cachedContentNames[word]

    def getTimestamps(self, word):
        """
        Returns a tuple with modification and creation date of
        a word or (None, None) if word is not in the database
        """
        dates = self.connWrap.execSqlQuery(
                "select modified, created from wikiwords where word = ?",
                (word,))

        if len(dates) > 0:
            return (float(dates[0][0]), float(dates[0][1]))
        else:
            return (None, None)  # ?


    # ---------- Renaming/deleting pages with cache update ----------

    def renameWord(self, word, toWord):
        if not self.dataManager.getFormatting().isNakedWikiWord(toWord):
            raise WikiDataException, u"'%s' is an invalid wiki word" % toWord

        if self.isDefinedWikiWord(toWord):
            raise WikiDataException, u"Cannot rename '%s' to '%s', '%s' already exists" % (word, toWord, toWord)

        # commit anything pending so we can rollback on error
        self.connWrap.commit()

        try:
            self.connWrap.execSql("update wikirelations set word = ? where word = ?", (toWord, word))
#             self.connWrap.execSql("update wikirelations set relation = ? where relation = ?", (toWord, word))
            self.connWrap.execSql("update wikiwordprops set word = ? where word = ?", (toWord, word))
            self.connWrap.execSql("update todos set word = ? where word = ?", (toWord, word))
            self.renameContent(word, toWord)
            self.connWrap.commit()
        except:
            self.connWrap.rollback()
            raise

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
        if word != self.dataManager.getWikiName():
            try:
                self.commit()
                # don't delete the relations to the word since other
                # pages still have valid outward links to this page.
                # just delete the content

                self.execSql("delete from wikirelations where word = ?", (word,))
                self.execSql("delete from wikiwordprops where word = ?", (word,))
                # self.execSql("delete from wikiwords where word = ?", (word,))
                self.execSql("delete from todos where word = ?", (word,))
                self.deleteContent(word)
#                 del self.cachedContentNames[word]
#                 wikiFile = self.getWikiWordFileName(word)
#                 if exists(wikiFile):
#                     unlink(wikiFile)
                self.commit()

                # due to some bug we have to close and reopen the db sometimes
                self.connWrap.close()
                conn = gadfly.gadfly("wikidb", self.dataDir)
                self.connWrap = DbStructure.ConnectWrap(conn)

            except:
                self.connWrap.rollback()
                raise
        else:
            raise WikiDataException, "You cannot delete the root wiki node"



    # ---------- Handling of relationships cache ----------

    def _getAllRelations(self):
        "get all of the relations in the db"
        relations = []
        data = self.execSqlQuery("select word, relation from wikirelations")
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
        children = self.execSqlQuerySingleColumn(sql, (wikiWord,))
        if not selfreference:
            try:
                children.remove(wikiWord)
            except ValueError:
                pass
        
        if existingonly:
            children = filter(lambda w: self.cachedContentNames.has_key(w), children)

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
        parents = sets.Set(self.connWrap.execSqlQuerySingleColumn(
                "select word from wikirelations where relation = ?", (wikiWord,)))

        # Plus parents of aliases
        aliases = [v for k, v in self.getPropertiesForWord(wikiWord)
                if k == u"alias"]

        for al in aliases:
            parents.union_update(self.connWrap.execSqlQuerySingleColumn(
                "select word from wikirelations where relation = ?", (al,)))

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
                if not self.cachedContentNames.has_key(word)]


    def addRelationship(self, word, toWord):
        """
        Add a relationship from word toWord. Returns True if relation added.
        A relation from one word to another is unique and can't be added twice.
        """
        data = self.execSqlQuery("select relation from wikirelations where "+
                "word = ? and relation = ?", (word, toWord))
        returnValue = False
        if len(data) < 1:
            self.execSql("insert into wikirelations(word, relation, created) "+
                    "values (?, ?, ?)", (word, toWord, time()))
            returnValue = True
        return returnValue

    def updateChildRelations(self, word, childRelations):
        self.deleteChildRelationships(word)
        for r in childRelations:
            self.addRelationship(word, r)

    def deleteChildRelationships(self, fromWord):
        self.execSql("delete from wikirelations where word = ?", (fromWord,))

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
        return self.execSqlQuerySingleColumn("select word from wikiwords")

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
        
        The self.cachedContentNames is also updated.
        """
        diskPages = sets.ImmutableSet(self._getAllPageNamesFromDisk())
        definedPages = sets.ImmutableSet(self.getAllDefinedContentNames())
        
        # Delete no-more-existing words
        for word in (definedPages - diskPages):
            self.execSql("delete from wikiwords where word = ?", (word,))
        
        # Add new words:
        ti = time()
        for word in (diskPages - definedPages):
            self.execSql("insert into wikiwords(word, created, modified, "
                    "presentationdatablock, wordnormcase) "
                    "values (?, ?, ?, '', '')", (word, ti, ti))

        self.cachedContentNames = {}

        # cache aliases
        aliases = self.getAllAliases()
        for alias in aliases:
            self.cachedContentNames[alias] = 2

        # recreate word caches
        for word in self.getAllDefinedContentNames():
            self.cachedContentNames[word] = 1


    # TODO More general Wikiword to filename mapping
    def _getAllPageNamesFromDisk(self):   # Used for rebuilding wiki
        files = glob.glob(mbcsEnc(join(self.dataDir,
                u'*' + self.pagefileSuffix), "replace")[0])
        return [mbcsDec(basename(file), "replace")[0].replace(self.pagefileSuffix, '')
                for file in files]   # TODO: Unsafe. Suffix like e.g. '.wiki' may appear
                                    #  in the word. E.g. "The.great.wiki.for.all.wiki"


    # TODO More general Wikiword to filename mapping
    def getWikiWordFileName(self, wikiWord):
        """
        Not part of public API!
        """

        # return mbcsEnc(join(self.dataDir, "%s.wiki" % wikiWord))[0]
        return join(self.dataDir, (u"%s" + self.pagefileSuffix) % wikiWord)

    # TODO More reliably esp. for aliases
    def isDefinedWikiWord(self, word):
        "check if a word is a valid wikiword (page name or alias)"
        return self.cachedContentNames.has_key(word)

    def getWikiWordsStartingWith(self, thisStr, includeAliases=False):
        "get the list of words starting with thisStr. used for autocompletion."
        words = self.getAllDefinedContentNames()
        if includeAliases:
            words.extend(self.getAllAliases())
        startingWith = [word for word in words if word.startswith(thisStr)]
        return startingWith

    def getWikiWordsWith(self, thisStr, includeAliases=False):
        "get the list of words with thisStr in them."
        thisStr = thisStr.lower()

        result = [word for word in self.getAllDefinedWikiPageNames()
                if word.lower().find(thisStr) != -1]

        if includeAliases:
            result += [word for word in self.getAllAliases()
                    if word.lower().find(thisStr) != -1]

        return result


    def getWikiWordsModifiedWithin(self, days):
        timeDiff = time()-(86400*days)
        rows = self.execSqlQuery("select word, modified from wikiwords")
        return [row[0] for row in rows if float(row[1]) >= timeDiff]


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
        names = self.execSqlQuerySingleColumn(
                "select distinct(key) from wikiwordprops")
        return [name for name in names if not name.startswith('global.')]

    def getPropertyNamesStartingWith(self, startingWith):
        names = self.execSqlQuerySingleColumn(
                "select distinct(key) from wikiwordprops")   #  order by key")
        return [name for name in names if name.startswith(startingWith)]

    def getGlobalProperties(self):
        if not self.cachedGlobalProps:
            data = self.execSqlQuery(
                    "select key, value from wikiwordprops")  # order by key
            globalMap = {}
            for (key, val) in data:
                if key.startswith('global.'):
                    globalMap[key] = val
            self.cachedGlobalProps = globalMap

        return self.cachedGlobalProps

    def getDistinctPropertyValues(self, key):
        return self.execSqlQuerySingleColumn("select distinct(value) "
                "from wikiwordprops where key = ?", (key,))  #  order by value

    def getWordsForPropertyName(self, key):
        return self.connWrap.execSqlQuerySingleColumn(
                "select distinct(word) from wikiwordprops where key = ? ",
                (key,))

    def getWordsWithPropertyValue(self, key, value):
        words = []
        data = self.execSqlQuery("select word from wikiwordprops "
                "where key = ? and value = ?", (key, value))
        for row in data:
            words.append(row[0])
        return words

    def getPropertiesForWord(self, word):
        """
        Returns list of tuples (key, value) of key and value
        of all properties for word.
        """
        return self.connWrap.execSqlQuery("select key, value "+
                    "from wikiwordprops where word = ?", (word,))

    def setProperty(self, word, key, value):
        # make sure the value doesn't already exist for this property
        data = self.execSqlQuery("select word from wikiwordprops where "+
                "word = ? and key = ? and value = ?", (word, key, value))
        # if it doesn't insert it
        returnValue = False
        if len(data) < 1:
            self.execSql("insert into wikiwordprops(word, key, value) "+
                    "values (?, ?, ?)", (word, key, value))
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
        self.execSql("delete from wikiwordprops where word = ?", (word,))


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
        return self.cachedContentNames.get(word) == 2

    def setAsAlias(self, word):
        """
        Sets this word in internal cache to be an alias
        """
        if self.cachedContentNames.get(word, 2) == 2:
            self.cachedContentNames[word] = 2


    def getAllAliases(self):
        # get all of the aliases
        return self.execSqlQuerySingleColumn(
                "select value from wikiwordprops where key = 'alias'")


    # ---------- Todo cache handling ----------

    def getTodos(self):
        return self.connWrap.execSqlQuery("select word, todo from todos")
#         todos = []
#         data = self.connWrap.execSqlQuery("select word, todo from todos")
#         for row in data:
#             todos.append((row[0], row[1]))
#         return todos

    def getTodosForWord(self, word):
        """
        Returns list of all todo items of word
        """
        return self.connWrap.execSqlQuerySingleColumn("select todo from todos "
                "where word = ?", (word,))

    def updateTodos(self, word, todos):
        self.deleteTodos(word)
        for t in todos:
            self.addTodo(word, t)

    def addTodo(self, word, todo):
        self.execSql("insert into todos(word, todo) values (?, ?)", (word, todo))

    def deleteTodos(self, word):
        self.execSql("delete from todos where word = ?", (word,))


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
        test = self.connWrap.execSqlQuerySingleItem(
                "select title from search_views where title = ?",
                (title,))
                
        if test is not None:
            self.connWrap.execSql(
                    "update search_views set datablock = ? where "+\
                    "title = ?", (datablock, title))
        else:
            self.connWrap.execSql(
                    "insert into search_views(title, datablock) "+\
                    "values (?, ?)", (title, datablock))

    def getSavedSearchTitles(self):
        """
        Return the titles of all stored searches in alphabetical order
        """
        return self.connWrap.execSqlQuerySingleColumn(
                "select title from search_views order by title")

    def getSearchDatablock(self, title):
        return self.connWrap.execSqlQuerySingleItem(
                "select datablock from search_views where title = ?", (title,),
                strConv=False)

    def deleteSavedSearch(self, title):
        self.connWrap.execSql(
                "delete from search_views where title = ?", (title,))



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
        self.connWrap.commit()

        self.cachedContentNames = {}
        self.cachedGlobalProps = None


    def setPresentationBlock(self, word, datablock):
        """
        Save the presentation datablock (a byte string) for a word to
        the database.
        """
        self.connWrap.execSql(
                "update wikiwords set presentationdatablock = ? where "
                "word = ?", (datablock, word))

    def getPresentationBlock(self, word):
        """
        Returns the presentation datablock (a byte string).
        The function may return either an empty string or a valid datablock
        """
        return self.connWrap.execSqlQuerySingleItem(
                "select presentationdatablock from wikiwords where word = ?",
                (word,), strConv=False)


    def close(self):
        self.commit()
        self.connWrap.close()

    # Not part of public API:

    def execSql(self, sql, params=None):
        "utility method, executes the sql, no return"
        return self.connWrap.execSql(sql, params)
#         cursor = self.dbConn.cursor()
#         if params:
#             params = tuple(map(_uniToUtf8, params))
#             cursor.execute(sql, params)
#         else:
#             cursor.execute(sql)
#         cursor.close()

    def execSqlQuery(self, sql, params=None):
        "utility method, executes the sql, returns query result"
        return self.connWrap.execSqlQuery(sql, params)
#         cursor = self.dbConn.cursor()
#         if params:
#             params = tuple(map(_uniToUtf8, params))
#             cursor.execute(sql, params)
#         else:
#             cursor.execute(sql)
#         data = cursor.fetchall()
#         cursor.close()
#         data = map(lambda row: map(_utf8ToUni, row), data)
#         return data

    def execSqlQuerySingleColumn(self, sql, params=None):
        "utility method, executes the sql, returns query result"
        return self.connWrap.execSqlQuerySingleColumn(sql, params)
#         data = self.execSqlQuery(sql, params)
#         return [row[0] for row in data]

    def commit(self):
        self.connWrap.commit()

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
