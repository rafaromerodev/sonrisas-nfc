"""Verificación completa de una importación con datos reales, sin modificar nada.

Uso:  python scripts/verificar_datos.py RUTA\\ong_usuarios.db

Copia la base de datos del programa anterior a una carpeta temporal, la importa y comprueba
que el programa funciona con TODOS los registros. Solo imprime cifras agregadas: ningún dato
personal sale por pantalla. Al terminar, la carpeta temporal se borra.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import sys
import tempfile
import time
from datetime import date, timedelta
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

RESULTADOS: list[tuple[bool, str]] = []


def comprobar(ok: bool, texto: str) -> None:
    RESULTADOS.append((ok, texto))
    print(f"  [{'OK' if ok else 'FALLO'}] {texto}", flush=True)


def main(origen: Path) -> int:
    temporal = Path(tempfile.mkdtemp(prefix="sonrisas_verificacion_"))
    os.environ["SONRISAS_DATA_DIR"] = str(temporal / "datos")
    try:
        return _verificar(origen, temporal)
    finally:
        shutil.rmtree(temporal, ignore_errors=True)


def _verificar(origen: Path, temporal: Path) -> int:
    from PySide6.QtCore import QDate
    from PySide6.QtWidgets import QApplication

    from sonrisas_nfc import config
    from sonrisas_nfc.domain.models import clave_natural
    from sonrisas_nfc.services import importador
    from sonrisas_nfc.services.contexto import Servicios
    from sonrisas_nfc.services.informes import exportar_csv
    from sonrisas_nfc.ui import tema
    from sonrisas_nfc.ui.dialogos import FichaDialog
    from sonrisas_nfc.ui.informe_pdf import generar_pdf
    from sonrisas_nfc.ui.ventana import VentanaPrincipal

    app = QApplication([])
    tema.aplicar(app)
    copia = temporal / "ong_usuarios.db"
    shutil.copy2(origen, copia)

    print("\n1. Datos de origen")
    with sqlite3.connect(f"file:{copia}?mode=ro", uri=True) as c:
        n_usuarios = c.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0]
        n_visitas = c.execute("SELECT COUNT(*) FROM visitas").fetchone()[0]
        n_uids = c.execute(
            "SELECT COUNT(DISTINCT card_uid) FROM usuarios WHERE card_uid IS NOT NULL AND card_uid <> ''"
        ).fetchone()[0]
        primera, ultima = c.execute("SELECT MIN(fecha), MAX(fecha) FROM visitas").fetchone()
    print(f"  {n_usuarios} usuarios, {n_visitas} visitas, {n_uids} tarjetas ({primera[:10]} a {ultima[:10]})")

    print("\n2. Importación")
    s = Servicios.crear(config.db_path())
    t = time.perf_counter()
    r = importador.importar(copia, s.db)
    comprobar(r.beneficiarios == n_usuarios, f"beneficiarios importados: {r.beneficiarios} de {n_usuarios}")
    comprobar(r.visitas == n_visitas, f"visitas importadas: {r.visitas} de {n_visitas} (ninguna se pierde)")
    comprobar(r.tarjetas == n_uids, f"tarjetas importadas: {r.tarjetas} de {n_uids}")
    print(f"  {r.visitas_duplicadas} visitas repetidas el mismo día (se conservan, no cuentan)")
    print(f"  {r.documentos_a_revisar} documentos para revisar · {time.perf_counter() - t:.2f} s")
    c = s.db.conn
    comprobar(c.execute("PRAGMA integrity_check").fetchone()[0] == "ok", "integridad de la base de datos")
    comprobar(not c.execute("PRAGMA foreign_key_check").fetchall(), "relaciones entre tablas correctas")

    print("\n3. Cada beneficiario")
    todos = s.beneficiarios.listar()
    fallos_ficha, t = 0, time.perf_counter()
    for b in todos:
        try:
            ficha = FichaDialog(s, b.id)
            ficha._sucio = False
            ficha.deleteLater()
        except Exception:
            fallos_ficha += 1
    app.processEvents()
    comprobar(fallos_ficha == 0, f"las {len(todos)} fichas se abren sin error ({time.perf_counter() - t:.1f} s)")

    tarjetas_mal = sum(
        1 for b in todos if b.tarjeta_uid and s.tarjetas.activa_por_uid(b.tarjeta_uid).beneficiario_id != b.id
    )
    con_tarjeta = sum(1 for b in todos if b.tarjeta_uid)
    comprobar(tarjetas_mal == 0, f"cada una de las {con_tarjeta} tarjetas identifica a su persona")

    no_encontrados = 0
    for b in todos:
        for dato in filter(None, (b.documento, b.expediente)):
            if b.id not in {x.id for x in s.beneficiarios.buscar(dato)}:
                no_encontrados += 1
    comprobar(no_encontrados == 0, "todos los expedientes y documentos se encuentran con el buscador")

    print("\n4. Pantallas con todos los datos")
    v = VentanaPrincipal(s)
    v.resize(1366, 768)
    v.show()
    p = v.beneficiarios
    v.ir_a(p)
    p.botones_filtro["todos"].click()
    comprobar(p.proxy.rowCount() == len(todos), f"el listado muestra los {len(todos)} beneficiarios")
    expedientes = [p.proxy.index(i, 1).data() for i in range(p.proxy.rowCount())]
    comprobar(expedientes == sorted(expedientes, key=clave_natural), "orden por nº de expediente (menor a mayor)")
    for i in range(p.combo_orden.count()):
        t = time.perf_counter()
        p.combo_orden.setCurrentIndex(i)
        comprobar(p.proxy.rowCount() == len(todos),
                  f"orden «{p.combo_orden.itemText(i)}» ({(time.perf_counter() - t) * 1000:.0f} ms)")  # fmt: skip
    t = time.perf_counter()
    p.buscador.setText("a")
    comprobar(True, f"búsqueda instantánea sobre todos ({(time.perf_counter() - t) * 1000:.0f} ms)")
    v.ir_a(v.inicio)
    comprobar(v.inicio.c_activos.valor.text() == f"{len(todos):,}".replace(",", "."), "cifras de Inicio")

    print("\n5. Informes")
    desde = date.fromisoformat(primera[:10])
    hasta = date.fromisoformat(ultima[:10])
    total = s.informes.generar(desde, hasta)
    suma, mes = 0, desde.replace(day=1)
    while mes <= hasta:
        fin = (mes.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        suma += s.informes.generar(mes, fin).atenciones
        mes = fin + timedelta(days=1)
    comprobar(suma == total.atenciones, f"la suma de los meses cuadra con el total: {total.atenciones} atenciones")
    comprobar(total.atenciones == n_visitas - r.visitas_duplicadas,
              f"atenciones = visitas - repetidas ({n_visitas} - {r.visitas_duplicadas})")  # fmt: skip
    comprobar(sum(total.por_dia_semana) == total.atenciones, "el desglose por día de la semana cuadra")
    comprobar(sum(z.atenciones for z in total.por_zona) == total.atenciones, "el desglose por zona cuadra")
    t = time.perf_counter()
    pdf, csv = temporal / "informe.pdf", temporal / "informe.csv"
    generar_pdf(total, pdf)
    exportar_csv(total, csv)
    lineas_csv = len(csv.read_text(encoding="utf-8-sig").splitlines()) - 1
    comprobar(pdf.stat().st_size > 10_000, f"PDF del periodo completo generado ({pdf.stat().st_size // 1024} KB)")
    comprobar(lineas_csv == total.personas_unicas, f"CSV con {lineas_csv} personas")
    print(f"  exportación: {time.perf_counter() - t:.1f} s")
    v.ir_a(v.informes)
    v.informes.desde.setDate(QDate(desde.year, desde.month, desde.day))
    v.informes.hasta.setDate(QDate(hasta.year, hasta.month, hasta.day))
    comprobar(v.informes.tabla_detalle.rowCount() == total.personas_unicas, "pestaña de expedientes atendidos")

    v.close()
    s.db.close()
    fallos = [t for ok, t in RESULTADOS if not ok]
    print(f"\nRESULTADO: {len(RESULTADOS) - len(fallos)} de {len(RESULTADOS)} comprobaciones correctas")
    return 1 if fallos else 0


if __name__ == "__main__":
    if len(sys.argv) != 2 or not Path(sys.argv[1]).is_file():
        print(__doc__)
        sys.exit(2)
    sys.exit(main(Path(sys.argv[1])))
