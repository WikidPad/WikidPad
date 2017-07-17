"""
This is a Windows (32 bit) specific file for handling some operations not provided
by the OS-independent wxPython library.
"""

import ctypes, os, os.path, re, struct, traceback, multiprocessing
from ctypes import c_int, c_uint, c_long, c_ulong, c_ushort, c_char, c_char_p, \
        c_wchar_p, c_byte, byref, create_string_buffer, create_unicode_buffer, \
        c_void_p, string_at, sizeof   # , WindowsError

import wx

from .wxHelper import getTextFromClipboard
from .WikiExceptions import InternalError

from .StringOps import strftimeUB, pathEnc, mbcsEnc, mbcsDec   # unescapeWithRe
from . import SystemInfo
from . import DocPages



_user32dll = ctypes.windll.User32
_kernel32dll = ctypes.windll.Kernel32
_shell32dll = ctypes.windll.Shell32
_gdi32dll = ctypes.windll.Gdi32


GWL_WNDPROC = -4
WM_CHANGECBCHAIN = 781
WM_CHAR = 258
WM_DRAWCLIPBOARD = 776
WM_DESTROY = 2
WM_INPUTLANGCHANGE = 81
WM_KEYDOWN = 256

WM_APPCOMMAND = 0x0319
APPCOMMAND_BROWSER_BACKWARD = 1
APPCOMMAND_BROWSER_FORWARD = 2

MAX_PATH = 260


LOCALE_IDEFAULTANSICODEPAGE = 0x1004

MB_PRECOMPOSED = 1

SW_SHOW = 5

CF_METAFILEPICT = 3

FORMAT_MESSAGE_FROM_SYSTEM = 0x00001000
FORMAT_MESSAGE_ARGUMENT_ARRAY = 0x00002000


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



OpenClipboard = _user32dll.OpenClipboard
# BOOL OpenClipboard(
#     HWND hWndNewOwner
#    );



CloseClipboard = _user32dll.CloseClipboard
# BOOL CloseClipboard(
#     VOID
#    );


IsClipboardFormatAvailable = _user32dll.IsClipboardFormatAvailable
# BOOL IsClipboardFormatAvailable(
#     UINT format
#    );


GetClipboardData = _user32dll.GetClipboardData
GetClipboardData.restype = c_uint
# HANDLE GetClipboardData(
#     UINT uFormat
#    );


GlobalLock = _kernel32dll.GlobalLock
GlobalLock.restype = c_void_p
# LPVOID GlobalLock(
#   HGLOBAL hMem
# );



GlobalUnlock = _kernel32dll.GlobalUnlock
GlobalUnlock.restype = c_uint
# BOOL GlobalUnlock(
#   HGLOBAL hMem
# );



GlobalSize = _kernel32dll.GlobalSize
GlobalSize.restype = c_uint
# SIZE_T GlobalSize(
#   HGLOBAL hMem
# );



CopyMetaFile = _gdi32dll.CopyMetaFileW
CopyMetaFile.restype = c_uint
# HMETAFILE CopyMetaFile(
#   HMETAFILE hmfSrc,  // handle to Windows-format metafile
#   LPCTSTR lpszFile   // file name
# );


DeleteMetaFile = _gdi32dll.DeleteMetaFile
# BOOL DeleteMetaFile(
#   HMETAFILE hmf   // handle to Windows-format metafile
# );


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


FormatMessage = _kernel32dll.FormatMessageW
# DWORD FormatMessage(
#   DWORD dwFlags,
#   LPCVOID lpSource,
#   DWORD dwMessageId,
#   DWORD dwLanguageId,
#   LPTSTR lpBuffer,
#   DWORD nSize,
#   va_list* Arguments
# );


GetLastError = _kernel32dll.GetLastError
# DWORD GetLastError(void);


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


MapVirtualKey = _user32dll.MapVirtualKeyW
MapVirtualKey.restype = c_uint
# UINT MapVirtualKey(UINT uCode,
#     UINT uMapType
# );


VkKeyScan = _user32dll.VkKeyScanW
VkKeyScan.argtypes = [ctypes.c_wchar]
# SHORT VkKeyScan(          TCHAR ch
# );




# TODO
GetCurrentProcess = _kernel32dll.GetCurrentProcess
# HANDLE WINAPI GetCurrentProcess(void);


