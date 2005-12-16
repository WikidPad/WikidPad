from Enum import Enumeration
# from Config import faces

import srePersistent as re


FormatTypes = Enumeration("FormatTypes", ["Default", "WikiWord2", "WikiWord", "AvailWikiWord",                                          
                                          "Bold", "Italic", "Heading4", "Heading3", "Heading2", "Heading1",
                                          "Url", "Script", "Property", "ToDo",
                                          "HorizLine", "Bullet", "Numeric",
                                          "Suppress", "Footnote", "Table"], 1)


def compileCombinedRegex(expressions):
    """
    expressions -- List of tuples (r, s) where r is single compiled RE,
            s is a number from FormatTypes
    returns: compiled combined RE to feed into StringOps.Tokenizer
    """ 
    result = []
    for i in range(len(expressions)):
        r, s = expressions[i]
        result.append((u"(?P<style%i>" % i) + r.pattern + u")")
        
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
    

def getExpressionsFormatList(expressions, withCamelCase, footnotesAsWws):
    """
    Create from an expressions list (see compileCombinedRegex) a tuple
    of format types so that result[i] is the "right" number from
    FormatTypes when i is the index returned as second element of a tuple
    in the tuples list returned by the Tokenizer.

    In fact it is mainly the second tuple item from each expressions
    list element with some modifications according to the parameters
    withCamelCase -- Recognize camel-case words as wiki words instead
            of normal text
    footnotesAsWws -- Recognize footnotes (e.g. "[42]") as wiki-words
            instead of normal text
    """
    modifier = {FormatTypes.WikiWord2: FormatTypes.WikiWord}
    
    if not withCamelCase:
        modifier[FormatTypes.WikiWord] = FormatTypes.Default
    
    if footnotesAsWws:  # Footnotes (e.g. [42]) as wiki words
        modifier[FormatTypes.Footnote] = FormatTypes.WikiWord
    else:
        modifier[FormatTypes.Footnote] = FormatTypes.Default
        
    return _buildExpressionsUnindex(expressions, modifier)


def initialize(wikiSyntax):
    import WikiFormatting as ownmodule
    for item in dir(wikiSyntax):
        if item.startswith("_"):   # TODO check if necessary
            continue
        setattr(ownmodule, item, getattr(wikiSyntax, item))

    
    global FormatExpressions
    global CombinedSyntaxHighlightRE
    global UpdateExpressions
    global CombinedUpdateRE
    global HtmlExportExpressions
    global CombinedHtmlExportRE

# Most specific first

    FormatExpressions = [
            (TableRE, FormatTypes.Default),
            (SuppressHighlightingRE, FormatTypes.Default),
            (ScriptRE, FormatTypes.Script),
            (UrlRE, FormatTypes.Url),
            (ToDoRE, FormatTypes.ToDo),
            (PropertyRE, FormatTypes.Property),
            (FootnoteRE, FormatTypes.Footnote),
            (WikiWordEditorRE2, FormatTypes.WikiWord2),
            (WikiWordEditorRE, FormatTypes.WikiWord),
            (BoldRE, FormatTypes.Bold),
            (ItalicRE, FormatTypes.Italic),
            (Heading4RE, FormatTypes.Heading4),
            (Heading3RE, FormatTypes.Heading3),
            (Heading2RE, FormatTypes.Heading2),
            (Heading1RE, FormatTypes.Heading1)
            ]
            
    UpdateExpressions = [
            (TableRE, FormatTypes.Default),
            (SuppressHighlightingRE, FormatTypes.Default),
            (ScriptRE, FormatTypes.Script),
            (UrlRE, FormatTypes.Url),
            (ToDoREWithContent, FormatTypes.ToDo),
            (PropertyRE, FormatTypes.Property),
            (FootnoteRE, FormatTypes.Footnote),
            (WikiWordRE2, FormatTypes.WikiWord2),
            (WikiWordRE, FormatTypes.WikiWord),
            ]

    HtmlExportExpressions = [
            (TableRE, FormatTypes.Table),
            (SuppressHighlightingRE, FormatTypes.Suppress),
            (ScriptRE, FormatTypes.Script),
            (UrlRE, FormatTypes.Url),
            (ToDoREWithContent, FormatTypes.ToDo),
            (PropertyRE, FormatTypes.Property),
            (FootnoteRE, FormatTypes.Footnote),
            (WikiWordRE2, FormatTypes.WikiWord2),
            (WikiWordRE, FormatTypes.WikiWord),
            (BoldRE, FormatTypes.Bold),
            (ItalicRE, FormatTypes.Italic),
            (Heading4RE, FormatTypes.Heading4),
            (Heading3RE, FormatTypes.Heading3),
            (Heading2RE, FormatTypes.Heading2),
            (Heading1RE, FormatTypes.Heading1),
            (HorizLineRE, FormatTypes.HorizLine),
            (BulletRE, FormatTypes.Bullet),
            (NumericBulletRE, FormatTypes.Numeric)
            ]
            
    CombinedSyntaxHighlightRE = compileCombinedRegex(FormatExpressions)
    CombinedUpdateRE = compileCombinedRegex(UpdateExpressions)
    CombinedHtmlExportRE = compileCombinedRegex(HtmlExportExpressions)



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

def isWikiWord(word):
    """
    Test if word is syntactically a wiki word
    """
    return WikiWordRE.match(word) or (WikiWordRE2.match(word) and not \
            FootnoteRE.match(word))
 

def normalizeWikiWord(word, footnotesAsWws):
    """
    Try to normalize text to a valid wiki word and return it or None
    if it can't be normalized.
    """
    if WikiWordRE.match(word):
        return word
        
    if not footnotesAsWws and FootnoteRE.match(word):
        return None

    if WikiWordRE2.match(word):
        if WikiWordRE.match(word[1:-1]):
            # If word is '[WikiWord]', return 'WikiWord' instead
            return word[1:-1]
        else:
            return word
    
    # No valid wiki word -> try to add brackets
    if WikiWordRE2.match(u"[%s]" % word):
        return u"[%s]" % word
            
    return None





    
