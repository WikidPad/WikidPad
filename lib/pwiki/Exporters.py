# from Enum import Enumeration
import WikiFormatting
# import re
import os
from os.path import join, exists
import sys
import shutil
## from xml.sax.saxutils import escape
from time import localtime
import urllib_red as urllib


import WikiData
import WikiFormatting
from StringOps import mbcsWriter, utf8Writer, utf8Enc, mbcsEnc, strToBool, \
        Tokenizer, BOM_UTF8

from wxPython.wx import *
import wxPython.xrc as xrc

from wxHelper import XrcControls



## Copied from xml.sax.saxutils and modified to reduce dependencies
def escape(data):
    """
    Escape &, <, and > in a unicode string of data.
    """

    # must do ampersand first

#     data = data.replace(u"&", u"&amp;")
#     data = data.replace(u">", u"&gt;")
#     data = data.replace(u"<", u"&lt;")
#     data = data.replace(u"\n", u"<br />")   # ?
#     return data
    return data.replace(u"&", u"&amp;").replace(u">", u"&gt;").\
            replace(u"<", u"&lt;").replace(u"\n", u"<br />")


def splitIndent(text):
    pl = len(text)
    text = text.lstrip()
    return (text, pl-len(text))
        


# TODO UTF-8 support for HTML? Other encodings?

class HtmlXmlExporter:
    def __init__(self):
        self.pWiki = None
        self.wikiData = None
        self.wordList = None
        self.exportDest = None
        self.tokenizer = Tokenizer(
                WikiFormatting.CombinedHtmlExportWithCamelCaseRE, -1)
                
        self.result = None
        self.statestack = None
        # deepness of numeric bullets
        self.numericdeepness = None
        self.convertFilename = lambda s: s   # lambda s: mbcsEnc(s, "replace")[0]


    def getExportTypes(self, guiparent):
        """
        Return sequence of tuples with the description of export types provided
        by this object. A tuple has the form (<exp. type>,
            <human readbale description>, <panel for add. options or None>)
        If panels for additional options must be created, they should use
        guiparent as parent
        """
        return (
            (u"html_single", u'Single HTML page', None),
            (u"html_multi", u'Set of HTML pages', None),
            (u"xml", u'XML file', None)
            )


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

            
    def export(self, pWiki, wikiData, wordList, exportType, exportDest,
            addopt):
        """
        Run export operation.
        
        pWiki -- PersonalWikiFrame object
        wikiData -- WikiData object
        wordList -- Sequence of wiki words to export
        exportType -- string tag to identify how to export
        exportDest -- Path to destination directory or file to export to
        addopt -- additional options returned by getAddOpt()
        """
        
        self.pWiki = pWiki
        self.wikiData = wikiData # self.pWiki.wikiData
        self.wordList = wordList
        self.exportDest = exportDest
        
#         if compatFilenames:
#             self.convertFilename = unicodeToCompFilename
#         else:
 #            self.convertFilename = lambda s: s    # lambda s: mbcsEnc(s, "replace")[0]
        
        if exportType == u"html_single":
            startfile = self.exportHtmlSingleFile()
        elif exportType == u"html_multi":
            startfile = self.exportHtmlMultipleFiles()
        elif exportType == u"xml":
            startfile = self.exportXml()
            
            
