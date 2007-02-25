# setup.py
from distutils.core import setup
import os
from glob import glob
import py2exe
from py2exe.build_exe import Target


wikidpad = Target(
    # used for the versioninfo resource
    version = '1.8',
    name = "WikidPad",
    copyright = "(C) 2005-2007 Jason Horman, Michael Butscher, Gerhard Reitmayr",
    description = "Single user wiki notepad",
    comments="",

    # what to build
    script = 'WikidPad.py',
    icon_resources = [(0, 'icons/pwiki.ico')])


setup(name='WikidPad',
      version='1.8rc',
      author='Michael Butscher',
      author_email='mbutscher@gmx.de',
      url='http://www.mbutscher.nextdesigns.net/software.html',
      ## scripts=['WikidPad.py'],
      windows=[wikidpad],
      package_dir = {'': 'lib'},
      packages=['pwiki', 'pwiki.wikidata', 'pwiki.wikidata.compact_sqlite',
                'pwiki.wikidata.original_gadfly',
                'pwiki.wikidata.original_sqlite'],
      # py_modules=['encodings.utf_8', 'encodings.latin_1'],
      data_files=[('icons', glob(os.path.join('icons', '*.*'))),
#                   ('lib', glob('sql_mar.*')),
                  ('extensions', glob('extensions/*.*')),
                  ('', ['sqlite3.dll', 'WikidPad.xrc', 'readme_Wic.txt', "gadfly.zip"]),
                  ('WikidPadHelp', glob(os.path.join('WikidPadHelpOG-static18', "*.wiki"))),
                  (os.path.join('WikidPadHelp', 'data'),
                    glob(os.path.join('WikidPadHelpOG-static18', 'data', "*.*"))),
                  (os.path.join('WikidPadHelp', 'files'),
                    glob(os.path.join('WikidPadHelpOG-static18', 'files', "*.*"))),
                  ('export', [os.path.join('export', 'wikistyle.css')])]
)
