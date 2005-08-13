/*
kjbuckets C extension to Python.

Author: Aaron Watters
        Department of Computer and Information Sciences
        New Jersey Institute of Technology
        University Heights
        Newark, NJ 07102
                phone (201)596-2666
		fax (201)596-5777
		home phone (908)545-3367
		email: aaron@vienna.njit.edu

Adapted for Python 2.0 by Berthold Höllmann <bhoel@starship.python.net>
   and Oleg Broytmann <phd2@earthling.net>.

This file defines three Python datatypes (kjSet, kjGraph, and kjDict)
which share a common representational and procedural infrastructure:
a hash table with table driven behavior.

[ want to add
  .keys(n) -- pick n keys, Null == all
  want to make the deletion algorithm more complicated and faster!
]
================================================
A hint at the table structure:  

By setting WDEBUGPRINT and recompiling the structure of tables can be
examined using python.  Below we have a Graph constructed and examined
with OVLFACT of 1 and GSIZE 2.

>>> G = kjGraph()
>>> for i in range(15): G[i%5] = i%3
... 
>>> G
Table (size=14, basesize=7, entries=15, free=9, GRAPH)
0: ROOT(next=3)Group:Bkt[0, 0, 0] Bkt[0, 0, 1] 
1: ROOT(next=13)Group:Bkt[-131071, 1, 1] Bkt[-131071, 1, 0] 
2: ROOT(next=7)Group:Bkt[-393213, 3, 0] Bkt[-393213, 3, 2] 
3: OVFLW(next=0)Group:Bkt[0, 0, 2] Bkt[-1, NULL, NULL] 
4: OVFLW(next=5)Group:Bkt[-262142, 2, 0] Bkt[-1, NULL, NULL] 
5: ROOT(next=4)Group:Bkt[-262142, 2, 2] Bkt[-262142, 2, 1] 
6: ROOT(next=8)Group:Bkt[-524284, 4, 0] Bkt[-524284, 4, 1] 
7: OVFLW(next=2)Group:Bkt[-393213, 3, 1] Bkt[-1, NULL, NULL] 
8: OVFLW(next=6)Group:Bkt[-524284, 4, 2] Bkt[-1, NULL, NULL] 
9: FREE next=10, prev=12
10: FREE next=11, prev=9
11: FREE next=12, prev=10
12: FREE next=9, prev=11
13: OVFLW(next=1)Group:Bkt[-131071, 1, 2] Bkt[-1, NULL, NULL] 
>>> 

The basic unit for archiving is the bucket, which contains a hash
value (where -1 represents "No value"), a key object pointer and (for
dicts and graphs) a map object pointer.  The different behaviors for
the tables are determined primarily by the different behaviors of the
bucket structures under the appropriate interpretation.
Interpretations are indicated by flags from enum BucketFlag.

The table is an array of bucket groups, with each bucket group
containing 2 (GSIZE) buckets.  The table has a base size of 7, so all
hash index loops are rooted between indices 0 and 6.  Thus an item
with hash 23 will be placed in the hash sequence rooted at 23%7 = 2.
Hash index loops consist of a root group and possibly one or more
linked overflow groups arranged in a circular list (embedded in the
array).  For example the arcs with source 1 are rooted at index 1 with
one overflow group at index 13.

The code assumes in several places that any used group with "undefined
entries" is the last group in its hash index loop and all undefines
are at the higher indices of the group.

Dedicated overflow groups:
In this case 7 (basesize / OVLFACT) additional groups have been
allocated with indices 7..13 which can only be used as overflow
groups.  Those groups which are not used either as a root or an
overflow are kept in a circular free list with head at index 9.

This basic table structure has 3 encarnations:
   kjSet represent "sets of hashable objects."
     It has a smaller Bucket size which archives only one object.
   kjDict represents only relations that are 
     "partial functions from hashable objects to objects."
   kjGraph represents arbitrary relations from hashable objects to objects.
Both kjDict's and kjGraph's are indexed "on the left" only.
The behavior of tables under the differing interpretations are
determined primarily by the behavior of the function BPtrMatch
which defines what it means for a Bucket to match a key/map pair
under the differing interpretations.

*/

/* include a bunch of stuff */

#include "Python.h"
/* #include "rename2.h" */
/* #include "allobjects.h" */
/* #include "modsupport.h" */
/* #include "ceval.h" */
#ifdef STDC_HEADERS
#include <stddef.h>
#else
#include <sys/types.h>
#endif

/* THE FOLLOWING IS HISTORICAL AND NOT NEEDED */
/* define this flag to remove stuff which won't link under 1.2 */
/* #define PYTHON1DOT2 1 */
/* PROBLEM FIXED */

/* flag to enable optional debug printing during execution
   turned on/off by kjbuckets.debug() from python */

/* #define KJBDEBUG 1 */

#ifdef KJBDEBUG
static long DebugLevel = 0;
/* usage: Dprint(("this is an long %ld",i)); */
#define Dprint(x) if (DebugLevel) printf x 
#else
#define Dprint(x) {}
#endif

/***************************************************************/
/** local parameters                                          **/

/* if set, this changes printing to show internal structure of table */
/* if undefined, the debug printing will be omitted */
/* #define WDEBUGPRINT 0 */

/* overflow fudge factor, low values mean more fudge
     array size = basesize + basesize/OVLFACT
   extra space is used only for overflows
*/
#define OVLFACT 1

/* group size for each bucket group, smaller means faster/bigger 
   (roughly)
*/
#define GSIZE 4

/* if you redefine OVLFACT, better rethink the following macro
   which is designed to force a resize to a size large enough for
   additional inserts.
   !!!AN INFINITE RECURSION WILL RESULT IF THE RESULTING TABLE IS
      NOT LARGE ENOUGH!!!
 */

#define RESIZEUPSIZE(tp) ( tp->basesize * GSIZE + 1 )

/* resize down when fewer than 1/RESIZEFACTOR buckets are used */
#define RESIZEFACTOR 8

/* don't resize down if size is smaller than this */
#define RESIZETHRESHOLD 16

/* the test for resizing down */
#define RESIZEDOWNTEST(tp) \
   ( (tp->size > RESIZETHRESHOLD) && \
     ( (tp->entries * RESIZEFACTOR) < (tp->size * GSIZE) ) )

/* group states */
#ifdef OVERFLOW
#undef OVERFLOW
#endif
enum GState { UNKNOWN, FREE, ROOT, OVERFLOW };

/* bucket behaviors, smaller is less general! */
enum BucketFlag { SETFLAG=0, DICTFLAG=1, GRAPHFLAG=2 };

/* special invalid hash value (from python convention) */
#define NOHASH ( (long) -1 )

/* to force or not to force insertions during lookups */
enum ForceFlag { FORCE=1, NOFORCE=0 };

/* macro for getting hash values (snarfed from mappingobject.c) */

#ifdef CACHE_HASH 
#define GETHASH(hashvalue, object) \
     if (!PyString_Check(object) || \
         (hashvalue = ((PyStringObject *) object)->ob_shash) == -1)\
        hashvalue = PyObject_Hash(object)
#else
#define GETHASH(hashvalue, object) hashvalue = PyObject_Hash(object)
#endif

/*********************************************************/
/* bucket methods                                       **/

/* set bucket structure */
typedef struct {
  long hash;
  PyObject * member;
} SetBucket;

/* graph and dict bucket structure */
typedef struct {
  long hash;
  PyObject * member;
  PyObject * map;
} DiBucket;

/* for passing general buckets around, with external flags */
typedef union {
  SetBucket * SBucketp;
  DiBucket * DBucketp;
} Bucketptr;

/* destructuring a bucket (macroized) */
#define BPtrDestructure(/*Bucketptr*/ Bp, /*enum BucketFlag*/ flag,\
			   /*long*/ hp, /*PyObject*/ memp, /*PyObject*/ mapp)\
{\
  switch (flag) {\
  case SETFLAG:\
    hp = Bp.SBucketp->hash;\
    memp = Bp.SBucketp->member;\
    mapp = memp; /* map is copy of memp */\
    break;\
  case DICTFLAG:\
  case GRAPHFLAG:\
    hp = Bp.DBucketp->hash;\
    memp = Bp.DBucketp->member;\
    mapp = Bp.DBucketp->map;\
    break;\
  }\
}

#ifdef WDEBUGPRINT
/* testing only */
static long BPtrDump(Bucketptr Bp, enum BucketFlag flag, FILE *fp)
{
  long h;
  PyObject *mem, *map;
  BPtrDestructure(Bp, flag, h, mem, map);
  fprintf(fp, "Bkt[%ld, ",h);
  if (mem == 0) { fprintf(fp, "NULL"); }
  /*else {
    if (PyObject_Print(mem, fp, 0) != 0) { return -1; }
  }*/
  fprintf(fp, "%ld, ",mem);
  if (map == 0) { fprintf(fp, "NULL"); }
  /*else {
    if (PyObject_Print(map, fp, 0) != 0) { return -1; }
  }*/
  fprintf(fp, "%ld] ",map);
  return 0;
}
#endif

/* setting a bucket
   Py_INCREFs handled here.
   assumes initial contents are null or garbage. (macroized)
*/
/* static long */
#define BPtrSet( \
	    /* Bucketptr */ Bp, /* enum BucketFlag */ flag,\
	    /* long */ h, /* PyObject * */mem1, /* PyObject * */map1)\
{\
  switch(flag) {\
  case SETFLAG:\
    if ((mem1==0)&&(h!=NOHASH)) Dprint(("setting mem to 0, hash =%ld\n",h));\
    /* ignore map */\
    Bp.SBucketp->hash = h;\
    Bp.SBucketp->member = mem1;\
    if (mem1 != 0) { Py_XINCREF (mem1); }\
    break;\
  case DICTFLAG:\
  case GRAPHFLAG:\
    Bp.DBucketp->hash = h;\
    Bp.DBucketp->member = mem1;\
    if (mem1 != 0) { Py_XINCREF (mem1); }\
    Bp.DBucketp->map = map1;\
    if (map1 != 0) { Py_XINCREF (map1); }\
    break;\
  }\
}

/* initialization assuming invalid value -- not used.
   (no decrefs, could macroize) 
*/
/*static long BPtrInit( Bucketptr Bp, enum BucketFlag flag )
{
  PyObject *dummy;
  dummy = 0;
  BPtrSet( Bp, flag, NOHASH, dummy, dummy );
}*/

/* re-initialization assuming valid value 
   Py_DECREFs handled here.
   to save values in the bucket for use after reinitialization,
   incref them first and decref after...
   (macroized)
*/
/*static void*/
#define BPtrReInit( /*Bucketptr*/ Bp, /*enum BucketFlag*/ flag )\
{\
  long hashBBB;\
  PyObject *MemberBBB = 0, *MapBBB = 0, *dummyBBB = 0;\
  BPtrDestructure( Bp, flag, hashBBB, MemberBBB, MapBBB );\
  if ( MemberBBB != 0 ) { Py_DECREF(MemberBBB); }\
  /* don't decref map for sets!! */\
  if ( (MapBBB != 0) && (flag != SETFLAG) ) { Py_DECREF(MapBBB); }\
  dummyBBB = 0;\
  BPtrSet( Bp, flag, NOHASH, dummyBBB, dummyBBB );\
}

/* returns 1 on match, 0 no match, -1 error
   newflag is set if new entry, else reset
   dirtyflag is set if this is a forced overwrite, else left alone
*/
/* static long  */
#define BPtrMatch(/*int*/ result,\
		  /*Bucketptr*/ Bp, \
		  /*enum BucketFlag*/ flag,\
		  /*long*/ h, \
		  /*PyObject * */ Mm, \
		  /*PyObject * */ Mp, \
		  /*enum ForceFlag*/ Force,\
		  /*long * */ newflag, \
		  /*long * */ dirtyflag) \
{\
  long hashAAA = 0;\
  PyObject *MemberAAA = 0, *MapAAA = 0, *dummyAAA = 0;\
  newflag = 0; /* default assumption */\
  result = 0; /* default: fail */\
  BPtrDestructure( Bp, flag, hashAAA, MemberAAA, MapAAA );\
  switch (flag) {\
  case SETFLAG:\
    /* ignore maps */\
    if ( ( hashAAA == NOHASH) && (h != NOHASH)) { \
      /* force it? */\
      if (Force == FORCE) {\
	dummyAAA = 0;\
	BPtrSet( Bp, flag, h, Mm, dummyAAA );\
	newflag = 1; /* entry is new */\
	result = 1; /* forced match on empty bucket */\
      }\
    } else {\
      if (hashAAA != NOHASH) {\
	/* null match */\
	if (h == NOHASH)\
	  { result = 1; }  /* bucket full, hash null == null match */\
	else { /* fully defined match */\
	  if ((h == hashAAA) && (PyObject_Compare(Mm, MemberAAA)==0))\
	    { result = 1; } /* hash defined, all eq == match */\
	}\
      }\
    }\
    break;\
  case DICTFLAG:\
    /* null match case */\
    if ((h == NOHASH) && (hashAAA != NOHASH)) { result = 1; }\
    else {\
      /* Forced match succeeds if bucket is empty or members match */\
      if ((Force == FORCE) &&\
	  ( (hashAAA == NOHASH) || \
	  ((h == hashAAA)&&(PyObject_Compare(Mm, MemberAAA)==0)) ) ) {\
	if ((Mm == 0) || (Mp == 0)) { result = -1; } /* error */\
	else {\
	  if (hashAAA == NOHASH) { newflag = 1; } /* new if old was empty */\
	  else {\
	    if (PyObject_Compare(MapAAA,Mp)!=0) { /* overwriting: dirty */\
	      dirtyflag = 1;\
	    }\
	  }\
	  BPtrReInit( Bp, flag );\
	  BPtrSet( Bp, flag, h, Mm, Mp );\
	  result = 1; /* successful forced match */\
	}\
      } else {\
	if ( (h!=NOHASH) && (h==hashAAA) &&\
	     (Mm != 0) && (PyObject_Compare(Mm, MemberAAA)==0) &&\
	     ( ( Mp == 0 ) || (PyObject_Compare(MapAAA,Mp)==0) ) )\
	  { result = 1; } /* successful unforced match */\
      }\
    }\
    break;\
  case GRAPHFLAG:\
    if ( ( h == NOHASH ) && (hashAAA != NOHASH) ) { \
      Dprint(("graph null match\n")); \
      result = 1; /* null match */\
    } else {\
      /* force only on empty buckets */\
      if ( ( hashAAA == NOHASH ) && (Force == FORCE) ) {\
	if ( (h==NOHASH) || (Mm==0) || (Mp==0) ) { \
          Dprint(("graph match error\n")); \
          result = -1; /* error */\
	} else {\
          Dprint(("graph forced match\n")); \
	  BPtrReInit( Bp, flag );\
	  BPtrSet( Bp, flag, h, Mm, Mp );\
	  newflag = 1;\
	  result = 1; /* successful forced match */\
	}\
      } else {\
	/* unforced match, can match if Mm is null */\
	if (( hashAAA != NOHASH ) && ( hashAAA == h ) &&\
	    (Mm != 0) && ( PyObject_Compare(Mm,MemberAAA)==0 ) && \
	    ( (Mp == 0) || ( PyObject_Compare(MapAAA,Mp)==0 ))) {\
          Dprint(("graph unforced match\n")); \
	  result = 1; /* successful unforced match */\
	}\
      }\
    }\
    break;\
  default:\
    /* error case */\
    result = -1;\
    break;\
  }\
}

/*************************************************************/
/**  group methods                                           **/

/* array types for bucket groupings */
typedef SetBucket SBuckets[GSIZE];
typedef DiBucket DBuckets[GSIZE];

/* free group template */
typedef struct {
  long Next;
  long Previous;
} FreeGroup;

/* DiBucket group template */
typedef struct {
  long Next;
  DBuckets Buckets;
} DBGroup;