SetProcessAffinityMask = _kernel32dll.SetProcessAffinityMask
# BOOL WINAPI SetProcessAffinityMask(
#   _In_  HANDLE hProcess,
#   _In_  DWORD_PTR dwProcessAffinityMask
# );


GetProcessAffinityMask = _kernel32dll.GetProcessAffinityMask
# BOOL WINAPI GetProcessAffinityMask(
#   _In_   HANDLE hProcess,
#   _Out_  PDWORD_PTR lpProcessAffinityMask,
#   _Out_  PDWORD_PTR lpSystemAffinityMask
# );




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
    ShellExecuteW = _shell32dll.ShellExecuteW
except AttributeError:
    # TODO: Can this happen on Win9x?
    # Even worse: What to do if it does not happen?
    ShellExecuteW = None

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



class SHFILEOPSTRUCTW(ctypes.Structure):
    _fields_ = [
        ("hwnd", ctypes.c_uint),
        ("wFunc", ctypes.c_uint),
        ("pFrom", ctypes.c_wchar_p),
        ("pTo", ctypes.c_wchar_p),
        ("fFlags", ctypes.c_uint),
        ("fAnyOperationsAborted", ctypes.c_uint),
        ("hNameMappings", ctypes.c_uint),
        ("lpszProgressTitle", ctypes.c_wchar_p)
        ]


# typedef struct _SHFILEOPSTRUCTW {
# 	HWND hwnd;
# 	UINT wFunc;
# 	LPCWSTR pFrom;
# 	LPCWSTR pTo;
# 	FILEOP_FLAGS fFlags;
# 	BOOL fAnyOperationsAborted;
# 	PVOID hNameMappings;
# 	LPCWSTR lpszProgressTitle;
# } SHFILEOPSTRUCTW,*LPSHFILEOPSTRUCTW;


FO_MOVE = 1
FO_COPY = 2
FO_DELETE = 3
# FO_RENAME = 4

FOF_MULTIDESTFILES = 1
FOF_NOCONFIRMATION = 16
FOF_ALLOWUNDO = 0x0040
FOF_NOCONFIRMMKDIR = 512
FOF_NOERRORUI = 1024
FOF_SILENT = 4
FOF_WANTNUKEWARNING = 0x4000   # Windows 2000 and later

try:
    SHFileOperationW = _shell32dll.SHFileOperationW
except AttributeError:
    SHFileOperationW = None

# int SHFileOperation(LPSHFILEOPSTRUCT lpFileOp);


if SHFileOperationW is not None:
    def _shellFileOp(opcode, srcPath, dstPath):
        fileOp = SHFILEOPSTRUCTW()

        srcPathWc = ctypes.c_wchar_p(srcPath + "\0")

        fileOp.hwnd = 0
        fileOp.wFunc = opcode
        fileOp.pFrom = srcPathWc
        if dstPath is not None:
            dstDir = os.path.dirname(dstPath)

            if not os.path.exists(pathEnc(dstDir)):
                os.makedirs(dstDir)

            dstPathWc = ctypes.c_wchar_p(dstPath + "\0")
            fileOp.pTo = dstPathWc
        else:
            fileOp.pTo = 0
        fileOp.fFlags = FOF_ALLOWUNDO | FOF_MULTIDESTFILES | FOF_NOCONFIRMATION | \
                FOF_NOCONFIRMMKDIR | FOF_WANTNUKEWARNING # | FOF_SILENT  | FOF_NOERRORUI
        fileOp.fAnyOperationsAborted = 0
        fileOp.hNameMappings = 0
        fileOp.lpszProgressTitle = 0

        res = SHFileOperationW(ctypes.byref(fileOp))

        if res != 0:
            if opcode == FO_COPY:
                raise IOError(
                        _("Copying from %s to %s failed. SHFileOperation result no. %s") %
                        (srcPath, dstPath, res))
            elif opcode == FO_MOVE:
                raise IOError(
                        _("Moving from %s to %s failed. SHFileOperation result no. %s") %
                        (srcPath, dstPath, res))
            elif opcode == FO_DELETE:
                raise IOError(
                        _("Deleting %s failed. SHFileOperation result no. %s") %
                        (srcPath, res))
            else:
                raise InternalError("SHFileOperation failed. Opcode=%s from=%s to=%s errcode=%s" %
                        (opcode, srcPath, dstPath, res))


    def copyFile(srcPath, dstPath):
        """
        Copy file from srcPath to dstPath. dstPath may be overwritten if
        existing already. dstPath must point to a file, not a directory.
        If some directories in dstPath do not exist, they are created.

        This function only works on Win NT!
        """
        _shellFileOp(FO_COPY, srcPath, dstPath)

    def moveFile(srcPath, dstPath):
        """
        Move file from srcPath to dstPath. dstPath may be overwritten if
        existing already. dstPath must point to a file, not a directory.
        If some directories in dstPath do not exist, they are created.

        This function only works on Win NT!
        """
        _shellFileOp(FO_MOVE, srcPath, dstPath)

    def deleteFile(path):
        """
        Delete file or directory  path.

        This function only works on Win NT!
        """
        if os.path.isfile(path) or os.path.islink(path):
            _shellFileOp(FO_DELETE, path, None)
        elif os.path.isdir(path):
            os.rmdir(path)


