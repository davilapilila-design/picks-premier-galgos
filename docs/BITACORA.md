# Bitácora del proyecto

Registro de cambios significativos (ver regla en `CLAUDE.md`).
Entradas más recientes arriba.

## 2026-10-30 — Captación: registro del canal con el enlace escrito de otra forma

- Las 27 ventas del 29/10 salían sin canal: su enlace aún no se había leído
  y el registro del canal guardaba las entradas con otro texto de enlace
  (las mismas 30 personas, al segundo, que la lista de Telegram del enlace
  de la venta; solo pasa en 1 de 59 canales).
- Ahora un enlace del registro cuenta como el de la venta si trae entradas
  idénticas a la lista de un enlace de ese canal; uno distinto (p. ej. de
  regalo) sigue sin contar.
- Comprobado con las ventas conocidas: el orden en que se paga y se entra
  coincide en el 91 % de los pares a menos de 60 s (no basta para emparejar
  por orden); retraso pago→entrada: mediana 7 s, p90 32 s.
- Commits: (este)

## 2026-10-30 — Captación: copia diaria a Google Drive de lo que usa el cruce

- Lo pidió el dueño: Telegram borra el registro de los canales a las 48 h y
  la lista de «quién se unió» pierde a quien se va; todo eso solo estaba en
  la base de la VM (que no entraba en ninguna copia).
- `copia.py` saca la base entera (copia coherente con `backup`), un CSV por
  tabla del cruce (ventas, enlaces, quién se unió, registro, miembros,
  personas, chats, manuales, usuarios) con las fechas también en hora de
  España, el resultado del cruce y un LEEME. `deploy/copia-drive.sh` lo sube
  con rclone (de root) a `CAPTACION_COPIA_DRIVE/<instancia>/<día>` y a
  `.../ultima`; timer `captacion-copia@` a las 04:45. La sesión de Telegram
  no está en la base y nunca se sube.
- Commits: (este)

## 2026-10-30 — Captación: por nombre automático y registro del canal en el cruce

- El cruce usaba solo la lista de «quién se unió» de cada enlace (solo trae
  a quien sigue dentro) e ignoraba el registro del canal que guarda el
  lector (48 h, trae también a quien se fue): ahora junta las dos fuentes.
  Había 47 entradas de gente que luego se salió.
- `nombres.py`: correo ↔ persona por @usuario o nombre (apellido completo +
  nombre o sus 4 primeras letras; nunca un nombre suelto; si falta algún
  apellido del nombre de Telegram, solo con la hora). Lo aplica el cruce
  («por_nombre») si una sola persona casa mejor, manda sobre un cruce por
  hora suelto pero no si la hora dice otra persona ≥2 veces. Salen en
  «Correos por identificar» con 🤖 para revisarlos; «no» en la columna G lo
  bloquea.
- Nombres: canales de venta, usuarios del bot y chats privados del dueño,
  que el lector apunta una vez al día (migración 10: `personas_chat`, solo
  id, nombre y @usuario; con GetDialogs, que ya estaba permitido; autorizado
  por el dueño hoy).
- Commits: (este)

## 2026-10-30 — Captación: correos por nombre (a mano, con el visto bueno del dueño)

- Sin cambios de código. Un comprador grande no salía por ningún cruce: no
  está en ningún canal (se sale tras cada carrera) y Telegram solo enseña a
  quien sigue dentro. Su id salió buscando, en modo solo lectura («historico»,
  sin permisos nuevos), un mensaje suyo que dio el dueño. Antes le asigné por
  deducción el id de otra persona con el mismo nombre de pila: deshecho; no
  asignar nunca un id sin verificarlo en Telegram.
- Se leyeron (solo lectura) los nombres de los chats privados del dueño y se
  compararon con los correos pendientes: apellido completo + nombre (o sus 4
  primeras letras), o el @usuario dentro del correo; nunca un nombre suelto.
  El dueño revisó la lista y se apuntaron 29 correos en «Correos por
  identificar» (dos corrigen cruces míos: uno de eliminación que daba 31
  compras a otra persona). Archivo temporal de nombres borrado al acabar.
- Queda: 1.281 de 2.601 ventas con persona (78 de 235 correos).

## 2026-10-29 — Captación: eliminación en compras a la vez y correos que dice el dueño

- Eliminación (`pagos._eliminar`, por vueltas con el cruce por correo): en
  una venta dudosa se quitan de los que entraron a esa hora los que ya se
  sabe que pagaron ese canal con otra venta; si queda uno solo y no es
  posible para otra venta del canal, es «por eliminación» y cuenta como
  segura para su correo. Solo vale si su correo acaba siendo de esa persona
  (si no, el comprador se fue y quedó otro: un cliente que compra mucho en
  las avalanchas salía así en varios correos distintos).
- Pestaña nueva «Correos por identificar»: los correos con compras sin
  persona, de más a menos compras, con quién pudo ser (los que quedan
  posibles en sus dudosas) y una columna donde el dueño escribe el @usuario
  o id. Se lee antes de escribir el Sheet (migración 9:
  `pagos_correos_manual`), manda sobre el cruce y vaciar la celda lo quita.
- Con los datos reales: de 922 a 1.038 ventas con persona (52 de 235 correos).
- Commits: 3535210

## 2026-10-29 — Captación: «por correo» por mayoría y sin mayúsculas

- Con los 147 enlaces leídos, «por correo» bajaba en vez de subir: el
  comprador con más compras pagó unas veces con el correo en mayúscula y
  otras en minúscula (salía como persona con dos correos y no se propagaba),
  y un cruce suelto falso en contra bloqueaba correos con decenas de cruces
  buenos.
- Ahora: el correo se compara en minúsculas y sin espacios (también en la
  pestaña de clientes); un correo es de una persona si ≥2 ventas emparejadas
  apuntan a ella y son ≥80 % de las del correo (o una sola, si esa persona no
  sale con otro correo); y como nadie paga dos veces el mismo canal, un correo
  que compró canales que la persona ya pagó con otro suyo es otro comprador
  (un amigo que compra a la vez) y esos cruces pasan a dudosos.
- Con los datos reales: de 565 a 922 ventas con persona (50 personas).
- Commits: 01370b2

## 2026-10-29 — Captación: la lectura de enlaces sigue por donde iba

- La primera pasada con todos los enlaces leyó 51 de 147: Telegram pidió
  esperar ~50 min (más que el máximo de 30) y el programa acabó con error,
  y al relanzarlo habría empezado otra vez por el primero.
- Ahora sin trozo de enlace solo lee los pendientes (nunca leídos, o leídos
  antes de acabar la ventana de su última venta); con trozo, lee ese aunque
  ya esté leído. Si Telegram pide esperar demasiado, para limpio con código 3
  y lo leído queda guardado.
- Commits: (este)

## 2026-10-29 — Captación: cruce venta↔persona más estricto

- Prueba con un canal de agosto: el doble de ventas que de personas en la
  lista de quién se unió con el enlace, porque Telegram solo trae a quien
  sigue dentro. Si el comprador se fue, la venta se emparejaba con otro que
  entró a esa hora, y «por correo» extendía el error a todas sus compras
  (una persona salía con 3 correos; solo uno era suyo).
- Ahora: hay que entrar DESPUÉS de pagar (30 s de margen por los relojes);
  una entrada que reclaman dos ventas deja ambas dudosas; y no se propaga por
  correo si la persona sale emparejada con más de un correo.
- Commits: (este)

## 2026-10-29 — Captación: quién se unió con cada enlace de las ventas

- Para emparejar también el historial (canales antiguos, sin registro de
  entradas): Telegram guarda por enlace de invitación quién se unió y a qué
  hora, y overoption da el enlace exacto de cada producto. Permiso nuevo en
  el guardia, solo lectura y autorizado por el dueño hoy:
  `messages.GetChatInviteImportersRequest`, solo en el modo «invitaciones».
- `invitaciones.py` (modo a mano `lector.sh real invitaciones [trozo del
  enlace]`, con el lector parado) guarda canal e invitados (migración 8:
  `pagos_enlaces`, `pagos_invitados`; se queda la primera vez que se unió).
  El cruce usa los que entraron con el enlace de la venta si se conocen; si
  no, las entradas al canal, como antes. Primero se prueba con un canal.
- Commits: (este)

## 2026-10-29 — Captación: las compras se asignan también por correo

- Si una venta se empareja con una persona de Telegram (por enlace + hora),
  las demás compras con ese MISMO correo pasan a ser de esa persona (estado
  "por correo"), aunque sean de canales antiguos sin registro de entradas o
  hayan salido dudosas. Si un correo sale con dos personas distintas, no se
  propaga. Con los datos reales: de 11 ventas con persona a 355 (9 personas,
  7.680 € recibidos), sin ningún conflicto.
- "Canales que pagó"/"€ pagado" de Personas cuentan también estas compras;
  la pestaña Clientes gana la columna "Persona de Telegram".
- Commits: (este)

## 2026-10-29 — Captación: ventas de overoption cruzadas con las entradas

- El dueño quiere saber quién ha PAGADO cada canal. overoption (overoption.io)
  no tiene exportar, pero su web usa una API JSON (`api.overoption.io`) que,
  con su sesión, devuelve todas sus transacciones. Reconocimiento previo de la
  parte pública (sin cuenta) + sondeo de solo lectura con su cuenta: login
  correo+contraseña (sin 2FA ni captcha), `GET /transactions` devuelve todas
  las ventas (correo, fecha/hora UTC, importe, moneda, neto, método, estado,
  `content_uid`), y `GET /content/<uid>` da el enlace de Telegram del canal
  (`final_content`), que coincide con el `enlace` que guarda `ventas_*`. Sus
  condiciones no prohíben leer la propia cuenta por programa.
- `pagos.py` (SOLO LECTURA: el único POST es el login; todo lo demás GET).
  Baja las ventas, resuelve el enlace de cada producto (con caché en
  `pagos_contenidos`) y lo guarda (migración 7: `pagos_overoption`). Cruce
  venta↔persona por enlace (o por nombre de canal si es único) + hora de
  entrada ±3 min: emparejada / dudosa (varios) / sin emparejar / canal no
  identificado. El cruce se recalcula al copiar al Sheet, así mejora según
  entran más movimientos de Telegram.
- Pestañas nuevas del Sheet: «Canales de venta · Pagos» (una fila por venta,
  con € recibido y la persona o el motivo), «Clientes (por correo)» (compras,
  total pagado/recibido, nº de canales; no necesita Telegram) y dos columnas
  en «… · Personas» (canales que pagó y € pagado). Aviso honesto al dueño: el
  registro de entradas empezó el 28/10, así que las ventas viejas saldrán
  mayormente «sin emparejar»; los importes y la vista por correo sí son 100%.
- Credenciales de overoption solo en la VM (`/etc/premier-captacion/overoption.env`,
  root), nunca en el repo (público) ni en el chat; systemd se las pasa al
  servicio. Nuevo `captacion-pagos@<instancia>` (timer 3 veces al día) y
  `configurar.sh <instancia> overoption`. Tests: `test_pagos.py`, `test_cruce.py`.

## 2026-10-28 — Captación: quién entra y sale de los canales de venta

- El dueño quiere saber a cuántos canales de venta ha entrado cada persona.
  El enlace de un canal es el mismo para la venta (payoption lo manda por
  correo al pagar), la gratuita y las compensaciones: Telegram no dice quién
  pagó, pero restando la gratuita (ya apuntada) quedan compras o
  compensaciones; luego se podrá cruzar con un CSV de payoption.
- `ventas.py` (solo lectura, autorizado por el dueño: `GetParticipants` y
  `GetAdminLog`): lee la lista de miembros de cada canal de «CH Venta» con su
  fecha de entrada (solo quien sigue dentro) y el registro de entradas y
  salidas, que Telegram guarda 48 h. El lector lo vuelve a leer cada 4 h y lo
  va guardando (migración 5: `ventas_*`). Modo a mano
  `lector.sh real ventas [Sheet]` para la primera lectura completa.
- Pestañas del Sheet «Canales de venta · Personas» (una fila por persona:
  canales, fechas, canal de su gratuita, otros canales) y «… · Entradas y
  salidas»; la copia periódica al Sheet las mantiene al día.
- Solo los canales desde «Premier Galgos Debut» (22/07), por fecha de
  creación; los nuevos que se añadan a la carpeta entran solos.
- Revisión de la primera lectura (126 canales, 198 personas, 106
  movimientos en 48 h): salía el propio dueño (en los 126) y el canal de
  pruebas del bot. Se quitan los administradores de cada canal y el canal de
  pruebas; la lista de miembros de cada canal se sustituye entera en cada
  lectura completa, y se borra lo de canales que ya no cuentan.
- El equipo (el dueño y sus socios) no se quita: el dueño prefiere que se
  saque todo y que salgan marcados («Equipo», primera columna; al final de
  la lista). Cuentan como equipo los administradores de cada canal y los que
  se pongan con `configurar.sh real equipo "@uno,@dos"` (CAPTACION_EQUIPO,
  solo en la VM, no en el repositorio). Migración 6: `ventas_personas.admin`.
- Commits: 4d3df42

## 2026-10-28 — Captación: aviso cuando alguien vuelve a entrar (en vez del de cada gratuita)

- El dueño prefiere no recibir un aviso por cada gratuita (se llena el chat)
  y sí cuando alguien vuelve a pedir entrar al canal: suelen ser los que
  intentan conseguir otra gratuita. Al aceptar a alguien que ya estaba en el
  canal, ya tuvo la gratuita o ya había pasado por aquí, el bot le da la
  bienvenida sin gratuita, le acepta y después avisa: «🔁 X ha vuelto a
  entrar: ya tuvo la gratuita el dd/mm («canal»)…», con «Ver más info».
- Commits: 9fbdb4f

## 2026-10-28 — Captación: quien ya no puede tener la gratuita va a «free send», y aviso de cada gratuita

- Un cliente (ya con la gratuita) borró el chat: Telegram lo sacó de «free
  send» y el lector, al volver a escribir, no lo devolvía (daba por hecho que
  seguía dentro). Decisión del dueño: cuando escribe alguien que ya no puede
  recibir la gratuita (ya la tuvo, o ya estaba en el canal / volvió), va a
  «free send» si no está, en vez de a la carpeta del día. Incluye a los del
  canal sin bienvenida apuntada. Los nuevos siguen yendo al día; los
  desconocidos no se tocan. Mismo límite de 90 (salen los más antiguos).
- Aviso al dueño en el bot cada vez que se da una gratuita por primera vez
  («🎁 Gratuita a X («canal»)» con «Ver más info»), también con el lector en
  real (antes solo quedaba en el registro y en el resumen). Quitado el mismo
  día a petición del dueño (llenaba el chat de avisos): ver la entrada
  siguiente.
- Commits: 60b7058

## 2026-10-27 — Captación: /arrancar y /pausar mueven también el lector de carpetas

- El dueño quiere parar y arrancar todo desde el bot. `/arrancar` pone el bot
  en marcha y el lector de carpetas en REAL; `/pausar` pasa los dos a
  simulación. `/estado` dice el modo del lector.
- Cómo: el bot guarda `lector_modo` en la base de datos (compartida); el
  lector lo mira cada minuto y, si cambia, se reinicia (systemd, 30 s) con el
  modo nuevo. Si nunca se ha usado, manda `CAPTACION_LECTOR_SIMULAR` del .env.
  En la instancia `prueba` se ignora (allí el lector nunca pasa a real).
- Al pasar a real, el lector hace de verdad lo que avisaba en simulación,
  incluido borrar carpetas de días antiguos (los chats no se borran).
  Decisión del dueño (fase 6) tomada aquí.
- Commits: 54174fb

## 2026-10-24 — Captación: cuentas de prueba (/probador) que reciben respuesta en simulación

- El dueño quiere probar en el bot real, en simulación, cómo responde y las
  dudas, con una cuenta secundaria. Opción elegida por él: solo cuentas que
  apunte él (`/probador @cuenta`, `/probador quitar @cuenta`, `/probador` para
  ver la lista; también por id), no cualquiera que escriba al bot.
- A esas cuentas el bot les contesta en simulación como si estuviera
  funcionando (respuesta, botones y dudas). Sus solicitudes de entrada siguen
  simuladas: ni bienvenida ni aceptación. A nadie más le contesta.
- Commits: b67c8ad

## 2026-10-24 — Captación: en cada duda, primero los botones para pedir la gratuita

- El dueño vio confuso que en las pantallas de dudas se mezclaran los
  botones de navegar con «Ya he apostado» / «Es mi primera vez». Ahora esos
  dos van los primeros y en una sola fila (o «Escríbeme» si ya tiene la
  gratuita); debajo, los de moverse por las dudas y «Otras dudas».
- Final sin gratuita más directo: «¿Aún no tienes tu apuesta de regalo? Dime
  si ya has apostado o es tu primera vez 👇 y te regalo una apuesta de pago…».
- Commits: af46886

## 2026-10-24 — Captación: mensaje de dudas justo después de la bienvenida con gratuita

- Tras la bienvenida con gratuita, el bot envía un segundo mensaje («¿Tienes
  alguna duda? Aquí tienes las más frecuentes») con el menú de temas, y
  después acepta. Decisión del dueño: los dos seguidos, sin esperar 2-3 min,
  porque Telegram solo deja escribir mientras la solicitud está pendiente y
  esperar retrasaría la entrada al canal.
- Los temas se abren cambiando ese mismo mensaje (ya aceptado, el bot no
  puede enviarle mensajes nuevos si nunca le escribió). Por lo mismo, el
  botón «Dudas frecuentes» de la bienvenida sin gratuita, si no puede enviar
  el menú, lo pone en el mismo mensaje.
- Si el mensaje de dudas falla, la solicitud se acepta igual. Texto editable
  con /textos («Mensaje de dudas tras la bienvenida»).
- Commits: f0a856a

## 2026-10-24 — Captación: instancia real configurada y prueba apagada

- Bot real en simulación con propietario, Sheet propio y la memoria ya cargada
  (suscriptores del canal, gratuitas e históricos de bienvenidas).
- Instancia `prueba` apagada (servicios y temporizadores desactivados) y
  borrada su sesión de Telethon de la cuenta del dueño; se conservan su
  configuración y su base de datos por si hay que reactivarla
  (`instalar.sh prueba`). Mientras tanto, los cambios se prueban en el bot real
  con `/pausar` (simulación). Decisión del dueño.
- Commits: (solo documentación)

## 2026-10-24 — Captación: modo simulación del bot para ponerlo en el canal real sin que actúe
- **Qué**: el dueño quiere tener ya el bot definitivo en PREMIER GALGOS
  pero solo mirando: que le cuente lo que haría (bienvenida con o sin
  gratuita, carpetas, avisos de gratuita repetida) sin escribir a nadie ni
  aceptar. Nuevo `CAPTACION_BOT_SIMULAR=1`: en las solicitudes no hay
  bienvenida ni aceptación (evento `solicitud_simulada`) y el dueño recibe
  «🧪 Simulación (no he hecho nada): a X le enviaría la bienvenida CON/SIN
  gratuita (motivo) y le aceptaría» con «🔎 Ver más info»; no contesta a
  clientes; las órdenes del dueño funcionan. `instalar.sh real` lo deja en
  simulación si no está puesto; `configurar.sh real bot real|simulacion`.
- Nombre acordado: «PREMIER GALGOS» (@PremierGalgosBienvenida_bot o
  similar), logo del canal en colores invertidos; creado por el dueño en
  BotFather. Mismos textos que el de prueba (se copian los de /textos).
- **Órdenes en el propio bot** (pedido del dueño): `/pausar` ahora pasa a
  simulación (antes solo paraba en silencio) y `/arrancar` (o `/reanudar`)
  lo pone a actuar. La instancia real empieza en simulación hasta el primer
  `/arrancar` (se guarda en la base de datos y sobrevive a reinicios).
  `/estado` dice también cuántos hay en la lista de suscriptores (`e7788f3`).
- También: la ficha de /gratuita dice si estaba en el canal y si volvió a
  pedir entrar (`182158f`).
- Commits: (este commit)

## 2026-10-24 — Captación: el aviso de gratuita repetida también salta cuando la piden con sus palabras
- **Qué**: hasta ahora solo saltaba con la frase exacta de los botones. Con
  lo visto en los chats de clientes, ahora también con «gratis / gratuita /
  regalo / free» junto a «apuesta / me das / me pasas / dame / sigue /
  vigente» («¿me darás una gratis?», «¿lo de la apuesta gratis sigue
  vigente?»), salvo si el mensaje habla de compensación, garantía, packs o
  recuperar (las compensaciones las da el dueño por los canales). Mismas
  reglas: solo si ya tuvo la gratuita o ya estaba en el canal, una vez al
  día por persona, solo al dueño. Aprobado por el dueño.
- Comprobado contra los chats reales: tras la gratuita habría avisado de 16
  clientes (22 mensajes), casi todos pidiéndola de nuevo o preguntando por
  apuestas gratis.
- Commits: (este commit)

## 2026-10-24 — Captación: dudas frecuentes rehechas a partir de los chats con clientes
- **Análisis de los chats** (CSV de la pestaña «Análisis · Chats clientes»,
  procesado en local, sin subir nada al repo): desde el 22/07 escribieron
  346 de 1075 clientes (32 %), 274 recibieron la gratuita (79 %); 3 de cada
  4 se declaran novatos. Lo que más preguntan y no estaba en las dudas:
  precio y cómo se paga, cómo apostar a galgos y abrir cuenta, horarios,
  cuenta limitada, qué es gratis y qué de pago. El truco de salir y entrar
  no deja rastro en los chats (solo en las solicitudes, que ya vigila el
  bot). Las 11 apuestas de canales que faltaban en el grupo de picks: el
  dueño añadió 6 a mano (2 descartadas, 2 falsos positivos).
- **Nuevo flujo** (pedido por el dueño: sencillo, poco texto, para
  novatos): menú de 4 botones. «🆕 Empiezo de cero» en 3 pasos encadenados
  (abre cuenta → cuánto apostar → haz la apuesta; dentro, otras casas y
  gemelas), «⏰ ¿Cuándo llegan?», «📦 Precios y garantía» y «🆘 Tengo un
  problema» (cuenta limitada, cuota que baja). Unidades y bank se juntan;
  apuesta a ganador va en el paso 3. Datos del dueño: bank 400-500 € y 10 €
  por unidad; precios 1 galgo 15-25 €, 2 galgos 25-35 €, 3 galgos 35-45 €;
  Bizum en el enlace de pago; «todas son de pago»; horarios sin canódromos;
  consejos sobre límites sacados de sus propios mensajes. Horarios por
  franjas: mañanas sobre las 11:00, tardes entre las 15:00 y las 18:45.
- Pruebas: 198, pasan en Python 3.9, 3.12 y 3.13.
- Commits: `f220990`, `2d259e4`, `0de0024`, `9ba0127`, `3d8b857`, `2b0c9b3`
- **Corrección (2026-10-24)**: el dueño dice que la gemela de Star Pelaw del
  05/09 sí estaba en el grupo (reenvía tal cual). Fallo del emparejado: un
  mensaje reenviado al grupo solo contaba para el mensaje exacto del que
  venía, y si la misma apuesta estaba en dos canales la otra copia salía
  como «falta». Ahora vale cualquier mensaje del grupo de un día cercano con
  el mismo texto, o con las mismas horas y trampas (también las de
  «3/4 4/3»), y la pestaña añade lo que había en el grupo a esa hora para
  revisarlo a mano. Nueva opción `analisis <Sheet> canales` (sin releer los
  chats). Tras la corrección quedan 5, todas descartadas por el dueño o
  avisos que no son apuestas.
- **Todas las apuestas** (pedido del dueño): pestaña «Análisis · Todas las
  apuestas» con cada apuesta de los canales desde el 22/07 desglosada según
  el formato de sus mensajes (tipo, carrera/s «HH:MM Canódromo», galgo/s
  «T5 Nombre» o combinaciones de gemela, cuota, stake), si el mensaje
  exacto está en el grupo de picks (reenviado o mismo texto; «parecido» si
  solo coinciden hora y galgo) y el enlace a cada mensaje.

## 2026-10-24 — Captación: análisis puntual de canales de venta y chats con clientes
- **Qué**: el dueño pide (1) saber qué apuestas de los canales de venta
  (desde el 22/07, carpeta «ch ventas» de su cuenta) no están en el grupo
  «Picks Premier Galgos», que es el que alimenta la hoja del proyecto de
  picks, para el seguimiento de apuestas; y (2) leer los chats con
  clientes para buscar patrones (cómo piden la gratuita, qué preguntan) y
  mejorar las dudas frecuentes. Las compensaciones las da por los canales,
  no por privado.
- **Cómo**: modo `analisis` del lector (`analisis.py`), solo lectura (modo
  `historico` del candado, sin ampliarlo). Una apuesta = mensaje de canal
  con hora de carrera y cuota/stake (o gemela/trío); está en el grupo si
  allí está reenviada o hay un mensaje de un día cercano con las mismas
  horas. Las fotos sin texto se cuentan aparte para revisarlas a mano.
  Chats: lo que escriben cliente y dueño, con la etapa (antes/después de
  la gratuita) y si es recurrente; clientes como C0001… Se escribe en
  pestañas «Análisis · …» del Sheet de pruebas de captación (las demás
  pestañas no se tocan), que puedo leer con el conector de Google Drive.
- Pruebas: 198, pasan en Python 3.9, 3.12 y 3.13.
- Commits: (este commit)

## 2026-10-23 — Captación: bienvenida sin gratuita a quien ya estaba en el canal o vuelve
- **Qué**: el dueño ha visto que algunos salen y vuelven a entrar al canal
  (borrando mensajes) para conseguir otra gratuita. Pide no ofrecer la
  gratuita a quien ya está en el canal principal (unos 1798) y que, si
  salen y vuelven, el bot les mande una bienvenida sin gratuita, sin que se
  note, pero que él lo distinga.
- **Cómo**: tabla nueva `miembros_canal` (solo ids) y columna
  `usuarios.recurrente_ts` (migración 4). Modo nuevo del lector
  `suscriptores`, solo lectura, que lee la lista del canal (también por
  búsquedas, por si Telegram no la da entera) y dice cuántos consiguió.
  Para ello el candado tiene un modo `suscriptores` con
  `channels.GetParticipantsRequest` (autorizado por el dueño en el chat el
  2026-10-23; ningún otro modo lo tiene). Al pedir entrar quien ya estaba,
  ya recibió bienvenida o ya tuvo la gratuita: bienvenida «Buenas!
  Bienvenido a PREMIER GALGOS… aquí tienes las dudas más frecuentes… y si
  necesitas algo concreto, escríbeme» (tipo `bot_recurrente`, cambiable con
  /textos), botones «📚 Dudas frecuentes» y «✉️ Escríbeme» con «Hola, tengo
  una consulta» ya escrito («consulta» en vez de «duda»: lo pidió el dueño
  para reconocerlos). Al escribir al bot o en las dudas tampoco se les
  ofrece la gratuita. Antes, a quien volvía no se le enviaba nada.
- El dueño descartó «Bienvenido de nuevo» (demasiado intrusivo).
- Pruebas: 188, pasan en Python 3.9, 3.12 y 3.13.
- Commits: `b9002b1`

## 2026-10-23 — Captación: aviso si alguien pide la gratuita y ya la tuvo o ya estaba en el canal
- **Qué**: el dueño pregunta qué pasa si alguien copia la frase de los
  botones de la gratuita. El sistema reconoce a cada persona por su id de
  Telegram, no por lo que escribe; ahora además el lector avisa por el bot
  («⚠️ … te ha escrito pidiendo la gratuita, pero ya la tuvo el DD/MM
  («canal»)» o «… ya estaba en el canal») cuando quien escribe esa frase ya
  tuvo la gratuita o ya estaba en el canal (`db.estado_oferta` distinto de
  «nueva»). Una vez al día por persona (evento `aviso_gratuita_repetida`) y
  solo por mensajes recientes. Aprobado por el dueño, también para quien ya
  estaba en el canal.
- Probado por el dueño en el bot de prueba. A petición suya, el aviso lleva
  el botón «🔎 Ver más info», que enseña la ficha completa (la de
  /gratuita).
- Lista de suscriptores leída en la real: 1673 de 1798 (93 %; Telegram da
  200 de golpe, el resto sale por búsquedas).
- Pruebas: 191, pasan en Python 3.9, 3.12 y 3.13.
- Commits: `f3ba322`, `88d6561`

