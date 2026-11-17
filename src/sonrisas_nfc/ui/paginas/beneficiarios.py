"""Listado de beneficiarios con búsqueda instantánea y filtros por estado."""

from __future__ import annotations

import unicodedata
from datetime import date

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QRectF,
    QSortFilterProxyModel,
    Qt,
    Signal,
)
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QStyledItemDelegate,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from sonrisas_nfc.domain.models import Beneficiario, EstadoExpediente, clave_natural
from sonrisas_nfc.services.contexto import Servicios
from sonrisas_nfc.ui.componentes import Buscador, CabeceraPagina, boton, etiqueta
from sonrisas_nfc.ui.tema import COLORES_ESTADO, FUENTE_TITULOS, TINTA_SUAVE

COLUMNAS = ["Estado", "Expediente", "Documento", "Nombre y apellidos", "Teléfono", "Zona", "Hogar",
            "Última visita", "Vence", "Tarjeta"]  # fmt: skip
COL_ESTADO = 0

FILTROS: dict[str, tuple[str, callable]] = {
    "activos": ("Activos", lambda b, e: b.activo),
    "vigentes": ("Vigentes", lambda b, e: e is EstadoExpediente.VIGENTE),
    "por_vencer": ("Por vencer", lambda b, e: e is EstadoExpediente.POR_VENCER),
    "vencidos": ("Vencidos", lambda b, e: e is EstadoExpediente.VENCIDO),
    "sin_tarjeta": ("Sin tarjeta", lambda b, e: b.activo and not b.tarjeta_uid),
    "bajas": ("De baja", lambda b, e: not b.activo),
    "todos": ("Todos", lambda b, e: True),
}


_ASC, _DESC = Qt.SortOrder.AscendingOrder, Qt.SortOrder.DescendingOrder
#: Opciones del selector "Ordenar por": (texto, columna, sentido, nombre ordenado por apellidos).
ORDENES: list[tuple[str, int, Qt.SortOrder, bool]] = [
    ("Nº de expediente (menor a mayor)", 1, _ASC, True),
    ("Nº de expediente (mayor a menor)", 1, _DESC, True),
    ("Apellidos (A-Z)", 3, _ASC, True),
    ("Nombre (A-Z)", 3, _ASC, False),
    ("Última visita (más reciente)", 7, _DESC, True),
    ("Última visita (más antigua)", 7, _ASC, True),
    ("Vencimiento (más próximo)", 8, _ASC, True),
]


def _sin_tildes(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto.lower()) if unicodedata.category(c) != "Mn")


