

## import profilehooks
## profile = profilehooks.profile(filename="profile.prf", immediate=False)

# from Enum import Enumeration
import sys, os, re, traceback, locale, time, urllib.request, urllib.parse, urllib.error
from os.path import join, exists, splitext, abspath
from io import BytesIO
import shutil
## from xml.sax.saxutils import escape

from . import urllib_red as urllib

import wx
from .rtlibRepl import minidom

from .wxHelper import XrcControls, GUI_ID, wxKeyFunctionSink

import Consts
from .WikiExceptions import WikiWordNotFoundException, ExportException
from .ParseUtilities import getFootnoteAnchorDict
from .StringOps import *
from . import StringOps
from . import Serialization
from .WikiPyparsing import StackedCopyDict, SyntaxNode
from .TempFileSet import TempFileSet

from .SearchAndReplace import SearchReplaceOperation, ListWikiPagesOperation, \
        ListItemWithSubtreeWikiPagesNode

from . import SystemInfo, PluginManager

from . import OsAbstract

from . import DocPages



def retrieveSavedExportsList(mainControl, wikiData, continuousExport):
    unifNames = wikiData.getDataBlockUnifNamesStartingWith("savedexport/")

    result = []
    suppExTypes = PluginManager.getSupportedExportTypes(mainControl,
                None, continuousExport)

    for un in unifNames:
        name = un[12:]
        content = wikiData.retrieveDataBlock(un)
        xmlDoc = minidom.parseString(content)
        xmlNode = xmlDoc.firstChild
        etype = Serialization.serFromXmlUnicode(xmlNode, "exportTypeName")
        if etype not in suppExTypes:
            # Export type of saved export not supported
            continue

        result.append((name, xmlNode))

    mainControl.getCollator().sortByFirst(result)

    return result


def contentToUnicode(content):
    """
    Try to detect the text encoding of byte content
    and return converted unicode
    """
    if isinstance(content, str):
        return content

    if content.startswith(BOM_UTF8):
        return content[len(BOM_UTF8):].decode("utf-8", "replace")
    elif content.startswith(BOM_UTF16_BE):
        return content[len(BOM_UTF16_BE):].decode("utf-16-be", "replace")
    elif content.startswith(BOM_UTF16_LE):
        return content[len(BOM_UTF16_LE):].decode("utf-16-le", "replace")
    else:
        try:
            return content.decode("utf-8", "strict")
        except UnicodeDecodeError:
            return mbcsDec(content, "replace")[0]



class AbstractExporter:
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
            ("raw_files", _('Set of *.wiki files')),
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
        if not "raw_files" in exportTypes:
            return ()

        res = wx.xrc.XmlResource.Get()
        textPanel = res.LoadPanel(guiparent, "ExportSubText") # .ctrls.additOptions

        return (
            ("raw_files", textPanel),
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
                    self.convertFilename("%s.wiki" % word))

            try:
#                 if exists(outputFile):
#                     os.unlink(outputFile)
    
                fp = open(pathEnc(outputFile), "wb")
                fp.write(filehead)
                fp.write(enc(content, "replace")[0])
                fp.close()
                
                try:
                    os.utime(outputFile, (int(modified), int(modified)))
                except:
                    pass
            except:
                traceback.print_exc()
                continue


class MultiPageTextAddOptPanel(wx.Panel):
    def __init__(self, parent):
#         p = wx.PrePanel()
#         self.PostCreate(p)
        
        wx.Panel.__init__(self)

        res = wx.xrc.XmlResource.Get()
        res.LoadPanel(self, parent, "ExportSubMultipageText")
        
        self.ctrls = XrcControls(self)
        
        self.Bind(wx.EVT_CHOICE, self.OnFileVersionChoice, id=GUI_ID.chFileVersion)


    def OnFileVersionChoice(self, evt):
        enabled = evt.GetSelection() > 0
        
        self.ctrls.cbWriteWikiFuncPages.Enable(enabled)
        self.ctrls.cbWriteSavedSearches.Enable(enabled)
        self.ctrls.cbWriteVersionData.Enable(enabled)



class _SeparatorFoundException(Exception): pass

class _SeparatorWatchUtf8Writer(utf8Writer):
    def __init__(self, stream, separator, errors="strict"):
        utf8Writer.__init__(self, stream, errors)
        self.separator = separator
