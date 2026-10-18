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
 * - v4: revertido lo de "últimos 30 días" - el dueño dijo "no me cuadran
 *   los números", así que las tarjetas/gráfico vuelven a ser de TODO el
 *   histórico, como en la v1. La tabla deja de ser "los últimos 10" y
 *   pasa a ser el histórico COMPLETO de picks visibles y resueltos
 *   (mismo filtro que las tarjetas, sin límite de filas), con
 *   canódromo/galgo/mensaje original para poder revisarlas una a una.
 *   Se añade una tarjeta más con las unidades netas en crudo (sin
 *   convertir a euros), para poder cuadrar a mano el número en € contra
 *   las unidades reales de la hoja.
 * - v5 (esta versión, 2026-09-01, rediseño de Panel.html): filtro de
 *   rango de fechas en el cliente (sin acotar en el servidor - v4 se
 *   revirtió justo por eso, no repetir el error), hora de envío del pick
 *   y hora de cada carrera en "Mensaje original", y una 5ª tarjeta con
 *   el % de picks cuya cuota de cierre acabó por debajo de la publicada.
 *   Corregido de paso un bug real: `evolucion` tenía una entrada POR
 *   PICK en vez de por día, así que "nº de jornadas" y "nº de picks"
 *   coincidían siempre - ver `calcularMetricas_` más abajo.
 */

function assertIguales_(actual, esperado, etiqueta) {
  if (actual !== esperado) {
    throw new Error('FALLO en ' + etiqueta + ': esperado ' + esperado + ', obtenido ' + actual);
  }
}

/**
 * Ejecutar A MANO desde el editor de Apps Script (Ejecutar >
 * test_calcularMetricas) tras cada cambio en calcularMetricas_ - mismo
 * patrón que checkConfig/setupSheet (Config.gs/Setup.gs). Sin fallos ->
 * "OK" en el Registro de ejecución. Con fallos -> excepción con el detalle
 * de qué comprobación no cuadró.
 */
