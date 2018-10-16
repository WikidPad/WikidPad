# Example plugin for EditorFunctions type plugins
# The functionality was originally implemented by endura29 <endura29@gmail.com>
# Cosmetic changes by schnullibullihulli (2006-06-01)
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
# WIKIDPAD_PLUGIN = (("EditorFunctions",1),)
import wx


# If multiple descriptors with same plugin type but different version numbers
# are provided only the one with the highest version number known to the
# particular WikidPad version is processed.
# 
# Therefore 2.1beta03 or later will only see ("ToolbarFunctions",2), older ones
# only ("ToolbarFunctions",1)

WIKIDPAD_PLUGIN = (("ToolbarFunctions",2), ("ToolbarFunctions",1),
        ("MenuFunctions",1))



def describeMenuItems(wiki):
    """
    Called if plugin descriptor ("MenuFunctions",1) is present.

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
        evt - wxCommandEvent

    If the  menu item string  contains one or more vertical bars '|' these
        are taken as delimiters to describe a "path" of submenus where
        the item should be placed. E.g. the item string
        "Admin|Maintenance|Reset Settings" will create in plugins menu
        a submenu "Admin" containing a submenu "Maintenance" containing
        the item "Reset Settings".

    An  icon descriptor  can be one of the following:
        - a wxBitmap object
        - the filename of a bitmap (if file not found, no icon is used)
        - a tuple of filenames, first existing file is used

    The  update function  must take 2 parameters:
        wiki - Calling PersonalWikiFrame
        evt - wxUpdateUIEvent
    """
    return ((referrals, _("Insert referring pages") + "\tCtrl-Shift-P",
            _("Insert referring pages"), None, None, referralsUpdate),)


def describeToolbarItems(wiki):
    """
    Called if plugin descriptor ("ToolbarFunctions",1) is present.
    
    wiki -- Calling PersonalWikiFrame
    Returns a sequence of tuples to describe the menu items, where each must
    contain (in this order):
        - callback function
        - tooltip string
        - tool item description (string to show in status bar)
        - icon descriptor (see below, if no icon found, a default icon
            will be used)
    It can contain the following additional items (in this order), each of
    them can be replaced by None:
        - tool id.
        - update function

    The  callback function  must take 2 parameters:
        wiki - Calling PersonalWikiFrame
        evt - wxCommandEvent

    An  icon descriptor  can be one of the following:
        - a wxBitmap object
        - the filename of a bitmap (if file not found, a default icon is used)
        - a tuple of filenames, first existing file is used

    The  update function  must take 2 parameters:
        wiki - Calling PersonalWikiFrame
        evt - wxUpdateUIEvent
        
    """
    return ((referrals, _("Referers"), _("Insert referring pages"),
            ("rename", "tb_rename"), None, referralsUpdate),)



def describeToolbarItemsV02(wiki):
    """
    Called if plugin descriptor ("ToolbarFunctions",2) is present and WikidPad
    version is 2.1beta03 or later.
    
    Same as describeToolbarItems, but the tuples returned can have an additional
    parameter:
    
    - right-click function

    The  right-click function  must take 2 parameters:
        wiki - Calling PersonalWikiFrame
        evt - wxCommandEvent
    """

    return ((referrals, _("Referers"), _("Insert referring pages"),
            ("rename", "tb_rename"), None, referralsUpdate, referralsRightClick),)



def referrals(wiki, evt):
    if wiki.getCurrentWikiWord() is None:
        return

    langHelper = wx.GetApp().createWikiLanguageHelper(
            wiki.getWikiDefaultWikiLanguage())

    bracketWords = langHelper.createAbsoluteLinksFromWikiWords

    wiki.getActiveEditor().AddText("\n------------------------\n")

    parents = wiki.wikiData.getParentRelationships(wiki.getCurrentWikiWord())
    parents = [bracketWords((word,)) for word in parents]
    wiki.getActiveEditor().AddText(_("*%s page(s) referring to* %s\n") %
            (len(parents), bracketWords((wiki.getCurrentWikiWord(),))))

    for word in parents:
        wiki.getActiveEditor().AddText("%s\n" % word)
    wiki.getActiveEditor().AddText("------------------------\n")

    children = wiki.wikiData.getChildRelationships(wiki.getCurrentWikiWord())
    children = [bracketWords((word,)) for word in children]
    wiki.getActiveEditor().AddText(_("*%s page(s) referred to by* %s\n") %
            (len(children), bracketWords((wiki.getCurrentWikiWord(),))))

    for word in children:
        wiki.getActiveEditor().AddText("%s\n" % word)
    wiki.getActiveEditor().AddText("------------------------\n")


def referralsRightClick(wiki, evt):
    # Just for demo purposes
    print("Rightclick")


def referralsUpdate(wiki, evt):
    if wiki.getCurrentWikiWord() is None:
        evt.Enable(False)
        return

    dpp = wiki.getCurrentDocPagePresenter()
    if dpp is None:
        evt.Enable(False)
        return

    if dpp.getCurrentSubControlName() != "textedit":
        evt.Enable(False)
        return

    evt.Enable(True)     

    
    
