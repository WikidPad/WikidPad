# Based on code from sre_compile.py in the Python standard library
# which has the following copyright:



# Secret Labs' Regular Expression Engine
#
# re-compatible interface for the sre matching engine
#
# Copyright (c) 1998-2001 by Secret Labs AB.  All rights reserved.
#
# This version of the SRE library can be redistributed under CNRI's
# Python 1.6 license.  For any other use, please contact Secret Labs
# AB (info@pythonware.com).
#
# Portions of this engine have been developed in cooperation with
# CNRI.  Hewlett-Packard provided funding for 1.6 integration and
# other compatibility work.
#

from sre_compile import *
from sre_compile import _code

import sre
sub = sre.sub

import _sre

import cPickle as pickle

# flags
I = IGNORECASE = SRE_FLAG_IGNORECASE # ignore case
L = LOCALE = SRE_FLAG_LOCALE # assume current 8-bit locale
U = UNICODE = SRE_FLAG_UNICODE # assume unicode locale
M = MULTILINE = SRE_FLAG_MULTILINE # make anchors look for newline
S = DOTALL = SRE_FLAG_DOTALL # make dot match newline
X = VERBOSE = SRE_FLAG_VERBOSE # ignore whitespace and comments


_code_cache = {}
_code_cache_dirty = False


# try:
#     import srePersistentCache
#     _code_cache = srePersistentCache.data
# except:
#     print "sre except1"
#     pass


# TODO Check date
def loadCodeCache():
    global _code_cache
    try:
#        print "loadCodeCache1"
        fp = open("regexpr.cache", "rb")
        cache = pickle.load(fp)
        fp.close()
        _code_cache = cache
#        print "loadCodeCache2", len(_code_cache), repr(_code_cache.keys())

    except:
        pass

def saveCodeCache():
    global _code_cache, _code_cache_dirty
    
    if not _code_cache_dirty:
        return

    try:
        fp = open("regexpr.cache", "wb")
        pickle.dump(_code_cache, fp, pickle.HIGHEST_PROTOCOL)
        fp.close()
    except:
        pass


# def saveCodeCache():
#     global _code_cache, _code_cache_dirty
#     print "saveCodeCache1"
#     if not _code_cache_dirty:
#         return
#         
#     try:
#         print "saveCodeCache2"
#         fp = open("srePersistentCache.py", "w")
#         fp.write("data = ")
#         fp.write(repr(_code_cache))
#         fp.close()
#         print "saveCodeCache5"
#     except:
#         pass
    


def compile(p, flags=0):
    global _code_cache, _code_cache_dirty
    # internal: convert pattern list to internal format
    
    cachekey = (p, flags)   # type(p),
#    print "compile1", _code_cache.has_key(cachekey)
    pp, code = _code_cache.get(cachekey, (None, None))
#    print "compile3", repr(cachekey), repr((pp, code))

    if code is None:
#         print "compile2", repr(p)[:70]

        if isstring(p):
            import sre_parse
            pattern = p
            pp = sre_parse.parse(p, flags)
        else:
            # TODO Error
            pattern = None
            pp = p
 
        code = _code(pp, flags)
    
        # print code
    
        assert pp.pattern.groups <= 100,\
               "sorry, but this version only supports 100 named groups"

        _code_cache[cachekey] = (pp, code)
        _code_cache_dirty = True

    # map in either direction
    groupindex = pp.pattern.groupdict
    indexgroup = [None] * pp.pattern.groups
    for k, i in groupindex.items():
        indexgroup[i] = k

    return _sre.compile(
        p, flags, code,
        pp.pattern.groups-1,
        groupindex, indexgroup
        )
