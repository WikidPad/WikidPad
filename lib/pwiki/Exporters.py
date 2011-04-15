from __future__ import with_statement

## import profilehooks
## profile = profilehooks.profile(filename="profile.prf", immediate=False)

# from Enum import Enumeration
import sys, os, string, re, traceback, locale, time, urllib
from os.path import join, exists, splitext, abspath
from cStringIO import StringIO
import shutil
## from xml.sax.saxutils import escape

import urllib_red as urllib

import wx
from rtlibRepl import minidom

from wxHelper import XrcControls, GUI_ID, wxKeyFunctionSink

import Consts
from WikiExceptions import WikiWordNotFoundException, ExportException
from ParseUtilities import getFootnoteAnchorDict
from StringOps import *
from . import StringOps
import Serialization
from WikiPyparsing import StackedCopyDict, SyntaxNode
from TempFileSet import TempFileSet

from SearchAndReplace import SearchReplaceOperation, ListWikiPagesOperation, \
        ListItemWithSubtreeWikiPagesNode

import SystemInfo, PluginManager

import OsAbstract

import DocPages



def retrieveSavedExportsList(mainControl, wikiData, continuousExport):
    unifNames = wikiData.getDataBlockUnifNamesStartingWith(u"savedexport/")

    result = []
    suppExTypes = PluginManager.getSupportedExportTypes(mainControl,
                None, continuousExport)

    for un in unifNames:
        name = un[12:]
        content = wikiData.retrieveDataBlock(un)
        xmlDoc = minidom.parseString(content)
        xmlNode = xmlDoc.firstChild
        etype = Serialization.serFromXmlUnicode(xmlNode, u"exportTypeName")
        if etype not in suppExTypes:
            # Export type of saved export not supported
            continue

        result.append((name, xmlNode))

    mainControl.getCollator().sortByFirst(result)

    return result



class AbstractExporter(object):
    def __init__(self, mainControl):
        self.wikiDocument = None
        self.mainControl = mainControl

    def getMainControl(self):
        return self.mainControl    
 
    def setWikiDocument(self, wikiDocument):
        self.wikiDocument = wikiDocument

    def getWikiDocument(self):
        return self.wikiDocument

    @staticmethod
    def getExportTypes(mainControl, continuousExport=False):
        """
        Return sequence of tuples with the description of export types provided
        by this object. A tuple has the form (<exp. type>,
            <human readable description>)
        All exporters must provide this as a static method (which can be called
        without constructing an object first.

        mainControl -- PersonalWikiFrame object
        continuousExport -- If True, only types with support for continuous export
        are listed.
        """
        return ()

    def getAddOptPanelsForTypes(self, guiparent, exportTypes):
        """
        Construct all necessary GUI panels for additional options
        for the types contained in exportTypes.
        Returns sequence of tuples (<exp. type>, <panel for add. options or None>)
        
        The panels should use  guiparent  as parent.
        If the same panel is used for multiple export types the function can
        and should include all export types for this panel even if some of
        them weren't requested.
        """
        raise NotImplementedError
        
        

    def getExportDestinationWildcards(self, exportType):
        """
        If an export type is intended to go to a file, this function
        returns a (possibly empty) sequence of tuples
        (wildcard description, wildcard filepattern).
        
        If an export type goes to a directory, None is returned
        """
        raise NotImplementedError


    def getAddOptVersion(self):
        """
        Returns the version of the additional options information returned
        by getAddOpt(). If the return value is -1, the version info can't
        be stored between application sessions.
        
        Otherwise, the addopt information can be stored between sessions
        and can later handled back to the export method of the object
        without previously showing the export dialog.
        """
        raise NotImplementedError


    def getAddOpt(self, addoptpanel):
        """
        Reads additional options from panel addoptpanel.
        If addoptpanel is None, return default values
        If getAddOptVersion() > -1, the return value must be a sequence
        of simple string, unicode and/or numeric objects. Otherwise, any object
        can be returned (normally the addoptpanel itself).
        """
        raise NotImplementedError
    

    def setAddOpt(self, addOpt, addoptpanel):
        """
        Shows content of addOpt in the addoptpanel (must not be None).
        This function is only called if getAddOptVersion() != -1.
        """
        raise NotImplementedError


    def export(self, wikiDocument, wordList, exportType, exportDest,
            compatFilenames, addOpt, progressHandler):
        """
        Run non-continuous export operation.
        
        wikiDocument -- WikiDocument object
        wordList -- Sequence of wiki words to export
        exportType -- string tag to identify how to export
        exportDest -- Path to destination directory or file to export to
        compatFilenames -- Should the filenames be encoded to be lowest
                           level compatible
        addOpt -- additional options returned by getAddOpt()
        progressHandler -- wxHelper.ProgressHandler object
        """
        raise NotImplementedError

    
    def startContinuousExport(self, wikiDocument, listPagesOperation,
            exportType, exportDest, compatFilenames, addOpt, progressHandler):
        """
        Start continues export operation. This function may be unimplemented
        if derived class does not provide any continous-export type.
        
        wikiDocument -- WikiDocument object
        listPagesOperation -- Instance of SearchAndReplace.SearchReplaceOperation
        exportType -- string tag to identify how to export
        exportDest -- Path to destination directory or file to export to
        compatFilenames -- Should the filenames be encoded to be lowest
                           level compatible
        addOpt -- additional options returned by getAddOpt()
        progressHandler -- wxHelper.ProgressHandler object
        """
        raise NotImplementedError


    def stopContinuousExport(self):
        """
        Stop continues-export operation. This function may be unimplemented
        if derived class does not provide any continous-export type.
        """
        raise NotImplementedError


