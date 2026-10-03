# -*- coding: utf-8 -*-
"""Safe Windows directory migration with post-copy verification."""

import ctypes
import hashlib
import os
import shutil
import stat
import struct
import tempfile
import time
import uuid
from dataclasses import dataclass, field


FILE_ATTRIBUTE_READONLY = 0x00000001
FILE_ATTRIBUTE_HIDDEN = 0x00000002
FILE_ATTRIBUTE_SYSTEM = 0x00000004
FILE_ATTRIBUTE_DIRECTORY = 0x00000010
FILE_ATTRIBUTE_ARCHIVE = 0x00000020
FILE_ATTRIBUTE_REPARSE_POINT = 0x00000400
FILE_ATTRIBUTE_COMPRESSED = 0x00000800
FILE_ATTRIBUTE_OFFLINE = 0x00001000
FILE_ATTRIBUTE_NOT_CONTENT_INDEXED = 0x00002000
FILE_ATTRIBUTE_ENCRYPTED = 0x00004000
FILE_ATTRIBUTE_SPARSE_FILE = 0x00000200

IO_REPARSE_TAG_MOUNT_POINT = 0xA0000003
IO_REPARSE_TAG_SYMLINK = 0xA000000C
COPYABLE_ATTRIBUTES = (
    FILE_ATTRIBUTE_READONLY
    | FILE_ATTRIBUTE_HIDDEN
    | FILE_ATTRIBUTE_SYSTEM
    | FILE_ATTRIBUTE_ARCHIVE
    | FILE_ATTRIBUTE_NOT_CONTENT_INDEXED
)
UNSUPPORTED_STORAGE_ATTRIBUTES = (
    FILE_ATTRIBUTE_COMPRESSED
    | FILE_ATTRIBUTE_OFFLINE
    | FILE_ATTRIBUTE_ENCRYPTED
    | FILE_ATTRIBUTE_SPARSE_FILE
)


class MigrationError(RuntimeError):
    """An expected migration or safety error."""


class MigrationCancelled(MigrationError):
    """Raised when a user cancels before the cutover starts."""


class UnsupportedEntryError(MigrationError):
    """Raised when an entry cannot be copied without changing its behavior."""


class TreeMismatchError(MigrationError):
    """Raised when source and destination inventories differ."""


class SourceInUseError(MigrationError):
    """Raised when another process is using a resource in the source tree."""


class _RmFileTime(ctypes.Structure):
    _fields_ = [("low", ctypes.c_uint32), ("high", ctypes.c_uint32)]


class _RmUniqueProcess(ctypes.Structure):
    _fields_ = [("process_id", ctypes.c_uint32), ("start_time", _RmFileTime)]


class _RmProcessInfo(ctypes.Structure):
    _fields_ = [
        ("process", _RmUniqueProcess),
        ("app_name", ctypes.c_wchar * 256),
        ("service_name", ctypes.c_wchar * 64),
        ("app_type", ctypes.c_int),
        ("app_status", ctypes.c_uint32),
        ("session_id", ctypes.c_uint32),
        ("restartable", ctypes.c_int),
    ]


class _Win32FindStreamData(ctypes.Structure):
    _fields_ = [
        ("stream_size", ctypes.c_longlong),
        ("stream_name", ctypes.c_wchar * 296),
    ]


@dataclass(frozen=True)
class TreeEntry:
    relative_path: str
    kind: str
    size: int = 0
    sha256: str = ""
    mtime_ns: int = 0
    mode: int = 0
    attributes: int = 0
    link_semantic: str = ""
    raw_link_target: str = ""
    target_is_directory: bool = False
    hardlink_group: str = ""


@dataclass
class TreeInventory:
    root: str
    entries: dict = field(default_factory=dict)
    total_bytes: int = 0

    @property
    def file_count(self):
        return sum(entry.kind == "file" for entry in self.entries.values())

    @property
    def directory_count(self):
        return sum(entry.kind == "directory" for entry in self.entries.values())

    @property
    def link_count(self):
        return sum(entry.kind in ("symlink", "junction") for entry in self.entries.values())


@dataclass
class MigrationResult:
    source: str
    destination: str
    backup: str
    inventory: TreeInventory
    backup_cleaned: bool
    cleanup_error: str = ""


def _emit(progress, stage, **values):
    if progress is not None:
        event = {"stage": stage}
        event.update(values)
        progress(event)


def _check_cancel(cancel_event):
    if cancel_event is not None and cancel_event.is_set():
        raise MigrationCancelled("操作已取消；原目录尚未切换。")


def _absolute(path):
    path = os.path.normpath(
        os.path.abspath(os.path.expanduser(os.fspath(path)))
    )
    if os.name == "nt":
        lowered = path.lower()
        if lowered.startswith("\\\\?\\unc\\"):
            path = "\\\\" + path[8:]
        elif lowered.startswith("\\??\\unc\\"):
            path = "\\\\" + path[8:]
        elif lowered.startswith("\\??\\"):
            path = path[4:]
        elif lowered.startswith("\\\\?\\") and not lowered.startswith(
            "\\\\?\\volume{"
        ):
            path = path[4:]
    return os.path.normpath(path)


def _normal_case(path):
    return os.path.normcase(os.path.normpath(path))


def _path_is_within(path, root):
    try:
        return _normal_case(os.path.commonpath([path, root])) == _normal_case(root)
    except (ValueError, OSError):
        return False


def _relative_name(path):
    return path.replace(os.sep, "/").replace("\\", "/")


def _join_relative(root, relative):
    return os.path.join(root, *relative.split("/")) if relative else root


def _is_junction(path):
    checker = getattr(os.path, "isjunction", None)
    if checker is not None:
        try:
            if checker(path):
                return True
        except OSError:
            pass
    if os.name == "nt":
        try:
            return (
                getattr(os.lstat(path), "st_reparse_tag", 0)
                == IO_REPARSE_TAG_MOUNT_POINT
            )
        except OSError:
            return False
    return False


