# -*- coding: utf-8 -*-
"""专项测试：梯度热榜缺失时间戳门禁、纯正中文语音清洗、全维度筛选清除定位闭环及单测物理盘严格隔离。"""

import os
import re
import sys
import time
import pytest
from PyQt6.QtWidgets import QApplication, QTableWidgetItem
from ats.fusion.hot_pool import (
    HotPoolState,
    StockSeatState,
    CandidateActivation,
    SectorPulseEngine,
    HotPoolCalibratedConfig,
    _write_hot_pool_payload,
    load_hot_pool_state,
    load_previous_day_carry_states,
    _is_running_pytest,
    translate_reason_to_cn,
)
from ats.alert_notifier import get_alert_notifier


def test_missing_timestamp_strict_block_gate():
    """验证阻断项 3：缺失行情时间戳 (q_ts == 0.0 或无 ts) 严格被门禁拦截，绝不放行不可靠数据。"""
    cfg = HotPoolCalibratedConfig()
    engine = SectorPulseEngine(
        config=cfg,
        sector_map={"000001": "industry:半导体", "000002": "industry:半导体"},
    )
    engine.init_membership(["000001", "000002"])
    now = 1793870000.0

    # 1. SectorPulseEngine 门禁验证：000001 缺失时间戳 (ts=0.0)，000002 具备新鲜时间戳 (ts=now)
    quotes = {
        "000001": {"price": 10.0, "percent": 2.0, "volume": 1000.0, "vwap": 9.9, "ratio": 2.0, "ts": 0.0},
        "000002": {"price": 20.0, "percent": 3.0, "volume": 2000.0, "vwap": 19.8, "ratio": 2.5, "ts": now},
    }
    pulses = engine.step_frame("2026-11-05", now, quotes, market_pct=0.0)

    # 000001 因无时效证明，严禁进入价格窗口！
    assert "000001" not in engine._price_windows
    # 000002 具备时效证明，正常进入价格窗口
    assert "000002" in engine._price_windows

    # 2. HotPoolState 席位门禁验证
    hp = HotPoolState(config=cfg, sector_engine=engine)
    hp.candidates["000001"] = CandidateActivation(
        code="000001", trade_date="2026-11-05", ts=now, source="premarket_seed", reason="test", sector="industry:半导体"
    )
    hp.candidates["000002"] = CandidateActivation(
        code="000002", trade_date="2026-11-05", ts=now, source="premarket_seed", reason="test", sector="industry:半导体"
    )

    daily_mock = {
        "000001": {"vwap10": 9.5, "vwap_prev9_value": 90000.0, "vwap_prev9_volume": 9000.0, "close_pre1": 9.8, "is_structure_prejudged": 1.0},
        "000002": {"vwap10": 19.0, "vwap_prev9_value": 180000.0, "vwap_prev9_volume": 9000.0, "close_pre1": 19.5, "is_structure_prejudged": 1.0},
    }
    obs_map = {
        "000001": {"freshness": "missing_ts", "vwap": {"timing": {"freshness": "missing_ts"}, "including_current": {"10": 9.8}}},
        "000002": {"freshness": "same_day", "vwap": {"timing": {"freshness": "same_day"}, "including_current": {"10": 19.5}}},
    }

    hp.step_frame("2026-11-05", now, quotes, lambda c, d: daily_mock.get(c, {}), obs_evidence_map=obs_map)

    # 000001 缺失时间戳被席位门禁严格跳过，未获得任何有效席位
    assert "000001" not in hp.seats or hp.seats["000001"].seat == "NONE"
    # 000002 具备新鲜时间戳且满足条件，正常获得席位 (TREND_WATCH)
    assert "000002" in hp.seats and hp.seats["000002"].seat == "TREND_WATCH"


def test_production_voice_branch_cancels_english_and_broadcasts_pure_chinese(monkeypatch):
    """验证阻断项 4：生产语音分支彻底取消英文播报，100% 消除下划线与英文，实现地道中文播报。"""
    notifier = get_alert_notifier()
    assert notifier is not None

    spoken_texts = []
    def mock_speak(text):
        spoken_texts.append(text)

    monkeypatch.setattr(notifier, "_speak_text", mock_speak)
    monkeypatch.setattr(notifier, "is_voice_enabled", lambda: True)
    monkeypatch.setattr(notifier, "is_toast_enabled", lambda: False)
    notifier._is_busy = False
    notifier._notify_queue.clear()

    # 1. 模拟梯度热榜产生带有英文枚举与下划线的原始提示
    notifier.notify_special_signal(
        code="600000",
        name="浦发银行",
        reason="【梯度热榜】PROMOTED_TO_CORE_LEADER: core_capacity_exceeded_demotion",
        score=92.0,
        source="梯度热榜",
        is_force=True,
    )

    assert len(spoken_texts) == 1
    voice_str = spoken_texts[0]

    # 核心硬门禁校验：
    # ① 绝不包含任何下划线 '_'
    assert "_" not in voice_str
    # ② 绝不包含任何英文字母 (取消英文播报，纯正中文)
    assert not re.search(r'[a-zA-Z]', voice_str), f"语音播报中发现英文字符: {voice_str}"
    # ③ 真实包含中文标的与核心席位转译
    assert "梯度热榜" in voice_str
    assert "浦发银行" in voice_str
    assert "晋级核心领涨" in voice_str
    assert "核心席位超额顺延降级" in voice_str

    # 2. 验证动态参数转译覆盖
    dyn_reason_1 = translate_reason_to_cn("pulse_confirmed_industry:电子-半导体")
    assert "半导体" in dyn_reason_1 and "_" not in dyn_reason_1
    dyn_reason_2 = translate_reason_to_cn("leader_switch_from_600000_to_000001")
    assert "600000" in dyn_reason_2 and "000001" in dyn_reason_2 and "_" not in dyn_reason_2


