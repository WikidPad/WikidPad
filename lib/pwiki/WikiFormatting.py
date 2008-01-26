import sets, itertools
from Enum import Enumeration
from MiscEvent import KeyFunctionSink
from Utilities import DUMBTHREADHOLDER
# from Config import faces

import srePersistent as re

from StringOps import Tokenizer, matchWhole, Token, htmlColorToRgbTuple, \
        unescapeWithRe, TokenIterator


FormatTypes = Enumeration("FormatTypes", ["Default", "WikiWord",
        "AvailWikiWord", "Bold", "Italic", "Heading4", "Heading3", "Heading2",
        "Heading1", "Url", "Script", "Property", "ToDo", "WikiWord2",
        "HorizLine", "Bullet", "Numeric", "Suppress", "Footnote", "Table",
        "EscapedChar", "HtmlTag", "HtmlEntity", "TableCellSplit",
        "TableRowSplit", "PreBlock", "SuppressHighlight", "Insertion",
        "Anchor", "Newline", "Indentation", "PropertyInTodo",

        "Heading5", "Heading6", "Heading7", "Heading8", "Heading9",
        "Heading10", "Heading11", "Heading12", "Heading13", "Heading14",
        "Heading15", "HeadingCatchAll"
        ], 0)

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
    

# TODO Remove ?
# Currently needed only to get ToDoREWithCapturing in WikiTreeCtrl.py and
# for some regexes in WikiTxtCtrl.py
def initialize(wikiSyntax):
    import WikiFormatting as ownmodule
    for item in dir(wikiSyntax):
        if item.startswith("_"):   # TODO check if necessary
            continue
        setattr(ownmodule, item, getattr(wikiSyntax, item))


# Headings 5 to 15 are mapped to heading 4 in scintilla editor

def getStyles(styleFaces, config):
    # Read colors from config
    colPlaintext = config.get("main", "editor_plaintext_color", "#000000")
    colLink = config.get("main", "editor_link_color", "#0000BB")
    colAttribute = config.get("main", "editor_attribute_color", "#555555")

    # Check validity
    if htmlColorToRgbTuple(colPlaintext) is None:
        colPlaintext = "#000000"
    if htmlColorToRgbTuple(colLink) is None:
        colLink = "#0000BB"
    if htmlColorToRgbTuple(colAttribute) is None:
        colAttribute = "#555555"

    # Add colors to dictionary:
    styleFaces = styleFaces.copy()
    styleFaces.update({"colPlaintext": colPlaintext,
            "colLink": colLink, "colAttribute": colAttribute})

    return [(FormatTypes.Default,
                    "fore:%(colPlaintext)s,face:%(mono)s,size:%(size)d" % styleFaces),
            (FormatTypes.WikiWord,
                    "fore:%(colPlaintext)s,underline,face:%(mono)s,size:%(size)d" % styleFaces),      
            (FormatTypes.AvailWikiWord,
                    "fore:%(colLink)s,underline,face:%(mono)s,size:%(size)d" % styleFaces),      
            (FormatTypes.Bold, "fore:%(colPlaintext)s,bold,face:%(mono)s,size:%(size)d" % styleFaces),   
            (FormatTypes.Italic, "fore:%(colPlaintext)s,italic,face:%(mono)s,size:%(size)d" % styleFaces), 
            (FormatTypes.Heading4, "fore:%(colPlaintext)s,bold,face:%(mono)s,size:%(heading4)d" % styleFaces),       
            (FormatTypes.Heading3, "fore:%(colPlaintext)s,bold,face:%(mono)s,size:%(heading3)d" % styleFaces),       
            (FormatTypes.Heading2, "fore:%(colPlaintext)s,bold,face:%(mono)s,size:%(heading2)d" % styleFaces),       
            (FormatTypes.Heading1, "fore:%(colPlaintext)s,bold,face:%(mono)s,size:%(heading1)d" % styleFaces), 
            (FormatTypes.Url,
                    "fore:%(colLink)s,underline,face:%(mono)s,size:%(size)d" % styleFaces), 
            (FormatTypes.Script,
                    "fore:%(colAttribute)s,face:%(mono)s,size:%(size)d" % styleFaces),
            (FormatTypes.Property,
                    "bold,fore:%(colAttribute)s,face:%(mono)s,size:%(size)d" % styleFaces),
            (FormatTypes.ToDo, "fore:%(colPlaintext)s,bold,face:%(mono)s,size:%(size)d" % styleFaces)]

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


