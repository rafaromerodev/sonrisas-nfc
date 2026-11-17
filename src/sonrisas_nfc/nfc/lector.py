"""Lectura de tarjetas NFC (lectores PC/SC como el ACR122U) en un hilo independiente.

Diferencias con la versión anterior:

* La lectura no bloquea la interfaz (hilo propio en lugar de un temporizador en el hilo gráfico).
* Se emite **un único evento por cada vez que se acerca la tarjeta**: hasta que no se retira del
  lector no se vuelve a notificar. Antes, una tarjeta apoyada generaba una visita cada 1,5 s.
* Si el lector se desconecta y se vuelve a conectar, se detecta sin reiniciar el programa.
* Cada conexión con la tarjeta se cierra tras leer el UID.
"""

from __future__ import annotations

import contextlib
import logging
from enum import Enum

from PySide6.QtCore import QThread, Signal

log = logging.getLogger(__name__)

try:  # pyscard es opcional: sin él, la app funciona en modo manual
    from smartcard.System import readers as _lectores_pcsc
    from smartcard.util import toHexString

    PCSC_DISPONIBLE = True
except Exception:  # pragma: no cover - depende del sistema
    PCSC_DISPONIBLE = False

_APDU_LEER_UID = [0xFF, 0xCA, 0x00, 0x00, 0x00]
_INTERVALO_MS = 250
_INTERVALO_SIN_LECTOR_MS = 2000
_LECTURAS_PARA_RETIRADA = 2


class EstadoLector(Enum):
    LISTO = "Lector listo"
    SIN_LECTOR = "Lector no conectado"
    NO_DISPONIBLE = "Modo manual (sin soporte PC/SC)"


class LectorNFC(QThread):
    tarjeta_detectada = Signal(str)  # UID en formato "04 A1 B2 C3"
    tarjeta_retirada = Signal()
    estado_cambiado = Signal(object, str)  # (EstadoLector, nombre del lector)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._activo = True
        self._uid_presente: str | None = None
        self._lecturas_vacias = 0
        self._estado: tuple[EstadoLector, str] | None = None

    def detener(self) -> None:
        self._activo = False
        self.wait(2000)

    def run(self) -> None:
        if not PCSC_DISPONIBLE:
            self._cambiar_estado(EstadoLector.NO_DISPONIBLE)
            return
        while self._activo:
            lector = self._primer_lector()
            if lector is None:
                self._cambiar_estado(EstadoLector.SIN_LECTOR)
                self._actualizar_presencia(None)
                self.msleep(_INTERVALO_SIN_LECTOR_MS)
                continue
            self._cambiar_estado(EstadoLector.LISTO, str(lector))
            self._actualizar_presencia(self._leer_uid(lector))
            self.msleep(_INTERVALO_MS)

    # ------------------------------------------------------------------ internos
    def _actualizar_presencia(self, uid: str | None) -> None:
        # Una lectura fallida aislada con la tarjeta apoyada no cuenta como "retirada".
        if uid is None and self._uid_presente is not None:
            self._lecturas_vacias += 1
            if self._lecturas_vacias < _LECTURAS_PARA_RETIRADA:
                return
        self._lecturas_vacias = 0
        if uid == self._uid_presente:
            return
        self._uid_presente = uid
        if uid:
            log.info("Tarjeta detectada: %s", uid)
            self.tarjeta_detectada.emit(uid)
        else:
            self.tarjeta_retirada.emit()

    def _cambiar_estado(self, estado: EstadoLector, nombre: str = "") -> None:
        if self._estado != (estado, nombre):
            self._estado = (estado, nombre)
            log.info("Estado del lector: %s %s", estado.value, nombre)
            self.estado_cambiado.emit(estado, nombre)

    @staticmethod
    def _primer_lector():
        try:
            lectores = _lectores_pcsc()
        except Exception:  # servicio "Tarjeta inteligente" detenido, etc.
            return None
        return lectores[0] if lectores else None

    @staticmethod
    def _leer_uid(lector) -> str | None:
        conexion = None
        try:
            conexion = lector.createConnection()
            conexion.connect()
            datos, sw1, sw2 = conexion.transmit(_APDU_LEER_UID)
            if (sw1, sw2) == (0x90, 0x00) and datos:
                return toHexString(datos)
            return None
        except Exception:  # sin tarjeta o lectura fallida
            return None
        finally:
            if conexion is not None:
                with contextlib.suppress(Exception):
                    conexion.disconnect()
