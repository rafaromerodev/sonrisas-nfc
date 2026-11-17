"""Pruebas de aceptación de extremo a extremo: cada función del programa, usada desde la interfaz.

Se manejan los mismos controles que usaría la persona de la ONG (escribir, pulsar botones,
pasar tarjetas, exportar). Los cuadros de diálogo modales se sustituyen por respuestas
automáticas registradas en ``Mesa`` para que las pruebas no se queden esperando.
"""

from __future__ import annotations

import csv
import os
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QDate, QEvent, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QKeyEvent, QShortcut
from PySide6.QtPdf import QPdfDocument
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFileDialog

from sonrisas_nfc import config
from sonrisas_nfc.db.database import abrir
from sonrisas_nfc.domain.models import MotivoCambioTarjeta, OrigenVisita, sumar_meses
from sonrisas_nfc.domain.validators import letra_control
from sonrisas_nfc.nfc import lector as modulo_lector
from sonrisas_nfc.nfc.lector import EstadoLector, LectorNFC
from sonrisas_nfc.services import copias
from sonrisas_nfc.services.contexto import Servicios
from sonrisas_nfc.ui import dialogos, tema
from sonrisas_nfc.ui import ventana as modulo_ventana
from sonrisas_nfc.ui.dialogos import CambiarTarjetaDialog, FichaDialog
from sonrisas_nfc.ui.paginas import alta as modulo_alta
from sonrisas_nfc.ui.paginas import datos as modulo_datos
from sonrisas_nfc.ui.paginas import informes as modulo_informes
from sonrisas_nfc.ui.ventana import VentanaPrincipal
from tests.test_importador import ESQUEMA_V1

HOY = date.today()


# --------------------------------------------------------------------------- utilidades
def dni(n: int) -> str:
    numero = 10_000_000 + n
    return f"{numero}{letra_control(numero)}"


@dataclass
class Mesa:
    """Registro de los cuadros de diálogo que habría visto el usuario y sus respuestas."""

    responder: bool = True
    confirmaciones: list[str] = field(default_factory=list)
    informaciones: list[str] = field(default_factory=list)
    errores: list[str] = field(default_factory=list)
    fichas: list[FichaDialog] = field(default_factory=list)
    urls_abiertas: list[QUrl] = field(default_factory=list)
    uid_nueva_tarjeta: str = ""
    motivo: MotivoCambioTarjeta = MotivoCambioTarjeta.PERDIDA

    @property
    def ficha(self) -> FichaDialog:
        return self.fichas[-1]


@pytest.fixture(scope="module")
def app():
    a = QApplication.instance() or QApplication([])
    tema.aplicar(a)
    return a


@pytest.fixture
def mesa(monkeypatch) -> Mesa:
    m = Mesa()

    def confirmar(_p, titulo, *a, **k):
        m.confirmaciones.append(titulo)
        return m.responder

    def informar(_p, titulo, *a, **k):
        m.informaciones.append(titulo)

    def avisar_error(_p, titulo, *a, **k):
        m.errores.append(titulo)

    for modulo in (dialogos, modulo_alta, modulo_datos, modulo_ventana, modulo_informes):
        for nombre, funcion in (
            ("confirmar", confirmar),
            ("informar", informar),
            ("avisar_error", avisar_error),
        ):
            if hasattr(modulo, nombre):
                monkeypatch.setattr(modulo, nombre, funcion)

    # La ficha se abre sin bloquear (en la app real es modal) y queda accesible para la prueba.
    def abrir_ficha(self, bid, resultado=None):
        dlg = FichaDialog(self.s, bid, resultado, self)
        dlg.show()
        m.fichas.append(dlg)

    monkeypatch.setattr(VentanaPrincipal, "abrir_ficha", abrir_ficha)

    # Cambio de tarjeta: se "acerca" la tarjeta configurada en la mesa y se confirma.
    def exec_cambio(dlg: CambiarTarjetaDialog):
        if dlg.motivo is not None:
            dlg.motivo.setCurrentIndex(dlg.motivo.findData(m.motivo))
        dlg.recibir_uid(m.uid_nueva_tarjeta)
        if dlg.b_ok.isEnabled():
            dlg._confirmar()
        return dlg.result()

    monkeypatch.setattr(CambiarTarjetaDialog, "exec", exec_cambio)
    monkeypatch.setattr(QDesktopServices, "openUrl", staticmethod(lambda url: m.urls_abiertas.append(url)))
    return m


@pytest.fixture
def v(app, servicios, mesa) -> VentanaPrincipal:
    w = VentanaPrincipal(servicios)
    w.resize(1366, 768)
    w.show()
    yield w
    for f in mesa.fichas:
        f._sucio = False
        f.close()
    w.close()


def crear(s: Servicios, n: int, uid: str | None = None, visita: bool = False, **campos):
    base = dict(
        documento=dni(n), nombre=f"Nombre{n}", apellidos=f"Apellido{n}", telefono=f"6{n:08d}",
        expediente=str(n), adultos=1, menores=0, mayores=0, zona="Valleseco",
        vencimiento=HOY + timedelta(days=200),
    )  # fmt: skip
    base.update(campos)
    from sonrisas_nfc.domain.models import Beneficiario

    return s.beneficiarios.crear(Beneficiario(**base), tarjeta_uid=uid, registrar_visita=visita)


def banner(ficha: FichaDialog) -> tuple[str, dict]:
    capa = ficha.banner._acciones
    botones = {capa.itemAt(i).widget().text(): capa.itemAt(i).widget() for i in range(capa.count())}
    return (ficha.banner._titulo.text() if ficha.banner.isVisible() else ""), botones


