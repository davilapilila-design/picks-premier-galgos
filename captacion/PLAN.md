# Captación PREMIER GALGOS — plan aprobado

Aprobado por el dueño el 2026-10-14. Subsistema independiente del de picks:
vive solo en `captacion/` (rama `captacion-bienvenida`), no toca `src/`.

## Objetivo
1. **Bienvenida automática**: las solicitudes de unión al canal (unas 20-30
   al día) pasan a aceptarse solas. Un bot envía la bienvenida por privado
   y acepta la solicitud. El dueño deja de aceptar a mano.
2. **Organizar los chats del dueño**: quien le escribe por privado entra en
   la carpeta del día (`DD.MM`, p. ej. `18.10`); cuando el dueño le envía el enlace de un
   canal de venta, pasa a la carpeta `free send`.
3. **Estadísticas**: todo queda registrado (Google Sheet + resúmenes por
   Telegram).

## Restricciones de Telegram que condicionan el diseño
- Un bot solo puede escribir a alguien que no le ha hablado antes mientras
  su solicitud de unión está pendiente (5 minutos como máximo). Por eso la
  bienvenida se envía **siempre antes** de aceptar, y "Solicitar aprobación
  de administrador" tiene que seguir activado en los enlaces.
- El bot no ve los miembros actuales del canal: la memoria de "a quién se le
  dio ya la bienvenida" empieza en la activación, más lo que se recupere del
  histórico de chats del dueño (fase 4).
- Telegram no avisa al bot cuando alguien pulsa un botón de enlace: qué
  botón eligió cada persona se sabe por el texto que le llega al dueño.
- Carpetas sin Premium (el dueño no tiene Premium): máximo **10 carpetas** y
  **100 chats por carpeta**; nombre de carpeta de 12 caracteres como mucho.

