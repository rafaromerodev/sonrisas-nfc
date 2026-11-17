"""Importación de la base de datos del programa anterior (v1, ``ong_usuarios.db``).

- No modifica el archivo de origen (se abre en solo lectura).
- Conserva **todas** las visitas. Las repetidas el mismo día (provocadas por la tarjeta
  apoyada en el lector en la versión anterior) se marcan como ``duplicada`` para que no
  cuenten en los informes, pero no se borran.
- Los datos antiguos se importan aunque no pasen la validación nueva (p. ej. letra del DNI
  incorrecta); se listan como avisos para revisarlos.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from sonrisas_nfc.db.database import FORMATO_FECHA, FORMATO_FECHA_HORA, Database, ahora, fecha_a_texto
from sonrisas_nfc.domain.models import OrigenVisita
from sonrisas_nfc.domain.validators import (
    ErrorValidacion,
    normalizar_documento,
    normalizar_uid,
    validar_documento,
)


@dataclass(slots=True)
class ResumenImportacion:
    beneficiarios: int = 0
    tarjetas: int = 0
    visitas: int = 0
    visitas_duplicadas: int = 0
    documentos_a_revisar: int = 0
    avisos: list[str] = field(default_factory=list)


class ErrorImportacion(Exception):
    pass


def es_bd_antigua(ruta: Path) -> bool:
    try:
        with sqlite3.connect(f"file:{ruta}?mode=ro", uri=True) as c:
            tablas = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not {"usuarios", "visitas"} <= tablas:
                return False
            columnas = {r[1] for r in c.execute("PRAGMA table_info(usuarios)")}
            return {"dni", "nombre", "apellidos"} <= columnas
    except sqlite3.Error:
        return False


def importar(origen: Path, db: Database) -> ResumenImportacion:
    if not es_bd_antigua(origen):
        raise ErrorImportacion("El archivo no parece una base de datos del programa anterior.")
    if db.conn.execute("SELECT COUNT(*) FROM beneficiarios").fetchone()[0]:
        raise ErrorImportacion(
            "La base de datos actual ya contiene beneficiarios; solo se puede importar en vacío."
        )

    src = sqlite3.connect(f"file:{origen}?mode=ro", uri=True)
    src.row_factory = sqlite3.Row
    try:
        columnas = {r[1] for r in src.execute("PRAGMA table_info(usuarios)")}
        usuarios = src.execute("SELECT * FROM usuarios").fetchall()
        visitas = src.execute("SELECT dni, fecha FROM visitas ORDER BY dni, fecha").fetchall()
    finally:
        src.close()

    res = ResumenImportacion()
    primera_visita: dict[str, str] = {}
    for v in visitas:
        primera_visita.setdefault(v["dni"], v["fecha"])

    ids: dict[str, int] = {}  # dni original -> id nuevo
    vistos: set[str] = set()
    momento = fecha_a_texto(ahora())
    with db.transaccion() as conn:
        for u in usuarios:
            dni_original = u["dni"]
            documento = normalizar_documento(dni_original)
            if not documento:
                res.avisos.append("Se omitió un usuario sin documento.")
                continue
            if documento in vistos:
                res.avisos.append(
                    f"Documento repetido tras normalizar: {documento} (se omitió el duplicado)."
                )
                continue
            vistos.add(documento)
            try:
                validar_documento(documento)
            except ErrorValidacion as e:
                res.documentos_a_revisar += 1
                res.avisos.append(f"{documento}: {e.mensaje}")

            creado = (
                _fecha_hora_valida(primera_visita.get(dni_original))
                or _fecha_hora_valida(u["ultima_visita"] if "ultima_visita" in columnas else None)
                or momento
            )
            cur = conn.execute(
                """INSERT INTO beneficiarios (documento, nombre, apellidos, telefono, expediente, adultos,
                       menores, mayores, zona, vencimiento, activo, creado_en, actualizado_en)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)""",
                (
                    documento,
                    _texto(u["nombre"]) or "(sin nombre)",
                    _texto(u["apellidos"]) or "(sin apellidos)",
                    _texto(u["telefono"]) or "",
                    _texto(u["expediente_social"]) if "expediente_social" in columnas else None,
                    _entero(u["adultos"]),
                    _entero(u["menores"]),
                    _entero(u["mayores"]),
                    _texto(u["zona"]),
                    _fecha_valida(u["vencimiento"]) if "vencimiento" in columnas else None,
                    creado,
                    momento,
                ),
            )
            ids[dni_original] = cur.lastrowid  # type: ignore[assignment]
            res.beneficiarios += 1

            if "card_uid" in columnas and u["card_uid"]:
                try:
                    uid = normalizar_uid(u["card_uid"])
                    conn.execute(
                        "INSERT INTO tarjetas (uid, beneficiario_id, asignada_en) VALUES (?, ?, ?)",
                        (uid, cur.lastrowid, creado),
                    )
                    res.tarjetas += 1
                except ErrorValidacion:
                    res.avisos.append(
                        f"{documento}: UID de tarjeta no válido ({u['card_uid']}), no se importó."
                    )
                except sqlite3.IntegrityError:
                    res.avisos.append(
                        f"{documento}: la tarjeta {u['card_uid']} ya estaba asignada a otra persona."
                    )

        ultimo_dia: dict[int, str] = {}
        for v in visitas:
            bid = ids.get(v["dni"])
            fecha = _fecha_hora_valida(v["fecha"])
            if bid is None or fecha is None:
                res.avisos.append(f"Visita omitida (sin usuario o fecha no válida): {v['dni']} {v['fecha']}")
                continue
            duplicada = ultimo_dia.get(bid) == fecha[:10]
            ultimo_dia[bid] = fecha[:10]
            conn.execute(
                "INSERT INTO visitas (beneficiario_id, fecha, origen, duplicada) VALUES (?, ?, ?, ?)",
                (bid, fecha, OrigenVisita.IMPORTADA.value, int(duplicada)),
            )
            res.visitas += 1
            res.visitas_duplicadas += duplicada

        db.registrar_cambio(
            "importacion",
            None,
            f"{origen.name}: {res.beneficiarios} beneficiarios, {res.visitas} visitas "
            f"({res.visitas_duplicadas} repetidas el mismo día), {res.tarjetas} tarjetas",
        )
    return res


def _texto(valor) -> str | None:
    texto = str(valor).strip() if valor is not None else ""
    return texto or None


def _entero(valor) -> int | None:
    try:
        n = int(str(valor).strip())
    except (TypeError, ValueError):
        return None
    return n if n >= 0 else None


def _fecha_valida(valor) -> str | None:
    try:
        return datetime.strptime(str(valor).strip()[:10], FORMATO_FECHA).strftime(FORMATO_FECHA)
    except (TypeError, ValueError):
        return None


def _fecha_hora_valida(valor) -> str | None:
    try:
        return datetime.strptime(str(valor).strip(), FORMATO_FECHA_HORA).strftime(FORMATO_FECHA_HORA)
    except (TypeError, ValueError):
        return None
