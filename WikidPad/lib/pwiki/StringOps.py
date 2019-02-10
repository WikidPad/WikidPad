## -*- coding: ISO-8859-1 -*-

"""
Various string operations, like unicode encoding/decoding,
creating diff information for plain byte sequences
"""

import os, traceback

from struct import pack, unpack

import difflib, codecs, os.path, random, base64, locale, hashlib, tempfile, \
        math, time

# import urllib_red as urllib
import urllib.request, urllib.parse, urllib.error, urllib.parse, cgi

from codecs import BOM_UTF8, BOM_UTF16_BE, BOM_UTF16_LE

import wx

import re as _re # import pwiki.srePersistent as reimport pwiki.srePersistent as _re
from .WikiExceptions import *
from Consts import BYTETYPES

from . import Utilities, MyersUkkonenDiff

from .SystemInfo import isOSX, isLinux, isWindows


# To generate dependencies for py2exe/py2app
import encodings.utf_8, encodings.latin_1, encodings.utf_16, \
        encodings.utf_16_be, encodings.utf_16_le, encodings.ascii



LINEEND_SPLIT_RE_STR = _re.compile(r"\r\n?|\n")
LINEEND_SPLIT_RE_BYTES = _re.compile(br"\r\n?|\n")



# ---------- Encoding conversion ----------


utf8Enc = codecs.getencoder("utf-8")
utf8Dec = codecs.getdecoder("utf-8")
utf8Reader = codecs.getreader("utf-8")
utf8Writer = codecs.getwriter("utf-8")

def convertLineEndings(text, newLe):
    """
    Convert line endings of text to string newLe which should be
    "\n", "\r" or "\r\n". If text is bytes/unicode, the result
    will be bytes/unicode, too.
    """

    if isinstance(text, BYTETYPES):
        if isinstance(newLe, str):
            newLe = newLe.encode("latin-1")
        
        return newLe.join(LINEEND_SPLIT_RE_BYTES.split(text))
    else:
        if isinstance(newLe, BYTETYPES):
            newLe = newLe.decode("latin-1")
        
        return newLe.join(LINEEND_SPLIT_RE_STR.split(text))



def lineendToInternal(text):
    return convertLineEndings(text, b"\n")

def lineendToOs(text):
    return convertLineEndings(text, os.linesep)




if isOSX():
    # generate dependencies for py2app
    import encodings.mac_roman
    
    MBCS_ENCODING = "mac_roman"

elif isLinux():
    # Could be wrong encoding
#     MBCS_ENCODING = "latin-1"
#     MBCS_ENCODING = "utf8"
    MBCS_ENCODING = locale.getpreferredencoding()

    if not MBCS_ENCODING:
        MBCS_ENCODING = "utf-8"
        
else:
    # generate dependencies for py2exe
    import encodings.ascii
    import encodings.mbcs

    MBCS_ENCODING = "mbcs"


_mbcsEnc = codecs.getencoder(MBCS_ENCODING)
_mbcsDec = codecs.getdecoder(MBCS_ENCODING)
mbcsReader = codecs.getreader(MBCS_ENCODING)
mbcsWriter = codecs.getwriter(MBCS_ENCODING)



# mbcsEnc is idempotent for the first item of returned tuple
# pathEnc and longPathEnc are also idempotent
# (f is idempotent iff f(x) == f(f(x)) for all x)


def mbcsEnc(input, errors="strict"):
    if isinstance(input, BYTETYPES):
        return input, len(input)
    else:
        return _mbcsEnc(input, errors)


def mbcsDec(input, errors="strict"):
    if isinstance(input, str):
        return input, len(input)
    else:
        return _mbcsDec(input, errors)



if os.path.supports_unicode_filenames:
    def dummy(s):
        return s

    pathEnc = dummy
    pathDec = dummy
else:
    def pathEnc(s):
        if s is None:
            return None
        return mbcsEnc(s, "replace")[0]

    def pathDec(s):
        if s is None:
            return None
        return mbcsDec(s, "replace")[0]


if isWindows():
    if not os.path.supports_unicode_filenames:
        raise InternalError("This Python version does not support unicode paths")
    
    # To process paths longer than 255 characters, Windows (NT and following)
    # expects an absolute path prefixed with \\?\

    def longPathEnc(s):
        if s is None:
            return None
#         if s.startswith("\\\\?\\"):
        if s.startswith("\\\\"):
            return s

        return "\\\\?\\" + os.path.abspath(s)

    def longPathDec(s):
        if s is None:
            return None
        if s.startswith("\\\\?\\"):
            return s[4:]

        return s

else:
    longPathEnc = pathEnc
    longPathDec = pathDec


def uniToGui(text):
    """
    Convert unicode text to a format usable for wx GUI. Legacy function, TODO 2.5: Remove
    """
    return text   # Nothing to do

def guiToUni(text):
    """
    Convert wx GUI string format to unicode. Legacy function, TODO 2.5: Remove
    """
    return text   # Nothing to do



# TODO!
def unicodeToCompFilename(us):
    """
    Encode a unicode filename to a filename compatible to (hopefully)
    any filesystem encoding by converting unicode to '=xx' for
    characters up to 255 and '$xxxx' above. Each 'x represents a hex
    character.
    
    Be aware that the returned filename may be too long to be allowed in
    the used filesystem.
    """
    result = []
    for c in us:
        if ord(c) > 255:
            result.append("$%04x" % ord(c))
            continue
        if c in "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"+\
                "{}()+-_,.%":   # Allowed characters
            result.append(str(c))
            continue

        result.append("=%02x" % ord(c))

    return "".join(result)


# def unicodeToAllCharFilename

def strWithNone(s):
    if s is None:
        return ""
    
    return s

def uniWithNone(u):
    if u is None:
        return ""
    
    return u


def strToBool(s, default=False):
    """
    Try to interpret string s as
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
        if s in ("true", "yes", "on"):
            return True
        if s in ("false", "no", "off"):
            return False

        return default


# TODO More formats
def fileContentToUnicode(content, tryHard=False):
    """
    Try to detect the text encoding of byte content based on BOM
    and, if tryHard is True, by guessing and return converted unicode
    """
    if isinstance(content, str):
        return content

    try:    
        if content.startswith(BOM_UTF8):
            return content[len(BOM_UTF8):].decode("utf-8", "surrogateescape")
        elif content.startswith(BOM_UTF16_BE):
            return content[len(BOM_UTF16_BE):].decode("utf-16-be", "surrogateescape")
        elif content.startswith(BOM_UTF16_LE):
            return content[len(BOM_UTF16_LE):].decode("utf-16-le", "surrogateescape")
    except UnicodeDecodeError:
        pass

    if tryHard:
        try:
            return content.decode("utf-8", "strict")
        except UnicodeDecodeError:
            pass
    
        try:
            return content.decode("utf-16", "strict")
        except UnicodeDecodeError:
            pass

    try:
        return mbcsDec(content, "strict")[0]
    except UnicodeDecodeError:
        pass

    return content.decode("latin-1", "replace")



def loadEntireTxtFile(filename):
    """
    Load entire file, adjust line endings and return its byte content.
    """
    rf = open(pathEnc(filename), "rb")
    try:
        return lineendToInternal(rf.read())
    finally:
        rf.close()


# def writeEntireTxtFile(filename, content):
#     """
#     Write entire file (text mode).
#     content can either be a byte string or a tuple or list of byte strings
#     which are then written one by one to the file.
#     """
#     rf = open(pathEnc(filename), "w")
#     try:
#         if isinstance(content, tuple) or isinstance(content, list):
#             for c in content:
#                 rf.write(c)
#         else:
#             rf.write(content)
#         return
#     finally:
#         rf.close()


# def writeEntireFileFast(filename, content, textMode=False):
#     """
#     Fast write of bytestring content without temporary file and
#     error checking.
#     """
#     if textMode:
#         rf = open(pathEnc(filename), "w")
#     else:
#         rf = open(pathEnc(filename), "wb")
# 
#     try:
#         rf.write(content)
#     finally:
#         rf.close()


def loadEntireFile(filename, textMode=False):
    """
    Load entire file and return its content.
    """
    with open(pathEnc(filename), "rb") as rf:
        content = rf.read()
    
    if textMode:
        content = lineendToInternal(content)
    
    return content



# Constants for writeFileMode of writeEntireFile

# safe: Create temporary file, delete previous target file, rename temporary to target
WRITE_FILE_MODE_SAFE = 0

# overwrite: Just overwrite file if it exists (useful if hard links are used)
WRITE_FILE_MODE_OVERWRITE = 1