def escribir(campo, texto: str) -> None:
    """Escribe tecla a tecla como un usuario (emite textEdited, a diferencia de setText).

    Se envían los eventos de teclado directamente: ``QTest.keyClicks`` cierra el proceso con
    caracteres no ASCII (tildes, ñ) en PySide6 6.12, y aquí necesitamos probar justo esos.
    """
    campo.clear()
    for caracter in texto:
        for tipo in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
            QApplication.sendEvent(campo, QKeyEvent(tipo, 0, Qt.KeyboardModifier.NoModifier, caracter))


def pasar_tarjeta(v: VentanaPrincipal, uid: str) -> None:
    v.al_detectar_tarjeta(uid)


# ============================================================ 1. Alta de beneficiarios
def test_01_alta_completa_pasando_tarjeta_nueva(v, servicios, mesa):
    pasar_tarjeta(v, "04 10 20 30")
    assert v.pila.currentWidget() is v.alta, "una tarjeta nueva debe llevar al alta"
    assert v.alta.uid == "04 10 20 30"

    f = v.alta.form
    escribir(f.nombre, "Lucía")
    escribir(f.apellidos, "Santana Pérez")
    escribir(f.documento, "12.345.678-z")
    escribir(f.telefono, "612 345 678")
    escribir(f.expediente, "45")
    escribir(f.zona, "Valleseco")
    f._poner_vencimiento(12)  # botón «+12 meses»
    f.adultos.setValue(2)
    f.menores.setValue(1)
    v.alta.b_guardar.click()

    assert mesa.errores == []
    b = servicios.beneficiarios.obtener_por_documento("12345678Z")
    assert b is not None
    assert (b.nombre, b.telefono, b.expediente, b.tarjeta_uid) == ("Lucía", "612345678", "45", "04 10 20 30")
    assert b.vencimiento == sumar_meses(HOY, 12)
    assert b.total_visitas == 1, "el alta registra la primera atención"
    assert mesa.ficha.b.id == b.id, "tras el alta se abre la ficha"
    assert v.alta.form.nombre.text() == "" and v.alta.uid is None, "el formulario queda limpio"


def test_02_alta_sin_registrar_primera_visita_y_sin_tarjeta(v, servicios, mesa):
    v.ir_a(v.alta)
    f = v.alta.form
    for campo, texto in (
        (f.nombre, "Ana"),
        (f.apellidos, "Díaz"),
        (f.documento, "X1234567L"),
        (f.telefono, "699000111"),
    ):
        escribir(campo, texto)
    v.alta.chk_visita.setChecked(False)
    mesa.responder = False  # «¿Guardar sin tarjeta?» → Cancelar
    v.alta.b_guardar.click()
    assert "Sin tarjeta" in mesa.confirmaciones
    assert servicios.beneficiarios.obtener_por_documento("X1234567L") is None
    mesa.responder = True
    v.alta.b_guardar.click()
    b = servicios.beneficiarios.obtener_por_documento("X1234567L")
    assert b is not None and b.total_visitas == 0 and b.tarjeta_uid is None


@pytest.mark.parametrize(
    ("campo", "valor", "mensaje"),
    [
        ("nombre", "", "obligatorio"),
        ("documento", "12345678A", "debería ser Z"),
        ("documento", "12345678", "Falta la letra"),
        ("telefono", "12345", "9 dígitos"),
    ],
)
def test_03_alta_validaciones_en_el_campo(v, servicios, mesa, campo, valor, mensaje):
    v.ir_a(v.alta)
    f = v.alta.form
    for c, texto in (
        ("nombre", "Ana"),
        ("apellidos", "Díaz"),
        ("documento", "12345678Z"),
        ("telefono", "612345678"),
    ):
        escribir(getattr(f, c), valor if c == campo else texto)
    v.alta.establecer_uid("04 99 99 99")
    v.alta.b_guardar.click()
    error = f.campos[campo].error
    assert not error.isHidden() and mensaje in error.text()
    assert f.campos[campo].control.property("error") is True
    assert servicios.beneficiarios.listar() == []
    escribir(getattr(f, campo), "X")  # al corregir, el error desaparece
    assert error.isHidden()


def test_04_alta_duplicados(v, servicios, mesa):
    crear(servicios, 1, uid="04 00 00 01")
    v.ir_a(v.alta)
    f = v.alta.form
    for c, texto in (
        ("nombre", "Otra"),
        ("apellidos", "Persona"),
        ("documento", dni(1)),
        ("telefono", "611111111"),
    ):
        escribir(getattr(f, c), texto)
    v.alta.establecer_uid("04 00 00 02")
    v.alta.b_guardar.click()
    assert "Ya existe" in f.campos["documento"].error.text()

    # Teléfono repetido: aviso que se puede aceptar
    escribir(f.documento, dni(2))
    escribir(f.telefono, f"6{1:08d}")
    mesa.responder = False
    v.alta.b_guardar.click()
    assert "Revisar datos" in mesa.confirmaciones
    assert servicios.beneficiarios.obtener_por_documento(dni(2)) is None
    mesa.responder = True
    v.alta.b_guardar.click()
    assert servicios.beneficiarios.obtener_por_documento(dni(2)) is not None


