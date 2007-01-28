from time import time
import os.path, re, struct, sets, traceback

from MiscEvent import MiscEventSourceMixin

from WikiExceptions import *   # TODO make normal import?

from StringOps import strToBool, fileContentToUnicode, BOM_UTF8, utf8Enc, \
        utf8Dec

import WikiFormatting
import PageAst

from wxPython.wx import wxGetApp


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
        txtEditor = self.getTxtEditor()
        if txtEditor is not None:
            # page is in text editor(s), so call AppendText on one of it
            txtEditor.AppendText(text)
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
        txtEditor = self.getTxtEditor()
        if txtEditor is not None:
            # page is in text editor(s), so call AppendText on one of it
            return txtEditor.GetText()
        else:
            return self.getContent()


    def getLiveTextNoTemplate(self):
        """
        Return None if page isn't existing instead of creating an automatic
        live text (e.g. by template).
        """
        assert 0 #abstract


    def replaceLiveText(self, text):
        txtEditor = self.getTxtEditor()
        if txtEditor is not None:
            # page is in text editor(s), so call replace on one of it
            txtEditor.replaceText(text)
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


    def getTitle(self):
        """
        Return human readable title of the page.
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

    def getTitle(self):
        """
        Return human readable title of the page.
        """
        return self.aliasWikiWord


#     def addTxtEditor(self, txted):
#         """
#         Add txted to the list of editors (views) showing this page.
#         """
#         print "AliasWikiPage addTxtEditor1", repr(self.aliasWikiWord)
#         return self.realWikiPage.addTxtEditor(txted)
# 
#     def removeTxtEditor(self, txted):
#         """
#         Remove txted from the list of editors (views) showing this page.
#         """
#         return self.realWikiPage.removeTxtEditor(txted)
# 
#     def getTxtEditor(self):
#         """
#         Returns an arbitrary text editor associated with the page
#         or None if no editor is associated.
#         """
#         print "AliasWikiPage getTxtEditor1", repr(self.aliasWikiWord), repr(self.realWikiPage.getTxtEditor())
#         return self.realWikiPage.getTxtEditor()


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
        
    def getTitle(self):
        """
        Return human readable title of the page.
        """
        return self.getWikiWord()

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
            withPosition=False, excludeSet=sets.ImmutableSet()):
        """
        get the child relations of this word
        existingonly -- List only existing wiki words
        selfreference -- List also wikiWord if it references itself
        withPositions -- Return tuples (relation, firstcharpos) with char.
            position of link in page (may be -1 to represent unknown)
        excludeSet -- set of words which should be excluded from the list

        Does not support caching
        """
        
        relations = self.getWikiData().getChildRelationships(self.wikiWord,
                existingonly, selfreference, withPosition=withPosition)
                
        if len(excludeSet) > 0:
            # Filter out members of excludeSet
            if withPosition:
                relations = [r for r in relations if not r[0] in excludeSet]
            else:
                relations = [r for r in relations if not r in excludeSet]

        return relations


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


    def getLiveTextNoTemplate(self):
        """
        Return None if page isn't existing instead of creating an automatic
        live text (e.g. by template).
        """
        if self.getTxtEditor() is not None:
            return self.getLiveText()
        else:
            if self.isDefined():
                return self.getContent()
            else:
                return None


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


    _DEFAULT_PRESENTATION = (0, 0, 0, 0, 0)

    def getPresentation(self):
        """
        Get the presentation tuple (<cursor pos>, <editor scroll pos x>,
            <e.s.p. y>, <preview s.p. x>, <p.s.p. y>)
        """
        wikiData = self.wikiDocument.getWikiData()

        if wikiData is None:
            return WikiPage._DEFAULT_PRESENTATION

        datablock = wikiData.getPresentationBlock(
                self.getWikiWord())

        if datablock is None or datablock == "":
            return WikiPage._DEFAULT_PRESENTATION

        try:
            return struct.unpack("iiiii", datablock)
        except struct.error:
            return WikiPage._DEFAULT_PRESENTATION


    def setPresentation(self, data, startPos):
        """
        Set (a part of) the presentation tuple. This is silently ignored
        if the "write access failed" or "read access failed" flags are
        set in the wiki document.
        data -- tuple with new presentation data
        startPos -- start position in the presentation tuple which should be
                overwritten with data.
        """
        if self.wikiDocument.getReadAccessFailed() or \
                self.wikiDocument.getWriteAccessFailed():
            return

        try:
            pt = self.getPresentation()
            pt = pt[:startPos] + data + pt[startPos+len(data):]
    
            wikiData = self.wikiDocument.getWikiData()
            if wikiData is None:
                return

            wikiData.setPresentationBlock(self.getWikiWord(),
                    struct.pack("iiiii", *pt))
        except AttributeError:
            traceback.print_exc()
