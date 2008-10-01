# Thrown by WikiData classes
class WikiDataException(Exception): pass
class WikiWordNotFoundException(WikiDataException): pass
class WikiFileNotFoundException(WikiDataException): pass
class WikiDBExistsException(WikiDataException): pass

# For non-Windows systems
try:
    WindowsError
except NameError:
    class WindowsError(Exception): pass


class DbAccessError(Exception):
    """
    Base classes for read or write errors when acessing database
    where "database" also means wiki configuration and additional
    files.
    """
    def __init__(self, originalException):
        Exception.__init__(self, str(originalException))
        self.originalException = originalException
    
    def getOriginalException(self):
        return self.originalException

class DbReadAccessError(DbAccessError):
    """
    Impossible to read (and therefore also to write to) database
    """
    pass

class DbWriteAccessError(DbAccessError):
    """
    Impossible to write to database, reading may be possible
    """
    pass



class InternalError(Exception): pass


class ExportException(Exception): pass
class ImportException(Exception): pass

# See Serialization.py
class SerializationException(Exception): pass

# See WikiDataManager.py. Thrown if requested handler for db backend isn't
#     available
class NoDbHandlerException(Exception): pass
class WrongDbHandlerException(Exception): pass
class DbHandlerNotAvailableException(Exception): pass
class UnknownDbHandlerException(Exception): pass

class MissingConfigurationFileException(Exception): pass
class BadConfigurationFileException(Exception): pass
class LockedWikiException(Exception): pass

class NotCurrentThreadException(Exception): pass

class BadFuncPageTagException(Exception): pass
