"""
Resúmenes que el bot envía al dueño por Telegram.

- Diario: cada noche a las 00:05 (hora de España), con el día anterior ya
  cerrado.
- Semanal: los lunes a las 9:00, con la semana anterior (lunes a domingo)
  comparada con la de antes.
Los lanzan los timers de systemd (deploy/) ejecutando este módulo; el dueño
también puede pedirlos al bot en cualquier momento con /resumen (hoy hasta
ahora) y /semana (semana en curso hasta ahora).

Todo sale de la tabla `eventos` (db.py). En la fase 1 solo hay datos del
bot (solicitudes, bienvenidas, aceptaciones, mensajes al bot); las líneas
de "te escribieron" y "free send" se añaden en la fase 3, cuando exista el
programa que lee la cuenta del dueño.

Los dos van contados con frases (pedido por el dueño el 2026-11-05):
primero los nuevos como un embudo (entraron, te escribieron, la gratuita,
los que no escribieron), luego el resto de quien te escribió, quién volvió,
las ventas de overoption (cruce.py) y, al final, el bot. El diario lleva los
nombres; el semanal, los números con la semana anterior al lado y solo los
nombres de quien espera la gratuita.

Uso manual (en la VM, con el mismo entorno que el servicio):
    python3 -m premier_captacion.resumen diario [--fecha AAAA-MM-DD] [--imprimir]
    python3 -m premier_captacion.resumen semanal [--fecha AAAA-MM-DD] [--imprimir]
"""
import argparse
import logging
import sys
import time
from collections import Counter
from datetime import date, datetime, time as hora, timedelta
from types import SimpleNamespace

from . import db, mensajes, textos
from .config import ErrorConfig, cargar_config
from .telegram_api import BotAPI, ErrorRed, ErrorTelegram

log = logging.getLogger("captacion.resumen")

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]

MOTIVOS = {
    "fuera_de_plazo": "llegaron con más de 5 min de espera (¿bot parado?)",
    "solicitud_ya_gestionada": "ya gestionadas a mano o retiradas",
    "Forbidden: bot was blocked by the user": "tenían el bot bloqueado",
}
MAX_NOMBRES = 10  # en cada frase del diario; el resto, «y N más»


def inicio_dia(fecha, tz):
    return int(datetime.combine(fecha, hora(0), tzinfo=tz).timestamp())


def calcular(eventos):
    est = {
        "solicitudes": 0,
        "personas": set(),
        "por_enlace": Counter(),
        "bienvenidas": 0,
        "por_tipo": Counter(),
        "sin_bienvenida": Counter(),
        "ya_recibida": 0,
        "volvieron": set(),  # quienes recibieron la bienvenida sin gratuita
        "aceptadas": 0,
        "sin_aceptar": Counter(),
        "escribieron_bot": set(),
        "te_escribieron": set(),
        "primera_vez": set(),  # te escribieron por primera vez
        "enlaces_venta": 0,
        "en_pausa": 0,
        "dudas": set(),
        "con_lector": False,
        "con_bienvenida": set(),
        "bloquearon": set(),
        "registrados": {},  # escribieron sin bienvenida -> cómo se les registró
        "fuera_canal": set(),  # te escribieron sin estar en el canal
        "venta_a": set(),  # a quién se le envió un enlace de venta
        "orden": {},  # user_id -> su primer evento (los nombres van por orden)
    }
    for ev in eventos:
        tipo, d = ev["tipo"], ev["detalle"]
        if ev["user_id"] is not None:
            est["orden"].setdefault(ev["user_id"], ev["ts"])
        if tipo == "solicitud":
            est["solicitudes"] += 1
            est["personas"].add(ev["user_id"])
            est["por_enlace"][d.get("enlace") or "(enlace desconocido)"] += 1
        elif tipo == "bienvenida_enviada":
            est["bienvenidas"] += 1
            est["por_tipo"][d.get("tipo_mensaje") or "?"] += 1
            est["con_bienvenida"].add(ev["user_id"])
        elif tipo == "bienvenida_fallida":
            est["sin_bienvenida"][d.get("motivo") or "?"] += 1
        elif tipo == "ya_recibida":
            est["ya_recibida"] += 1
            est["volvieron"].add(ev["user_id"])
        elif tipo == "aceptada":
            est["aceptadas"] += 1
        elif tipo == "aceptacion_fallida":
            est["sin_aceptar"][d.get("motivo") or "?"] += 1
        elif tipo == "mensaje_al_bot":
            est["escribieron_bot"].add(ev["user_id"])
        elif tipo == "solicitud_en_pausa":
            est["en_pausa"] += 1
        elif tipo == "faq":
            est["dudas"].add(ev["user_id"])
        elif tipo == "bloqueo_bot":
            est["bloquearon"].add(ev["user_id"])
        elif tipo == "desbloqueo_bot":
            est["bloquearon"].discard(ev["user_id"])
        # Fase 3 (lector de la cuenta del dueño). Lo que viene del histórico
        # (fase 4) tiene fechas pasadas y no cae en el día del resumen.
        elif tipo == "te_escribe":
            est["te_escribieron"].add(ev["user_id"])
            if d.get("primera_vez"):
                est["primera_vez"].add(ev["user_id"])
        elif tipo == "enlace_venta":
            est["enlaces_venta"] += 1
            est["venta_a"].add(ev["user_id"])
        elif tipo == "registrado_sin_bienvenida":
            est["registrados"][ev["user_id"]] = d.get("tipo_mensaje")
        elif tipo == "aviso_fuera_del_canal":
            est["fuera_canal"].add(ev["user_id"])
    return est


