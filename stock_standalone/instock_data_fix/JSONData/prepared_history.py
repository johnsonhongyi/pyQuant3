"""Persistent prepared arrays, mmap reads, atomic versioned replacement."""
import json
import os
from pathlib import Path
import tempfile
import datetime
import logging

import numpy as np
import pandas as pd


def prepared_history(cache_path, fingerprint, loader, *, _lookback=None, _allow_loader=True):
    lookback = max(60, min(1000, int(_lookback or os.environ.get('INSTOCK_HIST_LOOKBACK_ROWS', '150'))))
    path = Path(cache_path).with_name(Path(cache_path).stem + '-%s.npy' % lookback)
    metadata = path.with_suffix('.meta.json')
    # The immutable baseline is refreshed once per premarket epoch. Today's
    # quote/bar is merged outside this store; no intraday baseline rebuilds.
    epoch = os.environ.get('INSTOCK_HISTORY_CACHE_EPOCH')
    signature = (fingerprint[2:4], fingerprint[4], epoch, lookback) if epoch else (fingerprint, lookback)
    version = json.dumps(signature, ensure_ascii=False, sort_keys=True)
    try:
        info = json.loads(metadata.read_text(encoding='utf-8'))
        if info['version'] == version or (epoch and info.get('source_version') == json.dumps(fingerprint[5])
                                         and info.get('profile') == json.dumps(signature[:2])):
            if info['version'] != version:
                info['version'] = version
                fd, name = tempfile.mkstemp(dir=path.parent, suffix='.meta.tmp')
                try:
                    with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                        json.dump(info, stream, ensure_ascii=False)
                    os.replace(name, metadata)
                finally:
                    if os.path.exists(name):
                        os.unlink(name)
            try:
                mapped = np.load(path, mmap_mode='r', allow_pickle=False)
            except OSError:
                mapped = np.load(path, allow_pickle=False)
            try:
                # A batch owns its arrays; no cached mutable DataFrame is shared.
                values = {}
                for name in info['columns']:
                    if name in info['constants']:
                        values[name] = info['constants'][name]
                    elif name == 'date':
                        values[name] = mapped[name].astype('datetime64[D]').astype('U10')
                    else:
                        values[name] = mapped[name].copy()
                frame = pd.DataFrame(values)
            finally:
                if hasattr(mapped, '_mmap'):
                    mapped._mmap.close()
            from JSONData.history_cache import _count
            _count('prepared_hits')
            return frame
    except (OSError, ValueError, KeyError, TypeError) as exc:
        logging.debug('Prepared history miss: %s', exc)
    if not _allow_loader:
        return None
    frame = None
    source_version = json.dumps(fingerprint[5])
    for rows in (210, 260, 310, 1000):
        larger = path.with_name(Path(cache_path).stem + '-%s.npy' % rows)
        if rows <= lookback or not larger.exists():
            continue
        try:
            candidate = prepared_history(cache_path, fingerprint, None, _lookback=rows, _allow_loader=False)
            if candidate is not None:
                # Preserve the actual frozen source version, including intraday changes.
                source_version = json.loads(larger.with_suffix('.meta.json').read_text(encoding='utf-8'))['source_version']
                frame = candidate
                break
        except (OSError, ValueError, KeyError, TypeError):
            continue
    if frame is None:
        frame = loader()
    if frame is None or frame.empty:
        return frame
    frame = frame.tail(lookback).reset_index(drop=True)
    arrays = {}
    constants = {}
    for name in frame.columns:
        if name == 'date':
            arrays[name] = pd.to_datetime(frame[name]).to_numpy(dtype='datetime64[D]').astype('int32')
        elif frame[name].nunique(dropna=False) == 1:
            value = frame[name].iloc[0]
            constants[name] = value.item() if hasattr(value, 'item') else value
        elif frame[name].dtype.kind == 'O':
            arrays[name] = frame[name].astype(str).to_numpy(dtype='U64')
        else:
            arrays[name] = frame[name].to_numpy()
    records = np.empty(len(frame), dtype=[(name, array.dtype) for name, array in arrays.items()])
    for name, array in arrays.items():
        records[name] = array
    temporary = None
    meta_temporary = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(dir=path.parent, suffix='.npy.tmp')
        with os.fdopen(fd, 'wb') as stream:
            np.save(stream, records, allow_pickle=False)
        fd, meta_temporary = tempfile.mkstemp(dir=path.parent, suffix='.meta.tmp')
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(dict(version=version, columns=list(frame.columns), constants=constants,
                           source_version=source_version, profile=json.dumps(signature[:2])), stream, ensure_ascii=False)
        os.replace(temporary, path)
        os.replace(meta_temporary, metadata)
    except OSError:
        # Cache capacity/permissions must not stop the scan.
        pass
    finally:
        for candidate in (temporary, meta_temporary):
            if candidate and os.path.exists(candidate):
                os.unlink(candidate)
    return frame
