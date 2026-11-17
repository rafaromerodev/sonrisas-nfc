"""Importación desde el esquema del programa anterior (con datos ficticios)."""

import sqlite3

import pytest

from sonrisas_nfc.services.atencion import Resultado
from sonrisas_nfc.services.importador import ErrorImportacion, es_bd_antigua, importar

ESQUEMA_V1 = """
CREATE TABLE usuarios(
    dni TEXT PRIMARY KEY, nombre TEXT NOT NULL, apellidos TEXT NOT NULL, telefono TEXT NOT NULL,
    adultos TEXT, menores TEXT, mayores TEXT, zona TEXT, expediente_social TEXT,
    vencimiento TEXT, ultima_visita TEXT, card_uid TEXT);
CREATE TABLE visitas(dni TEXT NOT NULL, fecha TEXT NOT NULL);
"""


@pytest.fixture
def bd_antigua(tmp_path):
    ruta = tmp_path / "ong_usuarios.db"
    with sqlite3.connect(ruta) as c:
        c.executescript(ESQUEMA_V1)
        c.executemany(
            "INSERT INTO usuarios VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                ("12345678Z", "Ana", "Pérez", "612345678", "2", "1", "", "Valleseco", "E1",
                 "2026-12-01", "2026-05-02 10:00:00", "04 A1 B2 C3"),
                ("12345678A", "Luis", "Díaz", "622345678", "abc", None, None, None, "E2",
                 "2025-01-01", "2026-05-02 10:00:00", "04 D4 E5 F6"),
            ],
        )  # fmt: skip
        c.executemany(
            "INSERT INTO visitas VALUES (?, ?)",
            [
                ("12345678Z", "2026-05-01 10:00:00"),
                ("12345678Z", "2026-05-01 10:00:02"),  # repetida por el lector
                ("12345678Z", "2026-05-01 10:00:04"),  # repetida por el lector
                ("12345678Z", "2026-05-08 11:00:00"),
                ("12345678A", "2026-05-02 10:00:00"),
                ("NOEXISTE", "2026-05-02 10:00:00"),
            ],
        )
    return ruta


def test_detecta_bd_antigua(bd_antigua, tmp_path):
    assert es_bd_antigua(bd_antigua)
    otra = tmp_path / "otra.db"
    sqlite3.connect(otra).close()
    assert not es_bd_antigua(otra)


def test_importa_conservando_todo_y_marcando_repetidas(servicios, bd_antigua):
    res = importar(bd_antigua, servicios.db)
    assert res.beneficiarios == 2
    assert res.tarjetas == 2
    assert res.visitas == 5
    assert res.visitas_duplicadas == 2
    assert res.documentos_a_revisar == 1  # 12345678A tiene la letra mal

    ana = servicios.beneficiarios.obtener_por_documento("12345678Z")
    assert ana.total_visitas == 2  # las repetidas no cuentan
    assert len(servicios.visitas.historial(ana.id, incluir_duplicadas=True)) == 4
    assert (ana.adultos, ana.menores, ana.mayores) == (2, 1, None)
    assert str(ana.creado_en) == "2026-05-01 10:00:00"

    luis = servicios.beneficiarios.obtener_por_documento("12345678A")
    assert luis.adultos is None  # "abc" no es un número

    # Las tarjetas siguen funcionando tras la importación
    r = servicios.atencion.procesar_tarjeta("04a1b2c3")
    assert r.beneficiario.id == ana.id
    assert r.resultado in {Resultado.VISITA_REGISTRADA, Resultado.YA_ATENDIDO_HOY}


def test_no_importa_sobre_datos_existentes(servicios, bd_antigua, datos):
    servicios.beneficiarios.crear(datos)
    with pytest.raises(ErrorImportacion):
        importar(bd_antigua, servicios.db)


def test_no_modifica_el_origen(servicios, bd_antigua):
    antes = bd_antigua.read_bytes()
    importar(bd_antigua, servicios.db)
    assert bd_antigua.read_bytes() == antes
