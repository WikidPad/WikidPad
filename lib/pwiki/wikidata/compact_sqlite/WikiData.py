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



from os import mkdir, unlink, listdir, rename, stat, utime
from os.path import exists, join, basename
from time import time, localtime
import datetime
import string, glob, types, sets
import pwiki.srePersistent as re

from pwiki.WikiExceptions import *   # TODO make normal import
from pwiki import SearchAndReplace
# from SqliteThin3 import *

try:
    import pwiki.sqlite3api as sqlite
    import DbStructure
    from DbStructure import createWikiDB, WikiDBExistsException
except:
    sqlite = None
# finally:
#     pass

from pwiki.StringOps import getBinCompactForDiff, applyBinCompact, mbcsEnc, mbcsDec,\
        binCompactToCompact, fileContentToUnicode, utf8Enc, utf8Dec, Tokenizer

from pwiki import WikiFormatting
from pwiki import PageAst

# from pwiki.DocPages import WikiPage


class WikiData:
    "Interface to wiki data."
    def __init__(self, pWiki, dataDir):
        self.pWiki = pWiki
        self.dataDir = dataDir

        dbfile = join(dataDir, "wiki.sli")

        if (not exists(dbfile)):
            DbStructure.createWikiDB(None, dataDir)  # , True

        self.connWrap = DbStructure.ConnectWrap(sqlite.connect(dbfile))
        self.commit = self.connWrap.commit

        DbStructure.registerSqliteFunctions(self.connWrap)

        formatcheck, formatmsg = DbStructure.checkDatabaseFormat(self.connWrap)

        if formatcheck == 2:
            # Unknown format
            raise WikiDataException, formatmsg

        # Update database from previous versions if necessary
        if formatcheck == 1:
            try:
                DbStructure.updateDatabase(self.connWrap)
            except:
                self.connWrap.rollback()
                raise

        # Activate UTF8 support for text in database (content is blob!)
        DbStructure.registerUtf8Support(self.connWrap)

        # Function to convert from content in database to
        # return value, used by getContent()
        self.contentDbToOutput = lambda c: utf8Dec(c, "replace")[0]
        
        # Set marker for database type
        self.pWiki.configuration.set("main", "wiki_database_type",
                "compact_sqlite")

        # Function to convert unicode strings from input to content in database
        # used by setContent

        def contentUniInputToDb(unidata):
            return utf8Enc(unidata, "replace")[0]

        self.contentUniInputToDb = contentUniInputToDb


        # Temporary table for findBestPathFromWordToWord

        # These schema changes are only on a temporary table so they are not
        # in DbStructure.py
        self.connWrap.execSql("create temp table temppathfindparents "+
                "(word text primary key, child text, steps integer)")

        self.connWrap.execSql("create index temppathfindparents_steps "+
                "on temppathfindparents(steps)")

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


    def _reinit(self):
        """
        Actual initialization or reinitialization after rebuildWiki()
        """
        


    # ---------- Direct handling of page data ----------
    
    def getContent(self, word):
        result = self.connWrap.execSqlQuerySingleItem("select content from "+\
            "wikiwordcontent where word = ?", (word,), None)

        if result is None:
            raise WikiFileNotFoundException, "wiki page not found: %s" % word

        # print "getContent", repr(result)
        
        # if self.contentDbToOutput:
        return self.contentDbToOutput(result)
        # else:
        #     return result


    def _getContentAndInfo(self, word):
        """
        Get content and further information about a word
        
        Not part of public API!
        """
        result = self.connWrap.execSqlQuery("select content, modified from "+\
            "wikiwordcontent where word = ?", (word,))
        if len(result) == 0:
            raise WikiFileNotFoundException, "wiki page not found: %s" % word

        content = self.contentDbToOutput(result[0][0])
        return (content, result[0][1])


    def setContent(self, word, content, moddate = None, creadate = None):
        """
        Sets the content, does not modify the cache information
        except self.cachedContentNames
        """
        if not content: content = u""  # ?
        
        assert type(content) is unicode

        content = self.contentUniInputToDb(content)
        self.setContentRaw(word, content, moddate, creadate)

        self.cachedContentNames[word] = 1


    def setContentRaw(self, word, content, moddate = None, creadate = None):
        """
        Sets the content without applying any encoding, used by versioning,
        does not modify the cache information
        
        moddate -- Modification date to store or None for current
        creadate -- Creation date to store or None for current 
        
        Not part of public API!
        """
        ti = time()
        if moddate is None:
            moddate = ti

        # if not content: content = ""
        
        assert type(content) is str

        if self.connWrap.execSqlQuerySingleItem("select word from "+\
                "wikiwordcontent where word=?", (word,), None) is not None:

            # Word exists already
            self.connWrap.execSql("insert or replace into wikiwordcontent"+\
                "(word, content, modified) values (?,?,?)",
                (word, sqlite.Binary(content), moddate))
        else:
            if creadate is None:
                creadate = ti

            # Word does not exist -> record creation date
            self.connWrap.execSql("insert or replace into wikiwordcontent"+\
                "(word, content, modified, created) values (?,?,?,?)",
                (word, sqlite.Binary(content), moddate, creadate))

    def renameContent(self, oldWord, newWord):
        """
        The content which was stored under oldWord is stored
        after the call under newWord. The self.cachedContentNames
        dictionary is updated, other caches won't be updated.
        """
        self.connWrap.execSql("update wikiwordcontent set word = ? where word = ?",
                (newWord, oldWord))

        del self.cachedContentNames[oldWord]
        self.cachedContentNames[newWord] = 1


    def deleteContent(self, word):
        """
        Deletes a page
        """
        try:
            self.connWrap.execSql("delete from wikiwordcontent where word = ?", (word,))
            del self.cachedContentNames[word]
        except sqlite.Error:
            raise WikiFileNotFoundException, "wiki page for deletion not found: %s" % word

    def getTimestamps(self, word):
        """
        Returns a tuple with modification and creation date of
        a word or (None, None) if word is not in the database
        """
        dates = self.connWrap.execSqlQuery(
                "select modified, created from wikiwordcontent where word = ?",
                (word,))

        if len(dates) > 0:
            return (float(dates[0][0]), float(dates[0][1]))
        else:
            return (None, None)  # ?


    # ---------- Renaming/deleting pages with cache update ----------

    def renameWord(self, word, toWord):
        if not self.pWiki.getFormatting().isNakedWikiWord(toWord):
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

