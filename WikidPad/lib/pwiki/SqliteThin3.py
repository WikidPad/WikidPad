# -*- coding: ISO-8859-1 -*-

import codecs, types, traceback, sys, os, platform, re
from ctypes import *



# Error values

SQLITE_OK         =  0   # Successful result
SQLITE_ERROR      =  1   # SQL error or missing database
SQLITE_INTERNAL   =  2   # An internal logic error in SQLite
SQLITE_PERM       =  3   # Access permission denied
SQLITE_ABORT      =  4   # Callback routine requested an abort
SQLITE_BUSY       =  5   # The database file is locked
SQLITE_LOCKED     =  6   # A table in the database is locked
SQLITE_NOMEM      =  7   # A malloc() failed
SQLITE_READONLY   =  8   # Attempt to write a readonly database
SQLITE_INTERRUPT  =  9   # Operation terminated by sqlite_interrupt()
SQLITE_IOERR      = 10   # Some kind of disk I/O error occurred
SQLITE_CORRUPT    = 11   # The database disk image is malformed
SQLITE_NOTFOUND   = 12   # (Internal Only) Table or record not found
SQLITE_FULL       = 13   # Insertion failed because database is full
SQLITE_CANTOPEN   = 14   # Unable to open the database file
SQLITE_PROTOCOL   = 15   # Database lock protocol error
SQLITE_EMPTY      = 16   # (Internal Only) Database table is empty
SQLITE_SCHEMA     = 17   # The database schema changed
SQLITE_TOOBIG     = 18   # Too much data for one row of a table
SQLITE_CONSTRAINT = 19   # Abort due to contraint violation
SQLITE_MISMATCH   = 20   # Data type mismatch
SQLITE_MISUSE     = 21   # Library used incorrectly
SQLITE_NOLFS      = 22   # Uses OS features not supported on host
SQLITE_AUTH       = 23   # Authorization denied

SQLITE_ROW        = 100  # sqlite_step() has another row ready
SQLITE_DONE       = 101  # sqlite_step() has finished executing


# Memory handling values for bind_*

SQLITE_STATIC = c_void_p(0)
SQLITE_TRANSIENT = c_void_p(-1)


# Column (more precisely value-) types, returned by _SqliteStatement3.column_type()

SQLITE_INTEGER = 1
SQLITE_FLOAT   = 2
SQLITE_TEXT    = 3
SQLITE_BLOB    = 4
SQLITE_NULL    = 5


SQLITE_UTF8    = 1
SQLITE_UTF16BE = 2
SQLITE_UTF16LE = 3
SQLITE_UTF16   = 4


def isLinux():
    """
    Return if working on Linux system
    """
    try:
        return os.uname()[0] == "Linux"
    except AttributeError:
        return False



class Binary:
    "String wrapper to distinguish between blob and text for bind_auto"

    def __init__(self, s):
        self.__dict__["data"] = s

    def __getattr__(self, attr):
        return getattr(self.data, attr)

    def __setattr__(self, attr, val):
        return setattr(self.data, attr, val)


class SqliteError3(Exception):
    "Default exception"
    def __init__(self, err):
        self.err = err

    def __str__(self):
        return "SqliteError "+str(self.err)


if isLinux():
    if sys.hexversion >= 0x02050000:
        _dll = CDLL("libsqlite3.so.0")
    else:
        _dll = CDLL("libsqlite3.so")
elif platform.uname()[0] == "Darwin":
    # Mac OS 9 (or 9.1.0 specifically?)
    _dll = CDLL("libsqlite3.0.dylib")
else:
    _dll = cdll.sqlite3



utf8Encode = codecs.getencoder("UTF8")
utf8Decode = codecs.getdecoder("UTF8")

isoLatin1Decoder = codecs.getdecoder("iso-8859-1")



def stdToUtf8(s):
    if type(s) is str:
        return utf8Encode(s)[0]
    else:
        return utf8Encode(isoLatin1Decoder(s, "surrogateescape")[0],
                "surrogateescape")[0]


def utf8Enc(s):
    if isinstance(s, str):
        return utf8Encode(s, "surrogateescape")[0]
    else:
        return s


def stdErrHandler(err):
    if not err in (SQLITE_OK, SQLITE_ROW, SQLITE_DONE):
        raise SqliteError3(err)

def vpId(o):
    """
    Should be used only internally here
    """
    return c_void_p(id(o)).value
    
    
def llId(o):
    """
    Should be used instead of id(o) to avoid conversion problems.
    Returns a long value guaranteed to fit into signed long long 64bit data type.
    (At least until 128bit CPUs are used :-) )
    """
    return c_longlong(id(o)).value
    

