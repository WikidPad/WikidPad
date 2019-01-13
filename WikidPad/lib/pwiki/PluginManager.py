

from zipimport import zipimporter
import sys, traceback, os.path

import wx

from .StringOps import mbcsEnc
from functools import reduce




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


class SimplePluginAPI:
    """encapsulates a single plugin api and stores the functions of various
       plugins implementing that api. It takes a unique descriptor and a list
       of function names at creation time. For each function name a member is
       created that calls the registered plugin functions. The descriptor must 
       appear in the WIKIDPAD_PLUGIN sequence object of a module to have
       the module registered. After that the module just has to implement a 
       subset of the api's functions to be registered."""

    def __init__(self, descriptor, functions):
        self.descriptor = descriptor
        self._functionNames = functions
        self._plugins = {}
        for f in self._functionNames:
            pluginlist = []
            self._plugins[f] = pluginlist
            helper = self._createHelper( pluginlist )
            setattr(self,f, helper)

    def getFunctionNames(self):
        return self._functionNames

    def hasFunctionName(self, fctName):
        return fctName in self._functionNames


    @staticmethod
    def _createHelper(funcList):
        f = lambda *args, **kwargs: [fun(*args, **kwargs) for fun in funcList]
        f.getCompounds = lambda: funcList

        return f


    def registerModule(self, module):
        registered = False
        if self.descriptor in module.WIKIDPAD_PLUGIN:
            for f in self._functionNames:
                if hasattr(module, f):
                    self._plugins[f].append(getattr(module,f))
                    registered = True
            if not registered:
                sys.stderr.write("plugin " + module.__name__ + " exposes " +
                        str(self.descriptor) + 
                        " but does not support any interface methods!")
        return registered

#     def deleteModule(self, module):
#         for f in self._functionNames:
#             if hasattr(module, f):
#                 self._plugins[f].remove(getattr(module,f))


class WrappedPluginAPI:
    """
    Constructor takes as keyword arguments after descriptor names.
    
    The keys of the arguments are the function names exposed as attributes by
    the API object. The values can be either:
        None  to call function of same name in module(s) as SimplePluginAPI
            does
        a string  to call function of this name in module(s)
        a wrapper function  to call with module object and parameters from
                original function call
    """

    def __init__(self, descriptor, **wrappedFunctions):
        self.descriptor = descriptor
        self._functionNames = list(wrappedFunctions.keys())
        self._wrappedFunctions = wrappedFunctions
        self._plugins = {}
        for f in self._functionNames:
            pluginlist = [] # List containing either modules if wrappedFunctions[f]
                    # is not None or functions if wrappedFunctions[f] is None
            self._plugins[f] = pluginlist
            helper = self._createHelper(wrappedFunctions[f], pluginlist)
            setattr(self,f, helper)
            
    def getFunctionNames(self):
        return self._functionNames

    def hasFunctionName(self, fctName):
        return fctName in self._functionNames


    @staticmethod
    def _createHelper(wrapFct, list):
        if wrapFct is None or isinstance(wrapFct, str):
            f = lambda *args, **kwargs: [fun(*args, **kwargs) for fun in list]
            f.getCompounds = lambda: list
            
            return f
        else:
            f = lambda *args, **kwargs: [wrapFct(module, *args, **kwargs)
                    for module in list]
            f.getCompounds = lambda: [lambda *args, **kwargs: wrapFct(module,
                    *args, **kwargs) for module in list]

            return f


    def registerModule(self, module):
        if not self.descriptor in module.WIKIDPAD_PLUGIN:
            return False

        registered = False
        for f in self._functionNames:
            if self._wrappedFunctions[f] is None:
                if hasattr(module, f):
                    self._plugins[f].append(getattr(module,f))
                    registered = True
            elif isinstance(self._wrappedFunctions[f], str):
                realF = self._wrappedFunctions[f]
                if hasattr(module, realF):
                    self._plugins[f].append(getattr(module,realF))
                    registered = True
            else:
                self._plugins[f].append(module)
                # An internal wrapper function doesn't count as "registered"
