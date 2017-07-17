
## import profilehooks
## profile = profilehooks.profile(filename="profile.prf", immediate=False)


import os.path, re, struct, time, traceback, collections

from .rtlibRepl import minidom

import wx

from .MiscEvent import MiscEventSourceMixin, KeyFunctionSinkAR

import Consts
from .WikiExceptions import *

from .StringOps import strToBool, fileContentToUnicode, lineendToInternal, \
        loadEntireTxtFile, writeEntireFile

from . import Utilities
from .Utilities import DUMBTHREADSTOP, FunctionThreadStop, TimeoutRLock, \
        callInMainThread, callInMainThreadAsync

from .WikiPyparsing import buildSyntaxNode
from . import ParseUtilities

from . import Serialization



# Dummy
UNDEFINED = object()


class DocPage(MiscEventSourceMixin):
    """
    Abstract common base class for WikiPage and FunctionalPage
    """

    def __init__(self, wikiDocument):
        MiscEventSourceMixin.__init__(self)
        
        self.wikiDocument = wikiDocument
        self.txtEditors = []  # List of all editors (views) showing this page
        self.livePageAst = None   # Cached page AST of live text

        # lock while building live AST
        self.livePageAstBuildLock = TimeoutRLock(Consts.DEADBLOCKTIMEOUT)

        # lock while setting, getting or saving self.editorText and some other ops
        self.textOperationLock = TimeoutRLock(Consts.DEADBLOCKTIMEOUT)

        # lock while changing or reading self.txtEditors list
        self.txtEditorListLock = TimeoutRLock(Consts.DEADBLOCKTIMEOUT)
        self.editorText = None  # Contains editor text, 
                # if no text editor is registered, this cache is invalid
#         self.pageState = STATE_TEXTCACHE_MATCHES_EDITOR


    def invalidate(self):
        """
        Make page invalid to prevent yet running threads from changing
        database.
        """
        with self.textOperationLock:
            with self.txtEditorListLock:
                # self.wikiDocument = None
                self.txtEditors = None
                self.livePageAst = None
                self.setEditorText(None)


    def isInvalid(self):
        return self.txtEditors is None

    def getTextOperationLock(self):
        return self.textOperationLock

    def getWikiDocument(self):
        return self.wikiDocument
        
    def setEditorText(self, text, dirty=True):
        """
        Just set editor text. Derived class overwrites this to set flags
        """
        with self.textOperationLock:
            self.editorText = text
            self.livePageAst = None


    def getEditorText(self):
        return self.editorText

    def addTxtEditor(self, txted):
        """
        Add txted to the list of editors (views) showing this page.
        """
        # TODO Set text in editor if first editor is created?
        with self.txtEditorListLock:
            if not txted in self.txtEditors:
                if len(self.txtEditors) == 0:
                    with self.textOperationLock:
                        # We are assuming that editor content came from
                        # database
                        self.setEditorText(txted.GetText(), dirty=False)

                self.txtEditors.append(txted)


    def removeTxtEditor(self, txted):
        """
        Remove txted from the list of editors (views) showing this page.
        If the last is removed, text is saved to database.
        """
        with self.txtEditorListLock:
            try:
                idx = self.txtEditors.index(txted)
                if len(self.txtEditors) == 1:
                    self.setEditorText(None)

                del self.txtEditors[idx]
    
            except ValueError:
                # txted not in list
                pass

    def getTxtEditor(self):
        """
        Returns an arbitrary text editor associated with the page
        or None if no editor is associated.
        """
        with self.txtEditorListLock:
            if len(self.txtEditors) > 0:
                return self.txtEditors[0]
            else:
                return None


    def getLiveText(self):
        """
        Return current text of page, either from a text editor or
        from the database
        """
        with self.textOperationLock:
            if self.getEditorText() is not None:
                return self.getEditorText()
            
            return self.getContent()



    def getLiveTextNoTemplate(self):
        """
        Return None if page isn't existing instead of creating an automatic
        live text (e.g. by template).
        """
        raise NotImplementedError   # abstract


    def appendLiveText(self, text, fireEvent=True):
        """
        Append some text to page which is either loaded in one or more
        editor(s) or only stored in the database (with automatic update).

        fireEvent -- Send event if database was directly modified
        """
        with self.textOperationLock:
            if self.isReadOnlyEffect():
                return

            self.setDirty(True)
            txtEditor = self.getTxtEditor()
            self.livePageAst = None
            if txtEditor is not None:
                # page is in text editor(s), so call AppendText on one of it
                # TODO Call self.SetReadOnly(False) first?
                txtEditor.AppendText(text)
                return

            # Modify database
            text = self.getContent() + text
            self.writeToDatabase(text, fireEvent=fireEvent)


    def replaceLiveText(self, text, fireEvent=True):
        with self.textOperationLock:
            if self.isReadOnlyEffect():
                return

            self.setDirty(True)
            txtEditor = self.getTxtEditor()
            self.livePageAst = None
            if txtEditor is not None:
                # page is in text editor(s), so call replace on one of it
                # TODO Call self.SetReadOnly(False) first?
                txtEditor.replaceText(text)
                return

            self.writeToDatabase(text, fireEvent=fireEvent)


    def informEditorTextChanged(self, changer):
        """
        Called by the txt editor control. Must be called in GUI(=main) thread
        """
        with self.textOperationLock:
            txtEditor = self.getTxtEditor()
            self.setEditorText(txtEditor.GetText())

        self.fireMiscEventProps({"changed editor text": True,
                "changed live text": True, "changer": changer})


    def informVisited(self):
        """
        Called to inform the page that it was visited and should set
        the "visited" entry in the database to current time.
        """
        self.fireMiscEventProps({"visited doc page": True})


    def getWikiLanguageName(self):
        """
        Returns the internal name of the wiki language of this page.
        """
        return self.wikiDocument.getWikiDefaultWikiLanguage()



    def createWikiLanguageHelper(self):
        return wx.GetApp().createWikiLanguageHelper(self.getWikiLanguageName())


    def getContent(self):
        """
        Returns page content. If page doesn't exist already some content
        is created automatically (may be empty string).
        """
        raise NotImplementedError #abstract

    def setDirty(self, dirt):
        raise NotImplementedError #abstract

    def getDirty(self):
        raise NotImplementedError #abstract


    def getTitle(self):
        """
        Return human readable title of the page.
        """
        raise NotImplementedError #abstract


    def getUnifiedPageName(self):
        """
        Return the name of the unified name of the page, which is
        "wikipage/" + the wiki word for wiki pages or the functional tag
        for functional pages.
        """
        raise NotImplementedError #abstract


    def isReadOnlyEffect(self):
        """
        Return true if page is effectively read-only, this means
        "for any reason", regardless if error or intention.
        """
        return (self.wikiDocument is None) or self.wikiDocument.isReadOnlyEffect()


    def writeToDatabase(self, text=None, fireEvent=True):
        """
        Write current text to database and initiate update of meta-data.
        """
        with self.textOperationLock:
            if self.isReadOnlyEffect():
                return

            s, u = self.getDirty()
            if s:
                if text is None:
                    text = self.getLiveText()
                self._save(text, fireEvent=fireEvent)
                self.initiateUpdate(fireEvent=fireEvent)
            elif u:
                self.initiateUpdate(fireEvent=fireEvent)
            else:
                if self.getMetaDataState() < \
                        self.getWikiDocument().getFinalMetaDataState():
                    self.updateDirtySince = time.time()
                    self.initiateUpdate(fireEvent=fireEvent)


    def _save(self, text, fireEvent=True):
        """
        Saves the content of current doc page.
        """
        raise NotImplementedError #abstract


    def initiateUpdate(self, fireEvent=True):
        """
        Initiate update of page meta-data. This function may call update
        directly if can be done fast
        """
        raise NotImplementedError #abstract


#     def _update(self, fireEvent=True):
#         """
#         Update additional cached informations of doc page
#         """
#         raise NotImplementedError #abstract



