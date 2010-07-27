from __future__ import with_statement

# from Enum import Enumeration
import sys, os, string, re, traceback, locale, time, urllib
from os.path import join, exists, splitext, abspath
from cStringIO import StringIO
import shutil
## from xml.sax.saxutils import escape

import urllib_red as urllib

import wx

from wxHelper import XrcControls, GUI_ID, wxKeyFunctionSink


from WikiExceptions import WikiWordNotFoundException, ExportException
from ParseUtilities import getFootnoteAnchorDict
from StringOps import *
from WikiPyparsing import StackedCopyDict, SyntaxNode
from TempFileSet import TempFileSet

from SearchAndReplace import SearchReplaceOperation, ListWikiPagesOperation, \
        ListItemWithSubtreeWikiPagesNode

import Configuration

import OsAbstract

import DocPages



class AbstractExporter(object):
    def __init__(self, mainControl):
        self.wikiDocument = None
        self.mainControl = mainControl

    def getMainControl(self):
        return self.mainControl    
 
    def setWikiDocument(self, wikiDocument):
        self.wikiDocument = wikiDocument

    def getWikiDocument(self):
        return self.wikiDocument

    def getExportTypes(self, guiparent, continuousExport=False):
        """
        Return sequence of tuples with the description of export types provided
        by this object. A tuple has the form (<exp. type>,
            <human readable description>, <panel for add. options or None>)
        If panels for additional options must be created, they should use
        guiparent as parent
        continuousExport -- If True, only types with support for continuous export
        are listed.
        """
        raise NotImplementedError


    def getExportDestinationWildcards(self, exportType):
        """
        If an export type is intended to go to a file, this function
        returns a (possibly empty) sequence of tuples
        (wildcard description, wildcard filepattern).
        
        If an export type goes to a directory, None is returned
        """
        raise NotImplementedError


    def getAddOptVersion(self):
        """
        Returns the version of the additional options information returned
        by getAddOpt(). If the return value is -1, the version info can't
        be stored between application sessions.
        
        Otherwise, the addopt information can be stored between sessions
        and can later handled back to the export method of the object
        without previously showing the export dialog.
        """
        raise NotImplementedError


    def getAddOpt(self, addoptpanel):
        """
        Reads additional options from panel addoptpanel.
        If addoptpanel is None, return default values
        If getAddOptVersion() > -1, the return value must be a sequence
        of simple string, unicode and/or numeric objects. Otherwise, any object
        can be returned (normally the addoptpanel itself).
        """
        raise NotImplementedError
    

    def setAddOpt(self, addOpt, addoptpanel):
        """
        Shows content of addOpt in the addoptpanel (must not be None).
        This function is only called if getAddOptVersion() != -1.
        """
        raise NotImplementedError


    def export(self, wikiDocument, wordList, exportType, exportDest,
            compatFilenames, addOpt, progressHandler):
        """
        Run non-continuous export operation.
        
        wikiDocument -- WikiDocument object
        wordList -- Sequence of wiki words to export
        exportType -- string tag to identify how to export
        exportDest -- Path to destination directory or file to export to
        compatFilenames -- Should the filenames be encoded to be lowest
                           level compatible
        addOpt -- additional options returned by getAddOpt()
        progressHandler -- wxHelper.ProgressHandler object
        """
        raise NotImplementedError

    
    def startContinuousExport(self, wikiDocument, listPagesOperation,
            exportType, exportDest, compatFilenames, addOpt, progressHandler):
        """
        Start continues export operation. This function may be unimplemented
        if derived class does not provide any continous-export type.
        
        wikiDocument -- WikiDocument object
        listPagesOperation -- Instance of SearchAndReplace.SearchReplaceOperation
        exportType -- string tag to identify how to export
        exportDest -- Path to destination directory or file to export to
        compatFilenames -- Should the filenames be encoded to be lowest
                           level compatible
        addOpt -- additional options returned by getAddOpt()
        progressHandler -- wxHelper.ProgressHandler object
        """
        raise NotImplementedError


    def stopContinuousExport(self):
        """
        Stop continues-export operation. This function may be unimplemented
        if derived class does not provide any continous-export type.
        """
        raise NotImplementedError


#     def supportsXmlOptions(self):
#         """
#         Returns True if additional options can be returned and processed
#         as XML.
#         """
#         return True
#     
#     def getXmlRepresentation


def removeBracketsToCompFilename(fn):
    """
    Combine unicodeToCompFilename() and removeBracketsFilename() from StringOps
    """
    return unicodeToCompFilename(removeBracketsFilename(fn))


def _escapeAnchor(name):
    """
    Escape name to be usable as HTML anchor (URL fragment)
    """
    result = []
    for c in name:
        oc = ord(c)
        if oc < 48 or (57 < oc < 65) or (90 < oc < 97) or oc > 122:
            if oc > 255:
                result.append("$%04x" % oc)
            else:
                result.append("=%02x" % oc)
        else:
            result.append(c)
    return u"".join(result)

# # Types of export destinations
# EXPORT_DEST_TYPE_DIR = 1
# EXPORT_DEST_TYPE_FILE = 2


class BasicLinkConverter(object):
    def __init__(self, wikiDocument, htmlExporter):
        self.htmlExporter = htmlExporter
        self.wikiDocument = wikiDocument
        
    def getLinkForWikiWord(self, word, default = None):
        return default


class LinkConverterForHtmlSingleFilesExport(BasicLinkConverter):
    def getLinkForWikiWord(self, word, default = None):
        relUnAlias = self.wikiDocument.getUnAliasedWikiWord(word)
        if relUnAlias is None:
            return default
        if not self.htmlExporter.shouldExport(word):
            return default
            
#         print "--LinkConverterForHtmlSingleFilesExport4", repr((urlFromPathname(u"ce%2FExp")))

        return urlFromPathname(
                self.htmlExporter.filenameConverter.getFilenameForWikiWord(
                relUnAlias) + ".html")

class LinkConverterForHtmlMultiPageExport(BasicLinkConverter):
    def getLinkForWikiWord(self, word, default = None):
        relUnAlias = self.wikiDocument.getUnAliasedWikiWord(word)
        if relUnAlias is None:
            return default
        if not self.htmlExporter.shouldExport(word):
            return default

        if relUnAlias not in self.htmlExporter.wordList:
            return default

        return u"#%s" % _escapeAnchor(relUnAlias)


class FilenameConverter(object):
    def __init__(self, asciiOnly):
        self.asciiOnly = asciiOnly
        self.reset()

    def reset(self):
        self._used = {}
        self._valueSet = set()

    def getFilenameForWikiWord(self, ww):
        try:
            return self._used[ww]
        except KeyError:
            for fname in iterCompatibleFilename(ww, u"",
                    asciiOnly=self.asciiOnly, maxLength=245):
                if not fname in self._valueSet:
                    self._used[ww] = fname
                    self._valueSet.add(fname)
                    return fname



class SizeValue(object):
    """
    Represents a single size value, either a pixel or percent size.
    """

    UNIT_INVALID = 0
    UNIT_PIXEL = 1
    UNIT_FACTOR = 2
    _UNIT_PERCENT = 3
    
    def __init__(self, valStr):
        self.unit = SizeValue.UNIT_INVALID
        self.value = 0.0
        self.setValueStr(valStr)

    def getUnit(self):
        return self.unit
    
    def isValid(self):
        return self.unit != SizeValue.UNIT_INVALID
        
    def getValue(self):
        return self.value

    def setValueStr(self, valStr):
        """
        Set members fo class        
        """
        valStr = valStr.strip()
        if len(valStr) == 0:
            self.unit = SizeValue.UNIT_INVALID
            return False

        if valStr[-1] == "%":
            valStr = valStr[:-1]
            self.unit = SizeValue._UNIT_PERCENT
        else:
            self.unit = SizeValue.UNIT_PIXEL

        try:
            val = float(valStr)
            if val >= 0.0:
                self.value = float(val)
                if self.unit == SizeValue._UNIT_PERCENT:
                    self.value /= 100.0
                    self.unit = SizeValue.UNIT_FACTOR
                
                return True
            else:
                self.unit = SizeValue.UNIT_INVALID
                return False

        except ValueError:
            self.unit = SizeValue.UNIT_INVALID
            return False




# TODO UTF-8 support for HTML? Other encodings?

class HtmlExporter(AbstractExporter):
    def __init__(self, mainControl):
        """
        mainControl -- Currently PersonalWikiFrame object
        """
        AbstractExporter.__init__(self, mainControl)
        self.wordList = None
        self.exportDest = None
        
        # List of tuples (<source CSS path>, <dest CSS file name / url>)
        self.styleSheetList = []
        self.basePageAst = None
                
        self.exportType = None
        self.progressHandler = None
        self.referencedStorageFiles = None
        
        self.linkConverter = None
        self.compatFilenames = None
        self.listPagesOperation = None

        self.wordAnchor = None  # For multiple wiki pages in one HTML page, this contains the anchor
                # of the current word.
        self.tempFileSet = None
        self.copiedTempFileCache = None  # Dictionary {<original path>: <target URL>}
        self.filenameConverter = FilenameConverter(False)
