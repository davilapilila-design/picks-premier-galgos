# Panel de métricas (Fase 8) — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Añadir un panel web (`doGet`) al mismo Web App del bot, que muestre 4
métricas (ganancia neta, stake total, ROI, % de aciertos) en euros y un
gráfico de evolución acumulada, calculados en vivo desde `apuestas`.

**Architecture:** Dos archivos nuevos en `src/`: `Dashboard.gs` (lógica de
servidor: `doGet`, `getMetricasPanel`, `calcularMetricas_`) y
`Dashboard.html` (HTML/CSS/JS de cliente + Google Charts). Se despliegan
sobre el MISMO deployment ID que ya usa el webhook de Telegram (Apps Script
enruta por verbo HTTP: GET → `doGet`, POST → `doPost`).

**Tech Stack:** Google Apps Script (`.gs`), `HtmlService`, Google Charts
(`corechart`/`LineChart`), `clasp` para desplegar.

**Nota sobre "tests" en este proyecto:** no hay framework de tests (Jest,
etc.) — es Apps Script puro, sin Node. `clasp run` no funciona en este
proyecto concreto (confirmado en `docs/BITACORA.md` 2026-08-26: da
"NOT_FOUND"), así que no se puede ejecutar ni ver el resultado de una
función desde esta sesión/CLI. El patrón ya establecido en el repo
(`checkConfig`, `setupSheet`) es: escribir una función que haga
comprobaciones con `Logger.log`/`throw`, y que **el usuario** la ejecute a
mano desde el editor de Apps Script (`clasp open-script` → seleccionar la
función en el desplegable → Ejecutar → mirar el "Registro de ejecución").
Este plan seguirlo: la Tarea 2 escribe primero el test manual (falla porque
la función no existe), luego la implementación (el usuario la ejecuta y
debe ver "OK" en el log). La verificación final de extremo a extremo (Tarea
5) es visual en el navegador, coherente con que esto es una página web.

---

### Task 1: Constante de conversión a euros

**Files:**
- Modify: `src/Config.gs`

- [ ] **Step 1: Añadir la constante**

Añade esta línea en `src/Config.gs`, junto a las demás constantes de
configuración (después de `TIPOS_APUESTA_SOPORTADOS`, línea 81):

```javascript
// Solo el panel de métricas (Dashboard.gs) convierte a euros para mostrar
// - el resto del proyecto sigue en unidades. Excepción explícita, ver
// CLAUDE.md y docs/superpowers/specs/2026-08-26-panel-metricas-design.md.
const TASA_EUR_POR_UNIDAD = 250;
```

- [ ] **Step 2: Commit**

```bash
git add src/Config.gs
git commit -m "feat: constante de conversión a euros para el panel de métricas"
```

---

### Task 2: `calcularMetricas_` — cálculo puro, con test manual

**Files:**
- Create: `src/Dashboard.gs`

Esta función NO toca `SpreadsheetApp` — recibe un array ya leído de filas y
devuelve las métricas. Así se puede probar con datos inventados, sin
depender de la hoja real.

- [ ] **Step 1: Crear `src/Dashboard.gs` con el test manual (sin implementación todavía)**

