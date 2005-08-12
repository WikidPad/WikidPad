#! /usr/local/bin/python -O

# A simple implementation of the relational algebra
#  using kjbuckets
from kjbuckets import *

def relFromDictSet(schemeseq, dictSet):
    result = relation(schemeseq, [] )
    result.rowset = dictSet
    return result

class relation:

    def __init__(self, schemeseq, listofrows):
        self.schemeseq = schemeseq
        self.scheme = kjSet(schemeseq)
        rowset = kjSet()
        for row in listofrows:
            rowset.add(kjUndump(schemeseq, row))
        self.rowset = rowset

    def pprint(self):
        print self.schemeseq
        print "============"
        for row in self.rowset.items():
            print row.dump(self.schemeseq)

    def addDicts(self, dictseq): # not used...
        for dict in dictseq:
            self.rowset.add(dict)

    def checkUnionCompatible(self,other):
        if self.scheme != other.scheme:
            raise ValueError, "operands not union compatible"

    # relational union
    def __add__(self, other):
        self.checkUnionCompatible(other)
        return relFromDictSet(self.schemeseq, self.rowset + other.rowset)

    # relational difference
    def __sub__(self, other):
        self.checkUnionCompatible(other)
        return relFromDictSet(self.schemeseq, self.rowset - other.rowset)

    # natural join (hash based algorithm)
    def __mul__(self,other):
        commonatts = self.scheme & other.scheme
        resultset = kjSet()
        if commonatts: # do a hash based join
            dumper = tuple(commonatts.items())
            selfgraph = kjGraph() # hash index for self
            othergraph = kjGraph() # hash index for other
            for row in self.rowset.items():
                selfgraph[row] = row.dump(dumper)
            for row in other.rowset.items():
                othergraph[row.dump(dumper)] = row
            for (selfrow, otherrow) in (selfgraph * othergraph).items():
                resultset.add(selfrow + otherrow)
        else: # no common attributes: do a cross product
            otherrows = other.rowset.items()
            for selfrow in self.rowset.items():
                for otherrow in otherrows:
                    resultset.add(selfrow + otherrow)
        return relFromDictSet( tuple((self.scheme + other.scheme).items()),
                               resultset )

# selection using a att->value pairs (as conjunction)
def vSel(pairs, rel):
    selected = kjSet()
    selector = kjDict(pairs)
    if selector.Clean()!=None:
        for row in rel.rowset.items():
            if (row + selector).Clean() != None:
                selected.add(row)
    return relFromDictSet(rel.schemeseq, selected)

# selection using att = att pairs (as conjunction)
def eqSelect(pairs, rel):
    selected = kjSet()
    selector = kjGraph(pairs)
    selector = (selector + ~selector).tclosure() # sym, trans closure
    for row in rel.rowset.items():
        if row.remap(selector) != None:
            selected.add(row)
    return relFromDictSet(rel.schemeseq, selected)

# projection on attribute sequence (as conjunction)
def proj(atts, rel):
    attset = kjSet(atts)
    resultset = kjSet()
    for row in rel.rowset.items():
        resultset.add(attset * row)
    return relFromDictSet(atts, resultset)

# renaming using (new,old) pair sequence
def rename(pairs, rel):
    renames = kjDict(pairs)
    untouched = rel.scheme - kjSet(renames.values())
    mapper = renames + untouched
    resultset = kjSet()
    for row in rel.rowset.items():
        resultset.add(mapper * row)
    return relFromDictSet(tuple(mapper.keys()), resultset)

#=========== end of simple.py
#
#Now let me show you the "simple" module in use.  First we need some relations.
#I'll steal C.J.Date's canonical/soporific supplier/parts database:
#
## database of suppliers, parts and shipments
##  from Date, page 79 (2nd ed) or page 92 (3rd ed) */
def test():
    #suppliers
    S = relation(
       ('snum', 'sname', 'status', 'city'),
       [ (1,   'Smith', 20,     'London'),
         (2,   'Jones', 10,     'Paris'),
         (3,   'Blake', 30,     'Paris'),
         (4,   'Clark', 20,     'London'),
         (5,   'Adams', 30,     'Athens')
       ])
    #parts
    P = relation(
       ('pnum', 'pname', 'color', 'weight', 'pcity'),
       [ (1,   'Nut',   'Red',   12,     'London'),
         (2,   'Bolt',  'Green', 17,     'Paris' ),
         (3,   'Screw', 'Blue',  17,     'Rome'  ),
         (4,   'Screw', 'Red',   14,     'London'),
         (5,   'Cam',   'Blue',  12,     'Paris'),
         (6,   'Cog',   'Red',   19,     'London')
       ])
    # shipments
    SP = relation(
       ('snum', 'pnum', 'qty',),
       [ (1,   1,   300),
         (1,   2,   200),
         (1,   3,   400),
         (1,   4,   200),
         (1,   5,   100),
         (1,   6,   100),
         (2,   1,   300),
         (2,   2,   400),
         (3,   2,   200),
         (4,   2,   200),
         (4,   4,   300),
         (4,   5,   400)
       ])

    # names and cities of suppliers
    proj(("sname","city"),S).pprint()

    # part names of parts supplied by Blake
    proj(("pname",),vSel( ( ("sname","Blake"), ), S*SP*P)).pprint()


    # supplier names and numbers where the supplier doesn't supply screws
    ( proj( ("sname","snum"), S) -
       proj( ("sname","snum"),
             vSel( ( ("pname", "Screw"), ), P*SP*S )
     ) ).pprint()


if __name__=="__main__":
    test()
