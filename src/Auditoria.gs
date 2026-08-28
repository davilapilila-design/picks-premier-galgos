/**
 * Auditoría de solo lectura de todo el sistema de cálculo de apuestas
 * (pedida por el dueño 2026-08-27, ver docs/BITACORA.md). Recalcula desde
 * cero -sin leer ninguna fórmula (nunca getFormula()) ni fiarse de los
 * valores ya calculados- resultado_pata, resultado_final, retorno_real y
 * unidades_netas de cada fila, reimplementando las reglas de negocio en
 * JavaScript puro, y compara el resultado contra lo que la hoja tiene AHORA
 * MISMO en esas columnas. También revisa consistencia estructural
 * (message_id duplicados, patas huérfanas, número de patas vs
 * tipo_apuesta, celdas en error, cuotas/stakes inválidos, fecha_pick vs
 * fecha_forward, datos raros en resultados_galgos, picks "pendiente" desde
 * hace más días de los razonables) y una comprobación de exactitud del
 * propio automatismo más allá de la fórmula: si el nombre del galgo que
 * puso el tipster no se parece al que la VM registró para la trampa/
 * carrera que se dio por buena (señal de trampa con corredor sustituido).
 * Además recalcula los
 * agregados del panel (ganancia neta, stake total, ROI%, % de aciertos)
 * para compararlos contra lo que devuelve getMetricasPanel() (Dashboard.gs)
 * hoy mismo.
 *
 * SOLO LECTURA sobre apuestas/apuestas_patas/resultados_galgos/
 * mensajes_crudos: no se escribe nada en ellas. La única escritura es la
 * pestaña `auditoria` (se crea si no existe, se limpia y se vuelve a
 * rellenar si ya existía), para poder revisar el detalle completo con
 * calma sin depender del Registro de ejecución, que es efímero.
 *
 * CÓMO EJECUTAR (mismo patrón que setupSheet/checkConfig - clasp run NO
 * funciona en este proyecto, hay que hacerlo a mano desde el editor):
 *   1. `clasp push` para subir este archivo al proyecto de Apps Script.
 *   2. `clasp open-script` (o abrir el proyecto directamente en
 *      script.google.com).
 *   3. En el desplegable de funciones de la barra superior del editor,
 *      elegir `auditarSistema`.
 *   4. Pulsar "Ejecutar". La primera vez pedirá autorizar permisos (son de
 *      solo lectura sobre la hoja salvo por la pestaña `auditoria` nueva).
 *   5. Ver > Registro de ejecución para el resumen. Para el detalle
 *      completo, fila a fila, abrir la pestaña `auditoria` de la propia
 *      hoja de cálculo.
 *   (Opcional, recomendado antes de fiarte de una auditoría sobre miles de
 *   filas reales) Ejecutar primero `testReglasAuditoria` - son
 *   comprobaciones de la propia lógica de recálculo con casos de mano,
 *   "OK" en el log si todo cuadra.
 */

const SHEET_AUDITORIA = 'auditoria';
const TOLERANCIA_NUMERICA_ = 0.01;

// ---------------------------------------------------------------------
// Normalización: dos valores pueden significar lo mismo aunque vengan con
// distinto tipo/formato (fecha como Date o como texto "dd/mm/yyyy", hora
// como Date/fracción de día/"HH:MM", trampa como número 3 o texto "3"...).
// Estas funciones dan la "verdad de negocio" (lo que el dueño quiere decir
// con "misma trampa"), NO una réplica de las rarezas de comparación de
// Sheets (que no coacciona número<->texto en "=" - ver más abajo dónde se
// usa esto para detectar ese bug ya visto antes).
// ---------------------------------------------------------------------

function normalizarTexto_(v) {
  if (v === null || v === undefined) return '';
  return String(v).trim().toLowerCase();
}

function normalizarFechaISO_(v) {
  const tz = SpreadsheetApp.getActiveSpreadsheet().getSpreadsheetTimeZone();
  if (v instanceof Date && !isNaN(v.getTime())) {
    return Utilities.formatDate(v, tz, 'yyyy-MM-dd');
  }
  if (typeof v === 'number' && !isNaN(v)) {
    // Serial de fecha de Sheets: días desde 1899-12-30.
    const ms = Math.round((v - 25569) * 86400 * 1000);
    return Utilities.formatDate(new Date(ms), 'UTC', 'yyyy-MM-dd');
  }
  if (typeof v === 'string' && v.trim() !== '') {
    const texto = v.trim();
    const dmy = texto.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
    if (dmy) return dmy[3] + '-' + ('0' + dmy[2]).slice(-2) + '-' + ('0' + dmy[1]).slice(-2);
    const d = new Date(texto);
    if (!isNaN(d.getTime())) return Utilities.formatDate(d, tz, 'yyyy-MM-dd');
    return texto;
  }
  return '';
}

function normalizarHoraSegundos_(v) {
  if (v instanceof Date && !isNaN(v.getTime())) {
    return v.getHours() * 3600 + v.getMinutes() * 60 + v.getSeconds();
  }
  if (typeof v === 'number' && !isNaN(v)) {
    // Fracción de día (0-1), tal como Sheets guarda internamente una TIME.
    const fraccion = v - Math.floor(v);
    return Math.round(fraccion * 86400);
  }
  if (typeof v === 'string' && v.trim() !== '') {
    const m = v.trim().match(/^(\d{1,2}):(\d{2})(?::(\d{2}))?$/);
    if (m) return Number(m[1]) * 3600 + Number(m[2]) * 60 + Number(m[3] || 0);
  }
  return null;
}

function esNumerico_(v) {
  return typeof v === 'number' && !isNaN(v);
}

function pareceNumerico_(v) {
  return esNumerico_(v) || (typeof v === 'string' && v.trim() !== '' && !isNaN(Number(v.trim())));
}

