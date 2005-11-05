#! /usr/local/bin/python -O

# silly functions for testing/timing simple table access operations.

import profile
from kjbuckets import *
r = range(5000)
r2 = range(1000)

def dtest(d):
    for i in r:
        d[ (hex(i),oct(i),i) ] = hex(i)+oct(i)+`i`

def dtest2(d):
    global temp
    for i in r: d[ (i*33) % 1000 ] = i
    for i in r: temp = d[ (i*31) % 1000 ]
    for i in r: temp = d[ (i*7) % 1000 ]

def dtest3(d):
    global temp
    for i in r: d[ (i*33) % 1000 ] = i
    for i in r: temp = d[ (i*31) % 1000 ]
    for i in r: temp = d[ (i*7) % 1000 ]
    for i in r2:
        del d[i]
        d[`i`] = `(i*3%1000)`
    for i in r2:
        del d[`i`]

def dtest4(d):
    for i in range(10):
        dtest(d)
        dtest2(d)
        dtest3(d)

if __name__=="__main__":
    from kjbuckets import kjDict
    dtest4(kjDict())

# some profiling done on my ancient sun server
#
# example stats for Python dict
#>>> D = {}
#>>> profile.run("dtest4(D)")
#         33 function calls in 83.033 CPU seconds
#
#   Ordered by: standard name
#
#   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
#       10   14.383    1.438   14.383    1.438 kjtest.py:11(dtest2)
#       10   20.967    2.097   20.967    2.097 kjtest.py:17(dtest3)
#        1    0.083    0.083   83.017   83.017 kjtest.py:28(dtest4)
#       10   47.583    4.758   47.583    4.758 kjtest.py:7(dtest)
#        1    0.017    0.017   83.033   83.033 profile:0(dtest4(D))
#        0    0.000             0.000          profile:0(profiler)
#        1    0.000    0.000   83.017   83.017 python:0(20520.C.2)
#

# with gsize of 1
#
#
#   Ordered by: standard name
#
#   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
#       10   16.650    1.665   16.650    1.665 kjtest.py:11(dtest2)
#       10   24.083    2.408   24.083    2.408 kjtest.py:17(dtest3)
#        1    0.050    0.050   84.150   84.150 kjtest.py:28(dtest4)
#       10   43.367    4.337   43.367    4.337 kjtest.py:7(dtest)
#        1    0.117    0.117   84.267   84.267 profile:0(dtest4(D))
#        0    0.000             0.000          profile:0(profiler)
#        1    0.000    0.000   84.150   84.150 python:0(21460.C.1)


# with gsize of 2
#>>> profile.run("dtest4(D)")
#         33 function calls in 93.467 CPU seconds
#
#   Ordered by: standard name
#
#   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
#       10   16.900    1.690   16.900    1.690 kjtest.py:11(dtest2)
#       10   24.183    2.418   24.183    2.418 kjtest.py:17(dtest3)
#        1    0.083    0.083   93.433   93.433 kjtest.py:28(dtest4)
#       10   52.267    5.227   52.267    5.227 kjtest.py:7(dtest)
#        1    0.017    0.017   93.467   93.467 profile:0(dtest4(D))
#        0    0.000             0.000          profile:0(profiler)
#        1    0.017    0.017   93.450   93.450 python:0(20824.C.3)
#

# with gsize of 4
#33 function calls in 90.200 CPU seconds
#
#   Ordered by: standard name
#
#   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
#       10   17.950    1.795   17.950    1.795 kjtest.py:11(dtest2)
#       10   26.733    2.673   26.733    2.673 kjtest.py:17(dtest3)
#        1    0.033    0.033   90.067   90.067 kjtest.py:28(dtest4)
#       10   45.350    4.535   45.350    4.535 kjtest.py:7(dtest)
#        1    0.133    0.133   90.200   90.200 profile:0(dtest4(D))
#        0    0.000             0.000          profile:0(profiler)
#        1    0.000    0.000   90.067   90.067 python:0(22100.C.1)

# with gsize of 6
#         33 function calls in 98.217 CPU seconds
#
#   Ordered by: standard name
#
#   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
#       10   17.017    1.702   17.017    1.702 kjtest.py:11(dtest2)
#       10   27.033    2.703   27.033    2.703 kjtest.py:17(dtest3)
#        1    0.067    0.067   98.200   98.200 kjtest.py:28(dtest4)
#       10   54.083    5.408   54.083    5.408 kjtest.py:7(dtest)
#        1    0.017    0.017   98.217   98.217 profile:0(dtest4(D))
#        0    0.000             0.000          profile:0(profiler)
#        1    0.000    0.000   98.200   98.200 python:0(22727.C.2)




