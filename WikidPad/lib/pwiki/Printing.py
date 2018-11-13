## import hotshot
## _prof = hotshot.Profile("hotshot.prf")


import wx, wx.xrc

from .wxHelper import *

from . import PluginManager


from .SearchAndReplaceDialogs import SearchWikiDialog   # WikiPageListConstructionDialog
from .SearchAndReplace import SearchReplaceOperation  # ListWikiPagesOperation




class PrintMainDialog(wx.Dialog):
    
#     EXPORT_TO_PLAINT_TEXT = 0
#     EXPORT_TO_HTML = 1
#     EXPORT_TO_HTML_WEBKIT = 2
    
    def __init__(self, mainControl, ID, title="Print",
                 pos=wx.DefaultPosition, size=wx.DefaultSize, exportTo=None):
        wx.Dialog.__init__(self)

        self.mainControl = mainControl
        self.printer = self.mainControl.printer
        
#         self.plainTextFontDesc = self.printer.plainTextFontDesc

        res = wx.xrc.XmlResource.Get()
        res.LoadDialog(self, self.mainControl, "PrintMainDialog")
        
        self.ctrls = XrcControls(self)
        
        self.ctrls.chSelectedSet.SetSelection(self.printer.selectionSet)
        
#         # If Webkit available allow to use it for HTML print
#         if WKHtmlWindow:
#             self.ctrls.chExportTo.Append(_(u'HTML (Webkit)'))
#             
#         if exportTo >= 0:
#             self.ctrls.chExportTo.SetSelection(exportTo)
# 
#         self.ctrls.tfWikiPageSeparator.SetValue(
#                 self.mainControl.configuration.get("main",
#                 "print_plaintext_wpseparator"))

        self.ctrls.btnPrint.SetId(wx.ID_OK)
        self.ctrls.btnCancel.SetId(wx.ID_CANCEL)

        self.mainControl.saveAllDocPages()
        self.mainControl.getWikiData().commit()


        self.supportedPrintTypes = set()

        self.emptyPanel = None

        printList = [] # List of tuples (<print object>, <print tag>,
                       # <readable description>, <additional options panel>)

        addOptSizer = LayerSizer()

        for obtp in list(PluginManager.getSupportedPrintTypes(self.mainControl,
                self.ctrls.additOptions).values()):
            panel = obtp[3]
            if panel is None:
                if self.emptyPanel is None:
                    # Necessary to avoid a crash        
                    self.emptyPanel = wx.Panel(self.ctrls.additOptions)

                panel = self.emptyPanel
            else:
                pass

            # Add Tuple (Print object, print type tag,
            #     print type description, additional options panel)
            printList.append((obtp[0], obtp[1], obtp[2], panel))
            self.supportedPrintTypes.add(obtp[1])
            addOptSizer.Add(panel)

        mainControl.getCollator().sortByItem(printList, 2)

        self.ctrls.additOptions.SetSizer(addOptSizer)
        self.ctrls.additOptions.SetMinSize(addOptSizer.GetMinSize())

        self.ctrls.additOptions.Fit()
        self.Fit()

        self.printList = printList

        for e in self.printList:
            e[3].Show(False)
            e[3].Enable(False)
            self.ctrls.chExportTo.Append(e[2])

        if exportTo is None:
            exportTo = self.mainControl.getConfig().get("main",
                    "print_lastDialogTag", "")

        selection = 0
        
        for i, e in enumerate(self.printList):
            if exportTo == e[1]:
                selection = i
                break

        self.ctrls.chExportTo.SetSelection(selection)  
        self._refreshForPtype()

        # Fixes focus bug under Linux
        self.SetFocus()

        self.Bind(wx.EVT_CHOICE, self.OnExportTo, id=GUI_ID.chExportTo)
        self.Bind(wx.EVT_CHOICE, self.OnChSelectedSet, id=GUI_ID.chSelectedSet)

        self.Bind(wx.EVT_BUTTON, self.OnPreview, id=GUI_ID.btnPreview)
        self.Bind(wx.EVT_BUTTON, self.OnPageSetup, id=GUI_ID.btnPageSetup)
#         self.Bind(wx.EVT_BUTTON, self.OnChoosePlainTextFont, id=GUI_ID.btnChoosePlainTextFont)
        self.Bind(wx.EVT_BUTTON, self.OnPrint, id=wx.ID_OK)


    def _transferOptionsToPrinter(self):
        sel = self.ctrls.chSelectedSet.GetSelection()
        if sel == -1:
            sel = self.printer.selectionSet
            
        ob, ptype, desc, panel = \
                self.printList[self.ctrls.chExportTo.GetSelection()][:4]

