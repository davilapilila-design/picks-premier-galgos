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
set -euo pipefail

DESTINO=/opt/premier-captacion
fallo() { echo "❌ $*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || fallo "Hay que ejecutarlo como root (pon sudo delante)."
INSTANCIA="${1:-}"
case "$INSTANCIA" in prueba|real) ;; *) fallo "Uso: bash $0 <prueba|real>" ;; esac
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

echo "Leyendo el histórico (solo lectura; puede tardar unos minutos)..."
bash "$DESTINO/lector.sh" "$INSTANCIA" historico
