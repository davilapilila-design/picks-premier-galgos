"""Cruce de las ventas de overoption con las personas de Telegram (cruce.py,
pagos.emparejar_ventas y agregados). Reglas del diseño del 2026-11-01. Datos
INVENTADOS."""
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


def invitados(con, enlace, canal_id, titulo, filas):
    """Quién se unió con un enlace (lista de Telegram): filas [(uid, nombre, @, ts)]."""
    from premier_captacion import invitaciones
    with con:
        invitaciones.guardar(con, enlace, canal_id, titulo, filas, ahora=1)


def compra(con, vid, n, ts, correo, entra=(), segundos=5, producto=None):
    """Una compra del canal n (cada canal con su enlace, como en la realidad:
    nadie compra dos veces el mismo) y quienes entran con el enlace
    `segundos` después de pagar (`entra`: un id o varios)."""
    enlace = f"https://t.me/+C{n}"
    if con.execute("SELECT 1 FROM ventas_canales WHERE canal_id = ?", (n,)).fetchone() is None:
        canal(con, n, f"Canal {n}")
    for i, uid in enumerate((entra,) if isinstance(entra, int) else entra):
        entra_movimiento(con, n, ts * 10 + i, uid, ts + segundos + i, enlace)
    venta(con, vid, enlace, ts, producto=producto or f"Canal {n}", correo=correo)


def datos(con):
    from premier_captacion import cruce
    return cruce.Datos(con)


def venta_de(d, vid):
    return next(v for v in d.ventas if v["id"] == vid)


def cruce(con):
    return por_id(pagos.emparejar_ventas(con))


def indicar(con, correo, texto):
    with con:
        pagos.guardar_manuales(con, {correo: texto}, ahora=1)


class TestCandidatos(unittest.TestCase):
    """Candidatos de una venta: quienes entraron entre 0 s y 3 min después
    de pagar (nadie entra antes de pagar: medido en 519 compras)."""

    def setUp(self):
        self.con = db.abrir(":memory:")
        self.addCleanup(self.con.close)
        canal(self.con, 10, "Canal X")

    def candidatos(self, vid="v1"):
        return venta_de(datos(self.con), vid)["candidatos"]

    def test_de_0_a_180_segundos_despues_del_pago(self):
        for i, (uid, ts) in enumerate(((500, 1000), (501, 1180), (502, 1181), (503, 995))):
            entra_movimiento(self.con, 10, i, uid, ts, "https://t.me/+L")
        venta(self.con, "v1", "https://t.me/+L", 1000)
        self.assertEqual(self.candidatos(), {500, 501})

    def test_con_la_lista_del_enlace_solo_cuentan_los_de_ese_enlace(self):
        entra_movimiento(self.con, 10, 1, 500, 1003, "https://t.me/+OTRAVENTA")
        invitados(self.con, "https://t.me/+L", 10, "Canal X", [(700, "Eva", None, 1030)])
        venta(self.con, "v1", "https://t.me/+L", 1000)
        venta(self.con, "v2", "https://t.me/+OTRAVENTA", 900, producto="Otro producto")
        self.assertEqual(self.candidatos(), {700})

    def test_el_registro_trae_tambien_a_quien_se_fue(self):
        invitados(self.con, "https://t.me/+L", 10, "Canal X", [(700, "Eva", None, 5030)])
        entra_movimiento(self.con, 10, 1, 500, 1003, "https://t.me/+L")  # entró y se fue
        venta(self.con, "v1", "https://t.me/+L", 1000)
        self.assertEqual(self.candidatos(), {500})

    def test_registro_con_el_enlace_escrito_de_otra_forma(self):
        # Pasó con un canal: el registro guardaba el mismo enlace con otro texto
        # (se nota porque trae las mismas entradas, al segundo, que la lista).
        invitados(self.con, "https://t.me/+L", 10, "Canal X", [(700, "Eva", None, 5030)])
        entra_movimiento(self.con, 10, 1, 500, 1003, "https://t.me/+OTROTEXTO")  # entró y se fue
        entra_movimiento(self.con, 10, 2, 700, 5030, "https://t.me/+OTROTEXTO")  # como en la lista
        venta(self.con, "v1", "https://t.me/+L", 1000)
        self.assertEqual(self.candidatos(), {500})

    def test_enlace_nuevo_se_sabe_el_canal_por_el_registro(self):
        entra_movimiento(self.con, 10, 1, 500, 1005, "https://t.me/+NUEVO")
        venta(self.con, "v1", "https://t.me/+NUEVO", 1000, producto="Lunes Tarde 7.00 - 3.00")
        v = venta_de(datos(self.con), "v1")
        self.assertEqual((v["candidatos"], v["canal_id"]), ({500}, 10))

    def test_canal_que_no_se_sigue_por_la_lista_del_enlace(self):
        invitados(self.con, "https://t.me/+V", 99, "Canal viejo", [(700, "Eva", "eva", 1060)])
        venta(self.con, "v1", "https://t.me/+V", 1000, producto="Otro nombre")
        v = venta_de(datos(self.con), "v1")
        self.assertEqual((v["candidatos"], v["canal_id"]), ({700}, 99))

    def test_sin_canal_no_hay_candidatos_que_mirar(self):
        venta(self.con, "v1", "https://t.me/+DESCONOCIDO", 1000, producto="No existe")
        self.assertIsNone(self.candidatos())


