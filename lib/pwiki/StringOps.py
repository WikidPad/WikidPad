## -*- coding: ISO-8859-1 -*-

"""
Various string operations, like unicode encoding/decoding,
creating diff information for plain byte sequences
"""



import threading

from struct import pack, unpack

import difflib, codecs, os.path, random

import urllib_red as urllib

from codecs import BOM_UTF8, BOM_UTF16_BE, BOM_UTF16_LE

from Utilities import DUMBTHREADHOLDER

import srePersistent as _re

LINEEND_SPLIT_RE = _re.compile(r"\r\n?|\n")


from Configuration import isUnicode, isOSX, isLinux, isWindows, isWin9x


# To generate dependencies for py2exe/py2app
import encodings.utf_8, encodings.latin_1, encodings.utf_16, \
        encodings.utf_16_be, encodings.utf_16_le



# ---------- Encoding conversion ----------


utf8Enc = codecs.getencoder("utf-8")
utf8Dec = codecs.getdecoder("utf-8")
utf8Reader = codecs.getreader("utf-8")
utf8Writer = codecs.getwriter("utf-8")

def convertLineEndings(text, newLe):
    """
    Convert line endings of text to string newLe which should be
    "\n", "\r" or "\r\n". If newLe or text is unicode, the result
    will be unicode, too.
    """
    return newLe.join(LINEEND_SPLIT_RE.split(text))

def lineendToInternal(text):
    return convertLineEndings(text, "\n")
    


if isOSX():
    # generate dependencies for py2app
    import encodings.mac_roman
    mbcsEnc = codecs.getencoder("mac_roman")
    _mbcsDec = codecs.getdecoder("mac_roman")
    mbcsReader = codecs.getreader("mac_roman")
    mbcsWriter = codecs.getwriter("mac_roman")
    
    def lineendToOs(text):
        return convertLineEndings(text, "\r")

elif isLinux():
    # Could be wrong encoding
    mbcsEnc = codecs.getencoder("latin-1")
    _mbcsDec = codecs.getdecoder("latin-1")
    mbcsReader = codecs.getreader("latin-1")
    mbcsWriter = codecs.getwriter("latin-1")

    def lineendToOs(text):
        return convertLineEndings(text, "\n")

else:
    # generate dependencies for py2exe
    import encodings.ascii
    import encodings.mbcs
    mbcsEnc = codecs.getencoder("mbcs")
    _mbcsDec = codecs.getdecoder("mbcs")
    mbcsReader = codecs.getreader("mbcs")
    mbcsWriter = codecs.getwriter("mbcs")

    # TODO This is suitable for Windows only
    def lineendToOs(text):
        return convertLineEndings(text, "\r\n")


def mbcsDec(input, errors="strict"):
    if isinstance(input, unicode):
        return input, len(input)
    else:
        return _mbcsDec(input, errors)


if isWindows() and not isWin9x():
    def dummy(s, e=""):
        return s, len(s)

    pathEnc = dummy
    pathDec = dummy
else:
    pathEnc = mbcsEnc
    pathDec = mbcsDec


if isUnicode():
    def uniToGui(text):
        """
        Convert unicode text to a format usable for wx GUI
        """
        return text   # Nothing to do
        
    def guiToUni(text):
        """
        Convert wx GUI string format to unicode
        """
        return text   # Nothing to do
else:
    def uniToGui(text):
        """
        Convert unicode text to a format usable for wx GUI
        """
        return mbcsEnc(text, "replace")[0]
        
    def guiToUni(text):
        """
        Convert wx GUI string format to unicode
        """
        return mbcsDec(text, "replace")[0]