#     def supportsXmlOptions(self):
#         """
#         Returns True if additional options can be returned and processed
#         as XML.
#         """
#         return True
#     
#     def getXmlRepresentation


def removeBracketsToCompFilename(fn):
    """
    Combine unicodeToCompFilename() and removeBracketsFilename() from StringOps
    """
    return unicodeToCompFilename(removeBracketsFilename(fn))




class TextExporter(AbstractExporter):
    """
    Exports raw text
    """
    def __init__(self, mainControl):
        AbstractExporter.__init__(self, mainControl)
        self.wordList = None
        self.exportDest = None
        self.convertFilename = removeBracketsFilename # lambda s: s   

    @staticmethod
    def getExportTypes(mainControl, continuousExport=False):
        """
        Return sequence of tuples with the description of export types provided
        by this object. A tuple has the form (<exp. type>,
            <human readable description>)
        All exporters must provide this as a static method (which can be called
        without constructing an object first.

        mainControl -- PersonalWikiFrame object
        continuousExport -- If True, only types with support for continuous export
        are listed.
        """
        if continuousExport:
            # Continuous export not supported
            return ()

        return (
            (u"raw_files", _(u'Set of *.wiki files')),
            )

    def getAddOptPanelsForTypes(self, guiparent, exportTypes):
        """
        Construct all necessary GUI panels for additional options
        for the types contained in exportTypes.
        Returns sequence of tuples (<exp. type>, <panel for add. options or None>)

        The panels should use  guiparent  as parent.
        If the same panel is used for multiple export types the function can
        and should include all export types for this panel even if some of
        them weren't requested. Panel objects must not be shared by different
        exporter classes.
        """
        if not u"raw_files" in exportTypes:
            return ()

        res = wx.xrc.XmlResource.Get()
        textPanel = res.LoadPanel(guiparent, "ExportSubText") # .ctrls.additOptions

        return (
            (u"raw_files", textPanel),
            )



#     def getExportDestinationType(self, exportType):
#         """
#         Return one of the EXPORT_DEST_TYPE_* constants describing
#         if exportType exorts to a file or directory
#         """
#         TYPEMAP = {
#                 u"raw_files": EXPORT_DEST_TYPE_DIR
#                 }
#                 
#         return TYPEMAP[exportType]


    def getExportDestinationWildcards(self, exportType):
        """
        If an export type is intended to go to a file, this function
        returns a (possibly empty) sequence of tuples
        (wildcard description, wildcard filepattern).
        
        If an export type goes to a directory, None is returned
        """
        return None


    def getAddOptVersion(self):
        """
        Returns the version of the additional options information returned
        by getAddOpt(). If the return value is -1, the version info can't
        be stored between application sessions.
        
        Otherwise, the addopt information can be stored between sessions
        and can later handled back to the export method of the object
        without previously showing the export dialog.
        """
        return 0


    def getAddOpt(self, addoptpanel):
        """
        Reads additional options from panel addoptpanel.
        If getAddOptVersion() > -1, the return value must be a sequence
        of simple string and/or numeric objects. Otherwise, any object
        can be returned (normally the addoptpanel itself)
        """
        if addoptpanel is None:
            return (1,)
        else:
            ctrls = XrcControls(addoptpanel)
            
            # Which encoding:
            # 0:System standard, 1:utf-8 with BOM, 2: utf-8 without BOM
    
            return (ctrls.chTextEncoding.GetSelection(),)


    def setAddOpt(self, addOpt, addoptpanel):
        """
        Shows content of addOpt in the addoptpanel (must not be None).
        This function is only called if getAddOptVersion() != -1.
        """
        ctrls = XrcControls(addoptpanel)
        ctrls.chTextEncoding.SetSelection(addOpt[0])


    def export(self, wikiDocument, wordList, exportType, exportDest,
            compatFilenames, addopt, progressHandler):
        """
        Run export operation.
        
        wikiDocument -- WikiDocument object
        wordList -- Sequence of wiki words to export
        exportType -- string tag to identify how to export
        exportDest -- Path to destination directory or file to export to
        compatFilenames -- Should the filenames be encoded to be lowest
                           level compatible
        addopt -- additional options returned by getAddOpt()
        """
        self.wikiDocument = wikiDocument
        self.wordList = wordList
        self.exportDest = exportDest
       
        if compatFilenames:
            self.convertFilename = removeBracketsToCompFilename
        else:
            self.convertFilename = removeBracketsFilename # lambda s: s
         
        # 0:System standard, 1:utf-8 with BOM, 2: utf-8 without BOM
        encoding = addopt[0]
                
        if encoding == 0:
            enc = mbcsEnc
        else:
            enc = utf8Enc
            
        if encoding == 1:
            filehead = BOM_UTF8
        else:
            filehead = ""

        for word in self.wordList:
            try:
                wikiPage = self.wikiDocument.getWikiPage(word)
                content = wikiPage.getLiveText()
                modified = wikiPage.getTimestamps()[0]
