# from Enum import Enumeration
import sys, os, string, re, traceback, time
from os.path import join, exists, splitext
from calendar import timegm
import urllib_red as urllib

# import wx

import Consts
from StringOps import *

from WikiExceptions import WikiWordNotFoundException, ImportException, \
        BadFuncPageTagException



class MultiPageTextImporter:
    def __init__(self, mainControl):
        """
        mainControl -- Currently PersonalWikiFrame object
        """
        self.mainControl = mainControl


    def getImportTypes(self, guiparent):
        """
        Return sequence of tuples with the description of import types provided
        by this object. A tuple has the form (<imp. type>,
            <human readable description>, <panel for add. options or None>)
        If panels for additional options must be created, they should use
        guiparent as parent
        """
        return (
                (u"multipage_text", _(u"Multipage text"), None),
                )


    def getImportSourceWildcards(self, importType):
        """
        If an export type is intended to go to a file, this function
        returns a (possibly empty) sequence of tuples
        (wildcard description, wildcard filepattern).
        
        If an export type goes to a directory, None is returned
        """
        if importType == u"multipage_text":
            return ((_(u"Multipage files (*.mpt)"), "*.mpt"),
                    (_(u"Text file (*.txt)"), "*.txt")) 

        return None


    def getAddOptVersion(self):
        """
        Returns the version of the additional options information returned
        by getAddOpt(). If the return value is -1, the version info can't
        be stored between application sessions.
        
        Otherwise, the addopt information can be stored between sessions
        and can later handled back to the doImport method of the object
        without previously showing the import dialog.
        """
        return 0


    def getAddOpt(self, addoptpanel):
        """
        Reads additional options from panel addoptpanel.
        If getAddOptVersion() > -1, the return value must be a sequence
        of simple string, unicode and/or numeric objects. Otherwise, any object
        can be returned (normally the addoptpanel itself)
        """
        return ()


    def collectContent(self):
        """
        Collect lines from current position of importFile up to separator
        or file end collect all lines and return them as list of lines.
        """
        content = []                    
        while True:
            # Read lines of wikiword
            line = self.importFile.readline()
            if line == u"":
                # The last page in mpt file without separator
                # ends as the real wiki page
#                 content = u"".join(content)
                break
            
            if line == self.separator:
                if len(content) > 0:
                    # Iff last line of mpt page is empty, the original
                    # page ended with a newline, so remove last
                    # character (=newline)

                    content[-1] = content[-1][:-1]
#                     content = u"".join(content)
                break

            content.append(line)
            
        return u"".join(content)




    def doImport(self, wikiDataManager, importType, importSrc,
            compatFilenames, addOpt):
        """
        Run import operation.
        
        wikiDataManager -- WikiDataManager object
        importType -- string tag to identify how to import
        importDest -- Path to source directory or file to import from
        compatFilenames -- Should the filenames be decoded from the lowest
                           level compatible?
        addOpt -- additional options returned by getAddOpt()
        """
        try:
            self.rawImportFile = open(pathEnc(importSrc), "rU")
        except IOError:
            raise ImportException(_(u"Opening import file failed"))
            
        self.wikiDataManager = wikiDataManager
