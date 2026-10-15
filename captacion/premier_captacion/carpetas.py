"""
Reglas de las carpetas de la cuenta del dueño (fase 3 de captacion/PLAN.md).

- Si alguien que recibió la bienvenida (del bot o manual) le escribe por
  privado, su chat entra en la carpeta del día («MM.DD», hora de España).
  Si estaba en la de otro día, pasa a la de hoy.
- Si el dueño le envía un enlace de invitación que NO es del canal
  principal (uno de los canales de venta), el chat pasa a «free send» y ahí
  se queda aunque vuelva a escribir.
- Se mantienen las 5 carpetas de días más recientes; las más antiguas se
  borran (borrar una carpeta no borra ningún chat).
- «free send» se queda con los ~90 chats del embudo más recientes (tope de
  Telegram sin Premium: 100 chats por carpeta y 10 carpetas).
- Solo se tocan chats del embudo. Los chats que el dueño haya metido a mano
  en una carpeta no se quitan nunca (salvo que se borre la carpeta entera
  de un día al rotar, que es lo acordado).
- Solo se gestionan las carpetas de días («MM.DD») y «free send». Las demás
  carpetas del dueño no se tocan.

Este módulo no sabe nada de Telethon: habla con un "adaptador" (ver
`CarpetasEnMemoria`, que sirve para los tests y para el modo simulación,
y `TelegramReal` en lector.py) con estas operaciones:
    await carpetas()                         -> [Carpeta]
    await crear_carpeta(titulo, usuarios)    -> id
    await cambiar(id, anadir, quitar)        -> False si se borró por quedar vacía
    await borrar(id)
    await destino_enlace(hash)               -> (chat_id o None, título o None)
"""
import asyncio
import logging
import re
import time
import unicodedata
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from typing import Optional

from . import db, enlaces

log = logging.getLogger("captacion.carpetas")

_RE_DIA = re.compile(r"^(\d{2})\.(\d{2})$")
# Cuánto se fía uno de lo que se sabe de un enlace antes de volver a preguntar.
VIGENCIA_ENLACE_S = 30 * 24 * 3600


@dataclass(frozen=True)
class Carpeta:
    id: int
    titulo: str
    usuarios: frozenset  # user_id de los chats privados que incluye (también fijados)
    total: int           # chats incluidos en total, que es lo que Telegram limita
    gestionable: bool = True  # False = carpeta compartida (chatlist): no se toca nunca
    con_reglas: bool = False  # incluye por tipo (contactos, grupos...): no queda vacía


@dataclass(frozen=True)
class Ajustes:
    canal_principal: Optional[int] = None  # id "puro" (sin -100) del canal principal
    dias: int = 5
    nombre_free_send: str = "free send"
    max_free_send: int = 90
    max_carpetas: int = 10
    max_chats: int = 100
    simular: bool = True


def id_canal_puro(canal_id):
    """-1001234567890 (formato de la Bot API) -> 1234567890 (formato de Telethon)."""
    if canal_id is None:
        return None
    return -canal_id - 10 ** 12 if canal_id < -10 ** 12 else abs(canal_id)


def titulo_dia(fecha):
    return f"{fecha:%m.%d}"


def fecha_de_titulo(titulo, hoy):
    """«10.14» -> date; si con el año de hoy cae en el futuro, es del año pasado."""
    m = _RE_DIA.match(titulo.strip())
    if not m:
        return None
    mes, dia = int(m.group(1)), int(m.group(2))
    for anio in (hoy.year, hoy.year - 1):
        try:
            fecha = date(anio, mes, dia)
        except ValueError:
            return None
        if fecha <= hoy:
            return fecha
    return None


def normalizar(texto):
    sin_tildes = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in sin_tildes if not unicodedata.combining(c)).casefold()


def detectar_boton(texto):
    """Qué botón de la bienvenida pulsó, por el texto que dejó escrito."""
    t = normalizar(texto)
    if "ya he apostado" in t:
        return "ya_apostado"
    if "primera vez" in t:
        return "primera_vez"
    return None


