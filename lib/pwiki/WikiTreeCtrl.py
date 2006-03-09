import sys # , hotshot

## _prof = hotshot.Profile("hotshot.prf")

from wxPython.wx import *
from wxPython.stc import *
import wxPython.xrc as xrc

from wxHelper import GUI_ID
from MiscEvent import KeyFunctionSink, DebugSimple

from WikiExceptions import WikiWordNotFoundException
import WikiFormatting
from PageAst import tokenizeTodoValue
from SearchAndReplace import SearchReplaceOperation

from StringOps import mbcsEnc, guiToUni, uniToGui, wikiWordToLabel, strToBool


class NodeStyle(object):
    """
    A simple structure to hold all necessary information to present a tree node.
    """
    
    __slots__ = ("__weakref__", "label", "bold", "icon", "color", "hasChildren")
    def __init__(self):
        self.label = u""
        
        self.bold = u"False"
        self.icon = u"page"
        self.color = u"null"
        
        self.hasChildren = False
        

_SETTABLE_PROPS = (u"bold", u"icon", u"color")


# New style class to allow __slots__ for efficiency
class AbstractNode(object):
    """
    Especially for view nodes. An instance of a derived class
    is saved in funcData for such special nodes
    """
    
    __slots__ = ("__weakref__",   # just in case...
            "treeCtrl", "parentNode")
            
    def __init__(self, tree, parentNode):
        self.treeCtrl = tree
        self.parentNode = parentNode
    
    def setRoot(self, flag = True):
        """
        Sets if this node is a logical root of the tree or not
        (currently the physical root is the one and only logical root)
        """
        if flag: raise Error   # TODO Better exception
        
    def getParentNode(self):
        return self.parentNode

    def getNodePresentation(self):
        """
        return a NodeStyle object for the node
        """
        return NodeStyle()
        
    def representsFamilyWikiWord(self):
        """
        True iff the node type represents a wiki word and is bound into its
        family of parent and children
        """
        return False
        
    def representsWikiWord(self):
        """
        Returns true if node represents a wiki word (not necessarily
        a defined one).
        """
        return False
        
    def listChildren(self):
        """
        Returns a sequence of Nodes for the children of this node.
        This is called before expanding the node
        """
        return ()

    def onActivate(self):
        """
        React on activation
        """
        pass
        
    def getContextMenu(self):
        """
        Return a context menu for this item or None
        """
        return None
        
    def nodeEquality(self, other):
        """
        Test for node equality
        """
        return self.__class__ == other.__class__ 



class WikiWordNode(AbstractNode):
    """
    Represents a wiki word
    """
    __slots__ = ("wikiWord", "flagChildren", "flagRoot", "ancestors")
    
    def __init__(self, tree, parentNode, wikiWord):
        AbstractNode.__init__(self, tree, parentNode)
        self.wikiWord = wikiWord
        self.flagChildren = None

#         if flagChildren is False:
#             self.flagChildren = False
#         elif self.treeCtrl.pWiki.configuration.getboolean("main", "tree_no_cycles"):
#             # All children of these node could be part of a cycle, so we
#             # don't know here if the node really has valid children
#             self.flagChildren = None
#         else:
#             self.flagChildren = flagChildren
        self.flagRoot = False
        self.ancestors = None

    def getNodePresentation(self):
        return self._createNodePresentation(self.wikiWord)

    def setRoot(self, flag = True):
        self.flagRoot = flag

    def getAncestors(self):  # TODO Check for cache clearing conditions
        """
        Returns a dictionary with the ancestor words (parent, grandparent, ...)
        as keys (instead of a list for speed reasons).
        """
        if self.ancestors is None:
            parent = self.getParentNode()
            if parent is not None:
                result = parent.getAncestors().copy()
                result[parent.getWikiWord()] = None
            else:
                result = {}
#             result = {}
#             anc = self.getParentNode()
#             while anc is not None:
#                 result[anc.getWikiWord()] = None
#                 anc = anc.getParentNode()

            self.ancestors = result

        return self.ancestors            
       

    def _getValidChildren(self, wikiPage, withPosition=False):
        """
        Get all valid children, filter out undefined and/or cycles
        if options are set accordingly
        """
        relations = wikiPage.getChildRelationships(
                existingonly=self.treeCtrl.getHideUndefined(),
                selfreference=False, withPosition=withPosition)

        if self.treeCtrl.pWiki.configuration.getboolean("main", "tree_no_cycles"):
            # Filter out cycles
            ancestors = self.getAncestors()
            if withPosition:
                relations = [r for r in relations if not ancestors.has_key(r[0])]
            else:
                relations = [r for r in relations if not ancestors.has_key(r)]

        return relations


    def _hasValidChildren(self, wikiPage):  # TODO More efficient
        """
        Check if represented word has valid children, filter out undefined
        and/or cycles if options are set accordingly
        """
#         relations = wikiPage.getChildRelationships(
#                 existingonly=self.treeCtrl.getHideUndefined(),
#                 selfreference=False)
#         if self.treeCtrl.pWiki.configuration.getboolean("main", "tree_no_cycles"):
#             # Filter out cycles
#             ancestors = self.getAncestors()
#             relations = [r for r in relations if not ancestors.has_key(r)]
        
        return len(self._getValidChildren(wikiPage, withPosition=False)) > 0


    def _createNodePresentation(self, baselabel):
        """
        Splitted to support derived class WikiWordSearchNode
        """
        wikiDataManager = self.treeCtrl.pWiki.getWikiDataManager()
        wikiData = wikiDataManager.getWikiData()
        wikiPage = wikiDataManager.getWikiPageNoError(self.wikiWord)

        style = NodeStyle()
        
        style.label = baselabel
        
        # Has children?
        if self.flagRoot:
            self.flagChildren = True # Has at least ScratchPad and Views
