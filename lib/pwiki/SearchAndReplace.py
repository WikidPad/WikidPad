import re, sets
from struct import pack, unpack

# import wx
from wxHelper import GUI_ID  #, setWindowPos, setWindowSize

from WikiExceptions import *

from Serialization import SerializeStream

from StringOps import utf8Enc, utf8Dec, boolToChar, charToBool, strToBin, \
        binToStr
        



Unknown = object()  # Abstract third truth value constant


class AbstractSearchNode:
    """
    Base class for all search nodes of the search tree
    """
    def __init__(self, sarOp):
        """
        sarOp -- search and replace operation, the node belongs to
        """
        self.sarOp = sarOp
        
    def setSarOp(self, sarOp):
        self.sarOp = sarOp
    
    def beginWikiSearch(self, wikiDocument):
        """
        Always called before a new wiki-wide search operation begins
        """
        pass
    
    def endWikiSearch(self):
        """
        Called after a wiki-wide search operation ended
        """
        pass

    def testWikiPage(self, word, text):
        """
        Test, if wiki page fulfills the search criteria and return
        truth value. This is useful for wiki-wide searching for pages.
        
        word -- Naked wiki word of the page
        text -- Textual content of the page
        """
        return self.testText(text)
        # assert 0  # Abstract
        

    def testText(self, text):
        """
        DEPRECATED
        Test, if text of a page fulfills the search criteria and return
        truth value. This is useful for wiki-wide searching for pages.
        
        Remarks:
        - If the node contains non text-related criteria,
          they are ignored (interpreted as 'unknown' in boolean logic).
          If the truth value can't be determined, the Unknown object is
          returned
        """
        assert 0  # Abstract


    def serializeBin(self, stream):
        """
        Read or write content of this object to or from a serialize stream

        stream -- StringOps.SerializeStream object
        """
        assert 0 #abstract


    def orderNatural(self, wordSet, coll):
        """
        Order the words in the wordSet in a natural order for this search
        node. The meaning of "natural" depends on the concrete node called.
        It is only called after a call to beginWikiSearch() and before
        matching call to endWikiSearch().
        
        wordSet -- Mutable set with words containing
            the words to sort natural. On exit, it contains only the words
            not contained in the returned list
        coll -- Collator for sorting
        Returns: List of words from wordSet which could be sorted in a
            natural order.
        """
        return []
        
    def getRootWords(self):
        """
        Return all words used as roots of subtrees (if any) for better tree sorting
        """
        return []



class AndSearchNode(AbstractSearchNode):
    """
    Connects two nodes by logical "and"
    """
    
    def __init__(self, sarOp, left, right):
        AbstractSearchNode.__init__(self, sarOp)
        self.left = left
        self.right = right
        
    def beginWikiSearch(self, wikiDocument):
        self.left.beginWikiSearch(wikiDocument)
        self.right.beginWikiSearch(wikiDocument)
        
    def endWikiSearch(self):
        """
        Called after a wiki-wide search operation ended
        """
        self.left.endWikiSearch()
        self.right.endWikiSearch()

        
    def testWikiPage(self, word, text):
        leftret = self.left.testWikiPage(word, text)
        
        if leftret == False:
            return False
            
        rightret = self.left.testWikiPage(word, text)
        
        if rightret == False:
            return False

        if leftret == True and rightret == True:
            return True
            
        return Unknown

        
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


    def orderNatural(self, wordSet, coll):
        """
        Order of left operand has priority
        """
        leftret = self.left.orderNatural(wordSet, coll)
        
        if len(wordSet) == 0:
            return leftret

        rightret = self.right.orderNatural(wordSet, coll)
        
        return leftret + rightret
        
        
class NotSearchNode(AbstractSearchNode):
    """
    Inverts the meaning of the subnode
    """
    
    CLASS_PERSID = "Not"  # Class id for persistence storage

    def __init__(self, sarOp, sub=None):
        AbstractSearchNode.__init__(self, sarOp)
        self.sub = sub
        
    def beginWikiSearch(self, wikiDocument):
        self.sub.beginWikiSearch(wikiDocument)
        
    def endWikiSearch(self):
        """
        Called after a wiki-wide search operation ended
        """
        self.sub.endWikiSearch()

        
    def testWikiPage(self, word, text):
        subret = self.sub.testWikiPage(word, text)
        
        if subret == Unknown:
            return Unknown
            
        return not subret


    # orderNatural() from the subnode is not delegated

    def serializeBin(self, stream):  # TODO !!!
        """
        Read or write content of this object to or from a serialize stream

        stream -- StringOps.SerializeStream object
        """
        version = stream.serUint32(0)
        
        if version != 0:
            raise SerializationException
            
        self.sub = _serNode(stream, self.sarOp, self.sub)


