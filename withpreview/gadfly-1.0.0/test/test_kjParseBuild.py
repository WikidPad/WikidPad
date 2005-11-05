# $Id: test_kjParseBuild.py,v 1.4 2002/05/11 02:59:05 richard Exp $

import unittest, os, shutil, time, sys

from gadfly.kjParseBuild import *
from gadfly import kjParseBuild, kjParser

class test_kjParseBuild(unittest.TestCase):
    def test(self):
        def echo(x): return x

        # simple grammar stolen from a text
        LD0 = kjParser.LexDictionary()
        id = LD0.terminal("id","id",echo)
        plus = LD0.punctuation("+")
        star = LD0.punctuation("*")
        oppar = LD0.punctuation("(")
        clpar = LD0.punctuation(")")
        equals = LD0.punctuation("=")
        E = kjParser.nonterminal("E")
        T = kjParser.nonterminal("T")
        Tp = kjParser.nonterminal("Tp")
        Ep = kjParser.nonterminal("Ep")
        F = kjParser.nonterminal("F")
        rule1 = kjParser.ParseRule( E, [ T, Ep ] )
        rule2 = kjParser.ParseRule( Ep, [ plus, T, Ep ] )
        rule3 = kjParser.ParseRule( Ep, [ ] )
        rule4 = kjParser.ParseRule( T, [ F, Tp ] )
        rule5 = kjParser.ParseRule( Tp, [ star, F, Tp ] )
        rule6 = kjParser.ParseRule( Tp, [ ] )
        rule7 = kjParser.ParseRule( F, [ oppar, E, clpar ] )
        rule8 = kjParser.ParseRule( F, [ id ] )

        rl0 = [ rule1, rule2, rule3, rule4, rule5, rule6, rule7,rule8]
        rs0 = kjParseBuild.Ruleset(E, rl0)
        rs0.compFirst()
        Firstpairs = kjSet.GetPairs(rs0.First)
        rs0.compFollow()
        Followpairs = kjSet.GetPairs(rs0.Follow)
        rs0.compSLRNFA()
        NFA0 = rs0.SLRNFA
        rs0.compDFA()
        rs0.SLRFixDFA()
        DFA0 = rs0.DFA

        class dummy: pass
        ttt0 = dummy()
        ttt0.STRING = " id + id * id "
        #ttt.List = kjParser.LexList(LD0, ttt0.STRING)
        ttt0.Stream = kjParser.LexStringWalker(ttt0.STRING, LD0)
        ttt0.Stack = [] #{-1:0}# Walkers.SimpleStack()
        ttt0.ParseObj = kjParser.ParserObj(rl0, ttt0.Stream, DFA0,
            ttt0. Stack, 1)
        ttt0.RESULT = ttt0.ParseObj.GO()
        #ttt0.Stack.Dump(10)

        # an even simpler grammar
        S = kjParser.nonterminal("S")
        M = kjParser.nonterminal("M")
        A = kjParser.nonterminal("A")
        rr1 = kjParser.ParseRule( S, [M] )
        #rr2 = kjParser.ParseRule( A, [A, plus, M])
        #rr3 = kjParser.ParseRule( A, [M], echo)
        #rr4 = kjParser.ParseRule( M, [M, star, M])
        rr5 = kjParser.ParseRule( M, [oppar, M, clpar])
        rr6 = kjParser.ParseRule( M, [id])
        rl1 = [rr1,rr5,rr6]
        rs1 = kjParseBuild.Ruleset(S, rl1)
        rs1.compFirst()
        rs1.compFollow()
        rs1.compSLRNFA()
        rs1.compDFA()
        rs1.SLRFixDFA()
        DFA1 = rs1.DFA

        ttt1=dummy()

#        def TESTDFA1( STRING , DOREDUCTIONS = 1):
#            return TESTDFA( STRING, ttt1, DFA1, rl1, DOREDUCTIONS )

        X = kjParser.nonterminal("X")
        Y = kjParser.nonterminal("Y")
        RX = kjParser.ParseRule( X, [ oppar, Y, clpar ] )
        RY = kjParser.ParseRule( Y, [] )
        rl2 = [RX,RY]
        rs2 = kjParseBuild.Ruleset(X, rl2)
        rs2.compFirst()
        rs2.compFollow()
        rs2.compSLRNFA()
        rs2.compDFA()
        rs2.SLRFixDFA()
        DFA2 = rs2.DFA

        ttt2 = dummy()
