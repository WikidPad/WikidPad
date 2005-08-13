#!/usr/local/bin/python
'''
An Interactive Shell for the Gadfly RDBMS (http://gadfly.sf.net/)

Jeff Berliner (jeff@popmail.med.nyu.edu) -- 11/24/1998
    (old URL http://shamrock.med.nyu.edu/~jeff/gfplus/)

gfplus is a simple interactive shell for Gadfly, based losely on
Oracle's SQL*Plus tool.  gfplus allows you to type SQL directly, and
handles allocating resources, and dealing with output.

Thanks to:
     Aaron Watters!
     Richard Jones
     Lars M. Garshol
     Marc Risney
'''

__version__ = '$Revision: 1.1 $'

# $Id: gfplus.py,v 1.1 2005/06/05 05:51:03 jhorman Exp $

import os, sys, string, traceback, time, operator, cmd, re

try:
    import gadfly
except ImportError:
    print 'Unable to load Gadfly. Check your PYTHONPATH and try again.'
    sys.exit()

try:   # if the readline module exists, it will provide command line recall
    import readline    # and other editing features to raw_input().
    rl = '[readline]'
except ImportError:
    rl = ''

## pp() function by Aaron Watters, posted to gadfly-rdbms@egroups.com 1/18/99
# Thanks Aaron!!
def pp(cursor):
    try:
        rows = cursor.fetchall()
    except:
        return "No description"
    desc = cursor.description
    names = []
    maxen = []
    for d in desc:
        n = d[0]
        names.append(n)
        maxen.append(len(n))
    rcols = range(len(desc))
    rrows = range(len(rows))
    for i in rrows:
        rows[i] = rowsi = map(str, rows[i])
        for j in rcols:
            maxen[j] = max(maxen[j], len(rowsi[j]))
    for i in rcols:
        maxcol = maxen[i]
        name = names[i]
        names[i] = name + (" " * (maxcol-len(name)))
        for j in rrows:
            val = rows[j][i]
            rows[j][i] = val + (" " * (maxcol-len(val)))
    for j in rrows:
        rows[j] = ' | '.join(rows[j])
    names = ' | '.join(names)
    width = reduce(operator.add, maxen) + 3*len(desc)
    rows.insert(0, "=" * width)
    rows.insert(0, names)
    return '\n'.join(rows, "\n")

