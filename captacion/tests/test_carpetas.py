import asyncio
import unittest
from datetime import date, datetime
from zoneinfo import ZoneInfo

from premier_captacion import db
from premier_captacion.carpetas import (Ajustes, Carpeta, CarpetasEnMemoria, Organizador,
                                        detectar_boton, fecha_de_titulo, id_canal_puro, titulo_dia)

from .apoyo import conexion, usuario

MADRID = ZoneInfo("Europe/Madrid")
CANAL = 1234567890          # canal principal (id de Telethon)
VENTA = ("VENTA0000000001", (5550001, "Canal VIP"))
PRINCIPAL = ("PRINCIPAL000001", (CANAL, "PREMIER GALGOS"))


def ts(*fecha_hora):
    return int(datetime(*fecha_hora, tzinfo=MADRID).timestamp())


AHORA = ts(2026, 10, 15, 10, 0)


def carpeta(id_, titulo, usuarios=(), otros=0, **extra):
    return Carpeta(id_, titulo, frozenset(usuarios), len(usuarios) + otros, **extra)


def cuenta_tipica():
    """Como la del dueño: 2 carpetas suyas y 7 de días (08.10 a 14.10)."""
    carpetas = [carpeta(2, "Trabajo", {900, 901}, otros=3), carpeta(3, "Familia", {902})]
    for i, dia in enumerate(range(8, 15)):
        carpetas.append(carpeta(4 + i, f"{dia:02d}.10", {800 + dia}))
    return carpetas


class Base(unittest.TestCase):
    def setUp(self):
        self.con = conexion()
        self.addCleanup(self.con.close)
        self.avisos = []
        self.ahora = AHORA
        self.tg = CarpetasEnMemoria(cuenta_tipica(), destinos=dict([VENTA, PRINCIPAL]))
        self.org = self.organizador()

    def organizador(self, **ajustes):
        aj = dict(canal_principal=CANAL, simular=False)
        aj.update(ajustes)
        return Organizador(self.con, self.tg, MADRID, Ajustes(**aj), avisar=self.avisos.append,
                           reloj=lambda: self.ahora)

    def del_embudo(self, uid, nombre="Ana", **campos):
        with self.con:
            db.actualizar_datos_usuario(self.con, 1, usuario(uid, nombre, nombre.lower()))
            db.marcar_bienvenida(self.con, uid, 1, "bot_b_v1")
            if campos:
                db.actualizar_campos(self.con, uid, 1, **campos)

    def correr(self, corrutina):
        return asyncio.run(corrutina)

    def recibe(self, uid, msg_id, texto="hola", momento=None):
        self.correr(self.org.al_recibir(uid, msg_id, momento or self.ahora, texto))

    def envia(self, uid, msg_id, texto, momento=None):
        self.correr(self.org.al_enviar(uid, msg_id, momento or self.ahora, [texto]))

    def titulos(self):
        return [c.titulo for c in self.correr(self.tg.carpetas())]

    def usuarios_de(self, titulo):
        c = self.tg.por_titulo(titulo)
        return None if c is None else set(c.usuarios)

    def eventos(self, uid=None):
        sql = "SELECT tipo FROM eventos" + (" WHERE user_id = ?" if uid else "") + " ORDER BY id"
        return [f["tipo"] for f in self.con.execute(sql, (uid,) if uid else ())]


