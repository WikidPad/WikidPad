from __future__ import with_statement


from weakref import WeakValueDictionary
import os, os.path, time, shutil, traceback, ConfigParser
# from collections import deque

import re

from wx import GetApp

import Consts
from pwiki.WikiExceptions import *

from ..Utilities import TimeoutRLock, SingleThreadExecutor, DUMBTHREADSTOP

from ..MiscEvent import MiscEventSourceMixin

from .. import ParseUtilities
from .. import StringOps
from ..StringOps import mbcsDec, re_sub_escape, pathEnc, pathDec, \
        unescapeWithRe, strToBool, pathnameFromUrl, urlFromPathname, \
        relativeFilePath, getFileSignatureBlock
from ..DocPages import DocPage, WikiPage, FunctionalPage, AliasWikiPage
# from ..timeView.Versioning import VersionOverview

from ..timeView.WikiWideHistory import WikiWideHistory

from .. import AttributeHandling

from ..SearchAndReplace import SearchReplaceOperation

from .. import SpellChecker
from .. import Trashcan

import DbBackendUtils, FileStorage

# Some functions import parts of the whoosh library



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

    try:
        wikiConfig.loadConfig(wikiConfigFilename)
        return wikiConfigFilename, None
    except ConfigParser.ParsingError, e:
        # try to recover by checking if the parent dir contains the real wiki file
        # if it does the current wiki file must be a wiki word file, so open the
        # real wiki to the wiki word.
        wikiWord = None
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

                    wikiConfig.loadConfig(os.path.join(parentDir, wikiFiles[0]))
                    return os.path.join(parentDir, wikiFiles[0]), wikiWord
            except:
                pass

        # Either parent directory couldn't be constructed or something went
        # wrong in parent directory so return initial wikiConfigFilename
        # although the file is obviously corrupted but this is handled by
        # code PersonalWikiFrame.openWiki
        return wikiConfigFilename, None

    except Exception, e:
        # Something else went wrong (file not present or not accessible)
        traceback.print_exc()
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
    
    # Update executor queue for index search update
    UEQUEUE_INDEX = 2

    def __init__(self, wikiConfigFilename, dbtype, wikiLangName, ignoreLock=False,
            createLock=True, recoveryMode=False):
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
        self.writeAccessDenied = recoveryMode
        self.recoveryMode = recoveryMode

        try:
            wikiConfig.loadConfig(wikiConfigFilename)
        except ConfigParser.ParsingError, e:
            raise BadConfigurationFileException(
                    _(u"Wiki configuration file is corrupted"))

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

        dataDir = pathDec(os.path.abspath(dataDir))

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

        wikiData = wikiDataFactory(self, dataDir, self.getWikiTempDir())

        self.baseWikiData = wikiData
        self.autoLinkRelaxInfo = None

        # Set of camelcase words not to see as wiki words
        self.ccWordBlacklist = None
        self.nccWordBlacklist = None
        self.wikiData = WikiDataSynchronizedProxy(self.baseWikiData)
        self.wikiPageDict = WeakValueDictionary()
        self.funcPageDict = WeakValueDictionary()
        
        self.updateExecutor = SingleThreadExecutor(4)
        self.pageRetrievingLock = TimeoutRLock(Consts.DEADBLOCKTIMEOUT)
        self.wikiWideHistory = WikiWideHistory(self)
        
        if self.recoveryMode:
            if self.wikiData.checkCapability("recovery mode") is None:
                raise WikiDataException(_(u"Recovery mode not supported"))

        if not self.recoveryMode:
            self.wikiWideHistory.readOverview()

        self.wikiName = wikiName
        self.dataDir = dataDir
        self.dbtype = wikidhName

        self.whooshIndex = None

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
            if self.recoveryMode:
                self.wikiData.connect(recoveryMode=True)
            else:
                self.wikiData.connect()
        except DbWriteAccessError, e:
            traceback.print_exc()
            writeException = e

        # TODO: Only initialize on demand
        self.onlineSpellCheckerSession = None
        
        if not self.recoveryMode:
            if SpellChecker.isSpellCheckSupported():
                self.onlineSpellCheckerSession = \
                        SpellChecker.SpellCheckerSession(self)
                self.onlineSpellCheckerSession.rereadPersonalWordLists()

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

        if not self.recoveryMode:
            self._updateCcWordBlacklist()
            self._updateNccWordBlacklist()

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
            
        self.trashcan = Trashcan.Trashcan(self)
        
        if not self.recoveryMode:
            if self.trashcan.isInDatabase():
                try:
                    self.trashcan.readOverview()
                except:
                    traceback.print_exc() # TODO: Notify user?

        if not self.recoveryMode:
            if self.isSearchIndexEnabled() and self.getWikiConfig().getint(
                    "main", "indexSearch_formatNo", 1) != Consts.SEARCHINDEX_FORMAT_NO:
                # Search index rebuild needed
                # Remove old search index and lower meta data state.
                # The following pushDirtyMetaDataUpdate() will start rebuilding
    
                wikiData = self.getWikiData()
    
                wikiData.commit()
                finalState = Consts.WIKIWORDMETADATA_STATE_SYNTAXPROCESSED
    
                for wikiWord in wikiData.getWikiPageNamesForMetaDataState(
                        finalState, "<"):
                    wikiData.setMetaDataState(wikiWord, finalState)
    
                wikiData.commit()
                self.removeSearchIndex()
    
            self.pushDirtyMetaDataUpdate()

        self.updateExecutor.start()


