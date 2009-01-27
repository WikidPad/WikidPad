import threading, traceback, collections
from thread import allocate_lock as _allocate_lock
from time import time as _time, sleep as _sleep


import wx

from Consts import DEADBLOCKTIMEOUT
from WikiExceptions import NotCurrentThreadException, \
        DeadBlockPreventionTimeOutError, InternalError


class Dummy(object):
    pass


class BasicThreadStop(object):
    """
    Used for synchronous operations where no thread stop condition is necessary
    """
    __slots__ = ()
    
    def isRunning(self):
        return True
        
    def testRunning(self):
        pass

        
DUMBTHREADSTOP = BasicThreadStop()


class FunctionThreadStop(BasicThreadStop):
    __slots__ = ("fct",)

    def __init__(self, fct):
        self.fct = fct
        
    def isRunning(self):
        return self.fct()
        
    def testRunning(self):
        if not self.fct():
            raise NotCurrentThreadException()



class ThreadHolder(BasicThreadStop):
    """
    Holds a thread and compares it to current. Used for asynchronous
    operations.
    """
    __slots__ = ("__weakref__", "thread")
    
    def __init__(self):
        self.thread = None
        
    def getThread(self):
        return self.thread
        
    def setThread(self, thread):
        self.thread = thread
        
    def testRunning(self):
        """
        Throws NotCurrentThreadException if self.thread is not equal to
        current thread
        """
        if threading.currentThread() is not self.thread:
            raise NotCurrentThreadException()

    def isRunning(self):
        """
        Return True if current thread is thread in holder
        """
        return threading.currentThread() is self.thread




class ExecutionResult(object):
    __slots__ = ("result", "exception", "state")

    def __init__(self):
        self.result = None
        self.exception = None
        self.state = 0   # 0: Invalid, 1: result is valid, 2: exception is valid
        
    def setResult(self, result):
        self.result = result
        self.state = 1
        
    def getReturn(self):
        if self.state == 1:
            return self.result
        elif self.state == 2:
            raise self.exception
        
        # else ?
    
    def setException(self, exception):
        self.exception = exception
        self.state = 2
    
#     def getState(self):
#         return self.state




class SingleThreadExecutor(object):
    def __init__(self, dequeCount=1, daemon=False):
        self.dequeCondition = threading.Condition()
        self.daemon = daemon
        self.dequeCount = dequeCount

        self.deques = None
        self.thread = None


    def start(self):
        if self.thread is not None and self.thread.isAlive():
            return

        with self.dequeCondition:
            if self.deques is None:
                self.deques = tuple(collections.deque()
                        for i in range(self.dequeCount))

            self.thread = threading.Thread(target=self._runQueue)
            self.thread.setDaemon(self.daemon)
            self.thread.start()


    def getDeque(self, idx=0):
        if self.deques is None:
            return None

        return self.deques[idx]


    def getDequeCondition(self):
        return self.dequeCondition
        
    
    def clearDeque(self, idx=0):
        if self.deques is None:
            return  # Error?

        with self.dequeCondition:
            self.deques[idx].clear()


    ENDOBJECT = object()

    def _getNextJob(self):
        # No lock as it is called always inside a lock
        for deque in self.deques:
            if len(deque) != 0:
                return deque.pop()
        
        return None


    def getJobCount(self, start=None, end=None):
        if start is not None and end is None:
            end = start
            start = 0

        with self.dequeCondition:
            if self.deques is None:
                return 0   # Error?
            
            if start is None:
                return sum((len(deque) for deque in self.deques), 0)
            else:
                return sum((len(deque) for deque in self.deques[start:end]), 0)

