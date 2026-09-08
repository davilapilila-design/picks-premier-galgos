/**
 * Webhook de Telegram. Ver PLAN.md secciones 3, 6 y 10 para el porqué de
 * cada decisión (token por query param, LockService, guardar crudo
 * siempre antes de procesar, etc.).
 */

function doPost(e) {
  const lock = LockService.getScriptLock();
  try {
    // OJO: waitLock() va DENTRO del try - si no, un timeout lanza una
    // excepción sin capturar (bug real encontrado 2026-08-26 revisando un
    // incidente de datos en mensajes_crudos: no se confirmó que fuera la
    // causa de ESE incidente en concreto, pero es un fallo real de todas
    // formas). 120s en vez de 30s: con los reintentos de Gemini ante 429
    // (hasta 21s extra, ver AI.gs), dos mensajes casi seguidos tardan más
    // en total, y 30s se quedaba corto de margen para que el segundo
    // esperara su turno sin problemas.
    lock.waitLock(120000);
  } catch (err) {
    Logger.log('No se pudo adquirir el lock tras 120s: ' + err);
    return HtmlService.createHtmlOutput('locked');
  }
  try {
    if (!e.parameter || e.parameter.token !== getWebhookToken_()) {
      return HtmlService.createHtmlOutput('forbidden');
    }

    const update = JSON.parse(e.postData.contents);
    const msg = update.message;
    if (!msg) {
      return HtmlService.createHtmlOutput('ok'); // otros tipos de update, se ignoran
    }

    if (mensajeCrudoYaExiste(msg.message_id)) {
      // Reintento del webhook de Telegram sobre un mensaje ya procesado.
      return HtmlService.createHtmlOutput('ok');
    }

    const texto = msg.caption || msg.text || '';
    const fotoFileId = mejorFotoFileId(msg.photo);
    const fechaRecibido = new Date(msg.date * 1000);
    const fechaForward = extraerFechaForward_(msg);

    appendMensajeCrudo(msg.message_id, fechaRecibido, texto, fotoFileId, ESTADO_PENDIENTE, fechaForward);

    if (msg.reply_to_message) {
      manejarReply_(msg, texto);
    } else {
      manejarPickNuevo_(msg, texto, fotoFileId, fechaRecibido, fechaForward);
    }

    return HtmlService.createHtmlOutput('ok');
  } catch (err) {
    Logger.log('Error en doPost: ' + err + '\n' + err.stack);
    return HtmlService.createHtmlOutput('error');
  } finally {
    lock.releaseLock();
  }
}

function manejarReply_(msg, texto) {
  const confirmMessageId = msg.reply_to_message.message_id;
  const respuesta = procesarComandoReply(texto, confirmMessageId);
  if (respuesta) {
    sendTelegramMessage(msg.chat.id, respuesta, msg.message_id);
  }
  actualizarEstadoMensajeCrudo_(msg.message_id, ESTADO_PROCESADO);
}

