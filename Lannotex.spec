# -*- mode: python ; coding: utf-8 -*-
import re
import sys

VERSION = re.search(r'__version__ = "([^"]+)"', open('src/lannotex/__init__.py').read()).group(1)

# Windows wants .ico, macOS wants .icns; Linux takes the window icon the app sets itself.
ICON = {'win32': 'assets/Lannotex.ico', 'darwin': 'assets/Lannotex.icns'}.get(sys.platform)

a = Analysis(
    ['run_lannotex.py'],
    pathex=['src'],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Lannotex',
    icon=ICON,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
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
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Lannotex',
)
if sys.platform == 'darwin':
    app = BUNDLE(
        coll,
        name='Lannotex.app',
        icon=ICON,
        bundle_identifier='io.github.lourdhu02.lannotex',
        info_plist={
            'CFBundleDisplayName': 'Lannotex',
            'CFBundleShortVersionString': VERSION,
            'NSHighResolutionCapable': True,
        },
    )
