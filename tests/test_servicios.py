from dataclasses import replace
from datetime import date, datetime, timedelta

import pytest

from sonrisas_nfc.domain.models import EstadoExpediente, MotivoCambioTarjeta, OrigenVisita
from sonrisas_nfc.domain.validators import ErrorValidacion
from sonrisas_nfc.services.atencion import Resultado

UID_A = "04 A1 B2 C3"
UID_B = "04 D4 E5 F6"


def test_alta_con_tarjeta_y_primera_visita(servicios, datos):
    b = servicios.beneficiarios.crear(datos, tarjeta_uid="04a1b2c3")
    assert b.id is not None
    assert b.tarjeta_uid == UID_A
    assert b.total_visitas == 1
    assert b.miembros_hogar == 3


def test_documento_duplicado(servicios, datos):
    servicios.beneficiarios.crear(datos)
    with pytest.raises(ErrorValidacion, match="Ya existe"):
        servicios.beneficiarios.crear(replace(datos, telefono="699999999"))


def test_tarjeta_en_uso_no_se_puede_asignar_en_alta(servicios, datos):
    servicios.beneficiarios.crear(datos, tarjeta_uid=UID_A)
    with pytest.raises(ErrorValidacion, match="ya está asignada"):
        servicios.beneficiarios.crear(replace(datos, documento="X1234567L"), tarjeta_uid=UID_A)
    # La transacción se deshizo: no se creó el segundo beneficiario
    assert servicios.beneficiarios.obtener_por_documento("X1234567L") is None


def test_corregir_documento_conserva_historial(servicios, datos):
    """En la versión anterior, cambiar el DNI en la ficha no guardaba nada (o pisaba otra ficha)."""
    b = servicios.beneficiarios.crear(datos)
    corregido = servicios.beneficiarios.actualizar(replace(b, documento="X1234567L"))
    assert corregido.documento == "X1234567L"
    assert corregido.total_visitas == 1


def test_no_se_puede_pisar_documento_de_otro(servicios, datos):
    servicios.beneficiarios.crear(datos)
    otro = servicios.beneficiarios.crear(replace(datos, documento="X1234567L", telefono="699999999"))
    with pytest.raises(ErrorValidacion, match="otro beneficiario"):
        servicios.beneficiarios.actualizar(replace(otro, documento="12345678Z"))


def test_avisos_telefono_y_expediente_repetidos(servicios, datos):
    servicios.beneficiarios.crear(datos)
    avisos = servicios.beneficiarios.avisos(replace(datos, documento="X1234567L"))
    assert {a.campo for a in avisos} == {"telefono", "expediente"}


def test_cambio_de_tarjeta_por_perdida_conserva_historial(servicios, datos):
    b = servicios.beneficiarios.crear(datos, tarjeta_uid=UID_A)
    servicios.visitas.registrar(b.id, momento=datetime.now() + timedelta(days=1))

    servicios.tarjetas.asignar(b.id, UID_B, MotivoCambioTarjeta.PERDIDA)

    actual = servicios.beneficiarios.obtener(b.id)
    assert actual.tarjeta_uid == UID_B
    assert actual.total_visitas == 2  # historial intacto
    historial = servicios.tarjetas.historial(b.id)
    assert [t.uid for t in historial] == [UID_B, UID_A]
    assert historial[1].motivo_baja == "Pérdida"
    # La tarjeta antigua ya no da acceso, pero se reconoce
    r = servicios.atencion.procesar_tarjeta(UID_A)
    assert r.resultado is Resultado.TARJETA_DE_BAJA
    assert r.beneficiario.id == b.id


def test_no_se_puede_reasignar_tarjeta_de_otra_persona(servicios, datos):
    servicios.beneficiarios.crear(datos, tarjeta_uid=UID_A)
    otro = servicios.beneficiarios.crear(replace(datos, documento="X1234567L", telefono="699999999"))
    with pytest.raises(ErrorValidacion, match="ya pertenece a Ana"):
        servicios.tarjetas.asignar(otro.id, UID_A)


def test_tarjeta_nueva(servicios):
    assert servicios.atencion.procesar_tarjeta(UID_A).resultado is Resultado.TARJETA_NUEVA


def test_una_sola_atencion_por_dia(servicios, datos):
    """Regresión: la versión anterior registraba otra visita cada 1,5 s con la tarjeta en el lector."""
    b = servicios.beneficiarios.crear(datos, tarjeta_uid=UID_A, registrar_visita=False)
    b = servicios.beneficiarios.renovar(b.id, 6)
    r1 = servicios.atencion.procesar_tarjeta(UID_A)
    r2 = servicios.atencion.procesar_tarjeta(UID_A)
    assert r1.resultado is Resultado.VISITA_REGISTRADA
    assert r2.resultado is Resultado.YA_ATENDIDO_HOY
    assert servicios.beneficiarios.obtener(b.id).total_visitas == 1


