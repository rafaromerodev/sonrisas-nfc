"""Rutas y parámetros de la aplicación.

Los datos se guardan en el perfil del usuario de Windows (``%LOCALAPPDATA%``) y no junto
al ejecutable: así una reinstalación o actualización nunca sobrescribe la base de datos,
y el programa funciona aunque esté instalado en ``Program Files`` (carpeta de solo lectura).
"""

from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "Sonrisas NFC"
ORG_NAME = "ONG Sonrisas Canarias"

#: Días antes del vencimiento a partir de los cuales un expediente se marca "por vencer".
DIAS_AVISO_VENCIMIENTO = 30
#: Opciones rápidas de renovación de expediente (meses).
MESES_RENOVACION = (6, 12)
#: Copias de seguridad automáticas: frecuencia y cuántas se conservan.
HORAS_ENTRE_COPIAS = 24
COPIAS_A_CONSERVAR = 30

ASSETS_DIR = Path(__file__).resolve().parent / "assets"


def data_dir() -> Path:
    """Carpeta de datos. Se puede redirigir con la variable ``SONRISAS_DATA_DIR``."""
    override = os.environ.get("SONRISAS_DATA_DIR")
    if override:
        base = Path(override)
    else:
        local = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".local" / "share")
        base = Path(local) / "SonrisasCanarias" / "NFC"
    base.mkdir(parents=True, exist_ok=True)
    return base


def db_path() -> Path:
    return data_dir() / "sonrisas.db"


def backups_dir() -> Path:
    d = data_dir() / "copias"
    d.mkdir(exist_ok=True)
    return d


def logs_dir() -> Path:
    d = data_dir() / "logs"
    d.mkdir(exist_ok=True)
    return d
