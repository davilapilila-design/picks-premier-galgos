# -*- coding: utf-8 -*-
"""
Job recurrente (Fase 7, complemento): rellena en `resultados_galgos` la
fila EXACTA (posicion + cuota SP real, no solo "trampa ganadora") de las
patas de `apuestas_patas` que ya se resolvieron gano/perdio por el
fallback de trampa ganadora pero les falta el detalle fino (estan fuera
de podio en results_enriched.parquet).

Estrategia (pedida por el usuario 2026-08-26, en vez de ir directo a
"resultados" en vivo, que puede no tener ni la carrera ni el galgo si
quedo fuera de podio):

  1. Identificar la carrera+galgo con los datos YA GUARDADOS de la propia
     card (galgos_master.parquet: canodromo+fecha+nombre -> Dog_ID,
     Race_ID). Sin esto no hay nada que buscar.
  2. Buscar la carrera dentro del HISTORIAL embebido en la propia card del
     galgo (galgos_json_sidecar.parquet: Raw_Dog_Details_JSON.details.forms,
     hasta 60 carreras pasadas con posicion Y cuota SP) - sin ninguna
     peticion en vivo. Esto resuelve la carrera en cuanto el galgo haya
     vuelto a correr despues (su siguiente card trae el historial
     actualizado).
  3. Si el galgo TODAVIA no ha vuelto a correr desde la carrera en
     cuestion (no aparece en ningun snapshot guardado), y solo entonces,
     una petición EN VIVO a Racing Post (`dog/blocks.sd`) - una sola vez,
     sin reintentos ni rotacion de VPN (el rotador de src/utils/vpn.py del
     propio Proyecto Galgos esta roto - bucle infinito visto el
     2026-08-26). Cada dog_id se respeta con un enfriamiento de 2 DIAS
     entre intentos en vivo (pedido explicito del usuario: el dato del
     historial de un galgo solo cambia cuando vuelve a correr, machacar
     la peticion mas seguido no sirve de nada y arriesga el rate-limit).

Idempotente: antes de intentar nada, comprueba si ya existe una fila para
esa canodromo+fecha+hora+trampa en `resultados_galgos` - si la hay, la
salta.
"""
import json
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import gspread
import pandas as pd
import pyarrow.parquet as pq
from google.oauth2.service_account import Credentials

SERVICE_ACCOUNT_FILE = "/root/.config/picks-premier-galgos/service_account.json"
SHEET_ID = "1axZnIIIXBpqVhhb6RVGawNaWpSLVLBwXK079MxcOfF4"
MASTER_PARQUET = "/opt/galgos/data/master/galgos_master.parquet"
SIDECAR_PARQUET = "/opt/galgos/data/master/galgos_json_sidecar.parquet"
COOLDOWN_FILE = Path("/opt/picks-premier-galgos/dog_lookup_cooldown.json")
COOLDOWN_DIAS = 2

TRACK_IDS = {
    "Central Park": "70", "Monmore": "4", "Newcastle": "6", "Oxford": "7",
    "Romford": "11", "Sheffield": "34", "Shelbourne Park": "21",
    "Star Pelaw": "86", "Suffolk Downs": "63", "Sunderland": "61",
    "Towcester": "98", "Tralee": "57", "Valley": "73", "Hove": "5",
    "Dunstall Park": "99", "Nottingham": "33", "Kinsley": "76",
    "Limerick": "40", "Waterford": "58", "Enniscorthy": "48", "Cork": "42",
    "Harlow": "69", "Mullingar": "53", "Dundalk": "45", "Newbridge": "55",
    "Kilkenny": "50", "Clonmel": "41", "Yarmouth": "16", "Doncaster": "66",
    "Youghal": "59", "Galway": "49", "Lifford": "51", "Thurles": "56",
    "Drumbo Park": "88",
}


def cargar_cooldown():
    if COOLDOWN_FILE.exists():
        return json.loads(COOLDOWN_FILE.read_text(encoding="utf-8"))
    return {}


def guardar_cooldown(estado):
    COOLDOWN_FILE.parent.mkdir(parents=True, exist_ok=True)
    COOLDOWN_FILE.write_text(json.dumps(estado, ensure_ascii=False, indent=2), encoding="utf-8")