## 2026-10-21 — Captación: el lector apunta en directo las bienvenidas que el dueño da a mano
- **Qué**: el dueño buscó con la consulta a un cliente al que dio la
  gratuita hoy y no salía: la instancia real solo tenía el histórico del
  18/10 y su lector no estaba encendido. Quiere dejar la lectura en marcha
  mientras sigue aceptando a mano. El lector solo seguía a quien ya tenía
  bienvenida apuntada; ahora, con `CAPTACION_BIENVENIDAS_MANUALES=1`, al
  ver que el dueño envía su bienvenida manual (misma detección que el
  histórico) apunta a esa persona y la sigue (respuesta, enlace de venta).
  Al arrancar también repasa los chats con movimiento aunque no estén aún
  en el embudo. Solo en la instancia real: `configurar.sh` no lo deja
  poner en la de prueba (allí sus clientes reales se ignoran).
- **Plan aprobado por el dueño**: actualizar, activarlo en real, repetir el
  histórico en real (cubre desde el 18/10) y encender `captacion-lector@real`
  en simulación. Sin bot real no hay avisos.
- Pruebas: 179, pasan en Python 3.9, 3.12 y 3.13.
- Hecho en la VM el mismo día: histórico repetido (1059 bienvenidas a mano,
  341 respuestas, 273 con enlace de venta) y `captacion-lector@real` en
  marcha. Un cliente al que se dio la gratuita el 20/10 no salía: borró el
  chat antes de encender la lectura. Para esos casos sueltos, nuevo modo
  `lector.sh real apuntar-gratuita @usuario "bienvenida" "gratuita" enlace`
  (busca a la persona por su @, solo lectura; el evento queda marcado como
  apuntado a mano; el canal sale de los enlaces ya conocidos).
- Commits: `bd47b44`, `8413e3f`

## 2026-10-19 — Captación: consultar en el bot a quién se le dio la gratuita (/gratuita)
- **Qué**: el dueño quiere que conste que, aunque se borren los mensajes,
  se sigue sabiendo a quién se le dio la apuesta gratuita, y poder
  consultarlo. Nueva orden del bot, solo para él: `/gratuita @usuario` o
  parte del nombre (sin importar mayúsculas ni tildes; también el id).
  Responde con la ficha: bienvenida (cuándo y cuál), primer mensaje y
  botón, y **cuándo se le dio la gratuita, a qué canal de venta y con qué
  enlace** (el enlace, pedido por el dueño al probarlo), más los enlaces de
  venta posteriores. Con varias coincidencias, botones para
  elegir (hasta 8; las de gratuita primero y con 🎁).
- **Por qué vale aunque borren los mensajes**: el lector (y la fase 4 con
  los chats antiguos) lo apunta en la base de datos al ver el enlace; la
  consulta solo lee de ahí (`consulta.py`). Para la gente nueva hace falta
  el lector en marcha en la instancia real.
- Pruebas: 178, pasan en Python 3.9, 3.12 y 3.13. Explicado también en el
  PDF para los socios del dueño (fuera del repo). Probado por el dueño en
  el bot de prueba.
- Commits: `095b3d9`, `89f521b`

## 2026-10-19 — Captación: textos de las dudas frecuentes con la redacción del dueño
- **Qué**: el dueño pasó los 12 textos de las dudas frecuentes (las dos
  respuestas a quien escribe al bot, el menú, los 7 temas y los dos finales)
  por otra sesión que tiene su estilo de redacción, y me los devolvió.
  Quedan como textos de partida en `mensajes.py`. Mismos datos, cifras,
  casas, canódromos y botones; cambian la redacción, algunas negritas
  (las casas en las listas, las cifras de los ejemplos, «Mi consejo:»,
  «Atento:») y algún emoji al final (✅, 📈, 💙). La bienvenida no cambia
  (sigue siendo `bot_b_v1`).
- **Por qué en el código y no con /textos**: lo que se guarda con /textos
  se queda en la instancia donde se guarda; así el bot real, que aún no
  existe, empieza ya con estos textos. Donde se haya guardado algún texto
  con /textos, sigue mandando ese (se vuelve a estos con «♻️ Volver al
  original»).
- Comprobado con un script que los 12 quedan idénticos al archivo del
  dueño, negritas incluidas. Pruebas: 169, pasan en Python 3.9, 3.12 y
  3.13.
- Commits: `c588ccf`

## 2026-10-19 — Captación: dudas frecuentes en el bot y cambiar textos desde el bot (/textos)
- **Qué**: el dueño quiere, antes de crear el bot real, que el bot resuelva
  las dudas de siempre, y poder cambiar él los textos sin pasar por mí.
  Plan y textos acordados con él tema por tema (casas, otras casas y
  canódromos, unidades, bank y stakes, apuesta a ganador, gemelas y tríos,
  garantía de los packs). Investigado para él qué canódromos son de cada
  red: PGR (Arena Racing Company + Entain, desde 2024: Central Park,
  Nottingham, Hove…) y SIS (en Reino Unido solo Doncaster, Harlow, Star
  Pelaw y Valley, además de los irlandeses). No hay web oficial con la
  lista, así que en el bot no va enlace.
- **Dudas frecuentes** (`mensajes.FAQ`): la respuesta a quien escribe al
  bot lleva «📚 Dudas frecuentes». El menú sale en un mensaje nuevo y los
  temas se ven en ese mismo mensaje (se edita), con «⬅️ Otras dudas».
  Cada respuesta acaba invitando a escribir al dueño: a quien aún no tiene
  la apuesta de regalo (sin enlace de venta) con los dos botones de la
  bienvenida, y a quien ya la tiene con «✉️ Escríbeme» y «Hola, tengo una
  duda sobre …» ya escrito. A este último tampoco se le repite la pregunta
  de la bienvenida en la respuesta del bot (pedido del dueño). Se apunta
  qué temas mira cada uno (evento «faq»; en el resumen diario, cuántas
  personas). `/dudas` enseña al dueño el menú como lo ve un cliente.
- **Cambiar textos** (`/textos`, solo el dueño; `textos.py` y tabla nueva
  `textos`, migración 3): elige el texto, el bot le manda el actual para
  copiarlo, él manda el nuevo (la negrita de Telegram se pasa a negrita
  Unicode) y ve una vista previa con sus botones antes de ✅ Guardar.
  Puede volver al anterior o al original; caduca a la media hora. Cada
  bienvenida distinta es un tipo nuevo (bot_b_v2, v3…; si repite un texto,
  recupera su tipo), y la pestaña «Tipos de mensaje» y los resúmenes las
  muestran con su fecha. Los botones de la bienvenida no se cambian desde
  aquí. Cada instancia guarda sus textos: lo del bot de prueba no pasa al
  real.
- `negrita()` ahora también pone en negrita las letras con tilde (letra en
  negrita + tilde suelta), para «𝗧𝗿𝗶́𝗼» o «𝗣𝗮𝘀𝘁𝗼́𝗻». Los textos de antes no
  cambian.
- Pruebas: 169, pasan en Python 3.9, 3.12 y 3.13 (las nuevas, comprobado
  que fallan si se rompe lo que prueban). Conversación simulada entera
  (respuesta, menú, tema, /textos, vista previa, guardar) revisada a mano.
- Commits: `f8e25dd`

## 2026-10-19 — Captación: freno de emergencia en el bot (/pausar y /reanudar)
- **Qué**: el dueño pide poder parar rápido, desde el propio bot, que acepte
  a la gente «por si falla algo». Nuevas órdenes, solo para el dueño:
  - `/pausar`: deja de enviar bienvenidas y de aceptar al momento. Las
    solicitudes que lleguen se apuntan («Solicitud sin atender (bot en
    pausa)») y se quedan pendientes en el canal para que las acepte a mano;
    avisa de la primera y no de las siguientes. Esas personas no quedan
    como «con bienvenida»: si luego entran por el bot, la recibirán.
  - `/reanudar`: vuelve a aceptar y dice cuántas solicitudes quedaron
    pendientes durante la pausa (el bot no puede listarlas ni recuperarlas:
    las acepta el dueño a mano).
  - La pausa se guarda en la base de datos (`pausa_desde`): sigue tras un
    reinicio, y lo recuerdan el arranque, `/estado` y los resúmenes diario
    y semanal.
- Plan B, si el bot no contestara: quitarle la administración del canal.
- Además, el dueño pregunta si se puede usar el bot de prueba como bot real
  cambiándole nombre y foto: se puede, pero el @ de un bot no se puede
  cambiar (los clientes verían «…pruebas_bot») y nos quedaríamos sin bot de
  prueba. Pendiente de su decisión.
- Pruebas: 141, pasan en Python 3.9, 3.12 y 3.13; las de la pausa fallan si
  se quita el freno.
- El dueño elige **bot nuevo** para PREMIER GALGOS (el de prueba se queda
  para probar). `instalar.sh` ya no dice «pulsa Iniciar» para saber el id:
  con el canal ya guardado en la fase 4, «Iniciar» no lo da; ahora dice
  `/miid`.
- Commits: `d315944`, `01015f4`

## 2026-10-18 — Captación: fase 4 hecha en la cuenta real (solo lectura)
- **Qué**: el dueño, con su visto bueno, actualizó la VM a `950e694`,
  conectó su cuenta a la instancia real (`conectar-cuenta.sh real`,
  reutilizando el api_id/api_hash de prueba) y ejecutó
  `leer-historico.sh real`. El canal principal se identificó con uno de sus
  enlaces de entrada («PREMIER GALGOS») y quedó guardado en la
  configuración real. No se instaló ni arrancó el bot real ni el lector.
- **Resultado**: 994 personas con bienvenida manual (197 «Buenas!
  Bienvenido a PREMIER GALGOS» y 797 «Buenos días y bienvenido a Premier
  Galgos»). Contestaron 319 (32 %) y recibieron enlace de venta 255 (26 %
  del total; el 80 % de los que contestaron). A ninguna se le enviará la
  bienvenida del bot. Los datos están en la base de datos real de la VM;
  irán al Sheet real cuando exista (fase 5).
- **Cómo fue**: unos 31 minutos (22:04-22:35 UTC). Telegram pidió esperar
  muchas veces (casi siempre unos 10 s; tres veces 2-3 min y una 886 s);
  con el tope anterior de 2 min se habría cortado. Hubo varios cortes de
  conexión de Telegram y Telethon se reconectó solo.
- **Cambio**: el tope de espera del histórico pasa de 15 a 30 min (la de
  886 s se quedó cerca del tope de 900 s), por si se vuelve a ejecutar.
- Commits: `f9e852c`

## 2026-10-18 — Captación: fase 4 preparada para la cuenta real (canal principal y api_id reutilizado)
- **Qué**: el dueño da el visto bueno a la fase 4 en su cuenta real (solo
  lectura). Antes de dársela a ejecutar, tres cambios:
  - **Canal principal**: la instancia real aún no sabe cuál es (lo diría el
    bot real, que es la fase 5). Sin él, los enlaces del canal principal
    contarían como de venta. Ahora `leer-historico.sh`, si falta, pide un
    enlace de invitación del canal, comprueba a qué canal lleva sin unirse
    (modo nuevo `lector canal-de-enlace`, con el candado de solo lectura),
    enseña su nombre y, si el dueño escribe SI, lo guarda en la
    configuración. Sin terminal, se niega.
  - **api_id/api_hash**: `conectar-cuenta.sh` ofrece reutilizar los de la
    otra instancia (`configurar.sh <instancia> api-de <otra>`, solo con
    órdenes internas de bash), para no copiarlos otra vez desde el móvil.
  - **Histórico más aguantador**: espera sola hasta 15 min si Telegram pide
    esperar (antes, a partir de 2 min se cortaba) y va diciendo por dónde
    va (búsqueda y «Repasando chats: N de M»).
- README: pasos de la fase 4 para la cuenta real; en la fase 5, `/miid`
  para saber el id (con el canal ya guardado, «Iniciar» no lo da) y el
  canal ya no hace falta configurarlo si se guardó en la fase 4.
- Pruebas: 135, pasan en Python 3.9, 3.12 y 3.13. Los scripts, probados en
  un entorno desechable con Telegram y systemd simulados: reutilizar o no
  el api_id, confirmar o cancelar el canal, segunda pasada sin preguntas,
  sin terminal.
- Commits: `950e694`

## 2026-10-18 — Captación: fase 3 probada en simulación; el botón se reconoce también en mensajes posteriores
- **Resto de la prueba** (cuenta principal, simulación), todo según las
  reglas:
  - El dueño no tenía carpeta del día porque ese día no entró nadie: crear
    la «18.10» era lo correcto.
  - Enlace del canal de prueba (otro enlace distinto del de solicitudes,
    pero del mismo canal): quedó como «Enlace del canal principal enviado»
    y no movió nada. Se comprueba a qué canal lleva el enlace, no el enlace
    en sí.
  - Enlace de un canal de venta: «saco a … de la carpeta 18.10 (se queda
    vacía y la borro)» y «creo la carpeta «free send» y meto a …».
  - La secundaria volvió a escribir: nada (ya tenía enlace). En Telegram no
    cambió ninguna carpeta. Comprobado también en la hoja de pruebas
    (Usuarios y Eventos).
  - El dueño preguntó por qué se cambia de carpeta y reconfirmó «pasa al
    día nuevo» (si vuelve a escribir otro día sin haber recibido la
    gratuita).
- **Mejora**: el botón («Ya he apostado» / «Primera vez») solo se miraba en
  el primer mensaje; si alguien escribía primero «hola» quedaba como «Otro
  texto» para siempre. Ahora un mensaje posterior que lo diga lo corrige;
  si ya había uno reconocido, se queda el primero. La carpeta del día no
  depende del texto: vale cualquier mensaje. 131 pruebas, pasan en Python
  3.9, 3.12 y 3.13; la nueva falla sin el cambio.
- Instalado en la VM por el dueño (`75355e0`, 21:43 UTC), con el lector
  reiniciado con el código nuevo; sigue en simulación.
- Commits: `75355e0`

## 2026-10-18 — Captación: cuenta principal del dueño conectada a la instancia de prueba (simulación)
- **Qué**: el dueño actualizó la VM a `35b5530`, sacó el api_id/api_hash
  en my.telegram.org y conectó su cuenta principal con
  `conectar-cuenta.sh prueba`. Resultado: sesión iniciada y
  `captacion-lector@prueba` en marcha en **modo SIMULACIÓN**. Falta la
  prueba con la secundaria (README, fase 3, paso 4).
- **Problemas encontrados** (no son fallos del código):
  - Desde el móvil (Termius), al cambiar de app Android cortaba la conexión
    SSH y se cerraba el programa a medias. Solución: ejecutarlo dentro de
    `tmux` (`tmux attach` para volver).
  - El primer intento lo bloqueó Telegram («el código fue compartido por tu
    cuenta»): el código había aparecido en algún chat de su cuenta. No
    entró nadie. En el segundo intento, escribiendo el código a mano, entró
    bien.
- README (paso 3) con los dos avisos. Sin cambios de código.
- Commits: `a27cc4f`

## 2026-10-18 — Captación: primera prueba de carpetas en simulación; avisos en orden
- **Resultado de la prueba** (cuenta principal, simulación): al arrancar
  reconoció 6 carpetas de días en formato día.mes y dijo que borraría la
  más antigua («07.09»; el dueño confirma que es vieja y puede irse). La
  secundaria pulsó un botón de la bienvenida y le escribió: «saco a … de la
  carpeta 19.09» (estaba ahí de antes), «creo la carpeta 18.10 y meto a …»
  y, al quedar 6 de días, «borro la carpeta 19.09». Es lo que dicen las
  reglas. Pendiente: confirmar si el dueño tenía ya una carpeta de hoy con
  otro nombre, y probar los enlaces (canal de prueba y canal de venta).
- **Arreglado**: los avisos llegaban desordenados (en la prueba, «borro la
  carpeta 19.09» llegó antes que «saco a … de la carpeta 19.09»), porque se
  enviaban varios a la vez. Ahora los envía un solo hilo, en orden. Prueba
  nueva que falla con el código anterior. 130 pruebas, pasan en Python 3.9,
  3.12 y 3.13. Llega a la VM con la próxima actualización; no hace falta
  actualizar para seguir probando.
- Commits: `8c9c5dc`

## 2026-10-18 — Captación: carpetas de días en formato día.mes («18.10»)
- **Qué**: el dueño avisa de que sus carpetas de días se llaman día.mes
  («18.10»), al revés de lo que se dijo al principio (mes.día). Cambiado
  antes de conectar su cuenta. La VM ya estaba actualizada a `7dd346d` (una
  sola pasada del instalador, como se esperaba).
- **Por qué importaba**: con mes.día, «12.10» se habría leído como el 10 de
  diciembre del año pasado y la rotación (en real) la habría borrado como
  la más antigua; «18.10» ni siquiera se habría reconocido.
- Además: las carpetas de días se comparan por fecha y no por el nombre
  exacto, así que vale «5.11» igual que «05.11» (se usa la del dueño tal
  cual; las nuevas se crean con cero delante). Y una carpeta de hasta una
  semana en el futuro (p. ej. la de mañana creada a mano por la noche) se
  toma como de este año, no del año pasado: antes la habría borrado al
  rotar.
- README: pasos para sacar el api_id/api_hash en my.telegram.org más
  detallados (el dueño aún no los tiene). Pruebas: 125, pasan en Python
  3.9, 3.12 y 3.13; las nuevas fallan con el formato y el cálculo de año
  anteriores.
- Commits: `b25be98`

## 2026-10-18 — Captación: teléfono con prefijo de cualquier país al conectar la cuenta
- **Qué**: el teléfono de la cuenta del dueño no es español, y el programa
  ponía de ejemplo un número con +34. Ahora pide el teléfono con el prefijo
  del país y sin el 0 inicial (ejemplos +353 8… y +34 6…). Acepta espacios,
  guiones y «00» delante, y si falta el prefijo lo vuelve a pedir.
- Si Telegram dice que el teléfono no es válido (p. ej. por dejar el 0
  después del prefijo), lo explica y lo vuelve a pedir, hasta 3 veces, en
  vez de acabar con un error de Python.
- De paso: en `tests/test_telethon_real.py` el `if __name__ == "__main__"`
  estaba a mitad del archivo; pasa al final. Pruebas: 129, pasan en Python
  3.9, 3.12 y 3.13.
- Commits: `35b5530`

## 2026-10-15 — Captación: la fase 3 se prueba con la cuenta principal, en simulación
- **Qué**: el dueño pidió probar las carpetas en su propia cuenta en vez de
  en la secundaria, porque ya tiene ahí sus carpetas de días. Su cuenta se
  conectará a la instancia `prueba`, en simulación. En esa instancia solo
  cuenta como cliente quien está en la memoria de prueba (la secundaria, que
  recibió la bienvenida del bot de prueba), así que sus clientes reales se
  ignoran, y el «canal principal» es el de prueba.
- **Candado más estricto en simulación**: nuevo modo `simulacion` en
  `guardia.py` (lectura + «no en línea», sin `UpdateDialogFilterRequest`).
  El lector lo usa cuando está en simulación, así que aunque hubiera un
  fallo en el código, Telegram no recibiría ningún cambio de carpetas.
- **Simulación fiel a lo que hace el dueño a mano**: las carpetas simuladas
  se tomaban de las reales solo al arrancar. Ahora, al cambiar de día,
  vuelven a leerse las reales, por si el dueño crea la carpeta del día a
  mano (antes habría dicho «creo la carpeta 10.16» aunque ya existiera).
  Dentro del mismo día no repite avisos.
- README (fase 3) reescrito con los pasos para su cuenta; avisos de no pasar
  el lector de `prueba` a real (borraría de verdad sus carpetas de días más
  antiguas) ni ejecutar el histórico en `prueba` con su cuenta conectada
  (metería a sus clientes reales en la memoria de prueba). Pruebas: 123,
  pasan en Python 3.9, 3.12 y 3.13.
- Commits: `7dd346d`

## 2026-10-15 — Captación: hoja de pruebas funcionando en la VM; instalador de una sola pasada
- La sesión de Claude de la VM (con autorización ampliada solo para crear el
  venv y copiar la credencial de picks) actualizó a `744efd5` y activó la
  copia al Sheet de pruebas: «Sheet actualizado: 1 usuarios, 3 eventos
  nuevos, 1 días». Comprobado leyendo la hoja con el conector de Drive: las
  cuatro pestañas (la pestaña vacía inicial reutilizada como «Usuarios»),
  fechas en hora de España, y el Resumen diario calcula bien con las
  fórmulas en inglés y separador «;» (COUNTIFS y COUNTUNIQUEIFS), con el
  día como «jue 15/10/2026». No hizo falta instalar python3-venv.
- Problema encontrado: hubo que ejecutar `instalar.sh` dos veces, porque se
  ejecutaba el instalador viejo (el de `/opt`), que aún no sabía crear el
  venv; la primera pasada solo instalaba el script nuevo. Arreglado: si el
  instalador descargado es distinto del que se está ejecutando, se reejecuta
  el nuevo con el código ya descargado (sin volver a descargar, sin pedir
  otra vez la confirmación de «real», y borrando la carpeta temporal al
  final). Probado en contenedor desechable simulando un instalador antiguo.
  Ojo: la PRÓXIMA actualización todavía parte de `744efd5`, que no tiene
  esto, así que esa vez aún harán falta dos pasadas; a partir de ahí, una.
- Commits: `9f9f142`

## 2026-10-15 — Captación: fases 3 y 4 programadas (carpetas e histórico)
Avanzado de noche sin el dueño, como pidió: solo código y pruebas; **nada
instalado ni conectado a ninguna cuenta**. Para activarlo hacen falta pasos
suyos (api_id/api_hash, conectar la cuenta secundaria) y su visto bueno.
- **Lector de la cuenta del dueño** (`captacion/premier_captacion/lector.py`,
  Telethon 1.45.0): servicio `captacion-lector@<instancia>` que ordena sus
  carpetas con las reglas acordadas (`carpetas.py`): carpeta del día «MM.DD»
  para quien recibió bienvenida y le escribe (pasa al día nuevo si vuelve a
  escribir sin enlace), «free send» cuando el dueño envía un enlace
  `t.me/+…` que no es del canal principal (se pregunta a Telegram a qué
  canal lleva, sin unirse, con caché en la base de datos), rotación a las 5
  carpetas de días más recientes, «free send» con los ~90 más recientes del
  embudo, nunca se quitan chats puestos a mano, nunca se tocan carpetas
  compartidas ni las que no son de días/free send, aviso si no hay hueco.
- **Seguridad**: `guardia.py` es una lista blanca de peticiones a Telegram
  enganchada en `TelegramClient._call` (por donde pasan todas): en modo
  lector solo lectura + carpetas + «no en línea»; en modo histórico, solo
  lectura. Enviar, marcar como leído, unirse, reenviar, borrar, salir,
  «escribiendo…», reaccionar o aparecer «en línea» quedan bloqueados. Se
  comprobó contra las clases reales de Telethon que cada nombre de la lista
  existe y que 11 peticiones peligrosas se bloquean en todos los modos.
- El lector **empieza siempre en simulación**: avisa por el bot de lo que
  haría («🧪 Simulación (no he tocado nada): …») sin tocar carpetas, sobre
  una copia en memoria de las carpetas reales. Solo actúa con
  `configurar.sh <instancia> lector real`. Recupera al arrancar lo llegado
  mientras estuvo parado (punto de control por persona: `ultimo_msg_id`).
- **Histórico** (`historico.py`, fase 4, solo lectura): busca las
  bienvenidas manuales del dueño (dos versiones, ahora tipos
  `manual_buenas` y `manual_buenos_dias` con sus textos en «Tipos de
  mensaje»), marca a esas personas como del embudo (el bot no les repetirá
  la bienvenida) y reconstruye si contestaron y si recibieron enlace de
  venta, para comparar manual frente a bot. Repetible sin duplicar.
- Base de datos: migración 2 (columnas de mensajes, botón, enlace y canal de
  venta, carpeta; tabla `enlaces`). Las migraciones ahora usan `BEGIN
  IMMEDIATE` y `abrir()` reintenta si la base está bloqueada (una prueba de
  6 procesos abriendo a la vez fallaba ~1 de cada 20 veces; ahora 0 de 80).
- Sheet y resúmenes ampliados: columnas de Usuarios (primer mensaje, botón,
  enlace y canal de venta, carpeta), columnas nuevas en Resumen diario y
  líneas «Te escribieron» / «Enlaces de venta» en los resúmenes por
  Telegram cuando el lector está activo.
- Despliegue: `instalar.sh` añade Telethon al venv y reinicia el lector si
  ya estaba activo (no lo activa); `conectar-cuenta.sh` (solo con terminal:
  lo hace el dueño; para la instancia `real` crea la configuración pero no
  arranca nada), `leer-historico.sh` y `lector.sh` (para el lector si
  estaba en marcha: una sesión usada por dos programas a la vez se anula);
  `configurar.sh` con `api` (api_hash oculto, nunca por argumento) y
  `lector simulacion|real`. La sesión de la cuenta vive en
  `/var/lib/premier-captacion/<instancia>-cuenta.session` (umask 077).
- Para probar con la secundaria como "dueño", la cuenta principal se marca
  del embudo con `lector.sh prueba embudo-prueba <id>` (solo pruebas).
- Verificado: 122 tests en Python 3.9, 3.12 (con gspread y Telethon reales)
  y 3.13; el adaptador de Telethon con sus tipos reales (`DialogFilter`,
  `TextWithEntities`, invitaciones) y el servicio entero con un cliente
  falso (simulación sin escrituras; modo real crea «MM.DD» y «free send» y
  todas las peticiones pasan la lista blanca). Scripts probados en
  contenedor desechable. Al revisar se quitaron del código de pruebas los
  ids reales de Telegram y los enlaces de los canales de venta que el dueño
  pasó como ejemplo (el repo es público).
- Commits: `5d79627` (código y pruebas), (este commit)

## 2026-10-15 — Captación: fase 2 (copia al Google Sheet)
El dueño eligió hacer el Sheet antes de pasar el bot a producción, y pidió
avanzar de noche con lo posible sin él (nada de producción).
- Hoja de pruebas **«Captación PREMIER GALGOS (pruebas)»** creada en su
  Drive con el conector de Google Drive, privada y compartida como editor
  solo con la cuenta de servicio que ya usa la VM para picks (el correo se
  sacó de los permisos de la hoja de picks; no se apunta aquí). Sin datos
  todavía: la llena la VM.
- `captacion/premier_captacion/sheet.py`: copia la base de datos local al
  Sheet cada 10 min (`captacion-sheet@<instancia>.timer`). Pestañas
  `Usuarios` (una fila por user_id), `Eventos` (solo añade lo nuevo; si se
  borran filas, se rellenan), `Resumen diario` (una fila por día con
  fórmulas COUNTIFS/COUNTUNIQUEIFS sobre Eventos, siguiendo la norma de que
  los números derivados sean fórmulas trazables) y `Tipos de mensaje`.
  Datos en modo RAW (un nombre que empiece por "=" no se convierte en
  fórmula); solo el Resumen va como fórmulas. Fechas como número de serie
  con formato de fecha, en hora de España.
- Fórmulas con nombres en inglés y separador ";", como las de
  `src/Setup.gs` de picks (hoja del mismo dueño, en español): por eso el
  volcado fija la configuración regional del libro en `es_ES` y la zona
  horaria en `Europe/Madrid`.
- Instalación: `instalar.sh` crea un venv propio
  (`/opt/premier-captacion/venv`, gspread 6.1.4) para no tocar el Python del
  sistema ni el venv de Proyecto Galgos, y copia (solo lectura del
  original) la credencial de picks a `/etc/premier-captacion/google.json`
  (root, 600); systemd se la pasa al servicio con `LoadCredential=`, así el
  usuario `captacion` no puede leerla fuera del servicio. Si algo de esto
  falla, el bot se instala igual y solo la copia queda sin activar.
  `configurar.sh <instancia> sheet <enlace>` acepta el enlace entero y hace
  la primera copia en el acto.
- Verificado sin red: 62 tests (incluida una hoja simulada que, como la
  API, falla al escribir fuera de la cuadrícula), y el volcado ejecutado con
  el gspread real sobre un cliente HTTP falso para ver las peticiones
  exactas que haría. Eso destapó un fallo ya corregido: gspread devuelve
  `[[]]` para una pestaña vacía, y la pestaña inicial no se reutilizaba.
  Instalador probado en contenedor desechable (venv + gspread + credencial
  falsa → error claro de credencial). **Falta probarlo contra Google de
  verdad en la VM.**
- Commits: `a8e337c`