## Decisiones
| Tema | Decisión |
|---|---|
| Bot | Nombre "PREMIER GALGOS" con el logo del canal. Administrador del canal con un único permiso: «Añadir suscriptores». |
| Bienvenida | Versión B (ver `premier_captacion/mensajes.py`), negritas Unicode idénticas al mensaje manual. Solo a quien no la haya recibido nunca (por `user_id`). |
| Botones | «🏁 Ya he apostado» y «🆕 Es mi primera vez». Abren el chat de @Dronwhite con el texto ya escrito: «¡Hola! Acabo de entrar en el canal. Ya he apostado en galgos antes 🐕» / «¡Hola! Acabo de entrar en el canal. Es mi primera vez con los galgos 🐕» (cambiado durante las pruebas: el dueño no quería «Vengo de PREMIER GALGOS»). |
| Si escriben al bot | Responde cada vez con «Por aquí no puedo contestarte 🙈 Escríbeme a mi perfil…» y los dos botones. Ante una ráfaga de mensajes, una sola respuesta (pausa de 60 s). Atender dudas desde el bot a quien ya escribió al dueño: **más adelante**. |
| Enlaces de entrada | `+VtCh-VrBHPpiMzg0` (descripción y web, se cuentan juntos) y `+om-eKd0-3OUyOGY0` (landing). Se guarda de cuál viene cada persona; conviene ponerles nombre en Telegram. |
| Carpeta del día `DD.MM` | Día.mes, p. ej. `18.10` (el dueño lo corrigió el 2026-10-18: al principio se dijo mes.día). También vale `5.11` sin cero. Solo entra quien recibió alguna bienvenida (bot o manual). Si vuelve a escribir otro día sin haber recibido el enlace, pasa a la carpeta del día nuevo (reconfirmado por el dueño el 2026-10-18). Hora de España. Se adoptan las carpetas de días que el dueño ya tiene, también la de mañana si la crea antes de tiempo. |
| Rotación | Se mantienen **5 días**; cada noche se borra la carpeta más antigua (los chats no se borran). La de hoy va **la última**. El dueño tiene 9 carpetas (7 de días + 2 suyas): quedan 5 + `free send` + 2 suyas = 8. Las suyas no se tocan nunca. |
| `free send` | Un chat pasa aquí cuando el dueño envía un enlace de invitación `t.me/+…` (o `t.me/joinchat/…`) que **no** sea del canal principal (se comprueba a qué canal lleva, así vale para enlaces futuros). Se guarda qué enlace y qué canal de venta se le envió. Se queda con los ~90 chats más recientes (tope 100). Quien ya está en `free send` no vuelve a moverse. |
| Bienvenidas antiguas | Se buscan en el histórico del dueño las dos versiones manuales («Buenas! Bienvenido a 𝗣𝗥𝗘𝗠𝗜𝗘𝗥 𝗚𝗔𝗟𝗚𝗢𝗦 🐕…» y «Buenos dias y bienvenido a Premier Galgos! 🐾…», y variantes) para no repetírsela a nadie. |
| Tipos de mensaje | Los dos manuales y el del bot (`bot_b_v1`) se guardan por separado. Cada cambio de texto del bot = tipo nuevo, para comparar. |
| Datos | SQLite local en la VM (con lo que el bot decide) + Google Sheet **privado y aparte** del de picks (copia para consultar y estadísticas). No se guarda el contenido de las conversaciones, solo qué pasó y cuándo. |
| Resúmenes | Bot → dueño: diario a las **00:05** (día anterior) y semanal los **lunes a las 9:00** (lunes a domingo, comparado con la semana anterior). También a demanda: `/resumen`, `/semana`, `/estado`. |
| Freno de emergencia | Pedido por el dueño (2026-10-19). `/pausar` al bot (solo el dueño): deja de enviar bienvenidas y de aceptar al momento; las solicitudes se quedan pendientes para aceptarlas a mano. Sigue en pausa tras un reinicio y lo recuerdan `/estado` y los resúmenes. `/reanudar` para volver. Plan B: quitarle la administración del canal. |
| Dudas frecuentes | Decidido con el dueño (2026-10-19): botón «📚 Dudas frecuentes» en la respuesta del bot a quien le escribe. Temas: Casas de apuestas (con submenú Otras casas y canódromos), Unidades, Bank y stakes, Apuesta a ganador, Gemelas y tríos, Packs (garantía). Respuestas cortas que acaban invitando a escribirle; a quien no tiene aún la apuesta de regalo (sin enlace de venta) se le vuelve a hacer la pregunta de la bienvenida con sus dos botones, y a quien ya la tiene, «escríbeme» con el tema ya escrito. |
| Cambiar textos | Pedido por el dueño (2026-10-19): `/textos` en el bot (solo él) para cambiar la bienvenida, las respuestas y las dudas, con vista previa y confirmación, y volver al anterior o al original. Se guardan en la base de datos de cada instancia. Cada bienvenida distinta es un tipo nuevo (bot_b_v2…) para las estadísticas. Los botones de la bienvenida no se cambian desde el bot. |
| Consultar la gratuita | Pedido por el dueño (2026-10-19): `/gratuita @usuario` o parte del nombre (solo él) → cuándo se le dio la gratuita y a qué canal de venta, más bienvenida, primer mensaje y botón. Sale de la base de datos, así que vale aunque se borren los mensajes. |
| Lectura real antes del bot | Decidido por el dueño (2026-10-21): mientras sigue aceptando a mano, el lector corre en la cuenta real en simulación y apunta en directo las bienvenidas que manda a mano (`CAPTACION_BIENVENIDAS_MANUALES=1`, solo en real), para que conste a quién se le da la gratuita. Antes se repite el histórico para cubrir desde el 18/10. |
| Quien ya estaba o vuelve | Pedido por el dueño (2026-10-23; algunos salían y volvían a entrar para conseguir otra gratuita): quien ya estaba en el canal (lista de suscriptores leída con su cuenta, solo lectura: modo `suscriptores` del candado, autorizado por él) o ya pasó por aquí y vuelve a pedir entrar recibe una bienvenida **sin gratuita** («Buenas! Bienvenido… aquí tienes las dudas… escríbeme»), con «📚 Dudas frecuentes» y «✉️ Escríbeme». Sin que se note: el texto ya escrito dice «consulta» en vez de «duda», así el dueño sabe que es alguien que vuelve. Tampoco se les ofrece la gratuita al escribir al bot ni en las dudas. Se cambia con `/textos`. |
| Dónde corre | La VM de Proyecto Galgos, como servicios systemd propios con un usuario de sistema sin privilegios (`captacion`). |

