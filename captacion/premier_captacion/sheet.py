"""
Copia de la base de datos local al Google Sheet (fase 2 de captacion/PLAN.md).

La base de datos de la VM sigue siendo la que manda (el bot decide con
ella); el Sheet es una copia para consultar y sacar estadísticas. Se
actualiza cada 10 minutos (captacion-sheet@<instancia>.timer). Lo que haya
en estas pestañas se sobrescribe: para notas propias, crear otras pestañas.

Pestañas:
- Usuarios: una fila por persona (user_id de Telegram), con su estado.
- Eventos: todo lo que pasa, en orden. Solo se añaden filas nuevas.
- Resumen diario: una fila por día, con fórmulas sobre Eventos (se puede
  pulsar cualquier número y ver de dónde sale).
- Tipos de mensaje: los textos de bienvenida y su código.

Seguridad: los datos (nombres, @usuario...) se escriben en modo RAW, sin
interpretar, para que un nombre que empiece por "=" no se convierta en
fórmula. Solo el Resumen diario, que es todo nuestro, va como fórmulas.

Fechas: se escriben como número de serie de Sheets (días desde 1899-12-30,
en hora de España) con formato de fecha, para que fórmulas y tablas
dinámicas las traten como fechas de verdad.

Las fórmulas usan nombres en inglés y ";" como separador, que es lo que
espera un Sheet con configuración regional española (igual que las
fórmulas de src/Setup.gs del sistema de picks). Por eso, al empezar, se
fija la configuración regional del libro en es_ES y la zona horaria en
Europe/Madrid.

Uso manual (en la VM; normalmente lo lanza el timer):
    systemctl start captacion-sheet@prueba
"""
import json
import logging
import os
import socket
import sys
from datetime import datetime

from . import db, mensajes, textos
from .config import ErrorConfig, cargar_config

log = logging.getLogger("captacion.sheet")

LOCALE = "es_ES"
ZONA_LIBRO = "Europe/Madrid"

TAB_USUARIOS = "Usuarios"
TAB_EVENTOS = "Eventos"
TAB_RESUMEN = "Resumen diario"
TAB_TIPOS = "Tipos de mensaje"
# Nombre de la primera pestaña de un Sheet recién creado (según idioma).
NOMBRES_PESTANA_INICIAL = ("Sheet1", "Hoja 1", "Hoja1")

CABECERA_USUARIOS = [
    "User ID", "Nombre", "Usuario", "Idioma", "Primera solicitud", "Última solicitud",
    "Solicitudes", "Enlace de entrada", "Tipo de bienvenida", "Bienvenida enviada",
    "Mensajes al bot", "Bloqueó el bot",
    # Fase 3 (lector de la cuenta del dueño) y fase 4 (histórico):
    "Te escribió (primera vez)", "Último mensaje", "Botón", "Primer enlace de venta",
    "Canal de venta", "Último enlace de venta", "Carpeta",
]
BOTONES = {"ya_apostado": "Ya he apostado", "primera_vez": "Primera vez", "otro": "Otro texto"}
CABECERA_EVENTOS = ["Id", "Fecha y hora", "Día", "User ID", "Nombre", "Evento", "Tipo de mensaje", "Detalle"]
CABECERA_TIPOS = ["Código", "Descripción", "Origen", "Texto"]

# Cómo se ve cada evento en el Sheet. Los no listados salen con su código.
ETIQUETAS_EVENTO = {
    "solicitud": "Solicitud",
    "bienvenida_enviada": "Bienvenida enviada",
    "bienvenida_fallida": "Bienvenida no enviada",
    "ya_recibida": "Ya estaba o volvió (bienvenida sin gratuita)",
    "aceptada": "Aceptada",
    "aceptacion_fallida": "No aceptada",
    "mensaje_al_bot": "Escribió al bot",
    "redireccion_enviada": "El bot le respondió",
    "redireccion_fallida": "El bot no pudo responderle",
    "solicitud_otro_chat": "Solicitud en otro chat",
    "bloqueo_bot": "Bloqueó el bot",
    "desbloqueo_bot": "Desbloqueó el bot",
    "permisos_bot": "Cambio de permisos del bot",
    "te_escribe": "Te escribió",
    "enlace_venta": "Enlace de venta enviado",
    "enlace_principal": "Enlace del canal principal enviado",
    "carpeta": "Carpeta",
    "carpeta_borrada": "Carpeta borrada",
    "bienvenida_manual": "Bienvenida manual",
    "bienvenida_prueba": "Marcado del embudo (prueba)",
    "pausa": "Bot en pausa (/pausar)",
    "reanudacion": "Bot reanudado (/reanudar)",
    "solicitud_en_pausa": "Solicitud sin atender (bot en pausa)",
    "faq": "Miró las dudas frecuentes",
    "texto_cambiado": "Texto cambiado desde el bot (/textos)",
    "aviso_gratuita_repetida": "Pidió la gratuita y ya la tuvo o ya estaba",
    "solicitud_simulada": "Solicitud en simulación (el bot no hizo nada)",
}

