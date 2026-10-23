# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for the ReelVault PC workspace (single-file Windows exe).
# Build with scripts\build_pc_exe.bat (or: pyinstaller reelvault.spec --noconfirm).
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

hidden = collect_submodules("uvicorn") + collect_submodules("anthropic") + ["segno", "multipart", "python_multipart"]
datas = [("reelvault/static", "reelvault/static")] + collect_data_files("anthropic") + collect_data_files("certifi") + collect_data_files("segno")

a = Analysis(
    ["launcher/run_server.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas,
    [],
    name="ReelVault",
    debug=False,
    strip=False,
    upx=False,
    console=True,
    icon=None,
)
