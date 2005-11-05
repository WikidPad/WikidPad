import re
import locale
import string

locale.setlocale(locale.LC_ALL, '')

# basic formatting
BoldRE          = re.compile("\*(?=[^\s])(.+?)\*", re.DOTALL)
ItalicRE        = re.compile(r"\b\_(.+?)\_\b", re.DOTALL)
Heading4RE      = re.compile("^\\+\\+\\+\\+(?!\\+) ?([^\\+\\n]+)", re.MULTILINE)
Heading3RE      = re.compile("^\\+\\+\\+(?!\\+) ?([^\\+\\n]+)", re.MULTILINE)
Heading2RE      = re.compile("^\\+\\+(?!\\+\\+) ?([^\\+\\n]+)", re.MULTILINE)
Heading1RE      = re.compile("^\\+(?!\\+\\+\\+) ?([^\\+\\n]+)", re.MULTILINE)
UrlRE           = re.compile("!?(?:\".+?\"\:)?((?:(?:wiki|file|https?|ftp)://[^\s!<]*|[^\@\s]+\@[^\s!]+))!?")
BulletRE        = re.compile("^(\s*)(\*)\s([^\\n]*)")
NumericBulletRE = re.compile("^(\s*)(\#)\s([^\\n]*)")
IndentedContentRE = re.compile("^((?:\s{4})+)()([^\\n]*)")

# WikiWords
#WikiWordRE      = re.compile(r"\b(?<!~)(?:[A-Z\xc0-\xde\x8a-\x8f]+[a-z\xdf-\xff\x9a-\x9f]+[A-Z\xc0-\xde\x8a-\x8f]+[a-zA-Z0-9\xc0-\xde\x8a-\x8f\xdf-\xff\x9a-\x9f]*|[A-Z\xc0-\xde\x8a-\x8f]{2,}[a-z\xdf-\xff\x9a-\x9f]+)\b")
#WikiWordRE2     = re.compile("\[[a-zA-Z0-9\-\_\s]+?\]")

WikiWordRE      = re.compile(r"\b(?<!~)(?:[" +
                             string.uppercase +
                             # "A-Z\xc0-\xde\x8a-\x8f"
                             r"]+[" +
                             string.lowercase +
                             # "a-z\xdf-\xff\x9a-\x9f"
                             r"]+[" +
                             string.uppercase +
                             # "A-Z\xc0-\xde\x8a-\x8f"
                             r"]+[" +
                             string.letters + string.digits +
                             # "a-zA-Z0-9\xc0-\xde\x8a-\x8f\xdf-\xff\x9a-\x9f"
                             r"]*|[" +
                             string.uppercase +
                             # "A-Z\xc0-\xde\x8a-\x8f"
                             r"]{2,}[" +
                             string.lowercase +
                             # "a-z\xdf-\xff\x9a-\x9f"
                             r"]+)\b", re.LOCALE)

WikiWordRE2     = re.compile("\[[" + string.letters + string.digits + "\-\_\s]+?\]", re.LOCALE)

# parses the dynamic properties
PropertyRE      = re.compile("\[\s*([a-zA-Z0-9\-\_\s\.]+?)\s*[=:]\s*([a-zA-Z0-9\-\_\s]+?)\s*\]")

# script blocks
ScriptRE        = re.compile("\<%(.*?)%\>", re.DOTALL)

# todos, non-capturing
ToDoRE          = re.compile("^\s*(?:todo|action|track|issue|question|project)\\.?[^\\:\\s]*:", re.MULTILINE)
# todos, captures the todo item text
ToDoREWithContent = re.compile("^\s*((?:todo|action|track|issue|question|project)\\.?[^\\:\\s]*:[^\\r\\n]+)", re.MULTILINE)
# todos, used in the tree control to parse saved todos
ToDoREWithCapturing = re.compile("(todo|action|track|issue|question|project)\\.?([^\\:\\s]*):([^\\r\\n]+)")

# used to detect indent levels
IndentedRE      = re.compile("^(    +)([^\\n]+)")

EmptyLineRE     = re.compile("^[\s\r\n]*$", re.MULTILINE)
HorizLineRE     = re.compile("----+")

# suppression expression
SuppressHighlightingRE = re.compile("\<\<(.*?)\>\>", re.DOTALL)
