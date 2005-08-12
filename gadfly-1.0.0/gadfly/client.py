import socket

from gadfly import gfsocket

# copied from gfserve
# shut down the server (admin policy only)
#   arguments = ()
#   shutdown the server with no checkpoint
SHUTDOWN = "SHUTDOWN"

# restart the server (admin only)
#   arguments = ()
#   restart the server (recover)
#   no checkpoint
RESTART = "RESTART"

# checkpoint the server (admin only)
#   arguments = ()
#   checkpoint the server
CHECKPOINT = "CHECKPOINT"

# exec prepared statement
#   arguments = (prepared_name_string, dyn=None)
#   execute the prepared statement with dynamic args.
#   autocommit.
EXECUTE_PREPARED = "EXECUTE_PREPARED"

# exec any statement (only if not disabled)
#   arguments = (statement_string, dyn=None)
#   execute the statement with dynamic args.
#   autocommit.
EXECUTE_STATEMENT = "EXECUTE_STATEMENT"

class gfclient:

    closed = 0

    def __init__(self, policy, password, machine, port):
        self.policy = policy
        self.port = int(port)
        self.password = password
        self.machine = machine

    def open_connection(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((self.machine, self.port))
        return sock

    def send_action(self, action, arguments, socket):
        gfsocket.send_certified_action(
          self.policy, action, arguments, self.password, socket)

    def checkpoint(self):
        return self.simple_action(CHECKPOINT)

    def simple_action(self, action, args=()):
        """only valid for admin policy: force a server checkpoint"""
        sock = self.open_connection()
        self.send_action(action, args, sock)
        data = gfsocket.recv_data(sock)
        data = gfsocket.interpret_response(data)
        return data

    def restart(self):
        """only valid for admin policy: force a server restart"""
        return self.simple_action(RESTART)

    def shutdown(self):
        """only valid for admin policy: shut down the server"""
        return self.simple_action(SHUTDOWN)

    def close(self):
        self.closed = 1

    def commit(self):
        # right now all actions autocommit
        pass

    # cannot rollback, autocommit on success
    rollback = commit

    def cursor(self):
        """return a cursor to this policy"""
        if self.closed:
            raise ValueError, "connection is closed"
        return gfClientCursor(self)


class gfClientCursor:

    statement = None
    results = None
    description = None

    def __init__(self, connection):
        self.connection = connection

    # should add fetchone fetchmany
    def fetchall(self):
        return self.results

    def execute(self, statement=None, params=None):
        con = self.connection
        data = con.simple_action(EXECUTE_STATEMENT, (statement, params))
        (self.description, self.results) = data

    def execute_prepared(self, name, params=None):
        con = self.connection
        data = con.simple_action(EXECUTE_PREPARED, (name, params))
        if data is None:
            self.description = self.results = None
        else:
            (self.description, self.results) = data

    def setoutputsizes(self, *args):
        pass # not implemented

    def setinputsizes(self):
        pass # not implemented

