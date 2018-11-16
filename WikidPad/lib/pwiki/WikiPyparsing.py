

## import hotshot
## _prof = hotshot.Profile("hotshot.prf")

## _profRunning = 0
# import cProfile as profile
# _prof = profile.Profile("hotshot.prf")


# module pyparsing.py
#
# Copyright (c) 2003-2009  Paul T. McGuire
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
# IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
# CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
# TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
# SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
#



__doc__ = \
"""
pyparsing module - Classes and methods to define and execute parsing grammars

The pyparsing module is an alternative approach to creating and executing simple grammars,
vs. the traditional lex/yacc approach, or the use of regular expressions.  With pyparsing, you
don't need to learn a new syntax for defining grammars or matching expressions - the parsing module
provides a library of classes that you use to construct the grammar directly in Python.

Here is a program to parse "Hello, World!" (or any greeting of the form "<salutation>, <addressee>!")::

    from pyparsing import Word, alphas

    # define grammar of a greeting
    greet = Word( alphas ) + "," + Word( alphas ) + "!"

    hello = "Hello, World!"
    print hello, "->", greet.parseString( hello )

The program outputs the following::

    Hello, World! -> ['Hello', ',', 'World', '!']

The Python representation of the grammar is quite readable, owing to the self-explanatory
class names, and the use of '+', '|' and '^' operators.

The parsed results returned from parseString() can be accessed as a nested list, a dictionary, or an
object with named attributes.

The pyparsing module handles some of the problems that are typically vexing when writing text parsers:
 - extra or missing whitespace (the above program will also handle "Hello,World!", "Hello  ,  World  !", etc.)
 - quoted strings
 - embedded comments
"""

__version__ = "1.5.2"
__versionTime__ = "17 February 2009 19:45"
__author__ = "Paul McGuire <ptmcg@users.sourceforge.net>"

import string
from weakref import ref as wkref
import copy, time
import sys
import warnings
import re
import sre_constants
import traceback

from .Utilities import DUMBTHREADSTOP
#~ sys.stderr.write( "testing pyparsing module, version %s, %s\n" % (__version__,__versionTime__ ) )

__all__ = [
'And', 'CaselessKeyword', 'CaselessLiteral', 'CharsNotIn', 'Choice', 'Combine', 'Each', 'Empty',    # 'Dict', 
'FindFirst', 'FollowedBy', 'Forward', 'GoToColumn', 'Group', 'Keyword', 'LineEnd', 'LineStart', 'Literal',
'MatchFirst', 'NoMatch', 'NonTerminalNode', 'NotAny', 'OneOrMore', 'OnlyOnce', 'Optional', 'Or',
'ParseBaseException', 'ParseElementEnhance', 'ParseException', 'ParseExpression', 'ParseFatalException',
'ParseSyntaxException', 'ParserElement', 'QuotedString', 'RecursiveGrammarException',   # 'ParseResults',
'Regex', 'SkipTo', 'StringEnd', 'StringStart', 'Suppress', 'SyntaxNode', 'TerminalNode', 'Token', 'TokenConverter', 'Upcase',
'White', 'Word', 'WordEnd', 'WordStart', 'ZeroOrMore',
'alphanums', 'alphas', 'alphas8bit', 'buildSyntaxNode', 'cStyleComment', 'col',   # 'anyCloseTag', 'anyOpenTag'
'commaSeparatedList', 'commonHTMLEntity', 'countedArray', 'cppStyleComment', 'dblQuotedString',
'dblSlashComment', 'delimitedList', 'downcaseTokens', 'empty', 'getTokenLength', 'getTokensEndLoc', 'hexnums',
'htmlComment', 'javaStyleComment', 'keepOriginalText', 'line', 'lineEnd', 'lineStart', 'lineno',
'matchOnlyAtCol', 'matchPreviousExpr', 'matchPreviousLiteral',    # 'makeHTMLTags', 'makeXMLTags'
'nestedExpr', 'nullDebugAction', 'nums', 'oneOf', 'opAssoc', 'operatorPrecedence', 'printables',
'punc8bit', 'pythonStyleComment', 'quotedString', 'removeQuotes', 'replaceHTMLEntity',
'replaceWith', 'restOfLine', 'sglQuotedString', 'srange', 'stringEnd',
'stringStart', 'traceParseAction', 'unicodeString', 'upcaseTokens', 'withAttribute',
'indentedBlock', 'originalTextFor',
]


"""
Detect if we are running version 3.X and make appropriate changes
Robert A. Clark
"""
if sys.version_info[0] > 2:
    _PY3K = True
    _MAX_INT = sys.maxsize
    str = str
else:
    _PY3K = False
    _MAX_INT = sys.maxsize

if not _PY3K:
    def _ustr(obj):
        """Drop-in replacement for str(obj) that tries to be Unicode friendly. It first tries
           str(obj). If that fails with a UnicodeEncodeError, then it tries unicode(obj). It
           then < returns the unicode object | encodes it with the default encoding | ... >.
        """
        if isinstance(obj,str):
            return obj

        try:
            # If this works, then _ustr(obj) has the same behaviour as str(obj), so
            # it won't break any existing code.
            return str(obj)

        except UnicodeEncodeError:
            # The Python docs (http://docs.python.org/ref/customization.html#l2h-182)
            # state that "The return value must be a string object". However, does a
            # unicode object (being a subclass of basestring) count as a "string
            # object"?
            # If so, then return a unicode object:
            return str(obj)
            # Else encode it... but how? There are many choices... :)
            # Replace unprintables with escape codes?
            #return unicode(obj).encode(sys.getdefaultencoding(), 'backslashreplace_errors')
            # Replace unprintables with question marks?
            #return unicode(obj).encode(sys.getdefaultencoding(), 'replace')
            # ...
else:
    _ustr = str
    chr = chr

if not _PY3K:
	def _str2dict(strg):
	    return dict( [(c,0) for c in strg] )
else:
	_str2dict = set

def _xml_escape(data):
    """Escape &, <, >, ", ', etc. in a string of data."""

    # ampersand must be replaced first
    from_symbols = '&><"\''
    to_symbols = ['&'+s+';' for s in "amp gt lt quot apos".split()]
    for from_,to_ in zip(from_symbols, to_symbols):
        data = data.replace(from_, to_)
    return data

class _Constants:
    pass

if not _PY3K:
    alphas     = string.lowercase + string.uppercase
else:
    alphas     = string.ascii_lowercase + string.ascii_uppercase
nums       = string.digits
hexnums    = nums + "ABCDEFabcdef"
alphanums  = alphas + nums
_bslash = chr(92)
printables = "".join( [ c for c in string.printable if c not in string.whitespace ] )

class ParseBaseException(Exception):
    """base exception class for all parsing runtime exceptions"""
    # Performance tuning: we construct a *lot* of these, so keep this
    # constructor as small and fast as possible
    def __init__( self, pstr, loc=0, msg=None, elem=None ):
        self.loc = loc
        if msg is None:
            self.msg = pstr
            self.pstr = ""
        else:
            self.msg = msg
            self.pstr = pstr
        self.parserElement = elem

    def __getattr__( self, aname ):
        """supported attributes by name are:
            - lineno - returns the line number of the exception text
            - col - returns the column number of the exception text
            - line - returns the line containing the exception text
        """
        if( aname == "lineno" ):
            return lineno( self.loc, self.pstr )
        elif( aname in ("col", "column") ):
            return col( self.loc, self.pstr )
        elif( aname == "line" ):
            return line( self.loc, self.pstr )
        else:
            raise AttributeError(aname)

    def __str__( self ):
        return "%s (at char %d), (line:%d, col:%d)" % \
                ( self.msg, self.loc, self.lineno, self.column )
    def __unicode__( self ):
        return "%s (at char %d), (line:%d, col:%d)" % \
                ( self.msg, self.loc, self.lineno, self.column )
    def __repr__( self ):
        return _ustr(self)
    def markInputline( self, markerString = ">!<" ):
        """Extracts the exception line from the input string, and marks
           the location of the exception with a special symbol.
        """
        line_str = self.line
        line_column = self.column - 1
        if markerString:
            line_str = "".join( [line_str[:line_column],
                                markerString, line_str[line_column:]])
        return line_str.strip()
    def __dir__(self):
        return "loc msg pstr parserElement lineno col line " \
               "markInputLine __str__ __repr__".split()

class ParseException(ParseBaseException):
    """exception thrown when parse expressions don't match class;
       supported attributes by name are:
        - lineno - returns the line number of the exception text
        - col - returns the column number of the exception text
        - line - returns the line containing the exception text
    """
    pass

class ParseFatalException(ParseBaseException):
    """user-throwable exception thrown when inconsistent parse content
       is found; stops all parsing immediately"""
    pass

class ParseSyntaxException(ParseFatalException):
    """just like ParseFatalException, but thrown internally when an
       ErrorStop indicates that parsing is to stop immediately because
       an unbacktrackable syntax error has been found"""
    def __init__(self, pe):
        super(ParseSyntaxException, self).__init__(
                                    pe.pstr, pe.loc, pe.msg, pe.parserElement)

#~ class ReparseException(ParseBaseException):
    #~ """Experimental class - parse actions can raise this exception to cause
       #~ pyparsing to reparse the input string:
        #~ - with a modified input string, and/or
        #~ - with a modified start location
       #~ Set the values of the ReparseException in the constructor, and raise the
       #~ exception in a parse action to cause pyparsing to use the new string/location.
       #~ Setting the values as None causes no change to be made.
       #~ """
    #~ def __init_( self, newstring, restartLoc ):
        #~ self.newParseText = newstring
        #~ self.reparseLoc = restartLoc

class RecursiveGrammarException(Exception):
    """exception thrown by validate() if the grammar could be improperly recursive"""
    def __init__( self, parseElementList ):
        self.parseElementTrace = parseElementList

    def __str__( self ):
        return "RecursiveGrammarException: %s" % self.parseElementTrace

RE_ALL = re.IGNORECASE | re.LOCALE | re.MULTILINE | re.DOTALL | re.UNICODE | re.VERBOSE


class NecessaryRegexProvider:
    """
    Classes implementing this may provide a regex which must necessarily match
    to match the parser element. If getRegex() returns None, such a regex
    can't be provided for this particular object.
    """

    def getRegex(self):
        return None

    def getRegexFlagsMask(self):
        """
        Return bitmask with only the relevant flags.
        """
        return RE_ALL

    def isRegexComplete(self):
        """
        Returns True if the regex does not only provide a necessary match but
        the complete match of the parser element. Even if this returns True,
        there may be actions which prevent the element from matching
        """
        return False





# class _ParseResultsWithOffset:
#     def __init__(self,p1,p2):
#         self.tup = (p1,p2)
#     def __getitem__(self,i):
#         return self.tup[i]
#     def __repr__(self):
#         return repr(self.tup)



def getTokenLength(tokList):
    if isinstance(tokList, list):
        try:
            return sum((getTokenLength(t) for t in tokList))
        except:
            raise
    elif isinstance(tokList, str):
        return len(tokList)
    elif isinstance(tokList, SyntaxNode):
        return tokList.strLength
    elif len(tokList) == 0:
        return 0



class SyntaxNode:
    __slots__ = ("pos", "strLength", "name", "__dict__", "__weakref__")
    def __init__(self, pos, name):
        self.name = name
        self.pos = pos


    def isTerminal(self):
        raise NotImplementedError  # abstract

    def asList(self):
        raise NotImplementedError  # abstract

    def asNonTerminal(self):
        raise NotImplementedError  # abstract

    def asStringList(self, sep=''):
        raise NotImplementedError  # abstract

    def getString(self):
        """
        Get concatenated string of all content in this node (and subnodes)
        """
        raise NotImplementedError  # abstract

    def recalcStrLength(self):
        raise NotImplementedError  # abstract

    def findNodesForCharPos(self, charPos):
        raise NotImplementedError  # abstract

    def cloneDeep(self):
        raise NotImplementedError  # abstract


    @staticmethod
    def pprintList(lst):
        result = []
        result.append("[\n")

        for item in lst:
            item._pprintRecurs(0, 2, result)
            result.append("\n")

        result.append("]")
        
        return "".join(result)

    def pprint(self, ind=0, inc=2):
        result = []
        self._pprintRecurs(ind, inc, result)

        return "".join(result)
        

    def _pprintRecurs(self, ind, inc, result):
        raise NotImplementedError  # abstract


class NonTerminalNode(SyntaxNode):
    __slots__ = ("sub",)

    def __init__(self, sub, pos, name):
        super(NonTerminalNode, self).__init__(pos, name)

        self.sub = sub
        self._calcedStrLength = -1 # sum(t.strLength for t in sub)


    def __repr__(self):
        if self.__dict__:
            return "NonTerminalNode" + repr((self.pos, self.strLength, self.name, self.sub, self.__dict__))
        else:
            return "NonTerminalNode" + repr((self.pos, self.strLength, self.name, self.sub))

    def isTerminal(self):
        return False

    def getChildren(self):
        return self.sub
        
    def getChildrenCount(self):
        return len(self.sub)
        
    def asList(self):
        return self.sub
    
    def asNonTerminal(self):
        return self

    def asStringList( self, sep='' ):
        out = []
        for item in self.sub:
            if out and sep:
                out.append(sep)
            if isinstance( item, SyntaxNode ):
                out += item.asStringList()
            else:
                out.append( _ustr(item) )
        return out

    def getString(self):
        return "".join([sn.getString() for sn in self.sub])

    @property
    def strLength(self):
        if self._calcedStrLength == -1:
            self.recalcStrLength()
        
        return self._calcedStrLength


    def recalcStrLength(self):
        self._calcedStrLength = sum(t.strLength for t in self.sub)
#         # TODO Call recursively for children?
#         self.strLength = getTokenLength(self.sub)


    def __iter__(self):
        return iter(self.sub)
        
    # "flat" means that it does not go deeper recursively

    def iterFlatByName(self, name, start=0):
        """
        Iterate over all elements with the given name.
        """
        for node in self.sub[start:]:
            if node.name == name:
                yield node


    def findFlatByName(self, name, start=0, default=None):
        """
        Return first element with given name or return default.
        """
        for node in self.sub[start:]:
            if node.name == name:
                return node
        
        return default


    def iterFlatNamed(self, start=0):
        """
        Iterate over all items which have a name
        """
        if start > 0:
            for node in self.sub[start:]:
                if node.name is not None and node.name != "":
                    yield node
        else:
            for node in self.sub:
                if node.name is not None and node.name != "":
                    yield node

    # Just for symmetry
    iterFlat = __iter__


    def iterSelectedDeepByName(self, name, deepSet, start=0):
        """
        Iterate over all elements with the given name. If an NTNode
        is found that is contained in deepSet, its children are searched, too.
        """
        for node in self.sub[start:]:
            if node.name == name:
                yield node
            if node.name in deepSet and isinstance(node, NonTerminalNode):
                for inner in node.iterSelectedDeepByName(name, deepSet):
                    yield inner


    def iterUnselectedDeepByName(self, name, negativeDeepSet, start=0):
        """
        Iterate over all elements with the given name. If an NTNode
        is found that is NOT contained in negativeDeepSet,
        its children are searched, too.
        """
        for node in self.sub[start:]:
            if node.name == name:
                yield node
            if isinstance(node, NonTerminalNode) and node.name not in negativeDeepSet:
                for inner in node.iterUnselectedDeepByName(name, negativeDeepSet):
                    yield inner


    def iterDeepByName(self, name, start=0):
        """
        Iterate over all elements with the given name with depth first.
        """
        for node in self.sub[start:]:
            if node.name == name:
                yield node
            if isinstance(node, NonTerminalNode):
                for inner in node.iterDeepByName(name):
                    yield inner

    def iterDeep(self, start=0):
        """
        Iterate over all elements.
        """
        for node in self.sub[start:]:
            yield node
            if isinstance(node, NonTerminalNode):
                for inner in node.iterDeep():
                    yield inner



#     def findFlatNodeIdxForCharPos(self, charPos):
#         lo = 0
#         hi = self.getChildrenCount()
#         while lo < hi:
#             mid = (lo+hi)//2
#             if charPos < self[mid].pos: hi = mid
#             else: lo = mid+1
# 
#         index = lo - 1
# 
#         if index == -1:
#             # Before first token
#             return -1
# 
#         node = self[index]
# 
#         if lo == self.getChildrenCount() and \
#                 charPos >= (node.pos + node.strLength):
#             # After last token
#             return -2
# 
#         return index
# 
# 
#     def findFlatNodesForCharSel(self, charStartPos, charAfterLastPos):
#         startIdx = self.findFlatNodeIdxForCharPos(charStartPos)
#         
#         if startIdx == -2:
#             # Start is already after last token -> no tokens available
#             return []
#         
#         if startIdx == -1:
#             startIdx = 0
# 
#         endIdx = self.findFlatNodeIdxForCharPos(charAfterLastPos)
#         
#         if endIdx == -1:
#             # End is yet before first token -> no tokens available
#             return []
#         
#         if endIdx == -2:
#             endIdx = -1
#         else:
#             
#         
#         return self.sub[
        


    def findNodesForCharPos(self, charPos):
        # Algorithm taken from standard lib bisect module
        lo = 0
        hi = self.getChildrenCount()
        while lo < hi:
            mid = (lo+hi)//2
            if charPos < self[mid].pos: hi = mid
            else: lo = mid+1

        index = lo - 1

        if index == -1:
            # Before first token
            return []

        node = self[index]

#         if lo == self.getChildrenCount() and \
#                 charPos >= (node.pos + node.strLength):
        if charPos >= (node.pos + node.strLength):
            # After last token or outside of any token
            return []

        result = node.findNodesForCharPos(charPos)
        result.append(node)
        return result


    def findFlatNodeIndexForCharPos(self, charPos):
        # Algorithm taken from standard lib bisect module
        lo = 0
        hi = self.getChildrenCount()
        while lo < hi:
            mid = (lo+hi)//2
            if charPos < self[mid].pos: hi = mid
            else: lo = mid+1

        index = lo - 1

        if index == -1:
            # Before first token
            return -1

        node = self[index]
        if charPos >= (node.pos + node.strLength):
            # After last token or outside of any token
            return -1

        return index
        

    def cloneDeep(self):
        ret = NonTerminalNode(self.sub, self.pos, self.name)
        ret.__dict__ = self.__dict__.copy()
        ret.sub = [n.cloneDeep() for n in self.sub]

        return ret


    def _pprintRecurs(self, ind, inc, result):
        if self.__dict__:
            result.append(" " * ind + "NtNode(%s, %s, %s, %s, " %
                    (self.pos, self.strLength, repr(self.name), repr(self.__dict__)))
        else:
            result.append(" " * ind + "NtNode(%s, %s, %s, " %
                    (self.pos, self.strLength, repr(self.name)))
        
        if isinstance(self.sub, list):
            result.append("[\n")
            
            newInd = ind + inc
            for item in self.sub:
                item._pprintRecurs(newInd, inc, result)
                result.append("\n")
            
            result.append(" " * ind + "]  (" + repr(self.name) + ")")


    def __getitem__( self, i ):
        assert isinstance( i, (int,slice) )
        return self.sub[i]

    def __setitem__( self, i, v ):
        assert isinstance( i, (int,slice) )
        
        if isinstance(v, SyntaxNode):
            v = v.getChildren()
 
        self.sub[i] = v

    def __delitem__( self, i ):
        assert isinstance( i, (int,slice) )

        del self.sub[i]
        
    
#     def copy( self ):
#         ret = SyntaxNode(self.sub, self.pos, self.name)
#         ret.sub = self.sub[:]
# 
#         return ret


    def __add__(self, other):
        ret = self.copy()
        ret += other
        return ret

    def __iadd__(self, other):
        if isinstance(other, list):
            self.sub += other
        else:   #   isinstance(other, SyntaxNode):
            self.sub += other.sub
        return self


    def append(self, item):
        self.sub.append(item)

    def prepend(self, item):
        self.sub.insert(0, item)



class TerminalNode(SyntaxNode):
    __slots__ = ("text",)

    def __init__(self, text, pos, name):
        super(TerminalNode, self).__init__(pos, name)

        self.text = text
        self.strLength = len(text)


    def __repr__(self):
        if self.__dict__:
            return "TerminalNode" + repr((self.pos, self.strLength, self.name, self.text, self.__dict__))
        else:
            return "TerminalNode" + repr((self.pos, self.strLength, self.name, self.text))

    def isTerminal(self):
        return True

    def getText(self):
        return self.text

    def asList(self):
        return [ self ]
    
    def asNonTerminal(self):
        return NonTerminalNode([self], self.pos, "")

    def asStringList(self, sep=''):
        return [ self.text ]
        
    def recalcStrLength(self):
        self.strLength = len(self.text)

    def getString(self):
        return self.text

    def iterFlatNamed(self, start=0):
        """
        Iterate over all items which have a name
        """
        if self.name is not None and self.name != "":
            yield self

    def findNodesForCharPos(self, charPos):
        if charPos < self.pos or charPos >= (self.pos + self.strLength):
            return []
        
        return [self]


    def _pprintRecurs(self, ind, inc, result):
        if self.__dict__:
            result.append(" " * ind + "TNode(%s, %s, %s, %s, " %
                    (self.pos, self.strLength, repr(self.name), repr(self.__dict__)))
        else:
            result.append(" " * ind + "TNode(%s, %s, %s, " %
                    (self.pos, self.strLength, repr(self.name)))
        result.append("%s)" % repr(self.text))


    def cloneDeep(self):
        ret = TerminalNode(self.text, self.pos, self.name)
        ret.__dict__ = self.__dict__.copy()

        return ret



    def copy(self):
        return TerminalNode(self.text, self.pos, self.name)




class ParsingState:
    """
    State object handed to action callbacks with additional information
    about the parsing state.
    All member variables can be accessed directly
    """
    def __init__(self, fullText, baseDict=None, threadstop=DUMBTHREADSTOP):
        self.nameStack = []
        self.dictStack = StackedCopyDict(baseDict)
        if threadstop is None:
            self.threadstop = DUMBTHREADSTOP
        else:
            self.threadstop = threadstop
        self.fullText = fullText
        self.revText = "".join(reversed(fullText))
        self.debugIndent = 0




def buildSyntaxNode(sub, pos=-1, name=None):
    if isinstance(sub, str):   # sub.__class__ is unicode:
        return TerminalNode(sub, pos, name)
    elif isinstance(sub, SyntaxNode):
        if pos != -1:
            sub.pos = pos
        if name is not None and name != "":
            sub.name = name
        return sub
    else:
        return NonTerminalNode(sub, pos, name)



def col (loc,strg):
    """Returns current column within a string, counting newlines as line separators.
   The first column is number 1.

   Note: the default parsing behavior is to expand tabs in the input string
   before starting the parsing process.  See L{I{ParserElement.parseString}<ParserElement.parseString>} for more information
   on parsing strings containing <TAB>s, and suggested methods to maintain a
   consistent view of the parsed string, the parse location, and line and column
   positions within the parsed string.
   """
    return (loc<len(strg) and strg[loc] == '\n') and 1 or loc - strg.rfind("\n", 0, loc)