class TestJuicio(unittest.TestCase):
    """Cada compra frente a una persona: buena (entró justo después de
    pagar), mala (se podía ver y no entró después de pagar) o sin comprobar."""

    def setUp(self):
        self.con = db.abrir(":memory:")
        self.addCleanup(self.con.close)
        canal(self.con, 10, "Canal X")

    def juicio(self, uid, vid="v1"):
        d = datos(self.con)
        return d.juicio(venta_de(d, vid), uid)

    def test_buena(self):
        entra_movimiento(self.con, 10, 1, 500, 1008, "https://t.me/+L")
        venta(self.con, "v1", "https://t.me/+L", 1000)
        self.assertEqual(self.juicio(500), "buena")

    def test_mala_si_entro_a_otra_hora(self):
        miembro(self.con, 10, 500, 1600)  # 10 min después
        venta(self.con, "v1", "https://t.me/+L", 1000)
        self.assertEqual(self.juicio(500), "mala")

    def test_mala_si_el_registro_cubria_la_hora_y_no_entro(self):
        entra_movimiento(self.con, 10, 1, 501, 900, "https://t.me/+L")  # el registro empieza antes
        venta(self.con, "v1", "https://t.me/+L", 1000)
        self.assertEqual(self.juicio(500), "mala")

    def test_sin_comprobar_si_no_hay_registro_ni_sigue_dentro(self):
        venta(self.con, "v1", "https://t.me/+L", 1000)
        miembro(self.con, 10, 501, 1005)
        self.assertEqual(self.juicio(500), "sin")

    def test_sin_comprobar_si_ya_estaba_dentro_antes_de_pagar(self):
        miembro(self.con, 10, 500, 400)
        venta(self.con, "v1", "https://t.me/+L", 1000)
        self.assertEqual(self.juicio(500), "sin")

    def test_sin_comprobar_si_no_se_sabe_el_canal(self):
        venta(self.con, "v1", "https://t.me/+DESCONOCIDO", 1000, producto="No existe")
        self.assertEqual(self.juicio(500), "sin")


