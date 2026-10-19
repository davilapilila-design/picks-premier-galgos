"""
Ficha de una persona para el dueño (/gratuita en el bot): sobre todo si se
le dio la apuesta gratuita, cuándo y a qué canal de venta.

Lo apunta el lector al ver que el dueño envía un enlace de venta (y la fase
4 con los chats antiguos), así que sigue sabiéndose aunque luego se borren
los mensajes. Solo lee la base de datos.
"""
import json
from datetime import datetime

from . import db, textos
from .carpetas import normalizar

MAX_OPCIONES = 8
CALLBACK = "gra:"  # + user_id: ficha de una de las opciones

_BOTONES = {"ya_apostado": "«Ya he apostado»", "primera_vez": "«Es mi primera vez»", "otro": "otro texto"}


def buscar(con, dato):
    """Personas que encajan con `dato`: @usuario exacto, id, o parte del nombre o del @
    (sin importar mayúsculas ni tildes). Las de enlace exacto van primero."""
    dato = dato.strip()
    if dato.lstrip("-").isdigit():
        fila = db.obtener_usuario(con, int(dato))
        return [fila] if fila else []
    buscado = normalizar(dato.lstrip("@"))
    if not buscado:
        return []
    filas = con.execute("SELECT * FROM usuarios ORDER BY COALESCE(enlace_venta_ts, 0) DESC, user_id").fetchall()
    exactas = [f for f in filas if normalizar(f["username"]) == buscado]
    if exactas:
        return exactas
    return [f for f in filas
            if buscado in normalizar(f["nombre"]) or buscado in normalizar(f["username"])]


def nombre(fila):
    n = fila["nombre"] or "sin nombre"
    return f"{n} (@{fila['username']})" if fila["username"] else n


def ficha(con, fila, tz):
    def fecha(ts):
        return f"{datetime.fromtimestamp(ts, tz):%d/%m/%Y a las %H:%M}"

    lineas = [f"👤 {nombre(fila)}"]
    if fila["bienvenida_ts"] is not None:
        lineas.append(f"👋 Bienvenida: {fecha(fila['bienvenida_ts'])} "
                      f"({textos.descripcion_tipo(con, fila['bienvenida_tipo'], tz)})")
    else:
        lineas.append("👋 Sin bienvenida apuntada")
    if fila["primer_mensaje_ts"] is not None:
        boton = _BOTONES.get(fila["boton"])
        lineas.append(f"💬 Te escribió por primera vez: {fecha(fila['primer_mensaje_ts'])}"
                      + (f", con el botón {boton}" if boton else ""))
    envios = []  # (ts, canal, enlace)
    for e in con.execute("SELECT ts, detalle FROM eventos WHERE user_id = ? AND tipo = 'enlace_venta' "
                         "ORDER BY ts, id", (fila["user_id"],)):
        detalle = json.loads(e["detalle"] or "{}")
        envios.append((e["ts"], detalle.get("canal") or "desconocido", detalle.get("enlace")))
    if fila["enlace_venta_ts"] is None:
        lineas.append("🎁 No le consta ninguna apuesta gratuita.")
        return "\n".join(lineas)
    canal, enlace = next(((c, e) for ts, c, e in envios if ts == fila["enlace_venta_ts"]),
                         (fila["canal_venta"] or "desconocido", fila["enlace_venta"]))
    lineas.append(f"🎁 Gratuita: {fecha(fila['enlace_venta_ts'])}, canal de venta «{canal}»")
    if enlace:
        lineas.append(f"   Enlace: {enlace}")
    despues = [(ts, c, e) for ts, c, e in envios if ts > fila["enlace_venta_ts"]]
    if despues:
        n = len(despues)
        lineas.append("🔗 Después se le envió 1 enlace de venta más:" if n == 1
                      else f"🔗 Después se le enviaron {n} enlaces de venta más:")
        lineas += [f"   · {fecha(ts)}: «{c}»" + (f" – {e}" if e else "") for ts, c, e in despues]
    return "\n".join(lineas)


def respuesta(con, dato, tz):
    """(texto, teclado o None) para «/gratuita <dato>»."""
    if not dato.strip():
        return ("Dime a quién: /gratuita @usuario, o parte de su nombre (por ejemplo /gratuita Juan).", None)
    filas = buscar(con, dato)
    if not filas:
        return (f"No encuentro a nadie con «{dato.strip()}». Prueba con su @ o con otra parte del nombre.", None)
    if len(filas) == 1:
        return ficha(con, filas[0], tz), None
    texto = f"Hay {len(filas)} personas con «{dato.strip()}». ¿Cuál?"
    if len(filas) > MAX_OPCIONES:
        texto += f"\n(Te enseño las {MAX_OPCIONES} primeras; si no está, afina más el nombre.)"
    teclado = {"inline_keyboard": [
        [{"text": ("🎁 " if f["enlace_venta_ts"] is not None else "") + nombre(f)[:60],
          "callback_data": f"{CALLBACK}{f['user_id']}"}] for f in filas[:MAX_OPCIONES]]}
    return texto, teclado
