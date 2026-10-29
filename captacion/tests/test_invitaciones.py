"""Quién se unió con cada enlace de invitación de las ventas (invitaciones.py).
Datos INVENTADOS. Las pruebas de la lectura usan los tipos reales de Telethon
con un cliente falso que no se conecta a nada (se saltan si no está instalado)."""
import asyncio
import contextlib
import io
import os
import tempfile
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

try:
    from telethon import errors
    from telethon.tl import functions, types
except ImportError:  # pragma: no cover
    types = None

from premier_captacion import db, invitaciones, pagos


def venta(con, id, enlace, pago_ts):
    pagos.guardar_ventas(con, [{
        "id": id, "content_uid": None, "portal_uid": None, "producto": "Canal X",
        "enlace": enlace, "correo": "a@example.com", "importe": 30, "moneda": "EUR",
        "neto": 27, "comision": 3, "metodo": "card", "estado": "SUCCESS",
        "es_propina": 0, "descuento_codigo": None, "descuento_importe": 0,
        "pago_ts": pago_ts,
    }], ahora=1)


class TestGuardar(unittest.TestCase):
    def setUp(self):
        self.con = db.abrir(":memory:")
        self.addCleanup(self.con.close)

    def test_guarda_canal_invitados_y_personas(self):
        with self.con:
            invitaciones.guardar(self.con, "https://t.me/+L", 10, "Canal X",
                                 [(500, "Ana", "ana", 1000), (501, "Luis", None, 2000)], ahora=5)
        e = self.con.execute("SELECT * FROM pagos_enlaces").fetchone()
        self.assertEqual((e["enlace"], e["canal_id"], e["titulo"], e["leido_ts"]),
                         ("https://t.me/+L", 10, "Canal X", 5))
        filas = self.con.execute("SELECT user_id, ts FROM pagos_invitados ORDER BY user_id").fetchall()
        self.assertEqual([tuple(f) for f in filas], [(500, 1000), (501, 2000)])
        p = self.con.execute("SELECT nombre, username FROM ventas_personas WHERE user_id = 500").fetchone()
        self.assertEqual(tuple(p), ("Ana", "ana"))

    def test_se_queda_la_primera_vez_que_se_unio(self):
        with self.con:
            invitaciones.guardar(self.con, "https://t.me/+L", 10, "Canal X", [(500, "Ana", None, 3000)], ahora=5)
            invitaciones.guardar(self.con, "https://t.me/+L", 10, "Canal X", [(500, "Ana", None, 1000)], ahora=6)
            invitaciones.guardar(self.con, "https://t.me/+L", 10, "Canal X", [(500, "Ana", None, 9000)], ahora=7)
        self.assertEqual(self.con.execute("SELECT ts FROM pagos_invitados").fetchone()[0], 1000)

    def test_enlace_que_no_lleva_a_un_canal_se_apunta_sin_canal(self):
        with self.con:
            invitaciones.guardar(self.con, "https://t.me/+CADUCADO", None, None, [], ahora=5)
        e = self.con.execute("SELECT canal_id, leido_ts FROM pagos_enlaces").fetchone()
        self.assertEqual(tuple(e), (None, 5))

    def test_enlaces_de_ventas_sin_repetir_y_los_recientes_primero(self):
        venta(self.con, "v1", "https://t.me/+A", 1000)
        venta(self.con, "v2", "https://t.me/+B", 3000)
        venta(self.con, "v3", "https://t.me/+A", 2000)
        venta(self.con, "v4", None, 4000)
        self.assertEqual(invitaciones.enlaces_de_ventas(self.con),
                         ["https://t.me/+B", "https://t.me/+A"])


class TestPendientes(unittest.TestCase):
    """Solo se vuelve a leer un enlace si nunca se leyó o si hay ventas
    después de leerlo (quien pagó después aún no salía en la lista)."""

    def setUp(self):
        self.con = db.abrir(":memory:")
        self.addCleanup(self.con.close)
        venta(self.con, "v1", "https://t.me/+A", 1000)

    def leido(self, ahora):
        with self.con:
            invitaciones.guardar(self.con, "https://t.me/+A", 10, "Canal X", [], ahora=ahora)

    def test_nunca_leido_esta_pendiente(self):
        self.assertEqual(invitaciones.enlaces_pendientes(self.con), ["https://t.me/+A"])

    def test_leido_despues_de_la_ultima_venta_no_se_repite(self):
        self.leido(1000 + pagos.VENTANA_S + 1)
        self.assertEqual(invitaciones.enlaces_pendientes(self.con), [])

    def test_leido_nada_mas_pagar_se_repite(self):
        self.leido(1000 + 60)  # el comprador aún podía no haber entrado
        self.assertEqual(invitaciones.enlaces_pendientes(self.con), ["https://t.me/+A"])

    def test_venta_nueva_despues_de_leerlo_se_repite(self):
        self.leido(5000)
        venta(self.con, "v2", "https://t.me/+A", 6000)
        self.assertEqual(invitaciones.enlaces_pendientes(self.con), ["https://t.me/+A"])

    def test_los_recientes_primero(self):
        venta(self.con, "v2", "https://t.me/+B", 3000)
        self.assertEqual(invitaciones.enlaces_pendientes(self.con),
                         ["https://t.me/+B", "https://t.me/+A"])