def _desglose(contador, traducir=None):
    return [
        f"   · {(traducir or {}).get(clave, clave)}: {n}"
        for clave, n in contador.most_common()
    ]


def _v(n, uno, varios):
    return uno if n == 1 else varios


def _y(partes):
    """«a, b y c»."""
    return partes[0] if len(partes) == 1 else ", ".join(partes[:-1]) + " y " + partes[-1]


def _nombre(con, uid):
    for tabla in ("usuarios", "personas_chat", "ventas_personas"):
        f = con.execute(f"SELECT nombre, username FROM {tabla} WHERE user_id = ?", (uid,)).fetchone()
        if f is not None and (f["nombre"] or f["username"]):
            return " ".join(p for p in (f["nombre"], f["username"] and f"@{f['username']}") if p)
    return f"id {uid}"


def _quienes(con, uids, orden, extra=None):
    """Sus nombres por orden de llegada; como mucho MAX_NOMBRES y «y N más»."""
    ids = sorted(uids, key=lambda u: (orden.get(u, 0), u))
    nombres = [_nombre(con, u) + (extra(u) if extra else "") for u in ids[:MAX_NOMBRES]]
    if len(ids) > MAX_NOMBRES:
        nombres.append(f"{len(ids) - MAX_NOMBRES} más")
    return _y(nombres)


def _euros(importe):
    texto = f"{importe:,.2f}".replace(",", " ").replace(".", ",").replace(" ", ".")
    return (texto[:-3] if texto.endswith(",00") else texto) + " €"


