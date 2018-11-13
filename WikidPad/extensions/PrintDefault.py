"""
Plugin to implement default printing methods plain text and HTML
(and demonstrating how to write print plugins).
"""


import re, traceback

from io import BytesIO

import wx

from pwiki.wxHelper import XrcControls, GUI_ID

from pwiki.TempFileSet import TempFileSet
from pwiki import PluginManager

from pwiki.StringOps import unescapeWithRe, urlFromPathname

from pwiki import WikiHtmlView

if WikiHtmlView.WikiHtmlViewWK is not None:
    try:
        from pwiki.WikiHtmlViewWK import WKHtmlWindow
    except:
        WKHtmlWindow = None
else:
    WKHtmlWindow = None


WIKIDPAD_PLUGIN = (("Prints", 1),)


def describePrintsV01(mainControl):
    """
    Return sequence of print classes.
    """
    return (PlainTextPrint, HtmlPrint, HtmlWKPrint)



_CUT_RE = re.compile(r"\n|\f| +|[^ \n\f]+",
        re.DOTALL | re.UNICODE | re.MULTILINE)


class PlainTextPrint:
    def __init__(self, mainControl):
        self.mainControl = mainControl

    @staticmethod
    def getPrintTypes(mainControl):
        """
        Part of "Prints" plugin API.
        Return sequence of tuples with the description of print types provided
        by this object. A tuple has the form (<print type>,
            <human readable description>)
        All exporters must provide this as a static method (which can be called
        without constructing an object first.

        mainControl -- PersonalWikiFrame object
        """
        return (
            ("plain_text", 'Plain text'),
            )

    def getAddOptPanelsForTypes(self, guiparent, printTypes):
        """
        Part of "Prints" plugin API.
        Construct all necessary GUI panels for additional options
        for the types contained in exportTypes.
        Returns sequence of tuples (<print type>, <panel for add. options or None>)

        The panels should use  guiparent  as parent.
        If the same panel is used for multiple export types the function can
        and should include all export types for this panel even if some of
        them weren't requested. Panel objects must not be shared by different
        print classes.
        """
        if not "plain_text" in printTypes:
            return ()

        res = wx.xrc.XmlResource.Get()
        panel = res.LoadPanel(guiparent, "PrintSubPlainText")
        ctrls = XrcControls(panel)
        config = self.mainControl.getConfig()

        def OnChoosePlainTextFont(evt):
            fontdata = wx.FontData()
            if panel.fontDesc:
                font = wx.FontFromNativeInfoString(panel.fontDesc)
                fontdata.SetInitialFont(font)

            dlg = wx.FontDialog(panel, fontdata)
            try:
                if dlg.ShowModal() == wx.ID_OK:
                    # fontdata = dlg.GetFontData()
                    font = dlg.GetFontData().GetChosenFont()
                    panel.fontDesc = font.GetNativeFontInfoDesc()
            finally:
                dlg.Destroy()

        ctrls.tfWikiPageSeparator.SetValue(config.get("main",
                "print_plaintext_wpseparator"))

        panel.fontDesc = config.get("main", "print_plaintext_font")

        panel.Bind(wx.EVT_BUTTON, OnChoosePlainTextFont,
                id=GUI_ID.btnChoosePlainTextFont)

        return (
            ("plain_text", panel),
            )


    def getAddOptVersion(self):
        """
        Part of "Prints" plugin API.
        Returns the version of the additional options information returned
        by getAddOpt(). If the return value is -1, the version info can't
        be stored between application sessions.

        Otherwise, the addopt information can be stored between sessions
        and can later handled back to the doPreview() or doPrint() method of
        the object without previously showing the print dialog (currently
        not implemented)
        """
        return 0


    def getAddOpt(self, addoptpanel):
        """
        Part of "Prints" plugin API.
        Reads additional options from panel addoptpanel.
        If getAddOptVersion() > -1, the return value must be a sequence
        of simple string, unicode and/or numeric objects. Otherwise, any object
        can be returned (normally the addoptpanel itself).
        Here, it returns a tuple with following items:
            fontDesc -- string describing font to use plain text
            wpseparator -- unistring with (escaped) separator between wiki words
        """
        if addoptpanel is None:
            # Return default set in options
            config = self.mainControl.getConfig()

            return ( config.get("main", "print_plaintext_font"),
                     config.get("main", "print_plaintext_wpseparator")
                    )
        else:
            fontDesc = addoptpanel.fontDesc
            ctrls = XrcControls(addoptpanel)
            wpseparator = ctrls.tfWikiPageSeparator.GetValue()

            return (fontDesc, wpseparator)


    def setAddOpt(self, addOpt, addoptpanel):
        """
        Part of "Prints" plugin API.
        Shows content of addOpt in the addoptpanel (must not be None).
        This function is only called if getAddOptVersion() != -1.
        """
        fontDesc, wpseparator = \
                addOpt[:2]

        ctrls = XrcControls(addoptpanel)

        addoptpanel.fontDesc = fontDesc
        ctrls.tfWikiPageSeparator.SetValue(wpseparator)


    def _buildText(self):
        def getTextFromWord(word):
            return self.wikiDocument.getWikiPage(word).getLiveText()

        contents = list(map(getTextFromWord, self.wordList))
        # Ensure that each wiki word content ends with newline
        for i, c in enumerate(contents):
            if len(c) > 0 and c[-1] != "\n":
                contents[i] += "\n"

        return self.separator.join(contents)