class AliasWikiPage(DocPage):
    """
    Fake page for an alias name of a wiki page. Most functions are delegated
    to underlying real page
    Fetched via the WikiDocument.getWikiPage method.
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
        
    def getUnifiedPageName(self):
        """
        Return the name of the unified name of the page, which is
        "wikipage/" + the wiki word for wiki pages or the functional tag
        for functional pages.
        """
        return "wikipage/" + self.aliasWikiWord

    def getNonAliasPage(self):
        """
        If this page belongs to an alias of a wiki word, return a page for
        the real one, otherwise return self
        """
        return self.realWikiPage
#         word = self.wikiDocument.getWikiData().getWikiPageNameForLinkTerm(self.wikiWord)
#         return self.wikiDocument.getWikiPageNoError(word)

    def getContent(self):
        """
        Returns page content. If page doesn't exist already some content
        is created automatically (may be empty string).
        """
        return self.realWikiPage.getContent()


    def setDirty(self, dirt):
        return self.realWikiPage.setDirty(dirt)

    def _save(self, text, fireEvent=True):
        """
        Saves the content of current doc page.
        """
        return self.realWikiPage._save(text, fireEvent)

    def initiateUpdate(self):
        return self.realWikiPage.initiateUpdate()
        
#     def update(self, fireEvent=True):
#         return self.realWikiPage.update(fireEvent)

    def getLivePageAst(self, fireEvent=True, dieOnChange=False, 
            threadstop=DUMBTHREADSTOP):
        return self.realWikiPage.getLivePageAst(fireEvent, dieOnChange,
                threadstop)


    # TODO A bit hackish, maybe remove
    def __getattr__(self, attr):
        return getattr(self.realWikiPage, attr)


class DataCarryingPage(DocPage):
    """
    A page that carries data for itself (mainly everything except an alias page)
    """
    def __init__(self, wikiDocument):
        DocPage.__init__(self, wikiDocument)
        
        # does this page need to be saved?
        
        # None, if not dirty or timestamp when it became dirty
        # Inside self.textOperationLock, it is ensured that it is None iff
        # the editorText is None or is in sync with the database.
        # This applies not only to editorText, but also to the text returned
        # by getLiveText().

        self.saveDirtySince = None
        self.updateDirtySince = None

        # To not store the content of the page here, a placeholder
        # object is stored instead. Each time, the live text may have changed,
        # a new object is created. Functions running in a separate thread can
        # keep a reference to the object at beginning and check for
        # identity at the end of their work.
        self.liveTextPlaceHold = object()


#         # To not store the full DB content of the page here, a placeholder
#         # object is stored instead. Each time, text is written to DB,
#         # a new object is created. Functions running in a separate task can
#         # keep a reference to the object at beginning and check for
#         # identity at the end of their work.
#         self.dbContentPlaceHold = object()
        

    def setDirty(self, dirt):
        if self.isReadOnlyEffect():
            return

        if dirt:
            if self.saveDirtySince is None:
                ti = time.time()
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


    def setEditorText(self, text, dirty=True):
        with self.textOperationLock:
            if self.isReadOnlyEffect():
                return

            super(DataCarryingPage, self).setEditorText(text)
            if text is None:
                if self.saveDirtySince is not None:
                    """
                    Editor text was removed although it wasn't in sync with
                    database, so the self.liveTextPlaceHold must be updated,
                    but self.saveDirtySince is set to None because
                    self.editorText isn't valid anymore
                    """
                    self.saveDirtySince = None
                    self.liveTextPlaceHold = object()
            else:
                if dirty:
                    self.setDirty(True)
                    self.liveTextPlaceHold = object()

    def checkFileSignatureAndMarkDirty(self, fireEvent=True):
        return True
    
    
    def markTextChanged(self):
        """
        Mark text as changed and cached pageAst as invalid.
        Mainly called when an external file change is detected.
        """
        self.liveTextPlaceHold = object()
        
        
    def getAttributeOrGlobal(self, attrkey, default=None):
        """
        Tries to find an attribute on this page and returns the first value.
        If it can't be found for page, it is searched for a global
        attribute with this name. If this also can't be found,
        default (normally None) is returned.
        """
        raise NotImplementedError #abstract



class AbstractWikiPage(DataCarryingPage):
    """
    Abstract base for WikiPage and Versioning.WikiPageSnapshot
    """

    def __init__(self, wikiDocument, wikiPageName):
        DataCarryingPage.__init__(self, wikiDocument)

        self.livePageBasePlaceHold = None   # liveTextPlaceHold object on which
                # the livePageAst is based.
                # This is needed to check for changes when saving
        self.livePageBaseFormatDetails = None   # Cached format details on which the
                # page-ast bases

        # List of words unknown to spellchecker
        self.liveSpellCheckerUnknownWords = None

        # liveTextPlaceHold object on which the liveSpellCheckerUnknownWords is based.
        self.liveSpellCheckerUnknownWordsBasePlaceHold = None

        self.__sinkWikiDocumentSpellSession = KeyFunctionSinkAR((
                ("modified spell checker session", self.onModifiedSpellCheckerSession),
        ))

        self.wikiPageName = wikiPageName
        self.childRelations = None
        self.childRelationSet = set()
        self.todos = None
        self.attrs = None
        self.modified, self.created, self.visited = None, None, None
        self.suggNewPageTitle = None  # Title to use for page if it is
                # newly created

#         if self.getWikiData().getMetaDataState(self.wikiPageName) != 1:
#             self.updateDirtySince = time.time()

    def invalidate(self):
        super(AbstractWikiPage, self).invalidate()
        self.__sinkWikiDocumentSpellSession.setEventSource(None)

    # TODO: Replace getWikiWord by getWikiPageName where appropriate
    def getWikiWord(self):
        """
        Overwritten by AliasPage to return the alias name
        """
        return self.wikiPageName

    def getWikiPageName(self):
        """
        This returns the real page name even for an AliasPage
        """
        return self.wikiPageName


    def getTitle(self):
        """
        Return human readable title of the page.
        """
        return self.getWikiWord()


    def getUnifiedPageName(self):
        """
        Return the name of the unified name of the page, which is
        "wikipage/" + the wiki word for wiki pages or the functional tag
        for functional pages.
        """
        return "wikipage/" + self.wikiPageName

    def getWikiDocument(self):
        return self.wikiDocument

    def getWikiData(self):
        return self.wikiDocument.getWikiData()

    def getMetaDataState(self):
        return self.getWikiData().getMetaDataState(self.wikiPageName)

    def addTxtEditor(self, txted):
        """
        Add txted to the list of editors (views) showing this page.
        """
        with self.txtEditorListLock:
            if len(self.txtEditors) == 0:
                with self.textOperationLock:
                    if not self.checkFileSignatureAndMarkDirty():
                        self.initiateUpdate()

            super(AbstractWikiPage, self).addTxtEditor(txted)


        # TODO Set text in editor here if first editor is created?

#         with self.txtEditorListLock:
            if not txted in self.txtEditors:
                if len(self.txtEditors) == 0:
                    with self.textOperationLock:
                        # We are assuming that editor content came from
                        # database
                        self.setEditorText(txted.GetText(), dirty=False)

                self.txtEditors.append(txted)


    def getTimestamps(self):
        """
        Return tuple (<last mod. time>, <creation time>, <last visit time>)
        of this page.
        """
        if self.modified is None:
            self.modified, self.created, self.visited = \
                    self.getWikiData().getTimestamps(self.wikiPageName)
                    
        if self.modified is None:
            ti = time.time()
            self.modified, self.created, self.visited = ti, ti, ti
        
        return self.modified, self.created, self.visited

    def setTimestamps(self, timestamps):
        if self.isReadOnlyEffect():
            return

        timestamps = timestamps[:3]
        self.modified, self.created, self.visited = timestamps
        
        self.getWikiData().setTimestamps(self.wikiPageName, timestamps)


    def getSuggNewPageTitle(self):
        return self.suggNewPageTitle
        
    def setSuggNewPageTitle(self, suggNewPageTitle):
        self.suggNewPageTitle = suggNewPageTitle

    def getParentRelationships(self):
        return self.getWikiData().getParentRelationships(self.wikiPageName)


    def getChildRelationships(self, existingonly=False, selfreference=True,
            withFields=(), excludeSet=frozenset(),
            includeSet=frozenset()):
        """
        get the child relations of this word
        existingonly -- List only existing wiki words
        selfreference -- List also wikiWord if it references itself
        withFields -- Seq. of names of fields which should be included in
            the output. If this is not empty, tuples are returned
            (relation, ...) with ... as further fields in the order mentioned
            in withfields.

            Possible field names:
                "firstcharpos": position of link in page (may be -1 to represent
                    unknown)
                "modified": Modification date
        excludeSet -- set of words which should be excluded from the list
        includeSet -- wikiWords to include in the result

        Does not support caching
        """
        with self.textOperationLock:
            wikiData = self.getWikiData()
            wikiDocument = self.getWikiDocument()
            
            if withFields is None:
                withFields = ()
    
            relations = wikiData.getChildRelationships(self.wikiPageName,
                    existingonly, selfreference, withFields=withFields)
    
            if len(excludeSet) > 0:
                # Filter out members of excludeSet
                if len(withFields) > 0:
                    relations = [r for r in relations if not r[0] in excludeSet]
                else:
                    relations = [r for r in relations if not r in excludeSet]
    
            if len(includeSet) > 0:
                # First unalias wiki pages and remove non-existing ones
                clearedIncSet = set()
                for w in includeSet:
                    w = wikiDocument.getWikiPageNameForLinkTerm(w)
                    if w is None:
                        continue

#                     if not wikiDocument.isDefinedWikiLinkTerm(w):
#                         continue
    
                    clearedIncSet.add(w)

                # Then remove items already present in relations
                if len(clearedIncSet) > 0:
                    if len(withFields) > 0:
                        for r in relations:
                            clearedIncSet.discard(r[0])
                    else:
                        for r in relations:
                            clearedIncSet.discard(r)
    
                # Now collect info
                if len(clearedIncSet) > 0:
                    relations += [wikiData.getExistingWikiWordInfo(r,
                            withFields=withFields) for r in clearedIncSet]
    
            return relations


    def getAttributes(self):
        with self.textOperationLock:
            if self.attrs is not None:
                return self.attrs
            
            data = self.getWikiData().getAttributesForWord(self.wikiPageName)

#         with self.textOperationLock:
#             if self.attrs is not None:
#                 return self.attrs

            self.attrs = {}
            for (key, val) in data:
                self._addAttribute(key, val)
            
            return self.attrs

    getProperties = getAttributes  # TODO remove "property"-compatibility


    def getAttribute(self, attrkey, default=None):
        with self.textOperationLock:
            attrs = self.getAttributes()
            if attrkey in attrs:
                return attrs[attrkey][-1]
            else:
                return default

    def getAttributeOrGlobal(self, attrkey, default=None):
        """
        Tries to find an attribute on this page and returns the first value.
        If it can't be found for page, it is searched for a global
        attribute with this name. If this also can't be found,
        default (normally None) is returned.
        """
        with self.textOperationLock:
            attrs = self.getAttributes()
            if attrkey in attrs:
                return attrs[attrkey][-1]

            globalAttrs = self.getWikiData().getGlobalAttributes() 
            attrkey = "global." + attrkey
            if attrkey in globalAttrs:
                return globalAttrs[attrkey]

            option = "attributeDefault_" + attrkey
            config = wx.GetApp().getGlobalConfig()
            if config.isOptionAllowed("main", option):
                return config.get("main", option, default)
            
            return default


    getPropertyOrGlobal = getAttributeOrGlobal # TODO remove "property"-compatibility
    
    
    def _addAttribute(self, key, val):
        values = self.attrs.get(key)
        if not values:
            values = []
            self.attrs[key] = values
        values.append(val)


#     def getTodos(self):
#         with self.textOperationLock:
#             if self.todos is None:
#                 self.todos = self.getWikiData().getTodosForWord(self.wikiPageName)
#                         
#             return self.todos


    def getAnchors(self):
        """
        Return sequence of anchors in page
        """
        pageAst = self.getLivePageAst()
        return [node.anchorLink
                for node in pageAst.iterDeepByName("anchorDef")]


    def getLiveTextNoTemplate(self):
        """
        Return None if page isn't existing instead of creating an automatic
        live text (e.g. by template).
        """
        with self.textOperationLock:
            if self.getTxtEditor() is not None:
                return self.getLiveText()
            else:
                if self.isDefined():
                    return self.getContent()
                else:
                    return None


    def getFormatDetails(self):
        """
        According to currently stored settings, return a
        ParseUtilities.WikiPageFormatDetails object to describe
        formatting
        """
        with self.textOperationLock:
            withCamelCase = strToBool(self.getAttributeOrGlobal(
                    "camelCaseWordsEnabled"), True)
    
#             footnotesAsWws = self.wikiDocument.getWikiConfig().getboolean(
#                     "main", "footnotes_as_wikiwords", False)
    
            autoLinkMode = self.getAttributeOrGlobal("auto_link", "off").lower()

            paragraphMode = strToBool(self.getAttributeOrGlobal(
                    "paragraph_mode"), False)
                    
            langHelper = wx.GetApp().createWikiLanguageHelper(
                    self.wikiDocument.getWikiDefaultWikiLanguage())

            wikiLanguageDetails = langHelper.createWikiLanguageDetails(
                    self.wikiDocument, self)

            return ParseUtilities.WikiPageFormatDetails(
                    withCamelCase=withCamelCase,
                    wikiDocument=self.wikiDocument,
                    basePage=self,
                    autoLinkMode=autoLinkMode,
                    paragraphMode=paragraphMode,
                    wikiLanguageDetails=wikiLanguageDetails)


    def isDefined(self):
        return self.getWikiDocument().isDefinedWikiPageName(self.getWikiWord())


    @staticmethod
    def extractAttributeNodesFromPageAst(pageAst):
        """
        Return an iterator of attribute nodes in pageAst. This does not return
        attributes inside of todo entries.
        """
        # Complicated version for compatibility with old language plugins
        # TODO 2.4 remove "property"-compatibility
        return Utilities.iterMergesort((
                pageAst.iterUnselectedDeepByName("attribute",
                frozenset(("todoEntry",))),
                pageAst.iterUnselectedDeepByName("property",
                frozenset(("todoEntry",))) ),
                key=lambda n: n.pos)
        
        # Simple one for later
#         return pageAst.iterUnselectedDeepByName("attribute",
#                 frozenset(("todoEntry",)))


    @staticmethod
    def extractTodoNodesFromPageAst(pageAst):
        """
        Return an iterator of todo nodes in pageAst.
        """
        return pageAst.iterDeepByName("todoEntry")


    def _save(self, text, fireEvent=True):
        """
        Saves the content of current doc page.
        """
        pass


    def setPresentation(self, data, startPos):
        """
        Set (a part of) the presentation tuple. This is silently ignored
        if the "write access failed" or "read access failed" flags are
        set in the wiki document.
        data -- tuple with new presentation data
        startPos -- start position in the presentation tuple which should be
                overwritten with data.
        """
        raise NotImplementedError   # abstract


    def initiateUpdate(self, fireEvent=True):
        """
        Initiate update of page meta-data. This function may call update
        directly if can be done fast
        """
        pass


    def getLivePageAstIfAvailable(self):
        """
        Return the current, up-to-date page AST if available, None otherwise
        """
        with self.textOperationLock:
            # Current state
            text = self.getLiveText()
            formatDetails = self.getFormatDetails()

            # AST state
            pageAst = self.livePageAst
            baseFormatDetails = self.livePageBaseFormatDetails

            if pageAst is not None and \
                    baseFormatDetails is not None and \
                    formatDetails.isEquivTo(baseFormatDetails) and \
                    self.liveTextPlaceHold is self.livePageBasePlaceHold:
                return pageAst

            return None



    def getLivePageAst(self, fireEvent=True, dieOnChange=False,
            threadstop=DUMBTHREADSTOP, allowMetaDataUpdate=False):
        """
        Return PageAst of live text. In rare cases the live text may have
        changed while method is running and the result is inaccurate.
        """
#         if self.livePageAstBuildLock.acquire(False):
#             self.livePageAstBuildLock.release()
#         else:
#             if wx.IsMainThread(): traceback.print_stack()

        with self.livePageAstBuildLock:   # TODO: Timeout?
            threadstop.testValidThread()

            with self.textOperationLock:
                text = self.getLiveText()
                liveTextPlaceHold = self.liveTextPlaceHold
                formatDetails = self.getFormatDetails()

                pageAst = self.getLivePageAstIfAvailable()

            if pageAst is not None:
                return pageAst

            if dieOnChange:
                if threadstop is DUMBTHREADSTOP:
                    threadstop = FunctionThreadStop(
                            lambda: liveTextPlaceHold is self.liveTextPlaceHold)
                else:
                    origThreadstop = threadstop
                    threadstop = FunctionThreadStop(
                            lambda: origThreadstop.isValidThread() and 
                            liveTextPlaceHold is self.liveTextPlaceHold)

            if len(text) == 0:
                pageAst = buildSyntaxNode([], 0)
            else:
                pageAst = self.parseTextInContext(text, formatDetails=formatDetails,
                        threadstop=threadstop)

            with self.textOperationLock:
                threadstop.testValidThread()

                self.livePageAst = pageAst
                self.livePageBasePlaceHold = liveTextPlaceHold
                self.livePageBaseFormatDetails = formatDetails


        if self.isReadOnlyEffect():
            threadstop.testValidThread()
            return pageAst

#         if False and allowMetaDataUpdate:   # TODO: Option
#             self._refreshMetaData(pageAst, formatDetails, fireEvent=fireEvent,
#                     threadstop=threadstop)

        with self.textOperationLock:
            threadstop.testValidThread()
            return pageAst


    def onModifiedSpellCheckerSession(self, miscevt):
        """
        Invalidate spell checker data when e.g. new words are added to
        dictionary
        """
        with self.textOperationLock:
            self.__sinkWikiDocumentSpellSession.setEventSource(None)

            self.liveSpellCheckerUnknownWords = None
            self.liveSpellCheckerUnknownWordsBasePlaceHold = None

        self.fireMiscEventKeys(("modified spell checker session",))


    def getSpellCheckerUnknownWordsIfAvailable(self):
        """
        Return the current, up-to-data page AST if available, None otherwise
        """
        with self.textOperationLock:
            # unknown words
            unknownWords = self.liveSpellCheckerUnknownWords

            if unknownWords is not None and \
                    self.liveTextPlaceHold is \
                    self.liveSpellCheckerUnknownWordsBasePlaceHold:
                return unknownWords

            return None



    def getSpellCheckerUnknownWords(self, dieOnChange=False,
            threadstop=DUMBTHREADSTOP):
        """
        Return list of unknown words as list of WikiPyparsing.TerminalNode of live text.
        In rare cases the live text may have changed while method is running and
        the result is inaccurate.
        """
#         with self.livePageAstBuildLock:   # TODO: Timeout?
        threadstop.testValidThread()
        
        with self.textOperationLock:
            text = self.getLiveText()
            liveTextPlaceHold = self.liveTextPlaceHold

            unknownWords = self.getSpellCheckerUnknownWordsIfAvailable()

        if unknownWords is not None:
            return unknownWords

        if dieOnChange:
            if threadstop is DUMBTHREADSTOP:
                threadstop = FunctionThreadStop(
                        lambda: liveTextPlaceHold is self.liveTextPlaceHold)
            else:
                origThreadstop = threadstop
                threadstop = FunctionThreadStop(
                        lambda: origThreadstop.isValidThread() and 
                        liveTextPlaceHold is self.liveTextPlaceHold)

        spellSession = self.getWikiDocument().createOnlineSpellCheckerSessionClone()
        if spellSession is None:
            return
            
        spellSession.setCurrentDocPage(self)

        if len(text) == 0:
            unknownWords = []
        else:
            unknownWords = spellSession.buildUnknownWordList(text,
                    threadstop=threadstop)

        spellSession.close()

        with self.textOperationLock:
            threadstop.testValidThread()

            self.liveSpellCheckerUnknownWords = unknownWords
            self.liveSpellCheckerUnknownWordsBasePlaceHold = liveTextPlaceHold
            
            self.__sinkWikiDocumentSpellSession.setEventSource(
                    self.getWikiDocument().getOnlineSpellCheckerSession())


        if self.isReadOnlyEffect():
            threadstop.testValidThread()
            return unknownWords

#         if False and allowMetaDataUpdate:   # TODO: Option
#             self._refreshMetaData(pageAst, formatDetails, fireEvent=fireEvent,
#                     threadstop=threadstop)

        with self.textOperationLock:
            threadstop.testValidThread()
            return unknownWords


##     @profile
    def parseTextInContext(self, text, formatDetails=None,
            threadstop=DUMBTHREADSTOP):
        """
        Return PageAst of text in the context of this page (wiki language and
        format details).

        text: unistring with text
        """
        parser = wx.GetApp().createWikiParser(self.getWikiLanguageName()) # TODO debug mode  , True

        if formatDetails is None:
            formatDetails = self.getFormatDetails()

        try:
            pageAst = parser.parse(self.getWikiLanguageName(), text,
                    formatDetails, threadstop=threadstop)
        finally:
            wx.GetApp().freeWikiParser(parser)

        threadstop.testValidThread()

        return pageAst


    _DEFAULT_PRESENTATION = (0, 0, 0, 0, 0, None)

    def getPresentation(self):
        """
        Get the presentation tuple (<cursor pos>, <editor scroll pos x>,
            <e.s.p. y>, <preview s.p. x>, <p.s.p. y>, <folding list>)
        The folding list may be None or a list of UInt32 numbers
        containing fold level, header flag and expand flag for each line
        in editor.
        """
        wikiData = self.wikiDocument.getWikiData()

        if wikiData is None:
            return AbstractWikiPage._DEFAULT_PRESENTATION

        datablock = wikiData.getPresentationBlock(
                self.getWikiWord())

        if datablock is None or datablock == "":
            return AbstractWikiPage._DEFAULT_PRESENTATION

        try:
            # TODO: On next incompatible file format change: Change '=' to '>' 
            if len(datablock) == struct.calcsize("=iiiii"):
                # Version 0
                return struct.unpack("=iiiii", datablock) + (None,)
            else:
                ss = Serialization.SerializeStream(byteBuf=datablock)
                rcVer = ss.serUint8(1)
                if rcVer == 1:
                    # Compatible to version 1                
                    ver = ss.serUint8(1)
                    pt = [ss.serInt32(0), ss.serInt32(0), ss.serInt32(0),
                            ss.serInt32(0), ss.serInt32(0), None]
    
                    # Fold list
                    fl = ss.serArrUint32([])
                    if len(fl) == 0:
                        fl = None
    
                    pt[5] = fl
    
                    return tuple(pt)
                else:
                    return AbstractWikiPage._DEFAULT_PRESENTATION
        except struct.error:
            return AbstractWikiPage._DEFAULT_PRESENTATION




class WikiPage(AbstractWikiPage):
    """
    holds the data for a real wikipage (no alias).

    Fetched via the WikiDocument.getWikiPage method.
    """
    def __init__(self, wikiDocument, wikiWord):
        AbstractWikiPage.__init__(self, wikiDocument, wikiWord)

        self.versionOverview = UNDEFINED
        self.pageReadOnly = None


    def getVersionOverview(self):
        """
        Return Versioning.VersionOverview object. If necessary create one.
        """
        with self.textOperationLock:
            if self.versionOverview is UNDEFINED or self.versionOverview is None:
                from .timeView.Versioning import VersionOverview
                
                versionOverview = VersionOverview(self.getWikiDocument(),
                        self)
                versionOverview.readOverview()
                self.versionOverview = versionOverview
    
            return self.versionOverview


    def getExistingVersionOverview(self):
        """
        Return Versioning.VersionOverview object.
        If not existing already return None.
        """
        with self.textOperationLock:
            if self.versionOverview is UNDEFINED:
                from .timeView.Versioning import VersionOverview

                versionOverview = VersionOverview(self.getWikiDocument(),
                        self)

                if versionOverview.isNotInDatabase():
                    self.versionOverview = None
                else:
                    versionOverview.readOverview()
                    self.versionOverview = versionOverview

            return self.versionOverview

    def releaseVersionOverview(self):
        """
        Should only be called by VersionOverview.invalidate()
        """
        self.versionOverview = UNDEFINED


    def getNonAliasPage(self):
        """
        If this page belongs to an alias of a wiki word, return a page for
        the real one, otherwise return self.
        This class always returns self
        """
        return self


    def setPresentation(self, data, startPos):
        """
        Set (a part of) the presentation tuple. This is silently ignored
        if the "write access failed" or "read access failed" flags are
        set in the wiki document.
        data -- tuple with new presentation data
        startPos -- start position in the presentation tuple which should be
                overwritten with data.
        """
        if self.wikiDocument.isReadOnlyEffect():
            return

        if self.wikiDocument.getReadAccessFailed() or \
                self.wikiDocument.getWriteAccessFailed():
            return

        try:
            pt = self.getPresentation()
            pt = pt[:startPos] + data + pt[startPos+len(data):]
    
            wikiData = self.wikiDocument.getWikiData()
            if wikiData is None:
                return
                
            if pt[5] is None:
                # Write it in old version 0
                # TODO: On next file format change: Change '=' to '>' 
                wikiData.setPresentationBlock(self.getWikiWord(),
                        struct.pack("=iiiii", *pt[:5]))
            else:
                # Write it in new version 1
                ss = Serialization.SerializeStream(byteBuf=b"", readMode=False)
                ss.serUint8(1)  # Read compatibility version
                ss.serUint8(1)  # Real version
                # First five numbers
                for n in pt[:5]:
                    ss.serInt32(n)
                # Folding tuple
                ft = pt[5]
                if ft is None:
                    ft = ()
                ss.serArrUint32(ft)

                wikiData.setPresentationBlock(self.getWikiWord(),
                        ss.getBytes())

        except AttributeError:
            traceback.print_exc()


    def informVisited(self):
        """
        Called to inform the page that it was visited and should set
        the "visited" entry in the database to current time.
        """
        with self.textOperationLock:
            if self.isReadOnlyEffect():
                return
    
            if not self.isDefined():
                return

            wikiData = self.wikiDocument.getWikiData()
            word = self.getWikiWord()
            ts = wikiData.getTimestamps(word)
            ts = ts[:2] + (time.time(),) + ts[3:]
            wikiData.setTimestamps(word, ts)
            
        super(WikiPage, self).informVisited()


    def _changeHeadingForTemplate(self, templatePage):
        """
        Modify the heading of a template page's content to match the page
        created from the template.
        """
        # Prefix is normally u"++"
#         pageTitlePrefix = \
#                 self.getWikiDocument().getPageTitlePrefix() + u" "

        content = templatePage.getContent()
        templatePage = templatePage.getNonAliasPage()
        wikiDoc = self.getWikiDocument()

        if self.suggNewPageTitle is None:
            wikiWordHead = wikiDoc.getWikiPageTitle(self.getWikiWord())
        else:
            wikiWordHead = self.suggNewPageTitle

        if wikiWordHead is None:
            return content

        wikiWordHead = wikiDoc.formatPageTitle(wikiWordHead) + "\n"
                
        # Based on parts of WikiDocument.renameWikiWord()
        # Maybe refactor

        templateWordTitle = wikiDoc.getWikiPageTitle(templatePage.getWikiWord())
        
        if templateWordTitle is not None:
            prevTitle = wikiDoc.formatPageTitle(templateWordTitle) + "\n"
        else:
            prevTitle = None

        if prevTitle is not None and content.startswith(prevTitle):
            # Replace previous title with new one
            content = content[len(prevTitle):]

        return wikiWordHead + content



    def getContentOfTemplate(self, templatePage, parentPage):
        # getLiveText() would be more logical, but this may
        # mean that content is up to date, while attributes
        # are not updated.
        content = templatePage.getContent()
        
        # Check if template title should be changed
        tplHeading = parentPage.getAttributeOrGlobal(
                "template_head", "auto")
        if tplHeading in ("auto", "automatic"):
            content = self._changeHeadingForTemplate(templatePage)

        return content


    def setMetaDataFromTemplate(self, templatePage):
        # Load attributes from template page
        self.attrs = templatePage._cloneDeepAttributes()
        

    def getContent(self):
        """
        Returns page content. If page doesn't exist already the template
        creation is done here. After calling this function, attributes
        are also accessible for a non-existing page
        """
        content = None
        try:
            content = self.getWikiData().getContent(self.wikiPageName)
        except WikiFileNotFoundException as e:
            # Create initial content of new page

            # Check for "template" attribute
            parents = self.getParentRelationships()
            if len(parents) > 0:
                langHelper = wx.GetApp().createWikiLanguageHelper(
                        self.getWikiLanguageName())

                templateSource = None
                templateParent = None
                conflict = False
                for parent in parents:
                    try:
                        parentPage = self.wikiDocument.getWikiPage(parent)
                        try:
                            templateWord = langHelper.resolveWikiWordLink(
                                parentPage.getAttribute("template"), parentPage)
                        except ValueError:
                            templateWord = None
                        if templateWord is not None and \
                                self.wikiDocument.isDefinedWikiLinkTerm(
                                        templateWord):
                            if templateSource is None:
                                templateSource = templateWord
                                templateParentPage = parentPage
                            elif templateSource != templateWord:
                                # More than one possible template source
                                # -> no template, stop here
                                templateSource = None
                                templateParentPage = None
                                conflict = True
                                break
                    except (WikiWordNotFoundException, WikiFileNotFoundException):
                        continue

                if templateSource is None and not conflict:
                    # No individual template attributes, try to find global one
                    globalAttrs = self.getWikiData().getGlobalAttributes()     
                    
                    templateWord = globalAttrs.get("global.template")
                    if templateWord is not None and \
                            self.wikiDocument.isDefinedWikiLinkTerm(templateWord):
                        templateSource = templateWord
                        templateParentPage = self.wikiDocument.getWikiPage(
                                parents[0])

                
                if templateSource is not None:
                    templatePage = self.wikiDocument.getWikiPage(templateSource)

                    content = self.getContentOfTemplate(templatePage,
                            templateParentPage)
                    self.setMetaDataFromTemplate(templatePage)


#             if len(parents) == 1:
#                 # Check if there is a template page
#                 try:
#                     parentPage = self.wikiDocument.getWikiPage(parents[0])
# 
# 
#                     # TODO Error checking
# #                     templateWord = parentPage.getAttributeOrGlobal("template")
#                     templateWord = langHelper.resolveWikiWordLink(
#                             parentPage.getAttributeOrGlobal("template"),
#                             parentPage)
# 
#                     templatePage = self.wikiDocument.getWikiPage(templateWord)
#                     
#                     content = self.getContentOfTemplate(templatePage, parentPage)
#                     self.setMetaDataFromTemplate(templatePage)
# 
#                 except (WikiWordNotFoundException, WikiFileNotFoundException):
#                     pass

            if content is None:
                if self.suggNewPageTitle is None:
                    title = self.getWikiDocument().getWikiPageTitle(
                            self.getWikiWord())
                else:
                    title = self.suggNewPageTitle

                if title is not None:
                    content = self.wikiDocument.formatPageTitle(title) + "\n\n"
                else:
                    content = ""

        return content


#     def isDefined(self):
#         return self.getWikiDocument().isDefinedWikiPageName(self.getWikiWord())


    def pseudoDeletePage(self):
        """
        Delete a page which doesn't really exist.
        Just sends an appropriate event.
        """
        wx.CallAfter(self.fireMiscEventKeys,
                ("pseudo-deleted page", "pseudo-deleted wiki page"))


    def deletePage(self, fireEvent=True):
        """
        Deletes the page from database
        """
        with self.textOperationLock:
            if self.isReadOnlyEffect():
                return
    
            if self.isDefined():
                self.getWikiData().deleteWord(self.getWikiWord())

            vo = self.getExistingVersionOverview()
            if vo is not None:
                vo.delete()
                self.versionOverview = UNDEFINED
        
            self.queueRemoveFromSearchIndex()   # TODO: Check for (dead-)locks

            if fireEvent:
                wx.CallAfter(self.fireMiscEventKeys,
                        ("deleted page", "deleted wiki page"))


    def deletePageToTrashcan(self, fireEvent=True):
        with self.textOperationLock:
            if self.isReadOnlyEffect():
                return
    
            if not self.isDefined():
                return

            wikiDoc = self.getWikiDocument()
            if wikiDoc.getWikiConfig().getint("main", "trashcan_maxNoOfBags",
                    200) > 0:
                # Trashcan is enabled
                wikiDoc.getTrashcan().storeWikiWord(self.getWikiWord())
            
            self.deletePage(fireEvent=fireEvent)


    def renameVersionData(self, newWord):
        """
        This is called by WikiDocument during
        WikiDocument.renameWikiWord() and shouldn't be called elsewhere.
        """
        with self.textOperationLock:
            vo = self.getExistingVersionOverview()
            if vo is None:
                return
            
            vo.renameTo("wikipage/" + newWord)
            self.versionOverview = UNDEFINED


    def informRenamedWikiPage(self, newWord):
        """
        Informs object that the page was renamed to newWord.
        This page object itself does not change its name but becomes invalid!

        This function should be called by WikiDocument only,
        use WikiDocument.renameWikiWord() to rename a page.
        """

        p = {}
        p["renamed page"] = True
        p["renamed wiki page"] = True
        p["newWord"] = newWord
        
        callInMainThreadAsync(self.fireMiscEventProps, p)


    def _cloneDeepAttributes(self):
        with self.textOperationLock:
            result = {}
            for key, value in self.getAttributes().items():
                result[key] = value[:]
                
            return result


    def checkFileSignatureAndMarkDirty(self, fireEvent=True):
        """
        First checks if file signature is valid, if not, the
        "metadataprocessed" field of the word is set to 0 to mark
        meta-data as not up-to-date. At last the signature is
        refreshed.
        
        This all is done inside the lock of the WikiData so it is
        somewhat atomically.
        """
        with self.textOperationLock:
            if self.wikiDocument.isReadOnlyEffect():
                return True  # TODO Error message?
    
            if not self.isDefined():
                return True  # TODO Error message?
    
            wikiData = self.getWikiData()
            word = self.wikiPageName

            proxyAccessLock = getattr(wikiData, "proxyAccessLock", None)
            if proxyAccessLock is not None:
                proxyAccessLock.acquire()
            try:
                valid = wikiData.validateFileSignatureForWikiPageName(word)
                
                if valid:
                    return True
    
                wikiData.setMetaDataState(word,
                        Consts.WIKIWORDMETADATA_STATE_DIRTY)
                wikiData.refreshFileSignatureForWikiPageName(word)
                self.markTextChanged()
            finally:
                if proxyAccessLock is not None:
                    proxyAccessLock.release()

            editor = self.getTxtEditor()
        
        if editor is not None:
            # TODO Check for deadlocks
            callInMainThread(editor.handleInvalidFileSignature, self)

        if fireEvent:
            wx.CallAfter(self.fireMiscEventKeys,
                    ("checked file signature invalid",))

        return False


    def markMetaDataDirty(self):
        self.getWikiData().setMetaDataState(self.wikiPageName,
                Consts.WIKIWORDMETADATA_STATE_DIRTY)


    def _refreshMetaData(self, pageAst, formatDetails, fireEvent=True,
            threadstop=DUMBTHREADSTOP):

        # Step 1: Refresh attributes
        self.refreshAttributesFromPageAst(pageAst, threadstop=threadstop)

        # Some attributes control format details so check if attribute
        # refresh changed the details
        formatDetails2 = self.getFormatDetails()
        if not formatDetails.isEquivTo(formatDetails2):
            # Formatting details have changed -> stop and wait for
            # new round to update
            return False

        # Step 2: Refresh todos, link structure ...
        self.refreshMainDbCacheFromPageAst(pageAst, fireEvent=fireEvent,
                threadstop=threadstop)

        # Step 3: Update index search data
        self.putIntoSearchIndex(threadstop=threadstop)
        
        return True



    def refreshSyncUpdateMatchTerms(self):
        """
        Refresh those match terms which must be refreshed synchronously
        """
        if self.wikiDocument.isReadOnlyEffect():
            return

        WORD_TYPE = Consts.WIKIWORDMATCHTERMS_TYPE_ASLINK | \
                Consts.WIKIWORDMATCHTERMS_TYPE_FROM_WORD | \
                Consts.WIKIWORDMATCHTERMS_TYPE_SYNCUPDATE

        matchTerms = [(self.wikiPageName, WORD_TYPE, self.wikiPageName, -1, 0)]
        self.getWikiData().updateWikiWordMatchTerms(self.wikiPageName, matchTerms,
                syncUpdate=True)


    def refreshAttributesFromPageAst(self, pageAst, threadstop=DUMBTHREADSTOP):
        """
        Update properties (aka attributes) only.
        This is step one in update/rebuild process.
        """
        if self.wikiDocument.isReadOnlyEffect():
            return True  # TODO Error?

        langHelper = wx.GetApp().createWikiLanguageHelper(
                self.getWikiLanguageName())

        attrs = {}

        def addAttribute(key, value):
            threadstop.testValidThread()
            values = attrs.get(key)
            if not values:
                values = []
                attrs[key] = values
            values.append(value)


        attrNodes = self.extractAttributeNodesFromPageAst(pageAst)
        for node in attrNodes:
            for attrKey, attrValue in \
                    (getattr(node, "attrs", []) + getattr(node, "props", [])):  # TODO remove "property"-compatibility
                addAttribute(attrKey, attrValue)

        with self.textOperationLock:
            threadstop.testValidThread()

            self.attrs = None

        try:
            self.getWikiData().updateAttributes(self.wikiPageName, attrs)
        except WikiWordNotFoundException:
            return False

        valid = False

        with self.textOperationLock:
            if self.saveDirtySince is None and \
                    self.livePageBasePlaceHold is self.liveTextPlaceHold and \
                    self.livePageBaseFormatDetails is not None and \
                    self.getFormatDetails().isEquivTo(self.livePageBaseFormatDetails) and \
                    pageAst is self.livePageAst:

                threadstop.testValidThread()
                # clear the dirty flag

                self.getWikiData().setMetaDataState(self.wikiPageName,
                        Consts.WIKIWORDMETADATA_STATE_ATTRSPROCESSED)

                valid = True

        return valid



    def refreshMainDbCacheFromPageAst(self, pageAst, fireEvent=True,
            threadstop=DUMBTHREADSTOP):
        """
        Update everything else (todos, relations).
        This is step two in update/rebuild process.
        """
        if self.wikiDocument.isReadOnlyEffect():
            return True   # return True or False?

        todos = []
        childRelations = []
        childRelationSet = set()

        def addTodo(todoKey, todoValue):
            threadstop.testValidThread()
            todo = (todoKey, todoValue)
            if todo not in todos:
                todos.append(todo)

        def addChildRelationship(toWord, pos):
            threadstop.testValidThread()
            if toWord not in childRelationSet:
                childRelations.append((toWord, pos))
                childRelationSet.add(toWord)

        # Add todo entries
        todoNodes = pageAst.iterDeepByName("todoEntry")
        for node in todoNodes:
            for todoKey, todoValueNode in node.todos:
                addTodo(todoKey, todoValueNode.getString())

        threadstop.testValidThread()

        # Add child relations
        wwTokens = pageAst.iterDeepByName("wikiWord")
        for t in wwTokens:
            addChildRelationship(t.wikiWord, t.pos)

        threadstop.testValidThread()
        
        # Add aliases to match terms
        matchTerms = []

        ALIAS_TYPE = Consts.WIKIWORDMATCHTERMS_TYPE_EXPLICIT_ALIAS | \
                Consts.WIKIWORDMATCHTERMS_TYPE_ASLINK | \
                Consts.WIKIWORDMATCHTERMS_TYPE_FROM_ATTRIBUTES

        langHelper = wx.GetApp().createWikiLanguageHelper(
                self.getWikiLanguageName())

        for w, k, v in self.getWikiDocument().getAttributeTriples(
                self.wikiPageName, "alias", None):
            threadstop.testValidThread()
            if not langHelper.checkForInvalidWikiLink(v,
                                                      self.getWikiDocument()):
#                 matchTerms.append((v, ALIAS_TYPE, self.wikiPageName, -1, -1))
                matchTerms.append((langHelper.resolveWikiWordLink(v, self),
                        ALIAS_TYPE, self.wikiPageName, -1, -1))

        # Add headings to match terms if wanted
        depth = self.wikiDocument.getWikiConfig().getint(
                "main", "headingsAsAliases_depth")

        if depth > 0:
            HEADALIAS_TYPE = Consts.WIKIWORDMATCHTERMS_TYPE_FROM_CONTENT
            for node in pageAst.iterFlatByName("heading"):
                threadstop.testValidThread()
                if node.level > depth:
                    continue

                title = node.getString()
                if title.endswith("\n"):
                    title = title[:-1]
                
                matchTerms.append((title, HEADALIAS_TYPE, self.wikiPageName,
                        node.pos + node.strLength, 0))

        with self.textOperationLock:
            threadstop.testValidThread()

            self.todos = None
            self.childRelations = None
            self.childRelationSet = set()
        try:
            self.getWikiData().updateTodos(self.wikiPageName, todos)
            threadstop.testValidThread()
            self.getWikiData().updateChildRelations(self.wikiPageName,
                    childRelations)
            threadstop.testValidThread()
            self.getWikiData().updateWikiWordMatchTerms(self.wikiPageName,
                    matchTerms)
            threadstop.testValidThread()
        except WikiWordNotFoundException:
            return False
#             self.modified = None   # ?
#             self.created = None


            # Now we check the whole chain if flags can be set:
            # db content is identical to liveText
            # liveText is basis of current livePageAst
            # formatDetails are same as the ones used for livePageAst
            # and livePageAst is identical to pageAst processed in this method

        valid = False
        with self.textOperationLock:
#             print "--refreshMainDbCacheFromPageAst43", repr((self.wikiPageName, self.saveDirtySince,
#                     self.livePageBasePlaceHold is self.liveTextPlaceHold,
#                     self.livePageBaseFormatDetails is not None,
# #                     self.getFormatDetails().isEquivTo(self.livePageBaseFormatDetails),
#                     pageAst is self.livePageAst))
            if self.saveDirtySince is None and \
                    self.livePageBasePlaceHold is self.liveTextPlaceHold and \
                    self.livePageBaseFormatDetails is not None and \
                    self.getFormatDetails().isEquivTo(self.livePageBaseFormatDetails) and \
                    pageAst is self.livePageAst:

                threadstop.testValidThread()
                # clear the dirty flag
                self.updateDirtySince = None

                self.getWikiData().setMetaDataState(self.wikiPageName,
                        Consts.WIKIWORDMETADATA_STATE_SYNTAXPROCESSED)
                valid = True

        if fireEvent:
            callInMainThreadAsync(self.fireMiscEventKeys,
                    ("updated wiki page", "updated page"))

        return valid


    def putIntoSearchIndex(self, threadstop=DUMBTHREADSTOP):
        """
        Add or update the index for the given docPage
        """
        with self.textOperationLock:
            threadstop.testValidThread()

            if self.isInvalid() or not self.getWikiDocument().isSearchIndexEnabled():
                return True  # Or false?
            
            liveTextPlaceHold = self.liveTextPlaceHold
            content = self.getLiveText()

        writer = None
        try:
            searchIdx = self.getWikiDocument().getSearchIndex()
            writer = searchIdx.writer(timeout=Consts.DEADBLOCKTIMEOUT)

            unifName = self.getUnifiedPageName()

            writer.delete_by_term("unifName", unifName)
            
            writer.add_document(unifName=unifName,
                    modTimestamp=self.getTimestamps()[0],
                    content=content)
        except:
            if writer is not None:
                writer.cancel()
            raise

        # Check within lock if data is current yet
        with self.textOperationLock:
            if self.isInvalid(): 
                writer.cancel()
                return True  # Or false?

            if not liveTextPlaceHold is self.liveTextPlaceHold:
                writer.cancel()
                return False
            else:
                writer.commit()
                self.getWikiData().setMetaDataState(self.wikiPageName,
                        Consts.WIKIWORDMETADATA_STATE_INDEXED)
                return True

    def removeFromSearchIndex(self):
        """
        Remove this page from search index. Direct calling is not recommended,
        call queueRemoveFromSearchIndex() instead.
        """
        if not self.getWikiDocument().isSearchIndexEnabled() or self.isInvalid():
            return

        unifName = self.getUnifiedPageName()
        
        writer = None
        
        with self.textOperationLock:
            try:
                searchIdx = self.getWikiDocument().getSearchIndex()
                writer = searchIdx.writer(timeout=Consts.DEADBLOCKTIMEOUT)
                writer.delete_by_term("unifName", unifName)
            except:
                if writer is not None:
                    writer.cancel()
                raise
    
            writer.commit()


    def queueRemoveFromSearchIndex(self):
        if not self.getWikiDocument().isSearchIndexEnabled():
            return

        wikiDoc = self.getWikiDocument()
        
        wikiDoc.getUpdateExecutor().executeAsync(wikiDoc.UEQUEUE_INDEX,
                self.removeFromSearchIndex)


#     def update(self):
#         return self.runDatabaseUpdate(step=-2)

    def runDatabaseUpdate(self, step=-1, threadstop=DUMBTHREADSTOP):
        with self.textOperationLock:
            if not self.isDefined():
                return False
            if self.wikiDocument.isReadOnlyEffect():
                return False

            liveTextPlaceHold = self.liveTextPlaceHold
            formatDetails = self.getFormatDetails()

        try:
            pageAst = self.getLivePageAst(dieOnChange=True,
                    threadstop=threadstop)

            # Check within lock if data is current yet
            with self.textOperationLock:
                if not liveTextPlaceHold is self.liveTextPlaceHold:
                    return False
    
    
            if step == -1:
                self._refreshMetaData(pageAst, formatDetails, threadstop=threadstop)

                with self.textOperationLock:
                    if not liveTextPlaceHold is self.liveTextPlaceHold:
                        return False
                    if not formatDetails.isEquivTo(self.getFormatDetails()):
                        self.initiateUpdate()
                        return False
#             elif step == -2:
#                 for i in range(15):   # while True  is too dangerous
#                     metaState = self.getWikiData().getMetaDataState(self.wikiPageName)
# 
#                     if not liveTextPlaceHold is self.liveTextPlaceHold:
#                         return False
#                     if not formatDetails.isEquivTo(self.getFormatDetails()):
#                         self.initiateUpdate()
#                         return False
# 
#                     if metaState == Consts.WIKIWORDMETADATA_STATE_SYNTAXPROCESSED:
#                         return True
# 
#                     elif metaState == Consts.WIKIWORDMETADATA_STATE_ATTRSPROCESSED:
#                         self.refreshMainDbCacheFromPageAst(pageAst,
#                                 threadstop=threadstop)
#                         continue
# 
#                     else: # step == Consts.WIKIWORDMETADATA_STATE_DIRTY
#                         self.refreshAttributesFromPageAst(pageAst,
#                                 threadstop=threadstop)
#                         continue
            else:
                metaState = self.getMetaDataState()

                if metaState >= self.getWikiDocument().getFinalMetaDataState() or \
                        metaState != step:
                    return False
    
                if step == Consts.WIKIWORDMETADATA_STATE_SYNTAXPROCESSED:
                    # 
                    return self.putIntoSearchIndex(threadstop=threadstop)

                elif step == Consts.WIKIWORDMETADATA_STATE_ATTRSPROCESSED:
                    return self.refreshMainDbCacheFromPageAst(pageAst,
                            threadstop=threadstop)
                else: # step == Consts.WIKIWORDMETADATA_STATE_DIRTY
                    return self.refreshAttributesFromPageAst(pageAst,
                            threadstop=threadstop)

        except NotCurrentThreadException:
            return False



    def initiateUpdate(self, fireEvent=True):
        """
        Initiate update of page meta-data. This function may call update
        directly if it can be done fast
        """
        with self.textOperationLock:
            self.wikiDocument.pushUpdatePage(self)


    def _save(self, text, fireEvent=True):
        """
        Saves the content of current wiki page.
        """
        if self.isReadOnlyEffect():
            return
        
        with self.textOperationLock:
            if not self.getWikiDocument().isDefinedWikiPageName(
                    self.wikiPageName):
                # Pages isn't yet in database  -> fire event
                # The event may be needed to invalidate a cache
                self.fireMiscEventKeys(("saving new wiki page",))

            self.getWikiData().setContent(self.wikiPageName, text)
            self.refreshSyncUpdateMatchTerms()
            self.saveDirtySince = None
#             self.dbContentPlaceHold = object()
            if self.getEditorText() is None:
                self.liveTextPlaceHold = object()


            # Clear timestamp cache
            self.modified = None


    def getPageReadOnly(self):
        if self.pageReadOnly is None:
            wikiWordReadOnly = self.getWikiData().getWikiWordReadOnly(
                    self.getNonAliasPage().getWikiWord())

            if wikiWordReadOnly is None:
                self.pageReadOnly = False
            else:
                self.pageReadOnly = bool(wikiWordReadOnly & 1)

        return self.pageReadOnly


    def setPageReadOnly(self, readOnly):
        if self.wikiDocument.isReadOnlyEffect() or \
                self.pageReadOnly == readOnly or \
                not self.isDefined():
            return

        if readOnly:
            self.writeToDatabase()  # Write to db before becoming read only
            self.getWikiData().setWikiWordReadOnly(self.getNonAliasPage()
                    .getWikiWord(), 1)
        else:
            self.getWikiData().setWikiWordReadOnly(self.getNonAliasPage()
                    .getWikiWord(), 0)
                    
        self.pageReadOnly = None
        self.fireMiscEventKeys(("changed read only flag",))



    def isReadOnlyEffect(self):
        """
        Return true if page is effectively read-only, this means
        "for any reason", regardless if error or intention.
        """
        return self.getPageReadOnly() or super(WikiPage, self).isReadOnlyEffect()



    # ----- Advanced functions -----

    def getChildRelationshipsTreeOrder(self, existingonly=False,
            excludeSet=frozenset(), includeSet=frozenset()):
        """
        Return a list of children wiki words of the page, ordered as they would
        appear in tree. Some children may be missing if they e.g.
        are set as hidden.
        existingonly -- true iff non-existing words should be hidden
        excludeSet -- set of words which should be excluded from the list
        includeSet -- wikiWords to include in the result
        """
        from functools import cmp_to_key
        
        wikiDocument = self.wikiDocument
        
        # get the sort order for the children
        childSortOrder = self.getAttributeOrGlobal('child_sort_order',
                "ascending")
            
        # Apply sort order
        if childSortOrder == "natural":
            # TODO: Do it right 
            # Retrieve relations as list of tuples (child, firstcharpos)
            relations = self.getChildRelationships(existingonly,
                    selfreference=False, withFields=("firstcharpos",),
                    excludeSet=excludeSet, includeSet=includeSet)

            relations.sort(key=cmp_to_key(_cmpNumbersItem1))
            # Remove firstcharpos
            relations = [r[0] for r in relations]
        elif childSortOrder == "mod_oldest":
            # Retrieve relations as list of tuples (child, modifTime)
            relations = self.getChildRelationships(existingonly,
                    selfreference=False, withFields=("modified",),
                    excludeSet=excludeSet, includeSet=includeSet)
            relations.sort(key=cmp_to_key(_cmpNumbersItem1))
            # Remove firstcharpos
            relations = [r[0] for r in relations]
        elif childSortOrder == "mod_newest":
            # Retrieve relations as list of tuples (child, modifTime)
            relations = self.getChildRelationships(existingonly,
                    selfreference=False, withFields=("modified",),
                    excludeSet=excludeSet, includeSet=includeSet)
            relations.sort(key=cmp_to_key(_cmpNumbersItem1Rev))
            # Remove firstcharpos
            relations = [r[0] for r in relations]            
        else:
            # Retrieve relations as list of children words
            relations = self.getChildRelationships(existingonly, 
                    selfreference=False, withFields=(),
                    excludeSet=excludeSet, includeSet=includeSet)
            if childSortOrder.startswith("desc"):
                coll = wikiDocument.getCollator()

                def cmpLowerDesc(a, b):
                    return coll.strcoll(
                            b.lower(), a.lower())
                            
                relations.sort(key=cmp_to_key(cmpLowerDesc)) # sort alphabetically
            elif childSortOrder.startswith("asc"):
                coll = wikiDocument.getCollator()

                def cmpLowerAsc(a, b):
                    return coll.strcoll(
                            a.lower(), b.lower())

                relations.sort(key=cmp_to_key(cmpLowerAsc))



        priorized = []
        positioned = []
        other = []

        # Put relations into their appropriate arrays
        for relation in relations:
            relationPage = wikiDocument.getWikiPageNoError(relation)
            attrs = relationPage.getAttributes()
            try:
                if ('tree_position' in attrs):
                    positioned.append((int(attrs['tree_position'][-1]) - 1, relation))
                elif ('priority' in attrs):
                    priorized.append((int(attrs['priority'][-1]), relation))
                else:
                    other.append(relation)
            except:
                other.append(relation)
                
        # Sort special arrays
        priorized.sort(key=lambda t: t[0])
        positioned.sort(key=lambda t: t[0])


        result = []
        ipr = 0
        ipo = 0
        iot = 0

        for i in range(len(relations)):
            if ipo < len(positioned) and positioned[ipo][0] <= i:
                result.append(positioned[ipo][1])
                ipo += 1
                continue
            
            if ipr < len(priorized):
                result.append(priorized[ipr][1])
                ipr += 1
                continue
            
            if iot < len(other):
                result.append(other[iot])
                iot += 1
                continue
            
            # When reaching this, only positioned can have elements yet
            if ipo < len(positioned):
                result.append(positioned[ipo][1])
                ipo += 1
                continue
            
            raise InternalError("Empty relation sorting arrays")
        

        return result


#         # TODO Remove aliases?
#     def _flatTreeHelper(self, page, deepness, excludeSet, includeSet, result,
#             unalias):
#         """
#         Recursive part of getFlatTree
#         """
# #         print "_flatTreeHelper1", repr((page.getWikiWord(), deepness, len(excludeSet)))
# 
#         word = page.getWikiWord()
#         nonAliasWord = page.getNonAliasPage().getWikiWord()
#         excludeSet.add(nonAliasWord)
# 
#         children = page.getChildRelationshipsTreeOrder(existingonly=True)
# 
#         for word in children:
#             subpage = self.wikiDocument.getWikiPage(word)
#             nonAliasWord = subpage.getNonAliasPage().getWikiWord()
#             if nonAliasWord in excludeSet:
#                 continue
#             if unalias:
#                 result.append((nonAliasWord, deepness + 1))
#             else:
#                 result.append((word, deepness + 1))
#             
#             if includeSet is not None:
#                 includeSet.discard(word)
#                 includeSet.discard(nonAliasWord)
#                 if len(includeSet) == 0:
#                     return
#             
#             self._flatTreeHelper(subpage, deepness + 1, excludeSet, includeSet,
#                     result, unalias)
# 
# 
#     def getFlatTree(self, unalias=False, includeSet=None):
#         """
#         Returns a sequence of tuples (word, deepness) where the current
#         word is the first one with deepness 0.
#         The words may contain aliases, but no word appears twice neither
#         will both a word and its alias appear in the list.
#         unalias -- replace all aliases by their real word
#         TODO EXPLAIN FUNCTION !!!
#         """
#         word = self.getWikiWord()
#         nonAliasWord = self.getNonAliasPage().getWikiWord()
# 
#         if unalias:
#             result = [(nonAliasWord, 0)]
#         else:
#             result = [(word, 0)]
# 
#         if includeSet is not None:
#             includeSet.discard(word)
#             includeSet.discard(nonAliasWord)
#             if len(includeSet) == 0:
#                 return result
# 
#         excludeSet = set()   # set((self.getWikiWord(),))
# 
#         self._flatTreeHelper(self, 0, excludeSet, includeSet, result, unalias)
# 
# #         print "getFlatTree", repr(result)
# 
#         return result


    def getFlatTree(self, unalias=False, includeSet=None, maxdepth=-1,
            resetdepth=0):
        """
        Returns a sequence of tuples (word, deepness) where the current
        word is the first one with deepness 0.
        The words may contain aliases, but no word appears twice neither
        will both a word and its alias appear in the list.
        
        unalias -- if to replace all aliases by their real word
        maxdepth -- don't create entries deeper than that level (-1: no limit)
        resetdepth -- if entry outreaches maxdepth it is inserted later
                with level  resetdepth  (-1: entry isn't inserted anymore)
        """
        getWikiPageNameForLinkTerm = self.getWikiDocument().getWikiPageNameForLinkTerm

        checkList = [(self.getWikiWord(), self.getNonAliasPage().getWikiWord(),
                0)]

        mixins = collections.deque()
        resultSet = set()
        result = []

        while True:
            if len(checkList) > 0:
                word, nonAliasWord, chLevel = checkList[-1]

                if len(mixins) > 0 and mixins[-1][2] >= chLevel:
                    word, nonAliasWord, chLevel = mixins.pop()
                else:
                    del checkList[-1]
            else:
                if len(mixins) == 0:
                    break # Everything empty -> terminate
                else:
                    mixList = list(mixins)
                    mixList.reverse()
                    checkList.extend((w, naw, 0) for w, naw, l in mixList)
                    mixins.clear()
                    continue

            if nonAliasWord in resultSet:
                continue

            if maxdepth > -1 and chLevel > maxdepth:
                # Don't go deeper
                if resetdepth > -1:
                    mixins.appendleft((word, nonAliasWord, resetdepth))
                continue

            if unalias:
                result.append((nonAliasWord, chLevel))
            else:
                result.append((word, chLevel))

            resultSet.add(nonAliasWord)

            if includeSet is not None:
                includeSet.discard(word)
                includeSet.discard(nonAliasWord)
                if len(includeSet) == 0:
                    return result


            page = self.getWikiDocument().getWikiPage(nonAliasWord)
            children = page.getChildRelationshipsTreeOrder(existingonly=True)

            children = [(c, getWikiPageNameForLinkTerm(c), chLevel + 1)
                    for c in children]
            children.reverse()
            checkList += children

        return result



    def getDependentDataBlocks(self):
        vo = self.getExistingVersionOverview()
        
        if vo is None:
            return []
        
        return vo.getDependentDataBlocks()





