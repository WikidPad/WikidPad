"""
GUI support and error checking for handling attributes (=properties)
"""

from __future__ import with_statement


import traceback

import re as _re # import pwiki.srePersistent as reimport pwiki.srePersistent as _re

import wx

from wxHelper import *

from WikiExceptions import *

from .Utilities import callInMainThreadAsync
from .SystemInfo import isUnicode

from . import StringOps

from .LogWindow import LogMessage

from .DocPages import WikiPage



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


_BUILTINS = {
    u"alias": None,
    u"auto_link": (u"off", u"relax"),
    u"bgcolor": _COLORS,
    u"bold": (u"true", u"false"),
    u"camelCaseWordsEnabled": (u"false", u"true"),
    u"child_sort_order": ("ascending", u"descending", u"mod_oldest",
            u"mod_newest", u"unsorted", u"natural"),
    u"color": _COLORS,
    u"export": (u"false",),
    u"font": None, # Special handling

    u"global.auto_link": (u"off", u"relax"),
    u"global.camelCaseWordsEnabled": (u"false", u"true"),
    u"global.child_sort_order": ("ascending", u"descending", u"mod_oldest",
            u"mod_newest", u"unsorted", u"natural"),
    u"global.font": None, # Special handling
    u"global.html.linkcolor": None,
    u"global.html.alinkcolor": None,
    u"global.html.vlinkcolor": None,
    u"global.html.textcolor": None,
    u"global.html.bgcolor": None,
    u"global.html.bgimage": None,
    u"global.import_scripts": None,
    u"global.language": None, # TODO: special handling
    u"global.paragraph_mode": (u"true", u"false"),
    u"global.template": None,
    u"global.template_head": (u"auto", u"manual"),
    u"global.view_pane": (u"off", u"editor", u"preview"),
    u"global.wrap_type": (u"word", u"char"),


    u"html.linkcolor": None,
    u"html.alinkcolor": None,
    u"html.vlinkcolor": None,
    u"html.textcolor": None,
    u"html.bgcolor": None,
    u"html.bgimage": None,
    u"icon": None,   # Special handling
    u"import_scripts": None,
    u"importance": (u"high", u"low"),
    u"language": None, # TODO: special handling
    u"pagetype": (u"form",),
    u"priority": (u"1", u"2", u"3", u"4", u"5"),
    u"paragraph_mode": (u"true", u"false"),
    u"short_hint": None,
    u"template": None,
    u"template_head": (u"auto", u"manual"),
    u"tree_position": None,
    u"view_pane": (u"off", u"editor", u"preview"),
    u"wrap_type": (u"word", u"char"),

    u"parent": None,
}


def getBuiltinKeys():
    return _BUILTINS.keys()


def getBuiltinValuesForKey(attrKey):
    # Handle exceptions here
    if attrKey == u"icon":
        return wx.GetApp().getIconCache().iconLookupCache.keys()
    elif attrKey == u"font" or attrKey == u"global.font":
        fenum = wx.FontEnumerator()
        fenum.EnumerateFacenames()
        return fenum.GetFacenames()
    else:    
        return _BUILTINS.get(attrKey)




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