#         if not self.isReadOnlyEffect():
#             words = self.getWikiData().getWikiPageNamesForMetaDataState(0)
#             for word in words:
#                 self.updateExecutor.executeAsync(1, self._runDatabaseUpdate,
#                         word)

    def _runDatabaseUpdate(self, word, step, threadstop=DUMBTHREADSTOP):
        time.sleep(0.1)
        try:
            page = self.getWikiPage(word)

            if step == Consts.WIKIWORDMETADATA_STATE_ATTRSPROCESSED:
                if page.runDatabaseUpdate(step=step, threadstop=threadstop):
                    if self.isSearchIndexEnabled():
                        self.updateExecutor.executeAsyncWithThreadStop(
                                self.UEQUEUE_INDEX,
                                self._runDatabaseUpdate, word,
                                Consts.WIKIWORDMETADATA_STATE_SYNTAXPROCESSED)

            elif step == Consts.WIKIWORDMETADATA_STATE_SYNTAXPROCESSED:
                if self.isSearchIndexEnabled():
                    page.runDatabaseUpdate(step=step, threadstop=threadstop)
            else:   # should be: step == Consts.WIKIWORDMETADATA_STATE_DIRTY:
                if page.runDatabaseUpdate(step=step, threadstop=threadstop):
                    self.updateExecutor.executeAsyncWithThreadStop(1,
                            self._runDatabaseUpdate, word,
                            Consts.WIKIWORDMETADATA_STATE_ATTRSPROCESSED)



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
            self.refCount = 0
            self.updateExecutor.end(hardEnd=True)  # TODO Inform user as this may take some time

            if self.trashcan is not None:
                self.trashcan.writeOverview()
                self.trashcan.close()
                self.trashcan = None
                
            self.wikiWideHistory.writeOverview()
            self.wikiWideHistory.close()

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
            
            if self.whooshIndex is not None:
                self.whooshIndex.close()
                self.whooshIndex = None

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
        
    def getTrashcan(self):
        return self.trashcan
        
    def getWikiWideHistory(self):
        return self.wikiWideHistory

    def getWikiDefaultWikiLanguage(self):
        """
        Returns the internal name of the default wiki language of this wiki.
        
        Single pages may have different languages (not implemented yet).
        """
        return self.getWikiConfig().get("main", "wiki_wikiLanguage",
                "wikidpad_default_2_0")

    def formatPageTitle(self, rawTitle, basePage=None):
        ptp = unescapeWithRe(self.getWikiConfig().get(
                "main", "wikiPageTitlePrefix", u""))
                
        level = self.getWikiConfig().getint("main",
                "wikiPageTitle_headingLevel", 0)
        
        if level > 0:
            langHelper = GetApp().createWikiLanguageHelper(
                    self.getWikiDefaultWikiLanguage())
    
            info = langHelper.formatSelectedText(rawTitle,
                    0, len(rawTitle), "plusHeading",
                    {"headingLevel": level, "titleSurrounding": u" "}) # TODO level

            if info is None:
                return ptp + u" " + rawTitle
    
            replacement, repStart, repAfterEnd, selStart, selAfterEnd = info[:5]
            
            return ptp + rawTitle[:repStart] + replacement + rawTitle[repAfterEnd:]
        else:
            return ptp + u" " + rawTitle



    def getPageTitlePrefix(self):
        """
        Return the default prefix for a wiki page main title.
        By default, it is u"++ "
        """
        return unescapeWithRe(self.getWikiConfig().get(
                "main", "wikiPageTitlePrefix", u"++"))

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


    def getOnlineSpellCheckerSession(self):
        return self.onlineSpellCheckerSession


    def createOnlineSpellCheckerSessionClone(self):
        if self.onlineSpellCheckerSession is None:
            return None
        
        return self.onlineSpellCheckerSession.cloneForThread()


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
            wikiConfig.save()
            wikiConfig.setWriteAccessDenied(True)
        else:
            wikiConfig.setWriteAccessDenied(False)
            wikiConfig.set("main", "wiki_readOnly", "False")


    def makeFileUrlAbsPath(self, fileurl):
        """
        Convert a relative or absolute file URL to an absolute path.
        Returns None if fileurl isn't "file:" or "rel:" protocol
        """
        if fileurl.startswith(u"rel://"):
            relpath = pathnameFromUrl(fileurl[6:], False)
            return os.path.abspath(os.path.join(os.path.dirname(
                    self.getWikiConfigPath()), relpath))
        elif fileurl.startswith(u"file:"):
            return os.path.abspath(pathnameFromUrl(fileurl))
        else:
            return None


    def makeRelUrlAbsolute(self, relurl, addSafe=''):
        """
        Return the absolute file: URL for a rel: URL
        """
        relurl, add = StringOps.decomposeUrlQsFrag(relurl)
        
        if relurl.startswith(u"rel://"):
            relpath = pathnameFromUrl(relurl[6:], False)

            url = u"file:" + urlFromPathname(
                    os.path.abspath(os.path.join(os.path.dirname(
                            self.getWikiConfigPath()), relpath)), addSafe=addSafe)

