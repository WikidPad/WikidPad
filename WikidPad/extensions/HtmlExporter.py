
## import profilehooks
## profile = profilehooks.profile(filename="profile.prf", immediate=False)

import sys, os, os.path, re, traceback, locale, time, urllib.request, urllib.parse, urllib.error
from os.path import join, exists
from io import StringIO, BytesIO
import shutil

import pwiki.urllib_red as urllib

import wx
from pwiki.rtlibRepl import minidom

from pwiki.wxHelper import XrcControls, GUI_ID, wxKeyFunctionSink

import Consts
from pwiki.WikiExceptions import WikiWordNotFoundException, ExportException, \
        InternalError
from pwiki.ParseUtilities import getFootnoteAnchorDict
from pwiki.Utilities import calcResizeArIntoBoundingBox, seqSupportWithTemplate
from pwiki.StringOps import *
from pwiki import StringOps, Serialization
from pwiki.WikiPyparsing import StackedCopyDict, SyntaxNode, buildSyntaxNode
from pwiki.TempFileSet import TempFileSet

from pwiki.SearchAndReplace import SearchReplaceOperation, ListWikiPagesOperation, \
        ListItemWithSubtreeWikiPagesNode

from pwiki import SystemInfo, PluginManager, OsAbstract, DocPages


from pwiki.Exporters import AbstractExporter



WIKIDPAD_PLUGIN = (("Exporters", 1),)


def describeExportersV01(mainControl):
    """
    Return sequence of exporter classes.
    """
    return (HtmlExporter,)





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
    return "".join(result)

# # Types of export destinations
# EXPORT_DEST_TYPE_DIR = 1
# EXPORT_DEST_TYPE_FILE = 2


class BasicLinkConverter:
    def __init__(self, wikiDocument, htmlExporter):
        self.htmlExporter = htmlExporter
        self.wikiDocument = wikiDocument
        
    def getLinkForWikiWord(self, word, default = None):
        return default


class LinkConverterForHtmlSingleFilesExport(BasicLinkConverter):
    def getLinkForWikiWord(self, word, default = None):
        relUnAlias = self.wikiDocument.getWikiPageNameForLinkTerm(word)
        if relUnAlias is None:
            return default
        if not self.htmlExporter.shouldExport(word):
            return default

        return urlFromPathname(
                self.htmlExporter.filenameConverter.getFilenameForWikiWord(
                relUnAlias) + ".html")

class LinkConverterForHtmlMultiPageExport(BasicLinkConverter):
    def getLinkForWikiWord(self, word, default = None):
        relUnAlias = self.wikiDocument.getWikiPageNameForLinkTerm(word)
        if relUnAlias is None:
            return default
        if not self.htmlExporter.shouldExport(word):
            return default

        if relUnAlias not in self.htmlExporter.wordList:
            return default

        return "#%s" % _escapeAnchor(relUnAlias)


class FilenameConverter:
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
            for fname in iterCompatibleFilename(ww, "",
                    asciiOnly=self.asciiOnly, maxLength=245):
                if not fname in self._valueSet:
                    self._used[ww] = fname
                    self._valueSet.add(fname)
                    return fname



class SizeValue:
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

    def __repr__(self):
        return "<SizeValue value={0} type={1}>".format(self.value, self.unit)


HOR_ALIGN_CSS_ATTR = {
    "l" : ('text-align: left',   'align="left"'),
    "c" : ('text-align: center', 'align="center"'),
#     u"m" : (u'text-align: center', u'align="center"'),
    "r" : ('text-align: right',  'align="right"'),
    "left" : ('text-align: left',   'align="left"'),
    "center" : ('text-align: center', 'align="center"'),
    "right" : ('text-align: right',  'align="right"'),
    }

VERT_ALIGN_CSS_ATTR = {
    "t" : ('vertical-align: top',   'valign="top"'),
    "m" : ('vertical-align: middle', 'valign="middle"'),
    "b" : ('vertical-align: bottom',  'valign="bottom"'),
    "top" : ('vertical-align: top',   'valign="top"'),
    "middle" : ('vertical-align: middle', 'valign="middle"'),
    "bottom" : ('vertical-align: bottom',  'valign="bottom"'),
    }
 
IMG_ALIGN_ATTR = {
    "t": ' align="top"',
    "m": ' align="middle"',
    "b": ' align="bottom"',
    "l": ' align="left"',
    "r": ' align="right"',
    "top": ' align="top"',
    "middle": ' align="middle"',
    "bottom": ' align="bottom"',
    "left": ' align="left"',
    "right": ' align="right"',
    }



class TableCell:
    MODE_VALID = 0
    MODE_CONTINUATION = 1
    
    __slots__ = ("exporter", "grid", "astNode", "posRow", "posCol", "mode",
            "infoRow", "infoCol", "content")
    
    def __init__(self, exporter, grid, posRow, posCol, astNode, content):
        self.exporter = exporter
        self.grid = grid
        self.posRow = posRow
        self.posCol = posCol
        self.astNode = astNode
        self.content = content
        self.mode = self.MODE_VALID
        
        # meanning of  self.info*  depends on mode. For valid cells it is
        # the rowspan/colspan, for continuation cells it is the position
        # of the valid cell which is continued
        self.infoRow = 1
        self.infoCol = 1
        
        if self.astNode.findFlatByName("tableCellContinuationUp"):
            self.astNode = None
            if self.posRow > 0:
                # In first row (self.posRow == 0) there wouldn't be a cell above
                self.mode = self.MODE_CONTINUATION
                
                self.infoRow, self.infoCol = self.findCreateValidCellCoords(
                        self.posRow - 1, self.posCol)
                
                self.getCellByCoords(self.infoRow, self.infoCol).extendSpanTo(
                        self.posRow, self.posCol)
        elif self.astNode.findFlatByName("tableCellContinuationLeft"):
            self.astNode = None
            if self.posCol > 0:
                # In first column there wouldn't be a cell to the left
                self.mode = self.MODE_CONTINUATION
                
                self.infoRow, self.infoCol = self.findCreateValidCellCoords(
                        self.posRow, self.posCol - 1)
                        
                self.getCellByCoords(self.infoRow, self.infoCol).extendSpanTo(
                        self.posRow, self.posCol)



    def processAst(self):
        if self.mode == self.MODE_CONTINUATION:
            return  # Don't do anything

        exporter = self.exporter

        if self.astNode is None:
            exporter.outAppend('<td class="wikidpad">')
            exporter.outAppend("</td>")
            return


        tableCellAppendix = self.astNode.findFlatByName("tableCellAppendix")

        css, styles, attribs = exporter.getCommonStylesFromAppendix(
                tableCellAppendix)
                
        if self.infoRow > 1:
            attribs.append('rowspan="{0}"'.format(self.infoRow))
        if self.infoCol > 1:
            attribs.append('colspan="{0}"'.format(self.infoCol))

