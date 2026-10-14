import unittest
from urllib.parse import parse_qs, urlparse

from premier_captacion import mensajes

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

    def test_respeta_espacios_tildes_y_emojis(self):
        self.assertEqual(mensajes.negrita("é ñ 🐕."), "é ñ 🐕.")


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
        self.assertEqual(borradores[0], "¡Hola! Vengo de PREMIER GALGOS 🐕 Ya he apostado en galgos")
        self.assertEqual(borradores[1], "¡Hola! Vengo de PREMIER GALGOS 🐕 Es mi primera vez")

    def test_cada_boton_deja_una_frase_distinta(self):
        # La fase 3 distingue la respuesta por estas frases.
        a, b = (texto for _, texto in mensajes.BOTONES)
        self.assertIn(mensajes.FRASE_YA_APOSTADO, a)
        self.assertNotIn(mensajes.FRASE_YA_APOSTADO, b)
        self.assertIn(mensajes.FRASE_PRIMERA_VEZ, b)
        self.assertNotIn(mensajes.FRASE_PRIMERA_VEZ, a)


if __name__ == "__main__":
    unittest.main()
