/**
 * Constantes y acceso a secrets. Los valores reales de los secrets viven
 * en PropertiesService (Project Settings > Script Properties en el editor
 * de Apps Script), nunca en este archivo. Ver PLAN.md sección 10.
 */

// Único grupo donde opera el bot (supergrupo tras añadir el bot como
// admin, ver docs/BITACORA.md 2026-08-20). Hace falta como constante para
// poder mandar mensajes fuera del flujo normal de doPost (reintentos
// programados) donde no hay un `msg.chat.id` disponible.
const TELEGRAM_CHAT_ID = -1004303594416;

const SHEET_MENSAJES_CRUDOS = 'mensajes_crudos';
const SHEET_APUESTAS = 'apuestas';
const SHEET_APUESTAS_PATAS = 'apuestas_patas';
const SHEET_RESULTADOS_GALGOS = 'resultados_galgos';

// `fecha_forward`: si el mensaje es un reenvío del propio tipster (picks
// antiguos que resenvía en bloque), aquí va la fecha ORIGINAL de la
// publicación (`msg.forward_date`/`msg.forward_origin.date`), no la de
// llegada al bot - vacío si no es un reenvío. Bug real encontrado
// 2026-08-26: sin esto, un mensaje que erroraba por cuota de Gemini
// agotada y se reintentaba luego (`reintentarMensajesConError`) perdía
// esa información para siempre (no había dónde leerla) y se le ponía la
// fecha de llegada como `fecha_pick` - con una carrera real coincidiendo
// por casualidad en el mismo hipódromo+hora+trampa ese mismo día, el
// fallback de "trampa ganadora" podía dar un resultado FALSO (comparando
// contra un galgo completamente distinto). Ver docs/BITACORA.md.
const COLUMNAS_MENSAJES_CRUDOS = [
  'message_id', 'fecha_recibido', 'contenido', 'foto_file_id', 'estado', 'fecha_forward',
];

// Rediseño 2026-08-26 (v2): antes `apuestas` tenía columnas fijas
// hipodromo_2/hora_2/trampa_2... para cubrir dobles/tríples - no escalaba
// a Trixie/Yankee (4 selecciones, varias apuestas independientes en un
// boleto). Ahora cada CARRERA de un pick es una fila en `apuestas_patas`
// (`COLUMNAS_APUESTAS_PATAS` más abajo), agrupadas por `message_id`; esta
// pestaña vuelve a ser una fila por APUESTA (no por carrera), con la
// cuota/stake CONJUNTOS (los del boleto entero) y un `tipo_apuesta` que
// dice cuántas patas esperar y qué lógica de pago aplicar. Las fórmulas
// (`resultado_final`, `cuota_final`, `url_carrera`, `race_id`, `dog_id`,
// `value_pct`...) agregan `apuestas_patas` por `message_id` - ver
// `crearApuestas_` en Setup.gs y docs/BITACORA.md 2026-08-26.
//
// tipo_apuesta: 'simple' | 'doble' | 'triple' hoy resuelven con la lógica
// "ganan TODAS las patas o pierde toda la apuesta". 'trixie'/'yankee' (con
// varias apuestas independientes y pagos parciales en un mismo boleto) NO
// encajan en esa lógica - quedan preparadas en el dato pero sin fórmula de
// pago todavía (fuera de alcance de hoy). Apuestas "a puesto" (gana si el
// galgo queda entre los 2 primeros) tampoco están cubiertas.
const COLUMNAS_APUESTAS = [
  'message_id', 'confirm_message_id', 'fecha_pick', 'tipo_apuesta', 'cuota',
  'stake', 'retorno_potencial', 'resultado_manual', 'oculto',
  'posible_duplicado_de', 'creado_en',
];

// Una fila por CARRERA de un pick (una apuesta simple tiene 1 fila aquí;
// una doble, 2; una tríple, 3...), agrupadas por `message_id` +
// `numero_pata` (1, 2, 3...). `apuestas` (arriba) agrega estas filas por
// `message_id` para dar el resultado conjunto de la apuesta entera.
const COLUMNAS_APUESTAS_PATAS = [
  'message_id', 'numero_pata', 'fecha_pick', 'hipodromo', 'hora_carrera',
  'trampa', 'seleccion', 'creado_en',
];

// Solo la escribe el script de la VM (gspread), nunca este código.
// cuota_final: SP de cierre en decimal (convertida desde el fraccionario de
// Racing Post), propia de CADA galgo. url_carrera y race_id: mismos para
// todas las filas de una misma carrera (no dependen de la trampa). dog_id:
// propio de cada galgo, igual que cuota_final - ver docs/BITACORA.md
// 2026-08-26.
const COLUMNAS_RESULTADOS_GALGOS = [
  'canodromo', 'fecha', 'hora', 'trap', 'nombre', 'posicion', 'actualizado_en',
  'cuota_final', 'url_carrera', 'race_id', 'dog_id',
];

const ESTADO_PENDIENTE = 'pendiente';
const ESTADO_PROCESADO = 'procesado';
const ESTADO_REVISION_MANUAL = 'revision_manual';
const ESTADO_ERROR = 'error';

// Por PATA (una carrera de un pick, simple o dentro de una combinada) -
// cuota/stake se validan aparte, son de la apuesta combinada entera, no
// por pata (ver AI.gs `extraerPick`).
const CAMPOS_OBLIGATORIOS_PATA = ['hipodromo', 'hora_carrera', 'trampa', 'seleccion'];

// tipo_apuesta que la fórmula de resultado_final sabe resolver (todas las
// patas ganan o pierde toda la apuesta) - cualquier otro valor (Trixie,
// Yankee, apuestas "a puesto"...) se manda a revision_manual, tanto en el
// bot (AI.gs `extraerPick`) como en la fórmula (Setup.gs), ver
// docs/BITACORA.md 2026-08-26.
const TIPOS_APUESTA_SOPORTADOS = ['simple', 'doble', 'triple'];

// Solo el panel de métricas (Dashboard.gs) convierte a euros para mostrar
// - el resto del proyecto sigue en unidades. Excepción explícita, ver
// CLAUDE.md y docs/superpowers/specs/2026-08-26-panel-metricas-design.md.
const TASA_EUR_POR_UNIDAD = 250;

function getScriptProperty_(key) {
  const value = PropertiesService.getScriptProperties().getProperty(key);
  if (!value) {
    throw new Error('Falta la propiedad de script "' + key + '". Configúrala en ' +
      'Project Settings > Script Properties antes de desplegar.');
  }
  return value;
}

function getBotToken_() {
  return getScriptProperty_('TELEGRAM_BOT_TOKEN');
}

function getWebhookToken_() {
  return getScriptProperty_('WEBHOOK_SECRET_TOKEN');
}

function getAiApiKey_() {
  return getScriptProperty_('AI_PROVIDER_API_KEY');
}

/**
 * Comprueba que todas las propiedades necesarias están configuradas.
 * Ejecutar manualmente desde el editor tras el primer despliegue.
 */
function checkConfig() {
  const requeridas = ['TELEGRAM_BOT_TOKEN', 'WEBHOOK_SECRET_TOKEN', 'AI_PROVIDER_API_KEY'];
  const props = PropertiesService.getScriptProperties().getProperties();
  const faltan = requeridas.filter(function (k) { return !props[k]; });
  if (faltan.length === 0) {
    Logger.log('OK: todas las propiedades requeridas están configuradas.');
  } else {
    Logger.log('Faltan propiedades: ' + faltan.join(', '));
  }
}
