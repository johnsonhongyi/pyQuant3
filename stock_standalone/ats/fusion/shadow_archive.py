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
from datetime import date


_DAY_FILE = re.compile(r"^\d{4}-\d{2}-\d{2}(?:_\d+)?\.jsonl$")
_CHUNK = 1024 * 1024
_logger = logging.getLogger(__name__)
_registered = set()
_registration_lock = threading.Lock()


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
                        shutil.copyfileobj(inp, out)
                    out.flush()
                    os.fsync(out.fileno())
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
                for error in result["errors"]:
                    _logger.warning("梯度历史归档失败，源文件保留: %s", error)
            except Exception:
                _logger.exception("梯度后台归档失败，源文件保留")
    threading.Thread(target=run, name="FusionShadowArchive", daemon=True).start()
