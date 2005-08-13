from Enum import Enumeration
import WikiFormatting
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
        # change the <<>> blocks into [[]] blocks so they aren't escaped
        content = WikiFormatting.SuppressHighlightingRE.sub('[[\\1]]', content)
        content = escape(content)
        contentBeforeProcessing = content

        content = WikiFormatting.ItalicRE.sub('<i>\\1</i>', content)
        content = WikiFormatting.Heading3RE.sub('<h3>\\1</h3>', content)
        content = WikiFormatting.Heading2RE.sub('<h2>\\1</h2>', content)
        content = WikiFormatting.Heading1RE.sub('<h1>\\1</h1>', content)

        if asXml:
            content = WikiFormatting.ToDoREWithContent.sub('<todo>\\1</todo>', content)
        else:
            content = WikiFormatting.ToDoREWithContent.sub('<span class="todo">\\1</span><br />', content)
            
        content = WikiFormatting.ScriptRE.sub('', content)

        if asXml:        
            content = WikiFormatting.PropertyRE.sub('<property name="\\1" value="\\2"/>', content)
        else:
            content = WikiFormatting.PropertyRE.sub('<span class="property">[\\1: \\2]</span>', content)

        if not asXml:    
            content = WikiFormatting.HorizLineRE.sub('<hr size="1"/>', content)

        # add the ul/ol/li tags for bullets
        content = self.createBullets(content, asXml)

        # add the blockquote tags for indents
        content = self.createIndents(content, asXml)

        # do bold last to make sure it doesn't mess with bullets
        content = WikiFormatting.BoldRE.sub('<b>\\1</b>', content)

        # link the wiki words
        if links:
            content = self.linkWikiWords(content, links, asXml)

        # replace URL's last
        if asXml:
            content = WikiFormatting.UrlRE.sub('<link type="href">\\1</link>', content)
        else:
            def replaceLink(match):
                lowerLink = match.group(1).lower()
                if lowerLink.endswith(".jpg") or lowerLink.endswith(".gif") or lowerLink.endswith(".png"):
                    return '<img src="%s" border="0">' % match.group(1)
                else:
                    return '<a href="%s">%s</a>' % (match.group(1), match.group(1))
            content = WikiFormatting.UrlRE.sub(replaceLink, content)

        # add <pre> tags for suppressed regions
        SuppressHighlightingRE = re.compile("\[\[(.*?)\]\]", re.DOTALL)

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
                htmlRe = re.compile("<.+?>")
                matchContent = htmlRe.sub('', matchContent)
                matchIndex.increment()
                return '<pre>%s</pre>' % matchContent
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
                    lastUolTag = "ul"
                else:
                    lastUolTag = "ol"

                depth = self.getIndentDepth(match.group(1), tabSize)

                if depth > lastBulletDepth:
                    while lastBulletDepth < depth:
                        newContent.append("<%s>\n" % lastUolTag)
                        lastBulletDepth = lastBulletDepth + 1
                else:
                    while lastBulletDepth > depth:
                        newContent.append("</%s>\n" % lastUolTag)
                        lastBulletDepth = lastBulletDepth - 1

                newContent.append("\t<li>%s</li>\n" % match.group(3))
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
                        newContent.append("</%s>\n" % lastUolTag)
                        lastBulletDepth = lastBulletDepth - 1

                if not asXml:
                    if len(line.strip()) == 0:
                        newContent.append("<p />\n")
                    elif len(line) < 50 and line.find("<h") == -1:
                        newContent.append("%s<br />\n" % line)
                    else:
                        newContent.append("%s\n" % line)
                else:
                    newContent.append("%s\n" % line)

        # i may need to write out the last set of ol/ul
        while lastBulletDepth > 0:
            newContent.append("</%s>\n" % lastUolTag)
            lastBulletDepth = lastBulletDepth - 1

        return "".join(newContent)

    def createIndents(self, content, asXml=False):
        lastBulletDepth = 0
        lastUolTag = None
        tabSize = 4
        newContent = []
        
        for line in content.splitlines():
            match = WikiFormatting.IndentedContentRE.search(line)
            if match:
                lastUolTag = "blockquote"
                depth = self.getIndentDepth(match.group(1), tabSize)
                if depth > lastBulletDepth:
                    while lastBulletDepth < depth:
                        newContent.append("<%s>\n" % lastUolTag)
                        lastBulletDepth = lastBulletDepth + 1
                else:
                    while lastBulletDepth > depth:
                        newContent.append("</%s>\n" % lastUolTag)
                        lastBulletDepth = lastBulletDepth - 1

                newContent.append("\t%s\n" % match.group(3))
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
                        newContent.append("</%s>\n" % lastUolTag)
                        lastBulletDepth = lastBulletDepth - 1

                if not asXml:
                    if len(line.strip()) == 0:
                        newContent.append("<p />\n")
                    elif len(line) < 50 and line.find("<h") == -1:
                        newContent.append("%s<br />\n" % line)
                    else:
                        newContent.append("%s\n" % line)
                else:
                    newContent.append("%s\n" % line)

        # i may need to write out the last set of ol/ul
        while lastBulletDepth > 0:
            newContent.append("</%s>\n" % lastUolTag)
            lastBulletDepth = lastBulletDepth - 1

        return "".join(newContent)


    def getIndentDepth(self, str, tabSize):
        """
        Gets the indent depth from the leading spaces in the bulleted list
        pattern and number list pattern. Bullets should be nested in increments
        of 3 spaces or with tabs. If using spaces the length of the spaces
        string is divided by 3 for the depth.
        """
        replaceRe = re.compile(" {%s}" % tabSize)        
        return len(replaceRe.sub(" ", str));


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
        
