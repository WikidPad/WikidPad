import re
from struct import pack, unpack

from wxPython.wx import *
from wxHelper import GUI_ID  #, setWindowPos, setWindowSize

from StringOps import utf8Enc, utf8Dec, boolToChar, charToBool, strToBin, \
        binToStr


# from WikiData import *
# from WikiTxtCtrl import *
# from WikiTreeCtrl import *
# from WikiHtmlView import WikiHtmlView
# from PageHistory import PageHistory
# 
# from AdditionalDialogs import *
# import Exporters
# from StringOps import uniToGui, guiToUni, mbcsDec, mbcsEnc, strToBool
# import WikiFormatting


Unknown = object()  # Abstract third truth value constant



class AbstractSearchNode:
    """
    Base class for all search nodes of the search tree
    """
    def testText(self, text):
        """
        Test, if text of a page fulfills the search criteria and return
        truth value. This is useful for wiki-wide searching for pages.
        
        Remarks:
        - If the node contains non text-related criteria,
          they are ignored (interpreted as 'unknown' in boolean logic).
          If the truth value can't be determined, the Unknown object is
          returned
        """
        assert 0  # Abstract



class AndSearchNode(AbstractSearchNode):
    """
    Connects two nodes by logical "and"
    """
    def __init__(self, left, right):
        self.left = left
        self.right = right
        
    def testText(self, text):
        leftret = self.left.testText(text)
        
        if leftret == False:
            return False
            
        rightret = self.right.testText(text)
        
        if rightret == False:
            return False

        if leftret == True and rightret == True:
            return True
            
        return Unknown



class AbstractCriteriumNode(AbstractSearchNode):
    """
    Base class for all nodes which check a single criterium
    """
    def searchText(self, text, searchCharStartPos=0):
        """
        Applies the search operation on text and returns either
        tuple (<first char>, <after last char>) with position of
        found data or (None, None) if search was unsuccessful.
        """
        return (None, None)

    def testText(self, text):
        return Unknown
        
    def matchesPart(self, toReplace):
        """
        Test if string toReplace matches operation. Mainly called before
        a replacement is done.
        """
        assert 0  # abstract

    def replace(self, text, searchData, pattern):
        """
        Return the content with which the area determined by searchData
        should be replaced.
        
        text -- Full text which was prior fed to searchText()
        searchData -- tuple returned by searchText(), containing
                start and end position of found data and maybe
                additional objects. searchData must come from the
                searchText() method of the same node for which
                replace() is called now.
        pattern -- Pattern of the replacement, e.g. an RE pattern
                for regular expressions
        """
        assert 0  # abstract



class RegexNode(AbstractCriteriumNode):
    """
    Check if regex matches
    """
    def __init__(self, rePattern):
        """
        regex -- precompiled regex pattern
        """
        self.rePattern = rePattern


    def searchText(self, text, searchCharStartPos=0, cycleToStart=False):
        match = self.rePattern.search(text, searchCharStartPos, len(text))
        if not match:
            if searchCharStartPos == 0:
                # We started at beginning, so nothing more to search
                return (None, None)
            elif cycleToStart:
                # Try again from beginning
                match = self.rePattern.search(text, 0, len(text))

        if not match:
            return (None, None)

        return (match.start(0), match.end(0), match)


    def testText(self, text):
        return not not self.rePattern.search(text)


    def matchesPart(self, toReplace):
        """
        Test if string toReplace matches operation. Mainly called before
        a replacement is done.
        """
        match = self.rePattern.match(toReplace)
        if match:
            return (0, len(toReplace), match)
        else:
            return None

    def replace(self, toReplace, foundData, pattern):
        return foundData[2].expand(pattern)



