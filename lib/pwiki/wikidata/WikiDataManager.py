from weakref import WeakValueDictionary
import os, os.path, sets, traceback
from threading import RLock

from wxPython.wx import wxGetApp

from pwiki.MiscEvent import MiscEventSourceMixin

from pwiki.WikiExceptions import *
from pwiki.StringOps import mbcsDec
from pwiki.DocPages import WikiPage, FunctionalPage, AliasWikiPage

from pwiki.Configuration import createWikiConfiguration
from pwiki.WikiFormatting import WikiFormatting

from pwiki.SearchAndReplace import SearchReplaceOperation

import DbBackendUtils, FileStorage



_openDocuments = {}  # Dictionary {<path to data dir>: <WikiDataManager>}


_globalFuncPages = WeakValueDictionary()  # weak dictionary
        # {<funcTag starting with "global/">: <funcPage>}

def isDbHandlerAvailable(dbtype):
    wikiDataFactory, createWikiDbFunc = DbBackendUtils.getHandler(dbtype)
    return wikiDataFactory is not None


def createWikiDb(pWiki, dbtype, wikiName, dataDir, overwrite=False):
    """
    Create a new wiki database
    pWiki -- instance of PersonalWikiFrame
    dbtype -- internal name of database type
    wikiName -- Name of the wiki to create
    dataDir -- directory for storing the data files
    overwrite -- Should already existing data be overwritten?
    """
    global _openDocuments

    wdm = _openDocuments.get(dataDir)
    if wdm is not None:
        raise WikiDBExistsException("Database exists already and is currently in use")

    wikiDataFactory, createWikiDbFunc = DbBackendUtils.getHandler(dbtype)
    if wikiDataFactory is None:
        raise NoDbHandlerException("Data handler %s not available" % dbtype)

    createWikiDbFunc(wikiName, dataDir, overwrite)


def openWikiDocument(wikiConfigFilename, wikiSyntax, dbtype=None):
    """
    Create a new instance of the WikiDataManager or return an already existing
    one
    dbtype -- internal name of database type
    wikiName -- Name of the wiki to create
    dataDir -- directory for storing the data files
    overwrite -- Should already existing data be overwritten
    """
    global _openDocuments

    wdm = _openDocuments.get(wikiConfigFilename)
    if wdm is not None:
        if dbtype is not None and dbtype != wdm.getDbtype():
            # Same database can't be opened twice with different db handlers
            raise WrongDbHandlerException(("Database is already in use "
                    "with handler '%s'. Can't open with different handler.") %
                    wdm.getDbtype())

        wdm.incRefCount()
        return wdm

    wdm = WikiDataManager(wikiConfigFilename, wikiSyntax, dbtype)
    
    _openDocuments[wikiConfigFilename] = wdm

    return wdm



#     wikiDataFactory, createWikiDbFunc = DbBackendUtils.getHandler(pWiki, dbtype)
#     if wikiDataFactory is None:
#         raise NoDbHandlerException("Data handler %s not available" % dbtype)
#
#     wd = wikiDataFactory(pWiki, dataDir)
#     return WikiDataManager(pWiki, wd, dbtype)


def splitConfigPathAndWord(wikiCombinedFilename):
    """
    wikiCombinedFilename -- Path of config filename or possibly name of a wiki file

    return: tuple (cfg, wikiword) with cfg real config filepath (None if it
            couldn't be found. wikiword is the wikiword to jump to or None
    """
    wikiConfig = createWikiConfiguration()
    wikiConfigFilename = wikiCombinedFilename
    wikiWord = None

    while True:
        try:
            # config.read(wikiConfigFile)
            wikiConfig.loadConfig(wikiConfigFilename)
            return wikiConfigFilename, wikiWord
        except Exception, e:
            # try to recover by checking if the parent dir contains the real wiki file
            # if it does the current wiki file must be a wiki word file, so open the
            # real wiki to the wiki word.
#                 try:
            parentDir = os.path.dirname(os.path.dirname(wikiConfigFilename))
            if parentDir:
                wikiFiles = [file for file in os.listdir(parentDir) \
                        if file.endswith(".wiki")]
                if len(wikiFiles) > 0:
                    wikiWord = os.path.basename(wikiConfigFilename)
                    wikiWord = wikiWord[0:len(wikiWord)-5]

                    # if this is win95 or < the file name could be a 8.3 alias, file~1 for example
                    windows83Marker = wikiWord.find("~")
                    if windows83Marker != -1:
                        wikiWord = wikiWord[0:windows83Marker]
                        matchingFiles = [file for file in wikiFiles \
                                if file.lower().startswith(wikiWord)]
                        if matchingFiles:
                            wikiWord = matchingFiles[0]

                    wikiConfigFilename = os.path.join(parentDir, wikiFiles[0])
                    continue