#         if not compatFilenames:
#             startfile = mbcsEnc(startfile)[0]
            
        if self.pWiki.configuration.getboolean(
                "main", "start_browser_after_export") and startfile:
            os.startfile(startfile)



    def exportHtmlSingleFile(self):
        if len(self.wordList) == 1:
            return self.exportHtmlMultipleFiles()

        outputFile = join(self.exportDest,
                self.convertFilename(u"%s.html" % self.pWiki.wikiName))

        if exists(outputFile):
            os.unlink(outputFile)

        realfp = open(outputFile, "w")
        fp = utf8Writer(realfp, "replace")
        fp.write(self.getFileHeader(self.pWiki.wikiName))
        
        for word in self.wordList:
            wikiPage = self.wikiData.getPage(word, toload=[""])
            if not self.shouldExport(word, wikiPage):
                continue
            
            try:
                content = wikiPage.getContent()
                links = {}
                for relation in wikiPage.getChildRelationships(
                        existingonly=True, selfreference=False):
                    if not self.shouldExport(relation):
                        continue
                    # get aliases too
                    relation = self.wikiData.getAliasesWikiWord(relation)
                        # TODO Use self.convertFilename here?
                    links[relation] = u"#%s" % relation
                    
                formattedContent = self.formatContent(word, content, links)
                fp.write((u'<span class="wiki-name-ref">'+
                        u'[<a name="%s">%s</a>]</span><br><br>'+
                        u'<span class="parent-nodes">parent nodes: %s</span>'+
                        u'<br>%s%s<hr size="1"/>') %
                        (word, word, self.getParentLinks(wikiPage, False),
                        formattedContent, u'<br />\n'*10))
            except Exception, e:
                pass

        fp.write(self.getFileFooter())
        fp.reset()        
        realfp.close()        
        self.copyCssFile(self.exportDest)
        return outputFile


    def exportHtmlMultipleFiles(self):
        for word in self.wordList:
            wikiPage = self.wikiData.getPage(word, toload=[""])
            if not self.shouldExport(word, wikiPage):
                continue

            links = {}
            for relation in wikiPage.getChildRelationships(
                    existingonly=True, selfreference=False):
                if not self.shouldExport(relation):
                    continue
                # get aliases too
                relation = self.wikiData.getAliasesWikiWord(relation)
                links[relation] = self.convertFilename(u"#%s" % relation)
#                 wordForAlias = self.wikiData.getAliasesWikiWord(relation)
#                 if wordForAlias:
#                     links[relation] = self.convertFilename(
#                             u"%s.html" % wordForAlias)
#                 else:
#                     links[relation] = self.convertFilename(
#                             u"%s.html" % relation)
                                
            self.exportWordToHtmlPage(self.exportDest, word, links, False)
        self.copyCssFile(self.exportDest)
        rootFile = join(self.exportDest, 
                self.convertFilename(u"%s.html" % self.wordList[0]))    #self.pWiki.wikiName))[0]
        return rootFile


    def exportXml(self):
        outputFile = join(self.exportDest,
                self.convertFilename(u"%s.xml" % self.pWiki.wikiName))

        if exists(outputFile):
            os.unlink(outputFile)

        realfp = open(outputFile, "w")
        fp = utf8Writer(realfp, "replace")

        fp.write(u'<?xml version="1.0" encoding="utf-8" ?>')
        fp.write(u'<wiki name="%s">' % self.pWiki.wikiName)
        
        for word in self.wordList:
            wikiPage = self.wikiData.getPage(word, toload=[""])
            if not self.shouldExport(word, wikiPage):
                continue
                
            # Why localtime?
            modified, created = wikiPage.getWikiWordInfo()
            created = localtime(float(created))
            modified = localtime(float(modified))
            
            fp.write(u'<wikiword name="%s" created="%s" modified="%s">' %
                    (word, created, modified))

            try:
                content = wikiPage.getContent()
                links = {}
                for relation in wikiPage.getChildRelationships(
                        existingonly=True, selfreference=False):
                    if not self.shouldExport(relation):
                        continue

                    # get aliases too
                    relation = self.wikiData.getAliasesWikiWord(relation)
                    links[relation] = u"#%s" % relation