# ----- Page list construction nodes -----

class AllWikiPagesNode(AbstractSearchNode):
    """
    Returns True for any page
    """
    
    CLASS_PERSID = "AllPages"  # Class id for persistence storage

    def __init__(self, sarOp):
        AbstractSearchNode.__init__(self, sarOp)
        self.wikiName = None
    
    def beginWikiSearch(self, wikiDocument):
        """
        Always called before a new wiki-wide search operation begins.
        Fills wordList and wordSet
        """
        self.wikiName = wikiDocument.getWikiName()

    def endWikiSearch(self):
        """
        Called after a wiki-wide search operation ended.
        Clears wordList
        """
        self.wikiName = None

    def testWikiPage(self, word, text):
        return True

    def serializeBin(self, stream):
        """
        Read or write content of this object to or from a serialize stream

        stream -- StringOps.SerializeStream object
        """
        version = stream.serUint32(0)
        
        if version != 0:
            raise SerializationException

    def getRootWords(self):
        """
        Return all words used as roots of subtrees (if any) for better tree sorting
        """
        return [self.wikiName]



class RegexWikiPageNode(AbstractSearchNode):
    """
    Returns True if regex matches page name
    """
    
    CLASS_PERSID = "RegexPage"  # Class id for persistence storage
    
    def __init__(self, sarOp, pattern=u""):
        AbstractSearchNode.__init__(self, sarOp)
        self.compPat = re.compile(pattern,
                re.DOTALL | re.UNICODE | re.MULTILINE)  # TODO MULTILINE?
    
    def testWikiPage(self, word, text):
        return not not self.compPat.match(word)

    def serializeBin(self, stream):
        """
        Read or write content of this object to or from a serialize stream

        stream -- StringOps.SerializeStream object
        """
        version = stream.serUint32(0)
        
        if version != 0:
            raise SerializationException
            
        pattern = stream.serUniUtf8(self.compPat.pattern)
        
        if pattern != self.compPat.pattern:
            self.compPat = re.compile(pattern,
                re.DOTALL | re.UNICODE | re.MULTILINE)  # TODO MULTILINE?
                
    def getPattern(self):
        """
        Return the pattern string
        """
        return self.compPat.pattern



class ListItemWithSubtreeWikiPagesNode(AbstractSearchNode):
    """
    Returns True for a specified root page and all pages below to a specified
    level. (level == -1: any depth, level == 0: root only)
    """

    CLASS_PERSID = "ListItemWithSubtreePages"  # Class id for persistence storage
    
    def __init__(self, sarOp, rootWords=None, level=-1):
        AbstractSearchNode.__init__(self, sarOp)
        self.rootWords = rootWords
        self.level = level
        
        # wordSet and wordList always contain the same words
        self.wordSet = None    # used for testWikiPage()
        self.wordList = None   # used for orderNatural()


    def beginWikiSearch(self, wikiDocument):
        """
        Always called before a new wiki-wide search operation begins.
        Fills wordList and wordSet
        """
        wordSet = {}
        
        if self.level == 0:
            for rw in self.rootWords:
                wordSet[rw] = None

            self.wordList = self.rootWords
            self.wordSet = wordSet
            return

#         wordList = []
        # for rw in self.rootWords:
        subWords = wikiDocument.getWikiData().getAllSubWords(
                self.rootWords, self.level)
        for sw in subWords:
#                 if wordSet.has_key(sw):
#                     continue
            wordSet[sw] = None
#                 wordList.append(sw)

        self.wordList = subWords  # wordList
        self.wordSet = wordSet


    def endWikiSearch(self):
        """
        Called after a wiki-wide search operation ended.
        Clears wordList
        """
        self.wordSet = None
        self.wordList = None


    def testWikiPage(self, word, text):
        return self.wordSet.has_key(word)


    def orderNatural(self, wordSet, coll):
        result = []
        for w in self.wordList:
            if w in wordSet:
                result.append(w)
                wordSet.remove(w)

        return result


    def serializeBin(self, stream):
        """
        Read or write content of this object to or from a serialize stream

        stream -- StringOps.SerializeStream object
        """
        version = stream.serUint32(0)

        if version != 0:
            raise SerializationException
            
        # Read/write all root words
        if stream.isReadMode():
            rwl = stream.serUint32(0)
            lst = []
            for i in xrange(rwl):
                lst.append(stream.serUniUtf8(u""))
                
            self.rootWords = lst
        else:
            stream.serUint32(len(self.rootWords))
            for item in self.rootWords:
                stream.serUniUtf8(item)

        # Serialize the level
        self.level = stream.serInt32(self.level)


    def getRootWords(self):
        """
        Return all words used as roots of subtrees (if any) for better tree sorting
        """
        return self.rootWords





