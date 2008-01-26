# -*- coding: iso-8859-1 -*-

import string, locale, codecs, sets, os, os.path, traceback

from xml.dom import minidom

from StringOps import utf8Enc, loadEntireTxtFile, writeEntireTxtFile, pathEnc


CASEMODE_UPPER_INSIDE = 0   # Sort upper case inside like aAbBcC
CASEMODE_UPPER_FIRST = 1    # Sort upper case first like ABCabc


def tt(s):
    """
    Currently only dummy: Lookup text in message table and return
    localized message
    """
    return s


def tt_noop(s):
    return s


# Factory functions for collators. Classes shouldn't be called directly

def getCollatorByString(locStr, caseMode=None):
    """
    locStr -- String describing the locale of the Collator
    caseMode --  (the flag isn't
            guaranteed to be respected
    """
    if locStr.lower() == u"c":
        return _CCollator(caseMode)
    else:
        if locStr.lower() == u"default":
            locStr = u""

        if caseMode == CASEMODE_UPPER_FIRST:
            return _PythonCollatorUppercaseFirst(locStr)
        else:
            return _PythonCollator(locStr)


def getCCollator(caseMode=None):
    """
    Returns a basic collator for 'C' locale. The only collator guaranteed to
    exist.
    caseMode -- True iff collator should be case sensitive (the flag isn't
            guaranteed to be respected
    """
    return _CCollator(caseMode)



class AbstractCollator:
    """
    Abstract base class for collator functionality.

    All string parameters to the methods must (or should at least) be
    unicode strings.
    """

    def sort(self, lst, ascend=True):
        """
        Sort list lst of unicode strings inplace alphabetically
        (as defined by strcoll() method).

        ascend -- If True sort ascending, descending otherwise
        """
        lst.sort(self.strcoll)
        if not ascend:
            lst.reverse()

    def sortByKey(self, lst, ascend=True):
        """
        Similar to sort(), but lst items are sequences where only the first
        element is taken for sorting.
        """
        lst.sort(self.strcollByKey)
        if not ascend:
            lst.reverse()


    def strcoll(self, left, right):
        """
        Compare strings left and right and return integer value smaller, greater or
        equal 0 following the same rules as the built-in cmp() function
        """
        raise NotImplementedError   # abstract


    def strcollByKey(self, left, right):
        """
        Compare tuples left and right (first elements only) and return integer
        value smaller, greater or equal 0 following the same rules as the
        built-in cmp() function.
        """
        return self.strcoll(left[0], right[0])


    def strxfrm(self, s):
        """
        Returns a byte string usable as byte sort key for string s. It must
        fulfill the condition:
        
        For all unicode strings a, b:
        cmp(strxfrm(a), strxfrm(b)) == strcoll(a, b)
        """
        raise NotImplementedError   # abstract

#     def normCase(self, s):
#         """
#         Normalize case for string s. It is recommended to just return
#         the UTF-8 encoding of the "lowered" string s. This should be even
#         true if the collator is case-sensitive.
#         
#         The collator must fulfill:
#         For all unicode strings a, b:
#         
#         1. normCase(a) == normCase(b) iff a == b or a is equal b except for case.
#         2. normCase(a) is part of normCase(b) iff a is part of b (at least if
#             case is ignored)
#         
#         """
#         assert 0  # abstract


# TODO case insensitivity

class _CCollator(AbstractCollator):
    """
    Collator for case sensitive "C" locale
    """
    def __init__(self, caseMode):
        self.caseMode = caseMode


    def sort(self, lst, ascend=True):
        """
        Sort list lst inplace.
        ascend -- If True sort ascending, descending otherwise
        """
        lst.sort()
        if not ascend:
            lst.reverse()
            
    def strcoll(self, left, right):
        """
        Compare left and right and return integer value smaller, greater or
        equal 0
        """
        return cmp(left, right)

    def strxfrm(self, s):
        """
        Returns a byte string usable as byte sort key for string s
        """
        return utf8Enc(s)[0]


#     def normCase(self, s):
#         """
#         Normalize case for unicode string s and return byte string
#         """
#         result = []
#         for c in s:
#             o = ord(c)
#             if o < 65 or o > 90:
#                 result.append(c)
#             else:
#                 result.append(unichr(o+32))
# 
#         return utf8Enc(u"".join(result))[0]
        



