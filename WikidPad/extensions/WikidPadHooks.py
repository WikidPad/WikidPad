

WIKIDPAD_PLUGIN = (("hooks", 2),)

def startup(wikidPad):
    """
    Called when application starts
    
    wikidPad -- PersonalWikiFrame object
    """

    pass

def newWiki(wikidPad, wikiName, wikiDir):
    """
    Called when a new wiki is about to be created.

    wikidPad -- PersonalWikiFrame object
    wikiName -- name of the wiki (already checked to be a proper CamelCase word)
    wikiDir -- directory to create the wiki in (more precisely the .wiki config
           file). This directory may already exist
    """
    pass

def createdWiki(wikidPad, wikiName, wikiDir):
    """
    Called when creation of a new wiki was done successfully.

    The home wiki word (equals name of the wiki) is not yet loaded.

    wikidPad -- PersonalWikiFrame object
    wikiName -- name of the wiki
    wikiDir -- directory the wiki was created in
    """
    pass

def openWiki(wikidPad, wikiConfig):
    """
    Called when an existing wiki is about to be opened.

    wikidPad -- PersonalWikiFrame object
    wikiConfig -- path to the .wiki config file
    """
    pass

def openedWiki(wikidPad, wikiName, wikiConfig):
    """
    Called when an existing wiki was opened successfully

    wikidPad -- PersonalWikiFrame object
    wikiName -- name of the wiki
    wikiConfig -- path to the .wiki config file
    """
    pass

def openWikiWord(docPagePresenter, wikiWord):
    """
    Called when a new or existing wiki word is about to be opened.
    The previous active page is already saved, new one is not yet loaded.

    wikiWord -- name of the wiki word to open
    """
    pass

def newWikiWord(docPagePresenter, wikiWord):
    """
    Called when a new wiki word is about to be created.
    The wikidPad.currentWikiPage of the new word is already available

    wikiWord -- name of the wiki word to create
    """
    pass

def openedWikiWord(docPagePresenter, wikiWord):
    """
    Called when a new or existing wiki word was opened successfully.

    wikiWord -- name of the wiki word to create
    """
    pass

def savingWikiWord(wikidPad, wikiWord):
    """
    Called when a new or existing wiki word is about to be saved

    wikidPad -- PersonalWikiFrame object
    wikiWord -- name of the wiki word to create
    """
    pass

def savedWikiWord(wikidPad, wikiWord):
    """
    Called when a wiki word was saved successfully

    wikidPad -- PersonalWikiFrame object
    wikiWord -- name of the wiki word to create
    """
    pass

def renamedWikiWord(wikidPad, fromWord, toWord):
    """
    Called when a wiki word was renamed successfully.

    The changed data is already saved in the fileset,
    the GUI is not updated yet, the renamed page is not yet loaded.

    wikidPad -- PersonalWikiFrame object
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

    wikidPad -- PersonalWikiFrame object
    wikiWord -- name of the deleted wiki word
    """
    pass

def closingWiki(wikidPad, wikiConfig):
    """
    Called when the current wiki is about to be closed in a PersonalWikiFrame.
    Be aware that the same wiki can be open in multiple frames.
    This function is called for "hooks"-plugins version 2 or later.

    wikidPad -- PersonalWikiFrame object
    wikiConfig -- path to the .wiki config file
    """
    pass

def droppingWiki(wikidPad, wikiConfig):
    """
    Called if the current wiki is about to be dropped. If the underlying
    database can't be accessed regularly anymore due to an error, WikidPad
    offers the option to "drop" a wiki by just forgetting the database
    connection and the wiki configuration file access.
    This function is called if the user chose to "close anyway" despite the
    error.
    Before this function is called a call to closingWiki may or may not happen.
    This function is called for "hooks"-plugins version 2 or later.

    wikidPad -- PersonalWikiFrame object
    wikiConfig -- path to the .wiki config file
    """
    pass

def closedWiki(wikidPad, wikiConfig):
    """
    Called when the current wiki was closed or dropped.
    This function is called for "hooks"-plugins version 2 or later.

    wikidPad -- PersonalWikiFrame object
    wikiConfig -- path to the .wiki config file
    """
    pass

def exit(wikidPad):
    """
    Called when the application is about to exit.

    The global and the wiki configuration (if any) are saved already,
    the current wiki page (if any) is saved already.

    wikidPad -- PersonalWikiFrame object
    """
    pass