def unicodeToCompFilename(us):
    """
    Encode a unicode filename to a filename compatible to (hopefully)
    any filesystem encoding by converting unicode to '=xx' for
    characters up to 255 and '$xxxx' above. Each 'x represents a hex
    character
    """
    result = []
    for c in us:
        if ord(c) > 255:
            result.append("$%04x" % ord(c))
            continue
        if c in u"0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"+\
                u"{}[]()+-*_,.%":   # Allowed characters
            result.append(str(c))
            continue
        
        result.append("=%02x" % ord(c))
        
    return "".join(result)


def strToBool(s, default=False):
    """
    Try to interpret string (or unicode) s as
    boolean, return default if string can't be
    interpreted
    """
    
    if s is None:
        return default
    
    # Try to interpret as integer
    try:
        return int(s) != 0
    except ValueError:
        # Not an integer
        s = s.lower()
        if s in (u"true", u"yes"):
            return True
        if s in (u"false", u"no"):
            return False
            
        return default


# TODO More formats
def fileContentToUnicode(content):
    """
    Try to detect the text encoding of content
    and return converted unicode
    """
    if content.startswith(BOM_UTF8):
        return utf8Dec(content[len(BOM_UTF8):], "replace")[0]
    else:
        return mbcsDec(content, "replace")[0]
        
        
def wikiWordToLabel(word):
    """
    Strip '[' and ']' if non camelcase word and return it
    """
    if word.startswith(u"[") and word.endswith(u"]"):
        return word[1:-1]
    return word


def removeBracketsFilename(fn):
    n, ext = os.path.splitext(fn)
    return wikiWordToLabel(n) + ext


def revStr(s):
    """
    Return reversed string
    """
    s = list(s)
    s.reverse()
    return u"".join(s)
    
def splitkeep(s, delim):
    """
    Similar to split, but keeps the delimiter as separate element, e.g.
    splitkeep("aaabaaabaa", "b") -> ["aaa", "b", "aaa", "b", "aa"]
    """
    result = []
    for e in s.split(delim):
        result.append(e)
        result.append(delim)
        
    return result[:-1]


def splitIndent(text):
    """
    Return tuple (t, d) where d is deepness of indentation and t is text
    without the indentation
    """
    pl = len(text)
    text = text.lstrip()
    return (text, pl-len(text))


def matchWhole(reObj, s):
    """
    reObj -- Compiled regular expression
    s -- String to match
    
    Similar to reObj.match(s), but returns MatchObject only if the 
    whole string s is covered by the match, returns None otherwise
    """
    mat = reObj.match(s)
    if not mat:
        return None
    if mat.end(0) < len(s):
        return None
        
    return mat
    


## Copied from xml.sax.saxutils and modified to reduce dependencies
def escapeHtml(data):
    """
    Escape &, <, > and line breaks in a unicode string of data.
    """

    # must do ampersand first

    return data.replace(u"&", u"&amp;").replace(u">", u"&gt;").\
            replace(u"<", u"&lt;").replace(u"\n", u"<br />\n")


def escapeHtmlNoBreaks(data):
    """
    Escape &, <, and > (no line breaks) in a unicode string of data.
    """

    # must do ampersand first

    return data.replace(u"&", u"&amp;").replace(u">", u"&gt;").\
            replace(u"<", u"&lt;")


def escapeForIni(text, toEscape=u""):
    """
    Return an escaped version of string. Always escaped will be backslash and
    all characters with ASCII value < 32. Additional characters can be given in
    the toEscape parameter (as unicode string, only characters < 128).
    
    Returns: unicode string
    """
    # Escape '\' and for readability escape \r \n \f and \t separately
    text = text.replace(u"\\", u"\\x%02x" % ord("\\"))
    
    # Escape everything with ord < 32
    for i in xrange(32):
        text = text.replace(unichr(i), u"\\x%02x" % i)
        
    for c in toEscape:
        text = text.replace(c, u"\\x%02x" % ord(c))
    
    return text


def _unescapeForIniHelper(match):
    return unichr(int(match.group(1), 16))

def unescapeForIni(text):
    """
    Inverse of escapeForIni()
    """
    return _re.sub(ur"\\x([0-9a-f]{2})", _unescapeForIniHelper, text)    


