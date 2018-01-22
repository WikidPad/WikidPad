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
            "Initialize external sqlite for compact_sqlite/WikiData.py")

    sqlite = None
# finally:
#     pass

from ... import StringOps

from ...StringOps import longPathEnc, \
        longPathDec, fileContentToUnicode, utf8Enc, utf8Dec

from ..BaseWikiData import BasicWikiData

import Consts

class WikiData(BasicWikiData):
    "Interface to wiki data."
    def __init__(self, wikiDocument, dataDir, tempDir):
        self.wikiDocument = wikiDocument
        self.dataDir = dataDir
        self.cachedWikiPageLinkTermDict = None

        self.dbFilename = "wiki.sli"


        self.CreateAndConnectToDb(DbStructure)

        app = GetApp()

        if app is not None:
            self.initSqlite(app)

        DbStructure.registerSqliteFunctions(self.connWrap)


    def checkDatabaseFormat(self):
        return DbStructure.checkDatabaseFormat(self.connWrap)


    def connect(self, recoveryMode=False):
        if not recoveryMode:
            formatcheck, formatmsg = self.checkDatabaseFormat()
    
            if formatcheck == 2:
                # Unknown format
                raise WikiDataException(formatmsg)
    
            # Update database from previous versions if necessary
            if formatcheck == 1:
                try:
                    DbStructure.updateDatabase(self.connWrap, self.dataDir)
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
            if not recoveryMode:
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
                    "compact_sqlite")
        except (IOError, OSError, sqlite.Error) as e:
            # Remember but continue
            lastException = DbWriteAccessError(e)

        # Function to convert unicode strings from input to content in database
        # used by setContent

        def contentUniInputToDb(unidata):
            return utf8Enc(unidata, "replace")[0]

        self.contentUniInputToDb = contentUniInputToDb

        try:
            if not recoveryMode:
                self._createTempTables()

            # reset cache
            self.cachedWikiPageLinkTermDict = None
            self.cachedGlobalAttrs = None
            
            if not recoveryMode:
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
            result = self.connWrap.execSqlQuerySingleItem("select content from "+\
                "wikiwords where word = ?", (word,), None)

            if result is None:
                raise WikiFileNotFoundException(_("Wiki page not found: %s") % word)
    
            return self.contentDbToOutput(result)
        except (IOError, OSError, sqlite.Error) as e:
            traceback.print_exc()
            raise DbReadAccessError(e)


    def _getContentAndInfo(self, word):
        """
        Get content and further information about a word
        
        Not part of public API!
        """
        try:
            result = self.connWrap.execSqlQuery("select content, modified from "+\
                "wikiwords where word = ?", (word,))
            if len(result) == 0:
                raise WikiFileNotFoundException("wiki page not found: %s" % word)
    
            content = self.contentDbToOutput(result[0][0])
            return (content, result[0][1])
        except (IOError, OSError, sqlite.Error) as e:
            traceback.print_exc()
            raise DbReadAccessError(e)


    def iterAllWikiPages(self):
        """
        Returns iterator over all wiki pages. Each iteration returns a tuple
        (word, content, modified timestamp, created timestamp, visited timestamp).
        
        This is only part of public API if "recovery mode" is supported.
        """
        return self.connWrap.execSqlQueryIter(
                "select word, content, modified, created, visited from wikiwords")


    def setContent(self, word, content, moddate = None, creadate = None):
        """
        Sets the content, does not modify the cache information
        except self.cachedWikiPageLinkTermDict
        """
        if not content: content = ""  # ?
        
        assert type(content) is str

        content = self.contentUniInputToDb(content)
        self.setContentRaw(word, content, moddate, creadate)

        self.cachedWikiPageLinkTermDict = None


    def setContentRaw(self, word, content, moddate = None, creadate = None):
        """
        Sets the content without applying any encoding,
        does not modify the cache information
        
        moddate -- Modification date to store or None for current
        creadate -- Creation date to store or None for current 
        
        Not part of public API!
        """
        ti = time()
        if moddate is None:
            moddate = ti

        # if not content: content = ""
        
        assert isinstance(content, Consts.BYTETYPES)

        try:
            if self.connWrap.execSqlQuerySingleItem("select word from "+\
                    "wikiwords where word=?", (word,), None) is not None:
    
                # Word exists already
    #             self.connWrap.execSql("insert or replace into wikiwords"+\
    #                 "(word, content, modified) values (?,?,?)",
    #                 (word, sqlite.Binary(content), moddate))
                self.connWrap.execSql("update wikiwords set "
                    "content=?, modified=? where word=?",
                    (sqlite.Binary(content), moddate, word))
            else:
                if creadate is None:
                    creadate = ti
    
                # Word does not exist -> record creation date
                self.connWrap.execSql("insert or replace into wikiwords"
                    "(word, content, modified, created) "
                    "values (?,?,?,?)",
                    (word, sqlite.Binary(content), moddate, creadate))
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
            self.connWrap.execSql("update wikiwords set word = ? "
                    "where word = ?", (newWord, oldWord))
    
            self.cachedWikiPageLinkTermDict = None
        except (IOError, OSError, sqlite.Error) as e:
            traceback.print_exc()
            raise DbWriteAccessError(e)


    def _deleteContent(self, word):
        try:
            self.connWrap.execSql("delete from wikiwords where word = ?", (word,))
            self.cachedWikiPageLinkTermDict = None
        except (IOError, OSError, sqlite.Error) as e:
            traceback.print_exc()
            raise DbWriteAccessError(e)


    def validateFileSignatureForWikiPageName(self, word, setMetaDataDirty=False, 
            refresh=False):
        """
        Returns True if file signature stored in DB matches the file
        containing the content, False otherwise.
        For compact_sqlite it always returns True.
        """
        return True


    def refreshFileSignatureForWikiPageName(self, word):
        """
        Sets file signature to match current file.
        For compact_sqlite it does nothing.
        """
        pass



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


        sql = "select relation%s from wikirelations where word = ?" % addFields

        if not selfreference:
            sql += " and relation != word"

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


        try:
            if len(withFields) > 0:
                return self.connWrap.execSqlQuery(sql, (wikiWord,))
            else:
                return self.connWrap.execSqlQuerySingleColumn(sql, (wikiWord,))
        except (IOError, OSError, sqlite.Error) as e:
            traceback.print_exc()
            raise DbReadAccessError(e)



    # ---------- Listing/Searching wiki words (see also "alias handling", "searching pages")----------

    def refreshWikiPageLinkTerms(self):
        """
        Refreshes the internal list of defined pages which
        may be different from the list of pages for which
        content is available (not possible for compact database).
        The function tries to conserve additional informations
        (creation/modif. date) if possible.
        
        It is mainly called during rebuilding of the wiki 
        so it must not rely on the presence of other cache
        information (e.g. relations).

        The self.cachedWikiPageLinkTermDict is invalidated.
        """
        self.cachedWikiPageLinkTermDict = None

    # ---------- Attribute cache handling ----------

    # ---------- Alias handling ----------

    # ---------- Todo cache handling ----------

    # ---------- Wikiword matchterm cache handling ----------

    # ---------- Data block handling ----------

    def getDataBlockUnifNamesStartingWith(self, startingWith):
        """
        Return all unified names starting with startingWith (case sensitive)
        """
        try:
            return self.connWrap.execSqlQuerySingleColumn(
                    "select distinct(unifiedname) from datablocks where "
                    "unifiedname glob (? || '*')",
                    (sqlite.escapeForGlob(startingWith),))
        except (IOError, OSError, sqlite.Error) as e:
            traceback.print_exc()
            raise DbReadAccessError(e)


    def retrieveDataBlock(self, unifName, default=""):
        """
        Retrieve data block as binary string.
        """
        try:
            # TODO exception if not present?
            return self.connWrap.execSqlQuerySingleItem(
                    "select data from datablocks where unifiedname = ?",
                    (unifName,))

        except (IOError, OSError, sqlite.Error) as e:
            traceback.print_exc()
            raise DbReadAccessError(e)


    def retrieveDataBlockAsText(self, unifName, default=""):
        """
        Retrieve data block as unicode string (assuming it was encoded properly)
        and with normalized line-ending (Un*x-style).
        """
        datablock = self.retrieveDataBlock(unifName)
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
            storeHint is ignored in compact_sqlite
        """
        
        if isinstance(newdata, str):
            newdata = StringOps.BOM_UTF8 + newdata.encode("utf-8",
                    "surrogateescape")

        try:
            self.connWrap.execSql("insert or replace into "
                    "datablocks(unifiedname, data) values (?, ?)",
                    (unifName, sqlite.Binary(newdata)))
        except (IOError, OSError, sqlite.Error) as e:
            traceback.print_exc()
            raise DbWriteAccessError(e)


    def guessDataBlockStoreHint(self, unifName):
        """
        Return a guess of the store hint used to store the block last time.
        Returns one of the DATABLOCK_STOREHINT_* constants from Consts.py.
        The function is allowed to return the wrong value (therefore a guess)
        For compact_sqlite it always returns Consts.DATABLOCK_STOREHINT_INTERN.
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

        return None


    def deleteDataBlock(self, unifName):
        """
        Delete data block with the associated unified name. If the unified name
        is not in database, nothing happens.
        """
        try:
            self.connWrap.execSql(
                    "delete from datablocks where unifiedname = ?", (unifName,))
        except (IOError, OSError, sqlite.Error) as e:
            traceback.print_exc()
            raise DbWriteAccessError(e)


    # ---------- Searching pages ----------

    def search(self, sarOp, exclusionSet):
        """
        Search all wiki pages using the SearchAndReplaceOperation sarOp and
        return set of all page names that match the search criteria.
        sarOp.beginWikiSearch() must be called before calling this function,
        sarOp.endWikiSearch() must be called after calling this function.
        This version uses sqlite user-defined functions.
        
        exclusionSet -- set of wiki words for which their pages shouldn't be
        searched here and which must not be part of the result set
        """

        if sarOp.isTextNeededForTest():
            try:
                result = self.connWrap.execSqlQuerySingleColumn(
                        "select word from wikiwords where "
                        "testMatch(word, content, ?)",
                        (sqlite.addTransObject(sarOp),))
            except (IOError, OSError, sqlite.Error) as e:
                traceback.print_exc()
                raise DbReadAccessError(e)
            finally:
                sqlite.delTransObject(sarOp)
    
            result = set(result)
            result -= exclusionSet
    
            return result
        else:
            try:
                result = self.connWrap.execSqlQuerySingleColumn(
                        "select word from wikiwords where "
                        "testMatch(word, '', ?)",
                        (sqlite.addTransObject(sarOp),))
            except (IOError, OSError, sqlite.Error) as e:
                traceback.print_exc()
                raise DbReadAccessError(e)
            finally:
                sqlite.delTransObject(sarOp)
    
            result = set(result)
            result -= exclusionSet
    
            return result


