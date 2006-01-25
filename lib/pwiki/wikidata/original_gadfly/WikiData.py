"""

Used terms:
    
    wikiword -- a string matching one of the wiki word regexes
    page -- real existing content stored and associated with a wikiword
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
import re, string, glob

try:
    import gadfly
except:
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

from pwiki.WikiPage import WikiPage


CleanTextRE = re.compile("[^A-Za-z0-9]")  # ?

class WikiData:
    "Interface to wiki data."
    def __init__(self, pWiki, dataDir):
        self.pWiki = pWiki
        self.dataDir = dataDir
        self.connWrap = None
        self.cachedWikiWords = None
        
#         self._updateTokenizer = \
#                 Tokenizer(WikiFormatting.CombinedUpdateRE, -1)

        self._reinit()
        

    def _reinit(self):
        """
        Actual initialization or reinitialization after rebuildWiki()
        """
        conn = gadfly.gadfly("wikidb", self.dataDir)
        self.connWrap = DbStructure.ConnectWrap(conn)
        
        formatcheck, formatmsg = DbStructure.checkDatabaseFormat(self.connWrap)

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
        self.pWiki.configuration.set("main", "wiki_database_type",
                "original_gadfly")

        # create word caches
        self.cachedWikiWords = {}
        for word in self.getAllDefinedPageNames():
            self.cachedWikiWords[word] = 1

        # cache aliases
        aliases = self.getAllAliases()
        for alias in aliases:
            self.cachedWikiWords[alias] = 2

        self.cachedGlobalProps = None
        self.getGlobalProperties()

#         # maintenance
#         #self.execSql("delete from wikiwords where word = ''")
#         #self.execSql("delete from wikirelations where word = 'MyContacts'")
# 
#         # database versioning...
#         indices = self.execSqlQuerySingleColumn("select INDEX_NAME from __indices__")
#         tables = self.execSqlQuerySingleColumn("select TABLE_NAME from __table_names__")
# 
#         if "WIKIWORDPROPS_PKEY" in indices:
#             print "dropping index wikiwordprops_pkey"
#             self.execSql("drop index wikiwordprops_pkey")
#         if "WIKIWORDPROPS_WORD" not in indices:
#             print "creating index wikiwordprops_word"
#             self.execSql("create index wikiwordprops_word on wikiwordprops(word)")
#         if "WIKIRELATIONS_WORD" not in indices:
#             print "creating index wikirelations_word"
#             self.execSql("create index wikirelations_word on wikirelations(word)")
#         if "REGISTRATION" in tables:
#             self.execSql("drop table registration")

    # ---------- Direct handling of page data ----------

    def getContent(self, word):
        if (not exists(self.getWikiWordFileName(word))):
            raise WikiFileNotFoundException, u"wiki page not found for word: %s" % word

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
                
            self.execSql("insert into wikiwords(word, created, modified) "+
                    "values (?, ?, ?)", (word, creadate, moddate))
        else:
            self.execSql("update wikiwords set modified = ? where word = ?",
                    (moddate, word))
                    
        self.cachedWikiWords[word] = 1


    def setContent(self, word, text, moddate = None, creadate = None):
        """
        Store unicode text for wikiword word, regardless if previous
        content exists or not. creadate will be used for new content
        only.
        
        moddate -- Modification date to store or None for current
        creadate -- Creation date to store or None for current        
        """
        
        output = open(self.getWikiWordFileName(word), 'w')
        output.write(BOM_UTF8)
        output.write(utf8Enc(text)[0])
        output.close()
        
        self._updatePageEntry(word, moddate, creadate)


#     def getContentAndInfo(self, word):
#         """
#         Get content and further information about a word
#         """
#         content = self.getContent(word)


    def renameContent(self, oldWord, newWord):
        """
        The content which was stored under oldWord is stored
        after the call under newWord. The self.cachedWikiWords
        dictionary is updated, other caches won't be updated.
        """
        self.execSql("update wikiwords set word = ? where word = ?",
                (newWord, oldWord))

        rename(self.getWikiWordFileName(oldWord),
                self.getWikiWordFileName(newWord))
        del self.cachedWikiWords[oldWord]
        self.cachedWikiWords[newWord] = 1


    def deleteContent(self, word):
        self.execSql("delete from wikiwords where word = ?", (word,))
        if exists(self.getWikiWordFileName(word)):
            unlink(self.getWikiWordFileName(word))
        del self.cachedWikiWords[word]

    def getTimestamps(self, word):
        """
        Returns a tuple with modification and creation date of
        a word or (None, None) if word is not in the database
        """
        dates = self.connWrap.execSqlQuery(
                "select modified, created from wikiwordcontent where word = ?",
                (word,))

        if len(dates) > 0:
            return dates[0]
        else:
            return (None, None)  # ?


    # ---------- Renaming/deleting pages with cache update ----------

    def renameWord(self, word, toWord):
        if self.pWiki.getFormatting().isNakedWikiWord(toWord):
            try:
                self.getPage(toWord)
                raise WikiDataException, u"Cannot rename '%s' to '%s', '%s' already exists" % (word, toWord, toWord)
            except WikiWordNotFoundException:
                pass

            # commit anything pending so we can rollback on error
            self.commit()

            try:
                # self.execSql("update wikiwords set word = ? where word = ?", (toWord, word))
                self.execSql("update wikirelations set word = ? where word = ?", (toWord, word))
                self.execSql("update wikirelations set relation = ? where relation = ?", (toWord, word))
                self.execSql("update wikiwordprops set word = ? where word = ?", (toWord, word))
                self.execSql("update todos set word = ? where word = ?", (toWord, word))
                self.renameContent(word, toWord)
                # rename(join(self.dataDir, "%s.wiki" % word), join(self.dataDir, "%s.wiki" % toWord))  # !!!
                self.commit()
