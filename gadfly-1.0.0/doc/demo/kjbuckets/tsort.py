#! /usr/local/bin/python -O

# simple implementation of topological sort
# using kjbuckets.  For very large and very dense
# graphs you can do better...

from kjbuckets import kjGraph, kjSet

LOOPERROR = "LOOPERROR"

# topological sort
def tsort(list_of_pairs):
    result = []
    Graph = kjGraph(list_of_pairs)
    notsource = (kjSet(Graph.values()) - kjSet(Graph.keys())).items()
    while Graph:
        sources = kjSet(Graph.keys())
        dests = kjSet(Graph.values())
        startingpoints = sources - dests
        if not startingpoints:
            raise LOOPERROR, "loop detected in Graph"
        for node in startingpoints.items():
            result.append(node)
            del Graph[node]
    return result + notsource

if __name__=="__main__":
    list = [ (1,2), (3,4), (1,6), (6,3), (3,9), (4,2) ]
    print tsort(list)
    try:
        list = [ (1,2), (3,4), (1,6), (6,3), (3,9), (3,1) ]
        print tsort(list)
        print "WHOOPS: loop 1-6-3-1 not detected"
    except LOOPERROR:
        print "loop error as expected"
