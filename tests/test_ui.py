"""Pruebas de humo de la interfaz (sin pantalla: plataforma offscreen)."""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QApplication

from sonrisas_nfc.services.atencion import Resultado
from sonrisas_nfc.ui import tema
from sonrisas_nfc.ui.dialogos import CambiarTarjetaDialog, FichaDialog
from sonrisas_nfc.ui.grafica import imagen_grafica
from sonrisas_nfc.ui.informe_pdf import generar_pdf
from sonrisas_nfc.ui.ventana import VentanaPrincipal


@pytest.fixture(scope="module")
def app():
    a = QApplication.instance() or QApplication([])
    tema.aplicar(a)
    return a


@pytest.fixture
def ventana(app, servicios, monkeypatch):
    abiertas = []
    # Evita los diálogos modales bloqueantes: registramos qué ficha se abriría.
    monkeypatch.setattr(VentanaPrincipal, "abrir_ficha", lambda self, bid, r=None: abiertas.append((bid, r)))
    v = VentanaPrincipal(servicios)
    v.fichas_abiertas = abiertas
    yield v
    v.close()


def test_tarjeta_nueva_lleva_al_alta(ventana):
    ventana.al_detectar_tarjeta("04 AA BB CC")
    assert ventana.pila.currentWidget() is ventana.alta
    assert ventana.alta.uid == "04 AA BB CC"


def test_tarjeta_conocida_registra_y_abre_ficha(ventana, servicios, datos):
    b = servicios.beneficiarios.crear(datos, tarjeta_uid="04 AA BB CC", registrar_visita=False)
    servicios.beneficiarios.renovar(b.id, 6)
    ventana.al_detectar_tarjeta("04aabbcc")
    (bid, r), *_ = ventana.fichas_abiertas
    assert bid == b.id
    assert r.resultado is Resultado.VISITA_REGISTRADA


def test_beneficiarios_ordenados_por_expediente_por_defecto(ventana, servicios, datos):
    from dataclasses import replace

    for exp, doc, tel, apellidos in (
        ("100", "12345678Z", "611111111", "Zamora"),
        ("45", "X1234567L", "622222222", "Benítez"),
        ("1234", "Y1234567X", "633333333", "Álvarez"),
    ):
        servicios.beneficiarios.crear(
            replace(datos, expediente=exp, documento=doc, telefono=tel, apellidos=apellidos)
        )
    pagina = ventana.beneficiarios
    ventana.ir_a(pagina)

    def columna(col):
        return [pagina.proxy.index(i, col).data() for i in range(pagina.proxy.rowCount())]

    assert pagina.combo_orden.currentIndex() == 0
    assert columna(1) == ["45", "100", "1234"]
    pagina.combo_orden.setCurrentIndex(2)  # Apellidos (A-Z), sin distinguir tildes
    assert columna(1) == ["1234", "45", "100"]
    pagina.combo_orden.setCurrentIndex(1)  # mayor a menor
    assert columna(1) == ["1234", "100", "45"]


def test_doble_clic_abre_una_sola_ficha(ventana, servicios, datos):
    """Regresión: doubleClicked y activated se emitían a la vez y abrían dos fichas."""
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    b = servicios.beneficiarios.crear(datos)
    pagina = ventana.beneficiarios
    ventana.ir_a(pagina)
    ventana.show()
    celda = pagina.tabla.visualRect(pagina.proxy.index(0, 3)).center()
    # Secuencia de un ratón real: pulsar/soltar y, enseguida, el doble clic.
    QTest.mouseClick(pagina.tabla.viewport(), Qt.MouseButton.LeftButton, pos=celda)
    QTest.mouseDClick(pagina.tabla.viewport(), Qt.MouseButton.LeftButton, pos=celda)
    assert [bid for bid, _ in ventana.fichas_abiertas] == [b.id]


def test_nunca_dos_fichas_a_la_vez(app, servicios, datos, monkeypatch):
    """Protección en la ventana: si ya hay una ficha visible, no se abre otra encima."""
    from sonrisas_nfc.ui import ventana as modulo

    b = servicios.beneficiarios.crear(datos)
    v = VentanaPrincipal(servicios)
    creadas = []

    class FichaFalsa:
        def __init__(self, *args):
            self.visible = False
            creadas.append(self)

        def isVisible(self):
            return self.visible

        def exec(self):
            self.visible = True
            v.abrir_ficha(b.id)  # segunda petición mientras la primera está abierta
            self.visible = False

        def raise_(self):
            pass

        def activateWindow(self):
            pass

    monkeypatch.setattr(modulo, "FichaDialog", FichaFalsa)
    v.abrir_ficha(b.id)
    assert len(creadas) == 1
    v.abrir_ficha(b.id)  # cerrada la primera, se puede abrir otra
    assert len(creadas) == 2
    v.close()


def test_intro_en_la_tabla_abre_la_ficha(ventana, servicios, datos):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    b = servicios.beneficiarios.crear(datos)
    pagina = ventana.beneficiarios
    ventana.ir_a(pagina)
    ventana.show()
    pagina.tabla.setFocus()
    pagina.tabla.setCurrentIndex(pagina.proxy.index(0, 3))
    QTest.keyClick(pagina.tabla, Qt.Key.Key_Return)
    assert [bid for bid, _ in ventana.fichas_abiertas] == [b.id]


def test_ficha_y_cambio_de_tarjeta(app, servicios, datos):
    b = servicios.beneficiarios.crear(datos, tarjeta_uid="04 AA BB CC")
    ficha = FichaDialog(servicios, b.id)
    assert ficha.lbl_nombre.text() == "Ana Pérez García"
    dlg = CambiarTarjetaDialog(servicios, servicios.beneficiarios.obtener(b.id), ficha)
    dlg.recibir_uid("04 AA BB CC")  # su propia tarjeta: no se permite
    assert not dlg.b_ok.isEnabled()
    dlg.recibir_uid("04 11 22 33")
    assert dlg.b_ok.isEnabled()
    dlg._confirmar()
    assert servicios.beneficiarios.obtener(b.id).tarjeta_uid == "04 11 22 33"


def test_pdf_e_imagen(app, servicios, datos, tmp_path):
    from datetime import date

    servicios.beneficiarios.crear(datos)
    assert not imagen_grafica([0, 1, 2, 3, 4, 5, 6], QSize(200, 100)).isNull()
    destino = tmp_path / "informe.pdf"
    generar_pdf(servicios.informes.generar(date.today(), date.today()), destino)
    assert destino.read_bytes().startswith(b"%PDF")