## 2026-10-14 — Captación: plan aprobado y fase 1 (bot de bienvenida)
Subsistema nuevo e independiente del de picks, en `captacion/` y en la rama
`captacion-bienvenida` (no toca `src/`). Objetivo: dejar de aceptar a mano
las ~20-30 solicitudes diarias de unión al canal y de enviar la bienvenida
desde la cuenta personal; después, organizar en carpetas los chats de
quien responde y sacar estadísticas.
- **Plan aprobado** por el dueño tras varias rondas de preguntas: todas las
  decisiones (texto versión B con dos botones, carpetas `MM.DD` con
  rotación de 5 días, `free send`, Sheet privado aparte, resúmenes a las
  00:05 y lunes 9:00, fases y riesgos) en `captacion/PLAN.md`.
- Por qué un bot y no la cuenta del dueño: Telegram solo deja a un bot
  escribir a alguien mientras su solicitud está pendiente (5 min). Por eso
  las solicitudes pasan a autoaceptarse y la bienvenida se envía siempre
  antes de aceptar. Enviar mensajes automáticos desde la cuenta personal
  se descartó (riesgo de denuncias por spam y de suspensión).
- **Fase 1 hecha (pendiente de probar en el canal de prueba)**: bot en
  Python solo con librería estándar (`captacion/premier_captacion/`):
  bienvenida + aceptación, memoria por `user_id` en SQLite local (quien ya
  la recibió y vuelve se acepta sin mensaje), respuesta «escríbeme» a
  quien escribe al bot (una por ráfaga), avisos al dueño (fallos, bot
  parado más de 5 min, cambios de permisos), comandos `/resumen`,
  `/semana`, `/estado`, `/miid`, y resúmenes diario/semanal por timers de
  systemd. Nunca acepta solicitudes de un chat que no sea el configurado.
- Corrección sobre lo hablado: Telegram no avisa al bot cuando se pulsa un
  botón de enlace, así que qué botón eligió cada persona se sabrá por el
  texto que le llegue al dueño (fase 3), no por el bot.
- Despliegue previsto en la VM como servicios propios
  (`captacion-bot@prueba`, usuario de sistema `captacion` sin privilegios,
  configuración con el token en `/etc/premier-captacion/`, fuera del repo).
  Guía paso a paso en `captacion/README.md`.
- Verificado: 45 tests (`cd captacion && python3 -m unittest discover -s
  tests -t .`) en Python 3.9, 3.11, 3.12 y 3.13; prueba de punta a punta del
  proceso real contra un Telegram falso local (orden bienvenida→aceptación,
  parada limpia con SIGTERM); unidades systemd validadas con
  `systemd-analyze`. Las negritas Unicode de la bienvenida se comprueban
  contra el texto original del dueño.
- Ajuste tras empezar la puesta en marcha: al abrir el bot por primera vez
  ("Iniciar") en plena configuración, contesta con el id de quien escribe
  en vez de con la respuesta para clientes.
- Papeles en la prueba de la fase 1, cambiados a petición del dueño: su
  cuenta principal hace de dueño (canal de prueba suyo, avisos y botones a
  @Dronwhite, igual que en producción) y la secundaria de cliente. Hacen
  falta dos cuentas porque quien crea un canal no puede pedir unirse a él.
  La secundaria como "dueño" queda para la fase 3 (programa de carpetas),
  para no conectar ese programa a la cuenta principal hasta probarlo.
- Bot de prueba creado por el dueño: `@premiergalgos_pruebas_bot`. Los
  enlaces de invitación de prueba NO se guardan en el repo: el repositorio
  es público y con el bot activo cualquiera con el enlace entraría.
- Instalación simplificada para el dueño (no técnico): como el repo es
  público, la VM descarga el código de GitHub directamente.
  `captacion/deploy/instalar.sh` (instala/actualiza en un comando, fija el
  commit exacto descargado y lo anota en `/opt/premier-captacion/VERSION`,
  pide el token sin mostrarlo, activa bot y resúmenes; la instancia `real`
  exige escribir SI) y `captacion/deploy/configurar.sh` (cambia propietario,
  canal, perfil o token sin editar archivos, y reinicia). El token nunca se
  acepta como argumento (quedaría en el historial de la terminal). `/estado`
  muestra la versión instalada. El resumen ya no falla si aún no hay
  propietario configurado (los timers se activan al instalar). Probados en
  un contenedor desechable con systemctl simulado, y el bot instalado
  arrancando con el usuario sin privilegios.
- **Instalado y probado en la VM** (instancia `prueba`, versión `6bbb6e7`).
  Lo ejecutó una sesión de Claude en la propia VM con autorización expresa
  del dueño limitada a lo de captación (usuario `captacion`,
  `/opt|/etc|/var/lib/premier-captacion`, servicios `captacion-*`; nada de
  Proyecto Galgos ni de picks); el token lo puso el dueño desde su terminal
  SSH con `configurar.sh prueba token`, sin pasar por ningún chat.
  Propietario y canal configurados con `configurar.sh` (los ids no se
  apuntan aquí: repo público).
- Tropiezo de la puesta en marcha: el primer intento («Prueba bot
  captación») era un **grupo** con el bot como simple miembro, y no sirve.
  Tiene que ser un **canal** con el bot **administrador** con «Añadir
  suscriptores». Canal de prueba definitivo: «Prueba canal captación con
  bot» (privado, enlace de «Solicitar unirse»). Ojo al pasar a producción.
- Prueba de punta a punta OK: la cuenta secundaria pide entrar → recibe la
  bienvenida nueva → el bot acepta solo; el botón abre el chat de
  @Dronwhite con el texto ya escrito. Primer resumen diario: madrugada del
  16-10 (hora de España); primer semanal: lunes 19-10 a las 9:00.
- Primer cambio tras probarlo: el texto que
  dejan escrito los botones pasa de «¡Hola! Vengo de PREMIER GALGOS 🐕 …» a
  «¡Hola! Acabo de entrar en el canal. Ya he apostado en galgos antes 🐕» /
  «… Es mi primera vez con los galgos 🐕» (al dueño no le gustaba «Vengo
  de PREMIER GALGOS»). Se mantiene el tipo de mensaje `bot_b_v1` porque aún
  no hay datos reales que separar.
- Commits: `3dc009a` (fase 1), `82876bc` (Iniciar en puesta en marcha),
  `35d0a71` (papeles de la prueba), `4e7b881`/`4f234e6`/`2616cfa`
  (instalador y configurador), (este commit)

## 2026-09-09 — Fixes de resolución de gemela/trío + disparador a 30 min
Tres ajustes sobre `resolverApuestasExoticas` (Main.gs), detectados con datos
reales de producción tras el lanzamiento del 8 sept. Desplegados en su
momento vía `clasp push` directo al proyecto de Apps Script; esta entrada
sincroniza ese código con el repo (quedó unos días sin commitear).
- `parsearNumeroLocale_`: `dividendo` en `resultados_gemela_trio` llega como
  número real (filas del job automático de la VM, desde el 09/09) o como
  texto con coma decimal es_ES (filas sembradas a mano antes de esa fecha,
  ej. "7,42" de Star Pelaw 05/09/2026) - `Number()` de JS no entiende la
  coma y daba `NaN` con la segunda forma.
- Nuevo resultado `no_disponible`: si la carrera ya tiene fila `forecast`
  en `resultados_gemela_trio` (la VM la resolvió del todo) pero sigue sin
  fila `tricast`, es que esa carrera nunca tuvo mercado de trío (necesita
  6 galgos corriendo - caso real Kinsley 06/09), no que falte por llegar.
  Se distingue de `pendiente` real. Se reembolsa el stake (no cuenta como
  ganada ni perdida, excluida del panel igual que `pendiente`/
  `revision_manual`) y se avisa por Telegram con ⚠️.
- `configurarTriggerResolverExoticas`: disparador de `resolverApuestasExoticas`
  pasa de cada 2h a **cada 30 min** - el job de la VM publica
  `resultados_gemela_trio` cada 20 min desde el 09/09, así que 2h añadía
  hasta 1h40 de retraso innecesario al aviso de Telegram.
- De paso: `.clasp.json` con `fileExtension: "gs"` para que `clasp pull`
  escriba directo en `.gs` (antes creaba duplicados `.js`).
- Commits: (este commit)

## 2026-09-08 — Soporte para gemela y trío (forecast/tricast)
Nuevo tipo de apuesta: gemela (1º y 2º de una carrera) y trío (1º, 2º y
3º), con o sin "reversible". A diferencia de simple/doble/triple, es UNA
carrera con varias selecciones y orden, pagada al dividendo oficial que
publica la pista tras la carrera (no a una cuota fija) - ver
`docs/superpowers/specs/2026-09-08-gemela-trio-design.md`.
- Hojas nuevas: `apuestas_exoticas` (la escribe el bot) y
  `resultados_gemela_trio` (la alimenta un job de la VM de Proyecto
  Galgos, tarea pendiente en ese otro repo - ver la spec).
- IA (`AI.gs`): reconoce "GEMELA"/"TRÍO" (desglosado o "reversible"),
  extrae combinaciones de orden en vez de cuota fija.
- Resolución por script (`resolverApuestasExoticas`, `Main.gs`, disparador
  cada 2h) en vez de fórmula de hoja - compara las combinaciones jugadas
  contra el resultado real y calcula retorno con el dividendo oficial.
- Dos avisos por Telegram (registro y resolución, ambos como respuesta al
  mensaje original) - a diferencia del resto de apuestas, que se resuelven
  en silencio.
- Cuentan en el panel público (unidades, ROI, aciertos, evolución,
  historial) - única excepción: la tarjeta "PICKS CON VALUE", que no
  aplica (no hay cuota previa que comparar).
- Reparado el caso histórico real (Star Pelaw, 5-sept-2026): acertó la
  combinación 4-3, dividendo 7.42, retorno 14.84u (+10.84u).
- Dos bugs reales de auto-conversión de tipos de Google Sheets
  encontrados y arreglados al probar contra producción (valores tipo
  "22:31" o "4-3" que Sheets detecta como hora/fecha si no se fuerza
  formato de texto antes de escribir), más un bug cosmético en la
  etiqueta de combinaciones del panel.
- Desplegado sobre el mismo deployment público de siempre
  (`...5vdXzrYcItxBlijtD68k4g72ww @24`).

Commits: f147576, 2b62930, 0114633, cda5695, 1f3ec87, 7d2e4ff, 7461b08, 4bbc5b5, d0fd795, 4d2766b

## 2026-09-04 — Panel v12: el tooltip del gráfico también muestra unidades
Pedido del dueño: al pinchar/pasar el ratón sobre la curva de beneficio, el tooltip solo mostraba
el € acumulado. `getMetricasPanel()` (`Dashboard.gs`) no mandaba las unidades crudas de cada punto
de `evolucion`, solo el equivalente en euros - se añadió `acumuladoUnidades` a esa respuesta.
En el cliente (`Panel.html`), se propaga por la agrupación semana/mes de `serie()` (antes solo
llevaba `acumuladoEur`) y se añade a `st.pts` para pintarlo en el tooltip junto al importe en euros.
Desplegado sobre el mismo deployment público de siempre (`...5vdXzrYcItxBlijtD68k4g72ww @23`).

Commits: 7156070

## 2026-09-02 — Bug real: pick perdido en silencio si fallaba la descarga de la foto
El dueño reenvió 3 picks casi seguidos (13:41-13:42); el bot confirmó el 1º y el 3º pero no dijo
nada del 2º ("12:21 Harlow · Rallying Wood"), y no aparecía ni en `apuestas` ni en el panel.
- **Causa**: en `manejarPickNuevo_` (`src/Main.gs`), `downloadTelegramPhoto(fotoFileId)` se llamaba
  FUERA del `try/catch` que solo envolvía la llamada a la IA. Si esa descarga fallaba (glitch
  puntual de la API de Telegram, probablemente por mandar 3 `getFile` casi a la vez), la excepción
  escapaba sin capturar hasta `doPost`, que solo hace `Logger.log` y no manda nada por Telegram - el
  mensaje se quedaba en `mensajes_crudos` con `estado=pendiente` para siempre, sin fila en `apuestas`.
- **Chequeo nuevo, solo lectura**: `buscarPicksAtascados()` (`src/Auditoria.gs`) - mensajes con
  `estado` en `pendiente`/`error` sin fila correspondiente en `apuestas` (la auditoría existente
  parte de `apuestas`, así que no veía estos). Ejecutado sobre 139 mensajes: **1 solo caso histórico**
  (el propio `message_id=214` de hoy) - no es un problema recurrente, era la primera vez.
- **Arreglo**: la descarga de la foto entra ahora en el mismo `try/catch` que la IA - cualquiera de
  los dos fallos marca `estado=error` y manda un aviso por Telegram explicando que se reintentará
  solo (antes el mensaje de error de la IA sonaba a "revísalo a mano"; ahora deja claro que
  `reintentarMensajesConError()`, ya programada cada 2h, se encarga sin que el tipster tenga que
  hacer nada).
- **Reparación del caso ya atascado**: `repararPicksAtascados_2026_09_02()` (`src/Main.gs`) - lista
  cerrada con el único `message_id` confirmado, lo pasa de `pendiente` a `error` y lanza
  `reintentarMensajesConError()` en la misma ejecución, sin que el dueño tuviera que reenviar nada
  ni tocar la hoja a mano.
- Desplegado sobre el mismo deployment público de siempre (`...5vdXzrYcItxBlijtD68k4g72ww @22`).

Commits: e6327fd

## 2026-09-01 — Panel v11: rediseño + filtro de fechas, hora de carrera, picks con value, fix jornadas=picks
Rediseño completo de `src/Panel.html` (entregable de un handoff de diseño, HTML/CSS/JS plano
autocontenido, sin frameworks - encaja tal cual en `HtmlService`) más los cambios de servidor en
`src/Dashboard.gs` que ese nuevo cliente necesitaba:
- **Filtro de rango de fechas** en la tabla de picks, combinable con Ganados/Perdidos - implementado
  en el CLIENTE sobre el histórico ya cargado (`historicoPicks[].fechaISO`), sin volver a acotar la
  consulta del servidor por fecha (la v4 ya se revirtió una vez por eso, "no me cuadran los números").
- **"Mensaje original"** ahora muestra la hora exacta de envío del pick (`fechaHoraLabel`) y la hora
  de cada carrera del pick (`historicoPicks[].patas`, una entrada por pata - cubre dobles/triples),
  con el tiempo transcurrido entre ambas calculado en el cliente. `getMetricasPanel()` no leía
  `apuestas_patas` hasta ahora; se añadió `obtenerPatasPorMensaje_()` (lectura en bloque, igual
  patrón que `Auditoria.gs`) y se cruza por `message_id`.
- **Nueva tarjeta "PICKS CON VALUE"**: % de picks resueltos cuya cuota de cierre (`cuota_final`)
  acabó por debajo de la publicada (`cuota`) - señal de que el mercado se movió a favor del pick.
  Función pura `calcularPctCuotaBajada_()` con su test, mismo patrón que `calcularMetricas_`.
- **Bug real corregido**: `calcularMetricas_` generaba una entrada de `evolucion` por CADA pick
  resuelto en vez de por día, así que "nº de jornadas" y "nº de picks" del panel coincidían siempre
  (reportado por el dueño: "130 picks en 130 jornadas"). Ahora se agrupa por día natural
  (`Europe/Madrid`); test nuevo cubre dos picks el mismo día.
- Aplicado el cambio obligatorio del handoff de diseño: retirado el `MOCK()` de `Panel.html` que
  solo se usaba para previsualizar fuera de Apps Script.
- Desplegado sobre el mismo deployment público de siempre
  (`AKfycbynXi-jwc8nA4Z3wEx3NNrcVxDwiBKMRQHdrXx_5vdXzrYcItxBlijtD68k4g72ww @21`).

Commits: 467ebfe

## 2026-08-28 (cont.) — Auditoría: excepciones confirmadas + comprobación de galgo distinto
Dos ajustes más a `src/Auditoria.gs` a partir de la sesión de auditoría de esta misma tarde:
- **Excepciones confirmadas para `fecha_pick_inconsistente`**: los 15 `message_id` restantes de la
  segunda tanda de importación manual (115, 116, 123, 127-130, 135, 136, 139, 140, 143, 144, 147,
  148) quedaron verificados uno a uno contra el texto original de 3 de ellos (fechas distintas
  dentro del lote) - `fecha_pick` es correcta, `fecha_recibido` de `mensajes_crudos` solo refleja
  el día de la carga manual. Añadida una lista explícita `MESSAGE_IDS_CARGA_MANUAL_CONFIRMADOS_`
  (documentada con el motivo) para que dejen de salir en la auditoría sin debilitar el check para
  picks reales futuros del bot.
- **Comprobación nueva, `posible_galgo_distinto`**: el dueño preguntó cómo validar que el
  automatismo no solo aplica bien la fórmula, sino que encuentra la carrera/galgo CORRECTOS de
  verdad (algo que comparar fórmulas entre sí no puede detectar, porque un dato de origen erróneo
  en `resultados_galgos` produciría el mismo resultado en ambos lados). Se añadió el cruce del
  nombre de galgo que puso el tipster (`apuestas_patas.seleccion`) contra el que registró la VM
  para la trampa/carrera que se dio por buena (`resultados_galgos.nombre`) - si no se parecen
  (tras ignorar mayúsculas/tildes/paréntesis tipo "(Res)"), es señal de que esa trampa cambió de
  corredor (reserva/no corredor sustituido) y `resultado_pata` podría estar comparando contra un
  perro distinto al apostado.
- **Ejecutado y revisado**: sobre 113 apuestas / 118 patas / 388 filas de `resultados_galgos`, un
  único aviso (`message_id 81`, fila 82: "Sccoby Mustang" del tipster vs "Scooby Mustang" en
  `resultados_galgos`). El dueño confirmó que es un error tipográfico de captura al registrar la
  selección, no un galgo distinto de verdad - el cruce trampa+carrera es correcto. Cero
  discrepancias reales; agregados recalculados de cero coinciden con el panel (ganancia neta
  +57,15 unidades, stake 520, ROI 10,99%, 35,71% de aciertos sobre 112 picks resueltos visibles).

Commits: ca3d056

## 2026-08-28 — Auditoría ejecutada: sistema de cálculo sano, sin bugs de cálculo encontrados
El dueño ejecutó `auditarSistema()` (ver entrada de abajo, 2026-08-27) contra la hoja real: 112
apuestas, 117 patas, 385 filas de `resultados_galgos`. **Cero discrepancias** en `resultado_pata`,
`resultado_final`, `retorno_real` y `unidades_netas` - el motor de cálculo reimplementado desde
cero coincide con las fórmulas de la hoja en todas las filas. Cero problemas estructurales
(sin `message_id` duplicados, sin patas huérfanas, sin descuadres de número de patas vs
`tipo_apuesta`, sin cuotas/stakes inválidos, sin celdas en error, sin trampas duplicadas ni
"varios ganadores" en `resultados_galgos`). Agregados del panel (ganancia neta +61,15 unidades,
stake total 516, ROI 11,85%, 36,04% de aciertos sobre 111 picks resueltos y visibles) coinciden
con `getMetricasPanel()`.

Durante la revisión salieron dos categorías de aviso, ambas descartadas como bug real:
- **2 "agregado" (ROI%/% aciertos) en la primera ejecución**: falso positivo del propio script de
  auditoría, no del sistema - comparaba el valor recalculado sin redondear contra el de
  `getMetricasPanel()` (que sí redondea a 1 decimal) con una tolerancia demasiado ajustada.
  Corregido redondeando ambos lados antes de comparar.
- **102 "fecha_pick_inconsistente" en la primera ejecución (87 + 15 tras el ajuste de abajo)**: el
  dueño confirmó que corresponden a dos tandas de importación manual de picks históricos
  anteriores a que el bot estuviera operativo (no pasaron por `Main.gs`), donde `fecha_recibido`
  de `mensajes_crudos` solo refleja el momento de la carga a mano, no la fecha real del pick -
  `fecha_pick` en `apuestas`/`apuestas_patas` (la que de verdad se usa para cruzar contra
  `resultados_galgos`) es correcta. Verificado a mano contra el texto original de 3 picks
  concretos de fechas distintas (`message_id` 115, 140, 147) antes de descartarlo. Durante esta
  revisión se detectó y corrigió un fallo en la propia heurística del script (agrupaba por DÍA de
  `fecha_recibido` para detectar cargas masivas; se cambió a agrupar por el INSTANTE EXACTO,
  porque agrupar por día habría podido ocultar también días reales de mucha actividad del bot,
  justo donde más importa vigilar el bug de reintentos/forward).

Conclusión: no hace falta ningún fix de código a raíz de esta auditoría. El sistema de cálculo de
apuestas está verificado como correcto sobre los datos reales actuales.

Commits: ca3d056

## 2026-08-27 — Auditoría independiente de todo el cálculo de apuestas (`src/Auditoria.gs`)
El dueño pidió verificar que las fórmulas de `apuestas`/`apuestas_patas` (resultado_pata,
resultado_final, retorno_real, unidades_netas) y los agregados del panel público
(`getMetricasPanel()`) son correctos, dado que ya se han encontrado bugs reales de cálculo antes
en este proyecto (comparación número/texto sin coaccionar, `fecha_forward` perdida en
reintentos...) y el panel es público sin login. Sin credenciales de la API de Sheets en este
entorno (viven solo en la VM, ver `CLAUDE.md`) y sin `clasp run` funcional en este proyecto
("NOT_FOUND"), la única vía es una función de Apps Script que el dueño ejecuta a mano desde el
editor - mismo patrón que `setupSheet`/`checkConfig`.

Añadida `auditarSistema()` (+ helpers de normalización y `test_reglasAuditoria_` con casos de
mano, mismo patrón que `test_calcularMetricas_` en `Dashboard.gs`): reimplementa desde cero -sin
leer ninguna fórmula ni fiarse de valores ya calculados- las reglas de `resultado_pata` (match
exacto canódromo+fecha+hora+trampa; si no, "trampa ganadora" de la carrera como fallback),
`resultado_final` (manual > tipo no soportado > alguna pata perdida > todas ganan > pendiente),
`retorno_real` y `unidades_netas`, y compara el resultado contra lo que la hoja tiene ahora mismo
en esas columnas, fila a fila. También revisa consistencia estructural (message_id duplicados,
patas huérfanas, número de patas vs `tipo_apuesta`, celdas en error, cuotas/stakes inválidos,
`fecha_pick` vs `fecha_forward`/`fecha_recibido` de `mensajes_crudos`, trampas duplicadas o
varios "ganadores" en la misma carrera dentro de `resultados_galgos`) y recalcula los agregados
del panel (ganancia neta, stake total, ROI%, % de aciertos) para compararlos contra
`getMetricasPanel()`. Solo lectura sobre las pestañas de datos; escribe el detalle en una pestaña
nueva `auditoria` además de en el Registro de ejecución. No se ha ejecutado todavía (pendiente de
que el dueño la corra desde el editor y comparta el resultado).

Commits: ca3d056

## 2026-08-27 (cont.) — Panel v10: logo real en la cabecera (sustituye el monograma CSS "PG")
El dueño mandó el logo circular real de Premier Galgos (JPEG). Redimensionado a 128×128
(el original era 640×640, innecesario para un logo que se ve a 38-46px - habría inflado el
HTML sin motivo) y **embebido como `data:` URI en base64 dentro del propio `src/Panel.html`**,
en vez de subirlo a un hosting externo: coherente con que el panel es una página 100%
autocontenida (la única dependencia externa permitida son Google Fonts) y evita depender de
que una URL de WordPress siga viva o permita hotlinking. Sustituye `<div class="logo-mark">PG</div>`
por `<div class="logo-mark"><img src="data:image/jpeg;base64,...) alt="Premier Galgos"></div>` -
el CSS `.logo-mark img{...object-fit:cover...}` ya existía preparado para esto (nota del propio
README del rediseño de Claude Design: "si se quiere la foto real, sustituir el div por el img").
Verificado sintaxis JS con `node -e "new Function(...)"` y con `curl` en producción antes de
dar el despliegue por bueno (v20).

Pendiente en paralelo (otra sesión con DevTools): diagnosticar por qué el iframe con
`position:fixed` en la página de WordPress no cubre pantalla completa - descartado por `curl`
que sea el HTML servido, un iframe duplicado, caché, o una regla CSS del tema que mencione
`iframe`; queda pendiente inspeccionar estilos computados en un navegador real.

Commits: (pendiente)

## 2026-08-27 — Iframe del panel en WordPress no cubría pantalla completa (`position:fixed` se comportaba como `static`)
- El bloque HTML personalizado en `https://premiergalgos.com/?page_id=9` incrusta el panel
  (`Panel.html` vía Apps Script) en un `<iframe>` con `position:fixed; inset:0` pensado para tapar
  la cabecera/menú/footer del tema (Twenty Twenty-Five). En todos los navegadores/dispositivos
  probados se veía como una caja normal dentro del flujo, con la cabecera arriba y el footer
  debajo - como si `position:fixed` no se aplicase.
- Descartado por el usuario con `curl`: el HTML servido tenía el CSS correcto, sin iframe
  duplicado, sin ninguna regla del tema mencionando `iframe`, sin `transform/filter/will-change/
  contain` en ningún ancestro, sin caché de navegador (incógnito, varios navegadores).
- Investigado más a fondo contra la página real: sin cabecera ni meta `Content-Security-Policy`
  (habría anulado el `style=""` inline), sin ninguna regla `position:` que apunte a `iframe` o a un
  wildcard con `!important`, ampliada la lista de propiedades que rompen el containing block de
  `position:fixed` (añadidas `perspective`, `backdrop-filter`, `content-visibility` - ninguna
  presente), y confirmado que el sitio **no tiene ningún plugin de WordPress activo** (solo JS core
  de emoji + interactividad del menú) - descarta un plugin de cookies/lazy-load reescribiendo el
  iframe por JS, la sospecha más probable para este síntoma.
- **Causa raíz no identificada con certeza** (no hubo acceso a DevTools real para ver el DOM/
  estilos computados en vivo - el HTML/CSS servido por el servidor estaba limpio).
- **Arreglado** con una solución robusta independiente de la causa: mover el `<iframe>` a ser
  hijo directo de `<body>` por JavaScript nada más cargar (`document.body.appendChild(...)`),
  escapando así de cualquier ancestro problemático presente o futuro. Confirmado por el dueño que
  soluciona el problema.
- Sin commits (snippet suelto pegado a mano en WordPress, fuera de este repo).

## 2026-08-27 — Bug real: `vm_job_dog_forms.py` se quedaba colgado 15 min y lo mataba el timeout de systemd, sin procesar nada - faltaba timeout de red
- El usuario reportó que seguía sin aparecer `cuota_final`/`dog_id` en
  varios picks (puso de ejemplo `message_id 30`, Hollyoak Ethel).
- Investigado con SSH (Tailscale había caducado otra vez, reautorizado):
  `picks-dog-forms.service` llevaba **dos ejecuciones seguidas fallando
  por timeout** - ayer 2026-08-26 16:32-16:47 (el intento manual de esa
  sesión) y hoy 2026-08-27 04:01-04:16 (la pasada diaria programada,
  06:00 Madrid). Ambas veces: matado por `TimeoutStartSec=15m` de
  systemd, habiendo consumido solo **1,1s de CPU real en 15 minutos de
  reloj** - la firma clásica de un proceso bloqueado esperando una
  respuesta de red que nunca llega, no calculando nada.
- **Causa raíz**: el cliente HTTP que usan `gspread`/`google-auth` no
  pone ningún timeout por defecto en sus peticiones - si la llamada a la
  API de Google Sheets (o al endpoint de OAuth para renovar el token) se
  queda colgada, el proceso espera indefinidamente en vez de fallar
  rápido. Sin nada que lo pare antes, solo el timeout duro de systemd
  (pensado como red de seguridad, no como mecanismo normal) lo corta - y
  para entonces ya se ha perdido la pasada entera sin haber tocado ni un
  solo pick.
- Confirmado que no era contención con otro job pesado corriendo a la
  vez: la pasada de hoy (04:01 UTC) no coincidía con ninguna ejecución de
  `galgos-poll-results` (`journalctl` sin entradas en esa franja) - el
  cuelgue es intrínseco a la propia llamada de red, no un efecto de carga
  de la VM.
- **Arreglado**: `socket.setdefaulttimeout(60)` al principio de
  `scripts/vm_job_dog_forms.py` (y también en
  `scripts/vm_job_resultados_galgos.py` de forma preventiva, mismo patrón
  de llamada a gspread aunque no se le haya visto colgar todavía - solo
  ha dado un `503` rápido una vez). Con esto, cualquier llamada de red que
  se quede colgada falla a los 60s en vez de nunca, y la siguiente pasada
  (diaria o cada 20 min según el job) lo reintenta sola sin perder una
  ejecución entera de 15 minutos por nada.