def _reparse_kind(path, file_stat):
    if _is_junction(path):
        return "junction"
    if os.path.islink(path):
        return "symlink"

    attributes = getattr(file_stat, "st_file_attributes", 0)
    if not attributes & FILE_ATTRIBUTE_REPARSE_POINT:
        return ""

    tag = getattr(file_stat, "st_reparse_tag", 0)
    if tag == IO_REPARSE_TAG_SYMLINK:
        return "symlink"
    if tag == IO_REPARSE_TAG_MOUNT_POINT:
        return "junction"
    raise UnsupportedEntryError(
        "发现不支持的重解析点，已停止以避免复制或清理其指向的数据：{}".format(path)
    )


def _resolved_link_target(path, raw_target):
    if os.path.isabs(raw_target):
        return _absolute(raw_target)
    return _absolute(os.path.join(os.path.dirname(path), raw_target))


def _link_semantic(path, raw_target, internal_roots):
    resolved = _resolved_link_target(path, raw_target)
    for root in internal_roots:
        root = _absolute(root)
        if _path_is_within(resolved, root):
            relative = os.path.relpath(resolved, root)
            return "inside:" + _relative_name(relative if relative != "." else "")
    return "outside:" + resolved


def _target_is_directory(path, raw_target):
    try:
        if os.path.isdir(path):
            return True
        if os.path.isdir(_resolved_link_target(path, raw_target)):
            return True
        entry_stat = os.lstat(path)
        return bool(getattr(entry_stat, "st_file_attributes", 0) & FILE_ATTRIBUTE_DIRECTORY)
    except OSError:
        return False


def _sha256_file(path, progress=None, cancel_event=None, path_label=""):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        while True:
            _check_cancel(cancel_event)
            chunk = stream.read(4 * 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            _emit(progress, "hash", path=path_label, bytes=len(chunk))
    return digest.hexdigest()


def _iter_source_resources(source, cancel_event=None, directory_callback=None):
    pending = [source]
    while pending:
        _check_cancel(cancel_event)
        current = pending.pop()
        if directory_callback is not None:
            directory_callback(current)
        try:
            with os.scandir(current) as iterator:
                directories = []
                for child in iterator:
                    _check_cancel(cancel_event)
                    try:
                        child_stat = os.lstat(child.path)
                        kind = _reparse_kind(child.path, child_stat)
                    except OSError as exc:
                        raise MigrationError(
                            "无法检查源目录占用：{} ({})".format(child.path, exc)
                        )
                    if kind:
                        continue
                    if stat.S_ISDIR(child_stat.st_mode):
                        directories.append(child.path)
                    elif stat.S_ISREG(child_stat.st_mode):
                        yield child.path
        except OSError as exc:
            raise MigrationError("无法检查源目录占用：{} ({})".format(current, exc))
        pending.extend(directories)


def _restart_manager_processes(get_list, session_id):
    needed = ctypes.c_uint32()
    count = ctypes.c_uint32()
    reboot_reasons = ctypes.c_uint32()
    status = get_list(
        session_id, ctypes.byref(needed), ctypes.byref(count), None,
        ctypes.byref(reboot_reasons),
    )
    if status == 0:
        return []
    if status != 234:
        raise MigrationError(
            "无法读取源目录占用进程：{}".format(ctypes.WinError(status))
        )

    for _ in range(5):
        count = ctypes.c_uint32(max(needed.value, 1))
        processes = (_RmProcessInfo * count.value)()
        status = get_list(
            session_id, ctypes.byref(needed), ctypes.byref(count),
            processes, ctypes.byref(reboot_reasons),
        )
        if status == 0:
            occupants = {}
            for process in processes[:count.value]:
                pid = int(process.process.process_id)
                name = process.app_name.strip() or process.service_name.strip()
                if not name:
                    name = "未知进程"
                key = (
                    pid,
                    int(process.process.start_time.high),
                    int(process.process.start_time.low),
                )
                occupants[key] = {"pid": pid, "name": name}
            return sorted(
                occupants.values(),
                key=lambda item: (item["name"].casefold(), item["pid"]),
            )
        if status != 234:
            raise MigrationError(
                "无法读取源目录占用进程：{}".format(ctypes.WinError(status))
            )
    raise MigrationError("占用进程变化过快，请重新检测。")


def _restart_manager_occupants(resource_paths, progress=None, cancel_event=None):
    restart_manager = ctypes.WinDLL("Rstrtmgr", use_last_error=True)
    start_session = restart_manager.RmStartSession
    start_session.argtypes = [
        ctypes.POINTER(ctypes.c_uint32), ctypes.c_uint32, ctypes.c_wchar_p
    ]
    start_session.restype = ctypes.c_uint32
    register_resources = restart_manager.RmRegisterResources
    register_resources.argtypes = [
        ctypes.c_uint32, ctypes.c_uint32,
        ctypes.POINTER(ctypes.c_wchar_p), ctypes.c_uint32, ctypes.c_void_p,
        ctypes.c_uint32, ctypes.c_void_p,
    ]
    register_resources.restype = ctypes.c_uint32
    get_list = restart_manager.RmGetList
    get_list.argtypes = [
        ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint32),
        ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(_RmProcessInfo),
        ctypes.POINTER(ctypes.c_uint32),
    ]
    get_list.restype = ctypes.c_uint32
    end_session = restart_manager.RmEndSession
    end_session.argtypes = [ctypes.c_uint32]
    end_session.restype = ctypes.c_uint32

    session = ctypes.c_uint32()
    session_key = ctypes.create_unicode_buffer(uuid.uuid4().hex, 33)
    status = start_session(ctypes.byref(session), 0, session_key)
    if status:
        raise MigrationError(
            "无法启动 Windows 占用检测：{}".format(ctypes.WinError(status))
        )

    try:
        batch = []
        registered = 0

        def register_batch(paths):
            nonlocal registered
            array_type = ctypes.c_wchar_p * len(paths)
            file_names = array_type(*paths)
            result = register_resources(
                session.value, len(paths), file_names, 0, None, 0, None
            )
            if result:
                raise MigrationError(
                    "无法登记源目录资源进行占用检测：{}".format(
                        ctypes.WinError(result)
                    )
                )
            registered += len(paths)
            _emit(
                progress, "check_occupants", checked=registered,
                path=paths[-1],
            )
            return _restart_manager_processes(get_list, session.value)

        for resource_path in resource_paths:
            _check_cancel(cancel_event)
            batch.append(resource_path)
            if len(batch) >= 256:
                occupants = register_batch(batch)
                if occupants:
                    return occupants
                batch = []
        if batch:
            occupants = register_batch(batch)
            if occupants:
                return occupants
        if registered == 0:
            return []

        return []
    finally:
        end_session(session.value)


