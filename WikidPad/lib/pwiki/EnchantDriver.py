

# pyenchant
#
# Copyright (C) 2004-2008, Ryan Kelly
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the
# Free Software Foundation, Inc., 59 Temple Place - Suite 330,
# Boston, MA 02111-1307, USA.
#
# In addition, as a special exception, you are
# given permission to link the code of this program with
# non-LGPL Spelling Provider libraries (eg: a MSFT Office
# spell checker backend) and distribute linked combinations including
# the two.  You must obey the GNU Lesser General Public License in all
# respects for all of the code used other than said providers.  If you modify
# this file, you may extend this exception to your version of the
# file, but you are not obligated to do so.  If you do not wish to
# do so, delete this exception statement from your version.
# 
# 
# 
# Modified to work with WikidPad and to reduce dependencies
#    2006, 2008, 2010 by Michael Butscher
#    2010 Added simple thread-safety
"""
    enchant:  Access to the enchant spellchecking library

    This module provides several classes for performing spell checking
    via the Enchant spellchecking library.  For more details on Enchant,
    visit the project website:

        http://www.abisource.com/enchant/

    Spellchecking is performed using 'Dict' objects, which represent
    a language dictionary.  Their use is best demonstrated by a quick
    example:

        >>> import enchant
        >>> d = enchant.Dict("en_US")   # create dictionary for US English
        >>> d.check("enchant")
        True
        >>> d.check("enchnt")
        False
        >>> d.suggest("enchnt")
        ['enchant', 'enchants', 'enchanter', 'penchant', 'incant', 'enchain', 'enchanted']

    Languages are identified by standard string tags such as "en" (English)
    and "fr" (French).  Specific language dialects can be specified by
    including an additional code - for example, "en_AU" refers to Australian
    English.  The later form is preferred as it is more widely supported.

    To check whether a dictionary exists for a given language, the function
    'dict_exists' is available.  Dictionaries may also be created using the
    function 'request_dict'.

    A finer degree of control over the dictionaries and how they are created
    can be obtained using one or more 'Broker' objects.  These objects are
    responsible for locating dictionaries for a specific language.
    
    In Python 2.x, unicode strings are supported transparently in the
    standard manner - if a unicode string is given as an argument, the
    result will be a unicode string. Note that Enchant works in UTF-8 
    internally, so passing an ASCII string to a dictionary for a language
    requiring Unicode may result in UTF-8 strings being returned.

    In Python 3.x unicode strings are expected throughout.  Bytestrings
    should not be passed into any functions.

    Errors that occur in this module are reported by raising subclasses
    of 'Error'.

"""



# Make version info available
__ver_major__ = 1
__ver_minor__ = 5
__ver_patch__ = 0
__ver_sub__ = ""
__version__ = "%d.%d.%d%s" % (__ver_major__,__ver_minor__,
                              __ver_patch__,__ver_sub__)


# from enchant import _enchant as _e
import sys, os, os.path
from threading import RLock
from ctypes import *
from ctypes.util import find_library

import wx


#  -------------------- From utils module --------------------


def get_resource_filename(resname):
    """Get the absolute path to the named resource file.

    This serves widely the same purpose as pkg_resources.resource_filename(),
    but tries to avoid loading pkg_resources unless we're actually in
    an egg.
    """
#     path = os.path.dirname(os.path.abspath(__file__))
    path = wx.GetApp().getWikiAppDir()
    path = os.path.join(path,resname)
    if os.path.exists(path):
        return path
#     import pkg_resources
#     return pkg_resources.resource_filename("enchant",resname)


_EnchantCCallLock = RLock()

