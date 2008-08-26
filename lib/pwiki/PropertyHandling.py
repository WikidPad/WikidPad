"""
GUI support and error checking for handling properties (=attributes)
"""

import sets, traceback

import pwiki.srePersistent as _re

import wx

from wxHelper import *

from WikiExceptions import *
from Configuration import isUnicode

from LogWindow import LogMessage


wxWIN95 = 20   # For wx.GetOsVersion(), this includes also Win 98 and ME

_COLORS = [
    N_(u"AQUAMARINE"),
    N_(u"BLACK"),
    N_(u"BLUE VIOLET"),
    N_(u"BLUE"),
    N_(u"BROWN"),
    N_(u"CADET BLUE"),
    N_(u"CORAL"),
    N_(u"CORNFLOWER BLUE"),
    N_(u"CYAN"),
    N_(u"DARK GREEN"),
    N_(u"DARK GREY"),
    N_(u"DARK OLIVE GREEN"),
    N_(u"DARK ORCHID"),
    N_(u"DARK SLATE BLUE"),
    N_(u"DARK SLATE GREY"),
    N_(u"DARK TURQUOISE"),
    N_(u"DIM GREY"),
    N_(u"FIREBRICK"),
    N_(u"FOREST GREEN"),
    N_(u"GOLD"),
    N_(u"GOLDENROD"),
    N_(u"GREEN YELLOW"),
    N_(u"GREEN"),
    N_(u"GREY"),
    N_(u"INDIAN RED"),
    N_(u"KHAKI"),
    N_(u"LIGHT BLUE"),
    N_(u"LIGHT GREY"),
    N_(u"LIGHT STEEL BLUE"),
    N_(u"LIME GREEN"),
    N_(u"MAGENTA"),
    N_(u"MAROON"),
    N_(u"MEDIUM AQUAMARINE"),
    N_(u"MEDIUM BLUE"),
    N_(u"MEDIUM FOREST GREEN"),
    N_(u"MEDIUM GOLDENROD"),
    N_(u"MEDIUM ORCHID"),
    N_(u"MEDIUM SEA GREEN"),
    N_(u"MEDIUM SLATE BLUE"),
    N_(u"MEDIUM SPRING GREEN"),
    N_(u"MEDIUM TURQUOISE"),
    N_(u"MEDIUM VIOLET RED"),
    N_(u"MIDNIGHT BLUE"),
    N_(u"NAVY"),
    N_(u"ORANGE RED"),
    N_(u"ORANGE"),
    N_(u"ORCHID"),
    N_(u"PALE GREEN"),
    N_(u"PINK"),
    N_(u"PLUM"),
    N_(u"PURPLE"),
    N_(u"RED"),
    N_(u"SALMON"),
    N_(u"SEA GREEN"),
    N_(u"SIENNA"),
    N_(u"SKY BLUE"),
    N_(u"SLATE BLUE"),
    N_(u"SPRING GREEN"),
    N_(u"STEEL BLUE"),
    N_(u"TAN"),
    N_(u"THISTLE"),
    N_(u"TURQUOISE"),
    N_(u"VIOLET RED"),
    N_(u"VIOLET"),
    N_(u"WHEAT"),
    N_(u"WHITE"),
    N_(u"YELLOW GREEN"),
    N_(u"YELLOW")
]


def buildIconsSubmenu(iconCache):
    """
    iconCache -- object which holds and delivers icon bitmaps (currently PersonalWikiFrame)
    Returns tuple (icon sub menu, dict from menu id to icon name)
    """
    iconMap = {}
    iconsMenu = wx.Menu()

    iconsMenu1 = wx.Menu()
    iconsMenu.AppendMenu(wx.NewId(), u'A-C', iconsMenu1)
    iconsMenu2 = wx.Menu()
    iconsMenu.AppendMenu(wx.NewId(), u'D-F', iconsMenu2)
    iconsMenu3 = wx.Menu()
    iconsMenu.AppendMenu(wx.NewId(), u'G-L', iconsMenu3)
    iconsMenu4 = wx.Menu()
    iconsMenu.AppendMenu(wx.NewId(), u'M-P', iconsMenu4)
    iconsMenu5 = wx.Menu()
    iconsMenu.AppendMenu(wx.NewId(), u'Q-S', iconsMenu5)
    iconsMenu6 = wx.Menu()
    iconsMenu.AppendMenu(wx.NewId(), u'T-Z', iconsMenu6)

    icons = iconCache.iconLookupCache.keys();  # TODO: Create function?
    icons.sort()    # TODO sort with collator

    for icname in icons:
        if icname.startswith("tb_"):
            continue
        iconsSubMenu = None
        if icname[0] <= u'c':
            iconsSubMenu = iconsMenu1
        elif icname[0] <= u'f':
            iconsSubMenu = iconsMenu2
        elif icname[0] <= u'l':
            iconsSubMenu = iconsMenu3
        elif icname[0] <= u'p':
            iconsSubMenu = iconsMenu4
        elif icname[0] <= u's':
            iconsSubMenu = iconsMenu5
        elif icname[0] <= u'z':
            iconsSubMenu = iconsMenu6

        menuID = wx.NewId()
        iconMap[menuID] = icname

        menuItem = wx.MenuItem(iconsSubMenu, menuID, icname, icname)
        bitmap = iconCache.lookupIcon(icname)
        menuItem.SetBitmap(bitmap)
        iconsSubMenu.AppendItem(menuItem)

    return (iconsMenu, iconMap)



