"""Copias de seguridad, importación del programa anterior y ayuda."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QTextBrowser, QVBoxLayout, QWidget

from sonrisas_nfc import __version__
from sonrisas_nfc.config import COPIAS_A_CONSERVAR, backups_dir, data_dir
from sonrisas_nfc.services import copias, importador
from sonrisas_nfc.services.contexto import Servicios
from sonrisas_nfc.ui.componentes import (
    CabeceraPagina,
    Tarjeta,
    avisar_error,
    boton,
    confirmar,
    etiqueta,
    informar,
)
from sonrisas_nfc.ui.tema import AZUL_OSCURO, TINTA, TINTA_SUAVE


class PaginaDatos(QWidget):
    datos_importados = Signal()

    def __init__(self, servicios: Servicios, parent=None) -> None:
        super().__init__(parent)
        self.s = servicios
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(36, 30, 36, 30)
        raiz.setSpacing(18)
        raiz.addWidget(CabeceraPagina("Seguridad", "Datos y copias de seguridad"))

        fila = QHBoxLayout()
        fila.setSpacing(20)

        t_copias = Tarjeta(margen=24)
        t_copias.capa.addWidget(etiqueta("Copias de seguridad", "seccion"))
        t_copias.capa.addWidget(
            etiqueta(
                f"Se hace una copia automática al abrir el programa (una al día) y se conservan las "
                f"{COPIAS_A_CONSERVAR} más recientes. Para mayor seguridad, guarde de vez en cuando una copia "
                "en un USB o disco externo.",
                "ayuda", ajustar=True,
            )
        )  # fmt: skip
        self.lbl_ultima = etiqueta("", None)
        t_copias.capa.addWidget(self.lbl_ultima)
        botones = QHBoxLayout()
        botones.addWidget(boton("Crear copia ahora", "primario", "guardar", self._copia_ahora))
        botones.addWidget(boton("Guardar copia en…", None, "descargar", self._copia_en))
        botones.addWidget(boton("Abrir carpeta", "plano", "carpeta", self._abrir_copias))
        botones.addStretch()
        t_copias.capa.addLayout(botones)
        t_copias.capa.addStretch()
        fila.addWidget(t_copias, 1)

        t_import = Tarjeta(margen=24)
        t_import.capa.addWidget(etiqueta("Importar del programa anterior", "seccion"))
        t_import.capa.addWidget(
            etiqueta(
                "Importa beneficiarios, tarjetas y todo el historial desde el archivo ong_usuarios.db "
                "de la versión anterior. El archivo original no se modifica. Solo puede hacerse con la "
                "base de datos vacía.",
                "ayuda", ajustar=True,
            )
        )  # fmt: skip
        self.b_importar = boton("Importar ong_usuarios.db…", None, "importar", self._importar)
        t_import.capa.addWidget(self.b_importar, 0, Qt.AlignmentFlag.AlignLeft)
        t_import.capa.addStretch()
        fila.addWidget(t_import, 1)
        raiz.addLayout(fila)

        t_ubic = Tarjeta(margen=24, espacio=6)
        t_ubic.capa.addWidget(etiqueta("Ubicación de los datos", "seccion"))
        ruta = etiqueta(str(data_dir()), None)
        ruta.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        t_ubic.capa.addWidget(ruta)
        t_ubic.capa.addWidget(
            etiqueta(
                "Los datos se guardan en el perfil de Windows y no en la carpeta del programa: "
                "reinstalar o actualizar no los borra.",
                "ayuda", ajustar=True,
            )
        )  # fmt: skip
        raiz.addWidget(t_ubic)
        raiz.addStretch()

    def refrescar(self) -> None:
        ultima = copias.ultima_copia(backups_dir())
        self.lbl_ultima.setText(
            f"Última copia: <b>{ultima:%d/%m/%Y a las %H:%M}</b>" if ultima else "Todavía no hay copias."
        )
        vacia = not self.s.db.conn.execute("SELECT 1 FROM beneficiarios LIMIT 1").fetchone()
        self.b_importar.setEnabled(vacia)
        self.b_importar.setToolTip("" if vacia else "Ya hay datos: la importación solo se permite en vacío.")

    def _copia_ahora(self) -> None:
        ruta = copias.crear_copia(self.s.db, backups_dir())
        self.refrescar()
        informar(self, "Copia creada", "La copia de seguridad se ha creado correctamente.", str(ruta))

    def _copia_en(self) -> None:
        carpeta = QFileDialog.getExistingDirectory(self, "Elija dónde guardar la copia (p. ej. un USB)")
        if carpeta:
            try:
                ruta = copias.crear_copia(self.s.db, Path(carpeta))
            except Exception as e:  # disco extraído, sin permisos...
                avisar_error(self, "No se pudo crear la copia", str(e))
                return
            informar(self, "Copia creada", "Copia guardada en:", str(ruta))

    def _abrir_copias(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(backups_dir())))

    def _importar(self) -> None:
        ruta, _ = QFileDialog.getOpenFileName(
            self, "Seleccione la base de datos del programa anterior", "", "Base de datos (*.db)"
        )
        if ruta:
            importar_con_dialogo(self, self.s, Path(ruta))
            self.datos_importados.emit()
            self.refrescar()


def importar_con_dialogo(padre, servicios: Servicios, ruta: Path, confirmar_antes: bool = True) -> bool:
    if not importador.es_bd_antigua(ruta):
        avisar_error(padre, "Archivo no válido", "El archivo no es una base de datos del programa anterior.")
        return False
    if confirmar_antes and not confirmar(
        padre, "Importar datos", f"¿Importar los datos de {ruta.name}?", si="Importar",
        detalle="Se hará antes una copia de seguridad de la base de datos actual.",
    ):  # fmt: skip
        return False
    copias.crear_copia(servicios.db, backups_dir())
    try:
        r = importador.importar(ruta, servicios.db)
    except importador.ErrorImportacion as e:
        avisar_error(padre, "No se pudo importar", str(e))
        return False
    detalle = (
        f"Beneficiarios: {r.beneficiarios}\nTarjetas: {r.tarjetas}\nVisitas: {r.visitas} "
        f"({r.visitas_duplicadas} repetidas el mismo día; se conservan pero no cuentan en los informes)"
    )
    if r.documentos_a_revisar:
        detalle += (
            f"\n\n{r.documentos_a_revisar} documentos tienen la letra de control incorrecta o incompleta."
        )
    caja_avisos = "\n".join(r.avisos[:40]) + ("\n…" if len(r.avisos) > 40 else "")
    informar(padre, "Importación completada", "Los datos se han importado correctamente.",
             detalle + (f"\n\nRevisar:\n{caja_avisos}" if r.avisos else ""))  # fmt: skip
    return True


AYUDA_HTML = f"""
<style>
 h2 {{ font-family: 'Fredoka'; color: {AZUL_OSCURO}; font-size: 19px; margin: 18px 0 6px 0; }}
 p, li {{ font-size: 15px; color: {TINTA}; line-height: 150%; }}
 .nota {{ color: {TINTA_SUAVE}; }}
