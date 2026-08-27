/**
 * Bootstrap de la hoja de cálculo (Fase 1 del PLAN.md, sección 5). Se
 * ejecuta a mano UNA VEZ desde el editor de Apps Script (Ejecutar >
 * setupSheet) tras vincular el proyecto con `clasp create`. No volver a
 * ejecutar sobre una hoja que ya tenga datos reales: `sheet.clear()` borra
 * lo que hubiera en las pestañas.
 */

const FILAS_FORMULA_APUESTAS = 2000; // margen amplio para picks futuros
const FILAS_FORMULA_APUESTAS_PATAS = 5000; // varias filas por pick (1 por carrera)

function setupSheet() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  crearMensajesCrudos_(ss);
  crearApuestasPatas_(ss);
  crearApuestas_(ss);
  crearResultadosGalgos_(ss);
  borrarHojaPorDefecto_(ss);
  Logger.log('Listo: mensajes_crudos, apuestas_patas, apuestas y resultados_galgos creadas.');
}

function crearMensajesCrudos_(ss) {
  const sheet = ss.getSheetByName(SHEET_MENSAJES_CRUDOS) || ss.insertSheet(SHEET_MENSAJES_CRUDOS);
  sheet.clear();
  sheet.getRange(1, 1, 1, COLUMNAS_MENSAJES_CRUDOS.length).setValues([COLUMNAS_MENSAJES_CRUDOS]);
  sheet.setFrozenRows(1);
}

function crearResultadosGalgos_(ss) {
  const sheet = ss.getSheetByName(SHEET_RESULTADOS_GALGOS) || ss.insertSheet(SHEET_RESULTADOS_GALGOS);
  sheet.clear();
  sheet.getRange(1, 1, 1, COLUMNAS_RESULTADOS_GALGOS.length).setValues([COLUMNAS_RESULTADOS_GALGOS]);
  sheet.setFrozenRows(1);
}

/**
 * `apuestas_patas` = una fila por CARRERA de un pick (COLUMNAS_APUESTAS_PATAS,
 * las rellena el script) + columnas fórmula que resuelven ESA pata sola
 * contra `resultados_galgos` (coincidencia exacta de trampa; si no, trampa
 * ganadora de la carrera como "perdió" seguro - mismo razonamiento que la
 * v1 de `apuestas`, ver docs/BITACORA.md 2026-08-26). `apuestas` (más abajo)
 * agrega estas filas por `message_id` para dar el resultado conjunto.
 */
