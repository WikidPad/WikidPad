# TODO Weak references!


class MiscEventSourceMixin:
    """
    Mixin class to handle misc events
    """
    def __init__(self):
        self._EventSource__miscevent = None


    def getMiscEvent(self):
        if (not hasattr(self, "_EventSource__miscevent")) or \
                (not self._EventSource__miscevent):
            self._EventSource__miscevent = MiscEvent(self)
            
        return self._EventSource__miscevent


    def removeMiscEvent(self):
        if hasattr(self, "_EventSource__miscevent"):
            del self._EventSource__miscevent


    def fireMiscEventProps(self, props, first=None):
        """
        props -- Dictionary {key: value} with properties
        first -- first object to call its miscEventHappened method
                 before other listeners are processed or None
                 
        return:  create clone event
        """
        cm = self.getMiscEvent().createCloneAddProps(props)
        cm.processSend(first)
        return cm


    def fireMiscEventKeys(self, keys, first=None):
        """
        keys -- Sequence with key strings
        first -- first object to call its miscEventHappened method
                 before other listeners are processed or None

        return:  create clone event
        """
        cm = self.getMiscEvent().createCloneAddKeys(keys)
        cm.processSend(first)
        return cm



class MiscEvent(object):
    __slots__ = ("__weakref__", "listeners", "source", "properties", "parent")

    def __init__(self, source = None):
        self.listeners = []
        self.source = source
        self.properties = None
        self.parent = None

    def getSource(self):
        return self.source

    def setSource(self, source):
        self.source = source

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
        return self.properties.has_key(key);

    def getParent(self):
        """
        The MiscEvent which was called to fire this clone. If it returns null this is not a clone.
        """
        return self.parent

    def clone(self):
        """
        Normally you shouldn't call this method directly,
        call createClone() instead
        """
        result = MiscEvent()

        result.listeners = self.listeners[:]
        
        if self.properties is not None:
            result.properties = self.properties.clone()

        return result


    # A MiscEvent manages the listener list itself.

    def addListener(self, listener):
        self.listeners.append(listener)

    def removeListener(self, listener):
        try:
            self.listeners.remove(listener)
        except ValueError:
            # Wasn't in the list
            pass


    def put(self, key, value = None):
        """
        Add a key-value pair to the internal Hashtable.
        <B>Can't be called on an original MiscEvent, must be a clone.</B>

        @return  this, so you can chain the call: event = event.put("a", a).put("foo", bar);

        @throws NullPointerException       if key is null
        @throws IllegalArgumentException   if this is not a clone
        """
        if self.getParent() is None:
            raise StandardError("This must be a clone")  # TODO Create/Find a better exception

        self.properties[key] = value
        return self;

    def processSend(self, first = None):
        """
        Called on the clone to dispatch itself to first, then to all listeners.
        <B>Can't be called on an original MiscEvent, must be a clone.</B>

        @param first   the first listener the event dispatches before dispatching to remaining listeners. A null value is ignored.
        @throws IllegalArgumentException   if this is not a clone
        """
        if self.getParent() is None:
            raise StandardError("This must be a clone")  # TODO Create/Find a better exception

        if first is not None:
            first.miscEventHappened(self);

        for l in self.listeners:
            if self.has_key("consumed"): break
            l.miscEventHappened(self)

    def createClone(self):
        """
        Creates a clone with the appropriate data, so dispatching can be done later.<BR>
        Some methods can be called only on a cloned MiscEvent.
        To add properties, use the put() method.

        _source -- The object which will dispatch the event
        """
        event = self.clone()
        if event.properties is None:
            event.properties = {}

        event.source = self.source
        event.parent = self

        return event
        
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
            self.properties[k] = None
        return self
        

    def createCloneAddProps(self, addprops):
        """
        Creates a clone with the appropriate data, so dispatching can be done later.<BR>
        Some methods can be called only on a cloned MiscEvent.

        @param addprops  Dictionary with additional properties
        """
        event = self.createClone()
        event.properties.update(addprops)
        return event

    def createCloneAddKeys(self, addkeys):
        """
        Creates a clone with the appropriate data, so dispatching can be done later.<BR>
        Some methods can be called only on a cloned MiscEvent.

        @param addkeys  Sequence with additional keys for properties
        """
        event = self.createClone()
        for k in addkeys:
            event.properties[k] = None
        return event


class KeyFunctionSink(object):
    """
    A MiscEvent sink which dispatches events further to other functions
    """
    __slots__ = ("__weakref__", "activationTable")
    
    def __init__(self, activationTable):
        """
        activationTable -- Sequence of tuples (<key in props>, <function to call>)
        """
        self.activationTable = activationTable
    
    def miscEventHappened(self, evt):
        for k, f in self.activationTable:
            if evt.has_key(k):
                f(evt)
                
        
    