#             return url
            return StringOps.composeUrlQsFrag(url, add)
        elif relurl.startswith(u"wikirel://"):
            relpath = pathnameFromUrl(relurl[10:], False)

            url = u"wiki:" + urlFromPathname(
                    os.path.abspath(os.path.join(os.path.dirname(
                            self.getWikiConfigPath()), relpath)), addSafe=addSafe)

#             return url
            return StringOps.composeUrlQsFrag(url, add)


    def makeAbsPathRelUrl(self, absPath, addSafe=''):
        """
        Return the rel: URL for an absolute file path or None if
        a relative URL can't be created
        """
        locPath = self.getWikiConfigPath()

        if locPath is None:
            return None

        locPath = os.path.dirname(locPath)
        relPath = relativeFilePath(locPath, absPath)
        if relPath is None:
            return None

        return u"rel://" + urlFromPathname(relPath, addSafe=addSafe)


    def makeAbsUrlRelative(self, url, addSafe=''):
        """
        Return the relative rel: URL for a file: URL if possible.
        Returns None if url can't be converted
        """
        link, add = StringOps.decomposeUrlQsFrag(url)

        if link.startswith(u"file:"):
            link = self.makeAbsPathRelUrl(StringOps.pathnameFromUrl(
                    link), addSafe=addSafe)
            if link is None:
                return None  # Error message?
        elif link.startswith(u"wiki:"):
            link = self.makeAbsPathRelUrl(StringOps.pathnameFromUrl(
                    link), addSafe=addSafe)
            if link is None:
                return None  # Error message?
            else:
                link = u"wiki" + link  # Combines to "wikirel://"
        else:
            return None  # Error message?
            
        return StringOps.composeUrlQsFrag(link, add)



    def pushUpdatePage(self, page):
        self.updateExecutor.executeAsyncWithThreadStop(0, page.runDatabaseUpdate)


    def getUpdateExecutor(self):
        return self.updateExecutor
        
        
    def pushDirtyMetaDataUpdate(self):
        """
        Push all words for which meta-data is set dirty into the queue
        of the update executor
        """
        if self.recoveryMode:
            return
        
        if not self.isReadOnlyEffect():
            self.updateExecutor.prepare()
            self.updateExecutor.clearDeque(1)
            self.updateExecutor.clearDeque(self.UEQUEUE_INDEX)
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

            words0 = self.getWikiData().getWikiPageNamesForMetaDataState(
                    Consts.WIKIWORDMETADATA_STATE_DIRTY)
            words1 = self.getWikiData().getWikiPageNamesForMetaDataState(
                    Consts.WIKIWORDMETADATA_STATE_ATTRSPROCESSED)

            with self.updateExecutor.getDequeCondition():
                for word in words0:
                    self.updateExecutor.executeAsyncWithThreadStop(1, self._runDatabaseUpdate,
                            word, Consts.WIKIWORDMETADATA_STATE_DIRTY)
    
                for word in words1:
                    self.updateExecutor.executeAsyncWithThreadStop(1, self._runDatabaseUpdate,
                            word, Consts.WIKIWORDMETADATA_STATE_ATTRSPROCESSED)
            
            if self.isSearchIndexEnabled():
                words2 = self.getWikiData().getWikiPageNamesForMetaDataState(
                        Consts.WIKIWORDMETADATA_STATE_SYNTAXPROCESSED)

                with self.updateExecutor.getDequeCondition():
                    for word in words2:
                        self.updateExecutor.executeAsyncWithThreadStop(
                                self.UEQUEUE_INDEX, self._runDatabaseUpdate,
                                word, Consts.WIKIWORDMETADATA_STATE_SYNTAXPROCESSED)


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


    def isDefinedWikiPageName(self, wikiWord):
        """
        Check if a page with this name exists (no aliases)
        """
        return self.wikiData.isDefinedWikiPageName(wikiWord)


    def isDefinedWikiLinkTerm(self, wikiWord):
        """
        check if a word is a valid wikiword (page name or alias)
        """
        return self.wikiData.isDefinedWikiLinkTerm(wikiWord)


    # For plugin compatibility
    isDefinedWikiWord = isDefinedWikiLinkTerm
    isDefinedWikiLink = isDefinedWikiLinkTerm

    def isCreatableWikiWord(self, wikiWord):
        """
        Returns True if wikiWord can be created in the database. Does not
        check against regular expression of wiki language, but checks if word
        already exists or (if document is in caseless mode) if word with
        different case but otherwise the same already exists.
        If this returns False, self.getWikiPageNameForLinkTerm(wikiWord) must be able to
        return the existing word whose existence prevents creation of wikiWord

        TODO: Check against existing aliases
        """
        # TODO: Caseless mode
