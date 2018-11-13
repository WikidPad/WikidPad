import traceback

from .MiscEvent import KeyFunctionSink

from . import DocPages

class PageHistory:
    """
    Represents the history of visited wikiwords. Active component which reacts
    on MiscEvents.
    """
    def __init__(self, mainControl, docPagePresenter):
        self.pos = 0   # Pos is index into history but points one element *behind* current word
        self.history = []
        self.mainControl = mainControl
        
        self.mainControlSink = KeyFunctionSink((
                ("opened wiki", self.onOpenedWiki),
        ))

        self.docPagePresenter = docPagePresenter

        self.docPPresenterSink = KeyFunctionSink((
                ("loaded current doc page", self.onLoadedCurrentDocPage),
        ))

        self.__sinkWikiDoc = KeyFunctionSink((
                ("deleted wiki page", self.onDeletedWikiPage),
                ("pseudo-deleted wiki page", self.onDeletedWikiPage),
                ("renamed wiki page", self.onRenamedWikiPage),
                ("changed configuration", self.onChangedConfiguration)
        ))


        # Register for events
        self.mainControl.getMiscEvent().addListener(self.mainControlSink, False)
        
        self.docPagePresenter.getMiscEvent().addListener(
                self.docPPresenterSink, False)

        self.mainControl.getCurrentWikiDocumentProxyEvent().addListener(
                self.__sinkWikiDoc)

##                 ("saving current page", self.savingCurrentWikiPage)



    def close(self):
        self.mainControl.getMiscEvent().removeListener(self.mainControlSink)
        self.docPagePresenter.getMiscEvent().removeListener(
                self.docPPresenterSink)
        self.mainControl.getCurrentWikiDocumentProxyEvent().removeListener(
                self.__sinkWikiDoc)


    def onLoadedCurrentDocPage(self, miscevt):
        if miscevt.get("motionType") == "pageHistory":
            # history was used to move to new word, so don't add word to
            # history, move only pos
            delta = miscevt.get("historyDelta", 0)
            self.pos += delta
        else:
            if not miscevt.get("addToHistory", True):
                return

            # Add to history
            if len(self.history) > self.pos:
                # We are not at the end, so cut history                
                self.history = self.history[:self.pos]

            page = miscevt.get("docPage")
            if page is None:
                return
                
            upname = page.getUnifiedPageName()
            if not upname.startswith("wikipage/") and \
                    not DocPages.isFuncTag(upname):
                # Page is neither a wiki page nor a standard functional page
                return

            if self.pos == 0 or self.history[self.pos-1] != upname:
                self.history.append(upname)
                self.pos += 1
                # Otherwise, we would add the same word which is already
                # at the end
            
                self.limitEntries()


    def onChangedConfiguration(self, miscevt):
        self.limitEntries()


    def limitEntries(self):
        limit = self.mainControl.getConfig().getint("main",
                "tabHistory_maxEntries", 25)
        
        while len(self.history) > limit:
            self.history.pop(0)
            self.pos -= 1
        
        self.pos = max(0, self.pos)
        

    def onDeletedWikiPage(self, miscevt):
        """
        Remove deleted word from history
        """
        newhist = []
        upname = "wikipage/" + miscevt.get("wikiPage").getWikiWord() # self.mainControl.getCurrentWikiWord()
        
        # print "onDeletedWikiPage1",  self.pos, repr(self.history)

        for w in self.history:
            if w != upname:
                newhist.append(w)
            else:
                if self.pos > len(newhist):
                    self.pos -= 1
        
        self.history = newhist
        self.goAfterDeletion()  # ?        
        # print "onDeletedWikiPage5",  self.pos, repr(self.history)

    
    def onRenamedWikiPage(self, miscevt):
        """
        Rename word in history
        """
        oldUpname = "wikipage/" + miscevt.get("wikiPage").getWikiWord()
        newUpname = "wikipage/" + miscevt.get("newWord")
        
        for i in range(len(self.history)):
            if self.history[i] == oldUpname:
                self.history[i] = newUpname


    def onOpenedWiki(self, miscevt):
        """
        Another wiki was opened, clear the history
        """
        self.pos = 0
        self.history = []
        

    def goInHistory(self, delta):
        if not self.history:
            return

        newpos = max(1, self.pos + delta)
        newpos = min(newpos, len(self.history))
        delta = newpos - self.pos
        
        if delta == 0:
            return

        self.docPagePresenter.openDocPage(self.history[newpos - 1],
                motionType="pageHistory", historyDelta=delta)


    def getDeepness(self):
        """
        Returns tuple (back, forth) where  back  is the maximum number of steps
        to go backward in history,  forth  the max. number to go forward
        """
        return (max(0, self.pos - 1), max(0, len(self.history) - self.pos))


    def goAfterDeletion(self):
        """
        Called after a page was deleted
        """
        if not self.history:
            # No history -> try to delete current tab
            if not self.mainControl.getMainAreaPanel().closePresenterTab(
                    self.docPagePresenter):

                # If tab can't be deleted -> go to homepage of wiki
                self.docPagePresenter.openDocPage("wikipage/" + 
                        self.docPagePresenter.getWikiDocument().getWikiName(),
                        motionType="random")

            return
            
        self.docPagePresenter.openDocPage(self.history[self.pos - 1],
                motionType="pageHistory", historyDelta=0)
        
        
    def getHrHistoryList(self):
        result = []
        
        for upname in self.history:
            if upname.startswith("wikipage/"):
                result.append(upname[9:])
            else:
                result.append("<" + DocPages.getHrNameForFuncTag(upname) + ">")
                
        return result
        
    def getPosition(self):
        return self.pos


            
    # def savingCurrentWikiPage(self, evt):

        
    
