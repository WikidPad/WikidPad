import re

## import hotshot
## _prof = hotshot.Profile("hotshot.prf")


import wx, wx.xrc
# from wxPython.wx import *
# import wxPython.xrc as xrc

from wxHelper import *

from StringOps import escapeHtml, unescapeWithRe

from SearchAndReplaceDialogs import WikiPageListConstructionDialog
from SearchAndReplace import ListWikiPagesOperation


_CUT_RE = re.compile(ur"\n|\f| +|[^ \n\f]+",
        re.DOTALL | re.UNICODE | re.MULTILINE)



class PrintMainDialog(wx.Dialog):
    def __init__(self, pWiki, ID, title="Print",
                 pos=wx.DefaultPosition, size=wx.DefaultSize):
        d = wx.PreDialog()
        self.PostCreate(d)

        self.pWiki = pWiki
        self.printer = self.pWiki.printer
        
        self.plainTextFontDesc = self.printer.plainTextFontDesc

        res = wx.xrc.XmlResource.Get()
        res.LoadOnDialog(self, self.pWiki, "PrintMainDialog")
        
        self.ctrls = XrcControls(self)
        
        self.ctrls.chSelectedSet.SetSelection(self.printer.selectionSet)
        
        self.ctrls.tfWikiPageSeparator.SetValue(
                self.pWiki.configuration.get("main",
                "print_plaintext_wpseparator"))
#         # Necessary to avoid a crash        
#         emptyPanel = wxPanel(self.ctrls.additOptions)
#         emptyPanel.Fit()
#         
#         exporterList = [] # List of tuples (<exporter object>, <export tag>,
#                           # <readable description>, <additional options panel>)
#         
#         for ob in Exporters.describeExporters():   # TODO search plugins
#             for tp in ob.getExportTypes(self.ctrls.additOptions):
#                 panel = tp[2]
#                 if panel is None:
#                     panel = emptyPanel
#                 else:
#                     panel.Fit()
# 
#                 exporterList.append((ob, tp[0], tp[1], panel))
#         
#         self.ctrls.additOptions.Fit()
#         mins = self.ctrls.additOptions.GetMinSize()
#         
#         self.ctrls.additOptions.SetMinSize(wxSize(mins.width+10, mins.height+10))
#         self.Fit()
#         
#         self.exporterList = exporterList

        self.ctrls.btnPrint.SetId(wx.ID_OK)
        self.ctrls.btnCancel.SetId(wx.ID_CANCEL)
        
        self.pWiki.saveAllDocPages(force=True)
        self.pWiki.getWikiData().commit()
        
        # Fixes focus bug under Linux
        self.SetFocus()
        
#         for e in self.exporterList:
#             e[3].Show(False)
#             e[3].Enable(False)
#             self.ctrls.chExportTo.Append(e[2])
#             
#         # Enable first addit. options panel
#         self.exporterList[0][3].Enable(True)
#         self.exporterList[0][3].Show(True)
#         self.ctrls.chExportTo.SetSelection(0)       
        
#         EVT_CHOICE(self, XRCID("chExportTo"), self.OnExportTo)
        wx.EVT_CHOICE(self, GUI_ID.chSelectedSet, self.OnChSelectedSet)

        wx.EVT_BUTTON(self, GUI_ID.btnPreview, self.OnPreview)
        wx.EVT_BUTTON(self, GUI_ID.btnPageSetup, self.OnPageSetup)
        wx.EVT_BUTTON(self, GUI_ID.btnChoosePlainTextFont,
                self.OnChoosePlainTextFont)
#         EVT_BUTTON(self, GUI_ID.btnPrintSetup, self.OnPrintSetup)
        wx.EVT_BUTTON(self, wx.ID_OK, self.OnPrint)


#     def OnExportTo(self, evt):
#         for e in self.exporterList:
#             e[3].Show(False)
#             e[3].Enable(False)
#             
#         # Enable appropriate addit. options panel
#         self.exporterList[evt.GetSelection()][3].Enable(True)
#         self.exporterList[evt.GetSelection()][3].Show(True)
# 
#         evt.Skip()


    def _transferOptionsToPrinter(self):
        sel = self.ctrls.chSelectedSet.GetSelection()
        if sel == -1:
            sel = self.printer.selectionSet
            
        self.printer.setStdOptions(sel, self.plainTextFontDesc,
                self.ctrls.tfWikiPageSeparator.GetValue())
        

    def OnPreview(self, evt):