class ModeloBeneficiarios(QAbstractTableModel):
    def __init__(self) -> None:
        super().__init__()
        self.filas: list[Beneficiario] = []
        self.orden_por_apellidos = True
        self._estados: list[EstadoExpediente] = []
        self._indice_busqueda: list[str] = []

    def cargar(self, beneficiarios: list[Beneficiario]) -> None:
        self.beginResetModel()
        hoy = date.today()
        self.filas = beneficiarios
        self._estados = [b.estado(hoy) for b in beneficiarios]
        self._indice_busqueda = [
            _sin_tildes(
                " ".join(
                    filter(
                        None,
                        (b.nombre_completo, b.documento, b.expediente, b.telefono, b.zona, b.tarjeta_uid),
                    )
                )
            )
            for b in beneficiarios
        ]
        self.endResetModel()

    def estado(self, fila: int) -> EstadoExpediente:
        return self._estados[fila]

    def texto_busqueda(self, fila: int) -> str:
        return self._indice_busqueda[fila]

    def rowCount(self, parent: QModelIndex | None = None) -> int:
        return 0 if parent is not None and parent.isValid() else len(self.filas)

    def columnCount(self, parent: QModelIndex | None = None) -> int:
        return len(COLUMNAS)

    def headerData(self, seccion, orientacion, rol=Qt.ItemDataRole.DisplayRole):
        if orientacion == Qt.Orientation.Horizontal and rol == Qt.ItemDataRole.DisplayRole:
            return COLUMNAS[seccion]
        return None

    def data(self, index: QModelIndex, rol=Qt.ItemDataRole.DisplayRole):
        b = self.filas[index.row()]
        col = index.column()
        if rol == Qt.ItemDataRole.DisplayRole:
            return self._texto(b, col, index.row())
        if rol == Qt.ItemDataRole.UserRole:  # valor para ordenar
            return self._orden(b, col, index.row())
        if rol == Qt.ItemDataRole.ForegroundRole and col in (7, 8, 9):
            if col == 8 and self._estados[index.row()] is EstadoExpediente.VENCIDO:
                return QColor(COLORES_ESTADO[EstadoExpediente.VENCIDO][0])
            if col == 9 and not b.tarjeta_uid:
                return QColor(TINTA_SUAVE)
        if rol == Qt.ItemDataRole.ToolTipRole and col == 9 and b.tarjeta_uid:
            return f"UID {b.tarjeta_uid}"
        if rol == Qt.ItemDataRole.ToolTipRole and col == 6:
            return f"{b.adultos or 0} adultos · {b.menores or 0} menores · {b.mayores or 0} mayores"
        return None

    def _texto(self, b: Beneficiario, col: int, fila: int) -> str:
        match col:
            case 0:
                return self._estados[fila].value
            case 1:
                return b.expediente or ""
            case 2:
                return b.documento
            case 3:
                return b.nombre_completo
            case 4:
                return b.telefono
            case 5:
                return b.zona or ""
            case 6:
                return str(b.miembros_hogar) if b.miembros_hogar else ""
            case 7:
                return f"{b.ultima_visita:%d/%m/%Y}" if b.ultima_visita else "—"
            case 8:
                return f"{b.vencimiento:%d/%m/%Y}" if b.vencimiento else "—"
            case 9:
                return "Sí" if b.tarjeta_uid else "No"
        return ""

    def _orden(self, b: Beneficiario, col: int, fila: int):
        if col == 0:
            return list(EstadoExpediente).index(self._estados[fila])
        if col == 6:
            return b.miembros_hogar
        if col == 7:
            return b.ultima_visita.isoformat() if b.ultima_visita else ""
        if col == 8:
            return b.vencimiento.isoformat() if b.vencimiento else ""
        if col in (1, 2):  # expediente y documento: orden numérico ("45" antes que "100")
            return clave_natural(self._texto(b, col, fila))
        if col == 3:
            orden = (b.apellidos, b.nombre) if self.orden_por_apellidos else (b.nombre, b.apellidos)
            return _sin_tildes(" ".join(orden))
        return _sin_tildes(self._texto(b, col, fila))


class FiltroBeneficiarios(QSortFilterProxyModel):
    def __init__(self) -> None:
        super().__init__()
        self.texto = ""
        self.filtro = "activos"
        self.setSortRole(Qt.ItemDataRole.UserRole)

    def establecer(self, texto: str | None = None, filtro: str | None = None) -> None:
        # Qt >= 6.9: begin/endFilterChange sustituye a invalidateFilter (obsoleto).
        moderno = hasattr(self, "beginFilterChange")
        if moderno:
            self.beginFilterChange()
        if texto is not None:
            self.texto = _sin_tildes(texto.strip())
        if filtro is not None:
            self.filtro = filtro
        if moderno:
            self.endFilterChange(QSortFilterProxyModel.Direction.Rows)
        else:
            self.invalidateFilter()

    def filterAcceptsRow(self, fila: int, _padre) -> bool:
        m: ModeloBeneficiarios = self.sourceModel()  # type: ignore[assignment]
        b = m.filas[fila]
        if not FILTROS[self.filtro][1](b, m.estado(fila)):
            return False
        return all(p in m.texto_busqueda(fila) for p in self.texto.split())


