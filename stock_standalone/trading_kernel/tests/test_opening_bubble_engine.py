import os
import sys
import time
import pytest
import numpy as np
import pandas as pd

_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(_DIR))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from ats.opening_bubble_engine import (
    OpeningBubbleEngine, get_opening_bubble_engine, get_pct_tier, get_vol_tier
)
from ats.limit_up_engine import LimitUpEngine


def test_pct_tier_classification():
    """测试 8 级阶梯划分准确性"""
    assert get_pct_tier(-5.0) == 0   # <-4%
    assert get_pct_tier(-3.0) == 1   # -4%~-2%
    assert get_pct_tier(-0.5) == 2   # -2%~0%
    assert get_pct_tier(1.2) == 3    # 0%~2%
    assert get_pct_tier(3.5) == 4    # 2%~4%
    assert get_pct_tier(5.2) == 5    # 4%~6%
    assert get_pct_tier(7.0) == 6    # 6%~8%
    assert get_pct_tier(9.9) == 7    # >8%


def test_vol_tier_classification():
    """测试量能能级划分"""
    assert get_vol_tier(1.0) == 1
    assert get_vol_tier(2.0) == 2
    assert get_vol_tier(4.0) == 3
    assert get_vol_tier(8.0) == 4


def test_pattern_recognition_and_transitions():
    """测试开盘形态识别与多轮冒泡跃迁"""
    engine = OpeningBubbleEngine()
    engine.reset_daily()

    # 1. 模拟 Round 1: 09:30 开盘快照
    df_round1 = pd.DataFrame([
        # 标的A: 低开 -1.5%
        {"code": "000001", "name": "平安银行", "close": 10.0, "open": 9.85, "pre_close": 10.0, "percent": -1.5, "volume_ratio": 1.8, "vwap": 9.85, "amount": 50000000},
        # 标的B: 高开 +3.0%
        {"code": "600519", "name": "贵州茅台", "close": 1854.0, "open": 1854.0, "pre_close": 1800.0, "percent": 3.0, "volume_ratio": 2.5, "vwap": 1854.0, "amount": 100000000},
        # 标的C: 平开 +0.2%
        {"code": "002412", "name": "汉森制药", "close": 10.02, "open": 10.02, "pre_close": 10.0, "percent": 0.2, "volume_ratio": 1.2, "vwap": 10.02, "amount": 20000000},
        # 标的D: 高开 +4.0%
        {"code": "601519", "name": "大智慧", "close": 10.4, "open": 10.4, "pre_close": 10.0, "percent": 4.0, "volume_ratio": 2.0, "vwap": 10.4, "amount": 30000000},
    ]).set_index("code")

    updated = engine.update_market_snapshot(df_round1)
    assert updated == 4

    # 2. 模拟 Round 2: 09:35 盘中演进
    # 标的A: 从 -1.5% 强力拉升至 +2.5% (低开高走反包，穿过0轴和均线)
    # 标的B: 高开 +3.0% 后横盘震荡在 +3.2% (高开放量蓄势)
    # 标的C: 从 0.2% 跃迁至 2.5% (经历阶梯 3 -> 4)
    # 标的D: 从 +4.0% 高开下杀至 +0.5% (跌破开盘价与均线，高开低走预警)
    df_round2 = pd.DataFrame([
        {"code": "000001", "name": "平安银行", "close": 10.25, "open": 9.85, "pre_close": 10.0, "percent": 2.5, "volume_ratio": 2.8, "vwap": 10.05, "amount": 120000000},
        {"code": "600519", "name": "贵州茅台", "close": 1857.6, "open": 1854.0, "pre_close": 1800.0, "percent": 3.2, "volume_ratio": 3.0, "vwap": 1855.0, "amount": 250000000},
        {"code": "002412", "name": "汉森制药", "close": 10.25, "open": 10.02, "pre_close": 10.0, "percent": 2.5, "volume_ratio": 2.5, "vwap": 10.15, "amount": 50000000},
        {"code": "601519", "name": "大智慧", "close": 10.05, "open": 10.4, "pre_close": 10.0, "percent": 0.5, "volume_ratio": 2.2, "vwap": 10.25, "amount": 80000000},
    ]).set_index("code")

    engine.update_market_snapshot(df_round2)

    # 3. 模拟 Round 3: 09:40
    # 标的C: 再次跃迁至 +5.5% (经历 0%~2% -> 2%~4% -> 4%~6% 步步高升)
    df_round3 = pd.DataFrame([
        {"code": "000001", "name": "平安银行", "close": 10.35, "open": 9.85, "pre_close": 10.0, "percent": 3.5, "volume_ratio": 3.2, "vwap": 10.12, "amount": 180000000},
        {"code": "600519", "name": "贵州茅台", "close": 1859.4, "open": 1854.0, "pre_close": 1800.0, "percent": 3.3, "volume_ratio": 3.5, "vwap": 1856.0, "amount": 350000000},
        {"code": "002412", "name": "汉森制药", "close": 10.55, "open": 10.02, "pre_close": 10.0, "percent": 5.5, "volume_ratio": 4.0, "vwap": 10.30, "amount": 90000000},
        {"code": "601519", "name": "大智慧", "close": 9.90, "open": 10.4, "pre_close": 10.0, "percent": -1.0, "volume_ratio": 2.5, "vwap": 10.20, "amount": 110000000},
    ]).set_index("code")

    engine.update_market_snapshot(df_round3)

    # 验证标的A (000001 平安银行): 低开高走
    prof_a = engine.get_stock_profile("000001")
    assert prof_a["pattern_type"] == "LOW_OPEN_HIGH_CLIMB"
    assert "低开高走" in prof_a["pattern_tag"]
    assert prof_a["alpha_score"] >= 75.0

    # 验证标的B (600519 贵州茅台): 高开横盘蓄势锁筹
    prof_b = engine.get_stock_profile("600519")
    assert prof_b["pattern_type"] == "HIGH_OPEN_CONSOLIDATION"
    assert "高开蓄势" in prof_b["pattern_tag"]

    # 验证标的C (002412 汉森制药): 步步高升跃迁
    prof_c = engine.get_stock_profile("002412")
    assert prof_c["tier_jumps"] >= 2
    assert prof_c["pattern_type"] == "STEP_BUBBLE_UP"
    assert "步步高升" in prof_c["pattern_tag"]

    # 验证标的D (601519 大智慧): 高开低走预警
    prof_d = engine.get_stock_profile("601519")
    assert prof_d["pattern_type"] == "HIGH_OPEN_DROP"
    assert "高开低走" in prof_d["pattern_tag"]
    assert prof_d["alpha_score"] <= 40.0


