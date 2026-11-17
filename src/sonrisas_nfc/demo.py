"""Datos ficticios para demostraciones y capturas de pantalla (nunca datos reales)."""

from __future__ import annotations

import random
from datetime import date, datetime, timedelta

from sonrisas_nfc.db.database import fecha_a_texto
from sonrisas_nfc.domain.models import Beneficiario, OrigenVisita
from sonrisas_nfc.domain.validators import letra_control
from sonrisas_nfc.services.contexto import Servicios

_NOMBRES = [
    "Lucía",
    "Carmen",
    "Ana",
    "Fátima",
    "Yeray",
    "Acerina",
    "Iballa",
    "Jonay",
    "Daniel",
    "María",
    "Aitor",
    "Nayra",
    "Cristo",
    "Raquel",
    "Samuel",
    "Elena",
    "Ayoze",
    "Dácil",
    "Tania",
    "Omar",
    "Yurena",
    "Moisés",
    "Aday",
    "Miriam",
    "Kevin",
    "Jennifer",
    "Nauzet",
    "Laura",
    "Pino",
    "Candelaria",
]
_APELLIDOS = [
    "González",
    "Rodríguez",
    "Hernández",
    "Pérez",
    "García",
    "Martín",
    "Santana",
    "Díaz",
    "Suárez",
    "Sánchez",
    "Cabrera",
    "Ramos",
    "Morales",
    "Delgado",
    "Medina",
    "Castro",
    "Alonso",
    "Padilla",
    "Quintana",
    "Afonso",
    "Febles",
    "Mesa",
    "Trujillo",
    "Herrera",
    "Brito",
    "Acosta",
]
_ZONAS = ("Valleseco", "La Salud", "Ofra", "Añaza", "Taco", "La Laguna", "Santa Cruz", "El Rosario")


def _dni(rng: random.Random) -> str:
    n = rng.randint(10_000_000, 79_999_999)
    return f"{n}{letra_control(n)}"


def _nie(rng: random.Random) -> str:
    prefijo = rng.choice("XYZ")
    n = rng.randint(1_000_000, 9_999_999)
    return f"{prefijo}{n:07d}{letra_control(int(str('XYZ'.index(prefijo)) + f'{n:07d}'))}"


def poblar(servicios: Servicios, cantidad: int = 140, semilla: int = 7) -> None:
    rng = random.Random(semilla)
    hoy = date.today()
    db = servicios.db
    for i in range(cantidad):
        b = servicios.beneficiarios.crear(
            Beneficiario(
                documento=_dni(rng) if rng.random() < 0.7 else _nie(rng),
                nombre=rng.choice(_NOMBRES),
                apellidos=f"{rng.choice(_APELLIDOS)} {rng.choice(_APELLIDOS)}",
                telefono=f"{rng.choice('67')}{rng.randint(10_000_000, 99_999_999)}",
                expediente=f"EXP-{2024 + i % 3}-{100 + i:04d}",
                adultos=rng.randint(1, 3),
                menores=rng.choice((0, 0, 1, 2, 3)),
                mayores=rng.choice((0, 0, 0, 1)),
                zona=rng.choice(_ZONAS),
                vencimiento=hoy + timedelta(days=rng.randint(-120, 330)),
            ),
            tarjeta_uid=None
            if rng.random() < 0.06
            else " ".join(f"{rng.randint(0, 255):02X}" for _ in range(4)),
            registrar_visita=False,
        )
        alta = datetime.combine(hoy - timedelta(days=rng.randint(20, 400)), datetime.min.time())
        with db.transaccion() as conn:
            conn.execute("UPDATE beneficiarios SET creado_en = ? WHERE id = ?", (fecha_a_texto(alta), b.id))
            dia = alta.date()
            while dia <= hoy:
                if dia.weekday() in (3, 4) and rng.random() < 0.55:  # reparto jueves y viernes
                    momento = datetime.combine(dia, datetime.min.time()) + timedelta(
                        hours=rng.randint(9, 13), minutes=rng.randint(0, 59)
                    )
                    if momento <= datetime.now():
                        conn.execute(
                            "INSERT INTO visitas (beneficiario_id, fecha, origen) VALUES (?, ?, ?)",
                            (b.id, fecha_a_texto(momento), OrigenVisita.TARJETA.value),
                        )
                dia += timedelta(days=rng.randint(5, 9))
    # Algunas atenciones hoy para que el panel no salga vacío
    todos = servicios.beneficiarios.listar()
    for b in rng.sample(todos, min(9, len(todos))):
        servicios.visitas.registrar(b.id, OrigenVisita.TARJETA)  # type: ignore[arg-type]
