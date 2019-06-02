import os
import subprocess

import wx

from pwiki.TempFileSet import createTempFile
from pwiki.StringOps import mbcsDec, utf8Enc, lineendToOs

WIKIDPAD_PLUGIN = (("InsertionByKey", 1), ("Options", 1))


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
            ("dot", ("html_single", "html_previewWX", "html_preview", "html_multi"), DotHandler),
            ("neato", ("html_single", "html_previewWX", "html_preview", "html_multi"), NeatoHandler),
            ("twopi", ("html_single", "html_previewWX", "html_preview", "html_multi"), TwopiHandler),
            ("circo", ("html_single", "html_previewWX", "html_preview", "html_multi"), CircoHandler),
            ("fdp", ("html_single", "html_previewWX", "html_preview", "html_multi"), FdpHandler)
            )


class GraphVizBaseHandler:
    """
    Base class fulfilling the "insertion by key" protocol.
    """
    DIR_CONFIG_KEY = "plugin_graphViz_dirExe"

    # Filled in by derived classes
    EXT_APP_NAME = ""
    EXE_CONFIG_KEY = ""

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
        globalConfig = self.app.getGlobalConfig()

        # Find executable by configuration setting
        self.extAppExe = globalConfig.get("main", self.EXE_CONFIG_KEY, "")

        if not self.extAppExe:
            return

        dirPath = globalConfig.get("main", self.DIR_CONFIG_KEY, "")

        if dirPath:
            self.extAppExe = os.path.join(self.app.getWikiAppDir(), dirPath, self.extAppExe)

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
        if not insToken.value:
            # Nothing in, nothing out
            return ""

        if not self.extAppExe:
            # No path to executable -> show message
            return '<pre>' + _('[Please set path to GraphViz executables]') + \
                    '</pre>'

        # Get exporters temporary file set (manages creation and deletion of
        # temporary files)
        tfs = exporter.getTempFileSet()

        # Create destination file in the set
        dstFilePath = tfs.createTempFile("", ".png", relativeTo="")

        # Retrieve quoted content of the insertion
        bstr = lineendToOs(utf8Enc(insToken.value, "replace")[0])

        # Store token content in a temporary source file
        srcFilePath = createTempFile(bstr, ".dot")

        # Run external application (shell is used to internally handle missing executable error)
        cmdline = subprocess.list2cmdline((self.extAppExe, "-Tpng",
                "-o", dstFilePath, srcFilePath))

        try:
            popenObject = subprocess.Popen(cmdline, shell=True, stderr=subprocess.PIPE)
            errResponse = popenObject.communicate()[1]
        finally:
            os.remove(srcFilePath)

        if errResponse and "noerror" not in [a.strip() for a in insToken.appendices]:
            appname = mbcsDec(self.EXT_APP_NAME, "replace")[0]
            errResponse = mbcsDec(errResponse, "replace")[0]
            return '<pre>' + _('[%s error: %s]') % (appname, errResponse) + \
                    '</pre>'

        # Get URL for the destination file
        url = tfs.getRelativeUrl(None, dstFilePath, pythonUrl=(exportType != "html_previewWX"))

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


class DotHandler(GraphVizBaseHandler):
    EXT_APP_NAME = "Dot"
    EXE_CONFIG_KEY = "plugin_graphViz_exeDot"


class NeatoHandler(GraphVizBaseHandler):
    EXT_APP_NAME = "Neato"
    EXE_CONFIG_KEY = "plugin_graphViz_exeNeato"


class TwopiHandler(GraphVizBaseHandler):
    EXT_APP_NAME = "Twopi"
    EXE_CONFIG_KEY = "plugin_graphViz_exeTwopi"


class CircoHandler(GraphVizBaseHandler):
    EXT_APP_NAME = "Circo"
    EXE_CONFIG_KEY = "plugin_graphViz_exeCirco"


class FdpHandler(GraphVizBaseHandler):
    EXT_APP_NAME = "Fdp"
    EXE_CONFIG_KEY = "plugin_graphViz_exeFdp"