def escapeWithRe(text):
    return text.replace(u"\\", u"\\\\").replace("\n", "\\n").\
            replace("\r", "\\r")

def unescapeWithRe(text):
    """
    Unescape things like \n or \f. Throws exception if unescaping fails
    """
    return _re.sub(u"", text, u"", 1)


def re_sub_escape(pattern):
    """
    Escape the replacement pattern for a re.sub function
    """
    return pattern.replace(u"\\", u"\\\\")


def htmlColorToRgbTuple(html):
    """
    Calculate RGB integer tuple from html '#hhhhhh' format string.
    Returns None in case of an error
    """
    if len(html) != 7 or html[0] != "#":
        return None
    try:
        r = int(html[1:3], 16)
        g = int(html[3:5], 16)
        b = int(html[5:7], 16)
        return (r, g, b)
    except:
        return None
        
def rgbToHtmlColor(r, g, b):
    """
    Return HTML color '#hhhhhh' format string.
    """
    return "#%02X%02X%02X" % (r, g, b)
    
    
def splitpath(path):
    """
    Cut a path into all of its pieces, starting with drive name, through
    all path components up to the name of the file (if any).
    Returns a list of the elements, first and/or last element may be
    empty strings.
    Maybe use os.path.abspath before calling it
    """
    dr, path = os.path.splitdrive(path)
    result = []
    while True:
        head, last = os.path.split(path)
        if head == path: break
        result.append(last)
        path = head
    result.append(dr)
    result.reverse()
    return result


def relativeFilePath(location, toFilePath):
    """
    Returns a relative (if possible) path to address the file
    toFilePath if you are in directory location.
    Both parameters should be normalized with os.path.abspath
    
    Function returns None if an absolute path is needed!

    location -- Directory where you are
    toFilePath -- absolute path to file you want to reach
    """
    locParts = splitpath(location)
    if locParts[-1] == "":
        del locParts[-1]
    
    locLen = len(locParts)
    fileParts = splitpath(toFilePath)
    
    for i in xrange(len(locParts)):
        if len(fileParts) == 0:
            break  # TODO Error ???

        if locParts[0] != fileParts[0]:
            break

        del locParts[0]
        del fileParts[0]

    result = []
    
    if len(locParts) == locLen:
        # Nothing matches at all, absolute path needed
        return None

    if len(locParts) > 0:
        # go back some steps
        result += [".."] * len(locParts)
    
    result += fileParts
    
    return os.path.join(*result)



_URL_RESERVED = frozenset((u";", u"?", u":", u"@", u"&", u"=", u"+", u",", u"/"))
        
def urlQuote(s, safe='/'):
    """
    Modified version of urllib.quote
    
    Each part of a URL, e.g. the path info, the query, etc., has a
    different set of reserved characters that must be quoted.

    RFC 2396 Uniform Resource Identifiers (URI): Generic Syntax lists
    the following reserved characters.

    reserved    = ";" | "/" | "?" | ":" | "@" | "&" | "=" | "+" |
                  "$" | ","

    Each of these characters is reserved in some component of a URL,
    but not necessarily in all of them.

    The function is intended for quoting the path
    section of a URL.  Thus, it will not encode '/'.  This character
    is reserved, but in typical usage the quote function is being
    called on a path where the existing slash characters are used as
    reserved characters.
    """
    result = []
    
    for c in s:
        if c not in safe and (ord(c) < 33 or c in _URL_RESERVED):
            result.append("%%%02X" % ord(c))
        else:
            result.append(c)

    return "".join(result)


