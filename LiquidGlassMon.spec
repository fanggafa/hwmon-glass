# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec: one-file windowed exe with the sensor runtime inside.

Everything a user needs ships in the binary: Python, the packages, the
LibreHardwareMonitor assemblies, and the PawnIO installer. The only thing that
cannot ride along is the kernel driver itself, which is installed on first run
through a UAC prompt.
"""

import os
import sys

block_cipher = None

ROOT = os.path.abspath(os.getcwd())

# LibreHardwareMonitor assemblies (downloaded by fetch_deps.py, not committed)
lib_dlls = []
lib_dir = os.path.join(ROOT, "lib")
if os.path.isdir(lib_dir):
    for name in os.listdir(lib_dir):
        if name.lower().endswith(".dll"):
            lib_dlls.append((os.path.join(lib_dir, name), "lib"))

# The PawnIO installer rides along so the app can offer a one-click setup.
assets = []
pawnio = os.path.join(ROOT, "assets", "PawnIO_setup.exe")
if os.path.exists(pawnio):
    assets.append((pawnio, "assets"))

a = Analysis(
    ["main.py"],
    pathex=[ROOT],
    # The assemblies go in as binaries only. Listing the whole lib/ directory
    # under `datas` as well packed every DLL twice and added ~3.8 MB to the
    # executable for nothing.
    binaries=lib_dlls,
    datas=assets,
    hiddenimports=[
        "clr",
        "pystray._win32",
        "PIL._tkinter_finder",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "scipy", "pandas", "IPython", "pytest"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="LiquidGlassMon",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # no console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
    uac_admin=True,         # ask for elevation on launch: needed for MSR/SuperIO
)