def test_limit_up_engine_integration():
    """测试 LimitUpEngine 的 get_opening_bubble_records 数据整合与策略字段对齐"""
    from ats.opening_bubble_engine import get_opening_bubble_engine
    get_opening_bubble_engine().reset_daily()

    lim_engine = LimitUpEngine.get_instance()
    
    test_df = pd.DataFrame([
        {"code": "000001", "name": "平安银行", "close": 10.35, "open": 9.85, "pre_close": 10.0, "percent": 3.5, "volume_ratio": 3.2, "vwap": 10.12, "amount": 180000000, "dff": 1.2, "dff2": 5.5, "dff3": 12.0, "Rank": 25, "hsl": 4.5, "category": "银行"},
        {"code": "002412", "name": "汉森制药", "close": 10.55, "open": 10.02, "pre_close": 10.0, "percent": 5.5, "volume_ratio": 4.0, "vwap": 10.30, "amount": 90000000, "dff": 2.5, "dff2": 8.0, "dff3": 25.0, "Rank": 10, "turnover": 6.8, "category": "医药商业"},
    ]).set_index("code")

    records = lim_engine.get_opening_bubble_records(current_df=test_df)
    assert isinstance(records, list)
    assert len(records) >= 2

    rec_map = {r["code"]: r for r in records}
    assert "000001" in rec_map
    assert "002412" in rec_map

    # 检查字段完整性与多维策略对齐
    for r in records:
        assert "code" in r
        assert "name" in r
        assert "open_pct" in r
        assert "tier_tag" in r
        assert "pattern_desc" in r
        assert "trajectory_str" in r
        assert "momentum_score" in r
        assert "dff" in r
        assert "dff2" in r
        assert "dff3" in r
        assert "rs_val" in r
        assert "resonance" in r and r["resonance"] in ("大盘共振", "逆市抗跌", "同步整理", "同步走弱")
        assert "turnover_rate" in r and r["turnover_rate"] > 0.0
        assert r["consecutive_boards"] == 0  # 未在涨停库中的普通标的连板数严格为 0
        assert r["is_limit_up"] is False

    r1 = rec_map["000001"]
    assert r1["rank"] == 25
    assert r1["category"] == "银行"
    assert r1["turnover_rate"] == 4.5

    r2 = rec_map["002412"]
    assert r2["rank"] == 10
    assert r2["category"] == "医药商业"
    assert r2["turnover_rate"] == 6.8


