# TODO Weak references!

import weakref, traceback

import wx

class MiscEventSourceMixin:
    """
    Mixin class to handle misc events
    """
    def __init__(self):
        self._MiscEventSourceMixin__miscevent = None


    def getMiscEvent(self):
        if (not hasattr(self, "_MiscEventSourceMixin__miscevent")) or \
                (not self._MiscEventSourceMixin__miscevent):
            self._MiscEventSourceMixin__miscevent = MiscEvent(self)
            
        return self._MiscEventSourceMixin__miscevent


    def removeMiscEvent(self):
        if hasattr(self, "_MiscEventSourceMixin__miscevent"):
            del self._MiscEventSourceMixin__miscevent


    def fireMiscEventProps(self, props, first=None, shareListenerList=False):
        """
        props -- Dictionary {key: value} with properties
        first -- first object to call its miscEventHappened method
                 before other listeners are processed or None
                 
        return:  create clone event
        """
        return self.getMiscEvent().createCloneAddProps(props,
                shareListenerList=shareListenerList).processSend(first)


    def fireMiscEventKeys(self, keys, first=None, shareListenerList=False):
        """
        keys -- Sequence with key strings
        first -- first object to call its miscEventHappened method
                 before other listeners are processed or None

        return:  create clone event
        """
        return self.getMiscEvent().createCloneAddKeys(keys,
                shareListenerList=shareListenerList).processSend(first)



class ListenerList:
    __slots__ = ("__weakref__", "listeners", "userCount", "cleanupFlag",
            "parentList")

    def __init__(self):
        self.listeners = []
        self.userCount = 0
        self.cleanupFlag = False
        self.parentList = None  # Don't know yet what it's good for
        
    def clone(self):
        result = ListenerList()
        result.listeners = self.listeners[:]
        result.userCount = 0
        result.parentList = self
        if self.cleanupFlag:
            result.cleanDeadRefs()

        return result


    def addListener(self, listener, isWeak=True):
        """
        isWeak -- Iff true, store weak reference to listener instead
                of listener itself
        """
        if isWeak:
            self.listeners.append(weakref.ref(listener))
        else:
            self.listeners.append(listener)


    def removeListener(self, listener):
        if self.userCount == 0:
            # No users -> manipulate list directly
            try:
                self.listeners.remove(weakref.ref(listener))
            except ValueError:
                try:
                    self.listeners.remove(listener)
                except ValueError:
                    # Wasn't in the list
                    pass
        else:
            # Invalidate listener
            i = self.findListener(listener)
            if i != -1:
                self.invalidateObjectAt(i)


    def findListener(self, listener):
        try:
            return self.listeners.index(weakref.ref(listener))
        except ValueError:
            try:
                return self.listeners.index(listener)
            except ValueError:
                return -1


    def hasListener(self, listener):
        return self.findListener(listener) != -1
#         try:
#             self.listeners.index(weakref.ref(listener))
#             return True
#         except ValueError:
#             try:
#                 self.listeners.index(listener)
#                 return True
#             except ValueError:
#                 return False


    def setListeners(self, listeners):
        self.listeners = listeners
        
    def incListenerUser(self):
        self.userCount += 1
        return self.listeners
        
    def decListenerUser(self):
        if self.userCount > 0:
            self.userCount -= 1
            
            if self.userCount == 0 and self.cleanupFlag:
                self.cleanDeadRefs()
                self.cleanupFlag = False


    def setCleanupFlag(self, value=True):
        self.cleanupFlag = value


    def getActualObject(lref):
        if lref is None:
            return None

        if isinstance(lref, weakref.ReferenceType):
            return lref()  # Retrieve real object from weakref object
            
        return lref
    getActualObject = staticmethod(getActualObject)


    def getObjectAt(self, i):
        lref = self.listeners[i]
        if lref is None:
            self.cleanupFlag = True
            return None

        if isinstance(lref, weakref.ReferenceType):
            l = lref()
            if l is None:
                self.cleanupFlag = True
                return None
        else:
            l = lref
            
        return l  # Return real
    
    def invalidateObjectAt(self, i):
        """
        Sets listener at index i to None (invalid) and flags list for
        cleaning.
        """
        self.listeners[i] = None
        self.cleanupFlag = True


    def cleanDeadRefs(self):
        """
        Remove references to already deleted objects.
        """
        i = 0
        while i < len(self.listeners):
            if self.getActualObject(self.listeners[i]) is None:
                del self.listeners[i]
                continue # Do not increment i here

            i += 1
            
    def __len__(self):
        return len(self.listeners)

    def __repr__(self):
        return "<MiscEvent.ListenerList " + hex(id(self)) + " " + \
                repr(self.listeners) + ">"



