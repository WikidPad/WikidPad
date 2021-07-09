

import sys, threading, traceback, collections, heapq, functools, logging
# from _thread import allocate_lock as _allocate_lock
from time import time as _time, sleep as _sleep

import wx

from Consts import DEADBLOCKTIMEOUT
from .WikiExceptions import NotCurrentThreadException, \
        DeadBlockPreventionTimeOutError, InternalError

from . import MiscEvent


# ---------- Thread handling and task execution ----------

class BasicThreadStop:
    """
    An object of this or a derived class is handed over to long running
    operations which might run in a separate thread and maybe must be stopped
    for some reason (e.g. a parsing operation should be stopped if the
    parsed text was changed and the operation on the old text therefore becomes
    useless).
    During the operation the function isValidThread() or testValidThread() should be
    called from time to time to check if op. should be stopped.

    This class itself is used for synchronous operations where no thread stop
    condition is necessary.
    """
    __slots__ = ()

    def isValidThread(self):
        """
        Returns True if operation should continue (calling thread is the
        desired thread which should perform the operation).
        """
        return True

    def testValidThread(self):
        """
        Throws a NotCurrentThreadException if operation should stop, does nothing
        otherwise. Convenience variant of isValidThread()
        """
        if not self.isValidThread():
            raise NotCurrentThreadException()


DUMBTHREADSTOP = BasicThreadStop()


class FunctionThreadStop(BasicThreadStop):
    __slots__ = ("fct",)

    def __init__(self, fct):
        self.fct = fct

    def isValidThread(self):
        return self.fct()



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
        
    def isValidThread(self):
        """
        Return True if current thread is thread in holder
        """
        return threading.currentThread() is self.thread




class ExecutionResult:
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




class SingleThreadExecutor(BasicThreadStop, MiscEvent.MiscEventSourceMixin):
    def __init__(self, dequeCount=1, daemon=False):
        MiscEvent.MiscEventSourceMixin.__init__(self)

        self.dequeCondition = threading.Condition()
        self.daemon = daemon
        self.dequeCount = dequeCount

        self.deques = None
        self.thread = None
        self.paused = False
        self.currentThreadStop = None
        
        self.doneJobCount = 0
        self.incDoneJobCount = self._inactiveIncDoneJobCount

    def isValidThread(self):
        return self.deques is not None
        
    def testValidThread(self):
        if self.deques is None:
            raise NotCurrentThreadException()

    def prepare(self):
        with self.dequeCondition:
            if self.deques is None:
                self.deques = tuple(collections.deque()
                        for i in range(self.dequeCount))

    def start(self):
        debuglog("SingleThreadExecutor starting")
        with self.dequeCondition:
            self.paused = False
            if self.thread is not None and self.thread.is_alive():
                return

            self.prepare()

            self.thread = threading.Thread(target=self._runQueue)
            self.thread.setDaemon(self.daemon)
            self.thread.start()
            debuglog("SingleThreadExecutor thread created",
                    self.thread, self.daemon)
            self._fireStateChange(True)


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
    PAUSEOBJECT = object()

    def _getNextJob(self):
        if self.paused:
            return (SingleThreadExecutor.PAUSEOBJECT, None, None, None, None,
                        False)

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


    def _activeIncDoneJobCount(self):
        self.doneJobCount += 1
    
    def _inactiveIncDoneJobCount(self):
        pass
    
    def resetDoneJobCount(self):
        self.doneJobCount = 0

    def getDoneJobCount(self):
        return self.doneJobCount
        
    def startDoneJobCount(self):
        self.incDoneJobCount = self._activeIncDoneJobCount

    def stopDoneJobCount(self):
        self.incDoneJobCount = self._inactiveIncDoneJobCount
        

    def _fireStateChange(self, running=None):
        if running is None:
            # Detect self
            running = self.thread is not None and self.thread.is_alive()

        callInMainThreadAsync(self.fireMiscEventProps, {"changed state": True,
            "isRunning": running, "jobCount": self.getJobCount()})

    def _runQueue(self):
        while True:
            with self.dequeCondition:

                while self.deques is not None:
                    job = self._getNextJob()
                    if job is not None:
                        break
                    self._fireStateChange(True)
                    self.dequeCondition.wait()
                    self._fireStateChange(True)

                if self.deques is None:
                    # Executor terminated
                    self._fireStateChange(False)
                    return

                fct, args, kwargs, event, retObj, tstop = job

                try:
                    if fct is SingleThreadExecutor.ENDOBJECT:
                        # We should stop here, but the problem is that other
                        # operations may itself push new jobs back on the deque
                        # which must be processed before thread can end
                        if self.getJobCount() == 0:
                            self._fireStateChange(False)
                            return

                        self.deques[-1].appendleft(
                                (SingleThreadExecutor.ENDOBJECT, None, None,
                                None, None))
                        continue
                    elif fct is SingleThreadExecutor.PAUSEOBJECT:
                        # Operation should pause, this means to kill the thread, but
                        # to keep the deques as they are.
                        # To resume, start() is called
                        self._fireStateChange(False)
                        return

                except Exception as e:
                    traceback.print_exc() # ?
                    retObj.setException(e)

