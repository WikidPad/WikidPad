"""
This is a Windows (32 bit) specific file for handling some operations not provided
by the OS-independent wxPython library.
"""

import ctypes, traceback
from ctypes import c_int, c_uint, c_long, c_ulong, c_ushort

# from   wxPython.wx import 

from wxHelper import getTextFromClipboard

from StringOps import unescapeWithRe

import DocPages


_user32dll = ctypes.windll.User32


GWL_WNDPROC = -4
WM_CHANGECBCHAIN = 781
WM_DRAWCLIPBOARD = 776
WM_DESTROY = 2



SetClipboardViewer = _user32dll.SetClipboardViewer
# HWND SetClipboardViewer(
# 
#     HWND hWndNewViewer 	// handle of clipboard viewer window  
#    );


ChangeClipboardChain = _user32dll.ChangeClipboardChain
# BOOL ChangeClipboardChain(
# 
#     HWND hWndRemove,	// handle to window to remove  
#     HWND hWndNewNext 	// handle to next window 
#    );


SendMessage = _user32dll.SendMessageA
# SendMessage(
# 
#     HWND hWnd,	// handle of destination window
#     UINT Msg,	// message to send
#     WPARAM wParam,	// first message parameter
#     LPARAM lParam 	// second message parameter
#    );


# TODO: Maybe use wide variants on NT-based OS?

SetWindowLong = _user32dll.SetWindowLongA
# LONG SetWindowLong(
# 
#     HWND hWnd,	// handle of window
#     int nIndex,	// offset of value to set
#     LONG dwNewLong 	// new value
#    );
#  Returns previous value of the entry


CallWindowProc = _user32dll.CallWindowProcA
# LRESULT CallWindowProc(
# 
#     WNDPROC lpPrevWndFunc,	// pointer to previous procedure
#     HWND hWnd,	// handle to window
#     UINT Msg,	// message
#     WPARAM wParam,	// first message parameter
#     LPARAM lParam 	// second message parameter
#    );


WindowProcType = ctypes.WINFUNCTYPE(ctypes.c_uint, ctypes.c_int, ctypes.c_uint,
        ctypes.c_uint, ctypes.c_ulong)
# LRESULT CALLBACK WindowProc(
# 
#     HWND hwnd,	// handle of window
#     UINT uMsg,	// message identifier
#     WPARAM wParam,	// first message parameter
#     LPARAM lParam 	// second message parameter
#    );
   

class BaseWinProcIntercept:
    """
    Generic base class for intercepting the WinProc of a window
    """
    def __init__(self):
        self.oldWinProc = None
        self.ctWinProcStub = None
        self.hWnd = None

    def start(self, hWnd):
        if self.hWnd is not None:
            raise RuntimeError("Trying to start WinProcIntercept twice")

        self.hWnd = hWnd

        # The stub must be saved because ctypes doesn't hold an own reference
        # to it.
        self.ctWinProcStub = WindowProcType(self.winProc)
        self.oldWndProc = SetWindowLong(c_int(self.hWnd), c_int(GWL_WNDPROC),
                self.ctWinProcStub)

    def stop(self):
        if self.hWnd is None:
            raise RuntimeError("Trying to stop WinProcIntercept twice")
            
        SetWindowLong(c_int(self.hWnd), c_int(GWL_WNDPROC),
                c_int(self.oldWndProc))

        self.oldWinProc = None
        self.ctWinProcStub = None
        self.hWnd = None


    def isActive(self):
        return self.hWnd is not None
        

    def winProc(self, hWnd, uMsg, wParam, lParam):
        """
        This base class reacts only on a WM_DESTROY message and
        stops interception. All messages are send to the original WinProc
        """
        if uMsg == WM_DESTROY and hWnd == self.hWnd:
            self.stop()
            
        return CallWindowProc(c_int(self.oldWndProc), c_int(hWnd), c_uint(uMsg),
                c_uint(wParam), c_ulong(lParam))


class TestWinProcIntercept(BaseWinProcIntercept):
    """
    Just for debugging/testing
    """
    def winProc(self, hWnd, uMsg, wParam, lParam):
        print "Intercept1", repr((uMsg, wParam, lParam))
        
        return BaseWinProcIntercept.winProc(self, hWnd, uMsg, wParam, lParam)
        