MOTIVOS = {
    "fuera_de_plazo": "llevaba más de 5 min esperando",
    "solicitud_ya_gestionada": "ya gestionada a mano o retirada",
}

# Resumen diario: (cabecera, evento contado, cómo se cuenta). "filas" cuenta
# filas de Eventos; "personas" cuenta personas distintas (User ID).
COLUMNAS_RESUMEN = [
    ("Solicitudes", "solicitud", "filas"),
    ("Personas que solicitaron", "solicitud", "personas"),
    ("Bienvenidas enviadas", "bienvenida_enviada", "filas"),
    ("Bienvenidas no enviadas", "bienvenida_fallida", "filas"),
    ("Ya estaban o volvieron (sin gratuita)", "ya_recibida", "filas"),
    ("Aceptadas", "aceptada", "filas"),
    ("Personas que escribieron al bot", "mensaje_al_bot", "personas"),
    ("Personas que te escribieron", "te_escribe", "personas"),
    ("Enlaces de venta enviados", "enlace_venta", "filas"),
    ("Bienvenidas manuales (histórico)", "bienvenida_manual", "filas"),
]
FILAS_CABECERA_RESUMEN = [
    ["Día"] + [cabecera for cabecera, _, _ in COLUMNAS_RESUMEN],
    ["Evento contado"] + [ETIQUETAS_EVENTO[evento] for _, evento, _ in COLUMNAS_RESUMEN],
]

FORMATO_FECHA_HORA = {"numberFormat": {"type": "DATE_TIME", "pattern": "dd/mm/yyyy hh:mm"}}
FORMATO_DIA = {"numberFormat": {"type": "DATE", "pattern": "dd/mm/yyyy"}}
FORMATO_DIA_SEMANA = {"numberFormat": {"type": "DATE", "pattern": "ddd dd/mm/yyyy"}}
FORMATO_CABECERA = {"textFormat": {"bold": True}}
FORMATO_FILA_EVENTO = {"textFormat": {"italic": True, "foregroundColor": {"red": 0.4, "green": 0.4, "blue": 0.4}}}

_EPOCA_SHEETS = datetime(1899, 12, 30)


# --- Conversión de datos --------------------------------------------------------

def serie_fecha_hora(ts, tz):
    """Fecha y hora local (tz) como número de serie de Sheets."""
    local = datetime.fromtimestamp(ts, tz).replace(tzinfo=None)
    return round((local - _EPOCA_SHEETS).total_seconds() / 86400, 6)


def serie_dia(ts, tz):
    """Día local (tz) como número de serie de Sheets (entero)."""
    return (datetime.fromtimestamp(ts, tz).date() - _EPOCA_SHEETS.date()).days


def _o_vacio(ts, tz):
    return "" if ts is None else serie_fecha_hora(ts, tz)


def nombre_visible(nombre, username):
    if nombre and username:
        return f"{nombre} (@{username})"
    if username:
        return f"@{username}"
    return nombre or ""


ESTADOS_BOT = {"administrator": "administrador", "member": "miembro", "left": "fuera", "kicked": "expulsado"}


def texto_detalle(detalle):
    partes = []
    if "chat_titulo" in detalle or "chat_id" in detalle:
        partes.append(f"chat: {detalle.get('chat_titulo') or 'sin título'} ({detalle.get('chat_id')})")
    for clave, valor in detalle.items():
        if clave in ("tipo_mensaje", "chat_titulo", "chat_id"):
            continue
        if clave == "estado":
            partes.append(f"estado del bot: {ESTADOS_BOT.get(valor, valor)}")
        elif clave == "enlace":
            partes.append(f"enlace: {valor}")
        elif clave == "retraso_s":
            partes.append(f"espera: {valor} s")
        elif clave == "motivo":
            partes.append(f"motivo: {MOTIVOS.get(valor, valor)}")
        elif clave == "ya_estaba":
            if valor:
                partes.append("ya estaba dentro")
        elif clave == "puede_invitar":
            partes.append(f"puede aceptar solicitudes: {'sí' if valor else 'no'}")
        elif clave == "canal":
            partes.append(f"canal: {valor}")
        elif clave == "carpeta":
            accion = detalle.get("accion")
            partes.append({"entra": "entra en", "sale": "sale de"}.get(accion, "carpeta") + f" {valor}")
        elif clave == "accion":
            continue
        elif clave == "boton":
            partes.append(f"botón: {BOTONES.get(valor, valor)}")
        elif clave == "primera_vez":
            if valor:
                partes.append("primera vez que escribe")
        elif clave == "historico":
            if valor:
                partes.append("del histórico")
        elif clave == "tema":
            nombre = mensajes.FAQ[valor]["boton"] if valor in mensajes.FAQ else ("menú" if valor == "menu" else valor)
            partes.append(f"tema: {nombre}")
        elif clave == "clave":
            partes.append(f"texto: {mensajes.TEXTOS_EDITABLES.get(valor, (valor,))[0]}")
        else:
            partes.append(f"{clave}: {valor}")
    return "; ".join(partes)


