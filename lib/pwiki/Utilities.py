from __future__ import with_statement

import threading, traceback, collections, heapq
from thread import allocate_lock as _allocate_lock
from time import time as _time, sleep as _sleep

import wx

from Consts import DEADBLOCKTIMEOUT
from .WikiExceptions import NotCurrentThreadException, \
        DeadBlockPreventionTimeOutError, InternalError

from . import MiscEvent


class Dummy(object):
    pass


# ---------- Thread handling and task execution ----------

class BasicThreadStop(object):
    """
    An object of this or a derived class is handed over to long running
    operations which might run in a separate thread and maybe must be stopped
    for some reason (e.g. a parsing operation should be stopped if the
    parsed text was changed and the operation on the old text therefore becomes
    useless).
    During the operation the function isValidThread() or testValidThread() should be
    called from time to time to check if op. should be stopped.

    This class is used for synchronous operations where no thread stop
    condition is necessary.
    """
    __slots__ = ()

    def isValidThread(self):
        """
        Returns True if operation should continue.
        """
        return True

    def testValidThread(self):
        """
        Throws a NotCurrentThreadException if op. should stop, does nothing
        otherwise.
        """
        pass


DUMBTHREADSTOP = BasicThreadStop()


class FunctionThreadStop(BasicThreadStop):
    __slots__ = ("fct",)

    def __init__(self, fct):
        self.fct = fct

    def isValidThread(self):
        return self.fct()
        
    def testValidThread(self):
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
        
    def testValidThread(self):
        """
        Throws NotCurrentThreadException if self.thread is not equal to
        current thread
        """
        if threading.currentThread() is not self.thread:
            raise NotCurrentThreadException()

    def isValidThread(self):
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
        with self.dequeCondition:
            self.paused = False
            if self.thread is not None and self.thread.isAlive():
                return

            self.prepare()

            self.thread = threading.Thread(target=self._runQueue)
            self.thread.setDaemon(self.daemon)
            self.thread.start()
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
            running = self.thread is not None and self.thread.isAlive()

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

                except Exception, e:
                    traceback.print_exc() # ?
                    retObj.setException(e)

#                 tracer.runctx('retObj.result = fct(*args, **kwargs)', globals(), locals())
                if tstop:
                    kwargs["threadstop"] = self

            try:
                retObj.setResult(fct(*args, **kwargs))
                self.incDoneJobCount()

            except Exception, e:
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
        Returns result from fct(...) or throws execption thrown by fct()
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
        if self.thread is None or not self.thread.isAlive():
            return

        with self.dequeCondition:
            if hardEnd:
                self.deques = None
            else:
                self.deques[-1].appendleft(
                        (SingleThreadExecutor.ENDOBJECT, None, None, None, None,
                        False))
            self.dequeCondition.notify()

        self.thread.join(120)  # TODO: Replace by constant

        if self.thread.isAlive():
            raise DeadBlockPreventionTimeOutError()

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
            
            if thread is None or not thread.isAlive():
                return False

            self.paused = True
            self.dequeCondition.notify()
            
        if wait:
            thread.join(120)  # TODO: Replace by constant
    
            if thread.isAlive():
                raise DeadBlockPreventionTimeOutError()

            self.thread = None

        return True



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
#         self.__acquiredStackTrace = None

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
#                 self.__acquiredStackTrace = traceback.extract_stack()
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
                
#                 print "----Lock acquired by"
#                 print "".join(traceback.format_list(self.__acquiredStackTrace))

                raise DeadBlockPreventionTimeOutError()
            else:
                if __debug__:
                    self._note("%s.wait(%s): got it", self, self.__timeout)
                
                self.__owner = me
                self.__count = 1
#                 self.__acquiredStackTrace = traceback.extract_stack()
                
                return gotit

    __enter__ = acquire

    def release(self):
        if self.__owner is not threading.currentThread():
            raise RuntimeError("cannot release un-aquired lock")
        self.__count = count = self.__count - 1
        if not count:
            self.__owner = None
#             self.__acquiredStackTrace = None
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


class DictFromFields(object):
    """
    Helper to create dictionary. Create an object from it, set fields on it
    and retrieve all fields which do not start with double underscore.
    """
    def getDict(self):
        return dict(((k, v) for k, v in self.__dict__.iteritems()
                if not k.startswith("__")))




