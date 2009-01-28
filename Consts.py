from pwiki.Enum import Enumeration


# VERSION_TUPLE is structured (branch, major, minor, stateAndMicro, patch)
# where branch is normally string "wikidPad", but should be changed if somebody
# develops a derived version of WikidPad.
# 
# major and minor are the main versions,
# stateAndMicro is:
#     between 0 and 99 for "alpha" 
#     between 100 and 199 for "beta"
#     between 200 and 299 for "rc" (release candidate)
#     300 for "final"
#     
#     the unit and tenth place form the micro version.
# 
# patch is a sub-micro version, if needed, normally 0.
# 
# Examples:
# (1, 8, 107, 0) is 1.8rc7
# (1, 9, 4, 0) is 1.9beta4
# (1, 9, 4, 2) is something after 1.9beta4
# (2, 0, 200, 0) is 2.0final

VERSION_TUPLE = ("wikidPad", 2, 0, 1, 2)
VERSION_STRING = "wikidPad 2.0alpha01_2"
HOMEPAGE = u"http://wikidpad.sourceforge.net"

CONFIG_FILENAME = "WikidPad.config"
CONFIG_GLOBALS_DIRNAME = "WikidPadGlobals"



# Remove this when going into 2.0beta phase!!!
DEADBLOCKTIMEOUT = 40


# Scintilla known format types and numbers
FormatTypes = Enumeration("FormatTypes", ["Default", "WikiWord",
        "AvailWikiWord", "Bold", "Italic", "Heading1", "Heading2", "Heading3",
        "Heading4", "Url", "Script", "Property", "ToDo"
        ], 0)


# Store hints for WikiData.storeDataBlock()

DATABLOCK_STOREHINT_INTERN = 0
DATABLOCK_STOREHINT_EXTERN = 1


WIKIWORDMETADATA_STATE_DIRTY = 0
WIKIWORDMETADATA_STATE_PROPSPROCESSED = 1
WIKIWORDMETADATA_STATE_UPTODATE = 2



# Types of wikiword match terms (some can be binary or'ed together)

# Explicit alias (by "alias" property).
WIKIWORDMATCHTERMS_TYPE_EXPLICIT_ALIAS = 1
# When trying to resolve links, look at this, too.
WIKIWORDMATCHTERMS_TYPE_ASLINK = 2

# The following four cannot be combined
# Bitmask to filter out following three
WIKIWORDMATCHTERMS_TYPE_FROM_MASK = 12
# Matchterm was created based on the wiki word itself
WIKIWORDMATCHTERMS_TYPE_FROM_WORD = 0
# Matchterm was created based on properties(=attributes) of the page or the wiki word
WIKIWORDMATCHTERMS_TYPE_FROM_PROPERTIES = 4
# Matchterm was created based on content of the page or one of the above
WIKIWORDMATCHTERMS_TYPE_FROM_CONTENT = 8


# Matchterm will be created and deleted synchronously (normally in main thread)
# to ensure it is always up-to-date
WIKIWORDMATCHTERMS_TYPE_SYNCUPDATE = 16



# Search types as they can be selected in the radiobox for wiki-wide search

# Simple regex
SEARCHTYPE_REGEX = 0
# Boolean regex (currently only "anded" regex)
SEARCHTYPE_BOOLEANREGEX = 1
# Text as is
SEARCHTYPE_ASIS = 2
