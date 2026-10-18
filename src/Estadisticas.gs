/**
 * Estadísticas por periodo para Telegram (pedido del dueño, 2026-09-25):
 * - Resumen semanal: todos los lunes hacia las 7:00 (Madrid) se envía al grupo
 *   del bot el resumen de la semana anterior (lunes a domingo).
 * - Comando `/stats N` en el grupo: lo mismo para los últimos N días
 *   (contando hoy); `/stats` sin número = 7 días.
 *
 * Mismos criterios que el panel (calcularMetricas_): simples, combinadas y
 * exóticas, sin las ocultas, solo las resueltas (gano/perdio). Todo en
 * UNIDADES (regla de CLAUDE.md: los euros solo en el panel). El periodo se
 * mide por `fecha_pick` (fecha de la carrera), en hora de Madrid.
 *
 * Se envían DOS mensajes: el primero con las estadísticas y, solo si hay
 * alguna apuesta del periodo sin resultado, un segundo con cuántas quedan
 * pendientes.
 */

const STATS_DIAS_POR_DEFECTO = 7;
const STATS_DIAS_MAX = 365;
const STATS_ZONA = 'Europe/Madrid';
const STATS_FORMATO_COMANDO = 'Formato: /stats o /stats N (N = días, entre 1 y ' + STATS_DIAS_MAX + ').';

// --- Fechas como clave 'yyyy-MM-dd' en hora de Madrid (sin depender de la
// zona horaria del runtime ni de cambios de hora) ---

function claveDiaMadrid_(fecha) {
  return Utilities.formatDate(fecha, STATS_ZONA, 'yyyy-MM-dd');
}

function sumarDiasClave_(clave, dias) {
  const p = clave.split('-').map(Number);
  return Utilities.formatDate(new Date(Date.UTC(p[0], p[1] - 1, p[2] + dias, 12)), 'UTC', 'yyyy-MM-dd');
}

function etiquetaClave_(clave) {
  const p = clave.split('-');
  return p[2] + '/' + p[1];
}

/** Semana anterior a `ahora`: de lunes a domingo, ambos incluidos. */
function rangoSemanaAnterior_(ahora) {
  const hoy = claveDiaMadrid_(ahora);
  const diaSemana = Number(Utilities.formatDate(ahora, STATS_ZONA, 'u')); // 1 = lunes ... 7 = domingo
  const lunesEstaSemana = sumarDiasClave_(hoy, -(diaSemana - 1));
  return { desde: sumarDiasClave_(lunesEstaSemana, -7), hasta: sumarDiasClave_(lunesEstaSemana, -1) };
}

/** Últimos `dias` días contando hoy. */
function rangoUltimosDias_(ahora, dias) {
  const hoy = claveDiaMadrid_(ahora);
  return { desde: sumarDiasClave_(hoy, -(dias - 1)), hasta: hoy };
}

// --- Cálculo ---

/**
 * filas: misma forma que usa calcularMetricas_ (obtenerFilasApuestas_ +
 * obtenerFilasExoticasNormalizadas_). Las filas sin message_id son las
 * vacías con fórmula de la hoja y se ignoran.
 */
function calcularEstadisticasPeriodo_(filas, rango) {
  const delPeriodo = filas.filter(function (f) {
    if (!f.messageId || f.oculto === true || !(f.fechaPick instanceof Date)) return false;
    const clave = claveDiaMadrid_(f.fechaPick);
    return clave >= rango.desde && clave <= rango.hasta;
  });
  const resueltas = delPeriodo.filter(function (f) {
    return f.resultadoFinal === 'gano' || f.resultadoFinal === 'perdio';
  });
  const pendientes = delPeriodo.filter(function (f) { return f.resultadoFinal === 'pendiente'; }).length;

  const ganadas = resueltas.filter(function (f) { return f.resultadoFinal === 'gano'; }).length;
  const metricas = calcularMetricas_(resueltas);
  return {
    resueltas: resueltas.length,
    ganadas: ganadas,
    perdidas: resueltas.length - ganadas,
    unidadesNetas: metricas.hayDatos ? metricas.unidadesNetas : 0,
    roiPct: metricas.hayDatos ? metricas.roiPct : 0,
    pctAciertos: metricas.hayDatos ? metricas.pctAciertos : 0,
    pendientes: pendientes,
  };
}

