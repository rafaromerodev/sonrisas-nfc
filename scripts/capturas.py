"""Genera las capturas de pantalla de ``docs/capturas`` con datos ficticios.

Uso:  python scripts/capturas.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

os.environ["SONRISAS_DATA_DIR"] = tempfile.mkdtemp(prefix="sonrisas_capturas_")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from sonrisas_nfc import config
from sonrisas_nfc.demo import poblar
from sonrisas_nfc.services.atencion import Resultado
from sonrisas_nfc.services.contexto import Servicios
from sonrisas_nfc.ui import tema
from sonrisas_nfc.ui.dialogos import CambiarTarjetaDialog, FichaDialog
from sonrisas_nfc.ui.informe_pdf import generar_pdf
from sonrisas_nfc.ui.ventana import VentanaPrincipal

SALIDA = Path(__file__).resolve().parents[1] / "docs" / "capturas"
TAM = (1440, 900)


def guardar(widget, nombre: str) -> None:
    QApplication.processEvents()
    widget.grab().save(str(SALIDA / f"{nombre}.png"))
    print("✓", nombre)


def main() -> None:
    SALIDA.mkdir(parents=True, exist_ok=True)
    app = QApplication(sys.argv[:1])
    tema.aplicar(app)
    s = Servicios.crear(config.db_path())
    poblar(s)

    v = VentanaPrincipal(s)
    v.resize(*TAM)
    v.show()
    for pagina, nombre in (
        (v.inicio, "01_inicio"),
        (v.beneficiarios, "02_beneficiarios"),
        (v.alta, "03_alta"),
        (v.informes, "05_informes"),
        (v.datos, "07_datos"),
    ):
        v.ir_a(pagina)
        if pagina is v.alta:
            v.alta.establecer_uid("04 7F 3A 9C")
        if pagina is v.informes:
            v.informes._preset("anio")
        guardar(v, nombre)

    # Ficha tras pasar una tarjeta con expediente vencido
    vencido = next(
        b
        for b in s.beneficiarios.listar()
        if b.tarjeta_uid and b.vencimiento < date.today() and not s.visitas.visita_de_hoy(b.id)
    )
    r = s.atencion.procesar_tarjeta(vencido.tarjeta_uid)
    assert r.resultado is Resultado.EXPEDIENTE_VENCIDO
    ficha = FichaDialog(s, vencido.id, r, v)
    ficha.resize(1100, 800)
    ficha.show()
    guardar(ficha, "04_ficha_vencido")
    ficha.done(0)

    # Ficha con atención registrada
    vigente = next(
        b
        for b in s.beneficiarios.listar()
        if b.tarjeta_uid and b.vencimiento > date.today() + timedelta(days=60)
        and not s.visitas.visita_de_hoy(b.id)
    )  # fmt: skip
    r = s.atencion.procesar_tarjeta(vigente.tarjeta_uid)
    ficha = FichaDialog(s, vigente.id, r, v)
    ficha.resize(1100, 800)
    ficha.show()
    guardar(ficha, "04b_ficha_atendido")

    # Cambio de tarjeta por pérdida
    dlg = CambiarTarjetaDialog(s, s.beneficiarios.obtener(vigente.id), ficha)
    dlg.show()
    dlg.recibir_uid("04 C2 19 E7")
    dlg.adjustSize()
    guardar(dlg, "06_cambiar_tarjeta")

    inf = s.informes.generar(date(date.today().year, 1, 1), date.today())
    generar_pdf(inf, SALIDA.parent / "ejemplo_informe.pdf")
    print("✓ ejemplo_informe.pdf")


if __name__ == "__main__":
    main()
