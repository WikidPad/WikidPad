# from Enum import Enumeration
import WikiFormatting
import srePersistent as re
import os, string
from os.path import join, exists, splitext
import sys
import shutil
## from xml.sax.saxutils import escape
from time import localtime
import urllib_red as urllib


from StringOps import *

from WikiExceptions import WikiWordNotFoundException
import WikiFormatting
import PageAst

from wxPython.wx import *
import wxPython.xrc as xrc

from wxHelper import XrcControls


def removeBracketsToCompFilename(fn):
    """
    Combine unicodeToCompFilename() and removeBracketsFilename() from StringOps
    """
    return unicodeToCompFilename(removeBracketsFilename(fn))



# TODO UTF-8 support for HTML? Other encodings?

class HtmlXmlExporter:
    def __init__(self):
        self.pWiki = None
        self.wikiData = None
        self.wordList = None
        self.exportDest = None
#         self.tokenizer = Tokenizer(
#                 WikiFormatting.CombinedHtmlExportRE, -1)
                
        self.result = None
        self.statestack = None
        # deepness of numeric bullets
        self.numericdeepness = None
        self.links = None
        self.convertFilename = removeBracketsFilename   # lambda s: mbcsEnc(s, "replace")[0]
        
        self.result = None
        
        # Flag to control how to push output into self.result
        self.outFlagEatPostBreak = False

        
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
            compatFilenames, addopt):
        """
        Run export operation.
        
        pWiki -- PersonalWikiFrame object
        wikiData -- WikiData object
        wordList -- Sequence of wiki words to export
        exportType -- string tag to identify how to export
        exportDest -- Path to destination directory or file to export to
        compatFilenames -- Should the filenames be encoded to be lowest
                           level compatible
        addopt -- additional options returned by getAddOpt()
        """
        
        self.pWiki = pWiki
        self.wikiData = wikiData # self.pWiki.wikiData
        self.wordList = wordList
        self.exportDest = exportDest
        
        if compatFilenames:
            self.convertFilename = removeBracketsToCompFilename
        else:
            self.convertFilename = removeBracketsFilename    # lambda s: mbcsEnc(s, "replace")[0]
        
        if exportType == u"html_single":
            startfile = self.exportHtmlSingleFile()
        elif exportType == u"html_multi":
            startfile = self.exportHtmlMultipleFiles()
        elif exportType == u"xml":
            startfile = self.exportXml()
            
            
        if not compatFilenames:
            startfile = mbcsEnc(startfile)[0]
            
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
            wikiPage = self.wikiData.getPage(word)
            if not self.shouldExport(word, wikiPage):
                continue
            
            try:
                content = wikiPage.getContent()
                links = {}  # TODO Why links to all (even not exported) children?
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
            wikiPage = self.wikiData.getPage(word)
            if not self.shouldExport(word, wikiPage):
                continue

            links = {}
            for relation in wikiPage.getChildRelationships(
                    existingonly=True, selfreference=False):
                if not self.shouldExport(relation):
                    continue
                # get aliases too
                relation = self.wikiData.getAliasesWikiWord(relation)
                links[relation] = self.convertFilename(u"%s.html" % relation)  #   "#%s" ???
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
            wikiPage = self.wikiData.getPage(word)
            if not self.shouldExport(word, wikiPage):
                continue
                
            # Why localtime?
            modified, created = wikiPage.getTimestamps()
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
            
            wikiPage = self.wikiData.getPage(word)
            content = wikiPage.getContent()            
            fp.write(self.exportContentToHtmlString(word, content, links, startFile,
                    onlyInclude))
            fp.reset()        
            realfp.close()
        except Exception, e:
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
            wikiPage = self.wikiData.getPage(word)
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
                wikiPage = self.wikiData.getPage(wikiWord)
            except WikiWordNotFoundException:
                return False
            
        #print "shouldExport", mbcsEnc(wikiWord)[0], repr(wikiPage.props.get("export", ("True",))), \
         #       type(wikiPage.props.get("export", ("True",)))
            
        return strToBool(wikiPage.getProperties().get("export", ("True",))[0])


    def popState(self):
        if self.statestack[-1][0] == "normalindent":
            self.outEatBreaks(u"</ul>\n")
        elif self.statestack[-1][0] == "ol":
            self.outEatBreaks(u"</ol>\n")
            self.numericdeepness -= 1
        elif self.statestack[-1][0] == "ul":
            self.outEatBreaks(u"</ul>\n")
            
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
                self.processTokens(content, celltokens)
                self.outAppend(u"</td>")
            self.outAppend(u"</tr>\n")

        self.outAppend(u'</table>\n', eatPostBreak=True)


    def formatContent(self, word, content, links=None, asXml=False,
            asHtmlPreview=False):
        if links is None:
            self.links = {}
        else:
            self.links = links
            
        self.asHtmlPreview = asHtmlPreview
        self.asXml = asXml
        # Replace tabs with spaces
        content = content.replace(u"\t", u" " * 4)  # TODO Configurable
        self.result = []
        self.statestack = [("normalindent", 0)]
        # deepness of numeric bullets
        self.numericdeepness = 0

        # TODO Without camel case
        page = PageAst.Page()
        page.buildAst(self.pWiki.getFormatting(), content)

        # Get property pattern
        if asHtmlPreview:
            proppattern = self.pWiki.configuration.get(
                        "main", "html_preview_proppattern", u"")
        else:
            proppattern = self.pWiki.configuration.get(
                        "main", "html_export_proppattern", u"")
                        
        self.proppattern = re.compile(proppattern,
                re.DOTALL | re.UNICODE | re.MULTILINE)

        if asHtmlPreview:
            self.proppatternExcluding = self.pWiki.configuration.getboolean(
                        "main", "html_preview_proppattern_is_excluding", u"True")
        else:
            self.proppatternExcluding = self.pWiki.configuration.getboolean(
                        "main", "html_export_proppattern_is_excluding", u"True")
        

        if len(page.getTokens()) >= 2:
            if asHtmlPreview:
                facename = self.pWiki.configuration.get(
                        "main", "facename_html_preview", u"")
                if facename:
                    self.outAppend('<font face="%s">' % facename)
            
            self.processTokens(content, page.getTokens())
                
            if asHtmlPreview and facename:
                self.outAppend('</font>')

        return self.getOutput()


    def processTokens(self, content, tokens):
        stacklen = len(self.statestack)
        unescapeNormalText = self.pWiki.getFormatting().unescapeNormalText
        

        for i in xrange(len(tokens)):
            tok = tokens[i]
            try:
                nexttok = tokens[i+1]
            except:
                nexttok = Token(WikiFormatting.FormatTypes.Default,
                    tok.start+len(tok.text), {}, u"")

            styleno = tok.ttype
            nextstyleno = nexttok.ttype

            # print "formatContent", styleno, nextstyleno, repr(content[tok[0]:nexttok[0]])

            if styleno == WikiFormatting.FormatTypes.Default or \
                styleno == WikiFormatting.FormatTypes.EscapedChar:  # == no token RE matches
                # Normal text, maybe with newlines and indentation to process
                lines = tok.text.split(u"\n")
                if styleno == WikiFormatting.FormatTypes.EscapedChar:
                    lines = [tok.node.unescaped]

                # Test if beginning of lines at beginning of a line in editor
                if tok.start > 0 and content[tok.start - 1] != u"\n":
