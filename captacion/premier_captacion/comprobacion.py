"""
Comprobación continua de cada correo frente a su persona de Telegram
(diseño del 2026-11-01, punto 3 bis; pedido por el dueño el 2026-11-02).

En cada sincronización del Sheet se mira cada compra de cada correo frente
a su persona (o, si no tiene, a su mejor candidata): buena, mala o sin
comprobar (cruce.Datos.juicio). Con eso, el estado del correo:
- «revisar» si sus 2 últimas compras comprobables son malas, si con
  MIN_COMPROBABLES o más las buenas bajan del 80 %, o si tuvo buenas pero
  ninguna en sus ULTIMAS últimas compras (p. ej. 2 buenas al principio y
  luego nada en 10 o 20 compras; sin ninguna buena es falta de datos, no
  algo raro). No pierde a su persona: lo mira el dueño.
- «vigilar» si tiene persona pero no llega a la regla del cruce (salvo las
  que dijo el dueño) o tiene alguna mala.
- «OK» el resto; «sin asignar» si no tiene persona.

Va a la pestaña «Correos · comprobación» (las de «revisar» arriba y en
rojo) y, al pasar a «revisar», el bot avisa al dueño (una vez por correo,
hasta que vuelva a estar en OK).
"""
import logging
import time

from . import cruce, db

log = logging.getLogger("captacion.comprobacion")

TAB = "Correos · comprobación"
CABECERA = ["Correo", "Usuario de Telegram", "ID de Telegram", "Compras", "Comprobables",
            "Buenas", "Malas", "Última buena", "Estado", "Motivo"]
OK, VIGILAR, REVISAR, SIN_ASIGNAR = "✅ OK", "👀 vigilar", "🔴 revisar", "— sin asignar"
ULTIMAS = 5
MIN_COMPROBABLES = 5
CLAVE_INICIO = "avisos_cruce_desde"  # en la tabla estado: desde cuándo se avisa
ROJO = {"backgroundColor": {"red": 0.96, "green": 0.8, "blue": 0.8}}
BLANCO = {"backgroundColor": {"red": 1, "green": 1, "blue": 1}}


def resumen_correo(juicios, origen):
    """juicios: [(pago_ts, BUENA|MALA|SIN)] en orden de compra; origen:
    manual / por_correo / por_nombre, o None si el correo no tiene persona."""
    buenas = sum(j == cruce.BUENA for _, j in juicios)
    malas = sum(j == cruce.MALA for _, j in juicios)
    r = {"compras": len(juicios), "comprobables": buenas + malas, "buenas": buenas, "malas": malas,
         "ultima_buena": max((ts for ts, j in juicios if j == cruce.BUENA and ts), default=None)}
    if origen is None:
        return dict(r, estado=SIN_ASIGNAR, motivo="")
    motivos = []
    comprobadas = [j for _, j in juicios if j != cruce.SIN]
    if comprobadas[-2:] == [cruce.MALA, cruce.MALA]:
        motivos.append("sus 2 últimas compras comprobables, sin entrar después de pagar")
    if r["comprobables"] >= MIN_COMPROBABLES and buenas < cruce.PROPORCION * r["comprobables"]:
        motivos.append(f"solo {buenas} buenas de {r['comprobables']} comprobables")
    if buenas and len(juicios) >= ULTIMAS and all(j != cruce.BUENA for _, j in juicios[-ULTIMAS:]):
        motivos.append(f"tuvo buenas, pero ninguna en sus últimas {ULTIMAS} compras")
    if motivos:
        return dict(r, estado=REVISAR, motivo="; ".join(motivos))
    if origen != "manual" and not cruce.cumple(buenas, r["comprobables"], 0):
        return dict(r, estado=VIGILAR, motivo=f"aún no llega a {cruce.MIN_BUENAS} buenas y el 80 %")
    if malas:
        return dict(r, estado=VIGILAR, motivo=f"{malas} mala{'s' if malas != 1 else ''}")
    return dict(r, estado=OK, motivo="")


def estados(calculo):
    """correo -> resumen_correo + user_id (su persona o su mejor candidata),
    origen y persona (nombre visible)."""
    from . import sheet
    salida = {}
    for correo in calculo.datos.correos():
        uid = calculo.persona_de(correo)
        origen = calculo.dueno[correo][1] if correo in calculo.dueno else None
        juicios = [(v["pago_ts"], calculo.datos.juicio(v, uid) if uid is not None else cruce.SIN)
                   for v in calculo.datos.ventas_de(correo)]
        p = calculo.personas.get(uid) or {}
        salida[correo] = dict(resumen_correo(juicios, origen), user_id=uid, origen=origen,
                              persona=sheet.nombre_visible(p.get("nombre"), p.get("username")))
    return salida