class EnchantStr(str):
    """String subclass for interfacing with enchant C library.

    This class encapsulate the logic for interfacing between python native
    string/unicode objects and the underlying enchant library, which expects
    all strings to be UTF-8 character arrays.  It is a subclass of the
    default string class 'str' - on Python 2.x that makes it an ascii string,
    on Python 3.x it is a unicode object.

    Initialise it with a string or unicode object, and use the encode() method
    to obtain an object suitable for passing to the underlying C library.
    When strings are read back into python, use decode(s) to translate them
    back into the appropriate python-level string type.

    This allows us to following the common Python 2.x idiom of returning
    unicode when unicode is passed in, and byte strings otherwise.  It also
    lets the interface be upwards-compatible with Python 3, in which string
    objects will be unicode by default.
    """

    def __new__(self,value):
        """EnchantStr data constructor.

        This method records whether the initial string was unicode, then
        simply passes it along to the default string constructor.
        """
        if type(value) is str:
          self._was_unicode = True
          if str is not str:
            value = value.encode("utf-8")
        else:
          self._was_unicode = False
          if str is not bytes:
            raise RuntimeError("Don't pass bytestrings to pyenchant")
        return str.__new__(self,value)

    def encode(self):
        """Encode this string into a form usable by the enchant C library."""
        return str.encode(self,"utf-8")

    def decode(self,value):
        """Decode a string returned by the enchant C library."""
        if self._was_unicode:
          return value.decode("utf-8")
          #if str is str:
          #  # TODO: why does ctypes convert c_char_p to str(),
          #  #       rather than to bytes()?
          #  return value.encode().decode("utf-8")
          #else:
          #  return value.decode("utf-8")
        else:
          return value




if os.name == "nt":
    ctypes_find_library = find_library

    def find_library(name):
#         if name in ('c', 'm'):
#             return find_msvcrt()
        # See MSDN for the REAL search order.
        for directory in [os.path.dirname(os.path.abspath(sys.argv[0]))] + os.environ['PATH'].split(os.pathsep):
            fname = os.path.join(directory, name)
            if os.path.exists(fname):
                return fname
            if fname.lower().endswith(".dll"):
                continue
            fname = fname + ".dll"
            if os.path.exists(fname):
                return fname
        return None




#  -------------------- From _enchant module --------------------


# if sys.platform == "win32":
#   # Add our bundled enchant libraries to DLL search path
#   mypath = os.path.dirname(get_resource_filename("libenchant.dll"))
#   os.environ['PATH'] = os.environ['PATH'] + ";" + mypath

# cmore deleted begin

# e_path = find_library("enchant")
# if not e_path:
#   e_path = find_library("libenchant")
# if not e_path:
#   raise ImportError("enchant C library not found")
# 
# e = cdll.LoadLibrary(e_path)

# cmore deleted end


# cmore add begin

e = None

# from enchant.errors import *

def _e_path_possibilities():
    """Generator yielding possible locations of the enchant library."""
    yield os.environ.get("PYENCHANT_LIBRARY_PATH")
    yield find_library("enchant")
    yield find_library("libenchant")
    yield find_library("libenchant-1")
    if sys.platform == 'darwin':
         # enchant lib installed by macports
         yield "/opt/local/lib/libenchant.dylib"


# On win32 we ship a bundled version of the enchant DLLs.
# Use them if they're present.
if sys.platform == "win32":
    e_path = None
    try:
        from enchant import utils
        e_path = utils.get_resource_filename("libenchant.dll")
    except:
         try:
            from enchant import utils
            e_path = utils.get_resource_filename("libenchant-1.dll")
         except:
            pass
    if e_path is not None:
        # We need to use LoadLibraryEx with LOAD_WITH_ALTERED_SEARCH_PATH so
        # that we don't accidentally suck in other versions of e.g. glib.
        if not isinstance(e_path,str):
            e_path = str(e_path,sys.getfilesystemencoding())
        LoadLibraryEx = windll.kernel32.LoadLibraryExW
        LOAD_WITH_ALTERED_SEARCH_PATH = 0x00000008
        e_handle = LoadLibraryEx(e_path,None,LOAD_WITH_ALTERED_SEARCH_PATH)
        if not e_handle:
            raise WinError()
        e = CDLL(e_path,handle=e_handle)


