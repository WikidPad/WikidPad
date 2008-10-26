# from Enum import Enumeration
import sys, os, string, re, traceback, sets, locale, time, urllib
from os.path import join, exists, splitext, abspath
from cStringIO import StringIO
import shutil
## from xml.sax.saxutils import escape

import urllib_red as urllib

import wx

from wxHelper import XrcControls, GUI_ID


from WikiExceptions import WikiWordNotFoundException, ExportException
import WikiFormatting
from StringOps import *
from Utilities import StackedCopyDict
from TempFileSet import TempFileSet

from SearchAndReplace import SearchReplaceOperation, ListWikiPagesOperation, \
        ListItemWithSubtreeWikiPagesNode

import Configuration

import OsAbstract

import WikiFormatting
import DocPages
import PageAst




class AbstractExporter:
    def __init__(self, mainControl):
        self.wikiDataManager = None
        self.mainControl = mainControl

    def getMainControl(self):
        return self.mainControl    
 
    def setWikiDataManager(self, wikiDataManager):
        self.wikiDataManager = wikiDataManager

    def setWikiDocument(self, wikiDocument):
        self.wikiDataManager = wikiDocument


    def getWikiDataManager(self):
        return self.wikiDataManager

    def getWikiDocument(self):
        return self.wikiDataManager

    def getExportTypes(self, guiparent):
        """
        Return sequence of tuples with the description of export types provided
        by this object. A tuple has the form (<exp. type>,
            <human readable description>, <panel for add. options or None>)
        If panels for additional options must be created, they should use
        guiparent as parent
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
        raise NotImplementedError


    def export(self, wikiDataManager, wordList, exportType, exportDest,
            compatFilenames, addOpt):
        """
        Run export operation.
        
        wikiDataManager -- WikiDataManager object
        wordList -- Sequence of wiki words to export
        exportType -- string tag to identify how to export
        exportDest -- Path to destination directory or file to export to
        compatFilenames -- Should the filenames be encoded to be lowest
                           level compatible
        addOpt -- additional options returned by getAddOpt()
        """
        raise NotImplementedError



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



class LinkCreatorForHtmlMultiPageExport:
    """
    Faked link dictionary for HTML exporter
    """
    def __init__(self, wikiData, htmlXmlExporter):
        self.wikiData = wikiData
        self.htmlXmlExporter = htmlXmlExporter
        
    def get(self, word, default = None):
        if not self.wikiData.isDefinedWikiWord(word):
            return default
        if not self.htmlXmlExporter.shouldExport(word):
            return default

        relUnAlias = self.wikiData.getAliasesWikiWord(word)
        return urlFromPathname(self.htmlXmlExporter.convertFilename(
                u"%s.html" % relUnAlias))


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




# TODO UTF-8 support for HTML? Other encodings?

class HtmlXmlExporter(AbstractExporter):
    def __init__(self, mainControl):
        """
        mainControl -- Currently PersonalWikiFrame object
        """
        AbstractExporter.__init__(self, mainControl)
        self.wikiData = None
        self.wordList = None
        self.exportDest = None
#         self.styleSheet = "wikistyle.css"
        
        # List of tuples (<source CSS path>, <dest CSS file name / url>)
        self.styleSheetList = []
        self.basePageAst = None
#         self.tokenizer = Tokenizer(
#                 WikiFormatting.CombinedHtmlExportRE, -1)
                
        self.exportType = None
        self.statestack = None
        self.referencedStorageFiles = None
        
        # If true ignores newlines, only an empty line starts a new paragraph
        self.paragraphMode = False
        # deepness of numeric bullets
        self.numericdeepness = None
        self.preMode = None  # Count how many <pre> tags are open
        self.consecEmptyLineCount = 0  # Consecutive empty line count
        self.links = None
        self.wordAnchor = None  # For multiple wiki pages in one HTML page, this contains the anchor
                # of the current word.
        self.tempFileSet = None
        self.convertFilename = removeBracketsFilename   # lambda s: mbcsEnc(s, "replace")[0]
        
        self.result = None
        
        # Flag to control how to push output into self.result
        self.outFlagEatPostBreak = False
        self.outFlagPostBreakEaten = False


    def getMainControl(self):
        return self.mainControl        

    def setWikiDataManager(self, wikiDataManager):
        self.wikiDataManager = wikiDataManager
        if self.wikiDataManager is None:
            self.wikiData = None
        else:
            self.wikiData = self.wikiDataManager.getWikiData()
            self.buildStyleSheetList()

    def setWikiDocument(self, wikiDataManager):
        self.setWikiDataManager(wikiDataManager)

    def getExportTypes(self, guiparent):
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
            (u"html_single", _(u'Single HTML page'), htmlPanel),
            (u"html_multi", _(u'Set of HTML pages'), htmlPanel),
            (u"xml", _(u'XML file'), None)
            )


#     def getExportDestinationType(self, exportType):
#         """
#         Return one of the EXPORT_DEST_TYPE_* constants describing
#         if exportType exorts to a file or directory
#         """
#         TYPEMAP = {
#                 u"html_single": EXPORT_DEST_TYPE_DIR,
#                 u"html_multi": EXPORT_DEST_TYPE_DIR,
#                 u"xml": EXPORT_DEST_TYPE_FILE
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
        if exportType == u"xml":
            return ((_(u"XML files (*.xml)"), "*.xml"),) 
        
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


    def export(self, wikiDataManager, wordList, exportType, exportDest,
            compatFilenames, addOpt):
        """
        Run export operation.
        
        wikiDataManager -- WikiDataManager object
        wordList -- Sequence of wiki words to export
        exportType -- string tag to identify how to export
        exportDest -- Path to destination directory or file to export to
        compatFilenames -- Should the filenames be encoded to be lowest
                           level compatible (ascii only)?
        addOpt -- additional options returned by getAddOpt()
        """
        
#         print "export1", repr((pWiki, wikiDataManager, wordList, exportType, exportDest,
#             compatFilenames, addopt))

        self.wikiDataManager = wikiDataManager
        self.wikiData = self.wikiDataManager.getWikiData()

        self.wordList = []
        for w in wordList:
            if self.wikiDataManager.isDefinedWikiWord(w):
                self.wordList.append(w)

        if len(self.wordList) == 0:
            return

#         self.wordList = wordList
        self.exportType = exportType
        self.exportDest = exportDest
        self.addOpt = addOpt

        if compatFilenames:
            self.convertFilename = removeBracketsToCompFilename
        else:
            self.convertFilename = removeBracketsFilename    # lambda s: mbcsEnc(s, "replace")[0]
            
        self.referencedStorageFiles = None

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


        if exportType == u"html_single":
            browserFile = self._exportHtmlSingleFile()
        elif exportType == u"html_multi":
            browserFile = self._exportHtmlMultipleFiles()
        elif exportType == u"xml":
            browserFile = self._exportXml()

        # Other supported types: html_previewWX, html_previewIE, html_previewMOZ

