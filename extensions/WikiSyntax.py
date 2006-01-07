import locale
import string

import pwiki.srePersistent as re
from pwiki.StringOps import mbcsDec

locale.setlocale(locale.LC_ALL, '')


# String containing the delimiter between the title of a wiki word (to show in
# HTML and the real word, as e.g. [title | WikiWord]
TitleWikiWordDelimiter = ur"|"

# Same, escaped for regular expression
TitleWikiWordDelimiterPAT = ur"\|"


# basic formatting
BoldRE          = re.compile(u"\*(?=[^\s])(?P<boldContent>.+?)\*",
        re.DOTALL | re.UNICODE | re.MULTILINE)
ItalicRE        = re.compile(ur"\b\_(?P<italicContent>.+?)\_\b",
        re.DOTALL | re.UNICODE | re.MULTILINE)
Heading4RE      = re.compile(u"^\\+\\+\\+\\+(?!\\+) ?(?P<h4Content>[^\\+\\n]+)",
        re.DOTALL | re.UNICODE | re.MULTILINE)
Heading3RE      = re.compile(u"^\\+\\+\\+(?!\\+) ?(?P<h3Content>[^\\+\\n]+)",
        re.DOTALL | re.UNICODE | re.MULTILINE)
Heading2RE      = re.compile(u"^\\+\\+(?!\\+\\+) ?(?P<h2Content>[^\\+\\n]+)",
        re.DOTALL | re.UNICODE | re.MULTILINE)
Heading1RE      = re.compile(u"^\\+(?!\\+\\+\\+) ?(?P<h1Content>[^\\+\\n]+)",
        re.DOTALL | re.UNICODE | re.MULTILINE)
UrlRE           = re.compile(ur'(?:(?:wiki|file|https?|ftp)://|mailto:)[^"\s<]*',
        re.DOTALL | re.UNICODE | re.MULTILINE)  # SPN

# TitledUrlRE =  re.compile(
#         ur"\[(?P<titledurlTitle>.+?" + TitleWikiWordDelimiterPAT + ur"\s*)?"
#         ur"(?P<titledurlUrl>" + UrlRE.pattern + ur")\]",
#         re.DOTALL | re.UNICODE | re.MULTILINE)
TitledUrlRE =  re.compile(
        ur"\[(?P<titledurlUrl>" + UrlRE.pattern + ur")"
        ur"(?:(?P<titledurlDelim>\s*" + TitleWikiWordDelimiterPAT + ur")"
        ur"(?P<titledurlTitle>[^\]]+))?\]",
        re.DOTALL | re.UNICODE | re.MULTILINE)

# The following 3 are not in WikiFormatting.FormatExpressions
BulletRE        = re.compile(ur"^(?P<indentBullet> *)(\*)[ \t]",
        re.DOTALL | re.UNICODE | re.MULTILINE)  # SPN
NumericBulletRE = re.compile(ur"^(?P<indentNumeric> *)(?P<preLastNumeric>(?:\d+\.)*)(\d+)\.[ \t]",
        re.DOTALL | re.UNICODE | re.MULTILINE)  # SPN


# WikiWords
#WikiWordRE      = re.compile(r"\b(?<!~)(?:[A-Z\xc0-\xde\x8a-\x8f]+[a-z\xdf-\xff\x9a-\x9f]+[A-Z\xc0-\xde\x8a-\x8f]+[a-zA-Z0-9\xc0-\xde\x8a-\x8f\xdf-\xff\x9a-\x9f]*|[A-Z\xc0-\xde\x8a-\x8f]{2,}[a-z\xdf-\xff\x9a-\x9f]+)\b")
#WikiWordRE2     = re.compile("\[[a-zA-Z0-9\-\_\s]+?\]")


# TODO To unicode

UPPERCASE = mbcsDec(string.uppercase)[0]
LOWERCASE = mbcsDec(string.lowercase)[0]
LETTERS = UPPERCASE + LOWERCASE


singleWikiWord    =          (ur"(?:[" +
                             UPPERCASE +
                             # "A-Z\xc0-\xde\x8a-\x8f"
                             ur"]+[" +
                             LOWERCASE +
                             # "a-z\xdf-\xff\x9a-\x9f"
                             ur"]+[" +
                             UPPERCASE +
                             # "A-Z\xc0-\xde\x8a-\x8f"
                             ur"]+[" +
                             LETTERS + string.digits +
                             # "a-zA-Z0-9\xc0-\xde\x8a-\x8f\xdf-\xff\x9a-\x9f"
                             ur"]*|[" +
                             UPPERCASE +
                             # "A-Z\xc0-\xde\x8a-\x8f"
                             ur"]{2,}[" +
                             LOWERCASE +
                             # "a-z\xdf-\xff\x9a-\x9f"
                             ur"]+)")

WikiWordRE      = re.compile(ur"\b(?<!~)" + singleWikiWord + 
                             ur"\b", re.DOTALL | re.UNICODE | re.MULTILINE)
                             
                             
# Special version for syntax highlighting to allow appending search expression with '#'
WikiWordEditorRE = re.compile(ur"(?P<wikiword>" + WikiWordRE.pattern +
        ur")(?:#(?P<wikiwordSearchfrag>(?:(?:#.)|[^ \t\n#])+))?",
        re.DOTALL | re.UNICODE | re.MULTILINE)


# Only to exclude them from WikiWordRE2
FootnoteRE     = re.compile(ur"\[[0-9]+?\]",
        re.DOTALL | re.UNICODE | re.MULTILINE)


