# Captación PREMIER GALGOS

Bot que da la bienvenida y acepta automáticamente a quien solicita entrar
en el canal, y (fases siguientes) organiza los chats del dueño. Decisiones y
fases: [`PLAN.md`](PLAN.md).

> El repositorio es **público**: aquí nunca van secretos (token, ids
> privados, sesiones) ni enlaces de invitación de canales de prueba.

## Estructura
```
captacion/
├── premier_captacion/      código (Python 3.9+)
│   ├── bot.py              el bot: solicitudes, mensajes, avisos, comandos
│   ├── mensajes.py         textos de bienvenida y botones
│   ├── resumen.py          resúmenes diario y semanal
│   ├── sheet.py            copia al Google Sheet (fase 2; usa gspread)
│   ├── db.py               base de datos local (SQLite)
│   ├── config.py           configuración (variables de entorno)
│   └── telegram_api.py     cliente mínimo de la Bot API
├── tests/                  pruebas automáticas (sin red ni Google)
└── deploy/                 instalador, configurador, servicios systemd y
                            plantilla de configuración
```

## Pruebas automáticas
```bash
cd captacion
python3 -m unittest discover -s tests -t .
```

---

## Fase 1: puesta en marcha en el canal de PRUEBA

Papeles en esta prueba:
- **Tu cuenta principal hace de dueño**, igual que en producción: es dueña
  del canal de prueba, recibe los avisos y los resúmenes, y los botones
  llevan a @Dronwhite.
- **La cuenta secundaria hace de cliente**: pide unirse, recibe la
  bienvenida y pulsa los botones. No necesita @usuario.

Hacen falta dos cuentas porque quien crea un canal ya está dentro y no
puede pedir unirse a él. Telegram deja tener varias cuentas en la misma app
(Ajustes → Añadir cuenta) y cambiar de una a otra.

En la fase 3 (programa de carpetas) se cambiarán los papeles: la secundaria
hará de dueño, para probar ese programa sin conectarlo todavía a tu cuenta
principal.

### Paso 1. Bot de prueba con @BotFather (desde tu cuenta principal) ✅
`/newbot` → nombre `PREMIER GALGOS (pruebas)` → @ `premiergalgos_pruebas_bot`.
El **token** que da BotFather no se copia a ningún sitio: se queda en ese
chat y solo se usa en el paso 3. Si se escapa, `/revoke` en BotFather.

### Paso 2. Canal de prueba (con tu cuenta principal) ✅
Canal **privado** «Prueba canal captación con bot», con un enlace de
invitación con **«Solicitar aprobación de administrador»** activado (si se
le pone nombre, p. ej. `prueba-1`, el bot lo usará para saber por qué
enlace entra cada uno). El bot todavía no se añade (paso 5).

⚠️ Tiene que ser un **canal**, no un grupo: el primer intento fue un grupo
con el bot como simple miembro y no sirve.

### Paso 3. Instalar el bot en la VM ✅
Entra en la VM por SSH (`ssh root@galgos-vm.tailc02685.ts.net`; si Tailscale
pide verificar en el navegador, se acepta) y ejecuta:
```bash
curl -fsSLo /tmp/instalar-captacion.sh https://raw.githubusercontent.com/davilapilila-design/picks-premier-galgos/captacion-bienvenida/captacion/deploy/instalar.sh
bash /tmp/instalar-captacion.sh prueba
```
El instalador comprueba la VM, descarga el código de GitHub, lo instala en
`/opt/premier-captacion` y **pide el token**: cópialo del chat con
@BotFather (más cómodo desde Telegram en el ordenador) y pégalo en la
terminal. No se ve al pegarlo; es normal. Pulsa Enter. Al final debe decir
«✅ Bot «prueba» instalado y funcionando».

### Paso 4. Decirle al bot quién eres ✅
Con tu **cuenta principal**, abre `@premiergalgos_pruebas_bot` y pulsa
**«Iniciar»**. Contesta «🛠️ Bot en puesta en marcha. Tu id de Telegram es:
…». En la VM, con ese número:
```bash
bash /opt/premier-captacion/configurar.sh prueba propietario TU_ID
```
(reinicia el bot solo). Escribe `/start` otra vez: ahora contesta «✅ Bot
de captación activo».

