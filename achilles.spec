# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['achilles/__main__.py'],
    pathex=['.'],
    binaries=[],
    datas=[],
    hiddenimports=[
        'rich',
        'rich.console',
        'rich.table',
        'rich.panel',
        'rich.text',
        'fastapi',
        'uvicorn',
        'uvicorn.logging',
        'uvicorn.protocols.http.auto',
        'pydantic',
        'playwright',
        'achilles.services.challenge_engine',
        'achilles.services.hud',
        'achilles.services.domain_memory',
        'achilles.services.visual_report',
    ],
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
    name='achilles',
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
