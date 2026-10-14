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

from . import db, mensajes
from .config import ErrorConfig, cargar_config
from .telegram_api import BotAPI, ErrorRed, ErrorTelegram

log = logging.getLogger("captacion.resumen")

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]

MOTIVOS = {
    "fuera_de_plazo": "llegaron con más de 5 min de espera (¿bot parado?)",
    "solicitud_ya_gestionada": "ya gestionadas a mano o retiradas",
}


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
        "aceptadas": 0,
        "sin_aceptar": Counter(),
        "escribieron_bot": set(),
    }
    for ev in eventos:
        tipo, d = ev["tipo"], ev["detalle"]
        if tipo == "solicitud":
            est["solicitudes"] += 1
            est["personas"].add(ev["user_id"])
            est["por_enlace"][d.get("enlace") or "(enlace desconocido)"] += 1
        elif tipo == "bienvenida_enviada":
            est["bienvenidas"] += 1
            est["por_tipo"][d.get("tipo_mensaje") or "?"] += 1
        elif tipo == "bienvenida_fallida":
            est["sin_bienvenida"][d.get("motivo") or "?"] += 1
        elif tipo == "ya_recibida":
            est["ya_recibida"] += 1
        elif tipo == "aceptada":
            est["aceptadas"] += 1
        elif tipo == "aceptacion_fallida":
            est["sin_aceptar"][d.get("motivo") or "?"] += 1
        elif tipo == "mensaje_al_bot":
            est["escribieron_bot"].add(ev["user_id"])
    return est


def _desglose(contador, traducir=None):
    return [
        f"   · {(traducir or {}).get(clave, clave)}: {n}"
        for clave, n in contador.most_common()
    ]


def _comparar(actual, anterior):
    if anterior == 0:
        return " (semana anterior: 0)" if actual else ""
    cambio = round((actual - anterior) * 100 / anterior)
    flecha = "↗️" if cambio > 0 else ("↘️" if cambio < 0 else "➡️")
    return f"  {flecha} {cambio:+d} % vs semana anterior ({anterior})"


def _personas(n):
    return f"{n} persona" if n == 1 else f"{n} personas"


def _num(est, clave):
    valor = est[clave]
    return len(valor) if isinstance(valor, set) else valor


def _cuerpo(est, anterior=None):
    def cmp(clave):
        return _comparar(_num(est, clave), _num(anterior, clave)) if anterior else ""

    lineas = []
    lineas.append(f"👥 Solicitudes: {est['solicitudes']} ({_personas(len(est['personas']))}){cmp('solicitudes')}")
    lineas += _desglose(est["por_enlace"])
    lineas.append(f"👋 Bienvenidas enviadas: {est['bienvenidas']}{cmp('bienvenidas')}")
    if anterior or len(est["por_tipo"]) > 1:
        lineas += _desglose(est["por_tipo"], mensajes.TIPOS_MENSAJE)
    if est["sin_bienvenida"]:
        lineas.append(f"⚠️ Sin bienvenida por algún problema: {sum(est['sin_bienvenida'].values())}")
        lineas += _desglose(est["sin_bienvenida"], MOTIVOS)
    lineas.append(f"🔁 Volvieron (ya tenían bienvenida): {est['ya_recibida']}")
    lineas.append(f"✅ Aceptadas: {est['aceptadas']}")
    if est["sin_aceptar"]:
        lineas.append(f"⚠️ Sin aceptar: {sum(est['sin_aceptar'].values())}")
        lineas += _desglose(est["sin_aceptar"], MOTIVOS)
    lineas.append(f"🤖 Escribieron al bot: {_personas(len(est['escribieron_bot']))}")
    return lineas


def texto_diario(con, tz, fecha, ahora_ts=None):
    """Resumen de `fecha`. Con `ahora_ts` dentro de ese día, lo que va de día."""
    desde = inicio_dia(fecha, tz)
    hasta = inicio_dia(fecha + timedelta(days=1), tz)
    nombre_dia = f"{DIAS[fecha.weekday()]} {fecha:%d.%m}"
    if ahora_ts is not None and ahora_ts < hasta:
        hasta = int(ahora_ts) + 1
        cabecera = f"📊 Hoy, {nombre_dia} (hasta las {datetime.fromtimestamp(ahora_ts, tz):%H:%M})"
    else:
        cabecera = f"📊 Resumen del {nombre_dia}"
    est = calcular(db.eventos_entre(con, desde, hasta))
    return "\n".join([cabecera, ""] + _cuerpo(est))


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
        cabecera = f"📅 Semana en curso, desde el lunes {lunes:%d.%m} (hasta ahora)"
    else:
        cabecera = f"📅 Resumen semanal: lunes {lunes:%d.%m} – domingo {domingo:%d.%m}"

    por_dia = Counter()
    for ev in eventos:
        if ev["tipo"] == "solicitud":
            por_dia[datetime.fromtimestamp(ev["ts"], tz).weekday()] += 1
    dias = " · ".join(f"{DIAS[i][:3]} {por_dia[i]}" for i in range(7))

    return "\n".join([cabecera, ""] + _cuerpo(est, anterior) + ["", f"📈 Solicitudes por día: {dias}"])


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

    if args.tipo == "diario":
        texto = texto_diario(con, tz, args.fecha or ayer(tz))
    else:
        hoy = ayer(tz) + timedelta(days=1)
        lunes = lunes_de(args.fecha) if args.fecha else lunes_de(hoy) - timedelta(days=7)
        texto = texto_semanal(con, tz, lunes)

    if args.imprimir:
        print(texto)
        return 0
    if cfg.propietario_id is None:
        log.error("CAPTACION_PROPIETARIO_ID vacío: no sé a quién enviar el resumen")
        return 1

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
