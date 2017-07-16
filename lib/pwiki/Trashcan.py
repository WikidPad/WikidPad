"""
"""

import time, zlib, re
from calendar import timegm

from .rtlibRepl import minidom

import wx

from .WikiExceptions import *
import Consts

from .MiscEvent import MiscEventSourceMixin, KeyFunctionSink

from . import Exporters, Serialization

from . import StringOps

# from ..StringOps import applyBinCompact, getBinCompactForDiff, \
#         fileContentToUnicode, BOM_UTF8, formatWxDate
# 
# from ..Serialization import serToXmlUnicode, serFromXmlUnicode, serToXmlInt, \
#         serFromXmlInt, iterXmlElementFlat
# 
# from ..DocPages import AbstractWikiPage



DAMAGED = object()


class TrashBag:
    """
    A trash bag contains all parts of a wikiword, wikipage content itself and
    dependent datablocks (e.g. old versions). It provides also a small subset
    of WikiData API to allow read-only access to the items in the bag.
    """
    __slots__ = ("trashcan", "trashTimeStamp", "bagId",
            "contentStorageMode", "originalUnifiedName", "xmlNode")

    def __init__(self, trashcan):   # , contentStorageMode = u"single"
        self.trashcan = trashcan
        self.trashTimeStamp = time.time()

        self.bagId = 0 # Invalid, numbers start with 1
#         self.contentStorageMode = contentStorageMode

        # Unified name of main content before it was trashed.
        # Normally this is a "wikipage/..." but the trash bag can contain
        # additional items
        self.originalUnifiedName = None

        self.xmlNode = None


    def getTrashcan(self):
        return self.trashcan


    def getFormattedTrashDate(self, formatStr):
        return StringOps.formatWxDate(formatStr, wx.DateTimeFromTimeT(
                self.trashTimeStamp))


    def serializeOverviewToXmlProd(self, xmlDoc):
        """
        Create XML node to contain all overview information (not content)
        about this object.
        """
        xmlNode = self.xmlNode
        if xmlNode is None:
            xmlNode = xmlDoc.createElement("trashBag")

        self.serializeOverviewToXml(xmlNode, xmlDoc)

        return xmlNode


    def serializeOverviewToXml(self, xmlNode, xmlDoc):
        """
        Create XML node to contain all overview information (not content)
        about this object.
        """
        Serialization.serToXmlInt(xmlNode, xmlDoc, "bagId", self.bagId,
                replace=True)

        Serialization.serToXmlUnicode(xmlNode, xmlDoc, "originalUnifiedName",
                self.originalUnifiedName, replace=True)

        Serialization.serToXmlUnicode(xmlNode, xmlDoc, "trashTime", str(time.strftime(
                "%Y-%m-%d/%H:%M:%S", time.gmtime(self.trashTimeStamp))),
                replace=True)


#         Serialization.serToXmlUnicode(xmlNode, xmlDoc, u"contentStorageMode",
#                 self.contentStorageMode, replace=True)


    def serializeOverviewFromXml(self, xmlNode):
        """
        Set object state from data in xmlNode)
        """
        self.xmlNode = xmlNode

        self.bagId = Serialization.serFromXmlInt(xmlNode, "bagId")

        self.originalUnifiedName = Serialization.serFromXmlUnicode(xmlNode,
                "originalUnifiedName")

        timeStr = Serialization.serFromXmlUnicode(xmlNode, "trashTime")
        self.trashTimeStamp = timegm(time.strptime(timeStr,
                "%Y-%m-%d/%H:%M:%S"))


    def getPacketUnifiedName(self):
        if self.bagId == 0:
            return None
        else:
            return "trashcan/trashBag/packet/bagId/%s" % self.bagId


    def getPacketData(self):
        unifName = self.getPacketUnifiedName()
        if unifName is None:
            return None

        return self.trashcan.getWikiDocument().retrieveDataBlock(unifName, None)
 
    def deletePacket(self):
        """
        Delete associated packet (if any). Should only be called from Trashcan
        """
        unifName = self.getPacketUnifiedName()
        if unifName is None:
            return
        
        self.trashcan.getWikiDocument().deleteDataBlock(unifName)
        self.bagId = 0