def test_05_tarjeta_ya_asignada_no_se_vincula_en_el_alta(v, servicios, mesa):
    crear(servicios, 1, uid="04 00 00 01")
    v.ir_a(v.alta)
    escribir(v.alta.form.nombre, "Alguien")  # se está rellenando un alta
    pasar_tarjeta(v, "04000001")
    assert "Tarjeta ya asignada" in mesa.errores
    assert v.alta.uid is None and mesa.fichas == []
    pasar_tarjeta(v, "04 00 00 09")
    assert v.alta.uid == "04 00 00 09"
    v.alta._quitar_tarjeta()  # botón «Quitar tarjeta»
    assert v.alta.uid is None


def test_05b_tras_un_alta_la_siguiente_tarjeta_se_atiende(v, servicios, mesa):
    """Regresión: tras guardar un alta, la siguiente persona que pasaba su tarjeta recibía
    «Tarjeta ya asignada» porque el programa seguía en «Nuevo registro»."""
    crear(servicios, 1, uid="04 00 00 01")
    pasar_tarjeta(v, "04 77 77 77")
    f = v.alta.form
    for c, t in (
        ("nombre", "Nueva"),
        ("apellidos", "Persona"),
        ("documento", dni(9)),
        ("telefono", "600000009"),
    ):
        escribir(getattr(f, c), t)
    v.alta.b_guardar.click()
    assert v.pila.currentWidget() is v.inicio, "tras el alta se vuelve a Inicio"
    pasar_tarjeta(v, "04 00 00 01")
    assert mesa.errores == []
    assert banner(mesa.ficha)[0].startswith("Atención registrada")
    # Aun estando en «Nuevo registro» con el formulario vacío, se atiende con normalidad
    v.ir_a(v.alta)
    pasar_tarjeta(v, "04 77 77 77")
    assert mesa.errores == [] and banner(mesa.ficha)[0].startswith("Ya fue atendido/a hoy")


def test_05c_botones_de_meses_del_formulario(v, servicios, mesa):
    """Regresión: «+6 meses»/«+12 meses» ponían la fecha de hoy (Qt pasaba False como meses)."""
    from PySide6.QtWidgets import QPushButton

    v.ir_a(v.alta)
    botones = {b.text(): b for b in v.alta.form.findChildren(QPushButton)}
    for texto, meses in (("+6 meses", 6), ("+12 meses", 12)):
        botones[texto].click()
        assert v.alta.form.vencimiento.date().toPython() == sumar_meses(HOY, meses)


# ========================================================= 2. Atención con tarjeta
def test_06_atencion_normal_y_una_sola_por_dia(v, servicios, mesa):
    b = crear(servicios, 1, uid="04 00 00 01")
    pasar_tarjeta(v, "04 00 00 01")
    titulo, _ = banner(mesa.ficha)
    assert titulo.startswith("Atención registrada")
    assert servicios.beneficiarios.obtener(b.id).total_visitas == 1

    pasar_tarjeta(v, "04 00 00 01")  # vuelve a pasar la tarjeta el mismo día
    titulo, _ = banner(mesa.ficha)
    assert titulo.startswith("Ya fue atendido/a hoy")
    assert servicios.beneficiarios.obtener(b.id).total_visitas == 1

    v.ir_a(v.inicio)
    assert v.inicio.c_hoy.valor.text() == "1"
    textos = [
        v.inicio.lista.itemAt(i).widget().findChildren(type(v.inicio.cabecera.titulo))[1].text()
        for i in range(v.inicio.lista.count())
    ]
    assert "Nombre1 Apellido1" in textos


def test_07_expediente_vencido_renovar_desde_el_aviso(v, servicios, mesa):
    b = crear(servicios, 1, uid="04 00 00 01", vencimiento=HOY - timedelta(days=1))
    pasar_tarjeta(v, "04 00 00 01")
    titulo, botones = banner(mesa.ficha)
    assert titulo.startswith("Expediente vencido")
    assert servicios.beneficiarios.obtener(b.id).total_visitas == 0, "no se registra sin confirmar"
    botones["Renovar 6 meses"].click()
    actual = servicios.beneficiarios.obtener(b.id)
    assert actual.vencimiento == sumar_meses(HOY, 6)
    assert actual.total_visitas == 1
    assert banner(mesa.ficha)[0].startswith("Atención registrada")


def test_08_expediente_vencido_atender_igualmente(v, servicios, mesa):
    vencimiento = HOY - timedelta(days=30)
    b = crear(servicios, 1, uid="04 00 00 01", vencimiento=vencimiento)
    pasar_tarjeta(v, "04 00 00 01")
    banner(mesa.ficha)[1]["Atender igualmente"].click()
    actual = servicios.beneficiarios.obtener(b.id)
    assert actual.total_visitas == 1 and actual.vencimiento == vencimiento


def test_09_aviso_de_expediente_por_vencer(v, servicios, mesa):
    crear(servicios, 1, uid="04 00 00 01", vencimiento=HOY + timedelta(days=10))
    pasar_tarjeta(v, "04 00 00 01")
    titulo, botones = banner(mesa.ficha)
    assert titulo.startswith("Atención registrada")
    assert "vence en 10 días" in mesa.ficha.banner._detalle.text()
    assert "Renovar 12 meses" in botones


