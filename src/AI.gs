/**
 * Extracción de los campos del pick con la API de Gemini (Flash). Recibe
 * el texto (caption o mensaje) y, si hay foto, la imagen también, y pide
 * un JSON estricto con los campos de PLAN.md sección 5.
 *
 * Basado en 89 picks reales del tipster (ver docs/BITACORA.md), el prompt
 * contempla explícitamente: la palabra "Galgo" es opcional antes de la
 * trampa, el hipódromo puede ir antes o después de la hora, y las apuestas
 * combinadas (2+ carreras en un mismo pick) se extraen como una lista de
 * "patas" en vez de forzarlas al esquema de una sola selección (rediseño
 * 2026-08-26: antes estas se marcaban `es_apuesta_multiple` y se mandaban
 * enteras a revisión manual; ahora simples/dobles/tríples se procesan
 * solas - ver docs/BITACORA.md).
 */

const GEMINI_MODEL = 'gemini-3.6-flash';

const EXTRACTION_SYSTEM_PROMPT = [
  'Extraes datos estructurados de picks de apuestas de galgos (carreras de',
  'perros) enviados por un tipster a un grupo de Telegram. El texto puede',
  'venir con erratas (p. ej. "Ciota" en vez de "Cuota", o ";" en vez de ":"',
  'en la hora) - interprétalas igualmente si el significado es claro.',
  '',
  'Un pick puede ser una apuesta SIMPLE (1 carrera), una combinada de',
  'varias carreras con una sola cuota conjunta ("Apuesta Doble" = 2',
  'carreras, "Apuesta Tríple" = 3 carreras), o una GEMELA/TRÍO: acertar el',
  'ORDEN de llegada de 2 (gemela) o 3 (trío) galgos de UNA SOLA carrera.',
  'Una gemela/trío NO lleva cuota - se paga al dividendo oficial que',
  'publica la pista después de la carrera, así que "cuota" va a null en',
  'ese caso.',
  '',
  'Formato de gemela/trío en el texto: números de trampa separados por',
  'guion, indicando el orden ("3-4" = 3 primero, 4 segundo). Si aparece',
  'más de una combinación de orden (ej. "3-4 Y 4-3"), son varias jugadas',
  'a la vez con el mismo stake repartido - inclúyelas todas en',
  '"combinaciones". Si el texto dice "REVERSIBLE" sin desglosar (ej.',
  '"GEMELA REVERSIBLE 3-4"), tú mismo genera las combinaciones: para',
  'gemela reversible son las 2 permutaciones (3-4 y 4-3); para trío',
  'reversible, si no se desglosa, pon "tipo_apuesta":"otro" (no lo',
  'adivines con 6 combinaciones, es un caso raro que no se ha visto en la',
  'práctica).',
  '',
  'Cada carrera de una combinada (simple/doble/triple) es una "pata":',
  'mismo formato que una apuesta simple (hipódromo, hora, trampa,',
  'selección), una tras otra en el texto.',
  '',
  'Devuelve SOLO un JSON con esta forma exacta, sin texto adicional:',
  '{',
  '  "tipo_apuesta": "simple" | "doble" | "triple" | "gemela" | "trio" | "otro",',
  '  "patas": [',
  '    { "hipodromo": string o null, "hora_carrera": string "HH:MM" o null,',
  '      "trampa": string (solo el número) o null,',
  '      "seleccion": string (nombre del galgo) o null }',
  '  ],',
  '  "hipodromo_exotica": string o null,',
  '  "hora_carrera_exotica": string "HH:MM" o null,',
  '  "combinaciones": [["3","4"],["4","3"]] o null,',
  '  "cuota": number o null,',
  '  "stake": number o null',
  '}',
  '',
  'Reglas:',
  '- "tipo_apuesta": "simple" si es 1 sola carrera, "doble" si son 2,',
  '  "triple" si son 3, "gemela"/"trio" si es una apuesta de orden de UNA',
  '  carrera. Si es cualquier otra cosa (Trixie, Yankee, apuesta',
  '  "a puesto"/colocado, 4+ carreras, trío reversible sin desglosar, o no',
  '  estás seguro del tipo), pon "otro" - en ese caso rellena "patas" o',
  '  "combinaciones" con lo que puedas identificar de todas formas (ayuda',
  '  a la revisión manual), no lo dejes vacío si hay datos reconocibles.',
  '- Si "tipo_apuesta" es "simple"/"doble"/"triple": rellena "patas" (1, 2',
  '  o 3 elementos), deja "hipodromo_exotica"/"hora_carrera_exotica"/',
  '  "combinaciones" a null.',
  '- Si "tipo_apuesta" es "gemela"/"trio": rellena "hipodromo_exotica",',
  '  "hora_carrera_exotica" y "combinaciones" (cada combinación con 2',
  '  elementos para gemela, 3 para trío), deja "patas" como array vacío y',
  '  "cuota" a null.',
  '- "cuota" y "stake" son SIEMPRE los de la apuesta conjunta entera (la',
  '  única cuota y el único stake que aparecen en el mensaje), nunca por',
  '  carrera - no hay una cuota distinta por pata. Para gemela/trío,',
  '  "stake" es el TOTAL sumando todas las combinaciones (ej. "stake 2',
  '  cada una, 4 total" -> stake=4).',
  '- La palabra "Galgo" antes del número de trampa es opcional, ignórala.',
  '- El hipódromo y la hora de cada carrera pueden aparecer en cualquier',
  '  orden en su línea.',
  '- Copia el nombre del hipódromo COMPLETO, tal y como aparece en el texto',
  '  del mensaje ("Star Pelaw", nunca solo "Pelaw"; "Central Park", no',
  '  "Central"). Si el texto y la imagen no coinciden, manda el texto.',
  '- El nombre del galgo ("seleccion") es al revés: si hay imagen del boleto',
  '  y en ella se lee el nombre del galgo, cópialo EXACTO de la imagen (es el',
  '  nombre oficial de la casa de apuestas; el texto del tipster puede traer',
  '  erratas, ej. texto "Joys Of Dannielle", boleto "Joys Of Danielle" ->',
  '  "Joys Of Danielle"). Si no hay imagen o no se lee, usa el del texto.',
  '- Si un campo no aparece o no estás seguro, ponlo a null. No inventes',
  '  valores.',
].join('\n');

