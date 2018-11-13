# import datetime

# This module does currently not support date and time handling


import re

from . import SqliteThin3


# def def_bind_fctfinder(stmt, parno, data)
# def_column_fctfinder(stmt, col)

from .SqliteThin3 import def_bind_fctfinder, def_column_fctfinder, \
        SQLITE_UTF8, SQLITE_UTF16BE, \
        SQLITE_UTF16LE, SQLITE_UTF16, \
        SQLITE_INTEGER, SQLITE_FLOAT, SQLITE_TEXT, SQLITE_BLOB, SQLITE_NULL, \
        AUTO_COLUMN_CONVERTS, getLibVersion, \
        \
        addTransObject, getTransObject, delTransObject


apilevel = "2.0"
threadsafety = 0  # Maybe 1?
paramstyle = "qmark"
Binary = SqliteThin3.Binary


# Exceptions

class Warning(Exception):
    pass
    
class Error(Exception):
    pass

class InterfaceError(Error):
    pass

class DatabaseError(Error):
    pass
    
class ReadOnlyDbError(DatabaseError):
    pass

class DataError(DatabaseError):
    pass

class OperationalError(DatabaseError):
    pass

class IntegrityError(DatabaseError):
    pass

class InternalError(DatabaseError):
    pass

class ProgrammingError(DatabaseError):
    pass

class NotSupportedError(DatabaseError):
    pass


# Modes for type detection:
TYPEDET_NONE = 0    # No automatic detection
TYPEDET_FIRST = 1   # Use types of first retrieved row

# TODO UTF-8 ???





class Connection:
    def __init__(self, dsn, *params, **keywords):
        self.thinConn = None
        self.thinConn = SqliteThin3.SqliteDb3(dsn, self._errHandler)
        self.statementCache = {} # Cache for prepared statements
        self._autoCommit = False
        self.bindfct = None
        self.colfct = None
        self.cursorFactory = keywords.get("cursorfactory", Cursor)
        
    def prepare(self, sql):
        """
        Return prepared sql thin-statement, either from cache or newly created.
        It will be removed from the cache if it was in to avoid that two cursors
        use the same statement.
        
        The function returns a list (a mutable sequence) with the statement
        as first item and a hint for the column types or None as second item.
        
        sql -- SQL-string to prepare
        """
        try:
            if self.statementCache.get(sql, None) is None:
                return [self.thinConn.prepare(sql), None]
            else:
                st = self.statementCache[sql]
                self.statementCache[sql] = None
                return st

        except AttributeError:
            raise Error("Trying to access a closed connection")
            
            
    def putStmtBack(self, sql, stmt):
        """
        Put statement back into the cache after use. Does not throw an
        exception  ???
        
        sql -- SQL-string used to prepare statement
        """
        try:
            if (self.statementCache.get(sql, None) is None):
                stmt[0].reset()
                self.statementCache[sql] = stmt
            else:
                # There is already a statement for this sql
                stmt[0].close()
            
        except AttributeError:
            stmt[0].close()
            pass   # raise Error, "Trying to access a closed connection"
            
            
    def clearStmtCache(self):
        try:
            stmts = [s for s in list(self.statementCache.values()) if s is not None]
            for s in stmts:
                s[0].close()
                
            self.statementCache = {}
        except AttributeError:
            raise Error("Trying to access a closed connection")


    def close(self):
        error = None
        try:
            self.clearStmtCache()
            self.statementCache = None
        except Exception as e:
            error = e        
        
        try:
            self.thinConn.close()
            self.thinConn = None
        except Exception as e:
            error = e        

        if error:
            raise e        
         
        
    def __del__(self):
        try:
            self.close()
        except:
            pass

    def begin(self):
        try:
            self.thinConn.execute("begin")
        except AttributeError:
            raise Error("Trying to access a closed connection")
        

    def commit(self):
        try:
            if not self.thinConn.get_autocommit():
                self.thinConn.execute("commit")
        except AttributeError:
            raise Error("Trying to access a closed connection")

    def rollback(self):
        try:
            if not self.thinConn.get_autocommit():
                self.thinConn.execute("rollback")
        except AttributeError:
            raise Error("Trying to access a closed connection")

            
    def cursor(self):
        if self.thinConn is None:
            raise Error("Trying to access a closed connection")
            
        return self.cursorFactory(self)
        
    # TODO refine
    def _errHandler(self, err):
        
        if not err in (SqliteThin3.SQLITE_OK, SqliteThin3.SQLITE_ROW,
                SqliteThin3.SQLITE_DONE):
            if err == SqliteThin3.SQLITE_READONLY:
                raise ReadOnlyDbError("Sqlite DB read-only error [%i]" % err)
            elif self.thinConn:
                msg = self.thinConn.errmsg()
                raise Error(msg + " [%i]" % err)
            else:
                raise Error("Sqlite open error %i" % err)

            
    # TODO Explain
    def setBindFctFinder(self, fct):
        self.bindfct = fct
        
    def setColumnFctFinder(self, fct):
        self.colfct = fct
        
    def createFunction(self, funcname, nArg, func,
            textRep=SqliteThin3.SQLITE_UTF8):
        self.thinConn.create_function(funcname, nArg, func, textRep)
        self.clearStmtCache()
        
    def setAutoCommit(self, v=True, silent=False):
        if v and not self._autoCommit and not silent:
            self.commit()

        self._autoCommit = v
        
        
    def getAutoCommit(self):
        return self._autoCommit



      
            
