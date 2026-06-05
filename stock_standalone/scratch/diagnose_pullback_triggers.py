# -*- coding: utf-8 -*-
import os
import sys
import zlib
import json
import pandas as pd
from datetime import datetime

# 强制将标准输出和标准错误输出流设为支持替换错误字符的 utf-8 模式，防止 Windows 终端崩溃
try:
    if sys.stdout.encoding.lower() != 'utf-8':
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
except Exception:
    pass

# 将项目根目录加入模块搜索路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from sector_focus_engine import SectorFocusMap, StarFollowEngine, IntradayPullbackDetector, SectorHeat

def analyze_snapshot(file_path):
    print("=" * 80)
    print(f"[*] 正在分析快照文件: {os.path.basename(file_path)}")
    print("=" * 80)

    # 1. 加载并解压数据
    try:
        with open(file_path, 'rb') as f:
            raw_bytes = f.read()
        json_str = zlib.decompress(raw_bytes).decode('utf-8')
        data = json.loads(json_str)
    except Exception as e:
        print(f"❌ 读取解压失败: {e}")
        return

    data_date = data.get('data_date', 'unknown')
    print(f"[-] 数据日期: {data_date}")

    sector_data = data.get('sector_data', {})
    stock_scores = data.get('stock_scores', {})
    meta_cols = data.get('meta_cols', {})

    if not sector_data:
        print("⚠️ 快照中无 active_sectors (sector_data) 数据。")
        return

    # 2. 还原 stock_snap
    stock_snap = {}
    if meta_cols and 'code' in meta_cols:
        codes = meta_cols['code']
        for i, code in enumerate(codes):
            if not code or len(code) != 6:
                continue
            
            def _get(key, default):
                val = meta_cols.get(key, [])
                return val[i] if i < len(val) and val[i] is not None else default

            stock_snap[code] = {
                'code': code,
                'name': _get('n', code),
                'pct': _get('p', 0.0),
                'pct_diff': _get('p', 0.0), # 兼容
                'score': stock_scores.get(code, _get('s', 0.0)),
                'price': _get('np', 0.0),
                'last_close': _get('lc', 0.0),
                'high_day': _get('hd', 0.0),
                'low_day': _get('ld', 0.0),
                'category': _get('c', ''),
                'pattern_hint': _get('ph', ''),
                'vol_ratio': _get('rl', 1.0),
                'signal_count': _get('sc', 0),
                'klines': [] # 简化
            }

    print(f"[-] 板块数: {len(sector_data)} | 还原个股数: {len(stock_snap)}")

    # 3. 构造 SectorFocusMap 并注入数据
    sector_map = SectorFocusMap()
    
    # 构造 active_sectors 列表
    active_sectors_list = []
    for sname, info in sector_data.items():
        sec_dict = {
            'sector': sname,
            'score': info.get('bidding_score', info.get('score', 0.0)),
            'score_diff': info.get('score_diff', 0.0),
            'follow_ratio': info.get('follow_ratio', 0.0),
            'leader': info.get('leader', info.get('leader_code', '')),
            'leader_name': info.get('leader_name', ''),
            'leader_pct': info.get('leader', {}).get('pct', info.get('leader_pct', info.get('leader_change_pct', 0.0))) if isinstance(info.get('leader'), dict) else info.get('leader_pct', info.get('leader_change_pct', 0.0)),
            'leader_pct_diff': info.get('leader_pct_diff', 0.0),
            'leader_dff': info.get('leader_dff', 0.0),
            'leader_vwap': info.get('leader_vwap', 0.0),
            'tags': info.get('tags', ''),
            'followers': info.get('followers', [])
        }
        active_sectors_list.append(sec_dict)

    # 注入数据
    sector_map.inject_detector_sectors(active_sectors_list, stock_snap)

    # 4. 模拟 StarFollowEngine 确核龙头
    star_engine = StarFollowEngine(sector_map)
    # 我们把 meta_cols 里的代码根据其涨幅，做龙头确认
    confirmed_leaders = []
    for code, snap in stock_snap.items():
        pct = snap['pct']
        if pct >= star_engine.LEADER_MIN_ZT_OR_PCT:
            # 简单模拟胜出确核
            with star_engine._lock:
                star_engine._confirmed_leaders[code] = datetime.now()
                star_engine._leader_baselines[code] = pct
            confirmed_leaders.append(code)

    print(f"[-] 模拟确核龙头数: {len(confirmed_leaders)} 个 (例如: {confirmed_leaders[:5]})")

    # 打印排名前10的板块分数与计算出的热度
    all_heats = []
    for sname in sector_map._sector_map.keys():
        sh = sector_map.get_sector_heat(sname)
        if sh:
            all_heats.append((sname, sh.bidding_score, sh.heat_score, sh.leader_code, sh.leader_name))
    all_heats.sort(key=lambda x: x[2], reverse=True)
    
    above_35 = len([x for x in all_heats if x[2] >= 35.0])
    below_35 = len(all_heats) - above_35
    print(f"[-] 板块热度(heat_score)统计: 共 {len(all_heats)} 个板块 | 热度>=35: {above_35} 个 | 热度<35: {below_35} 个")
    print("\n[-] 板块热度(heat_score)排名前10名:")
    for rank, (sname, b_score, h_score, l_code, l_name) in enumerate(all_heats[:10], 1):
        print(f"    {rank}. {sname} | 基础分: {b_score:.2f} | 热度分: {h_score:.2f} | 龙头: {l_code}({l_name})")
    print("-" * 50)

    # 5. 模拟 PullbackDetector 扫描，详细统计拦截原因
    detector = IntradayPullbackDetector(sector_map, star_engine)
    
    stats = {
        'total_scanned': 0,
        'passed': 0,
        'no_sector_map': 0,
        'blocked_sector_heat': 0,
        'blocked_no_leader': 0,
        'blocked_leader_weak': 0,
        'blocked_sector_heat_follower': 0,
        'blocked_not_top3_follower': 0,
        'blocked_t_factor': 0,
        'blocked_price_below_prev_close': 0,
        'blocked_pct_too_low': 0,
        'blocked_vwap_break': 0,
        'no_pattern_match': 0,
        'error': 0
    }

    passed_list = []

    # 遍历所有还原个股，运行扫描
    for code, snap in stock_snap.items():
        stats['total_scanned'] += 1
        
        price = float(snap.get('price', 0.0))
        day_high = float(snap.get('high_day', price))
        prev_close = float(snap.get('last_close', 0.0))
        name = snap.get('name', code)
        pct_diff = float(snap.get('pct_diff', 0.0))
        vol_ratio = float(snap.get('vol_ratio', 1.0))
        vwap = price # 简化

        is_debug_stock = name in ('丰光精密', '创远信科', '绿的谐波')
        if is_debug_stock:
            print(f"--- [DEBUG Stock: {name} ({code})] ---")
            print(f"    - price: {price} | prev_close: {prev_close} | pct: {(price/prev_close-1)*100:.2f}%")

        if price <= 0 or prev_close <= 0:
            if is_debug_stock: print(f"    - 拦截: 价格或昨收无效 ({price}/{prev_close})")
            stats['error'] += 1
            continue

        sector = sector_map.get_sector_of_code(code)
        if not sector:
            if is_debug_stock: print(f"    - 拦截: 无板块关系映射 (sector_map中未绑定该个股)")
            stats['no_sector_map'] += 1
            continue

        sh = sector_map.get_sector_heat(sector)
        sector_heat = sh.heat_score if sh else 0.0
        leader_code = sh.leader_code if sh else ''
        sector_type = sh.sector_type if sh else ''
        
        if is_debug_stock:
            print(f"    - sector: {sector} | heat: {sector_heat} | leader_code: {leader_code} | sector_type: {sector_type}")

        # A. 板块热度拦截
        if sector_heat < detector.MIN_SECTOR_HEAT:
            if is_debug_stock: print(f"    - 拦截: 板块热度 {sector_heat} 小于最小热度 {detector.MIN_SECTOR_HEAT}")
            stats['blocked_sector_heat'] += 1
            continue

        # B. 跟风股门槛拦截
        is_king = (code == leader_code)
        if not is_king:
            if not leader_code:
                if is_debug_stock: print(f"    - 拦截: 跟风股无龙头 (leader_code为空)")
                stats['blocked_no_leader'] += 1
                continue
            if not star_engine.is_leader_strong(leader_code):
                if is_debug_stock: print(f"    - 拦截: 龙头股 {leader_code} 不强")
                stats['blocked_leader_weak'] += 1
                continue
            if sector_heat < 45.0:
                if is_debug_stock: print(f"    - 拦截: 跟风股要求板块热度>=45，当前为 {sector_heat}")
                stats['blocked_sector_heat_follower'] += 1
                continue
            if code not in sh.follower_codes:
                if is_debug_stock: print(f"    - 拦截: 个股不在跟随股前3名单中 (follower_codes: {sh.follower_codes})")
                stats['blocked_not_top3_follower'] += 1
                continue
            
            # T-Factor
            t_val = 0.0
            for f_det in sh.follower_detail:
                if f_det.get('code') == code:
                    t_val = float(f_det.get('t_factor', 0.0))
                    break
            if t_val < 0.5:
                if is_debug_stock: print(f"    - 拦截: 跟风股 T-factor 为 {t_val}，小于 0.5")
                stats['blocked_t_factor'] += 1
                continue

        # C. 强势前置条件拦截
        change_pct = (price / prev_close - 1) * 100
        if price < prev_close:
            if is_debug_stock: print(f"    - 拦截: 价格 {price} 低于昨收 {prev_close}")
            stats['blocked_price_below_prev_close'] += 1
            continue

        if change_pct < 2.0:
            if is_debug_stock: print(f"    - 拦截: 涨幅 {change_pct:.2f}% 低于 2.0%")
            stats['blocked_pct_too_low'] += 1
            continue

        diff_from_vwap = (price - vwap) / vwap
        if diff_from_vwap < -0.005:
            if is_debug_stock: print(f"    - 拦截: 偏离均线百分比 {diff_from_vwap*100:.2f}% 低于 -0.5%")
            stats['blocked_vwap_break'] += 1
            continue

        # D. 形态匹配
        drop_from_high = (price - day_high) / day_high
        matched = False

        if is_debug_stock:
            print(f"    - 开始形态匹配: drop_from_high: {drop_from_high*100:.2f}%, diff_from_vwap: {diff_from_vwap*100:.2f}%, vol_ratio: {vol_ratio:.2f}")

        # 形态1：飞刀接落
        if (drop_from_high <= detector.MIN_DROP_FROM_HIGH and
                detector.MAX_DROP_FROM_VWAP <= diff_from_vwap <= 0.005 and
                vol_ratio <= detector.MAX_VOL_RATIO_DURING):
            matched = True
            if is_debug_stock: print(f"    - 匹配成功: 形态1 (飞刀接落)")

        # 形态2：VWAP支撑
        elif (abs(diff_from_vwap) <= 0.003 and
              vol_ratio >= 1.0 and
              star_engine.is_leader_strong(leader_code)):
            matched = True
            if is_debug_stock: print(f"    - 匹配成功: 形态2 (VWAP支撑)")

        # 形态3：板块共振点
        elif (star_engine.is_leader_strong(leader_code) and
              diff_from_vwap >= -0.008 and
              pct_diff >= 0.3):
            matched = True
            if is_debug_stock: print(f"    - 匹配成功: 形态3 (板块共振点)")

        # 形态4：强势蓄势突破
        elif ('蓄势' in sector_type or '强攻' in sector_type):
            if pct_diff >= 0.5 and diff_from_vwap >= -0.005:
                matched = True
                if is_debug_stock: print(f"    - 匹配成功: 形态4 (强势蓄势突破)")

        # 形态5：中阳起步确认
        if not matched:
            if pct_diff >= 5.0 and diff_from_vwap >= 0:
                matched = True
                if is_debug_stock: print(f"    - 匹配成功: 形态5 (中阳起步确认)")

        if matched:
            stats['passed'] += 1
            passed_list.append(f"{code}({name}) | 昨收: {prev_close:.2f} | 现价: {price:.2f} | 涨幅: {change_pct:+.2f}% | 偏离均线: {diff_from_vwap*100:+.2f}% | 板块: {sector}({sector_heat:.1f})")
        else:
            if is_debug_stock: print(f"    - 拦截: 未能匹配任何买点形态")
            stats['no_pattern_match'] += 1

    # 打印统计
    print("\n[+] 拦截拦截门槛统计结果:")
    print(f"    - 总扫描个股数: {stats['total_scanned']}")
    print(f"    - 成功通过(产生买点): {stats['passed']}")
    print(f"    - 拦截: 无板块关系映射: {stats['no_sector_map']}")
    print(f"    - 拦截: 板块热度低 (< {detector.MIN_SECTOR_HEAT}): {stats['blocked_sector_heat']}")
    print(f"    - 拦截: 跟风股无龙头: {stats['blocked_no_leader']}")
    print(f"    - 拦截: 跟风股龙头未确核或弱化: {stats['blocked_leader_weak']}")
    print(f"    - 拦截: 跟风股板块热度低 (< 45.0): {stats['blocked_sector_heat_follower']}")
    print(f"    - 拦截: 跟风股非前三跟风: {stats['blocked_not_top3_follower']}")
    print(f"    - 拦截: 跟风股 T-Factor 低 (< 0.5): {stats['blocked_t_factor']}")
    print(f"    - 拦截: 价格低于昨收: {stats['blocked_price_below_prev_close']}")
    print(f"    - 拦截: 涨幅过低 (< 2.0%): {stats['blocked_pct_too_low']}")
    print(f"    - 拦截: 跌破均线 (> 0.5%): {stats['blocked_vwap_break']}")
    print(f"    - 拦截: 无任何买点形态匹配: {stats['no_pattern_match']}")
    print(f"    - 异常数据/计算错误: {stats['error']}")

    if passed_list:
        print("\n[+] 通过的股票列表:")
        for p in passed_list[:15]:
            print(f"      {p}")
        if len(passed_list) > 15:
            print(f"      ... 以及其他 {len(passed_list) - 15} 只股票")
    else:
        print("\n[-] 没有任何股票通过买点过滤门槛。")
    print("\n")

def main():
    app_root = project_root
    snapshots_dir = os.path.join(app_root, "snapshots")
    
    # 查找 6 月份的快照文件
    files = sorted([
        os.path.join(snapshots_dir, f) for f in os.listdir(snapshots_dir)
        if f.startswith("bidding_202606") and f.endswith(".json.gz")
    ])
    
    if not files:
        # 如果没有 6 月份，就找最后三个 json.gz
        files = sorted([
            os.path.join(snapshots_dir, f) for f in os.listdir(snapshots_dir)
            if f.startswith("bidding_") and f.endswith(".json.gz") and not "ui_state" in f
        ])[-3:]

    if not files:
        print("❌ 未在 snapshots 目录下找到任何 bidding 快照数据！")
        return

    for fpath in files:
        analyze_snapshot(fpath)

if __name__ == "__main__":
    main()