class TestCarpetaDelDia(Base):
    def test_primer_mensaje_crea_la_carpeta_de_hoy_y_rota_las_antiguas(self):
        self.del_embudo(500)
        self.recibe(500, 1, "¡Hola! Acabo de entrar en el canal. Es mi primera vez con los galgos 🐕")
        # 15.10 se crea al final; se quedan solo los 5 días más recientes.
        self.assertEqual(self.titulos(), ["Trabajo", "Familia", "11.10", "12.10", "13.10", "14.10", "15.10"])
        self.assertEqual(self.usuarios_de("15.10"), {500})
        fila = db.obtener_usuario(self.con, 500)
        self.assertEqual((fila["carpeta"], fila["boton"], fila["primer_mensaje_ts"]), ("15.10", "primera_vez", AHORA))
        self.assertIn("te_escribe", self.eventos(500))
        self.assertEqual(self.avisos, [])  # en modo real no se avisa de cada cosa

    def test_quien_no_es_del_embudo_no_se_toca(self):
        antes = list(self.tg.cambios)
        self.recibe(999, 1)
        self.assertEqual(self.tg.cambios, antes)
        self.assertIsNone(db.obtener_usuario(self.con, 999))

    def test_si_estaba_en_otro_dia_pasa_a_hoy_y_los_demas_chats_se_quedan(self):
        self.del_embudo(500)
        self.tg = CarpetasEnMemoria([carpeta(2, "14.10", {500, 777})])
        self.org = self.organizador()
        self.recibe(500, 1)
        self.assertEqual(self.usuarios_de("14.10"), {777})  # el chat puesto a mano sigue
        self.assertEqual(self.usuarios_de("15.10"), {500})

    def test_si_la_carpeta_se_queda_vacia_se_borra(self):
        self.del_embudo(500)
        self.tg = CarpetasEnMemoria([carpeta(2, "14.10", {500})])
        self.org = self.organizador()
        self.recibe(500, 1)
        self.assertEqual(self.titulos(), ["15.10"])

    def test_una_carpeta_con_reglas_no_se_borra_aunque_quede_sin_chats(self):
        self.del_embudo(500)
        self.tg = CarpetasEnMemoria([carpeta(2, "14.10", {500}, con_reglas=True)])
        self.org = self.organizador()
        self.recibe(500, 1)
        self.assertEqual(self.usuarios_de("14.10"), set())

    def test_varios_mensajes_el_mismo_dia(self):
        self.del_embudo(500)
        self.recibe(500, 1, "hola")
        cambios = len(self.tg.cambios)
        self.recibe(500, 2, "¿sigues ahí?")
        self.recibe(500, 2, "¿sigues ahí?")  # el mismo mensaje dos veces: se ignora
        self.assertEqual(len(self.tg.cambios), cambios)
        self.assertEqual(self.eventos(500).count("te_escribe"), 1)
        self.assertEqual(db.obtener_usuario(self.con, 500)["boton"], "otro")

    def test_si_primero_saluda_y_luego_responde_cuenta_la_respuesta(self):
        self.del_embudo(500)
        self.recibe(500, 1, "hola!")
        self.assertEqual(db.obtener_usuario(self.con, 500)["boton"], "otro")
        self.recibe(500, 2, "es la primera vez que apuesto")
        self.assertEqual(db.obtener_usuario(self.con, 500)["boton"], "primera_vez")
        self.recibe(500, 3, "bueno, ya he apostado alguna vez")  # vale lo primero que respondió
        self.assertEqual(db.obtener_usuario(self.con, 500)["boton"], "primera_vez")
        self.assertEqual(self.usuarios_de("15.10"), {500})  # la carpeta, con cualquier texto

    def test_al_dia_siguiente_cambia_de_carpeta(self):
        self.del_embudo(500)
        self.recibe(500, 1)
        self.ahora = ts(2026, 10, 16, 9, 0)
        self.recibe(500, 2)
        self.assertNotIn("15.10", self.titulos())  # se quedó vacía
        self.assertEqual(self.usuarios_de("16.10"), {500})
        self.assertEqual(self.eventos(500).count("te_escribe"), 2)

    def test_mensaje_antiguo_se_apunta_pero_no_mueve(self):
        self.del_embudo(500)
        antes = list(self.tg.cambios)
        self.recibe(500, 1, momento=ts(2026, 10, 1, 12, 0))
        self.assertEqual(self.tg.cambios, antes)
        self.assertEqual(db.obtener_usuario(self.con, 500)["primer_mensaje_ts"], ts(2026, 10, 1, 12, 0))

    def test_sin_hueco_borra_antes_el_dia_mas_antiguo(self):
        self.del_embudo(500)
        lista = cuenta_tipica() + [carpeta(20, "Clientes"), carpeta(21, "free send", {1})]  # 11 > 10
        self.tg = CarpetasEnMemoria(lista[:10])  # justo 10 carpetas
        self.org = self.organizador()
        self.recibe(500, 1)
        self.assertIn(("borrar", "08.10"), self.tg.cambios)
        self.assertLess(self.tg.cambios.index(("borrar", "08.10")),
                        self.tg.cambios.index(("crear", "15.10", frozenset({500}))))

    def test_sin_hueco_y_sin_dias_avisa(self):
        self.del_embudo(500)
        self.tg = CarpetasEnMemoria([carpeta(2 + i, f"Mía {i}") for i in range(10)])
        self.org = self.organizador()
        self.recibe(500, 1)
        self.assertEqual(self.tg.cambios, [])
        self.assertIn("No puedo crear la carpeta «15.10»", self.avisos[0])

    def test_carpeta_llena_avisa(self):
        self.del_embudo(500)
        self.tg = CarpetasEnMemoria([carpeta(2, "15.10", set(range(100)))])
        self.org = self.organizador()
        self.recibe(500, 1)
        self.assertIn("ya tiene 100 chats", self.avisos[0])

    def test_las_carpetas_compartidas_no_se_tocan(self):
        self.del_embudo(500)
        self.tg = CarpetasEnMemoria([carpeta(2, "14.10", {500}, gestionable=False)])
        self.org = self.organizador()
        self.recibe(500, 1)  # CarpetasEnMemoria falla si se intenta cambiar una compartida
        self.assertEqual(self.usuarios_de("15.10"), {500})
        self.assertEqual(self.usuarios_de("14.10"), {500})

    def test_carpetas_del_dueno_en_dia_mes(self):
        # Hoy es el 18.10: tiene de la «12.10» a la «18.10» (la de hoy hecha a
        # mano) y la de mañana creada antes de tiempo.
        self.ahora = ts(2026, 10, 18, 10, 0)
        self.tg = CarpetasEnMemoria([carpeta(2, "Trabajo", {900})]
                                    + [carpeta(3 + i, f"{d}.10", {800 + d}) for i, d in enumerate(range(12, 20))])
        self.org = self.organizador()
        self.del_embudo(500)
        self.recibe(500, 1)
        self.assertEqual(self.usuarios_de("18.10"), {500, 818})  # usa la suya
        # Se quedan los 5 días más recientes, contando la de mañana.
        self.assertEqual(self.titulos(), ["Trabajo", "15.10", "16.10", "17.10", "18.10", "19.10"])

    def test_vale_el_dia_sin_cero_delante(self):
        self.ahora = ts(2026, 11, 5, 10, 0)
        self.tg = CarpetasEnMemoria([carpeta(2, "5.11", {777})])
        self.org = self.organizador()
        self.del_embudo(500)
        self.recibe(500, 1)
        self.assertEqual(self.titulos(), ["5.11"])  # no crea otra «05.11»
        self.assertEqual(self.usuarios_de("5.11"), {500, 777})
        self.assertEqual(db.obtener_usuario(self.con, 500)["carpeta"], "5.11")


