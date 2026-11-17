from __future__ import annotations

import pytest

from sonrisas_nfc.domain.models import Beneficiario
from sonrisas_nfc.services.contexto import Servicios


@pytest.fixture(autouse=True)
def carpeta_datos_temporal(tmp_path, monkeypatch):
    """Ninguna prueba debe tocar la carpeta de datos real (%LOCALAPPDATA%)."""
    monkeypatch.setenv("SONRISAS_DATA_DIR", str(tmp_path / "datos_app"))


@pytest.fixture
def servicios(tmp_path) -> Servicios:
    s = Servicios.crear(tmp_path / "test.db")
    yield s
    s.db.close()


@pytest.fixture
def datos() -> Beneficiario:
    return Beneficiario(
        documento="12345678Z",
        nombre="Ana",
        apellidos="Pérez García",
        telefono="612345678",
        expediente="EXP-001",
        adultos=2,
        menores=1,
        mayores=0,
        zona="Valleseco",
    )
