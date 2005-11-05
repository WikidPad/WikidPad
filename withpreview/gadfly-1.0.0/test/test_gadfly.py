# $Id: test_gadfly.py,v 1.8 2002/05/19 01:54:24 richard Exp $

import unittest, os, shutil, time, sys
from gadfly import gadfly
from gadfly.store import StorageError

class harness(unittest.TestCase):
    def setUp(self):
        self.connect = gadfly()
        if os.path.exists('_test_dir'):
            shutil.rmtree('_test_dir')
        os.makedirs('_test_dir')
        self.connect.startup("test", '_test_dir')
        self.curs = self.connect.cursor()

        table_creates = (
            "frequents (drinker varchar, bar varchar, perweek integer)",
            "likes (drinker varchar, beer varchar, perday integer)",
            "serves (bar varchar, beer varchar, quantity integer)",
            "work (name varchar, hours integer, rate float)",
            "empty (nothing varchar)",
            "accesses (page varchar, hits integer, month integer)",
        )
        for x in table_creates:
            self.curs.execute('create table '+x)

        self.curs.execute("""Create view
            nondrinkers(d, b) as select drinker, bar from frequents
            where drinker not in (select drinker from likes)""")

        # inserts
        C = "insert into work (name, hours, rate) values (?, ?, ?)"
        D = [("sam", 30, 40.2),
             ("norm", 45, 10.2),
             ("woody", 80, 5.4),
             ("diane", 3, 4.4),
             ("rebecca", 120, 12.9),
             ("cliff", 26, 200.00),
             ("carla", 9, 3.5),
        ]
        self.curs.execute(C, D)
        self.curs.execute('select name, hours, rate from work order by name')
        l = self.curs.fetchall()
        D.sort()
        self.assertEquals(l, D)

        fdata = [
          ('adam', 'lolas', 1),
          ('woody', 'cheers', 5),
          ('sam', 'cheers', 5),
          ('norm', 'cheers', 3),
          ('wilt', 'joes', 2),
          ('norm', 'joes', 1),
          ('lola', 'lolas', 6),
          ('norm', 'lolas', 2),
          ('woody', 'lolas', 1),
          ('pierre', 'frankies', 0),
        ]
        sdata = [
          ('cheers', 'bud', 500),
          ('cheers', 'samaddams', 255),
          ('joes', 'bud', 217),
          ('joes', 'samaddams', 13),
          ('joes', 'mickies', 2222),
          ('lolas', 'mickies', 1515),
          ('lolas', 'pabst', 333),
          ('winkos', 'rollingrock', 432),
          ('frankies', 'snafu', 5),
        ]
        ldata = [
          ('adam', 'bud', 2),
          ('wilt', 'rollingrock', 1),
          ('sam', 'bud', 2),
          ('norm', 'rollingrock', 3),
          ('norm', 'bud', 2),
          ('nan', 'sierranevada', 1),
          ('woody', 'pabst', 2),
          ('lola', 'mickies', 5),
        ]
        dpairs = [("frequents", fdata), ("serves", sdata), ("likes", ldata) ]
        for table, data in dpairs:
            ins = "insert into %s values (?, ?, ?)"%table
            if table!="frequents":
                for parameters in data:
                    self.curs.execute(ins, parameters)
            else:
                self.curs.execute(ins, data)

        # indexes
        indices = [
            "create index fd on frequents (drinker)",
            "create index sbb on serves (beer, bar)",
            "create index lb on likes (beer)",
            "create index fb on frequents (bar)",
        ]
        for ci in indices:
            self.curs.execute(ci)

        self.connect.commit()

    def runQueries(self, queries):
        for q, p in queries:
            self.curs.execute(q)
            self.assertEqual(self.curs.pp(), p)

    def tearDown(self):
        self.connect.close()
        if os.path.exists('_test_dir'):
            shutil.rmtree('_test_dir')

