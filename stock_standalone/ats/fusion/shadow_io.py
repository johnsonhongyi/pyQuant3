"""影子日志分片发现与读取；兼容旧文件、压缩档及 RAMDisk 副本。"""
import gzip
import hashlib
import json
import logging
import math
import os
import re
from collections import deque
from pathlib import Path
import zlib

LOG_NAME = re.compile(r"^(\d{4}-\d{2}-\d{2})(?:_\d+)?\.jsonl(?:\.gz)?$")
logger = logging.getLogger(__name__)


def record_ts(row):
    try:
        value = float(row.get("ts") or 0)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError, OverflowError, AttributeError):
        return None


def file_signature(paths):
    return tuple((p, os.stat(p).st_size, os.stat(p).st_mtime_ns) for p in paths)


def ram_directory(directory):
    try:
        from JohnsonUtil import commonTips as cct
        path = cct.get_ramdisk_path("fusion_shadow.jsonl")
        if path and os.path.isdir(os.path.dirname(path)):
            identity = os.path.normcase(os.path.abspath(directory))
            suffix = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
            return os.path.join(os.path.dirname(path), "fusion_shadow", suffix)
    except (ImportError, OSError, AttributeError, RuntimeError):
        logger.warning("影子 RAMDisk 路径不可用，使用本地目录", exc_info=True)
    return None


def log_directories(directory):
    ram = ram_directory(directory)
    return [directory] + ([ram] if ram else [])


def day_paths(directories, day):
    """每个分片只选一个副本；原始文件优先，其次选择最长副本。"""
    selected = {}
    for directory in directories:
        if not directory:
            continue
        try:
            paths = Path(directory).glob(day + "*.jsonl*")
            for path in paths:
                match = LOG_NAME.fullmatch(path.name)
                if not match or match[1] != day:
                    continue
                stat = path.stat()
                key = path.name.removesuffix(".gz")
                rank = (not path.name.endswith(".gz"), stat.st_size, stat.st_mtime_ns)
                if key not in selected or rank > selected[key][0]:
                    selected[key] = (rank, str(path))
        except OSError as exc:
            logger.warning("扫描影子目录失败 %s: %s", directory, exc)
    return [value[1] for _, value in sorted(selected.items())]


def log_days(directories):
    days = set()
    for directory in directories:
        try:
            for path in Path(directory).glob("*.jsonl*"):
                match = LOG_NAME.fullmatch(path.name)
                if match:
                    days.add(match[1])
        except OSError as exc:
            logger.warning("扫描影子日期失败 %s: %s", directory, exc)
    return sorted(days)


def list_day_files(directory, day):
    """列出指定日期的所有原始文件路径（含 .gz），用于归档和清理。"""
    dirs = log_directories(directory) if directory else []
    return day_paths(dirs, day)


def day_has_records(directory, day):
    """快速判断指定日期是否存在任何记录文件。"""
    dirs = log_directories(directory) if directory else []
    return bool(day_paths(dirs, day))


def iter_day_records(directory, day):
    """迭代指定日期的所有影子记录（跨分片、跨格式、跨目录）。

    查找顺序与降级：
    1. 优先扫描目录及其 RAMDisk 副本中的明文分片（{day}.jsonl 与 {day}_{pid}.jsonl）
    2. 无明文分片时自动降级至压缩归档（{day}*.jsonl.gz）
    
    Yields: dict（每条 json.loads 后的记录）
    跳过解析失败的行，不中断迭代。
    """
    paths = list_day_files(directory, day)
    records, errors = read_paths(paths)
    if errors:
        if any(error.startswith(str(path) + ": ") for error in errors for path in paths):
            raise ValueError("影子分片读取不完整: {}".format(errors[:5]))
        logger.warning("跳过影子日志坏行: %s", errors[:5])
    yield from records


def read_paths(paths, max_records=None):
    rows, errors, seen = [], [], set()
    for path in paths:
        part = deque(maxlen=max_records)
        try:
            opener = gzip.open if str(path).endswith(".gz") else open
            with opener(path, "rt", encoding="utf-8-sig") as stream:
                for number, line in enumerate(stream, 1):
                    if not line.strip():
                        continue
                    try:
                        row = json.loads(line)
                        if not isinstance(row, dict):
                            raise ValueError("record must be an object")
                        part.append(row)
                    except (ValueError, TypeError) as exc:
                        errors.append("{}:{}: {}".format(path, number, exc))
            identities = set()
            for row in part:
                # 兼容旧 UI 收盘副本：名称补全及 UI 来源标记不构成新观测。
                identity = json.dumps({k: v for k, v in row.items()
                                       if k != "name" and not k.startswith("_source_")},
                                      sort_keys=True, ensure_ascii=False)
                if identity not in seen:
                    rows.append(row)
                identities.add(identity)
            seen.update(identities)
        except (OSError, EOFError, UnicodeError, zlib.error) as exc:
            # 压缩损坏时整片拒用，其他 PID 的完整分片仍可读取。
            errors.append("{}: {}".format(path, exc))
    return rows, errors
