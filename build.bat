@ECHO OFF
SET PYTHONPATH=lib
del icons\Thumbs.db
c:\Python23\python.exe setup.py py2exe -O1 -w --force-imports sql_mar --icon pwiki.ico
copy license.txt dist\WikidPad