#         elif self.flagChildren is None:
#             # Inefficient, therefore self.flagChildren should be set
#             self.flagChildren = self._hasValidChildren(wikiPage)  # len(self._getValidChildren(wikiPage)) > 0
        else:
            self.flagChildren = self._hasValidChildren(wikiPage)
            

        style.hasChildren = self.flagChildren
        
        # apply custom properties to nodes
        wikiPage = wikiPage.getNonAliasPage() # Ensure we don't have an alias

        # if this is the scratch pad set the icon and return
        if (self.wikiWord == "ScratchPad"):
            style.icon = "note"
            return style # ?
            
            
        # fetch the global properties
        globalProps = self.treeCtrl.pWiki.wikiData.getGlobalProperties() # TODO More elegant
        # get the wikiPage properties
        props = wikiPage.getProperties()

        # priority
        priority = props.get("priority", (None,))[0]

        # priority is special. it can create an "importance" and it changes
        # the text of the node            
        if priority:
            style.label += u" (%s)" % priority
            # set default importance based on priority
            if not props.has_key(u'importance'):
                priorNum = int(priority)    # TODO Error check
                if (priorNum > 3):
                    props[u'importance'] = u'high'
                elif (priorNum < 3):
                    props[u'importance'] = u'low'


        # apply the global props based on the props of this node
        for p in _SETTABLE_PROPS:
            # Check per page props first
            if props.has_key(p):
                setattr(style, p, props[p][0])
                continue
                
            for (key, values) in props.items():
                for val in values:
                    gPropVal = globalProps.get(u"global.%s.%s.%s" % (key, val, p))
                    while not gPropVal:
                        gPropVal = globalProps.get(u"global.%s.%s" % (key, p))
                        dotpos = key.rfind(u".")
                        if dotpos == -1:
                            break
                        key = key[:dotpos]

                    if gPropVal:
                        setattr(style, p, gPropVal)

        return style


    def representsFamilyWikiWord(self):
        """
        True iff the node type is bound into its family of parent and children
        """
        return True

    def representsWikiWord(self):
        return True
        
    def listChildren(self):
        wikiDataManager = self.treeCtrl.pWiki.getWikiDataManager()
        wikiPage = wikiDataManager.getWikiPageNoError(self.wikiWord)

        # get the sort order for the children
        childSortOrder = wikiPage.getPropertyOrGlobal(u'child_sort_order',
                u"ascending")
            
        # Apply sort order
        if childSortOrder == u"natural":
            # Retrieve relations as list of tuples (child, firstcharpos)
            relations = self._getValidChildren(wikiPage, withPosition=True)
            relations.sort(_cmpCharPosition)
            # Remove firstcharpos
            relations = [r[0] for r in relations]
        else:
            # Retrieve relations as list of children words
            relations = self._getValidChildren(wikiPage, withPosition=False)
            if childSortOrder.startswith(u"desc"):
                relations.sort(_cmpLowerDesc) # sort alphabetically
            elif childSortOrder.startswith(u"asc"):
                relations.sort(_cmpLowerAsc)

#         if childSortOrder != u"unsorted":
#             if childSortOrder.startswith(u"desc"):
#                 relations.sort(_cmpLowerDesc) # sort alphabetically
#             else:
#                 relations.sort(_cmpLowerAsc)

        relationData = []
        position = 1
        for relation in relations:
            relationPage = wikiDataManager.getWikiPageNoError(relation)
            relationData.append((relation, relationPage, position))
            position += 1

        # Sort again, using tree position and priority properties
        relationData.sort(_relationSort)

        # if prev is None:
        ## Create everything new

        result = [WikiWordNode(self.treeCtrl, self, rd[0])
                for rd in relationData]
                
        if self.flagRoot:
            result.append(MainViewNode(self.treeCtrl, self))
                
        return result


    def onActivate(self):
        self.treeCtrl.pWiki.openWikiPage(self.wikiWord)
        
#     def getWikiPage(self):
#         return self.wikiPage

    def getWikiWord(self):
        return self.wikiWord

    def getContextMenu(self):
        # Take context menu from tree   # TODO Better solution esp. for event handling
        return self.treeCtrl.contextMenuWikiWords

    def nodeEquality(self, other):
        """
        Test for node equality
        """
        return AbstractNode.nodeEquality(self, other) and \
                self.wikiWord == other.wikiWord