# ======================================================= 3. Tarjeta perdida (cambio)
def test_10_cambio_de_tarjeta_por_perdida_conserva_historial(v, servicios, mesa):
    b = crear(servicios, 1, uid="04 00 00 0A")
    for dias in (14, 7):
        servicios.visitas.registrar(b.id, momento=datetime.now() - timedelta(days=dias))

    v.abrir_ficha(b.id)
    mesa.uid_nueva_tarjeta, mesa.motivo = "04 00 00 0B", MotivoCambioTarjeta.PERDIDA
    mesa.ficha.b_tarjeta.click()

    actual = servicios.beneficiarios.obtener(b.id)
    assert actual.tarjeta_uid == "04 00 00 0B"
    assert actual.total_visitas == 2, "el historial se conserva"
    tabla = mesa.ficha.tabla_tarjetas
    assert tabla.rowCount() == 2 and tabla.item(1, 3).text() == "Pérdida"
    assert mesa.ficha.pestanas.currentIndex() == 2

    pasar_tarjeta(v, "04 00 00 0A")  # aparece la tarjeta perdida
    titulo, botones = banner(mesa.ficha)
    assert titulo.startswith("Tarjeta anulada por pérdida")
    botones["Atender igualmente"].click()
    assert servicios.beneficiarios.obtener(b.id).total_visitas == 3

    pasar_tarjeta(v, "04 00 00 0B")  # la nueva funciona (y no duplica la atención de hoy)
    assert banner(mesa.ficha)[0].startswith("Ya fue atendido/a hoy")


def test_11_no_se_puede_usar_la_tarjeta_de_otra_persona_ni_la_propia(v, servicios, mesa):
    a = crear(servicios, 1, uid="04 00 00 01")
    crear(servicios, 2, uid="04 00 00 02")
    v.abrir_ficha(a.id)
    for uid in ("04 00 00 02", "04 00 00 01"):
        mesa.uid_nueva_tarjeta = uid
        mesa.ficha.b_tarjeta.click()
        assert servicios.beneficiarios.obtener(a.id).tarjeta_uid == "04 00 00 01"


def test_12_asignar_tarjeta_a_quien_no_tiene(v, servicios, mesa):
    b = crear(servicios, 1)
    v.abrir_ficha(b.id)
    assert mesa.ficha.b_tarjeta.text() == "Asignar tarjeta"
    mesa.uid_nueva_tarjeta = "04aabbcc"
    mesa.ficha.b_tarjeta.click()
    assert servicios.beneficiarios.obtener(b.id).tarjeta_uid == "04 AA BB CC"
    assert mesa.ficha.b_tarjeta.text() == "Cambiar tarjeta"


# ================================================================ 4. Ficha
def test_13_editar_y_corregir_documento(v, servicios, mesa):
    b = crear(servicios, 1, uid="04 00 00 01")
    v.abrir_ficha(b.id)
    ficha = mesa.ficha
    assert not ficha.b_guardar.isEnabled()
    escribir(ficha.form.documento, dni(50))
    escribir(ficha.form.telefono, "699 999 999")
    ficha.form.menores.setValue(3)
    assert ficha.b_guardar.isEnabled()
    ficha.b_guardar.click()
    actual = servicios.beneficiarios.obtener(b.id)
    assert (actual.documento, actual.telefono, actual.menores) == (dni(50), "699999999", 3)
    assert actual.tarjeta_uid == "04 00 00 01"
    assert ficha.tabla_cambios.item(0, 1).text() == "Edición"
    assert "Documento" in ficha.tabla_cambios.item(0, 2).text()


def test_14_editar_con_error_no_guarda(v, servicios, mesa):
    b = crear(servicios, 1)
    v.abrir_ficha(b.id)
    escribir(mesa.ficha.form.telefono, "123")
    mesa.ficha.b_guardar.click()
    assert not mesa.ficha.form.campos["telefono"].error.isHidden()
    assert servicios.beneficiarios.obtener(b.id).telefono == b.telefono


def test_15_cerrar_ficha_con_cambios_sin_guardar(v, servicios, mesa):
    b = crear(servicios, 1)
    v.abrir_ficha(b.id)
    escribir(mesa.ficha.form.zona, "Otra zona")
    mesa.responder = False
    mesa.ficha.reject()
    assert mesa.ficha.isVisible(), "cancelar mantiene la ficha abierta"
    mesa.responder = True
    mesa.ficha.reject()
    assert not mesa.ficha.isVisible()
    assert servicios.beneficiarios.obtener(b.id).zona == "Valleseco", "no se guardó"


def test_16_atender_ahora_sin_tarjeta_y_renovar_desde_el_menu(v, servicios, mesa):
    b = crear(servicios, 1, vencimiento=HOY + timedelta(days=5))
    v.abrir_ficha(b.id)
    mesa.ficha.b_atender.click()
    mesa.ficha.b_atender.click()
    visitas = servicios.visitas.historial(b.id)
    assert len(visitas) == 1 and visitas[0].origen is OrigenVisita.MANUAL
    assert mesa.ficha.tabla_visitas.item(0, 2).text() == "Manual"

    acciones = {a.text(): a for a in mesa.ficha.b_renovar.menu().actions()}
    acciones["Renovar 12 meses"].trigger()
    # vigente: se suma desde el vencimiento actual, no desde hoy
    assert servicios.beneficiarios.obtener(b.id).vencimiento == sumar_meses(HOY + timedelta(days=5), 12)


