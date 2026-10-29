import asyncio
import importlib.util
import threading
import time
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest import mock

from premier_captacion import carpetas, db, guardia, lector, mensajes
from premier_captacion.config import ErrorConfig, cargar_config



def peticion(nombre, **atributos):
    """Objeto con el mismo módulo y clase que una petición de Telethon."""
    espacio, clase = nombre.split(".")
    tipo = type(clase, (), {"__module__": f"telethon.tl.functions.{espacio}"})
    objeto = tipo()
    objeto.__dict__.update(atributos)
    return objeto


class TestGuardia(unittest.TestCase):
    def test_lectura_y_carpetas(self):
        guardia.comprobar(peticion("messages.GetDialogFiltersRequest"), "lector")
        guardia.comprobar(peticion("messages.UpdateDialogFilterRequest"), "lector")
        guardia.comprobar(peticion("messages.CheckChatInviteRequest"), "historico")
        guardia.comprobar([peticion("users.GetUsersRequest"), peticion("updates.GetStateRequest")], "lector")

    def test_nada_de_enviar_leer_ni_unirse_en_ningun_modo(self):
        for nombre in ("messages.SendMessageRequest", "messages.ReadHistoryRequest",
                       "messages.ImportChatInviteRequest", "channels.JoinChannelRequest",
                       "messages.ForwardMessagesRequest", "messages.DeleteHistoryRequest",
                       "auth.LogOutRequest", "messages.SetTypingRequest"):
            for modo in guardia.MODOS:
                with self.subTest(nombre=nombre, modo=modo), self.assertRaises(guardia.PeticionProhibida):
                    guardia.comprobar(peticion(nombre), modo)

    def test_en_el_historico_y_en_simulacion_no_se_tocan_carpetas(self):
        for modo in ("historico", "simulacion"):
            with self.subTest(modo), self.assertRaises(guardia.PeticionProhibida):
                guardia.comprobar(peticion("messages.UpdateDialogFilterRequest"), modo)
        guardia.comprobar(peticion("account.UpdateStatusRequest", offline=True), "simulacion")
        guardia.comprobar(peticion("messages.GetDialogFiltersRequest"), "simulacion")

    def test_estado_solo_no_en_linea(self):
        guardia.comprobar(peticion("account.UpdateStatusRequest", offline=True), "lector")
        with self.assertRaises(guardia.PeticionProhibida):
            guardia.comprobar(peticion("account.UpdateStatusRequest", offline=False), "lector")

    def test_una_lista_con_una_prohibida_se_bloquea_entera(self):
        with self.assertRaises(guardia.PeticionProhibida):
            guardia.comprobar([peticion("users.GetUsersRequest"), peticion("messages.SendMessageRequest")], "lector")

    def test_suscriptores_solo_en_su_modo_y_sin_carpetas(self):
        guardia.comprobar(peticion("channels.GetParticipantsRequest"), "suscriptores")
        for modo in ("historico", "simulacion", "lector"):
            with self.subTest(modo), self.assertRaises(guardia.PeticionProhibida):
                guardia.comprobar(peticion("channels.GetParticipantsRequest"), modo)
        with self.assertRaises(guardia.PeticionProhibida):
            guardia.comprobar(peticion("messages.UpdateDialogFilterRequest"), "suscriptores")

    def test_invitaciones_solo_lee_quien_se_unio_con_cada_enlace(self):
        guardia.comprobar(peticion("messages.GetChatInviteImportersRequest"), "invitaciones")
        guardia.comprobar(peticion("messages.CheckChatInviteRequest"), "invitaciones")
        for modo in ("historico", "simulacion", "lector", "suscriptores", "ventas"):
            with self.subTest(modo), self.assertRaises(guardia.PeticionProhibida):
                guardia.comprobar(peticion("messages.GetChatInviteImportersRequest"), modo)
        # Ni crear, cambiar, anular o borrar enlaces, ni aceptar solicitudes.
        for nombre in ("messages.ExportChatInviteRequest", "messages.EditExportedChatInviteRequest",
                       "messages.DeleteExportedChatInviteRequest", "messages.HideChatJoinRequestRequest",
                       "messages.HideAllChatJoinRequestsRequest", "messages.UpdateDialogFilterRequest",
                       "channels.GetParticipantsRequest", "channels.GetAdminLogRequest"):
            with self.subTest(nombre), self.assertRaises(guardia.PeticionProhibida):
                guardia.comprobar(peticion(nombre), "invitaciones")

    def test_iniciar_sesion_solo_en_su_modo(self):
        guardia.comprobar(peticion("auth.SendCodeRequest"), "iniciar-sesion")
        with self.assertRaises(guardia.PeticionProhibida):
            guardia.comprobar(peticion("auth.SendCodeRequest"), "lector")