# explain select distinct type from wikiwordmatchterms where type & 2
# explain select type from (select distinct type from wikiwordmatchterms) where type & 2
# explain select type, type & 2 from (select distinct type from wikiwordmatchterms where type > 1) 


    # ---------- Miscellaneous ----------

    _CAPABILITIES = {
        "rebuild": 1,
        "compactify": 1,     # = sqlite vacuum
        "plain text import": 1,
        "recovery mode": 1,
#         "asynchronous commit":1  # Commit can be done in separate thread, but
#                 # calling any other function during running commit is not allowed
        }


        # TODO drop and recreate tables and indices!
    def clearCacheTables(self):
        """
        Clear all tables in the database which contain non-essential
        (cache) information as well as other cache information.
        Needed before rebuilding the whole wiki
        """
        DbStructure.recreateCacheTables(self.connWrap)
        self.connWrap.syncCommit()

        self.cachedWikiPageLinkTermDict = None
        self.cachedGlobalAttrs = None


    def testWrite(self):
        """
        Test if writing to database is possible. Throws a DbWriteAccessError
        if writing failed.
        TODO !
        """
        pass



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

            indexes = self.connWrap.execSqlQuerySingleColumn(
                    "select name from sqlite_master where type='index'")
            indexes = [s.upper() for s in indexes]

            if not "WIKIWORDCONTENT_PKEY" in indexes:
                # Maybe we have multiple pages with the same name in the database
                
                # Copy valid creation date to all pages
                self.connWrap.execSql("update wikiwords set "
                        "created=(select max(created) from wikiwords as "
                        "inner where inner.word=wikiwords.word)")
    
                # Delete all but the newest page
                self.connWrap.execSql("delete from wikiwords where "
                        "ROWID not in (select max(ROWID) from wikiwords as "
                        "outer where modified=(select max(modified) from "
                        "wikiwords as inner where inner.word=outer.word) "
                        "group by outer.word)")
    
                DbStructure.rebuildIndices(self.connWrap)
        except (IOError, OSError, sqlite.Error) as e:
            traceback.print_exc()
            raise DbWriteAccessError(e)


       # TODO: More repair operations


