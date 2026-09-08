# Soporte para gemela y trío — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** El bot de Telegram reconoce apuestas de gemela/trío (1 carrera,
2-3 selecciones con orden, pagadas al dividendo oficial post-carrera, no
a una cuota fija), las guarda, las resuelve solas cuando llega el
dividendo, avisa por Telegram al registrar y al resolverse, y las cuenta
en el panel público.

**Architecture:** Hoja nueva `apuestas_exoticas` (paralela a
`apuestas`/`apuestas_patas`, sin fórmulas de hoja — la resolución la hace
una función de script, no un `ARRAYFORMULA`) más una hoja nueva
`resultados_gemela_trio` que alimenta un proyecto hermano (Proyecto
Galgos, VM) con el dividendo oficial de Racing Post — **ver "Dependencia
externa" más abajo, es una pieza que se monta en OTRO repo y NO bloquea
la mayoría de este plan**, que se puede implementar y probar sembrando
filas de prueba a mano en `resultados_gemela_trio`.

**Tech Stack:** Google Apps Script (V8), Google Sheets, API de Gemini
(extracción ya existente), Bot API de Telegram (ya existente).

**Caso real de prueba** (usado en varios tests de este plan): pick real
del 5-sept-2026, "GEMELA 3-4 Y 4-3 - STAKE 2 CADA UNA (STAKE 4 TOTAL)"
en 22:31 Star Pelaw (hora España). Resultado real: 1º trampa 4, 2º trampa
3 (combinación "4-3", una de las dos jugadas) → **acertada**, dividendo
oficial **7.42**, retorno `2×7.42=14.84u`, neto `14.84-4=+10.84u`.

---

## Dependencia externa (fuera de este plan, otro repo)

`resultados_gemela_trio` la rellena un job en la VM de Proyecto Galgos
(repo separado, `d:\Mis archivos\Documentos\Visual Studio Code\Proyecto
Galgos`, con su propio stack Python/systemd). Investigado el 2026-09-08:
el dato (`forecasts`/`tricasts` con el dividendo oficial) SÍ existe en la
respuesta que Racing Post ya devuelve a `src/scraper/scrape_results.py`
(confirmado en vivo contra la API real, ver
`docs/superpowers/specs/2026-09-08-gemela-trio-design.md`), pero el
pipeline que de verdad empuja datos a Sheets
(`/opt/picks-premier-galgos/vm_job_resultados_galgos.py`, SOLO EN LA VM,
no está en ningún repo git local) lee de un parquet
(`data/historical/results_enriched.parquet`) que construye
`automation/job_poll_results.py` → `sync_and_rebuild` (no investigado en
profundidad todavía — es un job de producción con historial de
incidentes reales por tocarlo sin cuidado, ver su propio docstring). Esa
parte necesita su PROPIO plan en el repo de Proyecto Galgos, con una
investigación previa de `sync_and_rebuild`/`etl_merge_results.py` antes
de escribir pasos concretos - no se hace aquí para no inventar detalles
sin verificar sobre un pipeline ajeno y frágil.

**Esto NO bloquea las Tareas 1-9 de este plan**: se prueban sembrando a
mano 1-2 filas en `resultados_gemela_trio` (Tarea 2 deja la hoja lista
para eso) con los datos reales del caso Star Pelaw.

---

## Archivos que se tocan (picks-premier-galgos)

- `src/Config.gs` — constantes de las 2 hojas nuevas.
- `src/Setup.gs` — creación de las 2 hojas nuevas.
- `src/Sheets.gs` — `appendApuestaExotica`.
- `src/AI.gs` — prompt ampliado + `extraerPickExotico`.
- `src/Main.gs` — rama en `manejarPickNuevo_`, `construirTextoConfirmacionExotica_`,
  `calcularResolucionExotica_`, `construirTextoResolucionExotica_`,
  `resolverApuestasExoticas`, `repararStarPelaw20260905`.
- `src/Dashboard.gs` — fusión en `getMetricasPanel()`.
- `src/Panel.html` — **sin cambios**: las filas de `apuestas_exoticas` se
  normalizan a la MISMA forma que ya consume `historicoPicks`, así que el
  cliente no necesita tocarse.

---

### Task 1: Config.gs — constantes de las hojas nuevas

**Files:**
- Modify: `src/Config.gs`

- [ ] **Step 1: Añadir las constantes**

Al final de `src/Config.gs`, después de `TASA_EUR_POR_UNIDAD`:

```javascript
const SHEET_APUESTAS_EXOTICAS = 'apuestas_exoticas';
const SHEET_RESULTADOS_GEMELA_TRIO = 'resultados_gemela_trio';

// gemela = acertar 1º y 2º de UNA carrera; trio = 1º, 2º y 3º. Se paga al
// dividendo oficial que publica la pista tras la carrera, no a una cuota
// pactada de antemano - por eso no hay columna `cuota` aquí como en
// `apuestas`. Ver docs/superpowers/specs/2026-09-08-gemela-trio-design.md.
const TIPOS_APUESTA_EXOTICA = ['gemela', 'trio'];

const COLUMNAS_APUESTAS_EXOTICAS = [
  'message_id', 'fecha_pick', 'tipo_apuesta', 'hipodromo', 'hora_carrera',
  'combinaciones', 'stake_total', 'stake_por_combinacion', 'resultado_final',
  'combinacion_acertada', 'dividendo', 'retorno_real', 'unidades_netas',
  'oculto', 'mensaje', 'confirm_message_id', 'creado_en',
];

// Solo la escribe el job de la VM de Proyecto Galgos (mismo patrón que
// resultados_galgos). tipo: 'forecast' (gemela) | 'tricast' (trio).
// pos1/pos2/pos3: trampas que de verdad quedaron en esas posiciones
// (pos3 vacío si tipo=forecast). dividendo: a stake de 1 unidad, mismo
// criterio que `cuota` en el resto del proyecto.
const COLUMNAS_RESULTADOS_GEMELA_TRIO = [
  'canodromo', 'fecha', 'hora', 'tipo', 'pos1', 'pos2', 'pos3', 'dividendo',
  'race_id', 'actualizado_en',
];
```

- [ ] **Step 2: Commit**

```bash
git add src/Config.gs
git commit -m "feat: constantes de config para apuestas_exoticas y resultados_gemela_trio"
```

---

### Task 2: Setup.gs — crear las dos hojas nuevas

**Files:**
- Modify: `src/Setup.gs`

- [ ] **Step 1: Añadir las dos funciones de creación**

Después de `crearResultadosGalgos_` en `src/Setup.gs`:

```javascript
function crearApuestasExoticas_(ss) {
  const sheet = ss.getSheetByName(SHEET_APUESTAS_EXOTICAS) || ss.insertSheet(SHEET_APUESTAS_EXOTICAS);
  sheet.clear();
  sheet.getRange(1, 1, 1, COLUMNAS_APUESTAS_EXOTICAS.length).setValues([COLUMNAS_APUESTAS_EXOTICAS]);
  sheet.setFrozenRows(1);
}

function crearResultadosGemelaTrio_(ss) {
  const sheet = ss.getSheetByName(SHEET_RESULTADOS_GEMELA_TRIO) || ss.insertSheet(SHEET_RESULTADOS_GEMELA_TRIO);
  sheet.clear();
  sheet.getRange(1, 1, 1, COLUMNAS_RESULTADOS_GEMELA_TRIO.length).setValues([COLUMNAS_RESULTADOS_GEMELA_TRIO]);
  sheet.setFrozenRows(1);
}
```