#                 del self.cachedWikiWords[word]
#                 self.cachedWikiWords[toWord] = 1
            except:
                self.connWrap.rollback()
                raise

            # now i have to search the wiki files and replace the old word with the new
            searchOp = SearchAndReplace.SearchReplaceOperation()
            searchOp.wikiWide = True
            searchOp.wildCard = 'no'
            searchOp.caseSensitive = True
            searchOp.searchStr = word
            
            results = self.search(searchOp)
            for resultWord in results:
                content = self.getContent(resultWord)
                content = content.replace(word, toWord)
                self.setContent(resultWord, content)
                
#                 file = join(self.dataDir, "%s.wiki" % resultWord)
# 
#                 fp = open(file)
#                 lines = fp.readlines()
#                 fp.close()
# 
#                 bakFileName = "%s.bak" % file
#                 fp = open(bakFileName, 'w')
#                 for line in lines:
#                     fp.write(line.replace(word, toWord))
#                 fp.close()
# 
#                 unlink(file)
#                 rename(bakFileName, file)

        else:
            raise WikiDataException, u"'%s' is an invalid wiki word" % toWord

    def deleteWord(self, word):
        """
        delete everything about the wikiword passed in. an exception is raised
        if you try and delete the wiki root node.
        """
        if word != self.pWiki.wikiName:
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
#                 del self.cachedWikiWords[word]
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


    # ---------- WikiPage creation ----------

    def getPage(self, wikiWord):
        """
        Fetch a WikiPage for the wikiWord, throws WikiWordNotFoundException
        if word doesn't exist
        """
        if not self.isDefinedWikiWord(wikiWord):
            raise WikiWordNotFoundException, u"Word '%s' not in wiki" % wikiWord

        return WikiPage(self, wikiWord)

    def getPageNoError(self, wikiWord):
        """
        fetch a WikiPage for the wikiWord. If it doesn't exist, return
        one without throwing an error and without updating the cache
        """
        return WikiPage(self, wikiWord)

    def createPage(self, wikiWord):
        """
        create a new wikiPage for the wikiWord. Cache is not updated until
        page is saved
        """
