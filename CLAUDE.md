# Reglas para IAs trabajando en este repo

Proyecto nuevo, independiente de "Proyecto Galgos" (stack y despliegue
distintos). El dueño habla **español de España** — responder siempre así
(no español latinoamericano).

## Qué es esto
Bot de Telegram que registra picks de un tipster externo en una Google
Sheet, permite marcar resultado (manual o automático) y expone un panel con
métricas. Todo el backend es Google Apps Script + Google Sheets, sin
hosting propio. Ver `PLAN.md` para arquitectura, estructura de la hoja y
roadmap completos.

## Reglas clave
- **Nunca commitear secrets**: bot token, API key de la IA, token propio del
  webhook y clave de la cuenta de servicio de Google van en
  `PropertiesService` (lado Apps Script) o en un archivo local ignorado por
  git (lado VM) — nunca en el código fuente ni en este repo.
- **Stake/retorno se registran en unidades, no en moneda** en la hoja y en
  todo el código de registro/resolución — no exponer el bankroll real ahí.
  Excepción explícita y deliberada (2026-08-26): el **panel de métricas**
  (`src/Dashboard.gs`/`Panel.html`, Fase 8) sí puede mostrar la
  conversión a euros (tasa fija 1 unidad = 250€, constante en el propio
  código del panel) porque el dueño lo pidió así a sabiendas de que el panel
  es de acceso público por enlace (sin login) — no cambia esta regla para
  ningún otro sitio del proyecto.
- **Verificación automática de resultados**: nunca inferir sobre ambigüedad.
  Sin fila exacta en `resultados_galgos` (canódromo+fecha+hora+trap) → la
  apuesta queda `pendiente` (columna fórmula), el marcado manual es la red
  de seguridad universal.
- **Dedup real por `message_id`** (único de Telegram), no por
  pista+hora+selección (puede repetirse legítimamente).
- La integración con la VM de Proyecto Galgos es **push saliente VM→Sheets**
  únicamente (vía `gspread` + cuenta de servicio). Este repo nunca expone un
  endpoint para que la VM lo consulte.
- El código de Apps Script se gestiona con `clasp` para que viva versionado
  en este repo, no solo en el editor web de Google.

## Documentación
Cada cambio significativo se registra en `docs/BITACORA.md` (mismo patrón
que Proyecto Galgos): fecha, qué se hizo y por qué, commits.
