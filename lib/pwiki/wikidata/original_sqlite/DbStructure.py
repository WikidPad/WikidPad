"""
Module responsible for structural changes to the database
(creating/dropping tables), creation of new DBs and the transition from older
DB formats to the current one
"""


import string, codecs, types

from os import mkdir, unlink
from os.path import exists, join

from pwiki.WikiExceptions import *
from pwiki.StringOps import mbcsDec, mbcsEnc, utf8Enc, utf8Dec, applyBinCompact, \
        getBinCompactForDiff, wikiWordToLabel
from pwiki.SearchAndReplace import SearchReplaceOperation

import pwiki.sqlite3api as sqlite

# from SqliteThin3 import *




# Connection (and Cursor)-Wrapper to simplify some operations

class ConnectWrap:
    def __init__(self, connection):
        self.__dict__["dbConn"] = connection
        self.__dict__["dbCursor"] = connection.cursor()
        
        # To make access a bit faster
        self.__dict__["execSql"] = self.dbCursor.execute
        
        self.__dict__["execute"] = self.dbCursor.execute
        self.__dict__["executemany"] = self.dbCursor.executemany
        self.__dict__["commit"] = self.dbConn.commit
        self.__dict__["rollback"] = self.dbConn.rollback
        self.__dict__["fetchone"] = self.dbCursor.fetchone
        self.__dict__["fetchall"] = self.dbCursor.fetchall
        
        
    def __setattr__(self, attr, value):
        setattr(self.dbCursor, attr, value)
        
    def __getattr__(self,  attr):
        return getattr(self.dbCursor, attr)

#     def execSql(self, sql, params=None):
#         "utility method, executes the sql"
#         if params:
#             self.execute(sql, params)
#         else:
#             self.execute(sql)
            

    def execSqlQuery(self, sql, params=None):
        "utility method, executes the sql, returns query result"
        ## print "execSqlQuery sql", sql, repr(params)
        if params:
            self.execute(sql, params, typeDetect=sqlite.TYPEDET_FIRST)
        else:
            self.execute(sql, typeDetect=sqlite.TYPEDET_FIRST)

        return self.dbCursor.fetchall()
 
        
    def execSqlQueryIter(self, sql, params=None):
        """
        utility method, executes the sql, returns an iterator
        over the query results
        """
        ## print "execSqlQuery sql", sql, repr(params)
        if params:
            self.execute(sql, params, typeDetect=sqlite.TYPEDET_FIRST)
        else:
            self.execute(sql, typeDetect=sqlite.TYPEDET_FIRST)

        return iter(self.dbCursor)


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
        self.execSql(sql, params)
        row = self.fetchone()
        if row is None:
            return default
            
        return row[0]
        
        
    def execSqlNoError(self, sql):
        """
        Ignore sqlite errors on execution
        """
        try:
            self.execute(sql)
        except sqlite.Error:
            pass


    def getLastRowid(self):
        return self.dbCursor.lastrowid
        
    def getConnection(self):
        """
        Return wrapped DB-API connection
        """
        return self.dbConn
        
    def getCursor(self):
        return self.dbCursor
        
    def closeCursor(self):
        if self.dbCursor:
            self.dbCursor.close()
            self.dbCursor == None
            
    def __del__(self):
        """
        Only the implicit generated cursor is closed automatically
        on deletion, the connection is not.
        """
        self.closeCursor()


    def close(self):
        """
        Close cursor and connection
        """
        if self.dbConn:
            self.closeCursor()
            self.dbConn.close()
            self.dbConn == None
       



# Helper for the following definitions
class t:
    pass
    
t.r = "real not null default 0.0"
t.i = "integer not null default 0"
t.pi = "integer primary key not null"
t.t = "text not null default ''"
t.pt = "text primary key not null"
t.b = "blob not null default x''"



# Dictionary of definitions for all tables (as for changeTableSchema)
# Some of the tables are optional and don't have to be in the DB

