SET TEMP_PYPATH=
if defined PYTHONPATH (
    SET TEMP_PYPATH=%PYTHONPATH%
)

SET PYTHONPATH=WikidPad\lib;WikidPad
del WikidPad\icons\Thumbs.db

cd WikidPad
python updateI18N.py
cd ..

python setup.py py2exe


copy WikidPad\license.txt dist\license.txt
xcopy WikidPad\icons\* dist\icons /i
xcopy WikidPad\extensions dist\extensions /i /s
xcopy sqlite3.dll dist /i /y
xcopy WikidPad\WikidPad.xrc dist /i /y
xcopy WikidPad\langlist.txt dist /i /y
xcopy WikidPad\appbase.css dist /i /y
xcopy WikidPad\WikidPad_*.po dist /i /y
xcopy WikidPad\WikidPadHelp dist\WikidPadHelp /i /s

REM python WikidPad\updateI18N.py
REM python setup.py py2exe
REM copy WikidPad\license.txt ..\dist\license.txt


if defined TEMP_PYPATH (
    SET PYTHONPATH=%TEMP_PYPATH%
) else (
    SET PYTHONPATH=
)

SET TEMP_PYPATH=
