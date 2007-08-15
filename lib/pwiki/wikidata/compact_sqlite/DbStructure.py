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
        getBinCompactForDiff
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
       


VERSION_DB = 7
VERSION_WRITECOMPAT = 7
VERSION_READCOMPAT = 7


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
    "changelog": (     # Essential if versioning used
        ("id", t.pi),
        ("word", t.t),
        ("op", t.i),
        ("content", t.b),
        ("compression", t.i),
        ("encryption", t.i),
        ("moddate", t.r)
        ),

 
    "headversion": (     # Essential if versioning used
        ("word", t.t),
        ("content", t.b),
        ("compression", t.i),
        ("encryption", t.i),
        ("modified", t.r),
        ("created", t.r)
        ),
    
    
    "versions": (     # Essential if versioning used
        ("id", t.pi),
        ("description", t.t),
        ("firstchangeid", t.i),
        ("created", t.r)
        ),


    "wikiwordcontent": (     # Essential for Compact
        ("word", t.t),
        ("content", t.b),
        ("compression", t.i),
        ("encryption", t.i),
        ("modified", t.r),
        ("created", t.r),
        ("presentationdatablock", t.b),
        ("wordnormcase", t.t)
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
    
    
    "settings": (     # Essential since Compact 1.3
        ("key", t.pt),    # !!! primary key?
        ("value", t.t)
        )
    }


del t


MAIN_TABLES = (
    "wikiwordcontent",
    "wikirelations",
    "wikiwordprops",
    "todos",
    "search_views",
    "settings"
    )



def hasVersioningData(connwrap):
    """
    connwrap -- a ConnectWrap object
    Returns true if version information was already stored in the underlying database
    """

    t1 = connwrap.execSqlQuerySingleItem("select name from sqlite_master "+\
            "where name='changelog'", default=None)
    return not t1 is None


def createVersioningTables(connwrap):
    for tn in ("changelog", "headversion", "versions"):
        changeTableSchema(connwrap, tn, TABLE_DEFINITIONS[tn])


def deleteVersioningTables(connwrap):
    for tn in ("changelog", "headversion", "versions"):
        connwrap.execSqlNoError("drop table %s" % tn)


def rebuildIndices(connwrap):
    """
    Delete and recreate all necessary indices of the database
    """
    connwrap.execSqlNoError("drop index wikiwordcontent_pkey")
    connwrap.execSqlNoError("drop index wikiwords_wordnormcase")
    connwrap.execSqlNoError("drop index wikirelations_pkey")
    connwrap.execSqlNoError("drop index wikirelations_word")
    connwrap.execSqlNoError("drop index wikirelations_relation")    
    connwrap.execSqlNoError("drop index wikiwordprops_word")
    connwrap.execSqlNoError("drop index changelog_word")
    connwrap.execSqlNoError("drop index headversion_pkey")
        
    connwrap.execSqlNoError("create unique index wikiwordcontent_pkey on wikiwordcontent(word)")
    connwrap.execSqlNoError("create index wikiwords_wordnormcase on wikiwordcontent(wordnormcase)")
    connwrap.execSqlNoError("create unique index wikirelations_pkey on wikirelations(word, relation)")
    connwrap.execSqlNoError("create index wikirelations_word on wikirelations(word)")
    connwrap.execSqlNoError("create index wikirelations_relation on wikirelations(relation)")
    connwrap.execSqlNoError("create index wikiwordprops_word on wikiwordprops(word)")
    connwrap.execSqlNoError("create index changelog_word on changelog(word)")
    connwrap.execSqlNoError("create unique index headversion_pkey on headversion(word)")



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

    connwrap.execSql("create unique index wikirelations_pkey on wikirelations(word, relation)")
    connwrap.execSql("create index wikirelations_word on wikirelations(word)")
    connwrap.execSql("create index wikirelations_relation on wikirelations(relation)")
    connwrap.execSql("create index wikiwordprops_word on wikiwordprops(word)")



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
    dbfile = join(dataDir, "wiki.sli")
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
                    ("formatver", str(VERSION_DB)),  # Version of database format the data was written
                    ("writecompatver", str(VERSION_WRITECOMPAT)),  # Lowest format version which is write compatible
                    ("readcompatver", str(VERSION_READCOMPAT)),  # Lowest format version which is read compatible
                    ("branchtag", "WikidPadCompact")  # Tag of the WikidPad branch