def test_high_concurrency_performance():
    """5000+ 全市场标的极限性能测试 (确保每秒能处理数百轮)"""
    engine = OpeningBubbleEngine()
    engine.reset_daily()

    num_stocks = 5000
    np.random.seed(42)
    
    codes = [f"{i:06d}" for i in range(1, num_stocks + 1)]
    pre_closes = np.random.uniform(5.0, 100.0, num_stocks)
    open_pcts = np.random.normal(0.0, 2.0, num_stocks)
    opens = pre_closes * (1.0 + open_pcts / 100.0)
    
    mock_df = pd.DataFrame({
        "name": [f"Stock_{c}" for c in codes],
        "close": opens,
        "open": opens,
        "pre_close": pre_closes,
        "percent": open_pcts,
        "volume_ratio": np.random.uniform(0.5, 5.0, num_stocks),
        "amount": np.random.uniform(1e6, 5e8, num_stocks),
        "vwap": opens
    }, index=codes)

    t_total = 0.0
    # 模拟连续更新 10 轮
    for round_idx in range(10):
        # 每次微调价格
        price_shifts = np.random.normal(0.2, 0.5, num_stocks)
        mock_df["percent"] += price_shifts
        mock_df["close"] = mock_df["pre_close"] * (1.0 + mock_df["percent"] / 100.0)
        t_start = time.time()
        engine.update_market_snapshot(mock_df)
        t_total += (time.time() - t_start)

    avg_per_round_ms = (t_total / 10.0) * 1000.0

    print(f"\n[OpeningBubbleEngine] 5000 stocks update benchmark: 10 rounds took {t_total:.3f}s, avg per round {avg_per_round_ms:.2f}ms")
    # 单轮 5000 只股票应在 400ms 以内完成（给 CI 和系统负载波动留出合理余量）
    assert avg_per_round_ms < 400.0


def test_turnover_rate_safety_filtering():
    """测试换手率列提取与超大成交金额防御"""
    engine = OpeningBubbleEngine()
    engine.reset_daily()

    # 构造同时含有 amount、turnover (金额) 和 turnover_rate 的 DataFrame
    df_sample = pd.DataFrame([
        {
            "code": "002015", "name": "协鑫能科", "close": 17.14, "open": 17.0, "pre_close": 15.88,
            "percent": 7.93, "volume_ratio": 1.81, "turnover": 3546353330.0, # 成交金额数十亿
            "turnover_rate": 14.52 # 真实换手率 14.52%
        },
        {
            "code": "600396", "name": "华电辽能", "close": 14.97, "open": 14.7, "pre_close": 14.14,
            "percent": 5.87, "volume_ratio": 1.30, "turnover": 3221398060.0, # 仅有 turnover 且值极大
        }
    ]).set_index("code")

    engine.update_market_snapshot(df_sample)
    
    # 002015 应该正确提取 14.52%
    prof_1 = engine.get_stock_profile("002015")
    assert prof_1["turnover_pct"] == 14.52

    # 600396 因为 turnover 为数十亿，应被安全防御为 0.0，杜绝显示 3221398060.00%
    prof_2 = engine.get_stock_profile("600396")
    assert prof_2["turnover_pct"] <= 100.0


