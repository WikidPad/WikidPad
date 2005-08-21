import sys    ## , hotshot

## _prof = hotshot.Profile("hotshot.prf")

from wxPython.wx import *
from wxPython.stc import *

from WikiData import WikiWordNotFoundException
import WikiFormatting

from StringOps import mbcsEnc, guiToUni, uniToGui


class NodeStyle:
    def __init__(self):
        self.bold = "False"
        self.icon = "page"
        self.color = "null"
        

class WikiTreeCtrl(wxTreeCtrl):
    def __init__(self, pWiki, parent, ID):        
        wxTreeCtrl.__init__(self, parent, ID, style=wxTR_HAS_BUTTONS)
        self.pWiki = pWiki

        # mapping of property names to functions to apply those properties
        self.propFunctions = {'color': self.setNodeColor,
                              'icon': self.setNodeImage,
                              'bold': self.setNodeBold}

        EVT_TREE_ITEM_ACTIVATED(self, ID, self.OnTreeItemActivated)
        EVT_TREE_SEL_CHANGED(self, ID, self.OnTreeItemActivated)
        EVT_TREE_ITEM_EXPANDING(self, ID, self.OnTreeItemExpand)
        EVT_TREE_ITEM_COLLAPSED(self, ID, self.OnTreeItemCollapse)
        EVT_RIGHT_DOWN(self, self.OnRightButtonDown)

        self.rightClickMenu=wxMenu()

        menuID=wxNewId()
        self.rightClickMenu.Append(menuID, 'Rename', 'Rename')
        EVT_MENU(self, menuID, lambda evt: self.pWiki.showWikiWordRenameDialog())

        menuID=wxNewId()
        self.rightClickMenu.Append(menuID, 'Delete', 'Delete')
        EVT_MENU(self, menuID, lambda evt: self.pWiki.showWikiWordDeleteDialog())

        menuID=wxNewId()
        self.rightClickMenu.Append(menuID, 'Bookmark', 'Bookmark')
        EVT_MENU(self, menuID, lambda evt: self.pWiki.insertAttribute("bookmarked", "true"))

        menuID=wxNewId()
        self.rightClickMenu.Append(menuID, 'Set As Root', 'Set As Root')
        EVT_MENU(self, menuID, lambda evt: self.pWiki.setCurrentWordAsRoot())


    def collapse(self):        
        rootNode = self.GetRootItem()
        self.CollapseAndReset(rootNode)
        
    def getHideUndefined(self):
        return self.pWiki.configuration.getboolean("main", "hideundefined")


    # TODO Update label (priority number)
    def updateTreeNode(self, wikiPage, treeNode, hasChildren=None):
        """
        Update visual presentation of tree node (label, style, color, itemhaschildren).
        But does not update its children.
        
        wikiPage -- WikiPage of the item at least with ['props'] data
        treeNode -- node of the item
        """
        ## haschildren = True
        if treeNode == self.GetRootItem():
            hasChildren = True # Has at least ScratchPad and Views
        elif hasChildren is None:
            hasChildren = len(wikiPage.getChildRelationships(      
                    existingonly=self.getHideUndefined(), selfreference=False)) > 0
        
        if not hasChildren:
            self.CollapseAndReset(treeNode)
            
        self.SetItemHasChildren(treeNode, hasChildren)

        # apply custom properties to nodes
        self.applyPropsToTreeNode(wikiPage, treeNode)


    def buildTreeForWord(self, wikiWord, selectNode=False, doexpand=False):
        """
        First tries to find a path from wikiWord to the currently selected node.
        If nothing is found, searches for a path from wikiWord to the root.
        Expands the tree out if a path is found.
        """

        if selectNode:
            doexpand = True

        wikiData = self.pWiki.wikiData
        currentNode = self.GetRootItem()

        # check for path from wikiWord to currently selected tree node            
        currentNodeText = self.getNodeValue(currentNode)
        crumbs = wikiData.findBestPathFromWordToWord(wikiWord, currentNodeText)

        # if a path is not found try to get a path to the root node
        if not crumbs:
            crumbs = wikiData.findBestPathFromWordToWord(wikiWord,
                    self.getNodeValue(self.GetRootItem()))   # self.pWiki.wikiName)
            if crumbs:
                currentNode = self.GetRootItem()

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
                        currentNode = self.findChildTreeNodeWithText(currentNode, crumbs[i+1])
                except Exception, e:
                    sys.stderr.write("error expanding tree node: %s\n" % e)


            # set the ItemHasChildren marker if the node is not expanded
            if currentNode:
                currentWikiWord = self.getNodeValue(currentNode)

                # the only time this could be 0 really is if the expand above
                # invalidated the root pointer
                if len(currentWikiWord) > 0:
                    try:
                        currentNodePage = wikiData.getPage(currentWikiWord, ['props'])   # 'children', 
                        self.updateTreeNode(currentNodePage, currentNode)
                    except Exception, e:
                        sys.stderr.write(str(e))

                if doexpand:
                    self.EnsureVisible(currentNode)                            
                if selectNode:
                    self.SelectItem(currentNode)


    def expandTreeNode(self, treeNode, wikiWord=None):
        """
        Fills in the treeNodes children with the relations to wikiWord. If the
        treeNode passed in is replaced, the replacement is returned.
        """
        wikiData = self.pWiki.wikiData

        if not wikiWord:
            wikiWord = self.getNodeValue(treeNode)

        wikiPage = wikiData.getPage(wikiWord, ['props'])
