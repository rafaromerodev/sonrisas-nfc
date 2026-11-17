"""Gráfica de barras de atenciones por día de la semana (pantalla y PDF)."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen, QRegion
from PySide6.QtWidgets import QToolTip, QWidget

from sonrisas_nfc.ui.tema import AZUL, FUENTE_TITULOS, LINEA, TINTA, TINTA_SUAVE

DIAS = ("Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo")


def _n(valor: int) -> str:
    return f"{valor:,}".replace(",", ".")


class GraficaDias(QWidget):
    """Una sola serie en el azul de marca: no necesita leyenda (el título la nombra).

    Etiqueta directa solo en el máximo; el valor de cada barra aparece al pasar el ratón.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.valores = [0] * 7
        self.setMinimumHeight(190)
        self.setMouseTracking(True)
        self._zonas: list[QRectF] = []

    def establecer(self, valores: list[int]) -> None:
        self.valores = list(valores)
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        alto_texto, arriba = 22, 22
        base = self.height() - alto_texto - 4
        ancho_hueco = self.width() / 7
        ancho_barra = min(34.0, ancho_hueco * 0.5)
        maximo = max(self.valores) or 1
        indice_max = self.valores.index(max(self.valores)) if any(self.valores) else -1

        fuente = QFont(FUENTE_TITULOS)
        fuente.setPixelSize(12)
        p.setFont(fuente)
        p.setPen(QPen(QColor(LINEA), 1))
        p.drawLine(0, base, self.width(), base)

        self._zonas = []
        for i, v in enumerate(self.valores):
            cx = ancho_hueco * i + ancho_hueco / 2
            h = (base - arriba) * v / maximo
            self._zonas.append(QRectF(ancho_hueco * i, 0, ancho_hueco, self.height()))
            if v:
                barra = QRectF(cx - ancho_barra / 2, base - h, ancho_barra, h)
                radio = min(4.0, h)
                p.save()
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(AZUL))
                p.setClipRect(QRectF(0, 0, self.width(), base))  # extremo inferior recto sobre la base
                p.drawRoundedRect(barra.adjusted(0, 0, 0, radio), radio, radio)
                p.restore()
            p.setPen(QColor(TINTA_SUAVE))
            p.drawText(
                QRectF(ancho_hueco * i, base + 4, ancho_hueco, alto_texto),
                Qt.AlignmentFlag.AlignCenter,
                DIAS[i][:3],
            )
            if i == indice_max:
                p.setPen(QColor(TINTA))
                p.drawText(
                    QRectF(ancho_hueco * i, base - h - 20, ancho_hueco, 18),
                    Qt.AlignmentFlag.AlignCenter,
                    _n(v),
                )

    def mouseMoveEvent(self, e) -> None:
        for i, zona in enumerate(self._zonas):
            if zona.contains(e.position()):
                QToolTip.showText(
                    e.globalPosition().toPoint(), f"{DIAS[i]}: {_n(self.valores[i])} atenciones", self
                )
                return
        QToolTip.hideText()


def imagen_grafica(valores: list[int], tam: QSize, escala: float = 3.0) -> QImage:
    """Renderiza la gráfica a imagen (alta resolución) para incrustarla en el PDF."""
    g = GraficaDias()
    g.establecer(valores)
    g.resize(tam)
    img = QImage(tam * escala, QImage.Format.Format_ARGB32_Premultiplied)
    img.setDevicePixelRatio(escala)
    img.fill(Qt.GlobalColor.white)
    g.render(img, QPoint(), QRegion(), QWidget.RenderFlag.DrawChildren)  # sin el fondo de la ventana
    return img
