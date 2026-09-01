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
 * Lee `apuestas_patas` completa de una vez (igual que Auditoria.gs, más
 * barato que una lectura por fila) y la agrupa por `message_id`, una
 * entrada por CARRERA del pick (dobles/triples incluidos), ordenadas por
 * `numero_pata`. Filas sin hora_carrera interpretable se excluyen (nada
 * que mostrar para esa pata).
 */
function obtenerPatasPorMensaje_() {
  const sheet = getSheet_(SHEET_APUESTAS_PATAS);
  const index = getHeaderIndex_(sheet);
  const lastRow = sheet.getLastRow();
  const porMensaje = {};
  if (lastRow < 2) return porMensaje;

  const datos = sheet.getRange(2, 1, lastRow - 1, sheet.getLastColumn()).getValues();
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

  const patasPorMensaje = obtenerPatasPorMensaje_();

  const historicoPicks = calcularHistoricoPicks_(filas).map(function (p) {
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

  const metricas = calcularMetricas_(filas);
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
