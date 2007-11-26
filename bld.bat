SET PYTHONPATH=lib
del icons\Thumbs.db
rem python setup.py py2exe -O2 --force-imports encodings.utf_8 --force-imports encodings.latin_1 --icon pwiki.ico
rem python setup.py py2exe -O2 --includes=encodings.utf_8,encodings.latin_1 --xref
python updateI18N.py
python setup.py py2exe -O2 --compressed --ascii
copy license.txt dist\license.txt
copy gadfly_small.zip dist\gadfly.zip