def buildColorsSubmenu():
    """
    Returns tuple (color sub menu, dict from menu id to color name)
    """
    colorMap = {}
    colorsMenu = wx.Menu()

    colorsMenu1 = wx.Menu()
    colorsMenu.AppendMenu(wx.NewId(), u'A-L', colorsMenu1)
    colorsMenu2 = wx.Menu()
    colorsMenu.AppendMenu(wx.NewId(), u'M-Z', colorsMenu2)
    
    # Set showColored to False if we are on Win 95/98/ME and use an unicode build
    #   of wxPython because it would crash then
    showColored = not (wx.GetOsVersion()[0] == wxWIN95 and isUnicode())

    for cn in _COLORS:    # ["BLACK"]:
        colorsSubMenu = None
        translatedColorName = _(cn)
        if translatedColorName[0] <= 'L':
            colorsSubMenu = colorsMenu1
        ## elif translatedColorName[0] <= 'Z':
        else:
            colorsSubMenu = colorsMenu2

        menuID = wx.NewId()
        colorMap[menuID] = cn
        menuItem = wx.MenuItem(colorsSubMenu, menuID, translatedColorName,
                translatedColorName)
        
        if showColored:
            cl = wx.NamedColour(cn)
    
            menuItem.SetBackgroundColour(cl)
    
            # if color is dark, text should be white
            #   (checking green component seems to be enough)
            if cl.Green() < 128:
                menuItem.SetTextColour(wx.WHITE)

        colorsSubMenu.AppendItem(menuItem)

    return (colorsMenu, colorMap)



class AbstractPropertyCheck:
    """
    Base class for the PropertyCheck* classes
    """
    def __init__(self, mainControl, propChecker):
        """
        propChecker -- PropertyChecker
        """
        self.mainControl = mainControl
        self.propChecker = propChecker

        self.wikiPage = None
        self.pageAst = None

    def getResponsibleRegex(self):
        """
        Return a compiled regular expression of the property name(s) (keys)
        this object is responsible for
        """
        assert 0  # abstract


    def beginPageCheck(self, wikiPage, pageAst):
        """
        Called before checking of a page begins. Initialize possible cache
        data here
        """
        self.wikiPage = wikiPage
        self.pageAst = pageAst

    def endPageCheck(self):
        """
        Called after checking of page ended. Delete possible cache data here
        """
        self.wikiPage = None
        self.pageAst = None


    def checkEntry(self, propName, propValue, foundProps, start, end, match):
        """
        Check property entry and issue messages if necessary. The function
        can assume that the propName matches the regex returned by
        getResponsibleRegex().

        foundProps -- Set of tuples (propName, propValue) of previously found
            props on a page
        start -- char pos in page where property entry starts
        end -- char pos after end of property entry
        match -- regex match returned by checking the reposibility regex
        """
        assert 0  # abstract
   



class PropertyCheckAlias(AbstractPropertyCheck):
    """
    Property check for "alias" property
    """
    def __init__(self, mainControl, propChecker):
        AbstractPropertyCheck.__init__(self, mainControl, propChecker)
        
    def getResponsibleRegex(self):
        """
        Return a compiled regular expression of the property name(s) (keys)
        this object is responsible for
        """
        return _re.compile(ur"^alias$", _re.DOTALL | _re.UNICODE | _re.MULTILINE)

    def checkEntry(self, propName, propValue, foundProps, start, end, match):
        """
        Check property entry and issue messages if necessary
        foundProps -- Set of tuples (propName, propValue) of previously found
            props on a page
        """
        formatting = self.mainControl.getFormatting()
        
        wikiWord = self.wikiPage.getWikiWord()
     
        if not formatting.isNakedWikiWord(propValue):
            msg = LogMessage(self.mainControl, LogMessage.SEVERITY_WARNING,
                    _(u"Alias value isn't a valid wikiword: [%s: %s]") %
                    (propName, propValue), wikiWord, wikiWord, (start, end))
            self.mainControl.appendLogMessage(msg)
            return
            
        wikiData = self.mainControl.getWikiData()
