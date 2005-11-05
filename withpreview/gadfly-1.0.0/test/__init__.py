#
# Copyright (c) 2001 Bizar Software Pty Ltd (http://www.bizarsoftware.com.au/)
# This module is free software, and you may redistribute it and/or modify
# under the same terms as Python, so long as this copyright message and
# disclaimer are retained in their original form.
#
# IN NO EVENT SHALL BIZAR SOFTWARE PTY LTD BE LIABLE TO ANY PARTY FOR
# DIRECT, INDIRECT, SPECIAL, INCIDENTAL, OR CONSEQUENTIAL DAMAGES ARISING
# OUT OF THE USE OF THIS CODE, EVEN IF THE AUTHOR HAS BEEN ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
#
# BIZAR SOFTWARE PTY LTD SPECIFICALLY DISCLAIMS ANY WARRANTIES, INCLUDING,
# BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
# FOR A PARTICULAR PURPOSE.  THE CODE PROVIDED HEREUNDER IS ON AN "AS IS"
# BASIS, AND THERE IS NO OBLIGATION WHATSOEVER TO PROVIDE MAINTENANCE,
# SUPPORT, UPDATES, ENHANCEMENTS, OR MODIFICATIONS.
#
# $Id: __init__.py,v 1.3 2002/05/08 00:49:01 anthonybaxter Exp $

import os, tempfile, unittest, shutil
os.environ['SENDMAILDEBUG'] = tempfile.mktemp()

# figure all the modules available
dir = os.path.split(__file__)[0]
test_mods = {}
for file in os.listdir(dir):
    if file.startswith('test_') and file.endswith('.py'):
        name = file[5:-3]
        test_mods[name] = __import__(file[:-3], globals(), locals(), [])
all_tests = test_mods.keys()

def go(tests=all_tests):
    l = []
    for name in tests:
        l.append(test_mods[name].suite())
    suite = unittest.TestSuite(l)
    runner = unittest.TextTestRunner()
    runner.run(suite)

#
# $Log: __init__.py,v $
# Revision 1.3  2002/05/08 00:49:01  anthonybaxter
# El Grande Grande reindente! Ran reindent.py over the whole thing.
# Gosh, what a lot of checkins. Tests still pass with 2.1 and 2.2.
#
# Revision 1.2  2002/05/06 23:27:10  richard
# . made the installation docco easier to find
# . fixed a "select *" test - column ordering is different for py 2.2
# . some cleanup in gadfly/kjParseBuild.py
# . made the test modules runnable (remembering that run_tests can take a
#   name argument to run a single module)
# . fixed the module name in gadfly/kjParser.py
#
# Revision 1.1.1.1  2002/05/06 07:31:09  richard
#