class WikiWordSearchNode(WikiWordNode):
    """
    Derived from WikiWordNode with ability to set label different from
    wikiWord and to set search information
    """
    __slots__ = ("newLabel", "searchOp")    
    
    def __init__(self, tree, parentNode, wikiWord, newLabel = None,
            searchOp = None):
        WikiWordNode.__init__(self, tree, parentNode, wikiWord)

        self.newLabel = newLabel
        self.searchOp = searchOp

    def getAncestors(self):
        """
        Returns a dictionary with the ancestor words (parent, grandparent, ...)
        as keys (instead of a list for speed reasons).
        """
        return {}

    def getNodePresentation(self):
        if self.newLabel:
            return WikiWordNode._createNodePresentation(self, self.newLabel)
        else:
            return WikiWordNode.getNodePresentation(self)

    def onActivate(self):
        WikiWordNode.onActivate(self)
        if self.searchOp:
            self.treeCtrl.pWiki.getActiveEditor().executeSearch(self.searchOp, 0)   # TODO

    def _getValidChildren(self, wikiPage, withPosition=False):
        """
        Get all valid children, filter out undefined and/or cycles
        if options are set accordingly. A WikiWordSearchNode has no children.
        """        
        return []

    def _hasValidChildren(self, wikiPage):  # TODO More efficient
        """
        Check if represented word has valid children, filter out undefined
        and/or cycles if options are set accordingly. A WikiWordSearchNode
        has no children.
        """
        return False

    def representsFamilyWikiWord(self):
        """
        A search node is alone as child of a view subnode without
        its children or real parent
        """
        return False

    def nodeEquality(self, other):
        """
        Test for node equality
        """
        return WikiWordNode.nodeEquality(self, other) and \
                self.newLabel == other.newLabel


class MainViewNode(AbstractNode):
    """
    Represents the "Views" node
    """
    __slots__ = ()
    
    def getNodePresentation(self):
        style = NodeStyle()
        style.label = u"Views"
        style.icon = u"orgchart"
        style.hasChildren = True
        return style
        
    def listChildren(self):
        wikiData = self.treeCtrl.pWiki.wikiData
        result = []

        # add to do list nodes
        result += TodoNode(self.treeCtrl, self, ()).listChildren()
        # add property names   
        result += PropCategoryNode(self.treeCtrl, self, ()).listChildren()
        # add searches view
        node = MainSearchesNode(self.treeCtrl, self)
        if node.isVisible():
            result.append(node)
        # add last modified view
        result.append(MainModifiedWithinNode(self.treeCtrl, self))
        # add parentless view
        node = MainParentlessNode(self.treeCtrl, self)
        if node.isVisible():
            result.append(node)
            
        result.append(MainFuncPagesNode(self.treeCtrl, self))
            
        return result



class TodoNode(AbstractNode):
    """
    Represents a todo node or subnode
    """
    
    __slots__ = ("categories", "isRightSide")
            
    def __init__(self, tree, parentNode, cats, isRightSide=False):
        """
        cats -- Sequence of category (todo, action, done, ...) and
                subcategories, may also include the todo-value (=right side)
        isRightSide -- If true, the last element of cats is the
                "right side" of todo (e.g.: todo.work: This is the right side)
        """
        AbstractNode.__init__(self, tree, parentNode)
        self.categories = cats
        self.isRightSide = isRightSide


    def getNodePresentation(self):
        style = NodeStyle()
        style.hasChildren = True
        style.label = self.categories[-1]
        style.icon = "pin"
        
        if self.isRightSide:
            # Last item in self.categories is the right side, so tokenize it
            # to find properties which modify the style
            formatting = self.treeCtrl.pWiki.getFormatting()
            tokens = tokenizeTodoValue(formatting, self.categories[-1])
            for tok in tokens:
                if tok.ttype == WikiFormatting.FormatTypes.Property and \
                        tok.grpdict["propertyName"] in _SETTABLE_PROPS:
                    # Use the found property to set the style of this node
                    setattr(style, tok.grpdict["propertyName"],
                            tok.grpdict["propertyValue"])

        return style
        
    def listChildren(self):
        """
        Returns a sequence of Nodes for the children of this node.
        This is called before expanding the node
        """
        wikiData = self.treeCtrl.pWiki.wikiData
        addedTodoSubCategories = []
        addedRightSides = []
        addedWords = []
        for (wikiWord, todo) in wikiData.getTodos():
            # parse the todo for name and value
            match = WikiFormatting.ToDoREWithCapturing.match(todo)
            entryCats = tuple(match.group(1).split(u".") + [match.group(2)])
        
            if len(entryCats) < len(self.categories):
                # Can't match
                continue
            elif (len(entryCats) == len(self.categories)) and \
                    (entryCats == self.categories):
                # Same category sequence -> wiki word node
                addedWords.append((wikiWord, todo))
            elif entryCats[:len(self.categories)] == \
                    self.categories:
                # Subcategories -> category node

                nextSubCategory = entryCats[len(self.categories)]
                
                if len(entryCats) - len(self.categories) == 1:
                    # nextSubCategory is the last category (the "right side")
                    # of the todo, so handle it differently
                    if nextSubCategory not in addedRightSides:
                        addedRightSides.append(nextSubCategory)
                else:
                    if nextSubCategory not in addedTodoSubCategories:
                        addedTodoSubCategories.append(nextSubCategory)

        addedTodoSubCategories.sort()
        addedRightSides.sort()
        addedWords.sort()

        result = []
        # First list real categories, then right sides, then words
        result += [TodoNode(self.treeCtrl, self, self.categories + (c,),
                isRightSide=False) for c in addedTodoSubCategories]

        result += [TodoNode(self.treeCtrl, self, self.categories + (c,),
                isRightSide=True) for c in addedRightSides]

        def createSearchNode(wt):
            searchOp = SearchReplaceOperation()
            searchOp.wildCard = "no"
            searchOp.searchStr = wt[1]
            return WikiWordSearchNode(self.treeCtrl, self, wt[0], searchOp=searchOp)

        result += [createSearchNode(wt) for wt in addedWords]

        return result

    def nodeEquality(self, other):
        """
        Test for node equality
        """
        return AbstractNode.nodeEquality(self, other) and \
                self.categories == other.categories


