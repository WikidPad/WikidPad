from time import time
import os.path, re, struct

from MiscEvent import MiscEventSourceMixin

from WikiExceptions import *   # TODO make normal import?

from StringOps import strToBool, fileContentToUnicode, BOM_UTF8, utf8Enc, \
        utf8Dec

import WikiFormatting
import PageAst

import WikidPadStarter


class DocPage(MiscEventSourceMixin):
    """
    Abstract common base class for WikiPage and FunctionalPage
    """
    def __init__(self, wikiDocument):
        MiscEventSourceMixin.__init__(self)
        
        self.wikiDocument = wikiDocument
        self.txtEditors = []  # List of all editors (views) showing this page


    def addTxtEditor(self, txted):
        """
        Add txted to the list of editors (views) showing this page.
        """
        if not txted in self.txtEditors:
            self.txtEditors.append(txted)


    def removeTxtEditor(self, txted):
        """
        Remove txted from the list of editors (views) showing this page.
        """
        try:
            idx = self.txtEditors.index(txted)
            del self.txtEditors[idx]
        except ValueError:
            # txted not in list
            pass
            
    def getTxtEditor(self):
        """
        Returns an arbitrary text editor associated with the page
        or None if no editor is associated.
        """
        if len(self.txtEditors) > 0:
            return self.txtEditors[0]
        else:
            return None


    def appendLiveText(self, text, fireEvent=True):
        """
        Append some text to page which is either loaded in one or more
        editor(s) or only stored in the database (with automatic update).

        fireEvent -- Send event if database was directly modified
        """
        if len(self.txtEditors) > 0:
            # page is in text editor(s), so call AppendText on one of it
            self.txtEditors[0].AppendText(text)
        else:
            # Modify database
#             wikiData = self.wikiDocument.getWikiData()
            text = self.getLiveText() + text
            self.save(text, fireEvent=fireEvent)
            self.update(text, fireEvent=fireEvent)


    def getLiveText(self):
        """
        Return current tex of page, either from a text editor or
        from the database
        """
        if len(self.txtEditors) > 0:
            # page is in text editor(s), so call AppendText on one of it
            return self.txtEditors[0].GetText()
        else:
            return self.getContent()


    def replaceLiveText(self, text):
        if len(self.txtEditors) > 0:
            # page is in text editor(s), so call replace on one of it
            self.txtEditors[0].replaceText(text)
        else:
            self.save(text)
#             self.update(text, False)   # TODO: Really update? Handle auto-generated areas
            self.update(text, True)   # TODO: Really update? Handle auto-generated areas


    def getContent(self):
        """
        Returns page content. If page doesn't exist already some content
        is created automatically (may be empty string).
        """
        assert 0 #abstract


    def save(self, text, fireEvent=True):
        """
        Saves the content of current doc page.
        """
        assert 0 #abstract


    def update(self, text, fireEvent=True):
        """
        Update additional cached informations of doc page
        """
        assert 0 #abstract



class AliasWikiPage(DocPage):
    """
    Fake page for an alias name of a wiki page. Most functions are delegated
    to underlying real page
    Fetched via the (WikiDocument=) WikiDataManager.getWikiPage method.
    """
    def __init__(self, wikiDocument, aliasWikiWord, realWikiPage):
        self.wikiDocument = wikiDocument
        self.aliasWikiWord = aliasWikiWord
        self.realWikiPage = realWikiPage

    def getWikiWord(self):
        return self.aliasWikiWord

    def getNonAliasPage(self):
        """
        If this page belongs to an alias of a wiki word, return a page for
        the real one, otherwise return self
        """
#         if not self.wikiData.isAlias(self.wikiWord):
#             return self
        
        word = self.wikiDocument.getWikiData().getAliasesWikiWord(self.wikiWord)
        return self.wikiDocument.getWikiPageNoError(word)

    def getContent(self):
        """
        Returns page content. If page doesn't exist already some content
        is created automatically (may be empty string).
        """
        return self.realWikiPage.getContent()


    def save(self, text, fireEvent=True):
        """
        Saves the content of current doc page.
        """
        return self.realWikiPage.save(text, fireEvent)


    def update(self, text, fireEvent=True):
        return self.realWikiPage.update(text, fireEvent)


    # TODO A bit hackish, maybe remove
    def __getattr__(self, attr):
        return getattr(self.realWikiPage, attr)



class WikiPage(DocPage):
    """
    holds the data for a real wikipage (no alias).
    
    Fetched via the WikiDataManager.getWikiPage method.
    """
    def __init__(self, wikiDocument, wikiWord):
        DocPage.__init__(self, wikiDocument)

