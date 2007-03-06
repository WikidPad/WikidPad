# from Enum import Enumeration
import sys, os, string, re, traceback, sets
from os.path import join, exists, splitext
from cStringIO import StringIO
import shutil
## from xml.sax.saxutils import escape
from time import localtime
import urllib_red as urllib

from wxPython.wx import *
import wxPython.xrc as xrc

from wxHelper import XrcControls


from WikiExceptions import WikiWordNotFoundException, ExportException
import WikiFormatting
from StringOps import *
from TempFileSet import TempFileSet

from SearchAndReplace import SearchReplaceOperation, ListWikiPagesOperation, \
        ListItemWithSubtreeWikiPagesNode

from Configuration import isUnicode

import WikiFormatting
import PageAst



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
        if oc < 65 or oc > 122 or (90 < oc < 97):
            if oc > 255:
                result.append("$%04x" % oc)
            else:
                result.append("=%02x" % oc)

#             result.append(u"%%%02x" % oc)
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
        return self.htmlXmlExporter.convertFilename(u"%s.html" % relUnAlias)



# TODO UTF-8 support for HTML? Other encodings?

class HtmlXmlExporter:
    def __init__(self, mainControl):
        """
        mainControl -- Currently PersonalWikiFrame object
        """

        self.mainControl = mainControl
        self.wikiData = None
        self.wordList = None
        self.exportDest = None
        self.styleSheet = "wikistyle.css"
        self.basePageAst = None
