SET PYTHONPATH=lib
del icons\Thumbs.db
python buildGadflyZips.py
python setup.py py2exe -O2 --compressed --ascii
copy license.txt dist\license.txt
copy gadfly_small.zip dist\gadfly.zip
