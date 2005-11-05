''' essentially, specialized pickle for this app:

:Author: Aaron Watters
:Maintainers: http://gadfly.sf.net/
:Copyright: Aaron Robert Watters, 1994
:Id: $Id: serialize.py,v 1.4 2002/05/11 02:59:05 richard Exp $:
'''

# TODO need to fix serialization/deserialization of btand and btor
import types

def serialize(ob):
    """ Simple protocol for generating a marshallable ob

        TODO: I'm worried that tuples are special cases here...
    """
    if not isinstance(ob, types.InstanceType):
        # base type
        return ob

    args1 = ob.initargs()
    args1 = tuple(map(serialize, args1))
    args2 = ob.marshaldata()
    return (ob.__class__.__name__, (args1, args2))

def deserialize(description):
    """ Dual of serialize
    """
    # base type
    if not isinstance(description, types.TupleType) or len(description) != 2:
        return description

    # pull out the class name and marshal data
    (name, desc) = description

    # TODO: these doesn't actually appear to be possible
    if name == "tuple":
        # tuple case
        return desc
    if name == "list":
        # list case: map deserialize across desc
        return map(deserialize, desc)

    # all other cases are classes of semantics
    import semantics
    klass = getattr(semantics, name)
    (args1, args2) = desc
    args1 = tuple(map(deserialize, args1))
    ob = apply(klass, args1)
    ob.demarshal(args2)
    return ob

# invariant:
#   deserialize(serialize(ob)) returns semantic copy of ob
#   serialize(ob) is marshallable
# ie,
#   args1 = ob.initargs() # init args
#   args1d = map(serialize, args1) # serialized
#   args2 = ob.marshaldata() # marshalable addl info
#   # assert args1d, args2 are marshallable
#   args1copy = map(deserialize, args1)
#   ob2 = ob.__class__(args1copy)
#   ob2 = ob2.demarshal(args2)
#   # assert ob2 is semantic copy of ob


#
# $Log: serialize.py,v $
# Revision 1.4  2002/05/11 02:59:05  richard
# Added info into module docstrings.
# Fixed docco of kwParsing to reflect new grammar "marshalling".
# Fixed bug in gadfly.open - most likely introduced during sql loading
# re-work (though looking back at the diff from back then, I can't see how it
# wasn't different before, but it musta been ;)
# A buncha new unit test stuff.
#
#
