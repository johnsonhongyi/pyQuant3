# -*- coding: utf-8 -*-
import time
import logging
import pandas as pd
import gzip
import json
import glob
import os
import sys

# 导入核心组件并强制初始化环境路径
try:
    from JSONData import tdx_data_Day as tdd
    from sector_focus_engine import DragonLeaderTracker, DragonStatus
    
    # ⭐ 核心补丁：强制指定 TDX 路径，解决单机脚本找不到数据的问题
    tdx_root = r"D:\MacTools\WinTools\new_tdx2"
    if os.path.exists(tdx_root):
        tdd.path_dir = os.path.join(tdx_root, "vipdoc")
        # 如果 tdd 内部有缓存或多处引用，直接修改可能不够，我们再补一层
        os.environ['TDX_ROOT'] = tdx_root 
except ImportError as e:
    print(f"❌ 信号引擎导入失败: {e}")
    sys.exit(1)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("FinalVerify")

def normalize_code(code):
    c = str(code).strip().lower()
    raw = c[2:] if c.startswith(('sh', 'sz')) else c
    if len(raw) == 6:
        if raw.startswith(('6', '9')): return raw + '.SH'
        else: return raw + '.SZ'
    return raw.upper()

def run_verify():
    # 1. 冒烟测试：确认 601111.SH 能加载出数据
    test_code = "601111"
    df = tdd.get_tdx_Exp_day_to_df(test_code, dl=10)
    if df is None or df.empty:
        logger.error(f"❌ 数据加载失败! 路径 {tdd.path_dir} 下未找到 {test_code}。")
        # 尝试遍历一下目录看看到底在哪
        sh_path = os.path.join(tdd.path_dir, "sh", "lday")
        if os.path.exists(sh_path):
            files = os.listdir(sh_path)[:5]
            logger.info(f"📁 路径存在，前5个文件: {files}")
        return

    logger.info(f"✅ 环境对齐成功! {test_code} 加载了 {len(df)} 行数据。")
    
    # 2. 提取最近快照中的 100 只个股进行“冷启动”挖掘
    files = glob.glob('snapshots/bidding_*.json.gz')
    if not files: return
    latest = sorted(files, reverse=True)[0]
    with gzip.open(latest, 'rb') as f:
        data = json.load(f)
    
    def find_stocks(d):
        if not isinstance(d, dict): return []
        s = [k for k in d.keys() if str(k)[-6:].isdigit() and len(str(k))>=6]
        if len(s) > 30: return s
        for v in d.values():
            res = find_stocks(v)
            if res: return res
        return []

    sample_codes = [normalize_code(c) for c in find_stocks(data)[:100]]
    
    # 3. 执行挖掘
    tracker = DragonLeaderTracker()
    tracker._records.clear()
    
    logger.info(f"🚀 开始历史 7 日深度挖掘 (样本={len(sample_codes)})...")
    t0 = time.perf_counter()
    tracker.mine_history_dragons(sample_codes, days=7)
    dt = (time.perf_counter() - t0) * 1000
    
    # 4. 验证结果
    recs = tracker.get_dragon_records(min_status=None)
    logger.info(f"📊 挖掘过程完成 (耗时: {dt:.2f} ms)")
    logger.info(f"📈 最终识别出的活跃龙头/候选: {len(recs)} 只")
    
    if recs:
        recs.sort(key=lambda x: (int(x['status']), x['consecutive_new_highs']), reverse=True)
        for r in recs[:15]:
            logger.info(f"   >> {r['code']} ({r['name']}): {r['status']} ({r['consecutive_new_highs']}日新高)")
    else:
        # 如果还是为 0，打印 601111.SH 的趋势判断细节
        logger.warning("⚠️ 未发现符合趋势的龙头。正在诊断 601111.SH...")
        tracker.mine_history_dragons([test_code], days=7)
        if test_code in tracker._records:
            r = tracker._records[test_code]
            logger.info(f"💡 诊断: {test_code} 其实被识别到了! 状态={r.status}, 新高天={r.consecutive_new_highs}")
        else:
            logger.error(f"❌ 关键诊断失败: {test_code} 依然未被识别。")

if __name__ == "__main__":
    run_verify()
