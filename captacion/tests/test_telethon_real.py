"""
Pruebas del adaptador de Telethon (lector.TelegramReal) y del candado
enganchado al cliente, con los tipos REALES de Telethon y un cliente falso
que no se conecta a nada.

Necesitan Telethon instalado; si no lo está, se saltan. Para ejecutarlas:
    /opt/premier-captacion/venv/bin/python -m unittest tests.test_telethon_real
(o cualquier entorno con telethon==1.45.0).
"""
import asyncio
import os
import tempfile
import unittest
from types import SimpleNamespace

try:
    from telethon import errors
    from telethon.tl import functions, types
except ImportError:  # pragma: no cover
    types = None

from premier_captacion import guardia


def peer(uid):
    return types.InputPeerUser(user_id=uid, access_hash=uid * 10)


def titulo(texto):
    return types.TextWithEntities(text=texto, entities=[])


class ClienteFalso:
    """Hace de cliente de Telethon: devuelve las carpetas dadas y apunta las peticiones."""

    def __init__(self, filtros):
        self.filtros = filtros
        self.peticiones = []
        self.respuesta_invitacion = None

    async def __call__(self, peticion):
        self.peticiones.append(peticion)
        if isinstance(peticion, functions.messages.GetDialogFiltersRequest):
            return types.messages.DialogFilters(filters=list(self.filtros))
        if isinstance(peticion, functions.messages.UpdateDialogFilterRequest):
            # Como Telegram: crea, sustituye o (sin filtro) borra la carpeta.
            resto = [f for f in self.filtros if getattr(f, "id", None) != peticion.id]
            self.filtros = resto + ([peticion.filter] if peticion.filter is not None else [])
            return True
        if isinstance(peticion, functions.messages.CheckChatInviteRequest):
            if isinstance(self.respuesta_invitacion, Exception):
                raise self.respuesta_invitacion
            return self.respuesta_invitacion
        return True

    async def get_input_entity(self, uid):
        return peer(uid)


@unittest.skipIf(types is None, "telethon no está instalado")
class TestTelegramReal(unittest.TestCase):
    def setUp(self):
        from premier_captacion import lector

        self.lector = lector
        self.filtros = [
            types.DialogFilterDefault(),
            types.DialogFilter(id=2, title=titulo("Trabajo"), pinned_peers=[peer(900)],
                               include_peers=[peer(901), types.InputPeerChannel(channel_id=5, access_hash=1)],
                               exclude_peers=[peer(950)], contacts=True, emoticon="💼", color=3),
            types.DialogFilter(id=3, title=titulo("14.10"), pinned_peers=[], include_peers=[peer(500)],
                               exclude_peers=[]),
            types.DialogFilterChatlist(id=4, title=titulo("Compartida"), pinned_peers=[], include_peers=[peer(600)]),
        ]
        self.cliente = ClienteFalso(self.filtros)
        self.peticiones = self.cliente.peticiones
        self.tg = lector.TelegramReal(self.cliente)

    def correr(self, corrutina):
        return asyncio.run(corrutina)

    def test_lee_las_carpetas(self):
        lista = self.correr(self.tg.carpetas())
        self.assertEqual([c.titulo for c in lista], ["Trabajo", "14.10", "Compartida"])
        trabajo, dia, compartida = lista
        self.assertEqual((trabajo.usuarios, trabajo.total, trabajo.con_reglas), ({900, 901}, 3, True))
        self.assertEqual((dia.usuarios, dia.total, dia.gestionable), ({500}, 1, True))
        self.assertFalse(compartida.gestionable)

    def test_crear_carpeta(self):
        self.correr(self.tg.carpetas())
        nuevo = self.correr(self.tg.crear_carpeta("15.10", {501, 500}))
        self.assertEqual(nuevo, 5)  # 2, 3 y 4 están ocupados
        p = self.peticiones[-1]
        self.assertIsInstance(p, functions.messages.UpdateDialogFilterRequest)
        self.assertEqual(p.filter.title.text, "15.10")
        self.assertEqual([x.user_id for x in p.filter.include_peers], [500, 501])

    def test_cambiar_conserva_todo_lo_demas(self):
        self.correr(self.tg.carpetas())
        sigue = self.correr(self.tg.cambiar(2, anadir={777}, quitar={900}))
        self.assertTrue(sigue)
        f = self.peticiones[-1].filter
        self.assertEqual(f.pinned_peers, [])
        self.assertEqual([getattr(x, "user_id", "canal") for x in f.include_peers], [901, "canal", 777])
        self.assertEqual((f.emoticon, f.color, f.contacts, f.title.text), ("💼", 3, True, "Trabajo"))
        self.assertEqual([x.user_id for x in f.exclude_peers], [950])
        # El original no se toca (se trabaja sobre una copia).
        self.assertEqual([x.user_id for x in self.filtros[1].pinned_peers], [900])

    def test_si_se_queda_vacia_se_borra(self):
        self.correr(self.tg.carpetas())
        sigue = self.correr(self.tg.cambiar(3, quitar={500}))
        self.assertFalse(sigue)
        p = self.peticiones[-1]
        self.assertIsInstance(p, functions.messages.UpdateDialogFilterRequest)
        self.assertEqual((p.id, p.filter), (3, None))

    def test_una_compartida_no_se_cambia(self):
        self.correr(self.tg.carpetas())
        with self.assertRaises(self.lector.ErrorLector):
            self.correr(self.tg.cambiar(4, quitar={600}))

    def test_destino_de_un_enlace(self):
        self.cliente.respuesta_invitacion = types.ChatInviteAlready(chat=SimpleNamespace(id=1234567890, title="PREMIER GALGOS"))
        self.assertEqual(self.correr(self.tg.destino_enlace("X")), (1234567890, "PREMIER GALGOS"))
        invitacion = object.__new__(types.ChatInvite)
        invitacion.title = "Canal VIP"
        self.cliente.respuesta_invitacion = invitacion
        self.assertEqual(self.correr(self.tg.destino_enlace("X")), (None, "Canal VIP"))
        self.cliente.respuesta_invitacion = errors.InviteHashExpiredError(request=None)
        self.assertEqual(self.correr(self.tg.destino_enlace("X")), (None, None))


