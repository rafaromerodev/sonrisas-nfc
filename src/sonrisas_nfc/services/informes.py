"""Estadísticas para el panel de inicio e informes por periodo (PDF/CSV)."""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import Enum
from pathlib import Path

from sonrisas_nfc.config import DIAS_AVISO_VENCIMIENTO
from sonrisas_nfc.db.database import Database, fecha_a_texto, texto_a_fecha
from sonrisas_nfc.domain.models import clave_natural


@dataclass(frozen=True, slots=True)
class Resumen:
    """Cifras del panel de inicio."""

    atenciones_hoy: int
    atenciones_mes: int
    activos: int
    vencidos: int
    por_vencer: int
    sin_tarjeta: int


@dataclass(frozen=True, slots=True)
class FilaZona:
    zona: str
    personas: int
    atenciones: int


@dataclass(frozen=True, slots=True)
class FilaDetalle:
    beneficiario_id: int
    expediente: str
    documento: str
    nombre_completo: str
    zona: str
    atenciones: int
    ultima: date


class OrdenDetalle(Enum):
    """Órdenes disponibles para la relación de expedientes (el primero es el predeterminado)."""

    EXPEDIENTE_ASC = "Nº de expediente (menor a mayor)"
    EXPEDIENTE_DESC = "Nº de expediente (mayor a menor)"
    MAS_ATENCIONES = "Más atenciones primero"
    MENOS_ATENCIONES = "Menos atenciones primero"
    ULTIMA_RECIENTE = "Última atención más reciente"
    NOMBRE = "Nombre (A-Z)"


class Apariciones(Enum):
    """Filtro por número de veces que la persona ha sido atendida en el periodo."""

    TODAS = ("Todas", 1, None)
    UNA = ("Solo 1 vez", 1, 1)
    DOS_O_MAS = ("2 o más veces", 2, None)
    CINCO_O_MAS = ("5 o más veces", 5, None)
    DIEZ_O_MAS = ("10 o más veces", 10, None)

    @property
    def etiqueta(self) -> str:
        return self.value[0]

    def admite(self, n: int) -> bool:
        minimo, maximo = self.value[1], self.value[2]
        return n >= minimo and (maximo is None or n <= maximo)


def _clave_orden(orden: OrdenDetalle):
    exp = lambda d: (clave_natural(d.expediente), clave_natural(d.documento))  # noqa: E731
    return {
        OrdenDetalle.EXPEDIENTE_ASC: (exp, False),
        OrdenDetalle.EXPEDIENTE_DESC: (exp, True),
        OrdenDetalle.MAS_ATENCIONES: (lambda d: (-d.atenciones, exp(d)), False),
        OrdenDetalle.MENOS_ATENCIONES: (lambda d: (d.atenciones, exp(d)), False),
        OrdenDetalle.ULTIMA_RECIENTE: (lambda d: (d.ultima, exp(d)), True),
        OrdenDetalle.NOMBRE: (lambda d: (clave_natural(d.nombre_completo), exp(d)), False),
    }[orden]


def filtrar_detalle(
    detalle: list[FilaDetalle],
    texto: str = "",
    apariciones: Apariciones = Apariciones.TODAS,
    orden: OrdenDetalle = OrdenDetalle.EXPEDIENTE_ASC,
) -> list[FilaDetalle]:
    """Filtra por texto (expediente, documento o nombre) y nº de apariciones, y ordena.

    Un expediente o documento escrito completo encuentra solo esa coincidencia exacta
    (``"45"`` no devuelve el ``"145"``); cualquier otro texto busca coincidencias parciales.
    """
    filas = [d for d in detalle if apariciones.admite(d.atenciones)]
    buscado = (texto or "").strip().upper()
    if buscado:
        exactas = [d for d in filas if buscado in (d.expediente.upper(), d.documento.upper())]
        filas = exactas or [
            d
            for d in filas
            if buscado in d.expediente.upper()
            or buscado in d.documento.upper()
            or buscado in d.nombre_completo.upper()
        ]
    clave, inverso = _clave_orden(orden)
    if orden is OrdenDetalle.EXPEDIENTE_DESC:
        # Los que no tienen expediente siguen al final también en orden inverso.
        con = sorted((d for d in filas if d.expediente), key=clave, reverse=True)
        return con + [d for d in filas if not d.expediente]
    return sorted(filas, key=clave, reverse=inverso)


@dataclass(slots=True)
class Informe:
    desde: date
    hasta: date
    atenciones: int = 0
    personas_unicas: int = 0
    altas_nuevas: int = 0
    adultos: int = 0
    menores: int = 0
    mayores: int = 0
    por_zona: list[FilaZona] = field(default_factory=list)
    por_dia_semana: list[int] = field(default_factory=lambda: [0] * 7)  # lunes..domingo
    detalle: list[FilaDetalle] = field(default_factory=list)
    #: Si el detalle se ha filtrado al exportar, descripción del filtro (se imprime en el PDF).
    filtro_detalle: str = ""

    @property
    def personas_atendidas_hogar(self) -> int:
        return self.adultos + self.menores + self.mayores