class TestFreeSend(Base):
    def test_enlace_de_venta_pasa_a_free_send(self):
        self.del_embudo(500)
        self.recibe(500, 1)
        self.envia(500, 2, "Aquí tienes 👉 https://t.me/+VENTA0000000001")
        self.assertNotIn("15.10", self.titulos())
        self.assertEqual(self.usuarios_de("free send"), {500})
        fila = db.obtener_usuario(self.con, 500)
        self.assertEqual((fila["enlace_venta"], fila["canal_venta"], fila["carpeta"]),
                         ("https://t.me/+VENTA0000000001", "Canal VIP", "free send"))
        self.assertEqual(fila["enlace_venta_ts"], AHORA)
        self.assertIn("enlace_venta", self.eventos(500))

    def test_enlace_del_canal_principal_no_cuenta(self):
        self.del_embudo(500)
        self.recibe(500, 1)
        self.envia(500, 2, "Únete: t.me/+PRINCIPAL000001")
        self.assertEqual(self.usuarios_de("15.10"), {500})
        self.assertIsNone(self.usuarios_de("free send"))
        self.assertIn("enlace_principal", self.eventos(500))
        self.assertIsNone(db.obtener_usuario(self.con, 500)["enlace_venta_ts"])

    def test_enlace_desconocido_cuenta_como_venta(self):
        self.del_embudo(500)
        self.envia(500, 1, "https://t.me/+CADUCADO0000001")
        self.assertEqual(db.obtener_usuario(self.con, 500)["canal_venta"], "desconocido")
        self.assertEqual(self.usuarios_de("free send"), {500})

    def test_con_enlace_se_queda_en_free_send_aunque_vuelva_a_escribir(self):
        self.del_embudo(500)
        self.envia(500, 1, "t.me/+VENTA0000000001")
        self.ahora = ts(2026, 10, 16, 9, 0)
        self.recibe(500, 2, "gracias!")
        self.assertNotIn("16.10", self.titulos())
        self.assertEqual(self.usuarios_de("free send"), {500})
        self.assertEqual(self.eventos(500).count("te_escribe"), 1)

    def test_mensajes_sin_enlace_o_de_otros_no_hacen_nada(self):
        self.del_embudo(500)
        antes = list(self.tg.cambios)
        self.envia(500, 1, "te lo paso ahora")
        self.envia(999, 2, "t.me/+VENTA0000000001")  # no es del embudo
        self.assertEqual(self.tg.cambios, antes)

    def test_recorta_a_90_quitando_solo_los_del_embudo_mas_antiguos(self):
        del_embudo = list(range(1000, 1090))
        for i, uid in enumerate(del_embudo):
            self.del_embudo(uid, f"U{i}", enlace_venta_ts=1000 + i)
        a_mano = set(range(2000, 2005))
        self.tg = CarpetasEnMemoria([carpeta(2, "free send", set(del_embudo) | a_mano)])
        self.org = self.organizador()
        self.del_embudo(500)
        self.envia(500, 1, "t.me/+VENTA0000000001")
        dentro = self.usuarios_de("free send")
        self.assertEqual(len(dentro), 90)
        self.assertTrue(a_mano <= dentro)
        self.assertIn(500, dentro)
        self.assertEqual(set(del_embudo) - dentro, set(range(1000, 1006)))  # los 6 más antiguos
        self.assertIsNone(db.obtener_usuario(self.con, 1000)["carpeta"])

    def test_free_send_llena_de_chats_a_mano_avisa(self):
        self.tg = CarpetasEnMemoria([carpeta(2, "free send", set(range(3000, 3100)))])
        self.org = self.organizador()
        self.del_embudo(500)
        self.envia(500, 1, "t.me/+VENTA0000000001")
        self.assertIn("está llena", self.avisos[0])
        self.assertNotIn(500, self.usuarios_de("free send"))

    def test_cada_enlace_se_consulta_una_sola_vez(self):
        consultas = []
        destino_original = self.tg.destino_enlace

        async def contar(h):
            consultas.append(h)
            return await destino_original(h)

        self.tg.destino_enlace = contar
        self.del_embudo(500)
        self.del_embudo(501, "Luis")
        self.envia(500, 1, "t.me/+VENTA0000000001")
        self.envia(501, 2, "t.me/+VENTA0000000001")
        self.assertEqual(consultas, ["VENTA0000000001"])


