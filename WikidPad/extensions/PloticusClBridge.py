import os, os.path
import subprocess

import wx

from pwiki.TempFileSet import createTempFile
from pwiki.StringOps import mbcsEnc, mbcsDec, lineendToOs

WIKIDPAD_PLUGIN = (("InsertionByKey", 1), ("Options", 1))


OUTPUT_FORMAT_GIF = 0
OUTPUT_FORMAT_PNG = 1


def describeInsertionKeys(ver, app):
    """
    API function for "InsertionByKey" plugins
    Returns a sequence of tuples describing the supported
    insertion keys. Each tuple has the form (insKey, exportTypes, handlerFactory)
    where insKey is the insertion key handled, exportTypes is a sequence of
    strings describing the supported export types and handlerFactory is
    a factory function (normally a class) taking the wxApp object as
    parameter and returning a handler object fulfilling the protocol
    for "insertion by key" (see EqnHandler as example).

    ver -- API version (can only be 1 currently)
    app -- wxApp object
    """
    return (
            ("ploticus", ("html_single", "html_previewWX", "html_preview", "html_multi"), PltHandler),
            )


class PltHandler:
    """
    Base class fulfilling the "insertion by key" protocol.
    """
    def __init__(self, app):
        self.app = app
        self.extAppExe = None
        
    def taskStart(self, exporter, exportType):
        """
        This is called before any call to createContent() during an
        export task.
        An export task can be a single HTML page for
        preview or a single page or a set of pages for export.
        exporter -- Exporter object calling the handler
        exportType -- string describing the export type
        
        Calls to createContent() will only happen after a 
        call to taskStart() and before the call to taskEnd()
        """
        # Find Ploticus executable by configuration setting
        self.extAppExe = self.app.getGlobalConfig().get("main",
                "plugin_ploticus_exePath", "")
        
        if self.extAppExe:
            self.extAppExe = os.path.join(self.app.getWikiAppDir(),
                    self.extAppExe)
        
        if self.app.getGlobalConfig().getint("main",
                "plugin_ploticus_outputFormat", OUTPUT_FORMAT_GIF) == OUTPUT_FORMAT_GIF:
            self.outputSuffix = ".gif"
            self.outputParameter = "-gif"
        else:
            self.outputSuffix = ".png"
            self.outputParameter = "-png"


    def taskEnd(self):
        """
        Called after export task ended and after the last call to
        createContent().
        """
        pass


    def createContent(self, exporter, exportType, insToken):
        """
        Handle an insertion and create the appropriate content.

        exporter -- Exporter object calling the handler
        exportType -- string describing the export type
        insToken -- insertion token to create content for

        An insertion token has the following member variables:
            key: insertion key (unistring)
            value: value of an insertion (unistring)
            appendices: sequence of strings with the appendices

        Meaning and type of return value is solely defined by the type
        of the calling exporter.
        
        For HtmlExporter a unistring is returned with the HTML code
        to insert instead of the insertion.        
        """
        # Retrieve quoted content of the insertion
        bstr = lineendToOs(mbcsEnc(insToken.value, "replace")[0])

        if not bstr:
            # Nothing in, nothing out
            return ""
        
        if self.extAppExe == "":
            # No path to MimeTeX executable -> show message
            return '<pre>' + _('[Please set path to Ploticus executable]') +\
                    '</pre>'
        # Get exporters temporary file set (manages creation and deletion of
        # temporary files)
        tfs = exporter.getTempFileSet()

        pythonUrl = (exportType != "html_previewWX")
        
        dstFullPath = tfs.createTempFile("", self.outputSuffix, relativeTo="")
        url = tfs.getRelativeUrl(None, dstFullPath, pythonUrl=pythonUrl)
        
        baseDir = os.path.dirname(exporter.getMainControl().getWikiConfigPath())

        # Store token content in a temporary file
        srcfilepath = createTempFile(bstr, ".plt")
        try:
            cmdline = subprocess.list2cmdline((self.extAppExe, "-dir", baseDir,
                    srcfilepath, self.outputParameter, "-o", dstFullPath))

            # Run external application
#             childIn, childOut, childErr = os.popen3(cmdline, "b")
            popenObject = subprocess.Popen(cmdline, shell=True,
                    stderr=subprocess.PIPE, stdout=subprocess.PIPE,
                    stdin=subprocess.PIPE)
            childErr = popenObject.stderr

            # See http://bytes.com/topic/python/answers/634409-subprocess-handle-invalid-error
            # why this is necessary
            popenObject.stdin.close()
            popenObject.stdout.close()

            if "noerror" in [a.strip() for a in insToken.appendices]:
                childErr.read()
                errResponse = b""
            else:
                errResponse = childErr.read()
            
            childErr.close()
        finally:
            os.unlink(srcfilepath)
            
        if errResponse != b"":