class Trashcan(MiscEventSourceMixin):
    def __init__(self, wikiDocument):
        MiscEventSourceMixin.__init__(self)

        self.wikiDocument = wikiDocument
        self.trashBags = []
        self.trashBagIds = set()
        
        self.xmlNode = None

        self.__sinkWikiDoc = KeyFunctionSink((
                ("changed wiki configuration", self.onChangedWikiConfiguration),
        ))

        self.wikiDocument.getMiscEvent().addListener(self.__sinkWikiDoc)


    def getWikiDocument(self):
        return self.wikiDocument


    def close(self):
        self.wikiDocument.getMiscEvent().removeListener(self.__sinkWikiDoc)


    def isInDatabase(self):
        """
        Can be called before readOverview() to check if the version overview
        is already in database.
        """
        unifName = "trashcan/overview"
        return self.wikiDocument.retrieveDataBlock(unifName) is not None


    def onChangedWikiConfiguration(self, miscEvt):
        self._removeOldest()


    def _removeOldest(self):
        """
        Remove oldest trashbags if there are more in the can than configuration
        setting allows
        """
        remCount = len(self.trashBags) - self.wikiDocument.getWikiConfig()\
                .getint("main", "trashcan_maxNoOfBags", 200)

        if remCount <= 0:
            return

        for bag in self.trashBags[:remCount]:
            self.trashBagIds.discard(bag.bagId)
        
        del self.trashBags[:remCount]
        

    def _addTrashBag(self, trashBag):
        """
        Adds bag to trashcan. Also checks if there are too many bags according
        to settings and removes the oldest one(s). The bag must already have a
        unique bagId
        """
        assert trashBag.bagId > 0

        self.trashBags.append(trashBag)
        self.trashBagIds.add(trashBag.bagId)
        self._removeOldest()
        self.writeOverview()


    def storeWikiWord(self, word):
        """
        Store wikiword (including versions) in a trash bag and return bag id
        """
        bag = TrashBag(self)

        for bagId in range(1, len(self.trashBagIds) + 2):
            if not bagId in self.trashBagIds:
                break
        else:
            raise InternalError("Trashcan: No free bagId???")

        bag.bagId = bagId

        data = Exporters.getSingleWikiWordPacket(self.wikiDocument, word)
        self.wikiDocument.storeDataBlock(bag.getPacketUnifiedName(),
                data, storeHint=self.getStorageHint())

        bag.originalUnifiedName = "wikipage/" + word
        self._addTrashBag(bag)

        return bagId

    def deleteBag(self, bag):
        """
        Deletes bag from trashcan. Only the bagId of the  bag  parameter
        is used so to delete a bag with a particular bagId just create
        a "fake" bag and set bagId accordingly.
        """
        bagId = bag.bagId
        if bag.bagId == 0:
            return

        for i, tb in enumerate(self.trashBags):
            if tb.bagId == bagId:
                del self.trashBags[i]
                self.trashBagIds.discard(bagId)
                tb.deletePacket()
                return


    def readOverview(self):
        """
        Read and decode overview from database. Most functions can be called
        only after this was called (exception: isInDatabase())
        """
        unifName = "trashcan/overview"

        content = self.wikiDocument.retrieveDataBlock(unifName, default=DAMAGED)
        if content is DAMAGED:
            raise Exception(_("Trashcan data damaged"))   # TODO: Specific exception
        elif content is None:
            self.trashBags = []
            self.trashBagIds = set()
            self.xmlNode = None
            return

        xmlDoc = minidom.parseString(content)
        xmlNode = xmlDoc.firstChild
        self.serializeFromXml(xmlNode)