Sin columnas fórmula (a diferencia de `apuestas`/`apuestas_patas`): la
resolución la hace `resolverApuestasExoticas` (Tarea 6), no un
`ARRAYFORMULA` — mucho más simple de crear.

- [ ] **Step 2: Llamarlas desde `setupSheet()`**

En `src/Setup.gs`, la función `setupSheet()` queda así:

```javascript
function setupSheet() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  crearMensajesCrudos_(ss);
  crearApuestasPatas_(ss);
  crearApuestas_(ss);
  crearResultadosGalgos_(ss);
  crearApuestasExoticas_(ss);
  crearResultadosGemelaTrio_(ss);
  borrarHojaPorDefecto_(ss);
  Logger.log('Listo: mensajes_crudos, apuestas_patas, apuestas, resultados_galgos, ' +
    'apuestas_exoticas y resultados_gemela_trio creadas.');
}
```

- [ ] **Step 3: Subir y crear las hojas en la hoja real**

```bash
clasp push
```

En el editor de Apps Script: Setup.gs → desplegable de funciones →
`setupSheet` → Ejecutar. **Ojo**: `setupSheet()` hace `sheet.clear()` en
TODAS las hojas que gestiona, incluidas `apuestas`/`apuestas_patas` que ya
tienen datos reales — para no perderlos, en vez de ejecutar `setupSheet`
entera, ejecuta solo las dos funciones nuevas a mano desde el mismo
desplegable: `crearApuestasExoticas_`... **espera**, esas llevan `_` al
final (privadas, no aparecen en el desplegable, ver el bug ya conocido de
este proyecto). Dos opciones: (a) crear una función temporal sin `_` que
las llame a las dos y bórrala después de ejecutarla una vez, o (b)
crearlas a mano desde la interfaz de Sheets (Insertar > Hoja, y pegar la
fila de cabeceras de `COLUMNAS_APUESTAS_EXOTICAS`/
`COLUMNAS_RESULTADOS_GEMELA_TRIO` en la fila 1). Usa la opción (a):

```javascript
function crearHojasExoticasUnaVez() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  crearApuestasExoticas_(ss);
  crearResultadosGemelaTrio_(ss);
  Logger.log('Listo: apuestas_exoticas y resultados_gemela_trio creadas.');
}
```

Añádela temporalmente al final de `Setup.gs`, `clasp push`, ejecútala
desde el editor, confirma en el Registro de ejecución el mensaje "Listo:
...", y BÓRRALA de `Setup.gs` antes de seguir (no debe quedar en el
repo - era solo para esta ejecución única).

- [ ] **Step 4: Verificar a mano**

Abre la hoja de cálculo real, confirma que existen las pestañas
`apuestas_exoticas` y `resultados_gemela_trio`, cada una con su fila de
cabeceras exacta (compárala con `COLUMNAS_APUESTAS_EXOTICAS`/
`COLUMNAS_RESULTADOS_GEMELA_TRIO` de `Config.gs`).

- [ ] **Step 5: Sembrar la fila de prueba (para las Tareas 6-9 sin depender de la VM)**

En `resultados_gemela_trio`, añade a mano esta fila (datos reales del
caso Star Pelaw, verificados en vivo contra Racing Post):

| canodromo | fecha | hora | tipo | pos1 | pos2 | pos3 | dividendo | race_id | actualizado_en |
|---|---|---|---|---|---|---|---|---|---|
| Star Pelaw | 05/09/2026 | 22:31 | forecast | 4 | 3 | | 7.42 | 2222093 | (fecha de hoy) |

- [ ] **Step 6: Commit**

```bash
git add src/Setup.gs
git commit -m "feat: crear hojas apuestas_exoticas y resultados_gemela_trio"
```

---

### Task 3: Sheets.gs — guardar una apuesta exótica

**Files:**
- Modify: `src/Sheets.gs`

- [ ] **Step 1: Añadir `appendApuestaExotica`**

Después de `mensajeCrudoYaExiste` en `src/Sheets.gs` (reutiliza
`appendRowByHeader_`, que ya funciona para cualquier hoja con columna
`message_id` - `clonarFormulasDeApuestas_` ya hace no-op para hojas que
no sean `apuestas`/`apuestas_patas`, confirmado leyendo su código):

```javascript
/**
 * Guarda 1 fila en `apuestas_exoticas` (gemela/trío). A diferencia de
 * appendApuestaConPatas, no hay tabla de patas aparte - es 1 sola
 * carrera con varias combinaciones, cabe entera en una fila.
 */
function appendApuestaExotica(messageId, fechaPick, tipoApuesta, hipodromo, horaCarrera,
    combinaciones, stakeTotal, stakePorCombinacion, mensaje) {
  const sheet = getSheet_(SHEET_APUESTAS_EXOTICAS);
  return appendRowByHeader_(sheet, {
    message_id: messageId,
    fecha_pick: fechaPick,
    tipo_apuesta: tipoApuesta,
    hipodromo: hipodromo,
    hora_carrera: horaCarrera,
    combinaciones: combinaciones.map(function (c) { return c.join('-'); }).join(';'),
    stake_total: stakeTotal,
    stake_por_combinacion: stakePorCombinacion,
    resultado_final: 'pendiente',
    oculto: false,
    mensaje: mensaje,
  });
}

function setApuestaExoticaConfirmMessageId(fila, confirmMessageId) {
  const sheet = getSheet_(SHEET_APUESTAS_EXOTICAS);
  const index = getHeaderIndex_(sheet);
  sheet.getRange(fila, index['confirm_message_id'] + 1).setValue(confirmMessageId);
}

function findApuestaExoticaByMessageIdRecienCreada_(messageId) {
  const sheet = getSheet_(SHEET_APUESTAS_EXOTICAS);
  const index = getHeaderIndex_(sheet);
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) return null;
  const ids = sheet.getRange(2, index['message_id'] + 1, lastRow - 1, 1).getValues();
  for (let i = 0; i < ids.length; i++) {
    if (String(ids[i][0]) === String(messageId)) return { row: i + 2 };
  }
  return null;
}
```

- [ ] **Step 2: Subir y probar a mano desde el editor**

```bash
clasp push
```

En el editor, añade temporalmente esta función de prueba en `Sheets.gs`,
ejecútala, comprueba en la hoja `apuestas_exoticas` que aparece 1 fila
nueva con `combinaciones = "3-4;4-3"`, y BÓRRALA después de confirmarlo:

```javascript
function pruebaManualAppendApuestaExotica() {
  const fila = appendApuestaExotica('999999', new Date(), 'gemela', 'Star Pelaw', '22:31',
    [['3', '4'], ['4', '3']], 4, 2, 'texto de prueba');
  Logger.log('Fila escrita: ' + fila);
}
```

- [ ] **Step 3: Commit**

```bash
git add src/Sheets.gs
git commit -m "feat: appendApuestaExotica para guardar gemela/trio en su propia hoja"
```

---

### Task 4: AI.gs — reconocer gemela/trío en la extracción

**Files:**
- Modify: `src/AI.gs`

- [ ] **Step 1: Ampliar `EXTRACTION_SYSTEM_PROMPT`**

