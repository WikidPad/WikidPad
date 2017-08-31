import configparser
import traceback
import io

# from os.path import *

import codecs
import wx

from .MiscEvent import MiscEventSourceMixin
from .WikiExceptions import *

# For compatibility TODO: remove in 2.2
from .SystemInfo import isOSX, isLinux, isWindows

# from WikiExceptions import *

from .StringOps import utf8Enc, utf8Dec, mbcsDec, strToBool

Error = configparser.Error


class UnknownOptionException(Exception): pass



def _setValue(section, option, value, config):
    """
    if value is of type bytes, it is assumed to be mbcs-coded
    if section or option are of type bytes, they are assumed to be utf8 coded
        (it is recommended to use only ascii characters for section/option
        names)
    """
    if type(section) is bytes:
        section = utf8Dec(section)[0]

    if type(option) is bytes:
        option = utf8Dec(option)[0]

    if type(value) is bytes:
        value = mbcsDec(value)[0]
    elif type(value) is not str:
        value = str(value)

    if not config.has_section(section):
        config.add_section(section)

    config.set(section, option, value)


def _fillWithDefaults(config, defaults):
    for s, o in list(defaults.keys()):
        if not config.has_option(s, o) and defaults[(s, o)] is not None:
            _setValue(s, o, defaults[(s, o)], config)



class _AbstractConfiguration:
    def get(self, section, option, default=None):
        raise NotImplementedError   # abstract

    def getint(self, section, option, default=None):
        result = self.get(section, option)
        if result is None:
            return default

        try:
            return int(result)
        except ValueError:
            # Can't convert result string to integer
            return default


    def getfloat(self, section, option, default=None):
        result = self.get(section, option)
        if result is None:
            return default

        try:
            return float(result)
        except ValueError:
            # Can't convert result string to float
            return default


    def getboolean(self, section, option, default=None):
        result = self.get(section, option)
        if result is None:
            return default

        return strToBool(result, False)

    @staticmethod
    def isUnicode():
        """
        Return if GUI is in unicode mode. Legacy function, TODO 2.5: Remove
        """
        return True



class SingleConfiguration(_AbstractConfiguration, MiscEventSourceMixin):
    """
    Wraps a single ConfigParser object
    """

    def __init__(self, configdef, fallthroughDict=None):
        """
        configdef -- Dictionary with defaults for configuration file
        fallthroughDict -- Dictionary with settings for fallthrough mode
                (only stored here, but processed by CombinedConfiguration)
        """
        MiscEventSourceMixin.__init__(self)

        self.configParserObject = None
        self.configPath = None

        self.configDefaults = configdef

        if fallthroughDict is None:
            self.fallthroughDict = {}
        else:
            self.fallthroughDict = fallthroughDict
        self.writeAccessDenied = False


    def get(self, section, option, default=None):
        """
        Return a configuration value returned as string/unicode which
        is entered in given section and has specified option key.
        """
        if type(section) is bytes:
            section = utf8Dec(section)[0]

        if type(option) is bytes:
            option = utf8Dec(option)[0]

        result = None

        if self.isOptionAllowed(section, option):
            if self.configParserObject.has_option(section, option):
                result = self.configParserObject.get(section, option)
            else:
                result = self.configDefaults[(section, option)]
        else:
            raise UnknownOptionException(_("Unknown option %s:%s") % (section, option))

        if result is None:
            return default

#         try:
#             result = utf8Dec(result)[0]
#         except UnicodeError:
#             # Result is not Utf-8 -> try mbcs
#             try:
#                 result = mbcsDec(result)[0]
#             except UnicodeError:
#                 # Result can't be converted
#                 result = default

        return result


    def getDefault(self, section, option):
        """
        Return the default configuration value as string/unicode
        """
        if type(section) is bytes:
            section = utf8Dec(section)[0]

        if type(option) is bytes:
            option = utf8Dec(option)[0]

        if self.isOptionAllowed(section, option):
            return self.configDefaults[(section, option)]
        else:
            raise UnknownOptionException(_("Unknown option %s:%s") % (section, option))




    def setWriteAccessDenied(self, flag):
        self.writeAccessDenied = flag

    def getWriteAccessDenied(self):
        return self.writeAccessDenied

    def isReadOnlyEffect(self):
        return self.writeAccessDenied


    def isOptionAllowed(self, section, option):
        """
        The function tests if an option is valid.
        Only options can be set/retrieved which have an entry in the
        defaults and if the configParserObject is valid.
        """
        if type(section) is bytes:
            section = utf8Dec(section)[0]

        if type(option) is bytes:
            option = utf8Dec(option)[0]

        return self.configParserObject is not None and \
                (section, option) in self.configDefaults

    # TODO Allow in read-only mode?
    def set(self, section, option, value):
        if type(section) is bytes:
            section = utf8Dec(section)[0]

        if type(option) is bytes:
            option = utf8Dec(option)[0]

        if self.isOptionAllowed(section, option):
            _setValue(section, option, value, self.configParserObject)
        else:
            raise UnknownOptionException(_("Unknown option %s:%s") % (section, option))


    def fillWithDefaults(self):
        _fillWithDefaults(self.configParserObject, self.configDefaults)


    def setConfigParserObject(self, config, fn):
        self.configParserObject = config
        self.configPath = fn

    def getConfigParserObject(self):
        return self.configParserObject

    def getConfigPath(self):
        return self.configPath

    def loadConfig(self, fn):
        if fn is None:
            self.setConfigParserObject(None, None)
            return

        config = configparser.ConfigParser(empty_lines_in_values=False,
                default_section=None, interpolation=None)
        
        try:
            configFile = open(fn, 'rt', encoding="utf-8",
                    errors="surrogateescape")
        except FileNotFoundError:
            raise MissingConfigurationFileException(_("Config file not found"))
        
        config.read_file(configFile)
        self.setConfigParserObject(config, fn)


    def createEmptyConfig(self, fn):
        config = configparser.ConfigParser(empty_lines_in_values=False,
                default_section=None, interpolation=None)
        self.setConfigParserObject(config, fn)

    def getFallthroughDict(self):
        return self.fallthroughDict


    def save(self):
        """
        Save all configurations
        """
        if self.isReadOnlyEffect():
            return

        if self.configParserObject:
#             sfile = io.StringIO()
#             self.configParserObject.write(sfile)
            configFile = open(self.configPath, 'w', encoding="utf-8",
                    errors="surrogateescape")
            try:
                self.configParserObject.write(configFile)
            finally:
                configFile.close()

    def informChanged(self, oldSettings):
        """
        This should be called after configuration was changed to let
        the object send out an event.
        The set method does not send events automatically to prevent
        the creation of many events (one per each set call) instead
        of one at the end of changes
        """
        self.fireMiscEventProps({"changed configuration": True,
                "old config settings": oldSettings})



class CombinedConfiguration(_AbstractConfiguration):
    """
    Manages global and wiki specific configuration options.
    Mainly wraps two SingleConfiguration instances
    """

    def __init__(self, globalconfig, wikiconfig):
        """
        globalconfig -- SingleConfiguration object for global settings
        wikiconfig -- Same for wiki settings
        """
        self.globalConfig = globalconfig
        self.wikiConfig = wikiconfig

    def get(self, section, option, default=None):
        """
        Return a configuration value returned as string/unicode which
        is entered in given section and has specified option key.
        """
        if type(section) is bytes:
            section = utf8Dec(section)[0]

        if type(option) is bytes:
            option = utf8Dec(option)[0]

        result = None

        checkWiki = True
        checkGlobal = True

        if option.startswith("option/wiki/"):
            option = option[12:]
            checkGlobal = False
        elif option.startswith("option/user/"):
            option = option[12:]
            checkWiki = False

        if checkWiki:
            if self.wikiConfig is not None and \
                    self.wikiConfig.isOptionAllowed(section, option):
                result = self.wikiConfig.get(section, option, default)
                ftDict = self.wikiConfig.getFallthroughDict()
                if (section, option) not in ftDict or \
                        ftDict[(section, option)] != result:
                    checkGlobal = False

            # TODO more elegantly
            elif (section, option) in WIKIDEFAULTS:
                result = default
                checkGlobal = False
            elif not checkGlobal:
                raise UnknownOptionException(_("Unknown option %s:%s") % (section, option))

        if checkGlobal:
            if self.globalConfig is not None:
                result = self.globalConfig.get(section, option, default)
            else:
                raise UnknownOptionException(_("Unknown option %s:%s") % (section, option))

        if result is None:
            return default

        return result


    def getDefault(self, section, option):
        """
        Return the default configuration value as string/unicode
        """
        if type(section) is bytes:
            section = utf8Dec(section)[0]

        if type(option) is bytes:
            option = utf8Dec(option)[0]

        result = None

        checkWiki = True
        checkGlobal = True

        if option.startswith("option/wiki/"):
            option = option[12:]
            checkGlobal = False
        elif option.startswith("option/user/"):
            option = option[12:]
            checkWiki = False

        if checkWiki:
            # TODO more elegantly
            if (section, option) in WIKIDEFAULTS:
                result = WIKIDEFAULTS.get((section, option))
                if (section, option) not in WIKIFALLTHROUGH or \
                        WIKIFALLTHROUGH[(section, option)] != result:
                    checkGlobal = False

            elif not checkGlobal:
                raise UnknownOptionException(_("Unknown option %s:%s") % (section, option))

        if checkGlobal:
            if self.globalConfig is not None:
                result = self.globalConfig.getDefault(section, option)
            else:
                raise UnknownOptionException(_("Unknown option %s:%s") % (section, option))

        return result


    def isOptionAllowed(self, section, option):
        """
        The function tests if an option is valid.
        Only options can be set/retrieved which have an entry in the
        defaults and if the configParserObject is valid.
        """
        if type(section) is bytes:
            section = utf8Dec(section)[0]

        if type(option) is bytes:
            option = utf8Dec(option)[0]

        checkWiki = True
        checkGlobal = True

        if option.startswith("option/wiki/"):
            option = option[12:]
            checkGlobal = False
        elif option.startswith("option/user/"):
            option = option[12:]
            checkWiki = False

        if checkWiki and (section, option) in WIKIDEFAULTS:
            return True

        if checkGlobal and (section, option) in GLOBALDEFAULTS:
            return True

        return False


    def set(self, section, option, value):
        if type(section) is bytes:
            section = utf8Dec(section)[0]

        if type(option) is bytes:
            option = utf8Dec(option)[0]

        if option.startswith("option/wiki/"):
            option = option[12:]
            self.wikiConfig.set(section, option, value)
        elif option.startswith("option/user/"):
            option = option[12:]
            self.globalConfig.set(section, option, value)
        elif self.wikiConfig is not None and \
                (section, option) in self.wikiConfig.getFallthroughDict():
            raise UnknownOptionException(_("Ambiguos option set %s:%s") % (section, option))
        else:
            if self.wikiConfig is not None and \
                    self.wikiConfig.isOptionAllowed(section, option):
                self.wikiConfig.set(section, option, value)
            elif self.globalConfig is not None:
                self.globalConfig.set(section, option, value)
            else:
                raise UnknownOptionException(_("Unknown option %s:%s") % (section, option))


