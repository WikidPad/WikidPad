#! /usr/local/bin/python -O

"""Trigram indexing of documents.
  T = TriGram()
 makes a trigram archive.
 Add *HASHABLE* documents to the archive, associated with keywords by
  T.add_doc(document, [keyword1, keyword2, ...])
 Get documents that for each substring are associated with a keyword
  containing that substring with T.getDocs([substring1, substring2,...])
  (returns kjSet) OR
  T.getDocList([keyword1, keyword2,...]) returns list.
 if you can't hash your documents use some aliasing strategy...

 performance should be "good" when the graphs are sparse, but may
 get bad if graphs get extremely dense...
"""

### note: this is in the process of improvement ###
### need to vector docs to numbers to save space on loading ###

from kjbuckets import *
from string import upper, find

# note: documents must be hashable!

class TriGram:

    def __init__(self):
        self._trigramtokeyword = kjGraph()
        self._keywordtodoc = kjGraph()
        self._tricache = kjDict() # memory optimization

    def keys(self):
        return self._keywordtodoc.keys()

    def trigrams(self):
        return self._trigramtokeyword.keys()

    def marshal_to_file(self, file):
        from kjfactor import factor
        from marshal import dump
        dump( (factor(self._trigramtokeyword), factor(self._keywordtodoc)),
              file )

    def unmarshal_from_file(self, file):
        from marshal import load
        from kjfactor import unfactor
        (ttkf, kwdf) = load(file)
        self._trigramtokeyword = apply(unfactor, ttkf)
        self._keywordtodoc = apply(unfactor, kwdf)

    # associate document to all keywords in keyword_list
    def add_doc(self, document, keyword_list):
        for keyword in keyword_list:
            keyword = upper(keyword)
            self._addlink(keyword, document)

    # associate keyword to document, assumes keyword upcased
    def _addlink(self, keyword, document):
        cache = self._tricache
        ntrigrams = len(keyword) - 2
        if ntrigrams<1:
            #raise ValueError, "keyword must be length 3 or greater"
            return # ignore
        for start in range(ntrigrams):
            trigram = keyword[start: start+3]
            try:
                trigram = cache[trigram]
            except:
                cache[trigram]=trigram
            self._trigramtokeyword[trigram] = keyword
            self._keywordtodoc[keyword] = document

    # get set of keywords associated with a substring, assumes substring upcased
    def _getkeywords(self, substring):
        TtoK = self._trigramtokeyword
        ntrigrams = len(substring) - 2
        if ntrigrams<1:
            raise ValueError, \
              "substring must be length 3 or greater:" +`substring`
        keywords = None
        for start in range(ntrigrams):
            trigram = substring[start: start+3]
            thesekeywords = kjSet( TtoK.neighbors(trigram) )
            if keywords == None:
                keywords = thesekeywords
            else:
                keywords = keywords & thesekeywords
            if not keywords: break
        # now check for false hits (trigrams in wrong order...)
        for keyword in keywords.items():
            if find(keyword, substring)==-1:
                del keywords[keyword]
        return keywords

    # get kjSet of documents
    #  which for each substring of substring_list
    #  is associated with a keyword containing that substring.
    # (for boolean queries, left as set for easy combination...)
    def getDocs(self, substring_list):
        DocSet = None
        kwToDoc = self._keywordtodoc
        for substring in substring_list:
            substring = upper(substring)
            keywords = self._getkeywords(substring)
            thesedocs = kjSet((keywords * kwToDoc).values())
            if DocSet == None:
                DocSet = thesedocs
            else:
                DocSet = thesedocs & DocSet
            if not DocSet: break
        return DocSet

    # same as above, but returns list not set.
    def getDocList(self, substring_list):
        return self.getDocs(substring_list).items()

if __name__=="__main__":
    #### example usage and for testing
    bigstring = """
    Python release 1.1.1
    ====================
    ==> This is Python version 1.1.1.
    ==> Python 1.1.1 is a pure bugfix release.  It fixes two core dumps
        related to the changed implementation of (new)getargs, some
        portability bugs, and some very minor things here and there.  If
        you have 1.1, you only need to install 1.1 if bugs in it are
        bugging you.
    ==> If you don't know yet what Python is: it's an interpreted,
        extensible, embeddable, interactive, object-oriented programming
        language.  For a quick summary of what Python can mean for a
        UNIX/C programmer, read Misc/BLURB.LUTZ.
    ==> If you want to start compiling right away (on UNIX): just type
        "./configure" in the current directory and when it finishes, type
        "make".  See the section Build Instructions below for more
        details.
    ==> All documentation is in the subdirectory Doc in the form of LaTeX
        files.  In order of importance for new users: Tutorial (tut),
        Library Reference (lib), Language Reference (ref), Extending
        (ext).  Note that especially the Library Reference is of immense
        value since much of Python's power (including the built-in data
        types and functions!) is described there.  [NB The ext document
        has not been updated to reflect this release yet.] ....
    --Guido van Rossum, CWI, Amsterdam <Guido.van.Rossum@cwi.nl>
    <URL:http://www.cwi.nl/cwi/people/Guido.van.Rossum.html>"""

    import string
    bigsplit = string.split(bigstring)
    print "testing loading"
    TGram = TriGram()
    # associate each string of bigstring to itself, unless too small...
    for str in bigsplit:
        if len(str)>3:
            TGram.add_doc(str, [str])
    print len(TGram._trigramtokeyword), len(TGram._keywordtodoc)
    print "testing marshalling"
    f = open("test.mar", "wb")
    TGram.marshal_to_file(f)
    f.close()
    f = open("test.mar", "rb")
    TGram = TriGram()
    TGram.unmarshal_from_file(f)
    f.close()
    print "testing retrieval"
    print TGram.getDocList(["thon"])
    print TGram.getDocList(["tion"])
    print TGram.getDocList(["dire"])
    print TGram.getDocList(["here"])
    print TGram.getDocList(["ers","sio"])
    print TGram.getDocList(["int","era"])
    print TGram.getDocList(["htt","url","van"])
    print TGram.getDocList(["Nope"])
