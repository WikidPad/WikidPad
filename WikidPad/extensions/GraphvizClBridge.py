import os, os.path, traceback
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
    # Filled in by derived classes
    EXAPPNAME = ""
    EXECONFIGKEY = ""
    
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
        # Find MimeTeX executable by configuration setting
        dirPath = self.app.getGlobalConfig().get("main",
                "plugin_graphViz_dirExe", "")
        if not dirPath:
            self.extAppExe = ""
            return
            
        exeName = self.app.getGlobalConfig().get("main", self.EXECONFIGKEY, "")
        self.extAppExe = os.path.join(self.app.getWikiAppDir(), dirPath, exeName)


        
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
        bstr = lineendToOs(utf8Enc(insToken.value, "replace")[0])

        if not bstr:
            # Nothing in, nothing out
            return ""
        
        if self.extAppExe == "":
            # No path to MimeTeX executable -> show message
            return '<pre>' + _('[Please set path to GraphViz executables]') + \
                    '</pre>'

        # Get exporters temporary file set (manages creation and deletion of
        # temporary files)
        tfs = exporter.getTempFileSet()

        pythonUrl = (exportType != "html_previewWX")
        dstFullPath = tfs.createTempFile("", ".png", relativeTo="")
        url = tfs.getRelativeUrl(None, dstFullPath, pythonUrl=pythonUrl)

        # Store token content in a temporary file
        srcfilepath = createTempFile(bstr, ".dot")
        try:
            cmdline = subprocess.list2cmdline((self.extAppExe, "-Tpng", "-o" + dstFullPath,
                    srcfilepath))

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
                errResponse = ""
            else:
                errResponse = childErr.read()
            
            childErr.close()
        finally:
            os.unlink(srcfilepath)
            
        if errResponse != "":
            appname = mbcsDec(self.EXAPPNAME, "replace")[0]
            errResponse = mbcsDec(errResponse, "replace")[0]
            return '<pre>' + _('[%s Error: %s]') % (appname, errResponse) +\
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
        


class DotHandler(GraphVizBaseHandler):
    EXAPPNAME = "Dot"
    EXECONFIGKEY = "plugin_graphViz_exeDot"

class NeatoHandler(GraphVizBaseHandler):
    EXAPPNAME = "Neato"
    EXECONFIGKEY = "plugin_graphViz_exeNeato"

class TwopiHandler(GraphVizBaseHandler):
    EXAPPNAME = "Twopi"
    EXECONFIGKEY = "plugin_graphViz_exeTwopi"

class CircoHandler(GraphVizBaseHandler):
    EXAPPNAME = "Circo"
    EXECONFIGKEY = "plugin_graphViz_exeCirco"

class FdpHandler(GraphVizBaseHandler):
    EXAPPNAME = "Fdp"
    EXECONFIGKEY = "plugin_graphViz_exeFdp"


def registerOptions(ver, app):
    """
    API function for "Options" plugins
    Register configuration options and their GUI presentation
    ver -- API version (can only be 1 currently)
    app -- wxApp object
    """
    # Register options
    app.getDefaultGlobalConfigDict()[("main", "plugin_graphViz_dirExe")] = ""

    app.getDefaultGlobalConfigDict()[("main", "plugin_graphViz_exeDot")] = "dot.exe"
    app.getDefaultGlobalConfigDict()[("main", "plugin_graphViz_exeNeato")] = "neato.exe"
    app.getDefaultGlobalConfigDict()[("main", "plugin_graphViz_exeTwopi")] = "twopi.exe"
    app.getDefaultGlobalConfigDict()[("main", "plugin_graphViz_exeCirco")] = "circo.exe"
    app.getDefaultGlobalConfigDict()[("main", "plugin_graphViz_exeFdp")] = "fdp.exe"

    # Register panel in options dialog
    app.addGlobalPluginOptionsDlgPanel(GraphVizOptionsPanel, "GraphViz")


class GraphVizOptionsPanel(wx.Panel):
    def __init__(self, parent, optionsDlg, mainControl):
        """
        Called when "Options" dialog is opened to show the panel.
        Transfer here all options from the configuration file into the
        text fields, check boxes, ...
        """
        wx.Panel.__init__(self, parent)
        self.app = wx.GetApp()
        
        pt = self.app.getGlobalConfig().get("main", "plugin_graphViz_dirExe",
                "")
        self.tfDir = wx.TextCtrl(self, -1, pt)

        pt = self.app.getGlobalConfig().get("main", "plugin_graphViz_exeDot",
                "dot.exe")
        self.tfDot = wx.TextCtrl(self, -1, pt)

        pt = self.app.getGlobalConfig().get("main", "plugin_graphViz_exeNeato",
                "neato.exe")
        self.tfNeato = wx.TextCtrl(self, -1, pt)

        pt = self.app.getGlobalConfig().get("main", "plugin_graphViz_exeTwopi",
                "twopi.exe")
        self.tfTwopi = wx.TextCtrl(self, -1, pt)

        pt = self.app.getGlobalConfig().get("main", "plugin_graphViz_exeCirco",
                "circo.exe")
        self.tfCirco = wx.TextCtrl(self, -1, pt)

        pt = self.app.getGlobalConfig().get("main", "plugin_graphViz_exeFdp",
                "fdp.exe")
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
        pt = self.tfDir.GetValue()
        self.app.getGlobalConfig().set("main", "plugin_graphViz_dirExe", pt)

        pt = self.tfDot.GetValue()
        self.app.getGlobalConfig().set("main", "plugin_graphViz_exeDot", pt)

        pt = self.tfNeato.GetValue()
        self.app.getGlobalConfig().set("main", "plugin_graphViz_exeNeato", pt)

        pt = self.tfTwopi.GetValue()
        self.app.getGlobalConfig().set("main", "plugin_graphViz_exeTwopi", pt)

        pt = self.tfCirco.GetValue()
        self.app.getGlobalConfig().set("main", "plugin_graphViz_exeCirco", pt)

        pt = self.tfFdp.GetValue()
        self.app.getGlobalConfig().set("main", "plugin_graphViz_exeFdp", pt)