def _grupos(con, est, desde, hasta):
    """Quién es quién en el periodo: los nuevos y su embudo, y el resto de
    quien te escribió, por grupos (los usan el diario y el semanal)."""
    nuevos = est["personas"] - est["volvieron"]
    # La gratuita es el primer enlace de venta que se le envía a alguien.
    gratuita = {f[0] for f in con.execute(
        "SELECT user_id FROM usuarios WHERE enlace_venta_ts >= ? AND enlace_venta_ts < ?", (desde, hasta))}
    escribieron = est["te_escribieron"] & nuevos
    resto = nuevos - escribieron
    otros = (est["te_escribieron"] | est["fuera_canal"]) - nuevos
    fuera = est["fuera_canal"] & otros
    tipo = est["registrados"]
    sin_bot = {u for u in otros - fuera if tipo.get(u) == mensajes.TIPO_SIN_BOT}
    aprobados = {u for u in otros - fuera if tipo.get(u) == mensajes.TIPO_APROBADO_SIN_BIENVENIDA}
    primera = (est["primera_vez"] & otros) - fuera - sin_bot - aprobados
    return SimpleNamespace(
        nuevos=nuevos, con_bienvenida=est["con_bienvenida"] & nuevos, escribieron=escribieron,
        faltan=escribieron - gratuita, resto=resto, bloquearon=est["bloquearon"] & resto,
        dudas=est["dudas"] & nuevos, otros=otros, fuera=fuera, sin_bot=sin_bot, aprobados=aprobados,
        primera=primera, repiten=otros - fuera - sin_bot - aprobados - primera,
        gratuita_otros=gratuita - nuevos, venta_repetida=est["venta_a"] - gratuita,
        volvieron=est["volvieron"] & est["personas"])


def _cruzadas(con):
    """Las ventas de overoption con su persona (cruce.py), o None si aún no
    se leen o si el cruce falla (el resumen sale igual, sin ellas)."""
    if con.execute("SELECT 1 FROM pagos_overoption LIMIT 1").fetchone() is None:
        return None
    try:
        from . import cruce
        return cruce.calcular(con).resultados
    except Exception:
        log.exception("No se pudo cruzar las ventas para el resumen")
        return None


def _compras(resultados):
    """user_id -> cuántas compras suyas se conocen."""
    return Counter(r["user_id"] for r in resultados or () if r["user_id"] is not None)


def _ventas(con, tz, resultados, desde, hasta, de="del día", antes=None):
    """Las ventas de overoption del periodo y si se sabe de quién son, con las
    del periodo `antes` (desde, hasta) para comparar."""
    if resultados is None:
        return []
    leido = con.execute("SELECT MAX(bajado_ts) FROM pagos_overoption").fetchone()[0]

    def entre(a, b):
        return [r for r in resultados if a <= (r["pago_ts"] or 0) < b]

    def cuantas(ventas):
        return f"{len(ventas)}, {_euros(sum(r['importe'] or 0 for r in ventas))}" if ventas else "ninguna"

    ventas = entre(desde, hasta)
    texto = f"💶 Ventas {de}: {cuantas(ventas)}"
    if leido < hasta:
        cuando = datetime.fromtimestamp(leido, tz)
        texto += (f" (leídas hasta las {cuando:%H:%M})" if leido >= desde and hasta - desde <= 25 * 3600
                  else f" (leídas hasta el {cuando:%d/%m a las %H:%M})")
    texto += "."
    con_persona = sum(r["user_id"] is not None for r in ventas)
    dudosas = sum(r["estado_cruce"] == "dudosa_varios" for r in ventas)
    sin = len(ventas) - con_persona - dudosas
    partes = []
    if con_persona:
        partes.append(f"Sabemos de quién {_v(con_persona, 'es', 'son')} {con_persona}")
    if dudosas:
        partes.append(f"{dudosas} {_v(dudosas, 'está dudosa', 'están dudosas')}")
    if sin:
        partes.append(f"{sin} sin identificar")
    if partes:
        texto += " " + "; ".join(partes) + "."
    if antes is not None:
        texto += f" La semana anterior: {cuantas(entre(*antes))}."
    return ["", texto]