/* SetBucket group template */
typedef struct {
  long Next;
  SBuckets Buckets;  
} SBGroup;

/* SetGroup structure */
typedef struct {
  enum GState State;
  union {
    FreeGroup free;
    SBGroup group;
  } mem;
} SetGroup;

/* DiGroup structure */
typedef struct {
  enum GState State;
  union {
    FreeGroup free;
    DBGroup group;
  } mem;
} DiGroup;

/* union of different group template pointer types */
typedef union {
  FreeGroup *fgp;
  DBGroup *dbp;
  SBGroup *sbp;
} Groupptr;

/* get a bucket from a group 
   (macroized)
*/
/*static Bucketptr*/
#define GetBucket(/*Bucketptr * */ Bp, \
                  /*Groupptr*/ g, \
                  /*enum BucketFlag*/ flag, \
                  /*int*/ index)\
{\
  if (index>GSIZE) Dprint((" BAD INDEX IN GETBUCKET %ld \n", index));\
  switch(flag){\
  case SETFLAG:\
    Bp.SBucketp = &(g.sbp->Buckets[index]);\
    break;\
  case DICTFLAG:\
  case GRAPHFLAG:\
    Bp.DBucketp = &(g.dbp->Buckets[index]);\
  }\
}

/* testing for empty group -- assumes correct backfilling 
   (macroized)
*/
/*static int*/
#define GroupEmpty(/*int*/ Eresult, \
                   /*Groupptr*/ Eg, /*enum BucketFlag*/ Eflag)\
{\
  long Eh = 0;\
  PyObject *EMm, *EMp;\
  Bucketptr EBp;\
  GetBucket(EBp, Eg, Eflag, 0);\
  BPtrDestructure(EBp, Eflag, Eh, EMm, EMp);\
  if (Eh == NOHASH) { Eresult = 1; }\
  else { Eresult = 0; }\
}

/* initialize a groupptr to empty, assuming garbage initially 
   (macroized)
*/
/*static void */
#define Groupinit(/*Groupptr*/ Dg, /*enum BucketFlag*/ Dflag)\
{\
  Bucketptr DBp;\
  PyObject *Ddummy;\
  long Di;\
  Ddummy = 0;\
  for  (Di=0; Di<GSIZE; Di++) {\
    GetBucket(DBp, Dg, Dflag, Di);\
    BPtrSet(DBp, Dflag, NOHASH, Ddummy, Ddummy);\
  }\
}

#ifdef WDEBUGPRINT
/* test printing */
static long GroupDump(Groupptr g, enum BucketFlag flag, FILE *fp)
{
  Bucketptr Bp;
  long i;
  fprintf(fp, "Group:");
  for (i=0; i<GSIZE; i++) {
    GetBucket(Bp, g, flag, i);
    if (BPtrDump(Bp,flag,fp) != 0) { return -1; }
  }
  fprintf(fp, "\n");
  return 0;
}
#endif

/* copy one group to another 
   could be macroized
*/
/*static void */
#define GroupCopy(/*Groupptr*/ gto, \
                  /*Groupptr*/ gfrom, \
                  /*enum BucketFlag*/ flag)\
{\
  switch(flag) {\
  case SETFLAG:\
    *(gto.sbp) = *(gfrom.sbp);\
    break;\
  case DICTFLAG:\
  case GRAPHFLAG:\
    *(gto.dbp) = *(gfrom.dbp);\
    break;\
  }\
}

/* find a match within a group returns 1 if found else 0 
   could macroize
*/
/* isnew and dirtyflag are as in BPtrMatch */
/* static long */
#define groupmatch(   /* long */ result,  \
                      /* Groupptr */ g, \
		      /* enum BucketFlag */ flag,\
		      /* long */ hash1, \
		      /* PyObject * */ Member1, \
		      /* PyObject * */ Map1, \
		      /* enum ForceFlag */ Force, \
		      /* long */ StartAfter,\
		      /* long * */ index, /* use literal */\
		      /* Bucketptr * */ Bp, /* use literal */\
		      /* long * */ isnew, /* use literal */\
		      /* long * */ dirtyflag ) /* use literal */\
{\
  long iCCC;\
  result = 0; /* assumption */\
  for (iCCC=StartAfter+1; iCCC<GSIZE; iCCC++) {\
    GetBucket(Bp,g,flag,iCCC);\
    BPtrMatch(result, Bp, flag, hash1, Member1, Map1, Force, \
              isnew, dirtyflag);\
    if (result) {\
      index = iCCC;\
      break;\
    }\
  }\
}

/* array of groups union */
typedef union {
  DiGroup * Dgroups;
  SetGroup * Sgroups;
} GroupArray;

/***************************************************************/
/**  Group Array methods                                      **/

/* 
 get templateptr and stateptr from array of groups
 macroized
*/
/* static void */
#define GArrayRef(/* GroupArray */ g, \
		  /* enum BucketFlag */ flag, \
		  /* long */ index,\
	          /* Groupptr * */ templateptr, \
		  /* enum GState ** */ Stateout, \
		  /* long ** */ Nextptr)\
{\
  SetGroup *SGptr;\
  DiGroup *DGptr;\
  Dprint(("GArrayRef %ld\n",index));\
  switch (flag) {\
  case SETFLAG:\
    SGptr = &(g.Sgroups[index]);\
    Stateout = &(SGptr->State);\
    switch (SGptr->State) {\
    case FREE:\
      templateptr.fgp = &(SGptr->mem.free);\
      Nextptr = &(SGptr->mem.free.Next);\
      break;\
    case ROOT:\
    case OVERFLOW:\
    case UNKNOWN:\
      templateptr.sbp = &(SGptr->mem.group);\
      Nextptr = &(SGptr->mem.group.Next);\
    }\
    break;\
  case DICTFLAG:\
  case GRAPHFLAG:\
    DGptr = & (g.Dgroups[index]);\
    Stateout = &(DGptr->State);\
    switch (DGptr->State) {\
    case FREE:\
      templateptr.fgp = &(DGptr->mem.free);\
      Nextptr = &(DGptr->mem.free.Next);\
      break;\
    case ROOT:\
    case OVERFLOW:\
    case UNKNOWN:\
      templateptr.dbp = &(DGptr->mem.group);\
      Nextptr = &(DGptr->mem.group.Next);\
      break;\
    }\
    break;\
  }\
}

/* free group methods */
/* (macroized) */
/* static void */
#define SetFreeGroup(/*GroupArray*/ Fg, \
		     /*enum BucketFlag*/ Fflag,\
		     /*int*/ Fselfindex, \
		     /*int*/ Fnextindex, \
		     /*int*/ Fpreviousindex)\
{\
  Groupptr Fself, Fnext, Fprev;\
  long *Fdummy;\
  enum GState *FselfState = 0, *FnextState = 0, *FprevState = 0;\
  Dprint(("SetFreeGroup(self=%ld, next=%ld, prev=%ld)\n", \
	  Fselfindex, Fnextindex, Fpreviousindex));\
  GArrayRef(Fg, Fflag, Fselfindex, Fself, FselfState, Fdummy );\
  GArrayRef(Fg, Fflag, Fnextindex, Fnext, FnextState, Fdummy );\
  GArrayRef(Fg, Fflag, Fpreviousindex, Fprev, FprevState, Fdummy );\
  *FselfState = FREE;\
  Fself.fgp->Previous = Fpreviousindex;\
  Fself.fgp->Next = Fnextindex;\
  Fnext.fgp->Previous = Fselfindex;\
  Fprev.fgp->Next = Fselfindex;\
}

/* get a free group (macroized) */
/*static void*/ 
#define ExtractFreeGroup(/*GroupArray*/ Gg, \
		 /*enum BucketFlag*/ Gflag, \
		 /*int*/ Gindex )\
{\
  long Gnextindex, Gpreviousindex, *Gdummy;\
  Groupptr Gself, Gnext, Gprev;\
  enum GState *GselfState = 0, *GnextState, *GprevState;\
  Dprint(("ExtractFreeGroup %ld\n",Gindex));\
  GArrayRef(Gg, Gflag, Gindex, Gself, GselfState, Gdummy  );\
  Gnextindex = Gself.fgp->Next;\
  Gpreviousindex = Gself.fgp->Previous;\
  GArrayRef(Gg, Gflag, Gnextindex, Gnext, GnextState, Gdummy );\
  GArrayRef(Gg, Gflag, Gpreviousindex, Gprev, GprevState, Gdummy );\
  Gnext.fgp->Previous = Gpreviousindex;\
  Gprev.fgp->Next = Gnextindex;\
  *GselfState = UNKNOWN;\
}

/* for a non-free group, find previous entry in circular list */
/* macroized */
/* static long */
#define Gprevious( /*int*/ Hresult,\
		   /* enum BucketFlag */ Hflag, \
		   /*int*/ Hindex, \
		   /*GroupArray*/ Harray)\
{\
  long Hnext, HHHindex;\
  enum GState *HdummyState;\
  Groupptr Hdummytemplate;\
  long *HNptr = 0;\
  Dprint(("Gprevious %ld\n",Hindex));\
  HHHindex = Hnext = Hindex;\
  do {\
    Hresult = Hnext;\
    GArrayRef(Harray, Hflag, Hnext, Hdummytemplate, HdummyState, HNptr);\
    Hnext = *HNptr;\
    Dprint(("Gprevious at %ld %ld %ld\n", Hnext, HHHindex, Hindex));\
  } while (Hnext != HHHindex);\
  /* return Hresult; */\
}

/* remove a group from its circular list */
/* macroized */
/* static void*/
#define  Gremove( /*enum BucketFlag*/ Iflag, \
		  /*int*/ Iindex, \
		  /*GroupArray*/ Iarray)\
{\
  enum GState *IdummyState;\
  Groupptr Idummytemplate;\
  long *INext = 0, *INextOfPrev = 0;\
  long Iprevious;\
  Dprint(("Gremove %ld\n",Iindex));\
  Gprevious(Iprevious, Iflag, Iindex, Iarray);\
  GArrayRef(Iarray, Iflag, Iindex, Idummytemplate, IdummyState, INext);\
  GArrayRef(Iarray, Iflag, Iprevious, Idummytemplate, \
            IdummyState, INextOfPrev);\
  *INextOfPrev = *INext;\
  *INext = Iindex;\
}

/* Swap out overflow at fromindex contents from its circular list to toindex */
/* assumes toindex is currently on a unary list */
/* macroized */
/* static void */
#define Gswapout(/*GroupArray*/ Jarray, \
		 /*int*/ Jfromindex, \
		 /*int*/ Jtoindex,\
		 /*enum BucketFlag*/ Jflag)\
{\
  long *JNext = 0, *JNextOfPrev = 0, *JNextOfOther = 0;\
  enum GState *JState, *JOtherState = 0, *JPrevState;\
  Groupptr Jg, Jgprev, Jgother;\
  long Jprevious;\
  Gprevious(Jprevious, Jflag,Jfromindex,Jarray);\
  Dprint(("Gswapout %ld --> %ld\n",Jfromindex, Jtoindex));\
  GArrayRef(Jarray,Jflag,Jfromindex, Jg, JState, JNext);\
  GArrayRef(Jarray,Jflag,Jprevious, Jgprev, JPrevState, JNextOfPrev);\
  GArrayRef(Jarray,Jflag,Jtoindex, Jgother, JOtherState, JNextOfOther);\
  *JNextOfOther = *JNext;\
  *JOtherState = OVERFLOW;\
  GroupCopy(Jgother, Jg, Jflag);\
  *JNextOfPrev = Jtoindex;\
  Groupinit(Jg, Jflag);\
  /* *JState = ROOT; */\
  *JNext = Jfromindex;\
}

/******************************************************************/
/**  table methods                                               **/

/* table structure */
typedef struct {
  enum BucketFlag flag;       /* bucket behavior */
  long Dirty;                  /* should be set if the table
                                 has had a "bucket overwrite"
                                 ie, if a deletion or entry
                                 overwrite has occurred */
  long Free;                   /* head of circular free list */
  long entries;                /* number of entries used */
  long basesize;                  /* basesize for truncating hash */
  long size;                   /* number of groups (basesize+extras) */
  GroupArray groups;          /* array of groups of buckets */
} Table;

/* place an entry on the free list, assuming it isn't there already */
/* macroized */
/*static void*/
#define FreeTableIndex(/*Table * */ Ktp, /*int*/ Kindex)\
{\
  register enum BucketFlag Kflag = tp->flag;\
  GroupArray Kgroups = Ktp->groups;\
  long Kfreeindex = Ktp->Free;\
  Groupptr Kthis, Kfree;\
  enum GState *KthisState = 0, *KfreeState = 0;\
  long *KNext = 0, *KfreeNext = 0;\
  Dprint(("FreeTableIndex %ld\n",Kindex));\
  GArrayRef( Kgroups, Kflag, Kindex, Kthis, KthisState, KNext);\
  /* extract the group, only if its in a known state */\
  if (*KthisState != UNKNOWN) {\
    Gremove( Kflag, Kindex, Kgroups );\
  }\
  *KthisState = FREE;\
  if (Kfreeindex == -1) {\
    SetFreeGroup( Kgroups, Kflag, Kindex, Kindex, Kindex );\
  }\
  else {\
    GArrayRef( Kgroups, Kflag, Kfreeindex, Kfree, KfreeState, KfreeNext);\
    SetFreeGroup( Kgroups, Kflag, Kindex, *KfreeNext, Kfreeindex);\
  }\
  Ktp->Free = Kindex;\
}
  

/* bucket allocation for table */
static long AllocateBuckets(Table *tp, long numMembers)
{
  register enum BucketFlag flag = tp->flag;
  long ExpSize = numMembers/GSIZE + 1;
  long basesize, size, *Next, i;
  enum GState *State = NULL;
  Groupptr g;
  GroupArray groups;
  Dprint(("AllocateBuckets %ld\n",numMembers));
  /* this weird heuristic is chosen arbitrarily (powers of 2 minus 1) */
  for (basesize=1; ; basesize += basesize + 1) {
    if ((basesize <= 0) || (basesize>=ExpSize)) { break; }
  }
  if (basesize<ExpSize) { return 0; } /* failure, error */
  tp->basesize = basesize;
  tp->size = size = basesize + basesize/OVLFACT;
  tp->entries = 0;
  switch (flag) {
  case SETFLAG:
    groups.Sgroups =
      (SetGroup *) calloc(sizeof(SetGroup), size);
    break;
  case DICTFLAG:
  case GRAPHFLAG:
    groups.Dgroups =
      (DiGroup *) calloc(sizeof(DiGroup), size);
    break;
  default: 
    PyErr_SetString(PyExc_SystemError, "invalid internal table behavior flag");
    return 0; /* error */
  }
  if (groups.Dgroups == NULL) {
    PyErr_NoMemory();
    return 0; /* error */
  }
  /* initialize all states to unknown */
  for (i=0; i<size; i++) {
    GArrayRef(groups, flag, i, g, State, Next);
    *State = UNKNOWN;
  }
  tp->groups = groups;
  tp->Free = -1;
  /* initialize free groups backwards, to encourage
     use of dedicated free groups */
  for (i=size-1; i>=0; i--) {
    FreeTableIndex(tp, i);
  }
  return 1;
}

