import time
import logging
import pytest
import pandas as pd
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from data_utils import send_code_via_pipe
from system_linkage_quotes import frame_quote_row


def test_send_code_via_pipe_fast_fail_on_missing_pipe():
    """验证当命名管道不存在时立即退出，绝不 sleep(0.5)*5 耗费 2.5 秒"""
    mock_logger = MagicMock()
    non_existent_pipe = r"\\.\pipe\test_non_existent_pipe_12345"
    
    start_time = time.monotonic()
    result = send_code_via_pipe({"cmd": "TEST"}, mock_logger, pipe_name=non_existent_pipe, max_retries=2)
    elapsed = time.monotonic() - start_time
    
    assert result is False
    # 以前需要 2.5 秒以上，现在必须小于 0.2 秒 (甚至毫秒级)
    assert elapsed < 0.2, f"send_code_via_pipe took {elapsed:.3f}s, expected < 0.2s"


def test_frame_quote_row_o1_index_priority():
    """验证 frame_quote_row 优先命中索引，避免全表字符串转换"""
    # 构造包含 2000 行的大 DataFrame
    codes = [f"{i:06d}" for i in range(2000)]
    df = pd.DataFrame({
        "code": codes,
        "now": [10.0 + i * 0.01 for i in range(2000)],
        "trade_date": ["20261023"] * 2000,
    }, index=codes)
    
    start_time = time.monotonic()
    # 连续查询 100 次
    for _ in range(100):
        row = frame_quote_row(df, "000500")
        assert row is not None
        assert row["code"] == "000500"
    elapsed = time.monotonic() - start_time
    
    # 100 次 O(1) 查询应在 0.05 秒以内
    assert elapsed < 0.05, f"100 lookups took {elapsed:.3f}s, expected < 0.05s"


def test_linkage_heartbeat_short_circuit():
    """验证 _linkage_heartbeat_quote_status 遇到 ready 即刻短路返回，无需遍历全部标的"""
    from types import MethodType, SimpleNamespace
    from ats.ui.main_window import ATSMainWindow

    window = SimpleNamespace(
        _linkage_quote_statuses={"000001": "ready", "000002": "stale"},
        _is_market_session_active=lambda: True,
        _linkage_quote_status=lambda code: "ready" if code == "000001" else "unknown",
    )
    window._linkage_heartbeat_quote_status = MethodType(ATSMainWindow._linkage_heartbeat_quote_status, window)

    # 模拟 GlobalFavoriteManager 返回 100 只股票
    class FakeFavoriteManager:
        def get_favorite_stocks(self):
            return [f"{i:06d}" for i in range(1, 101)]

    with patch("global_favorites.GlobalFavoriteManager", FakeFavoriteManager):
        status = window._linkage_heartbeat_quote_status()
        assert status == "ready"


def test_linkage_receipt_worker_warning_suppression(caplog):
    """验证当 TK 管道不可达时，300 秒内只告警一次，后续静默降级为 debug 杜绝刷屏"""
    import queue
    import threading
    from types import MethodType, SimpleNamespace
    from ats.ui.main_window import ATSMainWindow

    window = SimpleNamespace(
        _linkage_receipt_queue=queue.Queue(),
        _linkage_receipt_stop=threading.Event(),
        _linkage_state_lock=threading.Lock(),
        _linkage_last_reported={},
        _linkage_pipe_available=None,
        _linkage_pipe_last_warning_at=0.0,
        _linkage_pipe_last_attempt_at=0.0,
    )
    window._linkage_receipt_worker = MethodType(ATSMainWindow._linkage_receipt_worker, window)

    # 连续放入 3 个心跳包
    window._linkage_receipt_queue.put({"cmd": "WATCHLIST_HEARTBEAT"})
    window._linkage_receipt_queue.put({"cmd": "WATCHLIST_HEARTBEAT"})
    window._linkage_receipt_queue.put({"cmd": "WATCHLIST_HEARTBEAT"})

    # 模拟 send_code_via_pipe 始终返回 False (管道不可达)
    with patch("data_utils.send_code_via_pipe", return_value=False):
        worker_thread = threading.Thread(target=window._linkage_receipt_worker, daemon=True)
        worker_thread.start()

        # 等待队列被消费
        time.sleep(0.3)
        window._linkage_receipt_stop.set()
        worker_thread.join(timeout=1.0)

    # 检查日志：WARNING 级别的日志只能有至多 1 条，不能有 3 条刷屏
    warning_logs = [record for record in caplog.records if record.levelno == logging.WARNING and "ATS watchlist status" in record.message]
    assert len(warning_logs) <= 1, f"Expected at most 1 warning, got {len(warning_logs)}"
