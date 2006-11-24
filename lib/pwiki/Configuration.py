import ConfigParser
import os, traceback
# from os.path import *

import codecs

from wxPython.wx import wxPlatformInfo, wxGetOsVersion, wxGetApp

wxWINDOWS_NT = 18   # For wxGetOsVersion() 
wxWIN95 = 20   # For wxGetOsVersion(), this includes also Win 98 and ME


from MiscEvent import MiscEventSourceMixin


# Placed here to avoid circular dependency with StringOps
def isUnicode():
    """
    Return if GUI is in unicode mode
    """
    return wxPlatformInfo[2] == "unicode"

def isOSX():
    """
    Return if working on Mac OSX
    """
    return '__WXMAC__' in wxPlatformInfo
    
def isLinux():
    """
    Return if working on Linux system
    """
    try:
        return os.uname()[0] == "Linux"
    except AttributeError:
        return False


_ISWIN9x = wxGetOsVersion()[0] == wxWIN95

def isWin9x():
    """
    Returns True if OS is WIndows 95/98/ME
    """
    return _ISWIN9x






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
        assert 0  # abstract    

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

    def __init__(self, configdef):
        """
        configdef -- Dictionary with defaults for configuration file
        """
        MiscEventSourceMixin.__init__(self)
        
        self.configParserObject = None
        self.configPath = None
        
        self.configDefaults = configdef

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
            raise UnknownOptionException, "Unknown option %s:%s" % (section, option)

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


    def isOptionAllowed(self, section, option):
        """
        The function test if an option is valid.
        Only options can be set/retrieved which have an entry in the
        defaults and if the configParserObject is valid.
        """
        return self.configParserObject is not None and \
                self.configDefaults.has_key((section, option))


    def set(self, section, option, value):
        if type(section) is unicode:
            section = utf8Enc(section)[0]

        if type(option) is unicode:
            option = utf8Enc(option)[0]
            
        if self.isOptionAllowed(section, option):
            _setValue(section, option, value, self.configParserObject)
        else:
            raise UnknownOptionException, "Unknown option"


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
        config.read(fn)
        self.setConfigParserObject(config, fn)


    def createEmptyConfig(self, fn):
        config = ConfigParser.ConfigParser()
        self.setConfigParserObject(config, fn)


    def save(self):
        """
        Save all configurations
        """
        if self.configParserObject:
            configFile = open(self.configPath, 'w')
            try:
                self.configParserObject.write(configFile)
            finally:
                configFile.close()
    
    def informChanged(self):
        """
        This should be called after configuration was changed to let
        the object send out an event.
        The set method does not send events automatically to prevent
        the creation of many events (one per each set call) instead
        of one at the end of changes
        """
        self.fireMiscEventKeys(("configuration changed",))



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

        if self.wikiConfig is not None and \
                self.wikiConfig.isOptionAllowed(section, option):
            result = self.wikiConfig.get(section, option, default)
        elif self.globalConfig is not None and \
                self.globalConfig.isOptionAllowed(section, option):
            result = self.globalConfig.get(section, option, default)
        else:
            raise UnknownOptionException, "Unknown option %s:%s" % (section, option)

        if result is None:
            return default

        return result
        
        
#     def getint(self, section, option, default=None):
#         result = self.get(section, option)
#         if result is None:
#             return default
#         
#         try:
#             return int(result)
#         except ValueError:
#             # Can't convert result string to integer
#             return default
# 
# 
#     def getfloat(self, section, option, default=None):
#         result = self.get(section, option)
#         if result is None:
#             return default
#         
#         try:
#             return float(result)
#         except ValueError:
#             # Can't convert result string to float
#             return default
# 
# 
#     def getboolean(self, section, option, default=None):
#         result = self.get(section, option)
#         if result is None:
#             return default
#         
#         return strToBool(result, False)


    def set(self, section, option, value):
        if type(section) is unicode:
            section = utf8Enc(section)[0]

        if type(option) is unicode:
            option = utf8Enc(option)[0]

        if self.wikiConfig is not None and \
                self.wikiConfig.isOptionAllowed(section, option):
            self.wikiConfig.set(section, option, value)
        elif self.globalConfig is not None and \
                self.globalConfig.isOptionAllowed(section, option):
            self.globalConfig.set(section, option, value)
        else:
            raise UnknownOptionException, "Unknown option %s:%s" % (section, option)


    def fillGlobalWithDefaults(self):
        self.globalConfig.fillWithDefaults()


    def fillWikiWithDefaults(self):
        self.wikiConfig.fillWithDefaults()


