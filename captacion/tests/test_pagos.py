"""Tests de pagos.py (ventas de overoption, solo lectura). Valores inventados:
nada de datos reales en el repo (es público)."""
import unittest

from premier_captacion import db, pagos


def _venta(**cambios):
    """Una transacción como la que devuelve overoption /transactions, con
    datos INVENTADOS."""
    base = {
        "_id": "aaaa0000bbbb1111cccc2222",
        "content_uid": "11111111-1111-1111-1111-111111111111",
        "portal_uid": "22222222-2222-2222-2222-222222222222",
        "is_tip": False,
        "amount": 30,
        "currency": "EUR",
        "gateway_amount": 31.2,
        "net_amount": 27,
        "net_amount_eur": 27,
        "payment_method_type": "card",
        "payment_status": "SUCCESS",
        "payment_date": "2026-10-28T17:46:12.202Z",
        "customer_email": "cliente@example.com",
        "metadata": {
            "product_title": "Mi&#233;rcoles Tarde Galgos 3.50",
            "commission_amount": 3,
            "discount_code": "",
            "discountAmount": 0,
        },
    }
    base.update(cambios)
    return base


class TestParseo(unittest.TestCase):
    def test_fecha_iso_utc_a_epoch(self):
        # 2026-10-28T17:46:12Z = 1792000... epoch en UTC
        ts = pagos._parsear_fecha("2026-10-28T17:46:12.202Z")
        self.assertEqual(ts, 1793209572)

    def test_fecha_vacia_es_none(self):
        self.assertIsNone(pagos._parsear_fecha(None))
        self.assertIsNone(pagos._parsear_fecha(""))

    def test_decodifica_entidades_html(self):
        self.assertEqual(pagos._decodificar("Mi&#233;rcoles"), "Miércoles")
        self.assertEqual(pagos._decodificar("Ma&#241;ana &amp; tarde"), "Mañana & tarde")

    def test_normalizar_venta_saca_los_campos_clave(self):
        fila = pagos.normalizar_venta(_venta(), enlace="https://t.me/+Abc123")
        self.assertEqual(fila["id"], "aaaa0000bbbb1111cccc2222")
        self.assertEqual(fila["producto"], "Miércoles Tarde Galgos 3.50")
        self.assertEqual(fila["enlace"], "https://t.me/+Abc123")
        self.assertEqual(fila["correo"], "cliente@example.com")
        self.assertEqual(fila["importe"], 30)
        self.assertEqual(fila["moneda"], "EUR")
        self.assertEqual(fila["neto"], 27)
        self.assertEqual(fila["comision"], 3)
        self.assertEqual(fila["metodo"], "card")
        self.assertEqual(fila["estado"], "SUCCESS")
        self.assertEqual(fila["es_propina"], 0)
        self.assertEqual(fila["pago_ts"], 1793209572)

    def test_normalizar_usa_net_amount_eur_si_hay(self):
        fila = pagos.normalizar_venta(
            _venta(net_amount=100, net_amount_eur=90), enlace=None)
        self.assertEqual(fila["neto"], 90)


class TestGuardar(unittest.TestCase):
    def setUp(self):
        self.con = db.abrir(":memory:")
        self.addCleanup(self.con.close)

    def test_crea_las_tablas(self):
        # No debe lanzar: las tablas existen tras migrar.
        self.con.execute("SELECT * FROM pagos_overoption")
        self.con.execute("SELECT * FROM pagos_contenidos")

    def test_guardar_y_no_duplicar_por_id(self):
        v = pagos.normalizar_venta(_venta(), enlace="https://t.me/+A")
        pagos.guardar_ventas(self.con, [v, v])  # mismo id dos veces
        n = self.con.execute("SELECT COUNT(*) c FROM pagos_overoption").fetchone()["c"]
        self.assertEqual(n, 1)

    def test_guardar_actualiza_si_cambia(self):
        v1 = pagos.normalizar_venta(_venta(), enlace=None)
        pagos.guardar_ventas(self.con, [v1])
        v2 = pagos.normalizar_venta(_venta(), enlace="https://t.me/+NUEVO")
        pagos.guardar_ventas(self.con, [v2])
        fila = self.con.execute("SELECT enlace FROM pagos_overoption").fetchone()
        self.assertEqual(fila["enlace"], "https://t.me/+NUEVO")


class OveroptionFalso:
    """Imita la API de overoption: apunta cada petición y devuelve lo pactado.
    Solo se le piden GET y el POST de login (nada que cambie datos)."""

    def __init__(self, transacciones=None, enlaces=None):
        self.llamadas = []
        self._tx = transacciones or []
        self._enlaces = enlaces or {}  # content_uid -> enlace

    def pedir(self, metodo, ruta, cuerpo=None, params=None, token=None):
        self.llamadas.append((metodo, ruta))
        if ruta == "/auth/login":
            return {"data": {"access_token": "token-de-prueba-xxxxxxxxxxxxx"}}
        if ruta == "/transactions":
            return {"data": {"content": self._tx, "total": len(self._tx)}}
        if ruta.startswith("/content/"):
            uid = ruta.split("/content/")[1]
            return {"data": {"content": {"final_content": self._enlaces.get(uid)}}}
        raise AssertionError("ruta inesperada: " + ruta)

    def metodos(self):
        return [m for m, _ in self.llamadas]


