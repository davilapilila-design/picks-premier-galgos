"""
Análisis puntual (pedido por el dueño el 2026-10-24), SOLO LECTURA en
Telegram (candado en modo "historico"). Lee con la cuenta del dueño:

1. La carpeta «ch ventas»: los canales de venta (desde el 22/07), el canal
   principal y el grupo «Picks Premier Galgos». Busca las apuestas de los
   canales de venta que NO están en el grupo de picks (seguimiento de
   apuestas del proyecto de picks: ese grupo es el que alimenta su hoja).
2. Los chats privados con clientes (los que tienen bienvenida apuntada):
   lo que escriben ellos y el dueño, por etapas (antes / después de la
   gratuita), para buscar patrones y mejorar las dudas frecuentes.

Lo escribe en pestañas «Análisis · …» de un Google Sheet que se le pasa
(con la cuenta de servicio). A los clientes no se les nombra: van como
C0001, C0002… No envía nada ni marca nada como leído.

    bash /opt/premier-captacion/lector.sh real analisis <id del Sheet>
"""
import asyncio
import logging
import re
import time
from datetime import date, datetime

from . import carpetas, db, sheet

log = logging.getLogger("captacion.analisis")

CARPETA = "ch venta"  # «CH Venta» en su Telegram (también vale «ch ventas»)
DESDE = date(2026, 7, 22)  # primer canal de venta («Premier Galgos Debut»)
MAX_TEXTO = 1000
MAX_MENSAJES_CHAT = 500
FILAS_POR_ENVIO = 4000
ESPERA_MAXIMA_S = 30 * 60

TAB_SIN_PICKS = "Análisis · Apuestas sin picks"
TAB_CANALES = "Análisis · Canales"
TAB_CHATS = "Análisis · Chats clientes"
TAB_TODAS = "Análisis · Todas las apuestas"

_RE_HORA = re.compile(r"(?<![\d.,])([01]?\d|2[0-3])\s*[:;h]\s*([0-5]\d)(?!\d)")
_RE_APUESTA = re.compile(r"cuota|ciota|stake|@\s*\d|gemela|trio")


# --- Apuestas en los canales ----------------------------------------------------

def horas(texto):
    """Horas de carrera («HH:MM») que aparecen en el texto, sin repetir."""
    return frozenset(f"{int(h):02d}:{m}" for h, m in _RE_HORA.findall(texto or ""))


def es_apuesta(texto):
    """Un mensaje de canal que parece una apuesta: lleva hora de carrera y
    cuota/stake (o es una gemela/trío)."""
    return bool(horas(texto)) and bool(_RE_APUESTA.search(carpetas.normalizar(texto)))


_RE_TRAP = re.compile(r"(?:(?<![\w.,])t|trap|galgo\s*t?)\s*([1-8])(?![\d.,])")
_RE_COMBINACION = re.compile(r"(?<![\d.,])([1-8])\s*[-/]\s*([1-8])(?![\d.,])")


def trampas(texto):
    """Números de trampa del texto («T5», «trap 5», o los de «3-4»/«3/4»)."""
    t = carpetas.normalizar(texto)
    numeros = set(_RE_TRAP.findall(t))
    for a, b in _RE_COMBINACION.findall(t):
        numeros |= {a, b}
    return frozenset(numeros)


def _texto_igual(texto):
    return " ".join(carpetas.normalizar(texto).split())


def en_grupo(a, picks, margen_dias=1):
    """Cómo está una apuesta de un canal en el grupo de picks:
    («reenviado» | «mismo texto» | «misma hora y galgo» | «no», el mensaje del
    grupo o None). «reenviado» y «mismo texto» = el mensaje exacto."""
    for p in picks:
        if p.get("reenvio") == (a["canal_id"], a["msg_id"]):
            return "reenviado", p
    cerca = [p for p in picks if abs((p["fecha"] - a["fecha"]).days) <= margen_dias]
    igual = _texto_igual(a["texto"])
    for p in cerca:
        if _texto_igual(p["texto"]) == igual:
            return "mismo texto", p
    clave = (horas(a["texto"]), trampas(a["texto"]))
    for p in cerca:
        if (horas(p["texto"]), trampas(p["texto"])) == clave:
            return "misma hora y galgo", p
    return "no", None


