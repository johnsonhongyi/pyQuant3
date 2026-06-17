# -*- mode: python ; coding: utf-8 -*-
import os
import glob

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
    ['webTools/manage_window_layout.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        ("MonitorTK.ico", "."),
        ("webTools/window_manager/window_layout_config.json", "webTools/window_manager"),
    ] + [(f, ".") for f in glob.glob("*monitordisplay_config.json")],
    hiddenimports=[
        'sys_utils',
        'webTools.window_manager.core', 
        'webTools.window_manager.ui',
        'screeninfo', 
        'win32gui', 
        'win32con', 
        'PyQt6',
        'configobj',
        'JohnsonUtil.johnson_cons',
        'JohnsonUtil.LoggerFactory',
        'JohnsonUtil.commonTips',
        'sys_performance_analyzer'
    ],
    excludes=[
        'a_trade_calendar',
        'db_utils',
        'JSONData',
        'pandas',
        'numpy',
        'pyqtgraph',
        'sqlite3',
        'tables',
        'h5py',
        'tushare',
        'pandas_ta',
        'talib',
        'matplotlib',
        'scipy',
        'jedi',
        'IPython',
        'notebook',
        'lxml',
        'cryptography',
        'numba',
        'llvmlite',
        'botocore',
        'boto3',
        'PyQt5',
        'PySide2',
        'PySide6'
    ],
    noarchive=False,
    optimize=1,              # 相当于 -OO，保留文档字符串
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
    # 同时排除 botocore/data 这样庞大的 AWS 配置数据文件 (无 AWS 需求)
    is_aws_data = ('botocore' in x[0] or 'botocore' in x[1])
    if is_trash or is_dirty_temp or is_aws_data:
        removed_datas.append(x[0])
    else:
        filtered_datas.append(x)

print(f"\n[WindowLayoutManager Spec Optimizer] Filtered out {len(removed_binaries)} binary files. Examples: {removed_binaries[:10]}")
print(f"[WindowLayoutManager Spec Optimizer] Filtered out {len(removed_datas)} data files. Examples: {removed_datas[:10]}\n")

a.binaries = filtered_binaries
a.datas = filtered_datas

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='manage_window_layout',
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
    icon="MonitorTK32.ico",
)
