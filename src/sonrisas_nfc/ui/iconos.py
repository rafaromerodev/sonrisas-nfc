"""Iconos de trazo (24×24) dibujados como SVG en línea: nítidos a cualquier escala y sin archivos externos."""

from __future__ import annotations

from functools import cache

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QImage, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from sonrisas_nfc.ui.tema import TINTA

_TRAZOS: dict[str, str] = {
    "inicio": '<path d="M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z"/>',
    "personas": '<circle cx="9" cy="8" r="4"/><path d="M2 21v-1a6 6 0 0 1 6-6h2a6 6 0 0 1 6 6v1"/>'
    '<path d="M16 3.5a4 4 0 0 1 0 8"/><path d="M22 21v-1a6 6 0 0 0-4-5.7"/>',
    "alta": '<circle cx="9" cy="8" r="4"/><path d="M2 21v-1a6 6 0 0 1 6-6h2a6 6 0 0 1 6 6v1"/>'
    '<path d="M19 8v6M16 11h6"/>',
    "informes": '<path d="M4 20V11M10 20V4M16 20v-6M22 20H2"/>',
    "ayuda": '<circle cx="12" cy="12" r="10"/><path d="M9.1 9a3 3 0 0 1 5.8 1c0 2-3 2.5-3 4"/>'
    '<path d="M12 17.5h.01"/>',
    "datos": '<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 1.7 3.6 3 8 3s8-1.3 8-3V5"/>'
    '<path d="M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/>',
    "nfc": '<path d="M6 8.5a5 5 0 0 1 0 7"/><path d="M9.5 6a9 9 0 0 1 0 12"/><path d="M13 3.5a13 13 0 0 1 0 17"/>',
    "tarjeta": '<rect x="2" y="5" width="20" height="14" rx="2.5"/><path d="M2 10h20M6 15h4"/>',
    "buscar": '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.6-3.6"/>',
    "mas": '<path d="M12 5v14M5 12h14"/>',
    "check": '<path d="m4.5 12.5 5 5L20 7"/>',
    "aviso": '<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/>'
    '<path d="M12 9v4M12 17h.01"/>',
    "renovar": '<path d="M3 12a9 9 0 0 1 15.4-6.4L21 8"/><path d="M21 3v5h-5"/>'
    '<path d="M21 12a9 9 0 0 1-15.4 6.4L3 16"/><path d="M3 21v-5h5"/>',
    "calendario": '<rect x="3" y="4.5" width="18" height="17" rx="2.5"/><path d="M3 10h18M8 2.5v4M16 2.5v4"/>',
    "descargar": '<path d="M12 3v12M7 10l5 5 5-5M4 21h16"/>',
    "baja": '<circle cx="9" cy="8" r="4"/><path d="M2 21v-1a6 6 0 0 1 6-6h2a6 6 0 0 1 6 6v1"/>'
    '<path d="m17 8 5 5M22 8l-5 5"/>',
    "guardar": '<path d="M5 3h11l5 5v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z"/>'
    '<path d="M7 3v5h8M7 21v-7h10v7"/>',
    "cerrar": '<path d="M6 6l12 12M18 6 6 18"/>',
    "carpeta": '<path d="M3 6.5A2.5 2.5 0 0 1 5.5 4H9l2 2.5h7.5A2.5 2.5 0 0 1 21 9v9a2.5 2.5 0 0 1-2.5 2.5h-13A2.5 2.5 0 0 1 3 18z"/>',
    "historial": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "importar": '<path d="M12 15V3M7 8l5-5 5 5M4 15v4a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-4"/>',
    "editar": '<path d="M4 20h4L19 9l-4-4L4 16z"/><path d="m14 6 4 4"/>',
}


def _svg(nombre: str, color: str, grosor: float) -> bytes:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" '
        f'stroke-width="{grosor}" stroke-linecap="round" stroke-linejoin="round">{_TRAZOS[nombre]}</svg>'
    ).encode()


@cache
def pixmap(
    nombre: str, tam: int = 20, color: str = TINTA, grosor: float = 2.2, escala: float = 2.0
) -> QPixmap:
    imagen = QImage(int(tam * escala), int(tam * escala), QImage.Format.Format_ARGB32_Premultiplied)
    imagen.fill(Qt.GlobalColor.transparent)
    pintor = QPainter(imagen)
    pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
    QSvgRenderer(QByteArray(_svg(nombre, color, grosor))).render(
        pintor, QRectF(0, 0, imagen.width(), imagen.height())
    )
    pintor.end()
    pm = QPixmap.fromImage(imagen)
    pm.setDevicePixelRatio(escala)
    return pm


@cache
def icono(nombre: str, color: str = TINTA, tam: int = 20) -> QIcon:
    return QIcon(pixmap(nombre, tam, color))