def writeEntireFile(filename, content, textMode=False,
        writeFileMode=WRITE_FILE_MODE_SAFE):
    """
    Write entire file.
    content  can either be a bytestring or a tuple or list of bytestrings
    which are then written one by one to the file.
    If textMode is True, content can also be a unistring or sequence 
    of them (no mixed bytestring/unistring sequences allowed!)
    which are then converted to UTF-8 and written to file with prefixed BOM
    for utf-8. In textMode, lineEndings are properly converted to the
    appropriate for the OS.
    """
    if writeFileMode == WRITE_FILE_MODE_OVERWRITE:
        f = open(filename, "wb")

        try:
            if isinstance(content, str):
                # assert textMode
                content = content.encode("utf-8")
                f.write(BOM_UTF8)
                if textMode:
                    content = lineendToOs(content)
                f.write(content)
            elif isinstance(content, BYTETYPES):
                if textMode:
                    content = lineendToOs(content)
                f.write(content)
            else:    # content is a sequence
                try:
                    iCont = iter(content)
        
                    firstContent = next(iCont)
                    
                    unic = False
                    if isinstance(firstContent, str):
                        firstContent = firstContent.encode("utf-8")
                        f.write(BOM_UTF8)
                        unic = True
    
                    assert isinstance(firstContent, BYTETYPES)
                    if textMode:
                        content = lineendToOs(content)
                    f.write(firstContent)
    
                    while True:
                        content = next(iCont)
    
                        if unic:
                            assert isinstance(content, str)
                            content = content.encode("utf-8")
    
                        assert isinstance(content, BYTETYPES)
                        if textMode:
                            content = lineendToOs(content)
                        f.write(content)
                except StopIteration:
                    pass
        finally:
            f.close()
        
    else:
        from . import TempFileSet
        
        basePath = os.path.split(filename)[0]
        suffix = os.path.splitext(filename)[1]
    
        if basePath == "":
            basePath = "."
    
        tempPath = TempFileSet.createTempFile(content, suffix=suffix, path=basePath,
                textMode=textMode)
    
        # TODO: What if unlink or rename fails?
        if os.path.exists(filename):
            os.unlink(filename)
    
        os.rename(tempPath, filename)



def getFileSignatureBlock(filename, timeCoarsening=None):
    """
    Returns the file signature block for a given file. It is a bytestring
    containing size and modification date of the file and can be compared to a
    db-stored version to check for file changes outside of WikidPad.
    
    The  timeCoarsening  can be a number of seconds (or fractions thereof).
    The modification time is rounded UP to a number divisible by timeCoarsening.
    
    If a wiki is moved between file systems with different time granularity
    (e.g. NTFS uses 100ns, FAT uses 2s for mod. time) the file would be seen as
    dirty and cache data would be rebuild without need without coarsening.
    """
    statinfo = os.stat(pathEnc(filename))
    
    if timeCoarsening is None or timeCoarsening <= 0:
        return pack(">BQd", 0, statinfo.st_size, statinfo.st_mtime)
    
    ct = int(math.ceil(statinfo.st_mtime / timeCoarsening)) * timeCoarsening
    
    return pack(">BQd", 0, statinfo.st_size, ct)

    


def removeBracketsFilename(fn):
    """
    Remove brackets (real brackets, not configurable) from a filename
    """
    n, ext = os.path.splitext(fn)
    if n.startswith("[") and n.endswith("]"):
        n = n[1:-1]

    return n + ext


def revStr(s):
    """
    Return reversed string
    """
    s = list(s)
    s.reverse()
    return "".join(s)

def splitKeep(s, delim):
    """
    Similar to split, but keeps the delimiter as separate element, e.g.
    splitKeep("aaabaaabaa", "b") -> ["aaa", "b", "aaa", "b", "aa"]
    """
    result = []
    for e in s.split(delim):
        result.append(e)
        result.append(delim)

    return result[:-1]

def splitIndentDeepness(text):
    """
    Return tuple (d, t) where d is deepness of indentation and t is text
    without the indentation.
    """
    pl = len(text)
    text = text.lstrip()
    return (pl-len(text), text)
    
def splitIndent(text):
    """
    Return tuple (ind, t) where ind is a string of the indentation characters
    (normally spaces) and t is text without the indentation.
    """
    pl = len(text)
    textOnly = text.lstrip()
    return (text[:pl-len(textOnly)], textOnly)

def measureIndent(indent):
    return len(indent)


def findLineStart(text, pos):
    # This is even right if no newline is found
    return text.rfind("\n", 0, pos) + 1


def findLineEnd(text, pos):
    result = text.find("\n", pos)
    if result == -1:
        return len(text)
    else:
        return result
    
    

LASTWORDSTART_RE = _re.compile(r"(?:.*\W)?()\w", _re.UNICODE)
FIRSTWORDEND_RE = _re.compile(r".*?()(?:\W|(?!.))", _re.UNICODE)



def getNearestWordStart(text, pos):
    lsPos = findLineStart(text, pos)

    match = LASTWORDSTART_RE.match(text, lsPos, pos + 1)
    if match is not None:
        return match.start(1)
    else:
        return pos
        

def getNearestWordEnd(text, pos):
    match = FIRSTWORDEND_RE.match(text, pos)
    if match is not None:
        return match.start(1)
    else:
        return pos


def styleSelection(text, start, afterEnd, startChars, endChars=None):
    """
    Called when selected text (between start and afterEnd)
    e.g. in editor should be styled with startChars and endChars
    text -- Whole text
    start -- Start position of selection
    afterEnd -- After end position of selection

    startChars -- Characters to place before selection
    endChars -- Characters to place after selection. If None, startChars
            is used for that, too
    
    Returns tuple (replacement, repStart, repAfterEnd, selStart, selAfterEnd) where

        replacement -- replacement text
        repStart -- Start of characters to delete in original text
        repAfterEnd -- After end of characters to delete
        selStart -- Recommended start of editor selection after replacement
            was done
        selAfterEnd -- Recommended after end of editor selection after replacement
    """
    if endChars is None:
        endChars = startChars

    if start == afterEnd:
        start = getNearestWordStart(text, start)
        afterEnd = getNearestWordEnd(text, start)
        
    emptySelection = start == afterEnd  # is selection empty

    replacement = startChars + text[start:afterEnd] + endChars

    if emptySelection:
        # If selection is empty, cursor should in the end
        # stand between the style characters
        cursorPos = afterEnd + len(startChars)
    else:
        # If not, it will stand after styled word
        cursorPos = afterEnd + len(startChars) + len(endChars)

    return (replacement, start, afterEnd, cursorPos, cursorPos)

    

def splitFill(text, delim, count, fill=""):
    """
    Split text by delim into up to count pieces. If less
    pieces than count+1 are available, additional pieces are added containing
    fill.
    """
    result = text.split(delim, count)
    if len(result) < count + 1:
        result += [fill] * (count + 1 - len(result))
    
    return result


# def splitUnifName(unifName):
#     """
#     Split a unified name path and return a list of components.
#     If a part of the path must contain a slash it is quoted as double slash.
#     
#     Some unified names shouldn't be processed by this function, especially
#     "wikipage/..." unifNames
#     """
#     result = 



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



def obfuscateShortcut(shortcut):
    """
    Necessary to prevent wxPython from interpreting e.g. CTRL+LEFT in a menu
    item as being a shortcut. I haven't found a better way.
    Unused at the moment.
    """
    return "".join(["\u200B" + c for c in shortcut])



## Copied from xml.sax.saxutils and modified to reduce dependencies
def escapeHtml(data):
    """
    Escape &, <, > and line breaks in a unicode string of data.
    """

    # must do ampersand first

    return data.replace("&", "&amp;").replace(">", "&gt;").\
            replace("<", "&lt;").replace("\n", "<br />\n")


def escapeHtmlNoBreaks(data):
    """
    Escape &, <, and > (no line breaks) in a unicode string of data.
    """

    # must do ampersand first

    return data.replace("&", "&amp;").replace(">", "&gt;").\
            replace("<", "&lt;")




class AbstractHtmlItem:
    """
    Abstract base for some "things" appearing in HTML. This and derived classes
    mainly needed for the "htmlEquivalent" token in a wiki AST
    """
    def __init__(self):
        pass
    
    def asString(self):
        raise NotImplementedError

    def clone(self):
        raise NotImplementedError

    def __repr__(self):
        return self.__class__.__name__ + ":" + self.asString()


class HtmlStartTag(AbstractHtmlItem):
    """
    Regular start tag
    """
    def __init__(self, tag, attributes=None):
        self.tag = tag
        if attributes is None:
            self.attributes = {}
        else:
            self.attributes = dict((k, escapeHtml(v).replace("\"", "&quot;"))
                    for k, v in attributes.items())
    
    def addAttribute(self, key, value):
        if value is None:
            value = key

        self.attributes[key] = escapeHtml(value).replace("\"", "&quot;")


    def addEscapedAttribute(self, key, value):
        if value is None:
            value = key

        self.attributes[key] = value


    def addEscapedAttributes(self, attrSeq):
        for key, value in attrSeq:
            self.addEscapedAttribute(key, value)


    def getTag(self):
        return self.tag

    def getStringForAttributes(self):
        return " ".join(
                k + "=\"" + v + "\""
                for k, v in self.attributes.items())
    
    def asString(self):
        if len(self.attributes) == 0:
            return "<" + self.tag + ">"
        
        attrString = self.getStringForAttributes()
        return "<" + self.tag + " " + attrString + ">"


    def clone(self):
        return HtmlStartTag(self.tag, self.attributes)


