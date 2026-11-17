"""Generación del informe en PDF (HTML maquetado con la identidad de la ONG)."""

from __future__ import annotations

from datetime import datetime
from html import escape
from pathlib import Path

from PySide6.QtCore import QMarginsF, QSize, QSizeF, QUrl
from PySide6.QtGui import QPageLayout, QPageSize, QPdfWriter, QTextDocument

from sonrisas_nfc.config import ASSETS_DIR, ORG_NAME
from sonrisas_nfc.services.informes import Informe
from sonrisas_nfc.ui.grafica import DIAS, imagen_grafica
from sonrisas_nfc.ui.tema import AZUL_OSCURO, AZUL_SUAVE, PAPEL_3, TINTA, TINTA_SUAVE

#: El documento se maqueta a 96 ppp (como en pantalla): el texto del PDF es vectorial igualmente,
#: y las imágenes se generan a mayor resolución.
_PPP = 96
_TAM_GRAFICA = QSize(330, 170)


def _n(valor: int) -> str:
    return f"{valor:,}".replace(",", ".")


def _html(inf: Informe) -> str:
    logo = (ASSETS_DIR / "logo.png").as_uri()
    cifras = [
        ("Atenciones", inf.atenciones),
        ("Personas atendidas", inf.personas_unicas),
        ("Miembros de hogares", inf.personas_atendidas_hogar),
        ("Altas nuevas", inf.altas_nuevas),
    ]
    celdas_cifras = "".join(
        f'<td width="25%" style="background:{AZUL_SUAVE}; padding:10px 12px;">'
        f'<div style="font-size:20pt; font-weight:700; color:{AZUL_OSCURO};">{_n(v)}</div>'
        f'<div style="font-size:8.5pt; color:{TINTA_SUAVE};">{t}</div></td>'
        for t, v in cifras
    )
    valores_dias = " · ".join(f"{d[:3]} {_n(n)}" for d, n in zip(DIAS, inf.por_dia_semana, strict=True))
    filas_zona = (
        "".join(
            f"<tr><td>{escape(z.zona)}</td><td align='right'>{_n(z.personas)}</td>"
            f"<td align='right'>{_n(z.atenciones)}</td></tr>"
            for z in inf.por_zona
        )
        or "<tr><td colspan='3'>Sin datos en el periodo.</td></tr>"
    )
    filas_detalle = (
        "".join(
            f"<tr><td>{escape(d.expediente)}</td><td>{escape(d.documento)}</td>"
            f"<td>{escape(d.nombre_completo)}</td><td align='right'>{d.atenciones}</td><td>{d.ultima:%d/%m/%Y}</td></tr>"
            for d in inf.detalle
        )
        or "<tr><td colspan='5'>No hay atenciones en el periodo.</td></tr>"
    )

    return f"""
<html><head><style>
  body {{ font-family: 'Nunito'; font-size: 9.5pt; color: {TINTA}; }}
  h1 {{ font-family: 'Fredoka'; font-size: 20pt; font-weight: 600; margin: 0; }}
  h2 {{ font-family: 'Fredoka'; font-size: 12.5pt; font-weight: 600; margin: 16px 0 6px 0; color: {AZUL_OSCURO}; }}
  table.datos {{ border-collapse: collapse; }}
  table.datos th {{ background: {PAPEL_3}; text-align: left; padding: 5px 7px; border-bottom: 1.5px solid {TINTA}; }}
  table.datos td {{ padding: 4px 7px; border-bottom: 0.5px solid #d5dce1; }}
  .meta {{ color: {TINTA_SUAVE}; font-size: 9pt; }}
</style></head><body>
<table width="100%" cellspacing="0" cellpadding="0"><tr>
  <td width="70"><img src="{logo}" width="62" height="62"></td>
  <td style="padding-left:12px;">
    <div class="meta">{escape(ORG_NAME).upper()}</div>
    <h1>Informe de atenciones</h1>
    <div class="meta">Periodo: <b>{inf.desde:%d/%m/%Y}</b> – <b>{inf.hasta:%d/%m/%Y}</b></div>
  </td></tr></table>
<p></p>
<table width="100%" cellspacing="6" cellpadding="0"><tr>{celdas_cifras}</tr></table>
<p class="meta">Se cuenta una atención por persona y día. Hogares: {_n(inf.adultos)} adultos,
{_n(inf.menores)} menores y {_n(inf.mayores)} mayores de 65 (personas atendidas en el periodo).</p>

<table width="100%" cellspacing="0" cellpadding="0"><tr>
<td width="52%" valign="top" style="padding-right:14px;">
  <h2>Atenciones por día de la semana</h2>
  <img src="grafica-dias" width="{_TAM_GRAFICA.width()}" height="{_TAM_GRAFICA.height()}">
  <div class="meta">{valores_dias}</div>
</td>
<td width="48%" valign="top">
  <h2>Por municipio / localidad</h2>
  <table class="datos" width="100%"><tr><th>Zona</th><th align="right">Personas</th>
  <th align="right">Atenciones</th></tr>{filas_zona}</table>
</td></tr></table>

<h2>Relación de expedientes atendidos ({len(inf.detalle)})</h2>
{f'<p class="meta">{escape(inf.filtro_detalle)}</p>' if inf.filtro_detalle else ""}
<table class="datos" width="100%">
  <tr><th>Expediente</th><th>Documento</th><th>Nombre y apellidos</th><th align="right">Atenciones</th>
  <th>Última</th></tr>
  {filas_detalle}
</table>
<p class="meta">Generado el {datetime.now():%d/%m/%Y a las %H:%M} · Sonrisas NFC.
Documento con datos personales: trátelo conforme al RGPD.</p>
</body></html>"""


def generar_pdf(inf: Informe, destino: Path) -> None:
    escritor = QPdfWriter(str(destino))
    escritor.setResolution(_PPP)
    escritor.setTitle(f"Informe de atenciones {inf.desde:%d/%m/%Y} - {inf.hasta:%d/%m/%Y}")
    escritor.setCreator(ORG_NAME)
    escritor.setPageLayout(
        QPageLayout(
            QPageSize(QPageSize.PageSizeId.A4), QPageLayout.Orientation.Portrait, QMarginsF(16, 14, 16, 16)
        )
    )
    doc = QTextDocument()
    doc.documentLayout().setPaintDevice(escritor)  # maquetar a la resolución del PDF, no de la pantalla
    doc.setDocumentMargin(0)
    doc.addResource(
        QTextDocument.ResourceType.ImageResource,
        QUrl("grafica-dias"),
        imagen_grafica(inf.por_dia_semana, _TAM_GRAFICA),
    )
    doc.setHtml(_html(inf))
    doc.setPageSize(QSizeF(escritor.width(), escritor.height()))
    doc.print_(escritor)
