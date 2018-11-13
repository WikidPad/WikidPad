
import traceback

import wx

from pwiki.OptionsDialog import PluginOptionsPanel

# This is a stub for the actual plugin located in
# "mediaWikiParser/MediaWikiParser.py". The stub ensures that the real plugin is
# only loaded if the language is actually used.


WIKIDPAD_PLUGIN = (("WikiParser", 1),)

WIKI_LANGUAGE_NAME = "mediawiki_1"
WIKI_HR_LANGUAGE_NAME = "MediaWiki 1.0"


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
        from .mediaWikiParser.MediaWikiParser import parserFactory as pf
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
        from .mediaWikiParser.MediaWikiParser import languageHelperFactory as lhf
        _realLanguageHelperFactory = lhf

    return _realLanguageHelperFactory(intLanguageName, debugMode)
