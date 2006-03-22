from time import time
import os.path, re

from MiscEvent import MiscEventSourceMixin

from WikiExceptions import *   # TODO make normal import?

from StringOps import strToBool, fileContentToUnicode, BOM_UTF8, utf8Enc

import WikiFormatting
import PageAst


class DocPage(MiscEventSourceMixin):
    """
    Abstract common base class for WikiPage and FunctionalPage
    """
    def __init__(self, wikiDataManager):
        MiscEventSourceMixin.__init__(self)
        
        self.wikiDataManager = wikiDataManager
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
            wikiData = self.wikiDataManager()
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
            self.update(text, False)   # TODO: Really update? Handle auto-generated areas


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




class WikiPage(DocPage):
    """
    holds the data for a wikipage. fetched via the WikiDataManager.getWikiPage method.
    """
    def __init__(self, wikiDataManager, wikiWord):
        DocPage.__init__(self, wikiDataManager)

        self.wikiData = self.wikiDataManager.getWikiData()

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


    def getTimestamps(self):
        if self.modified is None:
            self.modified, self.created = \
                    self.wikiData.getTimestamps(self.wikiWord)
                    
        if self.modified is None:
            ti = time()
            self.modified, self.created = ti, ti
        
        return self.modified, self.created

    def getParentRelationships(self):
        if self.parentRelations is None:
            self.parentRelations = \
                    self.wikiData.getParentRelationships(self.wikiWord)
        
        return self.parentRelations

        
    def getChildRelationships(self, existingonly=False, selfreference=True,
            withPosition=False):
        """
        Does not support caching
        """
        return self.wikiData.getChildRelationships(self.wikiWord,
                existingonly, selfreference, withPosition=withPosition)


#     def getChildRelationshipsAndHasChildren(self, existingonly=False,
#             selfreference=True):
#         """
#         Does not support caching
#         """
#         return self.wikiData.getChildRelationshipsAndHasChildren(self.wikiWord,
#                 existingonly, selfreference)

    def getProperties(self):
        if self.props is None:
            data = self.wikiData.getPropertiesForWord(self.wikiWord)
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
            return props[propkey][0]
        else:
            globalProps = self.wikiData.getGlobalProperties()     
            return globalProps.get(u"global."+propkey, default)


    def addProperty(self, key, val):
        values = self.props.get(key)
        if not values:
            values = []
            self.props[key] = values
        values.append(val)
        

    def getTodos(self):
        if self.todos is None:
            self.todos = self.wikiData.getTodosForWord(self.wikiWord)
                    
        return self.todos
        
    def getNonAliasPage(self):
        """
        If this page belongs to an alias of a wiki word, return a page for
        the real one, otherwise return self
        """
        if not self.wikiData.isAlias(self.wikiWord):
            return self
        
        word = self.wikiData.getAliasesWikiWord(self.wikiWord)
        return self.wikiDataManager.getWikiPageNoError(word)
        

    def _getWikiPageTitle(self, wikiWord):
        title = re.sub(ur'([A-Z\xc0-\xde]{2,})([a-z\xdf-\xff])', r'\1 \2', wikiWord)
        title = re.sub(ur'([a-z\xdf-\xff])([A-Z\xc0-\xde])', r'\1 \2', title)
        return title


    def isDefined(self):
        return self.wikiData.isDefinedWikiWord(self.getWikiWord())

    def getContent(self):
        """
        Returns page content. If page doesn't exist already the template
        creation is done here. After calling this function, properties
        are also accessible for a non-existing page
        """
        content = None

        try:
            content = self.wikiData.getContent(self.wikiWord)
        except WikiFileNotFoundException, e:
            # Create initial content of new page
            
            # Check if there is exactly one parent
            parents = self.getParentRelationships()
            if len(parents) == 1:
                # Check if there is a template page
                try:
                    parentPage = self.wikiDataManager.getWikiPage(parents[0])
                    templateWord = parentPage.getPropertyOrGlobal("template")
                    templatePage = self.wikiDataManager.getWikiPage(templateWord)
                    content = templatePage.getContent()
                    # Load also properties from template page (especially pagetype prop.)
                    self.props = templatePage.getProperties()
                except (WikiWordNotFoundException, WikiFileNotFoundException):
                    pass

            if content is None:
                title = self._getWikiPageTitle(self.getWikiWord())
                content = u"++ %s\n\n" % title

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


    def save(self, text, fireEvent=True):
        """
        Saves the content of current wiki page.
        """
