import sys, os, os.path, zipfile, glob

# Otherwise Consts couldn't be imported
sys.path.append("lib")


import Consts

# Build dirlist

print "Build Windows portable Zip File"
print "Collecting files..."

DIRS_TO_WALK = r"""dist\WikidPadHelp"""

FILES_TO_GLOB = r"""dist\WikidPad.exe
dist\appbase.css
dist\extensions\*.py
dist\extensions\wikidPadParser\*.py
dist\icons\*.gif
dist\icons\pwiki.ico
dist\license.txt
dist\python26.dll
dist\sqlite3.dll
dist\wxmsw28uh_adv_vc.dll
dist\wxmsw28uh_core_vc.dll
dist\wxmsw28uh_html_vc.dll
dist\wxmsw28uh_stc_vc.dll
dist\wxmsw28uh_xrc_vc.dll
dist\wxbase28uh_net_vc.dll
dist\wxbase28uh_vc.dll
dist\wxbase28uh_xml_vc.dll
dist\_ctypes.pyd
dist\_hashlib.pyd
dist\pyexpat.pyd
dist\_sqlite3.pyd
dist\_socket.pyd
dist\select.pyd
dist\wx._controls_.pyd
dist\wx._core_.pyd
dist\wx._gdi_.pyd
dist\wx._grid.pyd
dist\wx._html.pyd
dist\wx._misc_.pyd
dist\wx._stc.pyd
dist\wx._windows_.pyd
dist\wx._xrc.pyd
dist\WikidPad.xrc
dist\WikidPad_*.po
dist\langlist.txt
dist\gadfly.zip
dist\library.zip"""


FILES_TO_PROCESS2 = (
    ("Microsoft.VC90.CRT.manifest", "Microsoft.VC90.CRT.manifest"),
    (r"winBinAdditions\msvcp90.dll", "msvcp90.dll"),
    (r"winBinAdditions\msvcr90.dll", "msvcr90.dll"),
    (r"winBinAdditions\msvcm90.dll", "msvcm90.dll"),
    (r"winBinAdditions\gdiplus.dll", "gdiplus.dll"),
    ("WikidPad-winport.config", "WikidPad.config")
)



# walkedFiles = list(os.walk("dist"))

filesToZip = []

for dtw in DIRS_TO_WALK.split("\n"):
    for dirpath, dirname, filenames in list(os.walk(dtw)):
        for filename in filenames:
            src = os.path.join(dirpath, filename)
            ziptarget = os.path.join(dirpath[5:], filename)
            filesToZip.append((src, ziptarget))


for fpat in FILES_TO_GLOB.split("\n"):
    for fn in glob.glob(fpat):
        if os.path.isdir(fn):
            continue
        filesToZip.append((fn, fn[5:]))

filesToZip += list(FILES_TO_PROCESS2)


# print "--wpz16", "\n".join([repr(entry) for entry in filesToZip])




VERSTRING = Consts.VERSION_STRING.split(" ")[1]

zfilefull = zipfile.ZipFile("Output\\WikidPad-" + VERSTRING + "-winport.zip", "w",
        zipfile.ZIP_DEFLATED)

print "Compressing files..."
for src, ziptarget in filesToZip:
    zfilefull.write(src, ziptarget)
#     if src.endswith(".py"):
#         zfilefull.write(src+"c", ziptarget+"c")
#         zfilefull.write(src+"o", ziptarget+"o")
#         zfilesmall.write(src+"o", ziptarget+"o")


zfilefull.close()

