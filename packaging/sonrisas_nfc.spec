# -*- mode: python ; coding: utf-8 -*-
# Empaquetado con PyInstaller (carpeta, arranque rápido).  Uso:  pyinstaller packaging/sonrisas_nfc.spec
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

raiz = Path(SPECPATH).parent  # noqa: F821 (variable inyectada por PyInstaller)

a = Analysis(
    [str(raiz / "src" / "sonrisas_nfc" / "__main__.py")],
    pathex=[str(raiz / "src")],
    datas=collect_data_files("sonrisas_nfc"),
    hiddenimports=["smartcard.scard"],
    excludes=["tkinter", "PySide6.QtWebEngineCore", "PySide6.QtQml", "PySide6.Qt3DCore", "PySide6.QtMultimedia"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SonrisasNFC",
    console=False,
    icon=str(raiz / "src" / "sonrisas_nfc" / "assets" / "sonrisas.ico"),
    version=None,
)
coll = COLLECT(exe, a.binaries, a.datas, name="SonrisasNFC")