def _bot(est, nombres_tipo):
    """Cómo fue el bot: lo normal, en una línea; el detalle, solo si hubo algo."""
    lineas = []
    if len(est["por_enlace"]) > 1:
        lineas.append("🔗 Por qué enlace entraron: "
                      + " · ".join(f"«{enlace}» {k}" for enlace, k in est["por_enlace"].most_common()))
    versiones = Counter({t: k for t, k in est["por_tipo"].items() if t != mensajes.TIPO_BIENVENIDA_RECURRENTE})
    if len(versiones) > 1:
        lineas.append("🧪 Versiones de la bienvenida:")
        lineas += _desglose(versiones, nombres_tipo)
    if est["escribieron_bot"]:
        b = len(est["escribieron_bot"])
        lineas.append(f"🤖 {b} {_v(b, 'persona escribió', 'personas escribieron')} al bot en vez de a ti.")
    if est["sin_bienvenida"]:
        lineas.append(f"⚠️ Sin bienvenida por algún problema: {sum(est['sin_bienvenida'].values())}")
        lineas += _desglose(est["sin_bienvenida"], MOTIVOS)
    if est["en_pausa"]:
        lineas.append(f"⏸️ Sin atender por la pausa (para aceptar a mano): {est['en_pausa']}")
    if est["sin_aceptar"]:
        lineas.append(f"⚠️ Sin aceptar: {sum(est['sin_aceptar'].values())}")
        lineas += _desglose(est["sin_aceptar"], MOTIVOS)
    a, s = est["aceptadas"], est["solicitudes"]
    if s:
        if est["sin_aceptar"] or est["en_pausa"] or a < s:
            lineas.append(f"✅ El bot aceptó {a} de {s} solicitudes.")
        else:
            lineas.append(_v(s, "✅ El bot aceptó la solicitud", f"✅ El bot aceptó las {s} solicitudes")
                          + ("." if est["sin_bienvenida"] else ", sin fallos."))
    return [""] + lineas if lineas else []


def _entraron(g):
    n, con_b = len(g.nuevos), len(g.con_bienvenida)
    if not n:
        return "🆕 No entró nadie nuevo."
    if n == 1:
        return "🆕 Entró 1 persona nueva. " + ("El bot le mandó la bienvenida con la gratuita." if con_b
                                              else "No recibió la bienvenida del bot.")
    a_quien = "a todas" if con_b == n else f"a {con_b} de ellas"
    return f"🆕 Entraron {n} personas nuevas. " + (f"El bot les mandó {a_quien} la bienvenida con la gratuita."
                                                   if con_b else "Ninguna recibió la bienvenida del bot.")


def _gratuita(g, quienes):
    """Si les enviaste la gratuita a los nuevos que te escribieron (y a quién falta)."""
    k, f = len(g.escribieron), len(g.faltan)
    if not f:
        return "🎁 Ya le enviaste la gratuita." if k == 1 else "🎁 A todas les enviaste la gratuita."
    if f == k:
        return "🎁 Todavía no le has enviado la gratuita." if k == 1 else \
            f"🎁 A ninguna de las {k} le has enviado todavía la gratuita."
    return f"🎁 Les enviaste la gratuita a {k - f} de las {k}. {_v(f, 'Falta', 'Faltan')}: {quienes(g.faltan)}."


def _sin_escribir(g, con_nombres, quienes, comparacion=""):
    """Los nuevos que no te escribieron y cuántos de ellos bloquearon el bot."""
    n, k, r = len(g.nuevos), len(g.escribieron), len(g.resto)
    if not k:
        texto = ("😶 Todavía no te ha escrito" if n == 1 else "😶 Ninguna te ha escrito todavía") + comparacion + "."
    else:
        texto = "😶 La otra no te ha escrito." if r == 1 else f"😶 Las otras {r} no te han escrito."
    if g.bloquearon:
        b = len(g.bloquearon)
        verbo = _v(b, "bloqueó", "bloquearon")
        texto += (f" {verbo.capitalize()}" if r == 1 else f" {b} de ellas {verbo}") + " el bot"
        texto += (f": {quienes(g.bloquearon)} ({_v(b, 'sigue', 'siguen')} en el canal, pero el bot ya no puede "
                  f"{_v(b, 'escribirle', 'escribirles')})." if con_nombres else ".")
    return texto


def _dudas(g, con_lector):
    n, d = len(g.nuevos), len(g.dudas)
    texto = ("📚 Miró las preguntas frecuentes del bot." if n == 1 else
             f"📚 {d} de las {n} {_v(d, 'miró', 'miraron')} las preguntas frecuentes del bot.")
    x = len(g.dudas & g.escribieron)
    if con_lector and x:
        texto += " Y te escribió." if d == 1 else f" {x} de ellas te {_v(x, 'escribió', 'escribieron')}."
    return texto