def emparejar(apuestas, picks, margen_dias=1):
    """Qué apuestas de los canales no están en el grupo de picks.

    `apuestas`: [{"canal_id", "msg_id", "fecha" (date), "texto"}];
    `picks`: [{"fecha", "texto", "reenvio": (canal_id, msg_id) o None}].
    Está si el grupo tiene ese mismo mensaje reenviado o, en un día cercano,
    un mensaje con el mismo texto o con las mismas horas de carrera y las
    mismas trampas. Un mismo mensaje del grupo vale para varias copias (el
    dueño a veces publica la misma apuesta en dos canales y reenvía una).
    """
    faltan = []
    for a in apuestas:
        if en_grupo(a, picks, margen_dias)[0] == "no":
            # Para revisarla a mano: lo del grupo de esos días a la misma hora, si hay algo.
            cerca = [p for p in picks if abs((p["fecha"] - a["fecha"]).days) <= margen_dias]
            parecido = next((p["texto"] for p in cerca if horas(p["texto"]) & horas(a["texto"])), "")
            faltan.append(dict(a, parecido=parecido))
    return faltan


# --- Datos de cada apuesta (formato de los canales del dueño) -------------------
# «14:37 Harlow / Galgo T5 Blundel Croia / Cuota 4.33🔥 / ⚠️Stake 3⚠️»; dobles
# con una línea «HH:MM Canódromo T2 Galgo» por carrera; gemelas «3-4 y 4-3».
_RE_CARRERA = re.compile(r"(?<![\d.,])([01]?\d|2[0-3])\s*[:;h]\s*([0-5]\d)(?!\d)\s*([A-Za-zÀ-ÿ' ]*)")
_RE_GALGO = re.compile(r"(?:\bgalgo\s*t?|\bt)\s*([1-8])\b\s*([A-Za-zÀ-ÿ'][A-Za-zÀ-ÿ' ]*)", re.I)
_RE_CUOTA = re.compile(r"(?:cuota|ciota|@)\s*:?\s*(\d+(?:[.,]\d+)?)", re.I)
_RE_STAKE = re.compile(r"stake\s*:?\s*(\d+(?:[.,]\d+)?)", re.I)


def datos_apuesta(texto):
    """Tipo, carreras («HH:MM Canódromo»), trampas y galgos, cuota y stake,
    tal y como vienen en el mensaje (vacío lo que no se reconozca)."""
    n = carpetas.normalizar(texto)
    carreras = []
    for linea in (texto or "").splitlines():
        for h, m, resto in _RE_CARRERA.findall(linea):
            canodromo = re.split(r"\b(?:galgo|cuota|stake|gemela|trio|tr[ií]o)\b", resto, flags=re.I)[0]
            canodromo = re.sub(r"\s*\bt\s*$", "", canodromo.strip(), flags=re.I)  # «Hove T2…» -> «Hove»
            if not canodromo:  # «Sheffield 17:59 …»: el canódromo va antes de la hora
                canodromo = re.split(r"\d", linea)[0].strip()
            carreras.append(f"{int(h):02d}:{m} {canodromo}".strip())
    galgos = [f"T{t} " + re.split(r"\b(?:cuota|ciota|stake)\b", nombre, flags=re.I)[0].strip()
              for t, nombre in _RE_GALGO.findall(texto or "")]
    if not galgos:  # gemelas y tríos: las combinaciones («3-4 y 4-3»)
        galgos = [f"{x}-{y}" for x, y in _RE_COMBINACION.findall(n)]
    if "gemela" in n:
        tipo = "gemela"
    elif "trio" in n:
        tipo = "trío"
    else:
        tipo = {1: "simple", 2: "doble", 3: "triple"}.get(len(set(carreras)), "otra")
    cuota = _RE_CUOTA.search(texto or "")
    stake = _RE_STAKE.search(texto or "")
    return {"tipo": tipo, "carreras": " | ".join(dict.fromkeys(carreras)), "galgos": " | ".join(galgos),
            "cuota": cuota.group(1).replace(",", ".") if cuota else "",
            "stake": stake.group(1).replace(",", ".") if stake else ""}


