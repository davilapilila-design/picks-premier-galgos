"""Cruce de las ventas de overoption con las entradas a los canales de
Telegram (pagos.emparejar_ventas y agregados). Datos INVENTADOS."""
import unittest

from premier_captacion import db, pagos


def venta(con, id, enlace, pago_ts, producto="Canal X", correo="a@example.com",
          importe=30, neto=27, ahora=1):
    pagos.guardar_ventas(con, [{
        "id": id, "content_uid": None, "portal_uid": None, "producto": producto,
        "enlace": enlace, "correo": correo, "importe": importe, "moneda": "EUR",
        "neto": neto, "comision": 3, "metodo": "card", "estado": "SUCCESS",
        "es_propina": 0, "descuento_codigo": None, "descuento_importe": 0,
        "pago_ts": pago_ts,
    }], ahora=ahora)


def canal(con, canal_id, titulo):
    con.execute("INSERT INTO ventas_canales (canal_id, titulo, leido_ts) VALUES (?, ?, 0)",
                (canal_id, titulo))
    con.commit()


def persona(con, user_id, nombre="Pepe", username="pepe"):
    con.execute("INSERT INTO ventas_personas (user_id, nombre, username) VALUES (?, ?, ?)",
                (user_id, nombre, username))
    con.commit()


def entra_movimiento(con, canal_id, log_id, user_id, ts, enlace):
    con.execute("INSERT INTO ventas_movimientos (canal_id, log_id, user_id, tipo, ts, enlace) "
                "VALUES (?, ?, ?, 'entra', ?, ?)", (canal_id, log_id, user_id, ts, enlace))
    con.commit()


def miembro(con, canal_id, user_id, desde_ts):
    con.execute("INSERT INTO ventas_miembros (canal_id, user_id, desde_ts, visto_ts) "
                "VALUES (?, ?, ?, 0)", (canal_id, user_id, desde_ts))
    con.commit()


def por_id(resultados):
    return {r["id"]: r for r in resultados}