#         return not self.wikiData.isDefinedWikiWord(wikiWord)
        return not self.getWikiPageNameForLinkTerm(wikiWord)


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
            if not self.isDefinedWikiLinkTerm(wikiWord):
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
#                 realWikiWord2 = self.wikiData.getWikiPageNameForLinkTerm(wikiWord)
# 
#                 if realWikiWord1 != realWikiWord2:
#                     # if not, retrieve new page
#                     value = None
# 
#             if value is None:
#                 # No active page available
#                 realWikiWord = self.getWikiPageNameForLinkTermOrAsIs(wikiWord)
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
                realWikiWord2 = self.wikiData.getWikiPageNameForLinkTerm(wikiWord)
                
                if realWikiWord1 != realWikiWord2:
                    # if not, retrieve new page
                    value = None
            
            if value is None:
                # No active page available
                realWikiWord = self.getWikiPageNameForLinkTermOrAsIs(wikiWord)
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
        Return if datablock exists.

        This works also with wiki pages (unified name starting with "wikipage/")
        but does not return aliases in this case
        """
        if unifName.startswith(u"wikipage/"):
            return self.isDefinedWikiPageName(unifName[9:])
            
        # TODO Create native method in WikiData classes
        return self.guessDataBlockStoreHint(unifName) is not None


    def retrieveDataBlock(self, unifName, default=""):
        """
        Retrieve data block as binary string.
        """
        return self.wikiData.retrieveDataBlock(unifName, default=default)

    def retrieveDataBlockAsText(self, unifName, default=""):
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


    def guessDataBlockStoreHint(self, unifName):
        """
        Return a guess of the store hint used to store the block last time.
        Returns one of the DATABLOCK_STOREHINT_* constants from Consts.py.
        The function is allowed to return the wrong value (therefore a guess).
        It returns None for non-existing data blocks.
        """
        return self.wikiData.guessDataBlockStoreHint(unifName)


    def deleteDataBlock(self, unifName):
        """
        Delete data block with the associated unified name. If the unified name
        is not in database, nothing happens.
        """
        return self.wikiData.deleteDataBlock(unifName)


    def renameDataBlock(self, oldUnifName, newUnifName):
        """
        Renames data block with oldUnifName to newUnifName. Tries to preserve
        storage hint. If data block with newUnifName exists, it is overwritten.
        Currently if oldUnifName doesn't exist, the function does nothing

        TODO: Native support in WikiData classes.
        """
        sh = self.guessDataBlockStoreHint(oldUnifName)
        if sh is None:
            return

        content = self.retrieveDataBlock(oldUnifName, default=None)
        self.storeDataBlock(newUnifName, content, storeHint=sh)
        self.deleteDataBlock(oldUnifName)



    # TODO Remove if not needed
    def checkFileSignatureForWikiPageNameAndMarkDirty(self, word):
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
            valid = wikiData.validateFileSignatureForWikiPageName(word)

            if not valid:
                wikiData.setMetaDataState(word,
                        Consts.WIKIWORDMETADATA_STATE_DIRTY)
                wikiData.refreshFileSignatureForWikiPageName(word)

                wikiPage = self.wikiPageDict.get(word)
                if wikiPage is not None:
                    wikiPage.markTextChanged()

            return valid
        finally:
            if proxyAccessLock is not None:
                proxyAccessLock.release()


    def checkFileSignatureForAllWikiPageNamesAndMarkDirty(self):
        if self.isReadOnlyEffect():
            return True  # TODO Error message?

        wikiData = self.getWikiData()
        
        proxyAccessLock = getattr(wikiData, "proxyAccessLock", None)
        if proxyAccessLock is not None:
            proxyAccessLock.acquire()
        try:
            for word in self.getAllDefinedWikiPageNames():
                if not wikiData.validateFileSignatureForWikiPageName(word):
                    wikiData.setMetaDataState(word,
                            Consts.WIKIWORDMETADATA_STATE_DIRTY)
                    wikiData.refreshFileSignatureForWikiPageName(word)

                    wikiPage = self.wikiPageDict.get(word)
                    if wikiPage is not None:
                        wikiPage.markTextChanged()
        finally:
            if proxyAccessLock is not None:
                proxyAccessLock.release()



    def initiateFullUpdate(self, progresshandler):
        self.updateExecutor.end(hardEnd=True)
        self.getWikiData().refreshWikiPageLinkTerms()

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

            self.getWikiData().fullyResetMetaDataState()
            self.pushDirtyMetaDataUpdate()

        finally:
            progresshandler.close()
            self.updateExecutor.start()


    def initiateExtWikiFileUpdate(self):
        """
        Called to ensure that database is synchronized with external wiki page
        files (for "Original ..." database backends). This is intended to be run
        after direct file changes (using external text editor, dropbox, ...)
        """
        if self.getWikiData().checkCapability("filePerPage") != 1:
            # Nothing to do
            return
            
        self.updateExecutor.end(hardEnd=True)
        try:
            self.getWikiData().refreshWikiPageLinkTerms(deleteFully=True)
            self.checkFileSignatureForAllWikiPageNamesAndMarkDirty()
            self.pushDirtyMetaDataUpdate()
        finally:
            self.updateExecutor.start()


    def rebuildWiki(self, progresshandler, onlyDirty):
        """
        Rebuild  the wiki

        progresshandler -- Object, fulfilling the
            PersonalWikiFrame.GuiProgressHandler protocol
        """
        self.updateExecutor.end(hardEnd=True)
        self.getWikiData().refreshWikiPageLinkTerms()

        if onlyDirty:
#             wikiWords = self.getWikiData().getWikiPageNamesForMetaDataState(
#                     Consts.WIKIWORDMETADATA_STATE_DIRTY) + \
#                     self.getWikiData().getWikiPageNamesForMetaDataState(
#                     Consts.WIKIWORDMETADATA_STATE_ATTRSPROCESSED)
            wikiWords = self.getWikiData().getWikiPageNamesForMetaDataState(
                    self.getFinalMetaDataState(), ">")
        else:
            # get all of the wikiWords
            wikiWords = self.getWikiData().getAllDefinedWikiPageNames()


        if self.isSearchIndexEnabled():
            progresshandler.open(len(wikiWords) * 4 + 1)
        else:
            progresshandler.open(len(wikiWords) * 3 + 1)
#         progresshandler.update(0, _(u"Waiting for update thread to end"))


        self.fireMiscEventKeys(("begin foreground update", "begin update"))

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
                progresshandler.update(step, _(u"Update attributes of %s") %
                        wikiWord)
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

                    self.getWikiData().refreshFileSignatureForWikiPageName(
                            wikiWord)
                    wikiPage.refreshAttributesFromPageAst(pageAst)
                except:
                    traceback.print_exc()

                step += 1

            # Step three: update the rest of the syntax (todos, relations)
            for wikiWord in wikiWords:
                progresshandler.update(step, _(u"Update syntax of %s") % wikiWord)
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
            
            if self.isSearchIndexEnabled():
                # Step four: update index
                for wikiWord in wikiWords:
                    progresshandler.update(step, _(u"Update index of %s") % wikiWord)
                    try:
                        wikiPage = self._getWikiPageNoErrorNoCache(wikiWord)
                        if isinstance(wikiPage, AliasWikiPage):
                            # This should never be an alias page, so fetch the
                            # real underlying page
                            # This can only happen if there is a real page with
                            # the same name as an alias
                            wikiPage = WikiPage(self, wikiWord)

                        wikiPage.putIntoSearchIndex()

#                         writer.add_document(unifName="wikipage/"+wikiWord,
#                                 modTimestamp=wikiPage.getTimestamps()[0],
#                                 content=content)
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
            self.fireMiscEventKeys(("end foreground update",))
            self.updateExecutor.start()



    def getWikiWordSubpages(self, wikiWord):
        return self.getWikiData().getDefinedWikiPageNamesStartingWith(
                wikiWord + u"/")


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

        if self.isDefinedWikiPageName(fromWikiWord):
            # If fromWikiWord exists (not mandatory) it must be renamed, too
            renameDict[fromWikiWord] = toWikiWord

        for subPageName in self.getWikiWordSubpages(fromWikiWord):
            renameDict[subPageName] = toWikiWord + subPageName[len(fromWikiWord):]

        # Check for renames with errors
        errorRenames = []

        toSet = set()
        sameToSet = set()
        
        for key, value in renameDict.iteritems():
            if self.isDefinedWikiPageName(value):
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

        if self.isDefinedWikiLinkTerm(toWikiWord):
            raise WikiDataException(
                    _(u"Cannot rename '%s' to '%s', '%s' already exists") %
                    (wikiWord, toWikiWord, toWikiWord))

        try:
            oldWikiPage = self.getWikiPage(wikiWord)
        except WikiWordNotFoundException:
            # So create page first
            oldWikiPage = self.createWikiPage(wikiWord)
            oldWikiPage.writeToDatabase()

        self.getWikiData().renameWord(wikiWord, toWikiWord)
        
        # TODO: Replace always?
        
        # Check if replacing previous title of page with new one

        wikiWordTitle = self.getWikiPageTitle(wikiWord)
        
        if wikiWordTitle is not None:
            prevTitle = self.formatPageTitle(wikiWordTitle) + u"\n"
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
        oldWikiPage.queueRemoveFromSearchIndex()
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

        self.getWikiData().setMetaDataState(toWikiWord,
                Consts.WIKIWORDMETADATA_STATE_DIRTY)

        content = page.getLiveText()
        if prevTitle is not None and content.startswith(prevTitle):
            # Replace previous title with new one
            content = self.formatPageTitle(self.getWikiPageTitle(toWikiWord)) + \
                    u"\n" + content[len(prevTitle):]
            page.replaceLiveText(content)

        page.initiateUpdate()


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


    _TITLE_SPLIT_RE1 = re.compile(ur"([" + StringOps.UPPERCASE + ur"]+)" + 
            ur"([" + StringOps.UPPERCASE + ur"][" + StringOps.LOWERCASE + ur"])")
    _TITLE_SPLIT_RE2 = re.compile(ur"([" + StringOps.LOWERCASE + ur"])" +
            ur"([" + StringOps.UPPERCASE + ur"])")


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
            UC = StringOps.UPPERCASE
            
#             title = re.sub(ur'([A-Z\xc0-\xde]+)([A-Z\xc0-\xde][a-z\xdf-\xff])',
#                     r'\1 \2', wikiWord)
#             title = re.sub(ur'([a-z\xdf-\xff])([A-Z\xc0-\xde])', r'\1 \2',
#                     title)
            title = self._TITLE_SPLIT_RE1.sub(ur'\1 \2', wikiWord)
            title = self._TITLE_SPLIT_RE2.sub(ur'\1 \2', title)
            return title
        else:  # creaMode == 2: No title at all.
            return None


    def searchWiki(self, sarOp, applyOrdering=True, threadstop=DUMBTHREADSTOP):
        """
        Search all wiki pages using the SearchAndReplaceOperation sarOp and
        return list of all page names that match the search criteria.
        If applyOrdering is True, the ordering of the sarOp is applied before
        returning the list.
        """
        if sarOp.indexSearch == "no": 
            wikiData = self.getWikiData()
            sarOp.beginWikiSearch(self)
            try:
                threadstop.testValidThread()
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
    
                    threadstop.testValidThread()
    
                # Now search database
                resultSet = self.getWikiData().search(sarOp, exclusionSet)
                threadstop.testValidThread()
                resultSet |= preResultSet
                if applyOrdering:
                    result = sarOp.applyOrdering(resultSet, self.getCollator())
                else:
                    result = list(resultSet)
    
            finally:
                sarOp.endWikiSearch()
    
            threadstop.testValidThread()
            return result
        else:
            # Processing index search
            threadstop.testValidThread()
            if not self.isSearchIndexEnabled():
                return []

            q = sarOp.getWhooshIndexQuery(self)
            s = self.getSearchIndex().searcher()
            threadstop.testValidThread()
            resultList = s.search(q, limit=None)
            
            result = [rd["unifName"][9:] for rd in resultList
                    if rd["unifName"].startswith(u"wikipage/")]
            
            threadstop.testValidThread()
            return result


    @staticmethod
    def getWhooshIndexContentAnalyzer():
        from whoosh.analysis import StandardAnalyzer        
        return StandardAnalyzer(stoplist=None)



    _REV_SEARCH_INDEX_SCHEMA = None
    
    @staticmethod
    def getWhooshIndexSchema():
        if WikiDataManager._REV_SEARCH_INDEX_SCHEMA is None:
            from whoosh.fields import Schema, ID, NUMERIC, TEXT
            
            WikiDataManager._REV_SEARCH_INDEX_SCHEMA = Schema(
                    unifName=ID(stored=True, unique=True),
                    modTimestamp=NUMERIC(), content=TEXT(
                    analyzer=WikiDataManager.getWhooshIndexContentAnalyzer()))

        return WikiDataManager._REV_SEARCH_INDEX_SCHEMA
    
    


    def getFinalMetaDataState(self):
        if self.isSearchIndexEnabled():
            return Consts.WIKIWORDMETADATA_STATE_INDEXED
        else:
            return Consts.WIKIWORDMETADATA_STATE_SYNTAXPROCESSED

    def isSearchIndexEnabled(self):
        return self.getWikiConfig().getboolean("main", "indexSearch_enabled",
                False)

    def isSearchIndexPresent(self):
        import whoosh.index

        indexPath = os.path.join(self.getWikiPath(), "indexsearch")
        return os.path.exists(indexPath) and whoosh.index.exists_in(indexPath)

    def removeSearchIndex(self):
#         if self.isSearchIndexEnabled():
#             raise InternalError("Calling removeSearchIndex() while index is enabled")
        
        p = self.updateExecutor.pause(wait=True)
        self.updateExecutor.clearDeque(self.UEQUEUE_INDEX)
        self.updateExecutor.start()

        if self.whooshIndex is not None:
            self.whooshIndex.close()
            self.whooshIndex = None
        

        indexPath = os.path.join(self.getWikiPath(), "indexsearch")
        if os.path.exists(indexPath):
            # Warning!!! rmtree() is very dangerous, don't make a mistake here!
            shutil.rmtree(indexPath, ignore_errors=True)

        self.getWikiConfig().set("main", "indexSearch_formatNo", u"0")


    def getSearchIndex(self, clear=False):
        """
        Opens (or creates if necessary) the whoosh search index and returns it.
        It also automatically refreshes the index to the latest version if needed.
        """
        if not self.isSearchIndexEnabled():
            return None
        
        import whoosh.index, whoosh.writing

        whoosh.writing.DOCLENGTH_TYPE = "l"
        whoosh.writing.DOCLENGTH_LIMIT = 2 ** 31 - 1

        if self.whooshIndex is None:
            indexPath = os.path.join(self.getWikiPath(), "indexsearch")
            if not os.path.exists(indexPath):
                os.mkdir(indexPath)

            if clear or not whoosh.index.exists_in(indexPath):
                schema = self.getWhooshIndexSchema()
                whoosh.index.create_in(indexPath, schema)

            self.whooshIndex = whoosh.index.open_dir(indexPath)
            
            self.getWikiConfig().set("main", "indexSearch_formatNo",
                    unicode(Consts.SEARCHINDEX_FORMAT_NO))

        self.whooshIndex = self.whooshIndex.refresh()

        return self.whooshIndex


#     def rebuildSearchIndex(self, progresshandler, onlyDirty=False):
#         """
#         progresshandler -- Object, fulfilling the
#             PersonalWikiFrame.GuiProgressHandler protocol
#         """
#         if not self.isSearchIndexEnabled():
#             return
# 
#         self.updateExecutor.pause()
#         self.getWikiData().refreshWikiPageLinkTerms()
# 
#         # get all of the wikiWords
#         wikiWords = self.getWikiData().getAllDefinedWikiPageNames()
# 
#         progresshandler.open(len(wikiWords))
#         
#         searchIdx = self.getSearchIndex(clear=True)
#         writer = searchIdx.writer()
# 
#         try:
#             step = 1
#             
#             for wikiWord in wikiWords:
# # Disabled to remove from .pot                progresshandler.update(step, _(u"Update rev. index"))
#                 wikiPage = self._getWikiPageNoErrorNoCache(wikiWord)
#                 if isinstance(wikiPage, AliasWikiPage):
#                     # This should never be an alias page, so fetch the
#                     # real underlying page
#                     # This can only happen if there is a real page with
#                     # the same name as an alias
#                     wikiPage = WikiPage(self, wikiWord)
# 
#                 content = wikiPage.getLiveText()
#                 
#                 writer.add_document(unifName="wikipage/"+wikiWord,
#                         modTimestamp=wikiPage.getTimestamps()[0],
#                         content=content)
#                 
#                 step += 1
#         finally:
#             writer.commit()
#             progresshandler.close()
#             self.updateExecutor.start()


