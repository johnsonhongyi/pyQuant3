"""Persistent prepared arrays, mmap reads, atomic versioned replacement with unified thick baseline."""
import json
import os
from pathlib import Path
import tempfile
import datetime
import logging

import numpy as np
import pandas as pd

UNIFIED_BASE_ROWS = 600
_LOOKBACK_PROFILES = (1000, 600, 310, 260, 210, 150)
_METADATA_CACHE = {}
_GLOBAL_MANIFEST = {}


def _load_manifest(parent_dir):
    """Load unified manifest.json for zero-IO metadata access."""
    manifest_path = Path(parent_dir) / 'manifest.json'
    try:
        stat = os.stat(manifest_path)
        cache_key = (str(parent_dir), stat.st_mtime_ns)
        cached = _GLOBAL_MANIFEST.get(cache_key)
        if cached is not None:
            return cached
        data = json.loads(manifest_path.read_text(encoding='utf-8'))
        if isinstance(data, dict):
            if len(_GLOBAL_MANIFEST) > 16:
                _GLOBAL_MANIFEST.clear()
            _GLOBAL_MANIFEST[cache_key] = data
            return data
    except (OSError, ValueError, KeyError):
        pass
    return None


def save_manifest(directory):
    """Scan directory and aggregate all *-600.meta.json (or *-1000) into a single manifest.json."""
    parent = Path(directory)
    manifest = {}
    meta_files = list(parent.glob(f'*-{UNIFIED_BASE_ROWS}.meta.json'))
    if not meta_files:
        meta_files = list(parent.glob('*-1000.meta.json'))
    for meta_file in meta_files:
        symbol = meta_file.name.split('-')[0]
        info = _load_metadata(meta_file)
        if info:
            manifest[symbol] = info

    if not manifest:
        return None

    try:
        parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=parent, suffix='.manifest.tmp')
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, ensure_ascii=False)
        target = parent / 'manifest.json'
        os.replace(tmp_path, target)
        stat = os.stat(target)
        _GLOBAL_MANIFEST[(str(parent), stat.st_mtime_ns)] = manifest
        logging.info("Saved unified manifest.json with %d entries", len(manifest))
        return target
    except OSError as exc:
        logging.warning("Failed to save manifest.json: %s", exc)
        return None


def is_history_cache_ready(directory=None, min_entries=3000):
    """Check if the thick history cache manifest is ready and sufficiently warm."""
    try:
        if directory is None:
            import instock.core.stockfetch as stf
            directory = getattr(stf, 'stock_hist_cache_path', None)
        if not directory:
            return False
        manifest = _load_manifest(directory)
        return bool(manifest and len(manifest) >= min_entries)
    except Exception:
        return False


def _load_metadata(metadata_path, symbol=None, parent=None):
    # 1. 优先从集中式 manifest 中获取（0 磁盘 I/O）
    if parent is not None and symbol is not None:
        manifest = _load_manifest(parent)
        if manifest and symbol in manifest:
            return manifest[symbol]

    # 2. 回退到单文件 meta.json
    try:
        stat = os.stat(metadata_path)
        cache_key = (str(metadata_path), stat.st_mtime_ns)
        cached = _METADATA_CACHE.get(cache_key)
        if cached is not None:
            return cached
        info = json.loads(Path(metadata_path).read_text(encoding='utf-8'))
        if len(_METADATA_CACHE) > 12000:
            _METADATA_CACHE.clear()
        _METADATA_CACHE[cache_key] = info
        return info
    except (OSError, ValueError, KeyError):
        return None


