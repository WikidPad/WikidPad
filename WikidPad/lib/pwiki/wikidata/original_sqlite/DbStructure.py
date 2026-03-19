"""
Module responsible for structural changes to the database
(creating/dropping tables), creation of new DBs and the transition from older
DB formats to the current one
"""


import codecs, types, threading, traceback

from os import mkdir, unlink, rename
from os.path import exists, join

import Consts
from pwiki.WikiExceptions import *
from pwiki.StringOps import mbcsDec, utf8Enc, utf8Dec, applyBinCompact, \
        removeBracketsFilename, pathEnc, getFileSignatureBlock, \
        iterCompatibleFilename
from pwiki.SearchAndReplace import SearchReplaceOperation

import pwiki.sqlite3api as sqlite




# Connection (and Cursor)-Wrapper to simplify some operations

class ConnectWrapBase:
    """
    Connection (and Cursor)-Wrapper to simplify some operations.
    Base class to versions with synchronous and asynchronous commit.
    """
    def __init__(self, connection):
        self.__dict__["dbConn"] = connection
        self.__dict__["dbCursor"] = connection.cursor()
     
#         self.__dict__["execute"] = self.dbCursor.execute
#         self.__dict__["executemany"] = self.dbCursor.executemany
#         self.__dict__["fetchone"] = self.dbCursor.fetchone
#         self.__dict__["fetchall"] = self.dbCursor.fetchall

   
    def __setattr__(self, attr, value):
        setattr(self.dbCursor, attr, value)

    def __getattr__(self,  attr):
        return getattr(self.dbCursor, attr)


    # The following are mainly the versions for synchronized commit
    # For async commit they are wrapped by a lock

    def execSql(self, sql, params=None):
        "utility method, executes the sql"
        if params:
            self.dbCursor.execute(sql, params)
        else:
            self.dbCursor.execute(sql)


    def execSqlQuery(self, sql, params=None):
        "utility method, executes the sql, returns query result"
        if params:
            self.dbCursor.execute(sql, params, typeDetect=sqlite.TYPEDET_FIRST)
        else:
            self.dbCursor.execute(sql, typeDetect=sqlite.TYPEDET_FIRST)

        return self.dbCursor.fetchall()


#     def execSqlQueryIter(self, sql, params=None):
#         """
#         utility method, executes the sql, returns an iterator
#         over the query results
#         """
#         ## print "execSqlQuery sql", sql, repr(params)
#         if params:
#             self.dbCursor.execute(sql, params, typeDetect=sqlite.TYPEDET_FIRST)
#         else:
#             self.dbCursor.execute(sql, typeDetect=sqlite.TYPEDET_FIRST)
# 
#         return iter(self.dbCursor)


    def execSqlQuerySingleColumn(self, sql, params=None):
        "utility method, executes the sql, returns query result"
        data = self.execSqlQuery(sql, params)
        return [row[0] for row in data]
        

    def execSqlQuerySingleItem(self, sql, params=None, default=None):
        """
        Executes a query to retrieve at most one row with
        one column and returns result. If query results
        to 0 rows, default is returned (defaults to None)
        """
        if params:
            self.dbCursor.execute(sql, params)
        else:
            self.dbCursor.execute(sql)

        row = self.fetchone()
        if row is None:
            return default
            
        return row[0]

        
    def execSqlNoError(self, sql):
        """
        Ignore sqlite errors on execution
        """
        try:
            self.dbCursor.execute(sql)
        except sqlite.Error:
            pass


    def getLastRowid(self):
        return self.dbCursor.lastrowid


    def closeCursor(self):
        if self.dbCursor:
            self.dbCursor.close()
            self.dbCursor = None

    def close(self):
        """
        Close cursor and connection
        """
        if self.dbConn:
            self.closeCursor()
            self.dbConn.close()
            self.dbConn = None


    def __del__(self):
        """
        Only the implicit generated cursor is closed automatically
        on deletion, the connection is not.
        """
        self.closeCursor()
     
    def getConnection(self):
        """
        Return wrapped DB-API connection
        """
        return self.dbConn
        
    def getCursor(self):
        return self.dbCursor



class ConnectWrapSyncCommit(ConnectWrapBase):
    """
    Connection wrapper for synchronous commit
    """
    def __init__(self, connection):
        ConnectWrapBase.__init__(self, connection)
        
        # To make access a bit faster
        self.__dict__["commit"] = self.dbConn.commit
        self.__dict__["syncCommit"] = self.dbConn.commit
        self.__dict__["rollback"] = self.dbConn.rollback


    # Other functions are already defined by ConnectWrapBase



