"""
Temporary file management
"""
import sys, os, traceback, sets, tempfile

import wx

from StringOps import urlFromPathname, relativeFilePath, escapeHtml


class TempFileSet:
    """
    A TempFileSet allows to create temporary files and stores their
    pathes so that they can all be deleted at once when needed no more.

    The files are not automatically deleted when the object is garbage
    collected.
    """

    def __init__(self):
        self.fileSet = sets.Set()
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

    def mkstemp(self, suffix=None, prefix=None, dir=None, text=False):
        """
        Same as tempfile.mkstemp from standard library, but
        stores returned path also in the bag.
        """
        if dir is None:
            dir = self.preferredPath
        
        fd, fullPath = tempfile.mkstemp(suffix, prefix, dir, text)
        
        self.fileSet.add(fullPath)
        
        return fd, fullPath


    def clear(self):
        """
        Delete all files of which the path is stored in the bag
        """
        for fullPath in self.fileSet:
            try:
                os.remove(fullPath)
            except:
                traceback.print_exc()
        
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
        
    
    def getRelativeUrl(self, relativeTo, fullPath):
        """
        Returns URL relative to relativeTo. If relativeTo is ""
        the URL is absolute, if it is None the preferred relativeTo
        is used.
        """
        if relativeTo is None:
            relativeTo = self.preferredRelativeTo
        
        return getRelativeUrl(relativeTo, fullPath)
        

    def createTempFile(self, content, suffix, path=None, relativeTo=None):
        """
        Specialized function. Creates a file in directory path, fills it with 
        content (byte string), closes it and returns its full path.
        relativeTo -- path relative to which the path should be or None
            for preferred relativeTo path or "" for absolute path
        """
        if path is None:
            path = self.preferredPath
            
        fullPath = createTempFile(content, suffix, path)
        self.fileSet.add(fullPath)
        
        return self.getRelativePath(relativeTo, fullPath)


    def createTempFileAndUrl(self, content, suffix, path=None, relativeTo=None):
        """
        Specialized function. Creates a file, fills it with content 
        (byte string), closes it and returns (filepath, url) tuple
        where filepath and url point to the same newly created file.
        relativeTo -- path relative to which path and URL should be or None
            for preferred relativeTo path or "" for absolute path/URL
        """
        fullPath = self.createTempFile(content, suffix, path, "")
        
        return (self.getRelativePath(relativeTo, fullPath),
                self.getRelativeUrl(relativeTo, fullPath))


    def createTempUrl(self, content, suffix, path=None, relativeTo=None):
        """
        Specialized function. Creates a file, fills it with content 
        (byte string), closes it and returns its URL.
        relativeTo -- path relative to which the URL should be or None
            for preferred relativeTo path or "" for absolute URL
        """
        fullPath = self.createTempFile(content, suffix, path, "")
        
        return self.getRelativeUrl(relativeTo, fullPath)



# The following three functions do not record the created files in a
# TempFileSet and have no internal defaults for path and relativeTo.

def createTempFile(content, suffix, path=None, relativeTo=None):
    """
    Specialized function. Creates a file in directory path, fills it with 
    content (byte string), closes it and returns its full path.
    relativeTo -- path relative to which the path should be or None
        for absolute path
    """
    fd, fullPath = tempfile.mkstemp(suffix=suffix, dir=path, text=False)
    try:
        os.write(fd, content)
    finally:
        os.close(fd)

    return getRelativePath(relativeTo, fullPath)


def createTempFileAndUrl(content, suffix, path=None, relativeTo=None):
    """
    Specialized function. Creates a file, fills it with content 
    (byte string), closes it and returns (filepath, url) tuple
    where filepath and url point to the same newly created file.
    relativeTo -- path relative to which path/URL should be or None
        for absolute path/URL
    """
    fullPath = createTempFile(content, suffix, path, None)
    
    return (getRelativePath(relativeTo, fullPath),
            getRelativeUrl(relativeTo, fullPath))


def createTempUrl(content, suffix, path=None, relativeTo=None):
    """
    Specialized function. Creates a file in directory path, fills it with 
    content (byte string), closes it and returns its URL.
    relativeTo -- path relative to which the URL should be or None
        for absolute URL
    """
    fullPath = createTempFile(content, suffix, path, None)
    
    return getRelativeUrl(relativeTo, fullPath)


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
    
    
def getRelativeUrl(relativeTo, fullPath):
    """
    Returns URL relative to relativeTo. If relativeTo is "" or None
    the URL is absolute.
    """
    if relativeTo is None or relativeTo == "":
        return escapeHtml(wx.FileSystem.FileNameToURL(fullPath))

    relPath = relativeFilePath(relativeTo, fullPath)
    if relPath is None:
        return escapeHtml(wx.FileSystem.FileNameToURL(fullPath))

    return urlFromPathname(relPath)
