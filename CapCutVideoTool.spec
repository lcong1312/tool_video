# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.building.datastruct import Tree
from PyInstaller.utils.hooks import collect_all

fishaudio_datas, fishaudio_binaries, fishaudio_hiddenimports = collect_all('fishaudio')
httpx_datas, httpx_binaries, httpx_hiddenimports = collect_all('httpx')
httpcore_datas, httpcore_binaries, httpcore_hiddenimports = collect_all('httpcore')
anyio_datas, anyio_binaries, anyio_hiddenimports = collect_all('anyio')
dotenv_datas, dotenv_binaries, dotenv_hiddenimports = collect_all('dotenv')
tkinterdnd2_datas, tkinterdnd2_binaries, tkinterdnd2_hiddenimports = collect_all('tkinterdnd2')


a = Analysis(
    ['capcut_video_gui.py'],
    pathex=['.'],
    binaries=(
        fishaudio_binaries
        + httpx_binaries
        + httpcore_binaries
        + anyio_binaries
        + dotenv_binaries
        + tkinterdnd2_binaries
    ),
    datas=[
        ('acp_build_project.py', '.'),
        ('make_capcut_video.py', '.'),
        ('capcut_draft.py', '.'),
        ('pexels_downloader.py', '.'),
        ('voicevox_tts.py', '.'),
        ('app_update.py', '.'),
        ('app_version.py', '.'),
        ('fish_mexico_gui.py', '.'),
        ('run_setting_fish.bat', '.'),
        ('config.json', '.'),
        ('fish_story_v53_settings.json', '.'),
        ('.env', '.'),
        ('bin', 'bin'),
    ] + fishaudio_datas + httpx_datas + httpcore_datas + anyio_datas + dotenv_datas + tkinterdnd2_datas,
    hiddenimports=(
        fishaudio_hiddenimports
        + httpx_hiddenimports
        + httpcore_hiddenimports
        + anyio_hiddenimports
        + dotenv_hiddenimports
        + tkinterdnd2_hiddenimports
    ),
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
    name='CapCutVideoTool',
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
    icon='assets/app_icon.ico',
    contents_directory='.',
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    Tree('capcut_template', prefix='capcut_template'),
    Tree('vendor/VOICEVOX', prefix='vendor/VOICEVOX'),
    Tree('vendor/auto_capcut_pro', prefix='vendor/auto_capcut_pro'),
    strip=False,
    upx=True,
    upx_exclude=[],
    name='CapCutVideoTool',
)