def _getMemoryContentFromHandle(hdl):
    """
    Needed to retrieve clipboard data
    """
    pt = GlobalLock(hdl)
    if pt == 0:
        return None
    try:
        size = GlobalSize(hdl)

        return string_at(pt, size)
    finally:
        GlobalUnlock(hdl)


def isWmfAvailableOnClipboard():
    """
    Return True iff Windows meta file format is available on clipboard
    """
    OpenClipboard(0)
    try:
        return IsClipboardFormatAvailable(CF_METAFILEPICT) != 0
    finally:
        CloseClipboard()
    
    

def saveWmfFromClipboardToFileStorage(fs, prefix):
    """
    Retrieve raw Windows meta data file from clipboard. Return None,
    if not present.

    fs -- FileStorage to save to

    Returns path to new file or None.
    """
    OpenClipboard(0)
    try:
        if IsClipboardFormatAvailable(CF_METAFILEPICT) == 0:
            return None

        hdl = GetClipboardData(CF_METAFILEPICT)
        if hdl == 0:
            return None

        data = _getMemoryContentFromHandle(hdl)
        if data is None:
            return None

        hdl = struct.unpack("lllI", data)[3]

        destPath = fs.findDestPathNoSource(".wmf", prefix)

        if destPath is None:
            # Couldn't find unused filename
            return None

        chdl = CopyMetaFile(hdl, destPath)
        if chdl == 0:
            return None

        DeleteMetaFile(chdl)

        return destPath
    finally:
        CloseClipboard()




GetLongPathName = _kernel32dll.GetLongPathNameW
# DWORD GetLongPathName(
#   LPCTSTR lpszShortPath,
#   LPTSTR lpszLongPath,
#   DWORD cchBuffer
# );



def getLongPath(path):
    if isinstance(path, str):
        path = mbcsDec(path)[0]

    if not isinstance(path, str):
        return path

    if len(path) > 32760:
        # Path too long for UNICODE
        return path

    result = create_unicode_buffer(1024)
    rv = GetLongPathName("\\\\?\\" + path, result, 1024)
    if rv == 0:
        return path
    if rv > 1024:
        result = create_unicode_buffer(rv)
        rv = GetLongPathName("\\\\?\\" + path, result, rv)

        if rv == 0:
            return path

    return result.value[4:]


def getErrorMessageFromCode(errCode):
    result = create_unicode_buffer(1024)

    FormatMessage(FORMAT_MESSAGE_FROM_SYSTEM | FORMAT_MESSAGE_ARGUMENT_ARRAY,
            0, errCode, 0, result, 1024, 0)

    return result.value


def getLastErrorMessage():
    return getErrorMessageFromCode(GetLastError())



def ansiInputToUnicodeChar(ansiCode):
    """
    A special function for Windows 9x/ME to convert from ANSI to unicode
    ansiCode -- Numerical ANSI keycode from EVT_CHAR
    """
    if ansiCode < 128:
        return chr(ansiCode)

    if ansiCode > 255:
        # This may be wrong for Asian languages on Win 9x,
        # but I just hope this case doesn't happen
        return chr(ansiCode)


    # get current locale
    lcid = _user32dll.GetKeyboardLayout(0) & 0xffff

    # get codepage for locale
    currAcpStr = (c_char * 50)()

    _kernel32dll.GetLocaleInfoA(lcid, LOCALE_IDEFAULTANSICODEPAGE,
            byref(currAcpStr), 50)

    try:
        codepage = int(currAcpStr.value)
    except:
        return chr(ansiCode)

    ansiByte = c_byte(ansiCode)
    uniChar = (c_ushort * 2)()

    length = MultiByteToWideChar(codepage, MB_PRECOMPOSED, byref(ansiByte), 1,
            byref(uniChar), 2)

    if length == 0:
        # function failed, fallback
        return chr(ansiCode)
    elif length == 1:
        return chr(uniChar[0])
    elif length == 2:
        return chr(uniChar[0]) + chr(uniChar[1])

    assert 0



