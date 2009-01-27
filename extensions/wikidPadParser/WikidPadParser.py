## import hotshot
## _prof = hotshot.Profile("hotshot.prf")


import locale, pprint, time, sys, string, traceback

from textwrap import fill

from pwiki.rtlibRepl import re
from pwiki.StringOps import UPPERCASE, LOWERCASE, revStr
from pwiki.WikiDocument import WikiDocument

sys.stderr = sys.stdout

locale.setlocale(locale.LC_ALL, '')

from pwiki.WikiPyparsing import *


WIKIDPAD_PLUGIN = (("WikiParser", 1),)



LETTERS = UPPERCASE + LOWERCASE


# The specialized optimizer in WikiPyParsing can't handle automatic whitespace
# removing
ParserElement.setDefaultWhitespaceChars("")



RE_FLAGS = re.DOTALL | re.UNICODE | re.MULTILINE


class IndentInfo(object):
    __slots__ = ("level", "type")
    def __init__(self, type):
        self.level = 0
        self.type = type



def buildRegex(regex, name=None, hideOnEmpty=False):
    if name is None:
        element = Regex(regex, RE_FLAGS)
    else:
        element = Regex(regex, RE_FLAGS).setResultsName(name).setName(name)
    
    if hideOnEmpty:
        element.setParseAction(actionHideOnEmpty)
        
    return element

stringEnd = buildRegex(ur"(?!.)", "stringEnd")



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
    for i in xrange(len(txt) - 1, -1, -1):
        if txt[i] not in (u"\t", u" ", u"\n", u"\r"):
            if i < len(txt) - 1:
                lt.text = txt[:i+1]
                lt.recalcStrLength()
                
                t2 = buildSyntaxNode(txt[i+1:], lt.pos + i + 1)
                t.append(t2)
            return t

    return None

  
_CHECK_LEFT_RE = re.compile(ur"[ \t]*$", RE_FLAGS)


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
    print "--precTest", repr((l, st, type(pe)))



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

tableContentInCell = Forward().setResultsName("tableCell")
headingContent = Forward().setResultsName("headingContent")
todoContent = Forward().setResultsName("value")
titleContent = Forward().setResultsName("title")

whitespace = buildRegex(ur"[ \t]*")
whitespace = whitespace.setParseAction(actionHideOnEmpty)


# The mode appendix for URLs and tables
def actionModeAppendix(s, l, st, t):
    entries = []

    for entry in t.iterFlatByName("entry"):
        key = entry.findFlatByName("key").getText()
        data = entry.findFlatByName("data").getText()
        entries.append((key, data))
        
    t.entries = entries
    return t



modeAppendixEntry = buildRegex(ur"(?!;)\S", "key") + buildRegex(ur"(?:(?!;)\S)*", "data")
modeAppendixEntry = modeAppendixEntry.setResultsName("entry")
modeAppendix = modeAppendixEntry + ZeroOrMore(buildRegex(ur";") + modeAppendixEntry)
modeAppendix = modeAppendix.addParseAction(actionModeAppendix)




# -------------------- Simple formatting --------------------

EscapePlainCharPAT = ur"\\"


escapedChar = buildRegex(EscapePlainCharPAT) + buildRegex(ur".", "plainText")

italicsStart = buildRegex(ur"\b_")
italicsStart = italicsStart.setParseStartAction(createCheckNotIn(("italics",)))

italicsEnd = buildRegex(ur"_\b")

italics = italicsStart + content + italicsEnd
italics = italics.setResultsName("italics").setName("italics")

boldStart = buildRegex(ur"\*(?=\S)")
boldStart = boldStart.setParseStartAction(createCheckNotIn(("bold",)))

boldEnd = buildRegex(ur"\*")

bold = boldStart + content + boldEnd
bold = bold.setResultsName("bold").setName("bold")


script = buildRegex(ur"<%") + buildRegex(ur".*?(?=%>)", "code") + \
        buildRegex(ur"%>")
script = script.setResultsName("script")

horizontalLine = buildRegex(ur"----+[ \t]*$", "horizontalLine")\
        .setParseStartAction(preActCheckNothingLeft)


# -------------------- HTML --------------------

htmlTag = buildRegex(ur"</?[A-Za-z][A-Za-z0-9:]*(?:/| [^\n>]*)?>", "htmlTag")

htmlEntity = buildRegex(
        ur"&(?:[A-Za-z0-9]{2,10}|#[0-9]{1,10}|#x[0-9a-fA-F]{1,8});",
        "htmlEntity")



# -------------------- Heading --------------------

def actionHeading(s, l, st, t):
    t.level = len(t[0].getText()) - 1
    t.contentNode = t.findFlatByName("headingContent")

headingEnd = buildRegex(ur"\n")

heading = buildRegex(ur"^\+{1,15}(?!\+) ?") + headingContent + headingEnd
heading = heading.setResultsName("heading").setParseAction(actionHeading)



# -------------------- Todo-Entry --------------------

def actionTodoEntry(s, l, st, t):
    t.key = t.findFlatByName("key").getString()
    t.keyComponents = t.key.split(u".")
    t.delimiter = t.findFlatByName("todoDelimiter").getString()
    t.valueNode = t.findFlatByName("value")
        


todoKey = buildRegex(ur"(?:todo|done|wait|action|track|issue|"
        ur"question|project)(?:\.[^:\s]+)?", "key")