#                     ("locale", "-") # Locale for cached wordnormcase column. '-': column invalid
                    )  )

            rebuildIndices(connwrap)
            connwrap.commit()
            
        finally:
            # close the connection
            connwrap.close()

    else:
        raise WikiDBExistsException, "database already exists at location: %s" % dataDir
    





def sqlite_utf8ToLatin1(context, values):
    """
    Used as user-defined sqlite function
    """
    enc = codecs.getencoder("iso-8859-1")
    
    s = values[0].value_text()
    context.result_text(enc(utf8Dec(s)[0])[0])


def sqlite_latin1ToUtf8(context, values):
    """
    Used as user-defined sqlite function
    """
    dec = codecs.getdecoder("iso-8859-1")
    
    s = values[0].value_text()
    context.result_text(utf8Enc(dec(s)[0])[0])


def sqlite_utf8ToMbcs(context, values):
    """
    Used as user-defined sqlite function
    """
    enc = codecs.getencoder("mbcs")
    
    s = values[0].value_text()
    context.result_text(enc(utf8Dec(s)[0])[0])


def mbcsToUtf8(s):
    return utf8Enc(mbcsDec(s)[0])[0]


def sqlite_mbcsToUtf8(context, values):
    """
    Used as user-defined sqlite function
    """
    dec = codecs.getdecoder("mbcs")
    
    s = values[0].value_text()
    context.result_text(utf8Enc(dec(s)[0])[0])


def sqlite_textToBlob(context, values):
    """
    User-defined sqlite function to convert text to blob without changes
    """
    context.result_blob(values[0].value_text())


def sqlite_testMatch(context, values):
    """
    Sqlite user-defined function "testMatch" for WikiData.search()
    method
    """
    nakedword = utf8Dec(values[0].value_blob(), "replace")[0]
    fileContents = utf8Dec(values[1].value_blob(), "replace")[0]
    sarOp = sqlite.getTransObject(values[2].value_int())
    if sarOp.testWikiPage(nakedword, fileContents) == True:
        context.result_int(1)
    else:
        context.result_null()


def sqlite_nakedWord(context, values):
    """
    Sqlite user-defined function "nakedWord" to remove brackets around
    wiki words. Needed for version update from 4 to 5.
    """
    word = utf8Dec(values[0].value_text(), "replace")[0]
    if word.startswith(u"[") and word.endswith(u"]"):
        nakedword = word[1:-1]
    else:
        nakedword = word

    context.result_text(utf8Enc(nakedword)[0])


def sqlite_utf8Normcase(context, values):
    """
    Sqlite user-defined function "utf8Normcase" to get the lowercase of a word
    encoded in UTF-8. The result is also encoded in UTF-8.
    """
    normalWord = utf8Dec(values[0].value_text(), "replace")[0].lower()
    context.result_text(utf8Enc(normalWord)[0])


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
    connwrap.getConnection().createFunction("textToBlob", 1, sqlite_textToBlob)
    connwrap.getConnection().createFunction("testMatch", 3, sqlite_testMatch)
    connwrap.getConnection().createFunction("latin1ToUtf8", 1, sqlite_latin1ToUtf8)
    connwrap.getConnection().createFunction("utf8ToLatin1", 1, sqlite_utf8ToLatin1)
    connwrap.getConnection().createFunction("mbcsToUtf8", 1, sqlite_mbcsToUtf8)
    connwrap.getConnection().createFunction("utf8ToMbcs", 1, sqlite_utf8ToMbcs)
    connwrap.getConnection().createFunction("nakedWord", 1, sqlite_nakedWord)
    connwrap.getConnection().createFunction("utf8Normcase", 1, sqlite_utf8Normcase)


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
    
    indices = connwrap.execSqlQuerySingleColumn("select name from sqlite_master where type='index'")
    tables = connwrap.execSqlQuerySingleColumn("select name from sqlite_master where type='table'")

    indices = map(string.upper, indices)
    tables = map(string.upper, tables)
    
    if not "SETTINGS" in tables:
        return 1, "Update needed"
        
        
    if getSettingsValue(connwrap, "branchtag") != "WikidPadCompact":
        return 2, "Database has unknown format branchtag='%s'" \
                % getSettingsValue(connwrap, "branchtag")

    formatver = getSettingsInt(connwrap, "formatver")
    writecompatver = getSettingsInt(connwrap, "writecompatver")

    if writecompatver > VERSION_WRITECOMPAT:
        # TODO: Check compatibility
        
        return 2, "Database has unknown format version='%i'" \
                % formatver
                
    if formatver < VERSION_DB:
        return 1, "Update needed, current format version='%i'" \
                % formatver
        
    return 0, "Database format is up to date"


