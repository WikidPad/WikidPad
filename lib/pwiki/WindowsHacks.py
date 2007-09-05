"""
This is a Windows (32 bit) specific file for handling some operations not provided
by the OS-independent wxPython library.
"""

import ctypes, traceback
from ctypes import c_int, c_uint, c_long, c_ulong, c_ushort, c_char, c_char_p, \
        c_wchar_p, c_byte, byref

import wx

from wxHelper import getTextFromClipboard

from StringOps import unescapeWithRe

import DocPages


_user32dll = ctypes.windll.User32
_kernel32dll = ctypes.windll.Kernel32
_shell32dll = ctypes.windll.Shell32

GWL_WNDPROC = -4
WM_CHANGECBCHAIN = 781
WM_CHAR = 258
WM_DRAWCLIPBOARD = 776
WM_DESTROY = 2
WM_INPUTLANGCHANGE = 81
WM_KEYDOWN = 256

LOCALE_IDEFAULTANSICODEPAGE = 0x1004

MB_PRECOMPOSED = 1

SW_SHOW = 5


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


MultiByteToWideChar = _kernel32dll.MultiByteToWideChar
# int MultiByteToWideChar(
# 
#     UINT CodePage,	// code page 
#     DWORD dwFlags,	// character-type options 
#     LPCSTR lpMultiByteStr,	// address of string to map 
#     int cchMultiByte,	// number of characters in string 
#     LPWSTR lpWideCharStr,	// address of wide-character buffer 
#     int cchWideChar 	// size of buffer 
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


try:
    SHShellExecuteW = _shell32dll.SHShellExecuteW
except AttributeError:
    # TODO: Can this happen on Win9x?
    # Even worse: What to do if it does not happen?
    SHShellExecuteW = None

# HINSTANCE ShellExecute(
# 
#     HWND hwnd,	// handle to parent window
#     LPCTSTR lpOperation,	// pointer to string that specifies operation to perform
#     LPCTSTR lpFile,	// pointer to filename or folder name string
#     LPCTSTR lpParameters,	// pointer to string that specifies executable-file parameters 
#     LPCTSTR lpDirectory,	// pointer to string that specifies default directory
#     INT nShowCmd 	// whether file is shown when opened
#    );
#    
   
# res = _shell32dll.ShellExecuteW(hwnd, 0, ctypes.c_wchar_p(ur"file:///C|/Daten/Projekte/Wikidpad/Current/wikidpad_unicode.iss"), 0, 0, SW_SHOW)


def ansiInputToUnicodeChar(ansiCode):
    """
    A special function for Windows 9x/ME to convert from ANSI to unicode
    ansiCode -- Numerical ANSI keycode from EVT_CHAR
    """
    if ansiCode < 128:
        return unichr(ansiCode)

    if ansiCode > 255:
        # This may be wrong for Asian languages on Win 9x,
        # but I just hope this case doesn't happen
        return unichr(ansiCode)


    # get current locale
    lcid = _user32dll.GetKeyboardLayout(0) & 0xffff
    
    # get codepage for locale
    currAcpStr = (c_char * 50)()

    _kernel32dll.GetLocaleInfoA(lcid, LOCALE_IDEFAULTANSICODEPAGE,
            byref(currAcpStr), 50)

    try:
        codepage = int(currAcpStr.value)
    except:
        return unichr(ansiCode)
        
    ansiByte = c_byte(ansiCode)
    uniChar = (c_ushort * 2)()
    
    length = MultiByteToWideChar(codepage, MB_PRECOMPOSED, byref(ansiByte), 1,
            byref(uniChar), 2)
            
    if length == 0:
        # function failed, fallback
        return unichr(ansiCode)
    elif length == 1:
        return unichr(uniChar[0])
    elif length == 2:
        return unichr(uniChar[0]) + unichr(uniChar[1])

    assert 0


