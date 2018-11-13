import re


# Example plugin for EditorFunctions type plugins
#
# The plugin allows to install new menu items and toolbar items and register a
# a function with each that is called. The function must accept one argument which
# is the instance of PersonalWikiFrame providing access to the editor and the data store.
#
# To register a menu item implement the function describeMenuItem to return a
# sequence of tuples at least containing the callback function, the item string
# and an item tooltip (see below for details).
#
# To register a toolbar item implement the function describeToolbarItem to return
# a tuple at least containing the callback function, item label, tooltip and icon.
#
# both register functions must accept one argument which is again the
# PersonalWikiFrame instance

# descriptor for EditorFunctions plugin type
WIKIDPAD_PLUGIN = (("MenuFunctions",1),)

def describeMenuItems(wiki):
    """
    wiki -- Calling PersonalWikiFrame
    Returns a sequence of tuples to describe the menu items, where each must
    contain (in this order):
        - callback function
        - menu item string
        - menu item description (string to show in status bar)
    It can contain the following additional items (in this order), each of
    them can be replaced by None:
        - icon descriptor (see below, if no icon found, it won't show one)
        - menu item id.
        - update function
        - kind of menu item (wx.ITEM_NORMAL, wx.ITEM_CHECK)


    The  callback function  must take 2 parameters:
        wiki - Calling PersonalWikiFrame
        evt - wx.CommandEvent

    If the  menu item string  contains one or more vertical bars '|' these
        are taken as delimiters to describe a "path" of submenus where
        the item should be placed. E.g. the item string
        "Admin|Maintenance|Reset Settings" will create in plugins menu
        a submenu "Admin" containing a submenu "Maintenance" containing
        the item "Reset Settings".

    An  icon descriptor  can be one of the following:
        - a wx.Bitmap object
        - the filename of a bitmap (if file not found, no icon is used)
        - a tuple of filenames, first existing file is used
    """
    
    kb = wiki.getKeyBindings()
    
    return ((autoNewNumbered, _("Create new page") + "\t" +
            kb.Plugin_AutoNew_Numbered, _("Create new page")),)


_testRE = re.compile(r"^New[0-9]{6}$")


def autoNewNumbered(wiki, evt):
    wiki.saveAllDocPages()
    candidates = wiki.getWikiData().getWikiPageLinkTermsStartingWith("New")
            
    candidates = [w for w in candidates if _testRE.match(w)]
    numbers = [int(w[3:]) for w in candidates]

    if len(numbers) == 0:
        nextNumber = 1
    else:
        nextNumber = max(numbers) + 1
    wiki.openWikiPage("New%06i" % nextNumber)
    dpp = wiki.getCurrentDocPagePresenter()
    if dpp is None:
        return
    dpp.switchSubControl("textedit", True)
    dpp.SetFocus()

