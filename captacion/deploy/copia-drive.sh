#!/usr/bin/env bash
# Sube a Google Drive una copia de todo lo que usa el cruce de las ventas de
# overoption con las personas de Telegram (premier_captacion/copia.py): la
# base de datos entera y un CSV por tabla. Lo lanza una vez al día
# captacion-copia@<instancia>.timer; a mano:
#
#   bash /opt/premier-captacion/copia-drive.sh real
#
# Necesita rclone configurado para root y, en el .env de la instancia,
# CAPTACION_COPIA_DRIVE=<remoto:carpeta> (p. ej. gdrive:premier-captacion).
# Deja una carpeta por día y «ultima» con la más reciente. La sesión de
# Telegram de la cuenta del dueño no está en la base y nunca se sube.
set -euo pipefail

fallo() { echo "❌ $*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || fallo "Hay que ejecutarlo como root (pon sudo delante)."
INSTANCIA="${1:-}"
case "$INSTANCIA" in prueba|real) ;; *) fallo "Uso: bash $0 <prueba|real>" ;; esac
ENV="/etc/premier-captacion/$INSTANCIA.env"
[ -f "$ENV" ] || fallo "No existe $ENV."
DESTINO=$(sed -n 's/^CAPTACION_COPIA_DRIVE=//p' "$ENV" | tail -n 1)
if [ -z "$DESTINO" ]; then
    echo "CAPTACION_COPIA_DRIVE vacío en $ENV: no hay copia a Drive configurada."
    exit 0
fi
command -v rclone >/dev/null || fallo "Falta rclone."

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
chown captacion:captacion "$TMP"
chmod 700 "$TMP"
cd /opt/premier-captacion
runuser -u captacion -- env CAPTACION_DB="/var/lib/premier-captacion/$INSTANCIA.db" PYTHONDONTWRITEBYTECODE=1 \
    /opt/premier-captacion/venv/bin/python -m premier_captacion.copia "$TMP"

DIA=$(TZ=Europe/Madrid date +%F)
rclone copy "$TMP" "$DESTINO/$INSTANCIA/$DIA"
rclone sync "$TMP" "$DESTINO/$INSTANCIA/ultima"
echo "✓ Copia subida a $DESTINO/$INSTANCIA/$DIA (y a $DESTINO/$INSTANCIA/ultima)"