#         self.separatorRe = re.compile(u"^" + re.escape(separator) + u"$",
#                 re.MULTILINE | re.UNICODE)
        self.buffer = []
        self.firstSeparatorCallDone = False

    def write(self, obj):
        self.buffer.append(obj)
        utf8Writer.write(self, obj)

    def writelines(self, list):
        self.buffer += list
        utf8Writer.writelines(self, list)

    def clearBuffer(self):
        self.buffer = []
    
    def checkAndClearBuffer(self):
#         if self.separatorRe.search(u"".join(self.buffer)):
        if "".join(self.buffer).find("\n%s\n" % self.separator) > -1:
            raise _SeparatorFoundException()

        self.clearBuffer()


    def writeSeparator(self):
        self.checkAndClearBuffer()

        if self.firstSeparatorCallDone:
            utf8Writer.write(self, "\n%s\n" % self.separator)
        else:
            self.firstSeparatorCallDone = True




class MultiPageTextWikiPageWriter:
    """
    Exports in multipage text format
    """
    def __init__(self, wikiDocument, exportFile, writeVersionData=True,
            formatVer=1):
        self.wikiDocument = wikiDocument
        self.exportFile = exportFile
        self.writeVersionData = writeVersionData
        self.formatVer = formatVer


    def _writeHintedDatablock(self, unifName, useB64):
        sh = self.wikiDocument.guessDataBlockStoreHint(unifName)
        if sh == Consts.DATABLOCK_STOREHINT_EXTERN:
            shText = "extern"
        else:
            shText = "intern"

        self.exportFile.write(unifName + "\n")
        if useB64:
            datablock = self.wikiDocument.retrieveDataBlock(unifName)

            self.exportFile.write("important/encoding/base64  storeHint/%s\n" %
                    shText)
            self.exportFile.write(base64BlockEncode(datablock))
        else:
            content = self.wikiDocument.retrieveDataBlockAsText(unifName)

            self.exportFile.write("important/encoding/text  storeHint/%s\n" %
                    shText)
            self.exportFile.write(content)


    def exportWikiWord(self, word):
        page = self.wikiDocument.getWikiPage(word)

        self.exportFile.writeSeparator()
        if self.formatVer == 0:
            self.exportFile.write("%s\n" % word)
        else:
            self.exportFile.write("wikipage/%s\n" % word)
            # modDate, creaDate, visitDate
            timeStamps = page.getTimestamps()[:3]

            # Do not use StringOps.strftimeUB here as its output
            # relates to local time, but we need UTC here.
            timeStrings = [str(time.strftime(
                    "%Y-%m-%d/%H:%M:%S", time.gmtime(ts)))
                    for ts in timeStamps]

            self.exportFile.write("%s  %s  %s\n" % tuple(timeStrings))

        self.exportFile.write(page.getLiveText())

        # Write version data for this word
        if self.writeVersionData:
            verOvw = page.getExistingVersionOverview()
            if verOvw is not None and not verOvw.isNotInDatabase():
                unifName = verOvw.getUnifiedName()

                self.exportFile.writeSeparator()
                self._writeHintedDatablock(unifName, False)

                for unifName in verOvw.getDependentDataBlocks(
                        omitSelf=True):
                    self.exportFile.writeSeparator()
                    self._writeHintedDatablock(unifName, True)