```javascript
/**
 * Panel de métricas (Fase 8 del PLAN.md). Ver
 * docs/superpowers/specs/2026-08-26-panel-metricas-design.md para el
 * diseño completo (filtro, fórmulas, decisión de mostrar euros).
 */

function assertIguales_(actual, esperado, etiqueta) {
  if (actual !== esperado) {
    throw new Error('FALLO en ' + etiqueta + ': esperado ' + esperado + ', obtenido ' + actual);
  }
}

/**
 * Ejecutar A MANO desde el editor de Apps Script (Ejecutar >
 * test_calcularMetricas_) tras cada cambio en calcularMetricas_ - mismo
 * patrón que checkConfig/setupSheet (Config.gs/Setup.gs). Sin fallos ->
 * "OK" en el Registro de ejecución. Con fallos -> excepción con el detalle
 * de qué comprobación no cuadró.
 */
function test_calcularMetricas_() {
  const filas = [
    { oculto: false, resultadoFinal: 'gano', unidadesNetas: 5, stake: 2, fechaPick: new Date('2026-01-01') },
    { oculto: false, resultadoFinal: 'perdio', unidadesNetas: -3, stake: 3, fechaPick: new Date('2026-01-02') },
    // oculta: no debe contar aunque tenga resultado
    { oculto: true, resultadoFinal: 'gano', unidadesNetas: 100, stake: 1, fechaPick: new Date('2026-01-03') },
    // sin resolver: no debe contar
    { oculto: false, resultadoFinal: 'pendiente', unidadesNetas: '', stake: 4, fechaPick: new Date('2026-01-04') },
  ];

  const resultado = calcularMetricas_(filas);

  assertIguales_(resultado.hayDatos, true, 'hayDatos');
  assertIguales_(resultado.unidadesNetas, 2, 'unidadesNetas'); // 5 + -3
  assertIguales_(resultado.stakeTotal, 5, 'stakeTotal'); // 2 + 3
  assertIguales_(resultado.roiPct, 40, 'roiPct'); // 2/5*100
  assertIguales_(resultado.pctAciertos, 50, 'pctAciertos'); // 1 de 2 resueltas
  assertIguales_(resultado.evolucion.length, 2, 'evolucion.length');
  assertIguales_(resultado.evolucion[0].acumuladoUnidades, 5, 'evolucion[0].acumuladoUnidades');
  assertIguales_(resultado.evolucion[1].acumuladoUnidades, 2, 'evolucion[1].acumuladoUnidades');

  const vacio = calcularMetricas_([]);
  assertIguales_(vacio.hayDatos, false, 'hayDatos (sin filas)');

  Logger.log('test_calcularMetricas_: OK, todas las comprobaciones pasaron.');
}
```

- [ ] **Step 2: Push y ejecutar el test — debe FALLAR (la función no existe todavía)**

```bash
clasp push
```
Pide confirmar sobreescribir el manifest si lo pregunta: responde que no
(el manifest ya está subido, no hace falta tocarlo aquí).

Pide al usuario que abra `clasp open-script`, seleccione
`test_calcularMetricas_` en el desplegable de funciones y pulse Ejecutar.
Resultado esperado: error `ReferenceError: calcularMetricas_ is not
defined`.

- [ ] **Step 3: Implementar `calcularMetricas_`**

Añade esto en `src/Dashboard.gs`, debajo del test:

```javascript
/**
 * filas: array de {oculto, resultadoFinal, unidadesNetas, stake, fechaPick}
 * ya leído de la pestaña `apuestas` (o de datos de prueba). Filtra a las
 * resueltas y visibles (oculto=false, resultadoFinal en gano/perdio - ver
 * el spec del panel) y calcula las métricas. Todo en UNIDADES - la
 * conversión a euros la hace getMetricasPanel(), no esta función.
 */
function calcularMetricas_(filas) {
  const resueltas = filas.filter(function (f) {
    return f.oculto !== true && (f.resultadoFinal === 'gano' || f.resultadoFinal === 'perdio');
  });

  if (resueltas.length === 0) {
    return { hayDatos: false };
  }

  let unidadesNetas = 0;
  let stakeTotal = 0;
  let ganadas = 0;
  resueltas.forEach(function (f) {
    unidadesNetas += Number(f.unidadesNetas);
    stakeTotal += Number(f.stake);
    if (f.resultadoFinal === 'gano') ganadas++;
  });

  const ordenadas = resueltas.slice().sort(function (a, b) { return a.fechaPick - b.fechaPick; });
  let acumulado = 0;
  const evolucion = ordenadas.map(function (f) {
    acumulado += Number(f.unidadesNetas);
    return { fecha: f.fechaPick, acumuladoUnidades: acumulado };
  });

  return {
    hayDatos: true,
    unidadesNetas: unidadesNetas,
    stakeTotal: stakeTotal,
    roiPct: stakeTotal === 0 ? 0 : (unidadesNetas / stakeTotal) * 100,
    pctAciertos: (ganadas / resueltas.length) * 100,
    evolucion: evolucion,
  };
}
```

