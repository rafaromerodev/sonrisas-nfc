"""Registro e historial de visitas (atenciones)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sonrisas_nfc.db.database import Database, ahora, fecha_a_texto, texto_a_fecha_hora
from sonrisas_nfc.domain.models import OrigenVisita, Visita


@dataclass(frozen=True, slots=True)
class VisitaReciente:
    visita: Visita
    beneficiario_id: int
    nombre_completo: str
    expediente: str | None


class VisitasService:
    def __init__(self, db: Database) -> None:
        self.db = db

    def visita_de_hoy(self, beneficiario_id: int, hoy: date | None = None) -> Visita | None:
        """Primera visita no duplicada del beneficiario en el día indicado (por defecto, hoy)."""
        dia = hoy or date.today()
        fila = self.db.conn.execute(
            """SELECT * FROM visitas WHERE beneficiario_id = ? AND duplicada = 0
               AND fecha >= ? AND fecha < ? ORDER BY fecha LIMIT 1""",
            (beneficiario_id, fecha_a_texto(dia), fecha_a_texto(dia + timedelta(days=1))),
        ).fetchone()
        return _desde_fila(fila) if fila else None

    def registrar(
        self,
        beneficiario_id: int,
        origen: OrigenVisita = OrigenVisita.TARJETA,
        momento: datetime | None = None,
    ) -> tuple[Visita, bool]:
        """Registra una atención. Devuelve ``(visita, es_nueva)``.

        Solo se cuenta una atención por persona y día: si ya existe, se devuelve la existente
        y no se crea otra. Esto evita que una tarjeta apoyada en el lector infle los informes.
        """
        momento = momento or ahora()
        with self.db.transaccion() as conn:
            existente = self.visita_de_hoy(beneficiario_id, momento.date())
            if existente:
                return existente, False
            cur = conn.execute(
                "INSERT INTO visitas (beneficiario_id, fecha, origen) VALUES (?, ?, ?)",
                (beneficiario_id, fecha_a_texto(momento), origen.value),
            )
            fila = conn.execute("SELECT * FROM visitas WHERE id = ?", (cur.lastrowid,)).fetchone()
        return _desde_fila(fila), True

    def historial(self, beneficiario_id: int, incluir_duplicadas: bool = False) -> list[Visita]:
        filtro = "" if incluir_duplicadas else " AND duplicada = 0"
        filas = self.db.conn.execute(
            f"SELECT * FROM visitas WHERE beneficiario_id = ?{filtro} ORDER BY fecha DESC", (beneficiario_id,)
        )
        return [_desde_fila(f) for f in filas]

    def recientes(self, limite: int = 12) -> list[VisitaReciente]:
        filas = self.db.conn.execute(
            """SELECT v.*, b.nombre, b.apellidos, b.expediente FROM visitas v
               JOIN beneficiarios b ON b.id = v.beneficiario_id
               WHERE v.duplicada = 0 ORDER BY v.fecha DESC, v.id DESC LIMIT ?""",
            (limite,),
        )
        return [
            VisitaReciente(
                _desde_fila(f), f["beneficiario_id"], f"{f['nombre']} {f['apellidos']}", f["expediente"]
            )
            for f in filas
        ]


def _desde_fila(f) -> Visita:
    return Visita(
        id=f["id"],
        beneficiario_id=f["beneficiario_id"],
        fecha=texto_a_fecha_hora(f["fecha"]),  # type: ignore[arg-type]
        origen=OrigenVisita(f["origen"]),
        duplicada=bool(f["duplicada"]),
    )