#                 content = self.wikiDocument.getWikiData().getContent(word)
#                 modified = self.wikiDocument.getWikiData().getTimestamps(word)[0]
            except:
                traceback.print_exc()
                continue

            # TODO Use self.convertFilename here???
            outputFile = join(self.exportDest,
                    self.convertFilename(u"%s.wiki" % word))

            try:
#                 if exists(outputFile):
#                     os.unlink(outputFile)
    
                fp = open(pathEnc(outputFile), "wb")
                fp.write(filehead)
                fp.write(enc(content, "replace")[0])
                fp.close()
                
                try:
                    os.utime(outputFile, (long(modified), long(modified)))
                except:
                    pass
            except:
                traceback.print_exc()
                continue


class MultiPageTextAddOptPanel(wx.Panel):
    def __init__(self, parent):
        p = wx.PrePanel()
        self.PostCreate(p)

        res = wx.xrc.XmlResource.Get()
        res.LoadOnPanel(self, parent, "ExportSubMultipageText")
        
        self.ctrls = XrcControls(self)
        
        wx.EVT_CHOICE(self, GUI_ID.chFileVersion, self.OnFileVersionChoice)


    def OnFileVersionChoice(self, evt):
        enabled = evt.GetSelection() > 0
        
        self.ctrls.cbWriteWikiFuncPages.Enable(enabled)
        self.ctrls.cbWriteSavedSearches.Enable(enabled)
        self.ctrls.cbWriteVersionData.Enable(enabled)



