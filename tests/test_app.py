"""Búsqueda de la base de datos del programa anterior en el primer arranque."""

import os
import sqlite3
import time

from sonrisas_nfc import app
from tests.test_importador import ESQUEMA_V1


def _bd_antigua(ruta):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(ruta) as c:
        c.executescript(ESQUEMA_V1)
    return ruta


def test_encuentra_la_bd_antigua_mas_reciente(tmp_path, monkeypatch):
    escritorio = tmp_path / "Desktop"
    vieja = _bd_antigua(escritorio / "copia_vieja" / "ong_usuarios.db")
    actual = _bd_antigua(escritorio / "ONG_NFC_Deploy_APP" / "dist" / "ONG_Sonrisas" / "ong_usuarios.db")
    hace_un_mes = time.time() - 30 * 86400
    os.utime(vieja, (hace_un_mes, hace_un_mes))
    (escritorio / "otra.db").write_bytes(b"no es sqlite")

    monkeypatch.setattr(app.Path, "home", lambda: tmp_path)
    monkeypatch.setenv("SYSTEMDRIVE", str(tmp_path / "no_existe"))
    monkeypatch.chdir(tmp_path)
    assert app._buscar_bd_antigua() == actual


def test_sin_bd_antigua(tmp_path, monkeypatch):
    monkeypatch.setattr(app.Path, "home", lambda: tmp_path)
    monkeypatch.setenv("SYSTEMDRIVE", str(tmp_path / "no_existe"))
    monkeypatch.chdir(tmp_path)
    assert app._buscar_bd_antigua() is None