#     def getDependentDataBlocks(self):
#         assert not self.isInvalid()
# 
#         unifiedPageName = self.basePage.getUnifiedPageName()
# 
#         result = [u"versioning/overview/" + unifiedPageName]
# 
#         for entry in self.versionEntries:
#             result.append(u"versioning/packet/versionNo/%s/%s" % (entry.versionNumber,
#                 unifiedPageName))
# 
#         return result




    @staticmethod
    def deleteBrokenData(wikiDocument):
        """
        Delete all trashcan data in case existing data is broken and can't
        be deleted in regular ways.
        """
        dataBlocks = wikiDocument.getDataBlockUnifNamesStartingWith(
                "trashcan/")

        for db in dataBlocks:
            wikiDocument.deleteDataBlock(db)


    def writeOverview(self):
        unifName = "trashcan/overview"

        if len(self.trashBags) == 0:
            self.wikiDocument.deleteDataBlock(unifName)
            return

        xmlDoc = minidom.getDOMImplementation().createDocument(None, None, None)
        xmlNode = self.serializeToXmlProd(xmlDoc)

        xmlDoc.appendChild(xmlNode)
        content = xmlDoc.toxml("utf-8")

        self.wikiDocument.storeDataBlock(unifName, content,
                storeHint=self.getStorageHint())


    def clear(self):
        """
        Delete all data from trashcan (called when user empties trashcan)
        """
        self.trashBags = []
        self.trashBagIds = set()
        
        self.xmlNode = None
        self.deleteBrokenData(self.wikiDocument)


    def getTrashBags(self):
        return self.trashBags
        

    def getStorageHint(self):
        """
        Return appropriate storage hint according to option settings.
        """
        if self.wikiDocument.getWikiConfig().getint("main",
                "trashcan_storageLocation", 0) != 1:
            return Consts.DATABLOCK_STOREHINT_INTERN
        else:
            return Consts.DATABLOCK_STOREHINT_EXTERN


#     @staticmethod
#     def decodeContent(encContent, encoding):
#         if encoding is None:
#             return encContent
#         if encoding == "zlib":
#             return zlib.decompress(encContent)
# 
#     @staticmethod
#     def encodeContent(content, encoding):
#         if encoding is None:
#             return content
#         if encoding == "zlib":
#             return zlib.compress(content)


    def serializeToXmlProd(self, xmlDoc):
        """
        Create XML node to contain all information about this object.
        """
        xmlNode = self.xmlNode
        if xmlNode is None:
            xmlNode = xmlDoc.createElement("trashcanOverview")

        self.serializeToXml(xmlNode, xmlDoc)
        
        return xmlNode


    def serializeToXml(self, xmlNode, xmlDoc):
        """
        Modify XML node to contain all information about this object.
        """
        xmlNode.setAttribute("formatVersion", "0")
        xmlNode.setAttribute("readCompatVersion", "0")
        xmlNode.setAttribute("writeCompatVersion", "0")

        for xmlEntry in Serialization.iterXmlElementFlat(xmlNode, "trashBag"):
            xmlNode.removeChild(xmlEntry)

        for entry in self.trashBags:
            entryNode = entry.serializeOverviewToXmlProd(xmlDoc)
            xmlNode.appendChild(entryNode)


    def serializeFromXml(self, xmlNode):
        """
        Set object state from data in xmlNode.
        """
        formatVer = int(xmlNode.getAttribute("writeCompatVersion"))
        if formatVer > 0:
            SerializationException("Wrong version no. %s for trashcan overview" %
                    formatVer)

        self.xmlNode = xmlNode

        trashBags = []
        trashBagIds = set()

        for xmlEntry in Serialization.iterXmlElementFlat(xmlNode, "trashBag"):
            entry = TrashBag(self)
            entry.serializeOverviewFromXml(xmlEntry)

            trashBags.append(entry)
            trashBagIds.add(entry.bagId)

        # Order trash bags by trash date
        trashBags.sort(key=lambda entry: entry.trashTimeStamp)

        self.trashBags = trashBags
        self.trashBagIds = trashBagIds


