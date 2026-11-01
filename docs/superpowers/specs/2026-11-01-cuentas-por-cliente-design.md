# Cuentas por cliente (captación) — diseño

Fecha: 2026-11-01

## Objetivo
Saber, por cada persona de Telegram que ha recibido apuestas de los canales de
venta desde el 22/07/2026:

- a cuántas apuestas ha entrado (pagadas y gratis),
- cuántas unidades lleva ganadas o perdidas,
- cuánto ha pagado en € (todas sus compras de overoption, de todos sus correos),
- y una simulación de lo que llevaría apostando a **10 € por unidad** (un pick
  de stake 2 a 20 €, uno de stake 0,5 a 5 €), con el balance frente a lo pagado.

## Decisiones del dueño (2026-11-01)
1. **Usuario = persona de Telegram.** Hace falta el cruce correo ↔ Telegram
   porque el dueño da apuestas gratis (compensaciones cuando falla y la
   gratuita de bienvenida): sin ellas, las unidades de cada persona salen mal.
2. **Las gratis llegan de dos formas:** el dueño pega el enlace del siguiente
   canal por privado desde su cuenta, o lo publica en el canal donde se falló
   (a los clientes se les dice que no salgan del canal para recibirlo ahí).
3. **Simulación:** 10 € por unidad.
4. **Desde el 22/07/2026** (primer canal de venta). Lo anterior no se cuenta.
5. **Cruce: forma A** (pruebas por correo, automático solo con prueba fuerte;
   lo dudoso va a la lista del dueño). Descartadas: parchear el cruce actual
   (B) y dejarlo todo en manos del dueño (C).
6. **Más protección (2026-11-02):** un correo solo se da a alguien con 3
   compras buenas o más y al menos el 80 % de las comprobables buenas (no
   basta con 2), y la comprobación sigue siempre, también después de
   asignarlo y en los que confirmó el dueño. Pestaña por correo con compras,
   comprobables, buenas y malas.
7. **Aviso:** si un correo pasa a «revisar», el bot se lo dice al dueño al
   momento (una vez por correo) y su fila sale en rojo en el Sheet.

## Hechos medidos (2026-11-01, base real, solo lectura)
- **Gratis y pagadas entran con el mismo enlace.** Las 259 entradas a los
  canales desde que hay registro (27/10) usan el enlace de overoption del
  canal, también una gratuita conocida. Por el enlace no se puede separar
  una gratis de una pagada.
- **Nadie entra antes de pagar.** En 519 compras ya confirmadas, la entrada
  llega entre 3 s y 34 s después del pago (mediana 8 s, percentil 90 34 s);
  ninguna antes, salvo una a −43 min (enlace reutilizado). El margen actual
  de 30 s hacia atrás (`ANTES_S`) solo cuela a quien ya tenía el enlace.
- **Cruce actual frente a los 42 correos confirmados por el dueño** (quitando
  sus respuestas): 287 compras bien, 2 mal, 431 sin persona. Lo que falla son
  los cruces sueltos por hora (2 de 10 mal), que hoy se extienden a todas las
  compras del correo. El cruce por nombre acertó en todas (207).
- **El cruce no usa el nombre en contra:** un correo con un nombre de pila
  puede acabar en una persona de Telegram con otro nombre distinto.
- **Registro de entradas y salidas desde el 27/10.** Antes solo se sabe quién
  sigue dentro (miembros con su fecha de entrada y listas de quién se unió con
  cada enlace, que solo traen a quien sigue dentro).
- Ventas desde el 22/07/2026: unas 1.740. Las apuestas de los canales están
  en el grupo de picks salvo 5 que el dueño descartó (análisis del 24/10), y
  la hoja de picks ya calcula `resultado_final` y `unidades_netas` con los
  resultados de Racing Post.

## Piezas

### 1. Apuestas de cada canal
- Leer los mensajes de los canales de venta (carpeta «ch ventas», desde el
  22/07) y quedarse con las apuestas (`analisis.es_apuesta`,
  `analisis.datos_apuesta`).
- Cada apuesta se busca en la hoja de picks con la regla que ya existe
  (`analisis.en_grupo`: reenviado, mismo texto, o misma hora y galgo) y de ahí
  salen `stake`, `cuota`, `resultado_final` y `unidades_netas` (pestañas
  `apuestas` y `apuestas_exoticas`).