#         if self.plainTextFontDesc is not None:        
#             self.pWiki.printer.setFontDesc(self.plainTextFontDesc)
        self._transferOptionsToPrinter()
        self.printer.doPreview()
        

#     def OnPrintSetup(self, evt):
#         self.pWiki.printer.doPrintSetup(self.pWiki)


    def OnPrint(self, evt):
#         if self.plainTextFontDesc is not None:        
#             self.pWiki.printer.setFontDesc(self.plainTextFontDesc)
        self._transferOptionsToPrinter()
        if self.printer.doPrint():
            self.EndModal(wx.ID_OK)


    def OnChSelectedSet(self, evt):
        selset = self.ctrls.chSelectedSet.GetSelection()
        if selset == 3:  # Custom
            dlg = WikiPageListConstructionDialog(self, self.pWiki, -1, 
                    value=self.printer.listPagesOperation)
            if dlg.ShowModal() == wx.ID_OK:
                self.printer.listPagesOperation = dlg.getValue()
            dlg.Destroy()


    def OnChoosePlainTextFont(self, evt):
        fontdata = wx.FontData()
        if self.plainTextFontDesc:
            font = wx.FontFromNativeInfoString(self.plainTextFontDesc)
            fontdata.SetInitialFont(font)
            
        dlg = wx.FontDialog(self, fontdata)
        if dlg.ShowModal() == wx.ID_OK:
            # fontdata = dlg.GetFontData()
            font = dlg.GetFontData().GetChosenFont()
            self.plainTextFontDesc = font.GetNativeFontInfoDesc()
        
        dlg.Destroy()


    def OnPageSetup(self, evt):
        pageDialog = wx.PageSetupDialog(self.pWiki,
                self.printer.getPageSetupDialogData())
        pageDialog.ShowModal();
        
        self.printer.setOptionsByPageSetup(pageDialog.GetPageSetupData())

        pageDialog.Destroy()

        


class Printer:
    def __init__(self, pWiki):
        self.pWiki = pWiki
        self.printData = wx.PrintData()
        self.psddata = wx.PageSetupDialogData(self.printData)
        self.selectionSet = 0
        self.listPagesOperation = ListWikiPagesOperation()

        self.plainTextFontDesc = self.pWiki.configuration.get(
                "main", "print_plaintext_font")
        try:
            margintext = self.pWiki.configuration.get(
                    "main", "print_margins")
            margins = map(int, margintext.split(u","))
        except:
            margins = [0, 0, 0, 0]  # TODO Perhaps error message
            
        self.psddata.SetMarginTopLeft(wx.Point(margins[0], margins[1]))
        self.psddata.SetMarginBottomRight(wx.Point(margins[2], margins[3]))
        

    def setStdOptions(self, selectionSet, plainTextFontDesc, wpSeparator):
        self.selectionSet = selectionSet
        self.plainTextFontDesc = plainTextFontDesc
        self.pWiki.configuration.set("main", "print_plaintext_font",
                plainTextFontDesc)
        self.pWiki.configuration.set("main", "print_plaintext_wpseparator",
                wpSeparator)


    def buildWordList(self):
        import SearchAndReplace as Sar

        # Create wordList (what to export)
        selset = self.selectionSet
        root = self.pWiki.getCurrentWikiWord()
        
        if root is None and selset in (0, 1):
            self.pWiki.displayErrorMessage(u"No real wiki word selected as root")
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
#             wordList = self.pWiki.getWikiData().getAllSubWords([root])
        elif selset == 2:
            # whole wiki
            item = Sar.AllWikiPagesNode(lpOp)
            lpOp.setSearchOpTree(item)
            lpOp.ordering = "asroottree"  # Slow, but more intuitive
#             wordList = self.pWiki.getWikiData().getAllDefinedWikiPageNames()
        else:
            # custom list
            lpOp = self.listPagesOperation
        
        wordList = self.pWiki.getWikiDocument().searchWiki(lpOp, True)
 
