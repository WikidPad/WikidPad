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
        
    def getText(self):
        """
        Return the plain text the ast or ast part consists of
        """
        assert 0  # Abstract
        
    def getLength(self):
        """
        Return the length of the plain text the ast or ast part consists of
        """
        # Default implementation
        return len(self.getText())


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
            if formatting.isInCcWordBlacklist(tok.text):
                # word is in camelcase blacklist, so make it normal text
                tok.ttype = WikiFormatting.FormatTypes.Default
            else:
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
        elif tok.ttype == WikiFormatting.FormatTypes.Insertion:
            node = Insertion()
            node.buildSubAst(formatting, tok, formatDetails, threadholder)
            tok.node = node            



def _getRealTextForTokens(tokens):
    """
    Returns the concatenated real text of a sequence of tokens
    """
    return u"".join([t.getRealText() for t in tokens])


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


def iterWords(pageast):
    """
    Generator to find all words in page, generates a sequence of
    (start, end, word) tuples. Used for spell checking
    """
    for texttoken in pageast.getTextualTokens():
        for mat in WikiFormatting.TextWordRE.finditer(texttoken.text):
            yield (mat.start() + texttoken.start, mat.end() + texttoken.start,
                    mat.group(0))


class Page(Ast):
    __slots__ = ("tokens",)

    def __init__(self):
        Ast.__init__(self)
        self.tokens = None
        
    def getText(self):
        return _getRealTextForTokens(self.tokens)
        
    def getTokens(self):
        """
        Return all top-level tokens the page consists of
        """
        return self.tokens
        
    def getTokensForPos(self, pos):
        return _findTokensForPos(self.tokens, pos)
        
    def buildAst(self, formatting, text, formatDetails=None,
            threadholder=DUMBTHREADHOLDER):
        self.tokens = formatting.tokenizePage(text, formatDetails,
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

    def getTextualTokens(self):
        """
        Returns a sequence of tokens containing real text only which are then
        processed and cut into words for word counting or spell checking.
        Returned token types can only be FormatTypes.SuppressHighlight for
        plain text and FormatTypes.Default for escaped text.
        """
        result = []
        for t in self.tokens:
            if t.ttype in (WikiFormatting.FormatTypes.WikiWord, 
                    WikiFormatting.FormatTypes.WikiWord2):
                # Ignore these
                continue

            t = t.shallowCopy()
            
            if t.ttype in (WikiFormatting.FormatTypes.EscapedChar, 
                    WikiFormatting.FormatTypes.Bold,
                    WikiFormatting.FormatTypes.Italic,
                    WikiFormatting.FormatTypes.Heading4,
                    WikiFormatting.FormatTypes.Heading3,
                    WikiFormatting.FormatTypes.Heading2,
                    WikiFormatting.FormatTypes.Heading1):
                # Convert to default
                t.ttype = WikiFormatting.FormatTypes.Default
                t.grpdict = None
                t.node = None


            if t.ttype == WikiFormatting.FormatTypes.Default or \
                    t.ttype == WikiFormatting.FormatTypes.SuppressHighlight:
                # check for coalescing possibility
                if len(result) > 0 and result[-1].ttype == t.ttype and \
                        result[-1].start + len(result[-1].text) == t.start:
                    result[-1].text += t.text
                else:
                    result.append(t)

        return result



class Todo(Ast):
    __slots__ = ("indent", "name", "delimiter", "valuetokens")

    def __init__(self):
        Ast.__init__(self)
        
    def getTokensForPos(self, pos):
        return _findTokensForPos(self.valuetokens, pos)
        
    def getText(self):
        return self.indent + self.name + self.delimiter + \
                _getRealTextForTokens(self.valuetokens)

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
                formatDetails, threadholder=threadholder)

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

    def getText(self):
        return self.begin + self.end + _getRealTextForTokens(self.contenttokens)

    def getTokensForPos(self, pos):
        return _findTokensForPos(self.contenttokens, pos)

    def buildSubAst(self, formatting, token, formatDetails=None,
            threadholder=DUMBTHREADHOLDER):
        groupdict = token.grpdict
        self.begin = groupdict["tableBegin"]
        self.end = groupdict["tableEnd"]
        content = groupdict["tableContent"]
      
        tokensIn = formatting.tokenizeTableContent(content,
                formatDetails, threadholder=threadholder)
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
    __slots__ = ("nakedWord", "searchFragment", "anchorFragment", "titleTokens")

    def __init__(self):
        Ast.__init__(self)

    def getText(self):
        # Full text not available
        return None
        
    def getLength(self):
        # Length not available
        return -1

    def getTokensForPos(self, pos):
        return _findTokensForPos(self.titleTokens, pos)

    def buildSubAst(self, formatting, token, formatDetails=None,
            threadholder=DUMBTHREADHOLDER):
        groupdict = token.grpdict
        frag = groupdict.get("wikiwordnccSearchfrag")
        if frag is None:
            frag = groupdict.get("wikiwordSearchfrag")
        self.searchFragment = frag
        
        frag = groupdict.get("wikiwordnccAnchorfrag")
        if frag is None:
            frag = groupdict.get("wikiwordAnchorfrag")
        self.anchorFragment = frag

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
                formatDetails, threadholder=threadholder)
                
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
    __slots__ = ("url", "titleTokens", "modeAppendix")

    def __init__(self):
        Ast.__init__(self)

    def getText(self):
        # Full text not available
        return None
        
    def getLength(self):
        # Length not available
        return -1

    def getTokensForPos(self, pos):
        return _findTokensForPos(self.titleTokens, pos)

    def buildSubAst(self, formatting, token, formatDetails=None,
            threadholder=DUMBTHREADHOLDER):
        groupdict = token.grpdict
        
        self.titleTokens = None
        self.modeAppendix = ()
        
        url = groupdict.get("titledurlUrl")
        if url is None:
            self.url = token.text
            self.titleTokens = None
        else:
            self.url = url.strip()
            
            title = groupdict.get("titledurlTitle")
            if title is None:
                self.titleTokens = None
            else:
                relpos = token.start + 1 + len(url) + len(groupdict.get(
                        "titledurlDelim"))
        
        #         delimPos = title.rindex(formatting.TitleWikiWordDelimiter)
        #         title = title[:delimPos]
        
                self.titleTokens = formatting.tokenizeTitle(title,
                        formatDetails, threadholder=threadholder)
                        
                for t in self.titleTokens:
                    t.start += relpos
        
                _enrichTokens(formatting, self.titleTokens, formatDetails,
                        threadholder)
                        
        # Now process the mode appendix (part after '>') from the URL, if present
        
        # The mode appendix consists of mode entries delimited by semicolons
        #   Each entry consists of the first character which defines the mode
        #   and optionally additional characters which contain further details
        
        cut = self.url.split(u">", 1)
        
        if len(cut) > 1:
            self.url = cut[0]
            
            modeAppendix = []
            for entry in cut[1].split(";"):
                if entry == u"":
                    continue
                
                modeAppendix.append((entry[0], entry[1:]))
                
            self.modeAppendix = modeAppendix


    def containsModeInAppendix(self, mode):
        """
        Returns True iff character mode is a mode in the modeAppendix list
        """
        for m, a in self.modeAppendix:
            if m == mode:
                return True
                
        return False
        
    def getInfoForMode(self, mode, defaultEmpty=u"", defaultNonExist=None):
        """
        Return additional settings for mode (the part after the first mode
        letter). If the mode is part of the appendix but doesn't contain any
        further characters, defaultEmpty is returned. If the mode is not in
        the index, defaultNonExist is returned.
        """

        for m, a in self.modeAppendix:
            if m == mode:
                if a == u"":
                    return defaultEmpty
                else:
                    return a
                
        return defaultNonExist


    def _findType(self, typeToFind, result):
        if self.titleTokens is None:
            return

        for tok in self.titleTokens:
            if tok.ttype == typeToFind:
                result.append(tok)
            if tok.node is not None:
                tok.node._findType(typeToFind, result)



