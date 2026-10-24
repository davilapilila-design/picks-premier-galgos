# Reglas para IAs trabajando en `captacion/`

Subsistema de captación (bot de bienvenida + organización de chats). Ver
`PLAN.md` en esta carpeta para decisiones y fases. Además de las reglas del
`CLAUDE.md` raíz (español de España, nunca commitear secrets, bitácora):

- **Solo esta carpeta y la rama `captacion-bienvenida`**. No tocar `src/`
  ni nada del sistema de picks.
- **Nada de producción sin el visto bueno explícito del dueño**: ni el canal
  real PREMIER GALGOS, ni el bot real, ni su cuenta personal de Telegram.
  Todo se prueba antes en el canal de prueba con el bot de prueba y la
  cuenta secundaria.
- **Nunca enviar mensajes desde la cuenta personal del dueño.** El programa
  que usa su cuenta (Telethon, fases 3-6) solo lee y organiza carpetas; no
  debe tener ninguna función de enviar, y no marca chats como leídos. Lo
  garantiza la lista blanca de `premier_captacion/guardia.py`: no se amplía
  sin el visto bueno explícito del dueño, y nunca con nada que envíe,
  marque como leído, se una o salga de chats.
- El lector arranca siempre en **simulación**; pasarlo a real
  (`configurar.sh <instancia> lector real`) es decisión del dueño. En
  simulación el candado usa el modo `simulacion`, que no deja pedir cambios
  de carpetas.
- La fase 3 se prueba con la **cuenta principal del dueño conectada a la
  instancia `prueba`** (decisión suya del 2026-10-15). Por eso, en `prueba`:
  nunca pasar el lector a real (borraría de verdad sus carpetas de días) ni
  ejecutar el histórico (metería a sus clientes reales en la memoria de
  prueba).
- Una sesión de Telethon no se usa desde dos programas a la vez (Telegram
  la anula): `lector.sh`, `conectar-cuenta.sh` y `leer-historico.sh` paran
  antes el servicio. Iniciar sesión lo hace SIEMPRE el dueño en su terminal
  (el código de Telegram nunca pasa por un chat).
- **Secrets** (token del bot, api_id/api_hash, sesión de Telethon) solo en
  la VM: `/etc/premier-captacion/*.env` y el directorio de estado
  `/var/lib/premier-captacion/`. Nunca en el repo ni en el chat.
- **El repositorio es público**: tampoco van aquí enlaces de invitación
  (de prueba ni de los canales de venta), ids de Telegram reales, ids de
  Sheets ni datos de clientes. En los tests, valores inventados.
- En la VM se instala/actualiza con `deploy/instalar.sh <prueba|real>` y se
  configura con `deploy/configurar.sh` (ver README.md). El dueño no es
  técnico: darle siempre comandos completos para copiar y pegar.
- La bienvenida se envía **siempre antes** de aceptar la solicitud (después
  Telegram ya no deja escribir a esa persona).
- El bot tiene **modo simulación** (`CAPTACION_BOT_SIMULAR=1`, por defecto en la
  instancia real): ni escribe a clientes ni acepta solicitudes; solo avisa al
  dueño. Cualquier cambio que haga hablar o aceptar al bot tiene que respetarlo.
  Única excepción: las cuentas de prueba que apunta el dueño con `/probador`
  reciben respuesta si escriben al bot o pulsan las dudas (sus solicitudes
  siguen simuladas).
- El bot tiene **freno de emergencia** (`/pausar` = simulación / `/arrancar`, solo el
  dueño; estado `pausa_desde` en la base de datos): cualquier cambio en la
  gestión de solicitudes tiene que respetarlo.
- Los textos con "negrita" son letras Unicode: generarlos con
  `mensajes.negrita()` y comprobarlos contra el original
  (`tests/test_mensajes.py`). Cambiar un texto de bienvenida = tipo de
  mensaje nuevo en `TIPOS_MENSAJE`, nunca reutilizar un id.
- El dueño cambia textos desde el bot (`/textos`): los de `mensajes.py`
  son solo los de partida, y vale lo último guardado en la tabla `textos`
  (ver `textos.py`). Al leer un texto en el bot, usar siempre
  `textos.actual()`, nunca la constante. Las bienvenidas que crea él
  reciben su tipo solas (bot_b_v2…). Los botones de la bienvenida y sus
  frases no se exponen a `/textos`: de ellas depende saber qué eligió cada
  persona.
- Quien ya estaba en el canal (`miembros_canal`) o ya pasó por aquí
  recibe la bienvenida sin gratuita (`db.ya_conocido`, `db.estado_oferta`):
  no debe notarse que es otro mensaje; lo distingue el texto ya escrito
  («consulta» en vez de «duda»).
- El bot (fase 1) usa solo la librería estándar; el Sheet (gspread 6.1.4) y
  el lector (Telethon 1.45.0) usan el venv `/opt/premier-captacion/venv`.
  Compatible con Python 3.9+. Tests: `cd captacion && python3 -m unittest
  discover -s tests -t .` (los de `test_*_real.py` se saltan si no están
  gspread/Telethon; conviene pasarlos también con un venv que los tenga).
