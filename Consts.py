
# VERSION_TUPLE is structured (branch, major, minor, stateAndMicro, patch)
# where branch is normally string "wikidPad", but should be changed if somebody
# develops a derived version of WikidPad.
# 
# major and minor are the main versions,
# stateAndMicro is:
#     between 0 and 99 for "alpha" or "beta"
#     between 100 and 199 for "rc" (release candidate)
#     200 for "final"
#     
#     the unit and tenth place form the micro version.
# 
# patch is a sub-micro version, if needed, normally 0.
# 
# Examples:
# (1, 8, 107, 0) is 1.8rc7
# (1, 9, 4, 0) is 1.9beta4
# (1, 9, 4, 2) is something after 1.9beta4
# (2, 0, 200, 0) is 2.0final

VERSION_TUPLE = ("wikidPad", 1, 9, 109, 0)
VERSION_STRING = "wikidPad 1.9rc09"
HOMEPAGE = u"http://wikidpad.sourceforge.net"