#         if not compatFilenames:
#             browserFile = mbcsEnc(browserFile)[0]

        wx.GetApp().getInsertionPluginManager().taskEnd()

        if self.referencedStorageFiles is not None:
            # Some files must be available
            wikiPath = self.wikiDataManager.getWikiPath()
            
            if abspath(wikiPath) != abspath(self.exportDest):
                # Now we have to copy the referenced files to new location
                for rsf in self.referencedStorageFiles:
                    OsAbstract.copyFile(join(wikiPath, rsf),
                            join(self.exportDest, rsf))


        if self.mainControl.getConfig().getboolean(
                "main", "start_browser_after_export") and browserFile:
            OsAbstract.startFile(self.mainControl, browserFile)
#             if Configuration.isWindows():
#                  os.startfile(startfile)
#                 # os.startfile(mbcsEnc(link2, "replace")[0])
#             else:
#                 # Better solution?
#                 wx.LaunchDefaultBrowser(startfile)    # TODO

        self.tempFileSet.reset()
        self.tempFileSet = None

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


    def _exportHtmlSingleFile(self):
        config = self.mainControl.getConfig()
        sepLineCount = config.getint("main",
                "html_export_singlePage_sepLineCount", 10)
        
        if sepLineCount < 0:
            sepLineCount = 10
        if len(self.wordList) == 1:
            self.exportType = u"html_multi"
            return self._exportHtmlMultipleFiles()

        outputFile = join(self.exportDest,
                self.convertFilename(u"%s.html" % self.mainControl.wikiName))
        self.buildStyleSheetList()
#         self.styleSheet = "wikistyle.css"

        if exists(pathEnc(outputFile)):
            os.unlink(pathEnc(outputFile))

        realfp = open(pathEnc(outputFile), "w")
        fp = utf8Writer(realfp, "replace")
        fp.write(self.getFileHeaderMultiPage(self.mainControl.wikiName))

        tocTitle = self.addOpt[2]

        if self.addOpt[1] == 1:
            # Write a content tree at beginning
            rootPage = self.mainControl.getWikiDocument().getWikiPage(
                        self.mainControl.getWikiDocument().getWikiName())
            flatTree = rootPage.getFlatTree()

            fp.write((u'<h2>%s</h2>\n'
                    '%s%s<hr size="1"/>') %
                    (tocTitle, # = "Table of Contents"
                    self.getContentTreeBody(flatTree, linkAsFragments=True),
                    u'<br />\n' * sepLineCount))

        elif self.addOpt[1] == 2:
            # Write a content list at beginning
            fp.write((u'<h2>%s</h2>\n'
                    '%s%s<hr size="1"/>') %
                    (tocTitle, # = "Table of Contents"
                    self.getContentListBody(linkAsFragments=True),
                    u'<br />\n' * sepLineCount))
                    
        links = {}

        # First build links dictionary for all included words and their aliases
        for word in self.wordList:
            wikiPage = self.wikiDataManager.getWikiPage(word)
            if not self.shouldExport(word, wikiPage):
                continue
            for alias in wikiPage.getProperties().get("alias", ()):
                links[alias] = u"#%s" % _escapeAnchor(word)

            links[word] = u"#%s" % _escapeAnchor(word)

        # Then create the big page word by word
        for word in self.wordList:

            wikiPage = self.wikiDataManager.getWikiPage(word)
            if not self.shouldExport(word, wikiPage):
                continue

            try:
                content = wikiPage.getLiveText()
                formatDetails = wikiPage.getFormatDetails()
                    
                self.wordAnchor = _escapeAnchor(word)
                formattedContent = self.formatContent(word, content,
                        formatDetails, links)
                fp.write((u'<span class="wiki-name-ref">'+
                        u'[<a name="%s">%s</a>]</span><br /><br />'+
                        u'<span class="parent-nodes">parent nodes: %s</span>'+
                        u'<br />%s%s<hr size="1"/>') %
                        (self.wordAnchor, word,
                        self.getParentLinks(wikiPage, False), formattedContent,
                        u'<br />\n' * sepLineCount))
            except Exception, e:
                traceback.print_exc()

        self.wordAnchor = None

        fp.write(self.getFileFooter())
        fp.reset()
        realfp.close() 
        self.copyCssFiles(self.exportDest)
        return outputFile


    def _exportHtmlMultipleFiles(self):
        links = LinkCreatorForHtmlMultiPageExport(
                self.wikiDataManager.getWikiData(), self)
#         self.styleSheet = "wikistyle.css"
        self.buildStyleSheetList()


        if self.addOpt[1] in (1,2):
            # Write a table of contents in html page "index.html"
            self.links = links

            # TODO Configurable name
            outputFile = join(self.exportDest, self.convertFilename(u"index.html"))
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

        for word in self.wordList:
            wikiPage = self.wikiDataManager.getWikiPage(word)
            if not self.shouldExport(word, wikiPage):
                continue

            self.exportWordToHtmlPage(self.exportDest, word, links, False)
        self.copyCssFiles(self.exportDest)
        rootFile = join(self.exportDest, 
                self.convertFilename(u"%s.html" % self.wordList[0]))    #self.mainControl.wikiName))[0]
        return rootFile


    def _exportXml(self):
#         outputFile = join(self.exportDest,
#                 self.convertFilename(u"%s.xml" % self.mainControl.wikiName))

        outputFile = self.exportDest

        if exists(pathEnc(outputFile)):
            os.unlink(pathEnc(outputFile))

        realfp = open(pathEnc(outputFile), "w")
        fp = utf8Writer(realfp, "replace")

        fp.write(u'<?xml version="1.0" encoding="utf-8" ?>')
        fp.write(u'<wiki name="%s">' % self.mainControl.wikiName)
        
        for word in self.wordList:
            wikiPage = self.wikiDataManager.getWikiPage(word)
            if not self.shouldExport(word, wikiPage):
                continue
                
            # Why localtime?
            modified, created = wikiPage.getTimestamps()[:2]
            created = time.localtime(float(created))
            modified = time.localtime(float(modified))
            
            fp.write(u'<wikiword name="%s" created="%s" modified="%s">' %
                    (word, created, modified))

            try:
                content = wikiPage.getLiveText()
                formatDetails = wikiPage.getFormatDetails()
                links = {}
                for relation in wikiPage.getChildRelationships(
                        existingonly=True, selfreference=False):
                    if not self.shouldExport(relation):
                        continue

                    # get aliases too
                    relUnAlias = self.wikiDataManager.getWikiData().getAliasesWikiWord(relation)
                    links[relation] = u"#%s" % _escapeAnchor(relUnAlias)
                    