class _PythonCollator(AbstractCollator):
    """
    Uses Python's localization support from the "locale" module.
    This class pretends to allow the use of multiple locale settings
    at once, but Python doesn't provide that.
    """
    def __init__(self, locStr):
        """
        """
        self.locStr = locStr
        self.prevLocale = locale.setlocale(locale.LC_ALL, self.locStr)

    def strcoll(self, left, right):
        return locale.strcoll(left, right)
        
    def strxfrm(self, s):
        return locale.strxfrm(s)

#     def normCase(self, s):
#         return utf8Enc(s.lower)[0]


class _PythonCollatorUppercaseFirst(AbstractCollator):
    """
    Uses Python's localization support from the "locale" module.
    This class pretends to allow the use of multiple locale settings
    at once, but Python doesn't provide that.
    """
    def __init__(self, locStr):
        """
        caseMode -- ignored here
        """
        self.locStr = locStr
        self.prevLocale = locale.setlocale(locale.LC_ALL, self.locStr)

    def strcoll(self, left, right):
        ml = min(len(left), len(right))
        for i in xrange(ml):
            lv = 0
            if left[i].islower():
                lv = 1
    
            rv = 0
            if right[i].islower():
                rv = 1
                
            comp = lv - rv
            
            if comp != 0:
                return comp
    
            comp = locale.strcoll(left[i].lower(), right[i].lower())
            if comp != 0:
                return comp
            
        if len(right) > ml:
            return 1
        if len(left) > ml:
            return -1
            
        return 0

        
    def strxfrm(self, s):
        assert 0 # Not properly implemented

        return locale.strxfrm(s)



# Function taken from standard lib Python 2.4 tool msgfmt.py, written by
# Martin v. Löwis <loewis@informatik.hu-berlin.de>
def buildMessageDict(filename):
    messages = {}

    def add(id, ustr, fuzzy):
        "Add a non-fuzzy translation to the dictionary."
        if not fuzzy and ustr:
            messages[id] = ustr

    if filename.endswith('.po') or filename.endswith('.pot'):
        infile = filename
    else:
        infile = filename + '.po'

    try:
        lines = codecs.open(pathEnc(infile), "r", "utf-8").readlines()
    except IOError, msg:
#         print >> sys.stderr, msg
        raise

    # Strip BOM
    if len(lines) > 0 and lines[0].startswith(u"\ufeff"):
        lines[0] = lines[0][1:]

    ID = 1
    STR = 2

    section = None
    fuzzy = 0

    # Parse the catalog
    lno = 0
    for l in lines:
        lno += 1
        # If we get a comment line after a msgstr, this is a new entry
        if l[0] == u'#' and section == STR:
            add(msgid, msgstr, fuzzy)
            section = None
            fuzzy = 0
        # Record a fuzzy mark
        if l[:2] == u'#,' and u'fuzzy' in l:
            fuzzy = 1
        # Skip comments
        if l[0] == u'#':
            continue
        # Now we are in a msgid section, output previous section
        if l.startswith(u'msgid'):
            if section == STR:
                add(msgid, msgstr, fuzzy)
            section = ID
            l = l[5:]
            msgid = msgstr = u''
        # Now we are in a msgstr section
        elif l.startswith(u'msgstr'):
            section = STR
            l = l[6:]
        # Skip empty lines
        l = l.strip()
        if not l:
            continue
        # XXX: Does this always follow Python escape semantics?
#         print "eval", repr(l)
        l = eval(l)
        if type(l) is str:
            l = l.decode("utf-8")

        if section == ID:
            msgid += l
        elif section == STR:
#             print "code", repr((msgstr, l))
            msgstr += l
        else:
            print >> sys.stderr, 'Syntax error on %s:%d' % (infile, lno), \
                  'before:'
            print >> sys.stderr, l
            raise SyntaxError('Syntax error on %s:%d' % (infile, lno) + 
                    ' before: ' + l)
            # sys.exit(1)
    # Add last entry
    if section == STR:
        add(msgid, msgstr, fuzzy)

    return messages




i18nLangList = [("C", u"English")]

