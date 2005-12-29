import os, traceback, codecs, array
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
        
    def buildAst(self, formatting, text, threadholder=DUMBTHREADHOLDER):
        self.tokens = formatting.tokenizePage(text, threadholder)
        
        for tok in self.tokens:
            if not threadholder.isCurrent():
                self.tokens = None
                return

            if tok.ttype == WikiFormatting.FormatTypes.ToDo:
                node = Todo()
                node.buildSubAst(formatting, tok, threadholder=threadholder)
                tok.node = node
            elif tok.ttype == WikiFormatting.FormatTypes.Table:
                node = Table()
                node.buildSubAst(formatting, tok, threadholder=threadholder)
                tok.node = node
                

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
        
    def buildSubAst(self, formatting, token, threadholder=DUMBTHREADHOLDER):
        # First three parts are simple
        groupdict = token.grpdict
        self.indent = groupdict["todoIndent"]
        self.name = groupdict["todoName"]
        self.delimiter = groupdict["todoDelimiter"]
        
        relpos = token.start + len(self.indent) + len(self.name) + \
                len(self.delimiter)
        
        value = groupdict["todoValue"]
        self.valuetokens = formatting.tokenizeCell(value, threadholder=threadholder)
        
        # The valuetokens contain start position relative to beginning of
        # value. This must be corrected to position rel. to whole page
        
        for t in self.valuetokens:
            t.start += relpos


    def _findType(self, typeToFind, result):
        for tok in self.valuetokens:
            if tok.ttype == typeToFind:
                result.append(tok)
            if tok.node is not None:
                tok.node._findType(typeToFind, result)
        
            
class Table(Ast):
    __slots__ = ("begin", "end", "contenttokens")

    def __init__(self):
        Ast.__init__(self)

    def buildSubAst(self, formatting, token, threadholder=DUMBTHREADHOLDER):
        groupdict = token.grpdict
        self.begin = groupdict["tableBegin"]
        self.end = groupdict["tableEnd"]
        content = groupdict["tableContent"]
        
        lines = splitkeep(content, u"\n")
        cells = []
        for l in lines:
            cells += splitkeep(l, u"|")
            
        contenttokens = []
        relpos = token.start + len(self.begin)
        for c in cells:
            if not threadholder.isCurrent():
                return

            tokensIn = formatting.tokenizeCell(c, threadholder=threadholder)
            tokensOut = []
            # Filter out empty tokens
            for t in tokensIn:
                if t.text == u"":
                    continue
                t.start += relpos
                tokensOut.append(t)
            
            relpos += len(c)
            contenttokens += tokensOut

        self.contenttokens = contenttokens

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
            if t.ttype == WikiFormatting.FormatTypes.Default:
                if t.text == u"\n":
                    if len(cell) > 0:
                        row.append(cell)
                        cell = []
                    if len(row) > 0:
                        grid.append(row)
                        row = []
                    continue
                elif t.text == u"|":
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


#     def outTable(self, content):
#         """
#         Write out content of a table as HTML code
#         """
#         # TODO XML
#         self.outAppend(u'<table border="2">\n')  # , eatPreBreak=True
#         for line in content.split(u"\n"):
#             if line.strip() == "":
#                 continue
#             cells = line.split(u"|")  # TODO strip whitespaces?
#             resline = [u"<tr>"]
#             resline += [u"<td>%s</td>" % escapeHtml(cell) for cell in cells]
#             resline.append(u"</tr>\n")
#             self.outAppend(u"".join(resline))
#         
#         self.outAppend(u'</table>\n', eatPostBreak=True)
        
#     def buildTableStyling(self, matchdict, sync=False):
#         tokenizer = Tokenizer(
#                 self.pWiki.getFormatting().formatInTCellExpressions, -1)
#                 
#         # Beginning of table is normal text
#         result = [chr(WikiFormatting.FormatTypes.Default) * 
#                 self.bytelenSct(matchdict["tableBegin"])]
#             
#         for line in splitkeep(matchdict["tableContent"], u"\n"):
#             if line.strip() == "":
#                 result.append(chr(WikiFormatting.FormatTypes.Default) * 
#                         self.bytelenSct(line))
#                 continue
#             cells = splitkeep(line, u"|")
#             for cell in cells:
#                 tokens = self.tokenizer.tokenize2(cell, self.tableFormatMap,
#                         WikiFormatting.FormatTypes.Default, sync=sync)
# 
#                 result.append(self.processTokens(cell, None, tokens, sync=False))                
#         
#         result = [chr(WikiFormatting.FormatTypes.Default) * 
#                 self.bytelenSct(matchdict["tableEnd"])]
