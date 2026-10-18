/**
 * Wrapper mínimo sobre la Bot API de Telegram vía UrlFetchApp.
 */

function telegramApiUrl_(method) {
  return 'https://api.telegram.org/bot' + getBotToken_() + '/' + method;
}

function sendTelegramMessage(chatId, text, replyToMessageId) {
  const payload = {
    chat_id: chatId,
    text: text,
    reply_to_message_id: replyToMessageId,
  };
  const response = UrlFetchApp.fetch(telegramApiUrl_('sendMessage'), {
    method: 'post',
    contentType: 'application/json',
    payload: JSON.stringify(payload),
    muteHttpExceptions: true,
  });
  const body = JSON.parse(response.getContentText());
  if (!body.ok) {
    Logger.log('Error enviando mensaje a Telegram: ' + response.getContentText());
    return null;
  }
  return body.result.message_id;
}

/**
 * Descarga una foto de Telegram por file_id y la devuelve como Blob, lista
 * para mandar a la API de la IA de visión.
 */
function downloadTelegramPhoto(fileId) {
  const getFileResp = UrlFetchApp.fetch(telegramApiUrl_('getFile') + '?file_id=' + fileId, {
    muteHttpExceptions: true,
  });
  const getFileBody = JSON.parse(getFileResp.getContentText());
  if (!getFileBody.ok) {
    throw new Error('No se pudo resolver file_id ' + fileId + ': ' + getFileResp.getContentText());
  }
  const filePath = getFileBody.result.file_path;
  const fileUrl = 'https://api.telegram.org/file/bot' + getBotToken_() + '/' + filePath;
  const fileResp = UrlFetchApp.fetch(fileUrl, { muteHttpExceptions: true });
  return fileResp.getBlob();
}

/**
 * Para revisar a mano la foto (boleto) de un pick desde fuera del editor:
 * `clasp run-function fotoDeMensajeBase64 --params '["32"]'`. Devuelve la
 * imagen en base64, o null si el mensaje no tiene foto.
 */
function fotoDeMensajeBase64(messageId) {
  const sheet = getSheet_(SHEET_MENSAJES_CRUDOS);
  const index = getHeaderIndex_(sheet);
  const datos = sheet.getRange(2, 1, sheet.getLastRow() - 1, sheet.getLastColumn()).getValues();
  const fila = datos.filter(function (f) { return String(f[index['message_id']]) === String(messageId); })[0];
  if (!fila || !fila[index['foto_file_id']]) return null;
  return Utilities.base64Encode(downloadTelegramPhoto(fila[index['foto_file_id']]).getBytes());
}

function mejorFotoFileId(photoArray) {
  if (!photoArray || photoArray.length === 0) return null;
  // Telegram devuelve las resoluciones de menor a mayor.
  return photoArray[photoArray.length - 1].file_id;
}
