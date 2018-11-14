import re, traceback

import wx

from .WikiExceptions import *

from .Serialization import SerializeStream, findXmlElementFlat, \
        iterXmlElementFlat, serToXmlUnicode, serFromXmlUnicode, \
        serToXmlBoolean, serFromXmlBoolean, serToXmlInt, serFromXmlInt

from . import SearchAndReplaceBoolLang



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
    
    def beginWikiSearch(self, wikiDocument, commonCache):
        """
        Always called before a new wiki-wide search operation begins
        commonCache -- a dictionary where search nodes can place information
            to avoid multiple retrieving of the same data from database.
            Each node is called with the same object.
        """
        pass
    
    def endWikiSearch(self):
        """
        Called after a wiki-wide search operation ended
        """
        pass

    def testWikiPage(self, word, text):
        """
        Test, if wiki page fulfills the search criteria and returns a tuple
        (<truth value>. This is useful for wiki-wide searching for pages.
        
        word -- Naked wiki word of the page
        text -- Textual content of the page
        """
#         return self.testText(text)
        raise NotImplementedError
        
    def isTextNeededForTest(self):
        """
        Returns False iff the  text  parameter in testWikiPage() can be None.
        Should return True in case of doubt.
        """
        return True
        

#     def testText(self, text):
#         """
#         DEPRECATED
#         Test, if text of a page fulfills the search criteria and return
#         truth value. This is useful for wiki-wide searching for pages.
#         
#         Remarks:
#         - If the node contains non text-related criteria,
#           they are ignored (interpreted as 'unknown' in boolean logic).
#           If the truth value can't be determined, the Unknown object is
#           returned
#         """
#         assert 0  # Abstract


    def serializeBin(self, stream):
        """
        Read or write content of this object to or from a serialize stream

        stream -- StringOps.SerializeStream object
        """
        raise NotImplementedError
    
    def serializeToXml(self, xmlNode, xmlDoc):
        """
        Add to xmlNode all information about this object.
        """
        raise NotImplementedError


    def serializeFromXml(self, xmlNode):
        """
        Set object state from data in xmlNode)
        """
        raise NotImplementedError


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
        Return all words used as roots of subtrees (if any) for better tree sorting.
        Do not assume that all returned words are valid!
        """
        return []
        
    def hasParticularTextPosition(self):
        """
        Returns True if a found entry has a particular text position (means
        to support the additonal AbstractContentSearchNode methods
        searchText(), matchesPart(), replace() ).

        Call it for the root of a tree, it will automatically ask its children.
        """
        return False



class NotSearchNode(AbstractSearchNode):
    """
    Inverts the meaning of the subnode
    """
    
    CLASS_PERSID = "Not"  # Class id for persistence storage

    def __init__(self, sarOp, sub=None):
        AbstractSearchNode.__init__(self, sarOp)
        self.sub = sub
        
    def beginWikiSearch(self, wikiDocument, commonCache):
        self.sub.beginWikiSearch(wikiDocument, commonCache)
        
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

    def isTextNeededForTest(self):
        return self.sub.isTextNeededForTest()

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


    def serializeToXml(self, xmlNode, xmlDoc):
        """
        Modify XML node to contain all information about this object.
        """
        subNode = xmlDoc.createElement("node")
        _serNodeToXml(subNode, xmlDoc, self.sub)
        xmlNode.appendChild(subNode)


    def serializeFromXml(self, xmlNode):
        """
        Set object state from data in xmlNode)
        """
        subNode = findXmlElementFlat(xmlNode, "node")
        self.sub = _serNodeFromXml(subNode, self.sarOp)



# ----- Page list construction nodes -----

class AllWikiPagesNode(AbstractSearchNode):
    """
    Returns True for any page
    """
    
    CLASS_PERSID = "AllPages"  # Class id for persistence storage

    def __init__(self, sarOp):
        AbstractSearchNode.__init__(self, sarOp)
        self.wikiName = None
#         print "--AllWikiPagesNode4"
#         traceback.print_stack()
    
    def beginWikiSearch(self, wikiDocument, commonCache):
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
        
    def isTextNeededForTest(self):
        return False

    def searchText(self, text, searchCharStartPos=0, cycleToStart=False):
        return (0, 0)


    def serializeBin(self, stream):
        """
        Read or write content of this object to or from a serialize stream

        stream -- StringOps.SerializeStream object
        """
        version = stream.serUint32(0)
        
        if version != 0:
            raise SerializationException

    def serializeToXml(self, xmlNode, xmlDoc):
        """
        Modify XML node to contain all information about this object.
        """
        pass


    def serializeFromXml(self, xmlNode):
        """
        Set object state from data in xmlNode)
        """
        pass


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
    
    def __init__(self, sarOp, pattern=""):
        AbstractSearchNode.__init__(self, sarOp)
        self.compPat = re.compile(pattern,
                re.DOTALL | re.UNICODE | re.MULTILINE)  # TODO MULTILINE?
    
    def testWikiPage(self, word, text):
        return bool(self.compPat.match(word))

    def isTextNeededForTest(self):
        return False

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

    def serializeToXml(self, xmlNode, xmlDoc):
        """
        Modify XML node to contain all information about this object.
        """
        serToXmlUnicode(xmlNode, xmlDoc, "pattern", self.compPat.pattern)


    def serializeFromXml(self, xmlNode):
        """
        Set object state from data in xmlNode)
        """
        pattern = serFromXmlUnicode(xmlNode, "pattern")
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


    def beginWikiSearch(self, wikiDocument, commonCache):
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
        return word in self.wordSet

    def isTextNeededForTest(self):
        return False


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
            for i in range(rwl):
                lst.append(stream.serUniUtf8(""))
                
            self.rootWords = lst
        else:
            stream.serUint32(len(self.rootWords))
            for item in self.rootWords:
                stream.serUniUtf8(item)

        # Serialize the level
        self.level = stream.serInt32(self.level)


    def serializeToXml(self, xmlNode, xmlDoc):
        """
        Modify XML node to contain all information about this object.
        """
        serToXmlInt(xmlNode, xmlDoc, "level", self.level)

        for item in self.rootWords:
            subNode = xmlDoc.createElement("wikiword")
            subNode.appendChild(xmlDoc.createTextNode(item))
            xmlNode.appendChild(subNode)

    def serializeFromXml(self, xmlNode):
        """
        Set object state from data in xmlNode)
        """
        
        words = []
        
        for subNode in iterXmlElementFlat(xmlNode, "wikiword"):
            words.append(subNode.firstChild.data)

        self.rootWords = words
        self.level = serFromXmlInt(xmlNode, "level")


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
        persId = stream.serUniUtf8("")
        cl = _PERSID_TO_CLASS_MAP[persId]
        obj = cl(sarOp)
        obj.serializeBin(stream)
        return obj
    else:
        stream.serUniUtf8(obj.CLASS_PERSID)
        obj.serializeBin(stream)
        return obj


def _serNodeToXml(xmlNode, xmlDoc, obj):
    xmlNode.setAttribute("persistenceClass", str(obj.CLASS_PERSID))
    obj.serializeToXml(xmlNode, xmlDoc)
#     xmlNode.appendChild(subNode)
    return obj


def _serNodeFromXml(xmlNode, sarOp):
    global _PERSID_TO_CLASS_MAP
    persId = xmlNode.getAttribute("persistenceClass")
    cl = _PERSID_TO_CLASS_MAP[persId]
    obj = cl(sarOp)
    obj.serializeFromXml(xmlNode)
    return obj



# -------------------- Text search criteria --------------------

class AbstractContentSearchNode(AbstractSearchNode):
    """
    Base class for all nodes which check a single criterion
    """
    def __init__(self, sarOp):
        AbstractSearchNode.__init__(self, sarOp)

    def searchDocPageAndText(self, docPage, text, searchCharStartPos=0,
            cycleToStart=False):
        """
        Default implementation to apply search operation on docPage.
        Calls searchText().
        """
        if docPage is None:
            return (None, None)
        return self.searchText(text, searchCharStartPos=searchCharStartPos,
                cycleToStart=cycleToStart)

    def searchText(self, text, searchCharStartPos=0, cycleToStart=False):
        """
        Applies the search operation on text and returns either
        tuple (<first char>, <after last char>) with position of
        found data or (None, None) if search was unsuccessful.
        Attention: The actually returned tuple may contain more than two items.
        May only be called if hasParticularTextPosition() returns True.
        """
        return (None, None)

#     def testText(self, text):
#         return Unknown
        
    def matchesPart(self, text, range):
        """
        Test if string text[range[0]: range[1]] matches operation. Mainly called before
        a replacement is done.
        May only be called if hasParticularTextPosition() returns True.
        """
        assert 0  # abstract

    def replace(self, text, foundData, pattern):
        """
        Return the content with which the area determined by searchData
        should be replaced.
        
        text -- Full text which was prior fed to searchText()
        foundData -- tuple returned by searchText(), containing
                start and end position of found data and maybe
                additional objects. searchData must come from the
                searchText() method of the same node for which
                replace() is called now.
        pattern -- Pattern of the replacement, e.g. an RE pattern
                for regular expressions
        May only be called if hasParticularTextPosition() returns True.
        """
        assert 0  # abstract

    def hasParticularTextPosition(self):
        """
        Returns True if a found entry has a particular text position (means
        to support the additonal AbstractContentSearchNode methods
        searchText(), matchesPart(), replace() ).

        Call it for the root of a tree, it will automatically ask its children.
        """
        return True


class AbstractAndOrSearchNode(AbstractContentSearchNode):
    """
    Connects two nodes by logical "and" or "or".
    """
    def __init__(self, sarOp, left, right):
        AbstractSearchNode.__init__(self, sarOp)
        self.left = left
        self.right = right
        self.partTextPosChildren = None

    def beginWikiSearch(self, wikiDocument, commonCache):
        self.left.beginWikiSearch(wikiDocument, commonCache)
        self.right.beginWikiSearch(wikiDocument, commonCache)
        
        ptpc = []
        if self.left.hasParticularTextPosition():
            ptpc.append(self.left)
        
        if self.right.hasParticularTextPosition():
            ptpc.append(self.right)
        
        self.partTextPosChildren = ptpc


    def endWikiSearch(self):
        """
        Called after a wiki-wide search operation ended
        """
        self.left.endWikiSearch()
        self.right.endWikiSearch()

        
    def testWikiPage(self, word, text):
        raise NotImplementedError  # abstract

    def isTextNeededForTest(self):
        return self.left.isTextNeededForTest() or self.right.isTextNeededForTest()

    def searchDocPageAndText(self, docPage, text, searchCharStartPos=0,
            cycleToStart=False):
        """
        Applies the search operation on text and returns either
        tuple (<first char>, <after last char>) with position of
        found data or (None, None) if search was unsuccessful.
        May only be called if hasParticularTextPosition() returns True.
        """
        firstPos = -1
        firstFound = (None, None)
        for child in self.partTextPosChildren:
            found = child.searchDocPageAndText(docPage, text, searchCharStartPos,
                    cycleToStart=False)
            if found[0] is not None and (firstPos == -1 or firstPos > found[0]):
                firstPos = found[0]
                firstFound = found + (child,)

        if firstFound[0] is not None:
            return firstFound

        if not cycleToStart or searchCharStartPos == 0:
            # We started at beginning, so nothing more to search
            return (None, None)

        # Try again from beginning
        for child in self.partTextPosChildren:
            found = child.searchDocPageAndText(docPage, text, 0,
                    cycleToStart=False)
            if found[0] is not None and (firstPos == -1 or firstPos > found[0]):
                firstPos = found[0]
                firstFound = found + (child,)

        return firstFound


    def searchText(self, text, searchCharStartPos=0, cycleToStart=False):
        """
        Applies the search operation on text and returns either
        tuple (<first char>, <after last char>) with position of
        found data or (None, None) if search was unsuccessful.
        May only be called if hasParticularTextPosition() returns True.
        """
        firstPos = -1
        firstFound = (None, None)
        for child in self.partTextPosChildren:
            found = child.searchText(text, searchCharStartPos, cycleToStart=False)
            if found[0] is not None and (firstPos == -1 or firstPos > found[0]):
                firstPos = found[0]
                firstFound = found + (child,)

        if firstFound[0] is not None:
            return firstFound

        if not cycleToStart or searchCharStartPos == 0:
            # We started at beginning, so nothing more to search
            return (None, None)

        # Try again from beginning
        for child in self.partTextPosChildren:
            found = child.searchText(text, 0, cycleToStart=False)
            if found[0] is not None and (firstPos == -1 or firstPos > found[0]):
                firstPos = found[0]
                firstFound = found + (child,)

        return firstFound


    def matchesPart(self, text, range):
        """
        Test if string text[range[0]: range[1]] matches operation. Mainly called before
        a replacement is done.
        May only be called if hasParticularTextPosition() returns True.
        """
        for child in self.partTextPosChildren:
            if child.matchesPart(text, range):
                return True
        
        return False


    def replace(self, text, foundData, pattern):
        """
        Return the content with which the area determined by searchData
        should be replaced.
        
        text -- Full text which was prior fed to searchText()
        foundData -- tuple returned by searchText(), containing
                start and end position of found data and maybe
                additional objects. foundData must come from the
                searchText() method of the same node for which
                replace() is called now.
        pattern -- Pattern of the replacement, e.g. an RE pattern
                for regular expressions
        May only be called if hasParticularTextPosition() returns True.
        """
        child = foundData[-1]
        foundData = foundData[:-1]

        return child.replace(text, foundData, pattern)

    def hasParticularTextPosition(self):
        """
        Returns True if a found entry has a particular text position (means
        to support the additonal AbstractContentSearchNode methods
        searchText(), matchesPart(), replace() ).

        Call it for the root of a tree, it will automatically ask its children.
        """
        return len(self.partTextPosChildren) > 0  # self.partTextPosChild is not None


    def orderNatural(self, wordSet, coll):
        """
        Order of left operand has priority
        """
        leftret = self.left.orderNatural(wordSet, coll)

        if len(wordSet) == 0:
            return leftret

        rightret = self.right.orderNatural(wordSet, coll)

        return leftret + rightret



class AndSearchNode(AbstractAndOrSearchNode):
    """
    Connects two nodes by logical "and"
    """
    CLASS_PERSID = "And"  # Class id for persistence storage

    def testWikiPage(self, word, text):
        leftret = self.left.testWikiPage(word, text)
        
        if leftret == False:
            return False
            
        rightret = self.right.testWikiPage(word, text)
        
        if rightret == False:
            return False

        if leftret == True and rightret == True:
            return True
            
        return Unknown


class OrSearchNode(AbstractAndOrSearchNode):
    """
    Connects two nodes by logical "or"
    """
    CLASS_PERSID = "Or"  # Class id for persistence storage

    def testWikiPage(self, word, text):
        leftret = self.left.testWikiPage(word, text)
        
        if leftret == True:
            return True
            
        rightret = self.right.testWikiPage(word, text)
        
        if rightret == True:
            return True

        if leftret == False and rightret == False:
            return False

        return Unknown



class RegexTextNode(AbstractContentSearchNode):
    """
    Check if regex matches the contained text
    """
    CLASS_PERSID = "RegexText"  # Class id for persistence storage

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


    def testWikiPage(self, word, text):
        return bool(self.rePattern.search(text))

#     def testText(self, text):
#         return bool(self.rePattern.search(text))


    def matchesPart(self, text, range):
        """
        Test if string text[range[0]: range[1]] matches operation. Mainly called before
        a replacement is done.
        """
#         match = self.rePattern.match(toReplace)
        match = self.rePattern.match(text, range[0], range[1])

        if match:
            return (match.start(0), match.end(0), match)
        else:
            return None

    def replace(self, text, foundData, pattern):
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


    def testWikiPage(self, word, text):
        return text.find(self.subStr) != -1


#     def testText(self, text):
#         return text.find(self.subStr) != -1

    def matchesPart(self, text, range):
        """
        Test if string text[range[0]: range[1]] matches operation. Mainly called before
        a replacement is done.
        """
#         if self.subStr == toReplace:
        if self.subStr == text[range[0]: range[1]]:
            return (range[0], range[0] + len(self.subStr))
        else:
            return None

    def replace(self, text, foundData, pattern):
        return pattern


class AttributeNode(AbstractContentSearchNode):
    CLASS_PERSID = "Attribute"  # Class id for persistence storage
    def __init__(self, sarOp, pattern, valuePattern):
        AbstractContentSearchNode.__init__(self, sarOp)
        self.compPat = re.compile(pattern,
                re.DOTALL | re.UNICODE | re.MULTILINE)  # TODO MULTILINE?

        self.compValuePat = re.compile(valuePattern,
                re.DOTALL | re.UNICODE | re.MULTILINE)  # TODO MULTILINE?

        # wordSet and wordList always contain the same words
        self.wordSet = None    # used for testWikiPage()


    def searchDocPageAndText(self, docPage, text, searchCharStartPos=0,
            cycleToStart=False):
        """
        """
        if docPage is None:
            return (None, None)
        
        wikiWord = docPage.getWikiWord()
        
        pageAst = docPage.getLivePageAst()
        if pageAst is None:
            return (None, None)
        
        # Note: extractAttributeNodesFromPageAst() returns an iterator

        for node in docPage.extractAttributeNodesFromPageAst(pageAst):
            if node.pos < searchCharStartPos:
                continue
            for k, v in node.attrs:
                if self._checkAttribute(wikiWord, k, v):
                    return (node.pos, node.pos + node.strLength)

        if cycleToStart and searchCharStartPos > 0:
            # Try again from beginning
            for node in docPage.extractAttributeNodesFromPageAst(pageAst):
                if node.pos >= searchCharStartPos:
                    break
                for k, v in node.attrs:
                    if self._checkAttribute(wikiWord, k, v):
                        return (node.pos, node.pos + node.strLength)

        # Not found
        return (None, None)



    def _getAllAttributes(self, wikiDocument, commonCache):
        allAttributes = commonCache.get("allAttributes")
        
        if allAttributes is None:
            allAttributes = wikiDocument.getAttributeTriples(None, None, None)
            commonCache["allAttributes"] = allAttributes

        return allAttributes


    def beginWikiSearch(self, wikiDocument, commonCache):
        """
        Always called before a new wiki-wide search operation begins.
        Fills wordSet.
        TODO: Maybe use alternative implementation if only a few words are
        checked
        """
        wordSet = set()
        
        for w, k, v in self._getAllAttributes(wikiDocument, commonCache):
            if self._checkAttribute(w, k, v):
                wordSet.add(w)

        self.wordSet = wordSet

    def _checkAttribute(self, w, k, v):
        return self.compPat.search(k) and self.compValuePat.search(v)

    def testWikiPage(self, word, text):
        return word in self.wordSet

    def isTextNeededForTest(self):
        return False

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

    def serializeToXml(self, xmlNode, xmlDoc):
        """
        Modify XML node to contain all information about this object.
        """
        serToXmlUnicode(xmlNode, xmlDoc, "pattern", self.compPat.pattern)


    def serializeFromXml(self, xmlNode):
        """
        Set object state from data in xmlNode)
        """
        pattern = serFromXmlUnicode(xmlNode, "pattern")
        if pattern != self.compPat.pattern:
            self.compPat = re.compile(pattern,
                re.DOTALL | re.UNICODE | re.MULTILINE)  # TODO MULTILINE?

    def getPattern(self):
        """
        Return the pattern string
        """
        return self.compPat.pattern


    def endWikiSearch(self):
        """
        Called after a wiki-wide search operation ended.
        Clears wordList
        """
        self.wordSet = None



class TodoNode(AbstractContentSearchNode):
    CLASS_PERSID = "Todo"  # Class id for persistence storage
    def __init__(self, sarOp, pattern, valuePattern):
        AbstractContentSearchNode.__init__(self, sarOp)
        self.compPat = re.compile(pattern,
                re.DOTALL | re.UNICODE | re.MULTILINE)  # TODO MULTILINE?

        self.compValuePat = re.compile(valuePattern,
                re.DOTALL | re.UNICODE | re.MULTILINE)  # TODO MULTILINE?

        # wordSet and wordList always contain the same words
        self.wordSet = None    # used for testWikiPage()


    def searchDocPageAndText(self, docPage, text, searchCharStartPos=0,
            cycleToStart=False):
        """
        """
        if docPage is None:
            return (None, None)
        
        wikiWord = docPage.getWikiWord()
        
        pageAst = docPage.getLivePageAst()
        if pageAst is None:
            return (None, None)
        
        # Note: extractAttributeNodesFromPageAst() returns an iterator

        for node in docPage.extractTodoNodesFromPageAst(pageAst):
            if node.pos < searchCharStartPos:
                continue
            if self._checkTodo(wikiWord, node.key, node.valueNode.getString()):
                return (node.pos, node.pos + node.strLength)

        if cycleToStart and searchCharStartPos > 0:
            # Try again from beginning
            for node in docPage.extractTodoNodesFromPageAst(pageAst):
                if node.pos >= searchCharStartPos:
                    break
                if self._checkTodo(wikiWord, node.key, node.valueNode.getString()):
                    return (node.pos, node.pos + node.strLength)

        # Not found
        return (None, None)


    def _getAllTodos(self, wikiDocument, commonCache):
        allTodos = commonCache.get("allTodos")
        
        if allTodos is None:
            allTodos = wikiDocument.getTodos()
            commonCache["allTodos"] = allTodos

        return allTodos


    def beginWikiSearch(self, wikiDocument, commonCache):
        """
        Always called before a new wiki-wide search operation begins.
        Fills wordSet.
        TODO: Maybe use alternative implementation if only a few words are
        checked
        """
        wordSet = set()
        
        for w, k, v in self._getAllTodos(wikiDocument, commonCache):
            if self._checkTodo(w, k, v):
                wordSet.add(w)

        self.wordSet = wordSet

    def _checkTodo(self, w, k, v):
        return self.compPat.search(k) and self.compValuePat.search(v)

    def testWikiPage(self, word, text):
        return word in self.wordSet

    def isTextNeededForTest(self):
        return False

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

    def serializeToXml(self, xmlNode, xmlDoc):
        """
        Modify XML node to contain all information about this object.
        """
        serToXmlUnicode(xmlNode, xmlDoc, "pattern", self.compPat.pattern)


    def serializeFromXml(self, xmlNode):
        """
        Set object state from data in xmlNode)
        """
        pattern = serFromXmlUnicode(xmlNode, "pattern")
        if pattern != self.compPat.pattern:
            self.compPat = re.compile(pattern,
                re.DOTALL | re.UNICODE | re.MULTILINE)  # TODO MULTILINE?

    def getPattern(self):
        """
        Return the pattern string
        """
        return self.compPat.pattern


    def endWikiSearch(self):
        """
        Called after a wiki-wide search operation ended.
        Clears wordList
        """
        self.wordSet = None





# ----------------------------------------------------------------------


# Special whoosh formatter class
class SimpleHtmlFormatter:
    """Returns a string in which the matched terms are enclosed in <b></b>.
    """
    
    def __init__(self, between="... "):
        """
        :param between: the text to add between fragments.
        """
        self.between = between
        self.firstPos = -1
        
    def _format_fragment(self, text, fragment):
        from pwiki.StringOps import escapeHtml as htmlescape

        output = []
        index = fragment.startchar
        
        for t in fragment.matches:
            if t.startchar > index:
                output.append(htmlescape(text[index:t.startchar]))

            ttxt = htmlescape(text[t.startchar:t.endchar])
            if t.matched:
                ttxt = "<b>%s</b>" % ttxt
                if self.firstPos == -1:
                    self.firstPos = t.startchar
                else:
                    self.firstPos = min(self.firstPos, t.startchar)

            output.append(ttxt)
            index = t.endchar
        
        output.append(htmlescape(text[index:fragment.endchar]))
        return "".join(output)

    def __call__(self, text, fragments):
        return self.between.join([self._format_fragment(text, fragment)
                                  for fragment in fragments]), self.firstPos




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
        
#     def setWikiDocument(self, wikiDoc):
#         self.wikiDocument = wikiDoc
#     
#     def getWikiDocument(self):
#         return self.wikiDocument

    def serializeBin(self, stream):
        """
        Read or write content of this object to or from a serialize stream

        stream -- StringOps.SerializeStream object
        """
        self.ordering = stream.serUniUtf8(self.ordering)
        self.searchOpTree = _serNode(stream, self, self.searchOpTree)


    def serializeToXml(self, xmlNode, xmlDoc):
        """
        Modify XML node to contain all information about this object.
        """
        serToXmlUnicode(xmlNode, xmlDoc, "ordering", self.ordering)
        
        subNode = xmlDoc.createElement("optree")
        subNode2 = xmlDoc.createElement("node")
        _serNodeToXml(subNode2, xmlDoc, self.searchOpTree)
        subNode.appendChild(subNode2)
        xmlNode.appendChild(subNode)



    def serializeFromXml(self, xmlNode):
        """
        Set object state from data in xmlNode)
        """
        self.ordering = serFromXmlUnicode(xmlNode, "ordering")

        subNode = findXmlElementFlat(xmlNode, "optree")
        subNode = findXmlElementFlat(subNode, "node")

        self.searchOpTree = _serNodeFromXml(subNode, self)


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


    def beginWikiSearch(self, wikiDocument, commonCache=None):
        """
        Called by WikiDocument to begin a wiki-wide search
        """
        self.wikiDocument = wikiDocument

        if self.searchOpTree is None:
            return   # TODO: Error ?
            
        if commonCache is None:
            commonCache = {}

        return self.searchOpTree.beginWikiSearch(wikiDocument, commonCache)


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

    def isTextNeededForTest(self):
        """
        Returns False iff the  text  parameter in testWikiPage() can be None.
        Should return True in case of doubt.
        """
        if self.searchOpTree is None:
            return True

        return self.searchOpTree.isTextNeededForTest()


    def testWikiPageByDocPage(self, docPage):
        return self.testWikiPage(docPage.getWikiWord(), docPage.getLiveText())

    def getRootWords(self):
        """
        Return all words used as roots of subtrees (if any) for better tree sorting
        It must be called after beginWikiSearch() and before corresponding
        endWikiSearch() call.
        Only valid wiki refs are returned.
        """
        if self.searchOpTree is None:
            return []

        return [w for w in self.searchOpTree.getRootWords() 
                if self.wikiDocument.isDefinedWikiLinkTerm(w)]


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
            rootWordSet = set(self.getRootWords())
            rootWordSet.intersection_update(wordSet)
            wordSet.difference_update(rootWordSet)

            for rootWord in rootWords:
                rootPage = self.wikiDocument.getWikiPage(rootWord)
                flatTree = rootPage.getFlatTree(unalias=True,
                        includeSet=wordSet.copy())

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
        self.indexSearch = 'no'  # Reverse index search, either 'no' or 'default'
        self.wildCard = 'regex' # Search string is: 'regex':regular expression
                                # (and replace str.) 'no':Without wildcards
        self.wikiWide = False   # Operation on whole wiki (or current page only)?

        self.title = None       # Title of the search for saving it. Use getter
                                # and setter to retrieve/modify value
#         self.ordering = "no"    # How to order the pages

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

        
#     def setWikiDocument(self, wikiDoc):
#         self.wikiDocument = wikiDoc
#         if self.listWikiPagesOp is not None:
#             self.listWikiPagesOp.setWikiDocument(wikiDoc)
# 
#     def getWikiDocument(self):
#         return self.wikiDocument

    
    def serializeBin(self, stream):
        """
        Read or write content of this object to or from a serialize stream

        stream -- StringOps.SerializeStream object
        """
        version = 2
        if not stream.isReadMode():
            # Adjust to lowest possible version
            if self.indexSearch == 'no':
                version = 1
        
        version = stream.serUint32(version)
        
        if version < 0 or version > 2:
            raise SerializationException

        self.searchStr = stream.serUniUtf8(self.searchStr)
        self.replaceStr = stream.serUniUtf8(self.replaceStr)
        
        self.replaceOp = stream.serBool(self.replaceOp)
        self.wholeWord = stream.serBool(self.wholeWord)
        self.caseSensitive = stream.serBool(self.caseSensitive)
        self.cycleToStart = stream.serBool(self.cycleToStart)
        self.booleanOp = stream.serBool(self.booleanOp)

        self.wildCard = stream.serUniUtf8(self.wildCard)

        if version > 0:
            self.listWikiPagesOp.serializeBin(stream)
        else:
            # Can only happen in stream read mode
            # Reset listWikiPagesOp to default
            self.listWikiPagesOp = ListWikiPagesOperation()
        
        if version > 1:
            self.indexSearch = stream.serUniUtf8(self.indexSearch)
        elif stream.isReadMode():
            self.indexSearch = 'no'
        


    def serializeToXml(self, xmlNode, xmlDoc):
        """
        Modify XML node to contain all information about this object.
        """
        serToXmlUnicode(xmlNode, xmlDoc, "searchPattern", self.searchStr)
        serToXmlUnicode(xmlNode, xmlDoc, "replacePattern", self.replaceStr)

        serToXmlBoolean(xmlNode, xmlDoc, "replaceOperation", self.replaceOp)
        serToXmlBoolean(xmlNode, xmlDoc, "wholeWord", self.wholeWord)
        serToXmlBoolean(xmlNode, xmlDoc, "caseSensitive", self.caseSensitive)
        serToXmlBoolean(xmlNode, xmlDoc, "cycleToStart", self.cycleToStart)
        serToXmlBoolean(xmlNode, xmlDoc, "booleanOperation", self.booleanOp)
        serToXmlUnicode(xmlNode, xmlDoc, "indexSearch", str(self.indexSearch))

        serToXmlUnicode(xmlNode, xmlDoc, "wildCardMode", str(self.wildCard))

        subNode = xmlDoc.createElement("listWikiPagesOperation")
        xmlNode.appendChild(subNode)

        self.listWikiPagesOp.serializeToXml(subNode, xmlDoc)


    def serializeFromXml(self, xmlNode):
        """
        Set object state from data in xmlNode)
        """
        self.searchStr = serFromXmlUnicode(xmlNode, "searchPattern")
        self.replaceStr = serFromXmlUnicode(xmlNode, "replacePattern")

        self.replaceOp = serFromXmlBoolean(xmlNode, "replaceOperation")
        self.wholeWord = serFromXmlBoolean(xmlNode, "wholeWord")
        self.caseSensitive = serFromXmlBoolean(xmlNode, "caseSensitive")
        self.cycleToStart = serFromXmlBoolean(xmlNode, "cycleToStart")
        self.booleanOp = serFromXmlBoolean(xmlNode, "booleanOperation")

        self.wildCard = serFromXmlUnicode(xmlNode, "wildCardMode")

        subNode = findXmlElementFlat(xmlNode, "listWikiPagesOperation")

        self.listWikiPagesOp = ListWikiPagesOperation()
        self.listWikiPagesOp.serializeFromXml(subNode)

        self.indexSearch = serFromXmlUnicode(xmlNode, "indexSearch", "no")


    def getPackedSettings(self):
        """
        Returns bytes containing the current settings
        of all data members (except title and cache info (searchOpTree)).
        This can be saved in the database and restored later with
        setPackedSettings()
        """
        stream = SerializeStream(byteBuf=b"", readMode=False)
        self.serializeBin(stream)

        return stream.getBytes()


    def setPackedSettings(self, data):
        """
        Set member variables according to the bytes stored in
        data by getPackedSettings()
        """
        stream = SerializeStream(byteBuf=data, readMode=True)
        self.serializeBin(stream)

        self.clearCache()


    def _reNeeded(self):
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
        searchText() if necessary.
        May throw RE exception or WikiPyparsing.ParseException if
        the search string has syntax errors.
        """
        if self.searchStr == "":
            self.searchOpTree = AllWikiPagesNode(self)
            return
        
        if self.indexSearch != "no":
            # Search tree not used, but non-None value needed
            self.searchOpTree = AllWikiPagesNode(self)
            return

        if not self.booleanOp:
            self.searchOpTree = self._buildSearchTerm(self.searchStr)
        else:
            parseResult = SearchAndReplaceBoolLang.parse(self.searchStr)
            self.searchOpTree = self._buildBooleanSearchTree(parseResult)


    def _buildSearchTerm(self, searchStr):
        """
        Build single search criterion e.g. as part of a boolean search
        and return the node. May throw RE exception.
        """
        if not self._reNeeded():
            # TODO: Test if really faster than REs
            return SimpleStrNode(self, searchStr)
        else:
            if self.wildCard == 'no':
                searchStr = re.escape(searchStr)

            if self.wholeWord:
                searchStr = r"\b%s\b" % searchStr

            if self.caseSensitive:
                reFlags = re.MULTILINE | re.UNICODE
            else:
                reFlags = re.IGNORECASE | re.MULTILINE | re.UNICODE

            return RegexTextNode(self, re.compile(searchStr, reFlags))



    def _buildBooleanSearchTree(self, parseExpr):
