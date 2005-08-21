## -*- coding: ISO-8859-1 -*-

"""
Various string operations, like unicode encoding/decoding,
creating diff information for plain byte sequences
"""



import difflib, codecs

from struct import pack, unpack

from codecs import BOM_UTF8, BOM_UTF16_BE, BOM_UTF16_LE

from Configuration import isUnicode


# To generate dependencies for py2exe
import encodings.utf_8, encodings.latin_1, encodings.mbcs



# ---------- Encoding conversion ----------


utf8Enc = codecs.getencoder("utf-8")
utf8Dec = codecs.getdecoder("utf-8")
mbcsEnc = codecs.getencoder("mbcs")
mbcsDec = codecs.getdecoder("mbcs")
utf8Reader = codecs.getreader("utf-8")
utf8Writer = codecs.getwriter("utf-8")
mbcsReader = codecs.getreader("mbcs")
mbcsWriter = codecs.getwriter("mbcs")

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
        Convert unicode text to a format usable for wx GUI
        """
        return mbcsDec(text, "replace")[0]


def strToBool(s, default=False):
    """
    Try to interpret string (or unicode) s as
    boolean, return default if string can't be
    interpreted
    """
    
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
        
        

# ---------- Handling  diff information ----------


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
    return applyCompact(a, binCompactToCompact(bops))


def getBinCompactForDiff(a, b):
    """
    Return the binary compact codes to change string a to b
    """

    sm = difflib.SequenceMatcher(None, a, b)
    ops = sm.get_opcodes()
    return compactToBinCompact(difflibToCompact(ops, b))

