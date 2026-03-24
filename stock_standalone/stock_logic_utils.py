import re
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Any, Optional, Union, Callable
from typing import Tuple,List,Dict
from JohnsonUtil import LoggerFactory
import logging
import tkinter as tk
from tkinter import messagebox, scrolledtext
import threading

try:
    from tk_gui_modules.window_mixin import WindowMixin
except ImportError:
    WindowMixin = None

from query_engine_util import query_engine

# 获取或创建日志记录器
logger: logging.Logger = LoggerFactory.getLogger("instock_TK.StockLogic")

# === 概念过滤逻辑 ===
GENERIC_KEYWORDS = [
    "国企改革", "沪股通", "深股通", "融资融券", "高股息", "MSCI", "中字头",
    "央企改革", "标普概念", "B股", "AH股", "转融券", "股权转让", "新股与次新股",
    "战略", "指数", "主题", "计划", "预期", "改革", "通", "国企", "央企"
]

REAL_CONCEPT_KEYWORDS = [
    "半导体", "AI", "机器人", "光伏", "锂电", "医药", "芯片", "5G", "储能",
    "新能源", "军工", "卫星", "航天", "汽车", "算力", "氢能", "量子", "云计算",
    "电商", "游戏", "消费电子", "数据要素", "AI", "大模型"
]

def is_generic_concept(concept_name: str) -> bool:
    """识别是否为泛概念（需过滤）"""
    if any(k in concept_name for k in REAL_CONCEPT_KEYWORDS):
        return False
    if any(k in concept_name for k in GENERIC_KEYWORDS):
        return True
    if len(concept_name) <= 3:
        return True
    if any(x in concept_name for x in ["通", "改革", "指数", "主题", "计划", "战略", "预期"]):
        return True
    return False

def filter_concepts(cat_dict: dict[str, Any]) -> dict[str, Any]:
    """批量过滤概念"""
    INVALID: list[str] = [
        "国企改革", "沪股通", "深股通", "融资融券", "MSCI", "富时", 
        "标普", "中字头", "央企", "基金重仓", "机构重仓", "大盘股", "高股息"
    ]
    VALID_HINTS: list[str] = [
        "能源", "科技", "芯片", "AI", "人工智能", "光伏", "储能", 
        "汽车", "机器人", "碳", "半导体", "电力", "通信", "军工", "医药"
    ]
    res: dict[str, Any] = {}
    for k, v in cat_dict.items():
        if any(bad in k for bad in INVALID):
            continue
        if len(v) > 500 or len(v) < 2:
            continue
        if not any(ok in k for ok in VALID_HINTS):
            continue
        res[k] = v
    return res

def ensure_parentheses_balanced(expr: str) -> str:
    """自动补齐括号并确保外层有括号"""
    expr = expr.strip()
    left_count = expr.count("(")
    right_count = expr.count(")")

    if left_count > right_count:
        expr += ")" * (left_count - right_count)
    elif right_count > left_count:
        expr = "(" * (right_count - left_count) + expr

    if not (expr.startswith("(") and expr.endswith(")")):
        expr = f"({expr})"
    return expr

def remove_invalid_conditions(query: str, invalid_cols: list[str]) -> str:
    """从 query 表达式中剔除包含无效列的条件"""
    query = re.sub(r'\s+', ' ', query).strip()
    for col in invalid_cols:
        pattern: str = (
            rf'(\b(and|or)\s+[^()]*\b{col}\b[^()]*?)'
            rf'|(\([^()]*\b{col}\b[^()]*\))'
            rf'|([^()]*\b{col}\b[^()]*\s+(and|or))'
            rf'|([^()]*\b{col}\b[^()]*)'
        )
        query = re.sub(pattern, lambda m: "", query, flags=re.IGNORECASE)

    query = re.sub(r'\s+(and|or)\s+(\)|$)', ' ', query)
    query = re.sub(r'(\(|^)\s*(and|or)\s+', ' ', query)
    query = re.sub(r'\s{2,}', ' ', query).strip()

    open_count: int = query.count("(")
    close_count: int = query.count(")")
    if open_count > close_count:
        query += ")" * (open_count - close_count)
    elif close_count > open_count:
        query = "(" * (close_count - open_count) + query
    return query


