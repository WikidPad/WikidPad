from MiscEvent import KeyFunctionSink

class PageHistory:
    """
    Represents the history of visited wikiwords
    """
    def __init__(self, pWiki):
        self.pos = 0   # Pos is index into history but points one element *behind* current word
        self.history = []
        self.pWiki = pWiki
        
        # Register for pWiki events
        self.pWiki.getMiscEvent().addListener(KeyFunctionSink((
                ("loading current page", self.onLoadingCurrentWikiPage),
                ("deleted current page", self.onDeletedCurrentWikiPage),
                ("renamed page", self.onRenamedWikiPage),
                ("opened wiki", self.onOpenedWiki)
        )))
              
##                 ("saving current page", self.savingCurrentWikiPage)

    def onLoadingCurrentWikiPage(self, miscevt):
        if miscevt.get("motionType") == "history":
            # history was used to move to new word, so don't add word to
            # history, move only pos
            delta = miscevt.get("historyDelta")
            self.pos += delta
        else:
            if not miscevt.get("addToHistory", True):
                return

            # Add to history
            if len(self.history) > self.pos:
                # We are not at the end, so cut history                
                self.history = self.history[:self.pos]

            word = self.pWiki.getCurrentWikiWord()
            if self.pos == 0 or self.history[self.pos-1] != word:
                self.history.append(word)
                self.pos += 1
                # Otherwise, we would add the same word which is already
                # at the end
            
                if len(self.history) > 25:  # TODO Configurable
                    self.history.pop(0)
                    self.pos -= 1
                    self.pos = max(0, self.pos)  # TODO ?


    def onDeletedCurrentWikiPage(self, miscevt):
        """
        Remove deleted word from history
        """
        newhist = []
        word = self.pWiki.getCurrentWikiWord()
        
        for i, w in enumerate(self.history):
            if w != word:
                newhist.append(w)
            else:
                if self.pos > i:
                    self.pos -= 1
        
    
    def onRenamedWikiPage(self, miscevt):
        """
        Rename word in history
        """
        oldWord = miscevt.get("oldWord")
        newWord = miscevt.get("newWord")
        
        for i in xrange(len(self.history)):
            w = self.history[i]
            if w == oldWord:
                self.history[i] = newWord


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

        self.pWiki.openWikiPage(self.history[newpos - 1],
                motionType="history", historyDelta=delta)


    def goAfterDeletion(self):
        """
        Called after a page was deleted
        """
        if not self.history:
            self.pWiki.openWikiPage(self.pWiki.getWikiName(),
                    motionType="random")
            return
            
        self.pWiki.openWikiPage(self.history[self.pos - 1],
                motionType="history", historyDelta=0)
        
        
    def getHistory(self):
        return self.history
        
    def getPosition(self):
        return self.pos


            
    # def savingCurrentWikiPage(self, evt):

        
    