function test_calcularMetricas() {
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

  // Bug real (2026-09-01, ver docs/BITACORA.md): dos picks el MISMO día
  // deben dar 1 sola entrada en evolucion, no 2 - si no, "nº de jornadas"
  // en el panel siempre coincide con "nº de picks", que es justo el bug
  // que se reportó (130 picks en 130 "jornadas").
  const filasMismoDia = [
    { oculto: false, resultadoFinal: 'gano', unidadesNetas: 3, stake: 2, fechaPick: new Date('2026-02-01T10:00:00') },
    { oculto: false, resultadoFinal: 'perdio', unidadesNetas: -1, stake: 1, fechaPick: new Date('2026-02-01T18:30:00') },
    { oculto: false, resultadoFinal: 'gano', unidadesNetas: 4, stake: 2, fechaPick: new Date('2026-02-02T10:00:00') },
  ];
  const resultadoMismoDia = calcularMetricas_(filasMismoDia);
  assertIguales_(resultadoMismoDia.evolucion.length, 2, 'evolucion.length debe agrupar por día (2 días distintos, no 3 picks)');
  assertIguales_(resultadoMismoDia.evolucion[0].acumuladoUnidades, 2, 'evolucion[0] (01/02) debe llevar el acumulado de SUS DOS picks (3-1=2)');
  assertIguales_(resultadoMismoDia.evolucion[1].acumuladoUnidades, 6, 'evolucion[1] (02/02) debe llevar el acumulado total (2+4=6)');

  Logger.log('test_calcularMetricas: OK, todas las comprobaciones pasaron.');
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

  // Una entrada de evolucion por DÍA natural, no por pick - varios picks
  // el mismo día deben acumular en el mismo punto de la curva (bug real
  // 2026-09-01: antes había 1 entrada por pick, así que "nº de jornadas"
  // del panel siempre coincidía con "nº de picks", ver docs/BITACORA.md).
  const ordenadas = resueltas.slice().sort(function (a, b) { return a.fechaPick - b.fechaPick; });
  let acumulado = 0;
  const evolucion = [];
  let diaActual = null;
  ordenadas.forEach(function (f) {
    acumulado += Number(f.unidadesNetas);
    const claveDia = Utilities.formatDate(f.fechaPick, 'Europe/Madrid', 'yyyy-MM-dd');
    if (claveDia === diaActual) {
      evolucion[evolucion.length - 1].acumuladoUnidades = acumulado;
    } else {
      evolucion.push({ fecha: f.fechaPick, acumuladoUnidades: acumulado });
      diaActual = claveDia;
    }
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
 * Ejecutar A MANO desde el editor (Ejecutar > test_calcularHistoricoPicks)
 * tras cada cambio en calcularHistoricoPicks_ - mismo patrón que
 * test_calcularMetricas más arriba.
 */
function test_calcularHistoricoPicks() {
  const filas = [
    { messageId: '1', oculto: false, resultadoFinal: 'gano', unidadesNetas: 2, cuota: 3.5, fechaPick: new Date('2026-01-01') },
    { messageId: '2', oculto: false, resultadoFinal: 'perdio', unidadesNetas: -4, cuota: 2.1, fechaPick: new Date('2026-01-05') },
    // oculta: no debe aparecer aunque sea la más reciente
    { messageId: '3', oculto: true, resultadoFinal: 'gano', unidadesNetas: 99, cuota: 9.9, fechaPick: new Date('2026-01-10') },
    // sin resolver: no debe aparecer
    { messageId: '4', oculto: false, resultadoFinal: 'pendiente', unidadesNetas: '', cuota: 4.2, fechaPick: new Date('2026-01-09') },
    { messageId: '5', oculto: false, resultadoFinal: 'gano', unidadesNetas: 1, cuota: 2.0, fechaPick: new Date('2026-01-03') },
  ];

  const historico = calcularHistoricoPicks_(filas);
  assertIguales_(historico.length, 3, 'historico.length (solo las 3 resueltas y visibles, sin límite)');
  // Más reciente primero (orden descendente por fecha), no el orden del array.
  assertIguales_(historico[0].fechaPick.getTime(), new Date('2026-01-05').getTime(), 'historico[0] debe ser 05/01 (la mas reciente)');
  assertIguales_(historico[0].cuota, 2.1, 'historico[0].cuota');
  assertIguales_(historico[0].unidadesNetas, -4, 'historico[0].unidadesNetas');
  assertIguales_(historico[0].messageId, '2', 'historico[0].messageId debe pasar tal cual, hace falta para cruzar con apuestas_patas');
  assertIguales_(historico[1].fechaPick.getTime(), new Date('2026-01-03').getTime(), 'historico[1] debe ser 03/01');
  assertIguales_(historico[2].fechaPick.getTime(), new Date('2026-01-01').getTime(), 'historico[2] debe ser 01/01 (la mas antigua, ultima)');

  const vacio = calcularHistoricoPicks_([]);
  assertIguales_(vacio.length, 0, 'vacio.length');

  Logger.log('test_calcularHistoricoPicks: OK, todas las comprobaciones pasaron.');
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
      messageId: f.messageId,
      fechaPick: f.fechaPick,
      cuota: Number(f.cuota),
      unidadesNetas: Number(f.unidadesNetas),
      stake: Number(f.stake),
      canodromo: f.canodromo,
      galgo: f.galgo,
      mensaje: f.mensaje,
    };
  });
}

/**
 * "Cuota bajada" = la cuota de cierre (`cuota_final`, cierre de mercado)
 * acabó por debajo de la cuota con la que se publicó el pick - señal
 * clásica de valor (el mercado se movió a favor del pick tras publicarse).
 * Mismo filtro que calcularMetricas_ (visible + resuelta), y además exige
 * que AMBAS cuotas sean numéricas - las filas sin cuota_final rellenada
 * todavía no cuentan ni suman ni restan, se excluyen del denominador (no
 * es que "no bajaron", es que no lo sabemos). Devuelve null si no hay
 * ninguna fila con ambos datos (nada que mostrar todavía).
 */
