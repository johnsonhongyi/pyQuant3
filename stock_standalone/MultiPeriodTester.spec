# -*- mode: python ; coding: utf-8 -*-
import glob

# --- 定义需要剔除的冗余库和 DLL 关键词 ---
trash_list = [
    'Qt6WebEngineCore', 'Qt6WebEngineWidgets', 'Qt6Pdf', 
    'Qt6Quick', 'Qt6Qml', 'Qt6VirtualKeyboard', 
    'Qt6Multimedia', 'Qt6Bluetooth', 'Qt6Network',
    'Qt6Svg', 'Qt6Sql', 'Qt6Test', 'Qt6Xml',
    'opengl32sw'
]

import a_trade_calendar
import os

csv_path = os.path.join(os.path.dirname(a_trade_calendar.__file__), "a_trade_calendar.csv")

a = Analysis(
    ['standalone_multi_period_tester.py'],
    pathex=[],
    binaries=[],
    datas=[(csv_path, "a_trade_calendar"),
        ("config/multi_period_help.md", "config"),
    ],
    hiddenimports=[
        'global_favorites', 'stock_logic_utils', 
        'pandas', 'numpy', 'tables', 'sqlite3', 
        'tdx_utils', 'db_utils', 'JSONData', 'JSONData.tdx_data_Day',
        'a_trade_calendar', 'talib', 'talib.stream', 'tushare', 'pandas_ta'
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'PyQt6', 'PyQt5', 'PySide2', 'PySide6', 'pyqtgraph',
        'matplotlib', 'scipy', 'IPython', 'notebook', 
        'bokeh', 'seaborn', 'flask', 'django', 
        'sqlalchemy', 'pyecharts', 'zmq', 'tornado',
        'botocore', 'boto3'
    ],
    noarchive=False,
    optimize=1,
)

# --- 核心优化：强制从 binaries 和 datas 中过滤掉垃圾文件与 Windows pip 残留脏文件 ---
filtered_binaries = []
removed_binaries = []
for x in a.binaries:
    is_trash = any(bad in x[0] for bad in trash_list)
    is_dirty_temp = ('~' in x[0] or '~' in x[1])
    if is_trash or is_dirty_temp:
        removed_binaries.append(x[0])
    else:
        filtered_binaries.append(x)

filtered_datas = []
removed_datas = []
for x in a.datas:
    is_trash = any(bad in x[0] for bad in trash_list)
    is_dirty_temp = ('~' in x[0] or '~' in x[1])
    is_aws_data = ('botocore' in x[0] or 'botocore' in x[1])
    if is_trash or is_dirty_temp or is_aws_data:
        removed_datas.append(x[0])
    else:
        filtered_datas.append(x)

print(f"\n[MultiPeriodTester Spec Optimizer] Filtered out {len(removed_binaries)} binary files.")
print(f"[MultiPeriodTester Spec Optimizer] Filtered out {len(removed_datas)} data files.\n")

a.binaries = filtered_binaries
a.datas = filtered_datas

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='MultiPeriodTester',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