#         if tableCellAppendix:
#             styleAttr = HOR_ALIGN_CSS_ATTR.get(getattr(tableCellAppendix,
#                     "text_align", None))
#             if styleAttr is not None:
#                 styles.append(styleAttr[0])
#                 attribs.append(styleAttr[1])

        if tableCellAppendix:
            for key, data in tableCellAppendix.entries:
                if key == "a" or key == "A" or key == "align":
                    styleAttr = VERT_ALIGN_CSS_ATTR.get(data)
                    if styleAttr is not None:
                        styles.append(styleAttr[0])
                        attribs.append(styleAttr[1])

        attrStr = exporter.combineStyles(css, styles, attribs)

        exporter.outAppend("<td{0}>".format(attrStr))
        exporter.processAst(self.content, self.astNode)
        exporter.outAppend("</td>")
    


    def findCreateCell(self, row, col):
        gridRow = self.grid[row]
        while len(gridRow) < (col + 1):
            gridRow.append(TableCell(self.exporter, self.grid, row,
                    len(gridRow), None, self.content))
        
        return gridRow[col]


    def findCreateValidCellCoords(self, row, col):
        while True:
            gridRow = self.grid[row]
            while len(gridRow) < (col + 1):
                gridRow.append(TableCell(self.exporter, self.grid, row,
                        len(gridRow), None, self.content))
            
            cell = gridRow[col]
            if cell.mode == self.MODE_CONTINUATION:
                row = cell.infoRow
                col = cell.infoCol
                continue

            return row, col

    def getCellByCoords(self, row, col):
        return self.grid[row][col]


    def extendSpanTo(self, row, col):
        assert self.mode == self.MODE_VALID, "Trying to extend continuation cell"
        self.infoRow = max(self.infoRow, row - self.posRow + 1)
        self.infoCol = max(self.infoCol, col - self.posCol + 1)
        

    def killExtend(self):
        if self.mode == self.MODE_CONTINUATION:
            return
        
        for row in range(self.posRow, self.posRow + self.infoRow):
            for col in range(self.posCol, self.posCol + self.infoCol):
                try:
                    cell = self.getCellByCoords(row, col)
                except IndexError:
                    continue
                
                if cell.mode == self.MODE_CONTINUATION:
                    cell.mode = self.MODE_VALID
                    cell.astNode = None
                    cell.infoRow = 1
                    cell.infoCol = 1

        self.infoRow = 1
        self.infoCol = 1


    def cleanup(self):
        """
        Called on each cell before pageAst() is called on them
        """
        if self.mode == self.MODE_CONTINUATION:
            return
            
        if self.infoRow > 1 or self.infoCol > 1:
            for row in range(self.posRow, self.posRow + self.infoRow):
                for col in range(self.posCol, self.posCol + self.infoCol):
                    if row == self.posRow and col == self.posCol:
                        # Don't treat this cell
                        continue
    
                    cell = self.findCreateCell(row, col)
                    if cell.mode == self.MODE_VALID:
                        # We have found a valid cell which is spanned over by
                        # this cell. Can happen for a table like
                        #    T | <
                        #    ^ | V
                        #
                        # where T is this cell and V is the valid cell
    
                        if cell.infoRow > 1 or cell.infoCol > 1:
                            # Valid cell itself spans multiple cells, e.g.
                            #    T | < | X
                            #    ^ | V | <
                            #    X | ^ | X
                            # 
                            # This doesn't work
    
                            cell.killExtend()
                        
                        cell.mode = self.MODE_CONTINUATION
                        cell.astNode = None
                        cell.infoRow = self.posRow
                        cell.infoCol = self.posCol





# TODO UTF-8 support for HTML? Other encodings?

class HtmlExporter(AbstractExporter):
    
    ADDOPT_IDX_PICS_AS_LINKS = 0
    ADDOPT_IDX_TABLE_OF_CONTENTS = 1
    ADDOPT_IDX_TOC_TITLE = 2
    ADDOPT_IDX_VOLATILE_DIRECTORY = 3
    ADDOPT_IDX_LIST_PARENTS = 4


    def __init__(self, mainControl):
        """
        mainControl -- PersonalWikiFrame object. Part of "Exporters" plugin API
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
        self.avoidDeadWikiLinks = True  # avoid links to not exported wikiwords
        self.listPagesOperation = None

        self.wordAnchor = None  # For multiple wiki pages in one HTML page, this contains the anchor
                # of the current word.
        self.tempFileSet = None
        self.copiedTempFileCache = None  # Dictionary {<original path>: <target URL>}
        self.filenameConverter = FilenameConverter(False)
#         self.convertFilename = removeBracketsFilename

        self.result = None
        
        # Flag to control how to push output into self.result
        self.outFlagEatPostBreak = False
        self.outFlagPostBreakEaten = False
        
        self.__sinkWikiDocument = None

    def setWikiDocument(self, wikiDocument):
        self.wikiDocument = wikiDocument
        if self.wikiDocument is not None:
            self.buildStyleSheetList()

    @staticmethod
    def getExportTypes(mainControl, continuousExport=False):
        """
        Part of "Exporters" plugin API.
        Return sequence of tuples with the description of export types provided
        by this object. A tuple has the form (<exp. type>,
            <human readable description>)
        All exporters must provide this as a static method (which can be called
        without constructing an object first.

        mainControl -- PersonalWikiFrame object
        continuousExport -- If True, only types with support for continuous export
        are listed.
        """
        return (
            ("html_multi", _('One HTML page')),
            ("html_single", _('Set of HTML pages'))
            )


    def getAddOptPanelsForTypes(self, guiparent, exportTypes):
        """
        Part of "Exporters" plugin API.
        Construct all necessary GUI panels for additional options
        for the types contained in exportTypes.
        Returns sequence of tuples (<exp. type>, <panel for add. options or None>)

        The panels should use  guiparent  as parent.
        If the same panel is used for multiple export types the function can
        and should include all export types for this panel even if some of
        them weren't requested. Panel objects must not be shared by different
        exporter classes.
        """
        if not "html_multi" in exportTypes and \
                not "html_single" in exportTypes:
            return ()

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

        return (
            ("html_multi", htmlPanel),
            ("html_single", htmlPanel)
            )


    def getExportDestinationWildcards(self, exportType):
        """
        Part of "Exporters" plugin API.
        If an export type is intended to go to a file, this function
        returns a (possibly empty) sequence of tuples
        (wildcard description, wildcard filepattern).
        
        If an export type goes to a directory, None is returned
        """
        return None


    def getAddOptVersion(self):
        """
        Part of "Exporters" plugin API.
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
        Part of "Exporters" plugin API.
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
                    "volatile",
                    boolToInt(True),
                    )
        else:
            ctrls = XrcControls(addoptpanel)

            picsAsLinks = boolToInt(ctrls.cbPicsAsLinks.GetValue())
            tableOfContents = ctrls.chTableOfContents.GetSelection()
            tocTitle = ctrls.tfHtmlTocTitle.GetValue()
            listParents = boolToInt(ctrls.cbListParents.GetValue())
            
            return (picsAsLinks, tableOfContents, tocTitle, "volatile",
                    listParents,)


    def setAddOpt(self, addOpt, addoptpanel):
        """
        Part of "Exporters" plugin API.
        Shows content of addOpt in the addoptpanel (must not be None).
        This function is only called if getAddOptVersion() != -1.
        """
        picsAsLinks, tableOfContents, tocTitle, volatileDir, listParents = \
                seqSupportWithTemplate(addOpt, self.getAddOpt(None))
                
        # volatileDir is currently ignored

        ctrls = XrcControls(addoptpanel)

        ctrls.cbPicsAsLinks.SetValue(picsAsLinks != 0)
        ctrls.chTableOfContents.SetSelection(tableOfContents)
        ctrls.tfHtmlTocTitle.SetValue(tocTitle)
        ctrls.cbListParents.SetValue(listParents != 0)
        

    def setJobData(self, wikiDocument, wordList, exportType, exportDest,
            compatFilenames, addOpt, progressHandler):
        """
        Set all information necessary to run export operation.
        """

        self.setWikiDocument(wikiDocument)

        if self.avoidDeadWikiLinks:
            self.wordList = [w for w in wordList
                    if self.shouldExport(
                    self.wikiDocument.getWikiPageNameForLinkTerm(w))]
        else:
            self.wordList = [w for w in wordList
                    if self.wikiDocument.isDefinedWikiLinkTerm(w)]

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
#             self.convertFilename = removeBracketsFilename

        self.referencedStorageFiles = None
        
        return True


    def export(self, wikiDocument, wordList, exportType, exportDest,
            compatFilenames, addOpt, progressHandler, tempFileSetReset=True):
        """
        Part of "Exporters" plugin API.
        Run export operation. This is only called for real exports,
        previews use other functions.
        
        wikiDocument -- wikiDocument object
        wordList -- Sequence of wiki words to export
        exportType -- string tag to identify how to export
        exportDest -- Path to destination directory or file to export to
        compatFilenames -- Should the filenames be encoded to be lowest
                           level compatible (ascii only)?
        addOpt -- additional options as returned by getAddOpt()
        """
        if not self.setJobData(wikiDocument, wordList, exportType, exportDest,
                compatFilenames, addOpt, progressHandler):
            return
            
        if exportType in ("html_single", "html_multi"):
            volatileDir = self.addOpt[self.ADDOPT_IDX_VOLATILE_DIRECTORY]

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


        if exportType == "html_multi":
            browserFile = self.exportHtmlMultiFile()
        elif exportType == "html_single":
            browserFile = self._exportHtmlSingleFiles(self.wordList)

        # Other supported types: html_previewWX, html_previewIE, html_previewMOZ,
        #   html_previewWK
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
                    except IOError as e:
                        raise ExportException(str(e))


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
        
        # for continuous export we want to have dead links to simplify updates
        self.avoidDeadWikiLinks = False

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
        self.avoidDeadWikiLinks = True
        self.__sinkWikiDocument.disconnect()

        self.tempFileSet.reset()
        self.tempFileSet = None
        self.copiedTempFileCache = None


    def onDeletedWikiPage(self, miscEvt):
        wikiWord = miscEvt.get("wikiPage").getWikiWord()

        if wikiWord not in self.wordList:
            return
            
        self.wordList.remove(wikiWord)
        
        if self.exportType == "html_multi":
            self.exportHtmlMultiFile()

        elif self.exportType == "html_single":
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


        if self.exportType == "html_multi":
            self.exportHtmlMultiFile()

        elif self.exportType == "html_single":
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
            if self.exportType == "html_multi":
                self.exportHtmlMultiFile()
    
            elif self.exportType == "html_single":
                self._exportHtmlSingleFiles(updList)
        except WikiWordNotFoundException:
            pass



    def getTempFileSet(self):
        return self.tempFileSet


    _INTERNALJUMP_PREFIXMAP = {
        "html_previewWX": "internaljump:",
        "html_previewIE": "http://internaljump/",
        "html_previewMOZ": "file://internaljump/",
        "html_previewWK": "http://internaljump/"
    }

    def _getInternaljumpPrefix(self):
        try:
            return self._INTERNALJUMP_PREFIXMAP[self.exportType]
        except IndexError:
            raise InternalError(
                    "Trying to get internal jump prefix for non-preview export")


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

            realfp = open(pathEnc(outputFile), "w", encoding="utf-8",
                    errors="surrogateescape")
        else:
            outputFile = None

        #filePointer = utf8Writer(realfp, "replace")
        filePointer = realfp

        filePointer.write(self.getFileHeaderMultiPage(self.mainControl.wikiName))

        tocTitle = self.addOpt[self.ADDOPT_IDX_TOC_TITLE]
        
        if tocMode is None:
            tocMode = self.addOpt[self.ADDOPT_IDX_TABLE_OF_CONTENTS]

        if tocMode == 1:
            # Write a content tree at beginning
            rootPage = self.mainControl.getWikiDocument().getWikiPage(
                        self.mainControl.getWikiDocument().getWikiName())
            flatTree = rootPage.getFlatTree()

            filePointer.write(('<h2 class="wikidpad">%s</h2>\n'
                    '%s%s<hr class="wikidpad" />') %
                    (tocTitle, # = "Table of Contents"
                    self.getContentTreeBody(flatTree, linkAsFragments=True),
                    '<br class="wikidpad" />\n' * sepLineCount))

        elif tocMode == 2:
            # Write a content list at beginning
            filePointer.write(('<h2 class="wikidpad">%s</h2>\n'
                    '%s%s<hr class="wikidpad" />') %
                    (tocTitle, # = "Table of Contents"
                    self.getContentListBody(linkAsFragments=True),
                    '<br class="wikidpad" />\n' * sepLineCount))


        if self.progressHandler is not None:
            self.progressHandler.open(len(self.wordList))
            step = 0

        # Then create the big page word by word
        for word in self.wordList:
            if self.progressHandler is not None:
                step += 1
                self.progressHandler.update(step, _("Exporting %s") % word)

            wikiPage = self.wikiDocument.getWikiPage(word)
            if not self.shouldExport(word, wikiPage):
                continue
                
            try:
                content = wikiPage.getLiveText()