### Paso 5. Hacer administrador al bot en el canal de prueba ✅
Con tu cuenta principal: canal de prueba → Administrar canal →
Administradores → Añadir administrador → busca `premiergalgos_pruebas_bot`
→ deja activado **solo «Añadir suscriptores»** → Guardar. El bot te escribe
el id del canal (`-100…`). En la VM:
```bash
bash /opt/premier-captacion/configurar.sh prueba canal -100XXXXXXXXXX
```
Después escribe `/estado` al bot: debe decir el canal y `Botones apuntan a:
@Dronwhite`. Los resúmenes (00:05 y lunes 9:00) ya los activó el instalador.

### Paso 6. Lista de pruebas (la secundaria hace de cliente)
Para pasarle el enlace de invitación a la secundaria basta con copiarlo y
pegarlo (o enviárselo por privado desde tu cuenta principal).
- [ ] **Bienvenida**: con la secundaria, abre el enlace y pide unirte. En
      segundos llega el mensaje del bot con los dos botones, y el bot
      acepta la solicitud. Comprueba las negritas y los emojis.
- [ ] **Botones**: pulsa «🏁 Ya he apostado»: se abre el chat con
      @Dronwhite con el texto ya escrito. Igual con «🆕 Es mi primera vez».
      Pruébalo en el móvil y, si puedes, en Telegram de ordenador. (No
      hace falta enviarlo; si lo envías, te llega a tu cuenta principal.)
- [ ] **Escribir al bot** (con la secundaria): escríbele "hola": responde
      «Por aquí no puedo contestarte…» con los botones. Envía 3 mensajes
      seguidos: una sola respuesta. Espera más de un minuto y escribe otra
      vez: vuelve a responder.
- [ ] **Volver a entrar**: la secundaria sale del canal y vuelve a pedir
      unirse: la acepta **sin** enviarle nada.
- [ ] **Comandos** (desde tu cuenta principal): `/resumen`, `/semana`, `/estado`.
- [ ] **Resumen programado ya**: `systemctl start captacion-resumen-diario@prueba`
      (envía el de ayer, que estará vacío: sirve para ver que llega).
- [ ] **Permisos**: quita al bot de administrador → te avisa con 🚨. Vuelve
      a ponerlo (solo «Añadir suscriptores») → te avisa con ✅.
- [ ] **Bot parado más de 5 min** (opcional). Para repetir pruebas desde
      cero hay que borrar la memoria de la prueba:
      ```bash
      systemctl stop captacion-bot@prueba
      rm -f /var/lib/premier-captacion/prueba.db*
      ```
      Con el bot parado: la secundaria sale del canal, pide unirse, espera 6
      minutos y arrancas el bot (`systemctl start captacion-bot@prueba`).
      La acepta sin bienvenida y te avisa de «1 solicitud(es) llevaban más
      de 5 minutos esperando».

### Cosas útiles (en la VM)
```bash
bash /opt/premier-captacion/configurar.sh prueba ver   # configuración (sin el token)
bash /opt/premier-captacion/instalar.sh prueba         # actualizar a la última versión
systemctl status captacion-bot@prueba                  # ¿está funcionando?
journalctl -u captacion-bot@prueba --since today       # registro de hoy
journalctl -u captacion-bot@prueba -f                  # registro en directo (Ctrl+C sale)
systemctl list-timers 'captacion-*'                    # próximos resúmenes y copias
systemctl start captacion-sheet@prueba                 # copiar al Sheet ahora mismo
journalctl -u captacion-sheet@prueba -n 20             # registro de las copias al Sheet
```
Si el token se ha escapado: `/revoke` en @BotFather y después
`bash /opt/premier-captacion/configurar.sh prueba token` con el nuevo.

Sin `root` hay que poner `sudo` delante de cada orden.

---

## Fase 2: copia al Google Sheet

Hoja de pruebas: **«Captación PREMIER GALGOS (pruebas)»**, en el Drive del
dueño, privada y compartida como editor solo con la cuenta de servicio de la
VM (la misma que usa el sistema de picks). La instancia real tendrá su
propia hoja.