class test_Gadfly(harness):

    def testIndex(self):
        # test unique index
        C = "create unique index wname on work(name)"
        self.curs.execute(C)
        C = "insert into work(name, hours, rate) values ('sam', 0, 0)"
        self.assertRaises(StorageError, self.curs.execute, C)

    def testIntrospection(self):
        # introspection
        itests = ["select 10*4 from dual",
                  "select * from __table_names__",
                  "select * from __datadefs__",
                  "select * from __indices__",
                  "select * from __columns__",
                  "select * from __indexcols__",
                  """
                  select i.index_name, is_unique, table_name, column_name
                  from __indexcols__ c, __indices__ i
                  where c.index_name = i.index_name""",
                  ]
        # TODO: compare results
        for C in itests:
            self.curs.execute(C)

    def testComplexLiterals(self):
        # testing complex, neg literals in insert
        self.curs.execute('''insert into work(name, hours, rate)
            values ('jo', -1, 3.1e-44-1e26j)''')
        self.curs.execute("select name,hours,rate from work where name='jo'")
        self.assertEquals(self.curs.fetchall(), [('jo', -1, (3.1e-44-1e+26j))])
        self.curs.execute("delete from work where name='jo'")

    def testParameterisedInsert(self):
        # parameterised inserts
        C = "insert into accesses(page, month, hits) values (?, ?, ?)"
        D = [
             ("index.html", 1, 2100),
             ("index.html", 2, 3300),
             ("index.html", 3, 1950),
             ("products.html", 1, 15),
             ("products.html", 2, 650),
             ("products.html", 3, 98),
             ("people.html", 1, 439),
             ("people.html", 2, 12),
             ("people.html", 3, 665),
             ]
        self.curs.execute(C, D)
        self.curs.execute("""select sum(hits) from accesses
            where page='people.html'""")
        self.assertEquals(self.curs.fetchall(), [(439+12+665,)])

        self.runQueries([
("""select month, sum(hits) as totalhits from accesses
   where month<>1 group by month order by 2""",
'MONTH | TOTALHITS\n=================\n3     | 2713     \n2     | 3962     '),
("""select month, sum(hits) as totalhits from accesses
   group by month order by 2 desc""",
'MONTH | TOTALHITS\n=================\n2     | 3962     \n3     | 2713     \n1     | 2554     '),
("""select month, sum(hits) as totalhits from accesses
   group by month having sum(hits)<3000 order by 2 desc""",
'MONTH | TOTALHITS\n=================\n3     | 2713     \n1     | 2554     '),
("select count(distinct month), count(distinct page) from accesses",
'Count(distinct ACCESSES.MONTH) | Count(distinct ACCESSES.PAGE)\n==============================================================\n3                              | 3                            '),
("select month, hits, page from accesses order by month, hits desc",
'MONTH | HITS | PAGE         \n============================\n1     | 2100 | index.html   \n1     | 439  | people.html  \n1     | 15   | products.html\n2     | 3300 | index.html   \n2     | 650  | products.html\n2     | 12   | people.html  \n3     | 1950 | index.html   \n3     | 665  | people.html  \n3     | 98   | products.html'),
        ])

    def testTrivialQueries1(self):
        self.runQueries([
("select name, hours from work",
'NAME    | HOURS\n===============\nsam     | 30   \nnorm    | 45   \nwoody   | 80   \ndiane   | 3    \nrebecca | 120  \ncliff   | 26   \ncarla   | 9    '),
        ])

    def testTrivialQueries2(self):
        self.runQueries([
("select B,D from nondrinkers",
'B        | D     \n=================\nfrankies | pierre'),
        ])

    def testTrivialQueries3(self):
        self.runQueries([
("""select QUANTITY,BAR,BEER from serves""",
'QUANTITY | BAR      | BEER       \n=================================\n500      | cheers   | bud        \n255      | cheers   | samaddams  \n217      | joes     | bud        \n13       | joes     | samaddams  \n2222     | joes     | mickies    \n1515     | lolas    | mickies    \n333      | lolas    | pabst      \n432      | winkos   | rollingrock\n5        | frankies | snafu      '),
        ])

    def testTrivialQueries4(self):
        self.runQueries([
("""select BAR,PERWEEK,DRINKER from frequents
   where drinker = 'norm'""",
'BAR    | PERWEEK | DRINKER\n==========================\ncheers | 3       | norm   \njoes   | 1       | norm   \nlolas  | 2       | norm   '),
        ])

    def testMedian(self):
        self.runQueries([
("select median(hours) from work",
'Median(WORK.HOURS)\n==================\n30                ')
        ])

    def testComments(self):
        self.runQueries([
("select name,rate,hours from work where name='carla' -- just carla",
'NAME  | RATE | HOURS\n====================\ncarla | 3.5  | 9    '),
("""select name, ' ain''t worth ', rate from work -- has more columns
    where name='carla'""",
"NAME  |  ain't worth  | RATE\n============================\ncarla |  ain't worth  | 3.5 "),
("""select name, -- name of worker
           hours -- hours worked
   from work""",
'NAME    | HOURS\n===============\nsam     | 30   \nnorm    | 45   \nwoody   | 80   \ndiane   | 3    \nrebecca | 120  \ncliff   | 26   \ncarla   | 9    '),
        ])

    def testSimpleRange(self):
        self.runQueries([
("select name, rate from work where rate>=20 and rate<=100",
'NAME | RATE\n===========\nsam  | 40.2'),
("select name, rate from work where rate between 20 and 100",
'NAME | RATE\n===========\nsam  | 40.2'),
("select name, rate from work where rate not between 20 and 100",
'NAME    | RATE \n===============\nnorm    | 10.2 \nwoody   | 5.4  \ndiane   | 4.4  \nrebecca | 12.9 \ncliff   | 200.0\ncarla   | 3.5  '),
        ])

    def testBetween(self):
        self.runQueries([
("""select BAR,PERWEEK,DRINKER
   from frequents
   where perweek not between 2 and 5""",
'BAR      | PERWEEK | DRINKER\n============================\nlolas    | 1       | adam   \njoes     | 1       | norm   \nlolas    | 6       | lola   \nlolas    | 1       | woody  \nfrankies | 0       | pierre '),
        ])

    def testIn(self):
        self.runQueries([
("""select drinker,beer,perday from likes
    where beer in ('bud', 'pabst')""",
'DRINKER | BEER  | PERDAY\n========================\nadam    | bud   | 2     \nsam     | bud   | 2     \nnorm    | bud   | 2     \nwoody   | pabst | 2     '),
        ])

    def testNotIn(self):
        result = 'BEER     \n=========\nsamaddams\nsamaddams\nsnafu    '
        self.runQueries([
("""select beer from serves
   where beer not in (select beer from likes)""", result)
        ])

    def testSimpleCalculations1(self):
        self.runQueries([
("select name, hours*rate as pay from work order by name",
'NAME    | PAY   \n================\ncarla   | 31.5  \ncliff   | 5200.0\ndiane   | 13.2  \nnorm    | 459.0 \nrebecca | 1548.0\nsam     | 1206.0\nwoody   | 432.0 '),
        ])

    def testSimpleCalculations2(self):
        self.runQueries([
("select name, rate, hours, hours*rate as pay from work",
'NAME    | RATE  | HOURS | PAY   \n================================\nsam     | 40.2  | 30    | 1206.0\nnorm    | 10.2  | 45    | 459.0 \nwoody   | 5.4   | 80    | 432.0 \ndiane   | 4.4   | 3     | 13.2  \nrebecca | 12.9  | 120   | 1548.0\ncliff   | 200.0 | 26    | 5200.0\ncarla   | 3.5   | 9     | 31.5  '),
        ])

    def testSimpleCalculations3(self):
        self.runQueries([
("""select name, rate, hours, hours*rate as pay from work
   where hours*rate>500 and (rate<100 or hours>5)""",
'NAME    | RATE  | HOURS | PAY   \n================================\nsam     | 40.2  | 30    | 1206.0\nrebecca | 12.9  | 120   | 1548.0\ncliff   | 200.0 | 26    | 5200.0'),
        ])

    def testSimpleCalculations4(self):
        self.runQueries([
("""select name, rate, hours, hours*rate as pay from work
   where hours*rate>500 and rate<100 or hours>5""",
'NAME    | RATE  | HOURS | PAY   \n================================\nsam     | 40.2  | 30    | 1206.0\nnorm    | 10.2  | 45    | 459.0 \nwoody   | 5.4   | 80    | 432.0 \nrebecca | 12.9  | 120   | 1548.0\ncliff   | 200.0 | 26    | 5200.0\ncarla   | 3.5   | 9     | 31.5  '),
        ])

    def testSimpleCalculations5(self):
        self.runQueries([
("""select avg(rate), min(hours), max(hours), sum(hours*rate) as expenses
   from work""",
'Average(WORK.RATE) | Minimum(WORK.HOURS) | Maximum(WORK.HOURS) | EXPENSES\n=========================================================================\n39.5142857143      | 3                   | 120                 | 8889.7  '),
        ])

    def testUnion1(self):
        self.runQueries([
("""select drinker as x from likes
    union select beer as x from serves
    union select drinker as x from frequents""",
'X          \n===========\nadam       \nwoody      \nsam        \nnorm       \nwilt       \nnorm       \nlola       \nnorm       \nwoody      \npierre     \nbud        \nsamaddams  \nbud        \nsamaddams  \nmickies    \nmickies    \npabst      \nrollingrock\nsnafu      \nadam       \nwilt       \nsam        \nnorm       \nnorm       \nnan        \nwoody      \nlola       '),
        ])

    def testUnion2(self):
        self.runQueries([
("""select drinker from likes union select drinker from frequents""",
'DRINKER\n=======\nadam   \nwoody  \nsam    \nnorm   \nwilt   \nnorm   \nlola   \nnorm   \nwoody  \npierre \nadam   \nwilt   \nsam    \nnorm   \nnorm   \nnan    \nwoody  \nlola   '),
        ])

    def testUnionDistinct(self):
        self.runQueries([
("""select drinker from likes union distinct
   select drinker from frequents
   order by drinker""",
'DRINKER\n=======\nadam   \nlola   \nnan    \nnorm   \npierre \nsam    \nwilt   \nwoody  '),
        ])

    def testJoin1(self):
        self.runQueries([
("""select f.drinker, s.bar, l.beer
   from frequents f, serves s, likes l
   where f.drinker=l.drinker and s.beer=l.beer and s.bar=f.bar""",
'DRINKER | BAR    | BEER   \n==========================\nsam     | cheers | bud    \nnorm    | cheers | bud    \nnorm    | joes   | bud    \nlola    | lolas  | mickies\nwoody   | lolas  | pabst  '),
        ])

    def testJoin2(self):
        self.runQueries([
("""select QUANTITY,BEER,PERWEEK,DRINKER,S.BAR,F.BAR
   from frequents as f, serves as s
   where f.bar = s.bar
   order by QUANTITY,BEER,PERWEEK,DRINKER,S.BAR,F.BAR""",
'QUANTITY | BEER      | PERWEEK | DRINKER | BAR      | F.BAR   \n==============================================================\n5        | snafu     | 0       | pierre  | frankies | frankies\n13       | samaddams | 1       | norm    | joes     | joes    \n13       | samaddams | 2       | wilt    | joes     | joes    \n217      | bud       | 1       | norm    | joes     | joes    \n217      | bud       | 2       | wilt    | joes     | joes    \n255      | samaddams | 3       | norm    | cheers   | cheers  \n255      | samaddams | 5       | sam     | cheers   | cheers  \n255      | samaddams | 5       | woody   | cheers   | cheers  \n333      | pabst     | 1       | adam    | lolas    | lolas   \n333      | pabst     | 1       | woody   | lolas    | lolas   \n333      | pabst     | 2       | norm    | lolas    | lolas   \n333      | pabst     | 6       | lola    | lolas    | lolas   \n500      | bud       | 3       | norm    | cheers   | cheers  \n500      | bud       | 5       | sam     | cheers   | cheers  \n500      | bud       | 5       | woody   | cheers   | cheers  \n1515     | mickies   | 1       | adam    | lolas    | lolas   \n1515     | mickies   | 1       | woody   | lolas    | lolas   \n1515     | mickies   | 2       | norm    | lolas    | lolas   \n1515     | mickies   | 6       | lola    | lolas    | lolas   \n2222     | mickies   | 1       | norm    | joes     | joes    \n2222     | mickies   | 2       | wilt    | joes     | joes    ')
        ])

    def testJoin3(self):
        self.runQueries([
("""select PERDAY,BAR,PERWEEK,BEER,F.DRINKER,L.DRINKER
   from likes l, frequents f
   where f.bar='cheers' and l.drinker=f.drinker and l.beer='bud'
   order by PERDAY,BAR,PERWEEK,BEER,F.DRINKER,L.DRINKER""",
'PERDAY | BAR    | PERWEEK | BEER | DRINKER | L.DRINKER\n======================================================\n2      | cheers | 3       | bud  | norm    | norm     \n2      | cheers | 5       | bud  | sam     | sam      '),
        ])

    def testComplex1(self):
        self.runQueries([
("""select l.beer, l.drinker, count(distinct s.bar)
   from likes l, serves s
   where l.beer=s.beer
   group by l.beer, l.drinker
   order by 3 desc, l.beer, l.drinker""",
'BEER        | DRINKER | Count(distinct S.BAR)\n=============================================\nbud         | adam    | 2                    \nbud         | norm    | 2                    \nbud         | sam     | 2                    \nmickies     | lola    | 2                    \npabst       | woody   | 1                    \nrollingrock | norm    | 1                    \nrollingrock | wilt    | 1                    '),
        ])

    def testComplex2(self):
        self.runQueries([
("""select l.beer, l.drinker, count(distinct s.bar) as nbars
   from likes l, serves s
   where l.beer=s.beer
   group by l.beer, l.drinker
    union distinct
     select beer, drinker, 0 as nbars
     from likes
     where beer not in (select beer from serves)
   order by 3 desc, l.beer, l.drinker""",
'BEER         | DRINKER | NBARS\n==============================\nbud          | adam    | 2    \nbud          | norm    | 2    \nbud          | sam     | 2    \nmickies      | lola    | 2    \npabst        | woody   | 1    \nrollingrock  | norm    | 1    \nrollingrock  | wilt    | 1    \nsierranevada | nan     | 0    '
),
        ])

    def testAverage(self):
        self.runQueries([
("""select avg(perweek) from frequents""",
'Average(FREQUENTS.PERWEEK)\n==========================\n2.6                       '),
        ])

    def testAverageSubQuery1(self):
        self.runQueries([
("""select BAR,PERWEEK,DRINKER from frequents
   where perweek <= (select avg(perweek) from frequents)""",
'BAR      | PERWEEK | DRINKER\n============================\nlolas    | 1       | adam   \njoes     | 2       | wilt   \njoes     | 1       | norm   \nlolas    | 2       | norm   \nlolas    | 1       | woody  \nfrankies | 0       | pierre '
),
        ])

    def testAverageSubQuery2(self):
        self.runQueries([
("""select QUANTITY,BAR,BEER from serves s1
   where quantity <= (select avg(quantity) from serves s2
                      where s1.bar=s2.bar)""",
'QUANTITY | BAR      | BEER       \n=================================\n255      | cheers   | samaddams  \n217      | joes     | bud        \n13       | joes     | samaddams  \n333      | lolas    | pabst      \n432      | winkos   | rollingrock\n5        | frankies | snafu      '),
        ])

    def testAverageSubQuery3(self):
        self.runQueries([
("""select BAR,PERWEEK,DRINKER from frequents
   where perweek > (select avg(perweek) from frequents)""",
'BAR    | PERWEEK | DRINKER\n==========================\ncheers | 5       | woody  \ncheers | 5       | sam    \ncheers | 3       | norm   \nlolas  | 6       | lola   '),
        ])

    def testAverageSubQuery4(self):
        self.runQueries([
("""select BAR,PERWEEK,DRINKER from frequents f1
   where perweek > (
   select avg(perweek) from frequents f2
   where f1.drinker = f2.drinker)""",
'BAR    | PERWEEK | DRINKER\n==========================\ncheers | 5       | woody  \ncheers | 3       | norm   '),
        ])

    def testAverageSubQuery5(self):
        self.runQueries([
("""select BAR,PERWEEK,DRINKER from frequents
   where perweek between 2 and
        (select avg(perweek) from frequents)""",
'BAR   | PERWEEK | DRINKER\n=========================\njoes  | 2       | wilt   \nlolas | 2       | norm   '),
        ])

    def testAverageGroup(self):
        self.runQueries([
("""select bar, avg(quantity) from serves group by bar order by bar""",
'BAR      | Average(SERVES.QUANTITY)\n===================================\ncheers   | 377.5                   \nfrankies | 5.0                     \njoes     | 817.333333333           \nlolas    | 924.0                   \nwinkos   | 432.0                   '),
        ])

    def testAny1(self):
        self.runQueries([
("""select BAR,PERWEEK,DRINKER from frequents
   where perweek < any (select perweek from frequents)""",
'BAR      | PERWEEK | DRINKER\n============================\nlolas    | 1       | adam   \ncheers   | 5       | woody  \ncheers   | 5       | sam    \ncheers   | 3       | norm   \njoes     | 2       | wilt   \njoes     | 1       | norm   \nlolas    | 2       | norm   \nlolas    | 1       | woody  \nfrankies | 0       | pierre '),
        ])

    def testAny2(self):
        self.runQueries([
("""select BAR,PERWEEK,DRINKER from frequents f1
   where perweek < any
   (select perweek from frequents f2
    where f1.drinker = f2.drinker)""",
'BAR   | PERWEEK | DRINKER\n=========================\njoes  | 1       | norm   \nlolas | 2       | norm   \nlolas | 1       | woody  '),
        ])

    def testAny3(self):
        result = 'BEER       \n===========\nbud        \nbud        \nmickies    \nmickies    \npabst      \nrollingrock'
        self.runQueries([
("""select beer from serves where beer = any (select beer from likes)""",
    result)])
        self.runQueries([
("""select beer from serves where beer in (select beer from likes)""",
    result)])

    def testAll1(self):
        self.runQueries([
("""select BAR,PERWEEK,DRINKER from frequents
   where perweek >= all (select perweek from frequents)""",
'BAR   | PERWEEK | DRINKER\n=========================\nlolas | 6       | lola   '),
        ])

    def testAll2(self):
        self.runQueries([
("""select BAR,PERWEEK,DRINKER from frequents
   where perweek <= all (select perweek from frequents)""",
'BAR      | PERWEEK | DRINKER\n============================\nfrankies | 0       | pierre '),
        ])

    def testAll3(self):
        self.runQueries([
("""select BAR,PERWEEK,DRINKER from frequents f1
   where perweek = all
   (select perweek from frequents f2
    where f1.drinker = f2.drinker)""",
'BAR      | PERWEEK | DRINKER\n============================\nlolas    | 1       | adam   \ncheers   | 5       | sam    \njoes     | 2       | wilt   \nlolas    | 6       | lola   \nfrankies | 0       | pierre '),
        ])

    def testAll4(self):
        self.runQueries([
("""select BAR,PERWEEK,DRINKER from frequents f1
   where perweek <> all
   (select perweek from frequents f2
    where f1.drinker <> f2.drinker)""",
'BAR      | PERWEEK | DRINKER\n============================\ncheers   | 3       | norm   \nlolas    | 6       | lola   \nfrankies | 0       | pierre '),
        ])

    def testAll5(self):
        self.runQueries([
("""select beer from serves
   where beer <> all (select beer from likes)""",
'BEER     \n=========\nsamaddams\nsamaddams\nsnafu    '),
        ])

    def testExcept(self):
        self.runQueries([
("""select drinker from likes except select drinker from frequents""",
'DRINKER\n=======\nnan    '),
        ])

    def testIntersect(self):
        self.runQueries([
("""select drinker from likes
    intersect select drinker from frequents
    order by drinker""",
'DRINKER\n=======\nadam   \nlola   \nnorm   \nsam    \nwilt   \nwoody  '),
        ])

    def testStringComparison1(self):
        self.runQueries([
("""select BAR,PERWEEK,DRINKER from frequents
   where drinker>'norm'""",
'BAR      | PERWEEK | DRINKER\n============================\ncheers   | 5       | woody  \ncheers   | 5       | sam    \njoes     | 2       | wilt   \nlolas    | 1       | woody  \nfrankies | 0       | pierre '),
        ])

    def testStringComparison2(self):
        self.runQueries([
("""select BAR,PERWEEK,DRINKER from frequents
   where drinker<='norm'""",
'BAR    | PERWEEK | DRINKER\n==========================\nlolas  | 1       | adam   \ncheers | 3       | norm   \njoes   | 1       | norm   \nlolas  | 6       | lola   \nlolas  | 2       | norm   '),
        ])

    def testStringComparison3(self):
        self.runQueries([
("""select BAR,PERWEEK,DRINKER from frequents
   where drinker>'norm' or drinker<'b'""",
'BAR      | PERWEEK | DRINKER\n============================\nlolas    | 1       | adam   \ncheers   | 5       | woody  \ncheers   | 5       | sam    \njoes     | 2       | wilt   \nlolas    | 1       | woody  \nfrankies | 0       | pierre '),
        ])

    def testStringComparison4(self):
        self.runQueries([
("""select BAR,PERWEEK,DRINKER from frequents
   where drinker<>'norm' and 'pierre'<>drinker""",
'BAR    | PERWEEK | DRINKER\n==========================\nlolas  | 1       | adam   \ncheers | 5       | woody  \ncheers | 5       | sam    \njoes   | 2       | wilt   \nlolas  | 6       | lola   \nlolas  | 1       | woody  '),
        ])

    def testStringComparison5(self):
        self.runQueries([
("""select BAR,PERWEEK,DRINKER from frequents
   where drinker<>'norm'""",
'BAR      | PERWEEK | DRINKER\n============================\nlolas    | 1       | adam   \ncheers   | 5       | woody  \ncheers   | 5       | sam    \njoes     | 2       | wilt   \nlolas    | 6       | lola   \nlolas    | 1       | woody  \nfrankies | 0       | pierre '),
        ])

    def testStringComparison6(self):
        self.runQueries([
("""select (drinker+' ')*2+bar
   from frequents
   where drinker>bar""",
'(((FREQUENTS.DRINKER)+( ))*(2))+(FREQUENTS.BAR)\n===============================================\nwoody woody cheers                             \nsam sam cheers                                 \nnorm norm cheers                               \nwilt wilt joes                                 \nnorm norm joes                                 \nnorm norm lolas                                \nwoody woody lolas                              \npierre pierre frankies                         '),
        ])

    def testExists1(self):
        self.runQueries([
("""select QUANTITY,BEER,PERWEEK,DRINKER,S.BAR,F.BAR
   from frequents as f, serves as s
   where f.bar = s.bar and
     not exists(
       select l.drinker, l.beer
       from likes l
       where l.drinker=f.drinker and s.beer=l.beer)
    order by QUANTITY,BEER,PERWEEK,DRINKER,S.BAR,F.BAR""",
'QUANTITY | BEER      | PERWEEK | DRINKER | BAR      | F.BAR   \n==============================================================\n5        | snafu     | 0       | pierre  | frankies | frankies\n13       | samaddams | 1       | norm    | joes     | joes    \n13       | samaddams | 2       | wilt    | joes     | joes    \n217      | bud       | 2       | wilt    | joes     | joes    \n255      | samaddams | 3       | norm    | cheers   | cheers  \n255      | samaddams | 5       | sam     | cheers   | cheers  \n255      | samaddams | 5       | woody   | cheers   | cheers  \n333      | pabst     | 1       | adam    | lolas    | lolas   \n333      | pabst     | 2       | norm    | lolas    | lolas   \n333      | pabst     | 6       | lola    | lolas    | lolas   \n500      | bud       | 5       | woody   | cheers   | cheers  \n1515     | mickies   | 1       | adam    | lolas    | lolas   \n1515     | mickies   | 1       | woody   | lolas    | lolas   \n1515     | mickies   | 2       | norm    | lolas    | lolas   \n2222     | mickies   | 1       | norm    | joes     | joes    \n2222     | mickies   | 2       | wilt    | joes     | joes    '),
        ])

    def testExists2(self):
        self.runQueries([
("""select QUANTITY,BAR,BEER
   from serves s
   where not exists (
     select *
     from likes l, frequents f
     where f.bar = s.bar and f.drinker=l.drinker
     and s.beer=l.beer)""",
'QUANTITY | BAR      | BEER       \n=================================\n255      | cheers   | samaddams  \n13       | joes     | samaddams  \n2222     | joes     | mickies    \n432      | winkos   | rollingrock\n5        | frankies | snafu      '),
        ])

    def testExists3(self):
        self.runQueries([
("""select 'nonbeer drinker '+f.drinker
   from frequents f
   where not exists
      (select l.drinker, l.beer from likes l
      where l.drinker=f.drinker)""",
'(nonbeer drinker )+(F.DRINKER)\n==============================\nnonbeer drinker pierre        '),
        ])

    def testExists4(self):
        self.runQueries([
("""select l.drinker+' likes '+l.beer+' but goes to no bar'
   from likes l
   where not exists (select f.drinker from frequents f
   where f.drinker=l.drinker)""",
'(((L.DRINKER)+( likes ))+(L.BEER))+( but goes to no bar)\n========================================================\nnan likes sierranevada but goes to no bar               '),
        ])

    def testDistinct(self):
        self.runQueries([
("""select distinct bar from frequents order by bar""",
'BAR     \n========\ncheers  \nfrankies\njoes    \nlolas   '),
        ])

    def Aggregations1(self):
        self.runQueries([
("""select sum(quantity), avg(quantity), count(*),
sum(quantity)/count(quantity) from serves""",
'Sum(SERVES.QUANTITY) | Average(SERVES.QUANTITY) | Count(*) | (Sum(SERVES.QUANTITY))/(Count(SERVES.QUANTITY))\n============================================================================================================\n5492                 | 610.222222222            | 9        | 610                                            '),
        ])

    def Aggregations2(self):
        self.runQueries([
("""select beer, sum(quantity), avg(quantity), count(*),
sum(quantity)/count(quantity)
   from serves
   group by beer""",
'BEER        | Sum(SERVES.QUANTITY) | Average(SERVES.QUANTITY) | Count(*) | (Sum(SERVES.QUANTITY))/(Count(SERVES.QUANTITY))\n==========================================================================================================================\npabst       | 333                  | 333.0                    | 1        | 333                                            \nmickies     | 3737                 | 1868.5                   | 2        | 1868                                           \nbud         | 717                  | 358.5                    | 2        | 358                                            \nsnafu       | 5                    | 5.0                      | 1        | 5                                              \nrollingrock | 432                  | 432.0                    | 1        | 432                                            \nsamaddams   | 268                  | 134.0                    | 2        | 134                                            '),
        ])

    def Aggregations3(self):
        self.runQueries([
("""select sum(quantity), avg(quantity), count(*),
sum(quantity)/count(quantity)
   from serves
   where beer<>'bud'""",
'Sum(SERVES.QUANTITY) | Average(SERVES.QUANTITY) | Count(*) | (Sum(SERVES.QUANTITY))/(Count(SERVES.QUANTITY))\n============================================================================================================\n4775                 | 682.142857143            | 7        | 682                                            '),
        ])

    def Aggregations4(self):
        self.runQueries([
("""select bar, sum(quantity), avg(quantity), count(*),
sum(quantity)/count(quantity)
   from serves
   where beer<>'bud'
   group by bar
   having sum(quantity)>500 or count(*)>3
   order by 2 desc""",
'BAR   | Sum(SERVES.QUANTITY) | Average(SERVES.QUANTITY) | Count(*) | (Sum(SERVES.QUANTITY))/(Count(SERVES.QUANTITY))\n====================================================================================================================\njoes  | 2235                 | 1117.5                   | 2        | 1117                                           \nlolas | 1848                 | 924.0                    | 2        | 924                                            '),
        ])

    def Aggregations5(self):
        self.runQueries([
("""select beer, sum(quantity), avg(quantity), count(*)
   from serves
   where beer<>'bud'
   group by beer
   having sum(quantity)>100
   order by 4 desc, beer""",
'BEER        | Sum(SERVES.QUANTITY) | Average(SERVES.QUANTITY) | Count(*)\n========================================================================\nmickies     | 3737                 | 1868.5                   | 2       \nsamaddams   | 268                  | 134.0                    | 2       \npabst       | 333                  | 333.0                    | 1       \nrollingrock | 432                  | 432.0                    | 1       '),
        ])

    def Aggregations6(self):
        self.runQueries([
("""select l.drinker, l.beer, count(*), sum(l.perday*f.perweek)
   from likes l, frequents f
   where l.drinker=f.drinker
   group by l.drinker, l.beer
   order by 4 desc, l.drinker, l.beer""",
'DRINKER | BEER        | Count(*) | Sum((L.PERDAY)*(F.PERWEEK))\n==============================================================\nlola    | mickies     | 1        | 30                         \nnorm    | rollingrock | 3        | 18                         \nnorm    | bud         | 3        | 12                         \nwoody   | pabst       | 2        | 12                         \nsam     | bud         | 1        | 10                         \nadam    | bud         | 1        | 2                          \nwilt    | rollingrock | 1        | 2                          '),
        ])

    def Aggregations7(self):
        self.runQueries([
("""select l.drinker, l.beer, f.bar, l.perday, f.perweek
   from likes l, frequents f
   where l.drinker=f.drinker
   order by l.drinker, l.perday desc, f.perweek desc""",
'DRINKER | BEER        | BAR    | PERDAY | PERWEEK\n=================================================\nadam    | bud         | lolas  | 2      | 1      \nlola    | mickies     | lolas  | 5      | 6      \nnorm    | rollingrock | cheers | 3      | 3      \nnorm    | rollingrock | lolas  | 3      | 2      \nnorm    | rollingrock | joes   | 3      | 1      \nnorm    | bud         | cheers | 2      | 3      \nnorm    | bud         | lolas  | 2      | 2      \nnorm    | bud         | joes   | 2      | 1      \nsam     | bud         | cheers | 2      | 5      \nwilt    | rollingrock | joes   | 1      | 2      \nwoody   | pabst       | cheers | 2      | 5      \nwoody   | pabst       | lolas  | 2      | 1      '),
        ])

    def testDynamicQueries(self):
        # DYNAMIC QUERIES
        dynamic_queries = [
            ( "select bar from frequents where drinker=?", ("norm",) ),
            ( "select * from frequents where drinker=? or bar=?",
                ("norm", "cheers") )
        ]
        for (x,y) in dynamic_queries:
            self.curs.execute(x, y)
            all = self.curs.fetchall()

    def testRepeatQueries(self):
        # "repeat test"
        repeats = [
            """-- drinkers bars and beers
               -- where the drinker likes the beer
               -- the bar serves the beer
               -- and the drinker frequents the bar
               select f.drinker, l.beer, s.bar
               from frequents f, serves s, likes l
               where f.drinker=l.drinker and s.bar=f.bar and s.beer=l.beer""",
            """select *
               from frequents as f, serves as s
               where f.bar = s.bar and
                 not exists(
                   select l.drinker, l.beer
                   from likes l
                   where l.drinker=f.drinker and s.beer=l.beer)""",
            """select * from frequents
               where drinker = 'norm'""",
        ]
        for x in repeats:
            #print "repeating", x
            #now = time.time()
            self.curs.execute(x)
            #print time.time()-now, "first time"
            #now = time.time()
            self.curs.execute(x)
            #print time.time()-now, "second time"
            #now = time.time()
            self.curs.execute(x)
            #print time.time()-now, "third time"

    def testArgh(self):
        sqls = ("""
            select bar, sum(quantity), avg(quantity),
                    count(*), sum(quantity)/count(quantity)
               from serves
               where beer<>'bud'
               group by bar
               having sum(quantity)>500 or count(*)>3
               order by 2 desc
            """,
            """
                select bar, sum(quantity),count(*)
                   from serves
                   group by bar
            """,
            """
                select bar, sum(quantity)
                   from serves
                   group by bar
                   having sum(quantity) > 2000 or sum(quantity) > 1
            """,
            """
                select bar, sum(quantity)
                   from serves
                   group by bar
                   having sum(quantity) > 2000 or sum(quantity) > 200
            """,
            """
            select bar, sum(quantity)
               from serves
               group by bar
               having sum(quantity) > 1000 or sum(quantity) > 1
            """,
        )
        for stmt in sqls:
            self.curs.execute(stmt)

