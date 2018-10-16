import traceback, time
from calendar import timegm

import wx

from ..rtlibRepl import minidom

import Consts

from ..MiscEvent import KeyFunctionSink, MiscEventSourceMixin

from ..StringOps import formatTimeT

from ..Serialization import serToXmlUnicode, serFromXmlUnicode, serToXmlInt, \
        serFromXmlInt, iterXmlElementFlat

from .. import DocPages


DAMAGED = object()

class HistoryEntry:
    __slots__ = ("visitedTimeStamp", "unifiedPageName",
            "xmlNode")

    def __init__(self, unifiedPageName=None):

        self.unifiedPageName = unifiedPageName
        self.visitedTimeStamp = time.time()
        self.xmlNode = None


    def getFormattedVisitedDate(self, formatStr):
        return formatTimeT(formatStr, self.visitedTimeStamp)


    def serializeToXmlProd(self, xmlDoc):
        """
        Create XML node to contain all information
        """
        xmlNode = self.xmlNode
        if xmlNode is None:
            xmlNode = xmlDoc.createElement("historyEntry")

        self.serializeToXml(xmlNode, xmlDoc)
        
        return xmlNode


    def serializeToXml(self, xmlNode, xmlDoc):
        """
        Create XML node to contain all information
        about this object.
        """
        serToXmlUnicode(xmlNode, xmlDoc, "unifiedName", self.unifiedPageName,
                    replace=True)

        serToXmlUnicode(xmlNode, xmlDoc, "visitedTime", str(time.strftime(
                "%Y-%m-%d/%H:%M:%S", time.gmtime(self.visitedTimeStamp))),
                replace=True)



    def serializeFromXml(self, xmlNode):
        """
        Set object state from data in xmlNode)
        """
        self.xmlNode = xmlNode

        self.unifiedPageName = serFromXmlUnicode(xmlNode, "unifiedName")

        timeStr = serFromXmlUnicode(xmlNode, "visitedTime")
        self.visitedTimeStamp = timegm(time.strptime(timeStr,
                "%Y-%m-%d/%H:%M:%S"))


    def getUnifiedPageName(self):
        return self.unifiedPageName


    def getHrPageName(self):
        if self.unifiedPageName.startswith("wikipage/"):
            return self.unifiedPageName[9:]
        else:
            return "<" + DocPages.getHrNameForFuncTag(self.unifiedPageName)\
                    + ">"





class WikiWideHistory(MiscEventSourceMixin):
    """
    Represents the history of visited wikiwords independent of particular page.
    """

    def __init__(self, wikiDocument):
        MiscEventSourceMixin.__init__(self)

        self.historyEntries = []
        self.wikiDocument = wikiDocument
        self.xmlNode = None

#         self.mainControlSink = KeyFunctionSink((
#                 ("opened wiki", self.onOpenedWiki),
#         ))
#         
#         self.docPagePresenter = docPagePresenter
# 
#         self.docPPresenterSink = KeyFunctionSink((
#                 ("loaded current doc page", self.onLoadedCurrentDocPage),
#         ))

        self.__sinkWikiDoc = KeyFunctionSink((
                ("deleted wiki page", self.onDeletedWikiPage),
                ("pseudo-deleted wiki page", self.onDeletedWikiPage),
                ("renamed wiki page", self.onRenamedWikiPage),
                ("visited doc page", self.onVisitedDocPage),
                ("changed configuration", self.onChangedConfiguration)
        ))


        # Register for events
#         self.mainControl.getMiscEvent().addListener(self.mainControlSink, False)
        
#         self.docPagePresenter.getMiscEvent().addListener(
#                 self.docPPresenterSink, False)

        self.wikiDocument.getMiscEvent().addListener(self.__sinkWikiDoc)

