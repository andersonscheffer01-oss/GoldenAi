"""Process-wide ownership guard for the Golden/Jarvis Core."""

import ctypes
import os


_mutex_handle = None


def acquire_core_instance(name="Local\\GoldenAI.JarvisCore"):
    """Acquire the Windows Core mutex before any background service starts."""
    global _mutex_handle
    if _mutex_handle:
        return _mutex_handle
    if os.name != "nt":
        return True
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.CreateMutexW(None, False, name)
    if not handle:
        raise OSError(ctypes.get_last_error(), "CreateMutexW failed")
    if kernel32.GetLastError() == 183:
        kernel32.CloseHandle(handle)
        raise RuntimeError("another Golden/Jarvis Core process already owns the voice runtime")
    _mutex_handle = handle
    return handle