#     def removeFromSearchIndex(self, unifName):
#         if not self.isSearchIndexEnabled():
#             return
#         
#         writer = None
#         try:
#             searchIdx = self.getSearchIndex()
#             writer = searchIdx.writer(timeout=Consts.DEADBLOCKTIMEOUT)
# 
#             writer.delete_by_term("unifName", unifName)
#         except:
#             if writer is not None:
#                 writer.cancel()
#             raise
# 
#         writer.commit()


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


    def getWikiPageNamesModifiedWithin(self, startTime, endTime):
        """
        startTime and endTime are floating values as returned by time.time()
        startTime is inclusive, endTime is exclusive
        """
        return self.getWikiData().getWikiPageNamesModifiedWithin(startTime,
                endTime)


    def getWikiPageNamesModifiedLastDays(self, days):
        """
        Return wiki words modified during the last number of days.
        """
        endTime = time.time()
        startTime = float(endTime-(86400*days))
        
        return self.getWikiData().getWikiPageNamesModifiedWithin(startTime,
                endTime)


    def getCcWordBlacklist(self):
        return self.ccWordBlacklist

    def getNccWordBlacklist(self):
        return self.nccWordBlacklist

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

    def _updateNccWordBlacklist(self):
        """
        Update the blacklist of non-camelcase (=bracketed) words which should
        show up as normal text.
        """
        pg = self.getFuncPage("global/NCCBlacklist")
        bls = set(pg.getLiveText().split("\n"))
        pg = self.getFuncPage("wiki/NCCBlacklist")
        bls.update(pg.getLiveText().split("\n"))
        self.nccWordBlacklist = bls


    def getWikiPageNameForLinkTerm(self, word):
        """
        Resolve links to wiki words. Returns None if it can't be resolved
        """
        # TODO: Resolve properly in caseless mode
        return self.getWikiData().getWikiPageNameForLinkTerm(word)

    
    def getWikiPageNameForLinkTermOrAsIs(self, word):
        """
        return the real word if word is an alias.
        returns word itself if word isn't an alias (may mean it's a real word
                or doesn't exist!)
        """
        result = self.getWikiData().getWikiPageNameForLinkTerm(word)

        if result is None:
            return word

        return result


    def getWikiPageNameForLinkCore(self, linkCore, basePageName):
        """
        Fully resolve a link core (which may be a relative or absolute
        link) to the real page name or None if not possible.
        basePageName is the name of the page where the link is placed on
        (needed for relative links and to retrieve the right language helper)
        """
        basePage = self.getWikiPageNoError(basePageName)

        langHelper = GetApp().createWikiLanguageHelper(
                basePage.getWikiLanguageName())

        # Convert possible relative path (if subpages used) to page name
        absoluteName = langHelper.resolveWikiWordLink(linkCore, basePage)

        # Convert possible alias to real page name (and check if term
        # denotes a wiki page at all, None is returned otherwise)
        return self.getWikiPageNameForLinkTerm(absoluteName)

        

    def getTodos(self):
        """
        Return all todo entries as list of tuples (wikiword, todoEntry)
        """
        return self.getWikiData().getTodos()


    def getAttributeNamesStartingWith(self, beg, builtins=False):
        """
        Function must work for read-only wiki.
        Returns list or set (whatever is more efficient) of all attribute names
        starting with  beg.
        """
        
        if not builtins:
            return self.getWikiData().getAttributeNamesStartingWith(beg)
        
        biKeys = [k for k in AttributeHandling.getBuiltinKeys() if k.startswith(beg)]
        
        if len(biKeys) == 0:
            # Nothing to add
            return self.getWikiData().getAttributeNamesStartingWith(beg)
        
        attrs = set(self.getWikiData().getAttributeNamesStartingWith(beg))
        attrs.update(biKeys)
        
        return attrs


    def getDistinctAttributeValuesByKey(self, key, builtins=False):
        """
        Function must work for read-only wiki.
        Return a list of all distinct used attribute values for a given key.
        """
        if not builtins:
            return self.getWikiData().getDistinctAttributeValues(key)
        
        biVals = AttributeHandling.getBuiltinValuesForKey(key)
        if biVals is None or len(biVals) == 0:
            # Nothing to add
            return self.getWikiData().getDistinctAttributeValues(key)
        
        vals = set(self.getWikiData().getDistinctAttributeValues(key))
        vals.update(biVals)
        
        return list(vals)
            
        
