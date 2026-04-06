# -*- coding: utf-8 -*-
import time
import logging
import pandas as pd
import gzip
import json
import glob
import os
import sys

# 尝试导入核心组件
try:
    from sector_focus_engine import DragonLeaderTracker, DragonStatus
    from JSONData import tdx_data_Day as tdd
except ImportError as e:
    print(f"❌ 导入失败: {e}")
    sys.exit(1)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("PerfTest")

def normalize_code(code):
    """代码规范化"""
    c = str(code).strip().lower()
    raw = c[2:] if c.startswith(('sh', 'sz')) else c
    if len(raw) == 6:
        if raw.startswith('6') or raw.startswith('9'): return raw + '.SH'
        else: return raw + '.SZ'
    return raw.upper()

def get_real_codes_from_snapshots(limit=500):
    """鲁棒地提取真实个股池"""
    files = glob.glob('snapshots/bidding_*.json.gz')
    if not files: return ['600519.SH', '000858.SZ']
    
    latest = sorted(files, reverse=True)[0]
    logger.info(f"📂 解析快照: {os.path.basename(latest)}")
    try:
        with gzip.open(latest, 'rb') as f:
            data = json.load(f)
            # 自动解包
            if len(data) == 1 and str(list(data.keys())[0]).startswith('202'):
                data = list(data.values())[0]

            items = []
            for k, v in data.items():
                if len(str(k)) < 6: continue
                try:
                    score = float(v[0]) if isinstance(v, list) else float(v)
                except: score = 0.0
                items.append((k, score))
            
            items.sort(key=lambda x: x[1], reverse=True)
            codes = []
            for k, _ in items:
                if k.startswith(('sh000', 'sz399', 'sz395', 'sh999', '999999')): continue
                codes.append(normalize_code(k))
                if len(codes) >= limit: break
            
            logger.info(f"✅ 已提取 {len(codes)} 只真实个股进行压测")
            return codes
    except Exception as e:
        logger.warning(f"解析失败: {e}")
        return ['600519.SH']

def run_performance_test():
    if tdd is None: return
    tracker = DragonLeaderTracker()
    with tracker._lock: tracker._records.clear()
    
    # 扩大到 800 只，保证能产生结果
    real_codes = get_real_codes_from_snapshots(limit=800)
    
    logger.info(f"🚀 开始真实的【7日深度挖掘】压测 (样本池={len(real_codes)})...")
    start_cur = time.perf_counter()
    tracker.mine_history_dragons(real_codes, days=7)
    duration = (time.perf_counter() - start_cur) * 1000
    
    # 状态展示 (验证 TypeError 是否已通过引擎端修复)
    found = tracker.get_dragon_records(min_status=None)
    logger.info(f"✅ 挖掘完成! 耗时: {duration:.2f} ms")
    logger.info(f"📊 累计活跃记录 (含候选): {len(found)} 只")
    
    if found:
        # 按连续新高天数再次排序
        found.sort(key=lambda x: x['consecutive_new_highs'], reverse=True)
        for r in found[:15]: 
            logger.info(f"   └─ {r['code']} ({r['name']}): {r['status']} ({r['consecutive_new_highs']}日新高)")
    else:
        logger.warning("⚠️ 挖掘池结论为空。请确保 TDX 数据最新且挖掘算法已放宽阈值。")

if __name__ == "__main__":
    run_performance_test()
