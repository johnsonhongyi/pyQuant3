import os
import re
import time
import pandas as pd
from io import BytesIO

forward_dir = '/data/InStock/instock/forwardp'

# 仅筛选出标准 6 位代码股票文件
all_entries = [entry for entry in os.scandir(forward_dir) if entry.is_file()]
stock_files = []
for entry in all_entries:
    name = entry.name.upper()
    if not name.endswith('.TXT'):
        continue
    match = re.match(r'^(?:BJ|SH|SZ)?(\d{6})\.TXT$', name)
    if match:
        stock_files.append((name, entry.path))

print(f"Found {len(stock_files)} valid TDX stock files. Benchmarking on first 300...")
test_files = stock_files[:300]

_COLUMNS = ['date', 'open', 'high', 'low', 'close', 'vol', 'amount']

# 1. 基线方式：4次 os.path.isfile + pd.read_csv 全量读取
t0 = time.perf_counter()
baseline_frames = {}
total_bytes_baseline = 0
for name, path in test_files:
    if os.path.isfile(path):
        total_bytes_baseline += os.path.getsize(path)
        try:
            frame = pd.read_csv(
                path, header=None, names=_COLUMNS, usecols=range(7),
                dtype={'date': str}, encoding='gb18030', on_bad_lines='skip',
            )
            frame['date'] = pd.to_datetime(frame['date'].str.strip(), errors='coerce')
            for col in _COLUMNS[1:]:
                frame[col] = pd.to_numeric(frame[col], errors='coerce')
            frame = frame.dropna(subset=_COLUMNS).drop_duplicates('date', keep='last')
            frame = frame.loc[(frame['open'] > 0) & (frame['close'] > 0)]
            baseline_frames[name] = frame.iloc[-600:]
        except Exception:
            pass
t_baseline = time.perf_counter() - t0
print(f"Baseline (full read): {t_baseline:.3f}s, read {total_bytes_baseline / 1024:.1f} KB, loaded {len(baseline_frames)}")

# 2. 优化方式：内存目录哈希索引 + 末尾 seek 跳读
t_idx0 = time.perf_counter()
# 构建内存目录哈希索引
index = {}
for entry in os.scandir(forward_dir):
    if entry.is_file():
        name_upper = entry.name.upper()
        if name_upper.endswith('.TXT'):
            stem = name_upper[:-4]
            index[stem] = entry.path
            if stem.startswith(('BJ', 'SH', 'SZ')):
                index[stem[2:]] = entry.path
t_index = time.perf_counter() - t_idx0
print(f"Directory index built in {t_index*1000:.2f} ms ({len(index)} keys)")

t1 = time.perf_counter()
optimized_frames = {}
total_bytes_optimized = 0
min_rows = 600
estimate_bytes = (min_rows + 100) * 100  # 70,000 bytes

for name, path in test_files:
    stem = name[:-4]
    matched_path = index.get(stem)
    if matched_path:
        file_size = os.path.getsize(matched_path)
        frame = None
        if file_size > estimate_bytes * 1.3:
            try:
                with open(matched_path, 'rb') as fp:
                    fp.seek(file_size - estimate_bytes)
                    fp.readline()
                    tail_bytes = fp.read()
                total_bytes_optimized += len(tail_bytes)
                frame = pd.read_csv(
                    BytesIO(tail_bytes), header=None, names=_COLUMNS, usecols=range(7),
                    dtype={'date': str}, encoding='gb18030', on_bad_lines='skip',
                )
                if len(frame) < min_rows:
                    frame = None  # 行数不足，触发回退
            except Exception:
                frame = None

        if frame is None:
            # 回退全量读
            total_bytes_optimized += file_size
            try:
                frame = pd.read_csv(
                    matched_path, header=None, names=_COLUMNS, usecols=range(7),
                    dtype={'date': str}, encoding='gb18030', on_bad_lines='skip',
                )
            except Exception:
                continue

        try:
            frame['date'] = pd.to_datetime(frame['date'].str.strip(), errors='coerce')
            for col in _COLUMNS[1:]:
                frame[col] = pd.to_numeric(frame[col], errors='coerce')
            frame = frame.dropna(subset=_COLUMNS).drop_duplicates('date', keep='last')
            frame = frame.loc[(frame['open'] > 0) & (frame['close'] > 0)]
            optimized_frames[name] = frame.iloc[-600:]
        except Exception:
            pass

t_opt = time.perf_counter() - t1
io_reduction = (1 - total_bytes_optimized / total_bytes_baseline) * 100
speedup = t_baseline / t_opt if t_opt > 0 else 1.0
print(f"Optimized (tail seek + memory index): {t_opt:.3f}s, read {total_bytes_optimized / 1024:.1f} KB (I/O reduced {io_reduction:.1f}%, speedup {speedup:.2f}x)")

# 3. 优化并发方式：受限 3 个 Worker 并发读取（严格遵守 CPU < 300% 门禁）
import concurrent.futures

def _load_single(item):
    name, path = item
    stem = name[:-4]
    matched_path = index.get(stem)
    if not matched_path:
        return name, None
    file_size = os.path.getsize(matched_path)
    frame = None
    if file_size > estimate_bytes * 1.3:
        try:
            with open(matched_path, 'rb') as fp:
                fp.seek(file_size - estimate_bytes)
                fp.readline()
                tail_bytes = fp.read()
            frame = pd.read_csv(
                BytesIO(tail_bytes), header=None, names=_COLUMNS, usecols=range(7),
                dtype={'date': str}, encoding='gb18030', on_bad_lines='skip',
            )
            if len(frame) < min_rows:
                frame = None
        except Exception:
            frame = None

    if frame is None:
        try:
            frame = pd.read_csv(
                matched_path, header=None, names=_COLUMNS, usecols=range(7),
                dtype={'date': str}, encoding='gb18030', on_bad_lines='skip',
            )
        except Exception:
            return name, None

    try:
        frame['date'] = pd.to_datetime(frame['date'].str.strip(), errors='coerce')
        for col in _COLUMNS[1:]:
            frame[col] = pd.to_numeric(frame[col], errors='coerce')
        frame = frame.dropna(subset=_COLUMNS).drop_duplicates('date', keep='last')
        frame = frame.loc[(frame['open'] > 0) & (frame['close'] > 0)]
        return name, frame.iloc[-600:]
    except Exception:
        return name, None

t2 = time.perf_counter()
concurrent_frames = {}
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
    for name, f in pool.map(_load_single, test_files):
        if f is not None:
            concurrent_frames[name] = f
t_concurrent = time.perf_counter() - t2
speedup_concurrent = t_baseline / t_concurrent if t_concurrent > 0 else 1.0
print(f"Optimized (3-worker concurrent + seek + index): {t_concurrent:.3f}s, loaded {len(concurrent_frames)} (speedup vs baseline {speedup_concurrent:.2f}x)")

# 4. 严格数据一致性核验
mismatches = 0
for name in baseline_frames:
    b = baseline_frames[name].reset_index(drop=True)
    o = concurrent_frames.get(name)
    if o is None:
        mismatches += 1
        continue
    o = o.reset_index(drop=True)
    if not b.equals(o):
        mismatches += 1

print(f"Data verification: {mismatches} mismatches out of {len(baseline_frames)} frames.")