class HtmlEmptyTag(HtmlStartTag):
    """
    Start tag which is also end tag
    """
    
    def asString(self):
        if len(self.attributes) == 0:
            return "<" + self.tag + " />"
        
        attrString = self.getStringForAttributes()
        return "<" + self.tag + " " + attrString + " />"

    def clone(self):
        return HtmlEmptyTag(self.tag, self.attributes)


class HtmlEndTag(AbstractHtmlItem):
    """
    Regular end tag
    """
    def __init__(self, tag):
        self.tag = tag
    
    def asString(self):
        return "</" + self.tag + ">"

    def clone(self):
        return HtmlEndTag(self.tag)


class HtmlEntity(AbstractHtmlItem):
    """
    Entity
    """
    def __init__(self, entity):
        if entity[0] != "&":
            entity = "&" + entity
        
        if entity[-1] != ";":
            entity += ";"
        
        self.entity = entity

    def asString(self):
        return self.entity
    
    def clone(self):
        return HtmlEntity(self.entity)

    

def escapeForIni(text, toEscape=""):
    """
    Return an escaped version of string. Always escaped will be backslash and
    all characters with ASCII value < 32. Additional characters can be given in
    the toEscape parameter (as unicode string, only characters < 128,
    not the backslash).

    Returns: unicode string
    """
    # Escape '\'
    text = text.replace("\\", "\\x%02x" % ord("\\"))

    # Escape everything with ord < 32
    for i in range(32):
        text = text.replace(chr(i), "\\x%02x" % i)

    for c in toEscape:
        text = text.replace(c, "\\x%02x" % ord(c))

    return text


def _unescapeForIniHelper(match):
    return chr(int(match.group(1), 16))

def unescapeForIni(text):
    """
    Inverse of escapeForIni()
    """
    return _re.sub(r"\\x([0-9a-f]{2})", _unescapeForIniHelper, text)


# def escapeWithRe(text):
#     return text.replace(u"\\", u"\\\\").replace("\n", "\\n").\
#             replace("\r", "\\r")

def unescapeWithRe(text):
    """
    Unescape things like \n or \f. Throws exception if unescaping fails
    """
    return _re.sub("", text, "", 1)


def re_sub_escape(pattern):
    """
    Escape the replacement pattern for a re.sub function
    """
    return pattern.replace("\\", "\\\\").replace("\n", "\\n").replace(
            "\r", "\\r").replace("\t", "\\t").replace("\f", "\\f")


HTML_DIGITCOLOR = _re.compile(
        r"^#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?$",
        _re.DOTALL | _re.UNICODE | _re.MULTILINE)


# def htmlColorToRgbTuple(desc):
def colorDescToRgbTuple(desc):
    """
    Converts a color description to an RGB tuple or None if
    description is invalid.
    Color description can be:
    HTML 6-digits color, e.g. #C0D623
    HTML 3-digits color, e.g. #4E2 which converts to #44EE22  (TODO: HTML standard?)
    HTML color name
    """
    global HTML_DIGITCOLOR, _COLORBASE

    if not HTML_DIGITCOLOR.match(desc):
        try:
            desc = _COLORBASE[desc.replace(" ", "").lower()]
        except KeyError:
            return None

    if len(desc) == 4:
        desc = "#" + desc[1] + desc[1] + desc[2] + desc[2] + desc[3] + desc[3]
    try:
        r = int(desc[1:3], 16)
        g = int(desc[3:5], 16)
        b = int(desc[5:7], 16)
        return (r, g, b)
    except:
        return None


# def colorDescToRgbTuple(desc):
#     """
#     Converts a color description to an RGB tuple or None if
#     description is invalid.
#     Color description can be:
#     HTML 6-digits color, e.g. #C0D623
#     HTML 3-digits color, e.g. #4E2 which converts to #44EE22  (TODO: HTML standard?)
#     HTML color name
#     """
#     desc = desc.strip()
#     if len(desc) == 0:
#         return None
#     
#     if desc[0] != "#":
#         desc = desc.replace(" ", "").lower()
#         desc = _COLORBASE.get(desc)
#         if desc is None:
#             return None
# 
#     if len(desc) == 4:
#         desc = "#" + desc[1] + desc[1] + desc[2] + desc[2] + desc[3] + desc[3]
# 
#     if len(desc) != 7:
#         return None
#     try:
#         r = int(desc[1:3], 16)
#         g = int(desc[3:5], 16)
#         b = int(desc[5:7], 16)
#         return (r, g, b)
#     except:
#         return None


def rgbToHtmlColor(r, g, b):
    """
    Return HTML color '#hhhhhh' format string.
    """
    return "#%02X%02X%02X" % (r, g, b)


def base64BlockEncode(data):
    """
    Cut a sequence of base64 characters into chunks of 70 characters
    and join them with newlines. Pythons base64 decoder can read this.
    data -- bytes to encode
    
    returns string
    """
    b64 = base64.b64encode(data)

    result = []
    while len(b64) > 70:
        result.append(b64[:70])
        b64 = b64[70:]

    if len(b64) > 0:
        result.append(b64)

    return b"\n".join(result).decode("ascii")


# Just for completeness
base64BlockDecode = base64.b64decode



EXTENDED_STRFTIME_RE = _re.compile(
        r"([^%]+|%(?:%|[%aAbBcdHIJmMpSUwWxXyYZ])|(?:%u))",
        _re.DOTALL | _re.UNICODE | _re.MULTILINE)


def formatWxDate(frmStr, date):
    """
    Format a date (wxDateTime) according to frmStr similar to strftime.
    """
    if frmStr == "":
        return frmStr
    
    resParts = []
    
    for part in EXTENDED_STRFTIME_RE.split(frmStr):
        if not part:
            continue
        if part == "%u":
            # Create weekday following ISO-8601
            wd = date.GetWeekDay()
            if wd == 0:
                # Sunday has number 7
                wd = 7
            resParts.append("%i" % wd)
        elif part == "%":
            resParts.append("%%")
        else:
            resParts.append(part)

    frmStr = "".join(resParts)

    return date.Format(unescapeWithRe(frmStr))


def formatTimeT(frmStr, timet=None):
    """
    Format a time_t (seconds since epoch) according to frmStr similar to strftime.
    If time_t is None, current time is used
    """
    if frmStr == "":
        return frmStr
    
    resParts = []
    
    if timet is None:
        locTime = time.localtime()
    else:
        locTime = time.localtime(timet)
    
    for part in EXTENDED_STRFTIME_RE.split(frmStr):
        if not part:
            continue
            
        if part == "%u":
            # Create weekday following ISO-8601 (1=Monday, ..., 7=Sunday)
            resParts.append("%i" % (locTime.tm_wday + 1))
        elif part == "%":
            resParts.append("%%")
        else:
            resParts.append(part)

    frmStr = "".join(resParts)

    return time.strftime(unescapeWithRe(frmStr), locTime)
    



def strftimeUB(frmStr, timet=None):
    """
    Similar to time.strftime, but uses a time_t number as time (no structure),
    also unescapes some backslash codes, supports unicode and shows local time
    if timet is GMT.
    """
    try:
        return formatTimeT(frmStr, timet)
    except TypeError:
        return _("Inval. timestamp")  #  TODO Better errorhandling?



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


def getRelativeFilePathAndTestContained(location, toFilePath):
    """
    Returns a relative (if possible) path to address the file
    toFilePath if you are in directory location as first tuple item.


    Function returns None as first tuple item if an absolute path is needed!
    
    Tests if toFilePath is a file or dir contained in location and returns
        truth value in second tuple item

    Both parameters should be normalized with os.path.abspath
    location -- Directory where you are
    toFilePath -- absolute path to file you want to reach
    """
    locParts = splitpath(location)
    if locParts[-1] == "":
        del locParts[-1]

    locLen = len(locParts)
    fileParts = splitpath(toFilePath)

    for i in range(len(locParts)):
        if len(fileParts) == 0:
            break  # TODO Error ???

        if os.path.normcase(locParts[0]) != os.path.normcase(fileParts[0]):
            break

        del locParts[0]
        del fileParts[0]

    result = []

    if len(locParts) == locLen:
        # Nothing matches at all, absolute path needed
        return None, False
        
    isContained = len(fileParts) > 0
    if len(locParts) > 0:
        # go back some steps
        result += [".."] * len(locParts)
        isContained = False

    result += fileParts
    
    if len(result) == 0:
        return "", False
    else:
        return os.path.join(*result), isContained



def relativeFilePath(location, toFilePath):
    """
    Returns a relative (if possible) path to address the file
    toFilePath if you are in directory location.
    Both parameters should be normalized with os.path.abspath

    Function returns None if an absolute path is needed!

    location -- Directory where you are
    toFilePath -- absolute path to file you want to reach
    """
    return getRelativeFilePathAndTestContained(location, toFilePath)[0]


def testContainedInDir(location, toFilePath):
    """
    Tests if toFilePath is a file or dir contained in location.
    Both parameters should be normalized with os.path.abspath
    """
    return getRelativeFilePathAndTestContained(location, toFilePath)[1]




