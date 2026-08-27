/**
 * Panel de métricas (Fase 8 del PLAN.md). Ver
 * docs/superpowers/specs/2026-08-26-panel-metricas-design.md para el
 * diseño completo (filtro, fórmulas, decisión de mostrar euros).
 *
 * Historial de cambios sobre el diseño original (todos 2026-08-26/27,
 * pedidos directos del dueño):
 * - v2: tarjetas/gráfico acotados a los últimos 30 días + tabla de los
 *   últimos 10 picks resueltos.
 * - v3: la tabla de picks se queda en unidades (no euros) + rediseño
 *   visual.
 * - v4 (esta versión): revertido lo de "últimos 30 días" - el dueño dijo
 *   "no me cuadran los números", así que las tarjetas/gráfico vuelven a
 *   ser de TODO el histórico, como en la v1. La tabla deja de ser "los
 *   últimos 10" y pasa a ser el histórico COMPLETO de picks visibles y
 *   resueltos (mismo filtro que las tarjetas, sin límite de filas), con
 *   canódromo/galgo/mensaje original para poder revisarlas una a una.
 *   Se añade una tarjeta más con las unidades netas en crudo (sin
 *   convertir a euros), para poder cuadrar a mano el número en € contra
 *   las unidades reales de la hoja.
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
 * Ejecutar A MANO desde el editor (Ejecutar > test_calcularHistoricoPicks_)
 * tras cada cambio en calcularHistoricoPicks_ - mismo patrón que
 * test_calcularMetricas_ más arriba.
 */
function test_calcularHistoricoPicks_() {
  const filas = [
    { oculto: false, resultadoFinal: 'gano', unidadesNetas: 2, cuota: 3.5, fechaPick: new Date('2026-01-01') },
    { oculto: false, resultadoFinal: 'perdio', unidadesNetas: -4, cuota: 2.1, fechaPick: new Date('2026-01-05') },
    // oculta: no debe aparecer aunque sea la más reciente
    { oculto: true, resultadoFinal: 'gano', unidadesNetas: 99, cuota: 9.9, fechaPick: new Date('2026-01-10') },
    // sin resolver: no debe aparecer
    { oculto: false, resultadoFinal: 'pendiente', unidadesNetas: '', cuota: 4.2, fechaPick: new Date('2026-01-09') },
    { oculto: false, resultadoFinal: 'gano', unidadesNetas: 1, cuota: 2.0, fechaPick: new Date('2026-01-03') },
  ];

  const historico = calcularHistoricoPicks_(filas);
  assertIguales_(historico.length, 3, 'historico.length (solo las 3 resueltas y visibles, sin límite)');
  // Más reciente primero (orden descendente por fecha), no el orden del array.
  assertIguales_(historico[0].fechaPick.getTime(), new Date('2026-01-05').getTime(), 'historico[0] debe ser 05/01 (la mas reciente)');
  assertIguales_(historico[0].cuota, 2.1, 'historico[0].cuota');
  assertIguales_(historico[0].unidadesNetas, -4, 'historico[0].unidadesNetas');
  assertIguales_(historico[1].fechaPick.getTime(), new Date('2026-01-03').getTime(), 'historico[1] debe ser 03/01');
  assertIguales_(historico[2].fechaPick.getTime(), new Date('2026-01-01').getTime(), 'historico[2] debe ser 01/01 (la mas antigua, ultima)');

  const vacio = calcularHistoricoPicks_([]);
  assertIguales_(vacio.length, 0, 'vacio.length');

  Logger.log('test_calcularHistoricoPicks_: OK, todas las comprobaciones pasaron.');
}

/**
 * filas: mismo formato que calcularMetricas_, con `cuota`/`canodromo`/
 * `galgo`/`mensaje` añadidos. Filtra igual que calcularMetricas_ (visible
 * + resuelta) y devuelve TODAS (sin límite de filas), más reciente
 * primero - es la tabla de revisión completa del panel, no un resumen.
 * Unidades en crudo - getMetricasPanel() no las convierte a euros (pedido
 * explícito del dueño, ver más abajo).
 */
