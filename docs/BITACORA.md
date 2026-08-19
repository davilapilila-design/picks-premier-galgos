# Bitácora del proyecto

Registro de cambios significativos (ver regla en `CLAUDE.md`).
Entradas más recientes arriba.

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