#             # now we have to search the wiki files and replace the old word with the new
#             searchOp = SearchAndReplace.SearchReplaceOperation()
#             searchOp.wikiWide = True
#             searchOp.wildCard = 'no'
#             searchOp.caseSensitive = True
#             searchOp.searchStr = word
#             
#             results = self.search(searchOp)
#             for resultWord in results:
#                 content = self.getContent(resultWord)
#                 content = content.replace(word, toWord)
#                 self.setContent(resultWord, content)

            self.connWrap.commit()
        except:
            self.connWrap.rollback()
            raise


    def deleteWord(self, word):
        """
        delete everything about the wikiword passed in. an exception is raised
        if you try and delete the wiki root node.
        """
        if word != self.pWiki.wikiName:
            try:
                # don't delete the relations to the word since other
                # pages still have valid outward links to this page.
                # just delete the content

                self.connWrap.commit()
                self.connWrap.execSql("delete from wikirelations where word = ?", (word,))
                self.connWrap.execSql("delete from wikiwordprops where word = ?", (word,))
                self.connWrap.execSql("delete from todos where word = ?", (word,))
                self.deleteContent(word)
                # self.connWrap.execSql("delete from wikiwordcontent where word = ?", (word,))
                # del self.cachedContentNames[word]

                self.connWrap.commit()

                # due to some bug we have to close and reopen the db sometimes (gadfly)
                ## self.dbConn.close()
                ## self.dbConn = gadfly.gadfly("wikidb", self.dataDir)

            except:
                self.connWrap.rollback()
                raise
        else:
            raise WikiDataException, "You cannot delete the root wiki node"


    # ---------- Handling of relationships cache ----------

    def getAllRelations(self):
        "get all of the relations in the db"
        relations = []
        data = self.connWrap.execSqlQuery("select word, relation from wikirelations")
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
            position of link in page (may be -1 to represent unknown)
        """
        if withPosition:
            sql = "select relation, firstcharpos from wikirelations where word = ?"
        else:
            sql = "select relation from wikirelations where word = ?"

        if existingonly:
            # filter to only words in wikiwords or aliases
            sql += " and (exists (select word from wikiwordcontent "+\
                    "where word = relation) or exists "+\
                    "(select value from wikiwordprops "+\
                    "where value = relation and key = 'alias'))"

        if not selfreference:
            sql += " and relation != word"
            
        if withPosition:
            return self.connWrap.execSqlQuery(sql, (wikiWord,))
        else:
            return self.connWrap.execSqlQuerySingleColumn(sql, (wikiWord,))



#     def getChildRelationshipsAndHasChildren(self, wikiWord, existingonly=False,
#             selfreference=True):
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
#             # filter to only words in wikiwordcontent or aliases
#             innersql += " and (exists (select word from wikiwordcontent "+\
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
#             # filter to only words in wikiwordcontent or aliases
#             outersql += " and (exists (select word from wikiwordcontent "+\
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
        "get the parent relations to this word"
#         return self.connWrap.execSqlQuerySingleColumn(
#                 "select word from wikirelations where relation = ?", (wikiWord,))
 
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
        """

        return self.connWrap.execSqlQuerySingleColumn(
                "select word from wikiwordcontent where not word glob '[[]*' "
                "except select relation from wikirelations")

    def addRelationship(self, word, toWord):
        """
        Add a relationship from word toWord.
        A relation from one word to another is unique and can't be added twice.
        """
        self.connWrap.execSql(
                "insert or replace into wikirelations(word, relation) "
                "values (?, ?)", (word, toWord))

    def updateChildRelations(self, word, childRelations):
        self.deleteChildRelationships(word)
        for r in childRelations:
            self.addRelationship(word, r)

    def deleteChildRelationships(self, fromWord):
        self.connWrap.execSql(
                "delete from wikirelations where word = ?", (fromWord,))


    # TODO Maybe optimize
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


    def findBestPathFromWordToWord(self, word, toWord):
        """
        finds the shortest path from word to toWord going through the parents.
        word and toWord are included as first/last element. If word == toWord,
        it is included only once as the single element of the list.
        If there is no path from word to toWord, [] is returned
        """

        if word == toWord:
            return [word]

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


    # ---------- Listing/Searching wiki words (see also "alias handling", "searching pages")----------

    def getAllDefinedWikiPageNames(self):
        "get the names of all wiki pages in the db, no aliases"
        return self.connWrap.execSqlQuerySingleColumn(
                "select word from wikiwordcontent where not word glob '[[]*'")

    def getAllDefinedContentNames(self):
        "get the names of all the content elements in the db, no aliases"
        return self.connWrap.execSqlQuerySingleColumn(
                "select word from wikiwordcontent")


    def refreshDefinedContentNames(self):
        """
        Refreshes the internal list of defined pages which
        may be different from the list of pages for which
        content is available (not possible for compact database).
        The function tries to conserve additional informations
        (creation/modif. date) if possible.
        
        It is mainly called during rebuilding of the wiki 
        so it may not rely on the presence of other cache
        information (e.g. relations).
        
        The self.cachedContentNames is also updated.
        """
        self.cachedContentNames = {}

        # cache aliases
        aliases = self.getAllAliases()
        for alias in aliases:
            self.cachedContentNames[alias] = 2

        # recreate word caches
        for word in self.getAllDefinedContentNames():
            self.cachedContentNames[word] = 1