#         self.convertFilename = removeBracketsFilename   # lambda s: mbcsEnc(s, "replace")[0]
        
        self.result = None
        
        # Flag to control how to push output into self.result
        self.outFlagEatPostBreak = False
        self.outFlagPostBreakEaten = False
        
        self.__sinkWikiDocument = None

    def setWikiDocument(self, wikiDocument):
        self.wikiDocument = wikiDocument
        if self.wikiDocument is not None:
            self.buildStyleSheetList()

    def getExportTypes(self, guiparent, continuousExport=False):
        """
        Return sequence of tuples with the description of export types provided
        by this object. A tuple has the form (<exp. type>,
            <human readable description>, <panel for add. options or None>)
        If panels for additional options must be created, they should use
        guiparent as parent
        """
        if guiparent:
            res = wx.xrc.XmlResource.Get()
            htmlPanel = res.LoadPanel(guiparent, "ExportSubHtml")
            ctrls = XrcControls(htmlPanel)
            config = self.mainControl.getConfig()

            ctrls.cbPicsAsLinks.SetValue(config.getboolean("main",
                    "html_export_pics_as_links"))
            ctrls.chTableOfContents.SetSelection(config.getint("main",
                    "export_table_of_contents"))
            ctrls.tfHtmlTocTitle.SetValue(config.get("main",
                    "html_toc_title"))

        else:
            htmlPanel = None
        
        return (
            (u"html_multi", _(u'One HTML page'), htmlPanel),
            (u"html_single", _(u'Set of HTML pages'), htmlPanel)
            )


    def getExportDestinationWildcards(self, exportType):
        """
        If an export type is intended to go to a file, this function
        returns a (possibly empty) sequence of tuples
        (wildcard description, wildcard filepattern).
        
        If an export type goes to a directory, None is returned
        """
        return None


    def getAddOptVersion(self):
        """
        Returns the version of the additional options information returned
        by getAddOpt(). If the return value is -1, the version info can't
        be stored between application sessions.
        
        Otherwise, the addopt information can be stored between sessions
        and can later handled back to the export method of the object
        without previously showing the export dialog.
        """
        return 0


    def getAddOpt(self, addoptpanel):
        """
        Reads additional options from panel addoptpanel.
        If getAddOptVersion() > -1, the return value must be a sequence
        of simple string, unicode and/or numeric objects. Otherwise, any object
        can be returned (normally the addoptpanel itself).
        Here, it returns a tuple with following items:
            * bool (as integer) if pictures should be exported as links
            * integer to control creation of table of contents
                (0: No; 1: as tree; 2: as list)
            * unistring: TOC title
            * unistring: name of export subdir for volatile files
                (= automatically generated files, e.g. formula images
                from MimeTeX).
        """
        if addoptpanel is None:
            # Return default set in options
            config = self.mainControl.getConfig()

            return ( boolToInt(config.getboolean("main",
                    "html_export_pics_as_links")),
                    config.getint("main", "export_table_of_contents"),
                    config.get("main", "html_toc_title"),
                    u"volatile"
                     )
        else:
            ctrls = XrcControls(addoptpanel)

            picsAsLinks = boolToInt(ctrls.cbPicsAsLinks.GetValue())
            tableOfContents = ctrls.chTableOfContents.GetSelection()
            tocTitle = ctrls.tfHtmlTocTitle.GetValue()

            return (picsAsLinks, tableOfContents, tocTitle, u"volatile")


    def setAddOpt(self, addOpt, addoptpanel):
        """
        Shows content of addOpt in the addoptpanel (must not be None).
        This function is only called if getAddOptVersion() != -1.
        """
        picsAsLinks, tableOfContents, tocTitle, volatileDir = \
                addOpt

        # volatileDir is currently ignored

        ctrls = XrcControls(addoptpanel)

        ctrls.cbPicsAsLinks.SetValue(picsAsLinks != 0)
        ctrls.chTableOfContents.SetSelection(tableOfContents)
        ctrls.tfHtmlTocTitle.SetValue(tocTitle)

        

    def setJobData(self, wikiDocument, wordList, exportType, exportDest,
            compatFilenames, addOpt, progressHandler):
        """
        Set all information necessary to run export operation.
        """

        self.setWikiDocument(wikiDocument)

        self.wordList = []
        for w in wordList:
            if self.wikiDocument.isDefinedWikiLink(w):
                self.wordList.append(w)

        if len(self.wordList) == 0:
            return False

#         self.wordList = wordList
        self.exportType = exportType
        self.exportDest = exportDest
        self.addOpt = addOpt
        self.progressHandler = progressHandler
        self.compatFilenames = compatFilenames

#             self.convertFilename = removeBracketsToCompFilename
        self.filenameConverter = FilenameConverter(bool(compatFilenames))
#         else:
#             self.convertFilename = removeBracketsFilename    # lambda s: mbcsEnc(s, "replace")[0]

        self.referencedStorageFiles = None
        
        return True



    def export(self, wikiDocument, wordList, exportType, exportDest,
            compatFilenames, addOpt, progressHandler, tempFileSetReset=True):
        """
        Run export operation. This is only called for real exports,
        previews use other functions.
        
        wikiDocument -- wikiDocument object
        wordList -- Sequence of wiki words to export
        exportType -- string tag to identify how to export
        exportDest -- Path to destination directory or file to export to
        compatFilenames -- Should the filenames be encoded to be lowest
                           level compatible (ascii only)?
        addOpt -- additional options returned by getAddOpt()
        """
        
#         print "export1", repr((pWiki, wikiDocument, wordList, exportType, exportDest,
#             compatFilenames, addopt))

        if not self.setJobData(wikiDocument, wordList, exportType, exportDest,
                compatFilenames, addOpt, progressHandler):
            return

        if exportType in (u"html_single", u"html_multi"):
            volatileDir = self.addOpt[3]

            volatileDir = join(self.exportDest, volatileDir)

            # Check if volatileDir is really a subdirectory of exportDest
            clearVolatile = testContainedInDir(self.exportDest, volatileDir)
            if clearVolatile:
                # Warning!!! rmtree() is very dangerous, don't make a mistake here!
                shutil.rmtree(volatileDir, True)

            # We must prepare a temporary file set for HTML exports
            self.tempFileSet = TempFileSet()
            self.tempFileSet.setPreferredPath(volatileDir)
            self.tempFileSet.setPreferredRelativeTo(self.exportDest)

            self.referencedStorageFiles = set()


        if exportType == u"html_multi":
            browserFile = self.exportHtmlMultiFile()
        elif exportType == u"html_single":
            browserFile = self._exportHtmlSingleFiles(self.wordList)

        # Other supported types: html_previewWX, html_previewIE, html_previewMOZ
        # are not handled in this function

        wx.GetApp().getInsertionPluginManager().taskEnd()

        if self.referencedStorageFiles is not None:
            # Some files must be available
            wikiPath = self.wikiDocument.getWikiPath()
            
            if not OsAbstract.samefile(wikiPath, self.exportDest):
                # Now we have to copy the referenced files to new location
                for rsf in self.referencedStorageFiles:
                    try:
                        OsAbstract.copyFile(join(wikiPath, rsf),
                                join(self.exportDest, rsf))
                    except IOError, e:
                        raise ExportException(unicode(e))


        if self.mainControl.getConfig().getboolean(
                "main", "start_browser_after_export") and browserFile:
            OsAbstract.startFile(self.mainControl, browserFile)

        if tempFileSetReset:
            self.tempFileSet.reset()
            self.tempFileSet = None
            self.copiedTempFileCache = None


    def startContinuousExport(self, wikiDocument, listPagesOperation,
            exportType, exportDest, compatFilenames, addOpt, progressHandler):
        
        self.listPagesOperation = listPagesOperation

        wordList = wikiDocument.searchWiki(self.listPagesOperation)
        
        self.listPagesOperation.beginWikiSearch(wikiDocument)

        # Initially static export
        self.export(wikiDocument, wordList, exportType, exportDest,
            compatFilenames, addOpt, progressHandler, tempFileSetReset=False)
            
        self.progressHandler = None

        self.__sinkWikiDocument = wxKeyFunctionSink((
                ("deleted wiki page", self.onDeletedWikiPage),
                ("renamed wiki page", self.onRenamedWikiPage),
                ("updated wiki page", self.onUpdatedWikiPage)
#                 ("saving new wiki page", self.onSavingNewWikiPage)
        ), self.wikiDocument.getMiscEvent())


    def stopContinuousExport(self):
        self.listPagesOperation.endWikiSearch()
        self.listPagesOperation = None
        self.__sinkWikiDocument.disconnect()

        self.tempFileSet.reset()
        self.tempFileSet = None
        self.copiedTempFileCache = None


    def onDeletedWikiPage(self, miscEvt):
        wikiWord = miscEvt.get("wikiPage").getWikiWord()

        if wikiWord not in self.wordList:
            return
            
        self.wordList.remove(wikiWord)
        
        if self.exportType == u"html_multi":
            self.exportHtmlMultiFile()

        elif self.exportType == u"html_single":
            self._exportHtmlSingleFiles([])


    def onRenamedWikiPage(self, miscEvt):
        oldWord = miscEvt.get("wikiPage").getWikiWord()
        newWord = miscEvt.get("newWord")
        newPage = self.wikiDocument.getWikiPage(newWord)
        
        oldInList = oldWord in self.wordList
        newInList = self.listPagesOperation.testWikiPageByDocPage(newPage)

        if not oldInList and not newInList:
            return

        if oldInList:
            self.wordList.remove(oldWord)
        
        if newInList:
            self.wordList.append(newWord)


        if self.exportType == u"html_multi":
            self.exportHtmlMultiFile()

        elif self.exportType == u"html_single":
            if newInList:
                updList = [newWord]
            else:
                updList = []

            self._exportHtmlSingleFiles(updList)


    def onUpdatedWikiPage(self, miscEvt):
        wikiPage = miscEvt.get("wikiPage")
        wikiWord = wikiPage.getWikiWord()

        oldInList = wikiWord in self.wordList
        newInList = self.listPagesOperation.testWikiPageByDocPage(wikiPage)

        if not oldInList:
            if not newInList:
                # Current set not affected
                return
            else:
                self.wordList.append(wikiWord)
                updList = [wikiWord]
        else:
            if not newInList:
                self.wordList.remove(wikiWord)
                updList = []
            else:
                updList = [wikiWord]
        
        if not wikiWord in self.wordList:
            return

        try:
            if self.exportType == u"html_multi":
                self.exportHtmlMultiFile()
    
            elif self.exportType == u"html_single":
                self._exportHtmlSingleFiles(updList)
        except WikiWordNotFoundException:
            pass



    def getTempFileSet(self):
        return self.tempFileSet


    _INTERNALJUMP_PREFIXMAP = {
        u"html_previewWX": u"internaljump:",
        u"html_previewIE": u"internaljump:",
        u"html_previewMOZ": u"file://internaljump/"
    }

    def _getInternaljumpPrefix(self):
        try:
            return self._INTERNALJUMP_PREFIXMAP[self.exportType]
        except IndexError:
            raise InternalError(
                    u"Trying to get internal jump prefix for non-preview export")


    def setLinkConverter(self, linkConverter):
        self.linkConverter = linkConverter


    def exportHtmlMultiFile(self, realfp=None, tocMode=None):
        """
        Multiple wiki pages in one file.
        """        
        config = self.mainControl.getConfig()
        sepLineCount = config.getint("main",
                "html_export_singlePage_sepLineCount", 10)

        if sepLineCount < 0:
            sepLineCount = 10
