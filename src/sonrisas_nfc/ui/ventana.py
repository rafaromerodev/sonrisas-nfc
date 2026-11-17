"""Ventana principal: navegación lateral, páginas y enrutado de las lecturas de tarjeta."""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from sonrisas_nfc import __version__
from sonrisas_nfc.config import APP_NAME, ASSETS_DIR, ORG_NAME
from sonrisas_nfc.domain.validators import ErrorValidacion, normalizar_uid
from sonrisas_nfc.nfc.lector import EstadoLector, LectorNFC
from sonrisas_nfc.services.atencion import Resultado
from sonrisas_nfc.services.contexto import Servicios
from sonrisas_nfc.ui.componentes import Toast, avisar_error, boton, etiqueta, refrescar_estilo
from sonrisas_nfc.ui.dialogos import FichaDialog
from sonrisas_nfc.ui.paginas.alta import PaginaAlta
from sonrisas_nfc.ui.paginas.beneficiarios import PaginaBeneficiarios
from sonrisas_nfc.ui.paginas.datos import PaginaAyuda, PaginaDatos
from sonrisas_nfc.ui.paginas.informes import PaginaInformes
from sonrisas_nfc.ui.paginas.inicio import PaginaInicio
from sonrisas_nfc.ui.tema import TINTA_SUAVE

log = logging.getLogger(__name__)