@unittest.skipIf(types is None, "telethon no está instalado")
class TestClienteVigilado(unittest.TestCase):
    def test_el_candado_salta_antes_de_salir_nada(self):
        from premier_captacion import lector

        async def probar(carpeta):
            # Como en el programa: el cliente se crea dentro del bucle de asyncio.
            cliente = lector.crear_cliente(os.path.join(carpeta, "s"), 1, "0" * 32, "lector")
            try:
                prohibida = functions.messages.SendMessageRequest(peer=types.InputPeerSelf(), message="hola")
                with self.assertRaises(guardia.PeticionProhibida):
                    await cliente._call(None, prohibida)
                leer = functions.messages.ReadHistoryRequest(peer=types.InputPeerSelf(), max_id=0)
                with self.assertRaises(guardia.PeticionProhibida):
                    await cliente(leer)
            finally:
                cliente.session.close()

        with tempfile.TemporaryDirectory() as carpeta:
            asyncio.run(probar(carpeta))


if __name__ == "__main__":
    unittest.main()


class ClienteServicio(ClienteFalso):
    """Cliente falso para lector.servicio(): entrega `eventos` como si
    llegaran en directo y luego "se desconecta"."""

    def __init__(self, filtros, eventos):
        super().__init__(filtros)
        self.eventos = eventos
        self.manejadores = []

    async def connect(self):
        pass

    async def disconnect(self):
        pass

    async def is_user_authorized(self):
        return True

    async def get_me(self):
        return SimpleNamespace(id=1, first_name="Secundaria", last_name=None)

    def on(self, _filtro):
        def registrar(funcion):
            self.manejadores.append(funcion)
            return funcion
        return registrar

    def iter_dialogs(self, limit=None):
        async def vacio():
            for _ in ():
                yield
        return vacio()

    async def run_until_disconnected(self):
        for evento in self.eventos:
            for manejador in self.manejadores:
                await manejador(evento)


