#! /usr/local/bin/python -O

# factor a graph G on A x B into
# a lists L and list of pairs G2 on int x int
# such that (a,b) in G iff (i,j) in G2 where L[i], L[j] == a,b
#
#  got that?
#
# The basic idea is that if the elements of G are (say)
# large strings and G is dense, then it saves space to
# marshal G to a file as a sequence of indices, rather
# than storing G directly.
#
# for greater space efficiency the list of pairs is spit
# into two lists (leftmembers, rightmembers)

def factor(G):
    from kjbuckets import kjSet, kjGraph
    allnodes = kjSet(G.keys()) + kjSet(G.values())
    allnodelist = allnodes.items()
    allnodemap = map(None, allnodelist, range(len(allnodelist)))
    nodetoindex = kjGraph(allnodemap)
    pairs = G.items()
    left = pairs[:]
    right = left[:]
    for i in xrange(len(left)):
        (l, r) = pairs[i]
        left[i], right[i] = nodetoindex[l], nodetoindex[r]
    return (left, right), allnodelist

# and back again

def unfactor(indexpairs, allnodelist):
    from kjbuckets import kjGraph
    from time import time
    now = time()
    (left, right) = indexpairs
    size = len(left)
    result = kjGraph(size)
    for i in xrange(size):
        result[allnodelist[left[i]]] = allnodelist[right[i]]
    #print time() - now
    return result

def test():
    from kjbuckets import kjGraph
    G = kjGraph( map(None, "pumpernickle", "nicklepumppp") )
    print G
    (iG, l) = factor(G)
    print iG, l
    G2 = unfactor(iG, l)
    print G2
    if G!=G2: print "OOPS"

if __name__=="__main__": test()