def getSingleWikiWordPacket(wikiDocument, word, writeVersionData=True,
        formatVer=1):
    """
    Helper function for the trashcan to create a trash bag packet for a
    single wiki word (including versions). Returns it as a utf8-encoded
    bytestring.
    """
    for tryNumber in range(35):
        stream = BytesIO()
        stream.write(BOM_UTF8)
        separator = "-----%s-----" % createRandomString(25)
        exportFile = _SeparatorWatchUtf8Writer(stream, separator)
        wikiPageWriter = MultiPageTextWikiPageWriter(wikiDocument, exportFile,
                writeVersionData, formatVer)

        exportFile.write("Multipage text format %i\n" % formatVer)
        # Separator line
        exportFile.write("Separator: %s\n" % separator)

        try:
            wikiPageWriter.exportWikiWord(word)
            exportFile.checkAndClearBuffer()

            return stream.getvalue()
        except _SeparatorFoundException:
            continue
    else:
        raise ExportException(_("No usable separator found"))




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
            ("multipage_text", _("Multipage text")),
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
        if not "multipage_text" in exportTypes:
            return ()

        optPanel = MultiPageTextAddOptPanel(guiparent)
        return (
            ("multipage_text", optPanel),
            )


    def getExportDestinationWildcards(self, exportType):
        """
        If an export type is intended to go to a file, this function
        returns a (possibly empty) sequence of tuples
        (wildcard description, wildcard filepattern).
        
        If an export type goes to a directory, None is returned
        """
        if exportType == "multipage_text":
            return ((_("Multipage files (*.mpt)"), "*.mpt"),
                    (_("Text file (*.txt)"), "*.txt")) 

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


    def _writeHintedDatablock(self, unifName, useB64):
        sh = self.wikiDocument.guessDataBlockStoreHint(unifName)
        if sh == Consts.DATABLOCK_STOREHINT_EXTERN:
            shText = "extern"
        else:
            shText = "intern"

        self.exportFile.write(unifName + "\n")
        if useB64:
            datablock = self.wikiDocument.retrieveDataBlock(unifName)

            self.exportFile.write("important/encoding/base64  storeHint/%s\n" %
                    shText)
            self.exportFile.write(base64BlockEncode(datablock))
        else:
            content = self.wikiDocument.retrieveDataBlockAsText(unifName)

            self.exportFile.write("important/encoding/text  storeHint/%s\n" %
                    shText)
            self.exportFile.write(content)

#     @staticmethod
#     def _writeHintedDatablock(wikiDocument, exportFile, unifName, useB64):
#         sh = wikiDocument.guessDataBlockStoreHint(unifName)
#         if sh == Consts.DATABLOCK_STOREHINT_EXTERN:
#             shText = u"extern"
#         else:
#             shText = u"intern"
# 
#         exportFile.write(unifName + u"\n")
#         if useB64:
#             datablock = wikiDocument.retrieveDataBlock(unifName)
# 
#             exportFile.write(u"important/encoding/base64  storeHint/%s\n" %
#                     shText)
#             exportFile.write(base64BlockEncode(datablock))
#         else:
#             content = wikiDocument.retrieveDataBlockAsText(unifName)
# 
#             exportFile.write(u"important/encoding/text  storeHint/%s\n" %
#                     shText)
#             exportFile.write(content)