class PropCategoryNode(AbstractNode):
    """
    Node representing a property category or subcategory
    """
    
    __slots__ = ("categories", "propIcon")
            
    def __init__(self, tree, parentNode, cats, propertyIcon=u"page"):
        AbstractNode.__init__(self, tree, parentNode)
        self.categories = cats
        self.propIcon = propertyIcon

    def getNodePresentation(self):   # TODO Retrieve prop icon here
        style = NodeStyle()
        globalProps = self.treeCtrl.pWiki.wikiData.getGlobalProperties()
        key = u".".join(self.categories)
        propertyIcon = globalProps.get(u"global.%s.icon" % (key), u"page")

        style.icon = propertyIcon   # u"page"  # self.propIcon
        style.label = self.categories[-1]
        style.hasChildren = True
        return style
        
    def listChildren(self):
        wikiData = self.treeCtrl.pWiki.wikiData
        result = []
        key = u".".join(self.categories + (u"",))
        
        # Start with subcategories
        addedSubCategories = {}
        for name in wikiData.getPropertyNamesStartingWith(key):
            # Cut off uninteresting
            name = name[len(key):]
            
            nextcat = name.split(u".", 1)[0]
            addedSubCategories[nextcat] = None
            
        subCats = addedSubCategories.keys()
        subCats.sort()
        result += map(lambda c: PropCategoryNode(self.treeCtrl, self,
                self.categories + (c,)), subCats)
                
        # Now the values:
        vals = wikiData.getDistinctPropertyValues(u".".join(self.categories))
        vals.sort()
        result += map(lambda v: PropValueNode(self.treeCtrl, self,
                self.categories, v), vals)
                
        # Replace a single "true" value node by its children
        if len(result) == 1 and isinstance(result[0], PropValueNode) and \
                result[0].getValue().lower() == u"true":
            result = result[0].listChildren()

        return result
        

    def nodeEquality(self, other):
        """
        Test for node equality
        """
        return AbstractNode.nodeEquality(self, other) and \
                self.categories == other.categories


class PropValueNode(AbstractNode):
    """
    Node representing a property value. Children are WikiWordSearchNode s
    """
    
    __slots__ = ("categories", "value", "propIcon")
            
    def __init__(self, tree, parentNode, cats, value, propertyIcon=u"page"):
        AbstractNode.__init__(self, tree, parentNode)
        self.categories = cats
        self.value = value
        self.propIcon = propertyIcon
        
    def getValue(self):
        return self.value

    def getNodePresentation(self):
        style = NodeStyle()
        style.icon = u"page"
        style.label = self.value
        style.hasChildren = True
        return style

    def listChildren(self):
        wikiData = self.treeCtrl.pWiki.wikiData
        result = []
        key = u".".join(self.categories)
        words = wikiData.getWordsWithPropertyValue(key, self.value)
        words.sort()                
        return [WikiWordSearchNode(self.treeCtrl, self, w) for w in words]

#         return map(lambda w: WikiWordSearchNode(self.treeCtrl,
#                 wikiData.getPage(w, toload=[""])), words)

    def nodeEquality(self, other):
        """
        Test for node equality
        """
        return AbstractNode.nodeEquality(self, other) and \
                self.categories == other.categories and \
                self.value == other.value



class MainSearchesNode(AbstractNode):
    """
    Represents the "searches" node
    """
    __slots__ = ()
    
    def getNodePresentation(self):
        style = NodeStyle()
        style.label = u"searches"
        style.icon = u"lens"
        style.hasChildren = True
        return style
        
    def isVisible(self):
        return not not self.treeCtrl.pWiki.wikiData.getSavedSearchTitles()
        
    def listChildren(self):
        wikiData = self.treeCtrl.pWiki.wikiData
        
        searchTitles = wikiData.getSavedSearchTitles()
        return map(lambda s: SearchNode(self.treeCtrl, self, s), searchTitles)


    
class SearchNode(AbstractNode):
    """
    Represents a search below the "searches" node
    """
    
    __slots__ = ("searchTitle",)
            
    def __init__(self, tree, parentNode, searchTitle):
        AbstractNode.__init__(self, tree, parentNode)
        self.searchTitle = searchTitle

    def getNodePresentation(self):
        style = NodeStyle()
        style.icon = u"lens"
        style.label = unicode(self.searchTitle)
        style.hasChildren = True
        return style

    def listChildren(self):
        wikiData = self.treeCtrl.pWiki.wikiData
        datablock = wikiData.getSearchDatablock(self.searchTitle)
        searchOp = SearchReplaceOperation()
        searchOp.setPackedSettings(datablock)
        searchOp.setTitle(self.searchTitle)
        searchOp.replaceOp = False
        words = wikiData.search(searchOp)
        words.sort()

        return [WikiWordSearchNode(self.treeCtrl, self, w, searchOp=searchOp)
                for w in words]