class test_GadflyRollback(harness):

    def test(self):
        self.connect.autocheckpoint = 0

        keep_updates = [
            """insert into frequents(drinker, bar, perweek)
               values ('peter', 'pans', 1)""",
            """create view alldrinkers as
                select drinker from frequents
                union
                select drinker from likes""",
        ]
        for x in keep_updates:
            self.curs.execute(x)
        self.connect.commit()
#        self.connect.dumplog()
        preresults = []

        rollback_queries = [
            """select * from likes""",
            """select * from frequents""",
            """select * from nondrinkers""",
            """select * from alldrinkers""",
            """select * from dummy""",
        ]
        for s in rollback_queries:
            try:
                self.curs.execute(s)
                preresults.append(self.curs.fetchall())
            except:
                d = sys.exc_type
                preresults.append(d)

        rollback_updates = [
            """create table dummy (nothing varchar)""",
            """insert into frequents(drinker, bar, perweek)
               values ('nobody', 'nobar', 0)""",
            """insert into likes(drinker, beer, perday)
               values ('wally', 'nobar', 0)""",
            """drop view alldrinkers""",
        ]
        for s in rollback_updates:
            self.curs.execute(s)

        for dummy in (1,2):
            postresults = []
            for s in rollback_queries:
                try:
                    self.curs.execute(s)
                    postresults.append(self.curs.fetchall())
                except:
                    d = sys.exc_type
                    postresults.append(d)
            if dummy==1:
                self.assert_(preresults != postresults)
                self.connect.rollback()
            else:
                self.assert_(preresults == postresults)

        for s in rollback_updates:
            self.curs.execute(s)
        for dummy in (1,2):
            postresults = []
            for s in rollback_queries:
                try:
                    self.curs.execute(s)
                    postresults.append(self.curs.fetchall())
                except:
                    d = sys.exc_type
                    postresults.append(d)
            if dummy==1:
                self.assert_(preresults != postresults)
