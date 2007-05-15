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


PlainCharacterPAT = ur"(?:[^\\]|\\.)"
PlainCharacterNoLfPAT = ur"(?:[^\\\n]|\\[^\n])"



PlainEscapedCharacterRE = re.compile(ur"\\(.)",
        re.DOTALL | re.UNICODE | re.MULTILINE)


# How to start a non-camelcase wiki word or an attribute (normally opening bracket)
BracketStart = u"["
# Same, escaped for RE pattern
BracketStartPAT = ur"\["
# Same, escaped for reverse RE pattern (for autocompletion)
BracketStartRevPAT = ur"\["

# How to end a non-camelcase wiki word or an attribute (normally closing bracket)
BracketEnd = u"]"
# Same, escaped for RE pattern
BracketEndPAT = ur"\]"
# Same, escaped for reverse RE pattern (for autocompletion)
BracketEndRevPAT = ur"\]"


PlainCharactersRE = re.compile(PlainCharacterPAT + "+",
        re.DOTALL | re.UNICODE | re.MULTILINE)


# basic formatting
BoldRE          = re.compile(ur"\*(?=\S)(?P<boldContent>" + PlainCharacterPAT +
        ur"+?)\*",
        re.DOTALL | re.UNICODE | re.MULTILINE)
ItalicRE        = re.compile(ur"\b_(?P<italicContent>" + PlainCharacterPAT +
        ur"+?)_\b",
        re.DOTALL | re.UNICODE | re.MULTILINE)
HtmlTagRE = re.compile(
        ur"</?[A-Za-z][A-Za-z0-9]*(?:/| [^\n>]*)?>",
        re.DOTALL | re.UNICODE | re.MULTILINE)
HtmlEntityRE = re.compile(
        ur"&(?:[A-Za-z0-9]{2,10}|#[0-9]{1,10}|#x[0-9a-fA-F]{1,8});",
        re.DOTALL | re.UNICODE | re.MULTILINE)
Heading15RE      = re.compile(ur"^\+{15}(?!\+) ?(?P<h15Content>" +
        PlainCharacterPAT + ur"+?)\n",
        re.DOTALL | re.UNICODE | re.MULTILINE)
Heading14RE      = re.compile(ur"^\+{14}(?!\+) ?(?P<h14Content>" +
        PlainCharacterPAT + ur"+?)\n",
        re.DOTALL | re.UNICODE | re.MULTILINE)
Heading13RE      = re.compile(ur"^\+{13}(?!\+) ?(?P<h13Content>" +
        PlainCharacterPAT + ur"+?)\n",
        re.DOTALL | re.UNICODE | re.MULTILINE)
Heading12RE      = re.compile(ur"^\+{12}(?!\+) ?(?P<h12Content>" +
        PlainCharacterPAT + ur"+?)\n",
        re.DOTALL | re.UNICODE | re.MULTILINE)
Heading11RE      = re.compile(ur"^\+{11}(?!\+) ?(?P<h11Content>" +
        PlainCharacterPAT + ur"+?)\n",
        re.DOTALL | re.UNICODE | re.MULTILINE)
Heading10RE      = re.compile(ur"^\+{10}(?!\+) ?(?P<h10Content>" +
        PlainCharacterPAT + ur"+?)\n",
        re.DOTALL | re.UNICODE | re.MULTILINE)
Heading9RE      = re.compile(ur"^\+{9}(?!\+) ?(?P<h9Content>" +
        PlainCharacterPAT + ur"+?)\n",
        re.DOTALL | re.UNICODE | re.MULTILINE)
Heading8RE      = re.compile(ur"^\+{8}(?!\+) ?(?P<h8Content>" +
        PlainCharacterPAT + ur"+?)\n",
        re.DOTALL | re.UNICODE | re.MULTILINE)
Heading7RE      = re.compile(ur"^\+{7}(?!\+) ?(?P<h7Content>" +
        PlainCharacterPAT + ur"+?)\n",
        re.DOTALL | re.UNICODE | re.MULTILINE)
Heading6RE      = re.compile(ur"^\+{6}(?!\+) ?(?P<h6Content>" +
        PlainCharacterPAT + ur"+?)\n",
        re.DOTALL | re.UNICODE | re.MULTILINE)
Heading5RE      = re.compile(ur"^\+{5}(?!\+) ?(?P<h5Content>" +
        PlainCharacterPAT + ur"+?)\n",
        re.DOTALL | re.UNICODE | re.MULTILINE)
Heading4RE      = re.compile(ur"^\+{4}(?!\+) ?(?P<h4Content>" +
        PlainCharacterPAT + ur"+?)\n",
        re.DOTALL | re.UNICODE | re.MULTILINE)
