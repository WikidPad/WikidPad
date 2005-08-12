#!/usr/local/bin/python

import os, string, sys
from distutils.core import setup
from distutils.command.build_scripts import build_scripts
from glob import glob

#
# SQL grammar compilation
#
# see if we should build the compiled SQL grammar file
marfile = os.path.join('gadfly','sql_mar.py')
build = 1
if os.path.exists(marfile):
    mtime = os.stat(marfile)[-2]
    if mtime > os.stat(os.path.join('gadfly', 'grammar.py'))[-2]:
        build = 0
if build:
    print 'building grammar file'
    # nuke any existing pyc/o
    for filename in ('sql_mar.pyc', 'sql_mar.pyo'):
        filename = os.path.join('gadfly', filename)
        if os.path.exists(filename):
            os.remove(filename)
    from gadfly import kjParseBuild
    from gadfly.grammar import *
    SQLG = kjParseBuild.NullCGrammar()
    SQLG.SetCaseSensitivity(0)
    DeclareTerminals(SQLG)
    SQLG.Keywords(keywords)
    SQLG.punct(puncts)
    SQLG.Nonterms(nonterms)
    SQLG.comments(["--.*"])
    # TODO: should add comments
    SQLG.Declarerules(sqlrules)
    SQLG.Compile()
    SQLG.MarshalDump(open(marfile, "w"))

#
# Build script files
# - stolen from the Roundup setup file (http://roundup.sf.net/)
#
class build_scripts_create(build_scripts):
    """ Overload the build_scripts command and create the scripts
        from scratch, depending on the target platform.

        You have to define the name of your package in an inherited
        class (due to the delayed instantiation of command classes
        in distutils, this cannot be passed to __init__).

        The scripts are created in an uniform scheme: they start the
        main() function in the module

            <packagename>.scripts.<mangled_scriptname>

        The mangling of script names replaces '-' and '/' characters
        with '-' and '.', so that they are valid module paths. 
    """
    package_name = None

    def copy_scripts(self):
        """ Create each script listed in 'self.scripts'
        """
        if not self.package_name:
            raise Exception("You have to inherit build_scripts_create and"
                " provide a package name")
        
        to_module = string.maketrans('-/', '_.')

        self.mkpath(self.build_dir)
        for script in self.scripts:
            outfile = os.path.join(self.build_dir, os.path.basename(script))

            #if not self.force and not newer(script, outfile):
            #    self.announce("not copying %s (up-to-date)" % script)
            #    continue

            if self.dry_run:
                self.announce("would create %s" % outfile)
                continue

            module = os.path.splitext(os.path.basename(script))[0]
            module = string.translate(module, to_module)
            script_vars = {
                'python': os.path.normpath(sys.executable),
                'package': self.package_name,
                'module': module,
            }

            self.announce("creating %s" % outfile)
            file = open(outfile, 'w')

            try:
                if sys.platform == "win32":
                    file.write('@echo off\n'
                        'if NOT "%%_4ver%%" == "" %(python)s -c "from %(package)s.scripts.%(module)s import main; main()" %%$\n'
                        'if     "%%_4ver%%" == "" %(python)s -c "from %(package)s.scripts.%(module)s import main; main()" %%*\n'
                        % script_vars)
                else:
                    file.write('#! %(python)s\n'
                        'from %(package)s.scripts.%(module)s import main\n'
                        'main()\n'
                        % script_vars)
            finally:
                file.close()
                os.chmod(outfile, 0755)

class build_scripts_gadfly(build_scripts_create):
    package_name = 'gadfly'

def scriptname(path):
    """ Helper for building a list of script names from a list of
        module files.
    """
    script = os.path.splitext(os.path.basename(path))[0]
    script = string.replace(script, '_', '-')
    if sys.platform == "win32":
        script = script + ".bat"
    return script

# build list of scripts from their implementation modules
gadfly_scripts = map(scriptname, glob('gadfly/scripts/[!_]*.py'))

if __name__ == '__main__':
    setup(
        name = 'gadfly',
        version = '1.0.0',
        description = 'Gadfly relational database',
        maintainer = 'Richard Jones',
        maintainer_email = 'richard@users.sourceforge.net',
        url = 'http://gadfly.sourceforge.net/',
        packages = ['gadfly', 'gadfly.scripts'],

        # Override certain command classes with our own ones
        cmdclass = {
            'build_scripts': build_scripts_gadfly,
        },
        scripts = gadfly_scripts,
    )

