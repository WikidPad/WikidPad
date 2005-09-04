# setup.py
from distutils.core import setup
import os
from glob import glob
import py2exe
from py2exe.build_exe import Target

# notice that i create a lib dir with the sql_mar
# gadfly grammar files. the build.bat forces the import
# of these files


wikidpad = Target(
    # used for the versioninfo resource
    version = '1.20',
    name = "WikidPad",
    copyright = "(C) 2005 Jason Horman, Michael Butscher, Gerhard Reitmayr",
    description = "Single user wiki notepad",
    comments="",

    # what to build
    script = 'WikidPad.py',
    icon_resources = [(0, 'icons/pwiki.ico')])


setup(name='WikidPadCompact',
      version='1.20',
      author='Jason Horman',
      author_email='jason@jhorman.org',
      url='http://www.jhorman.org/WikidPad/',
      scripts=['WikidPad.py'],
      windows=[wikidpad],
      package_dir = {'': 'lib'},
      packages=['pwiki'],
      data_files=[('icons', glob(os.path.join('icons', '*.*'))),
                  ('lib', glob('sql_mar.*')),
                  ('extensions', glob('extensions/*.*')),
                  ('', ['WikidPad.xrc']),
                  ('WikidPadHelp', glob(os.path.join('WikidPadHelp', "*.wiki"))),
                  (os.path.join('WikidPadHelp', 'data'),
                   glob(os.path.join('WikidPadHelp', 'data', "*.*"))),
                  ('export', [os.path.join('export', 'wikistyle.css')])]
)

