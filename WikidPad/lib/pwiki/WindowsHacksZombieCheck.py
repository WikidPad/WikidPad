import ctypes

_user32dll = ctypes.windll.User32
_kernel32dll = ctypes.windll.Kernel32
_shell32dll = ctypes.windll.Shell32
_gdi32dll = ctypes.windll.Gdi32

MAX_PATH =260

TH32CS_SNAPPROCESS = 0x2
PROCESS_ALL_ACCESS = 0x1F0FFF

SE_KERNEL_OBJECT = 6
OWNER_SECURITY_INFORMATION = 0x00000001
ERROR_SUCCESS = 0

# TODO: Check for 64bit system

HANDLE = ctypes.c_int   # ? for 64bit?
NULL = ctypes.c_void_p(0)


CreateToolhelp32Snapshot = _kernel32dll.CreateToolhelp32Snapshot
CreateToolhelp32Snapshot.argtypes = [ctypes.c_ulong, ctypes.c_ulong]
CreateToolhelp32Snapshot.restype = HANDLE
# HANDLE WINAPI CreateToolhelp32Snapshot(
#   DWORD dwFlags,
#   DWORD th32ProcessID
# );


class PROCESSENTRY32(ctypes.Structure):
    _fields_ = [
            ("dwSize", ctypes.c_ulong),
            ("cntUsage", ctypes.c_ulong),
            ("th32ProcessID", ctypes.c_ulong),
            ("th32DefaultHeapID", ctypes.c_int),
            ("th32ModuleID", ctypes.c_ulong),
            ("cntThreads", ctypes.c_ulong),
            ("th32ParentProcessID", ctypes.c_ulong),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", ctypes.c_ulong),

            ("szExeFile", ctypes.c_wchar * MAX_PATH)
        ]


# typedef struct tagPROCESSENTRY32 { 
# DWORD dwSize; 
# DWORD cntUsage; 
# DWORD th32ProcessID; 
# ULONG_PTR th32DefaultHeapID; 
# DWORD th32ModuleID; 
# DWORD cntThreads; 
# DWORD th32ParentProcessID; 
# LONG pcPriClassBase; 
# DWORD dwFlags; 
# TCHAR szExeFile[MAX_PATH];
# 
# } PROCESSENTRY32, 



Process32First = _kernel32dll.Process32FirstW
Process32First.argtypes = [HANDLE, ctypes.POINTER(PROCESSENTRY32)]
Process32First.restype = ctypes.c_int
# BOOL WINAPI Process32First(
#   HANDLE hSnapshot,
#   LPPROCESSENTRY32 lppe
# );


Process32Next = _kernel32dll.Process32NextW
Process32Next.argtypes = [HANDLE, ctypes.POINTER(PROCESSENTRY32)]
Process32Next.restype = ctypes.c_int
# BOOL WINAPI Process32Next(
#   HANDLE hSnapshot,
#   LPPROCESSENTRY32 lppe
# );

GetCurrentProcessId =_kernel32dll.GetCurrentProcessId
GetCurrentProcessId.argtypes = []
GetCurrentProcessId.restype = ctypes.c_ulong
# DWORD GetCurrentProcessId(void);


GetCurrentProcess =_kernel32dll.GetCurrentProcess
GetCurrentProcess.argtypes = []
GetCurrentProcess.restype = HANDLE
# HANDLE GetCurrentProcess(void);


CloseHandle = _kernel32dll.CloseHandle
CloseHandle.argtypes = [HANDLE]
CloseHandle.restype = ctypes.c_int
# BOOL CloseHandle(
#   HANDLE hObject
# );


OpenProcess = _kernel32dll.OpenProcess
OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
OpenProcess.restype = HANDLE
# HANDLE OpenProcess(
#   DWORD dwDesiredAccess,
#   BOOL bInheritHandle,
#   DWORD dwProcessId
# );


PSID = ctypes.c_void_p
PSECURITY_DESCRIPTOR = ctypes.c_void_p

GetSecurityInfo = ctypes.windll.advapi32.GetSecurityInfo
GetSecurityInfo.argtypes = [HANDLE, ctypes.c_int, ctypes.c_ulong, ctypes.POINTER(PSID),
        ctypes.POINTER(PSID), ctypes.c_void_p, ctypes.c_void_p,
        ctypes.POINTER(PSECURITY_DESCRIPTOR)]
GetSecurityInfo.restype = ctypes.c_ulong
# DWORD GetSecurityInfo(
#   HANDLE handle,
#   SE_OBJECT_TYPE ObjectType,
#   SECURITY_INFORMATION SecurityInfo,
#   PSID* ppsidOwner,
#   PSID* ppsidGroup,
#   PACL* ppDacl,
#   PACL* ppSacl,
#   PSECURITY_DESCRIPTOR* ppSecurityDescriptor
# );




