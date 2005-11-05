from os.path import join

def startup(wikidPad):
    pass

def newWiki(wikidPad, wikiName, wikiDir):
    pass

def createdWiki(wikidPad, wikiName, wikiDir):
    pass

def openWiki(wikidPad, wikiConfig):
    pass

def openedWiki(wikidPad, wikiName, wikiConfig):
    pass

def openWikiWord(wikidPad, wikiWord):
    #fileName = join(wikidPad.dataDir, "%s.wiki" % wikiWord)
    #wikidPad.displayMessage("File Location", fileName)
    #cvs update file
    pass

def newWikiWord(wikidPad, wikiWord):
    #cvs add file 
    pass

def openedWikiWord(wikidPad, wikiWord):
    pass

def savingWikiWord(wikidPad, wikiWord):
    pass

def savedWikiWord(wikidPad, wikiWord):
    #cvs commit file 
    pass

def renamedWikiWord(wikidPad, fromWord, toWord):
    #cvs remove file 
    #cvs add newfile 
    pass

def deletedWikiWord(wikidPad, wikiWord):
    #cvs remove file 
    pass

def exit(wikidPad):
    pass
