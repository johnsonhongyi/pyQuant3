
import sys
import os
import argparse
import pandas as pd
import numpy as np
from datetime import datetime
import concurrent.futures
import time
import tkinter as tk
from tkinter import ttk, scrolledtext
import json

# 强制 UTF-8 输出，解决 Windows 终端乱码
if __name__ == "__main__" and sys.platform.startswith('win'):
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 自动处理路径
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(BASE_DIR)
sys.path.append(os.path.join(BASE_DIR, 'JSONData'))

try:
    from JohnsonUtil import commonTips as cct
except ImportError:
    cct = None

# [🚀 UI IMPORTS]
try:
    from tk_gui_modules.window_mixin import WindowMixin
    from tk_gui_modules.gui_config import WINDOW_CONFIG_FILE
except ImportError:
    class WindowMixin: 
        def load_window_position(self, *args, **kwargs): return (args[2], args[3], None, None)
        def save_window_position(self, *args, **kwargs): pass
    WINDOW_CONFIG_FILE = "window_config.json"

try:
    from JSONData.tdx_data_Day import get_tdx_Exp_day_to_df
    # 引入性能监控工具
    from JohnsonUtil.commonTips import timed_ctx, print_timing_summary
except ImportError:
    # 失败则提供一个空的 mock 以防崩溃
    class timed_ctx:
        def __init__(self, name): self.name = name
        def __enter__(self): return self
        def __exit__(self, *args): pass
    def print_timing_summary(): pass

INDEX_MAP = {'60': '999999', '68': '000688', '00': '399001', '30': '399006'}
NAME_CACHE = {}
INDEX_DATA_CACHE = {} # [🚀 全局加速缓存]
DNA_CALC_CACHE = {}   # [🚀 DNA计算缓存：(code, start, end) -> (summary, ts)]

# [🚀 THREAD SAFETY] 为全局缓存引入锁，解决多线程审计时的 GIL/Race 冲突
import threading
CACHE_LOCK = threading.Lock()

def get_corresponding_index(code):
    # 🚀 [FIX] 对齐全市场指数映射：30开头(创业板)应使用 399006，8/9开头(北交所)使用 899050
    if code.startswith('30'): return "399006"
    if code.startswith(('00', '39')): return "399001"
    if code.startswith(('8', '9')): return "899050" 
    if code.startswith('6'): return "999999"
    return INDEX_MAP.get(code[:2], '999999')

# [🚀 PROGRESS SUPPORT] 定义进度回调协议
# progress_callback(current: int, total: int, msg: str)

def preheat_names(codes):
    """[🚀 极致优化] 批量预热股票名称，消除循环内频繁打开 HDF5 的灾难级 IO"""
    with CACHE_LOCK:
        missing_codes = [c for c in codes if c not in NAME_CACHE]
    if not missing_codes: return
        
    # 默认内置一些核心标的
    meta_names = {'002990': '盛视科技', '603698': '航天工程', '300058': '蓝色光标'}
    for c, n in meta_names.items():
        if c in missing_codes:
            with CACHE_LOCK:
                NAME_CACHE[c] = n
    
    with CACHE_LOCK:
        missing_codes = [c for c in codes if c not in NAME_CACHE]
    if not missing_codes: return
    
    try:
        import glob
        h5_files = glob.glob("g:/shared_df_all-*.h5")
        if h5_files:
            latest_h5 = sorted(h5_files)[-1]
            with pd.HDFStore(latest_h5, mode='r') as store:
                target_key = None
                if '/df' in store.keys(): target_key = '/df'
                elif '/all' in store.keys(): target_key = '/all'
                
                if target_key:
                    codes_str = [str(c) for c in missing_codes]
                    df_names = store.select(target_key, columns=['name'], where="index in codes_str")
                    if not df_names.empty:
                        with CACHE_LOCK:
                            for code, row in df_names.iterrows():
                                NAME_CACHE[str(code).zfill(6)] = row.get('name', str(code))
    except Exception as e:
        # print(f"DEBUG: Name Preheat failed: {e}")
        pass
        
    # 补齐未找到的
    with CACHE_LOCK:
        for c in codes:
            if c not in NAME_CACHE: NAME_CACHE[c] = c

def calculate_dna_indicators(df):
    if df is None or len(df) < 20: return None
    df['pct'] = df['close'].pct_change() * 100
    df['ma8'] = df['close'].rolling(8).mean()
    df['ma10'] = df['close'].rolling(10).mean()
    df['ma20'] = df['close'].rolling(20).mean()
    df['ma10_vol'] = df['vol'].rolling(10).mean()
    std = df['close'].rolling(20).std()
    df['upper'] = df['ma20'] + 2 * std
    df['high4'] = df['high'].rolling(4).max().shift(1)
    df['c_upper'] = df['close'] / df['upper']
    df['c_h4'] = df['close'] / df['high4']
    df['c_ma8'] = df['close'] / df['ma8']
    df['c_ma20'] = df['close'] / df['ma20']
    df['v_ratio'] = df['vol'] / df['ma10_vol']
    df['is_bid_low'] = (df['open'] == df['low'])
    
    # [🚀 NEW] 探测大跌背景 (用于审计“地量筑底”)
    # 10日内股价相对于高点的回撤百分比
    h10 = df['high'].rolling(10).max()
    df['drop_10d'] = (df['close'] / h10 - 1) * 100
    
    # [🚀 NEW] 十字星识别 (变盘基因)
    # 实体极小：实体长度 / 开盘价 < 0.3%
    df['is_doji'] = (abs(df['open'] - df['close']) / df['open'] < 0.003)
    return df