#     def _writeSeparator(self):
#         self.exportFile.checkAndClearBuffer()
# 
#         if self.firstSeparatorCallDone:
#             self.exportFile.writeSeparator()
#         else:
#             self.firstSeparatorCallDone = True


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

        try:
            for tryNumber in range(35):
                self.separator = "-----%s-----" % createRandomString(25)
                try:
                    self.rawExportFile = open(pathEnc(self.exportDest), "w")

                    # Only UTF-8 mode currently
                    self.rawExportFile.write(BOM_UTF8)
                    self.exportFile = _SeparatorWatchUtf8Writer(
                            self.rawExportFile, self.separator, "replace")

                    self.wikiPageWriter = MultiPageTextWikiPageWriter(
                            self.wikiDocument, self.exportFile,
                            self.writeVersionData, self.formatVer)

                    # Identifier line with file format
                    self.exportFile.write("Multipage text format %i\n" %
                            self.formatVer)
                    # Separator line
                    self.exportFile.write("Separator: %s\n" % self.separator)
    
    
                    # Write wiki-bound functional pages
                    if self.writeWikiFuncPages:
                        # Only wiki related functional pages
                        wikiFuncTags = [ft for ft in DocPages.getFuncTags()
                                if ft.startswith("wiki/")]
                        
                        for ft in wikiFuncTags:
                            self.exportFile.writeSeparator()
                            self.exportFile.write("funcpage/%s\n" % ft)
                            page = self.wikiDocument.getFuncPage(ft)
                            self.exportFile.write(page.getLiveText())
    
    
                    # Write saved searches
                    if self.writeSavedSearches:
                        # Wiki-wide searches
                        wikiData = self.wikiDocument.getWikiData()
                        unifNames = wikiData.getDataBlockUnifNamesStartingWith(
                                "savedsearch/")
    
                        for un in unifNames:
                            self.exportFile.writeSeparator()
                            self.exportFile.write(un + "\n")
                            datablock = wikiData.retrieveDataBlock(un)
    
                            self.exportFile.write(base64BlockEncode(datablock))
                        
                        # Page searches
                        unifNames = wikiData.getDataBlockUnifNamesStartingWith(
                                "savedpagesearch/")
    
                        for un in unifNames:
                            self.exportFile.writeSeparator()
                            self._writeHintedDatablock(un, False)

                    locale.setlocale(locale.LC_ALL, '')
                    
                    wx.Locale(wx.LANGUAGE_DEFAULT)
    
                    # Write actual wiki words
                    for word in self.wordList:
                        self.wikiPageWriter.exportWikiWord(word)
                        self.exportFile.checkAndClearBuffer()
                    break

                except _SeparatorFoundException:
                    if self.exportFile is not None:
                        self.exportFile.flush()
                        self.exportFile = None
        
                    if self.rawExportFile is not None:
                        self.rawExportFile.close()
                        self.rawExportFile = None

                    continue
                except Exception as e:
                    traceback.print_exc()
                    raise ExportException(str(e))
            else:
                raise ExportException(_("No usable separator found"))
        finally:
            if self.exportFile is not None:
                self.exportFile.flush()
                self.exportFile = None

            if self.rawExportFile is not None:
                self.rawExportFile.close()
                self.rawExportFile = None


    def _getDatablocksClass(self, unifName):
        """
        """
        if unifName.startswith("wiki/"):
            return 1 | 8  # as text, not hinted, prepend "funcpage/"
        elif unifName.startswith("savedsearch/"):
            return 2  # binary, not hinted
        elif unifName.startswith("savedpagesearch/"):
            return 1 | 4  # text, hinted
        elif unifName.startswith("savedexport/"):
            return 1 | 4  # text, hinted
        elif unifName.startswith("versioning/overview/"):
            return 1 | 4  # text, hinted
        elif unifName.startswith("versioning/packet/"):
            return 2 | 4  # binary, hinted
        else:
            return 2 | 4  # binary, hinted



    def _recoveryExportDatablocks(self):
        def writeDatablock(unifName, datablock, storeHint):
            cl = self._getDatablocksClass(unifName)

            if cl == 0:
                return
            
            if cl & 8 == 8:
                unifName = "funcpage/" + unifName
            
            self.exportFile.writeSeparator()
            self.exportFile.write(unifName + "\n")
            
            if cl & 4 == 4:
                # Hinted 
                if storeHint == Consts.DATABLOCK_STOREHINT_EXTERN:
                    shText = "extern"
                else:
                    shText = "intern"

                if cl & 3 == 1:
                    # as text
                    self.exportFile.write(
                            "important/encoding/text  storeHint/%s\n" %
                            shText)
                else:
                    # as binary
                    self.exportFile.write(
                            "important/encoding/base64  storeHint/%s\n" %
                            shText)

            if cl & 3 == 1:
                # as text
                datablock = StringOps.fileContentToUnicode(
                        StringOps.lineendToInternal(datablock))

                self.exportFile.write(datablock)

            else:
                # as binary
                self.exportFile.write(base64BlockEncode(datablock))


        found = set()
        try:
            for unifName, datablock in self.wikiDocument.getWikiData()\
                    .iterAllDataBlocks():
                        
                if unifName in found:
                    continue
                else:
                    found.add(unifName)
                