function callGeminiExtraction_(texto, fotoBlob) {
  const parts = [{ text: texto || '(sin texto, solo imagen)' }];
  if (fotoBlob) {
    parts.push({
      inline_data: {
        mime_type: fotoBlob.getContentType() || 'image/jpeg',
        data: Utilities.base64Encode(fotoBlob.getBytes()),
      },
    });
  }

  const payload = {
    system_instruction: { parts: [{ text: EXTRACTION_SYSTEM_PROMPT }] },
    contents: [{ role: 'user', parts: parts }],
    generationConfig: {
      responseMimeType: 'application/json',
      // Sin esto, el modelo gasta cientos de tokens de razonamiento interno
      // en una extracción trivial (probado: ~580 tokens de "thinking" con
      // presupuesto por defecto vs. 0 con 128) - más lento y más cuota
      // gastada del tier gratis, sin mejorar el resultado.
      thinkingConfig: { thinkingBudget: 128 },
    },
  };

  const url = 'https://generativelanguage.googleapis.com/v1beta/models/' +
    GEMINI_MODEL + ':generateContent?key=' + getAiApiKey_();

  // Reintentos ante 429 (rate-limit del tier gratis) y 503 (sobrecarga
  // transitoria): probado en producción el 2026-08-26 que sin esto, un
  // 429 puntual (el tier gratis de Gemini tiene un límite bajo de
  // peticiones/minuto, ver docs/BITACORA.md) tira un pick real entero a
  // "revision_manual" sin necesidad - 2 picks reales del tipster se
  // perdieron así el mismo día. 3 intentos con espera creciente (Apps
  // Script tiene 6 min de límite de ejecución total, esto añade como
  // mucho ~20s en el peor caso).
  const MAX_REINTENTOS_GEMINI = 3;
  let ultimoError;
  for (let intento = 0; intento < MAX_REINTENTOS_GEMINI; intento++) {
    const response = UrlFetchApp.fetch(url, {
      method: 'post',
      contentType: 'application/json',
      payload: JSON.stringify(payload),
      muteHttpExceptions: true,
    });

    const status = response.getResponseCode();
    if (status === 200) {
      const body = JSON.parse(response.getContentText());
      const textoRespuesta = body.candidates[0].content.parts[0].text.trim();
      return JSON.parse(textoRespuesta);
    }

    ultimoError = new Error('Error de la API de Gemini (' + status + '): ' + response.getContentText());
    const esReintentable = status === 429 || status === 503;
    if (!esReintentable || intento === MAX_REINTENTOS_GEMINI - 1) {
      throw ultimoError;
    }
    Utilities.sleep(3000 * Math.pow(2, intento)); // 3s, 6s, 12s
  }
  throw ultimoError;
}