def _cuerpo_diario(con, est, tz, desde, hasta, nombres_tipo):
    """El día contado con frases y con nombres, para saber quién es quién."""
    g = _grupos(con, est, desde, hasta)
    resultados = _cruzadas(con)
    compras = _compras(resultados)

    def quienes(uids, extra=None):
        return _quienes(con, uids, est["orden"], extra)

    def entro(uid):
        f = db.obtener_usuario(con, uid)
        cuando = f and (f["bienvenida_ts"] or f["primera_solicitud_ts"])
        return f" (entró el {datetime.fromtimestamp(cuando, tz):%d/%m})" if cuando else ""

    n = len(g.nuevos)
    lineas = [_entraron(g)]
    if est["con_lector"] and n:
        lineas.append("")
        k = len(g.escribieron)
        if k:
            lineas.append("✉️ Te escribió por privado." if n == 1 else
                          f"✉️ {k} de esas {n} te {_v(k, 'escribió', 'escribieron')} por privado "
                          f"({round(k * 100 / n)} %): {quienes(g.escribieron)}.")
            lineas.append(_gratuita(g, quienes))
        if g.resto:
            lineas.append(_sin_escribir(g, True, quienes))
    if g.dudas:
        lineas += ["", _dudas(g, est["con_lector"])]

    if est["con_lector"]:
        bloque = []
        if g.otros:
            o = len(g.otros)
            bloque.append("💬 También te " + _v(o, "escribió 1 persona que no es nueva:",
                                                 f"escribieron {o} personas que no son nuevas:"))
            if g.primera:
                bloque.append(f"· {quienes(g.primera, entro)}, que te {_v(len(g.primera), 'escribe', 'escriben')} "
                              "por primera vez.")
            # Quien no pasó por el bot suele ser un cliente de antes del bot.
            clientes = {u for u in g.sin_bot if compras[u]}
            if clientes:
                c = len(clientes)
                bloque.append(f"· {quienes(clientes, lambda u: f' ({compras[u]} {_v(compras[u], 'compra', 'compras')})')}"
                              f", que ya {_v(c, 'es cliente', 'son clientes')} y no {_v(c, 'pasó', 'pasaron')} por el "
                              f"bot: no {_v(c, 'tiene', 'tienen')} gratuita, {_v(c, 'va', 'van')} a free send.")
            if g.sin_bot - clientes:
                s = len(g.sin_bot - clientes)
                bloque.append(f"· {quienes(g.sin_bot - clientes)}, que {_v(s, 'entró', 'entraron')} al canal sin pasar "
                              f"por el bot: no {_v(s, 'tiene', 'tienen')} gratuita, {_v(s, 'va', 'van')} a free send.")
            if g.aprobados:
                s = len(g.aprobados)
                bloque.append(f"· {quienes(g.aprobados)}, que {_v(s, 'pidió', 'pidieron')} entrar pero no "
                              f"{_v(s, 'le', 'les')} llegó la bienvenida: sí {_v(s, 'tiene', 'tienen')} gratuita, "
                              f"{_v(s, 'va', 'van')} a la carpeta del día.")
            if g.fuera:
                s = len(g.fuera)
                bloque.append(f"· {quienes(g.fuera)}, que no {_v(s, 'está', 'están')} en el canal: te avisé con el "
                              f"enlace para que {_v(s, 'entre', 'entren')}.")
            if g.repiten:
                s = len(g.repiten)
                tuvieron = sum(1 for u in g.repiten
                               if (f := db.obtener_usuario(con, u)) is not None and f["enlace_venta_ts"] is not None)
                texto = f"· {s} que ya te {_v(s, 'había', 'habían')} escrito otras veces"
                if tuvieron == s:
                    texto += f" y ya {_v(s, 'tuvo', 'tuvieron')} su gratuita."
                elif tuvieron:
                    texto += f" ({tuvieron} ya {_v(tuvieron, 'tuvo', 'tuvieron')} su gratuita)."
                else:
                    texto += "."
                bloque.append(texto)
        if g.gratuita_otros:
            bloque.append(f"🎁 También enviaste la gratuita a {quienes(g.gratuita_otros)} "
                          f"(no {_v(len(g.gratuita_otros), 'era nueva', 'eran nuevas')}).")
        if g.venta_repetida:
            bloque.append(f"🔗 También enviaste enlaces de venta a {quienes(g.venta_repetida)}, que ya "
                          f"{_v(len(g.venta_repetida), 'había', 'habían')} tenido la gratuita.")
        if bloque:
            lineas += [""] + bloque

    if g.volvieron:
        v = len(g.volvieron)
        lineas += ["", f"↩️ {v} {_v(v, 'persona volvió', 'personas volvieron')} a entrar al canal "
                       f"({quienes(g.volvieron)}): sin gratuita, porque ya {_v(v, 'estaba', 'estaban')} "
                       f"o ya {_v(v, 'había', 'habían')} pasado por aquí."]
    return lineas + _ventas(con, tz, resultados, desde, hasta) + _bot(est, nombres_tipo)