def en_enfriamiento(estado, dog_id, ahora):
    ultimo = estado.get(str(dog_id))
    if not ultimo:
        return False
    return (ahora - datetime.fromisoformat(ultimo)) < timedelta(days=COOLDOWN_DIAS)


def construir_fila(hipodromo, fecha_str, hora_str, trap, nombre, posicion, cuota_final,
                    race_id, dog_id, ts):
    track_id = TRACK_IDS.get(hipodromo, "")
    d, m, y = fecha_str.split("/")
    url = ""
    if track_id:
        url = (
            f"https://greyhoundbet.racingpost.com/#result-meeting-result/"
            f"race_id={race_id}&track_id={track_id}&r_date={y}-{m}-{d}"
            f"&r_time={hora_str.replace(':', '%3A')}"
        )
    return [hipodromo, fecha_str, hora_str, str(trap), nombre, str(posicion), ts,
            cuota_final, url, str(race_id), str(dog_id)]


def parsear_forma(forma):
    """Extrae (posicion, cuota_decimal, fecha_str, hora_str) de una entrada
    de `forms` (misma sea de sidecar local o de la respuesta en vivo)."""
    pos_match = re.match(r"(\d+)", str(forma.get("rOutcomeDesc", "")))
    if not pos_match:
        return None
    posicion = pos_match.group(1)
    numer, denom = forma.get("oddsFrctnNumer"), forma.get("oddsFrctnDenom")
    cuota = ""
    if numer not in (None, "") and denom not in (None, "", "0"):
        try:
            cuota = round(1 + float(numer) / float(denom), 4)
        except (TypeError, ValueError, ZeroDivisionError):
            cuota = ""
    race_time_utc = datetime.strptime(forma["raceTime"], "%Y-%m-%d %H:%M")
    race_time_uk = race_time_utc + timedelta(hours=1)  # ver docs/BITACORA.md 2026-08-26
    return posicion, cuota, race_time_uk.strftime("%d/%m/%Y"), race_time_uk.strftime("%H:%M")


def buscar_en_sidecar(dog_id, race_id):
    """Busca race_id en el historial embebido de CUALQUIER snapshot guardado
    de ese dog_id. None si el galgo no ha vuelto a correr desde entonces."""
    pf = pq.ParquetFile(SIDECAR_PARQUET)
    for batch in pf.iter_batches(columns=["Dog_ID", "Raw_Dog_Details_JSON"], batch_size=4000):
        for d, raw in zip(batch.column("Dog_ID").to_pylist(), batch.column("Raw_Dog_Details_JSON").to_pylist()):
            if d is None or int(d) != dog_id or not raw:
                continue
            try:
                forms = json.loads(raw).get("details", {}).get("forms") or []
            except Exception:
                continue
            for f in forms:
                if str(f.get("rInstId")) == str(race_id):
                    return f
    return None


def buscar_en_vivo(dog_id, race_id):
    """UNA sola petición a Racing Post, sin reintentos ni VPN (ver
    docstring). Devuelve la entrada de forms si esta, o None."""
    from curl_cffi import requests as crequests
    url = f"https://greyhoundbet.racingpost.com/dog/blocks.sd?dog_id={dog_id}&race_id={race_id}&blocks=details"
    try:
        session = crequests.Session(impersonate="chrome124")
        resp = session.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        print(f"  peticion en vivo fallo para dog_id={dog_id}: {exc}", flush=True)
        return None
    forms = data.get("details", {}).get("forms") or []
    for f in forms:
        if str(f.get("rInstId")) == str(race_id):
            return f
    return None


