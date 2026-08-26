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
 * Llamada desde el cliente (Panel.html) vía google.script.run. Lee
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