class TestCliente(unittest.TestCase):
    def test_entrar_saca_el_token(self):
        api = OveroptionFalso()
        cli = pagos.ClienteOveroption(pedir=api.pedir)
        cli.entrar("yo@example.com", "secreta")
        self.assertEqual(cli.token, "token-de-prueba-xxxxxxxxxxxxx")
        self.assertEqual(api.llamadas[0], ("POST", "/auth/login"))

    def test_entrar_sin_token_falla(self):
        api = OveroptionFalso()
        api.pedir = lambda *a, **k: {"data": {}}
        cli = pagos.ClienteOveroption(pedir=api.pedir)
        with self.assertRaises(pagos.ErrorOveroption):
            cli.entrar("yo@example.com", "mal")

    def test_transacciones_devuelve_la_lista(self):
        api = OveroptionFalso(transacciones=[_venta(), _venta(_id="otra")])
        cli = pagos.ClienteOveroption(pedir=api.pedir)
        cli.entrar("yo@example.com", "secreta")
        self.assertEqual(len(cli.transacciones()), 2)

    def test_enlace_contenido(self):
        api = OveroptionFalso(enlaces={"uid-1": "https://t.me/+Zzz"})
        cli = pagos.ClienteOveroption(pedir=api.pedir)
        cli.entrar("yo@example.com", "secreta")
        self.assertEqual(cli.enlace_contenido("uid-1"), "https://t.me/+Zzz")

    def test_solo_lectura_nunca_modifica(self):
        # Solo se permite GET y el POST de /auth/login: nada de PUT/DELETE/PATCH
        # ni POST a otras rutas (garantía de que no toca la cuenta).
        api = OveroptionFalso(transacciones=[_venta()], enlaces={})
        cli = pagos.ClienteOveroption(pedir=api.pedir)
        cli.entrar("yo@example.com", "secreta")
        cli.transacciones()
        cli.enlace_contenido("uid-1")
        for metodo, ruta in api.llamadas:
            self.assertTrue(metodo == "GET" or ruta == "/auth/login",
                            msg=f"petición que no es de solo lectura: {metodo} {ruta}")


class TestBajada(unittest.TestCase):
    def setUp(self):
        self.con = db.abrir(":memory:")
        self.addCleanup(self.con.close)

    def test_baja_resuelve_enlaces_y_guarda(self):
        tx = [_venta(_id="v1", content_uid="uid-A"),
              _venta(_id="v2", content_uid="uid-A"),
              _venta(_id="v3", content_uid="uid-B")]
        api = OveroptionFalso(transacciones=tx,
                              enlaces={"uid-A": "https://t.me/+AAA", "uid-B": "https://t.me/+BBB"})
        cli = pagos.ClienteOveroption(pedir=api.pedir)
        n = pagos.bajar_y_guardar(self.con, cli, "yo@example.com", "secreta")
        self.assertEqual(n, 3)
        fila = self.con.execute("SELECT enlace FROM pagos_overoption WHERE id='v1'").fetchone()
        self.assertEqual(fila["enlace"], "https://t.me/+AAA")
        fila = self.con.execute("SELECT enlace FROM pagos_overoption WHERE id='v3'").fetchone()
        self.assertEqual(fila["enlace"], "https://t.me/+BBB")

    def test_no_pide_el_mismo_contenido_dos_veces(self):
        tx = [_venta(_id="v1", content_uid="uid-A"),
              _venta(_id="v2", content_uid="uid-A")]
        api = OveroptionFalso(transacciones=tx, enlaces={"uid-A": "https://t.me/+AAA"})
        cli = pagos.ClienteOveroption(pedir=api.pedir)
        pagos.bajar_y_guardar(self.con, cli, "yo@example.com", "secreta")
        peticiones_contenido = [r for _, r in api.llamadas if r.startswith("/content/")]
        self.assertEqual(peticiones_contenido, ["/content/uid-A"])

    def test_usa_la_cache_de_enlaces_entre_ejecuciones(self):
        tx = [_venta(_id="v1", content_uid="uid-A")]
        api = OveroptionFalso(transacciones=tx, enlaces={"uid-A": "https://t.me/+AAA"})
        cli = pagos.ClienteOveroption(pedir=api.pedir)
        pagos.bajar_y_guardar(self.con, cli, "yo@example.com", "secreta")
        api.llamadas.clear()
        pagos.bajar_y_guardar(self.con, cli, "yo@example.com", "secreta")
        self.assertEqual([r for _, r in api.llamadas if r.startswith("/content/")], [])


if __name__ == "__main__":
    unittest.main()
