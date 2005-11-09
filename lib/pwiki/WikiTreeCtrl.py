import sys # , hotshot

## _prof = hotshot.Profile("hotshot.prf")

from wxPython.wx import *
from wxPython.stc import *
import wxPython.xrc as xrc

from wxHelper import GUI_ID
from MiscEvent import KeyFunctionSink

from WikiExceptions import WikiWordNotFoundException
import WikiFormatting

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
            "treeCtrl")
            
    def __init__(self, tree):
        self.treeCtrl = tree
    
    def setRoot(self, flag = True):
        """
        Sets if this node is a logical root of the tree or not
        (currently the physical root is the one and only logical root)
        """
        if flag: raise Error   # TODO Better exception

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
        


class WikiWordNode(AbstractNode):
    """
    Represents a wiki word
    """
    __slots__ = ("wikiPage", "flagChildren", "flagRoot")
    
    def __init__(self, tree, wikiPage, flagChildren = None):
        AbstractNode.__init__(self, tree)
        self.wikiPage = wikiPage
        self.flagChildren = flagChildren
        self.flagRoot = False        

    def getNodePresentation(self):
        return self._createNodePresentation(
                wikiWordToLabel(self.wikiPage.getWikiWord()))

    def setRoot(self, flag = True):
        self.flagRoot = flag

    def _createNodePresentation(self, baselabel):
        """
        Splitted to support derived class WikiWordSearchNode
        """
        style = NodeStyle()
        
        style.label = baselabel
        
        # Has children?
        if self.flagRoot:
            self.flagChildren = True # Has at least ScratchPad and Views
        elif self.flagChildren is None:
            # Inefficient, therefore self.flagChildren should be set
            self.flagChildren = len(self.wikiPage.getChildRelationships(      
                    existingonly=self.treeCtrl.getHideUndefined(), selfreference=False)) > 0
        
        style.hasChildren = self.flagChildren
        
        # apply custom properties to nodes
        wikiPage = self.wikiPage.getNonAliasPage() # Ensure we don't have an alias

        wikiWord = wikiPage.getWikiWord()

        # if this is the scratch pad set the icon and return
        if (wikiPage.wikiWord == "ScratchPad"):
            style.icon = "note"
            return style # ?????????
            
            
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
        for (key, values) in props.items():
            for val in values:
                for p in _SETTABLE_PROPS:
                    gPropVal = globalProps.get(u"global.%s.%s.%s" % (key, val, p))
                    if not gPropVal:
                        gPropVal = globalProps.get(u"global.%s.%s" % (key, p))
                    if gPropVal:
                        setattr(style, p, gPropVal)
                   
        # Overwrite with per page props, if available         
        # color. let user override global color
        if props.has_key("color"):
            style.color = props["color"][0]
            # self.setNodeColor(treeNode, props["color"][0])

        # icon. let user override global icon
        if props.has_key("icon"):
            style.icon = props["icon"][0]
            # self.setNodeImage(treeNode, props["icon"][0])
        if props.has_key("bold"):
            style.bold = props["bold"][0]

        return style


    def representsFamilyWikiWord(self):
        """
        True iff the node type is bound into its family of parent and children
        """
        return True

    def representsWikiWord(self):
        return True
       
        
    def listChildren(self):
        wikiData = self.treeCtrl.pWiki.wikiData
        relations = self.wikiPage.getChildRelationshipsAndHasChildren(
                existingonly=self.treeCtrl.getHideUndefined(),
                selfreference=False)
                
        # get the sort order for the children
        childSortOrder = self.wikiPage.getProperties().get(u'child_sort_order',
                (u"ascending",))[0]
            
        # TODO Automatically add ScratchPad
#         if treeNode == self.GetRootItem() and not "ScratchPad" in relations:
#             relations.append(("ScratchPad", None))

        # Apply sort order
        if childSortOrder != u"unsorted":
            if childSortOrder.startswith(u"desc"):
                relations.sort(removeBracketsAndSortDesc) # sort alphabetically
            else:
                relations.sort(removeBracketsAndSortAsc)
            
        relationData = []
        position = 1
        for relation, hasChildren in relations:
            relationPage = wikiData.getPageNoError(relation, toload=[""])
            relationData.append((relation, relationPage, position, hasChildren))
            position += 1
            
        # Sort again, using tree position and priority properties
        relationData.sort(relationSort)
        
        # if prev is None:
        ## Create everything new
        
        result = map(lambda rd: WikiWordNode(self.treeCtrl, rd[1], rd[3]),
                relationData)
                
        if self.flagRoot:
            result.append(MainViewNode(self.treeCtrl))
                
        return result
        
        