#         for deque in self.deques:
#             if len(deque) != 0:
#                 return True
#         
#         return False


    def _runQueue(self):
        while True:
            with self.dequeCondition:
                while self.deques is not None:
                    job = self._getNextJob()
                    if job is not None:
                        break
                    self.dequeCondition.wait()
                
                if self.deques is None:
                    # Executor terminated
                    return

                fct, args, kwargs, event, retObj = job
            try:
                if fct is SingleThreadExecutor.ENDOBJECT:
                    # We should stop here, but the problem is that other
                    # operations may itself pushed back on the deque
                    # and must be processed before thread can end
                    with self.dequeCondition:
                        if self.getJobCount() == 0:
                            return

                        self.deques[-1].appendleft(
                                (SingleThreadExecutor.ENDOBJECT, None, None,
                                None, None))
                        continue


#                 tracer.runctx('retObj.result = fct(*args, **kwargs)', globals(), locals())
                retObj.setResult(fct(*args, **kwargs))

            except Exception, e:
                traceback.print_exc() # ?
                retObj.setException(e)
            finally:
                if event is not None:
                    event.set()


    def execute(self, idx, fct, *args, **kwargs):
        if threading.currentThread() is self.thread:
            return fct(*args, **kwargs)
            
        if self.deques is None:
            raise InternalError("Called SingleThreadExecutor.execute() after "
                    "queue was killed")
        
        event = threading.Event()
        retObj = ExecutionResult()

        with self.dequeCondition:
            self.deques[idx].appendleft((fct, args, kwargs, event, retObj))
            self.dequeCondition.notify()

        event.wait(120)

        if not event.isSet():
            raise DeadBlockPreventionTimeOutError()
        if retObj.exception is not None:
            raise retObj.exception

        return retObj.result


    def executeAsync(self, idx, fct, *args, **kwargs):
        retObj = ExecutionResult()

        if self.deques is None:
            return retObj  # Error?

        with self.dequeCondition:
            self.deques[idx].appendleft((fct, args, kwargs, None, retObj))
            self.dequeCondition.notify()

        return retObj


    __call__ = execute


    def end(self, hardEnd=False):
        """
        Wait (up to 120 seconds) to end the running jobs.
        
        If hardEnd is False, all jobs in the queue are processed yet.
        Even new jobs can be added during this time because
        the called jobs may generate new ones under certain conditions.
        
        If hardEnd is True, executor stops after the current job.

        If the queue is empty, executor stops in each case.
        """
        if self.thread is None or not self.thread.isAlive():
            return

        with self.dequeCondition:
            if hardEnd:
                self.deques = None
            else:
                self.deques[-1].appendleft(
                        (SingleThreadExecutor.ENDOBJECT, None, None, None, None))
            self.dequeCondition.notify()

        self.thread.join(120)
        
        if self.thread.isAlive():
            raise DeadBlockPreventionTimeOutError()
        
        self.thread = None



def callInMainThread(fct, *args, **kwargs):
    if wx.Thread_IsMain() or not wx.GetApp().IsMainLoopRunning():
        return fct(*args, **kwargs)
    
    returnOb = ExecutionResult()
    event = threading.Event()


    def _mainRun(*args, **kwargs):
        try:
            returnOb.result = fct(*args, **kwargs)
        except Exception, e:
            traceback.print_exc()
            returnOb.exception = e
        finally:
            event.set()

    event.clear()
    wx.CallAfter(_mainRun, *args, **kwargs)
#     print "--callInMainThread7", repr(fct)
#     wx.SafeYield()  # Good idea?
    event.wait(DEADBLOCKTIMEOUT)
    if not event.isSet():
        raise DeadBlockPreventionTimeOutError()
    if returnOb.exception is not None:
        raise returnOb.exception
    return returnOb.result




def callInMainThreadAsync(fct, *args, **kwargs):
    if wx.Thread_IsMain() or not wx.GetApp().IsMainLoopRunning():
        return fct(*args, **kwargs)
    def _mainRun(*args, **kwargs):
        try:
            fct(*args, **kwargs)
        except Exception, e:
            traceback.print_exc()

    wx.CallAfter(_mainRun, *args, **kwargs)
#     print "--callInMainThread7", repr(fct)
#     wx.SafeYield()  # Good idea?