#                     wordForAlias = self.wikiData.getAliasesWikiWord(relation)
#                     if wordForAlias:
#                         links[relation] = u"#%s" % wordForAlias
#                     else:
#                         links[relation] = u"#%s" % relation
                    
                formattedContent = self.formatContent(word, content, links, asXml=True)
                fp.write(formattedContent)

            except Exception, e:
                pass

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
            
            wikiPage = self.wikiData.getPage(word, toload=[""])
            content = wikiPage.getContent()            
            fp.write(self.exportContentToHtmlString(word, content, links, startFile,
                    onlyInclude))
            fp.reset()        
            realfp.close()
        except NotImplementedError: # Exception, e:    !!!!!!!!!!
            pass
        
        return outputFile


    def exportContentToHtmlString(self, word, content, links=None, startFile=True,
            onlyInclude=None, asHtmlPreview=False):
        """
        Read content of wiki word word, create an HTML page and return it
        """
        result = []
        
        formattedContent = self.formatContent(word, content, links,
                asHtmlPreview=asHtmlPreview)
        result.append(self.getFileHeader(word))
        # if startFile is set then this is the only page being exported so
        # do not include the parent header.
        if not startFile:
            wikiPage = self.wikiData.getPage(word, toload=[""])
            result.append(u'<span class="parent-nodes">parent nodes: %s</span>'
                    % self.getParentLinks(wikiPage, True, onlyInclude))

        result.append(formattedContent)
        result.append(self.getFileFooter())
        
        return u"".join(result)

            
    def getFileHeader(self, title):
        return u"""<html>
    <head>
        <meta http-equiv="content-type" content="text/html; charset=UTF-8">
        <title>%s</title>
         <link type="text/css" rel="stylesheet" href="wikistyle.css">
    </head>
    <body>
""" % title


    def getFileFooter(self):
        return u"""    </body>
</html>
"""

    def getParentLinks(self, wikiPage, asHref=True, wordsToInclude=None):
        parents = u""
        parentRelations = wikiPage.getParentRelationships()[:]
        parentRelations.sort()
        
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
                (relation, relation)
                
        return parents


    def copyCssFile(self, dir):
        if not exists(mbcsEnc(join(dir, 'wikistyle.css'))[0]):
            cssFile = mbcsEnc(join(self.pWiki.wikiAppDir, 'export', 'wikistyle.css'))[0]
            if exists(cssFile):
                shutil.copy(cssFile, dir)

    def shouldExport(self, wikiWord, wikiPage=None):
        if not wikiPage:
            try:
                wikiPage = self.wikiData.getPage(wikiWord, toload=[""])
            except WikiData.WikiWordNotFoundException:
                return False
            
        #print "shouldExport", mbcsEnc(wikiWord)[0], repr(wikiPage.props.get("export", ("True",))), \
         #       type(wikiPage.props.get("export", ("True",)))
            
        return strToBool(wikiPage.getProperties().get("export", ("True",))[0])


    def popState(self):
        if self.statestack[-1][0] == "normalindent":
            self.result.append(u"</ul>\n")
        elif self.statestack[-1][0] == "ol":
            self.result.append(u"</ol>\n")
            self.numericdeepness -= 1
        elif self.statestack[-1][0] == "ul":
            self.result.append(u"</ul>\n")
            
        self.statestack.pop()
        
    def hasStates(self):
        """
        Return true iff more than the basic state is on the state stack yet.
        """
        return len(self.statestack) > 1
        

    def formatContent(self, word, content, links=None, asXml=False,
            asHtmlPreview=False):
        if links is None:
            links = {}
        # Replace tabs with spaces
        content = content.replace(u"\t", u" " * 4)  # TODO Configurable