class GadflyShell(cmd.Cmd):
    prompt = 'GF> '
    prompt2 = '... '

    def __init__(self):
        print '\ngfplus %s -- Interactive gadfly shell  %s\n' %(__version__, rl)
        t = time.localtime(time.time())
        print time.strftime("%A %B %d, %Y %I:%M %p", t)
        print 'Using: '

        # flag added for client/server usage.  Will be set to 1 if the
        # arguments passed to gfplus appear to request a server connection
        self.SERVER = 0

        # parse command line
        if os.environ.has_key('GADFLY_HOME'):
            # If environment variable exists, use the data stored in it.
            # Don't prompt.
            loc, dbase = os.path.split(os.environ.get('GADFLY_HOME'))
            print 'DB:',dbase
            print 'Loc:',loc,'\n'
        elif len(sys.argv) < 2:
            # no arguments passed
            dbase = raw_input('DB Name: ')
            loc = raw_input('DB Location: ')
        elif len(sys.argv) < 3:
            # assume db name was passed, ask for location
            dbase = sys.argv[1]
            print 'DB Name: %s' % dbase
            loc = raw_input('DB Location: ')
        elif len(sys.argv) < 4:
            # assume all arguments were passed.
            dbase = sys.argv[1]
            loc = sys.argv[2]
            print 'DB:',dbase
            print 'Loc:',loc,'\n'
        elif len(sys.argv) == 5:
            # assume caller is requesting a client/server conn.
            dbase = sys.argv[1]
            port = sys.argv[2]
            passwd = sys.argv[3]
            machine = sys.argv[4]
            self.SERVER = 1
            print 'Policy:', dbase
            print 'Loc: %s:%s\n' %(machine, port)
        else:   # none of the above
            print 'usage: %s [dbname] [loc]' %sys.argv[0]
            sys.exit()

        if not self.SERVER:
            try:
                self.db = gadfly.gadfly(dbase,loc)
            except IOError, msg:
                print 'Unable to locate database "%s" at location "%s".'%(
                    dbase, loc)
                foo = raw_input('Create? (Yy/Nn) ')
                # if 'y', create a new DB.
                if string.lower(string.strip(foo)) == 'y':
                    self.db = gadfly.gadfly()
                    self.db.startup(dbase,loc)
                else:   # otherwise, non-'y', exit.
                    sys.exit(-1) 
        else:
            from gadfly.gfclient import gfclient
            self.db = gfclient(dbase, passwd, machine, int(port))

        # create a DB cursor to execute our SQL in.
        self.cur = self.db.cursor()

        # for "do something to the last command" commands
        self.last_command = ''

    def do_exit(self, arg):
        ''' exit gfplus, commiting changes
        '''
        print 'Commit...',
        sys.stdout.flush()
        self.db.commit()
        self.db.close()
        print 'exit'
        return 1

    def do_EOF(self, arg):
        print
        return self.do_exit(arg)

    def do_commit(self, arg):
        ''' commit database
        '''
        self.db.commit()

    def do_rollback(self, arg):
        ''' rollback to last commit
        '''
        self.db.rollback()

    def precmd(self, line):
        if line.strip() in ('/', '!!'):
            line = self.lastcmd
        if line.startswith('s/') or line.startswith('c/'):
            line = 'change '+line[2:]
        return line

    def emptyline(self):
        pass

    def postcmd(self, stop, line):
        '''I need to have the last command altered _after_ the current
            command is run
        '''
        self.last_command = self.lastcmd
        return stop

    def do_desc(self, table):
        ''' List columns for table named in table
        '''
        sql = 'select column_name from __columns__ where table_name = ?'
        self.cur.execute(sql, (string.upper(table),))
        if self.SERVER:
            print '\n'+pp(self.cur)+'\n'
        else:
            print '\n'+self.cur.pp()+'\n'

    def do_change(self, arg):
        '''Repeat the last command, but change it according to the re arg:
            s/pattern/replace
            c/pattern/replace
        '''
        if not self.last_command:
            print 'No last command to change'
        # TODO: allow \-escaped / to appear in the arg
        pattern, repl = arg.split('/')
        line = re.sub(pattern, repl, self.last_command)
        print line
        return self.onecmd(line)

    def do_use(self, dbase):
        ''' Switch active databases.
            dbase becomes the new name, and prompts the user for the location.
            Commits changes to original DB.
        '''
        self.db.commit()
        self.db.close()
        loc = raw_input('Loc: ')
        self.db = gadfly.gadfly(dbase, loc)
        self.cur = self.db.cursor()
        self.SERVER = 0
        print '\nNow using %s\n'%dbase

    def do_help(self, arg):
        ''' display help screen
        '''
        print '''
     gfplus -- Interactive Gadfly Shell

            Commands:

            <any sql statement>;        Execute SQL commands on gadfly database
            help                        This screen
            commit                      Commit changes to database
            rollback                    Rollback changes to last committed state
            desc <relation>             Display all columns in a table or view
            use <database>              Switch active database to <database>
            exit                        Exit gfplus, commiting changes
            '''

    def default(self, arg):
        ''' Run the command to Gadfly
        '''
        # make sure we have a whole query
        query = arg.strip()
        while not query.endswith(';'):   
            query = query + ' ' + raw_input(self.prompt2).strip()

        try:
            self.cur.execute(query[:-1])
        except:
            # Gadfly returned an error, use traceback to
            # print it.
            traceback.print_exc()
            return

        # display results
        if query.startswith('select'):
            f = self.cur.fetchall()
            if len(f) > 0:
                if self.SERVER:
                    print pp(self.cur)
                else:
                    print self.cur.pp()
            else:
                print 'No rows returned.'
        else:
            print 'OK'

def main():
    shell = GadflyShell()
    shell.cmdloop()

if __name__ == '__main__':
    main()

#
# $Log: gfplus.py,v $
# Revision 1.1  2005/06/05 05:51:03  jhorman
# initial checkin
#
# Revision 1.6  2002/07/10 07:45:07  richard
# Final commits before 1.0.0 release
#
# Revision 1.5  2002/05/24 01:56:05  richard
# we need a main()
#
# Revision 1.4  2002/05/14 23:52:55  richard
# - fixed commit-after-open bug (no working_db)
# - added more functionality to gfplus:
#   / or !!         repeat last command (blank line does the same thing)
#   (s|c)/pat/repl  repeat last but RE sub pat for repl
# - corrected gfplus exit code
#
# Revision 1.3  2002/05/12 23:56:55  richard
# Cleaned up gfplus (uses cmd.Cmd, buncha other cleanups)
# Removed the redundant gfclient
#
# Revision 1.2  2002/05/12 09:53:13  richard
# Corrected MANIFEST
# Fixed setup to create scripts that call main()
# Fixed gfplus, a lot ;)
#
# Revision 1.1  2002/05/11 23:32:06  richard
# added gfplus, docco
#
#

