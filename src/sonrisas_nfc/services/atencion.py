"""Qué ocurre cuando se pasa una tarjeta por el lector.

Toda la decisión vive aquí (sin interfaz) para poder probarla de forma automática.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

from sonrisas_nfc.domain.models import Beneficiario, EstadoExpediente, OrigenVisita, Tarjeta, Visita
from sonrisas_nfc.domain.validators import normalizar_uid
from sonrisas_nfc.services.beneficiarios import BeneficiariosService
from sonrisas_nfc.services.tarjetas import TarjetasService
from sonrisas_nfc.services.visitas import VisitasService


class Resultado(Enum):
    VISITA_REGISTRADA = auto()
    YA_ATENDIDO_HOY = auto()
    EXPEDIENTE_VENCIDO = auto()  # requiere confirmación: no se registra la visita automáticamente
    TARJETA_NUEVA = auto()  # tarjeta sin asignar: ir al alta
    TARJETA_DE_BAJA = auto()  # tarjeta perdida/sustituida que vuelve a aparecer
    BENEFICIARIO_DE_BAJA = auto()


@dataclass(frozen=True, slots=True)
class ResultadoAtencion:
    resultado: Resultado
    uid: str
    beneficiario: Beneficiario | None = None
    visita: Visita | None = None
    tarjeta: Tarjeta | None = None


class AtencionService:
    def __init__(
        self, beneficiarios: BeneficiariosService, tarjetas: TarjetasService, visitas: VisitasService
    ) -> None:
        self.beneficiarios = beneficiarios
        self.tarjetas = tarjetas
        self.visitas = visitas

    def procesar_tarjeta(self, uid: str) -> ResultadoAtencion:
        uid = normalizar_uid(uid)
        tarjeta = self.tarjetas.activa_por_uid(uid)
        if tarjeta is None:
            baja = self.tarjetas.ultima_de_baja_por_uid(uid)
            if baja is not None:
                return ResultadoAtencion(
                    Resultado.TARJETA_DE_BAJA,
                    uid,
                    self.beneficiarios.obtener(baja.beneficiario_id),
                    tarjeta=baja,
                )
            return ResultadoAtencion(Resultado.TARJETA_NUEVA, uid)

        benef = self.beneficiarios.obtener(tarjeta.beneficiario_id)
        assert benef is not None  # garantizado por la clave foránea
        if not benef.activo:
            return ResultadoAtencion(Resultado.BENEFICIARIO_DE_BAJA, uid, benef, tarjeta=tarjeta)
        hoy = self.visitas.visita_de_hoy(benef.id)  # type: ignore[arg-type]
        if hoy is not None:
            return ResultadoAtencion(Resultado.YA_ATENDIDO_HOY, uid, benef, hoy, tarjeta)
        if benef.estado() is EstadoExpediente.VENCIDO:
            return ResultadoAtencion(Resultado.EXPEDIENTE_VENCIDO, uid, benef, tarjeta=tarjeta)
        return self.registrar(benef, uid, tarjeta)

    def registrar(
        self,
        benef: Beneficiario,
        uid: str = "",
        tarjeta: Tarjeta | None = None,
        origen: OrigenVisita = OrigenVisita.TARJETA,
    ) -> ResultadoAtencion:
        """Registra la visita (también tras confirmar un expediente vencido o en atención manual)."""
        visita, nueva = self.visitas.registrar(benef.id, origen)  # type: ignore[arg-type]
        benef = self.beneficiarios.obtener(benef.id)  # type: ignore[arg-type,assignment]
        resultado = Resultado.VISITA_REGISTRADA if nueva else Resultado.YA_ATENDIDO_HOY
        return ResultadoAtencion(resultado, uid, benef, visita, tarjeta)