Heading3RE      = re.compile(ur"^\+{3}(?!\+) ?(?P<h3Content>" +
        PlainCharacterPAT + ur"+?)\n",
        re.DOTALL | re.UNICODE | re.MULTILINE)
Heading2RE      = re.compile(ur"^\+{2}(?!\+) ?(?P<h2Content>" +
        PlainCharacterPAT + ur"+?)\n",
        re.DOTALL | re.UNICODE | re.MULTILINE)
Heading1RE      = re.compile(ur"^\+{1}(?!\+) ?(?P<h1Content>" +
        PlainCharacterPAT + ur"+?)\n",
        re.DOTALL | re.UNICODE | re.MULTILINE)
# UrlRE           = re.compile(ur'(?:(?:wiki|file|https?|ftp|rel)://|mailto:)[^"\s<>]*',
#         re.DOTALL | re.UNICODE | re.MULTILINE)  # SPN
UrlRE           = re.compile(ur'(?:(?:wiki|https?|ftp|rel)://|mailto:|file://?)'
        ur'(?:(?![.,;:!?)]+["\s])[^"\s<>])*(?:>\S+)?',
        re.DOTALL | re.UNICODE | re.MULTILINE)  # SPN



TitledUrlRE =  re.compile(BracketStartPAT + 
        ur"(?P<titledurlUrl>" + UrlRE.pattern + ur")"
        ur"(?:(?P<titledurlDelim>[ \t]*" + TitleWikiWordDelimiterPAT + ur")"
        ur"(?P<titledurlTitle>" + PlainCharacterPAT + ur"+?))?" + BracketEndPAT,
        re.DOTALL | re.UNICODE | re.MULTILINE)


# The following 2 are not in WikiFormatting.FormatExpressions
BulletRE        = re.compile(ur"^(?P<indentBullet>[ \t]*)(?P<actualBullet>\*[ \t])",
        re.DOTALL | re.UNICODE | re.MULTILINE)  # SPN
NumericBulletRE = re.compile(ur"^(?P<indentNumeric>[ \t]*)(?P<preLastNumeric>(?:\d+\.)*)(\d+)\.[ \t]",
        re.DOTALL | re.UNICODE | re.MULTILINE)  # SPN


# WikiWords
#WikiWordRE      = re.compile(r"\b(?<!~)(?:[A-Z\xc0-\xde\x8a-\x8f]+[a-z\xdf-\xff\x9a-\x9f]+[A-Z\xc0-\xde\x8a-\x8f]+[a-zA-Z0-9\xc0-\xde\x8a-\x8f\xdf-\xff\x9a-\x9f]*|[A-Z\xc0-\xde\x8a-\x8f]{2,}[a-z\xdf-\xff\x9a-\x9f]+)\b")
#WikiWordRE2     = re.compile("\[[a-zA-Z0-9\-\_\s]+?\]")


# TODO To unicode

UPPERCASE = mbcsDec(string.uppercase)[0]
LOWERCASE = mbcsDec(string.lowercase)[0]
LETTERS = UPPERCASE + LOWERCASE


# # Pattern string for delimiter for search fragment after wiki word
# WikiWordSearchFragDelimPAT = ur"#"
# 
# # Pattern string for search fragment itself
# WikiWordSearchFragPAT = ur"(?:#.|[^ \t\n#])+"


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

WikiWordRE      = re.compile(ur"\b(?<!~)" + singleWikiWord + ur"\b", # ur"(?:/" + singleWikiWord +
                             # ur")*\b",
                             re.DOTALL | re.UNICODE | re.MULTILINE)


AnchorStart = ur"!"
AnchorStartPAT = ur"!"

# Special version for syntax highlighting to allow appending search expression with '#'
WikiWordEditorRE = re.compile(ur"(?P<wikiword>" + WikiWordRE.pattern +
        ur")(?:#(?P<wikiwordSearchfrag>(?:(?:#.)|[^ \t\n#])+)|" + 
        AnchorStartPAT + ur"(?P<wikiwordAnchorfrag>[A-Za-z0-9\_]+))?",
        re.DOTALL | re.UNICODE | re.MULTILINE)


# Only to exclude them from WikiWordRE2
FootnoteRE     = re.compile(BracketStartPAT + ur"(?P<footnoteId>[0-9]+?)" +
        BracketEndPAT, re.DOTALL | re.UNICODE | re.MULTILINE)


# Pattern string for non camelcase wiki word
WikiWordNccPAT = ur"[\w\-\_ \t]+?"
WikiWordNccRevPAT = ur"[\w\-\_ \t]+?"



