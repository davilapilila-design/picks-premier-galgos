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
# Se puede repetir sin miedo. Pasos:
#   1. Comprueba Python 3.9+ y las zonas horarias.
#   2. Crea el usuario de sistema "captacion" (sin privilegios) si no existe.
#   3. Descarga el código de GitHub (rama captacion-bienvenida, o la que
#      diga CAPTACION_RAMA) y lo deja en /opt/premier-captacion.
#   4. Instala los servicios de systemd.
#   5. Crea /etc/premier-captacion/<instancia>.env (solo root) si no existe,
#      pide el token si falta (no se ve al pegarlo) y pone el perfil
#      Dronwhite si está vacío. Los datos que ya haya no se tocan.
#   6. Arranca (o reinicia) el bot y activa los resúmenes.
set -euo pipefail

REPO=davilapilila-design/picks-premier-galgos
RAMA="${CAPTACION_RAMA:-captacion-bienvenida}"
DESTINO=/opt/premier-captacion
DIR_CONFIG=/etc/premier-captacion
DIR_UNIDADES=/etc/systemd/system
PY=/usr/bin/python3

fallo() { echo "❌ $*" >&2; exit 1; }
paso() { echo; echo "▶ $*"; }

[ "$(id -u)" -eq 0 ] || fallo "Hay que ejecutarlo como root (pon sudo delante)."
INSTANCIA="${1:-}"
case "$INSTANCIA" in
    prueba) ;;
    real)
        echo "⚠️  Vas a instalar el bot REAL, el del canal PREMIER GALGOS."
        read -r -p "   Escribe SI para continuar: " confirmacion
        [ "$confirmacion" = "SI" ] || fallo "Cancelado."
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

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
if [ -n "${CAPTACION_ORIGEN:-}" ]; then
    # Solo para pruebas: copia de una carpeta local en vez de descargar.
    paso "Copiando el código de $CAPTACION_ORIGEN"
    cp -r "$CAPTACION_ORIGEN/captacion" "$TMP/captacion"
    VERSION="local $(date '+%Y-%m-%d %H:%M')"
else
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

paso "Instalando en $DESTINO"
install -d -m 755 "$DESTINO"
rm -rf "$DESTINO/premier_captacion.nuevo"
cp -r "$TMP/captacion/premier_captacion" "$DESTINO/premier_captacion.nuevo"
rm -rf "$DESTINO/premier_captacion"
mv "$DESTINO/premier_captacion.nuevo" "$DESTINO/premier_captacion"
install -m 755 "$TMP/captacion/deploy/instalar.sh" "$TMP/captacion/deploy/configurar.sh" "$DESTINO/"
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

if [ -z "$(valor_de CAPTACION_BOT_TOKEN)" ]; then
    echo "   Falta el token del bot: cópialo del chat con @BotFather."
    CAPTACION_NO_REINICIAR=1 bash "$DESTINO/configurar.sh" "$INSTANCIA" token \
        || fallo "Sin token no se puede arrancar. Cuando lo tengas: bash $DESTINO/configurar.sh $INSTANCIA token  y después repite este instalador."
else
    echo "   token ya puesto ✓"
fi
if [ -z "$(valor_de CAPTACION_PERFIL)" ]; then
    CAPTACION_NO_REINICIAR=1 bash "$DESTINO/configurar.sh" "$INSTANCIA" perfil Dronwhite >/dev/null
    echo "   perfil de los botones: @Dronwhite ✓"
fi

paso "Arrancando el bot y los resúmenes"
systemctl enable --quiet "captacion-bot@$INSTANCIA"
systemctl restart "captacion-bot@$INSTANCIA"
systemctl enable --quiet --now "captacion-resumen-diario@$INSTANCIA.timer" "captacion-resumen-semanal@$INSTANCIA.timer"
sleep 4
if ! systemctl is-active --quiet "captacion-bot@$INSTANCIA"; then
    echo "❌ El bot no ha arrancado. Últimas líneas del registro:" >&2
    journalctl -u "captacion-bot@$INSTANCIA" -n 20 --no-pager >&2 || true
    exit 1
fi
journalctl -u "captacion-bot@$INSTANCIA" -n 4 --no-pager -o cat || true

echo
echo "✅ Bot «$INSTANCIA» instalado y funcionando (versión $VERSION)."
bash "$DESTINO/configurar.sh" "$INSTANCIA" ver
if [ -z "$(valor_de CAPTACION_PROPIETARIO_ID)" ]; then
    echo
    echo "Siguiente: abre el bot con tu cuenta principal y pulsa «Iniciar». Te dirá tu id;"
    echo "después: bash $DESTINO/configurar.sh $INSTANCIA propietario <tu id>"
fi