class ConnectWrapAsyncCommit(ConnectWrapBase):
    """
    Connection wrapper for asynchronous commit (experimental)
    """
    def __init__(self, connection):
        ConnectWrapBase.__init__(self, connection)
        
        self.__dict__["accessLock"] = threading.RLock()
        self.__dict__["commitTimer"] = None
        self.__dict__["commitNeeded"] = False


    def commit(self):
        self.accessLock.acquire()
        try:
            if not self.commitNeeded:
                return
            if self.commitTimer is not None and self.commitTimer.is_alive():
                return
            t = threading.Timer(0.6, self._timerCommit)
            self.commitTimer = t
            t.start()
        finally:
            self.accessLock.release()


    def _timerCommit(self):
        """
        Called by timer to commit.
        """
        self.accessLock.acquire()
        try:    
            if not self.commitNeeded:
                return
            self.dbConn.commit()
            self.commitNeeded = False
        finally:
            self.accessLock.release()
        

    def syncCommit(self):
        """
        Execute commit immediately and synchronous.
        """
        self.accessLock.acquire()
        try:
            if self.commitTimer is not None and self.commitTimer.is_alive():
                self.commitTimer.cancel()
            self.dbConn.commit()
            self.commitNeeded = False
        finally:
            self.accessLock.release()


    def rollback(self):
        self.accessLock.acquire()
        try:    
            if self.commitTimer is not None and self.commitTimer.is_alive():
                self.commitTimer.cancel()
            self.dbConn.rollback()
            self.commitNeeded = False
        finally:
            self.accessLock.release()


    def _commitIfPending(self):
        """
        Execute commit synchronously if timer currently runs.
        This function is not secured by a lock as it is only called
        by other functions.
        """
        if self.commitTimer is not None and self.commitTimer.is_alive():
            self.commitTimer.cancel()

            if not self.commitNeeded:
                return
            self.dbConn.commit()
            self.commitNeeded = False


    def execSql(self, sql, params=None):
        "utility method, executes the sql"
        self.accessLock.acquire()
        try:
            # Commit first before executing something that changes database
            self._commitIfPending()
            self.commitNeeded = True
            return ConnectWrapBase.execSql(self, sql, params)
        finally:
            self.accessLock.release()

    def execSqlQuery(self, sql, params=None):
        "utility method, executes the sql, returns query result"
        self.accessLock.acquire()
        try:
            return ConnectWrapBase.execSqlQuery(self, sql, params)
        finally:
            self.accessLock.release()


#     def execSqlQueryIter(self, sql, params=None):
#         """
#         utility method, executes the sql, returns an iterator
#         over the query results
#         """
#         ## print "execSqlQuery sql", sql, repr(params)
#         if params:
#             self.dbCursor.execute(sql, params, typeDetect=sqlite.TYPEDET_FIRST)
#         else:
#             self.dbCursor.execute(sql, typeDetect=sqlite.TYPEDET_FIRST)
# 
#         return iter(self.dbCursor)


    def execSqlQuerySingleColumn(self, sql, params=None):
        "utility method, executes the sql, returns query result"
        self.accessLock.acquire()
        try:
            return ConnectWrapBase.execSqlQuerySingleColumn(self, sql, params)
        finally:
            self.accessLock.release()
        

    def execSqlQuerySingleItem(self, sql, params=None, default=None):
        """
        Executes a query to retrieve at most one row with
        one column and returns result. If query results
        to 0 rows, default is returned (defaults to None)
        """
        self.accessLock.acquire()
        try:
            return ConnectWrapBase.execSqlQuerySingleItem(self, sql, params,
                    default)
        finally:
            self.accessLock.release()

        
    def execSqlNoError(self, sql):
        """
        Ignore sqlite errors on execution
        """
        self.accessLock.acquire()
        try:
            # Commit first before executing something that changes database
            self._commitIfPending()
            self.commitNeeded = True
            return ConnectWrapBase.execSqlNoError(self, sql)
        finally:
            self.accessLock.release()


    def getLastRowid(self):
        self.accessLock.acquire()
        try:
            return ConnectWrapBase.getLastRowid(self)
        finally:
            self.accessLock.release()

        
    def closeCursor(self):
        self.accessLock.acquire()
        try:
            # Commit first before executing something that changes database
            self._commitIfPending()
            return ConnectWrapBase.closeCursor(self)
        finally:
            self.accessLock.release()


    def close(self):
        """
        Close cursor and connection
        """
        self.accessLock.acquire()
        try:
            # Commit first before executing something that changes database
            self._commitIfPending()
            ConnectWrapBase.close(self)
        finally:
            self.accessLock.release()




VERSION_DB = 3
VERSION_WRITECOMPAT = 3
VERSION_READCOMPAT = 3


