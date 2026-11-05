import os
import sys
import tempfile
import pytest

# Ensure QApplication exists for Qt tests
from PyQt6.QtWidgets import QApplication
app = QApplication.instance()
if app is None:
    app = QApplication(sys.argv)

from ats.fusion.hot_pool import (
    StockSeatState,
    HotPoolState,
    save_hot_pool_state,
    load_hot_pool_state,
    load_previous_day_carry_states,
)
from ats.ui.fusion_ladder_dialog import FusionLadderDialog


def test_hot_pool_state_default_and_none_log_dir():
    """验证 load_hot_pool_state 与 save_hot_pool_state 在 log_dir 为空/None 时的健壮性"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        state = HotPoolState()
        state.current_trade_date = "2026-11-05"
        st = StockSeatState(
            code="600000",
            trade_date="2026-11-05",
            seat="CORE_LEADER",
            price=12.34,
            pct=5.67,
            watch_score=88.5,
            alpha_vs_sector=3.21,
        )
        state.seats["600000"] = st

        # 写入
        ok = save_hot_pool_state(state, log_dir=tmp_dir)
        assert ok is True

        # 读取：指定目录
        loaded = load_hot_pool_state("2026-11-05", log_dir=tmp_dir)
        assert loaded is not None
        assert "600000" in loaded.seats
        loaded_st = loaded.seats["600000"]
        assert loaded_st.price == 12.34
        assert loaded_st.pct == 5.67
        assert loaded_st.seat == "CORE_LEADER"

        # 读取：log_dir 为 None 不崩溃
        loaded_none = load_hot_pool_state("2099-01-01", log_dir=None)
        assert loaded_none is None

        # load_previous_day_carry_states 在 log_dir 为 None 时不崩溃
        carry = load_previous_day_carry_states("2026-11-06", log_dir=tmp_dir)
        assert "600000" in carry
        assert carry["600000"].seat == "CORE_LEADER"

        carry_none = load_previous_day_carry_states("2026-11-06", log_dir=None)
        assert isinstance(carry_none, dict)


def test_fusion_ladder_dialog_log_dir_and_refresh_hot_pool():
    """验证 FusionLadderDialog 包含 log_dir 属性且 refresh_hot_pool 绝不报 AttributeError"""
    dlg = FusionLadderDialog()
    try:
        # 1. 验证 log_dir 属性存在且为有效字符串路径
        assert hasattr(dlg, "log_dir")
        assert isinstance(dlg.log_dir, str)
        assert len(dlg.log_dir) > 0
        assert "fusion_shadow" in dlg.log_dir

        # 2. 验证 tab 激活表格映射
        dlg.tabs.setCurrentIndex(1)
        active_tbl = dlg._get_active_table()
        assert active_tbl is dlg.tbl_hot_pool

        # 3. 验证调用 refresh_hot_pool 不抛出任何异常
        dlg.refresh_hot_pool()

        # 4. 验证 Tab 切换到 1 时也能自动调用 refresh_hot_pool
        dlg._on_tab_changed(1)
    finally:
        dlg.close()