#                         self.openWiki(join(parentDir, wikiFiles[0]), wikiWord)
            return None, None
    


# TODO Remove this hackish solution

class WikiDataSynchronizedFunction:
    def __init__(self, lock, function):
        self.accessLock = lock
        self.callFunction = function

    def __call__(self, *args, **kwargs):
        self.accessLock.acquire()
        try:
            # print "WikiDataSynchronizedFunction", repr(self.callFunction)
            return self.callFunction(*args, **kwargs)
        finally:
            self.accessLock.release()


class WikiDataSynchronizedProxy:
    """
    Proxy class for synchronized access to a WikiData instance
    """
    def __init__(self, wikiData):
        self.wikiData = wikiData
        self.accessLock = RLock()

    def __getattr__(self, attr):
        return WikiDataSynchronizedFunction(self.accessLock,
                getattr(self.wikiData, attr))


class WikiDataManager(MiscEventSourceMixin):
    """
    Wraps a WikiData object and provides services independent
    of database backend, especially creation of WikiPage objects.

    When the open wiki database changes, a new DataManager is created.

    When asking for a WikiPage for the same word twice and the first object
    exists yet, no new object is created, but the same returned.

    WikiDataManager holds internally a reference count to know how many
    PersonalWikiFrame instances refer to it. Call release() to
    decrement the refcount. If it goes to zero, the wrapped WikiData
    instance will be closed. The refcount starts with 1 when creating
    a WikiDataManager instance.
    """

    def __init__(self, wikiConfigFilename, wikiSyntax, dbtype):  #  dataDir, fileStorDir, dbtype, ):
        wikiConfig = createWikiConfiguration()
        self.connected = False
        wikiConfig.loadConfig(wikiConfigFilename)
        
#         while True:
#             try:
#                 # config.read(wikiConfigFile)
#                 wikiConfig.loadConfig(wikiConfigFilename)
#             except Exception, e:
#                 # try to recover by checking if the parent dir contains the real wiki file
#                 # if it does the current wiki file must be a wiki word file, so open the
#                 # real wiki to the wiki word.
#     #                 try:
#                 parentDir = os.path.dirname(os.path.dirname(wikiConfigFilename))
#                 if parentDir:
#                     wikiFiles = [file for file in os.listdir(parentDir) \
#                             if file.endswith(".wiki")]
#                     if len(wikiFiles) > 0:
#                         wikiWord = os.path.basename(wikiConfigFilename)
#                         wikiWord = wikiWord[0:len(wikiWord)-5]
#     
#                         # if this is win95 or < the file name could be a 8.3 alias, file~1 for example
#                         windows83Marker = wikiWord.find("~")
#                         if windows83Marker != -1:
#                             wikiWord = wikiWord[0:windows83Marker]
#                             matchingFiles = [file for file in wikiFiles \
#                                     if file.lower().startswith(wikiWord)]
#                             if matchingFiles:
#                                 wikiWord = matchingFiles[0]
#                         wikiConfigFilename = os.path.join(parentDir, wikiFiles[0])
#                         continue
# #                         self.openWiki(join(parentDir, wikiFiles[0]), wikiWord)
#                 raise
# 
#             break

#                 except Exception, ne:
#                     traceback.print_exc()
#                     self.displayErrorMessage(u"Error reading config file '%s'" %
#                             wikiConfigFilename, ne)
#                     return False

        # config variables
        wikiName = wikiConfig.get("main", "wiki_name")
        dataDir = wikiConfig.get("wiki_db", "data_dir")

        # except Exception, e:
        if wikiName is None or dataDir is None:
            raise BadConfigurationFileException(
                    "Wiki configuration file is corrupted")
#                 self.displayErrorMessage("Wiki configuration file is corrupted", e)
#                 # traceback.print_exc()
#                 return False

        # absolutize the path to data dir if it's not already
        if not os.path.isabs(dataDir):
            dataDir = os.path.join(os.path.dirname(wikiConfigFilename), dataDir)
            
        dataDir = mbcsDec(os.path.abspath(dataDir), "replace")[0]

        self.wikiConfigFilename = wikiConfigFilename