function manejarPickNuevo_(msg, texto, fotoFileId, fechaRecibido, fechaForward) {
  // Descarga de foto y llamada a la IA van en el MISMO try/catch (bug real
  // encontrado 2026-09-02, ver docs/BITACORA.md): antes la descarga de la
  // foto estaba fuera de este bloque, así que si Telegram fallaba al
  // resolver el file_id (glitch puntual, límite de tasa...) la excepción
  // escapaba sin capturar hasta doPost, que no manda ningún mensaje - el
  // pick se perdía en silencio, con estado=pendiente para siempre y sin
  // fila en `apuestas`. Ambos fallos ahora acaban en el mismo sitio:
  // marcado como error y con aviso, para que reintentarMensajesConError()
  // (más abajo) lo recoja solo.
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

/**
 * Mensaje legible para el aviso de "necesita revisión manual" al tipster,
 * según el motivo devuelto por `extraerPick` (AI.gs).
 */
function motivoRevisionManual_(resultado) {
  if (resultado.motivo === 'tipo_no_soportado') {
    return 'tipo de apuesta no soportado todavía (' +
      (resultado.tipoApuesta || 'sin identificar') +
      ' - solo simples, dobles y tríples se procesan solas)';
  }
  if (resultado.motivo === 'num_patas_incorrecto') {
    return 'el número de carreras detectadas no cuadra con el tipo de apuesta';
  }
  return 'faltan datos (' + resultado.camposFaltantes.join(', ') + ')';
}

/**
 * Etiqueta + resumen de cada pata para la confirmación por Telegram.
 * Una simple queda igual que antes del rediseño ("Pick registrado: ...");
 * una doble/tríple lista las patas separadas por " + ".
 */
function construirTextoConfirmacion_(resultado) {
  const resumenPatas = resultado.patas.map(function (p) {
    return p.horaCarrera + ' ' + p.hipodromo + ' - T' + p.trampa + ' ' + p.seleccion;
  }).join(' + ');
  return 'Apuesta registrada (' + resultado.tipoApuesta + '): ' + resumenPatas +
    ' @' + resultado.cuota + ' (stake ' + resultado.stake + 'u)';
}

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

/**
 * Si el mensaje es un reenvío desde el canal del tipster, la fecha que
 * importa para cruzar con resultados_galgos es la de publicación original,
 * no la de reenvío al grupo (ver docs/BITACORA.md, backfill del histórico).
 * Devuelve `null` si no es un reenvío (para distinguirlo de "no lo sé" -
 * `fecha_forward` en mensajes_crudos se queda vacío en ese caso).
 *
 * Se calcula y se persiste en mensajes_crudos ANTES de saber si el pick se
 * procesa bien o da error - si no, un mensaje que erroraba por cuota de
 * Gemini agotada perdía esta información para siempre en el reintento
 * posterior (bug real encontrado 2026-08-26, ver docs/BITACORA.md: 11
 * reenvíos de picks antiguos se cargaron con la fecha de llegada en vez de
 * la real, y uno de ellos coincidió por casualidad con una carrera de otro
 * galgo en el mismo hipódromo+hora+trampa el día de llegada, dando un
 * resultado "perdió" falso vía el fallback de trampa ganadora).
 */
function extraerFechaForward_(msg) {
  if (msg.forward_date) {
    return new Date(msg.forward_date * 1000);
  }
  if (msg.forward_origin && msg.forward_origin.date) {
    return new Date(msg.forward_origin.date * 1000);
  }
  return null;
}

function actualizarEstadoMensajeCrudo_(messageId, estado) {
  const sheet = getSheet_(SHEET_MENSAJES_CRUDOS);
  const index = getHeaderIndex_(sheet);
  const lastRow = sheet.getLastRow();
  const ids = sheet.getRange(2, index['message_id'] + 1, lastRow - 1, 1).getValues();
  for (let i = 0; i < ids.length; i++) {
    if (String(ids[i][0]) === String(messageId)) {
      sheet.getRange(i + 2, index['estado'] + 1).setValue(estado);
      return;
    }
  }
}

function findApuestaByMessageIdRecienCreada_(messageId) {
  const sheet = getSheet_(SHEET_APUESTAS);
  const index = getHeaderIndex_(sheet);
  const lastRow = sheet.getLastRow();
  const ids = sheet.getRange(2, index['message_id'] + 1, lastRow - 1, 1).getValues();
  for (let i = ids.length - 1; i >= 0; i--) {
    if (String(ids[i][0]) === String(messageId)) {
      return { sheet: sheet, index: index, row: i + 2 };
    }
  }
  return null;
}

/**
 * Reintenta los mensajes que quedaron en estado "error" (fallo llamando a
 * la IA - típicamente cuota diaria de Gemini agotada, 20 peticiones/día en
 * el tier gratis de gemini-3.6-flash, ver docs/BITACORA.md 2026-08-26).
 * No se llama desde doPost - pensada para un disparador de tiempo, ver
 * `configurarTriggerReintentos()` más abajo (ejecutar una vez a mano desde
 * el editor, igual que `setupSheet`/`checkConfig`).
 *
 * Si el primer reintento de la lista sigue dando error, se corta ahí
 * mismo en vez de intentar los demás - lo más probable es que la cuota
 * siga agotada y todos fallarían igual, sin necesidad de gastar el tiempo
 * de ejecución en intentarlo con cada uno.
 */
function reintentarMensajesConError() {
  const lock = LockService.getScriptLock();
  try {
    lock.waitLock(120000);
  } catch (err) {
    Logger.log('reintentarMensajesConError: no se pudo adquirir el lock - ' + err);
    return;
  }

  try {
    const sheet = getSheet_(SHEET_MENSAJES_CRUDOS);
    const index = getHeaderIndex_(sheet);
    const lastRow = sheet.getLastRow();
    if (lastRow < 2) return;

    const datos = sheet.getRange(2, 1, lastRow - 1, sheet.getLastColumn()).getValues();
    let resueltos = 0;
    let revisionManual = 0;

    for (let i = 0; i < datos.length; i++) {
      const fila = datos[i];
      if (fila[index['estado']] !== ESTADO_ERROR) continue;

      const messageId = fila[index['message_id']];
      const fechaRecibido = fila[index['fecha_recibido']];
      const contenido = fila[index['contenido']];
      const fotoFileId = fila[index['foto_file_id']];
      const fechaForward = fila[index['fecha_forward']] || null;
      const filaSheet = i + 2;

      let fotoBlob = null;
      if (fotoFileId) {
        try {
          fotoBlob = downloadTelegramPhoto(fotoFileId);
        } catch (err) {
          Logger.log('Reintento ' + messageId + ': fallo descargando foto - ' + err);
          continue;
        }
      }

      let resultado;
      try {
        resultado = extraerPick(contenido, fotoBlob);
      } catch (err) {
        Logger.log('Reintento ' + messageId + ' sigue fallando: ' + err);
        if (String(err).indexOf('429') !== -1) {
          Logger.log('Parece seguir agotada la cuota - corto aquí, no sigo con el resto.');
          break;
        }
        continue;
      }

      if (!resultado.ok) {
        sheet.getRange(filaSheet, index['estado'] + 1).setValue(ESTADO_REVISION_MANUAL);
        sendTelegramMessage(TELEGRAM_CHAT_ID,
          'Pick guardado pero necesita revisión manual: ' + motivoRevisionManual_(resultado) + '.',
          messageId);
        revisionManual++;
        continue;
      }

      const fechaPick = fechaForward || fechaRecibido;
      appendApuestaConPatas(messageId, fechaPick, resultado.tipoApuesta, resultado.cuota, resultado.stake, resultado.patas);
      sheet.getRange(filaSheet, index['estado'] + 1).setValue(ESTADO_PROCESADO);

      const textoConfirmacion = construirTextoConfirmacion_(resultado);
      const confirmMessageId = sendTelegramMessage(TELEGRAM_CHAT_ID, textoConfirmacion, messageId);
      if (confirmMessageId) {
        const filaApuesta = findApuestaByMessageIdRecienCreada_(messageId);
        if (filaApuesta) setApuestaConfirmMessageId(filaApuesta.row, confirmMessageId);
      }
      resueltos++;
    }

    Logger.log('reintentarMensajesConError: ' + resueltos + ' resueltos, ' + revisionManual + ' a revisión manual.');
  } finally {
    lock.releaseLock();
  }
}

/**
 * Ejecutar UNA VEZ a mano desde el editor de Apps Script para instalar el
 * disparador periódico. Cada 2h en vez de más seguido - con solo 20
 * peticiones/día de cuota gratis, reintentar cada pocos minutos no ayuda a
 * que la cuota se libere antes, solo generaría más ejecuciones fallidas.
 */
function configurarTriggerReintentos() {
  ScriptApp.getProjectTriggers().forEach(function (t) {
    if (t.getHandlerFunction() === 'reintentarMensajesConError') {
      ScriptApp.deleteTrigger(t);
    }
  });
  ScriptApp.newTrigger('reintentarMensajesConError').timeBased().everyHours(2).create();
  Logger.log('Disparador instalado: reintentarMensajesConError cada 2 horas.');
}

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

/**
 * Reparación puntual (2026-09-02, ver docs/BITACORA.md) de picks que se
 * quedaron atascados en `pendiente` - no en `error` - por el bug real de
 * `manejarPickNuevo_` corregido arriba: `reintentarMensajesConError()`
 * solo recoge mensajes con estado=error, así que estos no se
 * reintentaban solos. Lista cerrada de `message_id` confirmados a mano
 * con `buscarPicksAtascados()` (Auditoria.gs) - no un heurístico
 * automático, para no arriesgarse a tocar una reply atascada de verdad
 * (que también puede salir en ese chequeo) y que el reintento intente
 * procesarla como si fuera un pick nuevo.
 *
 * Marca cada uno como `error` y lanza reintentarMensajesConError() en la
 * misma ejecución - un solo "Ejecutar" desde el editor basta.
 *
 * Ejecutar A MANO desde el editor de Apps Script, una sola vez.
 */
function repararPicksAtascados_2026_09_02() {
  const MESSAGE_IDS_CONFIRMADOS = ['214'];

  const sheet = getSheet_(SHEET_MENSAJES_CRUDOS);
  const index = getHeaderIndex_(sheet);
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) {
    Logger.log('mensajes_crudos está vacía, nada que reparar.');
    return;
  }
  const datos = sheet.getRange(2, 1, lastRow - 1, sheet.getLastColumn()).getValues();

  let marcados = 0;
  for (let i = 0; i < datos.length; i++) {
    const messageId = String(datos[i][index['message_id']]);
    if (MESSAGE_IDS_CONFIRMADOS.indexOf(messageId) === -1) continue;
    if (datos[i][index['estado']] !== ESTADO_PENDIENTE) {
      Logger.log('message_id=' + messageId + ' ya no está en pendiente (estado=' +
        datos[i][index['estado']] + '), no lo toco.');
      continue;
    }
    sheet.getRange(i + 2, index['estado'] + 1).setValue(ESTADO_ERROR);
    marcados++;
    Logger.log('message_id=' + messageId + ': estado cambiado de pendiente a error.');
  }

  Logger.log('Marcados ' + marcados + ' mensaje(s) como error. Lanzando reintentarMensajesConError()...');
  reintentarMensajesConError();
}