class TestAjustes(unittest.TestCase):
    BASE = {"CAPTACION_DB": "/tmp/x.db", "CAPTACION_CANAL_ID": "-1001234567890"}

    def test_lector_sin_bot_y_simulacion_por_defecto(self):
        cfg = cargar_config(self.BASE, requiere_bot=False)
        self.assertIsNone(cfg.bot_token)
        aj = lector.ajustes_desde({}, cfg)
        self.assertTrue(aj.simular)
        self.assertEqual((aj.canal_principal, aj.dias, aj.max_free_send, aj.nombre_free_send),
                         (1234567890, 5, 90, "free send"))
        self.assertFalse(lector.ajustes_desde({"CAPTACION_LECTOR_SIMULAR": "0"}, cfg).simular)
        self.assertFalse(aj.bienvenidas_manuales)
        self.assertTrue(lector.ajustes_desde({"CAPTACION_BIENVENIDAS_MANUALES": "1"}, cfg).bienvenidas_manuales)
        with self.assertRaises(ErrorConfig):
            lector.ajustes_desde({"CAPTACION_DIAS_CARPETAS": "0"}, cfg)

    def test_el_bot_sigue_necesitando_token(self):
        with self.assertRaises(ErrorConfig):
            cargar_config(self.BASE)

    def test_credenciales(self):
        buenas = {"CAPTACION_API_ID": "123456", "CAPTACION_API_HASH": "0123456789abcdef0123456789abcdef",
                  "CAPTACION_SESION": "/var/lib/premier-captacion/prueba-cuenta"}
        self.assertEqual(lector.credenciales_api(buenas)[0], 123456)
        for malo in ({"CAPTACION_API_ID": "abc"}, {"CAPTACION_API_HASH": "corto"}, {"CAPTACION_SESION": ""}):
            with self.subTest(malo), self.assertRaises(ErrorConfig):
                lector.credenciales_api({**buenas, **malo})


class OrganizadorFalso:
    def __init__(self, bienvenidas_manuales=False):
        self.llamadas = []
        self.con = db.abrir(":memory:")
        self.aj = carpetas.Ajustes(bienvenidas_manuales=bienvenidas_manuales)

    async def al_recibir(self, user_id, msg_id, ts, texto, usuario=None):
        self.llamadas.append(("recibe", user_id, msg_id, texto, usuario["first_name"]))

    async def al_enviar(self, user_id, msg_id, ts, textos):
        self.llamadas.append(("envia", user_id, msg_id, textos))


class TgFalso:
    def __init__(self):
        self.recordados = []

    def recordar(self, peer):
        self.recordados.append(peer)


class TestProcesar(unittest.TestCase):
    def procesar(self, mensaje, otro, org=None):
        org, tg = org or OrganizadorFalso(), TgFalso()
        asyncio.run(lector.procesar(mensaje, otro, "entrada", org, tg))
        return org.llamadas, tg.recordados

    def test_bienvenida_manual_en_directo_solo_si_esta_activado(self):
        ana = SimpleNamespace(id=500, first_name="Ana", last_name=None, username="ana", bot=False, is_self=False)
        bienvenida = self.msg(True, mensajes.TEXTO_MANUAL_BUENAS)
        sin = OrganizadorFalso()
        self.procesar(bienvenida, ana, sin)
        self.assertIsNone(db.obtener_usuario(sin.con, 500))  # instancia de prueba: se ignora
        con = OrganizadorFalso(bienvenidas_manuales=True)
        llamadas, _ = self.procesar(bienvenida, ana, con)
        fila = db.obtener_usuario(con.con, 500)
        self.assertEqual((fila["bienvenida_tipo"], fila["username"]), (mensajes.TIPO_MANUAL_BUENAS, "ana"))
        self.assertEqual(fila["bienvenida_ts"], int(bienvenida.date.timestamp()))
        evento = con.con.execute("SELECT tipo, detalle FROM eventos").fetchone()
        self.assertEqual((evento["tipo"], evento["detalle"]), ("bienvenida_manual", '{"tipo_mensaje": "manual_buenas"}'))
        self.assertEqual(llamadas[0][0], "envia")  # y sigue su camino (enlaces, etc.)
        self.procesar(self.msg(True, "hola de nuevo"), ana, con)  # otro mensaje no cambia nada
        self.assertEqual(db.obtener_usuario(con.con, 500)["bienvenida_tipo"], mensajes.TIPO_MANUAL_BUENAS)

    def msg(self, out, texto, url=None):
        return SimpleNamespace(id=7, out=out, message=texto, date=datetime(2026, 10, 15, tzinfo=timezone.utc),
                               entities=[SimpleNamespace(url=url)] if url else [])

    def test_entrante_y_saliente(self):
        ana = SimpleNamespace(id=500, first_name="Ana", last_name=None, username="ana", bot=False, is_self=False)
        llamadas, recordados = self.procesar(self.msg(False, "hola"), ana)
        self.assertEqual(llamadas, [("recibe", 500, 7, "hola", "Ana")])
        self.assertEqual(recordados, ["entrada"])
        llamadas, _ = self.procesar(self.msg(True, "pulsa aquí", url="https://t.me/+VENTA0000000001"), ana)
        self.assertEqual(llamadas, [("envia", 500, 7, ["pulsa aquí", "https://t.me/+VENTA0000000001"])])

    def test_bots_y_mensajes_guardados_se_ignoran(self):
        for otro in (SimpleNamespace(id=1, bot=True, is_self=False), SimpleNamespace(id=2, bot=False, is_self=True), None):
            self.assertEqual(self.procesar(self.msg(False, "x"), otro), ([], []))