#         self.setDirty(True)


    # ----- Advanced functions -----

    def getChildRelationshipsTreeOrder(self, existingonly=False,
            excludeSet=sets.ImmutableSet()):
        """
        Return a list of children wiki words of the page, ordered as they would
        appear in tree. Some children may be missing if they e.g.
        are set as hidden.
        excludeSet -- set of words which should be excluded from the list
        existingonly -- true iff non-existing words should be hidden
        """
        
        wikiDocument = self.wikiDocument
        
        # get the sort order for the children
        childSortOrder = self.getPropertyOrGlobal(u'child_sort_order',
                u"ascending")
            
        # Apply sort order
        if childSortOrder == u"natural":
            # Retrieve relations as list of tuples (child, firstcharpos)
            relations = self.getChildRelationships(existingonly,
                    selfreference=False, withPosition=True,
                    excludeSet=excludeSet)
            relations.sort(_cmpCharPosition)
            # Remove firstcharpos
            relations = [r[0] for r in relations]
        else:
            # Retrieve relations as list of children words
            relations = self.getChildRelationships(existingonly, 
                    selfreference=False, withPosition=False,
                    excludeSet=excludeSet)
            if childSortOrder.startswith(u"desc"):
                coll = wikiDocument.getCollator()

                def cmpLowerDesc(a, b):
                    return coll.strcoll(
                            b.lower(), a.lower())

                relations.sort(cmpLowerDesc) # sort alphabetically
            elif childSortOrder.startswith(u"asc"):
                coll = wikiDocument.getCollator()

                def cmpLowerAsc(a, b):
                    return coll.strcoll(
                            a.lower(), b.lower())

                relations.sort(cmpLowerAsc)

        relationData = []
        position = 1
        for relation in relations:
            relationPage = wikiDocument.getWikiPageNoError(relation)
            relationData.append((relation, relationPage, position))
            position += 1

        # Sort again, using tree position and priority properties
        relationData.sort(_relationSort)

        return [rd[0] for rd in relationData]


        # TODO Remove aliases?
    def _flatTreeHelper(self, page, deepness, excludeSet, result):
        """
        Recursive part of getFlatTree
        """
        children = page.getChildRelationshipsTreeOrder(existingonly=True,
                excludeSet=excludeSet)
                
        subExcludeSet = excludeSet.copy()
        # subExcludeSet.add(page.getWikiWord())
        subExcludeSet.union_update(children)
        for c in children:
            subpage = self.wikiDocument.getWikiPage(c)
            result.append((c, deepness + 1))
            self._flatTreeHelper(subpage, deepness + 1, subExcludeSet, result)


    def getFlatTree(self):
        """
        Returns a sequence of tuples (word, deepness) where the current
        word is the first one with deepness 0.
        TODO EXPLAIN FUNCTION !!!
        """
        result = [(self.getWikiWord(), 0)]
        excludeSet = sets.Set((self.getWikiWord(),))
        
        self._flatTreeHelper(self, 0, excludeSet, result)
        
        return result



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

    def getTitle(self):
        """
        Return human readable title of the page.
        """
        return u"<" + getHrNameForFuncTag(self.funcTag) + u">"


    def getFuncTag(self):
        """
        Return the functional tag of the page (a kind of filepath
        for the page)
        """
        return self.funcTag


    def _loadGlobalPage(self, subtag):
        tbLoc = os.path.join(wxGetApp().getGlobalConfigSubDir(),
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


    def getLiveTextNoTemplate(self):
        """
        Return None if page isn't existing instead of creating an automatic
        live text (e.g. by template).
        Functional pages by definition exist always 
        """
        return self.getLiveText()


    def getContent(self):     
        if self.funcTag in ("global/[TextBlocks]", "global/[PWL]",
                "global/[CCBlacklist]"):
            return self._loadGlobalPage(self.funcTag[7:])
        elif self.funcTag in ("wiki/[TextBlocks]", "wiki/[PWL]",
                "wiki/[CCBlacklist]"):
            return self._loadDbSpecificPage(self.funcTag[5:])


    def getFormatDetails(self):
        """
        According to currently stored settings, return a
        WikiFormatting.WikiPageFormatDetails object to describe
        formatting.
        
        For functional pages this is normally no formatting
        """
        return WikiFormatting.WikiPageFormatDetails(noFormat=True)


    def _saveGlobalPage(self, text, subtag):
        tbLoc = os.path.join(wxGetApp().getGlobalConfigSubDir(),
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



# Two search helpers for WikiPage.getChildRelationshipsTreeOrder

def _relationSort(a, b):
    propsA = a[1].getProperties()
    propsB = b[1].getProperties()

    aSort = None
    bSort = None

    try:
        if (propsA.has_key(u'tree_position')):
            aSort = int(propsA[u'tree_position'][-1])
        elif (propsA.has_key(u'priority')):
            aSort = int(propsA[u'priority'][-1])
        else:
            aSort = a[2]
    except:
        aSort = a[2]

    try:            
        if (propsB.has_key(u'tree_position')):
            bSort = int(propsB[u'tree_position'][-1])
        elif (propsB.has_key(u'priority')):
            bSort = int(propsB[u'priority'][-1])
        else:
            bSort = b[2]
    except:
        bSort = b[2]

    return cmp(aSort, bSort)


def _cmpCharPosition(a, b):
    """
    Compare "natural", means using the char. positions of the links in page
    """
    return int(a[1] - b[1])


_FUNCTAG_TO_HR_NAME_MAP = {
            "global/[TextBlocks]": u"Global text blocks",
            "wiki/[TextBlocks]": u"Wiki text blocks",
            "global/[PWL]": "Global spell list",
            "wiki/[PWL]": "Wiki spell list",
            "global/[CCBlacklist]": "Global cc. blacklist",
            "wiki/[CCBlacklist]": "Wiki cc. blacklist"
        }


def getHrNameForFuncTag(funcTag):
    """
    Return the human readable name of functional page with tag funcTag.
    """
    return _FUNCTAG_TO_HR_NAME_MAP.get(funcTag, funcTag)