#     def setWikiConfigParserObject(self, config, fn):
#         self.wikiConfig.setConfigParserObject(config, fn)
# 
#     def getWikiConfigParserObject(self):
#         return self.wikiConfig.getConfigParserObject()
# 
#     def getWikiConfigFilename(self):
#         return self.wikiConfig.getConfigFilename()


#     def setGlobalConfigParserObject(self, config, fn):
#         self.globalConfig.setConfigParserObject(config, fn)
# 
#     def getGlobalConfigParserObject(self):
#         return self.globalConfig.getConfigParserObject()
# 
#     def getGlobalConfigFilename(self):
#         return self.globalConfig.getConfigFilename()

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


    def save(self):
        """
        Save all configurations
        """
        if self.globalConfig is not None:
            self.globalConfig.save()

        try:
            if self.wikiConfig is not None:
                self.wikiConfig.save()
        except:
            traceback.print_exc()


    def informChanged(self):
        """
        This should be called after configuration was changed. It is called
        for its SingleConfiguration objects in turn to let them send events
        """
        if self.globalConfig is not None:
            self.globalConfig.informChanged()

        if self.wikiConfig is not None:
            self.wikiConfig.informChanged()



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
    ("main", "log_window_sashPos"): "1",  # Real splitter pos
    ("main", "log_window_effectiveSashPos"): "120",  # Splitter pos when calling showEffWindow
    ("main", "toolbar_show"): "True",  # Show the toolbar?
    ("main", "zoom"): '0',  # Zoom factor for editor
    ("main", "preview_zoom"): '0',  # Zoom factor for preview
    ("main", "last_active_dir"): None,   # Should be overwritten with concrete value
    ## ("main", "font"): "Courier New",
    ("main", "font"): None,
    ("main", "wrap_mode"): "True",
    ("main", "indentation_guides"): "True",
    ("main", "auto_bullets"): "True",  # Show bullet/number after newline if current line has bullet
    ("main", "auto_indent"): "True",
    ("main", "show_lineNumbers"): "False", 
    ("main", "clipboardCatcher_suffix"): ur"\n",  # Suffix to append after each caught clipboard snippet
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

    ("main", "auto_save"): "True",  # Boolean field, if auto save should be active
    ("main", "auto_save_delay_key_pressed"): "3",  # Seconds to wait after last key pressed and ...
    ("main", "auto_save_delay_dirty"): "15",  # secs. to wait after page became dirty before auto save
     
    ("main", "hideundefined"): "False", # hide undefined wikiwords in tree
    ("main", "tree_auto_follow"): "True", # The tree selection follows when opening a wiki word
    ("main", "tree_update_after_save"): "True", # The tree is updated after a save
    ("main", "tree_no_cycles"): "False", # Cycles in tree like NodeA -> NodeB -> NodeA are not shown

    ("main", "process_autogenerated_areas"): "False", # process auto-generated areas ?

    ("main", "new_window_on_follow_wiki_url"): "1", # Open new window when following a "wiki:" URL 0:No, 1:Yes, new process
    ("main", "start_browser_after_export"): "True",
    ("main", "facename_html_preview"): "", # Facename(s) for the internal HTML preview
    ("main", "html_preview_proppattern"): "",  # RE pattern for properties in HTML preview
    ("main", "html_preview_proppattern_is_excluding"): "False", # Should these pattern be excluded instead of included?
    ("main", "html_export_proppattern"): "",  # Same for HTML exporting
    ("main", "html_export_proppattern_is_excluding"): "False",  # Same for HTML exporting
    ("main", "html_preview_pics_as_links"): "False",  # Show only links to pictures in HTML preview
    ("main", "html_export_pics_as_links"): "False",  # Same for HTML exporting
    ("main", "export_table_of_contents"): "0",  # Show table of contents when exporting
            # 0:None, 1:formatted as tree, 2:as list

    ("main", "html_body_link"): "",  # for HTML preview/export, color for link or "" for default
    ("main", "html_body_alink"): "",  # for HTML preview/export, color for active link or "" for default
    ("main", "html_body_vlink"): "",  # for HTML preview/export, color for visited link or "" for default
    ("main", "html_body_text"): "",  # for HTML preview/export, color for text or "" for default
    ("main", "html_body_bgcolor"): "",  # for HTML preview/export, color for background or "" for default
    ("main", "html_body_background"): "",  # for HTML preview/export, URL for background image or "" for none


    ("main", "editor_plaintext_color"): "", # Color of plain text (and non-exist. wikiwords) in editor
    ("main", "editor_link_color"): "", # Color of links (URL and wikiwords)
    ("main", "editor_attribute_color"): "", # Color of attributes (=properties) and scripts
    ("main", "editor_bg_color"): "",  # Background color of the editor
    ("main", "sync_highlight_byte_limit"): "5120",  # Size limit when to start asyn. highlighting in editor
    ("main", "async_highlight_delay"): "0.2",  # Delay after keypress before starting async. highlighting
    ("main", "editor_autoUnbullets"): "True",  # When pressing return on line with lonely bullet, remove bullet?


    # For wiki-wide search
    ("main", "search_wiki_context_before"): "20", # No. of context characters before
    ("main", "search_wiki_context_after"): "30",  # and after a found pattern
    ("main", "search_wiki_count_occurrences"): "True", # Show for each page the number of found matches
    ("main", "fastSearch_sizeX"): "200",  # Size of the fastsearch popup frame
    ("main", "fastSearch_sizeY"): "400",

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
             # semicolon separated list of recently used time formats
    ("main", "script_security_level"): "0",  # Allow the use of scripts and
            # import_scripts property? 0: No scripts at all; 1: No import_scripts;
            # 2: allow local import_scripts; 3: allow also global.import_scripts
    ("main", "insertions_allow_eval"): "False",  # Evaluate :eval: and possible other script insertions?
    ("main", "single_process"): "False", # Ensure that only a single process runs per user  
    ("main", "collation_order"): "Default", # Set collation order, Default: system default order, C: ASCII byte value
    ("main", "collation_uppercaseFirst"): "False" # Sort uppercase first (ABCabc) or normal inside (AaBbCc)

    }


WIKIDEFAULTS = {
    ("wiki_db", "data_dir"): u"data",
    ("main", "wiki_name"): None,
    ("main", "last_wiki_word"): None,
    ("main", "first_wiki_word"): "", # Start with a special wiki word (If empty, use last word)
    ("main", "wiki_database_type"): u"",  # Type of database "original_gadfly" for WikidPad,
                                         # "compact_sqlite" for WikidPadCompact
                                         # or "original_sqlite"
    ("main", "footnotes_as_wikiwords"): "False",  # Interpret footnotes (e.g. [42]) as wiki words?
    ("main", "db_pagefile_suffix"): ".wiki",  # Suffix of the page files for "Original ..."
                                             # db types

    # For file storage (esp. identity check)
    ("main", "fileStorage_identity_modDateMustMatch"): "False",  # Modification date must match for file to be identical
    ("main", "fileStorage_identity_filenameMustMatch"): "False",  # Filename must match for file 
    ("main", "fileStorage_identity_modDateIsEnough"): "False",
            # Same modification date is enough to claim files identical (no content compare)

    ("main", "wikiPageTitlePrefix"): "++"   # Prefix for main title of new pages
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


