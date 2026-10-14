import os
import re
import tempfile
import unittest
from datetime import datetime
from unittest import mock
from zoneinfo import ZoneInfo

from premier_captacion import db, mensajes, sheet

from .apoyo import conexion, usuario

MADRID = ZoneInfo("Europe/Madrid")


def ts(*fecha_hora):
    return int(datetime(*fecha_hora, tzinfo=MADRID).timestamp())


# --- Imitación mínima de gspread (Worksheet / Spreadsheet) -----------------------

def _celda(a1):
    letras, numero = re.match(r"^([A-Z]+)(\d+)$", a1).groups()
    col = 0
    for letra in letras:
        col = col * 26 + ord(letra) - ord("A") + 1
    return int(numero), col


class WSFalsa:
    def __init__(self, title, rows=1000, cols=26):
        self.title = title
        self.row_count = rows
        self.col_count = cols
        self.celdas = {}
        self.llamadas = []

    # Lo que usa el código:
    def update(self, values, range_name, raw=True):
        self.llamadas.append(("update", range_name, raw))
        fila0, col0 = _celda(range_name)
        if fila0 + len(values) - 1 > self.row_count or col0 + max(len(f) for f in values) - 1 > self.col_count:
            raise AssertionError("la API rechaza escribir fuera de la cuadrícula")
        for i, fila in enumerate(values):
            for j, valor in enumerate(fila):
                self.celdas[(fila0 + i, col0 + j)] = valor

    def append_rows(self, values, value_input_option, table_range):
        self.llamadas.append(("append_rows", value_input_option))
        fila = self.ultima_fila() + 1
        necesarias = fila + len(values) - 1
        if necesarias > self.row_count:
            self.row_count = necesarias  # values.append amplía la hoja
        for i, f in enumerate(values):
            for j, valor in enumerate(f):
                self.celdas[(fila + i, 1 + j)] = valor

    def col_values(self, col, value_render_option):
        assert value_render_option == "UNFORMATTED_VALUE"
        return [self.celdas.get((r, col), "") for r in range(1, self.ultima_fila() + 1)]

    def batch_clear(self, rangos):
        self.llamadas.append(("batch_clear", rangos))
        for rango in rangos:
            desde, hasta = rango.split(":")
            (f1, c1), (f2, c2) = _celda(desde), _celda(hasta)
            for clave in list(self.celdas):
                if f1 <= clave[0] <= f2 and c1 <= clave[1] <= c2:
                    del self.celdas[clave]

    def resize(self, rows, cols):
        self.llamadas.append(("resize", rows, cols))
        self.row_count, self.col_count = rows, cols

    def freeze(self, rows):
        self.llamadas.append(("freeze", rows))

    def batch_format(self, formatos):
        self.llamadas.append(("batch_format", [f["range"] for f in formatos]))

    def get_all_values(self):
        # Como gspread: una pestaña vacía da [[]], no [].
        return self.tabla() or [[]]

    def update_title(self, title):
        self.title = title

    # Ayudas para los tests:
    def ultima_fila(self):
        return max((f for f, _ in self.celdas if self.celdas[(f, _)] not in ("", None)), default=0)

    def tabla(self):
        n = self.ultima_fila()
        ncols = max((c for _, c in self.celdas), default=0)
        return [[self.celdas.get((r, c), "") for c in range(1, ncols + 1)] for r in range(1, n + 1)]


class LibroFalso:
    def __init__(self, pestana_inicial="Hoja 1"):
        self.locale = "en_US"
        self.timezone = "Etc/GMT"
        self.hojas = [WSFalsa(pestana_inicial)]

    def update_locale(self, locale):
        self.locale = locale

    def update_timezone(self, tz):
        self.timezone = tz

    def worksheets(self):
        return list(self.hojas)

    def add_worksheet(self, title, rows, cols):
        ws = WSFalsa(title, rows, cols)
        self.hojas.append(ws)
        return ws

    def hoja(self, titulo):
        return next(ws for ws in self.hojas if ws.title == titulo)


def con_datos():
    con = conexion()
    with con:
        ana = usuario(500, "Ana", "ana")
        db.registrar_solicitud(con, ts(2026, 10, 14, 10, 0), ana, "landing")
        db.registrar_evento(con, ts(2026, 10, 14, 10, 0), "solicitud", 500, enlace="landing", retraso_s=2)
        db.marcar_bienvenida(con, 500, ts(2026, 10, 14, 10, 0), "bot_b_v1")
        db.registrar_evento(con, ts(2026, 10, 14, 10, 0), "bienvenida_enviada", 500, tipo_mensaje="bot_b_v1")
        db.registrar_evento(con, ts(2026, 10, 14, 10, 0), "aceptada", 500)
        malo = usuario(501, "=HYPERLINK(\"x\")", None)  # nombre con aspecto de fórmula
        db.registrar_solicitud(con, ts(2026, 10, 15, 9, 30), malo, None)
        db.registrar_evento(con, ts(2026, 10, 15, 9, 30), "solicitud", 501, enlace=None, retraso_s=400)
        db.registrar_evento(con, ts(2026, 10, 15, 9, 30), "bienvenida_fallida", 501, motivo="fuera_de_plazo")
        db.registrar_evento(con, ts(2026, 10, 15, 9, 31), "mensaje_al_bot", 501)
    return con