#         if len(self.wordList) == 1:
#             self.exportType = u"html_single"
#             return self._exportHtmlSingleFiles(self.wordList)

        self.setLinkConverter(LinkConverterForHtmlMultiPageExport(
                self.wikiDocument, self))

        self.buildStyleSheetList()

        if realfp is None:
            outputFile = join(self.exportDest, 
                    self.filenameConverter.getFilenameForWikiWord(
                    self.mainControl.wikiName) + ".html")

            if exists(pathEnc(outputFile)):
                os.unlink(pathEnc(outputFile))

            realfp = open(pathEnc(outputFile), "w")
        else:
            outputFile = None

        filePointer = utf8Writer(realfp, "replace")

        filePointer.write(self.getFileHeaderMultiPage(self.mainControl.wikiName))

        tocTitle = self.addOpt[2]
        
        if tocMode is None:
            tocMode = self.addOpt[1]

        if tocMode == 1:
            # Write a content tree at beginning
            rootPage = self.mainControl.getWikiDocument().getWikiPage(
                        self.mainControl.getWikiDocument().getWikiName())
            flatTree = rootPage.getFlatTree()

            filePointer.write((u'<h2>%s</h2>\n'
                    '%s%s<hr size="1"/>') %
                    (tocTitle, # = "Table of Contents"
                    self.getContentTreeBody(flatTree, linkAsFragments=True),
                    u'<br />\n' * sepLineCount))

        elif tocMode == 2:
            # Write a content list at beginning
            filePointer.write((u'<h2>%s</h2>\n'
                    '%s%s<hr size="1"/>') %
                    (tocTitle, # = "Table of Contents"
                    self.getContentListBody(linkAsFragments=True),
                    u'<br />\n' * sepLineCount))


        if self.progressHandler is not None:
            self.progressHandler.open(len(self.wordList))
            step = 0

        # Then create the big page word by word
        for word in self.wordList:
            if self.progressHandler is not None:
                step += 1
                self.progressHandler.update(step, _(u"Exporting %s") % word)

            wikiPage = self.wikiDocument.getWikiPage(word)
            if not self.shouldExport(word, wikiPage):
                continue

            try:
                content = wikiPage.getLiveText()
#                 formatDetails = wikiPage.getFormatDetails()
                    
                self.wordAnchor = _escapeAnchor(word)
                formattedContent = self.formatContent(wikiPage)

                filePointer.write((u'<span class="wiki-name-ref">'
                        u'[<a name="%s">%s</a>]</span><br /><br />'
                        u'<span class="parent-nodes">parent nodes: %s</span>'
                        u'<br />%s%s<hr size="1"/>') %
                        (self.wordAnchor, word,
                        self.getParentLinks(wikiPage, False), formattedContent,
                        u'<br />\n' * sepLineCount))
            except Exception, e:
                traceback.print_exc()

        self.wordAnchor = None

        filePointer.write(self.getFileFooter())
        
        filePointer.reset()

        if outputFile is not None:
            realfp.close()

        self.copyCssFiles(self.exportDest)
        return outputFile


    def _exportHtmlSingleFiles(self, wordListToUpdate):
        self.setLinkConverter(LinkConverterForHtmlSingleFilesExport(
                self.wikiDocument, self))
        self.buildStyleSheetList()


        if self.addOpt[1] in (1, 2):
            # TODO Configurable name
            outputFile = join(self.exportDest, pathEnc(u"index.html"))
            try:
                if exists(pathEnc(outputFile)):
                    os.unlink(pathEnc(outputFile))
    
                realfp = open(pathEnc(outputFile), "w")
                fp = utf8Writer(realfp, "replace")

                # TODO Factor out HTML header generation                
                fp.write(self._getGenericHtmlHeader(self.addOpt[2]) + 
                        u"    <body>\n")
                if self.addOpt[1] == 1:
                    # Write a content tree
                    rootPage = self.mainControl.getWikiDocument().getWikiPage(
                                self.mainControl.getWikiDocument().getWikiName())
                    flatTree = rootPage.getFlatTree()
    
                    fp.write((u'<h2>%s</h2>\n'
                            '%s') %
                            (self.addOpt[2],  # = "Table of Contents"
                            self.getContentTreeBody(flatTree, linkAsFragments=False)
                            ))
                elif self.addOpt[1] == 2:
                    # Write a content list
                    fp.write((u'<h2>%s</h2>\n'
                            '%s') %
                            (self.addOpt[2],  # = "Table of Contents"
                            self.getContentListBody(linkAsFragments=False)
                            ))

                fp.write(self.getFileFooter())

                fp.reset()        
                realfp.close()
            except Exception, e:
                traceback.print_exc()


        if self.progressHandler is not None:
            self.progressHandler.open(len(self.wordList))
            step = 0

        for word in wordListToUpdate:
            if self.progressHandler is not None:
                step += 1
                self.progressHandler.update(step, _(u"Exporting %s") % word)

            wikiPage = self.wikiDocument.getWikiPage(word)
            if not self.shouldExport(word, wikiPage):
                continue

            self.exportWordToHtmlPage(self.exportDest, word, False)

        self.copyCssFiles(self.exportDest)
        rootFile = join(self.exportDest,
                self.filenameConverter.getFilenameForWikiWord(self.wordList[0]) +
                ".html")
        return rootFile


    def exportWordToHtmlPage(self, dir, word, startFile=True,
            onlyInclude=None):
        outputFile = join(dir,
                self.filenameConverter.getFilenameForWikiWord(word) + ".html")

        try:
            if exists(pathEnc(outputFile)):
                os.unlink(pathEnc(outputFile))

            realfp = open(pathEnc(outputFile), "w")
            fp = utf8Writer(realfp, "replace")
            
            wikiPage = self.wikiDocument.getWikiPage(word)
            fp.write(self.exportWikiPageToHtmlString(wikiPage,
                    startFile, onlyInclude))
            fp.reset()        
            realfp.close()
        except Exception, e:
            sys.stderr.write("Error while exporting word %s" % repr(word))
            traceback.print_exc()

        return outputFile


    def exportWikiPageToHtmlString(self, wikiPage,
            startFile=True, onlyInclude=None):
        """
        Read content of wiki word word, create an HTML page and return it
        """
        result = []

        formattedContent = self.formatContent(wikiPage)

        if Configuration.isUnicode():
            result.append(self.getFileHeader(wikiPage))

        # if startFile is set then this is the only page being exported so
        # do not include the parent header.
        if not startFile:
            result.append((u'<span class="parent-nodes">parent nodes: %s</span>'
                    '<br /><br />\n')
                    % self.getParentLinks(wikiPage, True, onlyInclude))

        result.append(formattedContent)
        result.append(self.getFileFooter())
        
        return u"".join(result)


    def _getGenericHtmlHeader(self, title, charSet=u'; charset=UTF-8'):
        styleSheets = []
        for dummy, url in self.styleSheetList:
            styleSheets.append(
                    u'        <link type="text/css" rel="stylesheet" href="%(url)s">' %
                    locals())
        
        styleSheets = u"\n".join(styleSheets)

