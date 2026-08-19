# Proyecto: Registro de apuestas desde Telegram + Google Sheets

## 1. Objetivo
Capturar automáticamente cada pick publicado en un grupo de Telegram (foto o
texto) de un tipster externo, guardarlo estructurado en una hoja de cálculo,
permitir marcar el resultado (manual o automático) y disponer de un panel con
las métricas clave, mostrando solo las apuestas ya resueltas.

## 2. Por qué Google Sheets y no un hosting con PHP/MySQL

Se descartó la opción inicial (PHP + MySQL en cPanel/Sered) porque el
requisito principal es que la información sea **fácil de manipular a mano**:
corregir un dato, revisar una fila, filtrar por fecha. Con una base de datos
tradicional eso exige comandos o entrar en phpMyAdmin; con una hoja de
cálculo, se edita la celda y punto. Además, Google Apps Script permite recibir
el webhook de Telegram y ejecutar toda la lógica sin contratar ni mantener
ningún hosting.

## 3. Arquitectura

```
Grupo de Telegram (picks de un tipster externo)
        │
        ▼
Google Apps Script — Web App (doPost), es el webhook de Telegram
        │
        ├─ Escribe el mensaje crudo en la hoja `mensajes_crudos` (SIEMPRE,
        │  antes de intentar nada más — así nunca se pierde el original)
        │
        ├─ Si es un pick nuevo (foto o texto) → llama a la IA de
        │  visión/texto → si extrae todos los campos obligatorios, añade
        │  fila en `apuestas`; si falta algo, la deja en estado
        │  `revision_manual` y el bot lo indica al responder
        │
        └─ Si es un reply a la confirmación del bot → interpreta el
           comando: "ganó" / "perdió" / "ocultar" / "mostrar" /
           "corregir campo=valor"
        │
        ▼
Google Sheet "Picks Premier Galgos" (pestañas: mensajes_crudos, apuestas,
resultados_galgos)
        │
        ├─ Las columnas de resultado/retorno de `apuestas` son FÓRMULAS que
        │  buscan en `resultados_galgos` por canódromo+fecha+hora+trampa —
        │  se actualizan solas en cuanto llegan resultados nuevos, sin
        │  necesidad de ningún cron de verificación
        │
        ▼
`resultados_galgos` se alimenta por PUSH desde la VM de Proyecto Galgos
(que ya scrapea Racing Post cada 20 min, mismas pistas) vía un script Python
con cuenta de servicio de Google — la VM nunca expone nada nuevo, solo
escribe hacia fuera
        │
        ▼
Panel: la propia hoja (tabla dinámica/gráfico nativo) o Looker Studio
conectado en modo lectura — el control de acceso es simplemente a quién se
comparte la hoja de Google, sin contraseñas ni código de dashboard
```

## 4. Stack
| Pieza | Tecnología |
|---|---|
| Recepción del webhook + lógica del bot | Google Apps Script (Web App, `doPost`) |
| Almacenamiento | Google Sheets |
| Extracción de datos de la captura | API de Claude (Haiku, recomendado) o Gemini (Flash) desde Apps Script (`UrlFetchApp`) |
| Sync de resultados desde la VM | Python + `gspread` + cuenta de servicio de Google (nuevo paso en `job_poll_results.py`) |
| Panel | Gráficos/tabla dinámica nativos de Sheets, o Looker Studio (opcional, gratis) |
| Control de versiones del código Apps Script | `clasp` (CLI oficial de Google) → el código vive en este repo, no solo en el editor web |

## 5. Estructura de la hoja de cálculo

### Pestaña `mensajes_crudos`
`message_id` · `fecha_recibido` · `contenido` · `foto_file_id` · `estado` (pendiente / procesado / revision_manual / error)

### Pestaña `apuestas`
Columnas de datos (rellenadas por el script):
`message_id` (clave real de deduplicación, único de Telegram) · `confirm_message_id` · `fecha_pick` · `hipodromo` · `hora_carrera` ("HH:MM", normalizada) · `trampa` · `seleccion` · `cuota` · `stake` (en **unidades**, no en moneda) · `retorno_potencial` · `resultado_manual` (vacío / gano / perdio, solo si alguien respondió "ganó"/"perdió") · `oculto` (TRUE/FALSE) · `posible_duplicado_de` (aviso, no bloqueo) · `creado_en`

Columnas **fórmula** (no las toca el script, se recalculan solas):
- `posicion_auto` → `QUERY` contra `resultados_galgos` por canódromo+fecha+hora+trampa
- `resultado_final` → si hay `resultado_manual`, ese manda; si no, se deduce de `posicion_auto`
- `fuente_resultado` → "manual" o "auto" según cuál de las dos se usó
- `retorno_real` / `unidades_netas` → fórmula sobre `cuota`, `stake` y `resultado_final`

### Pestaña `resultados_galgos` (solo la escribe el script de la VM)
`canodromo` · `fecha` · `hora` · `trap` · `nombre` · `posicion` · `actualizado_en`
El script de la VM hace upsert (busca la fila por canódromo+fecha+hora+trap y la actualiza, o la añade si no existe) — nunca deja duplicados.

## 6. Funcionalidades