- Desplegado a la VM y ejecutado a mano para vaciar el atasco acumulado:
  de **9 patas pendientes de `cuota_final`** (las 4 de antes + 4 picks
  nuevos de ayer que nunca habían tenido ni un primer intento, por el
  cuelgue) bajó a **8** en una sola pasada limpia (resuelta 1 en vivo). El
  resto sigue esperando legítimamente a que su galgo vuelva a correr, más
  `message_id 30` (Hollyoak Ethel) que sigue sin `dog_id` por el
  emparejamiento por nombre exacto (lleva pegada la anotación "SIN el
  favorito" - limitación conocida y documentada, no relacionada con este
  bug).
- **De propina, arreglada también esa limitación**: el emparejamiento por
  nombre en `vm_job_dog_forms.py` ahora prueba, si no hay coincidencia
  exacta, si el nombre real del galgo (según la card) es un PREFIJO del
  texto del tipster - así "Hollyoak Ethel SIN el favorito" encuentra a
  "Hollyoak Ethel" sin arriesgar falsos positivos (nunca al revés).
  Verificado: tras el cambio, las 8 patas pendientes encuentran su
  `dog_id` (antes 1 no lo encontraba) - ninguna se resolvió más porque
  ninguno de esos galgos ha vuelto a correr todavía, esperado.
- Commits: ca3d056

## 2026-08-27 (cont.) — Panel v9: rediseño completo con Claude Design, identidad de marca de la landing, gráfico SVG propio (sin Google Charts)
El dueño pidió delegar el rediseño visual a Claude Design (herramienta aparte, sin acceso a
este repo) en vez de seguir iterando aquí. Se le generó un prompt autocontenido (contrato
exacto de `getMetricasPanel()`, restricciones del sandbox de `HtmlService`, y el HTML completo
de la landing de Premier Galgos como referencia de marca) para que investigara, decidiera el
mejor enfoque y entregara HTML/CSS/JS final + un README con lo que hiciera falta cambiar en
Apps Script.

- **Resultado**: sustituido `src/Panel.html` entero por el entregable. Misma identidad visual
  que la landing (fondo `#0a0e13`, verde `#39FF14`, `Inter Tight`/`Inter`, tarjetas con el mismo
  gradiente sutil). Cambios de fondo respecto a la v8:
  - "Registro" en vez de dashboard: cifra hero de beneficio neto con el gráfico incrustado,
    métricas secundarias, e historial como filas desplegables con el mensaje original del
    tipster en monoespaciada ("PUBLICADO EN TELEGRAM") - no una tabla.
  - Gráfico de evolución reescrito en **SVG propio** (línea con halo, área en degradado,
    tooltip, segmentado día/semana/mes) - **ya NO depende de Google Charts**, una dependencia
    externa menos en el sandbox.
  - Paginado en cliente de 20 en 20 (el histórico puede tener cientos de filas) + filtro
    Todos/Ganados/Perdidos.
  - Estados de carga/vacío/error rehechos con la misma identidad, uno de ellos con botón
    "Reintentar" que repite la llamada a `getMetricasPanel()`.
- **Cero cambios en el contrato de datos ni en `Dashboard.gs`**: el README del entregable
  confirmaba que el cliente consume exactamente los mismos campos que ya expone
  `getMetricasPanel()` - verificado por el propio dueño de esta sesión comparando campo a
  campo antes de integrar, no solo tomando la palabra del README.
- **2 ediciones mecánicas al integrar** (pedidas explícitamente por el README del propio
  entregable): borrada la función `MOCK()` (datos falsos para previsualizar fuera de Apps
  Script) y simplificado `cargar()` para llamar siempre a `google.script.run` sin la rama de
  respaldo.
- **Revisión de calidad antes de desplegar** (dado el tamaño del cambio - sustituye toda la
  página): verificado que el historial construye las filas con `innerHTML` + una función `esc()`
  propia (en vez de `textContent`/`createElement` como la v8) - trazado que `esc()` se aplica a
  los 4 campos de texto no confiable (`fechaLabel`/`canodromo`/`galgo`/`mensaje`, este último el
  mensaje libre del tipster) y que en los 4 casos el resultado cae siempre en posición de texto,
  nunca dentro de un atributo - seguro tal y como está, aunque `esc()` no escapa comillas (no
  hace falta en ese contexto). Confirmado que no se coló ninguna dependencia externa aparte de
  Google Fonts. 2 fixes menores aplicados tras la revisión: recuperado `<base target="_top">`
  (se había perdido en el rediseño; importante porque el panel se incrusta en un iframe de
  WordPress - sin esto, un enlace futuro sin `target` explícito navegaría dentro del iframe en
  vez de abrir la pestaña de arriba) y corregido un `style.cssText +=` que se acumulaba sin
  límite en cada reintento tras un error (cambiado a asignación directa de propiedades).
- Verificado con `curl` contra la URL real en producción que el HTML servido es el nuevo diseño
  (no una versión en caché), antes de dar el despliegue por bueno.
- Redesplegado sobre el mismo deployment (v19).
- Commits: (pendiente)

## 2026-08-27 (cont.) — Panel enmarcable en iframe, a petición del dueño (quiere meterlo en su web de WordPress)
El dueño quiere el panel dentro de su propia web (WordPress, autoalojado)
en vez de que la gente tenga que ir a la URL de Google. Decidió, tras
preguntarle, incrustarlo con un `<iframe>` (no una simple redirección).

- **`src/Dashboard.gs`, `doGet()`**: añadido
  `.setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL)`. Por
  defecto Apps Script solo deja enmarcar sus páginas desde el propio
  Google - sin esto, el iframe de WordPress se habría quedado en blanco o
  bloqueado.
- Verificado con `curl -D -` contra la URL real en producción: la
  respuesta no lleva ninguna cabecera `X-Frame-Options` ni
  `Content-Security-Policy` que bloquee el enmarcado - nada del lado del
  servidor lo impide. La prueba definitiva (que WordPress lo cargue de
  verdad dentro del iframe anidado de Apps Script) queda pendiente de que
  el dueño lo pruebe en su web.
- Redesplegado sobre el mismo deployment (v18).
- Se le da al dueño un snippet HTML listo (bloque "HTML personalizado" de
  WordPress, sin plugin) con altura fija (`85vh`) y scroll propio - el
  histórico de picks crece sin límite, así que una altura dinámica exigiría
  `postMessage` entre el iframe y la página (fuera de alcance por ahora,
  YAGNI). Avisado también de que el aviso azul de Google ("Esta aplicación
  la ha creado un usuario de Google Apps Script") seguirá viéndose dentro
  del iframe, no se puede quitar desde el código del panel.
- Commits: (pendiente)

## 2026-08-27 (cont.) — Causa REAL de los avisos "sin datos"/"error" pegados: `display:flex` en CSS anulaba el atributo `hidden`, no un problema de JS
- El fix anterior (`ocultarTodosLosEstados_`, ver entrada previa) no
  resolvió el problema - el dueño lo siguió viendo tras redesplegar,
  incluso en incógnito (descartando caché) y con la URL limpia sin `/u/2/`
  (descartando el tema de cuentas de Google, que sí era un problema real
  aparte - ver más abajo).
- **Diagnóstico verificado, no supuesto**: en vez de seguir adivinando,
  se comprobó el HTML servido de verdad con `curl` directamente contra la
  URL de producción (saltándose el móvil y el caché del navegador por
  completo). El JS del fix anterior SÍ estaba publicado y SÍ se ejecutaba
  bien - el bug no estaba ahí.
- **Causa real**: `.estado-especial { display: flex; ... }` (la clase que
  comparten los avisos de "sin datos" y "error") le ganaba siempre al
  atributo HTML `hidden` - `hidden` solo oculta un elemento poniendo
  `display:none` por defecto, pero CUALQUIER regla CSS propia que fije
  `display` en ese elemento anula ese comportamiento por defecto. Como
  resultado, `elemento.hidden = true` desde JavaScript nunca ocultaba
  estos dos avisos en la práctica, sin importar cuántas veces se llamara
  ni en qué orden - se veían siempre, superpuestos al contenido real.
  `#contenido` y `#estadoCarga` no tenían este problema porque ninguna
  regla CSS les fija `display` explícitamente.
- Fix real: `.estado-especial[hidden] { display: none; }` - selector con
  más especificidad que `.estado-especial` sola, para que gane siempre que
  el atributo esté puesto. Verificado en el HTML servido en producción con
  `curl` (no solo "debería funcionar") antes de darlo por cerrado.
  Redesplegado (v17).
- **Aparte, un problema real distinto** que el dueño encontró de camino:
  el enlace no abría en Opera ni Chrome del móvil - la URL llevaba
  `/u/2/` (Google intentando enrutar por una cuenta de Google concreta del
  navegador) y además la VPN propia de Opera estaba activada, dando un
  error de Google Drive con esa cuenta en vez de servir el panel público.
  Resuelto identificando ambas causas; el dueño confirmó que en incógnito
  (sin cuentas ni VPN de por medio) sí cargaba.
- Commits: (pendiente)

## 2026-08-27 (cont.) — Mergeado el rediseño v5 del panel (worktree en segundo plano) + bug real encontrado por el dueño en móvil: avisos de vacío/error apilados encima de datos correctos
- El rediseño v5 (jerarquía hero + historial en tarjetas apiladas en
  móvil, ver entrada anterior "rediseño a fondo del panel v5") se lanzó en
  un worktree aislado en segundo plano, sin tocar `main` ni desplegar.
  Revisado el código a mano (correspondencia de ids, nombres de campo
  contra `getMetricasPanel()`, patrón `textContent`/`createElement` sin
  `innerHTML`) y mergeado a `main` sin conflictos (la rama solo tocaba
  `Panel.html`/`BITACORA.md`, `main` no había vuelto a tocar esos
  archivos desde el punto común). Redesplegado (v15).
- **Bug real encontrado por el dueño nada más verlo en el móvil**: el
  panel mostraba a la vez el aviso de "sin datos todavía", el aviso de
  "error cargando el panel" Y el contenido real (107 picks, cifras
  correctas) - los tres superpuestos. Causa: `pintarPanel`/`mostrarError`
  nunca ocultaban los OTROS estados antes de mostrar el suyo propio - si
  el navegador llega a ejecutar el script más de una vez (visto en real en
  móvil, probablemente un parpadeo de red estableciendo el puente de
  `google.script.run` con el iframe de Apps Script en la conexión inicial),
  cada aviso que se mostraba se quedaba ahí para siempre, apilándose en
  vez de sustituirse.
- Fix: `ocultarTodosLosEstados_()` nueva, llamada al principio de
  `pintarPanel` y `mostrarError` antes de decidir qué mostrar - los 4
  estados (carga/vacío/error/contenido) pasan a ser mutuamente excluyentes
  de verdad, el resultado final ya no depende de cuántas veces se haya
  llamado antes, solo de la última. Redesplegado (v16).
- Commits: (pendiente)

## 2026-08-27 (cont.) — Panel v5: rediseño visual a fondo (encargado a un agente en worktree aislado, sin backend nuevo)
El dueño calificó el diseño de la v4 de "absoluta basura" y pidió un salto
de calidad real, no otro retoque de colores, delegando el criterio visual
por completo ("investiga, decide tú"). Trabajo hecho en la rama
`worktree-agent-aa4063ea4f58fe9a8` (worktree aislado), sin `clasp push`/
`clasp deploy` - pendiente de revisión y merge por otra sesión antes de
publicar, porque este proyecto no tiene entorno de pruebas separado (todo
`clasp deploy` va contra el Apps Script real).

- **Investigación previa**: 4 búsquedas web sobre dashboards fintech/
  trading actuales (Stripe, Revolut, Robinhood, patrones genéricos 2026) +
  la skill `dataviz` (validador de paleta + specs de marcas/figuras). Del
  dashboard de Stripe: jerarquía por tipografía en vez de por color ("one
  hero metric visualized, everything else numeric"), tabular-nums solo en
  columnas de cifras alineadas. De Revolut: superficies "un escalón más
  claras" para elevar la cifra más importante. Del patrón de listas de
  transacciones bancarias: tarjeta apilada por fila en móvil en vez de
  tabla con scroll horizontal, con tabla clásica reservada para pantallas
  con hueco real.
- **Dirección elegida**: jerarquía tipográfica "hero + secundarias" (1
  tarjeta hero para "ganancia neta", con el gráfico de evolución
  incrustado como su visualización, + 4 tarjetas secundarias más pequeñas
  debajo) en vez de 5 tarjetas iguales compitiendo por atención; historial
  de picks como lista de tarjetas en móvil (con mensaje del tipster
  recortado a 3 líneas + botón "ver mensaje completo") que pasa a tabla
  clásica solo a partir de 720px de ancho (punto de corte propio, distinto
  del de las tarjetas de estadísticas, porque una tabla de 6 columnas
  necesita más hueco real). Descartado un layout tipo "bento grid" /
  multi-panel (Grafana/Vercel) por sobredimensionado para 5 métricas + 1
  gráfico + 1 tabla; descartado también un dashboard con filtros/exportado
  interactivo (patrón "progressive disclosure" de fintech 2026) por no
  encajar en una página estática sin backend propio ni llamadas nuevas a
  `google.script.run`.
- **`src/Panel.html`** reescrito de fondo (único archivo tocado -
  `src/Dashboard.gs` y `src/Config.gs` sin cambios, mismo contrato exacto
  de `getMetricasPanel()`):
  - Misma paleta de color ya validada (hex sin cambios); revalidada con
    `scripts/validate_palette.js --mode dark` de la skill `dataviz` - el
    par bueno/crítico falla la separación CVD en aislamiento pero está
    permitido explícitamente cuando lleva señal secundaria, que aquí
    siempre la lleva (flecha ▲/▼ +, en las cifras que pueden ser
    negativas, también signo +/- en el propio texto, no solo en la
    flecha).
  - Fix de accesibilidad de color: "Total jugado" y "% de aciertos" ya no
    se pintan en verde fijo (`positivo=true` hardcodeado en la v4) - no son
    una señal binaria bien/mal (un 20% de aciertos no es "malo" per se en
    value-betting), así que quedan en el tono de texto neutro. Solo
    ganancia neta, unidades y ROI llevan color dinámico + flecha, que son
    las que sí tienen un sentido real de ganancia/pérdida.
  - Fix de inconsistencia: `formatearEur` no anteponía "+" en positivo
    (`formatearUnidades` sí) - ahora ambas cifras en euros que pueden ser
    negativas llevan signo textual explícito, no solo color/flecha.
  - Estados de carga/vacío/error rehechos: esqueleto con shimmer en vez de
    un spinner+texto suelto, estado vacío y estado de error ahora
    visualmente distintos (antes compartían el mismo `<div id="mensaje">`
    genérico).
  - Sin ningún `innerHTML` en todo el archivo (la v4 ya usaba
    `textContent`/`createElement` para el mensaje del tipster, pero tenía
    un `innerHTML` residual con contenido siempre estático en `setValor` -
    se quitó igualmente, por rigor, aunque no era explotable).
- **Verificación sin navegador** (no se puede probar en vivo, el único
  Apps Script es el real): revisión manual de que cada id usado en el JS
  existe en el HTML y viceversa, y de que cada campo leído en el cliente
  (`fechaLabel`/`cuota`/`unidades`/`canodromo`/`galgo`/`mensaje`,
  `unidadesNetasEur`/`unidadesNetas`/`stakeTotalEur`/`roiPct`/
  `pctAciertos`/`evolucion`) coincide exactamente con lo que devuelve
  `getMetricasPanel()`. Además, verificación automática con Node: el
  bloque `<script>` se parseó con `new Function()` (sin errores de
  sintaxis) y se comprobó el balance de etiquetas HTML y de llaves CSS con
  dos scripts ad-hoc.
- Pendiente real (no de esta tarea, gap preexistente): `getMetricasPanel()`
  llama a `getSheet_`/`getHeaderIndex_`, que no están definidas en ningún
  `.gs` del repo todavía - `Main.gs`/`Setup.gs`/`AI.gs` (mencionados en
  comentarios y en `docs/BITACORA.md` como ya escritos) no están en este
  worktree. No se ha tocado por ir fuera del alcance de un rediseño visual
  y no ser un bug introducido aquí.
- Commits: (este commit, rama `worktree-agent-aa4063ea4f58fe9a8` - pendiente
  de revisión y merge a `main`).

## 2026-08-27 — Panel v4: revertida la ventana de 30 días ("no me cuadran los números"), tabla de últimos picks sustituida por el historial completo con canódromo/galgo/mensaje, tarjeta nueva de unidades en crudo
El dueño reportó que los números del panel no le cuadraban con la ventana
de 30 días de la v2/v3, y pidió tres cosas directas: (1) volver a todo el
histórico en las tarjetas/gráfico, (2) sustituir la tabla de "últimos 10
picks" por el historial COMPLETO (mismo filtro que las tarjetas -
`oculto=false`, resuelto - pero sin límite de filas ni de fecha), con
canódromo, galgo(s) y el mensaje original del tipster, para poder
revisarlas una a una, y (3) una tarjeta más con las unidades netas en
crudo (sin convertir a euros) para poder cuadrar el número en € contra la
hoja a mano.

- **`src/Dashboard.gs`**: quitadas `DIAS_VENTANA_PANEL`/
  `LIMITE_ULTIMOS_PICKS` y el filtro de fecha en `getMetricasPanel()` -
  `calcularMetricas_` vuelve a recibir todas las filas, como en la v1.
  `calcularUltimosPicks_(filas, limite)` renombrada a
  `calcularHistoricoPicks_(filas)` (sin parámetro de límite, siempre
  devuelve todo lo que pasa el filtro) y ampliada para llevar también
  `canodromo`/`galgo`/`mensaje` - columnas fórmula que YA existían en la
  hoja real (`crearApuestas_` en `Setup.gs`), simplemente no se leían
  todavía desde el panel. Test manual renombrado a
  `test_calcularHistoricoPicks_`, reforzado para comprobar el orden de las
  3 filas completas en vez de solo un top-2.
  `getMetricasPanel()` añade el campo `unidadesNetas` (mismo dato que
  `unidadesNetasEur` pero SIN multiplicar por `TASA_EUR_POR_UNIDAD`).
- **`src/Panel.html`**: subtítulo "Últimos 30 días" → "Todo el histórico";
  5ª tarjeta "Unidades ganadas" (en unidades, no €); la sección de "Últimos
  picks" pasa a ser "Historial de picks" con 3 columnas nuevas
  (Canódromo/Galgo/Mensaje), renderizadas igual que el resto de la tabla
  (`textContent`, no `innerHTML` - sigue sin riesgo de inyección pese a
  que `mensaje` es la primera columna con texto libre real, el mensaje
  original del tipster). Grid de tarjetas ajustado a 5 (columna doble para
  la 5ª en el layout de 2 columnas de móvil, para que no quede huérfana
  con hueco vacío al lado).
- Revisión de calidad: confirmado con grep que no queda ninguna referencia
  a la ventana de 30 días ni al límite de 10 en todo el repo (el revert es
  completo, no parcial); confirmado que `unidadesNetas` y
  `unidadesNetasEur` no se cruzan entre sí.
- Redesplegado sobre el mismo deployment.
- Commits: (pendiente)

## 2026-08-26 (cont.) — Panel v3: bug real de la tabla de últimos picks (mostraba euros en vez de unidades) + rediseño visual completo, a petición del dueño ("mejora el diseño")
El dueño reportó dos cosas y delegó el criterio visual explícitamente
("lo dejo en tus manos no estoy atento"), así que se implementó
directamente sin más preguntas, con una revisión de calidad antes de
desplegar y commitear.

- **Bug real**: la columna "Unidades" de la tabla de últimos picks
  (añadida en la ampliación de esta misma tarde) mostraba el valor
  convertido a euros (`unidadesEur`, multiplicando por
  `TASA_EUR_POR_UNIDAD`) en vez de las unidades tal cual, que es lo que se
  había pedido originalmente ("las unidades ganadas por apuesta") y lo que
  el dueño confirmó ("las unidades ganadas son numeros"). Las 4 tarjetas
  principales (ganancia neta, total jugado) SÍ se quedan en euros - esa
  parte no cambia, es la excepción ya documentada en `CLAUDE.md`. Fix en
  `getMetricasPanel()` (`src/Dashboard.gs`): el campo pasa de
  `unidadesEur` a `unidades` (sin multiplicar por la tasa). Verificado con
  grep que no queda ninguna referencia a `unidadesEur` en el repo.
- **Rediseño visual de `src/Panel.html`**: sigue mobile-first (misma
  estructura de grid 2→4 columnas, mismos tokens de color validados con la
  skill `dataviz`), pero con más cuidado de detalle - sombras suaves en
  las tarjetas, etiquetas en mayúsculas con letter-spacing, flechita
  ▲/▼ delante de los positivos/negativos (para que el color nunca sea la
  única pista de si es un número bueno o malo, regla de accesibilidad de
  `dataviz`), spinner de carga animado en vez de solo texto, filas
  alternas en la tabla de picks, ancho máximo centrado en pantallas
  anchas.
- Revisión de calidad: confirmado el camino completo del fix (sin ningún
  resto de conversión a euros en la tabla), sin riesgo de inyección en el
  `innerHTML` nuevo (solo recibe contenido generado por el propio código,
  nunca texto de la hoja sin pasar por `textContent`), CSS confirmado
  mobile-first de verdad tras leer el diff completo. Encontrada y
  eliminada una variable CSS muerta (`--linea-grafico-suave`, sin usar).
- Redesplegado sobre el mismo deployment (v13).
- Commits: (pendiente)

## 2026-08-26 (cont.) — Bug real: 11 reenvíos de picks antiguos cargados con la fecha de llegada en vez de la fecha real de la carrera; uno de ellos dio un "perdió" FALSO. Arreglada la causa raíz (mensajes_crudos no guardaba si el mensaje era un reenvío)
- Tras arreglar el login de NordVPN (entrada anterior), quedaban 10
  apuestas en "pendiente" del bloque de 11 mensajes cargados a mano por
  cuota de Gemini agotada. El usuario, viendo el detalle exportado de la
  hoja, señaló que la causa no era la que yo había dado (Central Park sin
  reunión hoy) sino que **las fechas de esos picks estaban mal**.
- Confirmado buscando cada galgo por nombre en `galgos_master.parquet`
  (sin asumir nada, cruzando hora+trampa): los 11 mensajes eran
  **reenvíos de picks de días anteriores** (21, 22, 24 y 25 de agosto),
  no picks nuevos de hoy 26/08 - el tipster los reenvió todos juntos y
  `fecha_recibido` (26/08) es la fecha de reenvío, no la de la carrera.
- **Hallazgo grave, no solo "quedan pendientes"**: `message_id 127`
  (Moaning May, "perdió" ya registrado) estaba MAL - Harlow SÍ tiene una
  carrera real hoy a esa misma hora y trampa (12:54, T3), pero con OTRO
  GALGO. El fallback de "trampa ganadora" no verifica identidad del
  galgo, solo canódromo+fecha+hora+trampa - al llevar la fecha
  equivocada, comparó la apuesta contra una carrera que no tenía nada que
  ver, y dio "perdió" por pura coincidencia de trampa. Tras corregir la
  fecha a la real (21/08), sigue resolviendo "perdió", pero esta vez
  verificado de verdad (con `cuota_final` real, no vacío como antes).
- **Causa raíz real**: `mensajes_crudos` nunca guardaba si un mensaje era
  un reenvío (`msg.forward_date`) - el schema solo tenía
  `message_id/fecha_recibido/contenido/foto_file_id/estado`. `doPost`
  SÍ tenía esa información disponible en el momento de guardar el
  mensaje crudo, pero se perdía en cuanto la extracción de Gemini
  fallaba (estado=error) - `reintentarMensajesConError()` (y mi propia
  carga manual del bloque anterior) no tenían forma de recuperarla,
  así que ambos caían en usar `fecha_recibido` como `fecha_pick`. No es
  un bug exclusivo de mi carga manual: **cualquier reenvío real que
  errorara por cuota de Gemini habría sufrido lo mismo** en el flujo
  automático normal.
- **Arreglado en el código, no solo en el dato**:
  - `src/Config.gs`: nueva columna `fecha_forward` en
    `COLUMNAS_MENSAJES_CRUDOS` (vacía si no es reenvío).
  - `src/Main.gs`: `calcularFechaPick_(msg, fechaRecibido)` sustituida
    por `extraerFechaForward_(msg)` (devuelve `null` si no es reenvío,
    para poder persistirlo). `doPost` la calcula y la guarda en
    `mensajes_crudos` ANTES de intentar la extracción - así sobrevive
    aunque Gemini falle. `manejarPickNuevo_` y
    `reintentarMensajesConError()` usan `fechaForward || fechaRecibido`
    (esta última ahora sí lee la columna nueva en vez de asumir
    `forward_date: null` a ciegas).
  - `src/Sheets.gs`: `appendMensajeCrudo` acepta y escribe el nuevo
    parámetro `fechaForward`.
  - Añadida la columna `fecha_forward` a la hoja real en producción vía
    `gspread` (cabecera nueva, sin tocar `setupSheet`). `clasp push`
    desplegado.
- **Corrección de los datos ya cargados**: `fecha_pick` actualizado en
  `apuestas` y `apuestas_patas` para los 11 `message_id` (127→21/08,
  128→21/08, 129→21/08, 130→21/08, 135→21/08, 136→21/08, 139→22/08,
  143→24/08, 144→24/08, 147→25/08, 148→25/08). Relanzado
  `picks-resultados.service` a mano: encontró las 4 fechas nuevas
  (results_enriched.parquet ya las tenía, ~36-79 filas cada una) e
  insertó 34 filas nuevas en `resultados_galgos`.
- **Resultado final tras la corrección** (verificado con `gspread`, no
  supuesto): de los 11, **8 perdieron** (incluido `127`, mismo veredicto
  pero ahora con datos reales) y **3 GANARON** (`143` Dapper Beth +4,98u,
  `147` Cyclers Storm +9u, `148` Foxwood Dolly +14u) - picks que se
  habrían quedado marcados como perdidos/pendientes sin este arreglo.
  Neto del bloque: -10,02u (antes de corregir, el dato visible sugería
  un neto mucho peor, con 10 de 11 en pendiente y 1 falso "perdió").
  `message_id 139` (Magical Keith) sigue "perdió" correcto pero sin
  `cuota_final` (fuera de podio, el job diario de `vm_job_dog_forms.py`
  lo recogerá cuando el galgo vuelva a correr).
- Commits: (pendiente)

## 2026-08-26 (cont.) — Login de NordVPN arreglado en la VM de Proyecto Galgos (llevaba roto desde mayo) - desatascado el scraper de resultados en producción
- El usuario preguntó por qué había varios "pendientes" de hoy que no
  tenían sentido. Investigado con acceso SSH (reautorizado dos veces -
  la sesión de Tailscale SSH había caducado a mitad de sesión, el
  usuario autorizó los nuevos enlaces).
- **Diagnóstico inicial (parcialmente incorrecto, corregido en la
  entrada siguiente)**: `Central Park` no tenía ninguna carrera hoy
  26/08 según Racing Post en vivo (comprobado con dos llamadas
  distintas: `results/blocks.sd` y `meeting/blocks.sd`) - cierto, pero
  la verdadera explicación de por qué esos picks no encajaban era otra
  (ver entrada siguiente): las fechas de esos picks estaban mal, ni
  siquiera eran de hoy.
- **Bug real encontrado y arreglado esta vez sí**: `galgos-poll-results`
  (scraper de resultados de Proyecto Galgos) llevaba desde las 12:08 de
  hoy atascado en un bucle infinito probando los 32 países de la
  rotación de VPN (`src/utils/vpn.py` de Proyecto Galgos) sin éxito -
  Racing Post le puso rate-limit y la rotación no podía sacarlo del
  apuro porque **NordVPN llevaba desconectado de sesión desde mayo**
  (`nordvpn account` → "You're not logged in"; `cli.log` mostraba
  reintentos automáticos fallidos TODOS los días desde el 9 de mayo).
- El usuario tenía acceso a la cuenta NordVPN de Proyecto Galgos
  (`adri_200fcn@hotmail.com`). Las "Service credentials" del panel
  (usuario/contraseña) son para túnel manual OpenVPN/IKEv2, no sirven
  para el login del CLI/demonio `nordvpn`. Login completado con el flujo
  de navegador (`nordvpn login`, sin `--token`): genera una URL de
  intento: la primera vez no funcionó por dos motivos que se fueron
  resolviendo -
  1. cortar el proceso con un `timeout` antes de que el usuario pudiera
     completar el login en el navegador,
  2. y sobre todo: la pantalla final "Great – you're in!" tiene un botón
     "Continue" que en realidad intenta abrir un enlace `nordvpn://...`
     (pensado para que lo capture la app de escritorio) - sin una app
     instalada capturándolo, hacía falta copiar ese enlace a mano
     (clic derecho → copiar dirección del enlace) y pasarlo por
     `nordvpn login --callback "ese enlace"` para completar el login.
  Con el token fresco (generado y usado en la misma respuesta, sin
  pausas - los anteriores habían caducado por el tiempo transcurrido)
  completó: `nordvpn account` mostró la cuenta real, `nordvpn connect
  Spain` conectó sin problema.
- **Efecto inmediato**: el proceso de `galgos-poll-results` que llevaba
  atascado desde las 14:28 detectó la sesión nueva sola (sin reiniciarlo)
  y terminó su ciclo con éxito (`job_poll_results OK (981s)`).
- **Fuera de alcance de este repo**: todo esto es infraestructura de
  Proyecto Galgos (VPN, scraper), no de `picks-premier-galgos` - no se
  ha tocado ningún archivo de ese proyecto, solo se ha usado el CLI de
  NordVPN y comprobado logs/estado vía SSH, con permiso explícito del
  usuario en cada paso.
- Commits: (pendiente)

## 2026-08-26 (cont.) — Fase 8 completa: panel de métricas (`doGet`/`Panel.html`), y ampliado el mismo día a petición del dueño (ventana de 30 días, últimos picks, rediseño mobile-first)
Cierra la Fase 8 del `PLAN.md` (roadmap). Construido con `superpowers:subagent-driven-development` (implementador + revisor de spec + revisor de calidad por tarea, con 2 rondas de fixes reales encontradas por los revisores) y luego ampliado directamente a petición del dueño, con una revisión de calidad final antes de commitear.

**Build inicial (versión 1 del panel):**
- `src/Dashboard.gs` (nuevo): `calcularMetricas_` (función pura, filtra `oculto=false` y `resultado_final` en gano/perdio, calcula unidades netas/stake total/ROI%/% aciertos/evolución acumulada) + `getMetricasPanel()` (lee `apuestas`, delega en `calcularMetricas_`, convierte a euros) + `doGet(e)` (sirve la plantilla HTML).
- `src/Panel.html` (nuevo): 4 tarjetas + gráfico de evolución (Google Charts). **No se llama `Dashboard.html`** como decía el plan original: Apps Script no permite que un `.gs` y un `.html` compartan nombre base en el mismo proyecto (`clasp push` lo bloquea con "A file with this name already exists") - se descubrió al implementar, se renombró el HTML a `Panel.html` y se actualizó la única referencia (`doGet`). Revisado y aprobado como adaptación justificada a una limitación real de la plataforma, no una desviación del spec.
- **Excepción de euros**: el panel muestra conversión a euros (1 unidad = 250€, `TASA_EUR_POR_UNIDAD` en `Config.gs`) pese a que el resto del proyecto solo usa unidades - decisión explícita del dueño, a sabiendas de que el panel es de acceso público por enlace (sin login). Documentada en `CLAUDE.md`.
- Desplegado sobre el MISMO deployment ID que ya usa el webhook de Telegram (`AKfycbynXi...`, ahora v11 en este momento) - Apps Script enruta GET→`doGet` y POST→`doPost` dentro del mismo Web App, sin crear una URL nueva ni tocar el bot.
- Spec: `docs/superpowers/specs/2026-08-26-panel-metricas-design.md`. Plan: `docs/superpowers/plans/2026-08-26-panel-metricas.md`.
- Revisiones reales encontradas y corregidas antes de dar la tarea por cerrada: el test de `calcularMetricas_` no ejercitaba el `.sort()` de la evolución ni el guard de `stakeTotal===0` (arreglado añadiendo 2 casos aislados al test); 2 referencias obsoletas a "Dashboard.html" quedaron tras el rename (en un comentario de `Dashboard.gs` y en `CLAUDE.md`, corregidas en un commit de seguimiento).

**Ampliación misma tarde (versión 2), pedida directamente por el dueño en conversación, implementada sin subagentes dado el tamaño pequeño (con una revisión de calidad final antes de commitear):**
- Las tarjetas y el gráfico pasan de "todo el histórico" a **últimos 30 días** (`DIAS_VENTANA_PANEL`, filtro por `fecha_pick` aplicado en `getMetricasPanel` antes de llamar a `calcularMetricas_` - esa función sigue siendo agnóstica de la ventana).
- Tabla nueva **"Últimos picks"**: los 10 más recientes ya resueltos (`LIMITE_ULTIMOS_PICKS`), fecha/cuota/unidades ganadas en €, **sin acotar a los 30 días** (decisión aparte del dueño: quiere ver los últimos resueltos de verdad, no solo si caen dentro de la ventana). Función pura nueva `calcularUltimosPicks_` con su propio test manual (mismo patrón que `calcularMetricas_`).
- **Rediseño visual mobile-first**: se cargó la skill `dataviz` del proyecto para no improvisar colores - paleta oscura validada (línea del gráfico en azul `#3987e5`, positivo/negativo en verde/rojo de la paleta de estado del sistema, contraste ≥3:1 comprobado con el validador del skill contra la superficie oscura). CSS base pensado para pantalla estrecha (grid de 2 columnas, sin scroll horizontal) con una única media query (`min-width:640px`) que solo mejora el layout en pantallas anchas, nunca lo invierte.
- Revisión de calidad final: lógica de filtrado/orden/límite verificada correcta contra el esquema real (`fecha_pick`/`cuota` siempre presentes por diseño, ver `Sheets.gs`/`AI.gs`); tabla nueva renderizada con `textContent`/`createElement` (sin `innerHTML` con datos del servidor, sin riesgo de inyección pese a ser página de acceso público); único hallazgo real aplicado: guarda `fechaPick instanceof Date` añadida también en `calcularUltimosPicks_` por consistencia con el filtro de ventana (robustez, no bug activo con el esquema actual).
- Redesplegado sobre el mismo deployment (v12).
- Commits: (pendiente)

## 2026-08-26 (cont.) — Carga manual de los 11 picks bloqueados por cuota de Gemini + descubierta y explotada la fuente de datos "cards" para completar el histórico sin peticiones en vivo
El usuario, antes de irse a dormir, pidió cuatro cosas: (1) revisar y cargar
yo mismo los picks que se habían quedado en `error`, (2) marcarlos para que
Gemini no vuelva a intentarlo con ellos, (3) sacar los resultados
pendientes, y (4) resolver el resto del histórico de `dog_id` con una
estrategia concreta que él mismo propuso: ir primero a las "cards" ya
guardadas (no a "resultados" en vivo, que puede no tener ni la carrera ni
el galgo si quedó fuera de podio), y si hace falta ir en vivo, esperar 2
días entre petición al mismo perro (el dato del historial de un galgo solo
cambia cuando vuelve a correr).

**1) Los 11 mensajes en `error`** (127, 128, 129, 130, 135, 136, 139, 143,
144, 147, 148): todos simples, con datos completos y sin ambigüedad salvo
uno. Leídos a mano desde `mensajes_crudos` (vía `gspread`, sin usar Gemini
en absoluto) y cargados directamente en `apuestas`/`apuestas_patas` con el
mismo esquema que usa `appendApuestaConPatas` (`src/Sheets.gs`), verificando
antes que ninguno estuviera ya cargado. Caso dudoso: `message_id 129`
("Cuota 3.75 (Bet365) 3.25 (sportium)🔥") - el emoji va pegado al último
precio citado, mismo patrón que en los mensajes sin ambigüedad de la
tanda (127/128, donde el emoji va pegado al precio jugado) → se tomó
3.25. Verificadas las 11 filas con `gspread` (`fields=...FORMATTED_VALUE`):
todas resuelven `resultado_final=pendiente` sin `#ERROR!` (esperado, las
carreras de hoy 26/08 aún no se habían corrido). Marcadas `estado=procesado`
en `mensajes_crudos` - con eso `reintentarMensajesConError()` las ignora
solas (filtra por `estado=error`), sin tocar nada del código.

