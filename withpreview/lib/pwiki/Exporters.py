from Enum import Enumeration
import WikiFormatting
import textile
import re
import os
from os.path import join, exists
import sys
import shutil
from xml.sax.saxutils import escape
from time import localtime

ExportTypes = Enumeration("ExportTypes", ["WikiToSingleHtmlPage", "WikiToSetOfHtmlPages", "WikiWordToHtmlPage",
                                          "WikiSubTreeToSingleHtmlPage", "WikiSubTreeToSetOfHtmlPages",
                                          "WikiToXml"], 1)

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
        outputFile = join(dir, "%s.html" % self.pWiki.wikiName)
        if exists(outputFile):
            os.unlink(outputFile)

        fp = open(outputFile, "w")
        fp.write(self.getFileHeader(self.pWiki.wikiName))
        
        words = self.wikiData.getAllWords()
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
                        links[relation] = "#%s" % wordForAlias
                    else:
                        links[relation] = "#%s" % relation
                    
                formattedContent = self.formatContent(word, content, links)
                fp.write('<span class="wiki-name-ref">[<a name="%s">%s</a>]</span><br><br><span class="parent-nodes">parent nodes: %s</span><br>%s%s<hr size="1"/>'
                         % (word, word, self.getParentLinks(wikiPage, False), formattedContent, '<br />\n'*10))
            except Exception, e:
                pass

        fp.write(self.getFileFooter())
        fp.close()        
        self.copyCssFile(dir)
        os.startfile(outputFile)

        
    def exportWikiToSetOfHtmlPages(self, dir):
        words = self.wikiData.getAllWords()
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
                    links[relation] = "%s.html" % wordForAlias
                else:
                    links[relation] = "%s.html" % relation
                                
            self.exportWordToHtmlPage(dir, word, links, False)
        self.copyCssFile(dir)
        rootFile = join(dir, "%s.html" % self.pWiki.wikiName)
        os.startfile(rootFile)


    def exportWordToHtmlPage(self, dir, word=None, links=None, startFile=True, onlyInclude=None):
        if not word:
            word = self.pWiki.currentWikiWord

        outputFile = join(dir, "%s.html" % word)
        try:
            wikiPage = self.wikiData.getPage(word, toload=["parents"])
            content = wikiPage.getContent()
            formattedContent = self.formatContent(word, content, links)

            if exists(outputFile):
                os.unlink(outputFile)

            fp = open(outputFile, "w")
            fp.write(self.getFileHeader(word))

            # if startFile is set then this is the only page being exported so
            # do not include the parent header.
            if not startFile:
                fp.write('<span class="parent-nodes">parent nodes: %s</span>' % self.getParentLinks(wikiPage, True, onlyInclude))
                
            fp.write(formattedContent)
            fp.write(self.getFileFooter())
            fp.close()
        except Exception, e:
            pass
        
        self.copyCssFile(dir)
        if startFile:
            os.startfile(outputFile)


    def exportContentToHtmlString(self, word, content, links):
        formattedContent = self.formatContent(word, content, links)
        return "%s %s %s" % (self.getFileHeader(word), formattedContent, self.getFileFooter())


    def exportSubTreeToSingleHtmlPage(self, dir, rootWord=None):
        if not rootWord:
            rootWord = self.pWiki.currentWikiWord

        outputFile = join(dir, "%s.html" % rootWord)

        if exists(outputFile):
            os.unlink(outputFile)

        fp = open(outputFile, "w")
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
                        links[relation] = "#%s" % wordForAlias
                    else:
                        links[relation] = "#%s" % relation
                    
                formattedContent = self.formatContent(word, content, links)
                fp.write('<span class="wiki-name-ref">[<a name="%s">%s</a>]</span><br><br><span class="parent-nodes">parent nodes: %s</span><br>%s%s<hr size="1"/>'
                         % (word, word, self.getParentLinks(wikiPage, False, words), formattedContent, '<br />\n'*10))
            except Exception, e:
                pass

        fp.write(self.getFileFooter())
        fp.close()        
        self.copyCssFile(dir)
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
                    links[relation] = "%s.html" % wordForAlias
                else:
                    links[relation] = "%s.html" % relation
                                
            self.exportWordToHtmlPage(dir, word, links, False, words)
        self.copyCssFile(dir)
        rootFile = join(dir, "%s.html" % rootWord)
        os.startfile(rootFile)


    def exportWikiToXml(self, dir):
        outputFile = join(dir, "%s.xml" % self.pWiki.wikiName)

        if exists(outputFile):
            os.unlink(outputFile)

        fp = open(outputFile, "w")
        fp.write('<?xml version="1.0" encoding="iso-8859-1" ?>')


        fp.write('<wiki name="%s">' % self.pWiki.wikiName)
        
        words = self.wikiData.getAllWords()
        for word in words:
            wikiPage = self.wikiData.getPage(word, toload=["info", "parents", "children", "props"])
            if not self.shouldExport(word, wikiPage):
                continue

            created = localtime(float(wikiPage.created))
            modified = localtime(float(wikiPage.modified))
            
            fp.write('<wikiword name="%s" created="%s" modified="%s">' % (word, created, modified))

            try:
                content = wikiPage.getContent()
                links = {}
                for relation in wikiPage.childRelations:
                    if not self.shouldExport(relation):
                        continue

                    # get aliases too
                    wordForAlias = self.wikiData.getAliasesWikiWord(relation)
                    if wordForAlias:
                        links[relation] = "#%s" % wordForAlias
                    else:
                        links[relation] = "#%s" % relation
                    
                formattedContent = self.formatContent(word, content, links, asXml=True)
                fp.write(formattedContent)

            except Exception, e:
                pass

            fp.write('</wikiword>')

        fp.write("</wiki>")
        fp.close()
        os.startfile(outputFile)


    def getFileHeader(self, title):
        return """<html>
    <head>
        <title>%s</title>
         <link type="text/css" rel="stylesheet" href="wikistyle.css">
    </head>
    <body>
""" % title


    def getFileFooter(self):
        return """    </body>
</html>
"""

    def getParentLinks(self, wikiPage, asHref=True, wordsToInclude=None):
        parents = ""
        wikiPage.parentRelations.sort()
        for relation in wikiPage.parentRelations:
            if wordsToInclude and relation not in wordsToInclude:
                continue
            
            if parents != "":
                parents = parents + " | "

            if asHref:
                parents = parents + '<span class="parent-node"><a href="%s.html">%s</a></span>' % (relation, relation)
            else:
                parents = parents + '<span class="parent-node"><a href="#%s">%s</a></span>' % (relation, relation)

        return parents
    
    
    def formatContent(self, word, content, links=None, asXml=False):
        contentBeforeProcessing = content
        content = WikiFormatting.ItalicRE.sub('__\\1__', content)
        content = WikiFormatting.Heading4RE.sub('h4. \\1', content)
        content = WikiFormatting.Heading3RE.sub('h3. \\1', content)
        content = WikiFormatting.Heading2RE.sub('h2. \\1', content)
        content = WikiFormatting.Heading1RE.sub('h1. \\1', content)
        content = WikiFormatting.BoldRE.sub('**\\1**', content)

        if not asXml:    
            content = WikiFormatting.HorizLineRE.sub('<hr size="1"/>', content)

        # link the wiki words
        if links:
            content = self.linkWikiWords(content, links, asXml)

        # tracks which [] block we are on
        matchIndex = MatchIndex()
        def suppress(match):
            # now search the pre-processed text for the same match
            bpMatchNumber = 0
            bpMatch = WikiFormatting.SuppressHighlightingRE.search(contentBeforeProcessing)
            while bpMatch:
                if bpMatchNumber == matchIndex.get():
                    break
                bpMatch = WikiFormatting.SuppressHighlightingRE.search(contentBeforeProcessing, bpMatch.end())
                bpMatchNumber = bpMatchNumber + 1

            if (bpMatch):
                matchContent = bpMatch.group(1)
                htmlRe = re.compile("<.+?>")
                matchContent = htmlRe.sub('', matchContent)
                matchIndex.increment()
                return '<pre>%s</pre>' % matchContent
            else:
                return match.group(1)
        
        content = WikiFormatting.SuppressHighlightingRE.sub(suppress, content)

        return textile.textile(content)

    def linkWikiWords(self, content, links, asXml=False):
        def replaceWithLink(match):
            word = match.group(0)
            link = links.get(word)
            if link:
                if asXml:
                    return '<link type="wikiword">%s</link>' % word
                else:
                    if word.startswith("["):
                        word = word[1:len(word)-1]
                    return '<a href="%s">%s</a>' % (link, word)
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

        return "\n".join(newContent)
    
    def copyCssFile(self, dir):
        if not exists(join(dir, 'wikistyle.css')):
            cssFile = join(self.pWiki.wikiAppDir, 'export', 'wikistyle.css')
            if exists(cssFile):
                shutil.copy(cssFile, dir)

    def shouldExport(self, wikiWord, wikiPage=None):
        if not wikiPage:
            wikiPage = self.wikiData.getPage(wikiWord, toload=["props"])
            
        if wikiPage.props.has_key("export"):
            export = wikiPage.props["export"][0]
            export = export.lower()            
            return export == "true" or export == "1"
        return True

class MatchIndex:
    def __init__(self):
        self.matchIndex = 0
    def increment(self):
        self.matchIndex = self.matchIndex + 1
    def get(self):
        return self.matchIndex
        
