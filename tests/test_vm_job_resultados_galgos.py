"""Tests del job de la VM que rellena `resultados_galgos` (scripts/vm_job_resultados_galgos.py).

Horas (2026-10-29): la hora de la hoja (`apuestas_patas.hora_carrera`) es la de Madrid y el
`rTime` de `results_enriched.parquet` es la hora de Reino Unido. Casos reales a los dos lados
del cambio de hora del 25/10/2026.
"""
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import vm_job_resultados_galgos as job  # noqa: E402

MADRID = ZoneInfo("Europe/Madrid")


def test_hora_de_la_hoja_a_rtime_en_verano():
    # 24/10/2026 (verano británico): Central Park 18:50 en la hoja es el rTime 17:50 (resuelta)
    assert job.rtime_uk(date(2026, 10, 24), "18:50") == "2026-10-24 17:50"


def test_hora_de_la_hoja_a_rtime_en_invierno():
    # 25/10/2026 (ya en invierno): Sheffield 16:44 en la hoja es la carrera de las 15:44 UK
    assert job.rtime_uk(date(2026, 10, 25), "16:44") == "2026-10-25 15:44"


def _pata(msg, fecha, cano, hora, trap="2"):
    return [msg, "1", fecha, cano, hora, trap, "galgo", ""]


def test_ya_corrida_se_mide_en_hora_de_madrid():
    patas = [_pata("583", "25/10/2026", "Sheffield", "16:44")]
    # `limite` ya trae restado el margen (lo hace main): la carrera es a las 16:44 de Madrid.
    # Tomándola como hora UK (el fallo) parecería de las 17:44 de Madrid y seguiría «futura».
    antes = datetime(2026, 10, 25, 16, 43, tzinfo=MADRID)
    despues = datetime(2026, 10, 25, 16, 45, tzinfo=MADRID)
    pend, _, futuras = job.calcular_pendientes(patas, set(), antes)
    assert pend == [] and futuras == 1
    pend, _, _ = job.calcular_pendientes(patas, set(), despues)
    assert len(pend) == 1 and pend[0]["rtime_uk"] == "2026-10-25 15:44"


def _df(*carreras):
    filas = []
    for race_id, rtime, cano in carreras:
        for trap, pos in ((1, "1"), (2, "2"), (3, "3")):
            filas.append({"Fecha": rtime[:10], "rTime": rtime, "race_id": race_id, "Canodromo": cano,
                          "track_id": "50", "trap": trap, "name": f"galgo {trap}", "position": pos,
                          "fract": "2/1", "dogId": f"{race_id}{trap}"})
    return pd.DataFrame(filas)


def test_resuelve_la_carrera_exacta_con_la_hora_uk():
    pend, _, _ = job.calcular_pendientes([_pata("583", "25/10/2026", "Sheffield", "16:44")], set(),
                                         datetime(2026, 10, 26, 12, 0, tzinfo=MADRID))
    df = _df(("111", "2026-10-25 15:44", "Sheffield"), ("112", "2026-10-25 16:41", "Sheffield"))
    filas, sin_datos = job.resolver_contra_parquet(pend, df)
    assert sin_datos == 0 and len(filas) == 3
    # se guarda con la hora de la hoja (la clave de las fórmulas) y el race_id de RP
    assert {(f[0], f[1], f[2], f[9]) for f in filas} == {("Sheffield", "25/10/2026", "16:44", "111")}
    assert "r_time=15%3A44" in filas[0][8]          # el enlace lleva la hora real de la carrera


def test_sin_coincidencia_exacta_queda_pendiente():
    # Dunstall Park 10/10 21:54 (Madrid) = 20:54 UK: no hay carrera a esa hora (sí a las 21:54 UK)
    pend, _, _ = job.calcular_pendientes([_pata("446", "10/10/2026 18:36:43", "Dunstall Park", "21:54")],
                                         set(), datetime(2026, 10, 29, 12, 0, tzinfo=MADRID))
    df = _df(("201", "2026-10-10 20:38", "Dunstall Park"), ("202", "2026-10-10 21:54", "Dunstall Park"))
    filas, sin_datos = job.resolver_contra_parquet(pend, df)
    assert filas == [] and sin_datos == 1


def test_dos_carreras_a_la_misma_hora_no_se_resuelven():
    pend, _, _ = job.calcular_pendientes([_pata("600", "28/10/2026", "Harlow", "15:11")], set(),
                                         datetime(2026, 10, 29, 12, 0, tzinfo=MADRID))
    df = _df(("301", "2026-10-28 14:11", "Harlow"), ("302", "2026-10-28 14:11", "Harlow"))
    filas, sin_datos = job.resolver_contra_parquet(pend, df)
    assert filas == [] and sin_datos == 1


