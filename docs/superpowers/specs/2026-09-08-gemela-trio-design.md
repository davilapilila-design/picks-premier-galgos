# Soporte para gemela y trío — diseño

Fecha: 2026-09-08

## Objetivo
Hoy el bot solo sabe procesar solas apuestas `simple`/`doble`/`triple`
(múltiples de carreras independientes, una selección por carrera). Una
**gemela** (acertar 1º y 2º de UNA carrera) o un **trío** (1º, 2º y 3º de
UNA carrera) — con o sin "reversible" (cualquier orden) — caen hoy en
`tipo_apuesta="otro"` y van directas a revisión manual, sin más. Objetivo:
reconocerlas, guardarlas bien, y resolverlas solas (acierto + retorno en
unidades) igual que ya pasa con el resto.

Caso real que motiva esto (5 sept 2026, Star Pelaw 22:31 hora España /
21:31 UK): `"GEMELA 3-4 Y 4-3 - STAKE 2 CADA UNA (STAKE 4 TOTAL)"`.
Resultado real: 1º trampa 4, 2º trampa 3 — combinación "4-3" acertada,
dividendo oficial 7.42, retorno 2×7.42=14.84u sobre 4u apostadas
(+10.84u). Se usa como caso de prueba en el plan de implementación.

## Por qué es un tipo de apuesta distinto, no una extensión de doble/triple
`simple`/`doble`/`triple` son **N carreras independientes, 1 selección
cada una**, todas tienen que ganar. Una gemela/trío es **1 carrera, 2 o 3
selecciones**, hay que acertar el ORDEN de llegada entre ellas (exacto o
en cualquier orden si es "reversible"). Además no hay cuota conocida al
apostar — se paga al **dividendo oficial que publica la pista después de
la carrera** (Forecast/Tricast dividend), no a un precio pactado de
antemano. Por eso es un modelo de datos y de resolución aparte, no una
variante de lo que ya existe.

## Hallazgo clave: el dividendo SÍ está disponible
Comprobado en vivo (2026-09-08) contra la API real de Racing Post que ya
usa Proyecto Galgos (`src/utils/vpn.py`, mismo `curl_cffi` con
`impersonate=chrome`, vía la VPN de la VM): la respuesta de
`result-meeting` (la misma llamada que ya se hace para sacar posiciones)
trae, sin pedirlo aparte, dos bloques que hoy se descartan al guardar el
CSV:

```json
"forecasts": { "2222093": [{ "raceId": "2222093", "forecast1st": "4", "forecast2nd": "3", "forecastMoney": "7.42" }] },
"tricasts":  { "<raceId>": [{ "tricast1st": "..", "tricast2nd": "..", "tricast3rd": "..", "tricastMoney": ".." }] }
```

`forecast1st`/`forecast2nd` (y `tricast1st/2nd/3rd`) son las trampas que
de verdad quedaron en esas posiciones; `forecastMoney`/`tricastMoney` es
el dividendo oficial (a stake de 1 unidad, mismo criterio que `cuota` ya
usa el resto del proyecto — `retorno = stake × dividendo`, sin conversión
rara). **No todas las carreras tienen tricast** (campos pequeños no lo
ofrecen) — hay que contemplarlo como "no se puede verificar, pendiente".

Esto significa que la resolución automática completa (acierto Y retorno
exacto) es viable sin depender de una fuente de datos nueva — el dato ya
lo pide el scraper de Proyecto Galgos, solo hay que dejar de tirarlo.

## Arquitectura: cambios en dos proyectos

### Proyecto Galgos (VM, Python) — captar y publicar el dividendo
- `src/scraper/scrape_results.py`: en `scrape_results_for_track`, además
  de los campos por galgo que ya extrae, guardar también los bloques
  `forecasts`/`tricasts` de la respuesta (hoy se leen y se descartan).
- Job de sincronización a Sheets (mismo mecanismo `gspread` que ya empuja
  `resultados_galgos`, push saliente VM→Sheets, nada nuevo en el patrón de
  integración — ver `CLAUDE.md` de este repo) — añade filas a la hoja
  nueva `resultados_gemela_trio` (ver más abajo).
- Fuera de alcance de este documento el detalle fila-a-fila del cambio en
  Proyecto Galgos (stack y despliegue propios, independientes de este
  repo) — el plan de implementación lo cubre como una tarea separada, con
  su propio commit en ese otro repo.

