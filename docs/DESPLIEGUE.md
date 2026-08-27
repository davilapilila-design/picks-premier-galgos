# Despliegue del Apps Script (Fases 2, 3 y 5)

El código ya está escrito en `src/` (Fases 2, 4 y 6 del `PLAN.md`). Esto es
lo que queda por hacer, y necesita que estés delante del ordenador porque
son pasos interactivos (login de Google, edición en el navegador).

## 1. Login de `clasp` (una vez)
```
clasp login
```
Abre el navegador, pide iniciar sesión con la cuenta de Google que gestiona
la hoja "Picks Premier Galgos".

## 2. Vincular el proyecto Apps Script a la hoja
`clasp create --parentId TU_SHEET_ID` **no funciona** si la hoja no la creó
la propia `clasp` (falla con "Insufficient Permission" - el scope
`drive.file` que usa solo da acceso a archivos creados por ella misma).
Camino que sí funciona: vincular el script desde la propia hoja.

1. Abre la hoja en el navegador → **Extensiones > Apps Script**. Esto crea
   un proyecto Apps Script vacío, ya vinculado.
2. En el editor, icono de engranaje (**Configuración del proyecto**) →
   copia el **ID del script**.
3. Crea a mano `.clasp.json` en la raíz del repo:
   ```json
   {
     "scriptId": "EL_ID_QUE_COPIASTE",
     "rootDir": "./src"
   }
   ```

Si además de esto `clasp push` da igualmente "Insufficient Permission",
comprueba que la **API de Google Apps Script** está activada en
https://script.google.com/home/usersettings (desactivada por defecto) y
haz `clasp logout` + `clasp login` otra vez para que el token de sesión
recoja el cambio.

## 3. Subir el código
```
clasp push
```
Te preguntará si quieres sobrescribir el manifest (`appsscript.json`) por
defecto del proyecto vacío con el tuyo — confirma que sí.

## 3bis. Construir la hoja (pestañas, cabeceras, fórmulas)
Desde el editor (`clasp open`), Ejecutar > **setupSheet** (función en
`src/Setup.gs`). Crea `mensajes_crudos`, `apuestas` y `resultados_galgos`
con sus columnas y las fórmulas de la sección 5 del `PLAN.md`. Solo se
ejecuta esta vez - no se debe repetir sobre una hoja que ya tenga datos
reales, borraría lo que hubiera.

## 4. Configurar los secrets (Script Properties)
Abre el editor con `clasp open`, y en el icono de engranaje (Project
Settings) → Script Properties, añade estas 3 propiedades a mano (nunca por
código, para que no queden en el repo ni en el historial de Apps Script):
- `TELEGRAM_BOT_TOKEN` → el valor que tienes en tu `.env` local
- `AI_PROVIDER_API_KEY` → la API key de Gemini
- `WEBHOOK_SECRET_TOKEN` → un valor aleatorio que te inventes ahora (p. ej.
  generado con `openssl rand -hex 24`), es el secreto de la URL del webhook

Después, ejecuta la función `checkConfig` desde el editor (Ejecutar >
checkConfig) para confirmar que las 3 están bien puestas — mira el log.

## 5. Desplegar como Web App
Desde el editor: Desplegar > Nueva implementación > tipo "Aplicación web".
- Ejecutar como: tu cuenta (Yo)
- Quién tiene acceso: Cualquier usuario
Copia la URL que te da (acaba en `/exec`).

## 6. Registrar el webhook en Telegram
```
curl "https://api.telegram.org/bot<TU_BOT_TOKEN>/setWebhook?url=<URL_DEL_WEB_APP>?token=<WEBHOOK_SECRET_TOKEN>"
```
(La URL completa lleva el `?token=` pegado al final de la URL `/exec`.)

## 7. Verificar
Manda un pick de prueba al grupo y comprueba que:
- Aparece una fila nueva en `mensajes_crudos`.
- Si el pick es válido, aparece fila en `apuestas` y el bot responde
  confirmando (reply al mensaje original).
- Contesta "ganó" al mensaje de confirmación del bot y comprueba que
  `resultado_manual` se actualiza en la hoja.

## 8. Reintento automático ante cuota de Gemini agotada (2026-08-26)
El tier gratis de `gemini-3.6-flash` solo da **20 peticiones/día** - un pico
de picks (o pruebas) puede agotarla, dejando mensajes en `estado=error` en
`mensajes_crudos`. `reintentarMensajesConError()` (en `Main.gs`) los
reintenta solo; hay que instalar el disparador que la llama periódicamente,
**una vez**, a mano:
1. Abre el editor (`clasp open-script`), abre `Main.gs` para que aparezca
   en el desplegable de funciones.
2. Ejecutar > `configurarTriggerReintentos`. Instala un disparador de
   tiempo (cada 2h) - se puede ver/quitar luego en el reloj de la izquierda
   del editor ("Activadores").
3. Solo hace falta ejecutarlo una vez; si se cambia el intervalo en el
   código, hay que volver a ejecutarlo (borra el disparador viejo antes de
   crear el nuevo).

---

A partir de aquí, cualquier cambio en `src/*.gs` se sube con `clasp push`
(no hace falta repetir `clasp create` ni el despliegue, salvo que cambie la
lógica de forma que quieras versionar una nueva implementación).
