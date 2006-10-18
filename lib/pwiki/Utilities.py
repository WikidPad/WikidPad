import threading

class ThreadTerm(Exception): pass


class _DumbThreadHolder(object):
    """
    Used for synchronous operations where no thread holder is necessary
    """
    __slots__ = ()
    
    def isCurrent(self):
        return True
        
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
        
#     def testCurrent(self):
#         """
#         Throws ThreadTerm if self.thread is not equal current thread
#         """

    def isCurrent(self):
        return threading.currentThread() is self.thread


# class FlagHolder(object):
#     __slots__ = ("__weakref__", "flag")
#     
#     def __init__(self):
#         self.flag = True
#         
#     def setFlag(self, f):
#         self.flag = flag
        
    
