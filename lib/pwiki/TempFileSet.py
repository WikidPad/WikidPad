"""
Temporary file management
"""
import sys, os, os.path, traceback, tempfile, urllib
from codecs import BOM_UTF8    # , BOM_UTF16_BE, BOM_UTF16_LE

import wx

from .StringOps import urlFromPathname, relativeFilePath, escapeHtml, pathEnc


class TempFileSet:
    """
    A TempFileSet allows to create temporary files and stores their
    pathes so that they can all be deleted at once when needed no more.

    The files are not automatically deleted when the object is garbage
    collected.
    """

    def __init__(self):
        self.fileSet = set()
        self.preferredPath = None
        self.preferredRelativeTo = None

    def getPreferredPath(self):
        return self.preferredPath

    def setPreferredPath(self, preferredPath):
        """
        Set the preferred path which is used as dir argument to mkstemp()
        if no dir is given.
        
        It is also used for calls to createTempFile()/createTempUrl().
        """
        self.preferredPath = preferredPath        


    def getPreferredRelativeTo(self):
        return self.preferredRelativeTo

    def setPreferredRelativeTo(self, preferredRelativeTo):
        """
        Set the preferred relativeTo for calls to
        createTempFile()/createTempUrl().
        """
        self.preferredRelativeTo = preferredRelativeTo

    def addFile(self, fullPath):
        """
        Adds the file described by fullPath to the file set so it will be
        deleted automatically when clear() is called.
        """
        self.fileSet.add(fullPath)


    def mkstemp(self, suffix=None, prefix=None, path=None, text=False):
        """
        Same as tempfile.mkstemp from standard library, but
        stores returned path also in the set and does automatic path encoding.
        """
        if path is None:
            path = self.preferredPath
            if path is None:
                path = getDefaultTempFilePath()
                
            if path is not None and not os.path.exists(pathEnc(path)):
                try:
                    os.makedirs(pathEnc(path))
                except OSError:
                    path = None

        fd, fullPath = tempfile.mkstemp(pathEnc(suffix), pathEnc(prefix),
                pathEnc(path), text)

        self.fileSet.add(fullPath)

        return fd, fullPath


    def clear(self):
        """
        Delete all files of which the path is stored in the set
        """
        for fullPath in self.fileSet:
            try:
                os.remove(pathEnc(fullPath))
            except:
                pass
                # TODO: Option to show also these exceptions
                # traceback.print_exc()

        self.fileSet.clear()


    def reset(self):
        """
        Remove all entries from the internal file set without deleting
        the actual files
        """
        self.fileSet.clear()


    def getRelativePath(self, relativeTo, fullPath):
        """
        Returns path relative to relativeTo. If relativeTo is ""
        the path is absolute, if it is None the preferred relativeTo
        is used.
        """
        if relativeTo is None:
            relativeTo = self.preferredRelativeTo
        
        return getRelativePath(relativeTo, fullPath)
        
    
    def getRelativeUrl(self, relativeTo, fullPath, pythonUrl=False):
        """
        Returns URL relative to relativeTo. If relativeTo is ""
        the URL is absolute, if it is None the preferred relativeTo
        is used.
        """
        if relativeTo is None:
            relativeTo = self.preferredRelativeTo
        
        return getRelativeUrl(relativeTo, fullPath, pythonUrl=pythonUrl)
        

    def createTempFile(self, content, suffix, path=None, relativeTo=None):
        """
        Specialized function. Creates a file in directory path, fills it with 
        content (byte string), closes it and returns its full path.
        relativeTo -- path relative to which the path should be or None
            for preferred relativeTo path or "" for absolute path
        """
        if path is None:
            path = self.preferredPath
            if path is None:
                path = getDefaultTempFilePath()

            if path is not None and not os.path.exists(pathEnc(path)):
                try:
                    os.makedirs(path)
                except OSError:
                    path = None

        fullPath = createTempFile(content, suffix, path,
                textMode=isinstance(content, unicode))
        self.fileSet.add(fullPath)

        return self.getRelativePath(relativeTo, fullPath)


    def createTempFileAndUrl(self, content, suffix, path=None, relativeTo=None,
            pythonUrl=False):
        """
        Specialized function. Creates a file, fills it with content 
        (byte string), closes it and returns (filepath, url) tuple
        where filepath and url point to the same newly created file.
        relativeTo -- path relative to which path and URL should be or None
            for preferred relativeTo path or "" for absolute path/URL
        """
        fullPath = self.createTempFile(content, suffix, path, "")

        return (self.getRelativePath(relativeTo, fullPath),
                self.getRelativeUrl(relativeTo, fullPath, pythonUrl=pythonUrl))


    def createTempUrl(self, content, suffix, path=None, relativeTo=None,
            pythonUrl=False):
        """
        Specialized function. Creates a file, fills it with content 
        (byte string), closes it and returns its URL.
        relativeTo -- path relative to which the URL should be or None
            for preferred relativeTo path or "" for absolute URL
        """
        fullPath = self.createTempFile(content, suffix, path, "")
        
        return self.getRelativeUrl(relativeTo, fullPath, pythonUrl=pythonUrl)