#         if self.wikiConfig is not None and \
#                 self.wikiConfig.isOptionAllowed(section, option):
#             self.wikiConfig.set(section, option, value)
#         elif self.globalConfig is not None and \
#                 self.globalConfig.isOptionAllowed(section, option):
#             self.globalConfig.set(section, option, value)
#         else:
#             raise UnknownOptionException, _(u"Unknown option %s:%s") % (section, option)


    def fillGlobalWithDefaults(self):
        self.globalConfig.fillWithDefaults()


    def fillWikiWithDefaults(self):
        self.wikiConfig.fillWithDefaults()

    def loadWikiConfig(self, fn):
        self.wikiConfig.loadConfig(fn)

    def createEmptyWikiConfig(self, fn):
        self.wikiConfig.createEmptyConfig(fn)

    def getWikiConfig(self):
        return self.wikiConfig

    def setWikiConfig(self, config):
        self.wikiConfig = config


    def loadGlobalConfig(self, fn):
        self.globalConfig.loadConfig(fn)

    def createEmptyGlobalConfig(self, fn):
        self.globalConfig.createEmptyConfig(fn)

    def getGlobalConfig(self):
        return self.globalConfig

    def setGlobalConfig(self, config):
        self.globalConfig = config

    def saveGlobalConfig(self):
        if self.globalConfig is not None:
            self.globalConfig.save()


    def save(self):
        """
        Save all configurations
        """
        self.saveGlobalConfig()

        try:
            if self.wikiConfig is not None:
                self.wikiConfig.save()
        except:
            traceback.print_exc()


    def informChanged(self, oldSettings):
        """
        This should be called after configuration was changed. It is called
        for its SingleConfiguration objects in turn to let them send events
        """
        if self.globalConfig is not None:
            self.globalConfig.informChanged(oldSettings)

        if self.wikiConfig is not None:
            self.wikiConfig.informChanged(oldSettings)