def ntUrlFromPathname(p):
    r"""
    Modified version of nturl2path.pathname2url.

    Convert a DOS/Windows path name to a file url.

            C:\foo\bar\spam.foo

                    becomes

            ///C|/foo/bar/spam.foo
    """
    if not ':' in p:
        # No drive specifier, just convert slashes and quote the name
        if p[:2] == '\\\\':
        # path is something like \\host\path\on\remote\host
        # convert this to ////host/path/on/remote/host
        # (notice doubling of slashes at the start of the path)
            p = '\\\\' + p
        components = p.split('\\')
        return urlQuote('/'.join(components))
    comp = p.split(':')
    if len(comp) != 2 or len(comp[0]) > 1:
        error = 'Bad path: ' + p
        raise IOError, error

    drive = urlQuote(comp[0].upper())
    components = comp[1].split('\\')
    path = '///' + drive + '|'
    for comp in components:
        if comp:
            path = path + '/' + urlQuote(comp)
    return path


def _macpncomp2url(component):
    component = urlQuote(component[:31], safe='')  # We want to quote slashes
    return component

def macUrlFromPathname(pathname):
    """
    Modified version of macurl2path.pathname2url.

    convert mac pathname to /-delimited pathname
    """
    if '/' in pathname:
        raise RuntimeError, "Cannot convert pathname containing slashes"
    components = pathname.split(':')
    # Remove empty first and/or last component
    if components[0] == '':
        del components[0]
    if components[-1] == '':
        del components[-1]
    # Replace empty string ('::') by .. (will result in '/../' later)
    for i in range(len(components)):
        if components[i] == '':
            components[i] = '..'
    # Truncate names longer than 31 bytes
    components = map(_macpncomp2url, components)

    if os.path.isabs(pathname):
        return '/' + '/'.join(components)
    else:
        return '/'.join(components)


if os.name == 'nt':
    urlFromPathname = ntUrlFromPathname
elif os.name == 'mac':
    urlFromPathname = macUrlFromPathname
else:
    def urlFromPathname(fn):
        # TODO Really do this for non-Windows systems?
    
        if isinstance(fn, unicode):
            fn = utf8Enc(fn, "replace")[0]
            
        url = urllib.pathname2url(fn)
        url.replace("%24", "$")
    
        return url



_RNDBASESEQ = "1234567890abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"

def createRandomString(length):
    """
    Create a unicode string of random characters and digits
    """
    return u"".join([random.choice(_RNDBASESEQ) for i in xrange(length)])



def boolToChar(b):
    if b:
        return "1"
    else:
        return "\0"
        
def charToBool(c):
    return c != "\0"

def boolToInt(b):
    if b:
        return 1
    else:
        return 0
    

def strToBin(s):
    """
    s -- String to convert to binary (NOT unicode!)
    """
    return pack(">I", len(s)) + s   # Why big-endian? Why not?
    
def binToStr(b):
    """
    Returns tuple (s, br) with string s and rest of the binary data br
    """
    l = unpack(">I", b[:4])[0]
    s = b[4 : 4+l]
    br = b[4+l : ]
    return (s, br)




# ---------- Breaking text into tokens ----------

class Token(object):
    """
    The class has the following members:
        
    ttype - Token type number (one of the "FormatTypes" enumeration numbers
        in "WikiFormatting.py")
    start - Character position of the token start in page
    grpdict - Dictionary of the regular expression groups 
    text - Actual text content of token
    node - object derived from "Ast" class in "PageAst.py" if further
        data must be stored or None.
    """
    __slots__ = ("__weakref__", "ttype", "start", "grpdict", "text", "node")
    
    def __init__(self, ttype, start, grpdict, text, node=None):
        self.ttype = ttype
        self.start = start
        self.grpdict = grpdict
        self.text = text
        self.node = node
        
    def __repr__(self):
        return u"Token(%s, %s, %s, <dict>, %s)" % (repr(self.ttype),
                repr(self.start), repr(self.text), repr(self.node))


    def getRealLength(self):
        """
        If node object exist, it is asked for length. If it returns -1 or
        doesn't exist at all, length of self.text is returned.
        """
        result = -1
        
        if self.node is not None:
            result = self.node.getLength()
        
        if result == -1:
            result = len(self.text)
            
        return result


    def getRealText(self):
        """
        If node object exist, it is asked for text. If it returns None or
        doesn't exist at all, self.text is returned.
        """
        result = None
        if self.node is not None:
            result = self.node.getText()

        if result == None:
            result = self.text


    def shallowCopy(self):
        return Token(self.ttype, self.start, self.grpdict, self.text, self.node)

    

