## import hotshot
## _prof = hotshot.Profile("hotshot.prf")

# Official parser plugin for wiki language "WikidPad default 2.0"
# Last modified (format YYYY-MM-DD): 2017-10-18
from collections import Counter

import sys, string, traceback

from textwrap import fill

import wx

import re
from pwiki.WikiExceptions import *
from pwiki import StringOps, Localization
from pwiki.StringOps import UPPERCASE, LOWERCASE, revStr

sys.stderr = sys.stdout

# locale.setlocale(locale.LC_ALL, '')
# wx.Locale(wx.LANGUAGE_DEFAULT)
Localization.setLocale("")

from pwiki.WikiPyparsing import *


WIKIDPAD_PLUGIN = (("WikiParser", 1),)

WIKI_LANGUAGE_NAME = "wikidpad_default_2_0"
WIKI_HR_LANGUAGE_NAME = "WikidPad default 2.0"


LETTERS = UPPERCASE + LOWERCASE


# The specialized optimizer in WikiPyParsing can't handle automatic whitespace
# removing
ParserElement.setDefaultWhitespaceChars("")



RE_FLAGS = re.DOTALL | re.UNICODE | re.MULTILINE


class IndentInfo:
    __slots__ = ("level", "type")
    def __init__(self, type):
        self.level = 0
        self.type = type



def buildRegex(regex, resultsName=None, hideOnEmpty=False, name=None):
    element = Regex(regex, RE_FLAGS)
    
    if name is None:
        name = resultsName
    
    if resultsName is not None:
        element = element.setResultsNameNoCopy(resultsName)
    
    if name is not None:
        element = element.setName(name)

    if hideOnEmpty:
        element.setParseAction(actionHideOnEmpty)
        
    return element

stringEnd = buildRegex(r"(?!.)", "stringEnd")



def getFirstTerminalNode(t):
    if t.getChildrenCount() == 0:
        return None
    
    lt = t[-1]
    if not isinstance(lt, TerminalNode):
        return None
        
    return lt


def actionHideOnEmpty(s, l, st, t):
    if t.strLength == 0:
        return []


def actionCutRightWhitespace(s, l, st, t):
    lt = getFirstTerminalNode(t)
    if lt is None:
        return None

    txt = lt.getText()
    for i in range(len(txt) - 1, -1, -1):
        if txt[i] not in ("\t", " ", "\n", "\r"):
            if i < len(txt) - 1:
                lt.text = txt[:i+1]
                lt.recalcStrLength()
                
                t2 = buildSyntaxNode(txt[i+1:], lt.pos + i + 1)
                t.append(t2)
            return t

    return None

  
_CHECK_LEFT_RE = re.compile(r"[ \t]*$", RE_FLAGS)


def preActCheckNothingLeft(s, l, st, pe):
    # Technically we have to look behind, but this is not supported very
    # well by reg. ex., so we take the reverse string and look ahead
    revText = st.revText
    revLoc = len(s) - l
#     print "--preActCheckNothingLeft4", repr((revLoc, revText[revLoc: revLoc+20]))
    if not _CHECK_LEFT_RE.match(revText, revLoc):
        raise ParseException(s, l, "left of block markup (e.g. table) not empty")


def validateNonEmpty(s, l, st, t):
    if t.strLength == 0:
        raise ParseException(s, l, "matched token must not be empty")




def precTest(s, l, st, pe):
    print("--precTest", repr((l, st, type(pe))))



def createCheckNotIn(tokNames):
    tokNames = frozenset(tokNames)

    def checkNoContain(s, l, st, pe):
        for tn in tokNames:
            if tn in st.nameStack[:-1]:
#                 print "--notcontain exc", repr(st.nameStack[:-1]), tn
                raise ParseException(s, l, "token '%s' is not allowed here" % tn)

    return checkNoContain


def pseudoActionFindMarkup(s, l, st, t):
    if t.strLength == 0:
        return []
    t.name = "plainText"
    return t





# Forward definition of normal content and content in table cells, headings, ...
content = Forward()
oneLineContent = Forward()

tableContentInCell = Forward()   # .setResultsNameNoCopy("tableCell")
headingContent = Forward().setResultsNameNoCopy("headingContent")
todoContent = Forward().setResultsNameNoCopy("value")
titleContent = Forward().setResultsNameNoCopy("title")
characterAttributionContent = Forward()

whitespace = buildRegex(r"[ \t]*")
whitespace = whitespace.setParseAction(actionHideOnEmpty)


# The mode appendix for URLs and tables
def actionModeAppendix(s, l, st, t):
    entries = []

    for entry in t.iterFlatByName("entry"):
        key = entry.findFlatByName("key").getText()
        if key.endswith(":") or key.endswith("="):
            key = key[:-1]

        data = entry.findFlatByName("data").getText()
        entries.append((key, data))
        
    t.entries = entries
    return t



modeAppendixEntry = buildRegex(r"(?:(?![;\|\]=:])\S)+[=:]|(?![;\|\]=:])\S",
        "key") + buildRegex(r"(?:(?![;\|\]])\S)*", "data")
modeAppendixEntry = modeAppendixEntry.setResultsNameNoCopy("entry")
modeAppendix = modeAppendixEntry + ZeroOrMore(buildRegex(r";") + modeAppendixEntry)
modeAppendix = modeAppendix.addParseAction(actionModeAppendix)




# -------------------- Simple formatting --------------------

EscapePlainCharPAT = r"\\"


escapedChar = buildRegex(EscapePlainCharPAT) + buildRegex(r".", "plainText")

italicsStart = buildRegex(r"\b_")
italicsStart = italicsStart.setParseStartAction(createCheckNotIn(("italics",)))

italicsEnd = buildRegex(r"_\b")

italics = italicsStart + characterAttributionContent + italicsEnd
italics = italics.setResultsNameNoCopy("italics").setName("italics")

boldStart = buildRegex(r"\*(?=\S)")
boldStart = boldStart.setParseStartAction(createCheckNotIn(("bold",)))

boldEnd = buildRegex(r"\*")

bold = boldStart + characterAttributionContent + boldEnd
bold = bold.setResultsNameNoCopy("bold").setName("bold")


script = buildRegex(r"<%") + buildRegex(r".*?(?=%>)", "code") + \
        buildRegex(r"%>")
script = script.setResultsNameNoCopy("script")

horizontalLine = buildRegex(r"----+[ \t]*$", "horizontalLine")\
        .setParseStartAction(preActCheckNothingLeft)


# -------------------- HTML --------------------

htmlTag = buildRegex(r"</?[A-Za-z][A-Za-z0-9:]*(?:/| [^\n>]*)?>", "htmlTag")

htmlEntity = buildRegex(
        r"&(?:[A-Za-z0-9]{2,10}|#[0-9]{1,10}|#x[0-9a-fA-F]{1,8});",
        "htmlEntity")



# -------------------- Heading --------------------

def actionHeading(s, l, st, t):
    t.level = len(t[0].getText())
    t.contentNode = t.findFlatByName("headingContent")
    if t.contentNode is None:
        raise ParseException(s, l, "a heading needs content")

headingEnd = buildRegex(r"\n")

heading = buildRegex(r"^\+{1,15}(?!\+)") + Optional(buildRegex(r" ")) + \
        headingContent + headingEnd
heading = heading.setResultsNameNoCopy("heading").setParseAction(actionHeading)



# -------------------- Todo-Entry --------------------

def actionTodoEntry(s, l, st, t):
    t.key = t.findFlatByName("key").getString()
    t.keyComponents = t.key.split(".")
    t.delimiter = t.findFlatByName("todoDelimiter").getString()
    t.valueNode = t.findFlatByName("value")
    t.todos = [(t.key, t.valueNode)]



todoKey = buildRegex(r"\b(?:todo|done|wait|action|track|issue|"
        r"question|project)(?:\.[^:\s]+)?", "key")
# todoKey = todoKey.setParseStartAction(preActCheckNothingLeft)

todoEnd = buildRegex(r"\n|\||(?!.)")

todoEntry = todoKey + buildRegex(r":", "todoDelimiter") + todoContent

todoEntry = todoEntry.setResultsNameNoCopy("todoEntry")\
        .setParseAction(actionTodoEntry)
        
todoEntryWithTermination = todoEntry + Optional(buildRegex(r"\|"))

# Only for LanguageHelper.parseTodoEntry()
todoAsWhole = todoEntry + stringEnd

# -------------------- Indented text, (un)ordered list --------------------

def validateLessIndent(s, l, st, t):
    if t.strLength >= st.dictStack["indentInfo"].level:
        raise ParseException(s, l, "expected less indentation")


def validateMoreIndent(s, l, st, t):
    if t.strLength <= st.dictStack["indentInfo"].level:
        raise ParseException(s, l, "expected more indentation")


def validateEqualIndent(s, l, st, t):
    if t.strLength > st.dictStack["indentInfo"].level:
        raise ParseException(s, l, "expected equal indentation, but more found")
    if t.strLength < st.dictStack["indentInfo"].level:
        raise ParseException(s, l, "expected equal indentation, but less found")


def validateEquivalIndent(s, l, st, t):
    if t.strLength > st.dictStack["indentInfo"].level and \
            st.dictStack["indentInfo"].type == "normal":
        raise ParseException(s, l, "expected equival. indentation, but more found")
    if t.strLength < st.dictStack["indentInfo"].level:
        raise ParseException(s, l, "expected equival. indentation, but less found")


def validateInmostIndentNormal(s, l, st, t):
    if st.dictStack["indentInfo"].type != "normal":
        raise ParseException(s, l, 'Inmost indentation not "normal"')


def actionResetIndent(s, l, st, t):
    st.dictStack.getSubTopDict()["lastIdentation"] = 0


def actionIndent(s, l, st, t):
    st.dictStack.getSubTopDict()["lastIdentation"] = t.strLength


def actionListStartIndent(s, l, st, t):
    if t.strLength <= st.dictStack["indentInfo"].level:
        raise ParseException(s, l, "expected list start indentation, but less or equal found")

    return actionIndent(s, l, st, t)


def actionMoreIndent(s, l, st, t):
    """
    Called for more indentation before a general indented text.
    """
    newIdInfo = IndentInfo("normal")
    
    result = actionIndent(s, l, st, t)

    newIdInfo.level = st.dictStack.getSubTopDict().get("lastIdentation", 0)
    st.dictStack.getSubTopDict()["indentInfo"] = newIdInfo
    
    return result



def preActNewLinesParagraph(s, l, st, pe):
    if "preHtmlTag" in st.nameStack:
        raise ParseException(s, l, "Newlines aren't paragraph inside <pre> tag")
    
    wikiFormatDetails = st.dictStack["wikiFormatDetails"]
    if not wikiFormatDetails.paragraphMode:
        raise ParseException(s, l, "Newlines are only paragraph in paragraph mode")


def preActNewLineLineBreak(s, l, st, pe):
    if "preHtmlTag" in st.nameStack:
        raise ParseException(s, l, "Newline isn't line break inside <pre> tag")
    
    wikiFormatDetails = st.dictStack["wikiFormatDetails"]
    if wikiFormatDetails.paragraphMode:
        raise ParseException(s, l, "Newline isn't line break in paragraph mode")


def preActNewLineWhitespace(s, l, st, pe):
    if "preHtmlTag" in st.nameStack:
        raise ParseException(s, l, "Newline isn't whitespace inside <pre> tag")
    
    wikiFormatDetails = st.dictStack["wikiFormatDetails"]
    if not wikiFormatDetails.paragraphMode:
        raise ParseException(s, l, "Newline is only whitespace in paragraph mode")

def preActEscapedNewLine(s, l, st, pe):
    if "preHtmlTag" in st.nameStack:
        raise ParseException(s, l, "Escaped Newline isn't line break inside <pre> tag")




def preActUlPrepareStack(s, l, st, pe):
#     oldIdInfo = st.dictStack.getSubTopDict().get("indentInfo")
    newIdInfo = IndentInfo("ul")

    newIdInfo.level = st.dictStack.get("lastIdentation", 0)
    st.dictStack["indentInfo"] = newIdInfo