def loadLangList(appDir):
    global i18nLangList
    
    result = []

    try:
        data = loadEntireTxtFile(os.path.join(appDir, "langlist.txt"))
        data = data.decode("utf-8")
        
        # Remove BOM if present
        if data.startswith(u"\ufeff"):
            data = data[1:]
        
        for line in data.split("\n"):
            line = line.strip()
            try:
                localeStr, langTitle = line.split(u"\t", 1)
                localeStr = localeStr.encode("ascii")
                
                result.append((localeStr, langTitle))
            except:
                # Bad line
                pass
        
        i18nLangList = result
        return

    except:
        i18nLangList = [("C", u"English")]


def getLangList():
    global i18nLangList
    return i18nLangList


def findLangListIndex(localeStr):
    global i18nLangList
    
    localeStr = localeStr.lower()

    for i, lle in enumerate(i18nLangList):
        if localeStr == lle[0].lower():
            return i
    
    # Simple method failed, so try expanding locale strings
    for i, lle in enumerate(i18nLangList):
        locs = (ls.lower() for ls in _expand_lang(lle[0]))
        if localeStr in locs:
            return i
    
    # Nothing helped
    return -1


def getLangTitleForLocaleStr(localeStr):
    global i18nLangList

    i = findLangListIndex(localeStr)
    if i == -1:
        return u"<'%s'>" % localeStr
    else:
        return i18nLangList[i][1]




# Function taken from Python 2.4 standard library module gettext.py
def _expand_lang(locale):
    from locale import normalize
    locale = normalize(locale)
    COMPONENT_CODESET   = 1 << 0
    COMPONENT_TERRITORY = 1 << 1
    COMPONENT_MODIFIER  = 1 << 2
    # split up the locale into its base components
    mask = 0
    pos = locale.find('@')
    if pos >= 0:
        modifier = locale[pos:]
        locale = locale[:pos]
        mask |= COMPONENT_MODIFIER
    else:
        modifier = ''
    pos = locale.find('.')
    if pos >= 0:
        codeset = locale[pos:]
        locale = locale[:pos]
        mask |= COMPONENT_CODESET
    else:
        codeset = ''
    pos = locale.find('_')
    if pos >= 0:
        territory = locale[pos:]
        locale = locale[:pos]
        mask |= COMPONENT_TERRITORY
    else:
        territory = ''
    language = locale
    ret = []
    for i in range(mask+1):
        if not (i & ~mask):  # if all components for this combo exist ...
            val = language
            if i & COMPONENT_TERRITORY: val += territory
            if i & COMPONENT_CODESET:   val += codeset
            if i & COMPONENT_MODIFIER:  val += modifier
            ret.append(val)
    ret.reverse()
    return ret



# The global internationalization dictionary
i18nDict = {}
i18nPoPath = None
i18nLocale = "C"


def getI18nEntryDummy(key):
    """
    The function called with _() if dictionary is empty.
    A double questionmark "??" (the so-called discriminator)
    stops reading and only returns the part before it.
    """
    return key.split(u"??", 1)[0]


def getI18nEntry(key):
    """
    The function called with _() if dictionary is filled.
    """
    global i18nDict
    
    result = i18nDict.get(key)
    if result is None or result == u"":
        return key.split(u"??", 1)[0]
    else:
        return result


def getGuiLocale():
    global i18nLocale
    return i18nLocale




# def findI18nBaseFile(appDir, locStr=None):
#     """
#     Find the basic .po file containing the translated strings and return
#     path to it or None if no translation file found.
#     """
#     if not locStr:
#         locStr = locale.getdefaultlocale()[0]
# 
#     locList = _expand_lang(locStr)
#     
#     for locEntry in locList:
#         if locEntry.upper() == "C":
#             # No translation
#             return None
#         
#         path = os.path.join(appDir, "WikidPad_" + locEntry + ".po")
#         if not os.path.exists(path):
#             continue
#         else:
#             return path
#         
#     return None


def loadI18nDict(appDir, locStr=None):
    """
    Load and install the dictionary for the locale locStr

    appDir -- Application directory of WikidPad.
    """
    global i18nDict, i18nPoPath, i18nLocale

    if not locStr:
        locStr = locale.getdefaultlocale()[0]

    if locStr is None:
        locStr = ""

    locList = _expand_lang(locStr)

    for locEntry in locList:
        if locEntry.upper() == "C":
            # No translation
            i18nDict = {}
            __builtins__["_"] = getI18nEntryDummy
            i18nPoPath = None
            i18nLocale = "C"
            return
        
        path = os.path.join(appDir, "WikidPad_" + locEntry + ".po")
        if not os.path.exists(pathEnc(path)):
            continue
        
        try:
            md = buildMessageDict(path)
            i18nDict = md
            __builtins__["_"] = getI18nEntry
            i18nPoPath = path
            i18nLocale = locEntry
            return
        except IOError:
            traceback.print_exc()
            continue

    # No translation
    i18nDict = {}
    __builtins__["_"] = getI18nEntryDummy
    i18nPoPath = None
    i18nLocale = "C"