**2) `picks-resultados.service` (el job de la VM de Fase 7) se ejecutó
manualmente** (`systemctl start`) para no esperar al primer disparo
programado del día (10:35 Madrid) - resolvió 5 patas pendientes que ya
tenían datos en `results_enriched.parquet` (17 filas de podio insertadas).

**3) Hallazgo central de la sesión: `galgos_master.parquet` y
`galgos_json_sidecar.parquet` (en la VM, `/opt/galgos/data/master/`) son
exactamente las "cards ya guardadas" que proponía el usuario, y tienen
mucho más de lo esperado:**
- `galgos_master.parquet` (161.832 filas): una fila por galgo por carrera
  (card, no resultado), con `Canódromo/Fecha/Race_ID/Dog_ID/Trap/Nombre` -
  permite identificar `dog_id`+`race_id` de CUALQUIER carrera pasada sin
  ninguna petición en vivo, cruzando por canódromo+fecha+**nombre del
  galgo** (no por hora: la `Hora` de esta card, igual que `rTime` en
  `results_enriched.parquet`, va en UTC, mismo desfase de +1h respecto a
  la hora que escribe el tipster - confirmado de nuevo con `Rhombus Lass`,
  card a las `11:21` UTC vs `12:21` que escribió el tipster. Emparejar por
  nombre evita depender de ese desfase y de que el horario real de la
  carrera pueda moverse unos minutos respecto al programado).
- `galgos_json_sidecar.parquet` (148.831 filas, 1.36GB): trae
  `Raw_Dog_Details_JSON` completo de cada aparición en card de cada galgo,
  con `details.forms` - **hasta 60 carreras PASADAS de ese galgo, con
  posición Y cuota SP exacta** (`rInstId`=race_id, `raceTime`, `trapNum`,
  `rOutcomeDesc`, `oddsFrctnNumer`/`oddsFrctnDenom`, `trackId`...). Esto
  es exactamente el mecanismo que describía el usuario: la carrera de
  hace semanas que quedó fuera de podio aparece en el `forms` de
  cualquier card MÁS RECIENTE de ese mismo galgo (su próxima carrera trae
  el historial actualizado) - sin tocar Racing Post en vivo para nada.
  Bug propio encontrado al implementarlo: la primera versión solo miraba
  la PRIMERA fila del sidecar de cada `dog_id` (podía ser una card vieja,
  con una ventana de 60 carreras que aún no llegaba a la carrera buscada)
  - arreglado para mirar TODAS las apariciones guardadas de ese galgo y
  quedarse con la que sí trae la carrera.
- Cargando `read_table(...,filters=...)` sobre el sidecar completo la VM
  se quedó sin memoria (proceso matado por el kernel, 3.7GB de RAM) -
  arreglado leyendo por lotes con `iter_batches` y descartando en el acto
  lo que no hace falta, sin materializar el fichero entero.

**Resultado sobre las 29 patas fuera de podio pendientes de detalle**
(dog_id/cuota_final/url_carrera - el gano/perdio YA estaba bien resuelto
por el fallback de trampa ganadora, esto es solo para el informe de
Looker Studio):
- Emparejadas por nombre con `galgos_master.parquet`: 27/29 directas; las
  otras 2 fallaban por un matiz del propio texto del tipster ("Hollyoak
  Ethel **SIN el favorito**" trae una anotación pegada al nombre; "Imokilli
  Arminta" es una errata de una letra sobre el nombre real registrado,
  "Imokilly") - resueltas a mano comprobando el nombre real en la card.
- De esas 29, 20 ya tenían su carrera en el historial `forms` guardado -
  insertadas en `resultados_galgos` (deduplicando por `(race_id, trampa)`,
  no solo por `race_id`, para no confundir "ya existe la carrera" con "ya
  existe ESTA trampa de la carrera").
- Cruce de seguridad: una de las 20 (`message_id 76`, Betgoodwin Eddy) YA
  tenía fila exacta en `resultados_galgos` de una ejecución anterior del
  job de la VM (**1º puesto real**, no "trampa ganadora" - esa pata de la
  doble ya estaba bien resuelta desde antes, solo aparecía en la lista
  porque su pata hermana de la misma apuesta combinada seguía sin datos).
  Se comprobó a fondo para descartar que fuera una apuesta ganadora
  marcada como perdida por error - no lo era, coincidencia de que dos
  carreras distintas de Sheffield tuvieran el mismo galgo protagonista.

**4) Bug real encontrado de paso, no relacionado con lo de arriba:
`url_carrera` llevaba TODO el proyecto quedándose en blanco para las filas
de podio** que escribe `vm_job_resultados_galgos.py` en cada pasada
normal - el job nunca llegó a construirla (el comentario del propio código
decía que era una limitación deliberada, pero mirando el resto de campos
disponibles en `results_enriched.parquet` sí tiene `track_id`, todo lo que
hace falta para construir la URL). Arreglado en
`scripts/vm_job_resultados_galgos.py` (usa el `track_id` que el parquet ya
trae) y desplegado a la VM. Backfill retroactivo de las 285 filas ya
existentes que se habían quedado sin `url_carrera` (script puntual con un
mapa canódromo→track_id sacado de `results_enriched.parquet`, sin tocar
más columnas). Verificado: 0 apuestas con `resultado_final` resuelto y
`url_carrera` en blanco tras el backfill.

**5) Nuevo job recurrente: `scripts/vm_job_dog_forms.py`** (+ `systemd`
`picks-dog-forms.service`/`.timer`, `scripts/deploy/`), 1 vez al día
(06:00 Madrid) - automatiza exactamente la estrategia de arriba para las
patas que vayan quedando fuera de podio en el futuro:
  1. Localiza en `apuestas_patas` las patas con `resultado_pata=perdio`
     (ya resueltas por trampa ganadora) pero sin `cuota_final_pata`.
  2. Identifica `dog_id`/`race_id` por nombre en `galgos_master.parquet`.
  3. Busca la carrera en el `forms` ya guardado del galgo (gratis, sin red).
  4. Solo si no está ahí: **una única petición en vivo** a
     `dog/blocks.sd?dog_id=...&race_id=...` (mismo endpoint que usa
     Proyecto Galgos en `scripts/legacy/test_blocks_form_vs_details.py`,
     con `curl_cffi` `impersonate="chrome124"` igual que
     `src/utils/vpn.py` - pero **sin** su rotación de VPN, que el
     2026-08-26 anterior se comprobó rota - ni reintentos: un fallo aquí
     simplemente se reintenta en la siguiente pasada diaria).
  5. **Enfriamiento de 2 días por `dog_id`** (pedido explícito del
     usuario) guardado en `/opt/picks-premier-galgos/dog_lookup_cooldown.json`
     en la VM (fuera de la Sheet, es estado interno del job) - si un
     galgo no ha vuelto a correr, no tiene sentido volver a preguntar
     hasta pasado ese margen.
- Probado en la VM nada más desplegarlo: de las 8 patas que aún quedaban
  sin resolver del punto 3, 2 no tenían `dog_id` localizable por nombre
  (los 2 casos de errata/anotación de arriba, resueltos a mano aparte;
  **limitación conocida**: el emparejamiento por nombre exacto de este
  job no captura erratas del tipster ni anotaciones pegadas al nombre -
  aceptable para un puñado de casos raros, no vale la pena una
  coincidencia difusa para esto), y de las 6 restantes, **3 se resolvieron
  con una sola petición en vivo** (Ballymac Ralf, Start The Engine, Slick
  Senator) - las otras 3 (Da Motor Man, Jacktavern Turbo, Bockos Buster) no
  aparecían aún en ningún `forms` ni en vivo (esos galgos no han vuelto a
  correr todavía) - quedan en enfriamiento hasta dentro de 2 días.
- **Balance final de la noche**: de las 26 patas fuera de podio con
  `gano`/`perdio` correcto pero sin detalle, quedan solo **4** sin
  `cuota_final` (Hollyoak Ethel, Da Motor Man, Jacktavern Turbo, Bockos
  Buster) - las 4 genuinamente a la espera de que su galgo vuelva a
  correr; el job diario las recogerá solo en cuanto pase.
- Commits: (pendiente)
- Con el acceso SSH a la VM ya autorizado por el usuario (Tailscale SSH pedía
  verificación de identidad vía navegador; el usuario abrió el enlace y
  autorizó la sesión), se comprobaron dos accesos pedidos explícitamente:
  **GitHub** (`git ls-remote` contra
  `https://github.com/davilapilila-design/Proyecto_Galgos.git` respondió sin
  pedir credenciales, `HEAD` coincide con el clon local) y **la VM**
  (`ssh root@galgos-vm.tailc02685.ts.net` conecta bien; VM en `Etc/UTC`). No
  hay `gh` CLI instalada, pero no hace falta para leer/clonar el repo.
- Con SSH ya disponible se exploró `/opt/galgos/repo/data/historical/` en
  caliente en vez de conformarse con el backup de Drive (hasta 1 día de
  retraso, ver entrada anterior), y apareció una fuente mejor:
  **`results_enriched.parquet`** (mismo esquema que `results_historical.parquet`,
  139.341 filas frente a 110.622): trae el canódromo ya en Title Case
  ("Central Park", coincide con `apuestas.hipodromo` sin normalizar nada) y
  muchas más filas con posición 4/5/6 (11.398/10.616/6.314, frente a 0 en el
  otro fichero) — la mayoría de carreras traen el campo completo, no solo el
  podio. Copiado a esta sesión por `scp` (lectura, sin ejecutar nada pesado
  en la VM).
- **Importante, aclarado explícitamente con el usuario**: el acceso SSH de
  esta sesión depende de que este ordenador y esta sesión estén encendidos —
  no puede ser el mecanismo de producción. Sirve solo para la investigación
  y la prueba de hoy. El mecanismo recurrente (backfill completo + día a día)
  queda pendiente de construir como un script nuevo que corra **en la propia
  VM** (nuevo `systemd timer`, sin tocar `job_poll_results.py`), leyendo el
  parquet en local y empujando a `resultados_galgos` vía `gspread` — se
  decide y se construye después de esta prueba, no antes.
- **Rediseñadas `posicion_auto`/`resultado_final` en `src/Setup.gs`**: el
  diseño original solo resolvía una apuesta si la fila exacta de esa trampa
  aparecía en `resultados_galgos` (canódromo+fecha+hora+trampa). Pero ni
  `results_historical.parquet` ni `results_enriched.parquet` garantizan fila
  para TODAS las trampas de una carrera (ver entrada anterior, caso real
  confirmado: `More Firepower`, Harlow 22/07/2026, trampa 2, sin fila propia
  en ninguno de los dos ficheros aunque la carrera esté resuelta) — esas
  apuestas se habrían quedado en "pendiente" para siempre pese a haber
  perdido con toda certeza. Fix: si mi trampa no tiene fila exacta, se busca
  igualmente la trampa que sí ganó esa carrera (`posicion=1`); si existe y
  no es la mía, `resultado_final="perdio"` (no es inferencia ambigua: si mi
  trampa hubiera ganado, la búsqueda exacta ya la habría encontrado, porque
  el ganador siempre tiene fila). Los no-corredores (`posicion="N"`) se
  dejan aparte, en "pendiente" a propósito (normalmente implica devolución
  de stake, no es un simple gano/perdio).
- **Bug encontrado y corregido durante la prueba (no hipotético, verificado
  en caliente)**: la primera versión de la fórmula de "trampa ganadora"
  comparaba `resultados_galgos!F2:F5000="1"` (columna `posicion`, numérica)
  contra el texto literal `"1"` — en Google Sheets, a diferencia de Excel,
  el operador `=` **no hace coerción de tipos**: el número `1` comparado con
  el texto `"1"` da `FALSE`. Diagnosticado aislando la subexpresión en una
  celda suelta de la hoja real (mismo método que los bugs de hoy temprano):
  `=resultados_galgos!F2="1"` con F2=1 (número) dio `FALSE`. Fix: forzar
  ambos lados a texto con `&""` antes de comparar
  (`resultados_galgos!$F$2:$F$5000&""="1"`) — verificado que tras el cambio
  la búsqueda sí encuentra la trampa ganadora.
- **Prueba end-to-end con 2 picks reales** (no todo el histórico todavía,
  a petición del usuario — probar primero): `message_id 3` (Droopys Rarity,
  Central Park, 21/07/2026, trampa 3, terminó 3º — ya estaba en la hoja) y
  `message_id 5` (More Firepower, Harlow, 22/07/2026, trampa 2, fuera de
  podio — añadido a la hoja real desde `data/apuestas.csv`, backfill ya
  generado el 2026-08-20). Insertadas en `resultados_galgos` las 6 filas
  completas de ambas carreras (3 puestos cada una), con la hora ya corregida
  de UTC a hora de Reino Unido (`Europe/London`, con `zoneinfo` de Python —
  ver el porqué del desfase en la entrada anterior). Verificado con
  `gspread`/API de Sheets (`fields=...effectiveValue`, sin pedir nada al
  usuario): `message_id 3` → `posicion_auto=3, resultado_final=perdio,
  fuente_resultado=auto` (camino de fila exacta); `message_id 5` →
  `posicion_auto="", resultado_final=perdio, fuente_resultado=auto` (camino
  de trampa ganadora, sin fila propia). Revisada además una muestra amplia
  de filas sin resultado (P4:P50, P500, P1000, P2000): todas en "pendiente",
  0 errores.
- Fórmulas nuevas aplicadas directamente sobre el rango existente `O2:S2000`
  de `apuestas` vía `gspread` (no se ha vuelto a ejecutar `setupSheet`, que
  borraría los datos reales ya cargados) y en paralelo actualizado
  `src/Setup.gs` para que futuras hojas nazcan ya con el diseño correcto.
  Pendiente `clasp push` + nueva versión/redeploy para que el código
  desplegado coincida con el que ya está corregido a mano en la hoja real
  (mismo patrón que los fixes de hoy temprano).
- Pendiente (fuera de este trabajo): decidir con el usuario si se hace el
  backfill completo jul-ago desde `results_enriched.parquet` y construir el
  script recurrente en la VM.
- Commits: (pendiente)

## 2026-08-25 (cont.) — Investigación Fase 7: "exports del algoritmo" resultan ser el mismo backup en Drive de Proyecto Galgos, con dos hallazgos nuevos importantes
- El usuario propuso reusar "los exports del proyecto del algoritmo de
  predicción" en vez de (o adelantando) el hook original de `PLAN.md`
  sección 7 en `job_poll_results.py`. Antes de tocar código, exploradas
  `Proyecto Galgos` (clon activo) y `Proyecto_Galgos` (clon viejo,
  abandonado desde finales de mayo 2026 según su propio historial git) —
  mismo repo, no hay overlap de código con `picks-premier-galgos`.
- Confirmado con el usuario: no existe una copia de seguridad en Sheets
  aparte (fue un lapsus). La copia real es la ya documentada en el
  `README.md` de Proyecto Galgos: `rclone` copia `data/` de la VM a Google
  Drive cada noche (`galgos-backup`, 03:30 Madrid) — la misma fuente que en
  producción usa `job_poll_results.py`, con hasta 1 día de retraso.
- `results_historical.parquet` de ese backup **es accesible desde esta
  sesión** vía el conector de Google Drive (pertenece a
  `davilapilila@gmail.com`, no a `premiergalgos@gmail.com`, pero aparece en
  las búsquedas igual, ya compartido). Descargado (decodificado desde el
  resultado base64 del conector, sin pasar por el contexto de la
  conversación) y verificado con pandas: 110.622 filas, 2026-01-29 a
  2026-08-24 — cubre de sobra jul-ago 2026 del backfill. Columnas: `Fecha,
  Canodromo, race_id, rTime, distance, raceGrade, dogId, name, trap,
  position, status, winnersTimeS, rpDistDesc, fract, isNonRunner,
  withdrawreason, track_id`.
- **Canódromo**: los 7 nombres del tipster (Central Park, Star Pelaw,
  Harlow, Hove, Monmore, Nottingham, Shelbourne Park) existen tal cual en
  el parquet, solo en minúsculas — el usuario confirmó que basta normalizar
  mayúsculas, sin mapeo de alias.
- **Hallazgo nuevo, verificado con 5 picks reales, no hipótesis**: `rTime`
  del parquet va **1 hora por detrás** de la hora que escribe el tipster en
  jul-ago 2026 (ej. `rTime=20:31` vs tipster `21:31`; comprobado también con
  Drumbane Blue, Fairhill Autumn, Best Miney y Swift Krab — desfase de +1h
  exacto en los 4/5 casos, coincidiendo trampa y nombre). Consistente con
  que `rTime` esté en UTC y el tipster escriba en hora de Reino Unido en
  verano (BST, UTC+1) — confirmado además que `src/scraper/scrape_results.py`
  copia `rTime` tal cual de la API sin ninguna conversión de zona horaria.
  Sin corregir esto, el cruce por hora exacta fallaría siempre en horario de
  verano británico.
- **Hallazgo crítico, no contemplado en el diseño original de `PLAN.md`
  sección 5**: el parquet solo registra 1º/2º/3º puesto de cada carrera (+
  no corredores `N`) — `position` nunca vale 4/5/6 (confirmado contando
  filas por `race_id`: media 3,1 filas/carrera). Caso real:
  `More Firepower` (Harlow 22/07/2026, trampa 2) no aparece en ningún puesto
  pese a que la carrera está resuelta — quedó fuera del podio. El diseño
  original de `posicion_auto` (fila exacta por trampa) nunca resolvería
  estos casos.
- El usuario, preguntado por cómo resolver ambos huecos, indicó el enfoque:
  "identificar la carrera en los datos de la extracción y luego ver si ha
  ganado o no" — es decir, buscar el ganador de la carrera aunque mi trampa
  no tenga fila propia, en vez de depender de una coincidencia exacta o de
  cruzar por nombre del galgo (rechazado como clave principal por el
  usuario: "pueden estar escritos de forma diferente").
- Ver la entrada siguiente (2026-08-26) para el diseño final y la
  implementación con SSH ya autorizado a la VM.
- Commits: (pendiente)

## 2026-08-26 (cont.) — Causa real de los `error` en cadena: la cuota gratis de Gemini es de solo 20 peticiones/DÍA; añadido reintento automático
- El usuario mandó 4 picks más (`127-130`) y también dieron `error`.
  Preguntó si era el API de Gemini - se confirmó **con el mensaje de
  error real de la API**, no por suposición: probados los 4 textos
  directamente contra Gemini (mismo prompt que `AI.gs`) y los 4 siguen
  fallando con 429 incluso con hasta 5 reintentos (backoff hasta 40s,
  ~75s totales de espera) - descartando que fuera un pico de tráfico
  puntual. Leído el cuerpo completo de la respuesta 429 (no solo el
  código, el mensaje JSON entero):
  ```
  "Quota exceeded for metric: generate_content_free_tier_requests,
   limit: 20, model: gemini-3.6-flash"
  quotaId: "GenerateRequestsPerDayPerProjectPerModel-FreeTier"
  ```
  **Es un límite DIARIO de 20 peticiones**, no un rate-limit por minuto -
  coherente con por qué ni el reintento con backoff de `AI.gs` (hasta 21s)
  ni esperar más de un minuto sirven de nada: hace falta esperar al reset
  diario (estimado ~07:00 UTC / mediodía hora del Pacífico, la convención
  habitual de Google para cuotas gratuitas - no confirmado en la
  documentación de este límite en concreto, es una estimación).
  Entre las pruebas de hoy (extracción del histórico, verificaciones,
  picks reales) se agotó sin darse cuenta.
- Preguntado al usuario cómo seguir (esperar al reset / activar
  facturación / probar otro modelo con más cuota gratis) - eligió una
  cuarta opción no ofrecida: que se registren los que fallen y se
  relancen solos cuando pase el día, en vez de tener que reenviarlos a
  mano o esperar a que yo lo haga.
- **`reintentarMensajesConError()`** (nueva, en `src/Main.gs`): recorre
  `mensajes_crudos` buscando `estado=error`, y para cada uno vuelve a
  llamar a `extraerPick()` (baja la foto de Telegram otra vez si hacía
  falta) - si sale bien, escribe en `apuestas`/`apuestas_patas` igual que
  `manejarPickNuevo_` y manda la confirmación por Telegram (usando una
  constante nueva `TELEGRAM_CHAT_ID` en `Config.gs` - el único grupo del
  bot, no hay `msg.chat.id` disponible fuera del flujo normal de
  `doPost`); si sigue fallando por 429, **corta el bucle ahí mismo** en
  vez de intentar los demás (si la cuota sigue agotada, todos fallarían
  igual, no tiene sentido gastar tiempo de ejecución probándolos uno a
  uno). Protegida con el mismo `LockService` que `doPost`, para no pisarse
  con un pick real llegando a la vez.