def test_17_dar_de_baja_y_reactivar(v, servicios, mesa):
    b = crear(servicios, 1, uid="04 00 00 01", visita=True)
    v.abrir_ficha(b.id)
    mesa.ficha.b_baja.click()
    assert "Dar de baja" in mesa.confirmaciones
    actual = servicios.beneficiarios.obtener(b.id)
    assert not actual.activo and actual.tarjeta_uid is None
    assert not mesa.ficha.b_atender.isEnabled() and mesa.ficha.b_baja.text() == "Reactivar"

    pasar_tarjeta(v, "04 00 00 01")
    titulo, botones = banner(mesa.ficha)
    assert titulo == "Beneficiario dado de baja"
    botones["Reactivar"].click()
    assert servicios.beneficiarios.obtener(b.id).activo
    assert servicios.informes.generar(HOY, HOY).atenciones == 1, "la baja no borra el historial"


def test_18_pasar_otra_tarjeta_con_una_ficha_abierta(v, servicios, mesa):
    a = crear(servicios, 1, uid="04 00 00 01")
    crear(servicios, 2, uid="04 00 00 02")
    v.abrir_ficha(a.id)
    ficha = mesa.ficha
    assert ficha.recibir_uid("04 00 00 01") is True, "su propia tarjeta se ignora"
    escribir(ficha.form.zona, "Cambio pendiente")
    assert ficha.recibir_uid("04 00 00 02") is True and ficha.isVisible(), (
        "con cambios sin guardar no se cierra"
    )
    ficha._sucio = False
    assert ficha.recibir_uid("04 00 00 02") is False and not ficha.isVisible(), (
        "se cierra para atender la nueva"
    )


# ======================================================== 5. Listado y búsquedas
def _poblar_estados(s):
    crear(s, 1, uid="04 00 00 01", expediente="100")  # vigente
    crear(s, 2, uid="04 00 00 02", expediente="45", vencimiento=HOY + timedelta(days=10))  # por vencer
    crear(s, 3, uid="04 00 00 03", expediente="1234", vencimiento=HOY - timedelta(days=3), apellidos="Pérez")
    crear(s, 4, expediente="145")  # sin tarjeta
    baja = crear(s, 5, uid="04 00 00 05", expediente="7")
    s.beneficiarios.dar_de_baja(baja.id)


def test_19_filtros_del_listado(v, servicios, mesa):
    _poblar_estados(servicios)
    p = v.beneficiarios
    v.ir_a(p)
    esperado = {
        "activos": 4,
        "vigentes": 2,
        "por_vencer": 1,
        "vencidos": 1,
        "sin_tarjeta": 1,
        "bajas": 1,
        "todos": 5,
    }
    for filtro, n in esperado.items():
        p.botones_filtro[filtro].click()
        assert p.proxy.rowCount() == n, filtro
        assert p.lbl_total.text().startswith(str(n))


def test_20_orden_por_defecto_y_selector(v, servicios, mesa):
    _poblar_estados(servicios)
    p = v.beneficiarios
    v.ir_a(p)

    def expedientes():
        return [p.proxy.index(i, 1).data() for i in range(p.proxy.rowCount())]

    assert expedientes() == ["45", "100", "145", "1234"]
    textos = [p.combo_orden.itemText(i) for i in range(p.combo_orden.count())]
    for texto in textos:
        p.combo_orden.setCurrentIndex(textos.index(texto))
        assert len(expedientes()) == 4, texto
    p.combo_orden.setCurrentIndex(textos.index("Vencimiento (más próximo)"))
    assert expedientes()[0] == "1234"
    p.combo_orden.setCurrentIndex(textos.index("Nº de expediente (mayor a menor)"))
    assert expedientes() == ["1234", "145", "100", "45"]


def test_21_buscador_del_listado(v, servicios, mesa):
    _poblar_estados(servicios)
    p = v.beneficiarios
    v.ir_a(p)
    escribir(p.buscador, "perez")  # sin tilde encuentra «Pérez»
    assert p.proxy.rowCount() == 1
    escribir(p.buscador, "45")
    assert p.proxy.rowCount() == 2  # 45 y 145 mientras se escribe…
    QTest.keyClick(p.buscador, Qt.Key.Key_Return)
    assert mesa.ficha.b.expediente == "45"  # …pero Intro abre el exacto
    escribir(p.buscador, dni(3))
    QTest.keyClick(p.buscador, Qt.Key.Key_Return)
    assert mesa.ficha.b.documento == dni(3)
    escribir(p.buscador, "7")  # está de baja: Intro lo busca también entre las bajas
    QTest.keyClick(p.buscador, Qt.Key.Key_Return)
    assert mesa.ficha.b.expediente == "7"


def test_22_doble_clic_en_el_listado_abre_una_ficha(v, servicios, mesa):
    _poblar_estados(servicios)
    p = v.beneficiarios
    v.ir_a(p)
    celda = p.tabla.visualRect(p.proxy.index(0, 3)).center()
    QTest.mouseClick(p.tabla.viewport(), Qt.MouseButton.LeftButton, pos=celda)
    QTest.mouseDClick(p.tabla.viewport(), Qt.MouseButton.LeftButton, pos=celda)
    assert len(mesa.fichas) == 1 and mesa.ficha.b.expediente == "45"