# with Gsize of 8
#>>> D = kjDict()
#>>> profile.run("dtest4(D)")
#         33 function calls in 106.900 CPU seconds
#
#   Ordered by: standard name
#
#   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
#       10   18.683    1.868   18.683    1.868 kjtest.py:11(dtest2)
#       10   31.433    3.143   31.433    3.143 kjtest.py:17(dtest3)
#        1    0.017    0.017  106.883  106.883 kjtest.py:28(dtest4)
#       10   56.750    5.675   56.750    5.675 kjtest.py:7(dtest)
#        1    0.017    0.017  106.900  106.900 profile:0(dtest4(D))
#        0    0.000             0.000          profile:0(profiler)
#        1    0.000    0.000  106.883  106.883 python:0(20520.C.4)
#

# with gsize of 16
#>>> D = kjDict()
#>>> profile.run("dtest4(D)")
#         33 function calls in 118.533 CPU seconds
#
#   Ordered by: standard name
#
#   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
#       10   22.200    2.220   22.200    2.220 kjtest.py:11(dtest2)
#       10   41.233    4.123   41.233    4.123 kjtest.py:17(dtest3)
#        1    0.067    0.067  118.483  118.483 kjtest.py:28(dtest4)
#       10   54.983    5.498   54.983    5.498 kjtest.py:7(dtest)
#        1    0.033    0.033  118.533  118.533 profile:0(dtest4(D))
#        0    0.000             0.000          profile:0(profiler)
#        1    0.017    0.017  118.500  118.500 python:0(20659.C.3)
#

# with gsize of 32
#
#   Ordered by: standard name
#
#   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
#       10   27.650    2.765   27.650    2.765 kjtest.py:11(dtest2)
#       10   55.600    5.560   55.600    5.560 kjtest.py:17(dtest3)
#        1    0.067    0.067  129.117  129.117 kjtest.py:28(dtest4)
#       10   45.800    4.580   45.800    4.580 kjtest.py:7(dtest)
#        1    0.100    0.100  129.217  129.217 profile:0(dtest4(D))
#        0    0.000             0.000          profile:0(profiler)
#        1    0.000    0.000  129.117  129.117 python:0(21213.C.1)
#

# with gsize of 64
#          33 function calls in 177.017 CPU seconds
#
#   Ordered by: standard name
#
#   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
#       10   38.983    3.898   38.983    3.898 kjtest.py:11(dtest2)
#       10   89.517    8.952   89.517    8.952 kjtest.py:17(dtest3)
#        1    0.033    0.033  176.900  176.900 kjtest.py:28(dtest4)
#       10   48.367    4.837   48.367    4.837 kjtest.py:7(dtest)
#        1    0.117    0.117  177.017  177.017 profile:0(dtest4(D))
#        0    0.000             0.000          profile:0(profiler)
#        1    0.000    0.000  176.900  176.900 python:0(21657.C.1)
#

# with gsize of 128
#         33 function calls in 278.450 CPU seconds
#
#   Ordered by: standard name
#
#   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
#       10   63.500    6.350   63.500    6.350 kjtest.py:11(dtest2)
#       10  161.283   16.128  161.283   16.128 kjtest.py:17(dtest3)
#        1    0.033    0.033  278.333  278.333 kjtest.py:28(dtest4)
#       10   53.517    5.352   53.517    5.352 kjtest.py:7(dtest)
#        1    0.117    0.117  278.450  278.450 profile:0(dtest4(D))
#        0    0.000             0.000          profile:0(profiler)
#        1    0.000    0.000  278.333  278.333 python:0(22265.C.1)
#

#Stats = { # total times
#gsize: [ dtest,        dtest2,         dtest3 ]
#"py":  [ 47.5,         14.3,           20.9 ],
# 1:    [ 43.3,         16.6,           24.0 ], # better! on dtest(?)
# 2:    [ 52.2,         16.9,           24.1 ],
# 4:    [ 45.3,         17.9,           26.7 ],
# 6:    [ 54.0,         17.0,           27.0 ],
# 8:    [ 56.7,         18.6,           31.4 ],
# 16:   [ 54.9,         22.2,           41.2 ],
# 32:   [ 45.8,         27.6,           55.6 ],
# 64:   [ 48.3,         38.9,           89.5 ],
# 128:  [ 53.5,         63.5,           161.2 ]
# }#      weird         increasing      increasing
#
# linear performance decrease seems to start around GSIZE=64
# dtest performance seems to be heavily influenced by more complex
#   key/value calculations.  unreliable.
