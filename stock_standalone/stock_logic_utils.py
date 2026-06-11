import re
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Any, Optional, Union, Callable
from typing import Tuple,List,Dict
from JohnsonUtil import LoggerFactory
import logging
import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk
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




def extract_columns(expr: str) -> list:
    """
    从条件表达式中提取列名，保持出现顺序并去重。
    """
    tokens = re.findall(r"\b[a-zA-Z_][a-zA-Z0-9_]*\b", expr)
    keywords = {"and", "or", "not", "True", "False"}
    # 保持顺序去重
    seen = set()
    res = []
    for t in tokens:
        if t not in keywords and t not in RESERVED_SQL_FUNCS and not re.fullmatch(r"e\d+", t):
            if t not in seen:
                res.append(t)
                seen.add(t)
    return res

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
        # 🚀 [NEW] 对原始表达式进行预处理，确保支持 ( "a" "b" ) 结构及剥离注释
        expr = query_engine._preprocess_query(que["expr"])
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

        # 逐子条件拆分 (使用 query_engine 统一的智慧拆分逻辑，确保括号嵌套与 OR 分支能平铺展示)
        sub_conditions = query_engine.split_sub_conditions(expr)
        sub_results = []
        
        # [NEW] 整体判定分离：总判定由原始表达式直接 eval 得到，详情列表仅由拆分器生成的子块构成
        all_ok, _ = eval_condition(row, expr)
        
        for cond in sub_conditions:
            ok, err = eval_condition(row, cond)
            sub_results.append({
                "condition": cond,
                "ok": ok,
                "values": {c: row[c] for c in extract_columns(cond)}
            })

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
            # 1. 显示该表达式中涉及的所有字段当前数值 (保持出现在表达式中的顺序)
            involved_cols = extract_columns(r['expr'])
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
    name = df.at[code, 'name'] if 'name' in df.columns else ""
    # 使用 test_code_query 获取拆分后的结果
    report = test_code_query(df_code, queries)
    
    header = f"股票: {code} {name}\n" + "="*40 + "\n"
    summary_text = header + format_check_result(report)
    
    # 智能检查环境并做安全隔离。如果是在非 Tk (如 PyQt) 环境调用 check_code，
    # 我们创建一个隐藏的 tk.Tk() 主窗口，防止多出一个丑陋的空白小 Tk 窗口，
    # 并且通过 mainloop() 使其能在非 Tk 环境下流畅渲染且不卡死。
    is_standalone_tk = False
    current_root = None
    try:
        current_root = tk._default_root
    except Exception:
        pass

    if parent is None and current_root is None:
        main_root = tk.Tk()
        main_root.withdraw() # 隐藏最丑陋的空白主窗口！
        win = tk.Toplevel(main_root)
        is_standalone_tk = True
    else:
        win = tk.Toplevel(parent or current_root)
    win.title(f"股票检查报告 - {code} {name}")
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
        if is_standalone_tk:
            try:
                main_root.destroy()
            except Exception:
                pass
    win.protocol("WM_DELETE_WINDOW", on_close_report)
    
    # [FIX] ESC 关闭报告
    win.bind("<Escape>", lambda e: on_close_report())
    win.lift()
    win.focus_force()
    # 结果显示区域
    tk.Label(win, text="[ 检查结果摘要 ]", font=("微软雅黑", 10, "bold"), bg=bg_color).pack(anchor="w", padx=10, pady=5)
    st = scrolledtext.ScrolledText(win, wrap=tk.WORD, height=15)
    st.pack(fill="both", expand=True, padx=10, pady=5)
    st.insert(tk.END, summary_text)
    st.config(state=tk.DISABLED)
    def show_all_details():
        """显示所有字段的值 (按顺序 col: 值)"""
        details_win = tk.Toplevel(win)
        details_win.title(f"数据详情内容 - {code} {name}")
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
        
        # [FIX] ESC 关闭详情
        details_win.bind("<Escape>", lambda e: on_close_details())
        details_win.lift()
        details_win.focus_force()
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
        search_entry.focus_set()
    # 按钮栏
    # 按钮栏布局重构：增加历史选择与手动测试
    btn_frame = tk.Frame(win, bg=bg_color)
    btn_frame.pack(fill="x", pady=10, side="bottom") # 显式设置在底部
    
    # [NEW] 优先 pack 左右两端的固定按钮，确保它们可见
    btn_close = tk.Button(btn_frame, text="关闭窗口", command=on_close_report)
    btn_close.pack(side="right", padx=20)

    btn_details = tk.Button(btn_frame, text="显示详情", command=show_all_details, 
                            bg="#2196F3", fg="white", font=("微软雅黑", 9, "bold"))
    btn_details.pack(side="left", padx=20)

    # 2. 中间交互区域 (历史驱动 + 手动输入)
    manual_frame = tk.Frame(btn_frame, bg=bg_color)
    manual_frame.pack(side="left", fill="x", expand=True)

    tk.Label(manual_frame, text="历史:", bg=bg_color).pack(side="left")
    
    # 构建历史选项列表
    history_options = []
    _queries_list = queries if isinstance(queries, list) else [queries]
    for i, q in enumerate(_queries_list):
        if isinstance(q, dict):
            q_name = q.get("name") or q.get("expr", "")[:15]
            history_options.append(f"H{i+1}: {q_name}")
        elif isinstance(q, str):
            history_options.append(f"H{i+1}: {q[:15]}")
    
    if not history_options:
        history_options = ["(无历史查询)"]
    
    # 使用 tk.OptionMenu 替代 ttk.Combobox 提升稳定性
    selected_hist = tk.StringVar(manual_frame)
    selected_hist.set("选择历史...")
    
    def on_history_change(*args):
        val = selected_hist.get()
        if ":" in val:
            try:
                idx = int(val.split(":")[0][1:]) - 1
                expr = _queries_list[idx]
                if isinstance(expr, dict): expr = expr.get("expr", "")
                manual_expr_var.set(expr)
                run_manual_test(expr)
            except: pass

    opt_menu = tk.OptionMenu(manual_frame, selected_hist, *history_options, command=on_history_change)
    opt_menu.config(width=12)
    opt_menu.pack(side="left", padx=5)

    tk.Label(manual_frame, text="手动测试:", bg=bg_color).pack(side="left", padx=(10, 0))
    manual_expr_var = tk.StringVar()
    manual_entry = tk.Entry(manual_frame, textvariable=manual_expr_var)
    manual_entry.pack(side="left", fill="x", expand=True, padx=5)

    def run_manual_test(expr=None):
        """执行手动测试逻辑并追加到报告"""
        target_expr = expr or manual_expr_var.get().strip()
        if not target_expr or target_expr == "选择历史...": return
        
        # 实时评估
        res = test_code_query(df_code, [{"expr": target_expr}])
        summary = format_check_result(res)
        
        # 解锁 ScrolledText 并追加内容
        st.config(state=tk.NORMAL)
        st.insert(tk.END, f"\n{'='*20} 手动测试: {datetime.now().strftime('%H:%M:%S')} {'='*20}\n")
        st.insert(tk.END, summary)
        st.see(tk.END) # 自动滚动到底部
        st.config(state=tk.DISABLED)

    # 绑定回车事件
    manual_entry.bind("<Return>", lambda e: run_manual_test())

    btn_test = tk.Button(manual_frame, text="执行测试", command=run_manual_test, 
                         bg="#4CAF50", fg="white", font=("微软雅黑", 8, "bold"))
    btn_test.pack(side="left", padx=5)

    try:
        win.update_idletasks()
        win.update()
    except Exception as e:
        pass

    if is_standalone_tk:
        try:
            main_root.mainloop()
        except Exception:
            pass

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
    """短暂提示信息（浮层，不阻塞，线程安全）"""
    if master is None:
        return

    def _safe_toast():
        try:
            # 确认 master 是否还健在
            if hasattr(master, 'winfo_exists') and not master.winfo_exists():
                return
        except Exception:
            return

        try:
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
            
            try:
                toast.update_idletasks()
                toast_w = toast.winfo_width()
                toast_h = toast.winfo_height()
                toast.geometry(f"{toast_w}x{toast_h}+{master_x + (master_w-toast_w)//2}+{master_y + 50}")
            except Exception:
                pass
            
            toast.after(duration, lambda: _safe_destroy(toast))
        except Exception as e:
            logger.debug(f"[toast_message] Tkinter layout exception: {e}")

    def _safe_destroy(widget):
        try:
            if widget and widget.winfo_exists():
                widget.destroy()
        except Exception:
            pass

    try:
        master.after(0, _safe_toast)
    except Exception as e:
        logger.debug(f"[toast_message] Failed to schedule toast via after: {e}")