#         else:
#             tci = 0    # Index into prev
#             
#             result = []
#             # Delete/create/update tree nodes
#             for (relation, relationPage, position, hasChildren) in relationData:
#                 if (tci < len(prev)) and prev[tci].representsWikiWord() and \
#                         (prev[tci].wikiPage.getWikiWord() == relation):
#                             
#                     # This relation is already in the tree, so use existing node
#                     childTreeNode = prev[tci][0]
#                     tci += 1
#                 else:
#                     # No match, so create new node                
#                     childTreeNode = self.addTreeNode(treeNode, relation)
#                     
#                     # Update childTreeNode   # TODO: Also for existing children?
#                     try:
#                         self.updateTreeNode(relationPage, childTreeNode, hasChildren)
#                     except WikiWordNotFoundException, e:
#                         pass
#                     
#                     
#             # Remove old children
#             while (tci < len(prev)):
#                 self.Delete(prev[tci][0])
#                 tci += 1
#     
#             # add a "View" node to the root if it isn't already there
#             if treeNode == self.GetRootItem(): #wikiWord == self.pWiki.wikiName:
#                 if not self.findChildTreeNodeWithText(treeNode, "Views"):
#                     viewNode = self.addViewNode(treeNode, "Views", icon="orgchart")
#         return treeNode


    def onActivate(self):
        self.treeCtrl.pWiki.openWikiPage(self.wikiPage.getWikiWord())
        
    def getWikiPage(self):
        return self.wikiPage
        
    def getWikiWord(self):
        return self.wikiPage.getWikiWord()
        
    def getContextMenu(self):
        # Take context menu from tree   # TODO Better solution esp. for event handling
        return self.treeCtrl.contextMenuWikiWords



class WikiWordSearchNode(WikiWordNode):
    """
    Derived from WikiWordNode with ability to set label different from
    wikiWord and to set search information
    """
    __slots__ = ("newLabel", "searchInfo")    
    
    def __init__(self, tree, wikiPage, flagChildren = False, newLabel = None,
            searchInfo = None):
        WikiWordNode.__init__(self, tree, wikiPage, flagChildren)

        self.newLabel = newLabel
        self.searchInfo = searchInfo


    def getNodePresentation(self):
        if self.newLabel:
            return WikiWordNode._createNodePresentation(self, self.newLabel)
        else:
            return WikiWordNode.getNodePresentation(self)

    def onActivate(self):
        WikiWordNode.onActivate(self)
        if self.searchInfo:
            self.treeCtrl.pWiki.editor.executeSearch(self.searchInfo, 0)

    def representsFamilyWikiWord(self):
        """
        A search node is alone as child of a view subnode without
        its children or real parent
        """
        return False


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
        result += TodoNode(self.treeCtrl, ()).listChildren()
        # add property names   
        result += PropCategoryNode(self.treeCtrl, ()).listChildren()
        # add searches view
        node = MainSearchesNode(self.treeCtrl)
        if node.isVisible():
            result.append(node)
        # add last modified view
        result.append(MainModifiedWithinNode(self.treeCtrl))
        # add parentless view
        node = MainParentlessNode(self.treeCtrl)
        if node.isVisible():
            result.append(node)

        return result



