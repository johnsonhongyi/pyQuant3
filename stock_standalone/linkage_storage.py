"""Bounded RAMDisk linkage state, with delayed atomic archives after close."""
import hashlib
import json
import logging
import os
import shutil
from pathlib import Path
import sqlite3
import threading
import time
from contextlib import closing, contextmanager
from datetime import datetime, timedelta, timezone

from ats.persistence_lock import directory_write_lock

MAX_DATABASE_BYTES = 100 * 1024 * 1024
ARCHIVE_INTERVAL = 30 * 60
ARCHIVE_SETTLE_SECONDS = 120
RECLAIM_INTERVAL = 5 * 60
RECLAIM_PAGES = 256
MAX_EVENTS = 1000
MAX_EVENT_BYTES = 4 * 1024 * 1024
_workers = set()
_archive_targets = {}
_workers_lock = threading.Lock()
logger = logging.getLogger(__name__)
_database_gates = {}
_database_gates_lock = threading.Lock()
_database_owners = {}


@contextmanager
def database_access(path, operation, timeout=4.0, read_only=False):
    """Serialize local linkage connections; SQLite coordinates cross-process access."""
    identity = os.path.normcase(os.path.abspath(path))
    started = time.monotonic()
    if read_only:
        try:
            yield
        finally:
            elapsed = time.monotonic() - started
            if elapsed >= 0.25:
                caller = (os.getpid(), threading.current_thread().name, operation, 'read')
                logger.warning('[LINKAGE-DB-SLOW] database=%s caller=%s gate_wait_ms=0 directory_wait_ms=0 elapsed_ms=%.1f',
                               identity, caller, elapsed * 1000)
        return
    with _database_gates_lock:
        gate = _database_gates.setdefault(identity, threading.Lock())
    if not gate.acquire(timeout=timeout):
        logger.error('[LINKAGE-DB-BUSY] database=%s waiter=%s gate_owner=%s gate_wait_ms=%.1f',
                     identity, operation, _database_owners.get(identity),
                     (time.monotonic() - started) * 1000)
        raise TimeoutError('linkage database access busy: ' + operation)
    acquired = time.monotonic()
    owner = (os.getpid(), threading.current_thread().name, operation)
    _database_owners[identity] = owner
    directory_wait_ms = 0.0
    directory_lock_acquired = False
    directory_started = time.monotonic()
    try:
        # Keep cross-process writers coordinated; read-only connections bypass
        # this exclusive directory lock and use SQLite's native read locks.
        remaining = max(0.0, timeout - (acquired - started))
        with directory_write_lock(os.path.dirname(identity), timeout=remaining):
            directory_lock_acquired = True
            directory_wait_ms = (time.monotonic() - directory_started) * 1000
            yield
    finally:
        if not directory_lock_acquired:
            directory_wait_ms = (time.monotonic() - directory_started) * 1000
        _database_owners.pop(identity, None)
        gate.release()
        elapsed = time.monotonic() - started
        if elapsed >= 0.25:
            logger.warning('[LINKAGE-DB-SLOW] database=%s caller=%s gate_wait_ms=%.1f directory_wait_ms=%.1f elapsed_ms=%.1f',
                           identity, owner, (acquired - started) * 1000,
                           directory_wait_ms, elapsed * 1000)


