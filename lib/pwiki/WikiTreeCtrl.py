from wxPython.wx import *
from wxPython.stc import *

from WikiData import WikiWordNotFoundException
import WikiFormatting
import sys

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

        rightClickMenu=wxMenu()                                

        menuID=wxNewId()
        rightClickMenu.Append(menuID, 'Rename', 'Rename')
        EVT_MENU(self, menuID, lambda evt: self.pWiki.showWikiWordRenameDialog())

        menuID=wxNewId()
        rightClickMenu.Append(menuID, 'Delete', 'Delete')
        EVT_MENU(self, menuID, lambda evt: self.pWiki.showWikiWordDeleteDialog())

        menuID=wxNewId()
        rightClickMenu.Append(menuID, 'Bookmark', 'Bookmark')
        EVT_MENU(self, menuID, lambda evt: self.pWiki.insertAttribute("bookmarked", "true"))

        def popup(evt):
            if not self.isViewNode(self.GetSelection()):
                self.PopupMenuXY(rightClickMenu, evt.GetX(), evt.GetY())

        EVT_RIGHT_DOWN(self, popup)


    def collapse(self):        
        rootNode = self.GetRootItem()
        self.CollapseAndReset(rootNode)

    def buildTreeForWord(self, wikiWord, selectNode=False):
        """
        First tries to find a path from wikiWord to the currently selected node.
        If nothing is found, searches for a path from wikiWord to the root.
        Expands the tree out if a path is found.
        """

        wikiData = self.pWiki.wikiData
        currentNode = self.GetRootItem()

        # check for path from wikiWord to currently selected tree node            
        currentNodeText = self.getNodeValue(currentNode)
        crumbs = wikiData.findBestPathFromWordToWord(wikiWord, currentNodeText)

        # if a path is not found try to get a path to the root node
        if not crumbs:
            crumbs = wikiData.findBestPathFromWordToWord(wikiWord, self.pWiki.wikiName)
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
                        currentNodePage = wikiData.getPage(currentWikiWord, ['children', 'props'])
                        if len(currentNodePage.childRelations) > 0:
                            self.SetItemHasChildren(currentNode, 1)
                        else:
                            self.SetItemHasChildren(currentNode, 0)
                        # apply custom properties to nodes
                        self.applyPropsToTreeNode(currentNodePage, currentNode)
                    except Exception, e:
                        sys.stderr.write(e)

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

        treeChanged = False
        wikiPage = wikiData.getPage(wikiWord, ['children', 'props'])
        relations = wikiPage.childRelations

        if self.IsExpanded(treeNode):
            treeChildren = self.getChildTreeNodes(treeNode)

            # get the nodes not in the relations
            deleteThese = [childNode for (childNode, childText) in treeChildren
                            if not self.isViewNode(childNode) and childText not in relations]

            # delete them from the tree
            if len(deleteThese) > 0:
                for toDelete in deleteThese:
                    self.Delete(toDelete)
                # reset the tree children list
                treeChildren = self.getChildTreeNodes(treeNode)
                treeChanged = True

            # get the relations not in the tree
            childWordsInTree = [childText for (childNode, childText) in treeChildren]
            relations = [relation for relation in relations if relation not in childWordsInTree]

        # get the sort order for the children
        childSortOrder = "ascending"
        if (wikiPage.props.has_key('child_sort_order')):
            childSortOrder = wikiPage.props['child_sort_order'][0]

        # sorter for relations, removes brackets and sorts lower case
        def removeBracketsAndSort(a, b):
            a = getTextForNode(a)
            b = getTextForNode(b)
            if childSortOrder.startswith("desc"):
                return cmp(b.lower(), a.lower())
            else:
                return cmp(a.lower(), b.lower())

        # add the missing relationships
        if childSortOrder != "unsorted":
            relations.sort(removeBracketsAndSort) # sort alphabetically

        relationData = []
        position = 1
        for relation in relations:
            relationPage = wikiData.getPage(relation, ['children', 'props'])
            relationData.append((relation, relationPage, position))
            position = position+1
            
        relationData.sort(relationSort)
        for (relation, relationData, position) in relationData:
            childTreeNode = self.addTreeNode(treeNode, relation)
            try:
                if len(relationData.childRelations) > 0:
                    self.SetItemHasChildren(childTreeNode, 1)
                # apply custom properties to nodes
                self.applyPropsToTreeNode(relationData, childTreeNode)                
                treeChanged = True
            except WikiWordNotFoundException, e:
                pass

        # add a "View" node to the root if it isn't already there
        if wikiWord == self.pWiki.wikiName:            
            if not self.findChildTreeNodeWithText(treeNode, "Views"):
                viewNode = self.addViewNode(treeNode, "Views", icon="orgchart")

        return treeNode

    def addTreeNode(self, parentNode, nodeText, nodeValue=None, viewData=None, searchData=None, applyProps=False):
        if not nodeValue:
            nodeValue = nodeText
        nodeText = getTextForNode(nodeText)
        newNode = self.AppendItem(parentNode, nodeText)
        self.SetPyData(newNode, (nodeValue, viewData, searchData))

        # if applyProps true format the node according to its properties
        if applyProps:
            wikiPage = self.pWiki.wikiData.getPage(nodeValue, ['props'])
            self.applyPropsToTreeNode(wikiPage, newNode) 

        return newNode

    def addViewNode(self, toNode, named, data="view", icon='page'):
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
        (child, cookie) = self.GetFirstChild(fromNode, 0)
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

        # apply the global props based on the props of this node
        for (key, values) in props.items():
            for val in values:
                for (type, func) in self.propFunctions.items():
                    gPropVal = globalProps.get("global.%s.%s.%s" % (key, val, type))
                    if not gPropVal:
                        gPropVal = globalProps.get("global.%s.%s" % (key, type))
                    if gPropVal:
                        func(treeNode, gPropVal)
                            
        # color. let user override global color
        if props.has_key("color"):
            self.SetItemTextColour(treeNode, wxNamedColour(props["color"][0]))

        # icon. let user override global icon
        if props.has_key("icon"):
            self.setNodeImage(treeNode, props["icon"][0])
                
    def setNodeImage(self, node, image):
        try:
            (index, icon) = self.pWiki.iconLookup[image]
            if icon:
                self.SetItemImage(node, index, wxTreeItemIcon_Normal)
                self.SetItemImage(node, index, wxTreeItemIcon_Selected)
                self.SetItemImage(node, index, wxTreeItemIcon_Expanded)
                self.SetItemImage(node, index, wxTreeItemIcon_SelectedExpanded)
        except:
            pass        

    def setNodeBold(self, node, notUsed):
        self.SetItemBold(node, True)        

    def setNodeColor(self, node, color):
        self.SetItemTextColour(node, wxNamedColour(color))
        
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
            propNames.sort()
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
            for search in wikiData.getSavedSearches():
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
            for word in wikiData.search(name):
                resultNode = self.addTreeNode(viewNode, word, searchData=name, applyProps=True)

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
        if self.GetPyData(item) and not self.isViewNode(item):
            wikiWord = self.getNodeValue(item)
            self.pWiki.openWikiPage(wikiWord)
            searchInfo = self.getSearchInfo(item)
            if searchInfo:
                self.pWiki.editor.executeSearch(searchInfo, 0)
                    
    def OnTreeItemExpand(self, event):
        item = event.GetItem()
        if not self.isViewNode(item):
            self.expandTreeNode(item)
        else:
            self.expandView(item)

    def OnTreeItemCollapse(self, event):
        self.DeleteChildren(event.GetItem())

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
