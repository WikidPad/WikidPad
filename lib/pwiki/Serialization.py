from struct import pack, unpack
import cStringIO as StringIO

from StringOps import utf8Dec, utf8Enc



# ---------- Support for serializing values into binary data (and back) ----------
# Especially used in SearchAndReplace.py, class SearchReplaceOperation

class SerializeStream:
    def __init__(self, fileObj=None, stringBuf=None, readMode=True):
        """
        fileObj -- file-like object to wrap.
        stringBuf -- if not None, ignore fileObj, read from stringBuf
                instead or write to a new string buffer depending
                on readMode. Use getBytes() to retrieve written bytes
        readMode -- True; read from fileobj, False: write to fileobj
        """
        self.fileObj = fileObj 
        self.readMode = readMode

        if stringBuf is not None:
            if self.readMode:
                self.fileObj = StringIO.StringIO(stringBuf)
            else:
                self.fileObj = StringIO.StringIO()

    def isReadMode(self):
        """
        Returns True iff reading from fileObj, False iff writing to fileObj
        """
        return self.readMode
        
    def setBytesToRead(self, b):
        """
        Sets a string to read from via StringIO
        """
        self.fileObj = StringIO.StringIO(b)
        self.readMode = True

        
    def useBytesToWrite(self):
        """
        Sets the stream to write mode writing to a byte buffer (=string)
        via StringIO
        """
        self.fileObj = StringIO.StringIO()
        self.readMode = False

        
    def getBytes(self):
        """
        If fileObj is a StringIO object, call this to retrieve the stored
        string after write operations are finished, but before close() is
        called
        """
        return self.fileObj.getvalue()
        
    
    def writeBytes(self, b):
        self.fileObj.write(b)
        
    def readBytes(self, l):
        return self.fileObj.read(l)
        
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


    def serString(self, s):
        """
        Serialize string s, including length. This means: if stream is in read
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
            return utf8Dec(self.serString(""), "replace")[0]
        else:
            self.serString(utf8Enc(us)[0])
            return us


    def serBool(self, tv):
        """
        Serialize boolean truth value
        """
        if self.isReadMode():
            b = self.readBytes(1)
            return b != "\0"
        else:
            if tv:
                self.writeBytes("1")
            else:
                self.writeBytes("\0")
            
            return tv
            
    def serArrString(self, as):
        """
        Serialize array of byte strings
        """
        l = self.serUint32(len(as)) # Length of array

        if self.isReadMode() and l != len(as):
            as = [""] * l

        for i in xrange(l):
            as[i] = self.serString(as[i])
            
        return as


    def close(self):
        """
        Close stream and underlying file object
        """
        self.fileObj.close()

