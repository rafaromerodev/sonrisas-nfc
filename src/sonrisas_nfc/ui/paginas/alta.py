"""Alta de un nuevo beneficiario y vinculación de su tarjeta."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QScrollArea, QVBoxLayout, QWidget

from sonrisas_nfc.domain.validators import ErrorValidacion
from sonrisas_nfc.services.contexto import Servicios
from sonrisas_nfc.ui import iconos
from sonrisas_nfc.ui.componentes import (
    CabeceraPagina,
    Tarjeta,
    avisar_error,
    boton,
    confirmar,
    etiqueta,
)
from sonrisas_nfc.ui.formulario import FormularioBeneficiario
from sonrisas_nfc.ui.tema import AMARILLO, PAPEL


class PaginaAlta(QWidget):
    creado = Signal(int)

    def __init__(self, servicios: Servicios, parent=None) -> None:
        super().__init__(parent)
        self.s = servicios
        self.uid: str | None = None

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(36, 30, 36, 30)
        raiz.setSpacing(16)
        raiz.addWidget(
            CabeceraPagina(
                "Registro", "Nuevo beneficiario",
                "Rellene los datos y pase una tarjeta nueva por el lector para vincularla.",
            )
        )  # fmt: skip

        fila = QHBoxLayout()
        fila.setSpacing(20)

        self.form = FormularioBeneficiario()
        tarjeta_form = Tarjeta(margen=24)
        tarjeta_form.capa.addWidget(self.form)
        tarjeta_form.capa.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        envoltorio = QWidget()
        capa_env = QVBoxLayout(envoltorio)
        capa_env.setContentsMargins(0, 0, 6, 6)
        capa_env.addWidget(tarjeta_form)
        scroll.setWidget(envoltorio)
        fila.addWidget(scroll, 3)

        lateral = QVBoxLayout()
        lateral.setSpacing(16)
        self.zona_tarjeta = Tarjeta("azul", margen=24, espacio=8)
        self.icono_tarjeta = etiqueta()
        self.zona_tarjeta.capa.addWidget(self.icono_tarjeta)
        self.lbl_tarjeta = etiqueta("", "seccion", ajustar=True)
        self.zona_tarjeta.capa.addWidget(self.lbl_tarjeta)
        self.lbl_uid = etiqueta("", "uid")
        self.zona_tarjeta.capa.addWidget(self.lbl_uid)
        self.lbl_tarjeta_ayuda = etiqueta("", None, ajustar=True)
        self.lbl_tarjeta_ayuda.setStyleSheet("color: rgba(255,255,255,0.9);")
        self.zona_tarjeta.capa.addWidget(self.lbl_tarjeta_ayuda)
        self.b_quitar = boton("Quitar tarjeta", None, "cerrar", self._quitar_tarjeta)
        self.zona_tarjeta.capa.addWidget(self.b_quitar, 0, Qt.AlignmentFlag.AlignLeft)
        lateral.addWidget(self.zona_tarjeta)

        acciones = Tarjeta(margen=22)
        self.chk_visita = QCheckBox("Registrar la primera atención hoy")
        self.chk_visita.setChecked(True)
        acciones.capa.addWidget(self.chk_visita)
        self.b_guardar = boton("Guardar beneficiario", "primario", "guardar", self._guardar)
        self.b_guardar.setMinimumHeight(48)
        acciones.capa.addWidget(self.b_guardar)
        acciones.capa.addWidget(boton("Vaciar formulario", "plano", None, self._vaciar))
        lateral.addWidget(acciones)
        lateral.addStretch()
        fila.addLayout(lateral, 2)
        raiz.addLayout(fila, 1)

        self.form.limpiar()
        self._pintar_tarjeta()

    # ------------------------------------------------------------------ API
    def refrescar(self) -> None:
        self.form.establecer_zonas(
            [r[0] for r in self.s.db.conn.execute("SELECT DISTINCT zona FROM beneficiarios WHERE zona <> ''")]
        )

    def establecer_uid(self, uid: str) -> None:
        self.uid = uid
        self._pintar_tarjeta()
        if not self.form.nombre.text():
            self.form.nombre.setFocus()

    def esta_vacio(self) -> bool:
        """Sin tarjeta y sin datos personales escritos."""
        f = self.form
        return self.uid is None and not any(
            w.text().strip() for w in (f.nombre, f.apellidos, f.documento, f.telefono, f.expediente)
        )

    def prellenar(self, texto: str) -> None:
        """Usa el texto buscado sin resultados como documento del alta."""
        self.form.documento.setText(texto.upper())

    # ------------------------------------------------------------- internos
    def _pintar_tarjeta(self) -> None:
        if self.uid:
            self.icono_tarjeta.setPixmap(iconos.pixmap("check", 40, AMARILLO, 3))
            self.lbl_tarjeta.setText("Tarjeta lista para vincular")
            self.lbl_uid.setText(self.uid)
            self.lbl_uid.show()
            self.lbl_tarjeta_ayuda.setText("Se asignará al guardar. Pase otra tarjeta para sustituirla.")
            self.b_quitar.show()
        else:
            self.icono_tarjeta.setPixmap(iconos.pixmap("nfc", 40, PAPEL, 2.4))
            self.lbl_tarjeta.setText("Pase una tarjeta nueva por el lector")
            self.lbl_uid.hide()
            self.lbl_tarjeta_ayuda.setText(
                "También puede guardar sin tarjeta y asignarla después desde la ficha."
            )
            self.b_quitar.hide()

    def _quitar_tarjeta(self) -> None:
        self.uid = None
        self._pintar_tarjeta()

    def _vaciar(self) -> None:
        self.form.limpiar()
        self._quitar_tarjeta()
        self.chk_visita.setChecked(True)

    def _guardar(self) -> None:
        self.form.limpiar_errores()
        datos = self.form.datos()
        try:
            avisos = self.s.beneficiarios.avisos(datos)
            if avisos and not confirmar(
                self, "Revisar datos", "Hay datos que coinciden con otras fichas:",
                si="Guardar igualmente", detalle="\n".join(a.mensaje for a in avisos),
            ):  # fmt: skip
                return
            if not self.uid and not confirmar(
                self, "Sin tarjeta", "No se ha vinculado ninguna tarjeta.",
                si="Guardar sin tarjeta", detalle="Podrá asignarla más tarde desde la ficha.",
            ):  # fmt: skip
                return
            nuevo = self.s.beneficiarios.crear(datos, self.uid, self.chk_visita.isChecked())
        except ErrorValidacion as e:
            if e.campo == "uid":
                self._quitar_tarjeta()
            if not self.form.mostrar_error(e.campo, e.mensaje):
                avisar_error(self, "No se pudo guardar", e.mensaje)
            return
        self._vaciar()
        self.creado.emit(nuevo.id)  # type: ignore[arg-type]
