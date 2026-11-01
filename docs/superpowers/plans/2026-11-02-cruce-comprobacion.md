# Cruce nuevo, comprobación continua y avisos — plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sustituir el cruce correo ↔ Telegram por el de la forma A del diseño
(3 buenas y 80 %, veto por nombre, nadie entra antes de pagar), con la pestaña
«Correos · comprobación», avisos del bot al pasar a «revisar» y un examen fijo
contra los correos que confirmó el dueño.

**Diseño:** `docs/superpowers/specs/2026-11-01-cuentas-por-cliente-design.md`
(puntos 3, 3 bis y 6). Las gratis (punto 2), las apuestas (1) y las cuentas
(4-5) van en planes siguientes; este deja preparado el hueco de las gratis
(conjunto vacío) para no tener que tocar el cruce después.

**Arquitectura:** módulo nuevo `cruce.py` (el cálculo, sin Telegram ni Sheet)
que reutiliza los lectores de datos que ya hay en `pagos.py`;
`pagos.emparejar_ventas` pasa a delegar en él y conserva su salida (mismas
claves), así que el Sheet, la copia y `ventas.py` no cambian. Módulo nuevo
`comprobacion.py` (juicio por correo, estado, pestaña y avisos).

**Tech Stack:** Python 3.9+, sqlite3, unittest; gspread (Sheet) y la Bot API
(avisos) ya usados por el proyecto.

---

## Reglas (resumen del diseño, la referencia para los tests)

- **Candidatos de una venta:** quienes entraron entre 0 s y `VENTANA_S` (180 s)
  después del pago, con la lista del enlace de esa venta si se leyó y, si no,
  con las entradas del canal. Entrar antes del pago no cuenta (adiós `ANTES_S`).
- **Juicio de una venta frente a una persona:**
  - `buena`: es candidata;
  - `mala`: entró en ese canal a otra hora después del pago, o el registro
    del canal cubría la hora del pago y no entró;
  - `sin`: el resto (no hay canal, no hay datos o ya estaba dentro antes de
    pagar).
- **Un correo es de una persona (por compras)** si tiene ≥ 3 buenas, las
  buenas son ≥ 80 % de sus comprobables (buenas + malas), la segunda persona
  tiene ≤ la mitad de buenas, el nombre no choca y esa persona no pagó ya
  alguno de esos canales con otro correo. Se asigna de más a menos buenas.
- **Nombre que choca:** el correo empieza por un nombre de pila conocido,
  el nombre de Telegram empieza por otro nombre de pila distinto y ninguna
  palabra del nombre de Telegram (4+ letras) está en el correo.
- **Por nombre:** como hoy (`pagos._por_nombre`), salvo que la hora dé otra
  persona (punto anterior, aunque esté vetada).
- **Lo que escribe el dueño:** una persona manda sobre todo; «no» bloquea
  cualquier asignación automática de ese correo (antes solo la de nombre).
- **Sin dueño:** la venta no lleva persona; `posibles` = sus candidatos
  (menos quien ya pagó ese canal con otro correo). Estados de venta:
  `manual`, `por_nombre`, `por_correo`, `dudosa_varios` (hay candidatos),
  `sin_emparejar`, `sin_canal`. Desaparecen `emparejada` y `por_eliminacion`.
- **Estado del correo** (frente a su persona o, si no tiene, al mejor
  candidato): «revisar» si sus 2 últimas comprobables son malas, o si con
  ≥ 5 comprobables las buenas bajan del 80 %, o si con ≥ 5 compras ninguna de
  las 5 últimas es buena; «vigilar» si tiene persona y no llega a la regla
  (salvo las del dueño) o tiene alguna mala; «OK» el resto; «sin asignar»
  si no tiene persona.
- **Avisos:** al pasar a «revisar», un mensaje del bot al dueño por correo;
  no se repite hasta que ese correo vuelva a OK. La primera vez (sin avisos
  previos) un solo mensaje con cuántos hay, sin uno por correo. Si el envío
  falla, se reintenta en la siguiente sincronización.

## Ficheros

- Crear `captacion/premier_captacion/cruce.py`: `Datos` (carga y consultas:
  candidatos, juicio), `asignar`, `calcular`, `emparejar`, `examen`, `main`.
- Crear `captacion/premier_captacion/comprobacion.py`: `resumen_correo`,
  `estados`, `filas`, `escribir_pestana`, `avisar_cambios`, `aviso_por_bot`.
- Modificar `captacion/premier_captacion/nombres.py`: `choca(correo, nombre, username)`.
- Modificar `captacion/premier_captacion/pagos.py`: `emparejar_ventas`
  delega en `cruce`; fuera `_propagar_por_correo`, `_eliminar`, `ANTES_S`,
  `POR_CORREO_*`, `SEGURAS`, `MAX_VUELTAS`; textos de estado;
  `escribir_pestanas(..., avisar=None)` escribe la comprobación y avisa.