def filas_usuarios(con, tz):
    filas = []
    for u in con.execute(
        """
        SELECT u.*,
            (SELECT COUNT(*) FROM eventos e
              WHERE e.user_id = u.user_id AND e.tipo = 'mensaje_al_bot') AS mensajes_bot,
            (SELECT e.tipo FROM eventos e
              WHERE e.user_id = u.user_id AND e.tipo IN ('bloqueo_bot', 'desbloqueo_bot')
              ORDER BY e.id DESC LIMIT 1) AS ultimo_bloqueo
        FROM usuarios u
        ORDER BY u.primera_solicitud_ts IS NULL, u.primera_solicitud_ts DESC, u.user_id
        """
    ):
        filas.append([
            u["user_id"],
            u["nombre"] or "",
            f"@{u['username']}" if u["username"] else "",
            u["idioma"] or "",
            _o_vacio(u["primera_solicitud_ts"], tz),
            _o_vacio(u["ultima_solicitud_ts"], tz),
            u["num_solicitudes"],
            u["enlace_entrada"] or "",
            u["bienvenida_tipo"] or "",
            _o_vacio(u["bienvenida_ts"], tz),
            u["mensajes_bot"],
            "sí" if u["ultimo_bloqueo"] == "bloqueo_bot" else "",
            _o_vacio(u["primer_mensaje_ts"], tz),
            _o_vacio(u["ultimo_mensaje_ts"], tz),
            BOTONES.get(u["boton"], u["boton"] or ""),
            _o_vacio(u["enlace_venta_ts"], tz),
            u["canal_venta"] or "",
            u["enlace_venta"] or "",
            u["carpeta"] or "",
        ])
    return filas


def filas_eventos(con, tz, desde_id=0):
    filas = []
    for e in con.execute(
        """
        SELECT e.id, e.ts, e.user_id, e.tipo, e.detalle, u.nombre, u.username
        FROM eventos e LEFT JOIN usuarios u ON u.user_id = e.user_id
        WHERE e.id > ? ORDER BY e.id
        """,
        (int(desde_id),),
    ):
        detalle = json.loads(e["detalle"]) if e["detalle"] else {}
        filas.append([
            e["id"],
            serie_fecha_hora(e["ts"], tz),
            serie_dia(e["ts"], tz),
            e["user_id"] if e["user_id"] is not None else "",
            nombre_visible(e["nombre"], e["username"]),
            ETIQUETAS_EVENTO.get(e["tipo"], e["tipo"]),
            detalle.get("tipo_mensaje", ""),
            texto_detalle(detalle),
        ])
    return filas


def _letra_columna(numero):
    letras = ""
    while numero:
        numero, resto = divmod(numero - 1, 26)
        letras = chr(ord("A") + resto) + letras
    return letras


def filas_resumen(con, tz):
    """Filas del Resumen diario (desde la fila 3): día + fórmulas, más reciente arriba."""
    dias = sorted({serie_dia(f["ts"], tz) for f in con.execute("SELECT ts FROM eventos")}, reverse=True)
    filas = []
    for i, dia in enumerate(dias):
        r = 3 + i
        fila = [dia]
        for j, (_, _, modo) in enumerate(COLUMNAS_RESUMEN):
            col = _letra_columna(2 + j)
            if modo == "filas":
                fila.append(f"=COUNTIFS(Eventos!$C:$C;$A{r};Eventos!$F:$F;{col}$2)")
            else:
                fila.append(f"=COUNTUNIQUEIFS(Eventos!$D:$D;Eventos!$C:$C;$A{r};Eventos!$F:$F;{col}$2)")
        filas.append(fila)
    return filas