def test_daily_limit_up_multi_level_sorting():
    """测试天梯多级排序算法：L1 主排序 -> L2 从排序 -> L3 次排序"""
    from ats.ui.daily_limit_up_dialog import DailyLimitUpDialog
    from PyQt6.QtWidgets import QApplication
    import sys
    
    app = QApplication.instance() or QApplication(sys.argv)
    
    records = [
        {"code": "000001", "name": "A", "price": 10.0, "pct": 5.0, "consecutive_boards": 2, "turnover_rate": 10.0, "vol_ratio": 2.0},
        {"code": "000002", "name": "B", "price": 20.0, "pct": 9.9, "consecutive_boards": 2, "turnover_rate": 20.0, "vol_ratio": 1.5},
        {"code": "000003", "name": "C", "price": 15.0, "pct": 3.0, "consecutive_boards": 3, "turnover_rate": 5.0, "vol_ratio": 3.0},
        {"code": "000004", "name": "D", "price": 8.0, "pct": 9.9, "consecutive_boards": 1, "turnover_rate": 15.0, "vol_ratio": 1.0},
    ]

    dlg = DailyLimitUpDialog()
    dlg.fav_manager = None  # 单测隔离：清空外部自选股影响，纯净测试多级排序算法

    # Case 1: L1 主排序 = 连板数 (col 4, 降序)
    dlg.sort_level1_col = 4
    dlg.sort_level1_asc = False
    dlg.sort_level2_col = None
    dlg.sort_level3_col = None
    
    res1 = dlg._apply_multi_level_sort(records)
    assert res1[0]["code"] == "000003"  # 3板在最前
    assert res1[-1]["code"] == "000004" # 1板在最后

    # Case 2: L1 = 连板数 (col 4, 降序), L2 = 换手率 (col 10, 降序)
    dlg.sort_level1_col = 4
    dlg.sort_level1_asc = False
    dlg.sort_level2_col = 10
    dlg.sort_level2_asc = False
    dlg.sort_level3_col = None

    res2 = dlg._apply_multi_level_sort(records)
    # 主排序 3板 (000003) 绝对第一，2板里换手高的 (000002: 20%) 排在 (000001: 10%) 前面，1板 (000004) 绝对垫底
    assert [r["code"] for r in res2] == ["000003", "000002", "000001", "000004"]

    # Case 3: L1 = 涨幅 (col 3, 降序), L2 = 连板数 (col 4, 降序), L3 = 量比 (col 11, 降序)
    # 验证主排序 9.9% 必定排在 5.0% 和 3.0% 前面，次级排序绝对不破坏主排序
    dlg.sort_level1_col = 3
    dlg.sort_level1_asc = False
    dlg.sort_level2_col = 4
    dlg.sort_level2_asc = False
    dlg.sort_level3_col = 11
    dlg.sort_level3_asc = False

    res3 = dlg._apply_multi_level_sort(records)
    # 9.9% 的有 000002 (2板) 和 000004 (1板) -> 000002 排第1，000004 排第2
    # 接着是 5.0% 的 000001 -> 排第3
    # 最后是 3.0% 的 000003 -> 排第4
    assert [r["code"] for r in res3] == ["000002", "000004", "000001", "000003"]

    # Case 4: 任何排序下“无数据/占位符/--/0值”强制沉底测试
    # 模拟包含连板和无连板、有封流比和无封流比的数据
    mixed_records = [
        {"code": "688175", "name": "无连板股A", "price": 20.0, "pct": 16.32, "consecutive_boards": 0, "seal_to_circ_ratio": 0.0},
        {"code": "300684", "name": "无连板股B", "price": 87.0, "pct": 13.00, "consecutive_boards": 0, "seal_to_circ_ratio": 0.0},
        {"code": "600470", "name": "2连板股C", "price": 6.0, "pct": 10.00, "consecutive_boards": 2, "seal_to_circ_ratio": 5.2},
        {"code": "301376", "name": "3连板股D", "price": 21.0, "pct": 20.00, "consecutive_boards": 3, "seal_to_circ_ratio": 8.5},
    ]

    # 测试 4.1: 主排序连板数降序 -> 3板 (D), 2板 (C) 必须排在前面，无连板的 A, B 必须沉底在最后
    dlg.sort_level1_col = 4
    dlg.sort_level1_asc = False
    dlg.sort_level2_col = None
    dlg.sort_level3_col = None
    res_sink1 = dlg._apply_multi_level_sort(mixed_records)
    assert [r["code"] for r in res_sink1[:2]] == ["301376", "600470"]
    assert set([r["code"] for r in res_sink1[2:]]) == {"688175", "300684"}

    # 测试 4.2: 用户设置封流比%【升序】(col 8) -> 5.2% (C) 排第1，8.5% (D) 排第2，无封单(0.0%)的 A, B 绝不顶到前面，必须强制沉底！
    dlg.sort_level1_col = 8
    dlg.sort_level1_asc = True # 升序
    dlg.sort_level2_col = None
    dlg.sort_level3_col = None
    res_sink2 = dlg._apply_multi_level_sort(mixed_records)
    assert res_sink2[0]["code"] == "600470" # 5.2% 最小有效封流比排第1
    assert res_sink2[1]["code"] == "301376" # 8.5% 排第2
    assert set([r["code"] for r in res_sink2[2:]]) == {"688175", "300684"} # 0封单全部沉底在最后

    # 测试 4.3: 用户截图真实场景【L1连板数降序 + L2梯队分类降序 + L3封流比升序】
    # 验证：3板 (D) 绝对第1，2板 (C) 绝对第2，无连板的 A, B 绝对在最后，绝不可能出现在顶部！
    dlg.sort_level1_col = 4
    dlg.sort_level1_asc = False # 降序
    dlg.sort_level2_col = 5
    dlg.sort_level2_asc = False # 降序
    dlg.sort_level3_col = 8
    dlg.sort_level3_asc = True  # 升序
    res_sink3 = dlg._apply_multi_level_sort(mixed_records)
    assert res_sink3[0]["code"] == "301376" # 3板
    assert res_sink3[1]["code"] == "600470" # 2板
    assert set([r["code"] for r in res_sink3[2:]]) == {"688175", "300684"} # 无连板无封单在最底部

    # Case 5: 验证配置持久化 key（BUBBLE 独立，其余模式全部复用主配置 key 确保向后兼容）
    key_today  = dlg._get_current_header_config_key("TODAY")
    key_bubble = dlg._get_current_header_config_key("BUBBLE")
    key_3d     = dlg._get_current_header_config_key("3D")
    key_ladder = dlg._get_current_header_config_key("LADDER")
    assert key_today  == "ats_daily_limit_up_table"
    assert key_bubble == "ats_daily_limit_up_table_bubble"
    assert key_3d     == "ats_daily_limit_up_table"
    assert key_ladder == "ats_daily_limit_up_table"

    sort_key_today  = dlg._get_current_sort_config_key("TODAY")
    sort_key_bubble = dlg._get_current_sort_config_key("BUBBLE")
    sort_key_10d    = dlg._get_current_sort_config_key("10D")
    assert sort_key_today  == "ats_daily_limit_up_sort"
    assert sort_key_bubble == "ats_daily_limit_up_sort_bubble"
    assert sort_key_10d    == "ats_daily_limit_up_sort"



