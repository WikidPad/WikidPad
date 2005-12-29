from time import time

from WikiExceptions import *   # TODO make normal import?
import WikiFormatting
import PageAst


class WikiPage:
    """
    holds the data for a wikipage. fetched via the WikiData.getPage method.
    """
    def __init__(self, wikiData, wikiWord):
        self.wikiData = wikiData
        self.wikiWord = wikiWord
#         self.wikiFile = self.wikiData.getWikiWordFileName(self.wikiWord)
        self.parentRelations = None
        self.todos = None
        self.props = None
        self.modified, self.created = None, None

        # does this page need to be saved?
        self.saveDirty = False
        self.updateDirty = False

        # save when this page was last saved
        self.lastSave = time()

        # save when this page was last saved
        self.lastUpdate = time()


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

        
    def getChildRelationships(self, existingonly=False, selfreference=True):
        """
        Does not support caching
        """
        return self.wikiData.getChildRelationships(self.wikiWord,
                existingonly, selfreference)


    def getChildRelationshipsAndHasChildren(self, existingonly=False,
            selfreference=True):
        """
        Does not support caching
        """
        return self.wikiData.getChildRelationshipsAndHasChildren(self.wikiWord,
                existingonly, selfreference)

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
        return WikiPage(self.wikiData, word)


    def getContent(self):
        return self.wikiData.getContent(self.wikiWord)


    def save(self, text, alertPWiki=True):
        """
        Saves the content of current wiki page.
        """
        self.lastSave = time()
        self.wikiData.setContent(self.wikiWord, text)
        self.saveDirty = False


    def update(self, text, alertPWiki=True):
        """
        Update additional cached informations (properties, todos, relations)
        """
        self.deleteChildRelationships()
        self.deleteProperties()
        self.deleteTodos()
        
        formatting = self.wikiData.pWiki.getFormatting()
        
        page = PageAst.Page()
        page.buildAst(formatting, text)
        
        todoTokens = page.findType(WikiFormatting.FormatTypes.ToDo)
        for t in todoTokens:
            self.addTodo(t.grpdict["todoName"] + t.grpdict["todoDelimiter"] +
                t.grpdict["todoValue"])
        
        propTokens = page.findType(WikiFormatting.FormatTypes.Property)
        for t in propTokens:
            propName = t.grpdict["propertyName"]
            propValue = t.grpdict["propertyValue"]
            if propName == u"alias":
                word = formatting.normalizeWikiWord(propValue)
                if word is not None:
                    self.wikiData.cachedWikiWords[word] = 2
                    self.setProperty(u"alias", word)
            else:
                self.setProperty(propName, propValue)

        wwTokens = page.findType(WikiFormatting.FormatTypes.WikiWord)
        for t in wwTokens:
            self.addChildRelationship(
                    formatting.normalizeWikiWord(t.text))

        self.lastUpdate = time()   # self.modified

        # kill the global prop cache in case any props were added
        self.wikiData.cachedGlobalProps = None

        # add a relationship to the scratchpad at the root
        if self.wikiWord == self.wikiData.pWiki.wikiName:
            self.addChildRelationship(u"ScratchPad")

        # clear the dirty flag
        self.updateDirty = False

        self.wikiData.updateTodos(self.wikiWord, self.todos)
        self.wikiData.updateChildRelations(self.wikiWord, self.childRelations)
        self.wikiData.updateProperties(self.wikiWord, self.props)

        if alertPWiki:
            self.wikiData.pWiki.informWikiPageUpdate(self)

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
        self.saveDirty = dirt
        self.updateDirty = dirt

    def getDirty(self):
        return (self.saveDirty, self.updateDirty)


####################################################
# module level functions
####################################################


def findShortestPath(graph, start, end, path):   # path=[]
    "finds the shortest path in the graph from start to end"
    path = path + [start]
    if start == end:
        return path
    if not graph.has_key(start):
        return None
    shortest = None
    for node in graph[start]:
        if node not in path:
            newpath = findShortestPath(graph, node, end, path)
            if newpath:
                if not shortest or len(newpath) < len(shortest):
                    shortest = newpath

    return shortest
