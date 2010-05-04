from __future__ import with_statement

from weakref import WeakValueDictionary
import os, os.path, time, shutil, traceback
from threading import RLock, Thread, Condition
from collections import deque

from pwiki.rtlibRepl import re  # Original re doesn't work right with
        # multiple threads

from wx import GetApp

import Consts
from pwiki.WikiExceptions import *

from pwiki.Utilities import TimeoutRLock, SingleThreadExecutor, DUMBTHREADSTOP

from pwiki.MiscEvent import MiscEventSourceMixin

from pwiki import ParseUtilities
from pwiki.StringOps import mbcsDec, re_sub_escape, pathEnc, pathDec, \
        unescapeWithRe, strToBool
from pwiki.DocPages import DocPage, WikiPage, FunctionalPage, AliasWikiPage
# from ..timeView.Versioning import VersionOverview

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
        raise WikiDBExistsException(
                _(u"Database exists already and is currently in use"))

    wikiDataFactory, createWikiDbFunc = DbBackendUtils.getHandler(dbtype)
    if wikiDataFactory is None:
        raise NoDbHandlerException(
                _(u"Data handler %s not available") % dbtype)

    createWikiDbFunc(wikiName, dataDir, overwrite)


def openWikiDocument(wikiConfigFilename, dbtype=None, wikiLang=None,
        ignoreLock=False, createLock=True):
    """
    Create a new instance of the WikiDataManager or return an already existing
    one
    dbtype -- internal name of database type
    wikiLang -- internal name of wiki language
    dataDir -- directory for storing the data files
    overwrite -- Should already existing data be overwritten
    """
    global _openDocuments

    wdm = _openDocuments.get(wikiConfigFilename)
    if wdm is not None:
        if dbtype is not None and dbtype != wdm.getDbtype():
            # Same database can't be opened twice with different db handlers
            raise WrongDbHandlerException(_(u"Database is already in use "
                    u'with database handler "%s". '
                    u"Can't open with different handler.") %
                    wdm.getDbtype())

        if wikiLang is not None and wikiLang != wdm.getWikiDefaultWikiLanguage():
            raise WrongWikiLanguageException(_(u"Database is already in use "
                    u'with wiki language handler "%s". '
                    u"Can't open with different handler.") %
                    wdm.getWikiDefaultWikiLanguage())

        wdm.incRefCount()
        return wdm

    wdm = WikiDataManager(wikiConfigFilename, dbtype, wikiLang, ignoreLock,
            createLock)

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
    wikiConfig = GetApp().createWikiConfiguration()
    if os.path.supports_unicode_filenames:
        wikiConfigFilename = mbcsDec(wikiCombinedFilename)[0]
    else:
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
                try:
                    wikiFiles = [file for file in os.listdir(parentDir) \
                            if file.endswith(".wiki")]
                    if len(wikiFiles) > 0:
                        wikiWord = os.path.basename(wikiConfigFilename)
                        wikiWord = wikiWord[0 : len(wikiWord) - 5]

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
                except (WindowsError, IOError, OSError):
                    # something went wrong -> give up
                    traceback.print_exc()
                    return None, None

            return None, None
    
    
def getGlobalFuncPage(funcTag):
    global _globalFuncPages
    
    if len(funcTag) == 0:
        return None  # TODO throw exception?

    if not funcTag.startswith(u"global/"):
        return None  # TODO throw exception?

    value = _globalFuncPages.get(funcTag)
    if value is None:
        value = FunctionalPage(None, funcTag)
        _globalFuncPages[funcTag] = value

    return value



# TODO Remove this hackish solution

# class WikiDataSynchronizedFunction:
#     def __init__(self, proxy, lock, function):
#         self.proxy = proxy
#         self.accessLock = lock
#         self.callFunction = function
# 
#     def __call__(self, *args, **kwargs):
#         return callInMainThread(self.callFunction, *args, **kwargs)


# class WikiDataSynchronizedFunction:
#     def __init__(self, proxy, lock, function):
#         self.proxy = proxy
#         self.accessLock = lock
#         self.callFunction = function
# 
#     def __call__(self, *args, **kwargs):
#         if not self.accessLock.acquire(False):
#             print "----Lock acquired by"
#             print "".join(traceback.format_list(self.proxy.accessLockStackTrace))
#             print 
#             print "----Lock requested by"
#             print traceback.print_stack()
#             print 
# 
#             self.accessLock.acquire()
#         
#         self.proxy.accessLockStackTrace = traceback.extract_stack()
#         try:
# #             print "WikiDataSynchronizedFunction", repr(self.callFunction), repr(args)
#             return callInMainThread(self.callFunction, *args, **kwargs)
#         finally:
# #             self.proxy.accessLockStackTrace = []
#             self.accessLock.release()


class WikiDataSynchronizedFunction:
    def __init__(self, proxy, lock, function):
        self.proxy = proxy
        self.proxyAccessLock = lock
        self.callFunction = function

    def __call__(self, *args, **kwargs):
#         if not self.proxyAccessLock.acquire(False):
#             print "----Lock acquired by"
#             print "".join(traceback.format_list(self.proxy.accessLockStackTrace))
#             print 
#             print "----Lock requested by"
#             print traceback.print_stack()
#             print 

        with self.proxyAccessLock:
#         self.proxy.accessLockStackTrace = traceback.extract_stack()
            return self.callFunction(*args, **kwargs)


class WikiDataSynchronizedProxy:
    """
    Proxy class for synchronized access to a WikiData instance
    """
    def __init__(self, wikiData):
        self.wikiData = wikiData
        self.proxyAccessLock = TimeoutRLock(Consts.DEADBLOCKTIMEOUT)
