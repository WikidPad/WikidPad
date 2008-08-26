import threading

from WikiExceptions import NotCurrentThreadException

class _DumbThreadHolder(object):
    """
    Used for synchronous operations where no thread holder is necessary
    """
    __slots__ = ()
    
    def isCurrent(self):
        return True
        
    def testCurrent(self):
        pass

        
DUMBTHREADHOLDER = _DumbThreadHolder()


class ThreadHolder(_DumbThreadHolder):
    """
    Holds a thread and compares it to current. Used for asynchronous
    operations
    """
    __slots__ = ("__weakref__", "thread")
    
    def __init__(self):
        self.thread = None
        
    def getThread(self):
        return self.thread
        
    def setThread(self, thread):
        self.thread = thread
        
    def testCurrent(self):
        """
        Throws NotCurrentThreadException if self.thread is not equal to
        current thread
        """
        if threading.currentThread() is not self.thread:
            raise NotCurrentThreadException()

    def isCurrent(self):
        """
        Return True if current thread is thread in holder
        """
        return threading.currentThread() is self.thread


def seqStartsWith(seq, startSeq):
    """
    Returns True iff sequence startSeq is the beginning of sequence seq or
    equal to seq.
    """
    if len(seq) < len(startSeq):
        return False
    
    if len(seq) > len(startSeq):
        return seq[:len(startSeq)] == startSeq
    
    return seq == startSeq




# class FlagHolder(object):
#     __slots__ = ("__weakref__", "flag")
#     
#     def __init__(self):
#         self.flag = True
#         
#     def setFlag(self, f):
#         self.flag = flag
        
    
    
class StringPathSet(set):
    """
    A string path is a tuple of (uni-)strings. A StringPathSet is a set
    of those pathes with basic set functionality and a function
    to find all pathes in set which start with a given tuple of strings.
    """
    
    # TODO More efficient
    def iterStartsWith(self, startseq):
        for sp in self:
            if seqStartsWith(sp, startseq):
                yield sp
        
    def listStartsWith(self, startseq):
        return list(self.iterStartsWith(startseq))
        
    
    def discardStartsWith(self, startseq):
        """
        Discard all elements starting with startseq
        """
        for sp in self.listStartsWith(startseq):
            self.discard(sp)



class StackedCopyDict:
    """
    A stacked dictionary is technically a stack of dictionaries plus one base
    dictionary which is at the bottom of the stack and can't be dropped off.
    Along with get and set operations which are always executed on the
    stack top dictionary there are functions to push() a new dictionary on
    the stack (which is automatically a copy of the previous stack top) and
    to pop() the stack top dict.
    """
    def __init__(self, baseDict=None):
        if baseDict is None:
            self.baseDict = {}
        else:
            self.baseDict = baseDict

        self.dictStack = []

    def getTopDict(self):
        if len(self.dictStack) > 0:
            return self.dictStack[-1]
        else:
            return self.baseDict

    def __repr__(self):
        return "<StackedCopyDict " + repr(self.getTopDict()) + ">"

    def __getitem__(self, key):
        return self.getTopDict()[key]

    def __setitem__(self, key, item):
        self.getTopDict()[key] = item

    def get(self, key, failobj=None):
        return self.getTopDict().get(key, failobj)
        
    
    def push(self, newDict=None):
        """
        Push new dictionary on stack, normally a copy of previous top stack dict.
        For convenience it returns the new stack top dict.
        """
        if newDict is None:
            newDict = self.getTopDict().copy()
        
        self.dictStack.append(newDict)
        return self.dictStack[-1]


    def pop(self):
        """
        May throw exception if only base dictionary is available.
        """
        return self.dictStack.pop()













# This description may be used later for another type of stacked dict
    """
    A stacked dictionary is technically a stack of dictionaries plus one base
    dictionary which is at the bottom of the stack and can't be dropped off.
    If executing a get operation on a key, it starts at stack top and looks
    if the dict there contains the key. If not, it goes down in stack until it
    finds the key or reaches stack bottom. If even the base dict does not
    contain the key, the default given in get() or None or an exception
    (for __getitem__()) is the answer.
    A set operation is always done
    """
    
    
    
    
    