#         self.tokenizer = Tokenizer(
#                 WikiFormatting.CombinedHtmlExportRE, -1)
                
        self.exportType = None
        self.statestack = None
        # deepness of numeric bullets
        self.numericdeepness = None
        self.preMode = None  # Count how many <pre> tags are open
        self.links = None
        self.wordAnchor = None  # For multiple wiki pages in one HTML page, this contains the anchor
                # of the current word.
        self.tempFileSet = None
        self.convertFilename = removeBracketsFilename   # lambda s: mbcsEnc(s, "replace")[0]
        
        self.result = None
        
        # Flag to control how to push output into self.result
        self.outFlagEatPostBreak = False


    def getMainControl(self):
        return self.mainControl        
        
    def getExportTypes(self, guiparent):
        """
        Return sequence of tuples with the description of export types provided
        by this object. A tuple has the form (<exp. type>,
            <human readable description>, <panel for add. options or None>)
        If panels for additional options must be created, they should use
        guiparent as parent
        """
        if guiparent:
            res = xrc.wxXmlResource.Get()
            htmlPanel = res.LoadPanel(guiparent, "ExportSubHtml")
            ctrls = XrcControls(htmlPanel)
            config = self.mainControl.getConfig()

            ctrls.cbPicsAsLinks.SetValue(config.getboolean("main",
                    "html_export_pics_as_links"))
            ctrls.chTableOfContents.SetSelection(config.getint("main",
                    "export_table_of_contents"))

        else:
            htmlPanel = None
        
        return (
            (u"html_single", u'Single HTML page', htmlPanel),
            (u"html_multi", u'Set of HTML pages', htmlPanel),
            (u"xml", u'XML file', None)
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
            return (("XML files (*.xml)", "*.xml"),) 
        
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
        can be returned (normally the addoptpanel itself)
        """
        if addoptpanel is None:
            # Return default set in options
            config = self.mainControl.getConfig()

            return ( boolToInt(config.getboolean("main",
                    "html_export_pics_as_links")),
                    config.getint("main", "export_table_of_contents") )
        else:
            ctrls = XrcControls(addoptpanel)
            picsAsLinks = boolToInt(ctrls.cbPicsAsLinks.GetValue())
            tableOfContents = ctrls.chTableOfContents.GetSelection()

            return (picsAsLinks, tableOfContents)


    def export(self, wikiDataManager, wordList, exportType, exportDest,
            compatFilenames, addOpt):
        """
        Run export operation.
        
        wikiData -- WikiData object
        wordList -- Sequence of wiki words to export
        exportType -- string tag to identify how to export
        exportDest -- Path to destination directory or file to export to
        compatFilenames -- Should the filenames be encoded to be lowest
                           level compatible
        addOpt -- additional options returned by getAddOpt()
        """
        
#         print "export1", repr((pWiki, wikiDataManager, wordList, exportType, exportDest,
#             compatFilenames, addopt))
        
        self.wikiDataManager = wikiDataManager
        self.wikiData = self.wikiDataManager.getWikiData()

        self.wordList = wordList
        self.exportType = exportType
        self.exportDest = exportDest
        self.addOpt = addOpt

        if compatFilenames:
            self.convertFilename = removeBracketsToCompFilename
        else:
            self.convertFilename = removeBracketsFilename    # lambda s: mbcsEnc(s, "replace")[0]
            
        if exportType in (u"html_single", u"html_multi"):
            # We must prepare a temporary file set for HTML exports
            self.tempFileSet = TempFileSet()
            self.tempFileSet.setPreferredPath(self.exportDest)
            self.tempFileSet.setPreferredRelativeTo(self.exportDest)

        if exportType == u"html_single":
            startfile = self._exportHtmlSingleFile()
        elif exportType == u"html_multi":
            startfile = self._exportHtmlMultipleFiles()
        elif exportType == u"xml":
            startfile = self._exportXml()
            
        # Other supported types: html_previewWX, html_previewIE, html_previewMOZ

        if not compatFilenames:
            startfile = mbcsEnc(startfile)[0]

        wxGetApp().getInsertionPluginManager().taskEnd()

        if self.mainControl.getConfig().getboolean(
                "main", "start_browser_after_export") and startfile:
            os.startfile(startfile)

        self.tempFileSet.reset()
        self.tempFileSet = None


    def setWikiDataManager(self, wikiDataManager):
        self.wikiDataManager = wikiDataManager
        if self.wikiDataManager is None:
            self.wikiData = None
        else:
            self.wikiData = self.wikiDataManager.getWikiData()

    def getTempFileSet(self):
        return self.tempFileSet

    def _exportHtmlSingleFile(self):
        if len(self.wordList) == 1:
            self.exportType = u"html_multi"
            return self._exportHtmlMultipleFiles()

        outputFile = join(self.exportDest,
                self.convertFilename(u"%s.html" % self.mainControl.wikiName))
        self.styleSheet = "wikistyle.css"

        if exists(outputFile):
            os.unlink(outputFile)

        realfp = open(outputFile, "w")
        fp = utf8Writer(realfp, "replace")
        fp.write(self.getFileHeaderMultiPage(self.mainControl.wikiName))

        if self.addOpt[1] == 1:
            # Write a content tree at beginning
            rootPage = self.mainControl.getWikiDocument().getWikiPage(
                        self.mainControl.getWikiDocument().getWikiName())
            flatTree = rootPage.getFlatTree()

            fp.write((u'<h2>Table of Contents</h2>\n'
                    '%s%s<hr size="1"/>') %
                    (self.getContentTreeBody(flatTree, linkAsFragments=True),
                    u'<br />\n'*10))

        elif self.addOpt[1] == 2:
            # Write a content list at beginning
            fp.write((u'<h2>Table of Contents</h2>\n'
                    '%s%s<hr size="1"/>') %
                    (self.getContentListBody(linkAsFragments=True),
                    u'<br />\n'*10))
                    
        links = {}
#         notExport = sets.Set() # Cache to store all rejected words
#         wordSet = sets.Set(self.wordList)
# 
#         def addWord(word):
#             if word in links:
#                 return
#             if word in notExport:
#                 return
#                 
#             unAlias = self.wikiData.getAliasesWikiWord(word)
#             if unAlias not in wordSet:
#                 notExport.add(word)
#                 return
# 
#             wikiPage = self.wikiDataManager.getWikiPage(word)
#             if not self.shouldExport(word, wikiPage):
#                 notExport.add(word)
#                 return
#             
#             links[word] = u"#%s" % _escapeAnchor(unAlias)

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
#                 links = {}  # TODO Why links to all (even not exported) children?
#                 for relation in wikiPage.getChildRelationships(
#                         existingonly=True, selfreference=False):
#                     if not self.shouldExport(relation):
#                         continue
#                     # get aliases too
#                     relUnAlias = self.wikiData.getAliasesWikiWord(relation)
#                     # TODO Use self.convertFilename here?
#                     links[relation] = u"#%s" % _escapeAnchor(relUnAlias)
                    
                self.wordAnchor = _escapeAnchor(word)
                formattedContent = self.formatContent(word, content,
                        formatDetails, links)
                fp.write((u'<span class="wiki-name-ref">'+
                        u'[<a name="%s">%s</a>]</span><br /><br />'+
                        u'<span class="parent-nodes">parent nodes: %s</span>'+
                        u'<br />%s%s<hr size="1"/>') %
                        (self.wordAnchor, word,
                        self.getParentLinks(wikiPage, False), formattedContent,
                        u'<br />\n'*10))
            except Exception, e:
                traceback.print_exc()
                
        self.wordAnchor = None

        fp.write(self.getFileFooter())
        fp.reset()
        realfp.close() 
        self.copyCssFile(self.exportDest)
        return outputFile


    def _exportHtmlMultipleFiles(self):
        links = LinkCreatorForHtmlMultiPageExport(
                self.wikiDataManager.getWikiData(), self)
        self.styleSheet = "wikistyle.css"

        if self.addOpt[1] in (1,2):
            # Write a table of contents in html page "index.html"
            self.links = links

            # TODO Configurable name
            outputFile = join(self.exportDest, self.convertFilename(u"index.html"))
            try:
                if exists(outputFile):
                    os.unlink(outputFile)
    
                realfp = open(outputFile, "w")
                fp = utf8Writer(realfp, "replace")

                # TODO Factor out HTML header generation                
                fp.write(self._getGenericHtmlHeader(u"Table of Contents") + 
                        u"    <body>\n")
                if self.addOpt[1] == 1:
                    # Write a content tree
                    rootPage = self.mainControl.getWikiDocument().getWikiPage(
                                self.mainControl.getWikiDocument().getWikiName())
                    flatTree = rootPage.getFlatTree()
    
                    fp.write((u'<h2>Table of Contents</h2>\n'
                            '%s') %
                            (self.getContentTreeBody(flatTree, linkAsFragments=False),))
                elif self.addOpt[1] == 2:
                    # Write a content list
                    fp.write((u'<h2>Table of Contents</h2>\n'
                            '%s') %
                            (self.getContentListBody(linkAsFragments=False),))

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
        self.copyCssFile(self.exportDest)
        rootFile = join(self.exportDest, 
                self.convertFilename(u"%s.html" % self.wordList[0]))    #self.mainControl.wikiName))[0]
        return rootFile


    def _exportXml(self):
#         outputFile = join(self.exportDest,
#                 self.convertFilename(u"%s.xml" % self.mainControl.wikiName))

        outputFile = self.exportDest

        if exists(outputFile):
            os.unlink(outputFile)

        realfp = open(outputFile, "w")
        fp = utf8Writer(realfp, "replace")

        fp.write(u'<?xml version="1.0" encoding="utf-8" ?>')
        fp.write(u'<wiki name="%s">' % self.mainControl.wikiName)
        
        for word in self.wordList:
            wikiPage = self.wikiDataManager.getWikiPage(word)
            if not self.shouldExport(word, wikiPage):
                continue
                
            # Why localtime?
            modified, created = wikiPage.getTimestamps()
            created = localtime(float(created))
            modified = localtime(float(modified))
            
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
            if exists(outputFile):
                os.unlink(outputFile)

            realfp = open(outputFile, "w")
            fp = utf8Writer(realfp, "replace")
            
            wikiPage = self.wikiDataManager.getWikiPage(word)
            content = wikiPage.getLiveText()
            formatDetails = wikiPage.getFormatDetails()       
            fp.write(self.exportContentToHtmlString(word, content,
                    formatDetails, links, startFile, onlyInclude))
            fp.reset()        
            realfp.close()
        except Exception, e:
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

        if isUnicode():
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


    def _getGenericHtmlHeader(self, title):
        charSet = u"; charset=UTF-8"
        styleSheet = self.styleSheet
        config = self.mainControl.getConfig()
        docType = config.get("main", "html_header_doctype",
                'DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.0 Transitional//EN"')

        return u"""<!%(docType)s>
<html>
    <head>
        <meta http-equiv="content-type" content="text/html%(charSet)s">
        <title>%(title)s</title>
        <link type="text/css" rel="stylesheet" href="%(styleSheet)s">
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
            
        # Build tagstring
        bodytag = u" ".join((linkcol, alinkcol, vlinkcol, textcol, bgcol, bgimg))
        if len(bodytag) > 5:  # the 5 spaces
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
        return u"""<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.0 Transitional//EN">
<html>
    <head>
        <meta http-equiv="content-type" content="text/html">
        <title>%s</title>
        <link type="text/css" rel="stylesheet" href="wikistyle.css">
    </head>
    %s
""" % (wikiPage.getWikiWord(), self._getBodyTag(wikiPage))


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


    def copyCssFile(self, dir):
        if not exists(mbcsEnc(join(dir, 'wikistyle.css'))[0]):
            cssFile = mbcsEnc(join(self.mainControl.wikiAppDir, 'export', 'wikistyle.css'))[0]
            if exists(cssFile):
                shutil.copy(cssFile, dir)

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


    def outAppend(self, toAppend, eatPreBreak=False, eatPostBreak=False):
        """
        Append toAppend to self.result, maybe remove or modify it according to
        flags
        """
        if toAppend == u"":    # .strip()
            return

        if self.outFlagEatPostBreak and toAppend.strip() == "<br />":
            self.outFlagEatPostBreak = eatPostBreak
            return
        
        if eatPreBreak and len(self.result) > 0 and \
                self.result[-1].strip() == "<br />":
            self.result[-1] = toAppend
            self.outFlagEatPostBreak = eatPostBreak
            return
            
        self.outFlagEatPostBreak = eatPostBreak
        self.result.append(toAppend)
        

    # TODO Remove
    def eatPreBreak(self, toAppend):
        """
        If last element in self.result is a <br />, delete it.
        Then append toAppend to self.result
        """
        if len(self.result) > 0 and self.result[-1].strip() == "<br />":
            self.result[-1] = toAppend
        else:
            self.result.append(toAppend)


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
#                 print "outTable2", repr(celltokens)
                opts = self.optsStack[-1].copy()
                opts["checkIndentation"] = False
                self.optsStack.append(opts)
                self.processTokens(content, celltokens)
                del self.optsStack[-1]
                
                self.outAppend(u"</td>")
            self.outAppend(u"</tr>\n")

        self.outAppend(u'</table>\n', eatPostBreak=True)


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
            if ("wikipage/" + value) in self.insertionVisitStack:
                # Prevent infinite recursion
                return

            docpage = wikiDocument.getWikiPageNoError(value)
            content = docpage.getLiveText()

            pageast = PageAst.Page()
            pageast.buildAst(self.mainControl.getFormatting(), content,
                    docpage.getFormatDetails())
            tokens = pageast.getTokens()
            
            self.insertionVisitStack.append("wikipage/" + value)
            
            opts = self.optsStack[-1].copy()
            opts["anchorForHeading"] = False
            self.optsStack.append(opts)
            self.processTokens(content, tokens)
            del self.optsStack[-1]
            
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
                    (WikiFormatting.FormatTypes.Heading4, 
                    WikiFormatting.FormatTypes.Heading3,
                    WikiFormatting.FormatTypes.Heading2,
                    WikiFormatting.FormatTypes.Heading1)]

            unescapeNormalText = \
                    self.mainControl.getFormatting().unescapeNormalText

