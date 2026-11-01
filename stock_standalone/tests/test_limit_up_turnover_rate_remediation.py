# -*- coding: utf-8 -*-
"""
tests/test_limit_up_turnover_rate_remediation.py
专项回归测试：强势股天梯换手率提取与显示对齐龙头突击跟单榜规范

测试目标：
1. 当行情 DataFrame 中包含成交额字段 'turnover'（几亿大数）时，scan_limit_up_records_from_df
   严格提取真实换手率 ('turnover_rate', 'hsl', 'ratio')，坚决不取 'turnover'；
2. 量比 ('vol_ratio') 不会被换手率 ('ratio') 误污染；
3. 换手率超出 (0, 100] 区间或缺失时，安全归零并正确在看板中显示为 '--'，彻底根除大数省略号 Bug；
4. 排序逻辑对齐：合法换手率正常参与升降序，0.0 或 '--' 沉底。
"""

import pytest
import pandas as pd
from ats.limit_up_engine import LimitUpEngine, extract_turnover_rate, extract_vol_ratio
from ats.ui.daily_limit_up_dialog import DailyLimitUpDialog


def test_turnover_rate_extraction_ignores_amount_turnover():
    """测试行情数据中包含成交额 turnover (如 8.22 亿) 时，换手率必须正确提取为 ratio/turnover_rate，不能泄漏成交额"""
    engine = LimitUpEngine.get_instance()

    df = pd.DataFrame([
        {
            "code": "301520",
            "name": "万邦医药",
            "trade": 60.06,
            "close": 60.06,
            "percent": 20.00,
            "vol": 13600.0,
            "amount": 822522000.0,
            "turnover": 822522000.0,  # 新浪接口中 turnover 为成交额元
            "ratio": 43.54,            # 真实换手率 (%)
            "vol_ratio": 1.24,         # 真实量比
        },
        {
            "code": "601919",
            "name": "中远海控",
            "trade": 17.84,
            "close": 17.84,
            "percent": 7.02,
            "vol": 206000.0,
            "amount": 3680200000.0,
            "turnover": 3680200000.0,  # 成交额 36.8 亿
            "turnover_rate": 5.86,     # 真实换手率 (%)
            "vol_ratio": 1.79,
        }
    ])

    records = engine.scan_limit_up_records_from_df(df, fetch_l2_quotes=False)
    rec_map = {r["code"]: r for r in records}

    assert "301520" in rec_map
    wb = rec_map["301520"]
    # 换手率必须是 43.54%，绝不能是 822522000.0
    assert wb["turnover_rate"] == pytest.approx(43.54, 0.01)
    # 量比必须是 1.24，绝不能被 ratio (43.54) 覆盖
    assert wb["vol_ratio"] == pytest.approx(1.24, 0.01)

    assert "601919" in rec_map
    zy = rec_map["601919"]
    # 换手率必须是 5.86%，绝不能是 3680200000.0
    assert zy["turnover_rate"] == pytest.approx(5.86, 0.01)
    assert zy["vol_ratio"] == pytest.approx(1.79, 0.01)


def test_turnover_rate_fallback_protection_when_no_ratio_field():
    """测试若数据中只有成交额 turnover (如 9.11 亿) 且无换手率字段时，换手率必须安全置 0.0，不泄漏大数"""
    engine = LimitUpEngine.get_instance()

    df = pd.DataFrame([
        {
            "code": "600721",
            "name": "百花医药",
            "trade": 9.83,
            "close": 9.83,
            "percent": 9.96,
            "amount": 911678000.0,
            "turnover": 911678000.0,  # 仅有成交额，缺少换手率
            "vol_ratio": 1.33,
        }
    ])

    records = engine.scan_limit_up_records_from_df(df, fetch_l2_quotes=False)
    assert len(records) == 1
    bh = records[0]
    # 换手率安全归零，绝不允许大数泄漏
    assert bh["turnover_rate"] == 0.0
    assert bh["vol_ratio"] == pytest.approx(1.33, 0.01)


def test_extract_turnover_rate_and_vol_ratio_helper():
    """测试抽取函数对不同字段名和脏数据的鲁棒性"""
    # 1. 优先提取 turnover_rate
    assert extract_turnover_rate({"turnover_rate": 15.2, "ratio": 10.0, "turnover": 1e8}) == 15.2
    # 2. 回退到 ratio
    assert extract_turnover_rate({"ratio": 8.5, "turnover": 5e8}) == 8.5
    # 3. 回退到 hsl / turnoverratio
    assert extract_turnover_rate({"hsl": 6.3}) == 6.3
    assert extract_turnover_rate({"turnoverratio": 12.0}) == 12.0
    # 4. 只有 turnover (成交额) 时绝对不当作换手率
    assert extract_turnover_rate({"turnover": 882500000.0}) == 0.0
    # 5. 异常大数 (>100) 或负数安全归零
    assert extract_turnover_rate({"turnover_rate": 105.0}) == 0.0
    assert extract_turnover_rate({"turnover_rate": -1.5}) == 0.0

    # 量比提取测试
    assert extract_vol_ratio({"vol_ratio": 2.5, "ratio": 15.0}) == 2.5
    assert extract_vol_ratio({"volume_ratio": 1.8, "ratio": 8.0}) == 1.8
    # 只有 ratio 时不被误当量比，保持默认 1.0
    assert extract_vol_ratio({"ratio": 25.0}) == 1.0


def test_daily_limit_up_dialog_sorting_subkey():
    """测试 DailyLimitUpDialog 排序子键对有效换手率和异常沉底的处理"""
    # col_idx = 10 (换手%)
    mock_rec_valid = {"turnover_rate": 43.54}
    mock_rec_zero = {"turnover_rate": 0.0}
    mock_rec_leak = {"turnover": 911678000.0}  # 脏记录

    # 升序下有效换手率正常排序
    k_valid_asc = DailyLimitUpDialog._make_column_subkey(None, mock_rec_valid, 10, False)
    assert k_valid_asc == (0, 43.54)

    # 降序下有效换手率正常取负
    k_valid_desc = DailyLimitUpDialog._make_column_subkey(None, mock_rec_valid, 10, True)
    assert k_valid_desc == (0, -43.54)

    # 0.0 换手沉底 (标记为 1)
    k_zero = DailyLimitUpDialog._make_column_subkey(None, mock_rec_zero, 10, True)
    assert k_zero == (1, 0.0)

    # 脏记录（只有成交额 turnover）绝不被提取，沉底
    k_leak = DailyLimitUpDialog._make_column_subkey(None, mock_rec_leak, 10, True)
    assert k_leak == (1, 0.0)