function calcularPctCuotaBajada_(filas) {
  const resueltas = filas.filter(function (f) {
    return f.oculto !== true && (f.resultadoFinal === 'gano' || f.resultadoFinal === 'perdio');
  });
  const conAmbasCuotas = resueltas.filter(function (f) {
    return esNumerico_(f.cuota) && esNumerico_(f.cuotaFinal);
  });
  if (conAmbasCuotas.length === 0) return null;
  const bajaron = conAmbasCuotas.filter(function (f) {
    return Number(f.cuotaFinal) < Number(f.cuota);
  }).length;
  return (bajaron / conAmbasCuotas.length) * 100;
}

/**
 * Ejecutar A MANO desde el editor (Ejecutar > test_calcularPctCuotaBajada)
 * tras cada cambio en calcularPctCuotaBajada_ - mismo patrón que las demás
 * funciones puras de este archivo.
 */
function test_calcularPctCuotaBajada() {
  const filas = [
    { oculto: false, resultadoFinal: 'gano', cuota: 3.0, cuotaFinal: 2.5 }, // bajó
    { oculto: false, resultadoFinal: 'perdio', cuota: 2.0, cuotaFinal: 2.4 }, // no bajó
    { oculto: false, resultadoFinal: 'gano', cuota: 4.0, cuotaFinal: 3.9 }, // bajó
    // oculta: no debe contar
    { oculto: true, resultadoFinal: 'gano', cuota: 9.0, cuotaFinal: 1.0 },
    // sin resolver: no debe contar
    { oculto: false, resultadoFinal: 'pendiente', cuota: 5.0, cuotaFinal: 4.0 },
    // sin cuota_final todavía: no debe contar ni en numerador ni en denominador
    { oculto: false, resultadoFinal: 'gano', cuota: 2.5, cuotaFinal: '' },
  ];
  assertIguales_(calcularPctCuotaBajada_(filas), (2 / 3) * 100, 'pctCuotaBajada: 2 de 3 filas válidas bajaron');
  assertIguales_(calcularPctCuotaBajada_([]), null, 'pctCuotaBajada con array vacío debe ser null, no NaN');
  assertIguales_(calcularPctCuotaBajada_([{ oculto: false, resultadoFinal: 'gano', cuota: '', cuotaFinal: '' }]), null,
    'pctCuotaBajada sin ninguna fila con ambas cuotas numéricas debe ser null');
  Logger.log('test_calcularPctCuotaBajada: OK, todas las comprobaciones pasaron.');
}

/**
 * Convierte hora_carrera (Date, serial de Sheets o string "HH:mm[:ss]")
 * en un string "HH:mm" para el panel. Reutiliza normalizarHoraSegundos_
 * (definida en Auditoria.gs, funciones globales de Apps Script - incluso
 * en archivos separados) en vez de reimplementar el parseo.
 */
function formatearHoraCarrera_(v) {
  const segundos = normalizarHoraSegundos_(v);
  if (segundos == null) return null;
  const h = Math.floor(segundos / 3600);
  const m = Math.floor((segundos % 3600) / 60);
  return ('0' + h).slice(-2) + ':' + ('0' + m).slice(-2);
}

/** Igual que arriba pero para la fecha de la carrera (apuestas_patas.fecha_pick), en dd/MM/yyyy. */
function formatearFechaCarreraLabel_(v) {
  const iso = normalizarFechaISO_(v);
  if (!iso) return null;
  const partes = iso.split('-');
  return partes[2] + '/' + partes[1] + '/' + partes[0];
}

