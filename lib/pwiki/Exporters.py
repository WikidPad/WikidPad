import re
import os
from os.path import join, exists
import sys, traceback
import shutil
# from xml.sax.saxutils import escape
from time import localtime

from Enum import Enumeration
from StringOps import mbcsWriter, utf8Writer, mbcsEnc, strToBool, BOM_UTF8
import WikiFormatting
from WikiExceptions import *


ExportTypes = Enumeration("ExportTypes", ["WikiToSingleHtmlPage", "WikiToSetOfHtmlPages", "WikiWordToHtmlPage",
                                          "WikiSubTreeToSingleHtmlPage", "WikiSubTreeToSetOfHtmlPages",
                                          "WikiToXml"], 1)


## Copied from xml.sax.saxutils and modified to reduce dependencies
def escape(data):
    """Escape &, <, and > in a string of data.
    """

    # must do ampersand first
    data = data.replace(u"&", u"&amp;")
    data = data.replace(u">", u"&gt;")
    data = data.replace(u"<", u"&lt;")
    return data



class HtmlExporter:
    def __init__(self, pWiki):
        self.pWiki = pWiki
        self.wikiData = self.pWiki.wikiData

    def export(self, type, dir):
        if type == ExportTypes.WikiToSingleHtmlPage:
            self.exportWikiToSingleHtmlPage(dir)
        elif type == ExportTypes.WikiToSetOfHtmlPages:
            self.exportWikiToSetOfHtmlPages(dir)
        elif type == ExportTypes.WikiWordToHtmlPage:
            self.exportWordToHtmlPage(dir)
        elif type == ExportTypes.WikiSubTreeToSingleHtmlPage:
            self.exportSubTreeToSingleHtmlPage(dir)
        elif type == ExportTypes.WikiSubTreeToSetOfHtmlPages:
            self.exportSubTreeToSetOfHtmlPages(dir)
        elif type == ExportTypes.WikiToXml:
            self.exportWikiToXml(dir)

    def exportWikiToSingleHtmlPage(self, dir):
        outputFile = mbcsEnc(join(dir, u"%s.html" % self.pWiki.wikiName))[0]
        if exists(outputFile):
            os.unlink(outputFile)

        realfp = open(outputFile, "w")
        fp = mbcsWriter(realfp, "replace")
        fp.write(self.getFileHeader(self.pWiki.wikiName))
        
        words = self.wikiData.getAllDefinedPageNames()
        for word in words:
            wikiPage = self.wikiData.getPage(word, toload=["parents", "children", "props"])
            if not self.shouldExport(word, wikiPage):
                continue
            
            try:
                content = wikiPage.getContent()
                links = {}
                for relation in wikiPage.childRelations:
                    if not self.shouldExport(relation):
                        continue
                    # get aliases too
                    wordForAlias = self.wikiData.getAliasesWikiWord(relation)
                    if wordForAlias:
                        links[relation] = u"#%s" % wordForAlias
                    else:
                        links[relation] = u"#%s" % relation
                    
                formattedContent = self.formatContent(word, content, links)
                fp.write((u'<span class="wiki-name-ref">[<a name="%s">%s</a>]'+
                        u'</span><br><br><span class="parent-nodes">'+
                        u'parent nodes: %s</span><br>%s%s<hr size="1"/>') %
                        (word, word, self.getParentLinks(wikiPage, False), formattedContent, '<br />\n'*10))
            except Exception, e:
                traceback.print_exc()
                pass

        fp.write(self.getFileFooter())
        fp.reset()        
        realfp.close()        
        self.copyCssFile(dir)
        if self.pWiki.configuration.getboolean("main", "start_browser_after_export"):
            os.startfile(outputFile)

        
    def exportWikiToSetOfHtmlPages(self, dir):
        words = self.wikiData.getAllDefinedPageNames()
        for word in words:
            wikiPage = self.wikiData.getPage(word, toload=["parents", "children", "props"])
            if not self.shouldExport(word, wikiPage):
                continue

            links = {}
            for relation in wikiPage.childRelations:
                if not self.shouldExport(relation):
                    continue
                # get aliases too
                wordForAlias = self.wikiData.getAliasesWikiWord(relation)
                if wordForAlias:
                    links[relation] = u"%s.html" % wordForAlias
                else:
                    links[relation] = u"%s.html" % relation
                                
            self.exportWordToHtmlPage(dir, word, links, False)
        self.copyCssFile(dir)
        rootFile = mbcsEnc(join(dir, u"%s.html" % self.pWiki.wikiName))[0]
        if self.pWiki.configuration.getboolean("main", "start_browser_after_export"):
            os.startfile(rootFile)


    def exportWordToHtmlPage(self, dir, word=None, links=None, startFile=True, onlyInclude=None):
        if not word:
            word = self.pWiki.currentWikiWord

        outputFile = mbcsEnc(join(dir, u"%s.html" % word))[0]
        try:
            wikiPage = self.wikiData.getPage(word, toload=["parents"])
            content = wikiPage.getContent()
            formattedContent = self.formatContent(word, content, links)

            if exists(outputFile):
                os.unlink(outputFile)

            realfp = open(outputFile, "w")
            fp = mbcsWriter(realfp, "replace")
            fp.write(self.getFileHeader(word))

            # if startFile is set then this is the only page being exported so
            # do not include the parent header.
            if not startFile:
                fp.write(u'<span class="parent-nodes">parent nodes: %s</span>' %
                        self.getParentLinks(wikiPage, True, onlyInclude))
                
            fp.write(formattedContent)
            fp.write(self.getFileFooter())
            fp.reset()        
            realfp.close()        
        except Exception, e:
            traceback.print_exc()
            pass
        
        self.copyCssFile(dir)
        if startFile and self.pWiki.configuration.getboolean(
                "main", "start_browser_after_export"):
            os.startfile(outputFile)


    def exportSubTreeToSingleHtmlPage(self, dir, rootWord=None):
        if not rootWord:
            rootWord = self.pWiki.currentWikiWord

        outputFile = mbcsEnc(join(dir, u"%s.html" % rootWord))[0]

        if exists(outputFile):
            os.unlink(outputFile)

        realfp = open(outputFile, "w")
        fp = mbcsWriter(realfp, "replace")
        fp.write(self.getFileHeader(rootWord))

        words = self.wikiData.getAllSubWords(rootWord, True)
        for word in words:
            wikiPage = self.wikiData.getPage(word, toload=["parents", "children", "props"])
            if not self.shouldExport(word, wikiPage):
                continue

            try:
                content = wikiPage.getContent()
                links = {}
                for relation in wikiPage.childRelations:
                    if not self.shouldExport(relation):
                        continue

                    # get aliases too
                    wordForAlias = self.wikiData.getAliasesWikiWord(relation)
                    if wordForAlias:
                        links[relation] = u"#%s" % wordForAlias
                    else:
                        links[relation] = u"#%s" % relation
                    
                formattedContent = self.formatContent(word, content, links)
                fp.write((u'<span class="wiki-name-ref">[<a name="%s">%s</a>]'+
                        u'</span><br><br><span class="parent-nodes">'+
                        u'parent nodes: %s</span><br>%s%s<hr size="1"/>') %
                        (word, word, self.getParentLinks(wikiPage, False, words),
                        formattedContent, u'<br />\n'*10))
            except Exception, e:
                pass

        fp.write(self.getFileFooter())
        fp.reset()        
        realfp.close()        
        self.copyCssFile(dir)
        if self.pWiki.configuration.getboolean("main", "start_browser_after_export"):
            os.startfile(outputFile)


    def exportSubTreeToSetOfHtmlPages(self, dir, rootWord=None):
        if not rootWord:
            rootWord = self.pWiki.currentWikiWord

        words = self.wikiData.getAllSubWords(rootWord, True)
        for word in words:
            wikiPage = self.wikiData.getPage(word, toload=["parents", "children", "props"])
            if not self.shouldExport(word, wikiPage):
                continue

            links = {}
            for relation in wikiPage.childRelations:
                if not self.shouldExport(relation):
                    continue

                # get aliases too
                wordForAlias = self.wikiData.getAliasesWikiWord(relation)
                if wordForAlias:
                    links[relation] = u"%s.html" % wordForAlias
                else:
                    links[relation] = u"%s.html" % relation
                                
            self.exportWordToHtmlPage(dir, word, links, False, words)
        self.copyCssFile(dir)
        rootFile = mbcsEnc(join(dir, u"%s.html" % rootWord))[0]
        if self.pWiki.configuration.getboolean("main", "start_browser_after_export"):
            os.startfile(rootFile)


    def exportWikiToXml(self, dir):
        outputFile = mbcsEnc(join(dir, u"%s.xml" % self.pWiki.wikiName))[0]

        if exists(outputFile):
            os.unlink(outputFile)

        realfp = open(outputFile, "w")
        realfp.write(BOM_UTF8)
        fp = utf8Writer(realfp, "replace")
        fp.write(u'<?xml version="1.0" encoding="utf-8" ?>')


        fp.write(u'<wiki name="%s">' % self.pWiki.wikiName)
        
        words = self.wikiData.getAllDefinedPageNames()
        for word in words:
            wikiPage = self.wikiData.getPage(word, toload=["info", "parents", "children", "props"])
            if not self.shouldExport(word, wikiPage):
                continue

            created = localtime(float(wikiPage.created))
            modified = localtime(float(wikiPage.modified))
            
            fp.write(u'<wikiword name="%s" created="%s" modified="%s">' %
                    (word, created, modified))

            try:
                content = wikiPage.getContent()
                links = {}
                for relation in wikiPage.childRelations:
                    if not self.shouldExport(relation):
                        continue

                    # get aliases too
                    wordForAlias = self.wikiData.getAliasesWikiWord(relation)
                    if wordForAlias:
                        links[relation] = u"#%s" % wordForAlias
                    else:
                        links[relation] = u"#%s" % relation
                    
                formattedContent = self.formatContent(word, content, links, asXml=True)
                fp.write(formattedContent)

            except Exception, e:
                pass

            fp.write(u'</wikiword>')

        fp.write(u"</wiki>")
        fp.reset()        
        realfp.close()        
        if self.pWiki.configuration.getboolean("main", "start_browser_after_export"):
            os.startfile(outputFile)


    def getFileHeader(self, title):
        return u"""<html>
    <head>
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
        wikiPage.parentRelations.sort()
        for relation in wikiPage.parentRelations:
            if wordsToInclude and relation not in wordsToInclude:
                continue
            
            if parents != u"":
                parents = parents + u" | "

            if asHref:
                parents = parents + u'<span class="parent-node"><a href="%s.html">%s</a></span>' % (relation, relation)
            else:
                parents = parents + u'<span class="parent-node"><a href="#%s">%s</a></span>' % (relation, relation)

        return parents
    
    
    def formatContent(self, word, content, links=None, asXml=False):
        # change the <<>> blocks into [[]] blocks so they aren't escaped
        content = WikiFormatting.SuppressHighlightingRE.sub('[[\\1]]', content)
        content = escape(content)
        contentBeforeProcessing = content

        content = WikiFormatting.ItalicRE.sub(u'<i>\\1</i>', content)
        content = WikiFormatting.Heading3RE.sub(u'<h3>\\1</h3>', content)
        content = WikiFormatting.Heading2RE.sub(u'<h2>\\1</h2>', content)
        content = WikiFormatting.Heading1RE.sub(u'<h1>\\1</h1>', content)

        if asXml:
            content = WikiFormatting.ToDoREWithContent.sub(u'<todo>\\1</todo>', content)
        else:
            content = WikiFormatting.ToDoREWithContent.sub(
                    u'<span class="todo">\\1</span><br />', content)
            
        content = WikiFormatting.ScriptRE.sub('', content)

        if asXml:        
            content = WikiFormatting.PropertyRE.sub(
                    u'<property name="\\1" value="\\2"/>', content)
        else:
            content = WikiFormatting.PropertyRE.sub(
                    u'<span class="property">[\\1: \\2]</span>', content)

        if not asXml:    
            content = WikiFormatting.HorizLineRE.sub(u'<hr size="1"/>', content)

        # add the ul/ol/li tags for bullets
        content = self.createBullets(content, asXml)

        # add the blockquote tags for indents
        content = self.createIndents(content, asXml)

        # do bold last to make sure it doesn't mess with bullets
        content = WikiFormatting.BoldRE.sub(u'<b>\\1</b>', content)

        # link the wiki words
        if links:
            content = self.linkWikiWords(content, links, asXml)

        # replace URL's last
        if asXml:
            content = WikiFormatting.UrlRE.sub(u'<link type="href">\\1</link>', content)
        else:
            def replaceLink(match):
                lowerLink = match.group(1).lower()
                if lowerLink.endswith(u".jpg") or lowerLink.endswith(u".gif") or\
                        lowerLink.endswith(u".png"):
                    return u'<img src="%s" border="0">' % match.group(1)
                else:
                    return u'<a href="%s">%s</a>' % (match.group(1), match.group(1))
            content = WikiFormatting.UrlRE.sub(replaceLink, content)

        # add <pre> tags for suppressed regions
        SuppressHighlightingRE = re.compile(u"\[\[(.*?)\]\]", re.DOTALL)

        # tracks which [] block we are on
        matchIndex = MatchIndex()
        def suppress(match):
            # now search the pre-processed text for the same match
            bpMatchNumber = 0
            bpMatch = SuppressHighlightingRE.search(contentBeforeProcessing)
            while bpMatch:
                if bpMatchNumber == matchIndex.get():
                    break
                bpMatch = SuppressHighlightingRE.search(contentBeforeProcessing, bpMatch.end())
                bpMatchNumber = bpMatchNumber + 1

            if (bpMatch):
                matchContent = bpMatch.group(1)
                htmlRe = re.compile(u"<.+?>")
                matchContent = htmlRe.sub('', matchContent)
                matchIndex.increment()
                return u'<pre>%s</pre>' % matchContent
            else:
                return match.group(1)
        
        content = SuppressHighlightingRE.sub(suppress, content)
        
        return content
    

    def createBullets(self, content, asXml=False):
        lastBulletDepth = 0
        lastUolTag = None
        tabSize = 4
        newContent = []
        
        for line in content.splitlines():
            match = WikiFormatting.BulletRE.search(line)
            if not match:
                match = WikiFormatting.NumericBulletRE.search(line)
                
            if match:
                if match.group(2) == '*':
                    lastUolTag = u"ul"
                else:
                    lastUolTag = u"ol"

                depth = self.getIndentDepth(match.group(1), tabSize)

                if depth > lastBulletDepth:
                    while lastBulletDepth < depth:
                        newContent.append(u"<%s>\n" % lastUolTag)
                        lastBulletDepth = lastBulletDepth + 1
                else:
                    while lastBulletDepth > depth:
                        newContent.append(u"</%s>\n" % lastUolTag)
                        lastBulletDepth = lastBulletDepth - 1

                newContent.append(u"\t<li>%s</li>\n" % match.group(3))
                lastBulletDepth = depth

            else:
                
                # bullet can span multiple lines so check and see if we are
                # still inside of a bullet tag.
                stillInBullet = False
                if lastBulletDepth > 0:
                    # if the trimed line is 0 we are probably still in the bullet since
                    # it probably is just a newline between bullets.
                    if len(line.strip()) > 0:
                        indentedMatch = WikiFormatting.IndentedRE.search(line)
                        if indentedMatch:
                            depth = self.getIndentDepth(indentedMatch.group(1), tabSize)
                            if depth >= lastBulletDepth:
                                line = indentedMatch.group(2)
                                stillInBullet = True
                    else:
                        stillInBullet = True;

                if not stillInBullet:
                    # close each opened ul/ol
                    while lastBulletDepth > 0:
                        newContent.append(u"</%s>\n" % lastUolTag)
                        lastBulletDepth = lastBulletDepth - 1

                if not asXml:
                    if len(line.strip()) == 0:
                        newContent.append(u"<p />\n")
                    elif len(line) < 50 and line.find("<h") == -1:
                        newContent.append(u"%s<br />\n" % line)
                    else:
                        newContent.append(u"%s\n" % line)
                else:
                    newContent.append(u"%s\n" % line)

        # i may need to write out the last set of ol/ul
        while lastBulletDepth > 0:
            newContent.append(u"</%s>\n" % lastUolTag)
            lastBulletDepth = lastBulletDepth - 1

        return u"".join(newContent)

    def createIndents(self, content, asXml=False):
        lastBulletDepth = 0
        lastUolTag = None
        tabSize = 4
        newContent = []
        
        for line in content.splitlines():
            match = WikiFormatting.IndentedContentRE.search(line)
            if match:
                lastUolTag = u"blockquote"
                depth = self.getIndentDepth(match.group(1), tabSize)
                if depth > lastBulletDepth:
                    while lastBulletDepth < depth:
                        newContent.append(u"<%s>\n" % lastUolTag)
                        lastBulletDepth = lastBulletDepth + 1
                else:
                    while lastBulletDepth > depth:
                        newContent.append(u"</%s>\n" % lastUolTag)
                        lastBulletDepth = lastBulletDepth - 1

                newContent.append(u"\t%s\n" % match.group(3))
                lastBulletDepth = depth

            else:
                
                # bullet can span multiple lines so check and see if we are
                # still inside of a bullet tag.
                stillInBullet = False
                if lastBulletDepth > 0:
                    # if the trimed line is 0 we are probably still in the bullet since
                    # it probably is just a newline between bullets.
                    if len(line.strip()) > 0:
                        indentedMatch = WikiFormatting.IndentedRE.search(line)
                        if indentedMatch:
                            depth = self.getIndentDepth(indentedMatch.group(1), tabSize)
                            if depth >= lastBulletDepth:
                                line = indentedMatch.group(2)
                                stillInBullet = True
                    else:
                        stillInBullet = True;

                if not stillInBullet:
                    # close each opened blockquote
                    while lastBulletDepth > 0:
                        newContent.append(u"</%s>\n" % lastUolTag)
                        lastBulletDepth = lastBulletDepth - 1

                if not asXml:
                    if len(line.strip()) == 0:
                        newContent.append(u"<p />\n")
                    elif len(line) < 50 and line.find("<h") == -1:
                        newContent.append(u"%s<br />\n" % line)
                    else:
                        newContent.append(u"%s\n" % line)
                else:
                    newContent.append(u"%s\n" % line)

        # i may need to write out the last set of ol/ul
        while lastBulletDepth > 0:
            newContent.append(u"</%s>\n" % lastUolTag)
            lastBulletDepth = lastBulletDepth - 1

        return u"".join(newContent)


    def getIndentDepth(self, str, tabSize):
        """
        Gets the indent depth from the leading spaces in the bulleted list
        pattern and number list pattern. Bullets should be nested in increments
        of 3 spaces or with tabs. If using spaces the length of the spaces
        string is divided by 3 for the depth.
        """
        replaceRe = re.compile(u" {%s}" % tabSize)        
        return len(replaceRe.sub(u" ", str));


    def linkWikiWords(self, content, links, asXml=False):
        def replaceWithLink(match):
            word = match.group(0)
            link = links.get(word)
            if link:
                if asXml:
                    return u'<link type="wikiword">%s</link>' % word
                else:
                    if word.startswith("["):
                        word = word[1:len(word)-1]
                    return u'<a href="%s">%s</a>' % (link, word)
            else:
                return word

        newContent = []
        for line in content.splitlines():
            # don't match links on the same line as properties
            # sorry, links and WikiWords can't be on the same line for exporting
            if not WikiFormatting.UrlRE.search(line) and not line.find("<property") != -1:
                line = WikiFormatting.WikiWordRE.sub(replaceWithLink, line)
                line = WikiFormatting.WikiWordRE2.sub(replaceWithLink, line)
            newContent.append(line)

        return u"\n".join(newContent)

    def copyCssFile(self, dir):
        if not exists(join(dir, 'wikistyle.css')):
            cssFile = join(self.pWiki.wikiAppDir, 'export', 'wikistyle.css')
            if exists(cssFile):
                shutil.copy(cssFile, dir)

    def shouldExport(self, wikiWord, wikiPage=None):
        if not wikiPage:
            try:
                wikiPage = self.wikiData.getPage(wikiWord, toload=["props"])
            except WikiWordNotFoundException:
                return False
            
        #print "shouldExport", mbcsEnc(wikiWord)[0], repr(wikiPage.props.get("export", ("True",))), \
         #       type(wikiPage.props.get("export", ("True",)))
            
        return strToBool(wikiPage.props.get("export", ("True",))[0])
            
class MatchIndex:
    def __init__(self):
        self.matchIndex = 0
    def increment(self):
        self.matchIndex = self.matchIndex + 1
    def get(self):
        return self.matchIndex
        
