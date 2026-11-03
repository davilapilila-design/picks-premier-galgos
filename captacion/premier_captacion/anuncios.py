"""
Anuncios de venta del canal principal y cuándo hay una venta abierta
(diseño del 2026-11-03: docs/superpowers/specs/2026-11-03-ventas-cada-20-min-design.md).
Solo lee la base local.

- Anuncio de venta: un mensaje del canal principal con el enlace de pago de
  payoption u overoption en el texto («Estas 3 apuestas por solo 36 € ⬇️ …»).
  El lector los guarda al momento en `publicaciones` (publicaciones.py).
- Canal de la venta: el de la mayoría de las compras de la primera hora tras
  el anuncio (por el enlace del producto o su nombre, como el cruce).
- Abierta hasta 15 min después de la última carrera de las apuestas de ese
  canal; si aún no se sabe el canal o sus carreras, hasta 4 h después del
  anuncio. Nunca más de 8 h.

Mientras haya una abierta, captacion-pagos-venta@ lee overoption cada 20 min
(pagos.py --si-hay-venta).
"""
import re
from collections import Counter

from . import analisis, apuestas, pagos

RE_PAGO = re.compile(r"\b(?:pay|over)option\.io/", re.I)
MAX_S = 8 * 3600
SIN_CARRERAS_S = 4 * 3600
TRAS_CARRERA_S = 15 * 60
PRIMERA_HORA_S = 3600
APUESTAS_ANTES_S = 3600  # apuestas del canal publicadas desde una hora antes del anuncio


def es_anuncio(texto):
    return bool(texto) and RE_PAGO.search(texto) is not None


def anuncios(con, principal, desde):
    """[ts] de los anuncios de venta del canal principal desde `desde`."""
    return [f[0] for f in con.execute(
        "SELECT ts, texto FROM publicaciones WHERE chat_id = ? AND ts >= ? ORDER BY ts",
        (principal, int(desde))) if es_anuncio(f[1])]


def canal_de_la_venta(con, ts):
    """El canal de la mayoría de las compras de la primera hora tras el
    anuncio, o None si aún no hay ninguna con canal conocido."""
    por_enlace, por_titulo, _ = pagos._mapa_canales(con)
    filas = con.execute(
        "SELECT enlace, producto FROM pagos_overoption WHERE es_propina = 0 AND estado = 'SUCCESS' "
        "AND pago_ts >= ? AND pago_ts <= ?", (int(ts), int(ts) + PRIMERA_HORA_S))
    cuenta = Counter(c for c in (pagos._canal_de_venta({"enlace": f[0], "producto": f[1]}, por_enlace, por_titulo)
                                 for f in filas) if c is not None)
    return cuenta.most_common(1)[0][0] if cuenta else None


def ultima_carrera(con, canal_id, desde):
    """Hora (ts) de la última carrera de las apuestas del canal publicadas
    desde `desde`, o None. Sin los avisos con una hora ya pasada."""
    horas = []
    for ts, texto in con.execute("SELECT ts, texto FROM publicaciones WHERE chat_id = ? AND ts >= ?",
                                 (canal_id, int(desde))):
        if not analisis.es_apuesta(texto or ""):
            continue
        h = apuestas.hora_carrera({"ts": ts, "texto": texto})
        if h >= ts - apuestas.YA_CORRIDA_S:
            horas.append(h)
    return max(horas, default=None)


def hasta(con, ts):
    """Hasta cuándo está abierta la venta anunciada a la hora `ts`."""
    canal = canal_de_la_venta(con, ts)
    ultima = ultima_carrera(con, canal, ts - APUESTAS_ANTES_S) if canal is not None else None
    fin = ts + SIN_CARRERAS_S if ultima is None else ultima + TRAS_CARRERA_S
    return min(fin, ts + MAX_S)


def abiertas(con, principal, ahora):
    """[(ts del anuncio, hasta)] de las ventas abiertas ahora."""
    salida = []
    for ts in anuncios(con, principal, ahora - MAX_S):
        fin = hasta(con, ts)
        if ts <= ahora < fin:
            salida.append((ts, fin))
    return salida
