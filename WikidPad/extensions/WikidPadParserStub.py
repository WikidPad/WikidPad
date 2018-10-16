
import traceback

import wx

from pwiki.OptionsDialog import PluginOptionsPanel

# This is a stub for the actual plugin located in
# "wikidPadParser/WikidPadParser.py". The stub ensures that the real plugin is
# only loaded if the language is actually used.


WIKIDPAD_PLUGIN = (("WikiParser", 1), ("Options", 1))

WIKI_LANGUAGE_NAME = "wikidpad_default_2_0"
WIKI_HR_LANGUAGE_NAME = "WikidPad default 2.0"


def describeWikiLanguage(ver, app):
    """
    API function for "WikiParser" plugins
    Returns a sequence of tuples describing the supported
    insertion keys. Each tuple has the form (intLanguageName, hrLanguageName,
            parserFactory, parserIsThreadsafe, editHelperFactory,
            editHelperIsThreadsafe)
    Where the items mean:
        intLanguageName -- internal unique name (should be ascii only) to
            identify wiki language processed by parser
        hrLanguageName -- human readable language name, unistring
            (TODO: localization)
        parserFactory -- factory function to create parser object(s) fulfilling

        parserIsThreadsafe -- boolean if parser is threadsafe. If not this
            will currently lead to a very inefficient operation
        processHelperFactory -- factory for helper object containing further
            functions needed for editing, tree presentation and so on.
        editHelperIsThreadsafe -- boolean if edit helper functions are
            threadsafe.

    Parameters:

    ver -- API version (can only be 1 currently)
    app -- wxApp object
    """

    return ((WIKI_LANGUAGE_NAME, WIKI_HR_LANGUAGE_NAME, parserFactory,
             True, languageHelperFactory, True),)


_realParserFactory = None
_realLanguageHelperFactory = None


def parserFactory(intLanguageName, debugMode):
    """
    Builds up a parser object. If the parser is threadsafe this function is
    allowed to return the same object multiple times (currently it should do
    so for efficiency).
    For seldom needed parsers it is recommended to put the actual parser
    construction as singleton in this function to reduce startup time of WikidPad.
    For non-threadsafe parsers it is required to create one inside this
    function at each call.

    intLanguageName -- internal unique name (should be ascii only) to
        identify wiki language to process by parser
    """
    global _realParserFactory
    
    if _realParserFactory is None:
        from .wikidPadParser.WikidPadParser import parserFactory as pf
        _realParserFactory = pf

    return _realParserFactory(intLanguageName, debugMode)


def languageHelperFactory(intLanguageName, debugMode):
    """
    Builds up a language helper object. If the object is threadsafe this function is
    allowed to return the same object multiple times (currently it should do
    so for efficiency).

    intLanguageName -- internal unique name (should be ascii only) to
        identify wiki language to process by helper
    """
    global _realLanguageHelperFactory
    
    if _realLanguageHelperFactory is None:
        from .wikidPadParser.WikidPadParser import languageHelperFactory as lhf
        _realLanguageHelperFactory = lhf

    return _realLanguageHelperFactory(intLanguageName, debugMode)


def registerOptions(ver, app):
    """
    API function for "Options" plugins
    Register configuration options and their GUI presentation
    ver -- API version (can only be 1 currently)
    app -- wxApp object
    """
    # Register options
    
    # Interpret footnotes (e.g. [42]) as wiki words?
    app.getDefaultWikiConfigDict()[("main", "footnotes_as_wikiwords")] = "False"

    # Register panel in options dialog
    app.addWikiWikiLangOptionsDlgPanel(WikiLangOptionsPanel,
            WIKI_HR_LANGUAGE_NAME)


class WikiLangOptionsPanel(PluginOptionsPanel):
    def __init__(self, parent, optionsDlg, mainControl):
        """
        Called when "Options" dialog is opened to show the panel.
        Transfer here all options from the configuration file into the
        text fields, check boxes, ...
        """
        PluginOptionsPanel.__init__(self, parent, optionsDlg)
        self.mainControl = mainControl

#         pt = self.mainControl.getConfig().getboolean("main",
#                 "footnotes_as_wikiwords", False)
        self.cbFootnotesAsWws = wx.CheckBox(self, -1,
                _("Footnotes as wiki words"))
#         self.cbFootnotesAsWws.SetValue(pt)

#         pt = self.app.getGlobalConfig().get("main", "plugin_graphViz_exeDot",
#                 u"dot.exe")
#         self.tfDot = wx.TextCtrl(self, -1, pt)

        mainsizer = wx.FlexGridSizer(1, 1, 0, 0)
        mainsizer.AddGrowableCol(0, 1)

        mainsizer.Add(self.cbFootnotesAsWws, 1, wx.ALL | wx.EXPAND, 5)
        
        self.addOptionEntry("footnotes_as_wikiwords",
                self.cbFootnotesAsWws, "b")


#         mainsizer.Add(wx.StaticText(self, -1, _(u"Name of dot executable:")), 0,
#                 wx.ALL | wx.EXPAND, 5)
#         mainsizer.Add(self.tfDot, 1, wx.ALL | wx.EXPAND, 5)

        self.SetSizer(mainsizer)
        self.Fit()
        self.transferOptionsToDialog()


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
        self.transferDialogToOptions()

#         pt = repr(self.cbFootnotesAsWws.GetValue())
#         self.mainControl.getConfig().set("main", "footnotes_as_wikiwords", pt)