def lineno(loc,strg):
    """Returns current line number within a string, counting newlines as line separators.
   The first line is number 1.

   Note: the default parsing behavior is to expand tabs in the input string
   before starting the parsing process.  See L{I{ParserElement.parseString}<ParserElement.parseString>} for more information
   on parsing strings containing <TAB>s, and suggested methods to maintain a
   consistent view of the parsed string, the parse location, and line and column
   positions within the parsed string.
   """
    return strg.count("\n",0,loc) + 1

def line( loc, strg ):
    """Returns the line of text containing loc within a string, counting newlines as line separators.
       """
    lastCR = strg.rfind("\n", 0, loc)
    nextCR = strg.find("\n", loc)
    if nextCR > 0:
        return strg[lastCR+1:nextCR]
    else:
        return strg[lastCR+1:]

# def _defaultStartDebugAction( instring, loc, expr ):
#     print ("Match " + _ustr(expr) + " at loc " + _ustr(loc) + "(%d,%d)" % ( lineno(loc,instring), col(loc,instring) ))
#     
# 
# def _defaultSuccessDebugAction( instring, startloc, endloc, expr, toks ):
#     if isinstance(toks, SyntaxNode):
#         toks = toks.asList()
#     print ("Matched " + _ustr(expr) + " -> " + str(toks))
# 
# def _defaultExceptionDebugAction( instring, loc, expr, exc ):
#     print ("Exception raised:" + _ustr(exc))
    


def nullDebugAction(*args):
    """'Do-nothing' debug action, to suppress debugging output during parsing."""
    pass

class ParserElement:
    """Abstract base level parser element class."""
    DEFAULT_WHITE_CHARS = " \n\t\r"

    def setDefaultWhitespaceChars( chars ):
        """Overrides the default whitespace chars
        """
        ParserElement.DEFAULT_WHITE_CHARS = chars
    setDefaultWhitespaceChars = staticmethod(setDefaultWhitespaceChars)

    def __init__( self ):
        self.parseStartAction = list()
        self.validateAction = list()
        self.parseAction = list()
        self.failAction = None
        #~ self.name = "<unknown>"  # don't define self.name, let subclasses try/except upcall
        self.strRepr = None
        self.resultsName = None
        self.whiteChars = ParserElement.DEFAULT_WHITE_CHARS
        self.skipWhitespace = self.whiteChars != ""
        self.copyDefaultWhiteChars = True
        self.mayReturnEmpty = False # used when checking for left-recursion
        self.keepTabs = False
        self.ignoreExprs = list()
        self.debug = False
        self.streamlined = False
        self.optimizing = False # To avoid endless recursion
        self.buildingRegex = False # To avoid endless recursion
        self.mayIndexError = True # used to optimize exception handling for subclasses that don't advance parse index
        self.errmsg = ""
#         self.modalResults = True # used to mark results names as modal (report only last) or cumulative (list all)
        self.debugActions = ( None, None, None ) #custom debug actions
        self.re = None
        self.callPreparse = True # used to avoid redundant calls to preParse
        self.callDuringTry = False


    def copy( self ):
        """Make a copy of this ParserElement.  Useful for defining different parse actions
           for the same parsing pattern, using copies of the original parse element."""
        cpy = copy.copy( self )
        cpy.parseStartAction = self.parseStartAction[:]
        cpy.validateAction = self.validateAction[:]
        cpy.parseAction = self.parseAction[:]
        cpy.ignoreExprs = self.ignoreExprs[:]
        if self.copyDefaultWhiteChars:
            cpy.whiteChars = ParserElement.DEFAULT_WHITE_CHARS
            cpy.skipWhitespace = cpy.whiteChars != ""
        return cpy
    

    def setName( self, name ):
        """Define name for this expression, for use in debugging."""
        self.name = name
        self.errmsg = "Expected " + self.name
        if hasattr(self,"exception"):
            self.exception.msg = self.errmsg
        return self

    def setResultsName( self, name, listAllMatches=False ):
        """Define name for referencing matching tokens as a nested attribute
           of the returned parse results.
           NOTE: this returns a *copy* of the original ParserElement object;
           this is so that the client can define a basic element, such as an
           integer, and reference it in multiple places with different names.
        """
        newself = self.copy()
        newself.resultsName = name
#         newself.modalResults = not listAllMatches
        return newself


    def setResultsNameNoCopy( self, name, listAllMatches=False ):
        """Define name for referencing matching tokens as a nested attribute
           of the returned parse results.
           NOTE: this returns no *copy* of the original ParserElement object
        """
        self.resultsName = name
#         newself.modalResults = not listAllMatches
        return self

        
    def getResultsName( self ):
        return self.resultsName

    def setBreak(self,breakFlag = True):
        """Method to invoke the Python pdb debugger when this element is
           about to be parsed. Set breakFlag to True to enable, False to
           disable.
        """
        if breakFlag:
            _parseMethod = self._parse
            def breaker(instring, loc, state, doActions=True, callPreParse=True):
                import pdb
                pdb.set_trace()
                return _parseMethod( instring, loc, state, doActions, callPreParse )
            breaker._originalParseMethod = _parseMethod
            self._parse = breaker
        else:
            if hasattr(self._parse,"_originalParseMethod"):
                self._parse = self._parse._originalParseMethod
        return self


# @staticmethod
    def _normalizeParseActionArgs( f ):
        """Internal method used to decorate parse actions that take fewer than 4 arguments,
           so that all parse actions can be called as f(s,l,st,t)."""
        STAR_ARGS = 4

        try:
            restore = None
            if isinstance(f,type):
                restore = f
                f = f.__init__
            if not _PY3K:
                codeObj = f.__code__
            else:
                codeObj = f.code
            if codeObj.co_flags & STAR_ARGS:
                return f
            numargs = codeObj.co_argcount
            if not _PY3K:
                if hasattr(f,"im_self"):
                    numargs -= 1
            else:
                if hasattr(f,"__self__"):
                    numargs -= 1
            if restore:
                f = restore
        except AttributeError:
            try:
                if not _PY3K:
                    call_im_func_code = f.__call__.__func__.__code__
                else:
                    call_im_func_code = f.__code__

                # not a function, must be a callable object, get info from the
                # im_func binding of its bound __call__ method
                if call_im_func_code.co_flags & STAR_ARGS:
                    return f
                numargs = call_im_func_code.co_argcount
                if not _PY3K:
                    if hasattr(f.__call__,"im_self"):
                        numargs -= 1
                else:
                    if hasattr(f.__call__,"__self__"):
                        numargs -= 0
            except AttributeError:
                if not _PY3K:
                    call_func_code = f.__call__.__code__
                else:
                    call_func_code = f.__call__.__code__
                # not a bound method, get info directly from __call__ method
                if call_func_code.co_flags & STAR_ARGS:
                    return f
                numargs = call_func_code.co_argcount
                if not _PY3K:
                    if hasattr(f.__call__,"im_self"):
                        numargs -= 1
                else:
                    if hasattr(f.__call__,"__self__"):
                        numargs -= 1


        #~ print ("adding function %s with %d args" % (f.func_name,numargs))
        if numargs == 4:
            return f
        else:
            if numargs > 4:
                def tmp(s,l,st,t):
                    return f(f.__call__.__self__, s,l,st,t)
            if numargs == 3:
                def tmp(s,l,st,t):
                    return f(s,l,t)
            elif numargs == 2:
                def tmp(s,l,st,t):
                    return f(l,t)
            elif numargs == 1:
                def tmp(s,l,st,t):
                    return f(t)
            else: #~ numargs == 0:
                def tmp(s,l,st,t):
                    return f()
            try:
                tmp.__name__ = f.__name__
            except (AttributeError,TypeError):
                # no need for special handling if attribute doesnt exist
                pass
            try:
                tmp.__doc__ = f.__doc__
            except (AttributeError,TypeError):
                # no need for special handling if attribute doesnt exist
                pass
            try:
                tmp.__dict__.update(f.__dict__)
            except (AttributeError,TypeError):
                # no need for special handling if attribute doesnt exist
                pass
            return tmp
    _normalizeParseActionArgs = staticmethod(_normalizeParseActionArgs)

    def setParseAction( self, *fns, **kwargs ):
        """Define action to perform when successfully matching parse element definition.
           Parse action fn is a callable method with 0-4 arguments, called as fn(s,loc,st,toks),
           fn(loc,toks), fn(toks), or just fn(), where:
            - s   = the original string being parsed (see note below)
            - loc = the location of the matching substring
            - st  = execution state of parsing
            - toks = a list of the matched tokens, packaged as a SyntaxNode object
           If the functions in fns modify the tokens, they can return them as the return
           value from fn, and the modified list of tokens will replace the original.
           Otherwise, fn does not need to return any value.

           Note: the default parsing behavior is to expand tabs in the input string
           before starting the parsing process.  See L{I{parseString}<parseString>} for more information
           on parsing strings containing <TAB>s, and suggested methods to maintain a
           consistent view of the parsed string, the parse location, and line and column
           positions within the parsed string.
           """
        self.parseAction = list(map(self._normalizeParseActionArgs, list(fns)))
        self.callDuringTry = ("callDuringTry" in kwargs and kwargs["callDuringTry"])
        return self

    def addParseAction( self, *fns, **kwargs ):
        """Add parse action to expression's list of parse actions. See L{I{setParseAction}<setParseAction>}."""
        self.parseAction += list(map(self._normalizeParseActionArgs, list(fns)))
        self.callDuringTry = self.callDuringTry or ("callDuringTry" in kwargs and kwargs["callDuringTry"])
        return self
        
    def setValidateAction(self, *fns, **kwargs):
        self.validateAction = list(fns)
        return self

    def addValidateAction( self, *fns, **kwargs):
        self.validateAction += list(fns)
        return self
        
    def setParseStartAction(self, *fns, **kwargs):
        self.parseStartAction = list(fns)
        return self

    def addParseStartAction( self, *fns, **kwargs):
        self.parseStartAction += list(fns)
        return self
        
        
    def setFailAction( self, fn ):
        """Define action to perform if parsing fails at this expression.
           Fail acton fn is a callable function that takes the arguments
           fn(s,loc,expr,err) where:
            - s = string being parsed
            - loc = location where expression match was attempted and failed
            - expr = the parse expression that failed
            - err = the exception thrown
           The function returns no value.  It may throw ParseFatalException
           if it is desired to stop parsing immediately."""
        self.failAction = fn
        return self

    def _skipIgnorables( self, instring, loc, state ):
        exprsFound = True
        while exprsFound:
            exprsFound = False
            for e in self.ignoreExprs:
                try:
                    while 1:
                        loc,dummy = e._parse( instring, loc, state )
                        exprsFound = True
                except ParseException:
                    pass
        return loc

    def preParse( self, instring, loc, state ):
        if self.ignoreExprs:
            loc = self._skipIgnorables( instring, loc, state )

        if self.skipWhitespace:
            wt = self.whiteChars
            instrlen = len(instring)
            while loc < instrlen and instring[loc] in wt:
                loc += 1

        return loc

    def getNamedElementNeedsPacking(self):
        """
        If the tokens returned by postParse() are a list and this element
        has a resultsName, the list is packed into a named NonTerminalSyntaxNode
        before further processing if this returns True
        """
        return False

    def parseImpl( self, instring, loc, state, doActions=True ):
        """
        parseImpl of derived classes can either return as second tuple item:
        A list of SyntaxNode s
        A string (interpreted as one-item-list of SyntaxNode s)
        One SyntaxNode (interpreted as one-item-list of SyntaxNode s)
        
        Instead of raising a ParseException the exception can be returned
        as second tuple item if first item is -1
        """
        return loc, []

    def postParse( self, instring, loc, state, tokenlist ):
        return tokenlist

    def _defaultStartDebugAction( self, instring, loc, expr, state ):
        if not self.debug:
            return

        if (self.debugActions[0] ):
            self.debugActions[0]( instring, loc, self )
        else:
            print((" " * state.debugIndent + "Match " + _ustr(expr) +
                    " at loc " + _ustr(loc) + "(%d,%d)" %
                    ( lineno(loc,instring), col(loc,instring) )))
            state.debugIndent += 2


    def _defaultSuccessDebugAction( self, instring, startloc, endloc, expr,
            toks, state ):
        if not self.debug:
            return

        if (self.debugActions[1] ):
            self.debugActions[1]( instring, loc, self )
        else:
            if isinstance(toks, SyntaxNode):
                toks = toks.asList()
            
            state.debugIndent -= 2
            print((" " * state.debugIndent + "Matched " + _ustr(expr) + " -> " + str(toks)))


    def _defaultExceptionDebugAction( self, instring, loc, expr, exc, state ):
        if not self.debug:
            return

        if self.debugActions[2]:
            self.debugActions[2]( instring, tokensStart, self, err )
        else:
            state.debugIndent -= 2
            print((" " * state.debugIndent + "Exception raised:" + _ustr(exc)))


    #~ @profile
    def _parseNoCache( self, instring, loc, state, doActions=True, callPreParse=True ):
##         global _profRunning
##         if _profRunning == 0: _prof.start()
##         _profRunning += 1

        assert loc > -1
        debugging = ( self.debug ) #and doActions )
        
        validResultName = bool(self.resultsName)
        if validResultName:
            state.nameStack.append(self.resultsName) # push to namestack

        ds = state.dictStack.push(self.resultsName)
        ds["parserElement"] = self
        ds["location"] = loc

        try:
            for psa in self.parseStartAction:
                psa(instring, loc, state, self)

            if debugging or self.failAction:
                self._defaultStartDebugAction( instring, loc, self, state )
                if callPreParse and self.callPreparse:
                    preloc = self.preParse( instring, loc, state )
                else:
                    preloc = loc
                tokensStart = loc
                try:
                    try:
                        loc,tokens = self.parseImpl( instring, preloc, state, doActions )
                        if loc == -1:
                            err = tokens
                            self._defaultExceptionDebugAction( instring, tokensStart,
                                    self, err, state )
                            if self.failAction:
                                self.failAction( instring, tokensStart, self, err )
                            return -1, err
                    except IndexError:
                        raise ParseException( instring, len(instring), self.errmsg, self )
                except ParseBaseException as err:
                    #~ print ("Exception raised:", err)
                    self._defaultExceptionDebugAction( instring, tokensStart,
                            self, err, state )
                    if self.failAction:
                        self.failAction( instring, tokensStart, self, err )
                    raise
            else:
                if callPreParse and self.callPreparse:
                    preloc = self.preParse( instring, loc, state )
                else:
                    preloc = loc
                tokensStart = loc

                if self.mayIndexError or loc >= len(instring):
                    try:
                        loc,tokens = self.parseImpl( instring, preloc, state, doActions )
                        if loc == -1:
                            return -1, tokens
                    except IndexError:
                        raise ParseException( instring, len(instring), self.errmsg, self )
                else:
                    loc,tokens = self.parseImpl( instring, preloc, state, doActions )
                    if loc == -1:
                        return -1, tokens

            if not isinstance(tokens, list):   # not tokens.__class__ is list:
                tokens = [buildSyntaxNode(tokens, tokensStart, self.resultsName)]

            tokens = self.postParse( instring, loc, state, tokens )
            if not isinstance(tokens, list):   # not tokens.__class__ is list:
                tokens = [buildSyntaxNode(tokens, tokensStart, self.resultsName)]
                retTokens = buildSyntaxNode(tokens, tokensStart)
            else:
                if self.getNamedElementNeedsPacking() and self.resultsName:
                    retTokens = buildSyntaxNode(tokens, tokensStart,
                            self.resultsName)
                else:
                    retTokens = buildSyntaxNode(tokens, tokensStart)

            try:
                for pc in self.validateAction:
                    pc(instring, preloc, state, retTokens)
            except ParseBaseException as err:
                #~ print "Exception raised in user validate action:", err
                self._defaultExceptionDebugAction( instring, tokensStart,
                        self, err, state )
                raise

            if self.parseAction and (doActions or self.callDuringTry):
                if debugging:
                    try:
                        for fn in self.parseAction:
                            tokens = fn( instring, tokensStart, state, retTokens )
                            if tokens is not None:
                                retTokens = tokens
                    except ParseBaseException as err:
                        #~ print "Exception raised in user parse action:", err
                        self._defaultExceptionDebugAction( instring, tokensStart,
                                self, err, state )
                        raise
                else:
                    for fn in self.parseAction:
                        tokens = fn( instring, tokensStart, state, retTokens )
                        if tokens is not None:
                            retTokens = tokens

            if debugging:
                #~ print ("Matched",self,"->",retTokens.asList())
                self._defaultSuccessDebugAction( instring, tokensStart, loc,
                        self, retTokens, state )

            if isinstance(retTokens, SyntaxNode):
                if retTokens.name:
                    retTokens = [retTokens]
                else:
                    retTokens = retTokens.asList()

            state.threadstop.testValidThread()
#             print "--Clock" , time.clock()
#             elif isinstance(retTokens, list) and len(retTokens) > 0 and self.resultsName:
#                 retTokens = [buildSyntaxNode(tokens, tokensStart, self.resultsName)]
            return loc, retTokens
        finally:
            state.dictStack.pop()

            if validResultName:
                state.nameStack.pop()
##             _profRunning -= 1
##             if _profRunning == 0: _prof.stop()



    def _parseNoAction( self, instring, loc, state, doActions=True, callPreParse=True ):
        """
        Optimizer ensures that this function is called instead of
        _parseNoCache() iff no actions are present
        (neither parse start nor validation nor parse).
        """
##         global _profRunning
##         if _profRunning == 0: _prof.start()
##         _profRunning += 1

        assert loc > -1
#         assert len(self.parseStartAction) == 0 and len(self.validateAction) == 0 \
#                 and len(self.parseAction) == 0

        debugging = ( self.debug ) #and doActions )
        
        validResultName = bool(self.resultsName)
        if validResultName:
            state.nameStack.append(self.resultsName) # push to namestack

        ds = state.dictStack.push(self.resultsName)
        ds["parserElement"] = self
        ds["location"] = loc

        try:
            if debugging:
                self._defaultStartDebugAction( instring, loc, self, state )
                if callPreParse and self.callPreparse:
                    preloc = self.preParse( instring, loc, state )
                else:
                    preloc = loc
                tokensStart = loc
                try:
                    try:
                        loc,tokens = self.parseImpl( instring, preloc, state, doActions )
                        if loc == -1:
                            err = tokens
                            self._defaultExceptionDebugAction( instring, tokensStart,
                                    self, err, state )
                            if self.failAction:
                                self.failAction( instring, tokensStart, self, err )
                            return -1, err
                    except IndexError:
                        raise ParseException( instring, len(instring), self.errmsg, self )
                except ParseBaseException as err:
                    #~ print ("Exception raised:", err)
                    self._defaultExceptionDebugAction( instring, tokensStart,
                            self, err, state )
                    if self.failAction:
                        self.failAction( instring, tokensStart, self, err )
                    raise
            else:
                if callPreParse and self.callPreparse:
                    preloc = self.preParse( instring, loc, state )
                else:
                    preloc = loc
                tokensStart = loc

                if self.mayIndexError or loc >= len(instring):
                    try:
                        loc,tokens = self.parseImpl( instring, preloc, state, doActions )
                        if loc == -1:
                            return -1, tokens
                    except IndexError:
                        raise ParseException( instring, len(instring), self.errmsg, self )
                else:
                    loc,tokens = self.parseImpl( instring, preloc, state, doActions )
                    if loc == -1:
                        return -1, tokens

            if not isinstance(tokens, list):   # not tokens.__class__ is list:
                tokens = [buildSyntaxNode(tokens, tokensStart, self.resultsName)]

            tokens = self.postParse( instring, loc, state, tokens )
            if not isinstance(tokens, list):   # not tokens.__class__ is list:
                retTokens = [buildSyntaxNode(tokens, tokensStart, self.resultsName)]
            else:
                if self.getNamedElementNeedsPacking() and self.resultsName:
                    retTokens = [buildSyntaxNode(tokens, tokensStart,
                            self.resultsName)]
                else:
                    retTokens = tokens

            if debugging:
                #~ print ("Matched",self,"->",retTokens.asList())
                self._defaultSuccessDebugAction( instring, tokensStart, loc,
                        self, retTokens, state )

#             if retTokens.name:
#                 retTokens = [retTokens]
#             else:
#                 retTokens = retTokens.asList()

            state.threadstop.testValidThread()
#             print "--Clock" , time.clock()
#             elif isinstance(retTokens, list) and len(retTokens) > 0 and self.resultsName:
#                 retTokens = [buildSyntaxNode(tokens, tokensStart, self.resultsName)]
            return loc, retTokens
        finally:
            state.dictStack.pop()

            if validResultName:
                state.nameStack.pop()
##             _profRunning -= 1
##             if _profRunning == 0: _prof.stop()



    def tryParse( self, instring, loc, state ):
        try:
            return self._parse( instring, loc, state, doActions=False )
        except ParseFatalException:
            return -1, ParseException( instring, loc, self.errmsg, self)
        except (ParseBaseException, IndexError) as err:
            return -1, err

#     # this method gets repeatedly called during backtracking with the same arguments -
#     # we can cache these arguments and save ourselves the trouble of re-parsing the contained expression
#     def _parseCache( self, instring, loc, state, doActions=True, callPreParse=True ):
# #         lookup = (self,instring,loc,callPreParse,doActions)
#         lookup = (self,instring,loc,tuple(state[0]),callPreParse,doActions)
#         if lookup in ParserElement._exprArgCache:
#             value = ParserElement._exprArgCache[ lookup ]
#             if isinstance(value,Exception):
#                 raise value
#             return value
#         else:
#             try:
#                 value = self._parseNoCache( instring, loc, state, doActions, callPreParse )
#                 ParserElement._exprArgCache[ lookup ] = (value[0],value[1].copy())
#                 return value
#             except ParseBaseException, pe:
#                 ParserElement._exprArgCache[ lookup ] = pe
#                 raise

    _parse = _parseNoCache

    # argument cache for optimizing repeated calls when backtracking through recursive expressions
    _exprArgCache = {}
    def resetCache():
        ParserElement._exprArgCache.clear()
    resetCache = staticmethod(resetCache)

    _packratEnabled = False
