"""
GUI support for handling properties
"""

from wxPython.wx import *


_COLORS = [
    "AQUAMARINE",
    "BLACK",
    "BLUE VIOLET",
    "BLUE",
    "BROWN",
    "CADET BLUE",
    "CORAL",
    "CORNFLOWER BLUE",
    "CYAN",
    "DARK GREEN",
    "DARK GREY",
    "DARK OLIVE GREEN",
    "DARK ORCHID",
    "DARK SLATE BLUE",
    "DARK SLATE GREY",
    "DARK TURQUOISE",
    "DIM GREY",
    "FIREBRICK",
    "FOREST GREEN",
    "GOLD",
    "GOLDENROD",
    "GREEN YELLOW",
    "GREEN",
    "GREY",
    "INDIAN RED",
    "KHAKI",
    "LIGHT BLUE",
    "LIGHT GREY",
    "LIGHT STEEL BLUE",
    "LIME GREEN",
    "MAGENTA",
    "MAROON",
    "MEDIUM AQUAMARINE",
    "MEDIUM BLUE",
    "MEDIUM FOREST GREEN",
    "MEDIUM GOLDENROD",
    "MEDIUM ORCHID",
    "MEDIUM SEA GREEN",
    "MEDIUM SLATE BLUE",
    "MEDIUM SPRING GREEN",
    "MEDIUM TURQUOISE",
    "MEDIUM VIOLET RED",
    "MIDNIGHT BLUE",
    "NAVY",
    "ORANGE RED",
    "ORANGE",
    "ORCHID",
    "PALE GREEN",
    "PINK",
    "PLUM",
    "PURPLE",
    "RED",
    "SALMON",
    "SEA GREEN",
    "SIENNA",
    "SKY BLUE",
    "SLATE BLUE",
    "SPRING GREEN",
    "STEEL BLUE",
    "TAN",
    "THISTLE",
    "TURQUOISE",
    "VIOLET RED",
    "VIOLET",
    "WHEAT",
    "WHITE",
    "YELLOW GREEN",
    "YELLOW"
]


def buildIconsSubmenu(iconCache):
    """
    iconCache -- object which holds and delivers icon bitmaps (currently PersonalWikiFrame)
    Returns tuple (icon sub menu, dict from menu id to icon name)
    """
    iconMap = {}
    iconsMenu = wxMenu()

    iconsMenu1 = wxMenu()
    iconsMenu.AppendMenu(wxNewId(), 'A-C', iconsMenu1)
    iconsMenu2 = wxMenu()
    iconsMenu.AppendMenu(wxNewId(), 'D-F', iconsMenu2)
    iconsMenu3 = wxMenu()
    iconsMenu.AppendMenu(wxNewId(), 'H-L', iconsMenu3)
    iconsMenu4 = wxMenu()
    iconsMenu.AppendMenu(wxNewId(), 'M-P', iconsMenu4)
    iconsMenu5 = wxMenu()
    iconsMenu.AppendMenu(wxNewId(), 'Q-S', iconsMenu5)
    iconsMenu6 = wxMenu()
    iconsMenu.AppendMenu(wxNewId(), 'T-Z', iconsMenu6)

    icons = iconCache.iconLookupCache.keys();  # TODO: Create function?
    icons.sort()

    for icname in icons:
        if icname.startswith("tb_"):
            continue
        iconsSubMenu = None
        if icname[0] <= 'c':
            iconsSubMenu = iconsMenu1
        elif icname[0] <= 'f':
            iconsSubMenu = iconsMenu2
        elif icname[0] <= 'l':
            iconsSubMenu = iconsMenu3
        elif icname[0] <= 'p':
            iconsSubMenu = iconsMenu4
        elif icname[0] <= 's':
            iconsSubMenu = iconsMenu5
        elif icname[0] <= 'z':
            iconsSubMenu = iconsMenu6

        menuID = wxNewId()
        iconMap[menuID] = icname

        menuItem = wxMenuItem(iconsSubMenu, menuID, icname, icname)
        bitmap = iconCache.lookupIcon(icname)
        menuItem.SetBitmap(bitmap)
        iconsSubMenu.AppendItem(menuItem)

    return (iconsMenu, iconMap)



def buildColorsSubmenu():
    """
    Returns tuple (color sub menu, dict from menu id to color name)
    """
    colorMap = {}
    colorsMenu = wxMenu()

    colorsMenu1 = wxMenu()
    colorsMenu.AppendMenu(wxNewId(), 'A-L', colorsMenu1)
    colorsMenu2 = wxMenu()
    colorsMenu.AppendMenu(wxNewId(), 'M-Z', colorsMenu2)

    for cn in _COLORS:    # ["BLACK"]:
        colorsSubMenu = None
        if cn[0] <= 'L':
            colorsSubMenu = colorsMenu1
        ## elif cn[0] <= 'Z':
        else:
            colorsSubMenu = colorsMenu2

        menuID = wxNewId()
        colorMap[menuID] = cn
        menuItem = wxMenuItem(colorsSubMenu, menuID, cn, cn)
        cl = wxNamedColour(cn)

        menuItem.SetBackgroundColour(cl)

        # if color is dark, text should be white (checking green component seems to be enough)
        if cl.Green() < 128:
            menuItem.SetTextColour(wxWHITE)

        colorsSubMenu.AppendItem(menuItem)

    return (colorsMenu, colorMap)
