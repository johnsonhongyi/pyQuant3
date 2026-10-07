"""Reuse deterministic static scans only while every input fingerprint matches."""
import hashlib
import json
import logging
import os
from pathlib import Path
import tempfile

import pandas as pd


def result_digest(results):
    return hashlib.sha256(json.dumps(sorted(results, key=str), default=str,
                                     sort_keys=True).encode('utf-8')).hexdigest()


def manifest(directory, stocks, quotes, date, rows, epoch, revision, source_signature):
    try:
        return _manifest(directory, stocks, quotes, date, rows, epoch, revision, source_signature)
    except (OSError, ValueError, TypeError) as exc:
        logging.debug('Static manifest unavailable: %s', exc)
        return None


def _normalize_rows(rows):
    if callable(rows):
        try:
            return {
                'default': rows('default'),
                'keep_increasing': rows('cn_stock_strategy_keep_increasing'),
                'backtrace_ma250': rows('cn_stock_strategy_backtrace_ma250'),
                'low_atr': rows('cn_stock_strategy_low_atr'),
                'breakthrough_platform': rows('cn_stock_strategy_breakthrough_platform'),
            }
        except Exception:
            return str(getattr(rows, '__name__', 'custom_rows'))
    return rows


def _manifest(directory, stocks, quotes, date, rows, epoch, revision, source_signature):
    digest = hashlib.sha256()
    norm_rows = _normalize_rows(rows)
    digest.update(json.dumps((str(date), norm_rows, epoch, revision, list(quotes.columns)),
                             sort_keys=True, default=str).encode('utf-8'))
    digest.update(pd.util.hash_pandas_object(quotes, index=False).values.tobytes())

    manifest_file = Path(directory, 'manifest.json')
    if manifest_file.exists():
        try:
            mstat = manifest_file.stat()
            digest.update(json.dumps(('manifest.json', mstat.st_size, mstat.st_mtime_ns)).encode('utf-8'))
        except OSError:
            pass

    base_rows_num = norm_rows.get('default', 150) if isinstance(norm_rows, dict) else norm_rows
    for stock in stocks:
        symbol = str(stock[1]).split('.')[0].zfill(6)
        signatures = [source_signature(stock[1])]
        for suffix in ('.npy', '.meta.json'):
            path = Path(directory, '%s-qfq-%s%s' % (symbol, base_rows_num, suffix))
            try:
                stat = path.stat()
                signatures.append((stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns))
            except OSError:
                signatures.append(None)
        digest.update(json.dumps((stock, signatures), default=str).encode('utf-8'))
    return digest.hexdigest()


def revision(files, version):
    digest = hashlib.sha256(str(version).encode('utf-8'))
    for filename in sorted(set(files)):
        try:
            digest.update(Path(filename).read_bytes())
        except OSError:
            # A missing code source cannot share a previous valid revision.
            digest.update(os.urandom(16))
    return digest.hexdigest()


class StaticResults:
    def __init__(self, directory):
        self.directory = Path(directory)

    def load(self, key, names, dependencies=None):
        if not key:
            return None
        try:
            data = json.loads((self.directory / (key + '.json')).read_text(encoding='utf-8'))
            if data.get('key') != key or data.get('version') != 1:
                return None
            if data['stocks'] < max(1, int(data['requested'] * .7)):
                return None
            for name in names:
                entry = data['strategies'][name]
                if entry.get('dependency') != (dependencies or {}).get(name):
                    return None
                if entry['scan']['errors'] or entry['scan']['result_sha256'] != result_digest(entry['results']):
                    return None
            return data
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def save(self, key, strategies, stocks, requested, gaps):
        if not key or not strategies or any(entry['scan']['errors'] for entry in strategies.values()):
            return
        temporary = None
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            previous = self.load(key, [])
            if previous:
                strategies = dict(previous['strategies'], **strategies)
            fd, temporary = tempfile.mkstemp(dir=self.directory, suffix='.tmp')
            with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                json.dump(dict(version=1, key=key, strategies=strategies, stocks=stocks,
                               requested=requested, gaps=gaps), stream, ensure_ascii=False, default=str)
            os.replace(temporary, self.directory / (key + '.json'))
            files = sorted(self.directory.glob('*.json'), key=lambda path: path.stat().st_mtime_ns)
            for path in files[:-32]:
                if len(path.stem) == 64 and all(char in '0123456789abcdef' for char in path.stem):
                    path.unlink()
        except (OSError, ValueError, TypeError) as exc:
            logging.debug('Static strategy cache unavailable: %s', exc)
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)