def evento(uid, nombre, msg_id, texto, out=False, url=None):
    from datetime import datetime, timezone

    otro = SimpleNamespace(id=uid, first_name=nombre, last_name=None, username=nombre.lower(), bot=False, is_self=False)
    mensaje = SimpleNamespace(id=msg_id, out=out, message=texto, date=datetime.now(timezone.utc),
                              entities=[SimpleNamespace(url=url)] if url else [])

    async def get_chat():
        return otro

    async def get_input_chat():
        return peer(uid)

    return SimpleNamespace(message=mensaje, is_private=True, get_chat=get_chat, get_input_chat=get_input_chat)


@unittest.skipIf(types is None, "telethon no está instalado")
class TestServicio(unittest.TestCase):
    def ejecutar(self, simular):
        from unittest import mock

        from premier_captacion import db, lector
        from premier_captacion.config import cargar_config

        with tempfile.TemporaryDirectory() as carpeta:
            entorno = {"CAPTACION_DB": os.path.join(carpeta, "p.db"), "CAPTACION_CANAL_ID": "-1001234567890",
                       "CAPTACION_API_ID": "1", "CAPTACION_API_HASH": "0" * 32,
                       "CAPTACION_SESION": os.path.join(carpeta, "s"),
                       "CAPTACION_LECTOR_SIMULAR": "1" if simular else "0"}
            cfg = cargar_config(entorno, requiere_bot=False)
            con = db.abrir(cfg.db_path)
            with con:
                db.actualizar_datos_usuario(con, 1, {"id": 500, "first_name": "Ana"})
                db.marcar_bienvenida(con, 500, 1, "bot_b_v1")
            con.close()
            filtros = [types.DialogFilter(id=2, title=titulo("Trabajo"), pinned_peers=[],
                                          include_peers=[peer(900)], exclude_peers=[])]
            cliente = ClienteServicio(filtros, [
                evento(500, "Ana", 10, "¡Hola! Acabo de entrar en el canal. Es mi primera vez con los galgos 🐕"),
                evento(999, "Otro", 11, "hola"),  # no es del embudo
                evento(500, "Ana", 12, "aquí tienes", out=True, url="https://t.me/+VENTA0000000001"),
            ])
            cliente.respuesta_invitacion = types.ChatInviteAlready(chat=SimpleNamespace(id=555, title="Canal VIP"))
            with mock.patch.object(lector, "crear_cliente", return_value=cliente) as crear:
                codigo = asyncio.run(lector.servicio(cfg, entorno))
            self.modo_candado = crear.call_args.args[3]
            con = db.abrir(cfg.db_path)
            fila = db.obtener_usuario(con, 500)
            otro = db.obtener_usuario(con, 999)
            con.close()
        return codigo, cliente.peticiones, fila, otro

    def nombres(self, peticiones):
        return [guardia.nombre_peticion(p) for p in peticiones]

    def test_simulacion_no_toca_carpetas(self):
        codigo, peticiones, fila, otro = self.ejecutar(simular=True)
        self.assertEqual(codigo, 1)  # se "desconectó" sin que nadie lo parase
        self.assertEqual(self.modo_candado, "simulacion")
        self.assertNotIn("messages.UpdateDialogFilterRequest", self.nombres(peticiones))
        for p in peticiones:  # todo lo pedido pasa el candado más estricto
            guardia.comprobar(p, "simulacion")
        self.assertIn("account.UpdateStatusRequest", self.nombres(peticiones))
        self.assertEqual((fila["boton"], fila["canal_venta"]), ("primera_vez", "Canal VIP"))
        self.assertIsNone(fila["carpeta"])
        self.assertIsNone(otro)

    def test_real_crea_y_mueve_carpetas(self):
        codigo, peticiones, fila, _ = self.ejecutar(simular=False)
        self.assertEqual(self.modo_candado, "lector")
        cambios = [p for p in peticiones if isinstance(p, functions.messages.UpdateDialogFilterRequest)]
        titulos = [p.filter.title.text if p.filter else f"borrar {p.id}" for p in cambios]
        self.assertEqual(titulos[0][2], ".")  # «DD.MM» de hoy
        self.assertIn("free send", titulos)
        self.assertIn(f"borrar {cambios[0].id}", titulos)  # la del día se queda vacía al pasar a free send
        self.assertEqual(fila["carpeta"], "free send")
        for p in peticiones:  # todo lo pedido está en la lista blanca del lector
            guardia.comprobar(p, "lector")