#         relations = wikiPage.getChildRelationships(
#                 existingonly=self.getHideUndefined(), selfreference=False)
        relations = wikiPage.getChildRelationshipsAndHasChildren(
                existingonly=self.getHideUndefined(), selfreference=False)
                
        # get the sort order for the children
        childSortOrder = "ascending"
        if (wikiPage.props.has_key('child_sort_order')):
            childSortOrder = wikiPage.props['child_sort_order'][0]
            
        # TODO Automatically add ScratchPad
#         if treeNode == self.GetRootItem() and not "ScratchPad" in relations:
#             relations.append(("ScratchPad", None))

        # Apply sort order
        if childSortOrder != "unsorted":
            if childSortOrder.startswith("desc"):
                relations.sort(removeBracketsAndSortDesc) # sort alphabetically
            else:
                relations.sort(removeBracketsAndSortAsc)
            
        relationData = []
        position = 1
        for relation, hasChildren in relations:
            relationPage = wikiData.getPageNoError(relation, ['props'])
            relationData.append((relation, relationPage, position, hasChildren))
            position = position+1
            
        # Sort again, using tree position and priority properties
        relationData.sort(relationSort)
        
        
        # Refresh subtree
        
        ## self.Freeze() # Stop visual updates
        if self.IsExpanded(treeNode):
            treeChildren = self.getChildTreeNodes(treeNode)
        else:
            # Simply remove all, no sophisticated replacement
            self.DeleteChildren(treeNode)
            treeChildren = []
        
        tci = 0    # Index into treeChildren
        
        # Delete/create/update tree nodes
        for (relation, relationPage, position, hasChildren) in relationData:
            if (tci < len(treeChildren)) and \
                    (treeChildren[tci][1] == relation):
                        
                # This relation is already in the tree, so use existing node
                childTreeNode = treeChildren[tci][0]
                tci += 1
            else:
                # No match, so create new node                
                childTreeNode = self.addTreeNode(treeNode, relation)
                
                # Update childTreeNode   # TODO: Also for existing children?
                try:
                    self.updateTreeNode(relationPage, childTreeNode, hasChildren)
                except WikiWordNotFoundException, e:
                    pass
                
                
        # Remove old children
        while (tci < len(treeChildren)):
            self.Delete(treeChildren[tci][0])
            tci += 1

        # add a "View" node to the root if it isn't already there
        if treeNode == self.GetRootItem(): #wikiWord == self.pWiki.wikiName:
            if not self.findChildTreeNodeWithText(treeNode, "Views"):
                viewNode = self.addViewNode(treeNode, "Views", icon="orgchart")
                
        ## self.Thaw() # Allow visual updates again
        
        return treeNode
        

    def setRootByPage(self, rootpage):
        """
        Clear the tree and use page described by rootpage as
        root of the tree
        """
        self.DeleteAllItems()
        # add the root node to the tree
        root = self.AddRoot(rootpage.wikiWord)
        self.SetPyData(root, (rootpage.wikiWord,None,None))
        self.SetItemBold(root, True)  # TODO: This doesn't work
        self.SelectItem(root)

