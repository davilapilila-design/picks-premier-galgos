"""
Correo de un comprador ↔ persona de Telegram por su nombre o su @usuario.

Hay compradores que nunca salen por la hora: se van del canal después de
cada carrera (Telegram solo enseña a quien sigue dentro) o compraron cuando
no había registro. Muchos llevan su nombre en el correo
(«luisferrandiz80@…» ↔ «Luis Ferrandiz») o usan el mismo @usuario. La regla
es estricta: el @usuario coincide con el correo, o coinciden un apellido
completo y el nombre (o sus 4 primeras letras); un nombre suelto nunca vale
(pagos.emparejar_ventas decide con esto y con la hora).

Los nombres salen de los canales de venta, de los usuarios del bot y de los
chats privados del dueño, que el lector apunta una vez al día (solo id,
nombre y @usuario; ningún mensaje; autorizado por el dueño el 2026-10-30).
"""
import asyncio
import logging
import re
import time
import unicodedata

log = logging.getLogger("captacion.nombres")

CHATS_CADA_S = 24 * 3600
PUNTOS_USUARIO = 10
# Nombres de pila (también los de los compuestos: «Miguel Ángel», «Juan
# Carlos»): no cuentan como apellido.
PILA = frozenset(
    "jose juan maria angel antonio manuel luis carlos javier francisco fco miguel pedro jesus "
    "david daniel dani alex alejandro pablo sergio jorge alberto fernando rafael ramon enrique "
    "vicente andres ignacio oscar ruben adrian adri victor roberto mario diego raul ivan marcos "
    "alvaro gonzalo jaime joan josep jordi xavier pau marc carmen ana laura isabel pilar lucia "
    "elena rosa".split())


def _norm(texto):
    return unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().lower()


def preparar(nombre, username):
    """(palabras del nombre de 3 letras o más, @usuario en minúsculas sin símbolos)."""
    palabras = [p for p in re.split(r"[^a-z]+", _norm(nombre)) if len(p) >= 3]
    return palabras, re.sub(r"[^a-z0-9]", "", _norm(username))


def preparar_correo(correo):
    """(solo letras, letras y números) de lo de antes de la @."""
    local = _norm((correo or "").split("@")[0])
    return re.sub(r"[^a-z]", "", local), re.sub(r"[^a-z0-9]", "", local)


def puntos_preparados(letras, alnum, palabras, usuario):
    """(puntos, motivo) si el correo casa con la persona; si no, None.
    motivo: «usuario», «nombre» (todos sus apellidos están en el correo) o
    «nombre_parcial» (falta alguno: solo vale si además entró a la hora)."""
    if usuario and ((len(usuario) >= 5 and usuario == alnum)
                    or (min(len(usuario), len(alnum)) >= 6 and (usuario in alnum or alnum in usuario))):
        return PUNTOS_USUARIO, "usuario"
    if len(palabras) < 2:
        return None
    pila = palabras[0]
    apellidos = [p for p in palabras[1:] if len(p) >= 4 and p not in PILA and p not in pila and pila not in p]
    estan = [p for p in apellidos if p in letras]
    if not estan:
        return None
    if not (pila in letras or (len(pila) >= 4 and letras.startswith(pila[:4]))):
        return None
    return sum(p in letras for p in palabras), "nombre" if len(estan) == len(apellidos) else "nombre_parcial"


def puntos(correo, nombre, username):
    return puntos_preparados(*preparar_correo(correo), *preparar(nombre, username))


# --- Chats privados del dueño ---------------------------------------------------------

def guardar_chats(con, personas, ahora=None):
    """personas: [(user_id, nombre, username)] de los chats privados."""
    ahora = int(time.time() if ahora is None else ahora)
    con.executemany(
        "INSERT INTO personas_chat (user_id, nombre, username, visto_ts) VALUES (?, ?, ?, ?) "
        "ON CONFLICT (user_id) DO UPDATE SET nombre = excluded.nombre, "
        "username = excluded.username, visto_ts = excluded.visto_ts",
        [(uid, nombre, username, ahora) for uid, nombre, username in personas])


async def leer_chats(client):
    """[(user_id, nombre, username)] de las personas con chat privado (sin
    bots ni cuentas borradas). Solo la lista de chats: ningún mensaje."""
    from telethon.tl import types

    personas = []
    async for dialogo in client.iter_dialogs():
        u = dialogo.entity
        if isinstance(u, types.User) and not u.bot and not u.deleted and not u.is_self:
            nombre = " ".join(x for x in (u.first_name, u.last_name) if x) or None
            personas.append((u.id, nombre, u.username))
    return personas


async def lectura_periodica(client, con, cada=CHATS_CADA_S):
    """Dentro del lector: apunta una vez al día quién tiene chat privado."""
    await asyncio.sleep(600)  # que el lector arranque tranquilo
    while True:
        try:
            personas = await leer_chats(client)
            with con:
                guardar_chats(con, personas)
            log.info("Chats privados: %s personas apuntadas (solo nombre e id)", len(personas))
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Error leyendo la lista de chats privados")
        await asyncio.sleep(cada)