def registerOptions(ver, app):
    """
    API function for "Options" plugins
    Register configuration options and their GUI presentation
    ver -- API version (can only be 1 currently)
    app -- wxApp object
    """
    # Register options
    defaultGlobalConfigDict = app.getDefaultGlobalConfigDict()
    defaultGlobalConfigDict[("main", GraphVizBaseHandler.DIR_CONFIG_KEY)] = ""

    defaultGlobalConfigDict[("main", DotHandler.EXE_CONFIG_KEY)] = ""
    defaultGlobalConfigDict[("main", NeatoHandler.EXE_CONFIG_KEY)] = ""
    defaultGlobalConfigDict[("main", TwopiHandler.EXE_CONFIG_KEY)] = ""
    defaultGlobalConfigDict[("main", CircoHandler.EXE_CONFIG_KEY)] = ""
    defaultGlobalConfigDict[("main", FdpHandler.EXE_CONFIG_KEY)] = ""

    # Register panel in options dialog
    app.addGlobalPluginOptionsDlgPanel(GraphVizOptionsPanel, "GraphViz")


class GraphVizOptionsPanel(wx.Panel):
    def __init__(self, parent, optionsDlg, app):
        """
        Called when "Options" dialog is opened to show the panel.
        Transfer here all options from the configuration file into the
        text fields, check boxes, ...
        """
        wx.Panel.__init__(self, parent)
        self.app = app

        globalConfig = self.app.getGlobalConfig()

        pt = globalConfig.get("main", GraphVizBaseHandler.DIR_CONFIG_KEY, "")
        self.tfDir = wx.TextCtrl(self, -1, pt)

        pt = globalConfig.get("main", DotHandler.EXE_CONFIG_KEY, "")
        self.tfDot = wx.TextCtrl(self, -1, pt)

        pt = globalConfig.get("main", NeatoHandler.EXE_CONFIG_KEY, "")
        self.tfNeato = wx.TextCtrl(self, -1, pt)

        pt = globalConfig.get("main", TwopiHandler.EXE_CONFIG_KEY, "")
        self.tfTwopi = wx.TextCtrl(self, -1, pt)

        pt = globalConfig.get("main", CircoHandler.EXE_CONFIG_KEY, "")
        self.tfCirco = wx.TextCtrl(self, -1, pt)

        pt = globalConfig.get("main", FdpHandler.EXE_CONFIG_KEY, "")
        self.tfFdp = wx.TextCtrl(self, -1, pt)

        mainsizer = wx.FlexGridSizer(6, 2, 0, 0)
        mainsizer.AddGrowableCol(1, 1)

        mainsizer.Add(wx.StaticText(self, -1, _("Directory of executables:")), 0,
                wx.ALL | wx.EXPAND, 5)
        mainsizer.Add(self.tfDir, 1, wx.ALL | wx.EXPAND, 5)

        mainsizer.Add(wx.StaticText(self, -1, _("Name of dot executable:")), 0,
                wx.ALL | wx.EXPAND, 5)
        mainsizer.Add(self.tfDot, 1, wx.ALL | wx.EXPAND, 5)

        mainsizer.Add(wx.StaticText(self, -1, _("Name of neato executable:")), 0,
                wx.ALL | wx.EXPAND, 5)
        mainsizer.Add(self.tfNeato, 1, wx.ALL | wx.EXPAND, 5)

        mainsizer.Add(wx.StaticText(self, -1, _("Name of twopi executable:")), 0,
                wx.ALL | wx.EXPAND, 5)
        mainsizer.Add(self.tfTwopi, 1, wx.ALL | wx.EXPAND, 5)

        mainsizer.Add(wx.StaticText(self, -1, _("Name of circo executable:")), 0,
                wx.ALL | wx.EXPAND, 5)
        mainsizer.Add(self.tfCirco, 1, wx.ALL | wx.EXPAND, 5)

        mainsizer.Add(wx.StaticText(self, -1, _("Name of fdp executable:")), 0,
                wx.ALL | wx.EXPAND, 5)
        mainsizer.Add(self.tfFdp, 1, wx.ALL | wx.EXPAND, 5)

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
        globalConfig = self.app.getGlobalConfig()

        pt = self.tfDir.GetValue()
        globalConfig.set("main", GraphVizBaseHandler.DIR_CONFIG_KEY, pt)

        pt = self.tfDot.GetValue()
        globalConfig.set("main", DotHandler.EXE_CONFIG_KEY, pt)

        pt = self.tfNeato.GetValue()
        globalConfig.set("main", NeatoHandler.EXE_CONFIG_KEY, pt)

        pt = self.tfTwopi.GetValue()
        globalConfig.set("main", TwopiHandler.EXE_CONFIG_KEY, pt)

        pt = self.tfCirco.GetValue()
        globalConfig.set("main", CircoHandler.EXE_CONFIG_KEY, pt)

        pt = self.tfFdp.GetValue()
        globalConfig.set("main", FdpHandler.EXE_CONFIG_KEY, pt)
