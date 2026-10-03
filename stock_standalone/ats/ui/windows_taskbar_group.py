"""Assign the same taskbar identity to the console and all Qt windows."""

import ctypes
import logging
import uuid
from ctypes import wintypes


_APP_ID = "JohnsonQuantLab.ATS_Terminal"
_LOG = logging.getLogger(__name__)


class _GUID(ctypes.Structure):
    _fields_ = [("data1", wintypes.DWORD), ("data2", wintypes.WORD),
                ("data3", wintypes.WORD), ("data4", ctypes.c_ubyte * 8)]

    @classmethod
    def parse(cls, value):
        return cls.from_buffer_copy(uuid.UUID(value).bytes_le)


class _PROPERTYKEY(ctypes.Structure):
    _fields_ = [("fmtid", _GUID), ("pid", wintypes.DWORD)]


class _PROPVARIANT(ctypes.Structure):
    _fields_ = [("vt", wintypes.USHORT), ("reserved", wintypes.USHORT * 3),
                ("value", ctypes.c_wchar_p)]


def _set_window_app_id(hwnd, app_id):
    iid = _GUID.parse("886d8eeb-8cf2-4446-8d02-cdba1dbdcf99")
    key = _PROPERTYKEY(_GUID.parse("9f4c2855-9f79-4b39-a8d0-e1d42de1d5f3"), 5)
    store = ctypes.c_void_p()
    shell32 = ctypes.windll.shell32
    shell32.SHGetPropertyStoreForWindow.argtypes = (
        wintypes.HWND, ctypes.POINTER(_GUID), ctypes.POINTER(ctypes.c_void_p))
    shell32.SHGetPropertyStoreForWindow.restype = ctypes.HRESULT
    result = shell32.SHGetPropertyStoreForWindow(hwnd, ctypes.byref(iid), ctypes.byref(store))
    if result < 0:
        raise OSError(f"SHGetPropertyStoreForWindow failed: {result:#x}")
    try:
        vtable = ctypes.cast(store, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        set_value = ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p,
                                      ctypes.POINTER(_PROPERTYKEY), ctypes.POINTER(_PROPVARIANT))(vtable[6])
        value = _PROPVARIANT(31, (0, 0, 0), app_id)  # VT_LPWSTR
        result = set_value(store, ctypes.byref(key), ctypes.byref(value))
        if result < 0:
            raise OSError(f"IPropertyStore.SetValue failed: {result:#x}")
    finally:
        release = ctypes.WINFUNCTYPE(wintypes.ULONG, ctypes.c_void_p)(vtable[2])
        release(store)


def group_console_and_windows():
    """Set console and process IDs before QApplication creates any windows."""
    try:
        ctypes.windll.kernel32.GetConsoleWindow.restype = wintypes.HWND
        console_hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if not console_hwnd:
            return
        _set_window_app_id(console_hwnd, _APP_ID)
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID.argtypes = (wintypes.LPCWSTR,)
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID.restype = ctypes.HRESULT
        result = ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(_APP_ID)
        if result < 0:
            raise OSError(f"SetCurrentProcessExplicitAppUserModelID failed: {result:#x}")
    except (OSError, AttributeError, ValueError) as exc:
        _LOG.warning("ATS taskbar grouping unavailable: %s", exc)