function crearApuestasPatas_(ss) {
  const columnasFormula = [
    'posicion_pata', 'resultado_pata', 'cuota_final_pata', 'url_carrera_pata',
    'race_id_pata', 'dog_id_pata',
  ];
  const cabeceras = COLUMNAS_APUESTAS_PATAS.concat(columnasFormula);

  const sheet = ss.getSheetByName(SHEET_APUESTAS_PATAS) || ss.insertSheet(SHEET_APUESTAS_PATAS);
  sheet.clear();
  sheet.getRange(1, 1, 1, cabeceras.length).setValues([cabeceras]);
  sheet.setFrozenRows(1);

  const col = {};
  cabeceras.forEach(function (nombreCol, i) { col[nombreCol] = columnToLetter_(i + 1); });
  const resultadosRango = 'resultados_galgos!$A$2:$A$5000';

  const formulas = [];
  for (let fila = 2; fila <= FILAS_FORMULA_APUESTAS_PATAS; fila++) {
    const hipodromo = col.hipodromo + fila;
    const fechaPick = col.fecha_pick + fila;
    const horaCarrera = col.hora_carrera + fila;
    const trampa = col.trampa + fila;
    const posicionPata = col.posicion_pata + fila;

    // Mismo razonamiento que en la v1 de apuestas (ver docs/BITACORA.md
    // 2026-08-26): INDEX/MATCH en vez de QUERY, INT() para ignorar la hora
    // del timestamp, &"" al comparar "posicion" (Sheets no hace coerción
    // de tipos: 1 numérico ≠ "1" texto).
    const posicionPataF = `=IFERROR(INDEX(resultados_galgos!$F$2:$F$5000;MATCH(1;(${resultadosRango}=${hipodromo})*(INT(resultados_galgos!$B$2:$B$5000)=INT(${fechaPick}))*(resultados_galgos!$C$2:$C$5000=${horaCarrera})*(resultados_galgos!$D$2:$D$5000=${trampa});0));"")`;
    const trampaGanadora = `IFERROR(INDEX(resultados_galgos!$D$2:$D$5000;MATCH(1;(${resultadosRango}=${hipodromo})*(INT(resultados_galgos!$B$2:$B$5000)=INT(${fechaPick}))*(resultados_galgos!$C$2:$C$5000=${horaCarrera})*(resultados_galgos!$F$2:$F$5000&""="1");0));"")`;
    const resultadoPataF = `=IF(${posicionPata}<>"";IF(${posicionPata}="N";"pendiente";IF(VALUE(${posicionPata})=1;"gano";"perdio"));IF(${trampaGanadora}<>"";"perdio";"pendiente"))`;

    const cuotaFinalPataF = `=IFERROR(INDEX(resultados_galgos!$H$2:$H$5000;MATCH(1;(${resultadosRango}=${hipodromo})*(INT(resultados_galgos!$B$2:$B$5000)=INT(${fechaPick}))*(resultados_galgos!$C$2:$C$5000=${horaCarrera})*(resultados_galgos!$D$2:$D$5000=${trampa});0));"")`;
    // url_carrera_pata/race_id_pata: dato de la CARRERA entera, sin trampa
    // en la búsqueda (todas las trampas de esa carrera comparten el dato).
    const urlCarreraPataF = `=IFERROR(INDEX(resultados_galgos!$I$2:$I$5000;MATCH(1;(${resultadosRango}=${hipodromo})*(INT(resultados_galgos!$B$2:$B$5000)=INT(${fechaPick}))*(resultados_galgos!$C$2:$C$5000=${horaCarrera});0));"")`;
    const raceIdPataF = `=IFERROR(INDEX(resultados_galgos!$J$2:$J$5000;MATCH(1;(${resultadosRango}=${hipodromo})*(INT(resultados_galgos!$B$2:$B$5000)=INT(${fechaPick}))*(resultados_galgos!$C$2:$C$5000=${horaCarrera});0));"")`;
    const dogIdPataF = `=IFERROR(INDEX(resultados_galgos!$K$2:$K$5000;MATCH(1;(${resultadosRango}=${hipodromo})*(INT(resultados_galgos!$B$2:$B$5000)=INT(${fechaPick}))*(resultados_galgos!$C$2:$C$5000=${horaCarrera})*(resultados_galgos!$D$2:$D$5000=${trampa});0));"")`;

    formulas.push([posicionPataF, resultadoPataF, cuotaFinalPataF, urlCarreraPataF, raceIdPataF, dogIdPataF]);
  }

  sheet.getRange(2, COLUMNAS_APUESTAS_PATAS.length + 1, formulas.length, columnasFormula.length).setFormulas(formulas);
}

/**
 * `apuestas` = una fila por APUESTA (COLUMNAS_APUESTAS, las rellena el
 * script) + columnas fórmula que AGREGAN las filas de `apuestas_patas` con
 * el mismo `message_id` (COUNTIFS para contar patas ganadas/perdidas,
 * FILTER+PRODUCT/TEXTJOIN para combinar cuota/url/ids de todas las patas).
 * Funciona igual para 1, 2 o 3 patas sin ramas por tipo de apuesta - no
 * hace falta un bloque de fórmula distinto para simple/doble/tríple.
 *
 * `tipo_apuesta` en {'simple','doble','triple'} usa la lógica "ganan TODAS
 * las patas o pierde toda la apuesta". Trixie/Yankee (varias apuestas
 * independientes en un mismo boleto, con pagos parciales) no encajan en
 * esa lógica - `resultado_final` las deja en "revision_manual" a
 * propósito, sin intentar calcular un pago que no le corresponde a este
 * diseño (fuera de alcance, ver docs/BITACORA.md 2026-08-26).
 */
