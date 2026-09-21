# PyInstaller spec for the lightweight Desktop client. Core/data stay external.
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules
import PySide6

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

# PyInstaller can collect older MSVC runtimes from unrelated scientific wheels
# into _internal. Qt then loads those before PySide6's matching runtime and
# fails with Windows status 0xc0000139 (entry point not found).
qt_root = Path(PySide6.__file__).resolve().parent
msvc_runtime_names = {
    "msvcp140.dll", "msvcp140_1.dll", "msvcp140_2.dll",
    "vcruntime140.dll", "vcruntime140_1.dll",
}
qt_conflicting_runtime_names = {
    "icuuc.dll", "icudt78.dll",
}
a.binaries = [item for item in a.binaries
              if Path(item[0]).name.lower() not in (
                  msvc_runtime_names | qt_conflicting_runtime_names)]
for runtime_name in sorted(msvc_runtime_names):
    runtime_path = qt_root / runtime_name
    if runtime_path.is_file():
        a.binaries.append((runtime_name, str(runtime_path), "BINARY"))

pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], [], [],
    name="Jarvis",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    exclude_binaries=True,
)
coll = COLLECT(
    exe, a.binaries, a.datas,
    strip=False,
    upx=True,
    name="Jarvis",
)
