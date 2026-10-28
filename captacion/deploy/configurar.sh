#!/usr/bin/env bash
# Cambia un dato de la configuración de una instancia del bot y lo reinicia.
# Se ejecuta en la VM como root:
#
#   bash /opt/premier-captacion/configurar.sh prueba token             (lo pide; no se ve al pegarlo)
#   bash /opt/premier-captacion/configurar.sh prueba perfil Dronwhite
#   bash /opt/premier-captacion/configurar.sh prueba propietario 123456789
#   bash /opt/premier-captacion/configurar.sh prueba canal -1001234567890
#   bash /opt/premier-captacion/configurar.sh prueba sheet <enlace o id del Google Sheet>
#   bash /opt/premier-captacion/configurar.sh prueba api               (api_id y api_hash de my.telegram.org; los pide)
#   bash /opt/premier-captacion/configurar.sh real api-de prueba       (copia el api_id y el api_hash de la otra instancia)
#   bash /opt/premier-captacion/configurar.sh prueba lector simulacion (el lector de carpetas solo avisa)
#   bash /opt/premier-captacion/configurar.sh prueba lector real       (el lector de carpetas actúa)
#   bash /opt/premier-captacion/configurar.sh real bot simulacion      (el bot no escribe ni acepta: solo cuenta lo que haría)
#   bash /opt/premier-captacion/configurar.sh real bot real            (el bot da la bienvenida y acepta)
#   bash /opt/premier-captacion/configurar.sh real bienvenidas-manuales si  (el lector apunta las bienvenidas que das a mano; solo real)
#   bash /opt/premier-captacion/configurar.sh real excluir-ventas "@uno,@dos"  (no cuentan en «Canales de venta»: los del equipo)
#   bash /opt/premier-captacion/configurar.sh prueba ver               (muestra todo menos los secretos)
#
# Por seguridad el token y el api_hash NUNCA se escriben en la línea de
# comandos (quedarían en el historial de la terminal): se pegan cuando los pide.
#
# Al cambiar el Sheet no se reinicia el bot: se hace una copia al Sheet en
# ese momento. Con CAPTACION_NO_REINICIAR=1 solo guarda, sin reiniciar nada
# (lo usa instalar.sh).
set -euo pipefail

DIR_CONFIG=/etc/premier-captacion

fallo() { echo "❌ $*" >&2; exit 1; }

uso() {
    # Muestra el comentario del principio de este archivo.
    awk 'NR > 1 && /^#/ { sub(/^# ?/, ""); print; next } NR > 1 { exit }' "$0" >&2
    exit 1
}

# poner ARCHIVO CLAVE VALOR: sustituye la línea CLAVE=... o la añade al
# final. Solo usa órdenes internas de bash para escribir, así el valor (el
# token) nunca aparece en la lista de procesos.
poner() {
    local archivo=$1 clave=$2 valor=$3 tmp linea hecho=0
    tmp=$(mktemp "$archivo.XXXXXX")  # mismo directorio, permisos 600
    while IFS= read -r linea || [ -n "$linea" ]; do
        if [[ "$linea" == "$clave="* ]]; then
            printf '%s=%s\n' "$clave" "$valor"
            hecho=1
        else
            printf '%s\n' "$linea"
        fi
    done < "$archivo" > "$tmp"
    if [ "$hecho" = 0 ]; then
        printf '%s=%s\n' "$clave" "$valor" >> "$tmp"
    fi
    chmod 600 "$tmp"
    mv "$tmp" "$archivo"
}

# leer_oculto VARIABLE MENSAJE [visible]: lee sin mostrar lo que se escribe
# (con un tercer argumento, mostrándolo).
leer_oculto() {
    local __var=$1 __msg=$2 __valor="" __oculto=1
    local -a __opciones=(-r -s)
    if [ -n "${3:-}" ]; then
        __oculto=0
        __opciones=(-r)
    fi
    if [ -t 0 ]; then
        read "${__opciones[@]}" -p "$__msg" __valor
        [ "$__oculto" = 0 ] || echo
    elif { : < /dev/tty; } 2>/dev/null; then
        read "${__opciones[@]}" -p "$__msg" __valor < /dev/tty
        [ "$__oculto" = 0 ] || echo
    else
        # Sin terminal (p. ej. el valor llega por una tubería).
        read -r __valor || true
    fi
    # Al pegar a veces se cuelan espacios o un retorno de carro.
    __valor=${__valor//[[:space:]]/}
    printf -v "$__var" '%s' "$__valor"
}

[ "$(id -u)" -eq 0 ] || fallo "Hay que ejecutarlo como root (pon sudo delante)."

INSTANCIA="${1:-}"
DATO="${2:-}"
VALOR="${3:-}"
case "$INSTANCIA" in prueba|real) ;; *) uso ;; esac
ENV="$DIR_CONFIG/$INSTANCIA.env"
[ -f "$ENV" ] || fallo "No existe $ENV: primero hay que instalar (instalar.sh $INSTANCIA)."