En `src/AI.gs`, dentro del array que forma `EXTRACTION_SYSTEM_PROMPT`,
después de la línea de `'tipo_apuesta': "simple" | "doble" | "triple" | "otro"`
en la definición del JSON, cambia esa línea y añade las nuevas:

```javascript
const EXTRACTION_SYSTEM_PROMPT = [
  'Extraes datos estructurados de picks de apuestas de galgos (carreras de',
  'perros) enviados por un tipster a un grupo de Telegram. El texto puede',
  'venir con erratas (p. ej. "Ciota" en vez de "Cuota", o ";" en vez de ":"',
  'en la hora) - interprétalas igualmente si el significado es claro.',
  '',
  'Un pick puede ser una apuesta SIMPLE (1 carrera), una combinada de',
  'varias carreras con una sola cuota conjunta ("Apuesta Doble" = 2',
  'carreras, "Apuesta Tríple" = 3 carreras), o una GEMELA/TRÍO: acertar el',
  'ORDEN de llegada de 2 (gemela) o 3 (trío) galgos de UNA SOLA carrera.',
  'Una gemela/trío NO lleva cuota - se paga al dividendo oficial que',
  'publica la pista después de la carrera, así que "cuota" va a null en',
  'ese caso.',
  '',
  'Formato de gemela/trío en el texto: números de trampa separados por',
  'guion, indicando el orden ("3-4" = 3 primero, 4 segundo). Si aparece',
  'más de una combinación de orden (ej. "3-4 Y 4-3"), son varias jugadas',
  'a la vez con el mismo stake repartido - inclúyelas todas en',
  '"combinaciones". Si el texto dice "REVERSIBLE" sin desglosar (ej.',
  '"GEMELA REVERSIBLE 3-4"), tú mismo genera las combinaciones: para',
  'gemela reversible son las 2 permutaciones (3-4 y 4-3); para trío',
  'reversible, si no se desglosa, pon "tipo_apuesta":"otro" (no lo',
  'adivines con 6 combinaciones, es un caso raro que no se ha visto en la',
  'práctica).',
  '',
  'Cada carrera de una combinada (simple/doble/triple) es una "pata":',
  'mismo formato que una apuesta simple (hipódromo, hora, trampa,',
  'selección), una tras otra en el texto.',
  '',
  'Devuelve SOLO un JSON con esta forma exacta, sin texto adicional:',
  '{',
  '  "tipo_apuesta": "simple" | "doble" | "triple" | "gemela" | "trio" | "otro",',
  '  "patas": [',
  '    { "hipodromo": string o null, "hora_carrera": string "HH:MM" o null,',
  '      "trampa": string (solo el número) o null,',
  '      "seleccion": string (nombre del galgo) o null }',
  '  ],',
  '  "hipodromo_exotica": string o null,',
  '  "hora_carrera_exotica": string "HH:MM" o null,',
  '  "combinaciones": [["3","4"],["4","3"]] o null,',
  '  "cuota": number o null,',
  '  "stake": number o null',
  '}',
  '',
  'Reglas:',
  '- "tipo_apuesta": "simple" si es 1 sola carrera, "doble" si son 2,',
  '  "triple" si son 3, "gemela"/"trio" si es una apuesta de orden de UNA',
  '  carrera. Si es cualquier otra cosa (Trixie, Yankee, apuesta',
  '  "a puesto"/colocado, 4+ carreras, trío reversible sin desglosar, o no',
  '  estás seguro del tipo), pon "otro" - en ese caso rellena "patas" o',
  '  "combinaciones" con lo que puedas identificar de todas formas (ayuda',
  '  a la revisión manual), no lo dejes vacío si hay datos reconocibles.',
  '- Si "tipo_apuesta" es "simple"/"doble"/"triple": rellena "patas" (1, 2',
  '  o 3 elementos), deja "hipodromo_exotica"/"hora_carrera_exotica"/',
  '  "combinaciones" a null.',
  '- Si "tipo_apuesta" es "gemela"/"trio": rellena "hipodromo_exotica",',
  '  "hora_carrera_exotica" y "combinaciones" (cada combinación con 2',
  '  elementos para gemela, 3 para trío), deja "patas" como array vacío y',
  '  "cuota" a null.',
  '- "cuota" y "stake" son SIEMPRE los de la apuesta conjunta entera (la',
  '  única cuota y el único stake que aparecen en el mensaje), nunca por',
  '  carrera - no hay una cuota distinta por pata. Para gemela/trío,',
  '  "stake" es el TOTAL sumando todas las combinaciones (ej. "stake 2',
  '  cada una, 4 total" -> stake=4).',
  '- La palabra "Galgo" antes del número de trampa es opcional, ignórala.',
  '- El hipódromo y la hora de cada carrera pueden aparecer en cualquier',
  '  orden en su línea.',
  '- Si un campo no aparece o no estás seguro, ponlo a null. No inventes',
  '  valores.',
].join('\n');
```

- [ ] **Step 2: Añadir `NUM_TRAMPAS_POR_TIPO_EXOTICA` y `extraerPickExotico_`**

Después de `NUM_PATAS_POR_TIPO` en `src/AI.gs`:

```javascript
const NUM_TRAMPAS_POR_TIPO_EXOTICA = { gemela: 2, trio: 3 };

/**
 * Valida el JSON ya extraído por Gemini para gemela/trío (misma idea que
 * las comprobaciones de extraerPick, pero para el esquema de
 * combinaciones en vez de patas). No llama a la IA - función pura,
 * testeable con un objeto ya construido a mano.
 */
function validarExtraccionExotica_(extraido) {
  const numEsperado = NUM_TRAMPAS_POR_TIPO_EXOTICA[extraido.tipo_apuesta];
  const combinaciones = extraido.combinaciones || [];

  if (combinaciones.length === 0) {
    return { ok: false, motivo: 'faltan_campos', camposFaltantes: ['combinaciones'] };
  }
  const todasLongitudCorrecta = combinaciones.every(function (c) { return c.length === numEsperado; });
  if (!todasLongitudCorrecta) {
    return { ok: false, motivo: 'num_patas_incorrecto' };
  }

  const camposFaltantes = [];
  if (!extraido.hipodromo_exotica) camposFaltantes.push('hipodromo_exotica');
  if (!extraido.hora_carrera_exotica) camposFaltantes.push('hora_carrera_exotica');
  if (extraido.stake === null || extraido.stake === undefined || extraido.stake === '') {
    camposFaltantes.push('stake');
  }
  if (camposFaltantes.length > 0) {
    return { ok: false, motivo: 'faltan_campos', camposFaltantes: camposFaltantes };
  }

  return {
    ok: true,
    esExotica: true,
    tipoApuesta: extraido.tipo_apuesta,
    hipodromo: extraido.hipodromo_exotica,
    horaCarrera: extraido.hora_carrera_exotica,
    combinaciones: combinaciones.map(function (c) { return c.map(String); }),
    stakeTotal: Number(extraido.stake),
    stakePorCombinacion: redondear2_(Number(extraido.stake) / combinaciones.length),
  };
}
```

- [ ] **Step 3: Ramificar `extraerPick`**

En `src/AI.gs`, al principio de `extraerPick` (antes de la comprobación
de `TIPOS_APUESTA_SOPORTADOS`), añade la rama de exóticas:

```javascript
function extraerPick(texto, fotoBlob) {
  const extraido = callGeminiExtraction_(texto, fotoBlob);

  if (TIPOS_APUESTA_EXOTICA.indexOf(extraido.tipo_apuesta) !== -1) {
    return validarExtraccionExotica_(extraido);
  }

  if (TIPOS_APUESTA_SOPORTADOS.indexOf(extraido.tipo_apuesta) === -1) {
    return { ok: false, motivo: 'tipo_no_soportado', tipoApuesta: extraido.tipo_apuesta };
  }
  // ... resto de la función sin cambios
```

- [ ] **Step 4: Test de `validarExtraccionExotica_` (sin llamar a Gemini)**

Después de `validarExtraccionExotica_`, añade su test (mismo patrón que
el resto del proyecto - `test_xxx` sin guion bajo final para que aparezca
en el desplegable de "Ejecutar"):

```javascript
function test_validarExtraccionExotica() {
  // Caso real: "GEMELA 3-4 Y 4-3 - STAKE 2 CADA UNA (STAKE 4 TOTAL)" en Star Pelaw 22:31.
  const real = validarExtraccionExotica_({
    tipo_apuesta: 'gemela',
    hipodromo_exotica: 'Star Pelaw',
    hora_carrera_exotica: '22:31',
    combinaciones: [['3', '4'], ['4', '3']],
    cuota: null,
    stake: 4,
  });
  assertIguales_(real.ok, true, 'gemela con todos los campos -> ok');
  assertIguales_(real.tipoApuesta, 'gemela', 'tipoApuesta pasa tal cual');
  assertIguales_(real.combinaciones.length, 2, 'las 2 combinaciones (3-4 y 4-3)');
  assertIguales_(real.stakeTotal, 4, 'stakeTotal = 4');
  assertIguales_(real.stakePorCombinacion, 2, 'stakePorCombinacion = 4/2 = 2');

  const trioMalFormado = validarExtraccionExotica_({
    tipo_apuesta: 'trio',
    hipodromo_exotica: 'Harlow',
    hora_carrera_exotica: '19:00',
    combinaciones: [['1', '2']], // solo 2 trampas, un trio necesita 3
    stake: 6,
  });
  assertIguales_(trioMalFormado.ok, false, 'trio con combinacion de 2 trampas -> mal formado');
  assertIguales_(trioMalFormado.motivo, 'num_patas_incorrecto', 'motivo correcto');

  const sinStake = validarExtraccionExotica_({
    tipo_apuesta: 'gemela',
    hipodromo_exotica: 'Harlow',
    hora_carrera_exotica: '19:00',
    combinaciones: [['1', '2']],
    stake: null,
  });
  assertIguales_(sinStake.ok, false, 'sin stake -> faltan_campos');
  assertIguales_(sinStake.camposFaltantes.indexOf('stake') !== -1, true, 'stake en la lista de faltantes');

  Logger.log('test_validarExtraccionExotica: OK, todas las comprobaciones pasaron.');
}
```

- [ ] **Step 5: Subir y ejecutar el test**

```bash
clasp push
```

Editor → AI.gs → `test_validarExtraccionExotica` → Ejecutar → Registro de
ejecución debe decir `OK, todas las comprobaciones pasaron.`. Si falla,
NO sigas a la Tarea 5 hasta que pase.

- [ ] **Step 6: Commit**

```bash
git add src/AI.gs
git commit -m "feat: reconocer gemela/trio en la extraccion con IA"
```

---

### Task 5: Main.gs — registrar el pick y confirmar por Telegram

**Files:**
- Modify: `src/Main.gs`

- [ ] **Step 1: Añadir `construirTextoConfirmacionExotica_`**

Después de `construirTextoConfirmacion_` en `src/Main.gs`:

```javascript
/**
 * Mensaje de confirmación al registrar una gemela/trío - sin cuota (no se
 * sabe hasta que se resuelve), a diferencia de construirTextoConfirmacion_.
 */
function construirTextoConfirmacionExotica_(resultado) {
  const combos = resultado.combinaciones.map(function (c) { return 'T' + c.join('-T'); }).join(' y ');
  return 'Apuesta registrada (' + resultado.tipoApuesta + '): ' + resultado.horaCarrera + ' ' +
    resultado.hipodromo + ' - ' + combos + ' (stake ' + resultado.stakePorCombinacion +
    'u cada una, ' + resultado.stakeTotal + 'u total)';
}
```

- [ ] **Step 2: Test con el caso real**

```javascript
function test_construirTextoConfirmacionExotica() {
  const texto = construirTextoConfirmacionExotica_({
    tipoApuesta: 'gemela',
    horaCarrera: '22:31',
    hipodromo: 'Star Pelaw',
    combinaciones: [['3', '4'], ['4', '3']],
    stakePorCombinacion: 2,
    stakeTotal: 4,
  });
  assertIguales_(texto, 'Apuesta registrada (gemela): 22:31 Star Pelaw - T3-T4 y T4-T3 (stake 2u cada una, 4u total)',
    'texto exacto del caso real Star Pelaw');
  Logger.log('test_construirTextoConfirmacionExotica: OK, todas las comprobaciones pasaron.');
}
```

- [ ] **Step 3: Subir y ejecutar el test**

```bash
clasp push
```

Editor → Main.gs → `test_construirTextoConfirmacionExotica` → Ejecutar →
debe dar `OK`.

- [ ] **Step 4: Ramificar `manejarPickNuevo_`**

En `src/Main.gs`, dentro de `manejarPickNuevo_`, justo después de que
`resultado.ok` sea `true` y ANTES del bloque que llama a
`appendApuestaConPatas` (que es solo para simple/doble/triple):

```javascript
function manejarPickNuevo_(msg, texto, fotoFileId, fechaRecibido, fechaForward) {
  let fotoBlob = null;
  let resultado;
  try {
    if (fotoFileId) {
      fotoBlob = downloadTelegramPhoto(fotoFileId);
    }
    resultado = extraerPick(texto, fotoBlob);
  } catch (err) {
    Logger.log('Fallo procesando el pick (descarga de foto o IA de extracción): ' + err);
    actualizarEstadoMensajeCrudo_(msg.message_id, ESTADO_ERROR);
    sendTelegramMessage(msg.chat.id,
      'No he podido procesar este pick ahora mismo (fallo técnico al leerlo). Lo tengo guardado y lo ' +
      'reintentaré yo solo en un rato - no hace falta que hagas nada.',
      msg.message_id);
    return;
  }

  if (!resultado.ok) {
    actualizarEstadoMensajeCrudo_(msg.message_id, ESTADO_REVISION_MANUAL);
    sendTelegramMessage(msg.chat.id,
      'Pick guardado pero necesita revisión manual: ' + motivoRevisionManual_(resultado) + '.',
      msg.message_id);
    return;
  }

  const fechaPick = fechaForward || fechaRecibido;

  if (resultado.esExotica) {
    appendApuestaExotica(msg.message_id, fechaPick, resultado.tipoApuesta, resultado.hipodromo,
      resultado.horaCarrera, resultado.combinaciones, resultado.stakeTotal,
      resultado.stakePorCombinacion, texto);
    actualizarEstadoMensajeCrudo_(msg.message_id, ESTADO_PROCESADO);

    const textoConfirmacionExotica = construirTextoConfirmacionExotica_(resultado);
    const confirmMessageIdExotica = sendTelegramMessage(msg.chat.id, textoConfirmacionExotica, msg.message_id);
    if (confirmMessageIdExotica) {
      const filaExotica = findApuestaExoticaByMessageIdRecienCreada_(msg.message_id);
      if (filaExotica) setApuestaExoticaConfirmMessageId(filaExotica.row, confirmMessageIdExotica);
    }
    return;
  }

  appendApuestaConPatas(msg.message_id, fechaPick, resultado.tipoApuesta, resultado.cuota, resultado.stake, resultado.patas);
  actualizarEstadoMensajeCrudo_(msg.message_id, ESTADO_PROCESADO);

  const textoConfirmacion = construirTextoConfirmacion_(resultado);
  const confirmMessageId = sendTelegramMessage(msg.chat.id, textoConfirmacion, msg.message_id);

  if (confirmMessageId) {
    const fila = findApuestaByMessageIdRecienCreada_(msg.message_id);
    if (fila) {
      setApuestaConfirmMessageId(fila.row, confirmMessageId);
    }
  }
}
```