#     # TODO More general Wikiword to filename mapping
#     def getAllPageNamesFromDisk(self):   # Used for rebuilding wiki
#         return self.connWrap.execSqlQuerySingleColumn("select word from wikiwordcontent")

#     # TODO More general Wikiword to filename mapping
#     def getWikiWordFileName(self, wikiWord):
#         return join(self.dataDir, u"%s.wiki" % wikiWord)

    def isDefinedWikiWord(self, word):
        "check if a word is a valid wikiword (page name or alias)"
        return self.cachedContentNames.has_key(word)

    def getWikiWordsStartingWith(self, thisStr, includeAliases=False):
        "get the list of words starting with thisStr. used for autocompletion."

        # Escape some characters:   # TODO more elegant
        thisStr = thisStr.replace("[", "[[").replace("]", "[]]").replace("[[", "[[]")
        if includeAliases:
            return self.connWrap.execSqlQuerySingleColumn(
                    "select word from wikiwordcontent where word glob (? || '*') union "+\
                    "select value from wikiwordprops where key = 'alias' and value glob (? || '*')", (thisStr, thisStr))
        else:
            return self.connWrap.execSqlQuerySingleColumn("select word from wikiwordcontent where word glob (? || '*')", (thisStr,))

    def getWikiWordsWith(self, thisStr, includeAliases=False):
        """
        get the list of words with thisStr in them,
        if possible first these which start with thisStr.
        """
        result = self.connWrap.execSqlQuerySingleColumn(
                "select word from wikiwordcontent where word like (? || '%')",
                (thisStr,))

        if includeAliases:
            result += self.connWrap.execSqlQuerySingleColumn(
                    "select value from wikiwordprops where key = 'alias' and "
                    "value like (? || '%')", (thisStr,))


        result += self.connWrap.execSqlQuerySingleColumn(
                "select word from wikiwordcontent "
                "where word like ('%' || ? || '%') and word not like (? || '%')"
                "and word not glob '[[]*'", (thisStr, thisStr))

        if includeAliases:
            result += self.connWrap.execSqlQuerySingleColumn(
                    "select value from wikiwordprops where key = 'alias' and "
                    "value like ('%' || ? || '%') and value not like (? || '%')",
                    (thisStr, thisStr))

        return result

