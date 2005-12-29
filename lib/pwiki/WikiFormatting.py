from Enum import Enumeration
from MiscEvent import KeyFunctionSink
from Utilities import DUMBTHREADHOLDER
# from Config import faces

import srePersistent as re

from StringOps import Tokenizer


FormatTypes = Enumeration("FormatTypes", ["Default", "WikiWord2", "WikiWord", "AvailWikiWord",                                          
                                          "Bold", "Italic", "Heading4", "Heading3", "Heading2", "Heading1",
                                          "Url", "Script", "Property", "ToDo",
                                          "HorizLine", "Bullet", "Numeric",
                                          "Suppress", "Footnote", "Table"], 1)

EMPTY_RE = re.compile(ur"", re.DOTALL | re.UNICODE | re.MULTILINE)

def compileCombinedRegex(expressions):
    """
    expressions -- List of tuples (r, s) where r is single compiled RE,
            s is a number from FormatTypes
    returns: compiled combined RE to feed into StringOps.Tokenizer
    """ 
    result = []
    for i in range(len(expressions)):
        r, s = expressions[i]
        if type(r) is type(EMPTY_RE):
            r = r.pattern
        else:
            r = unicode(r)
        result.append(u"(?P<style%i>%s)" % (i, r))

    return re.compile(u"|".join(result),
            re.DOTALL | re.UNICODE | re.MULTILINE)
    
    
