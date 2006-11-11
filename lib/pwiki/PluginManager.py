import os, sys, traceback, sets

from wxPython.wx import *


from StringOps import mbcsEnc

"""The PluginManager and PluginAPI classes implement a generic plugin framework.
   Plugin apis are created by the PluginManager and can be used to call all
   installed plugins for that api at once. The PluginManager loads plugins from
   specified directories and manages them. 
   
   Example code:
   
   pm = PluginManager()
   api = pm.registerPluginAPI(("myAPI",1), ["init", "call1", "call2", "exit"])
   pm.loadPlugins(["dir1, "dir2"], ["notloadme", "andnotme"])
   api.init("hello")
   api.exit()
   
   Plugin modules must expose the member WIKIDPAD_PLUGIN to be valid plugins. 
   Otherwise the PluginManager will not register them. Moreover WIKIDPAD_PLUGIN 
   must be a sequence container type that contains the descriptors for the apis
   it implements. For example in the above case a valid module would have the 
   following member:
   
   WIKIDPAD_PLUGIN = (("myAPI",1),)
   
   or
   
   WIKIDPAD_PLUGIN = [("myAPI",1)]
   
   then it defines all functions of the api it supports
   
   def init():
       pass
   
   def call1():
       pass
       
   ...
   
   Descriptors are searched for with 'in' so any non-mutable instance should work.
   
   Plugin functions also can return values. The api wrapper object will collect 
   all return values and return a list of these. If you know that there will be
   only one return value, you can unpack it directly to a variable with the 
   following syntax:
   a, = api.call1()
   """
        
class PluginAPI(object):
    """encapsulates a single plugin api and stores the functions of various
       plugins implementing that api. It takes a unique descriptor and a list
       of function names at creation time. For each function name a member is
       created that calls the registered plugin functions. The descriptor must 
       appear in the WIKIDPAD_PLUGIN sequence object of the any module to have
       the module registered. After that the module just has to implement a 
       subset of the api's functions to be registered."""

    def __init__(self, descriptor, functions):
        self.descriptor = descriptor
        self.__functionNames = functions
        self.__plugins = {}
        for f in functions:
            pluginlist = []
            self.__plugins[f] = pluginlist
            helper = self.createHelper( pluginlist )
            setattr(self,f, helper)
    
    def createHelper(self, list):
        def executeHelper(*args):
            res = []
            for fun in list:
                res.append(fun(*args))
            return res
        return executeHelper
    
    def registerModule(self, module):
        registered = False
        if self.descriptor in module.WIKIDPAD_PLUGIN:
            for f in self.__functionNames:
                if hasattr(module, f):
                    self.__plugins[f].append(getattr(module,f))
                    registered = True
            if not registered:
                print "plugin", module.__name__, " exposes ", self.descriptor, \
                      "but does not support any interface methods!"
        return registered

    def deleteModule(self, module):
        for f in __functionNames:
            if hasattr(module, f):
                self.__plugins[f].remove(getattr(module,f))
    