#       root has at least ScratchPad and Views as children
        self.SetItemHasChildren(root, 1)
        self.Expand(root)


    def addTreeNode(self, parentNode, nodeText, nodeValue=None, viewData=None, searchData=None, applyProps=False):
        if not nodeValue:
            nodeValue = nodeText
        nodeText = getTextForNode(nodeText)
        newNode = self.AppendItem(parentNode, mbcsEnc(nodeText, "replace")[0])
        self.SetPyData(newNode, (nodeValue, viewData, searchData))

        # if applyProps true format the node according to its properties
        if applyProps:
            wikiPage = self.pWiki.wikiData.getPage(nodeValue, ['props'])
            self.applyPropsToTreeNode(wikiPage, newNode) 

        return newNode

    def addViewNode(self, toNode, named, data=u"view", icon='page'):
        "adds a view node setting its data to 'view~something'"
        try:
            newNode = self.addTreeNode(toNode, named, named, data)
            self.SetItemHasChildren(newNode, 1)
            self.setNodeImage(newNode, icon)
            return newNode
        except:
            return None

    def isViewNode(self, item):
        return self.getViewInfo(item)

    def findChildTreeNodeWithText(self, fromNode, findText):
        treeChildren = self.getChildTreeNodes(fromNode)
        for (node, text) in treeChildren:
            if text == findText:
                return node
        return None
        
    def getChildTreeNodes(self, fromNode):
        childNodes = []
        (child, cookie) = self.GetFirstChild(fromNode)    # , 0
        while child:
            childText = self.getNodeValue(child)
            childNodes.append((child, childText))
            (child, cookie) = self.GetNextChild(fromNode, cookie)
        return childNodes

    def applyPropsToTreeNode(self, wikiPage, treeNode):
        wikiData = self.pWiki.wikiData
        wikiWord = wikiPage.wikiWord

        # if this word is an alias for another format this word
        # based on the others properties
        if (wikiData.isAlias(wikiWord)):
            aliasedWord = wikiData.getAliasesWikiWord(wikiWord)
            wikiPage = wikiData.getPage(aliasedWord, ['children', 'props'])

        # fetch the global properties
        globalProps = wikiData.getGlobalProperties()

        # if this is the scratch pad set the icon and return
        if (wikiWord == "ScratchPad"):
            self.setNodeImage(treeNode, "note")
            return

        # get the wikiPage properties
        props = wikiPage.props

        # priority
        priority = None
        if props.has_key("priority"):
            priority = props["priority"][0] # take the first one

        # priority is special. it can create an "importance" and it changes the text of the node            
        if priority:
            wikiWord = getTextForNode(wikiWord)
            self.SetItemText(treeNode, wikiWord + " (%s)" % priority)
            # set default importance based on priority
            if not props.has_key('importance'):
                priorNum = int(priority)
                if (priorNum > 3):
                    props['importance'] = 'high'
                elif (priorNum < 3):
                    props['importance'] = 'low'