# Helper for the following definitions
class t:
    pass
    
t.r = "real not null default 0.0"
t.i = "integer not null default 0"
t.pi = "integer primary key not null"
t.imo = "integer not null default -1"
t.t = "text not null default ''"
t.pt = "text primary key not null"
t.b = "blob not null default x''"



# Dictionary of definitions for all tables (as for changeTableSchema)
# Some of the tables are optional and don't have to be in the DB

TABLE_DEFINITIONS = {
    "wikiwords": (     # Essential
        ("word", t.t),
        ("created", t.r),
        ("modified", t.r),
        ("visited", t.r),
        ("filepath", t.t),
        ("filenamelowercase", t.t),
        ("filesignature", t.b),
        ("readonly", t.i),
        ("metadataprocessed", t.i),
        ("presentationdatablock", t.b),
        ),


    "wikirelations": (     # Cache
        ("word", t.t),
        ("relation", t.t),
        ("firstcharpos", t.imo),  # Position of the link from word to relation in chars
        ("charlength", t.imo)  # Length of the link
        ),
    
    
    "wikiwordattrs": (     # Cache, previous name: "wikiwordprops"
        ("word", t.t),
        ("key", t.t),
        ("value", t.t),
        ("firstcharpos", t.imo),  # Position of the attribute in page in chars
        ("charlength", t.imo)  # Length of the attribute
        ),


    "todos_PRE2_1alpha01": (     # Obsolete
        ("word", t.t),
        ("todo", t.t),
        ("firstcharpos", t.imo),  # Position of the todo in page in chars
        ),


    "todos": (     # Cache
        ("word", t.t),
        ("key", t.t),
        ("value", t.t),
        ("firstcharpos", t.imo),  # Position of the todo in page in chars
        ("charlength", t.imo)  # Length of the todo
        ),

    
    "search_views": (     # Deleted since 2.0alpha1. For updating format only 
        ("title", t.pt),
        ("datablock", t.b)
        ),
    
    
    "settings": (     # Essential
        ("key", t.pt),    # !!! primary key?
        ("value", t.t)
        ),

    "wikiwordmatchterms": (
        ("matchterm", t.t),
        ("matchtermnormcase", t.t),
        ("type", t.i),
        ("word", t.t),
        ("firstcharpos", t.imo),  # Position of the target of the matchterm in page <word>
        ("charlength", t.imo)  # Length of the target
        ),


    "datablocks": (
        ("unifiedname", t.t),
        ("data", t.b)
        ),


    "datablocksexternal": (
        ("unifiedname", t.t),
        ("filepath", t.t),
        ("filenamelowercase", t.t),
        ("filesignature", t.b)
        )

    }


del t


MAIN_TABLES = (
    "wikiwords",
    "wikirelations",
    "wikiwordattrs",
    "todos",
#     "search_views",
    "settings",
    "wikiwordmatchterms",
    "datablocks",
    "datablocksexternal"
    )


def rebuildIndices(connwrap):
    """
    Delete and recreate all necessary indices of the database
    """
    connwrap.execSqlNoError("drop index wikiwordprops_word")
    connwrap.execSqlNoError("drop index wikiwordprops_keyvalue")

    connwrap.execSqlNoError("drop index wikiwords_pkey")
    connwrap.execSqlNoError("drop index wikiwords_wordnormcase")
    connwrap.execSqlNoError("drop index wikiwords_modified")
    connwrap.execSqlNoError("drop index wikiwords_created")
    connwrap.execSqlNoError("drop index wikiwordmatchterms_matchterm")
    connwrap.execSqlNoError("drop index wikiwordmatchterms_matchtermnormcase")
    connwrap.execSqlNoError("drop index wikirelations_pkey")
    connwrap.execSqlNoError("drop index wikirelations_word")
    connwrap.execSqlNoError("drop index wikirelations_relation")    
    connwrap.execSqlNoError("drop index wikiwordattrs_word")
    connwrap.execSqlNoError("drop index wikiwordattrs_keyvalue")
    connwrap.execSqlNoError("drop index datablocks_unifiedname")
    connwrap.execSqlNoError("drop index datablocksexternal_unifiedname")

    connwrap.execSqlNoError("create unique index wikiwords_pkey on wikiwords(word)")
    connwrap.execSqlNoError("create index wikiwords_modified on wikiwordcontent(modified)")
    connwrap.execSqlNoError("create index wikiwords_created on wikiwordcontent(created)")
    connwrap.execSqlNoError("create index wikiwordmatchterms_matchterm on wikiwordmatchterms(matchterm)")
    connwrap.execSqlNoError("create index wikiwordmatchterms_matchtermnormcase on wikiwordmatchterms(matchtermnormcase)")
    connwrap.execSqlNoError("create unique index wikirelations_pkey on wikirelations(word, relation)")
    connwrap.execSqlNoError("create index wikirelations_word on wikirelations(word)")
    connwrap.execSqlNoError("create index wikirelations_relation on wikirelations(relation)")
    connwrap.execSqlNoError("create index wikiwordattrs_word on wikiwordattrs(word)")
    connwrap.execSqlNoError("create index wikiwordattrs_keyvalue on wikiwordattrs(key, value)")
    connwrap.execSqlNoError("create unique index datablocks_unifiedname on datablocks(unifiedname)")
    connwrap.execSqlNoError("create unique index datablocksexternal_unifiedname on datablocksexternal(unifiedname)")



