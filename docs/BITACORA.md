# Bitácora del proyecto

Registro de cambios significativos (ver regla en `CLAUDE.md`).
Entradas más recientes arriba.

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
- Commits: (este commit)

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
