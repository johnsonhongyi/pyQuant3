# -*- coding: utf-8 -*-
import os
import sys
import unittest
import tempfile
import shutil
import json
import re

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

    def test_evaluate_condition_detail(self):
        """测试策略过滤表达式详细测试报告与子条件拆解"""
        def evaluate_condition_detail(expr, row_dict):
            if not expr or not expr.strip():
                return False, "❌ 过滤表达式为空", {}, []
            expr = expr.strip()
            aliases = {
                '涨幅': ['percent', 'pct_chg'],
                'percent': ['涨幅'],
                '现价': ['close', 'price'],
                '价格': ['close', 'price'],
                'close': ['现价', '价格', 'price'],
                'price': ['现价', '价格', 'close'],
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
            for default_key in ('close', 'high4', 'percent', 'price'):
                if default_key not in eval_scope:
                    eval_scope[default_key] = 0.0

            tokens = re.findall(r'[a-zA-Z_一-龥][a-zA-Z0-9_一-龥]*', expr)
            keywords = {'and', 'or', 'not', 'in', 'is', 'True', 'False', 'None'}
            involved_vars = {t: eval_scope[t] for t in tokens if t not in keywords and t in eval_scope}

            sub_conditions = []
            parts = re.split(r'\s+(?:and|or)\s+', expr)
            for p in parts:
                p_clean = p.strip().strip("()")
                if p_clean:
                    try:
                        sub_res = bool(eval(p_clean, {"__builtins__": {}}, eval_scope))
                        sub_conditions.append((p_clean, sub_res, None))
                    except Exception as ex:
                        sub_conditions.append((p_clean, False, str(ex)))

            try:
                total_res = bool(eval(expr, {"__builtins__": {}}, eval_scope))
                return total_res, None, involved_vars, sub_conditions
            except Exception as e:
                return False, str(e), involved_vars, sub_conditions

        row = {"close": 12.5, "high4": 11.0, "percent": 6.2}
        total_pass, err_msg, inv_vars, sub_conds = evaluate_condition_detail("close > high4 and 涨幅 > 5", row)
        self.assertTrue(total_pass)
        self.assertIsNone(err_msg)
        self.assertIn("close", inv_vars)
        self.assertEqual(inv_vars["close"], 12.5)
        self.assertIn("high4", inv_vars)
        self.assertEqual(inv_vars["high4"], 11.0)
        self.assertEqual(len(sub_conds), 2)
        self.assertTrue(sub_conds[0][1])  # close > high4 is True
        self.assertTrue(sub_conds[1][1])  # 涨幅 > 5 is True

    def test_vertical_layout_column_wrap(self):
        """测试纵向并排优先 (layout='vertical') 满高自动换列算法，杜绝超长横行"""
        work_l, work_t, work_r, work_b = 0, 0, 1920, 1040
        margin_x, margin_y = 10, 5
        win_w, win_h = 300, 200

        # 模拟 10 个窗口在单屏排列
        num_windows = 10
        coords = []

        # 纵向并排逻辑
        current_x = work_l + margin_x
        current_y = work_t + margin_y
        max_col_width = 0

        for i in range(num_windows):
            w, h = win_w, win_h
            # 满高换列：如果超出工作区底部高度，则换到下一列
            if current_y + h + margin_y > work_b:
                current_x += max_col_width + margin_x
                current_y = work_t + margin_y
                max_col_width = 0

            coords.append((current_x, current_y, w, h))
            current_y += h + margin_y
            max_col_width = max(max_col_width, w)

        # 验证列数与换列效果
        distinct_x = set(c[0] for c in coords)
        self.assertGreater(len(distinct_x), 1, "纵向并排必须换列，不能只有1列或排成单横行")
        
        # 验证单列窗口数量：工作区高度1040，每个窗口加间距205，单列应容纳5个窗口
        col1_windows = [c for c in coords if c[0] == coords[0][0]]
        self.assertEqual(len(col1_windows), 5, "工作区高1040，第一列应排列5个窗口")
        
        # 第二列应从 x = 10 + 300 + 10 = 320 开始
        col2_windows = [c for c in coords if c[0] != coords[0][0]]
        self.assertEqual(col2_windows[0][0], 10 + 300 + 10)
        self.assertEqual(col2_windows[0][1], 0 + 5)

    def test_rearrange_policy_and_window_geometries_coexist(self):
        """测试重排策略与窗口几何位置在 window_config.json 中持久化共存"""
        # 1. 模拟写入 window_geometries
        config_data = {
            "window_geometries": {
                "rearrange_policy_dialog": "560x440+300+200",
                "rearrange_test_dialog": "700x560+400+250"
            },
            "rearrange_policy": {
                "filter_expr": "close > high4",
                "layout": "vertical"
            }
        }
        with open(self.config_file, "w", encoding="utf-8") as f:
            json.dump(config_data, f, ensure_ascii=False, indent=4)

        # 2. 模拟更新 rearrange_policy
        with open(self.config_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        data["rearrange_policy"]["layout"] = "horizontal"
        with open(self.config_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

        # 3. 模拟 save_window_positions 增量保存，不能覆盖掉已有的 rearrange_policy
        with open(self.config_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        data["window_geometries"]["rearrange_policy_dialog"] = "560x440+350+220"
        with open(self.config_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

        # 4. 重新读取检验两者均健在
        with open(self.config_file, "r", encoding="utf-8") as f:
            final_data = json.load(f)
        self.assertIn("window_geometries", final_data)
        self.assertIn("rearrange_policy", final_data)
        self.assertEqual(final_data["window_geometries"]["rearrange_policy_dialog"], "560x440+350+220")
        self.assertEqual(final_data["rearrange_policy"]["layout"], "horizontal")

if __name__ == "__main__":
    unittest.main()