# --- Chats con clientes -----------------------------------------------------------

def etapa(ts, fila):
    if fila is None or fila["enlace_venta_ts"] is None:
        return "sin gratuita"
    return "antes de la gratuita" if ts < fila["enlace_venta_ts"] else "después de la gratuita"


def _texto(t):
    t = (t or "").strip()
    return t if len(t) <= MAX_TEXTO else t[:MAX_TEXTO] + "…"


def _fecha_hora(ts, tz):
    return datetime.fromtimestamp(ts, tz).strftime("%d/%m/%Y %H:%M")


# --- Lectura de Telegram ------------------------------------------------------------

def _solo_letras(texto):
    """«📊 CH. Ventas» -> «chventas»: sin emojis, espacios, puntos ni tildes."""
    return "".join(c for c in carpetas.normalizar(texto) if c.isalnum())


async def _carpeta(client, nombre):
    """(la carpeta de Telegram o None, títulos de todas las carpetas)."""
    from telethon.tl import functions

    res = await client(functions.messages.GetDialogFiltersRequest())
    titulos = []
    for f in getattr(res, "filters", res):
        titulo = getattr(getattr(f, "title", ""), "text", getattr(f, "title", "")) or ""
        if not hasattr(f, "id"):
            continue  # «Todos los chats»
        titulos.append(titulo)
        if _solo_letras(nombre) in _solo_letras(titulo):
            return f, titulos
    return None, titulos


def _id_peer(peer):
    return getattr(peer, "channel_id", None) or getattr(peer, "chat_id", None) or getattr(peer, "user_id", None)


async def chats_de_carpeta(client, carpeta):
    """Canales y grupos de una carpeta: los puestos a mano y, si la carpeta
    tiene marcado «Canales» o «Grupos», todos los de ese tipo (menos los
    excluidos). Las opciones de silenciados/leídos no se aplican: cambian
    a cada rato y se prefiere no dejarse ninguno."""
    from telethon.tl import types

    explicitos = list(getattr(carpeta, "pinned_peers", None) or []) + list(getattr(carpeta, "include_peers", None) or [])
    fuera = {_id_peer(p) for p in getattr(carpeta, "exclude_peers", None) or []}
    chats = {}
    for peer in explicitos:
        ent = await client.get_entity(peer)
        chats[ent.id] = ent
    canales, grupos = getattr(carpeta, "broadcasts", False), getattr(carpeta, "groups", False)
    if canales or grupos:
        async for d in client.iter_dialogs():
            e = d.entity
            if e.id in chats or e.id in fuera or (getattr(carpeta, "exclude_archived", False) and d.archived):
                continue
            es_canal = isinstance(e, types.Channel) and e.broadcast
            es_grupo = isinstance(e, types.Chat) or (isinstance(e, types.Channel) and e.megagroup)
            if (canales and es_canal) or (grupos and es_grupo):
                chats[e.id] = e
    return list(chats.values())


def _enlace(chat, msg_id):
    """Enlace al mensaje (abre en Telegram a quien está en el canal). Los
    grupos básicos no tienen."""
    from telethon.tl import types

    return f"https://t.me/c/{chat.id}/{msg_id}" if isinstance(chat, types.Channel) else ""


async def canales_de_venta(client, cfg):
    """(canales/grupos de venta de la carpeta «CH Venta», grupo de picks o None)."""
    from telethon.tl import types

    carpeta, titulos = await _carpeta(client, CARPETA)
    if carpeta is None:
        raise RuntimeError(f"No encuentro la carpeta «{CARPETA}». Tus carpetas: "
                           + ", ".join(f"«{t}»" for t in titulos))
    principal = carpetas.id_canal_puro(cfg.canal_id)
    canales, grupo = [], None
    peers = await chats_de_carpeta(client, carpeta)
    for ent in peers:
        if not isinstance(ent, (types.Channel, types.Chat)) or ent.id == principal:
            continue  # personas o bots metidos en la carpeta, y el canal principal
        if "picks" in carpetas.normalizar(ent.title) and not getattr(ent, "broadcast", False):
            grupo = ent
        else:
            # Los «canales» de venta pueden ser canales o grupos de Telegram.
            canales.append(ent)
    log.info("Carpeta «%s» (%s chats): %s canales/grupos de venta", CARPETA, len(peers), len(canales))
    return canales, grupo


