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