if ShellExecuteW:
    def startFile(mainControl, link):
        if not isinstance(link, str):
            link = str(link)
        # TODO Test result?
        res = _shell32dll.ShellExecuteW(0, 0, ctypes.c_wchar_p(link), 0, 0,
                SW_SHOW)

        return res



def checkForOtherInstances():
    return []

try:
    from .WindowsHacksZombieCheck import checkForOtherInstances
except:
    if SystemInfo.isWindows():
        traceback.print_exc()



_ACCEL_KEY_MAPPING = None

def translateAcceleratorByKbLayout(accStr):
    global _ACCEL_KEY_MAPPING

    cm = re.match(r"(.+?[\+\-])(.) *$", accStr)
    if not cm:
        return accStr

    if not _ACCEL_KEY_MAPPING:
        # Build mapping

        result = {}

        # Dictionary for alternative detection method
        resultBack = {}

        # The order to scan for matches is important:
        # 1. Uppercase letters
        # 2. Digits
        # 3. Remaining codes

        for char in list(range(0x41, 0x5b)) + list(range(0x30, 0x3a)) + \
                list(range(0x20, 0x30)) + list(range(0x3a, 0x41)) + list(range(0x5b, 0xffff)):
            ks = VkKeyScan(chr(char))
            vkCode = ks & 0xff

            if vkCode == 0:
                continue

            # Alternative method
            targetChar = chr(vkCode).upper()
            if not targetChar in resultBack:
                resultBack[targetChar] = chr(char)


            targetChar = MapVirtualKey(vkCode, 2) & 0xffff

            if targetChar == 0:
                continue

            targetChar = chr(targetChar).upper()

            if targetChar in result:
                continue

            result[targetChar] = chr(char)

        # If result and resultBack have a key, result wins
        resultBack.update(result)
        _ACCEL_KEY_MAPPING = resultBack

    return cm.group(1) + _ACCEL_KEY_MAPPING.get(cm.group(2), cm.group(2))



def _getAffMaskIntegerByIndexes(cpuIndexSeq):
    """
    Convert sequence of cpus to integer object with appropriate bits set.
    indexseq -- Sequence of integer index numbers of cpu cores (first is 0).
            0 <= indexseq < (32 for 32bit and 64 for 64bit Windows)
    """
    result = 0
    
    max = sizeof(c_uint) * 8;

    for idx in cpuIndexSeq:
        if idx < 0:
            raise ValueError()
        
        if idx >= max:
            continue

        result |= 1 << idx
    
    return result


def _getSystemAffMask():
    """
    Retrieve system affinity mask (existing configured processors) as a bitset
    integer.
    Setting process affinity mask will fail if it has a 1 set in a bit where
    system affinity mask has 0.
    See http://msdn.microsoft.com/en-us/library/windows/desktop/ms683213%28v=vs.85%29.aspx
    
    May return 0 on failure
    """

    procMask = c_uint()
    sysMask = c_uint()
    result = GetProcessAffinityMask(GetCurrentProcess(), byref(procMask), byref(sysMask))
    if result == 0:
        # Something went wrong
        return 0
    
    return sysMask.value


def setCpuAffinity(cpuIndexSeq):
    """
    Set affinity of current process to those CPUs listed as sequence of integers
    in the cpuIndexSeq. Numbers equal or higher than getCpuCount() are ignored.
    
    If no valid CPU number is in cpuIndexSeq, function returns False and
    affinity isn't set.
    
    cpuIndexSeq -- Sequence of integer index numbers of cpu cores (first is 0).
    """

    procIntMask = _getAffMaskIntegerByIndexes(cpuIndexSeq)

    # Restrict to system-known CPUs
    procIntMask &= _getSystemAffMask()
    
    if procIntMask == 0:
        # No valid CPUs remain
        return False
    
    result = SetProcessAffinityMask(GetCurrentProcess(), c_uint(procIntMask))
    
    if result != 0:
        return True
        
    return False


