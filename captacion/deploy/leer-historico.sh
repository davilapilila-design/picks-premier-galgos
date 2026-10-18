#!/usr/bin/env bash
# Fase 4: lee el histórico de la cuenta conectada (SOLO LECTURA: no toca
# carpetas ni envía nada) y apunta en la base de datos de la instancia a
# quien recibió una bienvenida manual, si contestó y si recibió enlace de
# venta. Se puede repetir sin duplicar nada.
#
#   bash /opt/premier-captacion/leer-historico.sh prueba
#   bash /opt/premier-captacion/leer-historico.sh real
#
# Si el lector de carpetas está en marcha, lo para mientras (una sesión no
# puede usarse desde dos programas a la vez) y lo vuelve a arrancar.
#
# Si la instancia aún no sabe cuál es el canal principal (en «real», antes
# de instalar el bot real), lo pregunta: pegas un enlace de invitación del
# canal, se comprueba a qué canal lleva (sin unirse) y se guarda.
set -euo pipefail

DESTINO=/opt/premier-captacion
fallo() { echo "❌ $*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || fallo "Hay que ejecutarlo como root (pon sudo delante)."
INSTANCIA="${1:-}"
case "$INSTANCIA" in prueba|real) ;; *) fallo "Uso: bash $0 <prueba|real>" ;; esac
ENV="/etc/premier-captacion/$INSTANCIA.env"
[ -f "$ENV" ] || fallo "No existe $ENV: el dueño tiene que ejecutar antes conectar-cuenta.sh $INSTANCIA"
[ -f "/var/lib/premier-captacion/$INSTANCIA-cuenta.session" ] \
    || fallo "La cuenta no está conectada: el dueño tiene que ejecutar antes conectar-cuenta.sh $INSTANCIA"

ESTABA=0
if systemctl is-active --quiet "captacion-lector@$INSTANCIA" 2>/dev/null; then
    ESTABA=1
    systemctl stop "captacion-lector@$INSTANCIA"
fi
volver() {
    if [ "$ESTABA" = 1 ]; then
        systemctl start "captacion-lector@$INSTANCIA" || true
    fi
}
trap volver EXIT

# Sin saber cuál es el canal principal, sus enlaces contarían como de venta.
if ! grep -qE '^CAPTACION_CANAL_ID=-100[0-9]+$' "$ENV"; then
    [ -t 0 ] || fallo "Falta el canal principal: ejecútalo en tu terminal para que te lo pregunte."
    echo "Primero, cuál es tu canal principal (para no contar sus enlaces como de venta)."
    read -r -p "Pega un enlace de invitación de tu canal principal (t.me/+…): " ENLACE
    SALIDA=$(bash "$DESTINO/lector.sh" "$INSTANCIA" canal-de-enlace "$ENLACE") \
        || fallo "No he podido saber a qué canal lleva ese enlace. No he leído nada."
    CANAL=${SALIDA%%$'\t'*}
    TITULO=${SALIDA#*$'\t'}
    read -r -p "   Lleva al canal «$TITULO». Escribe SI si es tu canal principal: " confirmacion
    [ "$confirmacion" = SI ] || fallo "Cancelado: no he leído nada."
    CAPTACION_NO_REINICIAR=1 bash "$DESTINO/configurar.sh" "$INSTANCIA" canal "$CANAL"
fi

echo "Leyendo el histórico (solo lectura; puede tardar unos minutos)..."
bash "$DESTINO/lector.sh" "$INSTANCIA" historico