class MultiPageTextExporter(AbstractExporter):
    """
    Exports in multipage text format
    """
    def __init__(self, mainControl):
        AbstractExporter.__init__(self, mainControl)
        self.wordList = None
        self.exportDest = None
        self.addOpt = None

    @staticmethod
    def getExportTypes(mainControl, continuousExport=False):
        """
        Return sequence of tuples with the description of export types provided
        by this object. A tuple has the form (<exp. type>,
            <human readable description>)
        All exporters must provide this as a static method (which can be called
        without constructing an object first.

        mainControl -- PersonalWikiFrame object
        continuousExport -- If True, only types with support for continuous export
        are listed.
        """
        if continuousExport:
            # Continuous export not supported    TODO
            return ()
        return (
            (u"multipage_text", _(u"Multipage text")),
            )


    def getAddOptPanelsForTypes(self, guiparent, exportTypes):
        """
        Construct all necessary GUI panels for additional options
        for the types contained in exportTypes.
        Returns sequence of tuples (<exp. type>, <panel for add. options or None>)

        The panels should use  guiparent  as parent.
        If the same panel is used for multiple export types the function can
        and should include all export types for this panel even if some of
        them weren't requested. Panel objects must not be shared by different
        exporter classes.
        """
        if not u"multipage_text" in exportTypes:
            return ()

        optPanel = MultiPageTextAddOptPanel(guiparent)
        return (
            (u"multipage_text", optPanel),
            )


    def getExportDestinationWildcards(self, exportType):
        """
        If an export type is intended to go to a file, this function
        returns a (possibly empty) sequence of tuples
        (wildcard description, wildcard filepattern).
        
        If an export type goes to a directory, None is returned
        """
        if exportType == u"multipage_text":
            return ((_(u"Multipage files (*.mpt)"), "*.mpt"),
                    (_(u"Text file (*.txt)"), "*.txt")) 

        return None


    def getAddOptVersion(self):
        """
        Returns the version of the additional options information returned
        by getAddOpt(). If the return value is -1, the version info can't
        be stored between application sessions.
        
        Otherwise, the addopt information can be stored between sessions
        and can later handled back to the export method of the object
        without previously showing the export dialog.
        """
        return 1


    def getAddOpt(self, addoptpanel):
        """
        Reads additional options from panel addoptpanel.
        If getAddOptVersion() > -1, the return value must be a sequence
        of simple (unicode) string and/or numeric objects. Otherwise, any object
        can be returned (normally the addoptpanel itself).
        
        The tuple elements mean: (<format version to write>,
                <export func. pages>, <export saved searches>,
                <export version data>)
        """
        if addoptpanel is None:
            # Return default set in options
            fileVersion = 1
            writeWikiFuncPages = 1
            writeSavedSearches = 1            
        else:
            ctrls = addoptpanel.ctrls
            fileVersion = ctrls.chFileVersion.GetSelection()
            writeWikiFuncPages = boolToInt(ctrls.cbWriteWikiFuncPages.GetValue())
            writeSavedSearches = boolToInt(ctrls.cbWriteSavedSearches.GetValue())
            writeVersionData = boolToInt(ctrls.cbWriteVersionData.GetValue())

        return (fileVersion, writeWikiFuncPages, writeSavedSearches,
                writeVersionData)


    def setAddOpt(self, addOpt, addoptpanel):
        """
        Shows content of addOpt in the addoptpanel (must not be None).
        This function is only called if getAddOptVersion() != -1.
        """
        fileVersion, writeWikiFuncPages, writeSavedSearches, writeVersionData = \
                addOpt[:4]

        ctrls = addoptpanel.ctrls   # XrcControls(addoptpanel)?

        ctrls.chFileVersion.SetSelection(fileVersion)
        ctrls.cbWriteWikiFuncPages.SetValue(writeWikiFuncPages != 0)
        ctrls.cbWriteSavedSearches.SetValue(writeSavedSearches != 0)
        ctrls.cbWriteVersionData.SetValue(writeVersionData != 0)



    # TODO Check also wiki func pages and versions and and and ....!!!
    def _checkPossibleSeparator(self, sep):
        """
        Run search operation to test if separator string sep
        (without trailing newline) is already in use.
        Returns True if sep doesn't appear as line in any page from
        self.wordList
        """
        searchOp = SearchReplaceOperation()
        searchOp.searchStr = u"^" + re.escape(sep) + u"$"
        searchOp.booleanOp = False
        searchOp.caseSensitive = True
        searchOp.wholeWord = False
        searchOp.cycleToStart = False
        searchOp.wildCard = 'regex'
        searchOp.wikiWide = True

        wpo = ListWikiPagesOperation()
        wpo.setSearchOpTree(ListItemWithSubtreeWikiPagesNode(wpo, self.wordList,
                level=0))

        searchOp.listWikiPagesOp = wpo

        foundPages = self.mainControl.getWikiDocument().searchWiki(searchOp)

        return len(foundPages) == 0


    def _findSeparator(self):
        """
        Find a separator (=something not used as line in a page to export)
        """
        # Try random strings (35 tries)
        for i in xrange(35):
            sep = u"-----%s-----" % createRandomString(25)
            if self._checkPossibleSeparator(sep):
                return sep

        # Give up
        return None


    def _writeHintedDatablock(self, unifName, useB64):
        sh = self.wikiDocument.guessDataBlockStoreHint(unifName)
        if sh == Consts.DATABLOCK_STOREHINT_EXTERN:
            shText = u"extern"
        else:
            shText = u"intern"

        self.exportFile.write(unifName + u"\n")
        if useB64:
            datablock = self.wikiDocument.retrieveDataBlock(unifName)

            self.exportFile.write(u"important/encoding/base64  storeHint/%s\n" %
                    shText)
            self.exportFile.write(base64BlockEncode(datablock))
        else:
            content = self.wikiDocument.retrieveDataBlockAsText(unifName)

            self.exportFile.write(u"important/encoding/text  storeHint/%s\n" %
                    shText)
            self.exportFile.write(content)



    def _writeSeparator(self):
        if self.firstSeparatorCallDone:
            self.exportFile.write("\n%s\n" % self.separator)
        else:
            self.firstSeparatorCallDone = True


    def export(self, wikiDocument, wordList, exportType, exportDest,
            compatFilenames, addOpt, progressHandler):
        """
        Run export operation.
        
        wikiDocument -- WikiDocument object
        wordList -- Sequence of wiki words to export
        exportType -- string tag to identify how to export
        exportDest -- Path to destination directory or file to export to
        compatFilenames -- Should the filenames be encoded to be lowest
                           level compatible
        addOpt -- additional options returned by getAddOpt()
        """
        self.wikiDocument = wikiDocument
        self.wordList = wordList
        self.exportDest = exportDest
        self.addOpt = addOpt
        self.exportFile = None
        self.rawExportFile = None
        self.firstSeparatorCallDone = False
        
        self.formatVer = min(addOpt[0], 1)
        self.writeWikiFuncPages = addOpt[1] and (self.formatVer > 0)
        self.writeSavedSearches = addOpt[2] and (self.formatVer > 0)
        self.writeVersionData = addOpt[3] and (self.formatVer > 0)

        
        # The hairy thing first: find a separator that doesn't appear
        # as a line in one of the pages to export
        self.separator = self._findSeparator()
        if self.separator is None:
            # _findSeparator gave up
            raise ExportException(_(u"No usable separator found"))
        try:
            try:
                self.rawExportFile = open(pathEnc(self.exportDest), "w")
    
                # Only UTF-8 mode currently
                self.rawExportFile.write(BOM_UTF8)
                self.exportFile = utf8Writer(self.rawExportFile, "replace")
                
                # Identifier line with file format
                self.exportFile.write(u"Multipage text format %i\n" %
                        self.formatVer)
                # Separator line
                self.exportFile.write(u"Separator: %s\n" % self.separator)


                # Write wiki-bound functional pages
                if self.writeWikiFuncPages:
                    # Only wiki related functional pages
                    wikiFuncTags = [ft for ft in DocPages.getFuncTags()
                            if ft.startswith("wiki/")]
                    
                    for ft in wikiFuncTags:
                        self._writeSeparator()
                        self.exportFile.write(u"funcpage/%s\n" % ft)
                        page = self.wikiDocument.getFuncPage(ft)
                        self.exportFile.write(page.getLiveText())


                # Write saved searches
                if self.writeSavedSearches:
                    wikiData = self.wikiDocument.getWikiData()
