import re, traceback

from .WikiPyparsing import *


# The specialized optimizer in WikiPyParsing can't handle automatic whitespace
# removing
ParserElement.setDefaultWhitespaceChars("")


RE_FLAGS = re.DOTALL | re.UNICODE | re.MULTILINE

def buildRegex(regex, resName=None, hideOnEmpty=False, name=None):
    if resName is None:
        element = Regex(regex, RE_FLAGS)
    else:
        element = Regex(regex, RE_FLAGS).setResultsName(resName)
    
    if name is None:
        name = resName

    if name is not None:    
        element = element.setName(name)

    if hideOnEmpty:
        element.setParseAction(actionHideOnEmpty)

    return element

stringEnd = buildRegex(r"(?!.)", "stringEnd", name="end of string")



searchExpression = Forward()

def actionHide(s, l, st, t):
    return []


def actionValueQuoteStart(s, l, st, t):
    st.dictStack.getSubTopDict()["valueQuote"] = t[0].text

def actionValueQuoteEnd(s, l, st, t):
    if t[0].text != st.dictStack.getSubTopDict().get("valueQuote"):
        raise ParseException(s, l, "End quote does not match start")


def pseudoActionQuotedTerm(s, l, st, t):
    if t.strLength == 0:
        return []
    t.name = "regexTerm"
    t.regexTerm = t.getText()

    return t

def actionNonQuotedTerm(s, l, st, t):
    # Subtract last whitespace (or string end) from length of actual term
    termLen = t.strLength - t[-1].strLength
    if termLen == 0:
        return []

    t.name =  "regexTerm"
    t.regexTerm = t.getString()[:termLen]


def actionPrefixedTerm(s, l, st, t):
    # Try to find a quoted term
    ptt = t.findFlatByName("regexTerm")
    if ptt is not None:
        t.prefixedTerm = ptt.regexTerm
        return

    # Else find a non-quoted snippet
    t.prefixedTerm = t.findFlatByName("nonQuotedTermSnippet").getText()


def actionParameterTermOpt(s, l, st, t):
    # Try to find a quoted term
    ptt = t.findFlatByName("regexTerm")
    if ptt is not None:
        t.parameterTerm = ptt.regexTerm
        return

    # Else find a non-quoted snippet
    ptt = t.findFlatByName("nonQuotedTermSnippetNoColon")
    if ptt is not None:
        t.parameterTerm = ptt.getText()
        return

    t.parameterTerm = ""


def actionAttributeTerm(s, l, st, t):
    t.key = t.findFlatByName("key").parameterTerm
    
    ptt = t.findFlatByName("value")
    if ptt is None:
        t.value = ""
    else:
        t.value = ptt.parameterTerm


def actionPageTerm(s, l, st, t):
    t.pageName = t.findFlatByName("pageName").parameterTerm



def actionOneOp(s, l, st, t):
    t.op = t.findFlatByName("op")


def actionTwoOpsLeft(s, l, st, t):
    t.op1 = t.findFlatByName("op1")
    t.op2 = t.findFlatByName("op2")




whitespace = buildRegex(r"[ \t]+")
# whitespace = whitespace.setParseAction(actionHide)

optWhitespace = buildRegex(r"[ \t]*")
# optWhitespace = optWhitespace.setParseAction(actionHide)

whitespaceOrEnd = whitespace | stringEnd


keyParenOpen = buildRegex(r"\(", name="'('") + whitespaceOrEnd
keyParenClose = buildRegex(r"\)", name="')'") + whitespaceOrEnd

keyNot = buildRegex(r"[nN][oO][tT]") + whitespaceOrEnd
keyAnd = buildRegex(r"[aA][nN][dD]") + whitespaceOrEnd
keyOr = buildRegex(r"[oO][rR]") + whitespaceOrEnd
# keyPrefixKey = buildRegex(ur"key:")
# keyPrefixValue = buildRegex(ur"val(?:ue)?:")
keyPrefixAtt = buildRegex(r"att(?:r)?:")
keyPrefixTodo = buildRegex(r"todo:")
keyPrefixPage = buildRegex(r"page:")


keyWord = keyParenOpen | keyParenClose | keyNot | keyAnd | keyOr | \
        keyPrefixAtt | keyPrefixTodo | keyPrefixPage


valueQuote = buildRegex("\"+|'+|/+", name="quoting")
valueQuoteStart = valueQuote.copy().setParseAction(actionValueQuoteStart)
valueQuoteEnd = valueQuote.copy().setParseAction(actionValueQuoteEnd)

quotedTerm = valueQuoteStart + FindFirst([], valueQuoteEnd)\
        .setPseudoParseAction(pseudoActionQuotedTerm) + valueQuoteEnd + \
        whitespaceOrEnd


nonQuotedTermSnippetNoColon = NotAny(keyWord) + buildRegex(r"[^ \t:]*",
        "nonQuotedTermSnippetNoColon",
        name="non whitespace search snippet without colon")