#         styleSheet = self.styleSheet
        config = self.mainControl.getConfig()
        docType = config.get("main", "html_header_doctype",
                'DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.0 Transitional//EN"')

        return u"""<!%(docType)s>
<html>
    <head>
        <meta http-equiv="content-type" content="text/html%(charSet)s">
        <title>%(title)s</title>
%(styleSheets)s
    </head>
""" % locals()



    def getFileHeaderMultiPage(self, title):
        """
        Return file header for an HTML file containing multiple pages
        """
        return self._getGenericHtmlHeader(title) + u"    <body>\n"


    def _getBodyTag(self, wikiPage):
        # Get application defaults from config
        config = self.mainControl.getConfig()
        linkcol = config.get("main", "html_body_link")
        alinkcol = config.get("main", "html_body_alink")
        vlinkcol = config.get("main", "html_body_vlink")
        textcol = config.get("main", "html_body_text")
        bgcol = config.get("main", "html_body_bgcolor")
        bgimg = config.get("main", "html_body_background")

        # Get property settings
        linkcol = wikiPage.getPropertyOrGlobal(u"html.linkcolor", linkcol)
        alinkcol = wikiPage.getPropertyOrGlobal(u"html.alinkcolor", alinkcol)
        vlinkcol = wikiPage.getPropertyOrGlobal(u"html.vlinkcolor", vlinkcol)
        textcol = wikiPage.getPropertyOrGlobal(u"html.textcolor", textcol)
        bgcol = wikiPage.getPropertyOrGlobal(u"html.bgcolor", bgcol)
        bgimg = wikiPage.getPropertyOrGlobal(u"html.bgimage", bgimg)
        
        # Filter color
        def filterCol(col, prop):
            if colorDescToRgbTuple(col) is not None:
                return u'%s="%s"' % (prop, col)
            else:
                return u''
        
        linkcol = filterCol(linkcol, u"link")
        alinkcol = filterCol(alinkcol, u"alink")
        vlinkcol = filterCol(vlinkcol, u"vlink")
        textcol = filterCol(textcol, u"text")
        bgcol = filterCol(bgcol, u"bgcolor")
        
        if bgimg:
            if bgimg.startswith(u"rel://"):
                # Relative URL
                if self.asHtmlPreview:
                    # If preview, make absolute
                    bgimg = self.mainControl.makeRelUrlAbsolute(bgimg)
                else:
                    # If export, reformat a bit
                    bgimg = bgimg[6:]

            bgimg = u'background="%s"' % bgimg
        else:
            bgimg = u''
            
            
        if self.exportType in (u"html_previewIE", u"html_previewMOZ"):
            dblClick = 'ondblclick="window.location.href = &quot;' + \
                    self._getInternaljumpPrefix() + \
                    'mouse/leftdoubleclick/preview/body&quot;;"'

        else:
            dblClick = ''

        # Build tagstring
        bodytag = u" ".join((linkcol, alinkcol, vlinkcol, textcol, bgcol, bgimg, dblClick))
        if len(bodytag) > 6:  # the 6 spaces
            bodytag = "<body %s>" % bodytag
        else:
            bodytag = "<body>"

        return bodytag


    def getFileHeader(self, wikiPage):
        """
        Return the header part of an HTML file for wikiPage.
        wikiPage -- WikiPage object
        """

        return self._getGenericHtmlHeader(wikiPage.getWikiWord()) + \
                u"    %s\n" % self._getBodyTag(wikiPage)



    def getFileFooter(self):
        return u"""    </body>
</html>
"""

    def getParentLinks(self, wikiPage, asHref=True, wordsToInclude=None):
        parents = u""
        parentRelations = wikiPage.getParentRelationships()[:]
        self.mainControl.getCollator().sort(parentRelations)
        
        for relation in parentRelations:
            if wordsToInclude and relation not in wordsToInclude:
                continue

            if parents != u"":
                parents = parents + u" | "

            if asHref:
                parents = parents +\
                        u'<span class="parent-node"><a href="%s.html">%s</a></span>' %\
                        (self.filenameConverter.getFilenameForWikiWord(relation), relation)
            else:
                parents = parents +\
                u'<span class="parent-node"><a href="#%s">%s</a></span>' %\
                (_escapeAnchor(relation), relation)

        return parents


    def getBasePageAst(self):
        return self.basePageAst


    def buildStyleSheetList(self):
        """
        Sets the self.styleSheetList. This is a list of tuples
        (<source CSS path>, <dest CSS file name/url>). The source file name may be
        None if the file (normally for preview mode) shouldn't be copied.
        Must be called after export type is set!
        """
        asPreview = self.exportType in ("html_previewIE", "html_previewMOZ", "html_previewWX")
        if asPreview:
            # Step one: Create paths
            pathlist = [
                    # System base file
                    join(self.mainControl.wikiAppDir, "appbase.css"),
                    # Administrator modified application base file
                    join(self.mainControl.wikiAppDir, "export",
                        "wikistyle.css"),

                    # User modified file
                    join(wx.GetApp().globalConfigSubDir, "wikistyle.css")
                ]

            # Wiki specific file
            if self.wikiDocument is not None:
                pathlist.append(join(self.wikiDocument.getDataDir(),
                        "wikistyle.css"))

            # Overruling wikipreview.css files
            pathlist += [
                    # System base file (does not exist normally)
                    join(self.mainControl.wikiAppDir, "prevappbase.css"),
                    # Administrator modified application base file
                    join(self.mainControl.wikiAppDir, "export",
                            "wikipreview.css"),
                    # User modified file
                    join(wx.GetApp().globalConfigSubDir, "wikipreview.css")
                ]

            # Wiki specific file
            if self.wikiDocument is not None:
                pathlist.append(join(self.wikiDocument.getDataDir(),
                        "wikipreview.css"))

            # Step two: Check files for existence and create styleSheetList
            # We don't need the source paths, only a list of URLs to the
            # original files
            self.styleSheetList = []
            for p in pathlist:
                if not exists(pathEnc(p)):
                    continue
                
                self.styleSheetList.append((None, "file:" + urlFromPathname(p)))
            
        else:
            result = [
                    # System base file
                    (join(self.mainControl.wikiAppDir, "appbase.css"), "appbase.css"),
                    # Administrator modified application base file
                    (join(self.mainControl.wikiAppDir, "export", "wikistyle.css"),
                        "admbase.css"),
                    # User modified file
                    (join(wx.GetApp().globalConfigSubDir, "wikistyle.css"),
                        "userbase.css")
                ]

            # Wiki specific file
            if self.wikiDocument is not None:
                result.append((join(self.wikiDocument.getDataDir(),
                        "wikistyle.css"), "wikistyle.css"))

            # Filter non-existent
            self.styleSheetList = [ item for item in result
                    if exists(pathEnc(item[0])) ]




    def copyCssFiles(self, dir):
        for src, dst in self.styleSheetList:
            if src is None:
                continue
            try:
                OsAbstract.copyFile(pathEnc(src), pathEnc(join(dir, dst)))
            except:
                traceback.print_exc()


    def shouldExport(self, wikiWord, wikiPage=None):
        if not wikiPage:
            try:
                wikiPage = self.wikiDocument.getWikiPage(wikiWord)
            except WikiWordNotFoundException:
                return False

        return strToBool(wikiPage.getProperties().get("export", ("True",))[-1])


    def getContentListBody(self, linkAsFragments):
#         if linkAsFragments:
#             def wordToLink(wikiWord):
#                 relUnAlias = self.wikiDocument.getAliasesWikiWord(wikiWord)
#                 # TODO Use self.convertFilename here?
#                 return u"#%s" % _escapeAnchor(relUnAlias)
#         else:
#             def wordToLink(wikiWord):
#                 relUnAlias = self.wikiDocument.getAliasesWikiWord(wikiWord)
#                 # TODO Use self.convertFilename here?
#                 return self.linkConverter.getLinkForWikiWord(relUnAlias)

        result = []
        wordToLink = self.linkConverter.getLinkForWikiWord
        
        result.append(u"<ul>\n")
        for wikiWord in self.wordList:
            result.append(u'<li><a href="%s">%s</a>\n' % (wordToLink(wikiWord),
                    wikiWord))

        result.append(u"</ul>\n")
        
        return u"".join(result)


    def getContentTreeBody(self, flatTree, linkAsFragments):   # rootWords
        """
        Return content tree.
        flatTree -- flat tree as returned by DocPages.WikiPage.getFlatTree(),
            list of tuples (wikiWord, deepness)
        """
#         if linkAsFragments:
#             def wordToLink(wikiWord):
#                 relUnAlias = self.wikiDocument.getAliasesWikiWord(wikiWord)
#                 # TODO Use self.convertFilename here?
#                 return u"#%s" % _escapeAnchor(relUnAlias)
#         else:
#             def wordToLink(wikiWord):
#                 relUnAlias = self.wikiDocument.getAliasesWikiWord(wikiWord)
#                 # TODO Use self.convertFilename here?
#                 return self.linkConverter.getLinkForWikiWord(relUnAlias)

        wordSet = set(self.wordList)
        deepStack = [-1]
        result = []
        wordToLink = self.linkConverter.getLinkForWikiWord
        lastdeepness = 0
        
        for wikiWord, deepness in flatTree:
            if not wikiWord in wordSet:
                continue
                
            deepness += 1
            if deepness > lastdeepness:
                # print "getContentTreeBody9", deepness, lastdeepness
                result.append(u"<ul>\n" * (deepness - lastdeepness))
            elif deepness < lastdeepness:
                # print "getContentTreeBody10", deepness, lastdeepness
                result.append(u"</ul>\n" * (lastdeepness - deepness))
                
            lastdeepness = deepness

            wordSet.remove(wikiWord)

            # print "getContentTreeBody11", repr(wikiWord)
            result.append(u'<li><a href="%s">%s</a>\n' % (wordToLink(wikiWord),
                    wikiWord))

        result.append(u"</ul>\n" * lastdeepness)

        # list words not in the tree
        if len(wordSet) > 0:
            # print "getContentTreeBody13"
            remainList = list(wordSet)
            self.mainControl.getCollator().sort(remainList)
            
            # print "getContentTreeBody14", repr(remainList)
            result.append(u"<ul>\n")
            for wikiWord in remainList:
                result.append(u'<li><a href="%s">%s</a>\n' % (wordToLink(wikiWord),
                        wikiWord))

            result.append(u"</ul>\n")


        return u"".join(result)


    def getCurrentWikiWord(self):
        """
        Returns the wiki word which is currently processed by the exporter.
        """
        return self.wikiWord



    def formatContent(self, wikiPage):
        word = wikiPage.getWikiWord()
        content = wikiPage.getLiveText()
        formatDetails = wikiPage.getFormatDetails()
        self.basePageAst = wikiPage.getLivePageAst()

        if self.linkConverter is None:
            self.linkConverter = BasicLinkConverter(self.wikiDocument, self)
 
        self.asIntHtmlPreview = (self.exportType == "html_previewWX")
        self.asHtmlPreview = self.exportType in ("html_previewWX",
                "html_previewIE", "html_previewMOZ")
        self.wikiWord = word

        self.result = []
        self.optsStack = StackedCopyDict()
        self.insertionVisitStack = []
        self.astNodeStack = []
        self.copiedTempFileCache = {}

        self.outFlagEatPostBreak = False
        self.outFlagPostBreakEaten = False

        # Get property pattern
        if self.asHtmlPreview:
            proppattern = self.mainControl.getConfig().get(
                        "main", "html_preview_proppattern", u"")
        else:
            proppattern = self.mainControl.getConfig().get(
                        "main", "html_export_proppattern", u"")
                        
        self.proppattern = re.compile(proppattern,
                re.DOTALL | re.UNICODE | re.MULTILINE)

        if self.asHtmlPreview:
            self.proppatternExcluding = self.mainControl.getConfig().getboolean(
                        "main", "html_preview_proppattern_is_excluding", u"True")
        else:
            self.proppatternExcluding = self.mainControl.getConfig().getboolean(
                        "main", "html_export_proppattern_is_excluding", u"True")

        if self.asHtmlPreview:
            facename = self.mainControl.getConfig().get(
                    "main", "facename_html_preview", u"")
            if facename:
                self.outAppend('<font face="%s">' % facename)

        self.processAst(content, self.basePageAst)

        if self.asHtmlPreview and facename:
            self.outAppend('</font>')

        return self.getOutput()


    def _getImageDims(self, absUrl):
        """
        Return tuple (width, height) of image absUrl or (None, None) if it
        couldn't be determined.
        """
        try:
            if absUrl.startswith(u"file:"):
                absLink = pathnameFromUrl(absUrl)
                imgFile = file(absLink, "rb")
            else:
                imgFile = urllib.urlopen(absUrl)
                imgData = imgFile.read()
                imgFile.close()
                imgFile = StringIO(imgData)

            img = wx.EmptyImage(0, 0)
            img.LoadStream(imgFile)
            imgFile.close()
            
            if img.Ok():
                return img.GetWidth(), img.GetHeight()

            return None, None

        except IOError:
            return None, None


    def isHtmlSizeValue(sizeStr):
        """
        Test unistring sizestr if it is a valid HTML size info and returns
        True or False
        """
        sizeStr = sizeStr.strip()
        if len(sizeStr) == 0:
            return False

        if sizeStr[-1] == "%":
            sizeStr = sizeStr[:-1]

        try:
            val = int(sizeStr)
            return val >= 0
        except ValueError:
            return False

    isHtmlSizeValue = staticmethod(isHtmlSizeValue)


    def outAppend(self, toAppend, eatPreBreak=False, eatPostBreak=False):
        """
        Append toAppend to self.result, maybe remove or modify it according to
        flags
        """
        if toAppend == u"":    # .strip()
            return

        if self.outFlagEatPostBreak and toAppend.strip() == u"<br />":
            self.outFlagEatPostBreak = eatPostBreak
            self.outFlagPostBreakEaten = True
            return

        if eatPreBreak and len(self.result) > 0 and \
                self.result[-1].strip() == u"<br />" and \
                not self.outFlagPostBreakEaten:
            self.result[-1] = toAppend
            self.outFlagEatPostBreak = eatPostBreak
            return
        
        if self.outFlagPostBreakEaten:
            self.outFlagPostBreakEaten = (toAppend.strip() == u"<br />")

        self.outFlagEatPostBreak = eatPostBreak
        self.result.append(toAppend)


    def outEatBreaks(self, toAppend, **kpars):
        """
        Sets flags so that a <br /> before and/or after the item toAppend
        are eaten (removed) and appends toAppend to self.result
        """
        kpars["eatPreBreak"] = True
        kpars["eatPostBreak"] = True

        self.outAppend(toAppend, **kpars)



    START_INDENT_MAP = {"normalindent": u"<ul>", "ul": u"<ul>", "ol": u"<ol>"}

    END_INDENT_MAP = {"normalindent": u"</ul>\n", "ul": u"</ul>\n",
            "ol": u"</ol>\n"}

    def outStartIndentation(self, indType):
        """
        Insert indentation, bullet, or numbered list start tag.
        ind -- indentation depth
        """
        if indType == "normalindent" and self.asIntHtmlPreview:
            self.outEatBreaks(u"<blockquote>")
        else:
            tag = self.START_INDENT_MAP[indType]

