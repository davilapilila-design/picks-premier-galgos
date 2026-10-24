import unittest
from urllib.parse import parse_qs, urlparse

from premier_captacion import mensajes, textos

# Copiado tal cual del mensaje de bienvenida que el dueño enviaba a mano
# (2026-10-14). Si alguna letra "negrita" de mensajes.py no coincidiera con
# estas, el test falla.
ORIGINAL_LINEA_1 = "Buenas! Bienvenido a 𝗣𝗥𝗘𝗠𝗜𝗘𝗥 𝗚𝗔𝗟𝗚𝗢𝗦 🐕"
ORIGINAL_LINEA_2 = (
    "Para empezar 𝘁𝗲 𝗿𝗲𝗴𝗮𝗹𝗼 𝘂𝗻𝗮 𝗮𝗽𝘂𝗲𝘀𝘁𝗮 𝗱𝗲 𝗽𝗮𝗴𝗼 para que veas cómo trabajo. "
    "Aquí todo va con 𝗧𝗥𝗔𝗡𝗦𝗣𝗔𝗥𝗘𝗡𝗖𝗜𝗔."
)


class TestNegrita(unittest.TestCase):
    def test_letras_y_digitos(self):
        self.assertEqual(mensajes.negrita("Az09"), "𝗔𝘇𝟬𝟵")

    def test_respeta_espacios_y_emojis(self):
        self.assertEqual(mensajes.negrita(" 🐕. €"), " 🐕. €")

    def test_tildes_con_la_letra_en_negrita(self):
        # No hay «é» en negrita: va la «e» en negrita y la tilde suelta encima.
        self.assertEqual(mensajes.negrita("é ñ"), "𝗲́ 𝗻̃")


class TestBienvenida(unittest.TestCase):
    def test_coincide_con_el_texto_original(self):
        lineas = mensajes.TEXTO_BIENVENIDA.split("\n")
        self.assertEqual(lineas[0], ORIGINAL_LINEA_1)
        self.assertEqual(lineas[1], "")
        self.assertEqual(lineas[2], ORIGINAL_LINEA_2)

    def test_cabe_en_un_mensaje(self):
        self.assertLess(len(mensajes.TEXTO_BIENVENIDA), 4096)


class TestBotones(unittest.TestCase):
    def test_dos_botones_al_perfil_con_texto_escrito(self):
        teclado = mensajes.teclado_respuesta("Dronwhite")["inline_keyboard"]
        self.assertEqual(len(teclado), 2)
        borradores = []
        for fila in teclado:
            self.assertEqual(len(fila), 1)
            url = urlparse(fila[0]["url"])
            self.assertEqual((url.scheme, url.netloc, url.path), ("https", "t.me", "/Dronwhite"))
            borradores.append(parse_qs(url.query)["text"][0])
        self.assertEqual(borradores[0], "¡Hola! Acabo de entrar en el canal. Ya he apostado en galgos antes 🐕")
        self.assertEqual(borradores[1], "¡Hola! Acabo de entrar en el canal. Es mi primera vez con los galgos 🐕")

    def test_cada_boton_deja_una_frase_distinta(self):
        # La fase 3 distingue la respuesta por estas frases.
        a, b = (texto for _, texto in mensajes.BOTONES)
        self.assertIn(mensajes.FRASE_YA_APOSTADO, a)
        self.assertNotIn(mensajes.FRASE_YA_APOSTADO, b)
        self.assertIn(mensajes.FRASE_PRIMERA_VEZ, b)
        self.assertNotIn(mensajes.FRASE_PRIMERA_VEZ, a)


class TestDudasFrecuentes(unittest.TestCase):
    def test_cada_tema_esta_completo_y_se_puede_cambiar(self):
        for tema, datos in mensajes.FAQ.items():
            with self.subTest(tema):
                self.assertTrue({"boton", "titulo", "duda", "texto"} <= set(datos))
                for destino, _ in datos.get("enlaces", ()):
                    self.assertIn(destino, mensajes.FAQ)
                self.assertIn(f"faq:{tema}", mensajes.TEXTOS_EDITABLES)
        self.assertEqual(mensajes.FAQ_MENU, ["casas", "horarios", "packs", "problemas"])  # 4 botones
        # El resto se llega desde algún tema (nadie se queda sin camino).
        destinos = {d for datos in mensajes.FAQ.values() for d, _ in datos.get("enlaces", ())}
        self.assertEqual(set(mensajes.FAQ) - set(mensajes.FAQ_MENU) - destinos, set())

    def test_caben_en_telegram(self):
        pie = max(mensajes.PIE_SIN_GRATUITA, mensajes.PIE_CON_GRATUITA, key=len)
        for tema in mensajes.FAQ:
            completo = mensajes.mensaje_tema(tema, mensajes.FAQ[tema]["texto"], pie)
            self.assertLess(len(completo.encode("utf-16-le")) // 2, 4096)
            for gratuita in (False, True):
                for fila in mensajes.teclado_tema(tema, "Dronwhite", gratuita)["inline_keyboard"]:
                    for boton in fila:
                        if "callback_data" in boton:  # Telegram no admite más de 64 bytes
                            self.assertLessEqual(len(boton["callback_data"].encode()), 64)
        for clave, (_, texto) in mensajes.TEXTOS_EDITABLES.items():
            self.assertLessEqual(len(f"txt_orig:{clave}".encode()), 64)
            self.assertIsNone(textos.problema(texto), clave)

    def test_sin_la_gratuita_llevan_los_botones_de_la_bienvenida(self):
        bienvenida = [fila[0]["url"] for fila in mensajes.teclado_respuesta("Dronwhite")["inline_keyboard"]]
        tema = mensajes.teclado_tema("horarios", "Dronwhite", False)["inline_keyboard"]
        self.assertEqual([b["url"] for b in tema[0]], bienvenida)  # en una fila, los primeros
        redireccion = mensajes.teclado_redireccion("Dronwhite", False)["inline_keyboard"]
        self.assertEqual([fila[0].get("url") for fila in redireccion[:2]], bienvenida)
        self.assertEqual(redireccion[2][0]["callback_data"], mensajes.CALLBACK_DUDAS)

    def test_con_la_gratuita_escribeme_con_el_tema(self):
        filas = mensajes.teclado_tema("gemelas", "Dronwhite", True)["inline_keyboard"]
        borrador = parse_qs(urlparse(filas[0][0]["url"]).query)["text"][0]
        self.assertEqual(filas[1][0]["callback_data"], "faq:ganador")  # vuelve al paso 3
        self.assertEqual(borrador, "Hola, tengo una duda sobre las gemelas y los tríos")
        self.assertEqual(filas[-1][0]["callback_data"], mensajes.CALLBACK_MENU)


if __name__ == "__main__":
    unittest.main()