#     def enablePackrat():
#         """Enables "packrat" parsing, which adds memoizing to the parsing logic.
#            Repeated parse attempts at the same string location (which happens
#            often in many complex grammars) can immediately return a cached value,
#            instead of re-executing parsing/validating code.  Memoizing is done of
#            both valid results and parsing exceptions.
# 
#            This speedup may break existing programs that use parse actions that
#            have side-effects.  For this reason, packrat parsing is disabled when
#            you first import pyparsing.  To activate the packrat feature, your
#            program must call the class method ParserElement.enablePackrat().  If
#            your program uses psyco to "compile as you go", you must call
#            enablePackrat before calling psyco.full().  If you do not do this,
#            Python will crash.  For best results, call enablePackrat() immediately
#            after importing pyparsing.
#         """
#         if not ParserElement._packratEnabled:
#             ParserElement._packratEnabled = True
#             ParserElement._parse = ParserElement._parseCache
#     enablePackrat = staticmethod(enablePackrat)

    def buildStartState(self, instring, baseDict=None,
            threadstop=DUMBTHREADSTOP):
        """
        Returns a ParsingState containing namestack, fullstack, instring and
        revInstring.
        The  namestack  contains strings with all named tokens.
        fullstack  is a StackedCopyDict
        instring  is the complete text to parse
        revInstring is the reserved instring
        """
        return ParsingState(instring, baseDict, threadstop)
#         return ([], StackedCopyDict(baseDict), instring, u"".join(reversed(
#                 instring)))

    def parseString(self, instring, parseAll=False, baseDict=None,
            threadstop=DUMBTHREADSTOP):
        """Execute the parse expression with the given string.
           This is the main interface to the client code, once the complete
           expression has been built.

           If you want the grammar to require that the entire input string be
           successfully parsed, then set parseAll to True (equivalent to ending
           the grammar with StringEnd()).

           Note: parseString implicitly calls expandtabs() on the input string,
           in order to report proper column numbers in parse actions.
           If the input string contains tabs and
           the grammar uses parse actions that use the loc argument to index into the
           string being parsed, you can ensure you have a consistent view of the input
           string by:
            - calling parseWithTabs on your grammar before calling parseString
              (see L{I{parseWithTabs}<parseWithTabs>})
            - define your parse action using the full (s,loc,toks) signature, and
              reference the input string using the parse action's s argument
            - explictly expand the tabs in your input string before calling
              parseString
        """
        ParserElement.resetCache()
        if not self.streamlined:
            self.streamline()
        for e in self.ignoreExprs:
            e.streamline()
        if not self.keepTabs:
            instring = instring.expandtabs()
        state = self.buildStartState(instring, baseDict, threadstop)
        loc, tokens = self._parse( instring, 0, state )
        if loc == -1:
            raise tokens

        if parseAll:
            loc  = self.preParse( instring, loc, state )  # TODO Added from original pyparsing, check if OK.
            testLoc, testTokens = StringEnd()._parse( instring, loc, state )
            if testLoc == -1:
                raise testTokens

        return tokens

#     def scanString( self, instring, maxMatches=_MAX_INT, baseDict=None ):
#         """Scan the input string for expression matches.  Each match will return the
#            matching tokens, start location, and end location.  May be called with optional
#            maxMatches argument, to clip scanning after 'n' matches are found.
# 
#            Note that the start and end locations are reported relative to the string
#            being parsed.  See L{I{parseString}<parseString>} for more information on parsing
#            strings with embedded tabs."""
#         if not self.streamlined:
#             self.streamline()
#         for e in self.ignoreExprs:
#             e.streamline()
# 
#         if not self.keepTabs:
#             instring = _ustr(instring).expandtabs()
#         instrlen = len(instring)
#         loc = 0
#         preparseFn = self.preParse
#         parseFn = self._parse
#         ParserElement.resetCache()
#         matches = 0
#         state = self.buildStartState(instring, baseDict)
# 
#         while loc <= instrlen and matches < maxMatches:
#             try:
#                 preloc = preparseFn( instring, loc, state )
#                 nextLoc,tokens = parseFn( instring, preloc, state, callPreParse=False )
#                 if loc == -1:
#                     loc = preloc+1
#                     continue
#             except ParseException:
#                 loc = preloc+1
#             else:
#                 matches += 1
#                 yield tokens, preloc, nextLoc
#                 loc = nextLoc
# 
#     def transformString( self, instring, baseDict=None ):
#         # TODO Check if it works
#         """Extension to scanString, to modify matching text with modified tokens that may
#            be returned from a parse action.  To use transformString, define a grammar and
#            attach a parse action to it that modifies the returned token list.
#            Invoking transformString() on a target string will then scan for matches,
#            and replace the matched text patterns according to the logic in the parse
#            action.  transformString() returns the resulting transformed string."""
#         out = []
#         lastE = 0
#         # force preservation of <TAB>s, to minimize unwanted transformation of string, and to
#         # keep string locs straight between transformString and scanString
#         self.keepTabs = True
#         for t,s,e in self.scanString( instring, baseDict=baseDict ):
#             out.append( instring[lastE:s] )
#             if t:
#                 if isinstance(t, SyntaxNode):
#                     out += t.asList()
#                 elif isinstance(t,list):
#                     out += t
#                 else:
#                     out.append(t)
#             lastE = e
#         out.append(instring[lastE:])
#         return "".join(map(_ustr,out))
# 
#     def searchString( self, instring, maxMatches=_MAX_INT, baseDict=None ):
#         """Another extension to scanString, simplifying the access to the tokens found
#            to match the given parse expression.  May be called with optional
#            maxMatches argument, to clip searching after 'n' matches are found.
#         """
#         return buildSyntaxNode(
#                 [ t for t,s,e in self.scanString( instring, maxMatches, baseDict ) ])

    def __add__(self, other ):
        """Implementation of + operator - returns And"""
        if isinstance( other, str ):
            other = Literal( other )
        if not isinstance( other, ParserElement ):
            warnings.warn("Cannot combine element of type %s with ParserElement" % type(other),
                    SyntaxWarning, stacklevel=2)
            return None
        return And( [ self, other ] )

    def __radd__(self, other ):
        """Implementation of + operator when left operand is not a ParserElement"""
        if isinstance( other, str ):
            other = Literal( other )
        if not isinstance( other, ParserElement ):
            warnings.warn("Cannot combine element of type %s with ParserElement" % type(other),
                    SyntaxWarning, stacklevel=2)
            return None
        return other + self

    def __sub__(self, other):
        """Implementation of - operator, returns And with error stop"""
        if isinstance( other, str ):
            other = Literal( other )
        if not isinstance( other, ParserElement ):
            warnings.warn("Cannot combine element of type %s with ParserElement" % type(other),
                    SyntaxWarning, stacklevel=2)
            return None
        return And( [ self, And._ErrorStop(), other ] )

    def __rsub__(self, other ):
        """Implementation of - operator when left operand is not a ParserElement"""
        if isinstance( other, str ):
            other = Literal( other )
        if not isinstance( other, ParserElement ):
            warnings.warn("Cannot combine element of type %s with ParserElement" % type(other),
                    SyntaxWarning, stacklevel=2)
            return None
        return other - self

    def __mul__(self,other):
        if isinstance(other,int):
            minElements, optElements = other,0
        elif isinstance(other,tuple):
            other = (other + (None, None))[:2]
            if other[0] is None:
                other = (0, other[1])
            if isinstance(other[0],int) and other[1] is None:
                if other[0] == 0:
                    return ZeroOrMore(self)
                if other[0] == 1:
                    return OneOrMore(self)
                else:
                    return self*other[0] + ZeroOrMore(self)
            elif isinstance(other[0],int) and isinstance(other[1],int):
                minElements, optElements = other
                optElements -= minElements
            else:
                raise TypeError("cannot multiply 'ParserElement' and ('%s','%s') objects", type(other[0]),type(other[1]))
        else:
            raise TypeError("cannot multiply 'ParserElement' and '%s' objects", type(other))

        if minElements < 0:
            raise ValueError("cannot multiply ParserElement by negative value")
        if optElements < 0:
            raise ValueError("second tuple value must be greater or equal to first tuple value")
        if minElements == optElements == 0:
            raise ValueError("cannot multiply ParserElement by 0 or (0,0)")

        if (optElements):
            def makeOptionalList(n):
                if n>1:
                    return Optional(self + makeOptionalList(n-1))
                else:
                    return Optional(self)
            if minElements:
                if minElements == 1:
                    ret = self + makeOptionalList(optElements)
                else:
                    ret = And([self]*minElements) + makeOptionalList(optElements)
            else:
                ret = makeOptionalList(optElements)
        else:
            if minElements == 1:
                ret = self
            else:
                ret = And([self]*minElements)
        return ret

    def __rmul__(self, other):
        return self.__mul__(other)

    def __or__(self, other ):
        """Implementation of | operator - returns MatchFirst"""
        if isinstance( other, str ):
            other = Literal( other )
        if not isinstance( other, ParserElement ):
            warnings.warn("Cannot combine element of type %s with ParserElement" % type(other),
                    SyntaxWarning, stacklevel=2)
            return None
        return MatchFirst( [ self, other ] )

    def __ror__(self, other ):
        """Implementation of | operator when left operand is not a ParserElement"""
        if isinstance( other, str ):
            other = Literal( other )
        if not isinstance( other, ParserElement ):
            warnings.warn("Cannot combine element of type %s with ParserElement" % type(other),
                    SyntaxWarning, stacklevel=2)
            return None
        return other | self

    def __xor__(self, other ):
        """Implementation of ^ operator - returns Or"""
        if isinstance( other, str ):
            other = Literal( other )
        if not isinstance( other, ParserElement ):
            warnings.warn("Cannot combine element of type %s with ParserElement" % type(other),
                    SyntaxWarning, stacklevel=2)
            return None
        return Or( [ self, other ] )

    def __rxor__(self, other ):
        """Implementation of ^ operator when left operand is not a ParserElement"""
        if isinstance( other, str ):
            other = Literal( other )
        if not isinstance( other, ParserElement ):
            warnings.warn("Cannot combine element of type %s with ParserElement" % type(other),
                    SyntaxWarning, stacklevel=2)
            return None
        return other ^ self

    def __and__(self, other ):
        """Implementation of & operator - returns Each"""
        if isinstance( other, str ):
            other = Literal( other )
        if not isinstance( other, ParserElement ):
            warnings.warn("Cannot combine element of type %s with ParserElement" % type(other),
                    SyntaxWarning, stacklevel=2)
            return None
        return Each( [ self, other ] )

    def __rand__(self, other ):
        """Implementation of & operator when left operand is not a ParserElement"""
        if isinstance( other, str ):
            other = Literal( other )
        if not isinstance( other, ParserElement ):
            warnings.warn("Cannot combine element of type %s with ParserElement" % type(other),
                    SyntaxWarning, stacklevel=2)
            return None
        return other & self

    def __invert__( self ):
        """Implementation of ~ operator - returns NotAny"""
        return NotAny( self )

    def __call__(self, name):
        """Shortcut for setResultsName, with listAllMatches=default::
             userdata = Word(alphas).setResultsName("name") + Word(nums+"-").setResultsName("socsecno")
           could be written as::
             userdata = Word(alphas)("name") + Word(nums+"-")("socsecno")
           """
        return self.setResultsName(name)

    def suppress( self ):
        """Suppresses the output of this ParserElement; useful to keep punctuation from
           cluttering up returned output.
        """
        return Suppress( self )

    def leaveWhitespace( self ):
        """Disables the skipping of whitespace before matching the characters in the
           ParserElement's defined pattern.  This is normally only used internally by
           the pyparsing module, but may be needed in some whitespace-sensitive grammars.
        """
        self.skipWhitespace = False
        return self

    def setWhitespaceChars( self, chars ):
        """Overrides the default whitespace chars
        """
        self.whiteChars = chars
        self.skipWhitespace = self.whiteChars != ""
        return self

    def parseWithTabs( self ):
        """Overrides default behavior to expand <TAB>s to spaces before parsing the input string.
           Must be called before parseString when the input grammar contains elements that
           match <TAB> characters."""
        self.keepTabs = True
        return self

    def ignore( self, other ):
        """Define expression to be ignored (e.g., comments) while doing pattern
           matching; may be called repeatedly, to define multiple comment or other
           ignorable patterns.
        """
        if isinstance( other, Suppress ):
            if other not in self.ignoreExprs:
                self.ignoreExprs.append( other )
        else:
            self.ignoreExprs.append( Suppress( other ) )
        return self

    def setDebugActions( self, startAction, successAction, exceptionAction ):
        """Enable display of debugging messages while doing pattern matching."""
        self.debugActions = (startAction or None,
                             successAction or None,
                             exceptionAction or None)
        self.debug = True
        return self

    def setDebug( self, flag=True ):
        """Enable display of debugging messages while doing pattern matching.
           Set flag to True to enable, False to disable."""
        if flag:
            self.setDebugActions(None, None, None)
            self.debug = True
        else:
            self.debug = False
        return self
        
    def getDebug(self):
        return self.debug

    def setDebugRecurs(self, flag=True, deepness=-1):
        self._setDebugRecursIntern(flag, set(), deepness)
        
    def _setDebugRecursIntern(self, flag, visited, deepness):
        idv = id(self)
        if (idv in visited) or (deepness == 0):
            return False
        visited.add(idv)

        self.setDebug(flag)
        return True

    def __str__( self ):
        return self.name

    def __repr__( self ):
        return _ustr(self)
        
    def getContainedElements(self):
        return []

    def streamline( self ):
        if not self.streamlined:
            self.streamlined = True
            self.strRepr = None
            
            for e in self.getContainedElements():
                e.streamline()

        return self

    def optimize(self, options=None):
        result = self.streamline()
        if options is None:
            options = ()
                
        return result._realOptimize(options)
        
    def _optimizeSub(self, options):
        pass
        
    def _optimizeSelf(self, options):
        # TODO: Add option for that
        if len(self.parseStartAction) == 0 and len(self.validateAction) == 0 \
                and len(self.parseAction) == 0:
            self._parse = self._parseNoAction

        return self
    
    def _realOptimize(self, options):
        if self.optimizing:
            return self
        self.optimizing = True  # Prevent infinite recursion
        self._optimizeSub(options)
        return self._optimizeSelf(options)


    def checkRecursion( self, parseElementList ):
        pass

    def validate( self, validateTrace=[] ):
        """Check defined expressions for valid structure, check for infinite recursive definitions."""
        self.checkRecursion( [] )

    def parseFile( self, file_or_filename, parseAll=False ):
        """Execute the parse expression on the given file or filename.
           If a filename is specified (instead of a file object),
           the entire file is opened, read, and closed before parsing.
        """
        try:
            file_contents = file_or_filename.read()
        except AttributeError:
            f = open(file_or_filename, "rb")
            file_contents = f.read()
            f.close()
        return self.parseString(file_contents, parseAll)

    def getException(self):
        return ParseException("",0,self.errmsg,self)

    def __getattr__(self,aname):
        if aname == "myException":
            self.myException = ret = self.getException();
            return ret;
        else:
            raise AttributeError("no such attribute " + aname)

    def __eq__(self,other):
        if isinstance(other, ParserElement):
            return self is other or self.__dict__ == other.__dict__
        elif isinstance(other, str):
            try:
                self.parseString(_ustr(other), parseAll=True)
                return True
            except ParseBaseException:
                return False
        else:
            return super(ParserElement,self)==other

    def __ne__(self,other):
        return not (self == other)

    def __hash__(self):
        return hash(id(self))

    def __req__(self,other):
        return self == other

    def __rne__(self,other):
        return not (self == other)


class Token(ParserElement):
    """Abstract ParserElement subclass, for defining atomic matching patterns."""
    def __init__( self ):
        super(Token,self).__init__()
        #self.myException = ParseException("",0,"",self)

    def setName(self, name):
        s = super(Token,self).setName(name)
        self.errmsg = "Expected " + self.name
        #s.myException.msg = self.errmsg
        return s


class Empty(Token, NecessaryRegexProvider):
    """An empty token, will always match."""
    def __init__( self ):
        super(Empty,self).__init__()
        self.name = "Empty"
        self.mayReturnEmpty = True
        self.mayIndexError = False

    def getRegex(self):
        return ""
        
    def isRegexComplete(self):
        return True


class NoMatch(Token):
    """A token that will never match."""
    def __init__( self ):
        super(NoMatch,self).__init__()
        self.name = "NoMatch"
        self.mayReturnEmpty = True
        self.mayIndexError = False
        self.errmsg = "Unmatchable token"
        #self.myException.msg = self.errmsg

    def parseImpl( self, instring, loc, state, doActions=True ):
        exc = self.myException
        exc.loc = loc
        exc.pstr = instring
        return -1, exc


class Literal(Token, NecessaryRegexProvider):
    """Token to exactly match a specified string."""
    def __init__( self, matchString ):
        super(Literal,self).__init__()
        self.match = matchString
        self.matchLen = len(matchString)
        try:
            self.firstMatchChar = matchString[0]
        except IndexError:
            warnings.warn("null string passed to Literal; use Empty() instead",
                            SyntaxWarning, stacklevel=2)
            self.__class__ = Empty
        self.name = '"%s"' % _ustr(self.match)
        self.errmsg = "Expected " + self.name
        self.mayReturnEmpty = False
        #self.myException.msg = self.errmsg
        self.mayIndexError = False

    def getRegex(self):
        try:
            return re.compile(re.escape(self.match))
        except:
            traceback.print_exc()
            return None

    def getRegexFlagsMask(self):
        # Here is a case where a NOT SET regex flag is important
        return re.IGNORECASE
        
    def isRegexComplete(self):
        return True

    # Performance tuning: this routine gets called a *lot*
    # if this is a single character match string  and the first character matches,
    # short-circuit as quickly as possible, and avoid calling startswith
    #~ @profile
    def parseImpl( self, instring, loc, state, doActions=True ):
        if instring.startswith(self.match, loc):
            return loc+self.matchLen, self.match

#         if (instring[loc] == self.firstMatchChar and
#             (self.matchLen==1 or instring.startswith(self.match,loc)) ):
#             return loc+self.matchLen, self.match
        #~ raise ParseException( instring, loc, self.errmsg )
        exc = self.myException
        exc.loc = loc
        exc.pstr = instring
        return -1, exc
        
    
        
_L = Literal


# TODO NecessaryRegexProvider
class Keyword(Token):
    """Token to exactly match a specified string as a keyword, that is, it must be
       immediately followed by a non-keyword character.  Compare with Literal::
         Literal("if") will match the leading 'if' in 'ifAndOnlyIf'.
         Keyword("if") will not; it will only match the leading 'if in 'if x=1', or 'if(y==2)'
       Accepts two optional constructor arguments in addition to the keyword string:
       identChars is a string of characters that would be valid identifier characters,
       defaulting to all alphanumerics + "_" and "$"; caseless allows case-insensitive
       matching, default is False.
    """
    DEFAULT_KEYWORD_CHARS = alphanums+"_$"

    def __init__( self, matchString, identChars=DEFAULT_KEYWORD_CHARS, caseless=False ):
        super(Keyword,self).__init__()
        self.match = matchString
        self.matchLen = len(matchString)
        try:
            self.firstMatchChar = matchString[0]
        except IndexError:
            warnings.warn("null string passed to Keyword; use Empty() instead",
                            SyntaxWarning, stacklevel=2)
        self.name = '"%s"' % self.match
        self.errmsg = "Expected " + self.name
        self.mayReturnEmpty = False
        #self.myException.msg = self.errmsg
        self.mayIndexError = False
        self.caseless = caseless
        if caseless:
            self.caselessmatch = matchString.upper()
            identChars = identChars.upper()
        self.identChars = _str2dict(identChars)

    def parseImpl( self, instring, loc, state, doActions=True ):
        if self.caseless:
            if ( (instring[ loc:loc+self.matchLen ].upper() == self.caselessmatch) and
                 (loc >= len(instring)-self.matchLen or instring[loc+self.matchLen].upper() not in self.identChars) and
                 (loc == 0 or instring[loc-1].upper() not in self.identChars) ):
                return loc+self.matchLen, self.match
        else:
            if (instring[loc] == self.firstMatchChar and
                (self.matchLen==1 or instring.startswith(self.match,loc)) and
                (loc >= len(instring)-self.matchLen or instring[loc+self.matchLen] not in self.identChars) and
                (loc == 0 or instring[loc-1] not in self.identChars) ):
                return loc+self.matchLen, self.match
        #~ raise ParseException( instring, loc, self.errmsg )
        exc = self.myException
        exc.loc = loc
        exc.pstr = instring
        return -1, exc

    def copy(self):
        c = super(Keyword,self).copy()
        c.identChars = Keyword.DEFAULT_KEYWORD_CHARS  # TODO Really?
        return c

    def setDefaultKeywordChars( chars ):
        """Overrides the default Keyword chars
        """
        Keyword.DEFAULT_KEYWORD_CHARS = chars
    setDefaultKeywordChars = staticmethod(setDefaultKeywordChars)

# TODO NecessaryRegexProvider
class CaselessLiteral(Literal):
    """Token to match a specified string, ignoring case of letters.
       Note: the matched results will always be in the case of the given
       match string, NOT the case of the input text.
    """
    def __init__( self, matchString ):
        super(CaselessLiteral,self).__init__( matchString.upper() )
        # Preserve the defining literal.
        self.returnString = matchString
        self.name = "'%s'" % self.returnString
        self.errmsg = "Expected " + self.name
        #self.myException.msg = self.errmsg

    def parseImpl( self, instring, loc, state, doActions=True ):
        if instring[ loc:loc+self.matchLen ].upper() == self.match:
            return loc+self.matchLen, self.returnString
        #~ raise ParseException( instring, loc, self.errmsg )
        exc = self.myException
        exc.loc = loc
        exc.pstr = instring
        return -1, exc

# TODO NecessaryRegexProvider
class CaselessKeyword(Keyword):
    def __init__( self, matchString, identChars=Keyword.DEFAULT_KEYWORD_CHARS ):
        super(CaselessKeyword,self).__init__( matchString, identChars, caseless=True )

    def parseImpl( self, instring, loc, state, doActions=True ):
        if ( (instring[ loc:loc+self.matchLen ].upper() == self.caselessmatch) and
             (loc >= len(instring)-self.matchLen or instring[loc+self.matchLen].upper() not in self.identChars) ):
            return loc+self.matchLen, self.match
        #~ raise ParseException( instring, loc, self.errmsg )
        exc = self.myException
        exc.loc = loc
        exc.pstr = instring
        return -1, exc