def _buildExpressionsUnindex(expressions, modifier):
    """
    Helper for getExpressionsFormatList().
    Create from an expressions list (see compileCombinedRegex) a tuple
    of format types so that result[i] is the "right" number from
    FormatTypes when i is the index returned as second element of a tuple
    in the tuples list returned by the Tokenizer.

    In fact it is mainly the second tuple item from each expressions
    list element.
    modifier -- Dict. If a format type in expressions matches a key
            in modifier, it is replaced by its value in the result
    """
    
    return [modifier.get(t, t) for re, t in expressions]
    

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

        self.rebuildFormatting(None)


    def rebuildFormatting(self, miscevt):
        """
        Called after a new wiki is loaded or options were changed.
        It rebuilds regexes and sets other variables according to
        the new settings
        """
        # Most specific first
        self.formatExpressions = [
                (self.TableRE, FormatTypes.Table),
                (self.SuppressHighlightingRE, FormatTypes.Default),
                (self.ScriptRE, FormatTypes.Script),
                (self.UrlRE, FormatTypes.Url),
                (self.ToDoREWithContent, FormatTypes.ToDo),
                (self.PropertyRE, FormatTypes.Property),
                (self.FootnoteRE, FormatTypes.Footnote),
                (self.WikiWordEditorRE2, FormatTypes.WikiWord2),
                (self.WikiWordEditorRE, FormatTypes.WikiWord),
                (self.BoldRE, FormatTypes.Bold),
                (self.ItalicRE, FormatTypes.Italic),
                (self.Heading4RE, FormatTypes.Heading4),
                (self.Heading3RE, FormatTypes.Heading3),
                (self.Heading2RE, FormatTypes.Heading2),
                (self.Heading1RE, FormatTypes.Heading1),
                (self.BulletRE, FormatTypes.Bullet),
                (self.NumericBulletRE, FormatTypes.Numeric),
                (self.HorizLineRE, FormatTypes.HorizLine)
                ]
                
                
        self.formatCellExpressions = [
                (self.UrlRE, FormatTypes.Url),
#                 (self.ToDoREWithContent, FormatTypes.ToDo),  # TODO Doesn't work
                (self.FootnoteRE, FormatTypes.Footnote),
                (self.WikiWordEditorRE2, FormatTypes.WikiWord2),
                (self.WikiWordEditorRE, FormatTypes.WikiWord),
                (self.BoldRE, FormatTypes.Bold),
                (self.ItalicRE, FormatTypes.Italic),
                ]
                
        self.combinedPageRE = compileCombinedRegex(self.formatExpressions)
        self.combinedCellRE = compileCombinedRegex(self.formatCellExpressions)

        self.wikiWordStart = u"["
        self.wikiWordEnd = u"]"
        
        self.wikiWordStartEsc = ur"\["
        self.wikiWordEndEsc = ur"\]"
        
        if self.pWiki.wikiConfigFilename:
            self.footnotesAsWws = self.pWiki.getConfig().getboolean(
                    "main", "footnotes_as_wikiwords", False)

    
    def isWikiWord(self, word):
        """
        Test if word is syntactically a wiki word
        """
        if self.WikiWordRE.match(word):
            return True
        if self.WikiWordRE2.match(word):
            if self.footnotesAsWws:
                return True
            else:
                return not self.FootnoteRE.match(word)
        
        return False
    
    
    # TODO  What to do if wiki word start and end are configurable?
    def normalizeWikiWordImport(self, word):
        """
        Special version for WikidPadCompact to support importing of
        .wiki files into the database
        """
        if self.WikiWordRE.match(word):
            return word
            
        if self.WikiWordRE2.match(word):
            if self.WikiWordRE.match(
                    word[len(self.wikiWordStart):-len(self.wikiWordEnd)]):
                # If word is '[WikiWord]', return 'WikiWord' instead
                return word[len(self.wikiWordStart):-len(self.wikiWordEnd)]
            else:
                return word
        
        # No valid wiki word -> try to add brackets
        if self.WikiWordRE2.match(self.wikiWordStart + word + self.wikiWordEnd):
            return self.wikiWordStart + word + self.wikiWordEnd

        return None


    def normalizeWikiWord(self, word):
        """
        Try to normalize text to a valid wiki word and return it or None
        if it can't be normalized.
        """
        mat = self.WikiWordEditorRE.match(word)
        if mat:
            return mat.group("wikiword")
            
        mat = self.WikiWordEditorRE2.match(word)
        if mat:
            if not self.footnotesAsWws and self.FootnoteRE.match(word):
                return None

            if self.WikiWordEditorRE.match(mat.group("wikiwordncc")):
                # If word is '[WikiWord]', return 'WikiWord' instead
                return mat.group("wikiwordncc")
            else:
                return self.wikiWordStart + mat.group("wikiwordncc") + self.wikiWordEnd
        
        # No valid wiki word -> try to add brackets
        parword = self.wikiWordStart + word + self.wikiWordEnd
        mat = self.WikiWordEditorRE2.match(parword)
        if mat:
            if not self.footnotesAsWws and self.FootnoteRE.match(parword):
                return None

            return self.wikiWordStart + mat.group("wikiwordncc") + self.wikiWordEnd

        return None


    def wikiWordToLabel(self, word):
        """
        Strip '[' and ']' if non camelcase word and return it
        """
        if word.startswith(self.wikiWordStart) and \
                word.endswith(self.wikiWordEnd):
            return word[len(self.wikiWordStart):-len(self.wikiWordEnd)]
        return word


    def getExpressionsFormatList(self, expressions, withCamelCase=None):
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
        if withCamelCase is None:
            withCamelCase = self.pWiki.wikiWordsEnabled
        
        if not withCamelCase:
            modifier[FormatTypes.WikiWord] = FormatTypes.Default
        
        if self.footnotesAsWws:  # Footnotes (e.g. [42]) as wiki words
            modifier[FormatTypes.Footnote] = FormatTypes.WikiWord
        else:
            modifier[FormatTypes.Footnote] = FormatTypes.Default
            
        return _buildExpressionsUnindex(expressions, modifier)


    def tokenizePage(self, text, threadholder=DUMBTHREADHOLDER):
        """
        Function used by PageAst module
        """
        # TODO Cache if necessary
        formatMap = self.getExpressionsFormatList(
                self.formatExpressions)
                
        tokenizer = Tokenizer(self.combinedPageRE, -1)
        
        return tokenizer.tokenize(text, formatMap, FormatTypes.Default,
                threadholder=threadholder)


    def tokenizeCell(self, text, threadholder=DUMBTHREADHOLDER):
        """
        Function used by PageAst module
        """
        # TODO Cache if necessary
        formatMap = self.getExpressionsFormatList(
                self.formatCellExpressions)  # TODO non camelcase !!!!
                
        tokenizer = Tokenizer(self.combinedCellRE, -1)
        
        return tokenizer.tokenize(text, formatMap, FormatTypes.Default,
                threadholder=threadholder)