# This dictionary holds python objects which can't be handled
# as sqlite functions or function parameters directly
_sqliteTransObjects = {}  # Dictionary of type {<llId or vpId of object>: <object>}


def addTransObject(o):
    """
    Enters an arbitrary python object into the transfer
    table and returns its llId (long value unique for object during
    its lifetime).
    """
#     if type(o) is int:
#         return None  # TODO Other reaction?

    result = llId(o)
    _sqliteTransObjects[result] = o
    return result


def getTransObject(i):
    return _sqliteTransObjects.get(i, None)


def delTransObject(o):
    """
    Delete object o from transfer table. If it wasn't in the table nothing
    happens.
    
    Neither refcounting nor other thread safety measures are used!
    """
#     if not type(io) is int:
    io = llId(o)
    
    try:
        del _sqliteTransObjects[io]
    except KeyError:
        pass
        




# ----------  Bind functions  ----------

def bind_blob(stmt, parno, data):
    """
    Bind blob value to parameter in sql-statement
    stmt --- _Statement object to bind to
    parno -- parameter number (starting with 1)
    data -- string with blob data or Blob object
    """
    if isinstance(data, Binary):
        data = data.data

    stmt.errhandler(_dll.sqlite3_bind_blob(stmt._stmtpointer, parno, c_char_p(data), len(data), SQLITE_TRANSIENT))


def bind_text(stmt, parno, data):
    """
    See bind_blob for description.
    """
    stmt.errhandler(_dll.sqlite3_bind_text(stmt._stmtpointer, parno, c_char_p(utf8Enc(data)), len(data), SQLITE_TRANSIENT))


def bind_null(stmt, parno, data=None):
    """
    See bind_blob for description.
    The dummy parameter data ensures that all bind_* have the same interface
    """
    stmt.errhandler(_dll.sqlite3_bind_null(stmt._stmtpointer, parno))


def bind_double(stmt, parno, data):
    """
    See bind_blob for description
    """
    stmt.errhandler(_dll.sqlite3_bind_double(stmt._stmtpointer, parno, c_double(data)))


def bind_int(stmt, parno, data):
    """
    See bind_blob for description
    """
    stmt.errhandler(_dll.sqlite3_bind_int(stmt._stmtpointer, parno, c_int(data)))


def bind_int64(stmt, parno, data):
    """
    See bind_blob for description
    """
    stmt.errhandler(_dll.sqlite3_bind_int64(stmt._stmtpointer, parno, c_longlong(data)))




_AUTO_BIND_CONVERTS = {
        bytes: "text",
        str: "text",
        int: "int64",
        float: "double",
        type(None): "null",
        memoryview: "blob",
        Binary: "blob"
    }



def find_bindfct(data):
    """
    Return right binder for data or None
    """
    fn = _AUTO_BIND_CONVERTS.get(type(data), None)
    
    if fn is not None:
        return globals()["bind_" + fn]   # getattr(_module, "bind_"+fn)
    else:
        if isinstance(data, Binary):
            return bind_blob

    return None



def def_bind_fctfinder(stmt, parno, data):
    return find_bindfct(data)



# ----------  Column functions  ----------


def column_blob(stmt, col):
    """
    Retrieve a blob object as Blob from a db row after a SELECT statement was performed
    col -- zero based column index
    """
    length = _dll.sqlite3_column_bytes(stmt._stmtpointer, col)
    if length == 0:
        return ""

    _dll.sqlite3_column_blob.restype = POINTER(c_char * length)  # TODO: Thread safety
    
    return _dll.sqlite3_column_blob(stmt._stmtpointer, col).contents.raw   # Return Blob instead?


def column_text_raw(stmt, col):
    """
    Retrieve a text object as bytes from a db row after a SELECT statement was performed
    col -- zero based column index
    """
    length = _dll.sqlite3_column_bytes(stmt._stmtpointer, col)
    if length == 0:
        return b""

    _dll.sqlite3_column_text.restype = POINTER(c_char * length)  # TODO: Thread safety
    
    return _dll.sqlite3_column_text(stmt._stmtpointer, col).contents.raw


def column_text(stmt, col):
    """
    Retrieve a text object as unistring (assuming that text bytes were UTF-8
    encoded) from a db row after a SELECT statement was performed
    col -- zero based column index
    """
    return utf8Decode(column_text_raw(stmt, col), "surrogateescape")[0]


def column_null(stmt, col):
    """
    Returns always None.
    """
    return None
    




# The remaining column functions are created by this template