- Modificar `captacion/premier_captacion/sheet.py`: `sincronizar(..., avisar=None)`
  y `main` crea el aviso con `comprobacion.aviso_por_bot(cfg)`.
- Modificar `captacion/premier_captacion/db.py`: migración 11, tabla `pagos_avisos`.
- Tests: `captacion/tests/test_cruce.py` (reescrito para las reglas nuevas,
  con los mismos ayudantes), `captacion/tests/test_comprobacion.py` (nuevo),
  `captacion/tests/test_nombres.py` (`choca`), `captacion/tests/test_db.py`
  (versión de migración si se comprueba).

Comandos (desde `captacion/`):
- Tests: `python -m unittest discover -s tests -t .` (en Windows fallan
  siempre 5: test_db ×2, TestEmbudoPrueba, TestServicio ×2).
- Lint: `ruff check .` si está disponible; `python -m py_compile` de lo tocado.

---

### Task 1: `nombres.choca`

**Files:** Modify `premier_captacion/nombres.py`; Test `tests/test_nombres.py`.

- [ ] Tests nuevos en `TestChoca` (datos inventados):
  - `choca("victorlopez@example.com", "Raul", None)` → True.
  - mismo correo con «Victor Lopez» → False; con «Vic» → False (no es pila).
  - `choca("danirojo@…", "Daniel", None)` → False (uno empieza por el otro).
  - `choca("rosalesmanuel@…", "Pedro Rosales", None)` → False (su apellido
    está en el correo).
  - correo sin nombre de pila (`xk81@…`) → False.
  - @usuario que casa con el correo (`puntos` da «usuario») → False.
- [ ] Ver que fallan; implementar `_pila_del_correo(letras)` (el nombre de
  `PILA` más largo por el que empieza) y `choca`; ver que pasan; commit.

### Task 2: `cruce.Datos` — candidatos y juicio

**Files:** Create `premier_captacion/cruce.py`; Test `tests/test_cruce.py`.

- [ ] Tests (`TestCandidatos`, `TestJuicio`) con los ayudantes de siempre
  (`venta`, `canal`, `persona`, `entra_movimiento`, `miembro`, `invitado`):
  - entra a +0 s y a +180 s → candidato; a +181 s o −5 s → no;
  - con la lista del enlace leída solo cuentan los de ese enlace; la entrada
    del registro de alguien que se fue también cuenta; enlace de otro
    producto no cuenta; canal desconocido → `None` (sin canal);
  - juicio: `buena`; `mala` si entró a +10 min; `mala` si el registro cubría
    la hora y no entró; `sin` si no hay registro y no está en el canal; `sin`
    si ya estaba dentro antes del pago.
- [ ] Implementar `Datos(con, solo_ventas=True, gratis=None)` con
  `ventas` (dicts de `pagos_overoption` + `canal_id`, `grupo`, `clave`),
  `candidatos(v)`, `juicio(v, uid)`, `grupos_de(correo)`, `ventas_de(correo)`,
  usando `pagos._mapa_canales`, `_canal_de_venta`, `_entradas_por_canal`,
  `_invitados_por_enlace` y el inicio del registro por canal. Commit.

### Task 3: `cruce.asignar` y `cruce.emparejar`

**Files:** Modify `premier_captacion/cruce.py`, `premier_captacion/pagos.py`; Test `tests/test_cruce.py`.

- [ ] Tests (`TestPorCompras`, `TestNombreQueChoca`, `TestManual`, `TestPorNombre`):
  - 3 buenas → todas las compras del correo `por_correo` (también una sin canal);
  - 2 buenas → ninguna con persona; la venta con un único candidato queda
    `dudosa_varios` con `posibles == [uid]` y `user_id` None;
  - 3 buenas + 1 mala (75 %) → no; 4 buenas + 1 mala (80 %) → sí;
  - sombra: otra persona con 3 buenas frente a 4 → no; con 2 → sí;
  - nadie paga dos veces: la persona ya tiene otro correo con ese canal → no
    sale en `posibles` ni se le asigna;
  - nombre que choca con 3 buenas → sin persona;
  - por nombre (nombre y apellido en el correo) → `por_nombre`; si otra
    persona tiene 3 buenas → no se aplica el nombre;
  - lo del dueño manda sobre 3 buenas de otra persona; «no» bloquea por
    compras y por nombre; vaciar la celda lo quita.
