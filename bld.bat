SET PYTHONPATH=lib
del icons\Thumbs.db
python buildGadflyZips.py
python updateI18N.py
python setup.py py2exe
copy license.txt dist\license.txt
copy gadfly_small.zip dist\gadfly.zip
