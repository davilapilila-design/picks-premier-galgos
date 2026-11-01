"""
Cruce de las ventas de overoption con las personas de Telegram (quién es
cada correo), diseño del 2026-11-01:
docs/superpowers/specs/2026-11-01-cuentas-por-cliente-design.md

- Candidatos de una venta: quienes entraron a su canal entre 0 s y
  VENTANA_S después del pago. Nadie entra antes de pagar (medido en 519
  compras confirmadas: de 3 s a 34 s después), así que quien entró antes
  ya tenía el enlace y no es el comprador.
- Juicio de una venta frente a una persona: «buena» (es candidata),
  «mala» (se podía ver y no entró después de pagar) o «sin» (no se puede
  comprobar: sin canal, sin datos o ya estaba dentro).
- Un correo es de una persona por sus compras si tiene MIN_BUENAS buenas o
  más, son al menos PROPORCION de sus comprobables, la segunda persona no
  pasa de SOMBRA de sus buenas, el nombre no choca (nombres.choca) y esa
  persona no pagó ya alguno de esos canales con otro correo (nadie paga dos
  veces un canal). Un cruce suelto por hora nunca da el correo.
- Por nombre (pagos._por_nombre), salvo que la hora diga otra persona.
- Lo que escribe el dueño en «Correos por identificar» manda; su «no»
  bloquea cualquier asignación automática de ese correo.

Las gratis (compensaciones y gratuita) quedan fuera de los candidatos con
`gratis` (plan siguiente: se leerán de los chats y los canales).

Examen fijo contra los correos que confirmó el dueño (solo lectura):
    CAPTACION_DB=/var/lib/premier-captacion/real.db python -m premier_captacion.cruce examen
"""
from collections import Counter, defaultdict

from . import pagos

VENTANA_S = 180  # hasta 3 min después del pago para entrar al canal
MIN_BUENAS = 3
PROPORCION = 0.8
SOMBRA = 0.5
BUENA, MALA, SIN = "buena", "mala", "sin"


class Datos:
    """Las ventas y las entradas a los canales, leídas una vez, con las
    consultas del cruce: candidatos de cada venta y juicio frente a una
    persona."""

    def __init__(self, con, ventana_s=VENTANA_S, solo_ventas=True, gratis=None):
        self.ventana_s = ventana_s
        self.gratis = gratis or set()  # {(grupo, user_id)} de entradas gratis
        por_enlace, por_titulo, self.canales = pagos._mapa_canales(con)
        self._por_canal = pagos._entradas_por_canal(con)  # canal -> [(user_id, ts)]
        self._por_enlace = pagos._invitados_por_enlace(con)  # enlace -> [(user_id, ts)]
        # Desde cuándo se sabe todo el que entra en cada canal (el registro
        # trae también a quien se fue).
        self.registro_desde = {f[0]: f[1] for f in con.execute(
            "SELECT canal_id, MIN(ts) FROM ventas_movimientos GROUP BY canal_id")}
        self._entradas = defaultdict(set)  # (grupo, user_id) -> {ts}
        for canal_id, lista in self._por_canal.items():
            for uid, ts in lista:
                self._entradas[(canal_id, uid)].add(ts)
        for enlace, lista in self._por_enlace.items():
            for uid, ts in lista:
                self._entradas[(por_enlace.get(enlace, enlace), uid)].add(ts)
        filtro = "WHERE es_propina = 0 AND estado = 'SUCCESS'" if solo_ventas else ""
        self.ventas = []
        self._de = defaultdict(list)  # correo -> sus ventas
        for f in con.execute(f"SELECT * FROM pagos_overoption {filtro} ORDER BY pago_ts"):
            v = dict(f)
            v["canal_id"] = pagos._canal_de_venta(v, por_enlace, por_titulo)
            # El canal, o el enlace si no se sabe el canal (para «nadie paga dos veces»).
            v["grupo"] = v["canal_id"] if v["canal_id"] is not None else v["enlace"]
            v["clave"] = pagos._clave_correo(v["correo"])
            v["candidatos"] = self._candidatos(v)
            self.ventas.append(v)
            if v["clave"]:
                self._de[v["clave"]].append(v)

    def _candidatos(self, v):
        """Quiénes entraron justo después de pagar (con el enlace de la venta
        si se leyó su lista; si no, al canal), o None si no se sabe el canal."""
        fuente = self._por_enlace.get(v["enlace"]) if v["enlace"] else None
        if fuente is None and v["canal_id"] is not None:
            fuente = self._por_canal.get(v["canal_id"], [])
        if fuente is None:
            return None
        if v["pago_ts"] is None:
            return set()
        return {uid for uid, ts in fuente if 0 <= ts - v["pago_ts"] <= self.ventana_s
                and (v["grupo"], uid) not in self.gratis}

    def juicio(self, v, uid):
        """BUENA, MALA o SIN: la venta v frente a la persona uid."""
        if v["candidatos"] is None or v["pago_ts"] is None:
            return SIN
        if uid in v["candidatos"]:
            return BUENA
        if (v["grupo"], uid) in self.gratis:
            return SIN
        pago, entradas = v["pago_ts"], self._entradas.get((v["grupo"], uid), ())
        if any(t > pago + self.ventana_s for t in entradas):
            return MALA  # entró, pero a otra hora
        if any(t >= pago for t in entradas):
            return SIN  # entró a esa hora por otro enlace: no se sabe
        if any(t < pago for t in entradas):
            return SIN  # ya estaba dentro antes de pagar
        desde = self.registro_desde.get(v["canal_id"])
        if desde is not None and pago >= desde:
            return MALA  # el registro lo habría visto entrar
        return SIN

    def correos(self):
        return sorted(self._de)

    def ventas_de(self, correo):
        return self._de.get(correo, [])

    def grupos_de(self, correo):
        """Los canales que compró el correo (o el producto si no se sabe)."""
        return {v["grupo"] if v["grupo"] is not None else v["producto"] for v in self.ventas_de(correo)}

    def puntuar(self, correo, excluidos=frozenset()):
        """[(user_id, buenas, comprobables)] de quienes salen como candidatos
        en alguna compra del correo, de más a menos buenas."""
        ventas = self.ventas_de(correo)
        uids = {u for v in ventas for u in (v["candidatos"] or ())} - set(excluidos)
        tabla = []
        for uid in uids:
            j = Counter(self.juicio(v, uid) for v in ventas)
            tabla.append((uid, j[BUENA], j[BUENA] + j[MALA]))
        tabla.sort(key=lambda t: (-t[1], t[2] - t[1], t[0]))
        return tabla