/**
 * Cuántas patas se esperan para cada tipo de apuesta soportado
 * (TIPOS_APUESTA_SOPORTADOS en Config.gs). "otro" no tiene un número fijo,
 * no se valida aquí - va directo a revisión manual.
 */
const NUM_PATAS_POR_TIPO = { simple: 1, doble: 2, triple: 3 };

const NUM_TRAMPAS_POR_TIPO_EXOTICA = { gemela: 2, trio: 3 };

/**
 * Valida el JSON ya extraído por Gemini para gemela/trío (misma idea que
 * las comprobaciones de extraerPick, pero para el esquema de
 * combinaciones en vez de patas). No llama a la IA - función pura,
 * testeable con un objeto ya construido a mano.
 */
function validarExtraccionExotica_(extraido) {
  const numEsperado = NUM_TRAMPAS_POR_TIPO_EXOTICA[extraido.tipo_apuesta];
  const combinaciones = extraido.combinaciones || [];

  if (combinaciones.length === 0) {
    return { ok: false, motivo: 'faltan_campos', camposFaltantes: ['combinaciones'] };
  }
  const todasLongitudCorrecta = combinaciones.every(function (c) { return c.length === numEsperado; });
  if (!todasLongitudCorrecta) {
    return { ok: false, motivo: 'num_patas_incorrecto' };
  }

  const camposFaltantes = [];
  if (!extraido.hipodromo_exotica) camposFaltantes.push('hipodromo_exotica');
  if (!extraido.hora_carrera_exotica) camposFaltantes.push('hora_carrera_exotica');
  if (extraido.stake === null || extraido.stake === undefined || extraido.stake === '') {
    camposFaltantes.push('stake');
  }
  if (camposFaltantes.length > 0) {
    return { ok: false, motivo: 'faltan_campos', camposFaltantes: camposFaltantes };
  }

  return {
    ok: true,
    esExotica: true,
    tipoApuesta: extraido.tipo_apuesta,
    hipodromo: extraido.hipodromo_exotica,
    horaCarrera: extraido.hora_carrera_exotica,
    combinaciones: combinaciones.map(function (c) { return c.map(String); }),
    stakeTotal: Number(extraido.stake),
    stakePorCombinacion: redondear2_(Number(extraido.stake) / combinaciones.length),
  };
}

