from struct import pack, unpack
import io

import Consts

from .StringOps import utf8Dec, utf8Enc, strToBool, base64BlockEncode, \
        base64BlockDecode

from .WikiExceptions import *



# ---------- Support for serializing values into binary data (and back) ----------
# Especially used in SearchAndReplace.py, class SearchReplaceOperation

class SerializeStream:
    def __init__(self, fileObj=None, byteBuf=None, readMode=True):
        """
        fileObj -- file-like object to wrap.
        byteBuf -- if not None, ignore fileObj, read from byteBuf
                instead or write to a new byte buffer depending
                on readMode. Use getBytes() to retrieve written bytes
        readMode -- True; read from fileobj, False: write to fileobj
        """
        self.fileObj = fileObj 
        self.readMode = readMode

        if byteBuf is not None:
            if self.readMode:
                self.fileObj = io.BytesIO(byteBuf)
            else:
                self.fileObj = io.BytesIO()

    def isReadMode(self):
        """
        Returns True iff reading from fileObj, False iff writing to fileObj
        """
        return self.readMode
        
    def setBytesToRead(self, b):
        """
        Sets a byte object to read from via BytesIO
        """
        self.fileObj = io.BytesIO(b)
        self.readMode = True

        
    def useBytesToWrite(self):
        """
        Sets the stream to write mode writing to a byte buffer via BytesIO
        """
        self.fileObj = io.BytesIO()
        self.readMode = False

        
    def getBytes(self):
        """
        If fileObj is a BytesIO object, call this to retrieve the stored
        bytes after write operations are finished, but before close() is
        called
        """
        return self.fileObj.getvalue()
        
    
    def writeBytes(self, b):
        self.fileObj.write(b)
        
    def readBytes(self, l):
        return self.fileObj.read(l)


    def serUint8(self, val):
        """
        Serialize 8bit unsigned integer val. This means: if stream is in read
        mode, val is ignored and the int read from stream is returned,
        if in write mode, val is written and returned
        """
        if self.isReadMode():
            return unpack(">B", self.readBytes(1))[0]   # Why big-endian? Why not? 
        else:
            self.writeBytes(pack(">B", val))
            return val


    def serUint32(self, val):
        """
        Serialize 32bit unsigned integer val. This means: if stream is in read
        mode, val is ignored and the int read from stream is returned,
        if in write mode, val is written and returned
        """
        if self.isReadMode():
            return unpack(">I", self.readBytes(4))[0]   # Why big-endian? Why not? 
        else:
            self.writeBytes(pack(">I", val))
            return val


    def serInt32(self, val):
        """
        Serialize 32bit signed integer val. This means: if stream is in read
        mode, val is ignored and the int read from stream is returned,
        if in write mode, val is written and returned
        """
        if self.isReadMode():
            return unpack(">i", self.readBytes(4))[0]   # Why big-endian? Why not? 
        else:
            self.writeBytes(pack(">I", val))
            return val


    def serByteBlock(self, s):
        """
        Serialize byte block s, including length. This means: if stream is in read
        mode, s is ignored and the string read from stream is returned,
        if in write mode, s is written and returned
        """
        l = self.serUint32(len(s))

        if self.isReadMode():
            return self.readBytes(l)
        else:
            self.writeBytes(s)
            return s


    def serUniUtf8(self, us):
        """
        Serialize unicode string, encoded as UTF-8
        """
        if self.isReadMode():
            return utf8Dec(self.serByteBlock(b""), "replace")[0]
        else:
            self.serByteBlock(utf8Enc(us)[0])
            return us


    def serBool(self, tv):
        """
        Serialize boolean truth value
        """
        if self.isReadMode():
            b = self.readBytes(1)
            return b != b"\0"
        else:
            if tv:
                self.writeBytes(b"1")
            else:
                self.writeBytes(b"\0")
            
            return tv

    def serArrUniUtf8(self, aus):
        """
        Serialize array of unicode strings, encoded as UTF-8
        """
        l = self.serUint32(len(abs)) # Length of array
        
        if self.isReadMode() and l != len(abs):
            abs = [""] * l

        for i in range(l):
            abs[i] = self.serUniUtf8(abs[i])
            
        return abs


    def serArrByteBlock(self, aus):
        """
        Serialize array of byte blocks
        """
        l = self.serUint32(len(abs)) # Length of array
        
        if self.isReadMode() and l != len(abs):
            abs = [b""] * l

        for i in range(l):
            abs[i] = self.serByteBlock(abs[i])

        return abs

            
#     def serArrString(self, abs):
#         """
#         Serialize array of byte strings
#         """
#         l = self.serUint32(len(abs)) # Length of array
# 
#         if self.isReadMode() and l != len(abs):
#             abs = [""] * l
# 
#         for i in range(l):
#             abs[i] = self.serString(abs[i])
#             
#         return abs
        
    def serArrUint32(self, an):
        """
        Serialize array of unsigned integer 32 bit
        """
        l = self.serUint32(len(an)) # Length of array

        if self.isReadMode() and l != len(an):
            an = [0] * l

        for i in range(l):
            an[i] = self.serUint32(an[i])
            
        return an

    def close(self):
        """
        Close stream and underlying file object
        """
        self.fileObj.close()



