"""
GUI support and error checking for handling attributes (=properties)
"""




import traceback

import re as _re # import pwiki.srePersistent as reimport pwiki.srePersistent as _re

import wx

from .wxHelper import *

from .WikiExceptions import *

from .Utilities import callInMainThreadAsync

from . import StringOps

from .LogWindow import LogMessage

from .DocPages import WikiPage


ATTRIBUTES_WITH_WIKIWORD_VALUES = [u'template', u'parent', u'import_scripts']

wxWIN95 = 20   # For wx.GetOsVersion(), this includes also Win 98 and ME

_COLORS = [
    N_("AQUAMARINE"),
    N_("BLACK"),
    N_("BLUE VIOLET"),
    N_("BLUE"),
    N_("BROWN"),
    N_("CADET BLUE"),
    N_("CORAL"),
    N_("CORNFLOWER BLUE"),
    N_("CYAN"),
    N_("DARK GREEN"),
    N_("DARK GREY"),
    N_("DARK OLIVE GREEN"),
    N_("DARK ORCHID"),
    N_("DARK SLATE BLUE"),
    N_("DARK SLATE GREY"),
    N_("DARK TURQUOISE"),
    N_("DIM GREY"),
    N_("FIREBRICK"),
    N_("FOREST GREEN"),
    N_("GOLD"),
    N_("GOLDENROD"),
    N_("GREEN YELLOW"),
    N_("GREEN"),
    N_("GREY"),
    N_("INDIAN RED"),
    N_("KHAKI"),
    N_("LIGHT BLUE"),
    N_("LIGHT GREY"),
    N_("LIGHT STEEL BLUE"),
    N_("LIME GREEN"),
    N_("MAGENTA"),
    N_("MAROON"),
    N_("MEDIUM AQUAMARINE"),
    N_("MEDIUM BLUE"),
    N_("MEDIUM FOREST GREEN"),
    N_("MEDIUM GOLDENROD"),
    N_("MEDIUM ORCHID"),
    N_("MEDIUM SEA GREEN"),
    N_("MEDIUM SLATE BLUE"),
    N_("MEDIUM SPRING GREEN"),
    N_("MEDIUM TURQUOISE"),
    N_("MEDIUM VIOLET RED"),
    N_("MIDNIGHT BLUE"),
    N_("NAVY"),
    N_("ORANGE RED"),
    N_("ORANGE"),
    N_("ORCHID"),
    N_("PALE GREEN"),
    N_("PINK"),
    N_("PLUM"),
    N_("PURPLE"),
    N_("RED"),
    N_("SALMON"),
    N_("SEA GREEN"),
    N_("SIENNA"),
    N_("SKY BLUE"),
    N_("SLATE BLUE"),
    N_("SPRING GREEN"),
    N_("STEEL BLUE"),
    N_("TAN"),
    N_("THISTLE"),
    N_("TURQUOISE"),
    N_("VIOLET RED"),
    N_("VIOLET"),
    N_("WHEAT"),
    N_("WHITE"),
    N_("YELLOW GREEN"),
    N_("YELLOW")
]