def preActOlPrepareStack(s, l, st, pe):
#     oldIdInfo = st.dictStack.getSubTopDict().get("indentInfo")
    newIdInfo = IndentInfo("ol")

    newIdInfo.level = st.dictStack.get("lastIdentation", 0)
    st.dictStack["indentInfo"] = newIdInfo



def inmostIndentChecker(typ):
    def startAction(s, l, st, pe):
        if st.dictStack["indentInfo"].type != typ:
            raise ParseException(s, l, 'Expected inmost indent type "%s"' % typ)

    return startAction



# Only an empty line
fakeIndentation = buildRegex(r"^[ \t]+$")

newLine = buildRegex(r"\n") + Optional(fakeIndentation)



newLinesParagraph = newLine + OneOrMore(newLine)
newLinesParagraph = newLinesParagraph.setResultsNameNoCopy("newParagraph")\
        .setParseStartAction(preActNewLinesParagraph)\
        .setParseAction(actionResetIndent)


newLineLineBreak = newLine
newLineLineBreak = newLineLineBreak.setResultsName("lineBreak")\
        .setParseStartAction(preActNewLineLineBreak)\
        .setParseAction(actionResetIndent)


newLineWhitespace = newLine
newLineWhitespace = newLineWhitespace.setResultsName("whitespace")\
        .setParseStartAction(preActNewLineWhitespace)


escapedNewLine = buildRegex(EscapePlainCharPAT + "\n", "lineBreak")\
        .setParseStartAction(preActEscapedNewLine)


moreIndentation = buildRegex(r"^[ \t]*(?!\n)").setValidateAction(validateMoreIndent)
moreIndentation = moreIndentation.setParseStartAction(validateInmostIndentNormal).\
        setParseAction(actionMoreIndent).setName("moreIndentation")

equalIndentation = buildRegex(r"^[ \t]*(?!\n)").setValidateAction(validateEqualIndent)
equalIndentation = equalIndentation.setParseAction(actionIndent).\
        setName("equalIndentation")

lessIndentation = buildRegex(r"^[ \t]*(?!\n)").setValidateAction(validateLessIndent)
lessIndentation = lessIndentation.setParseAction(actionIndent).\
        setName("lessIndentation")

lessIndentOrEnd = stringEnd | lessIndentation
lessIndentOrEnd = lessIndentOrEnd.setName("lessIndentOrEnd")


equivalIndentation = buildRegex(r"^[ \t]+(?!\n)").setValidateAction(validateEquivalIndent)
equivalIndentation = equivalIndentation.setParseAction(actionIndent).\
        setName("equivalIndentation")


indentedText = moreIndentation + content + FollowedBy(lessIndentOrEnd)
indentedText = indentedText.setResultsNameNoCopy("indentedText")


listStartIndentation  = buildRegex(r"^[ \t]*")
listStartIndentation = listStartIndentation.\
        setParseAction(actionListStartIndent).setName("listStartIndentation")



bulletFirst = buildRegex(r"\*[ \t]", "bullet", name="bulletFirst")
bulletEntryFirst = bulletFirst + content
bulletEntryFirst = bulletEntryFirst.setResultsNameNoCopy("bulletEntry")\
        .setName("bulletEntryFirst")


bullet = equalIndentation.copy()\
            .addParseStartAction(inmostIndentChecker("ul")) + \
            buildRegex(r"\*[ \t]", "bullet")

bulletEntry = bullet + content
bulletEntry = bulletEntry.setResultsNameNoCopy("bulletEntry")


unorderedList = listStartIndentation + (bulletEntryFirst + ZeroOrMore(bulletEntry) + \
        FollowedBy(lessIndentOrEnd))\
        .addParseStartAction(preActUlPrepareStack)
unorderedList = unorderedList.setResultsNameNoCopy("unorderedList")


numberFirst = buildRegex(r"(?:\d+\.)*(\d+)\.[ \t]|#[ \t]", "number",
        name="numberFirst")
numberEntryFirst = numberFirst + content
numberEntryFirst = numberEntryFirst.setResultsNameNoCopy("numberEntry")\
        .setName("numberEntryFirst")


number = equalIndentation.copy()\
            .addParseStartAction(inmostIndentChecker("ol")) + \
            buildRegex(r"(?:\d+\.)*(\d+)\.[ \t]|#[ \t]", "number")

numberEntry = number + content
numberEntry = numberEntry.setResultsNameNoCopy("numberEntry")


orderedList = listStartIndentation + (numberEntryFirst + ZeroOrMore(numberEntry) + \
        FollowedBy(lessIndentOrEnd))\
        .addParseStartAction(preActOlPrepareStack)
orderedList = orderedList.setResultsNameNoCopy("orderedList")




# -------------------- Table --------------------


tableEnd = buildRegex(r"^[ \t]*>>[ \t]*(?:\n|$)")
newRow = buildRegex(r"\n")

newCellBar = buildRegex(r"\|")
newCellTab = buildRegex(r"\t")


def chooseCellEnd(s, l, st, pe):
    """
    """
    if st.dictStack.get("table.tabSeparated", False):
        return newCellTab
    else:
        return newCellBar


newCell = Choice([newCellBar, newCellTab], chooseCellEnd)

uselessSpaces = buildRegex(r" *")
uselessSpaces = uselessSpaces.setParseAction(actionHideOnEmpty)


def chooseTableCellWhitespace(s, l, st, pe):
    if st.dictStack.get("table.tabSeparated", False):
        return uselessSpaces
    else:
        return whitespace


tableCellWhitespace = Choice([whitespace, uselessSpaces],
        chooseTableCellWhitespace)


# Table cells can have their own appendix (started by ;) allowing for advanced
# formating

def parseGlobalAppendixEntries(s, l, st, t, ignore=()):
    """
    Handles the global appendix attributes that can be set for any
    item that supports appendices
    """
    t.cssClass = None
    t.text_align = None
#     t.width = None
#     t.height = None

    for key, data in t.entries:
        # Skip keys that have been redefined in the calling appendix
        if key in ignore:
            continue

        # CSS classes are designated by "s" or "class". They will result in the
        # css class(es) being applied to the element. Multiple classes can be
        # separated by comma (,)
        # E. g. "s=foo" uses class "foo". The '=' can be omitted for the
        # short form "s", therefore "sfoo" does the same. The same is also:
        # "class=foo", "s:foo" and "class:foo".
        
        # The longer form is recommended, the short "s" e.g. does not work
        # in appendices for image URLs due to a name clash
        if key == "s" or key == "class":
            t.cssClass = data.replace(",", " ")
        elif key == "A" or key == "align":
            if data in ("l", "c", "r", "left", "center", "right"):
                t.text_align = data
        # Element width can be specified by the "w" key. If the entry ends in
        # px or % it will be used directly, otherwise size is assumed to be in
        # pixels.
#         elif key == "w":
#             t.width = getSizeFromEntry(data)
#         elif key == "h":
#             t.height = getSizeFromEntry(data)

    return s, l, st, t


def actionTableCellAppendix(s, l, st, t):
    s, l, st, t = parseGlobalAppendixEntries(s, l, st, t)

tableCellAppendix = buildRegex(r";") + modeAppendixEntry + \
        ZeroOrMore(buildRegex(r";") + modeAppendixEntry)
tableCellAppendix = tableCellAppendix.addParseAction(actionModeAppendix)

tableCellAppendix = tableCellAppendix.setResultsName("tableCellAppendix")\
        .addParseAction(actionTableCellAppendix)


tableCellContinuationUp = buildRegex(r"\^")  + tableCellWhitespace + \
        FollowedBy(newCell | newRow)
tableCellContinuationUp = tableCellContinuationUp.setResultsNameNoCopy(
        "tableCellContinuationUp")

tableCellContinuationLeft = buildRegex(r"<")  + tableCellWhitespace + \
        FollowedBy(newCell | newRow)
tableCellContinuationLeft = tableCellContinuationLeft.setResultsNameNoCopy(
        "tableCellContinuationLeft")


tableCell = tableCellWhitespace + MatchFirst([
        tableCellContinuationUp, 
        tableCellContinuationLeft,  
        Optional(tableCellAppendix) + tableContentInCell])
        
tableCell = tableCell.setResultsNameNoCopy("tableCell")

tableRow = tableCellWhitespace + tableCell + ZeroOrMore(newCell + tableCellWhitespace + tableCell)
tableRow = tableRow.setResultsNameNoCopy("tableRow").setParseAction(actionHideOnEmpty)


def actionTableModeAppendix(s, l, st, t):
    st.dictStack.getNamedDict("table")["table.tabSeparated"] = False
    
    s, l, st, t = parseGlobalAppendixEntries(s, l, st, t)
    
    t.border = None

    for key, data in t.entries:
        if key == "t":
            st.dictStack.getNamedDict("table")["table.tabSeparated"] = True
        elif key == "b":
            if data.endswith("px"):
                t.border = data
            else:
                t.border = "{0}px".format(data)





tableModeAppendix = modeAppendix.setResultsName("tableModeAppendix").addParseAction(actionTableModeAppendix)


table = buildRegex(r"<<\|").setParseStartAction(preActCheckNothingLeft) + \
        Optional(tableModeAppendix) + buildRegex(r"[ \t]*\n") + \
        tableRow + newRow + ZeroOrMore(NotAny(tableEnd) + tableRow + newRow) + \
        tableEnd
table = table.setResultsNameNoCopy("table")



# -------------------- Suppress highlighting and no export --------------------

suppressHighlightingMultipleLines = buildRegex(r"<<[ \t]*\n")\
        .setParseStartAction(preActCheckNothingLeft) + \
        buildRegex(r".*?(?=^[ \t]*>>[ \t]*(?:\n|$))", "plainText") + \
        buildRegex(r"^[ \t]*>>[ \t]*(?:\n|$)")

suppressHighlightingSingleLine = buildRegex(r"<<") + \
        buildRegex(r"[^\n]*?(?=>>)", "plainText") + buildRegex(r">>")

# suppressHighlighting = suppressHighlightingMultipleLines | suppressHighlightingSingleLine




# -------------------- No export area--------------------

def actionNoExport(s, l, st, t):
    # Change name to reduce work when interpreting
    t.name = "noExport"



noExportMultipleLinesEnd = buildRegex(r"^[ \t]*>>[ \t]*(?:\n|$)")
noExportSingleLineEnd = buildRegex(r">>")


noExportMultipleLines = buildRegex(r"<<hide[ \t]*\n")\
        .setParseStartAction(preActCheckNothingLeft,
        createCheckNotIn(("noExportMl", "noExportSl"))) + \
        content + noExportMultipleLinesEnd
noExportMultipleLines = noExportMultipleLines.setResultsNameNoCopy("noExportMl")\
        .setParseAction(actionNoExport)

noExportSingleLine = buildRegex(r"<<hide[ \t]") + oneLineContent + \
        noExportSingleLineEnd
noExportSingleLine = noExportSingleLine.setResultsNameNoCopy("noExportSl")\
        .setParseStartAction(
        createCheckNotIn(("noExportMl", "noExportSl")))\
        .setParseAction(actionNoExport)



# -------------------- Pre block --------------------

PRE_BLOCK_END = r"^[ \t]*>>[ \t]*(?:\n|$)"

preBlock = buildRegex(r"<<pre[ \t]*\n")\
        .setParseStartAction(preActCheckNothingLeft) + \
        buildRegex(r".*?(?=" + PRE_BLOCK_END + ")", "preText") + \
        buildRegex(PRE_BLOCK_END)
preBlock = preBlock.setResultsNameNoCopy("preBlock")


# -------------------- <body> html tag --------------------

def actionBodyHtmlTag(s, l, st, t):
    t.content = t.findFlatByName("bodyHtmlText").getString()


bodyHtmlStart = buildRegex(r"<body(?: [^\n>]*)?>", "htmlTag")
 
bodyHtmlEnd = buildRegex(r"</body>", "htmlTag")

bodyHtmlText = buildRegex(r".*?(?=" + bodyHtmlEnd.getPattern() + ")",
        "bodyHtmlText")