class TestEmparejar(unittest.TestCase):
    def setUp(self):
        self.con = db.abrir(":memory:")
        self.addCleanup(self.con.close)

    def test_empareja_por_enlace_y_hora(self):
        canal(self.con, 10, "Canal X")
        persona(self.con, 500)
        entra_movimiento(self.con, 10, 1, 500, 1000, "https://t.me/+L")
        venta(self.con, "v1", "https://t.me/+L", 1000)
        r = por_id(pagos.emparejar_ventas(self.con, ventana_s=180))["v1"]
        self.assertEqual(r["estado_cruce"], "emparejada")
        self.assertEqual(r["user_id"], 500)
        self.assertEqual(r["canal_id"], 10)

    def test_fuera_de_la_ventana_no_empareja(self):
        canal(self.con, 10, "Canal X")
        entra_movimiento(self.con, 10, 1, 500, 1000 + 600, "https://t.me/+L")  # 10 min
        venta(self.con, "v1", "https://t.me/+L", 1000)
        r = por_id(pagos.emparejar_ventas(self.con, ventana_s=180))["v1"]
        self.assertEqual(r["estado_cruce"], "sin_emparejar")
        self.assertIsNone(r["user_id"])

    def test_varios_en_la_ventana_es_dudosa(self):
        canal(self.con, 10, "Canal X")
        entra_movimiento(self.con, 10, 1, 500, 1000, "https://t.me/+L")
        entra_movimiento(self.con, 10, 2, 501, 1020, "https://t.me/+L")
        venta(self.con, "v1", "https://t.me/+L", 1000)
        r = por_id(pagos.emparejar_ventas(self.con, ventana_s=180))["v1"]
        self.assertEqual(r["estado_cruce"], "dudosa_varios")
        self.assertIsNone(r["user_id"])

    def test_una_entrada_no_vale_para_dos_ventas(self):
        # Solo queda dentro uno; el otro comprador se fue y Telegram no lo enseña.
        canal(self.con, 10, "Canal X")
        entra_movimiento(self.con, 10, 1, 500, 1100, "https://t.me/+L")
        venta(self.con, "v1", "https://t.me/+L", 1000, correo="a@example.com")
        venta(self.con, "v2", "https://t.me/+L", 1090, correo="b@example.com")
        rs = por_id(pagos.emparejar_ventas(self.con, ventana_s=180))
        self.assertEqual((rs["v1"]["estado_cruce"], rs["v2"]["estado_cruce"]),
                         ("dudosa_varios", "dudosa_varios"))
        self.assertIsNone(rs["v1"]["user_id"])

    def test_entrar_antes_de_pagar_no_cuenta(self):
        canal(self.con, 10, "Canal X")
        entra_movimiento(self.con, 10, 1, 500, 1000, "https://t.me/+L")
        venta(self.con, "v1", "https://t.me/+L", 1000 + pagos.ANTES_S + 60)
        r = por_id(pagos.emparejar_ventas(self.con, ventana_s=180))["v1"]
        self.assertEqual(r["estado_cruce"], "sin_emparejar")

    def test_unos_segundos_antes_si_cuenta_por_los_relojes(self):
        canal(self.con, 10, "Canal X")
        entra_movimiento(self.con, 10, 1, 500, 1000, "https://t.me/+L")
        venta(self.con, "v1", "https://t.me/+L", 1000 + pagos.ANTES_S - 5)
        r = por_id(pagos.emparejar_ventas(self.con, ventana_s=180))["v1"]
        self.assertEqual(r["estado_cruce"], "emparejada")

    def test_sin_canal_identificado(self):
        venta(self.con, "v1", "https://t.me/+DESCONOCIDO", 1000, producto="No existe")
        r = por_id(pagos.emparejar_ventas(self.con, ventana_s=180))["v1"]
        self.assertEqual(r["estado_cruce"], "sin_canal")

    def test_empareja_por_nombre_cuando_no_hay_enlace(self):
        canal(self.con, 10, "Domingo Tarde 25.10")
        miembro(self.con, 10, 500, 1000)
        # El nombre del producto en overoption trae tildes/entidades distintas.
        venta(self.con, "v1", None, 1000, producto="Domingo Tarde 25.10")
        r = por_id(pagos.emparejar_ventas(self.con, ventana_s=180))["v1"]
        self.assertEqual(r["canal_id"], 10)
        self.assertEqual(r["estado_cruce"], "emparejada")
        self.assertEqual(r["user_id"], 500)

    def test_nombre_repetido_en_dos_canales_no_empareja_por_nombre(self):
        canal(self.con, 10, "Jueves Central Park")
        canal(self.con, 11, "Jueves Central Park")
        miembro(self.con, 10, 500, 1000)
        venta(self.con, "v1", None, 1000, producto="Jueves Central Park")
        r = por_id(pagos.emparejar_ventas(self.con, ventana_s=180))["v1"]
        self.assertEqual(r["estado_cruce"], "sin_canal")


