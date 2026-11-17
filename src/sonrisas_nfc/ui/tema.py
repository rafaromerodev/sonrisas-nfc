"""Identidad visual, alineada con la web de la ONG (ongsonrisascanarias.es).

Azul cielo y amarillo sol del logo, contornos en tinta oscura, sombras "duras" desplazadas
(simuladas con un borde inferior más grueso), botones en píldora y tipografías redondeadas
Fredoka (títulos) y Nunito (texto).
"""

from __future__ import annotations

import logging

from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication

from sonrisas_nfc.config import ASSETS_DIR
from sonrisas_nfc.domain.models import EstadoExpediente

log = logging.getLogger(__name__)

# Paleta (mismos valores que la hoja de estilos de la web)
TINTA = "#24313a"
TINTA_SUAVE = "#5b6871"
AZUL = "#159bd7"
AZUL_OSCURO = "#0d638e"
AZUL_SUAVE = "#edf7fb"
AMARILLO = "#ffcc00"
AMARILLO_OSCURO = "#e7b900"
PAPEL = "#ffffff"
PAPEL_2 = "#f6f8fa"
PAPEL_3 = "#eef3f6"
LINEA = "#d5dce1"
# Colores de estado (no existen en la web; elegidos con contraste AA sobre blanco)
VERDE = "#1f8a4c"
VERDE_SUAVE = "#e2f5e9"
AMBAR = "#8a6400"
AMBAR_SUAVE = "#fff4c2"
ROJO = "#c23b3b"
ROJO_SUAVE = "#fde7e7"

_ICONOS = (ASSETS_DIR / "iconos").as_posix()

FUENTE_TITULOS = "Fredoka"
FUENTE_TEXTO = "Nunito"

COLORES_ESTADO: dict[EstadoExpediente, tuple[str, str]] = {
    EstadoExpediente.VIGENTE: (VERDE, VERDE_SUAVE),
    EstadoExpediente.POR_VENCER: (AMBAR, AMBAR_SUAVE),
    EstadoExpediente.VENCIDO: (ROJO, ROJO_SUAVE),
    EstadoExpediente.SIN_FECHA: (TINTA_SUAVE, PAPEL_3),
    EstadoExpediente.BAJA: (TINTA_SUAVE, PAPEL_3),
}


def cargar_fuentes() -> None:
    for archivo in (ASSETS_DIR / "fonts").glob("*.ttf"):
        if QFontDatabase.addApplicationFont(str(archivo)) < 0:
            log.warning("No se pudo cargar la fuente %s", archivo.name)


def aplicar(app: QApplication) -> None:
    cargar_fuentes()
    app.setStyle("Fusion")
    fuente = QFont(FUENTE_TEXTO)
    fuente.setPixelSize(15)
    fuente.setWeight(QFont.Weight.Medium)
    app.setFont(fuente)

    paleta = app.palette()
    paleta.setColor(QPalette.ColorRole.Window, QColor(PAPEL_2))
    paleta.setColor(QPalette.ColorRole.WindowText, QColor(TINTA))
    paleta.setColor(QPalette.ColorRole.Base, QColor(PAPEL))
    paleta.setColor(QPalette.ColorRole.AlternateBase, QColor(PAPEL_2))
    paleta.setColor(QPalette.ColorRole.Text, QColor(TINTA))
    paleta.setColor(QPalette.ColorRole.Button, QColor(PAPEL))
    paleta.setColor(QPalette.ColorRole.ButtonText, QColor(TINTA))
    paleta.setColor(QPalette.ColorRole.Highlight, QColor(AZUL))
    paleta.setColor(QPalette.ColorRole.HighlightedText, QColor(PAPEL))
    paleta.setColor(QPalette.ColorRole.PlaceholderText, QColor("#8b979f"))
    paleta.setColor(QPalette.ColorRole.ToolTipBase, QColor(TINTA))
    paleta.setColor(QPalette.ColorRole.ToolTipText, QColor(PAPEL))
    app.setPalette(paleta)
    app.setStyleSheet(QSS)