class TestSimulacion(Base):
    def test_avisa_de_lo_que_haria_y_no_apunta_carpetas(self):
        self.org = self.organizador(simular=True)
        self.del_embudo(500)
        self.recibe(500, 1)
        self.assertTrue(all(a.startswith("🧪 Simulación") for a in self.avisos))
        self.assertTrue(any("creo la carpeta 15.10 y meto a Ana (@ana)" in a for a in self.avisos))
        self.assertTrue(any("borro la carpeta 08.10" in a for a in self.avisos))
        fila = db.obtener_usuario(self.con, 500)
        self.assertIsNone(fila["carpeta"])
        self.assertEqual(fila["primer_mensaje_ts"], AHORA)  # los hechos sí se apuntan
        self.assertNotIn("carpeta", self.eventos())

    def test_parte_de_las_carpetas_reales_sin_cambiarlas(self):
        real = CarpetasEnMemoria(cuenta_tipica(), destinos=dict([VENTA]))
        simulado = self.correr(CarpetasEnMemoria.desde(real))
        self.tg = simulado
        self.org = self.organizador(simular=True)
        self.del_embudo(500)
        self.recibe(500, 1)
        self.envia(500, 2, "t.me/+VENTA0000000001")
        self.assertEqual(real.cambios, [])
        self.assertEqual(self.usuarios_de("free send"), {500})

    def test_cada_dia_vuelve_a_partir_de_las_carpetas_reales(self):
        real = CarpetasEnMemoria(cuenta_tipica(), destinos=dict([VENTA]))
        self.tg = self.correr(CarpetasEnMemoria.desde(real))
        self.org = self.organizador(simular=True)
        self.del_embudo(500)
        self.recibe(500, 1)
        self.assertTrue(any("creo la carpeta 15.10" in a for a in self.avisos))
        # El mismo día no repite nada: ni al volver a escribir ni en cada revisión.
        self.avisos.clear()
        self.recibe(500, 2)
        self.correr(self.org.rotar())
        self.assertEqual(self.avisos, [])
        # Al día siguiente el dueño ya ha creado a mano la carpeta del día.
        self.correr(real.crear_carpeta("16.10", {777}))
        self.ahora = ts(2026, 10, 16, 9, 0)
        self.recibe(500, 3)
        self.assertTrue(any("meto a Ana (@ana) en la carpeta 16.10" in a for a in self.avisos), self.avisos)
        self.assertFalse(any("creo la carpeta" in a for a in self.avisos), self.avisos)
        self.assertEqual(real.cambios, [("crear", "16.10", frozenset({777}))])  # solo lo del dueño