#                 formatDetails = wikiPage.getFormatDetails()
                    
                self.wordAnchor = _escapeAnchor(word)
                formattedContent = self.formatContent(wikiPage)
                
                if self.addOpt[self.ADDOPT_IDX_LIST_PARENTS] != 0:
                    if self.avoidDeadWikiLinks:
                        parentLinks = self.getParentLinks(wikiPage, False,
                                self.wordList)
                    else:
                        parentLinks = self.getParentLinks(wikiPage, False)
                    
                    parentLinks = ('<span class="wikidpad parent-nodes">parent nodes: {0}'
                            '<br class="wikidpad" /><br class="wikidpad" /></span>')\
                            .format(parentLinks)
                    
                else:
                    parentLinks = u""
                    

                filePointer.write(('<span class="wikidpad wiki-name-ref">'
                        '[<a name="{0}" class="wikidpad">{1}</a>]<br class="wikidpad" />'
                        '<br class="wikidpad" /></span>'
                        '{2}{3}{4}<hr class="wikidpad" />')\
                        .format(self.wordAnchor, word, parentLinks,
                        formattedContent,
                        '<br class="wikidpad" />\n' * sepLineCount))
            except Exception as e:
                traceback.print_exc()

        self.wordAnchor = None

        filePointer.write(self.getFileFooter())
        
        #filePointer.reset()

        if outputFile is not None:
            realfp.close()

        self.copyCssFiles(self.exportDest)
        return outputFile


    def _exportHtmlSingleFiles(self, wordListToUpdate):
        self.setLinkConverter(LinkConverterForHtmlSingleFilesExport(
                self.wikiDocument, self))
        self.buildStyleSheetList()


        if self.addOpt[self.ADDOPT_IDX_TABLE_OF_CONTENTS] in (1, 2):
            # TODO Configurable name
            outputFile = join(self.exportDest, pathEnc("index.html"))
            try:
                if exists(pathEnc(outputFile)):
                    os.unlink(pathEnc(outputFile))
    
                realfp = open(pathEnc(outputFile), "w", encoding="utf-8",
                        errors="surrogateescape")
                #fp = utf8Writer(realfp, "replace")
                fp = realfp

                # TODO Factor out HTML header generation                
                fp.write(self._getGenericHtmlHeader(
                        self.addOpt[self.ADDOPT_IDX_TOC_TITLE]) + 
                        '    <body class="wikidpad">\n')
                if self.addOpt[self.ADDOPT_IDX_TABLE_OF_CONTENTS] == 1:
                    # Write a content tree
                    rootPage = self.mainControl.getWikiDocument().getWikiPage(
                                self.mainControl.getWikiDocument().getWikiName())
                    flatTree = rootPage.getFlatTree()
    
                    fp.write(('<h2 class="wikidpad">%s</h2>\n'
                            '%s') %
                            (self.addOpt[self.ADDOPT_IDX_TOC_TITLE],  # = "Table of Contents"
                            self.getContentTreeBody(flatTree, linkAsFragments=False)
                            ))
                elif self.addOpt[self.ADDOPT_IDX_TABLE_OF_CONTENTS] == 2:
                    # Write a content list
                    fp.write(('<h2 class="wikidpad">%s</h2>\n'
                            '%s') %
                            (self.addOpt[self.ADDOPT_IDX_TOC_TITLE],  # = "Table of Contents"
                            self.getContentListBody(linkAsFragments=False)
                            ))

                fp.write(self.getFileFooter())

                #fp.reset()        
                realfp.close()
            except Exception as e:
                traceback.print_exc()


        if self.progressHandler is not None:
            self.progressHandler.open(len(self.wordList))
            step = 0

        for word in wordListToUpdate:
            if self.progressHandler is not None:
                step += 1
                self.progressHandler.update(step, _("Exporting %s") % word)

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

            realfp = open(pathEnc(outputFile), "w", encoding="utf-8",
                    errors="surrogateescape")
            #fp = utf8Writer(realfp, "replace")
            fp = realfp
            
            wikiPage = self.wikiDocument.getWikiPage(word)
            fp.write(self.exportWikiPageToHtmlString(wikiPage,
                    startFile, onlyInclude))
            #fp.reset()        
            realfp.close()
        except Exception as e:
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

        result.append(self.getFileHeader(wikiPage))

        # if startFile is set then this is the only page being exported so
        # do not include the parent header.
        if not startFile and self.addOpt[self.ADDOPT_IDX_LIST_PARENTS] != 0:
            result.append(('<span class="wikidpad parent-nodes">parent nodes: %s'
                    '<br class="wikidpad" /><br class="wikidpad" /></span>\n')
                    % self.getParentLinks(wikiPage, True, onlyInclude))

        result.append(formattedContent)
        result.append(self.getFileFooter())
        
        return "".join(result)


    def _getGenericHtmlHeader(self, title, charSet='; charset=UTF-8'):
        styleSheets = []
        for dummy, url in self.styleSheetList:
            styleSheets.append(
                    '        <link type="text/css" rel="stylesheet" href="%(url)s">' %
                    locals())
        