#ifdef WDEBUGPRINT
/* printing for testing only */
static long TableDump(Table *tp, FILE *fp)
{
  register enum BucketFlag flag = tp->flag;
  GroupArray groups = tp->groups;
  Groupptr g;
  enum GState *State;
  long size = tp->size;
  long i, *Next;
  fprintf(fp, "Table (size=%ld, basesize=%ld, entries=%ld, free=%ld, ",
	          size, tp->basesize, tp->entries, tp->Free);
  switch (flag) {
  case SETFLAG:
    fprintf(fp, "SET)\n"); break;
  case DICTFLAG:
    fprintf(fp, "DICT)\n"); break;
  case GRAPHFLAG:
    fprintf(fp, "GRAPH)\n"); break;
  default:
    fprintf(fp, "!unknown flag!\n");
  }
  for (i=0; i<size; i++) {
    GArrayRef(groups, flag, i, g, State, Next);
    fprintf(fp, "%ld: ", i);
    switch (*State) {
    case UNKNOWN:
      fprintf(fp, "UNKNOWN\n"); break;
    case FREE:
      fprintf(fp, "FREE next=%ld, prev=%ld\n", g.fgp->Next, g.fgp->Previous);
      break;
    case ROOT:
      fprintf(fp, "ROOT(next=%ld)",*Next);
      if (GroupDump(g,flag,fp)!=0) { return -1; }
      break;
    case OVERFLOW:
      fprintf(fp, "OVFLW(next=%ld)",*Next);
      if (GroupDump(g,flag,fp)!=0) { return -1; }
      break;
    default:
      fprintf(fp, "!invalid GState!\n");
    }
  }
  return 0;
}
#endif

/* empty out all groups in this table */
static void groupsReinit(GroupArray g, enum BucketFlag flag, long size)
{
  enum GState *State = 0;
  Groupptr groupp;
  long i, j, *d;
  Bucketptr Bp;
  Dprint(("groupsReinit %ld \n",size));
  /* reinit all the groups to properly handle object references */
  for (i=0; i<size; i++) {
    Dprint(("greinit at %ld\n",i));
    GArrayRef(g, flag, i, groupp, State, d);
    if ((*State == ROOT) || (*State == OVERFLOW)) {
      for (j=0; j<GSIZE; j++) {
	GetBucket(Bp,groupp,flag,j);
	BPtrReInit(Bp, flag);
      }
    }
  }
  Dprint(("greinit done\n"));
}

/* deallocating groups array 
   could macroize
*/
static void groupsDealloc(GroupArray g, enum BucketFlag flag, long size)
{
  /* reinitialize all buckets */
  groupsReinit(g, flag, size);
  /* now delete the array */
  PyMem_Del(g.Sgroups);
}

/* unfreeing a group in the Table *assumed free with garbage contents* */
/* (macroized) */
/*long */
#define UnFreeTableIndex(/*int*/ Lresult, /*Table * */Ltp, /*int*/ Lindex)\
{\
  register enum BucketFlag Lflag = tp->flag;\
  GroupArray Lgroups = Ltp->groups;\
  long Lfreeindex = Ltp->Free;\
  long *LNextp = 0, LNextind;\
  enum GState *LState;\
  Groupptr Lthis;\
  Lresult = Lindex;\
  Dprint(("UnFreeTableIndex %ldn",Lresult));\
  GArrayRef(Lgroups, Lflag, Lresult, Lthis, LState, LNextp);\
  /* debug */\
  if (*LState != FREE) \
    Dprint(("UnFreeTableIndex State=%ld not FREE\n",*LState));\
  LNextind = *LNextp; /* save */\
  if (LNextind == Lresult) {\
    /* free list has one elt, zero after */\
    Ltp->Free = -1;\
  } else {\
    ExtractFreeGroup(Lgroups, Lflag, Lresult);\
    if (Lfreeindex == Lresult) { Ltp->Free = LNextind; }\
  }\
  Groupinit(Lthis,Lflag);\
  /*return Lindex;*/\
}

/* table initializer 
   could macroize
*/
static long initTable(Table *tp, enum BucketFlag flag, long numMembers)
{
  tp->flag = flag;
  tp->Dirty = 0;
  Dprint(("initTable\n"));
  return AllocateBuckets(tp, numMembers);
}

/* forward decl for table resizer */
long tableResize( Table *, long );

/* matching within a table.
   inputs: tp -- the table
           member1 -- the member to match
           map1 -- the map to match (null for set/dict)
           Force -- whether or not to force an insert on failure
           rootgroupI -- for reentrance, the rootgroup for current loop
           lastgroupI -- for reentrance, the current group
           lastbucketI -- for reentrance, the *previous* bucket
              to look past.
         (-1 means none for I* args)
           hsh -- the hash value if known (NOHASH means not known)
   outputs: (only valid after a successful search)
           rtgrp -- index of current root group (for later reenter)
           nxtgrp -- index of group where found
           nxtbkt -- index of bucket where found
           Bp -- Bucketptr to bucket where found
           hshout -- hash value
           isnew -- 1 if new entry inserted, 0 otherwise
   return value 1 (found) 0 (not found) -1 (error occurred)

Behaviors:
   if hsh == NOHASH and Member1 == 0 then
      rootgroupI should be valid;
      match any full value past reentrant state
   else
      if hsh, rootgroup, etc. not defined compute them.
      if the rootgroup is currently an overflow swap it out.
      search in circular list headed at rootgroup for match
        (if Force and there is space in existing bucket, force insert)
      if no match found and Force, allocate a new group on this list
        and force insert the member.
*/
/* crazy idea: macroize this monster, and use stub only for recursive
               calls... */
static long tableMatch( Table *tp, PyObject *member1, PyObject *map1,
	      enum ForceFlag Force,
	      long rootgroupI, long lastgroupI, long lastbucketI, long hsh,
  /*outputs*/ long *rtgrp, long *nxtgrp, long *nxtbkt, Bucketptr *Bp,
	      long *hshout, long *isnew)
{
  register enum BucketFlag flag = tp->flag;
  GroupArray groups = tp->groups;
  Groupptr root, thisgroup, avail;
  enum GState *state = 0, *availState = 0;
  long *Next = 0, *rNext = 0, AvailableI, found, *availNext = 0, *dirtyptr;
  unsigned long lhsh;

  /*Dprint(("TableMatch %ld\n",hsh));*/

  /* used to mark the table dirty upon "bucket overwrite" */
  dirtyptr = &(tp->Dirty);

  /* sanity checks (comment out later?) */
  if ( (member1 == 0) && ( (rootgroupI < 0) || (Force == FORCE) ) ) {
    PyErr_SetString(PyExc_SystemError, "bug in kjbuckets implementation (tableMatch)");
    return -1;
  }

  /* compute hash value if absent and needed */
  if ((hsh == NOHASH) && (member1 != 0)) { 
    GETHASH(hsh, member1);
    if (hsh == -1) { return -1; } /* unhashable */
    Dprint(("tm: hash = %ld computed\n",hsh));
  }

  /* sanity check */
  /*if (tp->Free != -1) {
     GArrayRef(groups, flag, tp->Free, root, state, rNext);
     if (*state != FREE) {
        PyErr_SetString(PyExc_SystemError, "free index not free in table");
        return -1;
      }
   }*/

  *hshout = hsh; /* return value */
  lhsh = /*(unsigned long)*/ hsh;

  /* find the root group if needed */
  if (rootgroupI < 0) {
    rootgroupI = lastgroupI = lhsh % tp->basesize;
    lastbucketI = -1;
    /* swap out or free root group if needed */
    GArrayRef(groups, flag, rootgroupI, root, state, rNext);
    if (*state != ROOT) {
      /* failure, unless forced insert */
      if (Force == NOFORCE) { return 0; }
      /* lastgroup and lastbucket must be none */
      lastgroupI = lastbucketI = -1;
      /* otherwise must force an insert, need root group... */
      if (*state == OVERFLOW) {
	/* swap out the overflow group */
        Dprint(("root is overflow %ld\n",rootgroupI));
	if (tp->Free == -1) {
	  /* nowhere to swap, must resize up */
          Dprint(("tm: resizing for root\n"));
	  if (tableResize(tp, RESIZEUPSIZE(tp)) == 0) {
	    return -1; /* failure to resize */
	  }
	  return tableMatch(tp, member1, map1,
			    Force, -1, -1, -1, hsh,
			    rtgrp, nxtgrp, nxtbkt, Bp, hshout, isnew);
	}
	UnFreeTableIndex(AvailableI, tp, tp->Free);
	Gswapout(groups, rootgroupI, AvailableI, flag);
      } else {
	if (*state == FREE) {
	  Dprint(("unfreeing rootgroup %ld\n", rootgroupI));
	  UnFreeTableIndex(rootgroupI, tp, rootgroupI);
	} else {
	  PyErr_SetString(PyExc_SystemError, "bad rootgroup state in tablematch");
	  return -1; /* error */
	}
      }
      /* set the next of new root group to self */
      /* paranioa: technically the structure may have changed... (omit?) */
      GArrayRef(groups, flag, rootgroupI, root, state, rNext);
      *state = ROOT;
      *rNext = rootgroupI;
    }
  }
  if (lastgroupI<0) { lastgroupI = rootgroupI; lastbucketI=-1; }
  *rtgrp = rootgroupI;
  /*Dprint(("tm: lg = %ld, rg = %ld, lb = %ld\n",\
	  lastgroupI, rootgroupI, lastbucketI));*/
  /* look in circular list until looped or found */
  do {
    Dprint(("tm: looking %ld\n", lastgroupI));
    GArrayRef(groups, flag, lastgroupI, thisgroup, state, Next);
    *nxtgrp = lastgroupI;
    groupmatch(found, thisgroup, flag, hsh, member1, map1,\
		       Force, lastbucketI, (*nxtbkt), \
                       (*Bp), (*isnew), (*dirtyptr));
    if (*Next == rootgroupI) { break; }
    lastgroupI = *Next;
    lastbucketI = -1;
  } while (found == 0);
  /* success if found */
  if (found != 0) {
    Dprint(("tm: found = %ld\n",found));
    if (found<0) {
      PyErr_SetString(PyExc_SystemError, "groupmatch abnormal return");
      return -1;
    }
    if (*isnew != 0) { tp->entries++; }
    Dprint(("tm: success, rg=%ld, ng=%ld, nb=%ld, ho=%ld, in=%ld", \
            *rtgrp, *nxtgrp, *nxtbkt, *hshout, *isnew));
    return 1;
  }
  /* otherwise force an insert into a new group, if requested */
  if (Force == FORCE) {
    Dprint(("tm: trying to force insert to overflow\n"));
    if (tp->Free == -1) {
      /* no room, no room (mad hatter) */
      Dprint(("tm: resizing for overflow\n"));
      if (tableResize(tp, RESIZEUPSIZE(tp)) == 0) {
	return -1; /* failure to resize */
      }
      return tableMatch(tp, member1, map1,
			Force, -1, -1, -1, hsh,
			rtgrp, nxtgrp, nxtbkt, Bp, hshout, isnew);
    }
    UnFreeTableIndex(AvailableI, tp, tp->Free);
    GArrayRef(groups, flag, AvailableI, avail, availState, availNext);
    *availState = OVERFLOW;
    *availNext = rootgroupI;
    *Next = AvailableI;
    groupmatch(found, avail,flag,hsh,member1,map1,
		       Force, -1, (*nxtbkt), (*Bp), (*isnew), (*dirtyptr));
    if (found<0) {
      PyErr_SetString(PyExc_SystemError, "groupmatch abnormal return");
      return -1;
    }
    *nxtgrp = AvailableI;
    if (*isnew != 0) { tp->entries++; }
    return 1;  /* successful insert */
  }
  return 0; /* not found */
}

/* some simple uses of table matching */

/* find (or set) a matching pair */
static long TableGet1( Table *tp, PyObject *member1, PyObject *map1, long hash,
	       enum ForceFlag Force,
	       PyObject **memout, PyObject **mapout)
{
  long hashout;
  long rt, nxt, nxtb, isnew, found;
  Bucketptr Bp;
  enum BucketFlag flag = tp->flag;
  if (member1 == NULL) {
    PyErr_SetString(PyExc_SystemError, "TableGet1 called with NULL??");
    return -1;
  }
  Dprint(("tg1: calling tablematch\n"));
  found = tableMatch(tp, member1, map1, Force,
		     -1, -1, -1, hash,
		     &rt, &nxt, &nxtb, &Bp, &hashout, &isnew);
  if (found == -1) { return -1; }
  if (found == 0) {
    PyErr_SetObject(PyExc_KeyError, member1);
    return -1;
  }
  BPtrDestructure(Bp, flag, hashout, *memout, *mapout);
  return 0;
}

/* utility function for resizing a table: reinserting a group */
/* could macroize */
long ReInsertGroup( Groupptr g, enum BucketFlag flag, Table *tp)
{
  PyObject *Member = 0, *Map = 0;
  long i, rt, nxt, nxtb, isnew, test;
  long hash = 0, h;
  Bucketptr Bp, Bpdummy;
  for (i=0; i<GSIZE; i++) {
    GetBucket(Bp, g, flag,i);
    BPtrDestructure(Bp, flag, hash, Member, Map);
    if (hash != NOHASH) {
      test = tableMatch(tp, Member, Map, FORCE, -1, -1, -1, hash,
		      &rt, &nxt, &nxtb, &Bpdummy, &h, &isnew);
      if (test != 1) {
	PyErr_SetString(PyExc_SystemError, "unable to resize table");
	return 0;
      }
    }
    /* note, no reinit in case we want to reuse the groups g!! */
  }
  return 1;
}

/* 
  clear the contents of a table, no resizing or deallocation 
*/
long tableClear( Table *tp )
{
  Dprint(("tclear\n"));
  groupsReinit( tp->groups, tp->flag, tp->size );
  tp->entries = 0;
  return 1;
}

long tableResize( Table *tp, long expected )
{
  long i, *Next;
  enum GState *State = 0;
  Groupptr g;
  long size = tp->size;
  enum BucketFlag flag = tp->flag;
  GroupArray oldgroups = tp->groups;
  long DirtyVal = tp->Dirty;
  long success = 1; /* assume success */
  Dprint(("tresize: resizing %ld\n",expected));
  /* allocate a new Table */
  if (AllocateBuckets(tp, expected) != 1) { return 0; }
  /* for debug */
  /*if (tp->Free!=-1) {
     GArrayRef(tp->groups, flag, tp->Free, g, State, Next);
     if (*State != FREE) {
       Dprint(("free ptr %ld corrupted in resize/alloc, State=%ld not %ld\n",\
	      tp->Free,*State,FREE));
       PyErr_SetString(PyExc_SystemError, "resize fail (1)");
       return 0;
     }
   }*/
  /* now reinsert all former contents */
  for (i=0; i<size; i++) {
    GArrayRef(oldgroups, flag, i, g, State, Next);
    if ( (*State == OVERFLOW) || (*State == ROOT) ) {
      if (ReInsertGroup(g, flag, tp) == 0) {
	success = 0;
	break;
      }
      /* for debug */
      /*if (tp->Free!=-1) {
	GArrayRef(tp->groups, flag, tp->Free, g, State, Next);
	if (*State != FREE) {
	  Dprint((\
            "free ptr %ld corrupted in resize/reinsert %ld, State=%ld not %ld\n",\
		 tp->Free,i,*State,FREE));
	  PyErr_SetString(PyExc_SystemError, "resize fail (2)");
	  return 0;
	}*/
    }
  }
  /* deallocate the old groups */
  groupsDealloc(oldgroups, flag, size);
  tp->Dirty = DirtyVal; /* use old dirty value... (paranoia) */
  /* for debug */
  /*if (tp->Free!=-1) {
     GArrayRef(tp->groups, flag, tp->Free, g, State, Next);
     if (*State != FREE) {
       Dprint(("free ptr %ld corrupted in resize, State=%ld not %ld\n",tp->Free,\
	      *State,FREE)); 
       PyErr_SetString(PyExc_SystemError, "resize fail (3)");
       return 0;
     }*/
  if (success==0) Dprint(("failing in tableresize\n"));
  return success;
}

