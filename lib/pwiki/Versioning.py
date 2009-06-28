"""
Processes versions of wiki pages.
"""

import time
from calendar import timegm

from xml.dom import minidom


from WikiExceptions import *
import Consts

from StringOps import applyBinCompact, getBinCompactForDiff, \
        fileContentToUnicode, BOM_UTF8

from Serialization import serToXmlUnicode, serFromXmlUnicode, serToXmlInt, \
        serFromXmlInt, iterXmlElementFlat

from DocPages import AbstractWikiPage


class VersionEntry(object):
    def __init__(self, description=None, contentCompression="revdiff"):
        self.creationTimeStamp = time.time()
        self.description = description

        # Head version has ver.no. -1
        self.versionNumber = 0
        # "complete" or reverse differential ("revdiff") content?
        self.contentCompression = contentCompression
        
        self.xmlNode = None


    def serializeOverviewToXmlProd(self, xmlDoc):
        """
        Create XML node to contain all overview information (not content)
        about this object.
        """
        xmlNode = self.xmlNode
        if xmlNode is None:
            xmlNode = xmlDoc.createElement(u"versionOverviewEntry")

        self.serializeOverviewToXml(xmlNode, xmlDoc)
        
        return xmlNode


    def serializeOverviewToXml(self, xmlNode, xmlDoc):
        """
        Create XML node to contain all overview information (not content)
        about this object.
        """
        xmlNode.setAttribute(u"formatVersion", u"0")
        xmlNode.setAttribute(u"readCompatVersion", u"0")
        xmlNode.setAttribute(u"writeCompatVersion", u"0")

        serToXmlUnicode(xmlNode, xmlDoc, u"creationTime", unicode(time.strftime(
                "%Y-%m-%d/%H:%M:%S", time.gmtime(self.creationTimeStamp))),
                replace=True)

        if self.description is not None:
            serToXmlUnicode(xmlNode, xmlDoc, u"description", self.description,
                    replace=True)

        serToXmlInt(xmlNode, xmlDoc, "versionNumber", self.versionNumber,
                replace=True)
        
        serToXmlUnicode(xmlNode, xmlDoc, u"contentCompression",
                self.contentCompression, replace=True)



    def serializeOverviewFromXml(self, xmlNode):
        """
        Set object state from data in xmlNode)
        """
        formatVer = int(xmlNode.getAttribute(u"writeCompatVersion"))
        if formatVer != 0:
            SerializationException("Wrong version no. %s for version entry" %
                    formatVer)
        
        self.xmlNode = xmlNode

        timeStr = serFromXmlUnicode(xmlNode, u"creationTime")

        self.creationTimeStamp = timegm(time.strptime(timeStr,
                "%Y-%m-%d/%H:%M:%S"))

        self.description = serFromXmlUnicode(xmlNode, u"description", None)

        self.versionNumber = serFromXmlInt(xmlNode, u"versionNumber")

        self.contentCompression = serFromXmlUnicode(xmlNode,
                u"contentCompression", u"complete")



#     def getPacketUnifiedPageName(self):
#         return u"versioning/packet/versionNo/%s/