#         styleSheet = self.styleSheet
        config = self.mainControl.getConfig()
        docType = config.get("main", "html_header_doctype",
                'DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.0 Transitional//EN"')

        # TODO: load javascript from plugins
        javascriptHeader = ""

        if self.exportType == "html_previewWK":
            javascriptHeader = '\n<script type="text/javascript" src="{0}"></script>'.format(os.path.join(self.mainControl.wikiAppDir, "lib", "js", "jquery", "jquery-2.0.2.min.js"))

        styleSheets = "\n".join(styleSheets)

        return """<!%(docType)s>
<html>
    <head>
        <meta http-equiv="content-type" content="text/html%(charSet)s">
        <title>%(title)s</title>
%(styleSheets)s
%(javascriptHeader)s
    </head>
""" % locals()



    def getFileHeaderMultiPage(self, title):
        """
        Return file header for an HTML file containing multiple pages
        """
        return self._getGenericHtmlHeader(title) + '    <body class="wikidpad">\n'


    def _getBodyTag(self, wikiPage):
        # Get application defaults from config
        config = self.mainControl.getConfig()
        linkcol = config.get("main", "html_body_link")
        alinkcol = config.get("main", "html_body_alink")
        vlinkcol = config.get("main", "html_body_vlink")
        textcol = config.get("main", "html_body_text")
        bgcol = config.get("main", "html_body_bgcolor")
        bgimg = config.get("main", "html_body_background")

        # Get attribute settings
        linkcol = wikiPage.getAttributeOrGlobal("html.linkcolor", linkcol)
        alinkcol = wikiPage.getAttributeOrGlobal("html.alinkcolor", alinkcol)
        vlinkcol = wikiPage.getAttributeOrGlobal("html.vlinkcolor", vlinkcol)
        textcol = wikiPage.getAttributeOrGlobal("html.textcolor", textcol)
        bgcol = wikiPage.getAttributeOrGlobal("html.bgcolor", bgcol)
        bgimg = wikiPage.getAttributeOrGlobal("html.bgimage", bgimg)
        
        # Filter color
        def filterCol(col, prop):
            if colorDescToRgbTuple(col) is not None:
                return '%s="%s"' % (prop, col)
            else:
                return ''
        
        linkcol = filterCol(linkcol, "link")
        alinkcol = filterCol(alinkcol, "alink")
        vlinkcol = filterCol(vlinkcol, "vlink")
        textcol = filterCol(textcol, "text")
        bgcol = filterCol(bgcol, "bgcolor")
        
        if bgimg:
            if bgimg.startswith("rel://"):
                # Relative URL
                if self.asHtmlPreview:
                    # If preview, make absolute
                    bgimg = self.wikiDocument.makeRelUrlAbsolute(bgimg)
                else:
                    # If export, reformat a bit
                    bgimg = bgimg[6:]

            bgimg = 'background="%s"' % bgimg
        else:
            bgimg = ''
            
            
        if self.exportType in ("html_previewIE", "html_previewMOZ", "html_previewWK"):
            dblClick = 'ondblclick="window.location.href = &quot;' + \
                    self._getInternaljumpPrefix() + \
                    'mouse/leftdoubleclick/preview/body&quot;;"'

        else:
            dblClick = ''

        # Build tagstring
        bodytag = " ".join((linkcol, alinkcol, vlinkcol, textcol, bgcol, bgimg, dblClick))
        if len(bodytag) > 6:  # the 6 spaces
            bodytag = '<body %s class="wikidpad">' % bodytag
        else:
            bodytag = '<body class="wikidpad">'

        return bodytag


    def getFileHeader(self, wikiPage):
        """
        Return the header part of an HTML file for wikiPage.
        wikiPage -- WikiPage object
        """

        return self._getGenericHtmlHeader(wikiPage.getWikiWord()) + \
                "    %s\n" % self._getBodyTag(wikiPage)



    def getFileFooter(self):
        return """    </body>
</html>
"""

    def getParentLinks(self, wikiPage, asHref=True, wordsToInclude=None):
        parents = ""
        parentRelations = wikiPage.getParentRelationships()[:]
        self.mainControl.getCollator().sort(parentRelations)
        
        for relation in parentRelations:
            if wordsToInclude and relation not in wordsToInclude:
                continue

            if parents != "":
                parents = parents + " | "

            if asHref:
                parents = parents +\
                        '<span class="wikidpad parent-node"><a href="%s" class="wikidpad">%s</a></span>' %\
                        (self.linkConverter.getLinkForWikiWord(relation), relation)
#                         u'<span class="wikidpad parent-node"><a href="%s.html" class="wikidpad">%s</a></span>' %\
#                         (self.filenameConverter.getFilenameForWikiWord(relation), relation)
            else:
                parents = parents +\
                '<span class="wikidpad parent-node"><a href="#%s" class="wikidpad">%s</a></span>' %\
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
        asPreview = self.exportType in ("html_previewIE", "html_previewMOZ", "html_previewWK", "html_previewWX")
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
            if not wikiWord:
                return False

            try:
                wikiPage = self.wikiDocument.getWikiPage(wikiWord)
            except WikiWordNotFoundException:
                return False

        return strToBool(wikiPage.getAttributes().get("export", ("True",))[-1])


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
        
        result.append('<ul class="wikidpad">\n')
        for wikiWord in self.wordList:
            result.append('<li class="wikidpad"><a href="%s" class="wikidpad">%s</a>\n' % (wordToLink(wikiWord),
                    wikiWord))

        result.append('</ul>\n')
        
        return "".join(result)


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
                result.append('<ul class="wikidpad">\n' * (deepness - lastdeepness))
            elif deepness < lastdeepness:
                # print "getContentTreeBody10", deepness, lastdeepness
                result.append('</ul>\n' * (lastdeepness - deepness))
                
            lastdeepness = deepness

            wordSet.remove(wikiWord)

            # print "getContentTreeBody11", repr(wikiWord)
            result.append('<li class="wikidpad"><a href="%s" class="wikidpad">%s</a>\n' % (wordToLink(wikiWord),
                    wikiWord))

        result.append("</ul>\n" * lastdeepness)

        # list words not in the tree
        if len(wordSet) > 0:
            # print "getContentTreeBody13"
            remainList = list(wordSet)
            self.mainControl.getCollator().sort(remainList)
            
            # print "getContentTreeBody14", repr(remainList)
            result.append('<ul class="wikidpad">\n')
            for wikiWord in remainList:
                result.append('<li class="wikidpad"><a href="%s" class="wikidpad">%s</a>\n' % (wordToLink(wikiWord),
                        wikiWord))

            result.append('</ul>\n')


        return "".join(result)


    def getCurrentWikiWord(self):
        """
        Returns the wiki word which is currently processed by the exporter.
        """
        return self.wikiWord


    def formatContent(self, wikiPage, content=None):
        word = wikiPage.getWikiWord()
        formatDetails = wikiPage.getFormatDetails()
        if content is None:
            content = wikiPage.getLiveText()
            self.basePageAst = wikiPage.getLivePageAst()
        else:
            self.basePageAst = wikiPage.parseTextInContext(content)

        if self.linkConverter is None:
            self.linkConverter = BasicLinkConverter(self.wikiDocument, self)
 
        self.asIntHtmlPreview = (self.exportType == "html_previewWX")
        self.asHtmlPreview = self.exportType in ("html_previewWX",
                "html_previewIE", "html_previewMOZ", "html_previewWK")
        self.wikiWord = word

        self.result = []
        self.optsStack = StackedCopyDict()
        self.insertionVisitStack = []
        self.astNodeStack = []
        self.copiedTempFileCache = {}

        self.outFlagEatPostBreak = False
        self.outFlagPostBreakEaten = False

        # Get attribute pattern
        if self.asHtmlPreview:
            proppattern = self.mainControl.getConfig().get(
                        "main", "html_preview_proppattern", "")
        else:
            proppattern = self.mainControl.getConfig().get(
                        "main", "html_export_proppattern", "")

        self.proppattern = re.compile(proppattern,
                re.DOTALL | re.UNICODE | re.MULTILINE)

        if self.asHtmlPreview:
            self.proppatternExcluding = self.mainControl.getConfig().getboolean(
                        "main", "html_preview_proppattern_is_excluding", "True")
        else:
            self.proppatternExcluding = self.mainControl.getConfig().getboolean(
                        "main", "html_export_proppattern_is_excluding", "True")

        if self.asHtmlPreview:
            facename = self.mainControl.getConfig().get(
                    "main", "facename_html_preview", "")
            if facename:
                self.outAppend('<font face="%s" class="wikidpad">' % facename)

        with self.optsStack:
            self.optsStack["innermostFullPageAst"] = self.basePageAst
            self.optsStack["innermostPageUnifName"] = "wikipage/" + word
            self.optsStack["innermostDocPage"] = wikiPage
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
            if absUrl.startswith("file:"):
                absLink = pathnameFromUrl(absUrl)
                imgFile = open(absLink, "rb")
            else:
                imgFile = urllib.request.urlopen(absUrl)
                imgData = imgFile.read()
                imgFile.close()
                imgFile = BytesIO(imgData)

            img = wx.Image(0, 0)
            img.LoadFile(imgFile)
            imgFile.close()
            
            if img.IsOk():
                return img.GetWidth(), img.GetHeight()

            return None, None

        except IOError:
            return None, None


    @staticmethod
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


    def outAppend(self, toAppend, eatPreBreak=False, eatPostBreak=False):
        """
        Append toAppend to self.result, maybe remove or modify it according to
        flags
        """
        if toAppend == "":    # .strip()
            return

        if self.outFlagEatPostBreak and toAppend.strip() == '<br class="wikidpad" />':
            self.outFlagEatPostBreak = eatPostBreak
            self.outFlagPostBreakEaten = True
            return

        if eatPreBreak and len(self.result) > 0 and \
                self.result[-1].strip() == '<br class="wikidpad" />' and \
                not self.outFlagPostBreakEaten:
            self.result[-1] = toAppend
            self.outFlagEatPostBreak = eatPostBreak
            return
        
        if self.outFlagPostBreakEaten:
            self.outFlagPostBreakEaten = (toAppend.strip() == '<br class="wikidpad" />')

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



    START_INDENT_MAP = {"normalindent": '<ul class="wikidpad normalindent">',
            "ul": '<ul class="wikidpad bulletlist">', "ol": '<ol class="wikidpad orderedlist">',
            "ol-roman" : '<ol class="wikidpad withroman">',
            "ol-alpha" : '<ol class="wikidpad withalpha">'}

    END_INDENT_MAP = {"normalindent": '</ul>\n', "ul": '</ul>\n',
            "ol": '</ol>\n', "ol-roman" : '</ol>\n', "ol-alpha" : '</ol>\n'}

    def outStartIndentation(self, indType):
        """
        Insert indentation, bullet, or numbered list start tag.
        ind -- indentation depth
        """
        if indType == "normalindent" and self.asIntHtmlPreview:
            self.outEatBreaks('<blockquote class="wikidpad">')
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
            self.outEatBreaks("</blockquote>\n")
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
        return "".join(self.result)


    def getCommonStylesFromAppendix(self, appendix):
        if appendix is None:
            return "", [], []

        cssClass = ""

        styles = []
        attributes = []

        if hasattr(appendix, "cssClass") and appendix.cssClass is not None:
            cssClass = appendix.cssClass
            
        styleAttr = HOR_ALIGN_CSS_ATTR.get(getattr(appendix, "text_align", None))
        if styleAttr is not None:
            styles.append(styleAttr[0])
            attributes.append(styleAttr[1])

        return cssClass, styles, attributes



    def combineStyles(self, cssClass, styles, attributes):
        if attributes is None:
            attributes = []

        if cssClass and cssClass[0] != " ":
            cssClass = " " + cssClass

        attributes.append('class="wikidpad{0}"'.format(cssClass))
        
        if styles:
            attributes.append('style="' + "; ".join(styles) + '"');
        
        return " " + " ".join(attributes)



    def _processTable(self, content, astNode):
        """
        Write out content of a table as HTML code.
        
        astNode -- node of type "table"
        """
        self.astNodeStack.append(astNode)

        # Retrieve table appendix values
        tableModeAppendix = astNode.findFlatByName("tableModeAppendix")
        css, styles, attribs = self.getCommonStylesFromAppendix(
                tableModeAppendix)
        
        attrStr = self.combineStyles(css, styles, attribs)
        
        # TODO: Move border definition to CSS-file (except for internal preview)
