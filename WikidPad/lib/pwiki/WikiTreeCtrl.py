import sys, time, traceback

## import profilehooks
## profile = profilehooks.profile(filename="profile.prf")
## import hotshot
## _prof = hotshot.Profile("hotshot.prf")

import wx, wx.xrc

from . import customtreectrl

from .wxHelper import GUI_ID, wxKeyFunctionSink, textToDataObject, \
        appendToMenuByMenuDesc, copyTextToClipboard
from .MiscEvent import DebugSimple   # , KeyFunctionSink

from .WikiExceptions import WikiWordNotFoundException, InternalError, \
        NoPageAstException

from . import Utilities
from .Utilities import StringPathSet


from .Configuration import MIDDLE_MOUSE_CONFIG_TO_TABMODE
from . import AttributeHandling
from . import DocPages
from .SearchAndReplace import SearchReplaceOperation

from .StringOps import strToBool, \
        pathWordAndAnchorToWikiUrl, escapeForIni, unescapeForIni, \
        colorDescToRgbTuple

from .DocPagePresenter import BasicDocPagePresenter

from .AdditionalDialogs import SelectWikiWordDialog


class NodeStyle:
    """
    A simple structure to hold all necessary information to present a tree node.
    """
    
    __slots__ = ("__weakref__", "label", "bold", "icon", "color", "bgcolor",
            "hasChildren")
    def __init__(self):
        self.label = ""
        
        self.bold = "False"
        self.icon = "page"
        self.color = "null"
        self.bgcolor = "null"
        
        self.hasChildren = False
    
    def emptyFields(self):
        self.label = ""
        
        self.bold = ""
        self.icon = ""
        self.color = "null"
        self.bgcolor = "null"



_SETTABLE_ATTRS = ("bold", "icon", "color", "bgcolor")


# New style class to allow __slots__ for efficiency
class AbstractNode:
    """
    Especially for view nodes. An instance of a derived class
    is saved in funcData for such special nodes
    """
    
    __slots__ = ("__weakref__",   # just in case...
            "treeCtrl", "wxItemId", "parentNode", "unifiedName")
            
    def __init__(self, tree, parentNode):
        self.treeCtrl = tree
        self.parentNode = parentNode
        self.wxItemId = -1
        # self.unifiedName = None

    def setRoot(self, flag = True):
        """
        Sets if this node is a logical root of the tree or not
        (currently the physical root is the one and only logical root)
        """
        pass
    
    def setWxItemId(self, wxItemId):
        self.wxItemId = wxItemId

    def getParentNode(self):
        return self.parentNode

    def getNodePresentation(self):
        """
        return a NodeStyle object for the node. This should be called mainly
        in background threads.
        """
        return NodeStyle()

    def getNodePresentationFast(self):
        """
        return a NodeStyle object for the node or None. If a style is returned it
        may be inaccurate because calculation is time-consuming. In this case
        call getNodePresentation() later in background to get proper style.
        If None is returned just call getNodePresentation() directly
        """
        return None
        
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
        This is called before expanding the node. This should be called mainly
        in background threads.
        """
        return ()
        
    def listChildrenFast(self):
        """
        Returns a sequence of Nodes for the children of this node or None.
        This is called before expanding the node. If a sequence is returned it
        may be inaccurate because calculation is time-consuming. In this case
        call listChildren() later in background to get proper style.
        If None is returned just call listChildren() directly.
        
        If a node doesn't have children an empty sequence is returned (not None!)
        """
        return None

    def onSelected(self):
        """
        React on selection of the item
        """
        pass
        
    def onActivated(self):
        """
        React on activation (double click). Returns True if event should be
        consumed (not handled further)
        """
        return False

    def prepareContextMenu(self, menu):
        """
        Return a context menu for this item or None
        """
        return None

    def getUnifiedName(self):
        """
        Return unistring describing this node. It is used to build a "path"
        in tree to identify a particular node (esp. to store if node is
        expanded or not).
        """
        return self.unifiedName
        
    def getNodePath(self):
        """
        Return a "path" (=list of node descriptors) to identify a particular
        node in tree.
        
        A single node descriptor isn't enough as a node for the same wiki word
        has the same descriptor and can appear in multiple places in tree.
        """
        if self.parentNode is None:
            return [self.getUnifiedName()]

        result = self.parentNode.getNodePath()
        result.append(self.getUnifiedName())
        return result

    def nodeEquality(self, other):
        """
        Test for node equality
        """
        return self.__class__ == other.__class__ 



class WikiWordNode(AbstractNode):
    """
    Represents a wiki word
    """
    __slots__ = ("wikiWord", "flagChildren", "flagRoot", "ancestors", "newLabel")

    def __init__(self, tree, parentNode, wikiWord):
        AbstractNode.__init__(self, tree, parentNode)
        self.wikiWord = wikiWord
        self.unifiedName = "wikipage/" + self.wikiWord

        self.flagRoot = False
        self.ancestors = None
        
        # Calculate label
        self.newLabel = self.wikiWord

        if parentNode is not None and isinstance(parentNode, WikiWordNode):
            parentWw = parentNode.getWikiWord()
            if parentWw is not None:
                wikiDocument = self.treeCtrl.pWiki.getWikiDocument()
                langHelper = wx.GetApp().createWikiLanguageHelper(
                        wikiDocument.getWikiDefaultWikiLanguage())

                relLink = langHelper.createRelativeLinkFromWikiWord(
                        self.wikiWord, parentWw)
                if relLink is not None:
                    self.newLabel = relLink


    def getNodePresentationFast(self):
        return None # self._createNodePresentation(self.newLabel, fast=True)

    def getNodePresentation(self):
        return self._createNodePresentation(self.newLabel)

    def setRoot(self, flag = True):
        self.flagRoot = flag

    def getAncestors(self):  # TODO Check for cache clearing conditions
        """
        Returns a set with the ancestor words (parent, grandparent, ...).
        """
        if self.ancestors is None:
            parent = self.getParentNode()
            if parent is not None:
                result = parent.getAncestors().union((parent.getWikiWord(),))
            else:
                result = frozenset()

            self.ancestors = result

        return self.ancestors            


#     def _getValidChildren(self, wikiPage, withFields=()):
#         """
#         Get all valid children, filter out undefined and/or cycles
#         if options are set accordingly
#         """
#         config = self.treeCtrl.pWiki.getConfig()
# 
#         if config.getboolean("main", "tree_no_cycles"):
#             # Filter out cycles
#             ancestors = self.getAncestors()
#         else:
#             ancestors = frozenset()  # Empty
# 
#         relations = wikiPage.getChildRelationships(
#                 existingonly=self.treeCtrl.getHideUndefined(),
#                 selfreference=False, withFields=withFields,
#                 excludeSet=ancestors)
# 
#         return relations


    def _hasValidChildren(self, wikiPage):  # TODO More efficient
        """
        Check if represented word has valid children, filter out undefined
        and/or cycles if options are set accordingly
        """
        if self.treeCtrl.pWiki.getConfig().getboolean("main", "tree_no_cycles"):
            # Filter out cycles
            ancestors = self.getAncestors().union((self.getWikiWord(),))
        else:
            ancestors = frozenset()  # Empty

        relations = wikiPage.getChildRelationships(
                existingonly=self.treeCtrl.getHideUndefined(),
                selfreference=False, withFields=())

        if len(relations) > len(ancestors):
            return True
            
        for r in relations:
            if r not in ancestors:
                return True
                
        return False


    def _createNodePresentation(self, baselabel, fast=False):
        """
        Splitted to support derived class WikiWordSearchNode
        """
        assert isinstance(baselabel, str)

        wikiDocument = self.treeCtrl.pWiki.getWikiDocument()
        wikiData = wikiDocument.getWikiData()
        wikiPage = wikiDocument.getWikiPageNoError(self.wikiWord)

        style = NodeStyle()
        
        style.label = baselabel

        # Has children?
        if self.flagRoot:
            style.hasChildren = True # Has at least Views
        else:
            style.hasChildren = fast or self._hasValidChildren(wikiPage)

        # apply custom attributes to nodes
        wikiPage = wikiPage.getNonAliasPage() # Ensure we don't have an alias

        # if this is the scratch pad set the icon and return
        if (self.wikiWord == "ScratchPad"):
            style.icon = "note"
            return style # ?


        # fetch the global attributes
        globalAttrs = self.treeCtrl.pWiki.getWikiData().getGlobalAttributes() # TODO More elegant
        # get the wikiPage attributes
        attrs = wikiPage.getAttributes()

        # priority
        priority = attrs.get("priority", (None,))[-1]

        # priority is special. it can create an "importance" and it changes
        # the text of the node            
        if priority:
            style.label += " (%s)" % priority
            # set default importance based on priority
            if 'importance' not in attrs:
                try:
                    priorNum = int(priority)    # TODO Error check
                    if (priorNum < 3):
                        attrs['importance'] = ['high']
                    elif (priorNum > 3):
                        attrs['importance'] = ['low']
                except ValueError:
                    pass

        attrsItems = list(attrs.items())

        # apply the global attrs based on the attrs of this node
        for p in _SETTABLE_ATTRS:
            # Check per page attrs first
            if p in attrs:
                setattr(style, p, attrs[p][-1])
                continue

            # Check attrs on page against global presentation attrs.
            # The dots in the key matter. The more dots the more specific
            # is the global prop and wins over less specific attrs

            gPropVal = None
            dots = -1

            # Preset if something like e.g. [global.color: green] is available
            newGPropVal = globalAttrs.get(u"global.%s" % p)
            if newGPropVal is not None:
                gPropVal = newGPropVal

            for (key, values) in attrsItems:
                newGPropVal = None
                newDots = key.count(".") + 1 # key dots plus one for value
                if newDots > dots:
                    for val in values:
                        newGPropVal = globalAttrs.get("global.%s.%s.%s" % (key, val, p))
                        if newGPropVal is not None:
                            gPropVal = newGPropVal
                            dots = newDots
                            break

                    # Now check without value
                    newDots -= 1
                    while newDots > dots:
                        newGPropVal = globalAttrs.get("global.%s.%s" % (key, p))
                        if newGPropVal is not None:
                            break
    
                        dotpos = key.rfind(".")
                        if dotpos == -1:
                            break
                        key = key[:dotpos]
                        newDots -= 1
    
                    if newGPropVal is not None:
                        gPropVal = newGPropVal
                        dots = newDots

            # If a value is found, we stop searching for this presentation
            # attribute here
            if gPropVal is not None:
                setattr(style, p, gPropVal)
                continue

        return style


    def representsFamilyWikiWord(self):
        """
        True iff the node type is bound into its family of parent and children
        """
        return True


    def representsWikiWord(self):
        return True