class TodoNode(AbstractNode):
    """
    Especially for view nodes. An instance of a derived class
    is saved in funcData for such special nodes
    """
    
    __slots__ = ("categories",)
            
    def __init__(self, tree, cats):
        AbstractNode.__init__(self, tree)
        self.categories = cats

    def getNodePresentation(self):
        style = NodeStyle()
        style.icon = "pin"
        style.label = self.categories[-1]
        style.hasChildren = True
        return style
        
    def listChildren(self):
        """
        Returns a sequence of Nodes for the children of this node.
        This is called before expanding the node
        """
        wikiData = self.treeCtrl.pWiki.wikiData
        result = []
        addedTodoSubCategories = []
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
                result.append(WikiWordSearchNode(self.treeCtrl,
                        wikiData.getPage(wikiWord, toload=[""]),
                               # flagChildren = False, newLabel=match.group(3)
                        searchInfo=todo))
            elif entryCats[:len(self.categories)] == \
                    self.categories:
                # Subcategories -> category node

                nextSubCategory = entryCats[len(self.categories)]
                
                if nextSubCategory not in addedTodoSubCategories:
                    result.append(TodoNode(self.treeCtrl,
                            self.categories + (nextSubCategory,)))
                    addedTodoSubCategories.append(nextSubCategory)
        
        return result


class PropCategoryNode(AbstractNode):
    """
    Node representing a property category or subcategory
    """
    
    __slots__ = ("categories", "propIcon")
            
    def __init__(self, tree, cats, propertyIcon=u"page"):
        AbstractNode.__init__(self, tree)
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
        result += map(lambda c: PropCategoryNode(self.treeCtrl,
                self.categories + (c,)), subCats)
                
        # Now the values:
        vals = wikiData.getDistinctPropertyValues(u".".join(self.categories))
        vals.sort()
        result += map(lambda v: PropValueNode(self.treeCtrl,
                self.categories, v), vals)
                
        # Remove a single "true" value node by its children
        if len(result) == 1 and isinstance(result[0], PropValueNode) and \
                result[0].getValue().lower() == u"true":
            result = result[0].listChildren()

        return result
        

class PropValueNode(AbstractNode):
    """
    Node representing a property value. Children are WikiWordSearchNode s
    """
    
    __slots__ = ("categories", "value", "propIcon")
            
    def __init__(self, tree, cats, value, propertyIcon=u"page"):
        AbstractNode.__init__(self, tree)
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
        
        return map(lambda w: WikiWordSearchNode(self.treeCtrl,
                wikiData.getPage(w, toload=[""])), words)




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
        return self.treeCtrl.pWiki.wikiData.getSavedSearches()
        
    def listChildren(self):
        wikiData = self.treeCtrl.pWiki.wikiData
        
        searches = wikiData.getSavedSearches()
        return map(lambda s: SearchNode(self.treeCtrl, s), searches)


    
class SearchNode(AbstractNode):
    """
    Represents a search below the "searches" node
    """
    
    __slots__ = ("search",)
            
    def __init__(self, tree, search):
        AbstractNode.__init__(self, tree)
        self.search = search

    def getNodePresentation(self):
        style = NodeStyle()
        style.icon = u"lens"
        style.label = unicode(self.search)
        style.hasChildren = True
        return style

    def listChildren(self):
        wikiData = self.treeCtrl.pWiki.wikiData
        words = wikiData.search(self.search)
        
        return map(lambda w: WikiWordSearchNode(self.treeCtrl,
                wikiData.getPage(w, toload=[""]), searchInfo=self.search),
                words)


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
        return map(lambda d: ModifiedWithinNode(self.treeCtrl, d),
                [1, 3, 7, 30])

    
class ModifiedWithinNode(AbstractNode):
    """
    Represents a time span below the "modified-within" node
    """
    
    __slots__ = ("daySpan",)
            
    def __init__(self, tree, daySpan):
        AbstractNode.__init__(self, tree)
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
                
        return map(lambda w: WikiWordSearchNode(self.treeCtrl,
                wikiData.getPage(w, toload=[""])),
                words)


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
        return len(wikiData.getParentLessWords()) > 1  # TODO Test if root is single element
        
    def listChildren(self):
        wikiData = self.treeCtrl.pWiki.wikiData
        words = wikiData.getParentLessWords()
        
        words = filter(lambda w: w != self.treeCtrl.pWiki.wikiName, words)
                
        return map(lambda w: WikiWordSearchNode(self.treeCtrl,
                wikiData.getPage(w, toload=[""])),
                words)


# ----------------------------------------------------------------------




    
    

