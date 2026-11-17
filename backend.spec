# -*- mode: python ; coding: utf-8 -*-

import sys
import os

block_cipher = None

a = Analysis(
    ['app.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        ('index.html', '.'),
        ('style.css', '.'),
        ('script.js', '.'),
        ('favicon.ico', '.'),
        ('build/icon.ico', 'build'),
        ('build/icon.png', 'build'),
    ],
    hiddenimports=[
        'agent',
        'sqlite3',
        'google.generativeai',
        'google.ai.generativelanguage',
        'google.protobuf',
        'google.auth',
        'pypdf',
        'docx',
        'flask',
        'flask_cors',
        'flask_limiter',
        'limits',
        'limits.storage',
        'werkzeug',
        'werkzeug.security',
        'jinja2',
        'markupsafe',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'numpy', 'scipy', 'pandas'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='nexus_backend',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True, # Keep console in onedir for clean stdout/stderr streaming into Electron
    icon='build/icon.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='nexus_backend',
)
