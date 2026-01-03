# -*- mode: python ; coding: utf-8 -*-
# build.spec 示例
import os
import a_trade_calendar

csv_path = os.path.join(os.path.dirname(a_trade_calendar.__file__), "a_trade_calendar.csv")
block_cipher = None
a = Analysis(
    ['异动联动.py'],
    pathex=[],
    binaries=[],
    datas=[(csv_path, "a_trade_calendar"),
        ("globalYD.ini", "."),
        ],
    hiddenimports=['filelock'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
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
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
