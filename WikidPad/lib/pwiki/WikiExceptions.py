# Thrown by WikiData classes
class AppBaseException(Exception):
    def __init__(self, message="", tag=None):
        Exception.__init__(self, message)
        self.tag = tag

    def getTag(self):
        return self.tag


class WikiDataException(AppBaseException): pass
class WikiWordNotFoundException(WikiDataException): pass
class WikiFileNotFoundException(WikiDataException): pass
class WikiDBExistsException(WikiDataException): pass

class NoPageAstException(AppBaseException): pass

# For non-Windows systems
try:
    WindowsError
except NameError:
    class WindowsError(Exception): pass


class DbAccessError(AppBaseException):
    """
    Base classes for read or write errors when acessing database
    where "database" also means wiki configuration and additional
    files.
    """
    def __init__(self, originalException):
        AppBaseException.__init__(self, str(originalException))
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



class RenameWikiWordException(AppBaseException):
    """
    Raised on problems with renaming multiple wikiwords at once.
    Constructed in 
    WikiDocument.WikiDocument.buildRenameSeqWithSubpages()
    """
    # Problems:
    # Multiple words should be renamed to same word
    PRB_RENAME_TO_SAME = 1
    # Word to rename to exist already
    PRB_TO_ALREADY_EXISTS = 2

    def __init__(self, affectedRenames):
        """
        affectedRenames -- list of tuples (fromWikiWord, toWikiWord, problem)
            where problem is one of the PRB_* constants of the class.
        """
        self.affectedRenames = affectedRenames
        
    def getAffectedRenames(self):
        return self.affectedRenames


    def getFlowText(self):
        """
        Return affectedRenames as multiple-line human readable text
        """
        # TODO Move definition outside (attn to i18n)
        PROBLEM_HR_DICT = {
                self.PRB_RENAME_TO_SAME: _("Multiple words rename to same word"),
                self.PRB_TO_ALREADY_EXISTS: _("Word already exists")
            }

        result = []
        for fromWikiWord, toWikiWord, problem in self.affectedRenames:
            result.append("%s -> %s: %s" % (fromWikiWord, toWikiWord,
                    PROBLEM_HR_DICT[problem]))
        
        return "\n".join(result)




class InternalError(AppBaseException): pass


class ExportException(AppBaseException): pass
class ImportException(AppBaseException): pass

# See Serialization.py
class SerializationException(AppBaseException): pass
class VersioningException(AppBaseException): pass

# See WikiDocument.py. Thrown if requested handler for db backend isn't
#     available
class NoDbHandlerException(AppBaseException): pass
class WrongDbHandlerException(AppBaseException): pass
class DbHandlerNotAvailableException(AppBaseException): pass
class UnknownDbHandlerException(AppBaseException): pass


# See WikiDocument.py. Thrown if requested handler for wiki language isn't
#     available
class UnknownWikiLanguageException(AppBaseException): pass
class WrongWikiLanguageException(AppBaseException): pass


class MissingConfigurationFileException(AppBaseException): pass
class BadConfigurationFileException(AppBaseException): pass
class LockedWikiException(AppBaseException): pass


class NotCurrentThreadException(AppBaseException): pass
class UserAbortException(AppBaseException): pass

class DeadBlockPreventionTimeOutError(InternalError): pass

class BadFuncPageTagException(AppBaseException): pass