def _check_source_rename_access(source, progress=None, cancel_event=None,
                                check_permissions=True):
    """Check rename rights and directory-handle sharing without moving source."""
    if os.name != "nt":
        return
    _check_cancel(cancel_event)
    source = _absolute(source)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = [
        ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p,
        ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p,
    ]
    create_file.restype = ctypes.c_void_p
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = [ctypes.c_void_p]
    close_handle.restype = ctypes.c_int

    invalid_handle = ctypes.c_void_p(-1).value
    share_all = 0x1 | 0x2 | 0x4
    open_existing = 3
    backup_semantics = 0x02000000

    def try_open_directory(path, desired_access):
        ctypes.set_last_error(0)
        handle = create_file(
            path, desired_access, share_all, None, open_existing,
            backup_semantics, None,
        )
        if handle == invalid_handle:
            return ctypes.get_last_error()
        if not close_handle(handle):
            return ctypes.get_last_error() or 1
        return 0

    # A DELETE-access open detects both missing rename rights and directory
    # handles opened without FILE_SHARE_DELETE (for example, a terminal cwd).
    error_code = try_open_directory(source, 0x00010000)  # DELETE
    if error_code == 0:
        return

    if error_code == 32:  # ERROR_SHARING_VIOLATION
        occupants = []
        try:
            occupants = _restart_manager_occupants(
                [source], progress=progress, cancel_event=cancel_event
            )
        except Exception:
            pass
        if occupants:
            raise SourceInUseError(
                "检测到占用源目录或其子目录的程序，无法安全重命名：\n{}".format(
                    format_source_occupants(occupants)
                )
            )
        raise SourceInUseError(
            "目录正被程序以目录句柄打开，Windows 拒绝重命名（WinError 32）：{}。"
            "占用检测未能定位具体进程；请关闭打开该目录的资源管理器窗口、"
            "终端或编辑器后重试。".format(source)
        )

    if error_code == 5:  # ERROR_ACCESS_DENIED
        if not check_permissions:
            return
        parent = os.path.dirname(source)
        parent_error = try_open_directory(parent, 0x40)  # FILE_DELETE_CHILD
        if parent_error == 0:
            return
        if parent_error == 32:
            raise SourceInUseError(
                "源目录或其父目录被程序以目录句柄打开，无法安全重命名。"
                "请关闭打开该位置的资源管理器窗口、终端或编辑器后重试：{}".format(
                    source
                )
            )
        raise MigrationError(
            "当前账户无法取得重命名源目录所需的 DELETE 权限，且父目录的 "
            "DELETE_CHILD 权限检查也失败；迁移已在复制前停止。"
            "请检查源目录和父目录权限，或安全软件的拦截：{} ({})".format(
                source, ctypes.WinError(parent_error)
            )
        )

    raise MigrationError(
        "无法检查源目录的重命名权限，迁移已停止：{} ({})".format(
            source, ctypes.WinError(error_code)
        )
    )


def find_source_occupants(source, progress=None, cancel_event=None,
                          inventory=None):
    """Check rename-blocking directory handles and processes using source files."""
    if os.name != "nt":
        raise MigrationError("源目录占用检测只支持 Windows。")
    source = _absolute(source)
    if not os.path.isdir(source):
        raise MigrationError("源目录不存在或不可访问：{}".format(source))
    if _reparse_kind(source, os.lstat(source)):
        raise MigrationError("占用检测要求选择实际源目录，不能选择链接目录。")
    _emit(progress, "check_occupants", path=source)
    _check_source_rename_access(source, progress, cancel_event)
    directories_checked = 0

    def check_directory_handle(path):
        nonlocal directories_checked
        if _normal_case(path) == _normal_case(source):
            return
        _check_source_rename_access(
            path, progress, cancel_event, check_permissions=False
        )
        directories_checked += 1
        if directories_checked % 64 == 0:
            _emit(progress, "check_occupants", path=path)

    if inventory is None:
        resource_paths = _iter_source_resources(
            source, cancel_event, directory_callback=check_directory_handle
        )
    else:
        for entry in inventory.entries.values():
            if entry.kind == "directory" and entry.relative_path:
                check_directory_handle(
                    _join_relative(source, entry.relative_path)
                )
        resource_paths = (
            _join_relative(source, entry.relative_path)
            for entry in inventory.entries.values()
            if entry.kind == "file"
        )
    return _restart_manager_occupants(
        resource_paths, progress=progress, cancel_event=cancel_event
    )


def format_source_occupants(occupants):
    return "\n".join(
        "  • {} (PID {})".format(item["name"], item["pid"])
        for item in occupants
    )


def _alternate_data_streams(path):
    if os.name != "nt":
        return []
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    find_first = kernel32.FindFirstStreamW
    find_first.argtypes = [
        ctypes.c_wchar_p, ctypes.c_int, ctypes.POINTER(_Win32FindStreamData),
        ctypes.c_uint,
    ]
    find_first.restype = ctypes.c_void_p
    find_next = kernel32.FindNextStreamW
    find_next.argtypes = [ctypes.c_void_p, ctypes.POINTER(_Win32FindStreamData)]
    find_next.restype = ctypes.c_int
    find_close = kernel32.FindClose
    find_close.argtypes = [ctypes.c_void_p]
    find_close.restype = ctypes.c_int

    data = _Win32FindStreamData()
    handle = find_first(path, 0, ctypes.byref(data), 0)
    if handle == ctypes.c_void_p(-1).value:
        error_code = ctypes.get_last_error()
        if error_code == 38:
            return []
        raise MigrationError(
            "无法检查 NTFS 备用数据流，已停止迁移：{} ({})".format(
                path, ctypes.WinError(error_code)
            )
        )

    streams = []
    try:
        while True:
            stream_name = data.stream_name
            if stream_name.casefold() != "::$data":
                streams.append(stream_name)
            if find_next(handle, ctypes.byref(data)):
                continue
            error_code = ctypes.get_last_error()
            if error_code not in (18, 38):
                raise MigrationError(
                    "枚举 NTFS 备用数据流失败，已停止迁移：{} ({})".format(
                        path, ctypes.WinError(error_code)
                    )
                )
            break
    finally:
        find_close(handle)
    return streams


