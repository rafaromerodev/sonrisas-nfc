"""Ficha del beneficiario y cambio de tarjeta."""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QMenu,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from sonrisas_nfc.config import MESES_RENOVACION
from sonrisas_nfc.domain.models import Beneficiario, EstadoExpediente, MotivoCambioTarjeta, OrigenVisita
from sonrisas_nfc.domain.validators import ErrorValidacion, normalizar_uid
from sonrisas_nfc.services.atencion import Resultado, ResultadoAtencion
from sonrisas_nfc.services.contexto import Servicios
from sonrisas_nfc.ui import iconos
from sonrisas_nfc.ui.componentes import (
    Avatar,
    Banner,
    ChipEstado,
    Tarjeta,
    Toast,
    avisar_error,
    boton,
    confirmar,
    etiqueta,
)
from sonrisas_nfc.ui.formulario import FormularioBeneficiario
from sonrisas_nfc.ui.tema import PAPEL

_ORIGENES = {
    OrigenVisita.TARJETA: "Tarjeta",
    OrigenVisita.MANUAL: "Manual",
    OrigenVisita.ALTA: "Alta",
    OrigenVisita.IMPORTADA: "Programa anterior",
}
_ACCIONES = {
    "alta": "Alta", "edicion": "Edición", "renovacion": "Renovación", "baja": "Baja",
    "reactivacion": "Reactivación", "tarjeta": "Tarjeta asignada", "cambio_tarjeta": "Cambio de tarjeta",
}  # fmt: skip


def _tabla(columnas: list[str]) -> QTableWidget:
    t = QTableWidget(0, len(columnas))
    t.setHorizontalHeaderLabels(columnas)
    t.verticalHeader().hide()
    t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    t.setAlternatingRowColors(True)
    t.setShowGrid(False)
    t.verticalHeader().setDefaultSectionSize(38)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    return t


def _rellenar(t: QTableWidget, filas: list[list[str]]) -> None:
    t.setRowCount(len(filas))
    for i, fila in enumerate(filas):
        for j, valor in enumerate(fila):
            t.setItem(i, j, QTableWidgetItem(valor))


