#!/usr/bin/env bash
# Conecta la cuenta de Telegram que leerá el programa de carpetas (fase 3)
# o el histórico (fase 4). Lo ejecuta el DUEÑO en su propia terminal SSH:
#
#   bash /opt/premier-captacion/conectar-cuenta.sh prueba    (cuenta secundaria, pruebas)
#   bash /opt/premier-captacion/conectar-cuenta.sh real      (tu cuenta, solo con tu visto bueno)
#
# Pide el teléfono, el código que llega por Telegram y, si la tienes, la
# contraseña de verificación en dos pasos. NO PEGUES el código en ningún
# chat (Telegram lo anula). Lo único que se guarda es la sesión, en
# /var/lib/premier-captacion/<instancia>-cuenta.session (solo root y
# «captacion»). La sesión aparece en Telegram → Ajustes → Dispositivos como
# «Premier captación (VM)» y se puede cerrar desde ahí cuando quieras.
#
# Con «prueba» arranca después el lector en modo SIMULACIÓN (solo avisa de
# lo que haría). Con «real» no arranca nada: eso es la fase 6.
set -euo pipefail

DESTINO=/opt/premier-captacion
fallo() { echo "❌ $*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || fallo "Hay que ejecutarlo como root (pon sudo delante)."
[ -t 0 ] || fallo "Esto lo tiene que ejecutar el dueño en su propia terminal: pide el código de Telegram."
INSTANCIA="${1:-}"
case "$INSTANCIA" in prueba|real) ;; *) fallo "Uso: bash $0 <prueba|real>" ;; esac
ENV="/etc/premier-captacion/$INSTANCIA.env"
[ -x "$DESTINO/venv/bin/python" ] || fallo "Falta el entorno de Python: ejecuta antes bash $DESTINO/instalar.sh prueba"

if [ ! -f "$ENV" ]; then
    # Pasa con «real» antes de instalar el bot real (fase 4 antes de la 5):
    # la configuración se crea vacía y el bot real NO se instala ni arranca.
    install -d -m 700 /etc/premier-captacion
    (umask 077 && cp "$DESTINO/instancia.env.example" "$ENV")
    echo "Creada la configuración $ENV (el bot de esta instancia no se instala ni arranca)."
fi
if ! grep -qE '^CAPTACION_API_HASH=[0-9a-f]{32}$' "$ENV"; then
    echo "Falta el api_id / api_hash de my.telegram.org (sección «API development tools»)."
    CAPTACION_NO_REINICIAR=1 bash "$DESTINO/configurar.sh" "$INSTANCIA" api
fi

ESTABA=0
if systemctl is-active --quiet "captacion-lector@$INSTANCIA" 2>/dev/null; then
    ESTABA=1
    systemctl stop "captacion-lector@$INSTANCIA"  # una sesión no puede usarse dos veces a la vez
fi

echo
echo "⚠️  Vas a conectar una cuenta de Telegram al programa. Equivale a dar acceso a la cuenta:"
echo "   el programa SOLO lee y organiza carpetas (nunca envía nada; está bloqueado en el código),"
echo "   y puedes cerrar la sesión cuando quieras en Telegram → Ajustes → Dispositivos."
read -r -p "   Escribe SI para continuar: " confirmacion
[ "$confirmacion" = "SI" ] || fallo "Cancelado."
echo

bash "$DESTINO/lector.sh" "$INSTANCIA" iniciar-sesion

if [ "$INSTANCIA" = prueba ] || [ "$ESTABA" = 1 ]; then
    systemctl enable --quiet "captacion-lector@$INSTANCIA"
    systemctl restart "captacion-lector@$INSTANCIA"
    sleep 5
    if systemctl is-active --quiet "captacion-lector@$INSTANCIA"; then
        echo "✅ Lector de carpetas en marcha. Modo: $(grep -q '^CAPTACION_LECTOR_SIMULAR=0$' "$ENV" && echo REAL || echo 'SIMULACIÓN (solo avisa por el bot de lo que haría)')."
    else
        echo "❌ El lector no ha arrancado. Registro:" >&2
        journalctl -u "captacion-lector@$INSTANCIA" -n 20 --no-pager >&2 || true
        exit 1
    fi
else
    echo "No arranco el lector de carpetas de esta cuenta (eso es la fase 6, con tu visto bueno)."
    echo "Siguiente paso posible (solo lectura): bash $DESTINO/leer-historico.sh $INSTANCIA"
fi