# Headings 5 to 15 are mapped to heading 4 in scintilla editor
ADDITIONAL_HEADING_STYLES = sets.ImmutableSet((
        FormatTypes.Heading15,
        FormatTypes.Heading14,
        FormatTypes.Heading13,
        FormatTypes.Heading12,
        FormatTypes.Heading11,
        FormatTypes.Heading10,
        FormatTypes.Heading9,
        FormatTypes.Heading8,
        FormatTypes.Heading7,
        FormatTypes.Heading6,
        FormatTypes.Heading5))



HEADING_LEVEL_MAP = {
        FormatTypes.Heading15: 15,
        FormatTypes.Heading14: 14,
        FormatTypes.Heading13: 13,
        FormatTypes.Heading12: 12,
        FormatTypes.Heading11: 11,
        FormatTypes.Heading10: 10,
        FormatTypes.Heading9:  9,
        FormatTypes.Heading8:  8,
        FormatTypes.Heading7:  7,
        FormatTypes.Heading6:  6,
        FormatTypes.Heading5:  5,
        FormatTypes.Heading4:  4,
        FormatTypes.Heading3:  3,
        FormatTypes.Heading2:  2,
        FormatTypes.Heading1:  1
        }


def getHeadingLevel(formatType):
    """
    Takes a formatType from Enumeration FormatTypes and returns
    0 if it isn't one of the headings or the heading level (1 to 4)
    if it is one of them.
    """
    return HEADING_LEVEL_MAP.get(formatType, 0)



def coalesceTokens(tokens):
    """
    Coalesce neighboured "Default" tokens.
    """
    result = []
    lenT = len(tokens)
    if lenT < 2:
        return tokens
        
    prevToken = tokens[0]
    for token in itertools.islice(tokens, 1, None):
        if prevToken.ttype == FormatTypes.Default and \
               token.ttype == FormatTypes.Default:
            prevToken.text = prevToken.text + token.text
            continue

        result.append(prevToken)
        prevToken = token
    
    result.append(prevToken)
    
    return result



# --------------------------------

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


# --------------------------------


class WikiFormatting:
    """
    Provides access to the regular expressions needed especially
    for the Tokenizer in StringOps.py, but also for other purposes.
    It also contains a few test and conversion functions for wiki words
    """
    def __init__(self, wikiDocument, wikiSyntax):
        self.wikiDocument = wikiDocument
        self.footnotesAsWws = False
        
        # Register for pWiki events
#         self.pWiki.getMiscEvent().addListener(KeyFunctionSink((
#                 ("options changed", self.rebuildFormatting),
#                 ("opened wiki", self.rebuildFormatting)
#         )))

        for item in dir(wikiSyntax):
            if item.startswith("_"):   # TODO check if necessary
                continue
            setattr(self, item, getattr(wikiSyntax, item))


        self.formatExpressions = None
        self.formatCellExpressions = None            
                
        self.combinedPageRE = None
        self.combinedCellRE = None
        
#         self.wikiWordStart = None  # String describing the beginning of a wiki
#                 # word or property, normally u"["
#                 
#         self.wikiWordEnd = None  # Same for end of word, normally u"]"
# 
#         # Same after applying re.escape()
#         self.wikiWordStartEsc = None
#         self.wikiWordEndEsc = None
        
        # Set of camelcase words which shouldn't be seen as wiki words
        self.ccWordBlacklist = sets.Set()  ## ("WikidPad", "NotWord")

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
                (self.HtmlEntityRE, FormatTypes.HtmlEntity),
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
                (self.HeadingCatchAllRE, FormatTypes.HeadingCatchAll),
