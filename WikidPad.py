#!python3.4

import sys

if not hasattr(sys, 'frozen'):
    from WikidPad import WikidPadStarter
else:
    import WikidPadStarter



if __name__ == "__main__":
    WikidPadStarter.main()
