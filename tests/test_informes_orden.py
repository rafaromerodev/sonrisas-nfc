"""Orden numérico de expedientes y filtros de la relación de expedientes del informe."""

from dataclasses import replace
from datetime import date

from sonrisas_nfc.domain.models import clave_natural
from sonrisas_nfc.services.informes import Apariciones, FilaDetalle, OrdenDetalle, filtrar_detalle


def _fila(
    exp: str, atenciones: int = 1, doc: str = "12345678Z", nombre: str = "Ana", dia: int = 1
) -> FilaDetalle:
    return FilaDetalle(1, exp, doc, nombre, "", atenciones, date(2026, 5, dia))


DETALLE = [
    _fila("1234", 3, "X1234567L", "Luis", 4),
    _fila("45", 1, "11111111H", "Ana", 9),
    _fila("", 7, "22222222J", "Sin expediente", 2),
    _fila("100", 12, "33333333P", "Carmen", 1),
    _fila("1234.1", 2, "44444444A", "Pedro", 3),
    _fila("145", 5, "55555555K", "Bea", 8),
]


def _exps(filas):
    return [f.expediente for f in filas]


def test_clave_natural():
    assert sorted(["100", "45", "1234", "99"], key=clave_natural) == ["45", "99", "100", "1234"]
    assert clave_natural("1234") < clave_natural("1234.1") < clave_natural("1235")
    assert clave_natural(None) > clave_natural("999999")


def test_orden_por_defecto_expediente_menor_a_mayor_y_vacios_al_final():
    assert _exps(filtrar_detalle(DETALLE)) == ["45", "100", "145", "1234", "1234.1", ""]


def test_orden_mayor_a_menor_mantiene_vacios_al_final():
    assert _exps(filtrar_detalle(DETALLE, orden=OrdenDetalle.EXPEDIENTE_DESC)) == [
        "1234.1", "1234", "145", "100", "45", "",
    ]  # fmt: skip


def test_otros_ordenes():
    assert _exps(filtrar_detalle(DETALLE, orden=OrdenDetalle.MAS_ATENCIONES))[:2] == ["100", ""]
    assert _exps(filtrar_detalle(DETALLE, orden=OrdenDetalle.MENOS_ATENCIONES))[0] == "45"
    assert _exps(filtrar_detalle(DETALLE, orden=OrdenDetalle.ULTIMA_RECIENTE))[0] == "45"
    assert [f.nombre_completo for f in filtrar_detalle(DETALLE, orden=OrdenDetalle.NOMBRE)][:2] == [
        "Ana",
        "Bea",
    ]


def test_filtro_apariciones():
    assert _exps(filtrar_detalle(DETALLE, apariciones=Apariciones.UNA)) == ["45"]
    assert _exps(filtrar_detalle(DETALLE, apariciones=Apariciones.CINCO_O_MAS)) == ["100", "145", ""]
    assert _exps(filtrar_detalle(DETALLE, apariciones=Apariciones.DIEZ_O_MAS)) == ["100"]


def test_busqueda_exacta_por_expediente_no_trae_parecidos():
    assert _exps(filtrar_detalle(DETALLE, "45")) == ["45"]  # no el 145
    assert _exps(filtrar_detalle(DETALLE, "x1234567l")) == ["1234"]


def test_busqueda_parcial_si_no_hay_exacta():
    assert _exps(filtrar_detalle(DETALLE, "123")) == ["1234", "1234.1"]
    assert _exps(filtrar_detalle(DETALLE, "carm")) == ["100"]


def test_informe_ordena_por_expediente_numerico(servicios, datos):
    for exp, doc, tel in (("100", "12345678Z", "611111111"), ("45", "X1234567L", "622222222")):
        servicios.beneficiarios.crear(replace(datos, expediente=exp, documento=doc, telefono=tel))
    inf = servicios.informes.generar(date.today(), date.today())
    assert _exps(inf.detalle) == ["45", "100"]