#         self.wikiName = wikiName
#         self.dataDir = dataDir
        
#         # create the db interface to the wiki data
#         wikiDataManager = None


        if not dbtype:
            wikidhName = wikiConfig.get("main",
                    "wiki_database_type", "")
        else:
            wikidhName = dbtype

        if not wikidhName:
            # Probably old database version without handler tag
            raise UnknownDbHandlerException(
                        'Required data handler %s not available' % wikidhName)

        if not isDbHandlerAvailable(wikidhName):
            raise DbHandlerNotAvailableException(
                    'Required data handler %s not available' % wikidhName)
#                 wikidhName = None
#         else:

#         wikiDataManager = WikiDataManager.openWikiDocument(self,
#                 wikidhName, dataDir, fileStorDir, self.wikiSyntax)

#         if not wikidhName:
#             wdhandlers = DbBackendUtils.listHandlers()
#             if len(wdhandlers) == 0:
#                 raise NoDbHandlerException(
#                         'No data handler available to open database.')
#                     self.displayErrorMessage(
#                             'No data handler available to open database.')
#                 return

#             # Ask for the data handler to use
#             index = wxGetSingleChoiceIndex(u"Choose database type",
#                     u"Choose database type", [wdh[1] for wdh in wdhandlers],
#                     self)
#             if index == -1:
#                 return
                