def _asciiFlexibleUrlUnquote(part):
    """
    Unquote ascii-only parts of an url
    """
    if len(part) == 0:
        return ""
    # Get bytes out of percent-quoted URL
    linkBytes = urllib.parse.unquote_to_bytes(part.encode("ascii"))
    # Try to interpret bytes as UTF-8
    try:
        return linkBytes.decode("utf8", "strict")
    except UnicodeDecodeError:
        # Failed -> try mbcs
        try:
            return mbcsDec(linkBytes, "strict")[0]
        except UnicodeDecodeError:
            # Failed, too -> leave link part unmodified. TODO: Doesn't make sense, will fail as well.
            return part


def flexibleUrlUnquote(link):
    """
    Tries to unquote an url.
    TODO: Faster and more elegantly.
    
    link -- unistring
    """
    if link is None:
        return None

    i = 0
    result = SnippetCollector("")

    while i < len(link):

        asciiPart = ""
        while i < len(link) and ord(link[i]) < 128:
            asciiPart += chr(ord(link[i]))
            i += 1
        
        result += _asciiFlexibleUrlUnquote(asciiPart)

        unicodePart = ""
        while i < len(link) and ord(link[i]) >= 128:
            unicodePart += link[i]
            i += 1
        
        result += unicodePart
        
    return result.value()



URL_RESERVED = frozenset((";", "?", ":", "@", "&", "=", "+", ",", "/",
        "{", "}", "|", "\\", "^", "~", "[", "]", "`", '"', "%"))



def urlQuote(s, safe='/'):
    """
    Modified version of urllib.quote supporting unicode.
    
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
    
    The characters u"{", u"}", u"|", u"\", u"^", u"~", u"[", u"]", u"`"
    are considered unsafe and should be quoted as well.
    """
    result = []
    
    for c in s:
        if c not in safe and (ord(c) < 33 or c in URL_RESERVED):
            result.append("%%%02X" % ord(c))
        else:
            result.append(c)

    return "".join(result)



def urlQuoteSpecific(s, toQuote=''):
    """
    Only quote characters in toQuote
    """
    result = []
    
    for c in s:
        if c in toQuote:
            result.append("%%%02X" % ord(c))
        else:
            result.append(c)

    return "".join(result)



def ntUrlFromPathname(p, addSafe=''):
    r"""
    Modified version of nturl2path.pathname2url.

    Convert a DOS/Windows path name to a file url.

            C:\foo\bar\spam.foo

                    becomes

            ///C:/foo/bar/spam.foo
    """
    if not ':' in p:
        # No drive specifier, just convert slashes and quote the name
#         if p[:2] == '\\\\':
#         # path is something like \\host\path\on\remote\host
#         # convert this to ////host/path/on/remote/host
#         # (notice doubling of slashes at the start of the path)
#             p = '\\\\' + p
        components = p.split('\\')
        return urlQuote('/'.join(components), safe='/' + addSafe)
    comp = p.split(':')
    if len(comp) != 2 or len(comp[0]) > 1:
        error = 'Bad path: ' + p
        raise IOError(error)

    drive = urlQuote(comp[0].upper(), safe='/' + addSafe)
    components = comp[1].split('\\')
    path = '///' + drive + ':'
    for comp in components:
        if comp:
            path = path + '/' + urlQuote(comp, safe='/' + addSafe)
    return path



def _macpncomp2url(component, addSafe):
    component = urlQuote(component[:31], safe=addSafe)  # We want to quote slashes
    return component

def macUrlFromPathname(pathname, addSafe=''):
    """
    Modified version of macurl2path.pathname2url.

    convert mac pathname to /-delimited pathname
    """
    if '/' in pathname:
        raise RuntimeError("Cannot convert pathname containing slashes")
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
    components = [_macpncomp2url(c, addSafe) for c in components]
#     components = map(_macpncomp2url, components)

    if os.path.isabs(pathname):
        return '/' + '/'.join(components)
    else:
        return '/'.join(components)


if os.name == 'nt':
    urlFromPathname = ntUrlFromPathname
elif os.name == 'mac':
    urlFromPathname = macUrlFromPathname
else:
    def urlFromPathname(fn, addSafe=''):
        if isinstance(fn, BYTETYPES):
            fn = fileContentToUnicode(fn, tryHard=True)
            
        # riscos not supported
        url = urlQuote(fn, safe='/$' + addSafe)
#         url.replace("%24", "$")

        return url




def ntPathnameFromUrl(url, testFileType=True):
    r"""
    Modified version of nturl2path.url2pathname.
    
    Convert a URL to a DOS path.

            ///C|/foo/bar/spam.foo

                    becomes

            C:\foo\bar\spam.foo
            
    testFileType -- ensure that URL has type "file" (and starts with "file:")
            throw RuntimeError if not.
    """
    import string
    if url.startswith("file:") or url.startswith("wiki:"):
        url = url[5:]
    elif testFileType:
        raise RuntimeError('Cannot convert non-local URL to pathname')
        
    # Strip fragment or query if present
    url, dummy = decomposeUrlQsFrag(url)

    if (not ':' in url) and (not '|' in url) and (not '%3A' in url) and (not '%3a' in url):
        # No drive specifier, just convert slashes
        if url[:4] == '////':
            # path is something like ////host/path/on/remote/host
            # convert this to \\host\path\on\remote\host
            # (notice halving of slashes at the start of the path)
            url = url[2:]
        components = url.split('/')
        # make sure not to convert quoted slashes :-)
        return flexibleUrlUnquote('\\'.join(components))

    comp = None
    for driveDelim in ('|', ':', '%3A', '%3a'):
        comp = url.split(driveDelim)
        if len(comp) != 2 or len(comp[0]) == 0 or comp[0][-1] not in string.ascii_letters:
            comp = None
            continue
        break

    if comp is None:
        error = 'Bad URL: ' + url
        raise IOError(error)


#     comp = url.split('|')
#     if len(comp) == 1:
#         comp = url.split(':')
# 
#     if len(comp) != 2 or len(comp[0]) == 0 or comp[0][-1] not in string.ascii_letters:
#         error = 'Bad URL: ' + url
#         raise IOError, error

    drive = comp[0][-1].upper()
    components = comp[1].split('/')
    path = drive + ':'
    for comp in components:
        if comp:
            path = path + '\\' + flexibleUrlUnquote(comp)
    return path



def macPathnameFromUrl(url, testFileType=True):
    "Convert /-delimited url to mac pathname"
    #
    # XXXX The .. handling should be fixed...
    #
    tp = urllib.parse.splittype(url)[0]
    if tp and tp != 'file' and tp != 'wiki':
        raise RuntimeError('Cannot convert non-local URL to pathname')
    # Turn starting /// into /, an empty hostname means current host
    if url[:3] == '///':
        url = url[2:]
    elif url[:2] == '//':
        raise RuntimeError('Cannot convert non-local URL to pathname')

    # Strip fragment or query if present
    url, dummy = decomposeUrlQsFrag(url)

    components = url.split('/')
    # Remove . and embedded ..
    i = 0
    while i < len(components):
        if components[i] == '.':
            del components[i]
        elif components[i] == '..' and i > 0 and \
                                  components[i-1] not in ('', '..'):
            del components[i-1:i+1]
            i = i-1
        elif components[i] == '' and i > 0 and components[i-1] != '':
            del components[i]
        else:
            i = i+1
    if not components[0]:
        # Absolute unix path, don't start with colon
        rv = ':'.join(components[1:])
    else:
        # relative unix path, start with colon. First replace
        # leading .. by empty strings (giving ::file)
        i = 0
        while i < len(components) and components[i] == '..':
            components[i] = ''
            i = i + 1
        rv = ':' + ':'.join(components)
    # and finally unquote slashes and other funny characters
    return flexibleUrlUnquote(rv)


def elsePathnameFromUrl(url, testFileType=True):
    "Convert /-delimited url to pathname"
    #
    # XXXX The .. handling should be fixed...
    #
    if url.startswith("file:///") or url.startswith("wiki:///"):
        url = url[7:]   # Third '/' remains
    elif url.startswith("file:") or url.startswith("wiki:"):
        url = url[5:]
    elif testFileType:
        raise RuntimeError('Cannot convert non-local URL to pathname')
    
    # Strip fragment or query if present
    url, dummy = decomposeUrlQsFrag(url)

    return flexibleUrlUnquote(url)




if os.name == 'nt':
    pathnameFromUrl = ntPathnameFromUrl
elif os.name == 'mac':
    pathnameFromUrl = macPathnameFromUrl
else:
#     pathnameFromUrl = flexibleUrlUnquote
    pathnameFromUrl = elsePathnameFromUrl



_DECOMPOSE_URL_RE = _re.compile(r"([^?#]*)((?:[?#].*)?)", _re.UNICODE | _re.DOTALL);


def decomposeUrlQsFrag(url):
    """
    Find first '?' or '#' (query string or fragment) in URL and split URL
    there so that the parts can be (un-)quoted differently.
    Returns a 2-tuple with main part and additional part of URL.
    """
    return _DECOMPOSE_URL_RE.match(url).groups()
    

