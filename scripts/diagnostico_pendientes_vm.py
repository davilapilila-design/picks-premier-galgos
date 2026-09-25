"""
Diagnóstico de SOLO LECTURA, para ejecutar en la VM de Proyecto Galgos
(docs/BITACORA.md 2026-09-25). No escribe nada en ningún sitio.

1. Picks 32 y 74 del histórico: no se guardó su fecha real. Busca en las
   cards (galgos_master.parquet) el día, dentro del rango que acotan los
   mensajes vecinos, en que TODAS sus patas cuadran con canódromo + galgo +
   trampa del boleto de Sky Bet. Solo da una fecha si es única.
2. Patas pendientes: localiza cada galgo en las cards de su día por NOMBRE
   (no por hora), y cruza por race_id con results_enriched.parquet para
   distinguir: galgo no está en las cards / carrera sin resultados /
   carrera con resultado pero hora distinta (el job de picks exige la hora
   exacta) / carrera abandonada.

Uso en la VM:
    /opt/galgos/repo/venv/bin/python diagnostico_pendientes_vm.py
"""
import difflib
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

MASTER = "/opt/galgos/data/master/galgos_master.parquet"
RESULTS = "/opt/galgos/repo/data/historical/results_enriched.parquet"
UK, UTC = ZoneInfo("Europe/London"), ZoneInfo("UTC")

# (message_id, [fechas candidatas], [(canodromo, galgo, trampa del boleto)])
HISTORICO_SIN_FECHA = [
    ("32", ["2026-07-31", "2026-08-01", "2026-08-02"],
     [("Central Park", "Turnthemagicon", 6), ("Monmore", "Vhagar", 5)]),
    ("74", ["2026-08-15", "2026-08-16"],
     [("Monmore", "Vhagar", 4), ("Monmore", "Slingshot Poppy", 4)]),
]

# (message_id, canodromo, fecha, hora UK del tipster, galgo)
PATAS_PENDIENTES = [
    ("120", "Hove", "2026-08-26", "21:59", "Tedushi Ted"),
    ("267", "Yarmouth", "2026-09-09", "20:22", "Roanna Mamba"),
    ("267", "Yarmouth", "2026-09-09", "22:23", "Romeo Empire"),
    ("268", "Yarmouth", "2026-09-09", "21:47", "Farneys Tilly"),
    ("289", "Central Park", "2026-09-15", "20:56", "Swift United"),
    ("292", "Harlow", "2026-09-16", "19:46", "Gagas Merry"),
    ("293", "Yarmouth", "2026-09-16", "21:31", "Rosshill Storm"),
    ("301", "Harlow", "2026-09-18", "14:03", "Joys Of Dannielle"),
    ("302", "Harlow", "2026-09-18", "14:19", "Caislean Champ"),
    ("303", "Harlow", "2026-09-18", "14:54", "Da Danna"),
    ("307", "Towcester", "2026-09-20", "18:06", "Romeo Tomcat"),
    ("308", "Towcester", "2026-09-20", "18:24", "Droopys Erlybird"),
    ("315", "Star Pelaw", "2026-09-22", "20:04", "Glenbowen Mabel"),
    ("316", "Central Park", "2026-09-22", "21:13", "King Cobain"),
]


def norm(s):
    return str(s).strip().lower()


def rid(v):
    return str(v).replace(".0", "").strip()


def cargar():
    m = pd.read_parquet(MASTER, columns=["Fecha", "Canódromo", "Race_ID", "Nombre", "Trap", "Hora"])
    m["cano"] = m["Canódromo"].map(norm)
    m["fecha"] = m["Fecha"].astype(str).str.slice(0, 10)
    m["nombre"] = m["Nombre"].map(norm)
    m["rid"] = m["Race_ID"].map(rid)
    m["hora"] = m["Hora"].astype(str).str.slice(0, 5)
    r = pd.read_parquet(RESULTS)
    r["rid"] = r["race_id"].map(rid)
    return m, r


def en_cards(m, cano, fecha, galgo):
    dia = m[(m["cano"] == norm(cano)) & (m["fecha"] == fecha)]
    g = dia[dia["nombre"] == norm(galgo)]
    if g.empty:  # nombre del tipster con nota pegada ("X SIN el favorito")
        g = dia[dia["nombre"].map(lambda n: bool(n) and norm(galgo).startswith(n))]
    return dia, g


def resultado(r, race_id, galgo):
    rr = r[r["rid"] == race_id]
    if rr.empty:
        return "SIN RESULTADOS en results_enriched"
    fila = rr[rr["name"].map(norm) == norm(galgo)]
    estados = {c: sorted(rr[c].astype(str).unique()) for c in rr.columns if "status" in c.lower()}
    pos = fila.iloc[0]["position"] if not fila.empty else "?"
    return f"resultado SI: rTime={rr.iloc[0]['rTime']} posicion={pos} {estados}"


def parte_historico(m, r):
    print("=" * 70, "\n1) PICKS DEL HISTORICO SIN FECHA (32, 74)\n" + "=" * 70)
    for msg, fechas, patas in HISTORICO_SIN_FECHA:
        print(f"\n--- msg {msg} ---")
        encajan = []
        for f in fechas:
            ok = True
            for cano, galgo, trampa in patas:
                _, g = en_cards(m, cano, f, galgo)
                if g.empty:
                    print(f"  {f} {cano} {galgo}: no corre ese dia")
                    ok = False
                    continue
                for _, row in g.iterrows():
                    t = int(float(row["Trap"]))
                    print(f"  {f} {cano} {galgo}: T{t} Hora(UTC)={row['hora']} race_id={row['rid']}"
                          f"{'  <-- trampa del boleto' if t == trampa else '  (trampa distinta al boleto)'}"
                          f" | {resultado(r, row['rid'], galgo)}")
                ok = ok and any(int(float(t)) == trampa for t in g["Trap"])
            if ok:
                encajan.append(f)
        if len(encajan) == 1:
            print(f"  => FECHA UNICA: {encajan[0]} (todas las patas cuadran con la trampa del boleto)")
        else:
            print(f"  => NO CONCLUYENTE: fechas que cuadran = {encajan or 'ninguna'}")


def parte_pendientes(m, r):
    print("\n" + "=" * 70, "\n2) PATAS PENDIENTES\n" + "=" * 70)
    for msg, cano, f, hora, galgo in PATAS_PENDIENTES:
        esperada = datetime.combine(date.fromisoformat(f), datetime.strptime(hora, "%H:%M").time(),
                                    tzinfo=UK).astimezone(UTC).strftime("%H:%M")
        cab = f"msg {msg} {cano} {f} {hora}UK ({esperada}UTC) {galgo}:"
        dia, g = en_cards(m, cano, f, galgo)
        if dia.empty:
            print(f"{cab} SIN CARDS de {cano} ese dia (reunion no descargada o nombre de canodromo distinto)")
            continue
        if g.empty:
            parecidos = difflib.get_close_matches(norm(galgo), dia["nombre"].unique().tolist(), n=3, cutoff=0.75)
            print(f"{cab} galgo NO esta en las cards ({dia['rid'].nunique()} carreras ese dia); parecidos: {parecidos}")
            continue
        for _, row in g.iterrows():
            aviso = "" if row["hora"] == esperada else f"  ** HORA DISTINTA: card {row['hora']}UTC vs tipster {esperada}UTC **"
            print(f"{cab} card T{int(float(row['Trap']))} race_id={row['rid']}{aviso} | {resultado(r, row['rid'], galgo)}")


if __name__ == "__main__":
    master, results = cargar()
    parte_historico(master, results)
    parte_pendientes(master, results)
