"""
Parsea el histórico de picks reenviado al grupo de Telegram (obtenido vía
getUpdates) y genera CSVs locales con la misma estructura que las pestañas
`mensajes_crudos` y `apuestas` de la hoja de Google (ver PLAN.md sección 5).

Uso:
    python scripts/backfill_picks.py raw_updates.json

Es un backfill puntual del histórico, no la lógica del bot en producción
(esa vive en Apps Script, Fase 4 del PLAN.md). Aquí no hace falta IA: los
captions ya traen toda la info en texto plano, así que se extrae con regex.
"""
import csv
import json
import re
import sys
from datetime import datetime, timezone

REQUIRED_FIELDS = ("hipodromo", "hora_carrera", "trampa", "seleccion", "cuota", "stake")

HORA_HIPODROMO_RE = re.compile(r"^\s*(\d{1,2})[:;](\d{2})\s+(.+?)\s*$", re.MULTILINE)
# Formato alternativo: hipódromo antes de la hora, p. ej. "Harlow 12:21"
HIPODROMO_HORA_RE = re.compile(r"^\s*([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ\s]*?)\s+(\d{1,2}):(\d{2})\s*$", re.MULTILINE)
TRAMPA_SELECCION_RE = re.compile(r"(?:Galgo\s+)?T(\d)\s+(.+)")
CUOTA_RE = re.compile(r"Cuota\s+([\d.,]+)")
STAKE_RE = re.compile(r"Stake\s+([\d.,]+)")
APUESTA_DOBLE_RE = re.compile(r"Apuesta\s+Doble", re.IGNORECASE)


def parse_pick_text(texto: str) -> dict:
    """Extrae los campos de una pick a partir del caption/texto. Devuelve
    dict con los campos encontrados; los que falten simplemente no aparecen
    (eso es lo que decide revision_manual más abajo)."""
    campos = {}

    if APUESTA_DOBLE_RE.search(texto):
        # Dos carreras en un mismo pick: no encaja en el esquema de una
        # fila = una selección. Se deja fuera, para revisión manual.
        return campos

    m = HORA_HIPODROMO_RE.search(texto)
    if m:
        hh, mm, hipodromo = m.groups()
        campos["hora_carrera"] = f"{int(hh):02d}:{mm}"
        campos["hipodromo"] = hipodromo.strip()
    else:
        m = HIPODROMO_HORA_RE.search(texto)
        if m:
            hipodromo, hh, mm = m.groups()
            campos["hora_carrera"] = f"{int(hh):02d}:{mm}"
            campos["hipodromo"] = hipodromo.strip()

    m = TRAMPA_SELECCION_RE.search(texto)
    if m:
        campos["trampa"] = m.group(1)
        campos["seleccion"] = m.group(2).strip()

    m = CUOTA_RE.search(texto)
    if m:
        campos["cuota"] = m.group(1).replace(",", ".").strip()

    m = STAKE_RE.search(texto)
    if m:
        campos["stake"] = m.group(1).replace(",", ".").strip()

    return campos


def best_photo_file_id(photos):
    if not photos:
        return ""
    # Telegram devuelve las resoluciones de menor a mayor; la última es la
    # de mayor calidad.
    return photos[-1]["file_id"]


def iso_datetime(unix_ts: int) -> str:
    return datetime.fromtimestamp(unix_ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main(raw_path: str):
    with open(raw_path, encoding="utf-8") as f:
        data = json.load(f)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    mensajes_rows = []
    apuestas_rows = []
    skipped = []  # (message_id, motivo) — para el resumen final

    for update in data["result"]:
        msg = update.get("message")
        if msg is None:
            continue  # eventos my_chat_member, migrate_to_chat_id, etc.

        message_id = msg["message_id"]
        texto = msg.get("caption") or msg.get("text") or ""
        foto_file_id = best_photo_file_id(msg.get("photo"))

        # Fecha real del pick: si el mensaje es un reenvío, la fecha que
        # importa para cruzar con resultados_galgos es la de publicación
        # original en el canal del tipster, no la de reenvío al grupo.
        # Timestamp completo (no solo la fecha) - igual que el bot en vivo
        # (Main.gs calcularFechaPick_ guarda un Date completo, no solo el
        # día); la fórmula posicion_auto ya usa INT() para quedarse solo
        # con el día al comparar, así que conservar la hora no rompe nada
        # y evita perder información real (detectado: se estaba guardando
        # como medianoche en vez de la hora real de publicación).
        forward_date = msg.get("forward_date") or msg.get("forward_origin", {}).get("date")
        fecha_pick = iso_datetime(forward_date) if forward_date else iso_datetime(msg["date"])
        fecha_recibido = iso_datetime(msg["date"])

        if not texto:
            mensajes_rows.append([message_id, fecha_recibido, texto, foto_file_id, "revision_manual"])
            skipped.append((message_id, "sin texto/caption"))
            continue

        campos = parse_pick_text(texto)
        faltan = [c for c in REQUIRED_FIELDS if c not in campos]

        if faltan:
            estado = "revision_manual"
            skipped.append((message_id, f"faltan campos: {', '.join(faltan)}"))
        else:
            estado = "procesado"

        mensajes_rows.append([message_id, fecha_recibido, texto, foto_file_id, estado])

        if estado == "procesado":
            cuota = float(campos["cuota"])
            stake = float(campos["stake"])
            apuestas_rows.append([
                message_id,           # message_id
                "",                   # confirm_message_id (no aplica en backfill)
                fecha_pick,           # fecha_pick
                campos["hipodromo"],  # hipodromo
                campos["hora_carrera"],  # hora_carrera
                campos["trampa"],     # trampa
                campos["seleccion"],  # seleccion
                cuota,                # cuota
                stake,                # stake (unidades)
                round(cuota * stake, 2),  # retorno_potencial
                "",                   # resultado_manual
                "FALSE",              # oculto
                "",                   # posible_duplicado_de
                now,                  # creado_en
            ])

    with open("data/mensajes_crudos.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["message_id", "fecha_recibido", "contenido", "foto_file_id", "estado"])
        w.writerows(mensajes_rows)

    with open("data/apuestas.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "message_id", "confirm_message_id", "fecha_pick", "hipodromo",
            "hora_carrera", "trampa", "seleccion", "cuota", "stake",
            "retorno_potencial", "resultado_manual", "oculto",
            "posible_duplicado_de", "creado_en",
        ])
        w.writerows(apuestas_rows)

    print(f"mensajes_crudos: {len(mensajes_rows)} filas -> data/mensajes_crudos.csv")
    print(f"apuestas: {len(apuestas_rows)} filas -> data/apuestas.csv")
    print(f"revision_manual: {len(skipped)}")
    for message_id, motivo in skipped:
        print(f"  - message_id {message_id}: {motivo}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "raw_updates_tmp.json")
