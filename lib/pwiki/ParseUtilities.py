

class WikiPageFormatDetails(object):
    """
    Store some details of the formatting of a specific page
    """
    __slots__ = ("__weakref__", "withCamelCase", "footnotesAsWws",
            "wikiDocument", "autoLinkMode", "noFormat", "paragraphMode")
    
    def __init__(self, withCamelCase=True, footnotesAsWws=False,
            wikiDocument=None, autoLinkMode=u"off", noFormat=False,
            paragraphMode=False):
        self.wikiDocument = wikiDocument   # WikiDocument object (needed for autoLink)

        self.withCamelCase = withCamelCase   # Interpret CamelCase as wiki word?
        self.footnotesAsWws = footnotesAsWws # Interpret footnotes
                # (e.g. "[42]") as wikiwords?
        self.autoLinkMode = autoLinkMode   # Mode to automatically create links from plain text
        self.noFormat = noFormat   # No formatting at all, overrides other settings
        
        # If True, ignore single newlines, only empty line starts new paragraph
        # Not relevant for page AST creation but for exporting (e.g. to HTML)
        self.paragraphMode = paragraphMode 


    def isEquivTo(self, details):
        """
        Compares with other details object if both are "equivalent"
        """
        if self.noFormat or details.noFormat:
            # Remaining doesn't matter in this case
            return self.noFormat == details.noFormat

        return self.withCamelCase == details.withCamelCase and \
                self.footnotesAsWws == details.footnotesAsWws and \
                self.autoLinkMode == details.autoLinkMode and \
                self.paragraphMode == details.paragraphMode



def getFootnoteAnchorDict(pageAst):
    """
    Returns a new or cached dictionary of footnote anchors
    {footnodeId: anchorNode} from a page ast.
    """
    if pageAst is None:
        return
    if not hasattr(pageAst, "footnoteAnchorDict"):
        result = {}
        fnNodes = pageAst.iterSelectedDeepByName("footnote",
                frozenset(("indentedText", "orderedList", "unorderedList")))

        for node in fnNodes:
            result[node.footnoteId] = node

        pageAst.footnoteAnchorDict = result

    return pageAst.footnoteAnchorDict



# def coalesceTokens(tokens):
#     """
#     Coalesce neighboured "Default" tokens.
#     """
#     result = []
#     lenT = len(tokens)
#     if lenT < 2:
#         return tokens
#         
#     prevToken = tokens[0]
#     for token in itertools.islice(tokens, 1, None):
#         if prevToken.ttype == FormatTypes.Default and \
#                token.ttype == FormatTypes.Default:
#             prevToken.text = prevToken.text + token.text
#             continue
# 
#         result.append(prevToken)
#         prevToken = token
#     
#     result.append(prevToken)
#     
#     return result








# # ---------- Breaking text into tokens (the old way) ----------
# 
# class Token(object):
#     """
#     The class has the following members:
# 
#     ttype - Token type number (one of the "FormatTypes" enumeration numbers
#         in "WikiFormatting.py")
#     start - Character position of the token start in page
#     grpdict - Dictionary of the regular expression groups
#     text - Actual text content of token
#     node - object derived from "Ast" class in "PageAst.py" if further
#         data must be stored or None.
#     """
#     __slots__ = ("__weakref__", "ttype", "start", "grpdict", "text", "node")
# 
#     def __init__(self, ttype, start, grpdict, text, node=None):
#         self.ttype = ttype
#         self.start = start
#         self.grpdict = grpdict
#         self.text = text
#         self.node = node
# 
#     def __repr__(self):
#         return u"Token(%s, %s, %s, <dict>, %s)" % (repr(self.ttype),
#                 repr(self.start), repr(self.text), repr(self.node))
# 
# 
#     def getRealLength(self):
#         """
#         If node object exist, it is asked for length. If it returns -1 or
#         doesn't exist at all, length of self.text is returned.
#         """
#         result = -1
# 
#         if self.node is not None:
#             result = self.node.getLength()
# 
#         if result == -1:
#             result = len(self.text)
# 
#         return result
# 
# 
#     def getRealText(self):
#         """
#         If node object exist, it is asked for text. If it returns None or
#         doesn't exist at all, self.text is returned.
#         """
#         result = None
#         if self.node is not None:
#             result = self.node.getText()
# 
#         if result == None:
#             result = self.text
# 
# 
#     def shallowCopy(self):
#         return Token(self.ttype, self.start, self.grpdict, self.text, self.node)
# 
# 
# 
# class TokenIterator:
#     """
#     Tokenizer with iterator mechanism
#     """
#     def __init__(self, tokenre, formatMap, defaultType, text, charPos=0,
#             tokenStartOffset=0):
#         """
#         charPos -- start position in text where to start
#         tokenStartOffset -- offset to add to token.start value before returning token
#         """
#         self.tokenre = tokenre
#         self.formatMap = formatMap
#         self.defaultType = defaultType
#         self.text = text
#         self.charPos = charPos
#         self.tokenStartOffset = tokenStartOffset
#         self.nextMatch = None  # Stores an already found match to speed up things
# 
#     def __iter__(self):
#         return self
# 
#     def setCharPos(charPos):
#         self.charPos = charPos
# 
#     def getCharPos(self):
#         return self.charPos
# 
# 
#     def next(self):
#         textlen = len(self.text)
# 
#         if self.charPos >= textlen:
#             raise StopIteration()
# 
#         # Try to get cached nextMatch
#         if self.nextMatch:
#             mat = self.nextMatch
#             self.nextMatch = None
#         else:
#             mat = self.tokenre.search(self.text, self.charPos)
# 
#         if mat is None:
#             cp = self.charPos
#             self.charPos = textlen
#             return Token(self.defaultType, cp + self.tokenStartOffset, None,
#                     self.text[cp:textlen])
# 
#         start, end = mat.span()
#         if self.charPos < start:
#             self.nextMatch = mat
#             cp = self.charPos
#             self.charPos = start
#             return Token(self.defaultType, cp + self.tokenStartOffset, None,
#                     self.text[cp:start])
# 
# 
#         groupdict = mat.groupdict()
#         for m in groupdict.keys():
#             if not groupdict[m] is None and m.startswith(u"style"):
#                 # m is of the form:   style<index>
#                 index = int(m[5:])
#                 cp = self.charPos
#                 self.charPos = end
#                 return Token(self.formatMap[index], cp + self.tokenStartOffset,
#                         groupdict, self.text[start:end])
# 
# 
# class Tokenizer:
#     def __init__(self, tokenre, defaultType):
#         self.tokenre = tokenre
#         self.defaultType = defaultType
# 
#     def tokenize(self, text, formatMap, defaultType,
#             threadholder=DUMBTHREADHOLDER, tokenStartOffset=0):
#         result = []
#         if not threadholder.isRunning():
#             return result
# 
#         it = TokenIterator(self.tokenre, formatMap, defaultType, text,
#                 tokenStartOffset=tokenStartOffset)
# 
#         for t in it:
#             result.append(t)
#             if not threadholder.isRunning():
#                 break
# 
#         return result

