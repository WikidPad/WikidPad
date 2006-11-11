import os, urllib

import wx

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
    return ((u"eqn", ("html_single", "html_preview", "html_multi"), EqnHandler),)


class EqnHandler:
    """
    Class fulfilling the "insertion by key" protocol.
    """
    def __init__(self, app):
        self.app = app
        self.mimetexExe = None
        
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
        self.mimetexExe = self.app.getGlobalConfig().get("main",
                "plugin_mimeTex_exePath", "")

        
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
        bstr = urllib.quote(insToken.quotedValue.encode("latin-1", "replace"))

        if not bstr:
            # Nothing in, nothing out
            return u""
        
        if self.mimetexExe == "":
            # No path to MimeTeX executable -> show message
            return "[Please set path to MimeTeX executable]"

        # Prepare CGI environment. MimeTeX needs only "QUERY_STRING" environment
        # variable
        os.environ["QUERY_STRING"] = bstr

        # Run MimeTeX process
        childIn, childOut = os.popen2(self.mimetexExe, "b")

        # Read stdout of process entirely
        response = childOut.read()

        # Cut off HTTP header (may need changes for non-Windows OS)
        try:
            response = response[(response.index("\n\n") + 2):]
        except ValueError:
            return "[Invalid response from MimeTeX]"

        # Get exporters temporary file set (manages creation and deletion of
        # temporary files)
        tfs = exporter.getTempFileSet()
        
        # Create .gif file out of returned data and retrieve URL for the file
        url = tfs.createTempUrl(response, ".gif")

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



def registerOptions(ver, app):
    """
    API function for "Options" plugins
    Register configuration options and their GUI presentation
    ver -- API version (can only be 1 currently)
    app -- wxApp object
    """
    # Register option
    app.getDefaultGlobalConfigDict()[("main", "plugin_mimeTex_exePath")] = u""
    # Register panel in options dialog
    app.addOptionsDlgPanel(MimeTexOptionsPanel, u"  MimeTeX")


class MimeTexOptionsPanel(wx.Panel):
    def __init__(self, parent, optionsDlg, app):
        wx.Panel.__init__(self, parent)
        self.app = app
        
        pt = self.app.getGlobalConfig().get("main", "plugin_mimeTex_exePath", "")
        
        self.tfPath = wx.TextCtrl(self, -1, pt)

        mainsizer = wx.BoxSizer(wx.VERTICAL)

        inputsizer = wx.BoxSizer(wx.HORIZONTAL)
        inputsizer.Add(wx.StaticText(self, -1, "Path to MimeTeX:"), 0,
                wx.ALL | wx.EXPAND, 5)
        inputsizer.Add(self.tfPath, 1, wx.ALL | wx.EXPAND, 5)
        mainsizer.Add(inputsizer, 0, wx.EXPAND)
        
        self.SetSizer(mainsizer)
        self.Fit()

    def setVisible(self, vis):
        return True

    def checkOk(self):
        return True

    def handleOk(self):
        pt = self.tfPath.GetValue()
        
        self.app.getGlobalConfig().set("main", "plugin_mimeTex_exePath", pt)


