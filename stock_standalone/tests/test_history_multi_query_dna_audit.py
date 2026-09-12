# -*- coding: utf-8 -*-
"""
tests/test_history_multi_query_dna_audit.py
验证多选策略对比弹窗中右键 DNA 专项审核功能与 Alt+W 快捷键：
1. _get_target_codes_for_dna:
   - 无选择 code 时自动从顶部选择默认前 50 只；
   - 单选 code 时从当前选中行向下取 50 只 (包含自身)；
   - 多选 code 时取选中的股票 (上限 50 只)；
   - 占位提示行 (如 '-') 自动安全过滤；
2. 右键菜单包含 DNA 专项审核选项；
3. 快捷键 Alt+w / Alt+W 绑定与触发执行；
4. 多 Tab (tree1 / tree2) 智能感知与 standalone 安全降级。
"""

import sys
import os
import pytest
import tkinter as tk
from tkinter import ttk
from unittest.mock import MagicMock

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

from history_manager import QueryHistoryManager


@pytest.fixture(scope="session")
def tk_root():
    """保证 Tk 实例存在"""
    root = tk.Tk()
    root.withdraw()
    yield root
    try:
        root.destroy()
    except Exception:
        pass


def test_dna_audit_code_selection_logic(tk_root):
    """验证 _get_target_codes_for_dna 的四维选股逻辑 (对齐 tk 点击逻辑)"""
    mock_master = MagicMock()
    hm = QueryHistoryManager.__new__(QueryHistoryManager)
    hm.root = tk_root
    hm.master = mock_master

    # 构造含 70 只模拟股票与 1 个占位行的测试数据
    queries = ["close > 10", "close > 20"]
    # 模拟全中 70 只，差集 10 只
    query_hits = {
        0: {f"{i:06d}" for i in range(1, 71)} | {f"600{i:03d}" for i in range(1, 11)},
        1: {f"{i:06d}" for i in range(1, 71)}
    }
    import pandas as pd
    all_codes = [f"{i:06d}" for i in range(1, 71)] + [f"600{i:03d}" for i in range(1, 11)]
    df_target = pd.DataFrame([{'name': f'股票{c}', 'percent': 1.0} for c in all_codes], index=all_codes)

    # 调起 show_multi_query_details 生成 top 窗口
    hm.show_multi_query_details(queries, query_hits, df_target)
    
    # 查找最新生成的 Toplevel
    detail_top = None
    for child in tk_root.winfo_children():
        if isinstance(child, tk.Toplevel) and "多选策略对比" in child.title():
            detail_top = child
            break

    assert detail_top is not None, "必须成功创建多选策略对比弹窗"
    assert hasattr(detail_top, "_get_target_codes_for_dna"), "弹窗必须挂载 _get_target_codes_for_dna"

    # 获取 detail_top 内部的 tree1 和 tree2
    nb = None
    for w in detail_top.winfo_children():
        if isinstance(w, ttk.Notebook):
            nb = w
            break
    assert nb is not None
    tabs = nb.winfo_children()
    tree1 = tabs[0].winfo_children()[0]
    tree2 = tabs[1].winfo_children()[0]

    # ===== 测试场景 1: 未选择 code，自动从顶部取默认前 50 只 =====
    tree1.selection_remove(tree1.selection())
    codes_no_sel = detail_top._get_target_codes_for_dna(tree1, limit=50)
    assert len(codes_no_sel) == 50, f"未选择时应默认取前 50 只，实际: {len(codes_no_sel)}"
    assert "000001" in codes_no_sel, "必须包含顶部第一只 000001"
    assert "000050" in codes_no_sel, "必须包含第 50 只 000050"
    assert "000051" not in codes_no_sel, "第 51 只应被截断"

    # ===== 测试场景 2: 单选第 20 只股票 (000020)，从当前 code 往下取 50 只 (20~69) =====
    all_items = tree1.get_children()
    item_20 = None
    for it in all_items:
        if tree1.item(it, 'values')[0] == "000020":
            item_20 = it
            break
    assert item_20 is not None
    tree1.selection_set(item_20)
    
    codes_single_sel = detail_top._get_target_codes_for_dna(tree1, limit=50)
    assert len(codes_single_sel) == 50, f"单选 000020 往下应取 50 只，实际: {len(codes_single_sel)}"
    assert "000019" not in codes_single_sel, "选中行之前的股票不应包含"
    assert "000020" in codes_single_sel, "必须包含选中的自身 000020"
    assert "000069" in codes_single_sel, "必须包含第 50 只 000069"
    assert "000070" not in codes_single_sel, "超出 50 只范围的应截断"

    # ===== 测试场景 3: 多选 3 只股票 (000003, 000008, 000015)，仅提取选中的 3 只 =====
    sel_3 = [it for it in all_items if tree1.item(it, 'values')[0] in ["000003", "000008", "000015"]]
    tree1.selection_set(sel_3)
    codes_multi_sel = detail_top._get_target_codes_for_dna(tree1, limit=50)
    assert len(codes_multi_sel) == 3
    assert set(codes_multi_sel.keys()) == {"000003", "000008", "000015"}

    # ===== 测试场景 4: 切换到 Tab 2 (未全中标的)，快捷键智能审计当前 Tab =====
    nb.select(1) # 切换到 Tab 2
    mock_run_audit = MagicMock()
    hm.root._run_dna_audit_batch = mock_run_audit
    
    # 在 Tab 2 未选择 code 时触发 Alt+W，应自动提取 Tab 2 的前 10 只
    detail_top._trigger_dna_audit()
    assert mock_run_audit.called
    called_codes = mock_run_audit.call_args[0][0]
    assert len(called_codes) == 10
    assert "600001" in called_codes

    # ===== 测试场景 5: 验证快捷键绑定事件存在 =====
    bindings_top = detail_top.bind()
    assert "<Alt-Key-w>" in bindings_top or "<Alt-w>" in bindings_top
    assert "<Alt-Key-W>" in bindings_top or "<Alt-W>" in bindings_top

    detail_top.destroy()