class RealtimeSignalManager:
    def __init__(self) -> None:
        # [FIX] 增加线程锁，确保跨线程计算信号时的状态一致性，防止 GIL 冲突
        self._lock = threading.Lock()
        self.vol_cols = ['vol_h0', 'vol_h1', 'vol_h2', 'vol_h3', 'vol_h4']
        # 统一使用按周期 (resample) 隔离的 state_df
        self._state_dfs = {}
        self._cached_data = {}

        # 兼容旧代码直接访问 self.state_df，默认指向日线 'd'
        self._state_dfs['d'] = pd.DataFrame(columns=[
            'prev_now', 'today_high', 'today_low', 'prev_signal', 'down_streak',
            'vol_h0', 'vol_h1', 'vol_h2', 'vol_h3', 'vol_h4', 'vol_ptr'
        ])
        
    @property
    def state_df(self):
        # 兼容旧属性访问，指向日线状态
        return self._state_dfs.setdefault('d', pd.DataFrame(columns=[
            'prev_now', 'today_high', 'today_low', 'prev_signal', 'down_streak',
            'vol_h0', 'vol_h1', 'vol_h2', 'vol_h3', 'vol_h4', 'vol_ptr'
        ]))

    @state_df.setter
    def state_df(self, value):
        self._state_dfs['d'] = value

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

        # 提取当前周期 resample 标识，默认为 'd'
        resample = 'd'
        if 'resample' in df.columns and len(df) > 0:
            resample = str(df['resample'].iloc[0]).strip()

        cache = self._cached_data.setdefault(resample, {
            'last_hash': None,
            'cached_signal_strength': None,
            'cached_signal': None
        })

        try:
            current_hash = hash(tuple(df[price_col].values)) ^ hash(tuple(df['volume'].values))
            if cache['last_hash'] == current_hash and cache['cached_signal'] is not None and len(cache['cached_signal']) == len(df):
                df['signal_strength'] = cache['cached_signal_strength']
                df['signal'] = cache['cached_signal']
                return df
            cache['last_hash'] = current_hash
        except Exception:
            pass

        codes = df.index
        
        with self._lock:
            # 提取或初始化当前周期的 state_df
            state_df = self._state_dfs.get(resample)
            if state_df is None:
                state_df = pd.DataFrame(columns=[
                    'prev_now', 'today_high', 'today_low', 'prev_signal', 'down_streak',
                    'vol_h0', 'vol_h1', 'vol_h2', 'vol_h3', 'vol_h4', 'vol_ptr'
                ])
                self._state_dfs[resample] = state_df

            # 快速更新 state_df，补齐缺失的股票
            missing_codes = codes.difference(state_df.index)
            if not missing_codes.empty:
                new_states = pd.DataFrame({
                    'prev_now': df.loc[missing_codes, price_col],
                    'today_high': df.loc[missing_codes, 'high'],
                    'today_low': df.loc[missing_codes, 'low'],
                    'prev_signal': None,
                    'down_streak': 0,
                    'vol_h0': df.loc[missing_codes, 'volume'],
                    'vol_h1': np.nan,
                    'vol_h2': np.nan,
                    'vol_h3': np.nan,
                    'vol_h4': np.nan,
                    'vol_ptr': 1
                }, index=missing_codes)
                state_df = pd.concat([state_df, new_states])
                self._state_dfs[resample] = state_df
    
            # 提取历史状态数据
            state = state_df.loc[codes]
            # 提取成交量历史并计算均值
            avg_vol_arr = np.nanmean(state[self.vol_cols].values.astype(float), axis=1)
        
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
        
        signal_col = np.full(len(df), '', dtype=object)
        signal_col[score >= 9] = 'BUY_S'
        signal_col[(score >= 6) & (score < 9)] = 'BUY_N'
        signal_col[(score < 6) & (macd < 0)] = 'SELL_WEAK'

        sell_cond = ((macddif < macddea) & (macd < 0)) | ((rsi < 45) & (kdj_j < kdj_k)) | \
                    ((now_arr < ma51d) & (macdlast1 < macdlast2)) | intraday_low_break
        signal_col[sell_cond] = 'SELL'
        
        df['signal'] = signal_col
        cache['cached_signal_strength'] = score.copy()
        cache['cached_signal'] = signal_col.copy()

        # ⚡ 批量同步回 state_df
        with self._lock:
            state_df.loc[codes, 'prev_now'] = now_arr
            state_df.loc[codes, 'today_high'] = updated_today_high
            state_df.loc[codes, 'today_low'] = updated_today_low
            state_df.loc[codes, 'down_streak'] = updated_down_streak
            state_df.loc[codes, 'prev_signal'] = signal_col
            
            # 处理成交量历史 (完全向量化)
            ptrs = state_df.loc[codes, 'vol_ptr'].values.astype(int) % 5
            for i in range(5):
                mask = (ptrs == i)
                if mask.any():
                    state_df.loc[codes[mask], f'vol_h{i}'] = volume_arr[mask]
            
            state_df.loc[codes, 'vol_ptr'] += 1
            
            self._state_dfs[resample] = state_df

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

    # 🌟 强行进行防身独立拷贝，阻断并发对全局共享内存的原位修改，彻底根治 Access Violation 闪退
    df = df.copy()

    if "code" not in df.columns:
        df["code"] = df.index.astype(str).str.zfill(6)

    # 这里的 df 已经是一个安全的本地拷贝副本，可以安全地在底层进行各种属性与信号填充
    df = signal_manager.update_signals(df)

    df["emotion"] = "中性"
    df.loc[df.get("volume", 0) > 1.2, "emotion"] = "乐观"
    df.loc[df.get("volume", 0) < 0.8, "emotion"] = "悲观"
    return df