/* deleting a member from a group, deletes *all* matching members */
long deleteFromTable(Table *tp, PyObject *member1, PyObject *map1)
{
  PyObject *M = 0, *Mp = 0;
  enum BucketFlag flag = tp->flag;
  GroupArray groups = tp->groups;
  long hash, bhash;
  long test, rtgrp, nxtgrp, nxtbkt, isnew, found, grp, *N = 0,
      brt, bnxtgrp, bnxtbkt, bisnew, bfound, rtg1, rtg2;
  Bucketptr Bp, bBp;
  Groupptr g;
  enum GState *State;
  /* find first match */
  found = tableMatch(tp, member1, map1,
		     NOFORCE, -1, -1, -1, NOHASH,
		     &rtgrp, &nxtgrp, &nxtbkt, &Bp, &hash, &isnew);
  if (found == -1) { return 0; } /* external error */
  if (found == 0) {
    PyErr_SetObject(PyExc_KeyError, member1);
    return 0;
  }
  /* mark the table as dirty */
  tp->Dirty = 1;
  /* delete all such matches */
  while (found) {
    BPtrReInit(Bp, flag);
    tp->entries--;
    found = tableMatch(tp, member1, map1,
		       NOFORCE, rtgrp, nxtgrp, nxtbkt, hash,
		       &rtgrp, &nxtgrp, &nxtbkt, &Bp, &hash, &isnew);
    if (found == -1) { return 0; } /* external error */
  }
  /* back fill nulled entries in circular list (could be faster?) */
  found = tableMatch(tp, 0, 0,
		     NOFORCE, rtgrp, rtgrp, -1, NOHASH,
		     &rtgrp, &nxtgrp, &nxtbkt, &Bp, &hash, &isnew);
  if (found == -1) { return 0; } /* error */
  brt = bnxtgrp = rtgrp;
  bnxtbkt = -1;
  while (found) {
    BPtrDestructure(Bp, flag, hash, M, Mp);
    tp->entries--;
    /*  !!! NOTE: since BPtrReInit Py_DECREFs the contents, must
	Py_INCREF contents here to prevent deallocation of the
	members and decref after reinstallation in the table
	!!! (kinda subtle python thing!) !!! */
    Py_XINCREF(M);
    Py_XINCREF(Mp);
    BPtrReInit(Bp,flag);
    bfound = tableMatch(tp, M, Mp,
			FORCE, brt, bnxtgrp, bnxtbkt, hash,
			&brt, &bnxtgrp, &bnxtbkt, &bBp, &bhash, &bisnew);
    Py_DECREF(M);
    Py_DECREF(Mp);
    if (found != 1) {
      PyErr_SetString(PyExc_SystemError, "?? cannot backfill on delete");
      return 0;
    }
    found = tableMatch(tp, 0, 0,
		       NOFORCE, rtgrp, nxtgrp, nxtbkt, NOHASH,
		       &rtgrp, &nxtgrp, &nxtbkt, &Bp, &hash, &isnew);
    if (found == -1) { return 0; }
  }
  /* now free up any groups on this cycle that are left empty */
  /* this will only delete the rootgroup if there is nothing in the cycle */
  grp = rtgrp;
  do {
    GArrayRef(groups, flag, grp, g, State, N);
    nxtgrp = *N;
    GroupEmpty(test, g,flag);
    if (test) {
      if (grp == rtgrp) { 
        rtg1 = rtg2 = rtgrp; /* nasty macro bug fixed here */
	Gprevious(rtg1,flag,rtg2,groups);  /* for termination */
      }
      FreeTableIndex(tp,grp);
    }
    grp = nxtgrp;
  } while (grp != rtgrp);
  /* finally, resize if too few entries */
  if (RESIZEDOWNTEST(tp)) {
    tableResize(tp, tp->entries);
  }
  return 1;
}

/***********************************************************/
/**  table walker methods                                 **/

/* TableWalkers are used for *strictly local and temporary*
   walking of table structure in two ways:
   - by key
   - by all values in table
   (things like increfs and decrefs aren't done since use is temporary).
   */

typedef struct {
  Table *tp;
  long valid;  /* 1 means okay, 0 means done, -1 means error */
  long root;
  long lastgroup;
  long lastbucket;
  PyObject *key;
  PyObject *map;
  long hash;
} TableWalker;

/* 
  methods for walking by all values
  */

static long NextAll(TableWalker *twp)
{
  Bucketptr Bp;
  Groupptr g;
  enum BucketFlag flag;
  enum GState *State = 0;
  long *Next, size, found, isnew, dirtyptr;
  PyObject *dummy;
  Table *tp = twp->tp;
  size = tp->size;
  flag = tp->flag;
  if (twp->lastgroup > size) {
    twp->valid = 0;
    return 0; /* failure return */
  }
  if ((twp->lastgroup == -1) || (twp->lastbucket>GSIZE)){
    twp->lastbucket = -1;
    twp->lastgroup++;
  }
  found = 0;
  do {
    GArrayRef(tp->groups, flag, twp->lastgroup, g, State, Next);
    if ((*State==ROOT) || (*State==OVERFLOW)) {
      dummy = 0;
      groupmatch(found, g, flag, NOHASH, dummy, dummy, NOFORCE,\
			 (twp->lastbucket), (twp->lastbucket), \
			 Bp, isnew, dirtyptr);
    }
    if (found==0) {
      twp->lastgroup++;
      twp->lastbucket = -1;
    }
  } while ( (found == 0) && (twp->lastgroup < size) );
  if (found == 0) {
    twp->valid = 0;
    return 0; /* failure return */
  }
  /* success: find the hash, key and map values */
  BPtrDestructure(Bp, flag, (twp->hash), (twp->key), (twp->map));
  twp->valid = 1;
  /*printf("allwalker: item found with hash %ld\n",twp->hash);*/
  return 1; /* successful return */
}

/* could macroize */
static void InitAll(TableWalker *twp, Table *tp)
{
  twp->lastgroup = -1;
  twp->lastbucket = -1;
  twp->tp = tp;
  twp->valid = NextAll(twp);
}

/* methods for walking my key
   NOHASH may be used as an "unknown" hash value */

static long Nextbykey(TableWalker *twp)
{
  Bucketptr Bp;
  PyObject *dummyk;
  long dummyh;
  long isnew;
  Dprint(("Nextbykey\n"));
  twp->valid =
    tableMatch(twp->tp, twp->key, 0, NOFORCE,
	       twp->root, twp->lastgroup, twp->lastbucket, twp->hash,
	       &(twp->root), &(twp->lastgroup), &(twp->lastbucket), &Bp,
	       &(twp->hash), &isnew);
  if (twp->valid == 1) {
    BPtrDestructure(Bp, twp->tp->flag, dummyh, dummyk, (twp->map));
  }
  return twp->valid;
}

/* could macroize */
static void Initbykey(TableWalker *twp, Table *tp, PyObject *key, long hash)
{
  Dprint(("Initbykey\n"));
  twp->tp = tp;
  twp->root = -1;
  twp->lastgroup = -1;
  twp->lastbucket = -1;
  twp->key = key;
  twp->hash = hash;
  twp->valid = Nextbykey(twp);
}

/*******************************************************************/
/** methods for combining tables                                  **/

/* augmenting one table using another, assuming types are compatible */

static long Taugment(Table *target, Table *source)
{
  long test;
  TableWalker tw;
  PyObject *d1, *d2;
  /* walk through the source */
  (void) InitAll(&tw, source);
  while (tw.valid == 1) {
    Dprint(("taug: TableGet1\n"));
    test = TableGet1(target, tw.key, tw.map, tw.hash, FORCE, &d1, &d2);
    if (test!=0) { return -1; } /* error return */
    (void) NextAll(&tw);
  } 
  return tw.valid; /* 0 for success, -1 for error */
}

/* transpose a table (can't be a set!) 
   if target is a dictionary result may be nondeterministic unless
   source is 1:1.
   if target is a set result will be set of all targets+dests (nodes)
   */
static long Ttranspose(Table *target, Table *source)
{
  long test;
  TableWalker tw;
  PyObject *d1, *d2;
  enum BucketFlag tflag = target->flag;
  /* source flag cannot be set */
  if (source->flag == SETFLAG) { 
    PyErr_SetString(PyExc_TypeError, "Cannot transpose set");
    return -1;  /* error return */
  }
  /* walk through the source */
  (void) InitAll(&tw, source);
  while (tw.valid == 1) {
    if (tflag == SETFLAG) {
      /* add mem and map separately to target */
      test = TableGet1(target, tw.key, 0, tw.hash, FORCE, &d1, &d2);
      if (test!=0) { return -1; } /* error */
      test = TableGet1(target, tw.map, 0, NOHASH, FORCE, &d1, &d2);
      if (test!=0) { return -1; } /* error */
    } else {
      /* add inversion */
      test = TableGet1(target, tw.map, tw.key, NOHASH, FORCE, &d1, &d2);
      if (test!=0) { return -1; } /* error */
    }
    /* advance cursor */
    (void) NextAll(&tw);
  }
  return tw.valid; /* 0 for success, -1 for error */
}

/* 
  Compose a dict/graph with a dict/graph and put the result in another.
  If mask is non-null mask out any members of mask (for tclosure).
  Table types assumed to be sensible.
  target = ( (left o right) - mask )
  long returned is number of inserts or -1 on error.
  if prelim is set only counting will be done, no inserts (target may be null).
  */
static long Tcompose(Table *target, Table *left, Table *right, Table *mask,
		    long prelim)
{
  TableWalker lwalker, rwalker;
  PyObject *d1, *d2;
  long test, count, exclude, rt, nxt, nxtb, isnew;
  Bucketptr Bp;
  long hashout;
  enum BucketFlag lflag = left->flag;
  
  /* walk through left */
  (void) InitAll(&lwalker, left);
  Dprint(("Tcompose: lwalker initialized\n"));
  count = 0;
  while (lwalker.valid == 1) {
    /* walk through members of right matching lwalker.map */
    /* if left is a set then don't recompute the hash value */
    if (lflag == SETFLAG) {
      (void) Initbykey(&rwalker, right, lwalker.key, lwalker.hash);
    } else {
      (void) Initbykey(&rwalker, right, lwalker.map, NOHASH);
    }
    Dprint(("Tcompose: rwalker initialized\n"));
    while (rwalker.valid == 1) {
      exclude = 0;
      if (mask != 0) {
        Dprint(("Tcompose: computing exclude\n"));
	exclude = tableMatch(mask, lwalker.key, rwalker.map, NOFORCE,
			     -1, -1, -1, lwalker.hash,
			     &rt, &nxt, &nxtb, &Bp, &hashout, &isnew);
      }
      if (exclude==0) {
	if (prelim==0) {
	  test = TableGet1(target, lwalker.key, rwalker.map, lwalker.hash,
			   FORCE, &d1, &d2);
	  if (test!=0) { return -1; } /* error */
	}
	count++;
      }
      (void) Nextbykey(&rwalker);
    }
    if (rwalker.valid == -1) { return -1; } /* error */
    (void) NextAll(&lwalker);
  }
  if (lwalker.valid == -1) { return -1; } /* error */
  return count;
}

/* Add the intersection or difference of two tables to another
   table.
   On error returns -1, else returns count of inserts.
   Invoke with a nonzero prelim value to get just count of inserts
   without inserting, in this case target may be null.
   */
static long Tintdiff(Table *target, Table *left, Table *right, 
		    long include, long prelim)
{
  long hashout;
  long test, rt, nxt, nxtb, isnew, found, count;
  Bucketptr Bp;
  TableWalker tw;
  PyObject *d1, *d2;
  /* walk through left */
  (void) InitAll(&tw, left);
  count = 0;
  while (tw.valid == 1) {
    /* is current in right? */
    found = tableMatch(right, tw.key, tw.map, NOFORCE,
		       -1, -1, -1, tw.hash,
		       &rt, &nxt, &nxtb, &Bp, &hashout, &isnew);
    if (found == -1) { return -1; } /* error */
    /* maybe either include or exclude the member based on flag value */
    if ( ((include==1)&&(found==1)) || ((include==0)&&(found==0)) ) {
      if (prelim == 0) {
	test = TableGet1(target, tw.key, tw.map, tw.hash, FORCE, &d1, &d2);
	if (test!=0) { return -1; } /* error */
      }
      count++;
    }
    /* advance cursor */
    (void) NextAll(&tw);
  }
  if (tw.valid == -1) { return -1; } /* error */
  return count; /* success */
}

/* Utility function for comparisons:
   find the "smallest" pair in left that is not in right
   return 1 if found, else 0 (-1 on error).
   */
static long Tmindiff(Table *left, Table *right, 
		    PyObject **mem, PyObject **map, long *hash)
{
  long hashout;
  long gotit, rt, nxt, nxtb, isnew, found, cmp;
  Bucketptr Bp;
  TableWalker tw;
  /* walk through left */
  (void) InitAll(&tw, left);
  gotit = 0;
  while (tw.valid == 1) {
    /* is current in right? */
    found = tableMatch(right, tw.key, tw.map, NOFORCE,
		       -1, -1, -1, tw.hash,
		       &rt, &nxt, &nxtb, &Bp, &hashout, &isnew);
    if (found == -1) { return -1; } /* error */
    /* if it wasn't in right test it for minimality */
    if (found == 0) {
      if (gotit == 0) {
	*mem = tw.key;
	*map = tw.map;
	*hash = tw.hash;
	gotit = 1;
      } else {
	cmp = *hash - tw.hash;
	if (cmp == 0) { cmp = PyObject_Compare( tw.key, *mem ); }
	if ((cmp>0) || 
	    ((cmp==0) && (tw.map!=0) && (PyObject_Compare( tw.map, *map )>0))) {
	  *mem = tw.key;
	  *map = tw.map;
	  *hash = tw.hash;
	}
      }
    }
    (void) NextAll(&tw);
  }
  if (tw.valid == -1) { return -1; } /* error */
  return gotit;
}

/* for coercing table types:
   Dict intersect Graph is Dict,  Dict union Graph is Graph, etc.
   generality should be positive (nonzero) to default to more general
   negative to default to less general
   */
static long FlagCoercion(enum BucketFlag flag1, enum BucketFlag flag2,
			enum BucketFlag *fp, long Generality)
{
  *fp = flag2;
  if ( ((flag1 > flag2) && (Generality>0) ) ||
       ((flag1 < flag2) && (Generality<0) ) ) { *fp = flag1; }
  return 1; /* always succeed */
}


/*********************************************/
/*  python data structures and interfaces... */
/*********************************************/

/* general structure for all table behaviors */

typedef struct {
  PyObject_VAR_HEAD
    /* the hash flag */
    /* IF THIS IS NOT NOHASH THE TABLE SHOULD BE IMMUTABLE */
    long hashvalue;
  /* the flag in member rep determines behaviors */
  Table rep;
} TableWrapper;

/* predeclarations of type objects */
staticforward PyTypeObject kjSettype;
staticforward PyTypeObject kjDicttype;
staticforward PyTypeObject kjGraphtype;

/* type test macros */
#define is_kjSetobject(op) ((op)->ob_type == &kjSettype)
#define is_kjDictobject(op) ((op)->ob_type == &kjDicttype)
#define is_kjGraphobject(op) ((op)->ob_type == &kjGraphtype)
#define is_kjTable(op) \
    ( is_kjSetobject(op) || is_kjDictobject(op) || is_kjGraphobject(op) )

/* for algebraic operations that may be using a tainted argument
   propagate the taintedness... (requires ending semicolon!)
*/
#define propagateDirt(in,out) \
   if (in->rep.Dirty!=0) out->rep.Dirty = 1

/* internal allocation function for table wrappers */
static PyObject * newWrapper(long expectedsize, enum BucketFlag flag)
{
  /* allocate one wrapper */
  TableWrapper *wp;
  Dprint(("WnewWrapper\n"));
  wp = PyMem_NEW(TableWrapper, 1);
  if (wp == NULL) {
    return PyErr_NoMemory(); /* allocation failure */
  }
  switch (flag) {
  case SETFLAG:
    wp->ob_type = &kjSettype; break;
  case DICTFLAG:
    wp->ob_type = &kjDicttype; break;
  case GRAPHFLAG:
    wp->ob_type = &kjGraphtype; break;
  default:
    PyErr_SetString(PyExc_SystemError, "invalid internal table flag");
    return NULL;
  }
  /* initialize the internal table */
  if (initTable(&(wp->rep), flag, expectedsize) == 0) {
    /* initialization failed, assume an appropriate error is set */
    PyMem_Del(wp);
    return NULL;
  }
  Dprint(("WnewWrapper: table initialized\n"));
  wp->hashvalue = NOHASH;
  /* INITIALIZE THE REFERENCE COUNT FOR THE NEW OBJECT */
  _Py_NewReference(wp);
  return (PyObject *) wp;
}

