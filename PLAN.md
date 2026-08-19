# Proyecto: Registro de apuestas desde Telegram + Dashboard

## 1. Objetivo
Capturar automáticamente cada pick publicado en un grupo de Telegram (foto o
texto) de un tipster externo, guardarlo estructurado, permitir marcar el
resultado (manual o automático) y mostrar un dashboard con métricas clave,
mostrando solo apuestas resueltas.

## 2. Arquitectura

```
Grupo de Telegram (picks de un tipster externo)
        │
        ▼
Webhook PHP (hosting Sered) → responde 200 OK al instante
        │
        ▼
Tabla `mensajes_crudos` (mensaje sin procesar, estado=pendiente)
        │
        ▼ (cron cPanel cada 1-2 min)
IA de visión/texto extrae JSON → valida campos obligatorios
        │
        ├─ OK           → fila en `apuestas` (estado=pendiente resultado)
        └─ falta algo    → estado=revision_manual, el bot pide confirmación
        │
        ▼
Bot confirma en Telegram (sendMessage), citando el mensaje original
        │
        ├─ reply "ganó"/"perdió"        → marca resultado manual
        ├─ reply "corregir campo=valor" → corrige errores de OCR
        ├─ reply "ocultar"/"mostrar"    → oculta/muestra del dashboard
        │
        ▼
Cron de verificación automática (cada 15-30 min)
        │
        └─ busca (canódromo, fecha, hora, trap) en tabla `resultados_galgos`
           (alimentada por PUSH desde la VM de Proyecto Galgos, que ya
           scrapea Racing Post cada 20 min — NUNCA al revés, la VM no
           expone nada nuevo)
           ├─ match único → marca resultado automático
           └─ sin match    → queda pendiente, marcado manual como red de
                              seguridad universal
        │
        ▼
Dashboard (PHP, protegido con .htpasswd), solo apuestas resueltas y no ocultas
```

## 3. Stack
| Pieza | Tecnología |
|---|---|
| Webhook + bot | PHP en hosting Sered (cPanel) |
| Base de datos | MySQL (cPanel) |
| Extracción IA | Claude Haiku (recomendado: ~$1/mes, no entrena con tus datos) o Gemini Flash (gratis) |
| Verificación automática | Push saliente desde la VM Galgos (pymysql) → tabla en MySQL Sered |
| Dashboard | PHP/HTML + Chart.js, protegido con `.htpasswd` |

## 4. Esquema de datos

```sql
CREATE TABLE mensajes_crudos (
  id INT AUTO_INCREMENT PRIMARY KEY,
  message_id BIGINT NOT NULL UNIQUE,
  contenido TEXT NULL,
  foto_file_id VARCHAR(256) NULL,
  estado ENUM('pendiente','procesado','revision_manual','error') DEFAULT 'pendiente',
  creado_en DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE apuestas (
  id INT AUTO_INCREMENT PRIMARY KEY,
  mensaje_crudo_id INT NOT NULL,
  message_id BIGINT NOT NULL UNIQUE,          -- dedup real
  confirm_message_id BIGINT NULL,
  fecha_pick DATETIME NOT NULL,
  hipodromo VARCHAR(64) NOT NULL,
  hora_carrera VARCHAR(8) NOT NULL,            -- "HH:MM", normalizada igual que el lado Python
  trampa INT NULL,
  seleccion VARCHAR(128) NOT NULL,
  cuota DECIMAL(6,2) NOT NULL,
  stake DECIMAL(8,2) NOT NULL,                 -- en UNIDADES, no moneda
  retorno_potencial DECIMAL(10,2) NULL,
  resultado ENUM('pendiente','gano','perdio') NOT NULL DEFAULT 'pendiente',
  retorno_real DECIMAL(10,2) NULL,
  unidades_netas DECIMAL(10,2) NULL,
  fuente_resultado ENUM('auto','manual') NULL,
  posible_duplicado_de INT NULL,               -- aviso, no bloqueo
  oculto TINYINT(1) NOT NULL DEFAULT 0,
  creado_en DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (mensaje_crudo_id) REFERENCES mensajes_crudos(id)
);

-- alimentada por push desde la VM Galgos (nunca al revés)
CREATE TABLE resultados_galgos (
  canodromo VARCHAR(64) NOT NULL,
  fecha DATE NOT NULL,
  hora VARCHAR(5) NOT NULL,
  trap TINYINT NOT NULL,
  nombre VARCHAR(128) NULL,
  posicion TINYINT NULL,
  actualizado_en DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (canodromo, fecha, hora, trap)
);
```

## 5. Seguridad (no negociable)
- Webhook valida `X-Telegram-Bot-Api-Secret-Token`.
- `config.php`/credenciales fuera del webroot o bloqueado por `.htaccess`.
- PDO + prepared statements en todas las queries (entra texto OCR de usuarios).
- Usuario MySQL dedicado para `resultados_galgos` con privilegio mínimo (INSERT/UPDATE/SELECT solo esa tabla), IP de la VM whitelisteada en "Remote MySQL" de cPanel.
- Dashboard con `.htpasswd`.

## 6. Roadmap
- [ ] **Fase 0** — Crear el bot con @BotFather, agregarlo como admin al grupo.
- [ ] **Fase 1** — Crear BBDD MySQL en cPanel, importar esquema (3 tablas).
- [ ] **Fase 2** — Subir PHP al hosting, `config.php` con credenciales (bot token, API key IA, MySQL).
- [ ] **Fase 3** — Registrar webhook de Telegram con secret token.
- [ ] **Fase 4** — Probar ingesta en dos etapas: mensaje crudo → IA → confirmación.
- [ ] **Fase 5** — Comandos por reply: ganó/perdió/ocultar/mostrar/corregir.
- [ ] **Fase 6** — Job de push en la VM Galgos (nuevo paso en `job_poll_results.py`) + Remote MySQL habilitado en Sered.
- [ ] **Fase 7** — Cron de verificación automática (match por canódromo+fecha+hora+trap).
- [ ] **Fase 8** — Dashboard con `.htpasswd` y las 5 métricas + gráfico de evolución.

## 7. Lo que tenés que hacer vos (no delegable)
1. Crear el bot en Telegram y agregarlo al grupo como admin.
2. Sacar la API key de Claude o Gemini.
3. Crear la BBDD MySQL en cPanel, habilitar "Remote MySQL" con la IP saliente de la VM Galgos.
4. Completar `config.php` con credenciales.
5. Crear los Cron Jobs desde cPanel (procesar mensajes crudos, verificación automática).

## 8. Decisiones abiertas
- [ ] ¿Claude Haiku o Gemini Flash? (recomendación: Claude, costo marginal)
- [ ] Repo de GitHub: crear ahora en privado (pendiente de ejecutar `gh` o creación manual)