#     def getVersionContentRaw(self, versionNumber):
#         if len(self.trashBags) == 0:
#             raise InternalError(u"Tried to retrieve non-existing "
#                     u"version number %s from empty list." % versionNumber)
# 
#         if versionNumber == -1:
#             versionNumber = self.trashBags[-1].versionNumber
# 
#         base = None
#         workList = []
#         for i in range(len(self.trashBags) - 1, -1, -1):
#             entry = self.trashBags[i]
#             if entry.contentDifferencing == u"complete":
#                 workList = []
#                 base = entry
#             else:
#                 workList.append(entry)
# 
#             if entry.versionNumber == versionNumber:
#                 break
#         else:
#             raise InternalError(u"Tried to retrieve non-existing "
#                     u"version number %s." % versionNumber)
# 
#         if base is None:
#             raise InternalError(u"No base version found for getVersionContent(%s)" %
#                     versionNumber)
# 
#         unifName = u"versioning/packet/versionNo/%s/%s" % (base.versionNumber,
#                 self.basePage.getUnifiedPageName())
# 
#         content = self.wikiDocument.retrieveDataBlock(unifName, default=DAMAGED)
#         if content is DAMAGED:
#             raise VersioningException(_(u"Versioning data damaged"))
#         elif content is None:
#             raise InternalError(u"Tried to retrieve non-existing "
#                     u"packet for version number %s" % versionNumber)
# 
#         content = self.decodeContent(content, entry.contentEncoding)
# 
#         for entry in workList:
#             unifName = u"versioning/packet/versionNo/%s/%s" % (entry.versionNumber,
#                     self.basePage.getUnifiedPageName())
#             packet = self.wikiDocument.retrieveDataBlock(unifName, default=None)
#             if content is DAMAGED:
#                 raise VersioningException(_(u"Versioning data damaged"))
#             elif content is None:
#                 raise InternalError(u"Tried to retrieve non-existing "
#                         u"packet for version number %s" % versionNumber)
# 
# 
#             content = applyBinCompact(content, packet)
# 
#         return content
# 
# 
#     def getVersionContent(self, versionNumber):
#         return fileContentToUnicode(self.getVersionContentRaw(versionNumber))
# 
# 
#     def addVersion(self, content, entry):
#         """
#         entry.versionNumber is assumed invalid and will be filled by this function.
#         """
#         if isinstance(content, unicode):
#             content = BOM_UTF8 + content.encode("utf-8")
#         assert isinstance(content, str)
# 
#         completeStep = max(self.wikiDocument.getWikiConfig().getint("main",
#                 "versioning_completeSteps", 10), 0)
# 
#         if completeStep == 0:
#             asRevDiff = True
#         else:
#             if len(self.trashBags) < completeStep:
#                 asRevDiff = True
#             else:
#                 asRevDiff = False
#                 for e in reversed(self.trashBags[-completeStep:-1]):
#                     if e.contentDifferencing == "complete":
#                         asRevDiff = True
#                         break
# 
#         self.maxVersionNumber += 1
#         newHeadVerNo = self.maxVersionNumber
# 
#         newHeadUnifName = u"versioning/packet/versionNo/%s/%s" % \
#                 (newHeadVerNo, self.basePage.getUnifiedPageName())
# 
#         self.wikiDocument.storeDataBlock(newHeadUnifName, content,
#                 storeHint=self.getStorageHint())
# 
#         entry.versionNumber = newHeadVerNo
#         entry.contentDifferencing = "complete"
#         entry.contentEncoding = None
#         self.trashBags.append(entry)
# 
#         if len(self.trashBags) > 1:
#             if asRevDiff:
#                 prevHeadEntry = self.trashBags[-2]
#                 prevHeadContent = self.getVersionContentRaw(prevHeadEntry.versionNumber)
# 
#                 unifName = u"versioning/packet/versionNo/%s/%s" % (prevHeadEntry.versionNumber,
#                         self.basePage.getUnifiedPageName())
#                 diffPacket = getBinCompactForDiff(content, prevHeadContent)
# 
#                 if len(diffPacket) < len(prevHeadContent):
#                     prevHeadEntry.contentDifferencing = "revdiff"
#                     prevHeadEntry.contentEncoding = None
#                     self.wikiDocument.storeDataBlock(unifName, diffPacket,
#                             storeHint=self.getStorageHint())
# 
#         self.fireMiscEventKeys(("appended version", "changed version overview"))
# 
# 
#     def deleteVersion(self, versionNumber):
#         if len(self.trashBags) == 0:
#             raise InternalError("Non-existing version %s to delete (empty list)." %
#                     versionNumber)
# 
#         if versionNumber == -1:
#             versionNumber = self.trashBags[-1].versionNumber
# 
#         if versionNumber == self.trashBags[0].versionNumber:
#             # Delete oldest
#             unifName = u"versioning/packet/versionNo/%s/%s" % (versionNumber,
#                     self.basePage.getUnifiedPageName())
# 
#             self.wikiDocument.deleteDataBlock(unifName)
#             del self.trashBags[0]
#             self.fireMiscEventKeys(("deleted version", "changed version overview"))
# 
#             return
# 
#         if versionNumber == self.trashBags[-1].versionNumber:
#             # Delete newest
# 
#             # We can assume here that len(self.trashBags) >= 2 otherwise
#             # previous "if" would have been true.
# 
#             prevHeadEntry = self.trashBags[-2]
#             newContent = self.getVersionContentRaw(prevHeadEntry.versionNumber)
#             
#             unifName = u"versioning/packet/versionNo/%s/%s" % (prevHeadEntry.versionNumber,
#                     self.basePage.getUnifiedPageName())
#             prevHeadEntry.contentDifferencing = "complete"
#             self.wikiDocument.storeDataBlock(unifName, newContent,
#                     storeHint=self.getStorageHint())
#                 
#             unifName = u"versioning/packet/versionNo/%s/%s" % (versionNumber,
#                     self.basePage.getUnifiedPageName())
#             self.wikiDocument.deleteDataBlock(unifName)
#             del self.trashBags[-1]
#             self.fireMiscEventKeys(("deleted version", "changed version overview"))
# 
#             return
# 
#         # Delete some version in-between: Not supported yet.
#         raise InternalError("In-between version %s to delete." %
#                         versionNumber)