#                     try:
#                         sh = self.wikiDocument.guessDataBlockStoreHint(unifName)
#                     except:

                writeDatablock(unifName, datablock,
                        Consts.DATABLOCK_STOREHINT_INTERN)
                

        except _SeparatorFoundException:
            raise
        except:
            traceback.print_exc()
            
        try:
            for unifName in self.wikiDocument.getDataBlockUnifNamesStartingWith(""):
                if unifName in found:
                    continue
                else:
                    found.add(unifName)
                
                if self._getDatablocksClass(unifName) == 0:
                    continue
                
                try:
                    datablock = self.wikiDocument.retrieveDataBlock(unifName)
                    writeDatablock(unifName, datablock,
                        Consts.DATABLOCK_STOREHINT_INTERN)

                except:
                    traceback.print_exc()

        except _SeparatorFoundException:
            raise
        except:
            traceback.print_exc()
        


    def _recoveryExportWikiWords(self):
        def writeWord(word, content, modified, created, visited):
            if isinstance(content, Consts.BYTETYPES):
                content = StringOps.contentToUnicode(content)

            self.exportFile.writeSeparator()

            self.exportFile.write("wikipage/%s\n" % word)
            
            # Do not use StringOps.strftimeUB here as its output
            # relates to local time, but we need UTC here.
            timeStrings = []
            for ts in (modified, created, visited):
                try:
                    tstr = str(time.strftime("%Y-%m-%d/%H:%M:%S",
                            time.gmtime(ts)))
                except ValueError:
                    print("bad timestamp", repr(ts))
                    traceback.print_exc()
                    tstr = str(time.strftime("%Y-%m-%d/%H:%M:%S",
                            time.gmtime(0)))

                timeStrings.append(tstr)


#             timeStrings = [unicode(time.strftime(
#                     "%Y-%m-%d/%H:%M:%S", time.gmtime(ts)))
#                     for ts in (modified, created, visited)]

            self.exportFile.write("%s  %s  %s\n" % tuple(timeStrings))
            self.exportFile.write(content)


        found = set()

        try:
            for word, content, modified, created, visited in \
                    self.wikiDocument.getWikiData().iterAllWikiPages():

                word = StringOps.contentToUnicode(word)

                if word in found:
                    continue
                else:
                    found.add(word)

                writeWord(word, content, modified, created, visited)

        except _SeparatorFoundException:
            raise
        except:
            traceback.print_exc()


        try:
            for word in self.wikiDocument.getWikiData().getAllDefinedWikiPageNames():
                if word in found:
                    continue
                else:
                    found.add(word)
                
                try:
                    content = self.wikiDocument.getWikiData().getContent(word)
                    try:
                        modified, created, visited = self.wikiDocument\
                                .getWikiData().getTimestamps(word)
                    except:
                        traceback.print_exc()
                        modified, created, visited = 0, 0, 0
                    
                    writeWord(word, content, modified, created, visited)
                except:
                    traceback.print_exc()

        except _SeparatorFoundException:
            raise
        except:
            traceback.print_exc()


    def recoveryExport(self, wikiDocument, exportDest, progressHandler):
        """
        Export in recovery mode
        
        wikiDocument -- WikiDocument object
        exportDest -- Path to destination directory or file to export to
        """
        self.wikiDocument = wikiDocument
        self.exportDest = exportDest
        self.exportFile = None
        self.rawExportFile = None
        self.firstSeparatorCallDone = False
        
        self.formatVer = 1
        
        try:
            for tryNumber in range(35):
                self.separator = "-----%s-----" % createRandomString(25)
                try:
                    self.rawExportFile = open(pathEnc(self.exportDest), "w")

                    # Only UTF-8 mode currently
                    self.rawExportFile.write(BOM_UTF8)
                    self.exportFile = _SeparatorWatchUtf8Writer(
                            self.rawExportFile, self.separator, "replace")

#                     self.wikiPageWriter = MultiPageTextWikiPageWriter(
#                             self.wikiDocument, self.exportFile,
#                             self.writeVersionData, self.formatVer)

                    # Identifier line with file format
                    self.exportFile.write("Multipage text format %i\n" %
                            self.formatVer)
                    # Separator line
                    self.exportFile.write("Separator: %s\n" % self.separator)

                    self._recoveryExportDatablocks()
                    self._recoveryExportWikiWords()
                    
                    break
                except _SeparatorFoundException:
                    if self.exportFile is not None:
                        self.exportFile.flush()
                        self.exportFile = None
        
                    if self.rawExportFile is not None:
                        self.rawExportFile.close()
                        self.rawExportFile = None

            else:
                raise ExportException(_("No usable separator found"))
        finally:
            if self.exportFile is not None:
                self.exportFile.flush()
                self.exportFile = None

            if self.rawExportFile is not None:
                self.rawExportFile.close()
                self.rawExportFile = None





def describeExportersV01(mainControl):
    return (TextExporter, MultiPageTextExporter)