def recreateCacheTables(connwrap):
    """
    Delete and create again all tables with cache information and
    associated indices
    """
    CACHE_TABLES = ("wikirelations", "wikiwordattrs", "todos",
            "wikiwordmatchterms")
    
    for tn in CACHE_TABLES:
        connwrap.execSqlNoError("drop table %s" % tn)

    for tn in CACHE_TABLES:
        changeTableSchema(connwrap, tn, TABLE_DEFINITIONS[tn])

    rebuildIndices(connwrap)

#     connwrap.execSql("create unique index wikirelations_pkey on wikirelations(word, relation)")
#     connwrap.execSql("create index wikirelations_word on wikirelations(word)")
#     connwrap.execSql("create index wikirelations_relation on wikirelations(relation)")
#     connwrap.execSql("create index wikiwordprops_word on wikiwordprops(word)")



####################################################
# module level functions
####################################################


def changeTableSchema(connwrap, tablename, schema, forcechange=False):
    """
    Creates or changes table, but tries to preserve the data of columns with the
    same name in old and new schema. If the set of columnn names of old and new
    schema are identical and forcechange is False, nothing is done.
    Returns true if old table was replaced by a new one.
    The commit-state of the connection is not modified

    Indices may need separate recreation.
    
    connwrap -- a ConnectWrap object
    schema -- sequence of tuples (<col name>, <col definition>)
        with <col definition>: type and constraints of the column
    forcechange -- Create a new table in any case
    """
    """
    schema -- sequence of tuples (<col name>, <col definition>, <col std value>)
        with <col definition>: type and constraints of the column
            <col std value>: standard value (as sql string) to insert if column was added
                to schema
    """

    # Build the sql command to create the table with new schema (needed later)
    sqlcreate = "create table %s (" % tablename
    sqlcreate += ", ".join(["%s %s" % sc for sc in schema])
    sqlcreate += ")"
    

    # Test if table already exists

    connwrap.execSql("select name from sqlite_master where type='table' "+\
            "and name='%s'" % tablename)

    tn = connwrap.fetchone()

    if tn is None:
        # Does not exist, so simply create
        connwrap.execSql(sqlcreate)
        return True


    # Table exists, so retrieve list of columns
    
    # A pragma statement would trigger a commit but we don't want this
    oldAc = connwrap.getConnection().getAutoCommit()
    # If autoCommit is on, no automatic begin or commit statements will
    # be created by the DB-interface (this sounds contradictional, but is true
    # because sqlite itself is then responsible for the automatic commit)
    
    # Without silent=True, the command would create a commit here
    connwrap.getConnection().setAutoCommit(True, silent=True)

    # This statement would automatically issue a commit if auto commit is off
    connwrap.execSql("pragma table_info(%s)" % tablename)
    oldcolumns = [r[1] for r in connwrap.fetchall()]
    
    # Set autoCommit state back
    connwrap.getConnection().setAutoCommit(oldAc, silent=True)
    

    # Which columns have old and new schema in common?    
    intersect = []
    for n, d in schema:
        if n in oldcolumns:
            intersect.append(n)

    recreate = False

    if forcechange:
        recreate = True
    elif (len(oldcolumns) != len(schema)) or (len(intersect) != len(oldcolumns)):
        recreate = True

    if not recreate:
        return False  # Nothing to do, same column set as before

    if len(intersect) > 0:
        intersect = ", ".join(intersect)
        # Common columns -> Copy to temporary table
        connwrap.execSql("create temp table tmptable as select %s from %s" % (intersect, tablename))
        connwrap.execSql("drop table %s" % tablename)
        connwrap.execSql(sqlcreate)
        connwrap.execSql("insert into %s(%s) select %s from tmptable" % (tablename, intersect, intersect))
        connwrap.execSql("drop table tmptable")
    else:
        # Nothing in common -> delete old, create new
        connwrap.execSql("drop table %s" % tablename)
        connwrap.execSql(sqlcreate)

    return True



