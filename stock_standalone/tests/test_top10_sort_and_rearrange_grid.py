import pytest
import tkinter as tk
from tkinter import ttk
from unittest.mock import MagicMock
from gui_utils import rearrange_top10_windows_grid
from tk_gui_modules.treeview_mixin import TreeviewMixin


class DummyTreeApp(TreeviewMixin):
    def __init__(self, root):
        self.root = root
        self.sender = MagicMock()
        self.tree = None
        self._highlight_tree_selection = MagicMock()


@pytest.fixture
def tk_root():
    try:
        root = tk.Tk()
        root.withdraw()
        yield root
        root.destroy()
    except Exception:
        pytest.skip("Tkinter not available or display not initialized")


def test_top10_sort_scroll_to_top_and_select_first(tk_root):
    """验证需求1：点击排序后自动滚动到顶部并选中首行第一只股票进行联动"""
    app = DummyTreeApp(tk_root)
    tree = ttk.Treeview(tk_root, columns=("code", "name", "percent"), show="headings")
    tree.pack()
    
    win = tk.Toplevel(tk_root)
    win.withdraw()
    tree._top10_win = win
    tree._parent_win = win
    win._selected_index = -1
    win.select_code = None

    # 插入多行数据
    tree.insert("", "end", iid="0", values=("301079", "邵阳液压", "10.85"))
    tree.insert("", "end", iid="1", values=("603131", "上海沪工", "10.03"))
    tree.insert("", "end", iid="2", values=("688698", "伟创电气", "0.47"))
    tree.insert("", "end", iid="3", values=("603028", "赛福天", "-8.97"))

    app._init_tree_sort_state(tree)
    
    # 模拟点击涨幅列排序 (升序)
    app.sort_mixin_by_column(tree, "percent", reverse=False)
    
    # 验证排序后动作：已选中首行，并联动发送
    children = tree.get_children()
    assert len(children) == 4
    first_item = children[0]
    
    # 首行代码是 -8.97% 的 603028
    vals = tree.item(first_item, "values")
    assert vals[0] == "603028"
    assert tuple(tree.selection()) == (first_item,)
    assert win._selected_index == 0
    assert win.select_code == "603028"
    assert app.sender.send.called
    assert app.sender.send.call_args[0][0] == "603028"


def test_rearrange_top10_windows_grid_and_no_forced_topmost(tk_root):
    """验证需求2：按Q键自动网格重排并最前显示，但不强制置顶(置顶需手动开启或保留原有状态)"""
    w1 = tk.Toplevel(tk_root)
    w2 = tk.Toplevel(tk_root)
    w3 = tk.Toplevel(tk_root)
    w4 = tk.Toplevel(tk_root)

    for i, w in enumerate([w1, w2, w3, w4]):
        w.title(f"概念窗口 {i}")
        w.geometry("400x250")
        w._unique_code = f"c_{i}"
        w._is_stay_on_top = False
        w.attributes("-topmost", False)

    # 手动让 w2 处于置顶状态
    w2._is_stay_on_top = True
    w2.attributes("-topmost", True)

    monitor_list = {
        "c_0": {"win": w1},
        "c_1": {"win": w2},
        "c_2": {"win": w3},
        "c_3": {"win": w4},
    }

    # 执行网格重排（默认 stay_on_top=None，不强制修改置顶）
    parent_app = MagicMock()
    active_wins = rearrange_top10_windows_grid(
        monitor_list=monitor_list,
        trigger_win=w1,
        stay_on_top=None,
        parent_app=parent_app
    )

    assert len(active_wins) == 4
    # 验证 w1, w3, w4 不会被强制置顶
    assert getattr(w1, "_is_stay_on_top", False) is False
    assert bool(w1.attributes("-topmost")) is False
    assert getattr(w3, "_is_stay_on_top", False) is False
    assert bool(w3.attributes("-topmost")) is False
    # 验证原本置顶的 w2 保持置顶
    assert getattr(w2, "_is_stay_on_top", False) is True
    assert bool(w2.attributes("-topmost")) is True

    # 验证各窗口几何坐标已按 2x2 网格排布
    for w in [w1, w2, w3, w4]:
        geom = w.geometry()
        assert "x" in geom and "+" in geom

    # 验证持久化保存已触发
    assert parent_app.save_window_position.call_count == 4


def test_topmost_toggle_state(tk_root):
    """验证小窗口置顶状态切换 (T 键)"""
    from instock_MonitorTK import StockMonitorApp
    
    mock_app = MagicMock(spec=StockMonitorApp)
    w = tk.Toplevel(tk_root)
    btn_top = tk.Button(w, text="📌置顶:关")
    btn_top.pack()
    w._btn_topmost = btn_top
    w._is_stay_on_top = False

    # 调用 toggle_top10_window_topmost
    StockMonitorApp.toggle_top10_window_topmost(mock_app, w)
    assert w._is_stay_on_top is True
    assert bool(w.attributes("-topmost")) is True
    assert "开" in btn_top.cget("text")

    # 再次调用切换关闭
    StockMonitorApp.toggle_top10_window_topmost(mock_app, w)
    assert w._is_stay_on_top is False
    assert bool(w.attributes("-topmost")) is False
    assert "关" in btn_top.cget("text")