#             lastLevel = 1
#             htmlContent = [u"<ul>\n"]

            htmlContent = [u'<div class="page-toc">\n']

            for tok in headtokens:
                styleno = tok.ttype
                if styleno == WikiFormatting.FormatTypes.Heading4:
                    headLevel = 4
                elif styleno == WikiFormatting.FormatTypes.Heading3:
                    headLevel = 3
                elif styleno == WikiFormatting.FormatTypes.Heading2:
                    headLevel = 2
                elif styleno == WikiFormatting.FormatTypes.Heading1:
                    headLevel = 1

                headContent = tok.grpdict["h%iContent" % headLevel]
                if self.asIntHtmlPreview:
                    # Simple indent
                    htmlContent.append(u"&nbsp;&nbsp;" * (headLevel - 1))
                else:
                    # use css
                    htmlContent.append(u'<div class="page-toc-level%i">' %
                            headLevel)
                
                htmlContent.append(u'<a href="#.h%i">%s</a>' % (tok.start,
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
                content = "<pre>[Allow evaluation of insertions in "\
                        "\"Options\", page \"Security\", option "\
                        "\"Process insertion scripts\"]</pre>"
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
            handler = wxGetApp().getInsertionPluginManager().getHandler(self,
                    exportType, key)

            if handler is None and self.asHtmlPreview:
                # No handlert found -> try to find generic HTML preview handler
                exportType = "html_preview"
                handler = wxGetApp().getInsertionPluginManager().getHandler(self,
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
                handler = wxGetApp().getInsertionPluginManager().getHandler(self,
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
                # "columns 3" was set)
                cols = 1
                for ap in insertionAstNode.appendices:
                    if ap.startswith(u"columns "):
                        try:
                            v = int(ap[8:])
                            if v > 0:
                                cols = v
                                break
                        except ValueError:
                            pass
                self.mainControl.getCollator().sort(wordList)
    
                if cols > 1:
                    # We need a table for the wordlist
                    content = [u"<table>\n"]
                    colpos = 0
                    for word in wordList:
                        if colpos == 0:
                            # Start table row
                            content.append(u"<tr>")
                        
                        content.append(u'<td valign="top">[' + word + u"]</td>")
                        
                        colpos += 1
                        if colpos == cols:
                            # At the end of a row
                            colpos = 0
                            content.append(u"</tr> ")
                            
                    # Fill the last incomplete row with empty cells if necessary
                    if colpos > 0:
                        while colpos < cols:
                            content.append(u"<td></td>")
                            colpos += 1
    
                        content.append(u"</tr>\n")
                    
                    content.append(u"</table>")
                    content = u"".join(content)
                else:
                    content = u"\n".join([u"[" + word + u"]" for word in wordList])


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
        # Replace tabs with spaces
        content = content.replace(u"\t", u" " * 4)  # TODO Configurable
        self.result = []
        self.statestack = [("normalindent", 0)]
        self.optsStack = [{}]
        self.insertionVisitStack = []
        # deepness of numeric bullets
        self.numericdeepness = 0
        self.preMode = 0  # Count how many <pre> tags are open

        # TODO Without camel case
        page = PageAst.Page()
        page.buildAst(self.mainControl.getFormatting(), content, formatDetails)
        self.basePageAst = page

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
        stacklen = len(self.statestack)
        formatting = self.mainControl.getFormatting()
        unescapeNormalText = formatting.unescapeNormalText
        wikiDocument = self.mainControl.getWikiDocument()
        
        for i in xrange(len(tokens)):
            tok = tokens[i]
            try:
                nexttok = tokens[i+1]
            except IndexError:
                nexttok = Token(WikiFormatting.FormatTypes.Default,
                    tok.start+len(tok.text), {}, u"")

            styleno = tok.ttype
            nextstyleno = nexttok.ttype

            # print "formatContent", styleno, nextstyleno, repr(content[tok[0]:nexttok[0]])

            
            if styleno in (WikiFormatting.FormatTypes.Default,
                WikiFormatting.FormatTypes.EscapedChar,
                WikiFormatting.FormatTypes.SuppressHighlight):
                # Some sort of plain, unformatted text

                if styleno == WikiFormatting.FormatTypes.EscapedChar:
                    text = tok.node.unescaped
                elif styleno == WikiFormatting.FormatTypes.SuppressHighlight:
                    text = tok.grpdict["suppressContent"]
                else:
                    text = tok.text

                if self.optsStack[-1].get("checkIndentation", True):
                    # With indentation check, we have a complicated mechanism
                    # here to check indentation, indent and dedent tracking
                    # The simple version without checking below is used for
                    # tables (table cells, more precisely)
                    
                    # Normal text, maybe with newlines and indentation to process
                    lines = text.split(u"\n")

#                     if styleno == WikiFormatting.FormatTypes.EscapedChar:
#                         lines = [tok.node.unescaped]
#                     elif styleno == WikiFormatting.FormatTypes.SuppressHighlight:
#                         lines = [tok.node.unescaped]
                    
    
                    # Test if beginning of lines at beginning of a line in editor
                    if tok.start > 0 and content[tok.start - 1] != u"\n":
                        # if not -> output of the first, incomplete, line
                        self.outAppend(escapeHtml(lines[0]))
    #                     print "processTokens12", repr(lines[0])
                        del lines[0]
                        
                        if len(lines) >= 1:
                            # If further lines follow, break line
                            if not self.preMode:
                                self.outAppend(u"<br />\n")
                            else:
                                self.outAppend(u"\n")
    
                    if len(lines) >= 1:
                        # All 'lines' now begin at a new line in the editor
                        # and all but the last end at one
                        for line in lines[:-1]:
    #                         print "processTokens15", repr(line)
                            if line.strip() == u"":
                                # Handle empty line
                                if not self.preMode:
                                    self.outAppend(u"<br />\n")
                                else:
                                    self.outAppend(u"\n")
                                continue
                                
                            if not self.preMode:
                                line, ind = splitIndent(line)
        
                                while stacklen < len(self.statestack) and \
                                        ind < self.statestack[-1][1]:
                                    # Current indentation is less than previous (stored
                                    # on stack) so close open <ul> and <ol>
                                    self.popState()
        
        #                         print "normal1", repr(line), repr(self.statestack[-1][0]), ind, repr(self.statestack[-1][1])
                                if self.statestack[-1][0] == "normalindent" and \
                                        ind > self.statestack[-1][1]:
                                    # More indentation than before -> open new <ul> level
        #                             print "normal2"
                                    self.outIndentation("normalindent")
    
                                    self.statestack.append(("normalindent", ind))
                                    self.outAppend(escapeHtml(line))
                                    self.outAppend(u"<br />\n")
        
                                elif self.statestack[-1][0] in ("normalindent", "ol", "ul"):
                                    self.outAppend(escapeHtml(line))
                                    self.outAppend(u"<br />\n")
                            else:
                                self.outAppend(escapeHtml(line))
                                self.outAppend(u"\n")
                                
                        # Handle last line
                        # Some tokens have own indentation handling
                        # and last line is empty string in this case,
                        # do not handle last line if such token follows
                        if not nextstyleno in \
                                (WikiFormatting.FormatTypes.Numeric,
                                WikiFormatting.FormatTypes.Bullet,
                                WikiFormatting.FormatTypes.Suppress,   # TODO Suppress?
                                WikiFormatting.FormatTypes.Table,
                                WikiFormatting.FormatTypes.PreBlock):
    
                            line = lines[-1]
                            if not self.preMode:
                                line, ind = splitIndent(line)
                                
                                while stacklen < len(self.statestack) and \
                                        ind < self.statestack[-1][1]:
                                    # Current indentation is less than previous (stored
                                    # on stack) so close open <ul> and <ol>
                                    self.popState()
                                        
                                if self.statestack[-1][0] == "normalindent" and \
                                        ind > self.statestack[-1][1]:
                                    # More indentation than before -> open new <ul> level
                                    self.outIndentation("normalindent")
    #                                 self.outEatBreaks(u"<ul>")
                                    self.statestack.append(("normalindent", ind))
                                    self.outAppend(escapeHtml(line))
                                elif self.statestack[-1][0] in ("normalindent", "ol", "ul"):
                                    self.outAppend(escapeHtml(line))
                            else:
                                self.outAppend(escapeHtml(line))
                        
                            
                    # self.result.append(u"<br />\n")   # TODO <br />  ?
    
                    continue    # Next token
                else:     # Not checkIndentation
                    # This is really simple
                    self.outAppend(escapeHtml(text))
#                     if styleno == WikiFormatting.FormatTypes.EscapedChar:
#                         self.outAppend(escapeHtml(tok.node.unescaped))
#                     else:
#                         self.outAppend(escapeHtml(tok.text))

            
            
            # if a known token RE matches:
            
            if styleno == WikiFormatting.FormatTypes.Bold:
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
            elif styleno in (WikiFormatting.FormatTypes.Heading4, 
                    WikiFormatting.FormatTypes.Heading3,
                    WikiFormatting.FormatTypes.Heading2,
                    WikiFormatting.FormatTypes.Heading1):
                if styleno == WikiFormatting.FormatTypes.Heading4:
                    headLevel = 4
                elif styleno == WikiFormatting.FormatTypes.Heading3:
                    headLevel = 3
                elif styleno == WikiFormatting.FormatTypes.Heading2:
                    headLevel = 2
                elif styleno == WikiFormatting.FormatTypes.Heading1:
                    headLevel = 1

                if self.optsStack[-1].get("anchorForHeading", True):
                    if self.wordAnchor:
                        anchor = self.wordAnchor + (u"#.h%i" % tok.start)
                    else:
                        anchor = u".h%i" % tok.start

                    self.outAppend(u'<a name="%s"></a>' % anchor)

                headContent = tok.grpdict["h%iContent" % headLevel]
                self.outEatBreaks(u"<h%i>%s</h%i>\n" % (headLevel, escapeHtml(
                        unescapeNormalText(headContent)), headLevel))

            elif styleno == WikiFormatting.FormatTypes.HorizLine:
                self.outEatBreaks(u'<hr size="1" />\n')
            elif styleno == WikiFormatting.FormatTypes.Script:
                pass  # Hide scripts 
            elif styleno == WikiFormatting.FormatTypes.PreBlock:
                self.outEatBreaks(u"<pre>%s</pre>" %
                        escapeHtmlNoBreaks(tok.grpdict["preContent"]))
            elif styleno == WikiFormatting.FormatTypes.Anchor:
                if self.wordAnchor:
                    anchor = self.wordAnchor + u"#" + tok.grpdict["anchorValue"]
                else:
                    anchor = tok.grpdict["anchorValue"]

                self.outAppend(u'<a name="%s"></a>' % anchor)
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
                if self.asXml:
                    self.outAppend( u'<property name="%s" value="%s"/>' % 
                            (escapeHtml(tok.grpdict["propertyName"]),
                            escapeHtml(tok.grpdict["propertyValue"])) )
                else:
                    standardProperty = u"%s: %s" % (tok.grpdict["propertyName"],
                            tok.grpdict["propertyValue"])
                    standardPropertyMatching = \
                            not not self.proppattern.match(standardProperty)
                    # Output only for different truth values
                    if standardPropertyMatching != self.proppatternExcluding:
                        self.outAppend( u'<span class="property">[%s: %s]</span>' % 
                                (escapeHtml(tok.grpdict["propertyName"]),
                                escapeHtml(tok.grpdict["propertyValue"])) )

            elif styleno == WikiFormatting.FormatTypes.Insertion:
                self._processInsertion(tok.node)

            elif styleno == WikiFormatting.FormatTypes.Url:
                link = tok.node.url
                if link.startswith(u"rel://"):
                    # Relative URL
                    if self.asHtmlPreview:
                        # If preview, make absolute
                        link = self.mainControl.makeRelUrlAbsolute(link)
                    else:
                        # If export, reformat a bit
                        link = link[6:]

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
                            lowerLink.endswith(".png"):
                        urlAsImage = True
                    else:
                        urlAsImage = False
                        
                    
                    if urlAsImage:
                        # Ignore title, use image
                        sizeInTag = u""

                        sizeInfo = tok.node.getInfoForMode("s")
                        if sizeInfo is not None:
                            try:
                                width, height = sizeInfo.split(u"x")
                                width = int(width)
                                height = int(height)
                                if width >= 0 and height >= 0:
                                    sizeInTag = ' width="%i" height="%i"' % \
                                            (width, height)
                            except:
                                # something does not match syntax requirements
                                pass
                        
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
                            p = urllib.url2pathname(link)  # TODO Relative URLs
                            link = wxFileSystem.FileNameToURL(p)
                        self.outAppend(u'<img src="%s" border="0"%s%s />' % 
                                (escapeHtml(link), sizeInTag, alignInTag))
                    else:
#                         self.outAppend(u'<a href="%s">%s</a>' %
#                                 (escapeHtml(link), escapeHtml(link)))
                        self.outAppend(u'<span class="url-link"><a href="%s">' % link)
                        if tok.node.titleTokens is not None:
                            self.processTokens(content, tok.node.titleTokens)
                        else:
                            self.outAppend(escapeHtml(link))                        
                        self.outAppend(u'</a></span>')

            elif styleno == WikiFormatting.FormatTypes.WikiWord:  # or \
                    # styleno == WikiFormatting.FormatTypes.WikiWord2:
                word = tok.node.nakedWord # self.mainControl.getFormatting().normalizeWikiWord(tok.text)
                link = self.links.get(word)
                
                selfLink = False

                if link:
                    if not self.exportType in (u"html_single", u"xml"):
                        wikiData = wikiDocument.getWikiData()
                        linkTo = wikiData.getAliasesWikiWord(word)
                        linkFrom = wikiData.getAliasesWikiWord(self.wikiWord)
                        if linkTo == linkFrom:
                            # Page links to itself
                            selfLink = True

                    # Add anchor fragment if present
                    if tok.node.anchorFragment:
                        if selfLink:
                            # Page links to itself, so replace link URL
                            # by the anchor.
                            link = u"#" + tok.node.anchorFragment
                        else:
                            link += u"#" + tok.node.anchorFragment

                    if self.asXml:   # TODO XML
                        self.outAppend(u'<link type="wikiword">%s</link>' % 
                                escapeHtml(tok.text))
                    else:
                        self.outAppend(u'<span class="wiki-link"><a href="%s">' %
                                escapeHtml(link))
                        if tok.node.titleTokens is not None:
                            self.processTokens(content, tok.node.titleTokens)
                        else:
#                             self.outAppend(escapeHtml(tok.text))                        
                            self.outAppend(escapeHtml(word))                        
                        self.outAppend(u'</a></span>')
                else:
                    if tok.node.titleTokens is not None:
                        self.processTokens(content, tok.node.titleTokens)
                    else:
                        self.outAppend(escapeHtml(tok.text))                        

            elif styleno == WikiFormatting.FormatTypes.Numeric:
                # Numeric bullet
                numbers = len(tok.grpdict["preLastNumeric"].split(u"."))
                ind = splitIndent(tok.grpdict["indentNumeric"])[1]

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
                    
                self.eatPreBreak(u"<li />")

            elif styleno == WikiFormatting.FormatTypes.Bullet:
                # Numeric bullet
                ind = splitIndent(tok.grpdict["indentBullet"])[1]
                
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

                self.eatPreBreak(u"<li />")
            elif styleno == WikiFormatting.FormatTypes.Suppress:
                while self.statestack[-1][0] != "normalindent":
                    self.popState()
                self.outAppend(escapeHtml(tok.grpdict["suppressContent"]))
            elif styleno == WikiFormatting.FormatTypes.Table:
                ind = splitIndent(tok.grpdict["tableBegin"])[1]
                
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




class TextExporter:
    """
    Exports raw text
    """
    def __init__(self, mainControl):
        self.mainControl = mainControl
        self.wikiDataManager = None
        self.wordList = None
        self.exportDest = None
        self.convertFilename = removeBracketsFilename # lambda s: s   


    def getExportTypes(self, guiparent):
        """
        Return sequence of tuples with the description of export types provided
        by this object. A tuple has the form (<exp. type>,
            <human readable description>, <panel for add. options or None>)
        If panels for additional options must be created, they should use
        guiparent as parent
        """
        if guiparent:
            res = xrc.wxXmlResource.Get()
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
        
        wikiData -- WikiData object
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
    
                fp = open(outputFile, "wb")
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
                



class MultiPageTextExporter:
    """
    Exports in multipage text format
    """
    def __init__(self, mainControl):
        self.mainControl = mainControl
        self.wikiDataManager = None
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
        return (
                (u"multipage_text", "Multipage text", None),
                )


    def getExportDestinationWildcards(self, exportType):
        """
        If an export type is intended to go to a file, this function
        returns a (possibly empty) sequence of tuples
        (wildcard description, wildcard filepattern).
        
        If an export type goes to a directory, None is returned
        """
        if exportType == u"multipage_text":
            return (("Multipage files (*.mpt)", "*.mpt"),
                    ("Text file (*.txt)", "*.txt")) 

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
        return ()


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
        # Try dashes
        sep = u"------"
        
        while len(sep) < 11:
            if self._checkPossibleSeparator(sep):
                return sep
            sep += u"-"

        # Try dots
        sep = u"...."
        while len(sep) < 11:
            if self._checkPossibleSeparator(sep):
                return sep
            sep += u"."
            
        # Try random strings (5 tries)
        for i in xrange(5):
            sep = u"-----%s-----" % createRandomString(20)
            if self._checkPossibleSeparator(sep):
                return sep

        # Give up
        return None            
        

    def export(self, wikiDataManager, wordList, exportType, exportDest,
            compatFilenames, addOpt):
        """
        Run export operation.
        
        wikiData -- WikiData object
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
        
        # The hairy thing first: find a separator that doesn't appear
        # as a line in one of the pages to export
        self.separator = self._findSeparator()
        if self.separator is None:
            # _findSeparator gave up
            raise ExportException("No usable separator found")
        try:
            try:
                self.rawExportFile = open(self.exportDest, "w")
    
                # Only UTF-8 mode currently
                self.rawExportFile.write(BOM_UTF8)
                self.exportFile = utf8Writer(self.rawExportFile, "replace")
                
                # Identifier line with file format
                self.exportFile.write("Multipage text format 0\n")
                # Separator line
                self.exportFile.write("Separator: %s\n" % self.separator)
    
                sepCount = len(self.wordList) - 1  # Number of separators yet to write
                for word in self.wordList:
                    self.exportFile.write("%s\n" % word)
                    page = self.wikiDataManager.getWikiPage(word)
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
    