class FichaDialog(QDialog):
    """Ficha completa: datos editables, visitas, tarjetas y registro de cambios.

    Si se abre tras pasar una tarjeta (``resultado``), muestra arriba qué ha ocurrido y las
    acciones posibles (renovar, atender igualmente, reactivar...).
    """

    def __init__(
        self,
        servicios: Servicios,
        beneficiario_id: int,
        resultado: ResultadoAtencion | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.s = servicios
        self.bid = beneficiario_id
        self.resultado = resultado
        self._sucio = False
        self.hubo_cambios = False
        self.setWindowTitle("Ficha del beneficiario")
        self.setMinimumSize(980, 720)

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(28, 24, 28, 22)
        raiz.setSpacing(14)

        # Cabecera
        cab = QHBoxLayout()
        cab.setSpacing(16)
        self.avatar = Avatar(tam=68)
        cab.addWidget(self.avatar)
        textos = QVBoxLayout()
        textos.setSpacing(2)
        self.lbl_nombre = etiqueta("", "titulo")
        self.lbl_sub = etiqueta("", "subtitulo")
        textos.addWidget(self.lbl_nombre)
        textos.addWidget(self.lbl_sub)
        cab.addLayout(textos, 1)
        self.chip = ChipEstado()
        cab.addWidget(self.chip, 0, Qt.AlignmentFlag.AlignTop)
        raiz.addLayout(cab)

        self.banner = Banner()
        raiz.addWidget(self.banner)

        # Pestañas
        self.pestanas = QTabWidget()
        self.form = FormularioBeneficiario()
        self.form.establecer_zonas(self._zonas())
        self.form.modificado.connect(self._marcar_sucio)
        contenedor = Tarjeta(margen=22)
        contenedor.capa.addWidget(self.form)
        contenedor.capa.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        envoltorio = QWidget()
        capa_env = QVBoxLayout(envoltorio)
        capa_env.setContentsMargins(2, 8, 8, 8)
        capa_env.addWidget(contenedor)
        scroll.setWidget(envoltorio)
        self.pestanas.addTab(scroll, "Datos")

        self.tabla_visitas = _tabla(["Fecha", "Hora", "Origen"])
        self.pestanas.addTab(self._envolver(self.tabla_visitas), "Visitas")
        self.tabla_tarjetas = _tabla(["UID", "Asignada", "Baja", "Motivo"])
        self.pestanas.addTab(self._envolver(self.tabla_tarjetas), "Tarjetas")
        self.tabla_cambios = _tabla(["Fecha", "Acción", "Detalle"])
        self.tabla_cambios.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.tabla_cambios.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.tabla_cambios.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.pestanas.addTab(self._envolver(self.tabla_cambios), "Registro de cambios")
        raiz.addWidget(self.pestanas, 1)

        # Pie de acciones
        pie = QHBoxLayout()
        pie.setSpacing(10)
        self.b_tarjeta = boton("Cambiar tarjeta", None, "tarjeta", self._cambiar_tarjeta)
        self.b_renovar = boton("Renovar", None, "renovar")
        menu = QMenu(self.b_renovar)
        for meses in MESES_RENOVACION:
            menu.addAction(f"Renovar {meses} meses", lambda m=meses: self._renovar(m))
        self.b_renovar.setMenu(menu)
        self.b_atender = boton("Atender ahora", None, "check", self._atender_manual)
        self.b_atender.setToolTip("Registrar la atención de hoy sin tarjeta (p. ej. si la ha olvidado)")
        self.b_baja = boton("Dar de baja", "peligro", "baja", self._baja_o_reactivar)
        for b in (self.b_tarjeta, self.b_renovar, self.b_atender, self.b_baja):
            pie.addWidget(b)
        pie.addStretch()
        pie.addWidget(boton("Cerrar", None, None, self.reject))
        self.b_guardar = boton("Guardar cambios", "primario", "guardar", self._guardar)
        self.b_guardar.setEnabled(False)
        pie.addWidget(self.b_guardar)
        raiz.addLayout(pie)

        self.toast = Toast(self)
        self._recargar()
        if resultado:
            self._mostrar_resultado(resultado)

    # ------------------------------------------------------------- datos
    def _zonas(self) -> list[str]:
        return [
            r[0] for r in self.s.db.conn.execute("SELECT DISTINCT zona FROM beneficiarios WHERE zona <> ''")
        ]

    @staticmethod
    def _envolver(w: QWidget) -> QWidget:
        caja = QWidget()
        capa = QVBoxLayout(caja)
        capa.setContentsMargins(2, 8, 2, 4)
        capa.addWidget(w)
        return caja

    def _recargar(self, recargar_formulario: bool = True) -> None:
        b = self.s.beneficiarios.obtener(self.bid)
        if b is None:
            self.reject()
            return
        self.b = b
        self.avatar.establecer(b.iniciales)
        self.lbl_nombre.setText(b.nombre_completo)
        partes = [b.documento]
        if b.expediente:
            partes.append(f"Exp. {b.expediente}")
        partes.append(f"Tarjeta {b.tarjeta_uid}" if b.tarjeta_uid else "Sin tarjeta")
        self.lbl_sub.setText("  ·  ".join(partes))
        estado = b.estado()
        texto_chip = estado.value
        if b.vencimiento and estado is not EstadoExpediente.BAJA:
            texto_chip = f"{estado.value} · {b.vencimiento:%d/%m/%Y}"
        self.chip.establecer(estado, texto_chip)
        if recargar_formulario:
            self.form.cargar(b)
            self._sucio = False
            self.b_guardar.setEnabled(False)

        self.b_baja.setText("Reactivar" if not b.activo else "Dar de baja")
        self.b_baja.setProperty("variante", None if not b.activo else "peligro")
        self.b_baja.style().polish(self.b_baja)
        for w in (self.b_tarjeta, self.b_renovar, self.b_atender):
            w.setEnabled(b.activo)
        self.b_tarjeta.setText("Cambiar tarjeta" if b.tarjeta_uid else "Asignar tarjeta")

        visitas = self.s.visitas.historial(b.id)  # type: ignore[arg-type]
        _rellenar(
            self.tabla_visitas,
            [[f"{v.fecha:%d/%m/%Y}", f"{v.fecha:%H:%M}", _ORIGENES[v.origen]] for v in visitas],
        )
        self.pestanas.setTabText(1, f"Visitas ({len(visitas)})")
        _rellenar(
            self.tabla_tarjetas,
            [
                [
                    t.uid, f"{t.asignada_en:%d/%m/%Y}",
                    f"{t.baja_en:%d/%m/%Y}" if t.baja_en else "Activa", t.motivo_baja or "",
                ]
                for t in self.s.tarjetas.historial(b.id)  # type: ignore[arg-type]
            ],
        )  # fmt: skip
        cambios = self.s.db.conn.execute(
            "SELECT fecha, accion, detalle FROM registro_cambios WHERE beneficiario_id = ? ORDER BY id DESC",
            (b.id,),
        ).fetchall()
        _rellenar(
            self.tabla_cambios,
            [[f"{c[0][8:10]}/{c[0][5:7]}/{c[0][:4]} {c[0][11:16]}", _ACCIONES.get(c[1], c[1]), c[2] or ""]
             for c in cambios],
        )  # fmt: skip

    # --------------------------------------------------------- resultado
    def _mostrar_resultado(self, r: ResultadoAtencion) -> None:
        b = self.b
        hogar = f"Hogar: {b.adultos or 0} adultos · {b.menores or 0} menores · {b.mayores or 0} mayores"
        if r.resultado is Resultado.VISITA_REGISTRADA:
            if b.estado() is EstadoExpediente.POR_VENCER:
                dias = (b.vencimiento - date.today()).days  # type: ignore[operator]
                self.banner.mostrar(
                    "aviso",
                    f"Atención registrada a las {r.visita.fecha:%H:%M}",  # type: ignore[union-attr]
                    f"El expediente vence en {dias} días ({b.vencimiento:%d/%m/%Y}).  {hogar}",
                    self._botones_renovar(atender=False),
                )
            else:
                self.banner.mostrar(
                    "ok",
                    f"Atención registrada a las {r.visita.fecha:%H:%M}",  # type: ignore[union-attr]
                    f"Visita nº {b.total_visitas}.  {hogar}",
                )
        elif r.resultado is Resultado.YA_ATENDIDO_HOY:
            self.banner.mostrar(
                "info",
                f"Ya fue atendido/a hoy a las {r.visita.fecha:%H:%M}",  # type: ignore[union-attr]
                "No se ha registrado una segunda visita.",
            )
        elif r.resultado is Resultado.EXPEDIENTE_VENCIDO:
            self.banner.mostrar(
                "error", f"Expediente vencido el {b.vencimiento:%d/%m/%Y}",
                "La atención todavía no se ha registrado. Renueve el expediente o atienda igualmente.",
                self._botones_renovar(atender=True),
            )  # fmt: skip
        elif r.resultado is Resultado.TARJETA_DE_BAJA:
            if not b.activo:
                self._banner_baja()
            else:
                motivo = (r.tarjeta.motivo_baja or "baja").lower()  # type: ignore[union-attr]
                self.banner.mostrar(
                    "error",
                    f"Tarjeta anulada por {motivo} el {r.tarjeta.baja_en:%d/%m/%Y}",  # type: ignore[union-attr]
                    "Esta tarjeta ya no es válida: retírela. La tarjeta actual de esta persona es "
                    f"{b.tarjeta_uid or 'ninguna'}.",
                    [boton("Atender igualmente", None, "check", lambda: self._atender(OrigenVisita.MANUAL))],
                )
        elif r.resultado is Resultado.BENEFICIARIO_DE_BAJA:
            self._banner_baja()

    def _banner_baja(self) -> None:
        self.banner.mostrar(
            "error", "Beneficiario dado de baja",
            "No se ha registrado la atención. Puede reactivarlo si vuelve a ser atendido.",
            [boton("Reactivar", "amarillo", "renovar", self._baja_o_reactivar)],
        )  # fmt: skip

    def _botones_renovar(self, atender: bool) -> list:
        botones = [
            boton(f"Renovar {m} meses", "amarillo", "renovar", lambda m=m: self._renovar(m, atender))
            for m in MESES_RENOVACION
        ]
        if atender:
            botones.append(
                boton("Atender igualmente", None, None, lambda: self._atender(OrigenVisita.TARJETA))
            )
        return botones

    # ----------------------------------------------------------- acciones
    def _atender(self, origen: OrigenVisita) -> None:
        r = self.s.atencion.registrar(self.b, self.resultado.uid if self.resultado else "", origen=origen)
        self.hubo_cambios = True
        self._recargar(recargar_formulario=not self._sucio)
        self.resultado = r
        self._mostrar_resultado(r)

    def _atender_manual(self) -> None:
        self._atender(OrigenVisita.MANUAL)

    def _renovar(self, meses: int, y_atender: bool = False) -> None:
        if self._sucio and not confirmar(
            self, "Cambios sin guardar", "Hay cambios sin guardar en la ficha. ¿Descartarlos y renovar?"
        ):
            return
        self.s.beneficiarios.renovar(self.bid, meses)
        self.hubo_cambios = True
        self._recargar()
        if y_atender:
            self._atender(OrigenVisita.TARJETA)
        else:
            self.banner.hide()
        self.toast.mostrar(f"Expediente renovado hasta el {self.b.vencimiento:%d/%m/%Y}")

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
            self.s.beneficiarios.actualizar(datos)
        except ErrorValidacion as e:
            if not self.form.mostrar_error(e.campo, e.mensaje):
                avisar_error(self, "No se pudo guardar", e.mensaje)
            self.pestanas.setCurrentIndex(0)
            return
        self.hubo_cambios = True
        self._recargar()
        self.toast.mostrar("Cambios guardados")

    def _cambiar_tarjeta(self) -> None:
        dlg = CambiarTarjetaDialog(self.s, self.b, self)
        if dlg.exec():
            self.hubo_cambios = True
            self._recargar(recargar_formulario=not self._sucio)
            self.pestanas.setCurrentIndex(2)
            self.toast.mostrar("Nueva tarjeta asignada. El historial se conserva.")

    def _baja_o_reactivar(self) -> None:
        if self.b.activo:
            if not confirmar(
                self, "Dar de baja", f"¿Dar de baja a {self.b.nombre_completo}?", si="Dar de baja",
                detalle="Su historial se conserva para los informes y su tarjeta queda anulada. "
                "Se puede reactivar más adelante.",
            ):  # fmt: skip
                return
            self.s.beneficiarios.dar_de_baja(self.bid)
            self.toast.mostrar("Beneficiario dado de baja")
        else:
            self.s.beneficiarios.reactivar(self.bid)
            self.toast.mostrar("Beneficiario reactivado. Asígnele una tarjeta si la necesita.")
        self.hubo_cambios = True
        self.banner.hide()
        self._recargar()

    def _marcar_sucio(self) -> None:
        self._sucio = True
        self.b_guardar.setEnabled(True)

    # ----------------------------------------------- integración con el lector
    def recibir_uid(self, uid: str) -> bool:
        """Llamado al pasar una tarjeta con la ficha abierta. ``True`` = evento consumido."""
        if uid == self.b.tarjeta_uid:
            return True
        if self._sucio:
            self.toast.mostrar("Guarde o cierre esta ficha antes de atender otra tarjeta")
            return True
        self.reject()  # se cierra y la ventana principal atiende la nueva tarjeta
        return False

    def reject(self) -> None:
        """Cerrar (botón, Esc o la X de la ventana): pide confirmación si hay cambios sin guardar."""
        if self._sucio and not confirmar(
            self, "Cambios sin guardar", "¿Cerrar la ficha sin guardar los cambios?", si="Cerrar sin guardar"
        ):
            return
        self._sucio = False
        super().reject()


class CambiarTarjetaDialog(QDialog):
    """Asigna una tarjeta nueva a un expediente existente (pérdida, robo, deterioro...)."""

    def __init__(self, servicios: Servicios, beneficiario: Beneficiario, parent=None) -> None:
        super().__init__(parent)
        self.s = servicios
        self.b = beneficiario
        self.uid: str | None = None
        reemplazo = bool(beneficiario.tarjeta_uid)
        self.setWindowTitle("Cambiar tarjeta" if reemplazo else "Asignar tarjeta")
        self.setMinimumWidth(560)

        capa = QVBoxLayout(self)
        capa.setContentsMargins(28, 24, 28, 22)
        capa.setSpacing(14)
        capa.addWidget(etiqueta("TARJETA NFC", "kicker"))
        capa.addWidget(etiqueta(self.windowTitle(), "titulo"))
        capa.addWidget(
            etiqueta(
                f"{beneficiario.nombre_completo} conservará su expediente y todo su historial de visitas."
                + (f" La tarjeta actual ({beneficiario.tarjeta_uid}) quedará anulada." if reemplazo else ""),
                "subtitulo", ajustar=True,
            )
        )  # fmt: skip

        if reemplazo:
            fila = QHBoxLayout()
            fila.addWidget(etiqueta("Motivo del cambio", "etiqueta"))
            self.motivo = QComboBox()
            for m in MotivoCambioTarjeta:
                self.motivo.addItem(m.value, m)
            fila.addWidget(self.motivo, 1)
            capa.addLayout(fila)
        else:
            self.motivo = None

        zona = Tarjeta("azul", margen=26, espacio=6)
        icono = etiqueta()
        icono.setPixmap(iconos.pixmap("nfc", 44, PAPEL, 2.4))
        zona.capa.addWidget(icono, 0, Qt.AlignmentFlag.AlignHCenter)
        self.lbl_instruccion = etiqueta("Acerque la nueva tarjeta al lector", "seccion")
        self.lbl_instruccion.setAlignment(Qt.AlignmentFlag.AlignCenter)
        zona.capa.addWidget(self.lbl_instruccion)
        self.lbl_uid = etiqueta("· · · ·", "uid")
        self.lbl_uid.setAlignment(Qt.AlignmentFlag.AlignCenter)
        zona.capa.addWidget(self.lbl_uid)
        capa.addWidget(zona)

        self.lbl_error = etiqueta("", "error", ajustar=True)
        self.lbl_error.hide()
        capa.addWidget(self.lbl_error)

        manual = QHBoxLayout()
        self.entrada_manual = QLineEdit()
        self.entrada_manual.setPlaceholderText("¿Sin lector? Escriba el UID (p. ej. 04 A1 B2 C3)")
        self.entrada_manual.returnPressed.connect(self._usar_manual)
        manual.addWidget(self.entrada_manual, 1)
        manual.addWidget(boton("Usar", None, None, self._usar_manual))
        capa.addLayout(manual)

        pie = QHBoxLayout()
        pie.addStretch()
        pie.addWidget(boton("Cancelar", None, None, self.reject))
        self.b_ok = boton(
            "Confirmar cambio" if reemplazo else "Asignar tarjeta", "primario", "check", self._confirmar
        )
        self.b_ok.setEnabled(False)
        pie.addWidget(self.b_ok)
        capa.addLayout(pie)

    def recibir_uid(self, uid: str) -> bool:
        self._probar(uid)
        return True

    def _usar_manual(self) -> None:
        self._probar(self.entrada_manual.text())

    def _probar(self, uid: str) -> None:
        self.uid = None
        self.b_ok.setEnabled(False)
        try:
            uid = normalizar_uid(uid)
        except ErrorValidacion as e:
            self._error(e.mensaje)
            return
        self.lbl_uid.setText(uid)
        actual = self.s.tarjetas.activa_por_uid(uid)
        if actual is not None:
            if actual.beneficiario_id == self.b.id:
                self._error("Esa es la tarjeta actual de esta persona. Acerque una tarjeta distinta.")
            else:
                otro = self.s.beneficiarios.obtener(actual.beneficiario_id)
                self._error(
                    f"Esta tarjeta ya pertenece a {otro.nombre_completo if otro else 'otra persona'}."
                )
            return
        self.lbl_error.hide()
        self.lbl_instruccion.setText("Tarjeta detectada")
        self.uid = uid
        self.b_ok.setEnabled(True)
        self.b_ok.setFocus()

    def _error(self, mensaje: str) -> None:
        self.lbl_error.setText(mensaje)
        self.lbl_error.show()
        self.lbl_instruccion.setText("Acerque la nueva tarjeta al lector")

    def _confirmar(self) -> None:
        if not self.uid:
            return
        motivo = self.motivo.currentData() if self.motivo else MotivoCambioTarjeta.OTRO
        try:
            self.s.tarjetas.asignar(self.b.id, self.uid, motivo)  # type: ignore[arg-type]
        except ErrorValidacion as e:
            self._error(e.mensaje)
            return
        self.accept()