// Clave comparable para trampa: números por valor (3 === "3"), texto por
// contenido (case-insensitive). Sheets NO hace esta coerción número<->texto
// en "=" (bug ya encontrado una vez, ver CLAUDE.md) - aquí se da el match
// por bueno porque esto es la verdad de negocio, y se avisa aparte (más
// abajo) cuando los TIPOS originales no coinciden, que es la pista de que
// la fórmula de la hoja puede estar fallando por esa causa exacta.
function claveComparable_(v) {
  if (pareceNumerico_(v)) return 'n:' + Number(String(v).trim());
  return 't:' + normalizarTexto_(v);
}

function tiposDifieren_(a, b) {
  return pareceNumerico_(a) !== pareceNumerico_(b);
}

// Nombre de galgo "core", para comparar el que puso el tipster contra el
// que registró la VM en resultados_galgos - quita anotaciones entre
// paréntesis habituales en resultados de carreras (p.ej. "(Res)", "(W)") y
// cualquier espacio/puntuación/tilde, para no disparar por simples
// diferencias de grafía.
function normalizarNombreGalgo_(v) {
  if (v === null || v === undefined) return '';
  return String(v)
    .toUpperCase()
    .replace(/\([^)]*\)/g, '')
    .replace(/[^A-Z0-9]/g, '')
    .trim();
}

// Da el match por bueno si son iguales o si uno contiene al otro (el
// tipster puede escribir el nombre abreviado, o la VM puede traer una
// variante con sufijo) - solo se acusa cuando no hay ningún parecido, que
// es la señal fuerte de "esta trampa cambió de galgo".
function nombresGalgoParecen_(tip, resultado) {
  const a = normalizarNombreGalgo_(tip);
  const b = normalizarNombreGalgo_(resultado);
  if (!a || !b) return true;
  if (a === b) return true;
  return a.indexOf(b) !== -1 || b.indexOf(a) !== -1;
}

function esPosicionNoCorredor_(pos) {
  return String(pos == null ? '' : pos).trim().toUpperCase() === 'N';
}

function esPosicionGanadora_(pos) {
  const n = Number(String(pos == null ? '' : pos).trim());
  return !isNaN(n) && n === 1;
}

function esPosicionValida_(pos) {
  if (esPosicionNoCorredor_(pos)) return true;
  const n = Number(String(pos == null ? '' : pos).trim());
  return !isNaN(n) && Number.isInteger(n) && n > 0;
}

function redondear2_(n) {
  return Math.round(n * 100) / 100;
}

function difierenNumericamente_(a, b) {
  const na = Number(a);
  const nb = Number(b);
  if (isNaN(na) || isNaN(nb)) return String(a) !== String(b);
  return Math.abs(na - nb) > TOLERANCIA_NUMERICA_;
}

// Compara un valor "recalculado" (puede ser '' cuando no aplica) contra el
// valor que hay en la hoja, tratando blanco/null como equivalentes y
// aplicando tolerancia numérica cuando ambos son números reales.
function difierenValorOpcional_(calc, actual) {
  const calcVacio = calc === '' || calc === null || calc === undefined;
  const actualVacio = actual === '' || actual === null || actual === undefined;
  if (calcVacio || actualVacio) return calcVacio !== actualVacio;
  return difierenNumericamente_(calc, actual);
}

// ---------------------------------------------------------------------
// Reglas de negocio reimplementadas desde cero (spec pedido por el dueño -
// NO es una copia de las fórmulas de Setup.gs, es una reimplementación
// independiente para poder detectar si esas fórmulas se desviaron de la
// regla real).
// ---------------------------------------------------------------------

/**
 * carreraFilas: filas de resultados_galgos ya filtradas por canódromo+
 * fecha+hora (misma carrera), cada una {trampaClave, posicion, numFila}.
 * trampaClavePata: clave comparable (claveComparable_) de la trampa de esta
 * pata.
 */
function calcularResultadoPata_(carreraFilas, trampaClavePata) {
  const exacta = carreraFilas.filter(function (r) { return r.trampaClave === trampaClavePata; })[0];
  if (exacta) {
    if (esPosicionNoCorredor_(exacta.posicion)) return 'pendiente';
    if (esPosicionGanadora_(exacta.posicion)) return 'gano';
    return 'perdio';
  }
  const hayGanador = carreraFilas.some(function (r) { return esPosicionGanadora_(r.posicion); });
  return hayGanador ? 'perdio' : 'pendiente';
}

function calcularResultadoFinal_(tipoApuesta, resultadoManual, resultadosPatasCalc) {
  if (resultadoManual !== '') return resultadoManual;
  if (TIPOS_APUESTA_SOPORTADOS.indexOf(tipoApuesta) === -1) return 'revision_manual';
  if (resultadosPatasCalc.length === 0) return 'pendiente';
  if (resultadosPatasCalc.indexOf('perdio') !== -1) return 'perdio';
  if (resultadosPatasCalc.every(function (r) { return r === 'gano'; })) return 'gano';
  return 'pendiente';
}

function calcularRetornoReal_(resultadoFinal, stake, cuota) {
  if (resultadoFinal === 'gano') return redondear2_(Number(stake) * Number(cuota));
  if (resultadoFinal === 'perdio') return 0;
  return '';
}

function calcularUnidadesNetas_(retornoReal, stake) {
  if (retornoReal === '') return '';
  return redondear2_(Number(retornoReal) - Number(stake));
}

/**
 * Ejecutar A MANO desde el editor (Ejecutar > testReglasAuditoria) antes
 * de fiarte del resultado de auditarSistema() sobre datos reales - mismo
 * espíritu que test_calcularMetricas_/test_calcularHistoricoPicks_ en
 * Dashboard.gs, pero SIN guion bajo al final: Apps Script oculta del
 * desplegable de "Ejecutar" cualquier función cuyo nombre termine en "_"
 * (las trata como privadas), así que una función pensada para ejecutarse a
 * mano no puede llamarse así. "OK" en el log si todas las comprobaciones
 * pasan.
 */
