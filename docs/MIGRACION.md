# Migración de la versión 1 a la versión 2

Esta guía es para quien instale la actualización en el ordenador de la sede.

## Antes de empezar

1. Cierre el programa antiguo.
2. **Haga una copia del archivo de datos antiguo** en un USB. Está en la carpeta del programa
   antiguo y se llama `ong_usuarios.db` (en la instalación actual, en
   `ONG_NFC_Deploy_APP\dist\ONG_Sonrisas\`).

## Instalación

1. Ejecute `SonrisasNFC-2.0.0-instalador.exe` (o copie la carpeta `SonrisasNFC`).
2. **No desinstale ni borre** todavía el programa antiguo.

## Importar los datos

Hay dos formas de hacerlo:

- **Automática.** Si abre la versión 2 desde la carpeta donde está `ong_usuarios.db`, al primer
  arranque le preguntará si quiere importarlo.
- **Manual.** En *Datos y copias* → *Importar ong_usuarios.db…*, seleccione el archivo.

Al terminar, el programa muestra un resumen.

| Concepto | Resultado esperado con los datos de agosto de 2026 |
|---|---|
| Beneficiarios | 487 |
| Tarjetas | 486 |
| Visitas importadas | 2.447 (todas) |
| Visitas repetidas el mismo día | 652: se conservan, pero no cuentan en los informes |
| Documentos a revisar | 32 (letra de control incorrecta o DNI sin letra) |

> **Por qué cambian las cifras de los informes.** La versión 1 registraba una visita nueva cada
> 1,5 segundos mientras la tarjeta estuviera apoyada en el lector. Por eso, de cada 4 visitas
> registradas, aproximadamente 1 era una repetición. La versión 2 cuenta **una atención por
> persona y día**. Los informes anteriores generados con la v1 estaban inflados en torno a un 27 %.

## Después de importar

- Revise los **documentos marcados** (aparecen en el resumen de la importación). Abra la ficha
  y corrija la letra.
- En *Inicio*, pulse *Expedientes vencidos* para ver quién necesita renovar.
- Pruebe a pasar una tarjeta: debe abrirse la ficha con el mensaje "Atención registrada".

## Dónde quedan los datos

`%LOCALAPPDATA%\SonrisasCanarias\NFC\`:

- `sonrisas.db`: la base de datos.
- `copias\`: copias automáticas, una al día; se conservan 30.
- `logs\`: registro técnico para el soporte.

Reinstalar o actualizar el programa **no** toca esta carpeta.
