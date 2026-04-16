# -*- coding: utf-8 -*-
import tkinter as tk
from tkinter import ttk

class IndicatorHelpWindow:
    """
    指标说明与搜索窗口 (Searchable Indicator Help Window)
    """
    def __init__(self, parent):
        self.parent = parent
        self.window = tk.Toplevel(parent)
        self.window.title("指标含义说明 (HotKey: Ctrl + /)")
        
        # [NEW] 恢复窗口位置
        if hasattr(parent, 'load_window_position'):
            parent.load_window_position(self.window, "indicator_help", default_width=600, default_height=500)
        else:
            self.window.geometry("600x500")
            
        self.window.attributes('-topmost', True)  # 保持置顶
        
        # 搜索框
        search_frame = ttk.Frame(self.window)
        search_frame.pack(fill='x', padx=10, pady=10)
        
        ttk.Label(search_frame, text="搜索指标:").pack(side='left')
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", self.on_search)
        self.search_entry = ttk.Entry(search_frame, textvariable=self.search_var)
        self.search_entry.pack(side='left', fill='x', expand=True, padx=5)
        self.search_entry.focus_set()

        # 列表展示区域
        list_frame = ttk.Frame(self.window)
        list_frame.pack(fill='both', expand=True, padx=10, pady=(0, 10))
        
        columns = ("col", "desc")
        self.tree = ttk.Treeview(list_frame, columns=columns, show='headings')
        self.tree.heading("col", text="字段 (Column)")
        self.tree.heading("desc", text="含义 (Description)")
        self.tree.column("col", width=120, stretch=False)
        self.tree.column("desc", width=450)
        
        # 滚动条
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        self.tree.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')
        # ===== Treeview 行颜色 + 帮助说明 =====
        # (tag_name, color, help_text)

        self.tree_row_tags = [
            ("red_row", "#ff3b30", "强势上涨：当日最低价 > 昨日收盘价，说明全天承接强"),
            ("orange_row", "#ff8c00", "强势突破：最高价突破 recent high4，短线突破信号"),
            ("green_row", "#00c853", "明显下跌：跌幅或最低价低于昨收，短线走弱"),
            ("blue_row", "#444444", "弱势状态：价格低于 MA5，短线趋势偏空"),
            ("purple_row", "#a855f7", "特殊信号：成交量异常或策略触发"),
            ("yellow_row", "#ffd400", "临界预警：价格接近或跌破 MA20，需要关注趋势变化"),
        ]
        # 指标数据源
        self.all_data = [
            ("cycle_stage", "【新增】周期阶段判定。1:筑底/启动, 2:主升/健康, 3:脉冲/扩张, 4:见顶/回落"),
            ("lowvol", "最低价成交量"),
            ("nvol", "今日交易量"),
            ("hv", "10天内最大成交量"),
            ("lv", "10天内最小成交量同llowvol"),
            ("last6vol", "6天平均成交量"),
            ("lvol", "昨天成交量 (%)"),
            ("percent", "今日实时涨跌幅 (%)"),
            ("trade", "最新成交价格"),
            ("ratio", "量比（成交量与过去5日均量之比）"),
            ("turnover", "成交金额 (单位:万元/亿元)"),
            ("dff", "MACD 指标中的 DIFF 差值"),
            ("boll", "近期布林带上轨位置/对应计算值"),
            ("upper", "布林带上轨 (Upper Bound)"),
            ("middle", "布林带中轨 (Middle Bound/MA20)"),
            ("lower", "布林带下轨 (Lower Bound)"),
            ("ma5d / ma10d", "日线级别 5日, 10日 均线"),
            ("ma20d / ma60d", "日线级别 20日, 60日 均线"),
            ("high4 / low4", "最近 4 个交易日的最高价 / 最低价"),
            ("lastdu4", "最近 4 个交易日的振幅表现"),
            ("hmax", "历史最高价位 (Close Highest)"),
            ("vchange", "由于量能变动引起的量比波动"),
            ("top10", "最近 10 个交易日内的封板/涨停次数"),
            ("topR", "综合强势排名指标（得分越高越强势）"),
            ("red", "主升浪阳K形态标识（连阳启动）"),
            ("green", "下降通道绿K形态标识"),
            ("fib", "15周期内波动幅度大于2%的频次"),
            ("maxp", "15个周期内的波动幅度百分比"),
            ("bandwidth", "布林带宽度 (Bandwidth), 反映波动率"),
            ("turnoverratio", "换手率 (%)"),
            ("couts", "信号触发计数 / 异动次数"),
            ("red_row", "强势上涨：当日最低价 > 昨收，全天承接强（红色 #ff3b30）"),
            ("orange_row", "突破信号：最高价突破 recent high4（橙色 #ff8c00）"),
            ("green_row", "明显下跌：跌幅或最低价低于昨收（绿色 #00c853）"),
            ("blue_row", "弱势：价格低于 MA5（深灰 #444444）"),
            ("purple_row", "特殊指标：成交量异常或策略触发（紫色 #a855f7）"),
            ("yellow_row", "预警状态：接近或跌破 MA20（黄色 #ffd400）"),
        ]
        
        # [NEW] 绑定退出事件以保存位置
        self.window.protocol("WM_DELETE_WINDOW", self.on_close)
        # 绑定 Esc 键关闭
        self.window.bind("<Escape>", lambda e: self.on_close())
        
        self.refresh_tree(self.all_data)

    def on_close(self):
        """关闭窗口并保存位置"""
        if hasattr(self.parent, 'save_window_position'):
            self.parent.save_window_position(self.window, "indicator_help")
        self.window.destroy()

    def refresh_tree(self, data):
        # 清空
        for item in self.tree.get_children():
            self.tree.delete(item)
        # 插入
        for col, desc in data:
            self.tree.insert("", "end", values=(col, desc))

    def on_search(self, *args):
        query = self.search_var.get().lower()
        if not query:
            self.refresh_tree(self.all_data)
            return
        
        filtered = [
            item for item in self.all_data 
            if query in item[0].lower() or query in item[1].lower()
        ]
        self.refresh_tree(filtered)

def show_help(parent):
    IndicatorHelpWindow(parent)

if __name__ == "__main__":
    # 模拟一个带 WindowMixin 的 parent 供测试 (此处简化)
    root = tk.Tk()
    root.title("Test Help Window")

    class MockApp:
        def __init__(self, root):
            self.root = root
        def load_window_position(self, win, name, **kwargs):
            win.geometry(f"{kwargs.get('default_width', 600)}x{kwargs.get('default_height', 500)}+100+100")
        def save_window_position(self, win, name):
            print(f"Saving {name} position: {win.geometry()}")

    mock_app = MockApp(root)
    btn = ttk.Button(root, text="Open Help (Ctrl+/)", command=lambda: show_help(mock_app))
    btn.pack(padx=20, pady=20)
    root.mainloop()
