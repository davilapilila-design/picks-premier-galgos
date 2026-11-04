"""
Ficha de una persona para el dueño (/gratuita en el bot): sobre todo si se
le dio la apuesta gratuita, cuándo y a qué canal de venta.

Lo apunta el lector al ver que el dueño envía un enlace de venta (y la fase
4 con los chats antiguos), así que sigue sabiéndose aunque luego se borren
los mensajes. Solo lee la base de datos.
"""
import json
import unicodedata
from datetime import datetime

from . import db, textos
from .carpetas import normalizar

MAX_OPCIONES = 8
CALLBACK = "gra:"  # + user_id: ficha de una de las opciones
CALLBACK_CONTIENE = "grc:"  # + lo buscado: los que lo contienen
_RELLENOS = {0x115F, 0x1160, 0x3164, 0xFFA0, 0x2800}  # se ven como espacios en blanco

_BOTONES = {"ya_apostado": "«Ya he apostado»", "primera_vez": "«Es mi primera vez»", "otro": "otro texto"}


def _sin_bienvenida(con, user_id=None):
    """Quienes no pasaron por la bienvenida (clientes de antes, o que entraron
    por otro camino) pero se conocen por el chat privado con el dueño o por los
    canales de venta, como filas de `usuarios` con todo lo demás vacío."""
    columnas = [d[0] for d in con.execute("SELECT * FROM usuarios LIMIT 0").description]
    filtro, params = ("AND user_id = ?", (user_id,)) if user_id is not None else ("", ())
    filas = {}
    for tabla in ("personas_chat", "ventas_personas"):
        for f in con.execute(f"SELECT user_id, nombre, username FROM {tabla} "
                             f"WHERE user_id NOT IN (SELECT user_id FROM usuarios) {filtro} ORDER BY user_id", params):
            filas.setdefault(f[0], {**dict.fromkeys(columnas), "user_id": f[0], "nombre": f[1], "username": f[2]})
    return list(filas.values())


def persona(con, user_id):
    """La fila de `usuarios`, la de alguien que se conoce sin bienvenida, o None."""
    fila = db.obtener_usuario(con, user_id)
    if fila is not None:
        return fila
    otras = _sin_bienvenida(con, user_id)
    return otras[0] if otras else None


def _es_id(dato):
    return dato.strip().lstrip("-").isdigit()


def _comparable(texto):
    """Sin mayúsculas, tildes, espacios de más ni caracteres invisibles (hay
    quien rodea su nombre de rellenos coreanos o espacios de anchura cero)."""
    visible = "".join(" " if ord(c) in _RELLENOS else c for c in texto or ""
                      if unicodedata.category(c) != "Cf")
    return " ".join(normalizar(visible).split())


def buscar(con, dato, contiene=False):
    """Personas que encajan con `dato` (sin importar mayúsculas ni tildes): id,
    @usuario exacto o nombre completo exacto; con `contiene`, las que llevan
    `dato` en el nombre o en el @. Las de gratuita van primero; las que no
    pasaron por la bienvenida, al final."""
    dato = dato.strip()
    if _es_id(dato):
        fila = persona(con, int(dato))
        return [fila] if fila else []
    buscado = _comparable(dato.lstrip("@"))
    if not buscado:
        return []
    filas = con.execute("SELECT * FROM usuarios ORDER BY COALESCE(enlace_venta_ts, 0) DESC, user_id").fetchall()
    filas += _sin_bienvenida(con)
    if contiene:
        return [f for f in filas
                if buscado in _comparable(f["nombre"]) or buscado in _comparable(f["username"])]
    exactas = [f for f in filas if _comparable(f["username"]) == buscado]
    return exactas or [f for f in filas if _comparable(f["nombre"]) == buscado]


def nombre(fila):
    n = fila["nombre"] or "sin nombre"
    return f"{n} (@{fila['username']})" if fila["username"] else n


def ficha(con, fila, tz):
    def fecha(ts):
        return f"{datetime.fromtimestamp(ts, tz):%d/%m/%Y a las %H:%M}"

    lineas = [f"👤 Nombre: {fila['nombre'] or 'sin nombre'}",
              f"🆔 Id de Telegram: {fila['user_id']}",
              f"📛 Usuario: @{fila['username']}" if fila["username"] else "📛 Usuario: no tiene @"]
    if fila["bienvenida_ts"] is not None:
        lineas.append(f"👋 Bienvenida: {fecha(fila['bienvenida_ts'])} "
                      f"({textos.descripcion_tipo(con, fila['bienvenida_tipo'], tz)})")
    else:
        lineas.append("👋 Sin bienvenida apuntada")
    miembro = con.execute("SELECT visto_ts FROM miembros_canal WHERE user_id = ?", (fila["user_id"],)).fetchone()
    if miembro is not None:
        lineas.append(f"📋 Ya estaba en el canal (lista de suscriptores del {fecha(miembro['visto_ts'])[:10]})")
    if fila["recurrente_ts"] is not None:
        lineas.append(f"🔁 Volvió a pedir entrar: {fecha(fila['recurrente_ts'])} (bienvenida sin gratuita)")
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


def _boton_contiene(dato):
    """El botón «Buscar los que contienen», si cabe en los 64 bytes de Telegram."""
    datos = f"{CALLBACK_CONTIENE}{dato}"
    if len(datos.encode()) > 64:
        return []
    return [[{"text": f"🔎 Buscar los que contienen «{dato}»", "callback_data": datos}]]


def respuesta(con, dato, tz, contiene=False):
    """(texto, teclado o None) para «/gratuita <dato>» (exacto) o para el botón
    «Buscar los que contienen» (`contiene`). Si nadie encaja exacto, busca los
    que lo contienen."""
    dato = dato.strip()
    if not dato:
        return ("Dime a quién: /gratuita con su @, su id o su nombre completo (por ejemplo /gratuita Juan Pérez). "
                "Si no lo encuentro exacto, busco los que lo contienen.", None)
    filas = buscar(con, dato, contiene)
    aviso = ""
    if not filas and not contiene and not _es_id(dato):
        filas, contiene = buscar(con, dato, contiene=True), True
        aviso = f"Nadie se llama exactamente «{dato}»."
    if not filas:
        return (f"No encuentro a nadie con «{dato}». Prueba con su @ o con otra parte del nombre.", None)
    ampliar = [] if contiene or _es_id(dato) else _boton_contiene(dato)
    if len(filas) == 1:
        texto = (f"{aviso} Lo contiene:\n\n" if aviso else "") + ficha(con, filas[0], tz)
        return texto, ({"inline_keyboard": ampliar} if ampliar else None)
    texto = (f"{aviso}\n" if aviso else "") + (
        f"Hay {len(filas)} personas que {'contienen' if contiene else 'se llaman'} «{dato}». ¿Cuál?")
    if len(filas) > MAX_OPCIONES:
        texto += f"\n(Te enseño las {MAX_OPCIONES} primeras; si no está, afina más el nombre.)"
    teclado = {"inline_keyboard": [
        [{"text": ("🎁 " if f["enlace_venta_ts"] is not None else "") + nombre(f)[:60],
          "callback_data": f"{CALLBACK}{f['user_id']}"}] for f in filas[:MAX_OPCIONES]] + ampliar}
    return texto, teclado