#         ti = time()
#         self.execSql(
#                 "insert into wikiwords(word, created, modified) values (?, ?, ?)",
#                 (wikiWord, ti, ti))
#         self.cachedWikiWords[wikiWord] = 1
        return self.getPageNoError(wikiWord)


    # ---------- Handling of relationships cache ----------

    def getAllRelations(self):
        "get all of the relations in the db"
        relations = []
        data = self.execSqlQuery("select word, relation from wikirelations")
        for row in data:
            relations.append((row[0], row[1]))
        return relations

    def getChildRelationships(self, wikiWord, existingonly=False,
            selfreference=True):
        """
        get the child relations to this word
        existingonly -- List only existing wiki words
        selfreference -- List also wikiWord if it references itself
        """
        sql = "select relation from wikirelations where word = ?"
        children = self.execSqlQuerySingleColumn(sql, (wikiWord,))
        if not selfreference:
            try:
                children.remove(wikiWord)
            except ValueError:
                pass
        
        if existingonly:
            return filter(lambda w: self.cachedWikiWords.has_key(w), children)
        else:
            return children

    # TODO More efficient
    def _hasChildren(self, wikiWord, existingonly=False,
            selfreference=True):
        return len(self.getChildRelationships(wikiWord, existingonly,
                selfreference)) > 0
                
    # TODO More efficient                
    def getChildRelationshipsAndHasChildren(self, wikiWord, existingonly=False,
            selfreference=True):
        """
        get the child relations to this word as sequence of tuples
            (<child word>, <has child children?>). Used when expanding
            a node in the tree control.
        existingonly -- List only existing wiki words
        selfreference -- List also wikiWord if it references itself
        """
        children = self.getChildRelationships(wikiWord, existingonly,
                selfreference)
                
        return map(lambda c: (c, self._hasChildren(c, existingonly,
                selfreference)), children)

    def getParentRelationships(self, toWord):
        "get the parent relations to this word"
        return self.execSqlQuerySingleColumn(
                "select word from wikirelations where relation = ?", (toWord,))

    def getParentLessWords(self):
        """
        get the words that have no parents. also returns nodes that have files but
        no entries in the wikiwords table.
        """
        words = self.getAllDefinedPageNames()
        relations = self.getAllRelations()
        rightSide = [relation for (word, relation) in relations]

        # get the list of wiki files
