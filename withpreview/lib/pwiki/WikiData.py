from os import mkdir, unlink, listdir, rename
from os.path import exists, join, basename
from time import time, localtime
import datetime
import re, string, glob

import gadfly
import WikiFormatting

CleanTextRE = re.compile("[^A-Za-z0-9]")

class WikiData:
    "Interface to wiki data."
    def __init__(self, pWiki, dataDir):
        self.pWiki = pWiki
        self.dataDir = dataDir            
        self.dbConn = gadfly.gadfly("wikidb", dataDir)

        # create word caches
        self.cachedWikiWords = {}
        for word in self.getAllWords():
            self.cachedWikiWords[word] = 1

        # cache aliases
        aliases = self.getAllAliases()
        for alias in aliases:
            self.cachedWikiWords[alias] = 2
            
        self.cachedGlobalProps = None
        self.getGlobalProperties()

        # maintenance
        #self.execSql("delete from wikiwords where word = ''")
        #self.execSql("delete from wikirelations where word = 'MyContacts'")

        # database versioning... 
        indices = self.execSqlQuerySingleColumn("select INDEX_NAME from __indices__")
        tables = self.execSqlQuerySingleColumn("select TABLE_NAME from __table_names__")

        if "WIKIWORDPROPS_PKEY" in indices:
            print "dropping index wikiwordprops_pkey"
            self.execSql("drop index wikiwordprops_pkey")
        if "WIKIWORDPROPS_WORD" not in indices:
            print "creating index wikiwordprops_word"
            self.execSql("create index wikiwordprops_word on wikiwordprops(word)")
        if "WIKIRELATIONS_WORD" not in indices:
            print "creating index wikirelations_word"
            self.execSql("create index wikirelations_word on wikirelations(word)")
        if "REGISTRATION" in tables:
            self.execSql("drop table registration")

    def getPage(self, wikiWord, toload=None):
        "fetch a WikiPage for the wikiWord"
        return WikiPage(self, wikiWord, toload)

    def createPage(self, wikiWord):
        "create a new wikiPage for the wikiWord"
        self.execSql("insert into wikiwords(word, created, modified) values ('%s', '%s', '%s')" % (wikiWord, time(),time()))
        self.cachedWikiWords[wikiWord] = 1
        return self.getPage(wikiWord)
        
    def getChildRelationships(self, toWord):
        "get the child relations to this word"
        return self.execSqlQuerySingleColumn("select relation from wikirelations where word = '%s'" % toWord)

    def getParentRelationships(self, toWord):
        "get the parent relations to this word"
        return self.execSqlQuerySingleColumn("select word from wikirelations where relation = '%s'" % toWord)

    def addRelationship(self, word, toWord):
        """
        Add a relationship from word toWord. Returns True if relation added.
        A relation from one word to another is unique and can't be added twice.
        """
        cursor = self.dbConn.cursor()
        cursor.execute("select relation from wikirelations where word = '%s' and relation = '%s'" % (word, toWord))
        data = cursor.fetchall()
        returnValue = False
        if len(data) < 1:
            cursor.execute("insert into wikirelations(word, relation, created) values ('%s', '%s', '%s')" % (word, toWord, time()))
            returnValue = True
        cursor.close()
        return returnValue

    def getAllWords(self):
        "get all of the words in the db"
        return self.execSqlQuerySingleColumn("select word from wikiwords")

    def getAllAliases(self):
        # get all of the aliases
        return self.execSqlQuerySingleColumn("select value from wikiwordprops where key = 'alias'")

    def getAllRelations(self):
        "get all of the relations in the db"
        relations = []
        data = self.execSqlQuery("select word, relation from wikirelations")
        for row in data:
            relations.append((row[0], row[1]))
        return relations

    def isWikiWord(self, word):
        "check if a word is a valid wikiword"
        if self.cachedWikiWords.has_key(word):
            return True
        return False
    
    def getWikiWordsStartingWith(self, thisStr, includeAliases=False):
        "get the list of words starting with thisStr. used for autocompletion."
        words = self.getAllWords()
        if includeAliases:
            words.extend(self.getAllAliases())
        startingWith = [word for word in words if word.startswith(thisStr)]
        return startingWith

    def getWikiWordsWith(self, thisStr):
        "get the list of words with thisStr in them."
        return [word for word in self.getAllWords() if word.lower().find(thisStr) != -1]

    def getWikiWordsModifiedWithin(self, days):
        timeDiff = time()-(86400*days)
        rows = self.execSqlQuery("select word, modified from wikiwords")
        return [row[0] for row in rows if float(row[1]) >= timeDiff]

    def getParentLessWords(self):
        """
        get the words that have no parents. also returns nodes that have files but
        no entries in the wikiwords table.
        """
        words = self.getAllWords()
        relations = self.getAllRelations()
        rightSide = [relation for (word, relation) in relations]

        # get the list of wiki files
        wikiFiles = [file.replace(".wiki", "") for file in listdir(self.dataDir)
                     if file.endswith(".wiki")]

        # append the words that don't exist in the words db
        words.extend([file for file in wikiFiles if file not in words])

        # find those that have no parent relations
        return [word for word in words if word not in rightSide]

    def renameWord(self, word, toWord):
        if WikiFormatting.isWikiWord(toWord):
            try:
                self.getPage(toWord)
                raise WikiDataException, "Cannot rename '%s' to '%s', '%s' already exists" % (word, toWord, toWord)
            except WikiWordNotFoundException:
                pass
            
            # commit anything pending so we can rollback on error
            self.commit()

            try:
                self.execSql("update wikiwords set word = '%s' where word = '%s'" % (toWord, word))
                self.execSql("update wikirelations set word = '%s' where word = '%s'" % (toWord, word))
                self.execSql("update wikirelations set relation = '%s' where relation = '%s'" % (toWord, word))
                self.execSql("update wikiwordprops set word = '%s' where word = '%s'" % (toWord, word))
                self.execSql("update todos set word = '%s' where word = '%s'" % (toWord, word))
                rename(join(self.dataDir, "%s.wiki" % word), join(self.dataDir, "%s.wiki" % toWord))
                self.commit()
                del self.cachedWikiWords[word]
                self.cachedWikiWords[toWord] = 1
            except:
                self.dbConn.rollback()
                raise
            
            # now i have to search the wiki files and replace the old word with the new
            results = self.search(word, False)
            for resultWord in results:
                file = join(self.dataDir, "%s.wiki" % resultWord)

                fp = open(file)
                lines = fp.readlines()
                fp.close()

                bakFileName = "%s.bak" % file
                fp = open(bakFileName, 'w')
                for line in lines:
                    fp.write(line.replace(word, toWord))
                fp.close()

                unlink(file)
                rename(bakFileName, file)

        else:
            raise WikiDataException, "'%s' is an invalid wiki word" % toWord
        
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

                self.execSql("delete from wikirelations where word = '%s'" % word)
                self.execSql("delete from wikiwordprops where word = '%s'" % word)
                self.execSql("delete from wikiwords where word = '%s'" % word)
                self.execSql("delete from todos where word = '%s'" % word)
                del self.cachedWikiWords[word]
                wikiFile = self.getWikiWordFileName(word)
                if exists(wikiFile):
                    unlink(wikiFile)
                self.commit()

                # due to some bug we have to close and reopen the db sometimes
                self.dbConn.close()
                self.dbConn = gadfly.gadfly("wikidb", self.dataDir)

            except:
                self.dbConn.rollback()
                raise
        else:
            raise WikiDataException, "You cannot delete the root wiki node"            

    def deleteChildRelationships(self, fromWord):
        self.execSql("delete from wikirelations where word = '%s'" % fromWord)

    def setProperty(self, word, key, value):
        cursor = self.dbConn.cursor()
        # make sure the value doesn't already exist for this property
        cursor.execute("select word from wikiwordprops where word = '%s' and key = '%s' and value = '%s'" % (word, key, value))
        data = cursor.fetchall()
        # if it doesn't insert it
        returnValue = False
        if len(data) < 1:
            cursor.execute("insert into wikiwordprops(word, key, value) values ('%s', '%s', '%s')" % (word, key, value))
            returnValue = True
        cursor.close()
        return returnValue

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
        return self.execSqlQuerySingleColumn("select distinct(value) from wikiwordprops where key = '%s' order by value" % key)

    def getWordsWithPropertyValue(self, key, value):
        words = []
        data = self.execSqlQuery("select word from wikiwordprops where key = '%s' and value = '%s'" % (key, value))
        for row in data:
            words.append(row[0])
        return words

    def getAliasesWikiWord(self, alias):
        aliases = self.getWordsWithPropertyValue("alias", alias)
        if len(aliases) > 0:
            return aliases[0]
        return None

    def isAlias(self, word):
        "check if a word is an alias for another"
        if self.cachedWikiWords.has_key(word):
            return self.cachedWikiWords.get(word) == 2
        return False

    def addTodo(self, word, todo):
        self.execSql("insert into todos(word, todo) values (?, ?)", (word, todo))

    def getTodos(self):
        todos = []
        data = self.execSqlQuery("select word, todo from todos")
        for row in data:
            todos.append((row[0], row[1]))
        return todos

    def deleteProperties(self, word):
        self.execSql("delete from wikiwordprops where word = '%s'" % word)

    def deleteTodos(self, word):
        self.execSql("delete from todos where word = '%s'" % word)        

    def findBestPathFromWordToWord(self, word, toWord):
        "finds the shortest path from word to toWord"
        bestPath = findShortestPath(self.assembleWordGraph(word), word, toWord)
        if bestPath: bestPath.reverse()
        return bestPath

    def assembleWordGraph(self, word, graph={}):
        "recursively builds a graph of each of words parent relations"
        if not graph.has_key(word):
            parents = self.getParentRelationships(word)
            graph[word] = parents;
            for parent in parents:
                self.assembleWordGraph(parent, graph)
        return graph

    def getAllSubWords(self, word, includeRoot=False):
        subWords = []
        if (includeRoot):
            subWords.append(word)
        allWords = self.getAllWords()
        for allWordsItem in allWords:
            if allWordsItem != word and self.findBestPathFromWordToWord(allWordsItem, word):
                subWords.append(allWordsItem)
        return subWords

    def getWikiWordFileName(self, wikiWord):        
        return join(self.dataDir, "%s.%s" % (wikiWord, 'wiki'))

    def search(self, forPattern, processAnds=True):
        if processAnds:
            andPatterns = [re.compile(pattern, re.IGNORECASE)
                           for pattern in forPattern.lower().split(' and ')]
        else:
            andPatterns = [re.compile(forPattern.lower(), re.IGNORECASE)]
        
        results = []
        for file in glob.glob(join(self.dataDir, '*.wiki')):
            fp = open(file)
            fileContents = fp.read()
            fp.close()

            patternsMatched = 0            
            for pattern in andPatterns:
                if pattern.search(fileContents):
                    patternsMatched = patternsMatched + 1                    

            if patternsMatched == len(andPatterns):
                results.append(basename(file).replace('.wiki', ''))

        return results

    def saveSearch(self, search):
        "save a search into the search_views table"
        cursor = self.dbConn.cursor()
        cursor.execute('select search from search_views where search = ?', (search,))
        data = cursor.fetchall()
        if len(data) < 1:
            cursor.execute('insert into search_views(search) values (?)', (search,))
        cursor.close()

    def getSavedSearches(self):
        return self.execSqlQuerySingleColumn('select search from search_views order by search')
    
    def deleteSavedSearch(self, search):
        cursor = self.dbConn.cursor()
        cursor.execute('delete from search_views where search = ?', (search,))
        cursor.close()

    def getAllWikiWordsFromDisk(self):
        files = glob.glob(join(self.dataDir, '*.wiki'))
        return [basename(file).replace('.wiki', '') for file in files]        

    def execSql(self, sql, params=None):
        "utility method, executes the sql, no return"
        cursor = self.dbConn.cursor()
        if params:
            cursor.execute(sql, params)
        else:
            cursor.execute(sql)
        cursor.close()
    
    def execSqlQuery(self, sql):
        "utility method, executes the sql, returns query result"
        cursor = self.dbConn.cursor()
        cursor.execute(sql)
        data = cursor.fetchall()
        cursor.close()
        return data

    def execSqlQuerySingleColumn(self, sql):
        "utility method, executes the sql, returns query result"
        data = self.execSqlQuery(sql)
        return [row[0] for row in data]

    def commit(self):
        self.dbConn.commit()

    def close(self):
        self.commit()
        self.dbConn.close()