#         s = set(v for w, k, v in
#                 self.getWikiData().getAttributeTriples(None, key, None))
#         return list(s)

    def getAttributeTriples(self, word, key, value):
        """
        Function must work for read-only wiki.
        word, key and value can either be unistrings to search for or None as
        wildcard.
        """
        return self.getWikiData().getAttributeTriples(word, key, value)


    def getGlobalAttributeValue(self, attribute, default=None):
        """
        Function must work for read-only wiki.
        Finds the wiki-global setting of attribute, if any.
        Attribute itself must not contain the "global." prefix
        """
        return self.getWikiData().getGlobalAttributes().get(
                u"global." + attribute, default)
        

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
        wikiData = wikiDataFactory(self, self.dataDir, self.getWikiTempDir())

        self.baseWikiData = wikiData
        self.wikiData = WikiDataSynchronizedProxy(self.baseWikiData)
        
        self.wikiData.connect()
        
        # Reset flag so program automatically tries reconnecting on next error
        self.autoReconnectTriedFlag = False

        attrs = {"reconnected database": True,}
        self.fireMiscEventProps(attrs)



    def _handleWikiConfigurationChanged(self, miscevt):
        wikiData = self.getWikiData()
        
        if self.getWikiConfig().getboolean("main",
                "indexSearch_enabled", False):
            self.pushDirtyMetaDataUpdate()
        else:
            if strToBool(miscevt.get("old config settings")
                    .get("indexSearch_enabled", "False")):
                # Index search was switched off

                # Check for wiki pages with wrong metadata state and adjust
                # TODO: Faster?

                wikiData.commit()
                finalState = self.getFinalMetaDataState()
                
                for wikiWord in wikiData.getWikiPageNamesForMetaDataState(
                        finalState, "<"):
                    wikiData.setMetaDataState(wikiWord, finalState)
                wikiData.commit()

                # Remove index
                self.removeSearchIndex()

        if wikiData.checkCapability("filePerPage") is not None:
            wikiData.setEditorTextMode(self.getWikiConfig().getboolean("main",
                    "editor_text_mode", False))


    def getFileSignatureBlock(self, filename):
        """
        Mainly called by WikiData. Returns the file signature block for a
        given file. It is a bytestring containing size and modification date
        of the file and can be compared to a db-stored version to check for
        file changes outside of WikidPad.
        
        It calls StringOps.getFileSignatureBlock with the time coarsening
        given in the wiki options.
        """
        
        coarseStr = self.getWikiConfig().get("main",
                "fileSignature_timeCoarsening", "0")

        try:
            if "." in coarseStr:
                coarsening = float(coarseStr)
            else:
                coarsening = int(coarseStr)
        except ValueError:
            coarsening = None
            
        return getFileSignatureBlock(filename, coarsening)



    def miscEventHappened(self, miscevt):
        """
        Handle misc events from DocPages
        """
        if miscevt.getSource() is self.wikiConfiguration:
            if miscevt.has_key("changed configuration"):
                attrs = miscevt.getProps().copy()
                attrs["changed wiki configuration"] = True
                self._handleWikiConfigurationChanged(miscevt)
                self.fireMiscEventProps(attrs)
        elif miscevt.getSource() is GetApp():
            if miscevt.has_key("reread cc blacklist needed"):
                self._updateCcWordBlacklist()
            elif miscevt.has_key("reread ncc blacklist needed"):
                self._updateNccWordBlacklist()
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
                miscevt.getSource().queueRemoveFromSearchIndex()  # TODO: Check for possible failure!!!
                # TODO: Add new on rename
            elif miscevt.has_key("updated wiki page"):
                self.autoLinkRelaxInfo = None
                attrs = miscevt.getProps().copy()
                attrs["wikiPage"] = miscevt.getSource()
                self.fireMiscEventProps(attrs)