def createWikiDB(wikiName, dataDir, overwrite=False, wikiDocument=None):
    """
    creates the initial db
    Warning: If overwrite is True, a previous file will be deleted!
    """
    
    if (wikiDocument is not None):
        dbPath = wikiDocument.getWikiConfig().get("wiki_db", "db_filename",
                    "").strip()
                    
        if (dbPath == ""):
            dbPath = "wikiovw.sli"
    else:
        dbPath = "wikiovw.sli"

    dbfile = join(dataDir, dbPath)
    if (not exists(pathEnc(dbfile)) or overwrite):
        if (not exists(pathEnc(dataDir))):
            mkdir(pathEnc(dataDir))
        else:
            if exists(pathEnc(dbfile)) and overwrite:
                unlink(pathEnc(dbfile))

        # create the database
        connwrap = ConnectWrapSyncCommit(sqlite.connect(dbfile))

        try:
            for tn in MAIN_TABLES:
                changeTableSchema(connwrap, tn, TABLE_DEFINITIONS[tn])
    
            connwrap.executemany("insert or replace into settings(key, value) "+
                        "values (?, ?)", (
                    ("formatver", str(VERSION_DB)),  # Version of database format the data was written
                    ("writecompatver", str(VERSION_WRITECOMPAT)),  # Lowest format version which is write compatible
                    ("readcompatver", str(VERSION_READCOMPAT)),  # Lowest format version which is read compatible
                    ("branchtag", "WikidPad")  # Tag of the WikidPad branch
#                     ("locale", "-") # Locale for cached wordnormcase column. '-': column invalid
                    )  )

            rebuildIndices(connwrap)
            connwrap.syncCommit()
            
        finally:
            # close the connection
            connwrap.close()

    else:
        raise WikiDBExistsException(
                _("database already exists at location: %s") % dataDir)


def mbcsToUtf8(s):
    return utf8Enc(mbcsDec(s)[0])[0]


def sqlite_utf8Normcase(context, values):
    """
    Sqlite user-defined function "utf8Normcase" to get the lowercase of a word
    encoded in UTF-8. The result is also encoded in UTF-8.
    """
    normalWord = utf8Dec(values[0].value_text(), "replace")[0].lower()
    context.result_text(utf8Enc(normalWord)[0])


# def sqlite_testMatch(context, values):
#     """
#     Sqlite user-defined function "testMatch" for WikiData.search()
#     method
#     """
#     nakedword = utf8Dec(values[0].value_blob(), "replace")[0]
#     fileContents = utf8Dec(values[1].value_blob(), "replace")[0]
#     sarOp = sqlite.getTransObject(values[2].value_int())
#     if sarOp.testWikiPage(nakedword, fileContents) == True:
#         context.result_int(1)
#     else:
#         context.result_null()





# Get the default text handling functions
bind_text = sqlite.def_bind_fctfinder(None, None, "")
column_text = sqlite.AUTO_COLUMN_CONVERTS[sqlite.SQLITE_TEXT]


column_utftext = column_text


def bind_mbcsutftext(stmt, parno, data):
    bind_text(stmt, parno, mbcsToUtf8(data))


def bind_utftext(stmt, parno, unicodedata):
    bind_text(stmt, parno, utf8Enc(unicodedata)[0])


def utf8_bind_fctfinder(stmt, parno, data):
    """
    Fctfinder for _SqliteStatement3 with support for utf8
    strings
    """
    if type(data) is str:
        return bind_mbcsutftext

    if type(data) is str:
        return bind_utftext
            
    return sqlite.def_bind_fctfinder(stmt, parno, data)

    

def utf8_column_fctfinder(stmt, col):
    """
    Fctfinder for _SqliteStatement3 with support for utf8
    strings
    """
    result = sqlite.def_column_fctfinder(stmt, col)
    if result != column_text:
        return result
        
    return column_utftext
    

def registerSqliteFunctions(connwrap):
    """
    Register necessary user-defined functions for a connection
    """
    connwrap.getConnection().createFunction("utf8Normcase", 1, sqlite_utf8Normcase)
#     connwrap.getConnection().createFunction("testMatch", 3, sqlite_testMatch)
#     connwrap.getConnection().createFunction("latin1ToUtf8", 1, sqlite_latin1ToUtf8)
#     connwrap.getConnection().createFunction("utf8ToLatin1", 1, sqlite_utf8ToLatin1)
#     connwrap.getConnection().createFunction("mbcsToUtf8", 1, sqlite_mbcsToUtf8)
#     connwrap.getConnection().createFunction("utf8ToMbcs", 1, sqlite_utf8ToMbcs)