#         self.wikiData = self.wikiDocument.getWikiData()

        self.wikiWord = wikiWord
        self.parentRelations = None
        self.todos = None
        self.props = None
        self.modified, self.created = None, None

        # does this page need to be saved?
        self.saveDirtySince = None  # None, if not dirty or timestamp when it became dirty
        self.updateDirtySince = None

    def getWikiWord(self):
        return self.wikiWord
        
    def getWikiData(self):
        return self.wikiDocument.getWikiData()

    def getTimestamps(self):
        if self.modified is None:
            self.modified, self.created = \
                    self.getWikiData().getTimestamps(self.wikiWord)
                    
        if self.modified is None:
            ti = time()
            self.modified, self.created = ti, ti
        
        return self.modified, self.created

    def getParentRelationships(self):
        if self.parentRelations is None:
            self.parentRelations = \
                    self.getWikiData().getParentRelationships(self.wikiWord)
        
        return self.parentRelations

        
    def getChildRelationships(self, existingonly=False, selfreference=True,
            withPosition=False):
        """
        Does not support caching
        """
        return self.getWikiData().getChildRelationships(self.wikiWord,
                existingonly, selfreference, withPosition=withPosition)


    def getProperties(self):
        if self.props is None:
            data = self.getWikiData().getPropertiesForWord(self.wikiWord)
            self.props = {}
            for (key, val) in data:
                self.addProperty(key, val)
                
        return self.props


    def getPropertyOrGlobal(self, propkey, default=None):
        """
        Tries to find a property on this page and returns the first value.
        If it can't be found for page, it is searched for a global
        property with this name. If this also can't be found,
        default (normally None) is returned.
        """
        props = self.getProperties()
        if props.has_key(propkey):
            return props[propkey][-1]
        else:
            globalProps = self.getWikiData().getGlobalProperties()     
            return globalProps.get(u"global."+propkey, default)


    def addProperty(self, key, val):
        values = self.props.get(key)
        if not values:
            values = []
            self.props[key] = values
        values.append(val)
        

    def getTodos(self):
        if self.todos is None:
            self.todos = self.getWikiData().getTodosForWord(self.wikiWord)
                    
        return self.todos
        
    def getNonAliasPage(self):
        """
        If this page belongs to an alias of a wiki word, return a page for
        the real one, otherwise return self.
        This class always returns self
        """
        return self
        

    def getWikiPageTitle(wikiWord):   # static
        title = re.sub(ur'([A-Z\xc0-\xde]+)([A-Z\xc0-\xde][a-z\xdf-\xff])', r'\1 \2', wikiWord)
        title = re.sub(ur'([a-z\xdf-\xff])([A-Z\xc0-\xde])', r'\1 \2', title)
        return title
        
    getWikiPageTitle = staticmethod(getWikiPageTitle)


    def isDefined(self):
        return self.getWikiData().isDefinedWikiWord(self.getWikiWord())
        
        
    def deletePage(self):
        """
        Deletes the page from database
        """
        if self.isDefined():
            self.getWikiData().deleteWord(self.getWikiWord())

        self.fireMiscEventKeys(("deleted page", "deleted wiki page"))


    def informRenamedWikiPage(self, newWord):
        """
        Informs object that the page was renamed to newWord.
        This page object itself does not change its name but becomes invalid!

        This function should be called by WikiDocument(=WikiDataManager) only,
        use WikiDocument.renameWikiWord() to rename a page.
        """
        
        p = {}
        p["renamed page"] = True
        p["renamed wiki page"] = True
        p["newWord"] = newWord
        
        self.fireMiscEventProps(p)


    def getContent(self):
        """
        Returns page content. If page doesn't exist already the template
        creation is done here. After calling this function, properties
        are also accessible for a non-existing page
        """
        content = None

        try:
            content = self.getWikiData().getContent(self.wikiWord)
        except WikiFileNotFoundException, e:
            # Create initial content of new page
            
            # Check if there is exactly one parent
            parents = self.getParentRelationships()
            if len(parents) == 1:
                # Check if there is a template page
                try:
                    parentPage = self.wikiDocument.getWikiPage(parents[0])
                    templateWord = parentPage.getPropertyOrGlobal("template")
                    templatePage = self.wikiDocument.getWikiPage(templateWord)
                    content = templatePage.getContent()
                    # Load also properties from template page (especially pagetype prop.)
                    self.props = templatePage.getProperties()
                except (WikiWordNotFoundException, WikiFileNotFoundException):
                    pass

            if content is None:
                title = self.getWikiPageTitle(self.getWikiWord())
                content = u"%s %s\n\n" % \
                        (self.wikiDocument.getFormatting().getPageTitlePrefix(),
                        title)

        return content


    def getFormatDetails(self):
        """
        According to currently stored settings, return a
        WikiFormatting.WikiPageFormatDetails object to describe
        formatting
        """
        withCamelCase = strToBool(self.getPropertyOrGlobal(
                "camelCaseWordsEnabled"), True)
        
        return WikiFormatting.WikiPageFormatDetails(withCamelCase)


    def extractPropertyTokensFromPageAst(self, pageAst):
        """
        Return a list of property tokens
        """
        return pageAst.findTypeFlat(WikiFormatting.FormatTypes.Property)


    def save(self, text, fireEvent=True):
        """
        Saves the content of current wiki page.
        """
