/**
 * Panel de métricas (Fase 8 del PLAN.md). Ver
 * docs/superpowers/specs/2026-08-26-panel-metricas-design.md para el
 * diseño completo (filtro, fórmulas, decisión de mostrar euros). Ampliado
 * 2026-08-26 (v2, pedido directo del dueño): las tarjetas y el gráfico
 * pasan a estar acotados a los últimos DIAS_VENTANA_PANEL días (antes eran
 * de todo el histórico), y se añade una tabla con los últimos
 * LIMITE_ULTIMOS_PICKS picks resueltos.
 */

// Ventana de las tarjetas/gráfico. LIMITE_ULTIMOS_PICKS no depende de esta
// ventana - la tabla de últimos picks muestra los N más recientes
// resueltos aunque caigan fuera de los últimos 30 días.
const DIAS_VENTANA_PANEL = 30;
const LIMITE_ULTIMOS_PICKS = 10;

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

  // El array de entrada no viene ordenado por fecha (marzo antes que enero):
  // si el .sort() de calcularMetricas_ se rompiera o se borrase, evolucion[0]
  // sería la fila de marzo (acumuladoUnidades=1) en vez de la de enero.
  const filasOrden = [
    { oculto: false, resultadoFinal: 'gano', unidadesNetas: 1, stake: 1, fechaPick: new Date('2026-03-01') },
    { oculto: false, resultadoFinal: 'gano', unidadesNetas: 2, stake: 1, fechaPick: new Date('2026-01-01') },
  ];
  const resultadoOrden = calcularMetricas_(filasOrden);
  assertIguales_(resultadoOrden.evolucion[0].acumuladoUnidades, 2, 'orden: evolucion[0] debe ser la fecha mas antigua (enero), no la primera del array');
  assertIguales_(resultadoOrden.evolucion[1].acumuladoUnidades, 3, 'orden: evolucion[1] acumulado tras ambas');

  // stakeTotal=0: roiPct debe caer en la guarda y devolver 0, no NaN/Infinity.
  const filasStakeCero = [
    { oculto: false, resultadoFinal: 'gano', unidadesNetas: 0, stake: 0, fechaPick: new Date('2026-01-01') },
  ];
  const resultadoStakeCero = calcularMetricas_(filasStakeCero);
  assertIguales_(resultadoStakeCero.roiPct, 0, 'roiPct debe ser 0 cuando stakeTotal es 0, no NaN/Infinity');

  Logger.log('test_calcularMetricas_: OK, todas las comprobaciones pasaron.');
}

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

/**
 * Ejecutar A MANO desde el editor (Ejecutar > test_calcularUltimosPicks_)
 * tras cada cambio en calcularUltimosPicks_ - mismo patrón que
 * test_calcularMetricas_ más arriba.
 */
function test_calcularUltimosPicks_() {
  const filas = [
    { oculto: false, resultadoFinal: 'gano', unidadesNetas: 2, cuota: 3.5, fechaPick: new Date('2026-01-01') },
    { oculto: false, resultadoFinal: 'perdio', unidadesNetas: -4, cuota: 2.1, fechaPick: new Date('2026-01-05') },
    // oculta: no debe aparecer aunque sea la más reciente
    { oculto: true, resultadoFinal: 'gano', unidadesNetas: 99, cuota: 9.9, fechaPick: new Date('2026-01-10') },
    // sin resolver: no debe aparecer
    { oculto: false, resultadoFinal: 'pendiente', unidadesNetas: '', cuota: 4.2, fechaPick: new Date('2026-01-09') },
    { oculto: false, resultadoFinal: 'gano', unidadesNetas: 1, cuota: 2.0, fechaPick: new Date('2026-01-03') },
  ];

  const top2 = calcularUltimosPicks_(filas, 2);
  assertIguales_(top2.length, 2, 'top2.length');
  // Más reciente primero (orden descendente por fecha), no el orden del array.
  assertIguales_(top2[0].fechaPick.getTime(), new Date('2026-01-05').getTime(), 'top2[0] debe ser 05/01 (el resuelto mas reciente)');
  assertIguales_(top2[0].cuota, 2.1, 'top2[0].cuota');
  assertIguales_(top2[0].unidadesNetas, -4, 'top2[0].unidadesNetas');
  assertIguales_(top2[1].fechaPick.getTime(), new Date('2026-01-03').getTime(), 'top2[1] debe ser 03/01');

  const sinLimite = calcularUltimosPicks_(filas, 10);
  assertIguales_(sinLimite.length, 3, 'sinLimite.length (solo las 3 resueltas y visibles)');

  const vacio = calcularUltimosPicks_([], 10);
  assertIguales_(vacio.length, 0, 'vacio.length');

  Logger.log('test_calcularUltimosPicks_: OK, todas las comprobaciones pasaron.');
}