#         # Replace &, <, > with entities
#         content = escape(content)
        self.result = []
        self.statestack = [("normalindent", 0)]
        # deepness of numeric bullets
        self.numericdeepness = 0
        
        # TODO Without camel case
        tokens = self.tokenizer.tokenize(content, sync=True)
        
        if len(tokens) >= 2:
            tok = tokens[0]

            if asHtmlPreview:
                facename = self.pWiki.configuration.get(
                        "main", "facename_html_preview", u"")
                if facename:
                    self.result.append('<font face="%s">' % facename)
            
            for nexttok in tokens[1:]:
                stindex = tok[1]
                if stindex == -1:  # == no token RE matches
                    # Normal text, maybe with newlines and indentation to process
                    lines = content[tok[0]:nexttok[0]].split(u"\n")
                    
                    # Test if beginning of lines at beginning of a line in editor
                    if tok[0] > 0 and content[tok[0] - 1] != u"\n":
                        # if not -> output of the first, incomplete, line
                        self.result.append(escape(lines[0]))
                        del lines[0]
                        
                    # All 'lines' now begin at a new line in the editor
                    for line in lines:
                        if line.strip() == u"":
                            # Handle empty line
                            self.result.append(u"<br />\n")
                            continue

                        line, ind = splitIndent(line)
                        
                        while ind < self.statestack[-1][1]:
                            # Current indentation is less than previous (stored
                            # on stack) so close open <ul> and <ol>
                            self.popState()
                                
                        if self.statestack[-1][0] == "normalindent" and \
                                ind > self.statestack[-1][1]:
                            # More indentation than before -> open new <ul> level
                            self.result.append(u"<ul>")
                            self.statestack.append(("normalindent", ind))
                            self.result.append(u"<br />\n"+escape(line))
                        elif self.statestack[-1][0] in ("normalindent", "ol", "ul"):
                            self.result.append(u"<br />\n" + escape(line))
                            
                    # self.result.append(u"<br />\n")   # TODO <br />  ?

                    tok = nexttok
                    continue    # Next token
                
                
                # if a known token RE matches:
                
                styleno = WikiFormatting.HtmlExportExpressions[stindex][1]
                if styleno == WikiFormatting.FormatTypes.Bold:
                    self.result.append(u"<b>" + escape(tok[2]["boldContent"]) + u"</b>")
                elif styleno == WikiFormatting.FormatTypes.Italic:
                    self.result.append(u"<i>"+escape(tok[2]["italicContent"]) + u"</i>")
                elif styleno == WikiFormatting.FormatTypes.Heading4:
                    self.result.append(u"<h4>%s</h4>" % escape(tok[2]["h4Content"]))
                elif styleno == WikiFormatting.FormatTypes.Heading3:
                    self.result.append(u"<h3>%s</h3>" % escape(tok[2]["h3Content"]))
                elif styleno == WikiFormatting.FormatTypes.Heading2:
                    self.result.append(u"<h2>%s</h2>" % escape(tok[2]["h2Content"]))
                elif styleno == WikiFormatting.FormatTypes.Heading1:
                    self.result.append(u"<h1>%s</h1>" % escape(tok[2]["h1Content"]))
                elif styleno == WikiFormatting.FormatTypes.HorizLine:
                    self.result.append(u'<hr size="1" />\n')
                elif styleno == WikiFormatting.FormatTypes.Script:
                    pass  # Hide scripts                
                elif styleno == WikiFormatting.FormatTypes.ToDo:
                    if asXml:
                        self.result.append(u'<todo>%s</todo>' % 
                                escape(tok[2]["todoContent"]))
                    else:
                        self.result.append(u'<span class="todo">%s</span><br />' % 
                                escape(tok[2]["todoContent"]))
                elif styleno == WikiFormatting.FormatTypes.Property:
                    if asXml:
                        self.result.append( u'<property name="%s" value="%s"/>' % 
                                (escape(tok[2]["propertyName"]),
                                escape(tok[2]["propertyValue"])) )
                    else:
                        self.result.append( u'<span class="property">[%s: %s]</span>' % 
                                (escape(tok[2]["propertyName"]),
                                escape(tok[2]["propertyValue"])) )
                elif styleno == WikiFormatting.FormatTypes.Url:
                    link = content[tok[0]:nexttok[0]]
                    if asXml:
                        self.result.append(u'<link type="href">%s</link>' % 
                                escape(link))
                    else:
                        lowerLink = link.lower()
                        if lowerLink.endswith(".jpg") or \
                                lowerLink.endswith(".gif") or \
                                lowerLink.endswith(".png"):
                            if asHtmlPreview and lowerLink.startswith("file:"):
                                # At least under Windows, wxWidgets has another
                                # opinion how a local file URL should look like
                                # than Python
                                p = urllib.url2pathname(link)  # TODO Relative URLs
                                link = wxFileSystem.FileNameToURL(p)
                            self.result.append(u'<img src="%s" border="0" />' % 
                                    escape(link))
                        else:
                            self.result.append(u'<a href="%s">%s</a>' %
                                    (escape(link), escape(link)))
                elif styleno == WikiFormatting.FormatTypes.WikiWord or \
                        styleno == WikiFormatting.FormatTypes.WikiWord2:
                    word = WikiFormatting.normalizeWikiWord(
                            content[tok[0]:nexttok[0]])
                    link = links.get(word)
                    
                    if link:
                        if asXml:
                            self.result.append(u'<link type="wikiword">%s</link>' % 
                                    escape(word))
                        else:
                            if word.startswith("["):
                                word = word[1:len(word)-1]
                            self.result.append(u'<a href="%s">%s</a>' %
                                    (link, word))
                    else:
                        self.result.append(word)
                elif styleno == WikiFormatting.FormatTypes.Numeric:
                    # Numeric bullet
                    numbers = len(tok[2]["preLastNumeric"].split(u"."))
                    ind = splitIndent(tok[2]["indentNumeric"])[1]
                    
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
                        self.result.append(u"<ol>")
                        self.statestack.append(("ol", ind))
                        self.numericdeepness += 1

                    while numbers > self.numericdeepness:
                        self.result.append(u"<ol>")
                        self.statestack.append(("ol", ind))
                        self.numericdeepness += 1
                        
                    self.result.append(u"<li />")
                elif styleno == WikiFormatting.FormatTypes.Bullet:
                    # Numeric bullet
                    ind = splitIndent(tok[2]["indentBullet"])[1]
                    
                    while ind < self.statestack[-1][1]:
                        self.popState()
                        
                    while ind == self.statestack[-1][1] and \
                            self.statestack[-1][0] != "ul" and \
                            self.hasStates():
                        self.popState()

                    if ind > self.statestack[-1][1] or \
                            self.statestack[-1][0] != "ul":
                        self.result.append(u"<ul>")
                        self.statestack.append(("ul", ind))

                    self.result.append(u"<li />")
                elif styleno == WikiFormatting.FormatTypes.Suppress:
                    while self.statestack[-1][0] != "normalindent":
                        self.popState()
                    self.result.append(escape(tok[2]["suppressContent"]))
                elif styleno == WikiFormatting.FormatTypes.Default:
