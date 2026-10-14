# Captación PREMIER GALGOS

Bot que da la bienvenida y acepta automáticamente a quien solicita entrar
en el canal, y (fases siguientes) organiza los chats del dueño. Decisiones y
fases: [`PLAN.md`](PLAN.md).

## Estructura
```
captacion/
├── premier_captacion/      código (solo librería estándar de Python 3.9+)
│   ├── bot.py              el bot: solicitudes, mensajes, avisos, comandos
│   ├── mensajes.py         textos de bienvenida y botones
│   ├── resumen.py          resúmenes diario y semanal
│   ├── db.py               base de datos local (SQLite)
│   ├── config.py           configuración (variables de entorno)
│   └── telegram_api.py     cliente mínimo de la Bot API
├── tests/                  pruebas automáticas (sin red)
└── deploy/                 servicios systemd y plantilla de configuración
```

## Pruebas automáticas
```bash
cd captacion
python3 -m unittest discover -s tests -t .
```

---

## Fase 1: puesta en marcha en el canal de PRUEBA

En la prueba los papeles se cambian para no tocar tu cuenta real: la
**cuenta secundaria hace de "tú"** (dueña del canal de prueba, recibe los
avisos, los botones llevan a ella) y **tu cuenta real hace de "cliente"**.

### Paso 1. Bot de prueba con @BotFather (desde tu cuenta real) ✅
`/newbot` → nombre `PREMIER GALGOS (pruebas)` → @ `premiergalgos_pruebas_bot`.
El **token** que da BotFather no se copia a ningún sitio: se queda en ese
chat y solo se usa en el paso 4. Si se escapa, `/revoke` en BotFather.

### Paso 2. @usuario de la cuenta secundaria
Ajustes → Nombre de usuario (en iPhone: Ajustes → Editar → Nombre de
usuario). Mínimo 5 caracteres; mejor uno que no se parezca a la marca, para
que nadie lo confunda con el canal.

### Paso 3. Canal de prueba (con la cuenta secundaria)
Crea un canal **privado** (p. ej. "Prueba captación"). Dentro: Administrar
canal → Enlaces de invitación → Crear enlace → nombre `prueba-1` y
**«Solicitar aprobación de administrador»** activado. Todavía no añadas el
bot (eso es el paso 6).

### Paso 4. Instalar el bot en la VM (por SSH)
1. Comprueba Python (vale 3.9 o superior):
   ```bash
   python3 --version
   ```
2. Usuario de sistema sin privilegios para el bot:
   ```bash
   sudo useradd --system --no-create-home --shell /usr/sbin/nologin captacion
   ```
3. Copia el código. Desde tu ordenador, con el repo en la rama
   `captacion-bienvenida`:
   ```bash
   scp -r captacion root@galgos-vm.tailc02685.ts.net:/tmp/
   ```
   y en la VM:
   ```bash
   sudo mkdir -p /opt/premier-captacion
   sudo cp -r /tmp/captacion/premier_captacion /opt/premier-captacion/
   sudo cp /tmp/captacion/deploy/*.service /tmp/captacion/deploy/*.timer /etc/systemd/system/
   sudo systemctl daemon-reload
   ```
4. Configuración (aquí va el token; solo la puede leer root):
   ```bash
   sudo mkdir -p /etc/premier-captacion
   sudo chmod 700 /etc/premier-captacion
   sudo install -m 600 /tmp/captacion/deploy/instancia.env.example /etc/premier-captacion/prueba.env
   sudo nano /etc/premier-captacion/prueba.env
   ```
   Rellena **solo** `CAPTACION_BOT_TOKEN` y `CAPTACION_PERFIL` (el
   @usuario de la cuenta secundaria, sin la @). Deja los otros dos vacíos.
5. Arranca el bot y mira el log:
   ```bash
   sudo systemctl enable --now captacion-bot@prueba
   journalctl -u captacion-bot@prueba -f
   ```
   Debe salir `Bot @… arrancando`. (Ctrl+C para salir del log; el bot sigue.)

