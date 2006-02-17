"""
Module responsible for structural changes to the database
(creating/dropping tables), creation of new DBs and the transition from older
DB formats to the current one
"""


import string, codecs, types

from os import mkdir, unlink, rename
from os.path import exists, join, split, basename
import glob

from pwiki.WikiExceptions import *
from pwiki.StringOps import mbcsDec, mbcsEnc, utf8Enc, utf8Dec, \
        removeBracketsFilename, wikiWordToLabel
from pwiki.SearchAndReplace import SearchReplaceOperation

import gadfly

# from SqliteThin3 import *


def _uniToUtf8(ob):
    if type(ob) is unicode:
        return utf8Enc(ob)[0]
    else:
        return ob


def _utf8ToUni(ob):
    if type(ob) is str:
        return utf8Dec(ob, "replace")[0]
    else:
        return ob



# Connection (and Cursor)-Wrapper to simplify some operations

class ConnectWrap:
    def __init__(self, connection):
        self.__dict__["dbConn"] = connection
        self.__dict__["dbCursor"] = connection.cursor()
        
#         # To make access a bit faster
#         self.__dict__["execSql"] = self.dbCursor.execute
        
        self.__dict__["execute"] = self.dbCursor.execute
        # self.__dict__["executemany"] = self.dbCursor.executemany  # TODO Replace by simple implementation
        self.__dict__["commit"] = self.dbConn.commit
        self.__dict__["rollback"] = self.dbConn.rollback
        self.__dict__["fetchone"] = self.dbCursor.fetchone
        self.__dict__["fetchall"] = self.dbCursor.fetchall
        
        
    def __setattr__(self, attr, value):
        setattr(self.dbCursor, attr, value)
        
    def __getattr__(self,  attr):
        return getattr(self.dbCursor, attr)


    def execSql(self, sql, params=None):
        "utility method, executes the sql"
        if params:
            params = tuple(map(_uniToUtf8, params))
            self.execute(sql, params)
        else:
            self.execute(sql)
            

    def execSqlQuery(self, sql, params=None, strConv=True):
        """
        utility method, executes the sql, returns query result
        params -- Tuple of parameters for sql statement
        strConv -- Should returned strings be seen as UTF8 and converted to unicode
                or instead left as they are?
        """
        ## print "execSqlQuery sql", sql, repr(params)
        if params:
            self.execSql(sql, params)
        else:
            self.execSql(sql)

        result = self.dbCursor.fetchall()

        if strConv:
            result = [tuple(map(_utf8ToUni, row)) for row in result]

        return result
            
 
        
    def execSqlQueryIter(self, sql, params=None):  # TODO Support unicode conversion
        """
        utility method, executes the sql, returns an iterator
        over the query results
        """
        ## print "execSqlQuery sql", sql, repr(params)
        if params:
            self.execute(sql, params)
        else:
            self.execute(sql)

        return iter(self.dbCursor)


    def execSqlQuerySingleColumn(self, sql, params=None, strConv=True):
        """
        utility method, executes the sql, returns a single column query result
        params -- Tuple of parameters for sql statement
        strConv -- Should returned strings be seen as UTF8 and converted to unicode
                or instead left as they are?
        """
        data = self.execSqlQuery(sql, params, strConv=strConv)
        return [row[0] for row in data]
        

    def execSqlQuerySingleItem(self, sql, params=None, default=None,
            strConv=True):
        """
        Executes a query to retrieve at most one row with
        one column and returns result. If query results
        to 0 rows, default is returned (defaults to None)
        
        params -- Tuple of parameters for sql statement
        strConv -- Should returned strings be seen as UTF8 and converted to unicode
                or instead left as they are?
        """
        self.execSql(sql, params)
        try:
            row = self.fetchone()
        except:   # TODO More specific catch
        # if row is None:
            return default
            
        if strConv:
            return _utf8ToUni(row[0])
        else:
            return row[0]
        
        
    def execSqlNoError(self, sql):  # TODO Support unicode conversion
        """
        Ignore sqlite errors on execution
        """
        try:
            self.execute(sql)
        except:   #  TODO: Specific exception catch?
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
    