function calcularHistoricoPicks_(filas) {
  const resueltas = filas.filter(function (f) {
    return f.oculto !== true && (f.resultadoFinal === 'gano' || f.resultadoFinal === 'perdio') &&
      f.fechaPick instanceof Date;
  });
  return resueltas.slice().sort(function (a, b) { return b.fechaPick - a.fechaPick; }).map(function (f) {
    return {
      fechaPick: f.fechaPick,
      cuota: Number(f.cuota),
      unidadesNetas: Number(f.unidadesNetas),
      canodromo: f.canodromo,
      galgo: f.galgo,
      mensaje: f.mensaje,
    };
  });
}

/**
 * Llamada desde el cliente (Panel.html) vía google.script.run. Lee
 * `apuestas` completa una sola vez y la reparte en dos vistas, ambas de
 * TODO el histórico (sin ventana de fecha ni límite de filas - revertido
 * 2026-08-27, ver el historial de cambios en la cabecera del archivo):
 * - Tarjetas + gráfico: calcularMetricas_ sobre todas las filas.
 * - Tabla de historial: calcularHistoricoPicks_ sobre todas las filas,
 *   con canódromo/galgo/mensaje para poder revisar cada pick.
 * Convierte a euros las cifras absolutas de las TARJETAS (unidades netas,
 * stake total, cada punto de la evolución) - ROI% y % de aciertos son
 * ratios, no se convierten. La tarjeta de "unidades ganadas" y la tabla de
 * historial se quedan en UNIDADES tal cual, sin convertir (pedido
 * explícito del dueño, para poder cuadrar el número en € contra las
 * unidades reales de la hoja). Ver TASA_EUR_POR_UNIDAD en Config.gs y la
 * excepción documentada en CLAUDE.md.
 */
function getMetricasPanel() {
  const sheet = getSheet_(SHEET_APUESTAS);
  const index = getHeaderIndex_(sheet);
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) return { hayDatos: false, historicoPicks: [] };

  const datos = sheet.getRange(2, 1, lastRow - 1, sheet.getLastColumn()).getValues();
  const filas = datos.map(function (fila) {
    return {
      oculto: fila[index['oculto']] === true,
      resultadoFinal: fila[index['resultado_final']],
      unidadesNetas: fila[index['unidades_netas']],
      stake: fila[index['stake']],
      cuota: fila[index['cuota']],
      fechaPick: fila[index['fecha_pick']],
      canodromo: fila[index['canodromo']],
      galgo: fila[index['galgo']],
      mensaje: fila[index['mensaje']],
    };
  });

  const historicoPicks = calcularHistoricoPicks_(filas).map(function (p) {
    return {
      fechaLabel: Utilities.formatDate(p.fechaPick, 'Europe/Madrid', 'dd/MM/yyyy'),
      cuota: p.cuota,
      unidades: Math.round(p.unidadesNetas * 100) / 100,
      canodromo: p.canodromo,
      galgo: p.galgo,
      mensaje: p.mensaje,
    };
  });

  const metricas = calcularMetricas_(filas);
  if (!metricas.hayDatos) return { hayDatos: false, historicoPicks: historicoPicks };

  return {
    hayDatos: true,
    unidadesNetasEur: Math.round(metricas.unidadesNetas * TASA_EUR_POR_UNIDAD * 100) / 100,
    unidadesNetas: Math.round(metricas.unidadesNetas * 100) / 100,
    stakeTotalEur: Math.round(metricas.stakeTotal * TASA_EUR_POR_UNIDAD * 100) / 100,
    roiPct: Math.round(metricas.roiPct * 10) / 10,
    pctAciertos: Math.round(metricas.pctAciertos * 10) / 10,
    evolucion: metricas.evolucion.map(function (p) {
      return {
        fechaLabel: Utilities.formatDate(p.fecha, 'Europe/Madrid', 'dd/MM/yyyy'),
        acumuladoEur: Math.round(p.acumuladoUnidades * TASA_EUR_POR_UNIDAD * 100) / 100,
      };
    }),
    historicoPicks: historicoPicks,
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
    .setTitle('Panel de métricas - Picks Premier Galgos')
    // Permite que el panel se incruste en un <iframe> desde otro dominio
    // (petición del dueño: quiere el panel dentro de su web de WordPress).
    // Por defecto Apps Script solo deja enmarcarlo desde el propio Google -
    // sin esto, el iframe de WordPress se quedaría en blanco/bloqueado.
    .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL);
}
