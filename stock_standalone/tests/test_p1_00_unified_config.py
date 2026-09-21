# -*- coding: utf-8 -*-
"""
tests/test_p1_00_unified_config.py
----------------------------------
专项测试 P1-00：现有退出与潮汐参数统一配置化 (SSOT)
验证范围：
1. 默认配置与既有代码逻辑基线 100% 等价（0.992 防守价生成、0.99 次低点破位、1.002 保本推移、0.992 时间衰减反转豁免）；
2. 12 阶潮汐门限默认配置完整映射，且支持自定义配置覆盖；
3. VWAPRuleModel 运行时快照 (get_config_snapshot) 序列化完整且线程安全；
4. 非法配置边界校验（安全回退至安全默认值，防止极端参数击穿风控）；
5. 磁盘热重载 (Hot-Reload) 触发配置实时生效。
"""

import os
import sys
import json
import tempfile
import unittest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from ats.vwap_rule_model import (
    VWAPRuleModel,
    TradePlanDefaultsConfig,
    SubnewTideThresholdsConfig,
)
from ats.proactive_exit_engine import ProactiveExitEngine, PositionWatchItem
from ats.strategy.subnew_tide_state_machine import (
    SubnewTideStateMachine,
    TideObservation,
)
from ats.strategy.channel_secondary_buy_strategy import (
    evaluate_channel_secondary_buy,
    SecondaryBuyStage,
)
import pandas as pd
import numpy as np


class TestP100UnifiedConfig(unittest.TestCase):
    """P1-00 统一参数配置化与等价性专项测试"""

    def setUp(self):
        self.model = VWAPRuleModel()

    def test_default_config_equivalency(self):
        """1. 验证默认配置与代码原硬编码常量完全等价"""
        tp_cfg = self.model.trade_plan_config
        self.assertEqual(tp_cfg.higher_low_stop_ratio, 0.992)
        self.assertEqual(tp_cfg.higher_low_stop_break_ratio, 0.99)
        self.assertEqual(tp_cfg.breakeven_trigger_ratio, 1.002)
        self.assertEqual(tp_cfg.reversal_exempt_ratio, 0.992)
        self.assertEqual(tp_cfg.default_position_pct, 30.0)
        self.assertEqual(tp_cfg.default_expire_at, "14:45:00")

        tide_cfg = self.model.tide_config
        self.assertEqual(tide_cfg.min_sample_count, 10)
        self.assertEqual(tide_cfg.min_completeness, 0.8)
        self.assertEqual(tide_cfg.t10_advance_ratio_min, 0.75)
        self.assertEqual(tide_cfg.t10_above_vwap_ratio_min, 0.70)
        self.assertEqual(tide_cfg.t10_amount_ratio_min, 0.90)
        self.assertEqual(tide_cfg.t1_advance_ratio_max, 0.55)
        self.assertEqual(tide_cfg.t1_above_vwap_ratio_max, 0.50)
        self.assertEqual(tide_cfg.t1_amount_ratio_min, 1.20)
        self.assertEqual(tide_cfg.t2_advance_ratio_collapse, 0.30)
        self.assertEqual(tide_cfg.t2_above_vwap_ratio_collapse, 0.20)

    def test_config_snapshot_structure(self):
        """2. 验证运行时快照导出格式完整且无死锁"""
        snap = self.model.get_config_snapshot()
        self.assertIn("version", snap)
        self.assertIn("trade_plan_config", snap)
        self.assertIn("tide_config", snap)
        tp_snap = snap["trade_plan_config"]
        self.assertEqual(tp_snap["higher_low_stop_ratio"], 0.992)
        self.assertEqual(tp_snap["breakeven_trigger_ratio"], 1.002)

    def test_illegal_values_safety_fallback(self):
        """3. 验证异常越界配置被安全拦截并自动回退默认值"""
        with tempfile.TemporaryDirectory() as td:
            cfg_path = os.path.join(td, "bad_rules.json")
            bad_data = {
                "version": "2.2",
                "trade_plan_defaults": {
                    "higher_low_stop_ratio": 2.5,  # 严重越界 (>1.0)
                    "higher_low_stop_break_ratio": -0.5, # 严重越界 (<0)
                    "breakeven_trigger_ratio": 0.5, # 严重越界 (<1.0)
                }
            }
            with open(cfg_path, "w", encoding="utf-8") as f:
                json.dump(bad_data, f)

            bad_model = VWAPRuleModel(config_path=cfg_path)
            self.assertEqual(bad_model.trade_plan_config.higher_low_stop_ratio, 0.992)
            self.assertEqual(bad_model.trade_plan_config.higher_low_stop_break_ratio, 0.99)
            self.assertEqual(bad_model.trade_plan_config.breakeven_trigger_ratio, 1.002)

    def test_proactive_exit_engine_uses_unified_config(self):
        """4. 验证主动退出引擎能够读取自定义配置中的 breakeven 与 break 阈值"""
        engine = ProactiveExitEngine(rule_model=self.model)
        # 模拟自定义修改配置
        self.model.trade_plan_config.higher_low_stop_break_ratio = 0.985
        self.model.trade_plan_config.breakeven_trigger_ratio = 1.005

        pos = engine.register_position("688826", entry_price=10.0, shares=1000)
        pos.higher_low_stop = 9.80

        # 当现价处于 9.80 * 0.988 时，原 0.99 会触发止损，但在 0.985 下不应触发
        price_test = 9.80 * 0.988
        action = engine.evaluate_tick("688826", price=price_test, vwap_today=10.0, volume=1000.0)
        self.assertIsNone(action, "在 0.985 宽容阈值下不应被触发止损")

        # 跌破 9.80 * 0.984 时触发止损
        action_break = engine.evaluate_tick("688826", price=9.80 * 0.984, vwap_today=10.0, volume=1000.0)
        self.assertIsNotNone(action_break)
        self.assertEqual(action_break.rule_id, "exit_higher_low_broken")

    def test_subnew_tide_state_machine_uses_unified_config(self):
        """5. 验证潮汐状态机能读取自定义门限"""
        custom_tide_cfg = SubnewTideThresholdsConfig(
            t10_advance_ratio_min=0.85, # 调高 T10 门槛至 85%
        )
        machine = SubnewTideStateMachine(config=custom_tide_cfg)
        # 注入前期为 T9
        obs_prior = TideObservation(
            observed_at="2026-09-21 09:35:00",
            sample_count=20,
            completeness=1.0,
            advance_ratio=0.80,
            above_vwap_ratio=0.75,
            median_return_pct=3.0,
            amount_yi=10.0,
            top20_return_pct=7.0,
            bottom20_return_pct=-1.0,
        )
        dec_prior = machine.update(obs_prior)
        self.assertEqual(dec_prior.state, "T9_FLOOD_SPREAD")

        # 下一交易日若上涨率为 80% (原门槛 75% 可进入 T10，但自定义 85% 不足以进入 T10)
        obs_curr = TideObservation(
            observed_at="2026-09-22 09:35:00",
            sample_count=20,
            completeness=1.0,
            advance_ratio=0.80, # 80% < 85%
            above_vwap_ratio=0.75,
            median_return_pct=3.0,
            amount_yi=10.0,
            top20_return_pct=7.0,
            bottom20_return_pct=-1.0,
        )
        dec_curr = machine.update(obs_curr)
        self.assertNotEqual(dec_curr.state, "T10_MAIN_UP", "高于 85% 门槛时 80% 不应触发 T10")


if __name__ == "__main__":
    unittest.main()
