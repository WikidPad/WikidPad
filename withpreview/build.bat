@ECHO OFF
SET PYTHONPATH=lib
rm icons\Thumbs.db
c:\Python23\python.exe setup.py py2exe --packages encodings -O1 -w --force-imports sql_mar --icon pwiki.ico
cp license.txt dist/WikidPad