def getCpuAffinity():
    """
    Get affinity of current process as a list of all CPU numbers to which
    the process is assigned.
    
    May return None if something went wrong.
    """
    maxNum = getCpuCount()

    result = []

    procMask = c_uint()
    sysMask = c_uint()
    retval = GetProcessAffinityMask(GetCurrentProcess(), byref(procMask), byref(sysMask))
    if retval == 0:
        # Something went wrong
        return None

    procMask = procMask.value

    for i in range(maxNum):
        if (procMask & (1 << i)) != 0:
            result.append(i)

    return result



def getCpuCount():
    """
    Returns number of CPUs allowed for the sequence list for setCpuAffinity().
    Highest number in sequence list must be lower than getCpuCount()
    
    The highest valid cpu number is system dependent and may be lower than
    the number of available CPUs.
    
    If setting CPU affinity is not supported, function returns 0
    """
    try:
        return min(sizeof(c_uint) * 8, multiprocessing.cpu_count())
    except NotImplementedError:
        return 0





class WinProcParams:
    def __init__(self):
        self.hWnd = None
        self.uMsg = None
        self.wParam = None
        self.lParam = None
        self.returnValue = None

    def set(self, hWnd, uMsg, wParam, lParam):
        self.hWnd = hWnd
        self.uMsg = uMsg
        self.wParam = wParam
        self.lParam = lParam
        self.returnValue = None


class BaseWinInterceptor:
    def __init__(self):
        pass

    def addInterceptCollection(self, interceptCollection):
        """
        Called automatically if interceptor is added to an
        intercept collection
        """
        pass

    def removeInterceptCollection(self, interceptCollection):
        """
        Called automatically if interceptor is removed from an
        intercept collection.
        """
        pass


    def startBeforeIntercept(self, interceptCollection):
        """
        Called for each interceptor of a collection before the actual
        intercept happens. If one interceptor returns anything but True,
        interception doesn't happen.
        """
        return True

    def startAfterIntercept(self, interceptCollection):
        """
        Called for each interceptor of a collection after the actual
        intercept happened.
        """
        pass


    def stopBeforeUnintercept(self, interceptCollection):
        """
        Called for each interceptor of a collection before the actual
        unintercept happens. If one interceptor returns anything but True,
        uninterception doesn't happen (this may be dangerous).
        """
        return True

    def stopAfterUnintercept(self, interceptCollection):
        """
        Called for each interceptor of a collection after the actual
        unintercept happened.
        """
        pass


    def interceptWinProc(self, interceptCollection, params):
        """
        Called for each Windows message to the intercepted window. This is
        the ANSI-style method, wide-char is not supported.

        params -- WinProcParams object containing parameters the function can
                modify and a returnValue which can be set to prevent
                from calling interceptWinProc functions
        """
        pass






class WinProcInterceptCollection:
    """
    Class holding a list of interceptor objects which can do different
    operations on the WinProc of a window.
    """
    def __init__(self, interceptors=None):
        self.oldWinProc = None
        self.ctWinProcStub = None
        self.hWnd = None
        self.interceptors = []

        self.winParams = WinProcParams()

        if interceptors is not None:
            for icept in interceptors:
                self.addInterceptor(icept)


    # TODO Test if already started!
    def addInterceptor(self, icept):
        if icept in self.interceptors:
            return

        icept.addInterceptCollection(self)
        self.interceptors.append(icept)


    def clear(self):
        self.stop()

        for icept in self.interceptors:
            icept.removeInterceptCollection(self)

        self.interceptors = []


    def close(self):
        self.clear()


    def getHWnd(self):
        return self.hWnd


    def start(self, callingWindow):
        if self.isIntercepting():
            return False

        for icept in self.interceptors:
            if not icept.startBeforeIntercept(self):
                return False

        self.intercept(callingWindow)

        for icept in self.interceptors:
            try:
                icept.startAfterIntercept(self)
            except:
                traceback.print_exc()

        return True


    def stop(self):
        if not self.isIntercepting():
            return False

        for icept in self.interceptors:
            try:
                if not icept.stopBeforeUnintercept(self):
                    return False
            except:
                traceback.print_exc()

        self.unintercept()

        for icept in self.interceptors:
            try:
                icept.stopAfterUnintercept(self)
            except:
                traceback.print_exc()



    def intercept(self, callingWindow):
        if self.isIntercepting():
            return

        self.hWnd = callingWindow.GetHandle()

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


    def _lastWinProc(self, params):
        """
        This default function reacts only on a WM_DESTROY message and
        stops interception. All messages are sent to the original WinProc
        """

        if params.uMsg == WM_DESTROY and params.hWnd == self.hWnd:
            self.stop()

        params.returnValue = CallWindowProc(c_int(self.oldWndProc),
                c_int(params.hWnd), c_uint(params.uMsg),
                c_uint(params.wParam), c_ulong(params.lParam))


    def winProc(self, hWnd, uMsg, wParam, lParam):
        params = self.winParams
        params.set(hWnd, uMsg, wParam, lParam)

        for icept in self.interceptors:
            try:
                icept.interceptWinProc(self, params)
            except:
                traceback.print_exc()

            if params.returnValue is not None:
                return params.returnValue

        self._lastWinProc(params)
        return params.returnValue





