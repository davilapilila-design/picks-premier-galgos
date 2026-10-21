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

En la fase 3 (programa de carpetas) los papeles son los mismos: tu cuenta
principal se conecta en simulación y la secundaria hace de cliente.

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
- [ ] **Freno de emergencia**: `/pausar` → con la secundaria pide unirte: no
      le llega bienvenida y la solicitud se queda pendiente (te avisa una
      vez). `/estado` dice «EN PAUSA». `/reanudar` → vuelve a aceptar (la
      pendiente la aceptas tú a mano).
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

## Fase 3: lector de carpetas (prueba con tu cuenta principal, en simulación)

Un programa en la VM se conecta a una cuenta de Telegram y ordena sus
carpetas (reglas completas en `premier_captacion/carpetas.py`):
- Quien recibió la bienvenida y le escribe → carpeta del día, día.mes («18.10»). Si
  ya existe, la usa. Si vuelve a escribir otro día sin tener enlace, pasa a
  la carpeta del nuevo día.
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
  toca ninguna carpeta. En simulación el candado ni siquiera deja pedirle a
  Telegram un cambio de carpetas. Solo actúa de verdad si se lo dices.
- **La sesión se guarda solo en la VM** (`/var/lib/premier-captacion/`). En
  Telegram aparece en Ajustes → Dispositivos como «Premier captación (VM)» y
  se puede cerrar desde ahí cuando quieras.

**Cómo se prueba**: tu cuenta principal se conecta a la instancia `prueba`,
en simulación. Para esa instancia solo es «del embudo» quien está en la
memoria de prueba, es decir, la cuenta secundaria (que recibió la bienvenida
del bot de prueba): **tus clientes reales se ignoran**. Se prueba el flujo de
verdad: la secundaria pulsa un botón de la bienvenida y te escribe.

### Paso 1. api_id y api_hash (tú, en el navegador)
1. Entra en <https://my.telegram.org>, pon tu teléfono con el prefijo del
   país y sin el 0 inicial (p. ej. +353 8… o +34 6…) y el código que te
   llega a la app de Telegram.
2. «API development tools» → rellena *App title* `Premier captacion`, *Short
   name* `premiercaptacion`, *Platform* `Desktop` (lo demás, vacío) →
   «Create application».
3. Apunta el **api_id** (un número) y el **api_hash** (32 letras y números,
   secreto: no lo pegues en ningún chat).

Si al crearla sale «ERROR», prueba con otro navegador, sin VPN ni
bloqueador de anuncios, o con otro *Short name*.

### Paso 2. Actualizar la VM
```bash
curl -fsSLo /tmp/instalar-captacion.sh https://raw.githubusercontent.com/davilapilila-design/picks-premier-galgos/captacion-bienvenida/captacion/deploy/instalar.sh
bash /tmp/instalar-captacion.sh prueba
```
No conecta ninguna cuenta.

### Paso 3. Conectar tu cuenta (tú, en TU terminal SSH)
```bash
bash /opt/premier-captacion/conectar-cuenta.sh prueba
```
Dos avisos antes de empezar:
- **El código, escríbelo a mano.** Si lo copias y lo pegas o lo reenvías en
  cualquier chat de Telegram (aunque sea a ti mismo o a un bot), Telegram lo
  da por robado y bloquea el inicio de sesión («el código fue compartido»).
  Si pasa, no ha entrado nadie: vuelve a ejecutar el comando y te llega uno
  nuevo.
- **Desde el móvil (Termius)**, al cambiar de app se corta la conexión SSH y
  se cierra el programa. Ejecútalo dentro de `tmux new -s tg`; si se corta,
  vuelve a entrar y escribe `tmux attach -t tg` para seguir donde estabas.

Te pide el api_id y el api_hash, confirmación (escribe SI), **tu teléfono**
(igual que en el paso 1: prefijo del país y sin el 0 inicial; si lo pones
mal, te lo vuelve a pedir), el código que te llega por Telegram y, si la
tienes, la contraseña de verificación en dos pasos. Al acabar arranca el
lector en simulación y te llega por el bot de prueba «📁 Lector de carpetas
conectado… Modo: SIMULACIÓN». Justo después pueden llegar dos tipos de
aviso, los dos solo avisos (no toca nada):
- «🧪 Simulación (no he tocado nada): borro la carpeta xx.10…»: si tienes más
  de 5 carpetas de días, las más antiguas que sobrarían.