def test_23_buscador_y_cifras_de_inicio(v, servicios, mesa):
    _poblar_estados(servicios)
    v.ir_a(v.inicio)
    assert [c.valor.text() for c in (v.inicio.c_activos, v.inicio.c_vencidos, v.inicio.c_por_vencer,
                                     v.inicio.c_sin_tarjeta)] == ["4", "1", "1", "1"]  # fmt: skip
    escribir(v.inicio.entrada, "45")
    QTest.keyClick(v.inicio.entrada, Qt.Key.Key_Return)
    assert mesa.ficha.b.expediente == "45", "exacto aunque exista el 145"

    escribir(v.inicio.entrada, "Nombre")  # varios resultados → listado filtrado
    QTest.keyClick(v.inicio.entrada, Qt.Key.Key_Return)
    assert v.pila.currentWidget() is v.beneficiarios and v.beneficiarios.proxy.rowCount() == 5

    escribir(v.inicio.entrada, "99999999R")  # no existe → alta con el documento
    QTest.keyClick(v.inicio.entrada, Qt.Key.Key_Return)
    assert v.pila.currentWidget() is v.alta and v.alta.form.documento.text() == "99999999R"

    v.ir_a(v.inicio)
    QTest.mouseClick(v.inicio.c_vencidos, Qt.MouseButton.LeftButton)  # las cifras son clicables
    assert v.pila.currentWidget() is v.beneficiarios and v.beneficiarios.proxy.rowCount() == 1


def test_24_atajos_de_teclado_y_navegacion(v, servicios, mesa):
    atajos = {s.key().toString(): s for s in v.findChildren(QShortcut)}
    atajos["Ctrl+N"].activated.emit()
    assert v.pila.currentWidget() is v.alta
    atajos["Ctrl+F"].activated.emit()
    assert v.pila.currentWidget() is v.beneficiarios
    for pagina, boton in v.botones_nav.items():
        boton.click()
        assert v.pila.currentWidget() is pagina and boton.isChecked()


def test_25_indicador_del_lector(v):
    v._estado_lector(EstadoLector.LISTO, "ACS ACR122U PICC Interface 0")
    assert v.lbl_lector.text() == "Lector listo" and v.lbl_lector.property("estado") == "ok"
    v._estado_lector(EstadoLector.SIN_LECTOR, "")
    assert v.lbl_lector.text() == "Lector no conectado" and v.lbl_lector.property("estado") == "error"


# ================================================================ 6. Informes
def _poblar_informe(s):
    a = crear(s, 1, expediente="100", zona="Valleseco", adultos=2, menores=2)
    b = crear(s, 2, expediente="45", zona="Taco")
    c = crear(s, 3, expediente="1234", zona="Taco")
    jueves = HOY - timedelta(days=(HOY.weekday() - 3) % 7 or 7)
    for persona, veces in ((a, 3), (b, 1), (c, 6)):
        for i in range(veces):
            dia = jueves - timedelta(weeks=i)
            s.visitas.registrar(
                persona.id, momento=datetime.combine(dia, datetime.min.time()) + timedelta(hours=10)
            )
    return jueves


def test_26_informe_cifras_zonas_y_periodos(v, servicios, mesa):
    _poblar_informe(servicios)
    p = v.informes
    v.ir_a(p)
    p._preset("anio")
    p.desde.setDate(QDate.fromString((HOY - timedelta(days=400)).isoformat(), "yyyy-MM-dd"))
    assert p.c_atenciones.valor.text() == "10"
    assert p.c_personas.valor.text() == "3"
    assert p.c_hogar.valor.text() == "6"  # 4 + 1 + 1
    assert {p.tabla_zonas.item(i, 0).text() for i in range(p.tabla_zonas.rowCount())} == {"Valleseco", "Taco"}
    assert sum(p.grafica.valores) == 10 and p.grafica.valores[3] == 10  # todo en jueves
    # Se pulsan los botones reales (regresión: todos daban «Año anterior»)
    from PySide6.QtWidgets import QPushButton

    botones = {b.text(): b for b in p.findChildren(QPushButton)}
    mes_pasado = HOY.replace(day=1) - timedelta(days=1)
    esperado = {
        "Este mes": (HOY.replace(day=1), HOY),
        "Mes anterior": (mes_pasado.replace(day=1), mes_pasado),
        "Trimestre": (date(HOY.year, 3 * ((HOY.month - 1) // 3) + 1, 1), HOY),
        "Este año": (date(HOY.year, 1, 1), HOY),
        "Año anterior": (date(HOY.year - 1, 1, 1), date(HOY.year - 1, 12, 31)),
    }
    for texto, (desde, hasta) in esperado.items():
        botones[texto].click()
        assert (p.desde.date().toPython(), p.hasta.date().toPython()) == (desde, hasta), texto


def test_27_relacion_de_expedientes_filtros_orden_y_busqueda(v, servicios, mesa):
    _poblar_informe(servicios)
    p = v.informes
    v.ir_a(p)
    p.desde.setDate(QDate.fromString((HOY - timedelta(days=400)).isoformat(), "yyyy-MM-dd"))

    def visibles():
        return [p.tabla_detalle.item(i, 0).text() for i in range(p.tabla_detalle.rowCount())]

    assert visibles() == ["45", "100", "1234"], "por defecto, nº de expediente de menor a mayor"
    assert p.pestanas.tabText(1) == "Expedientes atendidos (3)"
    p.combo_orden.setCurrentIndex(p.combo_orden.findText("Más atenciones primero"))
    assert visibles() == ["1234", "100", "45"]
    p.combo_apariciones.setCurrentIndex(p.combo_apariciones.findText("5 o más veces"))
    assert visibles() == ["1234"]
    p.combo_apariciones.setCurrentIndex(0)
    p.combo_orden.setCurrentIndex(0)
    escribir(p.buscador, "45")
    assert len(visibles()) == 3, "el filtro se aplica al pulsar Intro"
    QTest.keyClick(p.buscador, Qt.Key.Key_Return)
    assert visibles() == ["45"]
    p.buscador.clear()
    assert len(visibles()) == 3, "vaciar el buscador muestra todo"
    p.tabla_detalle.cellDoubleClicked.emit(0, 0)
    assert mesa.ficha.b.expediente == "45"


def test_28_exportar_pdf_y_csv_respetando_filtros(v, servicios, mesa, tmp_path, monkeypatch):
    _poblar_informe(servicios)
    p = v.informes
    v.ir_a(p)
    p.desde.setDate(QDate.fromString((HOY - timedelta(days=400)).isoformat(), "yyyy-MM-dd"))
    p.combo_apariciones.setCurrentIndex(p.combo_apariciones.findText("2 o más veces"))

    destino_pdf, destino_csv = tmp_path / "informe", tmp_path / "informe.csv"
    rutas = iter([str(destino_pdf), str(destino_csv)])  # sin extensión: se añade sola
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (next(rutas), "")))
    p._pdf()
    p._csv()

    pdf = destino_pdf.with_suffix(".pdf")
    doc = QPdfDocument()
    doc.load(str(pdf))
    texto = doc.getAllText(0).text()
    assert "Informe de atenciones" in texto and "Nombre3 Apellido3" in texto
    assert "Filtrado por apariciones: 2 o más veces: 2 de 3 personas" in " ".join(texto.split())
    assert "Nombre2" not in texto, "el filtrado no aparece en el PDF"
    assert Path(mesa.urls_abiertas[0].toLocalFile()) == pdf, "el PDF se abre al terminar"

    contenido = destino_csv.read_bytes()
    assert contenido.startswith(b"\xef\xbb\xbf"), "BOM para Excel"
    filas = list(csv.reader(contenido.decode("utf-8-sig").splitlines(), delimiter=";"))
    assert [f[0] for f in filas] == ["Expediente", "100", "1234"]


def test_29_periodo_invalido_no_exporta(v, servicios, mesa, monkeypatch):
    p = v.informes
    v.ir_a(p)
    p.desde.setDate(QDate(2030, 1, 1))
    p.hasta.setDate(QDate(2029, 1, 1))
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: pytest.fail("no debe preguntar"))
    )
    p._pdf()
    assert "Periodo no válido" in mesa.errores


