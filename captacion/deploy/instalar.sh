#!/usr/bin/env bash
# Instala o actualiza el bot de captación en la VM. Se ejecuta como root.
#
# Primera vez:
#   curl -fsSLo /tmp/instalar-captacion.sh https://raw.githubusercontent.com/davilapilila-design/picks-premier-galgos/captacion-bienvenida/captacion/deploy/instalar.sh
#   bash /tmp/instalar-captacion.sh prueba
#
# Para actualizar más adelante a la última versión del código:
#   bash /opt/premier-captacion/instalar.sh prueba
#
# Si lo ejecuta una sesión de Claude (sin terminal), con
# CAPTACION_SIN_TERMINAL=1 delante: instala todo y se para a falta del
# token, que el dueño pega desde su propia terminal (configurar.sh).
#
# Se puede repetir sin miedo. Pasos:
#   1. Comprueba Python 3.9+ y las zonas horarias.
#   2. Crea el usuario de sistema "captacion" (sin privilegios) si no existe.
#   3. Descarga el código de GitHub (rama captacion-bienvenida, o la que
#      diga CAPTACION_RAMA) y lo deja en /opt/premier-captacion.
#   4. Instala los servicios de systemd.
#   5. Crea /etc/premier-captacion/<instancia>.env (solo root) si no existe,
#      pide el token si falta (no se ve al pegarlo) y pone el perfil
#      Dronwhite si está vacío. Los datos que ya haya no se tocan.
#   6. Crea un entorno de Python propio en /opt/premier-captacion/venv con
#      gspread (copia al Google Sheet, fase 2) y Telethon (lector de la cuenta
#      del dueño, fases 3 y 4), y copia la credencial de la cuenta de
#      servicio de picks a /etc/premier-captacion/google.json.
#   7. Arranca (o reinicia) el bot y activa los resúmenes y la copia al Sheet.
#      El lector de carpetas NO lo activa: lo hace conectar-cuenta.sh. Si ya
#      estaba activo, lo reinicia para que use el código nuevo.
set -euo pipefail

REPO=davilapilila-design/picks-premier-galgos
RAMA="${CAPTACION_RAMA:-captacion-bienvenida}"
DESTINO=/opt/premier-captacion
DIR_CONFIG=/etc/premier-captacion
DIR_UNIDADES=/etc/systemd/system
PY=/usr/bin/python3
VERSION_GSPREAD=6.1.4
VERSION_TELETHON=1.45.0
# Cuenta de servicio de Google que ya usa el sistema de picks en la VM (solo
# se lee, para copiarla a $DIR_CONFIG/google.json).
ORIGEN_GOOGLE=/root/.config/picks-premier-galgos/service_account.json

fallo() { echo "❌ $*" >&2; exit 1; }
paso() { echo; echo "▶ $*"; }

[ "$(id -u)" -eq 0 ] || fallo "Hay que ejecutarlo como root (pon sudo delante)."
INSTANCIA="${1:-}"
case "$INSTANCIA" in
    prueba) ;;
    real)
        if [ -z "${CAPTACION_REEJECUTADO:-}" ]; then  # ya se confirmó antes de reejecutarse
            echo "⚠️  Vas a instalar el bot REAL, el del canal PREMIER GALGOS."
            read -r -p "   Escribe SI para continuar: " confirmacion
            [ "$confirmacion" = "SI" ] || fallo "Cancelado."
        fi
        ;;
    *) fallo "Uso: bash $0 prueba   (o «real», solo para producción)" ;;
esac

paso "Comprobando Python y zonas horarias"
[ -x "$PY" ] || fallo "No encuentro $PY (instálalo con: apt install python3)"
"$PY" -c 'import sys; sys.exit(sys.version_info < (3, 9))' \
    || fallo "Hace falta Python 3.9 o superior (hay $("$PY" -V 2>&1))"