- [ ] **Step 4: Push y ejecutar el test otra vez — debe PASAR**

```bash
clasp push
```
Pide al usuario que vuelva a ejecutar `test_calcularMetricas_` desde el
editor. Resultado esperado en el Registro de ejecución: `test_calcularMetricas_:
OK, todas las comprobaciones pasaron.` — sin excepción. Si falla, el
mensaje de `assertIguales_` dice exactamente qué comprobación no cuadró;
corrige `calcularMetricas_` y repite este paso antes de seguir.

- [ ] **Step 5: Commit**

```bash
git add src/Dashboard.gs
git commit -m "feat: calcularMetricas_ con test manual (panel de métricas)"
```

---

### Task 3: `getMetricasPanel` — lee la hoja real y convierte a euros

**Files:**
- Modify: `src/Dashboard.gs`

- [ ] **Step 1: Añadir `getMetricasPanel()`**

Añade al final de `src/Dashboard.gs`:

```javascript
/**
 * Llamada desde el cliente (Dashboard.html) vía google.script.run. Lee
 * `apuestas` completa, delega el cálculo en calcularMetricas_ (en
 * unidades) y convierte a euros lo que sea una cifra absoluta (unidades
 * netas, stake total, cada punto de la evolución) - ROI% y % de aciertos
 * son ratios, no se convierten. Ver TASA_EUR_POR_UNIDAD en Config.gs y la
 * excepción documentada en CLAUDE.md.
 */
function getMetricasPanel() {
  const sheet = getSheet_(SHEET_APUESTAS);
  const index = getHeaderIndex_(sheet);
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) return { hayDatos: false };

  const datos = sheet.getRange(2, 1, lastRow - 1, sheet.getLastColumn()).getValues();
  const filas = datos.map(function (fila) {
    return {
      oculto: fila[index['oculto']] === true,
      resultadoFinal: fila[index['resultado_final']],
      unidadesNetas: fila[index['unidades_netas']],
      stake: fila[index['stake']],
      fechaPick: fila[index['fecha_pick']],
    };
  });

  const metricas = calcularMetricas_(filas);
  if (!metricas.hayDatos) return { hayDatos: false };

  return {
    hayDatos: true,
    unidadesNetasEur: Math.round(metricas.unidadesNetas * TASA_EUR_POR_UNIDAD * 100) / 100,
    stakeTotalEur: Math.round(metricas.stakeTotal * TASA_EUR_POR_UNIDAD * 100) / 100,
    roiPct: Math.round(metricas.roiPct * 10) / 10,
    pctAciertos: Math.round(metricas.pctAciertos * 10) / 10,
    evolucion: metricas.evolucion.map(function (p) {
      return {
        fechaLabel: Utilities.formatDate(p.fecha, 'Europe/Madrid', 'dd/MM/yyyy'),
        acumuladoEur: Math.round(p.acumuladoUnidades * TASA_EUR_POR_UNIDAD * 100) / 100,
      };
    }),
  };
}
```

Reutiliza `getSheet_`/`getHeaderIndex_` (`src/Sheets.gs`, ya existen) y
`SHEET_APUESTAS`/`TASA_EUR_POR_UNIDAD` (`src/Config.gs`) - no hace falta
ningún dato ni constante nueva aparte de la de la Tarea 1.

- [ ] **Step 2: Commit**

```bash
git add src/Dashboard.gs
git commit -m "feat: getMetricasPanel lee apuestas y convierte a euros"
```

---

### Task 4: `doGet` + `Dashboard.html`

**Files:**
- Modify: `src/Dashboard.gs`
- Create: `src/Dashboard.html`

- [ ] **Step 1: Añadir `doGet` a `src/Dashboard.gs`**

```javascript
function doGet(e) {
  return HtmlService.createTemplateFromFile('Dashboard')
    .evaluate()
    .setTitle('Panel de métricas - Picks Premier Galgos');
}
```

- [ ] **Step 2: Crear `src/Dashboard.html`**

