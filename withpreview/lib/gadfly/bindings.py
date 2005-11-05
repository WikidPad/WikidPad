""" Rule bindings for sql grammar.

:Author: Aaron Watters
:Maintainers: http://gadfly.sf.net/
:Copyright: Aaron Robert Watters, 1994
:Id: $Id: bindings.py,v 1.4 2002/05/11 02:59:04 richard Exp $:
"""

import semantics

def elt0(list, context):
    """return first member of reduction"""
    return list[0]

def elt1(list, context):
    """return second member"""
    return list[1]

def elt2(list, context):
    return list[2]

def returnNone(list, context):
    return None

def stat1(list, context):
    """return list of len 1 of statements"""
    return list

#def statn(list, context):
#    """return a list of statement reductions"""
#    [stat, semi, statlist] = list
#    statlist.insert(0, stat)
#    return statlist

def thingcommalist(l, c):
    [thing, comma, list] = l
    list.insert(0, thing)
    return list

def listcommathing(l, c):
    [list, comma, thing] = l
    list.append(thing)
    return list

statn = thingcommalist
selstat = elt0
insstat = elt0
createtablestat = elt0
droptablestat = elt0
delstat = elt0
updatestat = elt0
createindexstat = elt0
dropindexstat = elt0
createviewstat = elt0
dropviewstat = elt0

# drop view statement stuff
def dropview(l, c):
    [drop, view, name] = l
    return semantics.DropView(name)

# create view statement stuff
def createview(l, c):
    [create, view, name, namelist, as, selection] = l
    return semantics.CreateView(name, namelist, selection)

optnamelist0 = returnNone
optnamelistn = elt1

# drop index statement stuff
def dropindex(l, c):
    [drop, index, name] = l
    return semantics.DropIndex(name)

# create index statement stuff
def createindex(l, c):
    [create, index, name, on, table, op, namelist, cp] = l
    return semantics.CreateIndex(name, table, namelist)

def createuniqueindex(l, c):
    [create, unique, index, name, on, table, op, namelist, cp] = l
    return semantics.CreateIndex(name, table, namelist, unique=1)

names1 = stat1
namesn = listcommathing

# update statement stuff

def update(l, c):
    [upd, name, set, assns, condition] = l
    return semantics.UpdateOp(name, assns, condition)

def assn(l, c):
    [col, eq, exp] = l
    return (col, exp)

def assn1(l, c):
    [ (col, exp) ] = l
    result = semantics.TupleCollector()
    result.addbinding(col, exp)
    return result

def assnn(l, c):
    [ result, comma, (col, exp) ] = l
    result.addbinding(col, exp)
    return result

# delete statement stuff

def deletefrom(l, c):
    [delete, fromkw, name, where] = l
    return semantics.DeleteOp(name, where)

# drop table stuff

def droptable(l, c):
    [drop, table, name] = l
    return semantics.DropTable(name)

# create table statement stuff

def createtable(list, context):
    [create, table, name, p1, colelts, p2] = list
    return semantics.CreateTable(name, colelts)

colelts1 = stat1
coleltsn = listcommathing
#def coleltsn(list, c):
#    [c1, cc, ce] = list
#    c1.append(ce)
#    return c1

coleltid = elt0
coleltconstraint = elt0

def coldef(l, c):
    [colid, datatype, default, constraints] = l
    return semantics.ColumnDef(colid, datatype, default, constraints)

optdef0 = returnNone
optcolconstr0 = returnNone
stringtype = exnumtype = appnumtype = integer = float = varchar = elt0
varcharn = elt0

# insert statement stuff

def insert1(l, c):
    [insert, into, name, optcolids, insert_spec] = l
    return semantics.InsertOp(name, optcolids, insert_spec)

optcolids0 = returnNone
optcolids1 = elt1
colids1 = stat1
colidsn = listcommathing

def insert_values(l, c):
    return semantics.InsertValues(l[2])

def insert_query(l, c):
    return semantics.InsertSubSelect(l[0])

litlist1 = stat1
litlistn = listcommathing

sliteral0 = elt0
def sliteralp(l, c):
    [p, v] = l
    return +v

def sliterald(l, c):
    [l1, m, l2] = l
    return l1 - l2

def sliterals(l, c):
    [l1, p, l2] = l
    return l1 + l2

def sliteralm(l, c):
    [m, v] = l
    return -v

# select statement stuff

def selectx(list, context):
    [sub, optorder_by] = list
    #sub.union_select = optunion
    sub.order_by = optorder_by
    # number of dynamic parameters in this parse.
    sub.ndynamic = context.ndynamic()
    return sub

psubselect = elt1

def subselect(list, context):
    [select, alldistinct, selectlist, fromkw, trlist,
     optwhere, optgroup, opthaving, optunion] = list
    sel = semantics.Selector(alldistinct, selectlist, trlist, optwhere,
      optgroup, opthaving,
      # store # of dynamic parameters seen in this parse.
      ndynamic = context.ndynamic()
      )
    sel.union_select = optunion
    return sel

