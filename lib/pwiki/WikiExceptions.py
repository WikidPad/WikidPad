class WikiDataException(Exception): pass
class WikiWordNotFoundException(WikiDataException): pass
class WikiFileNotFoundException(WikiDataException): pass
class WikiDBExistsException(WikiDataException): pass

class ExportException(Exception): pass
class ImportException(Exception): pass

class SerializationException(Exception): pass
