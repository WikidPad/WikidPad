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
# (1, 8, 207, 0) is 1.8rc07
# (2, 0, 3, 0) is 2.0alpha03
# (1, 9, 104, 0) is 1.9beta04
# (1, 9, 104, 2) is something after 1.9beta04
# (2, 0, 300, 0) is 2.0final

VERSION_TUPLE = ("wikidPad", 2, 3, 115, 0)
VERSION_STRING = "wikidPad 2.3beta15"
HOMEPAGE = u"http://wikidpad.sourceforge.net"

CONFIG_FILENAME = "WikidPad.config"
CONFIG_GLOBALS_DIRNAME = "WikidPadGlobals"



DEADBLOCKTIMEOUT = 1800


# Scintilla known format types and numbers
FormatTypes = Enumeration("FormatTypes", ["Default", "WikiWord",
        "AvailWikiWord", "Bold", "Italic", "Heading1", "Heading2", "Heading3",
        "Heading4", "Url", "Script", "Attribute", "ToDo"
        ], 0)


# Store hints for WikiData.storeDataBlock()

DATABLOCK_STOREHINT_INTERN = 0
DATABLOCK_STOREHINT_EXTERN = 1

# Content was modified and isn't in sync with meta data
WIKIWORDMETADATA_STATE_DIRTY = 0
# Attributes were processed
WIKIWORDMETADATA_STATE_ATTRSPROCESSED = 1
# All syntax information (links, todos, etc.) is processed
WIKIWORDMETADATA_STATE_SYNTAXPROCESSED = 2
# Syntax is processed and reverse index is up to date
WIKIWORDMETADATA_STATE_INDEXED = 6  # = 2 | 4

# WIKIWORDMETADATA_STATE_BIT_INDEXED = 4
# WIKIWORDMETADATA_STATE_BITMASK_SYNTAXPROCESSED = 3



# Types of wikiword match terms (some can be binary or'ed together)

# Explicit alias (by "alias" attribute).
WIKIWORDMATCHTERMS_TYPE_EXPLICIT_ALIAS = 1
# When trying to resolve links, look at this, too.
WIKIWORDMATCHTERMS_TYPE_ASLINK = 2


# The following four cannot be combined

# Bitmask to filter out following three
WIKIWORDMATCHTERMS_TYPE_FROM_MASK = 12
# Matchterm was created based on the wiki word itself
WIKIWORDMATCHTERMS_TYPE_FROM_WORD = 0
# Matchterm was created based on attributes(=properties) of the page or the wiki word
WIKIWORDMATCHTERMS_TYPE_FROM_ATTRIBUTES = 4
# Matchterm was created based on content of the page or one of the above
WIKIWORDMATCHTERMS_TYPE_FROM_CONTENT = 8


# Matchterm will be created and deleted synchronously (normally in main thread)
# to ensure it is always up-to-date
WIKIWORDMATCHTERMS_TYPE_SYNCUPDATE = 16



# Search types as they can be selected in the radiobox for wiki-wide search

# Simple regex
SEARCHTYPE_REGEX = 0
# Boolean regex
SEARCHTYPE_BOOLEANREGEX = 1
# Text as is
SEARCHTYPE_ASIS = 2
# Index search
SEARCHTYPE_INDEX = 3

# Version number of the current searchindex. If number doesn't match with
# number in configuration file, index must be rebuild
SEARCHINDEX_FORMAT_NO = 4



TEXTEDITOP_INSERT = 1
TEXTEDITOP_DELETE = 2