class TestConversion(unittest.TestCase):
    def test_numero_de_serie_en_hora_de_espana(self):
        # 14/10/2026 10:00 en Madrid: día 46309 de Sheets (+10/24).
        self.assertEqual(sheet.serie_dia(ts(2026, 10, 14, 10, 0), MADRID), 46309)
        self.assertAlmostEqual(sheet.serie_fecha_hora(ts(2026, 10, 14, 10, 0), MADRID), 46309 + 10 / 24, places=5)
        # 00:30 en Madrid ya es el día siguiente aunque en UTC sea el anterior.
        self.assertEqual(sheet.serie_dia(ts(2026, 10, 15, 0, 30), MADRID), 46310)

    def test_detalle_legible(self):
        self.assertEqual(sheet.texto_detalle({"enlace": "landing", "retraso_s": 3}), "enlace: landing; espera: 3 s")
        self.assertEqual(sheet.texto_detalle({"motivo": "fuera_de_plazo"}), "motivo: llevaba más de 5 min esperando")
        self.assertEqual(sheet.texto_detalle({"tipo_mensaje": "bot_b_v1"}), "")
        self.assertEqual(
            sheet.texto_detalle({"chat_id": -100, "chat_titulo": "Canal", "estado": "administrator", "puede_invitar": True}),
            "chat: Canal (-100); estado del bot: administrador; puede aceptar solicitudes: sí")


