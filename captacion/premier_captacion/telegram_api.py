"""
Cliente mínimo de la Bot API de Telegram, solo con la librería estándar
(no hace falta instalar nada en la VM para la fase 1).

Dos tipos de error, porque el bot reacciona distinto a cada uno:
- ErrorTelegram: Telegram contestó y dijo que no (p. ej. 403 "bot was
  blocked by the user"). Reintentar no sirve; se registra y se sigue.
- ErrorRed: no hubo respuesta (red caída, timeout...). La actualización se
  vuelve a procesar cuando vuelva la red.

El token va en la URL de cada petición: ningún mensaje de error ni de log
debe incluir la URL, y por si acaso todo texto de error pasa por
`_ocultar_token`.
"""
import json
import time
import urllib.error
import urllib.request


class ErrorTelegram(Exception):
    def __init__(self, metodo, codigo, descripcion, retry_after=None):
        super().__init__(f"{metodo}: {codigo} {descripcion}")
        self.metodo = metodo
        self.codigo = codigo
        self.descripcion = descripcion or ""
        self.retry_after = retry_after


class ErrorRed(Exception):
    pass


class BotAPI:
    MAX_ESPERAS_429 = 3

    def __init__(self, token, base_url="https://api.telegram.org", timeout_red=30):
        self._token = token
        self._base = f"{base_url}/bot{token}"
        self._timeout_red = timeout_red

    def _ocultar_token(self, texto):
        return str(texto).replace(self._token, "***")

    def llamar(self, metodo, _timeout_red=None, **params):
        """Llama a `metodo` con `params` (los None se omiten); devuelve `result`."""
        cuerpo_peticion = json.dumps(
            {k: v for k, v in params.items() if v is not None}
        ).encode("utf-8")
        for intento in range(self.MAX_ESPERAS_429 + 1):
            peticion = urllib.request.Request(
                f"{self._base}/{metodo}",
                data=cuerpo_peticion,
                headers={"Content-Type": "application/json"},
            )
            try:
                with urllib.request.urlopen(peticion, timeout=_timeout_red or self._timeout_red) as r:
                    cuerpo = r.read()
            except urllib.error.HTTPError as e:
                # Telegram también manda JSON con la descripción en 4xx/5xx.
                cuerpo = e.read()
                e.close()
            except (urllib.error.URLError, OSError) as e:
                # OSError cubre timeouts y conexiones cortadas.
                raise ErrorRed(f"{metodo}: {self._ocultar_token(e)}") from None

            try:
                respuesta = json.loads(cuerpo)
            except ValueError:
                raise ErrorRed(f"{metodo}: respuesta que no es JSON") from None

            if respuesta.get("ok"):
                return respuesta.get("result")

            codigo = respuesta.get("error_code")
            descripcion = self._ocultar_token(respuesta.get("description", ""))
            retry_after = (respuesta.get("parameters") or {}).get("retry_after")
            if codigo == 429 and retry_after and intento < self.MAX_ESPERAS_429:
                # Límite de velocidad: Telegram dice cuánto esperar.
                time.sleep(int(retry_after) + 1)
                continue
            if isinstance(codigo, int) and codigo >= 500:
                # Fallo pasajero del lado de Telegram: se trata como red.
                raise ErrorRed(f"{metodo}: {codigo} {descripcion}")
            raise ErrorTelegram(metodo, codigo, descripcion, retry_after)
