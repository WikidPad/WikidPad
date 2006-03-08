import os, traceback, codecs, array, string, re
from StringOps import *
from Utilities import DUMBTHREADHOLDER

import WikiFormatting


class Ast(object):
    __slots__ = ("__weakref__",)

    def __init__(self):
        pass
        
    def findType(self, typeToFind):
        """
        Find all tokens of specified type, also in subtoken lists
        """
        result = []
        self._findType(typeToFind, result)
        return result
        
    def _findType(self, typeToFind, result):
        pass

    def getTokensForPos(self, pos):
        return []




def _enrichTokens(formatting, tokens, formatDetails, threadholder):
    for tok in tokens:
        if not threadholder.isCurrent():
            return

        if tok.ttype == WikiFormatting.FormatTypes.ToDo:
            node = Todo()
            node.buildSubAst(formatting, tok, formatDetails, threadholder)
            tok.node = node
        elif tok.ttype == WikiFormatting.FormatTypes.Table:
            node = Table()
            node.buildSubAst(formatting, tok, formatDetails, threadholder)
            tok.node = node
        elif tok.ttype == WikiFormatting.FormatTypes.WikiWord:
            node = WikiWord()
            node.buildSubAst(formatting, tok, formatDetails, threadholder)
            tok.node = node
        elif tok.ttype == WikiFormatting.FormatTypes.Url:
            node = Url()
            node.buildSubAst(formatting, tok, formatDetails, threadholder)
            tok.node = node
        elif tok.ttype == WikiFormatting.FormatTypes.EscapedChar:
            node = EscapeCharacter()
            node.buildSubAst(formatting, tok, formatDetails, threadholder)
            tok.node = node

           

def _findTokensForPos(tokens, pos):
    # Algorithm taken from standard lib bisect module
    if tokens is None:
        return []

    lo = 0
    hi = len(tokens)
    while lo < hi:
        mid = (lo+hi)//2
        if pos < tokens[mid].start: hi = mid
        else: lo = mid+1
        
    index = lo - 1

    if index == -1:
        # Before first token
        return []

    tok = tokens[index]

    if lo == len(tokens) and pos >= (len(tok.text) + tok.start):
        # After last token
        return []

    if tok.node is not None:
        result = tok.node.getTokensForPos(pos)
        result.append(tok)
        return result
    else:
        return [tok]


class Page(Ast):
    __slots__ = ("tokens",)

    def __init__(self):
        Ast.__init__(self)
        self.tokens = None
        
    def getTokens(self):
        """
        Return all top-level tokens the page consists of
        """
        return self.tokens
        
    def getTokensForPos(self, pos):
        return _findTokensForPos(self.tokens, pos)
        
    def buildAst(self, formatting, text, formatDetails=None,
            threadholder=DUMBTHREADHOLDER):
        self.tokens = formatting.tokenizePage(text, formatDetails=formatDetails,
                threadholder=threadholder)
        
        _enrichTokens(formatting, self.tokens, formatDetails, threadholder)
        
    def findTypeFlat(self, typeToFind):
        """
        Non-recursive search for tokens of the specified type
        """
        return [tok for tok in self.tokens if tok.ttype == typeToFind]


    def _findType(self, typeToFind, result):
        for tok in self.tokens:
            if tok.ttype == typeToFind:
                result.append(tok)
            
            if tok.node is not None:
                tok.node._findType(typeToFind, result)


class Todo(Ast):
    __slots__ = ("indent", "name", "delimiter", "valuetokens")

    def __init__(self):
        Ast.__init__(self)
        
    def getTokensForPos(self, pos):
        return _findTokensForPos(self.valuetokens, pos)

    def buildSubAst(self, formatting, token, formatDetails=None,
            threadholder=DUMBTHREADHOLDER):
        # First three parts are simple
        groupdict = token.grpdict
        self.indent = groupdict["todoIndent"]
        self.name = groupdict["todoName"]
        self.delimiter = groupdict["todoDelimiter"]
        
        relpos = token.start + len(self.indent) + len(self.name) + \
                len(self.delimiter)
        
        value = groupdict["todoValue"]
        self.valuetokens = formatting.tokenizeTodo(value,
                formatDetails=formatDetails, threadholder=threadholder)

        # The valuetokens contain start position relative to beginning of
        # value. This must be corrected to position rel. to whole page

        for t in self.valuetokens:
            t.start += relpos
            
        _enrichTokens(formatting, self.valuetokens, formatDetails, threadholder)


    def _findType(self, typeToFind, result):
        for tok in self.valuetokens:
            if tok.ttype == typeToFind:
                result.append(tok)
            if tok.node is not None:
                tok.node._findType(typeToFind, result)
        

def tokenizeTodoValue(formatting, value):
    """
    Tokenize the value (the right side) of a todo and return enriched
    tokens. Used by WikiTreeCtrl to handle properties in todo items
    """
    formatDetails = WikiFormatting.WikiPageFormatDetails()
    tokens = formatting.tokenizeTodo(value,
            formatDetails)
    
    _enrichTokens(formatting, tokens, formatDetails, DUMBTHREADHOLDER)
    
    return tokens

        


            
class Table(Ast):
    __slots__ = ("begin", "end", "contenttokens")

    def __init__(self):
        Ast.__init__(self)
        
        self.contenttokens = None

    def getTokensForPos(self, pos):
        return _findTokensForPos(self.contenttokens, pos)

    def buildSubAst(self, formatting, token, formatDetails=None,
            threadholder=DUMBTHREADHOLDER):
        groupdict = token.grpdict
        self.begin = groupdict["tableBegin"]
        self.end = groupdict["tableEnd"]
        content = groupdict["tableContent"]
      
        tokensIn = formatting.tokenizeTableContent(content,
                formatDetails=formatDetails, threadholder=threadholder)
        relpos = token.start + len(self.begin)
        
        contenttokens = []

        # Filter out empty tokens and relocate them
        for t in tokensIn:
            if t.text == u"":
                continue
            t.start += relpos
            contenttokens.append(t)
            
        self.contenttokens = contenttokens


