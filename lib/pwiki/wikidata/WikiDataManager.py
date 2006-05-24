from weakref import WeakValueDictionary
import os.path

from pwiki.WikiExceptions import *
from pwiki.DocPages import WikiPage, FunctionalPage, AliasWikiPage

from pwiki.SearchAndReplace import SearchReplaceOperation

import FileStorage


class WikiDataManager:
    """
    Wraps a WikiData object and provides services independent
    of database backend, especially creation of WikiPage objects.
    
    When the open wiki database changes, a new DataManager is created.
    
    When asking for a WikiPage for the same word twice and the first object
    exists yet, no new object is created, but the same returned
    """

    def __init__(self, mainControl, wikiData):
        self.mainControl = mainControl
        self.wikiData = wikiData
        
        self.wikiPageDict = WeakValueDictionary()
        self.fileStorage = FileStorage.FileStorage(self.mainControl, self,
                os.path.join(os.path.dirname(
                self.mainControl.getWikiConfigPath()), "files"))

    def getWikiData(self):
        return self.wikiData
        
    def getFileStorage(self):
        return self.fileStorage


    def getWikiPage(self, wikiWord):
        """
        Fetch a WikiPage for the wikiWord, throws WikiWordNotFoundException
        if word doesn't exist
        """
        if not self.wikiData.isDefinedWikiWord(wikiWord):
            raise WikiWordNotFoundException, u"Word '%s' not in wiki" % wikiWord

        return self.getWikiPageNoError(wikiWord)
        
    def getWikiPageNoError(self, wikiWord):
        """
        fetch a WikiPage for the wikiWord. If it doesn't exist, return
        one without throwing an error and without updating the cache.
        
        Asking for the same wikiWord twice returns the same object if
        it wasn't garbage collected yet.
        """
        value = self.wikiPageDict.get(wikiWord)
        if value is None:
            # No active page available
            realWikiWord = self.wikiData.getAliasesWikiWord(wikiWord)
            if wikiWord == realWikiWord:
                # no alias
                value = WikiPage(self, wikiWord)
            else:
                realpage = WikiPage(self, realWikiWord)
                value = AliasWikiPage(self, wikiWord, realpage)

            self.wikiPageDict[wikiWord] = value

        return value


    def createWikiPage(self, wikiWord):
        """
        create a new wikiPage for the wikiWord. Cache is not updated until
        page is saved
        """
        return self.getWikiPageNoError(wikiWord)


    def getFuncPage(self, funcTag):
        """
        Retrieve a functional page
        """
        # TODO Ensure uniqueness as for wiki pages
        return FunctionalPage(self.mainControl, self, funcTag)


    def rebuildWiki(self, progresshandler):
        """
        Rebuild  the wiki
        
        progresshandler -- Object, fulfilling the
            PersonalWikiFrame.GuiProgressHandler protocol
        """
                
        self.getWikiData().refreshDefinedContentNames()

        # get all of the wikiWords
        wikiWords = self.getWikiData().getAllDefinedWikiPageNames()
        
        progresshandler.open(len(wikiWords) + 1)
        try:
            step = 1

            # re-save all of the pages
            self.getWikiData().clearCacheTables()
            for wikiWord in wikiWords:
                progresshandler.update(step, u"")   # , "Rebuilding %s" % wikiWord)
                wikiPage = self.createWikiPage(wikiWord)
                wikiPage.update(wikiPage.getContent(), False)  # TODO AGA processing
                step = step + 1

        finally:            
            progresshandler.close()
            

        # Give possibility to do further reorganisation
        # specific to database backend
        self.getWikiData().cleanupAfterRebuild(progresshandler)


    def renameWikiWord(self, wikiWord, toWikiWord, modifyText):
        """
        modifyText -- Should the text of links to the renamed page be
                modified? This text replacement works unreliably
        """
        self.getWikiData().renameWord(wikiWord, toWikiWord)
        
        # TODO: Replace always?
        prevTitle = "++ " + WikiPage.getWikiPageTitle(wikiWord) + u"\n"
        page = self.getWikiPage(toWikiWord)
        content = page.getLiveText()
        if content.startswith(prevTitle):
            # Replace previous title with new one
            content = "++ " + WikiPage.getWikiPageTitle(toWikiWord) + u"\n" + \
                    content[len(prevTitle):]
            page.replaceLiveText(content)

        if not modifyText:
            return

        # now we have to search the wiki files and replace the old word with the new
        searchOp = SearchReplaceOperation()
        searchOp.wikiWide = True
        searchOp.wildCard = 'no'
        searchOp.caseSensitive = True
        searchOp.searchStr = wikiWord
        
        for resultWord in self.getWikiData().search(searchOp):
            page = self.getWikiPage(resultWord)
            content = page.getContent()
            content = content.replace(wikiWord, toWikiWord)
            page.save(content)
            page.update(content, False)  # TODO AGA processing



