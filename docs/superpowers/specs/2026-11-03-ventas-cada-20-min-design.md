# Ventas cada 20 min mientras hay una venta abierta (captación) — diseño

Fecha: 2026-11-03. Aprobado por el dueño («dale») el mismo día.

## Objetivo
Ver las compras de overoption y su cruce con Telegram el mismo día, sin
esperar a las lecturas fijas (8:10, 16:10 y 0:10, hora de Madrid), que se
quedan como están.

## Hechos (2026-11-02/03, solo lectura)
- Cada venta se anuncia en el canal principal con un mensaje que lleva el
  enlace de pago de payoption («Estas 3 apuestas por solo 36 € ⬇️
  payoption.io/Dronwhite…»). El enlace va en el texto, sin botones.
- Las compras llegan en el mismo minuto del anuncio (16:45 → 16:45-17:13;
  20:05 → 20:05-21:08). Las lecturas fijas las veían a las 0:10.
- Cada lectura pregunta a overoption por unos 180 productos antiguos que ya
  contestaron que no existen («uid must be a UUID», «no existe»): 537 avisos
  al día en el registro.
- El lector ya recibe al momento lo que pasa en los canales de la cuenta
  (`updates.GetChannelDifferenceRequest` ya está en `guardia.LECTURA`).

## Piezas

### 1. El anuncio de venta (lector)
- El lector guarda al momento los mensajes del canal principal (tabla
  `publicaciones`, como los de los canales de venta), y el repaso de cada hora
  también lo lee por si se escapa alguno. Solo mira: ningún permiso nuevo.
- **Anuncio de venta:** mensaje del canal principal con un enlace de
  payoption u overoption en el texto.

### 2. Cuándo hay una venta abierta (`anuncios.py`, puro)
Por cada anuncio de las últimas 8 h:
- **Canal de la venta:** el de la mayoría de las compras de la primera hora
  tras el anuncio (por el enlace del producto, como el cruce).
- **Última carrera:** la más tardía de las apuestas publicadas en ese canal
  desde una hora antes del anuncio (`apuestas.hora_carrera`, hora de Reino
  Unido; sin los avisos con una hora ya pasada).
- **Abierta** mientras no hayan pasado 15 min de esa última carrera. Si aún
  no se sabe el canal o sus carreras, hasta 4 h después del anuncio. Nunca
  más de 8 h.

### 3. Lectura cada 20 min (`captacion-pagos-venta@`)
Timer cada 20 min que lanza `python -m premier_captacion.pagos --si-hay-venta`:
mira la base local y solo si hay una venta abierta entra en overoption (lo
mismo que las lecturas fijas: solo lectura). Si no, sale sin pedir nada.

### 4. Sin avisos falsos (cruce)
Una compra de las últimas 48 h con enlace conocido no cuenta como «mala»
mientras no se haya leído quién se unió con ese enlace después del pago
(`pagos_enlaces.leido_ts ≥ pago + VENTANA_S`; el lector lo lee cada 30 min).
Queda «sin comprobar» hasta entonces. Las «buenas» sí cuentan al momento.

### 5. Menos consultas a overoption
- Un producto cuyo id no es un UUID no se consulta nunca (overoption lo
  rechaza siempre).
- Uno que ya se consultó sin enlace se vuelve a consultar como mucho una vez
  al día.

### 6. Rama
La rama `captacion-bienvenida` pasa a llamarse `captacion` (bienvenida y
clientes van juntas: comparten la sesión de Telegram del lector y la base).
El instalador descarga `captacion` por defecto.

## Límites
- Si el enlace de pago va en un botón o una foto, no se ve el anuncio: quedan
  las lecturas fijas.
- Las apuestas de un canal nuevo se conocen en el repaso de cada hora; hasta
  entonces vale la regla de las 4 h.

## Seguridad
Solo lectura en overoption y en Telegram; ningún permiso nuevo. Las
credenciales siguen solo en la VM (`overoption.env`, solo root).
