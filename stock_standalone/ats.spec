# -*- mode: python ; coding: utf-8 -*-
import os
import a_trade_calendar

csv_path = os.path.join(os.path.dirname(a_trade_calendar.__file__), "a_trade_calendar.csv")

block_cipher = None

# --- 关键：定义需要剔除的冗余库和 DLL 关键词 ---
# 这些库通常是 PyQt6 自动带入但金融监控工具很少用到的，剔除它们能有效降低启动负载
trash_list = [
    'Qt6WebEngineCore', 'Qt6WebEngineWidgets', 'Qt6Pdf', 
    'Qt6Quick', 'Qt6Qml', 'Qt6VirtualKeyboard', 
    'Qt6Multimedia', 'Qt6Bluetooth', 'Qt6Network',
    'Qt6Svg', 'Qt6Sql', 'Qt6Test', 'Qt6Xml'
]

a = Analysis(
    ['run_ats.py'],
    pathex=[],
    binaries=[],
    datas=[(csv_path, "a_trade_calendar"),
        ("MonitorTK.ico", "."),
        ("window_config.json", "."),
        ("JSONData/stock_codes.conf", "JSONData"),
        ("JSONData/count.ini", "JSONData"),
        ("JohnsonUtil/global.ini", "JohnsonUtil"),
        ("strategy_config.json", "."),
         ],
    hiddenimports=['a_trade_calendar', 'pandas', 'numpy', 'pyqtgraph', 'sqlite3',
                    'sys_utils', 'db_utils', 'ats', 'ats.ipc_bridge', 'ats.universe_manager',
                    'ats.swing_tracker', 'ats.backtest_engine', 'ats.trade_journal',
                    'ats.ui.main_window', 'ats.ui.chart_widgets', 'ats.ui.universe_widget',
                    'ats.ui.heatmap_widget', 'ats.ui.swing_table', 'ats.ui.trade_flow',
                    'configobj'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=1,              # 相当于 -OO，保留文档字符串供 numpy 运行
)

# --- 核心优化：强制从 binaries 和 datas 中过滤掉垃圾文件 ---
a.binaries = [x for x in a.binaries if not any(bad in x[0] for bad in trash_list)]
a.datas = [x for x in a.datas if not any(bad in x[0] for bad in trash_list)]
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='ATS_Terminal',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="MonitorTK32.ico",
)