nonQuotedTermSnippet = NotAny(keyWord) + buildRegex(r"[^ \t]+",
        "nonQuotedTermSnippet", name="non whitespace search snippet")
nonQuotedTerm = OneOrMore(nonQuotedTermSnippet + whitespaceOrEnd)
nonQuotedTerm = nonQuotedTerm.setParseAction(actionNonQuotedTerm)


parameterTermOpt = quotedTerm | ( NotAny(keyWord) + buildRegex(r"[^ \t:]*",
        "nonQuotedTermSnippetNoColon",
        name="non whitespace regular expression without colon") )
parameterTermOpt = parameterTermOpt.setResultsNameNoCopy("parameterTerm")\
        .setParseAction(actionParameterTermOpt)


parameterTerm = quotedTerm | ( NotAny(keyWord) + buildRegex(r"[^ \t:]+",
        "nonQuotedTermSnippetNoColon",
        name="non whitespace regular expression without colon") )
parameterTerm = parameterTerm.setResultsNameNoCopy("parameterTerm")\
        .setParseAction(actionParameterTermOpt)


attributeTerm = keyPrefixAtt + buildRegex(r" ?") + \
        parameterTermOpt.setResultsName("key") + optWhitespace + \
        Optional( buildRegex(r": ?") + 
        parameterTerm.setResultsName("value") + optWhitespace )

attributeTerm = attributeTerm.setResultsNameNoCopy("attributeTerm")\
        .setParseAction(actionAttributeTerm)


todoTerm = keyPrefixTodo + buildRegex(r" ?") + \
        parameterTermOpt.setResultsName("key") + optWhitespace + \
        Optional( buildRegex(r": ?") + 
        parameterTerm.setResultsName("value") + optWhitespace )

todoTerm = todoTerm.setResultsNameNoCopy("todoTerm")\
        .setParseAction(actionAttributeTerm)


pageTerm = keyPrefixPage + buildRegex(r" ?") + \
        parameterTerm.setResultsName("pageName") + optWhitespace

pageTerm = pageTerm.setResultsNameNoCopy("pageTerm")\
        .setParseAction(actionPageTerm)




# todoTerm = keyPrefixTodo + buildRegex(ur" ?") + \
#         (quotedTerm | nonQuotedTermSnippet) + optWhitespace
# todoTerm = todoTerm.setResultsNameNoCopy("todoTerm")\
#         .setParseAction(actionPrefixedTerm)


# attributeValueTerm = keyPrefixValue + buildRegex(ur" ?") + \
#         (quotedTerm | nonQuotedTermSnippet) + optWhitespace
# attributeValueTerm = attributeValueTerm.setResultsNameNoCopy("attributeValueTerm")\
#         .setParseAction(actionPrefixedTerm)


regexTerm = quotedTerm | nonQuotedTerm



parensExpression = keyParenOpen + searchExpression + keyParenClose

exprLevel1 = Forward()

notExpression = keyNot + exprLevel1.setResultsName("op")
notExpression = notExpression.setResultsNameNoCopy("notExpression")\
        .setParseAction(actionOneOp)

exprLevel1 << (notExpression | parensExpression | attributeTerm | todoTerm |
        pageTerm | regexTerm)


orExpression = exprLevel1.setResultsName("op1") + keyOr + Group(searchExpression).setResultsName("op2")
orExpression = orExpression.setResultsNameNoCopy("orExpression")\
        .setParseAction(actionTwoOpsLeft)

andExpression = exprLevel1.setResultsName("op1") + keyAnd + Group(searchExpression).setResultsName("op2")
andExpression = andExpression.setResultsNameNoCopy("andExpression")\
        .setParseAction(actionTwoOpsLeft)

concatExprLevel1 = exprLevel1.setResultsName("op1") + Group(searchExpression).setResultsName("op2")
concatExprLevel1 = concatExprLevel1.setResultsNameNoCopy("concatExprLevel1")\
        .setParseAction(actionTwoOpsLeft)

exprLevel2 = orExpression | andExpression | concatExprLevel1 | exprLevel1


# searchExpression << (notExpression | orExpression | andExpression |
#         parensExpression | searchTerm) + optWhitespace
searchExpression << (exprLevel2 + optWhitespace)
searchExpression.setResultsNameNoCopy("searchExpression")


toSearch = optWhitespace + searchExpression + stringEnd
toSearch.parseWithTabs()
toSearch.optimize(("regexcombine",)).parseWithTabs()


# toSearch.setDebugRecurs(True)


def parse(content):
    """
    Parse the  content  written in wiki language  intLanguageName  using
    formatDetails  and regularly call  threadstop.testValidThread()  to
    raise exception if execution thread is no longer current parsing
    thread.
    """
    global toSearch

    if len(content) == 0:
        return buildSyntaxNode([], 0, "searchExpression")

##         _prof.start()
    try:
        t = toSearch.parseString(content, parseAll=True)
        t = buildSyntaxNode(t, 0, "searchExpression")
    finally:
##             _prof.stop()
        pass

    return t