function test_validarExtraccionExotica() {
  // Caso real: "GEMELA 3-4 Y 4-3 - STAKE 2 CADA UNA (STAKE 4 TOTAL)" en Star Pelaw 22:31.
  const real = validarExtraccionExotica_({
    tipo_apuesta: 'gemela',
    hipodromo_exotica: 'Star Pelaw',
    hora_carrera_exotica: '22:31',
    combinaciones: [['3', '4'], ['4', '3']],
    cuota: null,
    stake: 4,
  });
  assertIguales_(real.ok, true, 'gemela con todos los campos -> ok');
  assertIguales_(real.tipoApuesta, 'gemela', 'tipoApuesta pasa tal cual');
  assertIguales_(real.combinaciones.length, 2, 'las 2 combinaciones (3-4 y 4-3)');
  assertIguales_(real.stakeTotal, 4, 'stakeTotal = 4');
  assertIguales_(real.stakePorCombinacion, 2, 'stakePorCombinacion = 4/2 = 2');

  const trioMalFormado = validarExtraccionExotica_({
    tipo_apuesta: 'trio',
    hipodromo_exotica: 'Harlow',
    hora_carrera_exotica: '19:00',
    combinaciones: [['1', '2']], // solo 2 trampas, un trio necesita 3
    stake: 6,
  });
  assertIguales_(trioMalFormado.ok, false, 'trio con combinacion de 2 trampas -> mal formado');
  assertIguales_(trioMalFormado.motivo, 'num_patas_incorrecto', 'motivo correcto');

  const sinStake = validarExtraccionExotica_({
    tipo_apuesta: 'gemela',
    hipodromo_exotica: 'Harlow',
    hora_carrera_exotica: '19:00',
    combinaciones: [['1', '2']],
    stake: null,
  });
  assertIguales_(sinStake.ok, false, 'sin stake -> faltan_campos');
  assertIguales_(sinStake.camposFaltantes.indexOf('stake') !== -1, true, 'stake en la lista de faltantes');

  Logger.log('test_validarExtraccionExotica: OK, todas las comprobaciones pasaron.');
}

/**
 * Canódromos que ya han cruzado alguna vez con éxito contra el parquet de
 * Proyecto Galgos: el job de la VM compara el nombre EXACTO (sin
 * mayúsculas), así que cualquier nombre de `resultados_galgos` es uno que
 * se sabe que funciona.
 */
function obtenerCanodromosConocidos_() {
  const sheet = getSheet_(SHEET_RESULTADOS_GALGOS);
  const index = getHeaderIndex_(sheet);
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) return [];
  const valores = sheet.getRange(2, index['canodromo'] + 1, lastRow - 1, 1).getValues();
  const vistos = {};
  valores.forEach(function (r) {
    const nombre = String(r[0] || '').trim();
    if (nombre) vistos[nombre] = true;
  });
  return Object.keys(vistos);
}

/**
 * Corrige el canódromo que devuelve la IA contra la lista de conocidos -
 * bug real 2026-09-22 (msg 315): el tipster escribió "Star Pelaw", Gemini
 * devolvió "Pelaw", y la VM (match exacto) nunca encontró la carrera, así
 * que la apuesta se quedó pendiente para siempre sin avisar. Solo corrige
 * si no hay ambigüedad: coincidencia exacta ignorando mayúsculas, o el
 * nombre extraído aparece como palabra(s) completa(s) dentro de UN SOLO
 * canódromo conocido. Si no, lo deja tal cual (canódromo nuevo o
 * ambiguo - no se adivina).
 */
function normalizarCanodromo_(nombre, conocidos) {
  const limpio = String(nombre === null || nombre === undefined ? '' : nombre).trim();
  if (!limpio) return nombre;
  const bajo = limpio.toLowerCase();

  const exacto = conocidos.filter(function (c) { return c.toLowerCase() === bajo; });
  if (exacto.length > 0) return exacto[0];

  const contienen = conocidos.filter(function (c) {
    return (' ' + c.toLowerCase() + ' ').indexOf(' ' + bajo + ' ') !== -1;
  });
  return contienen.length === 1 ? contienen[0] : limpio;
}