# TODO NecessaryRegexProvider
class Word(Token):
    """Token for matching words composed of allowed character sets.
       Defined with string containing all allowed initial characters,
       an optional string containing allowed body characters (if omitted,
       defaults to the initial character set), and an optional minimum,
       maximum, and/or exact length.  The default value for min is 1 (a
       minimum value < 1 is not valid); the default values for max and exact
       are 0, meaning no maximum or exact length restriction.
    """
    def __init__( self, initChars, bodyChars=None, min=1, max=0, exact=0, asKeyword=False ):
        super(Word,self).__init__()
        self.initCharsOrig = initChars
        self.initChars = _str2dict(initChars)
        if bodyChars :
            self.bodyCharsOrig = bodyChars
            self.bodyChars = _str2dict(bodyChars)
        else:
            self.bodyCharsOrig = initChars
            self.bodyChars = _str2dict(initChars)

        self.maxSpecified = max > 0

        if min < 1:
            raise ValueError("cannot specify a minimum length < 1; use Optional(Word()) if zero-length word is permitted")

        self.minLen = min

        if max > 0:
            self.maxLen = max
        else:
            self.maxLen = _MAX_INT

        if exact > 0:
            self.maxLen = exact
            self.minLen = exact

        self.name = _ustr(self)
        self.errmsg = "Expected " + self.name
        #self.myException.msg = self.errmsg
        self.mayIndexError = False
        self.asKeyword = asKeyword

        if ' ' not in self.initCharsOrig+self.bodyCharsOrig and (min==1 and max==0 and exact==0):
            if self.bodyCharsOrig == self.initCharsOrig:
                self.reString = "[%s]+" % _escapeRegexRangeChars(self.initCharsOrig)
            elif len(self.bodyCharsOrig) == 1:
                self.reString = "%s[%s]*" % \
                                      (re.escape(self.initCharsOrig),
                                      _escapeRegexRangeChars(self.bodyCharsOrig),)
            else:
                self.reString = "[%s][%s]*" % \
                                      (_escapeRegexRangeChars(self.initCharsOrig),
                                      _escapeRegexRangeChars(self.bodyCharsOrig),)
            if self.asKeyword:
                self.reString = r"\b"+self.reString+r"\b"
            try:
                self.re = re.compile( self.reString )
            except:
                self.re = None

    def parseImpl( self, instring, loc, state, doActions=True ):
        if self.re:
            result = self.re.match(instring,loc)
            if not result:
                exc = self.myException
                exc.loc = loc
                exc.pstr = instring
                return -1, exc

            loc = result.end()
            return loc,result.group()

        if not(instring[ loc ] in self.initChars):
            #~ raise ParseException( instring, loc, self.errmsg )
            exc = self.myException
            exc.loc = loc
            exc.pstr = instring
            return -1, exc
        start = loc
        loc += 1
        instrlen = len(instring)
        bodychars = self.bodyChars
        maxloc = start + self.maxLen
        maxloc = min( maxloc, instrlen )
        while loc < maxloc and instring[loc] in bodychars:
            loc += 1

        throwException = False
        if loc - start < self.minLen:
            throwException = True
        if self.maxSpecified and loc < instrlen and instring[loc] in bodychars:
            throwException = True
        if self.asKeyword:
            if (start>0 and instring[start-1] in bodychars) or (loc<instrlen and instring[loc] in bodychars):
                throwException = True

        if throwException:
            #~ raise ParseException( instring, loc, self.errmsg )
            exc = self.myException
            exc.loc = loc
            exc.pstr = instring
            return -1, exc

        return loc, instring[start:loc]

    def __str__( self ):
        try:
            return super(Word,self).__str__()
        except:
            pass


        if self.strRepr is None:

            def charsAsStr(s):
                if len(s)>4:
                    return s[:4]+"..."
                else:
                    return s

            if ( self.initCharsOrig != self.bodyCharsOrig ):
                self.strRepr = "W:(%s,%s)" % ( charsAsStr(self.initCharsOrig), charsAsStr(self.bodyCharsOrig) )
            else:
                self.strRepr = "W:(%s)" % charsAsStr(self.initCharsOrig)

        return self.strRepr


class Regex(Token, NecessaryRegexProvider):
    """Token for matching strings that match a given regular expression.
       Defined with string specifying the regular expression in a form recognized by the inbuilt Python re module.
    """
    def __init__( self, pattern, flags=0, flagsMask=None):
        """The parameters pattern and flags are passed to the re.compile() function as-is. See the Python re module for an explanation of the acceptable patterns and flags."""
        super(Regex,self).__init__()

        if len(pattern) == 0:
            warnings.warn("null string passed to Regex; use Empty() instead",
                    SyntaxWarning, stacklevel=2)

        self.pattern = pattern
        self.flags = flags
        if flagsMask is None:
            self.flagsMask = flags
        else:
            self.flagsMask = flagsMask

        try:
            self.re = re.compile(self.pattern, self.flags)
            self.reString = self.pattern
        except sre_constants.error:
            warnings.warn("invalid pattern (%s) passed to Regex" % pattern,
                SyntaxWarning, stacklevel=2)
            raise

        self.name = _ustr(self)
        self.errmsg = "Expected " + self.name
        #self.myException.msg = self.errmsg
        self.mayIndexError = False
        self.mayReturnEmpty = True
        
    def getRegex(self):
        return self.re
    
    def getPattern(self):
        if self.re is None:
            return None
        
        return self.re.pattern
        
    def getRegexFlagsMask(self):
        return self.flagsMask
        
    def isRegexComplete(self):
        return True

    def parseImpl( self, instring, loc, state, doActions=True ):
        result = self.re.match(instring,loc)
        if not result:
            exc = self.myException
            exc.loc = loc
            exc.pstr = instring
            return -1, exc

#         startLoc = loc
        loc = result.end()
#         d = result.groupdict()
        ret = buildSyntaxNode(result.group())
#         ret.groupDict = d

#         if d:
#             for k in d:
#                 ret[k] = d[k]
        return loc,ret

    def __str__( self ):
        try:
            return super(Regex,self).__str__()
        except:
            pass

        if self.strRepr is None:
            self.strRepr = "Re:(%s)" % repr(self.pattern)

        return self.strRepr


class QuotedString(Token, NecessaryRegexProvider):
    """Token for matching strings that are delimited by quoting characters.
    """
    def __init__( self, quoteChar, escChar=None, escQuote=None, multiline=False, unquoteResults=True, endQuoteChar=None):
        """
           Defined with the following parameters:
            - quoteChar - string of one or more characters defining the quote delimiting string
            - escChar - character to escape quotes, typically backslash (default=None)
            - escQuote - special quote sequence to escape an embedded quote string (such as SQL's "" to escape an embedded ") (default=None)
            - multiline - boolean indicating whether quotes can span multiple lines (default=False)
            - unquoteResults - boolean indicating whether the matched text should be unquoted (default=True)
            - endQuoteChar - string of one or more characters defining the end of the quote delimited string (default=None => same as quoteChar)
        """
        super(QuotedString,self).__init__()

        # remove white space from quote chars - wont work anyway
        quoteChar = quoteChar.strip()
        if len(quoteChar) == 0:
            warnings.warn("quoteChar cannot be the empty string",SyntaxWarning,stacklevel=2)
            raise SyntaxError()

        if endQuoteChar is None:
            endQuoteChar = quoteChar
        else:
            endQuoteChar = endQuoteChar.strip()
            if len(endQuoteChar) == 0:
                warnings.warn("endQuoteChar cannot be the empty string",SyntaxWarning,stacklevel=2)
                raise SyntaxError()

        self.quoteChar = quoteChar
        self.quoteCharLen = len(quoteChar)
        self.firstQuoteChar = quoteChar[0]
        self.endQuoteChar = endQuoteChar
        self.endQuoteCharLen = len(endQuoteChar)
        self.escChar = escChar
        self.escQuote = escQuote
        self.unquoteResults = unquoteResults

        if multiline:
            self.flags = re.MULTILINE | re.DOTALL
            self.pattern = r'%s(?:[^%s%s]' % \
                ( re.escape(self.quoteChar),
                  _escapeRegexRangeChars(self.endQuoteChar[0]),
                  (escChar is not None and _escapeRegexRangeChars(escChar) or '') )
        else:
            self.flags = re.DOTALL
            self.pattern = r'%s(?:[^%s\n\r%s]' % \
                ( re.escape(self.quoteChar),
                  _escapeRegexRangeChars(self.endQuoteChar[0]),
                  (escChar is not None and _escapeRegexRangeChars(escChar) or '') )
        if len(self.endQuoteChar) > 1:
            self.pattern += (
                '|(?:' + ')|(?:'.join(["%s[^%s]" % (re.escape(self.endQuoteChar[:i]),
                                               _escapeRegexRangeChars(self.endQuoteChar[i]))
                                    for i in range(len(self.endQuoteChar)-1,0,-1)]) + ')'
                )
        if escQuote:
            self.pattern += (r'|(?:%s)' % re.escape(escQuote))
        if escChar:
            self.pattern += (r'|(?:%s.)' % re.escape(escChar))
            self.escCharReplacePattern = re.escape(self.escChar)+"(.)"
        self.pattern += (r')*%s' % re.escape(self.endQuoteChar))

        try:
            self.re = re.compile(self.pattern, self.flags)
            self.reString = self.pattern
        except sre_constants.error:
            warnings.warn("invalid pattern (%s) passed to Regex" % self.pattern,
                SyntaxWarning, stacklevel=2)
            raise

        self.name = _ustr(self)
        self.errmsg = "Expected " + self.name
        #self.myException.msg = self.errmsg
        self.mayIndexError = False
        self.mayReturnEmpty = True

    def getRegex(self):
        return self.re
        
    def getRegexFlagsMask(self):
        if self.re is None:
            return 0
        else:
            return self.re.flags
            
    def isRegexComplete(self):
        return True

    def parseImpl( self, instring, loc, state, doActions=True ):
        result = instring[loc] == self.firstQuoteChar and self.re.match(instring,loc) or None
        if not result:
            exc = self.myException
            exc.loc = loc
            exc.pstr = instring
            return -1, exc

        loc = result.end()
        ret = result.group()

        if self.unquoteResults:

            # strip off quotes
            ret = ret[self.quoteCharLen:-self.endQuoteCharLen]

            if isinstance(ret,str):
                # replace escaped characters
                if self.escChar:
                    ret = re.sub(self.escCharReplacePattern,"\g<1>",ret)

                # replace escaped quotes
                if self.escQuote:
                    ret = ret.replace(self.escQuote, self.endQuoteChar)

        return loc, ret

    def __str__( self ):
        try:
            return super(QuotedString,self).__str__()
        except:
            pass

        if self.strRepr is None:
            self.strRepr = "quoted string, starting with %s ending with %s" % (self.quoteChar, self.endQuoteChar)

        return self.strRepr


# TODO NecessaryRegexProvider
class CharsNotIn(Token):
    """Token for matching words composed of characters *not* in a given set.
       Defined with string containing all disallowed characters, and an optional
       minimum, maximum, and/or exact length.  The default value for min is 1 (a
       minimum value < 1 is not valid); the default values for max and exact
       are 0, meaning no maximum or exact length restriction.
    """
    def __init__( self, notChars, min=1, max=0, exact=0 ):
        super(CharsNotIn,self).__init__()
        self.skipWhitespace = False
        self.notChars = notChars

        if min < 1:
            raise ValueError("cannot specify a minimum length < 1; use Optional(CharsNotIn()) if zero-length char group is permitted")

        self.minLen = min

        if max > 0:
            self.maxLen = max
        else:
            self.maxLen = _MAX_INT

        if exact > 0:
            self.maxLen = exact
            self.minLen = exact

        self.name = _ustr(self)
        self.errmsg = "Expected " + self.name
        self.mayReturnEmpty = ( self.minLen == 0 )
        #self.myException.msg = self.errmsg
        self.mayIndexError = False

    def parseImpl( self, instring, loc, state, doActions=True ):
        if instring[loc] in self.notChars:
            #~ raise ParseException( instring, loc, self.errmsg )
            exc = self.myException
            exc.loc = loc
            exc.pstr = instring
            return -1, exc

        start = loc
        loc += 1
        notchars = self.notChars
        maxlen = min( start+self.maxLen, len(instring) )
        while loc < maxlen and \
              (instring[loc] not in notchars):
            loc += 1

        if loc - start < self.minLen:
            #~ raise ParseException( instring, loc, self.errmsg )
            exc = self.myException
            exc.loc = loc
            exc.pstr = instring
            return -1, exc

        return loc, instring[start:loc]

    def __str__( self ):
        try:
            return super(CharsNotIn, self).__str__()
        except:
            pass

        if self.strRepr is None:
            if len(self.notChars) > 4:
                self.strRepr = "!W:(%s...)" % self.notChars[:4]
            else:
                self.strRepr = "!W:(%s)" % self.notChars

        return self.strRepr


# TODO NecessaryRegexProvider
class White(Token):
    """Special matching class for matching whitespace.  Normally, whitespace is ignored
       by pyparsing grammars.  This class is included when some whitespace structures
       are significant.  Define with a string containing the whitespace characters to be
       matched; default is " \\t\\r\\n".  Also takes optional min, max, and exact arguments,
       as defined for the Word class."""
    whiteStrs = {
        " " : "<SPC>",
        "\t": "<TAB>",
        "\n": "<LF>",
        "\r": "<CR>",
        "\f": "<FF>",
        }
    def __init__(self, ws=" \t\r\n", min=1, max=0, exact=0):
        super(White,self).__init__()
        self.matchWhite = ws
        self.setWhitespaceChars( "".join([c for c in self.whiteChars if c not in self.matchWhite]) )
        #~ self.leaveWhitespace()
        self.name = ("".join([White.whiteStrs[c] for c in self.matchWhite]))
        self.mayReturnEmpty = True
        self.errmsg = "Expected " + self.name
        #self.myException.msg = self.errmsg

        self.minLen = min

        if max > 0:
            self.maxLen = max
        else:
            self.maxLen = _MAX_INT

        if exact > 0:
            self.maxLen = exact
            self.minLen = exact

    def parseImpl( self, instring, loc, state, doActions=True ):
        if not(instring[ loc ] in self.matchWhite):
            #~ raise ParseException( instring, loc, self.errmsg )
            exc = self.myException
            exc.loc = loc
            exc.pstr = instring
            return -1, exc
        start = loc
        loc += 1
        maxloc = start + self.maxLen
        maxloc = min( maxloc, len(instring) )
        while loc < maxloc and instring[loc] in self.matchWhite:
            loc += 1

        if loc - start < self.minLen:
            #~ raise ParseException( instring, loc, self.errmsg )
            exc = self.myException
            exc.loc = loc
            exc.pstr = instring
            return -1, exc

        return loc, instring[start:loc]


class _PositionToken(Token):
    def __init__( self ):
        super(_PositionToken,self).__init__()
        self.name=self.__class__.__name__
        self.mayReturnEmpty = True
        self.mayIndexError = False

class GoToColumn(_PositionToken):
    """Token to advance to a specific column of input text; useful for tabular report scraping."""
    def __init__( self, colno ):
        super(GoToColumn,self).__init__()
        self.col = colno

    def preParse( self, instring, loc, state ):
        if col(loc,instring) != self.col:
            instrlen = len(instring)
            if self.ignoreExprs:
                loc = self._skipIgnorables( instring, loc, state )
            while loc < instrlen and instring[loc].isspace() and col( loc, instring ) != self.col :
                loc += 1
        return loc

    def parseImpl( self, instring, loc, state, doActions=True ):
        thiscol = col( loc, instring )
        if thiscol > self.col:
            return -1, ParseException( instring, loc, "Text not in expected column", self )
        newloc = loc + self.col - thiscol
        ret = instring[ loc: newloc ]
        return newloc, ret


# TODO NecessaryRegexProvider
class LineStart(_PositionToken):
    """Matches if current position is at the beginning of a line within the parse string"""
    def __init__( self ):
        super(LineStart,self).__init__()
        self.setWhitespaceChars( ParserElement.DEFAULT_WHITE_CHARS.replace("\n","") )
        self.errmsg = "Expected start of line"
        #self.myException.msg = self.errmsg

    def preParse( self, instring, loc, state ):
        preloc = super(LineStart,self).preParse(instring, loc, state)
        if instring[preloc] == "\n":
            loc += 1
        return loc

    def parseImpl( self, instring, loc, state, doActions=True ):
        if not( loc==0 or
            (loc == self.preParse( instring, 0, state )) or
            (instring[loc-1] == "\n") ): #col(loc, instring) != 1:
            #~ raise ParseException( instring, loc, "Expected start of line" )
            exc = self.myException
            exc.loc = loc
            exc.pstr = instring
            return -1, exc
        return loc, []


# TODO NecessaryRegexProvider
class LineEnd(_PositionToken):
    """Matches if current position is at the end of a line within the parse string"""
    def __init__( self ):
        super(LineEnd,self).__init__()
        self.setWhitespaceChars( ParserElement.DEFAULT_WHITE_CHARS.replace("\n","") )
        self.errmsg = "Expected end of line"
        #self.myException.msg = self.errmsg

    def parseImpl( self, instring, loc, state, doActions=True ):
        if loc<len(instring):
            if instring[loc] == "\n":
                return loc+1, "\n"
            else:
                #~ raise ParseException( instring, loc, "Expected end of line" )
                exc = self.myException
                exc.loc = loc
                exc.pstr = instring
                return -1, exc
        elif loc == len(instring):
            return loc+1, []
        else:
            exc = self.myException
            exc.loc = loc
            exc.pstr = instring
            return -1, exc

class StringStart(_PositionToken, NecessaryRegexProvider):
#     REGEX = re.compile(ur"(?<!.)", re.DOTALL | re.UNICODE | re.MULTILINE)
    REGEX = re.compile(r"(?<!.)", re.DOTALL)

    """Matches if current position is at the beginning of the parse string"""
    def __init__( self ):
        super(StringStart,self).__init__()
        self.errmsg = "Expected start of text"
        #self.myException.msg = self.errmsg

    def parseImpl( self, instring, loc, state, doActions=True ):
        if loc != 0:
            # see if entire string up to here is just whitespace and ignoreables
            if loc != self.preParse( instring, 0, state ):
                #~ raise ParseException( instring, loc, "Expected start of text" )
                exc = self.myException
                exc.loc = loc
                exc.pstr = instring
                return -1, exc
        return loc, []
    
    def getRegex(self):
        return StringStart.REGEX
        
    def getRegexFlagsMask(self):
        return StringStart.REGEX.flags

    def isRegexComplete(self):
        return True


class StringEnd(_PositionToken, NecessaryRegexProvider):
#     REGEX = re.compile(ur"(?!.)", re.DOTALL | re.UNICODE | re.MULTILINE)
    REGEX = re.compile(r"(?!.)", re.DOTALL )

    """Matches if current position is at the end of the parse string"""
    def __init__( self ):
        super(StringEnd,self).__init__()
        self.errmsg = "Expected end of text"
        #self.myException.msg = self.errmsg

    def parseImpl( self, instring, loc, state, doActions=True ):
        if loc < len(instring):
            #~ raise ParseException( instring, loc, "Expected end of text" )
            exc = self.myException
            exc.loc = loc
            exc.pstr = instring
            return -1, exc
        elif loc == len(instring):
            return loc+1, []
        elif loc > len(instring):
            return loc, []
        else:
            exc = self.myException
            exc.loc = loc
            exc.pstr = instring
            return -1, exc

    def getRegex(self):
        return StringEnd.REGEX

    def getRegexFlagsMask(self):
        return StringEnd.REGEX.flags

    def isRegexComplete(self):
        return True


# TODO NecessaryRegexProvider
class WordStart(_PositionToken):
    """Matches if the current position is at the beginning of a Word, and
       is not preceded by any character in a given set of wordChars
       (default=printables). To emulate the \b behavior of regular expressions,
       use WordStart(alphanums). WordStart will also match at the beginning of
       the string being parsed, or at the beginning of a line.
    """
    def __init__(self, wordChars = printables):
        super(WordStart,self).__init__()
        self.wordChars = _str2dict(wordChars)
        self.errmsg = "Not at the start of a word"

    def parseImpl(self, instring, loc, state, doActions=True ):
        if loc != 0:
            if (instring[loc-1] in self.wordChars or
                instring[loc] not in self.wordChars):
                exc = self.myException
                exc.loc = loc
                exc.pstr = instring
                return -1, exc
        return loc, []


# TODO NecessaryRegexProvider
class WordEnd(_PositionToken):
    """Matches if the current position is at the end of a Word, and
       is not followed by any character in a given set of wordChars
       (default=printables). To emulate the \b behavior of regular expressions,
       use WordEnd(alphanums). WordEnd will also match at the end of
       the string being parsed, or at the end of a line.
    """
    def __init__(self, wordChars = printables):
        super(WordEnd,self).__init__()
        self.wordChars = _str2dict(wordChars)
        self.skipWhitespace = False
        self.errmsg = "Not at the end of a word"

    def parseImpl(self, instring, loc, state, doActions=True ):
        instrlen = len(instring)
        if instrlen>0 and loc<instrlen:
            if (instring[loc] in self.wordChars or
                instring[loc-1] not in self.wordChars):
                #~ raise ParseException( instring, loc, "Expected end of word" )
                exc = self.myException
                exc.loc = loc
                exc.pstr = instring
                return -1, exc
        return loc, []



class ParseExpression(ParserElement):
    """Abstract subclass of ParserElement, for combining and post-processing parsed tokens."""
    def __init__( self, exprs ):
        super(ParseExpression,self).__init__()
        if isinstance( exprs, list ):
            self.exprs = exprs
        elif isinstance( exprs, str ):
            self.exprs = [ Literal( exprs ) ]
        else:
            try:   # TODO Added
                self.exprs = list( exprs )  #  by
            except TypeError:   #  original. Check if OK.
                self.exprs = [ exprs ]
        self.callPreparse = False

    def __getitem__( self, i ):
        return self.exprs[i]

    def getNamedElementNeedsPacking(self):
        return True

    def append( self, other ):
        self.exprs.append( other )
        self.strRepr = None
        return self

    def leaveWhitespace( self ):
        """Extends leaveWhitespace defined in base class, and also invokes leaveWhitespace on
           all contained expressions."""
        self.skipWhitespace = False
        self.exprs = [ e.copy() for e in self.exprs ]
        for e in self.exprs:
            e.leaveWhitespace()
        return self

    def ignore( self, other ):
        if isinstance( other, Suppress ):
            if other not in self.ignoreExprs:
                super( ParseExpression, self).ignore( other )
                for e in self.exprs:
                    e.ignore( self.ignoreExprs[-1] )
        else:
            super( ParseExpression, self).ignore( other )
            for e in self.exprs:
                e.ignore( self.ignoreExprs[-1] )
        return self

    def __str__( self ):
        try:
            return super(ParseExpression,self).__str__()
        except:
            pass

        if self.strRepr is None:
            self.strRepr = "%s:(%s)" % ( self.__class__.__name__, _ustr(self.exprs) )
        return self.strRepr

    def getContainedElements(self):
        return self.exprs

    def streamline( self ):
        super(ParseExpression,self).streamline()

