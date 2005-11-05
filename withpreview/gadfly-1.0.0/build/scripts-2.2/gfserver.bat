@echo off
if NOT "%_4ver%" == "" c:\Python22\python.exe -c "from gadfly.scripts.gfserver import main; main()" %$
if     "%_4ver%" == "" c:\Python22\python.exe -c "from gadfly.scripts.gfserver import main; main()" %*
