# -*- coding: utf-8 -*-
import os
import json
import tkinter as tk
from tkinter import ttk
import re
from typing import List, Tuple, Dict, Any, Optional
from JohnsonUtil import LoggerFactory

log = LoggerFactory.getLogger("indicator_help")

def load_custom_indicator_help() -> List[Tuple[str, str, str]]:
    """
    外置持久化补充指标文档动态加载器。
    打包后用户仅需修改/扩展 config/indicator_help_custom.json，
    无需重新打包或重启主程序，重新按 Ctrl + / 即可热加载生效。
    """
    custom_items = []
    try:
        from sys_utils import get_conf_path
        cfg_file = get_conf_path("config/indicator_help_custom.json")
        if cfg_file and os.path.exists(cfg_file) and os.path.getsize(cfg_file) > 0:
            with open(cfg_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    for entry in data:
                        if isinstance(entry, dict):
                            k = str(entry.get("key", "")).strip()
                            s = str(entry.get("summary", "")).strip()
                            d = str(entry.get("detail", "")).strip()
                            if k:
                                custom_items.append((k, s, d))
                        elif isinstance(entry, (list, tuple)) and len(entry) >= 2:
                            k = str(entry[0]).strip()
                            s = str(entry[1]).strip()
                            d = str(entry[2]).strip() if len(entry) > 2 else ""
                            if k:
                                custom_items.append((k, s, d))
    except Exception as e:
        log.warning(f"Failed to load custom indicator help from config/indicator_help_custom.json: {e}")
    return custom_items

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
        tip_label = ttk.Label(self.window, text="提示: 双击列表项查看详情 | 支持外置补充配置 config/indicator_help_custom.json (免打包)", foreground="gray")
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
            
            ("ch_upper / ch_mid / ch_lower", "通达信自动通道上轨、中轨(回归线)、下轨", 
             "详细说明：基于通达信『自动画通道』算法，全图 BARSLAST 动态寻优极值顶点与底点拟合线性回归中轨(ch_mid)，上下延伸 5 阶动态斐波那契支撑/阻力通道(ch_upper, ch_lower)。\n\n"
             "Query同义词: ch_upper, ch_mid, ch_lower"),

            ("ch_slope / ch_slope_deg", "自动通道物理线性回归斜率与倾角 (°)", 
             "详细说明：衡量通道整体倾斜度。斜率 > 0 (倾角 > 0°) 代表上升趋势通道；斜率 < 0 代表下降趋势通道。\n\n"
             "Query同义词: ch_slope, slope, ch_slope_deg, slope_deg"),

            ("ch_anchor_high_price / ch_anchor_low_price", "自动通道顶点最高价 / 底点最低价", 
             "详细说明：自动通道拟合所锚定的全历史高点价格(upper_price)与低点价格(lower_price)。\n\n"
             "Query同义词: ch_anchor_high_price (ch_high_price), ch_anchor_low_price (ch_low_price)"),

            ("ch_tc2 / ch_bc2", "通道顶点距今 K 线数 (tc2) / 底点距今 K 线数 (bc2)", 
             "详细说明：通达信 BARSLAST 动态寻优测得的顶点与底点距离当前交易日的 K 线根数。\n\n"
             "Query同义词: ch_tc2 (tc2, high_bars_ago), ch_bc2 (bc2, low_bars_ago)"),

            ("ch_nod", "极值高低点间隔天数 (nod = abs(tc2 - bc2))", 
             "详细说明：统计股价从最高顶点下跌至最低底点（或从底点上涨至顶点）所经历的洗盘/拉升 K 线天数。\n\n"
             "Query同义词: ch_nod, nod, extrema_bars"),

            ("ch_pattern", "【核心】趋势格局判定 (1: 触底反弹/震荡走高, -1: 触顶回落/震荡下跌)", 
             "详细逻辑：\n"
             " 1 : bc2 < tc2，底点比顶点更靠近现在，代表低位见底后进入震荡走高/反弹格局。\n"
             "-1 : tc2 < bc2，顶点比底点更靠近现在，代表高位见顶后进入回落/派发格局。\n\n"
             "Query同义词: ch_pattern, trend_pattern, channel_pattern"),

            ("ch_dir", "【核心】通道方向标识 (1: 向上, -1: 向下, 0: 平行)", 
             "详细说明：基于自动通道中轨线性回归斜率(ch_slope)判定的通道全局运行方向标识。\n"
             " 1 : 上涨通道 (中轨向上倾斜)\n"
             "-1 : 下跌通道 (中轨向下倾斜)\n"
             " 0 : 水平横盘通道\n\n"
             "Query同义词: ch_dir, channel_dir"),

            ("ch_pos", "【核心】通道相对位置百分比 (%) (0% 下轨 ~ 100% 上轨)", 
             "详细说明：当前最新收盘价处于通道下轨 (0%) 到上轨 (100%) 之间的百分比位置 ((close - lower) / width * 100)。\n"
             "ch_pos <= 30 代表股价回踩到通道下轨支撑区，适合寻找低吸/震荡企稳点；\n"
             "ch_pos >= 80 代表股价触及通道上轨压力区。\n\n"
             "Query同义词: ch_pos, channel_pos, ch_pct"),

            ("ch_width", "通道极值宽度比例 (%)", 
             "详细说明：通道上轨与下轨的价格差占中轨价格的百分比 ((upper - lower) / mid * 100)，反映通道波动张力与喇叭口扩张/收敛程度。\n\n"
             "Query同义词: ch_width, channel_width"),

            ("ch_supp_price / supp_price", "【核心】通达信上涨支撑线今日价格 (元)", 
             "详细说明：通达信 KX DRAWLINE 算法从历史低点(ch_bc2)向上延伸至今日的精准反弹支撑价格(对应图表上红字如『支撑:9.38元』)。当股价回踩支撑线企稳时构成极佳买点。\n\n"
             "Query同义词: ch_supp_price, supp_price, support_price, ch_supp, 支撑价"),

            ("ch_supp_slope / ch_supp_slope_deg", "【核心】上涨支撑线方向斜率与反弹倾角 (°)", 
             "详细说明：衡量通达信上涨支撑线的延伸方向与反弹攻击倾角：\n"
             "ch_supp_slope > 0 或 ch_supp_slope_deg > 0 代表支撑线昂首向上（上涨支撑线）；\n"
             "数值越大(如 +25°、+45°)代表底部探明后的反弹上攻动能越强劲。\n\n"
             "Query同义词: ch_supp_slope, supp_slope, ch_supp_slope_deg, supp_slope_deg, supp_deg, 支撑角度"),

            ("ch_supp_pos / supp_pos / supp_bias", "【核心】支撑线相对位置偏离度 (%)", 
             "详细说明：当前最新价格相对于今日支撑价格的偏离百分比 ((close - supp_price) / supp_price * 100)。\n"
             "正值(如 +1.5%)表示股价稳稳站在支撑线上方，负值表示破位跌破支撑线。\n"
             "ch_supp_pos 在 -1.0% ~ +4.0% 之间代表股价精准在支撑线上方窄幅震荡回踩。\n\n"
             "Query同义词: ch_supp_pos, supp_pos, supp_bias, 支撑偏离"),

            ("ch_supp_days", "支撑线起点距今 K 线天数", 
             "详细说明：自上涨支撑线首个锚定底点开始算起，已持续延伸运行的交易日 K 线根数。\n\n"
             "Query同义词: ch_supp_days, supp_days"),

            ("reversal_line / rev_price", "通达信趋势翻转线价格 (元)", 
             "详细说明：通达信同款趋势翻转防守线价格(趋势线=(EMA5+EMA13+EMA21)/3，翻转=IF(MA3>趋势线, 趋势线, MA3))，对应图表上黄色『反转:8.91元』，用于判定短线趋势翻转与防守位。\n\n"
             "Query同义词: reversal_line, reversal_price, rev_price, 反转价"),

            ("ch_res_price / ch_res_slope / ch_res_slope_deg", "通达信阻力线价格、斜率与倾角", 
             "详细说明：基于近期波段顶点与下飘形成的动态压力/阻力线价格与倾角。\n\n"
             "Query同义词: ch_res_price, res_price, ch_res_slope, ch_res_slope_deg"),

            ("fib_50 / fib_38 / fib_61", "斐波那契波段中轴与各阶黄金分割位", 
             "详细说明：自动通道 5 阶斐波那契回撤中轴与支撑阻力价格(fib_50 为 50% 轴心位，fib_38 为 38.2% 强势回调支撑位)。\n\n"
             "Query同义词: fib_50, fib_38, fib_61, fib_high, fib_low"),

            ("sig_bottom", "【信号】MACD/变速率低位见底企稳信号 (1: 见底)", 
             "详细说明：结合 MACD 柱状图二次微分与 A1X 变速率识别出的低位止跌见底信号 (sig_bottom=1)。\n\n"
             "Query同义词: sig_bottom, bottom_signal, 见底信号"),

            ("sig_launch", "【信号】SK/SD 极低位启动起爆信号 (1: 启动)", 
             "详细说明：SK/SD 动能线极低位金叉向上且配合量价异动触发的起爆信号 (sig_launch=1)。\n\n"
             "Query同义词: sig_launch, launch_signal, 启动信号"),

            ("sig_escape", "【信号】RSI6 高位逃顶预警信号 (1: 逃顶)", 
             "详细说明：RSI6 超买区域下穿 84 触发的高位逃顶警示信号 (sig_escape=1)。\n\n"
             "Query同义词: sig_escape, escape_signal, 逃顶信号"),

            ("STRATEGY: 通道支撑震荡低吸", "【策略用例】寻找上涨通道中在通道下轨/支撑线附近震荡企稳个股", 
             "策略说明：要求大趋势处于上涨通道(ch_dir==1)，且价格回踩至通道下轨支撑区(ch_pos<=35)或支撑线附近(ch_supp_pos在-1%~5%)企稳，守住下轨不破位(close>=ch_lower)。\n\n"
             "Query推荐组：\n"
             "df.query('ch_dir == 1 and ch_slope_deg > 1.5 and close >= ch_lower and ch_pos <= 35 and ch_supp_pos >= -1.0')"),

            ("STRATEGY: 通道触底反弹", "【策略用例】寻找近期探底企稳并震荡走高个股", 
             "策略说明：结合自动通道极值，寻找近 15 天内刚见底企稳、股价守牢底部、且在通道内部向上爬升的低吸标的。\n\n"
             "Query推荐组：\n"
             "df.query('ch_pattern == 1 and ch_bc2 <= 15 and close > ch_anchor_low_price and ch_pos > 25.0')"),
            
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
            ("QUERY: 重复/区间自适应展开", "【高级简洁语法】支持 {1-5} 区间与列表展开",
             "【使用说明与详细示例】\n"
             "针对连续多日对比或多指标重复公式，支持使用 {} 自适应展开简洁写法：\n\n"
             "1. 区间同步展开 (Range Sync):\n"
             "   写法: SWL > SWS and ma20d > ma60d and lastp{1-5}d > ma60{1-5}d\n"
             "   展开为: SWL > SWS and ma20d > ma60d and (lastp1d > ma601d and lastp2d > ma602d and lastp3d > ma603d and lastp4d > ma604d and lastp5d > ma605d)\n\n"
             "2. 固定右端区间展开:\n"
             "   写法: lastp{1-5}d > ma60d\n"
             "   展开为: (lastp1d > ma60d and lastp2d > ma60d and lastp3d > ma60d and lastp4d > ma60d and lastp5d > ma60d)\n\n"
             "3. 列表多列展开 (List Expansion):\n"
             "   写法: close > ma{5,10,20}d\n"
             "   展开为: (close > ma5d and close > ma10d and close > ma20d)\n\n"
             "4. 步长与倒序 (Step & Reverse):\n"
             "   写法: lastp{1-5:2}d > 10.0\n"
             "   展开为: (lastp1d > 10.0 and lastp3d > 10.0 and lastp5d > 10.0)\n\n"
             "5. OR 关系与括号嵌套组合 (OR Prefix & Nested Groups):\n"
             "   写法: (SWL > SWS and ma20d > ma60d and lastp{1-5}d > ma60{1-5}d and {or: per{1-3}d > 3.0}) and (close > 0)\n"
             "   展开为: (SWL > SWS and ma20d > ma60d and (lastp1d > ma601d and lastp2d > ma602d and lastp3d > ma603d and lastp4d > ma604d and lastp5d > ma605d) and (per1d > 3.0 or per2d > 3.0 or per3d > 3.0)) and (close > 0)\n"),
        ]

        # [NEW] 动态加载外置持久化补充文档 (实现打包后免重新编译热加载)
        custom_help = load_custom_indicator_help()
        if custom_help:
            existing_keys = {item[0]: idx for idx, item in enumerate(self.all_data)}
            new_additions = []
            for item in custom_help:
                k = item[0]
                if k in existing_keys:
                    self.all_data[existing_keys[k]] = item
                else:
                    new_additions.append(item)
            if new_additions:
                self.all_data = new_additions + self.all_data

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
        """弹出详细说明小窗口（支持位置与尺寸持久化，Esc 仅关闭自身）"""
        detail_win = tk.Toplevel(self.window)
        detail_win.title(f"详情: {title}")
        
        # 恢复持久化位置与尺寸 (默认增大至 780x560 确保 ASCII 图例对齐完整)
        if hasattr(self.parent, 'load_window_position'):
            self.parent.load_window_position(detail_win, "indicator_help_detail", default_width=780, default_height=560)
        else:
            try:
                from gui_utils import load_window_position_simple
                load_window_position_simple(detail_win, "indicator_help_detail", default_width=780, default_height=560)
            except Exception:
                detail_win.geometry("780x560")
                detail_win.update_idletasks()
                x = self.window.winfo_x() + (self.window.winfo_width() // 2) - (detail_win.winfo_width() // 2)
                y = self.window.winfo_y() + (self.window.winfo_height() // 2) - (detail_win.winfo_height() // 2)
                detail_win.geometry(f"+{x}+{y}")

        detail_win.attributes('-topmost', True)

        def close_detail(event=None):
            """关闭详情窗口并保存坐标，阻止 Esc 事件向上传播"""
            if hasattr(self.parent, 'save_window_position'):
                self.parent.save_window_position(detail_win, "indicator_help_detail")
            else:
                try:
                    from gui_utils import save_window_position_simple
                    save_window_position_simple(detail_win, "indicator_help_detail")
                except Exception:
                    pass
            detail_win.destroy()
            return "break"

        detail_win.protocol("WM_DELETE_WINDOW", close_detail)
        detail_win.bind("<Escape>", close_detail)

        # 内容区域
        main_frame = ttk.Frame(detail_win, padding=12)
        main_frame.pack(fill='both', expand=True)

        ttk.Label(main_frame, text=f"{title}", font=("微软雅黑", 12, "bold")).pack(anchor='w')
        ttk.Label(main_frame, text=f"{summary}", font=("微软雅黑", 10)).pack(anchor='w', pady=(4, 8))
        
        # 详细文本框容器 (带垂直与水平滚动条，wrap='none' 确保字符图例永不折行乱码)
        text_frame = ttk.Frame(main_frame)
        text_frame.pack(fill='both', expand=True)

        x_scroll = ttk.Scrollbar(text_frame, orient="horizontal")
        y_scroll = ttk.Scrollbar(text_frame, orient="vertical")
        
        text_area = tk.Text(text_frame, font=("Consolas", 10), wrap='none', bg="#f8f9fa", padx=8, pady=8,
                            xscrollcommand=x_scroll.set, yscrollcommand=y_scroll.set)
        x_scroll.config(command=text_area.xview)
        y_scroll.config(command=text_area.yview)

        y_scroll.pack(side='right', fill='y')
        x_scroll.pack(side='bottom', fill='x')
        text_area.pack(side='left', fill='both', expand=True)

        text_area.insert('1.0', detail)
        text_area.configure(state='disabled') # 只读

        ttk.Button(main_frame, text="关闭 (Esc)", command=close_detail).pack(pady=(8, 0))

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

_INDICATOR_HELP_DICT_CACHE = None

def get_indicator_help_dict():
    """
    解析全量指标字段帮助字典，返回映射结构: {col_name: (summary, detail)}
    使全系统 Treeview 表头悬浮提示与指标说明窗口保持 100% 同步
    """
    global _INDICATOR_HELP_DICT_CACHE
    if _INDICATOR_HELP_DICT_CACHE is not None:
        return _INDICATOR_HELP_DICT_CACHE

    raw_list = [
        ("code", "股票代码", "6 位 A 股标准证券代码。"),
        ("name", "股票名称", "中文股票简称。"),
        ("cycle_stage", "【新增】周期阶段判定。1:筑底/启动, 2:主升/健康, 3:脉冲/扩张, 4:见顶/回落", "判定规则：\n1: Bottoming - 低位放量或均线缠绕后初次抬头\n2: Healthy - 多头排列，支撑有效\n3: Expansion - 加速远离均线，波动率放大\n4: Topping - 高位滞涨，量价背离或跌破关键支撑"),
        ("ch_upper / ch_mid / ch_lower", "通达信自动通道上轨、中轨(回归线)、下轨", 
         "详细说明：基于通达信『自动画通道』算法，全图 BARSLAST 动态寻优极值顶点与底点拟合线性回归中轨(ch_mid)，上下延伸 5 阶动态斐波那契支撑/阻力通道(ch_upper, ch_lower)。\n\nQuery同义词: ch_upper, ch_mid, ch_lower"),
        ("ch_slope / ch_slope_deg", "自动通道物理线性回归斜率与倾角 (°)", 
         "详细说明：衡量通道整体倾斜度。斜率 > 0 (倾角 > 0°) 代表上升趋势通道；斜率 < 0 代表下降趋势通道。\n\nQuery同义词: ch_slope, slope, ch_slope_deg, slope_deg"),
        ("ch_anchor_high_price / ch_anchor_low_price / ch_anchor_high / ch_anchor_low", "自动通道顶点最高价 / 底点最低价", 
         "详细说明：自动通道拟合所锚定的全历史高点价格(upper_price)与低点价格(lower_price)。\n\nQuery同义词: ch_anchor_high_price (ch_high_price), ch_anchor_low_price (ch_low_price)"),
        ("ch_tc2 / ch_bc2", "通道顶点距今 K 线数 (tc2) / 底点距今 K 线数 (bc2)", 
         "详细说明：通达信 BARSLAST 动态寻优测得的顶点与底点距离当前交易日的 K 线根数。\n\nQuery同义词: ch_tc2 (tc2, high_bars_ago), ch_bc2 (bc2, low_bars_ago)"),
        ("ch_nod", "极值高低点间隔天数 (nod = abs(tc2 - bc2))", 
         "详细说明：统计股价从最高顶点下跌至最低底点（或从底点上涨至顶点）所经历的洗盘/拉升 K 线天数。\n\nQuery同义词: ch_nod, nod, extrema_bars"),
        ("ch_pattern", "【核心】趋势格局判定 (1: 触底反弹/震荡走高, -1: 触顶回落/震荡下跌)", 
         "详细逻辑：\n 1 : bc2 < tc2，底点比顶点更靠近现在，代表低位见底后进入震荡走高/反弹格局。\n-1 : tc2 < bc2，顶点比底点更靠近现在，代表高位见顶后进入回落/派发格局。\n\nQuery同义词: ch_pattern, trend_pattern, channel_pattern"),
        ("ch_pos", "通道相对位置百分比 (%)", "当前价格处于 5 阶斐波那契通道下轨 (0%) 到上轨 (100%) 之间的百分比位置。"),
        ("ch_supp_price / supp_price", "【核心】通达信上涨支撑线今日价格 (元)", 
         "详细说明：通达信 KX DRAWLINE 算法从历史低点(ch_bc2)延伸至今日的精准支撑价格(如国统股份 10.68元)。当股价回踩支撑线企稳时构成极佳买点。\n\nQuery同义词: ch_supp_price, supp_price, support_price, ch_supp, 支撑价"),
        ("ch_supp_slope / ch_supp_slope_deg", "上涨支撑线物理斜率与反弹倾角 (°)", 
         "详细说明：衡量自底部(ch_bc2)见底以来支撑线反弹上升的速率(元/天)与攻击倾角(°)。正值代表强劲反弹上涨斜率(如 +43.4°)，补齐大趋势向下时缺失的反弹攻击斜率。\n\nQuery同义词: ch_supp_slope, supp_slope, ch_supp_slope_deg, supp_slope_deg, supp_deg, 支撑角度"),
        ("ch_supp_pos / supp_pos / supp_bias", "支撑线相对位置偏离度 (%)", 
         "详细说明：当前最新价格相对于今日支撑价格的偏离百分比 ((close - supp_price) / supp_price * 100)。正值(如 +1.0%)表示股价稳稳站在支撑线上方，负值表示跌破支撑线。\n\nQuery同义词: ch_supp_pos, supp_pos, supp_bias, 支撑偏离"),
        ("reversal_line / rev_price", "通达信翻转线价格 (元)", 
         "详细说明：通达信同款趋势翻转线价格(趋势线=(EMA5+EMA13+EMA21)/3，翻转=IF(MA3>趋势线, 趋势线, MA3))，用于判定短线趋势翻转与防守位。\n\nQuery同义词: reversal_line, reversal_price, rev_price, 反转价"),
        ("ch_dir", "通道方向 (1: 向上, -1: 向下, 0: 平行)", "基于中轨线性回归斜率确定的通道运行方向标识。"),
        ("ch_width", "通道极值宽度比例 (%)", "通道上轨与下轨的价格差占中轨价格的百分比，反映通道波动张力。"),
        ("ptop / platform_top", "平台顶阻力位 (120日高点中枢)", "基于过去 120 个交易日内局部收盘高点（Peak）经过 ±3% 容忍度聚类拟合算出的平台顶部阻力价格中枢。最高价有效突破该位置触发突破信号。"),
        ("pbottom / platform_bottom", "平台底支撑位 (120日次低点中枢)", "基于过去 120 个交易日内局部收盘低点（Valley）经过 ±3% 容忍度聚类拟合算出的平台底部支撑价格中枢。"),
        ("pbreak / platform_breakout", "平台突破信号标记 (1: 突破, 0: 未突破)", "当盘中最高价突破平台顶阻力位 (high > ptop * 1.01) 且前一日收盘在阻力位下方时，触发平台有效突破信号 (pbreak=1)。"),
        ("pdays / pday", "主升/连阳/平台突破持续天数", "从平台突破/连阳起爆点开始计算，只要最低价守住平台支撑与 MA20 上方，持续累加的主升浪运行天数。"),
        ("obs_d / obs_day / obs_days", "二次起爆观察期运行天数", "离场/平仓标的被送入 Re-entry 观察矩阵后，已持续追踪观察的交易日天数（默认 5 天观察期，超强势标的扩展至 12 天）。"),
        ("resist_next / resist_to", "次级动态目标压力位", "根据近期高点序列、布林上轨及技术线预估的次级向上拓展阻力/目标价格。"),
        ("resist_top", "顶部极值阻力/历史最高压力位", "基于历史密集成交区顶端或前波段最高价格算出的强阻力位。"),
        ("winU / inU", "上升通道阳线/线上运行天数", "统计在上升趋势通道或 MA20 均线上方连续保持强势运行的阳线 K 线天数。"),
        ("winD", "下降通道阴线/线下运行天数", "统计在下降趋势通道或 MA20 均线下方连续弱势探底的阴线 K 线天数。"),
        ("minU / minD", "阳线/阴线波动极值区间天数", "统计特定周期内多头阳线或空头阴线拉升/下跌极值形态的持续时间。"),
        ("percent", "今日实时涨跌幅 (%)", "最新价相对于昨收盘价的涨跌百分比。"),
        ("trade / price / close / lastp0d", "最新成交价格", "实时盘中最新成交价格/收盘价。"),
        ("open / lasto0d", "今日开盘价", "今日开盘第一笔成交价格。"),
        ("high", "今日最高价", "盘中最高成交价格。"),
        ("low", "今日最低价", "盘中最低成交价格。"),
        ("lasth1d / lasth2d / lasth3d", "昨日/前日最高价", "前 1 日(昨日)、前 2 日、前 3 日的盘中最高成交价格。"),
        ("lastl1d / lastl2d / lastl3d / nlow", "昨日/前日最低价", "前 1 日(昨日)、前 2 日、前 3 日的盘中最低成交价格。"),
        ("lastc1d / lastp1d / lastp2d", "昨收/前日收盘价", "前 1 日(昨收)、前 2 日的全天收盘结算价格。"),
        ("lasto1d / lasto2d", "昨日/前日开盘价", "前 1 日(昨日)、前 2 日开盘第一笔成交价格。"),
        ("vwap / vwap_price / nclose", "全天成交量加权平均价 (VWAP 机构均价)", "基于分时分钟成交量与成交额加权算出的全天成交均价 (Volume Weighted Average Price)，代表当日市场整体机构持仓成本线。"),
        ("vwap_cum_2d / vwap_cum_3d / vwap_cum_4d / vwap_cum_5d / vwap_cum_10d", "近 2/3/4/5/10 日加权累计 VWAP 机构成本线", "跨越近 2、3、4、5、10 个交易日连续累加的成交量与成交金额加权均价，代表大资金/机构在近几日的平均建仓成本位。"),
        ("last_vwap / last_nclose1d / last_nclose2d / last_nclose3d", "历史各日 VWAP 机构均价", "上一个交易日 (last_vwap) 及此前各交易日全天成交量加权平均价。"),
        ("fib_50 / fib50 / fib_mid", "50% 斐波那契中轴中枢位", "自动通道或黄金分割波段 50% 核心中轴支撑与阻力价格。"),
        ("fib_19 / fib_38 / fib_61 / fib_80", "斐波那契各阶分位价格", "黄金分割与 5 阶斐波那契通道各分位点支撑阻力位。"),
        ("sig_bottom / bottom_signal", "MACD/变速率低位见底信号 (1: 见底)", "结合 MACD 柱状图二次微分与 A1X 变速率识别出的低位止跌见底 (sig_bottom=1) 信号。"),
        ("sig_top / top_signal", "MACD/变速率高位见顶信号 (1: 见顶)", "高位动能衰竭、顶背离见顶 (sig_top=1) 预警信号。"),
        ("sig_launch / launch_signal", "SK/SD 极低位启动信号 (1: 启动)", "SK/SD 动能线极低位金叉向上 (sig_launch=1) 起爆信号。"),
        ("sig_escape / escape_signal", "RSI6 高位逃顶预警信号 (1: 逃顶)", "RSI6 超买区域高位逃顶预警 (sig_escape=1) 信号。"),
        ("sig_start / start_signal", "趋势初次启动确认信号 (1: 启动)", "低位放量、均线金叉与变速率回升共振触发的趋势初次起爆启动标识。"),
        ("sk_val / sd_val", "随机动能指标 SK 值 / SD 值", "基于高低价振幅与收盘价导出的短线随机动能指标，SK 向上上穿 SD 代表短线起爆。"),
        ("rsi6", "6 日相对强弱指标 RSI", "衡量 6 个交易日内多空力量对比的相对强弱指标，RSI6 < 20 代表极度超跌，RSI6 > 85 代表超买警戒。"),
        ("strong_structure_score / structure_score", "强结构得分 (0-100)", "结合均线顺向、通道斜率、成交量量比及支撑位稳固度加权计算的强结构得分。"),
        ("Trends / Trends_d", "多周期趋势综合得分 (0-100)", "综合日线、周线、月线等多周期均线排列与动能计算的宏观趋势得分。"),
        ("Rank", "全市场个股综合强弱排名", "根据涨幅、量比、爆发力与结构得分在全市场股票中的相对位次排名。"),
        ("td_buy / td_sell", "九转序列买点 (TD Buy) / 卖点 (TD Sell)", "基于狄马克 TD 序列计算出的连续 9 日结构计数买点/卖点信号。"),
        ("volume / vol / nvol", "今日成交量", "成交总量（单位: 手/股）。"),
        ("ratio", "量比（成交量与过去5日均量之比）", "衡量盘中成交放量与萎缩程度的指标。"),
        ("turnover / turnoverratio", "换手率 / 成交金额", "换手率 (%) 或成交金额 (万元/亿元)。"),
        ("dff / macddif / dif", "MACD 指标中的 DIFF 差值", "快线与慢线的差值。"),
        ("dff2 / macddea / dea", "MACD 指标信号差 (DEA 差值)", "MACD 二次信号差值。"),
        ("dff3 / macd", "MACD 柱状图差值", "MACD 红绿柱动态增量。"),
        ("win", "连阳天数", "连续阳线收盘天数。"),
        ("slope", "趋势斜率", "近 10-20 日价格线性回归斜率。"),
        ("power_idx", "爆发力指数", "结合量能、动能与振幅计算的综合爆发起爆指数。"),
        ("topR", "综合强势排名指标", "综合得分越高代表短期攻击性与强势度越高。"),
        ("lastdu4", "最近 4 个交易日的振幅表现", "近 4 个交易日的高低价百分比振幅范围。"),
        ("ma5d / ma10d / ma20d / ma60d / ma120d / ma250d", "日线级别移动平均线 (MA5/10/20/60/120/250)", "移动平均价格。"),
        ("lastv1d / lastv2d", "昨日/前日成交量", "上一个交易日及前交易日的全天成交总量。"),
        ("signal1 / signal2 / signal3", "实时策略信号 1/2/3", "系统盘中实时策略触发的监控/预警/买点信号标记。"),
        ("structure_base", "结构底座评分", "形态结构基座支撑强度分值 (0-100)。"),
        ("score", "综合策略评分", "策略多因子综合加权分值。"),
        ("signal_strength", "信号强度", "策略触发的置信度与强度得分。"),
        ("support_n / support", "动态支撑位 / 近30日低点支撑", "LLV(high, 30)，取最近 30 个交易日高点序列中的最低点支撑。"),
        ("support_to", "目标支撑位", "根据动态支撑线推算的技术目标位。"),
        ("ma205", "MA20 斜率/支撑偏离", "20 日均线拐角偏离度。"),
        ("bull_s", "多头排列状态", "布尔值：MA5 > MA10 > MA20 多头格局。"),
        ("bullbreak", "多头突破", "布尔值：突破均线密集缠绕区。"),
        ("kind", "K 线形态 (U: 上升 / D: 下降)", "根据多日 K 线组合判定的宏观趋势方向。"),
        ("ra / ral", "支撑稳固度天数", "len(df.query('low > ma20d'))，统计最近 20 天内股价始终保持在 MA20 支撑位之上的天数。"),
        ("perc1c / per1d / perc1d", "昨日涨跌幅 (%)", "上一个交易日的涨跌百分比。"),
        ("top15", "【核心】强势上攻/加速突破", "当天强势启动(阳线 >4%), 突破近期新高或布林上轨。"),
        ("lowvol / lv", "10天内最小成交量", "近 10 天内最小成交量。"),
        ("hv", "10天内最大成交量", "近 10 天内最大成交量。"),
        ("last6vol", "6天平均成交量", "近 6 个交易日的平均成交量。"),
        ("lvol", "昨天成交量 (%)", "昨日成交量占近期平均量的比例。"),
        ("boll", "近期布林带位置", "布林带上轨位置/对应计算值。"),
        ("upper", "布林带上轨 (Upper Bound)", "布林带上轨阻力线。"),
        ("middle", "布林带中轨 (Middle Bound/MA20)", "布林带中轨 20 日均线。"),
        ("lower", "布林带下轨 (Lower Bound)", "布林带下轨支撑线。"),
        ("high4 / low4", "最近 4 个交易日最高价/最低价", "近 4 日极值。"),
        ("hmax", "历史最高价位", "Close Highest。"),
        ("vchange", "由于量能变动引起的量比波动", "量能异动增量。"),
        ("top10", "最近 10 个交易日封板/涨停次数", "近 10 日内涨停板频次。"),
        ("red", "主升浪阳K形态标识", "连阳启动阳线形态。"),
        ("green", "下降通道绿K形态标识", "阴线形态。"),
        ("fib / fibl", "主升连贯性 / 波动频次", "15周期内波动幅度大于2%的频次及连贯次数。"),
        ("maxp", "15个周期内的波动幅度百分比", "15 日内最大振幅幅度。"),
        ("bandwidth", "布林带宽度", "Bandwidth，反映股价波动率。"),
        ("couts", "信号触发计数", "异动触发次数。"),
        ("boll_probe", "【潜伏】试盘期信号", "股价当日最高点触及或突破布林上轨但收盘未能站稳。"),
        ("top0", "极端波动/一字板", "low == high and low != 0 一字涨跌停。"),
        ("resist / pressure", "动态压力位", "根据 KDJ 交叉点及历史高点回溯确定的阻力位。"),
        ("op", "区间累计涨幅", "相对于 30 天内最低价格的累计涨跌幅百分比。"),
        ("alert_info", "【系统】🔔 实时报警标注", "当前个股在本会话中触发了实盘报警（语音播报或日志预警）。"),
    ]

    result = {}
    for item in raw_list:
        keys_str = item[0]
        summary = item[1]
        detail = item[2] if len(item) > 2 else ""
        keys = [k.strip() for k in keys_str.split("/") if k.strip()]
        for k in keys:
            result[k] = (summary, detail)
            result[k.lower()] = (summary, detail)

    # [NEW] 动态合入外置持久化配置 (使表头 Tooltip 悬浮提示也能免打包热更新)
    custom_help = load_custom_indicator_help()
    for item in custom_help:
        keys_str = item[0]
        summary = item[1]
        detail = item[2] if len(item) > 2 else ""
        keys = [k.strip() for k in keys_str.split("/") if k.strip()]
        for k in keys:
            result[k] = (summary, detail)
            result[k.lower()] = (summary, detail)

    _INDICATOR_HELP_DICT_CACHE = result
    return result


class TreeColumnTooltip:
    """
    Treeview 表头 (Heading) 悬浮提示框 (Tooltip)
    当鼠标悬停在 Treeview 表头列上时，自动显示该指标列的主要功能说明与详细逻辑
    """
    def __init__(self, tree, get_help_dict_func=None, delay_ms=300):
        self.tree = tree
        self.get_help_dict_func = get_help_dict_func or get_indicator_help_dict
        self.delay_ms = delay_ms
        self.tooltip_window = None
        self.timer_id = None
        self.current_col = None

        self.tree.bind("<Motion>", self._on_motion, add="+")
        self.tree.bind("<Leave>", self._on_leave, add="+")

    def _get_column_info(self, event_x, event_y):
        """
        可靠解构 event.x/y 对应的列 ID (col_name) 与 表头显示文本 (heading_text)
        """
        region = self.tree.identify_region(event_x, event_y)
        if region != "heading":
            return None, None, None

        col_id = self.tree.identify_column(event_x)
        if not col_id:
            return None, None, None

        col_name = None
        heading_text = None

        # 优先通过 tree.column(col_id, option='id') 原生 API 获取真实列名
        try:
            col_name = self.tree.column(col_id, option="id")
        except Exception:
            pass

        try:
            heading_text = self.tree.heading(col_id, option="text")
        except Exception:
            pass

        # 兜底解包
        if not col_name or col_name.startswith("#"):
            try:
                col_idx = int(col_id.replace("#", "")) - 1
                disp_cols = self.tree.cget("displaycolumns")
                if disp_cols == "#all" or disp_cols == ("#all",) or not disp_cols:
                    cols = list(self.tree.cget("columns"))
                else:
                    cols = list(disp_cols)

                if 0 <= col_idx < len(cols):
                    col_name = str(cols[col_idx])
            except Exception:
                pass

        return col_id, col_name, heading_text

    def _on_motion(self, event):
        try:
            col_id, col_name, heading_text = self._get_column_info(event.x, event.y)
            if col_id and (col_name or heading_text):
                target_key = col_name or heading_text
                if target_key != self.current_col:
                    self._cancel_timer()
                    self._hide_tooltip()
                    self.current_col = target_key
                    px, py = event.x_root, event.y_root
                    self.timer_id = self.tree.after(
                        self.delay_ms,
                        lambda c=col_name, h=heading_text, x=px, y=py: self._show_tooltip(c, h, x, y)
                    )
                return
        except Exception:
            pass

        self._cancel_timer()
        self._hide_tooltip()
        self.current_col = None

    def _on_leave(self, event=None):
        # 防御 Windows Toplevel 产生的虚假 Leave 事件：校验鼠标是否仍然在 Treeview 物理坐标范围内
        if event and hasattr(event, 'x_root') and hasattr(event, 'y_root'):
            try:
                rx = self.tree.winfo_rootx()
                ry = self.tree.winfo_rooty()
                rw = self.tree.winfo_width()
                rh = self.tree.winfo_height()
                if rx <= event.x_root <= rx + rw and ry <= event.y_root <= ry + rh:
                    return
            except Exception:
                pass

        self._cancel_timer()
        self._hide_tooltip()
        self.current_col = None

    def _cancel_timer(self):
        if self.timer_id:
            try:
                self.tree.after_cancel(self.timer_id)
            except Exception:
                pass
            self.timer_id = None

    def _hide_tooltip(self):
        if self.tooltip_window:
            try:
                self.tooltip_window.destroy()
            except Exception:
                pass
            self.tooltip_window = None

    def _show_tooltip(self, col_name, heading_text=None, x=None, y=None):
        self._hide_tooltip()
        help_dict = self.get_help_dict_func() if callable(self.get_help_dict_func) else {}

        info = None
        # 多重智能检索逻辑:
        # 1. 精准列名匹配
        if col_name:
            info = help_dict.get(col_name) or help_dict.get(col_name.lower())

        # 2. 周期/多时间维度后缀剥离匹配 (如 ch_nod_w -> ch_nod, ma20d_1d -> ma20d)
        if not info and col_name:
            base_col = re.sub(r'_(?:[1-9]?d|w|m|q|y)$', '', col_name.lower())
            info = help_dict.get(base_col)

        # 3. 表头显示文本匹配 (如 "洗盘拉升天数" 或 "极值高低点间隔天数")
        if not info and heading_text:
            info = help_dict.get(heading_text) or help_dict.get(heading_text.lower())
            if not info:
                for k, v in help_dict.items():
                    if k in heading_text or heading_text in k:
                        info = v
                        break

        # 4. 包含/子串兜底匹配
        if not info and col_name:
            for k, v in help_dict.items():
                if k.lower() in col_name.lower() or col_name.lower() in k.lower():
                    info = v
                    break

        if not info:
            return

        summary = info[0] if isinstance(info, (tuple, list)) and len(info) > 0 else str(info)
        detail = info[1] if isinstance(info, (tuple, list)) and len(info) > 1 else ""

        tw = tk.Toplevel(self.tree)
        tw.wm_overrideredirect(True)
        tw.attributes("-topmost", True)
        tw.configure(bg="#2b2b2b", highlightbackground="#00b0ff", highlightthickness=1)

        screen_w = tw.winfo_screenwidth()
        screen_h = tw.winfo_screenheight()

        if x is None or y is None:
            x = self.tree.winfo_pointerx()
            y = self.tree.winfo_pointery()

        pos_x = min(x + 12, screen_w - 380)
        pos_y = min(y + 22, screen_h - 180)
        tw.geometry(f"+{pos_x}+{pos_y}")

        frame = tk.Frame(tw, bg="#2b2b2b", padx=10, pady=8)
        frame.pack(fill="both", expand=True)

        title_display = f"📊 指标: {col_name or heading_text}"
        if col_name and heading_text and col_name != heading_text:
            title_display = f"📊 指标: {heading_text} ({col_name})"

        lbl_title = tk.Label(
            frame, text=title_display, 
            font=("微软雅黑", 9, "bold"), fg="#4fc3f7", bg="#2b2b2b", anchor="w"
        )
        lbl_title.pack(anchor="w", fill="x")

        if summary:
            lbl_sum = tk.Label(
                frame, text=summary, 
                font=("微软雅黑", 9), fg="#ffffff", bg="#2b2b2b", anchor="w", justify="left", wraplength=340
            )
            lbl_sum.pack(anchor="w", fill="x", pady=(3, 0))

        if detail:
            clean_detail = detail
            if clean_detail.startswith("详细说明："):
                clean_detail = clean_detail[5:]
            lbl_det = tk.Label(
                frame, text=clean_detail, 
                font=("微软雅黑", 8), fg="#ffd54f", bg="#2b2b2b", anchor="w", justify="left", wraplength=340
            )
            lbl_det.pack(anchor="w", fill="x", pady=(5, 0))

        self.tooltip_window = tw


if __name__ == "__main__":
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

