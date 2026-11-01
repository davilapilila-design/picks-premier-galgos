"""Comprobación continua de cada correo frente a su persona, pestaña
«Correos · comprobación» y avisos del bot (comprobacion.py). Datos INVENTADOS."""
import unittest
from zoneinfo import ZoneInfo

from premier_captacion import comprobacion as cp
from premier_captacion import db, pagos

from .apoyo import PROPIETARIO, APIFalsa, config
from .test_cruce import compra, miembro, persona

B, M, S = "buena", "mala", "sin"


def juicios(*lista):
    return [(1000 * (i + 1), j) for i, j in enumerate(lista)]


class TestResumenCorreo(unittest.TestCase):
    def resumen(self, lista, origen="por_correo"):
        return cp.resumen_correo(juicios(*lista), origen)

    def test_ok(self):
        r = self.resumen([B, B, B, S])
        self.assertEqual((r["estado"], r["compras"], r["comprobables"], r["buenas"], r["malas"]),
                         (cp.OK, 4, 3, 3, 0))
        self.assertEqual(r["ultima_buena"], 3000)

    def test_vigilar_si_aun_no_llega_a_tres_buenas(self):
        self.assertEqual(self.resumen([B, B], origen="por_nombre")["estado"], cp.VIGILAR)

    def test_lo_del_dueno_no_necesita_tres_buenas(self):
        self.assertEqual(self.resumen([B, S], origen="manual")["estado"], cp.OK)

    def test_vigilar_con_una_mala_suelta(self):
        r = self.resumen([B, B, B, B, M, B])
        self.assertEqual(r["estado"], cp.VIGILAR)
        self.assertIn("1 mala", r["motivo"])

    def test_revisar_con_dos_malas_seguidas_al_final(self):
        r = self.resumen([B, B, B, B, B, B, M, S, M])
        self.assertEqual(r["estado"], cp.REVISAR)
        self.assertIn("2 últimas", r["motivo"])

    def test_dos_malas_que_no_son_las_ultimas_no_es_revisar(self):
        self.assertEqual(self.resumen([B, B, B, B, B, B, B, B, M, M, B])["estado"], cp.VIGILAR)

    def test_revisar_si_bajan_del_80_por_ciento(self):
        r = self.resumen([B, M, B, M, B, B])  # 4 de 6
        self.assertEqual(r["estado"], cp.REVISAR)
        self.assertIn("4 buenas de 6", r["motivo"])

    def test_revisar_si_ninguna_buena_en_las_ultimas_cinco(self):
        r = self.resumen([B, B, B, S, S, S, S, S])  # 2 buenas y luego nada
        self.assertEqual(r["estado"], cp.REVISAR)
        self.assertIn("últimas 5", r["motivo"])

    def test_sin_persona(self):
        self.assertEqual(self.resumen([B, B], origen=None)["estado"], cp.SIN_ASIGNAR)


class ConCruce(unittest.TestCase):
    def setUp(self):
        self.con = db.abrir(":memory:")
        self.addCleanup(self.con.close)
        self.tz = ZoneInfo("Europe/Madrid")
        persona(self.con, 500, nombre="Ana", username="ana")
        persona(self.con, 501, nombre="Luis", username="luis")
        for i in range(1, 4):  # ana@: OK
            compra(self.con, f"a{i}", i, 1000 * i, "ana@example.com", entra=500)
        for i in range(4, 7):  # bea@: Luis, y luego dos compras sin entrar
            compra(self.con, f"b{i}", i, 1000 * i, "bea@example.com", entra=501)
        self.fijar()  # una sincronización: bea@ queda de Luis
        for i in range(7, 9):
            compra(self.con, f"b{i}", i, 1000 * i, "bea@example.com")
            miembro(self.con, i, 501, 1000 * i + 900)  # entró 15 min después
        compra(self.con, "c1", 9, 9000, "cris@example.com", entra=500)  # sin persona

    def fijar(self):
        from premier_captacion import cruce
        with self.con:
            cruce.guardar_asignados(self.con, cruce.calcular(self.con), ahora=1)

    def estados(self):
        from premier_captacion import cruce
        return cp.estados(cruce.calcular(self.con))


