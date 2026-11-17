# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Windows build of WiFi Fortress.

Build:  python -m PyInstaller packaging/windows/wifi-fortress.spec --noconfirm
Output: dist/WiFi Fortress/WiFi Fortress.exe  (one-folder build)
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# The spec is executed by PyInstaller with SPECPATH set to the folder that
# holds this file; the project root is two levels above it.
ROOT = Path(SPECPATH).resolve().parents[1]

datas = [
    (str(ROOT / "wififortress" / "resources" / "dictionaries"), "wififortress/resources/dictionaries"),
    (str(ROOT / "docs" / "screenshots"), "docs/screenshots"),
    (str(ROOT / "README.md"), "."),
    (str(ROOT / "packaging" / "windows" / "LICENSE.txt"), "."),
]
for package in ("PySide6", "pyqtgraph", "reportlab"):
    try:
        datas += collect_data_files(package)
    except Exception:  # optional / absent package
        pass

hiddenimports = collect_submodules("wififortress") + [
    "reportlab.pdfbase._fontdata",
    "reportlab.rl_settings",
    "pyqtgraph.graphicsItems.PlotItem",
    "PySide6.QtSvg",
]

block_cipher = None

a = Analysis(
    [str(ROOT / "run.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "unittest", "pytest", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets"],
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
    name="WiFi Fortress",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / "packaging" / "windows" / "wifi-fortress.ico"),
    version=str(ROOT / "packaging" / "windows" / "version_info.txt"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="WiFi Fortress",
)