#         print "--_buildBooleanSearchTree1", parseExpr.pprint()
        for node in parseExpr.iterFlatNamed():
            tname = node.name
            if tname == "searchExpression":
                return self._buildBooleanSearchTree(node)
            elif tname == "regexTerm":
                return self._buildSearchTerm(node.regexTerm)
            elif tname == "notExpression":
                return NotSearchNode(self, self._buildBooleanSearchTree(node.op))
            elif tname == "andExpression":
                return AndSearchNode(self, self._buildBooleanSearchTree(node.op1),
                        self._buildBooleanSearchTree(node.op2))
            elif tname == "concatExprLevel1":
                return AndSearchNode(self, self._buildBooleanSearchTree(node.op1),
                        self._buildBooleanSearchTree(node.op2))
            elif tname == "orExpression":
                return OrSearchNode(self, self._buildBooleanSearchTree(node.op1),
                        self._buildBooleanSearchTree(node.op2))
            elif tname == "attributeTerm":
                return AttributeNode(self, node.key, node.value)
#             elif tname == "attributeKeyTerm":
#                 return AttributeKeyNode(self, node.prefixedTerm)
#             elif tname == "attributeValueTerm":
#                 return AttributeValueNode(self, node.prefixedTerm)
            elif tname == "todoTerm":
                return TodoNode(self, node.key, node.value)
            elif tname == "pageTerm":
                return RegexWikiPageNode(self, node.pageName)



    def searchDocPageAndText(self, docPage, text, searchCharStartPos=0):
        """
        Applies the search operation on docPage and returns a
        tuple with at least two elements <first char>, <after last char>
        with position of found data or (None, None) if search
        was not successful.

        Remarks:
        - The function works only if self.hasParticularTextPosition()
          returns True
        - The function does not apply a replacement, even if 'self'
          is a replacement operation
        """
        if not self.hasParticularTextPosition():
            return (None, None)  # TODO Exception?

        # Try to get regex pattern
        if self.searchOpTree is None:
            self.rebuildSearchOpTree()

        return self.searchOpTree.searchDocPageAndText(docPage, text,
                searchCharStartPos, self.cycleToStart)

    def iterSearchDocPageAndText(self, docPage, text, searchCharStartPos=0):
        """
        Returns iterator to consecutively find all places where the search
        matches as tuples with at least two elements <first char>, <after last char>
        """
        while True:
            found = self.searchDocPageAndText(docPage, text, searchCharStartPos)
            if found[0] is None:
                return
                
            if found[1] <= searchCharStartPos:
                searchCharStartPos += 1
            else:
                searchCharStartPos = found[1]
            
            yield found


    def searchText(self, text, searchCharStartPos=0):
        """
        Applies the search operation on text and returns a
        tuple with at least two elements <first char>, <after last char>
        with position of found data or (None, None) if search
        was not successful.

        Remarks:
        - The function works only if self.hasParticularTextPosition()
          returns True
        - The function does not apply a replacement, even if 'self'
          is a replacement operation
        """
        if not self.hasParticularTextPosition():
            return (None, None)  # TODO Exception?

        # Try to get regex pattern
        if self.searchOpTree is None:
            self.rebuildSearchOpTree()

        return self.searchOpTree.searchText(text, searchCharStartPos,
                self.cycleToStart)


    def getWhooshIndexQuery(self, wikiDocument):
        from whoosh.qparser import QueryParser

        qp = QueryParser("content", schema=wikiDocument.getWhooshIndexSchema())
        q = qp.parse(self.searchStr)