class AuditSummary:
    def __init__(self, code, name):
        self.code, self.name = code, name
        self.alpha_sum, self.max_adhesion = 0, 0
        self.squeeze_days, self.divergence_days = 0, 0
        self.intent_score, self.verdict, self.total_pct = 0, "", 0
        self.anti_drop_count = 0  # 大盘跌他涨
        self.leverage_count = 0   # 大盘涨更涨
        self.shield_count = 0     # 大盘回调他微调
        self.dragon_squeeze_days = 0 # 龙息蓄势 (上轨突破后缩量回调)
        self.bottom_stable_days = 0  # 筑底企稳 (缩量回踩，支撑确认)
        self.extreme_shrink_count = 0 # 地量基因 (地量见底)
        self.pivot_signal_found = False # 变盘基因 (缩量十字星)
        self.suggestions = []
        self.history = []

    def finalize(self, rows):
        self.alpha_sum = sum(r['alpha'] for r in rows)
        p_close = rows[0]['prev_close']
        if p_close != 0:
            self.total_pct = (rows[-1]['close'] / p_close - 1) * 100
        else:
            self.total_pct = 0
        streak = 0
        for r in rows:
            if r['c_upper'] >= 1.0:
                streak += 1
                self.max_adhesion = max(self.max_adhesion, streak)
            else: streak = 0
            
            if r['v_ratio'] < 0.76 and abs(r['alpha']) < 1.0: self.squeeze_days += 1
            if r['pct'] > 0 and r['idx_pct'] < -0.3: self.divergence_days += 1
            
            # [💎 DNA 核心特征提炼]
            # 1. 大盘跌他涨 (逆势特征)
            if r['idx_pct'] < -0.5 and r['pct'] > 0: self.anti_drop_count += 1
            # 2. 大盘涨更涨 (进攻杠杆)
            if r['idx_pct'] > 0.5 and r['pct'] > r['idx_pct'] * 1.5: self.leverage_count += 1
            # 3. 大盘回调他微调 (抗跌韧性)
            if r['idx_pct'] < -1.0 and r['pct'] > r['idx_pct'] * 0.4 and r['pct'] < 0: self.shield_count += 1
            
            # 4. [🚀 龙息蓄势] 突破上轨后的缩量踩线 (关键预判)
            # 条件：最近有过强力贴轨，当前缩量(v_ratio<1)，且价格回踩 MA8/MA20 附近 (0.98~1.03)
            if self.max_adhesion >= 1 and r['v_ratio'] < 1.05 and 0.98 <= r['c_ma8'] <= 1.03:
                if abs(r['alpha']) < 2.0: self.dragon_squeeze_days += 1
            
            # 5. [🏗️ 筑底企稳] 连续下跌后的缩量平衡点 (转折点)
            # 条件：成交量萎缩(v_ratio<0.85)，回踩 MA20 强支撑(0.98~1.05)，且下跌速率放缓或相对抗跌
            if r['v_ratio'] < 0.85 and 0.98 <= r['c_ma20'] <= 1.05:
                if r['idx_pct'] < -0.3 and r['pct'] > r['idx_pct']: # 比大盘跌得少
                    self.bottom_stable_days += 1
            
            # 6. [🧊 地量见底] 
            # 逻辑：地量即惜售。特别强化“大跌后地量” (筑底结构)
            if r['v_ratio'] < 0.65:
                # 如果 10 日内跌幅 > 10% 且缩量，视为极佳的筑底基因
                if r.get('drop_10d', 0) < -10:
                    self.extreme_shrink_count += 2 # 加倍权重
                else:
                    self.extreme_shrink_count += 1
            
            # 7. [⚖️ 变盘结构] 缩量十字星 (Pivot Doji)
            if r.get('is_doji', False) and r['v_ratio'] < 0.75:
                # 标记找到过变盘基因
                self.pivot_signal_found = True
            
            self.history.append(r) 
        
        # [🚀 NEW] 变盘基因加权：如果“最后 2 日”出现缩量十字星，给予高额评估分
        recent_pivot = False
        for r in rows[-2:]:
             if r.get('is_doji', False) and r['v_ratio'] < 0.75:
                 recent_pivot = True
                 break

        self.intent_score = (self.alpha_sum * 0.4) + (self.max_adhesion * 5) + (self.squeeze_days * 3) + \
                            (self.anti_drop_count * 8) + (self.leverage_count * 5) + (self.shield_count * 6) + \
                            (self.dragon_squeeze_days * 10) + (self.bottom_stable_days * 8) + (self.extreme_shrink_count * 12) + \
                            (15 if recent_pivot else (5 if self.pivot_signal_found else 0))
        
        if recent_pivot:
            self.suggestions.append("- 探测到‘临界变盘’信号：尾盘出现缩量十字星，多空达到极度平衡，通常预示方向选择在即")
        
        if self.intent_score > 50 and (self.max_adhesion >= 3 or self.anti_drop_count >= 2 or self.dragon_squeeze_days >= 2):
            self.verdict = "💎 [金身种子] 核心主升"
            if self.dragon_squeeze_days >= 2:
                self.suggestions.append(f"- 探测到极高价值的‘龙息蓄势’基因({self.dragon_squeeze_days}天)，属于典型的强突破后缩量回踩 MA 企稳")
            else:
                self.suggestions.append("- 探测到极强独立进攻基因，在指数走弱时具备卓越的抗风险与上攻动力")
            self.suggestions.append(f"- 轨道接力稳固({self.max_adhesion}天)，表现出明显的‘大盘跌他涨’特征({self.anti_drop_count}天)")
        elif self.intent_score > 35 or (self.bottom_stable_days >= 3 and self.intent_score > 20):
            self.verdict = "🛡️ [筑底种子] 企稳待发"
            self.suggestions.append(f"- 探测到明显的‘筑底企稳’基因({self.bottom_stable_days}天)，股价在支撑位缩量平衡")
            if self.extreme_shrink_count >= 1:
                self.suggestions.append(f"- 伴随 {self.extreme_shrink_count} 天极度地量，主力惜售明显，反转预期极强")
            if self.shield_count >= 1: self.suggestions.append("- 回调期间表现出极强的韧性，属于‘给点阳光就灿烂’的品种")
        elif self.intent_score > 20:
            self.verdict = "🚀 [加速跑道] 意图确认"
            self.suggestions.append("- 正在脱离结构压力位，具备较好的‘补涨+领涨’混合属性")
            if self.leverage_count >= 2: self.suggestions.append(f"- 具备高度的进攻杠杆({self.leverage_count}天)，属于‘大盘涨更涨’的活跃品种")
        else:
            self.verdict = "⚠️ [诱多陷阱] 杂毛跟风"
            self.suggestions.append("- 缺乏独立基因，在指数回调时回撤过大，大概率属于被动跟风")

        if self.shield_count >= 1:
            self.suggestions.append(f"- 展现出‘大盘深度回调，个股韧性维持’的特征，具备较好的安全垫")
        
        if self.divergence_days >= 2 and self.anti_drop_count == 0:
             self.suggestions.append(f"- 存在 {self.divergence_days} 天抗跌背离，符合泥沙俱下中的种子特征")

