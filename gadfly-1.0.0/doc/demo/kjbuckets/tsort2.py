#! /usr/local/bin/python -O

# more complex implementation of topological sort

LOOPERROR = "LOOPERROR"

def tsort(pairs):
    from kjbuckets import kjGraph, kjSet
    G = kjGraph(pairs)
    Gt = ~G # transpose
    sources = kjSet(G.keys())
    dests = kjSet(G.values())
    all = (sources+dests).items()
    total = len(all)
    endpoints = dests - sources
    for i in xrange(total-1, -1, -1):
        #print i, endpoints
        if not endpoints:
            raise LOOPERROR, "loop detected"
        choice = endpoints.choose_key()
        for n in Gt.neighbors(choice):
            G.delete_arc(n,choice)
            if not G.has_key(n):
                endpoints[n] = n
        del endpoints[choice]
        all[i] = choice
    return all


if __name__=="__main__":
    list = [ (1,2), (3,4), (1,6), (6,3), (3,9), (4,2) ]
    print tsort(list)
    try:
        list = [ (1,2), (3,4), (1,6), (6,3), (3,9), (3,1) ]
        print tsort(list)
        print "WHOOPS: loop 1-6-3-1 not detected"
    except LOOPERROR:
        print "loop error as expected"