#         try:
#             separator = unescapeWithRe(self.mainControl.getConfig().get(
#                     "main", "print_plaintext_wpseparator"))
#         except:
#             separator = u"\n\n\n\n"   # TODO Error message
#
#         return separator.join(contents)


    def setContext(self, printer, wikiDocument, wordList, printType, addopt):
        self.wikiDocument = wikiDocument
        self.wordList = wordList
        self.printer = printer
        try:
            self.separator = unescapeWithRe(addopt[1])
        except:
            self.separator = "\n\n\n\n"   # TODO Error message?


    def doPrint(self, printer, wikiDocument, wordList, printType, addopt):
        """
        Part of "Prints" plugin API. A Printing.Printer object calls this
        to print a list of wiki words.

        printer -- Printer object
        wikiDocument -- WikiDocument object
        wordList -- list of wiki words to print
        printType -- bytestring as returned as <print type> by getPrintTypes()
            (only interesting if class provides more than one print type)
        addOpt -- additional options as returned by getAddOpt()
        """
        self.setContext(printer, wikiDocument, wordList, printType, addopt)
        text = self._buildText()

        printout = PlainTextPrintout(text, self.printer, addopt)
        printer = wx.Printer(wx.PrintDialogData(self.printer.getPrintData()))

        config = self.mainControl.getConfig()

        config.set("main", "print_plaintext_font", addopt[0])
        config.set("main", "print_plaintext_wpseparator", addopt[1])

        return printer.Print(self.mainControl, printout, True)


    def doPreview(self, printer, wikiDocument, wordList, printType, addopt):
        """
        Part of "Prints" plugin API. A Printing.Printer object calls this
        to show a print preview for a list of wiki words.

        printer -- Printer object
        wikiDocument -- WikiDocument object
        wordList -- list of wiki words to print
        printType -- bytestring as returned as <print type> by getPrintTypes()
            (only interesting if class provides more than one print type)
        addOpt -- additional options as returned by getAddOpt()
        """
        self.setContext(printer, wikiDocument, wordList, printType, addopt)
        text = self._buildText()

        pddata = wx.PrintDialogData(self.printer.getPrintData())
        printout = PlainTextPrintout(text, self.printer, addopt)
        printout2 = PlainTextPrintout(text, self.printer, addopt)

        preview = wx.PrintPreview(printout, printout2, pddata)

        frame = wx.PreviewFrame(preview, self.mainControl, _("Print Preview"),
                style=wx.DEFAULT_FRAME_STYLE | wx.FRAME_FLOAT_ON_PARENT)

        frame.Initialize()
        frame.SetPosition(self.mainControl.GetPosition())
        frame.SetSize(self.mainControl.GetSize())
        frame.Show(True)