### picks-premier-galgos (Apps Script) — reconocer, guardar, resolver
Todo lo demás: prompt de extracción, hoja nueva de apuestas exóticas,
job de resolución, mensajes de Telegram. Detallado abajo.

## Modelo de datos

### Hoja nueva en el Sheet de Proyecto Galgos: `resultados_gemela_trio`
(la escribe solo el job de la VM, igual que `resultados_galgos` hoy)

| Columna | Contenido |
|---|---|
| `canodromo` | Nombre del hipódromo, mismo formato que `resultados_galgos.canodromo` |
| `fecha` | Fecha de la carrera |
| `hora` | Hora de la carrera |
| `tipo` | `forecast` \| `tricast` |
| `pos1`, `pos2`, `pos3` | Trampas en 1º/2º/3º (pos3 vacío si `tipo=forecast`) |
| `dividendo` | `forecastMoney`/`tricastMoney`, a stake de 1 unidad |
| `race_id` | Id de Racing Post, para depurar |
| `actualizado_en` | Timestamp de escritura |

Clave de cruce: `canodromo + fecha + hora` (mismo criterio que ya usa
`resultado_pata` para cruzar con `resultados_galgos` — reutilizar
`normalizarFechaISO_`/`normalizarHoraSegundos_`/`normalizarTexto_` de
`Auditoria.gs`, ya pensadas para esto).

### Hoja nueva en este proyecto: `apuestas_exoticas`
(la escribe el bot al reconocer el pick; las columnas de resultado las
rellena el job de resolución, como VALORES, no fórmulas — ver más abajo)

| Columna | Contenido |
|---|---|
| `message_id` | Igual que en `apuestas` |
| `fecha_pick` | Igual que en `apuestas` |
| `tipo_apuesta` | `gemela` \| `trio` |
| `hipodromo`, `hora_carrera` | Igual que una pata normal |
| `combinaciones` | Lista de combinaciones tal como las escribió el tipster, ej. `"3-4;4-3"` (gemela reversible) o `"3-4"` (gemela seca). Para trío, 3 números por combinación. |
| `stake_total` | Ej. 4 |
| `stake_por_combinacion` | Ej. 2 (= `stake_total / nº combinaciones`) |
| `resultado_final` | `pendiente` \| `gano` \| `perdio` \| `revision_manual` |
| `combinacion_acertada` | Cuál de `combinaciones` coincidió (vacío si perdió/pendiente) |
| `dividendo` | El de `resultados_gemela_trio` para la combinación acertada |
| `retorno_real` | `stake_por_combinacion × dividendo` si acertó, `0` si perdió, vacío si pendiente |
| `unidades_netas` | `retorno_real - stake_total` |
| `oculto` | Igual que en `apuestas` |
| `mensaje` | Texto original, igual que en `apuestas` |
| `confirm_message_id` | Para poder editar/responder luego, igual que `apuestas` |
| `creado_en` | Timestamp |

No hay `apuestas_patas` para esto — una gemela/trío es una sola carrera,
no tiene sentido partirla en patas. Tampoco entra en las columnas
fórmula de `apuestas` (`resultado_final`, `cuota_final`...): es un tipo de
apuesta con reglas de pago tan distintas que mezclarlo ahí complicaría
las fórmulas existentes sin necesidad — hoja aparte, más simple de leer y
de tocar sin arriesgar lo que ya funciona.

## Extracción con IA (`src/AI.gs`)
Ampliar `EXTRACTION_SYSTEM_PROMPT` con un bloque para gemela/trío:
- Reconoce "GEMELA"/"TRÍO" (con o sin "REVERSIBLE").
- Si el tipster desglosa las combinaciones explícitas (`"3-4 Y 4-3"`), las
  toma tal cual. Si dice "reversible" sin desglosar (`"GEMELA REVERSIBLE
  3-4"`), el propio modelo expande a todas las combinaciones (2 para
  gemela, hasta 6 para trío reversible completo — fuera de alcance por
  ahora, ver "Fuera de alcance").
- Devuelve: `tipo_apuesta` (`"gemela"`/`"trio"`), `hipodromo`,
  `hora_carrera`, `combinaciones` (array de arrays de nº de trampa),
  `stake_total`. Sin `cuota` — campo no aplicable, no se pide.
- `extraerPick` (mismo archivo) necesita una rama nueva: si
  `tipo_apuesta` es `gemela`/`trio`, valida estos campos en vez de los de
  `patas`, y `Main.gs` (`manejarPickNuevo_`) escribe en `apuestas_exoticas`
  en vez de `apuestas`/`apuestas_patas`.

