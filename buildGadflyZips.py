import sys, os, os.path, zipfile

from distutils.util import byte_compile

# Build dirlist

print "Build Gadfly Zip Files"
print "Collecting files..."

walkedFiles = list(os.walk("lib/gadfly"))

filesToZip = []

for dirpath, dirname, filenames in walkedFiles:
    for filename in filenames:
        if not filename.endswith(".py"):
            continue
            
        src = os.path.join(dirpath, filename)
        ziptarget = os.path.join(dirpath[4:], filename)
        filesToZip.append((src, ziptarget))

filesToZip.append(("sql_mar.py", "sql_mar.py"))

filesToCompile = [f[0] for f in filesToZip]

print "Compiling scripts..."
byte_compile(filesToCompile, optimize=0, force=1)
byte_compile(filesToCompile, optimize=2, force=1)

zfilefull = zipfile.ZipFile("gadfly.zip", "w", zipfile.ZIP_DEFLATED)
zfilesmall = zipfile.ZipFile("gadfly_small.zip", "w", zipfile.ZIP_DEFLATED)


print "Compressing files..."
for src, ziptarget in filesToZip:
    zfilefull.write(src, ziptarget)
    if src.endswith(".py"):
        zfilefull.write(src+"c", ziptarget+"c")
        zfilefull.write(src+"o", ziptarget+"o")
        zfilesmall.write(src+"o", ziptarget+"o")


zfilefull.close()
zfilesmall.close()