def run_optimized_audit(code, start_date, end_date):
    # [🚀 CACHE CHECK] 极致性能：同一天 30 分钟内共用结果
    cache_key = (code, start_date, end_date)
    # [🚀 UI-SAFE] 极致优化：先尝试不加锁读取
    cached_val = DNA_CALC_CACHE.get(cache_key)
    if cached_val:
        summary, ts = cached_val
        
        # 判定是否需要重新刷新（逻辑分支移出锁外）
        is_trading = True
        if cct:
            try: is_trading = cct.get_work_time()
            except: pass
            
        if not is_trading:
            return summary
            
        if time.time() - ts < 1800:
            return summary

    # [🚀 EXTREME SPEED] 极速模式：不再进行微睡，全力压榨 IO 与 CPU

    with timed_ctx(f"Load & Audit {code}", warn_ms=10000):
        # 🛡️ [CACHE_CHECK] 再次校验缓存
        with CACHE_LOCK:
            if cache_key in DNA_CALC_CACHE:
                return DNA_CALC_CACHE[cache_key][0]

        # [🚀 LIGHTWEIGHT LOAD] 使用 fastohlc=True 跳过不使用的 MACD/OBV 等重型指标计算
        df_raw = get_tdx_Exp_day_to_df(code, dl=800, fastohlc=True)
        
        if df_raw is None or df_raw.empty: return None
        
        with CACHE_LOCK:
            name = NAME_CACHE.get(code, code)
        
        # 🚀 [PERF-OPTIMIZED] 移除 redundant .copy()，直接在原始 DataFrame 上计算，节省内存分配开销
        df = calculate_dna_indicators(df_raw)
        if df is None: return None
        
        idx_code = get_corresponding_index(code)
        
        # 尝试从缓存读取指数
        df_idx = INDEX_DATA_CACHE.get(idx_code)
        
        if df_idx is None:
            # 🚀 [FIX] 加载指数数据（完全脱离锁环境进行 IO）
            df_idx_raw = get_tdx_Exp_day_to_df(idx_code, dl=800, fastohlc=True)
            if df_idx_raw is not None and not df_idx_raw.empty:
                df_idx_raw['idx_pct'] = df_idx_raw['close'].pct_change() * 100
                with CACHE_LOCK:
                    INDEX_DATA_CACHE[idx_code] = df_idx_raw
                df_idx = df_idx_raw
        
        # 🚀 [FIX] 增强日期格式鲁棒性：支持 YYYYMMDD 和 YYYY-MM-DD
        def normalize_dt(d_str):
            if not d_str: return None
            s = str(d_str).strip().replace('-', '').replace('/', '')
            if len(s) == 8:
                return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
            return d_str
            
        s_dt = normalize_dt(start_date)
        e_dt = normalize_dt(end_date) if end_date else df.index[-1]
        
        # [🚀 OPTIMIZED] 使用整数位置避免 get_loc 的切片冲突
        date_mask = (df.index >= s_dt) & (df.index <= e_dt)
        locs = np.where(date_mask)[0]
        if len(locs) == 0: return None
        
        summary = AuditSummary(code, name)
        audit_rows = []
        
        for idx in locs:
            dt = df.index[idx]
            row = df.iloc[idx]
            
            # 获取 idx_pct，考虑指数缺失或 duplicates
            idx_p = 0
            if df_idx is not None and dt in df_idx.index:
                try:
                    idx_val = df_idx.loc[dt, 'idx_pct']
                    # 如果有重复日期，取第一个
                    idx_p = idx_val.iloc[0] if hasattr(idx_val, 'iloc') else idx_val
                except:
                    idx_p = 0
                if np.isnan(idx_p): idx_p = 0
                
            alpha = row['pct'] - idx_p
            
            # 获取上个交易日收盘价 (用于累计涨幅计算)
            prev_idx = idx - 1
            if prev_idx >= 0:
                prev_close = df.iloc[prev_idx]['close']
            else:
                # 处于 df 边界，通过 pct 反算
                p = row.get('pct', 0)
                prev_close = row['close'] / (1 + p/100.0) if p != -100 else row['close']

            audit_rows.append({
                'date': dt,
                'alpha': alpha, 
                'idx_pct': idx_p, 
                'pct': row['pct'], 
                'c_upper': row['c_upper'], 
                'c_ma8': row['c_ma8'],
                'c_ma20': row['c_ma20'],
                'v_ratio': row['v_ratio'], 
                'close': row['close'], 
                'prev_close': prev_close
            })
            
        summary.finalize(audit_rows)
        # 存入缓存
        with CACHE_LOCK:
            DNA_CALC_CACHE[cache_key] = (summary, time.time())
        return summary