class TestEstados(ConCruce):
    def test_estado_de_cada_correo(self):
        e = self.estados()
        self.assertEqual(e["ana@example.com"]["estado"], cp.OK)
        self.assertEqual(e["bea@example.com"]["estado"], cp.REVISAR)
        self.assertEqual(e["bea@example.com"]["user_id"], 501)  # no pierde a su persona
        self.assertEqual(e["cris@example.com"]["estado"], cp.SIN_ASIGNAR)
        self.assertEqual(e["cris@example.com"]["user_id"], 500)  # su mejor candidata

    def test_pestana_con_revisar_arriba_y_en_rojo(self):
        from premier_captacion import sheet

        from .test_sheet import LibroFalso
        falso = LibroFalso()
        libro = sheet.LibroGoogle(falso)
        libro.preparar()
        pagos.escribir_pestanas(self.con, self.tz, libro)
        hoja = falso.hoja(cp.TAB)
        tabla = hoja.tabla()
        self.assertEqual(tabla[0], cp.CABECERA)
        self.assertEqual([f[0] for f in tabla[1:]], ["bea@example.com", "cris@example.com", "ana@example.com"])
        bea = tabla[1]
        self.assertEqual((bea[2], bea[3], bea[4], bea[5], bea[6]), (501, 5, 5, 3, 2))
        self.assertIn("Luis", bea[1])
        self.assertEqual(bea[8], cp.REVISAR)
        self.assertIn(("batch_format", ["A2:J", "A2:J2", "H2:H"]), hoja.llamadas)


class TestAvisos(ConCruce):
    def setUp(self):
        super().setUp()
        self.textos = []
        self.va_bien = True

    def avisar(self, texto):
        self.textos.append(texto)
        return self.va_bien

    def cambios(self, estados=None):
        return cp.avisar_cambios(self.con, estados or self.estados(), self.avisar, ahora=1)

    def test_la_primera_vez_un_solo_mensaje_con_cuantos_hay(self):
        self.cambios()
        self.assertEqual(len(self.textos), 1)
        self.assertIn("1 correo", self.textos[0])
        self.cambios()
        self.assertEqual(len(self.textos), 1)  # no se repite

    def test_despues_un_mensaje_por_correo_que_cae_y_solo_una_vez(self):
        e = self.estados()
        bien = {c: dict(d, estado=cp.OK) for c, d in e.items()}
        self.cambios(bien)  # la primera vez, todo bien: ningún mensaje
        self.assertEqual(self.textos, [])
        self.cambios(e)
        self.assertEqual(len(self.textos), 1)
        self.assertIn("bea@example.com", self.textos[0])
        self.assertIn("Luis", self.textos[0])
        self.cambios(e)
        self.assertEqual(len(self.textos), 1)

    def test_vuelve_a_avisar_si_pasa_por_ok_y_cae_otra_vez(self):
        e = self.estados()
        bien = {c: dict(d, estado=cp.OK) for c, d in e.items()}
        vigilar = {c: dict(d, estado=cp.VIGILAR) for c, d in e.items()}
        self.cambios(bien)
        self.cambios(e)
        self.cambios(vigilar)
        self.cambios(e)
        self.assertEqual(len(self.textos), 1)  # pasar por «vigilar» no rearma
        self.cambios(bien)
        self.cambios(e)
        self.assertEqual(len(self.textos), 2)

    def test_si_el_mensaje_no_sale_se_reintenta(self):
        e = self.estados()
        self.cambios({c: dict(d, estado=cp.OK) for c, d in e.items()})
        self.va_bien = False
        self.cambios(e)
        self.va_bien = True
        self.cambios(e)
        self.assertEqual(len(self.textos), 2)
        self.cambios(e)
        self.assertEqual(len(self.textos), 2)

    def test_sin_bot_no_hace_nada(self):
        self.assertEqual(cp.avisar_cambios(self.con, self.estados(), None, ahora=1), 0)

    def test_la_sincronizacion_del_sheet_avisa(self):
        from premier_captacion import sheet

        from .test_sheet import LibroFalso
        sheet.sincronizar(self.con, self.tz, sheet.LibroGoogle(LibroFalso()), avisar=self.avisar)
        self.assertEqual(len(self.textos), 1)
        self.assertIn("revisar", self.textos[0])


class TestAvisoPorBot(unittest.TestCase):
    def test_manda_al_dueno(self):
        api = APIFalsa()
        avisar = cp.aviso_por_bot(config(), api=api)
        self.assertTrue(avisar("hola"))
        self.assertEqual([p["text"] for p in api.envios_a(PROPIETARIO)], ["hola"])

    def test_si_telegram_falla_dice_que_no(self):
        from premier_captacion.telegram_api import ErrorRed
        api = APIFalsa()
        api.fallos["sendMessage"] = [ErrorRed("sin red")]
        self.assertFalse(cp.aviso_por_bot(config(), api=api)("hola"))

    def test_sin_bot_o_sin_dueno_no_hay_aviso(self):
        self.assertIsNone(cp.aviso_por_bot(config(propietario_id=None)))
        self.assertIsNone(cp.aviso_por_bot(config(bot_token=None)))


if __name__ == "__main__":
    unittest.main()
