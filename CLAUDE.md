# Reglas para IAs trabajando en este repo

Proyecto nuevo, independiente de "Proyecto Galgos" (stack, hosting y
despliegue distintos). El dueño habla **español** — responder siempre en
español.

## Qué es esto
Bot de Telegram que registra picks de un tipster externo, permite marcar
resultado (manual o automático) y muestra un dashboard con métricas. Ver
`PLAN.md` para arquitectura, esquema de datos y roadmap completos.

## Reglas clave
- **Nunca commitear `config.php` ni ninguna credencial** (bot token, API key
  IA, credenciales MySQL). Van en `config.php` local, ignorado por git; el
  repo lleva `config.example.php` como plantilla.
- **Stake/retorno se registran en unidades, no en moneda** — no exponer el
  bankroll real.
- **Verificación automática de resultados**: nunca inferir sobre ambigüedad.
  Sin match único en `resultados_galgos` (canódromo+fecha+hora+trap) → la
  apuesta queda `pendiente`, el marcado manual es la red de seguridad
  universal.
- **Dedup real por `message_id`** (único de Telegram), no por
  pista+hora+selección (puede repetirse legítimamente).
- La integración con la VM de Proyecto Galgos es **push saliente VM→Sered**
  únicamente. Este repo nunca expone un endpoint para que la VM lo consulte.

## Documentación
Cada cambio significativo se registra en `docs/BITACORA.md` (mismo patrón
que Proyecto Galgos): fecha, qué se hizo y por qué, commits.