def registerUtf8Support(connwrap):
    connwrap.getConnection().setColumnFctFinder(utf8_column_fctfinder)
    connwrap.getConnection().setBindFctFinder(utf8_bind_fctfinder)



def getSettingsValue(connwrap, key, default=None):
    """
    Retrieve a value from the settings table
    default -- Default value to return if key was not found
    """
    return connwrap.execSqlQuerySingleItem("select value from settings where key=?",
            (key,), default)


def getSettingsInt(connwrap, key, default=None):
    """
    Retrieve an integer value from the settings table.
    default -- Default value to return if key was not found
    """
    return int(connwrap.execSqlQuerySingleItem("select value from settings where key=?",
            (key,), default))




def checkDatabaseFormat(connwrap):
    """
    Check the database format.
    Returns: 0: Up to date,  1: Update needed,  2: Unknown format, update not possible
    """
    
#     indices = connwrap.execSqlQuerySingleColumn(
#             "select name from sqlite_master where type='index'")
#     tables = connwrap.execSqlQuerySingleColumn(
#             "select name from sqlite_master where type='table'")
# 
#     indices = map(string.upper, indices)
#     tables = map(string.upper, tables)

    if getSettingsValue(connwrap, "branchtag") != "WikidPad":
        return 2, _("Database has unknown format branchtag='%s'") \
                % getSettingsValue(connwrap, "branchtag")

    formatver = getSettingsInt(connwrap, "formatver")
    writecompatver = getSettingsInt(connwrap, "writecompatver")

    if writecompatver > VERSION_WRITECOMPAT:
        # TODO: Check compatibility
        
        return 2, _("Database has unknown format version='%i'") \
                % formatver
                
    if formatver < VERSION_DB:
        return 1, _("Update needed, current format version='%i'") \
                % formatver

    return 0, _("Database format is up to date")


