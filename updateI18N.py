import glob
import pygettext


def main():

    updFiles = glob.glob(ur"WikidPad*.po")
    
    updParams = []
#     for uf in updFiles:
#         updParams += [ur"-u", uf]

    pySrcParams = [
            ur"Consts.py",
            ur"ExceptionLogger.py",
            ur"WikidPadStarter.py",
            ur"extensions",
            ur"lib\pwiki",
            ur"lib\pwiki\rtlibRepl",
            ur"lib\pwiki\timeView",
            ur"lib\pwiki\wikidata",
            ur"lib\pwiki\wikidata\compact_sqlite",
            ur"lib\pwiki\wikidata\original_gadfly",
            ur"lib\pwiki\wikidata\original_sqlite"
            ]
    
    params = [ur"-o", ur"WikidPad.pot", ur"--xrc=WikidPad.xrc"] + updParams + \
            pySrcParams
            
    pygettext.main(params)



if __name__ == '__main__':
    main()