function testReglasAuditoria() {
  assertIguales_(calcularResultadoPata_([], 'n:3'), 'pendiente', 'sin filas de la carrera -> pendiente');
  assertIguales_(calcularResultadoPata_([{ trampaClave: 'n:3', posicion: 1 }], 'n:3'), 'gano', 'match exacto, posicion 1 -> gano');
  assertIguales_(calcularResultadoPata_([{ trampaClave: 'n:3', posicion: 4 }], 'n:3'), 'perdio', 'match exacto, posicion 4 -> perdio');
  assertIguales_(calcularResultadoPata_([{ trampaClave: 'n:3', posicion: 'N' }], 'n:3'), 'pendiente', 'match exacto, no corredor -> pendiente');
  assertIguales_(calcularResultadoPata_([{ trampaClave: 'n:3', posicion: 'n' }], 'n:3'), 'pendiente', 'no corredor en minuscula -> pendiente (Sheets "=" es case-insensitive)');
  assertIguales_(calcularResultadoPata_([{ trampaClave: 'n:5', posicion: 1 }], 'n:3'), 'perdio', 'sin match mi trampa, hay ganador de otra -> perdio');
  assertIguales_(calcularResultadoPata_([{ trampaClave: 'n:5', posicion: 2 }], 'n:3'), 'pendiente', 'sin match mi trampa, sin ganador en la carrera -> pendiente');

  assertIguales_(calcularResultadoFinal_('simple', 'gano', []), 'gano', 'resultado_manual manda siempre, aunque no haya patas');
  assertIguales_(calcularResultadoFinal_('trixie', '', ['gano']), 'revision_manual', 'tipo no soportado -> revision_manual');
  assertIguales_(calcularResultadoFinal_('simple', '', []), 'pendiente', 'sin patas -> pendiente');
  assertIguales_(calcularResultadoFinal_('doble', '', ['gano', 'perdio']), 'perdio', 'una pata perdida -> pierde toda la apuesta');
  assertIguales_(calcularResultadoFinal_('doble', '', ['gano', 'gano']), 'gano', 'todas las patas ganan -> gana');
  assertIguales_(calcularResultadoFinal_('doble', '', ['gano', 'pendiente']), 'pendiente', 'ninguna perdida, alguna pendiente -> pendiente');

  assertIguales_(calcularRetornoReal_('gano', 2, 3.5), 7, 'retorno_real = stake*cuota si gana');
  assertIguales_(calcularRetornoReal_('perdio', 2, 3.5), 0, 'retorno_real = 0 si pierde');
  assertIguales_(calcularRetornoReal_('pendiente', 2, 3.5), '', 'retorno_real vacio si no aplica');

  assertIguales_(calcularUnidadesNetas_(7, 2), 5, 'unidades_netas = retorno_real - stake');
  assertIguales_(calcularUnidadesNetas_('', 2), '', 'unidades_netas vacio si retorno_real vacio');

  Logger.log('testReglasAuditoria: OK, todas las comprobaciones pasaron.');
}

// ---------------------------------------------------------------------
// Lectura de hojas (siempre valores evaluados vía getValues(), nunca
// getFormula() - la auditoría no puede fiarse de la fórmula que dice tener
// la celda, solo del resultado que produce).
// ---------------------------------------------------------------------

function leerFilasConDatos_(sheet, index, campoClave) {
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) return [];
  const valores = sheet.getRange(2, 1, lastRow - 1, sheet.getLastColumn()).getValues();
  const filas = [];
  valores.forEach(function (fila, i) {
    if (fila[index[campoClave]] !== '') filas.push({ valores: fila, numFila: i + 2 });
  });
  return filas;
}

/**
 * Punto de entrada. Ver cabecera del archivo para cómo ejecutarlo.
 */