/* *almost* an external python constructor for wrappers */
static PyObject * makeWrapper(PyObject *module, PyObject *args,
			    enum BucketFlag flag)
{
  TableWrapper *result, *initWrapper;
  PyObject *initlist, *pair, *key, *map, *d1, *d2;
  long len = 0, members, valid, index, islist, iskjtable, istuple;
  Table *tp;
  islist = 0;
  iskjtable = 0;
  istuple = 0;
  initlist = NULL;
  initWrapper = NULL;
  Dprint(("makeWrapper\n"));
  /* no args: allocate a smallest table: */
  if (args == NULL) {
    members = 0;
  } else {  /* some args: check it and determine its length */
    valid = PyArg_Parse(args, "i", &members);
    if (!valid) {
      PyErr_Clear();
      valid = PyArg_Parse(args, "O", &initlist);
      if (valid) { 
	islist = PyList_Check(initlist);
	if (islist) {
          Dprint(("makeWrapper from list\n"));
	  len = PyList_Size(initlist);
	} else {
	  iskjtable = is_kjTable(initlist);
	  if (iskjtable) {
            Dprint(("makeWrapper from kj-table\n"));
	    initWrapper = (TableWrapper *) initlist;
	    len = initWrapper->rep.entries;
	  } else {
	    istuple = PyTuple_Check(initlist);
	    if (istuple) {
              Dprint(("makeWrapper from tuple\n"));
	      len = PyTuple_Size(initlist);
	    } else {
	      valid = 0;
	    }
	  }
	}
      }
      if (!valid) { 
	PyErr_SetString(PyExc_TypeError, 
         "initializer must be integer or list or tuple or kj-Table");
	return NULL; 
      }
      members = len/2; /* try to conserve space when initializing from list */
    }
  }
  result = (TableWrapper *) newWrapper(members, flag);
  if (result == NULL) { return NULL; } /* error */
  
  /* use initialization list if there is one */
  if (initlist != NULL) {
    /* if its a Python list or tuple, initialize from it... */
    if ( islist || istuple ) {
      Dprint(("makeWrapper unpacking Python sequence\n"));
      tp = &(result->rep);
      for (index = 0; index<len; index++) {
	if ( islist ) {
	  pair = PyList_GetItem(initlist, index);
	} else {
	  pair = PyTuple_GetItem(initlist, index);
	}
	if (flag == SETFLAG) {
	  valid = TableGet1(tp, pair, 0, NOHASH, FORCE, &d1, &d2);
	  if (valid == -1) {
	    Py_DECREF(result);
	    return NULL;
	  }
	} else {
	  if (!PyArg_Parse(pair, "(OO)", &key, &map)) {
	    Py_DECREF(result);
	    return NULL;
	  }
	  valid = TableGet1(tp, key, map, NOHASH, FORCE, &d1, &d2);
	  if (valid == -1) {
	    Py_DECREF(result);
	    return NULL;
	  }
	}
      } /* endfor */
    } else { /* it must be a kj-Table... initialize from that... */
      Dprint(("makeWrapper augmenting from kj-table\n"));
      /* initWrapper = (TableWrapper *) initlist; already done... */
      valid = Taugment( &(result->rep), &(initWrapper->rep) );
      if (valid!=0) {
	Py_DECREF(result);
	return NULL;
      }
    }
  }
  return (PyObject *) result;
}

/* specialization for sets */
static PyObject * makekjSet(PyObject *module, PyObject *args)
{
  return makeWrapper(module, args, SETFLAG);
}

/* specialization for graphs */
static PyObject * makekjGraph(PyObject *module, PyObject *args)
{
  return makeWrapper(module, args, GRAPHFLAG);
}

/* specialization for dicts */
static PyObject * makekjDict(PyObject *module, PyObject *args)
{
  return makeWrapper(module, args, DICTFLAG);
}

#ifdef KJBDEBUG
static PyObject * Wdebug( PyObject *m, PyObject *a)
{
   if (DebugLevel) { DebugLevel = 0; }
   else { DebugLevel = 1; }
   Py_INCREF(Py_None);
   return Py_None;
 }
#endif

static void WrapperDeallocate(TableWrapper *wp)
{
  /* must properly decref references... */
  groupsDealloc( wp->rep.groups, wp->rep.flag, wp->rep.size );
  PyMem_Del(wp);
}

/* hash value: symmetrical on members, a symmetrical within pairs */
static long Wrapper_hash(TableWrapper *wp)
{
  enum BucketFlag flag = wp->rep.flag;
  long this, that;
  long result = 121345; /* silly init value */
  TableWalker tw;
  Dprint(("Whash\n"));
  if (wp->hashvalue != NOHASH) 
    { /* memoized hash value */
      return wp->hashvalue;
    }
  result *= (wp->rep.entries+1);
  (void) InitAll(&tw, &(wp->rep));
  while (tw.valid == 1) { 
    this = tw.hash;
    /* bug/feature:
       structures that differ only on unhashable maps
       will have the same hash value.  I don't know whether
       to keep this of "fix" it.  Hmmm.  */
    if (  (flag != SETFLAG)   &&(tw.map != 0)) { 
      GETHASH(that,tw.map);
      if (that == -1) { PyErr_Clear(); }
      this += (that*23); 
    }
    result ^= this;
    (void) NextAll(&tw);
  }
  if (tw.valid == -1) { return NOHASH; } /* error */
  if (result == -1) { result = 973; }
  wp->hashvalue = result;
  return result;
}

static PyObject * WrapperItems1(TableWrapper *wp, PyObject *args, 
			      long dokey, long domap)
{
  PyObject *resultlist, *membertuple;
  TableWalker tw;
  long index, entries;
  Dprint(("WItems1\n"));
  
  if (!PyArg_Parse(args, "")) { return NULL; } /* error */
  entries = wp->rep.entries;
  /* make a list for all entries */
  resultlist = PyList_New( entries );
  if (resultlist == NULL) { return NULL; } /* error */
  /* walk through the table */
  (void) InitAll(&tw, &(wp->rep));
  index = 0;
  while (tw.valid == 1) {
    /* sanity check */
    if (index >= entries) {
      Py_DECREF(resultlist);
      PyErr_SetString(PyExc_SystemError, "loop overflowing in WrapperItems");
      return NULL; /* error */
    }
    /* get only the key, if requested */
    if ((dokey != 0) && (domap == 0)) {
      Py_XINCREF(tw.key);
      PyList_SetItem(resultlist, index, tw.key);
    } else {
      /* get only the map, if requested */
      if ((domap != 0) && (dokey == 0)) {
	Py_XINCREF(tw.map);
	PyList_SetItem(resultlist, index, tw.map);
      } else {
	/* otherwise get both */
	membertuple = PyTuple_New(2);
	if (membertuple == NULL) {
	  Py_DECREF(resultlist);
	  return NULL;   /* error */
	}
	Py_XINCREF(tw.key);
	PyTuple_SetItem(membertuple, 0, tw.key);
	Py_XINCREF(tw.map);
	PyTuple_SetItem(membertuple, 1, tw.map);
	PyList_SetItem(resultlist, index, membertuple);
      }
    }
    index++;
    (void) NextAll(&tw);
  }
  if (tw.valid == -1) {
    Py_DECREF(resultlist);
    return NULL; /* error */
  }
  return resultlist;
}

static PyObject * WrapperItems(TableWrapper *wp, PyObject *args)
{
  Dprint(("WItems\n"));
  if (wp->rep.flag == SETFLAG) {
    /* for sets do key only */
    return WrapperItems1(wp, args, 1, 0);
  } else {
    /* for others, get both */
    return WrapperItems1(wp, args, 1, 1);
  }
}

/* prlong function with debug option */
static long WrapperPrint(TableWrapper *wp, FILE *fp, long flags)
{
  PyObject * items;
#ifdef WDEBUGPRINT
  if (WDEBUGPRINT) {
    return TableDump((wp->rep), fp);
  }
#endif
  switch (wp->rep.flag) {
  case SETFLAG:
    fprintf(fp, "kjSet("); break;
  case DICTFLAG:
    fprintf(fp, "kjDict("); break;
  case GRAPHFLAG:
    fprintf(fp, "kjGraph("); break;
  default:
    fprintf(fp, "??unknown table type??\n");
  }
  items = WrapperItems(wp, NULL);
  if (items == NULL) {
    fprintf(fp, "??couldn't allocate items??\n");
    return -1;
  }
  if (PyObject_Print(items, fp, 0) != 0) { return -1; }
  Py_DECREF(items);
  fprintf(fp, ")");
  return 0;
}

static PyObject* WrapperRepr(TableWrapper *wp)
{
  PyObject *items, *result, *itemstring;
  char buf[256];
  switch (wp->rep.flag) {
  case SETFLAG:
    sprintf(buf, "kjSet("); break;
  case DICTFLAG:
    sprintf(buf, "kjDict("); break;
  case GRAPHFLAG:
    sprintf(buf, "kjGraph("); break;
  default:
    PyErr_SetString(PyExc_SystemError, "Bad flag in table");
    return NULL;
  }
  result = PyString_FromString(buf);
  items = WrapperItems(wp, NULL);
  if (items == NULL) {
    return NULL;
  }
  itemstring = PyObject_Repr(items);
  Py_DECREF(items);
  PyString_ConcatAndDel(&result, itemstring);
  PyString_ConcatAndDel(&result, PyString_FromString(")"));
  return result;
}

/* nonzero testing */
static long Wrapper_nonzero(TableWrapper *wp)
{
  Dprint(("Wnonzero\n"));
  return (wp->rep.entries != 0);
}

/* comparison:
   if w1 and w2 are of same type then w1<w2 if
   1) w1 has fewer entries than w2
   2) w1, w2 have same number of entries and
   the min pair of w1 not in w2 is smaller than analogue for w2 wrt w1.
   fair enough?  I'm pretty sure this is a total order
   (orthographic on sorted elts?)
   they are == iff they have the same elts
   */
static long Wcompare(TableWrapper *left, TableWrapper *right)
{
  PyObject *lmem, *lmap, *rmem, *rmap;
  long lhash, rhash;
  long lentries, rentries, lfound, rfound, cmp;
  Table *ltable, *rtable;
  Dprint(("Wcompare\n"));
  /* the easy way out */
  if (((long) left) == ((long) right)) { return 0; }
  ltable = &(left->rep);
  rtable = &(right->rep);
  lentries = ltable->entries;
  rentries = rtable->entries;
  if (lentries<rentries) { return -1; }
  if (rentries<lentries) { return 1; }
  lfound = Tmindiff(ltable, rtable, &lmem, &lmap, &lhash);
  rfound = Tmindiff(rtable, ltable, &rmem, &rmap, &rhash);
  /* the above should never fail, but just in case... */
  if ( (lfound == -1) || (rfound == -1) ) {
    
    if (((long) left) < ((long) right)) { return -1; }
    else { return 1; }
  }
  /* case of non-identical equality, no difference found... */
  if ((lfound == 0) && (rfound == 0)) { return 0; }
  /* otherwise compare min differences */
  cmp = lhash - rhash;
  if (cmp == 0) { cmp = PyObject_Compare( lmem, rmem ); }
  if (cmp < 0) { return -1; }
  if (cmp > 0) { return 1; }
  /* mems are identical, try maps */
  if ( (lmap != 0) && (rmap != 0) ) {
    /* if we get this far the following shouldn't return 0, ever. */
    return PyObject_Compare(lmap,rmap);
  }
  /* this should be an error, but it can't be done?? */
  return 0;
}


static PyObject * Whas_key(TableWrapper *wp, PyObject *args)
{
  long test, rt, nxt, nxtb, isnew;
  long hashout;
  Bucketptr Bp;
  PyObject *key;
  Dprint(("Whas_key\n"));
  if ((args == NULL) || !PyArg_Parse(args, "O", &key)) { 
    PyErr_SetString(PyExc_TypeError, "table method has_key requires an argument");
    return NULL; 
  }
  test = tableMatch(&(wp->rep), key, 0, NOFORCE,
		    -1, -1, -1, NOHASH,
		    &rt, &nxt, &nxtb, &Bp, &hashout, &isnew);
  if (test == -1) { return NULL; } /* error */
  return PyInt_FromLong((long) test);
}

/*
  Get the neighbors of a node in a graph.
  */
static PyObject *Gneighbors(TableWrapper *wp, PyObject *args)
{
  PyObject *key, *resultlist;
  Table *tp; 
  TableWalker tw;
  long count, index;
  Dprint(("Gneighbors\n"));
  if ((args == NULL) || !PyArg_Parse(args, "O", &key)) { 
    PyErr_SetString(PyExc_TypeError, "table method neighbors requires an argument");
    return NULL; 
  }
  tp = &(wp->rep);
  if ( tp->flag == SETFLAG ) {
    PyErr_SetString(PyExc_TypeError, "neighbors not defined for table of this type");
    return NULL;
  }
  /* find out how many neighbors there are */
  count = 0;
  (void) Initbykey(&tw, tp, key, NOHASH);
  Dprint(("Gneighbors: counting neighbors\n"));
  while (tw.valid == 1) {
    count++;
    (void) Nextbykey(&tw);
  }
  if (tw.valid == -1) { return NULL; } /* error */
  /* make a list large enough */
  Dprint(("Gneighbors: making resultlist\n"));
  resultlist = PyList_New( count );
  if (resultlist == NULL) { return NULL; } /* failure to allocate */
  /* record neighbors in list */
  (void) Initbykey(&tw, tp, key, NOHASH);
  index = 0;
  Dprint(("Gneighbors: storing results\n"));
  while (tw.valid == 1) {
    if (index >= count) {
      Py_DECREF(resultlist);
      PyErr_SetString(PyExc_SystemError, "loop overflow in neighbors calculation");
      return NULL;
    }
    Py_XINCREF(tw.map);
    PyList_SetItem(resultlist, index, tw.map);
    index++;
    (void) Nextbykey(&tw);
  }
  if (tw.valid == -1) {
    Py_DECREF(resultlist);
    return NULL;
  }
  return resultlist;
}

/* utility function for extracting keys or values
   if domaps is set this will get maps uniquely *only if
   all maps are hashable!* 
   */
static PyObject *Wparts(TableWrapper *wp, PyObject *args, long domaps)
{
  TableWalker tw;
  Table *tp, *Settp;
  TableWrapper *tempSet;
  PyObject *mem, *map, *items;
  long test;
  Dprint(("Wparts\n"));
  if (!PyArg_Parse(args, "")) { return NULL; } /* error */
  tp = &(wp->rep);
  if (tp->flag == SETFLAG) {
    PyErr_SetString(PyExc_TypeError, "keys/values not defined for sets");
    return NULL;
  }
  /* initialize a temp set to hold the keys */
  /* try to save a little space here, may actually waste space sometimes */
  tempSet = (TableWrapper *) newWrapper(tp->entries/4, SETFLAG);
  if (tempSet == NULL) { return NULL; }
  Settp = &(tempSet->rep);
  /* walk the table and record the keys */
  (void) InitAll(&tw, tp);
  test = 0;
  while ((tw.valid == 1) && (test != -1)) {
    if (domaps) {
      test = TableGet1(Settp, tw.map, 0, NOHASH, FORCE, &mem, &map);
    } else {
      test = TableGet1(Settp, tw.key, 0, tw.hash, FORCE, &mem, &map);
    }
    (void) NextAll(&tw);
  }
  if ((test == -1) || (tw.valid == -1)) {
    Py_DECREF(tempSet);
    return NULL;
  }
  items = WrapperItems(tempSet, NULL);
  Py_DECREF(tempSet);
  return items;
}