_ORDEN = {REVISAR: 0, VIGILAR: 1, SIN_ASIGNAR: 2, OK: 3}


def filas(estados_correo, tz):
    """Una fila por correo para la pestaña: «revisar» arriba, luego «vigilar»,
    «sin asignar» y OK; dentro, de más a menos compras."""
    from . import sheet
    salida = []
    for correo, e in sorted(estados_correo.items(), key=lambda x: (_ORDEN[x[1]["estado"]], -x[1]["compras"], x[0])):
        persona = e["persona"] or (str(e["user_id"]) if e["user_id"] is not None else "")
        if e["origen"] is None and persona:
            persona += " (candidata)"
        salida.append([correo, persona, e["user_id"] if e["user_id"] is not None else "", e["compras"],
                       e["comprobables"], e["buenas"], e["malas"],
                       sheet.serie_fecha_hora(e["ultima_buena"], tz) if e["ultima_buena"] else "",
                       e["estado"], e["motivo"]])
    return salida


def escribir_pestana(libro, filas_correo):
    from . import sheet
    p = libro.pestana(TAB, [CABECERA])
    p.reemplazar(filas_correo, desde_fila=2)
    rojas = sum(1 for f in filas_correo if f[8] == REVISAR)  # van todas arriba
    formatos = [("A2:J", BLANCO)]
    if rojas:
        formatos.append((f"A2:J{rojas + 1}", ROJO))
    formatos.append(("H2:H", sheet.FORMATO_FECHA_HORA))
    p.formatear(formatos)


def _texto_inicio(n):
    return (f"🔎 Comprobación de correos en marcha: {n} correo{'s' if n != 1 else ''} en «revisar». "
            f"Los tienes en rojo en la pestaña «{TAB}» del Sheet. A partir de ahora te aviso "
            f"de cada correo que caiga.")


def _texto_aviso(correo, e):
    return (f"🔴 Correo a revisar: {correo}\nPersona: {e['persona'] or e['user_id']}\n"
            f"Motivo: {e['motivo']}\nMíralo en la pestaña «{TAB}» del Sheet.")


def avisar_cambios(con, estados_correo, avisar, ahora=None):
    """Avisa al dueño (con `avisar(texto) -> bool`) de los correos que pasan a
    «revisar»: una vez por correo, hasta que vuelva a estar en OK. La primera
    vez, un solo mensaje con cuántos hay. Si un mensaje no sale, se intenta
    en la siguiente sincronización. Devuelve cuántos correos se avisaron."""
    if avisar is None:
        return 0
    ahora = int(time.time() if ahora is None else ahora)
    avisados = {f[0] for f in con.execute("SELECT correo FROM pagos_avisos")}
    with con:
        for correo in avisados:
            if estados_correo.get(correo, {}).get("estado") == OK:
                con.execute("DELETE FROM pagos_avisos WHERE correo = ?", (correo,))
    nuevos = sorted(c for c, e in estados_correo.items() if e["estado"] == REVISAR and c not in avisados)

    def marcar(correos):
        with con:
            con.executemany("INSERT OR IGNORE INTO pagos_avisos (correo, ts) VALUES (?, ?)",
                            [(c, ahora) for c in correos])

    if db.leer_estado(con, CLAVE_INICIO) is None:
        if nuevos and not avisar(_texto_inicio(len(nuevos))):
            return 0
        marcar(nuevos)
        with con:
            db.guardar_estado(con, CLAVE_INICIO, ahora)
        return len(nuevos)
    enviados = [c for c in nuevos if avisar(_texto_aviso(c, estados_correo[c]))]
    marcar(enviados)
    return len(enviados)


def aviso_por_bot(cfg, api=None):
    """avisar(texto) -> bool que manda el texto al dueño por el bot, o None
    si no hay bot o dueño configurados."""
    if not cfg.bot_token or cfg.propietario_id is None:
        return None
    from .telegram_api import BotAPI, ErrorRed, ErrorTelegram
    api = api or BotAPI(cfg.bot_token)

    def avisar(texto):
        try:
            api.llamar("sendMessage", chat_id=cfg.propietario_id, text=texto[:4000])
            return True
        except (ErrorTelegram, ErrorRed) as e:
            log.error("No se pudo enviar un aviso de la comprobación por el bot: %s", e)
            return False

    return avisar