#         print "--getWhooshIndexQuery10", repr((qp, q))

        return q


    def hasWhooshHighlighting(self):
        """
        Return True iff call to highlightWhooshIndexFound() would work.
        """
        return self.indexSearch == "default"


    def highlightWhooshIndexFound(self, content, docPage, maxchars, surround,
            formatter=None):
        """
        Retrieve formatted output with highlighted search hits for a page.
        formatter -- whoosh formatter or None (uses SimpleHtmlFormatter then)
        """
        if docPage is None:
            return
        
        from whoosh import highlight

        # TODO: Loop invariant, move out?
        q = self.getWhooshIndexQuery(docPage.getWikiDocument())
        
        # Extract the terms the user mentioned
        terms = [text for fieldname, text in q.all_terms()
                if fieldname == "content"]
        
        analyzer = docPage.getWikiDocument().getWhooshIndexContentAnalyzer()
        
        # TODO: Length of before and after from config
        fragmenter = highlight.ContextFragmenter(maxchars, surround)

        if formatter is None:
            formatter = SimpleHtmlFormatter()
        
        return highlight.highlight(content, terms, analyzer,
                     fragmenter, formatter, top=1)


    def hasParticularTextPosition(self):
        if self.indexSearch != "no":
            return False   # TODO!

        if self.searchOpTree is None:
            self.rebuildSearchOpTree()

        return self.searchOpTree.hasParticularTextPosition()


    def matchesPart(self, text, range):
        """
        Test if string text[range[0]: range[1]] matches operation.
        """
        if not self.hasParticularTextPosition():
            return None  # TODO Exception?

        # Try to get regex pattern
        if self.searchOpTree is None:
            self.rebuildSearchOpTree()

        return self.searchOpTree.matchesPart(text, range)


    def replace(self, text, foundData):
        """
        Return the text which should replace the selection in text
        described by foundData (which was returned by a call to searchText)
        """
        if not self.replaceOp or not self.hasParticularTextPosition():
            return None   # TODO Exception?

        # Try to get regex pattern
        if self.searchOpTree is None:
            self.rebuildSearchOpTree()

        return self.searchOpTree.replace(text, foundData, self.replaceStr)


    def beginWikiSearch(self, wikiDocument, commonCache=None):
        """
        Called by WikiDocument to begin a wiki-wide search
        """
        self.wikiDocument = wikiDocument

        if self.searchOpTree is None:
            self.rebuildSearchOpTree()

        if commonCache is None:
            commonCache = {}

        self.listWikiPagesOp.beginWikiSearch(wikiDocument,
                commonCache=commonCache)

        return self.searchOpTree.beginWikiSearch(wikiDocument,
                commonCache=commonCache)


    def endWikiSearch(self):
        """
        End a wiki-wide search
        """
        result = None