# t.r = "real not null default 0.0"
# t.i = "integer not null default 0"
# t.pi = "integer primary key not null"
t.t = "varchar"
# t.pt = "text primary key not null"
# t.b = "blob not null default x''"



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
#                     
#                     
#     "wikiwordcontent": (     # Essential for Compact
#         ("word", t.t),
#         ("content", t.b),
#         ("compression", t.i),
#         ("encryption", t.i),
#         ("modified", t.r),
#         ("created", t.r)
#         ),
    
    
    "wikiwords": (     # Essential
        ("word", t.t),
        ("created", t.t),
        ("modified", t.t)
        ),


    "wikirelations": (     # Cache
        ("word", t.t),
        ("relation", t.t),
        ("created", t.t)    # TODO What is this good for?
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
        ("title", t.t),
        ("datablock", t.t)
        ),
    
    
    "settings": (     # Essential since 1.2beta2
        ("key", t.t),
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


def rebuildIndices(connwrap):
    """
    Delete and recreate all necessary indices of the database
    """
    connwrap.commit()

    connwrap.execSqlNoError("drop index wikiwords_pkey")
    connwrap.execSqlNoError("drop index wikirelations_pkey")
    connwrap.execSqlNoError("drop index settings_pkey")
    connwrap.execSqlNoError("drop index search_views_pkey")
    connwrap.execSqlNoError("drop index wikirelations_word")
    connwrap.execSqlNoError("drop index wikiwordprops_word")    
        
    connwrap.execSqlNoError("create unique index wikiwords_pkey on wikiwords(word)")
    connwrap.execSqlNoError("create unique index wikirelations_pkey on wikirelations(word, relation)")
    connwrap.execSqlNoError("create unique index settings_pkey on settings(key)")
    connwrap.execSqlNoError("create unique index search_views_pkey on search_views(title)")
    connwrap.execSqlNoError("create index wikirelations_word on wikirelations(word)")
    connwrap.execSqlNoError("create index wikiwordprops_word on wikiwordprops(word)")

    connwrap.commit()


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
    
#     print "changeTableSchema1", repr(tablename), repr(schema)
    
    # Build the sql command to create the table with new schema (needed later)
    sqlcreate = "create table %s (" % tablename
    sqlcreate += ", ".join(map(lambda sc: "%s %s" % sc, schema))
    sqlcreate += ")"
    

    # Test if table already exists
    
    tn = connwrap.execSqlQuerySingleItem(
            "select table_name from __table_names__ where table_name='%s'" %
            tablename.upper())

    if tn is None:
        # Does not exist, so simply create
        connwrap.commit()        
        connwrap.execSql(sqlcreate)
        connwrap.commit()        
        return True

#     print "changeTableSchema2", repr(sqlcreate)

    # Table exists, so retrieve list of columns
    oldcolumns = connwrap.execSqlQuerySingleColumn(
            "select COLUMN_NAME from __columns__ where TABLE_NAME = '%s'" %
            tablename.upper())
    
    oldcolumns = map(string.upper, oldcolumns)
    
    # Which columns have old and new schema in common?    
    intersect = []
    for n, d in schema:
        n = n.upper()
        if n in oldcolumns:
            intersect.append(n)
            
    recreate = False
    
    if forcechange:
        recreate = True
    elif (len(oldcolumns) != len(schema)) or (len(intersect) != len(oldcolumns)):
        recreate = True

    if not recreate:
        return False  # Nothing to do, same column set as before

#     print "changeTableSchema4"

    if len(intersect) > 0:
#         print "changeTableSchema5"
        typemap = {}
        for n, t in schema:
            n = n.upper()
            typemap[n] = t
            
        intersecttyped = ["%s %s" % (n, typemap[n]) for n in intersect]
        intersecttyped = ", ".join(intersecttyped)
        
        intersect = ", ".join(intersect)
        
        connwrap.commit()        
        connwrap.execSql("create table tmptable(%s)" % intersecttyped)
        connwrap.execSql("insert into tmptable(%s) select %s from %s" % 
                (intersect, intersect, tablename))
        connwrap.execSql("drop table %s" % tablename)
        connwrap.execSql(sqlcreate)
        connwrap.execSql("insert into %s(%s) select %s from tmptable" %
                (tablename, intersect, intersect))
        connwrap.execSql("drop table tmptable")
        connwrap.commit()        
    else:
        # Nothing in common -> delete old, create new
#         print "changeTableSchema7"
        connwrap.commit()        
        connwrap.execSql("drop table %s" % tablename)
        connwrap.execSql(sqlcreate)
        connwrap.commit()
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
        connection = gadfly.gadfly()
        connection.startup("wikidb", dataDir)
        connwrap = ConnectWrap(connection)
        
        try:
            for tn in MAIN_TABLES:
                changeTableSchema(connwrap, tn, TABLE_DEFINITIONS[tn])
                
            for key, value in (
                    ("formatver", "2"),  # Version of database format the data was written
                    ("writecompatver", "2"),  # Lowest format version which is write compatible
                    ("readcompatver", "2"),  # Lowest format version which is read compatible
                    ("branchtag", "WikidPad")  # Tag of the WikidPad branch
                    ):
                setSettingsValue(connwrap, key, value)
    
#             connwrap.executemany("insert or replace into settings(key, value) "+
#                         "values (?, ?)", (
#                     ("formatver", "0"),  # Version of database format the data was written
#                     ("writecompatver", "0"),  # Lowest format version which is write compatible
#                     ("readcompatver", "0"),  # Lowest format version which is read compatible
#                     ("branchtag", "WikidPad")  # Tag of the WikidPad branch
#                     )  )
        
            rebuildIndices(connwrap)
            connwrap.commit()
            
        finally:
            # close the connection
            connwrap.close()

    else:
        raise WikiDBExistsException, "database already exists at location: %s" % dataDir



def setSettingsValue(connwrap, key, value):
    prevvalue = connwrap.execSqlQuerySingleItem("select value from settings " +
            "where key='%s'" % key)
    if prevvalue is None:
        connwrap.execSql("insert into settings(key, value) " +
                "values ('%s', '%s')" % (key, value))
    else:
        connwrap.execSql("update settings set value = '%s' where key = '%s'" %
                (str(value), key))


def getSettingsValue(connwrap, key, default=None):
    """
    Retrieve a value from the settings table
    default -- Default value to return if key was not found
    """
    return connwrap.execSqlQuerySingleItem("select value from settings " +
            "where key='%s'" % (key,), default)


def getSettingsInt(connwrap, key, default=None):
    """
    Retrieve an integer value from the settings table.
    default -- Default value to return if key was not found
    """
    return int(connwrap.execSqlQuerySingleItem("select value from settings " +
            "where key='%s'" % (key,), default))


def checkDatabaseFormat(connwrap):
    """
    Check the database format.
    Returns: 0: Up to date,  1: Update needed,  2: Unknown format, update not possible
    """
    
    indices = connwrap.execSqlQuerySingleColumn("select INDEX_NAME from __indices__")
    tables = connwrap.execSqlQuerySingleColumn("select TABLE_NAME from __table_names__")

    indices = map(string.upper, indices)
    tables = map(string.upper, tables)

    if not "SETTINGS" in tables:
        return 1, "Update needed"
        
    if getSettingsValue(connwrap, "branchtag") != "WikidPad":
        return 2, "Database has unknown format branchtag='%s'" \
                % getSettingsValue(connwrap, "branchtag")

    formatver = getSettingsInt(connwrap, "formatver")
    writecompatver = getSettingsInt(connwrap, "writecompatver")

    if writecompatver > 2:
        # TODO: Check compatibility
        
        return 2, "Database has unknown format version='%i'" \
                % formatver
                
    if formatver < 2:
        return 1, "Update needed, current format version='%i'" \
                % formatver
        
    return 0, "Database format is up to date"


def updateDatabase(connwrap, dataDir):
    """
    Update a database from an older version to current (checkDatabaseFormat()
    should have returned 1 before calling this function)
    """
    connwrap.commit()

    indices = connwrap.execSqlQuerySingleColumn("select INDEX_NAME from __indices__")
    tables = connwrap.execSqlQuerySingleColumn("select TABLE_NAME from __table_names__")

    indices = map(string.upper, indices)
    tables = map(string.upper, tables)
    
    # updatedTables = []
    
    if not "SETTINGS" in tables:
        # We are prior WikidPad 1.2beta2 (which writes format version 0)
        
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
                "insert into search_views(title, datablock) "+\
                "values (?, ?)", (searchOp.getTitle(), datablock))

        formatver = 0
        
        changeTableSchema(connwrap, "settings", 
                TABLE_DEFINITIONS["settings"])
        
        for key, value in (
                ("formatver", "0"),  # Version of database format the data was written
                ("writecompatver", "0"),  # Lowest format version which is write compatible
                ("readcompatver", "0"),  # Lowest format version which is read compatible
                ("branchtag", "WikidPad")  # Tag of the WikidPad branch
                ):
            setSettingsValue(connwrap, key, value)


        # --- WikiPad 1.20beta2 reached (formatver=0, writecompatver=0,
        #         readcompatver=0) ---


    formatver = getSettingsInt(connwrap, "formatver")
    
    if formatver == 0:
        # From formatver 0 to 1, all filenames with brackets are renamed
        # to have no brackets
        filenames = glob.glob(join(mbcsEnc(dataDir, "replace")[0], '*.wiki'))
        for fn in filenames:
            fn = mbcsDec(fn, "replace")[0]
            bn = basename(fn)
            newbname = removeBracketsFilename(bn)
            if bn == newbname:
                continue
                    
            newname = mbcsEnc(join(dataDir, newbname), "replace")[0]
            if exists(newname):
                # A file with the designated new name of fn already exists
                # -> do nothing
                continue
            
            try:
                rename(fn, newname)
            except (IOError, OSError):
                pass
        
        formatver = 1
        
        # --- WikiPad 1.20beta3 reached (formatver=1, writecompatver=1,
        #         readcompatver=1) ---

    if formatver == 1:
        # remove brackets from all wikiwords in database
        
        # table wikiwords
        dataIn = connwrap.execSqlQuery(
                "select word, created, modified from wikiwords")
        connwrap.execSql("drop table wikiwords")
        connwrap.commit()
        changeTableSchema(connwrap, "wikiwords", 
                TABLE_DEFINITIONS["wikiwords"])
        rebuildIndices(connwrap)
        
        uniqueCtl = {}
        for w, c, m in dataIn:
            w = wikiWordToLabel(w)
            if not uniqueCtl.has_key(w):
                connwrap.execSql("insert into wikiwords(word, created, modified) "
                        "values (?, ?, ?)", (w, c, m))
                uniqueCtl[w] = None

        # table wikirelations
        dataIn = connwrap.execSqlQuery(
                "select word, relation, created from wikirelations")
        connwrap.execSql("drop table wikirelations")
        connwrap.commit()
        changeTableSchema(connwrap, "wikirelations", 
                TABLE_DEFINITIONS["wikirelations"])
        rebuildIndices(connwrap)

        uniqueCtl = {}
        for w, r, c in dataIn:
            w, r = wikiWordToLabel(w), wikiWordToLabel(r)
            if not uniqueCtl.has_key((w, r)):
                connwrap.execSql("insert into wikirelations(word, relation, created) "
                        "values (?, ?, ?)", (w, r, c))
                uniqueCtl[(w, r)] = None

        # table wikiwordprops
        dataIn = connwrap.execSqlQuery(
                "select word, key, value from wikiwordprops")
        connwrap.execSql("drop table wikiwordprops")
        connwrap.commit()
        changeTableSchema(connwrap, "wikiwordprops", 
                TABLE_DEFINITIONS["wikiwordprops"])
        rebuildIndices(connwrap)

        for w, k, v in dataIn:
            connwrap.execSql("insert into wikiwordprops(word, key, value) "
                    "values (?, ?, ?)", (wikiWordToLabel(w), k, v))

        # table todos
        dataIn = connwrap.execSqlQuery(
                "select word, todo from todos")
        connwrap.execSql("drop table todos")
        connwrap.commit()
        changeTableSchema(connwrap, "todos", 
                TABLE_DEFINITIONS["todos"])
        rebuildIndices(connwrap)

        for w, t in dataIn:
            connwrap.execSql("insert into todos(word, todo) "
                    "values (?, ?)", (wikiWordToLabel(w), t))

        formatver = 2

        # --- WikiPad 1.6beta2 reached (formatver=2, writecompatver=2,
        #         readcompatver=2) ---

        
    # Write format information
    for key, value in (
            ("formatver", "2"),  # Version of database format the data was written
            ("writecompatver", "2"),  # Lowest format version which is write compatible
            ("readcompatver", "2"),  # Lowest format version which is read compatible
            ("branchtag", "WikidPad")  # Tag of the WikidPad branch
            ):
        setSettingsValue(connwrap, key, value)

    rebuildIndices(connwrap)
    
    connwrap.commit()
        

        
    
# class WikiDBExistsException(WikiDataException): pass
# class WikiDBExistsException(Exception): pass


"""
Schema changes in WikidPad:

+++ Initial 1.20beta1:


TABLE_DEFINITIONS = {

    "wikiwords": (     # Cache TODO Make essential because of crea. and mod. date
        ("word", t.t),
        ("created", t.t),
        ("modified", t.t)
        ),


    "wikirelations": (     # Cache
        ("word", t.t),
        ("relation", t.t),
        ("created", t.t)   # TODO What is this good for?
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
        ("search", t.t),
        ),
    
    
    "settings": (     # Essential since 1.2beta2
        ("key", t.t),
        ("value", t.t)
        )
    }


+++ 1.20beta1 to 1.20beta2 (formatver=0):
    Table "settings" created:
    
        "settings": (
        ("key", t.t),
        ("value", t.t)
        )

    "search_views" changed to:

        "search_views": (
            ("title", t.t),
            ("datablock", t.t)
            ),
 
++ 1.20beta2 to 1.20beta3 (formatver=1):
    All filenames of wiki files with brackets like e.g. "[Not Camelcase].wiki"
    are renamed to ones without brackets like "Not Camelcase.wiki"

"""