_CLASSES_WITH_PERSID = (NotSearchNode, AllWikiPagesNode,
        ListItemWithSubtreeWikiPagesNode, RegexWikiPageNode)

_PERSID_TO_CLASS_MAP = {}
for cl in _CLASSES_WITH_PERSID:
    _PERSID_TO_CLASS_MAP[cl.CLASS_PERSID] = cl


def _serNode(stream, sarOp, obj):
    """
    (De-)Serializes an object with a CLASS_PERSID. If object is read from
    stream, a newly created object is returned, if it is written, obj is
    returned
    """
    global _PERSID_TO_CLASS_MAP

    if stream.isReadMode():
        persId = stream.serString("")
        cl = _PERSID_TO_CLASS_MAP[persId]
        obj = cl(sarOp)
        obj.serializeBin(stream)
        return obj
    else:
        stream.serString(obj.CLASS_PERSID)
        obj.serializeBin(stream)
        return obj



# -------------------- Text search criteria --------------------

class AbstractContentSearchNode(AbstractSearchNode):
    """
    Base class for all nodes which check a single criterion
    """
    def __init__(self, sarOp):
        AbstractSearchNode.__init__(self, sarOp)
    
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



class RegexTextNode(AbstractContentSearchNode):
    """
    Check if regex matches the contained text
    """
    def __init__(self, sarOp, rePattern):
        """
        regex -- precompiled regex pattern
        """
        AbstractContentSearchNode.__init__(self, sarOp)
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



class SimpleStrNode(AbstractContentSearchNode):
    """
    Check if a simple string matches
    """
    def __init__(self, sarOp, subStr):
        """
        subStr -- sub-string to find in text
        """
        AbstractContentSearchNode.__init__(self, sarOp)
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



# TODO Abstract base for following two classes