#                     while self.statestack[-1][0] != "normalindent":
#                         self.popState()
                    self.result.append(escape(content[tok[0]:nexttok[0]]))

                tok = nexttok
                
            while len(self.statestack) > 1:
                self.popState()
                
            if asHtmlPreview and facename:
                self.result.append('</font>')


        return u"".join(self.result)


class TextExporter:
    """
    Exports raw text
    """
    def __init__(self):
        self.pWiki = None
        self.wikiData = None
        self.wordList = None
        self.exportDest = None
        self.convertFilename = lambda s: s   # lambda s: mbcsEnc(s, "replace")[0]


    def getExportTypes(self, guiparent):
        """
        Return sequence of tuples with the description of export types provided
        by this object. A tuple has the form (<exp. type>,
            <human readable desctiption>, <panel for add. options or None>)
        If panels for additional options must be created, they should use
        guiparent as parent
        """
        
        res = xrc.wxXmlResource.Get()
        
#         self.additOptions = wxPanel(self)
#         res.AttachUnknownControl("additOptions", self.additOptions, self)

        textPanel = res.LoadPanel(guiparent, "ExportSubText") # .ctrls.additOptions
        
        return (
            ("raw_files", 'Set of *.wiki files', textPanel),
            )


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
        ctrls = XrcControls(addoptpanel)
        
        # Which encoding:
        # 0:System standard, 1:utf-8 with BOM, 2: utf-8 without BOM

        return (ctrls.chTextEncoding.GetSelection(),)

            

    def export(self, pWiki, wikiData, wordList, exportType, exportDest,
            addopt):
        """
        Run export operation.
        
        pWiki -- PersonalWikiFrame object
        wikiData -- WikiData object
        wordList -- Sequence of wiki words to export
        exportType -- string tag to identify how to export
        exportDest -- Path to destination directory or file to export to
        addopt -- additional options returned by getAddOpt()
        """
        self.pWiki = pWiki
        self.wikiData = wikiData # self.pWiki.wikiData
        self.wordList = wordList
        self.exportDest = exportDest
        
#         if compatFilenames:
#             self.convertFilename = unicodeToCompFilename
#         else:
#             self.convertFilename = lambda s: s    # lambda s: mbcsEnc(s, "replace")[0]
         
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
                content, modified = self.wikiData.getContentAndInfo(word)[:2]
            except:
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
                continue


def describeExporters():
    return (HtmlXmlExporter(), TextExporter())
    