class VersionOverview(object):
    def __init__(self, wikiDocument, unifiedPageName):
        self.wikiDocument = wikiDocument
        self.unifiedPageName = unifiedPageName
        self.versionEntries = []
        self.headVersion = None
        self.maxVersionNumber = 0
        
        self.xmlNode = None


    def isNotInDatabase(self):
        """
        Can be called before readOverview() to check if the version overview
        is already in database.
        """
        unifName = u"versioning/overview/" + self.unifiedPageName
        return self.wikiDocument.retrieveDataBlock(unifName) is None


    def readOverview(self):
        """
        Read and decode overview from database. Most functions can be called
        only after this was called (exception: isNotInDatabase())
        """
        unifName = u"versioning/overview/" + self.unifiedPageName

        content = self.wikiDocument.retrieveDataBlock(unifName)
        if content is not None:
            xmlDoc = minidom.parseString(content)
            xmlNode = xmlDoc.firstChild
            self.serializeFromXml(xmlNode)


    def renameTo(self, newUnifiedPageName):
        """
        Rename all data to newUnifiedPageName. This object becomes invalid after
        doing so, so you must retrieve a new overview for the new name.
        """
        oldUnifiedPageName = self.unifiedPageName
        worklist = self.versionEntries[:]
        if self.headVersion is not None:
            worklist += [self.headVersion]

        # First copy to new 
        for entry in worklist:
            oldUnifName = u"versioning/packet/versionNo/%s/%s" % (entry.versionNumber,
                oldUnifiedPageName)
            newUnifName = u"versioning/packet/versionNo/%s/%s" % (entry.versionNumber,
                newUnifiedPageName)

            content = self.wikiDocument.retrieveDataBlock(oldUnifName)
            self.wikiDocument.storeDataBlock(newUnifName, content,
                    storeHint=Consts.DATABLOCK_STOREHINT_EXTERN)

        self.unifiedPageName = newUnifiedPageName
        self.writeOverview()


        # Then delete old data
        for entry in worklist:
            oldUnifName = u"versioning/packet/versionNo/%s/%s" % (entry.versionNumber,
                oldUnifiedPageName)

            self.wikiDocument.deleteDataBlock(oldUnifName)

        oldUnifName = u"versioning/overview/" + oldUnifiedPageName
        self.wikiDocument.deleteDataBlock(oldUnifName)

        self.invalidate()


    def delete(self):
        """
        Delete all versioning data. This object becomes invalid after
        doing so.
        """
        worklist = self.versionEntries[:]
        if self.headVersion is not None:
            worklist += [self.headVersion]
        
        for entry in worklist:
            unifName = u"versioning/packet/versionNo/%s/%s" % (entry.versionNumber,
                self.unifiedPageName)

            self.wikiDocument.deleteDataBlock(unifName)

        unifName = u"versioning/overview/" + self.unifiedPageName
        self.wikiDocument.deleteDataBlock(unifName)

        self.invalidate()


    def writeOverview(self):
        unifName = u"versioning/overview/" + self.unifiedPageName
        
        xmlDoc = minidom.getDOMImplementation().createDocument(None, None, None)
        xmlNode = self.serializeToXmlProd(xmlDoc)

        xmlDoc.appendChild(xmlNode)
        content = xmlDoc.toxml("utf-8")

        self.wikiDocument.storeDataBlock(unifName, content,
                storeHint=Consts.DATABLOCK_STOREHINT_EXTERN)

    def invalidate(self):
        self.unifiedPageName = None
        self.wikiDocument = None

    def getVersionEntries(self):
        return self.versionEntries

    def getHeadVersion(self):
        return self.headVersion


    def serializeToXmlProd(self, xmlDoc):
        """
        Create XML node to contain all information about this object.
        """
        xmlNode = self.xmlNode
        if xmlNode is None:
            xmlNode = xmlDoc.createElement(u"versionOverview")

        self.serializeToXml(xmlNode, xmlDoc)
        
        return xmlNode


    def serializeToXml(self, xmlNode, xmlDoc):
        """
        Modify XML node to contain all information about this object.
        """
        xmlNode.setAttribute(u"formatVersion", u"0")
        xmlNode.setAttribute(u"readCompatVersion", u"0")
        xmlNode.setAttribute(u"writeCompatVersion", u"0")

        serToXmlUnicode(xmlNode, xmlDoc, u"unifiedPageName",
                self.unifiedPageName, replace=True)

        for xmlEntry in tuple(iterXmlElementFlat(xmlNode, u"versionOverviewEntry")):
            xmlNode.removeChild(xmlEntry)

        for entry in self.versionEntries:
            entryNode = entry.serializeOverviewToXmlProd(xmlDoc)
            xmlNode.appendChild(entryNode)
        
        if self.headVersion is not None:
            entryNode = self.headVersion.serializeOverviewToXmlProd(xmlDoc)
            xmlNode.appendChild(entryNode)




    def serializeFromXml(self, xmlNode):
        """
        Set object state from data in xmlNode.
        """
        formatVer = int(xmlNode.getAttribute(u"writeCompatVersion"))
        if formatVer != 0:
            SerializationException("Wrong version no. %s for version overview" %
                    formatVer)

        self.xmlNode = xmlNode
        
        if serFromXmlUnicode(xmlNode, u"unifiedPageName") != self.unifiedPageName:
            raise InternalError("Mismatch of XML UPN %s and requested UPN %s" % 
                    (serFromXmlUnicode(xmlNode, u"unifiedPageName"),
                    self.unifiedPageName))

        headVersion = None
        versionEntries = []
        maxVersionNumber = 0

        for xmlEntry in iterXmlElementFlat(xmlNode, u"versionOverviewEntry"):
            entry = VersionEntry()
            entry.serializeOverviewFromXml(xmlEntry)
            
            if entry.versionNumber == -1:
                headVersion = entry
            else:
                versionEntries.append(entry)
                maxVersionNumber = max(maxVersionNumber, entry.versionNumber)

        self.headVersion = headVersion
        self.versionEntries = versionEntries
        self.maxVersionNumber = maxVersionNumber


    def getVersionContent(self, versionNumber):
        base = self.headVersion
        workList = []
        if versionNumber != -1:
            for i in xrange(len(self.versionEntries) - 1, -1, -1):
                entry = self.versionEntries[i]
                if entry.contentCompression == "complete":
                    workList = []
                    base = entry
                else:
                    workList.append(entry)

                if entry.versionNumber == versionNumber:
                    break
            else:
                raise InternalError(u"Tried to retrieve non-existing"
                        u"version number %s" % versionNumber)

        if base is None:
            raise InternalError(u"No base version found for getVersionContent(%s)" %
                    versionNumber)

        unifName = u"versioning/packet/versionNo/%s/%s" % (base.versionNumber,
                self.unifiedPageName)

        content = self.wikiDocument.retrieveDataBlock(unifName)

        for entry in workList:
            unifName = u"versioning/packet/versionNo/%s/%s" % (entry.versionNumber,
                    self.unifiedPageName)
            packet = self.wikiDocument.retrieveDataBlock(unifName)
            
            content = applyBinCompact(content, packet)
        
        return fileContentToUnicode(content)


    def addVersion(self, content, entry):
        """
        entry.versionNumber is invalid and will be filled by this function.
        """
        if isinstance(content, unicode):
            content = BOM_UTF8 + content.encode("utf-8")
        assert isinstance(content, str)

        headUnifName = u"versioning/packet/versionNo/-1/%s" % self.unifiedPageName

        if self.headVersion is not None:
            prevHeadContent = self.wikiDocument.retrieveDataBlock(headUnifName)
            diffPacket = getBinCompactForDiff(content, prevHeadContent)
            
            prevHeadEntry = self.headVersion
            prevHeadEntry.versionNumber = self.maxVersionNumber + 1
            prevHeadEntry.contentCompression = "revdiff"
            unifName = u"versioning/packet/versionNo/%s/%s" % (prevHeadEntry.versionNumber,
                    self.unifiedPageName)

            self.wikiDocument.storeDataBlock(unifName, diffPacket,
                    storeHint=Consts.DATABLOCK_STOREHINT_EXTERN)
            self.versionEntries.append(prevHeadEntry)

            self.maxVersionNumber += 1


        self.headVersion = entry
        self.headVersion.versionNumber = -1
        self.headVersion.contentCompression = "complete"

        self.wikiDocument.storeDataBlock(headUnifName, content,
                storeHint=Consts.DATABLOCK_STOREHINT_EXTERN)



class WikiPageSnapshot(AbstractWikiPage):
    def __init__(self, wikiDocument, baseWikiPage):
        AbstractWikiPage.__init__(self, wikiDocument, baseWikiPage.getWikiWord())
        
        self.baseWikiPage = baseWikiPage
        self.versionNumber = 0


    def setVersionNumber(self, vn):
        self.versionNumber = vn
        
        if vn == 0:
            content = u""
        else:
            content = self.baseWikiPage.getVersionOverview().getVersionContent(vn)

        self.setEditorText(content)


    def getUnifiedPageName(self):
        if self.versionNumber == 0:
            return None


    def isReadOnlyEffect(self):
        """
        Return true if page is effectively read-only, this means
        "for any reason", regardless if error or intention.
        """
        return True