/**
 * Filas de datos de una pestaña SIN las filas de margen: `apuestas` y
 * `apuestas_patas` traen las columnas fórmula pre-rellenadas hasta la fila
 * 2000/5000 (ver Setup.gs), así que `getLastRow()` devuelve esa fila lejana
 * y leer hasta ahí hacía que el panel trajera ~120.000 celdas en cada
 * visita cuando solo unos cientos de filas tienen un pick (2026-10-18, ver
 * docs/BITACORA.md). Se lee primero solo la columna `message_id` (nunca
 * tiene fórmulas, mismo criterio que proximaFilaVacia_ en Sheets.gs) para
 * saber dónde acaba el último pick real, y después solo ese bloque. Busca
 * el ÚLTIMO message_id no vacío (no el primer hueco), así que un hueco a
 * mitad de la hoja no corta la lectura. Devuelve [] si no hay ninguno.
 */
function leerFilasConDatos_(sheet, index) {
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) return [];
  const ids = sheet.getRange(2, index['message_id'] + 1, lastRow - 1, 1).getValues();
  let numFilas = ids.length;
  while (numFilas > 0 && String(ids[numFilas - 1][0]) === '') numFilas--;
  if (numFilas === 0) return [];
  return sheet.getRange(2, 1, numFilas, sheet.getLastColumn()).getValues();
}

/**
 * Lee `apuestas_patas` completa de una vez (igual que Auditoria.gs, más
 * barato que una lectura por fila) y la agrupa por `message_id`, una
 * entrada por CARRERA del pick (dobles/triples incluidos), ordenadas por
 * `numero_pata`. Filas sin hora_carrera interpretable se excluyen (nada
 * que mostrar para esa pata).
 */
function obtenerPatasPorMensaje_() {
  const sheet = getSheet_(SHEET_APUESTAS_PATAS);
  const index = getHeaderIndex_(sheet);
  const porMensaje = {};

  const datos = leerFilasConDatos_(sheet, index);
  datos.forEach(function (fila) {
    const messageId = String(fila[index['message_id']] || '');
    if (!messageId) return;
    const horaCarrera = formatearHoraCarrera_(fila[index['hora_carrera']]);
    if (!horaCarrera) return;
    if (!porMensaje[messageId]) porMensaje[messageId] = [];
    porMensaje[messageId].push({
      numero: Number(fila[index['numero_pata']]) || (porMensaje[messageId].length + 1),
      horaCarrera: horaCarrera,
      fechaCarreraLabel: formatearFechaCarreraLabel_(fila[index['fecha_pick']]),
    });
  });

  Object.keys(porMensaje).forEach(function (id) {
    porMensaje[id].sort(function (a, b) { return a.numero - b.numero; });
  });
  return porMensaje;
}

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

  const datos = leerFilasConDatos_(sheet, index);
  return datos.map(function (fila) {
    const tipoApuesta = fila[index['tipo_apuesta']];
    const nombre = tipoApuesta === 'trio' ? 'Trío' : 'Gemela';
    const combinaciones = String(fila[index['combinaciones']]).split(';').map(function (c) {
      return 'T' + c.split('-').join('-T');
    }).join(' y ');
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
      galgo: nombre + ' ' + combinaciones,
      mensaje: fila[index['mensaje']],
    };
  });
}

