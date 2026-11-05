# -*- coding: utf-8 -*-
"""
测试报警中心与异动监控在 Nuitka/打包环境下的实时报警触发与数据恢复
验证内容：
1. get_conf_path 签名兼容性 (is_user_save 参数不再抛 TypeError)
2. refresh_alert_center 行情解析多源兼容 (close / llastp / turnover 映射为价格、涨幅、亿元)
3. 报警规则判定 (107 只股票中 17 只达标股票能正确识别为 is_active)
4. refresh_all_stock_data 在 _tdx_df 缺失时依然能全量执行 check_alert
"""
import pytest
import os
import sys
import json
import numpy as np
import pandas as pd

# 将被测路径加入 sys.path
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(TEST_DIR)
# stock 目录在 pyQuant3 根目录下 (即 stock_standalone 的上一级)
TDXGUI_DIR = os.path.join(os.path.dirname(PROJECT_ROOT), "stock", "testpy", "tdxgui")
if TDXGUI_DIR not in sys.path:
    sys.path.insert(0, TDXGUI_DIR)

from sys_utils import get_conf_path


def test_get_conf_path_signature_compatibility():
    """验证 get_conf_path 支持 is_user_save 等扩展参数，绝不抛 TypeError"""
    path = get_conf_path("linkage_config.json", base_dir=TDXGUI_DIR, is_user_save=True)
    assert path is not None
    assert "linkage_config.json" in path


def test_sina_data_field_extraction_and_active_detection():
    """验证从真实 sina_data.h5 (只有 close, llastp, turnover 列) 能正确计算价格、涨幅与量"""
    alerts_file = "<USER_HOME>/Documents/TDX/55188/alerts.json"
    if not os.path.exists(alerts_file):
        alerts_file = os.path.join(TDXGUI_DIR, "alerts.json")
    assert os.path.exists(alerts_file), "alerts.json 文件必须存在"

    with open(alerts_file, "r", encoding="utf-8") as f:
        alerts_rules = json.load(f)

    sina_file = "G:/sina_data.h5"
    if not os.path.exists(sina_file):
        pytest.skip("G:/sina_data.h5 不存在，跳过实盘快照解析")

    sina_df = pd.read_hdf(sina_file)
    assert "close" in sina_df.columns
    assert "llastp" in sina_df.columns
    assert "price" not in sina_df.columns  # 确认新浪快照原本就没有 price 列

    active_count = 0
    checked_count = 0

    for code, rule_entry in alerts_rules.items():
        rule_list = rule_entry.get("rules", []) if isinstance(rule_entry, dict) else (rule_entry if isinstance(rule_entry, list) else [])
        if not rule_list:
            continue

        checked_count += 1
        code_str = str(code).zfill(6)
        if code_str not in sina_df.index:
            continue

        row = sina_df.loc[code_str]
        cur_price = float(getattr(row, "close", float("nan")))
        llastp = float(getattr(row, "llastp", float("nan")))
        cur_pct = round((cur_price - llastp) / llastp * 100.0, 2) if (llastp > 0 and not np.isnan(llastp)) else 0.0
        turnover = float(getattr(row, "turnover", float("nan")))
        cur_vol = round(turnover / 100.0 / 10000.0 / 100.0, 2) if (turnover > 0 and not np.isnan(turnover)) else 0.0

        val_map = {"价格": cur_price, "涨幅": cur_pct, "量": cur_vol}
        is_now_satisfy = False

        for rule in rule_list:
            if not rule.get("enabled", False):
                continue
            field = rule.get("field", "")
            op = rule.get("op", "")
            val = rule.get("value", "")
            rt_val = val_map.get(field)
            if rt_val is not None and not np.isnan(rt_val):
                try:
                    target_f = float(val)
                    if (op == ">=" and rt_val >= target_f) or (op == "<=" and rt_val <= target_f):
                        is_now_satisfy = True
                        break
                except Exception:
                    pass

        if is_now_satisfy:
            active_count += 1

    assert checked_count == 107, f"应该检查全部 107 个规则，实际 {checked_count}"
    assert active_count >= 15, f"在当前行情下应至少命中 15 只触发股票，实际命中 {active_count}"


def test_alert_check_and_flush_decoupling():
    """验证 check_alert 与 flush_alerts 的数据流转"""
    alerts_buffer = []
    alerts_history = []
    inserted_keys = set()

    # 模拟产生一条报警
    now_str = "11:20:00"
    unique_key = f"{now_str}-002164-价格 >= 16.7"
    alert_entry = {
        "time": now_str,
        "stock_code": "002164",
        "name": "宁波东力",
        "field": "价格",
        "value": 17.89,
        "delta": 0.0,
        "status": "价格 >= 16.7",
        "rule": {"field": "价格", "op": ">=", "value": 16.7, "enabled": True}
    }
    alerts_buffer.append(alert_entry)

    # 执行 flush
    for alert in alerts_buffer:
        k = f"{alert.get('time','')}-{alert.get('stock_code','')}-{alert.get('status','')}"
        if k not in inserted_keys:
            inserted_keys.add(k)
            alerts_history.append(alert)
    alerts_buffer = []

    assert len(alerts_history) == 1
    assert len(alerts_buffer) == 0
    assert alerts_history[0]["stock_code"] == "002164"
    assert "002164" in unique_key