"$PY" -c 'from zoneinfo import ZoneInfo; ZoneInfo("Europe/Madrid")' 2>/dev/null \
    || fallo "Faltan las zonas horarias (instálalas con: apt install tzdata)"
echo "   $("$PY" -V 2>&1) ✓"

paso "Usuario de sistema «captacion»"
if id captacion >/dev/null 2>&1; then
    echo "   ya existe ✓"
else
    useradd --system --user-group --no-create-home --shell /usr/sbin/nologin captacion
    echo "   creado ✓"
fi

if [ -n "${CAPTACION_DESCARGA:-}" ]; then
    # Lo descargó un instalador anterior, que se ha reejecutado con este
    # (ver más abajo): se usa tal cual, sin volver a descargar.
    TMP=$CAPTACION_DESCARGA
    trap 'rm -rf "$TMP"' EXIT
    VERSION=$CAPTACION_VERSION_DESCARGA
    paso "Código ya descargado"
elif [ -n "${CAPTACION_ORIGEN:-}" ]; then
    TMP=$(mktemp -d)
    trap 'rm -rf "$TMP"' EXIT
    # Solo para pruebas: copia de una carpeta local en vez de descargar.
    paso "Copiando el código de $CAPTACION_ORIGEN"
    cp -r "$CAPTACION_ORIGEN/captacion" "$TMP/captacion"
    VERSION="local $(date '+%Y-%m-%d %H:%M')"
else
    TMP=$(mktemp -d)
    trap 'rm -rf "$TMP"' EXIT
    paso "Descargando el código (rama $RAMA)"
    # Se fija el commit exacto para que lo descargado y la versión anotada
    # coincidan aunque alguien suba cambios justo a la vez.
    SHA=$(curl -fsSL -H 'Accept: application/vnd.github.sha' \
          "https://api.github.com/repos/$REPO/commits/$RAMA") \
        || fallo "No se puede consultar GitHub (¿hay internet en la VM?)"
    [[ "$SHA" =~ ^[0-9a-f]{40}$ ]] || fallo "Respuesta inesperada de GitHub al pedir la versión"
    curl -fsSL "https://github.com/$REPO/archive/$SHA.tar.gz" \
        | tar -xz -C "$TMP" --strip-components=1 \
        || fallo "No se ha podido descargar el código"
    VERSION="${SHA:0:7} (rama $RAMA, instalada $(date '+%Y-%m-%d %H:%M'))"
fi
[ -f "$TMP/captacion/premier_captacion/bot.py" ] || fallo "Lo descargado no trae el código del bot"
echo "   versión $VERSION ✓"

# Si el instalador descargado no es el que se está ejecutando (al actualizar
# desde una versión anterior), se sigue con el nuevo: así una sola ejecución
# aplica siempre todos los pasos de la versión nueva.
NUEVO="$TMP/captacion/deploy/instalar.sh"
if [ -z "${CAPTACION_REEJECUTADO:-}" ] && ! cmp -s "$0" "$NUEVO"; then
    echo "   el instalador ha cambiado: sigo con el nuevo"
    trap - EXIT  # la carpeta descargada la borrará el instalador nuevo
    CAPTACION_REEJECUTADO=1 CAPTACION_DESCARGA="$TMP" CAPTACION_VERSION_DESCARGA="$VERSION" \
        exec bash "$NUEVO" "$INSTANCIA"
fi

paso "Instalando en $DESTINO"
install -d -m 755 "$DESTINO"
rm -rf "$DESTINO/premier_captacion.nuevo"
cp -r "$TMP/captacion/premier_captacion" "$DESTINO/premier_captacion.nuevo"
rm -rf "$DESTINO/premier_captacion"
mv "$DESTINO/premier_captacion.nuevo" "$DESTINO/premier_captacion"
for script in instalar configurar lector conectar-cuenta leer-historico; do
    install -m 755 "$TMP/captacion/deploy/$script.sh" "$DESTINO/"