- «🧪 Simulación: … meto a … en la carpeta …»: al arrancar repasa las últimas
  24 horas, así que si la secundaria ya te escribió en ese rato, ya te dice
  dónde la metería.

Como en simulación no cambia nada, cada día vuelve a partir de tus carpetas
reales (por si creas o borras alguna a mano): por eso, pasada la medianoche,
te repetirá qué carpetas antiguas borraría.

### Paso 4. Probar en simulación
- [ ] Con la secundaria, pulsa un botón de la bienvenida del bot (o escríbete
      a @Dronwhite) y envía → te llega por el bot «🧪 Simulación (no he tocado
      nada): meto a … en la carpeta 18.10» (o «creo la carpeta…» si no
      existe). Si ya te lo dijo al arrancar, no lo repite: ya la tiene ahí.
- [ ] Desde tu cuenta, envía a la secundaria el enlace del canal de prueba →
      no pasa nada (en la prueba, el «canal principal» es el de prueba).
- [ ] Desde tu cuenta, envía a la secundaria el enlace `t.me/+…` de uno de tus
      canales de venta → «🧪 Simulación: saco a … de la carpeta 18.10» y
      «creo la carpeta «free send» y meto a …».
- [ ] Vuelve a escribir desde la secundaria → no se mueve (ya tiene enlace).
- [ ] Comprueba en tu Telegram que no ha cambiado ninguna carpeta y que los
      mensajes siguen como no leídos.

Pasar el lector de tu cuenta a modo real es la fase 6 y necesita tu visto
bueno: no lo hagas en la instancia `prueba`, porque al rotar borraría de
verdad tus carpetas de días más antiguas.

### Desconectar la cuenta
```bash
systemctl disable --now captacion-lector@prueba
rm -f /var/lib/premier-captacion/prueba-cuenta.session
```
y cierra la sesión «Premier captación (VM)» en Telegram → Ajustes → Dispositivos.

(Alternativa: probar con la cuenta secundaria como «dueña», conectándola a ella
y marcando tu cuenta principal con
`bash /opt/premier-captacion/lector.sh prueba embudo-prueba TU_ID`.)

---

## Fase 4: histórico de bienvenidas manuales (SOLO LECTURA)

Busca en los chats de la cuenta conectada las bienvenidas que enviabas a mano
(«Buenas! Bienvenido a 𝗣𝗥𝗘𝗠𝗜𝗘𝗥 𝗚𝗔𝗟𝗚𝗢𝗦 🐕…» y «Buenos dias y bienvenido a
Premier Galgos! 🐾…», con variantes). A esas personas el bot no les volverá a
enviar la bienvenida. Además apunta si contestaron y si recibieron enlace de
venta, para comparar en el Sheet las bienvenidas manuales con la del bot. No
toca carpetas ni envía nada (el candado no lo deja en este modo).

- **Prueba**: con tu cuenta principal conectada a `prueba` (fase 3), **no
  ejecutes el histórico en `prueba`**: leería tus chats reales y metería a
  tus clientes en la memoria de prueba. Solo se prueba así si la conectada a
  `prueba` es la secundaria: desde ella, envía a tu principal un texto de
  bienvenida antiguo y luego
  `bash /opt/premier-captacion/leer-historico.sh prueba`.
- **Tu cuenta real (solo con tu visto bueno)**. Desde el móvil, todo dentro
  de `tmux new -s tg` (si se corta: `tmux attach -t tg`):
  1. `bash /opt/premier-captacion/conectar-cuenta.sh real`: crea la
     configuración de la instancia real (no instala ni arranca el bot real
     ni el lector de carpetas). Te ofrece usar el mismo api_id y api_hash que
     en «prueba» (escribe SI); después SI, tu teléfono y el código (a mano).
  2. `bash /opt/premier-captacion/leer-historico.sh real`: la primera vez te
     pide un enlace de invitación de tu canal principal (p. ej. el de la
     descripción) para saber cuál es; comprueba a qué canal lleva, sin
     unirse, te dice su nombre y, si escribes SI, lo guarda. Luego lee el
     histórico: puede tardar media hora o más (si Telegram pide esperar, espera solo)
     y va diciendo por dónde va. Al final escribe el resumen.