#         self.accessLockStackTrace = None


    def __getattr__(self, attr):
        result = WikiDataSynchronizedFunction(self, self.proxyAccessLock,
                getattr(self.wikiData, attr))
                
        self.__dict__[attr] = result

        return result


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

    def __init__(self, wikiConfigFilename, dbtype, wikiLangName, ignoreLock=False,
            createLock=True):
        MiscEventSourceMixin.__init__(self)

        self.lockFileName = wikiConfigFilename + u".lock"
        if not ignoreLock and os.path.exists(pathEnc(self.lockFileName)):
            raise LockedWikiException(
                    _(u"Wiki is probably already in use by other instance"))

        if createLock:
            try:
                f = open(pathEnc(self.lockFileName), "w")
                self.writeAccessDenied = False
                f.close()
            except IOError:
                self.lockFileName = None
                self.writeAccessDenied = True
        else:
            self.lockFileName = None

        wikiConfig = GetApp().createWikiConfiguration()
        self.connected = False
        self.readAccessFailed = False
        self.writeAccessFailed = False
        self.writeAccessDenied = False

        wikiConfig.loadConfig(wikiConfigFilename)

        # config variables
        wikiName = wikiConfig.get("main", "wiki_name")
        dataDir = wikiConfig.get("wiki_db", "data_dir")

        # except Exception, e:
        if wikiName is None or dataDir is None:
            self._releaseLockFile()
            raise BadConfigurationFileException(
                    _(u"Wiki configuration file is corrupted"))
        
        # os.access does not answer reliably if file is writable
        # (at least on Windows), therefore we have to just open it
        # in writable mode
        try:
            f = open(pathEnc(wikiConfigFilename), "r+b")
            self.writeAccessDenied = False
            f.close()
        except IOError:
            self.writeAccessDenied = True

        self.wikiConfiguration = wikiConfig

        wikiConfig.setWriteAccessDenied(self.writeAccessDenied or
                self.getWriteAccessDeniedByConfig())

        # absolutize the path to data dir if it's not already
        if not os.path.isabs(dataDir):
            dataDir = os.path.join(os.path.dirname(wikiConfigFilename), dataDir)

#         dataDir = mbcsDec(os.path.abspath(dataDir), "replace")[0]
        dataDir = pathDec(os.path.abspath(dataDir))

#         self.wikiConfigFilename = wikiConfigFilename

        if not dbtype:
            wikidhName = wikiConfig.get("main",
                    "wiki_database_type", "")
        else:
            wikidhName = dbtype

        if not wikidhName:
            # Probably old database version without handler tag
            self._releaseLockFile()
            raise UnknownDbHandlerException(
                    _(u'No data handler information found, probably '
                    u'"Original Gadfly" is right.'))

        if not isDbHandlerAvailable(wikidhName):
            self._releaseLockFile()
            raise DbHandlerNotAvailableException(
                    _(u'Required data handler "%s" unknown to WikidPad') % wikidhName)

        wikiDataFactory, createWikiDbFunc = DbBackendUtils.getHandler(wikidhName)
        if wikiDataFactory is None:
            self._releaseLockFile()
            raise NoDbHandlerException(
                    _(u'Error on initializing data handler "%s"') % wikidhName)

        if wikiLangName is None:
            wikiLangName = wikiConfig.get("main", "wiki_wikiLanguage",
                    "wikidpad_default_2_0")
        else:
            wikiConfig.set("main", "wiki_wikiLanguage", wikiLangName)

        if GetApp().getWikiLanguageDescription(wikiLangName) is None:
            self._releaseLockFile()
            raise UnknownWikiLanguageException(
                    _(u'Required wiki language handler "%s" not available') %
                            wikiLangName)

        self.wikiLangName = wikiLangName
        self.ensureWikiTempDir()

#         dbExecutor = GetApp().getDbExecutor()
#         wikiData = dbExecutor(wikiDataFactory, self, dataDir, self.getWikiTempDir())
        wikiData = wikiDataFactory(self, dataDir, self.getWikiTempDir())

        self.baseWikiData = wikiData
        self.autoLinkRelaxInfo = None
        
        # Set of camelcase words not to see as wiki words
        self.ccWordBlacklist = None
        self.wikiData = WikiDataSynchronizedProxy(self.baseWikiData)
        self.wikiPageDict = WeakValueDictionary()
        self.funcPageDict = WeakValueDictionary()
        
        self.updateExecutor = SingleThreadExecutor(3)
        self.pageRetrievingLock = TimeoutRLock(Consts.DEADBLOCKTIMEOUT)