class SimpleStrNode(AbstractCriteriumNode):
    """
    Check if a simple string matches
    """
    def __init__(self, subStr):
        """
        subStr -- sub-string to find in text
        """
        self.subStr = subStr


    def searchText(self, text, searchCharStartPos=0, cycleToStart=False):
        pos = text.find(self.subStr, searchCharStartPos)
        if pos == -1:
            if searchCharStartPos == 0:
                # We started at beginning, so nothing more to search
                return (None, None)
            elif cycleToStart:
                # Try again from beginning
                pos = text.find(self.subStr, 0)

        if pos == -1:
            return (None, None)

        return (pos, pos + len(self.subStr))


    def testText(self, text):
        return text.find(self.subStr) != -1

    def matchesPart(self, toReplace):
        """
        Test if string toReplace matches operation. Mainly called before
        a replacement is done.
        """
        if self.subStr == toReplace:
            return (0, len(toReplace))
        else:
            return None

    def replace(self, toReplace, foundData, pattern):
        return pattern


# ----------------------------------------------------------------------


class SearchReplaceOperation:
    """
    Dumb container to hold data of a search or replace operation.
    
    Be aware that if self.booleanOp is True, some settings have no effect:
    - replaceOp is assumed to be False
    - cycleToStart is assumed to be False 
    - wikiWide is assumed to be True
    """
    def __init__(self):
        self.searchStr = ""   # Search string
        self.replaceStr = ""  # Replace string (if any)
        self.replaceOp = False  # Is this a replace operation (or search only)?
        self.wholeWord = False  # Search for whole words only?
        self.caseSensitive = False  # Search case sensitive?
        self.cycleToStart = False  # Wrap around when coming to the end of page
        self.booleanOp = False  # Can search string contain boolean operators?
        self.wildCard = 'regex' # Search string is: 'regex':regular expression
                                # (and replace str.) 'no':Without wildcards
        self.wikiWide = False   # Operation on whole wiki (or current page only)?

        self.title = None       # Title of the search for saving it. Use getter
                                # and setter to retrieve/modify value

        self.searchOpTree = None # Cache information

    def clone(self):
        """
        Create clone of the object
        """
        result = SearchReplaceOpData()
        
        # Shallow copy is enough because object contains only strings and
        # truth values
        result.__dict__.update(self.__dict__)  # TODO: Cleaner way to do that?
        
        result.clearCache()


    def clearCache(self):
        """
        Call this after making changes to reset any cached data
        """
        self.searchOpTree = None
        
    def getTitle(self):
        if self.title is None:
            return self.searchStr
        
        return self.title
        
        
    def setTitle(self, title):
        self.title = title
        
    def getPackedSettings(self):
        """
        Returns a byte sequence (string) containing the current settings
        of all data members (except title and cache info (searchOpTree)).
        This can be saved in the database and restored later with
        setPackedSettings()
        """
        result = []
        
        result.append(pack(">I", 0))  # Version number of binary data
        
        result.append(strToBin(utf8Enc(self.searchStr)[0]))
        result.append(strToBin(utf8Enc(self.replaceStr)[0]))
        
        result.append(boolToChar(self.replaceOp) + boolToChar(self.wholeWord) +
                boolToChar(self.caseSensitive) + boolToChar(self.cycleToStart) + \
                boolToChar(self.booleanOp))

        result.append(strToBin(self.wildCard))
        
#         result.append(boolToChar(self.wikiWide))
        
        return "".join(result)
        
    
    def setPackedSettings(self, data):
        """
        Set member variables according to the byte sequence stored in
        data by getPackedSettings()
        """
        
        version = unpack(">I", data[:4])[0]
        data = data[4:]
        
        if version != 0:
            return   # TODO Error handling
        
        self.searchStr, data = binToStr(data)
        self.replaceStr, data = binToStr(data)

        self.replaceOp = charToBool(data[0])
        self.wholeWord = charToBool(data[1])
        self.caseSensitive = charToBool(data[2])
        self.cycleToStart = charToBool(data[3])
        self.booleanOp = charToBool(data[4])
        data = data[5:]
       
        self.wildCard, data = binToStr(data)
        
