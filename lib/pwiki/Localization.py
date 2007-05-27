import string, locale, sets

from StringOps import utf8Enc


CASEMODE_UPPER_INSIDE = 0   # Sort upper case inside like aAbBcC
CASEMODE_UPPER_FIRST = 1    # Sort upper case first like ABCabc

def tt(s):
    """
    Currently only dummy: Lookup text in message table and return
    localized message
    """
    return s


def tt_noop(s):
    return s


# Factory functions for collators. Classes shouldn't be called directly

def getCollatorByString(locStr, caseMode=None):
    """
    locStr -- String describing the locale of the Collator
    caseMode --  (the flag isn't
            guaranteed to be respected
    """
    if locStr.lower() == u"c":
        return _CCollator(caseMode)
    else:
        if locStr.lower() == u"default":
            locStr = u""

        if caseMode == CASEMODE_UPPER_FIRST:
            return _PythonCollatorUppercaseFirst(locStr)
        else:
            return _PythonCollator(locStr)


def getCCollator(caseMode=None):
    """
    Returns a basic collator for 'C' locale. The only collator guaranteed to
    exist.
    caseMode -- True iff collator should be case sensitive (the flag isn't
            guaranteed to be respected
    """
    return _CCollator(caseMode)



class AbstractCollator:
    """
    Abstract base class for collator functionality.

    All string parameters to the methods must (or should at least) be
    unicode strings.
    """

    def sort(self, lst, ascend=True):
        """
        Sort list lst of unicode strings inplace alphabetically
        (as defined by strcoll() method).

        ascend -- If True sort ascending, descending otherwise
        """
        lst.sort(self.strcoll)
        if not ascend:
            lst.reverse()

    def sortByKey(self, lst, ascend=True):
        """
        Similar to sort(), but lst items are sequences where only the first
        element is taken for sorting.
        """
        lst.sort(self.strcollByKey)
        if not ascend:
            lst.reverse()


    def strcoll(self, left, right):
        """
        Compare strings left and right and return integer value smaller, greater or
        equal 0 following the same rules as the built-in cmp() function
        """
        raise NotImplementedError   # abstract


    def strcollByKey(self, left, right):
        """
        Compare tuples left and right (first elements only) and return integer
        value smaller, greater or equal 0 following the same rules as the
        built-in cmp() function.
        """
        return self.strcoll(left[0], right[0])


    def strxfrm(self, s):
        """
        Returns a byte string usable as byte sort key for string s. It must
        fulfill the condition:
        
        For all unicode strings a, b:
        cmp(strxfrm(a), strxfrm(b)) == strcoll(a, b)
        """
        raise NotImplementedError   # abstract

#     def normCase(self, s):
#         """
#         Normalize case for string s. It is recommended to just return
#         the UTF-8 encoding of the "lowered" string s. This should be even
#         true if the collator is case-sensitive.
#         
#         The collator must fulfill:
#         For all unicode strings a, b:
#         
#         1. normCase(a) == normCase(b) iff a == b or a is equal b except for case.
#         2. normCase(a) is part of normCase(b) iff a is part of b (at least if
#             case is ignored)
#         
#         """
#         assert 0  # abstract


# TODO case insensitivity

class _CCollator(AbstractCollator):
    """
    Collator for case sensitive "C" locale
    """
    def __init__(self, caseMode):
        self.caseMode = caseMode


    def sort(self, lst, ascend=True):
        """
        Sort list lst inplace.
        ascend -- If True sort ascending, descending otherwise
        """
        lst.sort()
        if not ascend:
            lst.reverse()
            
    def strcoll(self, left, right):
        """
        Compare left and right and return integer value smaller, greater or
        equal 0
        """
        return cmp(left, right)

    def strxfrm(self, s):
        """
        Returns a byte string usable as byte sort key for string s
        """
        return utf8Enc(s)[0]


#     def normCase(self, s):
#         """
#         Normalize case for unicode string s and return byte string
#         """
#         result = []
#         for c in s:
#             o = ord(c)
#             if o < 65 or o > 90:
#                 result.append(c)
#             else:
#                 result.append(unichr(o+32))
# 
#         return utf8Enc(u"".join(result))[0]
        



class _PythonCollator(AbstractCollator):
    """
    Uses Python's localization support from the "locale" module.
    This class pretends to allow the use of multiple locale settings
    at once, but Python doesn't provide that.
    """
    def __init__(self, locStr):
        """
        """
        self.locStr = locStr
        self.prevLocale = locale.setlocale(locale.LC_ALL, self.locStr)

    def strcoll(self, left, right):
        return locale.strcoll(left, right)
        
    def strxfrm(self, s):
        return locale.strxfrm(s)

#     def normCase(self, s):
#         return utf8Enc(s.lower)[0]


class _PythonCollatorUppercaseFirst(AbstractCollator):
    """
    Uses Python's localization support from the "locale" module.
    This class pretends to allow the use of multiple locale settings
    at once, but Python doesn't provide that.
    """
    def __init__(self, locStr):
        """
        caseMode -- ignored here
        """
        self.locStr = locStr
        self.prevLocale = locale.setlocale(locale.LC_ALL, self.locStr)

    def strcoll(self, left, right):
        ml = min(len(left), len(right))
        for i in xrange(ml):
            lv = 0
            if left[i].islower():
                lv = 1
    
            rv = 0
            if right[i].islower():
                rv = 1
                
            comp = lv - rv
            
            if comp != 0:
                return comp
    
            comp = locale.strcoll(left[i].lower(), right[i].lower())
            if comp != 0:
                return comp
            
        if len(right) > ml:
            return 1
        if len(left) > ml:
            return -1
            
        return 0

        
    def strxfrm(self, s):
        assert 0 # Not properly implemented

        return locale.strxfrm(s)