def updateDatabase(connwrap):
    """
    Update a database from an older version to current (checkDatabaseFormat()
    should have returned 1 before calling this function)
    """
    connwrap.commit()
    
    indices = connwrap.execSqlQuerySingleColumn("select name from sqlite_master where type='index'")
    tables = connwrap.execSqlQuerySingleColumn("select name from sqlite_master where type='table'")

    indices = map(string.upper, indices)
    tables = map(string.upper, tables)
    
    # updatedTables = []
    
    if not "SETTINGS" in tables:
        # We are prior WikidPadCompact 1.3pre (which writes format version 0)
        
        # From WikidPad original
        if "WIKIWORDPROPS_PKEY" in indices:
            print "dropping index wikiwordprops_pkey"
            connwrap.execSql("drop index wikiwordprops_pkey")
#         if "WIKIWORDPROPS_WORD" not in indices:
#             print "creating index wikiwordprops_word"
#             connwrap.execSql("create index wikiwordprops_word on wikiwordprops(word)")
#         if "WIKIRELATIONS_WORD" not in indices:
#             print "creating index wikirelations_word"
#             connwrap.execSql("create index wikirelations_word on wikirelations(word)")
        if "REGISTRATION" in tables:
            connwrap.execSql("drop table registration")
            
        # Here we have reached WikidPadCompact 1.0/1.1 format            
            
        # For database format changes
        rt = "real not null default 0.0"
        it = "integer not null default 0"
        tt = "text not null default ''"
        bt = "blob not null default x''"
    
        # From WikiPadCompact 1.1 to 1.2:            
        # if "WIKIWORDS" in tables:
        connwrap.execSqlNoError("drop table wikiwords")
            
        # Remove column "created" from "wikirelations"
        changed = changeTableSchema(connwrap, "wikirelations", 
                TABLE_DEFINITIONS["wikirelations"])

        # --- WikiPadCompact 1.2 reached ---
    
        # From WikiPadCompact 1.2 to 1.3:
        # Update all text items from standard encoding to UTF8
        # TODO: "Please wait"

        ## wikidata.dbConn.createFunction("stdToUtf8", 1, sqlite_stdToUtf8)
        
        connwrap.execSql("update wikiwordcontent set word=latin1ToUtf8(word), "+
                "content=textToBlob(content)")
        connwrap.execSql("update wikiwordprops set word=latin1ToUtf8(word), "+
                "key=latin1ToUtf8(key), value=latin1ToUtf8(value)")
        connwrap.execSql("update todos set word=latin1ToUtf8(word), "+
                "todo=latin1ToUtf8(todo)")
        connwrap.execSql("update search_views set search=latin1ToUtf8(search)")
        connwrap.execSql("update wikirelations set word=latin1ToUtf8(word), "+
                "relation=latin1ToUtf8(relation)")
                
        
        if hasVersioningData(connwrap):
            connwrap.execSql("update changelog set word=latin1ToUtf8(word)")
            connwrap.execSql("update headversion set word=latin1ToUtf8(word)")
            connwrap.execSql("update versions set description=latin1ToUtf8(description)")


        # Create the settings table:
        changeTableSchema(connwrap, "settings", 
                TABLE_DEFINITIONS["settings"])

        connwrap.executemany("insert or replace into settings(key, value) "+
                "values (?, ?)", (
            ("formatver", "0"),  # Version of database format the data was written in
            ("writecompatver", "0"),  # Lowest format version which is write compatible
            ("readcompatver", "0"),  # Lowest format version which is read compatible
            ("branchtag", "WikidPadCompact")  # Tag of the WikidPad branch
            )   )
                
                
        # --- WikiPadCompact 1.3pre reached (formatver=0, writecompatver=0,
        #         readcompatver=0) ---
                
                
    formatver = getSettingsInt(connwrap, "formatver")
    
    if formatver == 0:
        # Update wikiwordcontent (add "created" column):
        changeTableSchema(connwrap, "wikiwordcontent", 
                TABLE_DEFINITIONS["wikiwordcontent"])
                
        formatver = 1
        
    # --- WikiPadCompact 1.3 reached (formatver=1, writecompatver=1,
    #         readcompatver=0) ---
    
    if formatver == 1:
        # Repair bugs in versioning data (missing "created" column, wrong content type)
        if hasVersioningData(connwrap):
            # Update headversion (add "created" column):
            changeTableSchema(connwrap, "headversion", 
                    TABLE_DEFINITIONS["headversion"])
                    
            # Convert content values to blobs                    
            # Will be incorporated in transition 2 -> 3:
#             connwrap.execSql("update headversion set content=textToBlob(content)")
#             connwrap.execSql("update changelog set content=textToBlob(content)")
  
        formatver = 2

    # --- WikiPadCompact 1.3.1 reached (formatver=2, writecompatver=1,
    #         readcompatver=0) ---

    if formatver == 2:
        # Switch everything to utf-8, repair faked utf-8
        
        connwrap.execSql("update wikiwordcontent set "+
                "word=mbcsToUtf8(utf8ToLatin1(word)), "+
                "content=textToBlob(mbcsToUtf8(content))")
        connwrap.execSql("update wikiwordprops set "+
                "word=mbcsToUtf8(utf8ToLatin1(word)), "+
                "key=mbcsToUtf8(utf8ToLatin1(key)), "+
                "value=mbcsToUtf8(utf8ToLatin1(value))")
        connwrap.execSql("update todos set "+
                "word=mbcsToUtf8(utf8ToLatin1(word)), "+
                "todo=mbcsToUtf8(utf8ToLatin1(todo))")
        connwrap.execSql("update search_views set "+
                "search=mbcsToUtf8(utf8ToLatin1(search))")
        connwrap.execSql("update wikirelations set "+
                "word=mbcsToUtf8(utf8ToLatin1(word)), "+
                "relation=mbcsToUtf8(utf8ToLatin1(relation))")


