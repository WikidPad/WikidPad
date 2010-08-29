"""
Handles interprocess communication, currently it checks only if
another WikidPad instance is already active, transfers commandline
to it and closes the additional instance then.
"""

import os, sys, string, re, traceback
import threading, socket, SocketServer

import wx

from Serialization import SerializeStream

# TODO How to handle /x (exit) command on commandline?


etEVT_REMOTE_COMMAND = wx.NewEventType()
EVT_REMOTE_COMMAND = wx.PyEventBinder(etEVT_REMOTE_COMMAND, 0)


class RemoteCommandEvent(wx.PyCommandEvent):
    def __init__(self, cmdLine):
        wx.PyCommandEvent.__init__(self, etEVT_REMOTE_COMMAND, -1)
        self.cmdLine = cmdLine

    #def __del__(self):
    #    print '__del__'
    #    wx.PyCommandEvent.__del__(self)

    def getCmdLineAction(self):
        return self.cmdLine



class CommandServer(SocketServer.TCPServer):
    def __init__(self, server_address, RequestHandlerClass):
        SocketServer.TCPServer.__init__(self, server_address,
                RequestHandlerClass)
        
        self.cookie = None
        
        self.appLockPath = None
        self.appLockContent = None

#     def server_bind(self):
# #         self.socket.settimeout(3.0)
#         SocketServer.TCPServer.server_bind(self)
        
    def setAppCookie(self, appCookie):
        self.appCookie = appCookie
        
    def getAppCookie(self):
        return self.appCookie

    def setAppLockInfo(self, appLockPath, appLockContent):
        self.appLockPath = appLockPath
        self.appLockContent = appLockContent
    

    def close(self):
        try:
            # Method exists since Python 2.6
            self.shutdown()
        except AttributeError:
            pass
        self.server_close()



class RemoteCmdHandler(SocketServer.StreamRequestHandler):
    def setup(self):
        self.request.settimeout(10.0)
        SocketServer.StreamRequestHandler.setup(self)

    def finish(self):
        SocketServer.StreamRequestHandler.finish(self)
        self.request.close()

    def _readLine(self):
        result = []
        read = 0
        while read < 300:
            c = self.rfile.read(1)
            if c == "\n" or c == "":
                return "".join(result)

            result.append(c)
            read += 1

        return ""

    def handle(self):
        # Send initial greeting
        self.wfile.write("WikidPad_command_server 1.0\n")
        try:
            basecmd = self._readLine()
            if basecmd == "cmdline":
                # a commandline will be transmitted
                cookie = self._readLine()
                if cookie == self.server.getAppCookie():
                    self.wfile.write("+App cookie ok\n")
                    # Authentication passed
                    sst = SerializeStream(fileObj=self.rfile, readMode=True)
                    cmdline = sst.serArrString(())
                    evt = RemoteCommandEvent(cmdline)
                    wx.GetApp().GetTopWindow().AddPendingEvent(evt)
                else:
                    self.wfile.write("-Bad app cookie\n")
        except:
            pass
#             traceback.print_exc()
#         
#         print "handle10"



theServer = None
theServerThread = None


def createCommandServer(appCookie):
    global theServer

    # Search for an unused port
    for port in xrange(2000,3000):   # TODO range option
        try:
            server = CommandServer(("127.0.0.1", port), RemoteCmdHandler)
            server.setAppCookie(appCookie)
            theServer = server
            return port  # Free port found
        except socket.error, e:
            if not (e.args[0] == 10048 or e.args[0] == 98):
                # Not "Address already in use" error, so reraise
                raise

    return -1  # No free port found


def startCommandServer():
    global theServer, theServerThread
    
    theServerThread = threading.Thread(target = theServer.serve_forever)
    theServerThread.setDaemon(True)
    theServerThread.start()


def getCommandServer():
    return theServer


def stopCommandServer():
    global theServer
    
    if theServer is not None:
        theServer.close()




#wxPython demo code ----------------------------------------------------------------------



#----------------------------------------------------------------------

# 
#     evt = MyEvent(myEVT_BUTTON_CLICKPOS, self.GetId())
#     evt.SetMyVal(pt)
#     #print id(evt), sys.getrefcount(evt)
#     self.GetEventHandler().ProcessEvent(evt)
#     #print id(evt), sys.getrefcount(evt)