# TODO: Maybe split into single classes for each tag

class FunctionalPage(DataCarryingPage):
    """
    holds the data for a functional page. Such a page controls the behavior
    of the application or a special wiki
    """
    def __init__(self, wikiDocument, funcTag):
        DataCarryingPage.__init__(self, wikiDocument)
        
        if not isFuncTag(funcTag):
            raise BadFuncPageTagException(
                    _("Func. tag %s does not exist") % funcTag)

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
        return "<" + getHrNameForFuncTag(self.funcTag) + ">"


    def getFuncTag(self):
        """
        Return the functional tag of the page (a kind of filepath
        for the page)
        """
        return self.funcTag

    def getUnifiedPageName(self):
        """
        Return the name of the unified name of the page, which is
        "wikipage/" + the wiki word for wiki pages or the functional tag
        for functional pages.
        """
        return self.funcTag


    def _loadGlobalPage(self, subtag):
        tbLoc = os.path.join(wx.GetApp().getGlobalConfigSubDir(),
                "[%s].wiki" % subtag)
        try:
            tbContent = loadEntireTxtFile(tbLoc)
            return fileContentToUnicode(tbContent)
        except:
            return ""


    def _loadDbSpecificPage(self, funcTag):
        content = self.wikiDocument.getWikiData().retrieveDataBlockAsText(funcTag)
        if content is None:
            return ""
        
        return content