#         if self.asIntHtmlPreview:
        self.outAppend('<table border="2"{0}>\n'.format(attrStr))
#         else:
#             self.outAppend(u'<table{0}>\n'.format(attrStr))

        grid = []
        
        for posRow, row in enumerate(astNode.iterFlatByName("tableRow")):
            gridRow = []
            grid.append(gridRow)

            for posCol, cell in enumerate(row.iterFlatByName("tableCell")):
                gridRow.append(TableCell(self, grid, posRow, posCol, cell,
                        content))
            
        for gridRow in grid:
            for tc in gridRow:
                tc.cleanup()


        for gridRow in grid:
            self.outAppend('<tr class="wikidpad">')
            for tc in gridRow:
                tc.processAst()
            self.outAppend('</tr>\n')


        if self.asIntHtmlPreview:
            self.outAppend('</table>\n<br class="wikidpad" />\n') # , eatPostBreak=not self.asIntHtmlPreview)
        else:
            self.outAppend('</table>\n')

        self.astNodeStack.pop()


    # TODO: Multi-level processing for grouping and tree-like lists
    def _processInsertionResultList(self, resultList, resultItemProcessor,
            appendices):
        """
        Helper function to nicely format a list of result items generated by
        an insertion.
        The function uses the  appendices  given for the insertion to check for
        options if the list should be formatted as table or comma-separated list.
        resultList  list of result items of unspecified type
        resultItemProcessor  callback function which takes an item of  resultList
            and calls the appropriate out... functions (mainly outAppend) to
            produce output for that particular item
        """

        if len(resultList) == 0:
            return

        # Check for desired number of columns (as appendix e.g.
        # "columns 3" was set) and other settings
        cols = 1
        coldirDown = False
        asList = False
        colwidth = None
        tableBorderWidth = 0

        for ap in appendices:
            if ap.startswith("columns "):
                try:
                    v = int(ap[8:])
                    if v > 0:
                        cols = v
                except ValueError:
                    pass
            elif ap == "aslist":
                # No table but comma-separated list
                asList = True
            elif ap == "coldir down":
                # Order in table goes downward first then right
                # Default is right first then downward
                coldirDown = True
            elif ap == "colwidth equal":
                # All columns will have same width
                colwidth = "equal"
            elif ap.startswith("table_border_width "):
                try:
                    v = int(ap[18:])
                    if v >= 0:
                        tableBorderWidth = v
                except ValueError:
                    pass

        # To ensure that the sum of percentages is 100 there is a bit
        # work to do. On the other hand this means that the columns
        # don't have exactly equal width
        if colwidth == "equal":
            colwidth = []
            usedPerc = 0
            for i in range(1, cols + 1):
                cw = i * 100 // cols - usedPerc
                usedPerc += cw
                colwidth.append("%i%%" % cw)

        if asList:
            firstItem = True
            for resultItem in resultList:
                if firstItem:
                    firstItem = False
                else:
                    self.outAppend(", ")
                resultItemProcessor(resultItem)
        else:
            # Convert colwidth to HTML attribute
            if colwidth is None:
                colwidthAttr = [""] * cols
            else:
                colwidthAttr = [' width="%s"' % cw for cw in colwidth]
            
            tableAttrs = ""
            if tableBorderWidth > 0:
                tableAttrs += ' border="%s"' % tableBorderWidth
            
            # We need a table for the resultList
            self.outAppend('<table%s class="wikidpad">\n' % tableAttrs)
            colpos = 0
            firstRow = True

            if coldirDown:
                # Reorder words for downwards direction

                result = []
                itemCount = len(resultList)
                rowCount = (itemCount + cols - 1) // cols
                for r in range(rowCount):
                    result += [resultList[i]
                            for i in range(r, itemCount, rowCount)]
                resultList = result
            
            for resultItem in resultList:
                if colpos == 0:
                    # Start table row
                    self.outAppend('<tr class="wikidpad">')
                    
                if firstRow:
                    self.outAppend('<td valign="top"%s class="wikidpad">' %
                            colwidthAttr[colpos])
                else:
                    self.outAppend('<td valign="top" class="wikidpad">')
                resultItemProcessor(resultItem)
                self.outAppend('</td>')
                
                colpos += 1
                if colpos == cols:
                    # At the end of a row
                    colpos = 0
                    firstRow = False
                    self.outAppend("</tr>\n")
                    
            # Fill the last incomplete row with empty cells if necessary
            if colpos > 0:
                if firstRow:
                    while colpos < cols:
                        self.outAppend('<td%s class="wikidpad"></td>' %
                                colwidthAttr[colpos])
                        colpos += 1
                else:
                    while colpos < cols:
                        self.outAppend('<td class="wikidpad"></td>')
                        colpos += 1

                self.outAppend('</tr>\n')
            
            self.outAppend('</table>')





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
        searchOp = None
        content = None
        htmlContent = None
        key = astNode.key
        value = astNode.value
        appendices = astNode.appendices

        if key == "page":
            if ("wikipage/" + value) in self.insertionVisitStack:
                # Prevent infinite recursion
                return

            containingPage = self.optsStack["innermostDocPage"]
            
            langHelper = wx.GetApp().createWikiLanguageHelper(
                    containingPage.getWikiLanguageName())
                    
            if langHelper.checkForInvalidWikiLink(value,
                    self.mainControl.getWikiDocument()):
                return

            try:
                value = langHelper.resolveWikiWordLink(value, containingPage)
            except ValueError:
                return

            docpage = self.wikiDocument.getWikiPageNoError(value)
            pageAst = docpage.getLivePageAst()
            
            # Value to add to heading level to fix level inside inserted pages
            offsetHead = 0

            # Code to adjust heading level
            if ("adjheading" in appendices) or ("adjheading+" in appendices):
                minHead = 1000 # Just assuming that there won't be 1000 levels deep heading
                # Adjust heading level of insertion
                # First find the lowest heading level used in the inserted page
                for hn in pageAst.iterDeepByName("heading"):
                    minHead = min(minHead, hn.level)
                
                # if minHead is 1000 yet, there is no heading to adjust. Otherwise:
                if minHead < 1000:
                    fatherAst = astNode.astNodeStack[-2]
                    
                    # lastSurroundHead becomes the heading level in which the insertion
                    # is embedded (taken from last heading before insertion tag)
                    lastSurroundHead = -1
                    for hn in fatherAst.iterDeepByName("heading"):
                        if hn.pos > astNode.pos:
                            break
                        lastSurroundHead = hn.level

                    # Finally the offset is calculated
                    if lastSurroundHead > -1:
                        offsetHead = lastSurroundHead - (minHead - 1)


            self.insertionVisitStack.append("wikipage/" + value)
            try:
                
                # Inside an inserted page we don't want anchors to the
                # headings to avoid collisions with headings of surrounding
                # page.

                with self.optsStack:
                    self.optsStack["innermostFullPageAst"] = pageAst
                    self.optsStack["innermostPageUnifName"] = \
                            docpage.getUnifiedPageName()
                    self.optsStack["innermostDocPage"] = docpage

                    self.optsStack["anchorForHeading"] = False
                    if offsetHead != 0:
                        self.optsStack["offsetHeadingLevel"] = \
                                self.optsStack.get("offsetHeadingLevel", 0) + \
                                offsetHead

                    self.processAst(docpage.getLiveText(), pageAst)

            finally:
                del self.insertionVisitStack[-1]

            return
            
        elif key == "rel":
            # List relatives (children, parents)
            if value == "parents":
                wordList = self.wikiDocument.getWikiData().getParentRelationships(
                        self.wikiWord)
            elif value == "children":
                existingonly = ("existingonly" in appendices) # or \
                        # (u"existingonly +" in insertionAstNode.appendices)
                wordList = self.wikiDocument.getWikiData().getChildRelationships(
                        self.wikiWord, existingonly=existingonly,
                        selfreference=False)
            elif value == "parentless":
                wordList = self.wikiDocument.getWikiData().getParentlessWikiWords()
            elif value == "undefined":
                wordList = self.wikiDocument.getWikiData().getUndefinedWords()
            elif value == "top":
                htmlContent = '<a href="#" class="wikidpad">Top</a>'
            elif value == "back":
                if self.asHtmlPreview:
                    htmlContent = \
                            '<a href="' + self._getInternaljumpPrefix() + \
                            'action/history/back" class="wikidpad">Back</a>'
                else:
                    htmlContent = \
                            '<a href="javascript:history.go(-1)" class="wikidpad">Back</a>'

        elif key == "self":
            htmlContent = escapeHtml(self.getCurrentWikiWord())

        elif key == "savedsearch":
            datablock = self.wikiDocument.getWikiData().retrieveDataBlock(
                    "savedsearch/" + value)
            if datablock is not None:
                searchOp = SearchReplaceOperation()
                searchOp.setPackedSettings(datablock)
                searchOp.replaceOp = False
