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

Los textos que aquí se definen son los de partida: el dueño puede cambiarlos
desde el bot (/textos, ver textos.py), y entonces manda lo guardado en la
base de datos. Los botones de la bienvenida no se cambian desde el bot: de
la frase que dejan escrita depende saber qué eligió cada persona.
"""
import unicodedata
from urllib.parse import quote

# Bloques Unicode "Mathematical Sans-Serif Bold".
_MAYUS_A = 0x1D5D4
_MINUS_A = 0x1D5EE
_DIGITO_0 = 0x1D7EC


def negrita(texto):
    """Pasa A-Z, a-z y 0-9 a letras "negrita" Unicode; el resto queda igual.

    Las vocales con tilde y la ñ no tienen versión negrita en Unicode: se
    escriben como la letra en negrita seguida de la tilde suelta (Unicode
    «combinable»), que Telegram dibuja encima («𝗧𝗿𝗶́𝗼»).
    """
    salida = []
    for c in unicodedata.normalize("NFD", texto):
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
# A quien ya estaba en el canal o vuelve a entrar: sin la gratuita.
TIPO_BIENVENIDA_RECURRENTE = "bot_recurrente"

TIPOS_MENSAJE = {
    TIPO_BIENVENIDA_BOT: "Bienvenida del bot, versión B (dos botones), desde 2026-10",
    TIPO_MANUAL_BUENAS: "Bienvenida manual «Buenas! Bienvenido a PREMIER GALGOS», antes del bot",
    TIPO_MANUAL_BUENOS_DIAS: "Bienvenida manual «Buenos días y bienvenido a Premier Galgos», antes del bot",
    TIPO_BIENVENIDA_RECURRENTE: "Bienvenida del bot sin la gratuita (ya estaba en el canal o volvió a entrar)",
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

# A quien ya estaba en el canal o ya pasó por aquí y vuelve a pedir entrar:
# sin la gratuita y sin que se note que es otro mensaje (el dueño no quiere
# que busquen el truco de salir y entrar). Lleva las dudas y «escríbeme» con
# un texto ya escrito distinto («consulta» en vez de «duda»), para que el
# dueño sepa que es alguien que vuelve.
TEXTO_BIENVENIDA_RECURRENTE = (
    f"Buenas! Bienvenido a {negrita('PREMIER GALGOS')} 🐕\n"
    "\n"
    "Aquí tienes las dudas más frecuentes 📚 y, si necesitas algo concreto, escríbeme 💙"
)

# Respuesta cuando alguien escribe al bot en vez de al perfil del dueño.
# Se envía cada vez que escriben (con una pausa mínima entre respuestas,
# ver Config.pausa_redireccion_s, para no contestar a cada mensaje de una
# ráfaga).
# Hay dos: a quien aún no tiene la apuesta de regalo se le vuelve a hacer la
# pregunta de la bienvenida (con sus dos botones); a quien ya la tiene (el
# dueño le envió un enlace de venta), solo «escríbeme».
_LINEA_DUDAS = "Y si tienes dudas sobre casas, stakes o tipos de apuesta, aquí tienes las más frecuentes 📚"
TEXTO_REDIRECCION = (
    "Por aquí no puedo contestarte 🙈 Escríbeme a mi perfil y te atiendo yo personalmente.\n"
    "\n"
    "¿Ya has apostado en galgos o es tu primera vez? Pulsa tu respuesta 👇\n"
    "\n"
    f"{_LINEA_DUDAS}"
)
TEXTO_REDIRECCION_CON_GRATUITA = (
    "Por aquí no puedo contestarte 🙈 Escríbeme a mi perfil y te atiendo yo personalmente 👇\n"
    "\n"
    f"{_LINEA_DUDAS}"
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
ORIGEN_TIPO = {TIPO_BIENVENIDA_BOT: "bot", TIPO_MANUAL_BUENAS: "manual", TIPO_MANUAL_BUENOS_DIAS: "manual",
               TIPO_BIENVENIDA_RECURRENTE: "bot"}
TEXTOS_TIPO = {
    TIPO_BIENVENIDA_BOT: TEXTO_BIENVENIDA,
    TIPO_BIENVENIDA_RECURRENTE: TEXTO_BIENVENIDA_RECURRENTE,
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


def teclado_redireccion(usuario, con_gratuita, recurrente=False):
    """Respuesta a quien escribe al bot: los dos botones de la bienvenida (o
    «escríbeme», si ya tiene la gratuita o es recurrente) y el de las dudas
    frecuentes."""
    filas = [[boton_escribeme(usuario, recurrente=recurrente)]] if con_gratuita else _filas_botones(usuario)
    return {"inline_keyboard": filas + [[{"text": "📚 Dudas frecuentes", "callback_data": CALLBACK_DUDAS}]]}


def teclado_bienvenida_recurrente(usuario):
    return {"inline_keyboard": [[{"text": "📚 Dudas frecuentes", "callback_data": CALLBACK_DUDAS}],
                                [boton_escribeme(usuario, recurrente=True)]]}


def _filas_botones(usuario):
    return [[{"text": boton, "url": enlace_perfil(usuario, texto)}] for boton, texto in BOTONES]


def boton_escribeme(usuario, duda=None, recurrente=False):
    # Recurrentes: «consulta» en vez de «duda». El cliente ve el mismo botón;
    # el dueño, al leer el mensaje, sabe que es alguien que vuelve.
    palabra = "consulta" if recurrente else "duda"
    texto = f"Hola, tengo una {palabra} sobre {duda}" if duda else f"Hola, tengo una {palabra}"
    return {"text": "✉️ Escríbeme", "url": enlace_perfil(usuario, texto)}


# --- Dudas frecuentes (acordadas con el dueño el 2026-10-19) -----------------
# Se abren desde la respuesta del bot a quien le escribe («📚 Dudas
# frecuentes»). Cada tema: botón del menú, título, texto de partida (lo puede
# cambiar el dueño con /textos), de qué tema es la duda si escribe, y botones
# a otros temas. «otras_casas» es un submenú de «casas»: no sale en el menú.
# La redacción de los textos (y de las dos respuestas de arriba) la revisó el
# dueño el mismo día con su estilo: no retocarla sin él.
CALLBACK_DUDAS = "faq"          # desde la respuesta del bot: el menú, en un mensaje nuevo
CALLBACK_MENU = "faq:menu"      # «⬅️ Otras dudas»: vuelve al menú en el mismo mensaje

FAQ_TITULO = f"📚 {negrita('Dudas frecuentes')}\n\nElige tu tema y te lo explico en un momento 👇"

PIE_SIN_GRATUITA = (
    "👉 ¿Aún no tienes tu apuesta de regalo? Pulsa abajo y escríbeme: "
    f"{negrita('te regalo una apuesta de pago')} para que veas cómo trabajo 💙"
)
PIE_CON_GRATUITA = "¿Te queda alguna duda? Escríbeme y lo vemos 👇"

FAQ = {
    "casas": {
        "boton": "🏦 Casas de apuestas",
        "titulo": f"🏦 {negrita('Casas de apuestas')}",
        "duda": "las casas de apuestas",
        "enlaces": [("otras_casas", "🗺️ Otras casas y canódromos")],
        "texto": (
            f"Las que mejor van con nuestros picks: {negrita('Betway')}, {negrita('Betfair')} "
            f"y {negrita('Bet365')}.\n"
            "\n"
            f"También valen {negrita('William Hill')} y {negrita('Sportium')}. A veces tienen "
            "límites más altos, pero ponen las cuotas de otra manera:\n"
            f"· {negrita('William Hill')}: 30 min antes en carreras normales y horas antes en "
            "competiciones.\n"
            f"· {negrita('Sportium')}: horas antes en competiciones; en las normales depende, pero "
            "siempre con mucho margen. En Harlow y Star Pelaw no tiene cuotas tempranas.\n"
            "\n"
            f"{negrita('Mi consejo:')} ten cuenta en varias, o en todas. Así coges siempre la mejor "
            "cuota y, si en alguna tienes problemas para apostar, sigues con otra ✅"
        ),
    },
    "otras_casas": {
        "boton": "🗺️ Otras casas y canódromos",
        "titulo": f"🗺️ {negrita('Otras casas y canódromos')}",
        "duda": "las casas de apuestas",
        "enlaces": [("casas", "⬅️ Casas de apuestas")],
        "en_menu": False,
        "texto": (
            "Hay más casas con galgos, pero no tienen cuotas tempranas, o no siempre:\n"
            "\n"
            f"· {negrita('Versus')} y {negrita('Retabet')}: sin cuotas tempranas y solo algunos "
            "canódromos (Harlow, Star Pelaw, Doncaster…). No tienen Central Park, Nottingham, "
            "Hove ni muchos más.\n"
            f"· {negrita('Codere')}: tiene todos los canódromos, pero muchas veces sin cuotas "
            "tempranas. En Central Park, Nottingham, Hove y otros las está publicando una hora "
            "antes, aunque varía mucho.\n"
            f"· {negrita('DAZN Bet')}, {negrita('888')} y {negrita('Pastón')}: todos los "
            "canódromos, pero solo cuotas en directo, unos 5 min antes de la carrera."
        ),
    },
    "unidades": {
        "boton": "⚖️ Unidades",
        "titulo": f"⚖️ {negrita('Unidades')}",
        "duda": "las unidades",
        "texto": (
            f"Los stakes de los picks van en {negrita('unidades')}: «stake 2» son 2 unidades.\n"
            "\n"
            f"Lo más fácil: un {negrita('valor fijo')} por unidad, de "
            f"{negrita('al menos 10 €')}, y lo subes cuando crezca tu bank.\n"
            "\n"
            f"Ejemplo: con unidades de 10 €, un stake 2 son {negrita('20 €')}."
        ),
    },
    "bank": {
        "boton": "💰 Bank y stakes",
        "titulo": f"💰 {negrita('Bank y stakes')}",
        "duda": "el bank y los stakes",
        "texto": (
            f"El {negrita('bank')} es el dinero que apartas solo para apostar. Cada pick lleva su "
            f"stake en unidades; de media, unas {negrita('4-5')}.\n"
            "\n"
            "Apuesta solo dinero que no te haga falta ahora mismo. Si lo necesitas, o "
            "perderlo sería un problema grande para ti, no lo apuestes.\n"
            "\n"
            "+18 · Juega con responsabilidad."
        ),
    },
    "ganador": {
        "boton": "🏁 Apuesta a ganador",
        "titulo": f"🏁 {negrita('Apuesta a ganador')}",
        "duda": "las apuestas a ganador",
        "texto": (
            f"Nuestras apuestas son siempre {negrita('a ganador')}. {negrita('NUNCA')} pinches en "
            "«colocado», salvo que te digamos lo contrario.\n"
            "\n"
            f"Apuestas a que el galgo llega {negrita('primero')}. Si gana, cobras stake × cuota; "
            "si no, lo pierdes.\n"
            "\n"
            f"Ejemplo: 2 unidades a cuota {negrita('3,50')} → cobras {negrita('7')} (5 de beneficio) ✅\n"
            "\n"
            f"{negrita('Atento:')} cógela en cuanto te llegue el pick, la cuota puede bajar antes de "
            "la carrera."
        ),
    },
    "gemelas": {
        "boton": "🎯 Gemelas y tríos",
        "titulo": f"🎯 {negrita('Gemelas y tríos')}",
        "duda": "las gemelas y los tríos",
        "enlaces": [("otras_casas", "🗺️ Otras casas y canódromos")],
        "texto": (
            f"{negrita('Gemela')}: aciertas el 1º y el 2º de una carrera. {negrita('Trío')}: el "
            "1º, el 2º y el 3º. En las casas salen con esos mismos nombres.\n"
            "\n"
            "Si son en cualquier orden (reversible), la gemela son 2 combinaciones (p. ej. "
            "3-4 y 4-3) y el trío, 6. Cada una lleva su stake.\n"
            "\n"
            f"No tienen cuota fija: se pagan al {negrita('dividendo oficial')} que publica el "
            "canódromo después de la carrera. Por eso puedes hacerlas en las casas sin cuotas "
            "tempranas (👇 Otras casas y canódromos). Ojo: "
            f"{negrita('DAZN Bet')} y {negrita('Pastón')} no tienen gemelas ni tríos.\n"
            "\n"
            "Ejemplo real en Star Pelaw: gemela 3-4 y 4-3, stake 2 cada una = 4 unidades. "
            f"Llegó 4-3 con dividendo {negrita('7,42')} → {negrita('14,84 unidades')} "
            "(10,84 de beneficio) 📈"
        ),
    },
    "packs": {
        "boton": "📦 Packs: nuestra garantía",
        "titulo": f"📦 {negrita('Packs: nuestra garantía')}",
        "duda": "los packs",
        "texto": (
            f"Casi todo lo que vendemos son {negrita('packs')} de dos o más galgos.\n"
            "\n"
            "Si un pack sale en pérdidas, según las unidades perdidas "
            f"{negrita('te damos el siguiente gratis o con descuento')}.\n"
            "\n"
            f"Y si fallan todos los galgos del pack, el siguiente es {negrita('siempre gratis')} 💙"
        ),
    },
}
FAQ_MENU = [t for t, datos in FAQ.items() if datos.get("en_menu", True)]


def teclado_menu_faq():
    return {"inline_keyboard": [[{"text": FAQ[t]["boton"], "callback_data": f"faq:{t}"}] for t in FAQ_MENU]}


def mensaje_tema(tema, texto, pie):
    """Mensaje completo de un tema: título, el texto (el de partida o el que
    haya puesto el dueño) y el final («escríbeme»)."""
    return f"{FAQ[tema]['titulo']}\n\n{texto}\n\n{pie}"


def teclado_tema(tema, usuario, con_gratuita, recurrente=False):
    filas = [[{"text": texto, "callback_data": f"faq:{destino}"}] for destino, texto in FAQ[tema].get("enlaces", ())]
    if con_gratuita:
        filas.append([boton_escribeme(usuario, FAQ[tema]["duda"], recurrente=recurrente)])
    else:
        filas += _filas_botones(usuario)
    filas.append([{"text": "⬅️ Otras dudas", "callback_data": CALLBACK_MENU}])
    return {"inline_keyboard": filas}


# --- Textos que el dueño puede cambiar desde el bot (/textos) ----------------
# clave -> (nombre en el menú de /textos, texto de partida). El orden es el
# del menú. Ver textos.py.
TEXTOS_EDITABLES = {
    "bienvenida": ("👋 Bienvenida", TEXTO_BIENVENIDA),
    "bienvenida_recurrente": ("🔁 Bienvenida sin gratuita (ya estaba o vuelve)", TEXTO_BIENVENIDA_RECURRENTE),
    "redireccion": ("💬 Si escriben al bot (sin la gratuita)", TEXTO_REDIRECCION),
    "redireccion_gratuita": ("💬 Si escriben al bot (con la gratuita)", TEXTO_REDIRECCION_CON_GRATUITA),
    "faq_menu": ("📚 Menú de dudas", FAQ_TITULO),
    **{f"faq:{t}": (f"Duda · {FAQ[t]['boton']}", FAQ[t]["texto"])
       for t in ["casas", "otras_casas"] + [t for t in FAQ_MENU if t != "casas"]},
    "faq_pie": ("👉 Final de las dudas (sin la gratuita)", PIE_SIN_GRATUITA),
    "faq_pie_gratuita": ("👉 Final de las dudas (con la gratuita)", PIE_CON_GRATUITA),
}