##     @profile
    def listChildren(self):
##         _prof.start()
        wikiDocument = self.treeCtrl.pWiki.getWikiDocument()
        wikiPage = wikiDocument.getWikiPageNoError(self.wikiWord)

        if self.treeCtrl.pWiki.getConfig().getboolean("main", "tree_no_cycles"):
            # Filter out cycles
            ancestors = self.getAncestors().union((self.getWikiWord(),))
        else:
            ancestors = frozenset()  # Empty

        if self.treeCtrl.pWiki.getConfig().getboolean(
                "main", "tree_force_scratchpad_visibility", False) and \
                self.flagRoot:
            includeSet = frozenset(("ScratchPad",))
        else:
            includeSet = frozenset()

        children = wikiPage.getChildRelationshipsTreeOrder(
                existingonly=self.treeCtrl.getHideUndefined(),
                excludeSet=ancestors, includeSet=includeSet)

        result = [WikiWordNode(self.treeCtrl, self, c)
                for c in children]

        if self.flagRoot:
            result.append(MainViewNode(self.treeCtrl, self))

##         _prof.stop()

        return result


    def onSelected(self):
#         tracer.runctx('self.treeCtrl.pWiki.openWikiPage(self.wikiWord)', globals(), locals())
        self.treeCtrl.pWiki.openWikiPage(self.wikiWord)

    def getWikiWord(self):
        return self.wikiWord

    def prepareContextMenu(self, menu):
        # Take context menu from tree   # TODO Better solution esp. for event handling
        return self.treeCtrl.contextMenuWikiWords

    def nodeEquality(self, other):
        """
        Test for node equality
        """
        return AbstractNode.nodeEquality(self, other) and \
                self.wikiWord == other.wikiWord


class WikiWordRelabelNode(WikiWordNode):
    """
    Derived from WikiWordNode with ability to set label differently from
    wikiWord
    """
    # __slots__ = ("newLabel",)    
    
    def __init__(self, tree, parentNode, wikiWord, newLabel = None):
        WikiWordNode.__init__(self, tree, parentNode, wikiWord)

        if newLabel is not None:
            self.newLabel = newLabel

    def getAncestors(self):
        """
        Returns a set with the ancestor words (parent, grandparent, ...).
        """
        return frozenset()

#     def getNodePresentation(self):
#         if self.newLabel:
#             return WikiWordNode._createNodePresentation(self, self.newLabel)
#         else:
#             return WikiWordNode.getNodePresentation(self)

#     def _getValidChildren(self, wikiPage, withFields=False):
#         """
#         Get all valid children, filter out undefined and/or cycles
#         if options are set accordingly. A WikiWordSearchNode has no children.
#         """        
#         return []

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



class WikiWordSearchNode(WikiWordRelabelNode):
    """
    Derived from WikiWordRelabelNode with ability to set label different from
    wikiWord and to set search information
    """
    __slots__ = ("searchOp",)    
    
    def __init__(self, tree, parentNode, wikiWord, newLabel = None,
            searchOp = None):
        WikiWordRelabelNode.__init__(self, tree, parentNode, wikiWord, newLabel)

        self.searchOp = searchOp

    def onSelected(self):
        # WikiWordNode.onSelected(self)
        WikiWordRelabelNode.onSelected(self)
        if self.searchOp:
            self.treeCtrl.pWiki.getActiveEditor().executeSearch(self.searchOp, 0)   # TODO



class MainViewNode(AbstractNode):
    """
    Represents the "Views" node
    """
    __slots__ = ()


    def __init__(self, tree, parentNode):
        AbstractNode.__init__(self, tree, parentNode)
        self.unifiedName = "helpernode/main/view"

    def getNodePresentation(self):
        style = NodeStyle()
        style.label = _("Views")
        style.icon = "orgchart"
        style.hasChildren = True
        return style
        
    def listChildrenFast(self):
##         _prof.start()
        wikiData = self.treeCtrl.pWiki.getWikiData()
        result = []

        # add to do list nodes
        result += TodoNode(self.treeCtrl, self, ()).listChildren()
        # add property names   
        result += AttrCategoryNode(self.treeCtrl, self, ()).listChildren()
        # add "searches" view
        node = MainSearchesNode(self.treeCtrl, self)
        result.append(node)
        # add "last modified" view
        result.append(MainModifiedWithinNode(self.treeCtrl, self))
        # add "parentless" view
        node = MainParentlessNode(self.treeCtrl, self)
        # Checking visibility takes some time, so it is just listed
        # if node.isVisible():
        result.append(node)
        # add "undefined" view
        node = MainUndefinedNode(self.treeCtrl, self)
        # if node.isVisible():
        result.append(node)

        result.append(MainFuncPagesNode(self.treeCtrl, self))
##         _prof.stop()

        return result

    def listChildren(self):
##         _prof.start()
        wikiData = self.treeCtrl.pWiki.getWikiData()
        result = []

        # add to do list nodes
        result += TodoNode(self.treeCtrl, self, ()).listChildren()
        # add property names   
        result += AttrCategoryNode(self.treeCtrl, self, ()).listChildren()
        # add "searches" view
        node = MainSearchesNode(self.treeCtrl, self)
        if node.isVisible():
            result.append(node)
        # add "last modified" view
        result.append(MainModifiedWithinNode(self.treeCtrl, self))
        # add "parentless" view
        node = MainParentlessNode(self.treeCtrl, self)
        if node.isVisible():
            result.append(node)
        # add "undefined" view
        node = MainUndefinedNode(self.treeCtrl, self)
        if node.isVisible():
            result.append(node)

        result.append(MainFuncPagesNode(self.treeCtrl, self))
##         _prof.stop()
            
        return result



class TodoNode(AbstractNode):
    """
    Represents a todo node or subnode
    """
    
    __slots__ = ("categories", "isRightSide")
            
    def __init__(self, tree, parentNode, cats):  # , isRightSide=False):
        """
        cats -- Sequence of category (todo, action, done, ...) and
                subcategories, may also include the todo-value (=right side)
        isRightSide -- If true, the last element of cats is the
                "right side" of todo (e.g.: todo.work: This is the right side)
        """
        AbstractNode.__init__(self, tree, parentNode)
        self.categories = cats
        self.unifiedName = "todo/" + ".".join(self.categories)


    def getNodePresentation(self):
        style = NodeStyle()
        style.emptyFields()

        style.hasChildren = True
        
        wikiDocument = self.treeCtrl.pWiki.getWikiDocument()
        langHelper = wx.GetApp().createWikiLanguageHelper(
                wikiDocument.getWikiDefaultWikiLanguage())

        nodes = langHelper.parseTodoValue(self.categories[-1], wikiDocument)
        if nodes is not None:
            # Complicated version for compatibility with old language plugins
            # TODO remove "property"-compatibility
            for attrNode in Utilities.iterMergesort((
                    nodes.iterDeepByName("property"),
                    nodes.iterDeepByName("attribute") ),
                    key=lambda n: n.pos):
                for key, value in attrNode.attrs:
                    if key in _SETTABLE_ATTRS:
                        setattr(style, key, value)

        if style.label == "":
            style.label = self.categories[-1]
        if style.icon == "":
            style.icon = "pin"

        return style


    def onActivated(self):
        children = self.listChildren()
        if len(children) == 1 and \
                isinstance(children[0], WikiWordTodoSearchNode) and \
                not self.treeCtrl.IsExpanded(self.wxItemId):
            children[0].onSelected()
            
#             if self.treeCtrl.IsExpanded(self.wxItemId):
#                 return True

        return super(TodoNode, self).onActivated()


    def listChildren(self):
        """
        Returns a sequence of Nodes for the children of this node.
        This is called before expanding the node
        """
        from functools import cmp_to_key
        
        wikiData = self.treeCtrl.pWiki.getWikiData()
        addedTodoSubCategories = []
        addedWords = []
        for (wikiWord, todoKey, todoValue) in wikiData.getTodos():
            # parse the todo for name and value
            wikiDocument = self.treeCtrl.pWiki.getWikiDocument()
#             langHelper = wx.GetApp().createWikiLanguageHelper(
#                     wikiDocument.getWikiDefaultWikiLanguage())
# 
#             node = langHelper.parseTodoEntry(todo, wikiDocument)
#             if node is not None:
                
            keyComponents = todoKey.split(".")  # TODO Language dependent: Remove
            entryCats = tuple(keyComponents + [todoValue])

            if len(entryCats) < len(self.categories):
                # Can't match
                continue
            elif (len(entryCats) == len(self.categories)) and \
                    (entryCats == self.categories):
                # Same category sequence -> wiki word node
                addedWords.append((wikiWord, todoKey, todoValue))
            elif len(entryCats) > len(self.categories) and \
                    entryCats[:len(self.categories)] == self.categories:
                # Subcategories -> category node

                nextSubCategory = entryCats[len(self.categories)]

                if nextSubCategory not in addedTodoSubCategories:
                    addedTodoSubCategories.append(nextSubCategory)

        collator = self.treeCtrl.pWiki.getCollator()
        
        def cmpAddWords(left, right):
            result = collator.strcoll(left[0], right[0])
            if result != 0:
                return result
            
            result = collator.strcoll(left[1], right[1])
            if result != 0:
                return result            
            
            return collator.strcoll(left[2], right[2])

        collator.sort(addedTodoSubCategories)

        addedWords.sort(key=cmp_to_key(cmpAddWords))

        result = []
        # First list real categories, then right sides, then words
        result += [TodoNode(self.treeCtrl, self, self.categories + (c,))
                for c in addedTodoSubCategories]

#         result += [TodoNode(self.treeCtrl, self, self.categories + (c,),
#                 isRightSide=True) for c in addedRightSides]

#         def createSearchNode(wt):
#             searchOp = SearchReplaceOperation()
#             searchOp.wildCard = "no"
#             searchOp.searchStr = wt[1]
#             return WikiWordSearchNode(self.treeCtrl, self, wt[0], searchOp=searchOp)
# 
#         result += [createSearchNode(wt) for wt in addedWords]

        result += [WikiWordTodoSearchNode(self.treeCtrl, self, wt[0], wt[1],
                wt[2]) for wt in addedWords]

        return result

    def nodeEquality(self, other):
        """
        Test for node equality
        """
        return AbstractNode.nodeEquality(self, other) and \
                self.categories == other.categories


