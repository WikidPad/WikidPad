class WikiDataException(Exception): pass
class WikiWordNotFoundException(WikiDataException): pass
class WikiFileNotFoundException(WikiDataException): pass
class WikiDBExistsException(WikiDataException): pass