done
install -m 644 "$TMP/captacion/deploy/instancia.env.example" "$DESTINO/"
printf '%s\n' "$VERSION" > "$DESTINO/VERSION"
chmod -R a+rX "$DESTINO"
echo "   ✓"

paso "Servicios de systemd"
install -m 644 "$TMP"/captacion/deploy/*.service "$TMP"/captacion/deploy/*.timer "$DIR_UNIDADES/"
systemctl daemon-reload
echo "   ✓"

paso "Configuración ($DIR_CONFIG/$INSTANCIA.env)"
ENV="$DIR_CONFIG/$INSTANCIA.env"
install -d -m 700 "$DIR_CONFIG"
if [ ! -f "$ENV" ]; then
    (umask 077 && cp "$TMP/captacion/deploy/instancia.env.example" "$ENV")
    echo "   archivo creado"
fi
chown root:root "$ENV"
chmod 600 "$ENV"
valor_de() { sed -n "s/^$1=//p" "$ENV" | tail -n 1; }
# CAPTACION_SIN_TERMINAL=1 fuerza el modo sin terminal (para que una
# sesión de Claude nunca se quede esperando a que alguien escriba).
hay_terminal() {
    [ -z "${CAPTACION_SIN_TERMINAL:-}" ] && { [ -t 0 ] || { : < /dev/tty; } 2>/dev/null; }
}

if [ -z "$(valor_de CAPTACION_PERFIL)" ]; then
    CAPTACION_NO_REINICIAR=1 bash "$DESTINO/configurar.sh" "$INSTANCIA" perfil Dronwhite >/dev/null
    echo "   perfil de los botones: @Dronwhite ✓"
fi
if [ -n "$(valor_de CAPTACION_BOT_TOKEN)" ]; then
    echo "   token ya puesto ✓"
elif ! hay_terminal; then
    # P. ej. lo está ejecutando una sesión de Claude: no puede pedir el
    # token, y tampoco debe verlo. Se para aquí, sin arrancar nada.
    echo
    echo "⏸️  Instalado a falta del token del bot (aquí no hay terminal para pedirlo)."
    echo "   El dueño lo pega desde SU terminal SSH (nunca en un chat):"
    echo "     bash $DESTINO/configurar.sh $INSTANCIA token"
    echo "   y después se vuelve a ejecutar:"
    echo "     bash $DESTINO/instalar.sh $INSTANCIA"
    exit 3
else
    echo "   Falta el token del bot: cópialo del chat con @BotFather."
    CAPTACION_NO_REINICIAR=1 bash "$DESTINO/configurar.sh" "$INSTANCIA" token \
        || fallo "Sin token no se puede arrancar. Cuando lo tengas: bash $DESTINO/configurar.sh $INSTANCIA token  y después repite este instalador."
fi

# El entorno de Python (Sheet y lector) es opcional: si algo de esto falla,
# el bot se instala y funciona igual; solo quedan sin activar esas partes.
paso "Entorno de Python (Google Sheet y lector de la cuenta) y credencial de Google"
VENV_OK=1
if [ ! -x "$DESTINO/venv/bin/python" ]; then
    if "$PY" -m venv "$DESTINO/venv" >/dev/null 2>&1; then
        echo "   entorno de Python creado en $DESTINO/venv"
    else
        rm -rf "$DESTINO/venv"
        echo "   ⚠️  No se pudo crear el entorno de Python (suele faltar el paquete python3-venv)."
        VENV_OK=0
    fi
fi
if [ "$VENV_OK" = 1 ]; then
    if "$DESTINO/venv/bin/python" -m pip install --quiet --disable-pip-version-check \
            "gspread==$VERSION_GSPREAD" "telethon==$VERSION_TELETHON"; then
        chmod -R a+rX "$DESTINO/venv"
        echo "   gspread $VERSION_GSPREAD y telethon $VERSION_TELETHON ✓"
    else
        echo "   ⚠️  No se pudieron instalar gspread y telethon."
        VENV_OK=0
    fi
fi
SHEET_OK=$VENV_OK
if [ -f "$ORIGEN_GOOGLE" ]; then
    # Copia solo para root; systemd se la pasa al servicio (LoadCredential).
    install -m 600 -o root -g root "$ORIGEN_GOOGLE" "$DIR_CONFIG/google.json"
    echo "   credencial de Google (cuenta de servicio de picks) ✓"
elif [ -f "$DIR_CONFIG/google.json" ]; then
    echo "   credencial de Google ya puesta ✓"
else
    echo "   ⚠️  No encuentro la credencial de Google ($ORIGEN_GOOGLE)."
    SHEET_OK=0
fi
VERSION_SYSTEMD=$(systemctl --version 2>/dev/null | awk 'NR == 1 {print $2}')
if ! [ "${VERSION_SYSTEMD:-0}" -ge 247 ] 2>/dev/null; then
    echo "   ⚠️  systemd ${VERSION_SYSTEMD:-?} no sabe pasar credenciales a un servicio (hace falta la 247 o superior)."
    SHEET_OK=0
fi

paso "Arrancando el bot y los resúmenes"
systemctl enable --quiet "captacion-bot@$INSTANCIA"
systemctl restart "captacion-bot@$INSTANCIA"
systemctl enable --quiet --now "captacion-resumen-diario@$INSTANCIA.timer" "captacion-resumen-semanal@$INSTANCIA.timer"
if [ "$SHEET_OK" = 1 ]; then
    systemctl enable --quiet --now "captacion-sheet@$INSTANCIA.timer"
else
    echo "   ⚠️  La copia al Google Sheet queda sin activar; el bot funciona igual."
fi
if [ "$VENV_OK" = 1 ] && systemctl is-enabled --quiet "captacion-lector@$INSTANCIA" 2>/dev/null; then
    systemctl restart "captacion-lector@$INSTANCIA"
    echo "   lector de carpetas reiniciado con el código nuevo ✓"
fi
sleep 4
if ! systemctl is-active --quiet "captacion-bot@$INSTANCIA"; then
    echo "❌ El bot no ha arrancado. Últimas líneas del registro:" >&2
    journalctl -u "captacion-bot@$INSTANCIA" -n 20 --no-pager >&2 || true
    exit 1
fi
journalctl -u "captacion-bot@$INSTANCIA" -n 4 --no-pager -o cat || true

if [ "$SHEET_OK" = 1 ] && [ -n "$(valor_de CAPTACION_SHEET_ID)" ]; then
    if systemctl start "captacion-sheet@$INSTANCIA.service"; then
        echo "   copia al Google Sheet hecha ✓"
    else
        echo "   ⚠️  La copia al Google Sheet ha fallado (se reintenta cada 10 min). Registro:"
        journalctl -u "captacion-sheet@$INSTANCIA" -n 5 --no-pager -o cat || true
    fi
fi

echo
echo "✅ Bot «$INSTANCIA» instalado y funcionando (versión $VERSION)."
bash "$DESTINO/configurar.sh" "$INSTANCIA" ver
if [ -z "$(valor_de CAPTACION_PROPIETARIO_ID)" ]; then
    echo
    echo "Siguiente: abre el bot con tu cuenta principal y escríbele /miid. Te dirá tu id;"
    echo "después: bash $DESTINO/configurar.sh $INSTANCIA propietario <tu id>"
fi
if [ "$SHEET_OK" = 1 ] && [ -z "$(valor_de CAPTACION_SHEET_ID)" ]; then
    CORREO=$("$PY" -c 'import json, sys; print(json.load(open(sys.argv[1]))["client_email"])' "$DIR_CONFIG/google.json" 2>/dev/null || echo "?")
    echo
    echo "Para activar la copia al Google Sheet: compártelo como editor con"
    echo "  $CORREO"
    echo "y después: bash $DESTINO/configurar.sh $INSTANCIA sheet <enlace del Sheet>"
fi