#         self.lastSave = time()
        self.getWikiData().setContent(self.wikiWord, text)
        self.saveDirtySince = None

        # Clear timestamp cache
        self.modified = None


    def update(self, text, fireEvent=True):
        """
        Update additional cached informations (properties, todos, relations)
        """
        formatting = self.wikiDocument.getFormatting()
        
        page = PageAst.Page()
        page.buildAst(formatting, text, self.getFormatDetails())

        self.deleteChildRelationships()
        self.deleteProperties()
        self.deleteTodos()

        todoTokens = page.findType(WikiFormatting.FormatTypes.ToDo)
        for t in todoTokens:
            self.addTodo(t.grpdict["todoName"] + t.grpdict["todoDelimiter"] +
                t.grpdict["todoValue"])

        propTokens = self.extractPropertyTokensFromPageAst(page)
        for t in propTokens:
            propName = t.grpdict["propertyName"]
            propValue = t.grpdict["propertyValue"]
            if propName == u"alias":
                if formatting.isNakedWikiWord(propValue):
                    self.getWikiData().setAsAlias(propValue)
                    self.setProperty(u"alias", propValue)
            else:
                self.setProperty(propName, propValue)

        wwTokens = page.findType(WikiFormatting.FormatTypes.WikiWord)
        for t in wwTokens:
            self.addChildRelationship(t.node.nakedWord)

        # kill the global prop cache in case any props were added
        self.getWikiData().cachedGlobalProps = None

        # add a relationship to the scratchpad at the root
        if self.wikiWord == self.wikiDocument.getWikiName():
            self.addChildRelationship(u"ScratchPad")

        # clear the dirty flag
        self.updateDirtySince = None

        self.getWikiData().updateTodos(self.wikiWord, self.todos)
        self.getWikiData().updateChildRelations(self.wikiWord, self.childRelations)
        self.getWikiData().updateProperties(self.wikiWord, self.props)

#         self.lastUpdate = time()   # self.modified

        if fireEvent:
            ##??? self.mainControl.informWikiPageUpdate(self)  # TODO Remove
            self.fireMiscEventKeys(("updated wiki page", "updated page"))


    def addChildRelationship(self, toWord):
        if toWord not in self.childRelations:
            # if self.wikiData.addRelationship(self.wikiWord, toWord):
            self.childRelations.append(toWord)
        
    def setProperty(self, key, value):
        # if self.wikiData.setProperty(self.wikiWord, key, value):
        self.addProperty(key, value)
        
    def addTodo(self, todo):
        if todo not in self.todos:
            # if self.wikiData.addTodo(self.wikiWord, todo):
            self.todos.append(todo)

    def deleteChildRelationships(self):
        # self.wikiData.deleteChildRelationships(self.wikiWord)
        self.childRelations = []

    def deleteProperties(self):
        # self.wikiData.deleteProperties(self.wikiWord)
        self.props = {}

    def deleteTodos(self):
        # self.wikiData.deleteTodos(self.wikiWord)
        self.todos = []

    def setDirty(self, dirt):
        if dirt:
            if self.saveDirtySince is None:
                ti = time()
                self.saveDirtySince = ti
                self.updateDirtySince = ti
        else:
            self.saveDirtySince = None
            self.updateDirtySince = None

    def getDirty(self):
        return (self.saveDirtySince is not None,
                self.updateDirtySince is not None)

    def getDirtySince(self):
        return (self.saveDirtySince, self.updateDirtySince)


    def getPresentation(self):
        """
        Get the presentation tuple (<cursor pos>, <editor scroll pos x>,
            <e.s.p. y>, <preview s.p. x>, <p.s.p. y>)
        """
        datablock = self.wikiDocument.getWikiData().getPresentationBlock(
                self.getWikiWord())

        if datablock is None or datablock == "":
            return (0, 0, 0, 0, 0)

        try:
            return struct.unpack("iiiii", datablock)
        except struct.error:
            return (0, 0, 0, 0, 0)


    def setPresentation(self, data, startPos):
        """
        Set (a part of) the presentation tuple.
        data -- tuple with new presentation data
        startPos -- start position in the presentation tuple which should be
                overwritten with data.
        """
        pt = self.getPresentation()
        pt = pt[:startPos] + data + pt[startPos+len(data):]

        self.wikiDocument.getWikiData().setPresentationBlock(self.getWikiWord(),
                struct.pack("iiiii", *pt))