def prepared_history(cache_path, fingerprint, loader, *, _lookback=None, _allow_loader=True):
    lookback = max(60, min(UNIFIED_BASE_ROWS, int(_lookback or os.environ.get('INSTOCK_HIST_LOOKBACK_ROWS', '150'))))
    stem = Path(cache_path).stem
    parent = Path(cache_path).parent
    symbol = stem.split('-')[0]

    epoch = os.environ.get('INSTOCK_HISTORY_CACHE_EPOCH')
    source_version = json.dumps(fingerprint[5]) if len(fingerprint) > 5 else None

    # 1. 向下兼容的长周期自动裁切检索：从大到小探测大于等于 lookback 的基线缓存
    # 统一优先复用 1000 行加厚基线，向下兼容 310, 260, 210, 150
    candidate_profiles = [lookback] + [rows for rows in _LOOKBACK_PROFILES if rows > lookback]
    candidate_profiles = sorted(set(candidate_profiles), reverse=True)

    for cand_rows in candidate_profiles:
        cand_path = parent / f"{stem}-{cand_rows}.npy"
        cand_meta = cand_path.with_suffix('.meta.json')
        if not cand_path.exists():
            continue

        info = _load_metadata(cand_meta, symbol=symbol if cand_rows == UNIFIED_BASE_ROWS else None, parent=parent)
        if not info:
            continue

        cand_signature = (fingerprint[2:4], fingerprint[4], epoch, cand_rows) if epoch else (fingerprint, cand_rows)
        cand_version = json.dumps(cand_signature, ensure_ascii=False, sort_keys=True)

        # 校验版本签名或盘前同一 epoch 基线
        version_matched = (info.get('version') == cand_version)
        epoch_matched = bool(epoch and source_version and info.get('source_version') == source_version
                             and info.get('profile') == json.dumps(cand_signature[:2]))

        if not (version_matched or epoch_matched):
            continue

        # 若版本有微调则平滑刷写元数据
        if not version_matched and epoch_matched:
            info['version'] = cand_version
            try:
                fd, tmp_meta = tempfile.mkstemp(dir=parent, suffix='.meta.tmp')
                with os.fdopen(fd, 'w', encoding='utf-8') as s:
                    json.dump(info, s, ensure_ascii=False)
                os.replace(tmp_meta, cand_meta)
                _METADATA_CACHE.pop((str(cand_meta), os.stat(cand_meta).st_mtime_ns), None)
            except OSError:
                pass

        try:
            try:
                mapped = np.load(cand_path, mmap_mode='r', allow_pickle=False)
            except OSError:
                mapped = np.load(cand_path, allow_pickle=False)

            try:
                total_len = len(mapped)
                # 核心机制：向下自动零拷贝裁切！仅提取末尾 lookback 行
                slice_len = min(total_len, lookback)
                sub_mapped = mapped[-slice_len:] if total_len > slice_len else mapped

                values = {}
                for name in info.get('columns', []):
                    if name in info.get('constants', {}):
                        values[name] = info['constants'][name]
                    elif name == 'date':
                        values[name] = sub_mapped[name].astype('datetime64[D]').astype('U10')
                    else:
                        values[name] = sub_mapped[name].copy()
                frame = pd.DataFrame(values)
            finally:
                if hasattr(mapped, '_mmap'):
                    mapped._mmap.close()

            from JSONData.history_cache import _count
            _count('prepared_hits')
            return frame
        except (OSError, ValueError, KeyError, TypeError) as exc:
            logging.debug('Prepared history load/slice failed for %s (%s): %s', stem, cand_rows, exc)
            continue

    if not _allow_loader or loader is None:
        return None

    # 2. 没有任何可用缓存，调用 loader 获取底层原始全量数据
    frame = loader()
    if frame is None or frame.empty:
        return frame

    # 3. 统一长周期加厚写入：强制以 UNIFIED_BASE_ROWS (1000) 行基线入盘
    # 彻底杜绝多周期小文件生成与反复冷构建！
    base_frame = frame.tail(UNIFIED_BASE_ROWS).reset_index(drop=True)
    target_path = parent / f"{stem}-{UNIFIED_BASE_ROWS}.npy"
    target_meta = target_path.with_suffix('.meta.json')
    signature = (fingerprint[2:4], fingerprint[4], epoch, UNIFIED_BASE_ROWS) if epoch else (fingerprint, UNIFIED_BASE_ROWS)
    version = json.dumps(signature, ensure_ascii=False, sort_keys=True)

    arrays = {}
    constants = {}
    for name in base_frame.columns:
        if name == 'date':
            arrays[name] = pd.to_datetime(base_frame[name]).to_numpy(dtype='datetime64[D]').astype('int32')
        elif base_frame[name].nunique(dropna=False) == 1:
            value = base_frame[name].iloc[0]
            constants[name] = value.item() if hasattr(value, 'item') else value
        elif base_frame[name].dtype.kind == 'O':
            arrays[name] = base_frame[name].astype(str).to_numpy(dtype='U64')
        else:
            arrays[name] = base_frame[name].to_numpy()

    records = np.empty(len(base_frame), dtype=[(name, array.dtype) for name, array in arrays.items()])
    for name, array in arrays.items():
        records[name] = array

    temporary = None
    meta_temporary = None
    try:
        parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(dir=parent, suffix='.npy.tmp')
        with os.fdopen(fd, 'wb') as stream:
            np.save(stream, records, allow_pickle=False)
        fd, meta_temporary = tempfile.mkstemp(dir=parent, suffix='.meta.tmp')
        meta_dict = dict(version=version, columns=list(base_frame.columns), constants=constants,
                         source_version=source_version, profile=json.dumps(signature[:2]))
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(meta_dict, stream, ensure_ascii=False)
        os.replace(temporary, target_path)
        os.replace(meta_temporary, target_meta)
        _METADATA_CACHE.pop((str(target_meta), os.stat(target_meta).st_mtime_ns), None)
    except OSError:
        pass
    finally:
        for candidate in (temporary, meta_temporary):
            if candidate and os.path.exists(candidate):
                try:
                    os.unlink(candidate)
                except OSError:
                    pass

    # 返回调用方请求的窗口大小
    if len(base_frame) > lookback:
        return base_frame.tail(lookback).reset_index(drop=True)
    return base_frame
