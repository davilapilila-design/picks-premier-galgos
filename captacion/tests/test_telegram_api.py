"""Prueba BotAPI contra un servidor HTTP local que imita a Telegram."""
import json
import socket
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

from premier_captacion.telegram_api import BotAPI, ErrorRed, ErrorTelegram

TOKEN = "123456:" + "T" * 35


class _Manejador(BaseHTTPRequestHandler):
    def do_POST(self):
        cuerpo = self.rfile.read(int(self.headers["Content-Length"]))
        self.server.peticiones.append((self.path, json.loads(cuerpo)))
        estado, respuesta = self.server.respuestas.pop(0)
        datos = respuesta if isinstance(respuesta, bytes) else json.dumps(respuesta).encode()
        self.send_response(estado)
        self.send_header("Content-Length", str(len(datos)))
        self.end_headers()
        self.wfile.write(datos)

    def log_message(self, *args):
        pass


class TestBotAPI(unittest.TestCase):
    def setUp(self):
        self.servidor = ThreadingHTTPServer(("127.0.0.1", 0), _Manejador)
        self.servidor.peticiones = []
        self.servidor.respuestas = []
        hilo = threading.Thread(target=self.servidor.serve_forever, daemon=True)
        hilo.start()
        self.addCleanup(self.servidor.server_close)
        self.addCleanup(self.servidor.shutdown)
        base = f"http://127.0.0.1:{self.servidor.server_address[1]}"
        self.api = BotAPI(TOKEN, base_url=base, timeout_red=5)

    def responder(self, *respuestas):
        self.servidor.respuestas.extend(respuestas)

    def test_peticion_correcta(self):
        self.responder((200, {"ok": True, "result": {"message_id": 5}}))
        resultado = self.api.llamar("sendMessage", chat_id=1, text="hola", reply_markup=None)
        self.assertEqual(resultado, {"message_id": 5})
        ruta, cuerpo = self.servidor.peticiones[0]
        self.assertEqual(ruta, f"/bot{TOKEN}/sendMessage")
        self.assertEqual(cuerpo, {"chat_id": 1, "text": "hola"})  # los None no se envían

    def test_error_de_telegram(self):
        self.responder((403, {"ok": False, "error_code": 403, "description": "Forbidden: bot was blocked by the user"}))
        with self.assertRaises(ErrorTelegram) as ctx:
            self.api.llamar("sendMessage", chat_id=1, text="x")
        self.assertEqual(ctx.exception.codigo, 403)
        self.assertEqual(ctx.exception.descripcion, "Forbidden: bot was blocked by the user")

    def test_espera_y_reintenta_si_hay_limite_de_velocidad(self):
        self.responder(
            (429, {"ok": False, "error_code": 429, "description": "Too Many Requests",
                   "parameters": {"retry_after": 3}}),
            (200, {"ok": True, "result": True}),
        )
        with mock.patch("premier_captacion.telegram_api.time.sleep") as dormir:
            self.assertTrue(self.api.llamar("approveChatJoinRequest", chat_id=1, user_id=2))
        dormir.assert_called_once_with(4)
        self.assertEqual(len(self.servidor.peticiones), 2)

    def test_fallos_del_servidor_cuentan_como_red(self):
        self.responder((502, b"<html>Bad Gateway</html>"),
                       (500, {"ok": False, "error_code": 500, "description": "Internal Server Error"}))
        for _ in range(2):
            with self.assertRaises(ErrorRed):
                self.api.llamar("getUpdates")

    def test_sin_conexion_y_sin_token_en_el_error(self):
        libre = socket.socket()
        libre.bind(("127.0.0.1", 0))
        puerto = libre.getsockname()[1]
        libre.close()  # puerto cerrado: conexión rechazada
        api = BotAPI(TOKEN, base_url=f"http://127.0.0.1:{puerto}", timeout_red=2)
        with self.assertRaises(ErrorRed) as ctx:
            api.llamar("getMe")
        self.assertNotIn(TOKEN, str(ctx.exception))

    def test_el_token_nunca_sale_en_la_descripcion(self):
        self.responder((400, {"ok": False, "error_code": 400, "description": f"raro {TOKEN}"}))
        with self.assertRaises(ErrorTelegram) as ctx:
            self.api.llamar("getMe")
        self.assertNotIn(TOKEN, str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