GLOBALDEFAULTS = {
    ("main", "wiki_history"): None,   # Should be overwritten with concrete value
    ("main", "last_wiki"): "WikidPadHelp/WikidPadHelp.wiki",
    ("main", "size_x"): "500",
    ("main", "size_y"): "300",

    ("main", "pos_x"): "10",
    ("main", "pos_y"): "10",
    ("main", "splitter_pos"): '170',
    ("main", "log_window_autoshow"): "True", # Automatically show log window if messages added
    ("main", "log_window_autohide"): "True", # Automatically hide log window if empty
    ("main", "log_window_sashPos"): "1",  # Real splitter pos (obsolete, contained in windowLayout)
    ("main", "log_window_effectiveSashPos"): "120",  # Splitter pos when calling showEffWindow (obsolete, contained in windowLayout)
    ("main", "docStructure_position"): "0",  # Mode where to place the document structure window,
            # 0: Hidden, 1:Left, 2:Right, 3:Above, 4:Below
    ("main", "docStructure_depth"): "15",  # Maximum number of heading which is shown in document structure window
            # (between 1 and 15)
    ("main", "docStructure_autohide"): "False", # Automatically hide doc structure after something was activated in it.
    ("main", "docStructure_autofollow"): "True", # Selection in document structure follows text cursor position

    ("main", "toolbar_show"): "True",  # Show the toolbar?
    ("main", "zoom"): '0',  # Zoom factor for editor
    ("main", "preview_zoom"): '0',  # Zoom factor for preview
    ("main", "last_active_dir"): None,   # Should be overwritten with concrete value
    ## ("main", "font"): "Courier New",
    ("main", "gui_language"): "",   # Language (as locale code) to use in GUI. Empty string means system default language
    ("main", "recentWikisList_length"): "5",   # Length of recent wikis list
    ("main", "font"): None,
    ("main", "wrap_mode"): "True",
    ("main", "indentation_guides"): "True",
    ("main", "auto_bullets"): "True",  # Show bullet/number after newline if current line has bullet
    ("main", "auto_indent"): "True",
    ("main", "editor_tabsToSpaces"): "True",  # Write spaces when hitting TAB key
    ("main", "show_lineNumbers"): "False",
    ("main", "editor_useFolding"): "False",
    ("main", "editor_useImeWorkaround"): "False",  # Special workaround by handling input by WikidPad instead of Scintilla.
            # Seems to help against some problems with Vietnamese input programs
#     ("main", "wikiWord_rename_wikiLinks"): u"0", # When renaming wiki word, should it try to rename links to the word, too?
#             # 0:No, 1:Yes, 2:Ask for each renaming
    ("main", "wikiWord_renameDefault_modifyWikiLinks"): "off", # When renaming wiki word, should it try to rename links to the word, too?
            # "off": No link rename, "advanced": New method, rather reliable, "simple": Old method, unreliable but fast
            # This is the default setting but can be modified for each rename operation.
    ("main", "wikiWord_renameDefault_renameSubPages"): "True", # When renaming wiki word, should sub pages also be renamed
            # This is the default setting but can be modified for each rename operation
    ("main", "mainTree_position"): "0",  # Mode where to place the main tree,
            # 0:Left, 1:Right, 2:Above, 3:Below
    ("main", "viewsTree_position"): "0",  # Mode how to show the "Views" tree relative to main tree,
            # 0: Not at all, 1:Above, 2:Below, 3:Left, 4:Right

        # Actual layout data processed by PersonalWikiFrame.changeLayoutByCf()
        # which in turn calls WindowLayout.WindowSashLayouter.realizeNewLayoutByCf()

        # The value is not set directly but generated by
        # WindowLayout.calculateMainWindowLayoutCfString() each time configuration
        # changes by using some of the other layout settings in configuration.

    ("main", "windowLayout"): "name:main area panel;"\
            "layout relation:left&layout relative to:main area panel&name:maintree&"\
                "layout sash position:1&layout sash effective position:170;"\
            "layout relation:below&layout relative to:main area panel&name:log&"\
                "layout sash position:1&layout sash effective position:120",

            # !!!
#     ("main", "windowLayout"): "name:main area panel;"\
#             "layout relation:left&layout relative to:main area panel&name:maintree&"\
#                 "layout sash position:170&layout sash effective position:170;"\
#             "layout relation:below&layout relative to:maintree&name:viewstree;"\
#             "layout relation:below&layout relative to:main area panel&name:log&"\
#                 "layout sash position:1&layout sash effective position:120",
#             # !!!


    ("main", "chooseWikiWordDialog_sortOrder"): "None",  # How to sort wiki words shown as
            # parents, children, ... in the ChooseWikiWordDialog? "None": No particular order
            # "AlphaAsc": Alphabetically ascending

    ("main", "hotKey_showHide_byApp"): "", # System-wide hotkey to show/hide program. It is described
            # in the usual shortcut syntax e.g. "Ctrl-Alt-A".
            # This key is bound to the application. A second key can be bound to a particular
            # wiki
    ("main", "hotKey_showHide_byApp_isActive"): "True", # Separate switch to deactivate hotkey
            # without deleting the hotkey setting itself

    ("main", "wikiOpenNew_defaultDir"): "",   # Default directory to show when opening
            # or creating a wiki. If entry is empty, a built-in default is used.

    ("main", "wikiLockFile_ignore"): "False",  # Ignore the lock file created by another instance
            # when opening a wiki?
    ("main", "wikiLockFile_create"): "True",  # Create a lock file when opening a wiki?

    ("main", "auto_save"): "True",  # Boolean field, if auto save should be active
    ("main", "auto_save_delay_key_pressed"): "5",  # Seconds to wait after last key pressed and ...
    ("main", "auto_save_delay_dirty"): "60",  # secs. to wait after page became dirty before auto save

    ("main", "hideundefined"): "False", # hide undefined wikiwords in tree
    ("main", "tree_auto_follow"): "True", # The tree selection follows when opening a wiki word
    ("main", "tree_update_after_save"): "True", # The tree is updated after a save
    ("main", "tree_no_cycles"): "False", # Cycles in tree like NodeA -> NodeB -> NodeA are not shown
    ("main", "tree_autohide"): "False", # Automatically hide tree(s) after something was selected in it.
    ("main", "tree_bg_color"): "",  # Background color of the trees

    ("main", "tree_font_nativeDesc"): "",  # Data about tree font. If empty, default font is used

    ("main", "tree_updateGenerator_minDelay"): "0.1",  # Minimum delay (in secs) between calls to
            # the update generator

#     ("main", "tree_font_pointSize"): u"",  # Data about tree font. If pointSize is empty, default fonts is used
#     ("main", "tree_font_family"): u"",  # Data about tree font.
#     ("main", "tree_font_style"): u"",  # Data about tree font.
#     ("main", "tree_font_weight"): u"",  # Data about tree font.
#     ("main", "tree_font_underline"): u"",  # Data about tree font.
#     ("main", "tree_font_faceName"): u"",  # Data about tree font.
#     ("main", "tree_font_encoding"): u"",  # Data about tree font.


    # Security options
    ("main", "process_autogenerated_areas"): "False", # process auto-generated areas ?
    ("main", "insertions_allow_eval"): "False",  # Evaluate :eval: and possible other script insertions?
#     ("main", "tempFiles_inWikiDir"): "False",  # Store temp. files in wiki dir instead of normal temp dir.?
    ("main", "script_security_level"): "0",  # Allow the use of scripts and
            # import_scripts attribute? 0: No scripts at all; 1: No import_scripts;
            # 2: allow local import_scripts; 3: allow also global.import_scripts
    ("main", "script_search_reverse"): "False", # Normally when searching for a script first the local page
            # is searched, then local import_scripts, then global.import_scripts. If this is set to
            # True the search order is reversed


    # HTML options
    ("main", "new_window_on_follow_wiki_url"): "1", # Open new window when following a "wiki:" URL 0:No, 1:Yes, new process
    ("main", "start_browser_after_export"): "True",
    ("main", "facename_html_preview"): "", # Facename(s) for the internal HTML preview
    ("main", "html_preview_proppattern"): "",  # RE pattern for attributes in HTML preview
    ("main", "html_preview_proppattern_is_excluding"): "False", # Should these pattern be excluded instead of included?
    ("main", "html_export_proppattern"): "",  # Same for HTML exporting
    ("main", "html_export_proppattern_is_excluding"): "False",  # Same for HTML exporting
    ("main", "html_preview_pics_as_links"): "False",  # Show only links to pictures in HTML preview
    ("main", "html_export_pics_as_links"): "False",  # Same for HTML exporting
    ("main", "export_table_of_contents"): "0",  # Show table of contents when exporting
            # 0:None, 1:formatted as tree, 2:as list
    ("main", "export_lastDialogTag"): "",  # Tag of the last used export tag to set as default in export dialog
    ("main", "html_toc_title"): "Table of Contents",  # title of table of contents
    ("main", "html_export_singlePage_sepLineCount"): "10",  # How many empty lines to separate
            # two wiki pages in a single HTML page
    ("main", "html_preview_renderer"): "0",  # 0: Internal wxWidgets; 1: IE; 2: Mozilla; 3: Webkit
    ("main", "html_preview_ieShowIframes"): "False",  # Show iframes with external sources inside IE preview?
    ("main", "html_preview_webkitViKeys"): "False",  # Allow shortcut keys of vi editor to move around in Webkit preview
    ("main", "html_preview_reduceUpdateHandling"): "False",  # Switch off reaction on "updated wiki page" events
            # to avoid automatic scrolling of preview window upward to begin (especially for IE)

    ("main", "html_body_link"): "",  # for HTML preview/export, color for link or "" for default
    ("main", "html_body_alink"): "",  # for HTML preview/export, color for active link or "" for default
    ("main", "html_body_vlink"): "",  # for HTML preview/export, color for visited link or "" for default
    ("main", "html_body_text"): "",  # for HTML preview/export, color for text or "" for default
    ("main", "html_body_bgcolor"): "",  # for HTML preview/export, color for background or "" for default
    ("main", "html_body_background"): "",  # for HTML preview/export, URL for background image or "" for none
    ("main", "html_header_doctype"): 'DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.0 Transitional//EN"',


    # Editor options
    ("main", "sync_highlight_byte_limit"): "400",  # Size limit when to start asyn. highlighting in editor
    ("main", "async_highlight_delay"): "0.2",  # Delay after keypress before starting async. highlighting
    ("main", "editor_shortHint_delay"): "500",  # Delay in milliseconds until the short hint defined for a wikiword is displayed
            # 0 deactivates short hints
    ("main", "editor_autoUnbullets"): "True",  # When pressing return on line with lonely bullet, remove bullet?
    ("main", "editor_autoComplete_closingBracket"): "False",  # Append closing bracket to suggested wiki words
            # for autocompletion ("[Two" -> "[Two words]" instead of -> "[Two words")
    ("main", "editor_sync_byPreviewSelection"): "False", # If True, the selection in preview will be searched in editor
            # for synchronization of both.
    ("main", "editor_colorizeSearchFragments"): "False", # Search fragments (part after # in wiki link) are colored
            # separately in syntax coloring (by default blue if present, black if not). May slow down highlighting.
    ("main", "attributeDefault_global.wrap_type"): "word", # Default for attribute "global.wrap_type".
            # word: wrap lines word-wise, char: wrap lines character-wise (for Asian languages)
    ("main", "editor_tabWidth"): "4",  # How many spaces should a tab be wide?
    ("main", "editor_onlineSpellChecker_active"): "False",  # Online-spellchecker (check as you type)?
    ("main", "editor_imageTooltips_localUrls"): "True",  # Show image preview as tooltip for local image URL
    ("main", "editor_imageTooltips_maxWidth"): "200",  # Maximum width for image tooltip
    ("main", "editor_imageTooltips_maxHeight"): "200",  # Maximum height for image tooltip

    ("main", "editor_imagePaste_filenamePrefix"): "",  # Prefix to put before the filename.
    ("main", "editor_imagePaste_fileType"): "1",  # When pasting images into WikidPad, which file type
            # should be used. 0: Deactivate image-paste; 1: PNG format; 2: JPEG
    ("main", "editor_imagePaste_quality"): "75",  # Which quality should the (JPEG-)image have?
            # 0 zero means very bad, 100 means very good
    ("main", "editor_imagePaste_askOnEachPaste"): "True",  # When pasting image, ask each time for settings?
    ("main", "editor_filePaste_prefix"): "",  # When dropping files into editor, how to prefix, join(middle) and suffix them?
    ("main", "editor_filePaste_middle"): "\\x20",  # These three values are escaped with StringOps.escapeForIni to preserve spaces
    ("main", "editor_filePaste_suffix"): "",
    ("main", "editor_filePaste_bracketedUrl"): "True", # Should the URL be inserted in brackets (and with
            # spaces in it preserved unquoted)?

    ("main", "editor_paste_typeOrder"): "files;plainText;bitmap;wmf;rawHtml", # In which order should Paste() look for
            # types on clipboard (first found is used). Types are separated by ';', mapping to localized human readable
            # name is provided by WikiTxtCtrl.getHrNameForPasteType(pasteType)

    ("main", "userEvent_event/paste/editor/files"): "action/editor/this/paste/files/insert/url/ask",  # How to react on pasting files into editor?
            # "action/none": Do nothing; "action/editor/this/paste/files/insert/url/absolute" insert absolute urls,
            # ".../relative": relative URLs, ".../tostorage": copy to files storage and create relative URL
            # ".../ask": show dialog


    ("main", "editor_compatibility_ViKeys"): "False", # Use vi emulation keys in editor?


    # Editor color options
    ("main", "editor_plaintext_color"): "", # Color of plain text (and non-exist. wikiwords) in editor
    ("main", "editor_link_color"): "", # Color of links (URL and wikiwords)
    ("main", "editor_attribute_color"): "", # Color of attributes (=properties) and scripts
    ("main", "editor_bg_color"): "",  # Background color of the editor
    ("main", "editor_selection_fg_color"): "",  # Foreground color of the selection in the editor
    ("main", "editor_selection_bg_color"): "",  # Background color of the selection in the editor
    ("main", "editor_margin_bg_color"): "",  # Background color of margins in the editor except fold margin
    ("main", "editor_caret_color"): "",  # Color of caret in the editor

    # Clipboard catcher (some OS')
    ("main", "clipboardCatcher_prefix"): r"",  # Prefix to prepend before each caught clipboard snippet
    ("main", "clipboardCatcher_suffix"): r"\n",  # Suffix to append after each caught clipboard snippet
    ("main", "clipboardCatcher_filterDouble"): "True",  # If same text shall be inserted twice (or more often)
            # do not react
    ("main", "clipboardCatcher_userNotification"): "0",  # Type of notification when new clipboard snippet is caught, 0: None; 1: Sound
    ("main", "clipboardCatcher_soundFile"): "",  # Filepath of sound to play if notification type is 1. Empty path plays bell


    # File Launcher (for non-Windows OS)
    ("main", "fileLauncher_path"): "", # Path to an external program taking a path or URL to start appropriate application
            # depending on file type. For Windows, the console command "start" does this.


    # Mouse options
    ("main", "mouse_middleButton_withoutCtrl"): "1", # If middle mouse button is pressed on a link in editor or preview, without
            # Ctrl pressed, should it then open link in  0: a new tab in foreground, 1: new tab background, 2: same tab
    ("main", "mouse_middleButton_withCtrl"): "0", # Same, but if Ctrl is pressed

    ("main", "mouse_scrollUnderPointer"): "False", # Windows only, experimental, incomplete: Scroll window under pointer instead
            # of focused window

    ("main", "mouse_reverseWheelZoom"): "False", # Normally (since 2.3beta13) upward is zoom in, downward is zoom out.
            # If this settings is true this is reversed for editor and internal HTML-preview (other previews not supported)

    ("main", "userEvent_mouse/leftdoubleclick/preview/body"): "action/none", # How to react when user double-clicks somewhere into body of preview?
            # "action/none": Do nothing; "action/presenter/this/subcontrol/textedit": Switch current subcontrol to textedit mode;
            # "action/presenter/new/foreground/end/page/this/subcontrol/textedit": New tab with same wikiword in edit mode

    ("main", "userEvent_mouse/middleclick/pagetab"): "action/none",  # How to react on middle click on tab?
            # "action/none": Do nothing; "action/presenter/this/close" close this tab

    ("main", "userEvent_mouse/leftdrop/editor/files"): "action/editor/this/paste/files/insert/url/absolute",  # How to react on dropping files to editor?
            # "action/none": Do nothing; "action/editor/this/paste/files/insert/url/absolute" insert absolute urls,
            # ".../relative": relative URLs, ".../tostorage": copy to files storage and create relative URL

    ("main", "userEvent_mouse/leftdrop/editor/files/modkeys/shift"): "action/editor/this/paste/files/insert/url/relative",
            # How to react on dropping files to editor if shift key is pressed?

    ("main", "userEvent_mouse/leftdrop/editor/files/modkeys/ctrl"): "action/editor/this/paste/files/insert/url/tostorage",
            # How to react on dropping files to editor if ctrl key is pressed?

    # Time view/time line/calendar options
    ("main", "timeView_position"): "0",  # Mode where to place the time view window,
            # 0: Hidden, 1:Left, 2:Right, 3:Above, 4:Below
    ("main", "timeView_dateFormat"): "%Y %m %d",  # Time format to show and enter dates in the time view,
            # especially in the timeline
    ("main", "timeView_autohide"): "False", # Automatically hide time view after something was selected in it.
    ("main", "timeView_showWordListOnHovering"): "True", # If True the wordlist of a date is shown when hovering
            # over the entry
    ("main", "timeView_showWordListOnSelect"): "False", # If True the wordlist of a date is shown when
            # entry is selected
    ("main", "timeView_lastSelectedTab"): "modified", # Which tab was selected last when closing WikidPad?
            # "modified": Modified time, "version": Versioning tab

    ("main", "timeline_showEmptyDays"): "True", # Show days for which no wikiword is associated?
    ("main", "timeline_sortDateAscending"): "True", # If True the newer days are downward in the list, otherwise upward

    ("main", "versioning_dateFormat"): "%Y %m %d",  # Time format to show dates in the versioning view
    ("main", "wikiWideHistory_dateFormat"): "%x %I:%M %p",  # Time format to show "visited" time in wiki-wide history

    ("main", "wikiWideHistory_columnWidths"): "100,100", # Width of "page name" and
            # "visited" column in wiki-wide history panel


    # New wiki defaults
    ("main", "newWikiDefault_editor_text_mode"): "False",  # force the editor to write platform dependent files to disk
            # (line endings as CR/LF, LF or CR)
    ("main", "newWikiDefault_wikiPageFiles_asciiOnly"): "False", # Use only ASCII characters in filenames of wiki page files.


    # Search options
    ("main", "search_wiki_searchType"): "0",  # Default search type for wiki-wide search
            # 0: Regex; 1: Boolean regex; 2: Text as is; 3: Indexed search
    ("main", "search_wiki_caseSensitive"): "False",  # Wiki-wide search case sensitive?
    ("main", "search_wiki_wholeWord"): "False",  # Wiki-wide search for whole words only?
    ("main", "search_wiki_context_before"): "20", # No. of context characters before
    ("main", "search_wiki_context_after"): "30",  # and after a found pattern
    ("main", "search_wiki_count_occurrences"): "True", # Show for each page the number of found matches
    ("main", "search_wiki_max_count_occurrences"): "100", # Stop after how many occurrences on a page

    ("main", "fastSearch_sizeX"): "200",  # Size of the fastsearch popup frame
    ("main", "fastSearch_sizeY"): "400",
    ("main", "incSearch_autoOffDelay"): "0", # Secs. of inactivity until stopping incremental
            # search automatically, 0 means no auto. stop
    ("main", "fastSearch_searchType"): "0",  # Default search type for fast search
            # (little text field in toolbar). 0: Regex; 1: "Anded" regex; 2: Text as is
    ("main", "fastSearch_caseSensitive"): "False",  # Fast search case sensitive?
    ("main", "fastSearch_wholeWord"): "False",  # Fast search for whole words only

    ("main", "search_dontAllowCancel"): "False", # Iff true a running search can't be canceled
            # (advanced option to cure a problem on Mac OS)
    ("main", "search_stripSpaces"): "False", # Iff True then leading and trailing spaces are
            # stripped from search text before searching

    # Miscellaneous
    ("main", "print_margins"): "0,0,0,0", # Left, upper, right, lower page margins on printing
    ("main", "print_plaintext_font"): "", # Font description for printing in plain text mode
    ("main", "print_plaintext_wpseparator"): "\\n\\n\\n\\n", # How to separate wikiword pages (uses re escaping)
    ("main", "print_lastDialogTag"): "", # Tag of the last used print tag to set as default in print main dialog

    ("main", "windowmode"): "0",
    ("main", "frame_stayOnTop"): "False",  # Should frame stay on top of all other windows?
    ("main", "showontray"): "0",
    ("main", "minimize_on_closeButton"): "False", # Minimize if the close button ("X") is pressed
    ("main", "mainTabs_switchMruOrder"): "True", # Switch between tabs in most-recently used order
    ("main", "startup_splashScreen_show"): "True", # Show splash screen on startup
    ("main", "openWordDialog_askForCreateWhenNonexistingWord"): "True", # Ask if to create
            # (instead of create without ask) when trying to open non-existing word in "Open WikiWord" dialog
    ("main", "strftime"): "%x %I:%M %p",  # time format when inserting time in a page
    ("main", "pagestatus_timeformat"): "%x %I:%M %p",  # time format for the page status field in status bar
    ("main", "recent_time_formats"): "%x %I:%M %p;%m/%d/%y;%d.%m.%y;%d.%m.%Y;%a %Y-%m-%d",
            # semicolon-separated list of recently used time formats
    ("main", "single_process"): "True", # Ensure that only a single process runs per user
    ("main", "menu_accels_kbdTranslate"): "False", # Translate menu accelerators to match keyboard layout
            # this is only necessary for special layouts where ctrl-level uses fundamentally different layout
            # than base and shift level
    ("main", "zombieCheck"): "True", # Check for already running processes? Only active if "single_process" is True
    ("main", "cpu_affinity"): "-1", # Assign process to a single CPU? -1: Use CPU affinity on startup; greater numbers denote a particular CPU

    ("main", "tempHandling_preferMemory"): "False", # Prefer to store temporary data in memory where this is possible?
    ("main", "tempHandling_tempMode"): "system", # Mode for storing of temporary data.
            # system: use system default temp dir; config: use config subdirectory; given: use directory given
            # in option "sqlite_tempDir"; (( auto: use "config" if configuration directory is equal installation dir.,
            # use "system" otherwise ))
    ("main", "tempHandling_tempDir"): "", # Path to directory for temporary files. Only valid if
            # "tempHandling_tempMode" is set to "given".
    ("main", "wikiPathes_relative"): "False", # If True, pathes to last recently used wikis
            # are stored relative to application dir.
    ("main", "openWikiWordDialog_sortOrder"): "0", # Sort order in "Open Wiki Word" dialog
            # 0:Alphabetically; 1:By last visit, newest first; 2:By last visit, oldest first; 3:Alphabetically reverse

    ("main", "collation_order"): "Default", # Set collation order, Default: system default order, C: ASCII byte value
    ("main", "collation_uppercaseFirst"): "False" # Sort uppercase first (ABCabc) or normal inorder (AaBbCc)

    }