#         return map(lambda w: WikiWordSearchNode(self.treeCtrl,
#                 wikiData.getPage(w, toload=[""]), searchOp=searchOp),   # TODO
#                 words)

    def nodeEquality(self, other):
        """
        Test for node equality
        """
        return AbstractNode.nodeEquality(self, other) and \
                self.searchTitle.getTitle() == other.searchTitle.getTitle()



class MainModifiedWithinNode(AbstractNode):
    """
    Represents the "modified-within" node
    """
    __slots__ = ()
    
    def getNodePresentation(self):
        style = NodeStyle()
        style.label = u"modified-within"
        style.icon = u"date"
        style.hasChildren = True
        return style
        
    def listChildren(self):
        return map(lambda d: ModifiedWithinNode(self.treeCtrl, self, d),
                [1, 3, 7, 30])

    
class ModifiedWithinNode(AbstractNode):
    """
    Represents a time span below the "modified-within" node
    """
    
    __slots__ = ("daySpan",)
            
    def __init__(self, tree, parentNode, daySpan):
        AbstractNode.__init__(self, tree, parentNode)
        self.daySpan = daySpan

    def getNodePresentation(self):
        style = NodeStyle()
        style.icon = u"date"
        if self.daySpan == 1:
            style.label = u"1 day"
        else:
            style.label = u"%i days" % self.daySpan
        style.hasChildren = True   #?
        return style

    def listChildren(self):
        wikiData = self.treeCtrl.pWiki.wikiData
        words = wikiData.getWikiWordsModifiedWithin(self.daySpan)
        words.sort()
                
        return [WikiWordSearchNode(self.treeCtrl, self, w) for w in words]

#         return map(lambda w: WikiWordSearchNode(self.treeCtrl,
#                 wikiData.getPage(w, toload=[""])),
#                 words)

    def nodeEquality(self, other):
        """
        Test for node equality
        """
        return AbstractNode.nodeEquality(self, other) and \
                self.daySpan == other.daySpan


class MainParentlessNode(AbstractNode):
    """
    Represents the "parentless" node
    """
    __slots__ = ()
    
    def getNodePresentation(self):
        style = NodeStyle()
        style.label = u"parentless-nodes"
        style.icon = u"link"
        style.hasChildren = True
        return style
        
    def isVisible(self):
        wikiData = self.treeCtrl.pWiki.wikiData
        return len(wikiData.getParentlessWikiWords()) > 1  # TODO Test if root is single element
        
    def listChildren(self):
        wikiData = self.treeCtrl.pWiki.wikiData
        words = wikiData.getParentlessWikiWords()
        words.sort()
        
#         words = filter(lambda w: w != self.treeCtrl.pWiki.wikiName, words)
                
        return [WikiWordSearchNode(self.treeCtrl, self, w) for w in words
                if w != self.treeCtrl.pWiki.wikiName]
                
#         return map(lambda w: WikiWordSearchNode(self.treeCtrl,
#                 wikiData.getPage(w, toload=[""])),
#                 words)




class MainFuncPagesNode(AbstractNode):
    """
    Represents the "Func pages" node
    """
    __slots__ = ()
    
    def getNodePresentation(self):
        style = NodeStyle()
        style.label = u"Func. pages"
        style.icon = u"cog"
        style.hasChildren = True
        return style
        
    def listChildren(self):
        return [
                FuncPageNode(self.treeCtrl, self, "global/[TextBlocks]"),
                FuncPageNode(self.treeCtrl, self, "wiki/[TextBlocks]")
                ]


class FuncPageNode(AbstractNode):
    """
    Node representing a functional page
    """
    
    __slots__ = ("funcTag", "label")
    
    TAG_TO_LABEL_MAP = {    # Maps the func tag to the node's label
            "global/[TextBlocks]": u"Global text blocks",
            "wiki/[TextBlocks]": u"Wiki text blocks"
        }

    def __init__(self, tree, parentNode, funcTag):
        AbstractNode.__init__(self, tree, parentNode)
        self.funcTag = funcTag
        self.label = self.TAG_TO_LABEL_MAP.get(self.funcTag, self.funcTag)

    def getNodePresentation(self):
        """
        return a NodeStyle object for the node
        """
        style = NodeStyle()
        style.label = self.label
        style.icon = u"cog"
        style.hasChildren = False

        return style

    def onActivate(self):
        """
        React on activation
        """
        self.treeCtrl.pWiki.openFuncPage(self.funcTag)

#     def getContextMenu(self):
#         """
#         Return a context menu for this item or None
#         """
#         return None
        
    def nodeEquality(self, other):
        """
        Test for node equality
        """
        return AbstractNode.nodeEquality(self, other) and \
                self.funcTag == other.funcTag




# ----------------------------------------------------------------------


class WikiTreeCtrl(wxTreeCtrl):
    def __init__(self, pWiki, parent, ID):        
        wxTreeCtrl.__init__(self, parent, ID, style=wxTR_HAS_BUTTONS)
        self.pWiki = pWiki

        self.refreshGenerator = None  # Generator called in OnIdle