#         if self.searchOpTree is None:
#             self.rebuildSearchOpTree()   # TODO: Error ?
        if self.searchOpTree is not None:
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


    def isTextNeededForTest(self):
        """
        Returns False iff the  text  parameter in testWikiPage() can be None.
        Should return True in case of doubt.
        """
        if self.searchOpTree is None:
            self.rebuildSearchOpTree()

        return self.listWikiPagesOp.isTextNeededForTest() or \
                self.searchOpTree.isTextNeededForTest()


    def testWikiPageByDocPage(self, docPage):
        return self.testWikiPage(docPage.getWikiWord(), docPage.getLiveText())


    def applyOrdering(self, wordSet, coll):
        """
        Returns the wordSet set ordered as defined in self.ordering. It must
        be called after beginWikiSearch() and before corresponding
        endWikiSearch() call.

        wordSet must be a mutable set and may be modified during operation.
        """
        return self.listWikiPagesOp.applyOrdering(wordSet, coll)

#         if self.ordering == "no":
#             return list(wordSet)
#         elif self.ordering == "ascending":
#             result = list(wordSet)
#             coll.sort(result)
#             return result
#         elif self.ordering == "natural":
#             return self.orderNatural(wordSet, coll)
#             
#         return list(wordSet)  # TODO Error


    def orderNatural(self, wordSet, coll):
        """
        Return the list of words in a natural order. Meaning of "natural"
        is defined by the called search node(s). It must be called after
        beginWikiSearch() and before corresponding endWikiSearch() call.
        
        wordSet -- mutable set of words to order "natural"
        coll -- Collator for sorting
        """
        if self.searchOpTree is None:
            self.rebuildSearchOpTree()
            
        naturalList = self.searchOpTree.orderNatural(wordSet, coll)
        remain = list(wordSet)
        remain.sort()
        
        return naturalList + remain



def stripSearchString(searchStr):
    """
    Strip leading and trailing spaces from a search string if appropriate
    option is set.
    """
    if wx.GetApp().getGlobalConfig().getboolean("main", "search_stripSpaces",
            True):
        return searchStr.strip(" ")
    else:
        return searchStr