- **`configurarTriggerReintentos()`** (nueva): instala un disparador de
  tiempo de Apps Script que llama a `reintentarMensajesConError()` cada 2
  horas (no más seguido - con solo 20 peticiones/día de margen, reintentar
  cada pocos minutos no adelanta el reset, solo genera ejecuciones
  fallidas de más). Hay que ejecutarla **una vez a mano** desde el editor
  (`clasp run` no funciona en este proyecto - "NOT_FOUND", necesitaría un
  tipo de despliegue distinto no configurado) - documentado en
  `docs/DESPLIEGUE.md` sección 8, mismo patrón que `setupSheet`/
  `checkConfig`.
- `clasp push` + versión 10 + redeploy. Pendiente que el usuario ejecute
  `configurarTriggerReintentos` desde el editor para activarlo.
- Commits: (pendiente)

## 2026-08-26 (cont.) — `configurarTriggerReintentos` ejecutado; verificado con `gspread` que sigue habiendo mensajes en `error` (cuota aún agotada, comportamiento esperado)
- El usuario dio permisos y ejecutó `configurarTriggerReintentos` desde el
  editor de Apps Script (necesario porque `clasp run` no funciona en este
  proyecto, ver entrada anterior). No hay forma de leer los "Activadores"
  del proyecto desde esta sesión (la API de Apps Script para triggers no
  está disponible aquí), así que no se pudo verificar la instalación del
  disparador de forma directa - se toma la palabra del usuario en ese
  punto concreto.
- Lo que sí se pudo verificar con datos reales (vía `gspread`, cuenta de
  servicio): `mensajes_crudos` tiene ahora mismo **6 filas en
  `estado=error`**: las 4 ya conocidas (`127-130`) más 2 nuevas
  (`135, 136`) llegadas hoy mismo. Es el comportamiento esperado si la
  cuota diaria de Gemini sigue agotada (reset estimado, no confirmado,
  sobre las 07:00 UTC) - no un fallo nuevo del disparador ni de
  `doPost`. En cuanto la cuota se libere, `reintentarMensajesConError()`
  (cada 2h) debería resolver los 6 solo, sin intervención.
- Pendiente de verificar en una próxima sesión: que el recuento de
  `estado=error` baje a 0 tras el reset, confirmando que el disparador
  realmente se instaló y corre.
- Commits: (pendiente)

## 2026-08-26 (cont.) — Incidente al reenviar los 2 picks: fila de `mensajes_crudos` perdida + apuesta duplicada; arreglados los datos y un bug real de `doPost` (no confirmado como causa única)
- El usuario reenvió los 2 picks de la entrada anterior (Newcastle,
  Hove) tras el fix de reintentos. Resultado real:
  - Newcastle (nuevo `message_id 123`) **sí se procesó bien** (con
    confirmación real por Telegram, `confirm_message_id 125`) - pero
    duplicaba la apuesta que ya había restaurado a mano bajo
    `message_id 119`, ahora repetida en `apuestas`/`apuestas_patas`.
  - Hove (nuevo `message_id 124`) **volvió a fallar** (`estado=error` en
    `mensajes_crudos` de nuevo) - por eso "no aparece el comentario"
    (la confirmación) para ese: no llegó a enviarse, igual que la vez
    anterior. No hacía falta reenviarlo - `message_id 120` (restaurado a
    mano antes) ya cubre esa apuesta correctamente.
  - **Hallazgo más serio**: la fila de `mensajes_crudos` del `message_id
    119` original **desapareció por completo** (no solo se duplicó el
    dato en `apuestas` - la fila cruda entera dejó de existir). Diagnóstico:
    antes del reenvío, `mensajes_crudos` tenía 93=119, 94=120 (confirmado
    por consulta directa). Después del reenvío: 93=120 (contenido de Hove,
    el mismo mensaje que antes estaba en la fila 94), 94=123, 95=124 - es
    decir, todo se comporta como si la fila 93 (119) se hubiera BORRADO de
    verdad (no sobrescrita), desplazando todo lo de abajo una posición
    hacia arriba antes de que `appendMensajeCrudo` añadiera las 2 filas
    nuevas al final. Ningún sitio del código (`Main.gs`/`Sheets.gs`) borra
    filas - búsqueda explícita (`grep deleteRow`) sin resultados.
  - **No se pudo confirmar la causa raíz con certeza**: `clasp logs` no
    funciona en este proyecto ("GCP project ID is not set", sin un
    proyecto GCP estándar vinculado) - sin acceso a los logs de ejecución
    reales de Apps Script, no se puede ver qué pasó internamente en esas
    2 ejecuciones concretas de `doPost`. La explicación más plausible por
    los datos observados es una condición de carrera entre las 2
    ejecuciones casi simultáneas del webhook (los reintentos de Gemini
    alargan cuánto tarda cada una, aumentando la ventana de solape), pero
    es la hipótesis más probable, no un hecho verificado.
  - **Bug real encontrado de paso, aunque no confirmado como la causa de
    este incidente concreto**: en `Main.gs`, `lock.waitLock(30000)`
    estaba FUERA del bloque `try` - si se agota el tiempo de espera,
    lanza una excepción sin capturar (ni se hace log limpio, ni se llega
    al `finally` que libera el lock). Fix: el `waitLock` pasa a su propio
    `try/catch`, y el margen sube de 30s a 120s (los reintentos de Gemini
    ante 429 pueden añadir hasta ~21s a una ejecución, dejando menos
    margen del que había antes para que una segunda petición espere su
    turno sin problemas). `clasp push` + versión 9 + redeploy.
  - **Datos corregidos a mano**: quitada la fila duplicada de Newcastle
    (`119` en `apuestas`/`apuestas_patas` - la cubre `123`, que sí tiene
    confirmación real de Telegram). Restaurada la fila perdida de
    `mensajes_crudos` para `119` (con su texto original, `estado=error`,
    reflejando lo que pasó de verdad con ESA entrega concreta - la
    apuesta en sí ya está bien registrada bajo `123`). `120` (Hove) se
    dejó tal cual, sin duplicar (`124` falló, no llegó a escribir nada).
  - Aviso al usuario: no hace falta reenviar Hove otra vez, ya está
    registrado correctamente bajo `message_id 120`.
- Commits: (pendiente)

## 2026-08-26 (cont.) — Bug real en producción: 2 picks del tipster perdidos por rate-limit de Gemini sin reintento; restaurados y arreglada la causa
- El usuario mandó 2 picks reales por Telegram (`message_id 119` Newcastle,
  `120` Hove) y detectó que aparecían en `mensajes_crudos` pero no en
  `apuestas` - señal exacta de que `extraerPick()` había fallado
  (`Main.gs` guarda el crudo SIEMPRE antes de intentar nada más).
  Confirmado en la hoja real: ambos con `estado=error` en
  `mensajes_crudos` (no `revision_manual` - eso habría significado que la
  IA respondió pero el pick no encajaba; `error` significa que la propia
  llamada a Gemini falló, capturado por el `try/catch` de
  `manejarPickNuevo_`).
- `clasp logs` no sirve en este proyecto (pide un proyecto GCP vinculado
  que no está configurado - "GCP project ID is not set"). En vez de perder
  tiempo configurándolo, se reprodujo el fallo directamente: se llamó a
  Gemini con el texto EXACTO de los 2 mensajes usando
  `scripts/backfill_extraer_ia.py` (el mismo prompt que `AI.gs`, ya escrito
  esta mañana aunque no se usó para su propósito original). Los dos
  extrajeron perfectamente bien (`simple`, datos completos) - **no era un
  problema de esos textos ni del prompt**, era un 429 puntual (uno de los
  2 necesitó un reintento para pasar). Muy probablemente resaca del script
  de extracción por IA que se lanzó y se paró a medias hace unas horas
  (hizo bastantes peticiones seguidas antes de pararlo).
- **Causa raíz real**: `callGeminiExtraction_` en `src/AI.gs` no tenía
  NINGÚN reintento - un solo 429 tira el pick entero a `error` sin
  necesidad, perdiendo un pick real del tipster. Fix: hasta 3 intentos con
  espera creciente (3s/6s/12s) ante 429 o 503, antes de dar el fallo por
  definitivo (dentro del límite de 6 min de ejecución de Apps Script sin
  problema). `clasp push` + versión 8 + redeploy sobre el mismo deployment
  del webhook.
- **Los 2 picks perdidos, restaurados a mano** con los datos ya
  verificados por la extracción de prueba: 1 fila cada uno en `apuestas`
  (`tipo_apuesta=simple`) + 1 fila cada uno en `apuestas_patas`, y
  `mensajes_crudos` corregido de `error` a `procesado`. Verificado:
  `resultado_final=pendiente` para ambos (correcto, las carreras son de
  hoy, el timer recurrente las resolverá cuando corran).
- Commits: (pendiente)

## 2026-08-26 (cont.) — `vm_job_resultados_galgos.py`: no cargar el parquet si no hay patas pendientes
- Pedido del usuario: que el job no ejecute el trabajo pesado (cargar
  `results_enriched.parquet`, ~2MB+ en memoria) si no hay ninguna pata
  pendiente de verdad.
- Separado en dos fases: `calcular_pendientes()` (barata, solo con lo ya
  leído de `apuestas_patas`/`resultados_galgos` vía Sheets - decide qué
  patas no están cubiertas Y ya deberían haber corrido) y
  `resolver_contra_parquet()` (cara, solo se llama si la primera fase
  encontró al menos una pendiente). Si `pendientes` sale vacía, el job
  termina ahí mismo sin tocar el parquet.
- Redesplegado (`scp` a `/opt/picks-premier-galgos/`) y reprobados los dos
  caminos antes de dejarlo así:
  - Sin pendientes (estado real actual, las 91 patas ya cubiertas) → `0
    pendientes`, "no hace falta cargar el parquet, fin." - confirmado que
    no lo carga.
  - Con una pendiente de prueba (misma carrera sintética que la vez
    anterior) → sigue encontrando y resolviendo correctamente (3 filas
    insertadas, limpiadas después). El refactor no cambió el
    comportamiento, solo cuándo se paga el coste del parquet.
- El timer (`picks-resultados.timer`) no necesitó cambios, sigue activo
  con el mismo horario.
- Commits: (pendiente)

## 2026-08-26 (cont.) — Fase 7 completa: script recurrente en la VM (`picks-resultados.timer`), desplegado y probado en producción
- Pregunta directa del usuario tras la entrada anterior: si manda un pick
  hoy por el bot, ¿se resolvería solo? Respuesta honesta: no - hasta este
  punto, todo lo de `resultados_galgos` se había rellenado a mano (yo,
  bajo petición). Confirmado por el usuario: construirlo ahora.
- **`scripts/vm_job_resultados_galgos.py`** (nuevo, versionado en este
  repo): mismo enfoque validado en la entrada anterior (parquet local de
  la VM, `results_enriched.parquet`, sin llamadas en vivo a Racing Post -
  la "trampa ganadora" ya resuelve gano/perdio sin necesitar
  `dog_id`/`track_id`). Diferencias frente al script de backfill de hoy:
  - **Idempotente**: antes de tocar una carrera, comprueba si
    `resultados_galgos` ya tiene alguna fila para ese
    canódromo+fecha+hora - si la tiene, la salta. Probado en caliente
    ejecutándolo dos veces seguidas: la segunda vez no inserta nada
    (`0 revisadas`).
  - **Solo mira carreras que ya deberían haber corrido** (margen de 30
    min) - no pierde tiempo comprobando picks de carreras futuras.
  - Lee `apuestas_patas` entera cada vez (no hay marca de "pendiente" que
    consultar aparte - más simple y suficientemente barato, es una
    lectura local del parquet + una lectura/escritura de Sheets, nada
    pesado).
- **Desplegado en la VM siguiendo la convención ya existente de Proyecto
  Galgos** para procesos ajenos al propio repo de ese proyecto (mismo
  patrón que `backup_to_drive.sh`, que vive en `/opt/galgos/scripts/`, no
  dentro de `/opt/galgos/repo/`):
  - Script en `/opt/picks-premier-galgos/vm_job_resultados_galgos.py`
    (carpeta nueva, deliberadamente fuera de `/opt/galgos/repo` para no
    mezclar código de este proyecto con el de Proyecto Galgos).
  - Clave de la cuenta de servicio en
    `/root/.config/picks-premier-galgos/service_account.json`, permisos
    `600`, mismo criterio que `/root/.config/rclone/rclone.conf` (el
    único otro secreto que ya vive fuera del repo en esa VM). Nunca en
    `/opt/galgos/repo` ni en ningún repo de git.
  - Reutiliza el venv de Proyecto Galgos (`/opt/galgos/repo/venv`) - ya
    tenía `gspread`/`google-auth` instalados, no hizo falta instalar nada
    nuevo.
  - `scripts/deploy/picks-resultados.{service,timer}` (versionados en
    este repo): timer a las `:15,:35,:55` de cada hora entre 10:35 y
    23:55 hora de Madrid - **5 minutos después** de cada pasada de
    `galgos-poll-results` (que corre a `:10,:30,:50`), para darle tiempo
    a refrescar el parquet antes de leerlo. Mismo estilo de unidades que
    ya usa Proyecto Galgos (`Type=oneshot`, log a `/var/log/`).
- **Probado de extremo a extremo antes de activar el timer** (no se
  activó a ciegas):
  1. Ejecución manual sobre el estado real (91 patas ya cargadas hoy) →
     "91 ya cubiertas, 0 nuevas" - confirma que no reprocesa ni duplica
     lo que ya insertó el backfill de la entrada anterior.
  2. Insertada una pata de prueba sintética (`message_id 999999`,
     Central Park 10/08/2026, trampa 6 "Naughty Bonnie" - una carrera
     real del parquet, ganadora, que aún no estaba en
     `resultados_galgos`) → ejecutado el job → detectó la carrera nueva,
     insertó sus 3 filas de podio, y la fórmula de `apuestas_patas`
     resolvió `resultado_pata=gano` sola, sin tocar nada más.
  3. Ejecutado otra vez inmediatamente → `0 revisadas, nada que insertar`
     - confirma idempotencia real, no solo de diseño.
  4. Datos de prueba borrados de `apuestas_patas` y `resultados_galgos`
     tras verificar.
  - `systemctl enable --now picks-resultados.timer` → activo, próxima
    ejecución programada para las 10:35 hora de Madrid (fuera de la
    ventana de carreras a esta hora de la noche, como corresponde).
- **Con esto, la respuesta a "si mando un pick hoy, ¿se resuelve solo?"
  pasa a ser SÍ**: se registra por el bot (ya probado antes) y, en cuanto
  la carrera corra y `galgos-poll-results` actualice el parquet, el
  siguiente ciclo de `picks-resultados.timer` (máximo ~20-25 min después)
  le pone el resultado sin que nadie tenga que tocar nada.
- **Pendiente, explícitamente fuera de este job**: `cuota_final`/
  `url_carrera`/posición exacta para patas fuera de podio (necesitan
  `dog_id`/`track_id` en vivo) - se resuelven aparte, a mano o en una
  mejora futura con throttling adecuado para no repetir el problema de
  rate-limit/VPN de hoy.
- Commits: (pendiente)

## 2026-08-26 (cont.) — Resueltas automáticamente las 87 apuestas cargadas: 33 ganadas, 54 perdidas, sin ninguna en "pendiente"
- Malentendido aclarado por el usuario: el "proceso automatizado" que
  pedía no era volver a extraer los picks con IA (esos datos ya están
  bien parseados en los CSVs, no hace falta Gemini para eso) - era que,
  al cargar los picks que YA teníamos, el sistema debería haber buscado
  sus resultados automáticamente en vez de dejarlos todos en "pendiente".
  Se paró el intento de extracción por IA a medio hacer (rate-limit del
  tier gratis de Gemini tras las primeras peticiones - `scripts/
  backfill_extraer_ia.py` queda escrito por si hace falta en el futuro
  para verificar extracciones, pero no se ha usado para esto) y se
  construyó lo que realmente hacía falta: el script de resolución de
  resultados para las 87 patas cargadas.
- **Primer intento: en la VM, con el camino completo (parquet + fallback
  por `dog_id` en vivo)** - el mismo verificado a mano por la mañana con
  4 casos. Se atascó: Racing Post empezó a devolver rate-limit (probable,
  por el volumen acumulado de peticiones de todo el día) y el mecanismo
  de rotación automática de VPN del propio proyecto (`src/utils/vpn.py`,
  NordVPN) **no funciona ahora mismo en la VM** - falla la conexión
  (`rc=1`) en los 32 países de su lista, uno tras otro, y `change_vpn()`
  se llama a sí misma en bucle sin ningún límite si todos fallan -
  bucle infinito real, no hipotético, confirmado viéndolo encadenar los
  32 países repetidamente. Parado el proceso (`pkill` en la VM, el
  `TaskStop` local no basta - la sesión SSH sigue viva en la VM aunque se
  corte el cliente). No se perdió nada porque el script solo escribía su
  salida al final, no incrementalmente (lección para la próxima vez:
  guardar progreso según se avanza, no solo al terminar).
- **Segundo intento, resuelto sin tocar la VM ni la red**: la observación
  clave es que la "trampa ganadora" (el fallback ya implementado en las
  fórmulas desde por la mañana) **no necesita ninguna llamada en vivo** -
  solo necesita que las filas de podio de esa carrera estén en
  `resultados_galgos`, y esas ya estaban descargadas en
  `results_enriched.parquet` (copiado esta mañana a la sesión). Rehecho
  el script para correr 100% en local contra ese parquet ya descargado,
  sin `dog_id`/`track_id` en vivo (eso solo aporta posición exacta y URL
  para los casos fuera de podio - mejora, no imprescindible; queda
  pendiente para cuando el rate-limit se enfríe o se arregle la VPN).
  Resultado: **las 87 carreras SÍ estaban en el parquet** (0 sin ningún
  dato), 268 filas de resultado insertadas en `resultados_galgos`
  (dedupliadas por canódromo+fecha+hora+trampa) - 26 patas resueltas por
  el fallback de trampa ganadora (su propia trampa no estaba en el
  podio), 61 por coincidencia exacta.
- **Verificado sobre las 87 apuestas reales**: `resultado_final` en
  `apuestas` → 33 `gano` + 54 `perdio` = 87, ninguna en "pendiente" ni
  `#ERROR!`. `resultado_pata` en `apuestas_patas` → 36 `gano` + 55
  `perdio` = 91 patas. Unidades netas totales de las 87 apuestas:
  **+75,27** (positivo, consistente con el rendimiento que dice tener el
  tipster). Revisadas varias filas sueltas a mano: `retorno_real` cuadra
  con `cuota×stake` en las ganadas, `0` en las perdidas,
  `unidades_netas = retorno_real - stake` en todas.
- Limpiados los ficheros temporales dejados en la VM
  (`tmp_resolver_resultados.py`, `legs_input.json` y los JSON de salida
  del intento fallido) - no debían quedarse en el repo de producción de
  Proyecto Galgos.
- **Pendiente para cuando se arregle la VPN o pase el rate-limit**:
  completar `url_carrera`/posición exacta/`cuota_final`/`dog_id` de las
  26 patas resueltas por fallback (hoy se quedan con esos campos vacíos,
  correctamente en "perdio" pero sin el detalle fino) y construir el
  script recurrente de producción en la VM (seguía pendiente desde por la
  mañana, ahora con la lección añadida de que el rate-limit/VPN es un
  riesgo real a mitigar - ej. cachear más agresivamente, espaciar más las
  peticiones, o que el recurrente solo use el parquet local igual que
  este backfill, reservando las llamadas en vivo solo para lo que de
  verdad las necesita).
- Commits: (pendiente)

## 2026-08-26 (cont.) — Cargado el histórico completo (89 picks del backfill del 2026-08-20) en las 3 pestañas, en orden, sin repetir lo ya cargado
- Pedido del usuario: cargar TODOS los picks que ya había (el backfill de
  89 mensajes reales del 2026-08-20), sin repetir `message_id 3/5/14`
  (cargados antes hoy como pruebas), en orden.
- **80 simples** de `data/apuestas.csv` (los 82 ya parseados por el script
  de backfill del 2026-08-20, menos `3` y `5`) cargados directamente -
  `fecha_pick` convertida de UTC a hora de Madrid (mismo criterio que el
  resto de filas de hoy) para que se reconozca como fecha real en la hoja
  (es_ES, formato `DD/MM/YYYY HH:MM:SS`).
- **Revisados a mano los 7 `revision_manual` del backfill** (`14, 32, 33,
  52, 74, 75, 76`) para ver cuáles resuelve el diseño de hoy:
  - `75`: errata "Ciota" en vez de "Cuota" (el regex original no la
    reconocía) - simple, datos completos (Sheffield 17:59 T1 Jacktavern
    Turbo, cuota 2.75, stake 4). Resuelto.
  - `33`, `52`, `76`: dobles con las 2 patas completas (canódromo, hora,
    trampa, galgo) - resueltos como `doble` con 2 filas en
    `apuestas_patas` cada una. `52` traía una nota del tipster pegada al
    nombre ("Betgoodwin Eddy sin el favorito.") - recortada al nombre del
    galgo, la nota no es parte de la selección.
  - `32`, `74`: **siguen en `revision_manual`, de verdad, no por
    limitación de hoy** - a `32` le falta la trampa de la 2ª pata
    ("21:54 Monmore \nVhagar", sin "T#"); a `74` las dos patas traen un
    número raro sin formato de trampa reconocible ("Vhagar 1.44",
    "Slingshot Poppy 1.57" - no está claro si "1.44"/"1.57" es trampa,
    hora, o algo del tipster que no se ha decodificado). Ninguno de los
    dos se ha inventado un dato - coherente con "nunca inferir sobre
    ambigüedad" (CLAUDE.md).
  - `14` ya estaba cargado en `apuestas`/`apuestas_patas` desde antes de
    hoy, pero `mensajes_crudos` seguía marcándolo `revision_manual`
    (arrastrado sin querer del CSV original al backfillearlo hace unas
    horas) - corregido a `procesado`, ya que sí está resuelto.
- **Total cargado**: 87 `message_id` procesados (83 simples + 4 dobles) +
  2 en `revision_manual` real = 89, igual que el histórico completo.
  `apuestas_patas` con 91 filas (87 simples de 1 pata + 4 dobles de 2 =
  91). Todo en orden de `message_id`, en 3 escrituras por lotes (una por
  pestaña) en vez de fila a fila.
- Verificado con `gspread`: sin `#ERROR!` en `resultado_final` (solo
  `pendiente`/`gano`/`perdio` - la mayoría `pendiente`, como corresponde,
  `resultados_galgos` solo tiene los datos de las pruebas de hoy, no el
  histórico jul-ago completo todavía); formato numérico limpio (sin
  repetir el bug de formato heredado de la entrada anterior, ya arreglado
  antes de esta carga); conteos de `apuestas`/`apuestas_patas`/
  `mensajes_crudos` cuadran entre sí.
- Commits: (pendiente)

## 2026-08-26 (cont.) — Desplegado a producción (versión 7) y probado end-to-end contra el webhook real; bug real de formato heredado encontrado y arreglado
- `clasp push` (8 archivos) + `clasp version` (v7) + `clasp redeploy` sobre
  el MISMO deployment ID que ya usa el webhook de Telegram
  (`AKfycbynXi...`, antes en v6) - la URL no cambia, solo el código detrás.
  Verificado con `getWebhookInfo` tras el redeploy: `pending_update_count:
  0`, sin `last_error_message`, URL sigue terminando en `/exec?token=...`.
- **Prueba end-to-end real contra el webhook desplegado**, no solo
  revisión de código: construido un update de Telegram sintético (una
  "Apuesta Doble" de texto, con canódromos/galgos ficticios para no
  mezclarlo con datos reales) y mandado por HTTP POST directamente a la
  URL del webhook (la misma que usa Telegram), con un `chat_id` falso a
  propósito para que el aviso de confirmación no llegara al grupo real
  (`sendTelegramMessage` falla en silencio si el chat no existe - revisado
  en `Telegram.gs` antes de hacerlo, para no arriesgar spam en el grupo).
  Resultado: `doPost` devolvió `ok`, y las 3 pestañas se rellenaron solas
  y correctamente - `mensajes_crudos` (estado `procesado`),
  `apuestas_patas` (2 filas, una por pata), `apuestas` (1 fila,
  `tipo_apuesta=doble`, `num_patas=2`, `resultado_final=pendiente` como
  corresponde con canódromos que no existen en `resultados_galgos`).
  Primera confirmación real de que el rediseño de hoy funciona con el
  camino real del bot, no solo con datos insertados a mano por `gspread`.
- **Bug real encontrado con esta prueba, no hipotético**: la celda
  `cuota` de la fila nueva se veía como "0:00" en vez de "3" - el valor
  interno era correcto (`retorno_potencial=15=3×5` cuadraba), pero el
  FORMATO de la celda seguía siendo `TIME` (heredado de cuando esa misma
  posición de columna, en un diseño de `apuestas` de hace unas horas, era
  `hora_carrera`). `Range.setValues()` de Apps Script no toca el formato
  de una celda, solo su valor - así que el formato viejo sobrevivió a los
  `ws.clear()` de hoy (`clear()` de gspread solo borra VALORES, no
  formato) y quedó esperando en filas nunca reescritas hasta que el bot
  real escribió ahí. Comprobado que no era un caso aislado: `patas_ganadas`/
  `patas_perdidas` (antes `creado_en`, con formato `DATE`) mostraban `0`
  como "30/12/1899" (el "día cero" de Sheets) por el mismo motivo.
- Fix: limpiado el formato numérico de TODO el rango de datos de
  `apuestas` (`A2:Z2000`, vía `repeatCell`/`fields:
  userEnteredFormat.numberFormat` con formato vacío - `"AUTOMATIC"` no es
  un valor válido de la API, hay que dejar el campo sin especificar) y
  reaplicado `DATE_TIME` solo donde hace falta (`fecha_pick`,
  `creado_en`). Reverificadas las 3 filas reales + la de prueba: todo
  limpio, sin más artefactos de formato heredado. `apuestas_patas`,
  `mensajes_crudos` y `resultados_galgos` revisadas también - sin el
  mismo problema (solo `apuestas` pasó por tantos rediseños de columnas
  hoy como para arrastrar esto).
- Datos sintéticos de la prueba (`message_id 900001`) borrados de las 3
  pestañas tras verificar - no eran datos reales, no debían quedarse en
  la hoja de producción.
- Commits: (pendiente)

## 2026-08-26 (cont.) — Bot real actualizado: dobles/tríples se procesan solas en vivo (`AI.gs`, `Main.gs`, `Sheets.gs`, `Commands.gs`)
- Hasta ahora todo el trabajo de hoy era sobre las fórmulas de resolución
  (aplicadas a mano vía `gspread`); el bot real (`Main.gs`/`AI.gs`) seguía
  con el diseño viejo - una doble le llegaba y la mandaba entera a
  `revision_manual`, y además `Sheets.gs` seguía escribiendo en columnas
  de `apuestas` que ya no existen tras el rediseño de hoy
  (`hipodromo`/`hora_carrera`/`trampa`/`seleccion` viven ahora en
  `apuestas_patas`). El usuario pidió explícitamente completar esto ahora,
  no dejarlo solo anotado.
- **`src/AI.gs` reescrito**: el prompt de Gemini ya no usa
  `es_apuesta_multiple` (boolean + resto de campos a null); ahora siempre
  devuelve `tipo_apuesta` ("simple"/"doble"/"triple"/"otro") + un array
  `patas` (1 elemento para simple, 2 para doble, 3 para tríple) + `cuota`/
  `stake` de la apuesta conjunta (fuera del array, nunca por pata).
  "otro" cubre Trixie/Yankee/apuestas "a puesto"/cualquier cosa no
  identificada con certeza - en ese caso se le pide a la IA que rellene
  igualmente las patas que pueda reconocer, para ayudar a la revisión
  manual en vez de dejarla a ciegas.
  `extraerPick()` valida: `tipo_apuesta` tiene que estar en
  `TIPOS_APUESTA_SOPORTADOS` (Config.gs) o se rechaza con motivo
  `tipo_no_soportado`; el nº de patas tiene que cuadrar con el tipo
  (`num_patas_incorrecto` si no); cada pata necesita
  `CAMPOS_OBLIGATORIOS_PATA` (hipodromo/hora_carrera/trampa/seleccion) y
  la apuesta necesita `cuota`/`stake` (`faltan_campos` listando qué falta,
  con prefijo `pataN.` para saber de cuál).
