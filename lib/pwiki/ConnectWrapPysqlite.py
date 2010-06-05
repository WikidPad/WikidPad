"""
This module defines a connect wrapper similar to those in the "DbStructure.py"
files, but for Python's built-in pysqlite3.

Some day I will explain here why two sqlite implementations are needed in
WikidPad.
"""


import sqlite3, traceback

from pwiki.WikiExceptions import *


# Connection (and Cursor)-Wrapper to simplify some operations

class ConnectWrapBase:
    """
    Connection (and Cursor)-Wrapper to simplify some operations.
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
            self.dbCursor.execute(sql, params)
        else:
            self.dbCursor.execute(sql)

        return self.dbCursor.fetchall()


#     def execSqlQueryIter(self, sql, params=None):
#         """
#         utility method, executes the sql, returns an iterator
#         over the query results
#         """
#         ## print "execSqlQuery sql", sql, repr(params)
#         if params:
#             self.dbCursor.execute(sql, params)
#         else:
#             self.dbCursor.execute(sql)
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
        except sqlite3.Error:
            pass


    def getLastRowid(self):
        return self.dbCursor.lastrowid


    def closeCursor(self):
        if self.dbCursor:
            self.dbCursor.close()
            self.__dict__["dbCursor"] = None


    def close(self):
        """
        Close cursor and connection
        """
        if self.dbConn:
            self.closeCursor()
            self.dbConn.close()
            self.__dict__["dbConn"] = None


    def __del__(self):
        """
        Only the implicitly generated cursor is closed automatically
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