#         if self.wikiDocument.isDefinedWikiWord(subtag):
#             return self.wikiDocument.getWikiData().getContent(subtag)
#         else:
#             return u""


    def getWikiLanguageName(self):
        """
        Returns the internal name of the wiki language of this page.
        """
        if self.wikiDocument is None:
            return ParseUtilities.getBasicLanguageHelper().getWikiLanguageName()

        return super(FunctionalPage, self).getWikiLanguageName()


    def createWikiLanguageHelper(self):
        if self.wikiDocument is None:
            return ParseUtilities.getBasicLanguageHelper()

        return super(FunctionalPage, self).createWikiLanguageHelper()


    def getLiveTextNoTemplate(self):
        """
        Return None if page isn't existing instead of creating an automatic
        live text (e.g. by template).
        Functional pages by definition exist always 
        """
        return self.getLiveText()


    def getContent(self):
        if self.funcTag in ("global/TextBlocks", "global/PWL",
                "global/CCBlacklist", "global/NCCBlacklist",
                "global/FavoriteWikis"):
            return self._loadGlobalPage(self.funcTag[7:])
        elif self.funcTag in ("wiki/TextBlocks", "wiki/PWL",
                "wiki/CCBlacklist", "wiki/NCCBlacklist"):
            return self._loadDbSpecificPage(self.funcTag)


    def getFormatDetails(self):
        """
        According to currently stored settings, return a
        ParseUtilities.WikiPageFormatDetails object to describe
        formatting.
        
        For functional pages this is normally no formatting
        """
        return ParseUtilities.WikiPageFormatDetails(noFormat=True)


    def getLivePageAstIfAvailable(self):
        return self.getLivePageAst()


    # TODO Checking with dieOnChange == True
    def getLivePageAst(self, fireEvent=True, dieOnChange=False,
            threadstop=DUMBTHREADSTOP):
        """
        The PageAst of a func. page is always a single "default" token
        containing the whole text.
        """
        with self.livePageAstBuildLock:
            threadstop.testValidThread()
    
            pageAst = self.livePageAst
            
            if pageAst is not None:
                return pageAst

            with self.textOperationLock:
                pageAst = buildSyntaxNode([buildSyntaxNode(
                        self.getLiveText(), 0, "plainText")], 0, "text")

                threadstop.testValidThread()

                self.livePageAst = pageAst

                return pageAst



    def _saveGlobalPage(self, text, subtag):
        tbLoc = os.path.join(wx.GetApp().getGlobalConfigSubDir(),
                "[%s].wiki" % subtag)

        writeEntireFile(tbLoc, text, True)


    def _saveDbSpecificPage(self, text, funcTag):
        if self.isReadOnlyEffect():
            return

        wikiData = self.wikiDocument.getWikiData()
        
        if text == "":
            wikiData.deleteDataBlock(funcTag)
        else:
            wikiData.storeDataBlock(funcTag, text,
                    storeHint=Consts.DATABLOCK_STOREHINT_EXTERN)


