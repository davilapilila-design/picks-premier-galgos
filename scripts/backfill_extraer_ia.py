"""
Proceso AUTOMATIZADO de extracción de picks con la misma IA (Gemini) y el
mismo esquema que usa el bot en producción (src/AI.gs, extraerPick()).

Por qué existe: el backfill original (scripts/backfill_picks.py, 2026-08-20)
parseaba por regex, sin IA, y no sabía nada de apuestas dobles/tríples -
7 de 89 picks cayeron en revision_manual. El 2026-08-26 se resolvieron 4 de
esos 7 a mano (revisión manual mía, no repetible). Este script sustituye
esa revisión manual por el MISMO proceso que ya usa el bot real, para que
cualquier futuro backfill (o una repetición de este) sea automático y
consistente con lo que haría el bot en vivo - no una lectura ad-hoc.

IMPORTANTE: el prompt de aquí abajo debe mantenerse IDÉNTICO al de
EXTRACTION_SYSTEM_PROMPT en src/AI.gs. Si se cambia uno, cambiar el otro.

Uso:
    python scripts/backfill_extraer_ia.py
Lee data/mensajes_crudos.csv (columna `contenido`), llama a Gemini para
cada mensaje y escribe data/apuestas_ia.csv (una fila por pata,
tipo_apuesta) + data/apuestas_ia_rechazados.csv (motivo de rechazo) - no
toca la Google Sheet, eso es un paso aparte una vez se ha revisado la
salida.
"""

import csv
import json
import os
import time
import urllib.request
import urllib.error

GEMINI_MODEL = "gemini-3.6-flash"

# Copiado literalmente de src/AI.gs (EXTRACTION_SYSTEM_PROMPT) - mismo
# contrato de entrada/salida que usa el bot real.
EXTRACTION_SYSTEM_PROMPT = """Extraes datos estructurados de picks de apuestas de galgos (carreras de
perros) enviados por un tipster a un grupo de Telegram. El texto puede
venir con erratas (p. ej. "Ciota" en vez de "Cuota", o ";" en vez de ":"
en la hora) - interprétalas igualmente si el significado es claro.

Un pick puede ser una apuesta SIMPLE (1 carrera), o una combinada de
varias carreras con una sola cuota conjunta ("Apuesta Doble" = 2
carreras, "Apuesta Tríple" = 3 carreras). Cada carrera de la combinada
es una "pata": mismo formato que una apuesta simple (hipódromo, hora,
trampa, selección), una tras otra en el texto.

Devuelve SOLO un JSON con esta forma exacta, sin texto adicional:
{
  "tipo_apuesta": "simple" | "doble" | "triple" | "otro",
  "patas": [
    { "hipodromo": string o null, "hora_carrera": string "HH:MM" o null,
      "trampa": string (solo el número) o null,
      "seleccion": string (nombre del galgo) o null }
  ],
  "cuota": number o null,
  "stake": number o null
}

Reglas:
- "tipo_apuesta": "simple" si es 1 sola carrera, "doble" si son 2,
  "triple" si son 3. Si es cualquier otra cosa (Trixie, Yankee, apuesta
  "a puesto"/colocado, 4+ carreras, o no estás seguro del tipo), pon
  "otro" - en ese caso rellena "patas" con lo que puedas identificar de
  todas formas (ayuda a la revisión manual), no lo dejes vacío si hay
  datos reconocibles.
- "patas" tiene tantos elementos como carreras: 1 para "simple", 2 para
  "doble", 3 para "triple".
- "cuota" y "stake" son SIEMPRE los de la apuesta conjunta entera (la
  única cuota y el único stake que aparecen en el mensaje), nunca por
  carrera - no hay una cuota distinta por pata.
- La palabra "Galgo" antes del número de trampa es opcional, ignórala.
- El hipódromo y la hora de cada carrera pueden aparecer en cualquier
  orden en su línea.
- Si un campo no aparece o no estás seguro, ponlo a null. No inventes
  valores."""

TIPOS_APUESTA_SOPORTADOS = ["simple", "doble", "triple"]
CAMPOS_OBLIGATORIOS_PATA = ["hipodromo", "hora_carrera", "trampa", "seleccion"]
NUM_PATAS_POR_TIPO = {"simple": 1, "doble": 2, "triple": 3}


