import sets
from Enum import Enumeration
from MiscEvent import KeyFunctionSink
from Utilities import DUMBTHREADHOLDER
# from Config import faces

import srePersistent as re

from StringOps import Tokenizer, matchWhole, Token


FormatTypes = Enumeration("FormatTypes", ["Default", "WikiWord",
        "AvailWikiWord", "Bold", "Italic", "Heading4", "Heading3", "Heading2",
        "Heading1", "Url", "Script", "Property", "ToDo", "WikiWord2",
        "HorizLine", "Bullet", "Numeric", "Suppress", "Footnote", "Table",
        "EscapedChar", "HtmlTag", "TableCellSplit", "TableRowSplit", "PreBlock",
        "SuppressHighlight"], 1)

EMPTY_RE = re.compile(ur"", re.DOTALL | re.UNICODE | re.MULTILINE)


def compileCombinedRegex(expressions, ignoreList=None):
    """
    expressions -- List of tuples (r, s) where r is single compiled RE,
            s is a number from FormatTypes
    ignoreList -- List of FormatTypes for which the related
            expression shouldn't be taken into the compiled expression
    returns: compiled combined RE to feed into StringOps.Tokenizer
    """ 
    result = []
    if ignoreList == None:
        ignoreList = []

    for i in range(len(expressions)):
        r, s = expressions[i]

        if s in ignoreList:
            continue

        if type(r) is type(EMPTY_RE):
            r = r.pattern
        else:
            r = unicode(r)
        result.append(u"(?P<style%i>%s)" % (i, r))

    return re.compile(u"|".join(result),
            re.DOTALL | re.UNICODE | re.MULTILINE)



# def _buildExpressionsUnindex(expressions, modifier):
#     """
#     Helper for getExpressionsFormatList().
#     Create from an expressions list (see compileCombinedRegex) a tuple
#     of format types so that result[i] is the "right" number from
#     FormatTypes when i is the index returned as second element of a tuple
#     in the tuples list returned by the Tokenizer.
# 
#     In fact it is mainly the second tuple item from each expressions
#     list element.
#     modifier -- Dict. If a format type in expressions matches a key
#             in modifier, it is replaced by its value in the result
#     """
#     
#     return [modifier.get(t, t) for re, t in expressions]
    

# TODO Remove ?
# Currently needed only to get ToDoREWithCapturing in WikiTreeCtrl.py and
# for some regexes in WikiTxtCtrl.py
def initialize(wikiSyntax):
    import WikiFormatting as ownmodule
    for item in dir(wikiSyntax):
        if item.startswith("_"):   # TODO check if necessary
            continue
        setattr(ownmodule, item, getattr(wikiSyntax, item))

    
def getStyles(styleFaces):
    return [(FormatTypes.Default, "face:%(mono)s,size:%(size)d" % styleFaces),
            (FormatTypes.WikiWord, "fore:#000000,underline,face:%(mono)s,size:%(size)d" % styleFaces),      
            (FormatTypes.AvailWikiWord, "fore:#0000BB,underline,face:%(mono)s,size:%(size)d" % styleFaces),      
            (FormatTypes.Bold, "bold,face:%(mono)s,size:%(size)d" % styleFaces),   
            (FormatTypes.Italic, "italic,face:%(mono)s,size:%(size)d" % styleFaces), 
            (FormatTypes.Heading4, "bold,face:%(mono)s,size:%(heading4)d" % styleFaces),       
            (FormatTypes.Heading3, "bold,face:%(mono)s,size:%(heading3)d" % styleFaces),       
            (FormatTypes.Heading2, "bold,face:%(mono)s,size:%(heading2)d" % styleFaces),       
            (FormatTypes.Heading1, "bold,face:%(mono)s,size:%(heading1)d" % styleFaces), 
            (FormatTypes.Url, "fore:#0000BB,underline,face:%(mono)s,size:%(size)d" % styleFaces), 
            (FormatTypes.Script, "fore:#555555,face:%(mono)s,size:%(size)d" % styleFaces),
            (FormatTypes.Property, "bold,fore:#555555,face:%(mono)s,size:%(size)d" % styleFaces),
            (FormatTypes.ToDo, "bold,face:%(mono)s,size:%(size)d" % styleFaces)]