#                 wordList = self.wikiDocument.searchWiki(searchOp)
        elif key == "search":
            searchOp = SearchReplaceOperation()
            searchOp.replaceOp = False
            searchOp.searchStr = value
            
            searchType = Consts.SEARCHTYPE_BOOLEANREGEX
            removeSelf = False
            # Based on
            # SearchAndReplaceDialogs.SearchWikiDialog._buildSearchReplaceOperation
            for ap in appendices:
                if ap == "type boolean" or ap == "type bool":
                    searchType = Consts.SEARCHTYPE_BOOLEANREGEX
                elif ap == "type regex":
                    searchType = Consts.SEARCHTYPE_REGEX
                elif ap == "type asis" or ap == "type plain":
                    searchType = Consts.SEARCHTYPE_ASIS
                elif ap == "type index" and \
                        self.wikiDocument.isSearchIndexEnabled():
                    searchType = Consts.SEARCHTYPE_INDEX
                elif ap == "casesensitive":
                    searchOp.caseSensitive = True
                elif ap == "wholewordsonly":
                    searchOp.wholeWord = True
#                 elif ap == "removeself" or ap == "removethis":
#                     removeSelf = True

            searchOp.booleanOp = searchType == Consts.SEARCHTYPE_BOOLEANREGEX
            searchOp.indexSearch = 'no' if searchType != Consts.SEARCHTYPE_INDEX \
                    else 'default'
            searchOp.wildCard = 'regex' if searchType != Consts.SEARCHTYPE_ASIS \
                    else 'no'

#             wordList = self.wikiDocument.searchWiki(searchOp)
# 
#             # Because a simple search for "foo" includes the page containing
#             # the insertion searching for "foo" there is option "removeself"
#             # to remove the page containing the insertion from the list
#             if removeSelf and self.optsStack["innermostPageUnifName"]\
#                     .startswith(u"wikipage/"):
#                 
#                 selfPageName = self.wikiDocument.getWikiPageNameForLinkTermOrAsIs(
#                         self.optsStack["innermostPageUnifName"][9:])
#                 try:
#                     wordList.remove(selfPageName)
#                 except ValueError:
#                     pass
                    


        elif key == "toc" and value == "":
            pageAst = self.getBasePageAst()
#             pageAst = self.optsStack["innermostFullPageAst"]

            self.outAppend('<div class="wikidpad page-toc">\n')

            for node in pageAst.iterFlatByName("heading"):
                headLevel = node.level            
                if self.asIntHtmlPreview:
                    # Simple indent for internal preview
                    self.outAppend("&nbsp;&nbsp;" * (headLevel - 1))
                else:
                    # use css otherwise
                    self.outAppend('<div class="wikidpad page-toc-level%i">' %
                            headLevel)

                if self.wordAnchor:
                    anchor = self.wordAnchor + ("#.h%i" % node.pos)
                else:
                    anchor = ".h%i" % node.pos

                self.outAppend('<a href="#%s" class="wikidpad">' % anchor)

                with self.optsStack:
                    self.optsStack["suppressLinks"] = True
                    self.processAst(fullContent, node.contentNode)

                self.outAppend('</a>')

                if self.asIntHtmlPreview:
                    self.outAppend('<br class="wikidpad" />\n')
                else:
                    self.outAppend('</div>\n')

            self.outAppend("</div>\n")