TABLE_DEFINITIONS = {
#     "changelog": (     # Essential if versioning used
#         ("id", t.pi),
#         ("word", t.t),
#         ("op", t.i),
#         ("content", t.b),
#         ("compression", t.i),
#         ("encryption", t.i),
#         ("moddate", t.r)
#         ),
# 
#  
#     "headversion": (     # Essential if versioning used
#         ("word", t.t),
#         ("content", t.b),
#         ("compression", t.i),
#         ("encryption", t.i),
#         ("modified", t.r),
#         ("created", t.r)
#         ),
#     
#     
#     "versions": (     # Essential if versioning used
#         ("id", t.pi),
#         ("description", t.t),
#         ("firstchangeid", t.i),
#         ("created", t.r)
#         ),
                    
                    
    "wikiwords": (     # Essential
        ("word", t.t),
        ("created", t.t),
        ("modified", t.t)
        ),
    
    
    "wikirelations": (     # Cache
        ("word", t.t),
        ("relation", t.t)
        ),
    
    
    "wikiwordprops": (     # Cache
        ("word", t.t),
        ("key", t.t),
        ("value", t.t)
        ),
    
    
    "todos": (     # Cache
        ("word", t.t),
        ("todo", t.t)
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
    }


del t


MAIN_TABLES = (
    "wikiwords",
    "wikirelations",
    "wikiwordprops",
    "todos",
    "search_views",
    "settings"
    )



# def hasVersioningData(connwrap):
#     """
#     connwrap -- a ConnectWrap object
#     Returns true if version information was already stored in the underlying database
#     """
# 
#     t1 = connwrap.execSqlQuerySingleItem("select name from sqlite_master "+\
#             "where name='changelog'", default=None)
#     return not t1 is None
# 
# 
# def createVersioningTables(connwrap):
#     for tn in ("changelog", "headversion", "versions"):
#         changeTableSchema(connwrap, tn, TABLE_DEFINITIONS[tn])
# 
# 
# def deleteVersioningTables(connwrap):
#     for tn in ("changelog", "headversion", "versions"):
#         connwrap.execSqlNoError("drop table %s" % tn)


def rebuildIndices(connwrap):
    """
    Delete and recreate all necessary indices of the database
    """
    connwrap.execSqlNoError("drop index wikiwords_pkey")
    connwrap.execSqlNoError("drop index wikirelations_pkey")
    connwrap.execSqlNoError("drop index wikirelations_word")
    connwrap.execSqlNoError("drop index wikirelations_relation")    
    connwrap.execSqlNoError("drop index wikiwordprops_word")
#     connwrap.execSqlNoError("drop index changelog_word")
#     connwrap.execSqlNoError("drop index headversion_pkey")

    connwrap.execSqlNoError("create unique index wikiwords_pkey on wikiwords(word)")
    connwrap.execSqlNoError("create unique index wikirelations_pkey on wikirelations(word, relation)")
    connwrap.execSqlNoError("create index wikirelations_word on wikirelations(word)")
    connwrap.execSqlNoError("create index wikirelations_relation on wikirelations(relation)")
    connwrap.execSqlNoError("create index wikiwordprops_word on wikiwordprops(word)")
#     connwrap.execSqlNoError("create index changelog_word on changelog(word)")
#     connwrap.execSqlNoError("create unique index headversion_pkey on headversion(word)")



def recreateCacheTables(connwrap):
    """
    Delete and create again all tables with cache information and
    associated indices
    """
    CACHE_TABLES = ("wikirelations", "wikiwordprops", "todos")
    
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
    sqlcreate += ", ".join(map(lambda sc: "%s %s" % sc, schema))
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
    # be created by the DB-interface (this sounds contradictional, but is true)
    
    # Without silent=True, the command would create a commit here
    connwrap.getConnection().setAutoCommit(True, silent=True)

    connwrap.execSql("pragma table_info(%s)" % tablename)
    oldcolumns = map(lambda r: r[1], connwrap.fetchall())
    
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



def createWikiDB(wikiName, dataDir, overwrite=False):
    """
    creates the initial db
    Warning: If overwrite is True, a previous file will be deleted!
    """
    dbfile = join(dataDir, "wikiovw.sli")
    if (not exists(dbfile) or overwrite):
        if (not exists(dataDir)):
            mkdir(dataDir)
        else:
            if exists(dbfile) and overwrite:
                unlink(dbfile)

        # create the database
        connwrap = ConnectWrap(sqlite.connect(dbfile))
        
        try:
            for tn in MAIN_TABLES:
                changeTableSchema(connwrap, tn, TABLE_DEFINITIONS[tn])
    
            connwrap.executemany("insert or replace into settings(key, value) "+
                        "values (?, ?)", (
                    ("formatver", "0"),  # Version of database format the data was written
                    ("writecompatver", "0"),  # Lowest format version which is write compatible
                    ("readcompatver", "0"),  # Lowest format version which is read compatible
                    ("branchtag", "WikidPad")  # Tag of the WikidPad branch
                    )  )

            rebuildIndices(connwrap)
            connwrap.commit()
            
        finally:
            # close the connection
            connwrap.close()

    else:
        raise WikiDBExistsException, "database already exists at location: %s" % dataDir
    

def mbcsToUtf8(s):
    return utf8Enc(mbcsDec(s)[0])[0]


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


# def sqlite_nakedWord(context, values):
#     """
#     Sqlite user-defined function "nakedWord" to remove brackets around
#     wiki words. Needed for version update from 4 to 5.
#     """
#     nakedword = wikiWordToLabel(utf8Dec(values[0].value_text(), "replace")[0])
#     context.result_text(utf8Enc(nakedword)[0])



# Get the default text handling functions
bind_text = sqlite.def_bind_fctfinder(None, None, "")
column_text = sqlite.AUTO_COLUMN_CONVERTS[sqlite.SQLITE_TEXT]


def column_utftext(stmt, col):
    return utf8Dec(column_text(stmt, col))[0]


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

    if type(data) is unicode:
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
#     connwrap.getConnection().createFunction("textToBlob", 1, sqlite_textToBlob)
#     connwrap.getConnection().createFunction("testMatch", 3, sqlite_testMatch)
#     connwrap.getConnection().createFunction("latin1ToUtf8", 1, sqlite_latin1ToUtf8)
#     connwrap.getConnection().createFunction("utf8ToLatin1", 1, sqlite_utf8ToLatin1)
#     connwrap.getConnection().createFunction("mbcsToUtf8", 1, sqlite_mbcsToUtf8)
#     connwrap.getConnection().createFunction("utf8ToMbcs", 1, sqlite_utf8ToMbcs)
#     connwrap.getConnection().createFunction("nakedWord", 1, sqlite_nakedWord)


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
    
    indices = connwrap.execSqlQuerySingleColumn(
            "select name from sqlite_master where type='index'")
    tables = connwrap.execSqlQuerySingleColumn(
            "select name from sqlite_master where type='table'")

    indices = map(string.upper, indices)
    tables = map(string.upper, tables)
    
    if getSettingsValue(connwrap, "branchtag") != "WikidPad":
        return 2, "Database has unknown format branchtag='%s'" \
                % getSettingsValue(connwrap, "branchtag")

    formatver = getSettingsInt(connwrap, "formatver")
    writecompatver = getSettingsInt(connwrap, "writecompatver")

    if writecompatver > 0:
        # TODO: Check compatibility
        
        return 2, "Database has unknown format version='%i'" \
                % formatver
                
    if formatver < 0:
        return 1, "Update needed, current format version='%i'" \
                % formatver
        
    return 0, "Database format is up to date"


def updateDatabase(connwrap):
    """
    Update a database from an older version to current (checkDatabaseFormat()
    should have returned 1 before calling this function)
    """
    connwrap.commit()
    
    indices = connwrap.execSqlQuerySingleColumn(
            "select name from sqlite_master where type='index'")
    tables = connwrap.execSqlQuerySingleColumn(
            "select name from sqlite_master where type='table'")

    indices = map(string.upper, indices)
    tables = map(string.upper, tables)
    
    
    formatver = getSettingsInt(connwrap, "formatver")
    
#                       DO NOT DELETE!
#
#     if formatver == 3:
#         # Update search_views
#         searches = connwrap.execSqlQuerySingleColumn(
#                 "select search from search_views")
#         
#         changeTableSchema(connwrap, "search_views", 
#                 TABLE_DEFINITIONS["search_views"])
#         
#         for search in searches:
#             searchOp = SearchReplaceOperation()
#             searchOp.searchStr = search
#             searchOp.wikiWide = True
#             searchOp.booleanOp = True
# 
#             datablock = searchOp.getPackedSettings()
# 
#             connwrap.execSql(
#                 "insert or replace into search_views(title, datablock) "+\
#                 "values (?, ?)", (searchOp.getTitle(), sqlite.Binary(datablock)))
# 
#         formatver = 4
# 
#     # --- WikiPadCompact 1.5u reached (formatver=4, writecompatver=4,
#     #         readcompatver=4) ---
#     
#     if formatver == 4:
#         # Remove brackets from all wikiword references in database
#         connwrap.execSql("update or ignore wikiwordcontent set "
#                 "word=nakedWord(word)")
#         connwrap.execSql("update or ignore wikiwordprops set "
#                 "word=nakedWord(word)")
#         connwrap.execSql("update or ignore todos set "
#                 "word=nakedWord(word)")
#         connwrap.execSql("update or ignore wikirelations set "
#                 "word=nakedWord(word), "
#                 "relation=nakedWord(relation)")
# 
#     # --- WikiPad(Compact) 1.6beta2 reached (formatver=5, writecompatver=5,
#     #         readcompatver=5) ---
# 
# 
#     # Write format information
#     connwrap.executemany("insert or replace into settings(key, value) "+
#             "values (?, ?)", (
#         ("formatver", "5"),  # Version of database format the data was written
#         ("writecompatver", "5"),  # Lowest format version which is write compatible
#         ("readcompatver", "5"),  # Lowest format version which is read compatible
#         ("branchtag", "WikidPadCompact")  # Tag of the WikidPad branch
#         )   )
# 
#     rebuildIndices(connwrap)
#     
#     connwrap.commit()

        
    
"""
Schema changes in WikidPad:

+++ Initial 1.0 (formatver=0):

    "wikiwords": (     # Essential
        ("word", t.t),
        ("created", t.t),
        ("modified", t.t)
        ),
    
    
    "wikirelations": (     # Cache
        ("word", t.t),
        ("relation", t.t)
        ),
    
    
    "wikiwordprops": (     # Cache
        ("word", t.t),
        ("key", t.t),
        ("value", t.t)
        ),
    
    
    "todos": (     # Cache
        ("word", t.t),
        ("todo", t.t)
        ),
        
    
    "search_views": (     # Essential
        ("title", t.pt),
        ("datablock", t.b)
        ),
    
    
    "settings": (     # Essential
        ("key", t.pt),    # !!! primary key?
        ("value", t.t)
        )

"""