class WikiTreeCtrl(wxTreeCtrl):
    def __init__(self, pWiki, parent, ID):        
        wxTreeCtrl.__init__(self, parent, ID, style=wxTR_HAS_BUTTONS)
        self.pWiki = pWiki

        EVT_TREE_ITEM_ACTIVATED(self, ID, self.OnTreeItemActivated)
        EVT_TREE_SEL_CHANGED(self, ID, self.OnTreeItemActivated)
        EVT_TREE_ITEM_EXPANDING(self, ID, self.OnTreeItemExpand)
        EVT_TREE_ITEM_COLLAPSED(self, ID, self.OnTreeItemCollapse)
        EVT_RIGHT_DOWN(self, self.OnRightButtonDown)   # TODO Context menu
        
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

        # Register for pWiki events
        self.pWiki.getMiscEvent().addListener(KeyFunctionSink((
                ("loading current page", self.onLoadingCurrentWikiPage),
                ("updated current page cache", self.onUpdatedCurrentPageCache), # TODO is event fired somewhere?
                ("renamed page", self.onRenamedWikiPage)
        )))


    def collapse(self):
        rootNode = self.GetRootItem()
        self.CollapseAndReset(rootNode)
        
    def getHideUndefined(self):
        return self.pWiki.configuration.getboolean("main", "hideundefined")

    def onLoadingCurrentWikiPage(self, miscevt):
        if miscevt.get("forceTreeSyncFromRoot", False):
            self.buildTreeForWord(self.pWiki.getCurrentWikiWord(),
                    selectNode=True)
        else:
            currentNode = self.GetSelection()
            if currentNode.IsOk():
                node = self.GetPyData(currentNode)
                if node.representsWikiWord():                    
#                     if node.getWikiWord() == self.pWiki.getCurrentWikiWord():
#                         return # Is already on word -> nothing to do
                    if self.pWiki.wikiData.getAliasesWikiWord(node.getWikiWord()) ==\
                            self.pWiki.getCurrentWikiWord():
                        return
                if node.representsFamilyWikiWord():            
                    # If we know the motionType, tree selection can be moved smart
                    motionType = miscevt.get("motionType", "random")
                    if motionType == "parent":
                        self.SelectItem(self.GetItemParent(currentNode))
                        return
                    elif motionType == "child":
                        if self.IsExpanded(currentNode):
                            child = self.findChildTreeNodeByWikiWord(currentNode,
                                    self.pWiki.getCurrentWikiWord())
                            if child:
                                self.SelectItem(child)
                                return
                    
                # Can't find word -> remove selection
                self.Unselect()


    def onUpdatedCurrentPageCache(self, miscevt):
        self.buildTreeForWord(self.pWiki.getCurrentWikiWord())


    def onRenamedWikiPage(self, miscevt):
        self.collapse()   # TODO?




    def buildTreeForWord(self, wikiWord, selectNode=False, doexpand=False):
        """
        First tries to find a path from wikiWord to the currently selected node.
        If nothing is found, searches for a path from wikiWord to the root.
        Expands the tree out if a path is found.
        """
        
        if selectNode:
            doexpand = True

        wikiData = self.pWiki.wikiData
        currentNode = self.GetSelection()    # self.GetRootItem()
        crumbs = None
        
        if currentNode.IsOk() and self.GetPyData(currentNode).representsWikiWord():
            # check for path from wikiWord to currently selected tree node            
            currentWikiWord = self.GetPyData(currentNode).getWikiWord() #self.getNodeValue(currentNode)
            crumbs = wikiData.findBestPathFromWordToWord(wikiWord, currentWikiWord)
        
        # if a path is not found try to get a path to the root node
        if not crumbs:
            currentNode = self.GetRootItem()
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


    def setRootByPage(self, rootpage):
        """
        Clear the tree and use page described by rootpage as
        root of the tree
        """
        self.DeleteAllItems()
        # add the root node to the tree
        nodeobj = WikiWordNode(self, rootpage)
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

        childnodes = self.GetPyData(item).listChildren()

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


def relationSort(a, b):
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


# sorter for relations, removes brackets and sorts lower case
def removeBracketsAndSortDesc(a, b):
    a = wikiWordToLabel(a[0])
    b = wikiWordToLabel(b[0])
    return cmp(b.lower(), a.lower())

def removeBracketsAndSortAsc(a, b):
    a = wikiWordToLabel(a[0])
    b = wikiWordToLabel(b[0])
    return cmp(a.lower(), b.lower())

