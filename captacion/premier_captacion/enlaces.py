"""
Detección de enlaces de invitación de Telegram en los mensajes del dueño.

Cuenta como enlace de invitación cualquier forma de los de unirse a un
canal o grupo privado:
    https://t.me/+AbCdEf123456      t.me/+AbCd...   telegram.me/+...
    https://t.me/joinchat/AbCd...   (formato antiguo)
    tg://join?invite=AbCd...
Los enlaces públicos (t.me/nombre) NO cuentan: no son de invitación.

Solo se extrae el "hash" (lo que va detrás del + o de joinchat/). A qué
canal lleva cada uno lo comprueba después el lector preguntando a Telegram
(sin unirse a nada), y así se descartan los del canal principal.
"""
import re

_RE_WEB = re.compile(
    r"(?:https?://)?(?:www\.)?(?:t|telegram)\.(?:me|dog)/(?:\+|%2B|joinchat/)([A-Za-z0-9_-]{8,})",
    re.IGNORECASE,
)
_RE_TG = re.compile(r"tg://join\?invite=([A-Za-z0-9_-]{8,})", re.IGNORECASE)


def hashes_invitacion(textos):
    """Hashes de los enlaces de invitación en `textos`, sin repetir, en orden."""
    vistos = []
    for texto in textos:
        if not texto:
            continue
        for patron in (_RE_WEB, _RE_TG):
            for h in patron.findall(texto):
                if h not in vistos:
                    vistos.append(h)
    return vistos


def enlace(hash_enlace):
    return f"https://t.me/+{hash_enlace}"


def textos_de(mensaje):
    """Texto de un mensaje de Telethon más las URL escondidas tras un texto
    (p. ej. «pulsa aquí» con un enlace detrás)."""
    textos = [mensaje.message or ""]
    for entidad in mensaje.entities or []:
        url = getattr(entidad, "url", None)
        if url:
            textos.append(url)
    return textos