# TODO Maybe split into single classes for each tag

class FunctionalPage(DocPage):
    """
    holds the data for a functional page. Such a page controls the behavior
    of the application or a special wiki
    """
    def __init__(self, wikiDocument, funcTag):
        DocPage.__init__(self, wikiDocument)

        self.funcTag = funcTag

        # does this page need to be saved?
        self.saveDirtySince = None  # None if not dirty or timestamp when it became dirty
        self.updateDirtySince = None


    def getWikiWord(self):
        return None
        
    def getFuncTag(self):
        """
        Return the functional tag of the page (a kind of filepath
        for the page)
        """
        return self.funcTag


    def _loadGlobalPage(self, subtag):
        tbLoc = os.path.join(WikidPadStarter.app.getGlobalConfigSubDir(),
                subtag+".wiki")
        try:
            tbFile = open(tbLoc, "rU")
            tbContent = tbFile.read()
            tbFile.close()
            return fileContentToUnicode(tbContent)
        except:
            return u""


    def _loadDbSpecificPage(self, subtag):
        wikiData = self.wikiDocument.getWikiData()
        if wikiData.isDefinedWikiWord(subtag):
            return wikiData.getContent(subtag)
        else:
            return u""

    def getContent(self):     
        if self.funcTag in ("global/[TextBlocks]", "global/[PWL]",
                "global/[CCBlacklist]"):
            return self._loadGlobalPage(self.funcTag[7:])
        elif self.funcTag in ("wiki/[TextBlocks]", "wiki/[PWL]",
                "wiki/[CCBlacklist]"):
            return self._loadDbSpecificPage(self.funcTag[5:])

#     def getContent(self):
#         if self.funcTag == "global/[TextBlocks]":
#             tbLoc = os.path.join(WikidPadStarter.app.getGlobalConfigSubDir(),
#                     "[TextBlocks].wiki")
#             try:
#                 tbFile = open(tbLoc, "rU")
#                 tbContent = tbFile.read()
#                 tbFile.close()
#                 tbContent = fileContentToUnicode(tbContent)
#             except:
#                 tbContent = u""
#         elif self.funcTag == "global/[PWL]":
#             tbLoc = os.path.join(WikidPadStarter.app.getGlobalConfigSubDir(),
#                     "[PWL].wiki")
#             try:
#                 tbFile = open(tbLoc, "rU")
#                 tbContent = tbFile.read()
#                 tbFile.close()
#                 tbContent = fileContentToUnicode(tbContent)
#             except:
#                 tbContent = u""
#         elif self.funcTag == "wiki/[TextBlocks]":
#             wikiData = self.wikiDocument.getWikiData()
#             if wikiData.isDefinedWikiWord("[TextBlocks]"):
#                 tbContent = wikiData.getContent("[TextBlocks]")
#             else:
#                 tbContent = u""
#         elif self.funcTag == "wiki/[PWL]":
#             wikiData = self.wikiDocument.getWikiData()
#             if wikiData.isDefinedWikiWord("[PWL]"):
#                 tbContent = wikiData.getContent("[PWL]")
#             else:
#                 tbContent = u""
# 
#         return tbContent


    def getFormatDetails(self):
        """
        According to currently stored settings, return a
        WikiFormatting.WikiPageFormatDetails object to describe
        formatting.
        
        For functional pages this is normally no formatting
        """
        return WikiFormatting.WikiPageFormatDetails(noFormat=True)


    def _saveGlobalPage(self, text, subtag):
        tbLoc = os.path.join(WikidPadStarter.app.getGlobalConfigSubDir(),
                subtag+".wiki")
        tbFile = open(tbLoc, "w")
        try:
            tbFile.write(BOM_UTF8)
            tbFile.write(utf8Enc(text)[0])
        finally:
            tbFile.close()
        
    def _saveDbSpecificPage(self, text, subtag):
        wikiData = self.wikiDocument.getWikiData()
        if wikiData.isDefinedWikiWord(subtag) and text == u"":
            # Delete content
            wikiData.deleteContent(subtag)
        else:
            if text != u"":
                wikiData.setContent(subtag, text)



    def save(self, text, fireEvent=True):
        """
        Saves the content of current wiki page.
        """
        
        if self.funcTag in ("global/[TextBlocks]", "global/[PWL]",
                "global/[CCBlacklist]"):
            self._saveGlobalPage(text, self.funcTag[7:])
        elif self.funcTag in ("wiki/[TextBlocks]", "wiki/[PWL]",
                "wiki/[CCBlacklist]"):
            self._saveDbSpecificPage(text, self.funcTag[5:])

        self.saveDirtySince = None


