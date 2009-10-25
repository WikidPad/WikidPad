import ConfigParser
import os, traceback
import cStringIO as StringIO

# from os.path import *

import codecs
import wx

import MainApp
import Utilities

# Bug workaround: In wxPython 2.6 these constants weren't defined
#    in 2.8 they are defined under a different name and with different values

try:
    wxWINDOWS_NT = wx.OS_WINDOWS_NT
except AttributeError:
    wxWINDOWS_NT = 18   # For wx.GetOsVersion()
    
try:
    wxWIN95 = wx.OS_WINDOWS_9X
except AttributeError:
    wxWIN95 = 20   # For wx.GetOsVersion(), this includes also Win 98 and ME


from MiscEvent import MiscEventSourceMixin
from WikiExceptions import *


# Placed here to avoid circular dependency with StringOps
def isUnicode():
    """
    Return if GUI is in unicode mode
    """
    return wx.PlatformInfo[2] == "unicode"

def isOSX():
    """
    Return if running on Mac OSX
    """
    return '__WXMAC__' in wx.PlatformInfo
    
def isLinux():
    """
    Return if running on Linux system
    """
    try:
        return os.uname()[0] == "Linux"
    except AttributeError:
        return False


_ISWIN9x = wx.GetOsVersion()[0] == wxWIN95
_ISWINNT = wx.GetOsVersion()[0] == wxWINDOWS_NT

def isWin9x():
    """
    Returns True if OS is Windows 95/98/ME
    """
    return _ISWIN9x

def isWinNT():
    """
    Returns True if OS is Windows NT/2000/XP...
    """
    return _ISWINNT

def isWindows():
    return _ISWIN9x or _ISWINNT



# from WikiExceptions import *

from StringOps import utf8Enc, utf8Dec, mbcsDec, strToBool

Error = ConfigParser.Error


class UnknownOptionException(Exception): pass



def _setValue(section, option, value, config):
    """
    if value is of type str, it is assumed to be mbcs-coded
    if section or option are of type str, they are assumed to be utf8 coded
        (it is recommended to use only ascii characters for section/option
        names)
    """
    if type(section) is unicode:
        section = utf8Enc(section)[0]

    if type(option) is unicode:
        option = utf8Enc(option)[0]
        
    if type(value) is str:
        value = utf8Enc(mbcsDec(value)[0])[0]
    elif type(value) is unicode:
        value = utf8Enc(value)[0]
    else:
        value = utf8Enc(unicode(value))[0]
        
    if not config.has_section(section):
        config.add_section(section) 
        
    config.set(section, option, value)


