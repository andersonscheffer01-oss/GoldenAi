# PyInstaller spec for the lightweight Desktop client. Core/data stay external.
from PyInstaller.utils.hooks import collect_submodules

hiddenimports = collect_submodules("PySide6.QtWebEngineCore")

a = Analysis(
    ["jarvis_desktop_launcher.py"],
    pathex=["."],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    excludes=["ollama", "MetaTrader5", "playwright"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name="Jarvis",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
)
