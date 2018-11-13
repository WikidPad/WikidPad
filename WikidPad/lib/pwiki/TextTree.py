"""
Helper to convert a text written in a format like the functional pages for the 
text block menu or the favorite wikis menu in the appropriate tree and
to generate the corresponding menu.
"""

import traceback

import wx

from .WikiExceptions import *
from .wxHelper import XrcControls, GUI_ID

from .StringOps import splitIndentDeepness, unescapeWithRe, uniWithNone, \
        re_sub_escape, splitFill

from .AdditionalDialogs import SelectIconDialog


# class MenuBuilder:
#     def __init__(self, menu, evtSender, evtRcvFunc):
#         """
#         menu -- wx.Menu object to which items should be added
#         """
#         self.evtSender = evtSender
#         self.evtRcvFunc = evtRcvFunc


class Item:
    def isEntry(self):
        assert 0  # abstract


class Container(Item):
    def __init__(self):
        self.items = []
        self.title = None

    def append(self, item):
        if item.isEntry():
            if item.value != "":
                self.items.append(item)
            else:
                if self.title is None:
                    self.title = item.title
        else:
            self.items.append(item)

    def getItems(self):
        return self.items

    def isEntry(self):
        return False
        
    def __repr__(self):
        return "TextTree.Container("+ repr(self.title) + ", " + repr(self.items) + ")"


class TextBlocksEntry(Item):
    def __init__(self, title, flags, value):
        self.title = title
        self.flags = flags
        self.value = value

    def isEntry(self):
        return True

    @staticmethod        
    def factory(text):
        try:
            entryPrefix, entryValue = text.split("=", 1)
        except:
            return None
            
        entryPrefixes = entryPrefix.split(";")
        entryTitle = entryPrefixes[0]
        if len(entryPrefixes) > 1:
            entryFlags = entryPrefixes[1]
        else:
            entryFlags = ""
            
        entryValue = unescapeWithRe(entryValue)

#         if escapedValue:
#             try:
#                 entryValue = unescapeWithRe(entryValue)
#             except:
#                 return None

        if entryTitle == "":
            entryTitle = entryValue[:60]   # TODO Changeable
            entryTitle = entryTitle.split("\n", 1)[0]
        else:
            try:
                entryTitle = unescapeWithRe(entryTitle)
            except:
                return None
        
        return TextBlocksEntry(entryTitle, entryFlags, entryValue)
        
    def __repr__(self):
        return "TextBlocksEntry" + repr((self.title, self.flags, self.value))



class FavoriteWikisEntry(Item):
    def __init__(self, title, flags, iconDesc, value):
        self.title = title
        self.flags = flags
        self.iconDesc = iconDesc
        self.value = value

    def isEntry(self):
        return True
        
    def getToolbarPosition(self):
        """
        If a digit other than 0 is in the flags, this is the toolbar position.
        Otherwise return -1.
        """
        for f in self.flags:
            try:
                num = int(f)
                if num == 0:
                    continue
                return num
            except ValueError:
                continue
        
        return -1
    
    def getTextLine(self):
        """
        Create text line (without ending \n) which contains the data in
        this entry.
        """
        return re_sub_escape(uniWithNone(self.title)) + ";" + \
                uniWithNone(self.flags) + ";" + uniWithNone(self.iconDesc) + \
                "=" + uniWithNone(self.value)


    @staticmethod        
    def factory(text):
        try:
            entryPrefix, entryValue = text.split("=", 1)
        except:
            return None
            
        entryPrefixes = entryPrefix.split(";")
        entryTitle = entryPrefixes[0]
        entryFlags = ""
        entryIconDesc = ""

        if len(entryPrefixes) > 1:
            entryFlags = entryPrefixes[1]
            if len(entryPrefixes) > 2:
                entryIconDesc = entryPrefixes[2]

        if entryTitle == "":
            entryTitle = entryValue[-60:]   # TODO Changeable
            entryTitle = entryTitle.split("\n")[-1]
        else:
            try:
                entryTitle = unescapeWithRe(entryTitle)
            except:
                return None
        
        return FavoriteWikisEntry(entryTitle, entryFlags, entryIconDesc,
                entryValue)



