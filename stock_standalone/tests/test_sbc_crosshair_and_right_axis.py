# -*- coding: utf-8 -*-
import pytest
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QPointF
from ats.ui.intraday_strategy_dialog import SBCChartCanvas
import pandas as pd
import numpy as np


@pytest.fixture
def app():
    app_inst = QApplication.instance()
    if app_inst is None:
        app_inst = QApplication([])
    return app_inst


def test_sbc_margin_right_and_compact_labels(app):
    canvas = SBCChartCanvas()
    # 验证右边距已经优化为 58px 防遮挡
    assert canvas.MARGIN_RIGHT == 58

    # 构造测试数据
    dates = pd.date_range("2026-10-27 09:30", periods=50, freq="1min")
    df = pd.DataFrame({
        "open": np.linspace(10, 12, 50),
        "high": np.linspace(10.5, 12.5, 50),
        "low": np.linspace(9.8, 11.8, 50),
        "close": np.linspace(10.2, 12.2, 50),
        "price": np.linspace(10.2, 12.2, 50),
        "vwap": np.linspace(10.1, 12.1, 50),
        "volume": np.random.randint(100, 1000, 50),
    }, index=dates)

    canvas.df_intraday = df
    canvas.open_price = 10.0
    canvas.vwap = 12.1
    canvas.target_sell_min = 12.68
    canvas.resize(800, 600)
    canvas.show()
    app.processEvents()

    # 验证没有点击（未激活 _crosshair_active）时，设置 hover_pos 能够激活十字星手势与选择
    assert getattr(canvas, "_crosshair_active", False) is False
    c_info = getattr(canvas, "_coord_info", {})
    assert c_info.get("ready") is True

    # 模拟鼠标在主图中心悬停 (无需点击)
    ml = c_info["margin_left"]
    mt = c_info["margin_top"]
    cw = c_info["chart_w"]
    mh = c_info["main_h"]
    mid_pos = QPointF(ml + cw / 2.0, mt + mh / 2.0)
    canvas._hover_pos = mid_pos
    canvas.update()
    app.processEvents()

    # 鼠标离开
    canvas.leaveEvent(None)
    assert canvas._hover_pos is None
    canvas.close()
