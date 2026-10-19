"""
Textos que el dueño cambia desde el bot (/textos).

Los de partida están en mensajes.TEXTOS_EDITABLES. Cada cambio se guarda
como una fila nueva de la tabla `textos` (no se borra nada): vale el
último guardado de cada clave y, si no hay ninguno, el de partida. Así se
puede volver al anterior o al original.

La bienvenida es especial: cada texto distinto es un «tipo de mensaje»
(bot_b_v1 el de partida; bot_b_v2, v3… los que cree el dueño), para
comparar en el Sheet qué versión hace que más gente le escriba. Si vuelve a
poner un texto que ya usó, recupera el mismo tipo: un tipo es siempre un
mismo texto.

La edición va en dos pasos (el dueño manda el texto nuevo; el bot le
enseña cómo quedará y él confirma), y lo pendiente se guarda en la tabla
`estado` para que no se pierda si el bot se reinicia entre medias.
"""
import json
import re
from datetime import datetime

from . import db, mensajes

# Más que de sobra para estos mensajes, y lejos del límite de Telegram
# (4096) aunque se le sumen título y final.
MAX_CARACTERES = 3000
CADUCIDAD_EDICION_S = 30 * 60
_CLAVE_EDICION = "edicion_texto"
_RE_VERSION = re.compile(r"bot_b_v(\d+)")


def nombre(clave):
    return mensajes.TEXTOS_EDITABLES[clave][0]


def original(clave):
    return mensajes.TEXTOS_EDITABLES[clave][1]


def actual(con, clave):
    fila = con.execute("SELECT texto FROM textos WHERE clave = ? ORDER BY id DESC LIMIT 1", (clave,)).fetchone()
    return fila["texto"] if fila else original(clave)


def anterior(con, clave):
    """El texto que había antes del actual, o None si nunca se ha cambiado."""
    filas = con.execute("SELECT texto FROM textos WHERE clave = ? ORDER BY id DESC LIMIT 2", (clave,)).fetchall()
    if not filas:
        return None
    return filas[1]["texto"] if len(filas) > 1 else original(clave)


def tipo_bienvenida(con):
    """Tipo de mensaje de la bienvenida que se está enviando ahora."""
    fila = con.execute(
        "SELECT tipo_mensaje FROM textos WHERE clave = 'bienvenida' ORDER BY id DESC LIMIT 1").fetchone()
    return fila["tipo_mensaje"] if fila else mensajes.TIPO_BIENVENIDA_BOT


def _tipo_para(con, texto):
    if texto == original("bienvenida"):
        return mensajes.TIPO_BIENVENIDA_BOT
    fila = con.execute("SELECT tipo_mensaje FROM textos WHERE clave = 'bienvenida' AND texto = ? LIMIT 1",
                       (texto,)).fetchone()
    if fila:
        return fila["tipo_mensaje"]
    usados = [1]
    for (tipo,) in con.execute("SELECT DISTINCT tipo_mensaje FROM textos WHERE clave = 'bienvenida'"):
        m = _RE_VERSION.fullmatch(tipo or "")
        if m:
            usados.append(int(m.group(1)))
    return f"bot_b_v{max(usados) + 1}"


def guardar(con, clave, texto, ahora):
    """Guarda `texto` como el de `clave`. Devuelve el tipo de mensaje (solo
    en la bienvenida; None en los demás)."""
    tipo = _tipo_para(con, texto) if clave == "bienvenida" else None
    with con:
        con.execute("INSERT INTO textos (clave, texto, tipo_mensaje, creado_ts) VALUES (?, ?, ?, ?)",
                    (clave, texto, tipo, int(ahora)))
        db.registrar_evento(con, ahora, "texto_cambiado", None, clave=clave, tipo_mensaje=tipo)
    return tipo


def versiones_bienvenida(con):
    """[(tipo, texto, desde_ts)] de las bienvenidas creadas desde el bot, en orden."""
    return [(f["tipo_mensaje"], f["texto"], f["desde"]) for f in con.execute(
        "SELECT tipo_mensaje, texto, MIN(creado_ts) AS desde FROM textos "
        "WHERE clave = 'bienvenida' AND tipo_mensaje IS NOT NULL AND tipo_mensaje != ? "
        "GROUP BY tipo_mensaje ORDER BY desde", (mensajes.TIPO_BIENVENIDA_BOT,))]


def descripcion_tipo(con, tipo, tz=None):
    """Para el Sheet y los resúmenes; también los tipos creados desde el bot."""
    if tipo in mensajes.TIPOS_MENSAJE:
        return mensajes.TIPOS_MENSAJE[tipo]
    m = _RE_VERSION.fullmatch(tipo or "")
    if not m:
        return tipo
    fila = con.execute("SELECT MIN(creado_ts) FROM textos WHERE tipo_mensaje = ?", (tipo,)).fetchone()
    desde = f" el {datetime.fromtimestamp(fila[0], tz):%d/%m/%Y}" if fila and fila[0] and tz else ""
    return f"Bienvenida del bot, versión {m.group(1)} (cambiada desde el bot{desde})"


# --- Lo que manda el dueño ----------------------------------------------------

def con_negritas(texto, entidades):
    """El texto de un mensaje con las negritas que el dueño puso con el
    formato de Telegram pasadas a letras negrita Unicode (como las de la
    bienvenida), que se ven igual sin formato. Telegram da las posiciones en
    unidades UTF-16: un emoji suele contar como dos."""
    datos = texto.encode("utf-16-le")
    rangos = sorted((e["offset"], e["offset"] + e["length"])
                    for e in entidades or () if e.get("type") == "bold")
    partes, pos = [], 0
    for inicio, fin in rangos:
        inicio = max(inicio, pos)
        if fin <= inicio:
            continue
        partes.append(datos[pos * 2:inicio * 2].decode("utf-16-le"))
        partes.append(mensajes.negrita(datos[inicio * 2:fin * 2].decode("utf-16-le")))
        pos = fin
    partes.append(datos[pos * 2:].decode("utf-16-le"))
    return "".join(partes)


def problema(texto):
    """Por qué no vale un texto nuevo, o None si vale."""
    if not texto.strip():
        return "está vacío"
    largo = len(texto.encode("utf-16-le")) // 2
    if largo > MAX_CARACTERES:
        return f"es demasiado largo ({largo} caracteres; como mucho {MAX_CARACTERES})"
    return None


# --- Edición en curso (un solo dueño, una edición a la vez) -------------------

def empezar_edicion(con, clave, ahora):
    _guardar_edicion(con, {"clave": clave, "nuevo": None, "ts": int(ahora)})


def preparar(con, edicion, nuevo, ahora):
    """Texto nuevo recibido: queda a la espera de que el dueño confirme."""
    _guardar_edicion(con, dict(edicion, nuevo=nuevo, ts=int(ahora)))


def edicion(con, ahora):
    """La edición en curso, o None (si no hay o ha caducado)."""
    valor = db.leer_estado(con, _CLAVE_EDICION)
    if not valor:
        return None
    datos = json.loads(valor)
    if ahora - datos["ts"] > CADUCIDAD_EDICION_S or datos["clave"] not in mensajes.TEXTOS_EDITABLES:
        terminar(con)
        return None
    return datos


def terminar(con):
    with con:
        db.guardar_estado(con, _CLAVE_EDICION, "")


def _guardar_edicion(con, datos):
    with con:
        db.guardar_estado(con, _CLAVE_EDICION, json.dumps(datos, ensure_ascii=False))