#                     wordForAlias = self.wikiData.getAliasesWikiWord(relation)
#                     if wordForAlias:
#                         links[relation] = u"#%s" % wordForAlias
#                     else:
#                         links[relation] = u"#%s" % relation
                    
                formattedContent = self.formatContent(word, content,
                        formatDetails, links, asXml=True)
                fp.write(formattedContent)

            except Exception, e:
                traceback.print_exc()

            fp.write(u'</wikiword>')

        fp.write(u"</wiki>")
        fp.reset()        
        realfp.close()

        return outputFile
        
    def exportWordToHtmlPage(self, dir, word, links=None, startFile=True,
            onlyInclude=None):
        outputFile = join(dir, self.convertFilename(u"%s.html" % word))
        try:
            if exists(pathEnc(outputFile)):
                os.unlink(pathEnc(outputFile))

            realfp = open(pathEnc(outputFile), "w")
            fp = utf8Writer(realfp, "replace")
            
            wikiPage = self.wikiDataManager.getWikiPage(word)
            content = wikiPage.getLiveText()
            formatDetails = wikiPage.getFormatDetails()       
            fp.write(self.exportContentToHtmlString(word, content,
                    formatDetails, links, startFile, onlyInclude))
            fp.reset()        
            realfp.close()
        except Exception, e:
            sys.stderr.write("Error while exporting word %s" % repr(word))
            traceback.print_exc()

        return outputFile


    def exportContentToHtmlString(self, word, content, formatDetails,
            links=None, startFile=True, onlyInclude=None):
        """
        Read content of wiki word word, create an HTML page and return it
        """
        result = []
        wikiPage = self.wikiDataManager.getWikiPageNoError(word)

        formattedContent = self.formatContent(word, content, formatDetails,
                links)

        if Configuration.isUnicode():
            result.append(self.getFileHeader(wikiPage))
        else:
            # Retrieve file header without encoding mentioned
            result.append(self.getFileHeaderNoCharset(wikiPage))

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
        
        # Filter
        def filterCol(col, prop):
            # Filter color
            if htmlColorToRgbTuple(col) is not None:
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

#         elif self.exportType == u"html_previewMOZ":
#             dblClick = 'ondblclick="window.location.href = &quot;file://internaljump/mouse/leftdoubleclick/preview/body&quot;;"'
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


    def getFileHeaderNoCharset(self, wikiPage):
        """
        Ansi version of getFileHeader
        wikiPage -- WikiPage object
        """
        return self._getGenericHtmlHeader(wikiPage.getWikiWord(), charset=u"") + \
                u"    %s\n" % self._getBodyTag(wikiPage)


