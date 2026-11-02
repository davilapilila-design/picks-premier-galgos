"""
Apuestas de cada canal de venta con su resultado (cuentas por cliente,
diseño del 2026-11-01, punto 1). Solo lectura.

- Las apuestas son los mensajes de los canales de venta que guarda el lector
  (publicaciones.py) y que parecen una apuesta (analisis.es_apuesta).
- Cada una se busca en el grupo de picks con la regla del análisis del
  24/10 (analisis.en_grupo: reenviada, mismo texto, o misma hora y galgo).
- Su resultado sale de la hoja de picks, que ya lo calcula con los
  resultados de Racing Post: pestañas `apuestas` y `apuestas_exoticas`, por
  `message_id` del grupo (`resultado_final`, `unidades_netas`). Las ocultas
  (descartadas por el dueño) y las que no están en el grupo no suman.
"""
import os
from collections import defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from . import analisis, db, publicaciones

# La hoja de picks (proyecto de picks; el id ya está en scripts/ del repo).
PICKS_SHEET_ID = os.environ.get("CAPTACION_PICKS_SHEET_ID") or "1axZnIIIXBpqVhhb6RVGawNaWpSLVLBwXK079MxcOfF4"
PESTANAS = {"apuestas": "stake", "apuestas_exoticas": "stake_total"}
GANO, PERDIO = "gano", "perdio"
HORA_CARRERAS = ZoneInfo("Europe/London")
YA_CORRIDA_S = 300  # una «apuesta» cuya carrera ya pasó al publicarla es un aviso o un resumen


def hora_carrera(a):
    """Cuándo empieza la (primera) carrera de una apuesta: la primera hora
    del mensaje ese día en hora de Reino Unido; si no hay, cuando se publicó."""
    horas = sorted(analisis.horas(a["texto"]))
    if not horas:
        return a["ts"]
    dia = datetime.fromtimestamp(a["ts"], HORA_CARRERAS).date()
    h, m = map(int, horas[0].split(":"))
    return datetime(dia.year, dia.month, dia.day, h, m, tzinfo=HORA_CARRERAS).timestamp()


def _num(x):
    if isinstance(x, bool) or x is None:
        return None
    if isinstance(x, (int, float)):
        return x
    try:
        v = float(str(x).strip().replace(",", "."))
    except ValueError:
        return None
    return int(v) if v.is_integer() else v


def _si(x):
    return x is True or str(x).strip().upper() in ("TRUE", "VERDADERO", "1")


def leer_picks(libro):
    """message_id del grupo de picks -> {resultado, unidades, stake, oculta}."""
    salida = {}
    for pestana, col_stake in PESTANAS.items():
        filas = libro.worksheet(pestana).get_all_values(value_render_option="UNFORMATTED_VALUE")
        if not filas:
            continue
        i = {c: n for n, c in enumerate(filas[0])}
        for f in filas[1:]:
            f = list(f) + [""] * (len(i) - len(f))
            mid = _num(f[i["message_id"]])
            if mid is None:
                continue
            salida[int(mid)] = {"resultado": str(f[i["resultado_final"]]).strip(),
                                "unidades": _num(f[i["unidades_netas"]]), "stake": _num(f[i[col_stake]]),
                                "oculta": _si(f[i["oculto"]])}
    return salida


def abrir_picks(ruta_credencial):
    import gspread

    return gspread.service_account(filename=ruta_credencial).open_by_key(PICKS_SHEET_ID)


def _buscador(mensajes_grupo):
    por_reenvio = {p["reenvio"]: p for p in mensajes_grupo if p["reenvio"]}
    por_dia = defaultdict(list)
    for p in mensajes_grupo:
        por_dia[p["fecha"]].append(p)

    def buscar(a):
        p = por_reenvio.get((a["canal_id"], a["msg_id"]))
        if p is not None:
            return "reenviado", p
        cerca = [p for d in (-1, 0, 1) for p in por_dia.get(a["fecha"] + timedelta(days=d), [])]
        return analisis.en_grupo(a, cerca)

    return buscar


def por_canal(con, picks, tz):
    """canal_id -> [apuesta] en orden, cada una con su resultado (None si no
    está en el grupo o en la hoja) y unidades (None si no suma)."""
    grupo = db.leer_estado(con, publicaciones.CLAVE_GRUPO)
    canales = {f[0] for f in con.execute("SELECT canal_id FROM ventas_canales")}
    mensajes_grupo = []
    if grupo is not None:
        for f in con.execute("SELECT msg_id, ts, texto, reenvio_chat, reenvio_msg FROM publicaciones "
                             "WHERE chat_id = ? ORDER BY ts, msg_id", (int(grupo),)):
            mensajes_grupo.append({"msg_id": f[0], "fecha": datetime.fromtimestamp(f[1], tz).date(),
                                   "texto": f[2] or "", "reenvio": (f[3], f[4]) if f[3] is not None else None})
    buscar = _buscador(mensajes_grupo)
    salida = defaultdict(list)
    for chat_id, msg_id, ts, texto in con.execute(
            "SELECT chat_id, msg_id, ts, texto FROM publicaciones ORDER BY chat_id, ts, msg_id"):
        if chat_id not in canales or not analisis.es_apuesta(texto):
            continue
        a = {"canal_id": chat_id, "msg_id": msg_id, "ts": ts, "texto": texto,
             "fecha": datetime.fromtimestamp(ts, tz).date()}
        if hora_carrera(a) < ts - YA_CORRIDA_S:
            continue
        estado, p = buscar(a)
        r = picks.get(p["msg_id"]) if p is not None else None
        suma = r is not None and not r["oculta"] and r["resultado"] in (GANO, PERDIO)
        salida[chat_id].append(dict(a, en_grupo=estado, resultado=r["resultado"] if r else None,
                                    unidades=r["unidades"] if suma else None,
                                    stake=r["stake"] if r else None, oculta=bool(r and r["oculta"])))
    return dict(salida)
