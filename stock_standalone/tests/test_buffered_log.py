# -*- coding: utf-8 -*-
"""BufferedRamLogHandler 行为验证：正文保留 / 抑制聚合 / 轮转保留历史。

注意：去重 key 包含 pathname+lineno（调用点），因此所有重复场景必须从同一行发起，
这与生产环境（同一条 logger.warning 调用反复执行）一致。
"""
import logging
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import linkage_storage  # noqa: E402
from JohnsonUtil.buffered_log import BufferedRamLogHandler  # noqa: E402

tmpdir = None
results = []


def make_logger(name, path, max_bytes):
    h = BufferedRamLogHandler(path, maxBytes=max_bytes, encoding="utf-8")
    h.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s:%(name)s: %(message)s"))
    h.INTERVAL = 3600  # 手动 flush，避免后台线程干扰
    log = logging.getLogger(name)
    log.handlers = [h]
    log.setLevel(logging.DEBUG)
    log.propagate = False
    return h, log


def check(label, cond):
    results.append((label, cond))
    print("  %-32s %s" % (label, "PASS" if cond else "FAIL"))


# 统一调用点：模拟生产里同一条 logger.warning 反复执行
def emit_reject(logger):
    logger.warning("[T+1 Rule Gate] Rejected SELL order for 300540. available=0.0")


def run_all_checks():
    """在函数内临时把 runtime_file 指向本地路径，结束后恢复，避免污染同进程其它测试。"""
    global tmpdir
    tmpdir = tempfile.mkdtemp()
    results.clear()
    original = linkage_storage.runtime_file
    linkage_storage.runtime_file = lambda p, max_bytes=0: p
    try:
        return _run_all_checks()
    finally:
        linkage_storage.runtime_file = original


def test_buffered_ram_log_handler():
    assert run_all_checks(), [l for l, ok in results if not ok]


def _run_all_checks():
    # ══════════ 场景 A：去重必须保留正文 + 抑制窗口聚合 ══════════
    print("=== A. 去重与抑制 ===")
    path_a = os.path.join(tmpdir, "a.log")
    h, log = make_logger("audit.a", path_a, 1 << 20)

    for _ in range(5):
        emit_reject(log)
    h.flush()

    with open(path_a, encoding="utf-8") as f:
        lines1 = [l for l in f if "T+1 Rule Gate" in l]
    check("5 次重复只落 1 行", len(lines1) == 1)
    check("落盘保留完整正文", "Rejected SELL order for 300540" in "".join(lines1))
    check("计数正确 repeat_count=5", "repeat_count=5" in lines1[0])

    for _ in range(3):  # 抑制窗口内，不应新增行
        emit_reject(log)
    h.flush()
    with open(path_a, encoding="utf-8") as f:
        lines2 = [l for l in f if "T+1 Rule Gate" in l]
    check("抑制窗口内不新增行", len(lines2) == 1)

    # 强制抑制窗口过期（回退到窗口之外，但仍在 TTL 之内），再补写一次，计数应累加到 10（5 + 3 + 2）
    import time as _t
    expired_ts = _t.monotonic() - h.REPEAT_SUPPRESS - 1.0
    for k in list(h._seen.keys()):
        h._seen[k] = [h._seen[k][0], expired_ts]
    for _ in range(2):
        emit_reject(log)
    h.flush()
    with open(path_a, encoding="utf-8") as f:
        lines3 = [l for l in f if "T+1 Rule Gate" in l]
    check("窗口过期后补写 1 行", len(lines3) == 2)
    check("累计计数到 10", "repeat_count=10" in lines3[-1])
    check("补写行仍有正文", "Rejected SELL order for 300540" in lines3[-1])

    log.info("第一条不同消息")
    log.info("第二条不同消息")
    h.flush()
    with open(path_a, encoding="utf-8") as f:
        content = f.read()
    check("不同消息各自独立成行", "第一条不同消息" in content and "第二条不同消息" in content)
    h.close()

    # ══════════ 场景 B：轮转保留历史，不原地截断 ══════════
    print("\n=== B. 轮转 ===")
    path_b = os.path.join(tmpdir, "b.log")
    h2, log2 = make_logger("audit.b", path_b, 8192)
    log2.info("【最早的一行】必须在轮转后仍然可读")
    h2.flush()
    for i in range(60):
        log2.info("填充 %03d %s" % (i, "y" * 40))
        if i % 10 == 0:
            h2.flush()
    h2.flush()
    h2.close()

    files_b = [n for n in sorted(os.listdir(tmpdir)) if n.startswith("b.log")]
    check("产生轮转备份文件", len(files_b) >= 2)
    merged = ""
    for n in files_b:
        with open(os.path.join(tmpdir, n), encoding="utf-8") as f:
            merged += f.read()
    check("早期内容未被抹掉", "最早的一行" in merged)
    check("写入行数无丢失", merged.count("填充") == 60)

    # ══════════ 汇总 ══════════
    print("\n=== 汇总 ===")
    failed = [l for l, ok in results if not ok]
    print("  通过 %d / %d" % (len(results) - len(failed), len(results)))
    if failed:
        print("  失败:", failed)
        return False
    print("  全部通过")
    return True


if __name__ == "__main__":
    ok = run_all_checks()
    sys.exit(0 if ok else 1)
