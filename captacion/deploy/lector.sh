#!/usr/bin/env bash
# Ejecuta el lector de la cuenta del dueño A MANO, como el usuario de
# sistema «captacion» y con la configuración de la instancia. Lo usan
# conectar-cuenta.sh y leer-historico.sh; también sirve para pruebas:
#
#   bash /opt/premier-captacion/lector.sh prueba embudo-prueba <id de Telegram>
#
# No lo ejecutes mientras captacion-lector@<instancia> esté en marcha: una
# misma sesión usada por dos programas a la vez hace que Telegram la anule.
set -euo pipefail

fallo() { echo "❌ $*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || fallo "Hay que ejecutarlo como root (pon sudo delante)."
INSTANCIA="${1:-}"
case "$INSTANCIA" in prueba|real) ;; *) fallo "Uso: bash $0 <prueba|real> <modo> [argumentos]" ;; esac
shift
ENV="/etc/premier-captacion/$INSTANCIA.env"
[ -f "$ENV" ] || fallo "No existe $ENV."
[ -x /opt/premier-captacion/venv/bin/python ] || fallo "Falta el entorno de Python: ejecuta antes instalar.sh."

# embudo-prueba solo toca la base de datos; el resto usa la sesión de Telegram.
if [ "${1:-}" != embudo-prueba ] && systemctl is-active --quiet "captacion-lector@$INSTANCIA" 2>/dev/null; then
    fallo "captacion-lector@$INSTANCIA está en marcha: páralo antes (systemctl stop captacion-lector@$INSTANCIA)."
fi

install -d -o captacion -g captacion -m 700 /var/lib/premier-captacion
# Se cargan solo las variables CAPTACION_* del archivo, sin ejecutarlo como
# un script (algún valor lleva espacios, p. ej. «free send»).
while IFS= read -r linea || [ -n "$linea" ]; do
    if [[ "$linea" =~ ^(CAPTACION_[A-Z_]+)=(.*)$ ]]; then
        export "${BASH_REMATCH[1]}=${BASH_REMATCH[2]}"
    fi
done < "$ENV"
export CAPTACION_DB="/var/lib/premier-captacion/$INSTANCIA.db"
export CAPTACION_SESION="/var/lib/premier-captacion/$INSTANCIA-cuenta"
export PYTHONDONTWRITEBYTECODE=1
cd /opt/premier-captacion
umask 077
if [ "${1:-}" = analisis ] || [ "${1:-}" = ventas ]; then
    # El análisis (y «ventas») escribe en un Google Sheet: la credencial solo la lee root,
    # así que se le deja una copia privada mientras dura y luego se borra.
    [ -f /etc/premier-captacion/google.json ] || fallo "Falta la credencial de Google: ejecuta antes instalar.sh."
    CREDENCIAL=$(mktemp)
    trap 'rm -f "$CREDENCIAL"' EXIT
    install -m 600 -o captacion -g captacion /etc/premier-captacion/google.json "$CREDENCIAL"
    export CAPTACION_GOOGLE_CREDENCIAL="$CREDENCIAL"
    runuser -p -u captacion -- /opt/premier-captacion/venv/bin/python -m premier_captacion.lector "$@"
    exit $?
fi
exec runuser -p -u captacion -- /opt/premier-captacion/venv/bin/python -m premier_captacion.lector "$@"
