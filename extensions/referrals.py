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
WIKIDPAD_PLUGIN = (("MenuFunctions",1), ("ToolbarFunctions",1))

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

    The  callback function  must take 2 parameters:
        wiki - Calling PersonalWikiFrame
        evt - wxCommandEvent

    An  icon descriptor  can be one of the following:
        - a wxBitmap object
        - the filename of a bitmap (if file not found, no icon is used)
        - a tuple of filenames, first existing file is used
    """
    return ((referrals, "Show referring pages\tCtrl-Shift-P", "Show referring pages"),)


def describeToolbarItems(wiki):
    """
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

    The  callback function  must take 2 parameters:
        wiki - Calling PersonalWikiFrame
        evt - wxCommandEvent

    An  icon descriptor  can be one of the following:
        - a wxBitmap object
        - the filename of a bitmap (if file not found, a default icon is used)
        - a tuple of filenames, first existing file is used
    """
    return ((referrals, "Referers", "Show referring pages", ("rename", "tb_rename")),)
    #icon = wiki.lookupIcon("tb_rename")
    # return ((referrals, "Referers", "Show referring pages", icon),)


def referrals(wiki, evt):
    if wiki.getCurrentWikiWord() is None:
        return

    formatting = wiki.getFormatting()
    def bracketWord(word):
        return formatting.BracketStart + word + formatting.BracketEnd

    wiki.getActiveEditor().AddText(u"\n------------------------\n")

    parents = wiki.wikiData.getParentRelationships(wiki.getCurrentWikiWord())
    parents = [bracketWord(word) for word in parents]
    wiki.getActiveEditor().AddText(u"*%s page(s) referring to* %s\n" %
            (len(parents), bracketWord(wiki.getCurrentWikiWord())))

    for word in parents:
        wiki.getActiveEditor().AddText(u"%s\n" % word)
    wiki.getActiveEditor().AddText(u"------------------------\n")

    children = wiki.wikiData.getChildRelationships(wiki.getCurrentWikiWord())
    children = [bracketWord(word) for word in children]
    wiki.getActiveEditor().AddText(u"*%s page(s) referred to by* %s\n" %
            (len(children), bracketWord(wiki.getCurrentWikiWord())))

    for word in children:
        wiki.getActiveEditor().AddText(u"%s\n" % word)
    wiki.getActiveEditor().AddText(u"------------------------\n")