class TestVentaSinDueno(unittest.TestCase):
    """Mientras su correo no sea de nadie, una venta no lleva persona: solo
    sus candidatos (`posibles`). Un cruce suelto por hora nunca da el correo."""

    def setUp(self):
        self.con = db.abrir(":memory:")
        self.addCleanup(self.con.close)
        canal(self.con, 10, "Canal X")
        persona(self.con, 500)

    def test_un_cruce_suelto_no_da_persona(self):
        entra_movimiento(self.con, 10, 1, 500, 1000, "https://t.me/+L")
        venta(self.con, "v1", "https://t.me/+L", 1000)
        r = cruce(self.con)["v1"]
        self.assertEqual((r["estado_cruce"], r["user_id"], r["posibles"], r["canal_id"]),
                         ("dudosa_varios", None, [500], 10))

    def test_fuera_de_la_ventana_queda_sin_emparejar(self):
        entra_movimiento(self.con, 10, 1, 500, 1000 + 600, "https://t.me/+L")  # 10 min
        venta(self.con, "v1", "https://t.me/+L", 1000)
        r = cruce(self.con)["v1"]
        self.assertEqual((r["estado_cruce"], r["user_id"]), ("sin_emparejar", None))

    def test_entrar_antes_de_pagar_no_cuenta(self):
        entra_movimiento(self.con, 10, 1, 500, 995, "https://t.me/+L")
        venta(self.con, "v1", "https://t.me/+L", 1000)
        self.assertEqual(cruce(self.con)["v1"]["estado_cruce"], "sin_emparejar")

    def test_varios_en_la_ventana(self):
        entra_movimiento(self.con, 10, 1, 500, 1000, "https://t.me/+L")
        entra_movimiento(self.con, 10, 2, 501, 1020, "https://t.me/+L")
        venta(self.con, "v1", "https://t.me/+L", 1000)
        r = cruce(self.con)["v1"]
        self.assertEqual((r["estado_cruce"], r["posibles"]), ("dudosa_varios", [500, 501]))

    def test_sin_canal_identificado(self):
        venta(self.con, "v1", "https://t.me/+DESCONOCIDO", 1000, producto="No existe")
        self.assertEqual(cruce(self.con)["v1"]["estado_cruce"], "sin_canal")

    def test_canal_por_el_nombre_del_producto(self):
        canal(self.con, 11, "Domingo Tarde 25.10")
        miembro(self.con, 11, 500, 1000)
        venta(self.con, "v1", None, 1000, producto="Domingo Tarde 25.10")
        r = cruce(self.con)["v1"]
        self.assertEqual((r["canal_id"], r["posibles"]), (11, [500]))

    def test_nombre_repetido_en_dos_canales_no_vale_para_saber_el_canal(self):
        canal(self.con, 11, "Jueves Central Park")
        canal(self.con, 12, "Jueves Central Park")
        miembro(self.con, 11, 500, 1000)
        venta(self.con, "v1", None, 1000, producto="Jueves Central Park")
        self.assertEqual(cruce(self.con)["v1"]["estado_cruce"], "sin_canal")