class BaseWinProcIntercept:
    """
    Generic base class for intercepting the WinProc of a window
    """
    def __init__(self):
        self.oldWinProc = None
        self.ctWinProcStub = None
        self.hWnd = None

    def intercept(self, hWnd):
        if self.isIntercepting():
            return

        self.hWnd = hWnd

        # The stub must be saved because ctypes doesn't hold an own reference
        # to it.
        self.ctWinProcStub = WindowProcType(self.winProc)
        self.oldWndProc = SetWindowLong(c_int(self.hWnd), c_int(GWL_WNDPROC),
                self.ctWinProcStub)

    def unintercept(self):
        if not self.isIntercepting():
            return
            
        SetWindowLong(c_int(self.hWnd), c_int(GWL_WNDPROC),
                c_int(self.oldWndProc))

        self.oldWinProc = None
        self.ctWinProcStub = None
        self.hWnd = None


    def isIntercepting(self):
        return self.hWnd is not None
        

    def winProc(self, hWnd, uMsg, wParam, lParam):
        """
        This base class reacts only on a WM_DESTROY message and
        stops interception. All messages are sent to the original WinProc
        """
        if uMsg == WM_DESTROY and hWnd == self.hWnd:
            self.unintercept()
            
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
        self.intercept(hWnd)
        # SetClipboardViewer sends automatically an initial clipboard changed (CC)
        # message which should be ignored
        self.firstCCMessage = True
        self.nextWnd = SetClipboardViewer(c_int(self.hWnd))


    def stop(self):
        if self.nextWnd is None:
            return

        ChangeClipboardChain(c_int(self.hWnd), c_int(self.nextWnd))
        
        self.nextWnd = None
        
        
    def unintercept(self):
        self.stop()
        BaseWinProcIntercept.unintercept(self)


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
        assert 0  # abstract



class WikidPadWin32WPInterceptor(BaseClipboardCatcher):
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
        self.mode = WikidPadWin32WPInterceptor.MODE_OFF
        self.lastText = None
        
    def startAtPage(self, hWnd, wikiPage):
        """
        wikiPage -- page to write clipboard content to
        """
        if not isinstance(wikiPage,
                (DocPages.WikiPage, DocPages.AliasWikiPage)):
            self.mainControl.displayErrorMessage(
                    u"Only a real wiki page can be a clipboard catcher")
            return
            
        if self.mode != WikidPadWin32WPInterceptor.MODE_OFF:
            self.stop()

        self.lastText = None
        BaseClipboardCatcher.start(self, hWnd)
        self.wikiPage = wikiPage
        self.mode = WikidPadWin32WPInterceptor.MODE_AT_PAGE

    def startAtCursor(self, hWnd):
        """
        Write clipboard content to cursor position
        """
        if self.mode != WikidPadWin32WPInterceptor.MODE_OFF:
            self.stop()

        self.lastText = None
        BaseClipboardCatcher.start(self, hWnd)
        self.mode = WikidPadWin32WPInterceptor.MODE_AT_CURSOR


    def stop(self):
        BaseClipboardCatcher.stop(self)
        self.lastText = None
        self.wikiPage = None
        self.mode = WikidPadWin32WPInterceptor.MODE_OFF

    def getMode(self):
        return self.mode


    def winProc(self, hWnd, uMsg, wParam, lParam):
#         if uMsg == WM_CHAR:
#             print "WM_CHAR", repr((hWnd, wParam, lParam))
#             
#         if uMsg == WM_KEYDOWN:
#             print "WM_KEYDOWN", repr((hWnd, wParam, lParam))
# 
#         if uMsg == WM_INPUTLANGCHANGE:
#             print "WM_INPUTLANGCHANGE", repr((hWnd, wParam))

        return BaseClipboardCatcher.winProc(self, hWnd, uMsg, wParam, lParam)
        
        
    def notifyUserOnClipboardChange(self):
        config = self.mainControl.getConfig()
        notifMode = config.getint("main", "clipboardCatcher_userNotification", 0)
        if notifMode == 1:
            soundPath = config.get("main", "clipboardCatcher_soundFile", u"")
            if soundPath == u"":
                wx.Bell()
            else:
                try:
                    sound = wx.Sound(soundPath)
                    if sound.IsOk():
                        sound.Play(wx.SOUND_ASYNC)
                        self.clipCatchNotifySound = sound  # save a reference
                                # (This shoudln't be needed, but there seems to be a bug...)
                    else:
                        wx.Bell()
                except NotImplementedError, v:
                    wx.Bell()


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

        if self.mode == WikidPadWin32WPInterceptor.MODE_OFF:
            return
            
        if self.mainControl.getConfig().getboolean("main",
                "clipboardCatcher_filterDouble", True) and self.lastText == text:
            # Same text shall be inserted again
            return

        if self.mode == WikidPadWin32WPInterceptor.MODE_AT_PAGE:
            if self.wikiPage is None:
                return
            self.wikiPage.appendLiveText(text + suffix)
            self.notifyUserOnClipboardChange()
            
        elif self.mode == WikidPadWin32WPInterceptor.MODE_AT_CURSOR:
            self.mainControl.getActiveEditor().ReplaceSelection(text + suffix)
            self.notifyUserOnClipboardChange()
            
        self.lastText = text


    def getWikiWord(self):
        if self.wikiPage is None:
            return None
        else:
            return self.wikiPage.getWikiWord()