- **`src/Config.gs`**: `CAMPOS_OBLIGATORIOS_PICK` (mezclaba campos de pata
  y de apuesta) sustituido por `CAMPOS_OBLIGATORIOS_PATA` (solo hipodromo/
  hora_carrera/trampa/seleccion) + `TIPOS_APUESTA_SOPORTADOS` (['simple',
  'doble', 'triple'], usada tanto por `AI.gs` como por la fórmula de
  `resultado_final` en `Setup.gs` - un solo sitio donde ampliar la lista
  el día que se construya la fórmula de pago de Trixie/Yankee).
- **`src/Sheets.gs`**: `appendApuesta(campos)` (escribía 1 fila con todo
  mezclado) sustituida por `appendApuestaConPatas(messageId, fechaPick,
  tipoApuesta, cuota, stake, patas)` - escribe 1 fila en `apuestas` +
  1 fila por pata en `apuestas_patas` (mismo `appendRowByHeader_` de
  siempre, reutilizado sin cambios). `clonarFormulasDeApuestas_`
  generalizada para funcionar con las dos pestañas (antes solo
  contemplaba `apuestas`) - si algún día se supera
  `FILAS_FORMULA_APUESTAS_PATAS` (5000), las fórmulas se clonan solas
  igual que ya pasaba en `apuestas`. Nuevas `findApuestaPatasByMessageId`/
  `setApuestaPataField` para poder editar campos de pata desde comandos.
- **`src/Commands.gs`**: `corregir campo=valor` distingue ahora entre
  campos de la apuesta (`cuota`/`stake`, en `apuestas`) y de pata
  (`hipodromo`/`hora_carrera`/`trampa`/`seleccion`, en `apuestas_patas`).
  Para estos últimos, si la apuesta tiene más de 1 pata (doble/tríple) se
  avisa de que no se puede corregir sin decir cuál - **no implementado**
  a propósito (no pedido hoy, y "corregir pata2.hipodromo=X" es un
  parseo nuevo que no existía) - solo funciona sin ambigüedad para
  apuestas simples, igual que antes del rediseño.