for restype, fctname in (
        (c_int, "column_bytes"),
        (c_int, "column_bytes16"),
        (c_double, "column_double"),
        (c_int, "column_int"),
        (c_longlong, "column_int64"),
        (c_int, "column_type"),
        (c_char_p, "column_decltype"),
        (c_char_p, "column_name") ):


    exec("""
    
def %s(stmt, col):
    "Retrieve a column"
    return _dll.sqlite3_%s(stmt._stmtpointer, c_int(col))  # .value ?

""" % (fctname, fctname))
    
    
    getattr(_dll, "sqlite3_"+fctname).restype = restype



AUTO_COLUMN_CONVERTS = {
        SQLITE_TEXT: column_text,
        SQLITE_INTEGER: column_int64,
        SQLITE_FLOAT: column_double,
        SQLITE_BLOB: column_blob,
        SQLITE_NULL: column_null
    }

   
   
    
def def_column_fctfinder(stmt, col):
    """
    Default fctfinder for _SqliteStatement3.column_typefuncs and
        column_auto
    stmt -- statement object
    col -- column number
    """
    return AUTO_COLUMN_CONVERTS[stmt.column_type(col)]
    


class PresetColFctfinder:
    """
    Create a column functionfinder which has for each column a preset
    type.
    """
    def __init__(self, preset):
        """
        preset -- Sequence of type constants (SQLITE_*) or column functions,
            one for each column
        """
        self.presetFcts = [AUTO_COLUMN_CONVERTS.get(p, p) for p in preset]
    
    def __call__(self, stmt, col):
        return self.presetFcts[col]



def getLibVersion():
    """
    Retrieve sqlite version as bytestring
    """
    _dll.sqlite3_libversion.restype = c_char_p

    return utf8Decode(_dll.sqlite3_libversion())[0]



# TODO: Import functions as methods

class _SqliteStatement3:
    """ A statement. You should not try to create them directly, instead
        call SqliteDb3.prepare to retrieve one.
    """
    def __init__(self, stmt, errhandler = stdErrHandler):
        self._stmtpointer = stmt
        self.errhandler = errhandler

    def __del__(self):
        self.finalize()

    def close(self):
        """ Synonym to finalize """
        self.finalize()

    def finalize(self):
        if self._stmtpointer:
            self.errhandler(_dll.sqlite3_finalize(self._stmtpointer))

        self._stmtpointer = None
        
        
    def bind_auto(self, parno, data, fctfinder=None):
        """
        Choose bind type by type of data automatically.
        (strings are mapped to text type, blobs not supported)
        """
        try:
            if fctfinder is None:
                find_bindfct(data)(self, parno, data)
            else:
                fctfinder(self, parno, data)(self, parno, data)
                
        except AttributeError:
            raise TypeError("SqliteThin3: bind_auto: Type %s can't be bound" % repr(type(param)))


    def bind_auto_multi(self, datas, fctfinder=None):
        """
        Bind multiple parameters (beginning with 1)
        """
        first=1  # TODO: as dict parameter
        
        for i in range(first, len(datas)+first):
            self.bind_auto(i, datas[i-1], fctfinder)