#         for e in self.exprs:
#             e.streamline()

        # collapse nested And's of the form And( And( And( a,b), c), d) to And( a,b,c,d )
        # but only if there are no parse actions or resultsNames on the nested And's
        # (likewise for Or's and MatchFirst's)
        
        newExprs = []
        for other in self.exprs:
            if ( isinstance( other, self.__class__ ) and
                  not (other.parseStartAction) and
                  not (other.validateAction) and
                  not (other.parseAction) and
                  other.resultsName is None and
                  not other.debug ):
                newExprs += other.exprs[:]
                self.strRepr = None
                self.mayReturnEmpty |= other.mayReturnEmpty
                self.mayIndexError  |= other.mayIndexError
            else:
                newExprs.append(other)
            
        self.exprs = newExprs


#         if ( len(self.exprs) == 2 ):
#             other = self.exprs[0]
#             if ( isinstance( other, self.__class__ ) and
#                   not (other.parseStartAction) and
#                   not (other.validateAction) and
#                   not (other.parseAction) and
#                   other.resultsName is None and
#                   not other.debug ):
#                 self.exprs = other.exprs[:] + [ self.exprs[1] ]
#                 self.strRepr = None
#                 self.mayReturnEmpty |= other.mayReturnEmpty
#                 self.mayIndexError  |= other.mayIndexError
# 
#             other = self.exprs[-1]
#             if ( isinstance( other, self.__class__ ) and
#                   not (other.parseStartAction) and
#                   not (other.validateAction) and
#                   not(other.parseAction) and
#                   other.resultsName is None and
#                   not other.debug ):
#                 self.exprs = self.exprs[:-1] + other.exprs[:]
#                 self.strRepr = None
#                 self.mayReturnEmpty |= other.mayReturnEmpty
#                 self.mayIndexError  |= other.mayIndexError

        return self

    def _optimizeSub(self, options):
        super(ParseExpression,self)._optimizeSub(options)
        self.exprs = [e._realOptimize(options) for e in self.exprs]

    def _setDebugRecursIntern(self, flag, visited, deepness):
        if super(ParseExpression,self)._setDebugRecursIntern(flag, visited,
                deepness):
            for e in self.exprs:
                e._setDebugRecursIntern(flag, visited,
                        deepness - 1 if deepness > 0 else -1)
            return True
        return False

    def setResultsName( self, name, listAllMatches=False ):
        ret = super(ParseExpression,self).setResultsName(name,listAllMatches)
        return ret

    def validate( self, validateTrace=[] ):
        tmp = validateTrace[:]+[self]
        for e in self.exprs:
            e.validate(tmp)
        self.checkRecursion( [] )



class And(ParseExpression, NecessaryRegexProvider):
    """Requires all given ParseExpressions to be found in the given order.
       Expressions may be separated by whitespace.
       May be constructed using the '+' operator.
    """

    class _ErrorStop(Empty):
        def __init__(self, *args, **kwargs):
            super(Empty,self).__init__(*args, **kwargs)
            self.leaveWhitespace()

    def __init__( self, exprs ):
        super(And,self).__init__(exprs)
        self.mayReturnEmpty = True
        for e in self.exprs:
            if not e.mayReturnEmpty:
                self.mayReturnEmpty = False
                break
        self.setWhitespaceChars( exprs[0].whiteChars )
        self.skipWhitespace = exprs[0].skipWhitespace
        self.callPreparse = True
        self.reFlagsMask = 0
        self.reComplete = False


    def getRegex(self):
        if self.buildingRegex:
            return None
        
        self.buildingRegex = True
        try:
            self.reFlagsMask = 0
            self.reComplete = False
    
            result = []
            flags = 0
            flagsMask = 0
            complete = True
    
            for e in self.exprs:
                if not isinstance(e, NecessaryRegexProvider):
                    complete = False
                    break
                    
                nextRe = e.getRegex()
                if nextRe is None:
                    complete = False
                    break
                
                nextFlags, nextFlagsMask = combineRegexFlags(flags, flagsMask,
                    nextRe.flags, e.getRegexFlagsMask())
                
                if nextFlags is None:
                    complete = False
                    break
                
                result.append("(?:" + nextRe.pattern + ")")
                flags = nextFlags
                flagsMask = nextFlagsMask
                complete = complete and e.isRegexComplete()
                if not complete:
                    # If the current regex isn't complete, further parts can't
                    # be appended to the and-regex
                    break
                
            if len(result) is 0:
                return None
            
            self.reFlagsMask = flagsMask
            self.reComplete = complete
            return re.compile("".join(result), flags)
        finally:
            self.buildingRegex = False


    def getRegexFlagsMask(self):
        return self.reFlagsMask

    def isRegexComplete(self):
        return self.reComplete


    def parseImpl( self, instring, loc, state, doActions=True ):
        # pass False as last arg to _parse for first element, since we already
        # pre-parsed the string as part of our And pre-parsing
#         loc, resultlist = self.exprs[0]._parse( instring, loc, state, doActions, callPreParse=False )
#         errorStop = False

        resultlist = []
        for e in self.exprs:   # [1:]:
#             if einstance(e, And._ErrorStop):
#                 errorStop = True
#                 continue
#             if errorStop:
#                 try:
#                     loc, exprtokens = e._parse( instring, loc, state, doActions )
#                 except ParseBaseException, pe:
#                     raise ParseSyntaxException(pe)
#                 except IndexError, ie:
#                     raise ParseSyntaxException( ParseException(instring, len(instring), self.errmsg, self) )
#             else:
            loc, exprtokens = e._parse( instring, loc, state, doActions )
            if loc == -1:
                return loc, exprtokens

            if exprtokens: #  or exprtokens.keys():
                resultlist += exprtokens
                
        return loc, resultlist

    def __iadd__(self, other ):
        if isinstance( other, str ):
            other = Literal( other )
        return self.append( other ) #And( [ self, other ] )


    def checkRecursion( self, parseElementList ):
        subRecCheckList = parseElementList[:] + [ self ]
        for e in self.exprs:
            e.checkRecursion( subRecCheckList )
            if not e.mayReturnEmpty:
                break

    def __str__( self ):
        if hasattr(self,"name"):
            return self.name

        if self.strRepr is None:
            self.strRepr = "{" + " ".join( [ _ustr(e) for e in self.exprs ] ) + "}"

        return self.strRepr


class Or(ParseExpression):
    """Requires that at least one ParseExpression is found.
       If two expressions match, the expression that matches the longest string will be used.
       May be constructed using the '^' operator.
    """
    def __init__( self, exprs ):
        super(Or,self).__init__(exprs)
        self.mayReturnEmpty = False
        for e in self.exprs:
            if e.mayReturnEmpty:
                self.mayReturnEmpty = True
                break

    def parseImpl( self, instring, loc, state, doActions=True ):
        maxExcLoc = -1
        maxMatchLoc = -1
        maxException = None
        for e in self.exprs:
#             try:
            loc2, tmpTokens = e.tryParse( instring, loc, state )
            if loc2 == -1:
                err = tmpTokens
                if isinstance(err, ParseException) and err.loc > maxExcLoc:
                    maxException = err
                    maxExcLoc = err.loc
                elif isinstance(err, IndexError) and len(instring) > maxExcLoc:
                    maxException = ParseException(instring,len(instring),e.errmsg,self)
                    maxExcLoc = len(instring)
            else:
                if loc2 > maxMatchLoc:
                    maxMatchLoc = loc2
                    maxMatchExp = e

#             except ParseException, err:
#                 if err.loc > maxExcLoc:
#                     maxException = err
#                     maxExcLoc = err.loc
#             except IndexError:
#                 if len(instring) > maxExcLoc:
#                     maxException = ParseException(instring,len(instring),e.errmsg,self)
#                     maxExcLoc = len(instring)
#             else:
#                 if loc2 > maxMatchLoc:
#                     maxMatchLoc = loc2
#                     maxMatchExp = e

        if maxMatchLoc < 0:
            if maxException is not None:
                return -1, maxException
            else:
                return -1, ParseException(instring, loc, "no defined alternatives to match", self)

        return maxMatchExp._parse( instring, loc, state, doActions )

    def __ixor__(self, other ):
        if isinstance( other, str ):
            other = Literal( other )
        return self.append( other ) #Or( [ self, other ] )

    def __str__( self ):
        if hasattr(self,"name"):
            return self.name

        if self.strRepr is None:
            self.strRepr = "{" + " ^ ".join( [ _ustr(e) for e in self.exprs ] ) + "}"

        return self.strRepr

    def checkRecursion( self, parseElementList ):
        subRecCheckList = parseElementList[:] + [ self ]
        for e in self.exprs:
            e.checkRecursion( subRecCheckList )


class MatchFirst(ParseExpression, NecessaryRegexProvider):
    """Requires that at least one ParseExpression is found.
       If two expressions match, the first one listed is the one that will match.
       May be constructed using the '|' operator.
    """
    def __init__( self, exprs ):
        super(MatchFirst,self).__init__(exprs)
        if exprs:
            self.mayReturnEmpty = False
            for e in self.exprs:
                if e.mayReturnEmpty:
                    self.mayReturnEmpty = True
                    break
        else:
            self.mayReturnEmpty = True
            
        self.regexCombiner = None

    def parseImpl( self, instring, loc, state, doActions=True ):
        maxExcLoc = -1
        maxException = None
        # TODO Use regex combiner here
        if self.regexCombiner is None:
            for e in self.exprs:
                try:
                    tmpLoc, tokens = e._parse( instring, loc, state, doActions )
                    if tmpLoc != -1:
                        return tmpLoc, tokens
                    
                    err = tokens
                    if isinstance(tokens, ParseException) and err.loc > maxExcLoc:
                        maxException = err
                        maxExcLoc = err.loc
                    elif isinstance(tokens, IndexError) and len(instring) > maxExcLoc:
                        maxException = ParseException(instring,len(instring),e.errmsg,self)
                        maxExcLoc = len(instring)
                    continue
                    
                except ParseException as err:
                    if err.loc > maxExcLoc:
                        maxException = err
                        maxExcLoc = err.loc
                    continue
                except IndexError:
                    if len(instring) > maxExcLoc:
                        maxException = ParseException(instring,len(instring),e.errmsg,self)
                        maxExcLoc = len(instring)
                    continue
    
            # only got here if no expression matched, raise exception for match that made it the furthest
            else:
                if maxException is not None:
                    return -1, maxException
                else:
                    return -1, ParseException(instring, loc, "no defined alternatives to match", self)
        else:
            loc, styles = self.regexCombiner.findAll(instring, loc)
            
            if len(styles) == 0:
                return -1, ParseException(instring, loc, "no defined alternatives to match", self)

            for st in styles:
                try:
                    tmpLoc, tokens = self.exprs[st]._parse(instring, loc, state, doActions)
                    if tmpLoc != -1:
                        return tmpLoc, tokens
                    
                    err = tokens
                    if isinstance(tokens, ParseException) and err.loc > maxExcLoc:
                        maxException = err
                        maxExcLoc = err.loc
                    elif isinstance(tokens, IndexError) and len(instring) > maxExcLoc:
                        maxException = ParseException(instring,len(instring),e.errmsg,self)
                        maxExcLoc = len(instring)
                    continue
                        
                except ParseException as err:
                    if err.loc > maxExcLoc:
                        maxException = err
                        maxExcLoc = err.loc
                    continue
                except IndexError:
                    if len(instring) > maxExcLoc:
                        maxException = ParseException(instring,len(instring),e.errmsg,self)
                        maxExcLoc = len(instring)
                    continue
            # only got here if no expression matched, raise exception for match that made it the furthest
            else:
                if maxException is not None:
                    return -1, maxException
                else:
                    return -1, ParseException(instring, loc, "no defined alternatives to match", self)


    def getRegexCombiner(self):
        return self.regexCombiner

    def getRegex(self):
        if self.regexCombiner is not None:
            return re.compile(self.regexCombiner.getCleanPattern(),
                    self.regexCombiner.getFlags())


    def getRegexFlagsMask(self):
        if self.regexCombiner is None:
            return 0

        return self.regexCombiner.getFlagsMask()


    def __ior__(self, other ):
        if isinstance( other, str ):
            other = Literal( other )
        return self.append( other ) #MatchFirst( [ self, other ] )

    def __str__( self ):
        if hasattr(self,"name"):
            return self.name

        if self.strRepr is None:
            self.strRepr = "{" + " | ".join( [ _ustr(e) for e in self.exprs ] ) + "}"

        return self.strRepr

    def _optimizeSub(self, options):
        super(MatchFirst, self)._optimizeSub(options)
        if self.regexCombiner is not None or "regexcombine" not in options:
            return

        combiner = RegexCombiner(self.exprs, RegexCombiner.REMODE_MATCH_ALL)
        if combiner.combine():
            self.regexCombiner = combiner
        
#         print "--optimize match", repr((self, self.regexCombiner))

    def checkRecursion( self, parseElementList ):
        subRecCheckList = parseElementList[:] + [ self ]
        for e in self.exprs:
            e.checkRecursion( subRecCheckList )


class Choice(ParseExpression, NecessaryRegexProvider):
    """Calls a special parseStartAction which returns the actual parse element
    to match. For optimization the possible choices must be given as
    parameter.
    """
    def __init__( self, exprs, parseChoiceAction ):
        super(Choice,self).__init__(exprs)
        if exprs:
            self.mayReturnEmpty = False
            for e in self.exprs:
                if e.mayReturnEmpty:
                    self.mayReturnEmpty = True
                    break
        else:
            self.mayReturnEmpty = True
            
        self.parseChoiceAction = parseChoiceAction
        self.regexCombiner = None

    def setParseChoiceAction(self, pca):
        self.parseChoiceAction = pca


    def parseImpl( self, instring, loc, state, doActions=True ):
        maxExcLoc = -1
        maxException = None

        if self.parseChoiceAction is None or not self.exprs:
            return -1, ParseException(instring,len(instring),
                    "Choice: No choice action or no expressions given", self)

        expr = self.parseChoiceAction(instring, loc, state, self)
        if expr is None:
            return -1, ParseException(instring,len(instring),
                    "Choice: Choice action returned None", self)

        return expr._parse(instring, loc, state, doActions, callPreParse=False)

    def parseImpl_debug( self, instring, loc, state, doActions=True ):
        maxExcLoc = -1
        maxException = None

        if self.parseChoiceAction is None or not self.exprs:
            return -1, ParseException(instring,len(instring),
                    "Choice: No choice action or no expressions given", self)

        expr = self.parseChoiceAction(instring, loc, state, self)
        if expr is None:
            return -1, ParseException(instring,len(instring),
                    "Choice: Choice action returned None", self)
                    
        print(" " * state.debugIndent + "Choice choose: ", _ustr(expr))

        return expr._parse(instring, loc, state, doActions, callPreParse=False)


    def setDebug( self, flag=True ):
        super(Choice, self).setDebug(flag)
        if flag:
            self.parseImpl = self.parseImpl_debug

    def getRegex(self):
        if self.regexCombiner is not None:
            return re.compile(self.regexCombiner.getCleanPattern(),
                    self.regexCombiner.getFlags())


    def getRegexFlagsMask(self):
        if self.regexCombiner is None:
            return 0

        return self.regexCombiner.getFlagsMask()


    def __ior__(self, other ):    # TODO Remove?
        if isinstance( other, str ):
            other = Literal( other )
        return self.append( other ) #MatchFirst( [ self, other ] )

    def __str__( self ):
        if hasattr(self,"name"):
            return self.name

        if self.strRepr is None:
            self.strRepr = "Choice(" + " | ".join( [ _ustr(e) for e in self.exprs ] ) + ")"

        return self.strRepr

    def _optimizeSub(self, options):
        super(Choice, self)._optimizeSub(options)
        if self.regexCombiner is not None or "regexcombine" not in options:
            return

        combiner = RegexCombiner(self.exprs, RegexCombiner.REMODE_MATCH)
        if combiner.combine():
            self.regexCombiner = combiner
        
#         print "--optimize match", repr((self, self.regexCombiner))

    def checkRecursion( self, parseElementList ):
        subRecCheckList = parseElementList[:] + [ self ]
        for e in self.exprs:
            e.checkRecursion( subRecCheckList )


class FindFirst(ParseExpression):
    """Requires that at least one ParseExpression matches somewhere
       (not necessarily at start location) or the end expression matches.
       The end expression is not consumed. If no expression is found at
       beginning pseudo-token(s) is/are generated by calling
       pseudoParseAction
       If two expressions match, the first one listed is the one that will match.
    """
    def __init__( self, exprs, endExpr ):
        super(FindFirst,self).__init__(exprs)
        self.endExpr = endExpr

        if endExpr:
            self.mayReturnEmpty = True  # Because endExpr is not consumed
        elif exprs:
            self.mayReturnEmpty = False
            for e in self.exprs:
                if e.mayReturnEmpty:
                    self.mayReturnEmpty = True
                    break
        else:
            self.mayReturnEmpty = True

        self.pseudoParseAction = []
        self.regexCombinerAll = None
#         self.regexCombinerNoEnd = None


    def setPseudoParseAction( self, *fns, **kwargs ):
        """Define action to perform to create pseudo-expression before actual match
           Parse action fn is a callable method with 0-4 arguments, called as fn(s,loc,st,toks),
           fn(loc,toks), fn(toks), or just fn(), where:
            - s   = the original string being parsed (see note below)
            - loc = the location of the matching substring
            - st  = execution state of parsing
            - toks = a list containing the matched part as string
           If the functions in fns modify the tokens, they can return them as the return
           value from fn, and the modified list of tokens will replace the original.
           If fn returns None, no token is created

           Note: the default parsing behavior is to expand tabs in the input string
           before starting the parsing process.  See L{I{parseString}<parseString>} for more information
           on parsing strings containing <TAB>s, and suggested methods to maintain a
           consistent view of the parsed string, the parse location, and line and column
           positions within the parsed string.
           """
        self.pseudoParseAction = list(map(self._normalizeParseActionArgs, list(fns)))
        return self

    def addPseudoParseAction( self, *fns, **kwargs ):
        """Add parse action to expression's list of parse actions. See L{I{setPseudoParseAction}<setPseudoParseAction>}."""
        self.pseudoParseAction += list(map(self._normalizeParseActionArgs, list(fns)))
        return self

    def getRegexCombiner(self):
        return self.regexCombinerAll

#     def parseImpl1( self, instring, loc, state, doActions=True ):
#         instrlen = len(instring)
#         endParseFn = self.endExpr._parse
#         endTokenFound = False
#         startLoc = loc
#         nextLoc = -1
# 
#         if self.regexCombinerAll is None:
#             while loc <= instrlen:
#                 nextLoc = -1
#                 try:
#                     nextLoc,tokens = endParseFn(instring, loc, state, doActions)
# #                     print "--findFirst endToken found", _ustr(self.endExpr), loc, nextLoc
#                     endTokenFound = True
#                 except (ParseException, IndexError):
#                     for e in self.exprs:
#                         try:
#                             nextLoc, tokens = e._parse(instring, loc, state, doActions)
#                             break
#                         except (ParseException, IndexError):
#                             pass
#     
#                 if nextLoc > -1:
#                     break
#     
#                 loc += 1
#         
#         else:
#             while loc <= instrlen:
#                 nextLoc = -1
#                 loc, idx = self.regexCombinerAll.find(instring, loc)
#                 # If idx is 0, the end expression matched, higher values
#                 # matched self.exprs[idx-1]
#                 # idx == -1 means nothing found
#                 
#                 if idx == -1:
#                     raise ParseException(instring,startLoc,"Neither end %s nor one of %s found" %
#                             (_ustr(self.endExpr), _ustr(self.exprs)))
# 
#                 if idx == 0:
#                     try:
#                         nextLoc,tokens = endParseFn(instring, loc, state, doActions)
#                         endTokenFound = True
#                         break
#                     except (ParseException, IndexError):
#                         loc, idx = self.regexCombinerNoEnd.find(instring, loc)
#                         if idx == -1:
#                             loc += 1
#                             continue
# 
#                         idx += 1
# 
#                 for i in xrange(idx-1, len(self.exprs)):
#                     try:
#                         nextLoc, tokens = self.exprs[i]._parse(
#                                 instring, loc, state, doActions)
#                         break
#                     except (ParseException, IndexError):
#                         pass
#     
#                 if nextLoc > -1:
#                     break
# 
#                 loc += 1
# 
#         if nextLoc == -1:
#             raise ParseException(instring,startLoc,"Neither end %s nor one of %s found" %
#                     (_ustr(self.endExpr), _ustr(self.exprs)))
# 
#         pTokens = []
#         for fn in self.pseudoParseAction:
#             pTokens = fn(instring, startLoc, state, buildSyntaxNode(instring[startLoc:loc], startLoc))
# 
#         if pTokens is None:
#             pTokens = []
#         else:
#             if not isinstance(pTokens, list):
#                 pTokens = [buildSyntaxNode(pTokens)]
# 
#         if endTokenFound:
#             return loc, pTokens
#         else:
#             return nextLoc, pTokens + tokens


    def parseImpl( self, instring, loc, state, doActions=True ):
        instrlen = len(instring)
        endParseFn = self.endExpr._parse
        endTokenFound = False
        startLoc = loc
        nextLoc = -1
        
        if self.regexCombinerAll is None:
            while loc <= instrlen:
                nextLoc = -1
                try:
                    nextLoc,tokens = endParseFn(instring, loc, state, doActions)
                    if nextLoc != -1:
                        endTokenFound = True
                        break
                        
                except (ParseException, IndexError):
                    pass
                    
                for e in self.exprs:
                    try:
                        nextLoc, tokens = e._parse(instring, loc, state, doActions)
                        if nextLoc != -1:
                            break
                    except (ParseException, IndexError):
                        pass
    
                if nextLoc > -1:
                    break
    
                loc += 1

        else:
            while loc <= instrlen:
                nextLoc = -1
                loc, styles = self.regexCombinerAll.findAll(instring, loc)
                # If idx is 0, the end expression matched, higher values
                # matched self.exprs[idx-1]
                # idx == -1 means nothing found

                if len(styles) == 0:
                    return -1, ParseException(instring,startLoc,"Neither end %s nor one of %s found" %
                            (_ustr(self.endExpr), _ustr(self.exprs)))

                if styles[0] == 0:
                    try:
                        nextLoc,tokens = endParseFn(instring, loc, state, doActions)
                        if nextLoc != -1:
                            endTokenFound = True
                            break

                    except (ParseException, IndexError):
                        pass
                        
                    del styles[0]
                    if len(styles) == 0:
                        loc += 1
                        continue
                
                for st in styles:
                    try:
                        nextLoc, tokens = self.exprs[st - 1]._parse(
                                instring, loc, state, doActions)
                        if nextLoc != -1:
                            break
                    except (ParseException, IndexError):
                        pass
    
                if nextLoc > -1:
                    break

                loc += 1

        if nextLoc == -1:
            return -1, ParseException(instring,startLoc,"Neither end %s nor one of %s found" %
                    (_ustr(self.endExpr), _ustr(self.exprs)))

        pTokens = []
        for fn in self.pseudoParseAction:
            pTokens = fn(instring, startLoc, state, buildSyntaxNode(instring[startLoc:loc], startLoc))

        if pTokens is None:
            pTokens = []
        else:
            if not isinstance(pTokens, list):
                pTokens = [buildSyntaxNode(pTokens)]

        if endTokenFound:
            return loc, pTokens
        else:
            return nextLoc, pTokens + tokens


    def __str__( self ):
        if hasattr(self,"name"):
            return self.name

        if self.strRepr is None:
            self.strRepr = "FindFirst{" + _ustr(self.endExpr) + ", " + " | ".join( [ _ustr(e) for e in self.exprs ] ) + "}"

        return self.strRepr


    def checkRecursion( self, parseElementList ):
        subRecCheckList = parseElementList[:] + [ self ]
        for e in self.exprs:
            e.checkRecursion( subRecCheckList )


    def getContainedElements(self):
        return self.exprs + [self.endExpr]


    def _optimizeSub(self, options):
        super(FindFirst, self)._optimizeSub(options)
        self.endExpr._optimizeSub(options)

        if self.regexCombinerAll is not None or "regexcombine" not in options:
            return

        combiner = RegexCombiner([self.endExpr] + self.exprs,
                RegexCombiner.REMODE_SEARCH_ALL)
                
        if combiner.combine():
            self.regexCombinerAll = combiner
        