def fecha(ts):
    return datetime.fromtimestamp(ts, timezone.utc)


def usuario(uid, nombre, username=None):
    return types.User(id=uid, first_name=nombre, username=username, access_hash=uid * 7)


def canal_tg(cid, titulo):
    return types.Channel(id=cid, title=titulo, photo=types.ChatPhotoEmpty(), date=fecha(0),
                         broadcast=True, access_hash=cid * 3)


class ClienteFalso:
    """Hace de cliente de Telethon: responde a la comprobación del enlace y
    da los que se unieron por páginas. Apunta las peticiones."""

    def __init__(self, invitacion, invitados, por_pagina=2):
        self.invitacion = invitacion
        self.invitados = invitados  # [(User, ts)] del más reciente al más antiguo, como Telegram
        self.por_pagina = por_pagina
        self.peticiones = []

    async def __call__(self, peticion):
        self.peticiones.append(peticion)
        if isinstance(peticion, functions.messages.CheckChatInviteRequest):
            if isinstance(self.invitacion, Exception):
                raise self.invitacion
            return self.invitacion
        if isinstance(peticion, functions.messages.GetChatInviteImportersRequest):
            if isinstance(self.invitados, Exception):
                raise self.invitados
            resto = self.invitados
            if peticion.offset_date is not None:
                corte = [i for i, (u, _) in enumerate(resto) if u.id == peticion.offset_user.id][0]
                resto = resto[corte + 1:]
            pagina = resto[:min(self.por_pagina, peticion.limit)]
            return types.messages.ChatInviteImporters(
                count=len(self.invitados),
                importers=[types.ChatInviteImporter(user_id=u.id, date=fecha(ts)) for u, ts in pagina],
                users=[u for u, _ in pagina])
        raise AssertionError(f"petición inesperada: {peticion}")


@unittest.skipIf(types is None, "telethon no está instalado")
class TestLeerEnlace(unittest.TestCase):
    def setUp(self):
        self.antes = invitaciones.POR_PAGINA
        invitaciones.POR_PAGINA = 2
        self.addCleanup(setattr, invitaciones, "POR_PAGINA", self.antes)

    def leer(self, cliente, enlace="https://t.me/+AbCdEf123456"):
        return asyncio.run(invitaciones.leer_enlace(cliente, enlace))

    def test_lee_todos_los_que_se_unieron_por_paginas(self):
        canal = canal_tg(10, "Canal X")
        cliente = ClienteFalso(types.ChatInviteAlready(chat=canal), [
            (usuario(503, "Eva"), 4000), (usuario(502, "Juan", "juan"), 3000),
            (usuario(501, "Luis"), 2000), (usuario(500, "Ana", "ana"), 1000)])
        leido, invitados = self.leer(cliente)
        self.assertIs(leido, canal)
        self.assertEqual(sorted(invitados), [(500, "Ana", "ana", 1000), (501, "Luis", None, 2000),
                                             (502, "Juan", "juan", 3000), (503, "Eva", None, 4000)])
        pedidas = [p for p in cliente.peticiones
                   if isinstance(p, functions.messages.GetChatInviteImportersRequest)]
        self.assertEqual(len(pedidas), 3)  # 2 + 2 + 0
        self.assertEqual(pedidas[0].link, "https://t.me/+AbCdEf123456")
        self.assertFalse(pedidas[0].requested)  # los que entraron, no las solicitudes pendientes
        self.assertEqual(cliente.peticiones[0].hash, "AbCdEf123456")

    def test_enlace_caducado_no_lleva_a_ningun_canal(self):
        cliente = ClienteFalso(errors.InviteHashExpiredError(request=None), [])
        self.assertEqual(self.leer(cliente), (None, None))

    def test_enlace_de_un_canal_en_el_que_no_estas(self):
        cliente = ClienteFalso(types.ChatInvite(title="Otro", photo=types.PhotoEmpty(id=1),
                                                participants_count=5, color=0), [])
        self.assertEqual(self.leer(cliente), (None, None))

    def test_sin_ser_administrador_se_sabe_el_canal_pero_no_quien_entro(self):
        canal = canal_tg(10, "Canal X")
        cliente = ClienteFalso(types.ChatInviteAlready(chat=canal),
                               errors.ChatAdminRequiredError(request=None))
        self.assertEqual(self.leer(cliente), (canal, None))

    def test_texto_que_no_es_un_enlace(self):
        cliente = ClienteFalso(None, [])
        self.assertEqual(self.leer(cliente, "hola"), (None, None))
        self.assertEqual(cliente.peticiones, [])