- Se guarda en una tabla nueva `canales_apuestas` (canal, mensaje, fecha,
  texto, fila de la hoja de picks, stake, resultado, unidades). Las que no se
  encuentren en la hoja salen marcadas «sin resultado» y no suman unidades.
- **Por comprobar al empezar:** que la cuenta de servicio de captación pueda
  leer la hoja de picks. Si no, el dueño la comparte en modo lector.

### 2. Entradas gratis
Tabla nueva `entradas_gratis` (persona, canal, desde cuándo, origen,
referencia):
- **Por privado:** cada mensaje del dueño en un chat privado con el enlace de
  un canal de venta. El lector ya ve esos mensajes en directo (`al_enviar`);
  se apunta cada enlace, no solo el primero (`usuarios.enlace_venta` guarda
  solo la gratuita). Lo anterior se recupera una vez leyendo los chats.
- **En el canal fallado:** un mensaje de un canal de venta con el enlace de
  otro canal de venta. Reciben esa gratis quienes estaban en el canal fallado
  cuando se publicó.
- Una entrada a un canal es **gratis** si esa persona tenía una gratis de ese
  canal antes de entrar y no hay una compra suya asignada a ese canal.

### 3. Cruce correo ↔ Telegram (forma A)
Sustituye la lógica actual de `pagos.emparejar_ventas` (eliminación por
vueltas, un solo cruce que da el correo, etc.):

1. **Candidatos de cada compra:** quienes entraron a ese canal entre 0 s y
   `VENTANA_S` (180 s) después del pago. Nunca antes (`ANTES_S` = 0). Fuera:
   quien tenía una gratis de ese canal (punto 2) y quien ya tiene asignada
   otra compra de ese canal (nadie paga dos veces).
2. **Por correo:** cada compra del correo se mira frente a cada persona
   (definiciones en el punto 3 bis: comprobable, buena, mala). El correo es
   de esa persona si:
   - tiene 3 buenas o más,
   - las buenas son al menos el 80 % de sus comprobables,
   - la segunda persona tiene como mucho la mitad de buenas que ella,
   - y el nombre no choca.
3. **Nombre que choca:** el correo trae un nombre de pila reconocible y el
   nombre de Telegram trae otro nombre de pila distinto (p. ej. «victor…» y
   «Raúl»). Entonces nunca se asigna solo: va a la lista del dueño, con la
   prueba por hora al lado.
4. **Nombre que casa** (como hoy `por_nombre`): asigna el correo salvo que la
   hora lo contradiga (otra persona cumple el punto 2). Queda en «vigilar»
   hasta que tenga 3 buenas (punto 3 bis).
5. **Lo que diga el dueño** (pestaña «Correos por identificar») manda sobre
   todo.
6. **El resto** queda sin persona y va a la lista del dueño con sus
   candidatos, ordenada por € gastados.

### 3 bis. Comprobación continua y avisos
Cada compra de un correo frente a una persona (la asignada o, si no hay, la
mejor candidata):
- **Comprobable:** se puede ver si esa persona entró en ese canal después del
  pago: hay registro del canal a esa hora (desde el 27/10) o la persona sigue
  en el canal (lista del enlace o miembros con fecha de entrada).
- **Buena:** comprobable y la persona entró entre 0 s y `VENTANA_S` después
  del pago.
- **Mala:** comprobable y la persona no entró en esa ventana (entró a otra
  hora o, con registro, no entró).
- Si la persona ya estaba dentro antes del pago (p. ej. por una gratis), esa
  compra no cuenta ni como buena ni como mala: queda sin comprobar.

En cada sincronización se recalcula todo, también para los correos ya
asignados y los que confirmó el dueño. Estado del correo:
- **OK:** cumple la regla del punto 3.2 (o lo confirmó el dueño) y no salta
  ningún aviso.
- **Vigilar:** tiene persona pero aún no llega a la regla, o tiene alguna
  mala suelta.
