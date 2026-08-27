"""
Job recurrente (Fase 7): rellena `resultados_galgos` de la hoja "Picks
Premier Galgos" a partir de `data/historical/results_enriched.parquet`,
que la propia VM de Proyecto Galgos mantiene actualizado cada 20 min
(`galgos-poll-results`). Diseñado para correr EN esa VM vía systemd timer
- ver deploy/ para las instrucciones y las unidades.

Por qué solo usa el parquet local, sin llamadas en vivo a Racing Post
(dog_id/track_id): el 2026-08-26 se intentó con el camino completo y
Racing Post empezó a dar rate-limit tras el volumen acumulado del día; el
mecanismo de rotación de VPN del propio proyecto (src/utils/vpn.py) no
funcionaba en ese momento y entró en un bucle infinito real. La "trampa
ganadora" (fallback ya implementado en las fórmulas de `apuestas`/
`apuestas_patas`) no necesita esos datos para resolver gano/perdio - solo
necesita que las filas de podio de la carrera estén en `resultados_galgos`,
y esas SÍ están siempre en el parquet local. dog_id/cuota_final exactos
para patas fuera de podio quedan sin rellenar por este job (se resuelven
aparte - ver `enriquecer_legs.py`/`buscar_forms.py` en el histórico de
sesiones, que los saca de las cards ya guardadas en la VM sin peticiones
en vivo) - no bloquea la resolución de gano/perdio, que es lo esencial.
`url_carrera` SÍ se rellena aquí para las filas de podio (usa `track_id`,
que el parquet ya trae) - arreglado 2026-08-26 tras detectar que se
quedaba siempre en blanco (bug real, no una limitación deliberada como se
documentó al principio).
Ver docs/BITACORA.md 2026-08-26 para el detalle completo.

Idempotente: antes de tocar una carrera, comprueba si ya hay alguna fila
en `resultados_galgos` para ese canódromo+fecha+hora - si la hay, la salta
(no vuelve a insertar duplicados en cada ejecución).

Solo procesa carreras que ya deberían haber corrido (margen de 30 min),
para no perder tiempo buscando en el parquet algo que aún no puede estar.

Dos fases, para no cargar el parquet (lo más pesado, ~2MB+ en memoria) si
no hace falta: primero se calcula qué patas están "pendientes" (no
cubiertas todavía Y ya deberían haber corrido) con solo lo leído de
Sheets - si no hay ninguna, el job termina ahí, sin tocar el parquet.
"""
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import gspread
import pandas as pd
from google.oauth2.service_account import Credentials

SERVICE_ACCOUNT_FILE = "/root/.config/picks-premier-galgos/service_account.json"
SHEET_ID = "1axZnIIIXBpqVhhb6RVGawNaWpSLVLBwXK079MxcOfF4"
PARQUET_PATH = "/opt/galgos/repo/data/historical/results_enriched.parquet"

UK = ZoneInfo("Europe/London")
UTC = ZoneInfo("UTC")
MADRID = ZoneInfo("Europe/Madrid")

MARGEN_CARRERA_CORRIDA_MIN = 30


def frac_to_decimal(s):
    if s is None:
        return None
    s = str(s).strip()
    if not s or s.lower() == "none":
        return None
    if s.lower() in ("evs", "evens"):
        return 2.0
    if "/" in s:
        try:
            n, d = s.split("/")
            return round(1 + float(n) / float(d), 4)
        except Exception:
            return None
    try:
        return round(float(s), 4)
    except Exception:
        return None


def calcular_pendientes(patas, carreras_cubiertas, limite):
    """Fase barata (sin parquet): qué patas hay que mirar de verdad -
    no cubiertas todavía Y su carrera ya debería haber corrido."""
    pendientes = []
    saltadas_futuras = 0
    saltadas_ya_cubiertas = 0

    for row in patas:
        if len(row) < 6 or not row[0]:
            continue
        hipodromo = (row[3] or "").strip()
        hora_carrera = (row[4] or "").strip()
        fecha_pick_str = (row[2] or "").split(" ")[0]
        if not hipodromo or not hora_carrera or not fecha_pick_str:
            continue

        try:
            fecha_dt = datetime.strptime(fecha_pick_str, "%d/%m/%Y").date()
            hora_uk = datetime.strptime(hora_carrera, "%H:%M").time()
        except ValueError:
            continue

        fecha_str = fecha_dt.strftime("%d/%m/%Y")
        clave_carrera = (hipodromo.lower(), fecha_str, hora_carrera)
        if clave_carrera in carreras_cubiertas:
            saltadas_ya_cubiertas += 1
            continue

        dt_uk = datetime.combine(fecha_dt, hora_uk, tzinfo=UK)
        if dt_uk.astimezone(MADRID) > limite:
            saltadas_futuras += 1
            continue

        pendientes.append({
            "hipodromo": hipodromo, "hora_carrera": hora_carrera,
            "fecha_dt": fecha_dt, "fecha_str": fecha_str,
            "clave_carrera": clave_carrera, "dt_uk": dt_uk,
        })

    return pendientes, saltadas_ya_cubiertas, saltadas_futuras


