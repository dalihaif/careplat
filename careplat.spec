# -*- mode: python ; coding: utf-8 -*-
"""照护管理平台 · PyInstaller 打包配置
用法：打包.bat  （或 python -m PyInstaller careplat.spec --noconfirm）
产物：dist/照护管理平台/ 目录（含 exe + 模板 + 静态资源），整个文件夹拷走就能用
"""
import os

block_cipher = None

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[],
    datas=[
        # (源, 打进包后的相对目录)
        ('templates', 'templates'),
        ('static', 'static'),
    ],
    hiddenimports=[
        'waitress',
        'PIL._tkinter_finder',
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=['tkinter', 'unittest', 'pydoc_data'],
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name='照护管理平台',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,          # 保留控制台窗口：启动 banner 和访问地址都在这里
    icon='static/icon.ico' if os.path.exists('static/icon.ico') else None,
)
coll = COLLECT(
    exe, a.binaries, a.zipfiles, a.datas,
    strip=False, upx=False,
    name='照护管理平台',
)
