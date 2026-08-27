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
  'Un pick puede ser una apuesta SIMPLE (1 carrera), o una combinada de',
  'varias carreras con una sola cuota conjunta ("Apuesta Doble" = 2',
  'carreras, "Apuesta Tríple" = 3 carreras). Cada carrera de la combinada',
  'es una "pata": mismo formato que una apuesta simple (hipódromo, hora,',
  'trampa, selección), una tras otra en el texto.',
  '',
  'Devuelve SOLO un JSON con esta forma exacta, sin texto adicional:',
  '{',
  '  "tipo_apuesta": "simple" | "doble" | "triple" | "otro",',
  '  "patas": [',
  '    { "hipodromo": string o null, "hora_carrera": string "HH:MM" o null,',
  '      "trampa": string (solo el número) o null,',
  '      "seleccion": string (nombre del galgo) o null }',
  '  ],',
  '  "cuota": number o null,',
  '  "stake": number o null',
  '}',
  '',
  'Reglas:',
  '- "tipo_apuesta": "simple" si es 1 sola carrera, "doble" si son 2,',
  '  "triple" si son 3. Si es cualquier otra cosa (Trixie, Yankee, apuesta',
  '  "a puesto"/colocado, 4+ carreras, o no estás seguro del tipo), pon',
  '  "otro" - en ese caso rellena "patas" con lo que puedas identificar de',
  '  todas formas (ayuda a la revisión manual), no lo dejes vacío si hay',
  '  datos reconocibles.',
  '- "patas" tiene tantos elementos como carreras: 1 para "simple", 2 para',
  '  "doble", 3 para "triple".',
  '- "cuota" y "stake" son SIEMPRE los de la apuesta conjunta entera (la',
  '  única cuota y el único stake que aparecen en el mensaje), nunca por',
  '  carrera - no hay una cuota distinta por pata.',
  '- La palabra "Galgo" antes del número de trampa es opcional, ignórala.',
  '- El hipódromo y la hora de cada carrera pueden aparecer en cualquier',
  '  orden en su línea.',
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

/**
 * Punto de entrada usado por Main.gs. Devuelve:
 *   { ok: true, tipoApuesta, cuota, stake, patas: [{hipodromo, horaCarrera, trampa, seleccion}, ...] }
 *   { ok: false, motivo: 'tipo_no_soportado', tipoApuesta } - Trixie/Yankee/etc., fuera de alcance
 *   { ok: false, motivo: 'num_patas_incorrecto' } - el nº de patas no cuadra con tipo_apuesta
 *   { ok: false, motivo: 'faltan_campos', camposFaltantes: [...] }
 */
function extraerPick(texto, fotoBlob) {
  const extraido = callGeminiExtraction_(texto, fotoBlob);

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

  return {
    ok: true,
    tipoApuesta: extraido.tipo_apuesta,
    cuota: Number(extraido.cuota),
    stake: Number(extraido.stake),
    patas: patas.map(function (p) {
      return {
        hipodromo: p.hipodromo,
        horaCarrera: p.hora_carrera,
        trampa: String(p.trampa),
        seleccion: p.seleccion,
      };
    }),
  };
}
