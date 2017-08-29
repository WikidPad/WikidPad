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
    from . import DbStructure
    from .DbStructure import createWikiDB, WikiDBExistsException
except:
    import ExceptionLogger
    ExceptionLogger.logOptionalComponentException(
            "Initialize external sqlite for original_sqlite/WikiData.py")
    sqlite = None
# finally:
#     pass

from pwiki.StringOps import getBinCompactForDiff, applyBinCompact, longPathEnc, \
        longPathDec, binCompactToCompact, fileContentToUnicode, utf8Enc, utf8Dec, \
        uniWithNone, loadEntireTxtFile, Conjunction, lineendToInternal
from pwiki.StringOps import loadEntireFile, writeEntireFile, \
        iterCompatibleFilename, getFileSignatureBlock, guessBaseNameByFilename, \
        createRandomString, pathDec

from ..BaseWikiData import BasicWikiData, SqliteWikiData, FileWikiData

import Consts

class WikiData(FileWikiData, SqliteWikiData, BasicWikiData):
    "Interface to wiki data."
    def __init__(self, wikiDocument, dataDir, tempDir, app=None):
        self.dbType = "original_sqlite"

        self.wikiDocument = wikiDocument
        self.dataDir = dataDir
        self.cachedWikiPageLinkTermDict = None
        self.cachedWikiPageLinkTermDictLower = None

        dbPath = self.getDbFilenames()[0]
                
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
        
        if app is not None:
            self.initSqliteIfRequired(app)

        DbStructure.registerSqliteFunctions(self.connWrap)

        try:
            self.pagefileSuffix = self.wikiDocument.getWikiConfig().get("main",
                    "db_pagefile_suffix", ".wiki")
        except (IOError, OSError) as e:
            traceback.print_exc()
            raise DbReadAccessError(e)

        self.caseInsensitiveWikiWords = self.wikiDocument.getWikiConfig().\
                getboolean("main", "caseInsensitiveWikiWords", False)


    def getDbFilenames(self):
        """Return a list of database filenames"""
        dbPath = self.wikiDocument.getWikiConfig().get("wiki_db", 
                "db_filename", u"").strip()
                
        if (dbPath == u""):
            dbPath = u"wikiovw.sli"

        return [dbPath]


    def checkDatabaseFormat(self):
        return DbStructure.checkDatabaseFormat(self.connWrap)


    def connect(self):
        formatcheck, formatmsg = self.checkDatabaseFormat()

        if formatcheck == 2:
            # Unknown format
            raise WikiDataException(formatmsg)

        # Update database from previous versions if necessary
        if formatcheck == 1:
            # Offer the chance to backup a database
            self.backupDatabase()

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

        try:
            # Set marker for database type
            self.wikiDocument.getWikiConfig().set("main", "wiki_database_type",
                    "original_sqlite")
        except (IOError, OSError, sqlite.Error) as e:
            # Remember but continue
            lastException = DbWriteAccessError(e)

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




    # ---------- Miscellaneous ----------

    _CAPABILITIES = {
        "rebuild": 1,
        "compactify": 1,     # = sqlite vacuum
        "filePerPage": 1,   # Uses a single file per page
#         "versioning": 1,     # (old versioning)
#         "plain text import":1   # Is already plain text      
        }


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


    def getDbSettingsValue(self, key, default=None):
        return DbStructure.getSettingsValue(self.connWrap, key, default)


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
