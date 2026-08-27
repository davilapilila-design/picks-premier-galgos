/**
 * Acceso a la hoja de cálculo. Todas las escrituras se hacen por nombre de
 * columna (no por posición fija), para no depender del orden exacto en que
 * estén las columnas fórmula frente a las columnas de datos en la hoja.
 */

function getSheet_(nombre) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = ss.getSheetByName(nombre);
  if (!sheet) {
    throw new Error('No existe la pestaña "' + nombre + '"');
  }
  return sheet;
}

function getHeaderIndex_(sheet) {
  const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  const index = {};
  headers.forEach(function (h, i) {
    if (h) index[h] = i; // 0-based
  });
  return index;
}

function appendRowByHeader_(sheet, valoresPorColumna) {
  const index = getHeaderIndex_(sheet);
  // Solo hasta la última columna de DATOS que se va a escribir - nunca
  // hasta sheet.getLastColumn(), que en `apuestas` incluye las columnas
  // fórmula: escribirlas (aunque sea con '') las pisaría con celdas en
  // blanco en vez de dejar la fórmula que ya hubiera.
  let numColumnas = 0;
  Object.keys(valoresPorColumna).forEach(function (col) {
    if (!(col in index)) {
      throw new Error('Columna desconocida "' + col + '" en pestaña ' + sheet.getName());
    }
    numColumnas = Math.max(numColumnas, index[col] + 1);
  });

  const row = new Array(numColumnas).fill('');
  Object.keys(valoresPorColumna).forEach(function (col) {
    row[index[col]] = valoresPorColumna[col];
  });

  const fila = proximaFilaVacia_(sheet, index);
  sheet.getRange(fila, 1, 1, row.length).setValues([row]);
  clonarFormulasDeApuestas_(sheet, fila);
  return fila;
}

/**
 * `sheet.appendRow()`/`getLastRow()` no sirven aquí: en `apuestas` las
 * columnas fórmula vienen pre-rellenadas muchas filas por delante de los
 * datos reales (ver Setup.gs), así que `getLastRow()` devuelve esa fila
 * lejana y `appendRow` escribiría los datos ahí en vez de en la primera
 * fila realmente libre. Se busca por la columna `message_id` (columna A
 * en las dos pestañas que usan este helper), que nunca tiene fórmulas.
 */
function proximaFilaVacia_(sheet, index) {
  const colMessageId = index['message_id'] + 1;
  const ultimaFila = sheet.getLastRow();
  if (ultimaFila < 2) return 2;
  const valores = sheet.getRange(2, colMessageId, ultimaFila - 1, 1).getValues();
  for (let i = 0; i < valores.length; i++) {
    if (valores[i][0] === '') return i + 2;
  }
  return ultimaFila + 1;
}

/**
 * Si la fila en la que se acaba de escribir cae fuera del rango que
 * `setupSheet` pre-rellenó con fórmulas (más picks de los previstos en
 * `apuestas` o `apuestas_patas`), se clonan desde la fila 2 - las
 * referencias relativas se ajustan solas a la fila nueva.
 */
function clonarFormulasDeApuestas_(sheet, fila) {
  let columnasDatos;
  if (sheet.getName() === SHEET_APUESTAS) {
    columnasDatos = COLUMNAS_APUESTAS;
  } else if (sheet.getName() === SHEET_APUESTAS_PATAS) {
    columnasDatos = COLUMNAS_APUESTAS_PATAS;
  } else {
    return;
  }
  const primeraColFormula = columnasDatos.length + 1;
  const numColFormula = sheet.getLastColumn() - columnasDatos.length;
  if (numColFormula <= 0) return;
  const destino = sheet.getRange(fila, primeraColFormula, 1, numColFormula);
  if (destino.getFormula()) return; // ya tenía fórmula pre-rellenada
  sheet.getRange(2, primeraColFormula, 1, numColFormula).copyTo(destino);
}

function appendMensajeCrudo(messageId, fechaRecibido, contenido, fotoFileId, estado, fechaForward) {
  const sheet = getSheet_(SHEET_MENSAJES_CRUDOS);
  return appendRowByHeader_(sheet, {
    message_id: messageId,
    fecha_recibido: fechaRecibido,
    contenido: contenido,
    foto_file_id: fotoFileId || '',
    estado: estado,
    fecha_forward: fechaForward || '',
  });
}

