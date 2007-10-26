

WIKIDPAD_PLUGIN = (("hooks", 1),)

def startup(wikidPad):
    """
    Called when application starts
    """

    pass

def newWiki(wikidPad, wikiName, wikiDir):
    """
    Called when a new wiki is about to be created.

    wikiName -- name of the wiki (already checked to be a proper CamelCase word)
    wikiDir -- directory to create the wiki in (more precisely the .wiki config
           file). This directory may already exist
    """
    pass

def createdWiki(wikidPad, wikiName, wikiDir):
    """
    Called when creation of a new wiki was done successfully.

    The home wiki word (equals name of the wiki) is not yet loaded.

    wikiName -- name of the wiki
    wikiDir -- directory the wiki was created in
    """
    pass

def openWiki(wikidPad, wikiConfig):
    """
    Called when an existing wiki is about to be opened.

    wikiConfig -- path to the .wiki config file
    """
    pass

def openedWiki(wikidPad, wikiName, wikiConfig):
    """
    Called when an existing wiki was opened successfully

    wikiName -- name of the wiki
    wikiConfig -- path to the .wiki config file
    """
    pass

def openWikiWord(wikidPad, wikiWord):
    """
    Called when a new or existing wiki word is about to be opened.
    The previous active page is already saved, new one is not yet loaded.

    wikiWord -- name of the wiki word to open
    """
    pass

def newWikiWord(wikidPad, wikiWord):
    """
    Called when a new wiki word is about to be created.
    The wikidPad.currentWikiPage of the new word is already available

    wikiWord -- name of the wiki word to create
    """
    pass

def openedWikiWord(wikidPad, wikiWord):
    """
    Called when a new or existing wiki word was opened successfully.

    wikiWord -- name of the wiki word to create
    """
    pass

def savingWikiWord(wikidPad, wikiWord):
    """
    Called when a new or existing wiki word is about to be saved

    wikiWord -- name of the wiki word to create
    """
    pass

def savedWikiWord(wikidPad, wikiWord):
    """
    Called when a wiki word was saved successfully

    wikiWord -- name of the wiki word to create
    """
    pass

def renamedWikiWord(wikidPad, fromWord, toWord):
    """
    Called when a wiki word was renamed successfully.

    The changed data is already saved in the fileset,
    the GUI is not updated yet, the renamed page is not yet loaded.

    fromWord -- name of the wiki word before renaming
    toWord -- name of the wiki word after renaming
    """
    pass

def deletedWikiWord(wikidPad, wikiWord):
    """
    Called when a wiki word was deleted successfully.

    The changed data is already saved in the fileset,
    the GUI is not updated yet, another page (normally
    the last in history before the deleted one) is not yet loaded.

    wikiWord -- name of the deleted wiki word
    """
    pass

def exit(wikidPad):
    """
    Called when the application is about to exit.

    The global and the wiki configuration (if any) are saved already,
    the current wiki page (if any) is saved already.
    """
    pass