# The following three functions do not record the created files in a
# TempFileSet and have no internal defaults for path and relativeTo.

def createTempFile(content, suffix, path=None, relativeTo=None, textMode=False):
    """
    Specialized function. Creates a file in directory path, fills it with 
    content (byte string), closes it and returns its full path.
    relativeTo -- path relative to which the path should be or None
        for absolute path
    textMode -- Convert lineEndings
    """
    if path is None:
        path = getDefaultTempFilePath()
    
    fd, fullPath = tempfile.mkstemp(suffix=pathEnc(suffix), dir=pathEnc(path),
            text=textMode)
    try:
        try:
            if isinstance(content, unicode):
                # assert textMode
                content = content.encode("utf-8")
                os.write(fd, BOM_UTF8)
                os.write(fd, content)
            elif isinstance(content, str):
                os.write(fd, content)
            else:    # content is a sequence
                try:
                    iCont = iter(content)
        
                    firstContent = iCont.next()
                    
                    unic = False
                    if isinstance(firstContent, unicode):
                        firstContent = firstContent.encode("utf-8")
                        os.write(fd, BOM_UTF8)
                        unic = True
    
                    assert isinstance(firstContent, str)
                    os.write(fd, firstContent)
    
                    while True:
                        content = iCont.next()
    
                        if unic:
                            assert isinstance(content, unicode)
                            content = content.encode("utf-8")
    
                        assert isinstance(content, str)
                        os.write(fd, content)
                except StopIteration:
                    pass
        finally:
            os.close(fd)
    except Exception, e:
        traceback.print_exc()
        # Something went wrong -> try to remove temporary file
        try:
            os.unlink(fullPath)
        except:
            traceback.print_exc()
        
        raise e


    return getRelativePath(relativeTo, fullPath)




def createTempFileAndUrl(content, suffix, path=None, relativeTo=None,
        pythonUrl=False):
    """
    Specialized function. Creates a file, fills it with content 
    (byte string), closes it and returns (filepath, url) tuple
    where filepath and url point to the same newly created file.
    relativeTo -- path relative to which path/URL should be or None
        for absolute path/URL
    """
    fullPath = createTempFile(content, suffix, path, None)
    
    return (getRelativePath(relativeTo, fullPath),
            getRelativeUrl(relativeTo, fullPath, pythonUrl=pythonUrl))


def createTempUrl(content, suffix, path=None, relativeTo=None, pythonUrl=False):
    """
    Specialized function. Creates a file in directory path, fills it with 
    content (byte string), closes it and returns its URL.
    relativeTo -- path relative to which the URL should be or None
        for absolute URL
    """
    fullPath = createTempFile(content, suffix, path, None)
    
    return getRelativeUrl(relativeTo, fullPath, pythonUrl=pythonUrl)


def getRelativePath(relativeTo, fullPath):
    """
    Returns path relative to relativeTo. If relativeTo is "" or None
    the path is absolute.
    """
    if relativeTo is None or relativeTo == "":
        return fullPath

    relPath = relativeFilePath(relativeTo, fullPath)
    if relPath is None:
        return fullPath

    return relPath
    
    
def getRelativeUrl(relativeTo, fullPath, pythonUrl=False):
    """
    Returns URL relative to relativeTo. If relativeTo is "" or None
    the URL is absolute.
    """
    if relativeTo is None or relativeTo == "":
        if pythonUrl:
#             return escapeHtml(u"file:" + urllib.pathname2url(fullPath))
            return u"file:" + urlFromPathname(fullPath)
        else:
            return wx.FileSystem.FileNameToURL(fullPath)

    relPath = relativeFilePath(relativeTo, fullPath)
    if relPath is None:
        if pythonUrl:
#             return escapeHtml(u"file:" + urllib.pathname2url(fullPath))
            return u"file:" + urlFromPathname(fullPath)
        else:
            return wx.FileSystem.FileNameToURL(fullPath)

    return urlFromPathname(relPath)


def getDefaultTempFilePath():
    """
    Return default temp directory depending on global configuration settings.
    May return None for system default temp dir.
    """
    globalConfig = wx.GetApp().getGlobalConfig()
    tempMode = globalConfig.get("main", "tempHandling_tempMode",
            u"system")

    if tempMode == u"auto":
        if wx.GetApp().isInPortableMode():
            tempMode = u"config"
        else:
            tempMode = u"system"
    
    if tempMode == u"given":
        return globalConfig.get("main", "tempHandling_tempDir", u"")
    elif tempMode == u"config":
        return wx.GetApp().getGlobalConfigSubDir()
    else:   # tempMode == u"system"
        return None