#         r1 = self.connWrap.execSqlQuerySingleColumn(
#                 "select word from wikiwordcontent where word like (? || '%')",
#                 (thisStr,))
#         return r1 + self.connWrap.execSqlQuerySingleColumn(
#                 "select word from wikiwordcontent "
#                 "where word like ('%' || ? || '%') and word not like (? || '%')"
#                 "and word not glob '[[]*'", (thisStr, thisStr))

    def getWikiWordsModifiedWithin(self, days):
        timeDiff = float(time()-(86400*days))
        return self.connWrap.execSqlQuerySingleColumn(
                "select word from wikiwordcontent where modified >= ?",
                (timeDiff,))



    # ---------- Property cache handling ----------

    def getPropertyNames(self):
        """
        Return all property names (not beginning with "global.")
        in ascending order (C sort)
        """
        return self.connWrap.execSqlQuerySingleColumn(
                "select distinct(key) from wikiwordprops "
                "where key not glob 'global.*' order by key")

    # TODO More efficient? (used by autocompletion)
    def getPropertyNamesStartingWith(self, startingWith):
        names = self.connWrap.execSqlQuerySingleColumn(
                "select distinct(key) from wikiwordprops order by key")
        return [name for name in names if name.startswith(startingWith)]

    def getGlobalProperties(self):
        if not self.cachedGlobalProps:
            return self.updateCachedGlobalProps()

        return self.cachedGlobalProps

    def getDistinctPropertyValues(self, key):
        return self.connWrap.execSqlQuerySingleColumn(
                "select distinct(value) from wikiwordprops where key = ? "
                "order by value", (key,))

    def getWordsForPropertyName(self, key):
        return self.connWrap.execSqlQuerySingleColumn(
                "select distinct(word) from wikiwordprops where key = ? ",
                (key,))

    def getWordsWithPropertyValue(self, key, value):
        return self.connWrap.execSqlQuerySingleColumn(
                "select word from wikiwordprops where key = ? and value = ?",
                (key, value))

    def getPropertiesForWord(self, word):
        """
        Returns list of tuples (key, value) of key and value
        of all properties for word.
        """
        return self.connWrap.execSqlQuery("select key, value "+
                    "from wikiwordprops where word = ?", (word,))

    def setProperty(self, word, key, value):
        self.connWrap.execSql("insert into wikiwordprops(word, key, value) values (?, ?, ?)", (word, key, value))

    def updateProperties(self, word, props):
        self.deleteProperties(word)
        for k in props.keys():
            values = props[k]
            for v in values:
                self.setProperty(word, k, v)
                if k == "alias":
                    self.setAsAlias(v)  # TODO

    def updateCachedGlobalProps(self):
        """
        TODO: Should become part of public API!
        """
        data = self.connWrap.execSqlQuery("select key, value from wikiwordprops "+\
                "where key glob 'global.*'")
        globalMap = {}
        for (key, val) in data:
            globalMap[key] = val

        self.cachedGlobalProps = globalMap

        return globalMap

    def deleteProperties(self, word):
        self.connWrap.execSql("delete from wikiwordprops where word = ?", (word,))


    # ---------- Alias handling ----------

    def getAliasesWikiWord(self, alias):
        """
        If alias is an alias wiki word, return the original word,
        otherwise return alias
        """
        if not self.isAlias(alias):
            return alias

        aliases = self.getWordsWithPropertyValue("alias", alias)
        if len(aliases) > 0:
            return aliases[0]
        return alias  # None

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
        return self.connWrap.execSqlQuerySingleColumn(
                "select value from wikiwordprops where key = 'alias'")


    # ---------- Todo cache handling ----------

    def getTodos(self):
        return self.connWrap.execSqlQuery("select word, todo from todos")

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
        self.connWrap.execSql("insert into todos(word, todo) values (?, ?)", (word, todo))

    def deleteTodos(self, word):
        self.connWrap.execSql("delete from todos where word = ?", (word,))


    # ---------- Searching pages ----------

    # TODO Other searchmodes
    def search_fallback(self, forPattern, processAnds=True, caseSensitive=False,
            searchmode=0):
        """
        Backup method for non sqlite (without user-defined functions).
        Currently unused
        """
        if caseSensitive:
            reFlags = re.MULTILINE | re.UNICODE
        else:
            reFlags = re.IGNORECASE | re.MULTILINE | re.UNICODE
        
        if processAnds:
            andPatterns = [re.compile(pattern, reFlags)
                           for pattern in forPattern.split(u' and ')]
