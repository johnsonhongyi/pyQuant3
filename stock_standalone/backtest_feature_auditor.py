
import sys
import os
import argparse
import pandas as pd
import numpy as np
from datetime import datetime
import concurrent.futures
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

def get_corresponding_index(code):
    return INDEX_MAP.get(code[:2], '999999')

def preheat_names(codes):
    """[🚀 极致优化] 批量预热股票名称，消除循环内频繁打开 HDF5 的灾难级 IO"""
    with timed_ctx("Preheat Names"):
        missing_codes = [c for c in codes if c not in NAME_CACHE]
        if not missing_codes: return
        
        # 默认内置一些核心标的
        meta_names = {'002990': '盛视科技', '603698': '航天工程', '300058': '蓝色光标'}
        for c, n in meta_names.items():
            if c in missing_codes:
                NAME_CACHE[c] = n
        
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
                            for code, row in df_names.iterrows():
                                NAME_CACHE[str(code).zfill(6)] = row.get('name', str(code))
        except Exception as e:
            # print(f"DEBUG: Name Preheat failed: {e}")
            pass
            
        # 补齐未找到的
        for c in codes:
            if c not in NAME_CACHE: NAME_CACHE[c] = c

def calculate_dna_indicators(df):
    with timed_ctx("DNA Indicators Calculate"):
        if df is None or len(df) < 20: return None
        df['pct'] = df['close'].pct_change() * 100
        df['ma10'] = df['close'].rolling(10).mean()
        df['ma20'] = df['close'].rolling(20).mean()
        df['ma10_vol'] = df['vol'].rolling(10).mean()
        std = df['close'].rolling(20).std()
        df['upper'] = df['ma20'] + 2 * std
        df['high4'] = df['high'].rolling(4).max().shift(1)
        df['c_upper'] = df['close'] / df['upper']
        df['c_h4'] = df['close'] / df['high4']
        df['v_ratio'] = df['vol'] / df['ma10_vol']
        df['c_ma10'] = df['close'] / df['ma10']
        df['is_bid_low'] = (df['open'] == df['low'])
        return df

class AuditSummary:
    def __init__(self, code, name):
        self.code, self.name = code, name
        self.alpha_sum, self.max_adhesion = 0, 0
        self.squeeze_days, self.divergence_days = 0, 0
        self.intent_score, self.verdict, self.total_pct = 0, "", 0
        self.suggestions = []

    def finalize(self, rows):
        self.alpha_sum = sum(r['alpha'] for r in rows)
        self.total_pct = (rows[-1]['close'] / rows[0]['prev_close'] - 1) * 100
        streak = 0
        for r in rows:
            if r['c_upper'] >= 1.0:
                streak += 1
                self.max_adhesion = max(self.max_adhesion, streak)
            else: streak = 0
            if r['v_ratio'] < 0.76 and abs(r['alpha']) < 1.0: self.squeeze_days += 1
            if r['pct'] > 0 and r['idx_pct'] < -0.3: self.divergence_days += 1
        self.intent_score = (self.alpha_sum * 0.4) + (self.max_adhesion * 5) + (self.squeeze_days * 3)
        
        if self.intent_score > 35 and self.max_adhesion >= 3:
            self.verdict = "💎 [金身种子] 核心主升"
            self.suggestions.append("- 探测到极高 Alpha 浓度，展现出极其罕见的独立主升意图")
            self.suggestions.append(f"- 轨道接力稳固({self.max_adhesion}天)，股价贴合 Upper 强轴爬行")
        elif self.intent_score > 15:
            self.verdict = "🚀 [加速跑道] 意图确认"
            self.suggestions.append("- 正在脱离结构压力位，处于爆发初期的轨道切换阶段")
        else:
            self.verdict = "⚠️ [诱多陷阱] 杂毛跟风"
            self.suggestions.append("- 缺乏独立进攻基因，轨道拒斥明显，跟风属性重")
        if self.divergence_days >= 2:
            self.suggestions.append(f"- 存在 {self.divergence_days} 天抗跌背离，符合泥沙俱下中的种子特征")

def run_optimized_audit(code, start_date, end_date):
    with timed_ctx(f"Load & Audit {code}"):
        with timed_ctx("Data Loading"):
            # [🚀 LIGHTWEIGHT LOAD] 使用 fastohlc=True 跳过不使用的 MACD/OBV 等重型指标计算
            df_raw = get_tdx_Exp_day_to_df(code, dl=800, fastohlc=True)
        
        if df_raw is None or df_raw.empty: return None
        name = NAME_CACHE.get(code, code)
        df = calculate_dna_indicators(df_raw.copy())
        if df is None: return None
        
        idx_code = get_corresponding_index(code)
        if idx_code in INDEX_DATA_CACHE:
            df_idx = INDEX_DATA_CACHE[idx_code]
        else:
            with timed_ctx(f"Load Index {idx_code}"):
                # [🚀 LIGHTWEIGHT LOAD] 指数同样使用极速模式
                df_idx = get_tdx_Exp_day_to_df(idx_code, dl=800, fastohlc=True)
                INDEX_DATA_CACHE[idx_code] = df_idx
        df_idx['idx_pct'] = df_idx['close'].pct_change() * 100
        s_dt = f"{start_date[:4]}-{start_date[4:6]}-{start_date[6:8]}"
        e_dt = f"{end_date[:4]}-{end_date[4:6]}-{end_date[6:8]}" if end_date else df.index[-1]
        audit_dates = df.index[(df.index >= s_dt) & (df.index <= e_dt)]
        if len(audit_dates) == 0: return None
        
        summary = AuditSummary(code, name)
        audit_rows = []
        # print(f"\n>>> [ DNA 审计 ] {code} ({name})") # reduce noise in batch processing
        for dt in audit_dates:
            row = df.loc[dt]
            idx_p = df_idx.loc[dt, 'idx_pct'] if dt in df_idx.index else 0
            audit_rows.append({'alpha': row['pct'] - idx_p, 'idx_pct': idx_p, 'pct': row['pct'], 'c_upper': row['c_upper'], 'v_ratio': row['v_ratio'], 'close': row['close'], 'prev_close': df.iloc[df.index.get_loc(dt)-1]['close']})
        summary.finalize(audit_rows)
        return summary

