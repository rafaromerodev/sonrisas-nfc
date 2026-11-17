"""Formulario de datos del beneficiario (compartido por el alta y la ficha)."""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtWidgets import (
    QCompleter,
    QDateEdit,
    QHBoxLayout,
    QLineEdit,
    QPlainTextEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from sonrisas_nfc.config import MESES_RENOVACION
from sonrisas_nfc.domain.models import Beneficiario, sumar_meses
from sonrisas_nfc.ui.componentes import boton, etiqueta, refrescar_estilo


class Campo(QWidget):
    """Etiqueta + control + mensaje de error bajo el control."""

    def __init__(self, titulo: str, control: QWidget, ayuda: str = "") -> None:
        super().__init__()
        capa = QVBoxLayout(self)
        capa.setContentsMargins(0, 0, 0, 0)
        capa.setSpacing(4)
        capa.addWidget(etiqueta(titulo, "etiqueta"))
        capa.addWidget(control)
        self.control = control
        self.error = etiqueta("", "error", ajustar=True)
        self.error.hide()
        capa.addWidget(self.error)
        if ayuda:
            capa.addWidget(etiqueta(ayuda, "ayuda", ajustar=True))

    def marcar_error(self, mensaje: str | None) -> None:
        self.control.setProperty("error", bool(mensaje))
        refrescar_estilo(self.control)
        self.error.setText(mensaje or "")
        self.error.setVisible(bool(mensaje))


def _entrada(marcador: str = "", max_len: int = 80) -> QLineEdit:
    e = QLineEdit()
    e.setPlaceholderText(marcador)
    e.setMaxLength(max_len)
    return e


def _contador() -> QSpinBox:
    s = QSpinBox()
    s.setRange(0, 30)
    s.setButtonSymbols(QSpinBox.ButtonSymbols.PlusMinus)
    s.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return s


class FormularioBeneficiario(QWidget):
    modificado = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._id: int | None = None
        self._activo = True
        self._cargando = False

        self.nombre = _entrada("Nombre")
        self.apellidos = _entrada("Apellidos")
        self.documento = _entrada("DNI, NIE o pasaporte", 20)
        self.telefono = _entrada("9 dígitos", 20)
        self.expediente = _entrada("Nº de expediente social", 40)
        self.zona = _entrada("Municipio o localidad")
        self.vencimiento = QDateEdit()
        self.vencimiento.setCalendarPopup(True)
        self.vencimiento.setDisplayFormat("dd/MM/yyyy")
        self.vencimiento.setDate(QDate.currentDate())
        self.adultos, self.menores, self.mayores = _contador(), _contador(), _contador()
        self.notas = QPlainTextEdit()
        self.notas.setPlaceholderText("Observaciones internas (opcional)")
        self.notas.setFixedHeight(86)

        self.campos: dict[str, Campo] = {
            "nombre": Campo("Nombre *", self.nombre),
            "apellidos": Campo("Apellidos *", self.apellidos),
            "documento": Campo("Documento *", self.documento),
            "telefono": Campo("Teléfono *", self.telefono),
            "expediente": Campo("Nº expediente", self.expediente),
            "zona": Campo("Municipio / localidad", self.zona),
            "adultos": Campo("Adultos", self.adultos),
            "menores": Campo("Menores", self.menores),
            "mayores": Campo("Mayores de 65", self.mayores),
            "notas": Campo("Notas", self.notas),
        }

        renovar = QHBoxLayout()
        renovar.setSpacing(8)
        self.vencimiento.setMinimumWidth(170)
        renovar.addWidget(self.vencimiento)
        for meses in MESES_RENOVACION:
            b = boton(f"+{meses} meses", "filtro", al_pulsar=lambda m=meses: self._poner_vencimiento(m))
            b.setToolTip(f"Vencimiento dentro de {meses} meses desde hoy")
            renovar.addWidget(b)
        renovar.addStretch()
        contenedor_venc = QWidget()
        contenedor_venc.setLayout(renovar)
        renovar.setContentsMargins(0, 0, 0, 0)
        self.campos["vencimiento"] = Campo("Vencimiento del expediente", contenedor_venc)

        c = self.campos
        capa = QVBoxLayout(self)
        capa.setContentsMargins(0, 0, 0, 0)
        capa.setSpacing(10)
        for elemento in (
            "Datos personales",
            ((c["nombre"], 1), (c["apellidos"], 1)),
            ((c["documento"], 1), (c["telefono"], 1)),
            "Expediente",
            ((c["expediente"], 1), (c["zona"], 1)),
            ((c["vencimiento"], 1),),
            "Unidad familiar",
            ((c["adultos"], 1), (c["menores"], 1), (c["mayores"], 1)),
            ((c["notas"], 1),),
        ):
            if isinstance(elemento, str):
                capa.addSpacing(6)
                capa.addWidget(etiqueta(elemento, "seccion"))
                continue
            fila = QHBoxLayout()
            fila.setSpacing(18)
            for campo, peso in elemento:
                fila.addWidget(campo, peso, Qt.AlignmentFlag.AlignTop)
            capa.addLayout(fila)

        for w in (self.nombre, self.apellidos, self.documento, self.telefono, self.expediente, self.zona):
            w.textEdited.connect(self._cambio)
        for s in (self.adultos, self.menores, self.mayores):
            s.valueChanged.connect(self._cambio)
        self.vencimiento.dateChanged.connect(self._cambio)
        self.notas.textChanged.connect(self._cambio)
        self.documento.editingFinished.connect(
            lambda: self.documento.setText(self.documento.text().upper().strip())
        )

    # ----------------------------------------------------------------- API
    def establecer_zonas(self, zonas: list[str]) -> None:
        completar = QCompleter(sorted(set(zonas)), self)
        completar.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completar.setFilterMode(Qt.MatchFlag.MatchContains)
        self.zona.setCompleter(completar)

    def cargar(self, b: Beneficiario) -> None:
        self._cargando = True
        self._id, self._activo = b.id, b.activo
        self.nombre.setText(b.nombre)
        self.apellidos.setText(b.apellidos)
        self.documento.setText(b.documento)
        self.telefono.setText(b.telefono)
        self.expediente.setText(b.expediente or "")
        self.zona.setText(b.zona or "")
        self.vencimiento.setDate(_a_qdate(b.vencimiento) if b.vencimiento else QDate.currentDate())
        self.adultos.setValue(b.adultos or 0)
        self.menores.setValue(b.menores or 0)
        self.mayores.setValue(b.mayores or 0)
        self.notas.setPlainText(b.notas or "")
        self.limpiar_errores()
        self._cargando = False

    def datos(self) -> Beneficiario:
        return Beneficiario(
            id=self._id,
            activo=self._activo,
            nombre=self.nombre.text(),
            apellidos=self.apellidos.text(),
            documento=self.documento.text(),
            telefono=self.telefono.text(),
            expediente=self.expediente.text(),
            zona=self.zona.text(),
            vencimiento=self.vencimiento.date().toPython(),
            adultos=self.adultos.value(),
            menores=self.menores.value(),
            mayores=self.mayores.value(),
            notas=self.notas.toPlainText(),
        )

    def limpiar(self) -> None:
        self.cargar(Beneficiario(documento="", nombre="", apellidos="", telefono="", adultos=1))
        self._id = None

    def mostrar_error(self, campo: str, mensaje: str) -> bool:
        """Marca el campo con error. Devuelve ``False`` si el campo no está en el formulario."""
        c = self.campos.get(campo)
        if c is None:
            return False
        c.marcar_error(mensaje)
        c.control.setFocus()
        return True

    def limpiar_errores(self) -> None:
        for c in self.campos.values():
            c.marcar_error(None)

    # ------------------------------------------------------------- internos
    def _poner_vencimiento(self, meses: int) -> None:
        self.vencimiento.setDate(_a_qdate(sumar_meses(date.today(), meses)))

    def _cambio(self, *_args) -> None:
        if self._cargando:
            return
        emisor = self.sender()
        for c in self.campos.values():
            if c.control is emisor or c.control.isAncestorOf(emisor):
                c.marcar_error(None)
        self.modificado.emit()


def _a_qdate(d: date) -> QDate:
    return QDate(d.year, d.month, d.day)