#             errResponse = mbcsDec(errResponse, "replace")[0]
            return '<pre>' + _('[Ploticus error: %s]') % repr(errResponse) + \
                    '</pre>'

        # Return appropriate HTML code for the image
        if exportType == "html_previewWX":
            # Workaround for internal HTML renderer
            return ('<img src="%s" border="0" align="bottom" alt="formula" />'
                    '&nbsp;') % url
        else:
            return '<img src="%s" border="0" align="bottom" alt="formula" />' \
                    % url


    def getExtraFeatures(self):
        """
        Returns a list of bytestrings describing additional features supported
        by the plugin. Currently not specified further.
        """
        return ()



def registerOptions(ver, app):
    """
    API function for "Options" plugins
    Register configuration options and their GUI presentation
    ver -- API version (can only be 1 currently)
    app -- wxApp object
    """
    # Register option
    app.getDefaultGlobalConfigDict()[("main", "plugin_ploticus_exePath")] = ""
    app.getDefaultGlobalConfigDict()[("main", "plugin_ploticus_outputFormat")] = "0"
    # Register panel in options dialog
    app.addOptionsDlgPanel(PloticusOptionsPanel, "  Ploticus")


class PloticusOptionsPanel(wx.Panel):
    def __init__(self, parent, optionsDlg, app):
        """
        Called when "Options" dialog is opened to show the panel.
        Transfer here all options from the configuration file into the
        text fields, check boxes, ...
        """
        wx.Panel.__init__(self, parent)
        self.app = app

        pt = self.app.getGlobalConfig().get("main", "plugin_ploticus_exePath", "")
        outputFormat = self.app.getGlobalConfig().getint("main", "plugin_ploticus_outputFormat", 0)
        outputFormat = min(1, max(0, outputFormat))

        self.tfPath = wx.TextCtrl(self, -1, pt)

        self.chOutputFormat = wx.Choice(self, -1)
        self.chOutputFormat.Append("GIF")
        self.chOutputFormat.Append("PNG")
        self.chOutputFormat.SetSelection(outputFormat)

        mainsizer = wx.BoxSizer(wx.VERTICAL)

        inputsizer = wx.BoxSizer(wx.HORIZONTAL)
        inputsizer.Add(wx.StaticText(self, -1, _("Path to Ploticus:")), 0,
                wx.ALL | wx.EXPAND, 5)
        inputsizer.Add(self.tfPath, 1, wx.ALL | wx.EXPAND, 5)
        mainsizer.Add(inputsizer, 0, wx.EXPAND)

        inputsizer = wx.BoxSizer(wx.HORIZONTAL)
        inputsizer.Add(wx.StaticText(self, -1, _("Output format:")), 0,
                wx.ALL | wx.EXPAND, 5)
        inputsizer.Add(self.chOutputFormat, 1, wx.ALL | wx.EXPAND, 5)
        mainsizer.Add(inputsizer, 0, wx.EXPAND)

        self.SetSizer(mainsizer)
        self.Fit()

    def setVisible(self, vis):
        """
        Called when panel is shown or hidden. The actual wxWindow.Show()
        function is called automatically.
        
        If a panel is visible and becomes invisible because another panel is
        selected, the plugin can veto by returning False.
        When becoming visible, the return value is ignored.
        """
        return True

    def checkOk(self):
        """
        Called when "OK" is pressed in dialog. The plugin should check here if
        all input values are valid. If not, it should return False, then the
        Options dialog automatically shows this panel.
        
        There should be a visual indication about what is wrong (e.g. red
        background in text field). Be sure to reset the visual indication
        if field is valid again.
        """
        return True

    def handleOk(self):
        """
        This is called if checkOk() returned True for all panels. Transfer here
        all values from text fields, checkboxes, ... into the configuration
        file.
        """
        pt = self.tfPath.GetValue()
        
        self.app.getGlobalConfig().set("main", "plugin_ploticus_exePath", pt)
        
        outputFormat = self.chOutputFormat.GetSelection()
        outputFormat = min(1, max(0, outputFormat))
        
        self.app.getGlobalConfig().set("main", "plugin_ploticus_outputFormat",
                str(outputFormat))