case "$DATO" in
    token)
        CLAVE=CAPTACION_BOT_TOKEN
        PATRON='^[0-9]+:[A-Za-z0-9_-]{30,}$'
        [ -z "$VALOR" ] || fallo "Por seguridad el token no se escribe en el comando. Ejecuta: bash $0 $INSTANCIA token  (y pégalo cuando lo pida)"
        ;;
    excluir-ventas)
        # Los del equipo, que no cuentan en las estadísticas de los canales
        # de venta (no van al repositorio: es público).
        CLAVE=CAPTACION_EXCLUIR_VENTAS
        VALOR=${VALOR//[[:space:]]/}
        PATRON='^(@?[A-Za-z0-9_]{4,32}(,@?[A-Za-z0-9_]{4,32})*)?$'
        ;;
    perfil)
        CLAVE=CAPTACION_PERFIL
        VALOR="${VALOR#@}"
        PATRON='^[A-Za-z][A-Za-z0-9_]{3,31}$'
        ;;
    propietario)
        CLAVE=CAPTACION_PROPIETARIO_ID
        PATRON='^[0-9]+$'
        ;;
    canal)
        CLAVE=CAPTACION_CANAL_ID
        PATRON='^-100[0-9]+$'
        ;;
    sheet)
        CLAVE=CAPTACION_SHEET_ID
        # Vale pegar el enlace entero del Sheet: se queda con el id.
        if [[ "$VALOR" =~ /d/([A-Za-z0-9_-]+) ]]; then
            VALOR=${BASH_REMATCH[1]}
        fi
        PATRON='^[A-Za-z0-9_-]{30,100}$'
        ;;
    api)
        # De my.telegram.org → «API development tools». El api_hash es secreto.
        [ -z "$VALOR" ] || fallo "Por seguridad no se escriben en el comando: ejecuta bash $0 $INSTANCIA api"
        leer_oculto API_ID "api_id (el número de my.telegram.org): " visible
        [[ "$API_ID" =~ ^[0-9]{3,12}$ ]] || fallo "Eso no parece un api_id (es un número)."
        leer_oculto API_HASH "api_hash (no se verá al pegarlo): "
        [[ "$API_HASH" =~ ^[0-9a-f]{32}$ ]] || fallo "Eso no parece un api_hash (32 letras y números)."
        poner "$ENV" CAPTACION_API_ID "$API_ID"
        poner "$ENV" CAPTACION_API_HASH "$API_HASH"
        echo "✓ api_id y api_hash guardados"
        exit 0
        ;;
    api-de)
        # Copia el api_id y el api_hash de la otra instancia: la misma
        # aplicación de my.telegram.org vale para las dos. Solo con órdenes
        # internas de bash (el api_hash no aparece en la lista de procesos).
        case "$VALOR" in prueba|real) ;; *) fallo "Uso: bash $0 $INSTANCIA api-de <prueba|real>" ;; esac
        [ "$VALOR" != "$INSTANCIA" ] || fallo "Tiene que ser la otra instancia."
        ORIGEN="$DIR_CONFIG/$VALOR.env"
        [ -f "$ORIGEN" ] || fallo "No existe $ORIGEN."
        API_ID=""
        API_HASH=""
        while IFS= read -r linea || [ -n "$linea" ]; do
            case "$linea" in
                CAPTACION_API_ID=*) API_ID=${linea#*=} ;;
                CAPTACION_API_HASH=*) API_HASH=${linea#*=} ;;
            esac
        done < "$ORIGEN"
        [[ "$API_ID" =~ ^[0-9]{3,12}$ && "$API_HASH" =~ ^[0-9a-f]{32}$ ]] \
            || fallo "En «$VALOR» no hay un api_id y un api_hash válidos."
        poner "$ENV" CAPTACION_API_ID "$API_ID"
        poner "$ENV" CAPTACION_API_HASH "$API_HASH"
        echo "✓ api_id y api_hash copiados de «$VALOR»"
        exit 0
        ;;
    lector)
        case "$VALOR" in
            real) poner "$ENV" CAPTACION_LECTOR_SIMULAR 0 ;;
            simulacion) poner "$ENV" CAPTACION_LECTOR_SIMULAR 1 ;;
            *) fallo "Uso: bash $0 $INSTANCIA lector <simulacion|real>" ;;
        esac
        echo "✓ lector de carpetas en modo $VALOR"
        if [ -z "${CAPTACION_NO_REINICIAR:-}" ] && systemctl is-enabled --quiet "captacion-lector@$INSTANCIA" 2>/dev/null; then
            systemctl restart "captacion-lector@$INSTANCIA"
            echo "✓ lector reiniciado"
        fi
        exit 0
        ;;
    bot)
        case "$VALOR" in
            simulacion) poner "$ENV" CAPTACION_BOT_SIMULAR 1 ;;
            real) poner "$ENV" CAPTACION_BOT_SIMULAR 0 ;;
            *) fallo "Uso: bash $0 $INSTANCIA bot <simulacion|real>" ;;
        esac
        echo "✓ bot en modo $VALOR"
        if [ -z "${CAPTACION_NO_REINICIAR:-}" ] && systemctl is-enabled --quiet "captacion-bot@$INSTANCIA" 2>/dev/null; then
            systemctl restart "captacion-bot@$INSTANCIA"
            echo "✓ bot reiniciado"
        fi
        exit 0
        ;;
    bienvenidas-manuales)
        case "$VALOR" in
            si) [ "$INSTANCIA" = real ] || fallo "Solo en la instancia real: en la de prueba tus clientes reales se ignoran."
                poner "$ENV" CAPTACION_BIENVENIDAS_MANUALES 1 ;;
            no) poner "$ENV" CAPTACION_BIENVENIDAS_MANUALES 0 ;;
            *) fallo "Uso: bash $0 $INSTANCIA bienvenidas-manuales <si|no>" ;;
        esac
        echo "✓ bienvenidas a mano: $VALOR"
        if [ -z "${CAPTACION_NO_REINICIAR:-}" ] && systemctl is-enabled --quiet "captacion-lector@$INSTANCIA" 2>/dev/null; then
            systemctl restart "captacion-lector@$INSTANCIA"
            echo "✓ lector reiniciado"
        fi
        exit 0
        ;;
    ver)
        echo "Configuración de $INSTANCIA ($ENV):"
        while IFS= read -r linea || [ -n "$linea" ]; do
            case "$linea" in
                CAPTACION_BOT_TOKEN=?*) echo "  CAPTACION_BOT_TOKEN=*** (puesto)" ;;
                CAPTACION_API_HASH=?*) echo "  CAPTACION_API_HASH=*** (puesto)" ;;
                \#*|"") ;;
                *=) echo "  $linea(vacío)" ;;
                *) echo "  $linea" ;;
            esac
        done < "$ENV"
        exit 0
        ;;
    *) uso ;;