#         print "--optimize combined", repr((self, self.regexCombinerAll))


#     def streamline( self ):
#         if not self.streamlined:
#             self.streamlined = True
#             if self.endExpr is not None:
#                 self.endExpr.streamline()
# 
#             for e in self.exprs:
#                 e.streamline()
# 
#         return self

    def _setDebugRecursIntern(self, flag, visited, deepness):
        if super(FindFirst,self)._setDebugRecursIntern(flag, visited,
                deepness):
            if self.endExpr is not None:
                self.endExpr._setDebugRecursIntern(flag, visited,
                        deepness - 1 if deepness > 0 else -1)
            return True
        return False


class Each(ParseExpression):
    """Requires all given ParseExpressions to be found, but in any order.
       Expressions may be separated by whitespace.
       May be constructed using the '&' operator.
    """
    def __init__( self, exprs ):
        super(Each,self).__init__(exprs)
        self.mayReturnEmpty = True
        for e in self.exprs:
            if not e.mayReturnEmpty:
                self.mayReturnEmpty = False
                break
        self.skipWhitespace = True
        self.initExprGroups = True

    def parseImpl( self, instring, loc, state, doActions=True ):
        if self.initExprGroups:
            self.optionals = [ e.expr for e in self.exprs if isinstance(e,Optional) ]
            self.multioptionals = [ e.expr for e in self.exprs if isinstance(e,ZeroOrMore) ]
            self.multirequired = [ e.expr for e in self.exprs if isinstance(e,OneOrMore) ]
            self.required = [ e for e in self.exprs if not isinstance(e,(Optional,ZeroOrMore,OneOrMore)) ]
            self.required += self.multirequired
            self.initExprGroups = False

        tmpLoc = loc
        tmpReqd = self.required[:]
        tmpOpt  = self.optionals[:]
        matchOrder = []

        keepMatching = True
        while keepMatching:
            tmpExprs = tmpReqd + tmpOpt + self.multioptionals + self.multirequired
            failed = []
            for e in tmpExprs:
#                 try:
                testLoc, tokens = e.tryParse( instring, tmpLoc, state )
                if testLoc == -1:
                    err = tokens
                    if isinstance(err, ParseException):
                        failed.append(e)
                    else:
                        return -1, err
                else:
                    tmpLoc = testLoc
                    matchOrder.append(e)
                    if e in tmpReqd:
                        tmpReqd.remove(e)
                    elif e in tmpOpt:
                        tmpOpt.remove(e)


#                 except ParseException:
#                     failed.append(e)
#                 else:
#                     matchOrder.append(e)
#                     if e in tmpReqd:
#                         tmpReqd.remove(e)
#                     elif e in tmpOpt:
#                         tmpOpt.remove(e)

            if len(failed) == len(tmpExprs):
                keepMatching = False

        if tmpReqd:
            missing = ", ".join( [ _ustr(e) for e in tmpReqd ] )
            return -1, ParseException(instring,loc,"Missing one or more required elements (%s)" % missing )

        # add any unmatched Optionals, in case they have default values defined
        matchOrder += list(e for e in self.exprs if isinstance(e,Optional) and e.expr in tmpOpt)

        resultlist = []
        for e in matchOrder:
            loc,results = e._parse(instring, loc, state, doActions)
            if loc == -1:
                return -1, results

            resultlist.append(results)   # TODO: Not resultlist += results  ?

        return loc, resultlist




#         for r in resultlist:
#             dups = {}
#             for k in r.keys():
#                 if k in finalResults.keys():
#                     tmp = ParseResults(finalResults[k])
#                     tmp += ParseResults(r[k])
#                     dups[k] = tmp
#             finalResults += ParseResults(r)
#             for k,v in dups.items():
#                 finalResults[k] = v


    def __str__( self ):
        if hasattr(self,"name"):
            return self.name

        if self.strRepr is None:
            self.strRepr = "{" + " & ".join( [ _ustr(e) for e in self.exprs ] ) + "}"

        return self.strRepr

    def checkRecursion( self, parseElementList ):
        subRecCheckList = parseElementList[:] + [ self ]
        for e in self.exprs:
            e.checkRecursion( subRecCheckList )


class ParseElementEnhance(ParserElement):
    """Abstract subclass of ParserElement, for combining and post-processing parsed tokens."""
    def __init__( self, expr ):
        super(ParseElementEnhance,self).__init__()
        if isinstance( expr, str ):
            expr = Literal(expr)
        self.expr = expr
        self.strRepr = None
        if expr is not None:
            self.mayIndexError = expr.mayIndexError
            self.mayReturnEmpty = expr.mayReturnEmpty
            self.setWhitespaceChars( expr.whiteChars )
            self.skipWhitespace = expr.skipWhitespace
            self.callPreparse = expr.callPreparse
            self.ignoreExprs.extend(expr.ignoreExprs)

    def parseImpl( self, instring, loc, state, doActions=True ):
        if self.expr is not None:
            return self.expr._parse( instring, loc, state, doActions, callPreParse=False )
        else:
#             raise ParseException("ParseElementEnhance expr is None %s" % _ustr(self),loc,self.errmsg,self)
            return -1, ParseException("ParseElementEnhance expr is None %s" % _ustr(self),loc,"ParseElementEnhance expr is None %s" % _ustr(self),self)

    def leaveWhitespace( self ):
        self.skipWhitespace = False
        self.expr = self.expr.copy()
        if self.expr is not None:
            self.expr.leaveWhitespace()
        return self

    def ignore( self, other ):
        if isinstance( other, Suppress ):
            if other not in self.ignoreExprs:
                super( ParseElementEnhance, self).ignore( other )
                if self.expr is not None:
                    self.expr.ignore( self.ignoreExprs[-1] )
        else:
            super( ParseElementEnhance, self).ignore( other )
            if self.expr is not None:
                self.expr.ignore( self.ignoreExprs[-1] )
        return self

    def getContainedElements(self):
        if self.expr is not None:
            return [self.expr]
        else:
            return []

#     def streamline( self ):
#         super(ParseElementEnhance,self).streamline()
#         if self.expr is not None:
#             self.expr.streamline()
#         return self

    def checkRecursion( self, parseElementList ):
        if self in parseElementList:
            raise RecursiveGrammarException( parseElementList+[self] )
        subRecCheckList = parseElementList[:] + [ self ]
        if self.expr is not None:
            self.expr.checkRecursion( subRecCheckList )

    def validate( self, validateTrace=[] ):
        tmp = validateTrace[:]+[self]
        if self.expr is not None:
            self.expr.validate(tmp)
        self.checkRecursion( [] )

    def _setDebugRecursIntern(self, flag, visited, deepness):
        if super(ParseElementEnhance,self)._setDebugRecursIntern(flag, visited,
                deepness):
            if self.expr is not None:
                self.expr._setDebugRecursIntern(flag, visited,
                        deepness - 1 if deepness > 0 else -1)
            return True
        return False


    def __str__( self ):
        try:
            return super(ParseElementEnhance,self).__str__()
        except:
            pass

        if self.strRepr is None and self.expr is not None:
            self.strRepr = "%s:(%s)" % ( self.__class__.__name__, _ustr(self.expr) )
        return self.strRepr

    def _optimizeSub(self, options):
        if self.expr is not None:
            self.expr = self.expr._realOptimize(options)



class FollowedBy(ParseElementEnhance, NecessaryRegexProvider):
    """Lookahead matching of the given parse expression.  FollowedBy
    does *not* advance the parsing position within the input string, it only
    verifies that the specified parse expression matches at the current
    position.  FollowedBy always returns a null token list."""
    def __init__( self, expr ):
        super(FollowedBy,self).__init__(expr)
        self.mayReturnEmpty = True

    def parseImpl( self, instring, loc, state, doActions=True ):
        tmpLoc, tmpTokens = self.expr.tryParse( instring, loc, state )
        if tmpLoc == -1:
            return -1, tmpTokens

        return loc, []

    def getRegex(self):
        if not isinstance(self.expr, NecessaryRegexProvider):
            return None

        if self.buildingRegex:
            return None

        self.buildingRegex = True
        try:
            r = self.expr.getRegex()
            return re.compile("(?=" + r.pattern + ")", r.flags)
        finally:
            self.buildingRegex = False


    def getRegexFlagsMask(self):
        if not isinstance(self.expr, NecessaryRegexProvider):
            return 0

        if self.buildingRegex:
            return None
        self.buildingRegex = True
        try:
            return self.expr.getRegexFlagsMask()
        finally:
            self.buildingRegex = False


    def isRegexComplete(self):
        if not isinstance(self.expr, NecessaryRegexProvider):
            return False

        if self.buildingRegex:
            return None
        self.buildingRegex = True
        try:
            return self.expr.isRegexComplete()
        finally:
            self.buildingRegex = False





class NotAny(ParseElementEnhance, NecessaryRegexProvider):
    """Lookahead to disallow matching with the given parse expression.  NotAny
    does *not* advance the parsing position within the input string, it only
    verifies that the specified parse expression does *not* match at the current
    position.  Also, NotAny does *not* skip over leading whitespace. NotAny
    always returns a null token list.  May be constructed using the '~' operator."""
    def __init__( self, expr ):
        super(NotAny,self).__init__(expr)
        #~ self.leaveWhitespace()
        self.skipWhitespace = False  # do NOT use self.leaveWhitespace(), don't want to propagate to exprs
        self.mayReturnEmpty = True
        self.errmsg = "Found unwanted token, "+_ustr(self.expr)
        #self.myException = ParseException("",0,self.errmsg,self)

    def parseImpl( self, instring, loc, state, doActions=True ):
#         try:
        tmpLoc, tmpTokens = self.expr.tryParse( instring, loc, state )
        
        if tmpLoc == -1:
            return loc, []
        else:
            exc = self.myException
            exc.loc = loc
            exc.pstr = instring
            return -1, exc

#         except (ParseException,IndexError):
#             pass
#         else:
#             #~ raise ParseException(instring, loc, self.errmsg )
#             exc = self.myException
#             exc.loc = loc
#             exc.pstr = instring
#             return -1, exc
#         return loc, []

    def __str__( self ):
        if hasattr(self,"name"):
            return self.name

        if self.strRepr is None:
            self.strRepr = "~{" + _ustr(self.expr) + "}"

        return self.strRepr

    def getRegex(self):
        if not isinstance(self.expr, NecessaryRegexProvider):
            return None

        if self.buildingRegex:
            return None

        self.buildingRegex = True
        try:
            r = self.expr.getRegex()
            return re.compile("(?!" + r.pattern + ")", r.flags)
        finally:
            self.buildingRegex = False


    def getRegexFlagsMask(self):
        if not isinstance(self.expr, NecessaryRegexProvider):
            return 0

        if self.buildingRegex:
            return None
        self.buildingRegex = True
        try:
            return self.expr.getRegexFlagsMask()
        finally:
            self.buildingRegex = False


    def isRegexComplete(self):
        if not isinstance(self.expr, NecessaryRegexProvider):
            return False

        if self.buildingRegex:
            return None
        self.buildingRegex = True
        try:
            return self.expr.isRegexComplete()
        finally:
            self.buildingRegex = False


class ZeroOrMore(ParseElementEnhance):
    """Optional repetition of zero or more of the given expression."""
    def __init__( self, expr ):
        super(ZeroOrMore,self).__init__(expr)
        self.mayReturnEmpty = True

    def getNamedElementNeedsPacking(self):
        return True


    def getRegex(self):
        if not isinstance(self.expr, NecessaryRegexProvider):
            return None

        if self.buildingRegex:
            return None
        self.buildingRegex = True
        try:
            regex = self.expr.getRegex()
            if regex is None:
                return None
            try:
                return re.compile("(?:" + regex.pattern + ")*", regex.flags)
            except re.error:
                return None
        finally:
            self.buildingRegex = False


    def getRegexFlagsMask(self):
        if not isinstance(self.expr, NecessaryRegexProvider):
            return 0

        if self.buildingRegex:
            return None
        self.buildingRegex = True
        try:
            return self.expr.getRegexFlagsMask()
        finally:
            self.buildingRegex = False


    def isRegexComplete(self):
        if not isinstance(self.expr, NecessaryRegexProvider):
            return False

        if self.buildingRegex:
            return None
        self.buildingRegex = True
        try:
            return self.expr.isRegexComplete()
        finally:
            self.buildingRegex = False


    def parseImpl( self, instring, loc, state, doActions=True ):
        tokens = []
        try:
            tmpLoc, tmpTokens = self.expr._parse( instring, loc, state, doActions, callPreParse=False )
            if tmpLoc == -1:
                return loc, tokens
            
            loc = tmpLoc
            tokens = tmpTokens

            hasIgnoreExprs = ( len(self.ignoreExprs) > 0 )
            while 1:
                if hasIgnoreExprs:
                    preloc = self._skipIgnorables( instring, loc, state )
                else:
                    preloc = loc
                tmpLoc, tmptokens = self.expr._parse( instring, preloc, state, doActions )
                if tmpLoc == -1:
                    return loc, tokens
                
                loc = tmpLoc
                if tmptokens:   #  or tmptokens.keys():
                    tokens += tmptokens
        except (ParseException,IndexError) as e:
            pass
            
        return loc, tokens

    def __str__( self ):
        if hasattr(self,"name"):
            return self.name

        if self.strRepr is None:
            self.strRepr = "[" + _ustr(self.expr) + "]..."

        return self.strRepr

    def setResultsName( self, name, listAllMatches=False ):
        ret = super(ZeroOrMore,self).setResultsName(name,listAllMatches)
        return ret


class OneOrMore(ParseElementEnhance, NecessaryRegexProvider):
    """Repetition of one or more of the given expression."""

    def getNamedElementNeedsPacking(self):
        return True


    def getRegex(self):
        if not isinstance(self.expr, NecessaryRegexProvider):
            return None

        if self.buildingRegex:
            return None
        self.buildingRegex = True
        try:
            regex = self.expr.getRegex()
            if regex is None:
                return None
            try:
                return re.compile("(?:" + regex.pattern + ")+", regex.flags)
            except re.error:
                return None
        finally:
            self.buildingRegex = False


    def getRegexFlagsMask(self):
        if not isinstance(self.expr, NecessaryRegexProvider):
            return 0

        if self.buildingRegex:
            return None
        self.buildingRegex = True
        try:
            return self.expr.getRegexFlagsMask()
        finally:
            self.buildingRegex = False


    def isRegexComplete(self):
        if not isinstance(self.expr, NecessaryRegexProvider):
            return False

        if self.buildingRegex:
            return None
        self.buildingRegex = True
        try:
            return self.expr.isRegexComplete()
        finally:
            self.buildingRegex = False


    def parseImpl( self, instring, loc, state, doActions=True ):
        # must be at least one
        tmpLoc, tmpTokens = self.expr._parse( instring, loc, state, doActions, callPreParse=False )
        if tmpLoc == -1:
            return -1, tmpTokens
        
        loc = tmpLoc
        tokens = tmpTokens
        
        try:
            hasIgnoreExprs = ( len(self.ignoreExprs) > 0 )
            while 1:
                if hasIgnoreExprs:
                    preloc = self._skipIgnorables( instring, loc, state )
                else:
                    preloc = loc
                tmpLoc, tmptokens = self.expr._parse( instring, preloc, state, doActions )
                if tmpLoc == -1:
                    return loc, tokens
                
                loc = tmpLoc
                if tmptokens:   #  or tmptokens.keys():
                    tokens += tmptokens
        except (ParseException,IndexError) as e:
            pass
            
        return loc, tokens


    def __str__( self ):
        if hasattr(self,"name"):
            return self.name

        if self.strRepr is None:
            self.strRepr = "{" + _ustr(self.expr) + "}..."

        return self.strRepr

    def setResultsName( self, name, listAllMatches=False ):
        ret = super(OneOrMore,self).setResultsName(name,listAllMatches)
        return ret


class _NullToken:
    def __bool__(self):
        return False
    __nonzero__ = __bool__
    def __str__(self):
        return ""

_optionalNotMatched = _NullToken()
class Optional(ParseElementEnhance, NecessaryRegexProvider):
    """Optional matching of the given expression.
       A default return string can also be specified, if the optional expression
       is not found.
    """
    def __init__( self, exprs, default=_optionalNotMatched ):
        super(Optional,self).__init__( exprs )
        self.defaultValue = default
        self.mayReturnEmpty = True


    def getNamedElementNeedsPacking(self):
        return True

    def getRegex(self):
        if not isinstance(self.expr, NecessaryRegexProvider):
            return None

        if self.buildingRegex:
            return None
        self.buildingRegex = True
        try:
            regex = self.expr.getRegex()
            if regex is None:
                return None
            try:
                return re.compile("(?:" + regex.pattern + ")?", regex.flags)
            except re.error:
                return None
        finally:
            self.buildingRegex = False


    def getRegexFlagsMask(self):
        if not isinstance(self.expr, NecessaryRegexProvider):
            return 0

        if self.buildingRegex:
            return None
        self.buildingRegex = True
        try:
            return self.expr.getRegexFlagsMask()
        finally:
            self.buildingRegex = False


    def isRegexComplete(self):
        if not isinstance(self.expr, NecessaryRegexProvider):
            return False

        if self.buildingRegex:
            return None
        self.buildingRegex = True
        try:
            return self.expr.isRegexComplete()
        finally:
            self.buildingRegex = False


    def parseImpl( self, instring, loc, state, doActions=True ):
        try:
            tmpLoc, tokens = self.expr._parse( instring, loc, state, doActions, callPreParse=False )
            if tmpLoc != -1:
                return tmpLoc, tokens
        except (ParseException,IndexError):
            pass
        if self.defaultValue is not _optionalNotMatched:
            tokens = [self.defaultValue]

#                 if self.expr.resultsName:
#                     tokens = ParseResults([ self.defaultValue ])
#                     tokens[self.expr.resultsName] = self.defaultValue
#                 else:
#                     tokens = [ self.defaultValue ]
        else:
            tokens = []

        return loc, tokens



    def __str__( self ):
        if hasattr(self,"name"):
            return self.name

        if self.strRepr is None:
            self.strRepr = "[" + _ustr(self.expr) + "]"

        return self.strRepr


# TODO: allow pseudoParseAction to let behave it similar to FindFirst
# TODO: Modified from original. Check if OK.
class SkipTo(ParseElementEnhance):
    """Token for skipping over all undefined text until the matched expression is found.
       If include is set to true, the matched expression is also parsed (the skipped text
       and matched expression are returned as a 2-element list).  The ignore
       argument is used to define grammars (typically quoted strings and comments) that
       might contain false matches.
    """
    def __init__( self, other, include=False, ignore=None, failOn=None ):
        super( SkipTo, self ).__init__( other )
        self.ignoreExpr = ignore
        self.mayReturnEmpty = True
        self.mayIndexError = False
        self.includeMatch = include
        self.asList = False
        if failOn is not None and isinstance(failOn, str):
            self.failOn = Literal(failOn)
        else:
            self.failOn = failOn
        self.errmsg = "No match found for "+_ustr(self.expr)
        #self.myException = ParseException("",0,self.errmsg,self)

    def getNamedElementNeedsPacking(self):
        return True

    def parseImpl( self, instring, loc, state, doActions=True ):
        startLoc = loc
        instrlen = len(instring)
        expr = self.expr
        failParse = False
        while loc <= instrlen:
            try:
                if self.failOn:
                    try:
                        tmpLoc, tmpTokens = self.failOn.tryParse(instring, loc)
                        if tmpLoc == -1: # TODO: More efficient
                            raise tmpTokens
                    except ParseBaseException:
                        pass
                    else:
                        failParse = True
                        return -1, ParseException(instring, loc, "Found expression " + str(self.failOn))
                    failParse = False
                if self.ignoreExpr is not None:
                    while 1:
                        try:
                            tmpLoc, tmpTokens = self.ignoreExpr.tryParse(instring,loc)
                            if tmpLoc == -1: # TODO: More efficient
                                raise tmpTokens
                            
                            loc = tmpLoc

                            print("found ignoreExpr, advance to", loc)
                        except ParseBaseException:
                            break

                tmpLoc, tmpTokens = expr._parse( instring, loc, state, doActions=False,
                        callPreParse=False )

                if tmpLoc == -1: # TODO: More efficient
                    raise tmpTokens

                skipText = buildSyntaxNode(instring[startLoc:loc])
                if self.includeMatch:
                    tmpLoc, tmpTokens= expr._parse(instring, loc, state, doActions,
                            callPreParse=False)
                            
                    if tmpLoc == -1: # TODO: More efficient
                        raise tmpTokens
                        
                    loc = tmpLoc
                    mat = tmpTokens

                    return loc, [ skipText ] + mat

#                     if mat:
#                         skipRes = buildSyntaxNode([skipText] + mat)
#                         return loc, [ skipText ] + mat
#                     else:
#                         return loc, [ skipText ]
                else:
                    return loc, [ skipText ]

            except (ParseException,IndexError):
                if failParse:
                    raise
                else:
                    loc += 1
        exc = self.myException
        exc.loc = loc
        exc.pstr = instring
        return -1, exc