#             wikiDataManager = WikiDataManager.openWikiDocument(self,
#                     wdhandlers[index][0], dataDir, fileStorDir,
#                     self.wikiSyntax)


        self.wikiConfiguration = wikiConfig

        wikiDataFactory, createWikiDbFunc = DbBackendUtils.getHandler(wikidhName)
        if wikiDataFactory is None:
            raise NoDbHandlerException("Data handler %s not available" % wikidhName)

        wikiData = wikiDataFactory(self, dataDir)

        self.baseWikiData = wikiData
        self.wikiData = WikiDataSynchronizedProxy(self.baseWikiData)
        self.wikiPageDict = WeakValueDictionary()
        self.funcPageDict = WeakValueDictionary()

        self.wikiName = wikiName
        self.dataDir = dataDir
        self.dbtype = wikidhName

        self.refCount = 1
        
        self.formatting = WikiFormatting(self, wikiSyntax)  # TODO wikiSyntax

    
    def checkDatabaseFormat(self):
        """
        Returns a pair (<frmcode>, <plain text>) where frmcode is an integer
        and means:
        0: Up to date,  1: Update needed,  2: Unknown format, update not possible
        """
        return self.wikiData.checkDatabaseFormat()


    def connect(self):
        # Connect might be called too often, so check if it was already done
        if self.connected:
            return

        self.wikiData.connect()

        # Path to file storage
        fileStorDir = os.path.join(os.path.dirname(self.wikiConfigFilename),
                "files")

        self.fileStorage = FileStorage.FileStorage(self, fileStorDir)

        # Set file storage according to configuration
        fs = self.fileStorage

        fs.setModDateMustMatch(self.getWikiConfig().getboolean("main",
                "fileStorage_identity_modDateMustMatch", False))
        fs.setFilenameMustMatch(self.getWikiConfig().getboolean("main",
                "fileStorage_identity_filenameMustMatch", False))
        fs.setModDateIsEnough(self.getWikiConfig().getboolean("main",
                "fileStorage_identity_modDateIsEnough", False))

        self.wikiConfiguration.getMiscEvent().addListener(self)


        self.getFormatting().rebuildFormatting(None)
        self._updateCcWordBlacklist()
        
        self.noAutoSaveFlag = False # Flag is set (by PersonalWikiFrame),
                # if some error occurred during saving and the user doesn't want
                # to retry saving. WikiDataManager does not change or respect
                # this flag.
                
        self.autoReconnectTriedFlag = False
        
        self.connected = True


    def incRefCount(self):
        self.refCount += 1
        return self.refCount

    def release(self):
        """
        Inform this instance that it is no longer needed by one of the
        holding PersonalWikiFrame objects.
        Decrements the internal refcounter, if it goes to zero, the used
        WikiData instance is closed.
        
        Don't call any other method on the instance after calling this method.
        """
        global _openDocuments

        self.refCount -= 1

        if self.refCount <= 0:
            if self.wikiData is not None:
                self.wikiData.close()
                self.wikiData = None
                self.baseWikiData = None

            del _openDocuments[self.getWikiConfig().getConfigPath()]

        return self.refCount


    def getDbtype(self):
        return self.dbtype

    def getWikiData(self):
        return self.wikiData

    def getFileStorage(self):
        return self.fileStorage
        
    def getWikiConfig(self):
        return self.wikiConfiguration
        
    def getWikiConfigPath(self):
        return self.getWikiConfig().getConfigPath()

    def getFormatting(self):
        return self.formatting
        
    def getWikiName(self):
        return self.wikiName
        
    def getDataDir(self):
        return self.dataDir
        
    def getNoAutoSaveFlag(self):
        """
        Flag is set (by PersonalWikiFrame),
        if some error occurred during saving and the user doesn't want
        to retry saving. WikiDataManager does not change or respect
        this flag.
        """
        return self.noAutoSaveFlag
        
    def setNoAutoSaveFlag(self, val):
        self.noAutoSaveFlag = val
        # TODO send message?


    def getAutoReconnectTriedFlag(self):
        """
        Flag is set (by PersonalWikiFrame),
        if after some read/write error the program already tried to reconnect
        to database and should not automatically try again, only on user
        request.
        """
        return self.autoReconnectTriedFlag
        
    def setAutoReconnectTriedFlag(self, val):
        self.autoReconnectTriedFlag = val
        # TODO send message?


        
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
            
            value.getMiscEvent().addListener(self)

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
        global _globalFuncPages
        if funcTag.startswith("global/"):
            cacheDict = _globalFuncPages
        else:
            cacheDict = self.funcPageDict

        value = cacheDict.get(funcTag)
        if value is None:
            value = FunctionalPage(self, funcTag)
            if not value.getMiscEvent().hasListener(self):
                value.getMiscEvent().addListener(self)
            cacheDict[funcTag] = value

        return value


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
                try:
                    wikiPage = self.getWikiPageNoError(wikiWord)
                    if isinstance(wikiPage, AliasWikiPage):
                        # This should never be an alias page, so fetch the
                        # real underlying page
                        wikiPage = WikiPage(self, wikiWord)

                    wikiPage.update(wikiPage.getContent(), False)  # TODO AGA processing
                except:
                    traceback.print_exc()

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
        global _openDocuments
        
        try:        
            oldWikiPage = self.getWikiPage(wikiWord)
        except WikiWordNotFoundException:
            # So create page first
            oldWikiPage = self.createWikiPage(wikiWord)
            oldWikiPage.save(oldWikiPage.getLiveText())
            oldWikiPage.update(oldWikiPage.getLiveText())

        self.getWikiData().renameWord(wikiWord, toWikiWord)
        
        # TODO: Replace always?
        
        # Check if replacing previous title of page with new one

        # Prefix is normally u"++"
        pageTitlePrefix = self.getFormatting().getPageTitlePrefix() + u" "
        prevTitle = pageTitlePrefix + WikiPage.getWikiPageTitle(wikiWord) + u"\n"
        page = self.getWikiPage(toWikiWord)
        content = page.getLiveText()
        if content.startswith(prevTitle):
            # Replace previous title with new one
            content = pageTitlePrefix + WikiPage.getWikiPageTitle(toWikiWord) + \
                    u"\n" + content[len(prevTitle):]
            page.replaceLiveText(content)

        # if the root was renamed we have a little more to do
        if wikiWord == self.getWikiName():
            wikiConfig = self.getWikiConfig()
            wikiConfig.set("main", "wiki_name", toWikiWord)
            wikiConfig.set("main", "last_wiki_word", toWikiWord)
            wikiConfig.save()

            wikiConfigPath = wikiConfig.getConfigPath()
            # Unload wiki configuration file
            wikiConfig.loadConfig(None)

            # Rename config file
            renamedConfigPath = os.path.join(
                    os.path.dirname(wikiConfigPath),
                    u"%s.wiki" % toWikiWord)
            os.rename(wikiConfigPath, renamedConfigPath)

            # Load it again
            wikiConfig.loadConfig(renamedConfigPath)
            self.wikiName = toWikiWord
            
            # Update dict of open documents (= wiki data managers)
            del _openDocuments[wikiConfigPath]
            _openDocuments[renamedConfigPath] = self

        oldWikiPage.informRenamedWikiPage(toWikiWord)
        del self.wikiPageDict[wikiWord]

        if modifyText:
            # now we have to search the wiki files and replace the old word with the new
            searchOp = SearchReplaceOperation()
            searchOp.wikiWide = True
            searchOp.wildCard = 'no'
            searchOp.caseSensitive = True
            searchOp.searchStr = wikiWord

            for resultWord in self.searchWiki(searchOp):
                page = self.getWikiPage(resultWord)
                content = page.getLiveText()
                content = content.replace(wikiWord, toWikiWord)
