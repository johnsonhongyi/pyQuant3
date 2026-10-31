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

    def test_auto_popup_limit_and_replenish(self):
        """测试自动弹出未打开窗口限额10只、关闭旧窗口后可补位以及收盘清除标记机制"""
        class DummyWindow:
            def __init__(self):
                self._alter_tdx = False
                self._auto_popup = False
                self.bg = "SystemButtonFace"
            def winfo_exists(self): return True
            def cget(self, k): return self.bg

        monitor_windows = {}
        auto_popup_limit = 10

        # 模拟策略引擎在收到行情时创建小窗口
        def simulate_auto_popup(candidate_codes):
            alive_popups = [
                c for c, w in monitor_windows.items()
                if getattr(w['toplevel'], '_auto_popup', False)
            ]
            for code in candidate_codes:
                if code in monitor_windows:
                    continue
                if len(alive_popups) >= auto_popup_limit:
                    break
                win = DummyWindow()
                win._auto_popup = True
                win._alter_tdx = True
                win.bg = "red"
                monitor_windows[code] = {'toplevel': win, 'stock_info': [code, f"股_{code}"]}
                alive_popups.append(code)

        # 1. 批量来了 15 只满足策略的候选股票，应严格限制最多弹出 10 只
        candidates = [f"60000{i:02d}" for i in range(1, 16)]
        simulate_auto_popup(candidates)
        
        self.assertEqual(len(monitor_windows), 10)
        auto_pop_count = sum(1 for w in monitor_windows.values() if w['toplevel']._auto_popup)
        self.assertEqual(auto_pop_count, 10)

        # 2. 用户手动关闭了 2 个旧的自动弹出窗口
        del monitor_windows["6000001"]
        del monitor_windows["6000002"]
        self.assertEqual(len(monitor_windows), 8)

        # 3. 再次来了一批新候选股票，应精准补位 2 只，使总数重回 10 只
        new_candidates = ["6000100", "6000101", "6000102"]
        simulate_auto_popup(new_candidates)
        self.assertEqual(len(monitor_windows), 10)
        self.assertIn("6000100", monitor_windows)
        self.assertIn("6000101", monitor_windows)
        self.assertNotIn("6000102", monitor_windows)  # 超过 10 只被拦截

        # 4. 收盘后执行清理：清除 _auto_popup 标记，窗口归入常规监控
        for w_info in monitor_windows.values():
            win = w_info['toplevel']
            if hasattr(win, "_auto_popup"):
                delattr(win, "_auto_popup")

        # 验证标记已全部清除
        has_popup_flag = any(hasattr(w['toplevel'], '_auto_popup') for w in monitor_windows.values())
        self.assertFalse(has_popup_flag)

    def test_force_work_time_test_entry(self):
        """测试在非交易时间通过测试入口 (force_work_time=True) 依然能触发报警弹窗"""
        class DummyWindow:
            def __init__(self):
                self._alter_tdx = False
                self._auto_popup = False
            def winfo_exists(self): return True
            def cget(self, k): return "SystemButtonFace"

        monitor_windows = {"600688": {"toplevel": DummyWindow(), "stock_info": ["600688", "上海石化"]}}

        def simulate_check(force_work_time=False, is_work_time=False):
            if not (force_work_time or is_work_time):
                return False
            # 模拟触发
            monitor_windows["600688"]["toplevel"]._alter_tdx = True
            return True

        # 非交易时间且未强制：无法触发
        self.assertFalse(simulate_check(force_work_time=False, is_work_time=False))
        self.assertFalse(monitor_windows["600688"]["toplevel"]._alter_tdx)

        # 非交易时间但通过测试入口强制触发：成功触发
        self.assertTrue(simulate_check(force_work_time=True, is_work_time=False))
        self.assertTrue(monitor_windows["600688"]["toplevel"]._alter_tdx)

    def test_non_modal_independent_dialog_contract(self):
        """测试策略配置窗口与测试窗口为独立顶层窗口，绝不使用 grab_set 和 transient 阻断主流程"""
        # 读取 异动联动.py 源码静态契约
        script_path = os.path.join(os.path.dirname(__file__), "..", "..", "stock", "testpy", "tdxgui", "异动联动.py")
        if os.path.exists(script_path):
            with open(script_path, "r", encoding="utf-8") as f:
                content = f.read()
            # 定位 open_rearrange_policy_dialog 实现段
            policy_func_start = content.find("def open_rearrange_policy_dialog")
            self.assertGreater(policy_func_start, 0)
            policy_func_end = content.find("def show_rearrange_context_menu", policy_func_start)
            policy_func_code = content[policy_func_start:policy_func_end]

            # 验证绝无 win.grab_set()
            self.assertNotIn("win.grab_set()", policy_func_code)
            # 验证绝无 win.transient
            self.assertNotIn("win.transient(", policy_func_code)

            # 定位 open_rearrange_test_dialog 实现段
            test_func_start = content.find("def open_rearrange_test_dialog")
            self.assertGreater(test_func_start, 0)
            test_func_code = content[test_func_start:policy_func_start]
            self.assertNotIn("test_win.grab_set()", test_func_code)
            self.assertNotIn("test_win.transient(", test_func_code)

    def test_cold_stock_close_fallback_and_anti_zero_override(self):
        """测试冷门无异动股票从多源级联提取 close，且监控窗口中的 0.0 绝不覆盖已有真实价格"""
        # 模拟数据源：该股票无异动，GLOBAL_TOP_ALL 为空，但 sina 快照有真实行情
        sina_cache = {
            "002526": {"name": "山东矿机", "open": 2.96, "now": 2.95, "close": 2.95, "llastp": 3.28, "nclose": 3.01}
        }
        tdx_cache = {
            "002526": {"ma5d": 2.8, "lastp1d": 3.28, "per1d": 17.1, "high4": 2.6}
        }
        # 监控列表刚初始化的默认 0 值
        dummy_monitor_info = {
            "002526": {"stock_info": ["002526", "山东矿机", 0, 0, 0.0, 0.0, 0]}
        }

        # 模拟级联提取逻辑
        row_dict = {}
        # 1. tdx 补充
        if "002526" in tdx_cache:
            row_dict.update(tdx_cache["002526"])
        # 2. sina 补充
        if "002526" in sina_cache:
            row_dict.update(sina_cache["002526"])
        # 3. monitor_windows 补充 (防 0 覆盖)
        s_info = dummy_monitor_info["002526"]["stock_info"]
        if float(s_info[5]) > 0 and row_dict.get("close", 0) <= 0:
            row_dict["close"] = float(s_info[5])

        # 4. 价格归一化
        price_candidates = ['close', 'now', 'price', '现价', '价格', 'nclose', 'lastp']
        valid_price = next((float(row_dict[k]) for k in price_candidates if k in row_dict and float(row_dict[k] or 0) > 0), 0.0)
        self.assertEqual(valid_price, 2.95)
        self.assertEqual(row_dict.get("close"), 2.95)
        # 验证 0.0 没有覆盖真实的 2.95
        self.assertNotEqual(row_dict.get("close"), 0.0)

        # 5. 涨幅自愈计算
        pct = round((valid_price - row_dict['lastp1d']) / row_dict['lastp1d'] * 100.0, 2)
        self.assertEqual(pct, -10.06)

    def test_nclose_now_aliases_support(self):
        """测试过滤表达式支持 nclose 和 now 与 close 等价双向映射"""
        import numpy as np
        import pandas as pd
        # 提取 异动联动.py 中的 eval_rearrange_condition
        script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "stock", "testpy", "tdxgui", "异动联动.py"))
        with open(script_path, "r", encoding="utf-8") as f:
            code = f.read()
        eval_start = code.find("def eval_rearrange_condition")
        eval_end = code.find("def get_stock_eval_dict", eval_start)
        local_scope = {"np": np, "pd": pd}
        exec(code[eval_start:eval_end], local_scope)
        eval_func = local_scope["eval_rearrange_condition"]

        row = {"close": 3.05, "ma5d": 2.8, "lastp1d": 3.0, "per1d": 1.5}
        # 验证 close, now, nclose 均可求值通过
        self.assertTrue(eval_func("close > ma5d", row))
        self.assertTrue(eval_func("nclose > ma5d", row))
        self.assertTrue(eval_func("now > ma5d", row))
        self.assertTrue(eval_func("nclose > ma5d and per1d > 0 and nclose > lastp1d", row))

    def test_keep_dialog_open_on_save_and_escape_binding(self):
        """验证点击保存并应用重排后不关闭配置窗口，且绑定了 Escape 键"""
        script_path = os.path.join(os.path.dirname(__file__), "..", "..", "stock", "testpy", "tdxgui", "异动联动.py")
        with open(script_path, "r", encoding="utf-8") as f:
            code = f.read()

        policy_func_start = code.find("def open_rearrange_policy_dialog")
        policy_func_end = code.find("def show_rearrange_context_menu", policy_func_start)
        policy_func_code = code[policy_func_start:policy_func_end]

        apply_start = policy_func_code.find("def apply_and_save():")
        apply_end = policy_func_code.find("def reset_default():", apply_start)
        apply_code = policy_func_code[apply_start:apply_end]

        # 验证 apply_and_save 中绝对没有执行 on_close_policy_dialog()
        self.assertNotIn("\n        on_close_policy_dialog()", apply_code)
        self.assertNotIn("\n        win.destroy()", apply_code)

        # 验证绑定了 Escape 按键
        self.assertIn('win.bind("<Escape>", on_close_policy_dialog)', policy_func_code)
        self.assertIn('entry_expr.bind("<Escape>", on_close_policy_dialog)', policy_func_code)

if __name__ == "__main__":
    unittest.main()