def _fillWithDefaults(config, defaults):
    for s, o in defaults.keys():
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

    def isUnicode(unself):
        """
        Return if GUI is in unicode mode
        """
        return isUnicode()



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
        if type(section) is unicode:
            section = utf8Enc(section)[0]

        if type(option) is unicode:
            option = utf8Enc(option)[0]
            
        result = None

        if self.isOptionAllowed(section, option):
            if self.configParserObject.has_option(section, option):
                result = self.configParserObject.get(section, option)
            else:
                result = self.configDefaults[(section, option)]
        else:
            raise UnknownOptionException, _(u"Unknown option %s:%s") % (section, option)

        if result is None:
            return default

        try:
            result = utf8Dec(result)[0]
        except UnicodeError:
            # Result is not Utf-8 -> try mbcs
            try:
                result = mbcsDec(result)[0]
            except UnicodeError:
                # Result can't be converted
                result = default

        return result
        
    def setWriteAccessDenied(self, flag):
        self.writeAccessDenied = flag
        
    def getWriteAccessDenied(self):
        return self.writeAccessDenied
        
    def isReadOnlyEffect(self):
        return self.writeAccessDenied


    def isOptionAllowed(self, section, option):
        """
        The function test if an option is valid.
        Only options can be set/retrieved which have an entry in the
        defaults and if the configParserObject is valid.
        """
        return self.configParserObject is not None and \
                self.configDefaults.has_key((section, option))

    # TODO Allow in read-only mode?
    def set(self, section, option, value):
        if type(section) is unicode:
            section = utf8Enc(section)[0]

        if type(option) is unicode:
            option = utf8Enc(option)[0]
            
        if self.isOptionAllowed(section, option):
            _setValue(section, option, value, self.configParserObject)
        else:
            raise UnknownOptionException, _(u"Unknown option %s:%s") % (section, option)


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

        config = ConfigParser.ConfigParser()
        readFiles = config.read(fn)
        if len(readFiles) > 0:
            self.setConfigParserObject(config, fn)
        else:
            raise MissingConfigurationFileException(_(u"Config file not found"))


    def createEmptyConfig(self, fn):
        config = ConfigParser.ConfigParser()
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
            sfile = StringIO.StringIO()
            self.configParserObject.write(sfile)
            configFile = open(self.configPath, 'w')
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
        if type(section) is unicode:
            section = utf8Enc(section)[0]

        if type(option) is unicode:
            option = utf8Enc(option)[0]
            
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
                if not ftDict.has_key((section, option)) or \
                        ftDict[(section, option)] != result:
                    checkGlobal = False
                
            # TODO more elegantly
            elif WIKIDEFAULTS.has_key((section, option)):
                result = default
                checkGlobal = False
            elif not checkGlobal:
                raise UnknownOptionException, _(u"Unknown option %s:%s") % (section, option)

        if checkGlobal:
            if self.globalConfig is not None:
                result = self.globalConfig.get(section, option, default)
            else:
                raise UnknownOptionException, _(u"Unknown option %s:%s") % (section, option)