#                self.connect.dumplog()
                self.connect.restart()
            else:
                self.assert_(preresults == postresults)

class test_GadflyReconnect(harness):
    def testClose(self):
        self.connect.commit()
        self.connect.close()
        self.connect = gadfly("test", '_test_dir')
        self.curs = self.connect.cursor()
        self.runTest()

    def testRestart(self):
        self.connect.restart()
        self.curs = self.connect.cursor()
        self.runTest()

    def runTest(self):
        updates = [
            """select * from frequents""",
            """select * from likes""",
            """select * from serves""",

            """select count(*), d from nondrinkers group by d""",
            """insert into frequents (drinker, perweek, bar)
               values ('billybob', 4, 'cheers')""",
            """select * from nondrinkers""",
            """create table templikes (dr varchar, be varchar)""",
            """select * from templikes""",
            """insert into templikes(dr, be)
               select drinker, beer from likes""",
            """create index tdindex on templikes(dr)""",
            """create index tbindex on templikes(be)""",
            """select * from templikes""",
            """delete from templikes where be='rollingrock' """,
            """select * from templikes""",
            """update templikes set dr=dr+'an' where dr='norm' """,
            """drop index tdindex""",
            """delete from templikes
               where dr=(select min(dr) from templikes)""",
            """insert into templikes (dr, be)
               select max(dr), min(be) from templikes""",
            """select * from templikes""",
            """select * from frequents""",
            """update frequents
               set perweek=(select max(perweek)
                            from frequents
                            where drinker='norm')
               where drinker='woody'""",
            """select * from frequents""",
            """create view lazy as
               select drinker, sum(perweek) as wasted
               from frequents
               group by drinker
               having sum(perweek)>4
               order by drinker""",
            """select * from lazy""",
            """drop view lazy""",
            """drop table templikes""",
        ]
        for s in updates:
            self.curs.execute(s)
        self.connect.commit()