#         wikiFiles = [file.replace(".wiki", "") for file in listdir(self.dataDir)
#                      if file.endswith(".wiki")]
        wikiFiles = self.getAllPageNamesFromDisk()

        # append the words that don't exist in the words db
        words.extend([file for file in wikiFiles if file not in words])

        # find those that have no parent relations
        return [word for word in words if word not in rightSide]

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

    def getAllDefinedPageNames(self):
        "get the names of all the pages in the db, no aliases"
        return self.execSqlQuerySingleColumn("select word from wikiwords")

    # TODO More general Wikiword to filename mapping
    def getAllPageNamesFromDisk(self):   # Used for rebuilding wiki
        files = glob.glob(join(mbcsEnc(self.dataDir)[0], '*.wiki'))
        return [mbcsDec(basename(file).replace('.wiki', ''), "replace")[0]
                for file in files]

    # TODO More general Wikiword to filename mapping
    def getWikiWordFileName(self, wikiWord):
        """
        Not part of public API!
        """

        # return mbcsEnc(join(self.dataDir, "%s.wiki" % wikiWord))[0]
        return join(self.dataDir, u"%s.wiki" % wikiWord)

    def isDefinedWikiWord(self, word):
        "check if a word is a valid wikiword (page name or alias)"
        return self.cachedWikiWords.has_key(word)

    def getWikiWordsStartingWith(self, thisStr, includeAliases=False):
        "get the list of words starting with thisStr. used for autocompletion."
        words = self.getAllDefinedPageNames()
        if includeAliases:
            words.extend(self.getAllAliases())
        startingWith = [word for word in words if word.startswith(thisStr)]
        return startingWith

    def getWikiWordsWith(self, thisStr):
        "get the list of words with thisStr in them."
        return [word for word in self.getAllDefinedPageNames()
                if word.lower().find(thisStr) != -1]

    def getWikiWordsModifiedWithin(self, days):
        timeDiff = time()-(86400*days)
        rows = self.execSqlQuery("select word, modified from wikiwords")
        return [row[0] for row in rows if float(row[1]) >= timeDiff]


    # ---------- Property cache handling ----------

    def getPropertyNames(self):
        names = self.execSqlQuerySingleColumn("select distinct(key) from wikiwordprops order by key")
        return [name for name in names if not name.startswith('global.')]

    def getPropertyNamesStartingWith(self, startingWith):
        names = self.execSqlQuerySingleColumn("select distinct(key) from wikiwordprops order by key")
        return [name for name in names if name.startswith(startingWith)]

    def getGlobalProperties(self):
        if not self.cachedGlobalProps:
            data = self.execSqlQuery("select key, value from wikiwordprops order by key")
            globalMap = {}
            for (key, val) in data:
                if key.startswith('global.'):
                    globalMap[key] = val
            self.cachedGlobalProps = globalMap

        return self.cachedGlobalProps

    def getDistinctPropertyValues(self, key):
        return self.execSqlQuerySingleColumn("select distinct(value) "+
                "from wikiwordprops where key = ? order by value", (key,))

    def getWordsWithPropertyValue(self, key, value):
        words = []
        data = self.execSqlQuery("select word from wikiwordprops "+
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
                    self.cachedWikiWords[v] = 2

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
        if self.cachedWikiWords.has_key(word):
            return self.cachedWikiWords.get(word) == 2
        return False

    def getAllAliases(self):
        # get all of the aliases
        return self.execSqlQuerySingleColumn("select value from wikiwordprops where key = 'alias'")


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

    def search(self, sarOp, applOrdering=True):
        results = []
        sarOp.beginWikiSearch(self)
        try:
            for word in self.getAllDefinedPageNames():  #glob.glob(join(self.dataDir, '*.wiki')):
                # print "search1", repr(word), repr(self.getWikiWordFileName(word))
                fileContents = self.getContent(word)
                
                if sarOp.testPage(word, fileContents) == True:
                    results.append(word)
            if applOrdering:
                results = sarOp.applyOrdering(results)

        finally:
            sarOp.endWikiSearch()

        return results

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
        Needed before updating the whole wiki
        """
        DbStructure.recreateCacheTables(self.connWrap)
        self.connWrap.commit()

        self.cachedWikiWords = {}
        self.cachedGlobalProps = None

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

    def rebuildWiki(self, progresshandler):
        """
        Rebuild cached structures, try to repair database inconsistencies.

        Must be implemented if checkCapability returns a version number
        for "rebuild".
        
        progresshandler -- Object, fulfilling the GuiProgressHandler
            protocol
        """
        # get all of the wikiWords
        wikiWords = self.getAllPageNamesFromDisk()   # Replace this call
                
        progresshandler.open(len(wikiWords) + 1)
        try:
            step = 1
    
            # re-save all of the pages
            self.clearCacheTables()
            for wikiWord in wikiWords:
                progresshandler.update(step, u"Rebuilding %s" % wikiWord)
                self._updatePageEntry(wikiWord)
                wikiPage = self.createPage(wikiWord)
                wikiPage.update(wikiPage.getContent(), False)  # TODO AGA processing
                step = step + 1
    
        finally:            
            progresshandler.close()


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



def listAvailableWikiDataHandlers(pWiki):
    """
    Returns a list with the names of available handlers from this module.
    Each item is a tuple (<internal name>, <descriptive name>)
    """
    if gadfly is not None:
        return [("original_gadfly", "Original Gadfly")]
    else:
        return []


def getWikiDataHandler(pWiki, name):
    """
    Returns a creation function (or class) for an appropriate
    WikiData object and a createWikiDB function or (None, None)
    if name is unknown
    """
    if name == "original_gadfly":
        return WikiData, createWikiDB
    
    return (None, None)
