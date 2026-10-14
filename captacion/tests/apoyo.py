"""Utilidades compartidas por los tests: Telegram falso y configuración."""
from premier_captacion import db
from premier_captacion.config import Config

CANAL = -1001234567890
PROPIETARIO = 111
PERFIL = "PerfilPrueba"


def config(**cambios):
    valores = dict(
        bot_token="123456:" + "A" * 35,
        perfil=PERFIL,
        db_path=":memory:",
        canal_id=CANAL,
        propietario_id=PROPIETARIO,
    )
    valores.update(cambios)
    return Config(**valores)


def conexion():
    return db.abrir(":memory:")


class APIFalsa:
    """Imita BotAPI: apunta cada llamada y devuelve/lanza lo configurado."""

    def __init__(self):
        self.llamadas = []
        self.respuestas = {"getMe": {"id": 999, "username": "bot_prueba"}}
        # metodo -> lista de excepciones a lanzar en las próximas llamadas
        # (None = esa llamada va bien).
        self.fallos = {}

    def llamar(self, metodo, _timeout_red=None, **params):
        self.llamadas.append((metodo, params))
        pendientes = self.fallos.get(metodo)
        if pendientes:
            error = pendientes.pop(0)
            if error is not None:
                raise error
        return self.respuestas.get(metodo, True)

    def metodos(self):
        return [m for m, _ in self.llamadas]

    def envios_a(self, chat_id):
        return [p for m, p in self.llamadas if m == "sendMessage" and p["chat_id"] == chat_id]


def usuario(uid=500, nombre="Pepe", username="pepe"):
    u = {"id": uid, "is_bot": False, "first_name": nombre, "language_code": "es"}
    if username:
        u["username"] = username
    return u


def update_solicitud(update_id, uid=500, fecha=1_000_000, chat_id=CANAL, enlace_nombre="landing"):
    return {
        "update_id": update_id,
        "chat_join_request": {
            "chat": {"id": chat_id, "type": "channel", "title": "Canal de prueba"},
            "from": usuario(uid),
            "user_chat_id": uid,
            "date": fecha,
            "invite_link": {
                "invite_link": "https://t.me/+AbCd…",
                "name": enlace_nombre,
                "creates_join_request": True,
            },
        },
    }


def update_mensaje(update_id, uid=500, texto="hola"):
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id,
            "from": usuario(uid),
            "chat": {"id": uid, "type": "private"},
            "date": 1_000_000,
            "text": texto,
        },
    }