class WikiPage:
    """
    holds the data for a wikipage. fetched via the WikiData.getPage method.
    you can optionally pass the toload parameter into the constructor. this
    tells the object which pieces of data to load from the db. valid values
    are: info, parents, children, props, and todos
    """
    def __init__(self, wikiData, wikiWord, toload=None):
        self.wikiData = wikiData
        self.wikiWord = wikiWord    
        self.wikiFile = self.wikiData.getWikiWordFileName(self.wikiWord)
        self.parentRelations = []
        self.childRelations = []
        self.todos = []
        self.props = {}
        
        # load the wiki word info from the db
        if not toload or 'info' in toload:
            self.fetchWikiWordInfo()
        
        # load the wiki word parents
        if not toload or 'parents' in toload:
            self.fetchParentRelationships()

        # load the wiki word children
        if not toload or 'children' in toload:
            self.fetchChildRelationships()
        
        # fetch the props of the wiki word
        if not toload or 'props' in toload:
            self.fetchProperties()

        # fetch the todo list        
        if not toload or 'todos' in toload:
            self.fetchTodos()
        
        # does this page need to be saved
        self.saveDirty = False
        self.updateDirty = False
        
        # save when this page was last saved
        self.lastSave = time()
    
        # save when this page was last updated
        self.lastUpdate = time()

    def fetchWikiWordInfo(self):        
        data = self.wikiData.execSqlQuery("select created, modified from wikiwords where word = '%s'" % self.wikiWord)
        if (len(data) < 1):
            raise WikiWordNotFoundException, "wiki word not found: %s" % self.wikiWord
        self.created = data[0][0]
        self.modified = data[0][1]

    def fetchParentRelationships(self):
        self.parentRelations = self.wikiData.getParentRelationships(self.wikiWord)

    def fetchChildRelationships(self):
        self.childRelations = self.wikiData.getChildRelationships(self.wikiWord)

    def fetchProperties(self):
        data = self.wikiData.execSqlQuery("select key, value from wikiwordprops where word = '%s'" % self.wikiWord)
        for (key, val) in data:
            self.addProperty(key, val)
            
    def addProperty(self, key, val):
        values = self.props.get(key)
        if not values:
            values = []
            self.props[key] = values
        values.append(val)

    def fetchTodos(self):
        data = self.wikiData.execSqlQuery("select todo from todos where word = '%s'" % self.wikiWord)
        for row in data:
            self.todos.append(row[0])

    def getContent(self):
        if (not exists(self.wikiFile)):
            raise WikiFileNotFoundException, "wiki page not found: %s" % self.wikiFile        
        fp = open(self.wikiFile)
        content = fp.read()
        fp.close()
        return content

    def save(self, text, alertPWiki=True):
        self.lastSave = time()

        output = open(self.wikiFile, 'w')
        output.write(text)
        output.close()
        
        self.update(text, alertPWiki)
        self.wikiData.commit()

        self.saveDirty = False
    
    def update(self, text, alertPWiki=True):        
        self.deleteChildRelationships()
        self.deleteProperties()
        self.deleteTodos()

        textLen = len(text)        

        # 1st collect the toIgnore blocks.
        ignoreBlocks = []
        match = WikiFormatting.SuppressHighlightingRE.search(text)        
        while match:
            ignoreBlocks.append((match.start(), match.end()))
            match = WikiFormatting.SuppressHighlightingRE.search(text, match.end())

        # urls are also to be ignored
        match = WikiFormatting.UrlRE.search(text)        
        while match:
            ignoreBlocks.append((match.start(), match.end()))
            match = WikiFormatting.UrlRE.search(text, match.end())

        # script blocks are also to be ignored
        match = WikiFormatting.ScriptRE.search(text)        
        while match:
            ignoreBlocks.append((match.start(), match.end()))
            match = WikiFormatting.ScriptRE.search(text, match.end())

        # read todo's from the text        
        match = WikiFormatting.ToDoREWithContent.search(text)        
        while match:
            if not self.inIgnoreBlock(ignoreBlocks, match.start(), match.end()):
                # i couldn't get the re to ignore todos with a leading [
                if not match.group(1).startswith('['):
                    self.addTodo(match.group(1))
            match = WikiFormatting.ToDoREWithContent.search(text, match.end())

        # read relations from the text        
        match = WikiFormatting.WikiWordRE2.search(text)
        while match:
            if not self.inIgnoreBlock(ignoreBlocks, match.start(), match.end()):
                self.addChildRelationship(match.group(0))
                ignoreBlocks.append((match.start(), match.end()))
            match = WikiFormatting.WikiWordRE2.search(text, match.end())

        # read WikiWord relations from the text if they are not disabled
        if self.wikiData.pWiki.wikiWordsEnabled:
            match = WikiFormatting.WikiWordRE.search(text)        
            while match:
                if not self.inIgnoreBlock(ignoreBlocks, match.start(), match.end()):
                    relation = match.group(0)
                    # to avoid saving wiki looking words in properties
                    if match.end() < textLen:
                        if text[match.end()] != ']':
                            self.addChildRelationship(relation)
                    else:
                        # this else is neccessary for wiki words at the very end of a page
                        self.addChildRelationship(relation)
                match = WikiFormatting.WikiWordRE.search(text, match.end())

        # read properties from the text        
        match = WikiFormatting.PropertyRE.search(text)        
        while match:
            if not self.inIgnoreBlock(ignoreBlocks, match.start(), match.end()):
                # update alias cache for alias properties
                if match.group(1) == "alias":
                    word = match.group(2)
                    if not WikiFormatting.WikiWordRE.match(word):
                        word = "[%s]" % word
                    self.wikiData.cachedWikiWords[word] = 2
                    self.setProperty("alias", word)
                else:
                    self.setProperty(match.group(1), match.group(2))

            match = WikiFormatting.PropertyRE.search(text, match.end())

        # update the modified time
        self.modified = time()
        self.wikiData.execSql("update wikiwords set modified = '%s' where word = '%s'" % (self.modified, self.wikiWord))
        self.lastUpdate = self.modified

        # kill the global prop cache in case any props were added
        self.wikiData.cachedGlobalProps = None

        # add a relationship to the scratchpad at the root
        if self.wikiWord == self.wikiData.pWiki.wikiName:
            self.addChildRelationship("ScratchPad")

        # clear the dirty flag
        self.updateDirty = False

        if alertPWiki:        
            self.wikiData.pWiki.OnWikiPageUpdate(self)

    def inIgnoreBlock(self, ignoreBlocks, start, end):
        "true if start to end intersects with an existing applied style"
        for (ignoreStart, ignoreEnd) in ignoreBlocks:
            if start >= ignoreStart and start <= ignoreEnd:
                return True
            if end <= ignoreEnd and end >= ignoreStart:
                return True
            if start < ignoreStart and end > ignoreEnd:
                return True
        return False

    def addChildRelationship(self, toWord):
        if toWord not in self.childRelations:
            if self.wikiData.addRelationship(self.wikiWord, toWord):
                self.childRelations.append(toWord)

    def setProperty(self, key, value):
        if self.wikiData.setProperty(self.wikiWord, key, value):
            self.addProperty(key, value)

    def addTodo(self, todo):
        if todo not in self.todos:
            if self.wikiData.addTodo(self.wikiWord, todo):
                self.todos.append(todo)

    def deleteChildRelationships(self):
        self.wikiData.deleteChildRelationships(self.wikiWord)
        self.childRelations = []

    def deleteProperties(self):
        self.wikiData.deleteProperties(self.wikiWord)
        self.props = {}

    def deleteTodos(self):
        self.wikiData.deleteTodos(self.wikiWord)
        self.todos = []

    def setDirty(self, dirt):
        self.saveDirty = dirt
        self.updateDirty = dirt

    def getDirty(self):
        return (self.saveDirty, self.updateDirty)


