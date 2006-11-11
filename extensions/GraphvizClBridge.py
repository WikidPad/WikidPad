import os, urllib, os.path

import wx

from pwiki.TempFileSet import createTempFile

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
            (u"dot", ("html_single", "html_preview", "html_multi"), DotHandler),
            (u"neato", ("html_single", "html_preview", "html_multi"), NeatoHandler),
            (u"twopi", ("html_single", "html_preview", "html_multi"), TwopiHandler),
            (u"circo", ("html_single", "html_preview", "html_multi"), CircoHandler),
            (u"fdp", ("html_single", "html_preview", "html_multi"), FdpHandler)
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
        
        Calls to createContent() and getHoverImage() will only happen after a 
        call to taskStart() and before the call to taskEnd()
        """
        # Find MimeTeX executable by configuration setting
        dirPath = self.app.getGlobalConfig().get("main",
                "plugin_graphViz_dirExe", "")
        if not dirPath:
            self.extAppExe = ""
            return
            
        exeName = self.app.getGlobalConfig().get("main", self.EXECONFIGKEY, "")
        self.extAppExe = os.path.join(dirPath, exeName)

        
    def taskEnd(self):
        """
        Called after export task ended and after the last call to
        createContent() and getHoverImage().
        """
        pass


    def createContent(self, exporter, exportType, insToken):
        """
        Handle an insertion and create the appropriate content.

        exporter -- Exporter object calling the handler
        exportType -- string describing the export type
        insToken -- insertion token to create content for (see also 
                PageAst.Insertion)

        An insertion token has the following member variables:
            key: insertion key (unistring)
            value: value of a non-quoted insertion (unistring) or None
                for a quoted one
            appendices: sequence of strings with the appendices for
                non-quoted insertions
            quotedValue: value of a quoted insertion (unistring) or None
                for a non-quoted one

        Meaning and type of return value is solely defined by the type
        of the calling exporter.
        
        For HtmlXmlExporter a unistring is returned with the HTML code
        to insert instead of the insertion.        
        """
        # Retrieve quoted content of the insertion
        bstr = insToken.quotedValue.encode("latin-1", "replace")

        if not bstr:
            # Nothing in, nothing out
            return u""
        
        if self.extAppExe == "":
            # No path to MimeTeX executable -> show message
            return "[Please set path to GraphViz executables]"

        # Get exporters temporary file set (manages creation and deletion of
        # temporary files)
        tfs = exporter.getTempFileSet()

        dstFullPath = tfs.createTempFile("", ".png", relativeTo="")
        url = tfs.getRelativeUrl(None, dstFullPath)

        # Store token content in a temporary file
        srcfilepath = createTempFile(bstr, ".dot")
        try:
            # Run external application
            childIn, childOut, childErr = os.popen3('%s -Tpng "-o%s" "%s"' % 
                    (self.extAppExe, dstFullPath, srcfilepath), "b")

            errResponse = childErr.read()
        finally:
            os.unlink(srcfilepath)
            
        if errResponse != "":
            return "[%s Error: %s]" % (self.EXAPPNAME, errResponse)


        # Return appropriate HTML code for the image
        if exportType == "html_preview":
            # Workaround for internal HTML renderer
            return u'<img src="%s" border="0" align="bottom" />&nbsp;' % url
        else:
            return u'<img src="%s" border="0" align="bottom" />' % url


    def hasHoverImage(self):
        """
        Returns True if getHoverImage() exists.
        """
        return False
        
    def getHoverImage(self, insToken, tempFileSet):
        """
        Currently not called.
        Returns path to a preview image of the presentation rendered by the
        insertion. The file should be created using the tempFileSet, so it
        can be deleted automatically if not longer in use.
        """
        assert False


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
    app.getDefaultGlobalConfigDict()[("main", "plugin_graphViz_dirExe")] = u""

    app.getDefaultGlobalConfigDict()[("main", "plugin_graphViz_exeDot")] = u"dot.exe"
    app.getDefaultGlobalConfigDict()[("main", "plugin_graphViz_exeNeato")] = u"neato.exe"
    app.getDefaultGlobalConfigDict()[("main", "plugin_graphViz_exeTwopi")] = u"twopi.exe"
    app.getDefaultGlobalConfigDict()[("main", "plugin_graphViz_exeCirco")] = u"circo.exe"
    app.getDefaultGlobalConfigDict()[("main", "plugin_graphViz_exeFdp")] = u"fdp.exe"

    # Register panel in options dialog
    app.addOptionsDlgPanel(GraphVizOptionsPanel, u"  GraphViz")


class GraphVizOptionsPanel(wx.Panel):
    def __init__(self, parent, optionsDlg, app):
        wx.Panel.__init__(self, parent)
        self.app = app
        
        pt = self.app.getGlobalConfig().get("main", "plugin_graphViz_dirExe",
                u"")
        self.tfDir = wx.TextCtrl(self, -1, pt)

        pt = self.app.getGlobalConfig().get("main", "plugin_graphViz_exeDot",
                u"dot.exe")
        self.tfDot = wx.TextCtrl(self, -1, pt)

        pt = self.app.getGlobalConfig().get("main", "plugin_graphViz_exeNeato",
                u"neato.exe")
        self.tfNeato = wx.TextCtrl(self, -1, pt)

        pt = self.app.getGlobalConfig().get("main", "plugin_graphViz_exeTwopi",
                u"twopi.exe")
        self.tfTwopi = wx.TextCtrl(self, -1, pt)

        pt = self.app.getGlobalConfig().get("main", "plugin_graphViz_exeCirco",
                u"circo.exe")
        self.tfCirco = wx.TextCtrl(self, -1, pt)

        pt = self.app.getGlobalConfig().get("main", "plugin_graphViz_exeFdp",
                u"fdp.exe")
        self.tfFdp = wx.TextCtrl(self, -1, pt)

        mainsizer = wx.FlexGridSizer(6, 2, 0, 0)
        # mainsizer.AddGrowableCol(1, 1  )

        mainsizer.Add(wx.StaticText(self, -1, "Directory of executables:"), 0,
                wx.ALL | wx.EXPAND, 5)
        mainsizer.Add(self.tfDir, 1, wx.ALL | wx.EXPAND, 5)

        mainsizer.Add(wx.StaticText(self, -1, "Name of dot executable:"), 0,
                wx.ALL | wx.EXPAND, 5)
        mainsizer.Add(self.tfDot, 1, wx.ALL | wx.EXPAND, 5)

        mainsizer.Add(wx.StaticText(self, -1, "Name of neato executable:"), 0,
                wx.ALL | wx.EXPAND, 5)
        mainsizer.Add(self.tfNeato, 1, wx.ALL | wx.EXPAND, 5)

        mainsizer.Add(wx.StaticText(self, -1, "Name of twopi executable:"), 0,
                wx.ALL | wx.EXPAND, 5)
        mainsizer.Add(self.tfTwopi, 1, wx.ALL | wx.EXPAND, 5)

        mainsizer.Add(wx.StaticText(self, -1, "Name of circo executable:"), 0,
                wx.ALL | wx.EXPAND, 5)
        mainsizer.Add(self.tfCirco, 1, wx.ALL | wx.EXPAND, 5)

        mainsizer.Add(wx.StaticText(self, -1, "Name of fdp executable:"), 0,
                wx.ALL | wx.EXPAND, 5)
        mainsizer.Add(self.tfFdp, 1, wx.ALL | wx.EXPAND, 5)

        self.SetSizer(mainsizer)
        self.Fit()

    def setVisible(self, vis):
        return True

    def checkOk(self):
        return True

    def handleOk(self):
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



