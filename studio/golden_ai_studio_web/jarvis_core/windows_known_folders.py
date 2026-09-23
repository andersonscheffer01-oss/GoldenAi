"""Small Windows Known Folder bridge used by Computer Use missions."""
from __future__ import annotations

import ctypes
import os
from pathlib import Path


FOLDERID_DOCUMENTS = "{FDD39AD0-238F-46AF-ADB4-6C85480369C7}"


class _GUID(ctypes.Structure):
    _fields_ = [
        ("data1", ctypes.c_ulong),
        ("data2", ctypes.c_ushort),
        ("data3", ctypes.c_ushort),
        ("data4", ctypes.c_ubyte * 8),
    ]


def documents_dir() -> Path:
    """Return the user's real Documents folder, including shell redirection."""
    if os.name != "nt":
        return Path.home() / "Documents"

    shell32 = ctypes.windll.shell32
    ole32 = ctypes.windll.ole32
    known_folder_id = _GUID(
        0xFDD39AD0, 0x238F, 0x46AF,
        (ctypes.c_ubyte * 8)(0xAD, 0xB4, 0x6C, 0x85, 0x48, 0x03, 0x69, 0xC7))
    path_ptr = ctypes.c_wchar_p()
    shell32.SHGetKnownFolderPath.argtypes = [
        ctypes.POINTER(_GUID), ctypes.c_uint32, ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_wchar_p)]
    shell32.SHGetKnownFolderPath.restype = ctypes.c_long
    result = shell32.SHGetKnownFolderPath(
        ctypes.byref(known_folder_id), 0, None, ctypes.byref(path_ptr))
    if result != 0 or not path_ptr.value:
        raise OSError(result, "SHGetKnownFolderPath(Documents) failed")
    try:
        return Path(path_ptr.value)
    finally:
        ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]
        ole32.CoTaskMemFree(path_ptr)


__all__ = ["documents_dir", "FOLDERID_DOCUMENTS"]