# ====================================================== 7. Datos y copias
def test_30_copias_de_seguridad(v, servicios, mesa, tmp_path, monkeypatch):
    crear(servicios, 1)
    v.ir_a(v.datos)
    v.datos._copia_ahora()
    copias_hechas = copias.listar_copias(config.backups_dir())
    assert len(copias_hechas) == 1 and "Copia creada" in mesa.informaciones
    assert "Última copia" in v.datos.lbl_ultima.text()
    with Servicios.crear(copias_hechas[0]).db.conn as c:  # la copia es una base válida con los datos
        assert c.execute("SELECT COUNT(*) FROM beneficiarios").fetchone()[0] == 1

    usb = tmp_path / "usb"
    usb.mkdir()
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: str(usb)))
    v.datos._copia_en()
    assert len(list(usb.glob("sonrisas_*.db"))) == 1

    v.datos._abrir_copias()
    assert Path(mesa.urls_abiertas[-1].toLocalFile()) == config.backups_dir()


def test_31_copia_automatica_diaria_y_rotacion(servicios, tmp_path):
    carpeta = tmp_path / "copias"
    assert copias.copia_automatica(servicios.db, carpeta, cada_horas=24, conservar=3) is not None
    assert copias.copia_automatica(servicios.db, carpeta, cada_horas=24, conservar=3) is None, "una al día"
    for i in range(5):  # copias antiguas
        viejo = carpeta / f"sonrisas_2020-01-0{i + 1}_100000.db"
        viejo.write_bytes(b"x")
        os.utime(viejo, (0, 0))
    os.utime(copias.listar_copias(carpeta)[0], (0, 0))
    copias.copia_automatica(servicios.db, carpeta, cada_horas=24, conservar=3)
    assert len(copias.listar_copias(carpeta)) == 3


def test_32_importar_desde_la_pagina_de_datos(v, servicios, mesa, tmp_path, monkeypatch):
    import sqlite3

    antigua = tmp_path / "ong_usuarios.db"
    with sqlite3.connect(antigua) as c:
        c.executescript(ESQUEMA_V1)
        c.execute("INSERT INTO usuarios VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                  (dni(1), "Ana", "Díaz", "612345678", "2", "1", "0", "Taco", "77",
                   "2030-01-01", "2026-05-01 10:00:00", "04 0A 0B 0C"))  # fmt: skip
        c.executemany(
            "INSERT INTO visitas VALUES (?, ?)",
            [(dni(1), "2026-05-01 10:00:00"), (dni(1), "2026-05-01 10:00:01")],
        )
    v.ir_a(v.datos)
    assert v.datos.b_importar.isEnabled()
    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (str(antigua), "")))
    v.datos._importar()
    assert "Importación completada" in mesa.informaciones
    assert not v.datos.b_importar.isEnabled(), "no se puede importar dos veces"
    assert len(copias.listar_copias(config.backups_dir())) == 1, "copia de seguridad antes de importar"

    v.ir_a(v.beneficiarios)
    assert v.beneficiarios.proxy.rowCount() == 1, "las listas se refrescan tras importar"
    pasar_tarjeta(v, "04 0A 0B 0C")
    assert mesa.ficha.b.expediente == "77" and mesa.ficha.b.total_visitas == 2  # 1 importada + hoy


