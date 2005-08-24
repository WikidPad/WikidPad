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
        
        if self.wikiConfig and self.wikiDefaults.has_key((section, option)):
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
    ("main", "zoom"): '0',
    ("main", "last_active_dir"): None,   # Should be overwritten with concrete value
    ## ("main", "font"): "Courier New",
    ("main", "font"): None,
    ("main", "wrap_mode"): "True",
    ("main", "auto_save"): "1",
    ("main", "indentation_guides"): "True",
    ("main", "windowmode"): "0",   # The value must be a number, not a truth value!
    ("main", "lowresources"): "0",
    ("main", "showontray"): "0",
    ("main", "strftime"): u"%x %I:%M %p",  # time format
    ("main", "hideundefined"): "False", # hide undefined wikiwords in tree
    ("main", "process_autogenerated_areas"): "False", # process auto-generated areas ?
    ("main", "start_browser_after_export"): "True"
    }


WIKIDEFAULTS = {
    ("wiki_db", "data_dir"): u"data",
    ("main", "wiki_name"): None,
    ("main", "last_wiki_word"): None
    }



def createConfiguration():
    return Configuration(GLOBALDEFAULTS, WIKIDEFAULTS)



