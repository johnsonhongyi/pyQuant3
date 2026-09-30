"""Verified streaming compression before replacing or removing diagnostic files."""
import gzip
import hashlib
import os
import tempfile
import json


def archive_verified(source, target):
    os.makedirs(os.path.dirname(target), exist_ok=True)
    version = os.stat(source)
    digest = hashlib.sha256()
    fd, temporary = tempfile.mkstemp(prefix='.archive_', dir=os.path.dirname(target))
    try:
        with os.fdopen(fd, 'wb') as raw:
            with gzip.GzipFile(fileobj=raw, mode='wb', compresslevel=3) as writer:
                with open(source, 'rb') as reader:
                    for chunk in iter(lambda: reader.read(1024 * 1024), b''):
                        digest.update(chunk)
                        writer.write(chunk)
            raw.flush()
            os.fsync(raw.fileno())
        verified = hashlib.sha256()
        with gzip.open(temporary, 'rb') as reader:
            for chunk in iter(lambda: reader.read(1024 * 1024), b''):
                verified.update(chunk)
        current = os.stat(source)
        if digest.digest() != verified.digest() or (version.st_mtime_ns, version.st_size) != (current.st_mtime_ns, current.st_size):
            raise OSError('Source changed or archive verification failed')
        os.replace(temporary, target)
        return target
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)


def backup_large_evaluation(path):
    try:
        stat = os.stat(path)
    except FileNotFoundError:
        return
    if stat.st_size < 4 * 1024 * 1024:
        return
    target = os.path.join(os.path.dirname(path), 'archive',
                          os.path.basename(path) + '.legacy.%s.gz' % stat.st_mtime_ns)
    if not os.path.exists(target):
        archive_verified(path, target)


def write_json_gzip(path, value):
    """Called by the archive timer, never by a GUI or per-quote slot."""
    path = path[:-3] if path.endswith('.gz') else path
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.archive_json_', dir=directory)
    try:
        with os.fdopen(fd, 'wb') as raw:
            with gzip.GzipFile(fileobj=raw, mode='wb', compresslevel=3) as packed:
                payload = json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
                packed.write(payload.encode('utf-8'))
            raw.flush()
            os.fsync(raw.fileno())
        from ats.persistence_lock import replace_with_retry
        replace_with_retry(temporary, path + '.gz')
        if os.path.exists(path):
            try:
                archive_verified(path, path + '.legacy.gz')
                os.remove(path)
            except OSError:
                import logging
                logging.getLogger('ATS.ArchiveCache').warning('Legacy migration deferred: %s', path)
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)


def append_jsonl_gzip(path, records):
    """Write each archive interval as an atomic compressed segment, preserving all events."""
    import uuid
    from datetime import datetime
    directory = path + '.parts'
    os.makedirs(directory, exist_ok=True)
    name = datetime.now().strftime('%Y%m%d_%H%M%S_%f') + '_' + uuid.uuid4().hex[:8] + '.jsonl.gz'
    fd, temporary = tempfile.mkstemp(prefix='.segment_', dir=directory)
    try:
        with os.fdopen(fd, 'wb') as raw:
            with gzip.GzipFile(fileobj=raw, mode='wb', compresslevel=3) as writer:
                for record in records:
                    writer.write((json.dumps(record, ensure_ascii=False, separators=(',', ':')) + '\n').encode('utf-8'))
            raw.flush()
            os.fsync(raw.fileno())
        os.replace(temporary, os.path.join(directory, name))
        _trace_tail.cache_clear()
        _trace_index.cache_clear()
        _trace_code.cache_clear()
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)


def iter_archive_lines(path, include_pending=True):
    import glob
    files = [path + '.gz'] if os.path.exists(path + '.gz') else ([path] if os.path.exists(path) else [])
    files += sorted(glob.glob(os.path.join(path + '.parts', '*.jsonl.gz')))
    for filename in files:
        opener = gzip.open if filename.endswith('.gz') else open
        with opener(filename, 'rt', encoding='utf-8') as reader:
            yield from reader
    if include_pending:
        from ats.bounded_evaluation_store import evaluation_store
        for record in evaluation_store.buffered_records(path):
            yield json.dumps(record, ensure_ascii=False) + '\n'