def filas_tipos(con, tz):
    """Los tipos de mensaje de partida y las versiones de la bienvenida que
    el dueño haya creado desde el bot (/textos)."""
    filas = [
        [codigo, descripcion, mensajes.ORIGEN_TIPO.get(codigo, ""), mensajes.TEXTOS_TIPO.get(codigo, "")]
        for codigo, descripcion in mensajes.TIPOS_MENSAJE.items()
    ]
    for tipo, texto, _ in textos.versiones_bienvenida(con):
        filas.append([tipo, textos.descripcion_tipo(con, tipo, tz), "bot", texto])
    return filas


# --- Sincronización -----------------------------------------------------------

def sincronizar(con, tz, libro):
    """Copia la base de datos al libro. Devuelve un resumen de lo hecho.

    `libro` tiene preparar() y pestana(nombre, filas_cabecera); cada pestaña
    tiene reemplazar(filas, desde_fila, formulas), ids(), anadir(filas) y
    formatear(lista de (rango, formato)). Ver LibroGoogle/PestanaGoogle.
    """
    libro.preparar()

    usuarios = filas_usuarios(con, tz)
    p = libro.pestana(TAB_USUARIOS, [CABECERA_USUARIOS])
    p.reemplazar(usuarios, desde_fila=2)
    p.formatear([("E2:F", FORMATO_FECHA_HORA), ("J2:J", FORMATO_FECHA_HORA), ("M2:N", FORMATO_FECHA_HORA),
                 ("P2:P", FORMATO_FECHA_HORA)])

    p = libro.pestana(TAB_EVENTOS, [CABECERA_EVENTOS])
    nuevos = filas_eventos(con, tz, desde_id=max(p.ids(), default=0))
    if nuevos:
        p.anadir(nuevos)
    p.formatear([("B2:B", FORMATO_FECHA_HORA), ("C2:C", FORMATO_DIA)])

    dias = filas_resumen(con, tz)
    p = libro.pestana(TAB_RESUMEN, FILAS_CABECERA_RESUMEN)
    p.reemplazar(dias, desde_fila=3, formulas=True)
    p.formatear([(f"A2:{_letra_columna(len(FILAS_CABECERA_RESUMEN[0]))}2", FORMATO_FILA_EVENTO), ("A3:A", FORMATO_DIA_SEMANA)])

    p = libro.pestana(TAB_TIPOS, [CABECERA_TIPOS])
    p.reemplazar(filas_tipos(con, tz), desde_fila=2)

    return {"usuarios": len(usuarios), "eventos_nuevos": len(nuevos), "dias": len(dias)}


class PestanaGoogle:
    """Una pestaña del Sheet, sobre un Worksheet de gspread."""

    def __init__(self, ws, filas_cabecera, nueva):
        self.ws = ws
        self.filas_cabecera = filas_cabecera
        self.ncols = max(len(f) for f in filas_cabecera)
        # Las cabeceras se reescriben siempre (así se actualizan si cambian).
        self._asegurar_tamano(len(filas_cabecera))
        ws.update(values=filas_cabecera, range_name="A1", raw=True)
        if nueva:
            ws.freeze(rows=len(filas_cabecera))
            ws.batch_format([{"range": f"A1:{_letra_columna(self.ncols)}1", "format": FORMATO_CABECERA}])

    def _asegurar_tamano(self, filas):
        if self.ws.row_count < filas or self.ws.col_count < self.ncols:
            self.ws.resize(rows=max(self.ws.row_count, filas + 100), cols=max(self.ws.col_count, self.ncols))

    def reemplazar(self, filas, desde_fila, formulas=False):
        """Escribe `filas` a partir de `desde_fila` y vacía lo que quede debajo."""
        ultima = desde_fila + len(filas) - 1
        self._asegurar_tamano(ultima)
        if filas:
            # raw=False = como si se tecleara (necesario para las fórmulas).
            self.ws.update(values=filas, range_name=f"A{desde_fila}", raw=not formulas)
        if self.ws.row_count > ultima:
            self.ws.batch_clear([f"A{ultima + 1}:{_letra_columna(self.ncols)}{self.ws.row_count}"])

    def escribir(self, filas, desde_fila):
        """Escribe `filas` a partir de `desde_fila` sin tocar el resto."""
        self._asegurar_tamano(desde_fila + len(filas) - 1)
        self.ws.update(values=filas, range_name=f"A{desde_fila}", raw=True)

    def ids(self):
        valores = self.ws.col_values(1, value_render_option="UNFORMATTED_VALUE")
        return [int(v) for v in valores[len(self.filas_cabecera):] if isinstance(v, (int, float))]

    def anadir(self, filas):
        self.ws.append_rows(filas, value_input_option="RAW", table_range="A1")

    def formatear(self, formatos):
        self.ws.batch_format([{"range": rango, "format": formato} for rango, formato in formatos])