## Resolución (job de script, no fórmula de hoja)
Función nueva, mismo patrón que `reintentarMensajesConError` (disparador
periódico + ejecutable a mano): por cada fila de `apuestas_exoticas` con
`resultado_final=pendiente`, busca su carrera en `resultados_gemela_trio`
por `canodromo+fecha+hora` y `tipo` (forecast para gemela, tricast para
trío). Si no hay fila todavía → se queda pendiente (la carrera no se ha
resuelto, o ese hipódromo no ofrece ese producto para esa carrera). Si la
hay: compara cada elemento de `combinaciones` contra `pos1/pos2(/pos3)`;
si alguna coincide exacta → `gano`, guarda cuál coincidió y su dividendo,
calcula `retorno_real`/`unidades_netas`; si ninguna coincide → `perdio`,
`retorno_real=0`.

Se prefiere script a `ARRAYFORMULA` aquí porque "¿alguna de N
combinaciones coincide con esta pareja/trío exacta?" se vuelve muy
enrevesado como fórmula de hoja — más difícil de leer y de depurar que
una función con un test unitario al lado, que es el patrón que ya sigue
el resto de lógica de negocio de este proyecto (`Dashboard.gs`,
`Auditoria.gs`).

## Mensajes de Telegram
Dos mensajes, ambos como **respuesta** (`reply_to_message_id`) al mensaje
original del pick — mismo criterio que ya usa `sendTelegramMessage` para
todo lo demás:

**Al registrar** (sin cuota, no se sabe todavía):
```
Apuesta registrada (gemela): 22:31 Star Pelaw - T3-T4 y T4-T3 (stake 2u cada una, 4u total)
```

**Al resolverse** (lo manda el job de resolución, decisión explícita del
dueño 2026-09-08 — a diferencia de `apuestas`/`apuestas_patas`, que se
resuelven en silencio y solo se ven en la hoja/panel, aquí SÍ hay un
segundo aviso porque el resultado tarda y no es obvio como un "ganador"
normal):
```
✅ Gemela acertada — 22:31 Star Pelaw: ganó T4-T3, dividendo 7.42, retorno 14.84u (+10.84u)
```
```
❌ Gemela perdida — 22:31 Star Pelaw (ganó T1-T3)
```

## Caso histórico a reparar
El pick de Star Pelaw del 5 de septiembre quedó en `mensajes_crudos` con
`estado=revision_manual` (motivo `tipo_no_soportado`) — nunca se guardó
en ningún sitio estructurado. Una vez implementado esto, una función
puntual (mismo patrón que `repararPicksAtascados_2026_09_02` en
`Main.gs`) lo reprocesa por el camino nuevo: lo mete en
`apuestas_exoticas`, lo resuelve (ya sabemos que acierta, dividendo
7.42), y manda los dos mensajes de Telegram de arriba como si fuera una
recuperación automática — no hace falta que el dueño reenvíe nada.

## Fuera de alcance para esta primera versión
- Apuestas combinadas que MEZCLEN una gemela/trío con otras carreras
  (dobles/triples de otro tipo en el mismo boleto) — a revisión manual,
  como Trixie/Yankee hoy.
- Apuestas "a puesto"/colocado dentro de la gemela/trío.
- Trío reversible completo (6 combinaciones) si el tipster solo dice
  "reversible" sin desglosar — se soporta el caso 2 combinaciones
  (gemela reversible) porque es el único visto en la práctica; si aparece
  un trío reversible real, ampliar entonces con un caso de prueba real
  delante en vez de adivinar el formato.
- Mostrar nombre de galgo en el pick si el tipster solo da número de
  trampa (se muestra por trampa, como en el ejemplo real).
- Cambios en Proyecto Galgos más allá de capturar y publicar
  `forecasts`/`tricasts` — no se toca su dashboard, sus modelos, ni nada
  del pipeline de predicción.
- **Panel público** (`Dashboard.gs`/`Panel.html`): `getMetricasPanel()`
  sigue leyendo solo `apuestas` — las gemelas/tríos NO suman a las
  tarjetas ni a la tabla del panel en esta versión. Se guardan y se
  resuelven bien, pero de momento solo se ven en la hoja `apuestas_exoticas`
  y en Telegram. Sumarlas al panel es una ampliación aparte, con su propia
  decisión de diseño (¿una fila más en la tabla? ¿tarjetas separadas?) que
  no se ha hablado todavía.