EqualSid = ctypes.windll.advapi32.EqualSid
EqualSid.argtypes = [PSID, PSID]
EqualSid.restype = ctypes.c_int
# BOOL EqualSid(
#   PSID pSid1,
#   PSID pSid2
# );



LocalFree = _kernel32dll.LocalFree
LocalFree.argtypes = [ctypes.c_void_p]
LocalFree.restype = ctypes.c_void_p
# HLOCAL LocalFree(
#   HLOCAL hMem
# );


GetModuleFileNameEx = ctypes.windll.psapi.GetModuleFileNameExW
GetModuleFileNameEx.argtypes = [HANDLE, HANDLE, ctypes.c_void_p, ctypes.c_ulong]
GetModuleFileNameEx.restype = ctypes.c_ulong


# DWORD GetModuleFileNameEx(
#   HANDLE hProcess,
#   HMODULE hModule,
#   LPTSTR lpFilename,
#   DWORD nSize
# );



GetLastError = _kernel32dll.GetLastError
# DWORD GetLastError(void);





def getPsidAndSecdescByProcHandle(procHandle):
    psid = PSID()
    secdesc = PSECURITY_DESCRIPTOR()
    
    ret = GetSecurityInfo(procHandle, SE_KERNEL_OBJECT, 
        OWNER_SECURITY_INFORMATION, ctypes.byref(psid), None, None, None,
        ctypes.byref(secdesc))
    
    if ret != 0:
        return (None, None)
    else:
        return (psid, secdesc)




def getOtherProcIds():
    procE = PROCESSENTRY32()
    procE.dwSize = ctypes.sizeof(PROCESSENTRY32)
    
    ownProcId = GetCurrentProcessId()
    
    snapshot = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    
    result = []
    try:
        found = Process32First(snapshot, ctypes.byref(procE))
        
        while found:
            if procE.th32ProcessID != ownProcId:
                result.append(procE.th32ProcessID)
            
            found = Process32Next(snapshot, ctypes.byref(procE))
        
        return result
    finally:
        CloseHandle(snapshot)


def getProcHandleById(procId):
#     print "--getProcHandleById1", repr(type(procId))
    procHandle = OpenProcess(PROCESS_ALL_ACCESS, 0, procId)

    if procHandle == 0:
        return None
    return procHandle


def filterProcIdsByOwnPSID(procIdList):
    """
    Remove all processes not owned by current user
    """
    ownPsid, ownSecdesc = getPsidAndSecdescByProcHandle(GetCurrentProcess())
    try:
        if ownPsid is None:
            return procIdList
        
        result = []
        
        for procId in procIdList:
            procHandle = getProcHandleById(procId)
            if procHandle is None:
                continue

            psid, secdesc = getPsidAndSecdescByProcHandle(procHandle)
            if psid is None:
                continue
            
            if EqualSid(ownPsid, psid):
                result.append(procId)
            
            LocalFree(secdesc)
        
        return result

    finally:
        LocalFree(ownSecdesc)


def getModulePathByProcHandle(procHandle):
    pathMaxLength = 2048
    path = (ctypes.c_wchar * pathMaxLength)()

    while True:
        ret = GetModuleFileNameEx(procHandle, 0, ctypes.byref(path), pathMaxLength)
        if ret == 0:
            return None
        
        path = path.value
        if len(path) < (pathMaxLength - 1):
            # Path wasn't truncated
            return path
        
        pathMaxLength *= 2
        path = (ctypes.c_wchar * pathMaxLength)()


def getModulePathByProcId(procId):
    procHandle = getProcHandleById(procId)
    
    if procHandle is None:
        return None

    try:
        return getModulePathByProcHandle(procHandle)
    finally:
        CloseHandle(procHandle)



def checkForOtherInstances():
    from .OsAbstract import samefile
    procIdList = getOtherProcIds()
    ownModulePath = getModulePathByProcHandle(GetCurrentProcess())
    if ownModulePath is None:
        return []
    
    procIdList2 = []
    for procId in procIdList:
        modulePath = getModulePathByProcId(procId)
        if modulePath is None or not samefile(ownModulePath, modulePath):
            continue
        procIdList2.append(procId)
        
    return filterProcIdsByOwnPSID(procIdList2)



# procIdList = getOtherProcIds()
# print repr(procIdList)
# 
# print repr(filterProcIdsByOwnPSID(procIdList))
# 
# print repr(checkForOtherInstances())
# 
# 
# while True:
#     pass