class VentanaPrincipal(QMainWindow):
    def __init__(self, servicios: Servicios, lector: LectorNFC | None = None) -> None:
        super().__init__()
        self.s = servicios
        self._ficha: FichaDialog | None = None
        self.setWindowTitle(f"{APP_NAME} · {ORG_NAME}")
        self.setWindowIcon(QIcon(str(ASSETS_DIR / "sonrisas.ico")))
        self.setMinimumSize(1200, 760)

        self.inicio = PaginaInicio(servicios)
        self.beneficiarios = PaginaBeneficiarios(servicios)
        self.alta = PaginaAlta(servicios)
        self.informes = PaginaInformes(servicios)
        self.datos = PaginaDatos(servicios)
        self.ayuda = PaginaAyuda()

        self.pila = QStackedWidget()
        central = QWidget()
        capa = QHBoxLayout(central)
        capa.setContentsMargins(0, 0, 0, 0)
        capa.setSpacing(0)
        capa.addWidget(self._barra_lateral())
        capa.addWidget(self.pila, 1)
        self.setCentralWidget(central)
        self.toast = Toast(central)

        # Conexiones entre páginas
        self.inicio.buscar.connect(self._buscar)
        self.inicio.abrir_beneficiario.connect(self.abrir_ficha)
        self.inicio.ver_filtro.connect(self._ver_filtro)
        self.beneficiarios.abrir_beneficiario.connect(self.abrir_ficha)
        self.informes.abrir_beneficiario.connect(self.abrir_ficha)
        self.beneficiarios.nuevo.connect(lambda: self.ir_a(self.alta))
        self.alta.creado.connect(self._alta_creada)
        self.datos.datos_importados.connect(self.refrescar_todo)

        QShortcut(QKeySequence("Ctrl+F"), self, activated=self._enfocar_busqueda)
        QShortcut(QKeySequence("Ctrl+N"), self, activated=lambda: self.ir_a(self.alta))

        self.lector = lector
        if lector is None:
            self._estado_lector(EstadoLector.NO_DISPONIBLE, "")
        else:
            lector.tarjeta_detectada.connect(self.al_detectar_tarjeta)
            lector.estado_cambiado.connect(self._estado_lector)

        self.refrescar_todo()
        self.ir_a(self.inicio)

    # ------------------------------------------------------------ navegación
    def _barra_lateral(self) -> QFrame:
        barra = QFrame()
        barra.setObjectName("barraLateral")
        barra.setFixedWidth(248)
        capa = QVBoxLayout(barra)
        capa.setContentsMargins(18, 22, 18, 18)
        capa.setSpacing(6)

        logo = QLabel()
        pm = QPixmap(str(ASSETS_DIR / "logo.png"))
        logo.setPixmap(pm.scaledToWidth(120, Qt.TransformationMode.SmoothTransformation))
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        capa.addWidget(logo)
        marca = etiqueta("Registro de atenciones", "etiqueta")
        marca.setAlignment(Qt.AlignmentFlag.AlignCenter)
        capa.addWidget(marca)
        capa.addSpacing(18)

        self.grupo_nav = QButtonGroup(self)
        self.botones_nav: dict[QWidget, object] = {}
        for texto, icono, pagina, atajo in (
            ("Inicio", "inicio", self.inicio, None),
            ("Beneficiarios", "personas", self.beneficiarios, "Ctrl+F"),
            ("Nuevo registro", "alta", self.alta, "Ctrl+N"),
            ("Informes", "informes", self.informes, None),
            ("Datos y copias", "datos", self.datos, None),
            ("Ayuda", "ayuda", self.ayuda, None),
        ):
            self.pila.addWidget(pagina)
            b = boton(f"  {texto}", None, icono, lambda p=pagina: self.ir_a(p))
            b.setProperty("nav", True)
            b.setCheckable(True)
            b.setIconSize(b.iconSize() * 1.1)
            if atajo:
                b.setToolTip(atajo)
            self.grupo_nav.addButton(b)
            self.botones_nav[pagina] = b
            capa.addWidget(b)

        capa.addStretch()
        self.lbl_lector = QLabel("Comprobando lector…")
        self.lbl_lector.setObjectName("estadoLector")
        self.lbl_lector.setWordWrap(True)
        capa.addWidget(self.lbl_lector)
        version = etiqueta(f"v{__version__}", "ayuda")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        version.setStyleSheet(f"color: {TINTA_SUAVE}; font-size: 12px;")
        capa.addWidget(version)
        return barra

    def ir_a(self, pagina: QWidget) -> None:
        self.pila.setCurrentWidget(pagina)
        self.botones_nav[pagina].setChecked(True)  # type: ignore[attr-defined]
        if hasattr(pagina, "refrescar"):
            pagina.refrescar()

    def refrescar_todo(self) -> None:
        for p in (self.inicio, self.beneficiarios, self.alta, self.datos):
            p.refrescar()
        if self.pila.currentWidget() is self.informes:
            self.informes.refrescar()

    def _ver_filtro(self, filtro: str) -> None:
        self.ir_a(self.beneficiarios)
        self.beneficiarios.mostrar_filtro(filtro)

    def _enfocar_busqueda(self) -> None:
        self.ir_a(self.beneficiarios)
        self.beneficiarios.buscador.setFocus()
        self.beneficiarios.buscador.selectAll()

    # ---------------------------------------------------------- acciones
    def abrir_ficha(self, beneficiario_id: int, resultado=None) -> None:
        # Nunca dos fichas a la vez. Se mira si la anterior sigue *visible*: al pasar otra tarjeta,
        # la ficha abierta se cierra y la nueva se abre antes de que termine su exec().
        if self._ficha is not None and self._ficha.isVisible():
            self._ficha.raise_()
            self._ficha.activateWindow()
            return
        dlg = self._ficha = FichaDialog(self.s, beneficiario_id, resultado, self)
        try:
            dlg.exec()
        finally:
            if self._ficha is dlg:
                self._ficha = None
        self.refrescar_todo()

    def _buscar(self, texto: str) -> None:
        resultados = self.s.beneficiarios.buscar(texto)
        buscado = texto.strip().upper()
        exactas = [r for r in resultados if buscado in (r.documento.upper(), (r.expediente or "").upper())]
        if len(exactas) == 1 or len(resultados) == 1:
            self.abrir_ficha((exactas or resultados)[0].id)  # type: ignore[arg-type]
            return
        if not resultados:
            self.toast.mostrar(f"No hay nadie con «{texto}». Puede darlo de alta.")
            self.ir_a(self.alta)
            if any(ch.isdigit() for ch in texto):
                self.alta.prellenar(texto)
            return
        self.ir_a(self.beneficiarios)
        self.beneficiarios.mostrar_filtro("todos", texto)

    def _alta_creada(self, beneficiario_id: int) -> None:
        self.toast.mostrar("Beneficiario registrado correctamente")
        self.ir_a(self.inicio)  # listo para atender a la siguiente persona
        self.refrescar_todo()
        self.abrir_ficha(beneficiario_id)

    # ------------------------------------------------------------- lector
    def _estado_lector(self, estado: EstadoLector, nombre: str) -> None:
        texto = {
            EstadoLector.LISTO: "Lector listo",
            EstadoLector.SIN_LECTOR: "Lector no conectado",
            EstadoLector.NO_DISPONIBLE: "Modo manual (sin lector)",
        }[estado]
        self.lbl_lector.setText(texto)
        self.lbl_lector.setToolTip(nombre)
        self.lbl_lector.setProperty("estado", "ok" if estado is EstadoLector.LISTO else "error")
        refrescar_estilo(self.lbl_lector)

    def al_detectar_tarjeta(self, uid: str) -> None:
        """Enruta una lectura: al diálogo abierto que la espera, al alta o al flujo de atención."""
        QApplication.alert(self)
        modal = QApplication.activeModalWidget()
        if modal is not None:
            receptor = getattr(modal, "recibir_uid", None)
            if receptor is None or receptor(uid):
                return  # el diálogo la ha gestionado (o no admite tarjetas)
        try:
            if self.pila.currentWidget() is self.alta and self._tarjeta_es_para_el_alta(uid):
                self._tarjeta_en_alta(uid)
                return
            r = self.s.atencion.procesar_tarjeta(uid)
        except ErrorValidacion as e:
            avisar_error(self, "Tarjeta no válida", e.mensaje)
            return
        if r.resultado is Resultado.TARJETA_NUEVA:
            self.ir_a(self.alta)
            self.alta.establecer_uid(r.uid)
            self.toast.mostrar("Tarjeta nueva: complete el alta para vincularla")
            return
        self.abrir_ficha(r.beneficiario.id, r)  # type: ignore[union-attr]

    def _tarjeta_es_para_el_alta(self, uid: str) -> bool:
        """En «Nuevo registro», ¿la tarjeta es para vincularla o alguien viene a ser atendido?

        Si el formulario está vacío y la tarjeta ya es de alguien, se le atiende con normalidad
        (p. ej. justo después de guardar un alta llega la siguiente persona).
        """
        return not (self.alta.esta_vacio() and self.s.tarjetas.activa_por_uid(uid) is not None)

    def _tarjeta_en_alta(self, uid: str) -> None:
        en_uso = self.s.tarjetas.activa_por_uid(uid)
        if en_uso is not None:
            otro = self.s.beneficiarios.obtener(en_uso.beneficiario_id)
            avisar_error(
                self, "Tarjeta ya asignada",
                f"Esta tarjeta pertenece a {otro.nombre_completo if otro else 'otra persona'}.",
                "Use una tarjeta nueva. Para atender a esa persona, vaya a Inicio y pase la tarjeta.",
            )  # fmt: skip
            return
        self.alta.establecer_uid(normalizar_uid(uid))
        self.toast.mostrar("Tarjeta lista para vincular")

    def closeEvent(self, e) -> None:
        if self.lector:
            self.lector.detener()
        super().closeEvent(e)