class TestPorCompras(unittest.TestCase):
    """Un correo es de una persona si entró justo después de pagar en 3
    compras o más, que son al menos el 80 % de las que se pueden comprobar,
    y nadie le hace sombra."""

    def setUp(self):
        self.con = db.abrir(":memory:")
        self.addCleanup(self.con.close)
        persona(self.con, 500, nombre="Ana", username="ana")
        persona(self.con, 501, nombre="Luis", username="luis")

    def compras(self, correo, entra, desde=1, n=3, base=1000):
        for i in range(desde, desde + n):
            compra(self.con, f"{correo[:4]}{i}", i, base * i, correo, entra=entra)

    def test_tres_buenas_dan_el_correo_y_todas_sus_compras(self):
        self.compras("ana@example.com", 500)
        venta(self.con, "vieja", "https://t.me/+VIEJO", 50, producto="Canal viejo", correo="ana@example.com")
        rs = cruce(self.con)
        for vid in ("ana@1", "ana@2", "ana@3", "vieja"):
            self.assertEqual((rs[vid]["estado_cruce"], rs[vid]["user_id"]), ("por_correo", 500), vid)
        self.assertEqual(rs["vieja"]["nombre"], "Ana")

    def test_dos_buenas_no_bastan(self):
        self.compras("ana@example.com", 500, n=2)
        rs = cruce(self.con)
        self.assertEqual((rs["ana@1"]["estado_cruce"], rs["ana@1"]["user_id"], rs["ana@1"]["posibles"]),
                         ("dudosa_varios", None, [500]))

    def test_hace_falta_el_80_por_ciento_de_las_comprobables(self):
        self.compras("ana@example.com", 500)
        compra(self.con, "mala", 9, 9000, "ana@example.com")
        miembro(self.con, 9, 500, 9000 + 600)  # entró, pero 10 min después
        self.assertIsNone(cruce(self.con)["ana@1"]["user_id"])  # 3 de 4 = 75 %
        compra(self.con, "otra", 8, 8000, "ana@example.com", entra=500)
        self.assertEqual(cruce(self.con)["ana@1"]["user_id"], 500)  # 4 de 5 = 80 %

    def test_si_otra_persona_le_hace_sombra_no(self):
        self.compras("ana@example.com", (500, 501), n=3)
        compra(self.con, "ana@4", 4, 4000, "ana@example.com", entra=500)
        self.assertIsNone(cruce(self.con)["ana@1"]["user_id"])  # 4 frente a 3

    def test_sombra_pequena_si(self):
        self.compras("ana@example.com", (500, 501), n=2)
        self.compras("ana@example.com", 500, desde=3, n=2)
        self.assertEqual(cruce(self.con)["ana@1"]["user_id"], 500)  # 4 frente a 2

    def test_nadie_paga_dos_veces_el_mismo_canal(self):
        # Luis compra los mismos canales que Ana a la vez: la entrada de Ana
        # cae también en sus compras, pero ella ya pagó esos canales.
        self.compras("ana@example.com", 500)
        for i in range(1, 4):
            venta(self.con, f"luis{i}", f"https://t.me/+C{i}", 1000 * i + 2, producto=f"Canal {i}",
                  correo="luis@example.com")
        rs = cruce(self.con)
        self.assertEqual(rs["ana@1"]["user_id"], 500)
        for i in range(1, 4):
            r = rs[f"luis{i}"]
            self.assertEqual((r["user_id"], r["posibles"], r["estado_cruce"]), (None, [], "sin_emparejar"))

    def test_una_persona_puede_tener_dos_correos_con_canales_distintos(self):
        self.compras("ana@example.com", 500)
        self.compras("ana.nueva@example.com", 500, desde=4)
        rs = cruce(self.con)
        self.assertEqual((rs["ana@1"]["user_id"], rs["ana.4"]["user_id"]), (500, 500))

    def test_mayusculas_y_espacios_son_el_mismo_correo(self):
        compra(self.con, "v1", 1, 1000, " Ana@Example.COM ", entra=500)
        compra(self.con, "v2", 2, 2000, "ana@example.com", entra=500)
        compra(self.con, "v3", 3, 3000, "ANA@example.com", entra=500)
        self.assertEqual(cruce(self.con)["v1"]["user_id"], 500)

    def test_otro_correo_no_hereda_la_persona(self):
        self.compras("ana@example.com", 500)
        venta(self.con, "otro", "https://t.me/+VIEJO", 50, producto="Canal viejo", correo="otro@example.com")
        r = cruce(self.con)["otro"]
        self.assertEqual((r["estado_cruce"], r["user_id"]), ("sin_canal", None))


class TestNombreQueChoca(unittest.TestCase):
    """«victor…» no puede ser «Raúl» solo por la hora: lo decide el dueño."""

    def setUp(self):
        self.con = db.abrir(":memory:")
        self.addCleanup(self.con.close)

    def tres_buenas(self, nombre):
        persona(self.con, 500, nombre=nombre, username=None)
        for i in range(1, 4):
            compra(self.con, f"v{i}", i, 1000 * i, "victorlopez@example.com", entra=500)
        return cruce(self.con)["v1"]

    def test_otro_nombre_no_se_asigna(self):
        r = self.tres_buenas("Raul")
        self.assertEqual((r["user_id"], r["posibles"]), (None, [500]))

    def test_su_nombre_si(self):
        self.assertEqual(self.tres_buenas("Victor Lopez")["user_id"], 500)


