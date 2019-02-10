# setup.py
from setuptools import setup, find_packages
import os
from glob import glob

from WikidPad import Consts

DESCRIPTION = 'Single user wiki notepad'

try:
    from py2exe.runtime import Target
    wikidpadWinBin = Target(
        # used for the versioninfo resource
        version = ".".join(str(v) for v in Consts.VERSION_TUPLE[1:]),
        name = 'WikidPad',
        copyright = '(C) 2005-2019 Michael Butscher, Jason Horman, Gerhard Reitmayr',
        description = DESCRIPTION,
        comments='',
    
        # what to build
        script = 'WikidPad.py',
        icon_resources = [(0, 'WikidPad/icons/pwiki.ico'), (1, 'WikidPad/icons/pwiki.ico')]
    )

except ImportError:
    wikidpadWinBin = None



excludes = ["win32api", "win32con", "win32pipe", "gadfly"]

setup(
    options = {"py2exe": {"compressed": 1,
                          "exeoptimize": 1, # Opt.mode of the exe stub
                          "optimize": 2,  # Opt.mode for compiling library.zip
                          "excludes": excludes,
                          "dll_excludes": ["msvcp90.dll"]}},

    name='WikidPad',
    version = Consts.VERSION_STRING.split(" ")[1] + "",
    author = 'Michael Butscher',
    author_email = 'mbutscher@gmx.de',
    description = DESCRIPTION,
    url = 'http://wikidpad.sourceforge.net/',
    zip_safe = False,
    keywords = "Personal Wiki",
    entry_points = { 'gui_scripts' : [ 'wikidpad = WikidPad.WikidPadStarter:main' ]},
    windows = ([wikidpadWinBin] if wikidpadWinBin else None),
    package_dir = {'WikidPad': 'WikidPad'},

    packages = find_packages(include=["WikidPad*"], exclude=["WikidPad.tests"]) +
        [
            "WikidPad.extensions",
            "WikidPad.extensions.mediaWikiParser",
            "WikidPad.extensions.wikidPadParser",
            
            # Not really packages, but data folders (shows warning messages)
            "WikidPad.lib.js",
            "WikidPad.lib.js.jquery",
            "WikidPad.icons",
            "WikidPad.WikidPadHelp",
            "WikidPad.WikidPadHelp.data",
            "WikidPad.WikidPadHelp.files",
        ],
    
    install_requires =["wxpython>=4.0"],
    
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

    exclude_package_data={
        'WikidPad': ['WikidPad_Error.log', 'WikidPad.config', 'pytest.ini'],
        'WikidPad.tests': ['*'],
    },
    
    data_files=None,
    
    classifiers = ['Development Status :: 3 - Alpha',
                 'Intended Audience :: End Users/Desktop',
                 'Operating System :: OS Independent',
                 'License :: OSI Approved :: BSD License',
                 'Programming Language :: Python :: 3.4',
                 'Topic :: Office/Business',],

)