#     def bind_hint(self, datas, hint):
#         first=1  # TODO: as dict parameter
#         
#         for i in range(first, len(datas)+first):
#             hint[i-1](self, i, datas[i-1])
# 
# 
#     def bind_typefuncs(self, datas, fctfinder=None):
#         first=1  # TODO: as dict parameter
#         
#         if fctfinder is None:
#             return map(find_bindfct, datas)
#         else:
#             return map(lambda i: fctfinder(self, i, datas[i-1]),
#                     range(first, len(datas)+first))

   
    def column_count(self):
        """
        Return number of columns of this statement
        """
        return _dll.sqlite3_column_count(self._stmtpointer)


    def column_auto(self, col, fctfinder = None):
        """
        Retrieves a column automatically with the right type
        """
        if fctfinder is None:
            t = self.column_type(col)
    
            return AUTO_COLUMN_CONVERTS[t](self, col)
        else:
            return fctfinder(self, col)(self, col)


    def column_auto_multi(self, fctfinder = None):
        """
        Retrieve all columns of a row as list
        """
        return [self.column_auto(col, fctfinder) \
                for col in range(0, self.column_count())]

    def column_hint_multi(self, hint):
        """
        hint -- List of the typefuncs as returned by column_typefuncs
        """
        return [hint[col](self, col) for col in range(len(hint))]


    def column_hint_multi_fast(self, hint, arr):
        """
        hint -- List of the typefuncs as returned by column_typefuncs
        arr -- with length >= hint to use for result instead of creating a new one
        """
        for col in range(len(hint)):
            arr[col] = hint[col](self, col)
            
        return arr


    def column_typefuncs(self, fctfinder = None):
        """
        Retrieve a list of the typefuncs used for converting the column values
        as it is done by column_auto_multi. If for all columns each column has
        the same type for all rows, use this to retrieve the converters and use
        column_hint_multi to retrieve the individual column without detecting
        types for each row again.

        This function can only be called after a successful call to step()
        
        fctfinder -- a callable fctfinder(stmt, col) which returns a columngetter
                or None
        """
        if fctfinder is None:
            return [AUTO_COLUMN_CONVERTS[self.column_type(col)] \
                    for col in range(0, self.column_count())]
        else:
            return [fctfinder(self, col) \
                    for col in range(0, self.column_count())]
        
    def column_type(self, col):
        return column_type(self, col)

    def step(self):
        """
        After an SQL query has been prepared, this function must be
        called one or more times to execute the statement.
        Returns true if a new row was retrieved, false if statement
        is done or isn't a SELECT-statement
        """
         
        err = _dll.sqlite3_step(self._stmtpointer)
        if err == SQLITE_ROW: return True
        elif err == SQLITE_DONE: return False

        self.errhandler(err)

    def reset(self):
        self.errhandler(_dll.sqlite3_reset(self._stmtpointer))

    def column_name_multi(self):
        return [column_name(self, col) for col in range(0, self.column_count())]




_dll.sqlite3_last_insert_rowid.restype = c_longlong
_dll.sqlite3_errmsg.restype = c_char_p


class SqliteDb3:
    def __init__(self, dbname=None, errhandler = stdErrHandler):
        self._dbpointer = None
        self.errhandler = errhandler

        if dbname:
            self.open(dbname)


    def open(self, dbname):
        if self._dbpointer:
            assert 0  # TODO: Err handling

        obref = c_void_p()
        # This line works around a bug in sqlite. Might need change if bug
        # is fixed
        self.errhandler(_dll.sqlite3_open(c_char_p(utf8Enc(dbname)), byref(obref)))

        self._dbpointer = obref


    def __del__(self):
        self.close()


    def close(self):
        if self._dbpointer:
            self.errhandler(_dll.sqlite3_close(self._dbpointer))

        self._dbpointer = None


    def prepare(self, sql):
        """
        Prepares a statement out of the sql code.
        Only one sql-command in the sql string is allowed here!
        """
        stmtref = c_void_p()
        
#         utf8sql = stdToUtf8(sql)
#         ccpUtf8Sql = c_char_p(utf8sql)
# 
#         prep = _dll.sqlite3_prepare(self._dbpointer, ccpUtf8Sql,
#                 len(sql), byref(stmtref), 0)
#         
# 
#         self.errhandler(prep)
        self.errhandler(_dll.sqlite3_prepare(self._dbpointer, c_char_p(stdToUtf8(sql)),
                len(sql), byref(stmtref), 0))

        return _SqliteStatement3(stmtref, self.errhandler)


    def execute(self, sql):
        self.errhandler(_dll.sqlite3_exec(self._dbpointer, c_char_p(stdToUtf8(sql)),
                0, 0, 0))

    def busy_timeout(self, ms):
        """
        Set number of milliseconds to wait if a table is locked.
        A nonpositive value turns off all busy handlers
        """
        _dll.sqlite3_busy_timeout(self._dbpointer, c_int(ms))


    def last_insert_rowid(self):
        return _dll.sqlite3_last_insert_rowid(self._dbpointer)
        
    def get_autocommit(self):
        """
        Is connection in autocommit mode (at startup or between 'COMMIT|ROLLBACK'
        and 'BEGIN')?
        """
        return _dll.sqlite3_get_autocommit(self._dbpointer)
        
    def changes(self):
        """
        Return number of affected rows of last INSERT, UPDATE, or DELETE
        statement
        """
        return _dll.sqlite3_changes(self._dbpointer)

    
    def errmsg(self):
        """
        Return English error message for most recent API call (as unistring)
        """
        return _dll.sqlite3_errmsg(self._dbpointer).decode("utf-8",
                "surrogateescape")
   
   
    # TODO Support deletion
    def create_function(self, funcname, nArg, func, textRep=SQLITE_UTF8):
        _sqliteTransObjects[c_void_p(id(func)).value] = func

        self.errhandler(_dll.sqlite3_create_function(self._dbpointer, 
                utf8Enc(funcname), c_int(nArg), c_int(textRep), c_void_p(id(func)),
                _FUNC_CALLBACK, None, None))