def suite():
    l = [
        unittest.makeSuite(test_Gadfly),
        unittest.makeSuite(test_GadflyRollback),
        unittest.makeSuite(test_GadflyReconnect),
    ]
    return unittest.TestSuite(l)

if __name__ == '__main__':
    runner = unittest.TextTestRunner()
    runner.run(suite())

#
# $Log: test_gadfly.py,v $
# Revision 1.8  2002/05/19 01:54:24  richard
# - close db before removal in tests
#
# Revision 1.7  2002/05/11 02:59:05  richard
# Added info into module docstrings.
# Fixed docco of kwParsing to reflect new grammar "marshalling".
# Fixed bug in gadfly.open - most likely introduced during sql loading
# re-work (though looking back at the diff from back then, I can't see how it
# wasn't different before, but it musta been ;)
# A buncha new unit test stuff.
#
# Revision 1.6  2002/05/08 00:49:01  anthonybaxter
# El Grande Grande reindente! Ran reindent.py over the whole thing.
# Gosh, what a lot of checkins. Tests still pass with 2.1 and 2.2.
#
# Revision 1.5  2002/05/07 09:58:19  anthonybaxter
# all tests pass again. need to make a more thorough test
# suite, really.
#
# Revision 1.4  2002/05/07 04:39:30  anthonybaxter
# split out the broken test all by it's lonesome.
#
# Revision 1.3  2002/05/07 04:03:14  richard
# . major cleanup of test_gadfly
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
