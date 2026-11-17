"""Normalización y validación de datos de entrada (documento, teléfono, UID)."""

from __future__ import annotations

import re
from enum import Enum

_LETRAS_DNI = "TRWAGMYFPDXBNJZSQVHLCKE"
_RE_DNI = re.compile(r"^\d{8}[A-Z]$")
_RE_NIE = re.compile(r"^[XYZ]\d{7}[A-Z]$")
_RE_OTRO = re.compile(r"^[A-Z0-9]{5,15}$")
_RE_HEX = re.compile(r"^[0-9A-F]+$")


class TipoDocumento(Enum):
    DNI = "DNI"
    NIE = "NIE"
    OTRO = "Pasaporte / otro"


class ErrorValidacion(ValueError):
    """Error de datos introducidos por el usuario; el mensaje se muestra tal cual."""

    def __init__(self, campo: str, mensaje: str) -> None:
        super().__init__(mensaje)
        self.campo = campo
        self.mensaje = mensaje


def normalizar_documento(texto: str) -> str:
    """Mayúsculas y sin espacios, guiones ni puntos: ``"12.345.678-z"`` -> ``"12345678Z"``."""
    return re.sub(r"[\s.\-]", "", texto or "").upper()


def tipo_documento(documento: str) -> TipoDocumento:
    doc = normalizar_documento(documento)
    if _RE_DNI.match(doc):
        return TipoDocumento.DNI
    if _RE_NIE.match(doc):
        return TipoDocumento.NIE
    return TipoDocumento.OTRO


def letra_control(numero: int) -> str:
    return _LETRAS_DNI[numero % 23]


def validar_documento(documento: str) -> str:
    """Devuelve el documento normalizado o lanza :class:`ErrorValidacion`.

    DNI y NIE se comprueban con su letra de control. Cualquier otro documento
    (pasaporte, documento extranjero) se acepta si es alfanumérico de 5 a 15 caracteres.
    """
    doc = normalizar_documento(documento)
    if not doc:
        raise ErrorValidacion("documento", "El documento es obligatorio.")
    if re.fullmatch(r"\d{8}", doc):
        raise ErrorValidacion(
            "documento", f"Falta la letra del DNI (debería ser {doc}{letra_control(int(doc))})."
        )
    if _RE_DNI.match(doc):
        esperada = letra_control(int(doc[:8]))
        if doc[8] != esperada:
            raise ErrorValidacion("documento", f"La letra del DNI no es correcta (debería ser {esperada}).")
        return doc
    if _RE_NIE.match(doc):
        numero = int(str("XYZ".index(doc[0])) + doc[1:8])
        esperada = letra_control(numero)
        if doc[8] != esperada:
            raise ErrorValidacion("documento", f"La letra del NIE no es correcta (debería ser {esperada}).")
        return doc
    if _RE_OTRO.match(doc):
        return doc
    raise ErrorValidacion("documento", "Documento no válido: use DNI, NIE o pasaporte (5–15 letras/números).")


def validar_telefono(telefono: str) -> str:
    """Teléfono español de 9 dígitos; admite espacios y prefijo +34/0034."""
    tel = re.sub(r"[\s\-.()]", "", telefono or "")
    tel = re.sub(r"^(\+34|0034)", "", tel)
    if not tel:
        raise ErrorValidacion("telefono", "El teléfono es obligatorio.")
    if not re.fullmatch(r"\d{9}", tel):
        raise ErrorValidacion("telefono", "El teléfono debe tener 9 dígitos.")
    return tel


def normalizar_uid(uid: str) -> str:
    """Formato canónico de UID de tarjeta: bytes hex en mayúsculas separados por espacio.

    ``"04a1b2c3"``, ``"04:A1:B2:C3"`` y ``"04 a1 b2 c3"`` -> ``"04 A1 B2 C3"``.
    """
    limpio = re.sub(r"[\s:\-]", "", uid or "").upper()
    if not limpio or len(limpio) % 2 or not _RE_HEX.match(limpio):
        raise ErrorValidacion("uid", "El UID de la tarjeta no es válido (se esperan bytes hexadecimales).")
    return " ".join(limpio[i : i + 2] for i in range(0, len(limpio), 2))


def texto_o_none(valor: str | None) -> str | None:
    valor = (valor or "").strip()
    return valor or None
