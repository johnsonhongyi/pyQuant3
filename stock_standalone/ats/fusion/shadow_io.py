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
from sys import intern
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


def line_digest(raw):
    """原始行字节摘要，用于跨分片去重。

    旧实现把每条记录再 json.dumps(sort_keys=True) 一次做指纹，单次全量读取
    在 22 万行/220MB 的当日分片上额外付出 6 秒以上纯序列化开销。同一份记录
    在不同副本（RAMDisk / 明文 / 归档）里字节一致，因此直接用行摘要即可，
    语义等价且快两个数量级。
    """
    if isinstance(raw, str):
        raw = raw.encode("utf-8", "surrogatepass")
    return hashlib.blake2b(raw, digest_size=8).digest()


def record_key(row):
    """轻量语义键：同一观测的不同序列化副本视为同一条。

    行摘要能识别字节一致的副本（RAMDisk 镜像、归档）；UI 收盘副本会补全
    名称、追加 _source_ 标记后重新序列化，字节不同但仍是同一条观测，因此
    再用 (code, ts, source) 兜一层。采样间隔远大于 1ms，不会误合并。
    """
    try:
        ts = round(float(row.get("ts") or 0.0), 3)
    except (TypeError, ValueError, OverflowError):
        ts = 0.0
    return (str(row.get("code") or ""), ts, str(row.get("source") or ""))


# 冷字段：UI 只在 tooltip / 赛马入口偶尔读取，常驻内存占单条记录的 6 成以上。
# 精简模式把它们移出常驻记录，只留 (path, offset, length)，需要时按偏移回读原文。
COLD_FIELDS = ("observation_evidence", "track", "reclaim_detail", "legacy")


def _compact_value(value, limit=16):
    """递归驻留键与短字符串；用 type() 派发而不是 isinstance（快一倍以上）。"""
    kind = type(value)
    if kind is dict:
        return {intern(k) if type(k) is str else k: _compact_value(v, limit) for k, v in value.items()}
    if kind is list:
        return [_compact_value(item, limit) for item in value]
    if kind is str and len(value) <= limit:
        return intern(value)
    return value


def intern_tree(obj, limit=16):
    """把 dict 键与短字符串驻留到全局字符串表（对外兼容入口）。"""
    return _compact_value(obj, limit)


def _evidence_reason(evidence):
    if not isinstance(evidence, dict):
        return ""
    try:
        from ats.fusion.observation import observation_reason
    except ImportError:
        return ""
    return observation_reason(evidence)


def compact_record(row, ref=None):
    """生成常驻版记录：驻留字符串 + 剥离冷字段 + 记录回读位置。

    只有在能拿到原始行偏移（明文分片）时才剥离冷字段；压缩归档无偏移可回读，
    保持完整记录，避免历史回看时证据缺失。

    冷字段剥离前先抽出两个极小的派生值（观察结论、跟踪阶段），跨日汇总靠它们
    判定，不必为每条记录回读文件。
    """
    kept = {}
    for key, value in row.items():
        if ref and key in COLD_FIELDS:
            continue
        if type(key) is str:
            key = intern(key)
        kind = type(value)
        if kind is dict or kind is list:
            kept[key] = _compact_value(value)
        elif kind is str and len(value) <= 16:
            kept[key] = intern(value)
        else:
            kept[key] = value
    if ref:
        kept["_raw_ref"] = ref
        reason = _evidence_reason(row.get("observation_evidence"))
        if reason:
            kept["_evidence_reason"] = intern(reason)
        stage = (row.get("track") or {}).get("stage") if isinstance(row.get("track"), dict) else None
        if stage:
            kept["_track_stage"] = intern(str(stage))
    return kept


def hydrate(record):
    """按需把冷字段从原始行回填（tooltip / 赛马入口用），失败则保持精简。"""
    if not isinstance(record, dict):
        return record
    ref = record.get("_raw_ref")
    missing = [key for key in COLD_FIELDS if key not in record]
    if not missing or not isinstance(ref, tuple) or len(ref) != 3:
        return record
    path, offset, length = ref
    try:
        with open(path, "rb") as stream:
            stream.seek(int(offset))
            raw = stream.read(int(length))
        full = json.loads(raw.decode("utf-8-sig"))
    except (OSError, ValueError, TypeError, UnicodeDecodeError):
        return record
    for key in missing:
        if key in full:
            record[key] = full[key]
    record.pop("_raw_ref", None)
    return record


def _iter_lines(path):
    """逐行产出 (行号, 原始行文本)，兼容明文与 gzip。"""
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8-sig") as stream:
        for number, line in enumerate(stream, 1):
            if line.strip():
                yield number, line


def read_paths(paths, max_records=None):
    rows, errors, seen, seen_keys = [], [], set(), set()
    for path in paths:
        part = deque(maxlen=max_records)
        try:
            for number, line in _iter_lines(path):
                try:
                    row = json.loads(line)
                    if not isinstance(row, dict):
                        raise ValueError("record must be an object")
                    part.append((line_digest(line), record_key(row), row))
                except (ValueError, TypeError) as exc:
                    errors.append("{}:{}: {}".format(path, number, exc))
            identities, keys = set(), set()
            for digest, key, row in part:
                # 同一分片内也可能出现重复行（重写/补写），与游标保持同一口径。
                if digest in seen or digest in identities or key in seen_keys or key in keys:
                    continue
                rows.append(row)
                identities.add(digest)
                keys.add(key)
            seen.update(identities)
            seen_keys.update(keys)
        except (OSError, EOFError, UnicodeError, zlib.error) as exc:
            # 压缩损坏时整片拒用，其他 PID 的完整分片仍可读取。
            errors.append("{}: {}".format(path, exc))
    return rows, errors