class TestManual(unittest.TestCase):
    """El dueño dice de quién es un correo: todas sus compras son de esa
    persona; con «no», ese correo no se asigna solo."""

    def setUp(self):
        self.con = db.abrir(":memory:")
        self.addCleanup(self.con.close)
        persona(self.con, 500, nombre="Ana", username="ana")
        persona(self.con, 501, nombre="Luis", username="Luis_99")
        venta(self.con, "v1", "https://t.me/+VIEJO", 50, producto="Canal viejo", correo="luis@example.com")
        venta(self.con, "v2", "https://t.me/+VIEJO2", 60, producto="Otro viejo", correo="Luis@Example.com")

    def test_con_usuario_asigna_todas_sus_compras(self):
        indicar(self.con, "luis@example.com", "@luis_99")  # sin distinguir mayúsculas
        rs = cruce(self.con)
        for vid in ("v1", "v2"):
            self.assertEqual((rs[vid]["estado_cruce"], rs[vid]["user_id"]), ("manual", 501))
        self.assertEqual(rs["v1"]["nombre"], "Luis")

    def test_con_id_o_enlace(self):
        for texto in ("501", "https://t.me/Luis_99", " Luis_99 "):
            indicar(self.con, "luis@example.com", texto)
            self.assertEqual(cruce(self.con)["v1"]["user_id"], 501, texto)

    def test_persona_que_no_ha_entrado_en_tus_canales_no_se_asigna(self):
        indicar(self.con, "luis@example.com", "@nadie")
        self.assertEqual(cruce(self.con)["v1"]["estado_cruce"], "sin_canal")

    def test_lo_tuyo_manda_sobre_las_compras_de_otra_persona(self):
        for i in range(1, 4):
            compra(self.con, f"c{i}", i, 1000 * i, "luis@example.com", entra=500)
        indicar(self.con, "luis@example.com", "@luis_99")
        r = cruce(self.con)["c1"]
        self.assertEqual((r["estado_cruce"], r["user_id"]), ("manual", 501))

    def test_no_bloquea_tambien_las_compras(self):
        for i in range(1, 4):
            compra(self.con, f"c{i}", i, 1000 * i, "xk81@example.com", entra=500)
        self.assertEqual(cruce(self.con)["c1"]["user_id"], 500)
        indicar(self.con, "xk81@example.com", "no")
        self.assertIsNone(cruce(self.con)["c1"]["user_id"])

    def test_borrar_quita_la_asignacion(self):
        indicar(self.con, "luis@example.com", "@luis_99")
        indicar(self.con, "luis@example.com", "")
        self.assertEqual(cruce(self.con)["v1"]["estado_cruce"], "sin_canal")