Se rellena sola cada 10 minutos desde la VM. **No edites estas cuatro
pestañas** (se sobrescriben); para notas o gráficos propios, crea otras:

| Pestaña | Qué tiene |
|---|---|
| Usuarios | Una fila por persona (por su User ID de Telegram): nombre y @ actuales, primera y última solicitud, enlace de entrada, tipo de bienvenida y cuándo, mensajes al bot, si lo bloqueó |
| Eventos | Todo lo que pasa, en orden: solicitudes, bienvenidas, aceptaciones, mensajes al bot... Solo se añaden filas nuevas |
| Resumen diario | Una fila por día, más reciente arriba. Cada número es una fórmula sobre Eventos: al pulsarlo se ve de dónde sale |
| Tipos de mensaje | Cada texto de bienvenida con su código (el que aparece en Usuarios y Eventos) |

Las fechas son fechas de verdad (en hora de España), así que valen para
filtros, tablas dinámicas y gráficos. No se guarda el contenido de ninguna
conversación.

### Activarla en la VM
1. Actualiza: `bash /opt/premier-captacion/instalar.sh prueba`. Instala
   gspread en `/opt/premier-captacion/venv`, copia la credencial de la
   cuenta de servicio de picks a `/etc/premier-captacion/google.json` (solo
   root) y activa el timer `captacion-sheet@prueba`.
2. Dile qué hoja usar (vale pegar el enlace entero):
   ```bash
   bash /opt/premier-captacion/configurar.sh prueba sheet "https://docs.google.com/spreadsheets/d/…/edit"
   ```
   Hace la primera copia en el acto. Debe acabar en «✓ Sheet actualizado».
3. Abre la hoja: deben salir las cuatro pestañas con los datos de la prueba.

Si falla con un error de permisos, la hoja no está compartida como editor con
la cuenta de servicio (el instalador dice cuál es).

---

## Fase 3: lector de carpetas (se prueba con la cuenta SECUNDARIA)

Un programa en la VM se conecta a una cuenta de Telegram y ordena sus
carpetas (reglas completas en `premier_captacion/carpetas.py`):
- Quien recibió la bienvenida y le escribe → carpeta del día («10.15»). Si
  vuelve a escribir otro día sin tener enlace, pasa a la carpeta del nuevo día.
- La cuenta le envía un enlace `t.me/+…` que no es del canal principal →
  carpeta «free send», y ahí se queda.
- Se quedan las 5 carpetas de días más recientes; «free send» guarda los ~90
  más recientes. Solo toca chats del embudo y solo esas carpetas.

**Seguridad**:
- **Nunca envía nada.** Toda petición a Telegram pasa por un candado
  (`premier_captacion/guardia.py`) que solo deja leer y organizar carpetas.
  Enviar, marcar como leído, unirse a canales o aparecer «en línea» está
  bloqueado.
- **Empieza siempre en SIMULACIÓN:** te avisa por el bot de lo que haría y no
  toca ninguna carpeta. Solo actúa de verdad si se lo dices.
- **La sesión se guarda solo en la VM** (`/var/lib/premier-captacion/`). En
  Telegram aparece en Ajustes → Dispositivos como «Premier captación (VM)» y
  se puede cerrar desde ahí cuando quieras.

En la prueba los papeles cambian: **la secundaria hace de «dueño»** (el
programa ordena sus carpetas) y **tu cuenta principal hace de cliente**.

### Paso 1. api_id y api_hash (tú, en el navegador)
Entra en <https://my.telegram.org> con tu cuenta principal → «API development
tools» → crea una aplicación (nombre cualquiera, p. ej. «Premier captacion»).
Apunta el **api_id** (un número) y el **api_hash** (32 letras y números,
secreto: no lo pegues en ningún chat). Sirven para conectar cualquier cuenta.

### Paso 2. Actualizar la VM
```bash
bash /opt/premier-captacion/instalar.sh prueba
```
Instala Telethon en el entorno de Python. No conecta ninguna cuenta.