def buildTreeFromText(content, entryFactory):
    """
    content --- Text to build tree from
    """
    stack = [(0, Container())]
    
    emptyLine = False
    lastTitle = None
    for line in content.split("\n"):
        if line.strip() == "":
            emptyLine = True
            lastTitle = None
            continue

        # Parse line                
        deep, text = splitIndentDeepness(line)

        entry = entryFactory(text)
        if entry is None:
            emptyLine = False
            continue

        # Adjust the stack
        if deep > stack[-1][0]:
            container = Container()
            container.title = lastTitle
            lastTitle = None
            stack.append((deep, container))
        elif stack[-1][0] > deep:
            while stack[-1][0] > deep:
                container = stack.pop()[1]
                if container.title is None:
                    container.title = _("<No title>")

                stack[-1][1].append(container)
#         else:
#             if emptyLine:    
#                 container = stack.pop()[1]
#                 if container.title is None:
#                     container.title = _(u"<No title>")
#     
#                 stack[-1][1].append(container)
#                 stack.append((deep, Container()))


#         # Create new entry if necessary
#         title = stack[-1][1]
#         if title is None:
#             # Entry defines title
#             stack[-1][1] = entryTitle
#             
#         if entryValue == u"":
#             continue

        stack[-1][1].append(entry)

        if entry.value == "" and entry.title != "":
            lastTitle = entry.title
        else:
            lastTitle = None

        emptyLine = False

    # Finally empty stack
    while len(stack) > 1:
        container = stack.pop()[1]
        if container.title is None:
            container.title = _("<No title>")

        stack[-1][1].append(container)
    
    return stack[-1][1]



def addTreeToMenu(container, menu, idRecycler, evtSender, evtRcvFunc):
    """
    Helper to build up menu from tree
    
    container -- Tree data as built by buildTreeFromText()
    menu -- Menu to add items and submenus to
    evtSender -- wx.Window which sends the menu events
    evtRcvFunc -- event receiver function
    """
    for item in container.items:
        if item.isEntry():
            menuID, reused = idRecycler.assocGetIdAndReused(item)

            if not reused:
                # For a new id, an event must be set
                evtSender.Bind(wx.EVT_MENU, evtRcvFunc, id=menuID)

            menuItem = wx.MenuItem(menu, menuID, item.title)
            menu.Append(menuItem)
        elif isinstance(item, Container):
            # Handle subcontainer recursively
            submenu = wx.Menu()
            addTreeToMenu(item, submenu, idRecycler, evtSender, evtRcvFunc)
            menu.AppendSubMenu(submenu, item.title)

   
   
   
   