class Insertion(Ast):
    r"""
    Insertions can be either quoted or non-quoted.
    Non-quoted insertions look like:
    [:key:value;appendix;appendix]
    
    They are used mainly for keys supported by WikidPad internally
    
    Quoted insertions look like:
    [:key:"some data ..."]
    
    instead of the " there can be an arbitrary number (at least one) of
    quotation characters ", ', / or \. So " can be replaced by e.g
    "", ''', \ or //.

    These insertions are mainly used for keys supported by external plugins
    """
    
    __slots__ = ("key", "value", "appendices")

    def __init__(self):
        Ast.__init__(self)

    def buildSubAst(self, formatting, token, formatDetails=None,
            threadholder=DUMBTHREADHOLDER):
        groupdict = token.grpdict
        
        self.key = groupdict.get("insertionKey")
        
        content = groupdict.get("insertionContent")
        
        mat = WikiFormatting.InsertionValueRE.match(content)
        self.value = mat.group("insertionQuotedValue")
        if self.value is None:
            self.value = mat.group("insertionValue")
            
        nextStart = mat.end(0)
        
        self.appendices = []

        while True:
            mat = WikiFormatting.InsertionAppendixRE.match(content, nextStart)
            if mat is None:
                break
    
            apx = mat.group("insertionQuotedAppendix")
            if apx is None:
                apx = mat.group("insertionAppendix")
                
            self.appendices.append(apx)

            nextStart = mat.end(0)


#         self.quotedValue = groupdict.get("insertionQuotedValue")
# 
#         iv = groupdict.get("insertionValue")
#         if iv is not None:
#             values = iv.split(u";")
# 
#             self.value = values[0]
#             self.appendices = [v.lstrip() for v in values[1:]]
#         else:
#             self.value = None
#             self.appendices = ()



class EscapeCharacter(Ast):
    __slots__ = ("unescaped")

    def __init__(self):
        Ast.__init__(self)

    def buildSubAst(self, formatting, token, formatDetails=None,
            threadholder=DUMBTHREADHOLDER):
            self.unescaped = token.text[1]


