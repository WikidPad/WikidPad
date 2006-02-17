import WikiData_compact_sqlite
import WikiData_original_gadfly


_handlers = None


def _collectHandlers(pWiki):
    global _handlers
    _handlers = []

    hdls = WikiData_compact_sqlite.listAvailableWikiDataHandlers(pWiki)
    for h in hdls:
        _handlers.append((h[0], h[1],
                WikiData_compact_sqlite.getWikiDataHandler))

    hdls = WikiData_original_gadfly.listAvailableWikiDataHandlers(pWiki)
    for h in hdls:
        _handlers.append((h[0], h[1],
                WikiData_original_gadfly.getWikiDataHandler))
        

def listHandlers(pWiki):
    global _handlers
    if _handlers is None:
        _collectHandlers(pWiki)
        
    return [(h[0], h[1]) for h in _handlers]


def getHandler(pWiki, name):
    global _handlers
    if _handlers is None:
        _collectHandlers(pWiki)

    for h in _handlers:
        if h[0] == name:
            return h[2](pWiki, name)
            
    return (None, None)



