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
    ['instock_MonitorTK.py'],
    pathex=[],
    binaries=[],
    datas=[(csv_path, "a_trade_calendar"),
        ("MonitorTK.ico", "."),
        ("window_config.json", "."),
        ("scale2_window_config.json", "."),
        ("monitor_category_list.json", "."),
        ("visualizer_layout.json", "."),
        ("display_cols.json", "."),
        ("datacsv/search_history.json", "."),
        ("JSONData/stock_codes.conf", "JSONData"),
        ("JSONData/count.ini", "JSONData"),
        ("JohnsonUtil/global.ini", "JohnsonUtil"),
        ("JohnsonUtil/wencai/同花顺板块行业.xlsx", "JohnsonUtil/wencai"),
         ],
    hiddenimports=['talib.stream', 'talib.abstract'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=1,              # 相当于 -OO，移除文档字符串和断言  optimize=1：移除 assert 语句，但保留文档字符串，这样 NumPy 就能正常运行。
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
    name='instock_MonitorTK',
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
)
#   icon="MonitorTK32.ico",    # ✅ 加这一行
