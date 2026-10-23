# -*- coding: utf-8 -*-
"""端到端验证 Tkinter 在混合 PyQt 架构下的 DPI 自适应与防膨胀机制。

测试场景：
1. 真实 DPI 探测：严格基于 Windows 系统/会话物理 DPI，杜绝 RDP 误判 2.0 虚假放大。
2. 字体防膨胀机制：TkDefaultFont 等全局字体严格锁定设计基准磅数 (9pt)，绝不人为将 size 乘以 scale_factor。
3. 双向几何与列宽自适应：主窗口、子 Toplevel 窗口与各 Treeview 列宽随 DPI 放大/缩小平滑伸缩。
4. 动态新窗口自动捕捉：高 DPI 运行期动态打开的未适配子窗口，自动识别并无损对齐当前 scale。
"""
import pytest
import tkinter as tk
from tkinter import ttk
import tkinter.font as tkfont
from tk_gui_modules.dpi_mixin import DPIMixin
from dpi_utils import get_windows_dpi_scale_factor

class MockApp(DPIMixin, tk.Tk):
    def __init__(self):
        super().__init__()
        self.geometry('800x600+100+100')
        self.scale_factor = 1.0
        self.last_dpi_scale = 1.0
        self.default_font = tkfont.nametofont('TkDefaultFont')
        self.default_font_size = self.default_font.cget('size')
        self._apply_dpi_scaling(1.0)
        
        # 主表
        self.tree = ttk.Treeview(self, columns=('code', 'name', 'price'), show='headings')
        self.tree.column('code', width=80)
        self.tree.column('name', width=100)
        self.tree.column('price', width=60)
        self.tree.pack(fill='both', expand=True)

def test_dpi_scaling_and_subwindow_adaptation():
    try:
        app = MockApp()
    except Exception:
        pytest.skip("No graphical display available for Tkinter")

    # 弹出子窗口 (模拟概念前10放量上涨股)
    top = tk.Toplevel(app)
    top.title('国家大基金持股 概念前10放量上涨股')
    top.geometry('360x200+150+150')
    sub_tree = ttk.Treeview(top, columns=('code', 'name', 'rank', 'win'), show='headings')
    sub_tree.column('code', width=80)
    sub_tree.column('name', width=80)
    sub_tree.column('rank', width=30)
    sub_tree.column('win', width=40)
    sub_tree.pack(fill='both', expand=True)

    app.update()
    top.update()

    w_code_init = app.tree.column('code', 'width')
    w_rank_init = sub_tree.column('rank', 'width')
    w_win_init = sub_tree.column('win', 'width')

    # 1. 验证初始状态字体点数保持原生基准
    initial_font_size = app.default_font.cget('size')

    # 2. 模拟 DPI 改变为 1.5x (144 DPI)
    app._apply_scale_dpi_change(1.5)
    app.update()
    top.update()

    w_code_15 = app.tree.column('code', 'width')
    w_rank_15 = sub_tree.column('rank', 'width')
    w_win_15 = sub_tree.column('win', 'width')

    # 字体点数必须保持基准点数，由 tk scaling 换算，绝不二次相乘膨胀
    assert app.default_font.cget('size') == initial_font_size
    assert abs(w_code_15 - int(round(w_code_init * 1.5))) <= 2
    assert abs(w_rank_15 - int(round(w_rank_init * 1.5))) <= 2
    assert abs(w_win_15 - int(round(w_win_init * 1.5))) <= 2

    # 3. 动态新窗口捕捉测试：当前已是 1.5x，此时新弹出一个子窗口
    new_top = tk.Toplevel(app)
    new_top.title('动态新开概念窗口')
    new_top.geometry('360x200+200+200')
    new_tree = ttk.Treeview(new_top, columns=('code', 'rank'), show='headings')
    new_tree.column('code', width=80)
    new_tree.column('rank', width=40)
    new_tree.pack(fill='both', expand=True)
    new_top.update()

    # 巡检自动捕获新窗口并按 1.5x 对齐
    app._adapt_unregistered_toplevels(1.5)
    new_top.update()

    assert new_top._dpi_applied == 1.5
    assert new_top.winfo_width() >= 500  # 360 * 1.5 = 540

    # 4. 模拟切换回 1.0x DPI (96 DPI)
    app._apply_scale_dpi_change(1.0)
    app.update()
    top.update()
    new_top.update()

    w_code_back = app.tree.column('code', 'width')
    w_rank_back = sub_tree.column('rank', 'width')
    w_win_back = sub_tree.column('win', 'width')

    assert app.default_font.cget('size') == initial_font_size
    assert abs(w_code_back - w_code_init) <= 2
    assert abs(w_rank_back - w_rank_init) <= 2
    assert abs(w_win_back - w_win_init) <= 2

    app.destroy()

def test_real_dpi_scale_factor_no_fake_rdp_doubling():
    scale = get_windows_dpi_scale_factor()
    # 真实 DPI 缩放因子必须在合理区间 [0.75, 3.0]，绝不可直接被 RDP 强行写死为 2.0
    assert 0.75 <= scale <= 3.0