class MiscEvent:
    __slots__ = ("__weakref__", "listenerList", "source", "properties", "parent",
            "activeListenerIndex")

    def __init__(self, source = None):
        self.listenerList = ListenerList()
        self.source = source
        self.properties = None
        self.parent = None
        
        # Index into self.listeners which listener is currently called
        # needed for noChildrenForMe().
        self.activeListenerIndex = -1

    def __repr__(self):
        return "<MiscEvent.MiscEvent(%s, %s, %s)>" % (self.source, self.properties,
                self.listenerList)

    def getSource(self):
        return self.source

    def setSource(self, source):
        self.source = source
        
    def getListenerList(self):
        return self.listenerList
        
    def getMiscEvent(self):
        return self

    def get(self, key, default = None):
        """
        Return value for specified key or default if not found.
        Be careful: The value itself may be None.
        """
        return self.properties.get(key, default)

    def has_key(self, key):
        """
        Has the event the specified key?
        """
        return key in self.properties
        
    __contains__ = has_key

    def has_key_in(self, keyseq):
        """
        Returns true iff it has at least one key in the sequence of keys keyseq
        """
        for key in keyseq:
            if key in self:
                return True
                
        return False

    def getParent(self):
        """
        The MiscEvent which was called to fire this clone. If it returns null this is not a clone.
        """
        return self.parent

    def clone(self, shareListenerList=False):
        """
        Normally you shouldn't call this method directly,
        call createClone() instead
        """
        result = MiscEvent()

        if shareListenerList:
            result.listenerList = self.listenerList
        else:
            result.listenerList = self.listenerList.clone()

        if self.properties is not None:
            result.properties = self.properties.copy()

        return result


    # A MiscEvent manages the listener list itself.

    def addListener(self, listener, isWeak=True):
        """
        isWeak -- Iff true, store weak reference to listener instead
                of listener itself
        """
        return self.listenerList.addListener(listener, isWeak)

    def removeListener(self, listener):
        return self.listenerList.removeListener(listener)
                
    def hasListener(self, listener):
        return self.listenerList.hasListener(listener)

    def setListeners(self, listeners):
        return self.listenerList.setListeners(listeners)

    def setListenerList(self, listenerList):
        self.listenerList = listenerList

    def put(self, key, value = None):
        """
        Add a key-value pair to the internal Hashtable.
        <B>Can't be called on an original MiscEvent, must be a clone.</B>

        @return  this, so you can chain the call: event = event.put("a", a).put("foo", bar);

        @throws NullPointerException       if key is null
        @throws IllegalArgumentException   if this is not a clone
        """
        if self.getParent() is None:
            raise Exception("This must be a clone")  # TODO Create/Find a better exception

        self.properties[key] = value
        return self
        
        
    def cleanDeadRefs(self):
        """
        Remove references to already deleted objects. Mainly called by processSend
        to clean the parent event if a child finds a deadref.
        
        """
##        Automatically calls cleanDeadRefs of its parent event (if existing).
        self.listenerList.cleanDeadRefs()

#         parent = self.getParent()
#         if parent is not None:
#             parent.cleanDeadRefs()


    def processSend(self, first=None):
        """
        Called on the clone to dispatch itself to first, then to all listeners.
        <B>Can't be called on an original MiscEvent, must be a clone.</B>

        @param first   the first listener the event dispatches before dispatching to remaining listeners. A null value is ignored.
        @throws IllegalArgumentException   if this is not a clone
        """
        if self.getParent() is None:
            raise Exception("This must be a clone")  # TODO Create/Find a better exception

        if first is not None:
            first.miscEventHappened(self);
        
        self.listenerList.incListenerUser()
        try:
            i = 0
            while i < len(self.listenerList):
                l = self.listenerList.getObjectAt(i)
                if l is None:
                    i += 1
                    continue
                
                self.activeListenerIndex = i
                try:
                    l.miscEventHappened(self)
                except RuntimeError:
                    # The object is a wxPython object for which the C++ part was
                    # deleted already, so remove object from listener list.
                    self.listenerList.invalidateObjectAt(i)
                except:
                    traceback.print_stack()
                    traceback.print_exc()

                i += 1


        finally:
            self.listenerList.decListenerUser()


        self.activeListenerIndex = -1

        return self
            
            
    def createClone(self, shareListenerList=False):
        """
        Creates a clone with the appropriate data, so dispatching can be done later.<BR>
        Some methods can be called only on a cloned MiscEvent.
        To add properties, use the put() method.

        _source -- The object which will dispatch the event
        """
        event = self.clone(shareListenerList=shareListenerList)
        if event.properties is None:
            event.properties = {}

        event.source = self.source
        event.parent = self

        return event
        
    def getProps(self):
        """
        Return properties dictionary. The returned dictionary should not
        be altered.
        """
        return self.properties


    def addProps(self, addprops):
        """
        Add/update properties of the event

        @param addprops  Dictionary with additional properties
        @return self
        """
        self.properties.update(addprops)
        return self


    def addKeys(self, addkeys):
        """
        Add/update keys of the event

        @param addkeys  Sequence with additional keys for properties
        @return self
        """
        for k in addkeys:
            self.properties[k] = True
        return self
        

    def createCloneAddProps(self, addprops, shareListenerList=False):
        """
        Creates a clone with the appropriate data, so dispatching can be done later.<BR>
        Some methods can be called only on a cloned MiscEvent.

        @param addprops  Dictionary with additional properties
        """
        event = self.createClone(shareListenerList=shareListenerList)
        event.properties.update(addprops)
        return event

    def createCloneAddKeys(self, addkeys, shareListenerList=False):
        """
        Creates a clone with the appropriate data, so dispatching can be done later.<BR>
        Some methods can be called only on a cloned MiscEvent.

        @param addkeys  Sequence with additional keys for properties
        """
        event = self.createClone(shareListenerList=shareListenerList)
        for k in addkeys:
            event.properties[k] = True
        return event


