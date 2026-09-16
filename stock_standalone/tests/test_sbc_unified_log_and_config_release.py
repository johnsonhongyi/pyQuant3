# -*- coding: utf-8 -*-
"""
tests/test_sbc_unified_log_and_config_release.py
-------------------------------------------------
验证三大核心功能：
1. vwap_trading_rules.json 自动释放与 get_app_root 打包环境路径自愈；
2. 高频 Tick 日志下沉至 debug 级别，消除控制台刷屏与货币符号异常；
3. SBC 数据日志窗口默认打开可见，当前实时阶段日志与 TDX 行情合二为一，严格执行 T+1 与单日防重叠开仓。
"""

import os
import sys
import unittest
import json
import logging
import pandas as pd

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from PyQt6.QtWidgets import QApplication
_app = QApplication.instance()
if _app is None:
    _app = QApplication(sys.argv)

from ats.vwap_rule_model import resolve_and_ensure_config_path, DEFAULT_CONFIG_PATH, VWAPRuleModel
from ats.consensus_arbiter import ConsensusArbiter, VoteResult
from ats.proactive_exit_engine import ProactiveExitEngine
from ats.ui.intraday_strategy_dialog import SBCIntradayChartDialog


class TestVWAPConfigAutoRelease(unittest.TestCase):
    """测试规则配置文件自动释放与物理根目录解析"""

    def test_config_path_resolved_and_valid(self):
        cfg_path = resolve_and_ensure_config_path()
        self.assertTrue(os.path.isabs(cfg_path), f"配置路径必须为绝对路径: {cfg_path}")
        self.assertTrue(os.path.exists(cfg_path), f"配置文件必须真实存在: {cfg_path}")
        self.assertGreater(os.path.getsize(cfg_path), 50, "配置文件大小必须大于50字节")

        # 验证 JSON 结构正确
        with open(cfg_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertIn("strategy_groups", data)
        self.assertIn("proactive_exit_rules", data)

    def test_rule_model_loads_without_warning(self):
        model = VWAPRuleModel()
        self.assertIsNotNone(model.conservative_config)
        self.assertGreater(len(model.aggressive_rules), 0)


class TestLoggerDebugModeAndYenClean(unittest.TestCase):
    """测试日志调整为 DEBUG 级别及货币符号彻底安全"""

    def test_proactive_exit_register_debug_and_no_yen(self):
        engine = ProactiveExitEngine()
        with self.assertLogs("ProactiveExitEngine", level="DEBUG") as cm:
            pos = engine.register_position("600733", 4.48, 100.0)
            self.assertIsNotNone(pos)
            # 必须包含在 debug 日志中，且绝不可含有 \xa5
            log_output = "\n".join(cm.output)
            self.assertIn("DEBUG", log_output)
            self.assertNotIn("\xa5", log_output)
            self.assertIn("元", log_output)

    def test_consensus_arbiter_debug_logs(self):
        arbiter = ConsensusArbiter()
        agg_vote = VoteResult(
            voter_group="aggressive",
            decision="APPROVE",
            proposed_size_pct=0.15,
            rule_id="test_breakout",
            rule_name="测试筑底突破",
            reason="测试动能成立"
        )
        con_vote = VoteResult(
            voter_group="conservative",
            decision="APPROVE",
            structure_clarity_score=75.0,
            is_hesitation_period=False,
            proposed_size_pct=0.15,
            rule_id="con_guard",
            rule_name="形态规整",
            reason="分时结构清晰"
        )
        with self.assertLogs("ConsensusArbiter", level="DEBUG") as cm:
            decision = arbiter.arbitrate_buy("600733", agg_vote, con_vote)
            self.assertTrue(decision.allow)
            log_output = "\n".join(cm.output)
            self.assertIn("DEBUG", log_output)
            self.assertIn("双组共识通过", log_output)


class TestSBCUnifiedRealtimeLog(unittest.TestCase):
    """测试 SBC 数据日志默认打开直接可见、合二为一显示并严控 T+1"""

    def setUp(self):
        self.dialog = SBCIntradayChartDialog(code="600733")

    def tearDown(self):
        self.dialog.close()

    def test_log_box_visible_by_default(self):
        """测试数据日志框默认直接可见（未被隐藏），操盘手打开无需额外点击"""
        self.assertFalse(self.dialog.log_box.isHidden(), "SBC 数据日志框默认必须未被隐藏（直接可见）！")

    def test_unified_realtime_log_content(self):
        """测试日志合二为一呈现 TDX 通道、量价基准、实时策略、T+1风控及防重复开仓"""
        df_mock = pd.DataFrame([
            {"open": 4.50, "high": 4.51, "low": 4.38, "close": 4.48, "vwap": 4.45, "vol": 1000},
            {"open": 4.48, "high": 4.50, "low": 4.44, "close": 4.48, "vwap": 4.45, "vol": 1200},
        ])
        sigs = [
            {
                "trade_id": 0,
                "action": "buy",
                "type": "buy",
                "price": 4.48,
                "time": "09:35",
                "date": "2026-09-16",
                "holding_status": "open_holding",
                "note": "买:4.48元 (底抬高企稳反转突破)"
            }
        ]
        self.dialog._update_unified_realtime_log(
            df_bars=df_mock,
            op=4.50,
            p=4.48,
            vw=4.45,
            hi=4.51,
            lo=4.38,
            to_rate=100.0,
            amt=278000000.0,
            sigs=sigs,
            mode="1m"
        )
        log_text = self.dialog.txt_log.toPlainText()
        self.assertIn("【TDX 通信通道】", log_text)
        self.assertIn("600733", log_text)
        self.assertIn("【实时量价基准】", log_text)
        self.assertIn("4.48元", log_text)
        self.assertIn("【实时策略研判】", log_text)
        self.assertIn("【持仓与T+1风控】", log_text)
        self.assertIn("严格执行 A股 T+1 制度", log_text)
        self.assertIn("【防重复买卖严控】", log_text)
        self.assertIn("单日限开仓1次", log_text)
        self.assertIn("【运行结论】", log_text)


if __name__ == "__main__":
    unittest.main()