class PlainTextPrintout(wx.Printout):
    def __init__(self, text, printer, addOpt, title=_("Printout")):
        wx.Printout.__init__(self, title)

        self.mm2logUnitsFactor = None
        self.printer = printer
        self.text = text.replace("\t", "    ")  # TODO Better and configurable
        self.psddata = self.printer.getPageSetupDialogData()
        self.pageCharStartIndex = [0, 0] # For each page number, store the begin in text
        self.cuttedText = None

        self.fontDesc = addOpt[0]
        self.wpseparator = addOpt[1]


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

    def OnBeginPrinting(self):
        wx.Printout.OnBeginPrinting(self)
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

        fontDesc = self.fontDesc

        if not fontDesc:
            font = wx.Font(12, wx.DEFAULT, wx.NORMAL, wx.NORMAL, False,
                    "Courier New")
        else:
            font = wx.FontFromNativeInfoString(fontDesc)

        dc.SetFont(font)

        if pageNum != -1:
            pagepos = pageNum
        else:
            pagepos = 1

        textpos = self.pageCharStartIndex[pagepos]
        text = self.text

        if pageNum == -1:
            # Build a list of cuttedText. Each item is either a newline,
            # a new page command '\f', one or more spaces or one or more
            # other characters
            cuttedText = _CUT_RE.findall(text[textpos:])
        else:
            if pageNum + 1 >= len(self.pageCharStartIndex):
                lastCharPos = len(text)
            else:
                lastCharPos = self.pageCharStartIndex[pageNum + 1]

            cuttedText = _CUT_RE.findall(
                    text[self.pageCharStartIndex[pageNum]:lastCharPos])

        currLine = ""
        currLineWidth = 0
        w, stepY, d, e = dc.GetFullTextExtent("aaaaaaaa")

        posxLu, posyLu = printRectLu[0:2]
        prAreaWidth = printRectLu[2] - printRectLu[0]

        i = 0
        while i < len(cuttedText):    # _CUT_RE.finditer(text[textpos:]):
            part = cuttedText[i]

            flushLine = False
            flushPage = False

            if part[0] == " ":
                # One or more spaces -> Append to current line if possible,
                # throw away and start new print line if not
                partWidth = dc.GetTextExtent(part)[0]
                linewidth = currLineWidth + partWidth
#                 linewidth = dc.GetTextExtent(currLine + part)[0]
                if linewidth > prAreaWidth:
                    flushLine = True
                else:
                    currLine += part
                    currLineWidth = linewidth

                textpos += len(part)
            elif part[0] == "\n":
                flushLine = True
                textpos += 1
            elif part[0] == "\f":
                # New page
                flushPage = True
                textpos += 1
            else:
                partWidth = dc.GetTextExtent(part)[0]
                linewidth = currLineWidth + partWidth
#                 linewidth = dc.GetTextExtent(currLine + part)[0]
                if linewidth > prAreaWidth:
                    # Part doesn't fit into current print line
                    if currLine != "":
                        # Current print line already contains text ->
                        # Make new print line and reread part
                        flushLine = True
                        i -= 1
                    else:
                        # A single "word" which doesn't fit into a line
                        # TODO Use bisect algorithm?
                        for partPos in range(1, len(part)):
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

            i += 1

            if i == len(cuttedText) or flushPage:
                flushLine = True

            if flushLine:
                # Draw current row, start new one
                if pageNum != -1:
                    dc.DrawText(currLine, posxLu, posyLu)

                currLine = ""
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


        dc.SetFont(wx.NullFont)

        return True





class HtmlPrint:
    def __init__(self, mainControl):
        self.mainControl = mainControl
        self.tempFileSet = None

    @staticmethod
    def getPrintTypes(mainControl):
        return (
            ("html_simple", 'HTML'),
            )

    def getAddOptPanelsForTypes(self, guiparent, printTypes):
        return ()
#         if not u"html_multi" in exportTypes and \
#                 not u"html_single" in exportTypes:
#             return ()
#
#         res = wx.xrc.XmlResource.Get()
#         htmlPanel = res.LoadPanel(guiparent, "ExportSubHtml")
#         ctrls = XrcControls(htmlPanel)
#         config = self.mainControl.getConfig()
#
#         ctrls.cbPicsAsLinks.SetValue(config.getboolean("main",
#                 "html_export_pics_as_links"))
#         ctrls.chTableOfContents.SetSelection(config.getint("main",
#                 "export_table_of_contents"))
#         ctrls.tfHtmlTocTitle.SetValue(config.get("main",
#                 "html_toc_title"))
#
#         return (
#             (u"html_multi", htmlPanel),
#             (u"html_single", htmlPanel)
#             )

    def getAddOptVersion(self):
        return 0


    def getAddOpt(self, addoptpanel):
        return ()