/**
 * Calcula desde la hoja todo lo que pinta el panel (lo sirve
 * getMetricasPanel, normalmente desde caché - ver más abajo). Lee
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
function construirDatosPanel_() {
  const filas = obtenerFilasApuestas_();
  if (filas.length === 0) return { hayDatos: false, historicoPicks: [] };

  const filasCombinadas = filas.concat(obtenerFilasExoticasNormalizadas_());

  const patasPorMensaje = obtenerPatasPorMensaje_();

  const historicoPicks = calcularHistoricoPicks_(filasCombinadas).map(function (p) {
    // Un solo formatDate por pick (antes 3, uno por etiqueta) y las tres
    // etiquetas se recortan de ahí - mismo resultado, menos llamadas.
    const f = Utilities.formatDate(p.fechaPick, 'Europe/Madrid', 'yyyy-MM-dd HH:mm');
    const fechaLabel = f.slice(8, 10) + '/' + f.slice(5, 7) + '/' + f.slice(0, 4);
    return {
      fechaLabel: fechaLabel,
      fechaISO: f.slice(0, 10),
      fechaHoraLabel: fechaLabel + ' ' + f.slice(11, 16),
      cuota: p.cuota,
      unidades: Math.round(p.unidadesNetas * 100) / 100,
      stake: Math.round(p.stake * 100) / 100,
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

// Caché del panel (2026-10-18, ver docs/BITACORA.md). Sin ella, CADA
// visita abría la hoja y recalculaba todo (varios segundos). La respuesta
// de construirDatosPanel_ se guarda en CacheService comprimida (gzip +
// base64: los mensajes originales de todos los picks pasan de los 100 KB
// que admite un solo valor) y troceada por si aun así no cabe.
// - TTL de 15 min y disparador refrescarCachePanel cada 10 min
//   (configurarTriggerCachePanel): la caché no llega a caducar nunca, así
//   que ningún visitante paga el cálculo. Retraso máximo de un cambio
//   hecho directamente en la hoja (o por la VM en resultados_galgos) en
//   verse en el panel: ~10 min.
// - Los cambios que pasan por el bot (doPost, resolverApuestasExoticas)
//   la invalidan al momento (invalidarCachePanel_), así que un "ganó"/
//   "perdió" se ve en la siguiente carga.
// - Si la caché falla por lo que sea, se calcula en directo como antes: la
//   caché nunca puede dejar el panel sin datos, solo hacerlo más rápido.
// El prefijo lleva versión: si cambia la forma de los datos, subir v1->v2
// para que no se lea nunca un formato viejo tras un despliegue.
const CACHE_PANEL_PREFIJO = 'panel_v1_';
const CACHE_PANEL_TTL_SEG = 15 * 60;
const CACHE_PANEL_TROZO = 90000; // < 100 KB por valor de CacheService

function serializarCachePanel_(datos) {
  const blob = Utilities.newBlob('', 'application/json').setDataFromString(JSON.stringify(datos), 'UTF-8');
  const b64 = Utilities.base64Encode(Utilities.gzip(blob).getBytes());
  const trozos = [];
  for (let i = 0; i < b64.length; i += CACHE_PANEL_TROZO) {
    trozos.push(b64.slice(i, i + CACHE_PANEL_TROZO));
  }
  return trozos;
}

function deserializarCachePanel_(trozos) {
  const bytes = Utilities.base64Decode(trozos.join(''));
  const json = Utilities.ungzip(Utilities.newBlob(bytes, 'application/x-gzip')).getDataAsString('UTF-8');
  return JSON.parse(json);
}

function guardarCachePanel_(datos) {
  const trozos = serializarCachePanel_(datos);
  const valores = {};
  trozos.forEach(function (t, i) { valores[CACHE_PANEL_PREFIJO + i] = t; });
  // El índice va en el mismo putAll que los trozos: si no está, no se lee.
  valores[CACHE_PANEL_PREFIJO + 'n'] = String(trozos.length);
  CacheService.getScriptCache().putAll(valores, CACHE_PANEL_TTL_SEG);
}

/** null si no hay caché (o falta algún trozo) - nunca lanza. */
function leerCachePanel_() {
  try {
    const cache = CacheService.getScriptCache();
    const n = Number(cache.get(CACHE_PANEL_PREFIJO + 'n'));
    if (!n) return null;
    const claves = [];
    for (let i = 0; i < n; i++) claves.push(CACHE_PANEL_PREFIJO + i);
    const valores = cache.getAll(claves);
    const trozos = claves.map(function (k) { return valores[k]; });
    if (trozos.some(function (t) { return !t; })) return null;
    return deserializarCachePanel_(trozos);
  } catch (err) {
    Logger.log('leerCachePanel_: ' + err);
    return null;
  }
}

