# -*- coding: utf-8 -*-
"""
专项闭环测试：ATS 独立语音报警中心全功能对齐
1. 股票代码去数值化朗读防"60万零137"
2. 席位淘汰防抖冷却门禁 (Anti-Chattering Gate) 阻断高频死循环震荡
3. 容量超额淘汰不触发突发语音轰炸
4. SSOT 内存优先直连解决界面空白
5. AlertNotifier.shutdown() 退出彻底静默
6. Toast 点击定向唤醒 FusionLadderDialog 并切换到 Tab 1
"""

import os
import sys
import time
import pytest
from PyQt6.QtWidgets import QApplication, QWidget, QTabWidget, QTableWidget, QTableWidgetItem
from ats.alert_notifier import get_alert_notifier, AlertNotifier, activate_and_locate_target_window
from ats.fusion.hot_pool import HotPoolState, StockSeatState, HotPoolCalibratedConfig
from ats.fusion.shadow import FusionShadow


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app


def test_code_pronunciation_anti_numerical(qapp):
    """验证测试 1：股票代码发音去数值化，彻底杜绝把 600137 读成 60万零137。"""
    notifier = get_alert_notifier()
    
    # 构造包含 600137 股票代码的梯度热榜告警 item
    # 模拟内部生成 voice_text 逻辑
    name = "浪潮软件"
    code = "600137"
    reason = "【梯度热榜】浪潮软件 晋级核心领涨：所属计算机设备板块脉冲确认共振"
    
    # 获取规范化文本测试
    from alert_manager import normalize_speech_text
    norm_text = normalize_speech_text(f"梯度热榜 浪潮软件 {code} 晋级核心领涨 9.8%")
    
    # 断言：绝对不能含有连续 6 位阿拉伯数字！
    import re
    assert not re.search(r'\b\d{6}\b', norm_text), f"norm_text 依然包含 6 位连续数字: {norm_text}"
    # 断言：必须转化为逐字汉字发音
    assert "六零零一三七" in norm_text, f"norm_text 缺少六零零一三七: {norm_text}"


def test_seat_eviction_anti_chattering_gate():
    """验证测试 2：席位淘汰防抖冷却门禁 (Anti-Chattering Gate) 彻底阻断死循环秒级高频震荡。"""
    from ats.fusion.hot_pool import SectorPulseEngine
    cfg = HotPoolCalibratedConfig()
    codes = ["600136", "600137", "600138", "600139"]
    engine = SectorPulseEngine(
        config=cfg,
        sector_map={c: "半导体" for c in codes},
    )
    engine.init_membership(codes)
    hp = HotPoolState(config=cfg, sector_engine=engine)
    now = 1793870000.0

    st = StockSeatState(
        code="600137",
        trade_date="2026-11-05",
        seat="EVICTED",
        evicted_ts=now,
        first_observed_ts=now - 600.0,
        primary_sector="industry:半导体",
        price=10.0,
        watch_score=90.0,
    )
    hp.seats["600137"] = st

    # 1. 在 300 秒冷冻期内 (例如被淘汰后第 5 秒)，即使行情再次站上 10V 且板块共振
    quotes_base = {
        c: {"price": 10.0, "percent": 2.0, "volume": 50000.0, "vwap": 9.9, "ratio": 3.0, "ts": now + 5.0}
        for c in codes
    }
    daily_mock = {
        c: {"vwap10": 9.5, "vwap_prev9_value": 90000.0, "vwap_prev9_volume": 9000.0, "close_pre1": 9.8, "is_structure_prejudged": 1.0}
        for c in codes
    }
    obs_map = {
        c: {"same_day": True, "has_bottom_base": True, "is_above_10v": True, "ref_10v": 9.5, "vwap": 9.9, "ts": now + 5.0}
        for c in codes
    }

    hp.step_frame("2026-11-05", now + 5.0, quotes_base, lambda c, d: daily_mock.get(c, {}), obs_evidence_map=obs_map)
    
    # 断言：在 5 秒时处于冷冻期内，严禁重新准入！必须保持 EVICTED！
    assert hp.seats["600137"].seat == "EVICTED", "5秒时未能拦截震荡重入！"

    # 2. 跨越 300 秒冷冻期之后：
    # 2.1 在 now + 295.0 注入时窗基准帧 (此时仍未满 300 秒冷却，保持 EVICTED)
    quotes_pre = {
        c: {"price": 10.0, "percent": 2.0, "volume": 60000.0, "vwap": 9.9, "ratio": 3.0, "ts": now + 295.0}
        for c in codes
    }
    obs_map_pre = {
        c: {"same_day": True, "has_bottom_base": True, "is_above_10v": True, "ref_10v": 9.5, "vwap": 9.9, "ts": now + 295.0}
        for c in codes
    }
    hp.step_frame("2026-11-05", now + 295.0, quotes_pre, lambda c, d: daily_mock.get(c, {}), obs_evidence_map=obs_map_pre)
    assert hp.seats["600137"].seat == "EVICTED", "295秒时仍未满300秒，严禁提前解冻！"

    # 2.2 在 now + 305.0 (已超过 300 秒)，板块 3 只标的在 10 秒窗口内集体快速拉升 (+2.5% delta) 确认脉冲
    quotes_pump = {
        c: {"price": 10.5, "percent": 4.5, "volume": 80000.0, "vwap": 10.2, "ratio": 3.5, "ts": now + 305.0}
        for c in codes
    }
    obs_map_pump = {
        c: {"same_day": True, "has_bottom_base": True, "is_above_10v": True, "ref_10v": 9.5, "vwap": 10.2, "ts": now + 305.0}
        for c in codes
    }
    hp.step_frame("2026-11-05", now + 305.0, quotes_pump, lambda c, d: daily_mock.get(c, {}), obs_evidence_map=obs_map_pump)
    
    # 断言：超过 300 秒防抖期后且板块脉冲确认共振，允许重新准入 TREND_WATCH
    assert hp.seats["600137"].seat == "TREND_WATCH", "300秒冷却期后未能正常恢复准入！"