# TODO: (hasStates() was removed) if self.hasStates() or self.asIntHtmlPreview:
            if self.asIntHtmlPreview:
                # It is already indented, so additional indents will not
                # produce blank lines which must be eaten
                self.outAppend(tag)
            else:
                self.outEatBreaks(tag)

    def outEndIndentation(self, indType):
        """
        Insert indentation, bullet, or numbered list start tag.
        ind -- indentation depth
        """
        if indType == "normalindent" and self.asIntHtmlPreview:
            self.outEatBreaks(u"</blockquote>\n")
        else:
            tag = self.END_INDENT_MAP[indType]

# TODO: (hasStates() was removed) if self.hasStates() or self.asIntHtmlPreview:
            if self.asIntHtmlPreview:
                # It is already indented, so additional indents will not
                # produce blank lines which must be eaten  (?)
                self.outAppend(tag, eatPreBreak=True)
            else:
                self.outEatBreaks(tag)


    def getOutput(self):
        return u"".join(self.result)



    def _processTable(self, content, astNode):
        """
        Write out content of a table as HTML code.
        
        astNode -- node of type "table"
        """
        self.astNodeStack.append(astNode)

        self.outAppend(u'<table border="2">\n')
        
        for row in astNode.iterFlatByName("tableRow"):
            self.outAppend(u"<tr>")
            for cell in row.iterFlatByName("tableCell"):
                self.outAppend(u"<td>")
                self.processAst(content, cell)
                self.outAppend(u"</td>")
            self.outAppend(u"</tr>\n")
        self.outAppend(u'</table>\n', eatPostBreak=not self.asIntHtmlPreview)

        self.astNodeStack.pop()


    def _processInsertion(self, fullContent, astNode):
        self.astNodeStack.append(astNode)
        astNode.astNodeStack = self.astNodeStack

        try:
            return self._actualProcessInsertion(fullContent, astNode)
        finally:
            self.astNodeStack.pop()


    # TODO Context support so an insertion reacts differently in e.g. tables
    def _actualProcessInsertion(self, fullContent, astNode):
        """
        Process an insertion (e.g. "[:page:WikiWord]")
        
        astNode -- node of type "insertion"
        """
        wordList = None
        content = None
        htmlContent = None
        key = astNode.key
        value = astNode.value
        appendices = astNode.appendices

        if key == u"page":
            if (u"wikipage/" + value) in self.insertionVisitStack:
                # Prevent infinite recursion
                return

            docpage = self.wikiDocument.getWikiPageNoError(value)
            pageAst = docpage.getLivePageAst()

            self.insertionVisitStack.append("wikipage/" + value)
            try:
                
                # Inside an inserted page we don't want anchors to the
                # headings to avoid collisions with headings of surrounding
                # page.
                
                with self.optsStack:
                    self.optsStack["anchorForHeading"] = False
                    self.processAst(docpage.getLiveText(), pageAst)

            finally:
                del self.insertionVisitStack[-1]

            return
            
        elif key == u"rel":
            # List relatives (children, parents)
            if value == u"parents":
                wordList = self.wikiDocument.getWikiData().getParentRelationships(
                        self.wikiWord)
            elif value == u"children":
                existingonly = (u"existingonly" in appendices) # or \
                        # (u"existingonly +" in insertionAstNode.appendices)
                wordList = self.wikiDocument.getWikiData().getChildRelationships(
                        self.wikiWord, existingonly=existingonly,
                        selfreference=False)
            elif value == u"parentless":
                wordList = self.wikiDocument.getWikiData().getParentlessWikiWords()
            elif value == u"undefined":
                wordList = self.wikiDocument.getWikiData().getUndefinedWords()
            elif value == u"top":
                htmlContent = u'<a href="#">Top</a>'
            elif value == u"back":
                if self.asHtmlPreview:
                    htmlContent = \
                            u'<a href="' + self._getInternaljumpPrefix() + \
                            u'action/history/back">Back</a>'
                else:
                    htmlContent = \
                            u'<a href="javascript:history.go(-1)">Back</a>'

        elif key == u"self":
            htmlContent = escapeHtml(self.getCurrentWikiWord())

        elif key == u"savedsearch":
            datablock = self.wikiDocument.getWikiData().retrieveDataBlock(
                    u"savedsearch/" + value)
            if datablock is not None:
                searchOp = SearchReplaceOperation()
                searchOp.setPackedSettings(datablock)
                searchOp.replaceOp = False
                wordList = self.wikiDocument.searchWiki(searchOp)
        elif key == u"toc" and value == u"":
            pageAst = self.getBasePageAst()

            self.outAppend(u'<div class="page-toc">\n')
            
            for node in pageAst.iterFlatByName("heading"):
                headLevel = node.level            
                if self.asIntHtmlPreview:
                    # Simple indent for internal preview
                    self.outAppend(u"&nbsp;&nbsp;" * (headLevel - 1))
                else:
                    # use css otherwise
                    self.outAppend(u'<div class="page-toc-level%i">' %
                            headLevel)

                if self.wordAnchor:
                    anchor = self.wordAnchor + (u"#.h%i" % node.pos)
                else:
                    anchor = u".h%i" % node.pos

                self.outAppend(u'<a href="#%s">' % anchor)

                with self.optsStack:
                    self.optsStack["suppressLinks"] = True
                    self.processAst(fullContent, node.contentNode)

                self.outAppend(u'</a>')

                if self.asIntHtmlPreview:
                    self.outAppend(u'<br />\n')
                else:
                    self.outAppend(u'</div>\n')

            self.outAppend(u"</div>\n")
