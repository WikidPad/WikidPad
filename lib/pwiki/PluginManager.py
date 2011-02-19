from __future__ import with_statement

import os, sys, traceback, os.path, imp

# sys.path.append(ur"C:\Daten\Projekte\Wikidpad\Next20\extensions")

import wx

from .StringOps import mbcsEnc, pathEnc




"""The PluginManager and PluginAPI classes implement a generic plugin framework.
   Plugin apis are created by the PluginManager and can be used to call all
   installed plugins for that api at once. The PluginManager loads plugins from
   specified directories and manages them. 
   
   Example code:
   
   pm = PluginManager(["dir1, "dir2"])
   api = pm.registerSimplePluginAPI(("myAPI",1), ["init", "call1", "call2", "exit"])
   pm.loadPlugins(["notloadme", "andnotme"])
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


class SimplePluginAPI(object):
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
        for f in self.__functionNames:
            pluginlist = []
            self.__plugins[f] = pluginlist
            helper = self.__createHelper( pluginlist )
            setattr(self,f, helper)

    def getFunctionNames(self):
        return self.__functionNames

    def hasFunctionName(self, fctName):
        return fctName in self.__functionNames


    @staticmethod
    def __createHelper(funcList):
        return lambda *args, **kwargs: [fun(*args, **kwargs) for fun in funcList]


    def registerModule(self, module):
        registered = False
        if self.descriptor in module.WIKIDPAD_PLUGIN:
            for f in self.__functionNames:
                if hasattr(module, f):
                    self.__plugins[f].append(getattr(module,f))
                    registered = True
            if not registered:
                sys.stderr.write("plugin " + module.__name__ + " exposes " +
                        self.descriptor + 
                        " but does not support any interface methods!")
        return registered

#     def deleteModule(self, module):
#         for f in self.__functionNames:
#             if hasattr(module, f):
#                 self.__plugins[f].remove(getattr(module,f))


class WrappedPluginAPI(object):
    """
    Constructor takes as keyword arguments after descriptor names.
    
    The keys of the arguments are the function names exposed as attributes by
    the API object. The values can be either:
        None  to call function of same name in module(s)
        a string  to call function of this name in module(s)
        a wrapper function  to call with module object and parameters from
                original function call
    """

    def __init__(self, descriptor, **wrappedFunctions):
        self.descriptor = descriptor
        self.__functionNames = wrappedFunctions.keys()
        self.__wrappedFunctions = wrappedFunctions
        self.__plugins = {}
        for f in self.__functionNames:
            pluginlist = [] # List containing either modules if wrappedFunctions[f]
                    # is not None or functions if wrappedFunctions[f] is None
            self.__plugins[f] = pluginlist
            helper = self.__createHelper(wrappedFunctions[f], pluginlist)
            setattr(self,f, helper)
            
    def getFunctionNames(self):
        return self.__functionNames

    def hasFunctionName(self, fctName):
        return fctName in self.__functionNames


    @staticmethod
    def __createHelper(wrapFct, list):
        if wrapFct is None or isinstance(wrapFct, (str, unicode)):
            return lambda *args, **kwargs: [fun(*args, **kwargs) for fun in list]
        else:
            return lambda *args, **kwargs: [wrapFct(module, *args, **kwargs)
                    for module in list]


    def registerModule(self, module):
        if self.descriptor in module.WIKIDPAD_PLUGIN:
            for f in self.__functionNames:
                if self.__wrappedFunctions[f] is None:
                    if hasattr(module, f):
                        self.__plugins[f].append(getattr(module,f))
                        return True
                    else:
                        sys.stderr.write("plugin " + module.__name__ + " exposes " +
                                self.descriptor + 
                                " but does not support any interface methods!")
                        return False
                elif isinstance(self.__wrappedFunctions[f], (str, unicode)):
                    realF = self.__wrappedFunctions[f]
                    if hasattr(module, realF):
                        self.__plugins[f].append(getattr(module,realF))
                        return True
                    else:
                        sys.stderr.write("plugin " + module.__name__ + " exposes " +
                                self.descriptor + 
                                " but does not support any interface methods!")
                        return False
                else:
                    self.__plugins[f].append(module)
                    return True

        return False



class PluginAPIAggregation(object):
    def __init__(self, *apis):
        self.__apis = apis

        fctNames = set()
        for api in self.__apis:
            fctNames.update(api.getFunctionNames())
        
        for f in list(fctNames):
            funcList = [getattr(api, f) for api in apis if api.hasFunctionName(f)]
            helper = lambda *args, **kwargs: reduce(lambda a, b: a+list(b),
                    [fun(*args, **kwargs) for fun in funcList])
            setattr(self,f, helper)



class PluginManager(object):
    """manages all PluginAPIs and plugins."""
    def __init__(self, directories):
        self.pluginAPIs = {}  # Dictionary {<type name>:<verReg dict>}
                # where verReg dict is list of tuples (<version No>:<PluginAPI instance>)
        self.plugins = {}  
        self.directories = directories
        
    def registerSimplePluginAPI(self, descriptor, functions):
        api = SimplePluginAPI(descriptor, functions)
        self.pluginAPIs[descriptor] = api
        return api


    def registerWrappedPluginAPI(self, descriptor, **wrappedFunctions):
        api = WrappedPluginAPI(descriptor, **wrappedFunctions)
        self.pluginAPIs[descriptor] = api
        return api
        
    
    @staticmethod
    def combineAPIs(*apis):
        return PluginAPIAggregation(*apis)


#         name, versionNo = descriptor[:2]
# 
#         if not self.pluginAPIs.has_key(name):
#             verReg = []
#             self.pluginAPIs[name] = verReg
#         else:
#             verReg = self.pluginAPIs[name]
# 
#         verReg.append(versionNo, api)
#         return api


#     def deletePluginAPI(self, name):
#         del self.pluginAPIs[name]
#         
#     def getPluginAPIVerReg(self, name):
#         return self.pluginAPIs[name]


    def _processDescriptors(self, descriptors):
        """
        Find all known plugin API descriptors and return those
        of each type with highest version number.
        Returns a list of descriptor tuples.
        """
        found = {}
        for d in descriptors:
            name, versionNo = d[:2]
            if not (name, versionNo) in self.pluginAPIs:
                continue

            if versionNo > found.get(name, 0):
                found[name] = versionNo
        
        return found.items()


    def registerPlugin(self, module):
        registered = False
        
        for desc in self._processDescriptors(module.WIKIDPAD_PLUGIN):
            registered |= self.pluginAPIs[desc].registerModule(module)

#         for api in self.pluginAPIs.itervalues():
#             registered |= api.registerModule(module)

        if registered:
            self.plugins[module.__name__] = module

        return registered

#     def deletePlugin(self, name):
#         if name in self.plugins:
#             module = self.plugins[name]
#             for api in self.pluginAPIs.itervalues():
#                 api.deleteModule(module)
#             del self.plugins[name]
        
    def loadPlugins(self, excludeFiles):
        """load and register plugins with apis. the directories in the list
           directories are searched in order for all files ending with .py or 
           all directories. These are assumed to be possible plugins for 
           WikidPad. All such files and directories are loaded as modules and if
           they have the WIKIDPAD_PLUGIN variable, are registered. 
           
           Files and directories given in exludeFiles are not loaded at all. Also 
           directories are searched in order for plugins. Therefore plugins
           appearing in earlier directories are not loaded from later ones."""
        import imp
        exclusions = excludeFiles[:]
        for dirNum, directory in enumerate(self.directories):
            sys.path.append(os.path.dirname(directory))
            if not os.access(mbcsEnc(directory, "replace")[0], os.F_OK):
                continue
            files = os.listdir(directory)
            for name in files:
                try:
                    module = None
                    fullname = os.path.join(directory, name)
                    ( moduleName, ext ) = os.path.splitext(name)
                    if name in exclusions:
                        continue
                    if os.path.isfile(fullname) and ext == '.py':
                        with open(fullname) as f:
                            packageName = "cruelimportExtensionsPackage%i_%i" % \
                                    (id(self), dirNum)

                            module = imp.new_module(packageName)
                            module.__path__ = [directory]
                            sys.modules[packageName] = module

                            module = imp.load_module(packageName + "." + moduleName, f,
                                    mbcsEnc(fullname)[0], (".py", "r", imp.PY_SOURCE))
                    if module and hasattr(module, "WIKIDPAD_PLUGIN"):
                        if self.registerPlugin(module):
                            exclusions.append(name)
                except:
                    traceback.print_exc()
            del sys.path[-1]
          
    def importDirectory(self, name, add_to_sys_modules = False): 
        name = mbcsEnc(name, "replace")[0]
        try:
            module = __import__(name)
        except ImportError:
            return None
        if not add_to_sys_modules:
            del sys.modules[name]
        return module


#     def importCode(self,code,name,add_to_sys_modules = False):
#         """
#         Import dynamically generated code as a module. code is the
#         object containing the code (a string, a file handle or an
#         actual compiled code object, same types as accepted by an
#         exec statement). The name is the name to give to the module,
#         and the final argument says wheter to add it to sys.modules
#         or not. If it is added, a subsequent import statement using
#         name will return this module. If it is not added to sys.modules
#         import will try to load it in the normal fashion.
# 
#         import foo
# 
#         is equivalent to
# 
#         foofile = open("/path/to/foo.py")
#         foo = importCode(foofile,"foo",1)
# 
#         Returns a newly generated module.
#         """
#         import imp
# 
#         module = imp.new_module(name)
# 
#         exec code in module.__dict__
#         if add_to_sys_modules:
#             sys.modules[name] = module
# 
#         return module



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
            key, etlist, factory = keyDesc[:3]
            for et in etlist:
                ktToDescDict[(key, et)] = keyDesc[:3]

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
                    obj = factory(wx.GetApp())
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



def getSupportedExportTypes(mainControl, continuousExport, guiParent=None):
    import Exporters
    
    result = {}
    
    for ob in Exporters.describeExporters(mainControl):   # TODO search plugins
        for tp in ob.getExportTypes(guiParent, continuousExport):
            result[tp[0]] = (ob,) + tuple(tp)

    return result