def ad0(list, context):
    return "ALL"

adall = ad0

def addistinct(list, context):
    return "DISTINCT"

def where0(list, context):
    return semantics.BTPredicate() # true

where1 = elt1

group0 = returnNone

group1 = elt2

colnames1 = stat1

colnamesn = listcommathing

having0 = returnNone

having1 = elt1

union0 = returnNone

def union1(l, c):
    [union, alldistinct, selection] = l
    return semantics.Union(alldistinct, selection)

def except1(l, c):
    [union, selection] = l
    alldistinct = "DISTINCT"
    return semantics.Except(alldistinct, selection)

def intersect1(l, c):
    [union, selection] = l
    alldistinct = "DISTINCT"
    return semantics.Intersect(alldistinct, selection)

order0 = returnNone
order1 = elt2
#orderby = elt2
sortspec1 = stat1
sortspecn = listcommathing

def sortint(l, c):
    [num, ord] = l
    from types import IntType
    if type(num)!=IntType or num<=0:
        raise ValueError, `num`+': col position not positive int'
    return semantics.PositionedSort(num, ord)

def sortcol(l, c):
    [name, ord] = l
    return semantics.NamedSort(name, ord)

def optord0(l, c):
    return "ASC"

optordasc = optord0

def optorddesc(l, c):
    return "DESC"

## table reference list returns list of (name, name) or (name, alias)
def trl1(l, c):
    [name] = l
    return [(name, name)]

def trln(l,c):
    [name, comma, others] = l
    others.insert(0, (name, name))
    return others

def trl1a(l,c):
    [name, alias] = l
    return [(name, alias)]

def trlna(l,c):
    [name, alias, comma, others] = l
    others.insert(0, (name, alias))
    return others

def trl1as(l,c):
    [name, as, alias] = l
    return [(name, alias)]

def trlnas(l,c):
    [name, as, alias, comma, others] = l
    others.insert(0, (name, alias))
    return others

tablename1 = elt0
columnid1 = elt0

def columnname1(list, context):
    [ci] = list
    return columnname2([None, None, ci], context)

def columnname2(list, context):
    [table, ignore, col] = list
    return semantics.BoundAttribute(table, col)

def dynamic(list, context):
    # return a new dynamic parameter
    int = context.param()
    return semantics.BoundAttribute(0, int)

# expression stuff
def literal(list, context):
    [lit] = list
    return semantics.Constant(lit)

def stringstring(l, c):
    """two strings in sequence = apostrophe"""
    [l1, l2] = l
    value = "%s'%s" % (l1.value0, l2)
    return semantics.Constant(value)

numlit = literal
stringlit = literal
primarylit = elt0
primary1 = elt0
factor1 = elt0
term1 = elt0
exp1 = elt0

def expplus(list, context):
    [exp, plus, term] = list
    return exp + term

def expminus(list, context):
    [exp, minus, term] = list
    return exp - term

def termtimes(list, context):
    [exp, times, term] = list
    return exp * term

def termdiv(list, context):
    [exp, div, term] = list
    return exp / term

plusfactor = elt1

def minusfactor(list, context):
    [minus, factor] = list
    return -factor

primaryexp = elt1

primaryset = elt0

def countstar(l, c):
    return semantics.Count("*")

def distinctset(l, c):
    [agg, p1, distinct, exp, p2] = l
    return set(agg, exp, 1)

distinctcount = distinctset

def allset(l, c):
    [agg, p1, exp, p2] = l
    return set(agg, exp, 0)

allcount = allset

def set(agg, exp, distinct):
    import semantics
    if agg=="AVG":
        return semantics.Average(exp, distinct)
    if agg=="COUNT":
        return semantics.Count(exp, distinct)
    if agg=="MAX":
        return semantics.Maximum(exp, distinct)
    if agg=="MIN":
        return semantics.Minimum(exp, distinct)
    if agg=="SUM":
        return semantics.Sum(exp, distinct)
    if agg=="MEDIAN":
        return semantics.Median(exp, distinct)
    raise NameError, `agg`+": unknown aggregate"

average = count = maximum = minimum = summation = median = elt0

def predicateeq(list, context):
    [e1, eq, e2] = list
    return e1.equate(e2)

def predicatene(list, context):
    [e1, lt, gt, e2] = list
    return ~(e1.equate(e2))

def predicatelt(list, context):
    [e1, lt, e2] = list
    return e1.lt(e2)

def predicategt(list, context):
    [e1, lt, e2] = list
    return e2.lt(e1)

def predicatele(list, context):
    [e1, lt, eq, e2] = list
    return e1.le(e2)

def predicatege(list, context):
    [e1, lt, eq, e2] = list
    return e2.le(e1)

def predbetween(list, context):
    [e1, between, e2, andkw, e3] = list
    return semantics.BetweenPredicate(e1, e2, e3)

def prednotbetween(list, context):
    [e1, notkw, between, e2, andkw, e3] = list
    return ~semantics.BetweenPredicate(e1, e2, e3)