# class TestWinProcIntercept(BaseWinProcIntercept):
#     """
#     Just for debugging/testing
#     """
#     def winProc(self, hWnd, uMsg, wParam, lParam):
#         print "Intercept1", repr((uMsg, wParam, lParam))
#
#         return BaseWinProcIntercept.winProc(self, hWnd, uMsg, wParam, lParam)


class ClipboardCatchIceptor(BaseWinInterceptor):
    """
    Interceptor module to catch clipboard changes.
    """
    MODE_OFF = 0
    MODE_AT_PAGE = 1
    MODE_AT_CURSOR = 2

    def __init__(self, mainControl):
        BaseWinInterceptor.__init__(self)

        self.hWnd = None
        self.nextWnd = None

        self.ignoreNextCCMessage = False

        self.mainControl = mainControl
        self.wikiPage = None
        self.mode = ClipboardCatchIceptor.MODE_OFF
        self.lastText = None


    def getMode(self):
        return self.mode

    def _cbViewerChainIn(self):
        """
        Hook into clipboard viewer chain.
        """
        if self.nextWnd is not None:
            return

        # SetClipboardViewer sends automatically an initial clipboard changed (CC)
        # message which should be ignored
        self.ignoreNextCCMessage = True
        self.nextWnd = SetClipboardViewer(c_int(self.hWnd))


    def _cbViewerChainOut(self):
        """
        Remove hook to clipboard viewer chain.
        """
        if self.nextWnd is None:
            return

        ChangeClipboardChain(c_int(self.hWnd), c_int(self.nextWnd))
        self.nextWnd = None


    def catchAtPage(self, wikiPage):
        """
        wikiPage -- page to write clipboard content to
        """
        if not isinstance(wikiPage,
                (DocPages.WikiPage, DocPages.AliasWikiPage)):
            self.mainControl.displayErrorMessage(
                    _("Only a real wiki page can be a clipboard catcher"))
            return

        self.lastText = None
        self.wikiPage = wikiPage
        self.mode = ClipboardCatchIceptor.MODE_AT_PAGE
        self._cbViewerChainIn()


    def catchAtCursor(self):
        """
        Write clipboard content to cursor position
        """
        self.lastText = None
        self.mode = ClipboardCatchIceptor.MODE_AT_CURSOR
        self._cbViewerChainIn()


    def catchOff(self):
        self.mode = ClipboardCatchIceptor.MODE_OFF
        self._cbViewerChainOut()


    def informCopyInWikidPadStart(self, text=None):
        """
        Informs the interceptor, that currently something is copied in the
        editor in WikidPad itself. If mode is MODE_AT_CURSOR this
        clipboard content is then not copied back into the editor.
        """
        if self.mode == ClipboardCatchIceptor.MODE_AT_CURSOR:
            self.ignoreNextCCMessage = True
            self.lastText = None

    def informCopyInWikidPadStop(self):
        pass


    def startAfterIntercept(self, interceptCollection):
        """
        Called for each interceptor of a collection after the actual
        intercept happened.
        """
        self.hWnd = interceptCollection.getHWnd()


    def stopAfterUnintercept(self, interceptCollection):
        """
        Called for each interceptor of a collection after the actual
        unintercept happened.
        """
        self._cbViewerChainOut()
        self.hWnd = None


    def interceptWinProc(self, interceptCollection, params):
        """
        Called for each Windows message to the intercepted window. This is
        the ANSI-style method, wide-char is not supported.

        params -- WinProcParams object containing parameters the function can
                modify and a returnValue which can be set to prevent
                from calling interceptWinProc functions
        """
        if params.uMsg == WM_CHANGECBCHAIN:
            if self.nextWnd == params.wParam:
                # repair the chain
                self.nextWnd = params.lParam

            if self.nextWnd:  # Neither None nor 0
                # pass the message to the next window in chain
                SendMessage(c_int(self.nextWnd), c_int(params.uMsg),
                        c_uint(params.wParam), c_ulong(params.lParam))

        elif params.uMsg == WM_DRAWCLIPBOARD:
            if self.ignoreNextCCMessage:
                self.ignoreNextCCMessage = False
            else:
                self.handleClipboardChange()

            if self.nextWnd:  # Neither None nor 0
                # pass the message to the next window in chain
                SendMessage(c_int(self.nextWnd), c_int(params.uMsg),
                        c_uint(params.wParam), c_ulong(params.lParam))



    def notifyUserOnClipboardChange(self):
        config = self.mainControl.getConfig()
        notifMode = config.getint("main", "clipboardCatcher_userNotification", 0)
        if notifMode == 1:
            soundPath = config.get("main", "clipboardCatcher_soundFile", "")
            if soundPath == "":
                wx.Bell()
            else:
                try:
                    sound = wx.Sound(soundPath)
                    if sound.IsOk():
                        sound.Play(wx.SOUND_ASYNC)
                        self.clipCatchNotifySound = sound  # save a reference
                                # (This shouldn't be needed, but there seems to be a bug...)
                    else:
                        wx.Bell()
                except NotImplementedError as v:
                    wx.Bell()


    def handleClipboardChange(self):
        text = getTextFromClipboard()
        if text is None or len(text) == 0:
            return
        try:
            prefix = strftimeUB(self.mainControl.getConfig().get(
                    "main", "clipboardCatcher_prefix", r""))
        except:
            traceback.print_exc()
            prefix = ""   # TODO Error message?

        try:
            suffix = strftimeUB(self.mainControl.getConfig().get(
                    "main", "clipboardCatcher_suffix", r"\n"))
        except:
            traceback.print_exc()
            suffix = "\n"   # TODO Error message?

        if self.mode == ClipboardCatchIceptor.MODE_OFF:
            return

        if self.mainControl.getConfig().getboolean("main",
                "clipboardCatcher_filterDouble", True) and self.lastText == text:
            # Same text shall be inserted again
            return

        if self.mode == ClipboardCatchIceptor.MODE_AT_PAGE:
            if self.wikiPage is None:
                return
            self.wikiPage.appendLiveText(prefix + text + suffix)
            self.notifyUserOnClipboardChange()

        elif self.mode == ClipboardCatchIceptor.MODE_AT_CURSOR:
            self.mainControl.getActiveEditor().ReplaceSelection(prefix + text + suffix)
            self.notifyUserOnClipboardChange()

        self.lastText = text


    def getWikiWord(self):
        if self.wikiPage is None:
            return None
        else:
            return self.wikiPage.getWikiWord()






