"""Launch an unattended CLI on a private desktop, including its descendants."""
from __future__ import annotations

import ctypes
from ctypes import wintypes as w
import msvcrt
import os
import subprocess
import uuid


class _StartupInfo(ctypes.Structure):
    _fields_ = [('cb', w.DWORD), ('reserved', w.LPWSTR), ('desktop', w.LPWSTR),
        ('title', w.LPWSTR), *[(n, w.DWORD) for n in
        ('x', 'y', 'width', 'height', 'xchars', 'ychars', 'fill', 'flags')],
        ('show', w.WORD), ('reserved_size', w.WORD), ('reserved_bytes', ctypes.c_void_p),
        ('stdin', w.HANDLE), ('stdout', w.HANDLE), ('stderr', w.HANDLE)]


class _StartupInfoEx(ctypes.Structure):
    _fields_ = [('info', _StartupInfo), ('attributes', ctypes.c_void_p)]


class _ProcessInfo(ctypes.Structure):
    _fields_ = [('process', w.HANDLE), ('thread', w.HANDLE), ('pid', w.DWORD), ('tid', w.DWORD)]


class DesktopCLIProcess:
    """Small Popen-compatible owner; only the three pipe handles are inherited."""

    def __init__(self, command, *, stdin, cwd, creationflags, env=None, **unused):
        self.command, self.returncode = command, None
        self._desktop = self._process = None
        self.stdout = self.stderr = None
        self._user = ctypes.WinDLL('user32', use_last_error=True)
        self._kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        u, k = self._user, self._kernel
        u.CreateDesktopW.argtypes = [w.LPCWSTR, w.LPCWSTR, ctypes.c_void_p, w.DWORD, w.DWORD, ctypes.c_void_p]
        u.CreateDesktopW.restype = w.HANDLE
        u.CloseDesktop.argtypes = [w.HANDLE]
        k.CloseHandle.argtypes = [w.HANDLE]
        k.InitializeProcThreadAttributeList.argtypes = [ctypes.c_void_p, w.DWORD, w.DWORD, ctypes.POINTER(ctypes.c_size_t)]
        k.UpdateProcThreadAttribute.argtypes = [ctypes.c_void_p, w.DWORD, ctypes.c_size_t,
            ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p]
        k.DeleteProcThreadAttributeList.argtypes = [ctypes.c_void_p]
        k.CreateProcessW.argtypes = [w.LPCWSTR, w.LPWSTR, ctypes.c_void_p, ctypes.c_void_p,
            w.BOOL, w.DWORD, ctypes.c_void_p, w.LPCWSTR, ctypes.POINTER(_StartupInfoEx), ctypes.POINTER(_ProcessInfo)]
        k.WaitForSingleObject.argtypes = [w.HANDLE, w.DWORD]
        k.WaitForSingleObject.restype = w.DWORD
        k.GetExitCodeProcess.argtypes = [w.HANDLE, ctypes.POINTER(w.DWORD)]
        k.TerminateProcess.argtypes = [w.HANDLE, w.UINT]
        writes, reads, attributes = [], [], None
        attributes_ready = False
        try:
            self.desktop_name = 'AGYBackground_' + uuid.uuid4().hex
            self._desktop = u.CreateDesktopW(self.desktop_name, None, None, 0, 0x1ff, None)
            if not self._desktop:
                raise ctypes.WinError(ctypes.get_last_error())
            # Duplicate stdin so its original ownership/inheritability stays unchanged.
            input_fd = os.dup(stdin.fileno())
            writes.append(input_fd)
            for _ in range(2):
                read, write = os.pipe()
                reads.append(read)
                writes.append(write)
            handles = (w.HANDLE * 3)(*[msvcrt.get_osfhandle(fd) for fd in writes])
            for handle in handles:
                os.set_handle_inheritable(handle, True)
            size = ctypes.c_size_t()
            k.InitializeProcThreadAttributeList(None, 1, 0, ctypes.byref(size))
            attributes = ctypes.create_string_buffer(size.value)
            if not k.InitializeProcThreadAttributeList(attributes, 1, 0, ctypes.byref(size)):
                raise ctypes.WinError(ctypes.get_last_error())
            attributes_ready = True
            if not k.UpdateProcThreadAttribute(attributes, 0, 0x20002, handles, ctypes.sizeof(handles), None, None):
                raise ctypes.WinError(ctypes.get_last_error())
            startup = _StartupInfoEx()
            startup.info.cb = ctypes.sizeof(startup)
            startup.info.desktop = self.desktop_name
            startup.info.flags = subprocess.STARTF_USESTDHANDLES | subprocess.STARTF_USESHOWWINDOW
            startup.info.show = subprocess.SW_HIDE
            startup.info.stdin, startup.info.stdout, startup.info.stderr = handles
            startup.attributes = ctypes.addressof(attributes)
            environment = env if env is not None else os.environ
            block = ctypes.create_unicode_buffer('\0'.join(f'{key}={value}' for key, value in
                sorted(environment.items(), key=lambda row: row[0].upper())) + '\0\0')
            info = _ProcessInfo()
            if not k.CreateProcessW(None, ctypes.create_unicode_buffer(subprocess.list2cmdline(command)),
                    None, None, True, creationflags | 0x80000 | 0x400, block, str(cwd),
                    ctypes.byref(startup), ctypes.byref(info)):
                raise ctypes.WinError(ctypes.get_last_error())
            self._process, self.pid = info.process, info.pid
            k.CloseHandle(info.thread)
            self.stdout = os.fdopen(reads.pop(0), 'rb', buffering=0)
            self.stderr = os.fdopen(reads.pop(0), 'rb', buffering=0)
        except Exception:
            if self._process:
                self.kill()
                self.wait(timeout=2)
            self.close()
            raise
        finally:
            if attributes_ready:
                k.DeleteProcThreadAttributeList(attributes)
            for fd in writes + reads:
                os.close(fd)

    def poll(self):
        if self.returncode is None and self._kernel.WaitForSingleObject(self._process, 0) == 0:
            code = w.DWORD()
            if not self._kernel.GetExitCodeProcess(self._process, ctypes.byref(code)):
                raise ctypes.WinError(ctypes.get_last_error())
            self.returncode = code.value
        return self.returncode

    def wait(self, timeout=None):
        result = self._kernel.WaitForSingleObject(self._process, 0xffffffff if timeout is None else int(timeout * 1000))
        if result == 0xffffffff:
            raise ctypes.WinError(ctypes.get_last_error())
        if result == 258:
            raise subprocess.TimeoutExpired(self.command, timeout)
        return self.poll()

    def kill(self):
        self._kernel.TerminateProcess(self._process, 1)

    def close(self):
        for stream in (self.stdout, self.stderr):
            if stream is not None:
                stream.close()
        if self._process:
            self._kernel.CloseHandle(self._process)
            self._process = None
        if self._desktop:
            self._user.CloseDesktop(self._desktop)
            self._desktop = None