#         return u"""<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.0 Transitional//EN">
# <html>
#     <head>
#         <meta http-equiv="content-type" content="text/html">
#         <title>%s</title>
#         <link type="text/css" rel="stylesheet" href="wikistyle.css">
#     </head>
#     %s
# """ % (wikiPage.getWikiWord(), self._getBodyTag(wikiPage))



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
                        (self.convertFilename(relation), relation)
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
            # Step one: Create pathes
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
            if self.wikiDataManager is not None:
                pathlist.append(join(self.wikiDataManager.getDataDir(),
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
            if self.wikiDataManager is not None:
                pathlist.append(join(self.wikiDataManager.getDataDir(),
                        "wikipreview.css"))

            # Step two: Check files for existence and create styleSheetList
            # We don't need the source pathes, only a list of URLs to the
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
            if self.wikiDataManager is not None:
                result.append((join(self.wikiDataManager.getDataDir(),
                        "wikistyle.css"), "wikistyle.css"))

            # Filter non-existent
            self.styleSheetList = [ item for item in result
                    if exists(pathEnc(item[0])) ]




    def copyCssFiles(self, dir):
        for src, dst in self.styleSheetList:
            if src is None:
                continue
            try:
#                 if not exists(pathEnc(join(dir, dst))):
                OsAbstract.copyFile(pathEnc(src), pathEnc(join(dir, dst)))
            except:
                traceback.print_exc()
                
        
        
#         if not exists(pathEnc(join(dir, self.styleSheet))):
#             cssFile = pathEnc(join(self.mainControl.wikiAppDir, 'export', self.styleSheet))
#             if exists(pathEnc(cssFile)):
#                 OsAbstract.copyFile(pathEnc(cssFile), pathEnc(join(dir, self.styleSheet)))

    def shouldExport(self, wikiWord, wikiPage=None):
        if not wikiPage:
            try:
                wikiPage = self.wikiDataManager.getWikiPage(wikiWord)
            except WikiWordNotFoundException:
                return False

        #print "shouldExport", mbcsEnc(wikiWord)[0], repr(wikiPage.props.get("export", ("True",))), \
         #       type(wikiPage.props.get("export", ("True",)))

        return strToBool(wikiPage.getProperties().get("export", ("True",))[-1])


    def getContentListBody(self, linkAsFragments):
        wikiData = self.wikiDataManager.getWikiData()

        if linkAsFragments:
            def wordToLink(wikiWord):
                relUnAlias = wikiData.getAliasesWikiWord(wikiWord)
                # TODO Use self.convertFilename here?
                return u"#%s" % _escapeAnchor(relUnAlias)
        else:
            def wordToLink(wikiWord):
                relUnAlias = wikiData.getAliasesWikiWord(wikiWord)
                # TODO Use self.convertFilename here?
                return self.links.get(relUnAlias)

        result = []
        
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
        wordSet = sets.Set(self.wordList)
        deepStack = [-1]
        result = []
        wikiData = self.wikiDataManager.getWikiData()
        
        if linkAsFragments:
            def wordToLink(wikiWord):
                relUnAlias = wikiData.getAliasesWikiWord(wikiWord)
                # TODO Use self.convertFilename here?
                return u"#%s" % _escapeAnchor(relUnAlias)
        else:
            def wordToLink(wikiWord):
                relUnAlias = wikiData.getAliasesWikiWord(wikiWord)
                # TODO Use self.convertFilename here?
                return self.links.get(relUnAlias)


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


    def popState(self):
        breakEat = len(self.statestack) <= 2 or self.asIntHtmlPreview
        if self.statestack[-1][0] == "normalindent":
            if self.asIntHtmlPreview:
                self.outEatBreaks(u"</blockquote>\n")
            else:
                self.outAppend(u"</ul>\n", eatPreBreak=breakEat,
                        eatPostBreak=breakEat)
        elif self.statestack[-1][0] == "ol":
            self.outAppend(u"</ol>\n", eatPreBreak=breakEat,
                    eatPostBreak=breakEat)
            self.numericdeepness -= 1
        elif self.statestack[-1][0] == "ul":
            self.outAppend(u"</ul>\n", eatPreBreak=breakEat,
                    eatPostBreak=breakEat)

        self.statestack.pop()

    def hasStates(self):
        """
        Return true iff more than the basic state is on the state stack yet.
        """
        return len(self.statestack) > 1


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


    def getCurrentWikiWord(self):
        """
        Returns the wiki word which is currently processed by the exporter.
        """
        return self.wikiWord


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
        

    # TODO Remove
    def eatPreBreak(self, toAppend):
        """
        If last element in self.result is a <br />, delete it.
        Then append toAppend to self.result
        """
        self.outAppend(toAppend, eatPreBreak=True)
#         if len(self.result) > 0 and self.result[-1].strip() == "<br />":
#             self.result[-1] = toAppend
#         else:
#             self.result.append(toAppend)


    def outEatBreaks(self, toAppend, **kpars):
        """
        Sets flags so that a <br /> before and/or after the item toAppend
        are eaten (removed) and appends toAppend to self.result
        """
        kpars["eatPreBreak"] = True
        kpars["eatPostBreak"] = True

        self.outAppend(toAppend, **kpars)


    def outIndentation(self, indType):
        """
        Insert indentation, bullet, or numbered list start tag.
        ind -- indentation depth
        """
        if indType == "normalindent" and self.asIntHtmlPreview:
            self.outEatBreaks(u"<blockquote>")
        else:
            tag = {"normalindent": u"<ul>", "ul": u"<ul>", "ol": u"<ol>"}[indType]

            if self.hasStates() or self.asIntHtmlPreview:
                # It is already indented, so additional indents will not
                # produce blank lines which must be eaten
                self.outAppend(tag)
            else:
                self.outEatBreaks(tag)

    def getOutput(self):
        return u"".join(self.result)
        
    def outTable(self, content, node):
        """
        Write out content of a table as HTML code
        """
        # TODO XML
        self.outAppend(u'<table border="2">\n')  # , eatPreBreak=True
        grid = node.calcGrid()
#         print "outTable1", repr(grid)
        for row in grid:
            self.outAppend(u"<tr>")
            for celltokens in row:
                self.outAppend(u"<td>")

#                 opts = self.optsStack[-1].copy()
#                 opts["checkIndentation"] = False
#                 self.optsStack.append(opts)
#                 self.processTokens(content, celltokens)
#                 del self.optsStack[-1]
                self.optsStack.push()
                self.optsStack["checkIndentation"] = False
                self.processTokens(content, celltokens)
                self.optsStack.pop()
                
                self.outAppend(u"</td>")
            self.outAppend(u"</tr>\n")

        self.outAppend(u'</table>\n', eatPostBreak=True)


    # TODO Process paragraph-wise formatting
    def resetConsecEmptyLineCount(self):
        if not self.paragraphMode or self.preMode:
            self.consecEmptyLineCount = 0
        else:
            if self.consecEmptyLineCount > 0:
                self.outAppend(u"<br />\n" * (self.consecEmptyLineCount + 1))
            
            self.consecEmptyLineCount = 0


    def incConsecEmptyLineCount(self):
        self.consecEmptyLineCount += 1

        if self.preMode:
            self.outAppend(u"\n")
        elif not self.paragraphMode:
            self.outAppend(u"<br />\n")


    def _processInsertion(self, insertionAstNode):
        """
        Process an insertion (e.g. "[:page:WikiWord]")
        """
        wordList = None
        content = None
        htmlContent = None
        key = insertionAstNode.key
        value = insertionAstNode.value
        wikiDocument = self.mainControl.getWikiDocument()

        if key == u"page":
            if (u"wikipage/" + value) in self.insertionVisitStack:
                # Prevent infinite recursion
                return

            docpage = wikiDocument.getWikiPageNoError(value)
            pageAst = docpage.getLivePageAst()
            
#             pageast = PageAst.Page()
#             pageast.buildAst(self.mainControl.getFormatting(), content,
#                     docpage.getFormatDetails())
            tokens = pageAst.getTokens()
            
            self.insertionVisitStack.append("wikipage/" + value)
            
            # Inside an inserted page we don't want anchors to the
            # headings to avoid collisions with headings of surrounding
            # page.
#             opts = self.optsStack[-1].copy()
#             opts["anchorForHeading"] = False
#             self.optsStack.append(opts)
#             self.processTokens(docpage.getLiveText(), tokens)
#             del self.optsStack[-1]
            
            self.optsStack.push()
            self.optsStack["anchorForHeading"] = False
            self.processTokens(docpage.getLiveText(), tokens)
            self.optsStack.pop()

            del self.insertionVisitStack[-1]

            return
            
        elif key == u"rel":
            # List relatives (children, parents)
            if value == u"parents":
                wordList = wikiDocument.getWikiData().getParentRelationships(
                        self.wikiWord)
            elif value == u"children":
                existingonly = (u"existingonly" in insertionAstNode.appendices) # or \
                        # (u"existingonly +" in insertionAstNode.appendices)
                wordList = wikiDocument.getWikiData().getChildRelationships(
                        self.wikiWord, existingonly=existingonly,
                        selfreference=False)
            elif value == u"parentless":
                wordList = wikiDocument.getWikiData().getParentlessWikiWords()
            elif value == u"undefined":
                wordList = wikiDocument.getWikiData().getUndefinedWords()
            elif value == u"top":
                htmlContent = u'<a href="#">Top</a>'
            elif value == u"back":
                if self.asHtmlPreview:
                    htmlContent = \
                            u'<a href="' + self._getInternaljumpPrefix() + \
                            u'action/history/back">Back</a>'
#                     htmlContent = \
#                             u'<a href="internaljump:action/history/back">Back</a>'
#                 elif self.exportType == u"html_previewMOZ":
#                     htmlContent = \
#                             u'<a href="file://internaljump/action/history/back">Back</a>'
                else:
                    htmlContent = \
                            u'<a href="javascript:history.go(-1)">Back</a>'


        elif key == u"savedsearch":
            datablock = wikiDocument.getWikiData().getSearchDatablock(value)
            if datablock is not None:
                searchOp = SearchReplaceOperation()
                searchOp.setPackedSettings(datablock)
                searchOp.replaceOp = False
                wordList = wikiDocument.searchWiki(searchOp)
        elif key == u"toc" and value == u"":
            pageAst = self.getBasePageAst()
            headtokens = [tok for tok in pageAst.getTokens() if tok.ttype in
                    (
                    WikiFormatting.FormatTypes.Heading15,
                    WikiFormatting.FormatTypes.Heading14,
                    WikiFormatting.FormatTypes.Heading13,
                    WikiFormatting.FormatTypes.Heading12,
                    WikiFormatting.FormatTypes.Heading11,
                    WikiFormatting.FormatTypes.Heading10,
                    WikiFormatting.FormatTypes.Heading9,
                    WikiFormatting.FormatTypes.Heading8,
                    WikiFormatting.FormatTypes.Heading7,
                    WikiFormatting.FormatTypes.Heading6,
                    WikiFormatting.FormatTypes.Heading5,
                    WikiFormatting.FormatTypes.Heading4, 
                    WikiFormatting.FormatTypes.Heading3,
                    WikiFormatting.FormatTypes.Heading2,
                    WikiFormatting.FormatTypes.Heading1)]

            unescapeNormalText = \
                    self.mainControl.getFormatting().unescapeNormalText

            htmlContent = [u'<div class="page-toc">\n']

            for tok in headtokens:
                styleno = tok.ttype
                headLevel = WikiFormatting.getHeadingLevel(styleno)

                headContent = tok.grpdict["h%iContent" % headLevel]
                if self.asIntHtmlPreview:
                    # Simple indent for internal preview
                    htmlContent.append(u"&nbsp;&nbsp;" * (headLevel - 1))
                else:
                    # use css otherwise
                    htmlContent.append(u'<div class="page-toc-level%i">' %
                            headLevel)
                
                if self.wordAnchor:
                    anchor = self.wordAnchor + (u"#.h%i" % tok.start)
                else:
                    anchor = u".h%i" % tok.start

                htmlContent.append(u'<a href="#%s">%s</a>' % (anchor,
                        escapeHtml(unescapeNormalText(headContent))))

                if self.asIntHtmlPreview:
                    htmlContent.append(u'<br />\n')
                else:
                    htmlContent.append(u'</div>\n')

#                 if headLevel > lastLevel:
#                     htmlContent.append(u"<ul>\n" * (headLevel - lastLevel))
#                 elif headLevel < lastLevel:
#                     htmlContent.append(u"</ul>\n" * (lastLevel - headLevel))
#                 lastLevel = headLevel
# 
#                 htmlContent.append(u'<li><a href="#.h%i">%s</a>\n' % (tok.start,
#                         escapeHtml(unescapeNormalText(headContent))))
#             
#             htmlContent.append(u"</ul>\n")



            htmlContent.append(u"</div>\n")
            htmlContent = u"".join(htmlContent)

        elif key == u"eval":
            if not self.mainControl.getConfig().getboolean("main",
                    "insertions_allow_eval", False):
                # Evaluation of such insertions not allowed
                content = _(u"<pre>[Allow evaluation of insertions in "
                        "\"Options\", page \"Security\", option "
                        "\"Process insertion scripts\"]</pre>")
            else:
                evalScope = {"pwiki": self.getMainControl(),
                        "lib": self.getMainControl().evalLib}
                expr = value
                if expr is None:
                    expr = insertionAstNode.quotedValue
                # TODO Test security
                try:
                    content = unicode(eval(re.sub(u"[\n\r]", u"", expr),
                            evalScope))
                except Exception, e:
                    s = StringIO()
                    traceback.print_exc(file=s)
                    content = u"\n<<\n" + s.getvalue() + u"\n>>\n"
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
                            insertionAstNode)
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
                                "wikidpad_language", insertionAstNode)
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

                for ap in insertionAstNode.appendices:
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
                            
                        wwNode = PageAst.WikiWord()
                        wwNode.buildNodeForWord(word)

                        self.outAppend(u'<td valign="top">')
                        self._processWikiWord(word, wwNode, None)
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
                        wwNode = PageAst.WikiWord()
                        wwNode.buildNodeForWord(word)

                        self._processWikiWord(word, wwNode, None)

                else:   # cols == 1 and not asList
                    firstWord = True
                    for word in wordList:
                        if firstWord:
                            firstWord = False
                        else:
                            self.outAppend("<br />\n")
                            
                        wwNode = PageAst.WikiWord()
                        wwNode.buildNodeForWord(word)

                        self.outAppend(u'<td valign="top">')
                        self._processWikiWord(word, wwNode, None)
                        self.outAppend(u'</td>')
                        