- **Revisar:** salta cualquiera de estos avisos:
  - 2 compras comprobables seguidas que son malas;
  - las buenas bajan del 80 % de las comprobables;
  - tuvo buenas, pero ninguna en sus últimas 5 compras (p. ej. 2 buenas al
    principio y luego nada en 10 o 20 compras). Sin ninguna buena es falta
    de datos (compras antiguas sin forma de comprobar), no algo raro: medido
    el 2026-11-02, marcaba 7 correos confirmados por el dueño sin ningún dato.

Los correos que se dan solos (por compras o por nombre) se guardan (tabla
`pagos_asignados`) y conservan su persona en las siguientes
sincronizaciones aunque dejen de cumplir la regla; el «no» del dueño bloquea
cualquier asignación automática de ese correo. Un correo en «revisar» **no
pierde a su persona** (sus compras siguen contando para ella) hasta que el
dueño lo mire: escribe otra persona o «no»
en «Correos por identificar», o lo deja como está. Al pasar a «revisar», el
bot avisa al dueño al momento con el correo, la persona y el motivo; una vez
por correo (tabla nueva con el último estado avisado), y no vuelve a avisar
de ese correo hasta que haya estado en OK y vuelva a caer.

Pestaña «Correos · comprobación», una fila por correo: correo, usuario de
Telegram, id de Telegram, compras, comprobables, buenas, malas, fecha de la
última buena, estado y motivo. Las filas en «revisar» en rojo.

### 4. Cuentas por persona
Por persona de Telegram:
- **Pagadas:** las compras de sus correos (cada compra = un canal).
- **Gratis:** las entradas gratis del punto 2.
- **Sin explicar:** entró en el canal pero no hay compra ni gratis suya (puede
  ser la compra de un correo sin persona). Se cuenta aparte.
- Apuestas y aciertos de esos canales; unidades = suma de `unidades_netas`;
  simulación = unidades × 10 €; balance = simulación − € pagados.

Los correos sin persona también salen, una fila por correo, con sus compras,
€, apuestas, unidades y simulación, para que no se pierda ningún €.

### 5. Salida
Pestaña nueva «Clientes · cuentas» en el Sheet de captación, una fila por
persona: nombre y @ de Telegram, sus correos, compras, € pagados, canales
pagados, canales gratis, canales sin explicar, apuestas, aciertos, unidades,
simulación 10 € y balance. Debajo, los correos sin persona. Y la pestaña
«Correos · comprobación» del punto 3 bis. Las dos se reescriben con la
sincronización del Sheet que ya existe (`captacion-sheet`), que es también la
que comprueba los avisos.

### 6. Examen fijo del cruce
Un comando que calcula el cruce sin las respuestas del dueño y lo compara con
ellas: compras bien, mal y sin persona, y correos con algún error. El cruce
nuevo solo se instala si no tiene más «mal» que el actual. Se ejecuta antes
de cualquier cambio en el cruce y el resultado va a la bitácora.

## Límites
- Quien salió de un canal antes del 27/10 no aparece en ningún sitio de
  Telegram: sus entradas de antes no se ven.
- Una gratis por privado o por canal solo se ve si el enlace está en el
  mensaje (no en una foto).
- Las apuestas sin fila en la hoja de picks no suman unidades.

## Seguridad
- Con la cuenta del dueño solo se lee. Leer chats y canales
  (`messages.GetHistoryRequest`) y comprobar a qué canal lleva un enlace
  (`messages.CheckChatInviteRequest`) ya están en `LECTURA`: **ningún permiso
  nuevo de Telegram.**
- La sesión de Telegram no la usan dos programas a la vez (parar
  `captacion-lector@real` antes de una lectura puntual).
- Repo público: ni correos, ni ids, ni nombres, ni enlaces en código, pruebas
  o bitácora. Pruebas con datos inventados.

## Pruebas
- `unittest` con datos inventados para cada pieza: apuestas de un canal,
  gratis por privado y por canal, cada regla del cruce (incluidos nombre que
  choca, entrada antes del pago, gratis que no es candidata, sombra de la
  segunda persona, menos de 3 buenas) y las cuentas.
- La comprobación continua: buena, mala y sin comprobar; cada aviso de
  «revisar»; que se avisa una sola vez por correo y vuelve a avisar tras
  pasar por OK; que un correo en «revisar» conserva su persona.
- El examen del punto 6 sobre la base real, antes de instalar.