class TestAyudas(unittest.TestCase):
    def test_titulos_de_dias(self):
        # Día.mes, como las carpetas del dueño.
        self.assertEqual(titulo_dia(date(2026, 10, 5)), "05.10")
        hoy = date(2026, 10, 18)
        self.assertEqual(fecha_de_titulo("14.10", hoy), date(2026, 10, 14))
        self.assertEqual(fecha_de_titulo("12.10", hoy), date(2026, 10, 12))  # no el 10 de diciembre
        self.assertEqual(fecha_de_titulo("5.10", hoy), date(2026, 10, 5))
        self.assertEqual(fecha_de_titulo("19.10", hoy), date(2026, 10, 19))  # creada antes de tiempo
        self.assertEqual(fecha_de_titulo("18.04", hoy), date(2026, 4, 18))
        self.assertEqual(fecha_de_titulo("31.12", date(2027, 1, 2)), date(2026, 12, 31))
        self.assertEqual(fecha_de_titulo("02.01", date(2026, 12, 31)), date(2027, 1, 2))
        self.assertEqual(fecha_de_titulo("29.02", date(2028, 3, 1)), date(2028, 2, 29))
        for malo in ("30.02", "01.13", "10.18", "18/10", "18.10.2026", "Trabajo", "free send"):
            self.assertIsNone(fecha_de_titulo(malo, hoy), malo)

    def test_boton(self):
        self.assertEqual(detectar_boton("¡Hola! Acabo de entrar en el canal. Ya he apostado en galgos antes 🐕"),
                         "ya_apostado")
        self.assertEqual(detectar_boton("ES MI PRIMERA VEZ"), "primera_vez")
        self.assertIsNone(detectar_boton("hola"))

    def test_id_canal(self):
        self.assertEqual(id_canal_puro(-1001234567890), 1234567890)
        self.assertIsNone(id_canal_puro(None))


if __name__ == "__main__":
    unittest.main()