#                 tracer.runctx('retObj.result = fct(*args, **kwargs)', globals(), locals())
                if tstop:
                    kwargs["threadstop"] = self

            try:
                retObj.setResult(fct(*args, **kwargs))
                self.incDoneJobCount()

            except Exception as e:
                traceback.print_exc() # ?
                retObj.setException(e)
            finally:
                if event is not None:
                    event.set()


    def execute(self, idx, fct, *args, **kwargs):
        """
        Execute fct(*args, **kwargs) in the thread of the executor in queue idx
        and wait until it is finished.
        If the execution needs longer than 4 minutes,
        a DeadBlockPreventionTimeOutError is raised.
        Returns result from fct(...) or throws exception thrown by fct()
        """
        if threading.currentThread() is self.thread:
            return fct(*args, **kwargs)
            
        if self.deques is None:
            raise InternalError("Called SingleThreadExecutor.execute() after "
                    "queue was killed")

        event = threading.Event()
        retObj = ExecutionResult()

        with self.dequeCondition:
            self.deques[idx].appendleft((fct, args, kwargs, event, retObj, None))
            self.dequeCondition.notify()

        event.wait(240)  # TODO: Replace by constant

        if not event.isSet():
            raise DeadBlockPreventionTimeOutError()
        if retObj.exception is not None:
            raise retObj.exception

        return retObj.result


    def executeAsync(self, idx, fct, *args, **kwargs):
        """
        Execute fct(*args, **kwargs) in the thread of the executor in queue idx.
        Call may return before execution is done (asychronous).
        Returns an ExecutionResult object which can be checked if
        fct was executed already and which result it returned or exception
        it threw.
        """
        retObj = ExecutionResult()

        if self.deques is None:
            return retObj  # Error?

        with self.dequeCondition:
            self.deques[idx].appendleft((fct, args, kwargs, None, retObj, False))
            self.dequeCondition.notify()

        return retObj


    def executeAsyncWithThreadStop(self, idx, fct, *args, **kwargs):
        retObj = ExecutionResult()

        if self.deques is None:
            return retObj  # Error?

        with self.dequeCondition:
            self.deques[idx].appendleft((fct, args, kwargs, None, retObj, True))
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

        If the queues are empty, executor stops in each case.
        """
        if self.thread is None or not self.thread.is_alive():
            return

        with self.dequeCondition:
            if hardEnd:
                self.deques = None
            else:
                self.deques[-1].appendleft(
                        (SingleThreadExecutor.ENDOBJECT, None, None, None, None,
                        False))
            self.dequeCondition.notify()

        debuglog("SingleThreadExecutor ending, joining thread",
                self.thread, self.daemon)

        self.thread.join(120)  # TODO: Replace by constant

        if self.thread.is_alive():
            raise DeadBlockPreventionTimeOutError()

        debuglog("SingleThreadExecutor ending, thread terminated",
                thread=self.thread, daemon=self.daemon)

        self.thread = None


    def pause(self, wait=False):
        """
        Stops after current job but keeps the queue so that it can resume
        later by call to start(). Returns True if executor thread wasn't
        terminated already.
        If  wait  is True the function returns after the current job was
        done and the executor is in pause mode
        """
        with self.dequeCondition:
            thread = self.thread
            
            if thread is None or not thread.is_alive():
                return False

            self.paused = True
            self.dequeCondition.notify()
            
        if wait:
            thread.join(120)  # TODO: Replace by constant
    
            if thread.is_alive():
                raise DeadBlockPreventionTimeOutError()

            self.thread = None

        return True



def callInMainThread(fct, *args, **kwargs):
    if wx.IsMainThread() or not wx.GetApp().IsMainLoopRunning():
        return fct(*args, **kwargs)
    
    returnOb = ExecutionResult()
    event = threading.Event()


    def _mainRun(*args, **kwargs):
        try:
            returnOb.result = fct(*args, **kwargs)
        except Exception as e:
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


def mainThreadFunc(fct):
    """
    Decorator to ensure that function only runs in main thread.
    Do not use for unbound methods!
    """
    result = functools.partial(callInMainThread, fct)
    functools.update_wrapper(result, fct)

    return result


def callInMainThreadAsync(fct, *args, **kwargs):
    if wx.IsMainThread() or not wx.GetApp().IsMainLoopRunning():
        return fct(*args, **kwargs)
    def _mainRun(*args, **kwargs):
        try:
            fct(*args, **kwargs)
        except Exception as e:
            traceback.print_exc()

    wx.CallAfter(_mainRun, *args, **kwargs)




class TimeoutRLock:
    """
    Wrapper class for threading.RLock where the timeout is given in constructor
    in addition to acquire(). This is especially helpful when using context protocol.
    
    """
    def __init__(self, timeout=-1):
        self.realLock = threading.RLock()
        self.timeout = timeout if timeout is not None else -1
        
    def __repr__(self):
        return "<%s(timeout=%s, %s)>" % (self.__class__.__name__, self.timeout,
                repr(self.realLock))
    
    def acquire(self, blocking=True, timeout=None):
        """
        Slightly different behavior as RLock.acquire(): If no timeout is
        given in acquire() call (or timeout is None) and the timeout
        given in constructor runs out, a DeadBlockPreventionTimeOutError
        is raised.
        """
        
        if not blocking:
            return self.realLock.acquire(False)
        else:
            if timeout is None:
                timeout = self.timeout
                
                if self.realLock.acquire(True, timeout=timeout):
                    return True
                else:
                    raise DeadBlockPreventionTimeOutError()
            else:
                return self.realLock.acquire(True, timeout=timeout)


    __enter__ = acquire
    
    def release(self):
        self.realLock.release()
    

    def __exit__(self, t, v, tb):
        self.release()





# ---------- Data structures ----------

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



def seqEnforceContained(seq, allowedSeq):
    """
    Returns a list with those items of seq which are in allowedSeq
    plus (appended) items which are in allowedSeq but missing in seq.
    
    >>> seqEnforceContained([1,2,5],[1,2,3,4,5])
    [1, 2, 5, 3, 4]
    >>> seqEnforceContained([1,2,4,3,7,5],[1,2,3,4,5])
    [1, 2, 4, 3, 5]
    >>> seqEnforceContained([1,2,7,5],[1,2,3,4,5])
    [1, 2, 5, 3, 4]
    """
    
    aSeq = list(allowedSeq)
    result = []
    for item in seq:
        try:
            pos = aSeq.index(item)
            result.append(item)
            del aSeq[pos]
        except ValueError:
            pass
    
    result.extend(aSeq)
    
    return result



def seqSupportWithTemplate(tupleOrList, templateSeq):
    """
    If tupleOrList has same length as templateSeq
    (must support index access protocol), tupleOrList is returned.
    If tupleOrList is longer, only the first len(templateSeq) items are returned.
    
    If tupleOrList (which should be tuple, list or derived from it) is shorter
    than templateSeq then a new list or tuple (depending on tupleOrList's type)
    is returned with same length as templateSeq where the missing items were
    taken from the appropriate places in templateSeq
    
    >>> seqSupportWithTemplate([7, 8, 9], [1, 2, 3, 4, 5])
    [7, 8, 9, 4, 5]
    >>> seqSupportWithTemplate((7, 8, 9), [1, 2, 3, 4, 5])
    (7, 8, 9, 4, 5)
    >>> seqSupportWithTemplate((7, 8, 9, 10, 11, 12), [1, 2, 3, 4, 5])
    (7, 8, 9, 10, 11)
    >>> seqSupportWithTemplate([7, 8, 9, 10, 11], [1, 2, 3, 4, 5])
    [7, 8, 9, 10, 11]
    """
    n = len(tupleOrList)
    
    if n > len(templateSeq):
        return tupleOrList[:len(templateSeq)]

    if n == len(templateSeq):
        return tupleOrList
    
    return tupleOrList + type(tupleOrList)(templateSeq[n:])





# class FlagHolder:
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



class DefaultDictParam(dict):
    """
    Similar to collections.defaultdict, but gives key as argument to
    defaultFactory to create key-dependent value
    """
    def __init__(self, defaultFactory):
        self.defaultFactory = defaultFactory

    def __missing__(self, key):
        val = self.defaultFactory(key)
        self[key] = val
        return val


class DictFromFields:
    """
    Helper to create dictionary. Create an object from it, set fields on it
    and retrieve all fields which do not start with double underscore.
    """
    def getDict(self):
        return dict(((k, v) for k, v in self.__dict__.items()
                if not k.startswith("__")))



def iterMergesort(list_of_lists, key=None):
    # Based on http://code.activestate.com/recipes/511509-n-way-merge-sort/
    # from Mike Klaas
    """ Perform an N-way merge operation on sorted lists.

    @param list_of_lists: (really iterable of iterable) of sorted elements
    (either by naturally or by C{key})
    @param key: specify sort key function (like C{sort()}, C{sorted()})
    @param iterfun: function that returns an iterator.

    Yields tuples of the form C{(item, iterator)}, where the iterator is the
    built-in list iterator or something you pass in, if you pre-generate the
    iterators.

    This is a stable merge; complexity O(N lg N)

    Examples::

    print list(x[0] for x in mergesort([[1,2,3,4],
                                        [2,3.5,3.7,4.5,6,7],
                                        [2.6,3.6,6.6,9]]))
    [1, 2, 2, 2.6, 3, 3.5, 3.6, 3.7, 4, 4.5, 6, 6.6, 7, 9]

    # note stability
    print list(x[0] for x in mergesort([[1,2,3,4],
                                        [2,3.5,3.7,4.5,6,7],
                                        [2.6,3.6,6.6,9]], key=int))
    [1, 2, 2, 2.6, 3, 3.5, 3.7, 3.6, 4, 4.5, 6, 6.6, 7, 9]

    print list(x[0] for x in mergesort([[4,3,2,1],
                                        [7,6.5,4,3.7,3.3,1.9],
                                        [9,8.6,7.6,6.6,5.5,4.4,3.3]],
                                        key=lambda x: -x))
    [9, 8.6, 7.6, 7, 6.6, 6.5, 5.5, 4.4, 4, 4, 3.7, 3.3, 3.3, 3, 2, 1.9, 1]


    """

    heap = []
    for i, itr in enumerate(iter(pl) for pl in list_of_lists):
        try:
            item = next(itr)
            toadd = (key(item), i, item, itr) if key else (item, i, itr)
            heap.append(toadd)
        except StopIteration:
            pass
    heapq.heapify(heap)

    if key:
        while heap:
            _, idx, item, itr = heap[0]
            yield item  # , itr
            try:
                item = next(itr)
                heapq.heapreplace(heap, (key(item), idx, item, itr) )
            except StopIteration:
                heapq.heappop(heap)

    else:
        while heap:
            item, idx, itr = heap[0]
            yield item  # , itr
            try:
                heapq.heapreplace(heap, (next(itr), idx, itr))
            except StopIteration:
                heapq.heappop(heap)


class IdentityList(list):
    """
    A list where the "in" operator and index method check for identity
    instead of equality.
    """
    def __contains__(self, item):
        for i in self:
            if i is item:
                return True
        return False

    def index(self, elem):
        for i, item in enumerate(self):
            if elem is item:
                return i

        raise ValueError()

    def find(self, elem):
        for i, item in enumerate(self):
            if elem is item:
                return i

        return -1
        
    def remove(self, elem):
        del self[self.index(elem)]

    def drop(self, elem):
        """
        Same as remove() but fails silently if elem not found
        """
        idx = self.find(elem)
        if idx == -1:
            return

        del self[idx]
        
    def clear(self):
        del self[0:len(self)]



class AttrContainer:
    """
    Attribute container. Same objects can be retrieved by attribute or
    item syntax (similar to JavaScript objects)
    """
    def __getitem__(self, key):
        return self.__dict__[key]

    def __setitem__(self, key, value):
        self.__dict__[key] = value
        
    def __delitem__(self, key):
        del self.__dict__[key]



# ---------- Debug Logging ----------


if False:
    logging.basicConfig(level=logging.DEBUG, stream=sys.stderr)
    
    def debuglog(msg, *args, **kwargs):
        msg = msg + ", ".join(repr(arg) for arg in args) + "; " + \
                ", ".join(k + "=" + repr(v) for k, v in kwargs.items())
        
        logging.debug(msg)

else:

    def debuglog(msg, *args, **kwargs):
        pass




# ---------- Misc ----------



def sgn(value):
    """
    Signum function
    """
    if value < 0:
        return -1
    if value > 0:
        return 1
    
    return 0
    
    
def between(lower, value, upper):
    """
    Return number that is nearest to value and is between lower and upper
    (including)
    """
    return max(lower, min(value, upper))


def calcResizeArIntoBoundingBox(width, height, bbWidth, bbHeight, upright=False):
    """
    For an image with dimensions  width  and  height, calculate new dimension
    which optimally fill bounding box given by  bbWidth  and  bbHeight  so that
    aspect ratio (AR) is not changed.
    If  upright  is True the bounding box dimensions can be switched to create
    a larger resized image (typically if box has landscape format while
    image is portray format aka upright).

    Returns tuple (newWidth, newHeight).
    """
    assert bbWidth > 0 and bbHeight > 0, "Invalid bounding box values"
    assert width > 0 and height > 0, "Invalid image size values"
    
    
    if ( upright and
            # if bounding box or image is quadratic there is nothing to do
            (bbWidth != bbHeight) and (width != height) and 
            # check for different formats
            (sgn(bbWidth - bbHeight) != sgn(width - height)) ):

        bbWidth, bbHeight = bbHeight, bbWidth
    
    # Mathematically equal to bbWidth / width < bbHeight / height
    # but without floating point arithmetic
    if bbWidth * height < bbHeight * width:
        # Scaling factor is (bbWidth / width)
        newWidth = bbWidth
        newHeight = (height * bbWidth) // width
    else:
        # Scaling factor is (bbHeight / height)
        newWidth = (width * bbHeight) // height
        newHeight = bbHeight

    return (newWidth, newHeight)



