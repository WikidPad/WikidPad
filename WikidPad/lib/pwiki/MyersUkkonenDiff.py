# Source: https://gist.github.com/tonyg/2361e3bfe4e92a1fc6f7

# Copyright (c) 2015 Tony Garnock-Jones <tonyg@leastfixedpoint.com>
#
# Permission is hereby granted, free of charge, to any person
# obtaining a copy of this software and associated documentation files
# (the "Software"), to deal in the Software without restriction,
# including without limitation the rights to use, copy, modify, merge,
# publish, distribute, sublicense, and/or sell copies of the Software,
# and to permit persons to whom the Software is furnished to do so,
# subject to the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS
# BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN
# ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
# CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

# Text diff algorithm after Myers 1986 and Ukkonen 1985, following
# Levente Uzonyi's Squeak Smalltalk implementation at
# http://squeaksource.com/DiffMerge.html
#
# E. W. Myers, "An O(ND) difference algorithm and its variations,"
# Algorithmica, vol. 1, no. 1-4, pp. 251-266, Nov. 1986.
#
# E. Ukkonen, "Algorithms for approximate string matching," Inf.
# Control, vol. 64, no. 1-3, pp. 100-118, Jan. 1985.

def longest_common_subsequence(xs, ys):
  totallen = len(xs) + len(ys)
  frontier = [0] * (2 * totallen + 1)
  candidates = [None] * (2 * totallen + 1)
  for d in range(totallen + 1):
      for k in range(-d, d+1, 2):
          if k == -d or (k != d and frontier[totallen + k - 1] < frontier[totallen + k + 1]):
              index = totallen + k + 1
              x = frontier[index]
          else:
              index = totallen + k - 1
              x = frontier[index] + 1
          y = x - k
          chain = candidates[index]
          while x < len(xs) and y < len(ys) and xs[x] == ys[y]:
              chain = ((x, y), chain)
              x = x + 1
              y = y + 1
          if x >= len(xs) and y >= len(ys):
              result = []
              while chain:
                  result.append(chain[0])
                  chain = chain[1]
              result.reverse()
              return result
          frontier[totallen + k] = x
          candidates[totallen + k] = chain

def diff(xs, ys):
    i = -1
    j = -1
    matches = longest_common_subsequence(xs, ys)
    matches.append((len(xs), len(ys)))
    result = []
    for (mi, mj) in matches:
        if mi - i > 1 or mj - j > 1:
            result.append((i + 1, mi - i - 1, j + 1, mj - j - 1))
        i = mi
        j = mj
    return result


if __name__ == '__main__':
    def check(actual, expected):
        if actual != expected:
            print ("Expected:", repr(expected))
            print ("Actual:", repr(actual))
            print()

    check(diff("The red brown fox jumped over the rolling log",
               "The brown spotted fox leaped over the rolling log"),
          [(4,4,4,0), (14,0,10,8), (18,3,22,3)])

    for (xs, ys, lcs) in [("acbcaca", "bcbcacb", [(1,1),(2,2),(3,3),(4,4),(5,5)]),
                          ("bcbcacb", "acbcaca", [(1,1),(2,2),(3,3),(4,4),(5,5)]),
                          ("acba", "bcbb", [(1,1),(2,2)]),
                          ("abcabba", "cbabac", [(2,0),(3,2),(4,3),(6,4)]),
                          ("cbabac", "abcabba", [(1,1),(2,3),(3,4),(4,6)]),
                          ([[1,1,1],[1,1,1],[1,1,1],[1,1,1]],
                           [[1,1,1],[2,2,2],[1,1,1],[4,4,4]],
                           [(0,0),(1,2)])]:
        check(longest_common_subsequence(xs, ys), lcs)

    check(diff([[1,1,1],[1,1,1],[1,1,1],[1,1,1]],
               [[1,1,1],[2,2,2],[1,1,1],[4,4,4]]),
          [(1,0,1,1), (2,2,3,1)])

    check(longest_common_subsequence("abc", "def"), [])
    check(diff("abc", "def"), [(0,3,0,3)])