#         if self.wikiConfig is not None and \
#                 self.wikiConfig.isOptionAllowed(section, option):
#             result = self.wikiConfig.get(section, option, default)
#         # TODO more elegantly
#         elif WIKIDEFAULTS.has_key((section, option)):
#             result = default
#         elif self.globalConfig is not None and \
#                 self.globalConfig.isOptionAllowed(section, option):
#             result = self.globalConfig.get(section, option, default)
#         else:
#             raise UnknownOptionException, _(u"Unknown option %s:%s") % (section, option)

        if result is None:
            return default

        return result
        
        

    def set(self, section, option, value):
        if type(section) is unicode:
            section = utf8Enc(section)[0]

        if type(option) is unicode:
            option = utf8Enc(option)[0]
            
        if option.startswith("option/wiki/"):
            option = option[12:]
            self.wikiConfig.set(section, option, value)
        elif option.startswith("option/user/"):
            option = option[12:]
            self.globalConfig.set(section, option, value)
        elif self.wikiConfig is not None and \
                self.wikiConfig.getFallthroughDict().has_key((section, option)):
            raise UnknownOptionException, _(u"Ambiguos option set %s:%s") % (section, option)
        else:
            if self.wikiConfig is not None and \
                    self.wikiConfig.isOptionAllowed(section, option):
                self.wikiConfig.set(section, option, value)
            elif self.globalConfig is not None:
                self.globalConfig.set(section, option, value)
            else:
                raise UnknownOptionException, _(u"Unknown option %s:%s") % (section, option)


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
    ("main", "last_wiki"): "",   # Same
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

    ("main", "toolbar_show"): "True",  # Show the toolbar?
    ("main", "zoom"): '0',  # Zoom factor for editor
    ("main", "preview_zoom"): '0',  # Zoom factor for preview
    ("main", "last_active_dir"): None,   # Should be overwritten with concrete value
    ## ("main", "font"): "Courier New",
    ("main", "gui_language"): u"",   # Language (as locale code) to use in GUI. Empty string means system default language
    ("main", "recentWikisList_length"): u"5",   # Length of recent wikis list
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
    ("main", "wikiWord_rename_wikiLinks"): "2", # When renaming wiki word, should it try to rename links to the word, too?
            # 0:No, 1:Yes, 2:Ask for each renaming
    ("main", "mainTree_position"): "0",  # Mode where to place the main tree,
            # 0:Left, 1:Right, 2:Above, 3:Below
    ("main", "viewsTree_position"): "0",  # Mode how to show the "Views" tree relative to main tree,
            # 0: Not at all, 1:Above, 2:Below, 3:Left, 4:Right
    ("main", "windowLayout"): "name:main area panel;"\
            "layout relation:left&layout relative to:main area panel&name:maintree&"\
                "layout sash position:170&layout sash effective position:170;"\
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


    ("main", "hotKey_showHide_byApp"): "", # System-wide hotkey to show/hide program. It is described
            # in the usual shortcut syntax e.g. "Ctrl-Alt-A".
            # This key is bound to the application. A second key can be bound to a particular
            # wiki
    ("main", "hotKey_showHide_byApp_isActive"): "True", # Separate switch to deactivate hotkey
            # without deleting the hotkey setting itself
            
    ("main", "wikiOpenNew_defaultDir"): u"",   # Default directory to show when opening
            # or creating a wiki. If entry is empty, a built-in default is used.


    ("main", "wikiLockFile_ignore"): u"False",  # Ignore the lock file created by another instance
            # when opening a wiki?
    ("main", "wikiLockFile_create"): u"True",  # Create a lock file when opening a wiki?

    ("main", "auto_save"): "True",  # Boolean field, if auto save should be active
    ("main", "auto_save_delay_key_pressed"): "5",  # Seconds to wait after last key pressed and ...
    ("main", "auto_save_delay_dirty"): "60",  # secs. to wait after page became dirty before auto save
     
    ("main", "hideundefined"): "False", # hide undefined wikiwords in tree
    ("main", "tree_auto_follow"): "True", # The tree selection follows when opening a wiki word
    ("main", "tree_update_after_save"): "True", # The tree is updated after a save
    ("main", "tree_no_cycles"): "False", # Cycles in tree like NodeA -> NodeB -> NodeA are not shown
    ("main", "tree_autohide"): "False", # Automatically hide tree(s) after something was selected in it.
    ("main", "tree_bg_color"): "",  # Background color of the trees

    # Security options
    ("main", "process_autogenerated_areas"): "False", # process auto-generated areas ?
    ("main", "insertions_allow_eval"): "False",  # Evaluate :eval: and possible other script insertions?
