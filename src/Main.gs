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
  let fotoBlob = null;
  if (fotoFileId) {
    fotoBlob = downloadTelegramPhoto(fotoFileId);
  }

  let resultado;
  try {
    resultado = extraerPick(texto, fotoBlob);
  } catch (err) {
    Logger.log('Fallo llamando a la IA de extracción: ' + err);
    actualizarEstadoMensajeCrudo_(msg.message_id, ESTADO_ERROR);
    sendTelegramMessage(msg.chat.id,
      'No he podido procesar este pick (fallo llamando a la IA). Lo he guardado en crudo, revísalo a mano.',
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