WikiWordRE2     = re.compile(BracketStartPAT + ur"(?:" + WikiWordNccPAT +
        ur")" + BracketEndPAT, re.DOTALL | re.UNICODE | re.MULTILINE)

# Special version for syntax highlighting to allow appending search expression with '#'
# WikiWordEditorRE2      = re.compile(
#         ur"\[(?P<wikiwordnccTitle>[^\]\|]+" + TitleWikiWordDelimiterPAT + ur"\s*)?"
#         ur"(?P<wikiwordncc>" + WikiWordNccPAT + ur")\]"
#         ur"(?:#(?P<wikiwordnccSearchfrag>(?:(?:#.)|[^ \t\n#])+))?",
#         re.DOTALL | re.UNICODE | re.MULTILINE)
WikiWordEditorRE2      = re.compile(
        BracketStartPAT + ur"(?P<wikiwordncc>" + WikiWordNccPAT + ur")"
        ur"(?:(?P<wikiwordnccDelim>[ \t]*" + TitleWikiWordDelimiterPAT + ur")"
        ur"(?P<wikiwordnccTitle>" + PlainCharacterPAT + ur"+?))?" +
        BracketEndPAT +
        ur"(?:#(?P<wikiwordnccSearchfrag>(?:(?:#.)|[^ \t\n#])+)|" +
        AnchorStartPAT + ur"(?P<wikiwordnccAnchorfrag>[A-Za-z0-9\_]+))?",
        re.DOTALL | re.UNICODE | re.MULTILINE)

SearchFragmentUnescapeRE   = re.compile(ur"#(.)",
                              re.DOTALL | re.UNICODE | re.MULTILINE)


# For spell checking
TextWordRE = re.compile(ur"(?P<negative>[0-9]+|"+ UrlRE.pattern + u"|" +
        WikiWordRE.pattern + ur")|\b[\w']+",
        re.DOTALL | re.UNICODE | re.MULTILINE)  # SP only



# parses the dynamic properties
PropertyRE      = re.compile(BracketStartPAT +
        ur"[ \t]*(?P<propertyName>[\w\-\_\.]+?)[ \t]*"
        ur"[=:][ \t]*(?P<propertyValue>[\w\-\_ \t:;,.!?#/|]+?)" + 
        BracketEndPAT,
        re.DOTALL | re.UNICODE | re.MULTILINE)



InsertionValueRE = re.compile(ur"(?:(?P<insertionValue>[\w][\w\-\_ \t,.!?#/|]*)|"
        ur"(?P<insertionQuoteStarter>\"+|'+|/+|\\+)"
        ur"(?P<insertionQuotedValue>.*?)(?P=insertionQuoteStarter))",
        re.DOTALL | re.UNICODE | re.MULTILINE)

InsertionAppendixRE = re.compile(ur";[ \t]*(?:"
        ur"(?P<insertionAppendix>[\w][\w\-\_ \t,.!?#/|]*)|"
        ur"(?P<insertionApxQuoteStarter>\"+|'+|/+|\\+)"
        ur"(?P<insertionQuotedAppendix>.*?)(?P=insertionApxQuoteStarter))",
        re.DOTALL | re.UNICODE | re.MULTILINE)

InsertionRE     = re.compile(BracketStartPAT +
        ur":[ \t]*(?P<insertionKey>[\w][\w\-\_\.]*)[ \t]*"
        ur":[ \t]*(?P<insertionContent>" +
        InsertionValueRE.pattern +
        ur"(?:" + InsertionAppendixRE.pattern + ur")*)" + BracketEndPAT,
        re.DOTALL | re.UNICODE | re.MULTILINE)


# Reverse REs for autocompletion
revSingleWikiWord    =       (ur"(?:[" +
                             LETTERS + string.digits +
                             ur"]*[" +
                             UPPERCASE+
                             ur"])")

RevWikiWordRE      = re.compile(ur"^" + # revSingleWikiWord + ur"(?:/" +
                             revSingleWikiWord + ur"(?![\~])\b",
                             re.DOTALL | re.UNICODE | re.MULTILINE)  # SPN

RevWikiWordRE2     = re.compile(ur"^" + WikiWordNccRevPAT + BracketStartRevPAT,
        re.DOTALL | re.UNICODE | re.MULTILINE)  # SPN

RevPropertyValue     = re.compile(
        ur"^([\w\-\_ \t:;,.!?#/|]*?)([ \t]*[=:][ \t]*)([\w\-\_ \t\.]+?)" +
        BracketStartRevPAT,
        re.DOTALL | re.UNICODE | re.MULTILINE)  # SPN


