from weakref import WeakValueDictionary


from pwiki.WikiExceptions import *
from pwiki.WikiPage import WikiPage, FunctionalPage

from pwiki.SearchAndReplace import SearchReplaceOperation



class WikiDataManager:
    """
    Wraps a WikiData object and provides services independent
    of database backend, especially creation of WikiPage objects.
    
    When the open wiki database changes, a new DataManager is created.
    
    When asking for a WikiPage for the same word twice and the first object
    exists yet, no new object is created, but the same returned
    """

    def __init__(self, pWiki, wikiData):
        self.pWiki = pWiki
        self.wikiData = wikiData
        
        self.pageDict = WeakValueDictionary()
        
    def getWikiData(self):
        return self.wikiData


    def getWikiPage(self, wikiWord):
        """
        Fetch a WikiPage for the wikiWord, throws WikiWordNotFoundException
        if word doesn't exist
        """
        if not self.wikiData.isDefinedWikiWord(wikiWord):
            raise WikiWordNotFoundException, u"Word '%s' not in wiki" % wikiWord

        return self.getPageNoError(wikiWord)
        
    def getWikiPageNoError(self, wikiWord):
        """
        fetch a WikiPage for the wikiWord. If it doesn't exist, return
        one without throwing an error and without updating the cache.
        
        Asking for the same wikiWord twice returns the same object if
        it wasn't garbage collected yet.
        """
        value = self.pageDict.get(wikiWord)
        if value is None:
            # No active page available
            value = WikiPage(self, wikiWord)
            self.pageDict[wikiWord] = value

        return value


    def createWikiPage(self, wikiWord):
        """
        create a new wikiPage for the wikiWord. Cache is not updated until
        page is saved
        """
        return self.getPageNoError(wikiWord)

    # TODO Remove these:
    getPage = getWikiPage
    getPageNoError = getWikiPageNoError
    createPage = createWikiPage
        
        
    def getFuncPage(self, funcTag):
        """
        Retrieve a functional page
        """
        # TODO Ensure uniqueness as for wiki pages
        return FunctionalPage(self.pWiki, self, funcTag)


    def rebuildWiki(self, progresshandler):
        """
        Rebuild  the wiki
        
        progresshandler -- Object, fulfilling the
            PersonalWikiFrame.GuiProgressHandler protocol
        """
                
        self.getWikiData().refreshDefinedPageNames()

        # get all of the wikiWords
        wikiWords = self.getWikiData().getAllDefinedPageNames()
        
        progresshandler.open(len(wikiWords) + 1)
        try:
            step = 1

            # re-save all of the pages
            self.getWikiData().clearCacheTables()
            for wikiWord in wikiWords:
                progresshandler.update(step, u"")   # , "Rebuilding %s" % wikiWord)
                wikiPage = self.createPage(wikiWord)
                wikiPage.update(wikiPage.getContent(), False)  # TODO AGA processing
                step = step + 1

        finally:            
            progresshandler.close()
            

        # Give possibility to do further reorganisation
        # specific to database backend
        self.getWikiData().cleanupAfterRebuild(progresshandler)
        
    def renameWikiWord(self, wikiWord, toWikiWord):
        self.getWikiData().renameWord(wikiWord, toWikiWord)

        # now we have to search the wiki files and replace the old word with the new
        searchOp = SearchReplaceOperation()
        searchOp.wikiWide = True
        searchOp.wildCard = 'no'
        searchOp.caseSensitive = True
        searchOp.searchStr = wikiWord
        
        for resultWord in self.getWikiData().search(searchOp):
            page = self.getPage(resultWord)
            content = page.getContent()
            content = content.replace(wikiWord, toWikiWord)
            page.save(content)
            page.update(content, False)  # TODO AGA processing