## Arquitectura
```
Solicitud de unión ──► BOT ──► 1) envía la bienvenida (con los 2 botones)
                         │      2) acepta la solicitud
                         └────► 3) lo apunta en la base de datos local

Cuenta del dueño ──► LECTOR (fase 3+, Telethon: solo lectura + carpetas)
   · le escribe alguien con bienvenida   → carpeta DD.MM
   · el dueño le envía un enlace de venta → carpeta free send
   · limpieza nocturna de carpetas

Base de datos local ──► Google Sheet privado (fase 2) y resúmenes por Telegram
```
El lector **nunca envía mensajes** desde la cuenta del dueño: el código no
tendrá esa función. Tampoco marca chats como leídos.

## Fases
Cada fase necesita el visto bueno del dueño, y las de producción (5 y 6)
uno explícito aparte.

1. **Bot en el canal de prueba**: bienvenida, aceptación, memoria de quién
   la recibió, avisos, resúmenes. La cuenta principal del dueño hace de
   dueño, igual que en producción (canal de prueba suyo, avisos y botones a
   @Dronwhite), y la secundaria hace de cliente: hacen falta dos cuentas
   porque quien crea un canal no puede pedir unirse a él. ✅ *Instalado y
   probado en la VM (2026-10-14).*
2. **Google Sheet**: pestañas `Usuarios`, `Eventos`, `Resumen diario` y
   `Tipos de mensaje`; volcado automático desde la VM cada 10 min con la
   cuenta de servicio de picks. ✅ *Funcionando en la VM con la hoja de
   pruebas (2026-10-15). La instancia real tendrá su propia hoja.*
3. **Carpetas**: `DD.MM`, `free send`, filtro del canal principal, rotación
   de 5 días. Se prueban **con la cuenta principal del dueño, en
   simulación**, conectada a la instancia `prueba` (decisión del dueño,
   2026-10-15: ya tiene ahí sus carpetas de días). Allí solo cuenta como
   cliente la secundaria; sus clientes reales se ignoran. En simulación el
   candado no deja ni pedir cambios de carpetas. ✅ *Probada en simulación
   con la cuenta del dueño el 2026-10-18: carpeta del día (y cambio desde
   una carpeta antigua), rotación, enlace del canal principal ignorado y
   «free send». El modo real es la fase 6.*
4. **Lectura del histórico de la cuenta real** (solo lectura): bienvenidas
   manuales antiguas y respuestas pasadas, para no repetir bienvenidas y
   comparar manual frente a bot. ✅ *Hecha en la cuenta real el
   2026-10-18, con su visto bueno: 994 personas con bienvenida manual (a
   ninguna se le repetirá la del bot), 319 contestaron y 255 recibieron
   enlace de venta. El canal principal quedó guardado en la instancia
   real.*
5. **Producción del bot**: el bot real pasa a administrar PREMIER GALGOS.
   Justo antes, el dueño acepta a mano las solicitudes que haya pendientes
   (el bot no ve las anteriores a su activación).
6. **Producción de carpetas**: el lector pasa a la cuenta real.

## Riesgos y cómo se cubren
- **Bot caído más de 5 min**: quien solicite en ese rato entra sin
  bienvenida (se acepta igual al volver). systemd lo reinicia solo y avisa
  al dueño con el número de afectados.
- **Sesión de la cuenta del dueño** (fases 3-6): equivale a acceso total.
  Solo en la VM, archivo con permisos restringidos, nunca en el repo. Se ve
  y se puede cerrar en Telegram → Ajustes → Dispositivos. Se recomienda
  activar la verificación en dos pasos.
- **Uso de la cuenta desde un programa**: riesgo bajo al limitarse a leer y
  mover carpetas, con poca frecuencia.
- **Texto ya escrito en el botón**: las apps antiguas de Telegram lo
  ignoran (se abre el chat vacío). Se comprueba en las pruebas.

## Pendiente para más adelante
- Que el bot conteste por su cuenta a preguntas escritas (hoy solo hay el
  menú de dudas frecuentes).
