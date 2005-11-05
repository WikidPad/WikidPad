# $Id: test_sqlgrammar.py,v 1.4 2002/05/08 00:49:01 anthonybaxter Exp $

import unittest

from gadfly.semantics import Parse_Context
from gadfly import sql, bindings
sql = sql.getSQL()
sql = bindings.BindRules(sql)

class test_SQLGrammar(unittest.TestCase):
    def test(self):
        tests = [
            "select a from x where b=c",
            "select distinct x.a from x where x.b=c",
            "select all a from x where b=c",
            "select a from x, y where b=c or x.d=45",
            "select a as k from x d, y as m where b=c",
            "select 1 as n, a from x where b=c",
            "select * from x",
            "select a from x where b=c",
            "select a from x where not b=c or d=1 and e=5",
            "select a from x where a=1 and (x.b=3 or not b=c)",
            "select -1 from x",
            "select -1e6j from x",
            "insert into table1 (a,b,c) values (-1e6+3j, -34e10, 56j)"
        ]
        context = Parse_Context()
        for test in tests:
            sql.DoParse1(test, context)

def suite():
    l = [unittest.makeSuite(test_SQLGrammar),
    ]
    return unittest.TestSuite(l)

if __name__ == '__main__':
    runner = unittest.TextTestRunner()
    runner.run(suite())

#
# $Log: test_sqlgrammar.py,v $
# Revision 1.4  2002/05/08 00:49:01  anthonybaxter
# El Grande Grande reindente! Ran reindent.py over the whole thing.
# Gosh, what a lot of checkins. Tests still pass with 2.1 and 2.2.
#
# Revision 1.3  2002/05/07 07:06:11  richard
# Cleaned up sql grammar compilation some more.
# Split up the BigList into its components too.
#
# Revision 1.2  2002/05/06 23:27:10  richard
# . made the installation docco easier to find
# . fixed a "select *" test - column ordering is different for py 2.2
# . some cleanup in gadfly/kjParseBuild.py
# . made the test modules runnable (remembering that run_tests can take a
#   name argument to run a single module)
# . fixed the module name in gadfly/kjParser.py
#
#