QSS = f"""
* {{ outline: none; }}
QMainWindow, QDialog {{ background: {PAPEL_2}; }}
QToolTip {{ background: {TINTA}; color: {PAPEL}; border: none; padding: 6px 10px; border-radius: 8px; }}

/* ---------- Tipografía ---------- */
QLabel {{ color: {TINTA}; background: transparent; }}
QLabel[rol="titulo"] {{ font-family: "{FUENTE_TITULOS}"; font-size: 30px; font-weight: 600; }}
QLabel[rol="subtitulo"] {{ color: {TINTA_SUAVE}; font-size: 15px; }}
QLabel[rol="seccion"] {{ font-family: "{FUENTE_TITULOS}"; font-size: 19px; font-weight: 600; }}
QLabel[rol="kicker"] {{ font-family: "{FUENTE_TITULOS}"; font-size: 12px; font-weight: 700;
    color: {AZUL_OSCURO}; letter-spacing: 1.5px; }}
QLabel[rol="etiqueta"] {{ color: {TINTA_SUAVE}; font-size: 13px; font-weight: 700; }}
QLabel[rol="ayuda"] {{ color: {TINTA_SUAVE}; font-size: 13px; }}
QLabel[rol="error"] {{ color: {ROJO}; font-size: 13px; font-weight: 700; }}
QLabel[rol="cifra"] {{ font-family: "{FUENTE_TITULOS}"; font-size: 34px; font-weight: 700; }}
QLabel[rol="uid"] {{ font-family: "{FUENTE_TITULOS}"; font-size: 22px; font-weight: 600; letter-spacing: 3px; }}

/* ---------- Tarjetas (fondo, borde y sombra se pintan en componentes.Tarjeta) ---------- */
QFrame[card] {{ background: transparent; border: none; }}
QFrame[card="azul"] QLabel {{ color: {PAPEL}; }}
QFrame[banner="ok"] {{ background: {VERDE_SUAVE}; border: 2px solid {VERDE}; border-radius: 16px; }}
QFrame[banner="aviso"] {{ background: {AMBAR_SUAVE}; border: 2px solid {AMARILLO_OSCURO}; border-radius: 16px; }}
QFrame[banner="error"] {{ background: {ROJO_SUAVE}; border: 2px solid {ROJO}; border-radius: 16px; }}
QFrame[banner="info"] {{ background: {AZUL_SUAVE}; border: 2px solid {AZUL}; border-radius: 16px; }}
QFrame[separador="true"] {{ background: {LINEA}; border: none; max-height: 2px; min-height: 2px; }}

/* ---------- Barra lateral ---------- */
QFrame#barraLateral {{ background: {PAPEL}; border: none; border-right: 2px solid {TINTA}; }}
QPushButton[nav="true"] {{ text-align: left; padding: 11px 16px; border: 2px solid transparent;
    border-radius: 16px; background: transparent; color: {TINTA_SUAVE};
    font-family: "{FUENTE_TITULOS}"; font-size: 16px; font-weight: 500; }}
QPushButton[nav="true"]:hover {{ background: {PAPEL_2}; color: {TINTA}; }}
QPushButton[nav="true"]:checked {{ background: {AMARILLO}; color: {TINTA}; border: 2px solid {TINTA};
    border-bottom-width: 4px; font-weight: 600; }}
QLabel#estadoLector {{ border: 2px solid {TINTA}; border-radius: 14px; padding: 8px 12px;
    font-size: 13px; font-weight: 700; background: {PAPEL_2}; }}
QLabel#estadoLector[estado="ok"] {{ background: {VERDE_SUAVE}; }}
QLabel#estadoLector[estado="error"] {{ background: {ROJO_SUAVE}; }}

/* ---------- Botones ---------- */
QPushButton {{ font-family: "{FUENTE_TITULOS}"; font-size: 15px; font-weight: 600; color: {TINTA};
    background: {PAPEL}; border: 2px solid {TINTA}; border-bottom-width: 5px; border-radius: 21px;
    padding: 7px 20px; min-height: 24px; }}
QPushButton:hover {{ background: {PAPEL_2}; }}
QPushButton:pressed {{ border-bottom-width: 2px; padding-top: 10px; }}
QPushButton:disabled {{ color: #9aa5ad; border-color: #b9c2c8; background: {PAPEL_2}; }}
QPushButton[variante="primario"] {{ background: {AZUL}; color: {PAPEL}; }}
QPushButton[variante="primario"]:hover {{ background: {AZUL_OSCURO}; }}
QPushButton[variante="amarillo"] {{ background: {AMARILLO}; }}
QPushButton[variante="amarillo"]:hover {{ background: {AMARILLO_OSCURO}; }}
QPushButton[variante="peligro"] {{ color: {ROJO}; }}
QPushButton[variante="peligro"]:hover {{ background: {ROJO_SUAVE}; }}
QPushButton[variante="plano"] {{ border: 2px solid transparent; background: transparent; color: {AZUL_OSCURO}; }}
QPushButton[variante="plano"]:hover {{ background: {AZUL_SUAVE}; }}
QPushButton[variante="filtro"] {{ font-size: 13px; padding: 4px 14px; border-bottom-width: 2px;
    border-radius: 15px; min-height: 20px; color: {TINTA_SUAVE}; }}
QPushButton[variante="filtro"]:checked {{ background: {TINTA}; color: {PAPEL}; }}
QPushButton::menu-indicator {{ image: none; width: 0; }}

/* ---------- Campos ---------- */
QLineEdit, QSpinBox, QDateEdit, QComboBox, QPlainTextEdit {{ background: {PAPEL}; color: {TINTA};
    border: 2px solid {LINEA}; border-radius: 12px; padding: 7px 12px; min-height: 22px;
    selection-background-color: {AZUL}; font-size: 15px; }}
QLineEdit:hover, QSpinBox:hover, QDateEdit:hover, QComboBox:hover, QPlainTextEdit:hover {{ border-color: #b3bec6; }}
QLineEdit:focus, QSpinBox:focus, QDateEdit:focus, QComboBox:focus, QPlainTextEdit:focus {{ border-color: {AZUL}; }}
QLineEdit[error="true"], QSpinBox[error="true"], QDateEdit[error="true"] {{ border-color: {ROJO};
    background: {ROJO_SUAVE}; }}
QLineEdit:read-only {{ background: {PAPEL_2}; color: {TINTA_SUAVE}; }}
QLineEdit[rol="buscador"] {{ border: 2px solid {TINTA}; border-radius: 22px; padding: 9px 16px 9px 40px;
    font-size: 16px; }}
QSpinBox {{ padding-right: 30px; }}
QSpinBox::up-button, QSpinBox::down-button {{ width: 26px; border: none; background: transparent;
    subcontrol-origin: border; }}
QSpinBox::up-button {{ subcontrol-position: top right; margin: 3px 4px 0 0; }}
QSpinBox::down-button {{ subcontrol-position: bottom right; margin: 0 4px 3px 0; }}
QSpinBox::up-button:hover, QSpinBox::down-button:hover {{ background: {PAPEL_3}; border-radius: 6px; }}
QSpinBox::up-arrow {{ image: url({_ICONOS}/flecha_arriba.svg); width: 11px; height: 11px; }}
QSpinBox::down-arrow {{ image: url({_ICONOS}/flecha_abajo.svg); width: 11px; height: 11px; }}
QDateEdit::drop-down, QComboBox::drop-down {{ width: 34px; border: none; subcontrol-position: center right; }}
QDateEdit::down-arrow, QComboBox::down-arrow {{ image: url({_ICONOS}/flecha_abajo.svg); width: 14px; height: 14px; }}
QComboBox QAbstractItemView {{ border: 2px solid {TINTA}; border-radius: 10px; background: {PAPEL};
    selection-background-color: {AZUL_SUAVE}; selection-color: {TINTA}; padding: 4px; }}
QCheckBox {{ spacing: 10px; color: {TINTA}; }}
QCheckBox::indicator {{ width: 20px; height: 20px; border: 2px solid {TINTA}; border-radius: 6px; background: {PAPEL}; }}
QCheckBox::indicator:checked {{ background: {AZUL}; image: url({_ICONOS}/check_blanco.svg); }}

/* ---------- Calendario ----------
   QCalendarWidget usa internamente una QTableView: estas reglas (más específicas) anulan el
   estilo general de tablas, cuyo padding de celda dejaba días sin dibujar. */
QCalendarWidget {{ min-width: 330px; min-height: 290px; }}
QCalendarWidget QWidget#qt_calendar_navigationbar {{ background: {AZUL}; min-height: 40px; }}
QCalendarWidget QToolButton {{ color: {PAPEL}; font-family: "{FUENTE_TITULOS}"; font-size: 15px;
    font-weight: 600; background: transparent; border: none; border-radius: 8px; padding: 4px 10px; }}
QCalendarWidget QToolButton:hover {{ background: {AZUL_OSCURO}; }}
QCalendarWidget QToolButton::menu-indicator {{ image: none; width: 0; }}
QCalendarWidget QToolButton#qt_calendar_prevmonth {{ qproperty-icon: url({_ICONOS}/mes_anterior.svg); }}
QCalendarWidget QToolButton#qt_calendar_nextmonth {{ qproperty-icon: url({_ICONOS}/mes_siguiente.svg); }}
QCalendarWidget QTableView::item:selected {{ background: {AMARILLO}; color: {TINTA}; border-radius: 8px; }}
QCalendarWidget QSpinBox {{ color: {TINTA}; min-height: 20px; padding: 2px 26px 2px 6px; }}
QCalendarWidget QTableView {{ background: {PAPEL}; border: 2px solid {TINTA}; border-top: none;
    border-radius: 0; alternate-background-color: {PAPEL}; font-size: 14px; outline: none; }}
QCalendarWidget QTableView::item {{ padding: 0; border: none; }}
QCalendarWidget QAbstractItemView:enabled {{ color: {TINTA}; selection-background-color: {AMARILLO};
    selection-color: {TINTA}; }}
QCalendarWidget QAbstractItemView:disabled {{ color: #b3bec6; }}

/* ---------- Tablas ---------- */
QTableView {{ background: {PAPEL}; border: 2px solid {TINTA}; border-radius: 16px;
    gridline-color: transparent; alternate-background-color: {PAPEL_2};
    selection-background-color: {AZUL_SUAVE}; selection-color: {TINTA}; font-size: 14px; }}
QTableView::item {{ padding: 4px 10px; border-bottom: 1px solid {PAPEL_3}; }}
QTableView::item:selected {{ background: {AZUL_SUAVE}; color: {TINTA}; }}
QHeaderView {{ background: transparent; }}
QHeaderView::section {{ background: {PAPEL_3}; color: {TINTA}; font-family: "{FUENTE_TITULOS}";
    font-weight: 600; font-size: 14px; border: none; border-bottom: 2px solid {TINTA}; padding: 10px; }}
QHeaderView::section:first {{ border-top-left-radius: 14px; }}
QHeaderView::section:last {{ border-top-right-radius: 14px; }}
QTableCornerButton::section {{ background: {PAPEL_3}; border: none; }}

/* ---------- Pestañas ---------- */
QTabWidget::pane {{ border: none; }}
QTabBar::tab {{ font-family: "{FUENTE_TITULOS}"; font-size: 15px; font-weight: 600; color: {TINTA_SUAVE};
    padding: 8px 18px; margin-right: 6px; border: 2px solid transparent; border-radius: 16px; }}
QTabBar::tab:selected {{ color: {TINTA}; background: {PAPEL}; border: 2px solid {TINTA}; }}
QTabBar::tab:hover:!selected {{ background: {PAPEL_3}; }}

/* ---------- Scroll ---------- */
QScrollArea {{ border: none; background: transparent; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 12px; margin: 4px; }}
QScrollBar::handle:vertical {{ background: #c3ccd2; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {TINTA_SUAVE}; }}
QScrollBar:horizontal {{ background: transparent; height: 12px; margin: 4px; }}
QScrollBar::handle:horizontal {{ background: #c3ccd2; border-radius: 4px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

/* ---------- Menús y mensajes ---------- */
QMenu {{ background: {PAPEL}; border: 2px solid {TINTA}; border-radius: 12px; padding: 6px; }}
QMenu::item {{ padding: 8px 18px; border-radius: 8px; }}
QMenu::item:selected {{ background: {AZUL_SUAVE}; color: {TINTA}; }}
QMessageBox {{ background: {PAPEL}; }}
QMessageBox QLabel {{ font-size: 15px; }}

QLabel#toast {{ background: {TINTA}; color: {PAPEL}; border-radius: 18px; padding: 12px 22px;
    font-family: "{FUENTE_TITULOS}"; font-size: 15px; font-weight: 600; }}
"""
