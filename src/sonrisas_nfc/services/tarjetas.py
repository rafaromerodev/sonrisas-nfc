"""Asignación de tarjetas NFC y reemplazo de tarjetas perdidas sin perder el historial."""

from __future__ import annotations

import sqlite3

from sonrisas_nfc.db.database import Database, ahora, fecha_a_texto, texto_a_fecha_hora
from sonrisas_nfc.domain.models import MotivoCambioTarjeta, Tarjeta
from sonrisas_nfc.domain.validators import ErrorValidacion, normalizar_uid


class TarjetasService:
    def __init__(self, db: Database) -> None:
        self.db = db

    def activa_por_uid(self, uid: str) -> Tarjeta | None:
        fila = self.db.conn.execute(
            "SELECT * FROM tarjetas WHERE uid = ? AND baja_en IS NULL", (normalizar_uid(uid),)
        ).fetchone()
        return _desde_fila(fila) if fila else None

    def ultima_de_baja_por_uid(self, uid: str) -> Tarjeta | None:
        fila = self.db.conn.execute(
            "SELECT * FROM tarjetas WHERE uid = ? AND baja_en IS NOT NULL ORDER BY baja_en DESC LIMIT 1",
            (normalizar_uid(uid),),
        ).fetchone()
        return _desde_fila(fila) if fila else None

    def historial(self, beneficiario_id: int) -> list[Tarjeta]:
        filas = self.db.conn.execute(
            "SELECT * FROM tarjetas WHERE beneficiario_id = ? ORDER BY asignada_en DESC, id DESC",
            (beneficiario_id,),
        )
        return [_desde_fila(f) for f in filas]

    def asignar(
        self,
        beneficiario_id: int,
        uid: str,
        motivo: MotivoCambioTarjeta = MotivoCambioTarjeta.PERDIDA,
    ) -> Tarjeta:
        """Asigna ``uid`` al beneficiario. Si ya tenía una tarjeta activa, la da de baja con ``motivo``.

        El historial de visitas está ligado al beneficiario (no a la tarjeta), así que se conserva íntegro.
        """
        uid = normalizar_uid(uid)
        momento = fecha_a_texto(ahora())
        with self.db.transaccion() as conn:
            benef = conn.execute(
                "SELECT activo FROM beneficiarios WHERE id = ?", (beneficiario_id,)
            ).fetchone()
            if benef is None:
                raise ErrorValidacion("id", "El beneficiario no existe.")
            if not benef["activo"]:
                raise ErrorValidacion(
                    "id", "El beneficiario está de baja. Reactívelo antes de asignarle tarjeta."
                )
            en_uso = conn.execute(
                """SELECT t.beneficiario_id, b.nombre, b.apellidos FROM tarjetas t
                   JOIN beneficiarios b ON b.id = t.beneficiario_id
                   WHERE t.uid = ? AND t.baja_en IS NULL""",
                (uid,),
            ).fetchone()
            if en_uso:
                if en_uso["beneficiario_id"] == beneficiario_id:
                    raise ErrorValidacion("uid", "Esta tarjeta ya es la tarjeta actual de este beneficiario.")
                raise ErrorValidacion(
                    "uid", f"Esta tarjeta ya pertenece a {en_uso['nombre']} {en_uso['apellidos']}."
                )
            anterior = _activa_de(conn, beneficiario_id)
            if anterior:
                conn.execute(
                    "UPDATE tarjetas SET baja_en = ?, motivo_baja = ? WHERE id = ?",
                    (momento, motivo.value, anterior["id"]),
                )
            cur = conn.execute(
                "INSERT INTO tarjetas (uid, beneficiario_id, asignada_en) VALUES (?, ?, ?)",
                (uid, beneficiario_id, momento),
            )
            detalle = f"{anterior['uid']} → {uid} ({motivo.value})" if anterior else f"Primera tarjeta: {uid}"
            self.db.registrar_cambio("cambio_tarjeta" if anterior else "tarjeta", beneficiario_id, detalle)
            fila = conn.execute("SELECT * FROM tarjetas WHERE id = ?", (cur.lastrowid,)).fetchone()
        return _desde_fila(fila)


def _activa_de(conn: sqlite3.Connection, beneficiario_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM tarjetas WHERE beneficiario_id = ? AND baja_en IS NULL", (beneficiario_id,)
    ).fetchone()


def _desde_fila(f: sqlite3.Row) -> Tarjeta:
    return Tarjeta(
        id=f["id"],
        uid=f["uid"],
        beneficiario_id=f["beneficiario_id"],
        asignada_en=texto_a_fecha_hora(f["asignada_en"]),  # type: ignore[arg-type]
        baja_en=texto_a_fecha_hora(f["baja_en"]),
        motivo_baja=f["motivo_baja"],
    )