##                 ("saving current page", self.savingCurrentWikiPage)



    def close(self):
        self.wikiDocument.getMiscEvent().removeListener(self.__sinkWikiDoc)


    def getHistoryEntries(self):
        return self.historyEntries


    def onChangedConfiguration(self, miscevt):
        self.limitEntries()
        self.fireMiscEventKeys(("changed wiki wide history",))


    def limitEntries(self):
        limit = self.wikiDocument.getWikiConfig().getint("main",
                "wikiWideHistory_maxEntries", 100)
                
        while len(self.historyEntries) > limit:
            self.historyEntries.pop(0)


    def onVisitedDocPage(self, miscevt):
        if not miscevt.get("addToHistory", True):
            return

        docPage = miscevt.get("docPage")
        if docPage is None:
            return

        if isinstance(docPage, DocPages.AliasWikiPage):
            docPage = docPage.getNonAliasPage()

        upname = docPage.getUnifiedPageName()
        
        if not upname.startswith("wikipage/") and \
                not DocPages.isFuncTag(upname):
            # Page is neither a wiki page nor a standard functional page
            return

        self.historyEntries.append(HistoryEntry(upname))

        self.limitEntries()
        self.fireMiscEventKeys(("changed wiki wide history",))


    def clearAll(self):
        self.historyEntries = []
        self.fireMiscEventKeys(("changed wiki wide history",))


    def onDeletedWikiPage(self, miscevt):
        """
        Remove deleted word from history
        """
        upname = "wikipage/" + miscevt.get("wikiPage").getWikiWord() # self.mainControl.getCurrentWikiWord()
        
        # print "onDeletedWikiPage1",  self.pos, repr(self.historyEntries)

        self.historyEntries = [w for w in self.historyEntries
                if w.unifiedPageName != upname]
                
        self.fireMiscEventKeys(("changed wiki wide history",))


    def onRenamedWikiPage(self, miscevt):
        """
        Rename word in history
        """
        oldUpname = "wikipage/" + miscevt.get("wikiPage").getWikiWord()
        newUpname = "wikipage/" + miscevt.get("newWord")
        
        for i in range(len(self.historyEntries)):
            if self.historyEntries[i].unifiedPageName == oldUpname:
                self.historyEntries[i].unifiedPageName = newUpname
                
        self.fireMiscEventKeys(("changed wiki wide history",))


    def readOverviewFromBytes(self, content):
        """
        Read overview from bytestring content. Needed to handle multi-page text
        imports.
        """
        try:
            if content is None:
                self.historyEntries = []
                self.xmlNode = None
                return
    
            xmlDoc = minidom.parseString(content)
            xmlNode = xmlDoc.firstChild
            self.serializeFromXml(xmlNode)
        except:
            traceback.print_exc()
            self.historyEntries = []
            self.xmlNode = None


    def readOverview(self):
        """
        Read and decode overview from database. Most functions can be called
        only after this was called (exception: isNotInDatabase())
        """
        unifName = "wikiwidehistory"

        content = self.wikiDocument.retrieveDataBlock(unifName, default=DAMAGED)
        if content is DAMAGED:
            self.historyEntries = []
            self.xmlNode = None
            return

        self.readOverviewFromBytes(content)

        self.fireMiscEventKeys(("reread wiki wide history",
                "changed wiki wide history"))


    def writeOverview(self):
        unifName = "wikiwidehistory"

        if len(self.historyEntries) == 0:
            self.wikiDocument.deleteDataBlock(unifName)
            return

        xmlDoc = minidom.getDOMImplementation().createDocument(None, None, None)
        xmlNode = self.serializeToXmlProd(xmlDoc)

        xmlDoc.appendChild(xmlNode)
        content = xmlDoc.toxml("utf-8")

        self.wikiDocument.storeDataBlock(unifName, content,
                storeHint=Consts.DATABLOCK_STOREHINT_INTERN)


    def serializeToXmlProd(self, xmlDoc):
        """
        Create XML node to contain all information about this object.
        """
        xmlNode = self.xmlNode
        if xmlNode is None:
            xmlNode = xmlDoc.createElement("wikiWideHistory")

        self.serializeToXml(xmlNode, xmlDoc)

        return xmlNode


    def serializeToXml(self, xmlNode, xmlDoc):
        """
        Modify XML node to contain all information about this object.
        """
        xmlNode.setAttribute("formatVersion", "0")
        xmlNode.setAttribute("readCompatVersion", "0")
        xmlNode.setAttribute("writeCompatVersion", "0")

        for xmlEntry in iterXmlElementFlat(xmlNode, "historyEntry"):
            xmlNode.removeChild(xmlEntry)

        for entry in self.historyEntries:
            entryNode = entry.serializeToXmlProd(xmlDoc)
            xmlNode.appendChild(entryNode)


    def serializeFromXml(self, xmlNode):
        """
        Set object state from data in xmlNode.
        """
        formatVer = int(xmlNode.getAttribute("writeCompatVersion"))
        
        self.xmlNode = xmlNode

        if formatVer != 0:
            self.historyEntries = []
            return
            
#             SerializationException("Wrong version no. %s for wiki-wide history" %
#                     formatVer)

        historyEntries = []

        for xmlEntry in iterXmlElementFlat(xmlNode, "historyEntry"):
            entry = HistoryEntry()
            entry.serializeFromXml(xmlEntry)
            
            historyEntries.append(entry)

        self.historyEntries = historyEntries