def test_expediente_vencido_requiere_confirmacion(servicios, datos):
    b = servicios.beneficiarios.crear(
        replace(datos, vencimiento=date.today() - timedelta(days=1)),
        tarjeta_uid=UID_A,
        registrar_visita=False,
    )
    r = servicios.atencion.procesar_tarjeta(UID_A)
    assert r.resultado is Resultado.EXPEDIENTE_VENCIDO
    assert servicios.beneficiarios.obtener(b.id).total_visitas == 0
    r = servicios.atencion.registrar(r.beneficiario, UID_A)
    assert r.resultado is Resultado.VISITA_REGISTRADA


def test_renovar_desde_hoy_o_desde_vencimiento(servicios, datos):
    hoy = date(2026, 3, 10)
    vencido = servicios.beneficiarios.crear(replace(datos, vencimiento=date(2026, 1, 1)))
    assert servicios.beneficiarios.renovar(vencido.id, 6, desde=hoy).vencimiento == date(2026, 9, 10)
    vigente = servicios.beneficiarios.crear(
        replace(datos, documento="X1234567L", telefono="699999999", vencimiento=date(2026, 5, 1))
    )
    assert servicios.beneficiarios.renovar(vigente.id, 12, desde=hoy).vencimiento == date(2027, 5, 1)


def test_estados_de_expediente(datos):
    hoy = date(2026, 6, 1)
    assert replace(datos, vencimiento=None).estado(hoy) is EstadoExpediente.SIN_FECHA
    assert replace(datos, vencimiento=date(2026, 5, 31)).estado(hoy) is EstadoExpediente.VENCIDO
    assert replace(datos, vencimiento=date(2026, 6, 20)).estado(hoy) is EstadoExpediente.POR_VENCER
    assert replace(datos, vencimiento=date(2026, 12, 1)).estado(hoy) is EstadoExpediente.VIGENTE
    assert replace(datos, activo=False).estado(hoy) is EstadoExpediente.BAJA


def test_baja_libera_tarjeta_y_conserva_visitas_en_informe(servicios, datos):
    b = servicios.beneficiarios.crear(datos, tarjeta_uid=UID_A)
    servicios.beneficiarios.dar_de_baja(b.id, "Se traslada")
    r = servicios.atencion.procesar_tarjeta(UID_A)
    assert r.resultado is Resultado.TARJETA_DE_BAJA
    informe = servicios.informes.generar(date.today(), date.today())
    assert informe.atenciones == 1  # el historial sigue contando
    # La tarjeta liberada puede asignarse a otra persona
    otro = servicios.beneficiarios.crear(replace(datos, documento="X1234567L", telefono="699999999"))
    servicios.tarjetas.asignar(otro.id, UID_A)
    assert servicios.atencion.procesar_tarjeta(UID_A).beneficiario.id == otro.id


def test_busqueda_parcial(servicios, datos):
    servicios.beneficiarios.crear(datos)
    assert len(servicios.beneficiarios.buscar("pérez")) == 1
    assert len(servicios.beneficiarios.buscar("EXP-0")) == 1
    assert len(servicios.beneficiarios.buscar("5678")) == 1
    assert servicios.beneficiarios.buscar("zzz") == []


def test_informe_y_resumen(servicios, datos):
    b = servicios.beneficiarios.crear(datos)
    servicios.beneficiarios.crear(replace(datos, documento="X1234567L", telefono="699999999", zona=None))
    ayer = datetime.now() - timedelta(days=1)
    servicios.visitas.registrar(b.id, OrigenVisita.MANUAL, momento=ayer)
    inf = servicios.informes.generar(date.today() - timedelta(days=1), date.today())
    assert inf.atenciones == 3
    assert inf.personas_unicas == 2
    assert inf.altas_nuevas == 2
    assert (inf.adultos, inf.menores) == (4, 2)
    assert {z.zona for z in inf.por_zona} == {"Valleseco", "Sin indicar"}
    assert sum(inf.por_dia_semana) == 3
    resumen = servicios.informes.resumen()
    assert resumen.atenciones_hoy == 2
    assert resumen.activos == 2
    assert resumen.sin_tarjeta == 2


def test_registro_de_cambios(servicios, datos):
    b = servicios.beneficiarios.crear(datos, tarjeta_uid=UID_A)
    servicios.beneficiarios.actualizar(replace(b, telefono="699999999"))
    servicios.tarjetas.asignar(b.id, UID_B, MotivoCambioTarjeta.ROBO)
    acciones = [
        r[0]
        for r in servicios.db.conn.execute(
            "SELECT accion FROM registro_cambios WHERE beneficiario_id = ? ORDER BY id", (b.id,)
        )
    ]
    assert acciones == ["alta", "edicion", "cambio_tarjeta"]