bodyHtmlTag = bodyHtmlStart + bodyHtmlText + bodyHtmlEnd
bodyHtmlTag = bodyHtmlTag.setResultsNameNoCopy("bodyHtmlTag")\
        .setParseAction(actionBodyHtmlTag)


# -------------------- Auto generated area --------------------
# TODO

# autoGeneratedArea = buildRegex(r"<<[ \t]+")\
#         .setParseStartAction(preActCheckNothingLeft) + \
#         buildRegex(r"[^\n]+", "expression") + \
#         buildRegex(r"\n") + buildRegex(r".*?(?=>>)", "plainText") + \
#         buildRegex(r">>[ \t]*$").setParseStartAction(preActCheckNothingLeft)




# -------------------- <pre> html tag --------------------

def actionPreHtmlTag(s, l, st, t):
    """
    Remove the node name so this doesn't become an own NTNode.
    """
    t.name = None



preHtmlStart = buildRegex(r"<pre(?: [^\n>]*)?>", "htmlTag")\
        .setParseStartAction(createCheckNotIn(("preHtmlTag",)))

preHtmlEnd = buildRegex(r"</pre(?: [^\n>]*)?>", "htmlTag")

preHtmlTag = preHtmlStart + content + preHtmlEnd
preHtmlTag = preHtmlTag.setResultsNameNoCopy("preHtmlTag")\
        .setParseAction(actionPreHtmlTag)



# -------------------- Wikiwords and URLs --------------------

BracketStart = "["
BracketStartPAT = r"\["

BracketEnd = "]"
BracketEndPAT = r"\]"
# WikiWordNccPAT = r"/?(?:/?[^\\/\[\]\|\000-\037=:;#!]+)+" # r"[\w\-\_ \t]+"

# Single part of subpage path
WikiWordPathPartPAT = r"(?!\.\.)[^\\/\[\]\|\000-\037=:;#!]+"
WikiPageNamePAT = WikiWordPathPartPAT + "(?:/" + WikiWordPathPartPAT + ")*"

# Begins with dotted path parts which mean to go upward in subpage path
WikiWordDottedPathPAT = r"\.\.(?:/\.\.)*(?:/" + WikiWordPathPartPAT + ")*"
WikiWordNonDottedPathPAT = r"/{0,2}" + WikiPageNamePAT

WikiWordNccPAT = WikiWordDottedPathPAT + r"|" + WikiWordNonDottedPathPAT

WikiWordTitleStartPAT = r"\|"
WikiWordAnchorStart = "!"
WikiWordAnchorStartPAT = r"!"

# Bracket start, escaped for reverse RE pattern (for autocompletion)
BracketStartRevPAT = r"\["
# Bracket end, escaped for reverse RE pattern (for autocompletion)
BracketEndRevPAT = r"\]"

WikiWordNccRevPAT = r"[^\\\[\]\|\000-\037=:;#!]+?"  # r"[\w\-\_ \t.]+?"



WikiWordCcPAT = (r"(?:[" +
        UPPERCASE +
        r"]+[" +
        LOWERCASE +
        r"]+[" +
        UPPERCASE +
        r"]+[" +
        LETTERS + string.digits +
        r"]*|[" +
        UPPERCASE +
        r"]{2,}[" +
        LOWERCASE +
        r"]+)")


UrlPAT = r'(?:(?:https?|ftp|rel|wikirel)://|mailto:|Outlook:\S|wiki:/|file:/)'\
        r'(?:(?![.,;:!?)]+(?:["\s]|$))[^"\s|\]<>])*'


UrlInBracketsPAT = r'(?:(?:https?|ftp|rel|wikirel)://|mailto:|Outlook:\S|wiki:/|file:/)'\
        r'(?:(?![ \t]+[|\]])(?: |[^"\s|\]<>]))*'


bracketStart = buildRegex(BracketStartPAT)
bracketEnd = buildRegex(BracketEndPAT)


UnescapeExternalFragmentRE   = re.compile(r"#(.)",
                              re.DOTALL | re.UNICODE | re.MULTILINE)


def reThrough(matchobj):
    return matchobj.group(1)


def actionSearchFragmentExtern(s, l, st, t):
    """
    Called to unescape external fragment of wikiword.
    """
    lt2 = getFirstTerminalNode(t)
    if lt2 is None:
        return None
    
    lt2.unescaped = UnescapeExternalFragmentRE.sub(r"\1", lt2.text)


UnescapeStandardRE = re.compile(EscapePlainCharPAT + r"(.)",
                              re.DOTALL | re.UNICODE | re.MULTILINE)

def actionSearchFragmentIntern(s, l, st, t):
    lt2 = getFirstTerminalNode(t)
    if lt2 is None:
        return None

    lt2.unescaped = UnescapeStandardRE.sub(r"\1", lt2.text)



def resolveWikiWordLink(linkCore, basePage):
    """
    Return page name (absolute link).

    If using subpages this is used to resolve a link to the right
    wiki word relative to basePage on which the link is placed.
    """
    return _TheHelper.resolvePrefixSilenceAndWikiWordLink(linkCore, basePage)[2]
   



def actionWikiWordNcc(s, l, st, t):
    t.wikiWord = t.findFlatByName("word")
    wikiFormatDetails = st.dictStack["wikiFormatDetails"]

    link = t.wikiWord.getString() if t.wikiWord is not None else '.'
    # store path in node attribute, because that way we know in
    # the text generator if the link was absolute or relative, and
    # generate the correct link text with .getLinkCore()
    t.linkPath = _WikiLinkPath(linkCore=link)

    try:
        t.wikiWord = resolveWikiWordLink(link, wikiFormatDetails.basePage)
    except ValueError:
        raise ParseException(s, l, "Subpage resolution of wikiword failed")

    if t.wikiWord in wikiFormatDetails.wikiDocument.getNccWordBlacklist():
        raise ParseException(s, l, "Non-CamelCase word is in blacklist")

    # Format type is used for TextFormatter to better reconstruct content
    t.formatType = "ncc"

    t.titleNode = t.findFlatByName("title")

    t.fragmentNode = t.findFlatByName("searchFragment")
    if t.fragmentNode is not None:
        t.searchFragment = t.fragmentNode.unescaped
    else:
        t.searchFragment = None
    
    t.anchorLink = t.findFlatByName("anchorLink")
    if t.anchorLink is not None:
        t.anchorLink = t.anchorLink.getString()



def preActCheckWikiWordCcAllowed(s, l, st, pe):
    try:
        wikiFormatDetails = st.dictStack["wikiFormatDetails"]
        
        if not wikiFormatDetails.withCamelCase:
            raise ParseException(s, l, "CamelCase words not allowed here")
    except KeyError:
        pass


def actionWikiWordCc(s, l, st, t):
    t.wikiWord = t.findFlatByName("word")
    if t.wikiWord is not None:
        wikiFormatDetails = st.dictStack["wikiFormatDetails"]

        link = t.wikiWord.getString()
        t.linkPath = _WikiLinkPath(linkCore=link)

        try:
            t.wikiWord = resolveWikiWordLink(link, wikiFormatDetails.basePage)
        except ValueError:
            raise ParseException(s, l, "Subpage resolution of wikiword failed")

        try:
            if t.wikiWord in wikiFormatDetails.wikiDocument.getCcWordBlacklist():
                raise ParseException(s, l, "CamelCase word is in blacklist")
        except KeyError:
            pass

    # Format type is used for TextFormatter to better reconstruct content
    t.formatType = "cc"

    t.titleNode = None

    t.fragmentNode = t.findFlatByName("searchFragment")
    if t.fragmentNode is not None:
        t.searchFragment = t.fragmentNode.unescaped
    else:
        t.searchFragment = None

    t.anchorLink = t.findFlatByName("anchorLink")
    if t.anchorLink is not None:
        t.anchorLink = t.anchorLink.getString()





def actionExtractableWikiWord(s, l, st, t):
    t.wikiWord = t.findFlatByName("word")
    if t.wikiWord is not None:
        t.wikiWord = t.wikiWord.getString()



def actionUrlLink(s, l, st, t):
    if t.name == "urlLinkBare":
        t.bracketed = False
    else:
        t.bracketed = True
    
    t.name = "urlLink"        
    t.appendixNode = t.findFlatByName("urlModeAppendix")
    t.coreNode = t.findFlatByName("url")

    # Valid URL but may differ from original input
    t.url = StringOps.urlQuoteSpecific(t.coreNode.getString(), ' ')
    t.titleNode = t.findFlatByName("title")
#     print "--actionUrlLink3", repr(t.url)


def actionAnchorDef(s, l, st, t):
    t.anchorLink = t.findFlatByName("anchor").getString()


def actionUrlModeAppendix(s, l, st, t):
    s, l, st, t = parseGlobalAppendixEntries(s, l, st, t, ignore=("s",))
    
#     t.border = None
# 
#     for key, data in t.entries:
#         if key == "b":
#             if data.endswith("px"):
#                 t.border = data
#             else:
#                 t.border = "{0}px".format(data)




searchFragmentExtern = buildRegex(r"#") + \
        buildRegex(r"(?:(?:#.)|[^ \t\n#])+", "searchFragment")\
        .setParseAction(actionSearchFragmentExtern)

searchFragmentIntern = buildRegex(r"#") + buildRegex(r"(?:(?:" + EscapePlainCharPAT +
        r".)|(?!" + WikiWordTitleStartPAT +
        r"|" +  BracketEndPAT + r").)+", "searchFragment")\
        .setParseAction(actionSearchFragmentIntern)

wikiWordAnchorLink = buildRegex(WikiWordAnchorStartPAT) + \
        buildRegex(r"[A-Za-z0-9\_]+", "anchorLink")


title = buildRegex(WikiWordTitleStartPAT + r"[ \t]*") + titleContent    # content.setResultsName("title")


wikiWordNccCore = buildRegex(WikiWordNccPAT, "word")

wikiWordNcc = bracketStart + \
        wikiWordNccCore.copy().addParseAction(actionCutRightWhitespace) + \
        Optional(MatchFirst([searchFragmentIntern, wikiWordAnchorLink])) + whitespace + \
        Optional(title) + bracketEnd + \
        Optional(MatchFirst([searchFragmentExtern, wikiWordAnchorLink]))

wikiWordNcc = wikiWordNcc.setResultsNameNoCopy("wikiWord").setName("wikiWordNcc")\
        .setParseAction(actionWikiWordNcc)


anchorDef = buildRegex(r"^[ \t]*anchor:[ \t]*") + buildRegex(r"[A-Za-z0-9\_]+",
        "anchor") + buildRegex(r"\n")
anchorDef = anchorDef.setResultsNameNoCopy("anchorDef").setParseAction(actionAnchorDef)


AnchorRE = re.compile(r"^[ \t]*anchor:[ \t]*(?P<anchorValue>[A-Za-z0-9\_]+)\n",
        re.DOTALL | re.UNICODE | re.MULTILINE)



urlModeAppendix = modeAppendix.setResultsName("urlModeAppendix").addParseAction(
        actionUrlModeAppendix)

urlWithAppend = buildRegex(UrlPAT, "url") + Optional(buildRegex(r">") + \
        urlModeAppendix)

urlWithAppendInBrackets = buildRegex(UrlInBracketsPAT, "url") + Optional(buildRegex(r">") + \
        urlModeAppendix)


urlBare = urlWithAppend.setResultsName("urlLinkBare")
urlBare = urlBare.setParseAction(actionUrlLink)

urlTitled = bracketStart + urlWithAppendInBrackets + whitespace + \
        Optional(title) + bracketEnd
# urlTitled = bracketStart + urlWithAppend + whitespace + \
#         Optional(title) + bracketEnd
urlTitled = urlTitled.setResultsNameNoCopy("urlLinkBracketed").setParseAction(actionUrlLink)



urlRef = urlTitled | urlBare


# TODO anchor/fragment
wikiWordCc = buildRegex(r"\b(?<!~)" + WikiWordCcPAT + r"\b", "word") + \
        Optional(MatchFirst([searchFragmentExtern, wikiWordAnchorLink])) # Group( )
wikiWordCc = wikiWordCc.setResultsNameNoCopy("wikiWord").setName("wikiWordCc")\
        .setParseStartAction(preActCheckWikiWordCcAllowed)\
        .setParseAction(actionWikiWordCc)