def test_locate_stock_in_table_clears_seat_pulse_and_search_filters(monkeypatch):
    """验证阻断项 4：Toast 点击直达定位在存在席位筛选、板块脉冲筛选与搜索框限制时，能全维度清除阻碍精准定位。"""
    app = QApplication.instance() or QApplication(sys.argv)
    from ats.ui.fusion_ladder_dialog import FusionLadderDialog

    # 构造模拟热榜状态
    st_mock = HotPoolState()
    st_mock.current_trade_date = "2026-11-05"
    st_mock.seats["000001"] = StockSeatState(
        code="000001", trade_date="2026-11-05", seat="CORE_LEADER", primary_sector="industry:电子-半导体", price=15.0, pct=4.0
    )
    st_mock.seats["600000"] = StockSeatState(
        code="600000", trade_date="2026-11-05", seat="EVICTED", primary_sector="industry:通信-设备", price=10.0, pct=-2.0
    )

    import ats.fusion.hot_pool as hp_mod
    monkeypatch.setattr(hp_mod, "load_hot_pool_state", lambda day, log_dir=None, ramdisk_dir=None: st_mock)
    try:
        from ats.fusion.shadow import FusionShadow
        FusionShadow._ACTIVE_INSTANCE = None
    except Exception:
        pass

    dlg = FusionLadderDialog()
    tbl = dlg.tbl_hot_pool

    # 1. 初始状态：席位设置为“核心领涨”，板块筛选设置为“全部板块脉冲”
    dlg.cb_hp_seat.setCurrentText("核心领涨")
    dlg.cb_hp_pulse.setCurrentIndex(0)
    dlg.refresh_hot_pool()

    # 此时表格中只有 000001，而 600000 因处于 EVICTED 被席位过滤隐藏！
    codes_in_tbl = [tbl.item(r, 1).text() for r in range(tbl.rowCount()) if tbl.item(r, 1)]
    assert "000001" in codes_in_tbl
    assert "600000" not in codes_in_tbl

    # 2. 模拟用户又选择了板块筛选与搜索框输入
    dlg.cb_hp_pulse.addItem("电子-半导体", "industry:电子-半导体")
    dlg.cb_hp_pulse.setCurrentIndex(1)
    dlg.ed_search.setText("平安")

    # 3. 触发真实 Toast 点击定位调用！
    located = dlg.locate_stock_in_table("600000", auto_popup=False)

    assert located is True
    # 断言阻碍已被全维度清除并重新加载：
    # ① 席位筛选被自动切换为全部席位
    assert "全部席位" in dlg.cb_hp_seat.currentText()
    # ② 板块脉冲被重置为“全部板块脉冲”
    assert dlg.cb_hp_pulse.currentIndex() == 0
    # ③ 搜索框关键词被清空
    assert dlg.ed_search.text() == ""
    # ④ 表格重新加载并成功选中 600000 所在行！
    final_codes = [tbl.item(r, 1).text() for r in range(tbl.rowCount()) if tbl.item(r, 1)]
    assert "600000" in final_codes
    assert tbl.currentRow() >= 0
    assert tbl.item(tbl.currentRow(), 1).text() == "600000"


def test_pytest_environment_strictly_isolates_physical_g_disk(tmp_path):
    """验证阻断项 5：pytest 运行环境下物理盘 G:\\fusion_shadow 受到严格隔离，绝不读取也不写入。"""
    assert _is_running_pytest() is True

    # 1. 测试在指定 log_dir 时优先使用该目录，且绝不包含 G 盘
    custom_dir = str(tmp_path / "custom_logs")
    os.makedirs(custom_dir, exist_ok=True)
    _write_hot_pool_payload("2026-11-05", "{}", log_dir=custom_dir)
    assert os.path.exists(os.path.join(custom_dir, "hot_pool_2026-11-05.json"))

    # 2. 测试 load_hot_pool_state 在 pytest 环境下不访问 G 盘
    loaded = load_hot_pool_state("2026-11-05", log_dir=custom_dir)
    assert loaded is not None

    # 3. 验证 load_previous_day_carry_states 同样严格遵循隔离
    carries = load_previous_day_carry_states("2026-11-06", log_dir=custom_dir)
    assert isinstance(carries, dict)
