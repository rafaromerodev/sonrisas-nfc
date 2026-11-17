"""Componentes visuales reutilizables."""

from __future__ import annotations

from collections.abc import Callable
from typing import ClassVar

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from sonrisas_nfc.domain.models import EstadoExpediente
from sonrisas_nfc.ui import iconos
from sonrisas_nfc.ui.tema import (
    AMARILLO,
    AZUL,
    AZUL_SUAVE,
    COLORES_ESTADO,
    FUENTE_TITULOS,
    PAPEL,
    TINTA,
)


def etiqueta(texto: str = "", rol: str | None = None, ajustar: bool = False) -> QLabel:
    lbl = QLabel(texto)
    if rol:
        lbl.setProperty("rol", rol)
    lbl.setWordWrap(ajustar)
    return lbl


def boton(
    texto: str,
    variante: str | None = None,
    icono: str | None = None,
    al_pulsar: Callable[[], object] | None = None,
    color_icono: str = TINTA,
) -> QPushButton:
    b = QPushButton(texto)
    if variante:
        b.setProperty("variante", variante)
    if icono:
        b.setIcon(iconos.icono(icono, PAPEL if variante == "primario" else color_icono))
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    if al_pulsar:
        # «clicked» envía un booleano (checked). Si se conectara directamente, una acción como
        # ``lambda m=6: renovar(m)`` recibiría False en lugar de 6. Se llama siempre sin argumentos.
        b.clicked.connect(lambda _checked=False: al_pulsar())
    return b


def refrescar_estilo(w: QWidget) -> None:
    """Reaplica el QSS tras cambiar una propiedad dinámica (p. ej. ``error``)."""
    w.style().unpolish(w)
    w.style().polish(w)


class Tarjeta(QFrame):
    """Contenedor con borde de tinta y "sombra dura" desplazada, como las tarjetas de la web.

    Se pinta a mano: QSS no admite sombras y un borde inferior más grueso con esquinas
    redondeadas deja muescas.
    """

    SOMBRA = 6
    _ESTILOS: ClassVar[dict[str, tuple[str, int]]] = {
        "true": (PAPEL, 20),
        "suave": (AZUL_SUAVE, 20),
        "azul": (AZUL, 24),
    }

    def __init__(self, estilo: str = "true", margen: int = 22, espacio: int = 12, parent=None) -> None:
        super().__init__(parent)
        self.setProperty("card", estilo)  # usado por el QSS para el color de los textos internos
        self._fondo, self._radio = self._ESTILOS[estilo]
        self.capa = QVBoxLayout(self)
        self.capa.setContentsMargins(margen, margen, margen, margen + self.SOMBRA)
        self.capa.setSpacing(espacio)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1 - self.SOMBRA)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(TINTA))
        p.drawRoundedRect(r.translated(0, self.SOMBRA), self._radio, self._radio)
        p.setPen(QPen(QColor(TINTA), 2))
        p.setBrush(QColor(self._fondo))
        p.drawRoundedRect(r, self._radio, self._radio)


class CabeceraPagina(QWidget):
    def __init__(self, kicker: str, titulo: str, subtitulo: str = "", parent=None) -> None:
        super().__init__(parent)
        capa = QVBoxLayout(self)
        capa.setContentsMargins(0, 0, 0, 6)
        capa.setSpacing(2)
        capa.addWidget(etiqueta(kicker.upper(), "kicker"))
        self.titulo = etiqueta(titulo, "titulo")
        capa.addWidget(self.titulo)
        self.subtitulo = etiqueta(subtitulo, "subtitulo", ajustar=True)
        self.subtitulo.setVisible(bool(subtitulo))
        capa.addWidget(self.subtitulo)


class Cifra(Tarjeta):
    """Tarjeta de indicador (número grande + texto), clicable opcionalmente."""

    def __init__(self, texto: str, color: str = TINTA, estilo: str = "true", parent=None) -> None:
        super().__init__(estilo, margen=18, espacio=2, parent=parent)
        self.valor = etiqueta("–", "cifra")
        self.valor.setStyleSheet(f"color: {color};")
        self.texto = etiqueta(texto, "etiqueta", ajustar=True)
        self.capa.addWidget(self.valor)
        self.capa.addWidget(self.texto)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._al_pulsar: Callable[[], object] | None = None

    def establecer(self, valor: int | str) -> None:
        self.valor.setText(f"{valor:,}".replace(",", ".") if isinstance(valor, int) else valor)

    def al_pulsar(self, accion: Callable[[], object]) -> None:
        self._al_pulsar = accion
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mouseReleaseEvent(self, event) -> None:
        if self._al_pulsar and event.button() == Qt.MouseButton.LeftButton:
            self._al_pulsar()
        super().mouseReleaseEvent(event)


class ChipEstado(QLabel):
    def __init__(self, estado: EstadoExpediente | None = None, parent=None) -> None:
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if estado:
            self.establecer(estado)

    def establecer(self, estado: EstadoExpediente, texto: str | None = None) -> None:
        texto_color, fondo = COLORES_ESTADO[estado]
        self.setText(texto or estado.value)
        self.setStyleSheet(
            f"background: {fondo}; color: {texto_color}; border: 2px solid {texto_color};"
            f"border-radius: 13px; padding: 3px 12px; font-family: '{FUENTE_TITULOS}';"
            "font-weight: 600; font-size: 13px;"
        )