#             htmlContent = u"".join(htmlContent)

        elif key == u"eval":
            if not self.mainControl.getConfig().getboolean("main",
                    "insertions_allow_eval", False):
                # Evaluation of such insertions not allowed
                htmlContent = _(u"<pre>[Allow evaluation of insertions in "
                        "\"Options\", page \"Security\", option "
                        "\"Process insertion scripts\"]</pre>")
            else:
                evalScope = {"pwiki": self.getMainControl(),
                        "lib": self.getMainControl().evalLib}
                expr = astNode.value
                # TODO Test security
                try:
                    content = unicode(eval(re.sub(u"[\n\r]", u"", expr),
                            evalScope))
                except Exception, e:
                    s = StringIO()
                    traceback.print_exc(file=s)
                    htmlContent = u"\n<pre>\n" + \
                            escapeHtmlNoBreaks(s.getvalue()) + u"\n</pre>\n"
        elif key == u"iconimage":
            imgName = astNode.value
            icPath = wx.GetApp().getIconCache().lookupIconPath(imgName)
            if icPath is None:
                htmlContent = _(u"<pre>[Icon '%s' not found]</pre>" % imgName)
            else:
                url = self.copiedTempFileCache.get(icPath)
                if url is None:
                    tfs = self.getTempFileSet()
                    # TODO Take suffix from icPath
                    dstFullPath = tfs.createTempFile("", ".gif", relativeTo="")
                    pythonUrl = (self.exportType != "html_previewWX")
                    url = tfs.getRelativeUrl(None, dstFullPath, pythonUrl=pythonUrl)

                    OsAbstract.copyFile(icPath, dstFullPath)
                    self.copiedTempFileCache[icPath] = url
                
                htmlContent = u'<img src="%s" />' % url
        else:
            # Call external plugins
            exportType = self.exportType
            handler = wx.GetApp().getInsertionPluginManager().getHandler(self,
                    exportType, key)

            if handler is None and self.asHtmlPreview:
                # No handler found -> try to find generic HTML preview handler
                exportType = "html_preview"
                handler = wx.GetApp().getInsertionPluginManager().getHandler(self,
                        exportType, key)

            if handler is not None:
                try:
                    htmlContent = handler.createContent(self, exportType,
                            astNode)
                except Exception, e:
                    s = StringIO()
                    traceback.print_exc(file=s)
                    htmlContent = u"<pre>" + s.getvalue() + u"</pre>"

                if htmlContent is None:
                    htmlContent = u""
            else:
                # Try to find a generic handler for export type
                # "wikidpad_language"
                handler = wx.GetApp().getInsertionPluginManager().getHandler(self,
                        "wikidpad_language", key)
                if handler is not None:
                    try:
                        # This content is in WikidPad markup language
                        # and must be postprocessed
                        content = handler.createContent(self,
                                "wikidpad_language", astNode)
                    except Exception, e:
                        s = StringIO()
                        traceback.print_exc(file=s)
                        htmlContent = u"<pre>" + s.getvalue() + u"</pre>"

        if wordList is not None:
            # Create content as a nicely formatted list of wiki words
            
            if len(wordList) == 0:
                content = u""
            else:
                # wordList was set, so build a nicely formatted list of wiki words

                # Check for desired number of columns (as appendix e.g.
                # "columns 3" was set) and other settings
                cols = 1
                asList = False

                for ap in appendices:
                    if ap.startswith(u"columns "):
                        try:
                            v = int(ap[8:])
                            if v > 0:
                                cols = v
                                break
                        except ValueError:
                            pass
                    elif ap == "aslist":
                        asList = True

                self.mainControl.getCollator().sort(wordList)
    
                # TODO: Generate ready-made HTML content
                if cols > 1:
                    # We need a table for the wordlist
                    self.outAppend(u"<table>\n")
                    colpos = 0
                    for word in wordList:
                        if colpos == 0:
                            # Start table row
                            self.outAppend(u"<tr>")
                            
                        self.outAppend(u'<td valign="top">')
                        self._processWikiWord(word)
                        self.outAppend(u'</td>')
                        
                        colpos += 1
                        if colpos == cols:
                            # At the end of a row
                            colpos = 0
                            self.outAppend(u"</tr>\n")
                            
                    # Fill the last incomplete row with empty cells if necessary
                    if colpos > 0:
                        while colpos < cols:
                            self.outAppend(u"<td></td>")
                            colpos += 1
    
                        self.outAppend(u"</tr>\n")
                    
                    self.outAppend(u"</table>")
                elif asList:
                    
                    firstWord = True
                    for word in wordList:
                        if firstWord:
                            firstWord = False
                        else:
                            self.outAppend(", ")
                        self._processWikiWord(word)

                else:   # cols == 1 and not asList
                    firstWord = True
                    for word in wordList:
                        if firstWord:
                            firstWord = False
                        else:
                            self.outAppend("<br />\n")
                            
                        self.outAppend(u'<td valign="top">')
                        self._processWikiWord(word)
                        self.outAppend(u'</td>')
                    
                return


        if content is not None:
            # Content was set, so use standard formatting rules to create
            # tokens out of it and process them
            docPage = self.wikiDocument.getWikiPageNoError(self.wikiWord)
            self.processAst(content, docPage.parseTextInContext(content))

        elif htmlContent is not None:
            self.outAppend(htmlContent)


    def _processWikiWord(self, astNodeOrWord, fullContent=None):
        self.astNodeStack.append(astNodeOrWord)

        if isinstance(astNodeOrWord, SyntaxNode):
            wikiWord = astNodeOrWord.wikiWord
            anchorLink = astNodeOrWord.anchorLink
            titleNode = astNodeOrWord.titleNode
        else:
            wikiWord = astNodeOrWord
            anchorLink = None
            titleNode = None
            
        
        link = self.linkConverter.getLinkForWikiWord(wikiWord)
        
        selfLink = False

        if link:
            linkTo = self.wikiDocument.getUnAliasedWikiWord(wikiWord)

            # Test if link to same page itself (maybe with an anchor fragment)
            if not self.exportType in (u"html_multi", u"xml"):
                linkFrom = self.wikiDocument.getUnAliasedWikiWord(self.wikiWord)
                if linkTo is not None and linkTo == linkFrom:
                    # Page links to itself
                    selfLink = True

            # Add anchor fragment if present
            if anchorLink:
                if selfLink:
                    link = u"#" + anchorLink
                else:
                    link += u"#" + anchorLink

            title = None
            if linkTo is not None:
                propList = self.wikiDocument.getPropertyTriples(linkTo,
                        u"short_hint", None)
                if len(propList) > 0:
                    title = propList[-1][2]

            if self.optsStack.get("suppressLinks", False):
                self.outAppend(u'<span class="wiki-link">')
            else:
                if title is not None:
                    self.outAppend(u'<span class="wiki-link"><a href="%s" title="%s">' %
                            (link, escapeHtmlNoBreaks(title)))
                else:
                    self.outAppend(u'<span class="wiki-link"><a href="%s">' %
                            link)

            if titleNode is not None:
                with self.optsStack:
                    self.optsStack["suppressLinks"] = True
                    self.processAst(fullContent, titleNode)
            else:
                self.outAppend(escapeHtml(wikiWord))                        

            if self.optsStack.get("suppressLinks", False):
                self.outAppend(u'</span>')
            else:
                self.outAppend(u'</a></span>')
        else:
            if titleNode is not None:
                self.processAst(fullContent, titleNode)
            else:
                if isinstance(astNodeOrWord, SyntaxNode):
                    self.outAppend(escapeHtml(astNodeOrWord.getString()))
                else:
                    self.outAppend(escapeHtml(astNodeOrWord))

        self.astNodeStack.pop()


    def processAst(self, content, pageAst):
        """
        Actual token to HTML converter. May be called recursively
        """
        self.astNodeStack.append(pageAst)

        for node in pageAst.iterFlatNamed():
            tname = node.name
            
            if tname is None:
                continue            
            elif tname == "plainText":
                self.outAppend(escapeHtml(node.getString()))
            elif tname == "lineBreak":
                self.outAppend(u"<br />\n")
            elif tname == "newParagraph":
                self.outAppend(u"\n<p />")
            elif tname == "whitespace":
                self.outAppend(u" ")

            elif tname == "indentedText":
                self.outStartIndentation("normalindent")
                self.processAst(content, node)
                self.outEndIndentation("normalindent")
            elif tname == "orderedList":
                self.outStartIndentation("ol")
                self.processAst(content, node)
                self.outEndIndentation("ol")
            elif tname == "unorderedList":
                self.outStartIndentation("ul")
                self.processAst(content, node)
                self.outEndIndentation("ul")

            elif tname == "bullet":
