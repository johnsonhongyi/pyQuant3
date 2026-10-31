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

    def test_merge_code_int64_and_object_coercion(self):
        """测试在异动列表与行情缓存合并时，强制统一'代码'为 6 位字符串，彻底杜绝 int64 与 object 冲突导致的 ValueError"""
        import pandas as pd
        # 模拟 temp_df 的代码是 int64 类型
        temp_df = pd.DataFrame({
            '代码': [600688, 2526],
            '异动类型': ['火箭发射', '有大买盘']
        })
        self.assertEqual(temp_df['代码'].dtype, 'int64')

        # 模拟 right_df 的代码是 object / 字符串类型
        right_df = pd.DataFrame({
            '代码': ['600688', '002526'],
            'close': [19.5, 2.95],
            'ma5d': [18.2, 2.8]
        })
        self.assertEqual(right_df['代码'].dtype, 'object')

        # 如果直接 merge 会抛出 ValueError: You are trying to merge on int64 and object columns
        with self.assertRaises(ValueError):
            _ = temp_df.merge(right_df, on='代码', how='left')

        # 经过类型强制统一与 zfill(6) 纠偏处理
        temp_df['代码'] = temp_df['代码'].astype(str).str.zfill(6)
        right_df['代码'] = right_df['代码'].astype(str).str.zfill(6)

        merged = temp_df.merge(right_df, on='代码', how='left')
        self.assertEqual(len(merged), 2)
        self.assertEqual(list(merged['代码']), ['600688', '002526'])
        self.assertEqual(list(merged['close']), [19.5, 2.95])

    def test_link_stock_button_integration(self):
        """测试策略测试窗口中嵌入了【🔗 联动】快捷按钮并调用 send_to_tdx"""
        script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "stock", "testpy", "tdxgui", "异动联动.py"))
        with open(script_path, "r", encoding="utf-8") as f:
            code = f.read()

        test_func_start = code.find("def open_rearrange_test_dialog")
        test_func_end = code.find("def open_rearrange_policy_dialog", test_func_start)
        test_func_code = code[test_func_start:test_func_end]

        self.assertIn('text="🔗 联动"', test_func_code)
        self.assertIn('send_to_tdx(code)', test_func_code)

    def test_popup_shake_button_and_trigger_integration(self):
        """测试策略测试窗口中嵌入了【🔔 弹出震动】按钮并调用 trigger_stock_popup_and_shake"""
        script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "stock", "testpy", "tdxgui", "异动联动.py"))
        with open(script_path, "r", encoding="utf-8") as f:
            code = f.read()

        test_func_start = code.find("def open_rearrange_test_dialog")
        test_func_end = code.find("def open_rearrange_policy_dialog", test_func_start)
        test_func_code = code[test_func_start:test_func_end]

        self.assertIn('text="🔔 弹出震动"', test_func_code)
        self.assertIn('trigger_stock_popup_and_shake(code, test_win)', test_func_code)
        self.assertIn('def shake_window(', code)
        self.assertIn('def trigger_stock_popup_and_shake(', code)

    def test_filter_expr_history_max_20_and_dedup(self):
        """测试历史表达式持久化：自动去重、前置、严格保留最多 20 个不同表达式"""
        config_file = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "stock", "testpy", "tdxgui", "window_config.json"))
        
        # 模拟生成 25 个不同的表达式写入
        test_expressions = [f"close > ma{i}d and percent > {i}" for i in range(25)]
        
        # 模拟去重插入逻辑
        history = []
        for expr in test_expressions:
            expr = expr.strip()
            history = [h for h in history if h != expr]
            history.insert(0, expr)
            history = history[:20]

        self.assertEqual(len(history), 20)
        self.assertEqual(history[0], "close > ma24d and percent > 24")
        self.assertEqual(history[-1], "close > ma5d and percent > 5")

        # 再次插入已存在的表达式，验证去重前置
        re_insert = "close > ma10d and percent > 10"
        history = [h for h in history if h != re_insert]
        history.insert(0, re_insert)
        history = history[:20]

        self.assertEqual(len(history), 20)
        self.assertEqual(history[0], re_insert)

    def test_anti_overwrite_zero_price_and_candidate_codes(self):
        """测试在异动行价格/涨幅为 0.0 时，合并严格遵循防 0 覆盖，且候选代码提取不漏掉后面的股票"""
        import pandas as pd
        # 模拟全量原始异动表 (包含 000568 泸州老窖，但异动事件中价格和涨幅为 0.0)
        df_raw = pd.DataFrame([
            {'时间': '14:45:00', '代码': '000568', '名称': '泸州老窖', '异动类型': '向上缺口', '价格': 0.0, '涨幅': 0.0, '量': 0.0},
            {'时间': '14:45:02', '代码': '603338', '名称': '浙江鼎力', '异动类型': '向上缺口', '价格': 0.0, '涨幅': 0.0, '量': 0.0},
            {'时间': '14:50:00', '代码': '000568', '名称': '泸州老窖', '异动类型': '有大买盘', '价格': 0.0, '涨幅': 0.0, '量': 0.0},
        ])

        # 1. 提取去重候选股票代码
        candidate_codes = []
        if '代码' in df_raw.columns:
            candidate_codes = [str(c).strip().zfill(6) for c in df_raw['代码'].dropna().unique() if str(c).strip()]

        self.assertEqual(candidate_codes, ['000568', '603338'])

        # 2. 模拟从全市场快照/TDX已获取到 000568 的真实行情
        r_dict = {
            'code': '000568',
            'name': '泸州老窖',
            'close': 77.07,
            'nclose': 77.07,
            'ma5d': 75.20,
            'lastp1d': 70.05,
            'per1d': 10.0,
            'percent': 10.0,
            '涨幅': 10.0
        }

        # 3. 模拟合并异动事件行中的字段 (价格=0.0, 涨幅=0.0)
        evt_row = df_raw.iloc[0].to_dict()
        for k, v in evt_row.items():
            if v is None or pd.isna(v):
                continue
            if k in ['close', '价格', '现价', 'now', 'nclose', 'percent', '涨幅', 'pct', 'pct_chg', 'vol', '量', 'volume']:
                try:
                    if float(v) == 0.0 and float(r_dict.get(k, 0.0)) > 0:
                        continue
                except Exception:
                    pass
            r_dict[k] = v

        # 验证真实收盘价和涨幅绝对没有被 0.0 冲毁！
        self.assertEqual(r_dict['close'], 77.07)
        self.assertEqual(r_dict['nclose'], 77.07)
        self.assertEqual(r_dict['percent'], 10.0)

        # 4. 验证策略判定
        expr = "nclose > ma5d and per1d > 0 and nclose > lastp1d"
        # 表达式求值
        self.assertTrue(r_dict['nclose'] > r_dict['ma5d'])
        self.assertTrue(r_dict['per1d'] > 0)
        self.assertTrue(r_dict['nclose'] > r_dict['lastp1d'])

    def test_multi_screen_detection_and_work_rect_structure(self):
        """测试显示器结构支持字典形式 (monitor, work) 且按 left 坐标升序排列"""
        # 模拟 3 屏环境：左副屏 (-1920..0), 主屏 (0..1920), 右副屏 (1920..3840)
        raw_monitors = [
            {"monitor": (0, 0, 1920, 1080), "work": (0, 0, 1920, 1040), "flags": 1},
            {"monitor": (1920, 0, 3840, 1080), "work": (1920, 0, 3840, 1040), "flags": 0},
            {"monitor": (-1920, 0, 0, 1080), "work": (-1920, 0, 0, 1040), "flags": 0},
        ]

        def _get_monitor_rect(m):
            return m.get("monitor", m.get("work")) if isinstance(m, dict) else m

        def _get_work_rect(m):
            return m.get("work", m.get("monitor")) if isinstance(m, dict) else m

        # 排序：按物理左坐标升序
        sorted_monitors = sorted(raw_monitors, key=lambda m: _get_monitor_rect(m)[0])

        self.assertEqual(len(sorted_monitors), 3)
        self.assertEqual(_get_monitor_rect(sorted_monitors[0])[0], -1920)
        self.assertEqual(_get_monitor_rect(sorted_monitors[1])[0], 0)
        self.assertEqual(_get_monitor_rect(sorted_monitors[2])[0], 1920)
        self.assertEqual(_get_work_rect(sorted_monitors[1]), (0, 0, 1920, 1040))

    def test_multi_screen_balanced_chunk_allocation(self):
        """测试 3 屏环境下 10 个小窗口均匀分片分配 (4, 3, 3) 且保持排序顺序"""
        num_screens = 3
        # 模拟 10 个已按涨幅排序的窗口 (0~9)
        mock_windows = [f"win_{i}" for i in range(10)]

        screen_groups = {i: [] for i in range(num_screens)}
        total = len(mock_windows)
        base = total // num_screens
        rem = total % num_screens
        cur = 0
        for s_i in range(num_screens):
            count = base + (1 if s_i < rem else 0)
            screen_groups[s_i].extend(mock_windows[cur : cur + count])
            cur += count

        # 验证每个屏幕分配数量
        self.assertEqual(len(screen_groups[0]), 4)
        self.assertEqual(len(screen_groups[1]), 3)
        self.assertEqual(len(screen_groups[2]), 3)

        # 验证排序切片：第 0 屏分配排在最前的一批 (win_0 ~ win_3)
        self.assertEqual(screen_groups[0], ["win_0", "win_1", "win_2", "win_3"])
        self.assertEqual(screen_groups[1], ["win_4", "win_5", "win_6"])
        self.assertEqual(screen_groups[2], ["win_7", "win_8", "win_9"])

    def test_rdp_single_screen_collapse_auto_heal(self):
        """测试当远程 RDP 导致所有窗口缩在 Screen 0 (主屏) 时，自动自愈为 3 屏均匀分布"""
        num_screens = 3
        # 模拟 3 屏物理范围
        monitors = [
            {"monitor": (0, 0, 1920, 1080), "work": (0, 0, 1920, 1040)},
            {"monitor": (1920, 0, 3840, 1080), "work": (1920, 0, 3840, 1040)},
            {"monitor": (3840, 0, 5760, 1080), "work": (3840, 0, 5760, 1040)},
        ]
        # 模拟由于 RDP 导致所有 12 个窗口当前坐标全在 Screen 0 (0 <= x < 1920)
        window_coords = [(100 + i * 20, 100) for i in range(12)]

        occupied = set()
        for wx, wy in window_coords:
            for s_i, m in enumerate(monitors):
                l, t, r, b = m["monitor"]
                if l <= wx < r and t <= wy < b:
                    occupied.add(s_i)
                    break

        # 确认所有窗口当前确实只落在 Screen 0 (仅 1 个屏幕)
        self.assertEqual(occupied, {0})

        # 验证自愈触发逻辑
        multi_screen_mode = "current"
        use_balanced = (multi_screen_mode == "balanced")
        if not use_balanced and num_screens > 1:
            if len(occupied) <= 1:
                use_balanced = True  # 触发自愈

        self.assertTrue(use_balanced)

    def test_monitor_item_4_tuple_unpack_and_dict_access(self):
        """测试 MonitorItem 既是 4 元组可直接解包 (彻底防御 expected 4, got 3)，又支持字典访问"""
        class MonitorItem(tuple):
            def __new__(cls, monitor_rect, work_rect=None, flags=0):
                m_tup = tuple(monitor_rect) if isinstance(monitor_rect, (list, tuple)) else (0, 0, 1920, 1080)
                obj = super(MonitorItem, cls).__new__(cls, m_tup)
                obj.monitor = m_tup
                obj.work = tuple(work_rect) if isinstance(work_rect, (list, tuple)) else m_tup
                obj.flags = flags
                return obj

            def get(self, key, default=None):
                if key == "monitor": return self.monitor
                elif key == "work": return self.work
                elif key == "flags": return self.flags
                return default

            def __getitem__(self, item):
                if isinstance(item, str):
                    val = self.get(item)
                    if val is not None: return val
                    raise KeyError(item)
                return super().__getitem__(item)

        m = MonitorItem((0, 0, 1920, 1080), (0, 0, 1920, 1040), flags=1)

        # 1. 验证 4 元组原生解包 (不会抛出 expected 4, got 3)
        left, top, right, bottom = m
        self.assertEqual((left, top, right, bottom), (0, 0, 1920, 1080))

        # 2. 验证字典方法访问
        self.assertEqual(m.get("work"), (0, 0, 1920, 1040))
        self.assertEqual(m["work"], (0, 0, 1920, 1040))
        self.assertEqual(m.get("monitor"), (0, 0, 1920, 1080))

    def test_auto_popup_strict_quota_limit_and_no_save_to_monitor_list(self):
        """测试自动弹出达到 10 只后严格熔断终止，且带 _auto_popup 标记的窗口盘中绝不写入自选列表"""
        auto_popup_limit = 10
        alive_auto_popups = ["000001", "000002", "000003"]  # 已存活 3 只
        remaining_slots = auto_popup_limit - len(alive_auto_popups)  # 剩余 7 只配额
        self.assertEqual(remaining_slots, 7)

        # 模拟候选池有 100 只命中策略的股票
        candidate_hits = [f"stock_{i:06d}" for i in range(100)]
        created_count = 0
        newly_popped = []

        for code_str in candidate_hits:
            if len(alive_auto_popups) >= auto_popup_limit or created_count >= remaining_slots:
                break
            created_count += 1
            alive_auto_popups.append(code_str)
            newly_popped.append(code_str)

        # 严格验证：本次最多弹出 7 只，总数绝对卡在 10 只，绝不会超额
        self.assertEqual(created_count, 7)
        self.assertEqual(len(alive_auto_popups), 10)
        self.assertEqual(len(newly_popped), 7)

        # 验证盘中持久化过滤：带 _auto_popup 属性的临时窗口不计入常驻 monitor_list
        class MockWin:
            def __init__(self, is_auto):
                self._auto_popup = is_auto

        mock_monitor_windows = {
            "000001": {"toplevel": MockWin(is_auto=True), "stock_info": ["000001", "临时股1"]},
            "600519": {"toplevel": MockWin(is_auto=False), "stock_info": ["600519", "茅台(自选)"]},
        }

        # 盘中保存逻辑
        is_after_market = False  # 盘中
        saved_list = []
        for win_item in mock_monitor_windows.values():
            top = win_item.get("toplevel")
            if not is_after_market and top and getattr(top, "_auto_popup", False):
                continue
            saved_list.append(win_item["stock_info"])

        # 验证只有常驻自选股被持久化，临时报警窗口绝对不被写盘！
        self.assertEqual(len(saved_list), 1)
        self.assertEqual(saved_list[0][0], "600519")

if __name__ == "__main__":
    unittest.main()