#         if selset == 0:
#             # single page
#             wordList = [root]
#         elif selset == 1:
#             # subtree
#             wordList = self.pWiki.getWikiData().getAllSubWords([root])
#         elif selset == 2:
#             # whole wiki
#             wordList = self.pWiki.getWikiData().getAllDefinedWikiPageNames()
#         else:
#             # custom list
#             wordList = self.pWiki.getWikiDocument().searchWiki(
#                     self.listPagesOperation, True)
            
        return wordList


    def showPrintMainDialog(self):
        dlg = PrintMainDialog(self.pWiki, -1)
        dlg.CenterOnParent(wx.BOTH)

        result = dlg.ShowModal()
        dlg.Destroy()

    def getPageSetupDialogData(self):
        return self.psddata

    def setOptionsByPageSetup(self, pageSetupData):
        """
        Store options contained in a wx.PageSetupData object. It makes its
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
        margtext = u",".join(map(unicode, margins))
        self.pWiki.configuration.set("main", "print_margins", margtext)


    def doPreview(self):
        printObj = PlainTextPrint()
        printObj.setContext(self.pWiki, self, self.pWiki.getWikiDocument(),
                self.buildWordList(), "plain_text", None, None)

        return printObj.doPreview()
                    
                    
    def doPrint(self):
        printObj = PlainTextPrint()
        printObj.setContext(self.pWiki, self, self.pWiki.getWikiDocument(),
                self.buildWordList(), "plain_text", None, None)

        return printObj.doPrint()


class PlainTextPrint:
    def __init__(self):
        self.printOptions = None
        self.pWiki = None


    def getPrintTypes(self):
        return (
            ("plain_text", u'Plain text', None),
            )
            
#     def setFontDesc(self, fontDesc):
#         self.fontDesc = fontDesc     
#                
#     def getFontDesc(self):
#         return self.fontDesc
            
    def _buildText(self):
        def getTextFromWord(word):
            return self.wikiDocument.getWikiPage(word).getLiveText()

        contents = map(getTextFromWord, self.wordList)
        # Ensure that each wiki word content ends with newline
        for i, c in enumerate(contents):
            if len(c) > 0 and c[-1] != "\n":
                contents[i] += "\n"
                
        try:
            separator = unescapeWithRe(self.pWiki.getConfig().get(
                    "main", "print_plaintext_wpseparator"))
        except:
            separator = u"\n\n\n\n"   # TODO Error message
        
#         print "_buildText", repr(separator.join(contents))        
        return separator.join(contents)  # TODO Make configurable
            
            
    def setContext(self, pWiki, printer, wikiDocument, wordList, printType, options,
            addopt):
        self.pWiki = pWiki
        self.wikiDocument = wikiDocument
        self.wordList = wordList
        self.printer = printer

    def doPrint(self):
        text = self._buildText()

        printout = PlainTextPrintout(text, self.printer)
        printer = wx.Printer(wx.PrintDialogData(self.printer.printData))
        return printer.Print(self.pWiki, printout, True)


    def doPreview(self):
        text = self._buildText()
        
        pddata = wx.PrintDialogData(self.printer.printData)
        printout = PlainTextPrintout(text, self.printer)
        printout2 = PlainTextPrintout(text, self.printer)
        preview = wx.PrintPreview(printout, printout2, pddata)

        frame = wx.PreviewFrame(preview, self.pWiki, "Print Preview")

        frame.Initialize()
        frame.SetPosition(self.pWiki.GetPosition())
        frame.SetSize(self.pWiki.GetSize())
        frame.Show(True)


class PlainTextPrintout(wx.Printout):
    def __init__(self, text, printer, title="Printout"):
        wx.Printout.__init__(self, title)

        self.mm2logUnitsFactor = None
        self.printer = printer
        self.text = text.replace(u"\t", u"    ")  # TODO Better and configurable
        self.psddata = self.printer.getPageSetupDialogData()
        self.pageCharStartIndex = [0, 0] # For each page number, store the begin in text
        self.cuttedText = None
        
    def HasPage(self, pageNum):
        return len(self.pageCharStartIndex) > pageNum

    def GetPageInfo(self):
        ## _prof.start()
        self._printAndIndex(-1)
        ## _prof.stop()
        return (1, len(self.pageCharStartIndex) - 1, 1, 1)

    def _calcMmScaling(self, dc):
        """
        Calculate scaling for conversion from millimetres to device units
        (self.mm2logUnitsFactor).

        Must be called before using the conversion functions.
        
        Code taken from a wxWidgets sample
        """
        # You might use THIS code to set the printer DC to ROUGHLY reflect
        # the screen text size.
        # Get the logical pixels per inch of screen and printer
        ppiScreenX, ppiScreenY = self.GetPPIScreen()
        ppiPrinterX, ppiPrinterY = self.GetPPIPrinter()

        # This scales the DC so that the printout roughly represents the
        # the screen scaling. The text point size _should_ be the right size
        # but in fact is too small for some reason. This is a detail that will
        # need to be addressed at some point but can be fudged for the
        # moment.
        scale = float(ppiPrinterY)/ppiScreenY

        # Now we have to check in case our real page size is reduced
        # (e.g. because we're drawing to a print preview memory DC)
        w, h = dc.GetSize()
        pageWidth, pageHeight = self.GetPageSizePixels()

        # If printer pageWidth == current DC width, then this doesn't
        # change. But w might be the preview bitmap width, so scale down.
        overallScale = scale * float(w)/pageWidth;
        dc.SetUserScale(overallScale, overallScale)
        self.userScale = overallScale

        # Calculate conversion factor for converting millimetres into
        # logical units.
        # There are approx. 25.1 mm to the inch. There are ppi
        # device units to the inch. Therefore 1 mm corresponds to
        # ppi/25.1 device units. We also divide by the
        # screen-to-printer scaling factor, because we need to
        # unscale to pass logical units to DrawLine.

        self.mm2logUnitsFactor = float(ppiPrinterX)/(scale*25.1)


    def mmlenToLogUnits(self, mmpos):
        """
        """
        xr = mmpos[0] * self.mm2logUnitsFactor
        yr = mmpos[1] * self.mm2logUnitsFactor

        return (xr, yr)

#     def OnBeginDocument(self, start, end):
#         wx.Printout.base_OnBeginDocument(self, start, end)
#         print "OnBeginDocument"
#         return True

    def OnBeginPrinting(self):
#         print "OnBeginPrinting"
        self.base_OnBeginPrinting()
        self.mm2logUnitsFactor = None
        return True


    def OnPrintPage(self, pageNum):
#         self._fillPageStartIndex(pageNum)
        if len(self.pageCharStartIndex) <= pageNum:
            # Request for a non-existing page
            return True
            
        return self._printAndIndex(pageNum)


    def _printAndIndex(self, pageNum=-1):
        """
        Combined function to either fill the self.pageCharStartIndex
        if pageNum == -1 or print page pageNum if it is >= 1
        """

        dc = self.GetDC()

#         print "MapMode1", dc.GetMapMode(), wxMM_TWIPS, wxMM_TEXT, repr(dc.GetSizeMM())
#         dc.SetMapMode(wxMM_TWIPS)
#         print "MapMode2", repr(dc.GetSizeMM())
        
#         print "OnPrintPage size", repr(dc.GetSizeMM()), repr(self.GetPageSizeMM())
        
        if self.mm2logUnitsFactor is None:
            self._calcMmScaling(dc)

        if pageNum == -1:
            self.pageCharStartIndex = [0, 0]

        # Calculate print rectangle
        tlMarg = self.psddata.GetMarginTopLeft()
        brMarg = self.psddata.GetMarginBottomRight()
        
        leftLu, topLu = self.mmlenToLogUnits((tlMarg.x, tlMarg.y))
        rMargLu, bMargLu = self.mmlenToLogUnits((brMarg.x, brMarg.y))
        
        sizeLu = dc.GetSize()
        sizeLu.x = dc.DeviceToLogicalXRel(sizeLu.x)
        sizeLu.y = dc.DeviceToLogicalYRel(sizeLu.y)

        printRectLu = (leftLu, topLu, sizeLu.x - rMargLu, sizeLu.y - bMargLu)
        
        fontDesc = self.printer.plainTextFontDesc
        
        if not fontDesc:
            font = wx.Font(12, wx.DEFAULT, wx.NORMAL, wx.NORMAL, FALSE, "Courier New")
        else:
            font = wx.FontFromNativeInfoString(fontDesc)
#             font = wxFont()
#             font.SetNativeFontInfo(fontDesc)

        dc.SetFont(font)

        if pageNum != -1:
            pagepos = pageNum
        else:
            pagepos = 1

        textpos = self.pageCharStartIndex[pagepos]
        text = self.text
        
        if pageNum == -1:
            cuttedText = _CUT_RE.findall(text[textpos:])
        else:
            if pageNum + 1 >= len(self.pageCharStartIndex):
                lastCharPos = len(text)
            else:
                lastCharPos = self.pageCharStartIndex[pageNum + 1]
                
            cuttedText = _CUT_RE.findall(
                    text[self.pageCharStartIndex[pageNum]:lastCharPos])

        currLine = u""
        currLineWidth = 0
        w, stepY, d, e = dc.GetFullTextExtent("aaaaaaaa")
        
        posxLu, posyLu = printRectLu[0:2]
        prAreaWidth = printRectLu[2] - printRectLu[0]


#         def flushPage():
#             if currLine != u"":
#                 # Flush line first
#                 if pageNum != -1:
#                     dc.DrawText(currLine, posxLu, posyLu)
#                 currLine = u""
#                 
#             pagepos += 1
#             posyLu = printRectLu[1]
#             self.pageCharStartIndex.append(textpos)
# 
# 
#         def flushLine():
#             # Draw current row, start new one
#             if pageNum != -1:
#                 dc.DrawText(currLine, posxLu, posyLu)
#             currLine = u""
#             posyLu += stepY
#             if posyLu + stepY > printRectLu[3]: # Next line wouldn't fit on this page
#                 # End of page reached
#                 flushPage()

        i = 0
        while i < len(cuttedText):    # _CUT_RE.finditer(text[textpos:]):
            part = cuttedText[i]
            
            flushLine = False
            flushPage = False
#             print "Part", repr(part)
#             mat = _CUT_RE.search(text, textpos)
#             part = mat.group(0)
            
#             print "Match", repr(mat.groupdict()), textpos
            
            if part[0] == u" ":
                # One or more spaces
                partWidth = dc.GetTextExtent(part)[0]
                linewidth = currLineWidth + partWidth
#                 linewidth = dc.GetTextExtent(currLine + part)[0]
                if linewidth > prAreaWidth:
                    flushLine = True
                else:
                    currLine += part
                    currLineWidth = linewidth

                textpos += len(part)
            elif part[0] == u"\n":
                flushLine = True
                textpos += 1
            elif part[0] == u"\f":
                flushPage = True
                textpos += 1
            else:
                partWidth = dc.GetTextExtent(part)[0]
                linewidth = currLineWidth + partWidth
#                 linewidth = dc.GetTextExtent(currLine + part)[0]
                if linewidth > prAreaWidth:
                    if currLine != u"":
                        flushLine = True
                        i -= 1
                    else:
                        # A single "word" which doesn't fit into a line
                        # TODO Use bisect algorithm?
                        for partPos in xrange(1, len(part)):
                            partWidth = dc.GetTextExtent(part[:partPos])[0]
                            if partWidth > prAreaWidth:
                                break
                        partPos -= 1
                        currLine = part[:partPos]
                        textpos += partPos
                        cuttedText[i] = part[partPos:]
                        flushLine = True
                        i -= 1
                else:
                    currLine += part
                    textpos += len(part)
                    currLineWidth = linewidth

            if textpos == len(text) or flushPage:
                flushLine = True

            if flushLine:
                # Draw current row, start new one
                if pageNum != -1:
                    dc.DrawText(currLine, posxLu, posyLu)
                currLine = u""
                currLineWidth = 0
                posyLu += stepY
                if posyLu + stepY > printRectLu[3]:
                    # End of page reached
                    flushPage = True
                    
            if flushPage:
                if pageNum != -1 or textpos == len(text):
                    break
                pagepos += 1
#                 print "PagePos", pagepos
#                 if pagepos > 100: break
                posyLu = printRectLu[1]
                self.pageCharStartIndex.append(textpos)
                
            i += 1
            


        dc.SetFont(wx.NullFont) ## ?
        
        return True