def findXmlElementFlat(xmlNode, tag, excOnFail=True):
    """
    Search children of xmlNode until finding an element with tag  tag  and
    return it. Raises SerializationException if not found (excOnFail==True) or
    returns None (excOnFail==False).
    """
    for subNode in xmlNode.childNodes:
        if subNode.nodeType != subNode.ELEMENT_NODE:
            continue
        
        if subNode.tagName == tag:
            return subNode
    
    if excOnFail:
        raise SerializationException(
                "XML conversion: Element '%s' not found inside '%s'" %
                (tag, xmlNode.tagName))
    else:
        return None


def iterXmlElementFlat(xmlNode, tag):
    """
    Return iterator through all children of xmlNode with tag  tag.
    It is safe to add/modify/remove childNodes of xmlNode during use
    of the iterator.
    """
    for subNode in xmlNode.childNodes[:]:
        if subNode.nodeType != subNode.ELEMENT_NODE:
            continue
        
        if subNode.tagName == tag:
            yield subNode


def findOrAppendXmlElementFlat(xmlNode, xmlDoc, tag):
    """
    If inside xmlNode exists an element with tag already, return that,
    otherwise create and append to xmlNode a new child element with this tag.
    """
    subNode = findXmlElementFlat(xmlNode, tag, False)
    if subNode is not None:
        return subNode

    subNode = xmlDoc.createElement(tag)
    xmlNode.appendChild(subNode)

    return subNode



def serToXmlUnicode(xmlNode, xmlDoc, tag, data, replace=False):
    if replace:
        subNode = findXmlElementFlat(xmlNode, tag, False)
        if subNode is not None:
            xmlNode.removeChild(subNode)

    subNode = xmlDoc.createElement(tag)

    subNode.appendChild(xmlDoc.createTextNode(data))
    xmlNode.appendChild(subNode)


def serFromXmlUnicode(xmlNode, tag, default=""):
    subNode = findXmlElementFlat(xmlNode, tag, False)
    if subNode is None:
        return default

    child = subNode.firstChild
    if child is None:
        return default
    return child.data


def serToXmlBoolean(xmlNode, xmlDoc, tag, data, replace=False):
    serToXmlUnicode(xmlNode, xmlDoc, tag, str(repr(bool(data))),
            replace=replace)


def serFromXmlBoolean(xmlNode, tag, default=None):
    result = serFromXmlUnicode(xmlNode, tag, None)
    if result is None:
        return default

    return strToBool(result)


def serToXmlInt(xmlNode, xmlDoc, tag, data, replace=False):
    serToXmlUnicode(xmlNode, xmlDoc, tag, str(repr(data)),
            replace=replace)

def serFromXmlInt(xmlNode, tag, default=None):
    result = serFromXmlUnicode(xmlNode, tag, None)
    if result is None:
        return default
    try:
        return int(result)
    except ValueError:
        return default



_TYPE_TO_TYPENAME = (
        (bool, "bool"),
        (int, "int"),
        (float, "float"),
        (str, "unicode"),
        (Consts.BYTETYPES, "str"),
    )



_TYPENAME_TO_FACTORY = {
        "int": int,
        "long": int,
        "float": float,
        "unicode": str,
        "str": base64BlockDecode,
        "bool": strToBool,
    }


def convertTupleToXml(xmlNode, xmlDoc, addOpt):
#     mainEl = xmlDoc.createElement(u"addoptions")
#     mainEl.setAttribute(u"type", u"simpletuple")
    for opt in addOpt:
        dtype = None
        for t, tn in _TYPE_TO_TYPENAME:
            if isinstance(opt, t):
                dtype = tn
                break

        if dtype is None:
            raise SerializationException(
                    "XML conversion: Unknown item type in tuple: " + repr(opt))

        if dtype == "str":
            # Maybe binary data, so do base64 encoding
            opt = base64BlockEncode(opt)

        subEl = xmlDoc.createElement("item")
        subEl.setAttribute("type", dtype)

        subEl.appendChild(xmlDoc.createTextNode(str(opt)))

        xmlNode.appendChild(subEl)



def convertTupleFromXml(xmlNode):
#     # TODO More error checking
#     if mainEl.tagName != u"addoptions":
#         raise SerializationException(
#                 "Unknown XML element " + repr(mainEl.tagName) +
#                 ", expected 'addoptions'")
# 
#     if mainEl.getAttribute("type") != u"simpletuple":
#         raise SerializationException(
#                 "XML element 'addoptions' can only have type attribute 'simpletuple', found " +
#                 repr(mainEl.getAttribute("type")) +" instead")

    result = []
    for subEl in iterXmlElementFlat(xmlNode, "item"):
        dtype = subEl.getAttribute("type")
        fact = _TYPENAME_TO_FACTORY.get(dtype)
        if fact is None:
            raise SerializationException(
                    "XML conversion: XML element 'item' can't have type attribute '" +
                    repr(dtype))

        data = subEl.firstChild.data
        result.append(fact(data))

    return tuple(result)