class DelegadoEstado(QStyledItemDelegate):
    """Pinta el estado como una píldora de color."""

    def paint(self, painter: QPainter, opcion, index) -> None:
        super().paint(painter, opcion, QModelIndex())  # fondo/selección sin texto
        modelo: FiltroBeneficiarios = index.model()  # type: ignore[assignment]
        fila = modelo.mapToSource(index).row()
        estado = modelo.sourceModel().estado(fila)  # type: ignore[attr-defined]
        color, fondo = COLORES_ESTADO[estado]
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        fuente = QFont(FUENTE_TITULOS)
        fuente.setPixelSize(12)
        fuente.setWeight(QFont.Weight.DemiBold)
        painter.setFont(fuente)
        ancho = painter.fontMetrics().horizontalAdvance(estado.value) + 22
        r = QRectF(opcion.rect.x() + 10, opcion.rect.center().y() - 11, ancho, 22)
        painter.setPen(QPen(QColor(color), 1.6))
        painter.setBrush(QColor(fondo))
        painter.drawRoundedRect(r, 11, 11)
        painter.drawText(r, Qt.AlignmentFlag.AlignCenter, estado.value)
        painter.restore()


class PaginaBeneficiarios(QWidget):
    abrir_beneficiario = Signal(int)
    nuevo = Signal()

    def __init__(self, servicios: Servicios, parent=None) -> None:
        super().__init__(parent)
        self.s = servicios
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(36, 30, 36, 30)
        raiz.setSpacing(16)

        cab = QHBoxLayout()
        cab.addWidget(CabeceraPagina("Gestión", "Beneficiarios"), 1)
        cab.addWidget(
            boton("Nuevo beneficiario", "primario", "mas", self.nuevo.emit), 0, Qt.AlignmentFlag.AlignBottom
        )
        raiz.addLayout(cab)

        self.buscador = Buscador(
            "Escriba el nº de expediente o DNI/NIE y pulse Intro (también nombre, teléfono, zona o UID)"
        )
        self.buscador.textChanged.connect(lambda t: self._aplicar(texto=t))
        self.buscador.returnPressed.connect(self._buscar_intro)
        raiz.addWidget(self.buscador)

        filtros = QHBoxLayout()
        filtros.setSpacing(8)
        self.grupo = QButtonGroup(self)
        self.grupo.setExclusive(True)
        self.botones_filtro = {}
        for clave, (texto, _) in FILTROS.items():
            b = boton(texto, "filtro")
            b.setCheckable(True)
            b.clicked.connect(lambda _=False, c=clave: self._aplicar(filtro=c))
            self.grupo.addButton(b)
            self.botones_filtro[clave] = b
            filtros.addWidget(b)
        filtros.addStretch()
        filtros.addWidget(etiqueta("Ordenar por", "etiqueta"))
        self.combo_orden = QComboBox()
        for texto, *_ in ORDENES:
            self.combo_orden.addItem(texto)
        self.combo_orden.setMinimumWidth(290)
        self.combo_orden.currentIndexChanged.connect(self._ordenar)
        filtros.addWidget(self.combo_orden)
        filtros.addSpacing(12)
        self.lbl_total = etiqueta("", "ayuda")
        filtros.addWidget(self.lbl_total)
        raiz.addLayout(filtros)

        self.modelo = ModeloBeneficiarios()
        self.proxy = FiltroBeneficiarios()
        self.proxy.setSourceModel(self.modelo)
        self.tabla = QTableView()
        self.tabla.setModel(self.proxy)
        self.tabla.setItemDelegateForColumn(COL_ESTADO, DelegadoEstado(self.tabla))
        self.tabla.setSortingEnabled(True)
        # Orden por defecto: nº de expediente de menor a mayor (primera opción de ORDENES).
        self.tabla.horizontalHeader().sortIndicatorChanged.connect(self._sincronizar_combo)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabla.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla.setAlternatingRowColors(True)
        self.tabla.setShowGrid(False)
        self.tabla.setWordWrap(False)
        self.tabla.verticalHeader().hide()
        self.tabla.verticalHeader().setDefaultSectionSize(42)
        self.tabla.setCursor(Qt.CursorShape.PointingHandCursor)
        cabecera = self.tabla.horizontalHeader()
        # Anchos fijos (rápido con cientos de filas); el nombre ocupa el espacio restante.
        for col, ancho in enumerate((124, 132, 112, 0, 0, 124, 72, 118, 106, 76)):
            if ancho:
                cabecera.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
                cabecera.resizeSection(col, ancho)
        cabecera.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        # El teléfono se ve en la ficha y se puede buscar; se oculta para dar espacio al nombre.
        self.tabla.setColumnHidden(4, True)
        cabecera.setHighlightSections(False)
        # Solo «activated»: ya se emite con el doble clic y con Intro. Conectar también
        # «doubleClicked» abría dos fichas con un mismo doble clic.
        self.tabla.activated.connect(self._abrir)
        raiz.addWidget(self.tabla, 1)
        raiz.addWidget(etiqueta("Doble clic o Intro sobre una fila para abrir la ficha.", "ayuda"))

        self.botones_filtro["activos"].setChecked(True)
        self._ordenar(0)

    def _ordenar(self, indice: int) -> None:
        _, columna, sentido, por_apellidos = ORDENES[indice]
        self.modelo.orden_por_apellidos = por_apellidos
        self.proxy.invalidate()  # la clave de la columna de nombre puede haber cambiado
        self.tabla.sortByColumn(columna, sentido)

    def _sincronizar_combo(self, columna: int, sentido: Qt.SortOrder) -> None:
        """Si se ordena pulsando una cabecera, el selector refleja la opción equivalente."""
        for i, (_, col, sen, por_apellidos) in enumerate(ORDENES):
            if (col, sen) == (columna, sentido) and (
                col != 3 or por_apellidos == self.modelo.orden_por_apellidos
            ):
                self.combo_orden.blockSignals(True)
                self.combo_orden.setCurrentIndex(i)
                self.combo_orden.blockSignals(False)
                return

    def refrescar(self) -> None:
        self.modelo.cargar(self.s.beneficiarios.listar())
        self._actualizar_total()

    def mostrar_filtro(self, filtro: str, texto: str = "") -> None:
        self.botones_filtro[filtro].setChecked(True)
        self.buscador.setText(texto)
        self._aplicar(texto=texto, filtro=filtro)

    def _buscar_intro(self) -> None:
        """Intro en el buscador: si el expediente o documento coincide exactamente, abre la ficha."""
        texto = self.buscador.text().strip().upper()
        if not texto:
            return
        exactas = [
            b for b in self.modelo.filas if texto in (b.documento.upper(), (b.expediente or "").upper())
        ]
        if len(exactas) == 1:
            self.abrir_beneficiario.emit(exactas[0].id)
            return
        if self.proxy.rowCount() == 0 and self.proxy.filtro != "todos":
            # Puede estar de baja o fuera del filtro actual: buscar en todos.
            self.mostrar_filtro("todos", self.buscador.text())
        if self.proxy.rowCount() == 1:
            self._abrir(self.proxy.index(0, 0))
        elif self.proxy.rowCount() > 1:
            self.tabla.setFocus()
            self.tabla.selectRow(0)

    def _aplicar(self, texto: str | None = None, filtro: str | None = None) -> None:
        self.proxy.establecer(texto, filtro)
        self._actualizar_total()

    def _actualizar_total(self) -> None:
        n = self.proxy.rowCount()
        self.lbl_total.setText(f"{n} {'resultado' if n == 1 else 'resultados'}")

    def _abrir(self, index: QModelIndex) -> None:
        fila = self.proxy.mapToSource(index).row()
        self.abrir_beneficiario.emit(self.modelo.filas[fila].id)