#        def TESTDFA2( STRING, DOREDUCTIONS = 1):
#            return TESTDFA( STRING, ttt2, DFA2, rl2, DOREDUCTIONS )

        # the following grammar should fail to be slr
        # (Aho,Ullman p. 213)

        S = kjParser.nonterminal("S")
        L = kjParser.nonterminal("L")
        R = kjParser.nonterminal("R")
        RS1 = kjParser.ParseRule( S, [L, equals, R] )
        RS2 = kjParser.ParseRule( S, [R], echo )
        RL1 = kjParser.ParseRule( L, [star, R])
        RL2 = kjParser.ParseRule( L, [id])
        RR1 = kjParser.ParseRule( R, [L] )
        rs3 = kjParseBuild.Ruleset(S, [RS1,RS2,RL1,RL2,RR1])
        rs3.compFirst()
        rs3.compFollow()
        rs3.compSLRNFA()
        rs3.compDFA()
        #rs3.SLRFixDFA() # should fail and does.

        # testing RULEGRAM
        ObjG = NullCGrammar()
        ObjG.Addterm("id","id",echo)
        ObjG.Nonterms("T E Ep F Tp")
        ObjG.Keywords("begin end")
        ObjG.punct("+*()")
        ObjG.comments(["--.*\n"])
        # PROBLEM WITH COMMENTS???
        Rulestr = """
        ## what a silly grammar!
        T ::
        @R One :: T >> begin E end
        @R Three :: E >>
        @R Two :: E >> E + T
        @R Four :: E >> ( T )
        """
        RL = RULEGRAM.DoParse1( Rulestr, ObjG )

class test_Build(unittest.TestCase):
    ''' test generation of the grammar '''
    MARSHALFILE = "SQLTEST_mar"
    def test(self):
        #set this to automatically rebuild the grammar.

        SELECTRULES = """
          ## highest level for select statement (not select for update)
          select-statement ::
          @R selectR :: select-statement >>
                           SELECT
                           from-clause
                           where-clause
                           group-by-clause
                           having-clause
          ## generalized to allow null from clause eg: select 2+2
          @R fromNull :: from-clause >>
          @R fromFull :: from-clause >> FROM
          @R whereNull :: where-clause >>
          @R whereFull :: where-clause >> WHERE
          @R groupNull :: group-by-clause >>
          @R groupFull :: group-by-clause >> GROUP BY
          @R havingNull :: having-clause >>
          @R havingFull :: having-clause >> HAVING
          @R unionNull :: union-clause >>
          @R unionFull :: union-clause >> UNION
        """

        SELECTNONTERMS = """
          select-statement
          all-distinct select-list table-reference-list
          where-clause group-by-clause having-clause union-clause
          maybe-order-by
          search-condition column-list maybe-all order-by-clause
          column-name from-clause
        """
        # of these the following need resolution
        #   (select-list) (table-reference-list)
        #   (search-condition) order-by-clause (column-name)

        SELECTKEYWORDS = """
          SELECT FROM WHERE GROUP BY HAVING UNION DISTINCT ALL AS
        """
        SQLG = kjParseBuild.NullCGrammar()
        SQLG.SetCaseSensitivity(0)
        SQLG.Keywords(SELECTKEYWORDS)
        SQLG.Nonterms(SELECTNONTERMS)
        # no comments yet
        SQLG.Declarerules(SELECTRULES)
        SQLG.Compile()
        outfile = open(self.MARSHALFILE+'.py', "w")
        SQLG.MarshalDump(outfile)
        outfile.close()
        SQLG2 = kjParser.UnMarshalGram(self.MARSHALFILE)

    def tearDown(self):
        filename = self.MARSHALFILE+'.py'
        if os.path.exists(filename):
            os.remove(filename)
        if os.path.exists(filename+'c'):
            os.remove(filename+'c')
        if os.path.exists(filename+'o'):
            os.remove(filename+'o')


def suite():
    l = [
        unittest.makeSuite(test_kjParseBuild),
        unittest.makeSuite(test_Build),
    ]
    return unittest.TestSuite(l)

if __name__ == '__main__':
    runner = unittest.TextTestRunner()
    runner.run(suite())

#
# $Log: test_kjParseBuild.py,v $
# Revision 1.4  2002/05/11 02:59:05  richard
# Added info into module docstrings.
# Fixed docco of kwParsing to reflect new grammar "marshalling".
# Fixed bug in gadfly.open - most likely introduced during sql loading
# re-work (though looking back at the diff from back then, I can't see how it
# wasn't different before, but it musta been ;)
# A buncha new unit test stuff.
#
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
#
