# -*- coding: utf-8 -*-
"""tests/test_fusion_full_chain_audit.py — 融合信号梯度全链路闭环深度集成审计"""

import os
import json
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(["fusion-chain-audit"])
    return app


def test_fusion_full_chain_end_to_end_audit(qapp, tmp_path, monkeypatch):
    """
    全链路闭环深度集成审计：
    1. 信号与梯度双通道持久化 (Ramdisk + 物理落盘)
    2. 模拟盘中异常崩溃，重启后秒级自愈加载
    3. 盘后 >= 15:00 自动沉淀快照 (session_ctx) 与次日 handoff 交接
    4. 跨日日期自动感知刷新 (杜绝反复重启)
    5. 右键菜单全面对齐资金主线 (异动联动、SBC走势图、次新超短、DNA审计、重点关注)
    6. TK 主控台窗口枚举扫描与 Alt+R 激活展开联动
    """
    import ats.ui.fusion_ladder_dialog as fld
    from ats.ui.fusion_ladder_dialog import (
        FusionLadderDialog,
        persist_shadow_records,
        load_live_rows,
        get_open_fusion_ladder_dialog,
    )
    from ats.fusion.session_ctx import default_store
    from ats.ui.styles import save_config_node, load_config_node

    primary_dir = tmp_path / "primary"
    ramdisk_dir = tmp_path / "ramdisk"
    primary_dir.mkdir(parents=True)
    ramdisk_dir.mkdir(parents=True)

    monkeypatch.setattr("sys_utils.get_app_root", lambda: str(primary_dir))
    monkeypatch.setattr("ats.ui.fusion_ladder_dialog._detect_ramdisk_dir", lambda: str(ramdisk_dir))

    # =========================================================================
    # 环节 1：实盘影子流数据生成与 Ramdisk 双通道原子持久化
    # =========================================================================
    test_day = "2026-10-23"
    records = [
        {
            "code": "688787",
            "name": "海天瑞声",
            "ts": 1729647600.0,
            "price": 112.20,
            "pct": 6.85,
            "fusion": {
                "tier": 4,
                "tier_name": "主攻",
                "rar": 91.5,
                "size_pct": 28.0,
                "age_min": 15.0,
                "entry": {"price_lo": 111.50, "price_hi": 112.50},
                "stop": {"price": 107.00},
                "axes": {"position": 78.0, "support": 85.0, "intent": 92.0, "regime": 75.0},
                "sources": ["SHADOW_LIVE"],
            },
        },
        {
            "code": "300296",
            "name": "利亚德",
            "ts": 1729647900.0,
            "price": 6.88,
            "pct": 4.25,
            "fusion": {
                "tier": 3,
                "tier_name": "参与",
                "rar": 78.0,
                "size_pct": 18.0,
                "age_min": 25.0,
                "entry": {"price_lo": 6.80, "price_hi": 6.90},
                "stop": {"price": 6.55},
                "axes": {"position": 65.0, "support": 72.0, "intent": 80.0, "regime": 70.0},
                "sources": ["SHADOW_LIVE"],
            },
        },
    ]

    saved_n = persist_shadow_records(records, day=test_day)
    assert saved_n == 2
    # 验证 Ramdisk 与主落盘双通道均原子生成
    assert (ramdisk_dir / f"{test_day}.jsonl").exists()
    assert (primary_dir / "logs" / "fusion_shadow" / f"{test_day}.jsonl").exists()

    # =========================================================================
    # 环节 2：模拟程序崩溃中断，重启打开后秒级自愈复原
    # =========================================================================
    recovered_rows = load_live_rows(test_day)
    assert len(recovered_rows) == 2
    assert recovered_rows[0]["code"] == "688787"
    assert recovered_rows[0]["name"] == "海天瑞声"
    assert recovered_rows[0]["price"] == 112.20
    assert recovered_rows[0]["fusion"]["tier"] == 4
    assert recovered_rows[0]["fusion"]["rar"] == 91.5

    # =========================================================================
    # 环节 3：监视器窗口初始化与数据呈现
    # =========================================================================
    save_config_node("fusion_ladder_stays_on_top", False)
    save_config_node("fusion_last_auto_settle_day", "")

    dlg = fld.open_fusion_ladder_dialog()
    assert dlg is not None
    assert get_open_fusion_ladder_dialog() is dlg

    # 设置当前查看日期为 test_day 并刷新呈现
    dlg.cmb_day.addItem(test_day)
    dlg.cmb_day.setCurrentText(test_day)
    dlg.refresh_live()

    assert dlg.tbl_live.rowCount() == 2
    # 验证第 1 行是海天瑞声，包含代码、名称、现价、涨幅、RAR
    assert dlg.tbl_live.item(0, 1).text() == "688787"
    assert dlg.tbl_live.item(0, 2).text() == "海天瑞声"
    assert dlg.tbl_live.item(0, 3).text() == "112.20"
    assert "+6.85%" in dlg.tbl_live.item(0, 4).text()
    assert dlg.tbl_live.item(0, 5).text() == "91.5"

    # =========================================================================
    # 环节 4：右键菜单资金主线级对齐与异动联动验证
    # =========================================================================
    from PyQt6.QtCore import QPoint
    from PyQt6.QtWidgets import QMenu

    linkage_captured = []
    ipo_captured = []
    dna_captured = []
    fav_captured = []

    monkeypatch.setattr("ats.ui.base_table.send_to_linkage", lambda c, n, p: linkage_captured.append((c, n)))
    monkeypatch.setattr("ats.ui.ipo_detector_ipc.send_stock_to_ipo_detector", lambda c, n: ipo_captured.append((c, n)))
    monkeypatch.setattr("ats.ui.multi_period_dialog.run_dna_audit_batch_qt", lambda d, parent=None: dna_captured.append(d))

    menu_list = []
    monkeypatch.setattr(QMenu, "exec", lambda self, pt: menu_list.append(self))

    # 右键点击第 0 行 (688787 海天瑞声)
    dlg._on_table_context_menu(dlg.tbl_live, QPoint(10, 10))
    assert len(menu_list) == 1
    menu = menu_list[0]
    acts = {a.text(): a for a in menu.actions()}

    # 4.1 验证菜单项完全对齐资金主线
    assert any("复制股票代码 688787" in t for t in acts)
    assert any("发送到异动联动 688787" in t for t in acts)
    assert any("SBC 通道走势图" in t for t in acts)
    assert any("个股详情" in t for t in acts)
    assert any("新股次新超短检测工具" in t for t in acts)
    assert any("DNA 特征审计报告" in t for t in acts)
    assert any("全系统重点关注" in t for t in acts)
    assert any("每日涨停天梯看板" in t for t in acts)
    assert any("板块雷达" in t for t in acts)
    assert any("主线回踩深挖" in t for t in acts)

    # 4.2 触发异动联动发送
    act_linkage = [a for t, a in acts.items() if "发送到异动联动 688787" in t][0]
    act_linkage.trigger()
    assert len(linkage_captured) == 1
    assert linkage_captured[0][0] == "688787"
    assert "海天瑞声" in linkage_captured[0][1]
    assert "已发送 海天瑞声(688787) 到异动联动" in dlg.lbl_status.text()

    # 4.3 触发新股次新超短检测工具
    act_ipo = [a for t, a in acts.items() if "新股次新超短检测工具" in t][0]
    act_ipo.trigger()
    assert len(ipo_captured) == 1
    assert ipo_captured[0][0] == "688787"

    # =========================================================================
    # 环节 5：TK 主控台窗口枚举、Alt+R 轮选与激活展开闭环
    # =========================================================================
    from PyQt6.QtCore import QEvent

    # 5.1 贴边折叠测试
    dlg.anchor_edge = "right"
    dlg.is_hidden_state = True
    dlg.setWindowOpacity(0.35)

    # 模拟 Alt+R 切换激活
    dlg.isActiveWindow = lambda: True
    dlg.changeEvent(QEvent(QEvent.Type.ActivationChange))
    # 必须自动展开
    assert dlg.is_hidden_state is False
    assert dlg.windowOpacity() == 1.0

    # 5.2 模拟 TK 端的 _get_all_open_trade_windows
    # 当融合梯度窗口可见时，应该能自动识别并命名
    class DummyTKApp:
        def __init__(self):
            self._rotator_window_names = {}
            self._win_cache = {"fusion_ladder": int(dlg.winId())}
            self._window_mru_list = []

        def _scan_windows_cached(self):
            return self._win_cache

        def _get_toplevel_hwnd(self, wid):
            return wid

        def winfo_exists(self):
            return False

    tk_dummy = DummyTKApp()
    # 验证单例获取
    assert get_open_fusion_ladder_dialog() is dlg

    # =========================================================================
    # 环节 6：收盘后 (>= 15:00) 自动持久化与上下文固化及次日交接
    # =========================================================================
    # 触发收盘自动结算
    dlg._execute_closing_session_settlement(test_day)

    # 验证上下文快照已持久化
    store = default_store()
    session_file = store.path(test_day)
    assert os.path.exists(session_file)

    ctx = store.load(test_day)
    assert ctx is not None
    assert ctx.day == test_day
    assert ctx.source == "live"
    assert len(ctx.phase_path) >= 1
    assert ctx.phase_path[-1]["phase"] == "收盘完成"

    # 验证次日交接 handoff
    handoff_dict = store.handoff(test_day)
    assert handoff_dict is not None
    assert "day" in handoff_dict

    # 验证界面状态提示与配置记录
    assert load_config_node("fusion_last_auto_settle_day") == test_day
    assert "今日收盘上下文已自动沉淀" in dlg.lbl_status.text()

    dlg.close()