class ClienteVariosEnlaces:
    """Cliente falso para ejecutar(): cada hash lleva a un canal (o lanza un
    error), y nadie se unió. Apunta qué hashes se comprobaron."""

    def __init__(self, por_hash):
        self.por_hash = por_hash
        self.comprobados = []

    async def connect(self):
        pass

    async def disconnect(self):
        pass

    async def is_user_authorized(self):
        return True

    async def __call__(self, peticion):
        if isinstance(peticion, functions.messages.CheckChatInviteRequest):
            self.comprobados.append(peticion.hash)
            r = self.por_hash[peticion.hash]
            if isinstance(r, Exception):
                raise r
            return r
        if isinstance(peticion, functions.messages.GetChatInviteImportersRequest):
            return types.messages.ChatInviteImporters(count=0, importers=[], users=[])
        raise AssertionError(f"petición inesperada: {peticion}")


@unittest.skipIf(types is None, "telethon no está instalado")
class TestEjecutar(unittest.TestCase):
    A, B = "https://t.me/+AaAaAa111111", "https://t.me/+BbBbBb222222"

    def setUp(self):
        carpeta = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(carpeta.cleanup)
        self.cfg = SimpleNamespace(db_path=os.path.join(carpeta.name, "prueba.db"))
        con = db.abrir(self.cfg.db_path)
        with con:
            venta(con, "v1", self.A, 1000)
            venta(con, "v2", self.B, 2000)
        con.close()
        antes = invitaciones.PAUSA_S
        invitaciones.PAUSA_S = 0
        self.addCleanup(setattr, invitaciones, "PAUSA_S", antes)
        self.cliente = ClienteVariosEnlaces({
            "AaAaAa111111": types.ChatInviteAlready(chat=canal_tg(10, "Canal A")),
            "BbBbBb222222": types.ChatInviteAlready(chat=canal_tg(11, "Canal B"))})

    def ejecutar(self, solo=None):
        with contextlib.redirect_stdout(io.StringIO()):
            return asyncio.run(invitaciones.ejecutar(
                self.cfg, {}, lambda *a: self.cliente, lambda entorno: (1, "h", "sesion"), solo=solo))

    def leidos(self):
        con = db.abrir(self.cfg.db_path)
        try:
            return {f[0] for f in con.execute("SELECT enlace FROM pagos_enlaces")}
        finally:
            con.close()

    def marcar_leido(self, enlace):
        con = db.abrir(self.cfg.db_path)
        with con:
            invitaciones.guardar(con, enlace, 10, "Canal A", [], ahora=10 ** 6)
        con.close()

    def test_se_salta_los_enlaces_ya_leidos(self):
        self.marcar_leido(self.A)
        self.assertEqual(self.ejecutar(), 0)
        self.assertEqual(self.cliente.comprobados, ["BbBbBb222222"])

    def test_con_trozo_de_enlace_lo_lee_aunque_ya_este_leido(self):
        self.marcar_leido(self.A)
        self.assertEqual(self.ejecutar(solo="AaAa"), 0)
        self.assertEqual(self.cliente.comprobados, ["AaAaAa111111"])

    def test_si_todo_esta_leido_no_conecta(self):
        self.marcar_leido(self.A)
        self.marcar_leido(self.B)
        self.assertEqual(self.ejecutar(), 0)
        self.assertEqual(self.cliente.comprobados, [])

    def test_si_telegram_pide_esperar_mucho_para_y_guarda_lo_leido(self):
        self.cliente.por_hash["AaAaAa111111"] = errors.FloodWaitError(request=None, capture=2978)
        self.assertEqual(self.ejecutar(), invitaciones.PARADO_POR_TELEGRAM)
        self.assertEqual(self.leidos(), {self.B})  # B (la venta más reciente) se leyó antes


if __name__ == "__main__":
    unittest.main()