# List of all styles mentioned in getStyles which can be used as scintilla registered style
VALID_SCINTILLA_STYLES = sets.ImmutableSet((
        FormatTypes.Default,
        FormatTypes.WikiWord,
        FormatTypes.AvailWikiWord,      
        FormatTypes.Bold,
        FormatTypes.Italic,
        FormatTypes.Heading4,
        FormatTypes.Heading3,
        FormatTypes.Heading2,
        FormatTypes.Heading1,
        FormatTypes.Url,
        FormatTypes.Script,
        FormatTypes.Property,
        FormatTypes.ToDo))



# --------------------------------

class WikiPageFormatDetails(object):
    """
    Store some details of the formatting of a specific page
    """
    __slots__ = ("__weakref__", "withCamelCase", "noFormat")
    
    def __init__(self, withCamelCase=True, noFormat=False):
        self.withCamelCase = withCamelCase   # Interpret CamelCase as wiki word
        self.noFormat = noFormat   # No formatting at all, overrides other settings
    




# --------------------------------


class WikiFormatting:
    """
    Provides access to the regular expressions needed especially
    for the Tokenizer in StringOps.py, but also for other purposes.
    It also contains a few test and conversion functions for wiki words

    Active component which reacts on MiscEvents to change the
    regexes and other data according to loaded wiki and
    chosen options.
    """
    def __init__(self, pWiki, wikiSyntax):
        self.pWiki = pWiki
        self.footnotesAsWws = False
        
        # Register for pWiki events
        self.pWiki.getMiscEvent().addListener(KeyFunctionSink((
                ("options changed", self.rebuildFormatting),
                ("opened wiki", self.rebuildFormatting)
        )))

        for item in dir(wikiSyntax):
            if item.startswith("_"):   # TODO check if necessary
                continue
            setattr(self, item, getattr(wikiSyntax, item))


        self.formatExpressions = None
        self.formatCellExpressions = None            
                
        self.combinedPageRE = None
        self.combinedCellRE = None
        
        self.wikiWordStart = None  # String describing the beginning of a wiki
                # word or property, normally u"["
                
        self.wikiWordEnd = None  # Same for end of word, normally u"]"

        # Same after applying re.escape()
        self.wikiWordStartEsc = None
        self.wikiWordEndEsc = None

        # self.rebuildFormatting(None)


    def rebuildFormatting(self, miscevt):
        """
        Called after a new wiki is loaded or options were changed.
        It rebuilds regexes and sets other variables according to
        the new settings
        """
        # In each list most specific single expressions first
        
        # These are the full lists with all possible expressions
        # they might be reduced afterwards

        self.formatExpressions = [
                (self.PlainEscapedCharacterRE, FormatTypes.EscapedChar),
                (self.TableRE, FormatTypes.Table),
                (self.PreBlockRE, FormatTypes.PreBlock),
                (self.SuppressHighlightingRE, FormatTypes.SuppressHighlight),
                (self.ScriptRE, FormatTypes.Script),
                (self.TitledUrlRE, FormatTypes.Url),
                (self.UrlRE, FormatTypes.Url),
                (self.ToDoREWithContent, FormatTypes.ToDo),
                (self.PropertyRE, FormatTypes.Property),
                (self.FootnoteRE, FormatTypes.Footnote),
                (self.WikiWordEditorRE2, FormatTypes.WikiWord2),
                (self.WikiWordEditorRE, FormatTypes.WikiWord),
                (self.BoldRE, FormatTypes.Bold),
                (self.ItalicRE, FormatTypes.Italic),
                (self.HtmlTagRE, FormatTypes.HtmlTag),
                (self.Heading4RE, FormatTypes.Heading4),
                (self.Heading3RE, FormatTypes.Heading3),
                (self.Heading2RE, FormatTypes.Heading2),
                (self.Heading1RE, FormatTypes.Heading1),
                (self.BulletRE, FormatTypes.Bullet),
                (self.NumericBulletRE, FormatTypes.Numeric),
                (self.HorizLineRE, FormatTypes.HorizLine)
#                 (self.PlainCharactersRE, FormatTypes.Default)
                ]
                
                
        self.formatTodoExpressions = [
                (self.PlainEscapedCharacterRE, FormatTypes.EscapedChar),
                (self.TitledUrlRE, FormatTypes.Url),
                (self.UrlRE, FormatTypes.Url),
                (self.PropertyRE, FormatTypes.Property),
                (self.FootnoteRE, FormatTypes.Footnote),
                (self.WikiWordEditorRE2, FormatTypes.WikiWord2),
                (self.WikiWordEditorRE, FormatTypes.WikiWord),
                (self.BoldRE, FormatTypes.Bold),
                (self.ItalicRE, FormatTypes.Italic),
                (self.HtmlTagRE, FormatTypes.HtmlTag)
#                 (self.PlainCharactersRE, FormatTypes.Default)
                ]
                

        self.formatTableContentExpressions = [
                (self.PlainEscapedCharacterRE, FormatTypes.EscapedChar),
                (self.TitleWikiWordDelimiterPAT, FormatTypes.TableCellSplit),
                (self.TableRowDelimiterPAT, FormatTypes.TableRowSplit),
                (self.TitledUrlRE, FormatTypes.Url),
                (self.UrlRE, FormatTypes.Url),
#                 (self.ToDoREWithContent, FormatTypes.ToDo),  # TODO Doesn't work
                (self.FootnoteRE, FormatTypes.Footnote),
                (self.WikiWordEditorRE2, FormatTypes.WikiWord2),
                (self.WikiWordEditorRE, FormatTypes.WikiWord),
                (self.BoldRE, FormatTypes.Bold),
                (self.ItalicRE, FormatTypes.Italic),
                (self.HtmlTagRE, FormatTypes.HtmlTag)
#                 (self.PlainCharactersRE, FormatTypes.Default)
                ]


        self.formatWwTitleExpressions = [
                (self.PlainEscapedCharacterRE, FormatTypes.EscapedChar),
                (self.BoldRE, FormatTypes.Bold),
                (self.ItalicRE, FormatTypes.Italic),
                (self.HtmlTagRE, FormatTypes.HtmlTag)
#                 (self.PlainCharactersRE, FormatTypes.Default)
                ]


        ignoreList = []  # List of FormatTypes not to compile into the comb. regex

        if self.pWiki.getConfig().getboolean(
                    "main", "footnotes_as_wikiwords", False):
            ignoreList.append(FormatTypes.Footnote)
            self.footnotesAsWws = self.pWiki.getConfig().getboolean(
                    "main", "footnotes_as_wikiwords", False)


        self.combinedPageRE = compileCombinedRegex(self.formatExpressions,
                ignoreList)
        self.combinedTodoRE = compileCombinedRegex(self.formatTodoExpressions,
                ignoreList)
        self.combinedTableContentRE = compileCombinedRegex(
                self.formatTableContentExpressions, ignoreList)
        self.combinedWwTitleRE = compileCombinedRegex(
                self.formatWwTitleExpressions, ignoreList)


        self.wikiWordStart = u"["
        self.wikiWordEnd = u"]"
        
        self.wikiWordStartEsc = ur"\["
        self.wikiWordEndEsc = ur"\]"
        