def composeUrlQsFrag(mainUrl, additional):
    """
    Compose main URL and additional part back into one URL. Currently a very
    simple function but may become more complex later.
    """
    return mainUrl + additional
    


def _quoteChar(c):
    oc = ord(c)
    if oc < 256:
        return "%%%02X" % oc
    else:
        return "@%04X" % oc


_ESCAPING_CHARACTERS = "%@~"

_FORBIDDEN_CHARACTERS = frozenset(":/\\*?\"'<>|;![]" + _ESCAPING_CHARACTERS)
_FORBIDDEN_START = _FORBIDDEN_CHARACTERS | frozenset(".$ -")

# Allowed ascii characters remaining: #&()+,=[]^_`{}


def iterCompatibleFilename(baseName, suffix, asciiOnly=False, maxLength=120,
        randomLength=10):
    """
    Generator to create filenames compatible to (hopefully) all major
    OSs/filesystems.
    
    Encode a unicode filename to a filename compatible to (hopefully)
    any filesystem encoding by converting unicode to '%xx' for
    characters up to 250 and '@xxxx' above. Each 'x represents a hex
    character.
    
    If the resulting name is too long it is shortened.
    
    If the first returned filename isn't accepted, a sequence of random
    characters, delimited by a tilde '~' is added. If the filename is then
    too long it is also shortened.
    
    The first random sequence isn't random but a MD5-hash of baseName.
    
    Each time you ask for next filename, a new sequence of random characters
    is created.
    
    baseName - Base name to use for the filename
    suffix - Suffix (must include the dot) of the filename. The suffix must not
            be empty, is not quoted in any way and should follow the
            rules of the filesystem(s)
    asciiOnly - Iff True, all non-ascii characters are replaced.
    maxLength - Maximum length of filename including encoded basename,
        random sequence and suffix
    randomLength - Length of the random sequence (without leading tilde)

    """
    maxLength = Utilities.between(20 + len(suffix) + randomLength, maxLength, 250)

    baseName = mbcsDec(baseName)[0]

    if len(baseName) > 0:
        c = baseName[0]
        if ord(c) < 32 or c in _FORBIDDEN_START or \
                (asciiOnly and ord(c) > 127):
            baseQuoted = [_quoteChar(c)]
        else:
            baseQuoted = [c]

        for c in baseName[1:]:
            if ord(c) < 32 or c in _FORBIDDEN_CHARACTERS or \
                    (asciiOnly and ord(c) > 127):
                baseQuoted.append(_quoteChar(c))
            else:
                baseQuoted.append(c)

    else:
        baseQuoted = []

    overallLength = sum(len(bq) for bq in baseQuoted) + len(suffix)

    # Shorten baseQuoted if needed. This method ensures that no half-quoted
    # character (e.g. "@3") is remaining
    while overallLength > maxLength:
        overallLength -= len(baseQuoted.pop())

    if len(baseName) > 0:
        # First try, no random part
        yield "".join(baseQuoted) + suffix
    
    # Add random part to length
    overallLength += 1 + randomLength
    
    # Shorten baseQuoted again
    while overallLength > maxLength:
        overallLength -= len(baseQuoted.pop())
   
    beforeRandom = "".join(baseQuoted) + "~"

    # Now we try MD5-Hash. This is one last try to create a filename which
    # is non-ambigously connected to the baseName
    hashStr = getMd5B36ByString(baseName)[-randomLength:]
    if len(hashStr) < randomLength:
        hashStr = "0" * (randomLength - len(hashStr)) + hashStr

    yield beforeRandom + hashStr + suffix

    # Now build infinite random names
    while True:
        yield beforeRandom + createRandomString(randomLength) + suffix


def _unquoteCharRepl(matchObj):
    s = matchObj.group(0)
    
    if s[0] == "%":
        v = int(s[1:3], 16)
        return chr(v)
    else:   #  s[0] == "@":
        v = int(s[1:5], 16)
        return chr(v)


_FILENAME_UNQUOTE_RE = _re.compile(r"%[A-Fa-f0-9]{2}|@[A-Fa-f0-9]{4}",
        _re.UNICODE | _re.DOTALL | _re.MULTILINE)


def guessBaseNameByFilename(filename, suffix=""):
    """
    Try to guess the basename for a particular file name created by
    iterCompatibleFilename() as far as it can be reconstructed.
    """
    # Filename may contain a path, so at first, strip it 
    filename = os.path.basename(filename)
    
    if filename.endswith(suffix):
        filename = filename[:-len(suffix)]
    # else?

    # After a tilde begins the random part, so remove
    tildI = filename.find("~")
    if tildI > 0:  # tildI == 0 would mean a nameless file
        filename = filename[:tildI]

    return _FILENAME_UNQUOTE_RE.sub(_unquoteCharRepl, filename)




_RNDBASESEQ = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"

def createRandomString(length):
    """
    Create a unicode string of  length  random characters and digits
    """
    return "".join([random.choice(_RNDBASESEQ) for i in range(length)])



# _RNDBASENOHEX = u"GHIJKLMNOPQRSTUVWXYZ"
# 
# def createRandomStringNoHexFirst(length):
#     """
#     Create a unicode string of  length  random characters and digits.
#     First char. must not be a possible hexadecimal digit.
#     """
#     if length == 0:
#         return u""
# 
#     return random.choice(_RNDBASENOHEX) + u"".join([random.choice(_RNDBASESEQ)
#             for i in range(length - 1)])


def getMd5B36ByString(text):
    """
    Calculate the MD5 hash of text (if unicode after conversion to utf-8)
    and return it as unistring for numeric base 36.
    
    Based on http://code.activestate.com/recipes/111286/
    """
    if isinstance(text, str):
        text = text.encode("utf-8")
    
#     digest = hashlib.md5(text).digest()
# 
#     # make an integer out of the number
#     x = 0L
#     for digit in digest:
#        x = x*256 + ord(digit)

    x = int(hashlib.md5(text).hexdigest(), 16)
    
    # create the result in base len(_RNDBASESEQ) (=36)
    res=""
    if x == 0:
        res = _RNDBASESEQ[0]
    while x>0:
        digit = x % len(_RNDBASESEQ)
        res = _RNDBASESEQ[digit] + res
        x //= len(_RNDBASESEQ)

    return res




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


# def orderBySuggestion(strs, sugg):
#     """
#     Order string iterable  strs  in a way that all strings also present in
#     sequence  sugg  come first in resulting list, then the strings from strs
#     which are not in  sugg  in arbitrary order.
#     """
#     s = set(strs)
#     result = []
#     for e in sugg:
#         if e in s:
#             result.append(e)
#             s.remove(e)
#     
#     for e in s:
#         result.append(e)
#     
#     return result


def wikiUrlToPathWordAndAnchor(url):
    """
    Split a "wiki:" protocol URL into the path of the config file,
    the name of the wikiword and the anchor to open if given in query string.

    Returns (path, wikiword, anchor) where wikiword and/or anchor may be None
    """
    # Change "wiki:" url to "http:" for urlparse
    linkHt = "http:" + url[5:]
    parsed = urllib.parse.urlparse(linkHt)
    # Parse query string into dictionary
    queryDict = cgi.parse_qs(parsed[4])
    # Retrieve wikiword to open if existing
    # queryDict values are lists of values therefore this expression
    wikiWordToOpen = flexibleUrlUnquote(queryDict.get("page", (None,))[0])
    anchorToOpen = flexibleUrlUnquote(queryDict.get("anchor", (None,))[0])

    # Modify parsed to create clean url by clearing query and fragment
    parsed = list(parsed)
    parsed[4] = ""
    parsed[5] = ""
    parsed = tuple(parsed)

    filePath = pathnameFromUrl(urllib.parse.urlunparse(parsed)[5:], False)

#     filePath = urllib.url2pathname(url)

    return (filePath, wikiWordToOpen, anchorToOpen)
    
    
def pathWordAndAnchorToWikiUrl(filePath, wikiWordToOpen, anchorToOpen):
    url = urlFromPathname(filePath)
    
    queryStringNeeded = (wikiWordToOpen is not None) or \
            (anchorToOpen is not None)

    result = ["wiki:", url]
    if queryStringNeeded:
        result.append("?")
        ampNeeded = False

        if wikiWordToOpen is not None:
            result.append("page=")
            result.append(urlQuote(wikiWordToOpen, safe=""))
            ampNeeded = True
        
        if anchorToOpen is not None:
            if ampNeeded:
                result.append("&")
            result.append("anchor=")
            result.append(urlQuote(anchorToOpen, safe=""))
            ampNeeded = True

    return "".join(result)
    

def joinRegexes(patternList):
    return "(?:(?:" + ")|(?:".join(patternList) + "))"



