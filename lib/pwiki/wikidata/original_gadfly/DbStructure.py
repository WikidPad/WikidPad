"""
Module responsible for structural changes to the database
(creating/dropping tables), creation of new DBs and the transition from older
DB formats to the current one
"""


import string, codecs, types, traceback

from os import mkdir, unlink, rename
from os.path import exists, join, split, basename
import glob

import Consts
from pwiki.WikiExceptions import *
from pwiki.StringOps import mbcsDec, mbcsEnc, utf8Enc, utf8Dec, \
        removeBracketsFilename, pathEnc, getFileSignatureBlock, \
        iterCompatibleFilename
from pwiki.SearchAndReplace import SearchReplaceOperation

import gadfly


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

def _dummy(ob):
    return ob


# Connection (and Cursor)-Wrapper to simplify some operations

class ConnectWrap:
    def __init__(self, connection):
        self.__dict__["dbConn"] = connection
        self.__dict__["dbCursor"] = connection.cursor()
        
        self.__dict__["execute"] = self.dbCursor.execute
        # self.__dict__["executemany"] = self.dbCursor.executemany  # TODO Replace by simple implementation
        self.__dict__["commit"] = self.dbConn.commit
        self.__dict__["rollback"] = self.dbConn.rollback
        self.__dict__["fetchone"] = self.dbCursor.fetchone
        self.__dict__["fetchall"] = self.dbCursor.fetchall

        self.__dict__["_defaultValues"] = DEFAULT_VALS

        
    def __setattr__(self, attr, value):
        setattr(self.dbCursor, attr, value)
        
    def __getattr__(self,  attr):
        return getattr(self.dbCursor, attr)

    def readDefaultValues(self):
        self.fillDefaultValues()  # DEBUG ONLY!!!
        result = {}
        entries = self.execSqlQuery(
                "select tablename, field, value from defaultvalues", strConv=False)

        for t, f, v in entries:
            table = result.setdefault(t, {})
            table[f] = v

        self.__dict__["_defaultValues"] = result


    def fillDefaultValues(self):
        """
        Write the global standard default values to database.
        Should be called only during updateDatabase()
        """
        global DEFAULT_VALS, TABLE_DEFINITIONS

        # Remove "defaultvalues" if existing to fill it freshly
        try:
            self.execSql("drop table defaultvalues")
            self.commit()
        except:
            pass

        changeTableSchema(self, "defaultvalues",
                TABLE_DEFINITIONS["defaultvalues"])

        for tn in DEFAULT_VALS.keys():
            for fn in DEFAULT_VALS[tn]:
                self.execSqlInsert("defaultvalues", ("tablename", "field", 
                        "value"), (tn, fn, DEFAULT_VALS[tn][fn]))



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
        strConv -- Should returned bytestrings be seen as UTF8 and converted to
                unicode or instead left as they are?
                If it is a tuple of truth values, each truth value matches
                to one of the columns of the result of db query
        """
        ## print "execSqlQuery sql", sql, repr(params)
        if params:
            self.execSql(sql, params)
        else:
            self.execSql(sql)

        result = self.dbCursor.fetchall()

        if strConv == True:
            result = [tuple(_utf8ToUni(v) for v in row) for row in result]
        elif isinstance(strConv, tuple):
            strConv = [(_utf8ToUni if sc else _dummy) for sc in strConv]
            
            tup = tuple(range(len(strConv)))
            result = [tuple(strConv[i](row[i]) for i in tup) for row in result]

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
            
    def execSqlInsert(self, table, fields, values, tableDefault=None):
        """
        Gadfly-specific function. Since 2.0 it is possible to create default
        values for non-existent fields. Sqlite provides this for free.
        table -- Name of table to insert into
        fields -- sequence of field names (aka column names)
        values -- sequence of values to insert into the fields.
            Must have same length as fields
        tableDefault -- name of entry in defaultValues table to use.
            If None or not given same as table name
        """
        assert len(fields) == len(values)
        if tableDefault is None:
            tableDefault = table

        tableDefs = self._defaultValues.get(tableDefault)
        if tableDefs is not None:
            for k in tableDefs.keys():
                if k not in fields:
                    fields += (k,)
                    values += (tableDefs[k],)

        fieldStr = ", ".join(fields)
        qmStr = ", ".join(["?"] * len(fields))
        self.execSql("insert into %s(%s) values (%s)" % (table, fieldStr, qmStr),
                values)


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
            self.dbCursor = None
            
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
            self.dbConn = None
       


VERSION_DB = 5
VERSION_WRITECOMPAT = 5
VERSION_READCOMPAT = 5


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
    "wikiwords": (     # Essential
        ("word", t.t),
        ("created", t.t),
        ("modified", t.t),
        ("visited", t.t),
        ("filepath", t.t),
        ("filenamelowercase", t.t),
        ("filesignature", t.t),
        ("readonly", t.t),
        ("metadataprocessed", t.t),
        ("presentationdatablock", t.t)
        ),


    "wikirelations": (     # Cache, but main
        ("word", t.t),
        ("relation", t.t),
        ("created", t.t)    # TODO What is this good for?
        ),
    
    
    "wikiwordprops_PRE2_1alpha01": (     # Obsolete
        ("word", t.t),
        ("key", t.t),
        ("value", t.t)
        ),


    "wikiwordattrs": (     # Cache, but main
        ("word", t.t),
        ("key", t.t),
        ("value", t.t),
        ),

   
    "todos_PRE2_1alpha01": (     # Obsolete
        ("word", t.t),
        ("todo", t.t),
        ),


    "todos": (     # Cache, but main
        ("word", t.t),
        ("key", t.t),
        ("value", t.t),
        ),


    "search_views": (     # Deleted since 2.0alpha1. For updating format only 
        ("title", t.t),
        ("datablock", t.t)
        ),

    
    "settings": (     # Essential since 1.2beta2
        ("key", t.t),
        ("value", t.t)
        ),

    
    "defaultvalues": (   # Essential since 2.0alpha1
        ("tablename", t.t),
        ("field", t.t),
        ("value", t.t)
        ),


    "wikiwordmatchterms": (   # Essential since 2.0alpha1
        ("matchterm", t.t),
#         ("matchtermnormcase", t.t),  # Does not apply for Gadfly
        ("type", t.t),
        ("word", t.t),
        ("firstcharpos", t.t),
        ("charlength", t.t)  # Length of the target
        ),


    "datablocks": (   # Essential since 2.0alpha1
        ("unifiedname", t.t),
        ("data", t.t)
        ),


    "datablocksexternal": (   # Essential since 2.0alpha1
        ("unifiedname", t.t),
        ("filepath", t.t),
        ("filenamelowercase", t.t),
        ("filesignature", t.t)
        )
    }


# Recycling t for setting of default values

t.r = 0.0
t.i = 0
t.imo = -1
t.t = u""
t.b = ""


DEFAULT_VALS = {
    "wikiwords": {
        "word": t.t,
        "created": t.r,
        "modified": t.r,
        "visited": t.r,
        "filepath": t.t,
        "filenamelowercase": t.t,
        "filesignature": t.b,
        "readonly": t.i,
        "metadataprocessed": t.i,
        "presentationdatablock": t.b
        },
    
    "wikirelations": {
        "word": t.t,
        "relation": t.t,
        },
    
    
    "wikiwordprops_PRE2_1alpha01": {
        "word": t.t,
        "key": t.t,
        "value": t.t,
        },
    
    "wikiwordattrs": {
        "word": t.t,
        "key": t.t,
        "value": t.t,
        },

    
    "todos_PRE2_1alpha01": {
        "word": t.t,
        "todo": t.t,
        },
        
    
    "todos": {
        "word": t.t,
        "key": t.t,
        "value": t.t,
        },


    "settings": {
        "value": t.t
        },
    
    
    "wikiwordmatchterms": {
        "matchterm": t.t,
        # "matchtermnormcase": t.t,
        "type": t.i,
        "word": t.t,
        "firstcharpos": t.imo,
        "charlength": t.t,
        },


    "datablocks": {
        "unifiedname": t.t,
        "data": t.b
        },


    "datablocksexternal": {
        "unifiedname": t.t,
        "filepath": t.t,
        "filenamelowercase": t.t,
        "filesignature": t.b
        }
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
    connwrap.commit()

    connwrap.execSqlNoError("drop index wikiwordprops_word")
    connwrap.execSqlNoError("drop index wikiwordprops_keyvalue")

    connwrap.execSqlNoError("drop index wikiwords_pkey")
    connwrap.execSqlNoError("drop index wikiwordmatchterms_matchterm")
    connwrap.execSqlNoError("drop index wikirelations_pkey")
    connwrap.execSqlNoError("drop index settings_pkey")
    connwrap.execSqlNoError("drop index search_views_pkey")
    connwrap.execSqlNoError("drop index wikirelations_word")
    connwrap.execSqlNoError("drop index wikiwordattrs_word")
    connwrap.execSqlNoError("drop index datablocks_unifiedname")
    connwrap.execSqlNoError("drop index datablocksexternal_unifiedname")
        
    connwrap.execSqlNoError("create unique index wikiwords_pkey on wikiwords(word)")
    connwrap.execSqlNoError("create index wikiwordmatchterms_matchterm on wikiwordmatchterms(matchterm)")
    connwrap.execSqlNoError("create unique index wikirelations_pkey on wikirelations(word, relation)")
    connwrap.execSqlNoError("create unique index settings_pkey on settings(key)")
    connwrap.execSqlNoError("create index wikirelations_word on wikirelations(word)")
    connwrap.execSqlNoError("create index wikiwordattrs_word on wikiwordattrs(word)")
    connwrap.execSqlNoError("create index datablocks_unifiedname on datablocks(unifiedname)")
    connwrap.execSqlNoError("create index datablocksexternal_unifiedname on datablocksexternal(unifiedname)")

    connwrap.commit()


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

#     print "changeTableSchema1", repr(tablename), repr(schema)

    # Build the sql command to create the table with new schema (needed later)

    newtabletyped = ", ".join(map(lambda sc: "%s %s" % sc[:2], schema))
    newtableselect = ", ".join(map(lambda sc: sc[0], schema))

    newtablecreate = "create table %s (" % tablename
    newtablecreate += newtabletyped
    newtablecreate += ")"


    # Test if table already exists

    tn = connwrap.execSqlQuerySingleItem(
            "select table_name from __table_names__ where table_name='%s'" %
            tablename.upper())

    if tn is None:
        # Does not exist, so simply create
        connwrap.commit()
        connwrap.execSql(newtablecreate)
        connwrap.commit()        
        return True

    # Table exists, so retrieve list of columns
    oldcolumns = connwrap.execSqlQuerySingleColumn(
            "select COLUMN_NAME from __columns__ where TABLE_NAME = '%s'" %
            tablename.upper())
    
    oldcolumns = map(string.upper, oldcolumns)
    
    # Which columns have old and new schema in common?    
    intersect = []
    for sc in schema:
        n, d = sc[:2]
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

    if len(intersect) > 0:
        newinsertcols = intersect[:]
        newinsertvalues = ["?" for i in intersect]

        for sc in schema:
            n, t = sc[:2]
            n = n.upper()

            if n in intersect:
                continue

            if len(sc) > 2:
                df = sc[2]
            else:
                try:
                    dob = DEFAULT_VALS[tablename][n.lower()]
                    df = {0: "0", 0.0:"0.0", -1:"-1"}[dob]
                except KeyError:
                    df = None

            if df is None:
                if t.lower() == "varchar":
                    df = "''"

            newinsertcols.append(n)
            newinsertvalues.append(df)

        newinsertcols = ", ".join(newinsertcols)
        newinsertvalues = ", ".join(newinsertvalues)

            
#             n = n.upper()
#             typemap[n] = t
            
#         intersecttyped = ["%s %s" % (n, typemap[n]) for n in intersect]
#         intersecttyped = ", ".join(intersecttyped)
        
        intersectselect = ", ".join(intersect)
        
        connwrap.commit()        
        connwrap.execSql("create table tmptable(%s)" % newtabletyped)
        data = connwrap.execSqlQuery("select %s from %s" %
                (intersectselect, tablename), strConv=False)

        for row in data:
            connwrap.execSql("insert into tmptable (%s) values (%s)" %
                    (newinsertcols, newinsertvalues), row)
        
        connwrap.execSql("drop table %s" % tablename)
        connwrap.execSql(newtablecreate)
        connwrap.commit()        
        connwrap.execSql("insert into %s(%s) select %s from tmptable" %
                (tablename, newtableselect, newtableselect))
        connwrap.execSql("drop table tmptable")
        connwrap.commit()        
    else:
        # Nothing in common -> delete old, create new
        connwrap.commit()        
        connwrap.execSql("drop table %s" % tablename)
        connwrap.commit()        
        connwrap.execSql(newtablecreate)
        connwrap.commit()


    # TODO: Does this something?

    # Table exists, so retrieve list of columns
    oldcolumns = connwrap.execSqlQuerySingleColumn(
            "select COLUMN_NAME from __columns__ where TABLE_NAME = '%s'" %
            tablename.upper())
    
    oldcolumns = map(string.upper, oldcolumns)
    
    return True


def createWikiDB(wikiName, dataDir, overwrite=False):
    """
    creates the initial db
    Warning: If overwrite is True, a previous file will be deleted!
    """
    dbfile = join(dataDir, "wiki.sli")
    if (not exists(pathEnc(dbfile)) or overwrite):
        if (not exists(pathEnc(dataDir))):
            mkdir(pathEnc(dataDir))
        else:
            if exists(pathEnc(dbfile)) and overwrite:
                unlink(pathEnc(dbfile))

        # create the database
        connection = gadfly.gadfly()
        connection.startup("wikidb", dataDir)
        connwrap = ConnectWrap(connection)

        try:
            for tn in MAIN_TABLES:
                changeTableSchema(connwrap, tn, TABLE_DEFINITIONS[tn])
                
            for key, value in (
                    ("formatver", str(VERSION_DB)),  # Version of database format the data was written
                    ("writecompatver", str(VERSION_WRITECOMPAT)),  # Lowest format version which is write compatible
                    ("readcompatver", str(VERSION_READCOMPAT)),  # Lowest format version which is read compatible
                    ("branchtag", "WikidPad"),  # Tag of the WikidPad branch
                    ("locale", "-") # Locale for cached wordnormcase column. '-': column invalid
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
        raise WikiDBExistsException(
                _(u"database already exists at location: %s") % dataDir)



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


def oldWikiWordToLabel(word):
    """
    Strip '[' and ']' if non camelcase word and return it
    """
    if word.startswith(u"[") and word.endswith(u"]"):
        return word[1:-1]
    return word



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
        return 1, _(u"Update needed")
        
    if getSettingsValue(connwrap, "branchtag") != "WikidPad":
        return 2, _(u"Database has unknown format branchtag='%s'") \
                % getSettingsValue(connwrap, "branchtag")

    formatver = getSettingsInt(connwrap, "formatver")
    writecompatver = getSettingsInt(connwrap, "writecompatver")

    if writecompatver > VERSION_WRITECOMPAT:
        # TODO: Check compatibility
        
        return 2, _(u"Database has unknown format version='%i'") \
                % formatver
                
    if formatver < VERSION_DB:
        return 1, _(u"Update needed, current format version='%i'") \
                % formatver
        
    return 0, _(u"Database format is up to date")



def updateDatabase(connwrap, dataDir, pagefileSuffix):
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
#             print "dropping index wikiwordprops_pkey"
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

            try:
                # Raises exception if search is invalid
                searchOp.rebuildSearchOpTree()
            except:
                continue

            datablock = searchOp.getPackedSettings()

            connwrap.execSql(
                "insert into search_views(title, datablock) "+\
                "values (?, ?)", (searchOp.getTitle(), datablock))

        formatver = 0
        
        changeTableSchema(connwrap, "settings", 
                TABLE_DEFINITIONS["settings"])
        
        # Write initial format versions
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
            if exists(pathEnc(newname)):
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
            w = oldWikiWordToLabel(w)
            if not uniqueCtl.has_key(w):
                connwrap.execSqlInsert("wikiwords", ("word", "created", 
                        "modified", "presentationdatablock"),
                        (w, c, m, ""))
#                 connwrap.execSql("insert into wikiwords(word, created, modified) "
#                         "values (?, ?, ?)", (w, c, m))
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
            w, r = oldWikiWordToLabel(w), oldWikiWordToLabel(r)
            if not uniqueCtl.has_key((w, r)):
                connwrap.execSqlInsert("wikirelations", ("word", "relation", 
                        "created"), (w, r, c))
#                 connwrap.execSql("insert into wikirelations(word, relation, created) "
#                         "values (?, ?, ?)", (w, r, c))
                uniqueCtl[(w, r)] = None

        # table wikiwordprops
        dataIn = connwrap.execSqlQuery(
                "select word, key, value from wikiwordprops")
        connwrap.execSql("drop table wikiwordprops")
        connwrap.commit()
        changeTableSchema(connwrap, "wikiwordprops", 
                TABLE_DEFINITIONS["wikiwordprops_PRE2_1alpha01"])
        rebuildIndices(connwrap)

        for w, k, v in dataIn:
            connwrap.execSqlInsert("wikiwordprops", ("word", "key", 
                    "value"), (oldWikiWordToLabel(w), k, v),
                    tableDefault="wikiwordprops_PRE2_1alpha01")
#             connwrap.execSql("insert into wikiwordprops(word, key, value) "
#                     "values (?, ?, ?)", (oldWikiWordToLabel(w), k, v))

        # table todos
        dataIn = connwrap.execSqlQuery(
                "select word, todo from todos")
        connwrap.execSql("drop table todos")
        connwrap.commit()
        changeTableSchema(connwrap, "todos", 
                TABLE_DEFINITIONS["todos_PRE2_1alpha01"])
        rebuildIndices(connwrap)

        for w, t in dataIn:
            connwrap.execSqlInsert("todos", ("word", "todo"),
                    (oldWikiWordToLabel(w), t),
                    tableDefault="todos_PRE2_1alpha01")
#             connwrap.execSql("insert into todos(word, todo) "
#                     "values (?, ?)", (oldWikiWordToLabel(w), t))

        formatver = 2

        # --- WikiPad 1.6beta2 reached (formatver=2, writecompatver=2,
        #         readcompatver=2) ---

    if formatver == 2:
        changeTableSchema(connwrap, "wikiwords", 
                TABLE_DEFINITIONS["wikiwords"])
                
        # --- WikiPad 1.8beta1 reached (formatver=3, writecompatver=3,
        #         readcompatver=2) ---

        formatver = 3
        

    if formatver == 3:

        # Update "wikiwords" schema and create new tables
        for tn in ("wikiwords", "wikiwordmatchterms", "datablocks",
                "datablocksexternal", "defaultvalues"):
            changeTableSchema(connwrap, tn, TABLE_DEFINITIONS[tn])
        
        # (Re)fill "defaultvalues" and read them into connection wrapper
        connwrap.fillDefaultValues()
        connwrap.readDefaultValues()


        # Transfer "search_views" data to "datablocks" table
        searches = connwrap.execSqlQuery(
                "select title, datablock from search_views",
                strConv=(True, False))

        for title, data in searches:
            connwrap.execSql(
                "insert into datablocks(unifiedname, data) "+\
                "values (?, ?)", (u"savedsearch/" + title, data))

        connwrap.execSql("drop table search_views")

        allWords = connwrap.execSqlQuerySingleColumn("select word from wikiwords")
        
        # Divide into functional and wiki pages
        wikiWords = []
        funcWords = []
        for w in allWords:
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
                    "where word = ?", (filename, filename.lower(), filesig,
                    wikiWord))

        # Move functional pages to new table "datablocksexternal" and rename them
        for funcWord in funcWords:
            if funcWord not in (u"[TextBlocks]", u"[PWL]", u"[CCBlacklist]"):
                continue # Error ?!
            
            unifName = u"wiki/" + funcWord[1:-1]
            fullPath = join(dataDir, funcWord + pagefileSuffix)
            
            icf = iterCompatibleFilename(unifName, u".data")
            
            for i in range(10):  # Actual "while True", but that's too dangerous
                newFilename = icf.next()
                newPath = join(dataDir, newFilename)

                if exists(pathEnc(newPath)):
                    # A file with the designated new name of fn already exists
                    # -> do nothing
                    continue

                try:
                    rename(pathEnc(fullPath), pathEnc(newPath))

                    # We don't use coarsening here for the FSB because a different
                    # coarsening setting can't exist for the old wiki format
                    connwrap.execSqlInsert("datablocksexternal", ("unifiedname",
                            "filepath", "filenamelowercase", "filesignature"),
                            (unifName, newFilename, newFilename.lower(),
                            getFileSignatureBlock(newPath)))
                    connwrap.execSql("delete from wikiwords where word = ?",
                            (funcWord,))
                    break
                except (IOError, OSError):
                    traceback.print_exc()
                    continue


        # --- WikiPad 2.0alpha1 reached (formatver=4, writecompatver=4,
        #         readcompatver=4) ---

        formatver = 4
        
    if formatver == 4:
        # (Re)fill "defaultvalues" and read them into connection wrapper
        connwrap.fillDefaultValues()
        connwrap.readDefaultValues()

        # Recreate table "todos" with new schema
        connwrap.execSql("drop table todos")
        changeTableSchema(connwrap, "todos", TABLE_DEFINITIONS["todos"])

        # Rename table "wikiwordprops" to "wikiwordattrs"
        changeTableSchema(connwrap, "wikiwordattrs", TABLE_DEFINITIONS["wikiwordattrs"])
        connwrap.execSql("insert into wikiwordattrs(word, key, value) "
                "select word, key, value from wikiwordprops")
        connwrap.execSql("drop table wikiwordprops")

        for tn in ("wikirelations", "wikiwordmatchterms"):
            changeTableSchema(connwrap, tn, TABLE_DEFINITIONS[tn])

        # Mark all wikiwords to need a rebuild
        connwrap.execSql("update wikiwords set metadataprocessed=0")

        formatver = 5

    # --- WikiPad 2.1alpha.1 reached (formatver=5, writecompatver=5,
    #         readcompatver=5) ---



    # Write format information
    for key, value in (
            ("formatver", str(VERSION_DB)),  # Version of database format the data was written
            ("writecompatver", str(VERSION_WRITECOMPAT)),  # Lowest format version which is write compatible
            ("readcompatver", str(VERSION_READCOMPAT)),  # Lowest format version which is read compatible
            ("branchtag", "WikidPad"),  # Tag of the WikidPad branch
            ("locale", "-") # Locale for cached wordnormcase column. '-': column invalid
            ):
        setSettingsValue(connwrap, key, value)

    rebuildIndices(connwrap)
    
    connwrap.commit()
        

def updateDatabase2(connwrap):
    """
    Second update function. Called even when database version is current.
    Performs further updates
    """
    try:
        setSettingsValue(connwrap, "lastwritever", str(VERSION_DB))
        
        # Write which program version at last wrote to database
        setSettingsValue(connwrap, "lastwriteprogver.branchtag", Consts.VERSION_TUPLE[0])
        setSettingsValue(connwrap, "lastwriteprogver.major", str(Consts.VERSION_TUPLE[1]))
        setSettingsValue(connwrap, "lastwriteprogver.minor", str(Consts.VERSION_TUPLE[2]))
        setSettingsValue(connwrap, "lastwriteprogver.sub", str(Consts.VERSION_TUPLE[3]))
        setSettingsValue(connwrap, "lastwriteprogver.patch", str(Consts.VERSION_TUPLE[4]))
    except IOError:
        pass

        
    
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

++ 1.6beta1 to 1.6beta2 (formatver=2):
    Brackets are removed from all wikiwords stored in the database

++ 1.7beta8 to 1.8beta1 (formatver=3):

Table "wikiwords" changed to:
        "wikiwords": (
            ("word", t.t),
            ("created", t.t),
            ("modified", t.t),
            ("presentationdatablock", t.t),
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


++ 1.9final to 2.0alpha1 (formatver=4):
    
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


++ 2.0 to 2.1alpha1 (formatver=5):
    
    Table "todos" modified:
        "todo" column replaced by "key" and "value" columns

    Table "wikiwordprops" renamed to "wikiwordattrs"
    
    Table "wikiwordmatchterms":
        charlength: Integer. Length of the selection whose position is given in
            firstcharpos. Invalid if firstcharpos is -1.

"""