function test_normalizarCanodromo() {
  const conocidos = ['Star Pelaw', 'Central Park', 'Shelbourne Park', 'Nottingham', 'Harlow'];
  assertIguales_(normalizarCanodromo_('Pelaw', conocidos), 'Star Pelaw', 'caso real msg 315: Pelaw -> Star Pelaw');
  assertIguales_(normalizarCanodromo_('star pelaw ', conocidos), 'Star Pelaw', 'mayusculas/espacios -> nombre canonico');
  assertIguales_(normalizarCanodromo_('Park', conocidos), 'Park', 'ambiguo (2 canodromos con Park) -> se deja tal cual');
  assertIguales_(normalizarCanodromo_('ham', conocidos), 'ham', 'trozo de palabra (Nottingham) no cuenta');
  assertIguales_(normalizarCanodromo_('Yarmouth', conocidos), 'Yarmouth', 'canodromo nuevo -> se deja tal cual');
  assertIguales_(normalizarCanodromo_(null, conocidos), null, 'null se respeta (lo marca faltan_campos)');
  Logger.log('test_normalizarCanodromo: OK, todas las comprobaciones pasaron.');
}

/**
 * Punto de entrada usado por Main.gs. Devuelve:
 *   { ok: true, tipoApuesta, cuota, stake, patas: [{hipodromo, horaCarrera, trampa, seleccion}, ...] }
 *   { ok: false, motivo: 'tipo_no_soportado', tipoApuesta } - Trixie/Yankee/etc., fuera de alcance
 *   { ok: false, motivo: 'num_patas_incorrecto' } - el nº de patas no cuadra con tipo_apuesta
 *   { ok: false, motivo: 'faltan_campos', camposFaltantes: [...] }
 */
function extraerPick(texto, fotoBlob) {
  const extraido = callGeminiExtraction_(texto, fotoBlob);

  if (TIPOS_APUESTA_EXOTICA.indexOf(extraido.tipo_apuesta) !== -1) {
    const exotica = validarExtraccionExotica_(extraido);
    if (exotica.ok) exotica.hipodromo = normalizarCanodromo_(exotica.hipodromo, obtenerCanodromosConocidos_());
    return exotica;
  }

  if (TIPOS_APUESTA_SOPORTADOS.indexOf(extraido.tipo_apuesta) === -1) {
    return { ok: false, motivo: 'tipo_no_soportado', tipoApuesta: extraido.tipo_apuesta };
  }

  const patas = extraido.patas || [];
  if (patas.length !== NUM_PATAS_POR_TIPO[extraido.tipo_apuesta]) {
    return { ok: false, motivo: 'num_patas_incorrecto' };
  }

  const camposFaltantes = [];
  patas.forEach(function (pata, i) {
    CAMPOS_OBLIGATORIOS_PATA.forEach(function (campo) {
      if (pata[campo] === null || pata[campo] === undefined || pata[campo] === '') {
        camposFaltantes.push('pata' + (i + 1) + '.' + campo);
      }
    });
  });
  if (extraido.cuota === null || extraido.cuota === undefined || extraido.cuota === '') {
    camposFaltantes.push('cuota');
  }
  if (extraido.stake === null || extraido.stake === undefined || extraido.stake === '') {
    camposFaltantes.push('stake');
  }

  if (camposFaltantes.length > 0) {
    return { ok: false, motivo: 'faltan_campos', camposFaltantes: camposFaltantes };
  }

  const canodromosConocidos = obtenerCanodromosConocidos_();
  return {
    ok: true,
    tipoApuesta: extraido.tipo_apuesta,
    cuota: Number(extraido.cuota),
    stake: Number(extraido.stake),
    patas: patas.map(function (p) {
      return {
        hipodromo: normalizarCanodromo_(p.hipodromo, canodromosConocidos),
        horaCarrera: p.hora_carrera,
        trampa: String(p.trampa),
        seleccion: p.seleccion,
      };
    }),
  };
}