#                 page.save(content)
#                 page.update(content, False)  # TODO AGA processing
                page.replaceLiveText(content)


    def searchWiki(self, sarOp, applyOrdering=True):  # TODO Threadholder
        """
        Search all wiki pages using the SearchAndReplaceOperation sarOp and
        return list of all page names that match the search criteria.
        If applyOrdering is True, the ordering of the sarOp is applied before
        returning the list.
        """
        wikiData = self.getWikiData()
        sarOp.beginWikiSearch(wikiData)
        try:
            # First search currently cached pages
            exclusionSet = sets.Set()
            preResultSet = sets.Set()
            
            for k in self.wikiPageDict.keys():
                wikiPage = self.wikiPageDict.get(k)
                if wikiPage is None:
                    continue
                    
                text = wikiPage.getLiveText()
                if sarOp.testWikiPage(k, text) == True:
                    preResultSet.add(k)
                
                exclusionSet.add(k)

            # Now search database
            resultSet = self.getWikiData().search(sarOp, exclusionSet)
            resultSet |= preResultSet
            if applyOrdering:
                result = sarOp.applyOrdering(resultSet, wxGetApp().getCollator())
            else:
                result = list(resultSet)

        finally:
            sarOp.endWikiSearch()
            
        return result


    def reconnect(self):
        """
        Closes current WikiData instance and opens a new one with the same
        settings. This should be called if connection was interrupted by a network
        problem or similar issues.
        """
        try:
            if self.wikiData is not None:
                self.wikiData.close()
        except:
            traceback.print_exc()

        self.autoReconnectTriedFlag = True
            
        self.wikiData = None
        self.baseWikiData = None

        wikiDataFactory, createWikiDbFunc = DbBackendUtils.getHandler(self.dbtype)
        if wikiDataFactory is None:
            raise NoDbHandlerException("Data handler %s not available" % self.dbtype)

        wikiData = wikiDataFactory(self, self.dataDir)

        self.baseWikiData = wikiData
        self.wikiData = WikiDataSynchronizedProxy(self.baseWikiData)
        
        # Reset flag so program automatically tries reconnecting on next error
        self.autoReconnectTriedFlag = False

        props = {"reconnected database": True,}
        self.fireMiscEventProps(props)


    def _updateCcWordBlacklist(self):
        """
        Update the blacklist of camelcase words which should show up as normal
        text.
        """
        pg = self.getFuncPage("global/[CCBlacklist]")
        bls = sets.Set(pg.getLiveText().split("\n"))
        pg = self.getFuncPage("wiki/[CCBlacklist]")
        bls.union_update(pg.getLiveText().split("\n"))
        self.getFormatting().setCcWordBlacklist(bls)


    def miscEventHappened(self, miscevt):
        """
        Handle misc events from DocPages
        """
        if miscevt.getSource() is self.wikiConfiguration:
            if miscevt.has_key("configuration changed"):
                self.getFormatting().rebuildFormatting(miscevt)
        else:
            # These messages come from (classes derived from) DocPages,
            # they are mainly relayed

            if miscevt.has_key_in(("updated wiki page", "deleted wiki page",
                    "renamed wiki page")):
                props = miscevt.getProps().copy()
                props["wikiPage"] = miscevt.getSource()
                self.fireMiscEventProps(props)
            elif miscevt.has_key("reread cc blacklist needed"):
                self._updateCcWordBlacklist()

                props = miscevt.getProps().copy()
                props["wikiPage"] = miscevt.getSource()
                self.fireMiscEventProps(props)
            elif miscevt.has_key("updated func page"):
                # This was send from a FuncPage object, send it again
                # The event also contains more specific information
                # handled by PersonalWikiFrame

                props = miscevt.getProps().copy()
                props["funcPage"] = miscevt.getSource()
                self.fireMiscEventProps(props)

                
            
        