class Organizador:
    def __init__(self, con, tg, tz, ajustes, avisar=None, reloj=time.time):
        self.con = con
        self.tg = tg
        self.tz = tz
        self.aj = ajustes
        self.avisar = avisar or (lambda texto: None)
        self.reloj = reloj
        self._candado_creado = None
        self._dia_simulado = None

    @property
    def _candado(self):
        # Se crea dentro del bucle de asyncio (en Python 3.9 un Lock creado
        # fuera queda atado a otro bucle).
        if self._candado_creado is None:
            self._candado_creado = asyncio.Lock()
        return self._candado_creado

    # --- Utilidades -------------------------------------------------------------

    def _dia(self, ts):
        return datetime.fromtimestamp(ts, self.tz).date()

    def _hoy(self):
        return self._dia(self.reloj())

    def _es_dia(self, carpeta):
        return carpeta.gestionable and fecha_de_titulo(carpeta.titulo, self._hoy()) is not None

    def _es_free_send(self, carpeta):
        return carpeta.gestionable and carpeta.titulo.strip().casefold() == self.aj.nombre_free_send.casefold()

    def _nombre(self, user_id):
        fila = db.obtener_usuario(self.con, user_id)
        if fila is None:
            return str(user_id)
        if fila["nombre"] and fila["username"]:
            return f"{fila['nombre']} (@{fila['username']})"
        return fila["nombre"] or (f"@{fila['username']}" if fila["username"] else str(user_id))

    async def _al_dia(self):
        """Simulación: al cambiar de día se vuelve a partir de las carpetas
        reales, para ver las que el dueño haya creado o borrado a mano (lo
        simulado el día anterior se olvida)."""
        if not self.aj.simular:
            return
        hoy = self._hoy()
        if self._dia_simulado not in (None, hoy) and hasattr(self.tg, "refrescar"):
            await self.tg.refrescar()
        self._dia_simulado = hoy

    def _informar(self, texto):
        if self.aj.simular:
            log.info("SIMULACIÓN: %s", texto)
            self.avisar(f"🧪 Simulación (no he tocado nada): {texto}")
        else:
            log.info("%s", texto)

    def _apuntar_carpeta(self, user_id, titulo, accion):
        if self.aj.simular:
            return
        ahora = self.reloj()
        with self.con:
            if accion == "entra":
                db.actualizar_campos(self.con, user_id, ahora, carpeta=titulo)
            else:
                fila = db.obtener_usuario(self.con, user_id)
                if fila is not None and fila["carpeta"] == titulo:
                    db.actualizar_campos(self.con, user_id, ahora, carpeta=None)
            db.registrar_evento(self.con, ahora, "carpeta", user_id, carpeta=titulo, accion=accion)

    # --- Mensajes -----------------------------------------------------------------

    def _ya_visto(self, fila, msg_id):
        return fila["ultimo_msg_id"] is not None and msg_id <= fila["ultimo_msg_id"]

    async def al_recibir(self, user_id, msg_id, ts, texto, usuario=None):
        """Un mensaje que alguien le ha enviado al dueño por privado."""
        async with self._candado:
            fila = db.obtener_usuario(self.con, user_id)
            if not db.es_del_embudo(fila) or self._ya_visto(fila, msg_id):
                return
            dia = self._dia(ts)
            nuevo_dia = fila["ultimo_mensaje_ts"] is None or self._dia(fila["ultimo_mensaje_ts"]) != dia
            campos = {"ultimo_mensaje_ts": int(ts), "ultimo_msg_id": msg_id}
            detalle = {}
            if fila["primer_mensaje_ts"] is None:
                campos["primer_mensaje_ts"] = int(ts)
                detalle["primera_vez"] = True
            if fila["boton"] is None:
                campos["boton"] = detalle["boton"] = detectar_boton(texto) or "otro"
            with self.con:
                if usuario:
                    db.actualizar_datos_usuario(self.con, ts, usuario)
                db.actualizar_campos(self.con, user_id, ts, **campos)
                if nuevo_dia:
                    db.registrar_evento(self.con, ts, "te_escribe", user_id, **detalle)

            if fila["enlace_venta_ts"] is not None:
                return  # ya tiene enlace de venta: se queda en «free send»
            if dia < self._hoy() - timedelta(days=self.aj.dias - 1):
                return  # mensaje antiguo (p. ej. al recuperar lo perdido): no se mueve
            await self._a_carpeta_del_dia(user_id, dia)

    async def al_enviar(self, user_id, msg_id, ts, textos):
        """Un mensaje que el dueño ha enviado a alguien por privado."""
        async with self._candado:
            fila = db.obtener_usuario(self.con, user_id)
            if not db.es_del_embudo(fila) or self._ya_visto(fila, msg_id):
                return
            with self.con:
                db.actualizar_campos(self.con, user_id, ts, ultimo_msg_id=msg_id)
            venta = []
            for h in enlaces.hashes_invitacion(textos):
                chat_id, titulo = await self.destino(h)
                if self.es_principal(chat_id):
                    with self.con:
                        db.registrar_evento(self.con, ts, "enlace_principal", user_id, enlace=enlaces.enlace(h))
                else:
                    venta.append((h, titulo))
            if not venta:
                return
            with self.con:
                for h, titulo in venta:
                    db.registrar_evento(self.con, ts, "enlace_venta", user_id,
                                        enlace=enlaces.enlace(h), canal=titulo or "desconocido")
                h, titulo = venta[-1]
                campos = {"enlace_venta": enlaces.enlace(h), "canal_venta": titulo or "desconocido"}
                if fila["enlace_venta_ts"] is None:
                    campos["enlace_venta_ts"] = int(ts)
                db.actualizar_campos(self.con, user_id, ts, **campos)
            await self._a_free_send(user_id)

    def es_principal(self, chat_id):
        return self.aj.canal_principal is not None and chat_id == self.aj.canal_principal

    async def destino(self, hash_enlace):
        """(chat_id, título) del canal al que lleva un enlace, con caché en la base de datos."""
        guardado = db.enlace_guardado(self.con, hash_enlace)
        if guardado is not None and self.reloj() - guardado["comprobado_ts"] < VIGENCIA_ENLACE_S:
            return guardado["chat_id"], guardado["titulo"]
        chat_id, titulo = await self.tg.destino_enlace(hash_enlace)
        with self.con:
            db.guardar_enlace(self.con, hash_enlace, chat_id, titulo, self.reloj())
        return chat_id, titulo

    # --- Carpetas -----------------------------------------------------------------

    async def _quitar_de_dias(self, user_id, salvo=None):
        for c in await self.tg.carpetas():
            if self._es_dia(c) and c.titulo != salvo and user_id in c.usuarios:
                sigue = await self.tg.cambiar(c.id, quitar={user_id})
                self._informar(f"saco a {self._nombre(user_id)} de la carpeta {c.titulo}"
                               + ("" if sigue else " (se queda vacía y la borro)"))
                self._apuntar_carpeta(user_id, c.titulo, "sale")

    async def _hueco(self, carpetas, para):
        """¿Cabe una carpeta más? Si no, borra la de días más antigua."""
        if len(carpetas) < self.aj.max_carpetas:
            return True
        hoy = self._hoy()
        dias = sorted(((fecha_de_titulo(c.titulo, hoy), c) for c in carpetas
                       if self._es_dia(c) and c.titulo not in (para, titulo_dia(hoy))),
                      key=lambda par: par[0])
        if not dias:
            self.avisar(f"⚠️ No puedo crear la carpeta «{para}»: ya tienes {len(carpetas)} carpetas "
                        "(el máximo sin Premium) y ninguna es de días. Libera una.")
            return False
        await self._borrar(dias[0][1])
        return True

    async def _borrar(self, carpeta):
        await self.tg.borrar(carpeta.id)
        self._informar(f"borro la carpeta {carpeta.titulo} (los chats no se borran)")
        if not self.aj.simular:
            ahora = self.reloj()
            with self.con:
                self.con.execute("UPDATE usuarios SET carpeta = NULL, actualizado_ts = ? WHERE carpeta = ?",
                                 (int(ahora), carpeta.titulo))
                db.registrar_evento(self.con, ahora, "carpeta_borrada", None, carpeta=carpeta.titulo)

    async def _a_carpeta_del_dia(self, user_id, dia):
        await self._al_dia()
        titulo = titulo_dia(dia)
        await self._quitar_de_dias(user_id, salvo=titulo)
        carpetas = await self.tg.carpetas()
        destino = next((c for c in carpetas if self._es_dia(c) and c.titulo == titulo), None)
        if destino is None:
            if not await self._hueco(carpetas, titulo):
                return
            await self.tg.crear_carpeta(titulo, {user_id})
            self._informar(f"creo la carpeta {titulo} y meto a {self._nombre(user_id)}")
        elif user_id in destino.usuarios:
            return
        elif destino.total >= self.aj.max_chats:
            self.avisar(f"⚠️ La carpeta {titulo} ya tiene {destino.total} chats (el máximo): "
                        f"no puedo meter a {self._nombre(user_id)}.")
            return
        else:
            await self.tg.cambiar(destino.id, anadir={user_id})
            self._informar(f"meto a {self._nombre(user_id)} en la carpeta {titulo}")
        self._apuntar_carpeta(user_id, titulo, "entra")
        await self._rotar_sin_candado()

    async def _a_free_send(self, user_id):
        await self._al_dia()
        await self._quitar_de_dias(user_id)
        carpetas = await self.tg.carpetas()
        fs = next((c for c in carpetas if self._es_free_send(c)), None)
        nombre = self.aj.nombre_free_send
        if fs is None:
            if not await self._hueco(carpetas, nombre):
                return
            await self.tg.crear_carpeta(nombre, {user_id})
            self._informar(f"creo la carpeta «{nombre}» y meto a {self._nombre(user_id)}")
        elif user_id in fs.usuarios:
            return
        else:
            # Se quitan los del embudo que llevan más tiempo (por fecha del
            # primer enlace de venta); los que el dueño metió a mano, nunca.
            sobran = fs.total + 1 - self.aj.max_free_send
            quitar = []
            if sobran > 0:
                del_embudo = self.con.execute(
                    f"SELECT user_id FROM usuarios WHERE enlace_venta_ts IS NOT NULL "
                    f"AND user_id IN ({','.join('?' * len(fs.usuarios))}) ORDER BY enlace_venta_ts, user_id",
                    tuple(fs.usuarios),
                ).fetchall() if fs.usuarios else []
                quitar = [f["user_id"] for f in del_embudo if f["user_id"] != user_id][:sobran]
            if fs.total + 1 - len(quitar) > self.aj.max_chats:
                self.avisar(f"⚠️ «{nombre}» está llena ({fs.total} chats, casi todos puestos a mano): "
                            f"no puedo meter a {self._nombre(user_id)}.")
                return
            await self.tg.cambiar(fs.id, anadir={user_id}, quitar=set(quitar))
            self._informar(f"meto a {self._nombre(user_id)} en «{nombre}»"
                           + (f" y saco a los {len(quitar)} más antiguos para no pasar de {self.aj.max_free_send}"
                              if quitar else ""))
            for antiguo in quitar:
                self._apuntar_carpeta(antiguo, nombre, "sale")
        self._apuntar_carpeta(user_id, nombre, "entra")

    async def rotar(self):
        async with self._candado:
            await self._al_dia()
            await self._rotar_sin_candado()

    async def _rotar_sin_candado(self):
        hoy = self._hoy()
        dias = sorted(((fecha_de_titulo(c.titulo, hoy), c) for c in await self.tg.carpetas() if self._es_dia(c)),
                      key=lambda par: par[0], reverse=True)
        for _, carpeta in dias[self.aj.dias:]:
            await self._borrar(carpeta)


