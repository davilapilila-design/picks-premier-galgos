# Panel de métricas (Fase 8) — diseño

Fecha: 2026-08-26

## Objetivo
Cerrar la Fase 8 del [PLAN.md](../../../PLAN.md): un panel web con las
métricas clave de las apuestas ya resueltas, servido desde el propio
proyecto Apps Script (sin hosting nuevo, sin Looker Studio).

## Arquitectura
Un único Web App, dos entradas HTTP:
- `doPost` (ya existe, `src/Main.gs`) — webhook de Telegram, sin cambios.
- `doGet` (nuevo, `src/Dashboard.gs`) — sirve el panel.

Mismo despliegue Web App que ya usa el bot (acceso "cualquier usuario", ya
elegido para el webhook). No hace falta un despliegue nuevo, ni una URL
nueva, ni secrets nuevos: Apps Script enruta por verbo HTTP (GET → `doGet`,
POST → `doPost`) dentro del mismo deployment.

**Acceso**: cualquiera con el enlace, sin login de Google ni contraseña —
mismo criterio que el webhook. Decisión explícita del dueño, ver más abajo
la excepción de euros.

## Archivos nuevos
- `src/Dashboard.gs`:
  - `doGet(e)` → sirve `Dashboard.html` vía `HtmlService.createTemplateFromFile`.
  - `getMetricasPanel()` → lee la pestaña `apuestas`, filtra, calcula y
    devuelve un objeto JSON con las métricas (llamada desde el cliente vía
    `google.script.run`).
- `src/Dashboard.html` — página HTML+CSS+JS mínima, sin frameworks. Carga
  Google Charts (`https://www.gstatic.com/charts/loader.js`) para el
  gráfico de evolución acumulada.

## Filtro de datos
Sobre la pestaña `apuestas`, se incluyen solo las filas donde:
- `oculto = FALSE`, **y**
- `resultado_final` es `"gano"` o `"perdio"` (descarta `"pendiente"` y
  `"revision_manual"` a la vez — ninguna de las dos es un resultado real).

## Métricas (`getMetricasPanel()`)
Sobre el subconjunto filtrado:
- **Unidades netas totales** = suma de `unidades_netas`.
- **Stake total jugado** = suma de `stake`.
- **ROI / yield** = unidades netas totales ÷ stake total × 100 (ratio, se
  queda en %, no se convierte a euros).
- **% de aciertos** = (filas con `resultado_final="gano"` ÷ total de filas
  filtradas) × 100.
- **Evolución acumulada** = las filas ordenadas por `fecha_pick` ascendente,
  con la suma acumulada de `unidades_netas` punto a punto (alimenta el
  gráfico de línea).

Todo se calcula en vivo en cada visita (lee la hoja directamente, sin
caché) — el volumen de datos de este proyecto no lo justifica.

## Euros en el panel (excepción a la regla de unidades)
El resto del proyecto (hoja, bot, scripts de la VM) sigue registrando y
operando **solo en unidades**, sin excepción — ver `CLAUDE.md`. El panel es
la única excepción: las cifras en unidades (unidades netas totales, stake
total) se muestran convertidas a euros con una tasa fija — **1 unidad =
250€**, constante en `src/Dashboard.gs` — antes de pintarlas en el HTML. El
ROI (%) y el % de aciertos no se convierten, son ratios. El gráfico de
evolución acumulada también se pinta en euros.

Esta es una decisión explícita del dueño (2026-08-26), tomada sabiendo que
el panel es de acceso público por enlace: quien tenga la URL vería el
bankroll real convertido a euros. Documentado también en `CLAUDE.md`.

## Interfaz
Página simple: 4 tarjetas arriba (ganancia neta en €, stake total en €,
ROI %, % de aciertos) + gráfico de línea de evolución acumulada (en €)
debajo. Sin tabla de apuestas individuales ni filtros de fecha (fuera de
alcance de esta fase — el PLAN.md ya prevé ampliarlo más adelante si hace
falta).

## Manejo de errores
- Sin ninguna fila resuelta todavía (hoja nueva, o todo `pendiente`/oculto)
  → las 4 tarjetas muestran "Sin datos todavía", no se dibuja el gráfico
  (evita división por cero en el ROI).
- Fallo al leer la hoja → la página muestra un mensaje de error simple en
  vez de quedar en blanco o lanzar una excepción sin capturar.

## Despliegue
Igual que cualquier cambio en `src/*.gs`: `clasp push` + nueva versión +
`clasp redeploy` sobre el mismo deployment ID que ya usa el webhook (mismo
patrón que los redeploys anteriores documentados en `docs/BITACORA.md`). La
URL del panel es la misma `/exec` del webhook, visitada por GET en vez de
POST — no hace falta el `?token=` (eso es solo para el webhook).

## Fuera de alcance
- Tabla de apuestas individuales, filtros de fecha/periodo, desglose por
  tipster o canódromo — quedan para una fase futura si se necesitan.
- Looker Studio — descartado para esta fase, ver conversación previa (no
  tiene API de diseño programable; este panel cubre el mismo propósito con
  control total del código).