#         cells = formatting.tableCutRe.findall(content)
# 
#         contenttokens = []
#         relpos = token.start + len(self.begin)
#         for c in cells:
#             if not threadholder.isCurrent():
#                 return
# 
#             tokensIn = formatting.tokenizeCell(c, formatDetails=formatDetails,
#                     threadholder=threadholder)
#             tokensOut = []
#             # Filter out empty tokens
#             for t in tokensIn:
#                 if t.text == u"":
#                     continue
#                 t.start += relpos
#                 tokensOut.append(t)
#             
#             relpos += len(c)
#             contenttokens += tokensOut
# 
#         self.contenttokens = contenttokens

        _enrichTokens(formatting, self.contenttokens, formatDetails,
                threadholder)


    def _findType(self, typeToFind, result):
        for tok in self.contenttokens:
            if tok.ttype == typeToFind:
                result.append(tok)
            if tok.node is not None:
                tok.node._findType(typeToFind, result)
                
    def calcGrid(self):
        grid = []
        row = []
        cell = []
#         print "calcGrid1", repr(self.contenttokens)
        for t in self.contenttokens:
#             if t.ttype == WikiFormatting.FormatTypes.Default:
#                 if t.text == u"\n":
#                     if len(cell) > 0:
#                         row.append(cell)
#                         cell = []
#                     if len(row) > 0:
#                         grid.append(row)
#                         row = []
#                     continue
#                 elif t.text == u"|":
#                     row.append(cell)
#                     cell = []
#                     continue
            if t.ttype == WikiFormatting.FormatTypes.TableRowSplit:
                if len(cell) > 0:
                    row.append(cell)
                    cell = []
                if len(row) > 0:
                    grid.append(row)
                    row = []
                continue
            elif t.ttype == WikiFormatting.FormatTypes.TableCellSplit:
                row.append(cell)
                cell = []
                continue

            cell.append(t)
            
        if len(cell) > 0:
            row.append(cell)
            cell = []
        if len(row) > 0:
            grid.append(row)
            row = []
            
        return grid


class WikiWord(Ast):
    __slots__ = ("nakedWord", "searchFragment", "titleTokens")

    def __init__(self):
        Ast.__init__(self)

    def getTokensForPos(self, pos):
        return _findTokensForPos(self.titleTokens, pos)

    def buildSubAst(self, formatting, token, formatDetails=None,
            threadholder=DUMBTHREADHOLDER):
        groupdict = token.grpdict
        frag = groupdict.get("wikiwordnccSearchfrag")
        if frag is None:
            frag = groupdict.get("wikiwordSearchfrag")
        self.searchFragment = frag
        
        nw = groupdict.get("wikiwordncc")
        if nw is None:
            nw = groupdict.get("wikiword")
            
        self.nakedWord = nw.strip()
        
        title = groupdict.get("wikiwordnccTitle")
        if title is None:
            self.titleTokens = None
            return
            
        relpos = token.start + 1 + len(nw) + len(groupdict.get("wikiwordnccDelim"))
#         if title is not None:
#             relpos += len(title)

#         delimPos = title.rindex(formatting.TitleWikiWordDelimiter)
#         title = title[:delimPos]

        self.titleTokens = formatting.tokenizeTitle(title,
                formatDetails=formatDetails, threadholder=threadholder)
                
        for t in self.titleTokens:
            t.start += relpos

        _enrichTokens(formatting, self.titleTokens, formatDetails, threadholder)


    def _findType(self, typeToFind, result):
        if self.titleTokens is None:
            return

        for tok in self.titleTokens:
            if tok.ttype == typeToFind:
                result.append(tok)
            if tok.node is not None:
                tok.node._findType(typeToFind, result)



class Url(Ast):
    __slots__ = ("url", "titleTokens")

    def __init__(self):
        Ast.__init__(self)

    def getTokensForPos(self, pos):
        return _findTokensForPos(self.titleTokens, pos)

    def buildSubAst(self, formatting, token, formatDetails=None,
            threadholder=DUMBTHREADHOLDER):
        groupdict = token.grpdict
        
        url = groupdict.get("titledurlUrl")
        if url is None:
            self.url = token.text
            self.titleTokens = None
            return
        
        self.url = url.strip()
        
        title = groupdict.get("titledurlTitle")
        if title is None:
            self.titleTokens = None
            return
            
        relpos = token.start + 1 + len(url) + len(groupdict.get("titledurlDelim"))

#         delimPos = title.rindex(formatting.TitleWikiWordDelimiter)
#         title = title[:delimPos]

        self.titleTokens = formatting.tokenizeTitle(title,
                formatDetails=formatDetails, threadholder=threadholder)
                
        for t in self.titleTokens:
            t.start += relpos

        _enrichTokens(formatting, self.titleTokens, formatDetails, threadholder)


    def _findType(self, typeToFind, result):
        if self.titleTokens is None:
            return

        for tok in self.titleTokens:
            if tok.ttype == typeToFind:
                result.append(tok)
            if tok.node is not None:
                tok.node._findType(typeToFind, result)


class EscapeCharacter(Ast):
    __slots__ = ("unescaped")

    def __init__(self):
        Ast.__init__(self)

    def buildSubAst(self, formatting, token, formatDetails=None,
            threadholder=DUMBTHREADHOLDER):
#        if token.text[1] in u"\n\r\f|*_[]\\":
            self.unescaped = token.text[1]
#         else:
#             self.unescaped = token.text