class ErrorTelegramFalso(Exception):
    """Lo que devolvería Telegram si se le pide algo que no acepta."""


class CarpetasEnMemoria:
    """Carpetas en memoria, con las mismas normas que Telegram.

    Sirve para los tests y para el modo simulación del lector: parte de las
    carpetas reales (`desde`) y aplica los cambios solo aquí, sin tocar
    Telegram. `destino_enlace` sí se pregunta al adaptador real (es lectura).
    """

    def __init__(self, carpetas=(), destinos=None, real=None, max_carpetas=10, max_chats=100):
        self._carpetas = {c.id: c for c in carpetas}
        self._orden = [c.id for c in carpetas]
        self.destinos = dict(destinos or {})
        self.real = real
        self.max_carpetas = max_carpetas
        self.max_chats = max_chats
        self.cambios = []  # registro de operaciones de escritura (para los tests)

    @classmethod
    async def desde(cls, real, **kwargs):
        return cls(await real.carpetas(), real=real, **kwargs)

    async def refrescar(self):
        """Olvida lo simulado y vuelve a partir de las carpetas reales de ahora."""
        if self.real is None:
            return
        carpetas = await self.real.carpetas()
        self._carpetas = {c.id: c for c in carpetas}
        self._orden = [c.id for c in carpetas]

    async def carpetas(self):
        return [self._carpetas[i] for i in self._orden]

    async def crear_carpeta(self, titulo, usuarios):
        if len(self._carpetas) >= self.max_carpetas:
            raise ErrorTelegramFalso("DIALOG_FILTERS_TOO_MUCH")
        if not usuarios:
            raise ErrorTelegramFalso("FILTER_INCLUDE_EMPTY")
        nuevo = min(set(range(2, 256)) - set(self._carpetas))
        self._carpetas[nuevo] = Carpeta(nuevo, titulo, frozenset(usuarios), len(usuarios))
        self._orden.append(nuevo)  # Telegram añade las carpetas nuevas al final
        self.cambios.append(("crear", titulo, frozenset(usuarios)))
        return nuevo

    async def cambiar(self, carpeta_id, anadir=frozenset(), quitar=frozenset()):
        c = self._carpetas[carpeta_id]
        if not c.gestionable:
            raise AssertionError("se ha intentado cambiar una carpeta compartida")
        quitar = set(quitar) & c.usuarios
        anadir = set(anadir) - c.usuarios
        usuarios = (c.usuarios - quitar) | anadir
        total = c.total - len(quitar) + len(anadir)
        if total > self.max_chats:
            raise ErrorTelegramFalso("CHATLIST_INCLUDE_INVALID (demasiados chats)")
        self.cambios.append(("cambiar", c.titulo, frozenset(anadir), frozenset(quitar)))
        if total == 0 and not c.con_reglas:
            await self.borrar(carpeta_id)
            return False
        self._carpetas[carpeta_id] = replace(c, usuarios=frozenset(usuarios), total=total)
        return True

    async def borrar(self, carpeta_id):
        c = self._carpetas.pop(carpeta_id)
        self._orden.remove(carpeta_id)
        self.cambios.append(("borrar", c.titulo))

    async def destino_enlace(self, hash_enlace):
        if self.real is not None:
            return await self.real.destino_enlace(hash_enlace)
        return self.destinos.get(hash_enlace, (None, None))

    # Ayuda para los tests y los registros.
    def por_titulo(self, titulo):
        return next((c for c in self._carpetas.values() if c.titulo == titulo), None)
