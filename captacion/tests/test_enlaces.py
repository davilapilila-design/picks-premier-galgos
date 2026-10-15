import unittest

from premier_captacion.enlaces import enlace, hashes_invitacion


class TestEnlaces(unittest.TestCase):
    def test_formatos(self):
        textos = [
            "Aquí tienes: https://t.me/+Ejemplo1Venta0001 🔥",
            "o este t.me/+Ejemplo2Venta0002",
            "antiguo https://t.me/joinchat/AAAAAEjemploAntiguo-gg",
            "telegram.me/+Ejemplo_3Venta003 y tg://join?invite=Ejemplo4Venta0004",
            "codificado https://t.me/%2BEjemplo-5Venta005",
        ]
        self.assertEqual(hashes_invitacion(textos), [
            "Ejemplo1Venta0001", "Ejemplo2Venta0002", "AAAAAEjemploAntiguo-gg",
            "Ejemplo_3Venta003", "Ejemplo4Venta0004", "Ejemplo-5Venta005",
        ])

    def test_no_cuentan(self):
        textos = ["mi perfil t.me/Dronwhite", "https://t.me/canalpublico/123", "sin enlaces", "", None,
                  "t.me/+corto"]
        self.assertEqual(hashes_invitacion(textos), [])

    def test_sin_repetir(self):
        self.assertEqual(hashes_invitacion(["t.me/+Ejemplo1Venta0001", "https://t.me/+Ejemplo1Venta0001"]),
                         ["Ejemplo1Venta0001"])

    def test_enlace(self):
        self.assertEqual(enlace("Ejemplo1Venta0001"), "https://t.me/+Ejemplo1Venta0001")


if __name__ == "__main__":
    unittest.main()