wikiWord = wikiWordNcc | wikiWordCc



# Needed for _TheHelper.extractWikiWordFromLink()

extractableWikiWord = (wikiWordNccCore | wikiWordNcc) + stringEnd
extractableWikiWord = extractableWikiWord.setResultsNameNoCopy("extractableWikiWord")\
        .setParseAction(actionExtractableWikiWord).optimize(("regexcombine",))\
        .parseWithTabs()


wikiPageNameRE = re.compile(r"^" + WikiPageNamePAT + r"$",
        re.DOTALL | re.UNICODE | re.MULTILINE)


wikiWordCcRE = re.compile(r"^" + WikiWordCcPAT + r"$",
        re.DOTALL | re.UNICODE | re.MULTILINE)

def isCcWikiWord(word):
    return bool(wikiWordCcRE.match(word))


wikiLinkCoreRE = re.compile(r"^" + WikiWordNccPAT + r"$",
        re.DOTALL | re.UNICODE | re.MULTILINE)



# -------------------- Footnotes --------------------

footnotePAT = r"[0-9]+"

def preActCheckFootnotesAllowed(s, l, st, pe):
    wikiFormatDetails = st.dictStack["wikiFormatDetails"]
    
    if wikiFormatDetails.wikiLanguageDetails.footnotesAsWws:
        raise ParseException(s, l, "CamelCase words not allowed here")


def actionFootnote(s, l, st, t):
    t.footnoteId = t.findFlatByName("footnoteId").getString()


footnote = bracketStart + buildRegex(footnotePAT, "footnoteId") + bracketEnd
footnote = footnote.setResultsNameNoCopy("footnote")\
        .setParseStartAction(preActCheckFootnotesAllowed)\
        .setParseAction(actionFootnote)


footnoteRE = re.compile(r"^" + footnotePAT + r"$",
        re.DOTALL | re.UNICODE | re.MULTILINE)


# -------------------- Attributes (=properties) and insertions --------------------


def actionAttrInsValueQuoteStart(s, l, st, t):
    st.dictStack.getSubTopDict()["attrInsValueQuote"] = t[0].text

def actionAttrInsValueQuoteEnd(s, l, st, t):
    if t[0].text != st.dictStack.getSubTopDict().get("attrInsValueQuote"):
        raise ParseException(s, l, "End quote of attribute/insertion does not match start")


def pseudoActionAttrInsQuotedValue(s, l, st, t):
    if t.strLength == 0:
        return []
    t.name = "value"
    return t


def actionAttribute(s, l, st, t):
    key = t.findFlatByName("key").getString()
    t.key = key
    t.keyComponents = t.key.split(".")
    t.attrs = [(key, vNode.getString()) for vNode in t.iterFlatByName("value")]


def actionInsertion(s, l, st, t):
    t.key = t.findFlatByName("key").getString()
    t.keyComponents = t.key.split(".")
    values = list(vNode.getString() for vNode in t.iterFlatByName("value"))
    t.value = values[0]
    del values[0]
    t.appendices = values



attrInsQuote = buildRegex(r"\"+|'+|/+|\\+")
attrInsQuoteStart = attrInsQuote.copy()\
        .setParseAction(actionAttrInsValueQuoteStart)
attrInsQuoteEnd = attrInsQuote.copy()\
        .setParseAction(actionAttrInsValueQuoteEnd)

attrInsQuotedValue = FindFirst([], attrInsQuoteEnd)\
        .setPseudoParseAction(pseudoActionAttrInsQuotedValue)

# attrInsNonQuotedValue = buildRegex(r"[\w\-\_ \t:,.!?#%|/]*", "value")
ATTR_INS_NON_QUOTED_VALUE_PATTERN = r"(?:[ \t]*[\w\-\_=:,.!?#%|/]+)*"
attrInsNonQuotedValue = buildRegex(ATTR_INS_NON_QUOTED_VALUE_PATTERN, "value")


attrInsValue = whitespace + ((attrInsQuoteStart + attrInsQuotedValue + \
        attrInsQuoteEnd) | attrInsNonQuotedValue)

attrInsKey = buildRegex(r"[\w\-\_\.]+", "key")

attribute = bracketStart + whitespace + attrInsKey + \
        buildRegex(r"[ \t]*[=:]") + attrInsValue + \
        ZeroOrMore(buildRegex(r";") + attrInsValue) + whitespace + bracketEnd
attribute = attribute.setResultsNameNoCopy("attribute").setParseAction(actionAttribute)


insertion = bracketStart + buildRegex(r":") + whitespace + attrInsKey + \
        buildRegex(r"[ \t]*[=:]") + attrInsValue + \
        ZeroOrMore(buildRegex(r";") + attrInsValue) + whitespace + bracketEnd
insertion = insertion.setResultsNameNoCopy("insertion").setParseAction(actionInsertion)



# -------------------- Additional regexes to provide --------------------


# Needed for auto-bullet/auto-unbullet functionality of editor
BulletRE        = re.compile(r"^(?P<indentBullet>[ \t]*)(?P<actualBullet>\*[ \t])",
        re.DOTALL | re.UNICODE | re.MULTILINE)
NumericSimpleBulletRE = re.compile(r"^(?P<indentBullet>[ \t]*)(?P<actualBullet>#[ \t])",
        re.DOTALL | re.UNICODE | re.MULTILINE)
NumericBulletRE = re.compile(r"^(?P<indentNumeric>[ \t]*)(?P<preLastNumeric>(?:\d+\.)*)(\d+)\.[ \t]",
        re.DOTALL | re.UNICODE | re.MULTILINE)


# Needed for handleRewrapText
EmptyLineRE     = re.compile(r"^[ \t\r\n]*$",
        re.DOTALL | re.UNICODE | re.MULTILINE)




# Reverse REs for autocompletion
revSingleWikiWord    =       (r"(?:[" +
                             LETTERS + string.digits +
                             r"]*[" +
                             UPPERCASE+
                             r"])")   # Needed for auto-completion

RevWikiWordRE      = re.compile(r"^" +
                             revSingleWikiWord + r"(?![\~])\b",
                             re.DOTALL | re.UNICODE | re.MULTILINE)
                             # Needed for auto-completion


RevWikiWordRE2     = re.compile(r"^" + WikiWordNccRevPAT + BracketStartRevPAT,
        re.DOTALL | re.UNICODE | re.MULTILINE)  # Needed for auto-completion

RevAttributeValue     = re.compile(
        r"^([\w\-\_ \t:;,.!?#/|]*?)([ \t]*[=:][ \t]*)([\w\-\_ \t\.]+?)" +
        BracketStartRevPAT,
        re.DOTALL | re.UNICODE | re.MULTILINE)  # Needed for auto-completion


RevTodoKeyRE = re.compile(r"^(?:[^:\s]{0,40}\.)??"
        r"(?:odot|enod|tiaw|noitca|kcart|eussi|noitseuq|tcejorp)",
        re.DOTALL | re.UNICODE | re.MULTILINE)  # Needed for auto-completion

RevTodoValueRE = re.compile(r"^[^\n:]{0,30}:" + RevTodoKeyRE.pattern[1:],
        re.DOTALL | re.UNICODE | re.MULTILINE)  # Needed for auto-completion


RevWikiWordAnchorRE = re.compile(r"^(?P<anchorBegin>[A-Za-z0-9\_]{0,20})" +
        WikiWordAnchorStartPAT + r"(?P<wikiWord>" + RevWikiWordRE.pattern[1:] + r")",
        re.DOTALL | re.UNICODE | re.MULTILINE)  # Needed for auto-completion
        
RevWikiWordAnchorRE2 = re.compile(r"^(?P<anchorBegin>[A-Za-z0-9\_]{0,20})" + 
        WikiWordAnchorStartPAT + BracketEndRevPAT + r"(?P<wikiWord>" + 
        WikiWordNccRevPAT + r")" + BracketStartRevPAT,
        re.DOTALL | re.UNICODE | re.MULTILINE)  # Needed for auto-completion


# Simple todo RE for autocompletion.
ToDoREWithCapturing = re.compile(r"^([^:\s]+):[ \t]*(.+?)$",
        re.DOTALL | re.UNICODE | re.MULTILINE)



# For auto-link mode relax
AutoLinkRelaxSplitRE = re.compile(r"[\W]+", re.IGNORECASE | re.UNICODE)

AutoLinkRelaxJoinPAT = r"[\W]+"
AutoLinkRelaxJoinFlags = re.IGNORECASE | re.UNICODE



# For spell checking
TextWordRE = re.compile(r"(?P<negative>[0-9]+|"+ UrlPAT + "|\b(?<!~)" +
        WikiWordCcPAT + r"\b)|\b[\w']+",
        re.DOTALL | re.UNICODE | re.MULTILINE)





# -------------------- End tokens --------------------


TOKEN_TO_END = {
        "bold": boldEnd,
        "italics": italicsEnd,
        "unorderedList": lessIndentOrEnd,
        "bulletEntry": (bullet | lessIndentOrEnd),
        "orderedList": lessIndentOrEnd,
        "numberEntry": (number | lessIndentOrEnd),
        "indentedText": lessIndentOrEnd,
        "wikiWord": bracketEnd,
        "urlLinkBracketed": bracketEnd,
        "table": tableEnd,
        "preHtmlTag": preHtmlEnd,
        "heading": headingEnd,
        "todoEntry": todoEnd,
        "noExportMl": noExportMultipleLinesEnd,
        "noExportSl": noExportSingleLineEnd
    }


def chooseEndToken(s, l, st, pe):
    """
    """
    for tokName in reversed(st.nameStack):
        end = TOKEN_TO_END.get(tokName)
        if end is not None:
            return end

    return stringEnd


endToken = Choice([stringEnd]+list(TOKEN_TO_END.values()), chooseEndToken)

endTokenInTable = endToken | newCell | newRow

endTokenInTitle = endToken | buildRegex(r"\n")

endTokenInCharacterAttribution = endToken | heading



# -------------------- Content definitions --------------------


findMarkupInCell = FindFirst([bold, italics, noExportSingleLine,
        suppressHighlightingSingleLine,
        urlRef, insertion, escapedNewLine, escapedChar, footnote, wikiWord,
        bodyHtmlTag, htmlTag, htmlEntity], endTokenInTable)
findMarkupInCell = findMarkupInCell.setPseudoParseAction(pseudoActionFindMarkup)

temp = ZeroOrMore(NotAny(endTokenInTable) + findMarkupInCell)
temp = temp.leaveWhitespace().parseWithTabs()
tableContentInCell << temp



findMarkupInTitle = FindFirst([bold, italics, noExportSingleLine,
        suppressHighlightingSingleLine,
        urlRef, insertion, escapedChar, footnote, bodyHtmlTag, htmlTag,
        htmlEntity],
        endTokenInTitle)
findMarkupInTitle = findMarkupInTitle.setPseudoParseAction(pseudoActionFindMarkup)

temp = ZeroOrMore(NotAny(endTokenInTitle) + findMarkupInTitle)
temp = temp.leaveWhitespace().parseWithTabs()
titleContent << temp



findMarkupInHeading = FindFirst([bold, italics, noExportSingleLine,
        suppressHighlightingSingleLine,
        urlRef, insertion, escapedChar, footnote, wikiWord, bodyHtmlTag,
        htmlTag, htmlEntity], endToken)
findMarkupInHeading = findMarkupInHeading.setPseudoParseAction(
        pseudoActionFindMarkup)

temp = ZeroOrMore(NotAny(endToken) + findMarkupInHeading)
temp = temp.leaveWhitespace().parseWithTabs()
headingContent << temp



findMarkupInTodo = FindFirst([bold, italics, noExportSingleLine,
        suppressHighlightingSingleLine,
        urlRef, attribute, insertion, escapedChar, footnote, wikiWord,
        bodyHtmlTag, htmlTag, htmlEntity], endToken)
findMarkupInTodo = findMarkupInTodo.setPseudoParseAction(
        pseudoActionFindMarkup)

temp = OneOrMore(NotAny(endToken) + findMarkupInTodo)
temp = temp.leaveWhitespace().parseWithTabs()
todoContent << temp
oneLineContent << temp