RevTodoKeyRE = re.compile(ur"^(?:[^:\s]{0,40}\.)??"
        ur"(?:odot|enod|tiaw|noitca|kcart|eussi|noitseuq|tcejorp)",
        re.DOTALL | re.UNICODE | re.MULTILINE)  # SPN

RevTodoValueRE = re.compile(ur"^[^\n:]{0,30}:" + RevTodoKeyRE.pattern[1:],
        re.DOTALL | re.UNICODE | re.MULTILINE)  # SPN


RevWikiWordAnchorRE = re.compile(ur"^(?P<anchorBegin>[A-Za-z0-9\_]{0,20})" +
        AnchorStartPAT + ur"(?P<wikiWord>" + RevWikiWordRE.pattern[1:] + ur")",
        re.DOTALL | re.UNICODE | re.MULTILINE)  # SPN
        
RevWikiWordAnchorRE2 = re.compile(ur"^(?P<anchorBegin>[A-Za-z0-9\_]{0,20})" + 
        AnchorStartPAT + BracketEndRevPAT + ur"(?P<wikiWord>" + 
        WikiWordNccRevPAT + ur")" + BracketStartRevPAT,
        re.DOTALL | re.UNICODE | re.MULTILINE)  # SPN


AutoLinkRelaxSplitRE = re.compile(r"[\W]+", re.IGNORECASE | re.UNICODE)  # SPN

AutoLinkRelaxJoinPAT = ur"[\W]+"
# AutoLinkRelaxJoinPAT = ur"[ \n\t]+"
AutoLinkRelaxJoinFlags = re.IGNORECASE | re.UNICODE


# script blocks
# ScriptRE        = re.compile(u"\<%(.*?)%\>", re.DOTALL)
ScriptRE        = re.compile(u"\<%(?P<scriptContent>.*?)%\>", re.DOTALL)

# Auto generated area
AutoGenAreaRE = re.compile(ur"^([ \t]*<<[ \t]+)([^\n]+\n)(.*?)^([ \t]*>>[ \t]*\n)",
        re.DOTALL | re.LOCALE | re.MULTILINE)
        
# todos, captures the todo item text
ToDoREWithContent = re.compile(ur"\b(?P<todoIndent>)"    # ur"(?P<todoIndent>^[ \t]*)"
        ur"(?P<todoName>(?:todo|done|wait|action|track|issue|question|project)(?:\.[^:\s]+)?)"
        ur"(?P<todoDelimiter>:)(?P<todoValue>" + PlainCharacterNoLfPAT +
        ur"+?)(?:$|(?=\|))", re.DOTALL | re.UNICODE | re.MULTILINE)

# todos, used in the tree control to parse saved todos. Because they were
#   already identified as todos, the regexp can be quite simple
ToDoREWithCapturing = re.compile(ur"^([^:\s]+):[ \t]*(.+?)$",
        re.DOTALL | re.UNICODE | re.MULTILINE)


# used to detect indent levels

# The following 2 are not in WikiFormatting.FormatExpressions
EmptyLineRE     = re.compile(ur"^[ \t\r\n]*$",
        re.DOTALL | re.UNICODE | re.MULTILINE)

HorizLineRE     = re.compile(u"----+", re.DOTALL | re.UNICODE | re.MULTILINE)


# suppression expression
SuppressHighlightingRE = re.compile(ur"^(?P<suppressIndent>[ \t]*)<<[ \t]*\n"+
        ur"(?P<suppressContent>.*?)\n[ \t]*>>[ \t]*$",
        re.DOTALL | re.UNICODE | re.MULTILINE)

AnchorRE = re.compile(ur"^[ \t]*anchor:[ \t]*(?P<anchorValue>[A-Za-z0-9\_]+)\n",
        re.DOTALL | re.UNICODE | re.MULTILINE)


TableRowDelimiterPAT = ur"\n"

TableRE = re.compile(ur"(?P<tableBegin>^[ \t]*<<\|[ \t]*$)"
        ur"(?P<tableContent>" + PlainCharacterPAT +
        ur"*?)(?P<tableEnd>^[ \t]*>>[ \t]*$)",
        re.DOTALL | re.UNICODE | re.MULTILINE)


PreBlockRE = re.compile(ur"(?P<preBegin>^[ \t]*<<pre[ \t]*\n)"
        ur"(?P<preContent>."         #  + PlainCharacterPAT +
        ur"*?)(?P<preEnd>\n[ \t]*>>[ \t]*$(\n)?)",
        re.DOTALL | re.UNICODE | re.MULTILINE)