#                     content = u"\n".join([u"[" + word + u"]" for word in wordList])
                    
                return


        if content is not None:
            # Content was set, so use standard formatting rules to create
            # tokens out of it and process them
            pageast = PageAst.Page()
            docpage = wikiDocument.getWikiPageNoError(self.wikiWord)
            pageast.buildAst(self.mainControl.getFormatting(), content,
                    docpage.getFormatDetails())
            tokens = pageast.getTokens()

            self.processTokens(content, tokens)

        elif htmlContent is not None:
            self.outAppend(htmlContent)
            
            
    def _processWikiWord(self, tokenText, astNode, fullContent):
        word = astNode.nakedWord
        link = self.links.get(word)
        
        selfLink = False

        if link:
            wikiDocument = self.mainControl.getWikiDocument()
            wikiData = wikiDocument.getWikiData()
            # Test if link to same page itself (maybe with an anchor fragment)
            if not self.exportType in (u"html_single", u"xml"):
                linkTo = wikiData.getAliasesWikiWord(word)
                linkFrom = wikiData.getAliasesWikiWord(self.wikiWord)
                if linkTo == linkFrom:
                    # Page links to itself
                    selfLink = True

            # Add anchor fragment if present
            if astNode.anchorFragment:
                if selfLink:
                    # Page links to itself, so replace link URL
                    # by the anchor.
#                     if self.exportType in (u"html_previewIE", u"html_previewMOZ"):
#                         link = self._getInternaljumpPrefix() + \
#                                 "action/scroll/selfanchor/" + astNode.anchorFragment
#                     else:
                    link = u"#" + astNode.anchorFragment
                else:
                    link += u"#" + astNode.anchorFragment

            if self.asXml:   # TODO XML
                self.outAppend(u'<link type="wikiword">%s</link>' % 
                        escapeHtml(tokenText))
            else:
                title = None
                if wikiDocument.isDefinedWikiWord(word):
                    wikiWord = wikiData.getAliasesWikiWord(word)

                    propList = wikiData.getPropertiesForWord(wikiWord)
                    for key, value in propList:
                        if key == u"short_hint":
                            title = value
                            break

                if title is not None:
                    self.outAppend(u'<span class="wiki-link"><a href="%s" title="%s">' %
                            (link, escapeHtmlNoBreaks(title)))
                else:
                    self.outAppend(u'<span class="wiki-link"><a href="%s">' %
                            link)

                if astNode.titleTokens is not None:
                    self.optsStack.push()
                    self.optsStack["inWwOrUrlTitle"] = True
                    self.processTokens(fullContent, astNode.titleTokens)
                    self.optsStack.pop()
                else:
                    self.outAppend(escapeHtml(word))                        
                self.outAppend(u'</a></span>')
        else:
            if astNode.titleTokens is not None:
                self.processTokens(fullContent, astNode.titleTokens)
            else:
                self.outAppend(escapeHtml(tokenText))                        



    def formatContent(self, word, content, formatDetails, links=None,
            asXml=False):
        if links is None:
            self.links = {}
        else:
            self.links = links
 
        self.asIntHtmlPreview = (self.exportType == "html_previewWX")
        self.asHtmlPreview = self.exportType in ("html_previewWX",
                "html_previewIE", "html_previewMOZ")
        self.asXml = asXml
        self.wikiWord = word
        # Replace tabs with spaces (TODO Which problem did I want to solve here?)
        # content = content.replace(u"\t", u" " * 4)  # TODO Configurable
        self.result = []
        self.statestack = [("normalindent", 0)]
