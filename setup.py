# setup.py
from setuptools import setup, find_packages
import os
from glob import glob
try:
    from py2exe.runtime import Target
    wikidpadWinBin = Target(
        # used for the versioninfo resource
        version = '2.4',
        name = 'WikidPad',
        copyright = '(C) 2005-2018 Michael Butscher, Jason Horman, Gerhard Reitmayr',
        description = 'Single user wiki notepad',
        comments='',
    
        # what to build
        script = 'WikidPad.py',
        icon_resources = [(0, 'icons/pwiki.ico'), (1, 'icons/pwiki.ico')]
    )

except ImportError:
    wikidpadWinBin = None


excludes = ["win32api", "win32con", "win32pipe", "gadfly"]

setup(
    options = {"py2exe": {"compressed": 1,
                         "exeoptimize": 1, # Opt.mode of the exe stub
                          "optimize": 2,  # Opt.mode for compiling library.zip
                          ## "ascii": 1,
                          "excludes": excludes,
                          "dll_excludes": ["msvcp90.dll"]}},

    name='WikidPad',
    version = '2.4',
    author = 'Michael Butscher',
    author_email = 'mbutscher@gmx.de',
    url = 'http://www.mbutscher.de/software.html',
    zip_safe = False,
    keywords = "Personal Wiki",
    scripts=['WikidPad/WikidPad.py'],
    entry_points = { 'gui_scripts' : [ 'wikidpad = WikidPad:main' ]},
#     namespace_packages=['lib'],
    windows = ([wikidpadWinBin] if wikidpadWinBin else None),
#     console = [wikidpadWinBin],
    package_dir = {'WikidPad': 'WikidPad'},
#     package_dir = {'WikidPad': 'WikidPad'},
#     packages = ['pwiki', 'pwiki.wikidata', 'pwiki.wikidata.compact_sqlite',
#               'pwiki.wikidata.original_sqlite', 'pwiki.timeView',
#               'pwiki.rtlibRepl'],

    packages = find_packages(include=["WikidPad*"], exclude=["WikidPad.tests"]) +
        [
            "WikidPad.extensions",
            "WikidPad.extensions.mediaWikiParser",
            "WikidPad.extensions.wikidPadParser",
            
            # Not really packages, but data folders
            "WikidPad.lib.js",
            "WikidPad.lib.js.jquery",
            "WikidPad.icons",
            "WikidPad.WikidPadHelp",
            "WikidPad.WikidPadHelp.data",
            "WikidPad.WikidPadHelp.files",
        ],
    
#     ["WikidPad",
#             "WikidPad.extensions",
#             "WikidPad.extensions.mediaWikiParser",
#             "WikidPad.extensions.wikidPadParser",
#             "WikidPad.lib",
#             "WikidPad.lib.aui",
#             "WikidPad.lib.js",
#             "WikidPad.lib.js.jquery",
#             "WikidPad.lib.whoosh",
#             'WikidPad.lib.pwiki', 
#             'WikidPad.lib.pwiki.wikidata',
#             'WikidPad.lib.pwiki.wikidata.original_sqlite', 
#             'WikidPad.lib.pwiki.timeView',
#             'WikidPad.lib.pwiki.rtlibRepl',
#     ],
    
    install_requires =[ "wxpython"],    # , "appdirs", "pypubsub", "biopython"
    
    include_package_data=False,
    package_data={
        'WikidPad': ['*'],
        'WikidPad.extensions': ['*'],
        "WikidPad.lib.js": ['*'],
        "WikidPad.lib.js.jquery": ['*'],
        "WikidPad.icons": ['*'],
        "WikidPad.WikidPadHelp": ['*'],
        "WikidPad.WikidPadHelp.data": ['*'],
        "WikidPad.WikidPadHelp.files": ['*'],
    },

    exclude_package_data={'WikidPad.tests': ['*']},
    
    # py_modules=['encodings.utf_8', 'encodings.latin_1'],
#     data_files = [('icons', glob(os.path.join('icons', '*.*'))),
# #                 ('lib', glob('sql_mar.*')),
#           ('extensions', glob('extensions/*.*')),
#           ('extensions/wikidPadParser', glob('extensions/wikidPadParser/*.*')),
#           ('extensions/mediaWikiParser', glob('extensions/mediaWikiParser/*.*')),
#           ('', ['sqlite3.dll', 'WikidPad.xrc', 'langlist.txt',
#               'appbase.css'] + glob('WikidPad_*.po')),
#           ('WikidPadHelp', glob(os.path.join('WikidPadHelp', '*.wiki'))),
#           (os.path.join('WikidPadHelp', 'data'),
#               glob(os.path.join('WikidPadHelp', 'data', '*.*'))),
#           (os.path.join('WikidPadHelp', 'files'),
#               glob(os.path.join('WikidPadHelp', 'files', '*.*'))),
#           ('export', [])]
    classifiers = ['Development Status :: 4 - Beta',
                 'Intended Audience :: End Users/Desktop',
                 'Operating System :: OS Independent',
                 'License :: OSI Approved :: BSD License',
                 'Programming Language :: Python :: 3.6',
                 'Topic :: Office/Business',],

)