- **`src/Main.gs`**: `manejarPickNuevo_` adaptado al nuevo contrato de
  `extraerPick`; nuevas `motivoRevisionManual_` (mensaje según el motivo
  de rechazo) y `construirTextoConfirmacion_` (la confirmación por
  Telegram lista todas las patas separadas por " + ": p. ej. "Apuesta
  registrada (doble): 20:46 Hove - T2 Droopys Flare + 20:50 Central Park
  - T5 Zari Aki @2.59 (stake 6u)").
- **Bug real encontrado y corregido de paso** (mismo patrón que otros de
  hoy - probado con las filas de control ANTES de darlo por bueno):
  al cambiar `resultado_final` para mandar a `revision_manual` cualquier
  `tipo_apuesta` no soportado (en vez de solo comprobar literalmente
  "trixie"/"yankee"), una fila totalmente vacía (sin ninguna apuesta,
  `tipo_apuesta=""`) también caía en `revision_manual` - `""` tampoco es
  uno de los tipos soportados, así que `NOT(OR(...))` daba `TRUE`. Fix:
  comprobar primero `message_id=""` → "pendiente" directamente, antes de
  mirar `tipo_apuesta`. Reaplicado a las 2000 filas y reverificado: solo
  "pendiente" en las filas sin apuesta.
- No probado en producción todavía (necesita `clasp push` + redeploy +
  un pick real de prueba por Telegram) - las fórmulas de la hoja sí están
  verificadas con datos reales de hoy, pero el código del bot en sí solo
  se ha revisado, no ejecutado.
- Commits: (pendiente)

## 2026-08-26 (cont.) — Añadida columna `mensaje` a `apuestas`; corregido olvido de `mensajes_crudos` para los picks de hoy
- El usuario pidió el texto crudo del mensaje en la hoja final, y de paso
  detectó un olvido real: al backfillear hoy `message_id 5` y `14` en
  `apuestas`/`apuestas_patas`, no se rellenó `mensajes_crudos` para esos
  dos - solo tenía la fila de `message_id 3` de la sesión anterior. Fix:
  añadidas las 2 filas que faltaban en `mensajes_crudos` (texto real
  sacado de `data/mensajes_crudos.csv`, backfill del 2026-08-20) - `5` con
  `estado=procesado` (simple), `14` con `estado=revision_manual` (así lo
  dejó el bot real en su momento, con la lógica actual que no sabe tratar
  dobles; se ha resuelto hoy "a mano" en `apuestas_patas`/`apuestas` como
  parte de esta prueba, pero el `estado` en `mensajes_crudos` refleja lo
  que hizo el bot de verdad, no se ha falseado).
- `mensaje` en `apuestas`: `INDEX/MATCH` simple contra
  `mensajes_crudos.contenido` por `message_id` (relación 1:1 - un
  `message_id` es un único mensaje de Telegram, da igual si describe 1, 2
  o 3 carreras - a diferencia de `canodromo`/`galgo`/etc., que sí necesitan
  `TEXTJOIN`/`FILTER` porque son varias filas en `apuestas_patas`).
- Verificado: las 3 filas reales traen su texto completo; el resto de la
  hoja sigue sin `#ERROR!` ni contenido donde no debería haberlo.
- Commits: (pendiente)

## 2026-08-26 (cont.) — Añadidas `canodromo`/`galgo` agregados a `apuestas`
- Pedido del usuario: faltaba en la pestaña final el/los canódromo(s) y el
  nombre/nombres del galgo/galgos de la apuesta (legible de un vistazo,
  útil también para Looker Studio).
- Mismo patrón que `url_carrera`/`race_id`/`dog_id`:
  `TEXTJOIN(" | ";TRUE;FILTER(apuestas_patas!hipodromo;
  apuestas_patas!message_id=...))` para `canodromo`, e igual con
  `seleccion` para `galgo` - `""` si `num_patas=0`. Añadidas al final de
  `columnasFormula` en `crearApuestas_` (`src/Setup.gs`).
- Verificado: `message_id 3` → "Central Park"/"Droopys Rarity";
  `message_id 14` (doble) → "Hove | Central Park"/"Droopys Flare | Zari
  Aki".
- Commits: (pendiente)

## 2026-08-26 (cont.) — Rediseño v2: `apuestas_patas` (una fila por carrera) + `apuestas` agregada por `message_id` - ya soporta Trixie/Yankee en el dato
- El usuario propuso un modelo mejor que el de la entrada anterior (columnas
  fijas `hipodromo_2/3`): una pestaña intermedia con **una fila por
  CARRERA** de un pick (una doble = 2 filas, una tríple = 3...), agrupadas
  por `message_id`, y una pestaña final con **una fila por APUESTA** que
  agrega esas filas. Ventaja sobre el diseño anterior: no hace falta una
  columna fija por pata (que no escalaba a Trixie -3 selecciones, 4
  apuestas- ni Yankee -4 selecciones, 11 apuestas-), y añadió una columna
  `tipo_apuesta` para que la fórmula final sepa qué lógica de pago aplicar
  según el tipo.
- **Alcance acordado**: migrar hoy simple/doble/tríple a este modelo
  (misma lógica de "ganan todas las patas o pierde toda la apuesta" que ya
  estaba validada). Trixie/Yankee quedan con el dato preparado
  (`tipo_apuesta` los admite, `apuestas_patas` podría tener sus 3-4 filas)
  pero **sin fórmula de pago todavía** - un Trixie no es "todo gana o
  pierde todo", son 4 apuestas independientes con pagos parciales, y no
  hay ningún caso real en el histórico para construirlo y probarlo hoy.
  `resultado_final` los deja explícitamente en `revision_manual` en vez de
  intentar un cálculo que no le corresponde a este diseño.
- Clave de agrupación: `message_id` (ya es único por pick de Telegram, no
  hace falta inventar un id de apuesta nuevo).
- **Nueva pestaña `apuestas_patas`** (`COLUMNAS_APUESTAS_PATAS` en
  `src/Config.gs`): `message_id, numero_pata, fecha_pick, hipodromo,
  hora_carrera, trampa, seleccion, creado_en` + fórmulas
  `posicion_pata/resultado_pata/cuota_final_pata/url_carrera_pata/
  race_id_pata/dog_id_pata` - literalmente la misma lógica de resolución
  de "una pata sola" que ya existía (coincidencia exacta + trampa
  ganadora como fallback), aplicada una vez por fila en vez de 3 veces
  combinadas con `LET()` como en el diseño anterior - mucho más simple de
  leer y con el mismo comportamiento.
- **`apuestas` reconstruida desde cero** (`COLUMNAS_APUESTAS` rediseñada:
  ya no tiene `hipodromo/hora_carrera/trampa/seleccion` ni las columnas
  `_2/_3` - esos datos viven ahora solo en `apuestas_patas`. Añadido
  `tipo_apuesta`). Como solo había 3 filas reales cargadas, se reconstruyó
  entera en vez de parchear otra vez (mucho más seguro con tan poco dato
  real todavía). Fórmulas nuevas, todas agregando `apuestas_patas` por
  `message_id` con `COUNTIF(S)`/`FILTER`, sin ramas distintas por número
  de patas (la misma fórmula sirve para 1, 2 o 3 patas):
  - `num_patas`/`patas_ganadas`/`patas_perdidas`: `COUNTIF(S)` contra
    `apuestas_patas` filtrando por `message_id`.
  - `resultado_final`: manual manda; si `tipo_apuesta` es trixie/yankee →
    `revision_manual`; si `num_patas=0` → `pendiente` (mismo cuidado que
    el bug de la entrada anterior - sin esto, una fila sin patas cargadas
    volvería a dar "gano" por vacuidad lógica); si alguna pata perdió →
    `perdio`; si ganaron todas → `gano`; si no, `pendiente`.
  - `cuota_final`: `PRODUCT(FILTER(...))` de la cuota de cierre de cada
    pata, en blanco si a alguna le falta el dato (no se puede multiplicar
    por un hueco) - contado con `COUNTIFS(...;"")`.
  - `url_carrera`/`race_id`/`dog_id`: `TEXTJOIN(" | ";TRUE;FILTER(...))`
    de todas las patas.
  - `value_pct`: sin cambios de fórmula, usa la `cuota_final` ya agregada.
  - Todo dentro de `LET()` para no evaluar cada `COUNTIFS`/`FILTER` dos
    veces.
- **Verificado con las 3 apuestas reales** reconstruidas en la hoja
  (`message_id 3` y `5` como `simple`, `14` como `doble`, con sus patas ya
  en `apuestas_patas`): resultados idénticos a los de la entrada anterior
  (`perdio`/`perdio`/`gano`, `cuota_final` 3,25/5/2,1997,
  `value_pct` -26,8/70/17,7). Probado primero en un rango pequeño (filas
  2-5, incluida una fila vacía de control → `num_patas=0`,
  `resultado_final=pendiente`, sin repetir el bug de vacuidad) antes de
  aplicarlo a las 2000 filas. Revisada una muestra amplia (filas 5-50,
  500, 2000): sin `#ERROR!`.
- **Pendiente, fuera de esta prueba**: `Main.gs`/`AI.gs` (el bot en
  producción) siguen escribiendo con el esquema viejo de una sola fila
  por pick - hay que actualizarlos para que, ante una doble/tríple,
  escriban 1 fila en `apuestas` (con `tipo_apuesta`) + 2-3 filas en
  `apuestas_patas`. No tocado hoy, es trabajo de integración del bot, no
  de las fórmulas de resolución.
- `src/Config.gs`/`src/Setup.gs` actualizados con el diseño completo.
  Pendiente `clasp push`.
- Commits: (pendiente)

## 2026-08-26 (cont.) — [Reemplazado por el rediseño siguiente] `cuota_final`/`url_carrera`/`value_pct` combinan TODAS las patas; añadidos `race_id`/`dog_id` (para Looker Studio)
- El usuario va a usar esta hoja para un informe en Looker Studio (u
  otra herramienta de BI) y pidió que el dato quede limpio para eso:
  1. `url_carrera` debe traer las URLs de TODAS las carreras de la
     apuesta, no solo la de la pata 1.
  2. Nueva columna `race_id` (o varios, en dobles/tríples) y `dog_id`
     (ídem).
  3. `cuota_final` debe ser la cuota conjunta final = cuota de cierre del
     perro 1 × la del perro 2 (× la del 3 si hay tríple), no solo la de
     la pata 1.
  4. `resultado_final` ya representaba correctamente "ganaron/perdieron
     TODOS los participantes" desde el cambio anterior — sin cambios aquí,
     solo confirmado.
- **`resultados_galgos` ampliada** con `race_id` y `dog_id` (columnas J y
  K) — antes solo tenía `cuota_final`/`url_carrera` (columnas H/I).
  Backfilleadas las 13 filas ya cargadas (las de las 4 carreras de las
  pruebas de hoy) con los `race_id`/`dog_id` reales sacados de
  `results_enriched.parquet`.
- **`apuestas` rediseñada**: `cuota_final`/`url_carrera` (columnas T/U, ya
  existían) reescritas para combinar las patas presentes; `race_id`/
  `dog_id` son columnas nuevas (`AH`/`AI`). Para cada campo se calcula el
  valor de cada pata (`lookupGalgo_` para lo que es propio del galgo -
  cuota, dog_id -, `lookupCarrera_` para lo que es de la carrera entera -
  url, race_id -) y se combinan:
  - `cuota_final` = producto de las cuotas de cierre de las patas
    presentes (si a cualquier pata presente le falta su propia cuota,
    el conjunto se deja en blanco - no se puede multiplicar por un hueco).
  - `url_carrera`/`race_id`/`dog_id` = `TEXTJOIN(" | ";TRUE;...)` de las
    patas presentes (`TRUE` = ignorar vacíos, así una apuesta simple no
    arrastra separadores sueltos).
  - `value_pct` sin cambios de fórmula, pero ahora compara la cuota del
    pick (ya combinada, tal cual se apostó) contra la `cuota_final`
    combinada de verdad, no solo la de la pata 1.
- **Usado `LET()`** para no calcular cada búsqueda dos veces (una para
  comprobar si está vacía, otra para usarla) - las fórmulas ya eran largas
  y esto evita que dobles/tríples las tripliquen sin necesidad.
- **Bug encontrado y corregido antes de aplicarlo a las 2000 filas**:
  `LET()` no acepta nombres de variable con forma de referencia de celda
  - `c1`, `u1`, `r1`, `d1` se interpretan como las celdas C1/U1/R1/D1, no
    como identificadores, y Sheets lo rechaza con "Argument 1 of function
    LET is not a valid name". Verificado en una celda suelta antes de
    aplicarlo a toda la hoja (mismo método que otros bugs de hoy):
    `=LET(a;1;b;2;...)` funciona, `=LET(c1;1;c2;2;...)` no. Fix: nombres
    de 2-3 letras sin número al final (`cfa`/`cfb`/`cfc`,
    `ua`/`ub`/`uc`, etc.).
- **Verificado con las 3 filas reales** ya cargadas: `message_id 3`
  (simple) y `5` (simple sin podio) sin cambios; `message_id 14` (la
  doble) → `cuota_final=2,1997` (1,2222×1,8), `race_id="2214063 |
  2214053"`, `dog_id="586001 | 600135"`, `url_carrera` con las 2 URLs
  separadas por " | ", `value_pct=17,7%` (cuota del pick 2,59 vs. cierre
  real combinado 2,20 - ahora sí compara peras con peras). Revisada
  además una muestra amplia (filas 5-50, 500, 1000) y las filas vacías de
  control (1999-2000): sin `#ERROR!`, `resultado_final` sigue en
  "pendiente" donde no hay apuesta.
- Fue necesario ampliar el grid de la hoja (`ws.add_cols`, de 33 a 43
  columnas) para poder escribir hasta la columna `AI`.
- `src/Config.gs`/`src/Setup.gs` actualizados para que futuras hojas
  nazcan ya con este diseño. Pendiente `clasp push`.
- Commits: (pendiente)

## 2026-08-26 (cont.) — Corregido: simples/dobles/tríples en la MISMA pestaña `apuestas` (no una aparte), y bug real de fila vacía → "gano"
- El usuario corrigió el enfoque de la entrada anterior: no quiere una
  pestaña `apuestas_multiples` separada — quiere simples, dobles y tríples
  todas en la misma pestaña `apuestas`. Revertido: pestaña
  `apuestas_multiples` borrada de la hoja real, y las constantes
  `SHEET_APUESTAS_MULTIPLES`/`COLUMNAS_APUESTAS_MULTIPLES` y la función
  `crearApuestasMultiples_` quitadas de `src/Config.gs`/`src/Setup.gs`.
- Alcance acordado con el usuario: cubrir hasta **tríples** (no solo
  dobles, ya que el diseño se generaliza igual de fácil a una pata más).
  **Fuera de alcance a propósito** (el propio usuario los nombró, pero
  pidió no complicar esto ahora): Trixie/Yankee de verdad (varias apuestas
  independientes en un mismo boleto con pagos distintos - no es "todas
  las patas ganan o pierde toda la apuesta", no encaja en este modelo) y
  apuestas "a puesto" (gana si el galgo queda entre los 2 primeros, no
  solo si gana la carrera).
- **Diseño final**: `apuestas` gana 8 columnas de datos nuevas
  (`hipodromo_2/hora_2/trampa_2/seleccion_2` y las mismas `_3`), que
  quedan vacías en una apuesta simple. 3 columnas fórmula nuevas
  (`resultado_pierna_1/2/3`) resuelven cada pata por separado con la MISMA
  lógica que ya existía para una apuesta simple (coincidencia exacta de
  trampa; si no, trampa ganadora de la carrera como "perdió" seguro) —
  ahora factorizada en una función `formulaPierna()` reutilizable en
  `src/Setup.gs`, y devuelve `""` directamente si la pata no existe
  (columna hipódromo_N vacía). `resultado_final` ahora exige que la pata 1
  sea "gano" Y que las patas 2/3 sean "gano" o no existan; pierde en
  cuanto CUALQUIER pata presente pierde, sin esperar a las demás.
- **Bug real encontrado antes de aplicarlo a las 2000 filas** (probado con
  una fila vacía de control, `P1999`/`P2000`, antes de dar por bueno el
  cambio): la primera versión trataba las 3 patas igual, incluida la 1,
  como "vacuamente ganada" si estaba vacía
  (`OR(pierna="";pierna="gano")` en las 3). Con `hipodromo` vacío (fila sin
  ninguna apuesta), las 3 patas daban `""`, y `AND` de 3 condiciones todas
  vacuamente verdaderas dio **`resultado_final="gano"`** — una fila sin
  apuesta se marcaba como ganada. Causa: la pata 1 es OBLIGATORIA (toda
  apuesta real la tiene), a diferencia de la 2/3 que sí son opcionales;
  no debía tratarse igual. Fix: `resultado_final` exige
  `resultado_pierna_1="gano"` literalmente (no vacuo), solo 2/3 aceptan
  "" como paso. Reaplicado a las 2000 filas y reverificado: las filas
  vacías vuelven a dar "pendiente".
- **Verificado con datos reales** sobre las 3 filas ya cargadas en la hoja
  real: `message_id 3` (simple, perdió) y `message_id 5` (simple sin
  podio, perdió) sin cambios tras el rediseño; añadida `message_id 14`
  (la doble Hove/Central Park de la entrada anterior) como fila 4 de
  `apuestas` (pata 1 en A-N, pata 2 en las columnas nuevas W-Z) →
  `resultado_pierna_1=gano, resultado_pierna_2=gano, resultado_final=gano,
  retorno_real=15,54, unidades_netas=9,54` - igual que había dado el
  prototipo en la pestaña separada, ahora dentro de `apuestas`.
- **Limitación conocida, no arreglada hoy**: `cuota_final`/`url_carrera`/
  `value_pct` siguen siendo solo de la PATA 1 (no se extendieron a
  dobles/tríples) — en la fila de `message_id 14`, `value_pct=111,9%` es
  el valor de la pata 1 sola (Droopys Flare, cuota propia 1,22 vs. la
  cuota COMBINADA del pick, 2,59), no un "value" real de la doble
  completa. No es un bug, es un hueco de alcance ya señalado en el propio
  código (`src/Setup.gs`).
- **Layout físico de columnas en la hoja real, distinto del que generaría
  un `setupSheet` en limpio** (documentado para no confundir a futuro):
  no se puede insertar columnas en medio de una hoja con fórmulas ya
  aplicadas sin arriesgar romperlas, así que las columnas nuevas de hoy
  (`hipodromo_2`... y `resultado_pierna_1/2/3`) se añadieron al FINAL de
  la hoja real (columnas W en adelante), después de las columnas fórmula
  viejas (`O:V`), en vez de agruparse junto a las demás columnas de datos
  como sí hace `COLUMNAS_APUESTAS` en el código para una hoja nueva. Es
  inofensivo: todo el código de escritura (`appendRowByHeader_` en
  `Sheets.gs`) busca columnas por nombre de cabecera, nunca por letra fija.
- Pendiente `clasp push` para que `src/Setup.gs`/`src/Config.gs` (ya
  actualizados) coincidan con lo aplicado a mano hoy en la hoja real.
- Commits: (pendiente)

## 2026-08-26 (cont.) — [Enfoque descartado, ver entrada siguiente] Prototipo de resolución de apuestas "dobles" (2 carreras combinadas), pestaña `apuestas_multiples`
- Pedido del usuario: probar cómo se resolvería el gano/perdió de una
  apuesta doble, con datos reales cargados en la hoja para verlo.
- **Caso de prueba real** (no inventado): `message_id 14` en
  `data/mensajes_crudos.csv`, "Apuesta Doble Hove/Central Park" — pata 1
  Hove 20:46 T2 Droopys Flare, pata 2 Central Park 20:50 T5 Zari Aki,
  cuota combinada 2,59, stake 6. `fecha_recibido` del CSV backfill
  (2026-08-19) era otra vez la fecha de *proceso*, no la real — mismo
  problema que ya se documentó para `message_id 3` el 2026-08-25. Fecha
  real sacada del `forward_date` del JSON crudo
  (`data/raw_updates_backfill_2026-08-20.json`): **2026-07-25**.
- Resultado real de ambas patas (`results_enriched.parquet`, hora ya
  corregida a UK): Droopys Flare 1º en Hove (fract 2/9 → 1,22 decimal),
  Zari Aki 1º en Central Park (fract 4/5 → 1,80 decimal) — **las dos
  ganaron**.
- **Diseño**: nueva pestaña `apuestas_multiples` (no se reutiliza
  `apuestas` — el esquema de una fila = una selección no encaja con 2
  carreras y una cuota conjunta, tal como ya se documentó el 2026-08-20).
  Cada pata se resuelve con la MISMA lógica que `resultado_final` de
  `apuestas` (coincidencia exacta de trampa; si no, trampa ganadora de esa
  carrera como "perdió" seguro), pero sin el override de
  `resultado_manual` (ese es a nivel de la combinada entera). El
  `resultado_final` de la combinada:
  - si `resultado_manual` existe → manual
  - si CUALQUIER pata está en "perdio" → "perdio" (no hace falta esperar a
    la otra pata, una combinada pierde entera con que falle una)
  - si LAS DOS patas están en "gano" → "gano"
  - si no, "pendiente" (alguna pata sigue sin resultado y ninguna ha
    perdido todavía)
  - `retorno_real`/`unidades_netas`: igual que en `apuestas`, sobre
    `stake`/`cuota_combinada`.
- Implementado en `src/Setup.gs` (`crearApuestasMultiples_`, 200 filas de
  fórmulas pre-rellenadas — mucho menos que las 2000 de `apuestas`, las
  dobles son bastante menos frecuentes) y `src/Config.gs`
  (`SHEET_APUESTAS_MULTIPLES`, `COLUMNAS_APUESTAS_MULTIPLES`). Pestaña
  creada en la hoja real vía `gspread` con la cabecera, la fila real de
  `message_id 14` y las fórmulas.
- Insertadas en `resultados_galgos` las 6 filas de ambas carreras (3
  puestos cada una) para poder verificar. Verificado con `gspread`
  (`effectiveValue`): `resultado_pierna_1=gano, resultado_pierna_2=gano,
  resultado_final=gano, retorno_real=15,54 (6×2,59), unidades_netas=9,54`.
  Revisada además una fila vacía de control: "pendiente" sin `#ERROR!`.
- **Esto es un prototipo de la lógica de resolución, no está enganchado al
  flujo real todavía**: hoy `Main.gs`/`AI.gs` siguen mandando las dobles a
  `revision_manual` en `mensajes_crudos` sin escribir nada estructurado.
  Falta decidir y construir cómo la IA extraería las 2 patas de un pick
  doble y las escribiría en esta pestaña — no implementado, fuera del
  alcance de esta prueba.
- Commits: (pendiente)

## 2026-08-26 (cont.) — Hallazgo del usuario: consultar por `dog_id` sí da posición y cuota exactas fuera de podio (mejora el fallback de "trampa ganadora")
- El usuario preguntó si, visitando la página de resultados de Racing Post,
  se podía ver la posición de `More Firepower` (fuera de podio). Comprobado
  que NO: tanto el endpoint de resultados por carrera
  (`results/blocks.sd?view=result-meeting`) como uno más completo encontrado
  de paso (`view=result-meeting-result`, que sí trae los divisores de
  Forecast/Tricast — verificado que cuadran exactamente con una captura de
  pantalla real que mandó el usuario: `forecast1st=6,forecast2nd=1,
  forecastMoney=11.00` = "F/C: (6x1) £11.00"; `tricast 6-1-3, £22.64` =
  "T/C: (6x1x3) £22.64") **siguen devolviendo solo el podio** — 3 filas,
  igual que el parquet. La página web sí muestra el 4º-6º puesto completo,
  pero por una llamada que no se identificó (probablemente necesita contexto
  de sesión de navegador, SPA renderizada por JS, no visible con un fetch
  de servidor sin ejecutar JS - confirmado con `WebFetch` sobre la URL
  exacta: el HTML no trae nada, todo se carga dinámicamente).
- El usuario propuso una alternativa mejor: en vez de consultar la carrera,
  **consultar el historial propio del galgo por su `dog_id`** — si Racing
  Post guarda el histórico de CADA galgo (necesario para el modelo de
  predicción), ese historial debería incluir su posición en cualquier
  carrera que corriera, esté o no en podio.
- **Confirmado, con datos reales, no hipótesis**:
  1. `dog_id` de "More Firepower" obtenido cruzando por nombre contra
     `data/historical/dog_profile.parquet` de la VM (15.266 galgos):
     `594659`.
  2. Endpoint `https://greyhoundbet.racingpost.com/dog/blocks.sd?race_id=...&dog_id=...&r_date=...&track_id=...&blocks=details`
     (ya usado por `scrape_dog_details()` en
     `src/scraper/scrape_historical.py`, necesita contexto de una carrera
     — se le pasó la propia carrera de Harlow) devolvió 20 entradas de
     `forms` con el historial completo del galgo, **incluida la carrera del
     22/07/2026**: `rOutcomeDesc: "6th"`, `oddsDesc: "4/1"` (cuota SP propia
     de ESE galgo en ESA carrera). Decimal: `1 + 4/1 = 5.00`.
  3. Los ficheros locales de la VM que ya existían (`dog_forms.parquet`,
     `dog_progression.parquet`, `dog_details_sidecar.parquet`) están
     desactualizados para este galgo concreto (última entrada: marzo 2026)
     — no sirvieron. Solo la consulta **en vivo** al endpoint trajo el dato
     de julio.
- **Cambio de diseño (para el futuro script recurrente, no implementado
  hoy)**: el fallback de "trampa ganadora" (INDEX/MATCH en
  `resultado_final`, ver entrada anterior) deja de ser el único recurso
  para picks fuera de podio — pasa a ser la **última red de seguridad**,
  solo si falla el nuevo paso principal: cuando el resultado de la carrera
  no trae la trampa exacta, buscar `dog_id` por nombre del galgo (con el
  riesgo ya conocido de que el nombre esté escrito distinto — ver
  cuestión de naming de entradas anteriores) y consultar
  `dog/blocks.sd?...&dog_id=...` para sacar posición y cuota reales, no
  solo "perdió sin más detalle".
- **Aplicado a la prueba de hoy** para dejarla completa y consistente:
  añadida la fila real de `More Firepower` (trampa 2, posición 6, cuota
  final 5,00) a `resultados_galgos`. Reverificado `message_id 5`: ahora
  resuelve por coincidencia EXACTA en vez de por el fallback —
  `posicion_auto=6, resultado_final=perdio (sin cambios), cuota_final=5,
  value_pct=70` (positivo: el mercado acortó mucho la cuota tras el pick —
  de 8,5 a 5,00 — pese a que el galgo acabó último; el "value" del mercado
  y el resultado de la carrera son cosas distintas).
- Commits: (pendiente)

## 2026-08-26 (cont.) — Añadidos `cuota_final`, `url_carrera` y `value_pct` (SP de cierre, enlace a Racing Post y valor del pick)
- A petición del usuario, tras validar la Fase 7 con los 2 picks de prueba:
  cuota final de cierre en decimal, "value" del pick (cuánto se movió el
  mercado entre el pick y el cierre) y enlace directo a la carrera en
  Racing Post.
- **Esquema extendido** (columnas añadidas al final, nunca insertadas en
  medio — insertar en medio de un rango en producción desplazaría todas las
  referencias de columna por letra ya escritas, tanto en `Setup.gs` como en
  las fórmulas ya aplicadas a mano hoy):
  - `resultados_galgos`: `cuota_final` (decimal, columna H) y `url_carrera`
    (columna I) — los escribirá el mismo script de la VM que rellene el
    resto de la fila (pendiente de construir, ver entrada anterior).
  - `apuestas`: 3 columnas fórmula nuevas (`cuota_final`, `url_carrera`,
    `value_pct`), mismo patrón `INDEX/MATCH` que `posicion_auto`.
- **`cuota_final`**: fuente = campo `fract` de `results_enriched.parquet`
  (SP en formato fraccionario inglés, ej. "9/4", "Evs") convertido a decimal
  (`1 + numerador/denominador`, "Evs"=2.0) por el script que escribe
  `resultados_galgos` — no se intenta convertir fraccionario→decimal con
  fórmulas de Sheets, más simple y menos propenso a errores en Python.
  Búsqueda igual que `posicion_auto` (canódromo+fecha+hora+**trampa**
  exactos): es un dato por galgo, no por carrera, así que si mi trampa no
  tiene fila propia (como `More Firepower`) simplemente no hay dato — no
  se aplica el fallback de "trampa ganadora" de `resultado_final`, no
  tendría sentido (no sabríamos la cuota de un puesto que no vimos).
- **`url_carrera`**: SÍ es un dato de la carrera entera, no de la trampa
  concreta — se busca solo por canódromo+fecha+hora (sin trampa), igual que
  la "trampa ganadora" de `resultado_final`, así que aparece aunque mi
  trampa no tenga fila (confirmado con `More Firepower`: sin `cuota_final`
  pero con `url_carrera` sí resuelta). Formato de URL calcado del que ya
  usa `dashboard.py` de Proyecto Galgos
  (`_rp_result_url`):
  `https://greyhoundbet.racingpost.com/#result-meeting-result/race_id=...&track_id=...&r_date=...&r_time=...`.
  El `track_id` **no está en el parquet histórico** (solo se resuelve en
  vivo contra el endpoint de reuniones de Racing Post, `_fetch_results_tracks`
  de `src/scraper/scrape_results.py`) — para los 2 casos de prueba se
  obtuvo ejecutando esa misma función del proyecto directamente en la VM
  (por SSH, con el `venv` del proyecto: `Central Park`→`track_id=70` el
  21/07/2026, `Harlow`→`track_id=69` el 22/07/2026). El script recurrente
  de la Fase 7 tendrá que resolver el `track_id` de la misma forma al
  escribir cada fila nueva de `resultados_galgos`.
- **`value_pct`**: `(cuota_pick / cuota_final − 1) × 100`, redondeado a 1
  decimal. Positivo = la cuota se acortó después del pick (el mercado
  terminó dándole más opciones que cuando se apostó — buena señal,
  "steam"); negativo = se alargó (mala señal). Ejemplo real verificado:
  Droopys Rarity, cuota pick 2,38 → cierre 3,25 → `value_pct = -26,8`
  (coherente con que acabara 3º, no 1º). En blanco si no hay `cuota_final`
  (mismo caso que `More Firepower`).
- Verificado con `gspread`/API de Sheets (`effectiveValue`) sobre las 2
  filas de prueba: valores exactamente como se esperaba (ver arriba).
  Revisada además una fila sin resultado: todas las columnas nuevas en
  blanco sin `#ERROR!`.
- Pendiente, explícitamente fuera de este cambio (lo pidió el usuario, mucho
  más lío): guardar/enlazar la captura original del pick (`foto_file_id` de
  Telegram) en algún sitio con URL pública. No implementado.
- `src/Config.gs` (`COLUMNAS_RESULTADOS_GALGOS`) y `src/Setup.gs`
  (`crearApuestas_`) actualizados para que futuras hojas nazcan ya con este
  esquema. Igual que la entrada anterior, aplicado a mano en la hoja real
  vía `gspread` y pendiente `clasp push` para que coincida con Apps Script.
- Commits: (pendiente)

## 2026-08-25 (cont.) — `fecha_pick` del backfill perdía la hora real (medianoche en vez de la hora real)
- El usuario notó que la primera fila cargada mostraba `fecha_pick` a
  medianoche. Comprobado contra el JSON crudo
  (`data/raw_updates_backfill_2026-08-20.json`): el `forward_date` real de
  ese mensaje es `2026-07-21 19:20:25` hora de Madrid - `iso_date()` en
  `scripts/backfill_picks.py` truncaba a solo `YYYY-MM-DD` antes de
  guardarlo, perdiendo la hora. Inconsistente además con el bot en vivo
  (`Main.gs` sí guarda un `Date` completo).
- Fix: `fecha_pick` usa ahora `iso_datetime()` (timestamp completo) en vez
  de `iso_date()` - la función `iso_date()` quedó sin uso, borrada.
  `INT(fecha_pick)` en la fórmula de `posicion_auto` ya se encarga de
  quedarse solo con el día al comparar, así que conservar la hora no
  rompe nada.
- De paso, probado con `gspread` que un string ISO (`2026-07-21T19:20:25Z`)
  escrito en una celda se guarda como TEXTO plano (rompería `INT()`), pero
  el mismo valor en formato `DD/MM/YYYY HH:MM:SS` (el que espera el
  idioma español de la hoja) sí se reconoce como fecha real. A tener en
  cuenta para el resto del backfill: hay que convertir a esa zona horaria
  y formato al cargar filas en la hoja, no basta con pegar el ISO del CSV
  tal cual.
- CSVs regenerados con el fix (`data/apuestas.csv`, mismos 82
  procesados/7 revisión manual de siempre). Fila de prueba (message_id 3)
  corregida en la hoja real y reverificada: sigue sin `#ERROR!`.
- Commits: (pendiente)

## 2026-08-25 (cont.) — Causa real de los `#ERROR!`: la hoja está en español (`,` vs `;`)
- El fix anterior (INDEX/MATCH) tampoco funcionó - seguía dando
  `#ERROR!`. Como llevábamos ya 3 intentos fallidos a base de capturas de
  pantalla, el usuario creó una **cuenta de servicio de Google** (Sheets
  API + Drive API, compartida como Editor de la hoja) para que se pudiera
  depurar en caliente contra la hoja real con `gspread`, en vez de seguir
  a ciegas. Clave guardada en la carpeta de trabajo temporal (nunca en el
  repo - se detectó que el usuario la había guardado primero dentro de la
  carpeta del proyecto, sin coincidir con el patrón `service_account.json`
  de `.gitignore`; movida fuera antes de tocar nada más).
- Con acceso directo, `sheets.get` con `fields=...effectiveValue` dio el
  mensaje de error real por primera vez: `"Formula parse error."` -un
  error de análisis, no de ejecución, coherente con que ni IFERROR ni
  ARRAYFORMULA lo arreglaran en los intentos anteriores.
- Causa real: la hoja tiene el idioma en **español (es_ES)**
  (`properties.locale`), donde el separador de argumentos de las fórmulas
  es `;`, no `,` (la coma es el separador decimal en ese idioma). Todas
  las fórmulas escritas hasta ahora - tanto desde `Setup.gs` (Apps
  Script) como en las pruebas directas por la API de Sheets - usaban
  comas. Nada tenía que ver con QUERY, MATCH, ARRAYFORMULA ni con que
  `resultados_galgos` estuviera vacía; esos eran síntomas, no la causa.
- Verificado con `gspread` antes de tocar el código: la misma fórmula
  INDEX/MATCH con `;` en vez de `,` evalúa bien tanto sin match (cadena
  vacía) como con un match real insertado a mano de prueba en
  `resultados_galgos` (fila de prueba borrada después). Las 5 fórmulas
  encadenadas probadas en la fila 2 real dieron los valores esperados
  (`posicion_auto=1`, `resultado_final=gano`, `fuente_resultado=auto`,
  `retorno_real=11`, `unidades_netas=7`) antes de aplicar el cambio.
- Las 5 fórmulas de `Setup.gs` reescritas con `;`. Quedaba la duda de si
  `Range.setFormulas()` de Apps Script (que según su documentación espera
  las fórmulas en locale en_US y las traduce él solo) aceptaría bien un
  string ya en formato `;` en vez de `,` - probado que sí: tras
  `clasp push` + nueva versión + `clasp redeploy` y que el usuario
  re-ejecutara `setupSheet`, se comprobó por `gspread` (sin necesidad de
  que el usuario mirara nada) que las 5 filas muestreadas (2, 3, 100,
  1000, 2000) quedaron sin `#ERROR!`, con `resultado_final = "pendiente"`
  como corresponde sin datos en `resultados_galgos`.
- Con acceso por `gspread` ya montado, se puede seguir usando para
  depurar cualquier cosa de la hoja sin depender de capturas del usuario.
- Commits: (pendiente)

## 2026-08-25 (cont.) — `posicion_auto` rediseñada: INDEX/MATCH en vez de QUERY
- El fix anterior (guarda `IF(COUNTA(...)=0,"",...)`) no funcionó: seguía
  dando `#ERROR!`. Diagnóstico aislado en la propia hoja (el usuario probó
  dos fórmulas sueltas): `COUNTA(resultados_galgos!$A$2:$A)` → `0`
  (correcto, confirma que está vacía), pero incluso un `QUERY` estático
  sin fecha ni concatenación (`=QUERY(resultados_galgos!A:F,"select F
  where A='x'",0)`) da `#ERROR!` él solo. Conclusión: es una limitación de
  `QUERY` en Sheets contra un rango sin ninguna fila de datos - falla al
  "compilar" la cadena de consulta, no al ejecutarla, así que ni `IFERROR`
  ni un `IF` que lo rodee (evitando que se llegue a evaluar) lo evitan.
- Rediseñada `posicion_auto` en `Setup.gs` sin `QUERY`: `INDEX` +
  `MATCH` con multiplicación de arrays booleanos
  (`(A=hipodromo)*(INT(B)=INT(fecha))*(C=hora)*(D=trampa)`), acotado a
  `$2:$5000` en vez de columna abierta (evita barrer un rango gigante).
  Sin match, `MATCH` da el `#N/A` normal de siempre, que `IFERROR` sí
  atrapa sin problema - ya no depende de que `resultados_galgos` tenga
  datos para no reventar.
- Commits: (pendiente)

## 2026-08-25 (cont.) — Dos bugs más en la verificación end-to-end: `apuestas` y sus fórmulas
- Segunda ronda de pruebas (ya sin reintentos de Telegram): los picks se
  guardaban, pero mal.
- **Bug A**: `apuestas` tiene las 5 columnas fórmula pre-rellenadas hasta
  la fila 2000 (`Setup.gs`), así que `sheet.getLastRow()` siempre devuelve
  ~2000 aunque no haya datos reales. `appendRowByHeader_` usaba
  `sheet.appendRow()` (que se basa en `getLastRow()`), así que los picks
  se escribían en la fila 2001 en vez de en la 2. Fix: `proximaFilaVacia_`
  busca la primera fila libre por la columna `message_id` (nunca tiene
  fórmula) en vez de fiarse de `getLastRow()`.
- **Bug B** (todas las columnas fórmula de `apuestas` en `#ERROR!`):
  confirmado carácter a carácter que la fórmula de `posicion_auto` estaba
  bien escrita - el problema es que `resultados_galgos` está vacía
  todavía (Fase 7 sin montar), y `QUERY` no puede inferir el tipo de una
  columna sin datos para compararla con el literal `date '...'` - error
  de parseo de `QUERY` que ni `IFERROR` atrapa. Fix: guarda
  `IF(COUNTA(resultados_galgos!$A$2:$A)=0,"",...)` antes del `QUERY`.
- **Bug C** (efecto secundario del fix del Bug A, detectado en la
  siguiente prueba): el primer arreglo de `appendRowByHeader_` seguía
  construyendo la fila con el ancho completo de la hoja
  (`sheet.getLastColumn()`, 19 columnas en `apuestas`), así que al
  escribir por `setValues()` pisaba las 5 columnas fórmula con cadenas
  vacías en la fila que tocaba. Fix: la fila que se escribe solo llega
  hasta la última columna de DATOS real (las de `valoresPorColumna`),
  nunca hasta las columnas fórmula.
- Los 3 fixes en `src/Sheets.gs` y `src/Setup.gs`. Cada ronda de pruebas
  dejó picks de prueba a medio guardar en `apuestas` - sin problema,
  son solo datos de prueba, se limpian al re-ejecutar `setupSheet`
  (`mensajes_crudos` no se toca, ahí sí queda constancia de todos los
  intentos).
- `clasp push` + nueva versión + `clasp redeploy` de la misma
  implementación tras cada fix (versiones 3 y 4).
- Commits: (pendiente)

## 2026-08-25 (cont.) — Bug real en producción: Telegram rechazaba la respuesta del webhook (302)
- Primera prueba real: 2 picks distintos mandados al grupo, pero solo 1
  respuesta del bot. `mensajes_crudos` solo tenía 1 fila
  (`message_id 92`) pese a 9 ejecuciones de `doPost` en el registro.
- Diagnóstico: el dedup por `message_id` funcionaba bien (esas 9 no
  crearon duplicados) - el problema real era que **Telegram nunca daba
  por entregado el primer mensaje**. `getWebhookInfo` lo confirmó:
  `"last_error_message":"Wrong response from the webhook: 302 Found"`,
  `pending_update_count: 2`.
- Causa raíz: `ContentService.createTextOutput()` en una Web App de Apps
  Script se sirve con una redirección 302 (a `script.googleusercontent.com`)
  a nivel de infraestructura de Google. Telegram no la acepta como
  confirmación válida, así que reintenta el mismo update indefinidamente
  con backoff creciente (19s, 4s, 6s, 10s, 18s, 33s, 66s, 87s...) - y no
  entrega el siguiente mensaje en cola hasta que el anterior queda
  confirmado, así que el segundo pick se quedó bloqueado detrás del
  primero.
- Fix: sustituir `ContentService.createTextOutput(...)` por
  `HtmlService.createHtmlOutput(...)` en los 5 `return` de `doPost`/
  `manejarReply_` (`Main.gs`) - esa respuesta no sufre la redirección.
  `clasp push` + nueva versión (`clasp version`) + redesplegada la misma
  implementación a esa versión (`clasp redeploy`, mismo deployment ID, la
  URL del webhook no cambia). Cola de Telegram limpiada con
  `setWebhook?...&drop_pending_updates=true` (se descartan los 2 mensajes
  de prueba atascados, sin pérdida real).
- Pendiente: repetir la prueba end-to-end con picks nuevos para confirmar
  que ya no reintenta y que se guardan y responden bien.
- Commits: (pendiente)

## 2026-08-25 (cont.) — Desplegado como Web App y webhook registrado (Fase 5 completa)
- Implementación "Aplicación web" creada desde el editor (ejecutar como
  el usuario, acceso "Cualquier usuario"). URL `/exec` obtenida.
- Webhook registrado en Telegram con `setWebhook` (URL + `?token=` con el
  `WEBHOOK_SECRET_TOKEN`). Verificado con `getWebhookInfo`: URL correcta,
  `pending_update_count: 0`, sin `last_error_message`.
- Pendiente: verificación end-to-end (Fase 4/6 en producción) - mandar un
  pick de prueba real al grupo de Telegram y comprobar que aparece en
  `mensajes_crudos`/`apuestas` y que el bot responde.
- Commits: (pendiente)

## 2026-08-25 (cont.) — Secrets configurados en Script Properties (Fase 3 completa)
- Las 3 Script Properties (`TELEGRAM_BOT_TOKEN`, `AI_PROVIDER_API_KEY`,
  `WEBHOOK_SECRET_TOKEN`) añadidas a mano en el editor de Apps Script.
  `WEBHOOK_SECRET_TOKEN` generado por el usuario mismo (no había valor
  previo). Verificado con `checkConfig`: "OK: todas las propiedades
  requeridas están configuradas."
- Commits: (pendiente)

## 2026-08-25 (cont.) — `setupSheet` ejecutado, hoja construida (Fase 1 completa)
- Ejecutado `setupSheet` desde el editor de Apps Script. Log:
  "Listo: mensajes_crudos, apuestas y resultados_galgos creadas." Las 3
  pestañas existen con sus cabeceras y las fórmulas de `apuestas`.
- De paso, dos gotchas de `clasp` 3.3.0 documentadas: el comando para
  abrir el editor ya no es `clasp open` sino `clasp open-script` (cambió
  de nombre); y el desplegable de funciones del editor de Apps Script solo
  lista las funciones del archivo actualmente abierto en el panel, no
  todas las del proyecto - hay que abrir `Setup.gs` primero para que
  aparezca `setupSheet` en el desplegable.
- Commits: (pendiente)

## 2026-08-25 (cont.) — Código subido a Apps Script (Fase 2 completa)
- `clasp create --type sheets --parentId <id> --rootDir ./src` falló con
  "Insufficient Permission": el scope `drive.file` que usa `clasp` para esa
  operación solo da acceso a archivos creados por la propia app clasp, no a
  la hoja creada por el conector de Drive. Rodeo: vincular el script desde
  la propia hoja (**Extensiones > Apps Script**, con permisos plenos por
  venir de la UI de Google) y apuntar `clasp` a ese script a mano con un
  `.clasp.json` (`scriptId` + `rootDir: ./src`) en vez de usar
  `clasp create`.
- Con eso, `clasp push` seguía dando "Insufficient Permission" — causa
  distinta: la API de Google Apps Script estaba desactivada para la cuenta
  (toggle en https://script.google.com/home/usersettings, off por
  defecto). Activada. Aun así seguía fallando con el token de sesión viejo;
  hizo falta `clasp logout` + `clasp login` de nuevo para que se generase
  un token que ya reflejara el cambio.
- `clasp push` funcionó: 8 archivos subidos (`AI.gs`, `Commands.gs`,
  `Config.gs`, `Main.gs`, `Setup.gs`, `Sheets.gs`, `Telegram.gs`,
  `appsscript.json`), sobrescribiendo el manifest por defecto del script
  vacío con el nuestro (`clasp` avisa y pide confirmación antes de
  hacerlo).
- `docs/DESPLIEGUE.md` actualizado para reflejar este camino real (vincular
  desde la hoja + `.clasp.json` manual) en vez del `clasp create` original,
  que no funciona en este caso.
- Commits: (pendiente)

## 2026-08-25 (cont.) — Hoja de Google creada, `clasp login` hecho, `Setup.gs` escrito
- `clasp login` completado por el usuario (token guardado en
  `~/.clasprc.json`).
- Hoja de Google **"Picks Premier Galgos"** creada vía el conector de
  Google Drive (no hay API de Sheets en ese conector, solo gestión de
  archivos, así que la creación fue de la hoja vacía, no de su contenido).
  ID: `1axZnIIIXBpqVhhb6RVGawNaWpSLVLBwXK079MxcOfF4`. Propietaria:
  `premiergalgos@gmail.com`.
- Escrito `src/Setup.gs`: función `setupSheet()` para ejecutar a mano una
  vez desde el editor de Apps Script (Fase 1 del plan) — crea las 3
  pestañas (`mensajes_crudos`, `apuestas`, `resultados_galgos`) con sus
  cabeceras, añade las 5 columnas fórmula de `apuestas`
  (`posicion_auto`/`resultado_final`/`fuente_resultado`/`retorno_real`/
  `unidades_netas`, sección 5 del PLAN.md) pre-rellenadas hasta la fila
  2000, y borra la pestaña por defecto ("Hoja 1"). Las letras de columna
  de las fórmulas se calculan a partir de la posición real de cada
  cabecera (no están fijas a mano), para no depender del orden exacto.
- Commits: (pendiente)

## 2026-08-25 (cont.) — API key de Gemini probada en caliente contra la API real
- Con la API key ya en `.env`, se probó `src/AI.gs` contra la API real de
  Gemini (fuera de Apps Script, con `curl`) usando picks reales de
  `data/mensajes_crudos.csv`.
- El modelo `gemini-2.0-flash` que se había puesto inicialmente ya no existe
  (404 "no longer available") — la propia API redirige al actual,
  `gemini-3.6-flash`. Actualizado el código.
- Extracción verificada correcta en dos casos reales: un pick normal (todos
  los campos bien extraídos) y una "Apuesta Doble" (2 carreras combinadas,
  detectada como `es_apuesta_multiple: true` con el resto de campos a
  `null`, tal como se diseñó).
- Detectado que `gemini-3.6-flash` por defecto gasta un presupuesto de
  "thinking" grande (~580 tokens de razonamiento interno para una
  extracción trivial de ~80 tokens de respuesta) — más lento y gasta cuota
  del tier gratis más rápido sin mejorar el resultado. Añadido
  `generationConfig.thinkingConfig.thinkingBudget: 128` en `src/AI.gs`;
  probado que con ese límite bajo el resultado sigue siendo correcto en
  ambos casos de prueba.
- Commits: (pendiente)

## 2026-08-25 — Decisión IA: Gemini Flash, `src/AI.gs` adaptado
- Decisión del usuario: **Gemini Flash** en vez de Claude Haiku para la
  extracción de picks. Motivo: la API de Gemini tiene tier gratuito; la API
  de Claude (Anthropic) es un producto distinto de la suscripción de Claude
  (claude.ai/Claude Code) y se factura aparte por token, así que aunque el
  coste sería marginal, prefiere coste cero.
- `src/AI.gs` reescrito: `callGeminiExtraction_` en vez de
  `callClaudeExtraction_`, llamando a
  `generativelanguage.googleapis.com/.../gemini-2.0-flash:generateContent`
  con `system_instruction` + `contents` (formato Gemini) y
  `generationConfig.responseMimeType: "application/json"` en vez del
  formato de mensajes de Anthropic. Mismo contrato de entrada/salida
  (`extraerPick(texto, fotoBlob)`), mismo prompt de extracción — no cambia
  nada del resto del pipeline (`Main.gs`, `Config.gs` ya usaban el nombre
  genérico `AI_PROVIDER_API_KEY`, sin tocar).
- `PLAN.md` sección 13 y `docs/DESPLIEGUE.md` actualizados para reflejar la
  decisión ya tomada en vez de dejarla abierta.
- Sigue pendiente conseguir la API key de Gemini y rellenar el `.env` local
  y, más adelante, la Script Property `AI_PROVIDER_API_KEY`.
- Commits: (pendiente)

## 2026-08-20 — Fase 0 verificada, backfill del histórico y código de Fases 2/4/6

- **Fase 0 verificada en caliente**, no solo "creada": bot creado con
  BotFather (`@PicksPremierGalgosBot`), privacidad de grupo desactivada,
  añadido como admin (esto migró el grupo a supergrupo — el `chat_id`
  cambió de `-5370726728` a `-1004303594416`, es el que hay que usar en
  producción). Confirmado con `getMe`/`getUpdates` que el bot recibe todos
  los mensajes del grupo.
- El usuario reenvió el histórico completo del canal del tipster al grupo:
  **89 picks reales**. Se usaron como datos de prueba reales en vez de
  ejemplos inventados. Formato del caption bastante consistente, con
  variaciones detectadas: palabra "Galgo" opcional antes de la trampa,
  hipódromo antes o después de la hora indistintamente, apuestas
  "dobles"/combinadas (2 carreras en un pick, no encajan en el esquema de
  una fila = una selección → deben ir a `revision_manual`), y alguna
  errata suelta del tipster (p. ej. "Ciota" en vez de "Cuota").
- **Backfill local**: sin acceso todavía a la hoja de Google (pendiente de
  cuenta de servicio/Fase 1), se escribió `scripts/backfill_picks.py` que
  parsea los 89 mensajes por regex (no hace falta IA, los captions ya
  traen todo en texto) y genera `data/mensajes_crudos.csv` y
  `data/apuestas.csv` con la misma estructura que tendrá la hoja. 82/89
  procesados automáticamente, 7 en revisión manual (6 dobles + 1 errata).
  `data/` añadida a `.gitignore` (son datos reales del tipster, no tienen
  que vivir en el repo).
- Comprobado: la cuenta de servicio de Google que ya usa Proyecto Galgos
  para escribir en Sheets (`inlaid-sentinel-373522-....json`) no está
  presente en este ordenador (vive solo en la VM, según sus propias
  reglas de seguridad) — no reutilizable desde aquí sin que el usuario la
  traiga. El backup diario de Proyecto Galgos a Google Drive usa `rclone`
  (tarea `galgos-backup`, 03:30), un mecanismo distinto que tampoco sirve
  para escribir filas en Sheets.
- **Código completo de las Fases 2, 4 y 6** escrito en `src/*.gs` (listo
  para `clasp push` en cuanto se haga login): `doPost` que guarda crudo
  siempre primero, extrae con la API de Claude (Haiku, visión + texto) y
  escribe en `apuestas`, o marca `revision_manual` si faltan campos o es
  una apuesta múltiple; comandos por reply (`ganó`/`perdió`/`ocultar`/
  `mostrar`/`corregir campo=valor`); secrets vía `PropertiesService`
  (nunca en código); `LockService` para condiciones de carrera; dedup por
  `message_id` para reintentos del webhook de Telegram. `clasp` instalado
  globalmente (`npm install -g @google/clasp`), pendiente solo el login
  interactivo del usuario.
- Pasos de despliegue restantes documentados en `docs/DESPLIEGUE.md`
  (login de `clasp`, vincular a la hoja, Script Properties, desplegar Web
  App, registrar webhook en Telegram) — todos requieren estar delante del
  ordenador, quedan pendientes de que el usuario los ejecute.
- Pendiente de decisión del usuario: Claude vs Gemini para la API key (el
  código ya está escrito asumiendo Claude Haiku, la recomendación del
  plan; cambiarlo a Gemini es solo tocar `src/AI.gs`).
- Commits: (pendiente)

## 2026-08-19 — Cambio de stack: PHP/MySQL en Sered → Google Apps Script + Sheets
- El plan inicial usaba PHP+MySQL en el hosting Sered. Se descartó porque el
  requisito principal es poder manipular la información a mano con
  facilidad; una hoja de cálculo lo resuelve directamente (editar la celda),
  mientras que una BBDD tradicional exige comandos o phpMyAdmin.
- Nuevo stack: el webhook de Telegram lo recibe un Web App de Google Apps
  Script (`doPost`), que escribe en una Google Sheet con 3 pestañas
  (`mensajes_crudos`, `apuestas`, `resultados_galgos`). El resultado/retorno
  de cada apuesta se calcula con fórmulas de la propia hoja (`QUERY` contra
  `resultados_galgos`), no con un cron de verificación.
- La sincronización VM→Sheets sustituye a VM→MySQL: un script Python con
  `gspread` + cuenta de servicio de Google, mismo principio de antes (solo
  push saliente, la VM no expone nada nuevo).
- El panel deja de ser una página PHP con `.htpasswd`: ahora es la propia
  hoja o Looker Studio; el control de acceso es compartir la hoja de Google.
- Seguridad del webhook adaptada a la limitación real de Apps Script: no
  expone cabeceras HTTP personalizadas en `doPost`, así que el secreto va
  como parámetro en la URL (`?token=`) en vez del header de Telegram.
- Código de Apps Script versionado en este repo vía `clasp`.
- Commits: 3c62c01, cce547c

## 2026-08-19 — Plan inicial del proyecto
- Se revisó un primer borrador de plan (bot de Telegram para registrar picks
  de un tipster, verificación de resultados vía scraping de Sporting Life) y
  se rediseñó: la verificación automática se resuelve reutilizando el
  pipeline de resultados que ya scrapea Racing Post en la VM de Proyecto
  Galgos (mismas pistas), en vez de construir un scraper nuevo. Push saliente
  VM→MySQL Sered, sin exponer nada nuevo en la VM.
- Se definieron además: ingesta en dos etapas (mensaje crudo → IA →
  confirmación) para evitar timeouts de Telegram, estado `revision_manual`
  para extracciones incompletas, comando `corregir` por reply, dedup real
  por `message_id`, stake en unidades (no moneda).
- Repo creado como proyecto independiente (no vive dentro de Proyecto
  Galgos, stack y despliegue distintos).
- Commits: (primer commit)