#                     print "icline", repr(lines[0]), repr(escapeHtml(lines[0]))
                    # if not -> output of the first, incomplete, line
                    self.outAppend(escapeHtml(lines[0]))
                    del lines[0]
                    
                    if len(lines) >= 1:
                        # If further lines follow, break line
                        self.outAppend(u"<br />\n")


                if len(lines) >= 1:
                    # All 'lines' now begin at a new line in the editor
                    # and all but the last end at one
                    for line in lines[:-1]:
                        if line.strip() == u"":
                            # Handle empty line
                            self.outAppend(u"<br />\n")
                            continue

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
                            self.outEatBreaks(u"<ul>")
                            self.statestack.append(("normalindent", ind))
                            self.outAppend(escapeHtml(line))
                            self.outAppend(u"<br />\n")

                        elif self.statestack[-1][0] in ("normalindent", "ol", "ul"):
                            self.outAppend(escapeHtml(line))
                            self.outAppend(u"<br />\n")
                            
                            
                    # Handle last line
                    # Some tokens have own indentation handling
                    # and last line is empty string in this case,
                    # do not handle last line if such token follows
                    if not nextstyleno in \
                            (WikiFormatting.FormatTypes.Numeric,
                            WikiFormatting.FormatTypes.Bullet,
                            WikiFormatting.FormatTypes.Suppress,
                            WikiFormatting.FormatTypes.Table):

                        line = lines[-1]
                        line, ind = splitIndent(line)
                        
                        while stacklen < len(self.statestack) and \
                                ind < self.statestack[-1][1]:
                            # Current indentation is less than previous (stored
                            # on stack) so close open <ul> and <ol>
                            self.popState()
                                
                        if self.statestack[-1][0] == "normalindent" and \
                                ind > self.statestack[-1][1]:
                            # More indentation than before -> open new <ul> level
                            self.outEatBreaks(u"<ul>")
                            self.statestack.append(("normalindent", ind))
                            self.outAppend(escapeHtml(line))
                        elif self.statestack[-1][0] in ("normalindent", "ol", "ul"):
                            self.outAppend(escapeHtml(line))
                    
                        
                # self.result.append(u"<br />\n")   # TODO <br />  ?

                continue    # Next token
            
            
            # if a known token RE matches:
            
            if styleno == WikiFormatting.FormatTypes.Bold:
                self.outAppend(u"<b>" + escapeHtml(
                        unescapeNormalText(tok.grpdict["boldContent"])) + u"</b>")
            elif styleno == WikiFormatting.FormatTypes.Italic:
                self.outAppend(u"<i>"+escapeHtml(
                        unescapeNormalText(tok.grpdict["italicContent"])) + u"</i>")
            elif styleno == WikiFormatting.FormatTypes.Heading4:
                self.outEatBreaks(u"<h4>%s</h4>\n" % escapeHtml(
                        unescapeNormalText(tok.grpdict["h4Content"])))
            elif styleno == WikiFormatting.FormatTypes.Heading3:
                self.outEatBreaks(u"<h3>%s</h3>\n" % escapeHtml(
                        unescapeNormalText(tok.grpdict["h3Content"])))
            elif styleno == WikiFormatting.FormatTypes.Heading2:
                self.outEatBreaks(u"<h2>%s</h2>\n" % escapeHtml(
                        unescapeNormalText(tok.grpdict["h2Content"])))
            elif styleno == WikiFormatting.FormatTypes.Heading1:
                self.outEatBreaks(u"<h1>%s</h1>\n" % escapeHtml(
                        unescapeNormalText(tok.grpdict["h1Content"])))
            elif styleno == WikiFormatting.FormatTypes.HorizLine:
                self.outEatBreaks(u'<hr size="1" />\n')
            elif styleno == WikiFormatting.FormatTypes.Script:
                pass  # Hide scripts                
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

            elif styleno == WikiFormatting.FormatTypes.Url:
                link = tok.node.url
                if self.asXml:   # TODO XML
                    self.outAppend(u'<link type="href">%s</link>' % 
                            escapeHtml(link))
                else:
                    lowerLink = link.lower()
                    if lowerLink.endswith(".jpg") or \
                            lowerLink.endswith(".gif") or \
                            lowerLink.endswith(".png"):
                        # Ignore title, use image
                        if self.asHtmlPreview and lowerLink.startswith("file:"):
                            # At least under Windows, wxWidgets has another
                            # opinion how a local file URL should look like
                            # than Python
                            p = urllib.url2pathname(link)  # TODO Relative URLs
                            link = wxFileSystem.FileNameToURL(p)
                        self.outAppend(u'<img src="%s" border="0" />' % 
                                escapeHtml(link))
                    else:
#                         self.outAppend(u'<a href="%s">%s</a>' %
#                                 (escapeHtml(link), escapeHtml(link)))
                        self.outAppend(u'<a href="%s">' % link)
                        if tok.node.titleTokens is not None:
                            self.processTokens(content, tok.node.titleTokens)
                        else:
                            self.outAppend(escapeHtml(link))                        
                        self.outAppend(u'</a>')

            elif styleno == WikiFormatting.FormatTypes.WikiWord:  # or \
                    # styleno == WikiFormatting.FormatTypes.WikiWord2:
                word = tok.node.nakedWord # self.pWiki.getFormatting().normalizeWikiWord(tok.text)
                link = self.links.get(word)
                
                if link:
                    if self.asXml:   # TODO XML
                        self.outAppend(u'<link type="wikiword">%s</link>' % 
                                escapeHtml(tok.text))
                    else:
#                         if word.startswith(u"["):
#                             word = word[1:len(word)-1]
                        self.outAppend(u'<a href="%s">' % escapeHtml(link))
                        if tok.node.titleTokens is not None:
                            self.processTokens(content, tok.node.titleTokens)
                        else:
                            self.outAppend(escapeHtml(tok.text))                        
                        self.outAppend(u'</a>')
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
                    self.outEatBreaks(u"<ol>")
                    self.statestack.append(("ol", ind))
                    self.numericdeepness += 1

                while numbers > self.numericdeepness:
                    self.outEatBreaks(u"<ol>")
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
                    self.outEatBreaks(u"<ul>")
                    self.statestack.append(("ul", ind))

                self.eatPreBreak(u"<li />")
            elif styleno == WikiFormatting.FormatTypes.Suppress:
                while self.statestack[-1][0] != "normalindent":
                    self.popState()
                self.outAppend(escapeHtml(tok.grpdict["suppressContent"]))
            elif styleno == WikiFormatting.FormatTypes.Table:
                ind = splitIndent(tok.grpdict["tableBegin"])[1]
                