class TestEmbudoPrueba(unittest.TestCase):
    def test_marca_como_del_embudo(self):
        import os
        import tempfile

        with tempfile.TemporaryDirectory() as carpeta:
            cfg = cargar_config({"CAPTACION_DB": os.path.join(carpeta, "p.db")}, requiere_bot=False)
            lector.marcar_embudo_prueba(cfg, 123456789)
            con = db.abrir(cfg.db_path)
            self.addCleanup(con.close)
            self.assertTrue(db.es_del_embudo(db.obtener_usuario(con, 123456789)))


class TestLineaDeOrdenes(unittest.TestCase):
    def test_argumentos(self):
        import os
        import tempfile

        with tempfile.TemporaryDirectory() as carpeta, \
                mock.patch.dict(os.environ, {"CAPTACION_DB": os.path.join(carpeta, "p.db")}), \
                mock.patch("builtins.print"):
            self.assertEqual(lector.main(["embudo-prueba", "123456789"]), 0)
            for malo in (["embudo-prueba"], ["embudo-prueba", "abc"], ["canal-de-enlace"]):
                with self.subTest(malo), self.assertRaises(SystemExit), mock.patch("sys.stderr"):
                    lector.main(malo)


class TestAvisador(unittest.TestCase):
    def test_los_avisos_llegan_en_orden(self):
        enviados = []
        hecho = threading.Event()

        class BotFalso:
            def __init__(self, token):
                pass

            def llamar(self, metodo, **params):
                time.sleep(0.05 if params["text"] == "primero" else 0)
                enviados.append(params["text"])
                if len(enviados) == 2:
                    hecho.set()

        with mock.patch.object(lector, "BotAPI", BotFalso):
            avisar = lector.crear_avisador(SimpleNamespace(bot_token="1:x", propietario_id=1))

        async def probar():  # como en el lector: desde dentro del bucle de asyncio
            avisar("primero")
            avisar("segundo")
            await asyncio.get_running_loop().run_in_executor(None, hecho.wait, 5)

        asyncio.run(probar())
        self.assertEqual(enviados, ["primero", "segundo"])


class TestTelefono(unittest.TestCase):
    def test_formato_internacional(self):
        for escrito, esperado in (("+353 87 000 0000", "+353870000000"),
                                  ("00353870000000", "+353870000000"),
                                  ("+34 600-00-00-00", "+34600000000")):
            with self.subTest(escrito), mock.patch("builtins.print"):
                self.assertEqual(lector.pedir_telefono(leer=lambda _: escrito), esperado)

    def test_sin_prefijo_lo_vuelve_a_pedir(self):
        respuestas = iter(["087 000 0000", "+353 87 000 0000"])
        with mock.patch("builtins.print") as impreso:
            self.assertEqual(lector.pedir_telefono(leer=lambda _: next(respuestas)), "+353870000000")
        self.assertIn("prefijo", impreso.call_args.args[0])


if __name__ == "__main__":
    unittest.main()


class TestApuntarGratuita(unittest.TestCase):
    def test_busca_por_arroba_y_apunta(self):
        import os
        import tempfile
        ruta = os.path.join(tempfile.mkdtemp(), "x.db")
        cfg = cargar_config({"CAPTACION_DB": ruta}, requiere_bot=False)
        iker = SimpleNamespace(id=77, first_name="Iker", last_name=None, username="iker_falso")

        class Cliente:
            async def connect(self): pass
            async def disconnect(self): pass
            async def is_user_authorized(self): return True
            async def get_entity(self, quien):
                assert quien == "iker_falso"
                return iker

        entorno = {"CAPTACION_API_ID": "123456", "CAPTACION_API_HASH": "0123456789abcdef0123456789abcdef",
                   "CAPTACION_SESION": "/tmp/sesion"}
        with mock.patch.object(lector, "crear_cliente", return_value=Cliente()) as crear, \
                mock.patch("builtins.print") as imprimir:
            r = asyncio.run(lector.apuntar_gratuita(cfg, entorno, "@iker_falso", "2026-10-20 16:56",
                                                    "2026-10-20 18:45", "https://t.me/+VENTAFALSA01"))
        self.assertEqual(r, 0)
        self.assertEqual(crear.call_args[0][3], "historico")  # solo lectura
        self.assertIn("🎁 Gratuita: 20/10/2026 a las 18:45", imprimir.call_args[0][0])
        con = db.abrir(ruta)
        self.addCleanup(con.close)
        self.assertEqual(db.obtener_usuario(con, 77)["enlace_venta"], "https://t.me/+VENTAFALSA01")


