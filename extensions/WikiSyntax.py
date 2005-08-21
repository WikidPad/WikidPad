import re
import locale
import string

from pwiki.StringOps import mbcsDec

locale.setlocale(locale.LC_ALL, '')

# basic formatting
BoldRE          = re.compile(u"\*(?=[^\s])(.+?)\*",
        re.DOTALL | re.LOCALE | re.MULTILINE)
ItalicRE        = re.compile(ur"\b\_(.+?)\_\b",
        re.DOTALL | re.LOCALE | re.MULTILINE)
Heading4RE      = re.compile(u"^\\+\\+\\+\\+(?!\\+) ?([^\\+\\n]+)",
        re.DOTALL | re.LOCALE | re.MULTILINE)
Heading3RE      = re.compile(u"^\\+\\+\\+(?!\\+) ?([^\\+\\n]+)",
        re.DOTALL | re.LOCALE | re.MULTILINE)
Heading2RE      = re.compile(u"^\\+\\+(?!\\+\\+) ?([^\\+\\n]+)",
        re.DOTALL | re.LOCALE | re.MULTILINE)
Heading1RE      = re.compile(u"^\\+(?!\\+\\+\\+) ?([^\\+\\n]+)",
        re.DOTALL | re.LOCALE | re.MULTILINE)
UrlRE           = re.compile(u"((?:wiki|file|https?|ftp|mailto)://[^\s<]*)",
        re.DOTALL | re.LOCALE | re.MULTILINE)


# The following 3 are not in WikiFormatting.FormatExpressions
BulletRE        = re.compile(u"^(\s*)(\*)\s([^\\n]*)")
NumericBulletRE = re.compile(u"^(\s*)(\d+)\.\s([^\\n]*)")
IndentedContentRE = re.compile(u"^((?:\s{4})+)()([^\\n]*)")

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
                             ur"\b", re.DOTALL | re.LOCALE | re.MULTILINE)

WikiWordRE2     = re.compile(u"\[[" + LETTERS + string.digits + u"\-\_\s]+?\]",
        re.DOTALL | re.LOCALE | re.MULTILINE)

# parses the dynamic properties
PropertyRE      = re.compile(ur"\[\s*([a-zA-Z0-9\-\_\s\.]+?)\s*[=:]\s*([" +
                  LETTERS + string.digits + ur"\-\_\s]+?)\s*\]", re.DOTALL | re.LOCALE | re.MULTILINE)

# script blocks
ScriptRE        = re.compile(u"\<%(.*?)%\>", re.DOTALL)

# todos, non-capturing
ToDoRE          = re.compile(u"^\s*(?:todo|action|track|issue|question|project)\\.?[^\\:\\s]*:", re.DOTALL | re.LOCALE | re.MULTILINE)
# todos, captures the todo item text
ToDoREWithContent = re.compile(u"^\s*((?:todo|action|track|issue|question|project)\\.?[^\\:\\s]*:[^\\r\\n]+)", re.MULTILINE)
# todos, used in the tree control to parse saved todos
ToDoREWithCapturing = re.compile(u"(todo|action|track|issue|question|project)\\.?([^\\:\\s]*):([^\\r\\n]+)")

# used to detect indent levels

# The following 3 are not in WikiFormatting.FormatExpressions
IndentedRE      = re.compile(u"^(    +)([^\\n]+)")

EmptyLineRE     = re.compile(u"^[\s\r\n]*$", re.MULTILINE)
HorizLineRE     = re.compile(u"----+")

# suppression expression
# Orig: SuppressHighlightingRE = re.compile("\<\<(.*?)\>\>", re.DOTALL)
SuppressHighlightingRE = re.compile(ur"^[ \t]*<<[ \t]*$(.*?)^[ \t]*>>[ \t]*$", re.DOTALL | re.LOCALE | re.MULTILINE)