esac

if [ "$DATO" = token ]; then
    for _ in 1 2 3; do
        leer_oculto VALOR "Pega el token del bot y pulsa Enter (no se verá al pegarlo): "
        [[ "$VALOR" =~ $PATRON ]] && break
        echo "   Eso no parece un token (debe ser como 123456789:AAH...). Prueba otra vez." >&2
        VALOR=""
    done
fi
[[ "$VALOR" =~ $PATRON ]] || fallo "Valor no válido para «$DATO»."

poner "$ENV" "$CLAVE" "$VALOR"
echo "✓ $DATO guardado"

if [ "$DATO" = sheet ]; then
    [ -z "${CAPTACION_NO_REINICIAR:-}" ] || exit 0
    if ! systemctl is-enabled --quiet "captacion-sheet@$INSTANCIA.timer" 2>/dev/null; then
        echo "   (la copia al Sheet aún no está activada: la activa instalar.sh)"
        exit 0
    fi
    echo "   Copiando al Sheet ahora (puede tardar unos segundos)..."
    if systemctl start "captacion-sheet@$INSTANCIA.service"; then
        journalctl -u "captacion-sheet@$INSTANCIA" -n 1 --no-pager -o cat || true
        echo "✓ Sheet actualizado"
    else
        echo "❌ No se ha podido copiar al Sheet. Últimas líneas del registro:" >&2
        journalctl -u "captacion-sheet@$INSTANCIA" -n 15 --no-pager >&2 || true
        exit 1
    fi
    exit 0
fi

if [ -z "${CAPTACION_NO_REINICIAR:-}" ] && systemctl is-enabled --quiet "captacion-bot@$INSTANCIA" 2>/dev/null; then
    systemctl restart "captacion-bot@$INSTANCIA"
    sleep 3
    if systemctl is-active --quiet "captacion-bot@$INSTANCIA"; then
        echo "✓ Bot reiniciado y funcionando"
    else
        echo "❌ El bot no ha arrancado. Últimas líneas del registro:" >&2
        journalctl -u "captacion-bot@$INSTANCIA" -n 15 --no-pager >&2 || true
        exit 1
    fi
fi
