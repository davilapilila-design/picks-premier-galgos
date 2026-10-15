"""
El volcado al Sheet (sheet.py) con gspread REAL sobre un cliente HTTP falso
que imita la API de Google Sheets: comprueba las peticiones exactas que se
harían (sin red). Se salta si gspread no está instalado.
"""
import json
import unittest
from zoneinfo import ZoneInfo

try:
    from gspread.http_client import HTTPClient
    from gspread.spreadsheet import Spreadsheet
except ImportError:  # pragma: no cover
    HTTPClient = object
    Spreadsheet = None

from premier_captacion import sheet

from .test_sheet import con_datos


class HTTPFalso(HTTPClient):
    def __init__(self):  # sin llamar al de gspread: no hay credenciales
        self.peticiones = []
        self.hojas = [{"properties": {"sheetId": 0, "title": "Sheet1", "index": 0,
                                      "gridProperties": {"rowCount": 1000, "columnCount": 26}}}]

    def fetch_sheet_metadata(self, id, params=None):
        self.peticiones.append(("metadata",))
        return {"properties": {"title": "Captación", "locale": "en_US", "timeZone": "Etc/GMT"},
                "sheets": json.loads(json.dumps(self.hojas))}

    def batch_update(self, id, body):
        respuestas = []
        for r in body["requests"]:
            clave = next(iter(r))
            self.peticiones.append(("batchUpdate", clave, r[clave]))
            if clave == "addSheet":
                nuevo = {"properties": {"sheetId": 100 + len(self.hojas), "index": len(self.hojas),
                                        **r[clave]["properties"]}}
                self.hojas.append(nuevo)
                respuestas.append({"addSheet": nuevo})
            else:
                respuestas.append({})
        return {"replies": respuestas}

    def values_update(self, id, rango, params=None, body=None):
        self.peticiones.append(("values.update", rango, str(params["valueInputOption"]), body["values"]))
        return {}

    def values_append(self, id, rango, params=None, body=None):
        self.peticiones.append(("values.append", rango, str(params["valueInputOption"]), body["values"]))
        return {}

    def values_batch_clear(self, id, params=None, body=None):
        self.peticiones.append(("values.batchClear", body["ranges"]))
        return {}

    def values_get(self, id, rango, params=None):
        self.peticiones.append(("values.get", rango))
        return {"range": rango}


@unittest.skipIf(Spreadsheet is None, "gspread no está instalado")
class TestConGspreadReal(unittest.TestCase):
    def test_peticiones(self):
        con = con_datos()
        self.addCleanup(con.close)
        http = HTTPFalso()
        resultado = sheet.sincronizar(con, ZoneInfo("Europe/Madrid"), sheet.LibroGoogle(Spreadsheet(http, {"id": "x"})))
        self.assertEqual(resultado["usuarios"], 2)
        tipos = [p[1] for p in http.peticiones if p[0] == "batchUpdate"]
        self.assertEqual(tipos[:2], ["updateSpreadsheetProperties", "updateSpreadsheetProperties"])
        # La pestaña vacía inicial se renombra en vez de crear otra.
        renombrado = next(p for p in http.peticiones if p[0] == "batchUpdate" and p[1] == "updateSheetProperties")
        self.assertEqual(renombrado[2]["properties"]["title"], "Usuarios")
        escrituras = [p for p in http.peticiones if p[0] in ("values.update", "values.append")]
        for _, rango, modo, valores in escrituras:
            if rango == "'Resumen diario'!A3":
                self.assertIn("USER_ENTERED", modo)
                self.assertTrue(valores[0][1].startswith("=COUNTIFS("))
            else:
                self.assertIn("RAW", modo, rango)
        nombres = [str(v) for _, _, _, valores in escrituras for fila in valores for v in fila]
        self.assertIn('=HYPERLINK("x")', nombres)  # llega como texto (RAW), no como fórmula


if __name__ == "__main__":
    unittest.main()
