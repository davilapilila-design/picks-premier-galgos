"""
Configuración, leída de variables de entorno.

Los valores reales NUNCA van en el repo: en la VM viven en
/etc/premier-captacion/<instancia>.env (root:root, permisos 600), que
systemd carga con EnvironmentFile= antes de arrancar el proceso. Ver
deploy/config.example.env y README.md.

CANAL_ID y PROPIETARIO_ID pueden quedar vacíos durante la puesta en
marcha: el propio bot ayuda a averiguarlos (comando /miid, y aviso del id
del canal cuando lo hacen administrador). Mientras CANAL_ID esté vacío el
bot NO acepta ninguna solicitud.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Optional
from zoneinfo import ZoneInfo


class ErrorConfig(Exception):
    pass


@dataclass(frozen=True)
class Config:
    bot_token: str
    # @usuario (sin la @) al que llevan los botones de la bienvenida: el
    # perfil del dueño (también en las pruebas de la fase 1). Solo en las
    # pruebas de la fase 3 será la cuenta secundaria.
    perfil: str
    db_path: str
    # Canal cuyas solicitudes gestiona el bot. None = puesta en marcha.
    canal_id: Optional[int] = None
    # Quién recibe avisos y resúmenes. None = solo se escriben en el log.
    propietario_id: Optional[int] = None
    zona_horaria: str = "Europe/Madrid"
    # Telegram deja escribir al solicitante durante 5 min; se deja margen.
    ventana_bienvenida_s: int = 290
    # Pausa mínima entre dos respuestas "escríbeme" a la misma persona
    # (si manda varios mensajes seguidos, se contesta una sola vez).
    pausa_redireccion_s: int = 60
    # Google Sheet al que se copia todo (fase 2). None = sin Sheet.
    sheet_id: Optional[str] = None

    @property
    def tz(self):
        return ZoneInfo(self.zona_horaria)


_RE_TOKEN = re.compile(r"^\d+:[A-Za-z0-9_-]{30,}$")
_RE_USUARIO = re.compile(r"^[A-Za-z][A-Za-z0-9_]{3,31}$")
_RE_SHEET = re.compile(r"^[A-Za-z0-9_-]{30,100}$")


def _entero_opcional(entorno, clave):
    valor = entorno.get(clave, "").strip()
    if not valor:
        return None
    try:
        return int(valor)
    except ValueError:
        raise ErrorConfig(f"{clave} debe ser un número (está como {valor!r})") from None


def cargar_config(entorno=None) -> Config:
    entorno = os.environ if entorno is None else entorno

    token = entorno.get("CAPTACION_BOT_TOKEN", "").strip()
    if not _RE_TOKEN.match(token):
        # Nunca se muestra el token en el error.
        raise ErrorConfig("CAPTACION_BOT_TOKEN vacío o con formato incorrecto")

    perfil = entorno.get("CAPTACION_PERFIL", "").strip().lstrip("@")
    if not _RE_USUARIO.match(perfil):
        raise ErrorConfig(f"CAPTACION_PERFIL no es un @usuario válido: {perfil!r}")

    db_path = entorno.get("CAPTACION_DB", "").strip()
    if not db_path:
        raise ErrorConfig("CAPTACION_DB vacío (ruta de la base de datos)")

    canal_id = _entero_opcional(entorno, "CAPTACION_CANAL_ID")
    if canal_id is not None and not str(canal_id).startswith("-100"):
        raise ErrorConfig(f"CAPTACION_CANAL_ID debe empezar por -100 (está como {canal_id})")

    zona = entorno.get("CAPTACION_ZONA_HORARIA", "").strip() or "Europe/Madrid"
    try:
        ZoneInfo(zona)
    except Exception:
        raise ErrorConfig(f"CAPTACION_ZONA_HORARIA desconocida: {zona!r}") from None

    sheet_id = entorno.get("CAPTACION_SHEET_ID", "").strip() or None
    if sheet_id is not None and not _RE_SHEET.match(sheet_id):
        raise ErrorConfig(f"CAPTACION_SHEET_ID no parece el id de un Google Sheet: {sheet_id!r}")

    return Config(
        bot_token=token,
        perfil=perfil,
        db_path=db_path,
        canal_id=canal_id,
        propietario_id=_entero_opcional(entorno, "CAPTACION_PROPIETARIO_ID"),
        zona_horaria=zona,
        sheet_id=sheet_id,
    )
