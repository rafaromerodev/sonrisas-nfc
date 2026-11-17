"""Alta, edición, búsqueda, renovación y baja de beneficiarios."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, replace
from datetime import date

from sonrisas_nfc.db.database import (
    Database,
    ahora,
    fecha_a_texto,
    texto_a_fecha,
    texto_a_fecha_hora,
)
from sonrisas_nfc.domain.models import Beneficiario, OrigenVisita, sumar_meses
from sonrisas_nfc.domain.validators import (
    ErrorValidacion,
    normalizar_uid,
    texto_o_none,
    validar_documento,
    validar_telefono,
)

_SELECT = """
SELECT b.*,
       (SELECT MAX(v.fecha) FROM visitas v WHERE v.beneficiario_id = b.id) AS ultima_visita,
       (SELECT COUNT(*) FROM visitas v WHERE v.beneficiario_id = b.id AND v.duplicada = 0) AS total_visitas,
       (SELECT t.uid FROM tarjetas t WHERE t.beneficiario_id = b.id AND t.baja_en IS NULL) AS tarjeta_uid
FROM beneficiarios b
"""


@dataclass(frozen=True, slots=True)
class AvisoDuplicado:
    """Coincidencia no bloqueante (p. ej. mismo teléfono en otra ficha)."""

    campo: str
    mensaje: str


class BeneficiariosService:
    def __init__(self, db: Database) -> None:
        self.db = db

    # ------------------------------------------------------------------ lectura
    def obtener(self, beneficiario_id: int) -> Beneficiario | None:
        fila = self.db.conn.execute(_SELECT + " WHERE b.id = ?", (beneficiario_id,)).fetchone()
        return _desde_fila(fila) if fila else None

    def obtener_por_documento(self, documento: str) -> Beneficiario | None:
        fila = self.db.conn.execute(_SELECT + " WHERE b.documento = ?", (documento,)).fetchone()
        return _desde_fila(fila) if fila else None

    def listar(self, incluir_bajas: bool = True) -> list[Beneficiario]:
        where = "" if incluir_bajas else " WHERE b.activo = 1"
        filas = self.db.conn.execute(_SELECT + where + " ORDER BY ultima_visita DESC, b.id DESC")
        return [_desde_fila(f) for f in filas]

    def buscar(self, texto: str, limite: int = 50) -> list[Beneficiario]:
        """Búsqueda por documento, expediente, nombre, apellidos o teléfono (coincidencia parcial)."""
        texto = (texto or "").strip()
        if not texto:
            return []
        patron = f"%{texto}%"
        filas = self.db.conn.execute(
            _SELECT
            + """ WHERE b.documento LIKE ? OR b.expediente LIKE ? OR b.telefono LIKE ?
                   OR (b.nombre || ' ' || b.apellidos) LIKE ?
                 ORDER BY (b.documento = ? OR b.expediente = ?) DESC, b.activo DESC, b.apellidos
                 LIMIT ?""",
            (patron, patron, patron, patron, texto.upper(), texto, limite),
        )
        return [_desde_fila(f) for f in filas]

    def avisos(self, b: Beneficiario) -> list[AvisoDuplicado]:
        """Coincidencias que conviene revisar pero no impiden guardar."""
        avisos: list[AvisoDuplicado] = []
        excluir = b.id or -1
        fila = self.db.conn.execute(
            "SELECT nombre, apellidos FROM beneficiarios WHERE telefono = ? AND id <> ?",
            (b.telefono, excluir),
        ).fetchone()
        if fila:
            avisos.append(
                AvisoDuplicado("telefono", f"El teléfono ya figura en la ficha de {fila[0]} {fila[1]}.")
            )
        if b.expediente:
            fila = self.db.conn.execute(
                "SELECT nombre, apellidos FROM beneficiarios WHERE expediente = ? AND id <> ?",
                (b.expediente, excluir),
            ).fetchone()
            if fila:
                avisos.append(
                    AvisoDuplicado(
                        "expediente", f"El expediente ya figura en la ficha de {fila[0]} {fila[1]}."
                    )
                )
        return avisos

    # ---------------------------------------------------------------- escritura
    def crear(
        self, datos: Beneficiario, tarjeta_uid: str | None = None, registrar_visita: bool = True
    ) -> Beneficiario:
        """Da de alta un beneficiario, opcionalmente con tarjeta y primera visita, en una transacción."""
        b = self._validar(datos)
        uid = normalizar_uid(tarjeta_uid) if tarjeta_uid else None
        momento = fecha_a_texto(ahora())
        with self.db.transaccion() as conn:
            if conn.execute("SELECT 1 FROM beneficiarios WHERE documento = ?", (b.documento,)).fetchone():
                raise ErrorValidacion("documento", "Ya existe un beneficiario con este documento.")
            if uid and _uid_en_uso(conn, uid):
                raise ErrorValidacion("uid", "Esta tarjeta ya está asignada a otro beneficiario.")
            cur = conn.execute(
                """INSERT INTO beneficiarios (documento, nombre, apellidos, telefono, expediente, adultos,
                       menores, mayores, zona, vencimiento, notas, activo, creado_en, actualizado_en)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)""",
                (*_valores(b), momento, momento),
            )
            nuevo_id = cur.lastrowid
            if uid:
                conn.execute(
                    "INSERT INTO tarjetas (uid, beneficiario_id, asignada_en) VALUES (?, ?, ?)",
                    (uid, nuevo_id, momento),
                )
            if registrar_visita:
                conn.execute(
                    "INSERT INTO visitas (beneficiario_id, fecha, origen) VALUES (?, ?, ?)",
                    (nuevo_id, momento, OrigenVisita.ALTA.value),
                )
            self.db.registrar_cambio("alta", nuevo_id, f"Tarjeta: {uid or 'sin tarjeta'}")
        return self.obtener(nuevo_id)  # type: ignore[return-value]

    def actualizar(self, datos: Beneficiario) -> Beneficiario:
        """Guarda cambios de una ficha. El documento se puede corregir: la clave es el ``id``."""
        if datos.id is None:
            raise ValueError("Para actualizar hace falta el id del beneficiario.")
        b = self._validar(datos)
        with self.db.transaccion() as conn:
            if conn.execute(
                "SELECT 1 FROM beneficiarios WHERE documento = ? AND id <> ?", (b.documento, b.id)
            ).fetchone():
                raise ErrorValidacion("documento", "Ese documento ya pertenece a otro beneficiario.")
            anterior = self.obtener(b.id)
            if anterior is None:
                raise ErrorValidacion("id", "El beneficiario ya no existe.")
            conn.execute(
                """UPDATE beneficiarios SET documento=?, nombre=?, apellidos=?, telefono=?, expediente=?,
                       adultos=?, menores=?, mayores=?, zona=?, vencimiento=?, notas=?, actualizado_en=?
                   WHERE id=?""",
                (*_valores(b), fecha_a_texto(ahora()), b.id),
            )
            cambios = _diferencias(anterior, b)
            if cambios:
                self.db.registrar_cambio("edicion", b.id, "; ".join(cambios))
        return self.obtener(b.id)  # type: ignore[return-value]

    def renovar(self, beneficiario_id: int, meses: int, desde: date | None = None) -> Beneficiario:
        """Renueva el expediente ``meses`` meses a partir de hoy (o del vencimiento si aún no ha llegado)."""
        b = self._requerir(beneficiario_id)
        hoy = desde or date.today()
        base = b.vencimiento if b.vencimiento and b.vencimiento > hoy else hoy
        nuevo = sumar_meses(base, meses)
        with self.db.transaccion() as conn:
            conn.execute(
                "UPDATE beneficiarios SET vencimiento=?, actualizado_en=? WHERE id=?",
                (fecha_a_texto(nuevo), fecha_a_texto(ahora()), beneficiario_id),
            )
            self.db.registrar_cambio("renovacion", beneficiario_id, f"{meses} meses, vence {nuevo:%d/%m/%Y}")
        return self.obtener(beneficiario_id)  # type: ignore[return-value]

    def dar_de_baja(self, beneficiario_id: int, motivo: str = "") -> None:
        """Baja lógica: la ficha y su historial se conservan para los informes; la tarjeta queda libre."""
        self._requerir(beneficiario_id)
        momento = fecha_a_texto(ahora())
        with self.db.transaccion() as conn:
            conn.execute(
                "UPDATE beneficiarios SET activo=0, actualizado_en=? WHERE id=?", (momento, beneficiario_id)
            )
            conn.execute(
                "UPDATE tarjetas SET baja_en=?, motivo_baja=? WHERE beneficiario_id=? AND baja_en IS NULL",
                (momento, "Baja del beneficiario", beneficiario_id),
            )
            self.db.registrar_cambio("baja", beneficiario_id, motivo)

    def reactivar(self, beneficiario_id: int) -> Beneficiario:
        self._requerir(beneficiario_id)
        with self.db.transaccion() as conn:
            conn.execute(
                "UPDATE beneficiarios SET activo=1, actualizado_en=? WHERE id=?",
                (fecha_a_texto(ahora()), beneficiario_id),
            )
            self.db.registrar_cambio("reactivacion", beneficiario_id)
        return self.obtener(beneficiario_id)  # type: ignore[return-value]

    # ---------------------------------------------------------------- internos
    def _requerir(self, beneficiario_id: int) -> Beneficiario:
        b = self.obtener(beneficiario_id)
        if b is None:
            raise ErrorValidacion("id", "El beneficiario no existe.")
        return b

    @staticmethod
    def _validar(datos: Beneficiario) -> Beneficiario:
        nombre = texto_o_none(datos.nombre)
        apellidos = texto_o_none(datos.apellidos)
        if not nombre:
            raise ErrorValidacion("nombre", "El nombre es obligatorio.")
        if not apellidos:
            raise ErrorValidacion("apellidos", "Los apellidos son obligatorios.")
        for campo in ("adultos", "menores", "mayores"):
            valor = getattr(datos, campo)
            if valor is not None and valor < 0:
                raise ErrorValidacion(campo, "No puede ser negativo.")
        return replace(
            datos,
            nombre=nombre,
            apellidos=apellidos,
            documento=validar_documento(datos.documento),
            telefono=validar_telefono(datos.telefono),
            expediente=texto_o_none(datos.expediente),
            zona=texto_o_none(datos.zona),
            notas=texto_o_none(datos.notas),
        )


def _uid_en_uso(conn: sqlite3.Connection, uid: str) -> bool:
    return (
        conn.execute("SELECT 1 FROM tarjetas WHERE uid = ? AND baja_en IS NULL", (uid,)).fetchone()
        is not None
    )


def _valores(b: Beneficiario) -> tuple:
    return (
        b.documento, b.nombre, b.apellidos, b.telefono, b.expediente, b.adultos,
        b.menores, b.mayores, b.zona, fecha_a_texto(b.vencimiento), b.notas,
    )  # fmt: skip


_CAMPOS_AUDITADOS = {
    "documento": "Documento", "nombre": "Nombre", "apellidos": "Apellidos", "telefono": "Teléfono",
    "expediente": "Expediente", "adultos": "Adultos", "menores": "Menores", "mayores": "Mayores",
    "zona": "Zona", "vencimiento": "Vencimiento", "notas": "Notas",
}  # fmt: skip


def _diferencias(antes: Beneficiario, despues: Beneficiario) -> list[str]:
    return [
        f"{etiqueta}: {getattr(antes, campo) or '—'} → {getattr(despues, campo) or '—'}"
        for campo, etiqueta in _CAMPOS_AUDITADOS.items()
        if getattr(antes, campo) != getattr(despues, campo)
    ]


def _desde_fila(f: sqlite3.Row) -> Beneficiario:
    claves = f.keys()
    return Beneficiario(
        id=f["id"],
        documento=f["documento"],
        nombre=f["nombre"],
        apellidos=f["apellidos"],
        telefono=f["telefono"],
        expediente=f["expediente"],
        adultos=f["adultos"],
        menores=f["menores"],
        mayores=f["mayores"],
        zona=f["zona"],
        vencimiento=texto_a_fecha(f["vencimiento"]),
        notas=f["notas"],
        activo=bool(f["activo"]),
        creado_en=texto_a_fecha_hora(f["creado_en"]),
        ultima_visita=texto_a_fecha_hora(f["ultima_visita"]) if "ultima_visita" in claves else None,
        total_visitas=f["total_visitas"] if "total_visitas" in claves else 0,
        tarjeta_uid=f["tarjeta_uid"] if "tarjeta_uid" in claves else None,
    )