- [ ] Implementar `asignar(datos, manual, bloqueados, nombre_de)` y
  `calcular(con, ventana_s, solo_ventas, con_manual=True)` → objeto con
  `datos`, `dueno` {correo: (uid, origen)}, `resultados`, `mejor` {correo: uid};
  `emparejar(...)` devuelve `resultados` con las claves de siempre.
- [ ] `pagos.emparejar_ventas` delega en `cruce.emparejar`; quitar el código
  viejo del cruce y actualizar `_ESTADO_TEXTO`, `_ESTADO_CORTO` y el orden de
  `filas_pagos`.
- [ ] Repasar uno a uno los tests viejos de `test_cruce.py` que fallen: si
  prueban una regla que ya no existe (eliminación, un cruce suelto que da el
  correo, margen de 30 s) se borran; si prueban algo que sigue valiendo
  (pestañas, agregados, clientes) se adaptan sus datos a 3 buenas. Todo verde
  salvo los 5 de Windows. Commit.

### Task 4: `cruce.examen`

**Files:** Modify `premier_captacion/cruce.py`; Test `tests/test_cruce.py`.

- [ ] Test: con dos correos confirmados por el dueño (uno que el cruce
  acierta por compras y otro que no saca), `examen(con)` da
  `{"bien": n1, "mal": 0, "sin": n2, "correos_mal": []}`; y si el cruce da
  otra persona, cuenta `mal` y lista el correo.
- [ ] Implementar: verdad = `pagos._manuales`; cálculo con `con_manual=False`
  (sin lo del dueño ni sus «no»); comparar venta a venta.
  `python -m premier_captacion.cruce examen` (base en `CAPTACION_DB`, abierta
  en solo lectura) lo imprime. Commit.

### Task 5: `comprobacion` — estado por correo y pestaña

**Files:** Create `premier_captacion/comprobacion.py`; Modify `premier_captacion/pagos.py`; Test `tests/test_comprobacion.py`.

- [ ] Tests de `resumen_correo(juicios, origen)` (juicios = lista ordenada de
  `buena|mala|sin`): OK; «vigilar» por no llegar a 3 buenas (no si es del
  dueño) y por una mala suelta; «revisar» por 2 malas seguidas al final, por
  bajar del 80 % con ≥ 5 comprobables y por ninguna buena en las últimas 5
  compras; «sin asignar» sin persona; recuentos y motivo.
- [ ] Test de pestaña: `escribir_pestanas` crea «Correos · comprobación» con
  la cabecera, una fila por correo («revisar» arriba) y pinta de rojo sus filas.
- [ ] Implementar `estados(calculo)`, `filas(calculo, personas, tz)`,
  `escribir_pestana(libro, filas)`; llamarlo desde `pagos.escribir_pestanas`
  con un solo `calcular` por sincronización. Commit.

### Task 6: avisos

**Files:** Modify `premier_captacion/db.py`, `premier_captacion/comprobacion.py`, `premier_captacion/pagos.py`, `premier_captacion/sheet.py`; Test `tests/test_comprobacion.py`.

- [ ] Tests de `avisar_cambios(con, estados, avisar, ahora)` con un `avisar`
  falso que apunta los textos y devuelve True/False:
  - primera vez con 2 en «revisar»: un solo mensaje con «2»; no se repite;
  - después, un correo que cae a «revisar» → un mensaje con correo, persona
    y motivo; en la siguiente, nada;
  - vuelve a OK y cae otra vez → otro mensaje; pasar por «vigilar» no rearma;
  - si `avisar` devuelve False, se reintenta la siguiente vez;
  - `avisar=None` → no hace nada.
- [ ] Migración 11 (`pagos_avisos`: correo, ts); `avisar_cambios`;
  `aviso_por_bot(cfg)` (Bot API `sendMessage` al propietario; None sin token
  o propietario); `sheet.sincronizar(..., avisar=None)` lo pasa a
  `pagos.escribir_pestanas`, y `sheet.main` lo crea. Commit.

### Task 7: examen y medida en la base real, instalación

- [ ] Tests en local verdes (salvo los 5 de Windows), `ruff` y `py_compile`.
- [ ] Push. En la VM, con el tarball del commit en una carpeta temporal:
  tests, `cruce examen` sobre la base real (solo lectura) y recuento de
  estados («revisar», «vigilar», OK, sin asignar). Comparar con el cruce
  instalado: 287 bien, 2 mal, 431 sin persona.
- [ ] Si tiene más «mal», no se instala: se mira por qué. Si hay demasiados
  en «revisar» por ventas antiguas sin datos, se le enseña al dueño antes de
  activar los avisos.
- [ ] Instalar (`instalar.sh real`), comprobar la sincronización del Sheet en
  el journal y la pestaña nueva.
- [ ] Bitácora (sin datos de clientes) y README si cambia algo estructural.