class AddWikiToFavoriteWikisDialog(wx.Dialog):
    def __init__(self, parent, ID, entry, title=None,
                 pos=wx.DefaultPosition, size=wx.DefaultSize):
        """
        entry -- FavoriteWikisEntry
        """
        wx.Dialog.__init__(self)

        self.parent = parent
        self.entry = entry
        self.value = None
        res = wx.xrc.XmlResource.Get()
        res.LoadDialog(self, self.parent, "AddWikiToFavoriteWikisDialog")

        self.ctrls = XrcControls(self)

        if title is not None:
            self.SetTitle(title)

        # Create list of controls which should enabled only if checkbox
        # "show in toolbar" is checked
        self.dependingOnShowInToolbar = (
                self.ctrls.spinIconPosition, self.ctrls.tfIcon, 
                self.ctrls.btnSelectIcon
                )
                
        toolbarPos = self.entry.getToolbarPosition()

        title, shortcut = splitFill(uniWithNone(self.entry.title), "\t", 1)

        self.ctrls.tfTitle.SetValue(title)
        self.ctrls.tfShortcut.SetValue(shortcut)
        self.ctrls.tfPathOrUrl.SetValue(uniWithNone(self.entry.value))
        self.ctrls.cbOpenInNewWindow.SetValue("n" in self.entry.flags)
        self.ctrls.cbShowInToolbar.SetValue(toolbarPos != -1)

        self.ctrls.spinIconPosition.SetValue(toolbarPos)
        self.ctrls.tfIcon.SetValue(uniWithNone(self.entry.iconDesc))

        self.ctrls.btnOk.SetId(wx.ID_OK)
        self.ctrls.btnCancel.SetId(wx.ID_CANCEL)

        self.OnShowInToolbar(None)

        # Fixes focus bug under Linux
        self.SetFocus()

        self.Bind(wx.EVT_BUTTON, self.OnOk, id=wx.ID_OK)
        self.Bind(wx.EVT_BUTTON, self.OnSelectPath, id=GUI_ID.btnSelectPath)
        self.Bind(wx.EVT_BUTTON, self.OnSelectIcon, id=GUI_ID.btnSelectIcon)

        self.Bind(wx.EVT_CHECKBOX, self.OnShowInToolbar, id=GUI_ID.cbShowInToolbar)


    def getValue(self):
        return self.value

    def OnShowInToolbar(self, evt):
        """
        Gray out some fields if "show in toolbar" not checked.
        """
        enabled = self.ctrls.cbShowInToolbar.GetValue()
        for ct in self.dependingOnShowInToolbar:
            ct.Enable(enabled)


    def OnSelectPath(self, evt):
        """
        The "..." button after the "path or URL" field was pressed
        """

#         # Build wildcard string
#         wcs = []
#         for wd, wp in expDestWildcards:
#             wcs.append(wd)
#             wcs.append(wp)
#             
#         wcs.append(_(u"All files (*.*)"))
#         wcs.append(u"*")
#         
#         wcs = u"|".join(wcs)
            
        selfile = wx.FileSelector(_("Select wiki for favorites"),
                self.ctrls.tfPathOrUrl.GetValue(),
                default_filename = "", default_extension = "",
                wildcard = "*.wiki", flags=wx.FD_OPEN, parent=self)

        if selfile:
            self.ctrls.tfPathOrUrl.SetValue(selfile)


    def OnSelectIcon(self, evt):
        """
        The "..." button after the icon field was pressed
        """
        iconDesc = SelectIconDialog.runModal(self, -1,
                wx.GetApp().getIconCache())
        
        if iconDesc is not None:
            self.ctrls.tfIcon.SetValue(iconDesc)


    def OnOk(self, evt):
        try:
            entry = self.entry
            
            entry.title = self.ctrls.tfTitle.GetValue()

            shortcut = self.ctrls.tfShortcut.GetValue()
            if shortcut != "":
                entry.title += "\t" + shortcut

            entry.value = self.ctrls.tfPathOrUrl.GetValue()
            entry.iconDesc = self.ctrls.tfIcon.GetValue()
            
            flags = ""
            if self.ctrls.cbOpenInNewWindow.GetValue():
                flags += "n"
                
            if self.ctrls.cbBringToFront.GetValue():
                flags += "f"
            
            if self.ctrls.cbShowInToolbar.GetValue():
                flags += str(self.ctrls.spinIconPosition.GetValue())
                
            entry.flags = flags

            self.value = entry
        finally:
            self.EndModal(wx.ID_OK)


    @staticmethod
    def runModal(parent, ID, entry, title=None,
            pos=wx.DefaultPosition, size=wx.DefaultSize):

        dlg = AddWikiToFavoriteWikisDialog(parent, ID, entry, title, pos,
                size)
        try:
            dlg.CenterOnParent(wx.BOTH)
            if dlg.ShowModal() == wx.ID_OK:
                return dlg.getValue()
            else:
                return None

        finally:
            dlg.Destroy()