class InformesService:
    def __init__(self, db: Database) -> None:
        self.db = db

    def resumen(self, hoy: date | None = None) -> Resumen:
        hoy = hoy or date.today()
        manana = fecha_a_texto(hoy + timedelta(days=1))
        inicio_mes = fecha_a_texto(hoy.replace(day=1))
        limite_aviso = fecha_a_texto(hoy + timedelta(days=DIAS_AVISO_VENCIMIENTO))
        c = self.db.conn
        uno = lambda sql, *p: c.execute(sql, p).fetchone()[0]  # noqa: E731
        return Resumen(
            atenciones_hoy=uno(
                "SELECT COUNT(*) FROM visitas WHERE duplicada = 0 AND fecha >= ? AND fecha < ?",
                fecha_a_texto(hoy), manana,
            ),
            atenciones_mes=uno(
                "SELECT COUNT(*) FROM visitas WHERE duplicada = 0 AND fecha >= ? AND fecha < ?", inicio_mes, manana
            ),
            activos=uno("SELECT COUNT(*) FROM beneficiarios WHERE activo = 1"),
            vencidos=uno(
                "SELECT COUNT(*) FROM beneficiarios WHERE activo = 1 AND vencimiento < ?", fecha_a_texto(hoy)
            ),
            por_vencer=uno(
                "SELECT COUNT(*) FROM beneficiarios WHERE activo = 1 AND vencimiento >= ? AND vencimiento <= ?",
                fecha_a_texto(hoy), limite_aviso,
            ),
            sin_tarjeta=uno(
                """SELECT COUNT(*) FROM beneficiarios b WHERE activo = 1 AND NOT EXISTS
                   (SELECT 1 FROM tarjetas t WHERE t.beneficiario_id = b.id AND t.baja_en IS NULL)"""
            ),
        )  # fmt: skip

    def generar(self, desde: date, hasta: date) -> Informe:
        if desde > hasta:
            raise ValueError("La fecha inicial no puede ser posterior a la final.")
        rango = (fecha_a_texto(desde), fecha_a_texto(hasta + timedelta(days=1)))
        c = self.db.conn
        inf = Informe(desde, hasta)
        filtro = "v.duplicada = 0 AND v.fecha >= ? AND v.fecha < ?"

        inf.atenciones, inf.personas_unicas = c.execute(
            f"SELECT COUNT(*), COUNT(DISTINCT beneficiario_id) FROM visitas v WHERE {filtro}", rango
        ).fetchone()
        inf.altas_nuevas = c.execute(
            "SELECT COUNT(*) FROM beneficiarios WHERE creado_en >= ? AND creado_en < ?", rango
        ).fetchone()[0]
        adultos, menores, mayores = c.execute(
            f"""SELECT COALESCE(SUM(adultos),0), COALESCE(SUM(menores),0), COALESCE(SUM(mayores),0)
                FROM beneficiarios WHERE id IN (SELECT beneficiario_id FROM visitas v WHERE {filtro})""",
            rango,
        ).fetchone()
        inf.adultos, inf.menores, inf.mayores = adultos, menores, mayores

        inf.por_zona = [
            FilaZona(f[0], f[1], f[2])
            for f in c.execute(
                f"""SELECT COALESCE(NULLIF(TRIM(b.zona), ''), 'Sin indicar') AS zona,
                           COUNT(DISTINCT v.beneficiario_id), COUNT(*)
                    FROM visitas v JOIN beneficiarios b ON b.id = v.beneficiario_id
                    WHERE {filtro} GROUP BY 1 ORDER BY 3 DESC, 1""",
                rango,
            )
        ]
        for dia, total in c.execute(
            f"SELECT CAST(strftime('%w', v.fecha) AS INTEGER), COUNT(*) FROM visitas v WHERE {filtro} GROUP BY 1",
            rango,
        ):
            inf.por_dia_semana[(dia + 6) % 7] = total  # SQLite: 0 = domingo

        inf.detalle = filtrar_detalle([
            FilaDetalle(
                f["id"], f["expediente"] or "", f["documento"], f"{f['nombre']} {f['apellidos']}",
                f["zona"] or "", f["atenciones"], texto_a_fecha(f["ultima"]),
            )
            for f in c.execute(
                f"""SELECT b.id, b.expediente, b.documento, b.nombre, b.apellidos, b.zona,
                           COUNT(*) AS atenciones, MAX(v.fecha) AS ultima
                    FROM visitas v JOIN beneficiarios b ON b.id = v.beneficiario_id
                    WHERE {filtro} GROUP BY b.id""",
                rango,
            )
        ])  # fmt: skip
        return inf


def exportar_csv(informe: Informe, destino: Path) -> None:
    """CSV con ``;`` y BOM para que Excel en español lo abra directamente."""
    with open(destino, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["Expediente", "Documento", "Nombre y apellidos", "Zona", "Atenciones", "Última atención"])
        for d in informe.detalle:
            w.writerow(
                [d.expediente, d.documento, d.nombre_completo, d.zona, d.atenciones, f"{d.ultima:%d/%m/%Y}"]
            )
