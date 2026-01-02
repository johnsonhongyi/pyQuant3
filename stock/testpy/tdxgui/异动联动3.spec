# -*- mode: python ; coding: utf-8 -*-
import sys
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

# 必要的隐藏导入
hidden_imports = [
    'numpy',
    'pandas',
    'tables',
    'tkcalendar',
    'psutil',
    'pyperclip',
    'requests',
    'pywin32',
    'dateutil',
]

# 收集 pywin32 子模块
hidden_imports += collect_submodules('win32com')

a = Analysis(
    ['异动联动.py'],  # 主程序文件
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=hidden_imports,
    hookspath=[],
    excludes=[
        # 排除常见大包
        'matplotlib', 'scipy', 'sklearn', 'seaborn',
        'cv2', 'pygame', 'tensorflow', 'torch', 'keras',
        'notebook', 'jupyter', 'flask', 'fastapi',
        'bokeh', 'plotly', 'dash', 'aiohttp', 'numba',
        'numexpr', 'sympy', 'dateutil', 'lxml', 'pyyaml',
        'sqlalchemy', 'pyqt5', 'pyqt6', 'tornado', 'twisted'
    ],
    noarchive=False
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='异动联动',
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

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=True,
    upx=True,
    upx_exclude=['python3.dll'],  # 排除无法压缩的 DLL
    name='异动联动'
)

