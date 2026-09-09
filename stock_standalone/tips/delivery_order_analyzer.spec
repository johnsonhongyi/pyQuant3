# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller Spec for DeliveryOrderAnalyzer (极小体积与零崩溃架构)
-----------------------------------------------------------------
核心保障：
1. GUI已解耦为纯Python原生引擎，strict_excludes 排除 pandas, numpy, scipy 等所有重型计算包；
2. 剥离 PyQt6 中的 WebEngine, Qml, Quick, 3D, Multimedia 等庞大无用组件；
3. 设置 optimize=0，保留完整 docstring，杜绝 add_docstring 异常；
4. 单文件体积进一步暴降至约 25MB~35MB，启动毫秒级。
"""

import os
import sys

block_cipher = None

# 需要彻底剔除的 Qt6 冗余二进制与动态链接库关键词
trash_list = [
    'Qt6WebEngineCore', 'Qt6WebEngineWidgets', 'Qt6WebEngine', 'Qt6Pdf', 'Qt6PdfWidgets',
    'Qt6Quick', 'Qt6QuickWidgets', 'Qt6Quick3D', 'Qt6Qml', 'Qt6QmlModels',
    'Qt6VirtualKeyboard', 'Qt6Multimedia', 'Qt6MultimediaWidgets',
    'Qt6Bluetooth', 'Qt6Positioning', 'Qt6Sensors', 'Qt6SerialPort', 'Qt6Nfc',
    'Qt6SpatialAudio', 'Qt63D', 'Qt6Designer', 'Qt6Help',
    'Qt6Test', 'Qt6Xml', 'Qt6Sql', 'Qt6NetworkAuth',
    'opengl32sw', 'd3dcompiler'
]

# 严格的依赖排除列表 (Excludes) - 彻底排除非必需的三方重型库
strict_excludes = [
    'pandas', 'numpy', 'scipy', 'matplotlib', 'tables', 'h5py', 'cv2', 'PIL', 'Pillow',
    'IPython', 'jupyter', 'notebook', 'ipykernel', 'zmq', 'tornado',
    'numba', 'llvmlite', 'statsmodels', 'sklearn', 'sympy',
    'tushare', 'pytdx', 'cryptography', 'jedi', 'openpyxl',
    'botocore', 'boto3', 'awscli',
    'PyQt5', 'PySide2', 'PySide6',
    'sqlite3', 'unittest', 'doctest'
]

a = Analysis(
    ['delivery_order_analyzer_gui.py'],
    pathex=['.', '..'],
    binaries=[],
    datas=[],
    hiddenimports=[
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=strict_excludes,
    noarchive=False,
    optimize=0,  # 禁用 -OO，保留完整文档字符串，杜绝 add_docstring 异常
)

# 核心过滤：从 a.binaries 和 a.datas 中剥离所有命中文档或垃圾列表的文件
filtered_binaries = []
removed_binaries = []
for b in a.binaries:
    name_lower = b[0].lower()
    if any(bad.lower() in name_lower for bad in trash_list) or ('~' in b[0]):
        removed_binaries.append(b[0])
    else:
        filtered_binaries.append(b)

filtered_datas = []
removed_datas = []
for d in a.datas:
    name_lower = d[0].lower()
    if any(bad.lower() in name_lower for bad in trash_list) or ('~' in d[0]):
        removed_datas.append(d[0])
    else:
        filtered_datas.append(d)

print(f"\n[Spec Optimizer] 已剔除冗余二进制文件: {len(removed_binaries)} 个")
print(f"[Spec Optimizer] 已剔除冗余数据资源: {len(removed_datas)} 个\n")

a.binaries = filtered_binaries
a.datas = filtered_datas

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# 检查当前目录及上级目录图标
ico_path = None
for candidate in ["MonitorTK.ico", "../MonitorTK.ico"]:
    if os.path.exists(candidate):
        ico_path = candidate
        break

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='DeliveryOrderAnalyzer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=ico_path,
)