#         self.optsStack = [{}]
        self.optsStack = StackedCopyDict()
        self.insertionVisitStack = []
        self.outFlagEatPostBreak = False
        self.outFlagPostBreakEaten = False

        # deepness of numeric bullets
        self.numericdeepness = 0
        self.preMode = 0  # Count how many <pre> tags are open
        self.consecEmptyLineCount = 0
        self.paragraphMode = formatDetails.paragraphMode
        


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
 
        # TODO Without camel case
        page = PageAst.Page()
        page.buildAst(self.mainControl.getFormatting(), content, formatDetails)
        self.basePageAst = page

        if len(page.getTokens()) >= 1:
            if self.asHtmlPreview:
                facename = self.mainControl.getConfig().get(
                        "main", "facename_html_preview", u"")
                if facename:
                    self.outAppend('<font face="%s">' % facename)
            
            self.processTokens(content, page.getTokens())
            
            if self.asHtmlPreview and facename:
                self.outAppend('</font>')

        return self.getOutput()


    def processTokens(self, content, tokens):
        """
        Actual token to HTML converter. May be called recursively
        """

        # print "--processTokens1", repr(tokens)

        # Save state stack length so we do only pop states which were pushed
        # by this method (and not by some calling method which can in fact be
        # the same method because of recursion).

        stacklen = len(self.statestack)
        formatting = self.mainControl.getFormatting()
        unescapeNormalText = formatting.unescapeNormalText
        wikiDocument = self.mainControl.getWikiDocument()

        # Stores the indent of current line until it is used.
        # -1: indentation already processed

        lineIndentBuffer = 0

        for i in xrange(len(tokens)):
            tok = tokens[i]
            try:
                nexttok = tokens[i+1]
            except IndexError:
                nexttok = Token(WikiFormatting.FormatTypes.Default,
                    tok.start+len(tok.text), {}, u"")

            styleno = tok.ttype
            nextstyleno = nexttok.ttype

#             print "--processTokens4", repr((tok.text, self.statestack[-1]))

            if lineIndentBuffer > -1 and not self.preMode and not styleno in \
                    (WikiFormatting.FormatTypes.Numeric,
                    WikiFormatting.FormatTypes.Bullet,
                    WikiFormatting.FormatTypes.SuppressHighlight,
                    WikiFormatting.FormatTypes.Table,
                    WikiFormatting.FormatTypes.PreBlock,
                    WikiFormatting.FormatTypes.Newline,
                    WikiFormatting.FormatTypes.Indentation):

                # We have a not yet processed indentation (lineIndentBuffer > -1)
                # and are not in <pre> mode and the next token does neither
                # invalidate the indent buffer (FormatTypes.Newline
                # and Indentation) nor processes indentation itself
                # (the other token types above)
                # -> Adjust statestack

                # This line is not empty so reset counter
                # (which may close a paragraph and open a new one if necessary)
                self.resetConsecEmptyLineCount()

                while stacklen < len(self.statestack) and \
                        lineIndentBuffer < self.statestack[-1][1]:
                    # Current indentation is less than previous (stored
                    # on stack) so close open <ul> and <ol>
                    self.popState()

                if self.statestack[-1][0] == "normalindent" and \
                        lineIndentBuffer > self.statestack[-1][1]:
                    # More indentation than before -> open new indentation level
                    self.outIndentation("normalindent")
                    self.statestack.append(("normalindent", lineIndentBuffer))

                # Indentation process
                lineIndentBuffer = -1

            if styleno in (WikiFormatting.FormatTypes.Default,
                WikiFormatting.FormatTypes.EscapedChar):
                # Some sort of plain, unformatted text

                if styleno == WikiFormatting.FormatTypes.EscapedChar:
                    text = tok.node.unescaped
                else:
                    text = tok.text

                self.outAppend(escapeHtml(text))

            # if a known token RE matches:
            
            elif styleno == WikiFormatting.FormatTypes.Indentation:
                if not self.preMode and \
                        self.optsStack.get("checkIndentation", True):
                    lineIndentBuffer = measureIndent(tok.text)
                else:
                    self.outAppend(tok.text)
            elif styleno == WikiFormatting.FormatTypes.Newline:
                if not self.preMode and lineIndentBuffer > -1:
                    # Unprocessed indentation means empty line
                    self.incConsecEmptyLineCount()
                else:
                    if self.preMode:
                        self.outAppend(u"\n")
                    elif not self.paragraphMode:
                        self.outAppend(u"<br />\n")
                    else:
                        self.outAppend(u" ")

                lineIndentBuffer = 0
            elif styleno == WikiFormatting.FormatTypes.Bold:
                self.outAppend(u"<b>" + escapeHtml(
                        unescapeNormalText(tok.grpdict["boldContent"])) + u"</b>")
            elif styleno == WikiFormatting.FormatTypes.Italic:
                self.outAppend(u"<i>"+escapeHtml(
                        unescapeNormalText(tok.grpdict["italicContent"])) + u"</i>")
            elif styleno == WikiFormatting.FormatTypes.HtmlTag:
                if re.match(u"^<pre[ >]", tok.text.lower()):
                    self.preMode += 1
                elif re.match(u"^</pre[ >]", tok.text.lower()):
                    self.preMode = max(0, self.preMode - 1)
                # HTML tag -> export as is 
                self.outAppend(tok.text)
            elif styleno == WikiFormatting.FormatTypes.HtmlEntity:
                # HTML entity -> export as is  (TODO: This is bad for XML)
                self.outAppend(tok.text)
            elif WikiFormatting.getHeadingLevel(styleno):
                headLevel = WikiFormatting.getHeadingLevel(styleno)

                if self.optsStack.get("anchorForHeading", True):
                    if self.wordAnchor:
                        anchor = self.wordAnchor + (u"#.h%i" % tok.start)
                    else:
                        anchor = u".h%i" % tok.start

                    self.outAppend(u'<a name="%s"></a>' % anchor)

                headContent = tok.grpdict["h%iContent" % headLevel]
                # HTML only supports 6 heading levels
                boundHeadLevel = min(6, headLevel)
                self.outEatBreaks(u"<h%i>%s</h%i>\n" % (boundHeadLevel, escapeHtml(
                        unescapeNormalText(headContent)), boundHeadLevel))

            elif styleno == WikiFormatting.FormatTypes.HorizLine:
                self.outEatBreaks(u'<hr size="1" />\n')
            elif styleno == WikiFormatting.FormatTypes.Script:
                pass  # Hide scripts 
            elif styleno == WikiFormatting.FormatTypes.PreBlock:
                self.resetConsecEmptyLineCount()
                lineIndentBuffer = -1
                self.outAppend(u"<pre>%s</pre>" %
                        escapeHtmlNoBreaks(tok.grpdict["preContent"]), True,
                        not self.asIntHtmlPreview)
            elif styleno == WikiFormatting.FormatTypes.Anchor:
                if self.wordAnchor:
                    anchor = self.wordAnchor + u"#" + tok.grpdict["anchorValue"]
                else:
                    anchor = tok.grpdict["anchorValue"]

                self.outAppend(u'<a name="%s"></a>' % anchor)
            elif styleno == WikiFormatting.FormatTypes.Footnote:
                footnoteId = tok.grpdict["footnoteId"]
                fnAnchorTok = self.basePageAst.getFootnoteAnchorDict().get(
                        footnoteId)
                
                if fnAnchorTok is None:
                    self.outAppend(escapeHtml(tok.text))
                else:
                    if self.wordAnchor:
                        fnAnchor = self.wordAnchor + u"#.f" + _escapeAnchor(
                                footnoteId)
                    else:
                        fnAnchor = u".f" + _escapeAnchor(footnoteId)

                    if fnAnchorTok.start == tok.start:
                        # Current footnote token tok is an anchor (=last
                        # footnote token with this footnoteId)

                        self.outAppend(u'<a name="%s"></a>' % fnAnchor)
                        self.outAppend(escapeHtml(tok.text))
                    else:
                        # Current token is not an anchor -> make it a link.
                        self.outAppend(u'<a href="#%s">%s</a>' % (fnAnchor,
                        escapeHtml(tok.text)))
            elif styleno == WikiFormatting.FormatTypes.ToDo:
                node = tok.node
                namedelim = (node.name, node.delimiter)
                if self.asXml:
                    self.outAppend(u'<todo>%s%s' % namedelim)
                else:
                    self.outAppend(u'<span class="todo">%s%s' % namedelim)
                    
