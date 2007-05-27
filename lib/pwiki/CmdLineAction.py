import sys, os, getopt

import urllib_red as urllib

import wx
# from wxPython.wx import *

from StringOps import mbcsDec, wikiUrlToPathWordAndAnchor

import Exporters


class CmdLineAction:
    """
    This class parses command line options, provides necessary information
    and performs actions
    """
    
    def __init__(self, sargs):
        """
        sargs -- stripped args (normally sys.args[1:])
        """
        self.wikiToOpen = None  # Path to wiki to open
                # (interpreted by PersonalWikiFrame)
        self.wikiWordToOpen = None  # Name of wiki word to open
                # (interpreted by PersonalWikiFrame)
        self.anchorToOpen = None   # Name of anchor to open in wiki word
        self.exitFinally = False   # Exit WikidPad when done
                # (interpreted by PersonalWikiFrame)
        self.showHelp = False   # Show help text?
        self.cmdLineError = False   # Command line couldn't be interpreted
        self.exportWhat = None   # String identifying what to export
        self.exportType = None   # Export into which type of data?
        self.exportDest = None   # Destination path to dir/file
        self.exportCompFn = False   # Export with compatible filenames?

        if len(sargs) == 0:
            return
            
        if sargs[0][0] != "-":
            # Old style, mainly used by the system

            # mbcs decoding of parameters
            sargs = [mbcsDec(a, "replace")[0] for a in sargs]
            self.wikiToOpen = sargs[0]
            if self.wikiToOpen.startswith("wiki:"):
                self.wikiToOpen, self.wikiWordToOpen, self.anchorToOpen = \
                        wikiUrlToPathWordAndAnchor(self.wikiToOpen)
#                 self.wikiToOpen = urllib.url2pathname(self.wikiToOpen)
#                 self.wikiToOpen = self.wikiToOpen.replace("wiki:", "")

            if len(sargs) > 1:
                self.wikiWordToOpen = sargs[1]

            return
            
        # New style
        try:
            opts, rargs = getopt.getopt(sargs, "hw:p:x",
                    ["help", "wiki=", "page=", "exit", "export-what=",
                    "export-type=", "export-dest=", "export-compfn", "anchor"])
        except getopt.GetoptError:
            self.cmdLineError = True
            return

        for o, a in opts:
            if o in ("-h", "--help"):
                self.showHelp = True
            elif o in ("-w", "--wiki"):
                self.wikiToOpen = mbcsDec(a, "replace")[0]
            elif o in ("-p", "--page"):
                self.wikiWordToOpen = mbcsDec(a, "replace")[0]
            elif o == "--anchor":
                self.anchorToOpen = mbcsDec(a, "replace")[0]
            elif o in ("-x", "--exit"):
                self.exitFinally = True
            elif o == "--export-what":
                self.exportWhat = mbcsDec(a, "replace")[0]
            elif o == "--export-type":
                self.exportType = mbcsDec(a, "replace")[0]
            elif o == "--export-dest":
                self.exportDest = mbcsDec(a, "replace")[0]
            elif o == "--export-compfn":
                self.exportCompFn = True

    def actionBeforeShow(self, pWiki):
        """
        Actions to do before the main frame is shown
        """
        self.exportAction(pWiki)
        
        if self.showHelp:
            self.showCmdLineUsage(pWiki)
            

    def exportAction(self, pWiki):
        if not (self.exportWhat or self.exportType or self.exportDest):
            return # No export
            
        if not (self.exportWhat and self.exportType and self.exportDest):
            # but at least one of the necessary options is missing
            self.showCmdLineUsage(pWiki,
                    u"To export, all three export options must be set.\n\n")
            return

        # Handle self.exportWhat
        wordList = None
        if self.exportWhat in (u"page", u"word"):
            # single page
            wordList = [self.wikiWordToOpen]
        elif self.exportWhat == u"subtree":
            # subtree
            wordList = pWiki.getWikiData().getAllSubWords([self.wikiWordToOpen])
        elif self.exportWhat == u"wiki":
            # whole wiki
            wordList = pWiki.getWikiData().getAllDefinedWikiPageNames()
        else:
            self.showCmdLineUsage(pWiki,
                    u"Value for --export-what can be page, subtree or wiki.\n\n")
            return

#             # custom list
#             wordList = pWiki.getWikiData().search(self.listPagesOperation, True)

        # Handle self.exportType
        exporterList = []
        for ob in Exporters.describeExporters(pWiki):   # TODO search plugins
            for tp in ob.getExportTypes(None):
                exporterList.append((ob, tp[0]))

        exporter = None
        for ei in exporterList:
            if ei[1] == self.exportType:
                exporter = ei[0]
                break
                
        if exporter is None:
            exList = ", ".join([ei[1] for ei in exporterList])
            
            self.showCmdLineUsage(pWiki,
                    u"Value for --export-type can be one of:\n%s\n\n" % exList)
            return

        exporter.export(pWiki.getWikiDataManager(), wordList,
                self.exportType, self.exportDest, 
                self.exportCompFn, exporter.getAddOpt(None))



    USAGE = \
"""Options:

    -h, --help: Show this message box
    -w, --wiki  <wiki path>: set the wiki to open on startup
    -p, --page  <page name>: set the page to open on startup
    -x, --exit: exit immediately after performing command line actions
    --export-what <what>: choose if you want to export page, subtree or wiki
    --export-type <type>: tag of the export type
    --export-dest <destination path>: path of destination directory for export
    --export-compfn: Use compatible filenames on export
"""
        
    def showCmdLineUsage(self, pWiki, addRemark=u""):
        """
        Show dialog with addRemark and command line usage information.
        """
        wx.MessageBox(addRemark + self.USAGE, "Usage information",
                style=wx.OK, parent=pWiki)





