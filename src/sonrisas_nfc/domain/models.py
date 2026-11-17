"""Entidades del dominio."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import Enum

from sonrisas_nfc.config import DIAS_AVISO_VENCIMIENTO


class EstadoExpediente(Enum):
    VIGENTE = "Vigente"
    POR_VENCER = "Por vencer"
    VENCIDO = "Vencido"
    SIN_FECHA = "Sin fecha"
    BAJA = "De baja"


class OrigenVisita(Enum):
    TARJETA = "tarjeta"
    MANUAL = "manual"
    ALTA = "alta"
    IMPORTADA = "importada"


class MotivoCambioTarjeta(Enum):
    PERDIDA = "Pérdida"
    ROBO = "Robo"
    DETERIORO = "Deterioro"
    OTRO = "Otro"


@dataclass(slots=True)
class Beneficiario:
    documento: str
    nombre: str
    apellidos: str
    telefono: str
    expediente: str | None = None
    adultos: int | None = None
    menores: int | None = None
    mayores: int | None = None
    zona: str | None = None
    vencimiento: date | None = None
    notas: str | None = None
    activo: bool = True
    id: int | None = None
    creado_en: datetime | None = None
    # Campos calculados al leer de la base de datos
    ultima_visita: datetime | None = None
    total_visitas: int = 0
    tarjeta_uid: str | None = None

    @property
    def nombre_completo(self) -> str:
        return f"{self.nombre} {self.apellidos}".strip()

    @property
    def iniciales(self) -> str:
        partes = [p for p in (self.nombre, self.apellidos) if p]
        return "".join(p[0] for p in partes).upper()[:2] or "?"

    @property
    def miembros_hogar(self) -> int:
        return sum(n or 0 for n in (self.adultos, self.menores, self.mayores))

    def estado(self, hoy: date | None = None) -> EstadoExpediente:
        if not self.activo:
            return EstadoExpediente.BAJA
        if self.vencimiento is None:
            return EstadoExpediente.SIN_FECHA
        hoy = hoy or date.today()
        if self.vencimiento < hoy:
            return EstadoExpediente.VENCIDO
        if self.vencimiento <= hoy + timedelta(days=DIAS_AVISO_VENCIMIENTO):
            return EstadoExpediente.POR_VENCER
        return EstadoExpediente.VIGENTE


@dataclass(slots=True, frozen=True)
class Visita:
    id: int
    beneficiario_id: int
    fecha: datetime
    origen: OrigenVisita
    duplicada: bool = False


@dataclass(slots=True, frozen=True)
class Tarjeta:
    id: int
    uid: str
    beneficiario_id: int
    asignada_en: datetime
    baja_en: datetime | None = None
    motivo_baja: str | None = None

    @property
    def activa(self) -> bool:
        return self.baja_en is None


def clave_natural(texto: str | None) -> str:
    """Clave para ordenar textos con números por su valor: ``"45" < "100" < "1234.1"``.

    Rellena con ceros cada grupo de cifras, de modo que funciona como texto (también en las
    tablas de Qt). Los vacíos van al final.
    """
    if not texto:
        return "￿"
    return re.sub(r"\d+", lambda m: m.group().zfill(12), texto.strip().upper())


def sumar_meses(d: date, meses: int) -> date:
    """Suma meses a una fecha ajustando el día al último del mes si hace falta (31/01 + 1 = 28/02)."""
    total = d.month - 1 + meses
    anio, mes = d.year + total // 12, total % 12 + 1
    siguiente = date(anio + (mes == 12), mes % 12 + 1, 1)
    ultimo_dia = (siguiente - timedelta(days=1)).day
    return date(anio, mes, min(d.day, ultimo_dia))