#         if self.pWiki.wikiConfigFilename:
#             self.footnotesAsWws = self.pWiki.getConfig().getboolean(
#                     "main", "footnotes_as_wikiwords", False)

        # Needed in PageAst.Table.buildSubAst (placed here because of threading
        #   problem with re.compile            
        self.tableCutRe = re.compile(ur"\n|" + self.TitleWikiWordDelimiterPAT +
                ur"|" + self.PlainCharacterPAT + ur"+?(?=\n|" +
                self.TitleWikiWordDelimiterPAT + ur"|(?!.))", 
                re.DOTALL | re.UNICODE | re.MULTILINE)  # TODO Explain (if it works)

    
    def isWikiWord(self, word):
        """
        Test if word is syntactically a wiki word
        """
        if matchWhole(self.WikiWordEditorRE, word):
            return True
        if self.WikiWordRE2.match(word):
            if self.footnotesAsWws:
                return True
            else:
                return not self.FootnoteRE.match(word)

        return False

    def isCcWikiWord(self, word):
        """
        Test if word is syntactically a naked camel-case wiki word
        """
        if matchWhole(self.WikiWordEditorRE, word):
            return True
            
        return False       


    def isNakedWikiWord(self, word):
        """
        Test if word is syntactically a naked wiki word
        """
        if self.isCcWikiWord(word):
            return True
            
        parword = self.wikiWordStart + word + self.wikiWordEnd
        if self.WikiWordRE2.match(parword):
            if self.footnotesAsWws:
                return True
            else:
                return not self.FootnoteRE.match(parword)
        
        return False
        
    def unescapeNormalText(self, text):
        """
        Return the unescaped version of text (without "\\")
        """
        return  self.PlainEscapedCharacterRE.sub(ur"\1", text)



    # TODO  What to do if wiki word start and end are configurable?
    def normalizeWikiWordImport(self, word):
        """
        Special version for WikidPadCompact to support importing of
        .wiki files into the database
        """
        if matchWhole(self.WikiWordEditorRE, word):
            return word
            
        if matchWhole(self.WikiWordEditorRE2, word):
            if matchWhole(self.WikiWordEditorRE,
                    word[len(self.wikiWordStart):-len(self.wikiWordEnd)]):
                # If word is '[WikiWord]', return 'WikiWord' instead
                return word[len(self.wikiWordStart):-len(self.wikiWordEnd)]
            else:
                return word
        
        # No valid wiki word -> try to add brackets
        parword = self.wikiWordStart + word + self.wikiWordEnd
        if self.WikiWordRE2.match(parword):
            return parword

        return None


    def normalizeWikiWord(self, word):
        """
        Try to normalize text to a valid wiki word and return it or None
        if it can't be normalized.
        """
        mat = matchWhole(self.WikiWordEditorRE, word)
        if mat:
            return mat.group("wikiword")
            
        mat = matchWhole(self.WikiWordEditorRE2, word)
        if mat:
            if not self.footnotesAsWws and matchWhole(self.FootnoteRE, word):
                return None

            if matchWhole(self.WikiWordEditorRE, mat.group("wikiwordncc")):
                # If word is '[WikiWord]', return 'WikiWord' instead
                return mat.group("wikiwordncc")
            else:
                return self.wikiWordStart + mat.group("wikiwordncc") + \
                        self.wikiWordEnd
        
        # No valid wiki word -> try to add brackets
        parword = self.wikiWordStart + word + self.wikiWordEnd
        mat = matchWhole(self.WikiWordEditorRE2, parword)
        if mat:
            if not self.footnotesAsWws and self.FootnoteRE.match(parword):
                return None

            return self.wikiWordStart + mat.group("wikiwordncc") + self.wikiWordEnd

        return None


