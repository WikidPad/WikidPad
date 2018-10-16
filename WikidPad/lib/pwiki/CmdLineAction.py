import sys, os, getopt, traceback

import wx

from .WikiExceptions import *

from .StringOps import mbcsDec, wikiUrlToPathWordAndAnchor

from . import PluginManager


class CmdLineAction:
    """
    This class parses command line options, provides necessary information
    and performs actions
    """
    NOT_SET = -1  # Option isn't set to a value yet
    
    REBUILD_NONE = 0 # No rebuild
    REBUILD_EXT = 1 # Update externally modified files
    REBUILD_FULL = 2 # Full rebuild

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
        self.exportSaved = None  # Name of saved export instead
        self.continuousExportSaved = None  # Name of saved export to run as continuous export
        self.rebuild = self.NOT_SET  # Rebuild the wiki
        self.frameToOpen = 1  # Open wiki in new frame? (yet unrecognized) 
                # 1:New frame, 2:Already open frame, 0:Use config default 
        self.activeTabNo = -1  # Number of tab to activate
                # (interpreted by PersonalWikiFrame)
        self.lastTabsSubCtrls = None  # Corresponding list of subcontrol names
                # for each wikiword to open
        self.noRecent = False  # Do not modify history of recently opened wikis

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
                    "export-type=", "export-dest=", "export-compfn",
                    "export-saved=", "continuous-export-saved=",
                    "anchor",
                    "rebuild", "update-ext", "no-recent", "preview", "editor"])
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
            elif o == "--export-saved":
                self.exportSaved = mbcsDec(a, "replace")[0]
            elif o == "--continuous-export-saved":
                self.continuousExportSaved = mbcsDec(a, "replace")[0]
            elif o == "--rebuild":
                self.rebuild = self.REBUILD_FULL
            elif o == "--update-ext":
                self.rebuild = self.REBUILD_EXT
            elif o == "--no-recent":                
                self.noRecent = True
            elif o == "--preview":
                self._fillLastTabsSubCtrls(len(wikiWordsToOpen), "preview")
            elif o == "--editor":
                self._fillLastTabsSubCtrls(len(wikiWordsToOpen), "textedit")


        if len(wikiWordsToOpen) > 0:
            self.wikiWordsToOpen = tuple(wikiWordsToOpen)


#         self._fillLastTabsSubCtrls(len(wikiWordsToOpen))


    def _fillLastTabsSubCtrls(self, wwoLen, newItem=None):
        """
        If self.lastTabsSubCtrls contains at least one item, fill it up
        to length of wwoLen with last item. If newItem is not None, it is
        appended.
        If newItem is None (done by final call after collecting) self.lastTabsSubCtrls
        shortened to length of wwoLen. If wwoLen is 0, the last item is preserved
        to ensure that the setting "--preview" is processed when opening wiki
        with previously opened words.
        """
        if not self.lastTabsSubCtrls:
            if newItem is not None:
                # Fill up already mentioned words with textedit subControl setting
                self.lastTabsSubCtrls = ["textedit"] * wwoLen + [newItem]

            return


        if len(self.lastTabsSubCtrls) < wwoLen:
                self.lastTabsSubCtrls += [self.lastTabsSubCtrls[-1]] * \
                        (wwoLen - len(self.lastTabsSubCtrls))

        if newItem is not None:
            self.lastTabsSubCtrls.append(newItem)
        else:
            if wwoLen > 0:
                self.lastTabsSubCtrls = self.lastTabsSubCtrls[:wwoLen]
            else:
                self.lastTabsSubCtrls = self.lastTabsSubCtrls[-1:]

            if not self.lastTabsSubCtrls:
                self.lastTabsSubCtrls = None


    def setWikiToOpen(self, wto):
        if wto.startswith("wiki:"):
            self.wikiToOpen, wikiWordToOpen, self.anchorToOpen = \
                    wikiUrlToPathWordAndAnchor(wto)

            self.wikiWordsToOpen = (wikiWordToOpen,)
