"""
Autorevisión del panel (src/Panel.html) con Playwright, sin depender de
script.google.com (bloqueado por el proxy de los entornos cloud de Claude
Code - ver docs/BITACORA.md 2026-09-25).

Saca los datos REALES con `clasp run-function getMetricasPanel` (va por la
API de Apps Script, que sí es accesible), abre el Panel.html del repo en
Chromium local con `google.script.run` sustituido por esos datos, y
comprueba: errores de JavaScript, que el logo cargue, que el botón de
resumen funcione. Deja capturas de móvil y escritorio.

Ojo: usa el Panel.html del repo, pero getMetricasPanel del HEAD del Apps
Script (lo último que se subió con `clasp push`).

Uso (desde la raíz del repo):
    python3 scripts/revisar_panel_local.py [directorio_capturas]
Requiere: pip install playwright (Chromium ya está en /opt/pw-browsers).
"""
import json
import pathlib
import subprocess
import sys

from playwright.sync_api import sync_playwright

RAIZ = pathlib.Path(__file__).resolve().parent.parent
CHROMIUM = "/opt/pw-browsers/chromium"


def datos_reales():
    salida = subprocess.run(
        ["npx", "--yes", "@google/clasp", "run-function", "getMetricasPanel", "--json"],
        cwd=RAIZ, capture_output=True, text=True, check=True,
    ).stdout
    return json.loads(salida[salida.index("{"):])["response"]


def pagina_con_datos(datos, destino):
    html = (RAIZ / "src" / "Panel.html").read_text(encoding="utf-8")
    stub = ("<script>window.google={script:{run:(function(){let ok;const a={"
            "withSuccessHandler(f){ok=f;return a},withFailureHandler(){return a},"
            "getMetricasPanel(){setTimeout(()=>ok(%s),50)}};return a})()}};</script>" % json.dumps(datos))
    destino.write_text(html.replace("<head>", "<head>\n" + stub, 1), encoding="utf-8")


def revisar(pagina, capturas):
    fallos = []
    with sync_playwright() as p:
        navegador = p.chromium.launch(executable_path=CHROMIUM)
        for nombre, viewport in [("movil", {"width": 390, "height": 844}),
                                 ("escritorio", {"width": 1366, "height": 900})]:
            pg = navegador.new_page(viewport=viewport, locale="es-ES")
            errores = []
            pg.on("pageerror", lambda e: errores.append(str(e)))
            pg.goto(pagina.as_uri())
            pg.wait_for_timeout(1500)
            pg.screenshot(path=str(capturas / f"panel_{nombre}.png"))
            logo_ok = pg.evaluate("() => { const i = document.querySelector('.logo-mark img');"
                                  " return !!(i && i.complete && i.naturalWidth > 0); }")
            # Al pulsarlo, el texto pasa a "Ocultar resumen": se comprueba antes y después.
            resumen_ok = False
            boton = pg.get_by_text("Ver resumen de estos picks")
            if boton.count():
                boton.first.click()
                pg.wait_for_timeout(400)
                resumen_ok = pg.get_by_text("Ocultar resumen").count() > 0
                pg.screenshot(path=str(capturas / f"panel_{nombre}_resumen.png"))
            print(f"[{nombre}] errores JS: {errores or 'ninguno'} | logo: {'OK' if logo_ok else 'NO CARGA'}"
                  f" | boton resumen: {'OK' if resumen_ok else 'NO FUNCIONA'}")
            if errores or not logo_ok or not resumen_ok:
                fallos.append(nombre)
            pg.close()
        navegador.close()
    return fallos


if __name__ == "__main__":
    capturas = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/revision_panel")
    capturas.mkdir(parents=True, exist_ok=True)
    datos = datos_reales()
    print(f"Datos reales: {len(datos.get('historicoPicks', []))} picks en el historial")
    pagina = capturas / "panel_local.html"
    pagina_con_datos(datos, pagina)
    fallos = revisar(pagina, capturas)
    print(f"Capturas en {capturas}")
    sys.exit(1 if fallos else 0)