def _cuerpo_semanal(con, est, anterior, tz, lunes, periodo, periodo_antes, nombres_tipo, eventos):
    """La semana con los mismos grupos que el diario, en números y con la
    semana anterior al lado; con nombres, solo quien espera la gratuita."""
    g = _grupos(con, est, *periodo)
    a = _grupos(con, anterior, *periodo_antes)
    resultados = _cruzadas(con)
    compras = _compras(resultados)

    def quienes(uids):
        return _quienes(con, uids, est["orden"])

    n, na = len(g.nuevos), len(a.nuevos)
    antes = f" (semana anterior: {na})"
    lineas = [("🆕 No entró nadie nuevo" if not n else _v(n, "🆕 Entró 1 persona nueva", f"🆕 Entraron {n} personas nuevas"))
              + antes + "."]
    if est["con_lector"] and n:
        lineas.append("")
        k, ka = len(g.escribieron), len(a.escribieron)
        comparacion = f"semana anterior: {ka} de {na}" if na else "semana anterior: 0"
        if k:
            lineas.append(f"✉️ Te escribió por privado ({comparacion})." if n == 1 else
                          f"✉️ {k} de las {n} te {_v(k, 'escribió', 'escribieron')} por privado "
                          f"({round(k * 100 / n)} %; {comparacion}).")
            texto = _gratuita(g, quienes)
            if len(g.faltan) == len(g.escribieron):  # los nombres de quien la espera
                texto = texto[:-1] + f": {quienes(g.faltan)}."
            lineas.append(texto)
        if g.resto:
            lineas.append(_sin_escribir(g, False, quienes, f" ({comparacion})"))
    if g.dudas:
        lineas += ["", _dudas(g, est["con_lector"])]

    if est["con_lector"]:
        bloque = []
        if g.otros:
            o = len(g.otros)
            bloque.append("💬 También te " + _v(o, "escribió 1 persona que no es nueva de esta semana:",
                                                 f"escribieron {o} personas que no son nuevas de esta semana:"))
            if g.primera:
                bloque.append(f"· {len(g.primera)} por primera vez.")
            c = sum(1 for u in g.sin_bot if compras[u])
            if c:
                bloque.append(f"· {c} que ya {_v(c, 'es cliente', 'son clientes')} y no {_v(c, 'pasó', 'pasaron')} "
                              f"por el bot: no {_v(c, 'tiene', 'tienen')} gratuita.")
            if len(g.sin_bot) - c:
                s = len(g.sin_bot) - c
                bloque.append(f"· {s} que {_v(s, 'entró', 'entraron')} al canal sin pasar por el bot: "
                              f"no {_v(s, 'tiene', 'tienen')} gratuita.")
            if g.aprobados:
                s = len(g.aprobados)
                bloque.append(f"· {s} que {_v(s, 'pidió', 'pidieron')} entrar pero no {_v(s, 'le', 'les')} llegó "
                              f"la bienvenida: sí {_v(s, 'tiene', 'tienen')} gratuita.")
            if g.fuera:
                s = len(g.fuera)
                bloque.append(f"· {s} que no {_v(s, 'está', 'están')} en el canal (te avisé con el enlace).")
            if g.repiten:
                s = len(g.repiten)
                bloque.append(f"· {s} que ya te {_v(s, 'había', 'habían')} escrito otras veces.")
        if g.gratuita_otros:
            x = len(g.gratuita_otros)
            bloque.append(f"🎁 También enviaste la gratuita a {x} que no {_v(x, 'era nueva', 'eran nuevas')} "
                          "de esta semana.")
        if g.venta_repetida:
            x = len(g.venta_repetida)
            bloque.append(f"🔗 También enviaste enlaces de venta a {x} que ya {_v(x, 'había', 'habían')} "
                          "tenido la gratuita.")
        if bloque:
            lineas += [""] + bloque

    if g.volvieron:
        v = len(g.volvieron)
        lineas += ["", f"↩️ {v} {_v(v, 'persona volvió', 'personas volvieron')} a entrar al canal: sin gratuita."]
    lineas += _ventas(con, tz, resultados, *periodo, de="de la semana", antes=periodo_antes)

    primera_solicitud = {}
    for ev in eventos:
        if ev["tipo"] == "solicitud" and ev["user_id"] in g.nuevos:
            primera_solicitud.setdefault(ev["user_id"], ev["ts"])
    por_dia = Counter(datetime.fromtimestamp(t, tz).weekday() for t in primera_solicitud.values())
    dias = min(7, (datetime.fromtimestamp(periodo[1] - 1, tz).date() - lunes).days + 1)
    lineas += ["", "📈 Nuevos por día: " + " · ".join(f"{DIAS[i][:3]} {por_dia[i]}" for i in range(dias))]
    return lineas + _bot(est, nombres_tipo)