#         self.printer.setStdOptions(sel, ob, ptype, ob.getAddOpt(panel),
#                 self.plainTextFontDesc,
#                 self.ctrls.tfWikiPageSeparator.GetValue())

        self.printer.setStdOptions(sel, ob, ptype, ob.getAddOpt(panel))


    def _refreshForPtype(self):
        for e in self.printList:
            e[3].Show(False)
            e[3].Enable(False)

        ob, etype, desc, panel = \
                self.printList[self.ctrls.chExportTo.GetSelection()][:4]

        # Enable appropriate addit. options panel
        panel.Enable(True)
        panel.Show(True)


    def OnExportTo(self, evt):
        self._refreshForPtype()
        self.mainControl.getConfig().set("main", "print_lastDialogTag",
                self.printList[self.ctrls.chExportTo.GetSelection()][1])
        evt.Skip()


    def OnPreview(self, evt):
        ## _prof.start()
        self._transferOptionsToPrinter()
        self.printer.doPreview()
        ## _prof.stop()

    def OnPrint(self, evt):
        self._transferOptionsToPrinter()
        if self.printer.doPrint():
            self.EndModal(wx.ID_OK)


    def OnChSelectedSet(self, evt):
        selset = self.ctrls.chSelectedSet.GetSelection()
        if selset == 3:  # Custom
#             dlg = WikiPageListConstructionDialog(self, self.mainControl, -1, 
#                     value=self.printer.listPagesOperation)
            dlg = SearchWikiDialog(self, self.mainControl, -1,
                    value=self.printer.listPagesOperation)
            if dlg.ShowModal() == wx.ID_OK:
                self.printer.listPagesOperation = dlg.getValue()
            dlg.Destroy()


#     def OnChoosePlainTextFont(self, evt):
#         fontdata = wx.FontData()
#         if self.plainTextFontDesc:
#             font = wx.FontFromNativeInfoString(self.plainTextFontDesc)
#             fontdata.SetInitialFont(font)
#             
#         dlg = wx.FontDialog(self, fontdata)
#         if dlg.ShowModal() == wx.ID_OK:
#             # fontdata = dlg.GetFontData()
#             font = dlg.GetFontData().GetChosenFont()
#             self.plainTextFontDesc = font.GetNativeFontInfoDesc()
#         
#         dlg.Destroy()


    def OnPageSetup(self, evt):
        pageDialog = wx.PageSetupDialog(self.mainControl,
                self.printer.getPageSetupDialogData())
        pageDialog.ShowModal();
        
        self.printer.setOptionsByPageSetup(pageDialog.GetPageSetupData())

        pageDialog.Destroy()

        


class Printer:
    def __init__(self, pWiki):
        self.pWiki = pWiki
        # self.printData and self.psddata are only filled with values on demand
        # this avoids error messages if no printer is installed
        self.printData = None
        self.psddata = None

        self.selectionSet = 0
#         self.printType = 0  # 0: Plain text; 1: HTML; 2: HTML (Webkit)
        self.printObject = None
        self.printType = None
        self.addOpt = None
        self.listPagesOperation = SearchReplaceOperation()

        self.plainTextFontDesc = self.pWiki.configuration.get(
                "main", "print_plaintext_font")
        
    def _ensurePrintData(self):
        """
        Fill fields with PrintData and PageSetupDialogData if not yet done.
        """
        if self.printData is None:
            self.printData = wx.PrintData()
            self.psddata = wx.PageSetupDialogData(self.printData)

            try:
                margintext = self.pWiki.configuration.get(
                        "main", "print_margins")
                margins = list(map(int, margintext.split(",")))
            except:
                margins = [0, 0, 0, 0]  # TODO Perhaps error message
                
            self.psddata.SetMarginTopLeft(wx.Point(margins[0], margins[1]))
            self.psddata.SetMarginBottomRight(wx.Point(margins[2], margins[3]))


    def setStdOptions(self, selectionSet, ob, ptype, addOpt):
        self.selectionSet = selectionSet
        self.printObject = ob
        self.printType = ptype
        self.addOpt = addOpt