#         self.refreshCheckChildren = [] # List of nodes to check for new/deleted children

        EVT_TREE_ITEM_ACTIVATED(self, ID, self.OnTreeItemActivated)
        EVT_TREE_SEL_CHANGED(self, ID, self.OnTreeItemActivated)
        EVT_TREE_ITEM_EXPANDING(self, ID, self.OnTreeItemExpand)
        EVT_TREE_ITEM_COLLAPSED(self, ID, self.OnTreeItemCollapse)
        EVT_RIGHT_DOWN(self, self.OnRightButtonDown)   # TODO Context menu
        EVT_IDLE(self, self.OnIdle)
        
        res = xrc.wxXmlResource.Get()
        self.contextMenuWikiWords = res.LoadMenu("MenuTreectrlWikiWords")

        # TODO Let PersonalWikiFrame handle this 
        EVT_MENU(self, GUI_ID.CMD_RENAME_WIKIWORD,
                lambda evt: self.pWiki.showWikiWordRenameDialog())
        EVT_MENU(self, GUI_ID.CMD_DELETE_WIKIWORD,
                lambda evt: self.pWiki.showWikiWordDeleteDialog())
        EVT_MENU(self, GUI_ID.CMD_BOOKMARK_WIKIWORD,
                lambda evt: self.pWiki.insertAttribute("bookmarked", "true"))
        EVT_MENU(self, GUI_ID.CMD_SETASROOT_WIKIWORD,
                lambda evt: self.pWiki.setCurrentWordAsRoot())


##        self.pWiki.getMiscEvent().addListener(DebugSimple("tree event:"))
        # Register for pWiki events
        self.pWiki.getMiscEvent().addListener(KeyFunctionSink((
                ("loading current page", self.onLoadingCurrentWikiPage),
                ("closed current wiki", self.onClosedCurrentWiki),
                ("updated current page props", self.onUpdatedCurrentPageProps), # TODO is event fired somewhere?
                ("renamed page", self.onRenamedWikiPage),
                ("deleted page", self.onDeletedWikiPage)
        )))


    def collapse(self):
        rootNode = self.GetRootItem()
        self.CollapseAndReset(rootNode)
        
    def getHideUndefined(self):
        return self.pWiki.configuration.getboolean("main", "hideundefined")

    def onLoadingCurrentWikiPage(self, miscevt):
#         if miscevt.get("forceTreeSyncFromRoot", False):
#             self.buildTreeForWord(self.pWiki.getCurrentWikiWord(),
#                     selectNode=True)
#         else:
        currentNode = self.GetSelection()
        if currentNode.IsOk():
            node = self.GetPyData(currentNode)
            if node.representsWikiWord():                    
                if self.pWiki.wikiData.getAliasesWikiWord(node.getWikiWord()) ==\
                        self.pWiki.getCurrentWikiWord():
                    return  # Is already on word -> nothing to do
            if node.representsFamilyWikiWord():
                # If we know the motionType, tree selection can be moved smart
                motionType = miscevt.get("motionType", "random")
                if motionType == "parent":
                    parentnodeid = self.GetItemParent(currentNode)
                    if parentnodeid.IsOk():
                        parentnode = self.GetPyData(parentnodeid)
                        if parentnode.representsWikiWord() and \
                                (parentnode.getWikiWord() == \
                                self.pWiki.getCurrentWikiWord()):
                            self.SelectItem(parentnodeid)
                            return
                elif motionType == "child":
                    if not self.IsExpanded(currentNode) and \
                            self.pWiki.configuration.getboolean("main",
                            "tree_auto_follow"):
                        # Expand node to find child
                        self.Expand(currentNode)

                    if self.IsExpanded(currentNode):
                        child = self.findChildTreeNodeByWikiWord(currentNode,
                                self.pWiki.getCurrentWikiWord())
                        if child:
                            self.SelectItem(child)
                            return
#                         else:
#                             # TODO !!!!!! Better method if child doesn't even exist!
#                             # Move to child but child not found ->
#                             # subtree below currentNode might need
#                             # a refresh
#                             self.CollapseAndReset(currentNode)  # AndReset?
#                             self.Expand(currentNode)
# 
#                             child = self.findChildTreeNodeByWikiWord(currentNode,
#                                     self.pWiki.getCurrentWikiWord())
#                             if child:
#                                 self.SelectItem(child)
#                                 return
                    
        # No cheap way to find current word in tree    
        if self.pWiki.configuration.getboolean("main", "tree_auto_follow") or \
                miscevt.get("forceTreeSyncFromRoot", False):
            # Configuration or event says to use expensive way
            self.buildTreeForWord(self.pWiki.getCurrentWikiWord(),
                    selectNode=True)
        else:    
            # Can't find word -> remove selection
            self.Unselect()


    def onUpdatedCurrentPageProps(self, miscevt):
        if not self.pWiki.configuration.getboolean("main", "tree_update_after_save"):
            return

        self.refreshGenerator = self._generatorRefreshNodeAndChildren(
                self.GetRootItem())
                
#         wikiData = self.pWiki.wikiData
#         wikiWord = wikiData.getAliasesWikiWord(self.pWiki.getCurrentWikiWord())
#         if not wikiWord in self.refreshCheckChildren:
#             self.refreshCheckChildren.append(wikiWord)


        # self._refreshNodeAndChildren(self.GetRootItem())        
        # print "onUpdatedCurrentPageProps2"


    def onDeletedWikiPage(self, miscevt):  # TODO May be called multiple times if
                                           # multiple pages are deleted at once
        if not self.pWiki.configuration.getboolean("main", "tree_update_after_save"):
            return

        self.refreshGenerator = self._generatorRefreshNodeAndChildren(
                self.GetRootItem())
        
        

    def _generatorRefreshNodeAndChildren(self, parentnodeid):
        nodeObj = self.GetPyData(parentnodeid)
        wikiData = self.pWiki.wikiData

        self.setNodePresentation(parentnodeid, nodeObj.getNodePresentation())
        if not self.IsExpanded(parentnodeid):
            raise StopIteration
            
        if nodeObj.representsWikiWord():
            wikiWord = wikiData.getAliasesWikiWord(nodeObj.getWikiWord())