class AbstractAttributeCheck:
    """
    Base class for the AttributeCheck* classes
    """
    def __init__(self, mainControl, attrChecker):
        """
        attrChecker -- AttributeChecker
        """
        self.mainControl = mainControl
        self.attrChecker = attrChecker

        self.wikiPage = None
        self.pageAst = None

    def getResponsibleRegex(self):
        """
        Return a compiled regular expression of the attribute name(s) (keys)
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


    def checkEntry(self, attrName, attrValue, foundAttrs, start, end, match):
        """
        Check attribute entry and issue messages if necessary. The function
        can assume that the attrName matches the regex returned by
        getResponsibleRegex().

        foundAttrs -- Set of tuples (attrName, attrValue) of previously found
            attrs on a page
        start -- char pos in page where attribute entry starts
        end -- char pos after end of attribute entry
        match -- regex match returned by checking the reposibility regex
        """
        assert 0  # abstract
   
class AttributeCheckParent(AbstractAttributeCheck):
    """
    Attribute check for "parent" attribute
    """
    def __init__(self, mainControl, attrChecker):
        AbstractAttributeCheck.__init__(self, mainControl, attrChecker)
        self.foundAttributes = []
        
    def getResponsibleRegex(self):
        """
        Return a compiled regular expression of the attribute name(s) (keys)
        this object is responsible for
        """
        return _re.compile(ur"^parent$", _re.DOTALL | _re.UNICODE | _re.MULTILINE)

    def beginPageCheck(self, wikiPage, pageAst):
        AbstractAttributeCheck.beginPageCheck(self, wikiPage, pageAst)

    def endPageCheck(self):
        self.foundAttributes = []
        AbstractAttributeCheck.endPageCheck(self)

    def checkEntry(self, attrName, attrValue, foundAttrs, start, end, match):
        """
        Check attribute entry and issue messages if necessary
        foundAttrs -- Set of tuples (attrName, attrValue) of previously found
            attrs on a page
        """
        self.foundAttributes.append((attrName, attrValue, start, end))

        wikiDocument = self.wikiPage.getWikiDocument()
        langHelper = wx.GetApp().createWikiLanguageHelper(
                wikiDocument.getWikiDefaultWikiLanguage())

        wikiWord = self.wikiPage.getWikiWord()

        targetWikiWord = langHelper.resolveWikiWordLink(attrValue, self.wikiPage)

        if not wikiDocument.isDefinedWikiLinkTerm(targetWikiWord):
            # Word does not exist
#             print (attrName, attrValue), wikiWord, wikiWord, (start, end)
            msg = LogMessage(self.mainControl, LogMessage.SEVERITY_WARNING,
                    _(u"Parent wikiword does not exist: "
                    u"[%s: %s]") %
                    (attrName, attrValue), wikiWord, wikiWord, (start, end))
            self.attrChecker.appendLogMessage(msg)
            return

        # Doesn't seem to work in endPageCheck()
        if len(self.foundAttributes) > 1:
            wikiWord = self.wikiPage.getWikiWord()
            for attr in self.foundAttributes: 
                msg = LogMessage(self.mainControl, LogMessage.SEVERITY_WARNING,
                        _(u"Multiple parent attributes found on page: "
                        u"[%s: %s]") %
                        (attr[0], attr[1]), wikiWord, wikiWord, (attr[2], attr[3]))
                self.attrChecker.appendLogMessage(msg)
                return


class AttributeCheckAlias(AbstractAttributeCheck):
    """
    Attribute check for "alias" attribute
    """
    def __init__(self, mainControl, attrChecker):
        AbstractAttributeCheck.__init__(self, mainControl, attrChecker)
        
    def getResponsibleRegex(self):
        """
        Return a compiled regular expression of the attribute name(s) (keys)
        this object is responsible for
        """
        return _re.compile(ur"^alias$", _re.DOTALL | _re.UNICODE | _re.MULTILINE)

    def checkEntry(self, attrName, attrValue, foundAttrs, start, end, match):
        """
        Check attribute entry and issue messages if necessary
        foundAttrs -- Set of tuples (attrName, attrValue) of previously found
            attrs on a page
        """
        wikiDocument = self.wikiPage.getWikiDocument()
        langHelper = wx.GetApp().createWikiLanguageHelper(
                wikiDocument.getWikiDefaultWikiLanguage())

        wikiWord = self.wikiPage.getWikiWord()
        errMsg = langHelper.checkForInvalidWikiLink(attrValue, wikiDocument)

        if errMsg:
            msg = LogMessage(self.mainControl, LogMessage.SEVERITY_WARNING,
                    _(u"Alias value isn't a valid wikiword: [%s: %s], %s") %
                    (attrName, attrValue, errMsg), wikiWord, wikiWord,
                    (start, end))
            self.attrChecker.appendLogMessage(msg)
            return

        targetWikiWord = langHelper.resolveWikiWordLink(attrValue, self.wikiPage)

        if wikiDocument.isDefinedWikiPageName(targetWikiWord):
            # Word exists and isn't an alias
            msg = LogMessage(self.mainControl, LogMessage.SEVERITY_WARNING,
                    _(u"A real wikiword with the alias name exists already: "
                    u"[%s: %s]") %
                    (attrName, attrValue), wikiWord, wikiWord, (start, end))
            self.attrChecker.appendLogMessage(msg)
            return


        # TODO: Check for existing alias
        # Currently deactivated, needs resolving of all links

#         words = [w for w,k,v in wikiDocument
#                 .getAttributeTriples(None, "alias", attrValue)]
# 
# 
#         if len(words) > 1 or (len(words) > 0 and words[0] != wikiWord):
#             msg = LogMessage(self.mainControl, LogMessage.SEVERITY_WARNING,
#                     _(u"'%s' is already alias for the wiki word(s): %s") %
#                     (attrValue, u"; ".join(words)), wikiWord, wikiWord,
#                     (start, end))
#             self.attrChecker.appendLogMessage(msg)
#             return


class AttributeCheckTemplate(AbstractAttributeCheck):
    """
    Attribute check for "template" attribute
    """
    def __init__(self, mainControl, attrChecker):
        AbstractAttributeCheck.__init__(self, mainControl, attrChecker)
        
    def getResponsibleRegex(self):
        """
        Return a compiled regular expression of the attribute name(s) (keys)
        this object is responsible for
        """
        return _re.compile(ur"^(?:global\.)?template$", _re.DOTALL | _re.UNICODE | _re.MULTILINE)

    def checkEntry(self, attrName, attrValue, foundAttrs, start, end, match):
        """
        Check attribute entry and issue messages if necessary
        foundAttrs -- Set of tuples (attrName, attrValue) of previously found
            attrs on a page
        """
        wikiDocument = self.wikiPage.getWikiDocument()
        langHelper = wx.GetApp().createWikiLanguageHelper(
                wikiDocument.getWikiDefaultWikiLanguage())

        wikiWord = self.wikiPage.getWikiWord()
        errMsg = langHelper.checkForInvalidWikiLink(attrValue, wikiDocument)

        if errMsg :
            msg = LogMessage(self.mainControl, LogMessage.SEVERITY_WARNING,
                    _(u"Template value isn't a valid wikiword: [%s: %s], %s") %
                    (attrName, attrValue, errMsg), wikiWord, wikiWord,
                    (start, end))
            self.attrChecker.appendLogMessage(msg)
            return

        targetWikiWord = langHelper.resolveWikiWordLink(attrValue, self.wikiPage)

        if not wikiDocument.isDefinedWikiLinkTerm(targetWikiWord):
            # Word doesn't exist
            msg = LogMessage(self.mainControl, LogMessage.SEVERITY_WARNING,
                    _(u"Template value isn't an existing wikiword: "
                    u"[%s: %s]") %
                    (attrName, attrValue), wikiWord, wikiWord, (start, end))
            self.attrChecker.appendLogMessage(msg)
            return


class AttributeCheckPresentation(AbstractAttributeCheck):
    """
    Attribute check for presentation attributes "icon", "color" and "bold" and
    their global counterparts.
    """
    def __init__(self, mainControl, attrChecker):
        AbstractAttributeCheck.__init__(self, mainControl, attrChecker)
        self.foundEntryNames = None  # Set of found presentation entry names 


    def getResponsibleRegex(self):
        """
        Return a compiled regular expression of the attribute name(s) (keys)
        this object is responsible for
        """
        return _re.compile(ur"^(?:global\..*?\.)?(icon|color|bold)$",
                _re.DOTALL | _re.UNICODE | _re.MULTILINE)


    def beginPageCheck(self, wikiPage, pageAst):
        AbstractAttributeCheck.beginPageCheck(self, wikiPage, pageAst)
        self.foundEntryNames = set()


    def endPageCheck(self):
        self.foundEntryNames = None
        AbstractAttributeCheck.endPageCheck(self)


    def checkEntry(self, attrName, attrValue, foundAttrs, start, end, match):
        """
        Check attribute entry and issue messages if necessary
        foundAttrs -- Set of tuples (attrName, attrValue) of previously found
            attrs on a page
        """
        wikiWord = self.wikiPage.getWikiWord()

        # Check for double entries with different values on same page
        if attrName in self.foundEntryNames:
            msg = LogMessage(self.mainControl, LogMessage.SEVERITY_WARNING,
                    _(u"The attribute %s was already set differently on this page") %
                    (attrName,), wikiWord, wikiWord, (start, end))
            self.attrChecker.appendLogMessage(msg)
        else:
            self.foundEntryNames.add(attrName)
            
        # Check for double entries on other pages for global.* attrs
        wikiData = self.mainControl.getWikiData()
        if attrName.startswith(u"global"):
            words = wikiData.getWordsForAttributeName(attrName)
            if len(words) > 1 or (len(words) > 0 and words[0] != wikiWord):
                msg = LogMessage(self.mainControl, LogMessage.SEVERITY_WARNING,
                        _(u"Attribute '%s' is already defined on the wiki page(s): %s") %
                        (attrName, u"; ".join(words)), wikiWord, wikiWord,
                        (start, end))
                self.attrChecker.appendLogMessage(msg)

        # Check if value is a valid name for icon/color
        if attrName.endswith(u"icon"):
            if self.mainControl.lookupIconIndex(attrValue) == -1:
                msg = LogMessage(self.mainControl, LogMessage.SEVERITY_HINT,
                        _(u"Icon name doesn't exist: [%s: %s]") %
                        (attrName, attrValue), wikiWord, wikiWord, (start, end))
                self.attrChecker.appendLogMessage(msg)
        elif attrName.endswith(u"color"):
#             if attrValue.upper() not in _COLORS:
            if StringOps.colorDescToRgbTuple(attrValue) is None:
                msg = LogMessage(self.mainControl, LogMessage.SEVERITY_HINT,
                        _(u"Color name doesn't exist: [%s: %s]") %
                        (attrName, attrValue), wikiWord, wikiWord, (start, end))
                self.attrChecker.appendLogMessage(msg)


# TODO Move to extension
class AttributeCheckGlobalGraphInclude(AbstractAttributeCheck):
    """
    Attribute check for graph relations.
    """
    def __init__(self, mainControl, attrChecker):
        AbstractAttributeCheck.__init__(self, mainControl, attrChecker)
        self.foundEntryNames = None  # Set of found presentation entry names 


    def getResponsibleRegex(self):
        """
        Return a compiled regular expression of the attribute name(s) (keys)
        this object is responsible for
        """
        return _re.compile(ur"^global\.graph\.relations\.include$",
                _re.DOTALL | _re.UNICODE | _re.MULTILINE)


#     def beginPageCheck(self, wikiPage, pageAst):
#         AbstractAttributeCheck.beginPageCheck(self, wikiPage, pageAst)
# 
# 
#     def endPageCheck(self):
#         AbstractAttributeCheck.endPageCheck(self)


    def checkEntry(self, attrName, attrValue, foundAttrs, start, end, match):
        """
        Check attribute entry and issue messages if necessary
        foundAttrs -- Set of tuples (attrName, attrValue) of previously found
            attrs on a page
        """
        wikiWord = self.wikiPage.getWikiWord()
        wikiDocument = self.wikiPage.getWikiDocument()
        
        attrs = wikiDocument.getAttributeTriples(None,
                "global.graph.relations.exclude", None)
        
        if len(attrs) > 0:
            # Check for double entries with different values on same page
            msg = LogMessage(self.mainControl, LogMessage.SEVERITY_WARNING,
                    _(u"The attribute 'global.graph.relations.exclude' (e.g. on page '%s') "
                        "overrides the '...include' attribute") %
                    (attrs[0][0],), wikiWord, wikiWord, (start, end))
            
            self.attrChecker.appendLogMessage(msg)
            


class AttributeChecker:
    """
    Component which checks a page for possible errors in the written attributes
    """
    def __init__(self, mainControl):
        self.mainControl = mainControl
        self.singleCheckList = [AttributeCheckAlias(self.mainControl, self),
                AttributeCheckTemplate(self.mainControl, self),
                AttributeCheckPresentation(self.mainControl, self),
                AttributeCheckGlobalGraphInclude(self.mainControl, self),
                AttributeCheckParent(self.mainControl, self),]

        # Fill singleCheckREs (needed by findCheckObject)
        self.singleCheckREs = []
        for c in self.singleCheckList:
            self.singleCheckREs.append((c.getResponsibleRegex(), c))
        
        self.msgCollector = None


    def _beginPageCheck(self, wikiPage, pageAst):
        """
        Calls beginPageCheck of all AttributeCheck* objects in
        the singleCheckList
        """
        for c in self.singleCheckList:
            try:
                c.beginPageCheck(wikiPage, pageAst)
            except:
                traceback.print_exc()


    def _endPageCheck(self):
        """
        Calls endPageCheck of all AttributeCheck* objects in
        the singleCheckList
        """
        for c in self.singleCheckList:
            try:
                c.endPageCheck()
            except:
                traceback.print_exc()


    def findCheckObject(self, attrName):
        """
        Return appropriate AttributeCheck* object from singleCheckList and
        match object or (None, None) if not found.
        """
        for p, c in self.singleCheckREs:
            match = p.match(attrName)
            if match:
                return c, match

        return None, None


    def appendLogMessage(self, msg):
        if self.msgCollector is None:
            raise InternalError(u"Calling AttributeChecker.appendLogMessage "
                    u"while outside of checkPage")
        
        self.msgCollector.append(msg)


    def initiateCheckPage(self, wikiPage):
        with wikiPage.getTextOperationLock():
            s, u = wikiPage.getDirty()
            if u:
                # Otherwise, updating and an "updated wiki page" event will
                # follow, so listen for it.
                wikiPage.getMiscEvent().addListener(self)
                return 

        # TODO: Not completely threadsafe

        # if page needs no update, check it directly
        self.checkPage(wikiPage)


    def miscEventHappened(self, miscevt):
        src = miscevt.getSource()
        if isinstance(src, WikiPage):
            # Event from wiki document aka wiki data manager
            if miscevt.has_key("updated wiki page"):
                src.getMiscEvent().removeListener(self)
                self.checkPage(src)


    def checkPage(self, wikiPage):
        """
        Check attributes for a given page and page ast and fill
        log window with messages if necessary
        """
        if wikiPage.isInvalid():
            return

        foundAttrs = set()
        wikiWord = wikiPage.getWikiWord()
        pageAst = wikiPage.getLivePageAstIfAvailable()
        if pageAst is None:
            return

        attrNodes = wikiPage.extractAttributeNodesFromPageAst(pageAst)

        self._beginPageCheck(wikiPage, pageAst)
        try:
            self.msgCollector = []

            for node in attrNodes:
                for attrTuple in node.attrs:
                    attrKey, attrValue = attrTuple

                    if attrTuple in foundAttrs:
                        msg = LogMessage(self.mainControl, LogMessage.SEVERITY_HINT,
                                _(u"Same attribute twice: [%s: %s]") % attrTuple,
                                wikiWord, wikiWord,
                                (node.pos, node.pos + node.strLength))
                        self.appendLogMessage(msg)
                        continue # if first attribute had messages there's no need to repeat them

                    foundAttrs.add(attrTuple)

                    c, match = self.findCheckObject(attrKey)
                    if c is not None:                
                        c.checkEntry(attrKey, attrValue, foundAttrs, node.pos,
                                node.pos + node.strLength, match)

            callInMainThreadAsync(self.mainControl.getLogWindow().updateForWikiWord,
                    wikiWord, self.msgCollector)
        except:
            pass
        finally:
            self._endPageCheck()
            self.msgCollector = None



