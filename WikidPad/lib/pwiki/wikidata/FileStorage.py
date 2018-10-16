"""
Handles the storage of external files (e.g. images, but also other
data or programs)
"""

import os, os.path, traceback, glob

import re
from pwiki.StringOps import createRandomString, pathEnc
from pwiki.OsAbstract import copyFile, moveFile


class FSException(Exception):
    pass



_FILESPLITPAT = re.compile(r"^(?P<name>\.*[^.]+)(?P<suffix>.*)$",
        re.DOTALL | re.UNICODE | re.MULTILINE)



class FileStorage:
    """
    This class handles storing of files (especially finding names and copying)
    for a specified wiki. Unlike some other classes, this is not an active
    component, so it must be replaced by a new instance if a new wiki is loaded.
    """
    
    def __init__(self, wikiDocument, storagePath):
        """
        mainControl -- PersonalWikiFrame instance
        wikiDocument -- WikiDocument instance of current wiki
        filePath -- directory path where new files should be stored
                (doesn't have to exist already)
        """
        self.wikiDocument = wikiDocument
        self.storagePath = storagePath
        
        # Conditions for identity test
        self.modDateMustMatch = False  # File is only identical if modification
                # date matches, too
        self.filenameMustMatch = False  # File is only identical if complete
                # filename (without directory, of course) matches, too

        self.modDateIsEnough = False  # If modif. date (and file size
                # implicitly) matches, files are seen as identical

        # Currently unused:
#         self.preTestDistance = 2048  # Distance between file positions to read
#                 # in a preliminary test of identity
#         self.preTestLength = 4  # Number of bytes to read at each file position
#                 # for preliminary test of identity


    def setModDateMustMatch(self, val):
        self.modDateMustMatch = val

    def setFilenameMustMatch(self, val):
        self.filenameMustMatch = val

    def setModDateIsEnough(self, val):
        self.modDateIsEnough = val
    
    def getStoragePath(self):
        return self.storagePath


    def _storageExists(self):
        """
        Test if file storage (=directory) exists.
        """
        return os.path.exists(pathEnc(self.storagePath))
        
    def _ensureStorage(self):
        """
        Create storage directory if not yet existing.
        """
        if not self._storageExists():
            os.makedirs(self.storagePath)

#     def _preTestIdentical(self, path1, path2):
#         """
#         Preliminary test for identity of two files denoted by path1 and path2.
#         This test is fast, but not fully reliable. If the function returns
#         False, the files are definitely different. If it returns True,
#         a call to _isIdentical is needed to 
#         """

