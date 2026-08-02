# -*- coding: utf-8 -*-
import sys
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from PyQt6.QtWidgets import QApplication
from ats.ui.global_market_kline_dialog import GlobalMarketKLineDialog

app = QApplication.instance() or QApplication(sys.argv)

# 1. Render Candlestick mode
dlg1 = GlobalMarketKLineDialog('AMZN', '亚马逊')
dlg1.chart_mode = 'candlestick'
dlg1._draw_chart()
dlg1.show()
dlg1.resize(920, 580)
QApplication.processEvents()

save_path1 = os.path.join(r"C:\Users\Johnson\.gemini\antigravity\brain\7f75485b-fb3f-461d-96dc-2684a8dabb69", "amzn_candlestick_fixed.png")
pixmap1 = dlg1.grab()
pixmap1.save(save_path1, "PNG")
print(f"Candlestick screenshot saved to: {save_path1}")
dlg1.close()

# 2. Render OHLC mode
dlg2 = GlobalMarketKLineDialog('AMZN', '亚马逊')
dlg2.chart_mode = 'ohlc'
dlg2._draw_chart()
dlg2.show()
dlg2.resize(920, 580)
QApplication.processEvents()

save_path2 = os.path.join(r"C:\Users\Johnson\.gemini\antigravity\brain\7f75485b-fb3f-461d-96dc-2684a8dabb69", "amzn_ohlc_mode.png")
pixmap2 = dlg2.grab()
pixmap2.save(save_path2, "PNG")
print(f"OHLC screenshot saved to: {save_path2}")
dlg2.close()