def _nombres_tipo(con, tz, *estadisticas):
    """Nombre de cada tipo de bienvenida, también de las versiones creadas
    desde el bot (/textos), para el desglose."""
    tipos = {t for est in estadisticas if est is not None for t in est["por_tipo"]}
    return {t: textos.descripcion_tipo(con, t, tz) for t in tipos}


def _recordatorio_pausa(con, tz):
    """Si el bot sigue en pausa (/pausar), se recuerda al final del resumen."""
    pausa = db.pausa_desde(con)
    if pausa is None:
        return []
    return ["", f"⏸️ El bot sigue EN PAUSA desde las {datetime.fromtimestamp(pausa, tz):%H:%M del %d.%m}: "
                "no acepta a nadie (simulación). Escríbele /arrancar para que actúe."]


def _marcar_lector(con, *estadisticas):
    # Las líneas del lector solo salen cuando el lector está funcionando
    # (si no, "0 te escribieron" confundiría).
    activo = con.execute(
        "SELECT 1 FROM eventos WHERE tipo IN ('te_escribe', 'enlace_venta', 'carpeta') LIMIT 1").fetchone()
    for est in estadisticas:
        if est is not None:
            est["con_lector"] = activo is not None


def texto_diario(con, tz, fecha, ahora_ts=None):
    """Resumen de `fecha`. Con `ahora_ts` dentro de ese día, lo que va de día."""
    desde = inicio_dia(fecha, tz)
    hasta = inicio_dia(fecha + timedelta(days=1), tz)
    nombre_dia = f"{DIAS[fecha.weekday()]} {fecha:%d/%m}"
    if ahora_ts is not None and ahora_ts < hasta:
        hasta = int(ahora_ts) + 1
        cabecera = f"📊 Hoy, {nombre_dia} (hasta las {datetime.fromtimestamp(ahora_ts, tz):%H:%M})"
    else:
        cabecera = f"📊 {nombre_dia.capitalize()}"
    est = calcular(db.eventos_entre(con, desde, hasta))
    _marcar_lector(con, est)
    return "\n".join([cabecera, ""] + _cuerpo_diario(con, est, tz, desde, hasta, _nombres_tipo(con, tz, est))
                     + _recordatorio_pausa(con, tz))


