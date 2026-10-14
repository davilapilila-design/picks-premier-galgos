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
  debe tener ninguna función de enviar, y no marca chats como leídos.
- **Secrets** (token del bot, api_id/api_hash, sesión de Telethon) solo en
  la VM: `/etc/premier-captacion/*.env` y el directorio de estado
  `/var/lib/premier-captacion/`. Nunca en el repo ni en el chat.
- **El repositorio es público**: tampoco van aquí enlaces de invitación de
  canales de prueba ni datos de clientes.
- En la VM se instala/actualiza con `deploy/instalar.sh <prueba|real>` y se
  configura con `deploy/configurar.sh` (ver README.md). El dueño no es
  técnico: darle siempre comandos completos para copiar y pegar.
- La bienvenida se envía **siempre antes** de aceptar la solicitud (después
  Telegram ya no deja escribir a esa persona).
- Los textos con "negrita" son letras Unicode: generarlos con
  `mensajes.negrita()` y comprobarlos contra el original
  (`tests/test_mensajes.py`). Cambiar un texto de bienvenida = tipo de
  mensaje nuevo en `TIPOS_MENSAJE`, nunca reutilizar un id.
- Python solo con librería estándar en el bot (fase 1); compatible con
  Python 3.9+. Tests: `cd captacion && python3 -m unittest discover -s tests -t .`