```html
<!DOCTYPE html>
<html>
  <head>
    <base target="_top">
    <meta charset="utf-8">
    <style>
      body { font-family: Arial, sans-serif; background: #0b0f14; color: #e8eef4; margin: 0; padding: 24px; }
      h1 { font-size: 20px; font-weight: 600; margin-bottom: 24px; }
      .tarjetas { display: flex; flex-wrap: wrap; gap: 16px; margin-bottom: 32px; }
      .tarjeta { background: #151b23; border-radius: 8px; padding: 16px 20px; min-width: 160px; }
      .tarjeta .etiqueta { font-size: 13px; color: #9fb3c8; margin-bottom: 6px; }
      .tarjeta .valor { font-size: 24px; font-weight: 700; }
      .positivo { color: #4ade80; }
      .negativo { color: #f87171; }
      #grafico { width: 100%; height: 360px; }
      #mensaje { color: #9fb3c8; }
    </style>
  </head>
  <body>
    <h1>Panel de métricas — Picks Premier Galgos</h1>
    <div id="mensaje">Cargando...</div>
    <div id="contenido" style="display:none;">
      <div class="tarjetas">
        <div class="tarjeta"><div class="etiqueta">Ganancia neta</div><div class="valor" id="valUnidadesNetas">-</div></div>
        <div class="tarjeta"><div class="etiqueta">Total jugado</div><div class="valor" id="valStakeTotal">-</div></div>
        <div class="tarjeta"><div class="etiqueta">ROI / Yield</div><div class="valor" id="valRoi">-</div></div>
        <div class="tarjeta"><div class="etiqueta">% de aciertos</div><div class="valor" id="valAciertos">-</div></div>
      </div>
      <div id="grafico"></div>
    </div>

    <script src="https://www.gstatic.com/charts/loader.js"></script>
    <script>
      google.charts.load('current', { packages: ['corechart'] });

      google.script.run
        .withSuccessHandler(pintarPanel)
        .withFailureHandler(mostrarError)
        .getMetricasPanel();

      function pintarPanel(metricas) {
        if (!metricas.hayDatos) {
          document.getElementById('mensaje').textContent = 'Sin datos todavía.';
          return;
        }
        document.getElementById('mensaje').style.display = 'none';
        document.getElementById('contenido').style.display = 'block';

        setValor('valUnidadesNetas', formatearEur(metricas.unidadesNetasEur), metricas.unidadesNetasEur >= 0);
        setValor('valStakeTotal', formatearEur(metricas.stakeTotalEur), true);
        setValor('valRoi', metricas.roiPct.toFixed(1) + ' %', metricas.roiPct >= 0);
        setValor('valAciertos', metricas.pctAciertos.toFixed(1) + ' %', true);

        google.charts.setOnLoadCallback(function () { pintarGrafico(metricas.evolucion); });
      }

      function setValor(id, texto, positivo) {
        const el = document.getElementById(id);
        el.textContent = texto;
        el.className = 'valor ' + (positivo ? 'positivo' : 'negativo');
      }

      function formatearEur(valor) {
        return valor.toLocaleString('es-ES', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' €';
      }

      function pintarGrafico(evolucion) {
        const datos = new google.visualization.DataTable();
        datos.addColumn('string', 'Fecha');
        datos.addColumn('number', 'Ganancia acumulada (€)');
        evolucion.forEach(function (p) { datos.addRow([p.fechaLabel, p.acumuladoEur]); });

        const grafico = new google.visualization.LineChart(document.getElementById('grafico'));
        grafico.draw(datos, {
          backgroundColor: 'transparent',
          colors: ['#4ade80'],
          legend: { position: 'none' },
          hAxis: { textStyle: { color: '#9fb3c8' } },
          vAxis: { textStyle: { color: '#9fb3c8' } },
        });
      }

      function mostrarError(error) {
        document.getElementById('mensaje').textContent = 'Error cargando el panel: ' + error.message;
      }
    </script>
  </body>
</html>
```

- [ ] **Step 3: Push**

```bash
clasp push
```

- [ ] **Step 4: Commit**