#                 print "--bullet1", repr(self.result[-1])
                self.outAppend(u"\n<li />", eatPreBreak=True)
            elif tname == "number":
                self.outAppend(u"\n<li />", eatPreBreak=True)

            elif tname == "italics":
                self.outAppend(u"<i>")
                self.processAst(content, node)
                self.outAppend(u"</i>")
            elif tname == "bold":
                self.outAppend(u"<b>")
                self.processAst(content, node)
                self.outAppend(u"</b>")

            elif tname == "htmlTag" or tname == "htmlEntity":
                self.outAppend(node.getString())

            elif tname == "heading":
                if self.optsStack.get("anchorForHeading", True):
                    if self.wordAnchor:
                        anchor = self.wordAnchor + (u"#.h%i" % node.pos)
                    else:
                        anchor = u".h%i" % node.pos

                    self.outAppend(u'<a name="%s"></a>' % anchor)
                    
                boundHeadLevel = min(6, node.level)
                self.outAppend(u"<h%i>" % boundHeadLevel, eatPreBreak=True)
                self.processAst(content, node.contentNode)
                self.outAppend(u"</h%i>\n" % boundHeadLevel, eatPostBreak=True)

            elif tname == "horizontalLine":
                self.outEatBreaks(u'<hr size="1" />\n')

            elif tname == "preBlock":
                self.outAppend(u"<pre>%s</pre>\n" %
                        escapeHtmlNoBreaks(
                        node.findFlatByName("preText").getString()), True,
                        not self.asIntHtmlPreview)
                if self.asIntHtmlPreview:
                    self.outAppend(u"<br />\n")
            elif tname == "todoEntry":
                self.outAppend(u'<span class="todo">%s%s' %
                        (node.key, node.delimiter))
                self.processAst(content, node.valueNode)
                self.outAppend(u'</span>')
            elif tname == "property":
                for propKey, propValue in node.props:
                    standardProperty = u"%s: %s" % (propKey, propValue)
                    standardPropertyMatching = \
                            bool(self.proppattern.match(standardProperty))
                    # Output only for different truth values
                    # (Either it matches and matching props should not be
                    # hidden or vice versa)
                    if standardPropertyMatching != self.proppatternExcluding:
                        self.outAppend( u'<span class="property">[%s: %s]</span>' % 
                                (escapeHtml(propKey),
                                escapeHtml(propValue)) )
            elif tname == "insertion":
                self._processInsertion(content, node)
            elif tname == "script":
                pass  # Hide scripts
            elif tname == "noExport":
                pass  # Hide no export areas
            elif tname == "anchorDef":
                if self.wordAnchor:
                    self.outAppend('<a name="%s"></a>' %
                            (self.wordAnchor + u"#" + node.anchorLink))
                else:
                    self.outAppend('<a name="%s"></a>' % node.anchorLink)                
            elif tname == "wikiWord":
                self._processWikiWord(node, content)
            elif tname == "table":
                self._processTable(content, node)
            elif tname == "footnote":
                footnoteId = node.footnoteId
                fnAnchorNode = getFootnoteAnchorDict(self.basePageAst).get(
                        footnoteId)

                if fnAnchorNode is None:
                    self.outAppend(escapeHtml(node.getString()))
                else:
                    if self.wordAnchor:
                        fnAnchor = self.wordAnchor + u"#.f" + _escapeAnchor(
                                footnoteId)
                    else:
                        fnAnchor = u".f" + _escapeAnchor(footnoteId)

                    if fnAnchorNode.pos == node.pos:
                        # Current footnote token tok is an anchor (=last
                        # footnote token with this footnoteId)

                        self.outAppend(u'<a name="%s"></a>' % fnAnchor)
                        self.outAppend(escapeHtml(node.getString()))
                    else:
                        if not self.optsStack.get("suppressLinks", False):
                            # Current token is not an anchor -> make it a link.
                            self.outAppend(u'<a href="#%s">%s</a>' % (fnAnchor,
                            escapeHtml(node.getString())))
            elif tname == "urlLink":
                link = node.url
                if link.startswith(u"rel://"):
                    absUrl = self.mainControl.makeRelUrlAbsolute(link)

                    # Relative URL
                    if self.asHtmlPreview:
                        # If preview, make absolute
                        link = absUrl
                    else:
                        if self.referencedStorageFiles is not None:
                            # Get absolute path to the file
                            absLink = pathnameFromUrl(absUrl)
                            # and to the file storage
                            stPath = self.wikiDocument.getFileStorage().getStoragePath()
                            
                            isCont = testContainedInDir(stPath, absLink)
                            if isCont:
                                # File is in file storage -> add to
                                # referenced storage files                            
                                self.referencedStorageFiles.add(
                                        relativeFilePath(
                                        self.wikiDocument.getWikiPath(),
                                        absLink))

                        # If export, reformat a bit
                        link = link[6:]
                else:
                    absUrl = link

                lowerLink = link.lower()
                
                if node.appendixNode is None:
                    appendixDict = {}
                else:
                    appendixDict = dict(node.appendixNode.entries)

                # Decide if this is an image link
                if appendixDict.has_key("l"):
                    urlAsImage = False
                elif appendixDict.has_key("i"):
                    urlAsImage = True
                elif self.asHtmlPreview and \
                        self.mainControl.getConfig().getboolean(
                        "main", "html_preview_pics_as_links"):
                    urlAsImage = False
                elif not self.asHtmlPreview and self.addOpt[0]:
                    urlAsImage = False
                elif lowerLink.endswith(".jpg") or \
                        lowerLink.endswith(".gif") or \
                        lowerLink.endswith(".png") or \
                        lowerLink.endswith(".tif") or \
                        lowerLink.endswith(".bmp"):
                    urlAsImage = True
                else:
                    urlAsImage = False

                if urlAsImage:
                    # Ignore title, use image
                    sizeInTag = u""

                    # Size info for direct setting in HTML code
                    sizeInfo = appendixDict.get("s")
                    # Relative size info which modifies real image size
                    relSizeInfo = appendixDict.get("r")

                    if sizeInfo is not None:
                        try:
                            widthStr, heightStr = sizeInfo.split(u"x")
                            if self.isHtmlSizeValue(widthStr) and \
                                    self.isHtmlSizeValue(heightStr):
                                sizeInTag = ' width="%s" height="%s"' % \
                                        (widthStr, heightStr)
                        except:
                            # something does not meet syntax requirements
                            pass
                    
                    elif relSizeInfo is not None:
                        params = relSizeInfo.split(u"x")
                        if len(params) == 1:
                            if params[0] == u"":
                                widthStr, heightStr = "100%", "100%"
                            else:
                                widthStr, heightStr = params[0], params[0]
                        else:
                            widthStr, heightStr = params[0], params[1]

                        width = SizeValue(widthStr)
                        height = SizeValue(heightStr)

                        if width.isValid() and height.isValid() and \
                                (width.getUnit() == height.getUnit()):
                            imgWidth, imgHeight = self._getImageDims(absUrl)
                            if imgWidth is not None:
                                # TODO !!!
                                if width.getUnit() == width.UNIT_FACTOR:
                                    imgWidth = int(imgWidth * width.getValue())
                                    imgHeight = int(imgHeight * height.getValue())

                                sizeInTag = ' width="%s" height="%s"' % \
                                        (imgWidth, imgHeight)

                    alignInTag = u""
                    alignInfo = appendixDict.get("a")
                    if alignInfo is not None:
                        try:
                            if alignInfo == u"t":
                                alignInTag = u' align="top"'
                            elif alignInfo == u"m":
                                alignInTag = u' align="middle"'
                            elif alignInfo == u"b":
                                alignInTag = u' align="bottom"'
                            elif alignInfo == u"l":
                                alignInTag = u' align="left"'
                            elif alignInfo == u"r":
                                alignInTag = u' align="right"'
                        except:
                            # something does not match syntax requirements
                            pass

                    if self.asIntHtmlPreview and lowerLink.startswith("file:"):
                        # At least under Windows, wxWidgets has another
                        # opinion how a local file URL should look like
                        # than Python
                        p = pathnameFromUrl(link)
                        link = wx.FileSystem.FileNameToURL(p)
                    self.outAppend(u'<img src="%s" alt="" border="0"%s%s />' % 
                            (link, sizeInTag, alignInTag))
                else:
                    if not self.optsStack.get("suppressLinks", False):
                        # If we would be in a title, only image urls are allowed
                        self.outAppend(u'<span class="url-link"><a href="%s">' % link)
                        if node.titleNode is not None:
                            with self.optsStack:
                                self.optsStack["suppressLinks"] = True
                                self.processAst(content, node.titleNode)
                        else:
                            self.outAppend(escapeHtml(link))                        
                        self.outAppend(u'</a></span>')
            elif tname == "stringEnd":
                pass
            else:
                self.outAppend(u'<tt>' + escapeHtmlNoBreaks(
                        _(u'[Unknown parser node with name "%s" found]') % tname) + \
                        u'</tt>')

        self.astNodeStack.pop()


class TextExporter(AbstractExporter):
    """
    Exports raw text
    """
    def __init__(self, mainControl):
        AbstractExporter.__init__(self, mainControl)
        self.wordList = None
        self.exportDest = None
        self.convertFilename = removeBracketsFilename # lambda s: s   

    def getExportTypes(self, guiparent, continuousExport=False):
        """
        Return sequence of tuples with the description of export types provided
        by this object. A tuple has the form (<exp. type>,
            <human readable description>, <panel for add. options or None>)
        If panels for additional options must be created, they should use
        guiparent as parent
        """
        if continuousExport:
            # Continuous export not supported
            return ()
        if guiparent:
            res = wx.xrc.XmlResource.Get()
            textPanel = res.LoadPanel(guiparent, "ExportSubText") # .ctrls.additOptions
        else:
            textPanel = None

        return (
            (u"raw_files", _(u'Set of *.wiki files'), textPanel),
            )


#     def getExportDestinationType(self, exportType):
#         """
#         Return one of the EXPORT_DEST_TYPE_* constants describing
#         if exportType exorts to a file or directory
#         """
#         TYPEMAP = {
#                 u"raw_files": EXPORT_DEST_TYPE_DIR
#                 }
#                 
#         return TYPEMAP[exportType]


    def getExportDestinationWildcards(self, exportType):
        """
        If an export type is intended to go to a file, this function
        returns a (possibly empty) sequence of tuples
        (wildcard description, wildcard filepattern).
        
        If an export type goes to a directory, None is returned
        """
        return None


    def getAddOptVersion(self):
        """
        Returns the version of the additional options information returned
        by getAddOpt(). If the return value is -1, the version info can't
        be stored between application sessions.
        
        Otherwise, the addopt information can be stored between sessions
        and can later handled back to the export method of the object
        without previously showing the export dialog.
        """
        return 0


    def getAddOpt(self, addoptpanel):
        """
        Reads additional options from panel addoptpanel.
        If getAddOptVersion() > -1, the return value must be a sequence
        of simple string and/or numeric objects. Otherwise, any object
        can be returned (normally the addoptpanel itself)
        """
        if addoptpanel is None:
            return (1,)
        else:
            ctrls = XrcControls(addoptpanel)
            
            # Which encoding:
            # 0:System standard, 1:utf-8 with BOM, 2: utf-8 without BOM
    
            return (ctrls.chTextEncoding.GetSelection(),)


    def setAddOpt(self, addOpt, addoptpanel):
        """
        Shows content of addOpt in the addoptpanel (must not be None).
        This function is only called if getAddOptVersion() != -1.
        """
        ctrls = XrcControls(addoptpanel)
        ctrls.chTextEncoding.SetSelection(addOpt[0])


    def export(self, wikiDocument, wordList, exportType, exportDest,
            compatFilenames, addopt, progressHandler):
        """
        Run export operation.
        
        wikiDocument -- WikiDocument object
        wordList -- Sequence of wiki words to export
        exportType -- string tag to identify how to export
        exportDest -- Path to destination directory or file to export to
        compatFilenames -- Should the filenames be encoded to be lowest
                           level compatible
        addopt -- additional options returned by getAddOpt()
        """
        self.wikiDocument = wikiDocument
        self.wordList = wordList
        self.exportDest = exportDest
       
        if compatFilenames:
            self.convertFilename = removeBracketsToCompFilename
        else:
            self.convertFilename = removeBracketsFilename # lambda s: s
         
        # 0:System standard, 1:utf-8 with BOM, 2: utf-8 without BOM
        encoding = addopt[0]
                
        if encoding == 0:
            enc = mbcsEnc
        else:
            enc = utf8Enc
            
        if encoding == 1:
            filehead = BOM_UTF8
        else:
            filehead = ""

        for word in self.wordList:
            try:
                wikiPage = self.wikiDocument.getWikiPage(word)
                content = wikiPage.getLiveText()
                modified = wikiPage.getTimestamps()[0]
