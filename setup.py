# setup.py
from distutils.core import setup
import os
from glob import glob
import py2exe

# notice that i create a lib dir with the sql_mar
# gadfly grammar files. the build.bat forces the import
# of these files

setup(name='WikidPad',
      version='1.16',
      author='Jason Horman',
      author_email='jason@jhorman.org',
      url='http://www.jhorman.org/WikidPad/',
      scripts=['WikidPad.py'],
      package_dir = {'': 'lib'},
      packages=['pwiki'],
      data_files=[('icons', glob(os.path.join('icons', '*.*'))),
                  ('lib', glob('sql_mar.*')),
                  ('extensions', glob('extensions/*.*')),
                  ('WikidPadHelp', glob(os.path.join('WikidPadHelp', "*.wiki"))),
                  (os.path.join('WikidPadHelp', 'data'),
                   glob(os.path.join('WikidPadHelp', 'data', "*.*"))),
                  ('export', [os.path.join('export', 'wikistyle.css')])]
)