class TestPorNombre(unittest.TestCase):
    """Correos con el nombre o el @usuario de una persona de Telegram
    (nombres.py): si es seguro, todas sus compras son de esa persona."""

    CORREO = "luisferrandiz80@example.com"

    def setUp(self):
        from premier_captacion import nombres
        self.nombres = nombres
        self.con = db.abrir(":memory:")
        self.addCleanup(self.con.close)
        canal(self.con, 10, "Canal X")
        persona(self.con, 500, nombre="Ana", username="ana")
        venta(self.con, "v1", "https://t.me/+VIEJO", 50, producto="Canal viejo", correo=self.CORREO)

    def chats(self, *personas):
        with self.con:
            self.nombres.guardar_chats(self.con, personas, ahora=1)

    def test_nombre_y_apellido_de_un_chat_privado(self):
        self.chats((800, "Luis Ferrandiz", None))
        r = cruce(self.con)["v1"]
        self.assertEqual((r["estado_cruce"], r["user_id"], r["nombre"]), ("por_nombre", 800, "Luis Ferrandiz"))

    def test_si_le_falta_un_apellido_hace_falta_la_hora(self):
        self.chats((800, "Luis Ferrandiz Gimeno", None))  # «gimeno» no está en el correo
        self.assertEqual(cruce(self.con)["v1"]["estado_cruce"], "sin_canal")
        # Entró a la hora de una de sus compras (junto con Ana): ahora sí.
        venta(self.con, "v2", "https://t.me/+L", 5000, correo=self.CORREO)
        entra_movimiento(self.con, 10, 1, 500, 5002, "https://t.me/+L")
        entra_movimiento(self.con, 10, 2, 800, 5004, "https://t.me/+L")
        r = cruce(self.con)["v1"]
        self.assertEqual((r["estado_cruce"], r["user_id"]), ("por_nombre", 800))

    def test_dos_personas_que_casan_igual_no_se_aplica(self):
        self.chats((800, "Luis Ferrandiz", None), (801, "Luis Ferrandiz", None))
        self.assertEqual(cruce(self.con)["v1"]["estado_cruce"], "sin_canal")

    def test_un_cruce_suelto_con_otra_persona_no_lo_impide(self):
        self.chats((800, "Luis Ferrandiz", None))
        compra(self.con, "v2", 1, 5000, self.CORREO, entra=500)  # una sola vez con Ana
        r = cruce(self.con)["v2"]
        self.assertEqual((r["estado_cruce"], r["user_id"]), ("por_nombre", 800))

    def test_si_la_hora_da_otra_persona_no_se_aplica_el_nombre(self):
        self.chats((800, "Luis Ferrandiz", None))
        for i in range(1, 4):
            compra(self.con, f"c{i}", i, 1000 * i, self.CORREO, entra=500)  # tres veces Ana
        r = cruce(self.con)["v1"]
        self.assertEqual((r["estado_cruce"], r["user_id"]), ("sin_canal", None))  # lo decide el dueño

    def test_lo_que_dice_el_dueno_manda(self):
        self.chats((800, "Luis Ferrandiz", None), (801, "Pepe", "pepe_otro"))
        indicar(self.con, self.CORREO, "@pepe_otro")
        r = cruce(self.con)["v1"]
        self.assertEqual((r["estado_cruce"], r["user_id"]), ("manual", 801))  # también de los chats

    def test_escribir_no_lo_bloquea(self):
        self.chats((800, "Luis Ferrandiz", None))
        indicar(self.con, self.CORREO, "no")
        self.assertEqual(cruce(self.con)["v1"]["estado_cruce"], "sin_canal")

    def test_la_pestana_lo_ensena_y_dice_como_quitarlo(self):
        from zoneinfo import ZoneInfo
        self.chats((800, "Luis Ferrandiz", None))
        tz = ZoneInfo("Europe/Madrid")
        f = next(f for f in pagos.filas_por_identificar(self.con, tz) if f[0] == self.CORREO)
        self.assertIn("🤖", f[pagos.COLUMNA_MANUAL + 1])
        self.assertIn("Luis Ferrandiz", f[pagos.COLUMNA_MANUAL + 1])
        indicar(self.con, self.CORREO, "no")
        f = next(f for f in pagos.filas_por_identificar(self.con, tz) if f[0] == self.CORREO)
        self.assertIn("🚫", f[pagos.COLUMNA_MANUAL + 1])


class TestExamen(unittest.TestCase):
    """El cruce sin lo que escribió el dueño, comparado con lo que escribió."""

    def setUp(self):
        self.con = db.abrir(":memory:")
        self.addCleanup(self.con.close)
        persona(self.con, 500, nombre="Ana", username="ana")
        persona(self.con, 501, nombre="Luis", username="luis")
        for i in range(1, 4):
            compra(self.con, f"a{i}", i, 1000 * i, "ana@example.com", entra=500)  # lo acierta
        for i in range(4, 6):
            compra(self.con, f"l{i}", i, 1000 * i, "luis@example.com", entra=501)  # no llega
        indicar(self.con, "ana@example.com", "@ana")
        indicar(self.con, "luis@example.com", "@luis")

    def examen(self):
        from premier_captacion import cruce as modulo
        return modulo.examen(self.con)

    def test_cuenta_bien_y_sin_persona(self):
        self.assertEqual(self.examen(), {"correos": 2, "bien": 3, "mal": 0, "sin": 2, "correos_mal": []})

    def test_cuenta_mal_y_dice_el_correo(self):
        for i in range(6, 9):
            compra(self.con, f"p{i}", i, 1000 * i, "pepe@example.com", entra=500)
        indicar(self.con, "pepe@example.com", "@luis")  # el dueño dice Luis; la hora, Ana
        e = self.examen()
        self.assertEqual((e["mal"], e["correos_mal"]), (3, ["pepe@example.com"]))


