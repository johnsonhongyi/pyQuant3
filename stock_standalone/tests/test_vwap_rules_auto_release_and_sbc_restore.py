# -*- coding: utf-8 -*-
"""
tests/test_vwap_rules_auto_release_and_sbc_restore.py
-----------------------------------------------------
专项测试：
1. 验证 vwap_trading_rules.json 在打包/外部环境中的智能升级释放、旧版自动备份与最新规则覆盖；
2. 验证所有 spec 打包配置文件均正确包含 ("config/vwap_trading_rules.json", "config")；
3. 验证 run_sbc.py / SBC 窗口体系在退出时自动持久化已打开的多窗口及设置，并支持启动时自动恢复。
"""

import os
import sys
import json
import shutil
import unittest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from PyQt6.QtWidgets import QApplication
_app = QApplication.instance()
if _app is None:
    _app = QApplication(sys.argv)

import ats.vwap_rule_model as vrm
from ats.ui.intraday_strategy_dialog import (
    SBCIntradayChartDialog,
    open_sbc_chart_dialog,
    save_all_open_sbc_windows,
    restore_all_open_sbc_windows,
    _get_sbc_layout_cfg_path
)


class TestVwapRulesAndSbcRestore(unittest.TestCase):
    """测试 vwap 规则自动热升级释放与 SBC 退出持久化恢复"""

    def test_spec_files_contain_vwap_rules(self):
        """验证所有主流打包 spec 配置文件均包含 vwap_trading_rules.json 数据文件打包装配项"""
        specs = [
            "instock_MonitorTK.spec",
            "instock_MonitorTK-ondir.spec",
            "instock_MonitorTK-setuptools.spec",
            "ats.spec",
            "MultiPeriodDialog.spec",
            "MultiPeriodTester.spec"
        ]
        for spec_name in specs:
            spec_path = os.path.join(_PROJECT_ROOT, spec_name)
            self.assertTrue(os.path.exists(spec_path), f"Spec 文件不存在: {spec_name}")
            with open(spec_path, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertIn(
                '("config/vwap_trading_rules.json", "config")',
                content,
                f"Spec 文件 {spec_name} 必须包含 config/vwap_trading_rules.json 数据装配项！"
            )

    def test_vwap_rules_auto_upgrade_and_backup(self):
        """验证外部若存在旧版本 (如 4KB/v2.1) 时，系统能自动备份旧文件并升级覆盖为最新的 v2.2 规则"""
        import tempfile
        with tempfile.TemporaryDirectory() as temp_dir:
            # 模拟外部应用程序目录
            mock_config_dir = os.path.join(temp_dir, "config")
            os.makedirs(mock_config_dir, exist_ok=True)
            mock_target = os.path.join(mock_config_dir, "vwap_trading_rules.json")

            # 模拟一个 4KB 的旧版本配置 (v2.1，缺少反转规则)
            old_data = {
                "version": "2.1",
                "hot_reload": True,
                "strategy_groups": {
                    "aggressive": {
                        "buy_rules": [
                            {"id": "buy_vwap_base_breakout", "name": "VWAP筑底突破"}
                        ]
                    }
                }
            }
            with open(mock_target, "w", encoding="utf-8") as f:
                json.dump(old_data, f, ensure_ascii=False, indent=2)

            # mock get_app_root 返回 mock 目录
            orig_get_app_root = vrm.get_app_root
            vrm.get_app_root = lambda: temp_dir
            try:
                res_path = vrm.resolve_and_ensure_config_path()
                self.assertEqual(os.path.normpath(res_path), os.path.normpath(mock_target))

                # 验证 mock_target 已经被自动热升级覆盖为最新版本
                with open(mock_target, "r", encoding="utf-8") as f:
                    new_data = json.load(f)
                self.assertEqual(new_data.get("version"), "2.2", "目标配置必须自动升级为最新 v2.2！")
                self.assertIn("buy_vwap_displacement_reversal", json.dumps(new_data), "目标配置必须包含底抬高反转突破新规则！")

                # 验证旧版本被自动备份
                bak_files = [f for f in os.listdir(mock_config_dir) if ".bak_v" in f]
                self.assertGreaterEqual(len(bak_files), 1, "必须生成旧配置备份文件！")
            finally:
                vrm.get_app_root = orig_get_app_root

    def test_sbc_save_and_restore_all_open_windows(self):
        """验证 SBC 多窗口体系在退出时自动保存窗口位置、周期与个性化设置，并能成功自动恢复"""
        # 1. 打开 2 个模拟 SBC 独立窗口
        dlg1 = open_sbc_chart_dialog(code="688826", period_mode="10d")
        dlg2 = open_sbc_chart_dialog(code="300672", period_mode="30m")

        self.assertIsNotNone(dlg1)
        self.assertIsNotNone(dlg2)

        dlg1.setGeometry(50, 50, 600, 400)
        dlg2.setGeometry(700, 50, 650, 420)

        if hasattr(dlg1, 'btn_auto_strategy'):
            dlg1.btn_auto_strategy.setChecked(True)
        if hasattr(dlg2, 'log_box'):
            dlg2.log_box.setVisible(False)

        # 2. 执行保存
        save_all_open_sbc_windows()

        # 校验布局文件
        cfg_path = _get_sbc_layout_cfg_path()
        self.assertTrue(os.path.exists(cfg_path))
        with open(cfg_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        sbc_windows = data.get("sbc_open_windows", [])
        saved_codes = [item.get("code") for item in sbc_windows]
        self.assertIn("688826", saved_codes)
        self.assertIn("300672", saved_codes)

        # 3. 模拟退出流程：设置 is_app_exiting 标志并关闭现有窗口
        _app.setProperty("is_app_exiting", True)
        try:
            dlg1.close()
            dlg2.close()
        finally:
            _app.setProperty("is_app_exiting", False)

        # 4. 执行自动恢复
        restored = restore_all_open_sbc_windows()
        try:
            self.assertGreaterEqual(len(restored), 2, "必须成功恢复至少 2 个窗口！")
            restored_codes = [getattr(d, "code", "") for d in restored]
            self.assertIn("688826", restored_codes)
            self.assertIn("300672", restored_codes)

            # 校验周期恢复
            target_dlg1 = next(d for d in restored if getattr(d, "code", "") == "688826")
            self.assertEqual(getattr(target_dlg1, "_current_period_mode", ""), "10d")

            target_dlg2 = next(d for d in restored if getattr(d, "code", "") == "300672")
            self.assertEqual(getattr(target_dlg2, "_current_period_mode", ""), "30m")
        finally:
            for d in restored:
                d.close()


if __name__ == "__main__":
    unittest.main()