#         if addoptpanel is None:
#             # Return default set in options
#             config = self.mainControl.getConfig()
#
#             return ( boolToInt(config.getboolean("main",
#                     "html_export_pics_as_links")),
#                     config.getint("main", "export_table_of_contents"),
#                     config.get("main", "html_toc_title"),
#                     u"volatile"
#                      )
#         else:
#             ctrls = XrcControls(addoptpanel)
#
#             picsAsLinks = boolToInt(ctrls.cbPicsAsLinks.GetValue())
#             tableOfContents = ctrls.chTableOfContents.GetSelection()
#             tocTitle = ctrls.tfHtmlTocTitle.GetValue()
#
#             return (picsAsLinks, tableOfContents, tocTitle, u"volatile")


    def setAddOpt(self, addOpt, addoptpanel):
        pass
#         picsAsLinks, tableOfContents, tocTitle, volatileDir = \
#                 addOpt[:4]
#
#         # volatileDir is currently ignored
#
#         ctrls = XrcControls(addoptpanel)
#
#         ctrls.cbPicsAsLinks.SetValue(picsAsLinks != 0)
#         ctrls.chTableOfContents.SetSelection(tableOfContents)
#         ctrls.tfHtmlTocTitle.SetValue(tocTitle)


    def _buildHtml(self):
        def getTextFromWord(word):
            return self.wikiDocument.getWikiPage(word).getLiveText()

        exporterInstance = PluginManager.getExporterTypeDict(
                self.mainControl, False)["html_single"][0](self.mainControl)

        # TODO Progress handler
        # TODO Set additional options
        exporterInstance.setJobData(self.wikiDocument, self.wordList,
                "html_previewWX", None, False,
                exporterInstance.getAddOpt(None), progressHandler=None)

        self.tempFileSet = TempFileSet()
        exporterInstance.tempFileSet = self.tempFileSet
        exporterInstance.styleSheet = ""

        realfp = BytesIO()
        exporterInstance.exportHtmlMultiFile(realfp=realfp, tocMode=0)

        return realfp.getvalue().decode("utf-8")

    def _freeHtml(self):
        self.tempFileSet.clear()
        self.tempFileSet = None


    def setContext(self, printer, wikiDocument, wordList, printType, addopt):
        self.wikiDocument = wikiDocument
        self.wordList = wordList
        self.printer = printer


    def doPrint(self, printer, wikiDocument, wordList, printType, addopt):
        self.setContext(printer, wikiDocument, wordList, printType, addopt)
        text = self._buildHtml()

        try:
            printout = HtmlPrintout(text, self.printer)

            pData = wx.PrintDialogData(self.printer.getPrintData())
            printer = wx.Printer(pData)

            return printer.Print(self.mainControl, printout, True)
        finally:
            self._freeHtml()


    def doPreview(self, printer, wikiDocument, wordList, printType, addopt):
        self.setContext(printer, wikiDocument, wordList, printType, addopt)
        text = self._buildHtml()

        try:
            pddata = wx.PrintDialogData(self.printer.getPrintData())
            printout = HtmlPrintout(text, self.printer)
            printout2 = HtmlPrintout(text, self.printer)

            preview = wx.PrintPreview(printout, printout2, pddata)

            frame = wx.PreviewFrame(preview, self.mainControl, _("Print Preview"),
                    style=wx.DEFAULT_FRAME_STYLE | wx.FRAME_FLOAT_ON_PARENT)

            frame.Initialize()
            frame.SetPosition(self.mainControl.GetPosition())
            frame.SetSize(self.mainControl.GetSize())
            frame.Show(True)
        finally:
            self._freeHtml()



class HtmlPrintout(wx.html.HtmlPrintout):
    def __init__(self, text, printer):
        wx.html.HtmlPrintout.__init__(self)

        self.printer = printer
        self.SetHtmlText(text)
        psddata = self.printer.getPageSetupDialogData()
        tl = psddata.GetMarginTopLeft()
        br = psddata.GetMarginBottomRight()

        self.SetMargins(tl.y, br.y, tl.x, br.x, spaces=0)



#     def _updateTempFilePrefPath(self):
#         wikiDocument = self.presenter.getWikiDocument()
#
#         if wikiDocument is not None:
#             self.exporterInstance.tempFileSet.setPreferredPath(
#                     wikiDocument.getWikiTempDir())
#         else:
#             self.exporterInstance.tempFileSet.setPreferredPath(None)


#         self.SetHtmlText(u"ab<br />\n" * 5000)