#         if self.funcTag == "global/[TextBlocks]":
#             tbLoc = os.path.join(WikidPadStarter.app.getGlobalConfigSubDir(),
#                     "[TextBlocks].wiki")
# #             tbLoc = os.path.join(self.pWiki.globalConfigSubDir, "[TextBlocks].wiki")
#             tbFile = open(tbLoc, "w")
#             try:
#                 tbFile.write(BOM_UTF8)
#                 tbFile.write(utf8Enc(text)[0])
#             finally:
#                 tbFile.close()
#         elif self.funcTag == "global/[PWL]":
#             tbLoc = os.path.join(WikidPadStarter.app.getGlobalConfigSubDir(),
#                     "[PWL].wiki")
# #             tbLoc = os.path.join(self.pWiki.globalConfigSubDir, "[PWL].wiki")
#             tbFile = open(tbLoc, "w")
#             try:
#                 tbFile.write(BOM_UTF8)
#                 tbFile.write(utf8Enc(text)[0])
#             finally:
#                 tbFile.close()
#         elif self.funcTag == "wiki/[TextBlocks]":
#             wikiData = self.wikiDocument.getWikiData()
#             if wikiData.isDefinedWikiWord("[TextBlocks]") and text == u"":
#                 # Delete content
#                 wikiData.deleteContent("[TextBlocks]")
#             else:
#                 if text != u"":
#                     wikiData.setContent("[TextBlocks]", text)
#         elif self.funcTag == "wiki/[PWL]":
#             wikiData = self.wikiDocument.getWikiData()
#             if wikiData.isDefinedWikiWord("[PWL]") and text == u"":
#                 # Delete content
#                 wikiData.deleteContent("[PWL]")
#             else:
#                 if text != u"":
#                     wikiData.setContent("[PWL]", text)


    def update(self, text, fireEvent=True):
        """
        Update additional cached informations (properties, todos, relations)
        """
        # clear the dirty flag
        self.updateDirtySince = None

        if fireEvent:
            if self.funcTag in ("global/[TextBlocks]", "wiki/[TextBlocks]"):
                # The text blocks for the text blocks submenu was updated
                self.fireMiscEventKeys(("updated func page", "updated page",
                        "reread text blocks needed"))
#                 self.pWiki.rereadTextBlocks()   # TODO!
            elif self.funcTag in ("global/[PWL]", "wiki/[PWL]"):
                # The personal word list (words to ignore by spell checker)
                # was updated
                self.fireMiscEventKeys(("updated func page", "updated page",
                        "reread personal word list needed"))
#             if fireEvent and self.pWiki.spellChkDlg is not None:
#                 self.pWiki.spellChkDlg.rereadPersonalWordLists()
            elif self.funcTag in ("global/[CCBlacklist]", "wiki/[CCBlacklist]"):
                # The blacklist of camelcase words not to mark as wiki links
                # was updated
                self.fireMiscEventKeys(("updated func page", "updated page",
                        "reread cc blacklist needed"))


    def setDirty(self, dirt):
        if dirt:
            if self.saveDirtySince is None:
                ti = time()
                self.saveDirtySince = ti
                self.updateDirtySince = ti
        else:
            self.saveDirtySince = None
            self.updateDirtySince = None

    def getDirty(self):
        return (self.saveDirtySince is not None,
                self.updateDirtySince is not None)

    def getDirtySince(self):
        return (self.saveDirtySince, self.updateDirtySince)

    def getPresentation(self):
        """Dummy"""
        return (0, 0, 0, 0, 0)

    def setPresentation(self, data, startPos):
        """Dummy"""
        pass