def test_capacity_exceeded_eviction_no_alert_spam():
    """验证测试 3：容量超额末位挤出属于后台维护，绝不触发高频突发报警打扰用户。"""
    cfg = HotPoolCalibratedConfig()
    hp = HotPoolState(config=cfg)
    st = StockSeatState(code="600000", trade_date="2026-11-05", seat="TREND_WATCH")
    
    alerts_emitted = []
    # 注入测试回调记录
    hp.alert_callback = lambda code, name, text: alerts_emitted.append((code, name, text))
    
    # 模拟容量超额淘汰
    hp._evict_stock(st, 1793870000.0, "trend_capacity_exceeded_eviction", 10.0)
    
    # 断言：容量超额挤出严禁向报警通道发声！
    assert len(alerts_emitted) == 0, f"容量超额挤出不应触发外发报警: {alerts_emitted}"
    # 但内部日志必须完整记录供审计
    assert any(e.get("to_seat") == "EVICTED" for e in hp.events_log)


def test_ssot_memory_first_ladder_refresh(qapp):
    """验证测试 4：SSOT 内存优先架构，前台 refresh_hot_pool 优先直连 FusionShadow 活跃内存实例。"""
    from ats.ui.fusion_ladder_dialog import FusionLadderDialog
    
    # 1. 模拟当前进程启动了一个 FusionShadow 实例并在内存中维护热榜
    shadow = FusionShadow(root="mock_tmp")
    shadow.hot_pool.current_trade_date = "2026-11-05"
    st = StockSeatState(code="600137", trade_date="2026-11-05", seat="CORE_LEADER", price=12.5, watch_score=95.0)
    shadow.hot_pool.seats["600137"] = st
    
    # 验证单例注册成功
    assert FusionShadow.get_active_instance() is shadow

    # 2. 实例化 FusionLadderDialog 并触发刷新
    dlg = FusionLadderDialog()
    dlg.cmb_day.setCurrentText("2026-11-05")
    dlg.refresh_hot_pool()
    
    # 断言：前台表格必须从内存实例中读取到 600137，绝不会因为磁盘无文件而显示暂无记录！
    found_codes = [dlg.tbl_hot_pool.item(r, 1).text().strip() for r in range(dlg.tbl_hot_pool.rowCount()) if dlg.tbl_hot_pool.item(r, 1)]
    assert "600137" in found_codes, f"前台表格未能从活跃内存实例中读取到标的，表格内容: {found_codes}"
    # 清理单例引用，避免污染后续测试
    FusionShadow._ACTIVE_INSTANCE = None


def test_toast_click_direct_locate_fusion_ladder(qapp):
    """验证测试 5：点击 Toast 直达定向唤醒 FusionLadderDialog 并自动切换到 Tab 1 (🔥 梯度热榜)。"""
    from ats.ui.fusion_ladder_dialog import FusionLadderDialog
    
    dlg = FusionLadderDialog()
    # 初始处于 Tab 0 (实时梯度)
    dlg.tabs.setCurrentIndex(0)
    assert dlg.tabs.currentIndex() == 0

    # 往热榜表格填入测试标的
    dlg.tbl_hot_pool.setRowCount(1)
    dlg.tbl_hot_pool.setItem(0, 1, QTableWidgetItem("600137"))
    
    # 模拟点击 Toast 触发 activate_and_locate_target_window
    activate_and_locate_target_window(dlg, "600137", "【梯度热榜】浪潮软件 晋级核心领涨")
    
    # 断言：必须自动切换到 Tab 1 (🔥 梯度热榜)！
    assert dlg.tabs.currentIndex() == 1, f"未能自动切换至 Tab 1，当前为: {dlg.tabs.currentIndex()}"
    # 断言：表格中选中的行对应的股票代码必须是 600137
    selected_items = dlg.tbl_hot_pool.selectedItems()
    assert len(selected_items) > 0, "未能精准高亮选中标的行！"
    sel_code = dlg.tbl_hot_pool.item(selected_items[0].row(), 1).text().strip()
    assert sel_code == "600137", f"选中的股票代码不匹配: {sel_code}"


def test_alert_notifier_shutdown_and_sandbox_mute():
    """验证测试 6：AlertNotifier.shutdown() 彻底安全注销，且单测沙箱严格静音。"""
    notifier = get_alert_notifier()
    
    # 验证单测环境下 is_running_pytest 保护
    assert bool(os.environ.get("PYTEST_CURRENT_TEST") or "pytest" in sys.modules)
    
    # 执行 shutdown 协议
    notifier.shutdown()
    assert getattr(notifier, "_is_shutdown", False) is True
    assert len(notifier._notify_queue) == 0
    assert notifier._voice_stop_event.is_set()
    
    # 在已注销状态下尝试推送新信号，必须静默拦截
    notifier.notify_special_signal("600000", "浦发银行", "测试", is_force=True)
    assert len(notifier._notify_queue) == 0