##         if not nodeObj.representsFamilyWikiWord() or \
##                 wikiWord in self.refreshCheckChildren:
        if True:
            # We have to recreate the children of this node
            
            # This is time consuming
            children = nodeObj.listChildren()
            
            nodeid, cookie = self.GetFirstChild(parentnodeid)
            tci = 0  # Tree child index
            for c in children:
                if nodeid.IsOk():
                    nodeObj = self.GetPyData(nodeid)
                    if c.nodeEquality(nodeObj):
                        # Previous child matches new child -> normal refreshing
                        if self.IsExpanded(nodeid):
                            # Recursive generator call
                            try:
                                gen = self._generatorRefreshNodeAndChildren(nodeid)
                                while True:
                                    yield gen.next()
                            except StopIteration:
                                pass
                        else:
                            self.setNodePresentation(nodeid,
                                    nodeObj.getNodePresentation())
                            
                            yield None
                            
                        nodeid, cookie = self.GetNextChild(nodeid, cookie)
                        tci += 1                           

                    else:
                        # Old and new don't match -> Insert new child
                        newnodeid = self.InsertItemBefore(parentnodeid, tci, "")
                        tci += 1
                        self.SetPyData(newnodeid, c)
                        self.setNodePresentation(newnodeid,
                                c.getNodePresentation())
                        
                        yield None

                else:
                    # No more nodes in tree, but some in new children list
                    # -> append one to tree
                    newnodeid = self.AppendItem(parentnodeid, "")
                    self.SetPyData(newnodeid, c)
                    self.setNodePresentation(newnodeid,
                            c.getNodePresentation())


            # End of loop, no more new children, remove possible remaining
            # children in tree
            
            selnodeid = self.GetSelection()
            
            while nodeid.IsOk():
                # Trying to prevent failure of GetNextChild() after deletion
                delnodeid = nodeid                
                nodeid, cookie = self.GetNextChild(nodeid, cookie)
                
                if selnodeid.IsOk() and selnodeid == delnodeid:
                    self.Unselect()
                self.Delete(delnodeid)
        else:
            # Recreation of children not necessary -> simple refresh<
            nodeid, cookie = self.GetFirstChild(parentnodeid)
            while nodeid.IsOk():
                if self.IsExpanded(nodeid):
                    # Recursive generator call
                    try:
                        gen = self._generatorRefreshNodeAndChildren(nodeid)
                        while True:
                            yield gen.next()
                    except StopIteration:
                        pass
                else:
                    nodeObj = self.GetPyData(nodeid)
                    self.setNodePresentation(nodeid, nodeObj.getNodePresentation())
                    
                    yield None

                nodeid, cookie = self.GetNextChild(nodeid, cookie)
            
        raise StopIteration


    def onRenamedWikiPage(self, miscevt):
        if not self.pWiki.configuration.getboolean("main", "tree_update_after_save"):
            return

        self.refreshGenerator = self._generatorRefreshNodeAndChildren(
                self.GetRootItem())
#         self.collapse()   # TODO?


    def onClosedCurrentWiki(self, miscevt):
        self.refreshGenerator = None


    def buildTreeForWord(self, wikiWord, selectNode=False, doexpand=False):
        """
        First tries to find a path from wikiWord to the currently selected node.
        If nothing is found, searches for a path from wikiWord to the root.
        Expands the tree out if a path is found.
        """
        
#         if selectNode:
#             doexpand = True

        wikiData = self.pWiki.wikiData
        currentNode = self.GetSelection()    # self.GetRootItem()
        
        crumbs = None
        
        if currentNode.IsOk() and self.GetPyData(currentNode).representsFamilyWikiWord():
            # check for path from wikiWord to currently selected tree node            
            currentWikiWord = self.GetPyData(currentNode).getWikiWord() #self.getNodeValue(currentNode)
            crumbs = wikiData.findBestPathFromWordToWord(wikiWord, currentWikiWord)
            
            if crumbs and self.pWiki.configuration.getboolean("main",
                    "tree_no_cycles"):
                ancestors = self.GetPyData(currentNode).getAncestors()
                # If an ancestor of the current node is in the crumbs, the
                # crumbs path is invalid because it contains a cycle
                for c in crumbs:
                    if ancestors.has_key(c):
                        crumbs = None
                        break
        
        # if a path is not found try to get a path to the root node
        if not crumbs:
            currentNode = self.GetRootItem()
            if currentNode.IsOk():
                currentWikiWord = self.GetPyData(currentNode).getWikiWord()
                crumbs = wikiData.findBestPathFromWordToWord(wikiWord,
                        currentWikiWord)


        if crumbs:
            numCrumbs = len(crumbs)

            # expand all of the parents
            for i in range(0, numCrumbs):
                # fill in the missing nodes for each parent. expand can actually
                # replace currentNode under special conditions, which would invalidate
                # the currentNode pointer
                try:
                    if doexpand:
                        self.Expand(currentNode)

                    # fetch the next crumb node
                    if (i+1) < numCrumbs:
                        self.Expand(currentNode)
                        currentNode = self.findChildTreeNodeByWikiWord(currentNode,
                                crumbs[i+1])
                except Exception, e:
                    sys.stderr.write("error expanding tree node: %s\n" % e)


            # set the ItemHasChildren marker if the node is not expanded
            if currentNode:
                currentWikiWord = self.GetPyData(currentNode).getWikiWord()

                # the only time this could be 0 really is if the expand above
                # invalidated the root pointer
                

            # TODO Check if necessary:
                
