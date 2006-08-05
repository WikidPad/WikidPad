# Thrown by WikiData classes
class WikiDataException(Exception): pass
class WikiWordNotFoundException(WikiDataException): pass
class WikiFileNotFoundException(WikiDataException): pass
class WikiDBExistsException(WikiDataException): pass


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

class BadConfigurationFileException(Exception): pass