##        self.setNodeColor(treeNode, "black")
##        self.setNodeImage(treeNode, "page")
##        self.SetItemBold(treeNode, False)

        style = NodeStyle()

        # apply the global props based on the props of this node
        for (key, values) in props.items():
            for val in values:
                for (type, func) in self.propFunctions.items():
                    gPropVal = globalProps.get("global.%s.%s.%s" % (key, val, type))
                    if not gPropVal:
                        gPropVal = globalProps.get("global.%s.%s" % (key, type))
                    if gPropVal:
                        setattr(style, type, gPropVal)
                        # func(treeNode, gPropVal)
                            
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

        self.setNodeStyle(treeNode, style)


    def setNodeImage(self, node, image):
        try:
            (index, icon) = self.pWiki.iconLookup[image]
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

    def setNodeBold(self, node, notUsed):
        self.SetItemBold(node, True)        

    def setNodeColor(self, node, color):
        if color == "null":
            self.SetItemTextColour(node, wxNullColour)
        else:
            self.SetItemTextColour(node, wxNamedColour(color))

    def setNodeStyle(self, node, style):
        self.setNodeImage(node, style.icon)
        bold = not (style.bold in ("false", "0", "False", "FALSE"))
        self.SetItemBold(node, bold)
        self.setNodeColor(node, style.color)
        
    def expandView(self, viewNode):
        "called from OnTreeItemExpand when a view is expanded"

        wikiData = self.pWiki.wikiData

        # fetch the global properties
        globalProps = self.pWiki.wikiData.getGlobalProperties()

        name = self.GetItemText(viewNode)
        data = self.getViewInfo(viewNode)
        
        if name == "Views":
            # add to do list nodes
            addTheseCategories = []
            todos = wikiData.getTodos()
            for (wikiWord, todo) in todos:
                # parse the todo for name and value
                match = WikiFormatting.ToDoREWithCapturing.match(todo)
                if match:
                    category = match.group(1)
                    # only add the category once
                    if category not in addTheseCategories:
                        addTheseCategories.append(category)

            addTheseCategories.sort()
            for category in addTheseCategories:
                self.addViewNode(viewNode, category, "todos", icon="pin")

            # add property names            
            propNames = wikiData.getPropertyNames()
            ## propNames.sort()
            for name in propNames:
                propertyIcon = globalProps.get("global.%s.icon" % (name))
                if propertyIcon:
                    self.addViewNode(viewNode, name, "property", icon=propertyIcon)
                else:
                    self.addViewNode(viewNode, name, "property")
                    
            # add searches view
            if wikiData.getSavedSearches():
                self.addViewNode(viewNode, "searches", icon="lens") 
                                 
            # add last modified view
            self.addViewNode(viewNode, "modified-within", icon="date") 

            # add last modified view
            if len(self.pWiki.wikiData.getParentLessWords()) > 1:
                self.addViewNode(viewNode, "parentless-nodes", icon="link") 

        elif name == "searches":
            for search in wikiData.getSavedSearches():     # ???
                self.addViewNode(viewNode, search, "%s~searchFor" % name, icon="lens")

        elif name == "modified-within":
            self.addViewNode(viewNode, "1 day", "1~modifiedWithin", icon="date")
            self.addViewNode(viewNode, "3 days", "3~modifiedWithin", icon="date")
            self.addViewNode(viewNode, "1 week", "7~modifiedWithin", icon="date")
            self.addViewNode(viewNode, "1 month", "30~modifiedWithin", icon="date")

        elif name == "parentless-nodes":
            for word in self.pWiki.wikiData.getParentLessWords():
                if word != self.pWiki.wikiName:
                    resultNode = self.addTreeNode(viewNode, word, applyProps=True)

        elif data.endswith('todos'):
            todos = wikiData.getTodos()
            addedTodoSubCategories = []
            for (wikiWord, todo) in todos:
                # parse the todo for name and value
                match = WikiFormatting.ToDoREWithCapturing.match(todo)
                # get the sub categories for this category
                if match.group(1) == name:
                    subCategory = match.group(2)
                    # sub categories are optional
                    if subCategory:
                        # only add the subcategory once
                        if subCategory not in addedTodoSubCategories:
                            # stick the category name in the view data so the todo-item view can extract it
                            self.addViewNode(viewNode, subCategory, "%s~todo~item" % name, icon="pin")
                            addedTodoSubCategories.append(subCategory)
                    else:
                        self.addTreeNode(viewNode, match.group(3), wikiWord, searchData=todo, applyProps=True)

        elif data.endswith('todo~item'):
            # parse the category from the todo~item string
            category = data[0:data.find('~')]
            todos = wikiData.getTodos()
            for (wikiWord, todo) in todos:
                # parse the todo for name and value
                match = WikiFormatting.ToDoREWithCapturing.match(todo)
                # if cat and sub-cat match add the item
                if match.group(1) == category and match.group(2) == name:
                    try:
                        self.addTreeNode(viewNode, match.group(3), wikiWord, searchData=todo, applyProps=True)
                    except:
                        return None
            
        elif data.endswith('property'):
            propNames = wikiData.getPropertyNames()
            if name in propNames:
                values = wikiData.getDistinctPropertyValues(name)

                # if there is only 1 value and it is true or yes, expand it immediately.
                # this is for properties like "[todo: true]". There is no point in putting
                # "true" in the tree if there is no other value
                if len(values) == 1 and (values[0] == 'true' or values[0] == 'yes' or values[0] == 'on'):
                    self.expandViewPropValues(viewNode, name, values[0])
                else:
                    for value in values:                    
                        self.addViewNode(viewNode, value, "%s~property~value" % name)

        elif data.endswith('property~value'):
            self.expandViewPropValues(viewNode)
            
        elif data.endswith('searchFor'):
            for word in wikiData.search(guiToUni(name)):
                resultNode = self.addTreeNode(viewNode, word,
                        searchData=guiToUni(name), applyProps=True)

        elif data.endswith("modifiedWithin"):
            days = int(data[0:data.find('~')])
            words = self.pWiki.wikiData.getWikiWordsModifiedWithin(days)
            words.sort()
            for word in words:
                resultNode = self.addTreeNode(viewNode, word, applyProps=True)
                
    def expandViewPropValues(self, viewNode, key=None, value=None):
        wikiData = self.pWiki.wikiData

        "expands the actual results of a property value view"
        if not key:
            data = self.getViewInfo(viewNode)
            key = data[0:data.find('~')]

        if not value:
            value = self.GetItemText(viewNode)

        words = wikiData.getWordsWithPropertyValue(key, value)
        words.sort()
        for word in words:
            wordNode = self.addTreeNode(viewNode, word, applyProps=True)

    def getNodeValue(self, item):
        (value, data, search) = self.GetPyData(item)
        return value

    def getViewInfo(self, item):
        (value, view, search) = self.GetPyData(item)
        return view

    def getSearchInfo(self, item):
        (value, data, search) = self.GetPyData(item)
        return search
        
    def OnTreeItemActivated(self, event):
        item = event.GetItem()        
        # view nodes can't be activated
        if item.IsOk() and self.GetPyData(item) and not self.isViewNode(item):
            wikiWord = self.getNodeValue(item)
            self.pWiki.openWikiPage(wikiWord)
            searchInfo = self.getSearchInfo(item)
            if searchInfo:
                self.pWiki.editor.executeSearch(searchInfo, 0)
        
        event.Skip()
                    
    def OnTreeItemExpand(self, event):
        ## print "OnTreeItemExpand start"
        ## _prof.start()
        item = event.GetItem()
        if not self.isViewNode(item):
            
            if self.IsExpanded(item):   # TODO Check if a good idea
                return
            self.expandTreeNode(item)
        else:
            self.expandView(item)
        ## _prof.stop()
        ## print "OnTreeItemExpand stop"

    def OnTreeItemCollapse(self, event):
        self.DeleteChildren(event.GetItem())

    def OnRightButtonDown(self, evt):
        if not self.isViewNode(self.GetSelection()):
            self.PopupMenuXY(self.rightClickMenu, evt.GetX(), evt.GetY())


def getTextForNode(text):
    if text.startswith("["):
        return text[1:len(text)-1]
    return text
    

def relationSort(a, b):
    propsA = a[1].props
    propsB = b[1].props

    aSort = None
    bSort = None

    try:
        if (propsA.has_key('tree_position')):
            aSort = int(propsA['tree_position'][0])
        elif (propsA.has_key('priority')):
            aSort = int(propsA['priority'][0])
        else:
            aSort = a[2]
    except:
        aSort = a[2]

    try:            
        if (propsB.has_key('tree_position')):
            bSort = int(propsB['tree_position'][0])
        elif (propsB.has_key('priority')):
            bSort = int(propsB['priority'][0])
        else:
            bSort = b[2]
    except:
        bSort = b[2]

    return cmp(aSort, bSort)


# sorter for relations, removes brackets and sorts lower case
def removeBracketsAndSortDesc(a, b):
    a = getTextForNode(a[0])
    b = getTextForNode(b[0])
    return cmp(b.lower(), a.lower())

def removeBracketsAndSortAsc(a, b):
    a = getTextForNode(a[0])
    b = getTextForNode(b[0])
    return cmp(a.lower(), b.lower())

