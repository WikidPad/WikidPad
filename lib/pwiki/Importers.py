# from Enum import Enumeration
import os, string, re, traceback
from os.path import join, exists, splitext
import sys
# import shutil
# from time import localtime
import urllib_red as urllib

# import wx, wx.xrc

from wxHelper import XrcControls

# import WikiFormatting
from StringOps import *
# 
from WikiExceptions import WikiWordNotFoundException, ImportException
# import WikiFormatting
# import PageAst



class MultiPageTextImporter:
    def __init__(self, mainControl):
        """
        mainControl -- Currently PersonalWikiFrame object
        """
        self.mainControl = mainControl


    def getImportTypes(self, guiparent):
        """
        Return sequence of tuples with the description of import types provided
        by this object. A tuple has the form (<imp. type>,
            <human readable description>, <panel for add. options or None>)
        If panels for additional options must be created, they should use
        guiparent as parent
        """
        return (
                (u"multipage_text", "Multipage text", None),
                )


    def getImportSourceWildcards(self, importType):
        """
        If an export type is intended to go to a file, this function
        returns a (possibly empty) sequence of tuples
        (wildcard description, wildcard filepattern).
        
        If an export type goes to a directory, None is returned
        """
        if importType == u"multipage_text":
            return (("Multipage files (*.mpt)", "*.mpt"),
                    ("Text file (*.txt)", "*.txt")) 

        return None


    def getAddOptVersion(self):
        """
        Returns the version of the additional options information returned
        by getAddOpt(). If the return value is -1, the version info can't
        be stored between application sessions.
        
        Otherwise, the addopt information can be stored between sessions
        and can later handled back to the doImport method of the object
        without previously showing the import dialog.
        """
        return 0


    def getAddOpt(self, addoptpanel):
        """
        Reads additional options from panel addoptpanel.
        If getAddOptVersion() > -1, the return value must be a sequence
        of simple string, unicode and/or numeric objects. Otherwise, any object
        can be returned (normally the addoptpanel itself)
        """
        return ()


    def doImport(self, wikiDataManager, importType, importSrc,
            compatFilenames, addOpt):
        """
        Run import operation.
        
        wikiDataManager -- WikiDataManager object
        importType -- string tag to identify how to import
        importDest -- Path to source directory or file to import from
        compatFilenames -- Should the filenames be decoded from the lowest
                           level compatible?
        addOpt -- additional options returned by getAddOpt()
        """
        try:
            self.rawImportFile = open(pathEnc(importSrc), "rU")
        except IOError:
            raise ImportException("Opening import file failed")
            
        wikiData = wikiDataManager.getWikiData()
            
        try:
            try:
                # Wrap input file to convert format
                bom = self.rawImportFile.read(len(BOM_UTF8))
                if bom != BOM_UTF8:
                    self.rawImportFile.seek(0)
                    self.importFile = mbcsReader(self.rawImportFile, "replace")
                else:
                    self.importFile = utf8Reader(self.rawImportFile, "replace")
                
                line = self.importFile.readline()
                if line.startswith("#!"):
                    # Skip initial line with #! to allow execution as shell script
                    line = self.importFile.readline()

                if not line.startswith("Multipage text format "):
                    raise ImportException("Bad file format, header not detected")
                
                # Following in the format identifier line is a version number
                # of the file format
                self.formatVer = int(line[22:-1])
                
                if self.formatVer > 0:
                    raise ImportException(
                            "File format number %i is not supported" %
                            self.formatVer)

                # Next is the separator line
                line = self.importFile.readline()
                if not line.startswith("Separator: "):
                    raise ImportException("Bad file format, header not detected")
                    
                self.separator = line[11:]
                
                formatting = self.mainControl.getFormatting()
                
                while True:
                    # Read next wikiword
                    line = self.importFile.readline()
                    if line == u"":
                        break

                    wikiWord = line[:-1]
                    if not formatting.isNakedWikiWord(wikiWord):
                        raise ImportException("Bad wiki word: %s" % wikiWord)

                    content = []                    
                    while True:
                        # Read lines of wikiword
                        line = self.importFile.readline()
                        if line == u"":
                            # The last page in mpt file without separator
                            # ends as the real wiki page
                            content = u"".join(content)
                            break
                        
                        if line == self.separator:
                            if len(content) > 0:
                                # Iff last line of mpt page is empty, the original
                                # page ended with a newline, so remove last
                                # character (=newline)

                                content[-1] = content[-1][:-1]
                                content = u"".join(content)
                                break
                                
                        content.append(line)
                    
                    page = wikiDataManager.getWikiPageNoError(wikiWord)

                    page.replaceLiveText(content)
#                     page.save(content)
#                     page.update(content, False)

            except ImportException:
                raise
            except Exception, e:
                traceback.print_exc()
                raise ImportException(unicode(e))

        finally:
            self.rawImportFile.close()



def describeImporters(mainControl):
    return (MultiPageTextImporter(mainControl),)