def inspect_tree(root, progress=None, cancel_event=None, internal_roots=None):
    """Inventory content without following symlinks, junctions, or mount points."""
    root = _absolute(root)
    if not os.path.isdir(root):
        raise MigrationError("源目录不存在或不可访问：{}".format(root))

    internal_roots = list(internal_roots or [])
    internal_roots.insert(0, root)
    inventory = TreeInventory(root=root)
    root_stat = os.lstat(root)
    if _reparse_kind(root, root_stat):
        raise MigrationError("所选根目录是重解析点，请选择实际数据目录。")
    inventory.entries[""] = TreeEntry(
        relative_path="",
        kind="directory",
        mtime_ns=root_stat.st_mtime_ns,
        mode=stat.S_IMODE(root_stat.st_mode),
        attributes=getattr(root_stat, "st_file_attributes", 0) & COPYABLE_ATTRIBUTES,
    )
    hardlinks = {}
    pending = [root]
    scanned = 0

    while pending:
        _check_cancel(cancel_event)
        current = pending.pop()
        try:
            with os.scandir(current) as entries:
                children = sorted(entries, key=lambda item: item.name.casefold())
        except OSError as exc:
            raise MigrationError("无法读取目录 {}：{}".format(current, exc))

        directories = []
        for child in children:
            _check_cancel(cancel_event)
            path = child.path
            relative = _relative_name(os.path.relpath(path, root))
            try:
                item_stat = os.lstat(path)
                kind = _reparse_kind(path, item_stat)
            except OSError as exc:
                raise MigrationError("无法读取文件信息 {}：{}".format(path, exc))

            attributes = getattr(item_stat, "st_file_attributes", 0)
            if attributes & UNSUPPORTED_STORAGE_ATTRIBUTES:
                raise UnsupportedEntryError(
                    "发现压缩、脱机、EFS 加密或稀疏文件，当前无法保证其存储属性一致：{}".format(path)
                )

            if kind:
                try:
                    raw_target = os.readlink(path)
                except OSError as exc:
                    raise MigrationError("无法读取链接目标 {}：{}".format(path, exc))
                target_is_dir = kind == "junction" or _target_is_directory(path, raw_target)
                resolved = _resolved_link_target(path, raw_target)
                if kind == "junction" and not os.path.isdir(resolved):
                    raise UnsupportedEntryError(
                        "发现目标已失效的目录联接，已停止迁移：{} -> {}".format(path, raw_target)
                    )
                inventory.entries[relative] = TreeEntry(
                    relative_path=relative,
                    kind=kind,
                    mode=stat.S_IMODE(item_stat.st_mode),
                    link_semantic=_link_semantic(path, raw_target, internal_roots),
                    raw_link_target=raw_target,
                    target_is_directory=target_is_dir,
                )
            elif stat.S_ISDIR(item_stat.st_mode):
                inventory.entries[relative] = TreeEntry(
                    relative_path=relative,
                    kind="directory",
                    mtime_ns=item_stat.st_mtime_ns,
                    mode=stat.S_IMODE(item_stat.st_mode),
                    attributes=attributes & COPYABLE_ATTRIBUTES,
                )
                directories.append(path)
            elif stat.S_ISREG(item_stat.st_mode):
                # Windows DirEntry.stat(follow_symlinks=False) may return
                # zero for st_ino/st_nlink on ordinary files. The path was
                # already classified as a non-reparse regular file above.
                try:
                    item_stat = os.stat(path, follow_symlinks=True)
                except OSError as exc:
                    raise MigrationError("无法读取文件信息 {}：{}".format(path, exc))
                if not stat.S_ISREG(item_stat.st_mode):
                    raise MigrationError(
                        "扫描期间文件类型发生变化，请关闭相关程序后重试：{}".format(path)
                    )
                streams = _alternate_data_streams(path)
                if streams:
                    raise UnsupportedEntryError(
                        "发现未支持的 NTFS 备用数据流，已停止以避免遗漏：{} ({})".format(
                            path, ", ".join(streams)
                        )
                    )
                if getattr(item_stat, "st_nlink", 1) > 1:
                    identity = (item_stat.st_dev, item_stat.st_ino)
                    hardlinks.setdefault(identity, []).append(
                        (relative, int(item_stat.st_nlink))
                    )
                digest = _sha256_file(
                    path, progress, cancel_event, relative
                )
                inventory.entries[relative] = TreeEntry(
                    relative_path=relative,
                    kind="file",
                    size=item_stat.st_size,
                    sha256=digest,
                    mtime_ns=item_stat.st_mtime_ns,
                    mode=stat.S_IMODE(item_stat.st_mode),
                    attributes=attributes & COPYABLE_ATTRIBUTES,
                )
                inventory.total_bytes += item_stat.st_size
                scanned += 1
                _emit(
                    progress,
                    "scan",
                    current=scanned,
                    path=relative,
                    bytes=inventory.total_bytes,
                )
            else:
                raise UnsupportedEntryError(
                    "发现不支持的特殊文件，已停止迁移：{}".format(path)
                )

        pending.extend(reversed(directories))

    for identity, members in hardlinks.items():
        relative_names = sorted(member[0] for member in members)
        link_count = members[0][1]
        if link_count > len(relative_names):
            raise UnsupportedEntryError(
                "发现指向所选目录以外的硬链接，无法保证迁移后链接关系一致：{}".format(
                    relative_names[0]
                )
            )
        if len(relative_names) > 1:
            group = "\n".join(relative_names)
            for relative in relative_names:
                inventory.entries[relative] = TreeEntry(
                    **dict(
                        inventory.entries[relative].__dict__,
                        hardlink_group=group,
                    )
                )
    return inventory