#         self.plainTextFontDesc = plainTextFontDesc
#         self.pWiki.configuration.set("main", "print_plaintext_font",
#                 plainTextFontDesc)
#         self.pWiki.configuration.set("main", "print_plaintext_wpseparator",
#                 wpSeparator)


    def buildWordList(self):
        from . import SearchAndReplace as Sar

        # Create wordList (what to export)
        selset = self.selectionSet
        root = self.pWiki.getCurrentWikiWord()
        
        if root is None and selset in (0, 1):
            self.pWiki.displayErrorMessage(
                    _("No real wiki word selected as root"))
            return

        lpOp = Sar.ListWikiPagesOperation()

        if selset == 0:
            # single page
            item = Sar.ListItemWithSubtreeWikiPagesNode(lpOp, [root], 0)
            lpOp.setSearchOpTree(item)
            lpOp.ordering = "asroottree"  # Slow, but more intuitive
        elif selset == 1:
            # subtree
            item = Sar.ListItemWithSubtreeWikiPagesNode(lpOp, [root], -1)
            lpOp.setSearchOpTree(item)
            lpOp.ordering = "asroottree"  # Slow, but more intuitive
        elif selset == 2:
            # whole wiki
            item = Sar.AllWikiPagesNode(lpOp)
            lpOp.setSearchOpTree(item)
            lpOp.ordering = "asroottree"  # Slow, but more intuitive
        else:
            # custom list
            lpOp = self.listPagesOperation

        sarOp = Sar.SearchReplaceOperation()
        sarOp.listWikiPagesOp = lpOp
        wordList = self.pWiki.getWikiDocument().searchWiki(sarOp, True)
 
        return wordList


    def showPrintMainDialog(self, exportTo=None):
        self._ensurePrintData()
        dlg = PrintMainDialog(self.pWiki, -1, exportTo=exportTo)
        dlg.CenterOnParent(wx.BOTH)

        result = dlg.ShowModal()
        dlg.Destroy()

    def getPageSetupDialogData(self):
        return self.psddata

    def setOptionsByPageSetup(self, pageSetupData):
        """
        Store options contained in a wxPageSetupData object. It makes its
        own copies of the data, so the original data can be destroyed.
        """
        self.psddata = wx.PageSetupDialogData(pageSetupData)

        # this makes a copy of the wx.PrintData instead of just saving
        # a reference to the one inside the PrintDialogData that will
        # be destroyed when the dialog is destroyed
        self.printData = wx.PrintData(pageSetupData.GetPrintData())

        tl = self.psddata.GetMarginTopLeft()
        br = self.psddata.GetMarginBottomRight()

        margins = [tl.x, tl.y, br.x, br.y]
        margtext = ",".join(map(str, margins))
        self.pWiki.configuration.set("main", "print_margins", margtext)


    def getPrintData(self):
        return self.printData


    def doPreview(self):
#         if self.printType == 1:
#             printObj = HtmlPrint()
#             printObj.setContext(self.pWiki, self, self.pWiki.getWikiDocument(),
#                     self.buildWordList(), "html_simple", None, None)
#         elif self.printType == 2:
#             printObj = HtmlWKPrint()
#             printObj.setContext(self.pWiki, self, self.pWiki.getWikiDocument(),
#                     self.buildWordList(), "html_webkit", None, None)
#         else: # self.printType == 0:
#             printObj = PlainTextPrint()
#             printObj.setContext(self.pWiki, self, self.pWiki.getWikiDocument(),
#                     self.buildWordList(), "plain_text", None, None)
# 
        return self.printObject.doPreview(self, self.pWiki.getWikiDocument(),
                self.buildWordList(), self.printType, self.addOpt)


    def doPrint(self):
#         if self.printType == 1:
#             printObj = HtmlPrint()
#             printObj.setContext(self.pWiki, self, self.pWiki.getWikiDocument(),
#                     self.buildWordList(), "html_simple", None)
#         elif self.printType == 2:
#             printObj = HtmlWKPrint()
#             printObj.setContext(self.pWiki, self, self.pWiki.getWikiDocument(),
#                     self.buildWordList(), "html_webkit", None)
#         else:
#             printObj = PlainTextPrint()
#             printObj.setContext(self.pWiki, self, self.pWiki.getWikiDocument(),
#                     self.buildWordList(), "plain_text", None)

        return self.printObject.doPrint(self, self.pWiki.getWikiDocument(),
                self.buildWordList(), self.printType, self.addOpt)






