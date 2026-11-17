"""Punto único de acceso a los servicios (inyección de dependencias sencilla)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sonrisas_nfc.db.database import Database, abrir
from sonrisas_nfc.services.atencion import AtencionService
from sonrisas_nfc.services.beneficiarios import BeneficiariosService
from sonrisas_nfc.services.informes import InformesService
from sonrisas_nfc.services.tarjetas import TarjetasService
from sonrisas_nfc.services.visitas import VisitasService


@dataclass(slots=True)
class Servicios:
    db: Database
    beneficiarios: BeneficiariosService
    tarjetas: TarjetasService
    visitas: VisitasService
    atencion: AtencionService
    informes: InformesService

    @classmethod
    def crear(cls, ruta_db: Path | str) -> Servicios:
        db = abrir(ruta_db)
        beneficiarios = BeneficiariosService(db)
        tarjetas = TarjetasService(db)
        visitas = VisitasService(db)
        return cls(
            db=db,
            beneficiarios=beneficiarios,
            tarjetas=tarjetas,
            visitas=visitas,
            atencion=AtencionService(beneficiarios, tarjetas, visitas),
            informes=InformesService(db),
        )