---

## Dudas frecuentes y cambiar textos (en el bot)

**Dudas frecuentes.** Cuando alguien escribe al bot, la respuesta lleva el
botón «📚 Dudas frecuentes»: un menú con Casas de apuestas (y dentro, Otras
casas y canódromos), Unidades, Bank y stakes, Apuesta a ganador, Gemelas y
tríos y Packs. Cada respuesta acaba invitando a escribirte:
- **Sin la apuesta de regalo** (aún no le has enviado enlace de venta): con
  los dos botones de la bienvenida.
- **Con ella**: con «✉️ Escríbeme», que deja escrito «Hola, tengo una duda
  sobre …».

Para saber quién tiene la gratuita, el lector de tu cuenta tiene que estar en
marcha en esa instancia (basta en simulación). En el bot real, de las 994
del histórico ya lo sabe.

**Cambiar textos** (solo tú): escríbele `/textos` al bot y elige cuál
(bienvenida, las dos respuestas, el menú, cada duda y los dos finales). Te
manda el texto actual; lo copias, lo cambias y se lo mandas. Las negritas,
con la negrita de Telegram (seleccionar → Negrita): el bot las pasa a las
letras gruesas. Te enseña cómo quedará y eliges ✅ Guardar o ❌ Cancelar.
También puedes volver al texto anterior o al original. Cada bienvenida
distinta es una versión nueva (bot_b_v2, v3…), para compararlas en la hoja.
Los botones de la bienvenida no se cambian desde aquí. Cada bot guarda sus
propios textos: los del de prueba no pasan al real. `/dudas` te enseña el
menú como lo ve un cliente.

**Prueba en el bot de prueba:**
- [ ] Desde la secundaria, escribe al bot → respuesta con «📚 Dudas
      frecuentes» → recorre los temas y «⬅️ Otras dudas». La secundaria ya
      tiene enlace de venta (prueba de la fase 3), así que verás «✉️
      Escríbeme». Con `/dudas` desde tu cuenta ves la versión sin la
      gratuita.
- [ ] `/textos` → elige una duda → mándale un texto con alguna palabra en
      negrita → «👀 Así lo verán» → ✅ Guardar → compruébalo desde la
      secundaria.
- [ ] `/textos` → la misma → «↩️ Volver al anterior» → ✅ Guardar.

**Consultar la gratuita de alguien** (solo tú): `/gratuita @usuario`, o
parte del nombre (`/gratuita Juan`; sin importar mayúsculas ni tildes). El
bot te dice cuándo recibió la bienvenida, cuándo te escribió y con qué botón,
y **cuándo le diste la gratuita, a qué canal de venta y con qué enlace** (y
los enlaces de venta que le mandaste después). Si hay varias personas con ese nombre, te
da botones para elegir (las que tienen gratuita, con 🎁). Queda guardado en
la base de datos del bot en cuanto el lector ve el enlace: **aunque luego se
borren los mensajes, se sigue sabiendo**. Solo hace falta que el lector
esté en marcha cuando lo envías.
- [ ] En el bot de prueba: `/gratuita` con el @ o el nombre de la
      secundaria → debe salir la gratuita de la prueba de la fase 3.

---

## Paso a producción — SOLO con el visto bueno explícito del dueño

Orden recomendado: fase 4 en la cuenta real (solo lectura) antes de la fase
5, para que el bot real no repita la bienvenida a quien ya la recibió a mano.
Si se hace al revés no se pierde nada: como mucho, alguien que vuelve recibe
también la del bot.

### Fase 5: el bot real en PREMIER GALGOS
1. **@BotFather (tu cuenta principal)**: `/newbot` → nombre `PREMIER GALGOS`
   → un @ libre que acabe en `bot`. Después `/setuserpic` con el logo del
   canal. El token se queda en ese chat.
2. **Enlaces de entrada del canal real**: en cada uno (Administrar canal →
   Enlaces de invitación → el enlace → Editar) ponle nombre, p. ej.
   `descripcion-web` y `landing`, y comprueba que «Solicitar aprobación de
   administrador» sigue activado. La URL no cambia.
3. **VM**: `bash /opt/premier-captacion/instalar.sh real` (pide escribir SI y
   el token del bot real; los botones llevan a @Dronwhite).
