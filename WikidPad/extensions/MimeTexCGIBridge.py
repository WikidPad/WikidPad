import os, urllib.request, urllib.parse, urllib.error, os.path
import subprocess

import wx

from pwiki.StringOps import mbcsEnc

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
    return (("eqn", ("html_single", "html_previewWX", "html_preview",
            "html_multi"), EqnHandler),)


class EqnHandler:
    """
    Class fulfilling the "insertion by key" protocol.
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
        # Find MimeTeX executable by configuration setting
        self.extAppExe = self.app.getGlobalConfig().get("main",
                "plugin_mimeTex_exePath", "")
        
        if self.extAppExe:
            self.extAppExe = os.path.join(self.app.getWikiAppDir(),
                    self.extAppExe)

        
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
        bstr = urllib.parse.quote(mbcsEnc(insToken.value, "replace")[0])

        if not bstr:
            # Nothing in, nothing out
            return ""
        
        if self.extAppExe == "":
            # No path to MimeTeX executable -> show message
            return '<pre>' + _('[Please set path to MimeTeX executable]') + \
                    '</pre>'

        # Prepare CGI environment. MimeTeX needs only "QUERY_STRING" environment
        # variable
        os.environ["QUERY_STRING"] = bstr

        cmdline = subprocess.list2cmdline((self.extAppExe,))

#         childIn, childOut = os.popen2(cmdline, "b")

        # Run MimeTeX process
        popenObject = subprocess.Popen(cmdline, shell=True,
                 stdout=subprocess.PIPE, stdin=subprocess.PIPE,
                 stderr=subprocess.PIPE)

        childOut = popenObject.stdout
        
        # See http://bytes.com/topic/python/answers/634409-subprocess-handle-invalid-error
        # why this is necessary
        popenObject.stdin.close()
        popenObject.stderr.close()

        # Read stdout of process entirely
        response = childOut.read()
        
        childOut.close()
        
        # Cut off HTTP header (may need changes for non-Windows OS)
        try:
            response = response[(response.index(b"\n\n") + 2):]
        except ValueError:
            return '<pre>' + _('[Invalid response from MimeTeX]') + \
                    '</pre>'

        # Get exporters temporary file set (manages creation and deletion of
        # temporary files)
        tfs = exporter.getTempFileSet()
        
        # Create .gif file out of returned data and retrieve URL for the file
        pythonUrl = (exportType != "html_previewWX")
        url = tfs.createTempUrl(response, ".gif", pythonUrl=pythonUrl)

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
    app.getDefaultGlobalConfigDict()[("main", "plugin_mimeTex_exePath")] = ""
    # Register panel in options dialog
    app.addOptionsDlgPanel(MimeTexOptionsPanel, "  MimeTeX")


class MimeTexOptionsPanel(wx.Panel):
    def __init__(self, parent, optionsDlg, app):
        """
        Called when "Options" dialog is opened to show the panel.
        Transfer here all options from the configuration file into the
        text fields, check boxes, ...
        """
        wx.Panel.__init__(self, parent)
        self.app = app
        
        pt = self.app.getGlobalConfig().get("main", "plugin_mimeTex_exePath", "")
        
        self.tfPath = wx.TextCtrl(self, -1, pt)

        mainsizer = wx.BoxSizer(wx.VERTICAL)

        inputsizer = wx.BoxSizer(wx.HORIZONTAL)
        inputsizer.Add(wx.StaticText(self, -1, _("Path to MimeTeX:")), 0,
                wx.ALL | wx.EXPAND, 5)
        inputsizer.Add(self.tfPath, 1, wx.ALL | wx.EXPAND, 5)
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
        
        self.app.getGlobalConfig().set("main", "plugin_mimeTex_exePath", pt)


