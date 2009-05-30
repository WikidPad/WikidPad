import sys, os, getopt

import urllib_red as urllib

import wx

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
        self.wikiWordsToOpen = None  # Name of wiki words to open
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
        self.rebuild = False # Rebuild the wiki
        self.frameToOpen = 1  # Open wiki in new frame? (yet unrecognized) 
                # 1:New frame, 2:Already open frame, 0:Use config default 

        if len(sargs) == 0:
            return
            
        if sargs[0][0] != "-":
            # Old style, mainly used by the system

            # mbcs decoding of parameters
            sargs = [mbcsDec(a, "replace")[0] for a in sargs]
            self.setWikiToOpen(sargs[0])

            if len(sargs) > 1:
                self.wikiWordsToOpen = (sargs[1],)

            return

        # New style
        try:
            opts, rargs = getopt.getopt(sargs, "hw:p:x",
                    ["help", "wiki=", "page=", "exit", "export-what=",
                    "export-type=", "export-dest=", "export-compfn", "anchor",
					"rebuild"])
        except getopt.GetoptError:
            self.cmdLineError = True
            return

        wikiWordsToOpen = []
        for o, a in opts:
            if o in ("-h", "--help"):
                self.showHelp = True
            elif o in ("-w", "--wiki"):
                self.wikiToOpen = mbcsDec(a, "replace")[0]
            elif o in ("-p", "--page"):
                wikiWordsToOpen.append(mbcsDec(a, "replace")[0])
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
            elif o == "--rebuild":
                self.rebuild = True

        if len(wikiWordsToOpen) > 0:
            self.wikiWordsToOpen = tuple(wikiWordsToOpen)


    def setWikiToOpen(self, wto):
        if wto.startswith("wiki:"):
            self.wikiToOpen, wikiWordToOpen, self.anchorToOpen = \
                    wikiUrlToPathWordAndAnchor(wto)

            self.wikiWordsToOpen = (wikiWordToOpen,)
#                 self.wikiToOpen = urllib.url2pathname(self.wikiToOpen)
#                 self.wikiToOpen = self.wikiToOpen.replace("wiki:", "")
        else:
            self.wikiToOpen = wto


    def actionBeforeShow(self, pWiki):
        """
        Actions to do before the main frame is shown
        """
        self.rebuildAction(pWiki)
        self.exportAction(pWiki)

        if self.showHelp:
            self.showCmdLineUsage(pWiki)


    def rebuildAction(self, pWiki):
        if self.rebuild:
            pWiki.rebuildWiki(True)

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
            # single pages
            wordList = list(self.wikiWordsToOpen)
        elif self.exportWhat == u"subtree":
            # subtree
            wordList = pWiki.getWikiData().getAllSubWords(
                    list(self.wikiWordsToOpen))
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
                self.exportCompFn, exporter.getAddOpt(None), None)


    USAGE = \
N_(u"""Options:

    -h, --help: Show this message box
    -w, --wiki  <wiki path>: set the wiki to open on startup
    -p, --page  <page name>: set the page to open on startup
    -x, --exit: exit immediately after performing command line actions
    --export-what <what>: choose if you want to export page, subtree or wiki
    --export-type <type>: tag of the export type
    --export-dest <destination path>: path of destination directory for export
    --export-compfn: Use compatible filenames on export
    --rebuild: rebuild the Wiki database
""")

    def showCmdLineUsage(self, pWiki, addRemark=u""):
        """
        Show dialog with addRemark and command line usage information.
        """
        wx.MessageBox(addRemark + _(self.USAGE), _(u"Usage information"),
                style=wx.OK, parent=pWiki)