findMarkupInCharacterAttribution = FindFirst([bold, italics, noExportSingleLine,
        suppressHighlightingSingleLine, urlRef,
        attribute, insertion, footnote, wikiWord,
        newLinesParagraph, newLineLineBreak, newLineWhitespace,
        escapedNewLine, escapedChar,
        todoEntryWithTermination, anchorDef, preHtmlTag, bodyHtmlTag, htmlTag,
        htmlEntity, unorderedList, orderedList,
        indentedText, table, preBlock, noExportMultipleLines,
        suppressHighlightingMultipleLines, equivalIndentation],
        endTokenInCharacterAttribution)
findMarkupInCharacterAttribution = findMarkupInCharacterAttribution\
        .setPseudoParseAction(pseudoActionFindMarkup)

temp = ZeroOrMore(NotAny(endTokenInCharacterAttribution) +
        findMarkupInCharacterAttribution)
temp = temp.leaveWhitespace().parseWithTabs()
characterAttributionContent << temp



findMarkup = FindFirst([bold, italics, noExportSingleLine,
        suppressHighlightingSingleLine, urlRef,
        attribute, insertion, footnote, wikiWord,
        newLinesParagraph, newLineLineBreak, newLineWhitespace,
        escapedNewLine, escapedChar, heading,
        todoEntryWithTermination, anchorDef, preHtmlTag, bodyHtmlTag, htmlTag,
        htmlEntity, unorderedList, orderedList,
        indentedText, table, preBlock, noExportMultipleLines,
        suppressHighlightingMultipleLines,
        script, horizontalLine, equivalIndentation], endToken)
findMarkup = findMarkup.setPseudoParseAction(pseudoActionFindMarkup)


content << ZeroOrMore(NotAny(endToken) + findMarkup)  # .setResultsName("ZeroOrMore")
content = content.leaveWhitespace().setValidateAction(validateNonEmpty).parseWithTabs()



text = content + stringEnd


# Run optimizer

# Separate element for LanguageHelper.parseTodoEntry()
todoAsWhole = todoAsWhole.optimize(("regexcombine",)).parseWithTabs()

# Whole text, optimizes subelements recursively
text = text.optimize(("regexcombine",)).parseWithTabs()
# text = text.parseWithTabs()


# text.setDebugRecurs(True)



def _buildBaseDict(wikiDocument=None, formatDetails=None):
    if formatDetails is None:
        if wikiDocument is None:
            # Do import of WikiDocument here, i.e., only when we need it.
            # This way we can test the parser by loading only a handful
            # of WikiPad modules, see tests/
            from pwiki.WikiDocument import WikiDocument
            formatDetails = WikiDocument.getUserDefaultWikiPageFormatDetails()
            formatDetails.setWikiLanguageDetails(WikiLanguageDetails(None, None))
        else:
            formatDetails = wikiDocument.getWikiDefaultWikiPageFormatDetails()

    return {"indentInfo": IndentInfo("normal"),
            "wikiFormatDetails": formatDetails
        }



# -------------------- API for plugin WikiParser --------------------
# During beta state of the WikidPad version, this API isn't stable yet, 
# so changes may occur!


class _TheParser:
    @staticmethod
    def reset():
        """
        Reset possible internal states of a (non-thread-safe) object for
        later reuse.
        """
        pass

    @staticmethod
    def getWikiLanguageName():
        """
        Return the internal name of the wiki language implemented by this
        parser.
        """
        return WIKI_LANGUAGE_NAME



    @staticmethod
    def _postProcessing(intLanguageName, content, formatDetails, pageAst,
            threadstop):
        """
        Do some cleanup after main parsing.
        Not part of public API.
        """
        autoLinkRelaxRE = None
        if formatDetails.autoLinkMode == "relax":
            relaxList = formatDetails.wikiDocument.getAutoLinkRelaxInfo()

            def recursAutoLink(ast):
                newAstNodes = []
                for node in ast.getChildren():
                    if isinstance(node, NonTerminalNode):
                        newAstNodes.append(recursAutoLink(node))
                        continue
    
                    if node.name == "plainText":
                        text = node.text
                        start = node.pos
                        
                        threadstop.testValidThread()
                        while text != "":
                            # The foundWordText is the text as typed in the page
                            # foundWord is the word as entered in database
                            # These two may differ (esp. in whitespaces)
                            foundPos = len(text)
                            foundWord = None
                            foundWordText = None
                            
                            # Search all regexes for the earliest match
                            for regex, word in relaxList:
                                match = regex.search(text)
                                if match:
                                    pos = match.start(0)
                                    if pos < foundPos:
                                        # Match is earlier than previous
                                        foundPos = pos
                                        foundWord = word
                                        foundWordText = match.group(0)
                                        if pos == 0:
                                            # Can't find a better match -> stop loop
                                            break

                            # Add token for text before found word (if any)
                            preText = text[:foundPos]
                            if preText != "":
                                newAstNodes.append(buildSyntaxNode(preText,
                                        start, "plainText"))
                
                                start += len(preText)
                                text = text[len(preText):]
                            
                            if foundWord is not None:
                                wwNode = buildSyntaxNode(
                                        [buildSyntaxNode(foundWordText, start, "word")],
                                        start, "wikiWord")
                                        
                                wwNode.searchFragment = None
                                wwNode.anchorLink = None
                                wwNode.wikiWord = foundWord
                                wwNode.titleNode = buildSyntaxNode(foundWordText, start, "plainText") # None

                                newAstNodes.append(wwNode)

                                inc = max(len(foundWordText), 1)
                                start += inc
                                text = text[inc:]

                        continue

                    newAstNodes.append(node)


                ast.sub = newAstNodes
    
                return ast

            pageAst = recursAutoLink(pageAst)
        
        return pageAst

    @staticmethod
    def parse(intLanguageName, content, formatDetails, threadstop):
        """
        Parse the  content  written in wiki language  intLanguageName  using
        formatDetails  and regularly call  threadstop.testRunning()  to
        raise exception if execution thread is no longer current parsing
        thread.
        """

        if len(content) == 0:
            return buildSyntaxNode([], 0, "text")

        if formatDetails.noFormat:
            return buildSyntaxNode([buildSyntaxNode(content, 0, "plainText")],
                    0, "text")

        baseDict = _buildBaseDict(formatDetails=formatDetails)

##         _prof.start()
        try:
            t = text.parseString(content, parseAll=True, baseDict=baseDict,
                    threadstop=threadstop)
            t = buildSyntaxNode(t, 0, "text")

            t = _TheParser._postProcessing(intLanguageName, content, formatDetails,
                    t, threadstop)

        finally:
##             _prof.stop()
            pass

        return t

THE_PARSER = _TheParser()





class WikiLanguageDetails:
    """
    Stores state of wiki language specific options and allows to check if
    two option sets are equivalent.
    """
    __slots__ = ("__weakref__", "footnotesAsWws", "wikiDocument")

    def __init__(self, wikiDocument, docPage):
        self.wikiDocument = wikiDocument
        if self.wikiDocument is None:
            # Set wiki-independent default values
            self.footnotesAsWws = False
        else:
            self.footnotesAsWws = self.wikiDocument.getWikiConfig().getboolean(
                    "main", "footnotes_as_wikiwords", False)

    @staticmethod
    def getWikiLanguageName():
        return WIKI_LANGUAGE_NAME


    def isEquivTo(self, details):
        """
        Compares with other details object if both are "equivalent"
        """
        return self.getWikiLanguageName() == details.getWikiLanguageName() and \
                self.footnotesAsWws == details.footnotesAsWws


class _WikiLinkPath:
    __slots__ = ("upwardCount", "components")

    def __init__(self, linkCore=None, pageName=None,
                 upwardCount=-1, components=None):
        if linkCore is not None and pageName is not None:
            raise ValueError("linkCore and pageName can't be both specified.")

        if pageName is None and linkCore is None:
            self.upwardCount = upwardCount
            self.components = [] if components is None else components
            if self.upwardCount == -1 and len(self.components) == 0:
                raise ValueError("'//' is not a valid link.")
            return

        if pageName is not None:
            # Handle wiki word as absolute link
            self.upwardCount = -1
            self.components = pageName.split("/")
            return

        assert linkCore is not None

        if linkCore == "//":
            raise ValueError("'//' is not a valid link.")

        if linkCore.endswith("/"):
            raise ValueError("linkCore can not end with '/'.")

        if linkCore == "":
            raise ValueError("linkCore can not be empty.")

        if linkCore.startswith("//"):
            self.upwardCount = -1
            self.components = linkCore[2:].split("/")
            return
        
        if linkCore.startswith("/"):
            self.upwardCount = 0
            self.components = linkCore[1:].split("/")
            return

        if linkCore == ".":  # link to self
            self.upwardCount = 0
            self.components = []
            return

        components = linkCore.split("/")

        for i, component in enumerate(components):
            if component != "..":
                self.upwardCount = i + 1
                self.components = components[i:]
                return
        else:
            self.upwardCount = len(components)
            self.components = []

    def clone(self):
        return _WikiLinkPath(upwardCount=self.upwardCount,
                components=self.components[:])

    def __repr__(self):
        return "_WikiLinkPath(upwardCount=%i, components=%s)" % \
                (self.upwardCount, repr(self.components))

    def isAbsolute(self):
        return self.upwardCount == -1
        
    def join(self, other):
        if other.upwardCount == -1:
            self.upwardCount = -1
            self.components = other.components[:]

        elif other.upwardCount == 0:
            self.components = self.components + other.components

        else:
            if other.upwardCount <= len(self.components):
                self.components = (self.components[:-other.upwardCount] +
                                   other.components)
                if self.upwardCount == -1 and len(self.components) == 0:
                    raise ValueError('Not possible to go to root.')
            else:
                # Going back further than self was deep (eliminating
                # more components than self had)

                if self.upwardCount == -1:
                    raise ValueError('Can not go upward from root.')
                else:
                    # Add up upwardCount of other path after subtracting
                    # number of own components because otherPath walked
                    # over them already
                    self.upwardCount += (other.upwardCount -
                                         len(self.components))
                    self.components = other.components[:]

    def getLinkCore(self):
        if self.upwardCount == -1:
            assert len(self.components) > 0
            return '//' + '/'.join(self.components)
        elif self.upwardCount == 0:
            if len(self.components) == 0:
                return '.'
            else:
                return '/' + '/'.join(self.components)
        elif self.upwardCount >= 1:
            if not self.components:
                return '/'.join(['..'] * self.upwardCount)
            else:
                prefix = '/'.join(['..'] * (self.upwardCount - 1))
                if prefix:
                    prefix += '/'
                return prefix + '/'.join(self.components)

    def resolveWikiWord(self, basePath=None):
        """
        Return page name.
        """
        if self.isAbsolute():
            # Absolute is checked separately so basePath can be None if
            # self is absolute
            return "/".join(self.components)

        assert basePath is not None
        absPath = basePath.joinTo(self)
        return "/".join(absPath.components)

    def resolvePrefixSilenceAndWikiWordLink(self, basePath):
        """
        Return tuple (prefix, silence, pageName).

        If using subpages this is used to resolve a link to the right
        wiki word for autocompletion.

        Autocompletion now searches for all wiki words starting with
        `pageName`. For all found items it removes the first `silence`
        characters, prepends the `prefix` instead and uses the result
        as suggestion for autocompletion.

        If `prefix` is None autocompletion is not possible.
        """
        if self.isAbsolute():
            return "//", 0, self.resolveWikiWord(None)

        assert basePath.isAbsolute()
        
        if len(self.components) == 0:
            # link path only consists of ".." -> autocompletion not possible
            return None, None, self.resolveWikiWord(basePath)

        if self.upwardCount == 0:
            return ("/",
                    len(basePath.resolveWikiWord()) + 1,
                    self.resolveWikiWord(basePath))

        def lenAddOne(s):
            return len(s) + 1 if s != "" else 0

        if self.upwardCount == 1:
            return ("",
                    lenAddOne("/".join(basePath.components[:-1])),
                    self.resolveWikiWord(basePath))

        return (
            "/".join([".."] * (self.upwardCount - 1)) + "/",
            lenAddOne("/".join(basePath.components[:-self.upwardCount])),
            self.resolveWikiWord(basePath))
    def joinTo(self, other):
        result = self.clone()
        result.join(other)
        return result

    @staticmethod
    def isAbsoluteLinkCore(linkCore):
        return linkCore.startswith("//")

    @staticmethod
    def getRelativePathByAbsPaths(targetAbsPath, baseAbsPath,
            downwardOnly=True):
        """
        Create a link to targetAbsPath relative to baseAbsPath.

        If downwardOnly is False, the link may contain parts to go to parents
        or siblings in path (in this wiki language, ".." is used for this).

        If downwardOnly is True, the function may return None if a relative
        link can't be constructed.
        """
        assert targetAbsPath.isAbsolute() and baseAbsPath.isAbsolute()
        targetPath = targetAbsPath.components[:]
        basePath = baseAbsPath.components[:]

        if targetPath == basePath:
            if targetPath:
                return _WikiLinkPath(upwardCount=1, components=[targetPath[-1]])
            else:
                return _WikiLinkPath(linkCore='.')

        if downwardOnly:
            if len(basePath) >= len(targetPath):
                return None
            if basePath != targetPath[:len(basePath)]:
                return None
            return _WikiLinkPath(upwardCount=0,
                    components=targetPath[len(basePath):])
        else:
            # Remove common path elements
            while len(targetPath) > 0 and len(basePath) > 0 and \
                    targetPath[0] == basePath[0]:
                del targetPath[0]
                del basePath[0]

            if len(basePath) == 0:
                assert len(targetPath) > 0
                return _WikiLinkPath(upwardCount=0, components=targetPath)

            return _WikiLinkPath(upwardCount=len(basePath),
                    components=targetPath)

    def __eq__(self, other):
        return ((self.upwardCount, self.components) ==
                (other.upwardCount, other.components))


