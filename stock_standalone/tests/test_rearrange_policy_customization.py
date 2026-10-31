# -*- coding: utf-8 -*-
import os
import sys
import unittest
import tempfile
import shutil
import json

class TestRearrangePolicyCustomization(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.config_file = os.path.join(self.test_dir, "window_config.json")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_eval_rearrange_condition(self):
        """测试策略过滤表达式的安全求值与中英文双向映射"""
        def eval_rearrange_condition(expr, row_dict):
            if not expr or not expr.strip():
                return False
            expr = expr.strip()
            aliases = {
                '涨幅': ['percent', 'pct_chg'],
                'percent': ['涨幅'],
                '现价': ['close', 'price'],
                '价格': ['close', 'price'],
                'close': ['现价', '价格', 'price'],
                'price': ['现价', '价格', 'close'],
                '量': ['vol', 'volume'],
                '成交量': ['vol', 'volume'],
                'vol': ['量', '成交量', 'volume'],
                'volume': ['量', '成交量', 'vol'],
                'high4': ['前高4', 'h4'],
            }
            eval_scope = {}
            for k, v in row_dict.items():
                if v is not None:
                    eval_scope[str(k)] = v
                    if k in aliases:
                        for target_alias in aliases[k]:
                            if target_alias not in eval_scope:
                                eval_scope[target_alias] = v
            for default_key in ('close', 'high4', 'percent', 'price', 'vol', 'dff', 'dff2', 'rank', '涨幅', '现价', '价格', '量', '成交量'):
                if default_key not in eval_scope:
                    eval_scope[default_key] = 0.0

            try:
                return bool(eval(expr, {"__builtins__": {}}, eval_scope))
            except Exception:
                return False

        row1 = {"close": 15.6, "high4": 14.8, "percent": 5.4, "vol": 1200}
        self.assertTrue(eval_rearrange_condition("close > high4", row1))
        self.assertTrue(eval_rearrange_condition("涨幅 > 5", row1))
        self.assertTrue(eval_rearrange_condition("close > high4 and 涨幅 > 3", row1))
        self.assertFalse(eval_rearrange_condition("涨幅 > 6", row1))
        self.assertFalse(eval_rearrange_condition("close < high4", row1))

        # 中文 key 同样支持英文表达式
        row2 = {"现价": 18.0, "前高4": 15.0, "涨幅": 8.0}
        self.assertTrue(eval_rearrange_condition("close > 16", row2))
        self.assertTrue(eval_rearrange_condition("percent > 7", row2))

    def test_rearrange_policy_persistence(self):
        """测试重排策略自定义与自动持久化"""
        DEFAULT_REARRANGE_POLICY = {
            "filter_expr": "close > high4",
            "filter_enabled": True,
            "sort_by": "create_time",
            "sort_reverse": True,
            "align": "left",
            "layout": "horizontal",
            "action_alter": "bottom_right_red"
        }

        def load_policy(cfg_path):
            policy = DEFAULT_REARRANGE_POLICY.copy()
            if os.path.exists(cfg_path):
                with open(cfg_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if "rearrange_policy" in data:
                    policy.update(data["rearrange_policy"])
            return policy

        def save_policy(cfg_path, policy):
            data = {}
            if os.path.exists(cfg_path):
                with open(cfg_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            data["rearrange_policy"] = policy
            with open(cfg_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)

        # 1. 默认加载
        p1 = load_policy(self.config_file)
        self.assertEqual(p1["filter_expr"], "close > high4")

        # 2. 修改并持久化
        p1["filter_expr"] = "涨幅 > 3 and close > high4"
        p1["sort_by"] = "percent"
        p1["layout"] = "vertical"
        save_policy(self.config_file, p1)

        # 3. 重新加载验证
        p2 = load_policy(self.config_file)
        self.assertEqual(p2["filter_expr"], "涨幅 > 3 and close > high4")
        self.assertEqual(p2["sort_by"], "percent")
        self.assertEqual(p2["layout"], "vertical")

if __name__ == "__main__":
    unittest.main()