class TestPestanaPorIdentificar(unittest.TestCase):
    """Pestaña del Sheet con los correos sin persona, de más a menos compras,
    con una columna para que el dueño escriba su @usuario de Telegram."""

    def setUp(self):
        from zoneinfo import ZoneInfo

        from premier_captacion import sheet

        from .test_sheet import LibroFalso
        self.con = db.abrir(":memory:")
        self.addCleanup(self.con.close)
        self.tz = ZoneInfo("Europe/Madrid")
        persona(self.con, 500, nombre="Ana", username="ana")
        persona(self.con, 501, nombre="Luis", username="luis")
        for i in range(1, 4):  # resuelto
            compra(self.con, f"a{i}", 10 + i, 1000 * i, "ana@example.com", entra=500)
        for i in range(3):
            venta(self.con, f"l{i}", "https://t.me/+VIEJO", 50 + i, correo="luis@example.com", neto=10)
        venta(self.con, "p1", "https://t.me/+VIEJO", 70, correo="pepe@example.com", neto=10)
        self.falso = LibroFalso()
        self.libro = sheet.LibroGoogle(self.falso)

    def escribir(self):
        self.libro.preparar()
        pagos.escribir_pestanas(self.con, self.tz, self.libro)
        return self.falso.hoja(pagos.TAB_POR_IDENTIFICAR)

    def fila(self, hoja, correo):
        return next(f for f in hoja.tabla()[1:] if f[0] == correo)

    def test_lista_los_correos_sin_persona_de_mas_a_menos_compras(self):
        tabla = self.escribir().tabla()
        self.assertEqual(tabla[0], pagos.CABECERA_POR_IDENTIFICAR)
        self.assertEqual([f[0] for f in tabla[1:]], ["luis@example.com", "pepe@example.com"])
        self.assertEqual(tabla[1][1], 3)  # compras

    def test_lo_que_escribe_el_dueno_se_guarda_y_se_aplica(self):
        hoja = self.escribir()
        n = [f[0] for f in hoja.tabla()].index("luis@example.com") + 1
        hoja.celdas[(n, pagos.COLUMNA_MANUAL + 1)] = "@luis"
        hoja = self.escribir()
        f = self.fila(hoja, "luis@example.com")
        self.assertEqual(f[pagos.COLUMNA_MANUAL], "@luis")  # se queda escrito
        self.assertIn("Luis", f[pagos.COLUMNA_MANUAL + 1])  # ✅ aplicado
        pagos_tab = self.falso.hoja(pagos.TAB_PAGOS).tabla()
        self.assertTrue(all("Luis" in r[8] for r in pagos_tab[1:] if r[6] == "luis@example.com"))

    def test_si_no_encuentra_a_la_persona_lo_dice(self):
        hoja = self.escribir()
        n = [f[0] for f in hoja.tabla()].index("pepe@example.com") + 1
        hoja.celdas[(n, pagos.COLUMNA_MANUAL + 1)] = "@nadie"
        f = self.fila(self.escribir(), "pepe@example.com")
        self.assertIn("no encuentro", f[pagos.COLUMNA_MANUAL + 1])

    def test_vaciar_la_celda_lo_quita(self):
        hoja = self.escribir()
        n = [f[0] for f in hoja.tabla()].index("luis@example.com") + 1
        hoja.celdas[(n, pagos.COLUMNA_MANUAL + 1)] = "@luis"
        hoja = self.escribir()
        n = [f[0] for f in hoja.tabla()].index("luis@example.com") + 1
        del hoja.celdas[(n, pagos.COLUMNA_MANUAL + 1)]
        self.escribir()
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM pagos_correos_manual").fetchone()[0], 0)