# ── Enlace a la ficha del resultado en Racing Post (29/10/2026) ─────────────

def test_mapa_de_track_ids_de_las_filas_antiguas():
    df = pd.DataFrame({"Canodromo": ["Harlow", "Harlow", "Hove", "Hove", "Romford", "Romford", "Yarmouth"],
                       "track_id": ["61", None, "None", "50", "62", "63", ""]})
    # Hove: solo su id numérico; Romford: dos ids distintos, no se adivina; Yarmouth: sin id
    assert job.mapa_track_ids(df) == {"harlow": "61", "hove": "50"}


def test_las_filas_nuevas_llevan_el_enlace_aunque_el_parquet_no_traiga_track_id():
    pend, _, _ = job.calcular_pendientes([_pata("583", "25/10/2026", "Sheffield", "16:44")], set(),
                                         datetime(2026, 10, 26, 12, 0, tzinfo=MADRID))
    df = _df(("111", "2026-10-25 15:44", "Sheffield")).assign(track_id=None)
    df = pd.concat([df, pd.DataFrame([{"Fecha": "2026-03-01", "rTime": "2026-03-01 12:00", "race_id": "9",
                                       "Canodromo": "Sheffield", "track_id": "8", "trap": 1, "name": "x",
                                       "position": "1", "fract": "1/1", "dogId": "1"}])])
    filas, _ = job.resolver_contra_parquet(pend, df)
    assert filas[0][8] == ("https://greyhoundbet.racingpost.com/#result-meeting-result/"
                           "race_id=111&track_id=8&r_date=2026-10-25&r_time=15%3A44")


def test_urls_para_rellenar_las_filas_sin_enlace():
    df = pd.concat([_df(("111", "2026-10-25 15:44", "Sheffield"), ("222", "2026-10-26 11:21", "Harlow"))
                    .assign(track_id=None),
                    pd.DataFrame([{"Fecha": "2026-03-01", "rTime": "2026-03-01 12:00", "race_id": "9",
                                   "Canodromo": "Sheffield", "track_id": "8", "trap": 1, "name": "x",
                                   "position": "1", "fract": "1/1", "dogId": "1"}])])
    existentes = [
        ["Sheffield", "25/10/2026", "16:44", "2", "a", "1", "ts", "2", "", "111", "d"],    # sin enlace
        ["Sheffield", "25/10/2026", "16:44", "1", "b", "2", "ts", "3", "ya", "111", "d"],  # ya lo tiene
        ["Harlow", "26/10/2026", "12:21", "5", "c", "1", "ts", "2", "", "222", "d"],       # Harlow sin id
        ["Hove", "25/10/2026", "18:49", "1", "e", "1", "ts", "2", "", "", "d"],            # sin race_id
        ["Hove", "25/10/2026", "18:49", "1", "e", "1", "ts", "2", "", "333", "d"],         # no está en el parquet
    ]
    assert job.urls_para_rellenar(existentes, df) == [
        (2, "https://greyhoundbet.racingpost.com/#result-meeting-result/"
            "race_id=111&track_id=8&r_date=2026-10-25&r_time=15%3A44")]


class _HojaFalsa:
    """Imita lo que usa el job de un worksheet de gspread: `row_count`, `add_rows`, `update`."""

    def __init__(self, filas):
        self.row_count = filas
        self.anadidas = []
        self.escrito = None

    def add_rows(self, n):
        self.anadidas.append(n)
        self.row_count += n

    def update(self, values=None, range_name=None, **kw):
        assert range_name is not None and values is not None   # orden nuevo de gspread
        fin = int(range_name.split(":")[1].lstrip("ABCDEFGHIJK"))
        if fin > self.row_count:                               # lo que devuelve Google
            raise RuntimeError(f"Range ({range_name}) exceeds grid limits")
        self.escrito = (range_name, values)


def test_hoja_llena_anade_filas_antes_de_escribir():
    # 29/10/2026: resultados_galgos tenía 1012 filas, todas ocupadas, y las 4 de Central Park
    # (12 filas) iban a la 1013-1024 → «exceeds grid limits» en cada pasada.
    hoja = _HojaFalsa(1012)
    filas = [["central park"] + [""] * 10] * 12
    job.escribir_filas(hoja, 1013, filas)
    assert hoja.row_count >= 1024 and hoja.anadidas
    assert hoja.escrito == ("A1013:K1024", filas)


def test_con_sitio_no_anade_filas():
    hoja = _HojaFalsa(2000)
    job.escribir_filas(hoja, 1013, [["x"] * 11])
    assert hoja.anadidas == [] and hoja.escrito[0] == "A1013:K1013"