#     def splitWikiWord(self, word):
#         """
#         Splits a wiki word with (optional) title and/or search fragment
#         into its parts.
#         It is only recognized if it is valid in the editor, this means
#         a non camelcase word must be in brackets.
#         Returns tuple (<naked word>, <title>, <search fragment>) where
#         "naked" means it doesn't have brackets, "title" and/or "search fragment"
#         may be None if they are not present. The search fragment is unescaped
#         
#         If word isn't a wiki word, (None, None, None) is returned.
#         """
#         mat = matchWhole(self.WikiWordEditorRE, word)
#         if mat:
#             # Camelcase word without brackets (has never a title)
#             gd = mat.groupdict()
#             nword = gd.get("wikiword")
#             sfrag = gd.get("wikiwordSearchfrag")
#             if sfrag is not None:
#                 sfrag = self.SearchFragmentUnescapeRE.sub(ur"\1", sfrag)
#             
#             return (nword, None, sfrag)
#             
#         mat = matchWhole(self.WikiWordEditorRE2, word)
#         if mat:
#             # Sort out footnotes if appropriate
#             if not self.footnotesAsWws and matchWhole(self.FootnoteRE, word):
#                 return (None, None, None)
#                 
#             gd = mat.groupdict()
#             nword = gd.get("wikiwordncc")
#             title = gd.get("wikiwordnccTitle")
#             sfrag = gd.get("wikiwordnccSearchfrag")
#             if sfrag is not None:
#                 sfrag = self.SearchFragmentUnescapeRE.sub(ur"\1", sfrag)
#             
#             return (nword, title, sfrag)


    def wikiWordToLabel(self, word):
        """
        Strip '[' and ']' if present and return naked word
        """
        if word.startswith(self.wikiWordStart) and \
                word.endswith(self.wikiWordEnd):
            return word[len(self.wikiWordStart):-len(self.wikiWordEnd)]
        return word


    def getExpressionsFormatList(self, expressions, formatDetails=None):
        """
        Create from an expressions list (see compileCombinedRegex) a tuple
        of format types so that result[i] is the "right" number from
        FormatTypes when i is the index returned as second element of a tuple
        in the tuples list returned by the Tokenizer.
    
        In fact it is mainly the second tuple item from each expressions
        list element with some modifications according to the parameters
        withCamelCase -- Recognize camel-case words as wiki words instead
                of normal text
        """
        modifier = {FormatTypes.WikiWord2: FormatTypes.WikiWord}
        if formatDetails is None:
            page = self.pWiki.getCurrentDocPage()
            if page is None:
                formatDetails = WikiPageFormatDetails() # Default
            else:
                formatDetails = page.getFormatDetails()
        
        if not formatDetails.withCamelCase:
            modifier[FormatTypes.WikiWord] = FormatTypes.Default
        