# def _loadEntireFile(filename):
#     """
#     Load entire file (text mode) and return its content.
#     """
#     rf = open(filename, "rU")
#     try:
#         result = rf.read()
#         return result
#     finally:
#         rf.close()
# 
# 
# def _writeEntireFile(filename, content):
#     """
#     Write entire file (text mode).
#     """
#     rf = open(filename, "w")
#     try:
#         rf.write(content)
#         return
#     finally:
#         rf.close()


# TODO: Cache
def getI18nXrcData(appDir, globalConfigSubDir, baseXrcName):
    """
    Returns the XML data of translated XRC file.
    This function assumes that loadI18nDict() was previously
    called with same appDir.
    """
    global i18nPoPath, i18nLocale
    
    if i18nPoPath is None:
        # No translation
        return loadEntireTxtFile(os.path.join(appDir, baseXrcName + ".xrc"))

    # Retrieve modification time of .po and .xrc file to compare with cache
    # Cache is only valid if newer than both
    poModTime = os.stat(pathEnc(i18nPoPath)).st_mtime
    poModTime2 = os.stat(pathEnc(os.path.join(appDir, baseXrcName + ".xrc"))).st_mtime

    poModTime = max(poModTime, poModTime2)

    # First test for cache in appDir
    try:
        cachePath = os.path.join(appDir,
                baseXrcName + "_" + i18nLocale + ".xrc")

        if os.path.exists(pathEnc(cachePath)) and \
                os.stat(pathEnc(cachePath)).st_mtime > poModTime:
            # Valid cache found
            return loadEntireTxtFile(cachePath)
    except:
        traceback.print_exc()  # Really?


    # then test for cache in globalConfigSubDir
    try:
        cachePath = os.path.join(globalConfigSubDir,
                baseXrcName + "_" + i18nLocale + ".xrc")

        if os.path.exists(pathEnc(cachePath)) and \
                os.stat(pathEnc(cachePath)).st_mtime > poModTime:
            # Valid cache found
            return loadEntireTxtFile(cachePath)
    except:
        traceback.print_exc()  # Really?


    # No valid cache -> build content

    untranslated = loadEntireTxtFile(os.path.join(appDir, baseXrcName + ".xrc"))

    xmlDoc = minidom.parseString(untranslated)
    elementsContainingText = xmlDoc.getElementsByTagName("label") + \
            xmlDoc.getElementsByTagName("title") + \
            xmlDoc.getElementsByTagName("item")

    for le in elementsContainingText:
        childs = le.childNodes
        if len(childs) != 1:
            continue

        child = childs[0]
        if child.nodeType != child.TEXT_NODE:
            continue

        child.data = _(child.data)

    translated = xmlDoc.toxml("utf-8")

    xmlDoc.unlink()


    # The following conversion is only needed when running a Windows
    # binary created by py2exe with wxPython 2.6.
    # Otherwise some mysterious unicode error may ocurr.

    translated = translated.decode("utf-8")
    result = []
    for c in translated:
        o = ord(c)
        if o > 127:
            result.append("&#%i;" % o)
        else:
            result.append(chr(o))

    translated = "".join(result)



    # Try to store content as cache in appDir
    try:
        cachePath = os.path.join(appDir,
                baseXrcName + "_" + i18nLocale + ".xrc")
        
        writeEntireTxtFile(cachePath, translated)
        
        return translated
    except:
        pass
    
    # Try to store content as cache in globalConfigSubDir
    try:
        cachePath = os.path.join(globalConfigSubDir,
                baseXrcName + "_" + i18nLocale + ".xrc")
        
        writeEntireTxtFile(cachePath, translated)
        
        return translated
    except:
        pass
    
    
    # Cache saving failed

    return translated




# TODO Support for plugins!
    