_RE_LINE_INDENT = re.compile(r"^[ \t]*")

class _TheHelper:
    @staticmethod
    def reset():
        pass

    @staticmethod
    def getWikiLanguageName():
        return WIKI_LANGUAGE_NAME


    # TODO More descriptive error messages (which character(s) is/are wrong?)
    @staticmethod   # isValidWikiWord
    def checkForInvalidWikiWord(word, wikiDocument=None, settings=None):
        """
        Test if word is syntactically a valid wiki word and no settings
        are against it. The camelCase black list is not checked.
        The function returns None IFF THE WORD IS VALID, an error string
        otherwise
        """
        if settings is not None and "footnotesAsWws" in settings:
            footnotesAsWws = settings["footnotesAsWws"]
        else:
            if wikiDocument is None:
                footnotesAsWws = False
            else:
                footnotesAsWws = wikiDocument.getWikiConfig().getboolean(
                        "main", "footnotes_as_wikiwords", False)

        if not footnotesAsWws and footnoteRE.match(word):
            return _("This is a footnote")

        if wikiPageNameRE.match(word):
            return None
        else:
            return _("This is syntactically not a wiki word")


    # TODO More descriptive error messages (which character(s) is/are wrong?)
    @staticmethod   # isValidWikiWord
    def checkForInvalidWikiLink(word, wikiDocument=None, settings=None):
        """
        Test if word is syntactically a valid wiki link and no settings
        are against it. The camelCase black list is not checked.
        The function returns None IFF THE WORD IS VALID, an error string
        otherwise.
        """
        if settings is not None and "footnotesAsWws" in settings:
            footnotesAsWws = settings["footnotesAsWws"]
        else:
            if wikiDocument is None:
                footnotesAsWws = False
            else:
                footnotesAsWws = wikiDocument.getWikiConfig().getboolean(
                        "main", "footnotes_as_wikiwords", False)

        if not footnotesAsWws and footnoteRE.match(word):
            return _("This is a footnote")

        try:
            linkPath = _WikiLinkPath(linkCore=word)
        except ValueError:
            return _("This is not a valid link.")

        if wikiLinkCoreRE.match(word):
            return None
        else:
            return _("This is syntactically not a wiki word")


    @staticmethod
    def extractWikiWordFromLink(word, wikiDocument=None, basePage=None):  # TODO Problems with subpages?
        """
        Strip brackets and other link details if present and return wikiWord
        if a valid wiki word can be extracted, None otherwise.
        """
        if wikiDocument is None and basePage is not None:
            wikiDocument = basePage.getWikiDocument()

        if basePage is None:
            baseDict = _buildBaseDict(wikiDocument=wikiDocument)
        else:
            baseDict = _buildBaseDict(formatDetails=basePage.getFormatDetails())

        try:
            t = extractableWikiWord.parseString(word, parseAll=True,
                    baseDict=baseDict)
            t = t[0]
            return t.wikiWord
        except ParseException:
            return None


    resolveWikiWordLink = staticmethod(resolveWikiWordLink)
    """
    Return page name (absolute link).

    If using subpages this is used to resolve a link to the right
    wiki word relative to basePage on which the link is placed.

    Used in WikiDataManager._updateWikiWordReferences.
    """


    @staticmethod
    def resolvePrefixSilenceAndWikiWordLink(linkCore, basePage):
        """
        Return tuple (prefix, silence, pageName).

        If using subpages this is used to resolve a link to the right
        wiki word for autocompletion.

        Autocompletion now searches for all wiki words starting with
        `pageName`. For all found items it removes the first `silence`
        characters, prepends the `prefix` instead and uses the result
        as suggestion for autocompletion.
        
        If `prefix` is None autocompletion is not possible.
        """
        # if not link:
        #     raise ValueError('Need link to resolve.')
        linkPath = _WikiLinkPath(linkCore=linkCore)

        if linkPath.isAbsolute():
            return linkPath.resolvePrefixSilenceAndWikiWordLink(None)

        if basePage is None:
            return "", 0, linkCore  # TODO:  Better reaction?
        
        basePageName = basePage.getWikiWord()
        if basePageName is None:
            return "", 0, linkCore  # TODO:  Better reaction?
        
        return linkPath.resolvePrefixSilenceAndWikiWordLink(_WikiLinkPath(
                pageName=basePageName))



    @staticmethod
    def parseTodoValue(todoValue, wikiDocument=None):
        """
        Parse a todo value (right of the colon) and return the node or
        return None if value couldn't be parsed
        """
        baseDict = _buildBaseDict(wikiDocument=wikiDocument)
        try:
            t = todoContent.parseString(todoValue, parseAll=True,
                    baseDict=baseDict)
            return t[0]
        except:
            return None


    @staticmethod
    def parseTodoEntry(entry, wikiDocument=None):
        """
        Parse a complete todo entry (without end-token) and return the node or
        return None if value couldn't be parsed
        """
        baseDict = _buildBaseDict(wikiDocument=wikiDocument)
        try:
            t = todoAsWhole.parseString(entry, parseAll=True,
                    baseDict=baseDict)
            return t[0]
        except:
            traceback.print_exc()
            return None


    @staticmethod
    def _createAutoLinkRelaxWordEntryRE(word):
        """
        Get compiled regular expression for one word in autoLink "relax"
        mode.

        Not part of public API.
        """
        # Split into parts of contiguous alphanumeric characters
        parts = AutoLinkRelaxSplitRE.split(word)
        # Filter empty parts
        parts = [p for p in parts if p != ""]

        # Instead of original non-alphanum characters allow arbitrary
        # non-alphanum characters
        pat = r"\b" + (AutoLinkRelaxJoinPAT.join(parts)) + r"\b"
        regex = re.compile(pat, AutoLinkRelaxJoinFlags)

        return regex


    @staticmethod
    def buildAutoLinkRelaxInfo(wikiDocument):
        """
        Build some cache info needed to process auto-links in "relax" mode.
        This info will be given back in the formatDetails when calling
        _TheParser.parse().
        The implementation for this plugin creates a list of regular
        expressions and the related wiki words, but this is not mandatory.
        """
        # Build up regular expression
        # First fetch all wiki words
        words = wikiDocument.getWikiData().getAllProducedWikiLinks()

        # Sort longest words first
        words.sort(key=lambda w: len(w), reverse=True)
        
        return [(_TheHelper._createAutoLinkRelaxWordEntryRE(w), w)
                for w in words if w != ""]


    @staticmethod
    def createWikiLinkPathObject(*args, **kwargs):
        return _WikiLinkPath(*args, **kwargs)


    @staticmethod
    def isAbsoluteLinkCore(linkCore):
        return _WikiLinkPath.isAbsoluteLinkCore(linkCore)


    @staticmethod
    def createLinkFromWikiWord(word, wikiPage, forceAbsolute=False):
        """
        Create a link from word which should be put on wikiPage.
        """
        wikiDocument = wikiPage.getWikiDocument()
        
        targetPath = _WikiLinkPath(pageName=word)

        if forceAbsolute:
            return BracketStart + targetPath.getLinkCore() + BracketEnd

        linkCore = _TheHelper.createRelativeLinkFromWikiWord(
                word, wikiPage.getWikiWord(), downwardOnly=False)
                
        if _TheHelper.isCcWikiWord(word) and _TheHelper.isCcWikiWord(linkCore):
            wikiFormatDetails = wikiPage.getFormatDetails()
            if wikiFormatDetails.withCamelCase:
                
                ccBlacklist = wikiDocument.getCcWordBlacklist()
                if not word in ccBlacklist:
                    return linkCore
        
        return BracketStart + linkCore + BracketEnd


    @staticmethod
    def createAbsoluteLinksFromWikiWords(words, wikiPage=None):
        """
        Create particularly stable links from a list of words which should be
        put on wikiPage.
        """
        return "\n".join(["%s//%s%s" % (BracketStart, w, BracketEnd)
                for w in words])
                