/** Basta con borrar el índice: sin él leerCachePanel_ ya no lee los trozos. */
function invalidarCachePanel_() {
  try {
    CacheService.getScriptCache().remove(CACHE_PANEL_PREFIJO + 'n');
  } catch (err) {
    Logger.log('invalidarCachePanel_: ' + err);
  }
}

/**
 * Llamada desde el cliente (Panel.html) vía google.script.run cuando la
 * página no trae ya los datos incrustados (ver doGet) o al pulsar
 * "Reintentar". Sirve de la caché si la hay; si no, calcula y la rellena.
 */
function getMetricasPanel() {
  const enCache = leerCachePanel_();
  if (enCache) return enCache;
  const datos = construirDatosPanel_();
  try {
    guardarCachePanel_(datos);
  } catch (err) {
    Logger.log('getMetricasPanel: no se pudo guardar en caché: ' + err);
  }
  return datos;
}

/**
 * Lo llama el disparador de configurarTriggerCachePanel: recalcula SIEMPRE
 * (no mira la caché) y la reescribe, para que los visitantes nunca la
 * encuentren caducada.
 */
function refrescarCachePanel() {
  guardarCachePanel_(construirDatosPanel_());
}

/**
 * Ejecutar UNA VEZ a mano desde el editor para instalar el disparador
 * periódico - mismo patrón que configurarTriggerReintentos (Main.gs). Sin
 * él el panel sigue funcionando (la caché se rellena en la primera visita
 * tras caducar), solo que esa visita va lenta.
 */
function configurarTriggerCachePanel() {
  ScriptApp.getProjectTriggers().forEach(function (t) {
    if (t.getHandlerFunction() === 'refrescarCachePanel') {
      ScriptApp.deleteTrigger(t);
    }
  });
  ScriptApp.newTrigger('refrescarCachePanel').timeBased().everyMinutes(10).create();
  refrescarCachePanel();
  Logger.log('Disparador instalado: refrescarCachePanel cada 10 minutos (y caché ya rellenada).');
}

/**
 * Ejecutar A MANO desde el editor (Ejecutar > test_cachePanel) tras cada
 * cambio en la serialización - mismo patrón que los demás test_ de este
 * archivo. No toca la caché real: solo comprueba ida y vuelta.
 */
function test_cachePanel() {
  // Texto pseudoaleatorio (comprime mal) para forzar más de un trozo.
  let semilla = 1;
  let ruido = '';
  for (let i = 0; i < 200000; i++) {
    semilla = (semilla * 16807) % 2147483647;
    ruido += String.fromCharCode(33 + Math.floor(semilla / 65536) % 90);
  }
  const datos = { hayDatos: true, roiPct: 12.3, pctCuotaBajada: null, historicoPicks: [{ mensaje: 'ñ € 🐕 </script> ' + ruido }] };
  const trozos = serializarCachePanel_(datos);
  if (trozos.length < 2) throw new Error('FALLO en test_cachePanel: se esperaban varios trozos, hay ' + trozos.length);
  const vuelta = deserializarCachePanel_(trozos);
  assertIguales_(JSON.stringify(vuelta), JSON.stringify(datos), 'ida y vuelta de la caché (varios trozos, acentos, emoji, null)');
  Logger.log('test_cachePanel: OK, todas las comprobaciones pasaron.');
}

/**
 * JSON para incrustar dentro de un <script> del HTML: se escapan "<"
 * (un "</script>" dentro de un mensaje de Telegram cerraría la etiqueta)
 * y los separadores de línea U+2028/U+2029 (válidos en JSON, no en JS
 * antiguo). Sigue siendo JSON válido, JSON.parse da lo mismo.
 */
function jsonParaScript_(datos) {
  return JSON.stringify(datos)
    .replace(/</g, '\\u003c')
    .replace(/\u2028/g, '\\u2028')
    .replace(/\u2029/g, '\\u2029');
}