# On darwin there may be a bundled version of the enchant DLLs.
# Use them if they're present.
if e is None and sys.platform == "darwin":
  try:
      from enchant import utils
      e_path = utils.get_resource_filename("lib/libenchant.1.dylib")
  except:
      pass
  else:
      # Enchant doesn't natively support relocatable binaries on OSX.
      # We fake it by patching the enchant source to expose a char**, which
      # we can write the runtime path into ourselves.
      e = CDLL(e_path)
      try:
          e_dir = os.path.dirname(os.path.dirname(e_path))
          prefix_dir = POINTER(c_char_p).in_dll(e,"enchant_prefix_dir_p")
          prefix_dir.contents = c_char_p(e_dir)
      except AttributeError:
          e = None


# Not found yet, search various standard system locations.
if e is None:
    for e_path in _e_path_possibilities():
        if e_path is not None:
            try:
                e = cdll.LoadLibrary(e_path)
            except:
                pass



# No usable enchant install was found :-(
if e is None:
   raise ImportError("enchant C library not found")

# cmore add end


# Define various callback function types

t_broker_desc_func = CFUNCTYPE(None,c_char_p,c_char_p,c_char_p,c_void_p)
t_dict_desc_func = CFUNCTYPE(None,c_char_p,c_char_p,c_char_p,c_char_p,c_void_p)


# Simple typedefs for readability

t_broker = c_void_p
t_dict = c_void_p


# Now we can define the types of each function we are going to use

broker_init = e.enchant_broker_init
broker_init.argtypes = []
broker_init.restype = t_broker

broker_free = e.enchant_broker_free
broker_free.argtypes = [t_broker]
broker_free.restype = None

broker_request_dict = e.enchant_broker_request_dict
broker_request_dict.argtypes = [t_broker,c_char_p]
broker_request_dict.restype = t_dict

broker_request_pwl_dict = e.enchant_broker_request_pwl_dict
broker_request_pwl_dict.argtypes = [t_broker,c_char_p]
broker_request_pwl_dict.restype = t_dict

broker_free_dict = e.enchant_broker_free_dict
broker_free_dict.argtypes = [t_broker,t_dict]
broker_free_dict.restype = None

broker_dict_exists = e.enchant_broker_dict_exists
broker_dict_exists.argtypes = [t_broker,c_char_p]
broker_free_dict.restype = c_int

broker_set_ordering = e.enchant_broker_set_ordering
broker_set_ordering.argtypes = [t_broker,c_char_p,c_char_p]
broker_set_ordering.restype = None

broker_get_error = e.enchant_broker_get_error
broker_get_error.argtypes = [t_broker]
broker_get_error.restype = c_char_p

broker_describe1 = e.enchant_broker_describe
broker_describe1.argtypes = [t_broker,t_broker_desc_func,c_void_p]
broker_describe1.restype = None
def broker_describe(broker,cbfunc):
    def cbfunc1(*args):
        cbfunc(*args[:-1])
    broker_describe1(broker,t_broker_desc_func(cbfunc1),None)

dict_check1 = e.enchant_dict_check
dict_check1.argtypes = [t_dict,c_char_p,c_size_t]
dict_check1.restype = c_int
def dict_check(dict,word):
#     print "--dict_check1", repr(dict)
    with _EnchantCCallLock:
        return dict_check1(dict,word,len(word))

dict_suggest1 = e.enchant_dict_suggest
dict_suggest1.argtypes = [t_dict,c_char_p,c_size_t,POINTER(c_size_t)]
dict_suggest1.restype = POINTER(c_char_p)
def dict_suggest(dict,word):
    numSuggsP = pointer(c_size_t(0))
    with _EnchantCCallLock:
        suggs_c = dict_suggest1(dict,word,len(word),numSuggsP)
    suggs = []
    n = 0
    while n < numSuggsP.contents.value:
        suggs.append(suggs_c[n])
        n = n + 1
    if numSuggsP.contents.value > 0:
        with _EnchantCCallLock:
            dict_free_string_list(dict,suggs_c)
    return suggs

dict_add1 = e.enchant_dict_add
dict_add1.argtypes = [t_dict,c_char_p,c_size_t]
dict_add1.restype = None
def dict_add(dict,word):
    return dict_add1(dict,word,len(word))