def remove_expired_reconciliation_segments(root, retention_days, today):
    """Apply the existing daily retention to compressed parts; preserve unknown files."""
    import re
    from pathlib import Path
    from datetime import datetime
    removed = []
    if retention_days is None:
        return removed
    root = Path(root).resolve()
    for directory in root.glob('reconciliation_*.jsonl.parts'):
        match = re.fullmatch(r'reconciliation_(\d{8})\.jsonl\.parts', directory.name)
        if not match or not directory.is_dir() or directory.resolve().parent != root:
            continue
        try:
            day = datetime.strptime(match.group(1), '%Y%m%d').date()
        except ValueError:
            continue
        if (today - day).days < retention_days:
            continue
        for segment in directory.glob('*.jsonl.gz'):
            if segment.is_file() and segment.resolve().parent == directory.resolve():
                try:
                    segment.unlink()
                    removed.append(str(segment.relative_to(root)))
                except OSError:
                    pass
        try:
            directory.rmdir()
        except OSError:
            pass
    return removed


from functools import lru_cache


@lru_cache(maxsize=8)
def _trace_tail(path, interval, limit):
    """Visit newest segments first instead of decompressing the entire history."""
    import glob
    from collections import deque
    files = sorted(glob.glob(os.path.join(path + '.parts', '*.jsonl.gz')), reverse=True)
    if os.path.exists(path + '.gz'):
        files.append(path + '.gz')
    elif os.path.exists(path):
        files.append(path)
    newest = []
    for filename in files:
        opener = gzip.open if filename.endswith('.gz') else open
        with opener(filename, 'rt', encoding='utf-8') as reader:
            lines = deque((line for line in reader if line.strip()), maxlen=limit - len(newest))
        newest.extend(reversed(lines))
        if len(newest) >= limit:
            break
    return tuple(newest)


def load_trace_tail(path, limit=150):
    import time
    from ats.bounded_evaluation_store import evaluation_store
    pending = evaluation_store.buffered_records(path)[-limit:]
    lines = [json.dumps(record, ensure_ascii=False) for record in reversed(pending)]
    if len(lines) < limit:
        lines.extend(_trace_tail(path, int(time.monotonic() // 1800), limit)[:limit - len(lines)])
    return lines


@lru_cache(maxsize=8)
def _trace_index(path, interval):
    latest = {}
    for line in reversed(_trace_tail(path, interval, 5000)):
        try:
            record = json.loads(line)
            code = record.get('signal', {}).get('code') or record.get('intent', {}).get('code')
            if code:
                latest[str(code).strip()] = record
        except (ValueError, TypeError, AttributeError):
            continue
    return latest


@lru_cache(maxsize=128)
def _trace_code(path, interval, code):
    """Preserve older sparse signals without indexing the entire archive upfront."""
    result = {}
    for line in iter_archive_lines(path, include_pending=False):
        try:
            record = json.loads(line)
            current = record.get('signal', {}).get('code') or record.get('intent', {}).get('code')
            if str(current).strip() == code:
                result = record
        except (ValueError, TypeError, AttributeError):
            continue
    return result


def load_latest_trace(path, code):
    """Run on a worker; reuse the archive index for each 30-minute interval."""
    import time
    import copy
    from ats.bounded_evaluation_store import evaluation_store
    interval = int(time.monotonic() // 1800)
    result = _trace_index(path, interval).get(str(code).strip())
    if result is None:
        result = _trace_code(path, interval, str(code).strip())
    for record in evaluation_store.buffered_records(path):
        current = record.get('signal', {}).get('code') or record.get('intent', {}).get('code')
        if str(current).strip() == str(code).strip():
            result = record
    return copy.deepcopy(result)