def calc_platform_breakout(df: pd.DataFrame, lookback: int = 120) -> pd.DataFrame:
    """
    基于日K线数据计算平台突破（Platform Breakout）形态。
    
    核心设计与逻辑：
    1. 【确定历史平台顶底】：在历史 lookback 天内寻找价格相近（在 ±3% 容忍度内）的两个局部极值点（收盘价）。
       - 平台顶（ptop）：基于局部高点（Peak），寻找两两差距在 3% 以内的最高一对，将其均值作为阻力，以最高收盘价为兜底。
       - 平台底（pbottom）：基于局部低点（Valley），寻找两两差距在 3% 以内的次低点，以最低收盘价为兜底。
       - 无未来函数：阻力与支撑仅基于当前日期 $t$ 前的数据计算，完全消除未来泄露。
    2. 【右侧有效突破】：当日内最高价突破平台顶（high > platform_top * 1.01），且前一日收盘在平台阻力下方时，触发突破信号。
    3. 【持续趋势跟踪与破位】：一旦突破成立，持续累加 `pdays`。只要最低价守住平台支撑（low > platform_top * 0.97）且在 MA20 上方，持续有效。
    """
    if df is None or len(df) < lookback:
        df = df.copy() if df is not None else pd.DataFrame()
        df['ptop'] = np.nan
        df['pbottom'] = np.nan
        df['pbreak'] = 0
        df['pdays'] = 0
        return df

    df = df.copy()
    # 统一进行小写与标准字段映射，保证绝对健壮性
    mapping = {'vol': 'volume', 'Vol': 'volume', 'amount': 'amount', 'Amount': 'amount'}
    df = df.rename(columns=mapping)
    df.columns = [c.lower() for c in df.columns]
    
    n = len(df)
    
    # 确保基础指标存在，优先直接引用 ma5d 和 ma20d，避免中转
    if 'ma5d' in df.columns:
        ma5_series = df['ma5d']
    else:
        ma5_series = df['close'].rolling(5).mean()

    if 'ma20d' in df.columns:
        ma20_series = df['ma20d']
    else:
        ma20_series = df['close'].rolling(20).mean()
        
    vol_ma5 = df['volume'].rolling(5).mean().fillna(df['volume'])
    
    # 提取底层 NumPy 数组，彻底摆脱 Pandas 对象的循环内开销
    high_arr = df['high'].values
    low_arr = df['low'].values
    close_arr = df['close'].values
    volume_arr = df['volume'].values
    vol_ma5_arr = vol_ma5.values
    ma20_arr = ma20_series.values
    
    platform_tops = [np.nan] * n
    platform_bottoms = [np.nan] * n  # 💥 新增 platform_bottoms 容器
    breakouts = [0] * n
    trend_days = [0] * n
    
    active_breakout_top = None
    active_trend_count = 0
    
    # 寻找局部高点（11天中心最大值，使用收盘价确定平台以过滤冲高试盘噪声）
    is_local_max = (df['close'] == df['close'].rolling(11, center=True, min_periods=1).max())
    is_local_max_arr = is_local_max.values
    
    # 1. 向量化预计算所有区间的全局最高收盘价以消除循环内 rolling.max() 开销
    highest_high_series = df['close'].rolling(lookback - 3, min_periods=1).max().shift(4)
    highest_high_arr = highest_high_series.values
    
    # 2. 向量化提取所有局部高点的索引，利用 np.searchsorted 在 O(log P) 时间内快速切片
    peak_indices = np.where(is_local_max_arr)[0]
    
    # 寻找局部低点（11天中心最小值，使用收盘价确定平台底中枢）
    is_local_min = (df['close'] == df['close'].rolling(11, center=True, min_periods=1).min())
    is_local_min_arr = is_local_min.values
    
    # 1. 向量化预计算所有区间的全局最低收盘价以消除循环内 rolling.min() 开销
    lowest_low_series = df['close'].rolling(lookback - 3, min_periods=1).min().shift(4)
    lowest_low_arr = lowest_low_series.values
    
    # 2. 向量化提取所有局部低点的索引
    valley_indices = np.where(is_local_min_arr)[0]
    
    # 3. 极速 NumPy 局部主循环
    for idx in range(lookback, n):
        # 确定历史平台阻力位的索引区间 [start_idx, end_idx)
        start_idx = idx - lookback
        if start_idx < 0:
            start_idx = 0
        end_idx = idx - 3
        if end_idx <= start_idx:
            end_idx = start_idx + 1
            
        # ==================== 平台顶计算 (Platform Top) ====================
        left_idx = np.searchsorted(peak_indices, start_idx, side='left')
        right_idx = np.searchsorted(peak_indices, end_idx, side='left')
        
        peak_prices = close_arr[peak_indices[left_idx:right_idx]]
        highest_high = highest_high_arr[idx]
        
        if len(peak_prices) > 0 and not np.isnan(highest_high):
            peak_prices = peak_prices[peak_prices >= highest_high * 0.7]
            
        platform_top = np.nan
        if len(peak_prices) >= 2:
            sorted_peaks = np.sort(peak_prices)[::-1]
            found_pair = False
            for i in range(len(sorted_peaks) - 1):
                p1 = sorted_peaks[i]
                p2 = sorted_peaks[i+1]
                if p2 > 0 and (p1 - p2) / p2 <= 0.03:
                    platform_top = (p1 + p2) / 2.0
                    found_pair = True
                    break
            
            if not found_pair:
                platform_top = highest_high
        else:
            platform_top = highest_high
            
        platform_tops[idx] = platform_top
        
        # ==================== 平台底计算 (Platform Bottom / 次低点) ====================
        left_val_idx = np.searchsorted(valley_indices, start_idx, side='left')
        right_val_idx = np.searchsorted(valley_indices, end_idx, side='left')
        
        valley_prices = close_arr[valley_indices[left_val_idx:right_val_idx]]
        lowest_low = lowest_low_arr[idx]
        
        if len(valley_prices) > 0 and not np.isnan(lowest_low):
            valley_prices = valley_prices[valley_prices <= lowest_low * 1.3]
            
        platform_bottom = np.nan
        if len(valley_prices) >= 2:
            sorted_valleys = np.sort(valley_prices)
            found_pair = False
            for i in range(len(sorted_valleys) - 1):
                p1 = sorted_valleys[i]
                p2 = sorted_valleys[i+1]
                if p1 > 0 and (p2 - p1) / p1 <= 0.03:
                    platform_bottom = p2
                    found_pair = True
                    break
            
            if not found_pair:
                platform_bottom = sorted_valleys[1]
        else:
            platform_bottom = lowest_low
            
        platform_bottoms[idx] = platform_bottom
        
        # ==================== 突破判定与主升跟踪 ====================
        if np.isnan(platform_top):
            continue
            
        close_curr = close_arr[idx]
        close_prev = close_arr[idx - 1]
        high_curr = high_arr[idx]
        low_curr = low_arr[idx]
        vol_curr = volume_arr[idx]
        vol_ma5_curr = vol_ma5_arr[idx]
        ma20_curr = ma20_arr[idx]
        
        is_break = (high_curr > platform_top * 1.01) and (close_prev <= platform_top * 1.01)
        
        if is_break:
            breakouts[idx] = 1
            if active_breakout_top is None:
                active_trend_count = 1
            else:
                active_trend_count += 1
            active_breakout_top = platform_top
            trend_days[idx] = active_trend_count
            logger.debug(f"🚀 [Platform Breakout] {df['code'].iloc[idx] if 'code' in df.columns else ''} "
                        f"breakout (High: {high_curr:.2f}) above close platform {platform_top:.2f}")
        elif active_breakout_top is not None:
            if low_curr > active_breakout_top * 0.97 and low_curr > ma20_curr:
                active_trend_count += 1
                trend_days[idx] = active_trend_count
                breakouts[idx] = 1
            else:
                active_breakout_top = None
                active_trend_count = 0
                
    df['ptop'] = platform_tops
    df['pbottom'] = platform_bottoms
    df['pbreak'] = breakouts
    df['pdays'] = trend_days
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