def configure(connection):
    # The runtime file is on RAMDisk; rollback journals avoid an unbounded WAL.
    connection.execute('PRAGMA busy_timeout=4000')
    connection.execute('PRAGMA synchronous=NORMAL')
    page_size = connection.execute('PRAGMA page_size').fetchone()[0]
    actual_limit = connection.execute('PRAGMA max_page_count=%d' % (MAX_DATABASE_BYTES // page_size)).fetchone()[0]
    if actual_limit * page_size > MAX_DATABASE_BYTES:
        raise RuntimeError('linkage_existing_database_exceeds_size_limit')
    connection.execute('PRAGMA journal_size_limit=0')


def trim(connection):
    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if 'linkage_context_snapshots' in tables:
        connection.execute('DELETE FROM linkage_context_snapshots WHERE snapshot_id NOT IN '
                           '(SELECT snapshot_id FROM linkage_context_snapshots ORDER BY stored_at DESC LIMIT 1)')
    if 'linkage_context_events' in tables:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).strftime('%Y-%m-%d')
        connection.execute("DELETE FROM linkage_context_events WHERE event_type='' OR occurred_at='' "
                           "OR substr(occurred_at,1,10) < ?", (cutoff,))
        connection.execute('DELETE FROM linkage_context_events WHERE event_id NOT IN '
                           '(SELECT event_id FROM linkage_context_events ORDER BY occurred_at DESC,event_id DESC LIMIT ?)',
                           (MAX_EVENTS,))
        rows = connection.execute('SELECT event_id,payload FROM linkage_context_events '
                                  'ORDER BY occurred_at DESC,event_id DESC').fetchall()
        total = 0
        remove = []
        for event_id, payload in rows:
            try:
                valid = isinstance(json.loads(bytes(payload).decode('utf-8')), dict)
            except (ValueError, TypeError, UnicodeError):
                valid = False
            if not valid:
                remove.append((event_id,))
                continue
            total += len(payload)
            if total > MAX_EVENT_BYTES:
                remove.append((event_id,))
        connection.executemany('DELETE FROM linkage_context_events WHERE event_id=?', remove)
    if 'linkage_nonces' in tables:
        connection.execute('DELETE FROM linkage_nonces WHERE timestamp < ?', (int(time.time()) - 600,))
    # Never evict command identities or pending evidence to make room. A full
    # database rejects the transaction, rather than enabling duplicate execution.


def configured_ramdisk_root():
    """Normalize bare drive letters without requiring device realpath support."""
    from JohnsonUtil import commonTips as cct
    for value in cct.ramdisk_rootList:
        if not value:
            continue
        try:
            value = os.fspath(value)
            if os.name == 'nt' and len(value) == 2 and value[1] == ':':
                value += os.sep
            root = Path(os.path.abspath(os.path.normpath(value)))
            if root.is_dir():
                return root
        except (OSError, ValueError, TypeError):
            continue
    raise RuntimeError('linkage_ramdisk_unavailable: configured RAMDisk required')


def _runtime_location(local_path):
    local = Path(os.path.abspath(local_path))
    ram_root = configured_ramdisk_root()
    if ram_root == local.parent:
        raise RuntimeError('linkage_ramdisk_unavailable: configured RAMDisk required')
    identity = hashlib.sha256(str(local).casefold().encode('utf-8')).hexdigest()[:16]
    directory = ram_root / 'instock_runtime' / identity
    runtime = directory / local.name
    directory.mkdir(parents=True, exist_ok=True)
    return runtime, local


def _start_archive(runtime, local, file_limit=None):
    with _workers_lock:
        if str(runtime) not in _workers:
            _workers.add(str(runtime))
            _archive_targets[str(runtime)] = (runtime, local, file_limit)
            threading.Thread(target=_archive_loop, args=(runtime, local, file_limit),
                             name='ClosingArchive', daemon=True).start()


def runtime_file(local_path, max_bytes=4 * 1024 * 1024, archive=True):
    """Shared atomic JSON stores may write RAMDisk; local copies are closing-only."""
    runtime, local = _runtime_location(local_path)
    with directory_write_lock(str(runtime.parent), timeout=2):
        if not runtime.exists() and local.exists():
            if local.stat().st_size > max_bytes:
                raise RuntimeError('runtime_file_legacy_size_limit: ' + local.name)
            temporary = runtime.with_name(runtime.name + '.initializing')
            shutil.copyfile(local, temporary)
            os.replace(temporary, runtime)
    if archive:
        _start_archive(runtime, local, max_bytes)
    return str(runtime)


def runtime_database(local_path):
    runtime, local = _runtime_location(local_path)
    directory = runtime.parent
    with directory_write_lock(str(directory), timeout=10):
        if not runtime.exists():
            temporary = directory / (local.name + '.initializing')
            try:
                with closing(sqlite3.connect(str(temporary))) as target:
                    # Must be set before the first table is created. Existing
                    # non-auto-vacuum files are converted only after close.
                    target.execute('PRAGMA auto_vacuum=INCREMENTAL')
                    configure(target)
                    if local.exists():
                        if any(Path(str(local) + suffix).exists() for suffix in ('-wal', '-shm')):
                            raise RuntimeError('linkage_legacy_writer_or_wal_present: stop old version before migration')
                        source = sqlite3.connect(local.as_uri() + '?mode=ro', uri=True, timeout=1)
                        try:
                            # Migrate only bounded live context, retaining reliable
                            # operations/outbox. Do not copy the 100MB snapshot history.
                            schema = source.execute("SELECT type,name,sql FROM sqlite_master WHERE sql IS NOT NULL "
                                                    "AND name NOT LIKE 'sqlite_%' ORDER BY type='table' DESC").fetchall()
                            for kind, name, sql in schema:
                                if kind != 'table':
                                    continue
                                target.execute(sql)
                                quoted = '"' + name.replace('"', '""') + '"'
                                suffix = ''
                                if name == 'linkage_context_snapshots':
                                    suffix = ' ORDER BY stored_at DESC LIMIT 1'
                                elif name == 'linkage_context_events':
                                    suffix = ' ORDER BY occurred_at DESC,event_id DESC LIMIT 1000'
                                rows = source.execute('SELECT * FROM ' + quoted + suffix)
                                for row in rows:
                                    target.execute('INSERT INTO ' + quoted + ' VALUES (' + ','.join('?' for _ in row) + ')', row)
                            for kind, name, sql in schema:
                                if kind == 'index':
                                    target.execute(sql)
                            trim(target)
                        finally:
                            source.close()
                    target.commit()
                os.replace(temporary, runtime)
            finally:
                if temporary.exists():
                    temporary.unlink()
    _start_archive(runtime, local)
    return str(runtime)


def _archive_one(runtime, local, file_limit=None, force=False, timeout=0.25):
    """Atomically save one registered store; force is reserved for shutdown."""
    with directory_write_lock(str(runtime.parent), timeout=timeout):
        if not runtime.exists():
            raise FileNotFoundError(str(runtime))
        marker = runtime.parent / (runtime.name + '.archived_day')
        stat = runtime.stat()
        revision = '%s:%s:%s' % (datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d'),
                                 stat.st_mtime_ns, stat.st_size)
        if not force and marker.exists():
            if marker.read_text(encoding='utf-8') == revision:
                return
            if time.time() - marker.stat().st_mtime < ARCHIVE_INTERVAL:
                return
        local.parent.mkdir(parents=True, exist_ok=True)
        temporary = local.with_name(local.name + '.closing.tmp')
        if file_limit is not None:
            if not runtime.exists():
                return
            if runtime.stat().st_size > file_limit:
                raise RuntimeError('runtime_file_size_limit: ' + runtime.name)
            content = runtime.read_bytes()
            if len(content) > file_limit:
                raise RuntimeError('runtime_file_size_limit: ' + runtime.name)
            current = runtime.stat()
            if (current.st_mtime_ns, current.st_size) != (stat.st_mtime_ns, stat.st_size):
                raise RuntimeError('runtime_changed_during_archive')
            if not local.exists() or local.stat().st_size != len(content) or local.read_bytes() != content:
                with open(temporary, 'wb') as stream:
                    stream.write(content)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, local)
            marker.write_text(revision, encoding='utf-8')
            return
        source = sqlite3.connect(str(runtime), timeout=1)
        try:
            if not force:
                configure(source)
                trim(source)
                source.commit()
                if source.execute('PRAGMA auto_vacuum').fetchone()[0] != 2:
                    source.execute('PRAGMA auto_vacuum=INCREMENTAL')
                    source.execute('VACUUM')
                stat = runtime.stat()
                revision = '%s:%s:%s' % (revision.split(':')[0], stat.st_mtime_ns, stat.st_size)
            backup_deadline = time.monotonic() + max(0.1, timeout)
            def check_backup(status, remaining, total):
                if time.monotonic() > backup_deadline:
                    raise TimeoutError('runtime_database_backup_deadline')
            with closing(sqlite3.connect(str(temporary))) as target:
                source.backup(target, pages=128, progress=check_backup, sleep=0.01)
                if not force:
                    target.execute('VACUUM')
                if target.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                    raise RuntimeError('linkage_archive_integrity_failed')
        finally:
            source.close()
        if temporary.stat().st_size > MAX_DATABASE_BYTES:
            raise RuntimeError('linkage_archive_size_limit')
        # Old application versions must be stopped before deployment:
        # replacing a DB still held open by an old writer is not safe.
        if any(Path(str(local) + suffix).exists() for suffix in ('-wal', '-shm')):
            raise RuntimeError('linkage_legacy_writer_or_wal_present')
        os.replace(temporary, local)
        marker.write_text(revision, encoding='utf-8')

