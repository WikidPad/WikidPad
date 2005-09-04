@ECHO OFF
SET PYTHONPATH=lib
del icons\Thumbs.db
rem c:\Python23\python.exe setup.py py2exe -O2 -w --force-imports sql_mar --icon pwiki.ico
python setup.py py2exe -O2 --compressed --includes=sql_mar
copy license.txt dist\license.txt
