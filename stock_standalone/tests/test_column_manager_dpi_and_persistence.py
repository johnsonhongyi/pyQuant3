# -*- coding: utf-8 -*-
"""
tests/test_column_manager_dpi_and_persistence.py
=================================================
专项测试：验证 ColumnSetManager（列组合管理器）DPI 适配、防二次放大与窗口尺寸持久化自愈。
"""
import os
import json
import pytest
import tkinter as tk
from tkinter import ttk

from tk_gui_modules.dpi_mixin import DPIMixin
from tk_gui_modules.window_mixin import WindowMixin
from column_manager import ColumnSetManager


class DummyHostApp(DPIMixin, WindowMixin, tk.Tk):
    def __init__(self, scale_factor=1.5):
        super().__init__()
        self.withdraw()
        self.scale_factor = scale_factor
        self.last_dpi_scale = scale_factor
        self._apply_dpi_scaling(scale_factor)


def test_column_manager_initial_size_and_no_secondary_scaling(tmp_path, monkeypatch):
    """
    验证 ColumnSetManager 在 1.5x DPI 下打开时尺寸适中，
    经历后台巡检 _adapt_unregistered_toplevels 绝不发生二次放大铺满屏幕。
    """
    try:
        app = DummyHostApp(scale_factor=1.5)
    except Exception:
        pytest.skip("No graphical display available for Tkinter")

    config_file = str(tmp_path / "window_config.json")
    monkeypatch.setattr("tk_gui_modules.window_mixin.WINDOW_CONFIG_FILE", config_file)

    all_cols = ["name", "trade", "volume", "ratio", "ch_supp_slope_deg", "ch_res_slope_deg", "boll", "macd"]
    default_cols = ["name", "trade", "volume"]

    # 初始化管理器
    mgr = ColumnSetManager(app, all_cols, {}, lambda cols: None, default_cols)
    mgr.update()

    init_w = mgr.winfo_width()
    init_h = mgr.winfo_height()

    # 1. 验证初始尺寸在合理区间 (基于 800x520 * 1.5 约 1200x780)，而不是原始小尺寸，更不是铺满全屏 (如 1920+)
    assert 800 <= init_w <= 1400
    assert 400 <= init_h <= 900
    assert mgr._persisted_window_name == "column_set_manager"
    assert mgr._dpi_applied == 1.5

    # 2. 模拟后台定时巡检 3 次
    for _ in range(3):
        app._adapt_unregistered_toplevels(1.5)
        mgr.update()

    # 3. 核心断言：巡检后窗口绝对没有被二次放大！
    assert mgr.winfo_width() == init_w
    assert mgr.winfo_height() == init_h

    mgr.destroy()
    app.destroy()


def test_column_manager_manual_resize_and_restore_persistence(tmp_path, monkeypatch):
    """
    验证用户手动调整 ColumnSetManager 大小后，保存到配置，再次打开时 100% 精确恢复，绝不巨大。
    """
    try:
        app = DummyHostApp(scale_factor=1.0)
    except Exception:
        pytest.skip("No graphical display available for Tkinter")

    config_file = str(tmp_path / "window_config.json")
    all_cols = ["name", "trade", "volume", "ratio", "boll"]
    default_cols = ["name", "trade"]

    # 模拟用户将窗口拉小为 700x450 并保存
    mock_pos = {"x": 100, "y": 100, "width": 700, "height": 450}
    with open(config_file, "w", encoding="utf-8") as f:
        json.dump({"column_set_manager": mock_pos}, f)

    monkeypatch.setattr("tk_gui_modules.window_mixin.WINDOW_CONFIG_FILE", config_file)

    mgr = ColumnSetManager(app, all_cols, {}, lambda cols: None, default_cols)
    mgr.update()

    # 验证精确恢复用户调整的 700x450
    assert mgr.winfo_width() == 700
    assert mgr.winfo_height() == 450

    # 巡检依然不放大
    app._adapt_unregistered_toplevels(1.0)
    mgr.update()
    assert mgr.winfo_width() == 700
    assert mgr.winfo_height() == 450

    mgr.destroy()
    app.destroy()
