"""
Cuentas por persona de Telegram (diseño del 2026-11-01, puntos 4 y 5),
desde el 22/07/2026:

- Canales pagados: las compras de sus correos (el cruce, cruce.py).
- Canales gratis: entró después de tenerlo gratis (gratis.py) y sin compra.
- Canales sin explicar: entró sin compra ni gratis (p. ej. la compra de un
  correo que aún no tiene persona).
- Apuestas de esos canales (apuestas.py) a las que llegó a tiempo: entró
  antes de la carrera (la primera hora del mensaje, en hora de Reino Unido).
- Unidades = suma de `unidades_netas`; simulación = unidades × 10 €;
  balance = simulación − € pagado.

Los correos sin persona salen aparte, con sus compras y las apuestas de los
canales que compraron, para que no se pierda ningún €. El equipo no sale.
"""
from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

from . import analisis, apuestas, gratis, ventas

TAB = "Clientes · cuentas"
EUROS_POR_UNIDAD = 10
HORA_CARRERAS = ZoneInfo("Europe/London")
PAGADO, GRATIS, SIN_EXPLICAR = "pagado", "gratis", "sin_explicar"
CABECERA = ["Persona", "ID de Telegram", "Correos", "Compras", "€ pagado", "Canales pagados", "Canales gratis",
            "Canales sin explicar", "Apuestas", "Ganadas", "Perdidas", "Sin resultado", "Unidades",
            f"Simulación ({EUROS_POR_UNIDAD} €/unidad)", "Balance (simulación − € pagado)"]
TITULO_SIN_PERSONA = "Correos sin persona de Telegram"


def desde_ts(tz):
    """El 22/07/2026 (primer canal de venta) a las 00:00 en `tz`."""
    return datetime.combine(analisis.DESDE, datetime.min.time(), tzinfo=tz).timestamp()


def hora_carrera(a):
    """Cuándo empieza la (primera) carrera de una apuesta: la primera hora
    del mensaje ese día en hora de Reino Unido; si no hay, cuando se publicó."""
    horas = sorted(analisis.horas(a["texto"]))
    if not horas:
        return a["ts"]
    dia = datetime.fromtimestamp(a["ts"], HORA_CARRERAS).date()
    h, m = map(int, horas[0].split(":"))
    return datetime(dia.year, dia.month, dia.day, h, m, tzinfo=HORA_CARRERAS).timestamp()


def _cuenta():
    return {"correos": set(), "compras": 0, "euros": 0.0, "accesos": {}}


def _sumar_apuestas(c, apuestas_canal):
    c.update(apuestas=0, ganadas=0, perdidas=0, sin_resultado=0, unidades=0.0)
    for canal_id, (desde, _) in c["accesos"].items():
        for a in apuestas_canal.get(canal_id, ()):
            if hora_carrera(a) < desde:
                continue  # la carrera ya se había corrido cuando entró
            c["apuestas"] += 1
            if a["unidades"] is None:
                c["sin_resultado"] += 1
                continue
            c["ganadas"] += a["resultado"] == apuestas.GANO
            c["perdidas"] += a["resultado"] == apuestas.PERDIO
            c["unidades"] += a["unidades"]
    tipos = [t for _, t in c["accesos"].values()]
    c.update(pagados=tipos.count(PAGADO), gratis=tipos.count(GRATIS), sin_explicar=tipos.count(SIN_EXPLICAR),
             correos=sorted(c["correos"]), euros=round(c["euros"], 2), unidades=round(c["unidades"], 2))
    return c


def _equipo(con, del_equipo):
    return {f[0] for f in con.execute("SELECT user_id, username, admin FROM ventas_personas")
            if ventas._es_equipo(f[0], f[1], f[2], del_equipo)}


def calcular(con, calculo, apuestas_canal, desde_ts, del_equipo=None):
    """(user_id -> cuenta, correo sin persona -> cuenta). Cada cuenta: correos,
    compras, euros, pagados, gratis, sin_explicar, apuestas, ganadas,
    perdidas, sin_resultado y unidades."""
    equipo = _equipo(con, ventas.equipo() if del_equipo is None else del_equipo)
    canales = {f[0] for f in con.execute("SELECT canal_id FROM ventas_canales")}
    personas, sin_persona = defaultdict(_cuenta), defaultdict(_cuenta)
    for r in calculo.resultados:
        if r["pago_ts"] is None or r["pago_ts"] < desde_ts:
            continue
        c = personas[r["user_id"]] if r["user_id"] is not None else sin_persona[r["correo"]]
        c["correos"].add(r["correo"])
        c["compras"] += 1
        c["euros"] += r["importe"] or 0
        if r["canal_id"] is not None:
            antes = c["accesos"].get(r["canal_id"], (r["pago_ts"], PAGADO))[0]
            c["accesos"][r["canal_id"]] = (min(antes, r["pago_ts"]), PAGADO)
    ent = gratis.entradas(con)
    ofertas = gratis.ofertas(con, ent)
    for (canal_id, uid), tss in ent.items():
        primera = min(tss)
        if primera < desde_ts or canal_id not in canales or uid in equipo:
            continue
        accesos = personas[uid]["accesos"]
        if canal_id in accesos:  # pagado: entra cuando pagó o cuando se le ve entrar
            accesos[canal_id] = (min(accesos[canal_id][0], primera), PAGADO)
            continue
        oferta = ofertas.get((canal_id, uid))
        accesos[canal_id] = (primera, GRATIS if oferta is not None and oferta[0] <= primera else SIN_EXPLICAR)
    for uid in equipo:
        personas.pop(uid, None)
    return ({uid: _sumar_apuestas(c, apuestas_canal) for uid, c in personas.items()},
            {correo: _sumar_apuestas(c, apuestas_canal) for correo, c in sin_persona.items()})


def _numeros(c, con_gratis=True):
    sim = round(c["unidades"] * EUROS_POR_UNIDAD, 2)
    return [c["compras"], c["euros"], c["pagados"], c["gratis"] if con_gratis else "",
            c["sin_explicar"] if con_gratis else "", c["apuestas"], c["ganadas"], c["perdidas"],
            c["sin_resultado"], c["unidades"], sim, round(sim - c["euros"], 2)]


def filas(personas, sin_persona, nombres):
    """Filas de la pestaña (sin la cabecera): una por persona, de más a menos
    € pagado, y debajo los correos sin persona."""
    from . import sheet
    salida = []
    for uid, c in sorted(personas.items(), key=lambda x: (-x[1]["euros"], -x[1]["apuestas"], x[0])):
        p = nombres.get(uid) or {}
        salida.append([sheet.nombre_visible(p.get("nombre"), p.get("username")) or str(uid), uid,
                       ", ".join(c["correos"])] + _numeros(c))
    if sin_persona:
        salida.append([""])
        salida.append([TITULO_SIN_PERSONA])
        for correo, c in sorted(sin_persona.items(), key=lambda x: (-x[1]["euros"], x[0])):
            salida.append(["", "", correo] + _numeros(c, con_gratis=False))
    return salida


def escribir_pestana(libro, filas_cuentas):
    p = libro.pestana(TAB, [CABECERA])
    p.reemplazar(filas_cuentas, desde_fila=2)