WIKIDEFAULTS = {
    ("wiki_db", "data_dir"): "data",
    ("wiki_db", "db_filename"): "", # Name of database (overview databases without page data for "original ..." types,
            # full database for "compact sqlite")
            # If name is empty, defaults are used (original gadfly: "wikidb", original sqlite: "wikiovw.sli",
            # compact sqlite: "wiki.sli")

    ("main", "wiki_name"): None,
    ("main", "wiki_wikiLanguage"): "wikidpad_default_2_0", # Internal name of wiki language of the wiki
    ("main", "last_wiki_word"): None, # Show this wiki word as leftmost wiki word on startup if first_wiki_word is empty
    ("main", "tree_last_root_wiki_word"): None, # Last root word of wiki tree
    ("main", "tree_expandedNodes_rememberDuration"): "2", # How long should open nodes in tree be remembered?
            # 0: Not at all; 1: During session; 2: Between sessions in wiki config file
    ("main", "indexSearch_enabled"): "False", # should the index search be enabled?
    ("main", "indexSearch_formatNo"): "1", # internal: Number of format of search index (only valid if index enabled)
            # if it doesn't match format number of this WikidPad version, index rebuild is needed
    ("main", "tabs_maxCharacters"): "0", # Maximum number of characters to show on a tab (0: inifinite)
    ("main", "template_pageNamesRE"): "^template/",  # Regular expression pattern for pages which should be seen as templates
            # Especially they will be listed in text editor context menu on new pages

    ("main", "trashcan_maxNoOfBags"): "200",   # Maximum number of trashbags. If more are present
            # oldest are removed
    ("main", "trashcan_askOnDelete"): "True",   # When deleting an element ask before it is
            # put to trashbag
    ("main", "trashcan_storageLocation"): "0",  # Where to store trashcan data? 0: Intern in database;
            # 1: extern in files (not supported for Compact Sqlite DB)

    ("main", "first_wiki_word"): "", # Start with a special wiki word (If empty, use last word(s))

    ("main", "wiki_onOpen_rebuild"): "0", # Rebuild wiki when opening it. 0: No; 1: Only update ext. modified files
            # 2: Fully; Values must match CmdLineAction.REBUILD_* constants
    ("main", "wiki_onOpen_tabsSubCtrl"): "", #  Subctrl to set all tabs on open. Normally "textedit" or "preview".
            # If empty the content of config. entry "wiki_lastTabsSubCtrls" is used


    ("main", "tree_expandedNodes_descriptorPathes_main"): "", # ";"-delimited sequence of node descriptor pathes of expanded nodes in tree.
            # Descriptors of a path are delimited by ','. This config. entry applies to main tree
    ("main", "tree_expandedNodes_descriptorPathes_views"): "", # Same as above but applies to "Views" tree if present

    ("main", "tree_force_scratchpad_visibility"): "True",  # Always show scratchpad below wiki root even
            # if it is not a child of it

    ("main", "further_wiki_words"): "", # Semicolon separated list of further wiki words to show in addit. tabs
            # after last wiki word

    ("main", "wiki_lastTabsSubCtrls"): "", # Semicolon separated list of the subcontrols active in each presenter, normally "textedit" or "preview"
    ("main", "wiki_lastActiveTabNo"): "-1", # Number of the tab which was last active. Non-wikiwords are ignored
            # for this index
    ("main", "wiki_mainArea_auiPerspective"): "", # AUI perspective data for the main area panel.
            # If this setting is not empty it overrides "wiki_lastTabsSubCtrls", "wiki_lastActiveTabNo",
            # "last_wiki_word", "further_wiki_words" for 2.3beta10 and later

    ("main", "wiki_database_type"): "",  # Type of database "original_gadfly" for WikidPad,
                                         # "compact_sqlite" for WikidPadCompact
                                         # or "original_sqlite"
#     ("main", "footnotes_as_wikiwords"): "False",  # Interpret footnotes (e.g. [42]) as wiki words?
    ("main", "db_pagefile_suffix"): ".wiki",  # Suffix of the page files for "Original ..."
                                             # db types
    ("main", "export_default_dir"): "",  # Default directory for exports, u"" means fill in last active directory

    ("main", "wiki_readOnly"): "False",   # Should wiki be read only?

    ("main", "log_window_autoshow"): "Gray", # Automatically show log window if messages added? "Gray" means to look at
            # global configuration for same setting

    ("main", "wikiPageFiles_asciiOnly"): "False", # Use only ASCII characters in filenames of wiki page files.
    ("main", "wikiPageFiles_maxNameLength"): "120", # Maximum length of overall name of a wiki page file
    ("main", "wikiPageFiles_gracefulOutsideAddAndRemove"): "True",   # Handle missing wiki page files gracefully and try
            # to find existing files even if they are not in database.

    ("main", "wikiPageFiles_writeFileMode"): "0", # How wiki page files are modified on saving?
            # 0: Safe: create temp file, delete target file, rename temp to target
            # 1: Just overwrite in place (useful if files are hardlinked).

    ("main", "headingsAsAliases_depth"): "0",  # Maximum heading depth for which aliases should be generated for
            # each heading up to and including this depth.

    ("main", "versioning_storageLocation"): "0",  # Where to store versioning data? 0: Intern in database;
            # 1: extern in files (not supported for Compact Sqlite DB)

    ("main", "versioning_completeSteps"): "10",  # How many versions before next version is saved completely
            # instead of reverse differential? 0: Always revdiff, 1: Always complete, 2: Every second v. is complete ...

    ("main", "tabHistory_maxEntries"): "25",  # Maximum number of entries in the history for each tab
    ("main", "wikiWideHistory_maxEntries"): "100",  # Maximum number of entries in the wiki-wide history


    # For file storage (esp. identity check)
    ("main", "fileStorage_identity_modDateMustMatch"): "False",  # Modification date must match for file to be identical
    ("main", "fileStorage_identity_filenameMustMatch"): "False",  # Filename must match for file
    ("main", "fileStorage_identity_modDateIsEnough"): "False",
            # Same modification date is enough to claim files identical (no content compare)

    ("main", "fileSignature_timeCoarsening"): "0", # Coarsening of time stamp in file signature blocks (helpful when
            # transferring wikis between different file systems)

    ("main", "editor_text_mode"): "False",  # force the editor to write platform dependent files to disk
            # (line endings as CR/LF, LF or CR)

    ("main", "wikiPageTitlePrefix"): "",   # Prefix for main title of new pages.
            # The prefix would be put before the formatted heading title (formatted according to heading level from next option)
    ("main", "wikiPageTitle_headingLevel"): "0",   # Heading level for main title of new pages.
            # 0 means to not modify title. The default "0" is intended for existing wikis with a "wikiPageTitlePrefix"
            # set. For newly created wikis this option is set to "2
    ("main", "wikiPageTitle_creationMode"): "1",   # How to create title from name of a new wiki word:
            # 0: Use wiki word as title as it is ("NewWikiWord" -> "NewWikiWord")
            # 1: Add spaces before uppercase letter ("NewWikiWord" -> "New Wiki Word")
            # 2: No title at all
    ("main", "wikiPageTitle_fromLinkTitle"): "False",   # If clicking on a title link, e.g. [wiki word|interesting title]
            # of a non-existing page use that title as title of the page.

    ("main", "wiki_icon"): "",   # Name of the wiki icon. Empty if default icon should be used

    ("main", "hotKey_showHide_byWiki"): ""   # System-wide hotkey to show/hide program. It is described
            # in the usual shortcut syntax e.g. "Ctrl-Alt-A".
            # This key is bound to the wiki. Another key above can be bound to the whole app
    }



# If the fallthrough value is set in the wiki-bound config. then
# the global config. value is used instead
WIKIFALLTHROUGH ={
    ("main", "log_window_autoshow"): "Gray"

    }



# Maps configuration setting "mouse_middleButton_withoutCtrl" number to a
# tabMode number for WikiTxtCtrl._activateLink or WikiHtmlView._activateLink
MIDDLE_MOUSE_CONFIG_TO_TABMODE = {
                                    0: 2, # New tab in foreground
                                    1: 3, # New tab in background
                                    2: 0, # Same Tab
                                    3: 6, # New Window (in foreground)
                                 }



# def createCombinedConfiguration():
#     return CombinedConfiguration(createGlobalConfiguration(),
#             createWikiConfiguration())
#
#
# def createWikiConfiguration():
#     return SingleConfiguration(WIKIDEFAULTS)
#
#
# def createGlobalConfiguration():
#     return SingleConfiguration(GLOBALDEFAULTS)