#         if hasVersioningData(connwrap):   #TODO !!!
#             connwrap.execSql("update headversion set "+
#                     "word=mbcsToUtf8(utf8ToLatin1(word)), "+
#                     "content=textToBlob(mbcsToUtf8(content))")
#             connwrap.execSql("update versions set "+
#                     "description=mbcsToUtf8(utf8ToLatin1(description))")
#                     
#             # Updating changelog
#             # 1. word column for all rows
#             connwrap.execSql("update changelog set "+
#                     "word=mbcsToUtf8(utf8ToLatin1(word))")
# 
#             # 2. Update modify operation
#             #    Create temporary copy of headversion table
#             sqlcreate = "create temp table tempverupd ("
#             sqlcreate += ", ".join(map(lambda sc: "%s %s" % sc,
#                     TABLE_DEFINITIONS["headversion"]))
#             sqlcreate += ")"
#             connwrap.execSql(sqlcreate)
#             
#             connwrap.execSql("insert into tempverupd select * from headversion")
#             
#             
#             connwrap.execSqlQuery
#             changes = connWrap.execSqlQuery("select word, op, content, moddate "+
#                     "from changelog order by id desc")
# 
#             for word, op, content, moddate in changes:
#                 if op == 0 or op == 2:
#                     connwrap.execSql("insert or replace into tempverupd"+
#                             "(content) values (?)", (content,))
#                 elif op == 1:
#                     fromContent = connwrap.execSqlSingleItem("select content "+
#                             "from tempverupd where word=?", (word,))
#                     oldDiff = content
#                     toContent = applyBinCompact(fromContent, diff)
#                     newDiff = getBinCompactForDiff(fromContent, toContent)
#                     self.setContentRaw(word, applyBinCompact(self.getContent(word), content), moddate)
#                 elif op == 3:
#                     connwrap.execSql("delete from tempverupd where word=?",
#                             (word,)
# 
#             # 3. changelog content column for all but modify operation (op code 1)
#             connwrap.execSql("update changelog set "+
#                     "content=textToBlob(mbcsToUtf8(word)) where op != 1")
#                 
#             # !!!!!!!!!!!


        formatver = 3

    # --- WikiPadCompact 1.3.2uni reached (formatver=3, writecompatver=3,
    #         readcompatver=3) ---

    if formatver == 3:
        # Update search_views
        searches = connwrap.execSqlQuerySingleColumn(
                "select search from search_views")
        
        changeTableSchema(connwrap, "search_views", 
                TABLE_DEFINITIONS["search_views"])
        
        for search in searches:
            searchOp = SearchReplaceOperation()
            searchOp.searchStr = search
            searchOp.wikiWide = True
            searchOp.booleanOp = True

            datablock = searchOp.getPackedSettings()

            connwrap.execSql(
                "insert or replace into search_views(title, datablock) "+\
                "values (?, ?)", (searchOp.getTitle(), sqlite.Binary(datablock)))

        formatver = 4

    # --- WikiPadCompact 1.5u reached (formatver=4, writecompatver=4,
    #         readcompatver=4) ---
    
    if formatver == 4:
        # Remove brackets from all wikiword references in database
        connwrap.execSql("update or ignore wikiwordcontent set "
                "word=nakedWord(word)")
        connwrap.execSql("update or ignore wikiwordprops set "
                "word=nakedWord(word)")
        connwrap.execSql("update or ignore todos set "
                "word=nakedWord(word)")
        connwrap.execSql("update or ignore wikirelations set "
                "word=nakedWord(word), "
                "relation=nakedWord(relation)")
                
        formatver = 5
    # --- WikiPad(Compact) 1.6beta2 reached (formatver=5, writecompatver=5,
    #         readcompatver=5) ---

    if formatver == 5:
        # Add column "firstcharpos" to some tables

        changeTableSchema(connwrap, "wikirelations",
                TABLE_DEFINITIONS["wikirelations"])
        changeTableSchema(connwrap, "wikiwordprops", 
                TABLE_DEFINITIONS["wikiwordprops"])
        changeTableSchema(connwrap, "todos", 
                TABLE_DEFINITIONS["todos"])
        
        formatver = 6

        # --- WikiPad 1.7beta1 reached (formatver=6, writecompatver=5,
        #         readcompatver=5) ---

    if formatver == 6:
        # Add columns "presentationdatablock" and "wordnormcase" to wikiwordcontent

        changeTableSchema(connwrap, "wikiwordcontent",
                TABLE_DEFINITIONS["wikiwordcontent"])

        formatver = 7

        # --- WikiPad 1.8beta1 reached (formatver=7, writecompatver=7,
        #         readcompatver=7) ---

    # Write format information
    connwrap.executemany("insert or replace into settings(key, value) "+
            "values (?, ?)", (
        ("formatver", str(VERSION_DB)),  # Version of database format the data was written
        ("writecompatver", str(VERSION_WRITECOMPAT)),  # Lowest format version which is write compatible
        ("readcompatver", str(VERSION_READCOMPAT)),  # Lowest format version which is read compatible
        ("branchtag", "WikidPadCompact")  # Tag of the WikidPad branch
#         ("locale", "-") # Locale for cached wordnormcase column. '-': column invalid
        )   )

    rebuildIndices(connwrap)
    
    connwrap.commit()



def updateDatabase2(connwrap):
    """
    Second update function. Called when database version is current.
    Performs further updates
    """
    wordnormcasemode = getSettingsValue(connwrap, "wordnormcasemode")
    if wordnormcasemode != "lower":
        # No wordnormcasemode or other mode defined

        # Fill column wordnormcase
        connwrap.execSql("update wikiwordcontent set wordnormcase=utf8Normcase(word)")

        connwrap.execSql("insert or replace into settings(key, value) "
                "values ('wordnormcasemode', 'lower')")

    try:
        # Write which version at last wrote to database
        connwrap.execSql("insert or replace into settings(key, value) "
                "values ('lastwritever', '"+str(VERSION_DB)+"')")
    except sqlite.ReadOnlyDbError:
        pass