#     ("main", "tempFiles_inWikiDir"): "False",  # Store temp. files in wiki dir instead of normal temp dir.?
    ("main", "script_security_level"): "0",  # Allow the use of scripts and
            # import_scripts property? 0: No scripts at all; 1: No import_scripts;
            # 2: allow local import_scripts; 3: allow also global.import_scripts

    # HTML options
    ("main", "new_window_on_follow_wiki_url"): "1", # Open new window when following a "wiki:" URL 0:No, 1:Yes, new process
    ("main", "start_browser_after_export"): "True",
    ("main", "facename_html_preview"): "", # Facename(s) for the internal HTML preview
    ("main", "html_preview_proppattern"): "",  # RE pattern for properties in HTML preview
    ("main", "html_preview_proppattern_is_excluding"): "False", # Should these pattern be excluded instead of included?
    ("main", "html_export_proppattern"): "",  # Same for HTML exporting
    ("main", "html_export_proppattern_is_excluding"): "False",  # Same for HTML exporting
    ("main", "html_preview_pics_as_links"): "False",  # Show only links to pictures in HTML preview
    ("main", "html_export_pics_as_links"): "False",  # Same for HTML exporting
    ("main", "html_preview_renderer"): "0",  # 0: Internal wxWidgets; 1: IE; 2: Mozilla
    ("main", "export_table_of_contents"): "0",  # Show table of contents when exporting
            # 0:None, 1:formatted as tree, 2:as list
    ("main", "html_toc_title"): u"Table of Contents",  # title of table of contents
    ("main", "html_export_singlePage_sepLineCount"): u"10",  # How many empty lines to separate
            # two wiki pages in a single HTML page

    ("main", "html_body_link"): "",  # for HTML preview/export, color for link or "" for default
    ("main", "html_body_alink"): "",  # for HTML preview/export, color for active link or "" for default
    ("main", "html_body_vlink"): "",  # for HTML preview/export, color for visited link or "" for default
    ("main", "html_body_text"): "",  # for HTML preview/export, color for text or "" for default
    ("main", "html_body_bgcolor"): "",  # for HTML preview/export, color for background or "" for default
    ("main", "html_body_background"): "",  # for HTML preview/export, URL for background image or "" for none
    ("main", "html_header_doctype"): 'DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.0 Transitional//EN"',


    # Editor options
    ("main", "sync_highlight_byte_limit"): "5120",  # Size limit when to start asyn. highlighting in editor
    ("main", "async_highlight_delay"): "0.2",  # Delay after keypress before starting async. highlighting
    ("main", "editor_shortHint_delay"): "500",  # Delay in milliseconds until the short hint defined for a wikiword is displayed
            # 0 deactivates short hints
    ("main", "editor_autoUnbullets"): "True",  # When pressing return on line with lonely bullet, remove bullet?
    ("main", "editor_autoComplete_closingBracket"): "False",  # Append closing bracket to suggested wiki words
            # for autocompletion ("[Two" -> "[Two words]" instead of -> "[Two words")
    
    ("main", "editor_sync_byPreviewSelection"): "False", # If True, the selection in preview will be searched in editor
            # for synchronization of both.

    ("main", "editor_imagePaste_filenamePrefix"): "",  # Prefix to put before the filename.
    ("main", "editor_imagePaste_fileType"): "1",  # When pasting images into WikidPad, which file type
            # should be used. 0: Deactivate image-paste; 1: PNG format; 2: JPEG
    ("main", "editor_imagePaste_quality"): "75",  # Which quality should the (JPEG-)image have?
            # 0 zero means very bad, 100 means very good
    ("main", "editor_imagePaste_askOnEachPaste"): "True",  # When pasting image, ask each time for settings?


    # Editor color options
    ("main", "editor_plaintext_color"): "", # Color of plain text (and non-exist. wikiwords) in editor
    ("main", "editor_link_color"): "", # Color of links (URL and wikiwords)
    ("main", "editor_attribute_color"): "", # Color of attributes (=properties) and scripts
    ("main", "editor_bg_color"): "",  # Background color of the editor
    ("main", "editor_selection_fg_color"): "",  # Foreground color of the selection in the editor
    ("main", "editor_selection_bg_color"): "",  # Background color of the selection in the editor
    ("main", "editor_margin_bg_color"): "",  # Background color of margins in the editor except fold margin
    ("main", "editor_caret_color"): "",  # Color of caret in the editor


    # Clipboard catcher (Windows only)
    ("main", "clipboardCatcher_prefix"): ur"",  # Prefix to prepend before each caught clipboard snippet
    ("main", "clipboardCatcher_suffix"): ur"\n",  # Suffix to append after each caught clipboard snippet
    ("main", "clipboardCatcher_filterDouble"): "True",  # If same text shall be inserted twice (or more often)
            # do not react
    ("main", "clipboardCatcher_userNotification"): "0",  # Type of notification when new clipboard snippet is caught, 0: None; 1: Sound
    ("main", "clipboardCatcher_soundFile"): "",  # Filepath of sound to play if notification type is 1. Empty path plays bell


    # File Launcher (for non-Windows OS)
    ("main", "fileLauncher_path"): u"", # Path to an external program taking a path or URL to start appropriate application
            # depending on file type. For Windows, the console command "start" does this.


    # Mouse options
    ("main", "mouse_middleButton_withoutCtrl"): "1", # If middle mouse button is pressed on a link in editor or preview, without
            # Ctrl pressed, should it then open link in  0: a new tab in foreground, 1: new tab background, 2: same tab
    ("main", "mouse_middleButton_withCtrl"): "0", # Same, but if Ctrl is pressed


    ("main", "userEvent_mouse/leftdoubleclick/preview/body"): u"action/none", # How to react when user double-clicks somewhere into body of preview?
            # "action/none": Do nothing; "action/presenter/this/subcontrol/textedit": Switch current subcontrol to textedit mode;
            # "action/presenter/new/foreground/end/page/this/subcontrol/textedit": New tab with same wikiword in edit mode

    ("main", "userEvent_mouse/middleclick/pagetab"): u"action/none",  # How to react on middle click on tab?
            # "action/none": Do nothing; "action/presenter/this/close" close this tab

    ("main", "userEvent_mouse/leftdrop/editor/files"): u"action/editor/this/paste/files/insert/url/absolute",  # How to react on dropping files to editor?
            # "action/none": Do nothing; "action/editor/this/paste/files/insert/url/absolute" insert absolute urls,
            # ".../relative": relative URLs, ".../tostorage": copy to files storage and create relative URL

    ("main", "userEvent_mouse/leftdrop/editor/files/modkeys/shift"): u"action/editor/this/paste/files/insert/url/relative",
            # How to react on dropping files to editor if shift key is pressed?

    ("main", "userEvent_mouse/leftdrop/editor/files/modkeys/ctrl"): u"action/editor/this/paste/files/insert/url/tostorage",
            # How to react on dropping files to editor if ctrl key is pressed?

    # Time view/time line/calendar options
    ("main", "timeView_position"): "0",  # Mode where to place the time view window,
            # 0: Hidden, 1:Left, 2:Right, 3:Above, 4:Below
    ("main", "timeView_dateFormat"): u"%Y %m %d",  # Time format to show and enter dates in the time view,
            # especially in the timeline    
    ("main", "timeView_autohide"): "False", # Automatically hide time view after something was selected in it.
    ("main", "timeView_showWordListOnHovering"): "True", # If True the wordlist of a date is shown when hovering
            # over the entry
    ("main", "timeView_showWordListOnSelect"): "False", # If True the wordlist of a date is shown when 
            # entry is selected
    ("main", "timeline_showEmptyDays"): "True", # Show days for which no wikiword is associated?
    ("main", "timeline_sortDateAscending"): "True", # If True the newer days are downward in the list, otherwise upward


    # Search options
    ("main", "search_wiki_context_before"): "20", # No. of context characters before
    ("main", "search_wiki_context_after"): "30",  # and after a found pattern
    ("main", "search_wiki_count_occurrences"): "True", # Show for each page the number of found matches
    ("main", "fastSearch_sizeX"): "200",  # Size of the fastsearch popup frame
    ("main", "fastSearch_sizeY"): "400",
    ("main", "incSearch_autoOffDelay"): "0", # Secs. of inactivity until stopping incremental
            # search automatically, 0 means no auto. stop

    ("main", "print_margins"): "0,0,0,0", # Left, upper, right, lower page margins on printing
    ("main", "print_plaintext_font"): "", # Font description for printing in plain text mode
    ("main", "print_plaintext_wpseparator"): "\\n\\n\\n\\n", # How to separate wikiword pages (uses re escaping)

    ("main", "windowmode"): "0",
    ("main", "frame_stayOnTop"): "False",  # Should frame stay on top of all other windows?
    ("main", "lowresources"): "0",   # The value must be a number, not a truth value!
    ("main", "showontray"): "0",
    ("main", "minimize_on_closeButton"): "False", # Minimize if the close button ("X") is pressed  
    ("main", "strftime"): u"%x %I:%M %p",  # time format when inserting time in a page
    ("main", "pagestatus_timeformat"): u"%x %I:%M %p",  # time format for the page status field in status bar
    ("main", "recent_time_formats"): u"%x %I:%M %p;%m/%d/%y;%d.%m.%y;%d.%m.%Y;%a %Y-%m-%d",
            # semicolon-separated list of recently used time formats
    ("main", "single_process"): "True", # Ensure that only a single process runs per user  
    ("main", "tempHandling_preferMemory"): "False", # Prefer to store temporary data in memory where this is possible?
    ("main", "tempHandling_tempMode"): u"system", # Mode for storing of temporary data.
            # system: use system default temp dir; config: use config subdirectory; given: use directory given
            # in option "sqlite_tempDir"; (( auto: use "config" if configuration directory is equal installation dir.,
            # use "system" otherwise ))
    ("main", "tempHandling_tempDir"): u"", # Path to directory for temporary files. Only valid if
            # "tempHandling_tempMode" is set to "given".
    ("main", "wikiPathes_relative"): "False", # If True, pathes to last recently used wikis
            # are stored relative to application dir.
    
    ("main", "collation_order"): "Default", # Set collation order, Default: system default order, C: ASCII byte value
    ("main", "collation_uppercaseFirst"): "False" # Sort uppercase first (ABCabc) or normal inorder (AaBbCc)

    }