# For convenience:            
            
Connection.Warning = Warning
Connection.Error = Error
Connection.InterfaceError = InterfaceError
Connection.DatabaseError = DatabaseError
Connection.ReadOnlyDbError = ReadOnlyDbError
Connection.DataError = DataError
Connection.OperationalError = OperationalError
Connection.IntegrityError = IntegrityError
Connection.InternalError = InternalError
Connection.ProgrammingError = ProgrammingError
Connection.NotSupportedError = NotSupportedError




def connect(dsn, *params, **keywords):
    return Connection(dsn, *params, **keywords)





class Cursor:
    def __init__(self, conn):
        """
        conn -- underlying connection
        """
        self.conn = conn
        self.stmt = None
        self.stmtsql = None
        self.nextRow = None
        self.nextRowIntern = None
        self.colTypeHints = None
        self.colFct = None 

        self.description = None
        self.rowcount = -1
        self.arraysize = 50
    
    
    def _reset(self):
        self.description = None
        self.rowcount = -1
        self.nextRow = None
        self.nextRowIntern = None
        self.colTypeHints = None
        self.colFct = None
        
        try:
            if not self.stmt is None:
                self.conn.putStmtBack(self.stmtsql, self.stmt)
                self.stmt = None
                self.stmtsql = None
                
        except AttributeError:
            if not self.stmt is None:
                self.stmt[0].close()  
                self.stmt = None
                
            raise Error("Trying to access a closed cursor")


    def close(self):
        self._reset()
        self.conn = None
        
    def __del__(self):
        try:
            self.close()
        except:
            pass           


    # TODO refine type detection
    def execute(self, sql, parameters=None, bindfct=None, colfct=None,
            **keywords):
        self._reset()
        
        try:
            if bindfct is None:
                bindfct = self.conn.bindfct
                
            if colfct is None:
                colfct = self.conn.colfct
                
            cmd = sql.lstrip().split(" ",1)[0].lower()
            
            if not self.conn._autoCommit:
                if self.conn.thinConn.get_autocommit():
                    if cmd in ("insert", "update", "delete", "replace",
                            "create", "drop"):
                        self.conn.begin()
                else:
                    if cmd not in ("select", "begin", "commit", "rollback",
                            "insert", "update", "delete", "replace", "create",
                            "drop"):
                        self.conn.commit()
            
            self.stmt = self.conn.prepare(sql)
            self.stmtsql = sql

            if parameters:
                self.stmt[0].bind_auto_multi(parameters, fctfinder=bindfct)
            
            try:
                if self.stmt[0].step():
                    if keywords.get("typeDetect", TYPEDET_NONE) == TYPEDET_FIRST:
                        if self.stmt[1] is None:
                            self.colTypeHints = self.stmt[0].column_typefuncs(fctfinder=colfct)
                            self.stmt[1] = self.colTypeHints
                        else:
                            self.colTypeHints = self.stmt[1]
                            
                        self.nextRowIntern = self.stmt[0].column_hint_multi(self.colTypeHints)
                    else:
                        self.nextRowIntern = self.stmt[0].column_auto_multi(fctfinder=colfct)
                        self.colFct = colfct
                        
                    self.nextRow = tuple(self.nextRowIntern)
                else:
                    self.nextRow = None
                    self.colTypeHints = None
                    # Statement no longer needed here
                    self.conn.putStmtBack(self.stmtsql, self.stmt)
                    self.stmt = None
                    self.stmtsql = None
                    self.colFct = None

            except Error:
                self.nextRow = None
                self.colTypeHints = None
                # Statement no longer needed here
                self.conn.putStmtBack(self.stmtsql, self.stmt)
                self.stmt = None
                self.stmtsql = None
                self.colFct = None
                
                raise
                
            # After schema change clear stmt cache            
            if cmd in ("create", "drop", "vacuum", "pragma"):
                self.conn.clearStmtCache()
    
            elif cmd in ("insert", "update", "delete", "replace"):
                # Set rowcount to number of affected rows
                self.rowcount = self.conn.thinConn.changes()
                    
        except AttributeError:
            if not self.stmt is None:
                self.stmt[0].close()  
                self.stmt = None

            raise Error("Trying to access a closed cursor")


    def executemany(self, sql, seq_of_parameters, *params, **keywords):
        """
        Simple implementation
        """
        for pars in seq_of_parameters:
            self.execute(sql, pars, *params, **keywords)
            
    def fetchone(self):
        """
        Does not throw an error if no result set produced.
        """
        result = self.nextRow
        if result is None:
            return None
            
        try:
            if self.stmt[0].step():
                if self.colTypeHints:
                    self.nextRowIntern = self.stmt[0].column_hint_multi_fast(self.colTypeHints, self.nextRowIntern)
                else:
                    self.nextRowIntern = self.stmt[0].column_auto_multi(fctfinder=self.colFct)
                    
                self.nextRow = tuple(self.nextRowIntern)
            else:
                self.nextRow = None
                self.nextRowIntern = None
                # Statement no longer needed here
                self.conn.putStmtBack(self.stmtsql, self.stmt)
                self.stmt = None
                
            return result
            
        except Error:
                self.nextRow = None
                self.nextRowIntern = None
                # Statement no longer needed here
                self.conn.putStmtBack(self.stmtsql, self.stmt)
                self.stmt = None

                raise            
            
        except AttributeError:
            if not self.stmt is None:
                self.stmt[0].close()  
                self.stmt = None

            raise Error("Trying to access a closed cursor")

            
    def fetchmany(self, size=None):
        """
        Simple implementation
        """
        if size is None:
            size = self.arraysize
            
        result = []
        for i in range(size):
            row = self.fetchone()
            if row is None:
                break
                
            result.append(row)
            
        return result

            
    def fetchall(self):
        """
        Simple implementation
        """
        
        result = []
        while True:
            row = self.fetchone()
            if row is None:
                break
                
            result.append(row)
            
        return result
        
    def __next__(self):
        row = self.fetchone()
        if row is None:
            raise StopIteration
            
        return row
        
