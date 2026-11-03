# -*- coding: utf-8 -*-
"""影子日志无损归档；清理仅列出候选，调用方不得据此直接删除。"""
import gzip
import hashlib
import logging
import os
import re
import shutil
import tempfile
import threading
import time
from datetime import date, timedelta
import zlib


_DAY_FILE = re.compile(r"^\d{4}-\d{2}-\d{2}(?:_\d+)?\.jsonl$")
_ARCHIVE_FILE = re.compile(r"^(\d{4}-\d{2}-\d{2})(?:_\d+)?\.jsonl\.gz$")
_CHUNK = 1024 * 1024
_logger = logging.getLogger(__name__)
_registered = set()
_registration_lock = threading.Lock()


def _pid_alive(pid):
    """无法确定进程状态时按存活处理，禁止收割或清理。"""
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        api = ctypes.WinDLL("kernel32", use_last_error=True)
        api.OpenProcess.restype = wintypes.HANDLE
        api.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        api.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        api.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = api.OpenProcess(0x100000, False, pid)
        if not handle:
            return ctypes.get_last_error() != 87
        try:
            return api.WaitForSingleObject(handle, 0) != 0
        finally:
            api.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except OSError:
        return True


def _sync_orphan_shards(ramdisk_dir, persist_dir, own_pid=None, settle_seconds=120, now=None):
    """收割 RAMDisk 上的孤儿分片（进程异常崩溃残留），settle 稳定后原子发布到持久目录。"""
    if not ramdisk_dir or not persist_dir:
        return {"synced": [], "errors": []}
    ramdisk_dir = os.path.abspath(ramdisk_dir)
    persist_dir = os.path.abspath(persist_dir)
    if ramdisk_dir == persist_dir or not os.path.isdir(ramdisk_dir):
        return {"synced": [], "errors": []}

    now = time.time() if now is None else float(now)
    own_pid_suffix = "_{}.jsonl".format(own_pid) if own_pid is not None else None
    synced, errors = [], []
    os.makedirs(persist_dir, exist_ok=True)

    try:
        filenames = sorted(os.listdir(ramdisk_dir))
    except OSError as exc:
        return {"synced": [], "errors": [{"source": ramdisk_dir, "error": str(exc)}]}

    for name in filenames:
        if not _DAY_FILE.fullmatch(name) or "_" not in name:
            continue
        if own_pid_suffix and name.endswith(own_pid_suffix):
            continue  # 跳过本进程 PID，本进程正常退出走 close()
        if _pid_alive(int(name.rsplit("_", 1)[1][:-6])):
            continue
        src = os.path.join(ramdisk_dir, name)
        dst = os.path.join(persist_dir, name)
        try:
            st = os.stat(src)
            if (now - st.st_mtime) < settle_seconds:
                continue  # 尚未稳定，可能仍在写入中
            if os.path.exists(dst) and os.path.getsize(dst) >= st.st_size:
                continue

            fd, tmp = tempfile.mkstemp(prefix=".shadow-persist-", suffix=".tmp", dir=persist_dir)
            try:
                with os.fdopen(fd, "wb") as out:
                    with open(src, "rb") as inp:
                        if os.path.exists(dst):
                            with open(dst, "rb") as previous:
                                for chunk in iter(lambda: previous.read(_CHUNK), b""):
                                    if inp.read(len(chunk)) != chunk:
                                        raise RuntimeError("持久副本与 RAMDisk 前缀冲突，拒绝覆盖")
                            inp.seek(0)
                        shutil.copyfileobj(inp, out)
                    out.flush()
                    os.fsync(out.fileno())
                after = os.stat(src)
                if (st.st_size, st.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                    raise RuntimeError("孤儿分片在复制时变化，保留源文件")
                os.replace(tmp, dst)
                synced.append(name)
            finally:
                if os.path.exists(tmp):
                    try:
                        os.unlink(tmp)
                    except OSError:
                        pass
        except (OSError, RuntimeError) as exc:
            errors.append({"source": name, "error": str(exc)})
            _logger.warning("[fusion] 孤儿分片落盘失败 %s: %s", name, exc)

    return {"synced": synced, "errors": errors}


def cleanup_verified_shards(directory, today, keep_days=9, max_files=1, archive_directory=None):
    """仅删除过期、进程已退出且逐字节匹配压缩档的 PID 原文件。"""
    cutoff = (date.fromisoformat(today) - timedelta(days=max(1, keep_days))).isoformat()
    removed, errors = [], []
    root = os.path.realpath(directory)
    if archive_directory:
        candidates = [{"source": os.path.join(directory, name),
                       "archive": os.path.join(archive_directory, name + ".gz")}
                      for name in sorted(os.listdir(directory))
                      if _DAY_FILE.fullmatch(name) and name[:10] < cutoff
                      and os.path.isfile(os.path.join(archive_directory, name + ".gz"))]
    else:
        candidates = cleanup_candidates(directory, cutoff)
    for candidate in candidates:
        if len(removed) >= max_files:
            break
        source = candidate["source"]
        name = os.path.basename(source)
        if "_" not in name or _pid_alive(int(name.rsplit("_", 1)[1][:-6])):
            continue
        try:
            if os.path.dirname(os.path.realpath(source)) != root or os.path.islink(source):
                raise RuntimeError("清理目标超出日志目录")
            before = os.stat(source)
            with open(source, "rb") as raw, gzip.open(candidate["archive"], "rb") as archived:
                while True:
                    chunk = raw.read(_CHUNK)
                    if archived.read(len(chunk) or 1) != chunk:
                        raise RuntimeError("压缩档与源文件不一致，拒绝清理")
                    if not chunk:
                        break
            after = os.stat(source)
            if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                raise RuntimeError("源文件发生变化，拒绝清理")
            os.unlink(source)
            removed.append(source)
        except (OSError, EOFError, RuntimeError, zlib.error) as exc:
            errors.append({"source": source, "error": str(exc)})
    return {"removed": removed, "errors": errors}


def cleanup_expired_archives(
    directory,
    today,
    keep_archive_days=60,
    max_archive_mb=300.0,
    min_keep_days=15,
):
    """清理过期的 .jsonl.gz 压缩归档：双重守卫（超 60 天自动删除 + 超 300MB 按最老日期淘汰）。

    安全边界：
    1. 严格限制在 directory 真实路径内，拒绝符号链接；
    2. 优先删除早于 today - keep_archive_days（默认 60 天）的 .jsonl.gz；
    3. 若剩余 .jsonl.gz 总大小仍超过 max_archive_mb（默认 300MB），按日期从最老到最新依次淘汰，
       但强制保留最近 min_keep_days（默认 15 天）以内的归档不因容量淘汰被删，保障 Walk-Forward 评估窗口；
    4. 若某 .jsonl.gz 对应的同名未压缩 .jsonl 仍存在且尚未清理，先不删该 .gz，防止原文件清理校验失去对照。
    """
    removed, errors = [], []
    if not directory or not os.path.isdir(directory):
        return {"removed": removed, "total_bytes_after": 0, "errors": errors}

    root = os.path.realpath(directory)
    today_dt = date.fromisoformat(str(today)[:10])
    age_cutoff = (today_dt - timedelta(days=max(1, int(keep_archive_days)))).isoformat()
    min_keep_cutoff = (today_dt - timedelta(days=max(1, int(min_keep_days)))).isoformat()
    max_bytes = int(float(max_archive_mb) * 1024 * 1024)

    entries = []
    try:
        names = sorted(os.listdir(directory))
    except OSError as exc:
        return {"removed": removed, "total_bytes_after": 0, "errors": [{"source": directory, "error": str(exc)}]}

    for name in names:
        m = _ARCHIVE_FILE.fullmatch(name)
        if not m:
            continue
        day_str = m.group(1)
        path = os.path.join(directory, name)
        raw_sibling = path[:-3]  # 对应 .jsonl
        try:
            if os.path.islink(path) or os.path.dirname(os.path.realpath(path)) != root:
                continue
            if not os.path.isfile(path):
                continue
            size = os.path.getsize(path)
            entries.append({
                "name": name,
                "day": day_str,
                "path": path,
                "size": size,
                "has_raw_sibling": os.path.exists(raw_sibling),
            })
        except OSError as exc:
            errors.append({"source": path, "error": str(exc)})

    # 按 (日期, 文件名) 升序排列（最老的排最前）
    entries.sort(key=lambda x: (x["day"], x["name"]))
    remaining = []

    # 第一轮：按天数（> 60 天）清理过期 .gz
    for item in entries:
        if item["day"] < age_cutoff and not item["has_raw_sibling"]:
            try:
                os.unlink(item["path"])
                removed.append(item["path"])
            except OSError as exc:
                errors.append({"source": item["path"], "error": str(exc)})
                remaining.append(item)
        else:
            remaining.append(item)

    # 第二轮：按总容量上限（> 300MB）从最老往最新淘汰（保护 min_keep_days 内的近期样本）
    total_bytes = sum(x["size"] for x in remaining)
    if max_bytes > 0 and total_bytes > max_bytes:
        still_kept = []
        for item in remaining:
            if (
                total_bytes > max_bytes
                and item["day"] < min_keep_cutoff
                and not item["has_raw_sibling"]
            ):
                try:
                    os.unlink(item["path"])
                    removed.append(item["path"])
                    total_bytes -= item["size"]
                except OSError as exc:
                    errors.append({"source": item["path"], "error": str(exc)})
                    still_kept.append(item)
            else:
                still_kept.append(item)
        remaining = still_kept

    return {
        "removed": removed,
        "total_bytes_after": sum(x["size"] for x in remaining),
        "errors": errors,
    }


def archive_day(source, before_day, archive_directory=None):
    """归档已结束日期，允许从 RAMDisk 直接压缩到已有落盘目录。"""
    name = os.path.basename(source)
    if not _DAY_FILE.fullmatch(name):
        raise ValueError("不是按日影子日志")
    day = date.fromisoformat(name[:10])
    if day >= date.fromisoformat(before_day):
        raise ValueError("不能归档当日或未来日志")
    target = os.path.join(archive_directory, name + ".gz") if archive_directory else source + ".gz"
    if os.path.exists(target):
        raise FileExistsError(target)
    before = os.stat(source)
    digest = hashlib.sha256()
    fd, temporary = tempfile.mkstemp(prefix=".shadow-archive-", suffix=".tmp", dir=os.path.dirname(os.path.abspath(target)))
    try:
        with os.fdopen(fd, "wb") as raw:
            with gzip.GzipFile(filename="", fileobj=raw, mode="wb", compresslevel=6, mtime=0) as compressed:
                with open(source, "rb") as inp:
                    while True:
                        chunk = inp.read(_CHUNK)
                        if not chunk:
                            break
                        digest.update(chunk)
                        compressed.write(chunk)
            raw.flush()
            os.fsync(raw.fileno())
        after = os.stat(source)
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise RuntimeError("源日志在归档时发生变化")
        check = hashlib.sha256()
        with gzip.open(temporary, "rb") as inp:
            for chunk in iter(lambda: inp.read(_CHUNK), b""):
                check.update(chunk)
        if digest.digest() != check.digest():
            raise RuntimeError("归档校验失败")
        # 不覆盖既有归档；硬链接的创建在 Windows 同卷也是原子的。
        os.link(temporary, target)
        return {"source": source, "archive": target, "sha256": digest.hexdigest(),
                "source_bytes": before.st_size, "archive_bytes": os.path.getsize(target)}
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def cleanup_candidates(directory, before_day):
    """只计算已过期且有同名归档的原始文件，绝不删除或宣称归档已验证。"""
    cutoff = date.fromisoformat(before_day)
    result = []
    for name in sorted(os.listdir(directory)):
        if not _DAY_FILE.fullmatch(name):
            continue
        try:
            day = date.fromisoformat(name[:10])
        except ValueError:
            continue
        path = os.path.join(directory, name)
        if day < cutoff and os.path.isfile(path) and os.path.isfile(path + ".gz"):
            result.append({"source": path, "archive": path + ".gz", "source_bytes": os.path.getsize(path),
                           "requires_revalidation": True})
    return result


def archive_finished_days(directory, before_day, settle_seconds=120, max_files=1, now=None):
    """限量归档稳定的历史日；保留源文件，失败由调用方记录并重试。"""
    cutoff = date.fromisoformat(before_day)
    now = time.time() if now is None else float(now)
    archived, errors = [], []
    for name in sorted(os.listdir(directory)):
        if len(archived) >= max_files:
            break
        if not _DAY_FILE.fullmatch(name):
            continue
        try:
            if date.fromisoformat(name[:10]) >= cutoff:
                continue
            source = os.path.join(directory, name)
            if os.path.exists(source + ".gz"):
                continue
            if now - os.stat(source).st_mtime < settle_seconds:
                continue
            archived.append(archive_day(source, before_day))
        except FileExistsError:
            continue
        except (OSError, ValueError, RuntimeError, EOFError) as exc:
            errors.append({"source": name, "error": str(exc)})
    return {"archived": archived, "errors": errors}


def register_archive_worker(directory):
    """收盘窗口后台限速归档与孤儿分片收割；不影响写线程，不清理源文件。"""
    directory = os.path.abspath(directory)
    with _registration_lock:
        if directory in _registered:
            return
        _registered.add(directory)
    def run():
        last_attempt = 0.0
        closing_since = None
        while True:
            time.sleep(60)
            try:
                from ats.archive_policy import archive_window, ARCHIVE_INTERVAL
                from ats.fusion.shadow_io import ram_directory
                window, day = archive_window()
                if window != "close":
                    closing_since = None
                    continue
                current = time.monotonic()
                if closing_since is None:
                    closing_since = current
                if current - closing_since < 120 or current - last_attempt < ARCHIVE_INTERVAL:
                    continue
                last_attempt = current

                # 孤儿分片收割：收割 RAMDisk 崩溃残留的非本 PID 分片
                ram = ram_directory(directory)
                if ram:
                    _sync_orphan_shards(ram, directory, own_pid=os.getpid(), settle_seconds=120)

                # 历史日限量归档
                result = archive_finished_days(directory, day)
                cleanup = cleanup_verified_shards(directory, day)
                result["errors"].extend(cleanup["errors"])
                if ram and os.path.isdir(ram):
                    cleanup = cleanup_verified_shards(ram, day, archive_directory=directory)
                    result["errors"].extend(cleanup["errors"])
                gz_cleanup = cleanup_expired_archives(
                    directory, day, keep_archive_days=60, max_archive_mb=300.0
                )
                result["errors"].extend(gz_cleanup["errors"])
                for error in result["errors"]:
                    _logger.warning("梯度历史归档失败，源文件保留: %s", error)
            except Exception:
                _logger.exception("梯度后台归档失败，源文件保留")
    threading.Thread(target=run, name="FusionShadowArchive", daemon=True).start()