dict_add_to_pwl1 = e.enchant_dict_add
dict_add_to_pwl1.argtypes = [t_dict,c_char_p,c_size_t]
dict_add_to_pwl1.restype = None
def dict_add_to_pwl(dict,word):
    return dict_add_to_pwl1(dict,word,len(word))

dict_add_to_session1 = e.enchant_dict_add_to_session
dict_add_to_session1.argtypes = [t_dict,c_char_p,c_size_t]
dict_add_to_session1.restype = None
def dict_add_to_session(dict,word):
    return dict_add_to_session1(dict,word,len(word))

dict_remove1 = e.enchant_dict_remove
dict_remove1.argtypes = [t_dict,c_char_p,c_size_t]
dict_remove1.restype = None
def dict_remove(dict,word):
    return dict_remove1(dict,word,len(word))

dict_remove_from_session1 = e.enchant_dict_remove_from_session
dict_remove_from_session1.argtypes = [t_dict,c_char_p,c_size_t]
dict_remove_from_session1.restype = c_int
def dict_remove_from_session(dict,word):
    return dict_remove_from_session1(dict,word,len(word))

dict_is_added1 = e.enchant_dict_is_added
dict_is_added1.argtypes = [t_dict,c_char_p,c_size_t]
dict_is_added1.restype = c_int
def dict_is_added(dict,word):
    return dict_is_added1(dict,word,len(word))

dict_is_removed1 = e.enchant_dict_is_removed
dict_is_removed1.argtypes = [t_dict,c_char_p,c_size_t]
dict_is_removed1.restype = c_int
def dict_is_removed(dict,word):
    return dict_is_removed1(dict,word,len(word))

dict_is_in_session1 = e.enchant_dict_is_in_session
dict_is_in_session1.argtypes = [t_dict,c_char_p,c_size_t]
dict_is_in_session1.restype = c_int
def dict_is_in_session(dict,word):
    return dict_is_in_session1(dict,word,len(word))

dict_store_replacement1 = e.enchant_dict_store_replacement
dict_store_replacement1.argtypes = [t_dict,c_char_p,c_size_t,c_char_p,c_size_t]
dict_store_replacement1.restype = None
def dict_store_replacement(dict,mis,cor):
    return dict_store_replacement1(dict,mis,len(mis),cor,len(cor))

dict_free_string_list = e.enchant_dict_free_string_list
dict_free_string_list.argtypes = [t_dict,POINTER(c_char_p)]
dict_free_string_list.restype = None

dict_get_error = e.enchant_dict_get_error
dict_get_error.argtypes = [t_dict]
dict_get_error.restype = c_char_p

dict_describe1 = e.enchant_dict_describe
dict_describe1.argtypes = [t_dict,t_dict_desc_func,c_void_p]
dict_describe1.restype = None
def dict_describe(dict,cbfunc):
    def cbfunc1(*args):
        cbfunc(*args[:-1])
    dict_describe1(dict,t_dict_desc_func(cbfunc1),None)

broker_list_dicts1 = e.enchant_broker_list_dicts
broker_list_dicts1.argtypes = [t_broker,t_dict_desc_func,c_void_p]
broker_list_dicts1.restype = None
def broker_list_dicts(broker,cbfunc):
    def cbfunc1(*args):
        cbfunc(*args[:-1])
    broker_list_dicts1(broker,t_dict_desc_func(cbfunc1),None)




#  -------------------- From __init__ module --------------------

# Define Error class before imports, so it is available for import
# by enchant subpackages with circular dependencies
class Error(Exception):
    """Base exception class for the enchant module."""
    pass

class DictNotFoundError(Error):
    """Exception raised when a requested dictionary could not be found."""
    pass

class ProviderDesc:
    """Simple class describing an Enchant provider.
    Each provider has the following information associated with it:

        * name:        Internal provider name (e.g. "aspell")
        * desc:        Human-readable description (e.g. "Aspell Provider")
        * file:        Location of the library containing the provider

    """

    def __init__(self,name,desc,file):
        self.name = name
        self.desc = desc
        self.file = file

    def __str__(self):
        return "<Enchant: %s>" % self.desc

    def __repr__(self):
        return str(self)

    def __eq__(self,pd):
        """Equality operator on ProviderDesc objects."""
        return (self.name == pd.name and \
                self.desc == pd.desc and \
                self.file == pd.file)
                
    def __hash__(self):
        """Hash operator on ProviderDesc objects."""
        return hash(self.name + self.desc + self.file)