class PluginManager(object):
    """manages all PluginAPIs and plugins."""
    def __init__(self):
        self.pluginAPIs = {}
        self.plugins = {}      
        
    def registerPluginAPI(self, name, functions):
        api = PluginAPI(name, functions)
        self.pluginAPIs[name] = api
        return api
            
    def deletePluginAPI(self, name):
        del self.pluginAPIs[name]
        
    def getPluginAPI(self, name):
        return self.pluginAPIs[name]
        
    def registerPlugin(self, module):
        registered = False
        for api in self.pluginAPIs.itervalues():
            registered |= api.registerModule(module)
        if registered:
            self.plugins[module.__name__] = module
        return registered

    def deletePlugin(self, name):
        if name in self.plugins:
            module = self.plugins[name]
            for api in self.pluginAPIs.itervalues():
                api.deleteModule(module)
            del self.plugins[name]
        
    def loadPlugins(self, directories, excludeFiles):
        """load and register plugins with apis. the directories in the list
           directories are searched in order for all files ending with .py or 
           all directories. These are assumed to be possible plugins for 
           WikidPad. All such files and directories are loaded as modules and if
           they have the WIKIDPAD_PLUGIN variable, are registered. 
           
           Files and directories given in exludeFiles are not loaded at all. Also 
           directories are searched in order for plugins. Therefore plugins
           appearing in earlier directories are not loaded from later ones."""
        exclusions = excludeFiles[:]
        for directory in directories:
            if not os.access(mbcsEnc(directory, "replace")[0], os.F_OK):
                continue
            files = os.listdir(directory)
            for name in files:
                module = None
                fullname = os.path.join(directory, name)
                ( moduleName, ext ) = os.path.splitext(name)
                if name in exclusions:
                    continue
                if os.path.isfile(fullname) and ext == '.py':
                    module = self.importCode(open(fullname), moduleName)
                elif os.path.isdir(fullname):
                    module = self.importDirectory(fullname)
                if module and hasattr(module, "WIKIDPAD_PLUGIN"):
                    if self.registerPlugin(module):
                        exclusions.append(name)
          
    def importDirectory(self, name, add_to_sys_modules = False): 
        name = mbcsEnc(name, "replace")[0]
        try:
            module = __import__(name)
        except ImportError:
            return None
        if not add_to_sys_modules:
            del sys.modules[name]
        return module
        
    def importCode(self,code,name,add_to_sys_modules = False):
        """
        Import dynamically generated code as a module. code is the
        object containing the code (a string, a file handle or an
        actual compiled code object, same types as accepted by an
        exec statement). The name is the name to give to the module,
        and the final argument says wheter to add it to sys.modules
        or not. If it is added, a subsequent import statement using
        name will return this module. If it is not added to sys.modules
        import will try to load it in the normal fashion.

        import foo

        is equivalent to

        foofile = open("/path/to/foo.py")
        foo = importCode(foofile,"foo",1)

        Returns a newly generated module.
        """
        import imp

        module = imp.new_module(name)

        exec code in module.__dict__
        if add_to_sys_modules:
            sys.modules[name] = module

        return module



class InsertionPluginManager:
    def __init__(self, byKeyDescriptions):
        """
        byKeyDescriptions -- sequence of tuples as returned by
            describeInsertionKeys() of a plugin
        """
        self.byKeyDescriptions = byKeyDescriptions

        # (<insertion key>, <import type>) tuple to initialized handler
        # this is only filled on demand
        self.ktToHandlerDict = {}

        # Build ktToDescDict meaning
        # (<insertion key>, <import type>) tuple to description tuple dictionary
        ktToDescDict = {}
        for keyDesc in self.byKeyDescriptions:
            key, etlist, factory = keyDesc
            for et in etlist:
                ktToDescDict[(key, et)] = keyDesc

        # (<insertion key>, <import type>) tuple to description tuple dictionary
        self.ktToDescDict = ktToDescDict
        
        # Contains all handler objects for which taskStart() was called and
        # respective taskEnd() wasn't called yet.
        # Dictionary {id(handler): handler}

        self.startedHandlers = {}
        
    def getHandler(self, exporter, exportType, insKey):
        """
        Return the appropriate handler for the parameter combination or None
        exporter -- Calling exporter object
        exportType -- string describing the export type
        insKey -- insertion key
        """
        result = self.ktToHandlerDict.get((insKey, exportType), 0) # Can't use None here

        if result == 0:
            keyDesc = self.ktToDescDict.get((insKey, exportType))
            if keyDesc is None:
                result = None
            else:
                key, etlist, factory = keyDesc
                try:
                    obj = factory(wxGetApp())
                except:
                    traceback.print_exc()
                    obj = None

                for et in etlist:
                    self.ktToHandlerDict[(key, et)] = obj
                
                result = obj
        
        if result is not None and not id(result) in self.startedHandlers:
            # Handler must be started before it can be used.
            try:
                result.taskStart(exporter, exportType)
                self.startedHandlers[id(result)] = result
            except:
                traceback.print_exc()
                result = None

        return result


    def taskEnd(self):
        """
        Call taskEnd() of all created handlers.
        """
        for handler in self.startedHandlers.values():
            try:
                handler.taskEnd()
            except:
                traceback.print_exc()
            
        self.startedHandlers.clear()