static PyObject *Wkeys(TableWrapper *wp, PyObject *args)
{
  Dprint(("Wkeys\n"));
  return Wparts(wp, args, 0);
}

static PyObject *Wvalues(TableWrapper *wp, PyObject *args)
{
  Dprint(("Wvalues\n"));
  /*  return Wparts(wp, args, 1); -- wrong! */
  return WrapperItems1(wp, args, 0, 1);
}

/* choose an arbitrary key from the table or raise an indexerror if none */
static PyObject *Wchoose_key(TableWrapper *wp, PyObject *args)
{
  TableWalker tw;
  Dprint(("Wchoose_key\n"));
  if (!PyArg_Parse(args, "")) { return NULL; } /* error */
  (void) InitAll(&tw, &(wp->rep));
  if (tw.valid == 1) {
    Py_XINCREF(tw.key);
    return tw.key;
  }
  if (tw.valid == 0) {
    PyErr_SetString(PyExc_IndexError, "table is empty");
    return NULL;
  }
  /* external error otherwise (tw.valid == -1) */
  return NULL;
}

static PyObject *WSubset(TableWrapper *subset, PyObject *args)
{
  TableWrapper *superset;
  long hashout;
  long rt, nxt, nxtb, isnew, found;
  Bucketptr Bp;
  TableWalker tw;
  Table *supertable;
  Dprint(("WSubset\n"));
  /* verify argument */
  if (args == NULL) {
    PyErr_SetString(PyExc_TypeError, "Subset test requires argument");
    return NULL;
  }
  if (!PyArg_Parse(args, "O", &superset)) { return NULL; }
  if ( !is_kjTable(superset)) {
    PyErr_SetString(PyExc_TypeError, "Subset defined only between kj-tables");
    return NULL;
  }
  /* walk through subset, test for membership of all members */
  (void) InitAll(&tw, &(subset->rep));
  supertable = &(superset->rep);
  while (tw.valid == 1) {
    found = tableMatch(supertable, tw.key, tw.map, NOFORCE,
		       -1, -1, -1, tw.hash,
		       &rt, &nxt, &nxtb, &Bp, &hashout, &isnew);
    if (found == -1) { return NULL; } /* error */
    if (found == 0) {
      /* subset test fails */
      return PyInt_FromLong((long) 0);
    }
    (void) NextAll(&tw);
  }
  if (tw.valid == -1) { return NULL; } /* error */
  /* otherwise, success */
  return PyInt_FromLong((long) 1);
}

/* transitive closure of a graph */
/* algorithm could be made faster, KISS for now. */
static PyObject *Wtransclose(TableWrapper *wp, PyObject *args)
{
  Table *source, *target, Delta;
  TableWrapper *closure;
  enum BucketFlag flag;
  long count, test, abort;
  
  Dprint(("Wtransclose\n"));
  if (!PyArg_Parse(args, "")) { return NULL; } /* error */
  source = &(wp->rep);
  flag = source->flag;
  if (flag != GRAPHFLAG) {
    PyErr_SetString(PyExc_TypeError, 
	       "transitive closure not defined for this table type");
    return NULL;
  }
  Dprint(("tc: allocating closure\n"));
  closure = (TableWrapper *) newWrapper(source->entries, flag);
  if (closure == NULL) { return NULL; }
  propagateDirt(wp, closure);
  target = &(closure->rep);
  /* closure of source contains source */
  Dprint(("tc: augmenting closure\n"));
  test = Taugment( target, source );
  if (test != 0) {
    Py_DECREF(closure);
    return NULL;
  }
  /* initialize temp table Delta for transitive arcs */
  test = initTable(&Delta, flag, 0);
  /* add all transitive arcs */
  abort = 0;
  do {
    /* Delta = (source o target) - target */
    Dprint(("tc: calling tcompose\n"));
    count = Tcompose(&Delta, source, target, target, 0);
    Dprint(("tc: delta computed, count = %ld\n",count));
    if (count<0) { abort = 1; }
    if ((abort == 0) && (count>0)) {
      /* target = target U Delta */
      Dprint(("tc: augmenting target\n"));
      test = Taugment( target, &Delta );
      Dprint(("tc: done augmenting target\n"));
      if (test!=0) { abort = 1; }
      tableClear( &Delta );
    }
    Dprint(("tc: loop body done, count=%ld, abort=%ld\n",count,abort));
    /* loop terminates when (source o target) subset target */
  } while ((count>0) && (abort==0));
  Dprint(("tc: deallocating Delta\n"));
  groupsDealloc(Delta.groups, flag, Delta.size);
  if (abort != 0) {
    Py_DECREF(closure);
    return NULL;
  }
  return (PyObject *) closure;
}

static void Wset_hash_error(void)
{
  PyErr_SetString(PyExc_TypeError, "table has been hashed, it is now immutable");
}

static PyObject * Wdelete_arc(TableWrapper *wp, PyObject *args)
{
  PyObject *key, *map;
  Dprint(("Wdelete_arc\n"));
  if ((args == NULL) || !PyArg_Parse(args, "(OO)", &key, &map)) {
    PyErr_SetString(PyExc_TypeError, "delete_arc requires two arguments");
    return NULL;
  }
  if (wp->rep.flag == SETFLAG) {
    PyErr_SetString(PyExc_TypeError, "delete_arc not defined on sets");
    return NULL;
  }
  if (wp->hashvalue != NOHASH) {
    Wset_hash_error();
    return NULL;
  }
  if (deleteFromTable(&(wp->rep), key, map) == 0) { return NULL; }
  Py_INCREF(Py_None);
  return Py_None;
}

/* simple membership test */
static PyObject * Wmember1(TableWrapper *wp, PyObject *args, long insert)
{
  PyObject *key, *map;
  Table *tp;
  enum BucketFlag flag;
  long hashout;
  long rt, nxt, nxtb, isnew, found;
  Bucketptr Bp;
  Dprint(("Wmember1\n"));
  tp = &(wp->rep);
  flag = tp->flag;
  /* determine key and map */
  if (args == NULL) {
    PyErr_SetString(PyExc_TypeError, "membership test requires argument(s)");
    return NULL;
  }
  if ((insert!=0) & (wp->hashvalue!=NOHASH)) {
    Wset_hash_error();
    return NULL;
  }
  if (flag == SETFLAG) {
    if (!PyArg_Parse(args, "O", &key)) { return NULL; }
    map = 0;
  } else {
    if (!PyArg_Parse(args, "(OO)", &key, &map)) { return NULL; }
  }
  if (insert == 0) {
    found = tableMatch(tp, key, map, NOFORCE,
		       -1, -1, -1, NOHASH,
		       &rt, &nxt, &nxtb, &Bp, &hashout, &isnew);
    return PyInt_FromLong((long) found);
  } else {
    found = TableGet1(tp, key, map, NOHASH, FORCE, &key, &map);
    if (found == -1) { return NULL; }
    Py_INCREF(Py_None);
    return Py_None;
  }
}

static PyObject * Wmember(TableWrapper *wp, PyObject *args)
{
  Dprint(("Wmember\n"));
  return Wmember1(wp, args, 0);
}

static PyObject * Waddmember(TableWrapper *wp, PyObject *args)
{
  Dprint(("Waddmember\n"));
  return Wmember1(wp, args, 1);
}

/* generate identity graph from a set */
static PyObject * Gidentity(TableWrapper *SourceSet, PyObject *args)
{
  TableWrapper *resultGraph;
  Table *Graphtp;
  TableWalker tw;
  long test;
  PyObject *d1, *d2;
  Dprint(("Gidentity\n"));
  if (!PyArg_Parse(args, "")) { return NULL; }
  if (SourceSet->rep.flag != SETFLAG) {
    PyErr_SetString(PyExc_TypeError, "graph identity not defined for table of this type");
    return NULL;
  }
  /* make a new DICTIONARY for result, may waste space for graphs */
  resultGraph = (TableWrapper *) 
    newWrapper(SourceSet->rep.entries/3, DICTFLAG);
  if (resultGraph == NULL) { return NULL; }
  Graphtp = &(resultGraph->rep);
  /* walk through the set */
  (void) InitAll(&tw, &(SourceSet->rep));
  test = 0;
  while ((tw.valid == 1) && (test != -1)) {
    test = TableGet1(Graphtp, tw.key, tw.key, tw.hash, FORCE, &d1, &d2); 
    (void) NextAll(&tw);
  }
  if ((test == -1) || (tw.valid == -1)) {
    Py_DECREF(resultGraph);
    return NULL;
  }
  return (PyObject *) resultGraph;
}

static PyObject * Greachable(TableWrapper *graph, PyObject *args)
{
  PyObject *key, *d1, *d2;
  TableWrapper *resultSet, *tempSet, *deltaSet;
  Table *resulttp, *temptp, *deltatp, *graphtp;
  TableWalker deltaW, graphW;
  long test, fail;
  Dprint(("Greachable\n"));
  if (graph->rep.flag == SETFLAG) {
    PyErr_SetString(PyExc_TypeError, "reachable not defined for this table type");
    return NULL;
  }
  if ((args == NULL) || (!PyArg_Parse(args, "O", &key))) {
    PyErr_SetString(PyExc_TypeError, "reachable requires key argument");
    return NULL;
  }
  /* make result and temporary sets for computation */
  resultSet = (TableWrapper *) newWrapper(0, SETFLAG);
  tempSet = (TableWrapper *) newWrapper(0, SETFLAG);
  deltaSet = (TableWrapper *) newWrapper(0, SETFLAG);
  if ((deltaSet == NULL) || (resultSet == NULL) || (tempSet == NULL)) { 
    Py_DECREF(deltaSet);
    Py_DECREF(resultSet);
    Py_DECREF(tempSet);
    return NULL; 
  }
  propagateDirt(graph, resultSet);
  /* get table pointers */
  resulttp = &(resultSet->rep);
  temptp = &(tempSet->rep);
  deltatp = &(deltaSet->rep);
  graphtp = &(graph->rep);
  /* initialize deltaSet to contain only the key */
  test = TableGet1(deltatp, key, 0, NOHASH, FORCE, &d1, &d2);
  fail = 0;
  if (test == -1) { fail = 1; }
  /* repeat the following loop until delta becomes empty */
  while ((deltatp->entries > 0) && (fail == 0)) {
    /* put all neighbors to delta members in temp */
    (void) InitAll(&deltaW, deltatp);
    while ((deltaW.valid == 1) && (fail == 0)) {
      /* use this entry in delta to traverse neighbors in graph */
      (void) Initbykey(&graphW, graphtp, deltaW.key, deltaW.hash);
      while ((graphW.valid == 1) && (fail == 0)) {
	test = TableGet1(temptp, graphW.map, 0, NOHASH, FORCE, &d1, &d2);
	if (test == -1) { fail = 1; }
	(void) Nextbykey(&graphW);
      }
      if (graphW.valid == -1) { fail = 1; } /* external error */
      (void) NextAll(&deltaW);
    }
    if (deltaW.valid == -1) { fail = 1; } /* external error */
    /* clear delta and reinit to temp-result */
    if (fail == 0) {
      tableClear(deltatp);
      test = Tintdiff(deltatp, temptp, resulttp, 0, 0);
      if (test<0) { fail = 1; }
    }
    /* now add delta to result and clear temp */
    if (fail == 0) {
      tableClear( temptp );
      test = Taugment( resulttp, deltatp );
      if (test != 0) { fail = 1; }
    }
  } /* endwhile delta has entries... */
  /* get rid of temporaries */
  Py_DECREF(tempSet);
  Py_DECREF(deltaSet);
  if (fail != 0) {
    Py_DECREF(resultSet);
    return NULL;
  }
  return (PyObject *) resultSet;
}

/* Clean filter: returns argument if the table
   is clean, otherwise NULL */
static PyObject * WClean(TableWrapper *wp, PyObject *args)
{
  Dprint(("WClean\n"));
  if (!PyArg_Parse(args, "")) { return NULL; }
  if (wp->rep.Dirty) {
    Py_INCREF(Py_None);
    return Py_None;
  } else {
    Py_INCREF(wp);
    return (PyObject *) wp;
  }
}

/* force a table to be dirty */
static PyObject * WSoil(TableWrapper *wp, PyObject *args)
{
  Dprint(("WSoil\n"));
  if (!PyArg_Parse(args, "")) { return NULL; }
  wp->rep.Dirty = 1;
  Py_INCREF(Py_None);
  return Py_None;
}

/* force a table to be clean */
static PyObject * WWash(TableWrapper *wp, PyObject *args)
{
  Dprint(("WWash\n"));
  if (!PyArg_Parse(args, "")) { return NULL; }
  wp->rep.Dirty = 0;
  Py_INCREF(Py_None);
  return Py_None;
}

/* remap remaps a dictionary using a table which represents
   key rename pairs.
   Can be used to duplicate and/or project mappings.
   If the result is "dirty" (ie, if name/value collisions)
   Py_None is returned.
*/
static PyObject * Dremap(TableWrapper *wp, PyObject *args)
{
  TableWrapper *remapper, *result;
  long count;
  Dprint(("Dremap\n"));
  if (!is_kjDictobject(wp)) {
    PyErr_SetString(PyExc_TypeError, "remap only defined for kjDicts");
    return NULL;
  }
  if (args == NULL) {
    PyErr_SetString(PyExc_TypeError, "remap requires equality table argument");
    return NULL;
  }
  if (!PyArg_Parse(args, "O", &remapper)) { return NULL; }
  if ( !is_kjTable(remapper)) {
    PyErr_SetString(PyExc_TypeError, "remap defined only between kj-tables");
    return NULL;
  }
  /* don't assume anything about size of result */
  result = (TableWrapper *) newWrapper(0, DICTFLAG);
  if (result == NULL) { return NULL; } /* allocation error */
  propagateDirt(wp, result);
  propagateDirt(remapper, result);
  /* return NONE if result is dirty (save some work) */
  if (result->rep.Dirty != 0) {
    Py_DECREF(result);
    Py_INCREF(Py_None);
    return Py_None;
  }
  count = Tcompose( &(result->rep), &(remapper->rep), &(wp->rep), 0, 0);
  if (count<0) {
    Py_DECREF(result);
    return NULL; /* error */
  }
  /* return NONE if result is dirty after composition */
  if (result->rep.Dirty != 0) {
    Py_DECREF(result);
    Py_INCREF(Py_None);
    return Py_None;
  }
  return (PyObject *) result;
}

/* forward declarations needed below */
static PyObject * kjDict_subscript(TableWrapper *Set, PyObject *key);
static long kjDict_ass_subscript(PyObject *Set, PyObject *key, PyObject *thing);

/* for dumping a dictionary to a tuple */
/* D.dump(tup) produces D[tup[0]] if tup of len 1
      or (D[tup[0]], D[tup[1]],...) if tup of len > 1
      or keyerror if keys aren't present.
*/
static PyObject * kjDictDump(TableWrapper *wp, PyObject *args)
{
  PyObject *result, *input, *key, *map;
  long valid, index, length;
  Dprint(("kjDictDump\n"));
  if (!is_kjDictobject(wp) && !is_kjGraphobject(wp)) {
    PyErr_SetString(PyExc_TypeError, "dump only defined for kjDicts");
    return NULL;
  }
  if (args == NULL) {
    PyErr_SetString(PyExc_TypeError, "dictionary dump requires tuple argument");
    return NULL;
  }
  valid = PyArg_Parse(args, "O", &input);
  if (valid && (PyTuple_Check(input))) {
    length = PyTuple_Size(input);
    if (length < 1) {
      PyErr_SetString(PyExc_TypeError, "dictionary dump requires nonempty tuple arg");
      return NULL;
    }
    if (length == 1) {
      /* return D[input[0]] */
      key = PyTuple_GetItem(input, 0);
      return kjDict_subscript(wp, key); /* incref done by function */
    } else {
      /* return ( D[input[0]], D[input[1]], ..., D[input[n]] ) */
      result = PyTuple_New(length);
      if (result == NULL) { return NULL; } /* failure to allocate */
      for (index = 0; index<length; index++) {
	key = PyTuple_GetItem(input, index);
	map = kjDict_subscript(wp, key); /* incref done by function */
	if (map == NULL) { 
	  Py_DECREF(result);
	  return NULL;  /* keyerror, normally */
	}
        /* map was increfed by kjDict_subscript already */
	PyTuple_SetItem(result, index, map);
      }
      return result;
    }
  } else {
    PyErr_SetString(PyExc_TypeError, "dictionary dump arg must be tuple");
    return NULL;
  }
}