class _EnchantObject:
    """Base class for enchant objects.
    
    This class implements some general functionality for interfacing with
    the '_enchant' C-library in a consistent way.  All public objects
    from the 'enchant' module are subclasses of this class.
    
    All enchant objects have an attribute '_this' which contains the
    pointer to the underlying C-library object.  The method '_check_this'
    can be called to ensure that this point is not None, raising an
    exception if it is.
    """

    def __init__(self):
        """_EnchantObject constructor."""
        self._this = None
        
    def _check_this(self,msg=None):
         """Check that self._this is set to a pointer, rather than None."""
         if msg is None:
            msg = "%s unusable: the underlying C-library object has been freed."
            msg = msg % (self.__class__.__name__,)
         if self._this is None:
            raise Error(msg)
             
    def _raise_error(self,default="Unspecified Error",eclass=Error):
         """Raise an exception based on available error messages.
         This method causes an Error to be raised.  Subclasses should
         override it to retreive an error indication from the underlying
         API if possible.  If such a message cannot be retreived, the
         argument value <default> is used.  The class of the exception
         can be specified using the argument <eclass>
         """
         raise eclass(default)



class Broker(_EnchantObject):
    """Broker object for the Enchant spellchecker.

    Broker objects are responsible for locating and managing dictionaries.
    Unless custom functionality is required, there is no need to use Broker
    objects directly. The 'enchant' module provides a default broker object
    so that 'Dict' objects can be created directly.

    The most important methods of this class include:

        * dict_exists:   check existence of a specific language dictionary
        * request_dict:  obtain a dictionary for specific language
        * set_ordering:  specify which dictionaries to try for for a
                         given language.

    """

    def __init__(self):
        """Broker object constructor.
        
        This method is the constructor for the 'Broker' object.  No
        arguments are required.
        """
        _EnchantObject.__init__(self)
        self._this = broker_init()
        if not self._this:
            raise Error("Could not initialise an enchant broker.")

    def __del__(self):
        """Broker object destructor."""
        self._free()
            
    def _raise_error(self,default="Unspecified Error",eclass=Error):
        """Overrides _EnchantObject._raise_error to check broker errors."""
        err = broker_get_error(self._this)
        if err == "" or err is None:
            raise eclass(default)
        raise eclass(err)

    def _free(self):
        """Free system resource associated with a Broker object.
        
        This method can be called to free the underlying system resources
        associated with a Broker object.  It is called automatically when
        the object is garbage collected.  If called explicitly, the
        Broker and any associated Dict objects must no longer be used.
        """
        if self._this is not None:
            # Due to moving everything into one file, the destruction order
            # was changed so the following check became necessary
            if broker_free is not None:
                broker_free(self._this)
            self._this = None
            
    def request_dict(self,tag=None):
        """Request a Dict object for the language specified by <tag>.
        
        This method constructs and returns a Dict object for the
        requested language.  'tag' should be a string of the appropriate
        form for specifying a language, such as "fr" (French) or "en_AU"
        (Australian English).  The existence of a specific language can
        be tested using the 'dict_exists' method.
        
        If <tag> is not given or is None, an attempt is made to determine
        the current language in use.  If this cannot be determined, Error
        is raised.
        
        NOTE:  this method is functionally equivalent to calling the Dict()
               constructor and passing in the <broker> argument.
               
        """
        return Dict(tag,self)

    def _request_dict_data(self,tag):
        """Request raw C pointer data for a dictionary.
        This method call passes on the call to the C library, and does
        some internal bookkeeping.
        """
        self._check_this()
        tag = EnchantStr(tag)

        with _EnchantCCallLock:
            new_dict = broker_request_dict(self._this,tag.encode())

        if new_dict is None:
            eStr = "Dictionary for language '%s' could not be found"
            self._raise_error(eStr % (tag,),DictNotFoundError)
        return new_dict

    def request_pwl_dict(self,pwl):
        """Request a Dict object for a personal word list.
        
        This method behaves as 'request_dict' but rather than returning
        a dictionary for a specific language, it returns a dictionary
        referencing a personal word list.  A personal word list is a file
        of custom dictionary entries, one word per line.
        """
        self._check_this()
        pwl = EnchantStr(pwl)
        new_dict = broker_request_pwl_dict(self._this,pwl.encode())
        if new_dict is None:
            eStr = "Personal Word List file '%s' could not be loaded"
            self._raise_error(eStr % (pwl,))
        d = Dict(False)
        d._switch_this(new_dict,self)
        return d

    def _free_dict(self,dict):
        """Free memory associated with a dictionary.
        
        This method frees system resources associated with a Dict object.
        It is equivalent to calling the object's 'free' method.  Once this
        method has been called on a dictionary, it must not be used again.
        """
        self._check_this()
        broker_free_dict(self._this,dict._this)
        dict._this = None
        dict._broker = None

    def dict_exists(self,tag):
        """Check availability of a dictionary.
        
        This method checks whether there is a dictionary available for
        the language specified by 'tag'.  It returns True if a dictionary
        is available, and False otherwise.
        """
        self._check_this()
        tag = EnchantStr(tag)
        val = broker_dict_exists(self._this,tag.encode())
        return bool(val)

    def set_ordering(self,tag,ordering):
        """Set dictionary preferences for a language.
        
        The Enchant library supports the use of multiple dictionary programs
        and multiple languages.  This method specifies which dictionaries
        the broker should prefer when dealing with a given language.  'tag'
        must be an appropriate language specification and 'ordering' is a
        string listing the dictionaries in order of preference.  For example
        a valid ordering might be "aspell,myspell,ispell".
        The value of 'tag' can also be set to "*" to set a default ordering
        for all languages for which one has not been set explicitly.
        """
        self._check_this()
        tag = EnchantStr(tag)
        ordering = EnchantStr(ordering)
        broker_set_ordering(self._this,tag.encode(),ordering.encode())

    def describe(self):
        """Return list of provider descriptions.
        
        This method returns a list of descriptions of each of the
        dictionary providers available.  Each entry in the list is a 
        ProviderDesc object.
        """
        self._check_this()
        self.__describe_result = []
        broker_describe(self._this,self.__describe_callback)
        return [ ProviderDesc(*r) for r in self.__describe_result]

    def __describe_callback(self,name,desc,file):
        """Collector callback for dictionary description.
        
        This method is used as a callback into the _enchant function
        'enchant_broker_describe'.  It collects the given arguments in
        a tuple and appends them to the list '__describe_result'.
        """
        s = EnchantStr("")
        name = s.decode(name)
        desc = s.decode(desc)
        file = s.decode(file)
        self.__describe_result.append((name,desc,file))
        
    def list_dicts(self):
        """Return list of available dictionaries.
        
        This method returns a list of dictionaries available to the
        broker.  Each entry in the list is a two-tuple of the form:
            
            (tag,provider)
        
        where <tag> is the language lag for the dictionary and
        <provider> is a ProviderDesc object describing the provider
        through which that dictionary can be obtained.
        """
        self._check_this()
        self.__list_dicts_result = []
        broker_list_dicts(self._this,self.__list_dicts_callback)
        return [ (r[0],ProviderDesc(*r[1])) for r in self.__list_dicts_result]
    
    def __list_dicts_callback(self,tag,name,desc,file):
        """Collector callback for listing dictionaries.
        
        This method is used as a callback into the _enchant function
        'enchant_broker_list_dicts'.  It collects the given arguments into
        an appropriate tuple and appends them to '__list_dicts_result'.
        """
        s = EnchantStr("")
        tag = s.decode(tag)
        name = s.decode(name)
        desc = s.decode(desc)
        file = s.decode(file)
        self.__list_dicts_result.append((tag,(name,desc,file)))
 
    def list_languages(self):
        """List languages for which dictionaries are available.
        
        This function returns a list of language tags for which a
        dictionary is available.
        """
        langs = []
        for (tag,prov) in self.list_dicts():
            if tag not in langs:
                langs.append(tag)
        return langs
        
    def __describe_dict(self,dict_data):
        """Get the description tuple for a dict data object.
        <dict_data> must be a C-library pointer to an enchant dictionary.
        The return value is a tuple of the form:
                (<tag>,<name>,<desc>,<file>)
        """
        # Define local callback function
        cb_result = []
        def cb_func(tag,name,desc,file):
            s = EnchantStr("")
            tag = s.decode(tag)
            name = s.decode(name)
            desc = s.decode(desc)
            file = s.decode(file)
            cb_result.append((tag,name,desc,file))
        # Actually call the describer function
        dict_describe(dict_data,cb_func)
        return cb_result[0]
        