class TestPorEnlace(unittest.TestCase):
    """Con la lista de quién se unió con cada enlace (invitaciones.py), la
    venta se empareja con quien entró con SU enlace, también en canales
    antiguos que no se siguen."""

    def setUp(self):
        self.con = db.abrir(":memory:")
        self.addCleanup(self.con.close)

    def invitados(self, enlace, canal_id, titulo, filas):
        from premier_captacion import invitaciones
        with self.con:
            invitaciones.guardar(self.con, enlace, canal_id, titulo, filas, ahora=1)

    def test_empareja_en_un_canal_que_no_se_sigue(self):
        self.invitados("https://t.me/+V", 99, "Canal viejo", [(700, "Eva", "eva", 1060)])
        venta(self.con, "v1", "https://t.me/+V", 1000, producto="Otro nombre")
        r = por_id(pagos.emparejar_ventas(self.con, ventana_s=180))["v1"]
        self.assertEqual(r["estado_cruce"], "emparejada")
        self.assertEqual((r["user_id"], r["nombre"]), (700, "Eva"))
        self.assertEqual((r["canal_id"], r["titulo"]), (99, "Canal viejo"))

    def test_solo_cuentan_los_que_entraron_con_ese_enlace(self):
        canal(self.con, 10, "Canal X")
        entra_movimiento(self.con, 10, 1, 500, 1000, "https://t.me/+OTRO")  # otro enlace, misma hora
        self.invitados("https://t.me/+L", 10, "Canal X", [(700, "Eva", None, 1030)])
        venta(self.con, "v1", "https://t.me/+L", 1000)
        r = por_id(pagos.emparejar_ventas(self.con, ventana_s=180))["v1"]
        self.assertEqual(r["estado_cruce"], "emparejada")
        self.assertEqual(r["user_id"], 700)

    def test_enlace_leido_sin_nadie_en_la_ventana_queda_sin_emparejar(self):
        self.invitados("https://t.me/+V", 99, "Canal viejo", [(700, "Eva", None, 9000)])
        venta(self.con, "v1", "https://t.me/+V", 1000)
        r = por_id(pagos.emparejar_ventas(self.con, ventana_s=180))["v1"]
        self.assertEqual(r["estado_cruce"], "sin_emparejar")