# collections.Counter class from Python 2.7 standard library
class Counter(dict):
    '''Dict subclass for counting hashable items.  Sometimes called a bag
    or multiset.  Elements are stored as dictionary keys and their counts
    are stored as dictionary values.

    >>> c = Counter('abcdeabcdabcaba')  # count elements from a string

    >>> c.most_common(3)                # three most common elements
    [('a', 5), ('b', 4), ('c', 3)]
    >>> sorted(c)                       # list all unique elements
    ['a', 'b', 'c', 'd', 'e']
    >>> ''.join(sorted(c.elements()))   # list elements with repetitions
    'aaaaabbbbcccdde'
    >>> sum(c.values())                 # total of all counts
    15

    >>> c['a']                          # count of letter 'a'
    5
    >>> for elem in 'shazam':           # update counts from an iterable
    ...     c[elem] += 1                # by adding 1 to each element's count
    >>> c['a']                          # now there are seven 'a'
    7
    >>> del c['b']                      # remove all 'b'
    >>> c['b']                          # now there are zero 'b'
    0

    >>> d = Counter('simsalabim')       # make another counter
    >>> c.update(d)                     # add in the second counter
    >>> c['a']                          # now there are nine 'a'
    9

    >>> c.clear()                       # empty the counter
    >>> c
    Counter()

    Note:  If a count is set to zero or reduced to zero, it will remain
    in the counter until the entry is deleted or the counter is cleared:

    >>> c = Counter('aaabbc')
    >>> c['b'] -= 2                     # reduce the count of 'b' by two
    >>> c.most_common()                 # 'b' is still in, but its count is zero
    [('a', 3), ('c', 1), ('b', 0)]

    '''
    # References:
    #   http://en.wikipedia.org/wiki/Multiset
    #   http://www.gnu.org/software/smalltalk/manual-base/html_node/Bag.html
    #   http://www.demo2s.com/Tutorial/Cpp/0380__set-multiset/Catalog0380__set-multiset.htm
    #   http://code.activestate.com/recipes/259174/
    #   Knuth, TAOCP Vol. II section 4.6.3

    def __init__(*args, **kwds):
        '''Create a new, empty Counter object.  And if given, count elements
        from an input iterable.  Or, initialize the count from another mapping
        of elements to their counts.

        >>> c = Counter()                           # a new, empty counter
        >>> c = Counter('gallahad')                 # a new counter from an iterable
        >>> c = Counter({'a': 4, 'b': 2})           # a new counter from a mapping
        >>> c = Counter(a=4, b=2)                   # a new counter from keyword args

        '''
        if not args:
            raise TypeError("descriptor '__init__' of 'Counter' object "
                            "needs an argument")
        self = args[0]
        args = args[1:]
        if len(args) > 1:
            raise TypeError('expected at most 1 arguments, got %d' % len(args))
        super(Counter, self).__init__()
        self.update(*args, **kwds)

    def __missing__(self, key):
        'The count of elements not in the Counter is zero.'
        # Needed so that self[missing_item] does not raise KeyError
        return 0

    def most_common(self, n=None):
        '''List the n most common elements and their counts from the most
        common to the least.  If n is None, then list all element counts.

        >>> Counter('abcdeabcdabcaba').most_common(3)
        [('a', 5), ('b', 4), ('c', 3)]

        '''
        # Emulate Bag.sortedByCount from Smalltalk
        if n is None:
            return sorted(self.iteritems(), key=_itemgetter(1), reverse=True)
        return _heapq.nlargest(n, self.iteritems(), key=_itemgetter(1))

    def elements(self):
        '''Iterator over elements repeating each as many times as its count.

        >>> c = Counter('ABCABC')
        >>> sorted(c.elements())
        ['A', 'A', 'B', 'B', 'C', 'C']

        # Knuth's example for prime factors of 1836:  2**2 * 3**3 * 17**1
        >>> prime_factors = Counter({2: 2, 3: 3, 17: 1})
        >>> product = 1
        >>> for factor in prime_factors.elements():     # loop over factors
        ...     product *= factor                       # and multiply them
        >>> product
        1836

        Note, if an element's count has been set to zero or is a negative
        number, elements() will ignore it.

        '''
        # Emulate Bag.do from Smalltalk and Multiset.begin from C++.
        return _chain.from_iterable(_starmap(_repeat, self.iteritems()))

    # Override dict methods where necessary

    @classmethod
    def fromkeys(cls, iterable, v=None):
        # There is no equivalent method for counters because setting v=1
        # means that no element can have a count greater than one.
        raise NotImplementedError(
            'Counter.fromkeys() is undefined.  Use Counter(iterable) instead.')

    def update(*args, **kwds):
        '''Like dict.update() but add counts instead of replacing them.

        Source can be an iterable, a dictionary, or another Counter instance.

        >>> c = Counter('which')
        >>> c.update('witch')           # add elements from another iterable
        >>> d = Counter('watch')
        >>> c.update(d)                 # add elements from another counter
        >>> c['h']                      # four 'h' in which, witch, and watch
        4

        '''
        # The regular dict.update() operation makes no sense here because the
        # replace behavior results in the some of original untouched counts
        # being mixed-in with all of the other counts for a mismash that
        # doesn't have a straight-forward interpretation in most counting
        # contexts.  Instead, we implement straight-addition.  Both the inputs
        # and outputs are allowed to contain zero and negative counts.

        if not args:
            raise TypeError("descriptor 'update' of 'Counter' object "
                            "needs an argument")
        self = args[0]
        args = args[1:]
        if len(args) > 1:
            raise TypeError('expected at most 1 arguments, got %d' % len(args))
        iterable = args[0] if args else None
        if iterable is not None:
            if isinstance(iterable, Mapping):
                if self:
                    self_get = self.get
                    for elem, count in iterable.iteritems():
                        self[elem] = self_get(elem, 0) + count
                else:
                    super(Counter, self).update(iterable) # fast path when counter is empty
            else:
                self_get = self.get
                for elem in iterable:
                    self[elem] = self_get(elem, 0) + 1
        if kwds:
            self.update(kwds)

    def subtract(*args, **kwds):
        '''Like dict.update() but subtracts counts instead of replacing them.
        Counts can be reduced below zero.  Both the inputs and outputs are
        allowed to contain zero and negative counts.

        Source can be an iterable, a dictionary, or another Counter instance.

        >>> c = Counter('which')
        >>> c.subtract('witch')             # subtract elements from another iterable
        >>> c.subtract(Counter('watch'))    # subtract elements from another counter
        >>> c['h']                          # 2 in which, minus 1 in witch, minus 1 in watch
        0
        >>> c['w']                          # 1 in which, minus 1 in witch, minus 1 in watch
        -1

        '''
        if not args:
            raise TypeError("descriptor 'subtract' of 'Counter' object "
                            "needs an argument")
        self = args[0]
        args = args[1:]
        if len(args) > 1:
            raise TypeError('expected at most 1 arguments, got %d' % len(args))
        iterable = args[0] if args else None
        if iterable is not None:
            self_get = self.get
            if isinstance(iterable, Mapping):
                for elem, count in iterable.items():
                    self[elem] = self_get(elem, 0) - count
            else:
                for elem in iterable:
                    self[elem] = self_get(elem, 0) - 1
        if kwds:
            self.subtract(kwds)

    def copy(self):
        'Return a shallow copy.'
        return self.__class__(self)

    def __reduce__(self):
        return self.__class__, (dict(self),)

    def __delitem__(self, elem):
        'Like dict.__delitem__() but does not raise KeyError for missing values.'
        if elem in self:
            super(Counter, self).__delitem__(elem)

    def __repr__(self):
        if not self:
            return '%s()' % self.__class__.__name__
        items = ', '.join(map('%r: %r'.__mod__, self.most_common()))
        return '%s({%s})' % (self.__class__.__name__, items)

    # Multiset-style mathematical operations discussed in:
    #       Knuth TAOCP Volume II section 4.6.3 exercise 19
    #       and at http://en.wikipedia.org/wiki/Multiset
    #
    # Outputs guaranteed to only include positive counts.
    #
    # To strip negative and zero counts, add-in an empty counter:
    #       c += Counter()

    def __add__(self, other):
        '''Add counts from two counters.

        >>> Counter('abbb') + Counter('bcc')
        Counter({'b': 4, 'c': 2, 'a': 1})

        '''
        if not isinstance(other, Counter):
            return NotImplemented
        result = Counter()
        for elem, count in self.items():
            newcount = count + other[elem]
            if newcount > 0:
                result[elem] = newcount
        for elem, count in other.items():
            if elem not in self and count > 0:
                result[elem] = count
        return result

    def __sub__(self, other):
        ''' Subtract count, but keep only results with positive counts.

        >>> Counter('abbbc') - Counter('bccd')
        Counter({'b': 2, 'a': 1})

        '''
        if not isinstance(other, Counter):
            return NotImplemented
        result = Counter()
        for elem, count in self.items():
            newcount = count - other[elem]
            if newcount > 0:
                result[elem] = newcount
        for elem, count in other.items():
            if elem not in self and count < 0:
                result[elem] = 0 - count
        return result

    def __or__(self, other):
        '''Union is the maximum of value in either of the input counters.

        >>> Counter('abbb') | Counter('bcc')
        Counter({'b': 3, 'c': 2, 'a': 1})

        '''
        if not isinstance(other, Counter):
            return NotImplemented
        result = Counter()
        for elem, count in self.items():
            other_count = other[elem]
            newcount = other_count if count < other_count else count
            if newcount > 0:
                result[elem] = newcount
        for elem, count in other.items():
            if elem not in self and count > 0:
                result[elem] = count
        return result

    def __and__(self, other):
        ''' Intersection is the minimum of corresponding counts.

        >>> Counter('abbb') & Counter('bcc')
        Counter({'b': 1})

        '''
        if not isinstance(other, Counter):
            return NotImplemented
        result = Counter()
        for elem, count in self.items():
            other_count = other[elem]
            newcount = count if count < other_count else other_count
            if newcount > 0:
                result[elem] = newcount
        return result



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
            item = itr.next()
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
                item = itr.next()
                heapq.heapreplace(heap, (key(item), idx, item, itr) )
            except StopIteration:
                heapq.heappop(heap)

    else:
        while heap:
            item, idx, itr = heap[0]
            yield item  # , itr
            try:
                heapq.heapreplace(heap, (itr.next(), idx, itr))
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