#         print "checkEntry3", repr(propValue), repr(wikiData.isAlias(propValue)), \
#                 repr(wikiData.isDefinedWikiWord(propValue))

        if not wikiData.isAlias(propValue) and \
                wikiData.isDefinedWikiWord(propValue):
            # Word exists and isn't an alias
            msg = LogMessage(self.mainControl, LogMessage.SEVERITY_WARNING,
                    _(u"A real wikiword with the alias name exists already: "
                    u"[%s: %s]") %
                    (propName, propValue), wikiWord, wikiWord, (start, end))
            self.mainControl.appendLogMessage(msg)
            return
            
        words = wikiData.getWordsWithPropertyValue(u"alias", propValue)
        if len(words) > 1 or (len(words) > 0 and words[0] != wikiWord):
            msg = LogMessage(self.mainControl, LogMessage.SEVERITY_WARNING,
                    _(u"'%s' is already alias for the wiki word(s): %s") %
                    (propValue, u"; ".join(words)), wikiWord, wikiWord,
                    (start, end))
            self.mainControl.appendLogMessage(msg)
            return


class PropertyCheckPresentation(AbstractPropertyCheck):
    """
    Property check for presentation properties "icon", "color" and "bold" and
    their global counterparts.
    """
    def __init__(self, mainControl, propChecker):
        AbstractPropertyCheck.__init__(self, mainControl, propChecker)
        self.foundEntryNames = None  # Set of found presentation entry names 


    def getResponsibleRegex(self):
        """
        Return a compiled regular expression of the property name(s) (keys)
        this object is responsible for
        """
        return _re.compile(ur"^(?:global\..*?\.)?(icon|color|bold)$",
                _re.DOTALL | _re.UNICODE | _re.MULTILINE)


    def beginPageCheck(self, wikiPage, pageAst):
        AbstractPropertyCheck.beginPageCheck(self, wikiPage, pageAst)
        self.foundEntryNames = sets.Set()


    def endPageCheck(self):
        self.foundEntryNames = None
        AbstractPropertyCheck.endPageCheck(self)


    def checkEntry(self, propName, propValue, foundProps, start, end, match):
        """
        Check property entry and issue messages if necessary
        foundProps -- Set of tuples (propName, propValue) of previously found
            props on a page
        """
        wikiWord = self.wikiPage.getWikiWord()

        # Check for double entries with different values on same page
        if propName in self.foundEntryNames:
            msg = LogMessage(self.mainControl, LogMessage.SEVERITY_WARNING,
                    _(u"The attribute %s was already set differently on this page") %
                    (propName,), wikiWord, wikiWord, (start, end))
            self.mainControl.appendLogMessage(msg)
        else:
            self.foundEntryNames.add(propName)
            
        # Check for double entries on other pages for global.* props
        wikiData = self.mainControl.getWikiData()
        if propName.startswith(u"global"):
            words = wikiData.getWordsForPropertyName(propName)
            if len(words) > 1 or (len(words) > 0 and words[0] != wikiWord):
                msg = LogMessage(self.mainControl, LogMessage.SEVERITY_WARNING,
                        _(u"Attribute '%s' is already defined on the wiki page(s): %s") %
                        (propName, u"; ".join(words)), wikiWord, wikiWord,
                        (start, end))
                self.mainControl.appendLogMessage(msg)

        # Check if value is a valid name for icon/color
        if propName.endswith(u"icon"):
            if self.mainControl.lookupIconIndex(propValue) == -1:
                msg = LogMessage(self.mainControl, LogMessage.SEVERITY_HINT,
                        _(u"Icon name doesn't exist: [%s: %s]") %
                        (propName, propValue), wikiWord, wikiWord, (start, end))
                self.mainControl.appendLogMessage(msg)
        elif propName.endswith(u"color"):
            if propValue.upper() not in _COLORS:
                msg = LogMessage(self.mainControl, LogMessage.SEVERITY_HINT,
                        _(u"Color name doesn't exist: [%s: %s]") %
                        (propName, propValue), wikiWord, wikiWord, (start, end))
                self.mainControl.appendLogMessage(msg)