#                            for pattern in forPattern.lower().split(u' and ')]
        else:
            andPatterns = [re.compile(forPattern, reFlags)]


        itr = self.connWrap.execSqlQueryIter("select word, content from wikiwordcontent")

        results = []

        for word, content in itr:
            for pattern in andPatterns:
                if not pattern.search(content):
                    word = None
                    break

            if word:
                results.append(word)

        return results


#     # TODO Other searchmodes
#     def search_old(self, forPattern, processAnds=True, caseSensitive=False,
#             searchmode=0):
#         """
#         Search all content for the forPattern.
#         This version uses sqlite user-defined functions.
#         Use search_fallback for other databases
#         """
#         if caseSensitive:
#             reFlags = re.MULTILINE | re.UNICODE
#         else:
#             reFlags = re.IGNORECASE | re.MULTILINE | re.UNICODE
#         
#         if processAnds:
#             andPatterns = [re.compile(pattern, reFlags)
#                            for pattern in forPattern.split(u' and ')]
# #                            for pattern in forPattern.lower().split(u' and ')]
#         else:
#             andPatterns = [re.compile(forPattern, reFlags)]
# 
#         result = self.connWrap.execSqlQuerySingleColumn(
#                 "select word from wikiwordcontent where "+\
#                 "testMatch(content, ?)", (sqlite.addTransObject(andPatterns),))
# 
#         sqlite.delTransObject(andPatterns)
# 
#         return result


    def search(self, sarOp, applyOrdering=True):
        """
        Search all content using the SearchAndReplaceOperation sarOp and
        return list of all page names match the search criteria.
        This version uses sqlite user-defined functions.
        TODO: Use search_fallback for other databases (currently not working!)
        """
        sarOp.beginWikiSearch(self)
        try:
            result = self.connWrap.execSqlQuerySingleColumn(
                    "select word from wikiwordcontent where "+\
                    "word not glob '[[]*' and testMatch(word, content, ?)",
                    (sqlite.addTransObject(sarOp),))
    
            sqlite.delTransObject(sarOp)
            
            if applyOrdering:
                result = sarOp.applyOrdering(result)
        finally:
            sarOp.endWikiSearch()

        return result


    def saveSearch(self, title, datablock):
        "save a search into the search_views table"
        self.connWrap.execSql(
                "insert or replace into search_views(title, datablock) "+\
                "values (?, ?)", (title, sqlite.Binary(datablock)))

    def getSavedSearchTitles(self):
        """
        Return the titles of all stored searches in alphabetical order
        """
        return self.connWrap.execSqlQuerySingleColumn(
                "select title from search_views order by title")

    def getSearchDatablock(self, title):
        return self.connWrap.execSqlQuerySingleItem(
                "select datablock from search_views where title = ?", (title,))

    def deleteSavedSearch(self, title):
        self.connWrap.execSql(
                "delete from search_views where title = ?", (title,))


    # ---------- Miscellaneous ----------

    _CAPABILITIES = {
        "rebuild": 1,
        "compactify": 1,     # = sqlite vacuum
        "versioning": 1,     # TODO (old versioning)
        "plain text import":1        
        }


    def checkCapability(self, capkey):
        """
        Check the capabilities of this WikiData implementation.
        The capkey names the capability, the function returns normally
        a version number or None if not supported
        """
        return WikiData._CAPABILITIES.get(capkey, None)


        # TODO drop and recreate tables and indices!
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

    def close(self):
        self.connWrap.commit()
        self.connWrap.close()

        self.connWrap = None


    # ---------- Versioning (optional) ----------
    # Must be implemented if checkCapability returns a version number
    #     for "versioning".
        
    def storeModification(self, word):
        """ Store the modification for a single word (wikicontent and headversion for the word must exist)
        between wikicontents and headversion in the changelog.
        Does not modify headversion. It is recommended to not call this directly

        Values for the op-column in the changelog:
        0 set content: set content as it is in content column
        1 modify: content is a binary compact diff as defined in StringOps,
            apply it to new revision to get the old one.
        2 create page: content contains data of the page
        3 delete page: content is undefined
        """

        content, moddate = self._getContentAndInfo(word)[:2]

        headcontent, headmoddate = self.connWrap.execSqlQuery("select content, modified from headversion "+\
                "where word=?", (word,))[0]

        bindiff = getBinCompactForDiff(content, headcontent)
        self.connWrap.execSql("insert into changelog (word, op, content, moddate) values (?, ?, ?, ?)",
                (word, 1, sqlite.Binary(bindiff), headmoddate))  # Modify  # TODO: Support overwrite
        return self.connWrap.lastrowid


    def hasVersioningData(self):
        """
        Returns true iff any version information is stored in the database
        """
        return DbStructure.hasVersioningData(self.connWrap)


    def storeVersion(self, description):
        """
        Store the current version of a wiki in the changelog

        Values for the op-column in the changelog:
        0 set content: set content as it is in content column
        1 modify: content is a binary compact diff as defined in StringOps,
            apply it to new revision to get the old one.
        2 create page: content contains data of the page
        3 delete page: content is undefined

        Renaming is not supported directly.
        """
        # Test if tables were created already

        if not DbStructure.hasVersioningData(self.connWrap):
            # Create the tables
            self.connWrap.commit()
            try:
                DbStructure.createVersioningTables(self.connWrap)
                # self.connWrap.commit()
            except:
                self.connWrap.rollback()
                raise

        self.connWrap.commit()
        try:
            # First move head version to normal versions
            headversion = self.connWrap.execSqlQuery("select description, "+\
                    "created from versions where id=0") # id 0 is the special head version
            if len(headversion) == 1:
                firstchangeid = self.connWrap.execSqlQuerySingleItem("select id from changelog order by id desc limit 1 ",
                        default = -1) + 1

                # Find modified words
                modwords = self.connWrap.execSqlQuerySingleColumn("select headversion.word from headversion inner join "+\
                        "wikiwordcontent on headversion.word = wikiwordcontent.word where "+\
                        "headversion.modified != wikiwordcontent.modified")

                for w in modwords:
                    self.storeModification(w)


                # Store changes for deleted words
                self.connWrap.execSql("insert into changelog (word, op, content, moddate) "+\
                        "select word, 2, content, modified from headversion where "+\
                        "word not in (select word from wikiwordcontent)")

                # Store changes for inserted words
                self.connWrap.execSql("insert into changelog (word, op, content, moddate) "+\
                        "select word, 3, x'', modified from wikiwordcontent where "+\
                        "word not in (select word from headversion)")

                if firstchangeid == (self.connWrap.execSqlQuerySingleItem("select id from changelog order by id desc limit 1 ",
                        default = -1) + 1):

                    firstchangeid = -1 # No changes recorded in changelog

                headversion = headversion[0]
                self.connWrap.execSql("insert into versions(description, firstchangeid, created) "+\
                        "values(?, ?, ?)", (headversion[0], firstchangeid, headversion[1]))

            self.connWrap.execSql("insert or replace into versions(id, description, firstchangeid, created) "+\
                    "values(?, ?, ?, ?)", (0, description, -1, time()))

            # Copy from wikiwordcontent everything to headversion
            self.connWrap.execSql("delete from headversion")
            self.connWrap.execSql("insert into headversion select * from wikiwordcontent")

            self.connWrap.commit()
        except:
            self.connWrap.rollback()
            raise


    def getStoredVersions(self):
        """
        Return a list of tuples for each stored version with (<id>, <description>, <creation date>).
        Newest versions at first
        """
        # Head version first
        result = self.connWrap.execSqlQuery("select id, description, created "+\
                    "from versions where id == 0")

        result += self.connWrap.execSqlQuery("select id, description, created "+\
                    "from versions where id != 0 order by id desc")
        return result


    # TODO: Wrong moddate?
    def applyChange(self, word, op, content, moddate):
        """
        Apply a single change to wikiwordcontent. word, op, content and modified have the
        same meaning as in the changelog table
        """
        if op == 0:
            self.setContentRaw(word, content, moddate)
        elif op == 1:
            self.setContentRaw(word, applyBinCompact(self.getContent(word), content), moddate)
        elif op == 2:
            self.setContentRaw(word, content, moddate)
        elif op == 3:
            self.deleteContent(word)


    # TODO: Wrong date?, more efficient
    def applyStoredVersion(self, id):
        """
        Set the content back to the version identified by id (retrieved by getStoredVersions).
        Only wikiwordcontent is modified, the cache information must be updated separately
        """

        self.connWrap.commit()
        try:
            # Start with head version
            self.connWrap.execSql("delete from wikiwordcontent") #delete all rows
            self.connWrap.execSql("insert into wikiwordcontent select * from headversion") # copy from headversion

            if id != 0:
                lowestchangeid = self.connWrap.execSqlQuerySingleColumn("select firstchangeid from versions where id == ?",
                        (id,))
                if len(lowestchangeid) == 0:
                    raise WikiFileNotFoundException()  # TODO: Better exception

                lowestchangeid = lowestchangeid[0]

                changes = self.connWrap.execSqlQuery("select word, op, content, moddate from changelog "+\
                        "where id >= ? order by id desc", (lowestchangeid,))

                for c in changes:
                    self.applyChange(*c)


            self.connWrap.commit()
        except:
            self.connWrap.rollback()
            raise


    def deleteVersioningData(self):
        """
        Completely delete all versioning information
        """
        DbStructure.deleteVersioningTables(self.connWrap)


    # ---------- Other optional functionality ----------

    def cleanupAfterRebuild(self, progresshandler):
        """
        Rebuild cached structures, try to repair database inconsistencies.

        Must be implemented if checkCapability returns a version number
        for "rebuild".
        
        progresshandler -- Object, fulfilling the GuiProgressHandler
            protocol
        """