async def leer_canales(client, cfg, tz):
    """(apuestas de los canales de venta, mensajes del grupo de picks, resumen por canal)."""
    desde = datetime(DESDE.year, DESDE.month, DESDE.day, tzinfo=tz)
    apuestas, picks = [], []
    canales, grupo = await canales_de_venta(client, cfg)
    if grupo is None:
        raise RuntimeError(f"No encuentro el grupo de picks en la carpeta «{CARPETA}»")

    async for m in client.iter_messages(grupo, offset_date=desde, reverse=True):
        reenvio = None
        fwd = getattr(m, "fwd_from", None)
        if fwd is not None and getattr(fwd, "channel_post", None):
            origen = getattr(fwd.from_id, "channel_id", None) if fwd.from_id else None
            reenvio = (origen, fwd.channel_post) if origen else None
        picks.append({"fecha": m.date.astimezone(tz).date(), "texto": m.message or "", "reenvio": reenvio,
                      "enlace": _enlace(grupo, m.id)})

    resumen = []
    for canal in canales:
        n = solo_foto = 0
        async for m in client.iter_messages(canal, offset_date=desde, reverse=True):
            texto = m.message or ""
            if es_apuesta(texto):
                n += 1
                apuestas.append({"canal": canal.title, "canal_id": canal.id, "msg_id": m.id,
                                 "fecha": m.date.astimezone(tz).date(), "hora": m.date.timestamp(),
                                 "texto": texto, "enlace": _enlace(canal, m.id)})
            elif m.photo and not texto.strip():
                solo_foto += 1
        resumen.append({"canal": canal.title, "id": canal.id, "apuestas": n, "solo_foto": solo_foto})
        log.info("Canal «%s»: %s apuestas, %s fotos sin texto", canal.title, n, solo_foto)
        await asyncio.sleep(0.3)
    return apuestas, picks, resumen


async def leer_chats(client, con, tz):
    """Filas (cliente, etapa, fecha, quién, texto) de los chats con clientes."""
    clientes = {f["user_id"]: f for f in con.execute("SELECT * FROM usuarios WHERE bienvenida_ts IS NOT NULL")}
    alias, filas, vistos = {}, [], 0
    async for dialogo in client.iter_dialogs():
        if not dialogo.is_user or dialogo.entity.id not in clientes:
            continue
        uid = dialogo.entity.id
        fila = clientes[uid]
        alias.setdefault(uid, f"C{len(alias) + 1:04d}")
        recurrente = "sí" if db.estado_oferta(con, uid, fila) == "recurrente" else ""
        mensajes = [m async for m in client.iter_messages(dialogo.entity, limit=MAX_MENSAJES_CHAT)]
        for m in reversed(mensajes):
            if not (m.message or "").strip():
                continue
            ts = m.date.timestamp()
            filas.append([alias[uid], etapa(ts, fila), recurrente, _fecha_hora(ts, tz),
                          "tú" if m.out else "cliente", _texto(m.message)])
        vistos += 1
        if vistos % 100 == 0:
            log.info("Chats de clientes leídos: %s de %s", vistos, len(clientes))
        await asyncio.sleep(0.3)
    log.info("Chats de clientes leídos: %s (%s mensajes con texto)", vistos, len(filas))
    return filas


# --- Escritura en el Sheet -----------------------------------------------------------

def _escribir(libro, nombre, cabecera, filas):
    """Vacía la pestaña y escribe las filas por tandas (Google limita el
    tamaño de cada envío)."""
    p = libro.pestana(nombre, [cabecera])
    p.reemplazar([], desde_fila=2)
    for i in range(0, len(filas), FILAS_POR_ENVIO):
        p.escribir(filas[i:i + FILAS_POR_ENVIO], desde_fila=2 + i)