#         self.wikiWide = charToBool(data[0])
#         data = data[1:]
        
        self.clearCache()


    def reNeeded(self):
        """
        Return True if current settings require to use regular expressions
        instead of a simple string search. This can be True even if self.regEx
        is False.
        A returned True does not mean that a single RE is enough for search
        operation.
        """
        return self.wildCard != 'no' or self.wholeWord or not self.caseSensitive


    def rebuildSearchOpTree(self):
        """
        Rebuild the search operation tree. Automatically called by
        searchText() and testText() if necessary.
        """
        # TODO Test empty string

        if not self.booleanOp:
            self.searchOpTree = self._buildSearchCriterium(self.searchStr)

        else:
            # TODO More features
            andPatterns = self.searchStr.split(u' and ')

            if len(andPatterns) == 1:
                self.searchOpTree = self._buildSearchCriterium(self.searchStr)
            else:
                # Build up tree (bottom-up)
                node = AndSearchNode(self._buildSearchCriterium(andPatterns[-2]),
                        self._buildSearchCriterium(andPatterns[-1]))
                for i in xrange(len(andPatterns) - 3, -1, -1):
                    node = AndSearchNode(
                            self._buildSearchCriterium(andPatterns[i]), node)
                    
                self.searchOpTree = node


    def _buildSearchCriterium(self, searchStr):
        """
        Build single search criterium e.g. as part of a boolean search
        and return the node.
        """
        if not self.reNeeded():
            # TODO: Test if really faster than REs
            return SimpleStrNode(searchStr)
        else:
            if self.wildCard == 'no':
                searchStr = re.escape(searchStr)

            if self.wholeWord:
                searchStr = ur"\b%s\b" % searchStr
                
            if self.caseSensitive:
                reFlags = re.MULTILINE | re.UNICODE
            else:
                reFlags = re.IGNORECASE | re.MULTILINE | re.UNICODE
                
            return RegexNode(re.compile(searchStr, reFlags))


    def searchText(self, text, searchCharStartPos=0):
        """
        Applies the search operation on text and returns either
        tuple (<first char>, <after last char>) with position of
        found data or (None, None) if search was unsuccessful.
        
        Remarks:
        - The function does not work if self.booleanOp is True
        - The function does not apply a replacement, even if 'self'
          is a replacement operation
        """
        if self.booleanOp:
            return (None, None)  # TODO Exception?

        # Try to get regex pattern
        if self.searchOpTree is None:
            self.rebuildSearchOpTree()

        return self.searchOpTree.searchText(text, searchCharStartPos,
                self.cycleToStart)


    def matchesPart(self, toReplace):
        """
        Test if string toReplace matches operation and
        returns a faked 'found' tuple or None if not matching
        """
        
        if self.booleanOp:
            return None  # TODO Exception?

        # Try to get regex pattern
        if self.searchOpTree is None:
            self.rebuildSearchOpTree()

        return self.searchOpTree.matchesPart(toReplace)
        

    def replace(self, text, foundData):
        """
        Return the text which should replace the selection in text
        described by foundData (which was returned by a call to searchText)
        """
        if self.booleanOp or not self.replaceOp:
            return None   # TODO Exception?

        # Try to get regex pattern
        if self.searchOpTree is None:
            self.rebuildSearchOpTree()

        return self.searchOpTree.replace(text, foundData, self.replaceStr)


    def testText(self, text):
        """
        Test, if text of a page fulfills the search criteria and return
        truth value. This is useful for wiki-wide searching for pages.
        
        Remarks:
        - The self.replaceOp flag is ignored
        - If the SearchReplaceOperation contains non text-related criteria,
          they are ignored (interpreted as 'unknown' in boolean logic)
        """
        
        if self.searchOpTree is None:
            self.rebuildSearchOpTree()

        return self.searchOpTree.testText(text)