// --- Textos ---

function formatearNumeroEs_(n, decimales, conSigno) {
  const redondeado = Math.round(n * Math.pow(10, decimales)) / Math.pow(10, decimales);
  const signo = conSigno && redondeado > 0 ? '+' : '';
  return signo + redondeado.toFixed(decimales).replace('.', ',');
}

/** Devuelve [mensaje de estadísticas, mensaje de pendientes o null]. */
function construirTextosEstadisticas_(titulo, rango, stats) {
  const cabecera = '📊 ' + titulo + ' · ' + etiquetaClave_(rango.desde) +
    (rango.desde === rango.hasta ? '' : ' – ' + etiquetaClave_(rango.hasta));
  let principal;
  if (stats.resueltas === 0) {
    principal = cabecera + '\nSin apuestas resueltas.';
  } else {
    principal = [
      cabecera,
      'Apuestas resueltas: ' + stats.resueltas + ' (' + stats.ganadas + ' ganadas, ' + stats.perdidas + ' perdidas)',
      'Unidades: ' + formatearNumeroEs_(stats.unidadesNetas, 2, true) + ' UD',
      'ROI: ' + formatearNumeroEs_(stats.roiPct, 1, true) + ' %',
      'Acierto: ' + formatearNumeroEs_(stats.pctAciertos, 1, false) + ' %',
    ].join('\n');
  }
  const pendientes = stats.pendientes > 0 ? 'Pendientes de resultado: ' + stats.pendientes : null;
  return [principal, pendientes];
}

function tituloUltimosDias_(dias) {
  return dias === 1 ? 'Último día' : 'Últimos ' + dias + ' días';
}

// --- Comando /stats ---

/**
 * null si el texto no es el comando. Si lo es: { dias } o { error }.
 * Acepta "/stats", "/stats 30" y "/stats@nombre_bot 30" (Telegram añade el
 * @bot en los grupos cuando se elige el comando del menú).
 */
function parsearComandoStats_(texto) {
  const m = String(texto || '').trim().match(/^\/stats(?:@\w+)?(?:\s+(.*))?$/i);
  if (!m) return null;
  const arg = (m[1] || '').trim();
  if (!arg) return { dias: STATS_DIAS_POR_DEFECTO };
  if (!/^\d+$/.test(arg)) return { error: STATS_FORMATO_COMANDO };
  const dias = Number(arg);
  if (dias < 1 || dias > STATS_DIAS_MAX) return { error: STATS_FORMATO_COMANDO };
  return { dias: dias };
}

function textosComandoStats_(comando, ahora, filas) {
  if (comando.error) return [comando.error, null];
  const rango = rangoUltimosDias_(ahora, comando.dias);
  return construirTextosEstadisticas_(tituloUltimosDias_(comando.dias), rango,
    calcularEstadisticasPeriodo_(filas, rango));
}

/** Llamada desde doPost (Main.gs). */
function manejarComandoStats_(msg, comando) {
  const filas = comando.error ? [] : leerFilasEstadisticas_();
  const textos = textosComandoStats_(comando, new Date(), filas);
  enviarTextosEstadisticas_(msg.chat.id, textos, msg.message_id);
  actualizarEstadoMensajeCrudo_(msg.message_id, ESTADO_PROCESADO);
}

// --- Resumen semanal ---

function leerFilasEstadisticas_() {
  return obtenerFilasApuestas_().concat(obtenerFilasExoticasNormalizadas_());
}

function textosResumenSemanal_(ahora, filas) {
  const rango = rangoSemanaAnterior_(ahora);
  return construirTextosEstadisticas_('Resumen semanal', rango, calcularEstadisticasPeriodo_(filas, rango));
}