def compare_inventories(expected, actual):
    expected_paths = set(expected.entries)
    actual_paths = set(actual.entries)
    differences = []

    for relative in sorted(expected_paths - actual_paths):
        differences.append("目标缺少：{}".format(relative))
    for relative in sorted(actual_paths - expected_paths):
        differences.append("目标多出：{}".format(relative))
    for relative in sorted(expected_paths & actual_paths):
        left = expected.entries[relative]
        right = actual.entries[relative]
        fields = ("kind", "size", "sha256", "mtime_ns", "mode", "attributes",
                  "link_semantic", "target_is_directory", "hardlink_group")
        if left.kind in ("symlink", "junction"):
            fields = ("kind", "link_semantic", "target_is_directory")
        for field_name in fields:
            if getattr(left, field_name) != getattr(right, field_name):
                differences.append(
                    "{} 的 {} 不一致".format(relative, field_name)
                )
                break
        if len(differences) >= 30:
            differences.append("差异过多，已停止列出。")
            break

    if differences:
        raise TreeMismatchError(
            "两边核对未通过：\n" + "\n".join(differences)
        )
    return {
        "entry_count": len(expected.entries),
        "file_count": expected.file_count,
        "directory_count": expected.directory_count,
        "link_count": expected.link_count,
        "bytes": expected.total_bytes,
    }


def validate_paths(source, destination):
    source = _absolute(source)
    destination = _absolute(destination)
    if not os.path.isdir(source):
        raise MigrationError("源目录不存在：{}".format(source))
    if _reparse_kind(source, os.lstat(source)):
        raise MigrationError("源目录本身已经是链接，请选择实际数据目录。")
    if os.path.abspath(os.path.dirname(source)) == source:
        raise MigrationError("不能迁移磁盘根目录。")
    if os.path.lexists(destination):
        raise MigrationError("目标目录已存在。为避免覆盖，目标必须是尚未创建的目录：{}".format(destination))
    parent = os.path.dirname(destination)
    if not os.path.isdir(parent):
        raise MigrationError("目标父目录必须先存在：{}".format(parent))
    if _path_is_within(destination, source):
        raise MigrationError("目标不能位于源目录内部。")
    if _path_is_within(source, destination):
        raise MigrationError("目标不能是源目录的上级目录。")
    if _path_is_within(parent, source):
        raise MigrationError("目标父目录不能位于源目录内部。")
    source_resolved = _normal_case(os.path.realpath(source))
    destination_resolved = _normal_case(os.path.realpath(destination))
    if (
        source_resolved == destination_resolved
        or _path_is_within(destination_resolved, source_resolved)
        or _path_is_within(source_resolved, destination_resolved)
    ):
        raise MigrationError("源目录和目标路径经链接解析后发生重叠。")
    if _normal_case(source) == _normal_case(destination):
        raise MigrationError("源目录和目标目录不能相同。")
    return source, destination