/**
 * Lee `apuestas` completa y la deja en la forma que usan calcularMetricas_/
 * calcularHistoricoPicks_. Compartida por el panel (getMetricasPanel) y las
 * estadísticas de Telegram (Estadisticas.gs), para que los dos cuenten
 * exactamente lo mismo.
 */
function obtenerFilasApuestas_() {
  const sheet = getSheet_(SHEET_APUESTAS);
  const index = getHeaderIndex_(sheet);

  const datos = leerFilasConDatos_(sheet, index);
  return datos.map(function (fila) {
    return {
      messageId: String(fila[index['message_id']] || ''),
      oculto: fila[index['oculto']] === true,
      resultadoFinal: fila[index['resultado_final']],
      unidadesNetas: fila[index['unidades_netas']],
      stake: fila[index['stake']],
      cuota: fila[index['cuota']],
      cuotaFinal: fila[index['cuota_final']],
      fechaPick: fila[index['fecha_pick']],
      canodromo: fila[index['canodromo']],
      galgo: fila[index['galgo']],
      mensaje: fila[index['mensaje']],
    };
  });
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
/** Contenido de un .html del proyecto, para incluirlo desde Panel.html (`<?!= incluirHtml_('X') ?>`). */
function incluirHtml_(nombre) {
  return HtmlService.createHtmlOutputFromFile(nombre).getContent();
}

/** Lo de dentro de la primera etiqueta <tag>...</tag> de un .html del proyecto. */
function interiorDeEtiqueta_(nombre, tag) {
  const html = incluirHtml_(nombre);
  const ini = html.indexOf('<' + tag + '>');
  const fin = html.lastIndexOf('</' + tag + '>');
  if (ini === -1 || fin === -1) throw new Error('Falta <' + tag + '> en ' + nombre + '.html');
  return html.slice(ini + tag.length + 2, fin);
}

const FUENTES_PANEL_URL = 'https://fonts.googleapis.com/css2?family=Inter+Tight:wght@400;500;600;700;800&family=Inter:wght@400;500;600&display=swap';

/**
 * Panel para WordPress (2026-10-18, ver docs/BITACORA.md). El iframe a
 * script.google.com fallaba con "No se puede abrir el archivo en estos
 * momentos" (pantalla de Google Drive) a cualquier visitante con sesión de
 * Google abierta en el navegador, sobre todo con varias cuentas: el iframe
 * lleva las cookies de Google y Google lo enruta por /u/N/, que falla con
 * las apps web anónimas. Fallo de Google, sin arreglo desde el panel.
 *
 * Solución: el bloque de WordPress (docs/wordpress-panel.html) pide este
 * JS con fetch(..., {credentials: 'omit'}) - SIN cookies, siempre anónimo -
 * y lo ejecuta. Monta el panel en un Shadow DOM (sus estilos no chocan con
 * los del tema y viceversa) con las MISMAS piezas que Panel.html
 * (PanelEstilos/PanelCuerpo/PanelScript), y los datos de la caché ya
 * dentro; si la caché está fría, los pide a ?formato=json, también sin
 * cookies. Cambiar el panel = clasp push + desplegar, sin tocar WordPress.
 */
function construirScriptWordpress_() {
  // En el Shadow DOM no hay <html>/<body> ni :root: esas reglas pasan a
  // .pg-raiz, un envoltorio DENTRO del shadow. No vale ponerlas en :host:
  // las reglas del tema que caigan sobre el propio div#pg-panel ganan a
  // :host, y lo heredable (color, tamaño de letra...) se colaría dentro
  // (visto en la prueba con un tema agresivo). Al envoltorio no llega
  // ninguna regla del tema, y se le fija también lo heredable que el panel
  // no define (lo que en una página normal pondría el navegador).
  const css = interiorDeEtiqueta_('PanelEstilos', 'style')
    .replace(':root{', '.pg-raiz{')
    .replace('html,body{', '.pg-raiz{');
  const reinicio = ':host{display:block;min-height:100%}' +
    '.pg-raiz{min-height:100%;font-size:16px;line-height:normal;letter-spacing:normal;word-spacing:normal;' +
    'text-transform:none;text-align:left;text-indent:0;font-weight:400;font-style:normal;white-space:normal}';
  const cuerpo = '<div class="pg-raiz">' + incluirHtml_('PanelCuerpo') + '</div>';
  const script = interiorDeEtiqueta_('PanelScript', 'script');
  let urlServidor = '';
  try { urlServidor = ScriptApp.getService().getUrl() || ''; } catch (err) { /* el bloque de WordPress la pasa igualmente */ }
  return [
    '(function(){',
    '  var host = document.getElementById("pg-panel");',
    '  if (!host || host.shadowRoot) return;',
    '  var urlPanel = window.PG_PANEL_URL || ' + JSON.stringify(urlServidor) + ';',
    '  if (!document.getElementById("pg-panel-fuentes")) {',
    '    var l = document.createElement("link"); l.id = "pg-panel-fuentes"; l.rel = "stylesheet";',
    '    l.href = ' + JSON.stringify(FUENTES_PANEL_URL) + '; document.head.appendChild(l);',
    '  }',
    '  var root = host.attachShadow({ mode: "open" });',
    '  root.innerHTML = "<style>" + ' + jsonParaScript_(reinicio + css) + ' + "</style>" + ' + jsonParaScript_(cuerpo) + ';',
    script,
    '  iniciarPanelPG(root, ' + jsonParaScript_(leerCachePanel_()) + ', function(ok, fallo){',
    '    fetch(urlPanel + "?formato=json", { credentials: "omit" })',
    '      .then(function(r){ if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })',
    '      .then(function(d){ if (d && d.error) fallo({ message: d.error }); else ok(d); }, fallo);',
    '  });',
    '})();',
  ].join('\n');
}

function doGet(e) {
  const formato = e && e.parameter && e.parameter.formato;
  if (formato === 'json') {
    let datos;
    try {
      datos = getMetricasPanel();
    } catch (err) {
      Logger.log('doGet formato=json: ' + err);
      datos = { error: String(err && err.message || err) };
    }
    return ContentService.createTextOutput(JSON.stringify(datos)).setMimeType(ContentService.MimeType.JSON);
  }
  if (formato === 'js') {
    return ContentService.createTextOutput(construirScriptWordpress_()).setMimeType(ContentService.MimeType.JAVASCRIPT);
  }

  const plantilla = HtmlService.createTemplateFromFile('Panel');
  // Si la caché está caliente, los datos van ya dentro del HTML y el panel
  // se pinta sin el segundo viaje de google.script.run (que es lo que más
  // tardaba). Si no, "null" y Panel.html los pide como siempre - aquí NO
  // se calcula nunca en directo: dejaría la página en blanco (sin el
  // esqueleto de carga) mientras tanto.
  plantilla.datosInicialesJson = jsonParaScript_(leerCachePanel_());
  return plantilla
    .evaluate()
    .setTitle('Panel de métricas - Picks Premier Galgos')
    // El <meta name="viewport"> de Panel.html no basta: Apps Script sirve el
    // panel dentro de un iframe, y la página EXTERIOR (la de Google) no lo
    // lleva - en el móvil, abriendo el enlace directo, se pintaba a 980 px
    // de ancho (diseño de escritorio encogido). Visto con Playwright
    // 2026-10-18. Dentro de WordPress no pasaba (manda el viewport de la web).
    .addMetaTag('viewport', 'width=device-width, initial-scale=1')
    // Permite que el panel se incruste en un <iframe> desde otro dominio
    // (petición del dueño: quiere el panel dentro de su web de WordPress).
    // Por defecto Apps Script solo deja enmarcarlo desde el propio Google -
    // sin esto, el iframe de WordPress se quedaría en blanco/bloqueado.
    .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL);
}