#     def _fetchiter(self):
#         """
#         Generator function
#         """
#         while True:
#             row = self.fetchone()
#             if row is None:
#                 return
#                 
#             yield row
            
    def __iter__(self):
        return self     # ._fetchiter() #?

        
    def setinputsizes(self, sizes):
        "Dummy"
        pass

            
    def setoutputsize(self, size, column=None):
        "Dummy"
        pass

    def commit(self):
        try:
            self.conn.commit()
        except AttributeError:
            if not self.stmt is None:
                self.stmt[0].close()  
                self.stmt = None

            raise Error("Trying to access a closed cursor")

    def rollback(self):
        try:
            self.conn.rollback()
        except AttributeError:
            if not self.stmt is None:
                self.stmt[0].close()  
                self.stmt = None

            raise Error("Trying to access a closed cursor")


    def begin(self):
        try:
            self.conn.begin()
        except AttributeError:
            if not self.stmt is None:
                self.stmt[0].close()  
                self.stmt = None

            raise Error("Trying to access a closed cursor")


    def __getattr__(self, attr):
        if attr == "lastrowid":
            try:
                return self.conn.thinConn.last_insert_rowid()
            except DataError: #AttributeError:
                if not self.stmt is None:
                    self.stmt[0].close()  
                    self.stmt = None

                raise Error("Trying to access a closed cursor")
            
        raise AttributeError("No attribute %s in sqlite3api.Cursor" % attr)
            

_GLOB_ESCAPE_RE = re.compile(r"([\[\]\*\?])")

def escapeForGlob(s):
    return _GLOB_ESCAPE_RE.sub(r"[\1]", s)


