"""Informes por periodo: cifras, gráfica por día de la semana, desglose por zona y exportación."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

from PySide6.QtCore import QDate, QStandardPaths, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDateEdit,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from sonrisas_nfc.services.contexto import Servicios
from sonrisas_nfc.services.informes import (
    Apariciones,
    FilaDetalle,
    Informe,
    OrdenDetalle,
    exportar_csv,
    filtrar_detalle,
)
from sonrisas_nfc.ui.componentes import (
    Buscador,
    CabeceraPagina,
    Cifra,
    Tarjeta,
    avisar_error,
    boton,
    etiqueta,
)
from sonrisas_nfc.ui.grafica import GraficaDias
from sonrisas_nfc.ui.informe_pdf import generar_pdf
from sonrisas_nfc.ui.tema import AZUL_OSCURO, TINTA

_COLUMNAS_DETALLE = ["Expediente", "Documento", "Nombre y apellidos", "Zona", "Atenciones", "Última atención"]


class PaginaInformes(QWidget):
    abrir_beneficiario = Signal(int)

    def __init__(self, servicios: Servicios, parent=None) -> None:
        super().__init__(parent)
        self.s = servicios
        self.informe: Informe | None = None

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(36, 30, 36, 30)
        raiz.setSpacing(16)

        cab = QHBoxLayout()
        cab.addWidget(CabeceraPagina("Memoria y justificación", "Informes"), 1)
        cab.addWidget(
            boton("Exportar Excel (CSV)", None, "descargar", self._csv), 0, Qt.AlignmentFlag.AlignBottom
        )
        cab.addWidget(
            boton("Exportar PDF", "primario", "descargar", self._pdf), 0, Qt.AlignmentFlag.AlignBottom
        )
        raiz.addLayout(cab)

        periodo = QHBoxLayout()
        periodo.setSpacing(10)
        self.desde, self.hasta = QDateEdit(), QDateEdit()
        for d in (self.desde, self.hasta):
            d.setCalendarPopup(True)
            d.setDisplayFormat("dd/MM/yyyy")
            d.dateChanged.connect(self.refrescar)
        periodo.addWidget(etiqueta("Desde", "etiqueta"))
        periodo.addWidget(self.desde)
        periodo.addWidget(etiqueta("Hasta", "etiqueta"))
        periodo.addWidget(self.hasta)
        periodo.addSpacing(12)
        for texto, clave in (("Este mes", "mes"), ("Mes anterior", "anterior"), ("Trimestre", "trimestre"),
                             ("Este año", "anio"), ("Año anterior", "anio_anterior")):  # fmt: skip
            periodo.addWidget(boton(texto, "filtro", None, lambda c=clave: self._preset(c)))
        periodo.addStretch()
        raiz.addLayout(periodo)

        cifras = QHBoxLayout()
        cifras.setSpacing(16)
        self.c_atenciones = Cifra("Atenciones (1 por persona y día)", AZUL_OSCURO, "suave")
        self.c_personas = Cifra("Personas atendidas", TINTA)
        self.c_hogar = Cifra("Miembros de sus hogares", TINTA)
        self.c_altas = Cifra("Altas nuevas", TINTA)
        for c in (self.c_atenciones, self.c_personas, self.c_hogar, self.c_altas):
            cifras.addWidget(c)
        raiz.addLayout(cifras)

        self.pestanas = QTabWidget()
        resumen = QWidget()
        abajo = QGridLayout(resumen)
        abajo.setContentsMargins(0, 10, 0, 0)
        abajo.setSpacing(20)
        t_grafica = Tarjeta(margen=22)
        t_grafica.capa.addWidget(etiqueta("Atenciones por día de la semana", "seccion"))
        self.grafica = GraficaDias()
        t_grafica.capa.addWidget(self.grafica, 1)
        self.lbl_hogar = etiqueta("", "ayuda", ajustar=True)
        t_grafica.capa.addWidget(self.lbl_hogar)
        abajo.addWidget(t_grafica, 0, 0)

        t_zonas = Tarjeta(margen=22)
        t_zonas.capa.addWidget(etiqueta("Por municipio / localidad", "seccion"))
        self.tabla_zonas = QTableWidget(0, 3)
        self.tabla_zonas.setHorizontalHeaderLabels(["Zona", "Personas", "Atenciones"])
        self.tabla_zonas.verticalHeader().hide()
        self.tabla_zonas.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla_zonas.setShowGrid(False)
        self.tabla_zonas.setAlternatingRowColors(True)
        self.tabla_zonas.verticalHeader().setDefaultSectionSize(34)
        self.tabla_zonas.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.tabla_zonas.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        t_zonas.capa.addWidget(self.tabla_zonas, 1)
        abajo.addWidget(t_zonas, 0, 1)
        abajo.setColumnStretch(0, 1)
        abajo.setColumnStretch(1, 1)
        self.pestanas.addTab(resumen, "Resumen")
        self.pestanas.addTab(self._crear_pestana_expedientes(), "Expedientes atendidos")
        raiz.addWidget(self.pestanas, 1)

        self.visibles: list[FilaDetalle] = []
        self._preset("mes", refrescar=False)

    # ------------------------------------------------------- expedientes
    def _crear_pestana_expedientes(self) -> QWidget:
        caja = QWidget()
        capa = QVBoxLayout(caja)
        capa.setContentsMargins(0, 10, 0, 0)
        capa.setSpacing(12)

        filtros = QHBoxLayout()
        filtros.setSpacing(10)
        self.buscador = Buscador("Expediente, DNI/NIE o nombre + Intro")
        self.buscador.returnPressed.connect(self._aplicar_filtros)
        # Al vaciar el buscador (botón ✕ o borrando) se vuelve a mostrar todo.
        self.buscador.textChanged.connect(lambda t: None if t.strip() else self._aplicar_filtros())
        filtros.addWidget(self.buscador, 1)
        filtros.addWidget(boton("Buscar", "amarillo", "buscar", self._aplicar_filtros))
        filtros.addSpacing(8)
        filtros.addWidget(etiqueta("Apariciones", "etiqueta"))
        self.combo_apariciones = QComboBox()
        for a in Apariciones:
            self.combo_apariciones.addItem(a.etiqueta, a)
        self.combo_apariciones.currentIndexChanged.connect(self._aplicar_filtros)
        filtros.addWidget(self.combo_apariciones)
        filtros.addWidget(etiqueta("Orden", "etiqueta"))
        self.combo_orden = QComboBox()
        for o in OrdenDetalle:
            self.combo_orden.addItem(o.value, o)
        self.combo_orden.currentIndexChanged.connect(self._aplicar_filtros)
        filtros.addWidget(self.combo_orden)
        capa.addLayout(filtros)

        self.tabla_detalle = QTableWidget(0, len(_COLUMNAS_DETALLE))
        self.tabla_detalle.setHorizontalHeaderLabels(_COLUMNAS_DETALLE)
        self.tabla_detalle.verticalHeader().hide()
        self.tabla_detalle.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla_detalle.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabla_detalle.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tabla_detalle.setShowGrid(False)
        self.tabla_detalle.setAlternatingRowColors(True)
        self.tabla_detalle.setWordWrap(False)
        self.tabla_detalle.verticalHeader().setDefaultSectionSize(38)
        self.tabla_detalle.setCursor(Qt.CursorShape.PointingHandCursor)
        cabecera = self.tabla_detalle.horizontalHeader()
        for col, ancho in enumerate((140, 130, 0, 160, 120, 150)):
            if ancho:
                cabecera.resizeSection(col, ancho)
        cabecera.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        cabecera.setHighlightSections(False)
        self.tabla_detalle.cellDoubleClicked.connect(self._abrir_fila)
        capa.addWidget(self.tabla_detalle, 1)

        pie = QHBoxLayout()
        pie.addWidget(
            etiqueta(
                "Doble clic para abrir la ficha. Las exportaciones respetan el filtro y el orden.", "ayuda"
            )
        )
        pie.addStretch()
        self.lbl_detalle = etiqueta("", "ayuda")
        pie.addWidget(self.lbl_detalle)
        capa.addLayout(pie)
        return caja

    def _aplicar_filtros(self, *_args) -> None:
        if self.informe is None:
            return
        apariciones: Apariciones = self.combo_apariciones.currentData()
        orden: OrdenDetalle = self.combo_orden.currentData()
        self.visibles = filtrar_detalle(self.informe.detalle, self.buscador.text(), apariciones, orden)
        t = self.tabla_detalle
        t.setRowCount(len(self.visibles))
        derecha = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        for i, d in enumerate(self.visibles):
            valores = (
                d.expediente,
                d.documento,
                d.nombre_completo,
                d.zona,
                str(d.atenciones),
                f"{d.ultima:%d/%m/%Y}",
            )
            for j, valor in enumerate(valores):
                item = QTableWidgetItem(valor)
                if j == 4:
                    item.setTextAlignment(derecha)
                t.setItem(i, j, item)
        total = len(self.informe.detalle)
        self.lbl_detalle.setText(
            f"{len(self.visibles)} de {total} personas"
            if len(self.visibles) != total
            else f"{total} personas"
        )
        self.pestanas.setTabText(1, f"Expedientes atendidos ({total})")
        if len(self.visibles) == 1 and self.buscador.text().strip():
            t.selectRow(0)

    def _descripcion_filtro(self) -> str:
        partes = []
        if self.buscador.text().strip():
            partes.append(f"búsqueda «{self.buscador.text().strip()}»")
        apariciones: Apariciones = self.combo_apariciones.currentData()
        if apariciones is not Apariciones.TODAS:
            partes.append(f"apariciones: {apariciones.etiqueta.lower()}")
        if not partes:
            return ""
        return (
            f"Filtrado por {', '.join(partes)}: {len(self.visibles)} de {len(self.informe.detalle)} personas."  # type: ignore[union-attr]
        )

    def _informe_a_exportar(self) -> Informe:
        """El informe con la relación de expedientes tal como se ve (filtro y orden)."""
        return replace(self.informe, detalle=list(self.visibles), filtro_detalle=self._descripcion_filtro())  # type: ignore[type-var]

    def _abrir_fila(self, fila: int, _col: int) -> None:
        self.abrir_beneficiario.emit(self.visibles[fila].beneficiario_id)

    def _preset(self, clave: str, refrescar: bool = True) -> None:
        hoy = date.today()
        if clave == "mes":
            desde, hasta = hoy.replace(day=1), hoy
        elif clave == "anterior":
            hasta = hoy.replace(day=1) - timedelta(days=1)
            desde = hasta.replace(day=1)
        elif clave == "trimestre":
            mes = 3 * ((hoy.month - 1) // 3) + 1
            desde, hasta = date(hoy.year, mes, 1), hoy
        elif clave == "anio":
            desde, hasta = date(hoy.year, 1, 1), hoy
        else:
            desde, hasta = date(hoy.year - 1, 1, 1), date(hoy.year - 1, 12, 31)
        for w, d in ((self.desde, desde), (self.hasta, hasta)):
            w.blockSignals(True)
            w.setDate(QDate(d.year, d.month, d.day))
            w.blockSignals(False)
        if refrescar:
            self.refrescar()

    def refrescar(self) -> None:
        desde, hasta = self.desde.date().toPython(), self.hasta.date().toPython()
        if desde > hasta:
            self.informe = None
            return
        inf = self.informe = self.s.informes.generar(desde, hasta)
        self.c_atenciones.establecer(inf.atenciones)
        self.c_personas.establecer(inf.personas_unicas)
        self.c_hogar.establecer(inf.personas_atendidas_hogar)
        self.c_altas.establecer(inf.altas_nuevas)
        self.grafica.establecer(inf.por_dia_semana)
        self.lbl_hogar.setText(
            f"Hogares atendidos: {inf.adultos} adultos · {inf.menores} menores · {inf.mayores} mayores de 65."
        )
        self.tabla_zonas.setRowCount(len(inf.por_zona))
        for i, z in enumerate(inf.por_zona):
            for j, valor in enumerate((z.zona, str(z.personas), str(z.atenciones))):
                item = QTableWidgetItem(valor)
                if j:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.tabla_zonas.setItem(i, j, item)
        self._aplicar_filtros()

    def _ruta(self, extension: str, filtro: str) -> Path | None:
        if self.informe is None:
            avisar_error(self, "Periodo no válido", "La fecha inicial no puede ser posterior a la final.")
            return None
        carpeta = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)
        nombre = f"informe_atenciones_{self.informe.desde:%Y-%m-%d}_{self.informe.hasta:%Y-%m-%d}.{extension}"
        ruta, _ = QFileDialog.getSaveFileName(self, "Guardar informe", str(Path(carpeta) / nombre), filtro)
        if not ruta:
            return None
        ruta = Path(ruta)
        return ruta if ruta.suffix.lower() == f".{extension}" else ruta.with_suffix(f".{extension}")

    def _pdf(self) -> None:
        ruta = self._ruta("pdf", "PDF (*.pdf)")
        if ruta:
            try:
                generar_pdf(self._informe_a_exportar(), ruta)
            except OSError as e:
                avisar_error(self, "No se pudo guardar", f"No se pudo escribir el archivo: {e.strerror}")
                return
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(ruta)))

    def _csv(self) -> None:
        ruta = self._ruta("csv", "CSV para Excel (*.csv)")
        if ruta:
            try:
                exportar_csv(self._informe_a_exportar(), ruta)
            except OSError as e:
                avisar_error(self, "No se pudo guardar", f"No se pudo escribir el archivo: {e.strerror}")
                return
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(ruta.parent)))