def TimeoutRLock(*args, **kwargs):
    return _TimeoutRLock(*args, **kwargs)

class _TimeoutRLock(threading._Verbose):
    """
    Modified version of threading._RLock from standard library
    """
    def __init__(self, timeout=None, verbose=None):
        threading._Verbose.__init__(self, verbose)
        self.__block = _allocate_lock()
        self.__owner = None
        self.__count = 0
        self.__timeout = timeout
        self.__acquiredStackTrace = None

    def __repr__(self):
        owner = self.__owner
        return "<%s(%s, %d)>" % (
                self.__class__.__name__,
                owner and owner.getName(),
                self.__count)

    def acquire(self, blocking=1):
        me = threading.currentThread()
        if self.__owner is me:
            self.__count = self.__count + 1
            if __debug__:
                self._note("%s.acquire(%s): recursive success", self, blocking)
            return 1

        if not blocking or not self.__timeout:
            rc = self.__block.acquire(blocking)
            if rc:
                self.__owner = me
                self.__count = 1
                self.__acquiredStackTrace = traceback.extract_stack()
                if __debug__:
                    self._note("%s.acquire(%s): initial success", self, blocking)
            else:
                if __debug__:
                    self._note("%s.acquire(%s): failure", self, blocking)
            return rc
        else:
            # This comes from threading._Condition.wait()

            # Balancing act:  We can't afford a pure busy loop, so we
            # have to sleep; but if we sleep the whole timeout time,
            # we'll be unresponsive.  The scheme here sleeps very
            # little at first, longer as time goes on, but never longer
            # than 20 times per second (or the timeout time remaining).
            endtime = _time() + self.__timeout
            delay = 0.0005 # 500 us -> initial delay of 1 ms
            
#             if wx.Thread_IsMain():
#                 if not self.__block.acquire(0):
#                     _sleep(0.2)
#                     if not self.__block.acquire(0):
#                         print "----Lock acquired by"
#                         print "".join(traceback.format_list(self.__acquiredStackTrace))
#                         print "\n----Lock requested by"
#                         traceback.print_stack()
#                     else:
#                         self.__block.release()
#                 else:
#                     self.__block.release()

            while True:
                gotit = self.__block.acquire(0)
                if gotit:
                    break
                remaining = endtime - _time()
                if remaining <= 0:
                    break
#                 delay = min(delay * 2, remaining, .05)
                delay = min(delay * 2, remaining, .02)
                _sleep(delay)
            if not gotit:
                if __debug__:
                    self._note("%s.wait(%s): timed out", self, self.__timeout)
                
                print "----Lock acquired by"
                print "".join(traceback.format_list(self.__acquiredStackTrace))

                raise DeadBlockPreventionTimeOutError()
            else:
                if __debug__:
                    self._note("%s.wait(%s): got it", self, self.__timeout)
                
                self.__owner = me
                self.__count = 1
                self.__acquiredStackTrace = traceback.extract_stack()
                
                return gotit

    __enter__ = acquire

    def release(self):
        if self.__owner is not threading.currentThread():
            raise RuntimeError("cannot release un-aquired lock")
        self.__count = count = self.__count - 1
        if not count:
            self.__owner = None
            self.__block.release()
            if __debug__:
                self._note("%s.release(): final release", self)
        else:
            if __debug__:
                self._note("%s.release(): non-final release", self)

    def __exit__(self, t, v, tb):
        self.release()

    # Internal methods used by condition variables

    def _acquire_restore(self, (count, owner)):
        self.__block.acquire()
        self.__count = count
        self.__owner = owner
        if __debug__:
            self._note("%s._acquire_restore()", self)

    def _release_save(self):
        if __debug__:
            self._note("%s._release_save()", self)
        count = self.__count
        self.__count = 0
        owner = self.__owner
        self.__owner = None
        self.__block.release()
        return (count, owner)

    def _is_owned(self):
        return self.__owner is threading.currentThread()







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
    
    
    
    
    