class TokenIterator:
    """
    Tokenizer with iterator mechanism
    """
    def __init__(self, tokenre, formatMap, defaultType, text, charPos=0,
            tokenStartOffset=0):
        """
        charPos -- start position in text where to start
        tokenStartOffset -- offset to add to token.start value before returning token
        """
        self.tokenre = tokenre
        self.formatMap = formatMap
        self.defaultType = defaultType
        self.text = text
        self.charPos = charPos
        self.tokenStartOffset = tokenStartOffset
        self.nextMatch = None  # Stores an already found match to speed up things

    def __iter__(self):
        return self
        
    def setCharPos(charPos):
        self.charPos = charPos
        
    def getCharPos(self):
        return self.charPos


    def next(self):
        textlen = len(self.text)
        if self.charPos >= textlen:
            raise StopIteration()

        # Try to get cached nextMatch
        if self.nextMatch:
            mat = self.nextMatch
            self.nextMatch = None
        else:
            mat = self.tokenre.search(self.text, self.charPos)

        if mat is None:
#                     print "tokenize3", repr((defaultType, charpos, None,
#                             text[charpos:textlen]))

            cp = self.charPos
            self.charPos = textlen
            return Token(self.defaultType, cp + self.tokenStartOffset, None,
                    self.text[cp:textlen])
            
#                 print "tokenize4", repr((defaultType, textlen, None,
#                         u""))
#             result.append(Token(self.defaultType, textlen, None, u""))
#             break

        start, end = mat.span()
        if self.charPos < start:
#                         print "tokenize7", repr((defaultType, charpos, None,
#                                 text[charpos:start]))
            self.nextMatch = mat
            cp = self.charPos
            self.charPos = start
            return Token(self.defaultType, cp + self.tokenStartOffset, None,
                    self.text[cp:start])                   


        groupdict = mat.groupdict()
        for m in groupdict.keys():
            if not groupdict[m] is None and m.startswith(u"style"):
                # m is of the form:   style<index>
                index = int(m[5:])

#                     print "tokenize8", repr((formatMap[index], charpos, groupdict,
#                             text[start:end]))
                cp = self.charPos
                self.charPos = end
                return Token(self.formatMap[index], cp + self.tokenStartOffset,
                        groupdict, self.text[start:end])


class Tokenizer:
    def __init__(self, tokenre, defaultType):
        self.tokenre = tokenre
        self.defaultType = defaultType

#         self.tokenThread = None
# 
#     def setTokenThread(self, tt):
#         self.tokenThread = tt
# 
#     def getTokenThread(self):
#         return self.tokenThread

    def tokenize(self, text, formatMap, defaultType, threadholder=DUMBTHREADHOLDER):
        result = []
        if not threadholder.isCurrent():
            return result

        it = TokenIterator(self.tokenre, formatMap, defaultType, text)
        
        for t in it:
            result.append(t)
            if not threadholder.isCurrent():
                break
                
        return result