class ListWikiPagesOperation:
    def __init__(self):
        self.searchOpTree = AllWikiPagesNode(self)
        self.ordering = "no"  # How to order the pages ("natural",
                              # "ascending"=Alphabetically ascending or "no")
        self.wikiDocument = None

    def setSearchOpTree(self, searchOpTree):
        self.searchOpTree = searchOpTree
        
    def getSearchOpTree(self):
        return self.searchOpTree

    def serializeBin(self, stream):
        """
        Read or write content of this object to or from a serialize stream

        stream -- StringOps.SerializeStream object
        """
        self.ordering = stream.serString(self.ordering)
        self.searchOpTree = _serNode(stream, self, self.searchOpTree)


    def getPackedSettings(self):
        """
        Returns a byte sequence (string) containing the current settings
        of all data members (except title and cache info (searchOpTree)).
        This can be saved in the database and restored later with
        setPackedSettings()
        """
        return ""  # TODO !!!


    def setPackedSettings(self, data):
        """
        Set member variables according to the byte sequence stored in
        data by getPackedSettings()
        """
        pass   # TODO !!!


    def beginWikiSearch(self, wikiDocument):
        """
        Called by WikiDataManager(=WikiDocument) to begin a wiki-wide search
        """
        self.wikiDocument = wikiDocument

        if self.searchOpTree is None:
            return   # TODO: Error ?
            
        return self.searchOpTree.beginWikiSearch(wikiDocument)
        

    def endWikiSearch(self):
        """
        End a wiki-wide search
        """
        self.wikiDocument = None

        if self.searchOpTree is None:
            return   # TODO: Error ?
            
        return self.searchOpTree.endWikiSearch()
        

    def testWikiPage(self, word, text):
        """
        Test, if page fulfills the search criteria and return
        truth value. This is useful for wiki-wide searching for pages.
        
        word -- Naked wiki word of the page
        text -- Textual content of the page
        """
        if self.searchOpTree is None:
            return False
            
        return self.searchOpTree.testWikiPage(word, text)


    def getRootWords(self):
        """
        Return all words used as roots of subtrees (if any) for better tree sorting
        It must be called after beginWikiSearch() and before corresponding
        endWikiSearch() call.
        """
        if self.searchOpTree is None:
            return []
            
        return self.searchOpTree.getRootWords()


    def applyOrdering(self, wordSet, coll):
        """
        Returns the wordSet set ordered as defined in self.ordering. It must
        be called after beginWikiSearch() and before corresponding
        endWikiSearch() call.
        
        wordSet must be a mutable set and may be modified during operation.
        """
        if self.ordering == "no":
            return list(wordSet)
        elif self.ordering == "ascending":
            result = list(wordSet)
            coll.sort(result)
            return result
        elif self.ordering == "natural":
            return self.orderNatural(wordSet, coll)
        elif self.ordering == "asroottree":
            # Sort as in the root tree (= tree with the wiki name page as root)
            wordSet = wordSet.copy()
            result = []

            rootWords = self.getRootWords()

            if not self.wikiDocument.getWikiName() in rootWords:
                rootWords.append(self.wikiDocument.getWikiName())

            # Creation of the rootWordSet and later handling of it ensures
            # that the order of the rootWords is preserved.
            # Example: root words a, b, c are given in this order, but c
            # is child of a. Without the special handling, the output
            # order would be a, c, b
            rootWordSet = sets.Set(self.getRootWords())
            rootWordSet.intersection_update(wordSet)
            wordSet.difference_update(rootWordSet)

            for rootWord in rootWords:
                rootPage = self.wikiDocument.getWikiPage(rootWord)
                flatTree = rootPage.getFlatTree()
                if rootWord in rootWordSet:
                    result.append(rootWord)
                    rootWordSet.remove(rootWord)

                for word, deepness in flatTree:
                    if word in wordSet:
                        result.append(word)
                        wordSet.remove(word)
                        # Little optimization
                        if len(wordSet) < 2:
                            if len(wordSet) == 1:
                                result.append(wordSet.pop())
                            break

            if len(wordSet) > 0:
                # There are remaining words not in the root tree
                # -> sort them ascending and append them to result
                result2 = list(wordSet)
                coll.sort(result2)
                
                result += result2
            
            return result

        return list(wordSet)  # TODO Error


    def orderNatural(self, wordSet, coll):
        """
        Return the list of words in a natural order. Meaning of "natural"
        is defined by the called search node(s). It must be called after
        beginWikiSearch() and before corresponding endWikiSearch() call.
        
        wordSet -- mutable set of words to order "natural"
        coll -- Collator for sorting
        """
        if self.searchOpTree is None:
            result = list(wordSet)
            result.sort()
            return result

#         wordSet = {}
#         for w in words:
#             wordSet[w] = None
            
        naturalList = self.searchOpTree.orderNatural(wordSet, coll)
        remain = list(wordSet)
        remain.sort()

        return naturalList + remain