</style>
<h2>Atender a una persona</h2>
<ul>
 <li><b>Pase su tarjeta por el lector</b> en cualquier pantalla. Se registra la atención de hoy y se abre su ficha.</li>
 <li>Solo se cuenta <b>una atención por persona y día</b>: si vuelve a pasar la tarjeta, se avisa y no se duplica.</li>
 <li>Si ha olvidado la tarjeta, búsquela en <b>Inicio</b> o en <b>Beneficiarios</b> y pulse <b>Atender ahora</b>.</li>
 <li>Si su expediente está <b>vencido</b>, la ficha lo indica en rojo: puede renovarlo (6 o 12 meses) o atender igualmente.</li>
</ul>
<h2>Dar de alta</h2>
<ul>
 <li>Pase una <b>tarjeta nueva</b> por el lector: se abre el alta con la tarjeta ya vinculada.</li>
 <li>DNI y NIE se comprueban con su letra de control. Los pasaportes se aceptan con letras y números.</li>
</ul>
<h2>Tarjeta perdida, robada o rota</h2>
<ul>
 <li>Abra la ficha de la persona y pulse <b>Cambiar tarjeta</b>. Indique el motivo y pase la tarjeta nueva.</li>
 <li>Conserva su expediente y <b>todo su historial</b>. La tarjeta antigua queda anulada: si aparece y se pasa por el
 lector, el programa avisará de que no es válida.</li>
</ul>
<h2>Informes</h2>
<ul>
 <li>En <b>Informes</b>, elija el periodo (o use los botones rápidos) y exporte a <b>PDF</b> o a <b>Excel (CSV)</b>.</li>
</ul>
<h2>Si el lector no responde</h2>
<ul>
 <li>Compruebe el indicador de la barra lateral: debe aparecer en verde <i>Lector listo</i>.</li>
 <li>Desconecte y vuelva a conectar el lector: el programa lo detecta solo, sin reiniciar.</li>
 <li>Si sigue sin funcionar, reinstale el controlador del ACR122U.</li>
</ul>
<p class="nota">Sonrisas NFC v{__version__} · Los datos personales se guardan únicamente en este equipo.</p>
"""


class PaginaAyuda(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(36, 30, 36, 30)
        raiz.setSpacing(16)
        raiz.addWidget(CabeceraPagina("Guía rápida", "Ayuda"))
        t = Tarjeta(margen=26)
        texto = QTextBrowser()
        texto.setFrameShape(QTextBrowser.Shape.NoFrame)
        texto.setHtml(AYUDA_HTML)
        texto.setStyleSheet("background: transparent; border: none;")
        t.capa.addWidget(texto)
        raiz.addWidget(t, 1)
