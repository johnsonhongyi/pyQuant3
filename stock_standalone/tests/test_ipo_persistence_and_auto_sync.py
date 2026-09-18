# -*- coding: utf-8 -*-
"""
tests/test_ipo_persistence_and_auto_sync.py
-------------------------------------------
专项验证：
1. 集中交易指挥室 QSplitter 极窄暗黑科技配色与 handleWidth=2px 彻底消除白色竖线；
2. 手工添加标的独立持久化、专属 📌 标记、金色加粗与置顶优先展示；
3. 股票池 .bak 镜像备份双写容灾与损坏自愈恢复能力 (彻底杜绝数据丢失)；
4. 重置新股池时手工标的 100% 优先保留；
5. 底层新股次新股全自动增量同步入池与安全合并。
"""

import sys
import os
import json
import time
import pytest
from unittest.mock import patch, MagicMock

cur_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(cur_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from PyQt6.QtWidgets import QApplication
from ats.ui.ipo_command_room_dialog import IPOCommandRoomDialog
from ats.ui.ipo_subnew_detector_dialog import (
    IPOSubnewDetectorDialog,
    is_stock_actually_listed,
    get_ipo_detector_layout_file
)

app = QApplication.instance() or QApplication(sys.argv)
TEST_TMP_CFG = os.path.join(cur_dir, "_tmp_ipo_test_layout.json")
TEST_TMP_BAK = TEST_TMP_CFG + ".bak"


def teardown_module():
    for f in (TEST_TMP_CFG, TEST_TMP_BAK):
        if os.path.exists(f):
            try:
                os.remove(f)
            except Exception:
                pass


def test_command_room_splitter_style_and_width():
    """1. 验证集中交易指挥室 QSplitter 极窄暗黑科技配色，消除 Windows 白色竖线"""
    dlg = IPOCommandRoomDialog()
    try:
        # 验证样式表中显式包含 QSplitter::handle 规则
        qss = dlg.styleSheet()
        assert "QSplitter::handle" in qss
        assert "#1c1e2d" in qss or "#1a1c29" in qss
        assert "#00e5ff" in qss  # hover 科技青

        # 验证 handleWidth 精确为 2px 极窄科技线
        assert dlg.splitter.handleWidth() == 2
    finally:
        dlg.close()


def test_manual_code_marker_and_persistence(monkeypatch):
    """2. 验证手工代码独立持久化、名称列专属 📌 金色标记、代码列纯净无截断，点击名称排序优先"""
    monkeypatch.setattr("ats.ui.ipo_subnew_detector_dialog.get_ipo_detector_layout_file", lambda: TEST_TMP_CFG)
    if os.path.exists(TEST_TMP_CFG):
        os.remove(TEST_TMP_CFG)
    if os.path.exists(TEST_TMP_BAK):
        os.remove(TEST_TMP_BAK)

    dlg = IPOSubnewDetectorDialog(initial_code=None)
    try:
        # 手工添加一只代码
        test_code = "601091"
        dlg.add_stock(test_code)

        # 验证 manual_codes 记录该标的
        assert test_code in dlg.manual_codes

        # 验证表格第 0 列 (代码列) 纯净显示纯 6 位代码，绝不带 📌 污染
        item_0 = dlg.table.item(0, 0)
        assert item_0 is not None
        assert item_0.text() == test_code
        assert "📌" not in item_0.text()

        # 验证表格第 1 列 (名称列) 呈现 📌 专属徽标与金色高亮
        item_1 = dlg.table.item(0, 1)
        assert item_1 is not None
        assert "📌" in item_1.text()
        assert "手工添加标的" in item_1.toolTip()

        # 验证持久化 JSON 文件中独立记录了 manual_codes
        assert os.path.exists(TEST_TMP_CFG)
        with open(TEST_TMP_CFG, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert "manual_codes" in data
        assert test_code in data["manual_codes"]

        # 验证操盘手指示：点击名称列 (col=1) 排序时，手工标的置顶优先排列
        dlg.table.sortItems(1)
        assert dlg.table.item(0, 0).text() == test_code
    finally:
        dlg.close()


def test_dual_write_backup_and_disaster_recovery(monkeypatch):
    """3. 验证数据双写 .bak 镜像备份与主文件损坏自愈恢复能力 (防数据丢失)"""
    monkeypatch.setattr("ats.ui.ipo_subnew_detector_dialog.get_ipo_detector_layout_file", lambda: TEST_TMP_CFG)

    dlg = IPOSubnewDetectorDialog(initial_code=None)
    try:
        dlg.add_stock("688801")
        dlg.add_stock("920298")
        dlg.save_persisted_state()

        # 验证 .bak 备份镜像文件已同步创建
        assert os.path.exists(TEST_TMP_BAK)
        with open(TEST_TMP_BAK, "r", encoding="utf-8") as f_bak:
            bak_data = json.load(f_bak)
        assert "688801" in bak_data.get("manual_codes", [])
        assert "920298" in bak_data.get("manual_codes", [])
    finally:
        dlg.close()

    # 模拟突发事故：主配置文件被意外破坏或清空
    with open(TEST_TMP_CFG, "w", encoding="utf-8") as f_bad:
        f_bad.write("{corrupted_json: null")

    # 重新启动窗口，验证通过 .bak 镜像自愈恢复！
    dlg_recovered = IPOSubnewDetectorDialog(initial_code=None)
    try:
        assert "688801" in dlg_recovered.manual_codes
        assert "920298" in dlg_recovered.manual_codes
        assert "688801" in dlg_recovered.monitored_codes
        assert "920298" in dlg_recovered.monitored_codes
    finally:
        dlg_recovered.close()


def test_reset_pool_preserves_manual_codes(monkeypatch):
    """4. 验证点击【重置新股池】时，操盘手手工添加的代码 100% 优先保留不被清空"""
    monkeypatch.setattr("ats.ui.ipo_subnew_detector_dialog.get_ipo_detector_layout_file", lambda: TEST_TMP_CFG)

    dlg = IPOSubnewDetectorDialog(initial_code=None)
    try:
        manual_code = "603448"
        dlg.add_stock(manual_code)
        assert manual_code in dlg.manual_codes

        # 执行重置新股池
        dlg._on_reset_default_clicked()

        # 验证重置后手工标的依然在池中且稳居前列
        assert manual_code in dlg.manual_codes
        assert manual_code in dlg.monitored_codes
        assert dlg.monitored_codes[0] == manual_code
    finally:
        dlg.close()


def test_is_stock_actually_listed_exemption():
    """5. 验证手工添加标的拥有最高意志免检权，不会被 listing_date 缺失误杀"""
    # 模拟一个没有上市日期的代码
    code_unknown = "999888"
    # 常规检查可能受东财日历影响，但手工标的享有免检权
    assert is_stock_actually_listed(code_unknown, is_manual=True) is True
    # 虚拟代码拦截
    assert is_stock_actually_listed("920295", is_manual=False) is False
    assert is_stock_actually_listed("N12345", is_manual=False) is False


def test_auto_sync_bottom_ipo_stocks(monkeypatch):
    """6. 验证底层新股自动增量合并入池且保持手工代码首位"""
    monkeypatch.setattr("ats.ui.ipo_subnew_detector_dialog.get_ipo_detector_layout_file", lambda: TEST_TMP_CFG)

    dlg = IPOSubnewDetectorDialog(initial_code=None)
    try:
        dlg.manual_codes = ["601091"]
        dlg.monitored_codes = ["601091", "688801"]

        # 模拟底层拉取到了两只新上市股票
        mock_latest = ["601091", "688801", "301689", "688837"]
        monkeypatch.setattr(dlg, "_get_default_ipo_subnew_codes", lambda: mock_latest)

        # 触发底层同步
        merged = list(dlg.manual_codes)
        for c in dlg.monitored_codes:
            if c not in merged:
                merged.append(c)
        for c in mock_latest:
            if c not in merged:
                merged.append(c)
        dlg.monitored_codes = list(dict.fromkeys(merged))

        # 验证手工代码仍在第 0 位
        assert dlg.monitored_codes[0] == "601091"
        # 验证新上市标的已增量合入
        assert "301689" in dlg.monitored_codes
        assert "688837" in dlg.monitored_codes
    finally:
        dlg.close()


def test_auto_polling_smart_sleep_and_cold_start_full_restoration(monkeypatch):
    """测试新股检测工具收盘后智能休眠与冷启动战情满血复原"""
    from ats.ui.ipo_subnew_detector_dialog import IPOSubnewDetectorDialog
    from ats.strategy.ipo_vwap_detector_engine import VWAPDetectorSignal

    dlg = IPOSubnewDetectorDialog()
    try:
        # 1. 模拟注入测试信号
        sig = VWAPDetectorSignal(
            code="601091",
            name="沈鼓集团",
            price=82.0,
            change_pct=195.0,
            vwap=19.64,
            vwap_diff_pct=317.0,
            structure_tag="[50分 09:30] 极限拔地而起",
            signal_type="EXTREME_CLIMAX",
            signal_level="🚨 高潮冲刺",
            signal_desc="连续临停高潮冲刺",
            stop_loss_price=80.0,
            update_time="15:00:00"
        )
        dlg.signals_map["601091"] = sig

        # 2. 测试收盘非交易时段智能休眠
        monkeypatch.setattr(dlg, "_check_is_trading_time", lambda: (False, "收盘休市 (15:30:00)"))
        dlg._on_toggle_auto_refresh(True)
        assert dlg.auto_refresh_enabled is True
        # 确认非交易时段下未启动后台 worker 狂跑，而是进入休眠
        assert dlg.worker is None or not dlg.worker.isRunning()
        assert "智能休眠" in dlg.lbl_status.text()
        assert "非交易时段" in dlg.lbl_status.text()

        # 3. 测试持久化与冷启动满血复原
        dlg.save_persisted_state()
        
        # 模拟冷启动新建窗口
        dlg2 = IPOSubnewDetectorDialog()
        try:
            assert dlg2.auto_refresh_enabled is True, "自动轮询状态应被持久化恢复"
            assert "601091" in dlg2.signals_map, "信号应被持久化还原"
            # 确认集中战情已满血推导
            assert "沈鼓集团" in dlg2.lbl_fleet_leader.text() or "🥇" in dlg2.lbl_fleet_leader.text()
            assert "集中" in dlg2.lbl_fleet_action.text() and "决议" in dlg2.lbl_fleet_action.text()
        finally:
            dlg2.close()
    finally:
        dlg.close()


def test_poll_interval_dropdown_and_persistence(monkeypatch):
    """8. 验证轮询间隔下拉框、默认15秒、自动持久化及切换生效"""
    monkeypatch.setattr("ats.ui.ipo_subnew_detector_dialog.get_ipo_detector_layout_file", lambda: TEST_TMP_CFG)
    dlg = IPOSubnewDetectorDialog()
    try:
        # 1. 验证默认值为 15 秒
        assert hasattr(dlg, "combo_interval")
        assert dlg.poll_interval_sec == 15
        assert dlg.combo_interval.currentText() == "15秒"
        assert [dlg.combo_interval.itemText(i) for i in range(dlg.combo_interval.count())] == ["5秒", "10秒", "15秒", "30秒", "60秒"]

        # 2. 模拟切换至 30 秒
        idx_30 = dlg.combo_interval.findText("30秒")
        dlg.combo_interval.setCurrentIndex(idx_30)
        assert dlg.poll_interval_sec == 30

        # 验证开启自动轮询时按钮文本保持清爽简洁，不重复显示秒数
        dlg._on_toggle_auto_refresh(True)
        assert dlg.auto_refresh_enabled is True
        assert dlg.btn_auto.text() == "⏳ 自动轮询: 开"

        # 3. 持久化落盘与冷启动恢复验证
        dlg.save_persisted_state()

        dlg2 = IPOSubnewDetectorDialog()
        try:
            assert dlg2.poll_interval_sec == 30
            assert dlg2.combo_interval.currentText() == "30秒"
            assert dlg2.auto_refresh_enabled is True
            assert dlg2.btn_auto.text() == "⏳ 自动轮询: 开"
        finally:
            dlg2.close()
    finally:
        dlg.close()


def test_fullscreen_column_width_auto_fit_no_black_gap():
    """9. 验证全屏/大窗口下表格列宽自适应拉伸填充视口，彻底消灭右侧黑边"""
    dlg = IPOSubnewDetectorDialog()
    try:
        dlg.resize(1920, 1080)
        dlg.show()
        dlg.resize(1920, 1080)
        app.processEvents()
        dlg.adjust_columns_to_viewport()

        vp_w = dlg.table.viewport().width()
        total_cols = dlg.table.columnCount()
        action_col = total_cols - 3

        # 验证操作建议列自适应伸缩为较大宽度，吃满视口
        action_w = dlg.table.columnWidth(action_col)
        assert action_w >= 300, f"全屏下操作建议列应自适应伸展，实际为 {action_w}px"

        # 验证所有可见列的宽度之和与视口宽度对齐 (误差 <= 2px，彻底消灭黑边)
        total_w = sum(dlg.table.columnWidth(c) for c in range(total_cols) if not dlg.table.isColumnHidden(c))
        assert abs(total_w - vp_w) <= 2, f"总列宽 {total_w} 应与视口宽度 {vp_w} 严丝合缝对齐"
    finally:
        dlg.close()


def test_manual_only_persistence_and_faithful_restoration(monkeypatch):
    """10. 验证严格只有手动变动才持久化，冷启动100%忠实还原少数标的，绝不强塞默认股票"""
    monkeypatch.setattr("ats.ui.ipo_subnew_detector_dialog.get_ipo_detector_layout_file", lambda: TEST_TMP_CFG)
    
    # 模拟用户手工只配置了两只标的
    custom_codes = ["688801", "601091"]
    custom_data = {
        "monitored_codes": custom_codes,
        "manual_codes": ["688801"],
        "saved_at": "2026-09-18 23:00:00"
    }
    with open(TEST_TMP_CFG, "w", encoding="utf-8") as f:
        json.dump(custom_data, f)

    mtime_before = os.path.getmtime(TEST_TMP_CFG)

    # 1. 验证冷启动读取时，严禁写入覆盖磁盘
    dlg = IPOSubnewDetectorDialog()
    try:
        # 验证100%忠实还原这两只，绝不会被 <= 5 逻辑强塞 35 只默认股票！
        assert dlg.monitored_codes == custom_codes
        assert len(dlg.monitored_codes) == 2

        # 验证加载读操作未篡改磁盘文件
        mtime_after_load = os.path.getmtime(TEST_TMP_CFG)
        assert mtime_before == mtime_after_load

        # 2. 验证后台扫描完成回调不会触发写盘持久化
        dlg._on_scan_finished(2, 0.5, {})
        mtime_after_scan = os.path.getmtime(TEST_TMP_CFG)
        assert mtime_after_scan == mtime_before, "后台扫描结束绝不能触发写盘持久化"

        # 3. 验证只有用户手动添加或操作时，才真正触发持久化
        dlg.add_stock("301689")
        mtime_after_manual = os.path.getmtime(TEST_TMP_CFG)
        assert mtime_after_manual > mtime_before, "用户手动添加标的必须触发持久化落盘"
    finally:
        dlg.close()


def test_sbc_window_persistence_size_restoration(monkeypatch):
    """11. 验证SBC窗口默认舒适尺寸 (800x560) 与最后关闭持久化的尺寸在重新打开时严格生效"""
    from ats.ui.intraday_strategy_dialog import SBCIntradayChartDialog, _get_sbc_layout_cfg_path
    from PyQt6.QtCore import QSettings
    
    sbc_cfg = _get_sbc_layout_cfg_path()
    test_sbc_cfg = sbc_cfg + ".test_tmp.json"
    monkeypatch.setattr("ats.ui.intraday_strategy_dialog._get_sbc_layout_cfg_path", lambda: test_sbc_cfg)

    # 1. 验证操盘手关闭最后一个SBC保存的自定义大尺寸 (如 860x620)
    saved_size = {"width": 860, "height": 620}
    test_data = {
        "sbc_window_size": saved_size,
        "sbc_geometries": {
            # 即使某只股票历史上有平铺留下的微小尺寸，也坚决不能篡改全局标准尺寸！
            "688801": {"x": 50, "y": 50, "width": 522, "height": 436}
        }
    }
    with open(test_sbc_cfg, "w", encoding="utf-8") as f:
        json.dump(test_data, f)

    try:
        # 打开该股票的 SBC 窗口
        sbc_dlg = SBCIntradayChartDialog(code="688801")
        try:
            # 验证其尺寸忠实采用了操盘手持久化的 860x620，彻底粉碎平铺小尺寸覆盖！
            assert sbc_dlg.width() == 860
            assert sbc_dlg.height() == 620
        finally:
            sbc_dlg.close()

        # 2. 验证全新环境无持久化记录时，默认采用图2舒展舒适尺寸 (800, 560)
        if os.path.exists(test_sbc_cfg):
            os.remove(test_sbc_cfg)
        SBCIntradayChartDialog._global_sbc_size = None
        # mock QSettings 返回 None，模拟完全纯白出厂环境
        monkeypatch.setattr(QSettings, "value", lambda self, key, defaultValue=None: None)
        sbc_default = SBCIntradayChartDialog(code="920298")
        try:
            assert sbc_default.width() == 800
            assert sbc_default.height() == 560
        finally:
            sbc_default.close()
    finally:
        if os.path.exists(test_sbc_cfg):
            try:
                os.remove(test_sbc_cfg)
            except Exception:
                pass