#     def noChildrenForMe():
#         """
#         Called by a listener to ensure that it doesn't get any child events
#         of this event
#         """
#         if self.activeListenerIndex == -1:
#             # TODO Create/Find a better exception
#             raise StandardError("Must be called during processing of an event")
#             
#         self.listeners[self.activeListenerIndex] = None



# TODO Derivation from MiscEvent is not elegant

class ProxyMiscEvent(MiscEvent):
    """
    This specialized MiscEvent registers as listener to a list of other
    MiscEvents and resends any events send by them.
    """
    __slots__ = ("watchedEvents",)

    def __init__(self, source=None):
        MiscEvent.__init__(self, source)
        self.watchedEvents = ()

    def setWatchedSource(self, watchedSource):
        if watchedSource is None:
            self.setWatchedEvent(None)
        else:
            self.setWatchedEvent(watchedSource.getMiscEvent())

    def setWatchedEvent(self, watchedEvent):
        if watchedEvent is None:
            self.setWatchedEvents(())
        else:
            self.setWatchedEvents((watchedEvent,))

    def setWatchedEvents(self, watchedEvents):
        if watchedEvents is None:
            watchedEvents = ()

        for ev in self.watchedEvents:
            ev.removeListener(self)

        self.watchedEvents = watchedEvents

        for ev in self.watchedEvents:
            ev.addListener(self)

    def getWatchedEvents(self):
        return self.watchedEvents

    def miscEventHappened(self, miscevt):
        newMiscevt = miscevt.createClone()
#         newMiscevt.setSource(self)
        newMiscevt.setListenerList(self.listenerList)
        newMiscevt.processSend()



class KeyFunctionSink:
    """
    A MiscEvent sink which dispatches events further to other functions
    """
#     __slots__ = ("__weakref__", "activationTable")
    
    def __init__(self, activationTable):
        """
        activationTable -- Sequence of tuples (<key in props>, <function to call>)
        """
        self.activationTable = activationTable
    
    def miscEventHappened(self, evt):
        for k, f in self.activationTable:
            if k in evt:
                f(evt)


class KeyFunctionSinkAR(KeyFunctionSink):
    """
    Key function sink which automatically adds/removes itself as listener
    to one particular object (Auto Register).
    """
    __slots__= ("eventSource",)
    
    def __init__(self, activationTable, eventSource=None):
        """
        activationTable -- Sequence of tuples (<key in props>, <function to call>)
        eventSource -- object with getMiscEvent() function to listen to (may be None)
        """
        KeyFunctionSink.__init__(self, activationTable)
        
        self.eventSource = eventSource
        
        if self.eventSource is not None:
            self.eventSource.getMiscEvent().addListener(self)

    def getEventSource(self):
        return self.eventSource
        
    def setEventSource(self, eventSource):
        """
        Set the event source (may be None). This automatically removes itself
        as listener from the previous eventSource and registers to the new one
        """
        if self.eventSource is not None:
            self.eventSource.getMiscEvent().removeListener(self)
            
        self.eventSource = eventSource

        if self.eventSource is not None:
            self.eventSource.getMiscEvent().addListener(self)

    def disconnect(self):
        """
        Convenience function for setEventSource(None)
        """
        self.setEventSource(None)



# class EventResenderAR(MiscEventSourceMixin):
#     def __init__(self, eventSource=None):
#         """
#         eventSource -- object with getMiscEvent() function to listen to (may be None)
#         """
#         self.eventSource = eventSource
#         
#         if self.eventSource is not None:
#             self.eventSource.getMiscEvent().addListener(self)
# 
#     def getEventSource(self):
#         return self.eventSource
#         
#     def setEventSource(self, eventSource):
#         """
#         Set the event source (may be None). This automatically removes itself
#         as listener from the previous eventSource and registers to the new one
#         """
#         if self.eventSource is not None:
#             self.eventSource.getMiscEvent().removeListener(self)
#             
#         self.eventSource = eventSource
# 
#         if self.eventSource is not None:
#             self.eventSource.getMiscEvent().addListener(self)
# 
#     def disconnect(self):
#         """
#         Convenience function for setEventSource(None)
#         """
#         self.setEventSource(None)



    




class DebugSimple:
    """
    A MiscEvent sink which dispatches events further to other functions
    """
    __slots__ = ("__weakref__", "text")
    
    def __init__(self, text):
        """
        """
        self.text = text
    
    def miscEventHappened(self, evt):
        print(self.text, repr(evt.properties))


