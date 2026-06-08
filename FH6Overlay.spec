# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['overlay.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('logo/SkoiZzLogo.png', 'logo'),
        ('logo/SkoiZzLogo.ico', 'logo'),
    ],
    hiddenimports=['setup_wizard', 'settings_panel'],
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
    a.binaries,
    a.datas,
    [],
    name='FH6RPMOverlay2.0.0',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,          # U17: upx causes antivirus false positives
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='logo/SkoiZzLogo.ico',          # U2: application icon
    version='version_info.txt',           # U18: PE version metadata
)
