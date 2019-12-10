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
            ("plantuml", ("html_single", "html_previewWX", "html_preview", "html_multi"), PlantUmlHandler),
            )


class PlantUmlHandler:
    """
    Class fulfilling the "insertion by key" protocol.
    """
    JAVA_PATH_CONFIG_KEY = "plugin_plantuml_javaPath"
    JAR_PATH_CONFIG_KEY = "plugin_plantuml_jarPath"

    def __init__(self, app):
        self.app = app
        self.javaExe = None
        self.plantumlJar = None
        self.dotExe = None

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
        self.javaExe = globalConfig.get("main", self.JAVA_PATH_CONFIG_KEY, "")
        self.plantumlJar = globalConfig.get("main", self.JAR_PATH_CONFIG_KEY, "")

        wikiAppDir = self.app.getWikiAppDir()

        if self.javaExe and self.javaExe != os.path.basename(self.javaExe):
            self.javaExe = os.path.join(wikiAppDir, self.javaExe)
        if self.plantumlJar:
            self.plantumlJar = os.path.join(wikiAppDir, self.plantumlJar)

        # Pass dot path to PlantUML only if it's not available in PATH environment variable
        graphVizDirExe = globalConfig.get("main", "plugin_graphViz_dirExe", "")
        graphVizExeDot = globalConfig.get("main", "plugin_graphViz_exeDot", "")
        if graphVizDirExe and graphVizExeDot:
            self.dotExe = os.path.join(wikiAppDir, graphVizDirExe, graphVizExeDot)

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

        if not self.javaExe or not self.plantumlJar:
            # No paths -> show message
            return '<pre>' + _('[Please set path to Java executable and PlantUML JAR file]') + \
                    '</pre>'

        # Retrieve quoted content of the insertion
        bstr = lineendToOs(utf8Enc(insToken.value, "replace")[0])

        # Store token content in a temporary source file
        srcFilePath = createTempFile(bstr, ".puml")

        # Determine destination file path based on source file path
        dstFilePath = os.path.splitext(srcFilePath)[0] + ".png"

        # Get exporters temporary file set (manages creation and deletion of
        # temporary files)
        tfs = exporter.getTempFileSet()

        # Add the destination file to be created to the set
        tfs.addFile(dstFilePath)

        # Run external application (shell is used to internally handle missing executable error)
        cmdline = subprocess.list2cmdline((self.javaExe, "-jar", self.plantumlJar) +
                ("-tpng", "-charset", "utf-8") +
                (("-graphvizdot", self.dotExe) if self.dotExe else ()) +
                (srcFilePath,))

        try:
            popenObject = subprocess.Popen(cmdline, stderr=subprocess.PIPE, shell=True)
            errResponse = popenObject.communicate()[1]
        finally:
            os.remove(srcFilePath)

        if errResponse and "noerror" not in [a.strip() for a in insToken.appendices]:
            errResponse = mbcsDec(errResponse, "replace")[0]
            return '<pre>' + _('[PlantUML error: %s]') % errResponse + \
                    '</pre>'

        # Get URL for the destination file
        url = tfs.getRelativeUrl(None, dstFilePath, pythonUrl=(exportType != "html_previewWX"))

        # Return appropriate HTML code for the image
        if exportType == "html_previewWX":
            # Workaround for internal HTML renderer
            return ('<img src="%s" border="0" align="bottom" alt="plantuml" />'
                    '&nbsp;') % url
        else:
            return '<img src="%s" border="0" align="bottom" alt="plantuml" />' \
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
    defaultGlobalConfigDict = app.getDefaultGlobalConfigDict()
    defaultGlobalConfigDict[("main", PlantUmlHandler.JAVA_PATH_CONFIG_KEY)] = "java"
    defaultGlobalConfigDict[("main", PlantUmlHandler.JAR_PATH_CONFIG_KEY)] = "plantuml.jar"

    # Register panel in options dialog
    app.addOptionsDlgPanel(PlantUmlOptionsPanel, "PlantUML")


class PlantUmlOptionsPanel(wx.Panel):
    def __init__(self, parent, optionsDlg, app):
        """
        Called when "Options" dialog is opened to show the panel.
        Transfer here all options from the configuration file into the
        text fields, check boxes, ...
        """
        wx.Panel.__init__(self, parent)
        self.app = app

        globalConfig = self.app.getGlobalConfig()

        pt = globalConfig.get("main", PlantUmlHandler.JAVA_PATH_CONFIG_KEY, "")
        self.tfJava = wx.TextCtrl(self, -1, pt)

        pt = globalConfig.get("main", PlantUmlHandler.JAR_PATH_CONFIG_KEY, "")
        self.tfJar = wx.TextCtrl(self, -1, pt)

        mainsizer = wx.FlexGridSizer(2, 2, 0, 0)
        mainsizer.AddGrowableCol(1, 1)

        mainsizer.Add(wx.StaticText(self, -1, _("Path to Java executable:")), 0,
                wx.ALL | wx.EXPAND, 5)
        mainsizer.Add(self.tfJava, 1, wx.ALL | wx.EXPAND, 5)

        mainsizer.Add(wx.StaticText(self, -1, _("Path to PlantUML JAR file:")), 0,
                wx.ALL | wx.EXPAND, 5)
        mainsizer.Add(self.tfJar, 1, wx.ALL | wx.EXPAND, 5)

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

        pt = self.tfJava.GetValue()
        globalConfig.set("main", PlantUmlHandler.JAVA_PATH_CONFIG_KEY, pt)

        pt = self.tfJar.GetValue()
        globalConfig.set("main", PlantUmlHandler.JAR_PATH_CONFIG_KEY, pt)