```bash
git add src/Dashboard.gs src/Dashboard.html
git commit -m "feat: doGet y Dashboard.html sirven el panel de métricas"
```

---

### Task 5: Desplegar sobre el deployment del webhook y verificar en el navegador

**Files:** ninguno (solo despliegue y verificación manual)

- [ ] **Step 1: Confirmar el deployment ID del webhook**

```bash
clasp deployments
```
Busca la línea que NO es `@HEAD` (la que tiene descripción, ej. "Reintento
automatico de mensajes en error") — copia su ID (empieza por `AKfycb...`).
Es el mismo deployment que ya usa el webhook de Telegram: hay que
redesplegar sobre ÉL, no crear uno nuevo, para no cambiar la URL en
producción.

- [ ] **Step 2: Redesplegar**

```bash
clasp deploy -i <ID_COPIADO> -d "Fase 8: panel de metricas (doGet)"
```

- [ ] **Step 3: Verificación visual en el navegador (pide al usuario que la haga)**

Pide al usuario que abra la URL del Web App (la misma `/exec` del webhook,
sin `?token=` — eso es solo para el POST de Telegram) en su navegador y
confirme:
- Las 4 tarjetas muestran números en €, no "Cargando..." ni "Sin datos".
- El signo de "Ganancia neta" es coherente con lo que sabe del tipster
  (referencia conocida: +75,27 unidades a fecha del backfill de
  2026-08-26, documentado en `docs/BITACORA.md` — con más picks resueltos
  desde entonces el número real será distinto, pero del mismo orden de
  magnitud y positivo).
- El gráfico de evolución se dibuja (línea, no un hueco en blanco).
- Comprobación de que el bot sigue vivo: no hace falta reenviar un pick de
  prueba, pero confirma que `clasp deployments` sigue mostrando el mismo ID
  que antes (el redeploy actualiza el código detrás del mismo ID, no crea
  uno nuevo).

Si algo no cuadra, vuelve a la tarea correspondiente antes de seguir — no
se documenta como terminado sin esta confirmación visual real (igual que
las pruebas end-to-end anteriores del proyecto, ver `docs/BITACORA.md`
2026-08-26).

---

### Task 6: Documentar en la bitácora

**Files:**
- Modify: `docs/BITACORA.md`

- [ ] **Step 1: Añadir entrada nueva arriba del todo**

Con el resultado real de la Tarea 5 delante (cifras que viste en el
navegador), añade una entrada siguiendo el mismo formato que las demás
entradas de `docs/BITACORA.md` (fecha de hoy, qué se hizo y por qué,
commits). Debe cubrir: los archivos nuevos (`Dashboard.gs`/`Dashboard.html`),
la decisión de reusar el mismo deployment del webhook (`doGet` vs
`doPost`), la excepción de euros (1 unidad = 250€, y el porqué documentado
también en `CLAUDE.md`), el resultado de `test_calcularMetricas_`, y las
cifras reales observadas al abrir el panel en el navegador.

- [ ] **Step 2: Commit**

```bash
git add docs/BITACORA.md
git commit -m "docs: bitácora del panel de métricas (Fase 8)"
```

---

### Task 7: Marcar la Fase 8 como completa en el PLAN.md

**Files:**
- Modify: `PLAN.md:209`

- [ ] **Step 1: Marcar el roadmap**

Cambia en `PLAN.md` línea 209:

```markdown
- [ ] **Fase 8** — Montar el panel (pestaña de gráficos nativos o Looker Studio).
```

por:

```markdown
- [x] **Fase 8** — Completa (2026-08-26): panel web (`doGet` en
  `src/Dashboard.gs` + `src/Dashboard.html`) sobre el mismo deployment del
  webhook, con conversión a euros (excepción documentada en `CLAUDE.md`).
  Ver `docs/superpowers/specs/2026-08-26-panel-metricas-design.md` y
  `docs/BITACORA.md`.
```

- [ ] **Step 2: Commit**

```bash
git add PLAN.md
git commit -m "docs: Fase 8 (panel de métricas) completa en el roadmap"
```