#                     searchTitles = wikiData.getSavedSearchTitles()
                    unifNames = wikiData.getDataBlockUnifNamesStartingWith(
                            u"savedsearch/")

                    for un in unifNames:
                        self._writeSeparator()
#                         self.exportFile.write(u"savedsearch/%s\n" % st)
#                         datablock = wikiData.getSearchDatablock(st)
                        self.exportFile.write(un + u"\n")
                        datablock = wikiData.retrieveDataBlock(un)

                        self.exportFile.write(base64BlockEncode(datablock))

                locale.setlocale(locale.LC_ALL, '')

                # Write actual wiki words
                for word in self.wordList:
                    page = self.wikiDocument.getWikiPage(word)

                    self._writeSeparator()
                    if self.formatVer == 0:
                        self.exportFile.write(u"%s\n" % word)
                    else:
                        self.exportFile.write(u"wikipage/%s\n" % word)
                        # modDate, creaDate, visitDate
                        timeStamps = page.getTimestamps()[:3]

                        # Do not use StringOps.strftimeUB here as its output
                        # relates to local time, but we need UTC here.
                        timeStrings = [unicode(time.strftime(
                                "%Y-%m-%d/%H:%M:%S", time.gmtime(ts)))
                                for ts in timeStamps]

                        self.exportFile.write(u"%s  %s  %s\n" % tuple(timeStrings))

                    self.exportFile.write(page.getLiveText())

                    # Write version data for this word
                    if self.writeVersionData:
                        verOvw = page.getExistingVersionOverview()
                        if verOvw is not None:
                            unifName = verOvw.getUnifiedName()

                            self._writeSeparator()
                            self._writeHintedDatablock(unifName, False)

                            for unifName in verOvw.getDependentDataBlocks(
                                    omitSelf=True):
                                self._writeSeparator()
                                self._writeHintedDatablock(unifName, True)

            except Exception, e:
                traceback.print_exc()
                raise ExportException(unicode(e))
        finally:
            if self.exportFile is not None:
                self.exportFile.flush()

            if self.rawExportFile is not None:
                self.rawExportFile.close()



def describeExportersV01(mainControl):
    return (TextExporter, MultiPageTextExporter)