class TestSincronizar(unittest.TestCase):
    def setUp(self):
        self.con = con_datos()
        self.addCleanup(self.con.close)
        self.falso = LibroFalso()
        self.libro = sheet.LibroGoogle(self.falso)

    def sincronizar(self):
        return sheet.sincronizar(self.con, MADRID, self.libro)

    def test_primera_vez(self):
        resultado = self.sincronizar()
        self.assertEqual(resultado, {"usuarios": 2, "eventos_nuevos": 6, "dias": 2})
        self.assertEqual((self.falso.locale, self.falso.timezone), ("es_ES", "Europe/Madrid"))
        # La pestaña vacía inicial se ha reutilizado como «Usuarios».
        self.assertEqual([h.title for h in self.falso.hojas], ["Usuarios", "Eventos", "Resumen diario", "Tipos de mensaje"])

        usuarios = self.falso.hoja("Usuarios").tabla()
        self.assertEqual(usuarios[0], sheet.CABECERA_USUARIOS)
        self.assertEqual([f[0] for f in usuarios[1:]], [501, 500])  # más reciente arriba
        ana = usuarios[2]
        self.assertEqual(ana[1:4], ["Ana", "@ana", "es"])
        self.assertEqual(ana[6:9], [1, "landing", "bot_b_v1"])
        self.assertEqual(usuarios[1][1], '=HYPERLINK("x")')
        self.assertEqual(usuarios[1][10], 1)  # mensajes al bot

        eventos = self.falso.hoja("Eventos").tabla()
        self.assertEqual(eventos[0], sheet.CABECERA_EVENTOS)
        self.assertEqual([f[0] for f in eventos[1:]], [1, 2, 3, 4, 5, 6])
        self.assertEqual(eventos[2][5:7], ["Bienvenida enviada", "bot_b_v1"])
        self.assertEqual(eventos[1][4], "Ana (@ana)")

        resumen = self.falso.hoja("Resumen diario").tabla()
        self.assertEqual(resumen[:2], sheet.FILAS_CABECERA_RESUMEN)
        self.assertEqual([f[0] for f in resumen[2:]], [46310, 46309])
        self.assertEqual(resumen[2][1], "=COUNTIFS(Eventos!$C:$C;$A3;Eventos!$F:$F;B$2)")
        self.assertEqual(resumen[3][2], "=COUNTUNIQUEIFS(Eventos!$D:$D;Eventos!$C:$C;$A4;Eventos!$F:$F;C$2)")

        tipos = self.falso.hoja("Tipos de mensaje").tabla()
        self.assertEqual(tipos[1][:3], ["bot_b_v1", mensajes.TIPOS_MENSAJE["bot_b_v1"], "bot"])
        self.assertEqual(tipos[1][3], mensajes.TEXTO_BIENVENIDA)

    def test_solo_el_resumen_va_como_formulas(self):
        self.sincronizar()
        for hoja in self.falso.hojas:
            escrituras = [c for c in hoja.llamadas if c[0] == "update"]
            datos_crudos = all(raw for _, rango, raw in escrituras if hoja.title != "Resumen diario" or rango in ("A1",))
            self.assertTrue(datos_crudos, hoja.title)
            for c in hoja.llamadas:
                if c[0] == "append_rows":
                    self.assertEqual(c[1], "RAW")
        resumen = self.falso.hoja("Resumen diario")
        self.assertIn(("update", "A3", False), resumen.llamadas)

    def test_repetir_no_duplica_y_solo_anade_lo_nuevo(self):
        self.sincronizar()
        self.assertEqual(self.sincronizar()["eventos_nuevos"], 0)
        with self.con:
            db.registrar_evento(self.con, ts(2026, 10, 16, 8, 0), "solicitud", 500, enlace="landing")
        self.assertEqual(self.sincronizar(), {"usuarios": 2, "eventos_nuevos": 1, "dias": 3})
        eventos = self.falso.hoja("Eventos").tabla()
        self.assertEqual([f[0] for f in eventos[1:]], [1, 2, 3, 4, 5, 6, 7])
        self.assertEqual([f[0] for f in self.falso.hoja("Resumen diario").tabla()[2:]], [46311, 46310, 46309])

    def test_si_alguien_borra_eventos_del_sheet_se_rellenan(self):
        self.sincronizar()
        ws = self.falso.hoja("Eventos")
        ws.batch_clear(["A2:H1000"])
        self.assertEqual(self.sincronizar()["eventos_nuevos"], 6)

    def test_las_filas_sobrantes_se_vacian(self):
        self.sincronizar()
        ws = self.falso.hoja("Usuarios")
        ws.celdas[(10, 1)] = "fila vieja"
        self.sincronizar()
        self.assertNotIn((10, 1), ws.celdas)

    def test_crece_la_hoja_si_hacen_falta_mas_filas(self):
        with self.con:
            for i in range(1200):
                db.actualizar_datos_usuario(self.con, ts(2026, 10, 14, 12, 0), usuario(10_000 + i, f"U{i}", None))
        self.sincronizar()
        ws = self.falso.hoja("Usuarios")
        self.assertEqual(len(ws.tabla()), 1 + 1202)
        self.assertGreaterEqual(ws.row_count, 1203)

    def test_no_renombra_una_pestana_inicial_con_datos(self):
        falso = LibroFalso()
        falso.hojas[0].celdas[(1, 1)] = "mis notas"
        sheet.sincronizar(self.con, MADRID, sheet.LibroGoogle(falso))
        self.assertEqual([h.title for h in falso.hojas][:2], ["Hoja 1", "Usuarios"])
        self.assertEqual(falso.hoja("Hoja 1").celdas[(1, 1)], "mis notas")


class TestMain(unittest.TestCase):
    def entorno(self, carpeta, **extra):
        valores = {
            "CAPTACION_BOT_TOKEN": "123456:" + "Z" * 35,
            "CAPTACION_PERFIL": "Dronwhite",
            "CAPTACION_DB": os.path.join(carpeta, "prueba.db"),
        }
        valores.update(extra)
        return valores

    def test_sin_sheet_configurado_no_hace_nada(self):
        with tempfile.TemporaryDirectory() as carpeta, \
                mock.patch.dict(os.environ, self.entorno(carpeta), clear=True), \
                mock.patch("premier_captacion.sheet.abrir_libro") as abrir:
            self.assertEqual(sheet.main([]), 0)
        abrir.assert_not_called()

    def test_sin_credencial_falla_con_aviso(self):
        with tempfile.TemporaryDirectory() as carpeta, \
                mock.patch.dict(os.environ, self.entorno(carpeta, CAPTACION_SHEET_ID="x" * 44), clear=True):
            self.assertEqual(sheet.main([]), 2)

    def test_credencial_de_systemd(self):
        with tempfile.TemporaryDirectory() as carpeta:
            with open(os.path.join(carpeta, "google"), "w") as f:
                f.write('{"client_email": "cuenta@proyecto.iam.gserviceaccount.com"}')
            with mock.patch.dict(os.environ, {"CREDENTIALS_DIRECTORY": carpeta}, clear=True):
                self.assertEqual(sheet.ruta_credencial(), os.path.join(carpeta, "google"))
                self.assertEqual(sheet.correo_cuenta_servicio(sheet.ruta_credencial()),
                                 "cuenta@proyecto.iam.gserviceaccount.com")


if __name__ == "__main__":
    unittest.main()