/**
 * filas: mismo formato que calcularMetricas_, con `cuota` añadido. Filtra
 * igual (visible + resuelta) y devuelve las `limite` más recientes por
 * fechaPick, en unidades - getMetricasPanel() convierte a euros.
 */
function calcularUltimosPicks_(filas, limite) {
  const resueltas = filas.filter(function (f) {
    return f.oculto !== true && (f.resultadoFinal === 'gano' || f.resultadoFinal === 'perdio') &&
      f.fechaPick instanceof Date;
  });
  const ordenadas = resueltas.slice().sort(function (a, b) { return b.fechaPick - a.fechaPick; });
  return ordenadas.slice(0, limite).map(function (f) {
    return { fechaPick: f.fechaPick, cuota: Number(f.cuota), unidadesNetas: Number(f.unidadesNetas) };
  });
}

/**
 * Llamada desde el cliente (Panel.html) vía google.script.run. Lee
 * `apuestas` completa una sola vez y la reparte en dos vistas:
 * - Tarjetas + gráfico: solo picks de los últimos DIAS_VENTANA_PANEL días
 *   (antes era todo el histórico - cambiado 2026-08-26 a petición del
 *   dueño). calcularMetricas_ sigue siendo agnóstico de la ventana; el
 *   filtro de fecha se aplica aquí, antes de llamar a esa función.
 * - Tabla de últimos picks: los LIMITE_ULTIMOS_PICKS resueltos más
 *   recientes, SIN acotar a la ventana de 30 días (petición aparte del
 *   dueño) - por eso usa `filas` completo, no `filasVentana`.
 * Convierte a euros lo que sea una cifra absoluta (unidades netas, stake
 * total, cada punto de la evolución, unidades de cada pick) - ROI% y % de
 * aciertos son ratios, no se convierten. Ver TASA_EUR_POR_UNIDAD en
 * Config.gs y la excepción documentada en CLAUDE.md.
 */
function getMetricasPanel() {
  const sheet = getSheet_(SHEET_APUESTAS);
  const index = getHeaderIndex_(sheet);
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) return { hayDatos: false, ultimosPicks: [] };

  const datos = sheet.getRange(2, 1, lastRow - 1, sheet.getLastColumn()).getValues();
  const filas = datos.map(function (fila) {
    return {
      oculto: fila[index['oculto']] === true,
      resultadoFinal: fila[index['resultado_final']],
      unidadesNetas: fila[index['unidades_netas']],
      stake: fila[index['stake']],
      cuota: fila[index['cuota']],
      fechaPick: fila[index['fecha_pick']],
    };
  });

  // A diferencia de las tarjetas (que sí convierten a euros), la tabla de
  // últimos picks se queda en UNIDADES tal cual - pedido explícito del
  // dueño (2026-08-26): "las unidades ganadas son numeros", no €. La
  // relación entre las dos vistas sigue siendo 1 unidad = TASA_EUR_POR_UNIDAD.
  const ultimosPicks = calcularUltimosPicks_(filas, LIMITE_ULTIMOS_PICKS).map(function (p) {
    return {
      fechaLabel: Utilities.formatDate(p.fechaPick, 'Europe/Madrid', 'dd/MM/yyyy'),
      cuota: p.cuota,
      unidades: Math.round(p.unidadesNetas * 100) / 100,
    };
  });

  const fechaCorte = new Date();
  fechaCorte.setDate(fechaCorte.getDate() - DIAS_VENTANA_PANEL);
  const filasVentana = filas.filter(function (f) {
    return f.fechaPick instanceof Date && f.fechaPick >= fechaCorte;
  });

  const metricas = calcularMetricas_(filasVentana);
  if (!metricas.hayDatos) return { hayDatos: false, ultimosPicks: ultimosPicks };

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
    ultimosPicks: ultimosPicks,
  };
}

/**
 * Punto de entrada web (GET). Apps Script enruta GET -> doGet y POST ->
 * doPost (webhook de Telegram, en Main.gs) dentro del mismo despliegue de
 * Web App - no hay conflicto entre el panel y el bot.
 *
 * La plantilla se llama 'Panel' (src/Panel.html), no 'Dashboard': Apps
 * Script no permite que un archivo .gs y un archivo .html compartan el
 * mismo nombre base dentro del mismo proyecto (lo bloquea con "A file
 * with this name already exists in the current project" - comprobado con
 * clasp push contra el proyecto real). Dashboard.gs conserva su nombre tal
 * como pide el plan; el HTML se renombró para evitar el choque.
 */
function doGet(e) {
  return HtmlService.createTemplateFromFile('Panel')
    .evaluate()
    .setTitle('Panel de métricas - Picks Premier Galgos');
}
