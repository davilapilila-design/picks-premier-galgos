"""
Ventas de overoption (overoption.io), SOLO LECTURA, para saber quién ha
pagado cada canal de venta.

Pedido por el dueño el 2026-10-29. overoption no tiene botón de exportar,
pero su web usa una API JSON (api.overoption.io) que, con la sesión del
dueño, devuelve todas sus transacciones. Este módulo entra con sus
credenciales (correo + contraseña), baja las ventas y las guarda en la base
de datos local. NUNCA cambia, crea ni borra nada en overoption.

De cada venta interesa: correo del comprador, fecha y hora exactas, producto
(nombre del canal), importe, moneda, lo recibido (neto) y el método. Además,
cada producto (content_uid) permite consultar el enlace de Telegram del canal
(final_content), que es la llave para cruzar la venta con la entrada al canal
(ver el cruce en ventas.py / el Sheet).

Seguridad:
- Las credenciales NO van en el repo (público) ni en el chat: viven en la VM
  en /etc/premier-captacion/overoption.env (solo root), y systemd se las pasa
  al servicio por el entorno (OVEROPTION_EMAIL / OVEROPTION_PASSWORD).
- La base de datos de la VM (con correos de clientes) tampoco está en el repo.

Uso en la VM (normalmente lo lanza captacion-pagos@<instancia>.timer):
    systemctl start captacion-pagos@real
"""
from __future__ import annotations

import html
import json
import logging
import os
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone

from . import db

log = logging.getLogger("captacion.pagos")

VENTANA_S = 180  # hasta 3 min después del pago para entrar al canal
ANTES_S = 30  # margen por si los relojes de overoption y Telegram no van iguales

BASE = "https://api.overoption.io"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
# Las condiciones de overoption no prohíben leer la propia cuenta por
# programa, pero conviene ir suave: una descarga cada varias horas.
TIMEOUT_S = 60


# --- Normalización (puro, testeable) ------------------------------------------------

def _parsear_fecha(iso):
    """'2026-10-28T17:46:12.202Z' -> epoch UTC (int). None/'' -> None."""
    if not iso:
        return None
    texto = str(iso).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(texto)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def _decodificar(texto):
    """Deshace las entidades HTML ('Mi&#233;rcoles' -> 'Miércoles')."""
    return html.unescape(texto or "")


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def normalizar_venta(tx, enlace=None):
    """Una transacción de overoption -> fila para pagos_overoption.

    `enlace` es el enlace de Telegram del canal (se resuelve aparte por
    content_uid); puede ser None si aún no se conoce."""
    meta = tx.get("metadata") or {}
    producto = _decodificar(meta.get("product_title") or meta.get("content_title")
                            or tx.get("content_title") or "")
    neto = tx.get("net_amount_eur")
    if neto is None:
        neto = tx.get("net_amount")
    return {
        "id": tx.get("_id"),
        "content_uid": tx.get("content_uid"),
        "portal_uid": tx.get("portal_uid"),
        "producto": producto,
        "enlace": enlace,
        "correo": tx.get("customer_email"),
        "importe": _num(tx.get("amount")),
        "moneda": tx.get("currency"),
        "neto": _num(neto),
        "comision": _num(meta.get("commission_amount")),
        "metodo": tx.get("payment_method_type"),
        "estado": tx.get("payment_status"),
        "es_propina": 1 if tx.get("is_tip") else 0,
        "descuento_codigo": (meta.get("discount_code") or "").strip() or None,
        "descuento_importe": _num(meta.get("discountAmount")),
        "pago_ts": _parsear_fecha(tx.get("payment_date")),
    }


# --- Base de datos ------------------------------------------------------------------

_COLS = ["id", "content_uid", "portal_uid", "producto", "enlace", "correo", "importe",
         "moneda", "neto", "comision", "metodo", "estado", "es_propina",
         "descuento_codigo", "descuento_importe", "pago_ts"]


