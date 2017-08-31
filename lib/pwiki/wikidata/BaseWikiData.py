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

