# Captación PREMIER GALGOS

Bot que da la bienvenida y acepta automáticamente a quien solicita entrar
en el canal, y (fases siguientes) organiza los chats del dueño. Decisiones y
fases: [`PLAN.md`](PLAN.md).

> El repositorio es **público**: aquí nunca van secretos (token, ids
> privados, sesiones) ni enlaces de invitación de canales de prueba.

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
systemctl list-timers 'captacion-*'                    # próximos resúmenes
```
Si el token se ha escapado: `/revoke` en @BotFather y después
`bash /opt/premier-captacion/configurar.sh prueba token` con el nuevo.

Sin `root` hay que poner `sudo` delante de cada orden.

---

## Paso a producción (fase 5) — SOLO con el visto bueno del dueño
Igual que la prueba pero con la instancia `real` (el instalador pide
confirmación escribiendo SI): `bash /opt/premier-captacion/instalar.sh real`,
con el token del bot real (PREMIER GALGOS + logo), y después
`configurar.sh real propietario …` y `configurar.sh real canal …`. Antes de
activarlo: ponles nombre a los enlaces de entrada del canal, y acepta a mano
las solicitudes que haya pendientes en ese momento. El detalle se preparará
cuando toque.