def guardar_ventas(con, ventas, ahora=None):
    """Inserta o actualiza cada venta por su id (no duplica)."""
    ahora = int(time.time() if ahora is None else ahora)
    filas = [tuple(v.get(c) for c in _COLS) + (ahora,) for v in ventas if v.get("id")]
    if not filas:
        return 0
    marcas = ", ".join(["?"] * (len(_COLS) + 1))
    set_ = ", ".join(f"{c} = excluded.{c}" for c in _COLS[1:]) + ", bajado_ts = excluded.bajado_ts"
    con.execute("BEGIN")
    con.executemany(
        f"INSERT INTO pagos_overoption ({', '.join(_COLS)}, bajado_ts) VALUES ({marcas}) "
        f"ON CONFLICT (id) DO UPDATE SET {set_}", filas)
    con.commit()
    return len(filas)


def enlace_en_cache(con, content_uid):
    fila = con.execute("SELECT enlace FROM pagos_contenidos WHERE content_uid = ?",
                       (content_uid,)).fetchone()
    return fila["enlace"] if fila else None


def guardar_contenido(con, content_uid, enlace, titulo, ahora=None):
    ahora = int(time.time() if ahora is None else ahora)
    con.execute(
        "INSERT INTO pagos_contenidos (content_uid, enlace, titulo, visto_ts) VALUES (?, ?, ?, ?) "
        "ON CONFLICT (content_uid) DO UPDATE SET enlace = excluded.enlace, "
        "titulo = excluded.titulo, visto_ts = excluded.visto_ts",
        (content_uid, enlace, titulo, ahora))
    con.commit()


# --- Cliente de overoption (solo lectura) -------------------------------------------

class ErrorOveroption(Exception):
    pass