# Pattern string for non camelcase wiki word
WikiWordNccPAT = ur"[\w\-\_ \t]+?"



WikiWordRE2     = re.compile(ur"\[(?:" + WikiWordNccPAT + ur")\]",
        re.DOTALL | re.UNICODE | re.MULTILINE)

# Special version for syntax highlighting to allow appending search expression with '#'
# WikiWordEditorRE2      = re.compile(
#         ur"\[(?P<wikiwordnccTitle>[^\]\|]+" + TitleWikiWordDelimiterPAT + ur"\s*)?"
#         ur"(?P<wikiwordncc>" + WikiWordNccPAT + ur")\]"
#         ur"(?:#(?P<wikiwordnccSearchfrag>(?:(?:#.)|[^ \t\n#])+))?",
#         re.DOTALL | re.UNICODE | re.MULTILINE)
WikiWordEditorRE2      = re.compile(
        ur"\[(?P<wikiwordncc>" + WikiWordNccPAT + ur")"
        ur"(?:(?P<wikiwordnccDelim>\s*" + TitleWikiWordDelimiterPAT + ur")"
        ur"(?P<wikiwordnccTitle>[^\]]+))?\]"
        ur"(?:#(?P<wikiwordnccSearchfrag>(?:(?:#.)|[^ \t\n#])+))?",
        re.DOTALL | re.UNICODE | re.MULTILINE)

SearchUnescapeRE   = re.compile(ur"#(.)",
                              re.DOTALL | re.UNICODE | re.MULTILINE)



# parses the dynamic properties
PropertyRE      = re.compile(ur"\[\s*(?P<propertyName>[a-zA-Z0-9\-\_\.]+?)\s*" +
                  ur"[=:]\s*(?P<propertyValue>[\w\-\_ \t]+?)\]",
                  re.DOTALL | re.UNICODE | re.MULTILINE)


# Reverse REs for autocompletion
revSingleWikiWord    =       (ur"(?:[" +
                             LETTERS + string.digits +
                             ur"]*[" +
                             UPPERCASE+
                             ur"])")

RevWikiWordRE      = re.compile(ur"^" + revSingleWikiWord + 
                             ur"(?![\~])\b", re.DOTALL | re.UNICODE | re.MULTILINE)

RevWikiWordRE2     = re.compile(ur"^[\w\-\_ \t.]+?\[",
        re.DOTALL | re.UNICODE | re.MULTILINE)  # SPN

RevPropertyValue     = re.compile(ur"^([\w\-\_ \t]*?)([ \t]*[=:][ \t]*)([a-zA-Z0-9\-\_ \t\.]+?)\[",
        re.DOTALL | re.UNICODE | re.MULTILINE)  # SPN



# script blocks
ScriptRE        = re.compile(u"\<%(.*?)%\>", re.DOTALL)

# Auto generated area
AutoGenAreaRE = re.compile(ur"^([ \t]*<<[ \t]+)([^\n]+\n)(.*?)^([ \t]*>>[ \t]*\n)", re.DOTALL | re.LOCALE | re.MULTILINE)
# todos, non-capturing
## ToDoRE          = re.compile(u"^\s*(?:todo|action|track|issue|question|project)\\.?[^\\:\\s]*:", re.DOTALL | re.LOCALE | re.MULTILINE)
ToDoRE          = re.compile(ur"^\s*(?:todo|action|track|issue|question|project)(?:\.[^:\s]+)?:",
        re.DOTALL | re.UNICODE | re.MULTILINE)
        
# todos, captures the todo item text
## ToDoREWithContent = re.compile(u"^\s*((?:todo|action|track|issue|question|project)\\.?[^\\:\\s]*:[^\\r\\n]+)", re.MULTILINE)

ToDoREWithContent = re.compile(ur"(?P<todoIndent>^\s*)"
        ur"(?P<todoName>(?:todo|action|track|issue|question|project)(?:\.[^:\s]+)?)"
        ur"(?P<todoDelimiter>:)(?P<todoValue>[^\r\n]+)",
        re.DOTALL | re.UNICODE | re.MULTILINE)

# todos, used in the tree control to parse saved todos. Because they were
#   already identified as todos, the regexp can be quite simple
## ToDoREWithCapturing = re.compile(u"(todo|action|track|issue|question|project)\\.?([^\\:\\s]*):([^\\r\\n]+)")
ToDoREWithCapturing = re.compile(ur"([^:\s]+):\s*([^\r\n]+)",
        re.DOTALL | re.UNICODE | re.MULTILINE)


# used to detect indent levels

# The following 2 are not in WikiFormatting.FormatExpressions
EmptyLineRE     = re.compile(ur"^[\s\r\n]*$",
        re.DOTALL | re.UNICODE | re.MULTILINE)

HorizLineRE     = re.compile(u"----+", re.DOTALL | re.UNICODE | re.MULTILINE)

# suppression expression
# Orig: SuppressHighlightingRE = re.compile("\<\<(.*?)\>\>", re.DOTALL)
SuppressHighlightingRE = re.compile(ur"^(?P<suppressIndent>[ \t]*)<<[ \t]*$"+
        ur"(?P<suppressContent>.*?)^[ \t]*>>[ \t]*$",
        re.DOTALL | re.UNICODE | re.MULTILINE)

TableRE = re.compile(ur"(?P<tableBegin>^[ \t]*<<\|[ \t]*$)"
        ur"(?P<tableContent>.*?)(?P<tableEnd>^[ \t]*>>[ \t]*$)",
        re.DOTALL | re.UNICODE | re.MULTILINE)