- [ ] **Step 5: Subir**

```bash
clasp push
```

- [ ] **Step 6: Commit**

```bash
git add src/Main.gs
git commit -m "feat: registrar gemela/trio y confirmar por Telegram"
```

---

### Task 6: Main.gs — resolver la gemela/trío cuando llega el dividendo

**Files:**
- Modify: `src/Main.gs`

- [ ] **Step 1: Escribir `calcularResolucionExotica_` (función pura)**

Después de `construirTextoConfirmacionExotica_`:

```javascript
/**
 * combinaciones: array de arrays de string de trampa, ej. [['3','4'],['4','3']].
 * resultadoCarrera: {pos1, pos2, pos3, dividendo} o null si `resultados_gemela_trio`
 * todavía no tiene fila para esa carrera+tipo.
 * Devuelve {resultado:'pendiente'} o {resultado:'gano'|'perdio', resultadoReal, combinacionAcertada?, dividendo?}.
 */
function calcularResolucionExotica_(combinaciones, resultadoCarrera) {
  if (!resultadoCarrera) return { resultado: 'pendiente' };

  const posiciones = [resultadoCarrera.pos1, resultadoCarrera.pos2, resultadoCarrera.pos3]
    .filter(function (p) { return p !== '' && p !== null && p !== undefined; })
    .map(String);
  const resultadoReal = posiciones.join('-');

  const acertada = combinaciones.filter(function (combo) {
    return combo.length === posiciones.length &&
      combo.every(function (trampa, i) { return String(trampa) === posiciones[i]; });
  })[0];

  if (acertada) {
    return {
      resultado: 'gano',
      resultadoReal: resultadoReal,
      combinacionAcertada: acertada.join('-'),
      dividendo: Number(resultadoCarrera.dividendo),
    };
  }
  return { resultado: 'perdio', resultadoReal: resultadoReal };
}
```

- [ ] **Step 2: Test con el caso real (acierto, fallo y pendiente)**

```javascript
function test_calcularResolucionExotica() {
  // Caso real: acierta la combinacion "4-3".
  const acierto = calcularResolucionExotica_(
    [['3', '4'], ['4', '3']],
    { pos1: '4', pos2: '3', pos3: '', dividendo: '7.42' }
  );
  assertIguales_(acierto.resultado, 'gano', 'gemela reversible: 4-3 coincide con una combinacion jugada');
  assertIguales_(acierto.combinacionAcertada, '4-3', 'combinacionAcertada es la que realmente coincidio');
  assertIguales_(acierto.dividendo, 7.42, 'dividendo viene de resultadoCarrera');
  assertIguales_(acierto.resultadoReal, '4-3', 'resultadoReal refleja lo que paso de verdad');

  const fallo = calcularResolucionExotica_(
    [['3', '4']],
    { pos1: '5', pos2: '2', pos3: '', dividendo: '10.00' }
  );
  assertIguales_(fallo.resultado, 'perdio', 'ninguna combinacion jugada coincide -> perdio');
  assertIguales_(fallo.resultadoReal, '5-2', 'resultadoReal informa que gano el 5-2');

  const pendiente = calcularResolucionExotica_([['1', '2', '3']], null);
  assertIguales_(pendiente.resultado, 'pendiente', 'sin fila de resultado todavia -> pendiente');

  Logger.log('test_calcularResolucionExotica: OK, todas las comprobaciones pasaron.');
}
```

- [ ] **Step 3: Subir y ejecutar el test**

```bash
clasp push
```

Editor → Main.gs → `test_calcularResolucionExotica` → Ejecutar → `OK`.

- [ ] **Step 4: Escribir `construirTextoResolucionExotica_`**

```javascript
/**
 * Mensaje de resolución (✅/❌) de una gemela/trío. `pick` = fila de
 * apuestas_exoticas ya leída {tipoApuesta, horaCarrera, hipodromo,
 * stakeTotal, stakePorCombinacion}; `resolucion` = lo que devuelve
 * calcularResolucionExotica_ (resultado 'gano' o 'perdio', nunca
 * 'pendiente' - no se llama a esta función si sigue pendiente).
 */
function construirTextoResolucionExotica_(pick, resolucion) {
  const nombre = pick.tipoApuesta === 'trio' ? 'Trío' : 'Gemela';
  const etiqueta = function (combo) { return 'T' + combo.split('-').join('-T'); };

  if (resolucion.resultado === 'gano') {
    const retorno = redondear2_(pick.stakePorCombinacion * resolucion.dividendo);
    const neto = redondear2_(retorno - pick.stakeTotal);
    return '✅ ' + nombre + ' acertada — ' + pick.horaCarrera + ' ' + pick.hipodromo + ': ganó ' +
      etiqueta(resolucion.combinacionAcertada) + ', dividendo ' + resolucion.dividendo +
      ', retorno ' + retorno + 'u (' + (neto >= 0 ? '+' : '') + neto + 'u)';
  }
  return '❌ ' + nombre + ' perdida — ' + pick.horaCarrera + ' ' + pick.hipodromo +
    ' (ganó ' + etiqueta(resolucion.resultadoReal) + ')';
}
```

- [ ] **Step 5: Test con el caso real**

```javascript
function test_construirTextoResolucionExotica() {
  const pick = { tipoApuesta: 'gemela', horaCarrera: '22:31', hipodromo: 'Star Pelaw', stakeTotal: 4, stakePorCombinacion: 2 };

  const textoGano = construirTextoResolucionExotica_(pick, {
    resultado: 'gano', resultadoReal: '4-3', combinacionAcertada: '4-3', dividendo: 7.42,
  });
  assertIguales_(textoGano, '✅ Gemela acertada — 22:31 Star Pelaw: ganó T4-T3, dividendo 7.42, retorno 14.84u (+10.84u)',
    'texto exacto de acierto del caso real Star Pelaw');

  const textoPerdio = construirTextoResolucionExotica_(pick, { resultado: 'perdio', resultadoReal: '1-3' });
  assertIguales_(textoPerdio, '❌ Gemela perdida — 22:31 Star Pelaw (ganó T1-T3)', 'texto exacto de fallo');

  Logger.log('test_construirTextoResolucionExotica: OK, todas las comprobaciones pasaron.');
}
```