_BUILTINS = {
    "alias": None,
    "auto_link": ("off", "relax"),
    "bgcolor": _COLORS,
    "bold": ("true", "false"),
    "camelCaseWordsEnabled": ("false", "true"),
    "child_sort_order": ("ascending", "descending", "mod_oldest",
            "mod_newest", "unsorted", "natural"),
    "color": _COLORS,
    "export": ("false",),
    "font": None, # Special handling

    "global.auto_link": ("off", "relax"),
    "global.camelCaseWordsEnabled": ("false", "true"),
    "global.child_sort_order": ("ascending", "descending", "mod_oldest",
            "mod_newest", "unsorted", "natural"),
    "global.font": None, # Special handling
    "global.html.linkcolor": None,
    "global.html.alinkcolor": None,
    "global.html.vlinkcolor": None,
    "global.html.textcolor": None,
    "global.html.bgcolor": None,
    "global.html.bgimage": None,
    "global.import_scripts": None,
    "global.language": None, # TODO: special handling
    "global.paragraph_mode": ("true", "false"),
    "global.template": None,
    "global.template_head": ("auto", "manual"),
    "global.view_pane": ("off", "editor", "preview"),
    "global.wrap_type": ("word", "char"),


    "html.linkcolor": None,
    "html.alinkcolor": None,
    "html.vlinkcolor": None,
    "html.textcolor": None,
    "html.bgcolor": None,
    "html.bgimage": None,
    "icon": None,   # Special handling
    "import_scripts": None,
    "importance": ("high", "low"),
    "language": None, # TODO: special handling
    "pagetype": ("form",),
    "priority": ("1", "2", "3", "4", "5"),
    "paragraph_mode": ("true", "false"),
    "short_hint": None,
    "template": None,
    "template_head": ("auto", "manual"),
    "tree_position": None,
    "view_pane": ("off", "editor", "preview"),
    "wrap_type": ("word", "char"),

    "parent": None,
}


def getBuiltinKeys():
    return list(_BUILTINS.keys())


def getBuiltinValuesForKey(attrKey):
    # Handle exceptions here
    if attrKey == "icon":
        return list(wx.GetApp().getIconCache().iconLookupCache.keys())
    elif attrKey == "font" or attrKey == "global.font":
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
    iconsMenu.AppendSubMenu(iconsMenu1, 'A-C')
    iconsMenu2 = wx.Menu()
    iconsMenu.AppendSubMenu(iconsMenu2, 'D-F')
    iconsMenu3 = wx.Menu()
    iconsMenu.AppendSubMenu(iconsMenu3, 'G-L')
    iconsMenu4 = wx.Menu()
    iconsMenu.AppendSubMenu(iconsMenu4, 'M-P')
    iconsMenu5 = wx.Menu()
    iconsMenu.AppendSubMenu(iconsMenu5, 'Q-S')
    iconsMenu6 = wx.Menu()
    iconsMenu.AppendSubMenu(iconsMenu6, 'T-Z')

    icons = list(iconCache.iconLookupCache.keys());  # TODO: Create function?
    icons.sort()    # TODO sort with collator

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

        menuID = wx.NewId()
        iconMap[menuID] = icname

        menuItem = wx.MenuItem(iconsSubMenu, menuID, icname, icname)
        bitmap = iconCache.lookupIcon(icname)
        menuItem.SetBitmap(bitmap)
        iconsSubMenu.Append(menuItem)

    return (iconsMenu, iconMap)



def buildColorsSubmenu():
    """
    Returns tuple (color sub menu, dict from menu id to color name)
    """
    colorMap = {}
    colorsMenu = wx.Menu()

    colorsMenu1 = wx.Menu()
    colorsMenu.AppendSubMenu(colorsMenu1, 'A-L')
    colorsMenu2 = wx.Menu()
    colorsMenu.AppendSubMenu(colorsMenu2, 'M-Z')
    
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
        
        cl = wx.Colour(cn)

        menuItem.SetBackgroundColour(cl)

        # if color is dark, text should be white
        #   (checking green component seems to be enough)
        if cl.Green() < 128:
            menuItem.SetTextColour(wx.WHITE)

        colorsSubMenu.Append(menuItem)

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
        return _re.compile(r"^parent$", _re.DOTALL | _re.UNICODE | _re.MULTILINE)

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

        try:
            targetWikiWord = langHelper.resolveWikiWordLink(attrValue,
                                                            self.wikiPage)
        except ValueError:
            targetWikiWord = None

        if not wikiDocument.isDefinedWikiLinkTerm(targetWikiWord):
            # Word does not exist