class BrowserMoveIceptor(BaseWinInterceptor):
    """
    Interceptor module to catch application keys on mouse or keyboard to go
    backward or forward in browser.
    """
    def __init__(self, mainControl):
        BaseWinInterceptor.__init__(self)

        self.mainControl = mainControl


#     def startAfterIntercept(self, interceptCollection):
#         """
#         Called for each interceptor of a collection after the actual
#         intercept happened.
#         """
#         self.hWnd = interceptCollection.getHWnd()
#
#
#     def stopAfterUnintercept(self, interceptCollection):
#         """
#         Called for each interceptor of a collection after the actual
#         unintercept happened.
#         """
#         self._cbViewerChainOut()
#         self.hWnd = None


    def interceptWinProc(self, interceptCollection, params):
        """
        Called for each Windows message to the intercepted window. This is
        the ANSI-style method, wide-char is not supported.

        params -- WinProcParams object containing parameters the function can
                modify and a returnValue which can be set to prevent
                from calling interceptWinProc functions
        """
        if params.uMsg == WM_APPCOMMAND:
            cmd = (params.lParam >> 16) & 0xFFF
            if cmd == APPCOMMAND_BROWSER_BACKWARD:
                self.mainControl.goBrowserBack()
                params.returnValue = 1

            elif cmd == APPCOMMAND_BROWSER_FORWARD:
                self.mainControl.goBrowserForward()
                params.returnValue = 1