- [ ] **Step 6: Subir y ejecutar el test**

```bash
clasp push
```

Editor → Main.gs → `test_construirTextoResolucionExotica` → Ejecutar → `OK`.

- [ ] **Step 7: Escribir el job de resolución `resolverApuestasExoticas`**

Mismo patrón que `reintentarMensajesConError`: lee todas las
`apuestas_exoticas` pendientes, busca su carrera en
`resultados_gemela_trio`, resuelve y avisa.

```javascript
/**
 * Job periódico (mismo patrón que reintentarMensajesConError): resuelve
 * las apuestas_exoticas pendientes contra resultados_gemela_trio y avisa
 * por Telegram. Ejecutar a mano desde el editor, o instalar un trigger
 * (ver configurarTriggerReintentos - se añade su propio trigger en el
 * Step 8 de esta tarea).
 */
function resolverApuestasExoticas() {
  const lock = LockService.getScriptLock();
  try {
    lock.waitLock(120000);
  } catch (err) {
    Logger.log('resolverApuestasExoticas: no se pudo adquirir el lock - ' + err);
    return;
  }

  try {
    const sheet = getSheet_(SHEET_APUESTAS_EXOTICAS);
    const index = getHeaderIndex_(sheet);
    const lastRow = sheet.getLastRow();
    if (lastRow < 2) {
      Logger.log('resolverApuestasExoticas: apuestas_exoticas vacia, nada que hacer.');
      return;
    }

    const sheetResultados = getSheet_(SHEET_RESULTADOS_GEMELA_TRIO);
    const indexResultados = getHeaderIndex_(sheetResultados);
    const lastRowResultados = sheetResultados.getLastRow();
    const filasResultados = lastRowResultados < 2 ? [] :
      sheetResultados.getRange(2, 1, lastRowResultados - 1, sheetResultados.getLastColumn()).getValues();

    // Índice canodromo|fecha|hora|tipo -> {pos1,pos2,pos3,dividendo}, mismo
    // criterio de normalización que ya usa Auditoria.gs para cruzar carreras.
    const resultadosPorCarrera = {};
    filasResultados.forEach(function (r) {
      const key = normalizarTexto_(r[indexResultados['canodromo']]) + '|' +
        normalizarFechaISO_(r[indexResultados['fecha']]) + '|' +
        normalizarHoraSegundos_(r[indexResultados['hora']]) + '|' +
        r[indexResultados['tipo']];
      resultadosPorCarrera[key] = {
        pos1: r[indexResultados['pos1']], pos2: r[indexResultados['pos2']], pos3: r[indexResultados['pos3']],
        dividendo: r[indexResultados['dividendo']],
      };
    });

    const datos = sheet.getRange(2, 1, lastRow - 1, sheet.getLastColumn()).getValues();
    let resueltos = 0;

    for (let i = 0; i < datos.length; i++) {
      const fila = datos[i];
      if (fila[index['resultado_final']] !== 'pendiente') continue;

      const messageId = fila[index['message_id']];
      const tipoApuesta = fila[index['tipo_apuesta']];
      const hipodromo = fila[index['hipodromo']];
      const horaCarrera = fila[index['hora_carrera']];
      const fechaPick = fila[index['fecha_pick']];
      const combinaciones = String(fila[index['combinaciones']]).split(';').map(function (c) { return c.split('-'); });
      const stakeTotal = fila[index['stake_total']];
      const stakePorCombinacion = fila[index['stake_por_combinacion']];

      const tipoResultado = tipoApuesta === 'trio' ? 'tricast' : 'forecast';
      const key = normalizarTexto_(hipodromo) + '|' + normalizarFechaISO_(fechaPick) + '|' +
        normalizarHoraSegundos_(horaCarrera) + '|' + tipoResultado;
      const resolucion = calcularResolucionExotica_(combinaciones, resultadosPorCarrera[key] || null);

      if (resolucion.resultado === 'pendiente') continue;

      const retornoReal = resolucion.resultado === 'gano' ? redondear2_(stakePorCombinacion * resolucion.dividendo) : 0;
      const unidadesNetas = redondear2_(retornoReal - stakeTotal);
      const filaSheet = i + 2;

      sheet.getRange(filaSheet, index['resultado_final'] + 1).setValue(resolucion.resultado);
      sheet.getRange(filaSheet, index['combinacion_acertada'] + 1).setValue(resolucion.combinacionAcertada || '');
      sheet.getRange(filaSheet, index['dividendo'] + 1).setValue(resolucion.dividendo || '');
      sheet.getRange(filaSheet, index['retorno_real'] + 1).setValue(retornoReal);
      sheet.getRange(filaSheet, index['unidades_netas'] + 1).setValue(unidadesNetas);

      const pick = { tipoApuesta: tipoApuesta, horaCarrera: horaCarrera, hipodromo: hipodromo,
        stakeTotal: stakeTotal, stakePorCombinacion: stakePorCombinacion };
      sendTelegramMessage(TELEGRAM_CHAT_ID, construirTextoResolucionExotica_(pick, resolucion), messageId);
      resueltos++;
    }

    Logger.log('resolverApuestasExoticas: ' + resueltos + ' resuelta(s).');
  } finally {
    lock.releaseLock();
  }
}
```

- [ ] **Step 8: Instalar el trigger periódico**

```javascript
/**
 * Ejecutar UNA VEZ a mano desde el editor para instalar el disparador
 * periódico - mismo patrón que configurarTriggerReintentos.
 */
function configurarTriggerResolverExoticas() {
  ScriptApp.getProjectTriggers().forEach(function (t) {
    if (t.getHandlerFunction() === 'resolverApuestasExoticas') {
      ScriptApp.deleteTrigger(t);
    }
  });
  ScriptApp.newTrigger('resolverApuestasExoticas').timeBased().everyHours(2).create();
  Logger.log('Disparador instalado: resolverApuestasExoticas cada 2 horas.');
}
```

- [ ] **Step 9: Subir, probar contra la fila sembrada en la Tarea 2, y activar el trigger**

```bash
clasp push
```

Editor → Main.gs → `resolverApuestasExoticas` → Ejecutar. Como todavía no
hay ninguna fila real en `apuestas_exoticas` (eso llega en la Tarea 8),
el Registro de ejecución dirá `0 resuelta(s)` - normal, confírmalo sin
error. Después, `configurarTriggerResolverExoticas` → Ejecutar → confirma
`Disparador instalado`.

- [ ] **Step 10: Commit**

```bash
git add src/Main.gs
git commit -m "feat: resolver gemela/trio contra resultados_gemela_trio y avisar por Telegram"
```

---

### Task 7: Dashboard.gs — que cuenten en el panel público

**Files:**
- Modify: `src/Dashboard.gs`

- [ ] **Step 1: Función que normaliza una fila de `apuestas_exoticas` a la forma de `filas`**

Después de `obtenerPatasPorMensaje_` en `src/Dashboard.gs`:

```javascript
/**
 * Lee apuestas_exoticas y la normaliza a la MISMA forma que ya usan
 * calcularMetricas_/calcularHistoricoPicks_ para las filas de `apuestas`
 * - así esas dos funciones no necesitan tocarse, solo reciben un array
 * más largo. `cuota`/`cuotaFinal` se dejan vacíos (no aplica a gemela/
 * trío, no hay cuota previa que comparar - por eso calcularPctCuotaBajada_
 * sigue llamándose SOLO con las filas de `apuestas`, nunca con estas).
 */
function obtenerFilasExoticasNormalizadas_() {
  const sheet = getSheet_(SHEET_APUESTAS_EXOTICAS);
  const index = getHeaderIndex_(sheet);
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) return [];

  const datos = sheet.getRange(2, 1, lastRow - 1, sheet.getLastColumn()).getValues();
  return datos.map(function (fila) {
    const tipoApuesta = fila[index['tipo_apuesta']];
    const nombre = tipoApuesta === 'trio' ? 'Trío' : 'Gemela';
    const combinaciones = String(fila[index['combinaciones']]).split(';').join(' y ');
    return {
      messageId: String(fila[index['message_id']] || ''),
      oculto: fila[index['oculto']] === true,
      resultadoFinal: fila[index['resultado_final']],
      unidadesNetas: fila[index['unidades_netas']],
      stake: fila[index['stake_total']],
      cuota: fila[index['resultado_final']] === 'gano' ? fila[index['dividendo']] : '',
      cuotaFinal: '',
      fechaPick: fila[index['fecha_pick']],
      canodromo: fila[index['hipodromo']],
      galgo: nombre + ' T' + combinaciones.split('-').join('-T'),
      mensaje: fila[index['mensaje']],
    };
  });
}
```

- [ ] **Step 2: Fusionar en `getMetricasPanel()`**

En `src/Dashboard.gs`, dentro de `getMetricasPanel()`, justo después de
construir `filas` (el `.map` sobre `apuestas`) y ANTES de
`const patasPorMensaje = obtenerPatasPorMensaje_();`:

```javascript
  const filasCombinadas = filas.concat(obtenerFilasExoticasNormalizadas_());
```

Y sustituye las llamadas siguientes para que usen `filasCombinadas` en
vez de `filas`, **excepto** `calcularPctCuotaBajada_`, que se queda con
`filas` (solo `apuestas`, no aplica a gemela/trío):

```javascript
  const patasPorMensaje = obtenerPatasPorMensaje_();

  const historicoPicks = calcularHistoricoPicks_(filasCombinadas).map(function (p) {
    return {
      fechaLabel: Utilities.formatDate(p.fechaPick, 'Europe/Madrid', 'dd/MM/yyyy'),
      fechaISO: Utilities.formatDate(p.fechaPick, 'Europe/Madrid', 'yyyy-MM-dd'),
      fechaHoraLabel: Utilities.formatDate(p.fechaPick, 'Europe/Madrid', 'dd/MM/yyyy HH:mm'),
      cuota: p.cuota,
      unidades: Math.round(p.unidadesNetas * 100) / 100,
      canodromo: p.canodromo,
      galgo: p.galgo,
      mensaje: p.mensaje,
      patas: patasPorMensaje[p.messageId] || [],
    };
  });

  const metricas = calcularMetricas_(filasCombinadas);
  if (!metricas.hayDatos) return { hayDatos: false, historicoPicks: historicoPicks };

  return {
    hayDatos: true,
    unidadesNetasEur: Math.round(metricas.unidadesNetas * TASA_EUR_POR_UNIDAD * 100) / 100,
    unidadesNetas: Math.round(metricas.unidadesNetas * 100) / 100,
    stakeTotalEur: Math.round(metricas.stakeTotal * TASA_EUR_POR_UNIDAD * 100) / 100,
    roiPct: Math.round(metricas.roiPct * 10) / 10,
    pctAciertos: Math.round(metricas.pctAciertos * 10) / 10,
    pctCuotaBajada: calcularPctCuotaBajada_(filas),
    evolucion: metricas.evolucion.map(function (p) {
      return {
        fechaLabel: Utilities.formatDate(p.fecha, 'Europe/Madrid', 'dd/MM/yyyy'),
        acumuladoEur: Math.round(p.acumuladoUnidades * TASA_EUR_POR_UNIDAD * 100) / 100,
        acumuladoUnidades: Math.round(p.acumuladoUnidades * 100) / 100,
      };
    }),
    historicoPicks: historicoPicks,
  };
}
```

Nota: `calcularPctCuotaBajada_(filas)` se queda igual que estaba (sin
`Combinadas`) — es la única excepción documentada en la spec.

- [ ] **Step 3: Subir**

```bash
clasp push
```

- [ ] **Step 4: Commit**

```bash
git add src/Dashboard.gs
git commit -m "feat: gemela/trio cuentan en el panel publico (menos cuota bajada)"
```

---

### Task 8: Reparar el caso histórico (Star Pelaw, 5-sept-2026)

**Files:**
- Modify: `src/Main.gs`

- [ ] **Step 1: Averiguar el `message_id` real**

Necesitas el `message_id` exacto del mensaje "GEMELA 3-4 Y 4-3..." en
`mensajes_crudos` (quedó con `estado=revision_manual`). Añade
temporalmente esta función de búsqueda en `Auditoria.gs` (solo lectura,
mismo patrón que `buscarPicksAtascados`), ejecútala, apunta el
`message_id`, y BÓRRALA después:

```javascript
function buscarMensajePorTexto_TEMPORAL(fragmento) {
  const sheet = getSheet_(SHEET_MENSAJES_CRUDOS);
  const index = getHeaderIndex_(sheet);
  const lastRow = sheet.getLastRow();
  const datos = sheet.getRange(2, 1, lastRow - 1, sheet.getLastColumn()).getValues();
  datos.forEach(function (fila, i) {
    const contenido = String(fila[index['contenido']] || '');
    if (contenido.indexOf(fragmento) !== -1) {
      Logger.log('fila=' + (i + 2) + ' message_id=' + fila[index['message_id']] +
        ' fecha=' + fila[index['fecha_recibido']] + ' estado=' + fila[index['estado']] +
        ' contenido="' + contenido + '"');
    }
  });
}
```

Ejecútala pasándole `'GEMELA'` a mano (cambia la llamada dentro del
editor o crea una función sin parámetros que la llame con ese literal),
`clasp push`, Ejecutar, y copia el `message_id` del Registro de
ejecución.

- [ ] **Step 2: Escribir la función de reparación**

En `src/Main.gs`, después de `repararPicksAtascados_2026_09_02`
(sustituye `<MESSAGE_ID_REAL>` por el valor encontrado en el Step 1):

```javascript
/**
 * Reparación puntual (2026-09-08): el pick real de gemela reversible de
 * Star Pelaw (5-sept-2026) quedó en mensajes_crudos con
 * estado=revision_manual porque el soporte de gemela/trío no existía
 * todavía. Ahora que existe, lo reprocesa por el camino nuevo - mismo
 * patrón que repararPicksAtascados_2026_09_02 pero llamando directamente
 * a manejarPickNuevo_ con los datos ya guardados en mensajes_crudos, en
 * vez de re-descargar nada de Telegram.
 *
 * Ejecutar A MANO desde el editor, una sola vez.
 */
function repararStarPelaw20260905() {
  const messageId = '<MESSAGE_ID_REAL>';
  const sheet = getSheet_(SHEET_MENSAJES_CRUDOS);
  const index = getHeaderIndex_(sheet);
  const lastRow = sheet.getLastRow();
  const datos = sheet.getRange(2, 1, lastRow - 1, sheet.getLastColumn()).getValues();

  for (let i = 0; i < datos.length; i++) {
    if (String(datos[i][index['message_id']]) !== messageId) continue;

    const fila = datos[i];
    const texto = fila[index['contenido']];
    const fotoFileId = fila[index['foto_file_id']] || null;
    const fechaRecibido = fila[index['fecha_recibido']];
    const fechaForward = fila[index['fecha_forward']] || null;

    const msgFalso = { message_id: messageId, chat: { id: TELEGRAM_CHAT_ID } };
    manejarPickNuevo_(msgFalso, texto, fotoFileId, fechaRecibido, fechaForward);
    Logger.log('repararStarPelaw20260905: reprocesado message_id=' + messageId);
    return;
  }
  Logger.log('repararStarPelaw20260905: no se encontró message_id=' + messageId + ' en mensajes_crudos.');
}
```