class TestAgregados(unittest.TestCase):
    def setUp(self):
        self.con = db.abrir(":memory:")
        self.addCleanup(self.con.close)

    def test_pagos_por_persona_cuenta_canales_distintos(self):
        persona(self.con, 500)
        for i in range(1, 4):
            compra(self.con, f"v{i}", i, 1000 * i, "cli@example.com", entra=500)
        por_persona = pagos.pagos_por_persona(self.con)
        self.assertEqual(por_persona[500]["canales"], 3)
        self.assertAlmostEqual(por_persona[500]["eur"], 81)

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

    def test_clientes_trae_la_persona_de_telegram_del_correo(self):
        from zoneinfo import ZoneInfo
        persona(self.con, 500, nombre="Ana", username="ana")
        for i in range(1, 4):
            compra(self.con, f"v{i}", i, 1000 * i, "Ana@Example.com", entra=500)
        venta(self.con, "o1", None, 50, correo="otro@example.com")
        filas = {f[0]: f for f in pagos.filas_clientes_sheet(self.con, ZoneInfo("Europe/Madrid"))}
        self.assertIn("Ana", filas["ana@example.com"][-1])
        self.assertEqual(filas["ana@example.com"][1], 3)  # el mismo correo con mayúsculas
        self.assertEqual(filas["otro@example.com"][-1], "")


class TestPersonasPagos(unittest.TestCase):
    """Las columnas de la pestaña Personas: cuántos canales pagó cada
    persona y cuánto suma (de las ventas con persona)."""

    def setUp(self):
        self.con = db.abrir(":memory:")
        self.addCleanup(self.con.close)
        from zoneinfo import ZoneInfo
        self.tz = ZoneInfo("Europe/Madrid")
        persona(self.con, 500, nombre="Ana", username="ana")

    def test_personas_trae_canales_pagados_y_euros(self):
        from premier_captacion import ventas
        for i in range(1, 4):
            compra(self.con, f"v{i}", i, 1000 * i, "ana@example.com", entra=500)
        fila = ventas.filas_personas(self.con, self.tz, set())[0]
        # las dos últimas columnas: canales pagados, € pagado (recibido)
        self.assertEqual(fila[-2], 3)
        self.assertAlmostEqual(fila[-1], 81)

    def test_persona_sin_pago_con_persona_va_a_cero(self):
        from premier_captacion import ventas
        canal(self.con, 10, "Canal X")
        entra_movimiento(self.con, 10, 1, 500, 1000, "https://t.me/+L")
        venta(self.con, "v1", "https://t.me/+L", 9999, neto=27)  # en otra hora
        fila = ventas.filas_personas(self.con, self.tz, set())[0]
        self.assertEqual(fila[-2], 0)
        self.assertEqual(fila[-1], "")


class TestFilasPagos(unittest.TestCase):
    def setUp(self):
        self.con = db.abrir(":memory:")
        self.addCleanup(self.con.close)
        from zoneinfo import ZoneInfo
        self.tz = ZoneInfo("Europe/Madrid")

    def test_fila_de_venta_con_persona(self):
        persona(self.con, 500, nombre="Ana", username="ana")
        for i in range(1, 4):
            compra(self.con, f"v{i}", i, 1000 * i, "ana@example.com", entra=500)
        f = {f[10]: f for f in pagos.filas_pagos(self.con, self.tz)}["v1"]
        # [fecha(serie), producto, importe, moneda, €recibido, método,
        #  correo, canal, persona, estado, id]
        self.assertGreater(f[0], 0)              # fecha como número de serie
        self.assertEqual(f[1], "Canal 1")
        self.assertEqual(f[2], 30)
        self.assertEqual(f[4], 27)
        self.assertEqual(f[6], "ana@example.com")
        self.assertEqual(f[7], "Canal 1")
        self.assertIn("Ana", f[8])
        self.assertIn("por compras", f[9].lower())

    def test_fila_sin_canal_no_inventa_persona(self):
        venta(self.con, "v1", "https://t.me/+DESCONOCIDO", 1000, producto="No existe")
        f = pagos.filas_pagos(self.con, self.tz)[0]
        self.assertEqual(f[8], "")              # sin persona
        self.assertIn("canal no identificado", f[9])


if __name__ == "__main__":
    unittest.main()
