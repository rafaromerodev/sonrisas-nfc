from datetime import date

import pytest

from sonrisas_nfc.domain.models import sumar_meses
from sonrisas_nfc.domain.validators import (
    ErrorValidacion,
    TipoDocumento,
    normalizar_uid,
    tipo_documento,
    validar_documento,
    validar_telefono,
)


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("12345678Z", "12345678Z"),
        ("12.345.678-z", "12345678Z"),
        ("x1234567l", "X1234567L"),
        ("AB123456", "AB123456"),
    ],
)
def test_documentos_validos(entrada, esperado):
    assert validar_documento(entrada) == esperado


@pytest.mark.parametrize("entrada", ["12345678A", "X1234567A", "12345678", "", "AB-1", "ÑÑÑÑÑÑ"])
def test_documentos_invalidos(entrada):
    with pytest.raises(ErrorValidacion):
        validar_documento(entrada)


def test_mensaje_sugiere_letra_correcta():
    with pytest.raises(ErrorValidacion, match="debería ser Z"):
        validar_documento("12345678A")


def test_tipo_documento():
    assert tipo_documento("12345678Z") is TipoDocumento.DNI
    assert tipo_documento("Y1234567X") is TipoDocumento.NIE
    assert tipo_documento("PA1234567") is TipoDocumento.OTRO


@pytest.mark.parametrize("entrada", ["612345678", "612 34 56 78", "+34 612345678", "0034612345678"])
def test_telefono_valido(entrada):
    assert validar_telefono(entrada) == "612345678"


@pytest.mark.parametrize("entrada", ["", "61234567", "6123456789", "abc"])
def test_telefono_invalido(entrada):
    with pytest.raises(ErrorValidacion):
        validar_telefono(entrada)


@pytest.mark.parametrize("entrada", ["04a1b2c3", "04:A1:B2:C3", "04 a1 b2 c3", "04-A1-B2-C3"])
def test_normalizar_uid(entrada):
    assert normalizar_uid(entrada) == "04 A1 B2 C3"


@pytest.mark.parametrize("entrada", ["", "XYZ", "04A", "GG 00"])
def test_uid_invalido(entrada):
    with pytest.raises(ErrorValidacion):
        normalizar_uid(entrada)


@pytest.mark.parametrize(
    ("inicio", "meses", "esperado"),
    [
        (date(2026, 1, 31), 1, date(2026, 2, 28)),
        (date(2024, 1, 31), 1, date(2024, 2, 29)),
        (date(2026, 8, 15), 6, date(2027, 2, 15)),
        (date(2026, 12, 31), 12, date(2027, 12, 31)),
        (date(2026, 7, 1), 6, date(2027, 1, 1)),
    ],
)
def test_sumar_meses(inicio, meses, esperado):
    assert sumar_meses(inicio, meses) == esperado