#                 
#                 (self.Heading15RE, FormatTypes.Heading15),
#                 (self.Heading14RE, FormatTypes.Heading14),
#                 (self.Heading13RE, FormatTypes.Heading13),
#                 (self.Heading12RE, FormatTypes.Heading12),
#                 (self.Heading11RE, FormatTypes.Heading11),
#                 (self.Heading10RE, FormatTypes.Heading10),
#                 (self.Heading9RE, FormatTypes.Heading9),
#                 (self.Heading8RE, FormatTypes.Heading8),
#                 (self.Heading7RE, FormatTypes.Heading7),
#                 (self.Heading6RE, FormatTypes.Heading6),
#                 (self.Heading5RE, FormatTypes.Heading5),
#                 (self.Heading4RE, FormatTypes.Heading4),
#                 (self.Heading3RE, FormatTypes.Heading3),
#                 (self.Heading2RE, FormatTypes.Heading2),
#                 (self.Heading1RE, FormatTypes.Heading1),
                (self.AnchorRE, FormatTypes.Anchor),
                (self.BulletRE, FormatTypes.Bullet),
                (self.NumericBulletRE, FormatTypes.Numeric),
                (self.HorizLineRE, FormatTypes.HorizLine),
                (self.InsertionRE, FormatTypes.Insertion),
                (ur"\n", FormatTypes.Newline),
                (ur"^[ \t]+", FormatTypes.Indentation)
#                 (ur"[^\n]+", FormatTypes.Default)
#                 (self.PlainCharactersRE, FormatTypes.Default)
                ]
                
                
        self.formatTodoExpressions = [
                (self.PlainEscapedCharacterRE, FormatTypes.EscapedChar),
                (self.HtmlEntityRE, FormatTypes.HtmlEntity),
                (self.TitledUrlRE, FormatTypes.Url),
                (self.UrlRE, FormatTypes.Url),
                (self.PropertyInTodoRE, FormatTypes.PropertyInTodo),
                (self.FootnoteRE, FormatTypes.Footnote),
                (self.WikiWordEditorRE2, FormatTypes.WikiWord2),
                (self.WikiWordEditorRE, FormatTypes.WikiWord),
                (self.BoldRE, FormatTypes.Bold),
                (self.ItalicRE, FormatTypes.Italic),
                (self.HtmlTagRE, FormatTypes.HtmlTag)
                ]
                

        self.formatTableContentExpressions = [
                (self.PlainEscapedCharacterRE, FormatTypes.EscapedChar),
                (self.HtmlEntityRE, FormatTypes.HtmlEntity),
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
                ]


        self.formatTableContentTabDelimitExpressions = [
                (self.PlainEscapedCharacterRE, FormatTypes.EscapedChar),
                (self.HtmlEntityRE, FormatTypes.HtmlEntity),
                (ur"\t", FormatTypes.TableCellSplit),
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
                ]


        self.formatWwTitleExpressions = [
                (self.PlainEscapedCharacterRE, FormatTypes.EscapedChar),
                (self.HtmlEntityRE, FormatTypes.HtmlEntity),
                (self.BoldRE, FormatTypes.Bold),
                (self.ItalicRE, FormatTypes.Italic),
                (self.HtmlTagRE, FormatTypes.HtmlTag)
                ]


        self.formatHeadings= [
                (self.Heading15RE, FormatTypes.Heading15),
                (self.Heading14RE, FormatTypes.Heading14),
                (self.Heading13RE, FormatTypes.Heading13),
                (self.Heading12RE, FormatTypes.Heading12),
                (self.Heading11RE, FormatTypes.Heading11),
                (self.Heading10RE, FormatTypes.Heading10),
                (self.Heading9RE, FormatTypes.Heading9),
                (self.Heading8RE, FormatTypes.Heading8),
                (self.Heading7RE, FormatTypes.Heading7),
                (self.Heading6RE, FormatTypes.Heading6),
                (self.Heading5RE, FormatTypes.Heading5),
                (self.Heading4RE, FormatTypes.Heading4),
                (self.Heading3RE, FormatTypes.Heading3),
                (self.Heading2RE, FormatTypes.Heading2),
                (self.Heading1RE, FormatTypes.Heading1)
                ]


        ignoreList = []  # List of FormatTypes not to compile into the comb. regex

        self.footnotesAsWws = self.wikiDocument.getWikiConfig().getboolean(
                "main", "footnotes_as_wikiwords", False)

        if self.footnotesAsWws:
            ignoreList.append(FormatTypes.Footnote)


        self.combinedPageRE = compileCombinedRegex(self.formatExpressions,
                ignoreList)
        self.combinedTodoRE = compileCombinedRegex(self.formatTodoExpressions,
                ignoreList)
        self.combinedTableContentRE = compileCombinedRegex(
                self.formatTableContentExpressions, ignoreList)
        self.combinedTableContentTabDelimitRE = compileCombinedRegex(
                self.formatTableContentTabDelimitExpressions, ignoreList)
        self.combinedWwTitleRE = compileCombinedRegex(
                self.formatWwTitleExpressions, ignoreList)
        self.combinedHeadingsRE = compileCombinedRegex(
                self.formatHeadings, ignoreList)