todoKey = todoKey.setParseStartAction(preActCheckNothingLeft)

todoEnd = buildRegex(ur"\n|\||(?!.)")

todoEntry = todoKey + buildRegex(ur":", "todoDelimiter") + todoContent + \
        Optional(buildRegex(ur"\|"))

todoEntry = todoEntry.setResultsName("todoEntry")\
        .setParseAction(actionTodoEntry)

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




def preActUlPrepareStack(s, l, st, pe):
    oldIdInfo = st.dictStack.getSubTopDict().get("indentInfo")
    newIdInfo = IndentInfo("ul")

    newIdInfo.level = st.dictStack.get("lastIdentation", 0)
    st.dictStack["indentInfo"] = newIdInfo

def preActOlPrepareStack(s, l, st, pe):
    oldIdInfo = st.dictStack.getSubTopDict().get("indentInfo")
    newIdInfo = IndentInfo("ol")

    newIdInfo.level = st.dictStack.get("lastIdentation", 0)
    st.dictStack["indentInfo"] = newIdInfo



def inmostIndentChecker(typ):
    def startAction(s, l, st, pe):
        if st.dictStack["indentInfo"].type != typ:
            raise ParseException(s, l, 'Expected inmost indent type "%s"' % typ)

    return startAction



# Only an empty line
fakeIndentation = buildRegex(ur"^[ \t]+$")

newLine = buildRegex(ur"\n") + Optional(fakeIndentation)



newLinesParagraph = newLine + OneOrMore(newLine)
newLinesParagraph = newLinesParagraph.setResultsName("newParagraph")\
        .setParseStartAction(preActNewLinesParagraph)\
        .setParseAction(actionResetIndent)


newLineLineBreak = newLine
newLineLineBreak = newLineLineBreak.setResultsName("lineBreak")\
        .setParseStartAction(preActNewLineLineBreak)\
        .setParseAction(actionResetIndent)


newLineWhitespace = newLine
newLineWhitespace = newLineWhitespace.setResultsName("whitespace")\
        .setParseStartAction(preActNewLineWhitespace)


moreIndentation = buildRegex(ur"^[ \t]*(?!\n)").setValidateAction(validateMoreIndent)
moreIndentation = moreIndentation.setParseStartAction(validateInmostIndentNormal).\
        setParseAction(actionMoreIndent).setName("moreIndentation")

equalIndentation = buildRegex(ur"^[ \t]*(?!\n)").setValidateAction(validateEqualIndent)
equalIndentation = equalIndentation.setParseAction(actionIndent).\
        setName("equalIndentation")

lessIndentation = buildRegex(ur"^[ \t]*(?!\n)").setValidateAction(validateLessIndent)
lessIndentation = lessIndentation.setParseAction(actionIndent).\
        setName("lessIndentation")

lessIndentOrEnd = stringEnd | lessIndentation
lessIndentOrEnd = lessIndentOrEnd.setName("lessIndentOrEnd")


equivalIndentation = buildRegex(ur"^[ \t]+(?!\n)").setValidateAction(validateEquivalIndent)
equivalIndentation = equivalIndentation.setParseAction(actionIndent).\
        setName("equivalIndentation")


indentedText = moreIndentation + content + FollowedBy(lessIndentOrEnd)
indentedText = indentedText.setResultsName("indentedText")


listStartIndentation  = buildRegex(ur"^[ \t]*")
listStartIndentation = listStartIndentation.\
        setParseAction(actionListStartIndent).setName("listStartIndentation")


bullet = buildRegex(ur"\*[ \t]", "bullet")

bulletEntry = equalIndentation.copy()\
        .addParseStartAction(inmostIndentChecker("ul")) + bullet  # + \
        


unorderedList = listStartIndentation + bullet + \
        (content + FollowedBy(lessIndentOrEnd))\
        .addParseStartAction(preActUlPrepareStack)
unorderedList = unorderedList.setResultsName("unorderedList")


number = buildRegex(ur"(?:\d+\.)*(\d+)\.[ \t]|#[ \t]", "number")

numberEntry = equalIndentation.copy()\
        .addParseStartAction(inmostIndentChecker("ol")) + number



orderedList = listStartIndentation + number + \
        (content + FollowedBy(lessIndentOrEnd))\
        .addParseStartAction(preActOlPrepareStack)
orderedList = orderedList.setResultsName("orderedList")



# -------------------- Table --------------------


tableEnd = buildRegex(ur"^[ \t]*>>[ \t]*(?:\n|$)")
newRow = buildRegex(ur"\n")

newCellBar = buildRegex(ur"\|")
newCellTab = buildRegex(ur"\t")


def chooseCellEnd(s, l, st, pe):
    """
    """
    if st.dictStack.get("table.tabSeparated", False):
        return newCellTab
    else:
        return newCellBar


newCell = Choice([newCellBar, newCellTab], chooseCellEnd)


tableRow = tableContentInCell + ZeroOrMore(newCell + tableContentInCell)
tableRow = tableRow.setResultsName("tableRow").setParseAction(actionHideOnEmpty)


def actionTableModeAppendix(s, l, st, t):
    for key, data in t.entries:
        if key == "t":
            st.dictStack.getNamedDict("table")["table.tabSeparated"] = True
            return
    
    st.dictStack.getNamedDict("table")["table.tabSeparated"] = False


