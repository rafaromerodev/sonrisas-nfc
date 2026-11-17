"""Panel de inicio: zona de lectura de tarjeta, cifras del día y últimas atenciones."""

from __future__ import annotations

from datetime import date, datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLineEdit, QVBoxLayout, QWidget

from sonrisas_nfc.services.contexto import Servicios
from sonrisas_nfc.ui import iconos
from sonrisas_nfc.ui.componentes import CabeceraPagina, Cifra, Tarjeta, boton, etiqueta, separador
from sonrisas_nfc.ui.tema import AMARILLO, AZUL_OSCURO, PAPEL, ROJO, TINTA, TINTA_SUAVE

_DIAS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
_MESES = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)  # fmt: skip


def _saludo() -> str:
    h = datetime.now().hour
    return "Buenos días" if h < 14 else "Buenas tardes" if h < 21 else "Buenas noches"


class PaginaInicio(QWidget):
    buscar = Signal(str)
    abrir_beneficiario = Signal(int)
    ver_filtro = Signal(str)  # clave de filtro de la lista de beneficiarios

    def __init__(self, servicios: Servicios, parent=None) -> None:
        super().__init__(parent)
        self.s = servicios
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(36, 30, 36, 30)
        raiz.setSpacing(20)

        hoy = date.today()
        self.cabecera = CabeceraPagina(
            f"{_DIAS[hoy.weekday()]}, {hoy.day} de {_MESES[hoy.month - 1]} de {hoy.year}", f"¡{_saludo()}!"
        )
        raiz.addWidget(self.cabecera)

        fila = QHBoxLayout()
        fila.setSpacing(20)

        # Zona de lectura (protagonista)
        lectura = Tarjeta("azul", margen=30, espacio=10)
        icono = etiqueta()
        icono.setPixmap(iconos.pixmap("nfc", 64, AMARILLO, 2.4))
        lectura.capa.addWidget(icono)
        titulo = etiqueta("Acerque la tarjeta al lector", "titulo")
        titulo.setStyleSheet(f"color: {PAPEL};")
        lectura.capa.addWidget(titulo)
        explicacion = etiqueta(
            "Se registrará la atención de hoy y se abrirá la ficha. Si la tarjeta es nueva, "
            "pasará directamente al alta.",
            None,
            ajustar=True,
        )
        explicacion.setStyleSheet("color: rgba(255,255,255,0.92); font-size: 16px;")
        lectura.capa.addWidget(explicacion)
        lectura.capa.addStretch()
        lectura.capa.addWidget(separador())
        manual = QHBoxLayout()
        manual.setSpacing(10)
        self.entrada = QLineEdit()
        self.entrada.setPlaceholderText("Sin tarjeta: buscar por DNI, expediente o nombre")
        self.entrada.returnPressed.connect(self._enviar)
        manual.addWidget(self.entrada, 1)
        manual.addWidget(boton("Buscar", "amarillo", "buscar", self._enviar))
        lectura.capa.addLayout(manual)
        fila.addWidget(lectura, 3)

        # Cifras
        cifras = QGridLayout()
        cifras.setSpacing(16)
        self.c_hoy = Cifra("Atenciones hoy", AZUL_OSCURO, "suave")
        self.c_mes = Cifra("Atenciones este mes", TINTA)
        self.c_activos = Cifra("Beneficiarios activos", TINTA)
        self.c_vencidos = Cifra("Expedientes vencidos", ROJO)
        self.c_por_vencer = Cifra("Vencen en 30 días", "#8a6400")
        self.c_sin_tarjeta = Cifra("Sin tarjeta asignada", TINTA_SUAVE)
        self.c_vencidos.al_pulsar(lambda: self.ver_filtro.emit("vencidos"))
        self.c_por_vencer.al_pulsar(lambda: self.ver_filtro.emit("por_vencer"))
        self.c_sin_tarjeta.al_pulsar(lambda: self.ver_filtro.emit("sin_tarjeta"))
        self.c_activos.al_pulsar(lambda: self.ver_filtro.emit("activos"))
        for i, c in enumerate(
            (self.c_hoy, self.c_mes, self.c_activos, self.c_vencidos, self.c_por_vencer, self.c_sin_tarjeta)
        ):
            cifras.addWidget(c, i // 2, i % 2)
        contenedor = QWidget()
        contenedor.setLayout(cifras)
        cifras.setContentsMargins(0, 0, 0, 0)
        fila.addWidget(contenedor, 2)
        raiz.addLayout(fila)

        # Últimas atenciones
        recientes = Tarjeta(margen=22, espacio=4)
        recientes.capa.addWidget(etiqueta("Últimas atenciones", "seccion"))
        self.lista = QVBoxLayout()
        self.lista.setSpacing(0)
        recientes.capa.addLayout(self.lista)
        recientes.capa.addStretch()
        raiz.addWidget(recientes, 1)

    def _enviar(self) -> None:
        texto = self.entrada.text().strip()
        if texto:
            self.entrada.clear()
            self.buscar.emit(texto)

    def refrescar(self) -> None:
        r = self.s.informes.resumen()
        self.c_hoy.establecer(r.atenciones_hoy)
        self.c_mes.establecer(r.atenciones_mes)
        self.c_activos.establecer(r.activos)
        self.c_vencidos.establecer(r.vencidos)
        self.c_por_vencer.establecer(r.por_vencer)
        self.c_sin_tarjeta.establecer(r.sin_tarjeta)

        while self.lista.count():
            item = self.lista.takeAt(0)
            if item.widget():
                item.widget().hide()  # deleteLater es diferido: ocultar evita que se pinte encima
                item.widget().deleteLater()
        recientes = self.s.visitas.recientes(6)
        if not recientes:
            self.lista.addWidget(etiqueta("Todavía no hay atenciones registradas.", "ayuda"))
        hoy = date.today()
        for v in recientes:
            fila = QWidget()
            fila.setCursor(Qt.CursorShape.PointingHandCursor)
            capa = QHBoxLayout(fila)
            capa.setContentsMargins(4, 9, 4, 9)
            cuando = (
                f"{v.visita.fecha:%H:%M}" if v.visita.fecha.date() == hoy else f"{v.visita.fecha:%d/%m %H:%M}"
            )
            hora = etiqueta(cuando)
            hora.setFixedWidth(96)
            hora.setStyleSheet(f"color: {TINTA_SUAVE}; font-weight: 700;")
            capa.addWidget(hora)
            capa.addWidget(etiqueta(v.nombre_completo), 1)
            exp = etiqueta(v.expediente or "")
            exp.setStyleSheet(f"color: {TINTA_SUAVE};")
            capa.addWidget(exp)
            fila.mouseReleaseEvent = lambda _e, bid=v.beneficiario_id: self.abrir_beneficiario.emit(bid)
            self.lista.addWidget(fila)