predicate1 = elt0
bps = elt1
bp1 = elt0

# exists predicate stuff
predexists = elt0
def exists(l, c):
    [ex, paren1, subquery, paren2] = l
    return semantics.ExistsPred(subquery)

def notbf(list, context):
    [ notst, thing ] = list
    return ~thing

# quantified predicates
nnall = elt0
nnany = elt0

def predqeq(list, context):
    [exp, eq, allany, p1, subq, p2] = list
    if allany=="ANY":
        return semantics.QuantEQ(exp, subq)
    else:
        return ~semantics.QuantNE(exp, subq)

def predqne(list, context):
    [exp, lt, gt, allany, p1, subq, p2] = list
    if allany=="ANY":
        return semantics.QuantNE(exp, subq)
    else:
        return ~semantics.QuantEQ(exp, subq)

def predqlt(list, context):
    [exp, lt, allany, p1, subq, p2] = list
    if allany=="ANY":
        return semantics.QuantLT(exp, subq)
    else:
        return ~semantics.QuantGE(exp, subq)

def predqgt(list, context):
    [exp, gt, allany, p1, subq, p2] = list
    if allany=="ANY":
        return semantics.QuantGT(exp, subq)
    else:
        return ~semantics.QuantLE(exp, subq)

def predqle(list, context):
    [exp, less, eq, allany, p1, subq, p2] = list
    if allany=="ANY":
        return semantics.QuantLE(exp, subq)
    else:
        return ~semantics.QuantGT(exp, subq)

def predqge(list, context):
    [exp, gt, eq, allany, p1, subq, p2] = list
    if allany=="ANY":
        return semantics.QuantGE(exp, subq)
    else:
        return ~semantics.QuantLT(exp, subq)

# subquery expression
def subqexpr(list, context):
    [p1, subq, p2] = list
    return semantics.SubQueryExpression(subq)

def predin(list, context):
    [exp, inkw, p1, subq, p2] = list
    return semantics.InPredicate(exp, subq)

def prednotin(list, context):
    [exp, notkw, inkw, p1, subq, p2] = list
    return ~semantics.InPredicate(exp, subq)

def predinlits(list, context):
    [exp, inkw, p1, lits, p2] = list
    return semantics.InLits(exp, lits)

def prednotinlits(list, context):
    [exp, notkw, inkw, p1, lits, p2] = list
    return ~semantics.InLits(exp, lits)


bf1 = elt0

def booln(list, context):
    [ e1, andst, e2 ] = list
    return e1&e2

bool1 = elt0

def searchn(list, context):
    [ e1, orst, e2 ] = list
    return e1 | e2

search1 = elt0

colalias = elt0

# select list stuff
def selectstar(l,c):
    return "*"

selectsome = elt0
select1 = elt0

# selectsub returns (expression, asname)

def select1(list, context):
    [ (exp, name) ] = list
    result = semantics.TupleCollector()
    result.addbinding(name, exp)
    return result

def selectn(list, context):
    [ selectsubs, comma, select_sublist ] = list
    (exp, name) = select_sublist
    selectsubs.addbinding(name, exp)
    return selectsubs

def selectit(list, context):
    [exp] = list
    return (exp, None) # no binding!

def selectname(list, context):
    [exp, as, alias] = list
    return (exp, alias)

colalias = elt0


#### do the bindings.

# note: all reduction function defs must precede this assign
VARS = vars()

class punter:
    def __init__(self, name):
        self.name = name
    def __call__(self, list, context):
        print "punt:", self.name, list
        return list

class tracer:
    def __init__(self, name, fn):
        self.name = name
        self.fn = fn

    def __call__(self, list, context):
        print self.name, list
        return self.fn(list, context)

def BindRules(sqlg):
    for name in sqlg.RuleNameToIndex.keys():
        if VARS.has_key(name):
            #print "binding", name
            sqlg.Bind(name, VARS[name]) # nondebug
            #sqlg.Bind(name, tracer(name, VARS[name]) ) # debug
        else:
            print "unbound", name
            sqlg.Bind(name, punter(name))
    return sqlg

#
# $Log: bindings.py,v $
# Revision 1.4  2002/05/11 02:59:04  richard
# Added info into module docstrings.
# Fixed docco of kwParsing to reflect new grammar "marshalling".
# Fixed bug in gadfly.open - most likely introduced during sql loading
# re-work (though looking back at the diff from back then, I can't see how it
# wasn't different before, but it musta been ;)
# A buncha new unit test stuff.
#
# Revision 1.3  2002/05/08 00:49:00  anthonybaxter
# El Grande Grande reindente! Ran reindent.py over the whole thing.
# Gosh, what a lot of checkins. Tests still pass with 2.1 and 2.2.
#
# Revision 1.2  2002/05/08 00:31:52  richard
# More cleanup.
#
# Revision 1.1.1.1  2002/05/06 07:31:09  richard
#
#
#