- [ ] **Step 3: Subir y ejecutar**

```bash
clasp push
```

Editor → Main.gs → `repararStarPelaw20260905` → Ejecutar. Espera el
mensaje de "Apuesta registrada (gemela): 22:31 Star Pelaw - T3-T4 y
T4-T3..." en el chat de Telegram real.

- [ ] **Step 4: Resolverla contra la fila sembrada en la Tarea 2**

Editor → Main.gs → `resolverApuestasExoticas` → Ejecutar. Espera el
mensaje "✅ Gemela acertada — 22:31 Star Pelaw: ganó T4-T3, dividendo
7.42, retorno 14.84u (+10.84u)" en el chat real, como respuesta al pick
original.

- [ ] **Step 5: Verificar en la hoja**

Confirma en `apuestas_exoticas` que la fila tiene `resultado_final=gano`,
`combinacion_acertada=4-3`, `dividendo=7.42`, `retorno_real=14.84`,
`unidades_netas=10.84`.

- [ ] **Step 6: Commit**

```bash
git add src/Main.gs
git commit -m "fix: reparar historico de la gemela real de Star Pelaw (5-sept-2026)"
```

---

### Task 9: Verificación final y bitácora

**Files:**
- Modify: `docs/BITACORA.md`

- [ ] **Step 1: Ejecutar TODOS los tests nuevos de un tirón**

Desde el editor, ejecuta en este orden y confirma `OK` en cada uno:
`test_validarExtraccionExotica` (AI.gs), `test_construirTextoConfirmacionExotica`,
`test_calcularResolucionExotica`, `test_construirTextoResolucionExotica`
(Main.gs). Si alguno falla, vuelve a la tarea correspondiente - no sigas.

- [ ] **Step 2: Probar un pick nuevo de verdad**

Reenvía al grupo real de Telegram un mensaje de prueba tipo "GEMELA 1-2 Y
2-1 - STAKE 1 CADA UNA (STAKE 2 TOTAL)" con un hipódromo/hora real de una
carrera que vaya a correr pronto. Confirma que llega el mensaje de
"Apuesta registrada" y que aparece la fila en `apuestas_exoticas`. (No
hace falta esperar a que se resuelva sola para dar esto por bueno - eso
depende de la Tarea externa en Proyecto Galgos, ver la sección
"Dependencia externa" al principio del plan).

- [ ] **Step 3: Desplegar sobre el deployment público**

```bash
clasp deploy -i AKfycbynXi-jwc8nA4Z3wEx3NNrcVxDwiBKMRQHdrXx_5vdXzrYcItxBlijtD68k4g72ww -d "Soporte de gemela y trio (forecast/tricast)"
```

Abre la URL pública del panel y confirma que sigue cargando bien (aunque
no haya todavía ninguna gemela/trío resuelta que mostrar).

- [ ] **Step 4: Entrada en la bitácora**

Añade al principio de `docs/BITACORA.md` (mismo formato que las entradas
anteriores):

```markdown
## 2026-09-08 — Soporte para gemela y trío (forecast/tricast)
Nuevo tipo de apuesta: gemela (1º y 2º de una carrera) y trío (1º, 2º y
3º), con o sin "reversible". A diferencia de simple/doble/triple, es UNA
carrera con varias selecciones y orden, pagada al dividendo oficial que
publica la pista tras la carrera (no a una cuota fija) - ver
`docs/superpowers/specs/2026-09-08-gemela-trio-design.md`.
- Hojas nuevas: `apuestas_exoticas` (la escribe el bot) y
  `resultados_gemela_trio` (la alimenta un job de la VM de Proyecto
  Galgos, tarea pendiente en ese otro repo - ver la spec).
- IA (`AI.gs`): reconoce "GEMELA"/"TRÍO" (desglosado o "reversible"),
  extrae combinaciones de orden en vez de cuota fija.
- Resolución por script (`resolverApuestasExoticas`, `Main.gs`, disparador
  cada 2h) en vez de fórmula de hoja - compara las combinaciones jugadas
  contra el resultado real y calcula retorno con el dividendo oficial.
- Dos avisos por Telegram (registro y resolución, ambos como respuesta al
  mensaje original) - a diferencia del resto de apuestas, que se resuelven
  en silencio.
- Cuentan en el panel público (unidades, ROI, aciertos, evolución,
  historial) - única excepción: la tarjeta "PICKS CON VALUE", que no
  aplica (no hay cuota previa que comparar).
- Reparado el caso histórico real (Star Pelaw, 5-sept-2026): acertó la
  combinación 4-3, dividendo 7.42, retorno 14.84u (+10.84u).

Commits: (pendiente)
```

- [ ] **Step 5: Commit**

```bash
git add docs/BITACORA.md
git commit -m "docs: bitacora del soporte de gemela y trio"
```

Después, edita la línea `Commits: (pendiente)` con el hash real de este
commit (`git log --oneline -1`) y haz un commit más pequeño solo para
esa línea, igual que se ha hecho en entradas anteriores de esta bitácora.

---

## Self-review de este plan

- **Cobertura de la spec**: arquitectura (Tasks 1-2 + nota de dependencia
  externa), modelo de datos (Tasks 1-2), extracción IA (Task 4),
  resolución por script (Task 6), mensajes de Telegram (Tasks 5 y 6),
  caso histórico (Task 8), panel público (Task 7) - todas las secciones
  de la spec tienen tarea. La única sección de la spec sin tarea propia
  es "Proyecto Galgos" (captura de forecasts/tricasts) - deliberado, ver
  "Dependencia externa" al principio: necesita su propia investigación en
  ese otro repo antes de poder escribirse sin inventar detalles.
- **Placeholders**: ninguno salvo `<MESSAGE_ID_REAL>` en la Task 8 Step 2,
  que es intencional (no se puede saber sin ejecutar el Step 1 antes) y
  está explícitamente resuelto por el paso anterior, no un "TBD" vago.
- **Consistencia de nombres**: `esExotica`/`tipoApuesta`/`combinaciones`/
  `hipodromo`/`horaCarrera`/`stakeTotal`/`stakePorCombinacion` se usan
  igual en `validarExtraccionExotica_` (Task 4), `manejarPickNuevo_`/
  `construirTextoConfirmacionExotica_` (Task 5), y
  `calcularResolucionExotica_`/`construirTextoResolucionExotica_`/
  `resolverApuestasExoticas` (Task 6) - revisado campo a campo.