def audit_multiple_codes(codes, start_date=None, end_date=None, code_to_name=None):
    """
    供外部调用的批量审计接口
    :param code_to_name: 可选字典 {code: name}，若提供则跳过 HDF5 磁盘查询提升性能
    """
    if start_date is None:
        start_date = (datetime.now() - pd.Timedelta(days=25)).strftime("%Y%m%d")
    
    # [🚀 极速注入] 如果外部提供了名称对照表，直接存入内存缓存
    if code_to_name:
        for c, n in code_to_name.items():
            NAME_CACHE[c] = n
            
    preheat_names(codes)
    summaries = []
    
    with timed_ctx("Batch Execution"):
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            futures = {executor.submit(run_optimized_audit, code, start_date, end_date): code for code in codes}
            for future in concurrent.futures.as_completed(futures):
                try:
                    s = future.result()
                    if s: summaries.append(s)
                except Exception as e:
                    print(f"Error auditing {futures[future]}: {e}")
                    
    return summaries

class DnaAuditReportWindow(tk.Toplevel, WindowMixin):
    def __init__(self, summaries, parent=None):
        super().__init__(parent)
        self.summaries = summaries
        self.monitor_app = parent
        self.window_name = "dna_audit_report_v2"
        self.scale_factor = getattr(parent, 'scale_factor', 1.0) if parent else 1.0
        
        self.title(f"🧬 DNA 专项审计报告 (深度挖掘) - {len(summaries)}只")
        self.attributes("-topmost", False)
        
        self._setup_ui()
        
        # 加载位置与尺寸
        self.load_window_position(self, self.window_name, default_width=1000, default_height=750)
        
        # [NEW] 加载分割线位置 (延迟等待 UI 布局完成)
        self.after(200, self._load_sash_position)
        
        # 填充数据
        self._fill_data()
        
        # 绑定关闭保存
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        
        # 初始选中 (仅选中，不强制触发 Linkage 避免主程序意外跳转)
        if self.tree.get_children():
            first = self.tree.get_children()[0]
            self.tree.selection_set(first)
            self.tree.focus(first)
            # self._show_detail(None) # 禁用初始触发，由用户手动点击或查看

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
        data = [(self.tree.set(k, col), k) for k in self.tree.get_children('')]
        
        # 尝试数值排序
        try:
            data.sort(key=lambda t: float(t[0]), reverse=reverse)
        except ValueError:
            data.sort(reverse=reverse)

        for index, (val, k) in enumerate(data):
            self.tree.move(k, '', index)

        self.tree.heading(col, command=lambda: self._sort_column(col, not reverse))

    def _show_detail(self, event):
        sel = self.tree.selection()
        if not sel: return
        vals = self.tree.item(sel[0])['values']
        code = str(vals[0]).zfill(6)
        
        # [🚀 LINKAGE] 单击同步联动 TDX 与可视化终端
        if self.monitor_app and hasattr(self.monitor_app, 'on_code_click'):
            self.monitor_app.on_code_click(code)
            
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
            self.txt_detail.insert(tk.END, "\n" + "="*60 + "\n")
            
            # 设置简单的富文本样式
            self.txt_detail.tag_configure("title", font=("微软雅黑", 12, "bold"), foreground="#2c3e50")

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

def show_dna_audit_report_window(summaries, parent=None):
    if not summaries:
        from tkinter import messagebox
        messagebox.showinfo("DNA 审计", "没有产生足够的历史数据，或没有命中任何结论。", parent=parent)
        return
    
    # 使用新定义的类
    DnaAuditReportWindow(summaries, parent=parent)

def main():
    parser = argparse.ArgumentParser(description="DNA 审计专家 v9.8")
    parser.add_argument("-c", "--code", type=str, default="002990,603698,300058")
    parser.add_argument("-s", "--start", type=str, default="20260328")
    parser.add_argument("-e", "--end", type=str)
    args = parser.parse_args()
    
    with timed_ctx("Total Execution"):
        codes = [c.strip().zfill(6) for c in args.code.split(',')]
        summaries = audit_multiple_codes(codes, args.start, args.end)
        
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
            print("\n" + "="*85)

    # 打印全局性能汇总
    print("\n" + "="*45)
    print_timing_summary()
    print("="*45)

if __name__ == "__main__":
    main()