# class WikiPageSnapshot(AbstractWikiPage):
#     def __init__(self, wikiDocument, baseWikiPage, versionNo):
#         AbstractWikiPage.__init__(self, wikiDocument, baseWikiPage.getWikiWord())
#         
#         self.baseWikiPage = baseWikiPage
#         self.versionNumber = versionNo
#         
#         self.content = self.baseWikiPage.getVersionOverview().getVersionContent(
#                 versionNo)
# 
# 
#     def getSnapshotBaseDocPage(self):
#         return self.baseWikiPage
#         
#     def getSnapshotVersionNumber(self):
#         return self.versionNumber
# 
# 
#     def getContent(self):
#         return self.content
# 
# 
#     def getUnifiedPageName(self):
#         if self.versionNumber == 0:
#             return None
#         
#         return u"versioning/version/versionNo/%s/%s" % (self.versionNumber,
#                 self.baseWikiPage.getWikiWord())
# 
# 
#     def isReadOnlyEffect(self):
#         """
#         Return true if page is effectively read-only, this means
#         "for any reason", regardless if error or intention.
#         """
#         return True
# 
# 
#     def getVersionOverview(self):
#         return self.baseWikiPage.getVersionOverview()
# 
#     def getExistingVersionOverview(self):
#         return self.baseWikiPage.getExistingVersionOverview()
# 
#     def setPresentation(self, data, startPos):
#         """
#         Set (a part of) the presentation tuple. This is silently ignored
#         if the "write access failed" or "read access failed" flags are
#         set in the wiki document.
#         data -- tuple with new presentation data
#         startPos -- start position in the presentation tuple which should be
#                 overwritten with data.
#         """
#         pass  # TODO?