/* the parallel operation to dump */
/* kjUndump(tup, thing) produces kjDict( [ (tup[0], thing ) ] )
     if tup of len 1 or
       kjDict( [ (tup[0], thing[0]), (tup[1], thing[1]) ] )
     if tup of len>1 and thing of same len, or error
*/  
static PyObject * kjUndumpToDict(PyObject *self, PyObject *args)
{
  TableWrapper *result;
  PyObject *tup, *thing, *key, *map;
  long valid, index, length;
  Dprint(("kjUndump\n"));
  if (args == NULL) {
    PyErr_SetString(PyExc_TypeError, "kjUndump called with no args");
    return NULL;
  }
  valid = PyArg_Parse(args, "(OO)", &tup, &thing);
  if (valid) {
    valid = PyTuple_Check(tup);
  }
  if (valid) {
    length = PyTuple_Size(tup);
    if (length<1) {
      PyErr_SetString(PyExc_ValueError, "kjUndump: tuple must be non-empty");
      return NULL;
    }
    /* try to save a little space */
    result = (TableWrapper *) newWrapper(length/2, DICTFLAG);
    if (result == NULL) { return NULL; } /* allocation failure */
    if (length == 1) {
      /* return D[tup[0]] = thing */
      key = PyTuple_GetItem(tup, 0);
      valid = kjDict_ass_subscript((PyObject *) result, key, thing);
      if (valid == -1) {
	Py_DECREF(result);
	return NULL;
      }
      return (PyObject *) result;
    } else {
      /* return for i in len(tup): 
                  D[tup[i]] = thing[i]
      */
      if (PyTuple_Check(thing)) {
	if (PyTuple_Size(thing) != length) {
	  PyErr_SetString(PyExc_TypeError,"kjUndump -- tuple lengths don't match");
	  return NULL;
	}
	for (index = 0; index<length; index++) {
	  key = PyTuple_GetItem(tup, index);
	  map = PyTuple_GetItem(thing, index);
	  valid = kjDict_ass_subscript((PyObject *) result, key, map);
	  if (valid == -1){
	    Py_DECREF(result);
	    return NULL;
	  }
	}
	return (PyObject *) result;
      } else {
	PyErr_SetString(PyExc_TypeError,"kjUndump -- nonunary tuple with non-tuple");
	return NULL;
      }
    }
  } else {
    PyErr_SetString(PyExc_TypeError,"kjUndump requires 2 args, first must be tuple");
    return NULL;
  }
}

/* special function for restricting indices
     x.restrict(y) returns restriction of x to keys of y
   "same as"

     kjSet(x) * y

   but faster, doesn't allocate unneeded set
*/
static PyObject * kjWRestrict(TableWrapper *wp, PyObject *args)
{
  long test;
  TableWrapper *result, *compare;
  PyObject *d1, *d2; /* dummies */
  enum BucketFlag flag;
  TableWalker compareWalker, wpWalker;
  Table *tp, *resulttp, *comparetp;
  if ((args == NULL) || (!PyArg_Parse(args, "O", &compare))) {
    PyErr_SetString(PyExc_TypeError, 
               "restriction function requires one kjTable argument");
    return NULL;
  }
  if (!is_kjTable(compare)) {
    PyErr_SetString(PyExc_TypeError, "restrict function requires kjTable argument");
    return NULL;
  }
  flag = wp->rep.flag;
  /* make no assumption about size of result */
  result = (TableWrapper *) newWrapper(0, flag);
  if (result == NULL) { return NULL; } /* allocation failure */
  /* heuristic: walk through restrictor if much smaller than self
                otherwise walk through self */
  tp = &(wp->rep);
  resulttp = &(result->rep);
  comparetp = &(compare->rep);
  if (tp->entries > 4 * comparetp->entries) {
    /* walk through the restrictor */
    (void) InitAll(&compareWalker, comparetp);
    test = compareWalker.valid;
    while ((compareWalker.valid == 1) && (test!=-1)) {
      /* walk through matches for key in tp */
      /* (if many matches for same key, may not be efficient) */
      (void) Initbykey(&wpWalker, tp, compareWalker.key, compareWalker.hash);
      while ((wpWalker.valid == 1) && (test != -1)) {
	/* put member from wpWalker in result */
	test = TableGet1(resulttp, wpWalker.key, wpWalker.map, wpWalker.hash,
		         FORCE, &d1, &d2);
	if (test!=-1) {
	  (void) Nextbykey(&wpWalker);
	}
	if (wpWalker.valid == -1) { test = -1; }
      }
      if (test!=-1) {
	(void) NextAll(&compareWalker);
      }
      if (compareWalker.valid == -1) { test = -1; }
    }
  } else {
    /* walk through tp */
    (void) InitAll(&wpWalker, tp);
    test = wpWalker.valid;
    while ((wpWalker.valid == 1) && (test!=-1)) {
      /* see if there is a match in compare */
      (void) Initbykey(&compareWalker, comparetp,
		       wpWalker.key, wpWalker.hash);
      /* if there, insert elt in result */
      if (compareWalker.valid == 1) {
	test = TableGet1(resulttp, wpWalker.key, wpWalker.map, wpWalker.hash,
			 FORCE, &d1, &d2);
      }
      if (compareWalker.valid == -1) { test = -1; }
      if (test != -1) {
	(void) NextAll(&wpWalker);
      }
      if (wpWalker.valid == -1) { test = -1; }
    }
  }
  /* test for error cases */
  if (test == -1) {
    Py_DECREF(result);
    return NULL;
  }
  /* otherwise just return result */
  return (PyObject *) result;
}

/* special function for retrieving from dict-dumped indices
   "same as"

     def x.dget(dict, dumper):
         try:
             d = dict.dump(dumper)
             if d == Py_None: d = (Py_None,)
             return x.neighbors(d)
         except PyExc_KeyError: return Py_None

   x is kjDict or kjGraph
   dict is kjDict or kjGraph
   dumper is tuple
   dump of Py_None is mapped to (Py_None,) to avoid ambiguity elsewhere
    (may retrieve "too many neighbors" for key of Py_None or (Py_None,)

defined benieth following utility function as
  static PyObject * kjWdget(TableWrapper *wp, PyObject *args)

*/

/* same as above but if testonly is set, then instead of x.neighbors(d)
   return 1 if neighbors set is nonempty, else, 0
*/
/* #ifndef PYTHON1DOT2 */
static PyObject * kjWdget1(TableWrapper *wp, PyObject *args, long testonly)
{
  PyObject *d, *dumper, *result, *err_type /*, *err_value */;
  TableWrapper *dict;
  /* get and verify args */
  if (args == NULL) {
    PyErr_SetString(PyExc_TypeError, "dget requires 2 arguments");
    return NULL;
  }
  if (!PyArg_Parse(args, "(OO)", &dict, &dumper)) {
    PyErr_SetString(PyExc_TypeError,
	       "dget requires dict, dumper");
    return NULL;
  }
  if (!((is_kjDictobject(dict)) || (is_kjGraphobject(dict)))) {
    PyErr_SetString(PyExc_TypeError,
	       "first arg of dget must be kjDict or kjGraph");
    return NULL;
  }
  if (!PyTuple_Check(dumper)) {
    PyErr_SetString(PyExc_TypeError,
	       "second arg of dget must be tuple");
    return NULL;
  }
  /* initialize d */
  d = kjDictDump(dict, dumper);
  if (d == NULL) {
    /* unable to dump */
    /* check that error was a keyerror ??? */
    /* err_get(&err_type, &err_value); */
    err_type = PyErr_Occurred();
    if (err_type != PyExc_KeyError) {
      /* some other error... abort */
      /* PyErr_SetObject(err_type, err_value); */
      return NULL;
    }
    PyErr_Clear();
    /* in case of PyExc_KeyError, just return Py_None */
    Py_INCREF(Py_None);
    return Py_None;
  }
  /* if dump was successful, return neighbors */
  /* ??? should return d also ??? */
  if (testonly == 0) {
    result = Gneighbors(wp, d);
  } else {
    result = Whas_key(wp, d);
  }
  Py_DECREF(d);
  return result;
}
/* #endif */

/* variant of dget, that just tests for presence in index
   "same as"

     def x.dtest(dict, dumper):
         try:
             d = dict.dump(dumper)
             if d == Py_None: d = (Py_None,)
             return x.has_key(d)
         except PyExc_KeyError: return Py_None
*/
/* #ifndef PYTHON1DOT2 */
static PyObject * kjWdtest(TableWrapper *wp, PyObject *args)
{
  return kjWdget1(wp, args, 1); /* test only */
}
/* #endif
   #ifndef PYTHON1DOT2 */
static PyObject * kjWdget(TableWrapper *wp, PyObject *args)
{
  return kjWdget1(wp, args, 0); /* don't test only */
}
/* #endif */

/*
   miscellaneous methods for these types 
*/
static struct PyMethodDef Wrapper_methods[] = {
        {"member",      (PyCFunction)Wmember},
        {"add",         (PyCFunction)Waddmember},
        {"delete_arc",  (PyCFunction)Wdelete_arc},
        {"has_key",     (PyCFunction)Whas_key},
	{"choose_key",  (PyCFunction)Wchoose_key},
        {"Clean",       (PyCFunction)WClean},
	{"neighbors",   (PyCFunction)Gneighbors},
	{"dump",        (PyCFunction)kjDictDump},
/* #ifndef PYTHON1DOT2 */
        {"dget",        (PyCFunction)kjWdget},
        {"dtest",       (PyCFunction)kjWdtest},
/* #endif */
	{"reachable",   (PyCFunction)Greachable},
	{"subset",      (PyCFunction)WSubset},
        {"items",       (PyCFunction)WrapperItems},
        {"keys",        (PyCFunction)Wkeys},
        {"values",      (PyCFunction)Wvalues},
        {"ident",       (PyCFunction)Gidentity},
        {"remap",       (PyCFunction)Dremap},
	{"restrict",    (PyCFunction)kjWRestrict},
	{"tclosure",    (PyCFunction)Wtransclose},
	{"Soil",        (PyCFunction)WSoil},
	{"Wash",        (PyCFunction)WWash},
        {NULL,          NULL}           /* sentinel */
};

/* getattr snarfed from mappingobject.c */
static PyObject * Wrapper_getattr(PyObject *mp, char *name)
{
  return Py_FindMethod(Wrapper_methods, (PyObject *)mp, name);
}


/* methods for special behaviors as number and mapping */

/* undefined operations */
static PyObject * undefbin(PyObject *v, PyObject *w)
{
  PyErr_SetString(PyExc_TypeError, "op not valid for table of this type");
  return NULL;
}
static PyObject * undefter(PyObject *v, PyObject *w, PyObject *z)
{
  PyErr_SetString(PyExc_TypeError, "op not valid for table of this type");
  return NULL;
}
static PyObject * undefun(PyObject *v)
{
  PyErr_SetString(PyExc_TypeError, "op not valid for table of this type");
  return NULL;
}

/* transpose of non 1:1 dict will have nondeterministic results */
static PyObject *Wtranspose(TableWrapper *source)
{
  TableWrapper *result;
  long size, test;
  Dprint(("Wtranspose\n"));
  if (source->rep.flag == SETFLAG) {
    PyErr_SetString(PyExc_TypeError, "Cannot transpose set");
    return NULL;
  }
  /* conservative estimate of size (may save space, maybe not) */
  size = source->rep.entries;
  size = size/2;
  result = (TableWrapper *) newWrapper(size, source->rep.flag);
  if (result == NULL) { return NULL; } /* error */
  propagateDirt(source, result);
  test = Ttranspose( &(result->rep), &(source->rep) );
  if (test!=0) {
    Py_DECREF(result);
    return NULL;
  }
  return (PyObject *) result;
}
  
static PyObject *Wunion(TableWrapper *left, TableWrapper *right)
{
  enum BucketFlag flag;
  TableWrapper *result;
  long size, test;
  Dprint(("Wunion\n"));
  /* Py_None unioned with anything returns Py_None (universal set) */
  if (((PyObject *) left == Py_None) || ((PyObject *) right == Py_None)) {
    Py_INCREF(Py_None);
    return Py_None;
  }
  /* arbitrary size heuristic */
  if (left->rep.entries > right->rep.entries) 
    { size = left->rep.entries; }
  else 
    { size = right->rep.entries; }
  size = size/2; /* conservative to save space (maybe) */
  /* determine coercion if possible, default=more general */
  test = FlagCoercion(left->rep.flag, right->rep.flag, &flag, 1);
  if (test != 1) {
    PyErr_SetString(PyExc_TypeError, "incompatible types for table union");
    return NULL;
  }
  /* allocate a wrapper and augment it with both inputs */
  result = (TableWrapper *) newWrapper(size, flag);
  if (result == NULL) { return NULL; } /* error */
  propagateDirt( left, result );
  propagateDirt( right, result );
  test = Taugment( &(result->rep), &(left->rep) );
  if (test == 0) {
    test = Taugment( &(result->rep), &(right->rep) );
  }
  if (test!=0) {
    Py_DECREF(result);
    return NULL;
  }
  return (PyObject *) result;
}

/* utility function for intersection and difference */
static PyObject * Wintdiff(TableWrapper *left, TableWrapper *right,
			 long include, enum BucketFlag flagout)
{
  TableWrapper *result;
  long count;
  /* determine the size needed */
  Dprint(("Wintdiff\n"));
  count = Tintdiff(NULL, &(left->rep), &(right->rep), include, 1);
  if (count < 0) { return NULL; } /* error */
  /* be conservative, for fun */
  count = count / 2;
  /* allocate a wrapper of this size and initialize it */
  result = (TableWrapper *) newWrapper(count, flagout);
  if (result == NULL) { return NULL; } /* error */
  propagateDirt( left, result );
  propagateDirt( right, result );
  count = Tintdiff(&(result->rep), &(left->rep), &(right->rep), include, 0);
  if (count < 0) {
    Py_DECREF(result);
    return NULL;
  }
  return (PyObject *) result;
}

/* intersection */
static PyObject * Wintersect(TableWrapper *left, TableWrapper *right)
{
  long test;
  enum BucketFlag flag, lflag, rflag;
  Dprint(("Wintersect\n"));
  /* Py_None intersected with anything returns copy of anything... */
  if ((PyObject *)left == Py_None) {
     return Wunion(right, right);
  }
  if ((PyObject *)right == Py_None) {
     return Wunion(left, left);
  }
  /* determine flag: default to less general */
  rflag = right->rep.flag;
  lflag = left->rep.flag;
  /* coerce to more general, unless one arg is a set,
     in which case coerce to set */
  if ( (rflag != lflag) && ((rflag == SETFLAG)||(lflag == SETFLAG)) ) {
    PyErr_SetString(PyExc_TypeError, "mixed intersection not allowed with kjSet");
    return NULL;
  }
  test = FlagCoercion(left->rep.flag, right->rep.flag, &flag, -1);
  if (test!=1) {
    PyErr_SetString(PyExc_TypeError, "unable to coerce for intersection");
    return NULL;
  }
  /* iterate over the smaller argument */
  if ((left->rep.entries) < (right->rep.entries)) {
    return Wintdiff(left, right, 1, flag);
  } else {
    return Wintdiff(right, left, 1, flag);
  }
}

