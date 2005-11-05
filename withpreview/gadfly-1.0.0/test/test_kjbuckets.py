# $Id: test_kjbuckets.py,v 1.4 2002/05/08 00:49:01 anthonybaxter Exp $

import unittest

# a simple test for kjbuckets0 stolen from relalg.py in the kjbuckets C
# module distro

# A simple implementation of the relational algebra using kjbuckets

def relFromDictSet(schemeseq, dictSet):
    result = relation(schemeseq, [] )
    result.rowset = dictSet
    return result

class relation:
    def __init__(self, schemeseq, listofrows):
        self.schemeseq = schemeseq
        self.scheme = kjbuckets_module.kjSet(schemeseq)
        rowset = kjbuckets_module.kjSet()
        for row in listofrows:
            rowset.add(kjbuckets_module.kjUndump(schemeseq, row))
        self.rowset = rowset

    def result(self):
        l = []
        for row in self.rowset.items():
            l.append(row.dump(self.schemeseq))
        return l

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
        resultset = kjbuckets_module.kjSet()
        if commonatts: # do a hash based join
            dumper = tuple(commonatts.items())
            selfgraph = kjbuckets_module.kjGraph() # hash index for self
            othergraph = kjbuckets_module.kjGraph() # hash index for other
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
    selected = kjbuckets_module.kjSet()
    selector = kjbuckets_module.kjDict(pairs)
    if selector.Clean()!=None:
        for row in rel.rowset.items():
            if (row + selector).Clean() != None:
                selected.add(row)
    return relFromDictSet(rel.schemeseq, selected)

# selection using att = att pairs (as conjunction)
def eqSelect(pairs, rel):
    selected = kjbuckets_module.kjSet()
    selector = kjbuckets_module.kjGraph(pairs)
    selector = (selector + ~selector).tclosure() # sym, trans closure
    for row in rel.rowset.items():
        if row.remap(selector) != None:
            selected.add(row)
    return relFromDictSet(rel.schemeseq, selected)

# projection on attribute sequence (as conjunction)
def proj(atts, rel):
    attset = kjbuckets_module.kjSet(atts)
    resultset = kjbuckets_module.kjSet()
    for row in rel.rowset.items():
        resultset.add(attset * row)
    return relFromDictSet(atts, resultset)

# renaming using (new,old) pair sequence
def rename(pairs, rel):
    renames = kjbuckets_module.kjDict(pairs)
    untouched = rel.scheme - kjbuckets_module.kjSet(renames.values())
    mapper = renames + untouched
    resultset = kjbuckets_module.kjSet()
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
class test_kjbuckets0(unittest.TestCase):
    def setUp(self):
        global kjbuckets_module
        import gadfly.kjbuckets0 as kjbuckets_module

    def test(self):
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
        l = proj(("sname","city"),S).result()
        l.sort()
        self.assertEquals(l, [('Adams', 'Athens'), ('Blake', 'Paris'),
             ('Clark', 'London'), ('Jones', 'Paris'), ('Smith', 'London')])

        # part names of parts supplied by Blake
        self.assertEquals(proj(("pname",),vSel( ( ("sname","Blake"), ),
             S*SP*P)).result(), ['Bolt'])

        # supplier names and numbers where the supplier doesn't supply screws
        l = (proj(("sname","snum"), S) -
             proj(("sname","snum"), vSel((("pname", "Screw"),), P*SP*S))
            ).result()
        l.sort()
        self.assertEquals(l, [('Adams', 5), ('Blake', 3), ('Jones', 2)])


    def test2(self):
        G = kjbuckets_module.kjGraph()
        r3 = range(3)
        r = map(None, r3, r3)
        for i in range(3):
            G[i] = i+1
        D = kjbuckets_module.kjDict(G)
        D[9]=0
        G[0]=10
        S = kjbuckets_module.kjSet(G)
        S[-1] = 5
        #print "%s.remap(%s) = %s" % (D, G, D.remap(G))
        for X in (S, D, G, r, tuple(r), 1):
            for C in (kjbuckets_module.kjGraph, kjbuckets_module.kjSet,
                    kjbuckets_module.kjDict):
                T = C(X)
                T2 = C()
        ALL = (S, D, G)
        for X in ALL:
            self.assertEqual(len(X), len(X.items()))
            cb = X.Clean()
            del X[2]
            self.assertNotEqual(cb, X.Clean() or [])
            self.assert_(X.subset(X), "trivial subset fails")
            self.assert_(X==X, "trivial cmp fails")
            self.assert_(not not X, "nonzero fails")
            if X is S:
                self.assert_(S.member(0), "huh 1?")
                self.assert_(not S.member(123), "huh 2?")
                S.add(999)
                del S[1]
                self.assert_(S.has_key(999), "huh 3?")
            else:
                self.assertNotEqual(X, ~X, "inverted")
                self.assert_(X.member(0,1), "member test fails (0,1)")
                X.add(999,888)
                X.delete_arc(999,888)
                self.assert_(not X.member(999,888),
                    "member test fails (999,888)")
                self.assert_(not X.has_key(999), "has_key fails 999")
                self.assert_(X.has_key(0), "has_key fails 0")
            for Y in ALL:
                #if (X!=S and Y!=S):
                #   print "diff", X, Y
                #   print "%s-%s=%s" % (X,Y,X-Y)
                #elif X==S:
                #   D = kjbuckets_module.kjSet(Y)
                #   print "diff", X, D
                #   print "%s-%s=%s" % (X,D,X-D)
                #print "%s+%s=%s" % (X,Y,X+Y)
                #print "%s&%s=%s" % (X,Y,X&Y)
                #print "%s*%s=%s" % (X,Y,X*Y)
                x,y = cmp(X,Y), cmp(Y,X)
                self.assertEqual(x, -y, "bad cmp!")
                #print "cmp(X,Y), -cmp(Y,X)", x,-y
                #print "X.subset(Y)", X.subset(Y)

class test_kjbuckets(unittest.TestCase):
    def setUp(self):
        global kjbuckets_module
        import kjbuckets as kjbuckets_module

def suite():
    l = [
        unittest.makeSuite(test_kjbuckets0),
    ]
    try:
        import kjbuckets
        l.append(unittest.makeSuite(test_kjbuckets))
    except ImportError:
        print 'not running kjbuckets C module test'
        pass

    return unittest.TestSuite(l)

if __name__ == '__main__':
    runner = unittest.TextTestRunner()
    runner.run(suite())

#
# $Log: test_kjbuckets.py,v $
# Revision 1.4  2002/05/08 00:49:01  anthonybaxter
# El Grande Grande reindente! Ran reindent.py over the whole thing.
# Gosh, what a lot of checkins. Tests still pass with 2.1 and 2.2.
#
# Revision 1.3  2002/05/07 04:03:14  richard
# . major cleanup of test_gadfly
#
# Revision 1.2  2002/05/06 23:27:10  richard
# . made the installation docco easier to find
# . fixed a "select *" test - column ordering is different for py 2.2
# . some cleanup in gadfly/kjParseBuild.py
# . made the test modules runnable (remembering that run_tests can take a
#   name argument to run a single module)
# . fixed the module name in gadfly/kjParser.py
#
#