### Paso 3. Conectar la cuenta secundaria (tú, en TU terminal SSH)
```bash
bash /opt/premier-captacion/conectar-cuenta.sh prueba
```
Te pide el api_id y el api_hash, confirmación (escribe SI), el teléfono **de la
cuenta secundaria**, el código que le llega por Telegram y, si la tiene, la
contraseña de verificación en dos pasos. Al acabar arranca el lector en
simulación y te llega por el bot «📁 Lector de carpetas conectado…».

### Paso 4. Que tu cuenta principal cuente como «del embudo»
Tu cuenta principal no pasó por la bienvenida (es la dueña del canal de
prueba), así que se marca a mano, solo para la prueba, con tu id de
Telegram (el de `/miid`):
```bash
bash /opt/premier-captacion/lector.sh prueba embudo-prueba TU_ID
```

### Paso 5. Probar en simulación
- [ ] Desde tu cuenta principal, escribe a la secundaria → te llega por el bot
      «🧪 Simulación (no he tocado nada): creo la carpeta 10.15 y meto a …».
      Puede que también diga que borraría las carpetas de días más antiguas,
      si la secundaria tiene más de 5.
- [ ] Desde la secundaria, envíale a tu principal el enlace del canal de prueba
      → no pasa nada (es el canal principal).
- [ ] Desde la secundaria, envíale el enlace `t.me/+…` de otro canal →
      «🧪 Simulación: … creo la carpeta «free send» y meto a …».
- [ ] Vuelve a escribir desde la principal → no se mueve (ya tiene enlace).
- [ ] Revisa que en la secundaria no ha cambiado ninguna carpeta y que los
      mensajes siguen como no leídos.

### Paso 6. Probar de verdad (con tu visto bueno)
```bash
bash /opt/premier-captacion/configurar.sh prueba lector real
```
Para repetir la prueba desde cero, borra la memoria de prueba
(`systemctl stop captacion-bot@prueba captacion-lector@prueba`,
`rm -f /var/lib/premier-captacion/prueba.db*`, arrancarlos otra vez) y vuelve
al paso 4. Comprueba en la secundaria que se crean «10.15» y «free send» y que
el chat pasa de una a otra.

### Desconectar la cuenta
```bash
systemctl disable --now captacion-lector@prueba
rm -f /var/lib/premier-captacion/prueba-cuenta.session
```
y cierra la sesión «Premier captación (VM)» en Telegram → Ajustes → Dispositivos.

---

## Fase 4: histórico de bienvenidas manuales (SOLO LECTURA)

Busca en los chats de la cuenta conectada las bienvenidas que enviabas a mano
(«Buenas! Bienvenido a 𝗣𝗥𝗘𝗠𝗜𝗘𝗥 𝗚𝗔𝗟𝗚𝗢𝗦 🐕…» y «Buenos dias y bienvenido a
Premier Galgos! 🐾…», con variantes). A esas personas el bot no les volverá a
enviar la bienvenida. Además apunta si contestaron y si recibieron enlace de
venta, para comparar en el Sheet las bienvenidas manuales con la del bot. No
toca carpetas ni envía nada (el candado no lo deja en este modo).

- **Prueba**: desde la secundaria, envía a tu principal un texto de bienvenida
  antiguo y luego `bash /opt/premier-captacion/leer-historico.sh prueba`. Te
  llega el resumen por el bot.
- **Tu cuenta real (solo con tu visto bueno)**:
  `bash /opt/premier-captacion/conectar-cuenta.sh real` (en tu terminal; crea
  la configuración de la instancia real, pero no instala ni arranca el bot
  real ni el lector de carpetas) y después
  `bash /opt/premier-captacion/leer-historico.sh real`.

---

## Paso a producción (fase 5) — SOLO con el visto bueno del dueño
Igual que la prueba pero con la instancia `real` (el instalador pide
confirmación escribiendo SI): `bash /opt/premier-captacion/instalar.sh real`,
con el token del bot real (PREMIER GALGOS + logo), y después
`configurar.sh real propietario …` y `configurar.sh real canal …`. Antes de
activarlo: ponles nombre a los enlaces de entrada del canal, y acepta a mano
las solicitudes que haya pendientes en ese momento. El detalle se preparará
cuando toque.