class SearchReplaceOperation:
    """
    Container to hold data of a search or replace operation.
    
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
        self.ordering = "no"  # How to order the pages

        self.searchOpTree = None # Cache information
        self.wikiDocument = None
        self.listWikiPagesOp = ListWikiPagesOperation()

    def clone(self):
        """
        Create clone of the object
        """
        result = SearchReplaceOperation()
        
        # Shallow copy is enough because object contains only strings and
        # truth values
        result.__dict__.update(self.__dict__)  # TODO: Cleaner way to do that?
        
        result.clearCache()
        
        return result


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
        
    
    def serializeBin(self, stream):
        """
        Read or write content of this object to or from a serialize stream

        stream -- StringOps.SerializeStream object
        """
        version = stream.serUint32(1)
        
        if version < 0 or version > 1:
            raise SerializationException

        self.searchStr = stream.serUniUtf8(self.searchStr)
        self.replaceStr = stream.serUniUtf8(self.replaceStr)
        
        self.replaceOp = stream.serBool(self.replaceOp)
        self.wholeWord = stream.serBool(self.wholeWord)
        self.caseSensitive = stream.serBool(self.caseSensitive)
        self.cycleToStart = stream.serBool(self.cycleToStart)
        self.booleanOp = stream.serBool(self.booleanOp)

        self.wildCard = stream.serString(self.wildCard)
                
        if version > 0:
            self.listWikiPagesOp.serializeBin(stream)
        else:
            # Can only happen in stream read mode
            # Reset listWikiPagesOp to default
            self.listWikiPagesOp = ListWikiPagesOperation()


    def getPackedSettings(self):
        """
        Returns a byte sequence (string) containing the current settings
        of all data members (except title and cache info (searchOpTree)).
        This can be saved in the database and restored later with
        setPackedSettings()
        """
        stream = SerializeStream(stringBuf="", readMode=False)
        self.serializeBin(stream)
        
        return stream.getBytes()
        
    
    def setPackedSettings(self, data):
        """
        Set member variables according to the byte sequence stored in
        data by getPackedSettings()
        """
        stream = SerializeStream(stringBuf=data, readMode=True)
        self.serializeBin(stream)
        
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
            self.searchOpTree = self._buildSearchCriterion(self.searchStr)

        else:
            # TODO More features
            andPatterns = self.searchStr.split(u' and ')

            if len(andPatterns) == 1:
                self.searchOpTree = self._buildSearchCriterion(self.searchStr)
            else:
                # Build up tree (bottom-up)
                node = AndSearchNode(self, self._buildSearchCriterion(andPatterns[-2]),
                        self._buildSearchCriterion(andPatterns[-1]))
                for i in xrange(len(andPatterns) - 3, -1, -1):
                    node = AndSearchNode(self, 
                            self._buildSearchCriterion(andPatterns[i]), node)
                    
                self.searchOpTree = node


    def _buildSearchCriterion(self, searchStr):
        """
        Build single search criterion e.g. as part of a boolean search
        and return the node.
        """
        if not self.reNeeded():
            # TODO: Test if really faster than REs
            return SimpleStrNode(self, searchStr)
        else:
            if self.wildCard == 'no':
                searchStr = re.escape(searchStr)

            if self.wholeWord:
                searchStr = ur"\b%s\b" % searchStr
                
            if self.caseSensitive:
                reFlags = re.MULTILINE | re.UNICODE
            else:
                reFlags = re.IGNORECASE | re.MULTILINE | re.UNICODE
                
            return RegexTextNode(self, re.compile(searchStr, reFlags))


    def searchText(self, text, searchCharStartPos=0):
        """
        Applies the search operation on text and returns a
        tuple with at least two elements <first char>, <after last char>
        with position of found data or (None, None) if search
        was unsuccessful.
        
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


    def beginWikiSearch(self, wikiDocument):
        """
        Called by WikiDocument(=WikiDataManager) to begin a wiki-wide search
        """
        self.wikiDocument = wikiDocument

        if self.searchOpTree is None:
            self.rebuildSearchOpTree()
            
        self.listWikiPagesOp.beginWikiSearch(wikiDocument)
            
        return self.searchOpTree.beginWikiSearch(wikiDocument)
        

    def endWikiSearch(self):
        """
        End a wiki-wide search
        """
        if self.searchOpTree is None:
            self.rebuildSearchOpTree()   # TODO: Error ?
            
        result = self.searchOpTree.endWikiSearch()
        self.listWikiPagesOp.endWikiSearch()
        self.wikiDocument = None

        return result
        

    def testWikiPage(self, word, text):
        """
        Test, if page fulfills the search criteria and is listed
        from contained listWikiPagesOp and return
        truth value. This is useful for wiki-wide searching for pages.
        
        word -- Naked wiki word of the page
        text -- Textual content of the page
        """
        if self.searchOpTree is None:
            self.rebuildSearchOpTree()
            
        return self.listWikiPagesOp.testWikiPage(word, text) and \
                self.searchOpTree.testWikiPage(word, text)


    def applyOrdering(self, wordSet, coll):
        """
        Returns the wordSet set ordered as defined in self.ordering. It must
        be called after beginWikiSearch() and before corresponding
        endWikiSearch() call.

        wordSet must be a mutable set and may be modified during operation.
        """
        if self.ordering == "no":
            return list(wordSet)
        elif self.ordering == "ascending":
            result = list(wordSet)
            coll.sort(result)
            return result
        elif self.ordering == "natural":
            return self.orderNatural(wordSet, coll)
            
        return list(wordSet)  # TODO Error


    def orderNatural(self, wordSet, coll):
        """
        Return the list of words in a natural order. Meaning of "natural"
        is defined by the called search node(s). It must be called after
        beginWikiSearch() and before corresponding endWikiSearch() call.
        
        wordSet -- mutable set of words to order "natural"
        coll -- Collator for sorting
        """
#         wordSet = {}
#         for w in words:
#             wordSet[w] = None
#             
        if self.searchOpTree is None:
            self.rebuildSearchOpTree()
            
        naturalList = self.searchOpTree.orderNatural(wordSet, coll)
        remain = list(wordSet)
        remain.sort()
        
        return naturalList + remain