#     # For compatibility. TODO: Remove
#     createStableLinksFromWikiWords = createAbsoluteLinksFromWikiWords


    @staticmethod
    def createWikiLinkFromText(text, bracketed=True):
        text = text.replace(BracketStart, "").replace(BracketEnd, "")
        while text.startswith("+"):
            text = text[1:]
        
        text = text.strip()

        if len(text) == 0:
            return ""

        text = text[0:1].upper() + text[1:]
        if bracketed:
            text = BracketStart + text + BracketEnd

        return text


    @staticmethod
    def createRelativeLinkFromWikiWord(word, baseWord, downwardOnly=True):
        """
        Create a link to `word` relative to `baseWord`.

        If `downwardOnly` is False, the link may contain parts to go to parents
        or siblings in path (in this wiki language, ".." are used for this).

        If `downwardOnly` is True, the function may return None if a relative
        link can't be constructed.
        """
        if not word:
            raise ValueError('Target can not be empty.')

        relPath = _WikiLinkPath.getRelativePathByAbsPaths(
                _WikiLinkPath(pageName=word),
                _WikiLinkPath(pageName=baseWord),
                downwardOnly=downwardOnly)
        
        if relPath is None:
            return None
        
        return relPath.getLinkCore()


    WikiLinkPath = _WikiLinkPath
    # Used in WikiDataManager._updateWikiWordReferences.


    @staticmethod
    def createWikiLinkPathFromPageName(targetPageName, basePageName, absolute):
        """
        Create relative or absolute wiki link to pageName.

        Used in WikiDataManager._updateWikiWordReferences.
        """
        if not targetPageName:
            raise ValueError('Need target.')

        if absolute:
            return _TheHelper.WikiLinkPath(pageName=targetPageName)

        else:
            target = _TheHelper.WikiLinkPath(pageName=targetPageName)
            base = _TheHelper.WikiLinkPath(pageName=basePageName)
            return _TheHelper.WikiLinkPath.getRelativePathByAbsPaths(
                target, base, downwardOnly=False)


    @staticmethod
    def createUrlLinkFromPath(wikiDocument, path, relative=False,
            bracketed=False, protocol=None):
        if bracketed:
            addSafe = ' '
        else:
            addSafe = ''

        if relative:
            url = wikiDocument.makeAbsPathRelUrl(path, addSafe=addSafe)

            if url is None:
                # Relative not possible -> absolute instead
                relative = False
            else:
                if protocol == "wiki":
                    url = "wiki" + url  # Combines to "wikirel://"

        if not relative:
            if protocol == "wiki":
                url = "wiki:" + StringOps.urlFromPathname(path, addSafe=addSafe)
            else:
                url = "file:" + StringOps.urlFromPathname(path, addSafe=addSafe)

        if bracketed:
            url = BracketStart + url + BracketEnd
        
        return url


    @staticmethod
    def createAttributeFromComponents(key, value, wikiPage=None):
        """
        Build an attribute from key and value.
        TODO: Check for necessary escaping
        """
        return "%s%s: %s%s\n" % (BracketStart, key, value, BracketEnd)
        

    @staticmethod
    def isCcWikiWord(word):
        return bool(wikiWordCcRE.match(word))


    @staticmethod
    def findNextWordForSpellcheck(text, startPos, wikiPage):
        """
        Find in text next word to spellcheck, beginning at position startPos
        
        Returns tuple (start, end, spWord) which is either (None, None, None)
        if no more word can be found or returns start and after-end of the
        spWord to spellcheck.
        
        TODO: Move away because this is specific to human language,
            not wiki language.
        """
        while True:
            mat = TextWordRE.search(text, startPos)
            if mat is None:
                # No further word
                return (None, None, None)

            if mat.group("negative") is not None:
                startPos = mat.end()
                continue

            start, end = mat.span()
            spWord = mat.group()

            return (start, end, spWord)


    @staticmethod
    def prepareAutoComplete(editor, text, charPos, lineStartCharPos,
            wikiDocument, docPage, settings):
        """
        Called when user wants autocompletion.
        text -- Whole text of page
        charPos -- Cursor position in characters
        lineStartCharPos -- For convenience and speed, position of the 
                start of text line in which cursor is.
        wikiDocument -- wiki document object
        docPage -- DocPage object on which autocompletion is done
        closingBracket -- boolean iff a closing bracket should be suggested
                for bracket wikiwords and attributes

        returns -- a list of tuples (sortKey, entry, backStepChars) where
            sortKey -- unistring to use for sorting entries alphabetically
                using right collator
            entry -- actual unistring entry to show and to insert if
                selected
            backStepChars -- numbers of chars to delete to the left of cursor
                before inserting entry
        """
        line = text[lineStartCharPos:charPos]
        rline = revStr(line)
        backStepMap = {}
        closingBracket = settings.get("closingBracket", False)
        builtinAttribs = settings.get("builtinAttribs", False)

        # TODO Sort entries appropriately (whatever this means)

        wikiData = wikiDocument.getWikiData()
        baseWordSegments = docPage.getWikiWord().split("/")

        mat1 = RevWikiWordRE.match(rline)
        if mat1:
            # may be CamelCase word
            tofind = line[-mat1.end():]
            backstep = len(tofind)
            prefix, silence, tofind = _TheHelper.resolvePrefixSilenceAndWikiWordLink(
                    tofind, docPage)
            
            # We don't want prefixes here
            if prefix == "":
                ccBlacklist = wikiDocument.getCcWordBlacklist()
                for word in wikiData.getWikiPageLinkTermsStartingWith(tofind, True):
                    if not _TheHelper.isCcWikiWord(word[silence:]) or word in ccBlacklist:
                        continue

                    backStepMap[word[silence:]] = backstep

        mat2 = RevWikiWordRE2.match(rline)
        mat3 = RevAttributeValue.match(rline)
        if mat2:
            # may be not-CamelCase word or in an attribute name
            tofind = line[-mat2.end():]

            # Should a closing bracket be appended to suggested words?
            if closingBracket:
                wordBracketEnd = BracketEnd
            else:
                wordBracketEnd = ""
            
            backstep = len(tofind)

            prefix, silence, link = _TheHelper.resolvePrefixSilenceAndWikiWordLink(
                    tofind[len(BracketStart):], docPage)
            
            if prefix is not None:
                for word in wikiData.getWikiPageLinkTermsStartingWith(
                        link, True):
                    backStepMap[BracketStart + prefix + word[silence:] +
                            wordBracketEnd] = backstep

            for prop in wikiDocument.getAttributeNamesStartingWith(
                    tofind[len(BracketStart):], builtinAttribs):
                backStepMap[BracketStart + prop] = backstep
        elif mat3:
            # In an attribute value
            tofind = line[-mat3.end():]
            propkey = revStr(mat3.group(3))
            propfill = revStr(mat3.group(2))
            propvalpart = revStr(mat3.group(1))
            values = [pv for pv in wikiDocument.getDistinctAttributeValuesByKey(propkey,
                    builtinAttribs) if pv.startswith(propvalpart)]

            for v in values:
                backStepMap[BracketStart + propkey +
                        propfill + v + BracketEnd] = len(tofind)

        mat = RevTodoKeyRE.match(rline)
        if mat:
            # Might be todo entry
            tofind = line[-mat.end():]
            for t in wikiData.getTodos():
                td = t[1]
                if not td.startswith(tofind):
                    continue

#                 tdmat = ToDoREWithCapturing.match(td)
#                 key = tdmat.group(1) + ":"
                key = td + ":"
                backStepMap[key] = len(tofind)

        mat = RevTodoValueRE.match(rline)
        if mat:
            # Might be todo entry
            tofind = line[-mat.end():]
            combinedTodos = [t[1] + ":" + t[2] for t in wikiData.getTodos()]
#             todos = [t[1] for t in wikiData.getTodos() if t[1].startswith(tofind)]
            todos = [t for t in combinedTodos if t.startswith(tofind)]
            for t in todos:
                backStepMap[t] = len(tofind)

        mat = RevWikiWordAnchorRE2.match(rline)
        if mat:
            # In an anchor of a possible bracketed wiki word
            tofind = line[-mat.end():]
            wikiLinkCore = revStr(mat.group("wikiWord"))
            wikiWord = _TheHelper.resolvePrefixSilenceAndWikiWordLink(
                    wikiLinkCore, docPage)[2]

            anchorBegin = revStr(mat.group("anchorBegin"))

            try:
                page = wikiDocument.getWikiPage(wikiWord) # May throw exception
                anchors = [a for a in page.getAnchors()
                        if a.startswith(anchorBegin)]

                for a in anchors:
                    backStepMap[BracketStart + wikiLinkCore +
                            BracketEnd +
                            WikiWordAnchorStart + a] = len(tofind)
            except WikiWordNotFoundException:
                # wikiWord isn't a wiki word
                pass

        mat = RevWikiWordAnchorRE.match(rline)
        if mat:
            # In an anchor of a possible camel case word
            tofind = line[-mat.end():]
            wikiLinkCore = revStr(mat.group("wikiWord"))
            wikiWord = _TheHelper.resolvePrefixSilenceAndWikiWordLink(
                    wikiLinkCore, docPage)[2]

            anchorBegin = revStr(mat.group("anchorBegin"))

            try:
                page = wikiDocument.getWikiPage(wikiWord) # May throw exception
                anchors = [a for a in page.getAnchors()
                        if a.startswith(anchorBegin)]
                        
                for a in anchors:
                    backStepMap[wikiWord + wikiLinkCore +
                            a] = len(tofind)
            except WikiWordNotFoundException:
                # wikiWord isn't a wiki word
                pass


        acresult = list(backStepMap.keys())
        
        if len(acresult) > 0:
            # formatting.BracketEnd
            acresultTuples = []
            for r in acresult:
                if r.endswith(BracketEnd):
                    rc = r[: -len(BracketEnd)]
                else:
                    rc = r
                acresultTuples.append((rc, r, backStepMap[r]))

            return acresultTuples
        else:
            return []


    @staticmethod
    def handleNewLineBeforeEditor(editor, text, charPos, lineStartCharPos,
            wikiDocument, settings):
        """
        Processes pressing of a newline in editor before editor processes it.
        Returns True iff the actual newline should be processed by
            editor yet.
        """
        # autoIndent, autoBullet, autoUnbullet
        
        line = text[lineStartCharPos:charPos]

        if settings.get("autoUnbullet", False):
            # Check for lonely bullet or number
            mat = BulletRE.match(line)
            if mat and mat.end(0) == len(line):
                editor.SetSelectionByCharPos(lineStartCharPos, charPos)
                editor.ReplaceSelection(mat.group("indentBullet"))
                return False

            mat = NumericSimpleBulletRE.match(line)
            if mat and mat.end(0) == len(line):
                editor.SetSelectionByCharPos(lineStartCharPos, charPos)
                editor.ReplaceSelection(mat.group("indentBullet"))
                return False

            mat = NumericBulletRE.match(line)
            if mat and mat.end(0) == len(line):
                replacement = mat.group("indentNumeric")
                if mat.group("preLastNumeric") != "":
                    replacement += mat.group("preLastNumeric") + " "

                editor.SetSelectionByCharPos(lineStartCharPos, charPos)
                editor.ReplaceSelection(replacement)
                return False
        
        return True


    @staticmethod
    def handleNewLineAfterEditor(editor, text, charPos, lineStartCharPos,
            wikiDocument, settings):
        """
        Processes pressing of a newline after editor processed it (if 
        handleNewLineBeforeEditor returned True).
        """
        # autoIndent, autoBullet, autoUnbullet

        currentLine = editor.GetCurrentLine()

        if currentLine > 0:
            previousLine = editor.GetLine(currentLine - 1)
            indent = _RE_LINE_INDENT.match(previousLine).group(0)
    
            # check if the prev level was a bullet level
            if settings.get("autoBullets", False):
                match = BulletRE.match(previousLine)
                if match:
                    editor.AddText(indent + match.group("actualBullet"))
                    return

                match = NumericSimpleBulletRE.match(previousLine)
                if match:
                    editor.AddText(indent + match.group("actualBullet"))
                    return False

                match = NumericBulletRE.search(previousLine)
                if match:
                    prevNumStr = match.group(3)
                    prevNum = int(prevNumStr)
                    nextNum = prevNum+1
#                     adjustment = len(str(nextNum)) - len(prevNumStr)
#                     if adjustment == 0:
                    editor.AddText("%s%s%d. " % (indent,
                            match.group(2), int(prevNum)+1))