function enviarTextosEstadisticas_(chatId, textos, replyTo) {
  sendTelegramMessage(chatId, textos[0], replyTo);
  if (textos[1]) sendTelegramMessage(chatId, textos[1], replyTo);
}

/** La ejecuta el trigger de los lunes. */
function enviarResumenSemanal() {
  enviarTextosEstadisticas_(TELEGRAM_CHAT_ID, textosResumenSemanal_(new Date(), leerFilasEstadisticas_()));
}

/**
 * Devuelve el texto que se enviaría ahora, SIN enviarlo (para revisarlo con
 * `clasp run-function previsualizarResumenSemanal`). `dias` opcional:
 * previsualiza "/stats dias" en vez del resumen semanal.
 */
function previsualizarResumenSemanal(dias) {
  const filas = leerFilasEstadisticas_();
  const textos = dias ? textosComandoStats_({ dias: Number(dias) }, new Date(), filas)
    : textosResumenSemanal_(new Date(), filas);
  return textos.filter(Boolean).join('\n\n---\n\n');
}

/**
 * Ejecutar UNA vez (idempotente: borra el trigger anterior si lo hay).
 * Apps Script no permite fijar el minuto: se ejecuta entre las 7:00 y las 8:00.
 */
function configurarTriggerResumenSemanal() {
  ScriptApp.getProjectTriggers().forEach(function (t) {
    if (t.getHandlerFunction() === 'enviarResumenSemanal') ScriptApp.deleteTrigger(t);
  });
  ScriptApp.newTrigger('enviarResumenSemanal').timeBased()
    .onWeekDay(ScriptApp.WeekDay.MONDAY).atHour(7).nearMinute(0)
    .inTimezone(STATS_ZONA).create();
  Logger.log('Disparador instalado: enviarResumenSemanal los lunes a las 7:00 (Madrid).');
  return 'ok';
}

// --- Tests (clasp run-function test_estadisticas) ---