class HtmlWKPrint(HtmlPrint):
    @staticmethod
    def getPrintTypes(mainControl):
        if WKHtmlWindow:
            return (
                ("html_webkit", 'HTML (Webkit)'),
                )
        else:
            return ()


    def _buildHtml(self):
        def getTextFromWord(word):
            return self.wikiDocument.getWikiPage(word).getLiveText()

        exporterInstance = PluginManager.getExporterTypeDict(
                self.mainControl, False)["html_single"][0](self.mainControl)

        # TODO Progress handler
        # TODO Set additional options
        exporterInstance.setJobData(self.wikiDocument, self.wordList,
                "html_previewWK", None, False,
                exporterInstance.getAddOpt(None), progressHandler=None)

        self.tempFileSet = TempFileSet()
        exporterInstance.tempFileSet = self.tempFileSet
        exporterInstance.styleSheet = ""

        htpath = self.tempFileSet.createTempFile(
                    "", ".html", relativeTo="")

#         realfp = StringIO.StringIO()
        with open(htpath, "wb") as realfp:
            exporterInstance.exportHtmlMultiFile(realfp=realfp, tocMode=0)

        return htpath  # realfp.getvalue().decode("utf-8")

    def doPrint(self, printer, wikiDocument, wordList, printType, addopt,
            doPreview=False):
        """
        To print with webkit we load the pages into a temporary frame
        that contains a WKHtmlWindow and use webkits print function.

        The frame does not need to be shown as a preview is builtin
        """
        self.setContext(printer, wikiDocument, wordList, printType, addopt)
        if self.checkWebkit():
            import gtk
            htpath = self._buildHtml()
            frame = None

            try:
                # Get page setup dialog data (wxPython) and translate to pyGTK
                psddata = self.printer.getPageSetupDialogData()

                tl = psddata.GetMarginTopLeft()
                br = psddata.GetMarginBottomRight()

                print_op = gtk.PrintOperation()
                page_setup = gtk.PageSetup()
                page_setup.set_top_margin(tl.y, gtk.UNIT_MM)
                page_setup.set_left_margin(tl.x, gtk.UNIT_MM)
                page_setup.set_right_margin(br.x, gtk.UNIT_MM)
                page_setup.set_bottom_margin(br.y, gtk.UNIT_MM)
                print_op.set_default_page_setup(page_setup)

                frame = WKPrintFrame(htpath)
                if doPreview:
                    opCode = gtk.PRINT_OPERATION_ACTION_PREVIEW
                    frame.print_full(print_op, opCode)
                    return False
                else:
                    opCode = gtk.PRINT_OPERATION_ACTION_PRINT_DIALOG
                    result = frame.print_full(print_op, opCode)
                    return result in (gtk.PRINT_OPERATION_RESULT_APPLY,
                            gtk.PRINT_OPERATION_RESULT_IN_PROGRESS)
            finally:
                if frame:
                    frame.Destroy()
                self._freeHtml()

    def doPreview(self, printer, wikiDocument, wordList, printType, addopt):
        """Preview is built into the print function"""
        self.doPrint(printer, wikiDocument, wordList, printType, addopt,
                doPreview=True)

    def checkWebkit(self):
        # NOTE: It would be better to check this earlier but I don't
        #       know how to have conditions in XrcControls  -- Ross
        if WKHtmlWindow:
            return True
        else:
            dlg = wx.MessageDialog(None, \
                _('Error loading Webkit: try a different export format)'), \
                _('Error'), wx.OK | wx.ICON_ERROR)
            dlg.ShowModal()
            return False


if WKHtmlWindow:

    class WKPrintPanel(wx.Panel):
        def __init__(self, parent, htpath):
            """Panel to contain webkit ctrl"""
            wx.Panel.__init__(self, parent)

            self.html_preview = WKHtmlWindow(self)
            self.html_preview.PizzaMagic()
            url = "file:" + urlFromPathname(htpath)
            self.html_preview.LoadUrl(url)


#         def Print(self):
#             self.html_preview.Print()


    class WKPrintFrame(wx.Frame):
        """Frame to contain webkit ctrl panel"""
        def __init__(self, htpath):
            wx.Frame.__init__(self, None)
            self.html_panel = WKPrintPanel(self, htpath)

        def print_full(self, print_op, opCode):
            return self.html_panel.html_preview.getWebkitWebView()\
                    .get_main_frame().print_full(print_op, opCode)