#         self.pageUpdateDequeCondition = Condition()
#         self.pageUpdateDeque = deque()
#         self.pageUpdateThread = Thread(target=self._runUpdateQueue)

        self.wikiName = wikiName
        self.dataDir = dataDir
        self.dbtype = wikidhName

        self.refCount = 1


    
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

        writeException = None
        try:
            self.wikiData.connect()
        except DbWriteAccessError, e:
            traceback.print_exc()
            writeException = e

        # Path to file storage
        fileStorDir = os.path.join(os.path.dirname(self.getWikiConfigPath()),
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
        GetApp().getMiscEvent().addListener(self)

        self._updateCcWordBlacklist()
        
        self.readAccessFailed = False
        self.writeAccessFailed = False
        self.noAutoSaveFlag = False # Flag is set (by PersonalWikiFrame),
                # if some error occurred during saving and the user doesn't want
                # to retry saving. WikiDataManager does not change or respect
                # this flag.
                
        self.autoReconnectTriedFlag = False
        
        self.connected = True
        
        if writeException:
            self.writeAccessFailed = True
            raise writeException
            
        self.updateExecutor.start()
        
        self.pushDirtyMetaDataUpdate()
        
#         if not self.isReadOnlyEffect():
#             words = self.getWikiData().getWikiWordsForMetaDataState(0)
#             for word in words:
#                 self.updateExecutor.executeAsync(1, self._runDatabaseUpdate,
#                         word)

    def _runDatabaseUpdate(self, word, step, threadstop=DUMBTHREADSTOP):
        time.sleep(0.1)
        try:
            page = self.getWikiPage(word)

            if step == Consts.WIKIWORDMETADATA_STATE_DIRTY and \
                    page.runDatabaseUpdate(step=step, threadstop=threadstop):
                self.updateExecutor.executeAsyncWithThreadStop(1, self._runDatabaseUpdate,
                        word, Consts.WIKIWORDMETADATA_STATE_ATTRSPROCESSED)
            else:
                page.runDatabaseUpdate(step=step, threadstop=threadstop)

        except WikiWordNotFoundException:
            return


    def incRefCount(self):
        self.refCount += 1
        return self.refCount

    def _releaseLockFile(self):
        """
        Release lock file if it was created before
        """
        if self.lockFileName is not None:
            try:
                os.unlink(pathEnc(self.lockFileName))
            except:
                traceback.print_exc()


    def release(self):
        """
        Inform this instance that it is no longer needed by one of the
        holding PersonalWikiFrame objects.
        Decrements the internal refcounter, if it goes to zero, the used
        WikiData instance is closed, cached wiki pages are invalidated.
        
        Don't call any other method on the instance after calling this method.
        """
        global _openDocuments

        self.refCount -= 1

        if self.refCount <= 0:
            self.updateExecutor.end(hardEnd=True)  # TODO Inform user as this may take some time

            # Invalidate all cached pages to prevent yet running threads from
            # using them
            for page in self.wikiPageDict.values():
                page.invalidate()
            for page in self.funcPageDict.values():
                page.invalidate()
            
            wikiTempDir = self.getWikiTempDir()

            if self.wikiData is not None:
                self.wikiData.close()
                self.wikiData = None
                self.baseWikiData = None

            GetApp().getMiscEvent().removeListener(self)

            del _openDocuments[self.getWikiConfig().getConfigPath()]

            self._releaseLockFile()

            if wikiTempDir is not None:
                # Warning!!! rmtree() is very dangerous, don't make a mistake here!
                shutil.rmtree(wikiTempDir, True)

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
        return self.wikiConfiguration.getConfigPath()
        
    def getWikiPath(self):
        return os.path.dirname(self.getWikiConfigPath())        

    def getWikiName(self):
        return self.wikiName
        
    def getDataDir(self):
        return self.dataDir
        
    def getCollator(self):
        return GetApp().getCollator()
        
    def getWikiDefaultWikiLanguage(self):
        """
        Returns the internal name of the default wiki language of this wiki.
        
        Single pages may have different languages (not implemented yet).
        """
        return self.getWikiConfig().get("main", "wiki_wikiLanguage",
                "wikidpad_default_2_0")

    def getPageTitlePrefix(self):
        """
        Return the default prefix for a wiki page main title.
        By default, it is u"++ "
        """
        return unescapeWithRe(self.getWikiConfig().get(
                "main", "wikiPageTitlePrefix", "++"))

    def getWikiTempDir(self):
#         if GetApp().getGlobalConfig().getboolean("main", "tempFiles_inWikiDir",
#                 False) and not self.isReadOnlyEffect():
#             return os.path.join(os.path.dirname(self.getWikiConfigPath()),
#                     "temp")
#         else:

        # Warning! The returned directory will be deleted with shutil.rmtree when the wiki is
        # finally released!
        return None


    def ensureWikiTempDir(self):
        """
        Try to ensure existence of wiki temp directory
        """
        tempDir = self.getWikiTempDir()
        
        if tempDir is not None:
            try:
                os.makedirs(tempDir)
            except OSError:
                self.setReadAccessFailed(True)

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


    def getReadAccessFailed(self):
        """
        Flag is set (by PersonalWikiFrame),
        """
        return self.readAccessFailed
        
    def setReadAccessFailed(self, val):
        self.readAccessFailed = val
        # TODO send message?


    def getWriteAccessFailed(self):
        """
        Flag is set (by PersonalWikiFrame),
        """
        return self.writeAccessFailed
        
    def setWriteAccessFailed(self, val):
        self.writeAccessFailed = val
        # TODO send message?
        
    def getWriteAccessDenied(self):
        """
        Flag is set (by PersonalWikiFrame),
        """
        return self.writeAccessDenied
        
    def getWriteAccessDeniedByConfig(self):
        return self.getWikiConfig().getboolean("main", "wiki_readOnly")


    def setWriteAccessDeniedByConfig(self, newValue):
        wikiConfig = self.getWikiConfig()

        if wikiConfig.getboolean("main", "wiki_readOnly") == newValue:
            return

        if self.writeAccessFailed or self.writeAccessDenied:
            return  # Don't touch if readonly for other reasons

        if newValue:
            wikiConfig.set("main", "wiki_readOnly", "True")
            wikiConfig.setWriteAccessDenied(True)
        else:
            wikiConfig.setWriteAccessDenied(False)
            wikiConfig.set("main", "wiki_readOnly", "False")


#     STOPUPDATEOBJECT = object()
# 
#     def _runUpdateQueue(self):
#         while True:
#             with self.pageUpdateDequeCondition:
#                 while len(self.pageUpdateDeque) == 0:
#                     self.pageUpdateDequeCondition.wait()
# 
#                 page = self.pageUpdateDeque.pop()
# 
#             try:
#                 if page is WikiDataManager.STOPUPDATEOBJECT:
#                     # We should stop here, but the problem is that previously
#                     # updated pages may have pushed itself back on the deque
#                     # and must be processed before thread can end
#                     with self.pageUpdateDequeCondition:
#                         if len(self.pageUpdateDeque) == 0:
#                             return
#                         else:
#                             self.pushUpdatePage(WikiDataManager.STOPUPDATEOBJECT)
#                             continue
# 
#                 page.runDatabaseUpdate()
# #                 with self.pageUpdateDequeCondition:
# #                     for p in self.pageUpdateDeque:
# #                         if p is page:
# #                             break
# #                     else:
#                         
#                 
#             except:
#                 traceback.print_exc()


    def pushUpdatePage(self, page):
        self.updateExecutor.executeAsyncWithThreadStop(0, page.runDatabaseUpdate)
#         with self.pageUpdateDequeCondition:
#             self.pageUpdateDeque.appendleft(page)
#             self.pageUpdateDequeCondition.notify()


    def getUpdateExecutor(self):
        return self.updateExecutor
        
        
    def pushDirtyMetaDataUpdate(self):
        """
        Push all words for which meta-data is set dirty in the queue
        of the update executor
        """
        if not self.isReadOnlyEffect():
            self.updateExecutor.clearDeque(1)
            if not strToBool(self.getWikiData().getDbSettingsValue(
                    "syncWikiWordMatchtermsUpToDate", "0")):

                for wikiWord in self.getWikiData().getAllDefinedWikiPageNames():
                    wikiPage = self._getWikiPageNoErrorNoCache(wikiWord)
                    if isinstance(wikiPage, AliasWikiPage):
                        # This should never be an alias page, so fetch the
                        # real underlying page
                        # This can only happen if there is a real page with
                        # the same name as an alias
                        wikiPage = WikiPage(self, wikiWord)
    
                    wikiPage.refreshSyncUpdateMatchTerms()

                self.getWikiData().setDbSettingsValue(
                        "syncWikiWordMatchtermsUpToDate", "1")

            words0 = self.getWikiData().getWikiWordsForMetaDataState(
                    Consts.WIKIWORDMETADATA_STATE_DIRTY)
            words1 = self.getWikiData().getWikiWordsForMetaDataState(
                    Consts.WIKIWORDMETADATA_STATE_ATTRSPROCESSED)

            with self.updateExecutor.getDequeCondition():
                for word in words0:
                    self.updateExecutor.executeAsyncWithThreadStop(1, self._runDatabaseUpdate,
                            word, Consts.WIKIWORDMETADATA_STATE_DIRTY)
    
                for word in words1:
                    self.updateExecutor.executeAsyncWithThreadStop(1, self._runDatabaseUpdate,
                            word, Consts.WIKIWORDMETADATA_STATE_ATTRSPROCESSED)

    def isReadOnlyEffect(self):
        """
        Return true if underlying wiki is effectively read-only, this means
        "for any reason", regardless if error or intention.
        """
        return self.writeAccessFailed or self.writeAccessDenied or \
                self.getWriteAccessDeniedByConfig()


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


    def isDefinedWikiPage(self, wikiWord):
        """
        Check if a page with this name exists (no aliases)
        """
        return self.wikiData.isDefinedWikiPage(wikiWord)


    def isDefinedWikiLink(self, wikiWord):
        """
        check if a word is a valid wikiword (page name or alias)
        """
        return self.wikiData.isDefinedWikiLink(wikiWord)


    # For plugin compatibility
    isDefinedWikiWord = isDefinedWikiLink

    def isCreatableWikiWord(self, wikiWord):
        """
        Returns True if wikiWord can be created in the database. Does not
        check against regular expression of wiki language, but checks if word
        already exists or (if document is in caseless mode) if word with
        different case but otherwise the same already exists.
        If this returns False, self.getUnAliasedWikiWord(wikiWord) must be able to
        return the existing word whose existence prevents creation of wikiWord

        TODO: Check against existing aliases
        """
        # TODO: Caseless mode
#         return not self.wikiData.isDefinedWikiWord(wikiWord)
        return not self.getUnAliasedWikiWord(wikiWord)


    def getNormcasedWikiWord(self, word):
        """
        Get normcased version of word. It isn't checked if word exists.
        Currently this function just calls word.lower().
        """
        return word.lower()

    def getAllDefinedWikiPageNames(self):
        """
        get the names of all wiki pages in the db, no aliases, no functional
        pages.
        Function must work for read-only wiki.
        """
        return self.wikiData.getAllDefinedWikiPageNames()


    def getWikiPage(self, wikiWord):
        """
        Fetch a WikiPage for the wikiWord, throws WikiWordNotFoundException
        if word doesn't exist
        """
        with self.pageRetrievingLock:
            if not self.isDefinedWikiLink(wikiWord):
                raise WikiWordNotFoundException(
                        _(u"Word '%s' not in wiki") % wikiWord)
    
            return self.getWikiPageNoError(wikiWord)


    def getWikiPageNoError(self, wikiWord):
        """
        fetch a WikiPage for the wikiWord. If it doesn't exist, return
        one without throwing an error.

        Asking for the same wikiWord twice returns the same object if
        it wasn't garbage collected yet.
        """
        with self.pageRetrievingLock:
#             value = self.wikiPageDict.get(wikiWord)
#             
#             if value is not None and isinstance(value, AliasWikiPage):
#                 # Check if existing alias page is up to date
#                 realWikiWord1 = value.getNonAliasPage().getWikiWord()
#                 realWikiWord2 = self.wikiData.getUnAliasedWikiWord(wikiWord)
# 
#                 if realWikiWord1 != realWikiWord2:
#                     # if not, retrieve new page
#                     value = None
# 
#             if value is None:
#                 # No active page available
#                 realWikiWord = self.getUnAliasedWikiWordOrAsIs(wikiWord)
#                 if wikiWord == realWikiWord:
#                     # no alias
#                     value = WikiPage(self, wikiWord)
#                 else:
#                     realpage = self.getWikiPageNoError(realWikiWord)
#                     value = AliasWikiPage(self, wikiWord, realpage)


            value = self._getWikiPageNoErrorNoCache(wikiWord)
            
            self.wikiPageDict[wikiWord] = value

            if not value.getMiscEvent().hasListener(self):
                value.getMiscEvent().addListener(self)

        return value


    def _getWikiPageNoErrorNoCache(self, wikiWord):
        """
        Similar to getWikiPageNoError, but does not save retrieved
        page in cache if it isn't there yet.
        """
        if wikiWord is None:
            raise InternalError("None as wikiWord for "
                    "WikiDocument._getWikiPageNoErrorNoCache")

        with self.pageRetrievingLock:
            value = self.wikiPageDict.get(wikiWord)
    
            if value is not None and isinstance(value, AliasWikiPage):
                # Check if existing alias page is up to date
                realWikiWord1 = value.getNonAliasPage().getWikiWord()
                realWikiWord2 = self.wikiData.getUnAliasedWikiWord(wikiWord)
                
                if realWikiWord1 != realWikiWord2:
                    # if not, retrieve new page
                    value = None
            
            if value is None:
                # No active page available
                realWikiWord = self.getUnAliasedWikiWordOrAsIs(wikiWord)
#                 print "--_getWikiPageNoErrorNoCache13", repr((wikiWord, realWikiWord))
                if wikiWord == realWikiWord:
                    # no alias
                    value = WikiPage(self, wikiWord)
                else:
                    realpage = self.getWikiPageNoError(realWikiWord)
                    value = AliasWikiPage(self, wikiWord, realpage)
    
            return value



    def createWikiPage(self, wikiWord, suggNewPageTitle=None):
        """
        Create a new wikiPage for the wikiWord.
        suggNewPageTitle -- if not None contains the title of the page to create
                (without syntax specific prefix).
        """
        with self.pageRetrievingLock:
            page = self.getWikiPageNoError(wikiWord)
            page.setSuggNewPageTitle(suggNewPageTitle)
            return page


    def getFuncPage(self, funcTag):
        """
        Retrieve a functional page
        """
        global _globalFuncPages

        with self.pageRetrievingLock:
            if funcTag.startswith(u"global/"):
                value = getGlobalFuncPage(funcTag)
            else:
                value = self.funcPageDict.get(funcTag)
                if value is None:
                    value = FunctionalPage(self, funcTag)
                    self.funcPageDict[funcTag] = value
    
            if not value.getMiscEvent().hasListener(self):
                value.getMiscEvent().addListener(self)
    
            return value

#     def getVersionOverview(self, unifName):
#         """
#         Get the version overview for an object with name unifName.
#         """
#         value = self.versionOverviewDict.get(unifName)
#         if value is None:
#             value = VersionOverview(self, unifName)
#             value.readOverview()
#             self.versionOverviewDict[unifName] = value
#         
#         return value
#     
#     def getExistingVersionOverview(self, unifName):
#         """
#         Get the version overview for an object with name unifName. If a
#         version overview wasn't created already (in database or cache),
#         None is returned.
#         """
#         value = self.versionOverviewDict.get(unifName)
#         if value is None:
#             value = VersionOverview(self, unifName)
#             if value.isNotInDatabase():
#                 return None
# 
#             value.readOverview()
#             self.versionOverviewDict[unifName] = value
#         
#         return value


    # Datablock function delegates
    def getDataBlockUnifNamesStartingWith(self, startingWith):
        """
        Return all unified names starting with startingWith (case sensitive)
        """
        return self.wikiData.getDataBlockUnifNamesStartingWith(startingWith)

    def hasDataBlock(self, unifName):
        """
        Return if datablock exists
        """
        # TODO Create native method in WikiData classes
        return self.retrieveDataBlock(unifName, default=None) is not None


    def retrieveDataBlock(self, unifName, default=""):
        """
        Retrieve data block as binary string.
        """
        return self.wikiData.retrieveDataBlock(unifName, default=default)

    def retrieveDataBlockAsText(self, unifName, default=u""):
        """
        Retrieve data block as unicode string (assuming it was encoded properly)
        and with normalized line-ending (Un*x-style).
        """
        return self.wikiData.retrieveDataBlockAsText(unifName, default=default)

    def storeDataBlock(self, unifName, newdata, storeHint=None):
        """
        Store newdata under unified name. If previously data was stored under the
        same name, it is deleted.
        
        unifName -- unistring. Unified name to store data under
        newdata -- Data to store, either bytestring or unistring. The latter one
            will be converted using utf-8 before storing and the file gets
            the appropriate line-ending of the OS for external data blocks .
        storeHint -- Hint if data should be stored intern in table or extern
            in a file (using DATABLOCK_STOREHINT_* constants from Consts.py).
        """
        return self.wikiData.storeDataBlock(unifName, newdata, storeHint)

    def deleteDataBlock(self, unifName):
        """
        Delete data block with the associated unified name. If the unified name
        is not in database, nothing happens.
        """
        return self.wikiData.deleteDataBlock(unifName)



    # TODO Remove if not needed
    def checkFileSignatureForWikiWordAndMarkDirty(self, word):
        """
        First checks if file signature is valid, if not, the
        "metadataprocessed" field of the word is set to 0 to mark
        meta-data as not up-to-date. At last the signature is
        refreshed.
        
        This all is done inside the lock of the WikiData so it is
        somewhat atomically.
        """
        if self.isReadOnlyEffect():
            return True  # TODO Error message?

        wikiData = self.getWikiData()
        
        proxyAccessLock = getattr(wikiData, "proxyAccessLock", None)
        if proxyAccessLock is not None:
            proxyAccessLock.acquire()
        try:
            valid = wikiData.validateFileSignatureForWord(word)

            if not valid:
                wikiData.setMetaDataState(word,
                        Consts.WIKIWORDMETADATA_STATE_DIRTY)
                wikiData.refreshFileSignatureForWord(word)

                wikiPage = self.wikiPageDict.get(word)
                if wikiPage is not None:
                    wikiPage.markTextChanged()

            return valid
        finally:
            if proxyAccessLock is not None:
                proxyAccessLock.release()

    def checkFileSignatureForAllWikiWordsAndMarkDirty(self):
        if self.isReadOnlyEffect():
            return True  # TODO Error message?

        wikiData = self.getWikiData()
        
        proxyAccessLock = getattr(wikiData, "proxyAccessLock", None)
        if proxyAccessLock is not None:
            proxyAccessLock.acquire()
        try:
            for word in self.getAllDefinedWikiPageNames():
                if not wikiData.validateFileSignatureForWord(word):
                    wikiData.setMetaDataState(word,
                            Consts.WIKIWORDMETADATA_STATE_DIRTY)
                    wikiData.refreshFileSignatureForWord(word)

                    wikiPage = self.wikiPageDict.get(word)
                    if wikiPage is not None:
                        wikiPage.markTextChanged()
        finally:
            if proxyAccessLock is not None:
                proxyAccessLock.release()



    def initiateFullUpdate(self, progresshandler):
        self.updateExecutor.end(hardEnd=True)
        self.getWikiData().refreshDefinedContentNames()

        # get all of the wikiWords
        wikiWords = self.getWikiData().getAllDefinedWikiPageNames()

        progresshandler.open(len(wikiWords) + 1)

        try:
            step = 0

            # Update search terms which are generated synchronously.
            #   Some of them are essential to find anything or to follow
            #   links.
            for wikiWord in wikiWords:
                progresshandler.update(step, _(u"Update basic link info"))
                wikiPage = self._getWikiPageNoErrorNoCache(wikiWord)
                if isinstance(wikiPage, AliasWikiPage):
                    # This should never be an alias page, so fetch the
                    # real underlying page
                    # This can only happen if there is a real page with
                    # the same name as an alias
                    wikiPage = WikiPage(self, wikiWord)

                wikiPage.refreshSyncUpdateMatchTerms()
                
                step += 1
            
            self.getWikiData().setDbSettingsValue(
                    "syncWikiWordMatchtermsUpToDate", "1")
            
            progresshandler.update(step, _(u"Starting update thread"))

            self.updateExecutor.start()

            self.getWikiData().fullyResetMetaDataState()
            self.pushDirtyMetaDataUpdate()

        finally:
            progresshandler.close()
            self.updateExecutor.start()



    def rebuildWiki(self, progresshandler, onlyDirty):
        """
        Rebuild  the wiki

        progresshandler -- Object, fulfilling the
            PersonalWikiFrame.GuiProgressHandler protocol
        """
        self.updateExecutor.end(hardEnd=True)
        self.getWikiData().refreshDefinedContentNames()

        if onlyDirty:
            wikiWords = self.getWikiData().getWikiWordsForMetaDataState(
                    Consts.WIKIWORDMETADATA_STATE_DIRTY) + \
                    self.getWikiData().getWikiWordsForMetaDataState(
                    Consts.WIKIWORDMETADATA_STATE_ATTRSPROCESSED)
        else:
            # get all of the wikiWords
            wikiWords = self.getWikiData().getAllDefinedWikiPageNames()

        progresshandler.open(len(wikiWords) * 3 + 1)
#         progresshandler.update(0, _(u"Waiting for update thread to end"))

        # re-save all of the pages
        try:
            step = 1

            if not onlyDirty:
                self.getWikiData().setDbSettingsValue(
                        "syncWikiWordMatchtermsUpToDate", "0")
                self.getWikiData().clearCacheTables()
            
            # Step one: update search terms which are generated synchronously.
            #   Some of them are essential to find anything or to follow
            #   links.
            for wikiWord in wikiWords:
                progresshandler.update(step, _(u"Update basic link info"))
                wikiPage = self._getWikiPageNoErrorNoCache(wikiWord)
                if isinstance(wikiPage, AliasWikiPage):
                    # This should never be an alias page, so fetch the
                    # real underlying page
                    # This can only happen if there is a real page with
                    # the same name as an alias
                    wikiPage = WikiPage(self, wikiWord)

                wikiPage.refreshSyncUpdateMatchTerms()
                
                step += 1

            self.getWikiData().setDbSettingsValue(
                    "syncWikiWordMatchtermsUpToDate", "1")

            # Step two: update attributes. There may be attributes which
            #   define how the rest has to be interpreted, therefore they
            #   must be processed first.
            for wikiWord in wikiWords:
                progresshandler.update(step, _(u"Update attributes of %s") % wikiWord)
                try:
                    wikiPage = self._getWikiPageNoErrorNoCache(wikiWord)
                    if isinstance(wikiPage, AliasWikiPage):
                        # This should never be an alias page, so fetch the
                        # real underlying page
                        # This can only happen if there is a real page with
                        # the same name as an alias
                        wikiPage = WikiPage(self, wikiWord)

                    wikiPage.refreshSyncUpdateMatchTerms()
                    pageAst = wikiPage.getLivePageAst()

                    self.getWikiData().refreshFileSignatureForWord(wikiWord)
                    wikiPage.refreshAttributesFromPageAst(pageAst)
                except:
                    traceback.print_exc()

                step += 1

            # Step three: update the rest (todos, relations)
            for wikiWord in wikiWords:
                progresshandler.update(step, _(u"Update page %s") % wikiWord)
                try:
                    wikiPage = self._getWikiPageNoErrorNoCache(wikiWord)
                    if isinstance(wikiPage, AliasWikiPage):
                        # This should never be an alias page, so fetch the
                        # real underlying page
                        # This can only happen if there is a real page with
                        # the same name as an alias
                        wikiPage = WikiPage(self, wikiWord)

                    pageAst = wikiPage.getLivePageAst()

                    wikiPage.refreshMainDbCacheFromPageAst(pageAst)
                except:
                    traceback.print_exc()

                step += 1

            progresshandler.update(step - 1, _(u"Final cleanup"))
            # Give possibility to do further reorganisation
            # specific to database backend
            self.getWikiData().cleanupAfterRebuild(progresshandler)

            self.pushDirtyMetaDataUpdate()

        finally:
            progresshandler.close()
            self.updateExecutor.start()



    def getWikiWordSubpages(self, wikiWord):
        return self.getWikiData().getWikiLinksStartingWith(wikiWord + u"/")


    def buildRenameSeqWithSubpages(self, fromWikiWord, toWikiWord):
        """
        Returns a sequence of tuples (fromWikiWord, toWikiWord).
        May return None if one or more toWikiWords already exist and would be
        overwritten.
        
        It is (or will become) important that the renaming is processed
        in the order given by the returned sequence.
        """
        langHelper = GetApp().createWikiLanguageHelper(
                self.getWikiDefaultWikiLanguage())

        errMsg = langHelper.checkForInvalidWikiWord(toWikiWord, self)

        if errMsg:
            raise WikiDataException(_(u"'%s' is an invalid wiki word. %s") %
                    (toWikiWord, errMsg))

        # Build dictionary of renames
        renameDict = {}

        if self.isDefinedWikiPage(fromWikiWord):
            # If fromWikiWord exists (not mandatory) it must be renamed, too
            renameDict[fromWikiWord] = toWikiWord

        for subPageName in self.getWikiWordSubpages(fromWikiWord):
            renameDict[subPageName] = toWikiWord + subPageName[len(fromWikiWord):]

        # Check for renames with errors
        errorRenames = []

        toSet = set()
        sameToSet = set()
        
        for key, value in renameDict.iteritems():
            if self.isDefinedWikiPage(value):
                errorRenames.append((key, value,
                        RenameWikiWordException.PRB_TO_ALREADY_EXISTS))

            if value in toSet:
                sameToSet.add(value)
                continue
            toSet.add(value)
        
        if sameToSet:
            # Two or more words should be renamed to same word
            # List which ones
            errorRenames += [(key, value,
                    RenameWikiWordException.PRB_RENAME_TO_SAME)
                    for key, value in renameDict.iteritems()
                    if value in sameToSet]

        if errorRenames:
            raise RenameWikiWordException(errorRenames)

        return renameDict.items()


    def renameWikiWord(self, wikiWord, toWikiWord, modifyText):
        """
        modifyText -- Should the text of links to the renamed page be
                modified? This text replacement works unreliably
        """
        global _openDocuments
        
        langHelper = GetApp().createWikiLanguageHelper(
                self.getWikiDefaultWikiLanguage())

        errMsg = langHelper.checkForInvalidWikiWord(toWikiWord, self)

        if errMsg:
            raise WikiDataException(_(u"'%s' is an invalid wiki word. %s") %
                    (toWikiWord, errMsg))

        if self.isDefinedWikiLink(toWikiWord):
            raise WikiDataException(
                    _(u"Cannot rename '%s' to '%s', '%s' already exists") %
                    (word, toWikiWord, toWikiWord))

        try:        
            oldWikiPage = self.getWikiPage(wikiWord)
        except WikiWordNotFoundException:
            # So create page first
            oldWikiPage = self.createWikiPage(wikiWord)
            oldWikiPage.writeToDatabase()

        self.getWikiData().renameWord(wikiWord, toWikiWord)
        
        # TODO: Replace always?
        
        # Check if replacing previous title of page with new one

        # Prefix is normally u"++"
        pageTitlePrefix = self.getPageTitlePrefix() + u" "
        wikiWordTitle = self.getWikiPageTitle(wikiWord)
        
        if wikiWordTitle is not None:
            prevTitle = pageTitlePrefix + self.getWikiPageTitle(wikiWord) + u"\n"
        else:
            prevTitle = None

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

        oldWikiPage.renameVersionData(toWikiWord)
        oldWikiPage.informRenamedWikiPage(toWikiWord)
        del self.wikiPageDict[wikiWord]

        if modifyText:
            # now we have to search the wiki files and replace the old word with the new
            sarOp = SearchReplaceOperation()
            sarOp.wikiWide = True
            sarOp.wildCard = 'regex'
            sarOp.caseSensitive = True
            sarOp.searchStr = ur"\b" + re.escape(wikiWord) + ur"\b"
            
            for resultWord in self.searchWiki(sarOp):
                wikiPage = self.getWikiPage(resultWord)
                text = wikiPage.getLiveTextNoTemplate()
                if text is None:
                    continue

                sarOp.replaceStr = re_sub_escape(toWikiWord)
                sarOp.replaceOp = True
                sarOp.cycleToStart = False

                charStartPos = 0
    
                while True:
                    found = sarOp.searchText(text, charStartPos)
                    start, end = found[:2]
                    
                    if start is None: break
                    
                    repl = sarOp.replace(text, found)
                    text = text[:start] + repl + text[end:]  # TODO Faster?
                    charStartPos = start + len(repl)

                wikiPage.replaceLiveText(text)
#                 wikiPage.update(text)


        # Now we modify the page heading if not yet done by text replacing
        page = self.getWikiPage(toWikiWord)
        # But first update the match terms which need synchronous updating
        page.refreshSyncUpdateMatchTerms()

        content = page.getLiveText()
        if prevTitle is not None and content.startswith(prevTitle):
            # Replace previous title with new one
            content = pageTitlePrefix + self.getWikiPageTitle(toWikiWord) + \
                    u"\n" + content[len(prevTitle):]
            page.replaceLiveText(content)
#             page.update(content)


    # TODO threadstop?
    def getAutoLinkRelaxInfo(self):
        """
        Get regular expressions and words used to operate autoLink function in 
        "relax" mode
        """
        if self.autoLinkRelaxInfo is None:
            langHelper = GetApp().createWikiLanguageHelper(
                    self.getWikiDefaultWikiLanguage())

            self.autoLinkRelaxInfo = langHelper.buildAutoLinkRelaxInfo(self)

        return self.autoLinkRelaxInfo


    def getWikiPageTitle(self, wikiWord):
        """
        Return a title for a newly created page. It may return None if no title
        should be shown.
        """
        creaMode = self.getWikiConfig().getint("main",
                "wikiPageTitle_creationMode", 1)
        if creaMode == 0:
            # Let wikiword untouched
            return wikiWord
        elif creaMode == 1:
            # Add spaces before uppercase letters,
            # e.g. NewWikiWord -> New Wiki Word
            title = re.sub(ur'([A-Z\xc0-\xde]+)([A-Z\xc0-\xde][a-z\xdf-\xff])',
                    r'\1 \2', wikiWord)
            title = re.sub(ur'([a-z\xdf-\xff])([A-Z\xc0-\xde])', r'\1 \2',
                    title)
            return title
        else:  # creaMode == 2: No title at all.
            return None


    def searchWiki(self, sarOp, applyOrdering=True, threadstop=DUMBTHREADSTOP):  # TODO Threadholder
        """
        Search all wiki pages using the SearchAndReplaceOperation sarOp and
        return list of all page names that match the search criteria.
        If applyOrdering is True, the ordering of the sarOp is applied before
        returning the list.
        """
        wikiData = self.getWikiData()
        sarOp.beginWikiSearch(self)
        try:
            threadstop.testRunning()
            # First search currently cached pages
            exclusionSet = set()
            preResultSet = set()
            
            for k in self.wikiPageDict.keys():
                wikiPage = self.wikiPageDict.get(k)
                if wikiPage is None:
                    continue
                if isinstance(wikiPage, AliasWikiPage):
                    # Avoid to process same page twice (alias and real) or more often
                    continue
                    
                text = wikiPage.getLiveTextNoTemplate()
                if text is None:
                    continue

                if sarOp.testWikiPage(k, text) == True:
                    preResultSet.add(k)

                exclusionSet.add(k)

                threadstop.testRunning()

            # Now search database
            resultSet = self.getWikiData().search(sarOp, exclusionSet)
            threadstop.testRunning()
            resultSet |= preResultSet
            if applyOrdering:
                result = sarOp.applyOrdering(resultSet, self.getCollator())
            else:
                result = list(resultSet)

        finally:
            sarOp.endWikiSearch()

        threadstop.testRunning()
        return result


    def getWikiDefaultWikiPageFormatDetails(self):
        """
        According to currently stored settings and global attributes, returns a
        ParseUtilities.WikiPageFormatDetails object to describe
        default formatting details if a concrete wiki page is not available.
        """
        withCamelCase = strToBool(self.getGlobalAttributeValue(
                u"camelCaseWordsEnabled", True))

#         footnotesAsWws = self.getWikiConfig().getboolean(
#                 "main", "footnotes_as_wikiwords", False)

        autoLinkMode = self.getGlobalAttributeValue(
                u"auto_link", u"off").lower()

        paragraphMode = strToBool(self.getGlobalAttributeValue(
                u"paragraph_mode", False))

        langHelper = GetApp().createWikiLanguageHelper(
                self.getWikiDefaultWikiLanguage())

        wikiLanguageDetails = langHelper.createWikiLanguageDetails(
                self, None)

        return ParseUtilities.WikiPageFormatDetails(
                withCamelCase=withCamelCase,
                wikiDocument=self,
                basePage=None,
                autoLinkMode=autoLinkMode,
                paragraphMode=paragraphMode,
                wikiLanguageDetails=wikiLanguageDetails
                )


    @staticmethod
    def getUserDefaultWikiPageFormatDetails():
        """
        Return a ParseUtilities.WikiPageFormatDetails object to describe
        default formatting details if a concrete wiki document or wiki pages are
        not available. This method is static.
        """
        return ParseUtilities.WikiPageFormatDetails(
                withCamelCase=True,
#                 footnotesAsWws=False,
                wikiDocument=None,
                basePage=None,
                autoLinkMode=u"off",
                paragraphMode=False
                )


    def getWikiWordsModifiedWithin(self, startTime, endTime):
        """
        startTime and endTime are floating values as returned by time.time()
        startTime is inclusive, endTime is exclusive
        """
        return self.getWikiData().getWikiWordsModifiedWithin(startTime, endTime)


    def getWikiWordsModifiedLastDays(self, days):
        """
        Return wiki words modified during the last number of days.
        """
        endTime = time.time()
        startTime = float(endTime-(86400*days))
        
        return self.getWikiData().getWikiWordsModifiedWithin(startTime, endTime)


    def getCcWordBlacklist(self):
        return self.ccWordBlacklist

    def _updateCcWordBlacklist(self):
        """
        Update the blacklist of camelcase words which should show up as normal
        text.
        """
        pg = self.getFuncPage("global/CCBlacklist")
        bls = set(pg.getLiveText().split("\n"))
        pg = self.getFuncPage("wiki/CCBlacklist")
        bls.update(pg.getLiveText().split("\n"))
        self.ccWordBlacklist = bls


    def getUnAliasedWikiWord(self, word):
        """
        Resolve links to wiki words. Returns None if it can't be resolved
        """
        # TODO: Resolve properly in caseless mode
        return self.getWikiData().getUnAliasedWikiWord(word)

    
    def getUnAliasedWikiWordOrAsIs(self, word):
        """
        return the real word if word is an alias.
        returns word itself if word isn't an alias (may mean it's a real word
                or doesn't exist!)
        """
        result = self.getWikiData().getUnAliasedWikiWord(word)

        if result is None:
            return word

        return result


    def getTodos(self):
        """
        Return all todo entries as list of tuples (wikiword, todoEntry)
        """
        return self.getWikiData().getTodos()


    def getDistinctAttributeValuesByKey(self, key):
        """
        Function must work for read-only wiki.
        Return a list of all distinct used attribute values for a given key.
        """
        return self.getWikiData().getDistinctAttributeValues(key)
#         s = set(v for w, k, v in
#                 self.getWikiData().getAttributeTriples(None, key, None))
#         return list(s)

    getDistinctPropertyValuesByKey = getDistinctAttributeValuesByKey  # TODO remove "property"-compatibility


    def getAttributeTriples(self, word, key, value):
        """
        Function must work for read-only wiki.
        word, key and value can either be unistrings to search for or None as
        wildcard.
        """
        return self.getWikiData().getAttributeTriples(word, key, value)

    getPropertyTriples = getAttributeTriples  # TODO remove "property"-compatibility



    def getGlobalAttributeValue(self, attribute, default=None):
        """
        Function must work for read-only wiki.
        Finds the wiki-global setting of attribute, if any.
        Attribute itself must not contain the "global." prefix
        """
        return self.getWikiData().getGlobalAttributes().get(
                u"global." + attribute, default)
        
    getGlobalPropertyValue = getGlobalAttributeValue  # TODO remove "property"-compatibility


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
        self.autoLinkRelaxInfo = None

        wikiDataFactory, createWikiDbFunc = DbBackendUtils.getHandler(self.dbtype)
        if wikiDataFactory is None:
            raise NoDbHandlerException(
                    _(u"Data handler %s not available") % self.dbtype)

        self.ensureWikiTempDir()
#         dbExecutor = GetApp().getDbExecutor()
#         wikiData = dbExecutor(wikiDataFactory, self, self.dataDir, self.getWikiTempDir())
        wikiData = wikiDataFactory(self, self.dataDir, self.getWikiTempDir())

        self.baseWikiData = wikiData
        self.wikiData = WikiDataSynchronizedProxy(self.baseWikiData)
        
        self.wikiData.connect()
        
        # Reset flag so program automatically tries reconnecting on next error
        self.autoReconnectTriedFlag = False

        attrs = {"reconnected database": True,}
        self.fireMiscEventProps(attrs)




    def miscEventHappened(self, miscevt):
        """
        Handle misc events from DocPages
        """
        if miscevt.getSource() is self.wikiConfiguration:
            if miscevt.has_key("changed configuration"):
                attrs = miscevt.getProps().copy()
                attrs["changed wiki configuration"] = True
                self.fireMiscEventProps(attrs)                
        elif miscevt.getSource() is GetApp():
            if miscevt.has_key("reread cc blacklist needed"):
                self._updateCcWordBlacklist()
            elif miscevt.has_key("pause background threads"):
                self.updateExecutor.pause()
            elif miscevt.has_key("resume background threads"):
                self.updateExecutor.start()
        elif isinstance(miscevt.getSource(), DocPage):
            # These messages come from (classes derived from) DocPage,
            # they are mainly relayed

            if miscevt.has_key_in(("deleted wiki page", "renamed wiki page",
                    "pseudo-deleted wiki page")):
                self.autoLinkRelaxInfo = None
                attrs = miscevt.getProps().copy()
                attrs["wikiPage"] = miscevt.getSource()
                self.fireMiscEventProps(attrs)
            elif miscevt.has_key("updated wiki page"):
                self.autoLinkRelaxInfo = None  # TODO Does this slow down?
                attrs = miscevt.getProps().copy()
                attrs["wikiPage"] = miscevt.getSource()
                self.fireMiscEventProps(attrs)
            elif miscevt.has_key("saving new wiki page"):            
                self.autoLinkRelaxInfo = None
            elif miscevt.has_key("reread cc blacklist needed"):
                self._updateCcWordBlacklist()

                attrs = miscevt.getProps().copy()
                attrs["funcPage"] = miscevt.getSource()
                self.fireMiscEventProps(attrs)
            elif miscevt.has_key("updated func page"):
                # This was send from a FuncPage object, send it again
                # The event also contains more specific information
                # handled by PersonalWikiFrame
                attrs = miscevt.getProps().copy()
                attrs["funcPage"] = miscevt.getSource()

                self.fireMiscEventProps(attrs)



