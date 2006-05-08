import ConfigParser
# import os
# from os.path import *

import codecs

from wxPython.wx import wxPlatformInfo

# Positioned here to avoid circular dependency with StringOps
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

from StringOps import utf8Enc, utf8Dec, mbcsDec, strToBool

Error = ConfigParser.Error

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


class Configuration:
    """
    Manages global and wiki specific configuration options.
    Mainly wraps the ConfigParser
    """
    
    def __init__(self, globaldef, wikidef):
        """
        globaldef -- default values for the global configuration file,
                dictionary of type {(<section>, <option>): value}
        wikidef -- Same for wiki configuration file
        """
        self.globalConfig = None
        self.wikiConfig = None
        
        self.globalDefaults = globaldef
        self.wikiDefaults = wikidef

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
                self.wikiDefaults.has_key((section, option)):
            if self.wikiConfig.has_option(section, option):
                result = self.wikiConfig.get(section, option)
            else:
                result = self.wikiDefaults[(section, option)]

        elif self.globalDefaults.has_key((section, option)):
            if self.globalConfig.has_option(section, option):
                result = self.globalConfig.get(section, option)
            else:
                result = self.globalDefaults[(section, option)]
        else:
            raise Exception, "Unknown option" # TODO Better exception

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


    def set(self, section, option, value):
        if self.wikiConfig and \
                self.wikiDefaults.has_key((section, option)):
            _setValue(section, option, value, self.wikiConfig)
        elif self.globalDefaults.has_key((section, option)):
            _setValue(section, option, value, self.globalConfig)
        else:
            raise Exception, "Unknown option" # TODO Better exception


    def fillGlobalWithDefaults(self):
        _fillWithDefaults(self.globalConfig, self.globalDefaults)


    def fillWikiWithDefaults(self):
        _fillWithDefaults(self.wikiConfig, self.wikiDefaults)


    def setWikiConfig(self, config, fn):
        self.wikiConfig = config
        self.wikiConfigFilename = fn

    def getWikiConfig(self):
        return self.wikiConfig

    def getWikiConfigFilename(self):
        return self.wikiConfigFilename

    def setGlobalConfig(self, config, fn):
        self.globalConfig = config
        self.globalConfigFilename = fn

    def getGlobalConfig(self):
        return self.globalConfig

    def getGlobalConfigFilename(self):
        return self.globalConfigFilename


    def loadWikiConfig(self, fn):
        if fn is None:
            self.setWikiConfig(None, None)
            return

        config = ConfigParser.ConfigParser()
        config.read(fn)
        self.setWikiConfig(config, fn)


    def createEmptyWikiConfig(self, fn):
        config = ConfigParser.ConfigParser()
        self.setWikiConfig(config, fn)
        
        
    def loadGlobalConfig(self, fn):
        config = ConfigParser.ConfigParser()
        config.read(fn)
        self.setGlobalConfig(config, fn)


    def createEmptyGlobalConfig(self, fn):
        config = ConfigParser.ConfigParser()
        self.setGlobalConfig(config, fn)

        
    def save(self):
        """
        Save all configurations
        """
        if self.wikiConfig:
            configFile = open(self.wikiConfigFilename, 'w')
            try:
                self.wikiConfig.write(configFile)
            finally:
                configFile.close()

        configFile = open(self.globalConfigFilename, 'w')
        try:
            self.globalConfig.write(configFile)
        finally:
            configFile.close()
            
    def isUnicode(unself):
        """
        Return if GUI is in unicode mode
        """
        return isUnicode()



GLOBALDEFAULTS = {
    ("main", "wiki_history"): None,   # Should be overwritten with concrete value
    ("main", "last_wiki"): "",   # Same
    ("main", "size_x"): None,   # Same
    ("main", "size_y"): None,   # Same
    
    ("main", "pos_x"): None,   # Should be overwritten with concrete value
    ("main", "pos_y"): None,   # Same
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
    ("main", "auto_bullets"): "True",  # Show bullet/number in newline if current line has bullet
    ("main", "auto_indent"): "True",
    ("main", "clipboardCatcher_suffix"): ur"\n",  # Suffix to append after each caught clipboard snippet
    
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

    ("main", "html_body_link"): "",  # for HTML preview/export, color for link or "" for default
    ("main", "html_body_alink"): "",  # for HTML preview/export, color for active link or "" for default
    ("main", "html_body_vlink"): "",  # for HTML preview/export, color for visited link or "" for default
    ("main", "html_body_text"): "",  # for HTML preview/export, color for text or "" for default
    ("main", "html_body_bgcolor"): "",  # for HTML preview/export, color for background or "" for default
    ("main", "html_body_background"): "",  # for HTML preview/export, URL for background image or "" for none


    ("main", "sync_highlight_byte_limit"): "5120",  # Size limit when to start asyn. highlighting in editor
    ("main", "async_highlight_delay"): "0.2",  # Delay after keypress before starting async. highlighting
    ("main", "editor_plaintext_color"): "", # Color of plain text (and non-exist. wikiwords) in editor
    ("main", "editor_link_color"): "", # Color of links (URL and wikiwords)
    ("main", "editor_attribute_color"): "", # Color of attributes (=properties) and scripts
    ("main", "editor_bg_color"): "",  # Background color of the editor

    # For wiki-wide search
    ("main", "search_wiki_context_before"): "0", # No. of context characters before
    ("main", "search_wiki_context_after"): "0",  # and after a found pattern
    ("main", "search_wiki_count_occurrences"): "False", # Show for each page the number of found matches

    ("main", "print_margins"): "0,0,0,0", # Left, upper, right, lower page margins on printing
    ("main", "print_plaintext_font"): "", # Font description for printing in plain text mode
    ("main", "print_plaintext_wpseparator"): "\\n\\n\\n\\n", # How to separate wikiword pages (uses re escaping)

    ("main", "windowmode"): "0",
    ("main", "frame_stayOnTop"): "False",  # Should frame stay on top of all other windows?
    ("main", "lowresources"): "0",   # The value must be a number, not a truth value!
    ("main", "showontray"): "0",
    ("main", "strftime"): u"%x %I:%M %p",  # time format when inserting time in a page
    ("main", "pagestatus_timeformat"): u"%x %I:%M %p",  # time format for the page status field in status bar
    ("main", "recent_time_formats"): u"%x %I:%M %p;%m/%d/%y;%d.%m.%y;%d.%m.%Y;%a %Y-%m-%d",
             # semicolon separated list of recently used time formats
    ("main", "script_security_level"): "0"  # Allow the use of scripts and
            # import_scripts property? 0: No scripts at all; 1: No import_scripts;
            # 2: allow local import_scripts; 3: allow also global.import_scripts
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
    ("main", "fileStorage_identity_modDateIsEnough"): "False"
            # Same modification date is enough to claim files identical (no content compare)

    }



def createConfiguration():
    return Configuration(GLOBALDEFAULTS, WIKIDEFAULTS)



