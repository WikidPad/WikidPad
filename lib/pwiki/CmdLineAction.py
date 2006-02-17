import sys, os, getopt

import urllib_red as urllib

from StringOps import mbcsDec


class CmdLineAction:
    """
    This class parses command line options, provides necessary information
    and performs actions
    """
    
    def __init__(self, sargs):
        """
        sargs -- stripped args (mainly sys.args[1:])
        """
        self.wikiToOpen = None
        self.wikiWordToOpen = None

        if len(sargs) == 0:
            return
            
        # mbcs decoding of parameters
        sargs = [mbcsDec(a, "replace")[0] for a in sargs]

        if sargs[0][0] != "-":
            # Old style, mainly used by the system
            self.wikiToOpen = sargs[0]
            if self.wikiToOpen.startswith("wiki:"):
                self.wikiToOpen = urllib.url2pathname(self.wikiToOpen)
                self.wikiToOpen = self.wikiToOpen.replace("wiki:", "")

            if len(sargs) > 1:
                self.wikiWordToOpen = sargs[1]
                
                
                

                
    






if len(sys.argv) > 1:
   openThisWiki = sys.argv[1]
   if openThisWiki.startswith("wiki:"):
      openThisWiki = urllib.url2pathname(openThisWiki)
      openThisWiki = openThisWiki.replace("wiki:", "")

   if len(sys.argv) > 2:
      openThisWikiWord = sys.argv[2]