class Dict(_EnchantObject):
    """Dictionary object for the Enchant spellchecker.

    Dictionary objects are responsible for checking the spelling of words
    and suggesting possible corrections.  Each dictionary is owned by a
    Broker object, but unless a new Broker has explicitly been created
    then this will be the 'enchant' module default Broker and is of little
    interest.

    The important methods of this class include:

        * check():              check whether a word id spelled correctly
        * suggest():            suggest correct spellings for a word
        * add():                add a word to the user's personal dictionary
        * remove():             add a word to the user's personal exclude list
        * add_to_session():     add a word to the current spellcheck session
        * store_replacement():  indicate a replacement for a given word

    Information about the dictionary is available using the following
    attributes:

        * tag:        the language tag of the dictionary
        * provider:   a ProviderDesc object for the dictionary provider
    
    """

    def __init__(self,tag=None,broker=None):
        """Dict object constructor.
        
        A dictionary belongs to a specific language, identified by the
        string <tag>.  If the tag is not given or is None, an attempt to
        determine the language currently in use is made using the 'locale'
        module.  If the current language cannot be determined, Error is raised.

        If <tag> is instead given the value of False, a 'dead' Dict object
        is created without any reference to a language.  This is typically
        only useful within PyEnchant itself.  Any other non-string value
        for <tag> raises Error.
        
        Each dictionary must also have an associated Broker object which
        obtains the dictionary information from the underlying system. This
        may be specified using <broker>.  If not given, the default broker
        is used.
        """
        # Superclass initialisation
        _EnchantObject.__init__(self)
        # Initialise object attributes to None
        self._broker = None
        self.tag = None
        self.provider = None
        # Create dead object if False was given
        if tag is False:
            self._this = None
        else:
            if tag is None:
                tag = "No tag specified."
                raise Error("No tag specified.")
            # Use module-level broker if none given
            if broker is None:
                broker = _broker
            # Use the broker to get C-library pointer data
            self._switch_this(broker._request_dict_data(tag),broker)

    def __del__(self):
        """Dict object destructor."""
        # Calling free() might fail if python is shutting down
        try:
            self._free()
        except AttributeError:
            pass
            
    def _switch_this(self,this,broker):
        """Switch the underlying C-library pointer for this object.
        
        As all useful state for a Dict is stored by the underlying C-library
        pointer, it is very convenient to allow this to be switched at
        run-time.  Pass a new dict data object into this method to affect
        the necessary changes.  The creating Broker object (at the Python
        level) must also be provided.
                
        This should *never* *ever* be used by application code.  It's
        a convenience for developers only, replacing the clunkier <data>
        parameter to __init__ from earlier versions.
        """
        # Free old dict data
        Dict._free(self)
        # Hook in the new stuff
        self._this = this
        self._broker = broker
        # Update object properties
        desc = self.__describe(check_this=False)
        self.tag = desc[0]
        self.provider = ProviderDesc(*desc[1:])

    def _check_this(self,msg=None):
        """Extend _EnchantObject._check_this() to check Broker validity.
        
        It is possible for the managing Broker object to be freed without
        freeing the Dict.  Thus validity checking must take into account
        self._broker._this as well as self._this.
        """
        if self._broker is None or self._broker._this is None:
            self._this = None
        _EnchantObject._check_this(self,msg)

    def _raise_error(self,default="Unspecified Error",eclass=Error):
        """Overrides _EnchantObject._raise_error to check dict errors."""
        err = dict_get_error(self._this)
        if err == "" or err is None:
            raise eclass(default)
        raise eclass(err)

    def _free(self):
        """Free the system resources associated with a Dict object.
        
        This method frees underlying system resources for a Dict object.
        Once it has been called, the Dict object must no longer be used.
        It is called automatically when the object is garbage collected.
        """
        if self._broker is not None:
            self._broker._free_dict(self)

    def check(self,word):
        """Check spelling of a word.
        
        This method takes a word in the dictionary language and returns
        True if it is correctly spelled, and false otherwise.
        """
        self._check_this()
        word = EnchantStr(word)
        val = dict_check(self._this,word.encode())
        if val == 0:
            return True
        if val > 0:
            return False
        self._raise_error()

    def suggest(self,word):
        """Suggest possible spellings for a word.
        
        This method tries to guess the correct spelling for a given
        word, returning the possibilities in a list.
        """
        self._check_this()
        word = EnchantStr(word)
        suggs = dict_suggest(self._this,word.encode())
        return [word.decode(w) for w in suggs]

    def add(self,word):
        """Add a word to the user's personal word list."""
        self._check_this()
        word = EnchantStr(word)
        dict_add(self._this,word.encode())

    def remove(self,word):
        """Add a word to the user's personal exclude list."""
        self._check_this()
        word = EnchantStr(word)
        dict_remove(self._this,word.encode())

    def add_to_session(self,word):
        """Add a word to the session personal list."""
        self._check_this()
        word = EnchantStr(word)
        dict_add_to_session(self._this,word.encode())

    def remove_from_session(self,word):
        """Add a word to the session exclude list."""
        self._check_this()
        word = EnchantStr(word)
        dict_remove_from_session(self._this,word.encode())

    def is_added(self,word):
        """Check whether a word is in the personal word list."""
        self._check_this()
        word = EnchantStr(word)
        return dict_is_added(self._this,word.encode())

    def is_removed(self,word):
        """Check whether a word is in the personal exclude list."""
        self._check_this()
        word = EnchantStr(word)
        return dict_is_removed(self._this,word.encode())

    def store_replacement(self,mis,cor):
        """Store a replacement spelling for a miss-spelled word.
        
        This method makes a suggestion to the spellchecking engine that the 
        miss-spelled word <mis> is in fact correctly spelled as <cor>.  Such
        a suggestion will typically mean that <cor> appears early in the
        list of suggested spellings offered for later instances of <mis>.
        """
        self._check_this()
        mis = EnchantStr(mis)
        cor = EnchantStr(cor)
        dict_store_replacement(self._this,mis.encode(),cor.encode())

    def __describe(self,check_this=True):
        """Return a tuple describing the dictionary.
        
        This method returns a four-element tuple describing the underlying
        spellchecker system providing the dictionary.  It will contain the
        following strings:

            * language tag
            * name of dictionary provider
            * description of dictionary provider
            * dictionary file

        Direct use of this method is not recommended - instead, access this
        information through the 'tag' and 'provider' attributes.
        """
        if check_this:
            self._check_this()
        dict_describe(self._this,self.__describe_callback)
        return self.__describe_result

    def __describe_callback(self,tag,name,desc,file):
        """Collector callback for dictionary description.
        
        This method is used as a callback into the _enchant function
        'enchant_dict_describe'.  It collects the given arguments in
        a tuple and stores them in the attribute '__describe_result'.
        """
        s = EnchantStr("")
        tag = s.decode(tag)
        name = s.decode(name)
        desc = s.decode(desc)
        file = s.decode(file)
        self.__describe_result = (tag,name,desc,file)




##  Create a module-level default broker object, and make its important
##  methods available at the module level.
_broker = Broker()
request_dict = _broker.request_dict
request_pwl_dict = _broker.request_pwl_dict
dict_exists = _broker.dict_exists
list_dicts = _broker.list_dicts
list_languages = _broker.list_languages








