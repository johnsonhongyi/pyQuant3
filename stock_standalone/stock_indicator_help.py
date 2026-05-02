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
        self.window.title("指标说明 (双击查看详情) (HotKey: Ctrl + /)")
        
        # [NEW] 恢复窗口位置
        if hasattr(parent, 'load_window_position'):
            parent.load_window_position(self.window, "indicator_help", default_width=650, default_height=500)
        else:
            self.window.geometry("650x500")
            
        self.window.attributes('-topmost', True)  # 保持置顶
        
        # 提示语
        tip_label = ttk.Label(self.window, text="提示: 双击列表项可查看详细计算逻辑与 Query 语句", foreground="gray")
        tip_label.pack(side='bottom', fill='x', padx=10, pady=5)

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
        self.tree.column("col", width=130, stretch=False)
        self.tree.column("desc", width=480)
        
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
            ("alert_row", "#4B0082", "实时报警：本会话触发了语音/日志报警 (标注 🔔)"),
        ]
        # 配置 Treeview 标签颜色
        for tag_name, color, _ in self.tree_row_tags:
            if tag_name == "alert_row":
                self.tree.tag_configure(tag_name, background=color, foreground="white")
            else:
                self.tree.tag_configure(tag_name, foreground=color)

        # [FIX] 重新绑定双击事件 (之前手动编辑中丢失)
        self.tree.bind("<Double-1>", self.on_item_double_click)

        # 指标详细数据源 (字段, 简述, 详细逻辑/Query)
        self.all_data = [
            ("cycle_stage", "【新增】周期阶段判定。1:筑底/启动, 2:主升/健康, 3:脉冲/扩张, 4:见顶/回落", "判定规则：\n1: Bottoming - 低位放量或均线缠绕后初次抬头\n2: Healthy - 多头排列，支撑有效\n3: Expansion - 加速远离均线，波动率放大\n4: Topping - 高位滞涨，量价背离或跌破关键支撑"),
            
            ("【重要】强度排序优先级", "名称列图标(水印)强度权重说明", 
             "系统现支持按『名称列图标强度』智能排序，权重分值越高排序越靠前：\n\n"
             "🚀 [1000] 强势波段 (Bullish Trend)\n"
             "⬆️ [800]  突破/创新高 (New High/Breakout)\n"
             "🔴 [500]  涨停/极强 (Limit Up)\n"
             "⚠️ [300]  系统预警 (Alert Signal)\n"
             "🔥 [100]  热门概念 (Hot Concept)\n"
             "📊 [50]   异动放量 (High Volume)\n"
             "⭐ [20]   收藏标记 (Starred)\n"
             "⬇️ [-10]  破位下跌 (New Low)\n"
             "🟢 [-500] 跌停/极弱 (Limit Down)\n\n"
             "应用场景：在监控列表中点击『名称』表头，即可将最具攻击性(信号最强)的个股置顶展示。"),

            ("top15", "【核心】强势上攻/加速突破", 
             "逻辑分析：当天强势启动(阳线 >4%), 突破近期新高或布林上轨。\n\n"
             "Query实现：\n"
             "df.query('(low >= open*0.992 or open > open.shift(1)) and close > open and '"
             " '((high > upper or high > high.shift(1)) and close > close.shift(1)*1.04)')"),
            
            ("STRATEGY: 回调企稳", "寻找大波动回调后缩量十字星蓄势", 
             "策略说明：寻找前期有过活跃表现(大波动)后，经历良性回踩并缩量企稳的个股。\n\n"
             "Query组合建议：\n"
             "df.query('lastdu4 > 10 and gren > 2 and abs(close-open)/close < 0.003 and '"
             " 'volume < volume.rolling(5).mean() and abs(close-support)/support < 0.015')"),

            ("STRATEGY: 加速上扬", "寻找主升浪加速启动点", 
             "策略说明：在趋势已经多头排列的基础上，经过主力试盘确认抛压较轻，配合量能放大加速突围。\n\n"
             "Query组合建议：\n"
             "df.query('ma5d > ma10d > ma20d and boll_probe == True and ratio > 1.2 and top15 == 1')"),

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
            
            # 以下保留部分原有的详细说明
            ("boll_probe", "【潜伏】试盘期信号", 
             "详细逻辑：股价当日最高点触及或突破布林带上轨(upper)，但收盘未能站稳上轨道，同时布林上轨的斜率向上。\n"
             "含义：代表主力通过瞬间拉升探测上方卖盘压力，通常是主升破位前的预演。"),
            ("top0", "极端波动/一字板", "query('low == high and low != 0')\n最高价等于最低价，通常见于一字涨停或一字跌停。"),
            ("ral", "支撑稳固度天数", "len(df.query('low > ma20d'))\n统计最近 20 天内股价始终保持在 MA20 支撑位之上的天数。"),
            ("resist / pressure", "动态压力位", "计算逻辑：根据 KDJ 交叉点及历史高点回溯确定的阻力位。"),
            ("support", "动态支撑位", "计算逻辑：LLV(high, 30)。取最近 30 个交易日的最高价序列中的最低点。"),
            ("fib / fibl", "主升连贯性", "计算逻辑：((high > high.shift(1)*0.998) | (close > close.shift(1))).sum()\n衡量自近期低点以来股价维持强势运作的连贯次数。"),
            ("op", "区间累计涨幅", "((close / base_price) * 100 - 100)。相对于 30 天内最低价格的累计涨跌幅百分比。"),
            ("alert_info", "【系统】🔔 实时报警标注", "逻辑说明：\n当前个股在本会话中触发了实盘报警（语音播报或日志预警）。\n其背景将变为深紫色 (#4B0082)，名称前缀增加 🔔，便于在全系统中快速定位与追踪。"),
        ]

        # [NEW] 绑定退出事件以保存位置
        self.window.protocol("WM_DELETE_WINDOW", self.on_close)
        # 绑定 Esc 键关闭
        self.window.bind("<Escape>", lambda e: self.on_close())
        
        self.refresh_tree(self.all_data)

    def on_item_double_click(self, event):
        """处理树形列表双击事件，弹出详情窗口"""
        item = self.tree.selection()
        if not item:
            return
        
        values = self.tree.item(item, "values")
        col_name = values[0]
        
        # 从 all_data 寻找匹配项
        match = next((x for x in self.all_data if x[0] == col_name), None)
        if match:
            # 如果没有第三个详情列，则使用摘要作为详情
            detail_text = match[2] if len(match) > 2 else match[1]
            self.show_detail(match[0], match[1], detail_text)

    def show_detail(self, title, summary, detail):
        """弹出详细说明小窗口"""
        detail_win = tk.Toplevel(self.window)
        detail_win.title(f"详情: {title}")
        detail_win.geometry("500x400")
        detail_win.attributes('-topmost', True)
        
        # 居中显示
        detail_win.update_idletasks()
        x = self.window.winfo_x() + (self.window.winfo_width() // 2) - (detail_win.winfo_width() // 2)
        y = self.window.winfo_y() + (self.window.winfo_height() // 2) - (detail_win.winfo_height() // 2)
        detail_win.geometry(f"+{x}+{y}")

        # 内容区域
        main_frame = ttk.Frame(detail_win, padding=15)
        main_frame.pack(fill='both', expand=True)

        ttk.Label(main_frame, text=f"{title}", font=("微软雅黑", 12, "bold")).pack(anchor='w')
        ttk.Label(main_frame, text=f"{summary}", font=("微软雅黑", 10)).pack(anchor='w', pady=(5, 10))
        
        # 详细文本框
        text_area = tk.Text(main_frame, font=("Consolas", 10), wrap='word', bg="#f8f8f8", padx=5, pady=5)
        text_area.insert('1.0', detail)
        text_area.configure(state='disabled') # 只读
        text_area.pack(fill='both', expand=True)

        ttk.Button(main_frame, text="关闭", command=detail_win.destroy).pack(pady=10)

    def on_close(self):
        """关闭窗口并保存位置"""
        if hasattr(self.parent, 'save_window_position'):
            self.parent.save_window_position(self.window, "indicator_help")
        self.window.destroy()

    def refresh_tree(self, data):
        # 清空
        for item in self.tree.get_children():
            self.tree.delete(item)
        # 插入 (Treeview 只展示前两列)
        tag_names = [t[0] for t in self.tree_row_tags]
        for row in data:
            tag = ""
            if row[0] in tag_names:
                tag = row[0]
            elif row[0] == "alert_info":
                tag = "alert_row"
            self.tree.insert("", "end", values=(row[0], row[1]), tags=(tag,))

    def on_search(self, *args):
        query = self.search_var.get().lower()
        if not query:
            self.refresh_tree(self.all_data)
            return
        
        filtered = [
            item for item in self.all_data 
            if query in item[0].lower() or query in item[1].lower() or (len(item)>2 and query in item[2].lower())
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