#             htmlContent = u"".join(htmlContent)

        elif key == "eval":
            if not self.mainControl.getConfig().getboolean("main",
                    "insertions_allow_eval", False):
                # Evaluation of such insertions not allowed
                htmlContent = _('<pre class="wikidpad">[Allow evaluation of insertions in '
                        '"Options", page "Security", option '
                        '"Process insertion scripts"]</pre>')
            else:
                evalScope = {"pwiki": self.getMainControl(),
                        "lib": self.getMainControl().evalLib}
                expr = astNode.value
                # TODO Test security
                try:
                    content = str(eval(re.sub(r"[\n\r]", "", expr),
                            evalScope))
                except Exception as e:
                    s = StringIO()
                    traceback.print_exc(file=s)
                    htmlContent = '\n<pre class="wikidpad">\n' + \
                            escapeHtmlNoBreaks(s.getvalue()) + '\n</pre>\n'
        elif key == "iconimage":
            imgName = astNode.value
            icPath = wx.GetApp().getIconCache().lookupIconPath(imgName)
            if icPath is None:
                htmlContent = _('<pre class="wikidpad">[Icon "%s" not found]</pre>' % imgName)
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
                
                htmlContent = '<img src="%s" class="wikidpad" />' % url
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
                except Exception as e:
                    s = StringIO()
                    traceback.print_exc(file=s)
                    htmlContent = '<pre class="wikidpad">' + mbcsDec(s.getvalue(), 'replace')[0] + '</pre>'

                if htmlContent is None:
                    htmlContent = ""
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
                    except Exception as e:
                        s = StringIO()
                        traceback.print_exc(file=s)
                        htmlContent = '<pre class="wikidpad">' + mbcsDec(s.getvalue(), 'replace')[0] + '</pre>'

        if searchOp is not None:
            wordList = self.wikiDocument.searchWiki(searchOp)
            
            if ("removeself" in appendices) or ("removethis" in appendices):
                # Because a simple search for "foo" includes the page containing
                # the insertion searching for "foo" there is option "removeself"
                # to remove the page containing the insertion from the list
                if self.optsStack["innermostPageUnifName"].startswith("wikipage/"):
                    selfPageName = self.wikiDocument.getWikiPageNameForLinkTermOrAsIs(
                            self.optsStack["innermostPageUnifName"][9:])
                    try:
                        wordList.remove(selfPageName)
                    except ValueError:
                        pass
            
            if "showtext" in appendices:
                searchOp.beginWikiSearch(self.wikiDocument)
                try:
                    resultList = []
                    for wikiPageName in wordList:
                        docPage = self.wikiDocument.getWikiPage(wikiPageName)
                        text = docPage.getLiveTextNoTemplate()
                        if text is None:
                            continue
                        
                        resultList += [(wikiPageName, text[found[0]:found[1]])
                                for found in searchOp.iterSearchDocPageAndText(docPage, text)]
                        
                    wordList = None  # Wordlist shouldn't be processed further
                finally:
                    searchOp.endWikiSearch()

                def resultItemProcessor(resultItem):
                    # Build a fake "wikiWord" node to call _processWikiWord
                    wwNode = buildSyntaxNode([], astNode.pos, "wikiWord")
                    wwNode.wikiWord = resultItem[0]
                    wwNode.anchorLink = None
                    wwNode.titleNode = buildSyntaxNode(resultItem[1],
                            astNode.pos, "plainText")

                    self._processWikiWord(wwNode, fullContent)


                self._processInsertionResultList(resultList,
                        resultItemProcessor, appendices)


        if wordList is not None:
            # Create content as a nicely formatted list of wiki words

            self.mainControl.getCollator().sort(wordList)

            if len(wordList) == 0:
                content = ""
            else:
                self._processInsertionResultList(wordList, self._processWikiWord,
                        appendices)
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
            
        if self.avoidDeadWikiLinks and not self.shouldExport(
                self.wikiDocument.getWikiPageNameForLinkTerm(wikiWord)):
            link = None
        else:
            self.linkConverter.wikiDocument = self.wikiDocument
            link = self.linkConverter.getLinkForWikiWord(wikiWord)

        selfLink = False

        if link:
            linkTo = self.wikiDocument.getWikiPageNameForLinkTerm(wikiWord)

            # Test if link to same page itself (maybe with an anchor fragment)
            if not self.exportType == "html_multi":
                linkFrom = self.wikiDocument.getWikiPageNameForLinkTerm(
                        self.wikiWord)
                if linkTo is not None and linkTo == linkFrom:
                    # Page links to itself
                    selfLink = True

            # Add anchor fragment if present
            if anchorLink:
                if selfLink:
                    link = "#" + anchorLink
                else:
                    link += "#" + anchorLink

            title = None
            if linkTo is not None:
                propList = self.wikiDocument.getAttributeTriples(linkTo,
                        "short_hint", None)
                if len(propList) > 0:
                    title = propList[-1][2]

            if self.optsStack.get("suppressLinks", False):
                self.outAppend('<span class="wikidpad wiki-link">')
            else:
                if title is not None:
                    self.outAppend('<span class="wikidpad wiki-link"><a href="%s" title="%s" class="wikidpad">' %
                            (link, escapeHtmlNoBreaks(title)))
                else:
                    self.outAppend('<span class="wikidpad wiki-link"><a href="%s" class="wikidpad">' %
                            link)

            if titleNode is not None:
                with self.optsStack:
                    self.optsStack["suppressLinks"] = True
                    self.processAst(fullContent, titleNode)
            else:
                self.outAppend(escapeHtml(wikiWord))                        

            if self.optsStack.get("suppressLinks", False):
                self.outAppend('</span>')
            else:
                self.outAppend('</a></span>')
        else:
            if titleNode is not None:
                self.processAst(fullContent, titleNode)
            else:
                if isinstance(astNodeOrWord, SyntaxNode):
                    self.outAppend(escapeHtml(astNodeOrWord.getString()))
                else:
                    self.outAppend(escapeHtml(astNodeOrWord))

        self.astNodeStack.pop()


    def _processUrlLink(self, fullContent, astNode):
        link = astNode.url
        pointRelative = False  # Should final link be relative?

        if link.startswith("rel://"):
            pointRelative = True
            absUrl = self.wikiDocument.makeRelUrlAbsolute(link)

            # Relative URL
            if self.asHtmlPreview:
                # If preview, make absolute
                link = absUrl
            else:
                if self.referencedStorageFiles is not None:
                    # Get absolute path to the file
                    absPath = StringOps.pathnameFromUrl(absUrl)
                    # and to the file storage
                    stPath = self.wikiDocument.getFileStorage().getStoragePath()
                    
                    isCont = testContainedInDir(stPath, absPath)

                    if isCont:
                        # File is in file storage -> add to
                        # referenced storage files                            
                        self.referencedStorageFiles.add(
                                StringOps.relativeFilePath(
                                self.wikiDocument.getWikiPath(),
                                absPath))
                        
                        relPath = StringOps.pathnameFromUrl(link[6:], False)
                
                        absUrl = "file:" + StringOps.urlFromPathname(
                                os.path.abspath(os.path.join(self.exportDest,
                                relPath)))
                        link = absUrl

        else:
            absUrl = link

        lowerLink = link.lower()
        
        if astNode.appendixNode is None:
            appendixDict = {}
        else:
            appendixDict = dict(astNode.appendixNode.entries)

        # Decide if this is an image link
        if "l" in appendixDict:
            urlAsImage = False
        elif "i" in appendixDict:
            urlAsImage = True
        elif self.asHtmlPreview and \
                self.mainControl.getConfig().getboolean(
                "main", "html_preview_pics_as_links"):
            urlAsImage = False
        elif not self.asHtmlPreview and \
                self.addOpt[self.ADDOPT_IDX_PICS_AS_LINKS]:
            urlAsImage = False
        elif lowerLink.split(".")[-1] in ("jpg", "jpeg", "gif", "png", "tif",
                "bmp"):