# TODO Move to extension
class PropertyCheckGlobalGraphInclude(AbstractPropertyCheck):
    """
    Property check for presentation properties "icon", "color" and "bold" and
    their global counterparts.
    """
    def __init__(self, mainControl, propChecker):
        AbstractPropertyCheck.__init__(self, mainControl, propChecker)
        self.foundEntryNames = None  # Set of found presentation entry names 


    def getResponsibleRegex(self):
        """
        Return a compiled regular expression of the property name(s) (keys)
        this object is responsible for
        """
        return _re.compile(ur"^global\.graph\.relations\.include$",
                _re.DOTALL | _re.UNICODE | _re.MULTILINE)


#     def beginPageCheck(self, wikiPage, pageAst):
#         AbstractPropertyCheck.beginPageCheck(self, wikiPage, pageAst)
# 
# 
#     def endPageCheck(self):
#         AbstractPropertyCheck.endPageCheck(self)


    def checkEntry(self, propName, propValue, foundProps, start, end, match):
        """
        Check property entry and issue messages if necessary
        foundProps -- Set of tuples (propName, propValue) of previously found
            props on a page
        """
        wikiWord = self.wikiPage.getWikiWord()
        wikiDoc = self.wikiPage.getWikiDocument()
        
        props = wikiDoc.getPropertyTriples(None,
                "global.graph.relations.exclude", None)
        
        if len(props) > 0:
            # Check for double entries with different values on same page
            msg = LogMessage(self.mainControl, LogMessage.SEVERITY_WARNING,
                    _(u"The attribute 'global.graph.relations.exclude' (e.g. on page '%s') "
                        "overrides the '...include' property") %
                    (props[0][0],), wikiWord, wikiWord, (start, end))
            
            self.mainControl.appendLogMessage(msg)
            


class PropertyChecker:
    """
    Component which checks a page for possible errors in the written properties
    """
    def __init__(self, mainControl):
        self.mainControl = mainControl
        self.singleCheckList = [PropertyCheckAlias(self.mainControl, self),
                PropertyCheckPresentation(self.mainControl, self),
                PropertyCheckGlobalGraphInclude(self.mainControl, self)]

        # Fill singleCheckREs (needed by findCheckObject)
        self.singleCheckREs = []
        for c in self.singleCheckList:
            self.singleCheckREs.append((c.getResponsibleRegex(), c))


    def _beginPageCheck(self, wikiPage, pageAst):
        """
        Calls beginPageCheck of all PropertyCheck* objects in
        the singleCheckList
        """
        for c in self.singleCheckList:
            try:
                c.beginPageCheck(wikiPage, pageAst)
            except:
                traceback.print_exc()


    def _endPageCheck(self):
        """
        Calls endPageCheck of all PropertyCheck* objects in
        the singleCheckList
        """
        for c in self.singleCheckList:
            try:
                c.endPageCheck()
            except:
                traceback.print_exc()


    def findCheckObject(self, propName):
        """
        Return appropriate PropertyCheck* object from singleCheckList and
        match object or (None, None) if not found.
        """
        for p, c in self.singleCheckREs:
            match = p.match(propName)
            if match:
                return c, match

        return None, None


    def checkPage(self, wikiPage, pageAst):
        """
        Check properties for a given page and page ast and fill
        log window with messages if necessary
        """
        foundProps = sets.Set()
        propTokens = wikiPage.extractPropertyTokensFromPageAst(pageAst)
        
        self._beginPageCheck(wikiPage, pageAst)
        try:
            self.mainControl.getLogWindow().removeWithCheckedWikiWord(
                    wikiPage.getWikiWord())
            for t in propTokens:
                propKey = t.node.key
                for propValue in t.node.values:
                    propTuple = (propKey, propValue)

                    if propTuple in foundProps:
                        msg = LogMessage(self.mainControl, LogMessage.SEVERITY_HINT,
                                _(u"Same attribute twice: [%s: %s]") % propTuple,
                                wikiPage.getWikiWord(), wikiPage.getWikiWord(),
                                (t.start, t.start + t.getRealLength()))
                        self.mainControl.appendLogMessage(msg)
                        continue # if first property had messages there's no need to repeat them

                    foundProps.add(propTuple)

                    c, match = self.findCheckObject(propKey)
                    if c is not None:                
                        c.checkEntry(propKey, propValue, foundProps, t.start,
                                t.start + t.getRealLength(), match)

            self.mainControl.getLogWindow().checkAutoHide()
        finally:
            self._endPageCheck()