def persist_registered_runtime(timeout=20.0):
    """Flush log batches and save this process's stores, including before close."""
    failures = {}
    saved = []
    deadline = time.monotonic() + timeout
    # Drain already queued favorite mutations before snapshotting their file.
    # Do not import/initialize a manager during shutdown.
    import sys
    favorites = sys.modules.get('global_favorites')
    executor = getattr(favorites, '_favorite_write_executor', None)
    if executor is not None:
        try:
            executor.submit(lambda: None).result(timeout=min(4.0, max(0.0, deadline - time.monotonic())))
        except Exception as exc:
            failures['favorite_write_queue'] = str(exc)
    handlers = set(logging.getLogger().handlers)
    for item in list(logging.Logger.manager.loggerDict.values()):
        if isinstance(item, logging.Logger):
            handlers.update(item.handlers)
    for handler in handlers:
        if hasattr(handler, '_archive_target'):
            try:
                handler.flush()
            except Exception as exc:
                failures[str(handler._archive_target)] = str(exc)
    with _workers_lock:
        targets = list(_archive_targets.values())
    for runtime, local, file_limit in targets:
        try:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('runtime_shutdown_archive_deadline')
            _archive_one(runtime, local, file_limit, force=True, timeout=min(4.0, remaining))
            saved.append(str(local))
        except Exception as exc:
            failures[str(local)] = str(exc)
            logger.exception('Runtime shutdown archive failed: %s; RAMDisk retained', local)
    return {'saved': saved, 'failed': failures}