def filas_todas(apuestas, picks, tz):
    filas = []
    for a in sorted(apuestas, key=lambda a: a["hora"]):
        d = datos_apuesta(a["texto"])
        estado, p = en_grupo(a, picks)
        filas.append([_fecha_hora(a["hora"], tz), a["canal"], a.get("enlace") or a["msg_id"], d["tipo"],
                      d["carreras"], d["galgos"], d["cuota"], d["stake"],
                      "sí" if estado in ("reenviado", "mismo texto") else ("parecido" if p else "no"),
                      estado, (p or {}).get("enlace", ""), _texto(a["texto"])])
    return filas


def filas_informe(apuestas, faltan, resumen, tz):
    faltan_ids = {(a["canal_id"], a["msg_id"]) for a in faltan}
    sin_picks = [[_fecha_hora(a["hora"], tz), a["canal"], a.get("enlace") or a["msg_id"], _texto(a["texto"]),
                  _texto(a.get("parecido", ""))] for a in faltan]
    canales = [[r["canal"], r["apuestas"],
                sum(1 for a in apuestas if a["canal_id"] == r["id"] and (a["canal_id"], a["msg_id"]) not in faltan_ids),
                sum(1 for a in faltan if a["canal_id"] == r["id"]), r["solo_foto"]] for r in resumen]
    return sin_picks, canales


async def ejecutar(cfg, entorno, sheet_id, crear_cliente, credenciales_api, solo_canales=False):
    api_id, api_hash, sesion = credenciales_api(entorno)
    credencial = sheet.ruta_credencial()
    if credencial is None:
        log.error("No encuentro la credencial de Google")
        return 2
    libro = sheet.abrir_libro(credencial, sheet_id)  # antes de leer: si falla el acceso, se ve ya
    libro.preparar()
    client = crear_cliente(sesion, api_id, api_hash, "historico")
    client.flood_sleep_threshold = ESPERA_MAXIMA_S
    con = db.abrir(cfg.db_path)
    await client.connect()
    try:
        if not await client.is_user_authorized():
            log.error("La cuenta no está conectada: el dueño tiene que ejecutar conectar-cuenta.sh")
            return 2
        inicio = time.time()
        apuestas, picks, resumen = await leer_canales(client, cfg, cfg.tz)
        faltan = emparejar(apuestas, picks)
        chats = None if solo_canales else await leer_chats(client, con, cfg.tz)
    finally:
        await client.disconnect()
        con.close()
    sin_picks, canales = filas_informe(apuestas, faltan, resumen, cfg.tz)
    _escribir(libro, TAB_SIN_PICKS, ["Fecha y hora", "Canal", "Enlace al mensaje", "Mensaje",
                                     "En el grupo esos días a la misma hora (para revisar)"], sin_picks)
    _escribir(libro, TAB_CANALES, ["Canal", "Apuestas detectadas", "En el grupo de picks", "No están",
                                   "Fotos sin texto (revisar a mano)"], canales)
    _escribir(libro, TAB_TODAS, ["Fecha y hora", "Canal", "Enlace al mensaje", "Tipo", "Carrera(s)", "Galgo(s)",
                                 "Cuota", "Stake", "Mensaje exacto en el grupo", "Cómo se ha encontrado",
                                 "Enlace en el grupo", "Mensaje"], filas_todas(apuestas, picks, cfg.tz))
    if chats is not None:
        _escribir(libro, TAB_CHATS, ["Cliente", "Etapa", "Estaba en el canal o volvió", "Fecha y hora", "Quién",
                                     "Mensaje"], chats)
    print(f"✓ Análisis hecho en {int(time.time() - inicio) // 60} min: {len(apuestas)} apuestas en "
          f"{len(canales)} canales, {len(faltan)} no están en el grupo de picks"
          + ("" if chats is None else f"; {len(chats)} mensajes de chats con clientes")
          + ". Está en las pestañas «Análisis · …» del Sheet.")
    return 0