tableModeAppendix = modeAppendix.setResultsName("tableModeAppendix").addParseAction(actionTableModeAppendix)

table = buildRegex(ur"<<\|").setParseStartAction(preActCheckNothingLeft) + \
        Optional(tableModeAppendix) + buildRegex(ur"[ \t]*\n") + tableRow + ZeroOrMore(newRow + tableRow) + tableEnd
table = table.setResultsName("table")



# -------------------- Suppress highlighting --------------------

suppressHighlightingMultipleLines = buildRegex(ur"<<[ \t]*\n")\
        .setParseStartAction(preActCheckNothingLeft) + \
        buildRegex(ur".*?(?=^[ \t]*>>[ \t]*(?:\n|$))", "plainText") + \
        buildRegex(ur"^[ \t]*>>[ \t]*(?:\n|$)")

suppressHighlightingSingleLine = buildRegex(ur"<<") + \
        buildRegex(ur"[^\n]*?(?=>>)", "plainText") + buildRegex(ur">>")

suppressHighlighting = suppressHighlightingMultipleLines | suppressHighlightingSingleLine



# -------------------- Pre block --------------------

preBlock = buildRegex(ur"<<pre[ \t]*\n")\
        .setParseStartAction(preActCheckNothingLeft) + \
        buildRegex(ur".*?(?=^[ \t]*>>[ \t]*(?:\n|$))", "preText") + \
        buildRegex(ur"^[ \t]*>>[ \t]*(?:\n|$)")
preBlock = preBlock.setResultsName("preBlock")


# -------------------- Auto generated area --------------------
# TODO

# autoGeneratedArea = buildRegex(ur"<<[ \t]+")\
#         .setParseStartAction(preActCheckNothingLeft) + \
#         buildRegex(ur"[^\n]+", "expression") + \
#         buildRegex(ur"\n") + buildRegex(ur".*?(?=>>)", "plainText") + \
#         buildRegex(ur">>[ \t]*$").setParseStartAction(preActCheckNothingLeft)




# -------------------- <pre> html tag --------------------

def actionPreHtmlTag(s, l, st, t):
    """
    Remove the node name so this doesn't become an own NTNode.
    """
    t.name = None



preHtmlStart = buildRegex(ur"<pre(?: [^\n>]*)?>", "htmlTag")\
        .setParseStartAction(createCheckNotIn(("preHtmlTag",)))

preHtmlEnd = buildRegex(ur"</pre(?: [^\n>]*)?>", "htmlTag")

preHtmlTag = preHtmlStart + content + preHtmlEnd
preHtmlTag = preHtmlTag.setResultsName("preHtmlTag")\
        .setParseAction(actionPreHtmlTag)



# -------------------- Wikiwords and URLs --------------------

BracketStart = u"["
BracketStartPAT = ur"\["

BracketEnd = u"]"
BracketEndPAT = ur"\]"
WikiWordNccPAT = ur"[^\\/\[\]\|\000-\037=:;#!]+" # ur"[\w\-\_ \t]+"
WikiWordTitleStartPAT = ur"\|"
WikiWordAnchorStart = u"!"
WikiWordAnchorStartPAT = ur"!"

# Bracket start, escaped for reverse RE pattern (for autocompletion)
BracketStartRevPAT = ur"\["
# Bracket end, escaped for reverse RE pattern (for autocompletion)
BracketEndRevPAT = ur"\]"

WikiWordNccRevPAT = ur"[^\\/\[\]\|\000-\037=:;#!]+?"  # ur"[\w\-\_ \t.]+?"



WikiWordCcPAT = (ur"(?:[" +
        UPPERCASE +
        ur"]+[" +
        LOWERCASE +
        ur"]+[" +
        UPPERCASE +
        ur"]+[" +
        LETTERS + string.digits +
        ur"]*|[" +
        UPPERCASE +
        ur"]{2,}[" +
        LOWERCASE +
        ur"]+)")


UrlPAT = ur'(?:(?:wiki|https?|ftp|rel)://|mailto:|Outlook:\S|file://?)'\
        ur'(?:(?![.,;:!?)]+["\s])[^"\s<>])*'


bracketStart = buildRegex(BracketStartPAT)
bracketEnd = buildRegex(BracketEndPAT)