class SnippetCollector:
    """
    Collects (byte/uni)string snippets in a list. This is faster than
    using string += string.
    """
    def __init__(self, emptyElement):
        """
        emptyElement --- must be either "" for strings or b"" for bytes. Defines
                which data type is processed by this SnippetCollector
        """
        self.snippets = []
        self.length = 0
        self.emptyElement = emptyElement

    def drop(self, length):
        """
        Remove last  length  (byte/uni)characters
        """
        assert self.length >= length

        while length > 0 and len(self.snippets) > 0:
            if length < len(self.snippets[-1]):
                self.snippets[-1] = self.snippets[-1][:-length]
                self.length -= length
                break;
            
            if length >= len(self.snippets[-1]):
                length -= len(self.snippets[-1])
                self.length -= len(self.snippets[-1])
                del self.snippets[-1]

    def append(self, s):
        if len(s) == 0:
            return

        self.length += len(s)
        self.snippets.append(s)

    
    def __iadd__(self, s):
        self.append(s)
        return self

    def value(self):
        return self.emptyElement.join(self.snippets)
    
    def __len__(self):
        return self.length


class Conjunction:
    """
    Used to create SQL statements. Example:
        conjunction = Conjunction("where ", "and ")
        whereClause = ""
        if ...:
            whereClause += conjunction() + "word = ? "
        if ...:
            whereClause += conjunction() + "key = ? "
    
    will always create a valid where-clause
    """
    def __init__(self, firstpart, otherpart):
        self.firstpart = firstpart
        self.otherpart = otherpart
        self.first = True

    def __call__(self):
        if self.first:
            self.first = False
            return self.firstpart
        else:
            return self.otherpart

    def __repr__(self):
        return "<Conjunction(%s, %s) %s>" % (self.firstpart, self.otherpart,
                self.first)



# ---------- Handling diff information ----------


def difflibToCompact(ops, b):
    """
    Rewrite sequence of op_codes returned by difflib.SequenceMatcher.get_opcodes
    to the compact opcode format.

    0: replace,  1: delete,  2: insert

    b -- second string to match
    """
    result = []
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
            # Uses opposite endianness as the rest of WikidPad but it's
            # too late to change
            result.append( pack("<Biii", 0, op[1], op[2], len(op[3])) )
            result.append(op[3])
        elif op[0] == 1:
            result.append( pack("<Bii", *op) )
        elif op[0] == 2:
            result.append( pack("<Bii", 2, op[1], len(op[2])) )
            result.append(op[2])

    return b"".join(result)



def binCompactToCompact(bops):
    """
    Uncompress the ops from the binary format
    """
    pos = 0
    result = []
    while pos < len(bops):
        t = bops[pos]
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
    Apply compact ops to bytes a to create and return bytes b
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

    return b"".join(result)


def applyBinCompact(a, bops):
    """
    Apply binary diff operations bops to a to create and return b
    """
    return applyCompact(a, binCompactToCompact(bops))


# The "mu*" functions relate to the Myers-Ukkonen algorithm and provided module
# MyersUkkonenDiff which is much faster than internal difflib


def muDiffToCompact(b, diff):
    result = []
    for (i, ilen, j, jlen) in diff:
        assert ilen > 0 or jlen > 0
        
        if ilen == 0:
            # insert
            result.append((2, i, b[j:(j + jlen)]))
        elif jlen == 0:
            # delete
            result.append((1, i, i + ilen))
        else:
            #replace
            result.append((0, i, i + ilen, b[j:(j + jlen)]))
    
    return result
        


def muCompactDiff(a, b):
    return muDiffToCompact(b, MyersUkkonenDiff.diff(a, b))


def getBinCompactForDiff(a, b, mode=1):
    """
    Return the binary compact codes to change bytes a to b.
    For bytes a and b (NOT strings) it is always true that
        applyBinCompact(a, getBinCompactForDiff(a, b)) == b
    
    mode -- 0: Use standard library's difflib (yet default)
            1: Use Myers-Ukkonen algorithm (much faster on larger data with
               small changes)
    """
    if mode == 1:
        return compactToBinCompact(muCompactDiff(a, b))
    else:
        sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
        ops = sm.get_opcodes()
        return compactToBinCompact(difflibToCompact(ops, b))


# ---------- Unicode constants ----------

# UPPERCASE = None
# LOWERCASE = None
# 
# def _fillConsts():
#     global UPPERCASE, LOWERCASE
#     from unicodedata import category
#     
#     uc = []
#     lc = []
#     
#     for i in range(0, 0x10000):
#         c = unichr(i)
#         if category(c) == "Ll":
#             lc.append(c)
#         elif category(c) == "Lu":
#             uc.append(c)
#     
#     UPPERCASE = u"".join(uc)
#     LOWERCASE = u"".join(lc)
# 
# _fillConsts()


# Interestingly it isn't noticeably faster to set the constants directly than
# calculating it at each start, but it doesn't need "unicodedata.pyd"

