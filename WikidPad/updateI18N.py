import glob
import pygettext


def main():

    updFiles = glob.glob(r"WikidPad*.po")
    
    updParams = []
#     for uf in updFiles:
#         updParams += [ur"-u", uf]

    pySrcParams = [
            r"Consts.py",
            r"ExceptionLogger.py",
            r"WikidPadStarter.py",
            r"extensions",
            r"lib\pwiki",
            r"lib\pwiki\rtlibRepl",
            r"lib\pwiki\timeView",
            r"lib\pwiki\wikidata",
            r"lib\pwiki\wikidata\compact_sqlite",
            r"lib\pwiki\wikidata\original_gadfly",
            r"lib\pwiki\wikidata\original_sqlite"
            ]
    
    params = [r"-o", r"WikidPad.pot", r"--xrc=WikidPad.xrc"] + updParams + \
            pySrcParams
            
    pygettext.main(params)



if __name__ == '__main__':
    main()

