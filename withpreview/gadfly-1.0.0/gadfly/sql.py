''' defines the SQL grammar and bahaviour for gadfly

:Author: Aaron Watters
:Maintainers: http://gadfly.sf.net/
:Copyright: Aaron Robert Watters, 1994
:Id: $Id: sql.py,v 1.5 2002/05/11 02:59:05 richard Exp $:
'''

def getSQL():
    from grammar import DeclareTerminals
    from gadfly import kjParser
    infile = 'gadfly.sql_mar'
    try:
        SQLG = kjParser.UnMarshalGram(infile)
    except ImportError:
        raise ImportError, "Couldn't find sql_mar.py - has setup.py been run?"
    DeclareTerminals(SQLG)
    return SQLG

#
# $Log: sql.py,v $
# Revision 1.5  2002/05/11 02:59:05  richard
# Added info into module docstrings.
# Fixed docco of kwParsing to reflect new grammar "marshalling".
# Fixed bug in gadfly.open - most likely introduced during sql loading
# re-work (though looking back at the diff from back then, I can't see how it
# wasn't different before, but it musta been ;)
# A buncha new unit test stuff.
#
# Revision 1.4  2002/05/08 00:49:00  anthonybaxter
# El Grande Grande reindente! Ran reindent.py over the whole thing.
# Gosh, what a lot of checkins. Tests still pass with 2.1 and 2.2.
#
# Revision 1.3  2002/05/07 07:55:34  anthonybaxter
# more helpful message.
#
# Revision 1.2  2002/05/07 07:06:11  richard
# Cleaned up sql grammar compilation some more.
# Split up the BigList into its components too.
#
# Revision 1.1.1.1  2002/05/06 07:31:10  richard
#
#
#