/* difference */
static PyObject * Wdifference(TableWrapper *left, TableWrapper *right)
{
  enum BucketFlag lflag, rflag;
  /* left cannot be Py_None */
  Dprint(("Wdifference\n"));
  if ((PyObject *)left == Py_None) {
    PyErr_SetString(PyExc_TypeError, "cannot difference from Py_None");
    return NULL;
  }
  /* if right is Py_None return empty */
  if ((PyObject *)right == Py_None) {
    return (PyObject *) newWrapper(0, left->rep.flag);
  }
  rflag = right->rep.flag;
  lflag = left->rep.flag;
   /* diff default coerce to whatever left is, unless one arg is a
      set, in which case raise an error */
  if ( (rflag != lflag) && ((rflag == SETFLAG)||(lflag == SETFLAG)) ) {
    PyErr_SetString(PyExc_TypeError, "mixed difference not allowed with kjSet");
    return NULL;
  }
  return Wintdiff(left, right, 0, lflag);
}

/* composition of two tables */
static PyObject * Wcompose(TableWrapper *left, TableWrapper *right)
{
  enum BucketFlag flag;
  TableWrapper *result;
  long test, count;
  Table *Ltable, *Rtable;
  Dprint(("Wcompose\n"));
  /* neither arg may be Py_None */
  if (((PyObject *)left == Py_None) || ((PyObject *)right == Py_None)) {
    PyErr_SetString(PyExc_TypeError, "cannot compose Py_None");
    return NULL;
  }
  Ltable = &(left->rep);
  Rtable = &(right->rep);
  /* find coercion, prefer more general */
  test = FlagCoercion(Ltable->flag, Rtable->flag, &flag, 1);
  if (test!=1) {
    PyErr_SetString(PyExc_TypeError, "incompatible types for composition");
    return NULL;
  }
  /* DON'T determine required table size, (not easily done correctly) */
  count = 0;
  /* commented
  count = Tcompose(0, Ltable, Rtable, 0, 1);
  if (count<0) { return NULL; }
  count = count/2;
  */
  /* allocate result */
  result = (TableWrapper *) newWrapper(count, flag);
  if (result == NULL) { return NULL; } /* error */
  propagateDirt( left, result );
  propagateDirt( right, result );
  count = Tcompose(&(result->rep), Ltable, Rtable, 0, 0);
  if (count < 0) {
    Py_DECREF(result);
    return NULL;  /* error */
  }
  return (PyObject *) result;
}

/* coercion:
    just check that pw is either Py_None, kjSet, kjGraph or kjDict
    all other logic is at the function level
  (Py_None == universal set)
*/
static long Wrapper_coerce(PyObject **pv, PyObject **pw)
{
  PyObject *w;
  w = *pw;
  Dprint(("Wcoerce\n"));
  if ( (w == Py_None) || 
       is_kjTable(w) ) {
    /* both w and *pv are "returned", hence must be increfed */
    Py_INCREF(w);
    Py_INCREF(*pv);
    return 0; /* okay */
  }
  return 1; /* Nope! */
}



/* the number methods structure for all kjSets, kjDicts, kjGraphs */
static PyNumberMethods kjSet_as_number = {
        (binaryfunc)Wunion,  /*nb_add*/
        (binaryfunc)Wdifference, /*nb_subtract*/
        (binaryfunc)Wcompose, /*nb_multiply*/
        (binaryfunc)undefbin,            /*nb_divide*/
        (binaryfunc)undefbin,            /*nb_remainder*/
        (binaryfunc)undefbin,            /*nb_divmod*/
        (ternaryfunc)undefter,           /*nb_power*/
        (unaryfunc)undefun,             /*nb_negative*/
        (unaryfunc)undefun,             /*nb_positive*/
        (unaryfunc)undefun,             /*nb_absolute*/
        (inquiry)Wrapper_nonzero,  /*nb_nonzero*/
        (unaryfunc)Wtranspose,             /*nb_invert*/
        (binaryfunc)undefbin,            /*nb_lshift*/
        (binaryfunc)undefbin,            /*nb_rshift*/
        (binaryfunc)Wintersect,            /*nb_and*/
        (binaryfunc)undefbin,            /*nb_xor*/
        (binaryfunc)Wunion,            /*nb_or*/
        (coercion)Wrapper_coerce,              /*nb_coerce*/
        (unaryfunc)undefun,             /*nb_int*/
        (unaryfunc)undefun,             /*nb_long*/
        (unaryfunc)undefun,             /*nb_float*/
        (unaryfunc)undefun,             /*nb_oct*/
        (unaryfunc)undefun,             /*nb_hex*/
};

static PyObject * kjSet_subscript(TableWrapper *Set, PyObject *key)
{
  PyObject *mem, *map;
  long test;
  Dprint(("kjSet_subscript\n"));
  test = TableGet1(&(Set->rep), key, 0, NOHASH, NOFORCE, &mem, &map);
  if (test == -1) { return NULL; } 
  return PyInt_FromLong((long) 1); 
}

static long kjSet_ass_subscript(PyObject *Set, PyObject *key, PyObject *thing)
{
  PyObject *mem, *map;
  TableWrapper *S;
  Dprint(("kjSet_ass_subscript\n"));
  S = (TableWrapper *) Set;
  if (S->hashvalue != NOHASH) {
    Wset_hash_error();
    return -1;
  }
  if (thing == NULL) {
    /* request to delete */
    if (deleteFromTable(&(S->rep), key, 0) == 0) { return -1; }
    return 0;
  } else {
    /* should check for standard value of *thing = long 1 ? */
    return TableGet1(&(S->rep), key, 0, NOHASH, FORCE, &mem, &map);
  }
}

static PyObject * kjDict_subscript(TableWrapper *Set, PyObject *key)
{
  PyObject *mem, *map;
  long test;
  Dprint(("kjDict_subscript\n"));
  test = TableGet1(&(Set->rep), key, 0, NOHASH, NOFORCE, &mem, &map);
  if (test == -1) { return NULL; } 
  Py_XINCREF(map);
  return map;
}

static long kjDict_ass_subscript(PyObject *Set, PyObject *key, PyObject *thing)
{
  PyObject *mem, *map;
  TableWrapper *S;
  Dprint(("kjDict_ass_subscript\n"));
  S = (TableWrapper *) Set;
  if (S->hashvalue != NOHASH) {
    Wset_hash_error();
    return -1;
  }
  if (thing == NULL) {
    /* request to delete */
    if (deleteFromTable(&(S->rep), key, 0) == 0) { return -1; }
    return 0;
  } else {
    return TableGet1(&(S->rep), key, thing, NOHASH, FORCE, &mem, &map);
  }
}

static long Wrapper_length(TableWrapper *W)
{
  Dprint(("Wrapper_length\n"));
  return W->rep.entries;
}

/* mapping methods for jkSets */
static PyMappingMethods kjSet_as_mapping = {
        (inquiry)Wrapper_length, /*mp_length*/
        (binaryfunc)kjSet_subscript, /*mp_subscript*/
        (objobjargproc)kjSet_ass_subscript, /*mp_ass_subscript*/
};


/* mapping methods for kjDicts AND kjGraphs */
static PyMappingMethods kjDict_as_mapping = {
        (inquiry)Wrapper_length, /*mp_length*/
        (binaryfunc)kjDict_subscript, /*mp_subscript*/
        (objobjargproc)kjDict_ass_subscript, /*mp_ass_subscript*/
};

/* THE TYPE OBJECT FOR SETS */
static PyTypeObject kjSettype = {
        PyObject_HEAD_INIT(NULL)
        0,
        (char *) "kjSet",               /*tp_name for printing */
        (unsigned int) sizeof(TableWrapper),   /*tp_basicsize */
        (unsigned int)NULL,                       /*tp_itemsize */
        (destructor)WrapperDeallocate,             /*tp_dealloc*/
        (printfunc)WrapperPrint,                   /*tp_print*/
        (getattrfunc)Wrapper_getattr,                        /*tp_getattr*/
        (setattrfunc)NULL,                        /*tp_setattr*/
        (cmpfunc)Wcompare,               /*tp_compare*/
        (reprfunc)WrapperRepr,                  /*tp_repr*/
        (PyNumberMethods *)&kjSet_as_number,    /*tp_as_number*/
        (PySequenceMethods *)NULL,                 /*tp_as_sequence*/
        (PyMappingMethods *)&kjSet_as_mapping,  /*tp_as_mapping*/
        (hashfunc)Wrapper_hash,                 /*tp_hash*/
        NULL,                         /*tp_call*/
};

/* THE TYPE OBJECT FOR DICTS */
static PyTypeObject kjDicttype = {
        PyObject_HEAD_INIT(NULL)
        0,
        (char *) "kjDict",               /*tp_name for printing */
        (unsigned int) sizeof(TableWrapper),   /*tp_basicsize */
        (unsigned int)0,                       /*tp_itemsize */
        (destructor)WrapperDeallocate,             /*tp_dealloc*/
        (printfunc)WrapperPrint,                   /*tp_print*/
        (getattrfunc)Wrapper_getattr,                        /*tp_getattr*/
        (setattrfunc)0,                        /*tp_setattr*/
        (cmpfunc)Wcompare,               /*tp_compare*/
        (reprfunc)WrapperRepr,                  /*tp_repr*/
        (PyNumberMethods *)&kjSet_as_number,    /*tp_as_number*/
        (PySequenceMethods *)0,                 /*tp_as_sequence*/
        (PyMappingMethods *)&kjDict_as_mapping,  /*tp_as_mapping*/
        (hashfunc)Wrapper_hash,                 /*tp_hash*/
        0,                         /*tp_call*/
};

/* THE TYPE OBJECT FOR GRAPHSS */
static PyTypeObject kjGraphtype = {
        PyObject_HEAD_INIT(NULL)
        0,
        (char *) "kjGraph",               /*tp_name for printing */
        (unsigned int) sizeof(TableWrapper),   /*tp_basicsize */
        (unsigned int)0,                       /*tp_itemsize */
        (destructor)WrapperDeallocate,             /*tp_dealloc*/
        (printfunc)WrapperPrint,                   /*tp_print*/
        (getattrfunc)Wrapper_getattr,                        /*tp_getattr*/
        (setattrfunc)0,                        /*tp_setattr*/
        (cmpfunc)Wcompare,               /*tp_compare*/
        (reprfunc)WrapperRepr,                  /*tp_repr*/
        (PyNumberMethods *)&kjSet_as_number,    /*tp_as_number*/
        (PySequenceMethods *)0,                 /*tp_as_sequence*/
        (PyMappingMethods *)&kjDict_as_mapping,  /*tp_as_mapping*/
        (hashfunc)Wrapper_hash,                 /*tp_hash*/
        0,                         /*tp_call*/
};

/* special method for adding to a "dumped index"
   C implementation of frequently used python code (by me)
   same as:

    def kjKeyPut(dict, dumper, index, psuedokey, nullbag):
        try:
            d = dict.dump(dumper)
            if d == Py_None: d = (Py_None,)
            pair = (psuedokey, dict)
            index[d] = pair
            return d
        except PyExc_KeyError:
            nullbag[psuedokey] = dict
            return Py_None

   but faster. 
   Returns Py_None only on failure to index.
   Maps dump of Py_None to (Py_None,) to avoid ambiguity
   (may cause too many hits for retrieval on (Py_None,).)
   dict is kjDict or kjGraph
   dumper is tuple
   index is kjDict or kjGraph
   psuedokey is any hashable object (probably integer)
   nullbag is kjDict or kjGraph
*/
/* #ifndef PYTHON1DOT2 */
static PyObject * kjKeyPut(PyObject *self, PyObject *args)
{
  long valid;
  TableWrapper *dict, *index, *nullbag;
  PyObject *dumper, *psuedokey, *d, *pair, *err_type /*,  *err_value */;
  /* get and verify args */
  if (args == NULL) {
    PyErr_SetString(PyExc_TypeError, "KeyPut requires 5 arguments");
    return NULL;
  }
  if (!PyArg_Parse(args, "(OOOOO)",
	       &dict, &dumper, &index, &psuedokey, &nullbag)) {
    PyErr_SetString(PyExc_TypeError,
	       "KeyPut requires dict, dumper, index, psuedokey, nullbag");
    return NULL;
  }
  if (!((is_kjDictobject(dict)) || (is_kjGraphobject(dict)))) {
    PyErr_SetString(PyExc_TypeError,
	       "first arg of KeyPut must be kjDict or kjGraph");
    return NULL;
  }
  if (!((is_kjDictobject(index)) || (is_kjGraphobject(index)))) {
    PyErr_SetString(PyExc_TypeError,
	       "third arg of KeyPut must be kjDict or kjGraph");
    return NULL;
  }
  if (!((is_kjDictobject(nullbag)) || (is_kjGraphobject(nullbag)))) {
    PyErr_SetString(PyExc_TypeError,
	       "fifth arg of KeyPut must be kjDict or kjGraph");
    return NULL;
  }
  if (!PyTuple_Check(dumper)) {
    PyErr_SetString(PyExc_TypeError,
	       "second arg of KeyPut must be tuple");
    return NULL;
  }
  /* initialize d */
  d = kjDictDump(dict, dumper);
  if (d == NULL) {
    /* unable to dump */
    /* check that error was a keyerror ??? */
    /* err_get(&err_type, &err_value); */
    err_type = PyErr_Occurred();
    if (err_type != PyExc_KeyError) {
      /* some other error... abort */
      /* PyErr_SetObject(err_type, err_value); */
      return NULL;
    }
    /* in case of PyExc_KeyError, augment the Nullbag, return Py_None */
    PyErr_Clear();
    valid = kjDict_ass_subscript((PyObject *) nullbag, 
                                   psuedokey, (PyObject *) dict);
    if (valid == -1) {
      return NULL;
    }
    Py_INCREF(Py_None);
    return Py_None;
  }
  /* if dump succeeded... */
  /* initialize pair, Py_INCREF components */
  pair = PyTuple_New(2);
  if (pair == NULL) { return NULL; }
  PyTuple_SetItem(pair, 0, psuedokey);
  Py_INCREF(psuedokey);
  PyTuple_SetItem(pair, 1, (PyObject *) dict);
  Py_INCREF(dict);
  /* remap Py_None to (Py_None,) if needed */
  if (d == Py_None) {
    /* preserve extra reference to Py_None... */
    d = PyTuple_New(1);
    PyTuple_SetItem(d, 0, Py_None);
  }
  /* set index[d] = pair, creates an extra ref to pair */
  valid = kjDict_ass_subscript((PyObject *) index, d, pair);
  if (valid == -1) {
    Py_DECREF(pair);
    return NULL;
  }
  Py_DECREF(pair); /* dispose of extra ref to pair */
  return d;
}
/* #endif */

/* THE "METHODS" FOR THIS MODULE */
/* These are the basic external interfaces for python to
   access this module. */
static struct PyMethodDef kjbuckets_methods[] = {
  {"kjSet",     (PyCFunction)makekjSet},
  {"kjDict",    (PyCFunction)makekjDict},
  {"kjGraph",    (PyCFunction)makekjGraph},
  {"kjUndump",  (PyCFunction)kjUndumpToDict},
/* #ifndef PYTHON1DOT2 */
  {"kjKeyPut",  (PyCFunction)kjKeyPut},
/* #endif */
#ifdef KJBDEBUG
  {"debug",      (PyCFunction)Wdebug},
#endif
  {NULL, NULL}            /* sentinel */
};

void
initkjbuckets(void)
{
  kjSettype.ob_type = &PyType_Type;
  kjDicttype.ob_type = &PyType_Type;
  kjGraphtype.ob_type = &PyType_Type;

  Py_InitModule("kjbuckets", kjbuckets_methods);
}

/* end of kjbuckets module */