# def extract_columns(expr: str) -> set[str]:
#     """
#     从条件表达式中提取列名
#     """
#     tokens = re.findall(r"[A-Za-z_]\w*", expr)
#     keywords = {
#         "and", "or", "not", "True", "False"
#     }
#     return {t for t in tokens if not t.isupper() and t not in keywords}

RESERVED_SQL_FUNCS = {
    "GREATEST", "LEAST", "MAX", "MIN", "ABS", 
    "greatest", "least", "max", "min", "abs",
    "np", "pd", "df", "self"
}




def extract_columns(expr: str) -> set:
    tokens = re.findall(r"\b[a-zA-Z_][a-zA-Z0-9_]*\b", expr)
    keywords = {"and", "or", "not", "True", "False"}
    return {t for t in tokens if t not in keywords and t not in RESERVED_SQL_FUNCS and not re.fullmatch(r"e\d+", t)}

def eval_condition(row: dict, expr: str) -> Tuple[bool, Optional[str]]:
    # 构建执行上下文，支持 SQL 风格函数
    def _greatest(*args): return np.maximum.reduce(args) if args else None
    def _least(*args): return np.minimum.reduce(args) if args else None
    
    eval_ctx = {
        'GREATEST': _greatest, 'LEAST': _least, 'MAX': _greatest, 'MIN': _least, 'ABS': np.abs,
        'greatest': _greatest, 'least': _least, 'max': _greatest, 'min': _least, 'abs': np.abs,
        'np': np, 'pd': pd
    }
    try:
        # 在 eval 时，row 会作为 locals 被搜索，eval_ctx 作为 globals
        return bool(eval(expr, eval_ctx, row)), None
    except Exception as e:
        return False, str(e)