#                 print "processTodoToken", repr(node.valuetokens)

                self.processTokens(content, node.valuetokens)

                if self.asXml:
                    self.outAppend(u'</todo>')
                else:
                    self.outAppend(u'</span>')

            elif styleno == WikiFormatting.FormatTypes.Property:
                propKey = tok.node.key
                for propValue in tok.node.values:

                    if self.asXml:
                        self.outAppend( u'<property name="%s" value="%s"/>' % 
                                (escapeHtml(propKey),
                                escapeHtml(propValue)) )
                    else:
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

            elif styleno == WikiFormatting.FormatTypes.Insertion:
                self._processInsertion(tok.node)

            elif styleno == WikiFormatting.FormatTypes.Url:
                link = tok.node.url
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
                            stPath = self.wikiDataManager.getFileStorage().getStoragePath()
                            
                            isCont = testContainedInDir(stPath, absLink)
                            if isCont:
                                # File is in file storage -> add to
                                # referenced storage files                            
                                self.referencedStorageFiles.add(
                                        relativeFilePath(
                                        self.wikiDataManager.getWikiPath(),
                                        absLink))

                        # If export, reformat a bit
                        link = link[6:]
                else:
                    absUrl = link


                if self.asXml:   # TODO XML
                    self.outAppend(u'<link type="href">%s</link>' % 
                            escapeHtml(link))
                else:
                    lowerLink = link.lower()

                    # urlAsImage = False
                    if tok.node.containsModeInAppendix("l"):
                        urlAsImage = False
                    elif tok.node.containsModeInAppendix("i"):
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
                            lowerLink.endswith(".bmp"):
                        urlAsImage = True
                    else:
                        urlAsImage = False


                    if urlAsImage:
                        # Ignore title, use image
                        sizeInTag = u""

                        # Size info for direct setting in HTML code
                        sizeInfo = tok.node.getInfoForMode("s")
                        # Relative size info which modifies real image size
                        relSizeInfo = tok.node.getInfoForMode("r")

                        if sizeInfo is not None:
                            try:
                                widthStr, heightStr = sizeInfo.split(u"x")
                                if self.isHtmlSizeValue(widthStr) and \
                                        self.isHtmlSizeValue(heightStr):
                                    sizeInTag = ' width="%s" height="%s"' % \
                                            (widthStr, heightStr)
                            except:
                                # something does not match syntax requirements
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
                        alignInfo = tok.node.getInfoForMode("a")
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
#                             p = urllib.url2pathname(link)  # TODO Relative URLs
                            p = pathnameFromUrl(link)  # TODO Relative URLs
                            link = wx.FileSystem.FileNameToURL(p)
                        self.outAppend(u'<img src="%s" alt="" border="0"%s%s />' % 
                                (link, sizeInTag, alignInTag))
                    else:
                        if not self.optsStack.get("inWwOrUrlTitle", False):
                            # If we would be in a title, only image urls are allowed
                            self.outAppend(u'<span class="url-link"><a href="%s">' % link)
                            if tok.node.titleTokens is not None:
                                self.optsStack.push()
                                self.optsStack["inWwOrUrlTitle"] = True
                                self.processTokens(content, tok.node.titleTokens)
                                self.optsStack.pop()
                            else:
                                self.outAppend(escapeHtml(link))                        
                            self.outAppend(u'</a></span>')

            elif styleno == WikiFormatting.FormatTypes.WikiWord:
                self._processWikiWord(tok.text, tok.node, content)
            elif styleno == WikiFormatting.FormatTypes.Numeric:
                # Numeric bullet
                numbers = len(tok.grpdict["preLastNumeric"].split(u"."))
                ind = splitIndent(tok.grpdict["indentNumeric"])[1]

                self.resetConsecEmptyLineCount()
                lineIndentBuffer = -1

                while ind < self.statestack[-1][1] and \
                        (self.statestack[-1][0] != "ol" or \
                        numbers < self.numericdeepness):
                    self.popState()

                while ind == self.statestack[-1][1] and \
                        self.statestack[-1][0] != "ol" and \
                        self.hasStates():
                    self.popState()

                if ind > self.statestack[-1][1] or \
                        self.statestack[-1][0] != "ol":