HAY_TELETHON = importlib.util.find_spec("telethon") is not None


@unittest.skipUnless(HAY_TELETHON, "necesita Telethon (venv de la VM)")
class TestLeerSuscriptores(unittest.TestCase):
    def test_lista_directa_y_busquedas_hasta_tenerlos_todos(self):
        import os
        import tempfile
        ruta = os.path.join(tempfile.mkdtemp(), "x.db")
        cfg = cargar_config({"CAPTACION_DB": ruta, "CAPTACION_CANAL_ID": "-1001234567890"}, requiere_bot=False)
        busquedas = []

        class Cliente:
            flood_sleep_threshold = 0
            async def connect(self): pass
            async def disconnect(self): pass
            async def is_user_authorized(self): return True
            async def get_entity(self, peer): return "canal"
            async def __call__(self, peticion):
                return SimpleNamespace(full_chat=SimpleNamespace(participants_count=5))

            def iter_participants(self, canal, search=None):
                busquedas.append(search)
                ids = {None: [1, 2, 3], "a": [3, 4], "b": [5]}.get(search, [])

                async def gen():
                    for i in ids:
                        yield SimpleNamespace(id=i)
                return gen()

        entorno = {"CAPTACION_API_ID": "123456", "CAPTACION_API_HASH": "0123456789abcdef0123456789abcdef",
                   "CAPTACION_SESION": "/tmp/sesion"}
        with mock.patch.object(lector, "crear_cliente", return_value=Cliente()) as crear, \
                mock.patch("builtins.print") as imprimir:
            self.assertEqual(asyncio.run(lector.leer_suscriptores(cfg, entorno)), 0)
        self.assertEqual(crear.call_args[0][3], "suscriptores")
        self.assertEqual(busquedas, [None, "a", "b"])  # para al tenerlos todos
        self.assertIn("Leídos 5 de 5 suscriptores (100%)", imprimir.call_args[0][0])
        con = db.abrir(ruta)
        self.addCleanup(con.close)
        self.assertTrue(all(db.es_miembro(con, i) for i in range(1, 6)))
        self.assertFalse(db.es_miembro(con, 6))


class TestModoInvitaciones(unittest.TestCase):
    def test_lanza_la_lectura_de_invitaciones_con_el_trozo_de_enlace(self):
        from premier_captacion import invitaciones
        llamadas = []

        async def falso(cfg, entorno, crear_cliente, credenciales_api, solo=None):
            llamadas.append((crear_cliente, solo))
            return 0

        entorno = {"CAPTACION_DB": ":memory:", "CAPTACION_CANAL_ID": "-1001234567890"}
        with mock.patch.dict("os.environ", entorno), mock.patch.object(invitaciones, "ejecutar", falso):
            self.assertEqual(lector.main(["invitaciones", "AbCd"]), 0)
            self.assertEqual(lector.main(["invitaciones"]), 0)
        self.assertEqual(llamadas, [(lector.crear_cliente, "AbCd"), (lector.crear_cliente, None)])


class TestModoPedido(unittest.TestCase):
    """El lector sigue a /arrancar (real) y /pausar (simulación) del bot."""

    def setUp(self):
        self.con = db.abrir(":memory:")
        self.addCleanup(self.con.close)

    def modo(self, ruta="/var/lib/premier-captacion/real.db"):
        return lector.modo_pedido(self.con, SimpleNamespace(db_path=ruta))

    def test_sin_orden_manda_la_configuracion(self):
        self.assertIsNone(self.modo())

    def test_arrancar_y_pausar(self):
        with self.con:
            db.guardar_estado(self.con, "lector_modo", "real")
        self.assertIs(self.modo(), False)
        with self.con:
            db.guardar_estado(self.con, "lector_modo", "simulacion")
        self.assertIs(self.modo(), True)

    def test_en_prueba_nunca_pasa_a_real(self):
        with self.con:
            db.guardar_estado(self.con, "lector_modo", "real")
        self.assertIsNone(self.modo("/var/lib/premier-captacion/prueba.db"))