function auditarSistema() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheetApuestas = getSheet_(SHEET_APUESTAS);
  const sheetPatas = getSheet_(SHEET_APUESTAS_PATAS);
  const sheetResultados = getSheet_(SHEET_RESULTADOS_GALGOS);
  const sheetMensajes = getSheet_(SHEET_MENSAJES_CRUDOS);

  const idxApuestas = getHeaderIndex_(sheetApuestas);
  const idxPatas = getHeaderIndex_(sheetPatas);
  const idxResultados = getHeaderIndex_(sheetResultados);
  const idxMensajes = getHeaderIndex_(sheetMensajes);

  const filasApuestas = leerFilasConDatos_(sheetApuestas, idxApuestas, 'message_id');
  const filasPatas = leerFilasConDatos_(sheetPatas, idxPatas, 'message_id');
  const filasResultados = leerFilasConDatos_(sheetResultados, idxResultados, 'canodromo');
  const filasMensajes = leerFilasConDatos_(sheetMensajes, idxMensajes, 'message_id');

  const discrepancias = [];
  function registrar(tipo, messageId, fila, campo, esperado, actual, detalle) {
    discrepancias.push({
      tipo: tipo, messageId: messageId, fila: fila, campo: campo,
      esperado: esperado, actual: actual, detalle: detalle,
    });
  }

  // -- Índice de resultados_galgos por carrera (canódromo+fecha+hora) --
  const resultadosPorCarrera = {};
  filasResultados.forEach(function (r) {
    const posicionValor = r.valores[idxResultados['posicion']];
    if (!esPosicionValida_(posicionValor)) {
      registrar('posicion_no_reconocida', '', r.numFila, 'resultados_galgos.posicion',
        '"N" o un entero positivo', posicionValor,
        'resultados_galgos fila ' + r.numFila + ' tiene un valor de posición que no es "N" ni un ' +
        'entero positivo - no se puede determinar de forma fiable si esta trampa ganó o no corrió.');
    }
    const canodromo = normalizarTexto_(r.valores[idxResultados['canodromo']]);
    const fecha = normalizarFechaISO_(r.valores[idxResultados['fecha']]);
    const hora = normalizarHoraSegundos_(r.valores[idxResultados['hora']]);
    const key = canodromo + '|' + fecha + '|' + hora;
    if (!resultadosPorCarrera[key]) resultadosPorCarrera[key] = [];
    resultadosPorCarrera[key].push({
      trampaClave: claveComparable_(r.valores[idxResultados['trap']]),
      trampaOriginal: r.valores[idxResultados['trap']],
      posicion: posicionValor,
      nombre: r.valores[idxResultados['nombre']],
      numFila: r.numFila,
    });
  });

  // Consistencia dentro de cada carrera: trampa repetida o más de un
  // "ganador" registrado - si pasa, el cruce puede coger cualquiera de las
  // filas de forma no determinista y el razonamiento de la regla 2
  // ("si mi trampa hubiera ganado, la búsqueda exacta ya la habría
  // encontrado, porque el ganador siempre tiene fila") deja de sostenerse.
  Object.keys(resultadosPorCarrera).forEach(function (key) {
    const filas = resultadosPorCarrera[key];
    const porTrampa = {};
    filas.forEach(function (f) { porTrampa[f.trampaClave] = (porTrampa[f.trampaClave] || []).concat([f.numFila]); });
    Object.keys(porTrampa).forEach(function (trampaClave) {
      if (porTrampa[trampaClave].length > 1) {
        registrar('trampa_duplicada_en_carrera', '', porTrampa[trampaClave].join(','), 'resultados_galgos',
          '1 fila por trampa y carrera', porTrampa[trampaClave].length + ' filas',
          'La carrera "' + key + '" (canódromo|fecha|hora en segundos) tiene ' + porTrampa[trampaClave].length +
          ' filas para la misma trampa (filas ' + porTrampa[trampaClave].join(', ') + ') en resultados_galgos.');
      }
    });
    const ganadores = filas.filter(function (f) { return esPosicionGanadora_(f.posicion); });
    if (ganadores.length > 1) {
      const filasGanadoras = ganadores.map(function (g) { return g.numFila; });
      registrar('multiples_ganadores_en_carrera', '', filasGanadoras.join(','), 'resultados_galgos.posicion',
        '1 ganador por carrera', ganadores.length + ' ganadores',
        'La carrera "' + key + '" tiene ' + ganadores.length + ' filas con posicion=1 (filas ' +
        filasGanadoras.join(', ') + ') - dato inconsistente en resultados_galgos.');
    }
  });

  // -- mensajes_crudos por message_id, para el check de fecha_forward --
  //
  // Cargas históricas manuales (confirmado por el dueño 2026-08-27, ver
  // docs/BITACORA.md): antes de que el bot estuviera operativo se metieron
  // picks antiguos directamente en la hoja, sin pasar por Main.gs. Esas
  // filas comparten `fecha_recibido` entre MUCHOS message_id distintos (el
  // momento de la carga a mano, no el día real del pick) y no tienen
  // `fecha_forward` real - el check de fecha_pick de más abajo no tiene
  // sentido para ellas. Se detectan por heurística, agrupando por el
  // INSTANTE EXACTO (fecha+hora+minuto+segundo) de fecha_recibido, no solo
  // por el día: agrupar solo por día habría clasificado también como
  // "carga manual" cualquier día normal en que el bot recibiera
  // UMBRAL_CARGA_MASIVA_ picks reales o más (nada raro con un tipster
  // activo), dejando sin comprobar precisamente los días con más mensajes
  // - donde más importa vigilar el bug de reintentos/forward. Compartir el
  // segundo EXACTO entre varios message_id es prácticamente imposible en
  // uso normal del bot (cada mensaje llega en un instante distinto), pero
  // es justo lo que deja una carga masiva pegada de golpe (o tecleada solo
  // con fecha, sin hora - Sheets la guarda entonces a medianoche exacta).
  const UMBRAL_CARGA_MASIVA_ = 5;

  // Excepciones confirmadas a mano por el dueño (2026-08-28, ver
  // docs/BITACORA.md): segunda tanda de importación manual de picks
  // históricos, tecleada uno a uno (no comparte instante exacto de
  // fecha_recibido entre sí, por eso la heurística de arriba no la
  // detecta). Verificado contra el texto original de 3 de ellos
  // (message_id 115, 140, 147, de fechas distintas dentro del lote):
  // fecha_pick es correcta en los tres - fecha_recibido de mensajes_crudos
  // solo refleja el día de la carga manual (2026-08-26), no la fecha real
  // del pick. Si en el futuro un pick real del bot dispara
  // fecha_pick_inconsistente, no será ninguno de estos IDs.
  const MESSAGE_IDS_CARGA_MANUAL_CONFIRMADOS_ = [
    '115', '116', '123', '127', '128', '129', '130', '135', '136', '139', '140', '143', '144', '147', '148',
  ];

  function timestampExactoISO_(v) {
    if (v instanceof Date && !isNaN(v.getTime())) {
      const tz = SpreadsheetApp.getActiveSpreadsheet().getSpreadsheetTimeZone();
      return Utilities.formatDate(v, tz, 'yyyy-MM-dd HH:mm:ss');
    }
    return normalizarFechaISO_(v);
  }
  const conteoPorTimestampExacto_ = {};
  filasMensajes.forEach(function (m) {
    const ts = timestampExactoISO_(m.valores[idxMensajes['fecha_recibido']]);
    conteoPorTimestampExacto_[ts] = (conteoPorTimestampExacto_[ts] || 0) + 1;
  });

  const mensajesPorId = {};
  filasMensajes.forEach(function (m) {
    const ts = timestampExactoISO_(m.valores[idxMensajes['fecha_recibido']]);
    mensajesPorId[String(m.valores[idxMensajes['message_id']])] = {
      fechaRecibido: m.valores[idxMensajes['fecha_recibido']],
      fechaForward: m.valores[idxMensajes['fecha_forward']],
      cargaManualProbable: (conteoPorTimestampExacto_[ts] || 0) >= UMBRAL_CARGA_MASIVA_,
    };
  });

  // -- Patas: recalcular resultado_pata y agrupar por message_id --
  const patasPorMessageId = {};
  let filasSinFechaHoraValida = 0;

  filasPatas.forEach(function (p) {
    const messageId = String(p.valores[idxPatas['message_id']]);
    const canodromo = normalizarTexto_(p.valores[idxPatas['hipodromo']]);
    const fecha = normalizarFechaISO_(p.valores[idxPatas['fecha_pick']]);
    const hora = normalizarHoraSegundos_(p.valores[idxPatas['hora_carrera']]);
    const trampaClave = claveComparable_(p.valores[idxPatas['trampa']]);

    if (!fecha || hora === null) {
      filasSinFechaHoraValida++;
      registrar('dato_no_parseable', messageId, p.numFila, 'fecha_pick/hora_carrera',
        'fecha y hora interpretables',
        'fecha="' + p.valores[idxPatas['fecha_pick']] + '" hora="' + p.valores[idxPatas['hora_carrera']] + '"',
        'No se ha podido normalizar fecha u hora de esta pata - se ha omitido del recálculo de ' +
        'resultado_pata (no se puede garantizar el cruce contra resultados_galgos).');
      return;
    }

    const key = canodromo + '|' + fecha + '|' + hora;
    const carrera = resultadosPorCarrera[key] || [];
    const resultadoCalc = calcularResultadoPata_(carrera, trampaClave);
    const resultadoActual = String(p.valores[idxPatas['resultado_pata']] || '').trim();
    const exactaCandidata = carrera.filter(function (r) { return r.trampaClave === trampaClave; })[0];

    if (resultadoCalc !== resultadoActual) {
      let detalle = 'Recalculado de cero: "' + resultadoCalc + '". La hoja tiene: "' + resultadoActual + '".';
      if (!exactaCandidata) {
        const posibleTipoMismatch = carrera.some(function (r) {
          return normalizarTexto_(r.trampaOriginal) === normalizarTexto_(p.valores[idxPatas['trampa']]) &&
            tiposDifieren_(r.trampaOriginal, p.valores[idxPatas['trampa']]);
        });
        if (posibleTipoMismatch) {
          detalle += ' Causa probable: la trampa coincide en contenido pero no en TIPO (número vs texto) ' +
            'entre apuestas_patas.trampa y resultados_galgos.trap - Sheets no coacciona tipos en ' +
            'comparaciones "=" (bug ya visto antes en este proyecto, ver CLAUDE.md).';
        }
      }
      registrar('resultado_pata', messageId, p.numFila, 'resultado_pata', resultadoCalc, resultadoActual, detalle);
    }

    // El automatismo puede encontrar la carrera y la trampa correctas pero
    // estar comparando contra un galgo distinto al que se apostó, si esa
    // trampa cambió de corredor (reserva/sustitución) y resultados_galgos
    // no lo refleja de otra forma - esto no lo detecta ninguna comparación
    // de fórmulas, solo cruzando el nombre que puso el tipster contra el
    // que registró la VM para esa trampa/carrera.
    if (exactaCandidata && (resultadoCalc === 'gano' || resultadoCalc === 'perdio')) {
      const seleccionTip = p.valores[idxPatas['seleccion']];
      if (!nombresGalgoParecen_(seleccionTip, exactaCandidata.nombre)) {
        registrar('posible_galgo_distinto', messageId, p.numFila,
          'apuestas_patas.seleccion vs resultados_galgos.nombre', seleccionTip, exactaCandidata.nombre,
          'El nombre del galgo del pick ("' + seleccionTip + '") no se parece al registrado en ' +
          'resultados_galgos para esa trampa/carrera ("' + exactaCandidata.nombre + '") - puede ser solo una ' +
          'diferencia de grafía, o que la trampa cambiara de galgo (reserva/no corredor sustituido) y ' +
          'resultado_pata esté comparando contra un perro distinto al apostado. Revisar a mano.');
      }
    }

    if (!patasPorMessageId[messageId]) patasPorMessageId[messageId] = [];
    patasPorMessageId[messageId].push({ numFila: p.numFila, resultadoCalc: resultadoCalc });
  });

  // -- message_id duplicados en apuestas (dedup real, ver CLAUDE.md) --
  const conteoMessageId = {};
  filasApuestas.forEach(function (a) {
    const messageId = String(a.valores[idxApuestas['message_id']]);
    conteoMessageId[messageId] = (conteoMessageId[messageId] || []).concat([a.numFila]);
  });
  Object.keys(conteoMessageId).forEach(function (messageId) {
    const filas = conteoMessageId[messageId];
    if (filas.length > 1) {
      registrar('message_id_duplicado', messageId, filas.join(','), 'message_id',
        '1 fila por message_id', filas.length + ' filas',
        'El message_id ' + messageId + ' aparece en las filas ' + filas.join(', ') + ' de apuestas.');
    }
  });

  // -- Patas huérfanas (sin apuesta padre) --
  const messageIdsApuestas = {};
  filasApuestas.forEach(function (a) { messageIdsApuestas[String(a.valores[idxApuestas['message_id']])] = true; });
  const messageIdsConPatas = {};
  filasPatas.forEach(function (p) {
    const messageId = String(p.valores[idxPatas['message_id']]);
    messageIdsConPatas[messageId] = true;
    if (!messageIdsApuestas[messageId]) {
      registrar('pata_huerfana', messageId, p.numFila, 'message_id', 'existe en apuestas', 'no existe en apuestas',
        'apuestas_patas fila ' + p.numFila + ' tiene message_id ' + messageId + ' que no aparece en apuestas.');
    }
  });

  // -- Recalcular cada apuesta: resultado_final, retorno_real, unidades_netas
  //    + checks estructurales por fila (patas, cuota/stake, fecha_forward) --
  const CONTEO_ESPERADO_PATAS = { simple: 1, doble: 2, triple: 3 };
  // "pendiente" es normal el mismo día de la carrera o el día siguiente (el
  // job de la VM aún no habrá volcado el resultado) - más de
  // DIAS_MARGEN_PENDIENTE_ días desde fecha_pick sin resultado sí merece
  // que el dueño lo revise (o falta el scrape de esa carrera, o hay que
  // resolverla a mano).
  const DIAS_MARGEN_PENDIENTE_ = 2;
  const hoyISO_ = normalizarFechaISO_(new Date());
  const columnasFormulaApuestas = [
    'num_patas', 'patas_ganadas', 'patas_perdidas', 'resultado_final', 'fuente_resultado',
    'retorno_real', 'unidades_netas', 'canodromo', 'galgo', 'mensaje', 'cuota_final',
    'url_carrera', 'race_id', 'dog_id', 'value_pct',
  ];
  const filasParaAgregados = [];
  let filasFechaPickOmitidasPorCargaManual = 0;

  filasApuestas.forEach(function (a) {
    const messageId = String(a.valores[idxApuestas['message_id']]);
    const tipoApuesta = String(a.valores[idxApuestas['tipo_apuesta']] || '').trim();
    const cuota = a.valores[idxApuestas['cuota']];
    const stake = a.valores[idxApuestas['stake']];
    const resultadoManual = String(a.valores[idxApuestas['resultado_manual']] || '').trim();
    const oculto = a.valores[idxApuestas['oculto']] === true;

    if (!messageIdsConPatas[messageId]) {
      registrar('apuesta_sin_patas', messageId, a.numFila, 'apuestas_patas', 'al menos 1 fila', '0 filas',
        'apuestas fila ' + a.numFila + ' (message_id ' + messageId + ') no tiene ninguna fila en apuestas_patas.');
    }

    const patas = patasPorMessageId[messageId] || [];
    const esperadas = CONTEO_ESPERADO_PATAS[tipoApuesta];
    if (esperadas !== undefined && patas.length !== esperadas) {
      registrar('num_patas_incorrecto', messageId, a.numFila, 'apuestas_patas (filas reales)',
        esperadas + ' pata(s) para tipo_apuesta="' + tipoApuesta + '"', patas.length + ' pata(s)',
        'apuestas_patas tiene ' + patas.length + ' fila(s) para message_id ' + messageId +
        ' pero tipo_apuesta="' + tipoApuesta + '" debería tener ' + esperadas + '.');
    }

    if (cuota === '' || cuota === null || isNaN(Number(cuota)) || Number(cuota) <= 0) {
      registrar('cuota_invalida', messageId, a.numFila, 'cuota', 'número > 0', String(cuota),
        'cuota en blanco, no numérica, cero o negativa en apuestas fila ' + a.numFila + '.');
    }
    if (stake === '' || stake === null || isNaN(Number(stake)) || Number(stake) <= 0) {
      registrar('stake_invalido', messageId, a.numFila, 'stake', 'número > 0', String(stake),
        'stake en blanco, no numérico, cero o negativo en apuestas fila ' + a.numFila + '.');
    }

    const mensaje = mensajesPorId[messageId];
    if (!mensaje) {
      registrar('mensaje_crudo_no_encontrado', messageId, a.numFila, 'mensajes_crudos.message_id',
        'existe', 'no existe',
        'No se encuentra el message_id ' + messageId + ' en mensajes_crudos (apuestas fila ' + a.numFila + ').');
    } else if (mensaje.cargaManualProbable || MESSAGE_IDS_CARGA_MANUAL_CONFIRMADOS_.indexOf(messageId) !== -1) {
      // Carga histórica manual detectada (ver comentario junto a
      // UMBRAL_CARGA_MASIVA_ más arriba) - fecha_recibido de ese día no
      // sirve como referencia, así que no se compara fecha_pick contra
      // ella (daría falsos positivos en bloque, no un bug real).
      filasFechaPickOmitidasPorCargaManual++;
    } else {
      const fechaEsperada = mensaje.fechaForward || mensaje.fechaRecibido;
      const fechaPickISO = normalizarFechaISO_(a.valores[idxApuestas['fecha_pick']]);
      const fechaEsperadaISO = normalizarFechaISO_(fechaEsperada);
      if (fechaEsperadaISO && fechaPickISO && fechaEsperadaISO !== fechaPickISO) {
        registrar('fecha_pick_inconsistente', messageId, a.numFila, 'fecha_pick', fechaEsperadaISO, fechaPickISO,
          'fecha_pick de apuestas no coincide (a nivel de día) con fecha_forward/fecha_recibido de ' +
          'mensajes_crudos para este message_id - mismo patrón que el bug de reintentos/forward ya ' +
          'encontrado antes (ver CLAUDE.md); si hay una carrera real coincidiendo por casualidad en la ' +
          'fecha equivocada, resultado_pata puede estar comparando contra un galgo distinto.');
      }
    }

    const resultadosPatasCalc = patas.map(function (p) { return p.resultadoCalc; });
    const resultadoFinalCalc = calcularResultadoFinal_(tipoApuesta, resultadoManual, resultadosPatasCalc);
    const resultadoFinalActual = String(a.valores[idxApuestas['resultado_final']] || '').trim();
    if (resultadoFinalCalc !== resultadoFinalActual) {
      registrar('resultado_final', messageId, a.numFila, 'resultado_final', resultadoFinalCalc, resultadoFinalActual,
        'Recalculado a partir de resultado_manual/tipo_apuesta/patas: "' + resultadoFinalCalc +
        '". La hoja tiene: "' + resultadoFinalActual + '".');
    }

    if (resultadoFinalCalc === 'pendiente' && oculto !== true) {
      const fechaPickISOVencida = normalizarFechaISO_(a.valores[idxApuestas['fecha_pick']]);
      if (fechaPickISOVencida) {
        const diasTranscurridos = Math.round((new Date(hoyISO_) - new Date(fechaPickISOVencida)) / 86400000);
        if (diasTranscurridos > DIAS_MARGEN_PENDIENTE_) {
          registrar('pendiente_vencida', messageId, a.numFila, 'resultado_final',
            'gano/perdio (la carrera ya debería tener resultado)', 'pendiente',
            'fecha_pick=' + fechaPickISOVencida + ', ' + diasTranscurridos + ' día(s) desde la carrera y sigue ' +
            '"pendiente" - probablemente falta esa carrera en resultados_galgos (el job de la VM no la ' +
            'encontró/scrapeó) o necesita resolverse a mano con el comando de ganó/perdió.');
        }
      }
    }

    const retornoRealCalc = calcularRetornoReal_(resultadoFinalCalc, stake, cuota);
    const retornoRealActual = a.valores[idxApuestas['retorno_real']];
    if (difierenValorOpcional_(retornoRealCalc, retornoRealActual)) {
      registrar('retorno_real', messageId, a.numFila, 'retorno_real', retornoRealCalc, retornoRealActual,
        'Recalculado: ' + (retornoRealCalc === '' ? '(vacío)' : retornoRealCalc) +
        '. La hoja tiene: ' + (retornoRealActual === '' ? '(vacío)' : retornoRealActual) + '.');
    }

    const unidadesNetasCalc = calcularUnidadesNetas_(retornoRealCalc, stake);
    const unidadesNetasActual = a.valores[idxApuestas['unidades_netas']];
    if (difierenValorOpcional_(unidadesNetasCalc, unidadesNetasActual)) {
      registrar('unidades_netas', messageId, a.numFila, 'unidades_netas', unidadesNetasCalc, unidadesNetasActual,
        'Recalculado: ' + (unidadesNetasCalc === '' ? '(vacío)' : unidadesNetasCalc) +
        '. La hoja tiene: ' + (unidadesNetasActual === '' ? '(vacío)' : unidadesNetasActual) + '.');
    }

    columnasFormulaApuestas.forEach(function (col) {
      const valor = a.valores[idxApuestas[col]];
      if (typeof valor === 'string' && valor.indexOf('#') === 0) {
        registrar('celda_error', messageId, a.numFila, col, 'valor calculado', valor,
          'Celda con error de fórmula en apuestas!' + col + ' fila ' + a.numFila + ': ' + valor);
      }
    });

    filasParaAgregados.push({
      oculto: oculto,
      resultadoFinalCalc: resultadoFinalCalc,
      unidadesNetasCalc: unidadesNetasCalc,
      stake: Number(stake) || 0,
    });
  });

  // -- Celdas en error en apuestas_patas --
  const columnasFormulaPatas = [
    'posicion_pata', 'resultado_pata', 'cuota_final_pata', 'url_carrera_pata', 'race_id_pata', 'dog_id_pata',
  ];
  filasPatas.forEach(function (p) {
    columnasFormulaPatas.forEach(function (col) {
      const valor = p.valores[idxPatas[col]];
      if (typeof valor === 'string' && valor.indexOf('#') === 0) {
        registrar('celda_error', String(p.valores[idxPatas['message_id']]), p.numFila, col, 'valor calculado', valor,
          'Celda con error de fórmula en apuestas_patas!' + col + ' fila ' + p.numFila + ': ' + valor);
      }
    });
  });

  // -- Agregados recalculados de cero, comparados contra getMetricasPanel() --
  const filasFiltradas = filasParaAgregados.filter(function (f) {
    return f.oculto !== true && (f.resultadoFinalCalc === 'gano' || f.resultadoFinalCalc === 'perdio');
  });
  let unidadesNetasTotalCalc = 0;
  let stakeTotalCalc = 0;
  let ganadasCalc = 0;
  filasFiltradas.forEach(function (f) {
    unidadesNetasTotalCalc += Number(f.unidadesNetasCalc) || 0;
    stakeTotalCalc += f.stake;
    if (f.resultadoFinalCalc === 'gano') ganadasCalc++;
  });
  const roiPctCalc = stakeTotalCalc === 0 ? 0 : (unidadesNetasTotalCalc / stakeTotalCalc) * 100;
  const pctAciertosCalc = filasFiltradas.length === 0 ? 0 : (ganadasCalc / filasFiltradas.length) * 100;

  const metricasPanel = getMetricasPanel();
  if (metricasPanel.hayDatos) {
    const stakeTotalPanelUnidades = metricasPanel.stakeTotalEur / TASA_EUR_POR_UNIDAD;
    if (difierenNumericamente_(unidadesNetasTotalCalc, metricasPanel.unidadesNetas)) {
      registrar('agregado', '', '', 'unidades_netas (total, ganancia neta)',
        redondear2_(unidadesNetasTotalCalc), metricasPanel.unidadesNetas,
        'Ganancia neta total recalculada de cero difiere de getMetricasPanel().unidadesNetas.');
    }
    if (difierenNumericamente_(stakeTotalCalc, stakeTotalPanelUnidades)) {
      registrar('agregado', '', '', 'stake_total', redondear2_(stakeTotalCalc), redondear2_(stakeTotalPanelUnidades),
        'Stake total recalculado de cero difiere del de getMetricasPanel() (convertido de € de vuelta a unidades).');
    }
    // getMetricasPanel() redondea roiPct/pctAciertos a 1 decimal antes de
    // devolverlos - comparar contra el valor sin redondear con la misma
    // tolerancia de 0.01 de los demás campos daba falsos positivos por
    // simple redondeo (p.ej. 10.93 recalculado vs 10.9 ya redondeado). Se
    // redondea aquí también a 1 decimal antes de comparar estos dos campos.
    if (difierenNumericamente_(Math.round(roiPctCalc * 10) / 10, metricasPanel.roiPct)) {
      registrar('agregado', '', '', 'roi_pct', redondear2_(roiPctCalc), metricasPanel.roiPct,
        'ROI% recalculado de cero difiere de getMetricasPanel().roiPct incluso tras redondear ambos a 1 decimal.');
    }
    if (difierenNumericamente_(Math.round(pctAciertosCalc * 10) / 10, metricasPanel.pctAciertos)) {
      registrar('agregado', '', '', 'pct_aciertos', redondear2_(pctAciertosCalc), metricasPanel.pctAciertos,
        '% de aciertos recalculado de cero difiere de getMetricasPanel().pctAciertos incluso tras redondear ambos a 1 decimal.');
    }
  } else if (filasFiltradas.length > 0) {
    registrar('agregado', '', '', 'hayDatos', true, false,
      'El recálculo encuentra ' + filasFiltradas.length + ' fila(s) resueltas y visibles, pero ' +
      'getMetricasPanel() dice que no hay datos.');
  }

  escribirAuditoriaEnHoja_(ss, discrepancias);
  logResumenAuditoria_({
    numApuestas: filasApuestas.length,
    numPatas: filasPatas.length,
    numResultados: filasResultados.length,
    filasSinFechaHoraValida: filasSinFechaHoraValida,
    filasFechaPickOmitidasPorCargaManual: filasFechaPickOmitidasPorCargaManual,
    discrepancias: discrepancias,
    numFiltradasParaAgregados: filasFiltradas.length,
    unidadesNetasTotalCalc: unidadesNetasTotalCalc,
    stakeTotalCalc: stakeTotalCalc,
    roiPctCalc: roiPctCalc,
    pctAciertosCalc: pctAciertosCalc,
  });

  return {
    filasApuestasRevisadas: filasApuestas.length,
    filasPatasRevisadas: filasPatas.length,
    discrepanciasEncontradas: discrepancias.length,
  };
}