UnescapeExternalFragmentRE   = re.compile(ur"#(.)",
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
    
    lt2.unescaped = UnescapeExternalFragmentRE.sub(ur"\1", lt2.text)


UnescapeStandardRE = re.compile(EscapePlainCharPAT + ur"(.)",
                              re.DOTALL | re.UNICODE | re.MULTILINE)

def actionSearchFragmentIntern(s, l, st, t):
    lt2 = getFirstTerminalNode(t)
    if lt2 is None:
        return None

    lt2.unescaped = UnescapeStandardRE.sub(ur"\1", lt2.text)


def actionWikiWordNcc(s, l, st, t):
    t.wikiWord = t.findFlatByName("word")
    if t.wikiWord is not None:
        t.wikiWord = t.wikiWord.getString()

    t.titleNode = t.findFlatByName("title")

    fragmentNode = t.findFlatByName("searchFragment")
    if fragmentNode is not None:
        t.searchFragment = fragmentNode.unescaped
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
        t.wikiWord = t.wikiWord.getString()
        try:
            wikiFormatDetails = st.dictStack["wikiFormatDetails"]
            
            if t.wikiWord in wikiFormatDetails.wikiDocument.getCcWordBlacklist():
                raise ParseException(s, l, "CamelCase word is in blacklist")
        except KeyError:
            pass

    t.titleNode = None

    fragmentNode = t.findFlatByName("searchFragment")
    if fragmentNode is not None:
        t.searchFragment = fragmentNode.unescaped
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
    t.appendixNode = t.findFlatByName("urlModeAppendix")

    t.url = t.findFlatByName("url").getString()
    t.titleNode = t.findFlatByName("title")


def actionAnchorDef(s, l, st, t):
    t.anchorLink = t.findFlatByName("anchor").getString()


searchFragmentExtern = buildRegex(ur"#") + \
        buildRegex(ur"(?:(?:#.)|[^ \t\n#])+", "searchFragment")\
        .setParseAction(actionSearchFragmentExtern)

searchFragmentIntern = buildRegex(ur"#") + buildRegex(ur"(?:(?:" + EscapePlainCharPAT +
        ur".)|(?!" + WikiWordTitleStartPAT +
        ur"|" +  BracketEndPAT + ur").)+", "searchFragment")\
        .setParseAction(actionSearchFragmentIntern)

wikiWordAnchorLink = buildRegex(WikiWordAnchorStartPAT) + \
        buildRegex(ur"[A-Za-z0-9\_]+", "anchorLink")


title = buildRegex(WikiWordTitleStartPAT + ur"[ \t]*") + titleContent    # content.setResultsName("title")


wikiWordNccCore = buildRegex(WikiWordNccPAT, "word")

wikiWordNcc = bracketStart + \
        wikiWordNccCore.copy().addParseAction(actionCutRightWhitespace) + \
        Optional(MatchFirst([searchFragmentIntern, wikiWordAnchorLink])) + whitespace + \
        Optional(title) + bracketEnd + \
        Optional(MatchFirst([searchFragmentExtern, wikiWordAnchorLink]))

wikiWordNcc = wikiWordNcc.setResultsName("wikiWord").setName("wikiWordNcc")\
        .setParseAction(actionWikiWordNcc)


anchorDef = buildRegex(ur"^[ \t]*anchor:[ \t]*") + buildRegex(ur"[A-Za-z0-9\_]+",
        "anchor") + buildRegex(ur"\n")
anchorDef = anchorDef.setResultsName("anchorDef").setParseAction(actionAnchorDef)


AnchorRE = re.compile(ur"^[ \t]*anchor:[ \t]*(?P<anchorValue>[A-Za-z0-9\_]+)\n",
        re.DOTALL | re.UNICODE | re.MULTILINE)



urlModeAppendix = modeAppendix.setResultsName("urlModeAppendix")

urlWithAppend = buildRegex(UrlPAT, "url") + Optional(buildRegex(ur">") + \
        urlModeAppendix)

urlBare = urlWithAppend.setResultsName("urlLink")
urlBare = urlBare.setParseAction(actionUrlLink)

urlTitled = bracketStart + urlWithAppend + whitespace + \
        Optional(title) + bracketEnd
# urlTitled = buildRegex(BracketStartPAT) + urlBare.setResultsName("") + whitespace + \
#         buildRegex(WikiWordTitleStartPAT) + whitespace + \
#         content.setResultsName("title") + bracketEnd
urlTitled = urlTitled.setResultsName("urlLink").setParseAction(actionUrlLink)



urlRef = urlTitled | urlBare


# TODO anchor/fragment
wikiWordCc = buildRegex(ur"\b(?<!~)" + WikiWordCcPAT + ur"\b", "word") + \
        Optional(MatchFirst([searchFragmentExtern, wikiWordAnchorLink])) # Group( )
wikiWordCc = wikiWordCc.setResultsName("wikiWord").setName("wikiWordCc")\
        .setParseStartAction(preActCheckWikiWordCcAllowed)\
        .setParseAction(actionWikiWordCc)

wikiWord = wikiWordNcc | wikiWordCc



# Needed for _TheHelper.extractWikiWordFromLink()

extractableWikiWord = (wikiWordNccCore | wikiWordNcc) + stringEnd
extractableWikiWord = extractableWikiWord.setResultsName("extractableWikiWord")\
        .setParseAction(actionExtractableWikiWord).optimize(("regexcombine",))\
        .parseWithTabs()


wikiWordNccRE = re.compile(ur"^" + WikiWordNccPAT + ur"$",
        re.DOTALL | re.UNICODE | re.MULTILINE)


wikiWordCcRE = re.compile(ur"^" + WikiWordCcPAT + ur"$",
        re.DOTALL | re.UNICODE | re.MULTILINE)

def isCcWikiWord(word):
    return bool(wikiWordCcRE.match(word))



# -------------------- Footnotes --------------------

footnotePAT = ur"[0-9]+"

def preActCheckFootnotesAllowed(s, l, st, pe):
    wikiFormatDetails = st.dictStack["wikiFormatDetails"]
    
    if wikiFormatDetails.footnotesAsWws:
        raise ParseException(s, l, "CamelCase words not allowed here")


def actionFootnote(s, l, st, t):
    t.footnoteId = t.findFlatByName("footnoteId").getString()


footnote = bracketStart + buildRegex(footnotePAT, "footnoteId") + bracketEnd
footnote = footnote.setResultsName("footnote")\
        .setParseStartAction(preActCheckFootnotesAllowed)\
        .setParseAction(actionFootnote)


footnoteRE = re.compile(ur"^" + footnotePAT + ur"$",
        re.DOTALL | re.UNICODE | re.MULTILINE)


# -------------------- Properties (=attributes) and insertions --------------------


def actionPropInsValueQuoteStart(s, l, st, t):
    st.dictStack.getSubTopDict()["propInsValueQuote"] = t[0].text

def actionPropInsValueQuoteEnd(s, l, st, t):
#     print "--actionPropInsValueQuoteEnd", repr((l, t[0].text, st.dictStack.getSubTopDict().get("propInsValueQuote")))
    if t[0].text != st.dictStack.getSubTopDict().get("propInsValueQuote"):
        raise ParseException(s, l, "End quote of property/insertion does not match start")


def pseudoActionPropInsQuotedValue(s, l, st, t):
    if t.strLength == 0:
        return []
    t.name = "value"
    return t


def actionProperty(s, l, st, t):
    key = t.findFlatByName("key").getString()
    t.key = key
    t.props = [(key, vNode.getString()) for vNode in t.iterFlatByName("value")]


def actionInsertion(s, l, st, t):
    t.key = t.findFlatByName("key").getString()
    values = list(vNode.getString() for vNode in t.iterFlatByName("value"))
    t.value = values[0]
    del values[0]
    t.appendices = values



propInsQuote = buildRegex(ur"\"+|'+|/+|\\+")
propInsQuoteStart = propInsQuote.copy()\
        .setParseAction(actionPropInsValueQuoteStart)
propInsQuoteEnd = propInsQuote.copy()\
        .setParseAction(actionPropInsValueQuoteEnd)

propInsQuotedValue = FindFirst([], propInsQuoteEnd)\
        .setPseudoParseAction(pseudoActionPropInsQuotedValue)

propInsNonQuotedValue = buildRegex(ur"[\w\-\_ \t:,.!?#%|]*", "value")

propInsValue = whitespace + ((propInsQuoteStart + propInsQuotedValue + \
        propInsQuoteEnd) | propInsNonQuotedValue)

propInsKey = buildRegex(ur"[\w\-\_\.]+", "key")

property = bracketStart + whitespace + propInsKey + \
        buildRegex(ur"[ \t]*[=:]") + propInsValue + \
        ZeroOrMore(buildRegex(ur";") + propInsValue) + bracketEnd
property = property.setResultsName("property").setParseAction(actionProperty)


insertion = bracketStart + buildRegex(ur":") + whitespace + propInsKey + \
        buildRegex(ur"[ \t]*[=:]") + propInsValue + \
        ZeroOrMore(buildRegex(ur";") + propInsValue) + bracketEnd
insertion = insertion.setResultsName("insertion").setParseAction(actionInsertion)



# -------------------- Additional regexes to provide --------------------


# Needed for auto-bullet/auto-unbullet functionality of editor
BulletRE        = re.compile(ur"^(?P<indentBullet>[ \t]*)(?P<actualBullet>\*[ \t])",
        re.DOTALL | re.UNICODE | re.MULTILINE)
NumericSimpleBulletRE = re.compile(ur"^(?P<indentBullet>[ \t]*)(?P<actualBullet>#[ \t])",
        re.DOTALL | re.UNICODE | re.MULTILINE)
NumericBulletRE = re.compile(ur"^(?P<indentNumeric>[ \t]*)(?P<preLastNumeric>(?:\d+\.)*)(\d+)\.[ \t]",
        re.DOTALL | re.UNICODE | re.MULTILINE)


# Needed for handleRewrapText
EmptyLineRE     = re.compile(ur"^[ \t\r\n]*$",
        re.DOTALL | re.UNICODE | re.MULTILINE)




# Reverse REs for autocompletion
revSingleWikiWord    =       (ur"(?:[" +
                             LETTERS + string.digits +
                             ur"]*[" +
                             UPPERCASE+
                             ur"])")   # Needed for auto-completion

RevWikiWordRE      = re.compile(ur"^" +
                             revSingleWikiWord + ur"(?![\~])\b",
                             re.DOTALL | re.UNICODE | re.MULTILINE)
                             # Needed for auto-completion


RevWikiWordRE2     = re.compile(ur"^" + WikiWordNccRevPAT + BracketStartRevPAT,
        re.DOTALL | re.UNICODE | re.MULTILINE)  # Needed for auto-completion

RevPropertyValue     = re.compile(
        ur"^([\w\-\_ \t:;,.!?#/|]*?)([ \t]*[=:][ \t]*)([\w\-\_ \t\.]+?)" +
        BracketStartRevPAT,
        re.DOTALL | re.UNICODE | re.MULTILINE)  # Needed for auto-completion


RevTodoKeyRE = re.compile(ur"^(?:[^:\s]{0,40}\.)??"
        ur"(?:odot|enod|tiaw|noitca|kcart|eussi|noitseuq|tcejorp)",
        re.DOTALL | re.UNICODE | re.MULTILINE)  # Needed for auto-completion

RevTodoValueRE = re.compile(ur"^[^\n:]{0,30}:" + RevTodoKeyRE.pattern[1:],
        re.DOTALL | re.UNICODE | re.MULTILINE)  # Needed for auto-completion


RevWikiWordAnchorRE = re.compile(ur"^(?P<anchorBegin>[A-Za-z0-9\_]{0,20})" +
        WikiWordAnchorStartPAT + ur"(?P<wikiWord>" + RevWikiWordRE.pattern[1:] + ur")",
        re.DOTALL | re.UNICODE | re.MULTILINE)  # Needed for auto-completion
        
RevWikiWordAnchorRE2 = re.compile(ur"^(?P<anchorBegin>[A-Za-z0-9\_]{0,20})" + 
        WikiWordAnchorStartPAT + BracketEndRevPAT + ur"(?P<wikiWord>" + 
        WikiWordNccRevPAT + ur")" + BracketStartRevPAT,
        re.DOTALL | re.UNICODE | re.MULTILINE)  # Needed for auto-completion


# Simple todo RE for autocompletion.
ToDoREWithCapturing = re.compile(ur"^([^:\s]+):[ \t]*(.+?)$",
        re.DOTALL | re.UNICODE | re.MULTILINE)



# For auto-link mode relax
AutoLinkRelaxSplitRE = re.compile(r"[\W]+", re.IGNORECASE | re.UNICODE)

AutoLinkRelaxJoinPAT = ur"[\W]+"
AutoLinkRelaxJoinFlags = re.IGNORECASE | re.UNICODE



# For spell checking
TextWordRE = re.compile(ur"(?P<negative>[0-9]+|"+ UrlPAT + u"|\b(?<!~)" +
        WikiWordCcPAT + ur"\b)|\b[\w']+",
        re.DOTALL | re.UNICODE | re.MULTILINE)





# -------------------- End tokens --------------------


TOKEN_TO_END = {
        "bold": boldEnd,
        "italics": italicsEnd,
        "unorderedList": lessIndentOrEnd,
        "orderedList": lessIndentOrEnd,
        "indentedText": lessIndentOrEnd,
        "wikiWord": bracketEnd,
        "urlLink": bracketEnd,
        "table": tableEnd,
        "preHtmlTag": preHtmlEnd,
        "heading": headingEnd,
        "todoEntry": todoEnd
    }


def chooseEndToken(s, l, st, pe):
    """
    """
    for tokName in reversed(st.nameStack):
        end = TOKEN_TO_END.get(tokName)
        if end is not None:
            return end

    return stringEnd


endToken = Choice([stringEnd]+TOKEN_TO_END.values(), chooseEndToken)

endTokenInTable = endToken | newCell | newRow


# -------------------- Content definitions --------------------


findMarkupInCell = FindFirst([bold, italics, suppressHighlightingSingleLine,
        urlRef, insertion, escapedChar, footnote, wikiWord,    # wikiWordNcc, wikiWordCc,
        htmlTag, htmlEntity], endTokenInTable)
findMarkupInCell = findMarkupInCell.setPseudoParseAction(pseudoActionFindMarkup)

temp = ZeroOrMore(NotAny(endTokenInTable) + findMarkupInCell)
temp = temp.leaveWhitespace().parseWithTabs()
tableContentInCell << temp



endTokenInTitle = endToken | buildRegex(ur"\n")


findMarkupInTitle = FindFirst([bold, italics, suppressHighlightingSingleLine,
        urlRef, insertion, escapedChar, footnote, htmlTag, htmlEntity],
        endTokenInTitle)
findMarkupInTitle = findMarkupInTitle.setPseudoParseAction(pseudoActionFindMarkup)

temp = ZeroOrMore(NotAny(endTokenInTitle) + findMarkupInTitle)
temp = temp.leaveWhitespace().parseWithTabs()
titleContent << temp



findMarkupInHeading = FindFirst([bold, italics, suppressHighlightingSingleLine,
        urlRef, insertion, escapedChar, footnote, wikiWord, htmlTag,   # wikiWordNcc, wikiWordCc,
        htmlEntity], endToken)
findMarkupInHeading = findMarkupInHeading.setPseudoParseAction(
        pseudoActionFindMarkup)

temp = ZeroOrMore(NotAny(endToken) + findMarkupInHeading)
temp = temp.leaveWhitespace().parseWithTabs()
headingContent << temp



findMarkupInTodo = FindFirst([bold, italics, suppressHighlightingSingleLine,
        urlRef, property, insertion, escapedChar, footnote, wikiWord,   # wikiWordNcc, wikiWordCc,
        htmlTag, htmlEntity], endToken)
findMarkupInTodo = findMarkupInTodo.setPseudoParseAction(
        pseudoActionFindMarkup)

temp = OneOrMore(NotAny(endToken) + findMarkupInTodo)
temp = temp.leaveWhitespace().parseWithTabs()
todoContent << temp



findMarkup = FindFirst([bold, italics, suppressHighlightingSingleLine, urlRef,
        property, insertion, escapedChar, footnote, wikiWord,
        newLinesParagraph, newLineLineBreak, newLineWhitespace, heading,
        todoEntry, anchorDef, preHtmlTag, htmlTag,
        htmlEntity, bulletEntry, unorderedList, numberEntry, orderedList,
        indentedText, table, preBlock, suppressHighlightingMultipleLines,
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


# text.setDebugRecurs(GR_DEBUG)



def _buildBaseDict(wikiDocument=None, formatDetails=None):
    if formatDetails is None:
        if wikiDocument is None:
            formatDetails = WikiDocument.getUserDefaultWikiPageFormatDetails()
        else:
            formatDetails = wikiDocument.getWikiDefaultWikiPageFormatDetails()

    return {"indentInfo": IndentInfo("normal"),
            "wikiFormatDetails": formatDetails
        }



# -------------------- API for plugin WikiParser --------------------
# During alpha state of the WikidPad version, this API isn't stable yet, 
# so changes may occur!


class _TheParser(object):
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
        return "wikidpad_default_2_0"



    @staticmethod
    def _postProcessing(intLanguageName, content, formatDetails, pageAst,
            threadstop):
        """
        Do some cleanup after main parsing.
        Not part of public API.
        """
#         # Step one: coalesce "plainText" nodes
#         def recursCoalesce(ast):
#             prevNode = None
#             newAstNodes = []
#             for node in ast.getChildren():
#                 # This should be safe for this parser, but not for all
#                 if node.strLength == 0:
#                     continue
# 
#                 if isinstance(node, NonTerminalNode):
#                     prevNode = None
#                     node = recursCoalesce(node)
# #                     if node is not None:
#                     newAstNodes.append(node)
#                     continue
# 
#                 if node.name == "plainText":
#                     if prevNode is None:
#                         prevNode = node
#                         newAstNodes.append(node)
#                         continue
#                     else:
#                         prevNode.text += node.text
#                         prevNode.strLength = len(prevNode.text)
#                         continue
# 
#                 prevNode = None
#                 newAstNodes.append(node)
# 
#             ast.sub = newAstNodes
# 
#             return ast
#         
#         pageAst = recursCoalesce(pageAst)


        # Step two: Search for auto-links and add them
        autoLinkRelaxRE = None
        if formatDetails.autoLinkMode == u"relax":
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
                        
                        threadstop.testRunning()
                        while text != u"":
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
                            if preText != u"":
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
                                wwNode.titleNode = None
                                        
                               
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



_RE_LINE_INDENT = re.compile(ur"^[ \t]*")

class _TheHelper(object):
    @staticmethod
    def reset():
        pass

    @staticmethod
    def getWikiLanguageName():
        return "wikidpad_default_2_0"


    # TODO More descriptive error messages (which character(s) is/are wrong?)
    @staticmethod   # isValidWikiWord
    def checkForInvalidWikiWord(word, wikiDocument=None, settings=None):
        """
        Test if word is syntactically a valid wiki word and no settings
        are against it. The camelCase black list is not checked.
        The function returns None, IFF THE WORD IS VALID, an error string
        otherwise
        """
        if settings is not None and settings.has_key("footnotesAsWws"):
            footnotesAsWws = settings["footnotesAsWws"]
        else:
            if wikiDocument is None:
                footnotesAsWws = False
            else:
                footnotesAsWws = wikiDocument.getWikiConfig().getboolean(
                        "main", "footnotes_as_wikiwords", False)

        if not footnotesAsWws and footnoteRE.match(word):
            return _(u"This is a footnote")

        if wikiWordNccRE.match(word):
            return None
        else:
            return _(u"This is syntactically not a wiki word")


    @staticmethod
    def extractWikiWordFromLink(word, wikiDocument=None):
        """
        Strip brackets and other link details if present and return wikiWord
        if a valid wiki word can be extracted, None otherwise.
        """
        baseDict = _buildBaseDict(wikiDocument=wikiDocument)
        try:
            t = extractableWikiWord.parseString(word, parseAll=True,
                    baseDict=baseDict)
            t = t[0]
            return t.wikiWord
        except ParseException:
            return None


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
        parts = [p for p in parts if p != u""]

        # Instead of original non-alphanum characters allow arbitrary
        # non-alphanum characters
        pat = ur"\b" + (AutoLinkRelaxJoinPAT.join(parts)) + ur"\b"
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
                for w in words if w != u""]


    @staticmethod
    def createLinkFromWikiWord(word, wikiPage):    # normalizeWikiWord
        """
        Create a link from word which should be put on wikiPage.
        """
        if isCcWikiWord(word):
            wikiFormatDetails = wikiPage.getFormatDetails()
            if wikiFormatDetails.withCamelCase:
                ccBlacklist = wikiDocument.getCcWordBlacklist()
                if not word in ccBlacklist:
                    return word

        return BracketStart + word + BracketEnd


    @staticmethod
    def createStableLinksFromWikiWords(words, wikiPage=None):
        """
        Create particularly stable links from a list of words which should be
        put on wikiPage.
        """
        return u"".join([u"%s%s%s\n" % (BracketStart, w, BracketEnd)
                for w in words])


    @staticmethod
    def createAttributeFromComponents(key, value, wikiPage=None):
        """
        Build an attribute from key and value.
        TODO: Check for necessary escaping
        """
        return u"%s%s: %s%s\n" % (BracketStart, key, value, BracketEnd)


    @staticmethod
    def findNextWordForSpellcheck(text, startPos, wikiPage):
        """
        Find in text next word to spellcheck, beginning at position startPos
        
        Returns tuple (start, end, spWord) which is either (None, None, None)
        if no more word can be found or returns start and after-end of the
        spWord to spellcheck.
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
            wikiDocument, settings):
        """
        Called when user wants autocompletion.
        text -- Whole text of page
        charPos -- Cursor position in characters
        lineStartCharPos -- For convenience and speed, position of the 
                start of text line in which cursor is.
        wikiDocument -- wiki document object
        closingBracket -- boolean iff a closing bracket should be suggested
                for bracket wikiwords and properties

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

        # TODO Sort entries appropriately (whatever this means)

        wikiData = wikiDocument.getWikiData()

        mat1 = RevWikiWordRE.match(rline)
        if mat1:
            # may be CamelCase word
            tofind = line[-mat1.end():]
            ccBlacklist = wikiDocument.getCcWordBlacklist()
            for word in wikiData.getWikiLinksStartingWith(tofind, True, True):
                if not isCcWikiWord(word) or word in ccBlacklist:
                    continue
                
                backStepMap[word] = len(tofind)

        mat2 = RevWikiWordRE2.match(rline)
        mat3 = RevPropertyValue.match(rline)
        if mat2:
            # may be not-CamelCase word or in a property name
            tofind = line[-mat2.end():]
            
            # Should a closing bracket be appended to suggested words?
            if closingBracket:
                wordBracketEnd = BracketEnd
            else:
                wordBracketEnd = u""

            for word in wikiData.getWikiLinksStartingWith(
                    tofind[len(BracketStart):], True, True):
                backStepMap[BracketStart + word +
                        wordBracketEnd] = len(tofind)

            for prop in wikiData.getPropertyNamesStartingWith(
                    tofind[len(BracketStart):]):
                backStepMap[BracketStart + prop] = len(tofind)
        elif mat3:
            # In a property value
            tofind = line[-mat3.end():]
            propkey = revStr(mat3.group(3))
            propfill = revStr(mat3.group(2))
            propvalpart = revStr(mat3.group(1))
            values = filter(lambda pv: pv.startswith(propvalpart),
                    wikiData.getDistinctPropertyValues(propkey))

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

                tdmat = ToDoREWithCapturing.match(td)
                key = tdmat.group(1) + u":"
                backStepMap[key] = len(tofind)

        mat = RevTodoValueRE.match(rline)
        if mat:
            # Might be todo entry
            tofind = line[-mat.end():]
            todos = [t[1] for t in wikiData.getTodos() if t[1].startswith(tofind)]
            for t in todos:
                backStepMap[t] = len(tofind)

        mat = RevWikiWordAnchorRE2.match(rline)
        if mat:
            # In an anchor of a possible bracketed wiki word
            tofind = line[-mat.end():]
            wikiWord = revStr(mat.group("wikiWord"))
            anchorBegin = revStr(mat.group("anchorBegin"))

            try:
                page = wikiDocument.getWikiPage(wikiWord) # May throw exception
                anchors = [a for a in page.getAnchors()
                        if a.startswith(anchorBegin)]

                for a in anchors:
                    backStepMap[BracketStart + wikiWord +
                            BracketEnd +
                            WikiWordAnchorStart + a] = len(tofind)
            except WikiWordNotFoundException:
                # wikiWord isn't a wiki word
                pass

        mat = RevWikiWordAnchorRE.match(rline)
        if mat:
            # In an anchor of a possible camel case word
            tofind = line[-mat.end():]
            wikiWord = revStr(mat.group("wikiWord"))
            anchorBegin = revStr(mat.group("anchorBegin"))

            try:
                page = wikiDocument.getWikiPage(wikiWord) # May throw exception
                anchors = [a for a in page.getAnchors()
                        if a.startswith(anchorBegin)]
                        
                for a in anchors:
                    backStepMap[wikiWord + WikiWordAnchorStart +
                            a] = len(tofind)
            except WikiWordNotFoundException:
                # wikiWord isn't a wiki word
                pass


        acresult = backStepMap.keys()
        
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
                if mat.group("preLastNumeric") != u"":
                    replacement += mat.group("preLastNumeric") + u" "

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
                    adjustment = len(str(nextNum)) - len(prevNumStr)
                    if adjustment == 0:
                        editor.AddText(u"%s%s%d. " % (indent,
                                match.group(2), int(prevNum)+1))
                    else:
                        editor.AddText(u"%s%s%d. " % (u" " *
                                (editor.GetLineIndentation(currentLine - 1) - adjustment),
                                match.group(2), int(prevNum)+1))
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
                subIndent = indent + u"  "
            else:
                match = NumericBulletRE.match(editor.GetLine(startLine))
                if match:
                    subIndent = indent + u" " * (len(match.group(2)) + 2)

            # get the text that will be wrapped
            text = editor.GetTextRange(startPos, endPos)
            # remove spaces, newlines, etc
            text = re.sub("[\s\r\n]+", " ", text)

            # wrap the text
            wrapPosition = 70
            try:
                wrapPosition = int(
                        editor.getLoadedDocPage().getPropertyOrGlobal(
                        "wrap", "70"))
            except:
                pass

            # make the min wrapPosition 5
            if wrapPosition < 5:
                wrapPosition = 5

            filledText = fill(text, width=wrapPosition,
                    initial_indent=indent, 
                    subsequent_indent=subIndent)

            # replace the text based on targetting
            editor.SetTargetStart(startPos)
            editor.SetTargetEnd(endPos)
            editor.ReplaceTarget(filledText)
            editor.GotoPos(curPos)




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

    return (("wikidpad_default_2_0", u"WikidPad default 2.0", parserFactory,
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



# print t.pprint()