#         lowerLink.endswith(".jpg") or \
#                 lowerLink.endswith(".gif") or \
#                 lowerLink.endswith(".png") or \
#                 lowerLink.endswith(".tif") or \
#                 lowerLink.endswith(".bmp"):
            urlAsImage = True
        else:
            urlAsImage = False

        pointingType = appendixDict.get("p")

        relRelocate = True # Relocate(=rewrite) relative link?

        # Decide if link should be relative or absolute
        if self.asHtmlPreview:
            # For preview always absolute link
            pointRelative = False
        elif pointingType == "abs":
            pointRelative = False
        elif pointingType == "rel":
            pointRelative = True
        elif pointingType == "rnr":
            pointRelative = True
            relRelocate = False

        if pointRelative:
            if not relRelocate and lowerLink.startswith("rel://"):
                # Do not relocate relative link (might link to a resource
                # outside of WikidPad, relative to export destination)
                link = link[6:]
            elif lowerLink.startswith("file:") or \
                    lowerLink.startswith("rel://"):
                # Even if link is already relative it is relative to
                # wrong location in most cases
                absPath = StringOps.pathnameFromUrl(absUrl)
                relPath = StringOps.relativeFilePath(self.exportDest,
                        absPath)
                if relPath is None:
                    link = absUrl
                else:
                    link = StringOps.urlFromPathname(relPath)
        else:
            if lowerLink.startswith("rel://"):
                link = absUrl


        if urlAsImage:
            # Ignore title, use image

            css, styles, attribs = self.getCommonStylesFromAppendix(
                    astNode.appendixNode)

            # Size info for direct setting in HTML code
            sizeInfo = appendixDict.get("s")
            # Relative size info which modifies real image size
            relSizeInfo = appendixDict.get("r")

            if sizeInfo is not None:
                try:
                    widthStr, heightStr = sizeInfo.split("x")
                    if self.isHtmlSizeValue(widthStr) and \
                            self.isHtmlSizeValue(heightStr):
                        attribs.append('width="{0}" height="{1}"'.format(
                                widthStr, heightStr))
                except:
                    # something does not meet syntax requirements
                    pass
            
            elif relSizeInfo is not None:
                params = relSizeInfo.split("x")
                if len(params) == 1:
                    if params[0] == "":
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
                        if width.getUnit() == width.UNIT_FACTOR:
                            imgWidth = int(imgWidth * width.getValue())
                            imgHeight = int(imgHeight * height.getValue())
                        elif width.getUnit() == width.UNIT_PIXEL:
                            if width.getValue() <= 0 or height.getValue() <= 0 or \
                                    imgWidth <= 0 or imgHeight <= 0:
                                imgWidth = 0
                                imgHeight = 0
                            else:
                                imgWidth, imgHeight = calcResizeArIntoBoundingBox(
                                        imgWidth, imgHeight, 
                                        width.getValue(), height.getValue(),
                                        "upright" in appendixDict and
                                        strToBool(appendixDict.get("upright"),
                                        True))
                        
                        # Round dimensions to integers (and ensure they are non-negative)
                        imgWidth = max(0, int(round(imgWidth)))
                        imgHeight = max(0, int(round(imgHeight)))

                        attribs.append('width="{0}" height="{1}"'.format(
                                imgWidth, imgHeight))

            for key in ("align", "a", "A"):
                alignInTag = IMG_ALIGN_ATTR.get(appendixDict.get(key), "")
                if alignInTag != '':
                    attribs.append(alignInTag)
                    break

            if self.asIntHtmlPreview:
                attribs.append('border="0"')
                if lowerLink.startswith("file:"):
                    # At least on Windows, wxWidgets has another
                    # opinion how a local file URL should look like
                    # than Python
                    p = pathnameFromUrl(link)
                    link = wx.FileSystem.FileNameToURL(p)
                    
            attrStr = self.combineStyles(css, styles, attribs)

            self.outAppend('<img src="{0}"{1} />'.format(link, attrStr))
        else:
            if not self.optsStack.get("suppressLinks", False):
                # If we are in a title, only image urls would be allowed
                # but we are not
                self.outAppend('<span class="wikidpad url-link"><a href="%s" class="wikidpad">' % link)
                if astNode.titleNode is not None:
                    with self.optsStack:
                        self.optsStack["suppressLinks"] = True
                        self.processAst(fullContent, astNode.titleNode)
                else:
                    self.outAppend(escapeHtml(astNode.coreNode.getString()))                        
                self.outAppend('</a></span>')



    def processAst(self, content, pageAst):
        """
        Actual token to HTML converter. May be called recursively
        """
        self.astNodeStack.append(pageAst)
        try:
            for node in pageAst.iterFlatNamed():
                if not self.processAstNode(node, content, pageAst):
                    self.outAppend('<tt class="wikidpad">' + escapeHtmlNoBreaks(
                        _('[Unknown parser node with name "%s" found]') % node.name) + \
                        '</tt>')
        finally:
            self.astNodeStack.pop()


    def processAstNode(self, node, content, pageAst):
        tname = node.name
        
        if tname is None:
            return True
        elif tname == "plainText":
            self.outAppend(escapeHtmlNoBreaks(node.getString()))
        elif tname == "lineBreak":
            self.outAppend('<br class="wikidpad" />\n')
        elif tname == "newParagraph":
            self.outAppend('\n<p class="wikidpad" />')
        elif tname == "whitespace":
            self.outAppend(" ")

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
        elif tname == "romanList":
            self.outStartIndentation("ol-roman")
            self.processAst(content, node)
            self.outEndIndentation("ol-roman")
        elif tname == "alphaList":
            self.outStartIndentation("ol-alpha")
            self.processAst(content, node)
            self.outEndIndentation("ol-alpha")

        elif tname == "bullet":
            pass
        elif tname == "bulletEntry":
            self.outAppend('\n<li class="wikidpad">', eatPreBreak=True)
            self.processAst(content, node)
            self.outAppend('</li>', eatPreBreak=True)
        elif tname in ("number", "roman", "alpha"):
            pass
        elif tname == "numberEntry":
            self.outAppend('\n<li class="wikidpad">', eatPreBreak=True)
            self.processAst(content, node)
            self.outAppend('</li>', eatPreBreak=True)
            

        elif tname == "italics":
            self.outAppend('<i class="wikidpad">')
            self.processAst(content, node)
            self.outAppend('</i>')
        elif tname == "bold":
            self.outAppend('<b class="wikidpad">')
            self.processAst(content, node)
            self.outAppend('</b>')

        elif tname == "htmlTag" or tname == "htmlEntity":
            self.outAppend(node.getString())
        elif tname == "htmlEquivalent":
            htmlContent = node.htmlContent
            if isinstance(htmlContent, HtmlStartTag):
                htmlContent = htmlContent.clone()
                htmlContent.addAttribute("class", "wikidpad")
                if htmlContent.getTag() in ("li", "dl", "dt", "dd", "tr"):
                    self.outAppend("\n")
                
                if htmlContent.getTag() == "table":
                    # TODO: Remove for external HTML viewer
                    htmlContent.addAttribute("border", "2") 

            self.outAppend(htmlContent.asString())

        elif tname == "heading":
            if self.optsStack.get("anchorForHeading", True):
                if self.wordAnchor:
                    anchor = self.wordAnchor + ('#.h%i' % node.pos)
                else:
                    anchor = '.h%i' % node.pos

                self.outAppend('<a name="%s" class="wikidpad"></a>' % anchor)

            headLevel = node.level + self.optsStack.get(
                    "offsetHeadingLevel", 0)

            boundHeadLevel = min(6, headLevel)
            self.outAppend('<h%i class="wikidpad heading-level%i">' %
                    (boundHeadLevel, headLevel), eatPreBreak=True)
            self.processAst(content, node.contentNode)
            self.outAppend('</h%i>\n' % boundHeadLevel, eatPostBreak=True)

        elif tname == "horizontalLine":
            self.outEatBreaks('<hr class="wikidpad" />\n')

        elif tname == "preBlock":
            self.outAppend('<pre class="wikidpad">%s</pre>\n' %
                    escapeHtmlNoBreaks(
                    node.findFlatByName("preText").getString()), True,
                    not self.asIntHtmlPreview)
            if self.asIntHtmlPreview:
                self.outAppend('<br class="wikidpad" />\n')
        elif tname == "bodyHtmlTag":
            self.outAppend(node.content)
        elif tname == "todoEntry":
            self.outAppend('<span class="wikidpad todo">%s%s' %
                    (node.key, node.delimiter))
            self.processAst(content, node.valueNode)
            self.outAppend('</span>')
        # TODO remove "property"-compatibility
        elif tname in ("property", "attribute"):  # for compatibility with old language plugins
            for propKey, propValue in node.attrs:
                standardAttribute = "%s: %s" % (propKey, propValue)
                standardAttributeMatching = \
                        bool(self.proppattern.match(standardAttribute))
                # Output only for different truth values
                # (Either it matches and matching attrs should not be
                # hidden or vice versa)
                if standardAttributeMatching != self.proppatternExcluding:
                    # TODO remove "property"-compatibility
                    self.outAppend( '<span class="wikidpad property attribute">[%s: %s]</span>' % 
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
                self.outAppend('<a name="%s" class="wikidpad"></a>' %
                        (self.wordAnchor + "#" + node.anchorLink))
            else:
                self.outAppend('<a name="%s" class="wikidpad"></a>' % node.anchorLink)                
        elif tname == "wikiWord":
            self._processWikiWord(node, content)
        elif tname == "table":
            self._processTable(content, node)
        elif tname == "tableCellAppendix":
            pass
        elif tname == "footnote":
            footnoteId = node.footnoteId
            fnAnchorNode = getFootnoteAnchorDict(self.basePageAst).get(
                    footnoteId)

            if fnAnchorNode is None:
                self.outAppend(escapeHtml(node.getString()))
            else:
                if self.wordAnchor:
                    fnAnchor = self.wordAnchor + '#.f' + _escapeAnchor(
                            footnoteId)
                else:
                    fnAnchor = '.f' + _escapeAnchor(footnoteId)

                if fnAnchorNode.pos == node.pos:
                    # Current footnote token tok is an anchor (=last
                    # footnote token with this footnoteId)

                    self.outAppend('<a name="%s" class="wikidpad"></a>' % fnAnchor)
                    self.outAppend(escapeHtml(node.getString()))
                else:
                    if not self.optsStack.get("suppressLinks", False):
                        # Current token is not an anchor -> make it a link.
                        self.outAppend('<a href="#%s" class="wikidpad">%s</a>' % (fnAnchor,
                        escapeHtml(node.getString())))
        elif tname == "urlLink":
            self._processUrlLink(content, node)
        elif tname == "stringEnd":
            pass
        elif getattr(node, "helperNode", False):
            if not node.isTerminal() and getattr(node, "helperRecursive", False):
                self.processAst(content, node)
        else:
            return False
        
        return True




