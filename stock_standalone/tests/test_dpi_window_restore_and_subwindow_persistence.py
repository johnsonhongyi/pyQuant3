# -*- coding: utf-8 -*-
"""
tests/test_dpi_window_restore_and_subwindow_persistence.py
===========================================================
专项测试：验证 Tkinter 窗口位置/尺寸持久化与 DPI 缩放解耦，
1:1 绝对物理像素保真、RDP 与本地环境隔离及双向平滑兜底、安全行高防重叠闭环。
"""
import os
import sys
import json
import time
import pytest
from unittest.mock import Mock, patch

import tkinter as tk
from tkinter import ttk
import tkinter.font as tkfont

from tk_gui_modules.dpi_mixin import DPIMixin
from tk_gui_modules.window_mixin import WindowMixin
from dpi_utils import is_rdp_session, get_windows_dpi_scale_factor


class DummyTkApp(DPIMixin, WindowMixin, tk.Tk):
    def __init__(self):
        tk.Tk.__init__(self)
        self.withdraw()  # 测试时不弹出真实窗口
        self.scale_factor = 1.25  # 模拟 125% 缩放环境
        self.last_dpi_scale = 1.25
        self._pg_top10_window_simple = {}


@pytest.fixture
def tk_app():
    try:
        app = DummyTkApp()
    except tk.TclError:
        pytest.skip("No display/Tcl available")
    yield app
    try:
        app.destroy()
    except Exception:
        pass


def test_1_to_1_physical_pixel_fidelity_and_no_drift(tk_app, tmp_path):
    """
    【1:1 绝对物理像素保真与多次存取零漂移验证】
    用户摆好的 200x160 窗口，加载后严格保持 200x160，多次 save -> load 绝无浮点累积漂移。
    """
    cfg_file = str(tmp_path / "window_config.json")
    saved_cfg = {
        "concept_top10_window-5G概念_": {
            "x": 200, "y": 10, "width": 200, "height": 160
        }
    }
    with open(cfg_file, "w", encoding="utf-8") as f:
        json.dump(saved_cfg, f)

    sub_win = tk.Toplevel(tk_app)
    sub_win.title("5G概念 概念前10放量上涨股")

    # 1. 加载
    w, h, x, y = tk_app.load_window_position(
        sub_win, "concept_top10_window-5G概念_", file_path=cfg_file,
        default_width=460, default_height=260
    )
    sub_win.update_idletasks()

    assert w == 200, f"宽度应为 1:1 物理保真 200，实际为 {w}"
    assert h == 160, f"高度应为 1:1 物理保真 160，实际为 {h}"
    assert getattr(sub_win, "_persisted_window_name", None) == "concept_top10_window-5G概念_"

    # 2. 模拟多次 save 与 load 循环
    for _ in range(3):
        tk_app.save_window_position(sub_win, "concept_top10_window-5G概念_", file_path=cfg_file)
        w2, h2, x2, y2 = tk_app.load_window_position(
            sub_win, "concept_top10_window-5G概念_", file_path=cfg_file
        )
        sub_win.update_idletasks()
        assert w2 == 200
        assert h2 == 160

    # 3. 验证后台巡检绝不篡改已加载几何
    tk_app._adapt_unregistered_toplevels(current_scale=1.5)
    sub_win.update_idletasks()
    after_geom = sub_win.geometry().split("+")[0].split("x")
    assert int(after_geom[0]) == 200
    assert int(after_geom[1]) == 160

    sub_win.destroy()


def test_rdp_routing_and_smooth_fallback(tk_app, tmp_path):
    """
    【RDP环境隔离与双向平滑回退兜底验证】
    1. RDP 会话下优先读取 scale2_window_config.json；
    2. 若主文件不存在某窗口，平滑从备用配置文件回退继承。
    """
    scale2_file = str(tmp_path / "scale2_window_config.json")
    base_file = str(tmp_path / "window_config.json")

    # scale2 里有专属于 RDP 调优的紧凑小窗口
    with open(scale2_file, "w", encoding="utf-8") as f:
        json.dump({
            "concept_top10_window-RDP专享_": {"x": 10, "y": 0, "width": 218, "height": 180}
        }, f)

    # base 里有另一个窗口
    with open(base_file, "w", encoding="utf-8") as f:
        json.dump({
            "main_window": {"x": 100, "y": 100, "width": 1024, "height": 600}
        }, f)

    sub_win1 = tk.Toplevel(tk_app)
    sub_win2 = tk.Toplevel(tk_app)

    # 模拟处于 RDP 会话
    with patch("dpi_utils.is_rdp_session", return_value=True):
        # 1. 优先读取 scale2_window_config.json
        w1, h1, x1, y1 = tk_app.load_window_position(
            sub_win1, "concept_top10_window-RDP专享_", file_path=base_file
        )
        assert w1 == 218
        assert h1 == 180

        # 2. main_window 只在 base 文件中，触发平滑回退继承
        w2, h2, x2, y2 = tk_app.load_window_position(
            sub_win2, "main_window", file_path=base_file
        )
        assert w2 == 1024
        assert h2 == 600

    sub_win1.destroy()
    sub_win2.destroy()


def test_treeview_safe_rowheight_computation(tk_app):
    """
    【安全行高防重叠验证】
    Treeview 的 rowheight 必须基于当前字体 linespace 动态增加呼吸安全间距，
    在任何缩放比例下都严禁文字上下重叠。
    """
    try:
        f = tkfont.nametofont("TkDefaultFont")
        font_linespace = f.metrics("linespace")
    except Exception:
        font_linespace = 14

    # 1.0x 缩放
    row_h_10 = tk_app._compute_safe_rowheight(1.0)
    assert row_h_10 >= font_linespace + 5, f"安全行高 {row_h_10} 应至少比 linespace {font_linespace} 高 5 像素"

    # 1.5x 缩放
    row_h_15 = tk_app._compute_safe_rowheight(1.5)
    assert row_h_15 >= row_h_10
    assert row_h_15 >= font_linespace + 5

    # 验证应用到样式无异常
    tk_app._apply_dpi_scaling(1.0)
    style = ttk.Style(tk_app)
    assert int(style.lookup("Treeview", "rowheight") or 0) >= font_linespace + 5


def test_dpi_scaling_initializes_last_dpi_scale_preventing_false_alarm(tk_app):
    """
    验证 _apply_dpi_scaling 初始化时设置了 last_dpi_scale，
    避免初次轮询将 1.25/1.5 误判为从 1.0 改变而发生全量主窗二次放大。
    """
    tk_app.last_dpi_scale = None
    tk_app._apply_dpi_scaling(1.5)
    assert tk_app.scale_factor == 1.5
    assert tk_app.last_dpi_scale == 1.5
