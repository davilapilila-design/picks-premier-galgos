"""
Copia de todo lo que usa el cruce de las ventas de overoption con las
personas de Telegram, para guardarla en Google Drive (deploy/copia-drive.sh,
una vez al día; pedido por el dueño el 2026-10-30).

Telegram borra el registro de los canales a las 48 h y la lista de «quién se
unió» de cada enlace pierde a quien se va; la base de datos lo va guardando,
y esta copia lo pone a salvo fuera de la VM: la base entera (captacion.db) y
un CSV por tabla, con las fechas también en hora de España. La sesión de
Telegram de la cuenta del dueño no está en la base y nunca se copia.

    CAPTACION_DB=... python -m premier_captacion.copia <carpeta>
"""
import csv
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from . import pagos

TABLAS = (
    "pagos_overoption", "pagos_contenidos", "pagos_enlaces", "pagos_invitados",
    "pagos_correos_manual", "ventas_canales", "ventas_movimientos", "ventas_miembros",
    "ventas_personas", "personas_chat", "usuarios",
)
COLUMNAS_CRUCE = ("id", "pago_ts", "producto", "importe", "moneda", "neto", "metodo", "correo",
                  "enlace", "canal_id", "titulo", "user_id", "nombre", "username", "estado_cruce",
                  "posibles")
LEEME = """Copia de lo que usa el cruce de ventas de overoption con Telegram
(una carpeta por día; «ultima» es siempre la más reciente).

captacion.db              la base de datos entera (SQLite)
cruce_ventas.csv          cada venta con su persona de Telegram y cómo se sacó (estado_cruce)
pagos_overoption.csv      las ventas de overoption (correo, importe, enlace del producto...)
pagos_contenidos.csv      producto de overoption -> enlace de Telegram
pagos_enlaces.csv         cada enlace de venta -> canal de Telegram
pagos_invitados.csv       quién se unió con cada enlace y cuándo (lista de Telegram)
pagos_correos_manual.csv  lo que escribiste en «Correos por identificar»
ventas_canales.csv        los canales de venta
ventas_movimientos.csv    registro de los canales: entradas y salidas (Telegram lo borra a las 48 h)
ventas_miembros.csv       quién está en cada canal y desde cuándo
ventas_personas.csv       personas de los canales (id, nombre, @usuario)
personas_chat.csv         personas con chat privado contigo (solo id, nombre y @usuario)
usuarios.csv              personas que han pasado por el bot

Las columnas *_ts son segundos desde 1970 (UTC); cada una lleva al lado su
*_fecha en hora de España.
"""


def _es_ts(columna):
    return columna == "ts" or columna.endswith("_ts")


def _fecha(ts, tz):
    return datetime.fromtimestamp(ts, tz).strftime("%Y-%m-%d %H:%M:%S") if isinstance(ts, (int, float)) else ""


def _escribir_csv(ruta, columnas, filas, tz):
    fechas = [c for c in columnas if _es_ts(c)]
    with open(ruta, "w", encoding="utf-8-sig", newline="") as f:  # utf-8-sig: Excel ve los acentos
        w = csv.writer(f)
        w.writerow(list(columnas) + [f"{c}_fecha" for c in fechas])
        for fila in filas:
            valores = dict(zip(columnas, fila))
            w.writerow(list(fila) + [_fecha(valores[c], tz) for c in fechas])


def exportar(con, carpeta, tz):
    """Escribe en `carpeta` la base entera, un CSV por tabla, el cruce y el LEEME."""
    destino = sqlite3.connect(os.path.join(carpeta, "captacion.db"))
    try:
        con.backup(destino)  # copia coherente aunque el lector esté escribiendo
    finally:
        destino.close()
    for tabla in TABLAS:
        cursor = con.execute(f"SELECT * FROM {tabla}")
        columnas = [d[0] for d in cursor.description]
        _escribir_csv(os.path.join(carpeta, f"{tabla}.csv"), columnas, cursor.fetchall(), tz)
    cruce = [[" ".join(map(str, r[c])) if c == "posibles" else r[c] for c in COLUMNAS_CRUCE]
             for r in pagos.emparejar_ventas(con)]
    _escribir_csv(os.path.join(carpeta, "cruce_ventas.csv"), COLUMNAS_CRUCE, cruce, tz)
    with open(os.path.join(carpeta, "LEEME.txt"), "w", encoding="utf-8") as f:
        f.write(LEEME)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("Uso: CAPTACION_DB=<base> python -m premier_captacion.copia <carpeta>")
        return 2
    ruta = os.environ.get("CAPTACION_DB", "/var/lib/premier-captacion/real.db")
    con = sqlite3.connect(Path(ruta).resolve().as_uri() + "?mode=ro", uri=True)  # solo lectura
    con.row_factory = sqlite3.Row
    try:
        exportar(con, argv[0], ZoneInfo("Europe/Madrid"))
    finally:
        con.close()
    print(f"✓ Copia lista en {argv[0]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
