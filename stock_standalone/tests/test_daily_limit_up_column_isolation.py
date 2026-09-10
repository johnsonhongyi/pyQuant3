# -*- coding: utf-8 -*-
"""
测试天梯面板：
1. 顶栏自适应与极窄模式按钮已删除；
2. 一键自适应与极窄模式纯视图排版隔离（不持久化列宽数据）；
3. 右键恢复自定义列宽数据（准确还原用户手动调整保存的列宽）；
4. 一键自适应或极窄模式后手动调整列宽才持久化保存。
"""

import sys
import os
import pytest
from PyQt6.QtWidgets import QApplication

# 确保主路径在 sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from ats.ui.daily_limit_up_dialog import DailyLimitUpDialog
from ats.limit_up_engine import LimitUpEngine

@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app

def test_buttons_removed_from_toolbar(qapp):
    """验证顶栏已彻底删除自适应与极窄模式按钮"""
    dlg = DailyLimitUpDialog()
    try:
        # 验证按钮指针为 None 且未添加到工具栏
        assert dlg.btn_autofit is None
        assert dlg.btn_narrow_mode is None

        # 遍历子控件，确保没有名为 "📐 自适应" 或 "📱 极窄模式" 的 QPushButton
        from PyQt6.QtWidgets import QPushButton
        btn_texts = [b.text() for b in dlg.findChildren(QPushButton)]
        assert "📐 自适应" not in btn_texts
        assert "📱 极窄模式" not in btn_texts
    finally:
        dlg.close()

def test_autofit_isolation_and_restore_custom_widths(qapp):
    """验证一键自适应不持久化覆写自定义列宽，且恢复自定义列宽可精准复原"""
    dlg = DailyLimitUpDialog()
    dlg.show()
    try:
        col_count = dlg.table.columnCount()
        assert col_count > 5

        # 1. 模拟用户手动调整列宽并持久化
        target_col = 1  # 股票名称列
        custom_width = 188
        dlg.table.setColumnWidth(target_col, custom_width)
        
        # 模拟触发用户手动拖动表头调整
        dlg._on_header_section_resized(target_col, 80, custom_width)
        key = dlg._get_current_header_config_key(dlg.current_mode)
        cached_widths = dlg._column_widths_cache.get(key)
        assert cached_widths is not None
        assert cached_widths[target_col] == custom_width

        # 2. 执行一键自适应列宽
        dlg.auto_fit_columns()
        autofit_w = dlg.table.columnWidth(target_col)
        # 自适应后的名称列一般被限制在 68~105 之间
        assert autofit_w != custom_width

        # 核心断言：一键自适应绝不应覆盖持久化缓存 _column_widths_cache！
        assert dlg._column_widths_cache[key][target_col] == custom_width

        # 3. 执行恢复自定义列宽
        dlg.restore_custom_columns()
        # 验证表格列宽被精准复原
        assert dlg.table.columnWidth(target_col) == custom_width
    finally:
        dlg.close()

def test_narrow_mode_isolation_and_restore_on_exit(qapp):
    """验证极窄模式切换不会污染自定义列宽，切回宽屏时自动恢复自定义列宽"""
    dlg = DailyLimitUpDialog()
    dlg.show()
    try:
        target_col = 1
        custom_width = 199
        dlg.table.setColumnWidth(target_col, custom_width)
        dlg._on_header_section_resized(target_col, 80, custom_width)
        key = dlg._get_current_header_config_key(dlg.current_mode)
        assert dlg._column_widths_cache[key][target_col] == custom_width

        # 1. 进入极窄模式
        dlg.toggle_narrow_mode(True)
        assert dlg.is_narrow_mode is True
        # 核心断言：极窄模式排版绝不覆盖自定义列宽缓存
        assert dlg._column_widths_cache[key][target_col] == custom_width

        # 2. 退出极窄模式
        dlg.toggle_narrow_mode(False)
        assert dlg.is_narrow_mode is False
        # 核心断言：切回宽屏自动恢复为自定义列宽
        assert dlg.table.columnWidth(target_col) == custom_width
    finally:
        dlg.close()

def test_manual_resize_after_autofit_persists(qapp):
    """验证：自适应或极窄模式后，用户手动拖拽调整才进行持久化"""
    dlg = DailyLimitUpDialog()
    dlg.show()
    try:
        key = dlg._get_current_header_config_key(dlg.current_mode)
        
        # 1. 执行一键自适应
        dlg.auto_fit_columns()
        
        # 2. 自适应后，用户手动拖动第 0 列为 123px
        new_col0_w = 123
        dlg.table.setColumnWidth(0, new_col0_w)
        dlg._on_header_section_resized(0, 62, new_col0_w)

        # 核心断言：此时正式将自适应基础 + 用户微调进行了持久化！
        assert dlg._column_widths_cache[key][0] == new_col0_w
        
        # 验证防抖定时器已激活
        assert dlg._col_save_debounce_timer.isActive()
    finally:
        dlg.close()