#                 registered = True

        if not registered:
            sys.stderr.write("plugin " + module.__name__ + " exposes " +
                    str(self.descriptor) + 
                    " but does not support any interface methods!")

        return registered



class PluginAPIAggregation:
    def __init__(self, *apis):
        self._apis = apis

        fctNames = set()
        for api in self._apis:
            fctNames.update(api.getFunctionNames())
        
        for f in list(fctNames):
            funcList = [getattr(api, f) for api in apis if api.hasFunctionName(f)]
            setattr(self, f, PluginAPIAggregation._createHelper(funcList))


    @staticmethod
    def _createHelper(funcList):
        f = lambda *args, **kwargs: reduce(lambda a, b: a+list(b),
                [fun(*args, **kwargs) for fun in funcList])
        f.getCompounds = lambda: reduce(lambda a, b: a+list(b),
                [fun.getCompounds() for fun in funcList])

        return f




class PluginManager:
    """manages all PluginAPIs and plugins."""
    def __init__(self, directories, systemDirIdx=-1):
        self.pluginAPIs = {}  # Dictionary {<type name>:<verReg dict>}
                # where verReg dict is list of tuples (<version No>:<PluginAPI instance>)
        self.plugins = {}  
        self.directories = directories
        self.systemDirIdx = systemDirIdx
        
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
        
        return list(found.items())


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
        """
        load and register plugins with apis.
        
        Step one loads from the fixed directories (WikidPad installation
        plugin directories)
        Step two uses Python's package management to find plugins
        installed by PIP or similar measures.
        
        Files and directories given in exludeFiles are not loaded from fixed
        directories.
        
        Fixed directories are searched in order for plugins. Therefore plugins
        appearing in earlier directories are not loaded from later ones.
        The names of plugins from package management are not processed so
        all of these plugins are loaded.
        """
        self.loadPluginsFixed(excludeFiles)
        self.loadPluginsPackageManaged()
        
           

    def loadPluginsFixed(self, excludeFiles):
        """load and register plugins with apis. The directories in the list
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

            if dirNum == self.systemDirIdx:
                packageName = "wikidpadSystemPlugins"
            else:
                packageName = "cruelimportExtensionsPackage%i_%i" % \
                        (id(self), dirNum)

            package = imp.new_module(packageName)
            package.__path__ = [directory]
            sys.modules[packageName] = package

            for name in files:
                try:
                    module = None
                    fullname = os.path.join(directory, name)
                    ( moduleName, ext ) = os.path.splitext(name)
                    if name in exclusions:
                        continue
                    if os.path.isfile(fullname):
                        if ext == '.py':
                            with open(fullname, "rb") as f:
                                module = imp.load_module(packageName + "." + moduleName, f,
                                        fullname, (".py", "r", imp.PY_SOURCE))
                        elif ext == '.zip':
                            module = imp.new_module(
                                    packageName + "." + moduleName)
                            module.__path__ = [fullname]
                            module.__zippath__ = fullname
                            sys.modules[packageName + "." + moduleName] = module
                            zi = zipimporter(fullname)
                            co = zi.get_code("__init__")
                            exec(co, module.__dict__)

                    if module:
                        setattr(package, moduleName, module)
                        if hasattr(module, "WIKIDPAD_PLUGIN"):
                            self.registerPlugin(module)
                except:
                    traceback.print_exc()
            del sys.path[-1]
            
    def loadPluginsPackageManaged(self):
        import pkg_resources
        
        for entry_point in pkg_resources.iter_entry_points('WikidPad.plugins'):
            module = entry_point.load()
            if hasattr(module, "WIKIDPAD_PLUGIN"):
                self.registerPlugin(module)

          
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


class LearningDispatcher:
    """
    A LearningDispatcher stores a Simple- or WrappedPluginAPI object which
    contains API functions (usually all with the same name) scattered over
    multiple plugins.
    
    Basically when its dispatch() function is called the dispatcher in turn
    calls all functions in the API object. Because there can be many calls
    to dispatch() and many functions to call the dispatcher "learns" which
    functions to call and which not.
    
    The call to dispatch() receives a key (for a dictionary) as first
    parameter (all following parameters are handed to the called plugin
    functions unmodified). The key gives some kind of "context" in which
    this call happens. The key itself is not transferred to the plugin
    functions so the context must be repeated somehow in the following
    parameters so that a plugin function can decide if it handles this context
    or not.
    
    The rule is that every called plugin function must return None if
    and only if it does not and never handle this context. For a given
    context the function must return None either always or never. If the
    plugin function returns None it is usually not called again by the
    LearningDispatcher in this context.
    """    
    
    def __init__(self, apiFunc):
        self.apiFunc = apiFunc
        self.keyToHandlerList = {}
        
    def hasHandlerForKey(self, key):
        if key not in self.keyToHandlerList:
            # If the key is not in the dictionary this function wasn't called
            # yet therefore we have to assume that there may be handlers
            return True

        return len(self.keyToHandlerList[key]) > 0
    
    def clearLearning(self):
        """
        Forget the learned dispatching
        """
        self.keyToHandlerList.clear()
        
        
    def dispatch(self, key, *args, **kwargs):
        result = []
        
        if key in self.keyToHandlerList:
            # Function was called previously 
            for hdl in self.keyToHandlerList[key]:
                result.append(hdl(*args, **kwargs))
            
            return result
        else:
            # Yet unknown function
            allHandlers = self.apiFunc.getCompounds()
            hdlList = []
            for hdl in allHandlers:
                r = hdl(*args, **kwargs)
                if r is None:
                    # Handler doesn't handle particular key
                    continue
                result.append(r)
                hdlList.append(hdl)
            
            self.keyToHandlerList[key] = hdlList

        return result


class KeyInParamLearningDispatcher(LearningDispatcher):
    """
    While in a LearningDispatcher the context information contained in
    a key must be repeated somehow in the other parameters, the constructor
    here gets an index number keyIdx into the positional parameters of
    the dispatch() call (which here doesn't take a separate key parameter) 
    and uses the parameter with that number as key.
    """
    
    def __init__(self, apiFunc, keyIdx):
        LearningDispatcher.__init__(self, apiFunc)
        self.keyIdx = keyIdx

    def dispatch(self, *args, **kwargs):
        """
        All parameters are handed to the plugin functions, one of it is
        also used as key.
        """
        return LearningDispatcher.dispatch(self, args[self.keyIdx],
                *args, **kwargs)



# class MenuPluginDispatcher:
#     """
#     Dispatches menus (especially context menus) to handlers which can modify
#     them to add additional menu items
#     """
#     def __init__(self, descriptors):
#         """
#         descriptors -- Sequence of tuples as returned by
#             describeMenuModifiers() of a plugin. Each tuple is of form
#             (contextName, menuHandler). Assume length >= 2, it may have
#             additional fields.
#         """
#         contextNameIndex = collections.defaultdict(list)
#         for d in descriptors:
#             contextNameIndex[d[0]].append(d)
# 
#         self.contextNameIndex = contextNameIndex
# 
#     def hasHandlerForContextName(self, contextName):
#         return self.contextNameIndex.has_key(contextName) or \
#                 self.contextNameIndex.has_key("*")
# 
#     def dispatch(self, menu, contextName, contextDict):
#         for d in self.contextNameIndex.get(contextName, ()):
#             d[1](menu, contextName, contextDict)
#         for d in self.contextNameIndex.get("*", ()):
#             d[1](menu, contextName, contextDict)
        
    
        


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
        for handler in list(self.startedHandlers.values()):
            try:
                handler.taskEnd()
            except:
                traceback.print_exc()
            
        self.startedHandlers.clear()



def getExporterClasses(mainControl):
    from . import Exporters    # createExporters
    
    # TODO: Cache?
    return reduce(lambda a, b: a+list(b),
            wx.GetApp().describeExportersApi.describeExportersV01(mainControl),
            list(Exporters.describeExportersV01(mainControl)))

#     classIds = set()
#     classList = []
#     
#     unfilteredClasses = 
#     
#     for c in unfilteredClasses:
#         if id(c) in classIds:
#             continue
# 
#         classIds.add(id(c))
#         classList.append(c)
#     
#     return classList


def getExporterTypeDict(mainControl, continuousExport):
    """
    Returns dictionary {exporterTypeName: (class, exporterTypeName, humanReadableName)}
    """
    result = {}

    # External plugins can overwrite internal exporter types
    for c in getExporterClasses(mainControl):
        for tnt in c.getExportTypes(mainControl, continuousExport):
            tname, tnameHr = tnt[:2]
            result[tname] = (c, tname, tnameHr)

    return result



def groupOptPanelPlugins(mainControl, typeDict, guiParent=None):
    """
    Returns dictionary {pluginTypeName: (pluginObject, pluginTypeName,
        humanReadableName, addOptPanel)}
        addOptPanel: additional options GUI panel and is always None if
            guiParent is None
    typeDict -- dictionary {pluginTypeName: (class, pluginTypeName,
        humanReadableName)}
    """
    preResult = []

    classIdToInstanceDict = {}
    
    # First create an object of each exporter class and create list of 
    # objects with the respective exportType (and human readable export type)
    for ctt in list(typeDict.values()):
        ob = classIdToInstanceDict.get(id(ctt[0]))
        if ob is None:
            ob = ctt[0](mainControl)
            classIdToInstanceDict[id(ctt[0])] = ob

        preResult.append((ob, ctt[1], ctt[2]))

    result = {}

    if guiParent is None:
        # No GUI, just convert to appropriate dictionary
        result = {}
        for ob, expType, expTypeHr in preResult:
            result[expType] = (ob, expType, expTypeHr, None)
        return result

    else:
        # With GUI

        # First collect desired exporter types we want from each exporter object
        # Each object should only be asked once for the panel list
        # with the complete set of exporter types we want from it
        objIdToObjExporterTypes = {}
        for ob, expType, expTypeHr in preResult:
            objIdToObjExporterTypes.setdefault(id(ob), [ob, set()])[1].add(expType)

        # Now actually ask for panels from each object and create dictionary from
        # export type to panel
        # If we would ask the same object multiple times we may get multiple
        # equal panels where only one panel is necessary
        exportTypeToPanelDict = {}
        for ob, expTypeSet in list(objIdToObjExporterTypes.values()):
            expTypePanels = ob.getAddOptPanelsForTypes(guiParent, expTypeSet)
            for expType, panel in expTypePanels:
                if expType in expTypeSet:
                    exportTypeToPanelDict[expType] = panel
                    expTypeSet.remove(expType)
            
            # Possibly remaining types not returned by getAddOptPanelsForTypes
            # get a None as panel
            for expType in expTypeSet:
                exportTypeToPanelDict[expType] = None

        # Finally create result dictionary
        result = {}
        for ob, expType, expTypeHr in preResult:
            result[expType] = (ob, expType, expTypeHr,
                    exportTypeToPanelDict[expType])

        return result



def getSupportedExportTypes(mainControl, guiParent=None, continuousExport=False):
    """
    Returns dictionary {exporterTypeName: (exportObject, exporterTypeName,
        humanReadableName, addOptPanel)}
    addOptPanel is the additional options GUI panel and is always None if
    guiParent is None
    """
    return groupOptPanelPlugins(mainControl,
            getExporterTypeDict(mainControl, continuousExport),
            guiParent=guiParent)




def getPrintTypeDict(mainControl):
    """
    Returns dictionary {printTypeName: (class, printTypeName, humanReadableName)}
    """
    result = {}

    # External plugins can overwrite internal exporter types
    for c in wx.GetApp().describePrints(mainControl):
        for tnt in c.getPrintTypes(mainControl):
            tname, tnameHr = tnt[:2]
            result[tname] = (c, tname, tnameHr)

    return result



def getSupportedPrintTypes(mainControl, guiParent=None):
    """
    Returns dictionary {printTypeName: (printObject, printTypeName,
        humanReadableName, addOptPanel)}
    addOptPanel is the additional options GUI panel and is always None if
    guiParent is None
    """
    return groupOptPanelPlugins(mainControl,
            getPrintTypeDict(mainControl), guiParent=guiParent)