#         # get all of the wikiWords
#         wikiWords = self.getAllPageNamesFromDisk()   # Replace this call
#                 
#         progresshandler.open(len(wikiWords) + 1)
#         try:
#             step = 1
#     
#             # re-save all of the pages
#             self.clearCacheTables()
#             for wikiWord in wikiWords:
#                 progresshandler.update(step, u"")   # , "Rebuilding %s" % wikiWord)
#                 wikiPage = self.createPage(wikiWord)
#                 wikiPage.update(wikiPage.getContent(), False)  # TODO AGA processing
#                 step = step + 1
                
        DbStructure.rebuildIndices(self.connWrap)

        # TODO
        # Check the presence of important indexes

        indexes = self.connWrap.execSqlQuerySingleColumn(
                "select name from sqlite_master where type='index'")
        indexes = map(string.upper, indexes)
        
        if not "WIKIWORDCONTENT_PKEY" in indexes:
            # Maybe we have multiple pages with the same name in the database
            
            # Copy valid creation date to all pages
            self.connWrap.execSql("update wikiwordcontent set "
                    "created=(select max(created) from wikiwordcontent as "
                    "inner where inner.word=wikiwordcontent.word)")
            
            # Delete all but the newest page
            self.connWrap.execSql("delete from wikiwordcontent where "
                    "ROWID not in (select max(ROWID) from wikiwordcontent as "
                    "outer where modified=(select max(modified) from "
                    "wikiwordcontent as inner where inner.word=outer.word) "
                    "group by outer.word)")
                    
            DbStructure.rebuildIndices(self.connWrap)

       # TODO: More repair operations