class Forward(ParseElementEnhance, NecessaryRegexProvider):
    """Forward declaration of an expression to be defined later -
       used for recursive grammars, such as algebraic infix notation.
       When the expression is known, it is assigned to the Forward variable using the '<<' operator.

       Note: take care when assigning to Forward not to overlook precedence of operators.
       Specifically, '|' has a lower precedence than '<<', so that::
          fwdExpr << a | b | c
       will actually be evaluated as::
          (fwdExpr << a) | b | c
       thereby leaving b and c out as parseable alternatives.  It is recommended that you
       explicitly group the values inserted into the Forward::
          fwdExpr << (a | b | c)
    """
    def __init__( self, other=None ):
        super(Forward,self).__init__( other )

    def getNamedElementNeedsPacking(self):
        if not self.expr:
            return False
        
        return self.expr.getNamedElementNeedsPacking() and not self.expr.resultsName and \
                not self.resultsName

    def getRegex(self):
        if not isinstance(self.expr, NecessaryRegexProvider):
            return None

        if self.buildingRegex:
            return None
        self.buildingRegex = True
        try:
            return self.expr.getRegex()
        finally:
            self.buildingRegex = False


    def getRegexFlagsMask(self):
        if not isinstance(self.expr, NecessaryRegexProvider):
            return 0

        if self.buildingRegex:
            return None
        self.buildingRegex = True
        try:
            return self.expr.getRegexFlagsMask()
        finally:
            self.buildingRegex = False


    def isRegexComplete(self):
        if not isinstance(self.expr, NecessaryRegexProvider):
            return False

        if self.buildingRegex:
            return None
        self.buildingRegex = True
        try:
            return self.expr.isRegexComplete()
        finally:
            self.buildingRegex = False


    def _getHeadForward(self):
        """
        We may have a chain of Forward s pointing to other Forward s so find
        the head of this chain.
        """
        ret = self
        while ret.expr is not None and isinstance(ret.expr, Forward):
            ret = ret.expr
        
        return ret


    def __lshift__( self, other ):
        if isinstance( other, str ):
            other = Literal(other)
        
        head = self._getHeadForward()
        head.expr = other
        head.mayReturnEmpty = other.mayReturnEmpty
        head.strRepr = None
        head.mayIndexError = self.expr.mayIndexError
        head.mayReturnEmpty = self.expr.mayReturnEmpty
        head.setWhitespaceChars( self.expr.whiteChars )
        head.skipWhitespace = self.expr.skipWhitespace
        head.ignoreExprs.extend(self.expr.ignoreExprs)

        return None

    def leaveWhitespace( self ):
        self.skipWhitespace = False
        return self

    def parseImpl( self, instring, loc, state, doActions=True ):
        newLoc, tokens = super(Forward, self).parseImpl(instring, loc, state, doActions)
#         print "--Forward parseImpl2", repr((self.resultsName, self.expr.getNamedElementNeedsPacking(), tokens))
#         print "--Forward parseImpl2", repr((isinstance(tokens, list), len(tokens), self.expr.getNamedElementNeedsPacking(),
#                 self.expr.resultsName, self.resultsName))

        if isinstance(tokens, list) and len(tokens) > 0 and \
                self.expr.getNamedElementNeedsPacking() and \
                not self.expr.resultsName and self.resultsName:
            tokens = buildSyntaxNode(tokens, loc, self.resultsName)

        return newLoc, tokens

#     def streamline( self ):
#         if not self.streamlined:
#             self.streamlined = True
#             if self.expr is not None:
#                 self.expr.streamline()
#         return self


    def validate( self, validateTrace=[] ):
        if self not in validateTrace:
            tmp = validateTrace[:]+[self]
            if self.expr is not None:
                self.expr.validate(tmp)
        self.checkRecursion([])

    def __str__( self ):
        if hasattr(self,"name"):
            return self.name

        # TODO: Not thread-safe
        self._revertClass = self.__class__
        self.__class__ = _ForwardNoRecurse
        try:
            if self.expr is not None:
                retString = _ustr(self.expr)
            else:
                retString = "None"
        finally:
            self.__class__ = self._revertClass
        return self.__class__.__name__ + ": " + retString

    def copy(self):
        if self.expr is not None:
            return super(Forward,self).copy()
        else:
            ret = Forward()
            ret << self
            return ret

class _ForwardNoRecurse(Forward):
    def __str__( self ):
        return "..."

class TokenConverter(ParseElementEnhance):
    """Abstract subclass of ParseExpression, for converting parsed results."""
    def __init__( self, expr ):
        super(TokenConverter,self).__init__( expr )


# TODO May not work
class Upcase(TokenConverter):
    """Converter to upper case all matching tokens."""
    def __init__(self, *args):
        super(Upcase,self).__init__(*args)
        warnings.warn("Upcase class is deprecated, use upcaseTokens parse action instead",
                       DeprecationWarning,stacklevel=2)

    def postParse( self, instring, loc, state, tokenlist ):
        return list(map( string.upper, tokenlist ))


class Combine(TokenConverter):
    """Converter to concatenate all matching tokens to a single string.
       By default, the matching patterns must also be contiguous in the input string;
       this can be disabled by specifying 'adjacent=False' in the constructor.
    """
    def __init__( self, expr, joinString="", adjacent=True ):
        super(Combine,self).__init__( expr )
        # suppress whitespace-stripping in contained parse expressions, but re-enable it on the Combine itself
        if adjacent:
            self.leaveWhitespace()
        self.adjacent = adjacent
        self.skipWhitespace = True
        self.joinString = joinString

    def ignore( self, other ):
        if self.adjacent:
            ParserElement.ignore(self, other)
        else:
            super( Combine, self).ignore( other )
        return self

    def postParse( self, instring, loc, state, tokenlist ):
#         tokenlist = buildSyntaxNode(tokenlist)
#         retToks = tokenlist.copy()
#         del retToks.getChildren()[:]
#         del retToks[:]
#         retToks += [ "".join(tokenlist.asStringList(self.joinString)) ]
# 
#         if self.resultsName and len(retToks.keys())>0:
#             return [ retToks ]
#         else:
#             return retToks

        return [ buildSyntaxNode(self.joinString.join(tokenlist.asStringList())) ]


class Group(TokenConverter, NecessaryRegexProvider):
    """Converter to return the matched tokens as a list - useful for returning tokens of ZeroOrMore and OneOrMore expressions."""
#     def __init__( self, expr ):
#         super(Group,self).__init__( expr )


    def getNamedElementNeedsPacking(self):
        return True

    def getRegex(self):
        if not isinstance(self.expr, NecessaryRegexProvider):
            return None

        if self.buildingRegex:
            return None
        self.buildingRegex = True
        try:
            return self.expr.getRegex()
        finally:
            self.buildingRegex = False


    def getRegexFlagsMask(self):
        if not isinstance(self.expr, NecessaryRegexProvider):
            return 0

        if self.buildingRegex:
            return None
        self.buildingRegex = True
        try:
            return self.expr.getRegexFlagsMask()
        finally:
            self.buildingRegex = False


    def isRegexComplete(self):
        if not isinstance(self.expr, NecessaryRegexProvider):
            return False

        if self.buildingRegex:
            return None
        self.buildingRegex = True
        try:
            return self.expr.isRegexComplete()
        finally:
            self.buildingRegex = False

#     def postParse( self, instring, loc, state, tokenlist ):
#         return [ buildSyntaxNode(tokenlist) ]



# TODO Make working again  (_ParseResultsWithOffset not defined)
# class Dict(TokenConverter):
#     """Converter to return a repetitive expression as a list, but also as a dictionary.
#        Each element can also be referenced using the first token in the expression as its key.
#        Useful for tabular report scraping when the first column can be used as a item key.
#     """
#     def __init__( self, exprs ):
#         super(Dict,self).__init__( exprs )
#         self.saveAsList = True
# 
#     def postParse( self, instring, loc, state, tokenlist ):
#         for i,tok in enumerate(tokenlist):
#             if len(tok) == 0:
#                 continue
#             ikey = tok[0]
#             if isinstance(ikey,int):
#                 ikey = _ustr(tok[0]).strip()
#             if len(tok)==1:
#                 tokenlist[ikey] = _ParseResultsWithOffset("",i)
#             elif len(tok)==2 and not isinstance(tok[1],ParseResults):
#                 tokenlist[ikey] = _ParseResultsWithOffset(tok[1],i)
#             else:
#                 dictvalue = tok.copy() #ParseResults(i)
#                 del dictvalue[0]
#                 if len(dictvalue)!= 1 or (isinstance(dictvalue,ParseResults) and dictvalue.keys()):
#                     tokenlist[ikey] = _ParseResultsWithOffset(dictvalue,i)
#                 else:
#                     tokenlist[ikey] = _ParseResultsWithOffset(dictvalue[0],i)
# 
#         if self.resultsName:
#             return [ tokenlist ]
#         else:
#             return tokenlist


class Suppress(TokenConverter):
    """Converter for ignoring the results of a parsed expression."""
    def postParse( self, instring, loc, state, tokenlist ):
        return []

    def suppress( self ):
        return self


class OnlyOnce:
    """Wrapper for parse actions, to ensure they are only called once."""
    def __init__(self, methodCall):
        self.callable = ParserElement._normalizeParseActionArgs(methodCall)
        self.called = False
    def __call__(self,s,l,t):
        if not self.called:
            results = self.callable(s,l,t)
            self.called = True
            return results
        raise ParseException(s,l,"")
    def reset(self):
        self.called = False

def traceParseAction(f):
    """Decorator for debugging parse actions."""
    f = ParserElement._normalizeParseActionArgs(f)
    def z(*paArgs):
        thisFunc = f.__name__
        s,l,t = paArgs[-3:]
        if len(paArgs)>3:
            thisFunc = paArgs[0].__class__.__name__ + '.' + thisFunc
        sys.stderr.write( ">>entering %s(line: '%s', %d, %s)\n" % (thisFunc,line(l,s),l,t) )
        try:
            ret = f(*paArgs)
        except Exception as exc:
            sys.stderr.write( "<<leaving %s (exception: %s)\n" % (thisFunc,exc) )
            raise
        sys.stderr.write( "<<leaving %s (ret: %s)\n" % (thisFunc,ret) )
        return ret
    try:
        z.__name__ = f.__name__
    except AttributeError:
        pass
    return z




def combineRegexFlags(flags, flagsMask, otherFlags, otherFlagsMask):
    if flags is None:
        return otherFlags, otherFlagsMask
    else:
        commonMask = flagsMask & otherFlagsMask
        ownImportantFlags = flags & commonMask
        otherImportantFlags = otherFlags & commonMask
        newFlagsMask = flagsMask | otherFlagsMask

        if ownImportantFlags != otherImportantFlags:
            return None, newFlagsMask

        return (flags & flagsMask) | (otherFlags & otherFlagsMask), newFlagsMask




class RegexCombiner:
    # Match or search for the first matching expression
    REMODE_MATCH = 0
    REMODE_SEARCH = 1
    
    # Match or search for all matching expressions
    REMODE_MATCH_ALL = 2
    REMODE_SEARCH_ALL = 3
    
    def __init__(self, exprs, reMode):
        self.exprs = exprs
        self.reMode = reMode
        self.flags = None
        self.flagsMask = 0
        self.cleanPattern = None
        self.regEx = None
        
    def __getitem__(self, i):
        return self.exprs[i]
    
    def getFlags(self):
        return self.flags
        
    def getFlagsMask(self):
        return self.flagsMask
        
    def getCleanPattern(self):
        return self.cleanPattern
        
    def getRegex(self):
        return self.regEx

    def _compareCombineOtherFlags(self, otherFlags, otherFlagsMask):
        flags, flagsMask = combineRegexFlags(self.flags, self.flagsMask,
                otherFlags, otherFlagsMask)
        if flags is None:
            return False
        
        self.flags = flags
        self.flagsMask = flagsMask

        return True
        
#         if self.flags is None:
#             self.flags = otherFlags
#             self.flagsMask = otherFlagsMask
#         else:
#             commonMask = self.flagsMask & otherFlagsMask
#             ownImportantFlags = self.flags & commonMask
#             otherImportantFlags = otherFlags & commonMask
#             if ownImportantFlags != otherImportantFlags:
#                 return False
#             
#             self.flagsMask |= otherFlagsMask
#         
#         return True


    def combine(self):
#         print "--RegexCombiner.combine1", repr(self.exprs)
        regexPatterns = []
        i = 0
        
        if len(self.exprs) > 99:
            return False
        
        for i, exp in enumerate(self.exprs):
            while 1:
#                 print "--RegexCombiner.combine7", repr((i, exp))

                if isinstance(exp, Forward):
                    exp = exp.expr
                    continue

                if isinstance(exp, FindFirst) and self.reMode == \
                        RegexCombiner.REMODE_SEARCH:
                    subCombiner = exp.getRegexCombiner()
                    if subCombiner is None:
                        return False
                    
                    if not self._compareCombineOtherFlags(
                            subCombiner.getFlags(), subCombiner.getFlagsMask()):
                        return False
                    regexPatterns.append(subCombiner.getCleanPattern())
                    break
                
                if isinstance(exp, NecessaryRegexProvider):
#                     print "--RegexCombiner.combine13", repr((i, exp))
                    otherRe = exp.getRegex()
#                     print "--RegexCombiner.combine15", repr(otherRe)
                    if otherRe is None:
                        return False

#                     print "--RegexCombiner.combine17", repr(otherRe.pattern)                        
                    if not self._compareCombineOtherFlags(
                            otherRe.flags, exp.getRegexFlagsMask()):
                        return False
                    regexPatterns.append(otherRe.pattern)
                    break

                return False

        self.cleanPattern = "|".join(regexPatterns)

        if self.reMode & RegexCombiner.REMODE_MATCH_ALL:
            for i in range(len(regexPatterns)):
                regexPatterns[i] = ("(?P<style%02i>(?=" % i) + regexPatterns[i] + "))?"
            
            selectionPart = "".join(regexPatterns)

            if self.reMode == RegexCombiner.REMODE_SEARCH_ALL:
                self.regEx = re.compile(selectionPart +
                        "(?:" + self.cleanPattern + ")", self.flags)
            else:
                self.regEx = re.compile(selectionPart, self.flags)
                
#             print "--RegexCombiner.combine24", repr(self.regEx.pattern)
            return True

        else:
            for i in range(len(regexPatterns)):
                regexPatterns[i] = ("(?P<style%02i>" % i)+ regexPatterns[i] + ")"
            self.regEx = re.compile("|".join(regexPatterns), self.flags)
    
#             print "--RegexCombiner.combine29", repr(self.regEx.pattern)
            return True


    def find(self, instring, loc):
        assert self.reMode in (RegexCombiner.REMODE_SEARCH,
                RegexCombiner.REMODE_MATCH)
                
        if self.reMode == RegexCombiner.REMODE_SEARCH:
            m = self.regEx.search(instring, loc)
        else: # self.reMode == RegexCombiner.REMODE_MATCH:
            m = self.regEx.match(instring, loc)

        if m is None:
            return loc, -1

        for i in range(len(self.exprs)):
            g = m.group("style%02i" % i)
            if g is not None:
                return m.start(0), i

        raise Exception("Internal error: No matching style in RegexCombiner (match one)")


    def findAll(self, instring, loc):
        assert self.reMode in (RegexCombiner.REMODE_SEARCH_ALL,
                RegexCombiner.REMODE_MATCH_ALL)
                
        if self.reMode == RegexCombiner.REMODE_SEARCH_ALL:
            m = self.regEx.search(instring, loc)
        else: # self.reMode == RegexCombiner.REMODE_MATCH:
            m = self.regEx.match(instring, loc)

        if m is None:
            return loc, []
            
        styles = []
        
        for i in range(len(self.exprs)):
            g = m.group("style%02i" % i)
            if g is not None:
                styles.append(i)
                if "style%02i" % i == m.lastgroup:
                    break

        if len(styles) > 0:
            return m.start(0), styles

        if self.reMode == RegexCombiner.REMODE_SEARCH_ALL:
            raise Exception("Internal error: No matching style in RegexCombiner (match all)")
        else:
            return loc, []


    def __str__(self):
        return "<RegexCombiner %s>" % self.regEx.pattern
        
    __repr__ = __str__





class StackedCopyDict:
    """
    A stacked dictionary is technically a stack of dictionaries plus one base
    dictionary which is at the bottom of the stack and can't be dropped off.
    Along with get and set operations which are always executed on the
    stack top dictionary there are functions to push() a new dictionary on
    the stack (which is automatically a copy of the previous stack top) and
    to pop() the stack top dict.
    
    The class fulfills the context manager protocol and can be used with
    "with"-statement (returning itself as variable)
    """
    def __init__(self, baseDict=None, baseName=None):
        if baseDict is None:
            self.baseDict = {}
        else:
            self.baseDict = baseDict
        self.dictStack = []

        self.baseName = baseName
        self.nameStack = []
        self.topDict = self.baseDict

    def getTopDict(self):
        return self.topDict

#         if len(self.dictStack) > 0:
#             return self.dictStack[-1]
#         else:
#             return self.baseDict
            
    def getSubTopDict(self):
        if len(self.dictStack) > 1:
            return self.dictStack[-2]
        else:
            return self.baseDict
            
    def getNamedDict(self, name, default=None):
        for i in range(len(self.nameStack) - 1, -1, -1):
#             print "--getNamedDict2", repr((i, self.nameStack[i], name))
            if self.nameStack[i] == name:
                return self.dictStack[i]
        
        if self.baseName == name:
            return self.baseDict
        
        return default


    def __repr__(self):
        return "<StackedCopyDict " + repr(self.getTopDict()) + ">"

    def __getitem__(self, key):
        return self.getTopDict()[key]

    def get(self, key, failobj=None):
        return self.getTopDict().get(key, failobj)

    def __setitem__(self, key, item):
        self.getTopDict()[key] = item
        
    def __delitem__(self, key):
        del self.getTopDict()[key]

    def __enter__(self):
        self.push()
        return self
    
    def __exit__(self, type, value, traceback):
        self.pop()


    def push(self, newName=None, newDict=None):
        """
        Push new dictionary on stack, normally a copy of previous top stack dict.
        For convenience it returns the new stack top dict.
        """
#         if len(self.nameStack) > 0:
#             print "--push1", repr((newName, self.nameStack[-1]))
            
        if newDict is None:
            newDict = self.getTopDict().copy()

        self.dictStack.append(newDict)
        self.topDict = newDict

        self.nameStack.append(newName)

        return newDict


    def pop(self):
        """
        May throw exception if only base dictionary is available.
        """
        self.nameStack.pop()
        result = self.dictStack.pop()
        
        if len(self.dictStack) > 0:
            self.topDict = self.dictStack[-1]
        else:
            self.topDict = self.baseDict
        
        return result


    def has_key(self, key):
        return key in self.getTopDict()


#
# global helpers
#
def delimitedList( expr, delim=",", combine=False ):
    """Helper to define a delimited list of expressions - the delimiter defaults to ','.
       By default, the list elements and delimiters can have intervening whitespace, and
       comments, but this can be overridden by passing 'combine=True' in the constructor.
       If combine is set to True, the matching tokens are returned as a single token
       string, with the delimiters included; otherwise, the matching tokens are returned
       as a list of tokens, with the delimiters suppressed.
    """
    dlName = _ustr(expr)+" ["+_ustr(delim)+" "+_ustr(expr)+"]..."
    if combine:
        return Combine( expr + ZeroOrMore( delim + expr ) ).setName(dlName)
    else:
        return ( expr + ZeroOrMore( Suppress( delim ) + expr ) ).setName(dlName)

def countedArray( expr ):
    """Helper to define a counted list of expressions.
       This helper defines a pattern of the form::
           integer expr expr expr...
       where the leading integer tells how many expr expressions follow.
       The matched tokens returns the array of expr tokens as a list - the leading count token is suppressed.
    """
    arrayExpr = Forward()
    def countFieldParseAction(s,l,t):
        n = int(t[0])
        arrayExpr << (n and Group(And([expr]*n)) or Group(empty))
        return []
    return ( Word(nums).setName("arrayLen").setParseAction(countFieldParseAction, callDuringTry=True) + arrayExpr )

def _flatten(L):
    if type(L) is not list: return [L]
    if L == []: return L
    return _flatten(L[0]) + _flatten(L[1:])

def matchPreviousLiteral(expr):
    """Helper to define an expression that is indirectly defined from
       the tokens matched in a previous expression, that is, it looks
       for a 'repeat' of a previous expression.  For example::
           first = Word(nums)
           second = matchPreviousLiteral(first)
           matchExpr = first + ":" + second
       will match "1:1", but not "1:2".  Because this matches a
       previous literal, will also match the leading "1:1" in "1:10".
       If this is not desired, use matchPreviousExpr.
       Do *not* use with packrat parsing enabled.
    """
    rep = Forward()
    def copyTokenToRepeater(s,l,t):
        if t:
            if len(t) == 1:
                rep << t[0]
            else:
                # flatten t tokens
                tflat = _flatten(t.asList())
                rep << And( [ Literal(tt) for tt in tflat ] )
        else:
            rep << Empty()
    expr.addParseAction(copyTokenToRepeater, callDuringTry=True)
    return rep

def matchPreviousExpr(expr):
    """Helper to define an expression that is indirectly defined from
       the tokens matched in a previous expression, that is, it looks
       for a 'repeat' of a previous expression.  For example::
           first = Word(nums)
           second = matchPreviousExpr(first)
           matchExpr = first + ":" + second
       will match "1:1", but not "1:2".  Because this matches by
       expressions, will *not* match the leading "1:1" in "1:10";
       the expressions are evaluated first, and then compared, so
       "1" is compared with "10".
       Do *not* use with packrat parsing enabled.
    """
    rep = Forward()
    e2 = expr.copy()
    rep << e2
    def copyTokenToRepeater(s,l,t):
        matchTokens = _flatten(t.asList())
        def mustMatchTheseTokens(s,l,t):
            theseTokens = _flatten(t.asList())
            if  theseTokens != matchTokens:
                raise ParseException("",0,"")
        rep.setParseAction( mustMatchTheseTokens, callDuringTry=True )
    expr.addParseAction(copyTokenToRepeater, callDuringTry=True)
    return rep

def _escapeRegexRangeChars(s):
    #~  escape these chars: ^-]
    for c in r"\^-]":
        s = s.replace(c,_bslash+c)
    s = s.replace("\n",r"\n")
    s = s.replace("\t",r"\t")
    return _ustr(s)