def main():
    creds = Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(SHEET_ID)

    ws_patas = sh.worksheet("apuestas_patas")
    headers = ws_patas.row_values(1)
    idx = {h: i for i, h in enumerate(headers)}
    filas = ws_patas.get_all_values()[1:]

    candidatas = []
    for row in filas:
        if len(row) <= idx["cuota_final_pata"]:
            continue
        if row[idx["cuota_final_pata"]]:
            continue  # ya tiene el detalle
        resultado = row[idx["resultado_pata"]]
        if resultado != "perdio":
            continue  # "pendiente" (aun sin datos) o "gano" (no pasa por fallback)
        candidatas.append({
            "hipodromo": row[idx["hipodromo"]].strip(),
            "fecha_pick": row[idx["fecha_pick"]],
            "seleccion": row[idx["seleccion"]].strip(),
            "trampa": row[idx["trampa"]].strip(),
        })

    print(f"{len(candidatas)} patas con resultado (perdio via fallback) pero sin cuota_final_pata.", flush=True)
    if not candidatas:
        return

    print("Cargando galgos_master.parquet para dog_id/race_id...", flush=True)
    master = pd.read_parquet(MASTER_PARQUET, columns=["Fecha", "Canódromo", "Race_ID", "Dog_ID", "Nombre"])
    master["Canodromo_norm"] = master["Canódromo"].astype(str).str.strip().str.lower()
    master["Fecha_str"] = master["Fecha"].astype(str).str.slice(0, 10)
    master["Nombre_norm"] = master["Nombre"].astype(str).str.strip().str.lower()

    ws_resultados = sh.worksheet("resultados_galgos")
    existentes = ws_resultados.get_all_values()[1:]
    pares_existentes = {(row[0].strip().lower(), row[1], row[2], row[3]) for row in existentes if len(row) > 3}

    cooldown = cargar_cooldown()
    ahora = datetime.now(timezone.utc)
    ts = ahora.strftime("%Y-%m-%dT%H:%M:%SZ")

    nuevas_filas = []
    en_espera = 0
    resueltas_local = 0
    resueltas_vivo = 0
    sin_dog_id = 0

    for leg in candidatas:
        fecha_dmy = leg["fecha_pick"].split(" ")[0]
        try:
            d, m, y = fecha_dmy.split("/")
        except ValueError:
            continue
        fecha_iso = f"{y}-{m}-{d}"

        scope = master[(master["Canodromo_norm"] == leg["hipodromo"].lower()) & (master["Fecha_str"] == fecha_iso)]
        match = scope[scope["Nombre_norm"] == leg["seleccion"].lower()]
        if match.empty:
            sin_dog_id += 1
            continue
        row = match.iloc[0]
        dog_id, race_id = int(row["Dog_ID"]), str(row["Race_ID"])

        # Ya cubierta esta trampa concreta para esa carrera? (comprobacion
        # aproximada por canodromo+fecha+trampa, la hora exacta se sabe
        # solo tras resolver la forma - pero canodromo+fecha+trampa ya es
        # bastante especifico para picks reales)
        ya_cubierta = any(
            p[0] == leg["hipodromo"].lower() and p[1] == fecha_dmy and p[3] == leg["trampa"]
            for p in pares_existentes
        )
        if ya_cubierta:
            continue

        forma = buscar_en_sidecar(dog_id, race_id)
        if forma:
            resueltas_local += 1
        else:
            if en_enfriamiento(cooldown, dog_id, ahora):
                en_espera += 1
                continue
            forma = buscar_en_vivo(dog_id, race_id)
            cooldown[str(dog_id)] = ahora.isoformat()
            time.sleep(2)  # pequeño respiro entre peticiones en vivo, no hace falta mas con el enfriamiento de dias
            if forma:
                resueltas_vivo += 1

        if not forma:
            continue

        parsed = parsear_forma(forma)
        if not parsed:
            continue
        posicion, cuota, fecha_str, hora_str = parsed
        trap = forma.get("trapNum", leg["trampa"])
        nombre_card = row["Nombre"]
        nuevas_filas.append(construir_fila(
            leg["hipodromo"], fecha_str, hora_str, trap, nombre_card, posicion, cuota, race_id, dog_id, ts,
        ))

    print(f"sin dog_id en la card: {sin_dog_id} | en enfriamiento (2 dias): {en_espera} | "
          f"resueltas local: {resueltas_local} | resueltas en vivo: {resueltas_vivo}", flush=True)

    guardar_cooldown(cooldown)

    if nuevas_filas:
        fila_inicio = len(existentes) + 2
        fila_fin = fila_inicio + len(nuevas_filas) - 1
        ws_resultados.update(f"A{fila_inicio}:K{fila_fin}", nuevas_filas, value_input_option="USER_ENTERED")
        print(f"{len(nuevas_filas)} filas nuevas insertadas en resultados_galgos ({fila_inicio}-{fila_fin})", flush=True)
    else:
        print("nada que insertar en esta pasada.", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr, flush=True)
        raise