#         This function assumes that _preTestIdentical() was already called for
#         these pathes and returned True.

    def _preTestIdentity(self, destpath, srcfname, srcstat):
        """
        Preliminary test if the destination file denoted by destpath and
        the source described by its name srcfnam without path and
        its stats COULD BE identical.
        If the function returns False, they are definitely different,
        if it returns True, further tests are necessary.
        """
        if not os.path.isfile(destpath):
            # Must be existing file
            return False

        destfname = os.path.basename(destpath)

        if os.path.splitext(srcfname)[1] != os.path.splitext(destfname)[1]:
            # file suffix must match always
            return False

        if self.filenameMustMatch and srcfname != destfname:
            return False

        deststat = os.stat(pathEnc(destpath))
        
        if deststat.st_size != srcstat.st_size:
            # Size must match always
            return False

        if self.modDateMustMatch and deststat.st_mtime != srcstat.st_mtime:
            return False
            
        # This means it COULD BE identical according to the quick tests
        return True


    def _getCandidates(self, srcPath):
        """
        Find possible candidates for detailed identity check. The file storage
        must exist already.
        srcPath -- Must be a path to an existing file
        """
        srcfname = os.path.basename(srcPath)
        srcstat = os.stat(pathEnc(srcPath))

        
        ccSameName = set()     # candidate category: same filename
                                    # (only one possible entry)
        ccSameMod = set()     # candidate category: same mod. date
        ccElse = set()     # candidate category: everything else

        samenamepath = os.path.join(self.storagePath, srcfname)
        if self._preTestIdentity(samenamepath, srcfname, srcstat):
            ccSameName.add(samenamepath)

        if self.filenameMustMatch:
            # No other candidates possible
            return list(ccSameName)


        ext = os.path.splitext(srcPath)[1]
        for p in glob.glob(os.path.join(self.storagePath, "*" + ext)):
            if p == samenamepath:
                # Already tested above
                continue

            if self._preTestIdentity(p, srcfname, srcstat):
                deststat = os.stat(pathEnc(p))
                if deststat.st_mtime == srcstat.st_mtime:
                    ccSameMod.add(p)
                else:
                    ccElse.add(p)

        return list(ccSameName) + list(ccSameMod) + list(ccElse)


    def _isIdentical(self, path1, path2):
        """
        Checks if the files denoted by path1 and path2 are identical according
        to the settings of the object.

        The files must have passed the preliminary test by _preTestIdentity().
        """
        
        stat1 = os.stat(pathEnc(path1))
        stat2 = os.stat(pathEnc(path2))

        if self.modDateIsEnough and stat1.st_mtime == stat2.st_mtime:
            return True

        # End of fast tests, now the whole content must be compared
        
        file1 = open(path1, "rb")    
        file2 = open(path2, "rb")
        
        try:
            while True:
                block1 = file1.read(1024 * 1024)
                block2 = file2.read(1024 * 1024)
                if len(block1) == 0 and len(block2) == 0:
                    # EOF
                    return True
                if len(block1) != len(block2):
                    raise FSException(_("File compare error, file not readable or "
                            "changed during compare"))

                if block1 != block2:
                    return False
        finally:
            file2.close()
            file1.close()


    def findDestPath(self, srcPath):
        """
        Find a path to a new destination
        of the source file denoted by srcPath. Some settings of
        the object determine how this is done exactly.
        Returns a tuple (path, exists) where path is the destination
        path and exists is True if an identical file exists already
        at the destination.
        If path is None, a new filename couldn't be found.
        """

        if not (os.path.isfile(srcPath) or os.path.isdir(srcPath)):
            raise FSException(_("Path '%s' must point to an existing file") %
                    srcPath)

        self._ensureStorage()
        
        for c in self._getCandidates(srcPath):
            if self._isIdentical(srcPath, c):
                return (c, True)

        # No identical file found, so find a not yet used name for the new file.
        fname = os.path.basename(srcPath)

        if not os.path.exists(pathEnc(os.path.join(self.storagePath, fname))):
            return (os.path.join(self.storagePath, fname), False)

        mat = _FILESPLITPAT.match(fname)
        if mat is None:
            raise FSException(_("Internal error: Bad source file name"))

        coreName = mat.group("name")
        suffix = mat.group("suffix")

        for t in range(10):  # Number of tries
            newName = "%s_%s%s" % (coreName, createRandomString(10), suffix)
            
            if not os.path.exists(pathEnc(os.path.join(
                    self.storagePath, newName))):
                return (os.path.join(self.storagePath, newName), False)

        # Give up
        return (None, False)
    
    
    def findDestPathNoSource(self, suffix, prefix=""):
        """
        Find a path to a destination.
        """
        self._ensureStorage()

        if prefix:
            fname = prefix + suffix

            destPath = os.path.join(self.storagePath, fname)
            if not os.path.exists(pathEnc(destPath)):
                return destPath
        else:
            prefix = ""


#         mat = _FILESPLITPAT.match(fname)
#         if mat is None:
#             raise FSException("Internal error: Bad source file name")
# 
#         coreName = mat.group("name")
#         suffix = mat.group("suffix")

        for t in range(20):  # Number of tries
            newName = "%s_%s%s" % (prefix, createRandomString(20), suffix)

            destPath = os.path.join(self.storagePath, newName)
            if not os.path.exists(pathEnc(destPath)):
                return destPath

        # Give up
        return None
        


    # TODO progress indicator
    def createDestPath(self, srcPath, guiProgressListener=None, move=False):
        """
        Return destination path in fileStorage of a file denoted by srcPath.
        Destination may be already existing or was copied from source.
        
        guiProgressListener -- currently not used
        move -- If True, move file instead of copying
        """
        destpath, ex = self.findDestPath(srcPath)
        if ex:
            return destpath
            
        if destpath is None:
            raise FSException(_("Copy of file '%s' couldn't be created") %
                    srcPath)

        if move:
            self.moveFile(srcPath, destpath)
        else:
            self.copyFile(srcPath, destpath)

        return destpath

    @staticmethod
    def copyFile(srcPath, dstPath):
        """
        Copy file from srcPath to dstPath. dstPath my be overwritten if
        existing already.
        """
        copyFile(srcPath, dstPath)


    @staticmethod
    def moveFile(srcPath, dstPath):
        """
        Copy file from srcPath to dstPath. dstPath my be overwritten if
        existing already.
        """
        moveFile(srcPath, dstPath)


#     def findIdenticalFile(self, srcPath):
#         """
#         Return the path of a file in the storage identical to the
#         one denoted by srcPath and returns either the path of the
#         identical file or None if not found. Some settings of
#         the object determine how this is done exactly.
#         """