#         wikiData = self.wikiDataManager.getWikiData()

        
        # TODO Do not stop on each import error, instead create error list and
        #   continue

        try:
            try:
                # Wrap input file to convert format
                bom = self.rawImportFile.read(len(BOM_UTF8))
                if bom != BOM_UTF8:
                    self.rawImportFile.seek(0)
                    self.importFile = mbcsReader(self.rawImportFile, "replace")
                else:
                    self.importFile = utf8Reader(self.rawImportFile, "replace")
                
                line = self.importFile.readline()
                if line.startswith("#!"):
                    # Skip initial line with #! to allow execution as shell script
                    line = self.importFile.readline()

                if not line.startswith("Multipage text format "):
                    raise ImportException(
                            _(u"Bad file format, header not detected"))

                # Following in the format identifier line is a version number
                # of the file format
                self.formatVer = int(line[22:-1])
                
                if self.formatVer > 1:
                    raise ImportException(
                            _(u"File format number %i is not supported") %
                            self.formatVer)

                # Next is the separator line
                line = self.importFile.readline()
                if not line.startswith("Separator: "):
                    raise ImportException(
                            _(u"Bad file format, header not detected"))

                self.separator = line[11:]
                
                if self.formatVer == 0:
                    self.doImportVer0()
                elif self.formatVer == 1:
                    while True:
                        tag = self.importFile.readline()
                        if tag == u"":
                            # End of file
                            break
                        tag = tag[:-1]
                        if tag.startswith(u"funcpage/"):
                            self.importItemFuncPage(tag[9:])
                        elif tag.startswith(u"savedsearch/"):
                            self.importItemSavedSearch(tag)
                        elif tag.startswith(u"wikipage/"):
                            self.importItemWikiPage(tag[9:])
                        else:
                            # Unknown tag -> Ignore until separator
                            self.collectContent()
            except ImportException:
                raise
            except Exception, e:
                traceback.print_exc()
                raise ImportException(unicode(e))

        finally:
            self.rawImportFile.close()


    def doImportVer0(self):
        """
        Import wikiwords if format version is 0.
        """
        langHelper = wx.GetApp().createWikiLanguageHelper(
                self.wikiDataManager.getWikiDefaultWikiLanguage())

        while True:
            # Read next wikiword
            line = self.importFile.readline()
            if line == u"":
                break

            wikiWord = line[:-1]
            errMsg = langHelper.checkForInvalidWikiWord(wikiWord,
                    self.wikiDataManager)
            if errMsg:
                raise ImportException(_(u"Bad wiki word: %s, %s") %
                        (wikiWord, errMsg))

            content = self.collectContent()
            page = self.wikiDataManager.getWikiPageNoError(wikiWord)

            page.replaceLiveText(content)


    def importItemFuncPage(self, subtag):
        # The subtag is functional page tag
        try:
            # subtag is unicode but func tags are bytestrings
            subtag = str(subtag)
        except UnicodeEncodeError:
            return

        content = self.collectContent()
        try:
            page = self.wikiDataManager.getFuncPage(subtag)
            page.replaceLiveText(content)
        except BadFuncPageTagException:
            # This function tag is bad or unknown -> ignore
            return  # TODO Report error


    def importItemSavedSearch(self, unifName):
        # The subtag is the title of the search
        
        # Content is base64 encoded
        b64Content = self.collectContent()
        
        try:
            datablock = base64BlockDecode(b64Content)
            self.wikiDataManager.getWikiData().storeDataBlock(unifName, datablock,
                    storeHint=Consts.DATABLOCK_STOREHINT_INTERN)

        except TypeError:
            # base64 decoding failed
            return  # TODO Report error


    def importItemWikiPage(self, subtag):
        timeStampLine = self.importFile.readline()[:-1]
        timeStrings = timeStampLine.split(u"  ")
        if len(timeStrings) < 3:
            return  # TODO Report error

        timeStrings = timeStrings[:3]

        try:
            timeStrings = [str(ts) for ts in timeStrings]
        except UnicodeEncodeError:
            return  # TODO Report error

        try:
            timeStamps = [timegm(time.strptime(ts, "%Y-%m-%d/%H:%M:%S"))
                    for ts in timeStrings]

        except (ValueError, OverflowError):
            traceback.print_exc()
            return  # TODO Report error

        content = self.collectContent()
        page = self.wikiDataManager.getWikiPageNoError(subtag)

        # TODO How to handle versions here?
        page.replaceLiveText(content)
        if page.getTxtEditor() is not None:
            page.writeToDatabase()

        page.setTimestamps(timeStamps)


def describeImporters(mainControl):
    return (MultiPageTextImporter(mainControl),)