# class WikiDBExistsException(WikiDataException): pass
# class WikiDBExistsException(Exception): pass


"""
Schema changes in WikidPadCompact:

+++ Initial 1.0:


TABLE_DEFINITIONS = {
    "changelog": (
        ("id", t.pi),
        ("word", t.t),
        ("op", t.i),
        ("content", t.b),
        ("compression", t.i),
        ("encryption", t.i),
        ("moddate", t.r)
        ),

 
    "headversion": (
        ("word", t.pt),    # !!! primary key?
        ("content", t.b),
        ("compression", t.i),
        ("encryption", t.i),
        ("modified", t.r)
        ),
    
    
    "versions": (
        ("id", t.pi),
        ("description", t.t),
        ("firstchangeid", t.i),
        ("created", t.r)
        ),
                    
                    
    "wikiwordcontent": (
        ("word", t.t),
        ("content", t.b),
        ("compression", t.i),
        ("encryption", t.i),
        ("modified", t.r),
        ),
        
        
    "wikiwords": (
        ("word", t.t),
        ("created", t.t),
        ("modified", t.t)
        ),
    
    
    "wikirelations": (
        ("word", t.t),
        ("relation", t.t)
        ),
    
    
    "wikiwordprops": (
        ("word", t.t),
        ("key", t.t),
        ("value", t.t)
        ),
    
    
    "todos": (
        ("word", t.t),
        ("todo", t.t)
        ),
        
    
    "search_views": (
        ("search", t.t),
        )
    
    
    
    }
    


+++ 1.0 to 1.1:
    Nothing


+++ 1.1 to 1.2:
    Table "wikiwords" deleted


+++ 1.2 to 1.3pre (formatver=0):
    Table "settings" created:
    
        "settings": (
        ("key", t.pt),    # !!! primary key?
        ("value", t.t)
        )
        
    Every text field converted from raw text to utf8 (bug: this was forgotten for
    the versioning tables)
        
+++ 1.3pre (formatver=0) to 1.3 (formatver=1)
        
    In table "wikiwordcontent" column ("created", t.r) added
    
+++ 1.3 (formatver=1) to 1.3.1 (formatver=2)
        
    Bug fix: in table "headversion" column ("created", t.r) added
    ((Bug fix: Converting text fields in versioning tables to utf8))
    
+++ 1.3.1 (formatver=2) to 1.3.2uni (formatver=3)

    Switching content to UTF-8, repairing faked UTF-8 in
    tables wikiwordcontent, wikiwordprops, todos, search_views
    wikirelations

+++ 1.4.5u (formatver=3) to 1.5u (formatver=4)

    Completely new search_views table (previous data deleted)
    to store complex wiki-wide searches
    
    
+++ TODO Add missing entry
    
    
+++ 1.6beta4 (formatver=5) to 1.7beta1 (formatver=6)

    Added column "firstcharpos" to tables "wikirelations",
    "wikiwordprops", "todos". This column contains the position of the
    link, property or todo respectively in the wiki page in characters.
    
+++ 1.7bet1 (formatver=6) to 1.8beta (formatver=7)

    "wikiwordcontent": (     # Essential for Compact
        ("word", t.t),
        ("content", t.b),
        ("compression", t.i),
        ("encryption", t.i),
        ("modified", t.r),
        ("created", t.r),
        ("presentationdatablock", t.b),
        ("wordnormcase", t.t)
        ),

Column "presentationdatablock" contains byte string describing how to present
a particular page (window scroll and cursor position). Its content is
en/decoded by the WikiDataManager.

Column "wordnormcase" contains byte string returned by the normCase method
of a Collator object (see "Localization.py"). The column's content should 
be recreated at a rebuild.

Added "locale" key in "settings" table. This is the name of the locale used to
create the "wordnormcase" column content. A "-" means the column contains
invalid data.

"""

