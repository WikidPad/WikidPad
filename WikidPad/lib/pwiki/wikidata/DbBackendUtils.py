from . import WikiData_compact_sqlite
from . import WikiData_original_sqlite

_handlers = None


def _collectHandlers():
    global _handlers
    _handlers = []

    hdls = WikiData_original_sqlite.listAvailableWikiDataHandlers()
    for h in hdls:
        _handlers.append((h[0], h[1],
                WikiData_original_sqlite.getWikiDataHandler))

    hdls = WikiData_compact_sqlite.listAvailableWikiDataHandlers()
    for h in hdls:
        _handlers.append((h[0], h[1],
                WikiData_compact_sqlite.getWikiDataHandler))

#     print("--_collectHandlers34", repr(_handlers))

def listHandlers():
    global _handlers
    if _handlers is None:
        _collectHandlers()
        
    return [(h[0], h[1]) for h in _handlers]


def getHandler(name):
    global _handlers
    if _handlers is None:
        _collectHandlers()

    for h in _handlers:
        if h[0] == name:
            return h[2](name)
            
    return (None, None)



