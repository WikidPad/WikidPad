""" Socket interactions for gadfly client and server

:Author: Aaron Watters
:Maintainers: http://gadfly.sf.net/
:Copyright: Aaron Robert Watters, 1994
:Id: $Id: gfsocket.py,v 1.4 2002/05/11 13:28:35 richard Exp $:
"""

import sys, select, time, marshal, md5

# responses

SUCCESS = "SUCCESS"
EXCEPTION = "EXCEPTION"

def reply_exception(exception, info, socket):
    """send an exception back to the client"""
    # any error is invisible to client
    #from gfserve import ServerError
    try:
        reply( (EXCEPTION, (exception, info)), socket)
    except:
        #info = "%s %s" % (sys.exc_type, sys.exc_value)
        socket.close()
        #raise ServerError, "reply_exception failed: "+`info`

def reply_success(data, socket):
    """report success with data back to client"""
    reply( (SUCCESS, data), socket)

def reply(data, socket):
    marshaldata = marshal.dumps(data)
    send_packet(socket, marshaldata)
    socket.close()

def send_packet(socket, data):
    """blast out a length marked packet"""
    send_len(data, socket)
    socket.send(data)

def send_len(data, socket):
    """send length of data as cr terminated int rep"""
    info = `len(data)`+"\n"
    socket.send(info)

def send_certified_action(actor_name, action, arguments, password, socket):
    marshaldata = marshal.dumps( (action, arguments) )
    cert = certificate(marshaldata, password)
    #print actor_name, cert,  marshaldata
    marshaldata = marshal.dumps( (actor_name, cert, marshaldata) )
    send_packet(socket, marshaldata)

def unpack_certified_data(data):
    # sanity check
    unpack = (actor_name, certificate, marshaldata) = marshal.loads(data)
    return unpack

def recv_data(socket, timeout=10):
    """receive data or time out"""
    endtime = time.time() + timeout
    reader = Packet_Reader(socket)
    done = 0
    while not done:
        timeout = endtime - time.time()
        if timeout<0:
            raise IOError, "socket time out (1)"
        (readable, dummy, error) = select.select([socket], [], [socket], timeout)
        if error:
            raise IOError, "socket in error state"
        if not readable:
            raise IOError, "socket time out (2)"
        reader.poll()
        done = (reader.mode==READY)
    return reader.data

def interpret_response(data):
    """interpret response data, raise exception if needed"""
    (indicator, data) = marshal.loads(data)
    if indicator==SUCCESS:
        return data
    elif indicator==EXCEPTION:
        # ???
        raise EXCEPTION, data
    else:
        raise ValueError, "unknown indicator: "+`indicator`

# packet reader modes
LEN = "LEN"
DATA = "DATA"
READY = "READY"
ERROR = "ERROR"

BLOCK_SIZE = 4028

LEN_LIMIT = BLOCK_SIZE * 10

class Packet_Reader:
    """nonblocking pseudo-packet reader."""

    # packets come in as decimal_len\ndata
    # (note: cr! not crlf)

    # kick too large requests if set
    limit_len = LEN_LIMIT

    def __init__(self, socket):
        self.socket = socket
        self.length = None
        self.length_remaining = None
        self.len_list = []
        self.data_list = []
        self.received = ""
        self.data = None
        self.mode = LEN

    def __len__(self):
        if self.mode is LEN:
            raise ValueError, "still reading length"
        return self.length

    def get_data(self):
        if self.mode is not READY:
            raise ValueError, "still reading"
        return self.data

    def poll(self):
        mode = self.mode
        if mode is READY:
            raise ValueError, "data is ready"
        if mode is ERROR:
            raise ValueError, "socket error previously detected"
        socket = self.socket
        (readable, dummy, error) = select.select([socket], [], [socket], 0)
        if error:
            self.socket.close()
            self.mode = ERROR
            raise ValueError, "socket is in error state"
        if readable:
            if mode is LEN:
                self.read_len()
            # note: do not fall thru automatically
            elif mode is DATA:
                self.read_data()

    def read_len(self):
        """assume socket is readable now, read length"""
        socket = self.socket
        received = self.received
        len_list = self.len_list
        if not received:
            # 10 bytes at a time until len is read.
            received = socket.recv(10)
        while received:
            # consume, test one char
            input = received[0]
            received = received[1:]
            if input == "\n":
                # done reading length
                try:
                    length = self.length = int(''.join(len_list))
                except:
                    self.mode = ERROR
                    socket.close()
                    raise ValueError, "bad len string? "+`len_list`
                self.received = received
                self.length_remaining = length
                self.mode = DATA
                limit_len = self.limit_len
                if limit_len and length>limit_len:
                    raise ValueError, "Length too big: "+`(length, limit_len)`
                return
            if len(len_list)>10:
                self.mode = ERROR
                socket.close()
                raise ValueError, "len_list too long: "+`len_list`
            len_list.append(input)
            if not received:
                (readable, dummy, error) = select.select(\
                   [socket], [], [socket], 0)
                if error:
                    self.mode = ERROR
                    socket.close()
                    raise ValueError, "socket in error state"
                if readable:
                    received = socket.recv(10)
        # remember extra data received.
        self.received = received

    def read_data(self):
        # assume socket is readable
        socket = self.socket
        received = self.received
        length_remaining = self.length_remaining
        data_list = self.data_list
        if received:
            data_list.append(received)
            self.received = ""
            length_remaining = length_remaining - len(received)
        recv_len = max(length_remaining, BLOCK_SIZE)
        received = socket.recv(recv_len)
        if received:
            data_list.append(received)
            length_remaining = length_remaining - len(received)
        if length_remaining<1:
            self.mode = READY
            self.data = ''.join(data_list)
        self.length_remaining = length_remaining

def certificate(String, password):
    """generate a certificate for a string, using a password"""
    if not String:
        raise ValueError, "cannot generate certificate for empty string"
    taggedstring = password + String
    return md5.new(taggedstring).digest()

def certify(String, cert, password):
    """check a certificate for a string"""
    return certificate(String, password) == cert

#
# $Log: gfsocket.py,v $
# Revision 1.4  2002/05/11 13:28:35  richard
# Checked over the server code. Split out functionality into modules and
# scripts. Renamed documentation to "network". Made sure the gftest suite
# worked (will need to formalise it though).
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