class TestPorCorreo(unittest.TestCase):
    """Si una venta se empareja con una persona, las demás compras con ese
    mismo correo son de esa persona (aunque no se sepa el canal o la hora)."""

    def setUp(self):
        self.con = db.abrir(":memory:")
        self.addCleanup(self.con.close)
        canal(self.con, 10, "Canal X")
        persona(self.con, 500, nombre="Ana", username="ana")
        entra_movimiento(self.con, 10, 1, 500, 1000, "https://t.me/+L")
        venta(self.con, "v1", "https://t.me/+L", 1000, correo="ana@example.com")

    def test_venta_sin_canal_del_mismo_correo_es_de_esa_persona(self):
        venta(self.con, "v2", "https://t.me/+VIEJO", 50, producto="Canal viejo",
              correo="ana@example.com")
        r = por_id(pagos.emparejar_ventas(self.con, ventana_s=180))["v2"]
        self.assertEqual(r["estado_cruce"], "por_correo")
        self.assertEqual(r["user_id"], 500)
        self.assertEqual(r["nombre"], "Ana")

    def test_dudosa_y_sin_emparejar_del_mismo_correo_se_resuelven(self):
        entra_movimiento(self.con, 10, 2, 500, 5000, "https://t.me/+L")
        entra_movimiento(self.con, 10, 3, 501, 5010, "https://t.me/+L")
        venta(self.con, "v2", "https://t.me/+L", 5000, correo="ana@example.com")  # dudosa
        venta(self.con, "v3", "https://t.me/+L", 9000, correo="ana@example.com")  # nadie entra
        rs = por_id(pagos.emparejar_ventas(self.con, ventana_s=180))
        for vid in ("v2", "v3"):
            self.assertEqual(rs[vid]["estado_cruce"], "por_correo")
            self.assertEqual(rs[vid]["user_id"], 500)

    def test_otro_correo_no_hereda_la_persona(self):
        venta(self.con, "v2", "https://t.me/+VIEJO", 50, producto="Canal viejo",
              correo="otro@example.com")
        r = por_id(pagos.emparejar_ventas(self.con, ventana_s=180))["v2"]
        self.assertEqual(r["estado_cruce"], "sin_canal")
        self.assertIsNone(r["user_id"])

    def test_correo_con_dos_personas_distintas_no_se_propaga(self):
        canal(self.con, 11, "Canal Y")
        entra_movimiento(self.con, 11, 2, 501, 2000, "https://t.me/+Y")
        venta(self.con, "v2", "https://t.me/+Y", 2000, correo="ana@example.com")
        venta(self.con, "v3", "https://t.me/+VIEJO", 50, producto="Canal viejo",
              correo="ana@example.com")
        r = por_id(pagos.emparejar_ventas(self.con, ventana_s=180))["v3"]
        self.assertEqual(r["estado_cruce"], "sin_canal")
        self.assertIsNone(r["user_id"])

    def test_persona_con_varios_correos_no_se_propaga(self):
        # Ana sale emparejada con dos correos: uno de los dos cruces puede ser falso.
        canal(self.con, 11, "Canal Y")
        entra_movimiento(self.con, 11, 2, 500, 2000, "https://t.me/+Y")
        venta(self.con, "v2", "https://t.me/+Y", 2000, correo="otro@example.com")
        venta(self.con, "v3", "https://t.me/+VIEJO", 50, producto="Canal viejo",
              correo="ana@example.com")
        venta(self.con, "v4", "https://t.me/+VIEJO", 60, producto="Canal viejo",
              correo="otro@example.com")
        rs = por_id(pagos.emparejar_ventas(self.con, ventana_s=180))
        self.assertEqual((rs["v3"]["estado_cruce"], rs["v4"]["estado_cruce"]), ("sin_canal", "sin_canal"))

    def test_pagos_por_persona_suma_las_compras_por_correo(self):
        venta(self.con, "v2", "https://t.me/+VIEJO", 50, producto="Canal viejo",
              correo="ana@example.com", neto=50)
        p = pagos.pagos_por_persona(self.con, ventana_s=180)[500]
        self.assertEqual(p["canales"], 2)       # Canal X + el canal viejo
        self.assertAlmostEqual(p["eur"], 77)    # 27 + 50

    def test_fila_de_pagos_dice_por_correo_y_trae_la_persona(self):
        from zoneinfo import ZoneInfo
        venta(self.con, "v2", "https://t.me/+VIEJO", 50, producto="Canal viejo",
              correo="ana@example.com")
        filas = {f[10]: f for f in pagos.filas_pagos(self.con, ZoneInfo("Europe/Madrid"))}
        self.assertIn("Ana", filas["v2"][8])
        self.assertIn("por correo", filas["v2"][9].lower())

    def test_clientes_trae_la_persona_de_telegram_del_correo(self):
        from zoneinfo import ZoneInfo
        venta(self.con, "v2", None, 50, correo="otro@example.com")
        filas = {f[0]: f for f in pagos.filas_clientes_sheet(self.con, ZoneInfo("Europe/Madrid"))}
        self.assertIn("Ana", filas["ana@example.com"][-1])
        self.assertEqual(filas["otro@example.com"][-1], "")


class TestAgregados(unittest.TestCase):
    def setUp(self):
        self.con = db.abrir(":memory:")
        self.addCleanup(self.con.close)

    def test_pagos_por_persona_cuenta_canales_distintos(self):
        canal(self.con, 10, "Canal A")
        canal(self.con, 11, "Canal B")
        persona(self.con, 500)
        entra_movimiento(self.con, 10, 1, 500, 1000, "https://t.me/+A")
        entra_movimiento(self.con, 11, 2, 500, 2000, "https://t.me/+B")
        venta(self.con, "v1", "https://t.me/+A", 1000, neto=27)
        venta(self.con, "v2", "https://t.me/+B", 2000, neto=50)
        por_persona = pagos.pagos_por_persona(self.con, ventana_s=180)
        self.assertEqual(por_persona[500]["canales"], 2)
        self.assertAlmostEqual(por_persona[500]["eur"], 77)

    def test_filas_clientes_por_correo(self):
        venta(self.con, "v1", None, 1000, correo="cli@example.com", importe=30, neto=27)
        venta(self.con, "v2", None, 5000, correo="cli@example.com", importe=25, neto=22)
        venta(self.con, "v3", None, 1000, correo="otro@example.com", importe=15, neto=13)
        filas = pagos.filas_clientes(self.con)
        por_correo = {f[0]: f for f in filas}
        # [correo, nº compras, total pagado, total recibido, ...]
        self.assertEqual(por_correo["cli@example.com"][1], 2)
        self.assertAlmostEqual(por_correo["cli@example.com"][2], 55)
        self.assertAlmostEqual(por_correo["cli@example.com"][3], 49)
        # el que más compra va primero
        self.assertEqual(filas[0][0], "cli@example.com")


