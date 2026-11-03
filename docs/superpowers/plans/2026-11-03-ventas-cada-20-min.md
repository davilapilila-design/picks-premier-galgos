# Ventas cada 20 min mientras hay una venta abierta — plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans. Pasos con `- [ ]`.

**Goal:** leer overoption cada 20 min desde que se anuncia una venta en el canal principal
hasta 15 min después de la última carrera del canal de esa venta, sin avisos falsos.

**Architecture:** el lector guarda al momento los mensajes del canal principal en
`publicaciones`; `anuncios.py` (puro, sobre la base local) dice si hay una venta abierta;
un timer cada 20 min lanza `pagos --si-hay-venta`, que solo entra en overoption si la hay.
El cruce no juzga «mala» una compra reciente cuyo enlace aún no se ha leído después del pago.

**Tech Stack:** Python 3, SQLite, Telethon, systemd. Diseño:
`docs/superpowers/specs/2026-11-03-ventas-cada-20-min-design.md`.

Tests: `cd captacion && python -m unittest discover -s tests -t .` (en Windows fallan
siempre los mismos 5, que pasan en la VM) y `ruff check .`.

---

### Task 1: menos consultas a overoption (`pagos.py`)
- [ ] Tests (rojo, `tests/test_pagos.py`): un `content_uid` que no es UUID no se consulta;
  uno ya consultado sin enlace no se repite antes de 24 h y sí después; los tests de bajada
  pasan a usar UUID inventados.
- [ ] `RE_UUID`, `REPETIR_SIN_ENLACE_S = 24 * 3600`, `contenido_en_cache(con, uid)` (fila o
  None) y `_preguntar(uid, fila, ahora)` en `bajar_y_guardar`.
- [ ] Verde, ruff, commit.

### Task 2: sin avisos falsos (`cruce.py`)
- [ ] Test (rojo, `tests/test_cruce.py`): compra de hace 1 h con registro del canal y sin
  entrada de la persona → `juicio` = SIN mientras el enlace no se haya leído después de
  pago + VENTANA_S; MALA cuando ya se leyó; una compra de hace más de 48 h, MALA como antes.
- [ ] `Datos(..., ahora=None)`, `RECIENTE_S = 48 * 3600`, `self._leido` (enlace → leido_ts de
  `pagos_enlaces`) y `_sin_leer(v)`; cada `return MALA` de `juicio` pasa por `_sin_leer`.
- [ ] Verde, ruff, examen del cruce en la VM (no más «mal»), commit.

### Task 3: venta abierta (`anuncios.py`, nuevo)
- [ ] Tests (rojo, `tests/test_anuncios.py`): `es_anuncio` (payoption/overoption sí, otro
  texto no); abierta hasta 4 h sin compras; con compras de un canal y sus apuestas, hasta la
  última carrera + 15 min; nunca más de 8 h; un anuncio antiguo no abre nada; las apuestas de
  otro canal no cuentan; un aviso con la hora ya pasada no alarga la venta.
- [ ] `es_anuncio`, `anuncios`, `canal_de_la_venta`, `ultima_carrera`, `hasta`, `abiertas`.
- [ ] Verde, ruff, commit.

### Task 4: el canal principal en `publicaciones` (lector)
- [ ] Tests (rojo, `tests/test_publicaciones.py`): `guardar_al_momento` guarda un mensaje con
  texto y no duplica; `leer_canales` lee también el canal principal (`cfg.canal_id`).
- [ ] `publicaciones.fila_de(m)`, `guardar_al_momento(con, chat_id, m)`; `leer_canales` añade
  el canal principal; `lector.servicio` registra `events.NewMessage` del canal principal.
- [ ] Verde, ruff, commit.

### Task 5: lectura cada 20 min (`pagos.main` y systemd)
- [ ] Test (rojo): `pagos.toca_leer(con, cfg, ahora)` = ventas abiertas (vacío sin anuncio).
- [ ] `pagos.main` con `--si-hay-venta`; `deploy/captacion-pagos-venta@.service` y `.timer`
  (cada 20 min); `instalar.sh` lo activa junto al de las ventas.
- [ ] Verde, ruff, commit.

### Task 6: rama `captacion`, instalar y documentar
- [ ] `instalar.sh` (RAMA por defecto), README, CLAUDE.md y PLAN.md de captación con la rama
  nueva; subir la rama `captacion` y borrar la vieja en GitHub.
- [ ] Bitácora; instalar en la VM con `CAPTACION_RAMA=captacion`; comprobar timers, registro
  del lector y una pasada en seco de `--si-hay-venta`.
