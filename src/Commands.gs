/**
 * Comandos que llegan como reply al mensaje de confirmación del bot.
 * Ver PLAN.md sección 6.3.
 */

const CORREGIR_RE = /^corregir\s+([a-z_]+)\s*=\s*(.+)$/i;
// cuota/stake viven en `apuestas` (son de la apuesta combinada entera);
// hipodromo/hora_carrera/trampa/seleccion viven en `apuestas_patas` desde
// el rediseño 2026-08-26 - ver más abajo cómo se decide dónde corregir.
const CAMPOS_CORREGIBLES_APUESTA = ['cuota', 'stake'];
const CAMPOS_CORREGIBLES_PATA = ['hipodromo', 'hora_carrera', 'trampa', 'seleccion'];
const CAMPOS_CORREGIBLES = CAMPOS_CORREGIBLES_APUESTA.concat(CAMPOS_CORREGIBLES_PATA);

/**
 * Procesa un reply al mensaje de confirmación. Devuelve el texto de
 * respuesta a enviar, o null si el texto no coincide con ningún comando
 * reconocido (en ese caso no se contesta nada).
 */
function procesarComandoReply(textoOriginal, confirmMessageId) {
  const texto = (textoOriginal || '').trim();
  const textoLower = texto.toLowerCase();

  const apuesta = findApuestaByConfirmMessageId(confirmMessageId);
  if (!apuesta) {
    return 'No encuentro la apuesta asociada a ese mensaje (¿es muy antigua?).';
  }

  if (textoLower === 'gano' || textoLower === 'ganó' || textoLower === 'ganado') {
    setApuestaField(apuesta, 'resultado_manual', 'gano');
    return 'Marcado como GANADO.';
  }

  if (textoLower === 'perdio' || textoLower === 'perdió' || textoLower === 'perdido') {
    setApuestaField(apuesta, 'resultado_manual', 'perdio');
    return 'Marcado como PERDIDO.';
  }

  if (textoLower === 'ocultar') {
    setApuestaField(apuesta, 'oculto', true);
    return 'Apuesta ocultada del panel.';
  }

  if (textoLower === 'mostrar') {
    setApuestaField(apuesta, 'oculto', false);
    return 'Apuesta vuelta a mostrar en el panel.';
  }

  const matchCorregir = texto.match(CORREGIR_RE);
  if (matchCorregir) {
    const campo = matchCorregir[1].toLowerCase();
    const valorTexto = matchCorregir[2].trim();

    if (!CAMPOS_CORREGIBLES.includes(campo)) {
      return 'No se puede corregir el campo "' + campo + '". Campos válidos: ' +
        CAMPOS_CORREGIBLES.join(', ') + '.';
    }

    const valor = (campo === 'cuota' || campo === 'stake') ? Number(valorTexto) : valorTexto;
    if ((campo === 'cuota' || campo === 'stake') && isNaN(valor)) {
      return 'Valor no numérico para ' + campo + ': "' + valorTexto + '".';
    }

    if (CAMPOS_CORREGIBLES_APUESTA.includes(campo)) {
      setApuestaField(apuesta, campo, valor);
      return 'Corregido ' + campo + ' = ' + valor + '.';
    }

    // Campo de pata (hipodromo/hora_carrera/trampa/seleccion): solo se
    // puede corregir sin ambigüedad si la apuesta tiene una única carrera
    // (simple). Para dobles/tríples haría falta decir cuál pata - no
    // implementado todavía (fuera de alcance, ver docs/BITACORA.md
    // 2026-08-26), se avisa en vez de adivinar cuál corregir.
    const messageId = apuesta.sheet.getRange(apuesta.row, apuesta.index['message_id'] + 1).getValue();
    const patas = findApuestaPatasByMessageId(messageId);
    if (patas.length !== 1) {
      return 'Esta apuesta tiene ' + patas.length + ' carreras - no se puede corregir "' +
        campo + '" sin decir a cuál te refieres (pendiente de implementar para dobles/tríples).';
    }
    setApuestaPataField(patas[0], campo, valor);
    return 'Corregido ' + campo + ' = ' + valor + '.';
  }

  return null;
}