#                     self.outEatBreaks(u"<ol>")
                    self.outIndentation("ol")
                    self.statestack.append(("ol", ind))
                    self.numericdeepness += 1

                while numbers > self.numericdeepness:
#                     self.outEatBreaks(u"<ol>")
                    self.outIndentation("ol")
                    self.statestack.append(("ol", ind))
                    self.numericdeepness += 1
                    
                self.outAppend(u"<li />", True) # not self.asIntHtmlPreview)

            elif styleno == WikiFormatting.FormatTypes.Bullet:
                # Unnumbered bullet
                ind = splitIndent(tok.grpdict["indentBullet"])[1]
                
                self.resetConsecEmptyLineCount()
                lineIndentBuffer = -1

                while ind < self.statestack[-1][1]:
                    self.popState()

                while ind == self.statestack[-1][1] and \
                        self.statestack[-1][0] != "ul" and \
                        self.hasStates():
                    self.popState()

                if ind > self.statestack[-1][1] or \
                        self.statestack[-1][0] != "ul":
#                     self.outEatBreaks(u"<ul>")
                    self.outIndentation("ul")
                    self.statestack.append(("ul", ind))

                self.outAppend(u"<li />", True) # not self.asIntHtmlPreview)
            elif styleno == WikiFormatting.FormatTypes.SuppressHighlight:
                ind = splitIndent(tok.grpdict["suppressIndent"])[1]

                self.resetConsecEmptyLineCount()
                lineIndentBuffer = -1

                while ind < self.statestack[-1][1]:
                    self.popState()
                    
                while ind == self.statestack[-1][1] and \
                        self.statestack[-1][0] != "ul" and \
                        self.hasStates():
                    self.popState()

                if ind > self.statestack[-1][1] or \
                        self.statestack[-1][0] != "normalindent":
#                     self.outEatBreaks(u"<ul>")
                    self.outIndentation("normalindent")
                    self.statestack.append(("normalindent", ind))

#                 while self.statestack[-1][0] != "normalindent":
#                     self.popState()
                self.outAppend(escapeHtml(tok.grpdict["suppressContent"]))
            elif styleno == WikiFormatting.FormatTypes.Table:
                ind = splitIndent(tok.grpdict["tableBegin"])[1]
                
                self.resetConsecEmptyLineCount()
                lineIndentBuffer = -1
                
                while stacklen < len(self.statestack) and \
                        ind < self.statestack[-1][1]:
                    self.popState()
                    
                if ind > self.statestack[-1][1]: # or \
#                        self.statestack[-1][0] != "ul":
#                     self.outEatBreaks(u"<ul>")
                    self.outIndentation("normalindent")
                    self.statestack.append(("normalindent", ind))

                self.outTable(content, tok.node)

        while len(self.statestack) > stacklen:
            self.popState()




class TextExporter(AbstractExporter):
    """
    Exports raw text
    """
    def __init__(self, mainControl):
        AbstractExporter.__init__(self, mainControl)
        self.wordList = None
        self.exportDest = None
        self.convertFilename = removeBracketsFilename # lambda s: s   


    def getWikiDataManager(self):
        return self.wikiDataManager

    def getExportTypes(self, guiparent):
        """
        Return sequence of tuples with the description of export types provided
        by this object. A tuple has the form (<exp. type>,
            <human readable description>, <panel for add. options or None>)
        If panels for additional options must be created, they should use
        guiparent as parent
        """
        if guiparent:
            res = wx.xrc.XmlResource.Get()
            textPanel = res.LoadPanel(guiparent, "ExportSubText") # .ctrls.additOptions
        else:
            textPanel = None

        return (
            ("raw_files", 'Set of *.wiki files', textPanel),
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

            

    def export(self, wikiDataManager, wordList, exportType, exportDest,
            compatFilenames, addopt):
        """
        Run export operation.
        
        wikiDataManager -- WikiDataManager object
        wordList -- Sequence of wiki words to export
        exportType -- string tag to identify how to export
        exportDest -- Path to destination directory or file to export to
        compatFilenames -- Should the filenames be encoded to be lowest
                           level compatible
        addopt -- additional options returned by getAddOpt()
        """
        self.wikiDataManager = wikiDataManager
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
                wikiPage = self.wikiDataManager.getWikiPage(word)
                content = wikiPage.getLiveText()
                modified = wikiPage.getTimestamps()[0]
#                 content = self.wikiDataManager.getWikiData().getContent(word)
#                 modified = self.wikiDataManager.getWikiData().getTimestamps(word)[0]
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


    def getExportTypes(self, guiparent):
        """
        Return sequence of tuples with the description of export types provided
        by this object. A tuple has the form (<exp. type>,
            <human readable description>, <panel for add. options or None>)
        If panels for additional options must be created, they should use
        guiparent as parent
        """
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


        # TODO Make it better somehow
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
        

    def export(self, wikiDataManager, wordList, exportType, exportDest,
            compatFilenames, addOpt):
        """
        Run export operation.
        
        wikiDataManager -- WikiDataManager object
        wordList -- Sequence of wiki words to export
        exportType -- string tag to identify how to export
        exportDest -- Path to destination directory or file to export to
        compatFilenames -- Should the filenames be encoded to be lowest
                           level compatible
        addOpt -- additional options returned by getAddOpt()
        """
        self.wikiDataManager = wikiDataManager
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
                        page = self.wikiDataManager.getFuncPage(ft)
                        self.exportFile.write(page.getLiveText())

                        self.exportFile.write("\n%s\n" % self.separator)


                # Write saved searches
                if self.writeSavedSearches:
                    wikiData = self.wikiDataManager.getWikiData()
                    searchTitles = wikiData.getSavedSearchTitles()

                    for st in searchTitles:
                        self.exportFile.write(u"savedsearch/%s\n" % st)
                        datablock = wikiData.getSearchDatablock(st)
                        self.exportFile.write(base64BlockEncode(datablock))
                        
                        self.exportFile.write("\n%s\n" % self.separator)

                locale.setlocale(locale.LC_ALL, '')
                # Write actual wiki words
                sepCount = len(self.wordList) - 1  # Number of separators yet to write
                for word in self.wordList:
                    page = self.wikiDataManager.getWikiPage(word)

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
    return (HtmlXmlExporter(mainControl), TextExporter(mainControl),
            MultiPageTextExporter(mainControl))
    