#                 miscevt.getSource().putIntoSearchIndex()
            elif miscevt.has_key("saving new wiki page"):            
                self.autoLinkRelaxInfo = None
#                 miscevt.getSource().putIntoSearchIndex()
            elif miscevt.has_key("reread cc blacklist needed"):
                self._updateCcWordBlacklist()

                attrs = miscevt.getProps().copy()
                attrs["funcPage"] = miscevt.getSource()
                self.fireMiscEventProps(attrs)
            elif miscevt.has_key("reread ncc blacklist needed"):
                self._updateNccWordBlacklist()

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
            elif miscevt.has_key("visited doc page"):
                attrs = miscevt.getProps().copy()
                attrs["docPage"] = miscevt.getSource()

                self.fireMiscEventProps(attrs)

#         elif miscevt.getSource() is GetApp().getGlobalConfig():
#             if miscevt.has_key("changed configuration"):
#                 # TODO: On demand
#                 if SpellChecker.isSpellCheckSupported():
#                     self.onlineSpellCheckerSession = \
#                             SpellChecker.SpellCheckerSession(self)


    # TODO: 2.3: Remove "property"-compatibility
    getDistinctPropertyValuesByKey = getDistinctAttributeValuesByKey
    getPropertyTriples = getAttributeTriples
    getGlobalPropertyValue = getGlobalAttributeValue


    # TODO: 2.4: Remove compatibility definitions
    isDefinedWikiPage = isDefinedWikiPageName
    getUnAliasedWikiWord = getWikiPageNameForLinkTerm
    getUnAliasedWikiWordOrAsIs = getWikiPageNameForLinkTermOrAsIs
    getWikiWordsModifiedWithin = getWikiPageNamesModifiedWithin
    getWikiWordsModifiedLastDays = getWikiPageNamesModifiedLastDays
    checkFileSignatureForAllWikiWordsAndMarkDirty = \
            checkFileSignatureForAllWikiPageNamesAndMarkDirty