def updateDatabase(connwrap, dataDir, pagefileSuffix):
    """
    Update a database from an older version to current (checkDatabaseFormat()
    should have returned 1 before calling this function)
    """
    connwrap.syncCommit()
    
    # Always remember that there is no automatic unicode<->utf-8 conversion
    # during this function!

    formatver = getSettingsInt(connwrap, "formatver")

    if formatver == 0:
        # Insert in table wikiwords column wordnormcase
        changeTableSchema(connwrap, "wikiwords", 
                TABLE_DEFINITIONS["wikiwords"])

        formatver = 1

    # --- WikiPad 1.8beta1 reached (formatver=1, writecompatver=1,
    #         readcompatver=1) ---


    if formatver == 1:
        # Update "wikiwords" schema and create new tables
        for tn in ("wikiwords", "wikiwordmatchterms", "datablocks",
                "datablocksexternal"):
            changeTableSchema(connwrap, tn, TABLE_DEFINITIONS[tn])

        # Transfer "search_views" data to "datablocks" table
        searches = connwrap.execSqlQuery(
                "select title, datablock from search_views")

        for title, data in searches:
            connwrap.execSql(
                "insert into datablocks(unifiedname, data) "+\
                "values (?, ?)", ("savedsearch/" + title, sqlite.Binary(data)))

        connwrap.execSql("drop table search_views")

        allWords = connwrap.execSqlQuerySingleColumn("select word from wikiwords")

        # Divide into functional and wiki pages
        wikiWords = []
        funcWords = []
        for w in allWords:
            w = w.decode("utf-8")
            if w.startswith('['):
                funcWords.append(w)
            else:
                wikiWords.append(w)

        # Fill the new fields in table "wikiwords"
        for wikiWord in wikiWords:
            filename = wikiWord + pagefileSuffix
            fullPath = join(dataDir, filename)
            try:
                # We don't use coarsening here for the FSB because a different
                # coarsening setting can't exist for the old wiki format
                filesig = getFileSignatureBlock(fullPath)
            except (IOError, WindowsError):
                traceback.print_exc()
                continue
            
            connwrap.execSql("update wikiwords set filepath = ?, "
                    "filenamelowercase = ?, filesignature = ? "
                    "where word = ?", (filename.encode("utf-8"),
                    filename.lower().encode("utf-8"), sqlite.Binary(filesig),
                    wikiWord.encode("utf-8")))

        # Move functional pages to new table "datablocksexternal" and rename them
        for funcWord in funcWords:
            if funcWord not in ("[TextBlocks]", "[PWL]", "[CCBlacklist]"):
                continue # Error ?!
            
            unifName = "wiki/" + funcWord[1:-1]
            fullPath = join(dataDir, funcWord + pagefileSuffix)
            
            icf = iterCompatibleFilename(unifName, ".data")
            
            for i in range(10):  # Actual "while True", but that's too dangerous
                newFilename = next(icf)
                newPath = join(dataDir, newFilename)

                if exists(pathEnc(newPath)):
                    # A file with the designated new name of fn already exists
                    # -> do nothing
                    continue

                try:
                    rename(pathEnc(fullPath), pathEnc(newPath))
                    # We don't use coarsening here for the FSB because a different
                    # coarsening setting can't exist for the old wiki format
                    connwrap.execSql(
                        "insert into datablocksexternal(unifiedname, filepath, "
                        "filenamelowercase, filesignature) values (?, ?, ?, ?)",
                        (unifName.encode("utf-8"), newFilename.encode("utf-8"),
                            newFilename.lower().encode("utf-8"),
                            sqlite.Binary(getFileSignatureBlock(newPath))))
                    connwrap.execSql("delete from wikiwords where word = ?",
                            (funcWord.encode("utf-8"),))
                    break
                except (IOError, OSError):
                    traceback.print_exc()
                    continue

        formatver = 2
        
    # --- WikiPad 2.0alpha1 reached (formatver=2, writecompatver=2,
    #         readcompatver=2) ---
    
    if formatver == 2:
        # Recreate table "todos"
        connwrap.execSql("drop table todos;")
        changeTableSchema(connwrap, "todos", TABLE_DEFINITIONS["todos"])
        connwrap.execSql("update todos set firstcharpos=-1;")

        # Rename table "wikiwordprops" to "wikiwordattrs"
        changeTableSchema(connwrap, "wikiwordattrs", TABLE_DEFINITIONS["wikiwordattrs"])
        connwrap.execSql("insert into wikiwordattrs(word, key, value, "
                "firstcharpos, charlength) select word, key, value, "
                "firstcharpos, -1 from wikiwordprops;")
        connwrap.execSql("drop table wikiwordprops;")

        for tn in ("wikirelations", "wikiwordmatchterms"):
            changeTableSchema(connwrap, tn, TABLE_DEFINITIONS[tn])
            connwrap.execSql("update %s set firstcharpos=-1;" % tn)

        # Mark all wikiwords to need a rebuild
        connwrap.execSql("update wikiwords set metadataprocessed=0;")

        formatver = 3

    # --- WikiPad 2.1alpha1 reached (formatver=3, writecompatver=3,
    #         readcompatver=3) ---


    connwrap.executemany("insert or replace into settings(key, value) "+
                "values (?, ?)", (
            ("formatver", str(VERSION_DB)),  # Version of database format the data was written
            ("writecompatver", str(VERSION_WRITECOMPAT)),  # Lowest format version which is write compatible
            ("readcompatver", str(VERSION_READCOMPAT)),  # Lowest format version which is read compatible
            ("branchtag", "WikidPad")  # Tag of the WikidPad branch
            )  )

    rebuildIndices(connwrap)

    connwrap.syncCommit()



def updateDatabase2(connwrap):
    """
    Second update function. Called even when database version is current.
    Performs further updates
    """
    try:
        # Write which format version at last wrote to database
        connwrap.execSql("insert or replace into settings(key, value) "
                "values ('lastwritever', '"+str(VERSION_DB)+"')")

        # Write which program version at last wrote to database
        connwrap.execSql("insert or replace into settings(key, value) "
                "values ('lastwriteprogver.branchtag', '"+Consts.VERSION_TUPLE[0]+"')")
        connwrap.execSql("insert or replace into settings(key, value) "
                "values ('lastwriteprogver.major', '"+str(Consts.VERSION_TUPLE[1])+"')")
        connwrap.execSql("insert or replace into settings(key, value) "
                "values ('lastwriteprogver.minor', '"+str(Consts.VERSION_TUPLE[2])+"')")
        connwrap.execSql("insert or replace into settings(key, value) "
                "values ('lastwriteprogver.sub', '"+str(Consts.VERSION_TUPLE[3])+"')")
        connwrap.execSql("insert or replace into settings(key, value) "
                "values ('lastwriteprogver.patch', '"+str(Consts.VERSION_TUPLE[4])+"')")
    except sqlite.ReadOnlyDbError:
        pass