def _pedir_http(metodo, ruta, cuerpo=None, params=None, token=None):
    """Una petición HTTP a overoption. Devuelve el JSON como dict. Solo la usa
    ClienteOveroption; en los tests se inyecta otra función."""
    url = BASE + ruta + ("?" + urllib.parse.urlencode(params) if params else "")
    cabeceras = {"User-Agent": UA, "Accept": "application/json",
                 "Origin": "https://overoption.io", "Referer": "https://overoption.io/"}
    datos = None
    if cuerpo is not None:
        datos = json.dumps(cuerpo).encode()
        cabeceras["Content-Type"] = "application/json"
    if token:
        cabeceras["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, data=datos, headers=cabeceras, method=metodo)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            return json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        cuerpo_err = e.read().decode("utf-8", "replace")[:200]
        raise ErrorOveroption(f"HTTP {e.code} en {ruta}: {cuerpo_err}") from None
    except urllib.error.URLError as e:
        raise ErrorOveroption(f"red: {e}") from None


class ClienteOveroption:
    """Entra en overoption y lee transacciones y enlaces. SOLO LECTURA: el único
    POST es el de iniciar sesión; todo lo demás son GET."""

    def __init__(self, pedir=None):
        self._pedir = pedir or _pedir_http
        self.token = None

    def entrar(self, email, password):
        datos = self._pedir("POST", "/auth/login",
                            cuerpo={"email": email, "password": password})
        self.token = (datos.get("data") or {}).get("access_token")
        if not self.token:
            raise ErrorOveroption("login sin token (¿correo/contraseña incorrectos?)")
        return self.token

    def transacciones(self):
        # El endpoint ignora la paginación y devuelve todas; se pide un límite
        # alto por si algún día pagina.
        datos = self._pedir("GET", "/transactions", params={"page": 1, "limit": 100000},
                            token=self.token)
        return (datos.get("data") or {}).get("content") or []

    def enlace_contenido(self, content_uid):
        datos = self._pedir("GET", f"/content/{content_uid}", token=self.token)
        cont = (datos.get("data") or {}).get("content") or {}
        return cont.get("final_content")


# --- Orquestación -------------------------------------------------------------------

def bajar_y_guardar(con, cliente, email, password, ahora=None):
    """Entra, baja todas las ventas, resuelve el enlace de cada producto (con
    caché) y lo guarda todo. Devuelve cuántas ventas se guardaron."""
    ahora = int(time.time() if ahora is None else ahora)
    cliente.entrar(email, password)
    transacciones = cliente.transacciones()
    log.info("overoption: %d transacciones", len(transacciones))

    enlaces = {}  # content_uid -> enlace (caché de esta ejecución)
    filas = []
    for tx in transacciones:
        uid = tx.get("content_uid")
        enlace = None
        if uid:
            if uid in enlaces:
                enlace = enlaces[uid]
            else:
                enlace = enlace_en_cache(con, uid)
                if enlace is None:
                    try:
                        enlace = cliente.enlace_contenido(uid)
                    except ErrorOveroption as e:
                        log.warning("sin enlace de %s: %s", uid, e)
                        enlace = None
                    meta = tx.get("metadata") or {}
                    titulo = _decodificar(meta.get("product_title") or "")
                    guardar_contenido(con, uid, enlace, titulo, ahora=ahora)
                enlaces[uid] = enlace
        filas.append(normalizar_venta(tx, enlace=enlace))
    guardar_ventas(con, filas, ahora=ahora)
    return len(filas)


# --- Cruce con las entradas a los canales de Telegram --------------------------------

def _norm(texto):
    """Normaliza un título para comparar: sin tildes, en minúsculas y sin
    espacios de más."""
    t = unicodedata.normalize("NFKD", _decodificar(texto or ""))
    t = "".join(c for c in t if not unicodedata.combining(c))
    return " ".join(t.lower().split())


def _mapa_canales(con):
    """Para localizar el canal de una venta: por enlace (fiable) y por nombre
    (solo si ese nombre es de un único canal)."""
    por_enlace = {}
    for f in con.execute("SELECT DISTINCT enlace, canal_id FROM ventas_movimientos "
                         "WHERE enlace IS NOT NULL"):
        por_enlace.setdefault(f["enlace"], f["canal_id"])
    titulos = defaultdict(set)
    canales = {}
    for f in con.execute("SELECT canal_id, titulo FROM ventas_canales"):
        canales[f["canal_id"]] = f["titulo"]
        if f["titulo"]:
            titulos[_norm(f["titulo"])].add(f["canal_id"])
    # Solo los nombres que señalan a un único canal sirven para emparejar.
    por_titulo = {t: next(iter(ids)) for t, ids in titulos.items() if len(ids) == 1}
    # Los enlaces leídos en Telegram (invitaciones.py), también de canales antiguos.
    for f in con.execute("SELECT enlace, canal_id, titulo FROM pagos_enlaces WHERE canal_id IS NOT NULL"):
        por_enlace.setdefault(f["enlace"], f["canal_id"])
        canales.setdefault(f["canal_id"], f["titulo"])
    return por_enlace, por_titulo, canales


def _canal_de_venta(venta, por_enlace, por_titulo):
    if venta["enlace"] and venta["enlace"] in por_enlace:
        return por_enlace[venta["enlace"]]
    return por_titulo.get(_norm(venta["producto"]))


def _entradas_por_canal(con):
    """canal_id -> [(user_id, ts)] de cada entrada (del registro y de los
    miembros actuales, sin repetir el mismo usuario a la misma hora)."""
    ent = defaultdict(set)
    for f in con.execute("SELECT canal_id, user_id, ts FROM ventas_movimientos "
                         "WHERE tipo = 'entra'"):
        ent[f["canal_id"]].add((f["user_id"], f["ts"]))
    for f in con.execute("SELECT canal_id, user_id, desde_ts FROM ventas_miembros "
                         "WHERE desde_ts IS NOT NULL"):
        ent[f["canal_id"]].add((f["user_id"], f["desde_ts"]))
    return {cid: sorted(v, key=lambda x: x[1]) for cid, v in ent.items()}


def _invitados_por_enlace(con):
    """enlace -> [(user_id, ts)] de quien se unió con él (invitaciones.py)."""
    inv = defaultdict(list)
    for f in con.execute("SELECT enlace, user_id, ts FROM pagos_invitados ORDER BY ts"):
        inv[f["enlace"]].append((f["user_id"], f["ts"]))
    return inv


def emparejar_ventas(con, ventana_s=VENTANA_S, solo_ventas=True):
    """Para cada venta de overoption, busca a la persona de Telegram que entró
    después de pagar (hasta ventana_s, con ANTES_S de margen por los relojes):
    con el enlace de la venta si se sabe quién se unió con él; si no, al mismo
    canal. Telegram solo enseña a quien sigue dentro, así que el que entró a
    esa hora puede no ser el comprador (que se fue): solo es «emparejada» si
    es el único que entró y esa entrada no la reclama otra venta. Devuelve una
    lista de dicts con el resultado y su estado: emparejada / dudosa_varios /
    sin_emparejar / sin_canal (y por_correo, ver _propagar_por_correo)."""
    por_enlace, por_titulo, canales = _mapa_canales(con)
    entradas = _entradas_por_canal(con)
    invitados = _invitados_por_enlace(con)
    personas = {f["user_id"]: f for f in con.execute(
        "SELECT user_id, nombre, username FROM ventas_personas")}

    filtro = "WHERE es_propina = 0 AND estado = 'SUCCESS'" if solo_ventas else ""
    ventas = []  # (venta, canal_id, grupo, entradas cerca o None si no se sabe el canal)
    for v in con.execute(f"SELECT * FROM pagos_overoption {filtro} ORDER BY pago_ts"):
        v = dict(v)
        canal_id = _canal_de_venta(v, por_enlace, por_titulo)
        fuente = invitados.get(v["enlace"]) if v["enlace"] else None
        if fuente is None and canal_id is not None:
            fuente = entradas.get(canal_id, [])
        cerca = None if fuente is None else [
            (uid, ts) for uid, ts in fuente
            if v["pago_ts"] is not None and -ANTES_S <= ts - v["pago_ts"] <= ventana_s]
        ventas.append((v, canal_id, canal_id if canal_id is not None else v["enlace"], cerca))
    # Cuántas ventas reclaman cada entrada (en el mismo canal).
    reclamada = Counter((grupo, e) for _, _, grupo, cerca in ventas for e in set(cerca or []))

    resultados = []
    for v, canal_id, grupo, cerca in ventas:
        user_id = nombre = username = None
        quienes = list(dict.fromkeys(uid for uid, _ in cerca or []))  # sin repetir usuario
        if cerca is None:
            estado = "sin_canal"
        elif len(quienes) == 1 and all(reclamada[(grupo, e)] == 1 for e in cerca):
            estado = "emparejada"
            user_id = quienes[0]
            p = personas.get(user_id)
            nombre = p["nombre"] if p else None
            username = p["username"] if p else None
        elif quienes:
            estado = "dudosa_varios"
        else:
            estado = "sin_emparejar"
        resultados.append({
            "id": v["id"], "producto": v["producto"], "correo": v["correo"],
            "importe": v["importe"], "moneda": v["moneda"], "neto": v["neto"],
            "metodo": v["metodo"], "pago_ts": v["pago_ts"], "enlace": v["enlace"],
            "canal_id": canal_id, "titulo": canales.get(canal_id),
            "user_id": user_id, "nombre": nombre, "username": username,
            "estado_cruce": estado,
        })
    _propagar_por_correo(resultados)
    return resultados


def _propagar_por_correo(resultados):
    """Las ventas no emparejadas cuyo correo ya está emparejado con UNA sola
    persona pasan a ser de esa persona (estado por_correo). No se propaga si
    el correo sale con dos personas, ni si la persona sale con dos correos
    (uno de los cruces puede ser falso y se extendería a todas sus compras)."""
    por_correo = defaultdict(dict)
    correos_de = defaultdict(set)
    for r in resultados:
        if r["estado_cruce"] == "emparejada" and r["correo"]:
            por_correo[r["correo"]][r["user_id"]] = r
            correos_de[r["user_id"]].add(r["correo"])
    for r in resultados:
        quien = por_correo.get(r["correo"]) if r["correo"] else None
        if r["estado_cruce"] == "emparejada" or not quien or len(quien) != 1:
            continue
        if len(correos_de[next(iter(quien))]) != 1:
            continue
        ref = next(iter(quien.values()))
        r.update(user_id=ref["user_id"], nombre=ref["nombre"], username=ref["username"],
                 estado_cruce="por_correo")


def _clave_canal(r):
    """Para contar canales distintos aunque el canal de Telegram no se sepa."""
    return r["canal_id"] if r["canal_id"] is not None else (r["enlace"] or r["producto"])


def personas_por_correo(con, ventana_s=VENTANA_S):
    """correo -> (nombre, username) de la persona de Telegram de ese correo."""
    return {r["correo"]: (r["nombre"], r["username"])
            for r in emparejar_ventas(con, ventana_s=ventana_s)
            if r["user_id"] is not None and r["correo"]}


def pagos_por_persona(con, ventana_s=VENTANA_S):
    """user_id -> {canales: nº canales distintos pagados, eur: total recibido,
    n: nº de ventas} de las ventas emparejadas (por hora o por correo)."""
    por_persona = {}
    for r in emparejar_ventas(con, ventana_s=ventana_s):
        if r["user_id"] is None:
            continue
        d = por_persona.setdefault(r["user_id"], {"_canales": set(), "eur": 0.0, "n": 0})
        d["_canales"].add(_clave_canal(r))
        d["eur"] += r["neto"] or 0
        d["n"] += 1
    return {uid: {"canales": len(d["_canales"]), "eur": round(d["eur"], 2), "n": d["n"]}
            for uid, d in por_persona.items()}


def filas_clientes(con):
    """Una fila por correo de comprador (no necesita Telegram): nº de compras,
    total pagado, total recibido, nº de canales, primera y última compra."""
    por_correo = {}
    for v in con.execute("SELECT correo, importe, neto, content_uid, enlace, producto, pago_ts "
                         "FROM pagos_overoption WHERE es_propina = 0 AND estado = 'SUCCESS'"):
        if not v["correo"]:
            continue
        d = por_correo.setdefault(v["correo"], {
            "n": 0, "pagado": 0.0, "recibido": 0.0, "canales": set(),
            "primera": None, "ultima": None})
        d["n"] += 1
        d["pagado"] += v["importe"] or 0
        d["recibido"] += v["neto"] or 0
        d["canales"].add(v["enlace"] or v["content_uid"] or v["producto"])
        ts = v["pago_ts"]
        if ts is not None:
            d["primera"] = ts if d["primera"] is None else min(d["primera"], ts)
            d["ultima"] = ts if d["ultima"] is None else max(d["ultima"], ts)
    filas = [[correo, d["n"], round(d["pagado"], 2), round(d["recibido"], 2),
              len(d["canales"]), d["primera"], d["ultima"]]
             for correo, d in por_correo.items()]
    filas.sort(key=lambda f: (-f[1], -f[3]))  # más compras primero
    return filas


# --- Pestañas del Google Sheet ------------------------------------------------------

TAB_PAGOS = "Canales de venta · Pagos"
TAB_CLIENTES = "Clientes (por correo)"
CABECERA_PAGOS = ["Fecha y hora", "Producto (overoption)", "Importe", "Moneda", "€ recibido",
                  "Método", "Correo comprador", "Canal de Telegram", "Persona",
                  "Cruce", "ID transacción"]
CABECERA_CLIENTES = ["Correo", "Compras", "Total pagado", "Total recibido", "Canales distintos",
                     "Primera compra", "Última compra", "Persona de Telegram"]
_ESTADO_TEXTO = {
    "emparejada": "✅ emparejada",
    "por_correo": "✅ por correo (misma persona)",
    "dudosa_varios": "⚠️ dudosa (varias ventas o entradas a la vez)",
    "sin_emparejar": "— sin emparejar",
    "sin_canal": "⚠️ canal no identificado",
}


def filas_pagos(con, tz, ventana_s=VENTANA_S):
    from . import sheet
    filas = []
    for r in emparejar_ventas(con, ventana_s=ventana_s):
        persona = sheet.nombre_visible(r["nombre"], r["username"]) if r["user_id"] else ""
        filas.append([
            sheet.serie_fecha_hora(r["pago_ts"], tz) if r["pago_ts"] else "",
            r["producto"] or "", r["importe"], r["moneda"] or "", r["neto"],
            r["metodo"] or "", r["correo"] or "", r["titulo"] or "", persona,
            _ESTADO_TEXTO.get(r["estado_cruce"], r["estado_cruce"]), r["id"],
        ])
    # Las dudosas y sin emparejar, arriba del todo, para que el dueño las revise.
    orden = {"dudosa_varios": 0, "sin_canal": 1, "sin_emparejar": 2, "emparejada": 3,
             "por_correo": 4}
    filas.sort(key=lambda f: (orden.get(
        {v: k for k, v in _ESTADO_TEXTO.items()}.get(f[9], ""), 9), -(f[0] or 0)))
    return filas


def filas_clientes_sheet(con, tz):
    from . import sheet
    quien = personas_por_correo(con)
    filas = []
    for c in filas_clientes(con):
        correo, n, pagado, recibido, canales, primera, ultima = c
        persona = sheet.nombre_visible(*quien[correo]) if correo in quien else ""
        filas.append([correo, n, pagado, recibido, canales,
                      sheet.serie_fecha_hora(primera, tz) if primera else "",
                      sheet.serie_fecha_hora(ultima, tz) if ultima else "", persona])
    return filas


def hay_datos(con):
    return con.execute("SELECT 1 FROM pagos_overoption LIMIT 1").fetchone() is not None


def escribir_pestanas(con, tz, libro, ventana_s=VENTANA_S):
    from . import sheet
    p = libro.pestana(TAB_PAGOS, [CABECERA_PAGOS])
    p.reemplazar(filas_pagos(con, tz, ventana_s=ventana_s), desde_fila=2)
    p.formatear([("A2:A", sheet.FORMATO_FECHA_HORA)])
    p = libro.pestana(TAB_CLIENTES, [CABECERA_CLIENTES])
    p.reemplazar(filas_clientes_sheet(con, tz), desde_fila=2)
    p.formatear([("F2:G", sheet.FORMATO_FECHA_HORA)])


# --- Ejecutable (servicio captacion-pagos@<instancia>) --------------------------------

def credenciales(entorno=None):
    """(correo, contraseña) de overoption, del entorno. Vacías -> (None, None).
    Nunca se registran en el log."""
    entorno = os.environ if entorno is None else entorno
    return (entorno.get("OVEROPTION_EMAIL", "").strip() or None,
            entorno.get("OVEROPTION_PASSWORD", "") or None)


def main(argv=None):
    import socket

    from .config import ErrorConfig, cargar_config
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    socket.setdefaulttimeout(TIMEOUT_S + 30)
    try:
        cfg = cargar_config(requiere_bot=False)
    except ErrorConfig as e:
        log.error("Configuración incorrecta: %s", e)
        return 2
    email, password = credenciales()
    if not email or not password:
        log.error("Faltan las credenciales de overoption (OVEROPTION_EMAIL / "
                  "OVEROPTION_PASSWORD en /etc/premier-captacion/overoption.env)")
        return 2
    con = db.abrir(cfg.db_path)
    try:
        n = bajar_y_guardar(con, ClienteOveroption(), email, password)
    except ErrorOveroption as e:
        log.error("No se pudieron leer las ventas de overoption: %s", e)
        return 1
    finally:
        con.close()
    log.info("overoption: %d ventas guardadas", n)
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