class WikiWordTodoSearchNode(WikiWordRelabelNode):
    """
    Derived from WikiWordRelabelNode, specialized to locate and select
    in the active editor a particular todo item with given todoName and
    todoValue.
    """
    __slots__ = ("todoName", "todoValue")    
    
    def __init__(self, tree, parentNode, wikiWord, todoName, todoValue):
        super(WikiWordTodoSearchNode, self).__init__(tree, parentNode,
                wikiWord)

        self.todoName = todoName
        self.todoValue = todoValue


    def onSelected(self):
        super(WikiWordTodoSearchNode, self).onSelected()

        editor = self.treeCtrl.pWiki.getActiveEditor()
        try:
            pageAst = editor.getPageAst()

            wikiDocument = self.treeCtrl.pWiki.getWikiDocument()
            wikiPage = wikiDocument.getWikiPageNoError(self.wikiWord)
                
            todoNodes = wikiPage.extractTodoNodesFromPageAst(pageAst)
            for node in todoNodes:
                if self.todoName == node.key and \
                        self.todoValue == node.valueNode.getString():
                    editor.showSelectionByCharPos(node.pos, node.pos + node.strLength)
                    break
        except NoPageAstException:
            return



class AttrCategoryNode(AbstractNode):
    """
    Node representing a attribute category or subcategory
    """

    __slots__ = ("categories", "propIcon")

    def __init__(self, tree, parentNode, cats, attributeIcon="page"):
        AbstractNode.__init__(self, tree, parentNode)
        self.categories = cats
        self.propIcon = attributeIcon
        self.unifiedName = "helpernode/propcategory/" + \
                ".".join(self.categories)

    def getNodePresentation(self):   # TODO Retrieve prop icon here
        style = NodeStyle()
        globalAttrs = self.treeCtrl.pWiki.getWikiData().getGlobalAttributes()
        key = ".".join(self.categories)
        attributeIcon = globalAttrs.get("global.%s.icon" % (key), "page")

        style.icon = attributeIcon   # u"page"  # self.propIcon
        style.label = self.categories[-1]
        style.hasChildren = True
        return style

    def listChildren(self):
        wikiData = self.treeCtrl.pWiki.getWikiData()
        wikiDocument = self.treeCtrl.pWiki.getWikiDocument()

        result = []
        key = ".".join(self.categories + ("",))
        
        # Start with subcategories
        addedSubCategories = set()
        for name in wikiData.getAttributeNamesStartingWith(key):
            # Cut off uninteresting
            name = name[len(key):]

            nextcat = name.split(".", 1)[0]
            addedSubCategories.add(nextcat)
            
        subCats = list(addedSubCategories)
        self.treeCtrl.pWiki.getCollator().sort(subCats)
        result += [AttrCategoryNode(self.treeCtrl, self,
                self.categories + (c,)) for c in subCats]
                
        # Now the values:
        vals = wikiDocument.getDistinctAttributeValuesByKey(".".join(self.categories))
        self.treeCtrl.pWiki.getCollator().sort(vals)

        for v in vals:
            vn = AttrValueNode(self.treeCtrl, self, self.categories, v)
            if v == "":   # strip?
                # Replace empty value by its children
                result += vn.listChildren()
            else:
                result.append(vn)

#         result += map(lambda v: AttrValueNode(self.treeCtrl, self,
#                 self.categories, v), vals)
                
        # Replace a single "true" value node by its children
        if len(result) == 1 and isinstance(result[0], AttrValueNode) and \
                result[0].getValue().lower() == "true":
            result = result[0].listChildren()

        return result
        

    def onActivated(self):
        children = self.listChildren()
        if len(children) == 1 and \
                isinstance(children[0], WikiWordAttributeSearchNode) and \
                not self.treeCtrl.IsExpanded(self.wxItemId):
            children[0].onSelected()

#             if self.treeCtrl.IsExpanded(self.wxItemId):
#                 return True

        return super(AttrCategoryNode, self).onActivated()


    def nodeEquality(self, other):
        """
        Test for node equality
        """
        return AbstractNode.nodeEquality(self, other) and \
                self.categories == other.categories


class AttrValueNode(AbstractNode):
    """
    Node representing a attribute value. Children are WikiWordSearchNode's
    """
    
    __slots__ = ("categories", "value", "propIcon")
            
    def __init__(self, tree, parentNode, cats, value, attributeIcon="page"):
        AbstractNode.__init__(self, tree, parentNode)
        self.categories = cats
        self.value = value
        self.propIcon = attributeIcon
        self.unifiedName = "helpernode/propvalue/" + \
                ".".join(self.categories) + "/" + self.value

    def getValue(self):
        return self.value

    def getNodePresentation(self):
        style = NodeStyle()
        style.icon = "page"
        style.label = self.value
        style.hasChildren = True
        return style

    def listChildren(self):
        wikiDocument = self.treeCtrl.pWiki.getWikiDocument()
        result = []
        key = ".".join(self.categories)
#         words = wikiData.getWordsWithAttributeValue(key, self.value)
        words = list(set(w for w,k,v in wikiDocument.getAttributeTriples(
                None, key, self.value)))
        self.treeCtrl.pWiki.getCollator().sort(words)                
        return [WikiWordAttributeSearchNode(self.treeCtrl, self, w,
                key, self.value) for w in words]


    def onActivated(self):
        children = self.listChildren()
        if len(children) == 1 and \
                not self.treeCtrl.IsExpanded(self.wxItemId):
            children[0].onSelected()

        return super(AttrValueNode, self).onActivated()


    def nodeEquality(self, other):
        """
        Test for node equality
        """
        return AbstractNode.nodeEquality(self, other) and \
                self.categories == other.categories and \
                self.value == other.value


class WikiWordAttributeSearchNode(WikiWordRelabelNode):
    """
    Derived from WikiWordRelabelNode, specialized to locate and select
    in the active editor a particular attribute with given propName and
    propValue.
    """
    __slots__ = ("propName", "propValue")    
    
    def __init__(self, tree, parentNode, wikiWord, propName, propValue):
        super(WikiWordAttributeSearchNode, self).__init__(tree, parentNode,
                wikiWord)

        self.propName = propName
        self.propValue = propValue


    def onSelected(self):
        super(WikiWordAttributeSearchNode, self).onSelected()

        editor = self.treeCtrl.pWiki.getActiveEditor()
        try:
            pageAst = editor.getPageAst()

            wikiDocument = self.treeCtrl.pWiki.getWikiDocument()
            wikiPage = wikiDocument.getWikiPageNoError(self.wikiWord)
                
            attrNodes = wikiPage.extractAttributeNodesFromPageAst(pageAst)
            for node in attrNodes:
                if (self.propName, self.propValue) in node.attrs:
                    editor.showSelectionByCharPos(node.pos, node.pos + node.strLength)
                    break
        except NoPageAstException:
            return



class MainSearchesNode(AbstractNode):
    """
    Represents the "searches" node
    """
    __slots__ = ()
    
    def __init__(self, tree, parentNode):
        AbstractNode.__init__(self, tree, parentNode)
        self.unifiedName = "helpernode/main/searches"

    def getNodePresentationFast(self):
        style = NodeStyle()
        style.label = _("searches")
        style.icon = "lens"
        style.hasChildren = True
        return style
        
    def getNodePresentation(self):
        style = NodeStyle()
        style.label = _("searches")
        style.icon = "lens"
        style.hasChildren = self.isVisible()
        return style
        
    def isVisible(self):
#         return bool(self.treeCtrl.pWiki.getWikiData().getSavedSearchTitles())
        return bool(self.treeCtrl.pWiki.getWikiData()\
                .getDataBlockUnifNamesStartingWith("savedsearch/"))

    def listChildren(self):
        wikiData = self.treeCtrl.pWiki.getWikiData()

        unifNames = wikiData.getDataBlockUnifNamesStartingWith(
                "savedsearch/")

#         return map(lambda s: SearchNode(self.treeCtrl, self, s), searchTitles)
        return [SearchNode(self.treeCtrl, self, name[12:]) for name in unifNames]



    
class SearchNode(AbstractNode):
    """
    Represents a search below the "searches" node
    """
    
    __slots__ = ("searchTitle",)
            
    def __init__(self, tree, parentNode, searchTitle):
        AbstractNode.__init__(self, tree, parentNode)
        self.searchTitle = searchTitle
        self.unifiedName = "savedsearch/" + self.searchTitle

    def getNodePresentation(self):
        style = NodeStyle()
        style.icon = "lens"
        style.label = str(self.searchTitle)
        style.hasChildren = True
        return style

    def listChildren(self):
        pWiki = self.treeCtrl.pWiki
#         datablock = pWiki.getWikiData().getSearchDatablock(self.searchTitle)
        datablock = pWiki.getWikiData().retrieveDataBlock(
                "savedsearch/" + self.searchTitle)

        searchOp = SearchReplaceOperation()
        searchOp.setPackedSettings(datablock)
        searchOp.setTitle(self.searchTitle)
        searchOp.replaceOp = False
        words = pWiki.getWikiDocument().searchWiki(searchOp)
        self.treeCtrl.pWiki.getCollator().sort(words)

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
                self.searchTitle == other.searchTitle



class MainModifiedWithinNode(AbstractNode):
    """
    Represents the "modified-within" node
    """
    __slots__ = ()

    def __init__(self, tree, parentNode):
        AbstractNode.__init__(self, tree, parentNode)
        self.unifiedName = "helpernode/main/modifiedwithin"
    
    def getNodePresentation(self):
        style = NodeStyle()
        style.label = _("modified-within")
        style.icon = "date"
        style.hasChildren = True
        return style
        
    def listChildren(self):
        return [ModifiedWithinNode(self.treeCtrl, self, d) for d in [1, 3, 7, 30]]



class ModifiedWithinNode(AbstractNode):
    """
    Represents a time span below the "modified-within" node
    """
    
    __slots__ = ("daySpan",)
            
    def __init__(self, tree, parentNode, daySpan):
        AbstractNode.__init__(self, tree, parentNode)
        self.daySpan = daySpan
        self.unifiedName = "helpernode/modifiedwithin/days/" + \
                str(self.daySpan)

    def getNodePresentation(self):
        style = NodeStyle()
        style.icon = "date"
        if self.daySpan == 1:
            style.label = _("1 day")
        else:
            style.label = _("%i days") % self.daySpan
        style.hasChildren = True   #?
        return style

    def listChildren(self):