def get_api_key():
    with open(os.path.join(os.path.dirname(__file__), "..", ".env"), encoding="utf-8") as f:
        for line in f:
            if line.startswith("AI_PROVIDER_API_KEY"):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise RuntimeError("AI_PROVIDER_API_KEY no encontrada en .env")


def call_gemini(texto, api_key, reintentos=5):
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}"
        f":generateContent?key={api_key}"
    )
    payload = {
        "system_instruction": {"parts": [{"text": EXTRACTION_SYSTEM_PROMPT}]},
        "contents": [{"role": "user", "parts": [{"text": texto or "(sin texto, solo imagen)"}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "thinkingConfig": {"thinkingBudget": 128},
        },
    }
    req_data = json.dumps(payload).encode("utf-8")
    # Tier gratis de Gemini: límite bajo de peticiones/minuto - probado en
    # caliente que sin backoff, tras las primeras ~2 peticiones, todo lo
    # demás falla con 429 (no es hipotético, se vio en la primera pasada).
    espera = 5
    for intento in range(reintentos):
        req = urllib.request.Request(
            url, data=req_data,
            headers={"Content-Type": "application/json"}, method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = json.load(resp)
            texto_respuesta = body["candidates"][0]["content"]["parts"][0]["text"].strip()
            return json.loads(texto_respuesta)
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and intento < reintentos - 1:
                print(f"    429, reintento en {espera}s...")
                time.sleep(espera)
                espera = min(espera * 2, 60)
                continue
            raise


def validar(extraido):
    """Mismo contrato que extraerPick() en src/AI.gs, en Python."""
    tipo = extraido.get("tipo_apuesta")
    if tipo not in TIPOS_APUESTA_SOPORTADOS:
        return {"ok": False, "motivo": "tipo_no_soportado", "tipo_apuesta": tipo, "patas_crudas": extraido.get("patas")}

    patas = extraido.get("patas") or []
    if len(patas) != NUM_PATAS_POR_TIPO[tipo]:
        return {"ok": False, "motivo": "num_patas_incorrecto", "tipo_apuesta": tipo}

    campos_faltantes = []
    for i, pata in enumerate(patas):
        for campo in CAMPOS_OBLIGATORIOS_PATA:
            if pata.get(campo) in (None, ""):
                campos_faltantes.append(f"pata{i+1}.{campo}")
    if extraido.get("cuota") in (None, ""):
        campos_faltantes.append("cuota")
    if extraido.get("stake") in (None, ""):
        campos_faltantes.append("stake")

    if campos_faltantes:
        return {"ok": False, "motivo": "faltan_campos", "campos_faltantes": campos_faltantes}

    return {
        "ok": True,
        "tipo_apuesta": tipo,
        "cuota": float(extraido["cuota"]),
        "stake": float(extraido["stake"]),
        "patas": [
            {
                "hipodromo": p["hipodromo"],
                "hora_carrera": p["hora_carrera"],
                "trampa": str(p["trampa"]),
                "seleccion": p["seleccion"],
            }
            for p in patas
        ],
    }


def main():
    api_key = get_api_key()
    repo_root = os.path.join(os.path.dirname(__file__), "..")
    with open(os.path.join(repo_root, "data", "mensajes_crudos.csv"), encoding="utf-8") as f:
        mensajes = list(csv.DictReader(f))
    mensajes.sort(key=lambda r: int(r["message_id"]))

    resultados = []
    for i, msg in enumerate(mensajes, 1):
        mid = msg["message_id"]
        try:
            extraido = call_gemini(msg["contenido"], api_key)
            validado = validar(extraido)
        except Exception as exc:
            validado = {"ok": False, "motivo": "error_ia", "error": str(exc)}
        validado["message_id"] = mid
        resultados.append(validado)
        print(f"[{i}/{len(mensajes)}] {mid}: " + (
            f"OK {validado['tipo_apuesta']}" if validado["ok"] else f"RECHAZADO ({validado['motivo']})"
        ))
        time.sleep(4.5)  # tier gratis de Gemini: ~15 peticiones/min como mucho

    out_path = os.path.join(repo_root, "data", "apuestas_ia_backfill.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(resultados, f, ensure_ascii=False, indent=1)
    print(f"\nGuardado: {out_path}")
    ok = sum(1 for r in resultados if r["ok"])
    print(f"OK: {ok} / {len(resultados)} - rechazados: {len(resultados) - ok}")


if __name__ == "__main__":
    main()
