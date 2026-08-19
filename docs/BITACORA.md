# Bitácora del proyecto

Registro de cambios significativos (ver regla en `CLAUDE.md`).
Entradas más recientes arriba.

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