#             print (attrName, attrValue), wikiWord, wikiWord, (start, end)
            msg = LogMessage(self.mainControl, LogMessage.SEVERITY_WARNING,
                    _("Parent wikiword does not exist: "
                    "[%s: %s]") %
                    (attrName, attrValue), wikiWord, wikiWord, (start, end))
            self.attrChecker.appendLogMessage(msg)
            return

        # Doesn't seem to work in endPageCheck()
        if len(self.foundAttributes) > 1:
            wikiWord = self.wikiPage.getWikiWord()
            for attr in self.foundAttributes: 
                msg = LogMessage(self.mainControl, LogMessage.SEVERITY_WARNING,
                        _("Multiple parent attributes found on page: "
                        "[%s: %s]") %
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
        return _re.compile(r"^alias$", _re.DOTALL | _re.UNICODE | _re.MULTILINE)

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
                    _("Alias value isn't a valid wikiword: [%s: %s], %s") %
                    (attrName, attrValue, errMsg), wikiWord, wikiWord,
                    (start, end))
            self.attrChecker.appendLogMessage(msg)
            return

        try:
            targetWikiWord = langHelper.resolveWikiWordLink(attrValue,
                                                            self.wikiPage)
        except ValueError:
            targetWikiWord = None

        if wikiDocument.isDefinedWikiPageName(targetWikiWord):
            # Word exists and isn't an alias
            msg = LogMessage(self.mainControl, LogMessage.SEVERITY_WARNING,
                    _("A real wikiword with the alias name exists already: "
                    "[%s: %s]") %
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
        return _re.compile(r"^(?:global\.)?template$", _re.DOTALL | _re.UNICODE | _re.MULTILINE)

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
                    _("Template value isn't a valid wikiword: [%s: %s], %s") %
                    (attrName, attrValue, errMsg), wikiWord, wikiWord,
                    (start, end))
            self.attrChecker.appendLogMessage(msg)
            return

        try:
            targetWikiWord = langHelper.resolveWikiWordLink(attrValue,
                                                            self.wikiPage)
        except ValueError:
            targetWikiWord = None

        if not wikiDocument.isDefinedWikiLinkTerm(targetWikiWord):
            # Word doesn't exist
            msg = LogMessage(self.mainControl, LogMessage.SEVERITY_WARNING,
                    _("Template value isn't an existing wikiword: "
                    "[%s: %s]") %
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
        return _re.compile(r"^(?:global\..*?\.)?(icon|color|bold)$",
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
                    _("The attribute %s was already set differently on this page") %
                    (attrName,), wikiWord, wikiWord, (start, end))
            self.attrChecker.appendLogMessage(msg)
        else:
            self.foundEntryNames.add(attrName)
            
        # Check for double entries on other pages for global.* attrs
        wikiData = self.mainControl.getWikiData()
        if attrName.startswith("global"):
            words = wikiData.getWordsForAttributeName(attrName)
            if len(words) > 1 or (len(words) > 0 and words[0] != wikiWord):
                msg = LogMessage(self.mainControl, LogMessage.SEVERITY_WARNING,
                        _("Attribute '%s' is already defined on the wiki page(s): %s") %
                        (attrName, "; ".join(words)), wikiWord, wikiWord,
                        (start, end))
                self.attrChecker.appendLogMessage(msg)

        # Check if value is a valid name for icon/color
        if attrName.endswith("icon"):
            if self.mainControl.lookupIconIndex(attrValue) == -1:
                msg = LogMessage(self.mainControl, LogMessage.SEVERITY_HINT,
                        _("Icon name doesn't exist: [%s: %s]") %
                        (attrName, attrValue), wikiWord, wikiWord, (start, end))
                self.attrChecker.appendLogMessage(msg)
        elif attrName.endswith("color"):
#             if attrValue.upper() not in _COLORS:
            if StringOps.colorDescToRgbTuple(attrValue) is None:
                msg = LogMessage(self.mainControl, LogMessage.SEVERITY_HINT,
                        _("Color name doesn't exist: [%s: %s]") %
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
        return _re.compile(r"^global\.graph\.relations\.include$",
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
                    _("The attribute 'global.graph.relations.exclude' (e.g. on page '%s') "
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
            raise InternalError("Calling AttributeChecker.appendLogMessage "
                    "while outside of checkPage")
        
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
            if "updated wiki page" in miscevt:
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
                                _("Same attribute twice: [%s: %s]") % attrTuple,
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