#         if self.footnotesAsWws:  # Footnotes (e.g. [42]) as wiki words?
#             modifier[FormatTypes.Footnote] = FormatTypes.WikiWord
#         else:
#             modifier[FormatTypes.Footnote] = FormatTypes.Default
            
        return [modifier.get(t, t) for re, t in expressions]



    def tokenizePage(self, text, formatDetails=None,
            threadholder=DUMBTHREADHOLDER):
        """
        Function used by PageAst module
        """
        if formatDetails is None:
            page = self.pWiki.getCurrentDocPage()
            if page is None:
                formatDetails = WikiPageFormatDetails() # Default
            else:
                formatDetails = page.getFormatDetails()

        if formatDetails.noFormat:
            # No formatting at all (used e.g. by some functional pages)
            return [Token(FormatTypes.Default, 0, {}, text)]
            
        # TODO Cache if necessary
        formatMap = self.getExpressionsFormatList(
                self.formatExpressions, formatDetails=formatDetails)
                
        tokenizer = Tokenizer(self.combinedPageRE, -1)
        
        return tokenizer.tokenize(text, formatMap, FormatTypes.Default,
                threadholder=threadholder)


    def tokenizeTodo(self, text, formatDetails=None,
            threadholder=DUMBTHREADHOLDER):
        """
        Function used by PageAst module
        """
        # TODO Cache if necessary
        formatMap = self.getExpressionsFormatList(
                self.formatTodoExpressions, formatDetails=formatDetails)
                
        tokenizer = Tokenizer(self.combinedTodoRE, -1)
        
        return tokenizer.tokenize(text, formatMap, FormatTypes.Default,
                threadholder=threadholder)


    def tokenizeTableContent(self, text, formatDetails=None,
            threadholder=DUMBTHREADHOLDER):
        """
        Function used by PageAst module
        """
        # TODO Cache if necessary
        formatMap = self.getExpressionsFormatList(
                self.formatTableContentExpressions, formatDetails=formatDetails)
                
        tokenizer = Tokenizer(self.combinedTableContentRE, -1)
        
        return tokenizer.tokenize(text, formatMap, FormatTypes.Default,
                threadholder=threadholder)


    def tokenizeTitle(self, text, formatDetails=None,
            threadholder=DUMBTHREADHOLDER):
        """
        Function used by PageAst module
        """
        # TODO Cache if necessary
        formatMap = self.getExpressionsFormatList(
                self.formatWwTitleExpressions, formatDetails=formatDetails)
                
        tokenizer = Tokenizer(self.combinedWwTitleRE, -1)

        return tokenizer.tokenize(text, formatMap, FormatTypes.Default,
                threadholder=threadholder)