#                 self.wikiToOpen = urllib.url2pathname(self.wikiToOpen)
#                 self.wikiToOpen = self.wikiToOpen.replace("wiki:", "")
        else:
            self.wikiToOpen = wto


    def inheritFrom(self, cmdline):
        """
        Inherits some settings from another commandline. Some special settings
        should be persistent when opening one frame from another.
        """
        self.noRecent = cmdline.noRecent


    def actionBeforeShow(self, pWiki):
        """
        Actions to do before the main frame is shown
        """
        self.rebuildAction(pWiki)
        self.exportAction(pWiki)
        self.continuousExportAction(pWiki)

        if self.showHelp:
            self.showCmdLineUsage(pWiki)


    def rebuildAction(self, pWiki):
        if self.rebuild == self.REBUILD_FULL:
            pWiki.rebuildWiki(True)
        elif self.rebuild == self.REBUILD_EXT:
            pWiki.updateExternallyModFiles()


    def _runSavedExport(self, pWiki, savedExportName, continuousExport):
        from . import Serialization, PluginManager, Exporters, SearchAndReplace

        exportList = Exporters.retrieveSavedExportsList(pWiki,
                pWiki.getWikiData(), continuousExport)
        xmlNode = None
        for exportName, xn in exportList:
            if exportName == savedExportName:
                xmlNode = xn
                break

        if xmlNode is None:
            self.showCmdLineUsage(pWiki,
                    _("Saved export '%s' is unknown.") % savedExportName + "\n\n")
            return


        # TODO: Refactor, it is based on AdditionalDialogs.ExportDialog._showExportProfile
        try:
            etypeProfile = Serialization.serFromXmlUnicode(xmlNode,
                    "exportTypeName")

            try:  
                exporter, etype, desc, panel = PluginManager.getSupportedExportTypes(
                        pWiki, None, continuousExport)[etypeProfile]
            except KeyError:
                self.showCmdLineUsage(pWiki,
                        _("Export type '%s' of saved export is not supported") %
                        etypeProfile + "\n\n")
                return

            addOptXml = Serialization.findXmlElementFlat(xmlNode,
                    "additionalOptions")

            addOptVersion = int(addOptXml.getAttribute("version"))

            if addOptVersion != exporter.getAddOptVersion():
                self.showCmdLineUsage(pWiki,
                        _("Saved export uses different version for additional "
                        "options than current export\nExport type: '%s'\n"
                        "Saved export version: %i\nCurrent export version: %i") %
                        (etypeProfile, addOptVersion, exporter.getAddOptVersion()) +
                        "\n\n")
                return 

            if addOptXml.getAttribute("type") != "simpleTuple":
                self.showCmdLineUsage(pWiki,
                        _("Type of additional option storage ('%s') is unknown") %
                        addOptXml.getAttribute("type") + "\n\n")
                return

            pageSetXml = Serialization.findXmlElementFlat(xmlNode, "pageSet")

            sarOp = SearchAndReplace.SearchReplaceOperation()
            sarOp.serializeFromXml(pageSetXml)
            
            
            addOpt = Serialization.convertTupleFromXml(addOptXml)

#                 self.ctrls.chSelectedSet.SetSelection(3)
#                 self.ctrls.chExportTo.SetSelection(sel)
#                 exporter.setAddOpt(addOpt, panel)

            exportDest = Serialization.serFromXmlUnicode(xmlNode,
                    "destinationPath")