LOWERCASE = 'abcdefghijklmnopqrstuvwxyz\xaa\xb5\xba\xdf\xe0\xe1\xe2\xe3\xe4\xe5\xe6\xe7\xe8\xe9\xea\xeb\xec\xed\xee\xef\xf0\xf1\xf2\xf3\xf4\xf5\xf6\xf8\xf9\xfa\xfb\xfc\xfd\xfe\xff\u0101\u0103\u0105\u0107\u0109\u010b\u010d\u010f\u0111\u0113\u0115\u0117\u0119\u011b\u011d\u011f\u0121\u0123\u0125\u0127\u0129\u012b\u012d\u012f\u0131\u0133\u0135\u0137\u0138\u013a\u013c\u013e\u0140\u0142\u0144\u0146\u0148\u0149\u014b\u014d\u014f\u0151\u0153\u0155\u0157\u0159\u015b\u015d\u015f\u0161\u0163\u0165\u0167\u0169\u016b\u016d\u016f\u0171\u0173\u0175\u0177\u017a\u017c\u017e\u017f\u0180\u0183\u0185\u0188\u018c\u018d\u0192\u0195\u0199\u019a\u019b\u019e\u01a1\u01a3\u01a5\u01a8\u01aa\u01ab\u01ad\u01b0\u01b4\u01b6\u01b9\u01ba\u01bd\u01be\u01bf\u01c6\u01c9\u01cc\u01ce\u01d0\u01d2\u01d4\u01d6\u01d8\u01da\u01dc\u01dd\u01df\u01e1\u01e3\u01e5\u01e7\u01e9\u01eb\u01ed\u01ef\u01f0\u01f3\u01f5\u01f9\u01fb\u01fd\u01ff\u0201\u0203\u0205\u0207\u0209\u020b\u020d\u020f\u0211\u0213\u0215\u0217\u0219\u021b\u021d\u021f\u0223\u0225\u0227\u0229\u022b\u022d\u022f\u0231\u0233\u0250\u0251\u0252\u0253\u0254\u0255\u0256\u0257\u0258\u0259\u025a\u025b\u025c\u025d\u025e\u025f\u0260\u0261\u0262\u0263\u0264\u0265\u0266\u0267\u0268\u0269\u026a\u026b\u026c\u026d\u026e\u026f\u0270\u0271\u0272\u0273\u0274\u0275\u0276\u0277\u0278\u0279\u027a\u027b\u027c\u027d\u027e\u027f\u0280\u0281\u0282\u0283\u0284\u0285\u0286\u0287\u0288\u0289\u028a\u028b\u028c\u028d\u028e\u028f\u0290\u0291\u0292\u0293\u0294\u0295\u0296\u0297\u0298\u0299\u029a\u029b\u029c\u029d\u029e\u029f\u02a0\u02a1\u02a2\u02a3\u02a4\u02a5\u02a6\u02a7\u02a8\u02a9\u02aa\u02ab\u02ac\u02ad\u0390\u03ac\u03ad\u03ae\u03af\u03b0\u03b1\u03b2\u03b3\u03b4\u03b5\u03b6\u03b7\u03b8\u03b9\u03ba\u03bb\u03bc\u03bd\u03be\u03bf\u03c0\u03c1\u03c2\u03c3\u03c4\u03c5\u03c6\u03c7\u03c8\u03c9\u03ca\u03cb\u03cc\u03cd\u03ce\u03d0\u03d1\u03d5\u03d6\u03d7\u03d9\u03db\u03dd\u03df\u03e1\u03e3\u03e5\u03e7\u03e9\u03eb\u03ed\u03ef\u03f0\u03f1\u03f2\u03f3\u03f5\u0430\u0431\u0432\u0433\u0434\u0435\u0436\u0437\u0438\u0439\u043a\u043b\u043c\u043d\u043e\u043f\u0440\u0441\u0442\u0443\u0444\u0445\u0446\u0447\u0448\u0449\u044a\u044b\u044c\u044d\u044e\u044f\u0450\u0451\u0452\u0453\u0454\u0455\u0456\u0457\u0458\u0459\u045a\u045b\u045c\u045d\u045e\u045f\u0461\u0463\u0465\u0467\u0469\u046b\u046d\u046f\u0471\u0473\u0475\u0477\u0479\u047b\u047d\u047f\u0481\u048b\u048d\u048f\u0491\u0493\u0495\u0497\u0499\u049b\u049d\u049f\u04a1\u04a3\u04a5\u04a7\u04a9\u04ab\u04ad\u04af\u04b1\u04b3\u04b5\u04b7\u04b9\u04bb\u04bd\u04bf\u04c2\u04c4\u04c6\u04c8\u04ca\u04cc\u04ce\u04d1\u04d3\u04d5\u04d7\u04d9\u04db\u04dd\u04df\u04e1\u04e3\u04e5\u04e7\u04e9\u04eb\u04ed\u04ef\u04f1\u04f3\u04f5\u04f9\u0501\u0503\u0505\u0507\u0509\u050b\u050d\u050f\u0561\u0562\u0563\u0564\u0565\u0566\u0567\u0568\u0569\u056a\u056b\u056c\u056d\u056e\u056f\u0570\u0571\u0572\u0573\u0574\u0575\u0576\u0577\u0578\u0579\u057a\u057b\u057c\u057d\u057e\u057f\u0580\u0581\u0582\u0583\u0584\u0585\u0586\u0587\u1e01\u1e03\u1e05\u1e07\u1e09\u1e0b\u1e0d\u1e0f\u1e11\u1e13\u1e15\u1e17\u1e19\u1e1b\u1e1d\u1e1f\u1e21\u1e23\u1e25\u1e27\u1e29\u1e2b\u1e2d\u1e2f\u1e31\u1e33\u1e35\u1e37\u1e39\u1e3b\u1e3d\u1e3f\u1e41\u1e43\u1e45\u1e47\u1e49\u1e4b\u1e4d\u1e4f\u1e51\u1e53\u1e55\u1e57\u1e59\u1e5b\u1e5d\u1e5f\u1e61\u1e63\u1e65\u1e67\u1e69\u1e6b\u1e6d\u1e6f\u1e71\u1e73\u1e75\u1e77\u1e79\u1e7b\u1e7d\u1e7f\u1e81\u1e83\u1e85\u1e87\u1e89\u1e8b\u1e8d\u1e8f\u1e91\u1e93\u1e95\u1e96\u1e97\u1e98\u1e99\u1e9a\u1e9b\u1ea1\u1ea3\u1ea5\u1ea7\u1ea9\u1eab\u1ead\u1eaf\u1eb1\u1eb3\u1eb5\u1eb7\u1eb9\u1ebb\u1ebd\u1ebf\u1ec1\u1ec3\u1ec5\u1ec7\u1ec9\u1ecb\u1ecd\u1ecf\u1ed1\u1ed3\u1ed5\u1ed7\u1ed9\u1edb\u1edd\u1edf\u1ee1\u1ee3\u1ee5\u1ee7\u1ee9\u1eeb\u1eed\u1eef\u1ef1\u1ef3\u1ef5\u1ef7\u1ef9\u1f00\u1f01\u1f02\u1f03\u1f04\u1f05\u1f06\u1f07\u1f10\u1f11\u1f12\u1f13\u1f14\u1f15\u1f20\u1f21\u1f22\u1f23\u1f24\u1f25\u1f26\u1f27\u1f30\u1f31\u1f32\u1f33\u1f34\u1f35\u1f36\u1f37\u1f40\u1f41\u1f42\u1f43\u1f44\u1f45\u1f50\u1f51\u1f52\u1f53\u1f54\u1f55\u1f56\u1f57\u1f60\u1f61\u1f62\u1f63\u1f64\u1f65\u1f66\u1f67\u1f70\u1f71\u1f72\u1f73\u1f74\u1f75\u1f76\u1f77\u1f78\u1f79\u1f7a\u1f7b\u1f7c\u1f7d\u1f80\u1f81\u1f82\u1f83\u1f84\u1f85\u1f86\u1f87\u1f90\u1f91\u1f92\u1f93\u1f94\u1f95\u1f96\u1f97\u1fa0\u1fa1\u1fa2\u1fa3\u1fa4\u1fa5\u1fa6\u1fa7\u1fb0\u1fb1\u1fb2\u1fb3\u1fb4\u1fb6\u1fb7\u1fbe\u1fc2\u1fc3\u1fc4\u1fc6\u1fc7\u1fd0\u1fd1\u1fd2\u1fd3\u1fd6\u1fd7\u1fe0\u1fe1\u1fe2\u1fe3\u1fe4\u1fe5\u1fe6\u1fe7\u1ff2\u1ff3\u1ff4\u1ff6\u1ff7\u2071\u207f\u210a\u210e\u210f\u2113\u212f\u2134\u2139\u213d\u2146\u2147\u2148\u2149\ufb00\ufb01\ufb02\ufb03\ufb04\ufb05\ufb06\ufb13\ufb14\ufb15\ufb16\ufb17\uff41\uff42\uff43\uff44\uff45\uff46\uff47\uff48\uff49\uff4a\uff4b\uff4c\uff4d\uff4e\uff4f\uff50\uff51\uff52\uff53\uff54\uff55\uff56\uff57\uff58\uff59\uff5a'
UPPERCASE = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ\xc0\xc1\xc2\xc3\xc4\xc5\xc6\xc7\xc8\xc9\xca\xcb\xcc\xcd\xce\xcf\xd0\xd1\xd2\xd3\xd4\xd5\xd6\xd8\xd9\xda\xdb\xdc\xdd\xde\u0100\u0102\u0104\u0106\u0108\u010a\u010c\u010e\u0110\u0112\u0114\u0116\u0118\u011a\u011c\u011e\u0120\u0122\u0124\u0126\u0128\u012a\u012c\u012e\u0130\u0132\u0134\u0136\u0139\u013b\u013d\u013f\u0141\u0143\u0145\u0147\u014a\u014c\u014e\u0150\u0152\u0154\u0156\u0158\u015a\u015c\u015e\u0160\u0162\u0164\u0166\u0168\u016a\u016c\u016e\u0170\u0172\u0174\u0176\u0178\u0179\u017b\u017d\u0181\u0182\u0184\u0186\u0187\u0189\u018a\u018b\u018e\u018f\u0190\u0191\u0193\u0194\u0196\u0197\u0198\u019c\u019d\u019f\u01a0\u01a2\u01a4\u01a6\u01a7\u01a9\u01ac\u01ae\u01af\u01b1\u01b2\u01b3\u01b5\u01b7\u01b8\u01bc\u01c4\u01c7\u01ca\u01cd\u01cf\u01d1\u01d3\u01d5\u01d7\u01d9\u01db\u01de\u01e0\u01e2\u01e4\u01e6\u01e8\u01ea\u01ec\u01ee\u01f1\u01f4\u01f6\u01f7\u01f8\u01fa\u01fc\u01fe\u0200\u0202\u0204\u0206\u0208\u020a\u020c\u020e\u0210\u0212\u0214\u0216\u0218\u021a\u021c\u021e\u0220\u0222\u0224\u0226\u0228\u022a\u022c\u022e\u0230\u0232\u0386\u0388\u0389\u038a\u038c\u038e\u038f\u0391\u0392\u0393\u0394\u0395\u0396\u0397\u0398\u0399\u039a\u039b\u039c\u039d\u039e\u039f\u03a0\u03a1\u03a3\u03a4\u03a5\u03a6\u03a7\u03a8\u03a9\u03aa\u03ab\u03d2\u03d3\u03d4\u03d8\u03da\u03dc\u03de\u03e0\u03e2\u03e4\u03e6\u03e8\u03ea\u03ec\u03ee\u03f4\u0400\u0401\u0402\u0403\u0404\u0405\u0406\u0407\u0408\u0409\u040a\u040b\u040c\u040d\u040e\u040f\u0410\u0411\u0412\u0413\u0414\u0415\u0416\u0417\u0418\u0419\u041a\u041b\u041c\u041d\u041e\u041f\u0420\u0421\u0422\u0423\u0424\u0425\u0426\u0427\u0428\u0429\u042a\u042b\u042c\u042d\u042e\u042f\u0460\u0462\u0464\u0466\u0468\u046a\u046c\u046e\u0470\u0472\u0474\u0476\u0478\u047a\u047c\u047e\u0480\u048a\u048c\u048e\u0490\u0492\u0494\u0496\u0498\u049a\u049c\u049e\u04a0\u04a2\u04a4\u04a6\u04a8\u04aa\u04ac\u04ae\u04b0\u04b2\u04b4\u04b6\u04b8\u04ba\u04bc\u04be\u04c0\u04c1\u04c3\u04c5\u04c7\u04c9\u04cb\u04cd\u04d0\u04d2\u04d4\u04d6\u04d8\u04da\u04dc\u04de\u04e0\u04e2\u04e4\u04e6\u04e8\u04ea\u04ec\u04ee\u04f0\u04f2\u04f4\u04f8\u0500\u0502\u0504\u0506\u0508\u050a\u050c\u050e\u0531\u0532\u0533\u0534\u0535\u0536\u0537\u0538\u0539\u053a\u053b\u053c\u053d\u053e\u053f\u0540\u0541\u0542\u0543\u0544\u0545\u0546\u0547\u0548\u0549\u054a\u054b\u054c\u054d\u054e\u054f\u0550\u0551\u0552\u0553\u0554\u0555\u0556\u10a0\u10a1\u10a2\u10a3\u10a4\u10a5\u10a6\u10a7\u10a8\u10a9\u10aa\u10ab\u10ac\u10ad\u10ae\u10af\u10b0\u10b1\u10b2\u10b3\u10b4\u10b5\u10b6\u10b7\u10b8\u10b9\u10ba\u10bb\u10bc\u10bd\u10be\u10bf\u10c0\u10c1\u10c2\u10c3\u10c4\u10c5\u1e00\u1e02\u1e04\u1e06\u1e08\u1e0a\u1e0c\u1e0e\u1e10\u1e12\u1e14\u1e16\u1e18\u1e1a\u1e1c\u1e1e\u1e20\u1e22\u1e24\u1e26\u1e28\u1e2a\u1e2c\u1e2e\u1e30\u1e32\u1e34\u1e36\u1e38\u1e3a\u1e3c\u1e3e\u1e40\u1e42\u1e44\u1e46\u1e48\u1e4a\u1e4c\u1e4e\u1e50\u1e52\u1e54\u1e56\u1e58\u1e5a\u1e5c\u1e5e\u1e60\u1e62\u1e64\u1e66\u1e68\u1e6a\u1e6c\u1e6e\u1e70\u1e72\u1e74\u1e76\u1e78\u1e7a\u1e7c\u1e7e\u1e80\u1e82\u1e84\u1e86\u1e88\u1e8a\u1e8c\u1e8e\u1e90\u1e92\u1e94\u1ea0\u1ea2\u1ea4\u1ea6\u1ea8\u1eaa\u1eac\u1eae\u1eb0\u1eb2\u1eb4\u1eb6\u1eb8\u1eba\u1ebc\u1ebe\u1ec0\u1ec2\u1ec4\u1ec6\u1ec8\u1eca\u1ecc\u1ece\u1ed0\u1ed2\u1ed4\u1ed6\u1ed8\u1eda\u1edc\u1ede\u1ee0\u1ee2\u1ee4\u1ee6\u1ee8\u1eea\u1eec\u1eee\u1ef0\u1ef2\u1ef4\u1ef6\u1ef8\u1f08\u1f09\u1f0a\u1f0b\u1f0c\u1f0d\u1f0e\u1f0f\u1f18\u1f19\u1f1a\u1f1b\u1f1c\u1f1d\u1f28\u1f29\u1f2a\u1f2b\u1f2c\u1f2d\u1f2e\u1f2f\u1f38\u1f39\u1f3a\u1f3b\u1f3c\u1f3d\u1f3e\u1f3f\u1f48\u1f49\u1f4a\u1f4b\u1f4c\u1f4d\u1f59\u1f5b\u1f5d\u1f5f\u1f68\u1f69\u1f6a\u1f6b\u1f6c\u1f6d\u1f6e\u1f6f\u1fb8\u1fb9\u1fba\u1fbb\u1fc8\u1fc9\u1fca\u1fcb\u1fd8\u1fd9\u1fda\u1fdb\u1fe8\u1fe9\u1fea\u1feb\u1fec\u1ff8\u1ff9\u1ffa\u1ffb\u2102\u2107\u210b\u210c\u210d\u2110\u2111\u2112\u2115\u2119\u211a\u211b\u211c\u211d\u2124\u2126\u2128\u212a\u212b\u212c\u212d\u2130\u2131\u2133\u213e\u213f\u2145\uff21\uff22\uff23\uff24\uff25\uff26\uff27\uff28\uff29\uff2a\uff2b\uff2c\uff2d\uff2e\uff2f\uff30\uff31\uff32\uff33\uff34\uff35\uff36\uff37\uff38\uff39\uff3a'