def test_33_importar_archivo_que_no_es_del_programa_anterior(v, mesa, tmp_path, monkeypatch):
    falso = tmp_path / "otra.db"
    falso.write_bytes(b"no soy una base de datos")
    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (str(falso), "")))
    v.ir_a(v.datos)
    v.datos._importar()
    assert "Archivo no válido" in mesa.errores


# ============================================ 8. Persistencia y base de datos
def test_34_los_datos_persisten_al_cerrar_y_abrir(tmp_path):
    ruta = tmp_path / "persistencia.db"
    s = Servicios.crear(ruta)
    b = crear(s, 1, uid="04 00 00 01", visita=True)
    s.db.close()
    s2 = Servicios.crear(ruta)
    assert s2.beneficiarios.obtener(b.id).total_visitas == 1
    assert s2.db.version == 1
    s2.db.migrar()  # volver a migrar no rompe nada
    s2.db.close()
    db = abrir(ruta)
    assert db.conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert db.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    db.close()


# ================================================================ 9. Lector NFC
class _LectorSimulado:
    """Secuencia de lecturas: (hay_lector, uid_en_el_lector)."""

    def __init__(self, lector: LectorNFC, pasos: list[tuple[bool, str | None]]):
        self.lector, self.pasos, self.i = lector, pasos, 0

    def primer_lector(self):
        return "Lector simulado" if self.pasos[self.i][0] else None

    def leer(self, _lector):
        return self.pasos[self.i][1]

    def dormir(self, _ms):
        self.i += 1
        if self.i >= len(self.pasos):
            self.lector._activo = False


def test_35_lector_un_evento_por_cada_vez_que_se_acerca_la_tarjeta(app, monkeypatch):
    lector = LectorNFC()
    pasos = [
        (True, None),
        (True, "04 AA"), (True, "04 AA"), (True, "04 AA"),  # apoyada: un solo evento
        (True, None), (True, "04 AA"),  # una lectura fallida aislada no cuenta como retirada
        (True, None), (True, None),  # retirada
        (True, "04 AA"),  # se vuelve a acercar
        (False, None), (False, None),  # se desconecta el lector
        (True, "04 BB"),  # se reconecta y se pasa otra tarjeta
    ]  # fmt: skip
    sim = _LectorSimulado(lector, pasos)
    monkeypatch.setattr(modulo_lector, "PCSC_DISPONIBLE", True)
    monkeypatch.setattr(LectorNFC, "_primer_lector", staticmethod(sim.primer_lector))
    monkeypatch.setattr(LectorNFC, "_leer_uid", staticmethod(sim.leer))
    monkeypatch.setattr(lector, "msleep", sim.dormir)
    detectadas, retiradas, estados = [], [], []
    lector.tarjeta_detectada.connect(detectadas.append)
    lector.tarjeta_retirada.connect(lambda: retiradas.append(1))
    lector.estado_cambiado.connect(lambda e, _n: estados.append(e))
    lector.run()
    assert detectadas == ["04 AA", "04 AA", "04 BB"]
    assert len(retiradas) == 2
    assert estados == [EstadoLector.LISTO, EstadoLector.SIN_LECTOR, EstadoLector.LISTO]


def test_36_sin_pyscard_funciona_en_modo_manual(app, monkeypatch):
    monkeypatch.setattr(modulo_lector, "PCSC_DISPONIBLE", False)
    lector = LectorNFC()
    estados = []
    lector.estado_cambiado.connect(lambda e, _n: estados.append(e))
    lector.run()
    assert estados == [EstadoLector.NO_DISPONIBLE]


def test_37_flujo_completo_de_un_dia_de_reparto(v, servicios, mesa):
    """Escenario realista: altas, atenciones, una pérdida de tarjeta y el informe del día."""
    for n in range(1, 21):
        crear(
            servicios, n, uid=f"04 00 00 {n:02X}", vencimiento=HOY + timedelta(days=-5 if n % 7 == 0 else 120)
        )
    pasar_tarjeta(v, "04 99 99 99")  # persona nueva
    f = v.alta.form
    for c, t in (
        ("nombre", "Nueva"),
        ("apellidos", "Persona"),
        ("documento", dni(99)),
        ("telefono", "600000099"),
    ):
        escribir(getattr(f, c), t)
    v.alta.b_guardar.click()
    for n in range(1, 21):
        pasar_tarjeta(v, f"04 00 00 {n:02X}")
        titulo, botones = banner(mesa.ficha)
        if titulo.startswith("Expediente vencido"):
            botones["Renovar 12 meses"].click()
    perdida = servicios.beneficiarios.obtener_por_documento(dni(5))
    v.abrir_ficha(perdida.id)
    mesa.uid_nueva_tarjeta = "04 55 55 55"
    mesa.ficha.b_tarjeta.click()
    pasar_tarjeta(v, "04 55 55 55")

    resumen = servicios.informes.resumen()
    assert resumen.atenciones_hoy == 21 and resumen.vencidos == 0
    inf = servicios.informes.generar(HOY, HOY)
    assert (inf.atenciones, inf.personas_unicas) == (21, 21)
    assert inf.altas_nuevas == 21  # los 20 del escenario también se dan de alta hoy
    assert servicios.db.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert mesa.errores == []


def test_38_la_carpeta_de_datos_de_las_pruebas_no_es_la_real():
    assert "SonrisasCanarias" not in str(config.data_dir()) or str(config.data_dir()).startswith(
        str(Path(os.environ["SONRISAS_DATA_DIR"]))
    )
