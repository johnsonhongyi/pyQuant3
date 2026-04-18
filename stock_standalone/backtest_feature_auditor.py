
import sys
import os
import argparse
import pandas as pd
import numpy as np
from datetime import datetime

# 强制 UTF-8 输出，解决 Windows 终端乱码
if __name__ == "__main__" and sys.platform.startswith('win'):
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 自动处理路径
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(BASE_DIR)
sys.path.append(os.path.join(BASE_DIR, 'JSONData'))

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
            df_raw = get_tdx_Exp_day_to_df(code, dl=800)
        
        if df_raw is None or df_raw.empty: return None
        name = NAME_CACHE.get(code, code)
        df = calculate_dna_indicators(df_raw.copy())
        if df is None: return None
        
        idx_code = get_corresponding_index(code)
        if idx_code in INDEX_DATA_CACHE:
            df_idx = INDEX_DATA_CACHE[idx_code]
        else:
            with timed_ctx(f"Load Index {idx_code}"):
                df_idx = get_tdx_Exp_day_to_df(idx_code, dl=800)
                INDEX_DATA_CACHE[idx_code] = df_idx
        df_idx['idx_pct'] = df_idx['close'].pct_change() * 100
        s_dt = f"{start_date[:4]}-{start_date[4:6]}-{start_date[6:8]}"
        e_dt = f"{end_date[:4]}-{end_date[4:6]}-{end_date[6:8]}" if end_date else df.index[-1]
        audit_dates = df.index[(df.index >= s_dt) & (df.index <= e_dt)]
        if len(audit_dates) == 0: return None
        
        summary = AuditSummary(code, name)
        audit_rows = []
        print(f"\n>>> [ DNA 审计 ] {code} ({name})")
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
    for code in codes:
        s = run_optimized_audit(code, start_date, end_date)
        if s: summaries.append(s)
    return summaries

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
