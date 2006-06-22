import string, locale, sets

from StringOps import utf8Enc


# Factory functions for collators, classes shouldn't be called directly

def createCollatorByString(locStr, caseSensitive):
    """
    locStr -- String describing the locale of the Collator
    caseSensitive -- True iff collator should be case sensitive (the flag isn't
            guaranteed to be respected
    """
    return _PythonCollator(locStr, caseSensitive)


def createCCollator(caseSensitive):
    """
    Returns a basic collator for 'C' locale. The only collator guaranteed to
    exist.
    caseSensitive -- True iff collator should be case sensitive (the flag isn't
            guaranteed to be respected
    """
    return _CCollator(caseSensitive)



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

    def strcoll(self, left, right):
        """
        Compare strings left and right and return integer value smaller, greater or
        equal 0 following the same rules as the built-in cmp() function
        """
        assert 0  # abstract

    def strxfrm(self, s):
        """
        Returns a byte string usable as byte sort key for string s. It must
        fulfill the condition:
        
        For all unicode strings a, b:
        cmp(strxfrm(a), strxfrm(b)) == strcoll(a, b)
        """
        assert 0  # abstract

    def normCase(self, s):
        """
        Normalize case for string s. If the collator is case sensitive, this
        should just return the UTF-8 encoded string.
        
        If collator is case insensitive, it must fulfill:
        For all unicode strings a, b:
        
        1. normCase(a) == normCase(b) iff a == b or a is equal b except for case.
        2. normCase(a) is part of normCase(b) iff a is part of b (at least if
            case is ignored)
            
        It is recommended to just return the UTF-8 encoding of the "lowered"
        string s.
        """
        assert 0  # abstract


# TODO case insensitivity


class _CCollator(AbstractCollator):
    """
    Collator for case sensitive "C" locale
    """
    def __init__(self, caseSensitive):
        self.caseSensitive = caseSensitive


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


    def normCase(self, s):
        """
        Normalize case for string s if collator case-insensitive
        """
        return utf8Enc(s)[0]
        



class _PythonCollator(AbstractCollator):
    """
    Uses Python's localization support from the "locale" module.
    This class pretends to allow the use of multiple locale settings
    at once, but Python doesn't allow that.
    """
    def __init__(self, loc, caseSensitive):
        self.locCode = loc
        self.prevLocale = locale.setlocale(locale.LC_ALL, self.locCode)
        
        self.caseSensitive = caseSensitive

    def strcoll(self, left, right):
        locale.strcoll(left, right)
        
    def strxfrm(self, s):
        locale.strxfrm(s)