#         textlen = len(text)
#         result = []
#         charpos = 0    
#         
#         while True:
#             mat = self.tokenre.search(text, charpos)
#             if mat is None:
#                 if charpos < textlen:
# #                     print "tokenize3", repr((defaultType, charpos, None,
# #                             text[charpos:textlen]))
#                     result.append(Token(defaultType, charpos, None,
#                             text[charpos:textlen]))
#                 
# #                 print "tokenize4", repr((defaultType, textlen, None,
# #                         u""))
#                 result.append(Token(defaultType, textlen, None, u""))
#                 break
#     
#             groupdict = mat.groupdict()
#             for m in groupdict.keys():
#                 if not groupdict[m] is None and m.startswith(u"style"):
#                     start, end = mat.span()
#                     
#                     # m is of the form:   style<index>
#                     index = int(m[5:])
#                     if charpos < start:
# #                         print "tokenize7", repr((defaultType, charpos, None,
# #                                 text[charpos:start]))
#                         result.append(Token(defaultType, charpos, None,
#                                 text[charpos:start]))                    
#                         charpos = start
#     
# #                     print "tokenize8", repr((formatMap[index], charpos, groupdict,
# #                             text[start:end]))
#                     result.append(Token(formatMap[index], charpos, groupdict,
#                             text[start:end]))
#                     charpos = end
#                     break
#     
#             if not threadholder.isCurrent():
#                 break
# 
#         return result



# ---------- Handling diff information ----------


def difflibToCompact(ops, b):
    """
    Rewrite sequence of op_codes returned by difflib.SequenceMatcher.get_opcodes
    to the compact opcode format.

    0: replace,  1: delete,  2: insert

    b -- second string to match
    """
    result = []
    # ops.reverse()
    for tag, i1, i2, j1, j2 in ops:
        if tag == "equal":
            continue
        elif tag == "replace":
            result.append((0, i1, i2, b[j1:j2]))
        elif tag == "delete":
            result.append((1, i1, i2))
        elif tag == "insert":
            result.append((2, i1, b[j1:j2]))

    return result


def compactToBinCompact(cops):
    """
    Compress the ops to a compact binary format to store in the database
    as blob
    """
    result = []
    for op in cops:
        if op[0] == 0:
            result.append( pack("<Biii", 0, op[1], op[2], len(op[3])) )
            result.append(op[3])
        elif op[0] == 1:
            result.append( pack("<Bii", *op) )
        elif op[0] == 2:
            result.append( pack("<Bii", 2, op[1], len(op[2])) )
            result.append(op[2])

    return "".join(result)



def binCompactToCompact(bops):
    """
    Uncompress the ops from the binary format
    """
    pos = 0
    result = []
    while pos < len(bops):
        t = ord(bops[pos])
        pos += 1
        if t == 0:
            d = unpack("<iii", bops[pos:pos+12])
            pos += 12
            s = bops[pos:pos+d[2]]
            pos += d[2]
            
            result.append( (0, d[0], d[1], s) )
        elif t == 1:
            d = unpack("<ii", bops[pos:pos+8])
            pos += 8
            
            result.append( (1, d[0], d[1]) )
        elif t == 2:
            d = unpack("<ii", bops[pos:pos+8])
            pos += 8
            s = bops[pos:pos+d[1]]
            pos += d[1]
            
            result.append( (2, d[0], s) )

    return result            


def applyCompact(a, cops):
    """
    Apply compact ops to string a to create and return string b
    """
    result = []
    apos = 0
    for op in cops:
        if apos < op[1]:
            result.append(a[apos:op[1]])  # equal

        if op[0] == 0:
            result.append(op[3])
            apos = op[2]
        elif op[0] == 1:
            apos = op[2]
        elif op[0] == 2:
            result.append(op[2])
            apos = op[1]

    if apos < len(a):
        result.append(a[apos:])  # equal

    return "".join(result)


def applyBinCompact(a, bops):
    """
    Apply binary diff operations bops to a to create b
    """
    return applyCompact(a, binCompactToCompact(bops))


def getBinCompactForDiff(a, b):
    """
    Return the binary compact codes to change string a to b.
    For strings a and b (NOT unicode) it is true that
        applyBinCompact(a, getBinCompactForDiff(a, b)) == b
    """

    sm = difflib.SequenceMatcher(None, a, b)
    ops = sm.get_opcodes()
    return compactToBinCompact(difflibToCompact(ops, b))