# ----------  User defined functions  ----------

# ----------  result functions  ----------

class _Context:
    """
    Wrapper for an sqlite context, needed for user-defined functions.
    You should not create an object yourself, it will be created automatically
    when calling a user-defined function.
    
    A context does not provide *_auto functions nor provides it an errorhandler.
    """
    
    def __init__(self, ptr):
        self._contextpointer = c_void_p(ptr)

    def result_blob(self, data):
        """
        Set blob value as result of a user-defined function
        data -- string with blob data or Blob object
        """
        if isinstance(data, Binary):
            data = data.data
    
        _dll.sqlite3_result_blob(self._contextpointer, c_char_p(data), len(data), SQLITE_TRANSIENT)
    
    
    def result_text(self, data):
        """
        See result_blob for description.
        """
        _dll.sqlite3_result_text(self._contextpointer, c_char_p(data), len(data), SQLITE_TRANSIENT)
    
    
    def result_null(self, data=None):
        """
        See result_blob for description.
        The dummy parameter data ensures that all result_* have the same interface
        """
        _dll.sqlite3_result_null(self._contextpointer)
    
    
    def result_double(self, data):
        """
        See result_blob for description
        """
        _dll.sqlite3_result_double(self._contextpointer, c_double(data))
    
    
    def result_int(self, data):
        """
        See result_blob for description
        """
        _dll.sqlite3_result_int(self._contextpointer, c_int(data))
    
    
    def result_int64(self, data):
        """
        See result_blob for description
        """
        _dll.sqlite3_result_int64(self._contextpointer, c_longlong(data))


    # TODO void sqlite3_result_error(sqlite3_context*, const char*, int)   # Doc missing
    
    # TODO void sqlite3_result_value(sqlite3_context*, sqlite3_value*);

    
    
class _Value:
    """
    Wrapper for an sqlite value, needed for user-defined functions.
    You should not create an object yourself, it will be created automatically
    when calling a user-defined function.
    
    A Value does not provide *_auto functions nor provides it an errorhandler,
    you have to check the return values, if any, for that (see the SQLITE_ error constants)
    """
    
    def __init__(self, ptr):
        self._valuepointer = c_void_p(ptr)


    def value_blob(self):
        """
        Retrieve a blob object as string from a value.
        """
        length = _dll.sqlite3_value_bytes(self._valuepointer)
        if length == 0:
            return b""

        _dll.sqlite3_value_blob.restype = POINTER(c_char * length)  # TODO: Thread safety
        
        return _dll.sqlite3_value_blob(self._valuepointer).contents.raw   # Return Binary instead?
    
    
    def value_text(self):
        """
        Retrieve a text object as string from a value.
        """
        length = _dll.sqlite3_value_bytes(self._valuepointer)
        if length == 0:
            return b""
   
        _dll.sqlite3_value_text.restype = POINTER(c_char * length)  # TODO: Thread safety
        
        return _dll.sqlite3_value_text(self._valuepointer).contents.raw
    
    
    def value_null(self):
        """
        Returns always None.
        """
        return None
    

# The remaining value functions are created by this template

for restype, fctname in (
        ("c_int", "value_bytes"),
        ("c_int", "value_bytes16"),
        ("c_double", "value_double"),
        ("c_int", "value_int"),
        ("c_longlong", "value_int64"),
        ("c_int", "value_type") ):


    exec("""

def {1}(self):
    "Retrieve a value from a user-defined function"
    return _dll.sqlite3_{1}(self._valuepointer)  # .value ?

_Value.{1} = {1}

del {1}

_dll.sqlite3_{1}.restype = {0}

""".format(restype, fctname))


# void (*xFunc)(sqlite3_context*,int,sqlite3_value**)
FUNC_CALLBACK_TYPE = CFUNCTYPE(None, c_void_p, c_int, POINTER(c_void_p))

_dll.sqlite3_user_data.restype = c_void_p



def _pyFuncCallback(contextptr, nValues, valueptrptr):
    realfunc = _sqliteTransObjects[_dll.sqlite3_user_data(c_void_p(contextptr))]
    values = [_Value(valueptrptr[i]) for i in range(nValues)]
    # print "_pyFuncCallback", repr(realfunc), repr(values), id(realfunc), sys.getrefcount(realfunc)
    try:
        realfunc(_Context(contextptr), values)
    except:
        traceback.print_exc()

        
_FUNC_CALLBACK = FUNC_CALLBACK_TYPE(_pyFuncCallback)