#         self.lastSave = time()
        self.wikiData.setContent(self.wikiWord, text)
        self.saveDirtySince = None

        # Clear timestamp cache
        self.modified = None


    def update(self, text, fireEvent=True):
        """
        Update additional cached informations (properties, todos, relations)
        """
        formatting = self.wikiData.pWiki.getFormatting()
        
        page = PageAst.Page()
        page.buildAst(formatting, text, self.getFormatDetails())

        self.deleteChildRelationships()
        self.deleteProperties()
        self.deleteTodos()
        
        todoTokens = page.findType(WikiFormatting.FormatTypes.ToDo)
        for t in todoTokens:
            self.addTodo(t.grpdict["todoName"] + t.grpdict["todoDelimiter"] +
                t.grpdict["todoValue"])

        # Do not search for properties in subtoken
        propTokens = page.findTypeFlat(WikiFormatting.FormatTypes.Property)
        for t in propTokens:
            propName = t.grpdict["propertyName"]
            propValue = t.grpdict["propertyValue"]
            if propName == u"alias":
                if formatting.isNakedWikiWord(propValue):
                    self.wikiData.setAsAlias(propValue)
                    self.setProperty(u"alias", propValue)
            else:
                self.setProperty(propName, propValue)

        wwTokens = page.findType(WikiFormatting.FormatTypes.WikiWord)
        for t in wwTokens:
            self.addChildRelationship(t.node.nakedWord)

        # kill the global prop cache in case any props were added
        self.wikiData.cachedGlobalProps = None

        # add a relationship to the scratchpad at the root
        if self.wikiWord == self.wikiData.pWiki.wikiName:
            self.addChildRelationship(u"ScratchPad")

        # clear the dirty flag
        self.updateDirtySince = None

        self.wikiData.updateTodos(self.wikiWord, self.todos)
        self.wikiData.updateChildRelations(self.wikiWord, self.childRelations)
        self.wikiData.updateProperties(self.wikiWord, self.props)

#         self.lastUpdate = time()   # self.modified

        if fireEvent:
            self.wikiData.pWiki.informWikiPageUpdate(self)  # TODO Remove
            self.fireMiscEventKeys(("wiki page updated", "page updated"))


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




class FunctionalPage(DocPage):
    """
    holds the data for a functional page. Such a page controls the behavior
    of the application or a special wiki
    """
    def __init__(self, pWiki, wikiDataManager, funcTag):
        DocPage.__init__(self, wikiDataManager)

        self.pWiki = pWiki
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


    def getContent(self):
        if self.funcTag == "global/[TextBlocks]":
            tbLoc = os.path.join(self.pWiki.globalConfigSubDir, "[TextBlocks].wiki")
            try:
                tbFile = open(tbLoc, "rU")
                tbContent = tbFile.read()
                tbFile.close()
                tbContent = fileContentToUnicode(tbContent)
            except:
                tbContent = u""
        elif self.funcTag == "wiki/[TextBlocks]":
            wikiData = self.wikiDataManager.getWikiData()
            if wikiData.isDefinedWikiWord("[TextBlocks]"):
                tbContent = wikiData.getContent("[TextBlocks]")
            else:
                tbContent = u""

        return tbContent


    def getFormatDetails(self):
        """
        According to currently stored settings, return a
        WikiFormatting.WikiPageFormatDetails object to describe
        formatting.
        
        For functional pages this is normally no formatting
        """
        return WikiFormatting.WikiPageFormatDetails(noFormat=True)


    def save(self, text, fireEvent=True):
        """
        Saves the content of current wiki page.
        """
#         self.wikiData.setContent(self.wikiWord, text)

        if self.funcTag == "global/[TextBlocks]":
            tbLoc = os.path.join(self.pWiki.globalConfigSubDir, "[TextBlocks].wiki")
            tbFile = open(tbLoc, "w")

            try:
                tbFile.write(BOM_UTF8)
                tbFile.write(utf8Enc(text)[0])
            finally:
                tbFile.close()
        elif self.funcTag == "wiki/[TextBlocks]":
            wikiData = self.wikiDataManager.getWikiData()
            if wikiData.isDefinedWikiWord("[TextBlocks]") and text == u"":
                # Delete content
                wikiData.deleteContent("[TextBlocks]")
            else:
                if text != u"":
                    wikiData.setContent("[TextBlocks]", text)

        self.saveDirtySince = None


    def update(self, text, fireEvent=True):
        """
        Update additional cached informations (properties, todos, relations)
        """
        # clear the dirty flag
        self.updateDirtySince = None

        if self.funcTag in ("global/[TextBlocks]", "wiki/[TextBlocks]"):
            if fireEvent:
                self.pWiki.rereadTextBlocks()


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