def _windows_filesystem(path):
    if os.name != "nt":
        raise MigrationError("目录联接迁移工具只支持 Windows。")
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    requested_path = _absolute(path)
    volume_path = ctypes.create_unicode_buffer(32768)
    get_volume_path = kernel32.GetVolumePathNameW
    get_volume_path.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint]
    get_volume_path.restype = ctypes.c_int
    if get_volume_path(requested_path, volume_path, len(volume_path)):
        volume_mount_path = volume_path.value
        volume_query_path = volume_mount_path
    else:
        volume_path_error = ctypes.get_last_error()
        drive, _ = os.path.splitdrive(requested_path)
        if not drive or volume_path_error != 1:  # ERROR_INVALID_FUNCTION
            raise ctypes.WinError(volume_path_error)
        # Some RAM-disk drivers do not implement GetVolumePathNameW even
        # though normal volume queries work when addressed by drive root.
        volume_mount_path = drive + os.sep
        volume_query_path = volume_mount_path
    volume_name = ctypes.create_unicode_buffer(32768)
    get_volume_name = kernel32.GetVolumeNameForVolumeMountPointW
    get_volume_name.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint]
    get_volume_name.restype = ctypes.c_int
    if get_volume_name(volume_mount_path, volume_name, len(volume_name)):
        volume_query_path = volume_name.value
    else:
        drive, _ = os.path.splitdrive(requested_path)
        if drive:
            volume_query_path = drive + os.sep
    fs_name = ctypes.create_unicode_buffer(64)
    get_volume_info = kernel32.GetVolumeInformationW
    get_volume_info.argtypes = [
        ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint,
        ctypes.POINTER(ctypes.c_uint), ctypes.POINTER(ctypes.c_uint),
        ctypes.POINTER(ctypes.c_uint), ctypes.c_wchar_p, ctypes.c_uint,
    ]
    get_volume_info.restype = ctypes.c_int
    serial = ctypes.c_uint()
    max_component = ctypes.c_uint()
    flags = ctypes.c_uint()
    if not get_volume_info(
        volume_query_path, None, 0, ctypes.byref(serial),
        ctypes.byref(max_component), ctypes.byref(flags),
        fs_name, len(fs_name),
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    return fs_name.value.upper()


def _create_junction(link_path, target_path):
    if os.name != "nt":
        raise MigrationError("当前系统不能创建 Windows 目录联接。")
    if os.path.lexists(link_path):
        raise MigrationError("联接路径已存在：{}".format(link_path))
    if not os.path.isdir(target_path):
        raise MigrationError("目录联接目标不存在：{}".format(target_path))
    target_path = _absolute(target_path)
    lowered_target = target_path.lower()
    if lowered_target.startswith("\\\\?\\unc\\"):
        substitute_path = "\\??\\UNC\\" + target_path[8:]
    elif lowered_target.startswith("\\\\?\\volume{"):
        substitute_path = "\\??\\" + target_path[4:]
    elif target_path.startswith("\\\\"):
        substitute_path = "\\??\\UNC\\" + target_path.lstrip("\\")
    else:
        substitute_path = "\\??\\" + target_path
    substitute_bytes = substitute_path.encode("utf-16le")
    print_bytes = target_path.encode("utf-16le")
    path_buffer = substitute_bytes + b"\0\0" + print_bytes + b"\0\0"
    data_length = 8 + len(path_buffer)
    if data_length > 16 * 1024:
        raise MigrationError("目录联接目标路径超过 Windows 重解析点长度限制。")
    reparse_data = struct.pack(
        "<IHHHHHH",
        IO_REPARSE_TAG_MOUNT_POINT,
        data_length,
        0,
        0,
        len(substitute_bytes),
        len(substitute_bytes) + 2,
        len(print_bytes),
    ) + path_buffer

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = [
        ctypes.c_wchar_p, ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p,
        ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p,
    ]
    create_file.restype = ctypes.c_void_p
    device_io_control = kernel32.DeviceIoControl
    device_io_control.argtypes = [
        ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_uint,
        ctypes.c_void_p, ctypes.c_uint, ctypes.POINTER(ctypes.c_uint),
        ctypes.c_void_p,
    ]
    device_io_control.restype = ctypes.c_int
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = [ctypes.c_void_p]
    close_handle.restype = ctypes.c_int

    os.mkdir(link_path)
    handle = create_file(
        link_path,
        0x40000000,
        0x00000001 | 0x00000002 | 0x00000004,
        None,
        3,
        0x00200000 | 0x02000000,
        None,
    )
    invalid_handle = ctypes.c_void_p(-1).value
    if handle == invalid_handle:
        error_code = ctypes.get_last_error()
        os.rmdir(link_path)
        raise ctypes.WinError(error_code)

    input_buffer = ctypes.create_string_buffer(reparse_data)
    bytes_returned = ctypes.c_uint()
    try:
        success = device_io_control(
            handle,
            0x000900A4,
            input_buffer,
            len(reparse_data),
            None,
            0,
            ctypes.byref(bytes_returned),
            None,
        )
        error_code = 0 if success else ctypes.get_last_error()
    finally:
        close_handle(handle)
    if error_code:
        os.rmdir(link_path)
        raise ctypes.WinError(error_code)
    if not _is_junction(link_path) or not os.path.samefile(link_path, target_path):
        os.rmdir(link_path)
        raise MigrationError("Windows 未能确认新建目录联接的类型和目标。")


def _is_reparse_point(path):
    try:
        file_stat = os.lstat(path)
    except OSError:
        return False
    return bool(
        getattr(file_stat, "st_file_attributes", 0)
        & FILE_ATTRIBUTE_REPARSE_POINT
    ) or os.path.islink(path) or _is_junction(path)


def _remove_path_no_follow(path):
    """Remove a tree without ever traversing a symbolic link or junction."""
    try:
        item_stat = os.lstat(path)
    except FileNotFoundError:
        return

    reparse_kind = _reparse_kind(path, item_stat)
    if reparse_kind:
        if reparse_kind == "junction" or stat.S_ISDIR(item_stat.st_mode):
            os.rmdir(path)
        else:
            os.unlink(path)
        return

    if stat.S_ISDIR(item_stat.st_mode):
        with os.scandir(path) as children:
            child_paths = [child.path for child in children]
        for child_path in child_paths:
            _remove_path_no_follow(child_path)
        try:
            os.chmod(path, stat.S_IREAD | stat.S_IWRITE | stat.S_IEXEC)
        except OSError:
            pass
        os.rmdir(path)
        return

    try:
        os.chmod(path, stat.S_IREAD | stat.S_IWRITE)
    except OSError:
        pass
    os.unlink(path)


def _create_symlink(source_path, link_path, staging_root, final_root, entry):
    if entry.link_semantic.startswith("inside:"):
        relative_target = entry.link_semantic[len("inside:"):]
        staging_target = _join_relative(staging_root, relative_target)
        target = os.path.relpath(staging_target, os.path.dirname(link_path))
    else:
        target = entry.link_semantic[len("outside:"):]
    os.symlink(
        target,
        link_path,
        target_is_directory=entry.target_is_directory,
    )


def _create_copied_junction(source_path, link_path, staging_root, entry):
    if entry.link_semantic.startswith("inside:"):
        relative_target = entry.link_semantic[len("inside:"):]
        target = _join_relative(staging_root, relative_target)
    else:
        target = _resolved_link_target(source_path, entry.raw_link_target)
    _create_junction(link_path, target)


def _copy_tree(source, staging, final_destination, inventory,
               progress=None, cancel_event=None):
    os.mkdir(staging)
    directories = sorted(
        (entry for entry in inventory.entries.values()
         if entry.kind == "directory" and entry.relative_path),
        key=lambda entry: (entry.relative_path.count("/"), entry.relative_path),
    )
    for entry in directories:
        _check_cancel(cancel_event)
        os.mkdir(_join_relative(staging, entry.relative_path))

    regular_files = sorted(
        (entry for entry in inventory.entries.values() if entry.kind == "file"),
        key=lambda entry: entry.relative_path,
    )
    hardlink_first = {}
    bytes_done = 0
    for number, entry in enumerate(regular_files, 1):
        _check_cancel(cancel_event)
        source_path = _join_relative(source, entry.relative_path)
        dest_path = _join_relative(staging, entry.relative_path)
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        if entry.hardlink_group and entry.hardlink_group in hardlink_first:
            os.link(hardlink_first[entry.hardlink_group], dest_path)
        else:
            with open(source_path, "rb") as source_stream:
                with open(dest_path, "wb") as dest_stream:
                    while True:
                        _check_cancel(cancel_event)
                        chunk = source_stream.read(4 * 1024 * 1024)
                        if not chunk:
                            break
                        dest_stream.write(chunk)
                        bytes_done += len(chunk)
                        _emit(
                            progress, "copy", current=number,
                            total=len(regular_files), bytes=bytes_done,
                            total_bytes=inventory.total_bytes,
                            path=entry.relative_path,
                        )
            shutil.copystat(source_path, dest_path, follow_symlinks=False)
            _set_copyable_attributes(source_path, dest_path)
            if entry.hardlink_group:
                hardlink_first[entry.hardlink_group] = dest_path

    link_entries = sorted(
        (entry for entry in inventory.entries.values()
         if entry.kind in ("symlink", "junction")),
        key=lambda entry: entry.relative_path,
    )
    for entry in link_entries:
        _check_cancel(cancel_event)
        source_path = _join_relative(source, entry.relative_path)
        link_path = _join_relative(staging, entry.relative_path)
        os.makedirs(os.path.dirname(link_path), exist_ok=True)
        if entry.kind == "symlink":
            _create_symlink(
                source_path, link_path, staging, final_destination, entry
            )
        else:
            _create_copied_junction(source_path, link_path, staging, entry)
        _emit(progress, "copy_link", path=entry.relative_path)

    for entry in reversed(directories):
        source_path = _join_relative(source, entry.relative_path)
        dest_path = _join_relative(staging, entry.relative_path)
        shutil.copystat(source_path, dest_path, follow_symlinks=False)
        _set_copyable_attributes(source_path, dest_path)
    shutil.copystat(source, staging, follow_symlinks=False)
    _set_copyable_attributes(source, staging)


def _set_copyable_attributes(source_path, destination_path):
    if os.name != "nt":
        return
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        get_attributes = kernel32.GetFileAttributesW
        get_attributes.argtypes = [ctypes.c_wchar_p]
        get_attributes.restype = ctypes.c_uint
        set_attributes = kernel32.SetFileAttributesW
        set_attributes.argtypes = [ctypes.c_wchar_p, ctypes.c_uint]
        set_attributes.restype = ctypes.c_int
        source_attributes = get_attributes(source_path)
        invalid = ctypes.c_uint(-1).value
        if source_attributes == invalid:
            raise ctypes.WinError(ctypes.get_last_error())
        attributes = source_attributes & COPYABLE_ATTRIBUTES
        if attributes == 0:
            return
        if not set_attributes(destination_path, attributes):
            raise ctypes.WinError(ctypes.get_last_error())
    except AttributeError:
        return


def _probe_symlink(parent):
    with tempfile.TemporaryDirectory(prefix=".link-probe-", dir=parent) as temp:
        target = os.path.join(temp, "target")
        link = os.path.join(temp, "link")
        os.mkdir(target)
        os.symlink(target, link, target_is_directory=True)
        if not os.path.isdir(link):
            raise MigrationError("当前权限无法创建目录符号链接。")


def _probe_junction(parent):
    with tempfile.TemporaryDirectory(prefix=".junction-probe-", dir=parent) as temp:
        target = os.path.join(temp, "target")
        link = os.path.join(temp, "link")
        os.mkdir(target)
        _create_junction(link, target)
        if not os.path.isdir(link):
            raise MigrationError("当前权限无法创建 NTFS 目录联接。")
        os.rmdir(link)


def _check_volume_and_space(source, destination, required_bytes):
    source_fs = _windows_filesystem(source)
    target_fs = _windows_filesystem(os.path.dirname(destination))
    if source_fs != "NTFS" or target_fs != "NTFS":
        raise MigrationError(
            "源卷和目标卷都必须是 NTFS；当前检测到 {} -> {}。".format(
                source_fs, target_fs
            )
        )
    safety_margin = max(64 * 1024 * 1024, required_bytes // 50)
    free_bytes = shutil.disk_usage(os.path.dirname(destination)).free
    if free_bytes < required_bytes + safety_margin:
        raise MigrationError(
            "目标空间不足：需要约 {:.2f} GB，当前可用 {:.2f} GB。".format(
                (required_bytes + safety_margin) / (1024 ** 3),
                free_bytes / (1024 ** 3),
            )
        )
    _probe_symlink(os.path.dirname(destination))
    _probe_junction(os.path.dirname(source))
    return source_fs, target_fs, free_bytes


def _verify_junction(source, destination, allow_symlink=False):
    if not os.path.isdir(source):
        raise MigrationError("原路径未能通过联接访问目标目录。")
    if not (os.path.islink(source) or _is_junction(source)):
        raise MigrationError("原路径不是目录联接或符号链接。")
    if not os.path.samefile(source, destination):
        raise MigrationError("原路径联接没有指向所选目标目录。")
    if os.name == "nt" and not _is_junction(source) and not allow_symlink:
        file_stat = os.lstat(source)
        if getattr(file_stat, "st_reparse_tag", 0) != IO_REPARSE_TAG_MOUNT_POINT:
            raise MigrationError("原路径重解析点类型不是 NTFS 目录联接。")


def _backup_name(source):
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return source + ".migration-backup-{}-{}".format(stamp, uuid.uuid4().hex[:8])


def _cleanup_backup(source, backup):
    parent = _normal_case(os.path.dirname(source))
    backup_parent = _normal_case(os.path.dirname(backup))
    expected_prefix = os.path.basename(source) + ".migration-backup-"
    if parent != backup_parent or not os.path.basename(backup).startswith(expected_prefix):
        raise MigrationError("回退副本路径校验失败，拒绝清理：{}".format(backup))
    backup_stat = os.lstat(backup)
    if _reparse_kind(backup, backup_stat):
        raise MigrationError("回退副本根目录是重解析点，拒绝递归清理。")
    _remove_path_no_follow(backup)


def build_preflight_report(source, destination, progress=None, cancel_event=None,
                           platform_checks=True):
    source, destination = validate_paths(source, destination)
    occupants = []
    if platform_checks:
        occupants = find_source_occupants(source, progress, cancel_event)
        if occupants:
            return {
                "source": source,
                "destination": destination,
                "inventory": None,
                "source_filesystem": "未检测",
                "destination_filesystem": "未检测",
                "free_bytes": 0,
                "occupants": occupants,
            }
    inventory = inspect_tree(source, progress, cancel_event)
    if platform_checks:
        source_fs, destination_fs, free_bytes = _check_volume_and_space(
            source, destination, inventory.total_bytes
        )
    else:
        source_fs = destination_fs = "未检测"
        free_bytes = shutil.disk_usage(os.path.dirname(destination)).free
        if free_bytes < inventory.total_bytes:
            raise MigrationError("目标磁盘空间不足。")
    return {
        "source": source,
        "destination": destination,
        "inventory": inventory,
        "source_filesystem": source_fs,
        "destination_filesystem": destination_fs,
        "free_bytes": free_bytes,
        "occupants": occupants,
    }


def migrate_directory(source, destination, confirm_apps_closed=False,
                      progress=None, cancel_event=None,
                      junction_factory=None, platform_checks=True):
    """Copy, compare, switch the source path to a junction, then clean rollback."""
    if not confirm_apps_closed:
        raise MigrationError("请先关闭使用源目录的程序并确认该项。")
    source, destination = validate_paths(source, destination)
    if platform_checks:
        occupants = find_source_occupants(source, progress, cancel_event)
        if occupants:
            raise SourceInUseError(
                "检测到仍在使用源目录的程序，请关闭后重新检测，再启动迁移：\n{}".format(
                    format_source_occupants(occupants)
                )
            )
        _check_volume_and_space(source, destination, 0)
    if junction_factory is None:
        junction_factory = _create_junction
    elif platform_checks:
        raise MigrationError("测试联接工厂不能用于正式迁移。")

    parent = os.path.dirname(destination)
    source_parent = os.path.dirname(source)
    staging = os.path.join(
        parent, ".{}.migration-staging-{}".format(
            os.path.basename(destination), uuid.uuid4().hex
        )
    )
    backup = _backup_name(source)
    target_installed = False
    source_backed_up = False
    junction_created = False
    destination_verified = False

    try:
        _emit(progress, "scan_source", path=source)
        source_before = inspect_tree(source, progress, cancel_event)
        if platform_checks:
            _check_volume_and_space(source, destination, source_before.total_bytes)
        _check_cancel(cancel_event)

        _emit(progress, "copy_start", total_bytes=source_before.total_bytes)
        _copy_tree(
            source, staging, destination, source_before, progress, cancel_event
        )
        _emit(progress, "verify_copy", path=staging)
        stage_inventory = inspect_tree(staging, progress, cancel_event)
        summary = compare_inventories(source_before, stage_inventory)

        _emit(progress, "verify_source_unchanged", path=source)
        source_after = inspect_tree(source, progress, cancel_event)
        compare_inventories(source_before, source_after)
        _check_cancel(cancel_event)

        _emit(progress, "install_destination", path=destination)
        os.replace(staging, destination)
        target_installed = True

        # Internal directory junctions must be retargeted after the staging
        # directory receives its final name.
        changed_parent_dirs = set()
        for entry in source_before.entries.values():
            if entry.kind == "junction" and entry.link_semantic.startswith("inside:"):
                link_path = _join_relative(destination, entry.relative_path)
                relative_target = entry.link_semantic[len("inside:"):]
                final_target = _join_relative(destination, relative_target)
                os.rmdir(link_path)
                junction_factory(link_path, final_target)
                changed_parent_dirs.add(entry.relative_path.rpartition("/")[0])
        for relative in changed_parent_dirs:
            shutil.copystat(
                _join_relative(source, relative),
                _join_relative(destination, relative),
                follow_symlinks=False,
            )
            _set_copyable_attributes(
                _join_relative(source, relative),
                _join_relative(destination, relative),
            )

        _emit(progress, "verify_destination", path=destination)
        destination_inventory = inspect_tree(destination, progress)
        summary = compare_inventories(source_before, destination_inventory)
        destination_verified = True
        _check_cancel(cancel_event)

        if platform_checks:
            _emit(progress, "check_occupants", path=source)
            occupants = find_source_occupants(source, progress, cancel_event)
            if occupants:
                raise SourceInUseError(
                    "切换前发现仍在使用源目录的程序；已保留源目录并取消迁移：\n{}".format(
                        format_source_occupants(occupants)
                    )
                )

        if platform_checks:
            _check_source_rename_access(source, progress, cancel_event)
        _emit(progress, "switch_source", path=source)
        os.replace(source, backup)
        source_backed_up = True
        junction_factory(source, destination)
        junction_created = True
        _verify_junction(
            source, destination, allow_symlink=(junction_factory is not _create_junction)
        )

        _emit(progress, "verify_final", path=backup)
        backup_inventory = inspect_tree(
            backup, progress, internal_roots=[source]
        )
        destination_inventory = inspect_tree(destination, progress)
        summary = compare_inventories(backup_inventory, destination_inventory)
        compare_inventories(source_before, destination_inventory)
        _verify_junction(
            source, destination, allow_symlink=(junction_factory is not _create_junction)
        )

        _emit(progress, "cleanup_backup", path=backup)
        try:
            _cleanup_backup(source, backup)
            backup_cleaned = True
            cleanup_error = ""
        except Exception as exc:
            backup_cleaned = False
            cleanup_error = str(exc)
        _emit(
            progress, "complete",
            backup_cleaned=backup_cleaned,
            summary=summary,
        )
        return MigrationResult(
            source=source,
            destination=destination,
            backup=backup,
            inventory=source_before,
            backup_cleaned=backup_cleaned,
            cleanup_error=cleanup_error,
        )
    except Exception as exc:
        rollback_errors = []
        if source_backed_up:
            try:
                if os.path.lexists(source):
                    source_stat = os.lstat(source)
                    if _reparse_kind(source, source_stat):
                        if os.path.isdir(source):
                            os.rmdir(source)
                        else:
                            os.unlink(source)
                    else:
                        raise MigrationError(
                            "原路径出现非预期内容，未覆盖：{}".format(source)
                        )
                if os.path.lexists(backup):
                    os.replace(backup, source)
            except Exception as rollback_exc:
                rollback_errors.append(str(rollback_exc))
        elif target_installed and isinstance(exc, SourceInUseError):
            try:
                _remove_path_no_follow(destination)
                target_installed = False
            except Exception as cleanup_exc:
                rollback_errors.append(
                    "源目录未切换；清理已核验目标副本失败：{}".format(cleanup_exc)
                )
        if os.path.lexists(staging):
            try:
                _remove_path_no_follow(staging)
            except Exception as cleanup_exc:
                rollback_errors.append("清理临时目录失败：{}".format(cleanup_exc))
        if rollback_errors:
            raise MigrationError(
                "{}\n回退处理也遇到问题：{}".format(
                    exc, "\n".join(rollback_errors)
                )
            )
        if source_backed_up:
            raise MigrationError(
                "{}\n已将原目录恢复到：{}".format(exc, source)
            )
        if target_installed:
            if isinstance(exc, OSError) and getattr(exc, "winerror", None) in (5, 32):
                failure = (
                    "切换源目录失败，可能被目录句柄占用或缺少重命名权限：{}".format(
                        exc
                    )
                )
            else:
                failure = str(exc)
            copy_state = (
                "已核验通过的目标副本"
                if destination_verified
                else "尚未完成核验的目标副本"
            )
            raise MigrationError(
                "{}\n原目录保持不变；{}保留在：{}".format(
                    failure, copy_state, destination
                )
            )
        raise