def test_code_query(df_code: Any, queries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    results = []
    if df_code.empty:
        return [{"error": "df_code is empty"}]

    row = df_code.iloc[-1].to_dict()
    if isinstance(queries, str):
        queries = [{"expr": queries}]
    for que in queries:
        logger.debug(f'que: {que}')
        expr = que["expr"]
        cols = extract_columns(expr)
        missing_cols = [c for c in cols if c not in row]

        if missing_cols:
            results.append({
                "expr": expr,
                "ok": False,
                "reason": "missing_columns",
                "missing": missing_cols
            })
            continue

        # 逐子条件拆分
        # sub_conditions = [x.strip() for x in expr.split("and")]
        sub_conditions = [x.strip() for x in re.split(r'\band\b', expr)]
        sub_results = []
        all_ok = True
        for cond in sub_conditions:
            ok, err = eval_condition(row, cond)
            sub_results.append({
                "condition": cond,
                "ok": ok,
                "values": {c: row[c] for c in extract_columns(cond)}
            })
            if not ok:
                all_ok = False

        results.append({
            "expr": expr,
            "ok": all_ok,
            "reason": "pass" if all_ok else "condition_failed",
            "sub_conditions": sub_results,
            "full_data": row
        })

    return results

def format_check_result(results: List[Dict[str, Any]]) -> str:
    lines = []
    for i, r in enumerate(results, 1):
        lines.append(f"[条件 {i}]")
        lines.append(f"  表达式: {r['expr']}")
        lines.append(f"  是否通过: {'✅ 是' if r['ok'] else '❌ 否'}")

        if "missing" in r:
            lines.append("  缺失字段:")
            for c in r["missing"]:
                lines.append(f"    - {c}")
        elif "sub_conditions" in r:
            # 1. 显示该表达式中涉及的所有字段当前数值
            involved_cols = sorted(list(extract_columns(r['expr'])))
            if involved_cols and "full_data" in r:
                lines.append("  当前涉及字段数值:")
                row_data = r["full_data"]
                for col in involved_cols:
                    val = row_data.get(col, "N/A")
                    lines.append(f"    - {col}: {val}")
            
            # 2. 显示子条件执行详情
            lines.append("  子条件执行详情:")
            for sub in r["sub_conditions"]:
                status = "✅" if sub["ok"] else "❌"
                lines.append(f"    {status} {sub['condition']} → 当前值: {sub['values']}")
        
        lines.append("-" * 30)
        lines.append("")

    return "\n".join(lines)



def check_code(
    df: pd.DataFrame,
    code: str,
    queries: List[Dict[str, Any]],
    parent=None
) -> Any:
    """
    使用 Tk 自定义弹窗显示股票检查报告，并支持显示字段详情。
    """
    if code not in df.index:
        messagebox.showwarning(
            "股票检查",
            f"股票代码 {code} 不在当前 DataFrame 中",
            parent=parent
        )
        return None
    df_code = df.loc[[code]]
    # 使用 test_code_query 获取拆分后的结果
    report = test_code_query(df_code, queries)
    summary_text = format_check_result(report)
    # 创建自定义报告窗口
    win = tk.Toplevel(parent)
    win.title(f"股票检查报告 - {code}")
    bg_color = "#E3F2FD"  # 淡蓝色背景
    win.configure(bg=bg_color)
    report_win_name = "check_report_win"
    w_win, h_win = 750, 500
    # 尝试加载上次保存的位置大小
    loaded = False
    scale_factor = getattr(parent, 'scale_factor', 1.0)
    if parent and hasattr(parent, 'load_window_position'):
        _, _, lx, ly = parent.load_window_position(win, report_win_name, default_width=w_win, default_height=h_win)
        if lx is not None:
            loaded = True
    elif WindowMixin:
        helper = WindowMixin()
        helper.scale_factor = scale_factor
        _, _, lx, ly = helper.load_window_position(win, report_win_name, default_width=w_win, default_height=h_win)
        if lx is not None:
            loaded = True
    if not loaded:
        # 如果没有保存的位置，则按之前要求：使右下角对齐鼠标指针
        mx, my = win.winfo_pointerx(), win.winfo_pointery()
        win.geometry(f"{w_win}x{h_win}+{max(0, mx - w_win)}+{max(0, my - h_win)}")
    if parent:
        win.transient(parent)
    def on_close_report():
        """关闭时保存位置"""
        if parent and hasattr(parent, 'save_window_position'):
            parent.save_window_position(win, report_win_name)
        elif WindowMixin:
            helper = WindowMixin()
            helper.scale_factor = scale_factor
            helper.save_window_position(win, report_win_name)
        win.destroy()
    win.protocol("WM_DELETE_WINDOW", on_close_report)
    # 结果显示区域
    tk.Label(win, text="[ 检查结果摘要 ]", font=("微软雅黑", 10, "bold"), bg=bg_color).pack(anchor="w", padx=10, pady=5)
    st = scrolledtext.ScrolledText(win, wrap=tk.WORD, height=15)
    st.pack(fill="both", expand=True, padx=10, pady=5)
    st.insert(tk.END, summary_text)
    st.config(state=tk.DISABLED)
    def show_all_details():
        """显示所有字段的值 (按顺序 col: 值)"""
        details_win = tk.Toplevel(win)
        details_win.title(f"数据详情内容 - {code}")
        details_win.configure(bg=bg_color)
        detail_win_name = "check_details_win"
        w_det, h_det = 500, 800
        # 尝试加载位置
        loaded_det = False
        if parent and hasattr(parent, 'load_window_position'):
            _, _, lx, ly = parent.load_window_position(details_win, detail_win_name, default_width=w_det, default_height=h_det)
            if lx is not None:
                loaded_det = True
        elif WindowMixin:
            helper = WindowMixin()
            helper.scale_factor = scale_factor
            _, _, lx, ly = helper.load_window_position(details_win, detail_win_name, default_width=w_det, default_height=h_det)
            if lx is not None:
                loaded_det = True
        if not loaded_det:
            # 调整位置：使右下角对齐鼠标指针
            mx, my = details_win.winfo_pointerx(), details_win.winfo_pointery()
            details_win.geometry(f"{w_det}x{h_det}+{max(0, mx - w_det)}+{max(0, my - h_det)}")
        def on_close_details():
            if parent and hasattr(parent, 'save_window_position'):
                parent.save_window_position(details_win, detail_win_name)
            elif WindowMixin:
                helper = WindowMixin()
                helper.scale_factor = scale_factor
                helper.save_window_position(details_win, detail_win_name)
            details_win.destroy()
        details_win.protocol("WM_DELETE_WINDOW", on_close_details)
        row_dict = df.loc[code].to_dict()
        # 提取查询中涉及的列以便高亮或优先显示
        used_cols = set()
        for r in report:
            if 'expr' in r:
                used_cols.update(extract_columns(r['expr']))
        lines = []
        if used_cols:
            lines.append(">>> 查询涉及的关键字段:")
            for c in sorted(list(used_cols)):
                lines.append(f"  {c}: {row_dict.get(c, 'N/A')}")
            lines.append("-" * 40)
        lines.append(">>> 所有字段列表 (DataFrame 顺序):")
        for c in df.columns:
            lines.append(f"{c}: {row_dict.get(c, 'N/A')}")
        detail_text = "\n".join(lines)
        dst = scrolledtext.ScrolledText(details_win, wrap=tk.WORD)
        dst.pack(fill="both", expand=True, padx=10, pady=10)
        dst.insert(tk.END, detail_text)
        dst.config(state=tk.DISABLED)
        # 增加一个简单的查找/过滤功能
        filter_frame = tk.Frame(details_win, bg=bg_color)
        filter_frame.pack(fill="x", padx=10, pady=5)
        tk.Label(filter_frame, text="过滤字段:", bg=bg_color).pack(side="left")
        search_var = tk.StringVar()
        search_entry = tk.Entry(filter_frame, textvariable=search_var)
        search_entry.pack(side="left", fill="x", expand=True, padx=5)
        def on_search(*args):
            query = search_var.get().lower()
            filtered_lines = [line for line in lines if query in line.lower()]
            dst.config(state=tk.NORMAL)
            dst.delete("1.0", tk.END)
            dst.insert(tk.END, "\n".join(filtered_lines))
            dst.config(state=tk.DISABLED)
        search_var.trace_add("write", on_search)
    # 按钮栏
    btn_frame = tk.Frame(win, bg=bg_color)
    btn_frame.pack(fill="x", pady=10)
    btn_details = tk.Button(btn_frame, text="显示详情", command=show_all_details, 
                            bg="#2196F3", fg="white", font=("微软雅黑", 9, "bold"))
    btn_details.pack(side="left", padx=20)
    btn_close = tk.Button(btn_frame, text="关闭窗口", command=on_close_report)
    btn_close.pack(side="right", padx=20)
    # 确保窗口在前台
    win.lift()
    win.focus_force()
    return report
def test_code_against_queries(df_code: pd.DataFrame, queries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    测试单只股票（或小型数据集）是否符合多个查询条件。
    重构：使用新的 PandasQueryEngine 执行，替代旧的复杂正则剥离逻辑。
    """
    if not isinstance(df_code, pd.DataFrame) or df_code.empty:
        return []
    results: list[dict[str, Any]] = []
    for q in queries:
        expr: Any = q.get("query", "")
        if not isinstance(expr, str) or not expr:
            continue
        hit_count: int = 0
        try:
            # 使用 PandasQueryEngine 执行引擎，它会自动处理 columns 注入和 eval/exec 降级
            res = query_engine.execute(df_code, expr)
            # 统计命中结果
            if isinstance(res, pd.DataFrame):
                hit_count = len(res)
            elif isinstance(res, (pd.Series, np.ndarray, list)):
                hit_count = len(res)
            elif isinstance(res, (bool, np.bool_)):
                hit_count = 1 if res else 0
            else:
                # 兜底：如果是数值/非空对象，视为命中
                hit_count = 1 if res else 0
        except Exception as e:
            logger.debug(f"test_code_against_queries failed for query [{expr}]: {e}")
            hit_count = 0
        results.append({
            "query": expr,
            "note": q.get("note", ""),
            "starred": q.get("starred", 0),
            "hit": hit_count
        })
    return results
def estimate_virtual_volume_simple(now=None):
    """估算当前时间已完成的成交量比例"""
    if now is None:
        now = datetime.now()
    t = now.time()
    minutes = t.hour * 60 + t.minute
    segments = [
        (9*60+30, 10*60, 0.25),
        (10*60, 11*60, 0.50),
        (11*60, 11*60+30, 0.60),
        (13*60, 14*60, 0.78),
        (14*60, 15*60, 1.00),
    ]
    passed_ratio = 0.0
    prev_ratio = 0.0
    for start, end, ratio in segments:
        if minutes <= start:
            passed_ratio = prev_ratio
            break
        elif start < minutes <= end:
            seg_progress = (minutes - start) / (end - start)
            passed_ratio = prev_ratio + (ratio - prev_ratio) * seg_progress
            break
        prev_ratio = ratio
    else:
        passed_ratio = 1.0
    return max(passed_ratio, 0.05)
def get_row_tags(latest_row: Union[pd.Series, dict[str, Any]]) -> list[str]:
    """
    根据最新行情数据返回 Treeview 行标签列表
    """
    row_tags: list[str] = []
    low: Any = latest_row.get("low")
    lastp1d: Any = latest_row.get("lastp1d")
    high: Any = latest_row.get("high")
    high4: Any = latest_row.get("high4")
    ma5d: Any = latest_row.get("ma5d")
    ma20d: Any = latest_row.get("ma20d")
    ma60d: Any = latest_row.get("ma60d") # [NEW] 引入趋势基准
    close: Any = latest_row.get("close", latest_row.get("trade", 0))
    percent_val: Any = latest_row.get("percent", latest_row.get("per1d", 0))

    # 🚀 [TREND] 强势结构识别：均线顺向排列 MA5 > MA20 > MA60 且价格在 60 日线上
    if pd.notna(ma5d) and pd.notna(ma20d) and pd.notna(ma60d):
        if ma5d > ma20d > ma60d and close > ma60d:
            row_tags.append("bullish_trend")

    # 1️⃣ 红色：低点 > 昨收
    if pd.notna(low) and pd.notna(lastp1d):
        if low > lastp1d:
            row_tags.append("red_row")
    # 2️⃣ 橙色：高点或低点突破 high4
    if pd.notna(high) and pd.notna(high4):
        if high > high4 or (pd.notna(low) and low > high4):
            row_tags.append("orange_row")
    # 3️⃣ 紫色：弱势，低于 ma5d
    if pd.notna(high) and pd.notna(ma5d):
        if high < ma5d:
            row_tags.append("purple_row")
    # 4️⃣ 黄色：临界或预警，低于 ma20d
    if pd.notna(low) and pd.notna(ma20d):
        if low < ma20d:
            row_tags.append("yellow_row")
    # 5️⃣ 绿色：跌幅明显 <2% 且低于昨收
    if pd.notna(percent_val) and pd.notna(low) and pd.notna(lastp1d):
        if percent_val < 2 and low < lastp1d:
            row_tags.append("green_row")
    return row_tags
def safe_prev_signal_array(df: Optional[pd.DataFrame]) -> np.ndarray:
    """
    生成 prev_signal_arr，确保不会因为 df 异常、空值、结构错误而崩溃。
    """
    if df is None or df.empty:
        return np.array([])
    if 'prev_signal' not in df.columns:
        df.loc[:, 'prev_signal'] = None
    raw_vals: list[Any] = df['prev_signal'].tolist()
    safe_vals: list[int] = []
    for v in raw_vals:
        if isinstance(v, (pd.Series, np.ndarray, list, tuple, dict)):
            safe_vals.append(0)
            continue
        if isinstance(v, str):
            safe_vals.append(1 if v in ('BUY_N', 'BUY_S') else 0)
            continue
        if v is None or (isinstance(v, float) and np.isnan(v)):
            safe_vals.append(0)
            continue
        safe_vals.append(0)
    return np.array(safe_vals)
def toast_message(master, text, duration=1500):
    """短暂提示信息（浮层，不阻塞）"""
    toast = tk.Toplevel(master)
    toast.overrideredirect(True)
    toast.attributes("-topmost", True)
    label = tk.Label(toast, text=text, bg="black", fg="white", padx=10, pady=1)
    label.pack()
    try:
        master.update_idletasks()
        master_x = master.winfo_rootx()
        master_y = master.winfo_rooty()
        master_w = master.winfo_width()
    except Exception:
        master_x, master_y, master_w = 100, 100, 400
    toast.update_idletasks()
    toast_w = toast.winfo_width()
    toast_h = toast.winfo_height()
    toast.geometry(f"{toast_w}x{toast_h}+{master_x + (master_w-toast_w)//2}+{master_y + 50}")
    toast.after(duration, toast.destroy)

class RealtimeSignalManager:
    state_df: pd.DataFrame

    def __init__(self) -> None:
        # [FIX] 增加线程锁，确保跨线程计算信号时的状态一致性，防止 GIL 冲突
        self._lock = threading.Lock()
        # 使用 DataFrame 存储状态以实现向量化更新
        self.state_df = pd.DataFrame(columns=[
            'prev_now', 'today_high', 'today_low', 'prev_signal', 'down_streak'
        ])
        # 针对最近成交量的特殊处理（由于是滚动窗口，暂时保留 dict 或使用 numpy 矩阵）
        self.volume_history = {} # code -> list

    def update_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df
            
        # [FIX] 处理重复索引，防止 reindex/loc 报错
        if df.index.duplicated().any():
            df = df[~df.index.duplicated(keep='first')]
            
        # [FIX] 兼容不同的现价列名 (now, trade, price, close)
        price_col = 'now'
        for col in ['now', 'trade', 'price', 'close']:
            if col in df.columns:
                price_col = col
                break

        # 确保 code 是索引且存在列中
        if 'code' not in df.columns:
            df['code'] = df.index.astype(str).str.zfill(6)
        if df.index.name != 'code':
            df.set_index('code', inplace=True, drop=False)

        codes = df.index
        
        with self._lock:
            # 快速更新 state_df，补齐缺失的股票
            missing_codes = codes.difference(self.state_df.index)
            if not missing_codes.empty:
                new_states = pd.DataFrame({
                    'prev_now': df.loc[missing_codes, price_col],
                    'today_high': df.loc[missing_codes, 'high'],
                    'today_low': df.loc[missing_codes, 'low'],
                    'prev_signal': None,
                    'down_streak': 0
                }, index=missing_codes)
                self.state_df = pd.concat([self.state_df, new_states])
                for c in missing_codes:
                    self.volume_history[c] = [df.at[c, 'volume']]
    
            # 提取历史状态数据
            state = self.state_df.loc[codes].copy()
            # 提取成交量历史 (提前在持有锁时完成，防止后续向量化计算时被其他线程修改 dict)
            avg_vol_list = []
            for c in codes:
                v_list = self.volume_history.get(c, [])
                avg_vol_list.append(np.mean(v_list) if v_list else 0.0)
            avg_vol_arr = np.array(avg_vol_list)
        
        # [FIX] 重新提取当前价格数组，用于后续向量化计算
        now_arr = df[price_col].values
        
        high_arr = df['high'].values
        low_arr = df['low'].values
        volume_arr = df['volume'].values
        
        # 向量化计算当前最高的/最低的价格
        updated_today_high = np.maximum(state['today_high'].values, high_arr)
        updated_today_low = np.minimum(state['today_low'].values, low_arr)
        
        # 计算辅助指标
        ma51d = df.get('ma51d', now_arr).values if 'ma51d' in df.columns else now_arr
        ma10d = df.get('ma10d', now_arr).values if 'ma10d' in df.columns else now_arr
        lastp1d = df.get('lastp1d', now_arr).values if 'lastp1d' in df.columns else now_arr
        lastp2d = df.get('lastp2d', now_arr).values if 'lastp2d' in df.columns else now_arr
        lastp3d = df.get('lastp3d', now_arr).values if 'lastp3d' in df.columns else now_arr
        macddif = df.get('macddif', 0).values if 'macddif' in df.columns else np.zeros(len(df))
        macddea = df.get('macddea', 0).values if 'macddea' in df.columns else np.zeros(len(df))
        macd = df.get('macd', 0).values if 'macd' in df.columns else np.zeros(len(df))
        macdlast1 = df.get('macdlast1', 0).values if 'macdlast1' in df.columns else np.zeros(len(df))
        macdlast2 = df.get('macdlast2', 0).values if 'macdlast2' in df.columns else np.zeros(len(df))
        macdlast3 = df.get('macdlast3', 0).values if 'macdlast3' in df.columns else np.zeros(len(df))
        rsi = df.get('rsi', 50).values if 'rsi' in df.columns else np.full(len(df), 50.0)
        kdj_j = df.get('kdj_j', 50).values if 'kdj_j' in df.columns else np.full(len(df), 50.0)
        kdj_k = df.get('kdj_k', 50).values if 'kdj_k' in df.columns else np.full(len(df), 50.0)
        kdj_d = df.get('kdj_d', 50).values if 'kdj_d' in df.columns else np.full(len(df), 50.0)
        open_arr = df.get('open', now_arr).values if 'open' in df.columns else now_arr

        # 向量化成交量异常判断
        # ⚡ 优化：使用预计算好的均值数组，避免在向量化逻辑中进行循环
        vol_boom_now = volume_arr > avg_vol_arr

        # 向量化逻辑判断
        trend_up = ma51d > ma10d
        price_rise = (lastp1d > lastp2d) & (lastp2d > lastp3d)
        macd_bull = (macddif > macddea) & (macd > 0)
        macd_accel = (macdlast1 > macdlast2) & (macdlast2 > macdlast3)
        rsi_mid = (rsi > 45) & (rsi < 75)
        kdj_bull = (kdj_j > kdj_k) & (kdj_k > kdj_d)
        kdj_strong = kdj_j > 60
        morning_gap_up = open_arr <= low_arr * 1.001
        intraday_up = now_arr > state['prev_now'].values
        intraday_high_break = now_arr > updated_today_high
        intraday_low_break = now_arr < updated_today_low

        # 更新连跌天数
        updated_down_streak = np.where(now_arr < state['prev_now'].values, state['down_streak'].values + 1, 0)

        # 评分系统
        score = np.zeros(len(df))
        score += trend_up * 2
        score += price_rise * 1
        score += macd_bull * 1
        score += macd_accel * 2
        score += rsi_mid * 1
        score += np.nan_to_num(rsi - 50) * 0.05
        score += kdj_bull * 1
        score += kdj_strong * 1
        score += morning_gap_up * 2
        score += intraday_up * 1
        score += intraday_high_break * 2
        score += vol_boom_now * 1
        score += ((updated_down_streak >= 2) & (now_arr > state['prev_now'].values * 1.005)) * 2

        # 信号逻辑
        prev_signal_arr = safe_prev_signal_array(df)
        score += prev_signal_arr

        df['signal_strength'] = score
        df['signal'] = ''
        df.loc[score >= 9, 'signal'] = 'BUY_S'
        df.loc[(score >= 6) & (score < 9), 'signal'] = 'BUY_N'
        df.loc[(score < 6) & (macd < 0), 'signal'] = 'SELL_WEAK'

        sell_cond = ((macddif < macddea) & (macd < 0)) | ((rsi < 45) & (kdj_j < kdj_k)) | \
                    ((now_arr < ma51d) & (macdlast1 < macdlast2)) | intraday_low_break
        df.loc[sell_cond, 'signal'] = 'SELL'

        # ⚡ 批量同步回 state_df
        with self._lock:
            self.state_df.loc[codes, 'prev_now'] = now_arr
            self.state_df.loc[codes, 'today_high'] = updated_today_high
            self.state_df.loc[codes, 'today_low'] = updated_today_low
            self.state_df.loc[codes, 'down_streak'] = updated_down_streak
            self.state_df.loc[codes, 'prev_signal'] = df['signal'].values
            
            # 处理成交量历史
            for i, c in enumerate(codes):
                v_hist = self.volume_history.get(c, [])
                v_hist.append(volume_arr[i])
                if len(v_hist) > 5:
                    v_hist.pop(0)
                self.volume_history[c] = v_hist

        return df

def calc_support_resistance(df: pd.DataFrame) -> pd.DataFrame:
    """
    根据通达信逻辑计算撑压位（压力）和支撑位
    """
    LLV: Callable[[pd.Series, int], pd.Series] = lambda x, n: x.rolling(n, min_periods=1).min()
    HHV: Callable[[pd.Series, int], pd.Series] = lambda x, n: x.rolling(n, min_periods=1).max()
    SMA: Callable[[pd.Series, int, int], pd.Series] = lambda x, n, m: x.ewm(alpha=m/n, adjust=False).mean()

    RSV13: pd.Series = (df['close'] - LLV(df['low'], 13)) / (HHV(df['high'], 13) - LLV(df['low'], 13)) * 100
    ARSV: pd.Series = SMA(RSV13, 3, 1)
    AK: pd.Series = SMA(ARSV, 3, 1)
    AD: pd.Series = 3 * ARSV - 2 * AK

    RSV55: pd.Series = (df['close'] - LLV(df['low'], 55)) / (HHV(df['high'], 55) - LLV(df['low'], 55)) * 100
    ARSV24: pd.Series = SMA(RSV55, 3, 1)
    AK24: pd.Series = SMA(ARSV24, 3, 1)
    AD24: pd.Series = 3 * ARSV24 - 2 * AK24

    cross_up: pd.Series = (AD24 > AD) & (AD24.shift(1) <= AD.shift(1))

    pressure: list[Optional[float]] = []
    last_high: Optional[float] = None
    for i in range(len(df)):
        if cross_up.iloc[i]:
            last_high = float(df['high'].iloc[i])
        pressure.append(last_high)
    df.loc[:, 'pressure'] = pressure
    df.loc[:, 'support'] = LLV(df['high'], 30)
    return df

def calc_breakout_signals(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["signal_strength"] = 0
    df["signal"] = ""

    ma_short = df.get('ma51d', df['close']).values
    ma_mid = df.get('ma10d', df['close']).values

    cond_trend_up = (df['close'] > ma_short) & (ma_short > ma_mid)
    cond_trend_turn = (df['close'] > ma_short) & (df['ma51d'].diff() > 0)
    cond_price_rise = (df['lastp1d'] > df['lastp2d']) & (df['lastp2d'] > df['lastp3d'])

    cond_macd_bull = (df['macddif'] > df['macddea']) & (df['macd'] > 0)
    cond_macd_accel = (df['macdlast1'] > df['macdlast2']) & (df['macdlast2'] > df['macdlast3'])

    cond_rsi_mid = (df['rsi'] > 45) & (df['rsi'] < 75)
    cond_rsi_up = df['rsi'].diff() > 2

    cond_kdj_bull = (df['kdj_j'] > df['kdj_k']) & (df['kdj_k'] > df['kdj_d'])
    cond_kdj_strong = (df['kdj_j'] > 60)

    cond_break_high = df['close'] > df['lasth3d']
    cond_break_mid = df['close'] > df.get('max5', df['close'])

    cond_vol_boom = df['volume'] > 1

    score = 0
    score += cond_trend_up * 2
    score += cond_trend_turn * 1
    score += cond_price_rise * 1
    score += cond_macd_bull * 1
    score += cond_macd_accel * 2
    score += cond_rsi_mid * 1
    score += cond_rsi_up * 1
    score += cond_kdj_bull * 1
    score += cond_kdj_strong * 1
    score += cond_break_high * 2
    score += cond_break_mid * 1
    score += cond_vol_boom * 1

    df['signal_strength'] = score
    df.loc[df['signal_strength'] >= 8, 'signal'] = 'BUY_S'
    df.loc[(df['signal_strength'] >= 5) & (df['signal_strength'] < 8), 'signal'] = 'BUY_N'
    df.loc[(df['signal_strength'] < 5) & (df['macd'] < 0), 'signal'] = 'SELL_WEAK'

    sell_cond = (
        ((df['macddif'] < df['macddea']) & (df['macd'] < 0)) |
        ((df['rsi'] < 45) & (df['kdj_j'] < df['kdj_k'])) |
        ((df['close'] < ma_short) & (df['macdlast1'] < df['macdlast2']))
    )
    df.loc[sell_cond, "signal"] = "SELL"
    return df

# 管理器实例
signal_manager = RealtimeSignalManager()

def detect_signals(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    # 尽量避免全量 copy，除非确实需要修改原 df 结构
    if "code" not in df.columns:
        df["code"] = df.index.astype(str).str.zfill(6)

    # 这里的 df 已经在后面通过 signal_manager 修改，不再需要额外的 copy
    df = signal_manager.update_signals(df)

    df["emotion"] = "中性"
    df.loc[df.get("volume", 0) > 1.2, "emotion"] = "乐观"
    df.loc[df.get("volume", 0) < 0.8, "emotion"] = "悲观"
    return df

if __name__ == '__main__':
    from JSONData import tdx_data_Day as tdd
    code = '920088'
    df = tdd.get_tdx_append_now_df_api(code)

    queries = [
        {
            "name": "main_rule",
            "expr": "(vol > 1e8 or volume > 2) and (open <= nlow or (open > lasth1d and low >= lastp1d)) "
                    "and close > lastp1d and a1_v > 10 and percent > 3 and close > nclose and win > 2"
        }
    ]

    result = test_code_query(df, queries)
    print(f'test_code_query: {(format_check_result(result))}')