####################################################
# module level functions
####################################################

def createWikiDB(wikiName, dataDir, overwrite=False):
    "creates the initial db"
    if (not exists(dataDir) or overwrite):
        if (not exists(dataDir)):
            mkdir(dataDir)

        # create the new gadfly database
        connection = gadfly.gadfly()
        connection.startup("wikidb", dataDir)

        # create the tables, etc                
        cursor = connection.cursor()
        cursor.execute("create table wikiwords (word varchar, created varchar, modified varchar)")
        cursor.execute("create table wikirelations (word varchar, relation varchar, created varchar)")
        cursor.execute("create table wikiwordprops (word varchar, key varchar, value varchar)")
        cursor.execute("create table todos (word varchar, todo varchar)")
        cursor.execute("create table search_views (search varchar)")

        cursor.execute("create unique index wikiwords_pkey on wikiwords(word)")
        cursor.execute("create unique index wikirelations_pkey on wikirelations(word, relation)")
        cursor.execute("create index wikirelations_word on wikirelations(word)")
        cursor.execute("create index wikiwordprops_word on wikiwordprops(word)")

        connection.commit()
        
        # close the connection
        connection.close()
        
    else:
        raise WikiDBExistsException, "database already exists at location: %s" % dataDir
    
def findShortestPath(graph, start, end, path=[]):
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

class WikiDataException(Exception): pass
class WikiWordNotFoundException(WikiDataException): pass
class WikiFileNotFoundException(WikiDataException): pass
class WikiDBExistsException(WikiDataException): pass
