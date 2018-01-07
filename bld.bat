SET PYTHONPATH=lib
del icons\Thumbs.db
python updateI18N.py
python setup.py py2exe
copy license.txt dist\license.txt
