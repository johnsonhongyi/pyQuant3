import os
import sys
import json
import pytest
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QRect

from ats.ui.intraday_strategy_dialog import (
    SBCIntradayChartDialog,
    open_sbc_chart_dialog,
    restore_all_open_sbc_windows,
    save_all_open_sbc_windows,
    _get_sbc_layout_cfg_path,
    _get_screen_for_geometry
)
from run_sbc import _calculate_safe_geometry_with_wrap


@pytest.fixture
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


class TestSBCMultiscreenAndExactRestore:

    def test_get_screen_for_geometry_multiscreen(self, qapp):
        screen = _get_screen_for_geometry(100, 100, 680, 420)
        assert screen is not None

        secondary_screen = _get_screen_for_geometry(2500, 100, 680, 420)
        assert secondary_screen is not None

    def test_exact_geometry_and_screen_restore_without_wrap(self, qapp, tmp_path, monkeypatch):
        test_cfg = str(tmp_path / 'test_multiscreen_sbc_layout.json')
        monkeypatch.setenv('SBC_LAYOUT_CONFIG_PATH', test_cfg)

        sample_windows = [
            {'code': '600733', 'x': 10, 'y': 30, 'width': 340, 'height': 260, 'period_mode': '10d'},
            {'code': '688635', 'x': 360, 'y': 30, 'width': 340, 'height': 260, 'period_mode': '10d'},
            {'code': '603407', 'x': 710, 'y': 30, 'width': 340, 'height': 260, 'period_mode': '10d'}
        ]
        with open(test_cfg, 'w', encoding='utf-8') as f:
            json.dump({'sbc_open_windows': sample_windows}, f, indent=2)

        restored = restore_all_open_sbc_windows(parent_win=None, as_subprocess=False)
        try:
            assert len(restored) == 3

            d1 = next((d for d in restored if d.code == '600733'), None)
            d2 = next((d for d in restored if d.code == '688635'), None)
            d3 = next((d for d in restored if d.code == '603407'), None)

            assert d1 is not None and d2 is not None and d3 is not None
            assert d1.geometry().x() == 10
            assert d1.geometry().y() == 30
            assert d2.geometry().x() == 360
            assert d2.geometry().y() == 30
            assert d3.geometry().x() == 710
            assert d3.geometry().y() == 30

            assert d1.geometry().width() == 340
            assert d2.geometry().width() == 340
            assert d3.geometry().width() == 340

            with open(test_cfg, 'r', encoding='utf-8') as f:
                data_after = json.load(f)
            saved_list = data_after.get('sbc_open_windows', [])
            assert len(saved_list) == 3
            assert saved_list[0]['x'] == 10
            assert saved_list[1]['x'] == 360
            assert saved_list[2]['x'] == 710
        finally:
            for d in restored:
                try:
                    d.close()
                except Exception:
                    pass

    def test_run_sbc_calculate_safe_geometry_preserves_dimensions(self, qapp):
        sg = QRect(0, 0, 1920, 1080)
        item = {'x': 350, 'y': 40, 'width': 340, 'height': 260}
        tx, ty, tw, th, nb = _calculate_safe_geometry_with_wrap(item, sg, prev_bottom=0)
        assert tx == 350
        assert ty == 40
        assert tw == 340
        assert th == 260