class BaseClipboardCatcher(BaseWinProcIntercept):
    def __init__(self):
        BaseWinProcIntercept.__init__(self)
        self.nextWnd = None
        self.firstCCMessage = False


    def start(self, hWnd):
        BaseWinProcIntercept.start(self, hWnd)

        # SetClipboardViewer sends automatically an initial clipboard changed (CC)
        # message which should be ignored
        self.firstCCMessage = True
        self.nextWnd = SetClipboardViewer(c_int(self.hWnd))


    def stop(self):
        if self.nextWnd is None:
            raise RuntimeError("Trying to stop ClipboardCatcher twice")

        ChangeClipboardChain(c_int(self.hWnd), c_int(self.nextWnd))
        
        self.nextWnd = None

        BaseWinProcIntercept.stop(self)
        
    
    def winProc(self, hWnd, uMsg, wParam, lParam):
        if uMsg == WM_CHANGECBCHAIN:
            if self.nextWnd == wParam:
                # repair the chain
                self.nextWnd = lParam
    
            if self.nextWnd:  # Neither None nor 0
                # pass the message to the next window in chain
                SendMessage(c_int(self.nextWnd), c_int(uMsg), c_uint(wParam),
                        c_ulong(lParam))
        elif uMsg == WM_DRAWCLIPBOARD:
            if self.firstCCMessage:
                self.firstCCMessage = False
            else:
                self.handleClipboardChange()

            if self.nextWnd:  # Neither None nor 0
                # pass the message to the next window in chain
                SendMessage(c_int(self.nextWnd), c_int(uMsg), c_uint(wParam),
                        c_ulong(lParam))

        return BaseWinProcIntercept.winProc(self, hWnd, uMsg, wParam, lParam)


    def handleClipboardChange(self):
        print "Clipboard changed"


class ClipboardCatcher(BaseClipboardCatcher):
    """
    Specialized WikidPad clipboard catcher
    """
    
    MODE_OFF = 0
    MODE_AT_PAGE = 1
    MODE_AT_CURSOR = 2
    
    def __init__(self, mainControl):
        BaseClipboardCatcher.__init__(self)
        
        self.mainControl = mainControl
        self.wikiPage = None
        self.mode = ClipboardCatcher.MODE_OFF
        
    def startAtPage(self, hWnd, wikiPage):
        """
        wikiPage -- page to write clipboard content to
        """
        if not isinstance(wikiPage,
                (DocPages.WikiPage, DocPages.AliasWikiPage)):
            self.mainControl.displayErrorMessage(
                    u"Only a real wiki page can be a clipboard catcher")
            return
            
        if self.mode != ClipboardCatcher.MODE_OFF:
            self.stop()

        BaseClipboardCatcher.start(self, hWnd)
        self.wikiPage = wikiPage
        self.mode = ClipboardCatcher.MODE_AT_PAGE

    def startAtCursor(self, hWnd):
        """
        Write clipboard content to cursor position
        """
        if self.mode != ClipboardCatcher.MODE_OFF:
            self.stop()

        BaseClipboardCatcher.start(self, hWnd)
        self.mode = ClipboardCatcher.MODE_AT_CURSOR


    def stop(self):
        BaseClipboardCatcher.stop(self)
        self.wikiPage = None
        self.mode = ClipboardCatcher.MODE_OFF

    def getMode(self):
        return self.mode


    def handleClipboardChange(self):
        text = getTextFromClipboard()
        if len(text) == 0:
            return

        try:
            suffix = unescapeWithRe(self.mainControl.getConfig().get(
                    "main", "clipboardCatcher_suffix", r"\n"))
        except:
            traceback.print_exc()
            suffix = u"\n"   # TODO Error message?

        if self.mode == ClipboardCatcher.MODE_OFF:
            return
        elif self.mode == ClipboardCatcher.MODE_AT_PAGE:
            if self.wikiPage is None:
                return
            self.wikiPage.appendLiveText(text + suffix)
            
        elif self.mode == ClipboardCatcher.MODE_AT_CURSOR:
            self.mainControl.getActiveEditor().ReplaceSelection(text + suffix)


    def getWikiWord(self):
        if self.wikiPage is None:
            return None
        else:
            return self.wikiPage.getWikiWord()