function mensajeCrudoYaExiste(messageId) {
  const sheet = getSheet_(SHEET_MENSAJES_CRUDOS);
  const index = getHeaderIndex_(sheet);
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) return false;
  const ids = sheet.getRange(2, index['message_id'] + 1, lastRow - 1, 1).getValues();
  return ids.some(function (r) { return String(r[0]) === String(messageId); });
}

/**
 * Escribe la apuesta (1 fila en `apuestas`, la combinada entera) y sus
 * carreras (1 fila por pata en `apuestas_patas`) - rediseño 2026-08-26,
 * ver docs/BITACORA.md. `patas` es un array de
 * {hipodromo, horaCarrera, trampa, seleccion}, en el mismo orden en que
 * aparecen en el mensaje del tipster (numero_pata = posición + 1).
 */
function appendApuestaConPatas(messageId, fechaPick, tipoApuesta, cuota, stake, patas) {
  const sheetApuestas = getSheet_(SHEET_APUESTAS);
  const cuotaNum = Number(cuota);
  const stakeNum = Number(stake);
  const fila = appendRowByHeader_(sheetApuestas, {
    message_id: messageId,
    confirm_message_id: '',
    fecha_pick: fechaPick,
    tipo_apuesta: tipoApuesta,
    cuota: cuotaNum,
    stake: stakeNum,
    retorno_potencial: Math.round(cuotaNum * stakeNum * 100) / 100,
    resultado_manual: '',
    oculto: false,
    posible_duplicado_de: '',
    creado_en: new Date(),
  });

  const sheetPatas = getSheet_(SHEET_APUESTAS_PATAS);
  patas.forEach(function (pata, i) {
    appendRowByHeader_(sheetPatas, {
      message_id: messageId,
      numero_pata: i + 1,
      fecha_pick: fechaPick,
      hipodromo: pata.hipodromo,
      hora_carrera: pata.horaCarrera,
      trampa: pata.trampa,
      seleccion: pata.seleccion,
      creado_en: new Date(),
    });
  });

  return fila;
}

/**
 * Todas las filas de `apuestas_patas` (una por carrera) de un `message_id`
 * dado - una apuesta simple tiene 1, una doble 2, una tríple 3.
 */
function findApuestaPatasByMessageId(messageId) {
  const sheet = getSheet_(SHEET_APUESTAS_PATAS);
  const index = getHeaderIndex_(sheet);
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) return [];
  const col = index['message_id'] + 1;
  const values = sheet.getRange(2, col, lastRow - 1, 1).getValues();
  const resultado = [];
  for (let i = 0; i < values.length; i++) {
    if (String(values[i][0]) === String(messageId)) {
      resultado.push({ sheet: sheet, index: index, row: i + 2 });
    }
  }
  return resultado;
}

function setApuestaPataField(rowRef, campo, valor) {
  if (!COLUMNAS_APUESTAS_PATAS.includes(campo)) {
    throw new Error('Campo no editable por comando: ' + campo);
  }
  rowRef.sheet.getRange(rowRef.row, rowRef.index[campo] + 1).setValue(valor);
}

/**
 * Localiza la fila de `apuestas` cuyo confirm_message_id coincide con el
 * mensaje al que el usuario ha respondido (comandos ganó/perdió/ocultar/
 * mostrar/corregir). Devuelve {row, index} o null si no la encuentra.
 */
function findApuestaByConfirmMessageId(confirmMessageId) {
  const sheet = getSheet_(SHEET_APUESTAS);
  const index = getHeaderIndex_(sheet);
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) return null;
  const col = index['confirm_message_id'] + 1;
  const values = sheet.getRange(2, col, lastRow - 1, 1).getValues();
  for (let i = 0; i < values.length; i++) {
    if (String(values[i][0]) === String(confirmMessageId)) {
      return { sheet: sheet, index: index, row: i + 2 };
    }
  }
  return null;
}

function setApuestaConfirmMessageId(row, confirmMessageId) {
  const sheet = getSheet_(SHEET_APUESTAS);
  const index = getHeaderIndex_(sheet);
  sheet.getRange(row, index['confirm_message_id'] + 1).setValue(confirmMessageId);
}

function setApuestaField(rowRef, campo, valor) {
  if (!COLUMNAS_APUESTAS.includes(campo)) {
    throw new Error('Campo no editable por comando: ' + campo);
  }
  rowRef.sheet.getRange(rowRef.row, rowRef.index[campo] + 1).setValue(valor);
}