def _vacia(valores):
    # gspread devuelve [[]] (no []) para una pestaña vacía.
    return not any(str(celda).strip() for fila in valores for celda in fila)


def abrir_libro(ruta_credencial, sheet_id):
    import gspread  # solo hace falta aquí; el bot no lo usa

    cliente = gspread.service_account(filename=ruta_credencial)
    return LibroGoogle(cliente.open_by_key(sheet_id))


class LibroGoogle:
    """El Sheet entero, sobre un Spreadsheet de gspread."""

    def __init__(self, libro):
        self._libro = libro
        self._pestanas = {}
        self._renombrada = None

    def preparar(self):
        if self._libro.locale != LOCALE:
            self._libro.update_locale(LOCALE)
        if self._libro.timezone != ZONA_LIBRO:
            self._libro.update_timezone(ZONA_LIBRO)
        hojas = self._libro.worksheets()
        self._pestanas = {ws.title: ws for ws in hojas}
        # La pestaña vacía con la que nace un Sheet nuevo pasa a ser «Usuarios».
        if (TAB_USUARIOS not in self._pestanas and len(hojas) == 1
                and hojas[0].title in NOMBRES_PESTANA_INICIAL and _vacia(hojas[0].get_all_values())):
            hojas[0].update_title(TAB_USUARIOS)
            self._pestanas = {TAB_USUARIOS: hojas[0]}
            self._renombrada = TAB_USUARIOS
        else:
            self._renombrada = None

    def pestana(self, nombre, filas_cabecera):
        ws = self._pestanas.get(nombre)
        nueva = ws is None or nombre == self._renombrada
        if ws is None:
            ws = self._libro.add_worksheet(title=nombre, rows=1000, cols=max(len(f) for f in filas_cabecera))
            self._pestanas[nombre] = ws
        return PestanaGoogle(ws, filas_cabecera, nueva)


def ruta_credencial():
    """Credencial de la cuenta de servicio de Google.

    systemd la entrega con LoadCredential= en $CREDENTIALS_DIRECTORY/google
    (ver deploy/captacion-sheet@.service). Para pruebas a mano vale
    CAPTACION_GOOGLE_CREDENCIAL=<ruta>.
    """
    carpeta = os.environ.get("CREDENTIALS_DIRECTORY")
    if carpeta and os.path.isfile(os.path.join(carpeta, "google")):
        return os.path.join(carpeta, "google")
    ruta = os.environ.get("CAPTACION_GOOGLE_CREDENCIAL", "").strip()
    return ruta if ruta and os.path.isfile(ruta) else None


def correo_cuenta_servicio(ruta):
    try:
        with open(ruta, encoding="utf-8") as f:
            return json.load(f).get("client_email", "?")
    except (OSError, ValueError):
        return "?"


def main(argv=None):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    # Sin esto, una llamada colgada a Google bloquearía el job entero (ver
    # el mismo timeout en scripts/vm_job_resultados_galgos.py).
    socket.setdefaulttimeout(60)
    try:
        cfg = cargar_config()
    except ErrorConfig as e:
        log.error("Configuración incorrecta: %s", e)
        return 2
    if cfg.sheet_id is None:
        log.info("CAPTACION_SHEET_ID vacío: no hay Sheet configurado, nada que hacer")
        return 0
    credencial = ruta_credencial()
    if credencial is None:
        log.error("No encuentro la credencial de Google (/etc/premier-captacion/google.json)")
        return 2
    try:
        import gspread  # noqa: F401
    except ImportError:
        log.error("Falta gspread: lo instala deploy/instalar.sh en /opt/premier-captacion/venv")
        return 2

    con = db.abrir(cfg.db_path)
    try:
        resultado = sincronizar(con, cfg.tz, abrir_libro(credencial, cfg.sheet_id))
    except Exception as e:
        texto = str(e)
        if any(c in texto for c in ("403", "404", "PERMISSION_DENIED", "not found")) or type(e).__name__ == "SpreadsheetNotFound":
            texto += (f" — ¿Está el Sheet compartido como editor con "
                      f"{correo_cuenta_servicio(credencial)}?")
        log.error("No se pudo actualizar el Sheet: %s", texto)
        return 1
    finally:
        con.close()
    log.info("Sheet actualizado: %(usuarios)d usuarios, %(eventos_nuevos)d eventos nuevos, %(dias)d días", resultado)
    return 0


if __name__ == "__main__":
    sys.exit(main())