### 6.1 Registro automático
Llega un mensaje (foto o texto) → se guarda crudo → se procesa **en la misma
ejecución** (Apps Script tiene margen de sobra para llamar a la IA sin
timeouts, a diferencia de un cron de cPanel) → fila en `apuestas` → el bot
responde confirmando, citando el mensaje original.

### 6.2 Marcado de resultado
- **Automático**: en cuanto la VM empuja el resultado de esa carrera, la
  fórmula de `apuestas` lo refleja sola.
- **Manual**: respondiendo "ganó" o "perdió" al mensaje de confirmación,
  siempre disponible como red de seguridad si la pista no estaba cubierta
  ese día o el match no fue exacto.

### 6.3 Corrección y visibilidad
- `corregir cuota=3.5` (o el campo que sea) como reply → corrige un dato mal
  extraído por la IA sin tocar la hoja a mano.
- `ocultar` / `mostrar` como reply → cambia `oculto`, sin borrar nada.

## 7. Verificación automática de resultados
Resuelto: sin scraping nuevo. La VM de Proyecto Galgos ya tiene los
resultados oficiales de Racing Post; un paso nuevo al final de
`automation/job_poll_results.py` (que ya corre cada 20 min) empuja los
resultados recientes (últimas 24-48h) a la pestaña `resultados_galgos` vía
`gspread` y una cuenta de servicio de Google (la hoja se comparte con el
email de esa cuenta de servicio como editor; la clave del servicio vive solo
en la VM, igual que el resto de secrets del proyecto).

Si una pista no fue cubierta ese día, o la hora no coincide exactamente, la
fórmula de `apuestas` simplemente no encuentra fila → `resultado_final`
queda "pendiente" → el marcado manual cubre el hueco. Nunca se infiere sobre
una coincidencia ambigua.

## 8. Extracción de datos de la captura (IA)
Misma disyuntiva que en el plan original, sin cambios:

| | API de Claude (Haiku) | API de Gemini (Flash) |
|---|---|---|
| Costo para este volumen | ~$1/mes o menos | $0 (nivel gratis) |
| Requiere tarjeta | Sí | No |
| Uso de tus datos para entrenar modelos | No | Sí, en el nivel gratis |

Recomendación suave: Claude Haiku, el coste es marginal y evita ceder las
capturas para entrenamiento.

## 9. Panel (dashboard)
La propia hoja, con una pestaña de tabla dinámica/gráfico filtrando
`oculto=FALSE` y `resultado_final <> "pendiente"`: rentabilidad total,
unidades netas, yield/ROI, % de aciertos, evolución acumulada (gráfico
nativo de Sheets). Si más adelante se quiere algo más vistoso o compartible,
Looker Studio se conecta directo a la hoja sin tocar nada de lo anterior.

Control de acceso: compartir la hoja solo con tu cuenta de Google (o "ver"
para quien quieras invitar) — no hace falta contraseña ni código de
autenticación propio.

## 10. Seguridad
- Los Web Apps de Apps Script **no exponen cabeceras HTTP personalizadas**
  en `doPost`, así que en vez del `secret_token` de Telegram (que viaja por
  cabecera) el webhook lleva un parámetro propio en la URL
  (`?token=SECRETO`), comprobado contra un valor guardado en
  `PropertiesService` (nunca en el código ni en el repo).
- Bot token y API key de la IA también en `PropertiesService`, no en el
  código fuente.
- La cuenta de servicio de Google que usa la VM solo tiene acceso de editor
  a **esta hoja concreta**, nada más de tu Google Drive.
- `LockService` en el script para evitar condiciones de carrera si llegan
  dos mensajes casi a la vez.

## 11. Roadmap
- [ ] **Fase 0** — Crear el bot con @BotFather, agregarlo como admin al grupo.
- [ ] **Fase 1** — Crear la hoja de Google con las 3 pestañas y las columnas fórmula.
- [ ] **Fase 2** — Crear el proyecto Apps Script vinculado a la hoja, configurar `clasp` para tenerlo versionado en este repo.
- [ ] **Fase 3** — Guardar secrets (bot token, API key IA, token propio del webhook) en `PropertiesService`.
- [ ] **Fase 4** — Implementar `doPost`: guardar crudo, extraer con IA, escribir en `apuestas`, confirmar por Telegram.
- [ ] **Fase 5** — Desplegar como Web App y registrar la URL (con `?token=`) como webhook de Telegram.
- [ ] **Fase 6** — Implementar comandos por reply: ganó/perdió/ocultar/mostrar/corregir.
- [ ] **Fase 7** — Crear cuenta de servicio de Google, compartir la hoja con ella, escribir el script de push en la VM (`gspread`).
- [ ] **Fase 8** — Montar el panel (pestaña de gráficos nativos o Looker Studio).

## 12. Lo que tienes que hacer tú (no delegable)
1. Crear el bot en Telegram y agregarlo al grupo como admin.
2. Sacar la API key de Claude o Gemini.
3. Crear la hoja de Google y decidir con qué cuenta la gestionas.
4. Crear la cuenta de servicio de Google (Google Cloud Console) para que la VM pueda escribir en la hoja, y compartírsela como editor.
5. Autenticar `clasp` con tu cuenta de Google (login interactivo, una vez).

## 13. Decisiones abiertas
- [ ] ¿Claude Haiku o Gemini Flash? (recomendación: Claude, coste marginal)
- [ ] ¿Panel dentro de la propia hoja o Looker Studio aparte?