#                 content = self.wikiDocument.getWikiData().getContent(word)
#                 modified = self.wikiDocument.getWikiData().getTimestamps(word)[0]
            except:
                traceback.print_exc()
                continue

            # TODO Use self.convertFilename here???
            outputFile = join(self.exportDest,
                    self.convertFilename(u"%s.wiki" % word))

            try:
#                 if exists(outputFile):
#                     os.unlink(outputFile)
    
                fp = open(pathEnc(outputFile), "wb")
                fp.write(filehead)
                fp.write(enc(content, "replace")[0])
                fp.close()
                
                try:
                    os.utime(outputFile, (long(modified), long(modified)))
                except:
                    pass
            except:
                traceback.print_exc()
                continue


class MultiPageTextAddOptPanel(wx.Panel):
    def __init__(self, parent):
        p = wx.PrePanel()
        self.PostCreate(p)

        res = wx.xrc.XmlResource.Get()
        res.LoadOnPanel(self, parent, "ExportSubMultipageText")
        
        self.ctrls = XrcControls(self)
        
        wx.EVT_CHOICE(self, GUI_ID.chFileVersion, self.OnFileVersionChoice)


    def OnFileVersionChoice(self, evt):
        enabled = evt.GetSelection() > 0
        
        self.ctrls.cbWriteWikiFuncPages.Enable(enabled)
        self.ctrls.cbWriteSavedSearches.Enable(enabled)



class MultiPageTextExporter(AbstractExporter):
    """
    Exports in multipage text format
    """
    def __init__(self, mainControl):
        AbstractExporter.__init__(self, mainControl)
        self.wordList = None
        self.exportDest = None
        self.addOpt = None


    def getExportTypes(self, guiparent, continuousExport=False):
        """
        Return sequence of tuples with the description of export types provided
        by this object. A tuple has the form (<exp. type>,
            <human readable description>, <panel for add. options or None>)
        If panels for additional options must be created, they should use
        guiparent as parent
        """
        if continuousExport:
            # Continuous export not supported    TODO
            return ()
        if guiparent:
            optPanel = MultiPageTextAddOptPanel(guiparent)
        else:
            optPanel = None

        return (
            (u"multipage_text", _(u"Multipage text"), optPanel),
            )


    def getExportDestinationWildcards(self, exportType):
        """
        If an export type is intended to go to a file, this function
        returns a (possibly empty) sequence of tuples
        (wildcard description, wildcard filepattern).
        
        If an export type goes to a directory, None is returned
        """
        if exportType == u"multipage_text":
            return ((_(u"Multipage files (*.mpt)"), "*.mpt"),
                    (_(u"Text file (*.txt)"), "*.txt")) 

        return None


    def getAddOptVersion(self):
        """
        Returns the version of the additional options information returned
        by getAddOpt(). If the return value is -1, the version info can't
        be stored between application sessions.
        
        Otherwise, the addopt information can be stored between sessions
        and can later handled back to the export method of the object
        without previously showing the export dialog.
        """
        return 0


    def getAddOpt(self, addoptpanel):
        """
        Reads additional options from panel addoptpanel.
        If getAddOptVersion() > -1, the return value must be a sequence
        of simple (unicode) string and/or numeric objects. Otherwise, any object
        can be returned (normally the addoptpanel itself).
        
        The tuple elements mean: (<format version>,)
        """
        if addoptpanel is None:
            # Return default set in options
            fileVersion = 1
            writeWikiFuncPages = 1
            writeSavedSearches = 1            
        else:
            ctrls = addoptpanel.ctrls
            fileVersion = ctrls.chFileVersion.GetSelection()
            writeWikiFuncPages = boolToInt(ctrls.cbWriteWikiFuncPages.GetValue())
            writeSavedSearches = boolToInt(ctrls.cbWriteSavedSearches.GetValue())

        return (fileVersion, writeWikiFuncPages, writeSavedSearches)


    def setAddOpt(self, addOpt, addoptpanel):
        """
        Shows content of addOpt in the addoptpanel (must not be None).
        This function is only called if getAddOptVersion() != -1.
        """
        fileVersion, writeWikiFuncPages, writeSavedSearches = \
                addOpt

        ctrls = addoptpanel.ctrls   # XrcControls(addoptpanel)?

        ctrls.chFileVersion.SetSelection(fileVersion)
        ctrls.cbWriteWikiFuncPages.SetValue(writeWikiFuncPages != 0)
        ctrls.cbWriteSavedSearches.SetValue(writeSavedSearches != 0)



    # TODO Check also wiki func pages !!!
    def _checkPossibleSeparator(self, sep):
        """
        Run search operation to test if separator string sep
        (without trailing newline) is already in use.
        Returns True if sep doesn't appear as line in any page from
        self.wordList
        """
        searchOp = SearchReplaceOperation()
        searchOp.searchStr = u"^" + re.escape(sep) + u"$"
        searchOp.booleanOp = False
        searchOp.caseSensitive = True
        searchOp.wholeWord = False
        searchOp.cycleToStart = False
        searchOp.wildCard = 'regex'
        searchOp.wikiWide = True

        wpo = ListWikiPagesOperation()
        wpo.setSearchOpTree(ListItemWithSubtreeWikiPagesNode(wpo, self.wordList,
                level=0))

        searchOp.listWikiPagesOp = wpo

        foundPages = self.mainControl.getWikiDocument().searchWiki(searchOp)

        return len(foundPages) == 0


    def _findSeparator(self):
        """
        Find a separator (=something not used as line in a page to export)
        """
#         # Try dashes
#         sep = u"------"
#         
#         while len(sep) < 11:
#             if self._checkPossibleSeparator(sep):
#                 return sep
#             sep += u"-"
# 
#         # Try dots
#         sep = u"...."
#         while len(sep) < 11:
#             if self._checkPossibleSeparator(sep):
#                 return sep
#             sep += u"."
            
        # Try random strings (15 tries)
        for i in xrange(15):
            sep = u"-----%s-----" % createRandomString(25)
            if self._checkPossibleSeparator(sep):
                return sep

        # Give up
        return None            
        

    def export(self, wikiDocument, wordList, exportType, exportDest,
            compatFilenames, addOpt, progressHandler):
        """
        Run export operation.
        
        wikiDocument -- WikiDocument object
        wordList -- Sequence of wiki words to export
        exportType -- string tag to identify how to export
        exportDest -- Path to destination directory or file to export to
        compatFilenames -- Should the filenames be encoded to be lowest
                           level compatible
        addOpt -- additional options returned by getAddOpt()
        """
        self.wikiDocument = wikiDocument
        self.wordList = wordList
        self.exportDest = exportDest
        self.addOpt = addOpt
        self.exportFile = None
        self.rawExportFile = None
        
        self.formatVer = min(addOpt[0], 1)
        self.writeWikiFuncPages = addOpt[1] and (self.formatVer > 0)
        self.writeSavedSearches = addOpt[2] and (self.formatVer > 0)

        # The hairy thing first: find a separator that doesn't appear
        # as a line in one of the pages to export
        self.separator = self._findSeparator()
        if self.separator is None:
            # _findSeparator gave up
            raise ExportException(_(u"No usable separator found"))
        try:
            try:
                self.rawExportFile = open(pathEnc(self.exportDest), "w")
    
                # Only UTF-8 mode currently
                self.rawExportFile.write(BOM_UTF8)
                self.exportFile = utf8Writer(self.rawExportFile, "replace")
                
                # Identifier line with file format
                self.exportFile.write(u"Multipage text format %i\n" %
                        self.formatVer)
                # Separator line
                self.exportFile.write(u"Separator: %s\n" % self.separator)


                # Write wiki-bound functional pages
                if self.writeWikiFuncPages:
                    # Only wiki related functional pages
                    wikiFuncTags = [ft for ft in DocPages.getFuncTags()
                            if ft.startswith("wiki/")]
                    
                    for ft in wikiFuncTags:
                        self.exportFile.write(u"funcpage/%s\n" % ft)
                        page = self.wikiDocument.getFuncPage(ft)
                        self.exportFile.write(page.getLiveText())

                        self.exportFile.write("\n%s\n" % self.separator)


                # Write saved searches
                if self.writeSavedSearches:
                    wikiData = self.wikiDocument.getWikiData()
#                     searchTitles = wikiData.getSavedSearchTitles()
                    unifNames = wikiData.getDataBlockUnifNamesStartingWith(
                            u"savedsearch/")

                    for un in unifNames:
#                         self.exportFile.write(u"savedsearch/%s\n" % st)
#                         datablock = wikiData.getSearchDatablock(st)
                        self.exportFile.write(un + u"\n")
                        datablock = wikiData.retrieveDataBlock(un)

                        self.exportFile.write(base64BlockEncode(datablock))

                        self.exportFile.write("\n%s\n" % self.separator)

                locale.setlocale(locale.LC_ALL, '')
                # Write actual wiki words
                sepCount = len(self.wordList) - 1  # Number of separators yet to write
                for word in self.wordList:
                    page = self.wikiDocument.getWikiPage(word)

                    if self.formatVer == 0:
                        self.exportFile.write(u"%s\n" % word)
                    else:
                        self.exportFile.write(u"wikipage/%s\n" % word)
                        # modDate, creaDate, visitDate
                        timeStamps = page.getTimestamps()[:3]
                        
                        # Do not use StringOps.strftimeUB here as its output
                        # relates to local time, but we need UTC here.
                        timeStrings = [unicode(time.strftime(
                                "%Y-%m-%d/%H:%M:%S", time.gmtime(ts)))
                                for ts in timeStamps]

                        self.exportFile.write(u"%s  %s  %s\n" % tuple(timeStrings))

                    self.exportFile.write(page.getLiveText())

                    if sepCount > 0:
                        self.exportFile.write("\n%s\n" % self.separator)
                        sepCount -= 1

            except Exception, e:
                traceback.print_exc()
                raise ExportException(unicode(e))
        finally:
            if self.exportFile is not None:
                self.exportFile.flush()

            if self.rawExportFile is not None:
                self.rawExportFile.close()



def describeExporters(mainControl):
    return (HtmlExporter(mainControl), TextExporter(mainControl),
            MultiPageTextExporter(mainControl))
    

