"""
This is a demonstration plugin for constructing a wiki language parser based
on the default parser which doesn't need permanent updates (but maybe from
time to time).

Until now it was only possible to create a copy of the default parser plugin
and modify it in the desired way. This meaned that each change in the default
parser had to be done to the copied parser as well.

For simple changes (like double brackets for links as this plugin
demonstrates) it can be done more comfortable now by giving some
redefinitions of definitions in default parser which are used instead of the
original ones. If other parts of the default parser change an overlay parser
automatically uses these changes without a manual update.

The OverlayParser works by executing the default parser code in some sort of
"guarded" environment. When one of the overlaid identifiers should be set as
global variable, the OverlayParser evaluates the definition from its PAYLOAD
and sets this result instead. This allows to redefine e.g. the URL patterns
to support more URL protocols.

The plugin works for recent 2.2 and 2.1 versions. For final 2.0 it should
work but wasn't tested yet.

This plugin is mainly intended for demonstration purposes. If you want your
own, you should rename it and modify WIKI_LANGUAGE_NAME (internal name of new
wiki language) and WIKI_HR_LANGUAGE_NAME (human readable name) and of course
PAYLOAD.


Reference: http://trac.wikidpad2.webfactional.com/wiki/OverlayParser
"""
import re

WIKIDPAD_PLUGIN = (("WikiParser", 1),)

WIKI_LANGUAGE_NAME = "wikidpad_overlaid_2_0"
WIKI_HR_LANGUAGE_NAME = u"WikidPad overlaid 2.0"


def describeWikiLanguage(ver, app):
    """
    API function for "WikiParser" plugins
    Returns a sequence of tuples describing the supported
    insertion keys. Each tuple has the form

        (intLanguageName, hrLanguageName, parserFactory, parserIsThreadsafe,
        editHelperFactory, editHelperIsThreadsafe)

    Where the items mean:

    intLanguageName -- internal unique name (should be ascii only) to
                       identify wiki language processed by parser

    hrLanguageName -- human readable language name, unistring
                      (TODO: localization)

    parserFactory -- factory function to create parser object(s) fulfilling

    parserIsThreadsafe -- boolean if parser is threadsafe. If not this
                          will currently lead to a very inefficient operation

    processHelperFactory -- factory for helper object containing further
                            functions needed for editing, tree presentation
                            and so on.

    editHelperIsThreadsafe -- boolean if edit helper functions are
                              threadsafe.

    Parameters:

    ver -- API version (can only be 1 currently)
    app -- wxApp object
    """
    return ((WIKI_LANGUAGE_NAME, WIKI_HR_LANGUAGE_NAME, parserFactory,
             True, languageHelperFactory, True),)


# The PAYLOAD looks like Python code but has to use a much simpler syntax:
# 
# <identifier to overlay> = <Python expression>
# 
# If the expression spans multiple lines each except the last one has to end
# with backslash '\'
# 
# Comments are not allowed

PAYLOAD = """
BracketStart = u"[["
BracketStartPAT = ur"\[\["

BracketEnd = u"]]"
BracketEndPAT = ur"\]\]"

BracketStartRevPAT = ur"\[\["
BracketEndRevPAT = ur"\]\]"
"""

# add payload for text generator:
payload = {
    u'ATTRIBUTE_FMT': u'[[{key}: {values}]]',
    u'INSERTION_FMT': u'[[:{key}:{space}{value}{appendix}]]',
    u'WIKI_WORD_FMT': {
        0: u'[[{link_core}]]',
        1: u'[[{link_core}]]!{anchor}',
        2: u'[[{link_core}|{title}]]',
        3: u'[[{link_core}|{title}]]!{anchor}',
        4: u'[[{link_core}#{search_fragment}]]',
        5: u'[[{link_core}#{search_fragment}]]!{anchor}',
        6: u'[[{link_core}#{search_fragment}|{title}]]',
        7: u'[[{link_core}#{search_fragment}|{title}]]!{anchor}',
        # CamelCase
        8: u'{link_core}',
        9: u'{link_core}!{anchor}',
        10: u'{link_core}#{search_fragment}',
        # CamelCase and space in search fragment
        11: u'[[{link_core}#{search_fragment}]]',
    }}
lines = [u'%s = %r' % (k, v) for k, v in payload.iteritems()]
PAYLOAD += u'\n' + u'\n'.join(lines) + u'\n'



# ---------- Modifications below this line are not recommended ----------

_LINECONT_RE = re.compile(r"(?:\r\n?|\n)\\", re.UNICODE)
_LINEEND_SPLIT_RE = re.compile(r"\r\n?|\n", re.UNICODE)


def _joinLineConts(text):
    return _LINECONT_RE.sub("", text)


def _splitLines(text):
    return _LINEEND_SPLIT_RE.split(text)


class _ReplacementDictWrapper(dict):
    def __init__(self, realDict, replaceExprDict):
        self.realDict = realDict
        dict.update(self, realDict)
        self.replaceExprDict = replaceExprDict

    def __setitem__(self, key, value):
        if self.replaceExprDict.has_key(key):
            value = eval(self.replaceExprDict[key][0], self)

        self.realDict[key] = value
        dict.__setitem__(self, key, value)

    def __delitem__(self, key):
        del self.realDict[key]
        dict.__delitem__(self, key)

    @staticmethod
    def overlayToReplaceExprDict(overlay):
        overlay = _joinLineConts(overlay)

        result = {}
        for line in _splitLines(overlay):
            sp = line.split("=", 1)
            if len(sp) != 2:
                continue
            result[sp[0].strip()] = (sp[1].strip(),)

        return result


_realParserFactory = None
_realLanguageHelperFactory = None


def _loadWorkerModule():
    global _realParserFactory, _realLanguageHelperFactory
    from os.path import join
    from imp import new_module
    from pwiki.StringOps import loadEntireTxtFile

    # Find original "WikidPadParser.py" file
    try:
        # Should work with 2.2beta03 and later
        import wikidpadSystemPlugins
        targetPath = join(wikidpadSystemPlugins.__path__[0],
                          "wikidPadParser/WikidPadParser.py")
    except ImportError:
        # Fallback method
        # import sys
        # targetPath = join(sys.modules[__name__.split(".", 1)[0]].__path__[0],
        #                   "extensions/wikidPadParser/WikidPadParser.py")
        import os
        targetPath = os.path.join(os.path.dirname(__file__),
                                  "wikidPadParser/WikidPadParser.py")

    original = loadEntireTxtFile(targetPath)

    module = new_module("")

    glSpace = _ReplacementDictWrapper(
        module.__dict__,
        _ReplacementDictWrapper.overlayToReplaceExprDict(PAYLOAD))

    exec original in glSpace

    _realParserFactory = module.parserFactory
    _realLanguageHelperFactory = module.languageHelperFactory


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
        _loadWorkerModule()

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
        _loadWorkerModule()

    return _realLanguageHelperFactory(intLanguageName, debugMode)
