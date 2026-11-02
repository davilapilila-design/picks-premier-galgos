# Gratis, apuestas y cuentas por cliente — plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans. Pasos con `- [ ]`.

**Objetivo:** las piezas 1, 2, 4 y 5 del diseño
(`docs/superpowers/specs/2026-11-01-cuentas-por-cliente-design.md`): apuestas de
cada canal con su resultado, entradas gratis y la pestaña «Clientes · cuentas».

**Arquitectura:** el lector (que ya tiene la sesión de Telegram) lee cada hora,
solo lectura, los mensajes nuevos de los canales de venta y del grupo de picks,
y los enlaces de canales de venta que el dueño manda por privado; lo guarda en
la base. La sincronización del Sheet (cada 10 min) calcula con eso las gratis
(que también salen de los candidatos del cruce), lee los resultados de la hoja
de picks y escribe la pestaña de cuentas.

**Medido antes de empezar (2026-11-02, solo lectura):** desde el 22/07 se ven
1.520 entradas (persona, canal) de 205 personas: 757 con compra de un correo con
persona, 122 tras un enlace por privado ya apuntado (los apuntados son solo de
las personas del embudo) y 640 sin explicar, de ellas 319 en tandas (5 o más
en 10 min en el mismo canal: el enlace publicado en un canal). La cuenta de
servicio de captación puede leer la hoja de picks (312 apuestas con
resultado). Todo en EUR (2.736 ventas, 60.556 € de importe).

## Task 1: lectura de canales y enlaces por privado (en el lector)
**Files:** `premier_captacion/db.py` (migración 12), `premier_captacion/publicaciones.py`
(nuevo), `premier_captacion/ventas.py` (`filtrar`), `premier_captacion/lector.py`,
`tests/test_publicaciones.py`.
- [ ] Migración 12: `publicaciones(chat_id, msg_id, ts, texto, enlaces, reenvio_chat,
      reenvio_msg)` y `enlaces_privados(user_id, msg_id, ts, hash)`.
- [ ] Tests (rojo): guardar sin duplicar; leer un canal desde el último mensaje
      guardado (o desde el 22/07); reenvío del grupo de picks; enlaces de un
      mensaje (también tras un texto); privados: solo los del dueño, solo con
      enlace, desde la última lectura; Telegram pide esperar → espera y sigue;
      el destino de cada enlace nuevo se pregunta una vez (caché `enlaces`).
- [ ] `publicaciones.py`: `guardar_mensajes`, `guardar_privados`, `leer_canales`,
      `leer_privados`, `lectura_periodica` (cada hora, tras 20 min).
- [ ] `lector.servicio`: tarea `publicaciones.lectura_periodica(client, con, cfg, org.destino)`.
- [ ] Verde, ruff, commit, bitácora.

## Task 2: gratis y cruce
**Files:** `premier_captacion/gratis.py` (nuevo), `premier_captacion/cruce.py`,
`tests/test_gratis.py`.
- [ ] Tests (rojo): enlace por privado antes de entrar = gratis; después, no; enlace de
      otro canal publicado en un canal = gratis para quien estaba dentro (entró
      antes y no salió) y no para quien entró después o ya había salido; la
      gratis no es candidata en el cruce.
- [ ] `gratis.py`: `mapa_enlaces`, `ofertas` ({(canal, uid): (ts, origen)}), `para_cruce`.
- [ ] `cruce.calcular` pasa `gratis.para_cruce(con)` a `Datos` (el examen también).
- [ ] Examen en la base real: no puede tener más «mal» que hoy (0).

## Task 3: apuestas de cada canal
**Files:** `premier_captacion/apuestas.py` (nuevo), `tests/test_apuestas.py`.
- [ ] Tests (rojo): resultados de la hoja de picks por `message_id` (ocultas fuera,
      números con coma); apuesta del canal reenviada al grupo, con el mismo
      texto, o sin encontrar («sin resultado»).
- [ ] `apuestas.py`: `leer_picks(libro)`, `por_canal(con, picks, tz)`.

## Task 4: cuentas por persona y pestaña
**Files:** `premier_captacion/cuentas.py` (nuevo), `premier_captacion/sheet.py`,
`tests/test_cuentas.py`.
- [ ] Tests (rojo): canales pagados (compras de sus correos), gratis y sin explicar
      (equipo fuera, desde el 22/07); apuestas, ganadas, perdidas, unidades,
      simulación a 10 €/unidad y balance; correos sin persona en filas aparte.
- [ ] `cuentas.py`: `calcular`, `filas`, `escribir_pestana`; `sheet.sincronizar` la
      escribe (si la hoja de picks no se puede leer, sin unidades y lo dice).
- [ ] Instalar, comprobar en la base real y en el Sheet, bitácora.