function test_estadisticas() {
  // Fechas a mediodía de Madrid para no depender de la hora.
  function d(clave) { const p = clave.split('-').map(Number); return new Date(Date.UTC(p[0], p[1] - 1, p[2], 10)); }

  // Rangos. 2026-09-28 es lunes; 2026-09-27, domingo.
  let r = rangoSemanaAnterior_(d('2026-09-28'));
  assertIguales_(r.desde + '/' + r.hasta, '2026-09-21/2026-09-27', 'semana anterior desde un lunes');
  r = rangoSemanaAnterior_(d('2026-09-27'));
  assertIguales_(r.desde + '/' + r.hasta, '2026-09-14/2026-09-20', 'semana anterior desde un domingo');
  r = rangoUltimosDias_(d('2026-09-25'), 7);
  assertIguales_(r.desde + '/' + r.hasta, '2026-09-19/2026-09-25', 'ultimos 7 dias');
  r = rangoUltimosDias_(d('2026-10-02'), 5);
  assertIguales_(r.desde + '/' + r.hasta, '2026-09-28/2026-10-02', 'ultimos dias cruzando de mes');
  r = rangoUltimosDias_(d('2026-03-30'), 3);
  assertIguales_(r.desde + '/' + r.hasta, '2026-03-28/2026-03-30', 'ultimos dias cruzando cambio de hora');

  // Cálculo.
  const filas = [
    { messageId: '1', oculto: false, resultadoFinal: 'gano', unidadesNetas: 6, stake: 4, fechaPick: d('2026-09-21') },
    { messageId: '2', oculto: false, resultadoFinal: 'perdio', unidadesNetas: -5, stake: 5, fechaPick: d('2026-09-27') },
    { messageId: '3', oculto: false, resultadoFinal: 'perdio', unidadesNetas: -3, stake: 3, fechaPick: d('2026-09-24') },
    { messageId: '4', oculto: false, resultadoFinal: 'pendiente', unidadesNetas: '', stake: 2, fechaPick: d('2026-09-27') },
    { messageId: '5', oculto: true, resultadoFinal: 'gano', unidadesNetas: 100, stake: 1, fechaPick: d('2026-09-22') },
    { messageId: '6', oculto: false, resultadoFinal: 'gano', unidadesNetas: 50, stake: 5, fechaPick: d('2026-09-20') },
    { messageId: '7', oculto: false, resultadoFinal: 'gano', unidadesNetas: 50, stake: 5, fechaPick: d('2026-09-28') },
    { messageId: '', oculto: false, resultadoFinal: 'pendiente', unidadesNetas: '', stake: '', fechaPick: '' },
  ];
  const semana = { desde: '2026-09-21', hasta: '2026-09-27' };
  const s = calcularEstadisticasPeriodo_(filas, semana);
  assertIguales_(s.resueltas, 3, 'resueltas (sin ocultas ni fuera de rango)');
  assertIguales_(s.ganadas + '/' + s.perdidas, '1/2', 'ganadas/perdidas');
  assertIguales_(s.unidadesNetas, -2, 'unidades netas');
  assertIguales_(Math.round(s.roiPct * 10) / 10, -16.7, 'ROI = -2 / 12');
  assertIguales_(Math.round(s.pctAciertos * 10) / 10, 33.3, 'acierto');
  assertIguales_(s.pendientes, 1, 'pendientes (sin filas vacias de formula)');

  let textos = construirTextosEstadisticas_('Resumen semanal', semana, s);
  assertIguales_(textos[0], '📊 Resumen semanal · 21/09 – 27/09\nApuestas resueltas: 3 (1 ganadas, 2 perdidas)\n' +
    'Unidades: -2,00 UD\nROI: -16,7 %\nAcierto: 33,3 %', 'texto principal');
  assertIguales_(textos[1], 'Pendientes de resultado: 1', 'texto pendientes');

  textos = construirTextosEstadisticas_('Resumen semanal', semana,
    calcularEstadisticasPeriodo_([filas[0]], semana));
  assertIguales_(textos[0].split('\n')[2] + ' | ' + textos[0].split('\n')[3], 'Unidades: +6,00 UD | ROI: +150,0 %', 'signo +');
  assertIguales_(textos[1], null, 'sin pendientes no hay segundo mensaje');

  textos = construirTextosEstadisticas_('Último día', { desde: '2026-09-25', hasta: '2026-09-25' },
    calcularEstadisticasPeriodo_([], semana));
  assertIguales_(textos[0], '📊 Último día · 25/09\nSin apuestas resueltas.', 'periodo vacio');

  // Comando.
  function c(t) { return JSON.stringify(parsearComandoStats_(t)); }
  assertIguales_(c('/stats'), '{"dias":7}', '/stats');
  assertIguales_(c('/stats 30'), '{"dias":30}', '/stats 30');
  assertIguales_(c('  /STATS   30 '), '{"dias":30}', 'mayusculas y espacios');
  assertIguales_(c('/stats@PremierGalgosBot 14'), '{"dias":14}', '/stats@bot');
  assertIguales_(c('/stats abc'), JSON.stringify({ error: STATS_FORMATO_COMANDO }), '/stats abc');
  assertIguales_(c('/stats 0'), JSON.stringify({ error: STATS_FORMATO_COMANDO }), '/stats 0');
  assertIguales_(c('/stats 366'), JSON.stringify({ error: STATS_FORMATO_COMANDO }), '/stats 366');
  assertIguales_(c('/stats 7 30'), JSON.stringify({ error: STATS_FORMATO_COMANDO }), 'dos argumentos');
  assertIguales_(c('/statsx'), 'null', 'otro comando');
  assertIguales_(c('21:10 Central Park T6 Galgo'), 'null', 'un pick normal');
  assertIguales_(c(''), 'null', 'texto vacio');

  Logger.log('test_estadisticas: OK');
  return 'OK';
}
