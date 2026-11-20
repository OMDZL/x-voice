# -*- mode: python ; coding: utf-8 -*-
"""One-folder Windows build.

onnxruntime ships native DLLs. Packing those into a single exe means Windows
extracts them to a temp folder on every launch, and that extract is a common
place for the app to fail. A folder next to x-voice.exe keeps the DLLs where
the runtime expects them. UPX is off for the same reason: compressing those
DLLs often stops them from loading.
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_all

root = Path(SPECPATH)
datas = [
    (str(root / "models"), "models"),
    (str(root / "third_party" / "wakewords" / "computer_v2.onnx"), "models"),
    (str(root / "third_party" / "wakewords" / "LICENSE.txt"), "third_party/wakewords"),
    (str(root / "assets" / "x-voice.ico"), "assets"),
]
binaries = []
hiddenimports = [
    "xvoice",
    "xvoice.app",
    "xvoice.gui",
    "xvoice.tray",
    "xvoice.service",
    "xvoice.audio",
    "xvoice.automator",
    "xvoice.chime",
    "xvoice.config",
    "xvoice.deeplink",
    "xvoice.detector",
    "xvoice.guard",
    "xvoice.launcher",
    "xvoice.models",
    "xvoice.startup",
    "xvoice.windowmatch",
    "xvoice.custom_model",
    "tkinter",
    "tkinter.ttk",
    "openwakeword",
    "openwakeword.model",
    "openwakeword.utils",
    "openwakeword.vad",
    "openwakeword.custom_verifier_model",
    "onnxruntime",
    "sklearn",
    "sklearn.linear_model",
    "sklearn.pipeline",
    "sklearn.preprocessing",
    "scipy",
    "sounddevice",
    "numpy",
    "pystray",
    "pystray._win32",
    "pystray._util",
    "pystray._util.win32",
    "pystray._base",
    "PIL",
    "PIL.Image",
    "PIL.ImageDraw",
    "six",
    "comtypes",
    "comtypes.client",
    "comtypes.stream",
    "pywinauto",
    "pywinauto.controls.uiawrapper",
    "win32api",
    "win32con",
    "win32gui",
    "pywintypes",
    "pythoncom",
]

for package in ("onnxruntime", "sounddevice", "numpy", "scipy", "sklearn", "PIL"):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(package)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden

a = Analysis(
    [str(root / "xvoice" / "__main__.py")],
    pathex=[str(root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["xvoice.setup_models"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="x-voice",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=True,
    # Shown by Explorer and a pinned taskbar button even when x-voice is closed.
    icon=str(root / "assets" / "x-voice.ico"),
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="x-voice",
)