_COLORBASE = {
    "aliceblue": "#f0f8ff",
    "antiquewhite": "#faebd7",
    "aqua": "#00ffff",
    "aquamarine": "#7fffd4",
    "azure": "#f0ffff",
    "beige": "#f5f5dc",
    "bisque": "#ffe4c4",
    "black": "#000000",
    "blanchedalmond": "#ffebcd",
    "blue": "#0000ff",
    "blueviolet": "#8a2be2",
    "brown": "#a52a2a",
    "burlywood": "#deb887",
    "cadetblue": "#5f9ea0",
    "chartreuse": "#7fff00",
    "chocolate": "#d2691e",
    "coral": "#ff7f50",
    "cornflowerblue": "#6495ed",
    "cornsilk": "#fff8dc",
    "crimson": "#dc143c",
    "cyan": "#00ffff",
    "darkblue": "#00008b",
    "darkcyan": "#008b8b",
    "darkgoldenrod": "#b8860b",
    "darkgray": "#a9a9a9",
    "darkgrey": "#a9a9a9",
    "darkgreen": "#006400",
    "darkkhaki": "#bdb76b",
    "darkmagenta": "#8b008b",
    "darkolivegreen": "#556b2f",
    "darkorange": "#ff8c00",
    "darkorchid": "#9932cc",
    "darkred": "#8b0000",
    "darksalmon": "#e9967a",
    "darkseagreen": "#8fbc8f",
    "darkslateblue": "#483d8b",
    "darkslategray": "#2f4f4f",
    "darkslategrey": "#2f4f4f",
    "darkturquoise": "#00ced1",
    "darkviolet": "#9400d3",
    "deeppink": "#ff1493",
    "deepskyblue": "#00bfff",
    "dimgray": "#696969",
    "dimgrey": "#696969",
    "dodgerblue": "#1e90ff",
    "firebrick": "#b22222",
    "floralwhite": "#fffaf0",
    "forestgreen": "#228b22",
    "fuchsia": "#ff00ff",
    "gainsboro": "#dcdcdc",
    "ghostwhite": "#f8f8ff",
    "gold": "#ffd700",
    "goldenrod": "#daa520",
    "gray": "#808080",
    "grey": "#808080",
    "green": "#008000",
    "greenyellow": "#adff2f",
    "honeydew": "#f0fff0",
    "hotpink": "#ff69b4",
    "indianred": "#cd5c5c",
    "indigo": "#4b0082",
    "ivory": "#fffff0",
    "khaki": "#f0e68c",
    "lavender": "#e6e6fa",
    "lavenderblush": "#fff0f5",
    "lawngreen": "#7cfc00",
    "lemonchiffon": "#fffacd",
    "lightblue": "#add8e6",
    "lightcoral": "#f08080",
    "lightcyan": "#e0ffff",
    "lightgoldenrodyellow": "#fafad2",
    "lightgray": "#d3d3d3",
    "lightgrey": "#d3d3d3",
    "lightgreen": "#90ee90",
    "lightpink": "#ffb6c1",
    "lightsalmon": "#ffa07a",
    "lightseagreen": "#20b2aa",
    "lightskyblue": "#87cefa",
    "lightslategray": "#778899",
    "lightslategrey": "#778899",
    "lightsteelblue": "#b0c4de",
    "lightyellow": "#ffffe0",
    "lime": "#00ff00",
    "limegreen": "#32cd32",
    "linen": "#faf0e6",
    "magenta": "#ff00ff",
    "maroon": "#800000",
    "mediumaquamarine": "#66cdaa",
    "mediumblue": "#0000cd",
    "mediumorchid": "#ba55d3",
    "mediumpurple": "#9370d8",
    "mediumseagreen": "#3cb371",
    "mediumslateblue": "#7b68ee",
    "mediumspringgreen": "#00fa9a",
    "mediumturquoise": "#48d1cc",
    "mediumvioletred": "#c71585",
    "midnightblue": "#191970",
    "mintcream": "#f5fffa",
    "mistyrose": "#ffe4e1",
    "moccasin": "#ffe4b5",
    "navajowhite": "#ffdead",
    "navy": "#000080",
    "oldlace": "#fdf5e6",
    "olive": "#808000",
    "olivedrab": "#6b8e23",
    "orange": "#ffa500",
    "orangered": "#ff4500",
    "orchid": "#da70d6",
    "palegoldenrod": "#eee8aa",
    "palegreen": "#98fb98",
    "paleturquoise": "#afeeee",
    "palevioletred": "#d87093",
    "papayawhip": "#ffefd5",
    "peachpuff": "#ffdab9",
    "peru": "#cd853f",
    "pink": "#ffc0cb",
    "plum": "#dda0dd",
    "powderblue": "#b0e0e6",
    "purple": "#800080",
    "red": "#ff0000",
    "rosybrown": "#bc8f8f",
    "royalblue": "#4169e1",
    "saddlebrown": "#8b4513",
    "salmon": "#fa8072",
    "sandybrown": "#f4a460",
    "seagreen": "#2e8b57",
    "seashell": "#fff5ee",
    "sienna": "#a0522d",
    "silver": "#c0c0c0",
    "skyblue": "#87ceeb",
    "slateblue": "#6a5acd",
    "slategray": "#708090",
    "slategrey": "#708090",
    "snow": "#fffafa",
    "springgreen": "#00ff7f",
    "steelblue": "#4682b4",
    "tan": "#d2b48c",
    "teal": "#008080",
    "thistle": "#d8bfd8",
    "tomato": "#ff6347",
    "turquoise": "#40e0d0",
    "violet": "#ee82ee",
    "wheat": "#f5deb3",
    "white": "#ffffff",
    "whitesmoke": "#f5f5f5",
    "yellow": "#ffff00",
    "yellowgreen": "#9acd32"
}