#                 while self.statestack[-1][0] != "normalindent":  # TODO ?
#                     self.popState()
                while stacklen < len(self.statestack) and \
                        ind < self.statestack[-1][1]:
                    self.popState()
                    
#                 while ind == self.statestack[-1][1] and \
#                         self.statestack[-1][0] != "ul" and \
#                         stacklen < len(self.statestack):
#                     self.popState()

                if ind > self.statestack[-1][1]: # or \
#                        self.statestack[-1][0] != "ul":
                    self.outEatBreaks(u"<ul>")
                    self.statestack.append(("normalindent", ind))

                self.outTable(content, tok.node)

        while len(self.statestack) > stacklen:
            self.popState()




class TextExporter:
    """
    Exports raw text
    """
    def __init__(self):
        self.pWiki = None
        self.wikiData = None
        self.wordList = None
        self.exportDest = None
        self.convertFilename = removeBracketsFilename # lambda s: s   


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
            compatFilenames, addopt):
        """
        Run export operation.
        
        pWiki -- PersonalWikiFrame object
        wikiData -- WikiData object
        wordList -- Sequence of wiki words to export
        exportType -- string tag to identify how to export
        exportDest -- Path to destination directory or file to export to
        compatFilenames -- Should the filenames be encoded to be lowest
                           level compatible
        addopt -- additional options returned by getAddOpt()
        """
        self.pWiki = pWiki
        self.wikiData = wikiData # self.pWiki.wikiData
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
    