WIKIDEFAULTS = {
    ("wiki_db", "data_dir"): u"data",
    ("main", "wiki_name"): None,
    ("main", "last_wiki_word"): None, # Show this wiki word as leftmost wiki word on startup if first_wiki_word is empty
    ("main", "tree_last_root_wiki_word"): None, # Last root word of wiki tree
    ("main", "tree_expandedNodes_rememberDuration"): u"2", # How long should open nodes in tree be remembered?
            # 0: Not at all; 1: During session; 2: Between sessions in wiki config file
    ("main", "tree_expandedNodes_descriptorPathes_main"): u"", # ";"-delimited sequence of node descriptor pathes of expanded nodes in tree.
            # Descriptors of a path are delimited by ','. This config. entry applies to main tree
    ("main", "tree_expandedNodes_descriptorPathes_views"): u"", # Same as above but applies to "Views" tree if present

    ("main", "tree_force_scratchpad_visibility"): "True",  # Always show scratchpad below wiki root even
            # if it is not a child of it


    ("main", "further_wiki_words"): u"", # Semicolon separated list of further wiki words to show in addit. tabs
            # after last wiki word
    ("main", "first_wiki_word"): "", # Start with a special wiki word (If empty, use last word)
    ("main", "wiki_database_type"): u"",  # Type of database "original_gadfly" for WikidPad,
                                         # "compact_sqlite" for WikidPadCompact
                                         # or "original_sqlite"
    ("main", "footnotes_as_wikiwords"): "False",  # Interpret footnotes (e.g. [42]) as wiki words?
    ("main", "db_pagefile_suffix"): ".wiki",  # Suffix of the page files for "Original ..."
                                             # db types
    ("main", "export_default_dir"): u"",  # Default directory for exports, u"" means fill in last active directory
    
    ("main", "wiki_readOnly"): "False",   # Should wiki be read only?

    ("main", "log_window_autoshow"): "Gray", # Automatically show log window if messages added?

    # For file storage (esp. identity check)
    ("main", "fileStorage_identity_modDateMustMatch"): "False",  # Modification date must match for file to be identical
    ("main", "fileStorage_identity_filenameMustMatch"): "False",  # Filename must match for file 
    ("main", "fileStorage_identity_modDateIsEnough"): "False",
            # Same modification date is enough to claim files identical (no content compare)

    ("main", "wikiPageTitlePrefix"): "++",   # Prefix for main title of new pages
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


WIKIFALLTHROUGH ={
    ("main", "log_window_autoshow"): "Gray"

    }



# Maps configuration setting "mouse_middleButton_withoutCtrl" number to a 
# tabMode number for WikiTxtCtrl._activateLink or WikiHtmlView._activateLink
MIDDLE_MOUSE_CONFIG_TO_TABMODE = {0: 2, 1: 3, 2: 0}



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