#                 self._refreshForEtype()

        except SerializationException as e:
            self.showCmdLineUsage(pWiki, _("Error during retrieving "
                    "saved export: ") + e.message + "\n\n")


        if not continuousExport:
            wordList = pWiki.getWikiDocument().searchWiki(sarOp,
                    True)
            try:
                exporter.export(pWiki.getWikiDocument(), wordList,
                        etype, exportDest, self.exportCompFn, addOpt, None)
            except (IOError, WindowsError) as e:
                traceback.print_exc()
                # unicode(e) returns different result for IOError
                self.showCmdLineUsage(pWiki, str(e) + "\n\n") 
                return
        else:
            exporter.startContinuousExport(pWiki.getWikiDocument(),
                    sarOp, etype, exportDest, self.exportCompFn, addOpt,
                    None)
            pWiki.continuousExporter = exporter



    def exportAction(self, pWiki):
        if not (self.exportWhat or self.exportType or self.exportDest or
                self.exportSaved):
            return # No export

        if self.exportSaved:
            if self.exportWhat or self.exportType or self.exportDest:
                self.showCmdLineUsage(pWiki,
                        _("If saved export is given, 'what', 'type' and 'dest' aren't allowed.") +
                        "\n\n")
                return

            self._runSavedExport(pWiki, self.exportSaved, False)
            return


        if not (self.exportWhat and self.exportType and self.exportDest):
            # but at least one of the necessary options is missing
            self.showCmdLineUsage(pWiki,
                    _("To export, all three export options ('what', 'type' and 'dest') must be set.") + 
                    "\n\n")
            return

        # Handle self.exportWhat
        wordList = None
        if self.exportWhat in ("page", "word"):
            # single pages
            wordList = list(self.wikiWordsToOpen)
        elif self.exportWhat == "subtree":
            # subtree
            wordList = pWiki.getWikiData().getAllSubWords(
                    list(self.wikiWordsToOpen))
        elif self.exportWhat == "wiki":
            # whole wiki
            wordList = pWiki.getWikiData().getAllDefinedWikiPageNames()
        else:
            self.showCmdLineUsage(pWiki,
                    _("Value for --export-what can be 'page', 'subtree' or 'wiki'.") + "\n\n")
            return

#             # custom list
#             wordList = pWiki.getWikiData().search(self.listPagesOperation, True)

        # Handle self.exportType
        exporterList = []
        for obtp in list(PluginManager.getSupportedExportTypes(
                pWiki, None).values()):
            exporterList.append((obtp[0], obtp[1]))
            
        pWiki.getCollator().sortByItem(exporterList, 1)

        exporter = None
        for ei in exporterList:
            if ei[1] == self.exportType:
                exporter = ei[0]
                break
                
        if exporter is None:
            exList = ", ".join([ei[1] for ei in exporterList])
            
            self.showCmdLineUsage(pWiki,
                    _("Value for --export-type can be one of:\n%s") % exList) + "\n\n"
            return

        try:
            exporter.export(pWiki.getWikiDocument(), wordList,
                    self.exportType, self.exportDest, 
                    self.exportCompFn, exporter.getAddOpt(None), None)
        except (IOError, WindowsError) as e:
            traceback.print_exc()
            # unicode(e) returns different result for IOError
            self.showCmdLineUsage(pWiki, str(e) + "\n\n") 
            return



    def continuousExportAction(self, pWiki):
        if not self.continuousExportSaved:
            return
        
        if self.exitFinally:
            self.showCmdLineUsage(pWiki,
                    _("Combination of --exit and --continuous-export-saved isn't allowed") + "\n\n")
            return
        
        self._runSavedExport(pWiki, self.continuousExportSaved, True)
            


    USAGE = \
N_("""Options:

    -h, --help: Show this message box
    -w, --wiki  <wiki path>: set the wiki to open on startup
    -p, --page  <page name>: set the page to open on startup
    -x, --exit: exit immediately after performing command line actions
    --export-what <what>: choose if you want to export page, subtree or wiki
    --export-type <type>: tag of the export type
    --export-dest <destination path>: path of destination directory for export
    --export-saved <name of saved export>: alternatively name of saved export to run
    --export-compfn: Use compatible filenames on export
    --continuous-export-saved <name of saved export>: continuous export to start with
    --rebuild: rebuild the Wiki database
    --update-ext: update externally modified wiki files
    --no-recent: Do not record opened wikis in recently opened wikis list
    --preview: If no pages are given, all opened pages from previous session
               are opened in preview mode. Otherwise all pages given after that
               option are opened in preview mode.
    --editor: Same as --preview but opens in text editor mode.

""")

    def showCmdLineUsage(self, pWiki, addRemark=""):
        """
        Show dialog with addRemark and command line usage information.
        """
        wx.MessageBox(addRemark + _(self.USAGE), _("Usage information"),
                style=wx.OK, parent=None)