def _archive_loop(runtime, local, file_limit=None):
    last_error = 0.0
    closing_since = None
    while True:
        time.sleep(60)
        try:
            from ats.archive_policy import archive_window
            window, day = archive_window()
            if file_limit is None:
                _reclaim_runtime(runtime)
            if window != 'close':
                closing_since = None
                continue
            if closing_since is None:
                closing_since = time.monotonic()
            if time.monotonic() - closing_since < ARCHIVE_SETTLE_SECONDS:
                continue
            _archive_one(runtime, local, file_limit)
        except Exception:
            if time.monotonic() - last_error >= 300:
                last_error = time.monotonic()
                logger.exception('Linkage closing archive deferred; runtime state retained on RAMDisk')


def _reclaim_runtime(runtime):
    """Bounded background reclamation on RAMDisk, never a full intraday VACUUM."""
    with directory_write_lock(str(runtime.parent), timeout=0.05):
        marker = runtime.parent / (runtime.name + '.reclaim_time')
        if marker.exists() and time.time() - marker.stat().st_mtime < RECLAIM_INTERVAL:
            return
        marker.touch()
        with closing(sqlite3.connect(str(runtime), timeout=0.05)) as connection:
            if connection.execute('PRAGMA auto_vacuum').fetchone()[0] != 2:
                return
            pages = connection.execute('PRAGMA page_count').fetchone()[0]
            free_pages = connection.execute('PRAGMA freelist_count').fetchone()[0]
            if free_pages >= RECLAIM_PAGES and free_pages >= pages // 5:
                connection.execute('PRAGMA incremental_vacuum(%d)' % RECLAIM_PAGES).fetchall()
                connection.commit()