def audit_multiple_codes(codes, start_date=None, end_date=None, code_to_name=None, progress_callback=None):
    """
    供外部调用的批量审计接口
    :param progress_callback: 进度回调函数 f(current, total, msg)
    """
    if not codes: return []
    
    if start_date is None:
        # 🚀 [FIX] 起点动态对齐截止日期前25天
        base_dt = datetime.now()
        if end_date:
            try:
                s = str(end_date).strip().replace('-', '').replace('/', '')
                if len(s) == 8: base_dt = datetime.strptime(s, "%Y%m%d")
            except: pass
        start_date = (base_dt - pd.Timedelta(days=25)).strftime("%Y%m%d")
    
    # 🚀 [Standardize] 全部代码标准化，避免 N/A 或 散兵代码 进入循环
    codes = [str(c).strip().zfill(6) for c in codes if c and str(c).strip().isdigit() and len(str(c).strip()) >= 5]
    if not codes: return []
    
    total = len(codes)
    if progress_callback:
        progress_callback(0, total, f"正在准备审计 {total} 只个股...")

    # [🚀 极速注入] 如果外部提供了名称对照表，直接存入内存缓存
    if code_to_name:
        with CACHE_LOCK:
            for c, n in code_to_name.items():
                NAME_CACHE[c] = n
            
    preheat_names(codes)
    summaries = []
    
    # [🚀 PERF] 统一预加载指数数据（修正：IO 必须在锁外）
    unique_indices = set(get_corresponding_index(c) for c in codes)
    for idx_code in unique_indices:
        if idx_code not in INDEX_DATA_CACHE:
            # 预读指数 (IO 在锁外执行)
            df_idx = get_tdx_Exp_day_to_df(idx_code, dl=800, fastohlc=True)
            if df_idx is not None and not df_idx.empty:
                df_idx['idx_pct'] = df_idx['close'].pct_change() * 100
                with CACHE_LOCK:
                    INDEX_DATA_CACHE[idx_code] = df_idx

    with timed_ctx("Batch Execution", warn_ms=10000):
        # 🚀 [UI-SAFE] 降低并发数至 2-3，极大缓解 GIL 竞争引发的 UI 粘滞感
        # 对于 IO 密集型任务，过高并发在 Windows+Python 环境下反而会导致主线程失去响应
        # 🚀 [PERF] 极速模式：强力开放 16 路并发，彻底消除 IO 等待瓶颈
        # max_workers = 16 if total > 5 else 1
        cpu_count = int(os.cpu_count()/2) + 2 or 4
        max_workers = min(cpu_count, cct.livestrategy_max_workers) if total > 5 else 1
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_code = {executor.submit(run_optimized_audit, code, start_date, end_date): code for code in codes}
            
            res_dict = {}
            count = 0
            for future in concurrent.futures.as_completed(future_to_code):
                c = future_to_code[future]
                count += 1
                try:
                    res_dict[c] = future.result()
                    if progress_callback and (count % 20 == 0 or count == total):
                        nm = NAME_CACHE.get(c, c)
                        progress_callback(count, total, f"已完成: {nm} ({count}/{total})")
                except Exception as e:
                    logger.error(f"Error auditing {c}: {e}")
                    res_dict[c] = None
            
            # 最终按照原始 codes 顺序装填 summaries
            for code in codes:
                s = res_dict.get(code)
                if s: summaries.append(s)
                    
    if progress_callback:
        progress_callback(total, total, "审计完成，正在生成报告...")
        
    return summaries