#         wikiData = self.treeCtrl.pWiki.getWikiData()
#         words = wikiData.getWikiPageNamesModifiedLastDays(self.daySpan)
        wikiDocument = self.treeCtrl.pWiki.getWikiDocument()
        words = wikiDocument.getWikiPageNamesModifiedLastDays(self.daySpan)
        self.treeCtrl.pWiki.getCollator().sort(words)

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
    
    def __init__(self, tree, parentNode):
        AbstractNode.__init__(self, tree, parentNode)
        self.unifiedName = "helpernode/main/parentless"

    def getNodePresentationFast(self):
        style = NodeStyle()
        style.label = _("parentless-nodes")
        style.icon = "link"
        style.hasChildren = True
        return style

    def getNodePresentation(self):
        style = NodeStyle()
        style.label = _("parentless-nodes")
        style.icon = "link"
        
        wikiData = self.treeCtrl.pWiki.getWikiData()
        style.hasChildren = self.isVisible()
        return style

    def isVisible(self):
        wikiData = self.treeCtrl.pWiki.getWikiData()
        return len(wikiData.getParentlessWikiWords()) > 0  # TODO Test if root is single element

    def listChildren(self):
        wikiData = self.treeCtrl.pWiki.getWikiData()
        words = wikiData.getParentlessWikiWords()
        self.treeCtrl.pWiki.getCollator().sort(words)
        
        return [WikiWordSearchNode(self.treeCtrl, self, w) for w in words
                if w != self.treeCtrl.pWiki.wikiName]



class MainUndefinedNode(AbstractNode):
    """
    Represents the "undefined" node
    """
    __slots__ = ()
    
    def __init__(self, tree, parentNode):
        AbstractNode.__init__(self, tree, parentNode)
        self.unifiedName = "helpernode/main/undefined"

    def getNodePresentationFast(self):
        style = NodeStyle()
        style.label = _("undefined-nodes")
        style.icon = "question"
        style.hasChildren = True
        return style

    def getNodePresentation(self):
        style = NodeStyle()
        style.label = _("undefined-nodes")
        style.icon = "question"
        style.hasChildren = self.isVisible()
        return style

    def isVisible(self):
        wikiData = self.treeCtrl.pWiki.getWikiData()
        return len(wikiData.getUndefinedWords()) > 0

    def listChildren(self):
        wikiData = self.treeCtrl.pWiki.getWikiData()
        words = wikiData.getUndefinedWords()
        self.treeCtrl.pWiki.getCollator().sort(words)

        return [WikiWordSearchNode(self.treeCtrl, self, w) for w in words
                if w != self.treeCtrl.pWiki.wikiName]


class MainFuncPagesNode(AbstractNode):
    """
    Represents the "Func pages" node
    """
    __slots__ = ()

    def __init__(self, tree, parentNode):
        AbstractNode.__init__(self, tree, parentNode)
        self.unifiedName = "helpernode/main/funcpages"

    def getNodePresentation(self):
        style = NodeStyle()
        style.label = _("Func. pages")
        style.icon = "cog"
        style.hasChildren = True
        return style
        
    def listChildren(self):
        return [
                FuncPageNode(self.treeCtrl, self, "global/TextBlocks"),
                FuncPageNode(self.treeCtrl, self, "wiki/TextBlocks"),
                FuncPageNode(self.treeCtrl, self, "global/PWL"),
                FuncPageNode(self.treeCtrl, self, "wiki/PWL"),
                FuncPageNode(self.treeCtrl, self, "global/CCBlacklist"),
                FuncPageNode(self.treeCtrl, self, "wiki/CCBlacklist"),
                FuncPageNode(self.treeCtrl, self, "global/NCCBlacklist"),
                FuncPageNode(self.treeCtrl, self, "wiki/NCCBlacklist"),
                FuncPageNode(self.treeCtrl, self, "global/FavoriteWikis")
                ]