def resolver_contra_parquet(pendientes):
    """Fase cara: solo se llega aquí si `pendientes` no está vacío."""
    df = pd.read_parquet(PARQUET_PATH)
    df["Fecha"] = pd.to_datetime(df["Fecha"]).dt.strftime("%Y-%m-%d")

    nuevas_filas = []
    clave_puesta = set()
    sin_datos_todavia = 0
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    for p in pendientes:
        dt_utc = p["dt_uk"].astimezone(UTC)
        rtime_utc = dt_utc.strftime("%Y-%m-%d %H:%M")
        fecha_iso = p["fecha_dt"].isoformat()
        hipodromo = p["hipodromo"]
        hora_carrera = p["hora_carrera"]
        fecha_str = p["fecha_str"]

        mask = (
            (df["Canodromo"].str.lower() == hipodromo.lower())
            & (df["Fecha"] == fecha_iso)
            & (df["rTime"] == rtime_utc)
        )
        sub = df[mask]
        if len(sub) == 0:
            sin_datos_todavia += 1
            continue

        race_id = str(sub.iloc[0]["race_id"])
        track_id = str(sub.iloc[0]["track_id"]) if sub.iloc[0]["track_id"] not in (None, "None") else ""
        url_carrera = (
            f"https://greyhoundbet.racingpost.com/#result-meeting-result/"
            f"race_id={race_id}&track_id={track_id}&r_date={fecha_iso}&r_time={hora_carrera.replace(':', '%3A')}"
            if track_id else ""
        )
        for _, r in sub.iterrows():
            clave = (hipodromo, fecha_str, hora_carrera, str(r["trap"]))
            if clave in clave_puesta:
                continue
            clave_puesta.add(clave)
            nuevas_filas.append([
                hipodromo, fecha_str, hora_carrera, str(r["trap"]),
                r["name"], str(r["position"]), ts,
                frac_to_decimal(r["fract"]), url_carrera, race_id, str(r["dogId"]),
            ])

    return nuevas_filas, sin_datos_todavia


def main():
    creds = Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE,
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(SHEET_ID)

    ws_patas = sh.worksheet("apuestas_patas")
    patas = ws_patas.get("A2:H5000")

    ws_resultados = sh.worksheet("resultados_galgos")
    existentes = ws_resultados.get("A2:D5000")
    carreras_cubiertas = set()
    for row in existentes:
        if len(row) >= 3 and row[0]:
            carreras_cubiertas.add((row[0].strip().lower(), row[1], row[2]))

    ahora_madrid = datetime.now(MADRID)
    limite = ahora_madrid - timedelta(minutes=MARGEN_CARRERA_CORRIDA_MIN)

    pendientes, saltadas_ya_cubiertas, saltadas_futuras = calcular_pendientes(
        patas, carreras_cubiertas, limite
    )

    print(
        f"patas: {len(patas)} totales, {saltadas_ya_cubiertas} ya cubiertas, "
        f"{saltadas_futuras} aun no corridas, {len(pendientes)} pendientes",
        flush=True,
    )

    if not pendientes:
        print("nada pendiente - no hace falta cargar el parquet, fin.", flush=True)
        return

    nuevas_filas, sin_datos_todavia = resolver_contra_parquet(pendientes)
    print(
        f"de {len(pendientes)} pendientes: {len(nuevas_filas)} filas de resultado encontradas, "
        f"{sin_datos_todavia} carreras sin datos todavia (se reintentaran en la proxima pasada)",
        flush=True,
    )

    if nuevas_filas:
        fila_inicio = len(existentes) + 2
        fila_fin = fila_inicio + len(nuevas_filas) - 1
        ws_resultados.update(f"A{fila_inicio}:K{fila_fin}", nuevas_filas, value_input_option="USER_ENTERED")
        print(f"{len(nuevas_filas)} filas nuevas insertadas en resultados_galgos ({fila_inicio}-{fila_fin})", flush=True)
    else:
        print("ninguna de las pendientes tenia datos en el parquet todavia", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr, flush=True)
        raise