class DnaAuditReportWindow(tk.Toplevel, WindowMixin):
    def __init__(self, summaries, parent=None, end_date=None):
        tk.Toplevel.__init__(self, parent)
        self.withdraw()  # 🚀 [CRITICAL] 立即隐藏，配合 alpha=0 彻底杜绝初始化瞬间的默认小窗口
        self.attributes("-alpha", 0.0)
        
        self.summaries = summaries
        self.monitor_app = parent
        self.end_date = end_date
        
        # 🚀 [NEW] 核心逻辑：如果没有外部强制焦点，默认取审计列表第一个作为焦点
        self.focus_code = summaries[0].code if summaries else None
        
        self.window_name = "dna_audit_report_v2"
        self.scale_factor = getattr(parent, 'scale_factor', 1.0) if parent else 1.0
        
        title_suffix = f" (截止: {self.end_date})" if self.end_date else ""
        self.title(f"🧬 DNA 专项审计报告 (深度挖掘) - {len(summaries)}只{title_suffix}")
        
        self._setup_ui()
        
        # 加载位置与尺寸
        self.load_window_position(self, self.window_name, default_width=1000, default_height=750)
        
        # [NEW] 加载分割线位置 (延迟等待 UI 布局完成)
        self.after(200, self._load_sash_position)
        
        # 填充数据
        self._fill_data()
        
        # 绑定关闭保存
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        
        # 初始选中
        if self.tree.get_children():
            first = self.tree.get_children()[0]
            self.tree.selection_set(first)
            self.tree.focus(first)

        # 绑快捷键
        self.bind("<Escape>", lambda e: self.on_close())
        
        # 🚀 [INSTANT] 极速模式：缩短展示延迟，放弃渐变，直接呼出结果
        self.after(50, self._reveal_window)
        
        # 确保表格本身获得键盘焦点
        self.tree.focus_set() 

    def _reveal_window(self):
        """🚀 [NEW] 布局就绪后平滑展示，消除跳跃感"""
        # 强制绘制所有组件以确定最终几何尺寸
        self.update_idletasks()
        
        # 再次确认位置与尺寸 (在 deiconify 之前)
        self.load_window_position(self, self.window_name, default_width=1000, default_height=750)
        
        # 确保位置更新已送达桌面管理器
        self.update_idletasks()
        
        self.deiconify() # 直接显示窗口 (此时位置已修正)
        self.attributes("-alpha", 1.0)
        self.lift()
        self.focus_force()
        self.tree.focus_set()
        
        # 初始选中并滚动
        self._auto_scroll_to_focus()

    def _auto_scroll_to_focus(self):
        """🚀 [NEW] 自动滚动到指定的个股行"""
        found_item = None
        if self.focus_code:
            for item in self.tree.get_children():
                # 🚀 [FIX] 列名必须是定义的 ID 'code'，而不是显示文本 '代码'
                if self.tree.set(item, "code") == self.focus_code:
                    found_item = item
                    break
        
        if not found_item and self.tree.get_children():
            found_item = self.tree.get_children()[0]
            
        if found_item:
            self.tree.selection_set(found_item)
            self.tree.focus(found_item)
            self.tree.see(found_item)
            # 🚀 [FIX] 事件回调方法名应为 _show_detail
            self._show_detail(None)

    def _setup_ui(self):
        # 主容器
        self.paned = ttk.Panedwindow(self, orient=tk.VERTICAL)
        self.paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # 1. 顶部表格区域
        top_frame = tk.Frame(self.paned)
        self.paned.add(top_frame, weight=2)

        columns = ("code", "name", "score", "gain", "verdict")
        self.tree = ttk.Treeview(top_frame, columns=columns, show="headings")
        
        # 设置表头与排序
        headers = {"code": "代码", "name": "名称", "score": "DNA意图分", "gain": "波段涨幅%", "verdict": "极限判定"}
        for col, text in headers.items():
            self.tree.heading(col, text=text, command=lambda _c=col: self._sort_column(_c, False))
            self.tree.column(col, anchor=tk.CENTER, width=int(100 * self.scale_factor))
        
        self.tree.column("verdict", anchor=tk.W, width=int(300 * self.scale_factor))

        scroll_y = ttk.Scrollbar(top_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll_y.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)

        # 2. 底部详情区域
        bottom_frame = tk.Frame(self.paned)
        self.paned.add(bottom_frame, weight=3)
        
        self.txt_detail = scrolledtext.ScrolledText(bottom_frame, font=("微软雅黑", 10), wrap=tk.WORD, bg="#fdfdfd")
        self.txt_detail.pack(fill=tk.BOTH, expand=True)

        # 绑定事件
        self.tree.bind("<<TreeviewSelect>>", self._show_detail)
        self.tree.bind("<Double-1>", self._on_double_click)

    def _fill_data(self):
        # 初始按分数排序
        sorted_sums = sorted(self.summaries, key=lambda x: x.intent_score, reverse=True)
        for s in sorted_sums:
            self.tree.insert("", tk.END, values=(
                str(s.code).zfill(6),
                s.name,
                f"{s.intent_score:.1f}",
                f"{s.total_pct:.1f}",
                s.verdict
            ))
        # 自动调整列宽
        self._adjust_column_widths()

    def update_report(self, new_summaries, end_date=None):
        """[🚀 NEW] 动态更新报告内容，支持窗口复用"""
        if not new_summaries: return
        
        self.summaries = new_summaries
        if end_date: self.end_date = end_date
        
        # 1. 清空表格
        for item in self.tree.get_children():
            self.tree.delete(item)
            
        # 2. 重新填充数据
        self._fill_data()
        
        # 3. 更新标题
        title_suffix = f" (截止: {self.end_date})" if self.end_date else ""
        self.title(f"🧬 DNA 专项审计报告 (深度挖掘) - {len(self.summaries)}只{title_suffix}")
        
        # 4. 激活并置顶
        self.deiconify()
        self.lift()
        self.attributes("-topmost", True)
        self.after(500, lambda: self.attributes("-topmost", False))
        self.focus_force()
        
        # 5. 初始选中第一行并显示详情
        if self.tree.get_children():
            first = self.tree.get_children()[0]
            self.tree.selection_set(first)
            self.tree.focus(first)
            self._show_detail(None)

    def _adjust_column_widths(self):
        import tkinter.font as tkfont
        # ttk.Treeview 不支持直接 cget('font')，使用基础 Font 对象进行像素测量
        f = tkfont.Font() 
        for col in self.tree["columns"]:
            # 标题宽度
            header_text = self.tree.heading(col, "text")
            max_w = f.measure(header_text) + 20
            # 内容宽度 (前100行采样)
            for item in self.tree.get_children()[:100]:
                val = str(self.tree.set(item, col))
                w = f.measure(val) + 20
                if w > max_w: max_w = w
            
            # 设置限额
            if col == "verdict": max_w = min(max_w, int(500 * self.scale_factor))
            self.tree.column(col, width=max_w)

    def _sort_column(self, col, reverse):
        """🚀 [UPGRADE] 支持数值、百分比与普通字符串的智能排序"""
        items = self.tree.get_children('')
        
        def try_parse_numeric(val):
            # 处理百分比符号或多余字符
            clean_s = str(val).replace('%', '').strip()
            try:
                return float(clean_s)
            except ValueError:
                return str(val).lower()

        data = [(try_parse_numeric(self.tree.set(k, col)), k) for k in items]
        data.sort(key=lambda t: t[0], reverse=reverse)

        for index, (val, k) in enumerate(data):
            self.tree.move(k, '', index)

        # 🚀 [FIX] 更新表头点击事件，确保 toggle 排序方向
        self.tree.heading(col, command=lambda _c=col: self._sort_column(_c, not reverse))

    def _show_detail(self, event):
        sel = self.tree.selection()
        if not sel: return
        vals = self.tree.item(sel[0])['values']
        code = str(vals[0]).zfill(6)
        
        # [🚀 LINKAGE] 单击同步联动 TDX 与可视化终端
        if self.monitor_app and hasattr(self.monitor_app, 'on_code_click'):
            self.monitor_app.on_code_click(code, date=self.end_date)
            
        target_s = next((x for x in self.summaries if str(x.code).zfill(6) == code), None)
        if target_s:
            self.txt_detail.delete('1.0', tk.END)
            self.txt_detail.insert(tk.END, f"【基因解剖】 {target_s.name} ({target_s.code})\n", "title")
            self.txt_detail.insert(tk.END, f"意图评分: {target_s.intent_score:.1f} 分\n")
            self.txt_detail.insert(tk.END, f"极限判定: {target_s.verdict}\n")
            self.txt_detail.insert(tk.END, f"波段涨幅: {target_s.total_pct:.1f} %\n")
            self.txt_detail.insert(tk.END, "-"*60 + "\n[ 审计专家洞察 ]\n")
            for sug in target_s.suggestions:
                self.txt_detail.insert(tk.END, f"● {sug}\n")
            
            # [🚀 NEW] 指标演进提炼表格
            self.txt_detail.insert(tk.END, "\n[ 指标演进提炼 (Indicator Evolution) ]\n", "title_small")
            header = f"{'日期':<12} {'Alpha':>8} {'涨幅%':>8} {'指数%':>8} {'Bol-U':>8} {'量比':>8}\n"
            self.txt_detail.insert(tk.END, header, "header")
            for h in target_s.history[-15:]: # 显示最近 15 天
                row_str = f"{h['date']:<12} {h['alpha']:>8.2f} {h['pct']:>8.2f} {h['idx_pct']:>8.2f} {h['c_upper']:>8.2f} {h['v_ratio']:>8.2f}\n"
                self.txt_detail.insert(tk.END, row_str, "row")
                
            self.txt_detail.insert(tk.END, "\n" + "="*48 + "\n")
            
            # 设置简单的富文本样式
            self.txt_detail.tag_configure("title", font=("微软雅黑", 12, "bold"), foreground="#2c3e50")
            self.txt_detail.tag_configure("title_small", font=("微软雅黑", 10, "bold"), foreground="#34495e")
            self.txt_detail.tag_configure("header", font=("Consolas", 9, "bold"), foreground="#7f8c8d")
            self.txt_detail.tag_configure("row", font=("Consolas", 9), foreground="#2c3e50")

    def _on_double_click(self, event):
        sel = self.tree.selection()
        if not sel: return
        code = self.tree.item(sel[0])['values'][0]
        if self.monitor_app and hasattr(self.monitor_app, 'on_code_click'):
            # 联动主程序查看 K 线
            self.monitor_app.on_code_click(str(code).zfill(6))

    def _load_sash_position(self):
        """加载分割线位置 (按比例恢复，更健壮)"""
        try:
            # 确保 UI 布局已完成以获取准确高度
            self.update_idletasks()
            scale = self.scale_factor
            config_file = self._get_config_file_path(WINDOW_CONFIG_FILE, scale)
            
            if os.path.exists(config_file):
                with open(config_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if self.window_name in data:
                    pos = data[self.window_name]
                    
                    win_height = self.paned.winfo_height()
                    if win_height < 50: # 如果还没加载好，稍微等一下
                        self.after(100, self._load_sash_position)
                        return

                    # 优先使用比例恢复，兼容性更好
                    if "sash_ratio" in pos:
                        ratio = max(0.2, min(0.8, float(pos["sash_ratio"])))
                        self.paned.sashpos(0, int(win_height * ratio))
                    elif "sash_pos" in pos:
                        # 兼容旧版本绝对坐标
                        real_sash_pos = int(pos["sash_pos"] * scale)
                        min_y, max_y = int(win_height * 0.2), int(win_height * 0.8)
                        real_sash_pos = max(min_y, min(max_y, real_sash_pos))
                        self.paned.sashpos(0, real_sash_pos)
        except Exception:
            pass

    def _save_sash_position(self):
        """保存分割线位置 (按比例保存)"""
        try:
            scale = self.scale_factor
            config_file = self._get_config_file_path(WINDOW_CONFIG_FILE, scale)
            
            win_height = self.paned.winfo_height()
            if win_height < 100: return # 窗口太小时不保存，防止存入极值
            
            sash_pos = self.paned.sashpos(0)
            ratio = sash_pos / win_height
            
            data = {}
            if os.path.exists(config_file):
                with open(config_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
            
            if self.window_name not in data:
                data[self.window_name] = {}
            
            # 同时保存比例（新）和绝对值（旧），确保最大兼容性
            data[self.window_name]["sash_ratio"] = round(ratio, 3)
            data[self.window_name]["sash_pos"] = int(sash_pos / scale)
            
            with open(config_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def on_close(self):
        # 先保存基础坐标和尺寸，再追加分割线坐标（防止被 save_window_position 覆盖）
        self.save_window_position(self, self.window_name)
        self._save_sash_position()
        self.destroy()

def show_dna_audit_report_window(summaries, parent=None, end_date=None):
    if not summaries:
        from tkinter import messagebox
        messagebox.showinfo("DNA 审计", "没有产生足够的历史数据，或没有命中任何结论。", parent=parent)
        return
    
    # 使用新定义的类
    return DnaAuditReportWindow(summaries, parent=parent, end_date=end_date)

def main():
    parser = argparse.ArgumentParser(description="DNA 审计专家 v9.8 [Alpha Backtest Edition]")
    parser.add_argument("-c", "--code", type=str, help="指定股票代码，用逗号分隔 (如 000001,600000)")
    parser.add_argument("-n", "--top_n", type=int, help="自动从最新共享池中提取 Top N 个股进行批量审计")
    parser.add_argument("-f", "--follow", action="store_true", help="自动提取当前具有 'signal' 信号的个股进行审计")
    parser.add_argument("-m", "--mine", action="store_true", help="全盘挖掘全盘挖掘模式：扫描全市场寻找具备‘龙息蓄势’或‘金身种子’特征的潜伏个股")
    parser.add_argument("-v", "--verbose", action="store_true", help="输出详细的每日指标演进提炼报告")
    parser.add_argument("-s", "--start", type=str, help="审计起始日期 (YYYYMMDD), 默认最近25天")
    parser.add_argument("-e", "--end", type=str, help="审计结束日期 (YYYYMMDD)")
    args = parser.parse_args()
    
    codes = []
    code_to_name = {}
    
    with timed_ctx("Total Execution"):
        # 1. 确定代码来源
        if args.code:
            codes = [c.strip().zfill(6) for c in args.code.split(',')]
        elif args.top_n or args.follow or args.mine:
            # 从 HDF5 动态加载
            import glob
            h5_files = glob.glob("g:/shared_df_all-*.h5")
            if h5_files:
                latest_h5 = sorted(h5_files)[-1]
                print(f"[*] 正在从最新池加载数据: {os.path.basename(latest_h5)}")
                try:
                    with pd.HDFStore(latest_h5, mode='r') as store:
                        key = store.keys()[0]
                        df_all = store.select(key)
                        
                        if args.follow:
                            # 过滤有信号的
                            if 'signal' in df_all.columns:
                                df_all['signal'] = df_all['signal'].fillna('')
                                df_follow = df_all[df_all['signal'].str.len() > 0]
                                if df_follow.empty and 'trade_signal' in df_all.columns:
                                    df_all['trade_signal'] = df_all['trade_signal'].fillna('')
                                    df_follow = df_all[df_all['trade_signal'].str.len() > 0]
                            else:
                                df_follow = pd.DataFrame()
                                
                            if not df_follow.empty:
                                # 只取涨幅前 50，避免全市场审计导致慢死
                                df_follow = df_follow.sort_values(by='percent', ascending=False).head(50)
                                codes = df_follow.index.tolist()
                                if 'name' in df_follow.columns:
                                    code_to_name = df_follow['name'].to_dict()
                            print(f"[*] 发现 {len(codes)} 只带信号个股 (已取 Top 50)")
                        
                        if args.mine and not codes:
                            # [全盘挖掘] 扫描全市场
                            codes = df_all.index.tolist()
                            if 'name' in df_all.columns:
                                code_to_name = df_all['name'].to_dict()
                            print(f"[*] 全力开启全盘挖掘模式，扫描 {len(codes)} 只个股...")
                            
                        if args.top_n and not codes:
                            # 按涨幅排序取 Top N (最高 100)
                            n = min(args.top_n, 100)
                            if 'percent' in df_all.columns:
                                df_top = df_all.sort_values(by='percent', ascending=False).head(n)
                                codes = df_top.index.tolist()
                                if 'name' in df_top.columns:
                                    code_to_name = df_top['name'].to_dict()
                            print(f"[*] 提取涨幅 Top {n} 个股进行深度审计")
                except Exception as e:
                    print(f"[!] 加载共享池失败: {e}")
            else:
                print("[!] 未找到共享 HDF5 数据文件，无法执行批量审计。")
        
        # 兜底
        if not codes:
            codes = ["002990", "603698", "300058"]
            print(f"[*] 使用默认演示代码: {codes}")
            
        summaries = audit_multiple_codes(codes, args.start, args.end, code_to_name=code_to_name)
        
        if summaries:
            print("\n" + "="*85)
            print(f"{' [ CROSS-STOCK INTENT SCOREBOARD ] ':=^85}")
            print("="*85)
            print(f"{'Code':<8} {'Name':<10} {'Score':<10} {'Gain%':<10} {'Classification'}")
            print("-" * 85)
            for s in sorted(summaries, key=lambda x: x.intent_score, reverse=True):
                print(f"{s.code:<8} {s.name:<10} {s.intent_score:>8.1f} {s.total_pct:>9.1f}%   {s.verdict}")
            print("="*85)
            print(f"\n[ 审计专家判定报告 ]")
            for s in sorted(summaries, key=lambda x: x.intent_score, reverse=True):
                print(f"\n>>> {s.name} ({s.code}) -> {s.verdict}")
                for sug in s.suggestions: print(sug)
                
                if args.verbose:
                    print(f"\n    [ 指标演进提炼 (Indicator Evolution) ]")
                    print(f"    {'Date':<12} {'Alpha':>8} {'Pct%':>8} {'Idx%':>8} {'C/Upper':>8} {'V-Ratio':>8}")
                    # 只显示最近 10 天
                    for h in s.history[-10:]:
                        print(f"    {h['date']:<12} {h['alpha']:>8.2f} {h['pct']:>8.2f} {h['idx_pct']:>8.2f} {h['c_upper']:>8.2f} {h['v_ratio']:>8.2f}")
            print("\n" + "="*85)
            
            # 如果是全盘挖掘模式，输出专门的潜伏报告
            if args.mine:
                print("\n" + "="*85)
                print(f"{' [ 🕵️ 全盘潜伏基因种子挖掘报告 ] ':=^85}")
                print("="*85)
                print(f"{'Code':<8} {'Name':<10} {'Score':<10} {'Squeeze':<10} {'Today%':<10} {'Verdict'}")
                print("-" * 85)
                # 挖掘过滤器：分数较高、涨幅未爆发(<5%)、且具备蓄势或韧性基因
                mining_seeds = [s for s in summaries if s.intent_score > 35 and s.history[-1]['pct'] < 5.0]
                # 优先展示有“龙息蓄势”或“韧性”的
                mining_seeds = sorted(mining_seeds, key=lambda x: (x.dragon_squeeze_days > 0, x.intent_score), reverse=True)
                
                for s in mining_seeds[:30]: # 只透视最有潜力的 30 个
                    now_pct = s.history[-1]['pct']
                    print(f"{s.code:<8} {s.name:<10} {s.intent_score:>8.1f} {s.dragon_squeeze_days:>8} {now_pct:>9.2f}%   {s.verdict}")
                
                print("-" * 85)
                print(f"[*] 全盘挖掘完成。从 {len(summaries)} 只个股中提炼出 {len(mining_seeds)} 只潜伏种子。")
                print("="*85)

    # 打印全局性能汇总 (仅在 verbose 模式显示)
    if hasattr(args, 'verbose') and args.verbose:
        print("\n" + "="*45)
        print_timing_summary()
        print("="*45)

if __name__ == "__main__":
    main()