class Avatar(QWidget):
    """Círculo amarillo con iniciales."""

    def __init__(self, iniciales: str = "", tam: int = 64, parent=None) -> None:
        super().__init__(parent)
        self.iniciales = iniciales
        self.setFixedSize(tam, tam)

    def establecer(self, iniciales: str) -> None:
        self.iniciales = iniciales
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect().adjusted(2, 2, -2, -2)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(TINTA))
        p.drawEllipse(r.translated(0, 2))
        p.setBrush(QColor(AMARILLO))
        p.setPen(QColor(TINTA))
        p.drawEllipse(r.adjusted(0, 0, 0, -2))
        fuente = p.font()
        fuente.setFamily(FUENTE_TITULOS)
        fuente.setPixelSize(int(self.width() * 0.36))
        fuente.setWeight(fuente.Weight.DemiBold)
        p.setFont(fuente)
        p.drawText(r.adjusted(0, 0, 0, -2), Qt.AlignmentFlag.AlignCenter, self.iniciales)


class Banner(QFrame):
    """Mensaje destacado: ok / aviso / error / info, con botones opcionales a la derecha."""

    _ICONOS: ClassVar[dict[str, str]] = {"ok": "check", "aviso": "aviso", "error": "aviso", "info": "nfc"}

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        capa = QHBoxLayout(self)
        capa.setContentsMargins(16, 12, 12, 12)
        capa.setSpacing(12)
        self._icono = QLabel()
        capa.addWidget(self._icono, 0, Qt.AlignmentFlag.AlignTop)
        textos = QVBoxLayout()
        textos.setSpacing(0)
        self._titulo = etiqueta("", "seccion", ajustar=True)
        self._detalle = etiqueta("", None, ajustar=True)
        textos.addWidget(self._titulo)
        textos.addWidget(self._detalle)
        capa.addLayout(textos, 1)
        self._acciones = QHBoxLayout()
        self._acciones.setSpacing(8)
        capa.addLayout(self._acciones)
        self.hide()

    def mostrar(
        self, tipo: str, titulo: str, detalle: str = "", acciones: list[QPushButton] | None = None
    ) -> None:
        from sonrisas_nfc.ui.tema import AMBAR, AZUL_OSCURO, ROJO, VERDE

        color = {"ok": VERDE, "aviso": AMBAR, "error": ROJO, "info": AZUL_OSCURO}[tipo]
        self.setProperty("banner", tipo)
        refrescar_estilo(self)
        self._icono.setPixmap(iconos.pixmap(self._ICONOS[tipo], 26, color))
        self._titulo.setText(titulo)
        self._titulo.setStyleSheet(f"color: {color};")
        self._detalle.setText(detalle)
        self._detalle.setVisible(bool(detalle))
        while self._acciones.count():
            item = self._acciones.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()
        for b in acciones or []:
            self._acciones.addWidget(b)
        self.show()


class Buscador(QLineEdit):
    def __init__(self, marcador: str, parent=None) -> None:
        super().__init__(parent)
        self.setProperty("rol", "buscador")
        self.setPlaceholderText(marcador)
        self.setClearButtonEnabled(True)
        lupa = QLabel(self)
        lupa.setPixmap(iconos.pixmap("buscar", 18))
        lupa.move(15, 0)
        lupa.setFixedHeight(46)
        self._lupa = lupa

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        self._lupa.setFixedHeight(self.height())


class Toast(QLabel):
    """Notificación breve en la parte inferior de la ventana."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("toast")
        self._efecto = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._efecto)
        self._anim = QPropertyAnimation(self._efecto, b"opacity", self)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._timer = QTimer(self, singleShot=True, timeout=self._ocultar)
        self.hide()

    def mostrar(self, texto: str, ms: int = 2600) -> None:
        self.setText(texto)
        self.adjustSize()
        padre = self.parentWidget()
        self.move((padre.width() - self.width()) // 2, padre.height() - self.height() - 32)
        self.raise_()
        self.show()
        self._anim.stop()
        self._anim.setDuration(180)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.start()
        self._timer.start(ms)

    def _ocultar(self) -> None:
        self._anim.stop()
        self._anim.setDuration(400)
        self._anim.setStartValue(1.0)
        self._anim.setEndValue(0.0)
        self._anim.finished.connect(self.hide, Qt.ConnectionType.SingleShotConnection)
        self._anim.start()


def separador() -> QFrame:
    f = QFrame()
    f.setProperty("separador", "true")
    return f


# ---------------------------------------------------------------- mensajes
def _caja(padre, icono, titulo: str, texto: str, detalle: str = "") -> QMessageBox:
    caja = QMessageBox(icono, titulo, texto, parent=padre)
    if detalle:
        caja.setInformativeText(detalle)
    return caja


def confirmar(
    padre, titulo: str, texto: str, si: str = "Sí", no: str = "Cancelar", detalle: str = ""
) -> bool:
    caja = _caja(padre, QMessageBox.Icon.Question, titulo, texto, detalle)
    b_si = caja.addButton(si, QMessageBox.ButtonRole.AcceptRole)
    b_si.setProperty("variante", "primario")
    caja.addButton(no, QMessageBox.ButtonRole.RejectRole)
    caja.setDefaultButton(b_si)
    caja.exec()
    return caja.clickedButton() is b_si


def informar(padre, titulo: str, texto: str, detalle: str = "") -> None:
    caja = _caja(padre, QMessageBox.Icon.Information, titulo, texto, detalle)
    caja.addButton("Aceptar", QMessageBox.ButtonRole.AcceptRole)
    caja.exec()


def avisar_error(padre, titulo: str, texto: str, detalle: str = "") -> None:
    caja = _caja(padre, QMessageBox.Icon.Warning, titulo, texto, detalle)
    caja.addButton("Aceptar", QMessageBox.ButtonRole.AcceptRole)
    caja.exec()
