""" View based introspection and extension views

:Author: Aaron Watters
:Maintainers: http://gadfly.sf.net/
:Copyright: Aaron Robert Watters, 1994
:Id: $Id: introspection.py,v 1.1 2006/01/07 15:01:24 Michael Butscher Exp $:
"""

# $Id: introspection.py,v 1.1 2006/01/07 15:01:24 Michael Butscher Exp $

import store

class RemoteView(store.View):

    """Virtual superclass.  See text for methods and members to define."""

    # Usually redefine __init__
    def __init__(self):
        pass

    # set static (static=1) or dynamic (static=0)
    # for static tuple seq is generated once per load
    # for non-static tuple seq is regenerated once per query
    #  which uses the view.
    static = 0

    # define the column_names
    column_names = ['Column1']

    # define the row generator
    def listing(self):
        """return list of values (1 column)
           or list of tuples of values (>1 column).
           size of elts should match number of columns."""
        return [0]

    # possibly redefine __repr__ and irepr
    def __repr__(self):
        return "<Remote View %s at %s>" % (self.__class__, id(self))

    irepr = __repr__

    # for introspective methods possibly redefine relbind
    def relbind(self, db, atts):
        return self

    ### don't touch the following unless you are a guru!
    cached_rows = None

    def uncache(self):
        if self.static: return
        self.cached_rows = None

    def attributes(self):
        from string import upper
        return map(upper, self.column_names)

    def rows(self, andseqs=0):
        cached_rows = self.cached_rows
        if cached_rows is None:
            tups = list(self.listing())
            from semantics import kjbuckets
            undump = kjbuckets.kjUndump
            attributes = tuple(self.attributes())
            for i in xrange(len(tups)):
                tups[i] = undump(attributes, tups[i])
            cached_rows = self.cached_rows = tups
        tups = cached_rows[:]
        if andseqs:
            return (tups, range(len(tups)))
        else:
            return tups

class DualView(RemoteView):
    """static one row one column view for testing.
       (Inspired by Oracle DUAL relation)."""
    # trivial example extension view

    static = 1

    column_names = ['Column1']

    def listing(self):
        return [0]

class DictKeyValueView(RemoteView):
    """Less trivial example. Dict keys/values converted to strings"""

    static = 0 # regenerate in case dict changes

    column_names = ["key", "value"]

    mapstring = 1

    def __init__(self, dict=None):
        if dict is None: dict = {}
        self.dict = dict

    def listing(self):
        items = self.dict.items()
        if self.mapstring:
            def mapper(item):
                return tuple(map(str, item))
            return map(mapper, items)
        else:
            return items

class RelationsView(DictKeyValueView):
    """list of relations and whether they are views."""

    column_names = ["table_name", "is_view"]
    mapstring = 0

    def relbind(self, db, atts):
        rels = db.rels
        dict = {}
        for relname in rels.keys():
            dict[relname] = rels[relname].is_view
        self.dict = dict
        return self

class IndicesView(DictKeyValueView):
    """list of indices and relations they index"""

    column_names = ["index_name", "table_name", "is_unique"]

    mapstring = 0

    def relbind(self, db, atts):
        rels = db.rels
        dict = {}
        for relname in rels.keys():
            rel = rels[relname]
            if not rel.is_view:
                index_list = rels[relname].index_list
                for index in index_list:
                    dict[index.name] = (relname, index.unique)
        self.dict = dict
        return self

    def listing(self):
        L = []
        dict = self.dict
        keys = dict.keys()
        for k in keys:
            L.append( (k,) + dict[k] )
        return L

class DataDefsView(DictKeyValueView):
    """Data defs (of non-special views) and definition dumps."""

    column_names = ["name", "defn"]

    mapstring = 1

    def relbind(self, db, atts):
        self.dict = db.datadefs
        return self

class ColumnsView(RemoteView):
    """table_names and columns therein."""

    column_names = ["table_name", "column_name"]

    def relbind(self, db, atts):
        rels = db.rels
        pairs = []
        for relname in rels.keys():
            for att in rels[relname].attributes():
                pairs.append( (relname, att) )
        self.pairs = pairs
        return self

    def listing(self):
        return self.pairs

class IndexAttsView(ColumnsView):
    """indices and attributes."""

    column_names = ["index_name", "column_name"]

    def relbind(self, db, atts):
        indices = db.indices
        pairs = []
        for iname in indices.keys():
            for att in indices[iname].attributes():
                pairs.append( (iname, att) )
        self.pairs = pairs
        return self

#
# $Log: introspection.py,v $
# Revision 1.1  2006/01/07 15:01:24  Michael Butscher
# First combined version of WikidPad/WikidPadCompact
#
# Revision 1.1  2005/06/05 05:51:23  jhorman
# initial checkin
#
# Revision 1.3  2002/05/11 02:59:04  richard
# Added info into module docstrings.
# Fixed docco of kwParsing to reflect new grammar "marshalling".
# Fixed bug in gadfly.open - most likely introduced during sql loading
# re-work (though looking back at the diff from back then, I can't see how it
# wasn't different before, but it musta been ;)
# A buncha new unit test stuff.
#
# Revision 1.2  2002/05/08 00:49:00  anthonybaxter
# El Grande Grande reindente! Ran reindent.py over the whole thing.
# Gosh, what a lot of checkins. Tests still pass with 2.1 and 2.2.
#
# Revision 1.1.1.1  2002/05/06 07:31:09  richard
#
#
#