class DayLogCursor:
    """按天增量读取影子分片：只解析文件新增的尾部字节。

    影子分片在交易时段持续追加，文件指纹每几秒就变。旧实现每次刷新都把整份
    分片重新解析一遍（当日 220MB 约 12.6 秒），而看板每 2 秒刷新一次，导致
    单核长期打满、UI 线程被读取阻塞、临时对象把 RSS 推到 GB 级。

    本游标记录每个分片已消费的字节偏移，稳态（无新增）零解析，新增一行只
    解析一行。跨进程可见性与 read_paths 一致：只认已完整写入的行，不读半个
    JSON。
    """

    __slots__ = ("_max", "_rows", "_seen", "_seen_keys", "_states", "_tails", "_errors",
                 "_version", "_compact")

    def __init__(self, max_records=None, compact=True):
        self._max = int(max_records) if max_records else None
        self._rows = deque(maxlen=self._max)
        self._seen = set()
        self._seen_keys = set()
        self._states = {}   # path -> ("raw", size, mtime_ns, offset) / ("gz", (size, mtime_ns))
        self._tails = {}    # path -> 未成行的尾部字节
        self._errors = []
        self._version = 0
        self._compact = bool(compact)

    @property
    def version(self):
        return self._version

    @property
    def errors(self):
        return list(self._errors)

    def rows(self):
        return list(self._rows)

    def _reset(self):
        """分片被截断或替换：整份数据身份已变，必须重建。"""
        self._rows.clear()
        self._seen.clear()
        self._seen_keys.clear()
        self._tails.clear()

    def _append(self, digest, row, ref=None):
        key = record_key(row)
        if digest in self._seen or key in self._seen_keys:
            return False
        self._seen.add(digest)
        self._seen_keys.add(key)
        self._rows.append(compact_record(row, ref) if self._compact else row)
        return True

    def _forget_old(self):
        """摘要集合兜底上限：摘要本身只有 8 字节，正常一天不会触发。"""
        if len(self._seen) > 400000:
            self._seen.clear()
            self._seen_keys.clear()
            self._seen.update(line_digest(json.dumps(r, sort_keys=True, ensure_ascii=False, default=str))
                              for r in self._rows)
            self._seen_keys.update(record_key(r) for r in self._rows)

    def _read_raw(self, path, offset):
        with open(path, "rb") as stream:
            stream.seek(offset)
            return stream.read()

    def _consume_bytes(self, path, chunk, buf_start):
        buf = self._tails.get(path, b"") + chunk
        parts = buf.split(b"\n")
        self._tails[path] = parts.pop()
        added = 0
        position = buf_start
        for raw in parts:
            line_start, position = position, position + len(raw) + 1
            if not raw.strip():
                continue
            try:
                row = json.loads(raw.decode("utf-8-sig"))
                if not isinstance(row, dict):
                    raise ValueError("record must be an object")
            except (ValueError, TypeError, UnicodeDecodeError) as exc:
                self._errors.append("{}: {}".format(path, exc))
                if len(self._errors) > 50:
                    del self._errors[:25]
                continue
            ref = (path, line_start, len(raw)) if self._compact else None
            if self._append(line_digest(raw), row, ref):
                added += 1
        # 文件末尾可能没有换行：只要尾巴能解析成完整对象就提交，
        # 否则留到下一次 refresh（写端正在写这一行）。
        tail = self._tails.get(path)
        if tail and tail.strip():
            try:
                row = json.loads(tail.decode("utf-8-sig"))
            except (ValueError, TypeError, UnicodeDecodeError):
                return added
            if isinstance(row, dict):
                ref = (path, position, len(tail)) if self._compact else None
                if self._append(line_digest(tail), row, ref):
                    added += 1
                self._tails[path] = b""
        return added

    def refresh(self, paths):
        """把各分片新增的行并入游标，返回是否有变化。"""
        changed = False
        for path in paths:
            try:
                stat = os.stat(path)
            except OSError:
                continue
            state = self._states.get(path)
            if str(path).endswith(".gz"):
                signature = (stat.st_size, stat.st_mtime_ns)
                if state and state[0] == "gz" and state[1] == signature:
                    continue
                try:
                    for number, line in _iter_lines(path):
                        try:
                            row = json.loads(line)
                            if not isinstance(row, dict):
                                raise ValueError("record must be an object")
                        except (ValueError, TypeError) as exc:
                            self._errors.append("{}:{}: {}".format(path, number, exc))
                            continue
                        self._append(line_digest(line), row)
                except (OSError, EOFError, UnicodeError, zlib.error) as exc:
                    self._errors.append("{}: {}".format(path, exc))
                    continue
                self._states[path] = ("gz", signature)
                self._tails.pop(path, None)
                changed = True
                continue

            offset = state[3] if state and state[0] == "raw" else 0
            if stat.st_size < offset:      # 被截断或替换：身份已变，整体重建
                self._reset()
                offset = 0
            if state and state[0] == "raw" and stat.st_size == offset and stat.st_mtime_ns == state[2]:
                continue
            try:
                chunk = self._read_raw(path, offset)
            except OSError as exc:
                self._errors.append("{}: {}".format(path, exc))
                continue
            # 上一轮残留的半行也属于本次 buf，其绝对起点要回退掉它的长度。
            buf_start = offset - len(self._tails.get(path, b""))
            added = self._consume_bytes(path, chunk, buf_start)
            self._states[path] = ("raw", stat.st_size, stat.st_mtime_ns, offset + len(chunk))
            if added or chunk:
                changed = True
        if changed:
            self._version += 1
            self._forget_old()
        return changed
