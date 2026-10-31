# -*- coding: utf-8 -*-
"""
自动化测试：验证彻底移除鼠标 Button-4 / Button-5 侧键滚轮绑定
确保 Windows 平台下鼠标第 4、5 侧键（前进/后退/XButton1/XButton2）不再被 Tkinter 全局拦截，
且原生 <MouseWheel> 垂直滚动机制 100% 完好。
"""

import os
import re
import pytest
from unittest.mock import Mock, MagicMock


def test_no_button4_5_bind_all_in_codebase():
    """验证代码库中绝对不存在针对 <Button-4> 和 <Button-5> 的 bind_all / unbind_all 劫持"""
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    target_files = [
        os.path.join(project_root, "instock_MonitorTK.py"),
        os.path.join(project_root, "column_manager.py"),
        os.path.join(project_root, "popularity_resonance_gui.py"),
        os.path.join(project_root, "temp_historical_monitor.py"),
    ]

    pattern = re.compile(r'(bind_all|unbind_all)\s*\(\s*["\']<Button-[45]>["\']')

    violations = []
    for fpath in target_files:
        if not os.path.exists(fpath):
            continue
        with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
            for idx, line in enumerate(f, start=1):
                if pattern.search(line):
                    violations.append(f"{os.path.basename(fpath)}:{idx} -> {line.strip()}")

    assert not violations, f"发现残留的 Button-4/5 bind_all 全局劫持:\n" + "\n".join(violations)


def test_column_manager_bind_mousewheel_only_uses_mousewheel():
    """验证 ColumnManager 的滚轮绑定仅使用 <MouseWheel>，完全释放 Button-4/5 侧键"""
    import column_manager
    from types import SimpleNamespace

    bound = {}
    mock_canvas = MagicMock()
    mock_canvas.bind_all = MagicMock(side_effect=lambda ev, fn: bound.update({ev: fn}))
    mock_canvas.unbind_all = MagicMock(side_effect=lambda ev: bound.pop(ev, None))

    manager = object.__new__(column_manager.ColumnSetManager)
    manager.canvas = mock_canvas

    # 1. 模拟鼠标进入 (bind=True)
    manager._bind_mousewheel(True)
    assert "<MouseWheel>" in bound, "必须绑定原生 <MouseWheel>"
    assert "<Button-4>" not in bound, "严禁绑定 <Button-4>"
    assert "<Button-5>" not in bound, "严禁绑定 <Button-5>"

    # 2. 模拟滚轮滚动触发
    event_up = SimpleNamespace(delta=120)
    bound["<MouseWheel>"](event_up)
    mock_canvas.yview_scroll.assert_called_with(-1, "units")

    event_down = SimpleNamespace(delta=-120)
    bound["<MouseWheel>"](event_down)
    mock_canvas.yview_scroll.assert_called_with(1, "units")

    # 3. 模拟鼠标离开 (bind=False)
    manager._bind_mousewheel(False)
    assert "<MouseWheel>" not in bound, "必须正常解绑 <MouseWheel>"
    mock_canvas.unbind_all.assert_called_with("<MouseWheel>")