#         if self.wikiDocument.isDefinedWikiWord(subtag) and text == u"":
#             # Delete content
#             wikiData.deleteContent(subtag)
#         else:
#             if text != u"":
#                 wikiData.setContent(subtag, text)


    def _save(self, text, fireEvent=True):
        """
        Saves the content of current wiki page.
        """
        if self.isReadOnlyEffect():
            return
        
        with self.textOperationLock:
            # text = self.getLiveText()
    
            if self.funcTag in ("global/TextBlocks", "global/PWL",
                    "global/CCBlacklist", "global/NCCBlacklist",
                    "global/FavoriteWikis"):
                self._saveGlobalPage(text, self.funcTag[7:])
            elif self.funcTag in ("wiki/TextBlocks", "wiki/PWL",
                    "wiki/CCBlacklist", "wiki/NCCBlacklist"):
                self._saveDbSpecificPage(text, self.funcTag)

            self.saveDirtySince = None



    def initiateUpdate(self, fireEvent=True):
        """
        Update additional cached informations (attributes, todos, relations).
        Here it is done directly in initiateUpdate() because it doesn't need
        much work.
        """
        # For "global/*" functional pages self.wikiDocument is None
        if self.wikiDocument is not None and self.wikiDocument.isReadOnlyEffect():
            return

        with self.textOperationLock:
            # clear the dirty flag
            self.updateDirtySince = None
    
            if fireEvent:
                if self.funcTag.startswith("wiki/"):
                    evtSource = self
                else:
                    evtSource = wx.GetApp()
    
                if self.funcTag in ("global/TextBlocks", "wiki/TextBlocks"):
                    # The text blocks for the text blocks submenu was updated
                    evtSource.fireMiscEventKeys(("updated func page", "updated page",
                            "reread text blocks needed"))
                elif self.funcTag in ("global/PWL", "wiki/PWL"):
                    # The personal word list (words to ignore by spell checker)
                    # was updated
                    evtSource.fireMiscEventKeys(("updated func page", "updated page",
                            "reread personal word list needed"))
                elif self.funcTag in ("global/CCBlacklist", "wiki/CCBlacklist"):
                    # The blacklist of camelcase words not to mark as wiki links
                    # was updated
                    evtSource.fireMiscEventKeys(("updated func page", "updated page",
                            "reread cc blacklist needed"))
                elif self.funcTag in ("global/NCCBlacklist", "wiki/NCCBlacklist"):
                    # The blacklist of non-camelcase words not to mark as wiki links
                    # was updated
                    evtSource.fireMiscEventKeys(("updated func page", "updated page",
                            "reread ncc blacklist needed"))
                elif self.funcTag == "global/FavoriteWikis":
                    # The list of favorite wikis was updated (there is no
                    # wiki-bound version of favorite wikis
                    evtSource.fireMiscEventKeys(("updated func page", "updated page",
                            "reread favorite wikis needed"))

    def isReadOnlyEffect(self):
        """
        Return true if page is effectively read-only, this means
        "for any reason", regardless if error or intention.
        Global func. pages do not depend on the wiki state so they are writable.
        """
        if self.funcTag.startswith("global/"):
            # Global pages are not stored in the wiki and are always writable
            return False
        else:
            return DataCarryingPage.isReadOnlyEffect(self)


    def getPresentation(self):
        """Dummy"""
        return (0, 0, 0, 0, 0)

    def setPresentation(self, data, startPos):
        """Dummy"""
        pass
        
    def getAttributeOrGlobal(self, attrkey, default=None):
        """
        Because a functional page can't contain attributes,
        it is only searched for a global attribute with this name.
        If this can't be found, default (normally None) is returned.
        """
        attrkey = "global." + attrkey

        if self.wikiDocument is not None:
            wikiData = self.wikiDocument.getWikiData()
            if wikiData is not None:
                with self.textOperationLock:
                    globalAttrs = wikiData.getGlobalAttributes()
                    if attrkey in globalAttrs:
                        return globalAttrs[attrkey]

        option = "attributeDefault_" + attrkey
        config = wx.GetApp().getGlobalConfig()
        if config.isOptionAllowed("main", option):
            return config.get("main", option, default)

        return default