class TestPersonasPagos(unittest.TestCase):
    """Las columnas nuevas de la pestaña Personas: cuántos canales pagó cada
    persona y cuánto suma (de las ventas emparejadas)."""

    def setUp(self):
        self.con = db.abrir(":memory:")
        self.addCleanup(self.con.close)
        from zoneinfo import ZoneInfo
        self.tz = ZoneInfo("Europe/Madrid")

    def test_personas_trae_canales_pagados_y_euros(self):
        from premier_captacion import ventas
        canal(self.con, 10, "Canal X")
        persona(self.con, 500, nombre="Ana", username="ana")
        entra_movimiento(self.con, 10, 1, 500, 1000, "https://t.me/+L")
        venta(self.con, "v1", "https://t.me/+L", 1000, neto=27)
        fila = ventas.filas_personas(self.con, self.tz, set())[0]
        # las dos últimas columnas: canales pagados, € pagado (recibido)
        self.assertEqual(fila[-2], 1)
        self.assertAlmostEqual(fila[-1], 27)

    def test_persona_sin_pago_emparejado_va_a_cero(self):
        from premier_captacion import ventas
        canal(self.con, 10, "Canal X")
        persona(self.con, 500, nombre="Ana", username="ana")
        entra_movimiento(self.con, 10, 1, 500, 1000, "https://t.me/+L")
        # venta en otra hora: no empareja
        venta(self.con, "v1", "https://t.me/+L", 9999, neto=27)
        fila = ventas.filas_personas(self.con, self.tz, set())[0]
        self.assertEqual(fila[-2], 0)
        self.assertEqual(fila[-1], "")


class TestFilasPagos(unittest.TestCase):
    def setUp(self):
        self.con = db.abrir(":memory:")
        self.addCleanup(self.con.close)
        from zoneinfo import ZoneInfo
        self.tz = ZoneInfo("Europe/Madrid")

    def test_fila_de_venta_emparejada(self):
        canal(self.con, 10, "Canal X")
        persona(self.con, 500, nombre="Ana", username="ana")
        entra_movimiento(self.con, 10, 1, 500, 1000, "https://t.me/+L")
        venta(self.con, "v1", "https://t.me/+L", 1000, producto="Canal X",
              correo="ana@example.com", importe=30, neto=27)
        filas = pagos.filas_pagos(self.con, self.tz)
        f = filas[0]
        # [fecha(serie), producto, importe, moneda, €recibido, método,
        #  correo, canal, persona, estado, id]
        self.assertGreater(f[0], 0)              # fecha como número de serie
        self.assertEqual(f[1], "Canal X")
        self.assertEqual(f[2], 30)
        self.assertEqual(f[4], 27)
        self.assertEqual(f[6], "ana@example.com")
        self.assertIn("Ana", f[8])              # persona emparejada
        self.assertIn("emparejada", f[9].lower())
        self.assertEqual(f[10], "v1")

    def test_fila_sin_emparejar_no_inventa_persona(self):
        venta(self.con, "v1", "https://t.me/+DESCONOCIDO", 1000, producto="No existe")
        f = pagos.filas_pagos(self.con, self.tz)[0]
        self.assertEqual(f[8], "")              # sin persona
        self.assertNotIn("emparejada", f[9].lower())


if __name__ == "__main__":
    unittest.main()