def texto_semanal(con, tz, lunes, ahora_ts=None):
    """Resumen de la semana que empieza en `lunes`, comparada con la anterior."""
    assert lunes.weekday() == 0
    desde = inicio_dia(lunes, tz)
    hasta = inicio_dia(lunes + timedelta(days=7), tz)
    domingo = lunes + timedelta(days=6)
    parcial = ahora_ts is not None and ahora_ts < hasta
    if parcial:
        hasta = int(ahora_ts) + 1
    eventos = db.eventos_entre(con, desde, hasta)
    est = calcular(eventos)
    # La semana anterior se compara en el mismo tramo (si la actual va por
    # el miércoles a mediodía, se compara con lunes-miércoles a mediodía).
    duracion = hasta - desde
    desde_ant = inicio_dia(lunes - timedelta(days=7), tz)
    anterior = calcular(db.eventos_entre(con, desde_ant, desde_ant + duracion))

    if parcial:
        cabecera = [f"📅 Semana en curso, desde el lunes {lunes:%d/%m} (hasta ahora)",
                    "Comparada con la semana anterior hasta el mismo momento."]
    else:
        cabecera = [f"📅 Semana del lunes {lunes:%d/%m} al domingo {domingo:%d/%m}"]
    _marcar_lector(con, est, anterior)
    cuerpo = _cuerpo_semanal(con, est, anterior, tz, lunes, (desde, hasta), (desde_ant, desde_ant + duracion),
                             _nombres_tipo(con, tz, est), eventos)
    return "\n".join(cabecera + [""] + cuerpo + _recordatorio_pausa(con, tz))


def ayer(tz, ahora_ts=None):
    return datetime.fromtimestamp(ahora_ts or time.time(), tz).date() - timedelta(days=1)


def lunes_de(fecha):
    return fecha - timedelta(days=fecha.weekday())


def main(argv=None):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Envía el resumen diario o semanal al dueño.")
    parser.add_argument("tipo", choices=["diario", "semanal"])
    parser.add_argument("--fecha", type=date.fromisoformat,
                        help="AAAA-MM-DD. Diario: ese día (por defecto ayer). "
                             "Semanal: la semana que contiene ese día (por defecto la semana pasada).")
    parser.add_argument("--imprimir", action="store_true", help="Solo mostrarlo aquí, sin enviarlo.")
    args = parser.parse_args(argv)

    try:
        cfg = cargar_config()
    except ErrorConfig as e:
        log.error("Configuración incorrecta: %s", e)
        return 2
    con = db.abrir(cfg.db_path)
    tz = cfg.tz
    try:
        if args.tipo == "diario":
            texto = texto_diario(con, tz, args.fecha or ayer(tz))
        else:
            hoy = ayer(tz) + timedelta(days=1)
            lunes = lunes_de(args.fecha) if args.fecha else lunes_de(hoy) - timedelta(days=7)
            texto = texto_semanal(con, tz, lunes)
    finally:
        con.close()

    if args.imprimir:
        print(texto)
        return 0
    if cfg.propietario_id is None:
        # Pasa durante la puesta en marcha (los timers ya están activos).
        log.warning("CAPTACION_PROPIETARIO_ID vacío: no hay a quién enviar el resumen, se omite")
        return 0

    api = BotAPI(cfg.bot_token)
    for intento in range(3):
        try:
            api.llamar("sendMessage", chat_id=cfg.propietario_id, text=texto)
            log.info("Resumen %s enviado", args.tipo)
            return 0
        except ErrorRed as e:
            log.warning("Red caída enviando el resumen (intento %d): %s", intento + 1, e)
            time.sleep(30)
        except ErrorTelegram as e:
            log.error("Telegram no aceptó el resumen: %s", e)
            return 1
    return 1


if __name__ == "__main__":
    sys.exit(main())
