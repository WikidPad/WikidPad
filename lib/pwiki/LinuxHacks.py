"""
This is a Linux specific file for handling some operations not provided
by the OS-independent wxPython library.
"""

import ctypes, os, traceback, multiprocessing
from ctypes import c_int, c_uint, c_long, c_ulong, c_ushort, c_char, c_char_p, \
        c_wchar_p, c_byte, byref, create_string_buffer, create_unicode_buffer, \
        c_void_p, string_at, sizeof, Structure   # , WindowsError

from . import SystemInfo



libc = ctypes.CDLL('libc.so.6', use_errno=True)


# Based on "bits/sched.h", see e.g. http://code.woboq.org/gcc/include/bits/sched.h.html
# and http://linux.die.net/man/2/sched_setaffinity
try:
    sched_setaffinity = libc.sched_setaffinity
    sched_getaffinity = libc.sched_getaffinity
except:
    import ExceptionLogger
    ExceptionLogger.logOptionalComponentException(
            "Link to sched_setaffinity() in LinuxHacks.py")
    
    sched_setaffinity = None
    sched_getaffinity = None


# int sched_setaffinity(pid_t pid, size_t cpusetsize,
#                       cpu_set_t *mask);

# Naming is based on the C definitions, sometimes with less leading underscores
# than in original code

size_t = c_ulong
_cpu_mask = c_ulong
_CPU_SETSIZE = 1024
_NCPUBITS = 8 * sizeof (_cpu_mask)


class cpu_set_t(Structure):
    _fields_ = [("bits", _cpu_mask*(_CPU_SETSIZE // _NCPUBITS))]



def _getCpuSetTByIndexes(cpuIndexSeq):
    """
    Convert sequence of cpus to a cpu_set_t object with appropriate bits set.
    cpuIndexSeq -- Sequence of integer index numbers of cpu cores (first is 0).
            
    """
    result = cpu_set_t()

    for idx in cpuIndexSeq:
        if idx < 0:
            raise ValueError()
        
        if idx >= _CPU_SETSIZE:
            continue
            
        result.bits[idx // _NCPUBITS] |= 1 << (idx % _NCPUBITS)
    
    return result


def setCpuAffinity(cpuIndexSeq):
    """
    Set affinity of current process to those CPUs listed as sequence of integers
    in the cpuIndexSeq. Numbers equal or higher than getCpuCount() are ignored.
    
    If no valid CPU number is in cpuIndexSeq, function returns False and
    affinity isn't set.
    
    cpuIndexSeq -- Sequence of integer index numbers of cpu cores (first is 0).
    """
    if sched_setaffinity is None:
        return False

    cpuSet = _getCpuSetTByIndexes(cpuIndexSeq)
    
    for v in cpuSet.bits:
        if v != 0:
            break
    else:
        # No processors set
        return False

    result = sched_setaffinity(os.getpid(), sizeof(cpuSet), byref(cpuSet))
    if result == 0:
        return True
    
    return False
    
    # return ctypes.get_errno()


def getCpuAffinity():
    """
    Get affinity of current process as a list of all CPU numbers to which
    the process is assigned.
    
    May return None if something went wrong.
    """
    if sched_getaffinity is None:
        return False
        
    cpuCount = getCpuCount()

    result = []
    cpuSet = cpu_set_t()
    retval = sched_getaffinity(os.getpid(), sizeof(cpuSet), byref(cpuSet))
    if retval != 0:
        # Something went wrong
        return None

    for outer, mask in enumerate(cpuSet.bits):
        for inner in range(_NCPUBITS):
            cpu = outer * _NCPUBITS + inner
            if cpu > cpuCount:
                break

            if (mask & (1 << inner)) != 0:
                result.append(cpu)

    return result


def getCpuCount():
    """
    Returns number of CPUs allowed for the sequence list for setCpuAffinity().
    Highest number in sequence list must be lower than getCpuCount()
    
    The value is system dependent and may be lower than
    the number of available CPUs.
    
    If setting CPU affinity is not supported, function returns 0
    """
    if sched_setaffinity is None:
        return 0

    try:
        return min(_CPU_SETSIZE, multiprocessing.cpu_count())
    except NotImplementedError:
        return 0


