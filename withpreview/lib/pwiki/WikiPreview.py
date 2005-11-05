import os
from wxPython.wx import *
from wxPython.stc import *
from wxPython.html import *
from Exporters import *

class WikiPreview(wxHtmlWindow):
    def __init__(self, pWiki, parent, ID):        
        wxHtmlWindow.__init__(self, parent, ID)
        self.pWiki = pWiki
        self.links = None
        self.cache = {}

    def setWikiPage(self, wikiPage, wikiText):
        wikiWord = wikiPage.wikiWord

        try:
            # first check the cache
            cacheItem = self.cache.get(wikiWord)
            if cacheItem and float(cacheItem.modified) >= float(wikiPage.modified):
                self.SetPage(cacheItem.html)
                return
            
            wikiData = self.pWiki.wikiData

            links = {}
            for relation in wikiPage.childRelations:
                wordForAlias = wikiData.getAliasesWikiWord(relation)
                if wordForAlias:
                    links[relation] = wordForAlias
                else:
                    links[relation] = relation
            
            exporter = HtmlExporter(self.pWiki)
            html = exporter.exportContentToHtmlString(wikiWord, wikiText, links)

            # cache the html
            self.cache[wikiWord] = CacheItem(wikiWord, html, wikiPage.modified)
            self.SetPage(html)

        except Exception, e:
            self.pWiki.displayErrorMessage("Error rendering html", e)

    def OnLinkClicked(self, link):
        href = link.GetHref()
        if WikiFormatting.WikiWordRE.match(href) or WikiFormatting.WikiWordRE2.match(href):
            self.pWiki.openWikiPage(href)
        else:
            os.startfile(href)

class CacheItem:
    def __init__(self, word, html, modified):
        self.word = word
        self.html = html
        self.modified = modified
