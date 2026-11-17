"""Copias de seguridad automáticas y manuales de la base de datos."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from pathlib import Path

from sonrisas_nfc.db.database import Database

log = logging.getLogger(__name__)

_PREFIJO = "sonrisas_"
_FORMATO = "%Y-%m-%d_%H%M%S"


def crear_copia(db: Database, carpeta: Path) -> Path:
    carpeta.mkdir(parents=True, exist_ok=True)
    destino = carpeta / f"{_PREFIJO}{datetime.now():{_FORMATO}}.db"
    db.copiar_a(destino)
    log.info("Copia de seguridad creada: %s", destino)
    return destino


def listar_copias(carpeta: Path) -> list[Path]:
    return sorted(carpeta.glob(f"{_PREFIJO}*.db"), reverse=True)


def ultima_copia(carpeta: Path) -> datetime | None:
    copias = listar_copias(carpeta)
    return datetime.fromtimestamp(copias[0].stat().st_mtime) if copias else None


def copia_automatica(db: Database, carpeta: Path, cada_horas: int, conservar: int) -> Path | None:
    """Crea una copia si la última tiene más de ``cada_horas`` y elimina las más antiguas."""
    ultima = ultima_copia(carpeta)
    nueva = None
    if ultima is None or datetime.now() - ultima >= timedelta(hours=cada_horas):
        nueva = crear_copia(db, carpeta)
    for vieja in listar_copias(carpeta)[conservar:]:
        try:
            vieja.unlink()
        except OSError:
            log.warning("No se pudo borrar la copia antigua %s", vieja)
    return nueva