#         self.wikiWordStart = u"["
#         self.wikiWordEnd = u"]"
# 
#         self.wikiWordStartEsc = ur"\["
#         self.wikiWordEndEsc = ur"\]"

#         if self.pWiki.wikiConfigFilename:
#             self.footnotesAsWws = self.pWiki.getConfig().getboolean(
#                     "main", "footnotes_as_wikiwords", False)

        # Needed in PageAst.Table.buildSubAst (placed here because of threading
        #   problem with re.compile            
        self.tableCutRe = re.compile(ur"\n|" + self.TitleWikiWordDelimiterPAT +
                ur"|" + self.PlainCharacterPAT + ur"+?(?=\n|" +
                self.TitleWikiWordDelimiterPAT + ur"|(?!.))", 
                re.DOTALL | re.UNICODE | re.MULTILINE)  # TODO Explain (if it works)

    
    def setCcWordBlacklist(self, bs):
        self.ccWordBlacklist = bs
        
    # TODO remove search fragment if present before testing
    def isInCcWordBlacklist(self, word):
        return word in self.ccWordBlacklist


    def isWikiWord(self, word):
        """
        Test if word is syntactically a wiki word
        """
        if matchWhole(self.WikiWordEditorRE, word):
            return not word in self.ccWordBlacklist
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
            return not word in self.ccWordBlacklist
            
        return False       


    def isNakedWikiWord(self, word):
        """
        Test if word is syntactically a naked wiki word
        """
        if self.isCcWikiWord(word):
            return True
            
        parword = self.BracketStart + word + self.BracketEnd
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
                    word[len(self.BracketStart):-len(self.BracketEnd)]):
                # If word is '[WikiWord]', return 'WikiWord' instead
                return word[len(self.BracketStart):-len(self.BracketEnd)]
            else:
                return word
        
        # No valid wiki word -> try to add brackets
        parword = self.BracketStart + word + self.BracketEnd
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
                return self.BracketStart + mat.group("wikiwordncc") + \
                        self.BracketEnd
        
        # No valid wiki word -> try to add brackets
        parword = self.BracketStart + word + self.BracketEnd
        mat = matchWhole(self.WikiWordEditorRE2, parword)
        if mat:
            if not self.footnotesAsWws and self.FootnoteRE.match(parword):
                return None

            return self.BracketStart + mat.group("wikiwordncc") + \
                    self.BracketEnd

        return None


    def wikiWordToLabel(self, word):
        """
        Strip '[' and ']' if present and return naked word
        """
        if word.startswith(self.BracketStart) and \
                word.endswith(self.BracketEnd):
            return word[len(self.BracketStart) : -len(self.BracketEnd)]
        return word
        
        
    def getPageTitlePrefix(self):
        """
        Return the default prefix for a wiki page main title.
        By default, it is u"++ "
        """
        return unescapeWithRe(self.wikiDocument.getWikiConfig().get(
                "main", "wikiPageTitlePrefix", "++"))


    def getExpressionsFormatList(self, expressions, formatDetails):
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
                # FormatTypes.Footnote: FormatTypes.Default}
        if formatDetails is None:
            formatDetails = WikiPageFormatDetails() # Default
        
        if not formatDetails.withCamelCase:
            modifier[FormatTypes.WikiWord] = FormatTypes.Default
        
        return [modifier.get(t, t) for re, t in expressions]



    def tokenizePage(self, text, formatDetails,
            threadholder=DUMBTHREADHOLDER):
        """
        Function used by PageAst module
        """
        if formatDetails is None:
            formatDetails = WikiPageFormatDetails() # Default

        if formatDetails.noFormat:
            # No formatting at all (used e.g. by some functional pages)
            return [Token(FormatTypes.Default, 0, {}, text)]
            
        # TODO Cache if necessary
        formatMap = self.getExpressionsFormatList(
                self.formatExpressions, formatDetails)
                
        tokenizer = Tokenizer(self.combinedPageRE, -1)
        
        return tokenizer.tokenize(text, formatMap,
                FormatTypes.Default, threadholder=threadholder)


    def tokenizeTodo(self, text, formatDetails=None,
            threadholder=DUMBTHREADHOLDER):
        """
        Function used by PageAst module
        """
        # TODO Cache if necessary
        formatMap = self.getExpressionsFormatList(
                self.formatTodoExpressions, formatDetails)

        tokenizer = Tokenizer(self.combinedTodoRE, -1)

        return tokenizer.tokenize(text, formatMap,
                FormatTypes.Default, threadholder=threadholder)


    def tokenizeTableContent(self, text, formatDetails=None, useTabDelimit=False,
            threadholder=DUMBTHREADHOLDER):
        """
        Function used by PageAst module
        useTabDelimit -- Use tabs as cell delimiters instead of XXX
        """
        # TODO Cache if necessary
        formatMap = self.getExpressionsFormatList(
                self.formatTableContentExpressions, formatDetails)
                
        if useTabDelimit:
            tokenizer = Tokenizer(self.combinedTableContentTabDelimitRE, -1)
        else:
            tokenizer = Tokenizer(self.combinedTableContentRE, -1)

        return tokenizer.tokenize(text, formatMap,
                FormatTypes.Default, threadholder=threadholder)


    def tokenizeTitle(self, text, formatDetails=None,
            threadholder=DUMBTHREADHOLDER):
        """
        Function used by PageAst module
        """
        # TODO Cache if necessary
        formatMap = self.getExpressionsFormatList(
                self.formatWwTitleExpressions, formatDetails)

        tokenizer = Tokenizer(self.combinedWwTitleRE, -1)

        return tokenizer.tokenize(text, formatMap,
                FormatTypes.Default, threadholder=threadholder)


    def differentiateHeadingLevel(self, text, tokenStartOffset, formatDetails=None):
        formatMap = self.getExpressionsFormatList(
                self.formatHeadings, formatDetails)

        it = TokenIterator(self.combinedHeadingsRE, formatMap,
                FormatTypes.Default, text, tokenStartOffset=tokenStartOffset)
        
        return it.next()



def isNakedWikiWordForNewWiki(word):
    """
    Function to solve a hen-egg problem:
    We need a name to create a new wiki, but the wiki must exist already
    to check if wiki name is syntactically correct.
    """
    global WikiWordEditorRE, WikiWordRE2, BracketStart, BracketEnd

    if matchWhole(WikiWordEditorRE, word):
        return True

    parword = BracketStart + word + BracketEnd
    if WikiWordRE2.match(parword):
        return True

    return False


def wikiWordToLabelForNewWiki(word):
    """
    Strip '[' and ']' if present and return naked word
    """
    global BracketStart, BracketEnd

    if word.startswith(BracketStart) and \
            word.endswith(BracketEnd):
        return word[len(BracketStart) : -len(BracketEnd)]
    return word