### Paso 5. Decirle al bot quién eres
Con la **cuenta secundaria**, abre `@premiergalgos_pruebas_bot` y pulsa
**«Iniciar»**. Contesta «🛠️ Bot en puesta en marcha. Tu id de Telegram es:
…». Pon ese número en `CAPTACION_PROPIETARIO_ID` y reinicia:
```bash
sudo nano /etc/premier-captacion/prueba.env
sudo systemctl restart captacion-bot@prueba
```
Escribe `/start` otra vez: ahora contesta «✅ Bot de captación activo».

### Paso 6. Hacer administrador al bot en el canal de prueba
Con la cuenta secundaria: canal de prueba → Administrar canal →
Administradores → Añadir administrador → busca `premiergalgos_pruebas_bot`
→ deja activado **solo «Añadir suscriptores»** → Guardar. El bot te escribe
el id del canal (`CAPTACION_CANAL_ID=-100…`). Ponlo en el `.env` y reinicia
como en el paso 5. Después escribe `/estado` al bot: debe decir el canal y
`Botones apuntan a: @<secundaria>`.

### Paso 7. Activar los resúmenes
```bash
sudo systemctl enable --now captacion-resumen-diario@prueba.timer captacion-resumen-semanal@prueba.timer
systemctl list-timers 'captacion-*'
```

### Paso 8. Lista de pruebas (tu cuenta real hace de cliente)
- [ ] **Bienvenida**: abre el enlace `prueba-1` y pide unirte. En segundos
      llega el mensaje del bot con los dos botones, y te acepta. Comprueba
      las negritas y los emojis.
- [ ] **Botones**: pulsa «🏁 Ya he apostado»: se abre el chat con la cuenta
      secundaria con el texto ya escrito. Igual con «🆕 Es mi primera vez».
      Pruébalo en el móvil y, si puedes, en Telegram de ordenador. (No
      hace falta enviarlo.)
- [ ] **Escribir al bot**: escríbele "hola": responde «Por aquí no puedo
      contestarte…» con los botones. Envía 3 mensajes seguidos: una sola
      respuesta. Espera más de un minuto y escribe otra vez: vuelve a
      responder.
- [ ] **Volver a entrar**: sal del canal y vuelve a pedir unirte: te acepta
      **sin** enviarte nada.
- [ ] **Comandos** (desde la secundaria): `/resumen`, `/semana`, `/estado`.
- [ ] **Resumen programado ya**: `sudo systemctl start captacion-resumen-diario@prueba`
      (envía el de ayer, que estará vacío: sirve para ver que llega).
- [ ] **Permisos**: quita al bot de administrador → te avisa con 🚨. Vuelve
      a ponerlo (solo «Añadir suscriptores») → te avisa con ✅.
- [ ] **Bot parado más de 5 min** (opcional). Para repetir pruebas desde
      cero hay que borrar la memoria de la prueba:
      ```bash
      sudo systemctl stop captacion-bot@prueba
      sudo rm -f /var/lib/premier-captacion/prueba.db*
      ```
      Con el bot parado: sal del canal, pide unirte, espera 6 minutos y
      arranca el bot (`sudo systemctl start captacion-bot@prueba`). Te
      acepta sin bienvenida y te avisa de «1 solicitud(es) llevaban más de 5
      minutos esperando».

### Cosas útiles
```bash
systemctl status captacion-bot@prueba        # ¿está funcionando?
journalctl -u captacion-bot@prueba --since today
sudo systemctl restart captacion-bot@prueba  # tras cambiar el .env o el código
```
Para actualizar el código: repetir el punto 3 del paso 4 y reiniciar.

---

## Paso a producción (fase 5) — SOLO con el visto bueno del dueño
Igual que la prueba pero con la instancia `real`:
`/etc/premier-captacion/real.env` con el token del bot real
(PREMIER GALGOS + logo), `CAPTACION_PERFIL=Dronwhite` y tu id real, y los
servicios `captacion-bot@real` y los timers `@real`. Antes de activarlo:
ponles nombre a los enlaces de entrada del canal, y acepta a mano las
solicitudes que haya pendientes en ese momento. El detalle se preparará
cuando toque.
