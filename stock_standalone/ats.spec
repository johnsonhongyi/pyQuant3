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
    'Qt6Svg', 'Qt6Sql', 'Qt6Test', 'Qt6Xml',
    'opengl32sw'
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
                    'configobj', 'JSONData', 'JSONData.sina_data', 'tables', 'h5py',
                    'JSONData.tdx_hdf5_api', 'JSONData.realdatajson', 'JSONData.wencaiData',
                    'JSONData.tdxbk', 'JohnsonUtil.johnson_cons', 'tushare', 'pandas_ta',
                    'talib.stream', 'talib.abstract'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'PyQt6.QtWebEngineCore', 'PyQt6.QtWebEngineWidgets', 'PyQt6.QtPdf', 
        'PyQt6.QtQuick', 'PyQt6.QtQml', 'PyQt6.QtVirtualKeyboard', 
        'PyQt6.QtMultimedia', 'PyQt6.QtBluetooth', 'PyQt6.QtPositioning',
        'PyQt6.QtSensors', 'PyQt6.QtWebChannel', 'PyQt6.QtWebSockets',
        'PyQt6.QtSql', 'PyQt6.QtTest', 'PyQt6.QtXml', 'PyQt6.QtQuickWidgets',
        'PyQt6.QtQuick3D', 'PyQt6.QtRemoteObjects',
        'PyQt5', 'PySide2', 'PySide6',
        'matplotlib', 'scipy', 'jedi', 'IPython', 'notebook',
        'lxml', 'cryptography',
        'numba', 'llvmlite', 'botocore', 'boto3'
    ],
    noarchive=False,
    optimize=1,              # 相当于 -OO，保留文档字符串供 numpy 运行
)

# --- 核心优化：强制从 binaries 和 datas 中过滤掉垃圾文件与 Windows pip 残留脏文件 ---
filtered_binaries = []
removed_binaries = []
for x in a.binaries:
    # 判定是否命中垃圾列表，或者是否属于带有波浪号 '~' 的 Windows 升级残留脏路径/文件名
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
    # 同时排除 botocore/data 这样庞大的 AWS 配置数据文件 (ATS 无 AWS 需求)
    is_aws_data = ('botocore' in x[0] or 'botocore' in x[1])
    if is_trash or is_dirty_temp or is_aws_data:
        removed_datas.append(x[0])
    else:
        filtered_datas.append(x)

print(f"\n[ATS Spec Optimizer] Filtered out {len(removed_binaries)} binary files. Examples: {removed_binaries[:10]}")
print(f"[ATS Spec Optimizer] Filtered out {len(removed_datas)} data files. Examples: {removed_datas[:10]}\n")

a.binaries = filtered_binaries
a.datas = filtered_datas

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
