"""
Entradas gratis a los canales de venta (cuentas por cliente, diseño del
2026-11-01, punto 2). El dueño da canales gratis de dos formas:

- Por privado: manda el enlace del canal desde su cuenta (la gratuita de
  bienvenida o una compensación).
- En el canal fallado: publica allí el enlace del siguiente canal, y lo
  reciben quienes estaban dentro en ese momento (se les dice que no salgan).

Con lo que lee el lector (publicaciones.py) y las entradas de cada canal,
`ofertas` dice desde cuándo tiene cada persona un canal gratis. Una entrada
es gratis si llega después de la oferta: entonces no es candidata a la
compra de nadie en el cruce (cruce.Datos) y, si no hay compra suya de ese
canal, cuenta como gratis en sus cuentas.

El enlace de un canal es el mismo para las gratis y las ventas (medido el
2026-11-01), así que el canal de un enlace sale de la caché de enlaces
comprobados, de los enlaces de las ventas y del registro de los canales.
"""
import re
from collections import defaultdict

from . import pagos

PRIVADO, CANAL = "privado", "canal"
_RE_HASH = re.compile(r"(?:\+|%2B|joinchat/)([A-Za-z0-9_-]+)")


def _hash(enlace):
    m = _RE_HASH.search(enlace or "")
    return m.group(1) if m else None


def mapa_enlaces(con):
    """hash del enlace -> canal_id."""
    mapa = {f[0]: f[1] for f in con.execute("SELECT hash, chat_id FROM enlaces WHERE chat_id IS NOT NULL")}
    for enlace, canal_id in con.execute(
            "SELECT enlace, canal_id FROM pagos_enlaces WHERE canal_id IS NOT NULL "
            "UNION ALL SELECT DISTINCT enlace, canal_id FROM ventas_movimientos WHERE enlace IS NOT NULL"):
        h = _hash(enlace)
        if h:
            mapa.setdefault(h, canal_id)
    return mapa


def entradas(con):
    """(canal_id, user_id) -> {ts} de cada entrada que se ve (registro,
    miembros actuales y listas de quién se unió con cada enlace)."""
    por_enlace, _, _ = pagos._mapa_canales(con)
    salida = defaultdict(set)
    for canal_id, lista in pagos._entradas_por_canal(con).items():
        for uid, ts in lista:
            salida[(canal_id, uid)].add(ts)
    for enlace, lista in pagos._invitados_por_enlace(con).items():
        canal_id = por_enlace.get(enlace)
        if canal_id is not None:
            for uid, ts in lista:
                salida[(canal_id, uid)].add(ts)
    return salida


def _salidas(con):
    salida = defaultdict(list)
    for canal_id, uid, ts in con.execute("SELECT canal_id, user_id, ts FROM ventas_movimientos WHERE tipo = 'sale'"):
        salida[(canal_id, uid)].append(ts)
    return salida


def _dentro(entradas_ts, salidas_ts, ts):
    """Estaba dentro en `ts`: había entrado antes y no salió después."""
    antes = [e for e in entradas_ts if e <= ts]
    if not antes:
        return False
    ultima = max(antes)
    return not any(ultima < s <= ts for s in salidas_ts)


def ofertas(con, ent=None):
    """(canal_id, user_id) -> (ts, PRIVADO | CANAL): la primera vez que esa
    persona tuvo ese canal gratis."""
    ent = entradas(con) if ent is None else ent
    mapa = mapa_enlaces(con)
    canales = {f[0] for f in con.execute("SELECT canal_id FROM ventas_canales")}
    salida = {}

    def poner(clave, ts, origen):
        if clave not in salida or ts < salida[clave][0]:
            salida[clave] = (ts, origen)

    for uid, ts, h in con.execute("SELECT user_id, ts, hash FROM enlaces_privados"):
        if mapa.get(h) in canales:
            poner((mapa[h], uid), ts, PRIVADO)

    sal = _salidas(con)
    por_canal = defaultdict(list)  # canal -> [(uid, entradas, salidas)]
    for (canal_id, uid), tss in ent.items():
        por_canal[canal_id].append((uid, tss, sal.get((canal_id, uid), ())))
    for chat_id, ts, texto_enlaces in con.execute(
            "SELECT chat_id, ts, enlaces FROM publicaciones WHERE enlaces != '' ORDER BY ts"):
        if chat_id not in canales:
            continue
        destinos = {mapa.get(h) for h in texto_enlaces.split()} & canales - {chat_id}
        if not destinos:
            continue
        dentro = [uid for uid, tss, ss in por_canal[chat_id] if _dentro(tss, ss, ts)]
        for canal_id in destinos:
            for uid in dentro:
                poner((canal_id, uid), ts, CANAL)
    return salida


def para_cruce(con):
    """{(canal_id, user_id)} de quien entró en un canal después de tenerlo
    gratis: esas entradas no son de ninguna compra."""
    ent = entradas(con)
    return {k for k, (ts, _) in ofertas(con, ent).items() if k in ent and min(ent[k]) >= ts}
