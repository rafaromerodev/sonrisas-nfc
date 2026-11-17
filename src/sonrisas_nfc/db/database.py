"""Conexión SQLite, transacciones y migraciones de esquema versionadas.

Cada migración se aplica una sola vez y se registra en ``PRAGMA user_version``.
Para cambiar el esquema en el futuro basta con añadir una entrada nueva a ``MIGRACIONES``.
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path

log = logging.getLogger(__name__)

FORMATO_FECHA = "%Y-%m-%d"
FORMATO_FECHA_HORA = "%Y-%m-%d %H:%M:%S"

MIGRACIONES: dict[int, str] = {
    1: """
    CREATE TABLE beneficiarios (
        id              INTEGER PRIMARY KEY,
        documento       TEXT    NOT NULL UNIQUE,
        nombre          TEXT    NOT NULL,
        apellidos       TEXT    NOT NULL,
        telefono        TEXT    NOT NULL,
        expediente      TEXT,
        adultos         INTEGER CHECK (adultos IS NULL OR adultos >= 0),
        menores         INTEGER CHECK (menores IS NULL OR menores >= 0),
        mayores         INTEGER CHECK (mayores IS NULL OR mayores >= 0),
        zona            TEXT,
        vencimiento     TEXT,
        notas           TEXT,
        activo          INTEGER NOT NULL DEFAULT 1,
        creado_en       TEXT    NOT NULL,
        actualizado_en  TEXT    NOT NULL
    );
    CREATE INDEX ix_beneficiarios_expediente ON beneficiarios(expediente);

    -- Historial de tarjetas: una tarjeta perdida se da de baja (no se borra) y
    -- el beneficiario conserva su id, por lo que sus visitas no se pierden.
    CREATE TABLE tarjetas (
        id              INTEGER PRIMARY KEY,
        uid             TEXT    NOT NULL,
        beneficiario_id INTEGER NOT NULL REFERENCES beneficiarios(id) ON DELETE CASCADE,
        asignada_en     TEXT    NOT NULL,
        baja_en         TEXT,
        motivo_baja     TEXT
    );
    CREATE UNIQUE INDEX ux_tarjetas_uid_activa ON tarjetas(uid) WHERE baja_en IS NULL;
    CREATE UNIQUE INDEX ux_tarjetas_beneficiario_activa ON tarjetas(beneficiario_id) WHERE baja_en IS NULL;
    CREATE INDEX ix_tarjetas_uid ON tarjetas(uid);

    CREATE TABLE visitas (
        id              INTEGER PRIMARY KEY,
        beneficiario_id INTEGER NOT NULL REFERENCES beneficiarios(id) ON DELETE CASCADE,
        fecha           TEXT    NOT NULL,
        origen          TEXT    NOT NULL CHECK (origen IN ('tarjeta', 'manual', 'alta', 'importada')),
        duplicada       INTEGER NOT NULL DEFAULT 0
    );
    CREATE INDEX ix_visitas_beneficiario_fecha ON visitas(beneficiario_id, fecha);
    CREATE INDEX ix_visitas_fecha ON visitas(fecha);

    -- Registro de cambios relevantes (altas, ediciones, cambios de tarjeta, bajas...).
    CREATE TABLE registro_cambios (
        id              INTEGER PRIMARY KEY,
        fecha           TEXT    NOT NULL,
        accion          TEXT    NOT NULL,
        beneficiario_id INTEGER REFERENCES beneficiarios(id) ON DELETE SET NULL,
        detalle         TEXT
    );
    CREATE INDEX ix_registro_cambios_beneficiario ON registro_cambios(beneficiario_id);
    """,
}

VERSION_ESQUEMA = max(MIGRACIONES)


def ahora() -> datetime:
    return datetime.now().replace(microsecond=0)


def fecha_a_texto(valor: date | datetime | None) -> str | None:
    if valor is None:
        return None
    if isinstance(valor, datetime):
        return valor.strftime(FORMATO_FECHA_HORA)
    return valor.strftime(FORMATO_FECHA)


def texto_a_fecha(valor: str | None) -> date | None:
    return datetime.strptime(valor[:10], FORMATO_FECHA).date() if valor else None


def texto_a_fecha_hora(valor: str | None) -> datetime | None:
    return datetime.strptime(valor, FORMATO_FECHA_HORA) if valor else None


class Database:
    """Envoltorio fino sobre ``sqlite3`` con transacciones explícitas."""

    def __init__(self, path: Path | str) -> None:
        self.path = str(path)
        # isolation_level=None: autocommit; las transacciones se abren con ``transaccion()``.
        self.conn = sqlite3.connect(self.path, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA synchronous = FULL")
        self._en_transaccion = False

    @contextmanager
    def transaccion(self) -> Iterator[sqlite3.Connection]:
        """Ejecuta un bloque de forma atómica; admite anidamiento (el externo manda)."""
        if self._en_transaccion:
            yield self.conn
            return
        self._en_transaccion = True
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            yield self.conn
        except BaseException:
            self.conn.execute("ROLLBACK")
            raise
        else:
            self.conn.execute("COMMIT")
        finally:
            self._en_transaccion = False

    @property
    def version(self) -> int:
        return self.conn.execute("PRAGMA user_version").fetchone()[0]

    def migrar(self) -> None:
        actual = self.version
        for version in sorted(v for v in MIGRACIONES if v > actual):
            log.info("Aplicando migración de esquema %s", version)
            with self.transaccion() as conn:
                for sentencia in _sentencias(MIGRACIONES[version]):
                    conn.execute(sentencia)
                conn.execute(f"PRAGMA user_version = {version}")

    def registrar_cambio(self, accion: str, beneficiario_id: int | None, detalle: str = "") -> None:
        self.conn.execute(
            "INSERT INTO registro_cambios (fecha, accion, beneficiario_id, detalle) VALUES (?, ?, ?, ?)",
            (fecha_a_texto(ahora()), accion, beneficiario_id, detalle),
        )

    def copiar_a(self, destino: Path | str) -> None:
        """Copia consistente de la base de datos (API de backup de SQLite, segura en caliente)."""
        copia = sqlite3.connect(str(destino))
        try:
            self.conn.backup(copia)
        finally:
            copia.close()

    def close(self) -> None:
        self.conn.close()


def abrir(path: Path | str) -> Database:
    db = Database(path)
    db.migrar()
    return db


def _sentencias(script: str) -> list[str]:
    """Divide un script SQL en sentencias (sin ``executescript``, que hace COMMIT implícito)."""
    sentencias, actual = [], []
    for linea in script.splitlines():
        if linea.strip().startswith("--"):
            continue
        actual.append(linea)
        if sqlite3.complete_statement("\n".join(actual)):
            sentencias.append("\n".join(actual).strip())
            actual = []
    return [s for s in sentencias if s]