#                     else:
#                         editor.AddText("%s%s%d. " % (" " *
#                                 (editor.GetLineIndentation(currentLine - 1) - adjustment),
#                                 match.group(2), int(prevNum)+1))
                    return

            if settings.get("autoIndent", False):
                editor.AddText(indent)
                return


    @staticmethod
    def handleRewrapText(editor, settings):
        curPos = editor.GetCurrentPos()

        # search back for start of the para
        curLineNum = editor.GetCurrentLine()
        curLine = editor.GetLine(curLineNum)
        while curLineNum > 0:
            # don't wrap previous bullets with this bullet
            if (BulletRE.match(curLine) or NumericBulletRE.match(curLine)):
                break

            if EmptyLineRE.match(curLine):
                curLineNum = curLineNum + 1
                break

            curLineNum = curLineNum - 1
            curLine = editor.GetLine(curLineNum)
        startLine = curLineNum

        # search forward for end of the para
        curLineNum = editor.GetCurrentLine()
        curLine = editor.GetLine(curLineNum)
        while curLineNum <= editor.GetLineCount():
            # don't wrap the next bullet with this bullet
            if curLineNum > startLine:
                if (BulletRE.match(curLine) or NumericBulletRE.match(curLine)):
                    curLineNum = curLineNum - 1
                    break

            if EmptyLineRE.match(curLine):
                curLineNum = curLineNum - 1
                break

            curLineNum = curLineNum + 1
            curLine = editor.GetLine(curLineNum)
        endLine = curLineNum
        
        if (startLine <= endLine):
            # get the start and end of the lines
            startPos = editor.PositionFromLine(startLine)
            endPos = editor.GetLineEndPosition(endLine)

            # get the indentation for rewrapping
            indent = _RE_LINE_INDENT.match(editor.GetLine(startLine)).group(0)
            subIndent = indent

            # if the start of the para is a bullet the subIndent has to change
            if BulletRE.match(editor.GetLine(startLine)):
                subIndent = indent + "  "
            else:
                match = NumericBulletRE.match(editor.GetLine(startLine))
                if match:
                    subIndent = indent + " " * (len(match.group(2)) + 2)

            # get the text that will be wrapped
            indentedStartPos = startPos + editor.bytelenSct(indent)
            text = editor.GetTextRange(indentedStartPos, endPos)
            # remove spaces, newlines, etc
            text = re.sub(r"[\s\r\n]+", " ", text)

            # wrap the text
            wrapPosition = 70
            try:
                wrapPosition = int(
                        editor.getLoadedDocPage().getAttributeOrGlobal(
                        "wrap", "70"))
            except:
                pass

            # make the min wrapPosition 5
            if wrapPosition < 5:
                wrapPosition = 5

            if editor.isCharWrap():
                lines = []
                for s in range(0, len(text), wrapPosition):
                    lines.append(text[s:s+wrapPosition])
                    
                filledText = "\n".join(lines)
            else:
                filledText = fill(text, width=wrapPosition,
                        initial_indent=indent, 
                        subsequent_indent=subIndent)

            # replace the text based on targetting
            editor.SetTargetStart(startPos)
            editor.SetTargetEnd(endPos)
            editor.ReplaceTarget(filledText)
            editor.GotoPos(endPos)
            editor.scrollXY(0, editor.GetScrollPos(wx.VERTICAL))


    @staticmethod 
    def handlePasteRawHtml(editor, rawHtml, settings):
        # Remove possible body end tags
        rawHtml = rawHtml.replace("</body>", "")
        if rawHtml:
            editor.ReplaceSelection("<body>" + rawHtml + "</body>")
            return True

        return False


    @staticmethod 
    def formatSelectedText(text, start, afterEnd, formatType, settings):
        """
        Called when selected text (between start and afterEnd)
        e.g. in editor should be formatted (e.g. bold or as heading)
        text -- Whole text
        start -- Start position of selection
        afterEnd -- After end position of selection

        formatType -- string to describe type of format
        settings -- dict with additional information, currently ignored
        
        Returns None if operation wasn't supported or possible or 
            tuple (replacement, repStart, repAfterEnd, selStart, selAfterEnd) where
    
            replacement -- replacement text
            repStart -- Start of characters to delete in original text
            repAfterEnd -- After end of characters to delete
            selStart -- Recommended start of editor selection after replacement
                was done
            selAfterEnd -- Recommended after end of editor selection after replacement
        """
        if formatType == "bold":
            return StringOps.styleSelection(text, start, afterEnd, "*")
        elif formatType == "italics":
            return StringOps.styleSelection(text, start, afterEnd, "_")
        elif formatType == "plusHeading":
            level = settings.get("headingLevel", 1)
            titleSurrounding = settings.get("titleSurrounding", "")
            cursorShift = level + len(titleSurrounding)

            ls = StringOps.findLineStart(text, start)
            return ('+' * level + titleSurrounding, ls, ls,
                    start + cursorShift, start + cursorShift)

        return None


    @staticmethod
    def getNewDefaultWikiSettingsPage(mainControl):
        """
        Return default text of the "WikiSettings" page for a new wiki.
        """
        return _("""++ Wiki Settings

These are your default global settings.

[global.importance.low.color: grey]
[global.importance.high.bold: true]
[global.contact.icon: contact]
[global.wrap: 70]

[icon: cog]
""")  # TODO Localize differently?


    @staticmethod
    def createWikiLanguageDetails(wikiDocument, docPage):
        """
        Returns a new WikiLanguageDetails object based on current configuration
        """
        return WikiLanguageDetails(wikiDocument, docPage)
        
        
    
    _RECURSIVE_STYLING_NODE_NAMES = frozenset(("table", "tableRow", "tableCell",
                        "orderedList", "unorderedList", "indentedText",
                        "noExport", "bulletEntry", "numberEntry"))
                        
    @staticmethod
    def getRecursiveStylingNodeNames():
        """
        Returns a set of those node names of NonTerminalNode-s  for which the
        WikiTxtCtrl.processTokens() should process children recursively.
        """
        return _TheHelper._RECURSIVE_STYLING_NODE_NAMES
        
        
    _FOLDING_NODE_DICT = {
            "table": (True, False),
            "attribute": (True, False),
            "insertion": (True, False)
        }


    @staticmethod
    def getFoldingNodeDict():
        """
        Retrieve the folding node dictionary which tells
        which AST nodes (other than "heading") should be processed by
        folding.
        The folding node dictionary has the names of the AST node types as keys,
        each value is a tuple (fold, recursive) where
        fold -- True iff node should be folded
        recursive -- True iff node should be processed recursively
        
        The value tuples may contain more than these two items, processFolding()
        must be able to handle that.
        """
        return _TheHelper._FOLDING_NODE_DICT


THE_LANGUAGE_HELPER = _TheHelper()


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
    if text.getDebug() != debugMode:
        text.setDebugRecurs(debugMode)

    return THE_PARSER


def languageHelperFactory(intLanguageName, debugMode):
    """
    Builds up a language helper object. If the object is threadsafe this function is
    allowed to return the same object multiple times (currently it should do
    so for efficiency).

    intLanguageName -- internal unique name (should be ascii only) to
        identify wiki language to process by helper
    """
    return THE_LANGUAGE_HELPER


# - Text generator -------------------------------------------------------------

ATTRIBUTE_FMT = '[{key}: {values}]'  # also possible: [{key}={values}]

INSERTION_FMT = '[:{key}:{space}{value}{appendices}]'

WIKI_WORD_FMT = {  # fmt_nr -> fmt
        # non-camelcase
        0: '[{link_core}]',                        # [wikiword]
        1: '[{link_core}]!{anchor}',               # [wikiword]!anchor
        2: '[{link_core}|{title}]',                # [wikiword|title]
        3: '[{link_core}|{title}]!{anchor}',       # [wikiword|title]!anchor
        4: '[{link_core}#{search_fragment}]',      # [wikiword#search fragment]
        5: '[{link_core}#{search_fragment}]!{anchor}',
        6: '[{link_core}#{search_fragment}|{title}]',
        7: '[{link_core}#{search_fragment}|{title}]!{anchor}',
        # CamelCase
        8: '{link_core}',                          # WikiWord
        9: '{link_core}!{anchor}',                 # WikiWord!anchor
        10: '{link_core}#{search_fragment}',       # WikiWord#search_fragment
        # CamelCase and space in search fragment
        11: '[{link_core}#{search_fragment}]',     # [WikiWord#search fragment]
}

# (?:[ \t]*[\w\-\_=:,.!?#%|/]+)*
# valid_non_quoted_value = re.compile(ATTR_INS_NON_QUOTED_VALUE_PATTERN + '$')
valid_non_quoted_value = re.compile(r"[ \t\w\-_=:,.!?#%|/]*$")


def needs_quotes(s):
    return not valid_non_quoted_value.match(s)


def count_max_number_of_consecutive_quotes(s):
    n = i = 0
    for c in s:
        if c == '"':
            i += 1
        else:
            i = 0
        if i > n:
            n = i
    return n


def quote(s):
    n = count_max_number_of_consecutive_quotes(s)
    return '"' * (n + 1) + s + '"' * (n + 1)


def quote_if_needed(s):
    return quote(s) if needs_quotes(s) else s


class TextFormatter(object):
    """Given AST, return wiki formatted text.

    API::

        text = TextFormatter().format(pageAst, wikiPage)

    format() is like ast.getString(), but uses only the node values.
    For instance, for the node 'attribute', it uses the keys and values
    stored in node.attrs to generate the text, not by simply using the
    attribute text of its children (like getString does). This makes it
    easy to transform the AST and get an updated text. This is used to
    update wiki word references when renaming a wiki word.

    format traverses the AST. Visitor methods (one per node type) format
    the text based on the node value(s). For now, only visitor methods for
    the nodes 'wikiWord', 'attribute' and 'insertion' are implemented, and
    it falls back on .getString() for the other nodes. Note these visitor
    methods are the only ones needed to reliably update wiki word
    references.

    format uses THE_LANGUAGE_HELPER to check if a word is camelcase,
    and to create wiki links.
    """
    def __init__(self):
        self.helper = THE_LANGUAGE_HELPER
        self.realPage = None
        self.realPageName = None
        self.with_camel_case = None
        self.cc_blacklist = None
        self._count = None

    def format(self, ast, page):
        """
        Need page to get (real) page name + format details and
        cc blacklist (to check whether to use camelcase).
        """
        self._count = Counter()
        self.realPage = page.getNonAliasPage()
        self.realPageName = self.realPage.getWikiWord()
        self.with_camel_case = page.getFormatDetails().withCamelCase
        self.cc_blacklist = page.getWikiDocument().getCcWordBlacklist()

        return self.visit(ast)

    def count(self, node_name):
        return self._count[node_name]

    # --------------------------------------------------------------------------

    def visit(self, node):
        name = node.name if node.name is not None else 'None'
        self._count[name] += 1
        return getattr(self, 'visit_' + name, self.generic_visit)(node)

    def generic_visit(self, node):
        # no visitor method for node
        # visit children and fall back on getString() for TerminalNode-s
        try:
            i = iter(node)  # ? NonTerminal node
        except TypeError:  # not iterable, Terminal node
            return node.getString()
        else:
            return ''.join(self.visit(child) for child in i)

    def visit_text(self, node):
        """root"""
        return ''.join(self.visit(child) for child in node)

    def is_camelcase(self, word, link):
        # if self.helper.isCcWikiWord(word) and self.helper.isCcWikiWord(link):
        if self.helper.isCcWikiWord(link):
            if self.with_camel_case:
                if word not in self.cc_blacklist:
                    return True
        return False

    def visit_wikiWord(self, node):
        """
        node attributes used:

        .wikiWord -- real page name or alias (link has already been resolved)
        .linkPath -- WikiLinkPath
        .titleNode
        .fragmentNode
        .searchFragment
        .anchorLink
        """
        assert node.wikiWord
        assert node.linkPath

        link_core = node.linkPath.getLinkCore()

        has_anchor = node.anchorLink is not None
        has_title = node.titleNode is not None
        has_search = node.fragmentNode is not None
        
        # If node was non-camelcase then keep it that way. Otherwise
        # wiki words with additional brackets meant as text (e.g. '[[FooBar]]'
        # meant to be shown in preview/export as "[FooBar]")
        # are incorrectly changed (to '[FooBar]').

        if getattr(node, "formatType", "") == "ncc":
            is_camelcase = False
        else:
            is_camelcase = self.is_camelcase(node.wikiWord, link_core)

        search_fragment = node.searchFragment if has_search else None
        anchor = node.anchorLink
        title = node.titleNode.getString().strip() if has_title else None

        fmt_nr = has_search * 4 + has_title * 2 + has_anchor * 1

        if is_camelcase:
            if fmt_nr == 0:
                fmt_nr = 8
            elif fmt_nr == 1:
                fmt_nr = 9
            elif fmt_nr == 4:
                assert search_fragment is not None
                if ' ' not in search_fragment:
                    fmt_nr = 10
                else:
                    fmt_nr = 11
                    # alternative:
                    # search_fragment = search_fragment.replace(' ', '# ')

        s = WIKI_WORD_FMT[fmt_nr].format(
            link_core=link_core, title=title, anchor=anchor,
            search_fragment=search_fragment)
        return s

    def visit_attribute(self, node):
        """
        node attributes used:

        .key
        .attrs
        """
        values = '; '.join(quote_if_needed(value)
                            for key, value in node.attrs if value)
        return ATTRIBUTE_FMT.format(key=node.key, values=values)

    def visit_insertion(self, node):
        """
        node attributes used:

        .key
        .value
        .appendices
        """
        key, value = node.key, quote_if_needed(node.value)
        space = ' ' if value else ''
        if not node.appendices:
            appendices = ''
        else:
            s = '; '.join(quote_if_needed(appendix)
                           for appendix in node.appendices)
            appendices = '; ' + s
        return INSERTION_FMT.format(key=key, space=space,
                                    value=value, appendices=appendices)


THE_TEXT_FORMATTER = TextFormatter()

_TheHelper.generate_text = THE_TEXT_FORMATTER.format
_TheHelper.TextFormatter = TextFormatter
