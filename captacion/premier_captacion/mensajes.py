"""
Textos que envía el bot y botones que los acompañan.

Las "negritas" NO son formato de Telegram: son letras Unicode
(Mathematical Sans-Serif Bold), igual que en el mensaje que el dueño
enviaba a mano. Se generan con `negrita()` en vez de pegarlas a mano para
que no se cuele ninguna letra equivocada; tests/test_mensajes.py compara
el resultado con el texto original copiado tal cual.

Cada texto de bienvenida tiene un id de "tipo de mensaje" que se guarda
en la base de datos con cada envío, para poder comparar en las
estadísticas qué versión funciona mejor. Si se cambia el texto, se crea
un tipo NUEVO (no se reutiliza el id), para no mezclar estadísticas.
"""
from urllib.parse import quote

# Bloques Unicode "Mathematical Sans-Serif Bold".
_MAYUS_A = 0x1D5D4
_MINUS_A = 0x1D5EE
_DIGITO_0 = 0x1D7EC


def negrita(texto):
    """Pasa A-Z, a-z y 0-9 a letras "negrita" Unicode; el resto queda igual.

    Las vocales con tilde y la ñ no tienen versión negrita en Unicode, así
    que se quedan como están (en los textos actuales no aparece ninguna).
    """
    salida = []
    for c in texto:
        if "A" <= c <= "Z":
            salida.append(chr(_MAYUS_A + ord(c) - ord("A")))
        elif "a" <= c <= "z":
            salida.append(chr(_MINUS_A + ord(c) - ord("a")))
        elif "0" <= c <= "9":
            salida.append(chr(_DIGITO_0 + ord(c) - ord("0")))
        else:
            salida.append(c)
    return "".join(salida)


# --- Tipos de mensaje de bienvenida -----------------------------------------
# Los dos manuales (los que el dueño enviaba desde su cuenta) se registran
# en la fase 4, al leer el histórico de sus chats (historico.py).
TIPO_BIENVENIDA_BOT = "bot_b_v1"
TIPO_MANUAL_BUENAS = "manual_buenas"
TIPO_MANUAL_BUENOS_DIAS = "manual_buenos_dias"

TIPOS_MENSAJE = {
    TIPO_BIENVENIDA_BOT: "Bienvenida del bot, versión B (dos botones), desde 2026-10",
    TIPO_MANUAL_BUENAS: "Bienvenida manual «Buenas! Bienvenido a PREMIER GALGOS», antes del bot",
    TIPO_MANUAL_BUENOS_DIAS: "Bienvenida manual «Buenos días y bienvenido a Premier Galgos», antes del bot",
}


# --- Textos ---------------------------------------------------------------
TEXTO_BIENVENIDA = (
    f"Buenas! Bienvenido a {negrita('PREMIER GALGOS')} 🐕\n"
    "\n"
    f"Para empezar {negrita('te regalo una apuesta de pago')} para que veas "
    f"cómo trabajo. Aquí todo va con {negrita('TRANSPARENCIA')}.\n"
    "\n"
    "Para recibirla, dime: ¿ya has apostado en galgos o es tu primera vez? "
    "Pulsa tu respuesta y me escribes directamente 💙"
)

# Respuesta cuando alguien escribe al bot en vez de al perfil del dueño.
# Se envía cada vez que escriben (con una pausa mínima entre respuestas,
# ver Config.pausa_redireccion_s, para no contestar a cada mensaje de una
# ráfaga).
TEXTO_REDIRECCION = (
    "Por aquí no puedo contestarte 🙈 Escríbeme a mi perfil y te atiendo yo. "
    "¿Ya has apostado en galgos o es tu primera vez? 👇"
)

# Botones: (texto del botón, texto que queda ya escrito en el chat del
# dueño al pulsarlo). Telegram NO avisa al bot cuando se pulsa un botón de
# enlace, así que la única forma de saber qué eligió cada persona es el
# texto que acaba enviando al dueño (fase 3): por eso cada botón deja una
# frase distinta y reconocible.
FRASE_YA_APOSTADO = "Ya he apostado en galgos antes"
FRASE_PRIMERA_VEZ = "Es mi primera vez con los galgos"
_SALUDO = "¡Hola! Acabo de entrar en el canal."

BOTONES = (
    ("🏁 Ya he apostado", f"{_SALUDO} {FRASE_YA_APOSTADO} 🐕"),
    ("🆕 Es mi primera vez", f"{_SALUDO} {FRASE_PRIMERA_VEZ} 🐕"),
)


# Textos que el dueño enviaba a mano antes del bot, tal y como los pasó
# (2026-10-14). Solo para la pestaña «Tipos de mensaje»; nadie los envía.
TEXTO_MANUAL_BUENAS = (
    f"Buenas! Bienvenido a {negrita('PREMIER GALGOS')} 🐕\n"
    "\n"
    f"Para empezar {negrita('te regalo una apuesta de pago')} para que veas "
    f"cómo trabajo. Aquí todo va con {negrita('TRANSPARENCIA')}.\n"
    "\n"
    "Cualquier duda, escríbeme por aquí sin problema 💙\n"
    "\n"
    "¿Ya has apostado en galgos o es tu primera vez?"
)
TEXTO_MANUAL_BUENOS_DIAS = (
    "Buenos dias y bienvenido a Premier Galgos! 🐾\n"
    "\n"
    "Si tienes cualquier duda sobre el canal, el funcionamiento del servicio, las apuestas "
    "de galgos o la gestión de los stakes, puedes escribirnos por aquí sin ningún problema. "
    "Estaremos encantados de ayudarte en todo lo que necesites.\n"
    "\n"
    "Y para empezar en la comunidad te voy a dar una apuesta de pago de manera gratuita.\n"
    "\n"
    "Para darte el acceso, responde a este mensaje:\n"
    "Tienes experiencia en las carreras de galgos o es la primera vez?"
)

# Para la pestaña «Tipos de mensaje» del Sheet: de dónde sale cada tipo y
# su texto completo.
ORIGEN_TIPO = {TIPO_BIENVENIDA_BOT: "bot", TIPO_MANUAL_BUENAS: "manual", TIPO_MANUAL_BUENOS_DIAS: "manual"}
TEXTOS_TIPO = {
    TIPO_BIENVENIDA_BOT: TEXTO_BIENVENIDA,
    TIPO_MANUAL_BUENAS: TEXTO_MANUAL_BUENAS,
    TIPO_MANUAL_BUENOS_DIAS: TEXTO_MANUAL_BUENOS_DIAS,
}


def enlace_perfil(usuario, texto):
    """Enlace que abre el chat privado con `usuario` y deja `texto` escrito.

    Formato oficial de Telegram `t.me/<usuario>?text=<borrador>`: el texto
    queda en la caja de escribir, la persona decide si lo envía.
    """
    return f"https://t.me/{usuario}?text={quote(texto, safe='')}"


def teclado_respuesta(usuario):
    """Teclado con los dos botones, uno por fila."""
    return {
        "inline_keyboard": [
            [{"text": boton, "url": enlace_perfil(usuario, texto)}]
            for boton, texto in BOTONES
        ]
    }