"""
Schema changes in WikidPad:

+++ Initial 1.7beta1 (formatver=0):

    "wikiwords": (     # Essential
        ("word", t.t),
        ("created", t.t),
        ("modified", t.t)
        ),
    
    
    "wikirelations": (     # Cache
        ("word", t.t),
        ("relation", t.t),
        ("firstcharpos", t.imo)  # Position of the link from word to relation in chars
        ),
    
    
    "wikiwordprops": (     # Cache
        ("word", t.t),
        ("key", t.t),
        ("value", t.t),
        ("firstcharpos", t.imo)  # Position of the property in page in chars
        ),
    
    
    "todos": (     # Cache
        ("word", t.t),
        ("todo", t.t),
        ("firstcharpos", t.imo)  # Position of the todo in page in chars
        ),
        
    
    "search_views": (     # Essential
##        ("id", t.pi),   # ??????
        ("title", t.pt),
        ("datablock", t.b)
        ),
    
    
    "settings": (     # Essential
        ("key", t.pt),    # !!! primary key?
        ("value", t.t)
        )


++ 1.7beta1 to 1.8beta1 (formatver=1):

Table "wikiwords" changed to:
        "wikiwords": (
            ("word", t.t),
            ("created", t.t),
            ("modified", t.t),
            ("presentationdatablock", t.b),
            ("wordnormcase", t.t)
            )


Added column "presentationdatablock" contains byte string describing how to present
a particular page (window scroll and cursor position). Its content is
en/decoded by the WikiDocument.

Added column "wordnormcase" contains byte string returned by the normCase method
of a Collator object (see "Localization.py"). The column's content should 
be recreated at a rebuild.

Added "locale" key in "settings" table. This is the name of the locale used to
create the "wordnormcase" column content. A "-" means the column contains
invalid data.


++ 1.9final to 2.0alpha1 (formatver=2):
    
    Table "search_views" removed (taken over by "datablocks")
    
    Table "wikiwords" modified:
        "wordnormcase" removed (taken over by table "wikiwordmatchterms")
        "visited" added, float, time as returned by time.time()
        "metadataprocessed" added, int, state how far meta-data like attributes
            or todos are processed.
            0: Processing needed yet
            1: Processed. Meta-data in db is in sync with page text.

        "filepath" added, unistring. Name of the wiki file containing the
            content (not applicable for compact sqlite db). The path is relative
            to "data" directory, so it shouldn't contain more than the filename
            under most circumstances
        "filenamelowercase" added, unistring. Lower case of filename in filepath
            (not applicable for compact sqlite db). Needed when testing if a new
            filename is already in use. It is allowed that multiple pages have
            the same filenamelowercase, but this should only happen by explicit
            user interaction.
        "filesignature" added, binary. Data block to identify file
            (probably size + mod. date is enough) to check for external
            modification of file (not applicable for compact sqlite db)
        "readonly" added, boolean (actually integer), mark page as currently
            read-only

    Table "wikiwordmatchterms" added:
        To enlist all possible strings to search for a word. This includes the
        words itself, explicit aliases (via "alias" attribute) and implicit
        aliases (headings, optional).

        matchterm: unistring to search for. Same string may appear multiple
            times if no instance of it has type 2.
        matchtermnormcase: unistring. Matchterm in lowercase (not applicable
            for original gadfly db).
        type: integer:
            See Consts.WIKIWORDMATCHTERMS_TYPE_* defs. for the meaning.
            Mainly used values are:
            2: Real word, overwriting is an error and not possible
            7: Explicit alias, overwriting issues a warning.
            9: Term is implicit alias and may be overwritten by explicit
                alias or real word
        word: unistring. Real wiki word to go to
        firstcharpos: integer. Position in real wiki word page to go to
            (-1 for default position)

    Table "datablocks" added:
        Store searches and other small data directly in database.

        unifiedname: unistring with unified name of the data
        data: binary data

        
    Table "datablocksexternal" added:
        Store links to e.g. functional pages, revision infos here
        (not applicable for compact sqlite db)

        unifiedname: String with unified name of the data
        filepath: Name of the binary data file containing the content. The path
            is relative to "data" directory, so it shouldn't contain more than
            the filename under most circumstances.
        filenamelowercase: Lower case of filename in filepath. Needed when
            testing if a new filename is already in use. It is allowed that
            multiple pages have the same filenamelowercase, but this should
            only happen by explicit user interaction.
        filesignature: Binary data block to identify file (probably size + mod.
            date is enough) to check for external modification of file.

    Table "defaultvalues" added:
        Gadfly-specific to provide default values for fields for better
        future format-compatibility. Sqlite has built-in support for defaults
        tablename: bytestring, name of table
        field: bytestring, name of field in table
        value: arbitrary, default object for this field in table


++ 2.0 to 2.1alpha1 (formatver=3):
    
    Table "todos" modified:
        "todo" column replaced by "key" and "value" columns

    Table "wikiwordprops" renamed to "wikiwordattrs"
    
    Tables "todos", "wikiwordattrs", "wikirelations", "wikiwordmatchterms":
        charlength: Integer. Length of the selection whose position is given in
            respective firstcharpos. Invalid if firstcharpos is -1.

"""
