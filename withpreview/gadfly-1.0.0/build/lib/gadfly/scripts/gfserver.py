"""gadfly server mode

   script usage

    python gfserve.py port database directory password [startup]

   test example

    python gfserve.py 2222 test dbtest admin gfstest

   port is the port to listen to
   database is the database to start up. (must exist!)
   directory is the directory the database is in.
   password is the administrative access password.

   startup if present should be the name of a module to use
   for startup.  The Startup module must contain a function

    Dict = startup(admin_policy, connection, Server_instance)

   which performs any startup actions on the database needed
   and returns either None or a Dictionary of

       name > policy objects

   where the policy objects describe policies beyond the
   admin policy.  The startup function may also
   modify the admin_policy (disabling queries for example).

   The arguments passed to startup are:
       admin_policy: the administrative policy
          eg you could turn queries off for admin, using admin
          only for server maintenance, or you could add prepared
          queries to the admin_policy.
       connection: the database connection
          eg you could perform some inserts before server start
          also needed to make policies.
       Server_instance
          Included for additional customization.

   Create policies using
       P = gfserve.Policy(name, password, connection, queries=0)
         -- for a "secure" policy with only prepared queries allowed,
   or
       P = gfserve.Policy(name, password, connection, queries=1)
         -- for a policy with full access arbitrary statement
            execution.

   add a "named prepared statement" to a policy using
       P[name] = statement
   for example
       P["updatenorm"] = '''
          update frequents
          set bar=?, perweek=?
          where drinker='norm'
        '''
   in this case 'updatenorm' requires 2 dynamic parameters when
   invoked from a client.

   Script stdout lists server logging information.

   Some server administration services (eg shutdown)
   are implemented by the script interpretion of gfclient.py.
"""

# $Id: gfserver.py,v 1.1 2002/05/11 13:28:35 richard Exp $

import sys

def main():
    """start up the server."""
    try:
        done = 0
        argv = sys.argv
        nargs = len(argv)
        #print nargs, argv
        if nargs<5:
            sys.stderr.write("gfserve: not enough arguments: %s\n\n" % argv)
            sys.stderr.write(__doc__)
            return
        [port, db, dr, pw] = argv[1:5]
        print "gfserve startup port=%s db=%s, dr=%s password omitted" % (
           port, db, dr)
        port = int(port)
        startup = None
        if nargs>5:
            startup = argv[5]
            print "gfserve: load startup module %s" % startup
        S = Server(int(port), db, dr, pw, startup)
        S.init()
        print "gfserve: server initialized, setting stderr=stdout"
        sys.stderr = sys.stdout
        print "gfserve: starting the server"
        S.start()
        done = 1
    finally:
        if not done:
            print __doc__

if __name__=="__main__":
    main()

#
# $Log: gfserver.py,v $
# Revision 1.1  2002/05/11 13:28:35  richard
# Checked over the server code. Split out functionality into modules and
# scripts. Renamed documentation to "network". Made sure the gftest suite
# worked (will need to formalise it though).
#
#