# Two search helpers for WikiPage.getChildRelationshipsTreeOrder

def _floatToCompInt(f):
    if f > 0:
        return 1
    elif f < 0:
        return -1
    else:
        return 0



# TODO: Remove for Python 3.0
def _cmpNumbersItem1(a, b):
    """
    Compare "natural", means using the char. positions or moddates of
    the links in page.
    """
    return _floatToCompInt(a[1] - b[1])


def _cmpNumbersItem1Rev(a, b):
    """
    Compare "natural", means using the char. positions or moddates of
    the links in page.
    """
    return _floatToCompInt(b[1] - a[1])



_FUNCTAG_TO_HR_NAME_MAP = {
            "global/TextBlocks": N_("Global text blocks"),
            "wiki/TextBlocks": N_("Wiki text blocks"),
            "global/PWL": N_("Global spell list"),
            "wiki/PWL": N_("Wiki spell list"),
            "global/CCBlacklist": N_("Global cc. blacklist"),
            "wiki/CCBlacklist": N_("Wiki cc. blacklist"),
            "global/NCCBlacklist": N_("Global ncc. blacklist"),
            "wiki/NCCBlacklist": N_("Wiki ncc. blacklist"),
            "global/FavoriteWikis": N_("Favorite wikis"),
        }


def getHrNameForFuncTag(funcTag):
    """
    Return the human readable name of functional page with tag funcTag.
    """
    return _(_FUNCTAG_TO_HR_NAME_MAP.get(funcTag, funcTag))
    

def getFuncTags():
    """
    Return all available func tags
    """
    return list(_FUNCTAG_TO_HR_NAME_MAP.keys())


def isFuncTag(funcTag):
    return funcTag in _FUNCTAG_TO_HR_NAME_MAP

