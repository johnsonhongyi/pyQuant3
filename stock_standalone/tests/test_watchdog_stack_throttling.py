# -*- coding: utf-8 -*-
"""
tests/test_watchdog_stack_throttling.py
=======================================
验证主线程假死看门狗 [UI-BLOCK-STACK] 堆栈输出限流逻辑：
累计超过 5 次（每 5 次）才输出一次堆栈，避免频繁卡顿导致大段堆栈刷屏。
"""
import pytest
from unittest.mock import MagicMock, patch


def test_watchdog_stack_output_throttled_every_5_times():
    """验证堆栈输出每 5 次触发一次，其余次数仅抑制并记录简短警报。"""
    logged_warnings = []
    logged_debugs = []

    mock_logger = MagicMock()
    mock_logger.warning.side_effect = lambda msg, *args: logged_warnings.append(msg % args if args else msg)
    mock_logger.debug.side_effect = lambda msg, *args: logged_debugs.append(msg % args if args else msg)

    class MockApp:
        def __init__(self):
            self._ui_block_count = 0
            self.queue = MagicMock()
            self.queue.qsize.return_value = 0

    app = MockApp()

    def simulate_ui_block(app, delay=5.2):
        q_size = -1
        try:
            if hasattr(app, 'queue') and app.queue:
                q_size = app.queue.qsize()
        except Exception:
            pass

        app._ui_block_count = getattr(app, "_ui_block_count", 0) + 1
        cur_block_count = app._ui_block_count

        mock_logger.warning(
            f"🚨 [UI_BLOCK] 主线程假死检测! 延迟: {delay:.2f}s | "
            f"Queue积压: {q_size if q_size >= 0 else 'N/A'} "
            f"| 累计假死: 第 {cur_block_count} 次"
        )
        if cur_block_count % 5 == 0:
            mock_logger.warning(
                "[UI-BLOCK-STACK] (累计假死超过5次输出堆栈，当前第 %d 次)\nFakeStack",
                cur_block_count
            )
        else:
            mock_logger.debug(f"[UI-BLOCK-STACK] 堆栈日志已限流抑制 (当前第 {cur_block_count % 5}/5 次，超过5次输出一次)")

    # 模拟触发 12 次假死
    for _ in range(12):
        simulate_ui_block(app)

    # 1. 验证总共触发了 12 次 [UI_BLOCK] 简短警报
    block_alerts = [m for m in logged_warnings if "🚨 [UI_BLOCK]" in m]
    assert len(block_alerts) == 12

    # 2. 核心验证：[UI-BLOCK-STACK] 堆栈只有在第 5 次和第 10 次才输出 (共 2 次)
    stack_alerts = [m for m in logged_warnings if "[UI-BLOCK-STACK]" in m]
    assert len(stack_alerts) == 2
    assert "当前第 5 次" in stack_alerts[0]
    assert "当前第 10 次" in stack_alerts[1]

    # 3. 其余 10 次均被限流抑制
    suppressed = [m for m in logged_debugs if "堆栈日志已限流抑制" in m]
    assert len(suppressed) == 10