#         # recreate word caches
#         self.cachedWikiPageLinkTermDict = {}
#         for word in self.getAllDefinedWikiPageNames():
#             self.cachedWikiPageLinkTermDict[word] = 1
# 
#         # cache aliases
#         aliases = self.getAllAliases()
#         for alias in aliases:
#             self.cachedWikiPageLinkTermDict[alias] = 2


#         finally:            
#             progresshandler.close()


    # TODO: Better error checking
    # TODO: Process 2.0-named files
    def copyWikiFilesToDatabase(self):
        """
        Helper to transfer wiki files into database for migrating from
        original WikidPad to specialized databases.

        Must be implemented if checkCapability returns a version number
        for "plain text import".
        """
        self.connWrap.syncCommit()

        fnames = glob.glob(join(self.dataDir, '*.wiki'))
        for fn in fnames:
            word = basename(fn).replace('.wiki', '')

            content = fileContentToUnicode(StringOps.loadEntireTxtFile(fn))
            langHelper = GetApp().createWikiLanguageHelper(
                    self.wikiDocument.getWikiDefaultWikiLanguage())

            if not langHelper.checkForInvalidWikiWord(word, self.wikiDocument):
                self.setContent(word, content, moddate=os.stat(fn).st_mtime)

        self.connWrap.commit()


def listAvailableWikiDataHandlers():
    """
    Returns a list with the names of available handlers from this module.
    Each item is a tuple (<internal name>, <descriptive name>)
    """
    if sqlite is not None:
        return [("compact_sqlite", "Compact Sqlite")]
    else:
        return []


def getWikiDataHandler(name):
    """
    Returns a factory function (or class) for an appropriate
    WikiData object and a createWikiDB function or (None, None)
    if name is unknown
    """
    if name == "compact_sqlite":
        return WikiData, createWikiDB
    
    return (None, None)
