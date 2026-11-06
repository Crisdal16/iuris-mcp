# iuris-mcp — notas para Claude

Servidor MCP propio (Python, stdio) de fuentes jurídicas oficiales. Ver README.md
(qué hace) y FICHA-iuris-mcp.md (registro e historia).

## Entorno (Windows)

- Python: `C:\dev\iuris-mcp\.venv\Scripts\python.exe` (instalacion buena con rotacion
  de IPs; el MCP de Claude apunta aqui). El venv antiguo `C:\Users\crist\iuris-mcp-venv`
  y la copia de OneDrive estan obsoletos. El `.venv/` de esta carpeta en otros equipos
  (Mac) no se usa: cada maquina crea el suyo.
- NO usar `python3`: en esta máquina es el alias de la Microsoft Store y se cuelga.
- Rotacion de IPs: activada solo con `IURIS_ROTACION=true` (ya fijada con setx) y
  `proxies.txt` en la raiz. En la nube NO se usan proxies para CENDOJ (reglas abajo).
- Contenedor/nube: si Chromium no arranca por desajuste pip/contenedor, fijar
  `IURIS_CHROMIUM_PATH` al binario real (p. ej. `/opt/pw-browsers/chromium`).
- Para imprimir tildes en consola: `python -X utf8`.
- Parchear ficheros con Edit, no con heredocs de bash: el shell se come las
  barras invertidas (`\\` → `\`) y rompe regex y rutas.
- Tests: `python -m pytest -q -m "not red"` (sin red, <1 s) y `-q` (con red, ~1 min).
- Tras cambiar `server.py`, el MCP hay que reiniciarlo para que Claude vea los cambios.

## Reglas del proyecto

- Todo es de LECTURA. Solo escriben en disco las tools de guardar/descargar, y
  siempre pasando por `common.texto.ruta_permitida` / `dir_destino`.
- CENDOJ: navegador real solo para BUSCAR, documento a documento; nunca barridos
  masivos ni bases derivadas (aviso legal). No disfrazar peticiones ni evadir captchas.
- Si una fuente aplica anti-bot, se pasa a "humano en el bucle" (enlace oficial), no
  se evade.
- Textos largos: recortar con `common.lecturas.recortar` / `common.texto.truncar`,
  que dejan el resto disponible para `continuar_lectura`.
- Las tools se registran con `@herramienta(...)` en server.py (anotaciones +
  `structured_output=False`). Las nuevas van también en `INSTRUCCIONES` si cambian
  qué tool usar para qué.
- Errores de red: `common.http.describir_error` (distingue servidor oficial caído).

## Trampas conocidas de las fuentes

- CENDOJ `accessToPDF` redirige a `captcha.jsp` («Control · Descargas masivas») cuando
  la IP esta senalada (nube/contenedor compartido, o PC tras un pico de descargas).
  `ErrorCaptcha` (cendoj_live) lo detecta por URL/HTML y devuelve el enlace oficial del
  PDF para humano en el bucle; no reintentar en bucle, no evadir. En el PC del usuario
  la rotacion de IPs es la que evita llegar a ese control.
- BOE `/texto/bloque/<id>` trae TODAS las redacciones; la primera es la original.
  Usar `boe.elegir_version` (bug real corregido en v0.2.0; test de regresión en
  tests/test_boe.py).
- La API del BOE admite búsqueda en servidor: `boe.consultar_api` con sintaxis
  `titulo:(a and b)`, `numero_oficial:"29/1998"`, `rango@codigo:1300`,
  `ambito@codigo:1` (estatal). Códigos de rango: LO 1290, Ley 1300, RDLeg 1310,
  RDL 1320, RD 1340.
- CELLAR: documentos recientes en XHTML; los antiguos solo en `text/html`.
- PETETE (DGT) da 502 intermitentes: es suyo, no nuestro.
- Cualquier plazo o requisito que se escriba en `sources/escritos.py` debe
  contrastarse antes con `buscar_articulo` (redacción vigente).