#         # recreate word caches
#         self.cachedContentNames = {}
#         for word in self.getAllDefinedContentNames():
#             self.cachedContentNames[word] = 1
# 
#         # cache aliases
#         aliases = self.getAllAliases()
#         for alias in aliases:
#             self.cachedContentNames[alias] = 2


#         finally:            
#             progresshandler.close()


    def vacuum(self):
        """
        Reorganize the database, free unused space.
        
        Must be implemented if checkCapability returns a version number
        for "compactify".        
        """
        self.connWrap.commit()
        self.connWrap.execSql("vacuum")


    # TODO: Better error checking
    def copyWikiFilesToDatabase(self):
        """
        Helper to transfer wiki files into database for migrating from
        original WikidPad to specialized databases.

        Must be implemented if checkCapability returns a version number
        for "plain text import".
        """
        self.connWrap.commit()

        fnames = glob.glob(join(mbcsEnc(self.dataDir, "replace")[0], '*.wiki'))
        for fn in fnames:
            word = basename(mbcsDec(fn, "replace")[0]).replace('.wiki', '')   # mbcsDec

            fp = open(fn)
            content = fp.read()
            fp.close()
            content = fileContentToUnicode(content)
#             word = self.pWiki.getFormatting().normalizeWikiWordImport(word)
            if self.pWiki.getFormatting().isNakedWikiWord(word):
                self.setContent(word, content, moddate=stat(fn).st_mtime)
#             self.connWrap.execSql("insert or replace into wikiwordcontent(word, "+\
#                     "content, modified) values (?,?,?)", (word, sqlite.Binary(content), \
#                         stat(fn).st_mtime))

        self.connWrap.commit()


def listAvailableWikiDataHandlers(pWiki):
    """
    Returns a list with the names of available handlers from this module.
    Each item is a tuple (<internal name>, <descriptive name>)
    """
    if sqlite is not None:
        return [("compact_sqlite", "Compact Sqlite")]
    else:
        return []


def getWikiDataHandler(pWiki, name):
    """
    Returns a creation function (or class) for an appropriate
    WikiData object and a createWikiDB function or (None, None)
    if name is unknown
    """
    if name == "compact_sqlite":
        return WikiData, createWikiDB
    
    return (None, None)
