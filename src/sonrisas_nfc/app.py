"""Punto de entrada de la aplicación.

Uso::

    sonrisas-nfc                 # arranque normal
    sonrisas-nfc --demo          # datos ficticios en una carpeta temporal (demostraciones)
    sonrisas-nfc --importar RUTA # importa la base de datos del programa anterior y arranca
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import tempfile
import traceback
from logging.handlers import RotatingFileHandler
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from sonrisas_nfc import __version__, config
from sonrisas_nfc.services import copias, importador
from sonrisas_nfc.services.contexto import Servicios

log = logging.getLogger("sonrisas_nfc")


def _configurar_log() -> None:
    manejador = RotatingFileHandler(config.logs_dir() / "sonrisas.log", maxBytes=1_000_000, backupCount=3,
                                    encoding="utf-8")  # fmt: skip
    manejador.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    raiz = logging.getLogger()
    raiz.setLevel(logging.INFO)
    raiz.addHandler(manejador)


def _instalar_manejador_errores() -> None:
    """Cualquier error inesperado se registra y se muestra con un mensaje comprensible."""

    def manejar(tipo, valor, tb) -> None:
        log.critical("Error no controlado", exc_info=(tipo, valor, tb))
        from sonrisas_nfc.ui.componentes import avisar_error

        if QApplication.instance():
            avisar_error(
                None, "Se ha producido un error",
                "La operación no se ha completado. Los datos guardados no se han visto afectados.",
                f"Si se repite, envíe al soporte el archivo:\n{config.logs_dir() / 'sonrisas.log'}\n\n"
                + "".join(traceback.format_exception_only(tipo, valor)).strip(),
            )  # fmt: skip

    sys.excepthook = manejar


_NOMBRE_BD_ANTIGUA = "ong_usuarios.db"
#: Carpetas que no merece la pena recorrer al buscar la base de datos antigua.
_CARPETAS_OMITIDAS = {
    "windows",
    "appdata",
    "$recycle.bin",
    "programdata",
    "node_modules",
    ".git",
    "_internal",
}


def _buscar_bd_antigua() -> Path | None:
    """Busca el ``ong_usuarios.db`` del programa anterior en las ubicaciones habituales.

    Si hay varios (copias, pruebas...), devuelve el modificado más recientemente, que es el
    que el programa antiguo estaba usando.
    """
    casa = Path.home()
    raices: list[tuple[Path, int]] = [(Path.cwd(), 2), (Path(sys.executable).parent, 2)]
    raices += [(casa / c, 6) for c in ("Desktop", "Escritorio", "OneDrive/Desktop", "OneDrive/Escritorio",
                                       "Documents", "Documentos", "Downloads", "Descargas")]  # fmt: skip
    for pf in filter(None, (os.environ.get("PROGRAMFILES"), os.environ.get("PROGRAMFILES(X86)"))):
        raices.append((Path(pf) / "ONG Sonrisas Canarias", 3))
    raices.append((Path(os.environ.get("SYSTEMDRIVE", "C:") + "\\"), 4))

    encontrados: set[Path] = set()
    for raiz, profundidad in raices:
        if not raiz.is_dir():
            continue
        nivel_base = len(raiz.parts)
        for carpeta, subcarpetas, archivos in os.walk(raiz):
            actual = Path(carpeta)
            if len(actual.parts) - nivel_base >= profundidad:
                subcarpetas.clear()
            subcarpetas[:] = [
                s for s in subcarpetas
                if s.lower() not in _CARPETAS_OMITIDAS and not (actual == raiz.anchor and s.lower() == "users")
            ]  # fmt: skip
            if _NOMBRE_BD_ANTIGUA in archivos:
                encontrados.add(actual / _NOMBRE_BD_ANTIGUA)
    validos = [r for r in encontrados if importador.es_bd_antigua(r)]
    return max(validos, key=lambda r: r.stat().st_mtime, default=None)


def _describir_bd_antigua(ruta: Path) -> str:
    import sqlite3
    from datetime import datetime

    try:
        with sqlite3.connect(f"file:{ruta}?mode=ro", uri=True) as c:
            usuarios = c.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0]
            ultima = c.execute("SELECT MAX(fecha) FROM visitas").fetchone()[0] or "—"
    except sqlite3.Error:
        usuarios, ultima = "?", "?"
    modificado = datetime.fromtimestamp(ruta.stat().st_mtime)
    return (
        f"{ruta}\n\nUsuarios: {usuarios}\nÚltima visita registrada: {ultima}\n"
        f"Archivo modificado el {modificado:%d/%m/%Y a las %H:%M}"
    )


def _ofrecer_importacion(servicios: Servicios, ruta_indicada: Path | None) -> None:
    """Primer arranque con la base vacía: ofrecer traer los datos del programa anterior."""
    from PySide6.QtWidgets import QFileDialog, QMessageBox

    from sonrisas_nfc.ui.paginas.datos import importar_con_dialogo

    if ruta_indicada:
        importar_con_dialogo(None, servicios, ruta_indicada)
        return
    encontrada = _buscar_bd_antigua()
    caja = QMessageBox(QMessageBox.Icon.Question, "Datos del programa anterior", "")
    if encontrada:
        caja.setText("Se han encontrado los datos del programa anterior. ¿Desea importarlos ahora?")
        caja.setInformativeText(_describir_bd_antigua(encontrada))
        b_importar = caja.addButton("Importar", QMessageBox.ButtonRole.AcceptRole)
        b_importar.setProperty("variante", "primario")
    else:
        caja.setText("¿Desea importar los datos del programa anterior?")
        caja.setInformativeText(
            "No se ha encontrado automáticamente el archivo ong_usuarios.db. Puede seleccionarlo a mano.\n"
            "También puede hacerlo más tarde en «Datos y copias»."
        )
        b_importar = None
    b_elegir = caja.addButton("Elegir archivo…", QMessageBox.ButtonRole.ActionRole)
    caja.addButton("Empezar sin datos", QMessageBox.ButtonRole.RejectRole)
    caja.exec()

    if b_importar is not None and caja.clickedButton() is b_importar:
        importar_con_dialogo(None, servicios, encontrada, confirmar_antes=False)  # type: ignore[arg-type]
    elif caja.clickedButton() is b_elegir:
        ruta, _ = QFileDialog.getOpenFileName(
            None, "Seleccione ong_usuarios.db del programa anterior", str(Path.home()), "Base de datos (*.db)"
        )
        if ruta:
            importar_con_dialogo(None, servicios, Path(ruta))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sonrisas-nfc", description=config.APP_NAME)
    parser.add_argument("--demo", action="store_true", help="usar datos ficticios en una carpeta temporal")
    parser.add_argument("--importar", type=Path, help="importar ong_usuarios.db del programa anterior")
    parser.add_argument("--sin-lector", action="store_true", help="no iniciar la lectura NFC")
    parser.add_argument("--version", action="version", version=__version__)
    args = parser.parse_args(argv)

    if args.demo:
        os.environ["SONRISAS_DATA_DIR"] = tempfile.mkdtemp(prefix="sonrisas_demo_")

    _configurar_log()
    log.info("Inicio de %s %s (datos en %s)", config.APP_NAME, __version__, config.data_dir())

    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv[:1])
    app.setApplicationName(config.APP_NAME)
    app.setOrganizationName(config.ORG_NAME)
    app.setApplicationVersion(__version__)
    app.setWindowIcon(QIcon(str(config.ASSETS_DIR / "sonrisas.ico")))

    from sonrisas_nfc.nfc.lector import LectorNFC
    from sonrisas_nfc.ui import tema
    from sonrisas_nfc.ui.ventana import VentanaPrincipal

    tema.aplicar(app)
    _instalar_manejador_errores()

    servicios = Servicios.crear(config.db_path())
    if args.demo:
        from sonrisas_nfc.demo import poblar

        poblar(servicios)
    else:
        try:
            copias.copia_automatica(servicios.db, config.backups_dir(), config.HORAS_ENTRE_COPIAS,
                                    config.COPIAS_A_CONSERVAR)  # fmt: skip
        except Exception:
            log.exception("No se pudo crear la copia de seguridad automática")

    vacia = not servicios.db.conn.execute("SELECT 1 FROM beneficiarios LIMIT 1").fetchone()
    if vacia and not args.demo:
        _ofrecer_importacion(servicios, args.importar)

    lector = None if args.sin_lector else LectorNFC()
    ventana = VentanaPrincipal(servicios, lector)
    ventana.showMaximized()
    if lector:
        lector.start()
    codigo = app.exec()
    servicios.db.close()
    log.info("Cierre de la aplicación")
    return codigo


if __name__ == "__main__":
    sys.exit(main())