function escribirAuditoriaEnHoja_(ss, discrepancias) {
  let sheet = ss.getSheetByName(SHEET_AUDITORIA);
  if (!sheet) {
    sheet = ss.insertSheet(SHEET_AUDITORIA);
  } else {
    sheet.clear();
  }
  const cabeceras = ['tipo', 'message_id', 'fila', 'campo', 'esperado', 'actual', 'detalle', 'ejecutado_en'];
  sheet.getRange(1, 1, 1, cabeceras.length).setValues([cabeceras]);
  sheet.setFrozenRows(1);
  if (discrepancias.length === 0) return;
  const ahora = new Date();
  const filas = discrepancias.map(function (d) {
    return [d.tipo, d.messageId, d.fila, d.campo, String(d.esperado), String(d.actual), d.detalle, ahora];
  });
  sheet.getRange(2, 1, filas.length, cabeceras.length).setValues(filas);
}

function logResumenAuditoria_(r) {
  Logger.log('===== AUDITORÍA DE APUESTAS - RESUMEN =====');
  Logger.log('Filas revisadas: ' + r.numApuestas + ' en apuestas, ' + r.numPatas + ' en apuestas_patas, ' +
    r.numResultados + ' en resultados_galgos.');
  Logger.log('Patas sin fecha/hora interpretable (excluidas del recálculo de resultado_pata): ' + r.filasSinFechaHoraValida);
  Logger.log('Apuestas excluidas del check de fecha_pick por carga manual masiva detectada en ' +
    'mensajes_crudos (>=5 message_id distintos con el MISMO instante exacto de fecha_recibido): ' +
    r.filasFechaPickOmitidasPorCargaManual);
  Logger.log('Discrepancias totales encontradas: ' + r.discrepancias.length);

  const porTipo = {};
  r.discrepancias.forEach(function (d) { porTipo[d.tipo] = (porTipo[d.tipo] || 0) + 1; });
  Object.keys(porTipo).sort().forEach(function (tipo) { Logger.log('  - ' + tipo + ': ' + porTipo[tipo]); });

  Logger.log('--- Agregados recalculados de cero (oculto=false, resultado_final en gano/perdio) ---');
  Logger.log('Filas en el conjunto filtrado: ' + r.numFiltradasParaAgregados);
  Logger.log('Ganancia neta (unidades): ' + redondear2_(r.unidadesNetasTotalCalc));
  Logger.log('Stake total (unidades): ' + redondear2_(r.stakeTotalCalc));
  Logger.log('ROI%: ' + redondear2_(r.roiPctCalc));
  Logger.log('% aciertos: ' + redondear2_(r.pctAciertosCalc));

  if (r.discrepancias.length > 0) {
    Logger.log('--- Detalle (máximo 200 líneas aquí - el listado completo está en la pestaña "auditoria") ---');
    r.discrepancias.slice(0, 200).forEach(function (d) {
      Logger.log('[' + d.tipo + '] message_id=' + d.messageId + ' fila=' + d.fila + ' campo=' + d.campo +
        ' esperado=' + d.esperado + ' actual=' + d.actual + ' - ' + d.detalle);
    });
    if (r.discrepancias.length > 200) {
      Logger.log('... y ' + (r.discrepancias.length - 200) + ' discrepancia(s) más - ver la pestaña "auditoria".');
    }
  }

  Logger.log('===== FIN DEL RESUMEN =====');
}