4. Abre el bot real con tu cuenta principal y escríbele `/miid` → te da tu
   id → `bash /opt/premier-captacion/configurar.sh real propietario TU_ID`.
5. **Justo antes de activarlo**: acepta a mano las solicitudes pendientes del
   canal (el bot solo ve las que lleguen después).
6. Haz administrador al bot en PREMIER GALGOS **solo con «Añadir
   suscriptores»**. Si el canal ya quedó guardado en la fase 4 (te lo
   preguntó `leer-historico.sh`), desde ese momento las solicitudes se
   aceptan solas. Si no, te escribe el id del canal →
   `bash /opt/premier-captacion/configurar.sh real canal -100…`, y desde
   entonces se aceptan solas.
7. `/estado` al bot real, y mira las primeras solicitudes reales.
8. Sheet real: una hoja nueva («Captación PREMIER GALGOS»), compartida como
   editor con la cuenta de servicio →
   `bash /opt/premier-captacion/configurar.sh real sheet <enlace>`.
9. Cuando estés contento, apaga lo de prueba:
   `systemctl disable --now captacion-bot@prueba captacion-resumen-diario@prueba.timer captacion-resumen-semanal@prueba.timer captacion-sheet@prueba.timer`
   (y `captacion-lector@prueba` si está activo).

**Si algo falla, lo más rápido**: escríbele `/pausar` al bot (solo tú
puedes). Deja de enviar bienvenidas y de aceptar al momento; las solicitudes
se quedan pendientes para que las aceptes a mano. Sigue en pausa aunque el
bot se reinicie, y te lo recuerda en `/estado` y en los resúmenes. Para
volver: `/reanudar`. Si el bot no contestara ni a eso, quítalo de
administrador del canal (también para al momento).

Para volver atrás del todo: quita al bot de administrador del canal (vuelves
a aceptar a mano) y `systemctl disable --now captacion-bot@real`.

### Antes de la fase 5: lectura en la cuenta real mientras aceptas a mano
Decidido por el dueño (2026-10-21) para que, mientras no esté el bot real,
quede apuntado a quién se da la gratuita. El lector de la instancia real
reconoce en el momento la bienvenida que mandas a mano y, desde ahí, sigue a
esa persona (si te escribe, si le mandas enlace de venta). En simulación: no
mueve carpetas. Sin bot real no hay avisos; funciona en silencio.
1. Actualizar la VM (`instalar.sh prueba`, como siempre).
2. `bash /opt/premier-captacion/configurar.sh real bienvenidas-manuales si`
3. `bash /opt/premier-captacion/leer-historico.sh real` (recupera lo que
   pasó desde la última lectura; no duplica nada).
4. `systemctl enable --now captacion-lector@real`

Para consultar a alguien sin bot real, en la VM (solo lee):
```bash
cd /opt/premier-captacion && sudo -u captacion python3 -c "
import sqlite3; from zoneinfo import ZoneInfo; from premier_captacion import consulta
con = sqlite3.connect('file:/var/lib/premier-captacion/real.db?mode=ro', uri=True); con.row_factory = sqlite3.Row
print(consulta.respuesta(con, '@usuario', ZoneInfo('Europe/Madrid'))[0])"
```

Para apuntar a mano una gratuita que ya no se puede leer (chat borrado antes
de encender la lectura), con las horas de España de la bienvenida y de la
gratuita y el enlace de venta (solo lee de Telegram: busca a la persona):
```bash
systemctl stop captacion-lector@real
bash /opt/premier-captacion/lector.sh real apuntar-gratuita @usuario "AAAA-MM-DD HH:MM" "AAAA-MM-DD HH:MM" https://t.me/+…
systemctl start captacion-lector@real
```

### Fase 6: carpetas en tu cuenta real
1. Si no lo hiciste en la fase 4: `bash /opt/premier-captacion/conectar-cuenta.sh real`.
2. `systemctl enable --now captacion-lector@real`: arranca en **simulación**.
   Durante un día o dos te avisará por el bot de cada cosa que haría. Al
   arrancar dirá que borraría tus carpetas de días más antiguas que las 5
   más recientes (tienes 7): es lo acordado.
3. Si todo cuadra: `bash /opt/premier-captacion/configurar.sh real lector real`.