def oneOf( strs, caseless=False, useRegex=True ):
    """Helper to quickly define a set of alternative Literals, and makes sure to do
       longest-first testing when there is a conflict, regardless of the input order,
       but returns a MatchFirst for best performance.

       Parameters:
        - strs - a string of space-delimited literals, or a list of string literals
        - caseless - (default=False) - treat all literals as caseless
        - useRegex - (default=True) - as an optimization, will generate a Regex
          object; otherwise, will generate a MatchFirst object (if caseless=True, or
          if creating a Regex raises an exception)
    """
    if caseless:
        isequal = ( lambda a,b: a.upper() == b.upper() )
        masks = ( lambda a,b: b.upper().startswith(a.upper()) )
        parseElementClass = CaselessLiteral
    else:
        isequal = ( lambda a,b: a == b )
        masks = ( lambda a,b: b.startswith(a) )
        parseElementClass = Literal

    if isinstance(strs,(list,tuple)):
        symbols = list(strs[:])
    elif isinstance(strs,str):
        symbols = strs.split()
    else:
        warnings.warn("Invalid argument to oneOf, expected string or list",
                SyntaxWarning, stacklevel=2)

    i = 0
    while i < len(symbols)-1:
        cur = symbols[i]
        for j,other in enumerate(symbols[i+1:]):
            if ( isequal(other, cur) ):
                del symbols[i+j+1]
                break
            elif ( masks(cur, other) ):
                del symbols[i+j+1]
                symbols.insert(i,other)
                cur = other
                break
        else:
            i += 1

    if not caseless and useRegex:
        #~ print (strs,"->", "|".join( [ _escapeRegexChars(sym) for sym in symbols] ))
        try:
            if len(symbols)==len("".join(symbols)):
                return Regex( "[%s]" % "".join( [ _escapeRegexRangeChars(sym) for sym in symbols] ) )
            else:
                return Regex( "|".join( [ re.escape(sym) for sym in symbols] ) )
        except:
            warnings.warn("Exception creating Regex for oneOf, building MatchFirst",
                    SyntaxWarning, stacklevel=2)


    # last resort, just use MatchFirst
    return MatchFirst( [ parseElementClass(sym) for sym in symbols ] )

def originalTextFor(expr, asString=True):    # TODO From original. Check if OK.
    """Helper to return the original, untokenized text for a given expression.  Useful to
       restore the parsed fields of an HTML start tag into the raw tag text itself, or to
       revert separate tokens with intervening whitespace back to the original matching
       input text. Simpler to use than the parse action keepOriginalText, and does not
       require the inspect module to chase up the call stack.  By default, returns a 
       string containing the original parsed text.  
       
       If the optional asString argument is passed as False, then the return value is a 
       ParseResults containing any results names that were originally matched, and a 
       single token containing the original matched text from the input string.  So if 
       the expression passed to originalTextFor contains expressions with defined
       results names, you must set asString to False if you want to preserve those
       results name values."""
    locMarker = Empty().setParseAction(lambda s,loc,t: loc)
    matchExpr = locMarker("_original_start") + expr + locMarker("_original_end")
    if asString:
        extractText = lambda s,l,t: s[t._original_start:t._original_end]
    else:
        def extractText(s,l,t):
            del t[:]
            t.insert(0, s[t._original_start:t._original_end])
            del t["_original_start"]
            del t["_original_end"]
    matchExpr.setParseAction(extractText)
    return matchExpr
    
# convenience constants for positional expressions
empty       = Empty().setName("empty")
noMatch     = NoMatch().setName("noMatch")
lineStart   = LineStart().setName("lineStart")
lineEnd     = LineEnd().setName("lineEnd")
stringStart = StringStart().setName("stringStart")
stringEnd   = StringEnd().setName("stringEnd")

_escapedPunc = Word( _bslash, r"\[]-*.$+^?()~ ", exact=2 ).setParseAction(lambda s,l,t:t[0][1])
_printables_less_backslash = "".join([ c for c in printables if c not in  r"\]" ])
_escapedHexChar = Combine( Suppress(_bslash + "0x") + Word(hexnums) ).setParseAction(lambda s,l,t:chr(int(t[0],16)))
_escapedOctChar = Combine( Suppress(_bslash) + Word("0","01234567") ).setParseAction(lambda s,l,t:chr(int(t[0],8)))
_singleChar = _escapedPunc | _escapedHexChar | _escapedOctChar | Word(_printables_less_backslash,exact=1)
_charRange = Group(_singleChar + Suppress("-") + _singleChar)
_reBracketExpr = Literal("[") + Optional("^").setResultsName("negate") + Group( OneOrMore( _charRange | _singleChar ) ).setResultsName("body") + "]"

_expanded = lambda p: (isinstance(p,SyntaxNode) and ''.join([ chr(c) for c in range(ord(p[0]),ord(p[1])+1) ]) or p)

def srange(s):
    r"""Helper to easily define string ranges for use in Word construction.  Borrows
       syntax from regexp '[]' string range definitions::
          srange("[0-9]")   -> "0123456789"
          srange("[a-z]")   -> "abcdefghijklmnopqrstuvwxyz"
          srange("[a-z$_]") -> "abcdefghijklmnopqrstuvwxyz$_"
       The input string must be enclosed in []'s, and the returned string is the expanded
       character set joined into a single string.
       The values enclosed in the []'s may be::
          a single character
          an escaped character with a leading backslash (such as \- or \])
          an escaped hex character with a leading '\0x' (\0x21, which is a '!' character)
          an escaped octal character with a leading '\0' (\041, which is a '!' character)
          a range of any of the above, separated by a dash ('a-z', etc.)
          any combination of the above ('aeiouy', 'a-zA-Z0-9_$', etc.)
    """
    try:
        return "".join([_expanded(part) for part in _reBracketExpr.parseString(s).body])
    except:
        return ""

def matchOnlyAtCol(n):
    """Helper method for defining parse actions that require matching at a specific
       column in the input text.
    """
    def verifyCol(strg,locn,toks):
        if col(locn,strg) != n:
            raise ParseException(strg,locn,"matched token not at column %d" % n)
    return verifyCol

def replaceWith(replStr):
    """Helper method for common parse actions that simply return a literal value.  Especially
       useful when used with transformString().
    """
    def _replFunc(*args):
        return [replStr]
    return _replFunc

def removeQuotes(s,l,t):
    """Helper parse action for removing quotation marks from parsed quoted strings.
       To use, add this parse action to quoted string using::
         quotedString.setParseAction( removeQuotes )
    """
    return t[0][1:-1]

def upcaseTokens(s,l,t):
    """Helper parse action to convert tokens to upper case."""
    return [ tt.upper() for tt in map(_ustr,t) ]

def downcaseTokens(s,l,t):
    """Helper parse action to convert tokens to lower case."""
    return [ tt.lower() for tt in map(_ustr,t) ]

def keepOriginalText(s,startLoc,t):
    """Helper parse action to preserve original parsed text,
       overriding any nested parse actions."""
    try:
        endloc = getTokensEndLoc()
    except ParseException:
        raise ParseFatalException("incorrect usage of keepOriginalText - may only be called as a parse action")
    del t[:]
    t += buildSyntaxNode(s[startLoc:endloc])
    return t

def getTokensEndLoc():
    """Method to be called from within a parse action to determine the end
       location of the parsed tokens."""
    import inspect
    fstack = inspect.stack()
    try:
        # search up the stack (through intervening argument normalizers) for correct calling routine
        for f in fstack[2:]:
            if f[3] == "_parseNoCache":
                endloc = f[0].f_locals["loc"]
                return endloc
        else:
            raise ParseFatalException("incorrect usage of getTokensEndLoc - may only be called from within a parse action")
    finally:
        del fstack


# TODO Works if Dict works
# def _makeTags(tagStr, xml):
#     """Internal helper to construct opening and closing tag expressions, given a tag name"""
#     if isinstance(tagStr,basestring):
#         resname = tagStr
#         tagStr = Keyword(tagStr, caseless=not xml)
#     else:
#         resname = tagStr.name
# 
#     tagAttrName = Word(alphas,alphanums+"_-:")
#     if (xml):
#         tagAttrValue = dblQuotedString.copy().setParseAction( removeQuotes )
#         openTag = Suppress("<") + tagStr + \
#                 Dict(ZeroOrMore(Group( tagAttrName + Suppress("=") + tagAttrValue ))) + \
#                 Optional("/",default=[False]).setResultsName("empty").setParseAction(lambda s,l,t:t[0]=='/') + Suppress(">")
#     else:
#         printablesLessRAbrack = "".join( [ c for c in printables if c not in ">" ] )
#         tagAttrValue = quotedString.copy().setParseAction( removeQuotes ) | Word(printablesLessRAbrack)
#         openTag = Suppress("<") + tagStr + \
#                 Dict(ZeroOrMore(Group( tagAttrName.setParseAction(downcaseTokens) + \
#                 Optional( Suppress("=") + tagAttrValue ) ))) + \
#                 Optional("/",default=[False]).setResultsName("empty").setParseAction(lambda s,l,t:t[0]=='/') + Suppress(">")
#     closeTag = Combine(_L("</") + tagStr + ">")
# 
#     openTag = openTag.setResultsName("start"+"".join(resname.replace(":"," ").title().split())).setName("<%s>" % tagStr)
#     closeTag = closeTag.setResultsName("end"+"".join(resname.replace(":"," ").title().split())).setName("</%s>" % tagStr)
# 
#     return openTag, closeTag
# 
# def makeHTMLTags(tagStr):
#     """Helper to construct opening and closing tag expressions for HTML, given a tag name"""
#     return _makeTags( tagStr, False )
# 
# def makeXMLTags(tagStr):
#     """Helper to construct opening and closing tag expressions for XML, given a tag name"""
#     return _makeTags( tagStr, True )

def withAttribute(*args,**attrDict):
    """Helper to create a validating parse action to be used with start tags created
       with makeXMLTags or makeHTMLTags. Use withAttribute to qualify a starting tag
       with a required attribute value, to avoid false matches on common tags such as
       <TD> or <DIV>.

       Call withAttribute with a series of attribute names and values. Specify the list
       of filter attributes names and values as:
        - keyword arguments, as in (class="Customer",align="right"), or
        - a list of name-value tuples, as in ( ("ns1:class", "Customer"), ("ns2:align","right") )
       For attribute names with a namespace prefix, you must use the second form.  Attribute
       names are matched insensitive to upper/lower case.

       To verify that the attribute exists, but without specifying a value, pass
       withAttribute.ANY_VALUE as the value.
       """
    if args:
        attrs = args[:]
    else:
        attrs = list(attrDict.items())
    attrs = [(k,v) for k,v in attrs]
    def pa(s,l,tokens):
        for attrName,attrValue in attrs:
            if attrName not in tokens:
                raise ParseException(s,l,"no matching attribute " + attrName)
            if attrValue != withAttribute.ANY_VALUE and tokens[attrName] != attrValue:
                raise ParseException(s,l,"attribute '%s' has value '%s', must be '%s'" %
                                            (attrName, tokens[attrName], attrValue))
    return pa
withAttribute.ANY_VALUE = object()

opAssoc = _Constants()
opAssoc.LEFT = object()
opAssoc.RIGHT = object()

def operatorPrecedence( baseExpr, opList ):
    """Helper method for constructing grammars of expressions made up of
       operators working in a precedence hierarchy.  Operators may be unary or
       binary, left- or right-associative.  Parse actions can also be attached
       to operator expressions.

       Parameters:
        - baseExpr - expression representing the most basic element for the nested
        - opList - list of tuples, one for each operator precedence level in the
          expression grammar; each tuple is of the form
          (opExpr, numTerms, rightLeftAssoc, parseAction), where:
           - opExpr is the pyparsing expression for the operator;
              may also be a string, which will be converted to a Literal;
              if numTerms is 3, opExpr is a tuple of two expressions, for the
              two operators separating the 3 terms
           - numTerms is the number of terms for this operator (must
              be 1, 2, or 3)
           - rightLeftAssoc is the indicator whether the operator is
              right or left associative, using the pyparsing-defined
              constants opAssoc.RIGHT and opAssoc.LEFT.
           - parseAction is the parse action to be associated with
              expressions matching this operator expression (the
              parse action tuple member may be omitted)
    """
    ret = Forward()
    lastExpr = baseExpr | ( Suppress('(') + ret + Suppress(')') )
    for i,operDef in enumerate(opList):
        opExpr,arity,rightLeftAssoc,pa = (operDef + (None,))[:4]
        if arity == 3:
            if opExpr is None or len(opExpr) != 2:
                raise ValueError("if numterms=3, opExpr must be a tuple or list of two expressions")
            opExpr1, opExpr2 = opExpr
        thisExpr = Forward()#.setName("expr%d" % i)
        if rightLeftAssoc == opAssoc.LEFT:
            if arity == 1:
                matchExpr = FollowedBy(lastExpr + opExpr) + Group( lastExpr + OneOrMore( opExpr ) )
            elif arity == 2:
                if opExpr is not None:
                    matchExpr = FollowedBy(lastExpr + opExpr + lastExpr) + Group( lastExpr + OneOrMore( opExpr + lastExpr ) )
                else:
                    matchExpr = FollowedBy(lastExpr+lastExpr) + Group( lastExpr + OneOrMore(lastExpr) )
            elif arity == 3:
                matchExpr = FollowedBy(lastExpr + opExpr1 + lastExpr + opExpr2 + lastExpr) + \
                            Group( lastExpr + opExpr1 + lastExpr + opExpr2 + lastExpr )
            else:
                raise ValueError("operator must be unary (1), binary (2), or ternary (3)")
        elif rightLeftAssoc == opAssoc.RIGHT:
            if arity == 1:
                # try to avoid LR with this extra test
                if not isinstance(opExpr, Optional):
                    opExpr = Optional(opExpr)
                matchExpr = FollowedBy(opExpr.expr + thisExpr) + Group( opExpr + thisExpr )
            elif arity == 2:
                if opExpr is not None:
                    matchExpr = FollowedBy(lastExpr + opExpr + thisExpr) + Group( lastExpr + OneOrMore( opExpr + thisExpr ) )
                else:
                    matchExpr = FollowedBy(lastExpr + thisExpr) + Group( lastExpr + OneOrMore( thisExpr ) )
            elif arity == 3:
                matchExpr = FollowedBy(lastExpr + opExpr1 + thisExpr + opExpr2 + thisExpr) + \
                            Group( lastExpr + opExpr1 + thisExpr + opExpr2 + thisExpr )
            else:
                raise ValueError("operator must be unary (1), binary (2), or ternary (3)")
        else:
            raise ValueError("operator must indicate right or left associativity")
        if pa:
            matchExpr.setParseAction( pa )
        thisExpr << ( matchExpr | lastExpr )
        lastExpr = thisExpr
    ret << lastExpr
    return ret

dblQuotedString = Regex(r'"(?:[^"\n\r\\]|(?:"")|(?:\\x[0-9a-fA-F]+)|(?:\\.))*"').setName("string enclosed in double quotes")
sglQuotedString = Regex(r"'(?:[^'\n\r\\]|(?:'')|(?:\\x[0-9a-fA-F]+)|(?:\\.))*'").setName("string enclosed in single quotes")
quotedString = Regex(r'''(?:"(?:[^"\n\r\\]|(?:"")|(?:\\x[0-9a-fA-F]+)|(?:\\.))*")|(?:'(?:[^'\n\r\\]|(?:'')|(?:\\x[0-9a-fA-F]+)|(?:\\.))*')''').setName("quotedString using single or double quotes")
unicodeString = Combine(_L('u') + quotedString.copy())

def nestedExpr(opener="(", closer=")", content=None, ignoreExpr=quotedString):
    """Helper method for defining nested lists enclosed in opening and closing
       delimiters ("(" and ")" are the default).

       Parameters:
        - opener - opening character for a nested list (default="("); can also be a pyparsing expression
        - closer - closing character for a nested list (default=")"); can also be a pyparsing expression
        - content - expression for items within the nested lists (default=None)
        - ignoreExpr - expression for ignoring opening and closing delimiters (default=quotedString)

       If an expression is not provided for the content argument, the nested
       expression will capture all whitespace-delimited content between delimiters
       as a list of separate values.

       Use the ignoreExpr argument to define expressions that may contain
       opening or closing characters that should not be treated as opening
       or closing characters for nesting, such as quotedString or a comment
       expression.  Specify multiple expressions using an Or or MatchFirst.
       The default is quotedString, but if no expressions are to be ignored,
       then pass None for this argument.
    """
    if opener == closer:
        raise ValueError("opening and closing strings cannot be the same")
    if content is None:
        if isinstance(opener,str) and isinstance(closer,str):
            if len(opener) == 1 and len(closer)==1:
                if ignoreExpr is not None:
                    content = (Combine(OneOrMore(~ignoreExpr +
                                    CharsNotIn(opener+closer+ParserElement.DEFAULT_WHITE_CHARS,exact=1))
                                ).setParseAction(lambda t:t[0].strip()))
                else:
                    content = (empty+CharsNotIn(opener+closer+ParserElement.DEFAULT_WHITE_CHARS
                                ).setParseAction(lambda t:t[0].strip()))
            else:
                if ignoreExpr is not None:
                    content = (Combine(OneOrMore(~ignoreExpr + 
                                    ~Literal(opener) + ~Literal(closer) +
                                    CharsNotIn(ParserElement.DEFAULT_WHITE_CHARS,exact=1))
                                ).setParseAction(lambda t:t[0].strip()))
                else:
                    content = (Combine(OneOrMore(~Literal(opener) + ~Literal(closer) +
                                    CharsNotIn(ParserElement.DEFAULT_WHITE_CHARS,exact=1))
                                ).setParseAction(lambda t:t[0].strip()))
        else:
            raise ValueError("opening and closing arguments must be strings if no content expression is given")
    ret = Forward()
    if ignoreExpr is not None:
        ret << Group( Suppress(opener) + ZeroOrMore( ignoreExpr | ret | content ) + Suppress(closer) )
    else:
        ret << Group( Suppress(opener) + ZeroOrMore( ret | content )  + Suppress(closer) )
    return ret

def indentedBlock(blockStatementExpr, indentStack, indent=True):
    """Helper method for defining space-delimited indentation blocks, such as
       those used to define block statements in Python source code.

       Parameters:
        - blockStatementExpr - expression defining syntax of statement that
            is repeated within the indented block
        - indentStack - list created by caller to manage indentation stack
            (multiple statementWithIndentedBlock expressions within a single grammar
            should share a common indentStack)
        - indent - boolean indicating whether block must be indented beyond the
            the current level; set to False for block of left-most statements
            (default=True)

       A valid block must contain at least one blockStatement.
    """
    def checkPeerIndent(s,l,t):
        if l >= len(s): return
        curCol = col(l,s)
        if curCol != indentStack[-1]:
            if curCol > indentStack[-1]:
                raise ParseFatalException(s,l,"illegal nesting")
            raise ParseException(s,l,"not a peer entry")

    def checkSubIndent(s,l,t):
        curCol = col(l,s)
        if curCol > indentStack[-1]:
            indentStack.append( curCol )
        else:
            raise ParseException(s,l,"not a subentry")

    def checkUnindent(s,l,t):
        if l >= len(s): return
        curCol = col(l,s)
        if not(indentStack and curCol < indentStack[-1] and curCol <= indentStack[-2]):
            raise ParseException(s,l,"not an unindent")
        indentStack.pop()

    NL = OneOrMore(LineEnd().setWhitespaceChars("\t ").suppress())
    INDENT = Empty() + Empty().setParseAction(checkSubIndent)
    PEER   = Empty().setParseAction(checkPeerIndent)
    UNDENT = Empty().setParseAction(checkUnindent)
    if indent:
        smExpr = Group( Optional(NL) +
            FollowedBy(blockStatementExpr) +
            INDENT + (OneOrMore( PEER + Group(blockStatementExpr) + Optional(NL) )) + UNDENT)
    else:
        smExpr = Group( Optional(NL) +
            (OneOrMore( PEER + Group(blockStatementExpr) + Optional(NL) )) )
    blockStatementExpr.ignore(_bslash + LineEnd())
    return smExpr

alphas8bit = srange(r"[\0xc0-\0xd6\0xd8-\0xf6\0xf8-\0xff]")
punc8bit = srange(r"[\0xa1-\0xbf\0xd7\0xf7]")

# anyOpenTag,anyCloseTag = makeHTMLTags(Word(alphas,alphanums+"_:"))
commonHTMLEntity = Combine(_L("&") + oneOf("gt lt amp nbsp quot").setResultsName("entity") +";").streamline()
_htmlEntityMap = dict(list(zip("gt lt amp nbsp quot".split(),'><& "')))
replaceHTMLEntity = lambda t : t.entity in _htmlEntityMap and _htmlEntityMap[t.entity] or None

# it's easy to get these comment structures wrong - they're very common, so may as well make them available
cStyleComment = Regex(r"/\*(?:[^*]*\*+)+?/").setName("C style comment")

htmlComment = Regex(r"<!--[\s\S]*?-->")
restOfLine = Regex(r".*").leaveWhitespace()
dblSlashComment = Regex(r"\/\/(\\\n|.)*").setName("// comment")
cppStyleComment = Regex(r"/(?:\*(?:[^*]*\*+)+?/|/[^\n]*(?:\n[^\n]*)*?(?:(?<!\\)|\Z))").setName("C++ style comment")

javaStyleComment = cppStyleComment
pythonStyleComment = Regex(r"#.*").setName("Python style comment")
_noncomma = "".join( [ c for c in printables if c != "," ] )
_commasepitem = Combine(OneOrMore(Word(_noncomma) +
                                  Optional( Word(" \t") +
                                            ~Literal(",") + ~LineEnd() ) ) ).streamline().setName("commaItem")
commaSeparatedList = delimitedList( Optional( quotedString | _commasepitem, default="") ).setName("commaSeparatedList")


if __name__ == "__main__":

    def test( teststring ):
        try:
            tokens = simpleSQL.parseString( teststring )
            tokenlist = tokens.asList()
            print((teststring + "->"   + str(tokenlist)))
            print(("tokens = "         + str(tokens)))
            print(("tokens.columns = " + str(tokens.columns)))
            print(("tokens.tables = "  + str(tokens.tables)))
            print((tokens.asXML("SQL",True)))
        except ParseBaseException as err:
            print((teststring + "->"))
            print((err.line))
            print((" "*(err.column-1) + "^"))
            print (err)
        print()

    selectToken    = CaselessLiteral( "select" )
    fromToken      = CaselessLiteral( "from" )

    ident          = Word( alphas, alphanums + "_$" )
    columnName     = delimitedList( ident, ".", combine=True ).setParseAction( upcaseTokens )
    columnNameList = Group( delimitedList( columnName ) )#.setName("columns")
    tableName      = delimitedList( ident, ".", combine=True ).setParseAction( upcaseTokens )
    tableNameList  = Group( delimitedList( tableName ) )#.setName("tables")
    simpleSQL      = ( selectToken + \
                     ( '*' | columnNameList ).setResultsName( "columns" ) + \
                     fromToken + \
                     tableNameList.setResultsName( "tables" ) )

    test( "SELECT * from XYZZY, ABC" )
    test( "select * from SYS.XYZZY" )
    test( "Select A from Sys.dual" )
    test( "Select AA,BB,CC from Sys.dual" )
    test( "Select A, B, C from Sys.dual" )
    test( "Select A, B, C from Sys.dual" )
    test( "Xelect A, B, C from Sys.dual" )
    test( "Select A, B, C frox Sys.dual" )
    test( "Select" )
    test( "Select ^^^ frox Sys.dual" )
    test( "Select A, B, C from Sys.dual, Table2   " )
