import unittest

from premier_captacion.config import ErrorConfig, cargar_config

TOKEN = "123456789:AAH" + "x" * 32


def entorno(**cambios):
    valores = {
        "CAPTACION_BOT_TOKEN": TOKEN,
        "CAPTACION_PERFIL": "@Dronwhite",
        "CAPTACION_DB": "/var/lib/premier-captacion/prueba.db",
        "CAPTACION_CANAL_ID": "-1001234567890",
        "CAPTACION_PROPIETARIO_ID": "",
    }
    valores.update(cambios)
    return valores


class TestConfig(unittest.TestCase):
    def test_valores_correctos(self):
        cfg = cargar_config(entorno())
        self.assertEqual(cfg.perfil, "Dronwhite")  # sin la @
        self.assertEqual(cfg.canal_id, -1001234567890)
        self.assertIsNone(cfg.propietario_id)
        self.assertEqual(cfg.zona_horaria, "Europe/Madrid")

    def test_canal_vacio_es_puesta_en_marcha(self):
        self.assertIsNone(cargar_config(entorno(CAPTACION_CANAL_ID="")).canal_id)

    def test_token_incorrecto_no_aparece_en_el_error(self):
        malo = TOKEN[:-25]
        with self.assertRaises(ErrorConfig) as ctx:
            cargar_config(entorno(CAPTACION_BOT_TOKEN=malo))
        self.assertNotIn(malo, str(ctx.exception))

    def test_errores(self):
        for cambio in (
            {"CAPTACION_PERFIL": "a b"},
            {"CAPTACION_DB": ""},
            {"CAPTACION_CANAL_ID": "12345"},
            {"CAPTACION_PROPIETARIO_ID": "pepe"},
            {"CAPTACION_ZONA_HORARIA": "Marte/Olympus"},
        ):
            with self.subTest(cambio), self.assertRaises(ErrorConfig):
                cargar_config(entorno(**cambio))


if __name__ == "__main__":
    unittest.main()