class FuncPageNode(AbstractNode):
    """
    Node representing a functional page
    """
    
    __slots__ = ("funcTag", "label")
    
    def __init__(self, tree, parentNode, funcTag):
        AbstractNode.__init__(self, tree, parentNode)
        self.funcTag = funcTag
        self.label = DocPages.getHrNameForFuncTag(self.funcTag)
        self.unifiedName = "funcpage/" + self.funcTag

    def getNodePresentation(self):
        """
        return a NodeStyle object for the node
        """
        style = NodeStyle()
        style.label = self.label
        style.icon = "cog"
        style.hasChildren = False

        return style

    def onSelected(self):
        """
        React on selection
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


class WikiTreeCtrl(customtreectrl.CustomTreeCtrl):          # wxTreeCtrl):
    def __init__(self, pWiki, parent, ID, treeType):        
        # wxTreeCtrl.__init__(self, parent, ID, style=wxTR_HAS_BUTTONS)
        customtreectrl.CustomTreeCtrl.__init__(self, parent, ID,
                style=wx.TR_HAS_BUTTONS |
                customtreectrl.TR_HAS_VARIABLE_ROW_HEIGHT)

        self.pWiki = pWiki

        # Bytestring "main" for main tree or "views" for views tree
        # The setting affects the configuration entries used to set up tree
        self.treeType = treeType

#         self.SetBackgroundColour(wx.WHITE)

        self.SetSpacing(0)
        self.refreshGenerator = None  # Generator called in OnIdle
        self.refreshGeneratorLastCallTime = time.clock()  # Initial value
        self.refreshGeneratorLastCallMinDelay = 0.1
        self.refreshExecutor = Utilities.SingleThreadExecutor(1)
        self.refreshStartLock = False  # Disallows starting of refresh (mainly
                # during wiki rebuild
#        self.refreshCheckChildren = [] # List of nodes to check for new/deleted children
        self.sizeVisible = True
        # Descriptor pathes of all expanded nodes to remember or None
        # if functionality was switched off by user
        self.expandedNodePathes = StringPathSet()
        self.mainTreeMode = True  # Is this the main tree?
        
        self.onOptionsChanged(None)

        self.Bind(wx.EVT_TREE_ITEM_ACTIVATED, self.OnTreeItemActivated, id=ID)
        self.Bind(wx.EVT_RIGHT_DOWN, self.OnRightButtonDown)
        self.Bind(wx.EVT_RIGHT_UP, self.OnRightButtonUp)
        self.Bind(wx.EVT_MIDDLE_DOWN, self.OnMiddleButtonDown)
        self.Bind(wx.EVT_SIZE, self.OnSize)

        self._bindSelection()

#         self.Bind(wx.EVT_TREE_BEGIN_RDRAG, self.OnTreeBeginRDrag, id=ID)
        self.Bind(wx.EVT_TREE_ITEM_EXPANDING, self.OnTreeItemExpand, id=ID)
        self.Bind(wx.EVT_TREE_ITEM_COLLAPSED, self.OnTreeItemCollapse, id=ID)
        self.Bind(wx.EVT_TREE_BEGIN_DRAG, self.OnTreeBeginDrag, id=ID)

#        EVT_LEFT_DOWN(self, self.OnLeftDown)

        res = wx.xrc.XmlResource.Get()
        self.contextMenuWikiWords = res.LoadMenu("MenuTreectrlWikiWords")

        self.contextMenuWikiWords.AppendSeparator()

#         # Build icon menu (low resource version)
#         # Add only menu item for icon select dialog
#         menuID = wx.NewId()
#         self.contextMenuWikiWords.Append(menuID, _(u'Add icon attribute'),
#                 _(u'Open icon select dialog'))
#         self.Bind(wx.EVT_MENU, lambda evt: self.pWiki.showSelectIconDialog(), id=menuID)

        # Build icon menu
        # Build full submenu for icons
        iconsMenu, self.cmdIdToIconName = \
                AttributeHandling.buildIconsSubmenu(wx.GetApp().getIconCache())
        for cmi in list(self.cmdIdToIconName.keys()):
            self.Bind(wx.EVT_MENU, self.OnInsertIconAttribute, id=cmi)

        self.contextMenuWikiWords.AppendSubMenu(iconsMenu,
                _('Add icon attribute'))

        # Build submenu for colors
        colorsMenu, self.cmdIdToColorName = AttributeHandling.buildColorsSubmenu()
        for cmi in list(self.cmdIdToColorName.keys()):
            self.Bind(wx.EVT_MENU, self.OnInsertColorAttribute, id=cmi)

        self.contextMenuWikiWords.AppendSubMenu(colorsMenu,
                _('Add color attribute'))

        self.contextMenuNode = None  # Tree node for which a context menu was shown
        self.selectedNodeWhileContext = None # Tree node which was selected
                # before context menu was shown (when context menu is closed
                # selection jumps normally back to this node

        # TODO Let PersonalWikiFrame handle this 
        self.Bind(wx.EVT_MENU, lambda evt: self.pWiki.showWikiWordRenameDialog(
                self.GetItemData(self.contextMenuNode).getWikiWord()),
                id=GUI_ID.CMD_RENAME_THIS_WIKIWORD)
        self.Bind(wx.EVT_MENU, lambda evt: self.pWiki.showWikiWordDeleteDialog(
                self.GetItemData(self.contextMenuNode).getWikiWord()),
                id=GUI_ID.CMD_DELETE_THIS_WIKIWORD)
        self.Bind(wx.EVT_MENU, lambda evt: self.pWiki.insertAttribute(
                "bookmarked", "true",
                self.GetItemData(self.contextMenuNode).getWikiWord()),
                id=GUI_ID.CMD_BOOKMARK_THIS_WIKIWORD)
        self.Bind(wx.EVT_MENU, lambda evt: self.pWiki.setWikiWordAsRoot(
                self.GetItemData(self.contextMenuNode).getWikiWord()),
                id=GUI_ID.CMD_SETASROOT_THIS_WIKIWORD)

        self.Bind(wx.EVT_MENU, lambda evt: self.collapseAll(),
                id=GUI_ID.CMD_COLLAPSE_TREE)

        self.Bind(wx.EVT_MENU, self.OnAppendWikiWord, id=GUI_ID.CMD_APPEND_WIKIWORD_FOR_THIS)
        self.Bind(wx.EVT_MENU, self.OnPrependWikiWord, id=GUI_ID.CMD_PREPEND_WIKIWORD_FOR_THIS)
        self.Bind(wx.EVT_MENU, self.OnActivateNewTabThis, id=GUI_ID.CMD_ACTIVATE_NEW_TAB_THIS)
        self.Bind(wx.EVT_MENU, self.OnCmdClipboardCopyUrlToThisWikiWord, id=GUI_ID.CMD_CLIPBOARD_COPY_URL_TO_THIS_WIKIWORD)
                


        # Register for pWiki events
        self.__sinkMc = wxKeyFunctionSink((
                ("loading wiki page", self.onLoadingCurrentWikiPage),
                ("closing current wiki", self.onClosingCurrentWiki),
                ("dropping current wiki", self.onClosingCurrentWiki),
                ("closed current wiki", self.onClosedCurrentWiki),
                ("changed current presenter",
                    self.onChangedPresenter)
        ), self.pWiki.getMiscEvent(), None)

        self.__sinkDocPagePresenter = wxKeyFunctionSink((
                ("loading wiki page", self.onLoadingCurrentWikiPage),
        ), self.pWiki.getCurrentPresenterProxyEvent(), self)

        self.__sinkWikiDoc = wxKeyFunctionSink((
                ("renamed wiki page", self.onRenamedWikiPage),
                ("deleted wiki page", self.onDeletedWikiPage),
                ("updated wiki page", self.onWikiPageUpdated),
                ("changed wiki configuration", self.onChangedWikiConfiguration),
                ("begin foreground update", self.onBeginForegroundUpdate),
                ("end foreground update", self.onEndForegroundUpdate),
        ), self.pWiki.getCurrentWikiDocumentProxyEvent(), self)

        self.__sinkApp = wxKeyFunctionSink((
                ("options changed", self.onOptionsChanged),
        ), wx.GetApp().getMiscEvent(), self)
        

        self.refreshExecutor.start()


    def _bindSelection(self):
        self.Bind(wx.EVT_TREE_SEL_CHANGED, self.OnTreeItemSelected)
#         self.Bind(wx.EVT_TREE_SEL_CHANGING, self.OnTreeItemSelChanging)

    def _unbindSelection(self):
#         self.Unbind(wx.EVT_TREE_SEL_CHANGING)
        self.Unbind(wx.EVT_TREE_SEL_CHANGED)
        
    def close(self):
        self.__sinkMc.disconnect()
        self.__sinkDocPagePresenter.disconnect()
        self.__sinkWikiDoc.disconnect()
        self.__sinkApp.disconnect()
        self.refreshExecutor.end(hardEnd=True)


    def collapse(self):
        """
        Called before rebuilding tree
        """
        rootNode = self.GetRootItem()
        self.CollapseAndReset(rootNode)

    def collapseAll(self):
        self.UnselectAll()
        rootNode = self.GetRootItem()
        rootOb = self.GetItemData(rootNode)
        if self.expandedNodePathes is not None:
            self.expandedNodePathes = StringPathSet()

        if not self.IsExpanded(rootNode):
            return

        self.Freeze()
        try:
            nodeId, cookie = self.GetFirstChild(rootNode)
            while nodeId is not None and nodeId.IsOk():
                if self.IsExpanded(nodeId):
                    self.CollapseAndReset(nodeId)

                nodeId, cookie = self.GetNextChild(rootNode, cookie)
        finally:
            self.Thaw()


    def expandRoot(self):
        """
        Called after rebuilding tree
        """
        rootNode = self.GetRootItem()
        self.Expand(rootNode)
#         self.selectedNodeWhileContext = rootNode
#         self._sendSelectionEvents(None, rootNode)

    def getHideUndefined(self):
        return self.pWiki.getConfig().getboolean("main", "hideundefined")


    def onChangedPresenter(self, miscevt):
        currentDpp = self.pWiki.getCurrentDocPagePresenter()
        if currentDpp is not None and self.getMainTreeMode() and \
                currentDpp.mainTreePositionHint:
            posHint = currentDpp.mainTreePositionHint
            currentDocPage = self.pWiki.getCurrentDocPage()
            if currentDocPage is not None and \
                    posHint[-1] == currentDocPage.getUnifiedPageName() and \
                    self.selectNodeByNodePath(self.GetRootItem(), posHint):
                return

        self.onLoadingCurrentWikiPage(miscevt)


    def onLoadingCurrentWikiPage(self, miscevt):
#         if miscevt.get("forceTreeSyncFromRoot", False):
#             self.buildTreeForWord(self.pWiki.getCurrentWikiWord(),
#                     selectNode=True)
#         else:
        currentNode = self.GetSelection()
        currentWikiWord = self.pWiki.getCurrentWikiWord()
        if currentWikiWord is None:
            self.Unselect()
            return

        currentDpp = self.pWiki.getCurrentDocPagePresenter()
        if currentNode is not None and currentNode.IsOk():
            node = self.GetItemData(currentNode)
            if node.representsWikiWord():                    
                if self.pWiki.getWikiDocument()\
                        .getWikiPageNameForLinkTermOrAsIs(node.getWikiWord()) ==\
                        currentWikiWord:  #  and currentWikiWord is not None:
                    return  # Is already on word -> nothing to do
#                 if currentWikiWord is None:
#                     self.Unselect()
#                     return
            if node.representsFamilyWikiWord():
                # If we know the motionType, tree selection can be moved smart
                motionType = miscevt.get("motionType", "random")
                if motionType == "parent":
                    parentnodeid = self.GetItemParent(currentNode)
                    if parentnodeid is not None and parentnodeid.IsOk():
                        parentnode = self.GetItemData(parentnodeid)
                        if parentnode.representsWikiWord() and \
                                (parentnode.getWikiWord() == \
                                self.pWiki.getCurrentWikiWord()):
                            self._unbindSelection()
                            self.SelectItem(parentnodeid)
                            self._bindSelection()
                            self._storeMainTreePositionHint(currentDpp,
                                    parentnodeid)
                            return
                elif motionType == "child":
                    if not self.IsExpanded(currentNode) and \
                            self.pWiki.getConfig().getboolean("main",
                            "tree_auto_follow"):
                        # Expand node to find child
                        self.Expand(currentNode)

                    if self.IsExpanded(currentNode):
                        child = self.findChildTreeNodeByWikiWord(currentNode,
                                self.pWiki.getCurrentWikiWord())
                        if child:
                            self._unbindSelection()
                            self.SelectItem(child)
                            self._bindSelection()
                            self._storeMainTreePositionHint(currentDpp, child)
                            return
#                         else:
#                             # TODO Better method if child doesn't even exist!
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

        if currentWikiWord is not None:
            # No cheap way to find current word in tree    
            if  self.pWiki.getConfig().getboolean("main", "tree_auto_follow") or \
                    miscevt.get("forceTreeSyncFromRoot", False):
                # Configuration or event says to use expensive way
                if not self.buildTreeForWord(self.pWiki.getCurrentWikiWord(),
                        selectNode=True, startFromRoot=True):
                    self.Unselect()
                return
            else:    
                # Can't find word -> remove selection
                self.Unselect()
                return

        self._storeMainTreePositionHint(currentDpp, self.GetSelection())


    def _storeMainTreePositionHint(self, docPagePresenter, nodeId):
        if not self.getMainTreeMode():
            return

        if docPagePresenter is None:
            return
        
        if nodeId is None or not nodeId.IsOk():
            docPagePresenter.mainTreePositionHint = None
            return

        node = self.GetItemData(nodeId)

        docPagePresenter.mainTreePositionHint = tuple(node.getNodePath())


    def selectNodeByNodePath(self, parentNodeId, nodePath):
        """
        Tries to find and select a node by the node path. The function does
        not expand nodes. Return True iff node was selected.
        """
        if nodePath is None or len(nodePath) == 0:
            return False
        

        node = self.GetItemData(parentNodeId)
        if node.getUnifiedName() != nodePath[0]:
            return False

        if len(nodePath) == 1:
            self.SelectItem(parentNodeId, send_events=False)
            self.EnsureVisible(parentNodeId)
            return True

        return self._selectNodeByNodePathRecurs(parentNodeId, nodePath[1:])


    def _selectNodeByNodePathRecurs(self, parentNodeId, nodePath):
        """
        Internal recursion helper for selectNodeByNodePath()
        """
        nodeUnifiedName = nodePath[0]

        nodeId, cookie = self.GetFirstChild(parentNodeId)
        while nodeId is not None and nodeId.IsOk():
            node = self.GetItemData(nodeId)
            if node.getUnifiedName() == nodeUnifiedName:
                if len(nodePath) == 1:
                    self.SelectItem(nodeId, send_events=False)
                    self.EnsureVisible(nodeId)
                    return True
                else:
                    return self._selectNodeByNodePathRecurs(nodeId, nodePath[1:])

            nodeId, cookie = self.GetNextChild(parentNodeId, cookie)

        return False


    def joinItemIdToNode(self, treeItemId, nodeObj):
        self.SetItemData(treeItemId, nodeObj)
        nodeObj.setWxItemId(treeItemId)

    def _startBackgroundRefresh(self):
        if self.refreshStartLock:
            return
            
        self.refreshGenerator = self._generatorRefreshNodeAndChildren(
                self.GetRootItem())
        self.Bind(wx.EVT_IDLE, self.OnIdle)

    def _stopBackgroundRefresh(self):
        self.Unbind(wx.EVT_IDLE)
        self.refreshGenerator = None
        

    def onEndForegroundUpdate(self, miscEvt):
        self.refreshStartLock = False
        self._startBackgroundRefresh()

    def onBeginForegroundUpdate(self, miscEvt):
        self._stopBackgroundRefresh()
        self.refreshStartLock = True




    def onWikiPageUpdated(self, miscevt):
        if not self.pWiki.getConfig().getboolean("main", "tree_update_after_save"):
            return

        self._startBackgroundRefresh()



    def onDeletedWikiPage(self, miscevt):  # TODO May be called multiple times if
                                           # multiple pages are deleted at once
        if not self.pWiki.getConfig().getboolean("main", "tree_update_after_save"):
            return

        self._startBackgroundRefresh()
        
    
    def _addExpandedNodesToPathSet(self, parentNodeId):
        """
        Called by onChangedWikiConfiguration (and by itself) if expanded nodes
        will now be recorded.
        The function does intentionally not record the (presumably) expanded 
        parent node as this parent node is the tree root which is assumed
        to be nearly always expanded.
        """
        nodeId, cookie = self.GetFirstChild(parentNodeId)
        while nodeId is not None and nodeId.IsOk():
            if self.IsExpanded(nodeId):
                node = self.GetItemData(nodeId)
                self.expandedNodePathes.add(tuple(node.getNodePath()))
                # Recursively handle childs of expanded node
                self._addExpandedNodesToPathSet(nodeId)
            nodeId, cookie = self.GetNextChild(parentNodeId, cookie)


    def onOptionsChanged(self, miscevt):
        config = self.pWiki.getConfig()

        coltuple = colorDescToRgbTuple(config.get("main", "tree_bg_color"))   

        if coltuple is None:
            coltuple = (255, 255, 255)

        self.SetBackgroundColour(wx.Colour(*coltuple))

        font = wx.SystemSettings.GetFont(wx.SYS_DEFAULT_GUI_FONT)
        # wx.Font()    # 1, wx.FONTFAMILY_DEFAULT, 
        font.SetNativeFontInfoUserDesc(config.get(
                "main", "tree_font_nativeDesc", ""))

        self.SetFont(font)
        
#         self.SetDefaultScrollVisiblePos("middle")

        self.Refresh()
        
        self.refreshGeneratorLastCallMinDelay = config.getfloat("main",
                "tree_updateGenerator_minDelay", 0.1)

        self._startBackgroundRefresh()



    def onChangedWikiConfiguration(self, miscevt):
        config = self.pWiki.getConfig()
        durat = config.getint(
                "main", "tree_expandedNodes_rememberDuration", 2)
        if durat == 0:
            # Don't remember nodes
            self.expandedNodePathes = None
        else:
            if self.expandedNodePathes is None:
                self.expandedNodePathes = StringPathSet()
                # Add curently expanded nodes to the set
                self._addExpandedNodesToPathSet(self.GetRootItem())

        if durat != 2:
            # Clear pathes stored in config
            config.set("main",
                    "tree_expandedNodes_descriptorPathes_" + self.treeType,
                    "")

    def _generatorRefreshNodeAndChildren(self, parentnodeid):
        """
        This is some sort of user-space thread (aka "fiber"). It is executed inside
        the main thread as most things are GUI operations which must
        be done in GUI thread.
        Some non-GUI things are handed over to the refreshExecutor which
        runs them in a different thread.
        """
        try:        
            nodeObj = self.GetItemData(parentnodeid)
        except Exception:
            return

        wikiData = self.pWiki.getWikiData()


        retObj = self.refreshExecutor.executeAsync(0, nodeObj.getNodePresentation)
        while retObj.state == 0:  # Dangerous!
            yield None
        nodeStyle = retObj.getReturn() 
#         nodeStyle = nodeObj.getNodePresentation()

        self.setNodePresentation(parentnodeid, nodeStyle)

        if not nodeStyle.hasChildren and self.expandedNodePathes is not None:
            self.expandedNodePathes.discardStartsWith(
                    tuple(nodeObj.getNodePath()))

        if not self.IsExpanded(parentnodeid):
            return

#         if nodeObj.representsWikiWord():
#             retObj = self.refreshExecutor.executeAsync(
#                     0, wikiData.getWikiPageNameForLinkTerm, nodeObj.getWikiWord())
#             while retObj.state == 0:  # Dangerous!
#                 yield None
#             wikiWord = retObj.getReturn() 

        if True:
            # We have to recreate the children of this node
            

            # This is time consuming
            retObj = self.refreshExecutor.executeAsync(0, nodeObj.listChildren)
            while retObj.state == 0:
                yield None
            children = retObj.getReturn() 

#             # This is time consuming
#             children = nodeObj.listChildren()
            
            if self.expandedNodePathes is not None:
                # Pathes for all children
                childrenPathes = set(tuple(c.getNodePath()) for c in children)
            
            oldChildNodeIds = []
            nodeid, cookie = self.GetFirstChild(parentnodeid)
            while nodeid is not None and nodeid.IsOk():
                oldChildNodeIds.append(nodeid)
                nodeid, cookie = self.GetNextChild(parentnodeid, cookie)
            
            idIdx = 0
            
#             nodeid, cookie = self.GetFirstChild(parentnodeid)
            del nodeid
            
            tci = 0  # Tree child index
            for c in children:
                if idIdx < len(oldChildNodeIds):
                    nodeid = oldChildNodeIds[idIdx]
                    nodeObj = self.GetItemData(nodeid)
                    if c.nodeEquality(nodeObj):
                        # Previous child matches new child -> normal refreshing
                        if self.IsExpanded(nodeid):
                            # Recursive generator call
                            for sg in self._generatorRefreshNodeAndChildren(nodeid):
                                yield sg
                        else:
                            retObj = self.refreshExecutor.executeAsync(0,
                                    nodeObj.getNodePresentation)
                            while retObj.state == 0:
                                yield None
                            nodeStyle = retObj.getReturn()

                            self.setNodePresentation(nodeid, nodeStyle)

                            if not nodeStyle.hasChildren and \
                                    self.expandedNodePathes is not None:
                                self.expandedNodePathes.discardStartsWith(
                                        tuple(nodeObj.getNodePath()))

                            yield None
                            
                        
                        idIdx += 1
                        tci += 1                           

                    else:
                        # Old and new don't match -> Insert new child
                        newnodeid = self.InsertItemBefore(parentnodeid, tci, "")
                        tci += 1
                        self.joinItemIdToNode(newnodeid, c)

                        retObj = self.refreshExecutor.executeAsync(0,
                                c.getNodePresentation)
                        while retObj.state == 0:  # Dangerous!
                            yield None
                        nodeStyle = retObj.getReturn()
                        self.setNodePresentation(newnodeid, nodeStyle)
#                         self.setNodePresentation(newnodeid,
#                                 c.getNodePresentation())

                        yield None

                else:
                    # No more nodes in tree, but some in new children list
                    # -> append one to tree
                    newnodeid = self.AppendItem(parentnodeid, "")
                    self.joinItemIdToNode(newnodeid, c)
                    
                    retObj = self.refreshExecutor.executeAsync(0,
                            c.getNodePresentation)
                    while retObj.state == 0:
                        yield None
                    nodeStyle = retObj.getReturn()
                    self.setNodePresentation(newnodeid, nodeStyle)
#                     self.setNodePresentation(newnodeid,
#                             c.getNodePresentation())


            # End of loop, no more new children, remove possible remaining
            # children in tree

            while idIdx < len(oldChildNodeIds):
                nodeid = oldChildNodeIds[idIdx]
                # Trying to prevent failure of GetNextChild() after deletion
                delnodeid = nodeid                
                idIdx += 1

                if self.expandedNodePathes is not None:
                    nodeObj = self.GetItemData(nodeid)
                    nodePath = tuple(nodeObj.getNodePath())
                    if nodePath not in childrenPathes:
                        self.expandedNodePathes.discardStartsWith(nodePath)

                self.Delete(delnodeid)
                yield None

        else:
            # Recreation of children not necessary -> simple refresh
            nodeid, cookie = self.GetFirstChild(parentnodeid)
            while nodeid is not None and nodeid.IsOk():
                if self.IsExpanded(nodeid):
                    # Recursive generator call
                    for sg in self._generatorRefreshNodeAndChildren(nodeid):
                        yield sg
                else:
                    nodeObj = self.GetItemData(nodeid)
                    retObj = self.refreshExecutor.executeAsync(0,
                            nodeObj.getNodePresentation)
                    while retObj.state == 0:  # Dangerous!
                        yield None
                    nodeStyle = retObj.getReturn()
                    self.setNodePresentation(nodeid, nodeStyle)
#                     self.setNodePresentation(nodeid, nodeObj.getNodePresentation())

                    yield None

                nodeid, cookie = self.GetNextChild(parentnodeid, cookie)
            
        return


    def onRenamedWikiPage(self, miscevt):
        rootItem = self.GetItemData(self.GetRootItem())
        if isinstance(rootItem, WikiWordNode) and \
                miscevt.get("wikiPage").getWikiWord() == \
                rootItem.getWikiWord():

            # Renamed word was root of the tree, so set it as root again
            self.pWiki.setWikiWordAsRoot(miscevt.get("newWord"))
            
            # Updating the tree isn't necessary then, so return
            return

        if not self.pWiki.getConfig().getboolean("main", "tree_update_after_save"):
            return

        self._startBackgroundRefresh()
#         self.collapse()   # TODO?


    def onClosingCurrentWiki(self, miscevt):
        config = self.pWiki.getConfig()

        durat = config.getint("main", "tree_expandedNodes_rememberDuration", 2)
        if durat == 2 and self.expandedNodePathes is not None:
            pathStrs = []
            for path in self.expandedNodePathes:
                pathStrs.append(",".join(
                        [escapeForIni(item, ";,") for item in path]))
            
            remString = ";".join(pathStrs)

            config.set("main",
                    "tree_expandedNodes_descriptorPathes_" + self.treeType,
                    remString)
        else:
            config.set("main",
                    "tree_expandedNodes_descriptorPathes_" + self.treeType,
                    "")

        self._stopBackgroundRefresh()
        self.refreshExecutor.end(hardEnd=True)
        self.refreshExecutor.start()


    def onClosedCurrentWiki(self, miscevt):
#         self.refreshExecutor.end(hardEnd=True)
        self._stopBackgroundRefresh()
        if self.expandedNodePathes is not None:
            self.expandedNodePathes = StringPathSet()

    def OnInsertIconAttribute(self, evt):
        self.pWiki.insertAttribute("icon", self.cmdIdToIconName[evt.GetId()],
                self.GetItemData(self.contextMenuNode).getWikiWord())

    def OnInsertColorAttribute(self, evt):
        self.pWiki.insertAttribute("color", self.cmdIdToColorName[evt.GetId()],
                self.GetItemData(self.contextMenuNode).getWikiWord())

#         self.activeEditor.AppendText(u"\n\n[%s=%s]" % (name, value))

    def OnAppendWikiWord(self, evt):
        toWikiWord = SelectWikiWordDialog.runModal(self.pWiki, self.pWiki, -1,
                title=_("Append Wiki Word"))

        if toWikiWord is not None:
            parentWord = self.GetItemData(self.contextMenuNode).getWikiWord()
            page = self.pWiki.getWikiDocument().getWikiPageNoError(parentWord)
            
            langHelper = wx.GetApp().createWikiLanguageHelper(
                    page.getWikiLanguageName())

            page.appendLiveText("\n" +
                    langHelper.createAbsoluteLinksFromWikiWords((toWikiWord,)))


    def OnPrependWikiWord(self, evt):
        toWikiWord = SelectWikiWordDialog.runModal(self.pWiki, self.pWiki, -1,
                title=_("Prepend Wiki Word"))

        if toWikiWord is not None:
            parentWord = self.GetItemData(self.contextMenuNode).getWikiWord()
            page = self.pWiki.getWikiDocument().getWikiPageNoError(parentWord)
            
            langHelper = wx.GetApp().createWikiLanguageHelper(
                    page.getWikiLanguageName())
                    
            text = page.getLiveText()
            page.replaceLiveText(
                    langHelper.createAbsoluteLinksFromWikiWords((toWikiWord,)) +
                    "\n" + text)


    def OnActivateNewTabThis(self, evt):
        wikiWord = self.GetItemData(self.contextMenuNode).getWikiWord()
        presenter = self.pWiki.createNewDocPagePresenterTab()
        presenter.openWikiPage(wikiWord)
        presenter.getMainControl().getMainAreaPanel().\
                        showPresenter(presenter)
        self.selectedNodeWhileContext = self.contextMenuNode
        self.SelectItem(self.contextMenuNode)
        if self.pWiki.getConfig().getboolean("main", "tree_autohide", False):
            # Auto-hide tree
            self.pWiki.setShowTreeControl(False)


    def OnCmdClipboardCopyUrlToThisWikiWord(self, evt):
        wikiWord = self.GetItemData(self.contextMenuNode).getWikiWord()
        path = self.pWiki.getWikiDocument().getWikiConfigPath()
        copyTextToClipboard(pathWordAndAnchorToWikiUrl(path, wikiWord, None))


    def buildTreeForWord(self, wikiWord, selectNode=False, doexpand=False,
            startFromRoot=False):
        """
        First tries to find a path from wikiWord to the currently selected node.
        If nothing is found, searches for a path from wikiWord to the root.
        Expands the tree out and returns True if a path is found 
        """
#         if selectNode:
#             doexpand = True


        wikiData = self.pWiki.getWikiData()
        wikiDoc = self.pWiki.getWikiDocument()

        # If parent is defined use that as default node
        if not startFromRoot:
            currentNode = self.GetSelection()    # self.GetRootItem()
        else:
            currentNode = None
        
        crumbs = None

        # First check if word has canonical parent
        canonical_parent = self.pWiki.getWikiDocument().getAttributeTriples(
                wikiWord, "parent", None)

        if canonical_parent:
            parentWikiWord = wikiDoc.getWikiPageNameForLinkCore(
                    canonical_parent[0][2], wikiWord)
        else:
            parentWikiWord = None

        if parentWikiWord:
            loop = True

            parent_list = []

#             parentWikiWord = canonical_parent[0][2]
            parents = self.pWiki.getWikiData().getParentRelationships(wikiWord)

            newWikiWord = wikiWord

            # Follow canonical parents as far as they are defined
            # Care must be taken to check that the  parent exists in 
            # the tree (i.e. has a parent itself) and that it has not 
            # already been added to the list (to prevent infinite loops)
            while parentWikiWord and parentWikiWord not in parent_list \
                    and parentWikiWord in parents:
                parent_list.append(newWikiWord)
                newWikiWord = parentWikiWord
                canonical_parent = self.pWiki.getWikiDocument()\
                        .getAttributeTriples(newWikiWord, "parent", None)

                if canonical_parent:
                    parentWikiWord = wikiDoc.getWikiPageNameForLinkCore(
                            canonical_parent[0][2], wikiWord)
                else:
                    parentWikiWord = None

                if parentWikiWord:
                    parents = self.pWiki.getWikiData()\
                                .getParentRelationships(newWikiWord)
                else:
                    break

            # Find path between root node and first node without defined
            # canonical parent, if no path found try the next parent and
            # so on.
            for i in parent_list:
                rootNode = self.GetRootItem()
                if rootNode is not None and rootNode.IsOk() and \
                        self.GetItemData(rootNode).representsFamilyWikiWord():
                    rootWikiWord = self.GetItemData(rootNode).getWikiWord()
                    crumbs = wikiData.findBestPathFromWordToWord(
                                        parent_list.pop(), rootWikiWord)

                    # If parent path cannot be found resort to default path
                    if crumbs:
                        # When expanding crumbs below currentNode is used as first node
                        currentNode = rootNode

                        if parent_list:
                            parent_list.reverse()

                            # Prevent unnecessary tree node expansion
                            if parent_list[-1] in crumbs:
                                crumbs = crumbs[:crumbs.index(parent_list[-1])+1]
                            else:
                    # crumbs consists of two parts
                    # part 1 - path between root node and first node in chain
                    #           without a canonical parent
                    # part 2 - node path as defined by canonical parents 
                                crumbs.extend(parent_list)
                        break

        elif currentNode is not None and currentNode.IsOk() and \
                self.GetItemData(currentNode).representsFamilyWikiWord():
            # check for path from wikiWord to currently selected tree node            
            currentWikiWord = self.GetItemData(currentNode).getWikiWord() #self.getNodeValue(currentNode)
            crumbs = wikiData.findBestPathFromWordToWord(wikiWord, currentWikiWord)
           
            if crumbs and self.pWiki.getConfig().getboolean("main",
                    "tree_no_cycles"):
                ancestors = self.GetItemData(currentNode).getAncestors()
                # If an ancestor of the current node is in the crumbs, the
                # crumbs path is invalid because it contains a cycle
                for c in crumbs:
                    if c in ancestors:
                        crumbs = None
                        break

        
        # if a path is not found try to get a path to the root node
        if not crumbs:
            currentNode = self.GetRootItem()
            if currentNode is not None and currentNode.IsOk() and \
                    self.GetItemData(currentNode).representsFamilyWikiWord():
                currentWikiWord = self.GetItemData(currentNode).getWikiWord()
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
                except Exception as e:
                    sys.stderr.write("error expanding tree node: %s\n" % e)


            # set the ItemHasChildren marker if the node is not expanded
            if currentNode:
                currentWikiWord = self.GetItemData(currentNode).getWikiWord()

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
                    self._unbindSelection()
                    self.SelectItem(currentNode, send_events=False)
                    currentDpp = self.pWiki.getCurrentDocPagePresenter()
                    self._storeMainTreePositionHint(currentDpp, currentNode)
                    self.EnsureVisible(currentNode)
                    self._bindSelection()
                
                return True
        
        return False    

    def findChildTreeNodeByWikiWord(self, fromNode, findWord):
        (child, cookie) = self.GetFirstChild(fromNode)    # , 0
        while child:
            nodeobj = self.GetItemData(child)
#             if nodeobj.representsFamilyWikiWord() and nodeobj.getWikiWord() == findWord:
            if nodeobj.representsFamilyWikiWord() and \
                    self.pWiki.getWikiDocument().getWikiPageNameForLinkTerm(
                    nodeobj.getWikiWord()) == findWord:
                return child
            
            (child, cookie) = self.GetNextChild(fromNode, cookie)
        return None


    def setRootByWord(self, rootword):
        self.setRootByUnifiedName("wikipage/" + rootword)

    def getMainTreeMode(self):
        return self.mainTreeMode

    def setViewsAsRoot(self):
        self.mainTreeMode = False
        self.setRootByUnifiedName("helpernode/main/view")


    def setRootByUnifiedName(self, unifName):
        """
        Clear the tree and use a node described by unifName as root of the tree.
        """
        self.DeleteAllItems()
        # add the root node to the tree
        nodeobj = self.createNodeObjectByUnifiedName(unifName)
        nodeobj.setRoot(True)
        root = self.AddRoot("")
        self.joinItemIdToNode(root, nodeobj)
        
        nodeStyle = nodeobj.getNodePresentationFast()
        if nodeStyle is None:
            nodeStyle = nodeobj.getNodePresentation()
        else:
            self._startBackgroundRefresh()

        self.setNodePresentation(root, nodeStyle)
        if self.expandedNodePathes is not None:
            self.expandedNodePathes = StringPathSet()

        self.SelectItem(root)

        
    def createNodeObjectByUnifiedName(self, unifName):
        # TODO Support all node types
        if unifName.startswith("wikipage/"):
            return WikiWordNode(self, None, unifName[9:])
        elif unifName == "helpernode/main/view":
            return MainViewNode(self, None)
        else:
            raise InternalError(
                    "createNodeObjectByUnifiedName called with invalid parameter")


    def readExpandedNodesFromConfig(self):
        """
        Called by PersonalWikiFrame during opening of a wiki.
        Checks first if nodes should be read from there.
        """
        config = self.pWiki.getConfig()
        
        durat = config.getint("main", "tree_expandedNodes_rememberDuration", 2)
        if durat == 0:
            # Don't remember nodes
            self.expandedNodePathes = None
        elif durat == 2:
            pathSet = StringPathSet()
            remString = config.get("main",
                    "tree_expandedNodes_descriptorPathes_" + self.treeType,
                    "")
            
            # remString consists of node pathes delimited by ';'
            # the items of the paath are delimited by , and are
            # ini-escaped
            
            if not remString == "":
                for pathStr in remString.split(";"):
                    path = tuple(unescapeForIni(item)
                            for item in pathStr.split(","))
                    pathSet.add(path)
                    
            self.expandedNodePathes = pathSet
        else:  # durat == 1
            # Remember only during session
            self.expandedNodePathes = StringPathSet()


    def setNodeImage(self, node, image):
        try:
            index = self.pWiki.lookupIconIndex(image)
            if index == -1:
                index = self.pWiki.lookupIconIndex("page")
            ## if icon:
                ## self.SetItemImage(node, index, wx.TreeItemIcon_Selected)
                ## self.SetItemImage(node, index, wx.TreeItemIcon_Expanded)
                ## self.SetItemImage(node, index, wx.TreeItemIcon_SelectedExpanded)
            self.SetItemImage(node, index, wx.TreeItemIcon_Normal)
        except:
            try:
                self.SetItemImage(node, 0, wx.TreeItemIcon_Normal)
            except:
                pass    


    def setNodeColor(self, node, color):
        if color != "null":
            coltuple = colorDescToRgbTuple(color)
            if coltuple is not None:            
                self.SetItemTextColour(node, wx.Colour(*coltuple))
                return
                
        self.SetItemTextColour(node, wx.NullColour)


    def setNodeBgcolor(self, node, color):
        if color != "null":
            coltuple = colorDescToRgbTuple(color)
            if coltuple is not None:            
                self.SetItemBackgroundColour(node, wx.Colour(*coltuple))
                return
                
        self.SetItemBackgroundColour(node, wx.NullColour)


    def setNodePresentation(self, node, style):
        self.SetItemText(node, style.label, recalcSize=False)
        self.setNodeImage(node, style.icon)
        self.SetItemBold(node, strToBool(style.bold, False))
        self.setNodeColor(node, style.color)
        self.setNodeBgcolor(node, style.bgcolor)
        self.SetItemHasChildren(node, style.hasChildren)
        
    
    def _sendSelectionEvents(self, oldNode, newNode):
        # Simulate selection events
        event = customtreectrl.TreeEvent(wx.wxEVT_COMMAND_TREE_SEL_CHANGING,
                self.GetId())
        event.SetItem(newNode)
        event.SetOldItem(oldNode)
        event.SetEventObject(self)
        self.GetEventHandler().ProcessEvent(event)
        event.SetEventType(wx.wxEVT_COMMAND_TREE_SEL_CHANGED)
        self.GetEventHandler().ProcessEvent(event)


    def OnTreeItemSelected(self, event):
        item = event.GetItem()
        if item is not None and item.IsOk():
            node = self.GetItemData(item)
            node.onSelected()

            self._storeMainTreePositionHint(
                    self.pWiki.getCurrentDocPagePresenter(), item)

            if self.pWiki.getConfig().getboolean("main", "tree_autohide", False):
                # Auto-hide tree
                self.pWiki.setShowTreeControl(False)

        # Is said to fix a selection redraw problem
        self.Refresh()


    def OnTreeItemActivated(self, event):
        item = event.GetItem()
        if item is not None and item.IsOk():
            node = self.GetItemData(item)
            if not node.onActivated():
                event.Skip()

        # Is said to fix a selection redraw problem
        self.Refresh()


#     def OnTreeItemSelChanging(self, evt):
#         pass


#     def OnTreeBeginRDrag(self, evt):
#         pass

    def OnTreeItemExpand(self, event):
        ## _prof.start()
        item = event.GetItem()
        if self.IsExpanded(item):   # TODO Check if a good idea
            return

        itemobj = self.GetItemData(item)
        if self.expandedNodePathes is not None:
            self.expandedNodePathes.add(tuple(itemobj.getNodePath()))

        refreshNeeded = False

        childnodes = itemobj.listChildrenFast()
        if childnodes is None:
            childnodes = itemobj.listChildren()
        else:
            refreshNeeded = True

        self.Freeze()
        try:
            for ch in childnodes:
                newit = self.AppendItem(item, "")
                self.joinItemIdToNode(newit, ch)
                
                nodeStyle = ch.getNodePresentationFast()
                if nodeStyle is None:
                    nodeStyle = ch.getNodePresentation()
                else:
                    refreshNeeded = True

                self.setNodePresentation(newit, nodeStyle)
                
                if self.expandedNodePathes is not None:
                    if nodeStyle.hasChildren:
                        if tuple(ch.getNodePath()) in self.expandedNodePathes:
                            self.Expand(newit)
#                     else:
#                         self.expandedNodePathes.discardStartsWith(
#                                 tuple(ch.getNodePath()))
        finally:
            self.Thaw()
        
        if refreshNeeded:
            self._startBackgroundRefresh()

        ## _prof.stop()


    def OnTreeItemCollapse(self, event):
        itemobj = self.GetItemData(event.GetItem())

        if self.expandedNodePathes is not None:
            self.expandedNodePathes.discard(tuple(itemobj.getNodePath()))
        self.DeleteChildren(event.GetItem())
        # Is said to fix a selection redraw problem
        self.Refresh()


    def OnTreeBeginDrag(self, event):
        item = event.GetItem()   
        if item is None or not item.IsOk():
            event.Veto()
            return

        langHelper = wx.GetApp().createWikiLanguageHelper(
                self.pWiki.getWikiDocument().getWikiDefaultWikiLanguage())

        itemobj = self.GetItemData(item)
        if isinstance(itemobj, WikiWordNode):
            textDataOb = textToDataObject(
                    langHelper.createAbsoluteLinksFromWikiWords(
                    (itemobj.getWikiWord(),)))

            wikiWordDataOb = wx.DataObjectSimple(wx.DataFormat(
                    "application/x-wikidpad-unifiedname"))
            wikiWordDataOb.SetData(
                    ("wikipage/" + itemobj.getWikiWord()).encode("utf-8"))

            dataOb = wx.DataObjectComposite()
            dataOb.Add(textDataOb, True)
            dataOb.Add(wikiWordDataOb)

            dropsource = wx.DropSource(self)
            dropsource.SetData(dataOb)
            dropsource.DoDragDrop(wx.Drag_AllowMove)


#     def OnLeftDown(self, event):
# #         dataOb = textToDataObject(u"Test")
#         dataOb = wx.TextDataObject("Test")
#         dropsource = wx.DropSource(self)
#         dropsource.SetData(dataOb)
#         dropsource.DoDragDrop(wxDrag_AllowMove)



    def OnRightButtonDown(self, event):
        pass


    def OnRightButtonUp(self, event):
        selnode = self.GetSelection()
        
        clickPos = event.GetPosition()
        if clickPos == wx.DefaultPosition:
            # E.g. context menu key was pressed on Windows keyboard
            item = selnode
        else:
            item, flags = self.HitTest(clickPos)

        if item is None or not item.IsOk():
            return

        self.contextMenuNode = item

        menu = wx.Menu()
        menu = self.GetItemData(item).prepareContextMenu(menu)

        if menu is not None:
            self.selectedNodeWhileContext = selnode
            
            self._unbindSelection()
            self.SelectItem(item)
            self._bindSelection()

            self.PopupMenuXY(menu, event.GetX(), event.GetY())

            selnode = self.selectedNodeWhileContext

            self._unbindSelection()
            if selnode is None:
                self.Unselect()
            else:
                self.SelectItem(selnode, expand_if_necessary=False)
            self._bindSelection()

            newsel = self.GetSelection()
            if selnode != newsel:
                self._sendSelectionEvents(selnode, newsel)
        else:
            self.contextMenuNode = None


    def OnMiddleButtonDown(self, event):
        selnode = self.GetSelection()
        
        clickPos = event.GetPosition()
        if clickPos == wx.DefaultPosition:
            item = selnode
        else:
            item, flags = self.HitTest(clickPos)

        if item is None or not item.IsOk():
            return

        nodeObj = self.GetItemData(item)

        if event.ControlDown():
            configCode = self.pWiki.getConfig().getint("main",
                    "mouse_middleButton_withCtrl")
        else:
            configCode = self.pWiki.getConfig().getint("main",
                    "mouse_middleButton_withoutCtrl")
                    
        tabMode = MIDDLE_MOUSE_CONFIG_TO_TABMODE[configCode]

        if (tabMode & 2) and isinstance(nodeObj, WikiWordNode):
#             self.pWiki.activateWikiWord(nodeObj.getWikiWord(), tabMode)
            
            if self.pWiki.activatePageByUnifiedName(
                    "wikipage/" + nodeObj.getWikiWord(), tabMode) is None:
                return
            
            if not (tabMode & 1) and self.pWiki.getConfig().getboolean("main",
                    "tree_autohide", False):
                # Not opened in background -> auto-hide tree if option selected
                self.pWiki.setShowTreeControl(False)
        else:
            self.SelectItem(item)

#             # Create new tab
#             presenter = self.pWiki.createNewDocPagePresenterTab()
#             presenter.openWikiPage(nodeObj.getWikiWord())
#             if configCode == 0:
#                 # New tab in foreground
#                 presenter.getMainControl().getMainAreaPanel().\
#                                 showDocPagePresenter(presenter)
# 
#         elif configCode == 2:
#             self.SelectItem(item)


    def OnIdle(self, event):
        gen = self.refreshGenerator
        if gen is not None:
            cl = time.clock()
            if cl < self.refreshGeneratorLastCallTime:
                # May happen under special circumstances (e.g. after hibernation)
                self.refreshGeneratorLastCallTime = cl
            elif (cl - self.refreshGeneratorLastCallTime) < self.refreshGeneratorLastCallMinDelay:
                event.Skip()
                return

            try:
                next(gen)
                # Set time after generator run, so time needed by generator
                # itself doesn't count
                self.refreshGeneratorLastCallTime = time.clock()
            except StopIteration:
                if self.refreshGenerator == gen:
                    self.refreshGenerator = None
                    self.Unbind(wx.EVT_IDLE)
        else:
            event.Skip()
            self.Unbind(wx.EVT_IDLE)


    def isVisibleEffect(self):
        """
        Is this control effectively visible?
        """
        return self.sizeVisible


    def handleVisibilityChange(self):
        """
        Only call after isVisibleEffect() really changed its value.
        The new value is taken from isVisibleEffect(), the old is assumed
        to be the opposite.
        """
        if not self.isVisibleEffect():
            if wx.Window.FindFocus() is self:
                self.pWiki.getMainAreaPanel().SetFocus()


    def OnSize(self, evt):
        evt.Skip()
        oldVisible = self.isVisibleEffect()
        size = evt.GetSize()
        self.sizeVisible = size.GetHeight() >= 5 and size.GetWidth() >= 5

        if oldVisible != self.isVisibleEffect():
            self.handleVisibilityChange()





# _CONTEXT_MENU_WIKIWORD = \
# u"""
# Activate New Tab;CMD_ACTIVATE_NEW_TAB_THIS
# Rename;CMD_RENAME_THIS_WIKIWORD
# Delete;CMD_DELETE_THIS_WIKIWORD
# Bookmark;CMD_BOOKMARK_THIS_WIKIWORD
# Set As Root;CMD_SETASROOT_THIS_WIKIWORD
# Append wiki word;CMD_APPEND_WIKIWORD_FOR_THIS
# Prepend wiki word;CMD_PREPEND_WIKIWORD_FOR_THIS
# Copy URL to clipboard;CMD_CLIPBOARD_COPY_URL_TO_THIS_WIKIWORD
# """
# 
# 
# # Entries to support i18n of context menus
# 
# N_(u"Activate New Tab")
# N_(u"Rename")
# N_(u"Delete")
# N_(u"Bookmark")
# N_(u"Set As Root")
# N_(u"Append wiki word")
# N_(u"Prepend wiki word")
# N_(u"Copy URL to clipboard")