#                 if len(currentWikiWord) > 0:
#                     try:
#                         currentNodePage = wikiData.getPage(currentWikiWord, toload=[""])   # 'children', 
#                         self.updateTreeNode(currentNodePage, currentNode)
#                     except Exception, e:
#                         sys.stderr.write(str(e))

                if doexpand:
                    self.EnsureVisible(currentNode)                            
                if selectNode:
                    self.SelectItem(currentNode)

    def findChildTreeNodeByWikiWord(self, fromNode, findWord):
        (child, cookie) = self.GetFirstChild(fromNode)    # , 0
        while child:
            nodeobj = self.GetPyData(child)
#             if nodeobj.representsFamilyWikiWord() and nodeobj.getWikiWord() == findWord:
            if nodeobj.representsFamilyWikiWord() and \
                    self.pWiki.wikiData.getAliasesWikiWord(nodeobj.getWikiWord())\
                    == findWord:
                return child
            
            (child, cookie) = self.GetNextChild(fromNode, cookie)
        return None


    def setRootByWord(self, rootword):
        """
        Clear the tree and use page described by rootpage as
        root of the tree
        """
        self.DeleteAllItems()
        # add the root node to the tree
        nodeobj = WikiWordNode(self, None, rootword)
        nodeobj.setRoot(True)
        root = self.AddRoot(u"")
        self.SetPyData(root, nodeobj)
        self.setNodePresentation(root, nodeobj.getNodePresentation())
        self.SelectItem(root)
        self.Expand(root)        


    def setNodeImage(self, node, image):
        try:
            index = self.pWiki.lookupIconIndex(image)
            if index == -1:
                index = self.pWiki.lookupIconIndex(u"page")
            ## if icon:
                ## self.SetItemImage(node, index, wxTreeItemIcon_Selected)
                ## self.SetItemImage(node, index, wxTreeItemIcon_Expanded)
                ## self.SetItemImage(node, index, wxTreeItemIcon_SelectedExpanded)
            self.SetItemImage(node, index, wxTreeItemIcon_Normal)
        except:
            try:
                self.SetItemImage(node, 0, wxTreeItemIcon_Normal)
            except:
                pass    
                
                    
    def setNodeColor(self, node, color):
        if color == "null":
            self.SetItemTextColour(node, wxNullColour)
        else:
            self.SetItemTextColour(node, wxNamedColour(color))


    def setNodePresentation(self, node, style):
        self.SetItemText(node, uniToGui(style.label))
        self.setNodeImage(node, style.icon)
        self.SetItemBold(node, strToBool(style.bold, False))
        self.setNodeColor(node, style.color)
        self.SetItemHasChildren(node, style.hasChildren)
        
        
    def OnTreeItemActivated(self, event):
        item = event.GetItem()   
        if item.IsOk():
            self.GetPyData(item).onActivate()
        
        event.Skip()
                    
    def OnTreeItemExpand(self, event):
        ## _prof.start()
        item = event.GetItem()
        if self.IsExpanded(item):   # TODO Check if a good idea
            return

        itemobj = self.GetPyData(item)

        childnodes = itemobj.listChildren()

        #self.Freeze()
        try:
            for ch in childnodes:
                newit = self.AppendItem(item, u"")
                self.SetPyData(newit, ch)
                self.setNodePresentation(newit, ch.getNodePresentation())
        finally:
            pass
            #self.Thaw()

        ## _prof.stop()
     

    def OnTreeItemCollapse(self, event):
        self.DeleteChildren(event.GetItem())

    def OnRightButtonDown(self, event):
        menu = self.GetPyData(self.GetSelection()).getContextMenu()

        if menu is not None:
            self.PopupMenuXY(menu, event.GetX(), event.GetY())

    def OnIdle(self, event):
        gen = self.refreshGenerator
        if gen is not None:
            try:
                gen.next()
            except StopIteration:
                if self.refreshGenerator == gen:
                    self.refreshGenerator = None
#                     self.refreshCheckChildren = []

def _relationSort(a, b):
    propsA = a[1].getProperties()
    propsB = b[1].getProperties()

    aSort = None
    bSort = None

    try:
        if (propsA.has_key(u'tree_position')):
            aSort = int(propsA[u'tree_position'][0])
        elif (propsA.has_key(u'priority')):
            aSort = int(propsA[u'priority'][0])
        else:
            aSort = a[2]
    except:
        aSort = a[2]

    try:            
        if (propsB.has_key(u'tree_position')):
            bSort = int(propsB[u'tree_position'][0])
        elif (propsB.has_key(u'priority')):
            bSort = int(propsB[u'priority'][0])
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

# sorter for relations, removes brackets and sorts lower case
def _cmpLowerDesc(a, b):
    return cmp(b.lower(), a.lower())

def _cmpLowerAsc(a, b):
    return cmp(a.lower(), b.lower())