function crearApuestas_(ss) {
  const columnasFormula = [
    'num_patas', 'patas_ganadas', 'patas_perdidas', 'resultado_final',
    'fuente_resultado', 'retorno_real', 'unidades_netas', 'canodromo',
    'galgo', 'mensaje', 'cuota_final', 'url_carrera', 'race_id', 'dog_id',
    'value_pct',
  ];
  const cabeceras = COLUMNAS_APUESTAS.concat(columnasFormula);

  const sheet = ss.getSheetByName(SHEET_APUESTAS) || ss.insertSheet(SHEET_APUESTAS);
  sheet.clear();
  sheet.getRange(1, 1, 1, cabeceras.length).setValues([cabeceras]);
  sheet.setFrozenRows(1);

  const col = {};
  cabeceras.forEach(function (nombreCol, i) { col[nombreCol] = columnToLetter_(i + 1); });

  // Letras de columna de apuestas_patas (pestaña distinta, aparte de `col`).
  const patasCabeceras = COLUMNAS_APUESTAS_PATAS.concat([
    'posicion_pata', 'resultado_pata', 'cuota_final_pata', 'url_carrera_pata',
    'race_id_pata', 'dog_id_pata',
  ]);
  const patasCol = {};
  patasCabeceras.forEach(function (nombreCol, i) { patasCol[nombreCol] = columnToLetter_(i + 1); });
  const patasMsgId = `apuestas_patas!$${patasCol.message_id}$2:$${patasCol.message_id}$5000`;
  const patasResultado = `apuestas_patas!$${patasCol.resultado_pata}$2:$${patasCol.resultado_pata}$5000`;
  const patasCuotaFinal = `apuestas_patas!$${patasCol.cuota_final_pata}$2:$${patasCol.cuota_final_pata}$5000`;
  const patasUrl = `apuestas_patas!$${patasCol.url_carrera_pata}$2:$${patasCol.url_carrera_pata}$5000`;
  const patasRaceId = `apuestas_patas!$${patasCol.race_id_pata}$2:$${patasCol.race_id_pata}$5000`;
  const patasDogId = `apuestas_patas!$${patasCol.dog_id_pata}$2:$${patasCol.dog_id_pata}$5000`;
  const patasHipodromo = `apuestas_patas!$${patasCol.hipodromo}$2:$${patasCol.hipodromo}$5000`;
  const patasSeleccion = `apuestas_patas!$${patasCol.seleccion}$2:$${patasCol.seleccion}$5000`;

  const formulas = [];
  for (let fila = 2; fila <= FILAS_FORMULA_APUESTAS; fila++) {
    const messageId = col.message_id + fila;
    const tipoApuesta = col.tipo_apuesta + fila;
    const cuota = col.cuota + fila;
    const stake = col.stake + fila;
    const resultadoManual = col.resultado_manual + fila;
    const numPatas = col.num_patas + fila;
    const patasGanadas = col.patas_ganadas + fila;
    const patasPerdidas = col.patas_perdidas + fila;
    const resultadoFinal = col.resultado_final + fila;
    const retornoReal = col.retorno_real + fila;
    const cuotaFinal = col.cuota_final + fila;

    const numPatasF = `=COUNTIF(${patasMsgId};${messageId})`;
    const patasGanadasF = `=COUNTIFS(${patasMsgId};${messageId};${patasResultado};"gano")`;
    const patasPerdidasF = `=COUNTIFS(${patasMsgId};${messageId};${patasResultado};"perdio")`;

    // resultado_manual manda si existe. Si la fila no tiene ninguna
    // apuesta (message_id vacío - filas de margen sin usar todavía),
    // "pendiente" directamente, ANTES de mirar tipo_apuesta: un
    // tipo_apuesta vacío tampoco es uno de los soportados, así que sin
    // esta comprobación primero una fila vacía caía en "revision_manual"
    // por la misma vacuidad lógica que el bug de la v1 (probado en
    // caliente con las filas de control antes de aplicar esto a las 2000
    // filas - ver docs/BITACORA.md 2026-08-26).
    // Si sí hay apuesta: para los tipos soportados (TIPOS_APUESTA_SOPORTADOS
    // en Config.gs: simple/doble/triple - "todas las patas ganan o pierde
    // toda la apuesta"), pierde en cuanto CUALQUIER pata pierde; gana solo
    // si TODAS las patas ganan; si no hay ninguna pata todavía (num_patas=0,
    // no debería pasar con un pick real ya cargado, pero por si acaso,
    // antes de comparar patas_ganadas=num_patas, 0=0 daría "gano" si no se
    // guarda antes), pendiente. Cualquier tipo_apuesta NO soportado
    // (Trixie, Yankee, "otro"...) se manda a revision_manual a propósito -
    // no encajan en "todas ganan o pierde entera" y no hay fórmula de pago
    // para ellos todavía. Comprobación por POSITIVO (es uno de los
    // soportados) en vez de por negativo, para que un tipo nuevo e
    // inesperado también caiga en revision_manual por defecto.
    const tiposSoportadosF = TIPOS_APUESTA_SOPORTADOS.map(function (t) { return `${tipoApuesta}="${t}"`; }).join(';');
    const resultadoFinalF = `=IF(${resultadoManual}<>"";${resultadoManual};IF(${messageId}="";"pendiente";IF(NOT(OR(${tiposSoportadosF}));"revision_manual";IF(${numPatas}=0;"pendiente";IF(${patasPerdidas}>0;"perdio";IF(${patasGanadas}=${numPatas};"gano";"pendiente"))))))`;
    const fuenteResultadoF = `=IF(${resultadoManual}<>"";"manual";IF(OR(${resultadoFinal}="";${resultadoFinal}="pendiente";${resultadoFinal}="revision_manual");"";"auto"))`;
    const retornoRealF = `=IF(${resultadoFinal}="gano";${stake}*${cuota};IF(${resultadoFinal}="perdio";0;""))`;
    const unidadesNetasF = `=IF(${retornoReal}="";"";${retornoReal}-${stake})`;

    // canodromo/galgo: identificación legible de la apuesta (qué
    // canódromo(s) y qué galgo(s)), mismo TEXTJOIN que url_carrera/
    // race_id/dog_id - útil para leer la hoja de un vistazo y para el
    // informe de Looker Studio (pedido del usuario 2026-08-26).
    const canodromoF = `=IF(${numPatas}=0;"";TEXTJOIN(" | ";TRUE;FILTER(${patasHipodromo};${patasMsgId}=${messageId})))`;
    const galgoF = `=IF(${numPatas}=0;"";TEXTJOIN(" | ";TRUE;FILTER(${patasSeleccion};${patasMsgId}=${messageId})))`;
    // mensaje: texto crudo original del pick, tal cual lo mandó el
    // tipster - un solo mensaje por message_id (1:1, no hace falta
    // TEXTJOIN/FILTER como con las patas, que son varias por apuesta).
    const mensajeF = `=IFERROR(INDEX(mensajes_crudos!$C$2:$C$5000;MATCH(${messageId};mensajes_crudos!$A$2:$A$5000;0));"")`;

    // cuota_final: producto de la cuota de cierre de CADA pata (si a
    // alguna le falta su propio dato, el conjunto se deja en blanco - no
    // se puede multiplicar por un hueco). url_carrera/race_id/dog_id:
    // TEXTJOIN con "ignorar vacíos" de todas las patas - funciona igual
    // para 1, 2 o 3 patas sin fórmulas distintas por tipo de apuesta.
    // LET() evita evaluar cada FILTER/COUNTIFS dos veces.
    const cuotaFinalF = `=LET(vacias;COUNTIFS(${patasMsgId};${messageId};${patasCuotaFinal};"");IF(OR(${numPatas}=0;vacias>0);"";PRODUCT(FILTER(${patasCuotaFinal};${patasMsgId}=${messageId}))))`;
    const urlCarreraF = `=IF(${numPatas}=0;"";TEXTJOIN(" | ";TRUE;FILTER(${patasUrl};${patasMsgId}=${messageId})))`;
    const raceIdF = `=IF(${numPatas}=0;"";TEXTJOIN(" | ";TRUE;FILTER(${patasRaceId};${patasMsgId}=${messageId})))`;
    const dogIdF = `=IF(${numPatas}=0;"";TEXTJOIN(" | ";TRUE;FILTER(${patasDogId};${patasMsgId}=${messageId})))`;
    const valuePctF = `=IF(OR(${cuota}="";${cuotaFinal}="");"";ROUND((${cuota}/${cuotaFinal}-1)*100;1))`;

    formulas.push([
      numPatasF, patasGanadasF, patasPerdidasF, resultadoFinalF,
      fuenteResultadoF, retornoRealF, unidadesNetasF, canodromoF, galgoF,
      mensajeF, cuotaFinalF, urlCarreraF, raceIdF, dogIdF, valuePctF,
    ]);
  }

  sheet.getRange(2, COLUMNAS_APUESTAS.length + 1, formulas.length, columnasFormula.length).setFormulas(formulas);
}

function columnToLetter_(columna) {
  let letra = '';
  while (columna > 0) {
    const resto = (columna - 1) % 26;
    letra = String.fromCharCode(65 + resto) + letra;
    columna = Math.floor((columna - 1) / 26);
  }
  return letra;
}

/**
 * Toda hoja de Sheets nueva trae una pestaña por defecto ("Hoja 1" /
 * "Sheet1"). La quitamos una vez existen las pestañas reales (no se puede
 * borrar si es la única que queda).
 */
function borrarHojaPorDefecto_(ss) {
  const nombresReales = [SHEET_MENSAJES_CRUDOS, SHEET_APUESTAS, SHEET_APUESTAS_PATAS, SHEET_RESULTADOS_GALGOS];
  ss.getSheets().forEach(function (sheet) {
    if (nombresReales.indexOf(sheet.getName()) === -1 && ss.getSheets().length > 1) {
      ss.deleteSheet(sheet);
    }
  });
}
